# When to Use Elasticsearch and When to Choose Another Tool

Elasticsearch fits well when an application needs high-quality, fast content search: understanding keywords, ranking results by relevance, combining multiple filters, offering search-as-you-type suggestions, and scaling search across multiple machines. However, Elasticsearch is not automatically the best choice for every data-reading workload. If the requirement is primarily CRUD, relational queries, transactions requiring strong consistency, or basic search over a small dataset, your existing database is usually a leaner and safer choice.

The decision should depend on query patterns, consistency requirements, scale, operational cost, and the capabilities of your current system. A large number of records alone is not enough to conclude that Elasticsearch is required.

## 1. Understanding the proper role of Elasticsearch

Elasticsearch is a distributed search and analytics engine built on Apache Lucene. It ingests documents, indexes their content, and provides APIs for searching, filtering, sorting, and aggregating data. Search indices are organized to look up terms efficiently, especially for full-text queries.

A relational database typically stores normalized data to enforce constraints and transactions. An Elasticsearch index is usually designed around read patterns: holding the fields needed by search screens and queries, often repeating selected data from multiple tables to avoid joins at query time.

In many business systems, a sound architecture looks like this:

~~~text
Application writes data
        |
        v
Primary database
(authoritative source of truth)
        |
        | events / outbox / CDC / sync process
        v
Elasticsearch
(search index)
        |
        v
Search API and user interface
~~~

Under this model, the primary database remains responsible for business data and transactions. Elasticsearch holds a projection optimized for querying. When source data changes, the index is updated afterward; therefore, a brief lag can exist between writing data and finding the updated data in search.

Elasticsearch can accept document writes, updates, and deletes. That does not mean it should replace a transactional database. Updating documents in an index incurs indexing overhead, visibility of changes depends on refreshes, and its data model does not offer the same foreign keys, relational joins, and multi-record transactions as a relational database.

## 2. Cases where Elasticsearch shines

### 2.1. Full-text search is a core requirement

Consider Elasticsearch when users search by words or phrases across multiple text fields, such as product names, descriptions, brands, category codes, and article bodies. The system needs to analyze text before indexing and querying rather than merely checking exact string matches.

For example, an e-commerce site might need to:

- Search products by name and description.
- Prioritize results with keywords in the name over those in the description.
- Support phrase searches, fuzzy matches, or configured variants.
- Combine keywords with price, brand, stock availability, and category filters.
- Sort by relevance, then by price or update time.

Elasticsearch lets you tune text analysis, per-field weights, and scoring logic to match the desired search experience.

### 2.2. Relevance-based ranking is needed

A good search query usually should not simply return every record containing the entered string. It also needs to decide which results are more relevant.

For example, when a user searches for “travel camera”, a product with both words in its name should generally rank above a product that only mentions them in its description. Relevance scoring can combine:

- How closely keywords match.
- Which fields contain the matching content.
- Term rarity across the document set.
- Configured business weights.
- Additional signals such as popularity or recency.

If the application only performs exact lookups by code or ID, this ranking machinery may offer little meaningful benefit.

### 2.3. Filters and statistics accompany search

Elasticsearch is helpful when results pages must simultaneously filter and display counts per group. For example, a user searches for laptops and then filters by brand, price range, RAM, screen size, and availability; the UI also needs to show how many results remain for each brand or price bracket.

Queries can combine text conditions, exact filters, sorting, and aggregations. This is advantageous when filters vary dynamically by data type and must run against the same result set.

### 2.4. Suggestions, autocomplete, or typo tolerance are needed

Features such as query suggestions, autocomplete, prefix matching, fuzzy matching, synonyms, and language analysis can justify adopting a search engine. They are particularly valuable when search is the primary interaction flow of the product and result quality directly drives content discoverability.

These capabilities must be designed with analyzers, tokenizers, filters, and mappings tailored to the actual language and data. Simply installing Elasticsearch and running default queries does not guarantee strong Vietnamese search results. You must test with Vietnamese diacritics, capitalization, compound words, typos, and synonyms that real users actually type.

### 2.5. A dedicated read model and search scaling are needed

When multiple data sources must be combined into a single searchable document, Elasticsearch can serve as the store for a flattened read model. For instance, a product document can hold the product name, brand name, category name, and display stock status.

This document model avoids multi-way joins during search queries. It fits when the team accepts building a sync pipeline and managing duplicated data. Distributed shards and replicas also help scale storage, read throughput, and availability, though cluster capacity and operations still require proper engineering.

### 2.6. Searching and analyzing operational data

Elasticsearch can also fit querying logs, events, or time-series observability data, especially when full-text search is combined with filters by service, severity, timestamp, and attributes. However, clarify retention requirements, ingest volume, storage costs, and analytics needs. A dedicated columnar analytics store may be more appropriate if the focus is massive analytical queries rather than interactive search.

## 3. Cases where you should choose another tool

### 3.1. The application is primarily CRUD and exact lookups

