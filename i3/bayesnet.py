"""Data structures for Bayes nets and nodes."""

import itertools
import networkx

from i3 import dist
from i3 import random_world
from i3 import utils


class BayesNetNode(object):
  """General Bayes net node."""

  def __init__(self, index, name=None):
    """Initializes Bayes net node.

    Assumption: the network is fixed--once we use set_net(net), the
    structure of net does not change. If this assumption is violated,
    the caching of parents and children will cause incorrect lookups.

    Args:
      index: Bayesnet-unique identifier (integer)
      name: a string (optional)

    """
    self._children = None
    self._parents = None
    self.compiled = False
    self.index = index
    self.markov_blanket = None
    self.name = name
    self.net = None

  def __str__(self):
    return str(self.name or self.index)

  def __repr__(self):
    return str(self)

  def __cmp__(self, other):
    return cmp(self.index, other.index)

  def __hash__(self):
    return self.index

  def compute_markov_blanket(self):
    """Compute the Markov blanket for this node."""
    coparents = [parent for child in self.children for parent in child.parents]
    overcomplete_blanket = list(self.parents) + list(self.children) + coparents
    markov_blanket = sorted(
      set(node for node in overcomplete_blanket if node != self),
      key=lambda node: node.index)
    return markov_blanket

  def compile(self):
    """Compute and store Markov blanket."""
    assert self.net
    self.markov_blanket = self.compute_markov_blanket()
    self.compiled = True

  def set_net(self, net):
    """Set Bayes net associated with this node."""
    assert not self.net
    self.net = net

  def sample(self, world):
    """Sample node value given parent values in world."""
    raise NotImplementedError

  def log_probability(self, world, node_value):
    """Return log probability of node value given parent values in world."""
    raise NotImplementedError

  @property
  def parents(self):
    if self._parents is None:
      self._parents = sorted(self.net.predecessors(self))
    return self._parents

  @property
  def children(self):
    if self._children is None:
      self._children = sorted(self.net.successors(self))
    return self._children


class DiscreteBayesNetNode(BayesNetNode):
  """Bayes net node with discrete support."""

  def __init__(self, index, name=None, domain_size=None):
    super(DiscreteBayesNetNode, self).__init__(index, name=name)
    self.support = None
    self.domain_size = None
    if domain_size:
      self.set_domain_size(domain_size)

  def set_domain_size(self, domain_size):
    """Set the number of elements in the support of this node."""
    self.domain_size = domain_size
    self.support = range(domain_size)


class DistBayesNetNode(DiscreteBayesNetNode):
  """Bayes net node initialized using distribution."""

  def __init__(self, index, name=None, domain_size=None, distribution=None):
    super(DistBayesNetNode, self).__init__(
      index, name=name, domain_size=domain_size)
    self.distribution = None
    if distribution:
      self.set_distribution(distribution)

  def set_distribution(self, distribution):
    """Set distribution used for sampling and scoring."""
    self.distribution = distribution

  def sample(self, world):
    """Sample from distribution using parent vals as parameters."""
    parent_values = [world.data[parent.index] for parent in self.parents]
    return self.distribution.sample(parent_values)

  def log_probability(self, world, node_value):
    """Compute log probability of value given parent values."""
    parent_values = [world.data[parent.index] for parent in self.parents]
    return self.distribution.log_probability(parent_values, node_value)


class RealBayesNetNode(BayesNetNode):
  """Bayes net node with continuous support."""

  def __init__(self, index, name=None):
    super(RealBayesNetNode, self).__init__(index, name=name)
    self.support = 'R'
    self.domain_size = 'R'


class DistRealBayesNetNode(RealBayesNetNode):

  def __init__(self, index, name=None, distribution=None):
    super(DistRealBayesNetNode, self).__init__(index, name=name)
    self.distribution = None
    if distribution:
      self.set_distribution(distribution)

  def set_distribution(self, distribution):
    """Set distribution used for sampling and scoring."""
    self.distribution = distribution

  def sample(self, world):
    """Sample from distribution using parent vals as parameters."""
    parent_values = [world.data[parent.index] for parent in self.parents]
    return self.distribution.sample(parent_values)

  def log_probability(self, world, node_value):
    """Compute log probability of value given parent values."""
    parent_values = [world.data[parent.index] for parent in self.parents]
    return self.distribution.log_probability(parent_values, node_value)


