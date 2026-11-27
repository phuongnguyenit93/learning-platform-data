# Configuring Shard Count, Replicas, and Refresh Interval by Environment

When creating an index in Elasticsearch, in addition to the mapping describing document structure, you must also choose settings that affect how data is distributed, replicated, and made visible to queries. Three settings that commonly require attention are the primary shard count, replica shard count, and refresh interval.

These values directly impact storage capacity, fault tolerance, write speed, search latency, and cluster operational costs. A configuration suitable for a single-node development machine may not fit staging or production with multiple data nodes. Therefore, a Spring Data Elasticsearch application should separate index configuration from business code and select values according to the deployment environment.

After this lesson, you will be able to:

- Distinguish between primary shards and replica shards, and explain how Elasticsearch distributes shards.
- Estimate the number of primary shards based on data volume and workload.
- Choose an appropriate replica count for the cluster topology and availability requirements.
- Explain the refresh interval and its impact on search latency as well as indexing performance.
- Identify which settings can only be configured at index creation and which can be updated on a running index.
- Declare settings using the Elasticsearch API, Spring Data Elasticsearch annotations, JSON files, or profile-based configuration.
- Verify actual settings after the application creates or updates an index.

## 1. Three Settings to Distinguish

An Elasticsearch index is divided into shards. Each primary shard stores a portion of the index's data; a replica shard is a copy of the corresponding primary shard. Refresh is the process of making indexed changes visible to search operations.

| Setting | Meaning | Can be changed while the index is open? |
| --- | --- | --- |
| `index.number_of_shards` | Number of primary shards of the index | No; must be specified when creating the index |
| `index.number_of_replicas` | Number of replicas per primary shard | Yes |
| `index.refresh_interval` | Time interval between automatic refreshes | Yes |

The three settings serve three different goals:

- Primary shard count shapes how data is partitioned and the parallelism level of the index.
- Replica count determines the number of shard copies, affecting fault tolerance, storage volume, and search serving capacity.
- Refresh interval determines the latency between writing a document and that document becoming findable via search.

Do not pick these three values based on a single environment. Consider the number of data nodes, expected data volume, read/write traffic, recovery objectives, and result freshness requirements.

## 2. Primary Shards and Replica Shards

### 2.1. Primary Shards

Elasticsearch splits an index's data into one or more primary shards. Each shard is an independent Lucene index. When a document is written, Elasticsearch uses routing (computed by default from the document ID) to determine the primary shard responsible for storing that document.

For example, the `catalog-products` index has three primary shards:

~~~text
catalog-products
├── primary shard 0
├── primary shard 1
└── primary shard 2
~~~

Primary shards can be distributed across multiple data nodes. This allows an index to store more data than a single shard's capacity and distributes search or indexing work across multiple nodes.

The primary shard count is an important setting because it defines how index data is partitioned. Elasticsearch does not allow changing `index.number_of_shards` directly on an already created index, even by closing and reopening it. If a different number of primary shards is needed, you typically must create a new index with the new configuration and reindex the data; in some cases, the split or shrink API can be used when the prerequisites for those operations are met.

### 2.2. Replica Shards

A replica shard is a copy of a primary shard. If each primary shard has one replica, an index with three primary shards will have three replica shards:

~~~text
catalog-products
├── primary shard 0  ── replica shard 0
├── primary shard 1  ── replica shard 1
└── primary shard 2  ── replica shard 2
~~~

Elasticsearch attempts to place copies of the same shard on different nodes. Thus, replicas can serve search queries and replace a primary if the node holding the primary fails, provided the remaining copy is allocated and healthy.

If an index has \(P\) primary shards and \(R\) replicas per primary shard, the total number of allocated shard copies is:

\[
\text{Total shard copies} = P \times (1 + R)
\]

Examples:

| Primary shards | Replicas per primary | Total shard copies |
| ---: | ---: | ---: |
| 1 | 0 | 1 |
| 1 | 1 | 2 |
| 3 | 1 | 6 |
| 3 | 2 | 9 |
| 5 | 1 | 10 |

