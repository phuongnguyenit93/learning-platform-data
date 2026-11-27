# Running Elasticsearch for Learning with Docker

To learn Spring Data Elasticsearch, you first need a running Elasticsearch server so your Java application can send documents, create indices, and execute queries. Docker makes it quick to spin up this environment, stop or recreate it when needed, and preserve data in a volume independent of the container lifecycle.

This lesson uses Docker Compose to run an Elasticsearch node on a personal machine. The configuration is scoped for learning purposes: Elasticsearch listens only on the host machine's loopback interface and disables authentication so HTTP examples stay concise. Do not use this configuration in environments with real data or external network access.

## 1. Model for Running Elasticsearch with Docker

When running Elasticsearch with Docker, several components should be distinguished:

| Component | Role |
| --- | --- |
| Docker Engine | Creates and manages containers, networks, and volumes. |
| Elasticsearch image | The image containing Elasticsearch and the runtime needed to start the server. |
| Container | The running Elasticsearch process. Containers can be deleted and recreated. |
| Port mapping | Forwards connections from a host port to the Elasticsearch port inside the container. |
| Named volume | Stores index data outside the container's lifecycle-bound filesystem. |
| Docker Compose | Declares service configurations and how to launch them in a YAML file. |

Connection diagram when the Spring Boot application runs directly on the host machine:

~~~mermaid
flowchart LR
    A["Spring Boot application"] -->|"http://localhost:9200"| B["Port 9200 on host machine"]
    B --> C["Elasticsearch container :9200"]
    C --> D["Named volume esdata"]
~~~

The Java application sends HTTP requests to `localhost:9200`. Docker forwards requests through port mapping to port `9200` inside the container. Elasticsearch processes the requests and stores data in the data directory mounted to the named volume.

The named volume is important: removing a container does not mean deleting the data. When recreating the container and reattaching the `esdata` volume, Elasticsearch can read back previously stored indices.

## 2. Preparing Docker

You need Docker Desktop on Windows/macOS or Docker Engine with the Docker Compose plugin on Linux. The Docker daemon must be running before executing Compose commands.

Check Docker and Compose versions:

~~~bash
docker --version
docker compose version
~~~

Verify that the daemon can accept commands:

~~~bash
docker info
~~~

If the commands above fail, start Docker Desktop or Docker Engine and check again. Modern Docker Compose is invoked as `docker compose` (with a space).

### 2.1. Checking Machine Resources

Elasticsearch is a Java service that uses both heap and native memory. In the example below, heap is set to 1 GB. Allocate at least 2–4 GB of RAM to Docker Desktop so the container OS and Elasticsearch have enough memory beyond the heap. Machines with limited RAM can lower the heap to `512m` for small experiments.

On Linux running Docker Engine directly, Elasticsearch requires a sufficiently high `vm.max_map_count` limit. You can set it temporarily with:

~~~bash
sudo sysctl -w vm.max_map_count=262144
~~~

To persist the setting across Linux reboots, create a sysctl configuration file containing the line:

~~~text
vm.max_map_count=262144
~~~

Then reload the configuration with `sudo sysctl --system`. Docker Desktop runs inside a Linux VM; if logs report a bootstrap check failure related to `vm.max_map_count`, check your VM/WSL2 configuration and the documentation for your Docker Desktop version.

## 3. Creating the Docker Compose File

Create a dedicated directory for your learning environment, such as `elasticsearch-lab`, then create a `compose.yaml` file inside that directory.

~~~yaml
services:
  elasticsearch:
    image: docker.elastic.co/elasticsearch/elasticsearch:8.15.5
    environment:
      discovery.type: single-node
      xpack.security.enabled: "false"
      ES_JAVA_OPTS: "-Xms1g -Xmx1g"
    ports:
      - "127.0.0.1:9200:9200"
    volumes:
      - esdata:/usr/share/elasticsearch/data
    restart: unless-stopped

  kibana:
    image: docker.elastic.co/kibana/kibana:8.15.5
    profiles:
      - ui
    depends_on:
      - elasticsearch
    environment:
      ELASTICSEARCH_HOSTS: '["http://elasticsearch:9200"]'
      XPACK_SECURITY_ENABLED: "false"
    ports:
      - "127.0.0.1:5601:5601"

volumes:
  esdata:
~~~

This is a single-node Elasticsearch configuration suitable for hands-on practice on a personal machine. Key parts:

- `image`: selects Elasticsearch image version `8.15.5`. The version is pinned so recreating the environment yields consistent results. If changing versions, check compatibility with your Spring Data Elasticsearch version and update the Kibana image to match.
- `discovery.type: single-node`: tells Elasticsearch to run in single-node mode without needing multi-machine cluster discovery configuration.
- `xpack.security.enabled: "false"`: disables authentication and TLS so HTTP APIs can be called directly during lessons. Suitable only for local environments.
- `ES_JAVA_OPTS`: sets minimum and maximum heap to the same 1 GB value, preventing the JVM from automatically sizing the heap too large or resizing at runtime.
- `127.0.0.1:9200:9200`: maps host port `9200` to container port `9200` while binding only on loopback. Other machines on the network cannot reach Elasticsearch through this mapping.
- `esdata:/usr/share/elasticsearch/data`: mounts the named volume to Elasticsearch's default data directory.
- `restart: unless-stopped`: allows Docker to restart the service after the Docker daemon restarts, unless the user explicitly stopped the service.
- `profiles: [ui]`: Kibana is optional. Compose only launches Kibana on port `5601` when the `ui` profile is enabled.

Elasticsearch and Kibana should use the same version. If you only need to practice the REST API or Spring Data connections, you can omit the Kibana service from the file altogether.

### 3.1. Why Is a Named Volume Needed?

Elasticsearch writes segments, metadata, and index data to `/usr/share/elasticsearch/data`. Without a mounted volume, data lives inside the container's writable layer. When the container is removed and recreated, that data is lost.

With the `esdata` configuration, Docker manages a named volume and mounts it into the container. You can remove the container while preserving the volume so subsequent runs continue using the existing data.

### 3.2. Why Bind Ports Only to `127.0.0.1`?

`127.0.0.1:9200:9200` restricts incoming connections to the host machine itself. Using `9200:9200` typically causes Docker to bind on all host network interfaces, potentially exposing the service to other machines depending on firewall and network configuration.

In this example, Elasticsearch has security disabled. Restricting the port to loopback avoids accidentally exposing an unauthenticated API. Do not change this to `0.0.0.0` or open the port to the Internet for convenience.

## 4. Starting Elasticsearch

Open a terminal in the directory containing `compose.yaml`, then run:

~~~bash
docker compose up -d
~~~

On the first run, Docker downloads the image if it is not present locally. Compose then creates the network, volume, and container, and starts Elasticsearch in detached mode (`-d`).

Check service status:

~~~bash
docker compose ps
~~~

View startup logs:

~~~bash
docker compose logs -f elasticsearch
~~~

Press `Ctrl+C` to exit log following; this does not stop the container. Elasticsearch needs some time to initialize. Only send requests once the server is ready.

You can check directly in a browser at `http://localhost:9200` or call from the terminal:

~~~bash
curl http://localhost:9200
~~~

On Windows PowerShell, `curl` may be an alias for `Invoke-WebRequest`; use `curl.exe http://localhost:9200` to invoke the real curl binary. A successful response typically returns JSON containing the node name, cluster name, UUID, version, and Elasticsearch tagline.

Check cluster health:

~~~bash
curl "http://localhost:9200/_cluster/health?pretty"
~~~

The `_cluster/health` API returns the cluster status along with node counts, shard counts, and related details. With a single-node setup, a `yellow` status can be normal if an index has replica shards but there is no second node to allocate replicas. `yellow` means primary shards are allocated while some replicas are unassigned; it does not mean Elasticsearch has stopped working.

## 5. Starting Kibana (Optional)

Kibana provides a web UI to inspect indices, documents, and mappings, and to run queries in Dev Tools. If you want to use this interface, run:

~~~bash
docker compose --profile ui up -d
~~~

Wait for Kibana to start, then open `http://localhost:5601`. If the page is not immediately reachable, check the logs:

~~~bash
docker compose logs -f kibana
~~~

Kibana connects to Elasticsearch using the service name `elasticsearch` on the internal Docker network. This address only has meaning inside the Compose network; a browser on the host machine still accesses Kibana via `localhost:5601`.

## 6. Trying the Elasticsearch REST API

Elasticsearch provides a REST API over HTTP. Practicing directly with the API helps clarify what the server receives and returns before Spring Data Elasticsearch automates those operations.

### 6.1. Creating an Index and Mapping

Create the `products` index with an explicit mapping and zero replicas for the single-node exercise:

~~~http
PUT /products
Content-Type: application/json