class DeterministicRealBayesNetNode(RealBayesNetNode):

  def __init__(self, index, name=None, function=None, rng=None):
    super(DeterministicRealBayesNetNode, self).__init__(index, name=name)
    self.function = function
    self.rng = rng

  def get_value(self, world):
    parent_values = [world.data[parent.index] for parent in self.parents]
    return self.function(parent_values)

  def sample(self, world):
    return self.get_value(world)

  def log_probability(self, world, node_value):
    value = self.get_value(world)
    if value == node_value:
      return 0.0
    else:
      return utils.LOG_PROB_0


class TableBayesNetNode(DiscreteBayesNetNode):
  """Bayes net node initialized using CPT."""

  def __init__(self, index, domain_size=None, cpt_probabilities=None,
               name=None):
    """Initializes categorical Bayes net node.

    Args:
      index: Bayesnet-unique identifier (integer)
      domain_size: number of elements in support
      cpt_probabilities: a list of ordered cpt probabilities:
        - node ordering: parent nodes sorted by index (low to high), then self.
            e.g. [parent_5, parent_7, parent_10, node_8]
        - probability ordering: lexicographic based on node ordering.
            e.g. p(node_8=0 | parent_5=0, parent_7=0, parent_10=0)
                 p(node_8=1 | parent_5=0, parent_7=0, parent_10=0),
                 ...
                 p(node_8=1 | parent_5=1, parent_7=1, parent_10=1)
      name: a string (optional)
    """
    super(TableBayesNetNode, self).__init__(
      index, name=name, domain_size=domain_size)
    self.cpt_probabilities = None
    self.distributions = None
    self.parent_multiplier = None
    self.markov_blanket = None
    self.compiled = False
    if domain_size:
      self.set_domain_size(domain_size)
    if cpt_probabilities:
      self.set_cpt_probabilities(cpt_probabilities)

  def compute_distributions(self):
    """Compute the distribution for each setting of parent values."""
    assert self.cpt_probabilities
    assert self.net
    distributions = []
    parent_value_product = itertools.product(
      *[parent.support for parent in self.parents])
    j = 0
    for i, parent_values in enumerate(parent_value_product):
      values = self.support
      j = i * self.domain_size
      probabilities = self.cpt_probabilities[j:j + self.domain_size]
      distributions.append(
        dist.CategoricalDistribution(
          values, probabilities, self.net.rng))
      world = dict(zip(self.parents, parent_values))
      assert (self.distribution_index(world) == i)
    assert j + self.domain_size == len(self.cpt_probabilities)
    return distributions

  def compute_parent_multipliers(self):
    """Compute info used to associate parent values with distributions."""
    reversed_multiplier = []
    multiplier = 1
    for parent in reversed(self.parents):
      reversed_multiplier.append(multiplier)
      multiplier *= parent.domain_size
    parent_multiplier = list(reversed(reversed_multiplier))
    return parent_multiplier

  def distribution_index(self, world):
    """Given parent values, return index that points to correct distribution."""
    return sum(world[parent] * self.parent_multiplier[i]
               for (i, parent) in enumerate(self.parents))

  def get_distribution(self, world):
    """Given parent values in world, return appropriate distribution object."""
    return self.distributions[self.distribution_index(world)]

  def set_cpt_probabilities(self, cpt_probabilities):
    """Set the conditional probability table (CPT)."""
    self.cpt_probabilities = cpt_probabilities

  def compile(self):
    """Compute and store distributions and Markov blanket."""
    self.markov_blanket = self.compute_markov_blanket()
    self.parent_multiplier = self.compute_parent_multipliers()
    self.distributions = self.compute_distributions()
    self.compiled = True

  def sample(self, world):
    """Sample node value given parent values in world."""
    assert self.compiled
    return self.get_distribution(world).sample(None)

  def log_probability(self, world, node_value):
    """Return log probability of node value given parent values in world."""
    assert self.compiled
    return self.get_distribution(world).log_probability(None, node_value)