The replica count can be changed while the index is active. Increasing replicas increases storage usage and replication work during writes, but can improve fault tolerance and read query capacity. Replicas are not standalone backups; snapshots and data recovery procedures are still necessary.

### 2.3. Distributing Shards Across Nodes

Suppose a cluster has three data nodes and an index has three primary shards with one replica each:

~~~text
Data node A          Data node B          Data node C
-----------          -----------          -----------
primary 0            replica 0            primary 1
replica 2            primary 2            replica 1
~~~

This is only an illustrative diagram. Elasticsearch decides shard placement automatically based on cluster state and allocation rules. Copies of the same shard are not placed on the same node so that a replica remains useful if that node loses connectivity.

If a cluster has only one data node but the index requests one replica, the replica cannot be placed on the node holding the corresponding primary. The index may remain in a `yellow` state because primaries are allocated while replicas are unassigned. This is why single-node local environments typically set `number_of_replicas` to `0`.

In production, the replica count should be based on the number of nodes able to hold shards, availability zones, fault-tolerance requirements, and operational policies. Having more replicas than available allocation targets does not automatically make a cluster safer; unplaceable copies remain in an `unassigned` state.

## 3. Choosing the Primary Shard Count

### 3.1. There Is No Single Right Number for Every Index

The primary shard count should be determined based on:

- Expected data size after indexing and after growth periods.
- Number of documents and average document size.
- Write rate and concurrent query traffic.
- Number of data nodes, disk space, and CPU/RAM resources.
- Acceptable time for shard recovery after a failure.
- Whether queries typically access a subset of data or nearly the entire index.

Too few shards can cause a shard to grow too large, limiting load distribution and lengthening recovery times. Too many small shards increase cluster metadata and management overhead, and many queries must fan out across more shards.

Elastic's sizing guidance provides a common reference range of roughly 10 GB to 50 GB per shard and recommends keeping the document count per shard below roughly 200 million. This is a starting guideline for evaluation, not a hard limit or a formula replacing benchmarking. Specific workloads, data types, and infrastructure may fit smaller or larger shards.

### 3.2. Initial Estimation

You can make a rough estimate based on the expected primary data size:

\[
\text{Initial primary shard count}
\approx
\left\lceil
\frac{\text{Expected primary data size}}
{\text{Target size per shard}}
\right\rceil
\]

For example, if primary data after indexing is expected to be around 120 GB and the team chooses a planning target of about 30 GB per shard, you can start testing with four primary shards.

This number is only a starting point. Input JSON data size does not necessarily equal the index size on disk. Mappings, analyzers, doc values, compression, segments, and update/delete rates all affect actual size. Generate representative data, measure shard sizes, and benchmark with real queries.

### 3.3. Shard Count and Scalability

Increasing primary shards can help distribute data and work across multiple nodes, but more shards does not always mean faster searches. A query on a multi-shard index usually must execute on each relevant shard and then merge the results. When there are too many small shards, coordination overhead can outweigh parallelism gains.

If an index is expected to grow continuously, consider index lifecycle management. For time-based data, data streams combined with index templates and rollover policies allow each backing index to have an appropriate shard count. When rollover creates a new index, you can adjust the primary shard count in the template for future indexes.

### 3.4. Changing Shard Count After an Index Already Has Data

`index.number_of_shards` cannot be modified via the Update Index Settings API on a running index. When the initial design is no longer suitable, common approaches are:

1. Create a target index with the new primary shard count.
2. Reindex documents from the old index into the new index.
3. Verify mapping, document count, queries, and search results.
4. Switch read/write aliases to the new index.
5. Delete the old index only after confirming the transition process and when retention policies permit.

The split API can increase shard count under certain conditions; the shrink API can decrease shard count on a properly prepared index. Both have specific operational prerequisites and are not arbitrary shard-count toggles. For many applications, creating a new index and reindexing is easier to control.