{
  "settings": {
    "number_of_replicas": 0
  },
  "mappings": {
    "properties": {
      "name": { "type": "text" },
      "sku": { "type": "keyword" },
      "priceInCents": { "type": "long" },
      "active": { "type": "boolean" }
    }
  }
}
~~~

You can send the payload above using Kibana Dev Tools or an HTTP client. If calling from a terminal with curl, use `-X PUT`, the `Content-Type: application/json` header, and pass the JSON in the body. Upon success, Elasticsearch returns confirmation that the index was created.

Inspect the created mapping:

~~~http
GET /products/_mapping
~~~

The mapping defines how Elasticsearch indexes fields. In this example, `name` is `text` for full-text search, while `sku` is `keyword` for exact matching.

### 6.2. Writing a Document

Send a document with `_id` set to `KB-001`:

~~~http
PUT /products/_doc/KB-001
Content-Type: application/json

{
  "name": "Mechanical Keyboard",
  "sku": "KB-001",
  "priceInCents": 129900,
  "active": true
}
~~~

Read the document back:

~~~http
GET /products/_doc/KB-001
~~~

The result contains metadata (`_index`, `_id`, `_version`) and `_source`. This is a starting point for observing the relationship between IDs, JSON documents, and the data stored by Elasticsearch.

### 6.3. Searching Documents

Search by product name content using `match`:

~~~http
GET /products/_search
Content-Type: application/json

{
  "query": {
    "match": {
      "name": "mechanical keyboard"
    }
  }
}
~~~

Search by exact SKU using `term`:

~~~http
GET /products/_search
Content-Type: application/json

{
  "query": {
    "term": {
      "sku": "KB-001"
    }
  }
}
~~~

Search results contain a `hits.hits` array. Each hit has document metadata and usually `_source` returning the JSON fields. You can also try `GET /_cat/indices?v` to list indices or `GET /_cat/nodes?v` to see active nodes.

## 7. Connecting a Spring Data Elasticsearch Application

When the Spring Boot application runs directly on the host machine, configure the URI to point to the published port:

~~~yaml
spring:
  elasticsearch:
    uris: http://localhost:9200
~~~

Place this configuration in `application.yml` or in a profile for the learning environment. The application needs the Spring Data Elasticsearch dependency compatible with your project's Spring Boot version. After the application starts, repositories or `ElasticsearchOperations` will use the configured client to communicate with the server.

Key notes about connection addresses:

| Where the Java Application Runs | Typical URI |
| --- | --- |
| Java running directly on the host machine | `http://localhost:9200` |
| Java running in another service on the same Compose network | `http://elasticsearch:9200` |
| Java running in an independent container not on the same network | Must attach the container to the same network or configure a reachable network address. |

`localhost` inside a Java container refers to that Java container itself, not the host machine and not the Elasticsearch container. When two services share a Compose project, the service name `elasticsearch` is resolved by Docker DNS to the corresponding container's address.

Example adding the application service to the same Compose file:

~~~yaml
services:
  elasticsearch:
    image: docker.elastic.co/elasticsearch/elasticsearch:8.15.5
    environment:
      discovery.type: single-node
      xpack.security.enabled: "false"
      ES_JAVA_OPTS: "-Xms1g -Xmx1g"
    ports:
      - "127.0.0.1:9200:9200"
    volumes:
      - esdata:/usr/share/elasticsearch/data

  app:
    build: .
    environment:
      SPRING_ELASTICSEARCH_URIS: http://elasticsearch:9200
    depends_on:
      - elasticsearch

volumes:
  esdata:
~~~

`depends_on` in its simple form only guarantees container startup order, not that Elasticsearch is ready to accept requests. Real-world applications should have appropriate connection retry mechanisms or health checks instead of assuming the server is ready the instant the container is created.

## 8. Managing the Environment Lifecycle

Common commands used during hands-on practice:

| Command | Effect |
| --- | --- |
| `docker compose up -d` | Creates and starts services in the background. |
| `docker compose ps` | Shows the status of containers belonging to the Compose project. |
| `docker compose logs -f elasticsearch` | Follows Elasticsearch logs. |
| `docker compose stop` | Stops containers while keeping containers and volumes. |
| `docker compose start` | Restarts stopped containers. |
| `docker compose restart elasticsearch` | Restarts the Elasticsearch service. |
| `docker compose down` | Stops and removes containers and networks created by Compose; named volumes are preserved. |
| `docker compose down -v` | Also removes named volumes managed by Compose; Elasticsearch data in that volume is deleted. |

