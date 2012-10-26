"""
    GLBackend Database
    ******************

    :copyright: (c) 2012 by GlobaLeaks
    :license: see LICENSE for more details
"""

# this need to be completed for be included, but no more for be used in the
# createQuery loop

__all__ = ['createTables', 'database', 'transactor']

from twisted.internet.defer import inlineCallbacks
from globaleaks import database, transactor
from globaleaks.utils import log

@inlineCallbacks
def createTables():
    """
    @return: None, create the right table at the first start, and initialized the node
    """
    from globaleaks import models
    from globaleaks.db import tables

    for m in [models.node, models.context, models.receiver, models.submission,
              models.tip, models.admin ]:
        for model_name in m.__all__:
            try:
                model = getattr(m, model_name)
            except Exception, e:
                log.err("Error in db initting")
                log.err(e)
            try:
                log.debug("Creating %s" % model)
                yield tables.runCreateTable(model, transactor, database)
            except Exception, e:
                log.debug(str(e))


    nod = models.node.Node()
    is_only_one = yield nod.only_one()

    if False == is_only_one:
        yield nod.initialize_node()
        initvals = yield nod.get_admin_info()
        print "Node initialized with", initvals