## 4. Choosing the Replica Count

### 4.1. What Do Replicas Affect?

Replicas have three primary impacts:

**Fault tolerance.** If a node holding a primary goes down, an allocated replica on another node can be promoted to primary. Recovery time and capability depend on the copy's state, the cluster, and recovery mechanisms.

**Read capacity.** Searches can be routed to either primary or replica shards. Additional replicas can help the cluster handle more read queries, depending on workload and node resources.

**Write and storage cost.** Every write must be replicated to replicas. More replicas increase storage usage and network traffic, while consuming CPU, disk I/O, and recovery resources.

### 4.2. Choosing Replicas by Topology

An initial guideline table:

| Environment/topology | Common starting value | Reason |
| --- | ---: | --- |
| Single-node local | 0 | Avoids unassigned replicas and `yellow` status |
| Temporary single-node test | 0 | Saves resources, tests logic |
| Small dev cluster | 0 or 1 | Depends on node count and testing needs |
| Multi-node staging | Same as production | Tests distribution and recovery behavior close to reality |
| Multi-node production | Usually at least 1 | Provides copies on other nodes to support availability |

These are initial suggestions, not mandatory configurations. For instance, a single-node production cluster cannot distribute replicas to another node. Conversely, a staging environment meant to simulate production may need the same replica count and equivalent topology as production.

Setting replicas to 0 reduces the index's fault tolerance. If the sole node holding the primary fails or shard data becomes corrupted, there is no replica in the cluster to take over. Snapshots, backups, monitoring, and a recovery plan remain essential.

### 4.3. Cluster Health and Replicas

Cluster health generally has three statuses:

| Status | Meaning |
| --- | --- |
| `green` | All primary and replica shards are allocated |
| `yellow` | All primary shards are allocated, but some replicas are unallocated |
| `red` | At least one primary shard is unallocated |

A `yellow` index in a single-node local setup may simply occur because a replica has no other node to reside on. However, in production, persistent `yellow` status must be investigated because it may reflect missing nodes, disk watermarks, allocation rules, or shard failures.

Status can be inspected with:

~~~http
GET /_cluster/health/catalog-products
~~~

## 5. What Is the Refresh Interval?

### 5.1. Refresh Makes Documents Searchable

When a document is indexed or updated, Elasticsearch does not necessarily make that change appear in search results immediately. Refresh opens prepared changes inside a shard so they can be found by search.

`index.refresh_interval` specifies the time interval between automatic shard refreshes. In the Elastic Stack, the default value is typically `1s`; on Elastic Cloud Serverless, the default is `5s` and minimum limits differ as well. Specific behavior also depends on the version and service type, so check the documentation for the environment in use.

Example:

~~~json
{
  "index": {
    "refresh_interval": "2s"
  }
}
~~~

With a longer refresh interval, new data may take longer before appearing in search, but Elasticsearch reduces the frequency of creating search-visible segments. This often improves indexing performance when the workload is write-heavy.

### 5.2. Refresh Is Not Flush

Refresh and flush are two different operations:

- Refresh makes indexed changes visible to search.
- Flush creates a Lucene commit and processes the transaction log according to Elasticsearch's internal mechanisms.

Do not interpret the refresh interval as how often new data is durably persisted. Write durability also involves the translog, durability settings, and Elasticsearch acknowledgments. Refresh primarily controls search visibility.

### 5.3. Trade-off Between Freshness and Performance

| Refresh interval | Search visibility latency | Typical impact |
| --- | --- | --- |
| `1s` | Low | Search sees new data quickly, refreshes happen more frequently |
| `5s` | Higher | Reduces refresh frequency, can increase indexing performance |
| `30s` | Even higher | Better suited for write-heavy workloads accepting slower search updates |
| `-1` | No automatic refresh | Used in a controlled way during bulk indexing; must refresh again when finished |

A short interval is not always better. Frequent refreshes create additional small segments, increasing merge work and I/O overhead. A longer interval batches more changes between refreshes, though it delays search result updates.

