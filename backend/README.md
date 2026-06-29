To Start Celery Worker :
```
celery -A app.tasks.celery_app worker --pool=solo --loglevel=error
```

All Neo4J Relationsips and Nodes:
```
MATCH (n)-[r]->(m) RETURN n, r, m;
```

Delete Neo4J Nodes:
```
MATCH (n) DETACH DELETE n;
```