If screens only load a record by ID, filter on a few columns, sort by date, or paginate lists, your existing database usually handles this well. B-tree indices, composite indices, and well-tuned queries can meet performance goals without adding a search cluster.

Adding Elasticsearch in this case forces the system to maintain two data stores, synchronize writes and deletes, handle sync failures, monitor a cluster, and pay additional infrastructure costs. Without specialized search requirements, that complexity does not deliver enough value.

### 3.2. Transactions and strong consistency are the top priority

Workflows like payments, money transfers, limited-capacity bookings, balance updates, or inventory reservations demand strict constraints and transactions. The transactional database should remain the authoritative source of truth.

If a change must be confirmed immediately and all subsequent reads must observe the new state, do not rely on an asynchronously synced search index for the final decision check. You can use Elasticsearch to find and filter candidates, then read or verify critical state from the primary database.

### 3.3. Queries require complex relationships and joins

If most queries join multiple tables, enforce foreign key constraints, or compute over normalized data, a relational database is usually a more natural fit. Elasticsearch supports relationships in certain ways, but it does not replace SQL's general-purpose join model. Embedding or duplicating data in search documents speeds up reads while making updates and synchronization more complex.

### 3.4. Scale and search requirements remain simple

For small datasets, low user traffic, and basic search, your database's built-in full-text search may suffice. There is no fixed record-count threshold that triggers switching to Elasticsearch. Measure response times, query load, write latency, data size, and query complexity on real infrastructure.

A table with several million rows and well-indexed queries can run reliably in a relational database. Conversely, even a small dataset may warrant a search engine if requirements for relevance, autocomplete, or linguistic analysis are demanding.

### 3.5. The team is not ready to operate another system

Elasticsearch requires monitoring heap usage, CPU, disk, shards, replicas, indexing rate, query latency, cluster health, snapshots, and recovery. You need plans for access control, network security, version upgrades, and incident response.

If the team lacks a compelling search need or operational capacity, start with tools already in the stack or an appropriate managed service. Introduce an Elasticsearch cluster only once product benefits and operational readiness are confirmed.

## 4. Comparing popular alternatives

| Tool | Start here when | Points to consider |
|---|---|---|
| PostgreSQL or existing relational DB | CRUD, exact filters, joins, transactions; moderate full-text search | Requires index and query tuning; linguistic search capabilities have distinct limits |
| PostgreSQL Full Text Search and trigram | App uses PostgreSQL and needs word search, fuzzy matching, or substring matching at moderate scale | Requires configuring tsvector, dictionaries, GIN/GiST, and testing language quality |
| Full-text search in MySQL or current DBMS | Data and app already live in that DBMS with relatively basic search requirements | Analysis, ranking, and customization capabilities depend on the DBMS and version |
| MongoDB Atlas Search | Primary data already lives in MongoDB and you want search integrated in that ecosystem | Depends on the platform's managed service, deployment architecture, and pricing |
| Meilisearch or Typesense | Need a straightforward app search experience, quick setup, autocomplete, and common filters | Evaluate customization, scale, operations, and feature limits of each product |
| Apache Solr | Need a Lucene-based search platform with Solr's configurability and ecosystem | Assess operational expertise and fit with the current architecture |
| OpenSearch | Need a search/analytics engine compatible with many Elasticsearch ecosystem concepts and APIs | Do not assume all versions, plugins, or APIs are 100% compatible; verify compatibility matrices |
| ClickHouse or analytical data stores | Focus is large-scale columnar aggregation and analytics | Not a direct replacement for interactive full-text search |

The tools in this table are options to evaluate, not mechanical prescriptions. Compare them using a representative query suite, realistic data, operational requirements, and total cost of ownership.

## 5. Decision matrix by need

| Primary need | Reasonable starting choice | When to evaluate Elasticsearch |
|---|---|---|
| Read by ID, CRUD, business updates | Primary database | When genuinely complex search features are added |
| Filter by a few columns and paginate | Database indices | When text queries, relevance, and multi-facet filtering become a bottleneck |
| Basic full-text search in a PostgreSQL app | PostgreSQL Full Text Search | When analyzers, ranking, autocomplete, or search scale exceed current capacity |
| Product search with relevance, facets, and suggestions | Elasticsearch or a suitable search service | From the design phase if search is a core feature |
| Transactions needing latest state and strict constraints | Transactional database | Use only as a secondary index to find candidates, never as the transaction authority |
| Very large analytical aggregations | Data warehouse or suitable OLAP store | When interactive search on logs or documents is also needed |
| Simple search, small team, low customization needs | Existing tools or lightweight search service | When measurements prove those options fall short |

You can walk through these questions to decide:

1. Do users genuinely need searching within text content, relevance ranking, autocomplete, or fuzzy search?
2. Can the existing database meet the requirement using indices and built-in full-text search after benchmarking?
3. Is sync lag between primary data and the search index acceptable?
4. Can you build a reliable pipeline for updates, deletes, retries, and reindexing?
5. Can the team secure, monitor, back up, and operate an additional system?