### 5.4. Manual Refresh and `refresh=wait_for`

If a business flow needs to find a document immediately after writing, you can use the write API's refresh parameter:

~~~http
POST /catalog-products/_doc/sku-1001?refresh=wait_for
{
  "sku": "sku-1001",
  "name": "Keyboard"
}
~~~

`refresh=wait_for` waits for the next refresh to make the change visible. This is generally preferable to forcing an immediate refresh after every request with `refresh=true`, because it can wait for the scheduled refresh rather than triggering a separate refresh per write.

Spring Data Elasticsearch also supports refresh options in certain save/index APIs via the corresponding options of the version in use. When read-after-write guarantees are needed, choose a refresh policy based on the actual API and measure the impact on throughput.

Do not trigger a manual refresh after every single document save. Doing so can turn a write-heavy flow into a continuous stream of refreshes, degrading cluster performance.

### 5.5. Disabling Refresh During Bulk Indexing

When loading a large initial dataset, you can temporarily set the refresh interval to `-1` to disable automatic refreshes:

~~~http
PUT /catalog-products/_settings
{
  "index": {
    "refresh_interval": "-1"
  }
}
~~~

After completing bulk indexing, restore the refresh interval and trigger a refresh:

~~~http
PUT /catalog-products/_settings
{
  "index": {
    "refresh_interval": "1s"
  }
}
~~~

~~~http
POST /catalog-products/_refresh
~~~

Use this procedure only for controlled bulk phases. If you forget to restore the refresh interval, new documents may not appear in search until a manual refresh occurs. Also consider other clients reading from the index during data loading.

## 6. Configuring Index Settings When Creating an Index

### 6.1. Creating an Index via the Elasticsearch API

Settings can be declared alongside mappings in the Create Index API:

~~~http
PUT /catalog-products-v1
{
  "settings": {
    "number_of_shards": 3,
    "number_of_replicas": 1,
    "refresh_interval": "1s"
  },
  "mappings": {
    "properties": {
      "sku": {
        "type": "keyword"
      },
      "name": {
        "type": "text"
      },
      "price": {
        "type": "double"
      }
    }
  }
}
~~~

In the example, the index has three primary shards, each primary has one replica, and automatic refresh runs every second. When enough data nodes exist for distribution, there are six shard copies in total.

Settings at index creation time determine the primary shard count. Prepare mappings and settings together to avoid an index being created beforehand with default settings before realizing the shard count needs to change.

### 6.2. Updating Dynamic Settings

Replicas and refresh interval can be updated on an existing index via the Update Index Settings API:

~~~http
PUT /catalog-products-v1/_settings
{
  "index": {
    "number_of_replicas": 2,
    "refresh_interval": "5s"
  }
}
~~~

The request above changes the replica count from one to two and the refresh interval to five seconds. You cannot include `number_of_shards` in the request to alter the primary shard count of an existing index.

If you want to reset a setting to its default, Elasticsearch supports setting that setting's value to `null` in the Update Index Settings API. Check the exact version and service defaults before using this approach.

### 6.3. Classifying Settings

| Setting | Type | How to change |
| --- | --- | --- |
| `index.number_of_shards` | Static | At index creation; structural changes require split, shrink, or creating a new index |
| `index.number_of_replicas` | Dynamic | Update Index Settings API |
| `index.refresh_interval` | Dynamic | Update Index Settings API |

Changing replicas or refresh interval takes effect on a running index, but that does not mean the application automatically applies new values merely because a YAML profile changed. You need a process to send the update to Elasticsearch or create a new index with that configuration.

## 7. Declaring Settings in Spring Data Elasticsearch

Spring Data Elasticsearch can generate settings from annotations or JSON files. When values must vary by profile, you can combine Spring Boot configuration with `IndexOperations` to create the index with the bound values.

### 7.1. Using `@Setting` for Fixed Configuration