Distinguish clearly between `down` and `down -v`. When you only want to shut down the environment after a study session, use:

~~~bash
docker compose down
~~~

The next time you run `docker compose up -d`, Compose creates a new container and reattaches the `esdata` volume, so your data remains intact.

Only when you want to wipe all learning data and start fresh should you use:

~~~bash
docker compose down -v
~~~

This command destroys data stored in the Compose project's volumes. If you only want to delete a single index, use the `DELETE /products` API instead of deleting the entire volume.

## 9. Troubleshooting Common Errors

### Docker Daemon Is Not Running

A typical symptom is the Docker CLI reporting it cannot connect to the daemon or Docker Desktop engine. Open Docker Desktop or start Docker Engine, wait until it is ready, and retry `docker info` and `docker compose up -d`.

### Port 9200 Is Already in Use

Compose may report it cannot bind host port `9200`. Check which process or container is occupying that port. You can change the host port, for example:

~~~yaml
ports:
  - "127.0.0.1:9201:9200"
~~~

When changed like this, applications running on the host must connect to `http://localhost:9201`; the port inside the container remains `9200`. Other services on the same Compose network still connect to `http://elasticsearch:9200`.

### Elasticsearch Starts and Then Exits

Inspect the logs with `docker compose logs elasticsearch`. Common causes include insufficient RAM, a heap setting too large for allocated resources, write permissions on the data directory, or failed Linux bootstrap checks. Adjust Docker resources and configuration according to the specific error message; avoid deleting the volume immediately because it may contain data you want to keep.

### `vm.max_map_count` Error on Linux

If the log specifically indicates the map count limit is too low, set `vm.max_map_count` to at least `262144` on the Linux host running Docker and restart the service. On Docker Desktop, check the Linux VM/WSL2 instance used by Docker.

### Application Reports Connection Refused

Check `docker compose ps`, Elasticsearch logs, and call `http://localhost:9200` from the host machine itself. Ensure the application uses the exact published host port. If Java runs in a container on the same network, use the service hostname `elasticsearch` instead of `localhost`.

### Calling HTTP When Server Requires HTTPS or Authentication

This lesson disables security in the local configuration. If security is enabled or you use a different Elasticsearch configuration, the endpoint may require HTTPS and login credentials. In that case, configure the corresponding URI, certificates, and credentials in the application; do not disable security on a shared cluster just to make an example run.

### Cluster Status Is Yellow

With a single-node cluster, replica shards cannot be allocated to a second node. If primary shards are active, a yellow status usually still allows writes and searches. To make a single-node practice setup green, set `number_of_replicas` to `0` when creating indices, as shown in the `products` example above.

## 10. Security and Limitations of the Learning Environment

The sample configuration intentionally sets `xpack.security.enabled=false` so learners can focus on documents, mappings, repositories, and queries. That means any process able to reach the open port can call Elasticsearch APIs without authentication.

Safety boundaries for this configuration:

- Run only on a personal machine or isolated lab environment.
- Keep the port mapping bound to `127.0.0.1`; do not publish ports to public network interfaces.
- Do not store sensitive data or real customer data in this environment.
- Do not use a security-disabled configuration for staging or production.
- When a shared environment is needed, enable security, configure TLS, and set up credentials according to appropriate deployment guidelines.

Pinning the image version also keeps the learning environment reproducible. When upgrading Elasticsearch, review release notes, Spring Data Elasticsearch compatibility, and data upgrade procedures. Avoid automatically switching the tag to `latest` because the server version can change without corresponding updates in the application.

## 11. Recommended Practice Workflow

You can follow this sequence each time you start a learning session:

1. Check the Docker daemon with `docker info`.
2. Open a terminal in the directory containing `compose.yaml`.
3. Run `docker compose up -d` and verify `docker compose ps`.
4. Follow logs until Elasticsearch is ready.
5. Call `http://localhost:9200` and `_cluster/health` to confirm connectivity.
6. Create indices, mappings, and documents via the REST API or Kibana Dev Tools.
7. Connect Spring Boot via `spring.elasticsearch.uris` and practice repositories/queries.
8. End the study session with `docker compose down` to preserve data for next time.

When you want to delete data to start over from scratch, confirm you are in the right Compose project before running `docker compose down -v`.

Running Elasticsearch in Docker provides a standalone server for Spring Data Elasticsearch lessons. Docker Compose describes how to spin up the server, port mapping lets the application connect, the named volume preserves data across container recreations, and the REST API lets you verify the server before bringing Spring Data into the workflow.