If the answer to specialized search needs is “no”, favor existing tools. If the answer is “yes”, simpler options were benchmarked and fell short, and the team accepts the sync model and operational cost, Elasticsearch is a solid candidate to evaluate.

## 6. Factors to consider when integrating with Spring Data Elasticsearch

Spring Data Elasticsearch helps Java applications map objects, work with indices, and construct queries through familiar abstractions. It does not alter Elasticsearch's distributed, near-real-time, search-oriented nature. Using a repository does not mean you can treat Elasticsearch like another relational database.

### 6.1. Define the authoritative data source

Before creating a repository, identify which system owns the data. In typical business applications, the primary database stores canonical state while Elasticsearch stores documents for search. Write APIs should update the primary database first, then emit events or write to an outbox so a sync process updates the index.

Avoid writing directly to both stores via two independent calls without a recovery mechanism. If the database write succeeds while the Elasticsearch write fails, the two stores drift out of sync. An outbox, CDC, or queue with retries and idempotent processing handles that failure mode much better.

### 6.2. Design documents and mappings around queries

A document should contain the fields that search queries need. Distinguish text fields requiring analysis from fields needing exact matching, filtering, or sorting. For example, a product name may need `text` for searching alongside a separate `keyword` field for sorting or aggregations.

Mappings and analyzers directly shape how data is indexed. Changing a field type or analyzer usually requires creating a new index, reindexing data, and switching an alias to the new index. Treat mappings as versioned data design rather than configuration that can be freely altered after data is loaded.

### 6.3. Design synchronization and error handling

Your sync pipeline needs clear handling for:

- Document creation, updates, and deletions.
- Delayed or out-of-order events.
- Retries when Elasticsearch is temporarily unavailable.
- Duplicate events without corrupting state.
- Documents failing mapping validation or carrying invalid data.
- Reindexing when mappings or analyzers change.

For large datasets, bulk indexing is typically more efficient than sending documents individually. Monitor sync queue depth and lag time to detect when the index falls behind the source data.

### 6.4. Watch pagination and large queries

Deep pagination with large offsets can consume heavy resources because the search engine must evaluate many results before the requested slice. For scrolling large result sets, evaluate `search_after` and strategies for maintaining stable sort order. Also cap page sizes, returned fields, and query scope so a single search request cannot overload the cluster.

### 6.5. Manage versions and operations

Select versions of Spring Boot, Spring Data Elasticsearch, and Elasticsearch using the compatibility matrix for your active release train. Do not pick client or server versions independently merely because they are the newest releases.

In deployment environments, configure authentication, TLS, least-privilege permissions, snapshots, cluster health alerts, disk capacity, heap sizing, shard counts, and query latency tracking. With managed services, some operational tasks shift to the provider, though cost, quotas, and security responsibilities still need evaluation.

## 7. Example: deciding for a product search feature

Suppose an online store has product, brand, category, and inventory tables in PostgreSQL. Initially, the admin portal needs to look up products by ID, filter by status, and sort by last updated date. Those queries should run directly on PostgreSQL with proper indices.

Later, the store builds a customer-facing search page. Users want to enter natural phrases, search across names and descriptions, see live suggestions while typing, tolerate typos, filter by brand and price range, view product counts per filter, and prioritize the best matches. This is where Elasticsearch delivers clear value.

The design could look like this:

- PostgreSQL continues storing authoritative products and inventory state.
- A search document is built from the required fields of products, brands, and categories.
- Product change events flow via an outbox or CDC to a process updating Elasticsearch.
- The search API queries Elasticsearch to retrieve matching IDs and display fields.
- During checkout, the system verifies current price and stock in PostgreSQL before confirming the order.

Here, Elasticsearch handles finding matching products while the primary database handles confirming transactions. If the store had not implemented suggestions, relevance ranking, or complex facets—and PostgreSQL search met target response times—adding Elasticsearch might not yet be necessary.

## 8. Common mistakes

- **Choosing Elasticsearch just because data is large:** scale must be measured alongside query patterns and the indexing capabilities of your existing DBMS.
- **Using Elasticsearch as the sole store for transactional state:** account for business transactions, constraints, and consistency guarantees.
- **Synchronizing via two independent write calls:** a failure between the two calls causes drift; build retry and reconciliation mechanisms.
- **Dumping entire tables into an index without query goals:** design documents around search needs while weighing duplication costs.
- **Skipping analyzer testing with Vietnamese:** search quality depends on tokenization and real-world query datasets.
- **Assuming the repository abstraction guarantees compatibility:** mappings, queries, refreshes, pagination, and server versions still require explicit understanding.
- **Ignoring operational overhead:** a search cluster requires compute resources, monitoring, backups, upgrades, and recovery procedures.

Elasticsearch is worth using when search requirements clearly demand full-text matching, relevance, suggestions, faceted filtering, and scalability, and when the architecture can accommodate index synchronization and operating an extra system. For CRUD, transactions, relational queries, or basic search, start with your existing database and benchmark first. The right tool is the one that satisfies real requirements with manageable overall complexity and cost.