For an index with identical configuration across all environments, you can declare it directly:

~~~java
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Setting;

@Document(indexName = "catalog-products")
@Setting(
    shards = 3,
    replicas = 1,
    refreshInterval = "1s"
)
public class ProductDocument {
    // Document fields
}
~~~

Common attributes of `@Setting`:

- `shards`: number of primary shards when creating the index.
- `replicas`: number of replicas per primary shard when creating the index.
- `refreshInterval`: refresh interval when creating the index.
- `settingPath`: classpath path to a JSON file containing settings.
- `useServerConfiguration`: omits entity settings so Elasticsearch uses server-side configuration.

The published defaults in current Spring Data Elasticsearch for the annotation are one shard, one replica, and a `1s` refresh interval. Elasticsearch defaults and service behaviors may differ; explicitly declare important values rather than relying on implicit defaults.

`@Setting` is used when Spring Data creates the index. If the index already exists, editing the annotation and restarting the application does not automatically change the existing index's settings. Inspect and update them via index management APIs.

### 7.2. Using a JSON Settings File

When there are many settings or you want to manage settings outside annotations, you can use `settingPath`:

~~~java
@Document(indexName = "catalog-products")
@Setting(settingPath = "/elasticsearch/settings/catalog-settings.json")
public class ProductDocument {
    // Document fields
}
~~~

Example `src/main/resources/elasticsearch/settings/catalog-settings.json`:

~~~json
{
  "index": {
    "number_of_shards": 3,
    "number_of_replicas": 1,
    "refresh_interval": "1s"
  }
}
~~~

Spring Data reads the settings file from the classpath when creating the index. Current Spring Data documentation also supports SpEL expressions for `settingPath`, so you can choose a resource based on a bean or environment configuration if the project intentionally designs that resolution logic. For applications needing explicit profile-selection logic, configuring via `@ConfigurationProperties` and `IndexOperations` is often easier to control.

### 7.3. Letting the Server or Index Template Manage Settings

If cluster administrators manage settings via index templates, the entity can use:

~~~java
@Document(indexName = "catalog-products")
@Setting(useServerConfiguration = true)
public class ProductDocument {
    // Document fields
}
~~~

`useServerConfiguration = true` instructs Spring Data not to send entity settings when creating the index. In that case, settings can come from Elasticsearch-side configuration, such as an index template matching the index name. This is useful when multiple applications must follow an index standard managed by the operations team.

### 7.4. Creating an Index with Settings from a Spring Profile

When local, dev, staging, and production need different values, you can bind them into a configuration class:

~~~java
package com.example.catalog.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.elasticsearch.index")
public class ProductIndexProperties {

    private int shards = 1;
    private int replicas = 0;
    private String refreshInterval = "1s";

    public int getShards() {
        return shards;
    }

    public void setShards(int shards) {
        this.shards = shards;
    }

    public int getReplicas() {
        return replicas;
    }

    public void setReplicas(int replicas) {
        this.replicas = replicas;
    }

    public String getRefreshInterval() {
        return refreshInterval;
    }

    public void setRefreshInterval(String refreshInterval) {
        this.refreshInterval = refreshInterval;
    }
}
~~~

Register the configuration with `@ConfigurationPropertiesScan` on the application class or `@EnableConfigurationProperties(ProductIndexProperties.class)` in a configuration class:

~~~java
@SpringBootApplication
@ConfigurationPropertiesScan
public class CatalogApplication {
    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
~~~

Then use `ElasticsearchOperations` and `IndexOperations` to create the index with the active settings:

~~~java
import java.util.Map;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.boot.ApplicationRunner;
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.IndexOperations;
import org.springframework.data.elasticsearch.core.document.Document;

@Configuration
public class ProductIndexConfiguration {

