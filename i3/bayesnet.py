#!/usr/bin/env python

"""Data structures for Bayes nets and nodes."""

import copy

from i3 import toposort


class BayesNetNode(object):
  """A single node in a Bayesian network."""

  def __init__(self, name, parents, sample, score):
    """Initialize Bayes net node based on parents, sampling/scoring functions.

    Args:
      name: a string
      parents: a (potentially empty) list of BayesNetNodes
      sample: a random function taking |parents| arguments
      score: a function mapping a list of arguments and a value to a
        log probability
    """
    for parent in parents:
      assert isinstance(parent, BayesNetNode)
    self.name = name
    self._sample = sample
    self._score = score
    self.parents = parents
    self.sort_parents()    
    self.children = []
    self.sort_children()

  def sort_parents(self):
    """Sort the list of parent nodes."""
    self.parents = tuple(sorted(self.parents))

  def sort_children(self):
    """Sort the list of child nodes."""
    self.children = tuple(sorted(self.children))
    
  def add_parent(self, parent):
    """Add a new parent node."""
    self.parents = tuple(list(self.parents) + [parent])
    self.sort_parents()

  def add_child(self, child):
    """Add a new child node."""
    self.children = tuple(list(self.children) + [child])
    self.sort_children()

  def sample(self, random_world):
    """Sample a value for this node given parent node values.

    Args:
      random_world: a dictionary mapping nodes to values.

    Returns:
      a sampled value
    """
    parent_values = [random_world[parent] for parent in self.parents]
    return self._sample(*parent_values)

  def log_probability(self, random_world, node_value):
    """Return the log probability of node_value for this node given context.

    Args:
      random_world: a dictionary mapping nodes to values.
      node_value: a value for this node

    Returns:
      score: a log probability
    """
    parent_values = [random_world[parent] for parent in self.parents]
    return self._score(parent_values, node_value)

  def markov_blanket(self):
    """Return the list of nodes in the Markov blanket of this node."""
    coparents = [parent for child in self.children for parent in child.parents]
    blanket = list(self.parents) + list(self.children) + coparents
    return set(node for node in blanket if node != self)

  def __str__(self):
    return str(self.name)

  def __repr__(self):
    return str(self.name)

  def __cmp__(self, other):
    return cmp(self.name, other.name)


class BayesNet(object):
  """A Bayesian network."""

  def __init__(self, nodes):
    """Initializes Bayesian network given a list of nodes."""
    assert all(isinstance(node, BayesNetNode) for node in nodes)
    self.nodes = tuple(nodes)
    self.toposort_nodes()

  def toposort_nodes(self):
    """Topologically sort nodes in network."""
    edges = []
    extra_nodes = []
    for node in self.nodes:
      for child in node.children:
        edges.append( (node, child) )
      if not node.children:
        extra_nodes.append(node)
    sorted_nodes = toposort.toposort(edges, extra_nodes, loops_are_errors=True)
    self.nodes = tuple(sorted_nodes)

  def sample(self, random_world=None):
    """Sample an assignment to all nodes in the network."""
    if random_world:
      random_world = copy.copy(random_world)
    else:
      random_world = {}
    for node in self.nodes:
      if not random_world.has_key(node):
        random_world[node] = node.sample(random_world)
    return random_world

  def log_probability(self, random_world):
    """Return the total log probability of the given random world."""
    assert len(random_world) == len(self.nodes)
    log_prob = 0.0
    for node in random_world:
      log_prob += node.log_probability(random_world, random_world[node])
    return log_prob

  def find_node(self, name):
    """Return the (first) node with the given name, or fail.

    Args:
      name: a string

    Returns:
      a BayesNetNode
    """
    for node in self.nodes:
      if node.name == name:
        return node
    raise Exception("Node %s not found!", name)

  def connect(self, parent, child):
    """Add an edge from parent to child.

    Args:
      parent: a BayesNetNode
      child: a BayesNetNode
    """
    parent.add_child(child)
    child.add_parent(parent)
    self.toposort_nodes()