class BayesNet(networkx.DiGraph):
  """A Bayesian network.

  Creating a network:
  >>> from i3 import utils
  >>> from i3 import bayesnet
  >>> rng = utils.RandomState(seed=0)
  >>> node_1 = bayesnet.TableBayesNetNode(index=0, domain_size=2,
  ...   cpt_probabilities=[0.001, 0.999])
  >>> node_2 = bayesnet.TableBayesNetNode(index=1, domain_size=3,
  ...   cpt_probabilities=[0.002, 0.008, 0.980, 0.980, 0.002, 0.008])
  >>> net = bayesnet.BayesNet(rng,
  ...  nodes=[node_1, node_2],
  ...  edges=[(node_1, node_2)])
  >>> net.compile()

  Sampling random worlds:
  >>> world = net.sample()
  >>> world
  {0: 1, 1: 0}

  Computing the (log) probabilities of random worlds:
  >>> net.log_probability(world)
  -0.011152871797601495
  """

  def __init__(self, rng, nodes=None, edges=None, **attr):
    """Initializes Bayesian network.

    Args:
      rng: a RandomState
      nodes: a list of BayesNetNodes
      edges: a list of pairs of BayesNetNodes
      attr: arguments parsed by networkx.DiGraph
    """
    super(BayesNet, self).__init__(**attr)
    self.rng = rng
    self.compiled = False
    self.nodes_by_index = []
    self.nodes_by_topology = None
    self.node_count = None
    if nodes:
      for node in nodes:
        self.add_node(node)
    if edges:
      self.add_edges_from(edges)

  def __repr__(self):
    return str(self)

  def __str__(self):
    if not self.nodes_by_index:
      return "<<BN>>"
    s = "<<BN\n"
    for node in self.nodes_by_topology or self.nodes_by_index:
      s += "  {} -> {}  {}\n".format(
        node.parents, node, node.domain_size if hasattr(node, 'domain_size') else 'R')
    s += ">>"
    return s

  def compile(self):
    """Compute topological order, Markov blanket, etc."""
    if not self.nodes_by_topology:
      self.nodes_by_topology = tuple(networkx.topological_sort(self))
    self.nodes_by_index = sorted(self.nodes(), key=lambda node: node.index)
    self.node_count = self.number_of_nodes()
    assert ([node.index for node in self.nodes_by_index] ==
            range(self.nodes_by_index[-1].index + 1))
    for node in self.nodes_by_topology:
      node.compile()
    self.compiled = True

  def sample(self, world=None, mutate_world=False):
    """Sample a random world, potentially based on existing world."""
    if world:
      if not mutate_world:
        world = world.copy()
    else:
      world = random_world.RandomWorld()
    for node in self.nodes_by_topology:
      if not node in world:
        world.data[node.index] = node.sample(world)
    return world

  def log_probability(self, world):
    """Return the log probability of this network returning the given world."""
    assert len(world) == self.node_count
    log_prob = 0.0
    for node in self.nodes_by_index:
      log_prob += node.log_probability(world, world[node])
    return log_prob

  def add_node(self, node, attr_dict=None, **attr):
    """Add node to network."""
    assert node not in self.nodes_by_index
    super(BayesNet, self).add_node(node, attr_dict=attr_dict, **attr)
    if self.nodes_by_index:
      assert node.index == self.nodes_by_index[-1].index + 1
    else:
      assert node.index == 0
    node.set_net(self)
    self.nodes_by_index.append(node)

  def find_node(self, name):
    """Return node with given name."""
    for node in self.nodes_by_index:
      if node.name == name:
        return node
    raise ValueError("Node with name {} not found!".format(name))


class BayesNetMap(object):
  """A dict-like collection of factorizations of the same network.

  For each BayesNet added to the collection, check that it has nodes
  with the same support as previous networks.
  """

  def __init__(self):
    self.nets_by_key = {}
    self.node_count = -1
    self.supports = []

  def __len__(self):
    return len(self.nets_by_key)

  def add_net(self, key, net):
    """Add network to collection (with appropriate checks)."""
    assert not key in self.nets_by_key
    if self.node_count == -1:
      assert not self.nets_by_key
      self.node_count = net.node_count
      self.supports = [node.support for node in net.nodes_by_index]
    else:
      assert net.node_count == self.node_count
      for node, support in zip(net.nodes_by_index, self.supports):
        assert node.support == support
    self.nets_by_key[key] = net

  def get_net(self, key):
    """Look up network given key."""
    return self.nets_by_key[key]

  def keys(self):
    """Return keys of map."""
    return self.nets_by_key.keys()

  def values(self):
    """Return values of map."""
    return self.nets_by_key.values()

  def items(self):
    """Return list of (key, BayesNet) pairs."""
    return self.nets_by_key.items()