    @Bean
    ApplicationRunner createProductIndex(
            ElasticsearchOperations operations,
            ProductIndexProperties properties) {

        return args -> {
            IndexOperations indexOperations =
                operations.indexOps(ProductDocument.class);

            if (!indexOperations.exists()) {
                Map<String, Object> settings = Map.of(
                    "index", Map.of(
                        "number_of_shards", properties.getShards(),
                        "number_of_replicas", properties.getReplicas(),
                        "refresh_interval", properties.getRefreshInterval()
                    )
                );

                Document mapping = indexOperations.createMapping();
                indexOperations.create(settings, mapping);
            }
        };
    }
}
~~~

The snippet illustrates the `IndexOperations.create(settings, mapping)` API: the mapping is generated from `ProductDocument`'s annotations, while settings come from the profile-bound configuration. If the index does not exist yet, the application creates the index with both parts.

In real projects, place index creation responsibility in a migration or controlled bootstrap step, especially when running multiple application instances concurrently. If multiple instances simultaneously check `exists()` and then create the index, index creation contention can occur. Runtime applications also do not necessarily need index administration permissions.

Set `createIndex = false` on `@Document` if you do not want Spring Data to auto-create the index from annotations during repository bootstrap:

~~~java
@Document(indexName = "catalog-products", createIndex = false)
public class ProductDocument {
    // Document fields
}
~~~

When using this approach, the migration or bootstrap component must ensure the index has been created before the repository uses it.

## 8. Configuring by Environment with `application.yml`

### 8.1. Default Configuration

`src/main/resources/application.yml` can contain shared configuration:

~~~yaml
spring:
  application:
    name: catalog-service

app:
  elasticsearch:
    index:
      shards: 1
      replicas: 0
      refresh-interval: 1s
~~~

### 8.2. Single-Node Local

`application-local.yml`:

~~~yaml
spring:
  elasticsearch:
    uris: http://localhost:9200

app:
  elasticsearch:
    index:
      shards: 1
      replicas: 0
      refresh-interval: 1s
~~~

One primary shard is usually sufficient for small local datasets. Setting replicas to 0 avoids a `yellow` status caused by having no second node. A one-second refresh makes search results observable almost immediately after writes during development.

### 8.3. Development

`application-dev.yml`:

~~~yaml
spring:
  elasticsearch:
    uris: ${ELASTICSEARCH_URIS}
    username: ${ELASTICSEARCH_USERNAME}
    password: ${ELASTICSEARCH_PASSWORD}

app:
  elasticsearch:
    index:
      shards: 1
      replicas: 0
      refresh-interval: 2s
~~~

Dev values depend on the number of data nodes and goals of the shared cluster. If dev has multiple nodes and needs to test replica allocation, replicas can be set to one. If saving resources is the priority, keep replicas at zero.

### 8.4. Staging

`application-staging.yml`:

~~~yaml
spring:
  elasticsearch:
    uris: ${ELASTICSEARCH_URIS}
    username: ${ELASTICSEARCH_USERNAME}
    password: ${ELASTICSEARCH_PASSWORD}

app:
  elasticsearch:
    index:
      shards: 3
      replicas: 1
      refresh-interval: 1s
~~~

Staging should simulate production topology when testing shard distribution, recovery, and query load. The numbers in the example only illustrate how configuration overrides work; replace them with the system's sizing results.

### 8.5. Production

`application-prod.yml`:

~~~yaml
spring:
  elasticsearch:
    uris: ${ELASTICSEARCH_URIS}
    username: ${ELASTICSEARCH_USERNAME}
    password: ${ELASTICSEARCH_PASSWORD}

app:
  elasticsearch:
    index:
      shards: 3
      replicas: 1
      refresh-interval: 1s
~~~

In production, shard count must be based on capacity and benchmarks. Replicas must match the number of data nodes, failure domains, and availability objectives. The refresh interval must be based on search freshness requirements and indexing throughput. Do not copy illustrative numbers verbatim without evaluating the workload.

Activate a profile via environment variable or command-line argument:

~~~bash
SPRING_PROFILES_ACTIVE=local
~~~

~~~bash
java -jar catalog-service.jar --spring.profiles.active=prod
~~~

Endpoint and credential variables must be supplied by the deployment environment or secret manager. Do not store real passwords in `application-{profile}.yml` files committed to the repository.

### 8.6. Does Changing the Profile Update an Existing Index?

This is a critical point during deployment. Profiles only determine the values Spring binds into the application. Switching from local to production or changing replicas from 0 to 1 does not automatically update settings of an existing index.

There are three scenarios:

1. **Index does not exist yet:** the index creation step can use settings from the active profile.
2. **Index already exists, dynamic setting changed:** you must call the Update Index Settings API or corresponding admin workflow to update replicas and refresh interval.
3. **Index already exists, primary shard count changed:** you must create a new index with the new shard count and transfer data via reindex or an appropriate split/shrink operation.

Therefore, do not rely solely on restarting the application with a new profile to conclude the index has received the new settings. Always read the actual settings from Elasticsearch.

## 9. Using Index Templates to Standardize Settings

Index templates allow applying settings and mappings to new indexes whose names match a pattern. This is a suitable approach when the operations team wants to manage shard counts, replicas, and refresh intervals on the Elasticsearch side instead of letting each application create indexes independently.

Example creating a composable index template:

~~~http
PUT /_index_template/catalog-prod-template
{
  "index_patterns": ["catalog-products-prod-*"],
  "priority": 200,
  "template": {
    "settings": {
      "number_of_shards": 3,
      "number_of_replicas": 1,
      "refresh_interval": "1s"
    }
  }
}
~~~

When creating an index named `catalog-products-prod-v1`, a matching template can provide default settings. Separate templates can be created for local, dev, staging, and production using corresponding patterns, or shared component templates can be combined with environment-specific index templates.

For example, if the application uses `@Setting(useServerConfiguration = true)`, Spring Data does not send settings from the entity. In that case, an index template can serve as a unified source of settings management. Ensure the actual index name matches the pattern and the template has an appropriate priority if multiple templates match.

Index templates apply only when creating new indexes. Modifying a template does not automatically update settings of previously created indexes. Existing indexes must be updated separately if the setting supports dynamic changes.

## 10. Monitoring and Verifying Actual Settings

Do not check only `application.yml` or annotations. Read the settings that Elasticsearch is actually using.

### 10.1. Viewing Index Settings

~~~http
GET /catalog-products/_settings?include_defaults=true
~~~

This request returns current settings and can include default values. When comparing across environments, distinguish explicitly declared settings from Elasticsearch defaults.

### 10.2. Viewing Shard Counts and Sizes

~~~http
GET /_cat/shards/catalog-products?v=true&h=index,shard,prirep,state,store,node
~~~

The output helps inspect primary (`p`) and replica (`r`) shards, allocation state, shard sizes, and the node holding each shard.

You can view an index overview:

~~~http
GET /_cat/indices/catalog-products?v=true
~~~

### 10.3. Monitoring Cluster Health

~~~http
GET /_cluster/health/catalog-products
~~~

Monitor the metrics:

- `active_primary_shards`: number of active primary shards.
- `active_shards`: total number of active shard copies.
- `unassigned_shards`: number of unallocated shards.
- `relocating_shards`: number of shards currently being moved.
- `initializing_shards`: number of shards currently initializing.
- `status`: `green`, `yellow`, or `red`.

### 10.4. Testing the Impact of Refresh Interval

Measure both write speed and search visibility latency. A test can:

1. Write a representative batch of documents.
2. Record the timestamp when the request is acknowledged.
3. Execute queries until the documents appear.
4. Measure wait time and indexing throughput.
5. Repeat with several different refresh intervals.

Results must reflect the real workload: document size, mapping, shard count, replicas, concurrent request rate, and node resources. Do not rely on a single test on a development machine.

## 11. Common Configuration Mistakes

**Setting too many primary shards for a small index.** Many small shards increase overhead and search fan-out. Estimate data, measure shard sizes, and benchmark before selecting the count.

**Setting too few shards for a rapidly growing index.** An oversized shard can lengthen recovery and limit data distribution capacity. Monitor growth rate and prepare a rollover or reindex strategy.

**Keeping replicas at one in a cluster with only one data node.** A replica cannot be placed on the same node as its primary, leading to a `yellow` status. Use zero replicas in single-node environments if having no in-cluster copies is acceptable.

**Setting replicas to zero in production without a fault-tolerance plan.** When losing a primary or experiencing shard corruption, there is no replica to take over. Evaluate SLAs, node topology, and snapshots before deciding.

**Assuming increasing replicas increases primary capacity.** Replicas are copies of shards; they do not increase the primary data volume an index can hold. They increase total storage usage and can increase read capacity.

**Assuming changing `number_of_shards` via `PUT _settings` takes effect.** This is a static setting. You need to create a new index and migrate data, or use split/shrink operations under suitable conditions.

**Setting the refresh interval too short for heavy write workloads.** Frequent refreshes generate additional segment and merge work. Measure throughput and search latency before choosing.

**Disabling refresh and forgetting to re-enable it.** Documents may continue to be written but fail to appear automatically in search. Manage bulk operations with a procedure that includes restoring the setting and performing a final refresh.

**Calling manual refresh after every write.** This increases overhead and can reduce throughput. If read-after-write is needed, consider `refresh=wait_for`.

**Thinking changing `application-prod.yml` updates old indexes.** Profiles only alter application configuration. Check whether the index already exists and perform settings updates or reindexing depending on the setting type.

**Using the `@Setting` annotation as a migration mechanism.** `@Setting` supplies values when Spring Data creates an index. It does not automatically change existing settings on an already created index.

## 12. Workflow for Selecting and Deploying Settings

When creating a new index for a Spring Data Elasticsearch application, you can follow this sequence:

1. Determine expected data volume, growth rate, document size, and retention period.
2. Identify cluster topology: number of data nodes, failure domains, resources, and availability requirements.
3. Estimate initial primary shard count from primary data volume and target shard size.
4. Choose replica count based on shard distribution capacity and fault-tolerance goals.
5. Determine acceptable search visibility latency to choose the refresh interval.
6. Put the values into profile-based configuration or an index template.
7. Create the index with settings and mapping managed together.
8. Verify settings, mapping, shard allocation, and cluster health after creation.
9. Benchmark with representative data and queries in staging or a production-like environment.
10. Monitor shard size, shard count per node, indexing throughput, search latency, and allocation state.
11. If only replicas or refresh interval need changing, update dynamic settings and verify the result.
12. If primary shard count needs changing, plan creating a new index, reindexing/splitting/shrinking, and switching aliases.

Specific numbers must be validated with data and benchmarks. Local configurations typically prioritize simplicity and low resource usage; staging should simulate production; production must balance storage capacity, availability, throughput, and search result freshness.

## 13. References

- [Elasticsearch - General index settings](https://www.elastic.co/docs/reference/elasticsearch/index-settings/index-modules): classification of static and dynamic settings, replica count, and refresh interval.
- [Elastic - Size your Elasticsearch shards](https://www.elastic.co/docs/deploy-manage/production-guidance/optimize-performance/size-shards): sizing guidance, effects of oversharding, and adjusting shard strategy.
- [Elasticsearch - Update index settings API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-indices-put-settings): updating dynamic index settings.
- [Spring Data Elasticsearch - Index settings](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/misc.html): using `@Setting`, `settingPath`, and `useServerConfiguration`.
- [Spring Data Elasticsearch - IndexOperations API](https://docs.spring.io/spring-data/elasticsearch/docs/current/api/org/springframework/data/elasticsearch/core/IndexOperations.html): creating indexes with settings and mappings.

In actual operations, check the documentation for the exact Elasticsearch and Spring Data Elasticsearch versions your application uses. Defaults and limits across Elastic Stack, Elastic Cloud Serverless, and different versions may vary.
