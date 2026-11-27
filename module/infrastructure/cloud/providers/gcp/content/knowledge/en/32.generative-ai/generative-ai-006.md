# Vertex AI Vector Search and Building Vector Indexes

## 1. Scenario: Finding the Right Docs for a Java Assistant

A **Spring Boot application on Cloud Run** answers questions about company policies. Documents live in **Cloud Storage**, get split into chunks, and each chunk is converted into an **embedding**—a numeric vector representing semantics. When a user asks "How long do I have to request a refund?", the system needs to find the **most semantically similar** passages even if the query wording differs from the source text.

**Vertex AI Vector Search** accelerates **nearest-neighbor** search over large vector sets. It stores a **vector index (`Index`)** and serves queries via an **IndexEndpoint/DeployedIndex**; it does not write answers by itself, does not parse every PDF automatically, and is **not an embedding model**. To build a **Retrieval-Augmented Generation (RAG)** application, developers still need a pipeline to ingest and chunk documents, generate embeddings, enforce access controls, and pass relevant passages into a generative model prompt.

Within the **Generative AI on Google Cloud** chapter of the **CLOUD_PROVIDERS_GCP** module, this lesson connects Vector Search with IAM/VPC, Cloud Storage, Java, Cloud Run/GKE, reliability, performance observability, and cost. Examples are self-contained and use mock data to avoid incurring costs or exposing internal documents.

**After this lesson, you can:**

1. Distinguish **embeddings, vector distance, `Index`, `IndexEndpoint`, and `DeployedIndex`**.
2. Prepare **JSON Lines** data with valid schemas, dimensions, IDs, and token/numeric restricts.
3. Choose between **Tree-AH (ANN)** and **brute force (exact k-NN)**, batch/stream updates, and distance metrics.
4. Create an **Index**, deploy it to an authenticated public endpoint or a VPC endpoint, and call `findNeighbors`.
5. Write Java 21 code calling Vector Search with **ADC**, and build a permission-checked **RAG** retrieval pipeline.
6. Measure **recall@k, p95 latency, freshness, shard/replica costs**, and execute safe migrations and cleanup.

> **Practice scope:** Commands to create an Index/Endpoint/DeployedIndex are provided **to run in an authorized lab project and were not executed during authoring**. Even with only a few vectors, a **deployed index provisions nodes/replicas that incur charges when idle**; index builds/updates, Cloud Storage, and embedding models can also incur charges. Never modify or delete production indexes.

## 2. A Complete RAG Retrieval Flow

```mermaid
flowchart LR
    Docs["GCS / CMS Documents"] --> Chunk["Parse + chunk + metadata"]
    Chunk --> Embed["Embedding model\nsame model/version"]
    Embed --> GCS["GCS JSONL\nid + embedding + restricts"]
    GCS --> Index["Vector Search Index"]
    Index --> Deploy["DeployedIndex\non IndexEndpoint"]
    Ask["User question"] --> QEmb["Query embedding"]
    QEmb --> Deploy
    Deploy --> IDs["Top-k IDs + distance"]
    IDs --> Fetch["Lookup content + ACL\nCloud SQL/Firestore/GCS"]
    Fetch --> LLM["LLM + citations\nauthorized context only"]
    LLM --> Answer["Answer + sources + fallback"]
```

These are **two separate paths**: *ingestion/indexing* can run on a schedule; *retrieval* must meet application latency SLOs. Vector Search primarily returns **IDs and distance values**, without automatically returning source text, titles, or citations. Maintain a **`chunkId → source URI, revision, ACL, text`** mapping in a data store with appropriate access controls.

| Component | Responsibility | What not to expect |
| --- | --- | --- |
| **Embedding model** | Turns text/images into vectors in a shared semantic space | Vector Search generating embeddings from arbitrary strings |
| **Index** | Stores vector data and neighbor-search configuration | An empty index returning documents by itself |
| **IndexEndpoint** | Connection endpoint serving queries | Creating an endpoint meaning data is already searchable |
| **DeployedIndex** | Attaches an Index to an endpoint, provisioning nodes/replicas | Zero cost while idle |
| **Metadata/document store** | Stores text, provenance, tenant, permissions | Vector results replacing access control |
| **Java RAG service** | Authn/authz, embed query, retrieve, rerank, call LLM | An ANN score guaranteeing a truthful answer |

> **Product naming:** Newer documentation may place Vector Search under **Gemini Enterprise Agent Platform**; many SDKs/CLIs still use `aiplatform.googleapis.com`, `gcloud ai indexes`, and the legacy `MatchingEngineIndex` resource class. **Agent Retrieval (formerly Vector Search 2.0)** has a separate **collections/dataObjects** API (e.g., `vectorsearch.googleapis.com`)—**do not mix** it with the `Index/IndexEndpoint` model covered here.

## 3. Embeddings, Dimensions, and Metrics: What Must Match

An embedding is a real-valued vector `v = [v₁, …, v_d]`, where **`d` is the fixed dimension of the model/version**. The same sentence can encode differently if you change models, task types, or normalization rules. Creating a 768-dimension Index and sending a 3-dimensional query will be rejected or invalid; **never arbitrarily truncate or zero-pad vectors**.

### 3.1. Distance, Similarity, and Normalization

| Metric | Interpretation | When appropriate |
| --- | --- | --- |
| `DOT_PRODUCT_DISTANCE` | **Distance = negative dot product**; **smaller** values mean larger dot products | Optimized on Vector Search; commonly paired with normalized embeddings |
| `COSINE_DISTANCE` | Angular distance between vectors | Semantic retrieval when vector magnitude is not a signal |
| `SQUARED_L2_DISTANCE` | Squared Euclidean distance | When vector magnitude also carries meaning |
| `L1_DISTANCE` | Sum of absolute per-dimension differences | Certain continuous data types |

Google Cloud recommends **`DOT_PRODUCT_DISTANCE` paired with `UNIT_L2_NORM`** when you want cosine-equivalent ranking; this combination is well-optimized across many Vector Search setups. For **unit-length normalized vectors**, dot product equals cosine similarity, yet the API returns **distance (smaller is closer)**—do not mistake a negative number for "90% confidence."

```text
Mock 3D vectors (not generated by a language model):
  A = [1, 0, 0]
  B = [0.8, 0.6, 0]
  C = [0, 1, 0]
  q = [1, 0, 0]

q·A = 1.0; q·B = 0.8; q·C = 0.
distance=-dot: A=-1.0, B=-0.8, C=0.
=> A is closer than B, B is closer than C.
```

**In real RAG systems**, use one embedding model + version + preprocessing pipeline for both **chunks and queries**; if the model offers **task-specific input types** (document vs. query), use both modes from that same model family. When upgrading to a model that changes the vector space, **create a new index and deploy side-by-side/canary**—never mix vectors from two models in one index just because their dimensions match.

## 4. Designing Documents, Chunks, IDs, and Metadata

A chunk should hold enough context to answer questions without blending unrelated topics. Example:

```text
documentId: policy-refund-2026
revision:   v3
chunkId:    policy-refund-2026#v3#0007
sourceUri:  gs://DOC_BUCKET/policies/refund-v3.pdf
text:       "Refund requests within 14 days..."
tenant:     t01
lang:       vi
access:     employee
```

**Key design points:**

- **Stable, unique IDs in the index** for each chunk version. Retrying with the same ID simply overwrites the corresponding datapoint in a streaming index, whereas generating random IDs on retry causes duplicates.
- **Revision** distinguishes old from current results. Delete old versions from both the index and metadata store when a document is revoked.
- **Token restricts** like `tenant`, `lang`, and `access` handle exact filtering. **Numeric restricts** like `year` and `price` handle range comparisons; never encode them into the feature vector.
- **Crowding tags** like `documentId` prevent top-k from being filled solely by chunks from one document when per-crowding limits are supported at query time.
- Never put raw **emails, tokens, national IDs, or sensitive text** inside vector IDs, namespaces, or logs. **Metadata and vectors can still carry sensitive information**, requiring access controls and deletion policies.
- **Token/numeric filters do not replace authorization**. The backend must authenticate the tenant/user, construct server-controlled restricts, and **verify per-document permissions during fetch/rerank before sending text to an LLM**.

Store the `chunkId → text/ACL` mapping in Cloud Storage, Firestore, or Cloud SQL depending on workload. The index may not store or return full metadata; if using `embedding_metadata` where supported, it has **size limits** and does not replace a document management store.

## 5. Choosing the Index Algorithm and Update Method

| Choice | Strengths | Trade-offs |
| --- | --- | --- |
| **Tree-AH (ANN)** | Fast approximate search on large vector sets, tunable recall/latency | Does not guarantee exact top-k; requires measuring recall |
| **Brute-force (exact k-NN)** | Exact nearest neighbors for datasets or benchmarks | Cost and latency scale with dataset size; often used as ground truth |
| **Batch update** | Loads from a **GCS directory**; suits periodic updates | Index sync/compaction introduces lag; updates are not instant |
| **Stream update** | `upsertDatapoints`/`removeDatapoints` for near-real-time updates | Update/compaction costs, quotas, retries, and freshness management |

Key parameters for a **Tree-AH Index**:

| Parameter | Meaning | How to test |
| --- | --- | --- |
| `dimensions` | Dense vector length matching the model | Validate **every** record before index creation |
| `distanceMeasureType` and `featureNormType` | Distance metric and normalization | Measure retrieval quality per model |
| `approximateNeighborsCount` | Initial neighbors retrieved before exact reordering | Test recall/latency across k values |
| `leafNodeEmbeddingCount` | Target embeddings per leaf node | Larger leaves mean fewer routes, potentially lower recall |
| `fractionLeafNodesToSearch` | Fraction of leaf nodes searched | Increasing it usually boosts recall at higher latency |
| `shardSize` | Small/medium/large shard affects node count and machine types | Evaluate RAM, shard count, availability, and cost |

Shards can be **SMALL (~2 GiB), MEDIUM (~20 GiB), or LARGE (~50 GiB)** per supported config; eligible machine types depend on shard size. **Do not pick large shards just to "save money"** if doing so hurts distribution or availability. Without an existing benchmark, use **brute force as ground truth** and tune Tree-AH using `recall@k` and `p95`.

**You cannot convert an existing batch-update index to streaming with a simple flag**; normally you must create a new Index with `--index-update-method=stream-update`, reload data, and shift traffic safely. In batch updates, `isCompleteOverwrite=true` **replaces the entire dataset**; never enable it accidentally when intending only to add a few datapoints.

## 6. Safe Preflight: Project, Region, Bucket, IAM

**Read-only** commands in Cloud Shell/Bash:

```bash
gcloud config set project LAB_PROJECT_ID
gcloud ai indexes list \
  --project=LAB_PROJECT_ID --region=us-central1
gcloud ai index-endpoints list \
  --project=LAB_PROJECT_ID --region=us-central1
gcloud storage buckets describe gs://UNIQUE_LAB_BUCKET
```

Before creating resources:

1. Confirm **Billing, Vertex AI API `aiplatform.googleapis.com`, and eligible regions** for the Index, Endpoint, embeddings, and bucket.
2. Verify the operator's **permissions to create Indexes/Endpoints and deploy** (e.g., `roles/aiplatform.user` or a custom role with the required permissions). The service needs **GCS object read access** on the data project/bucket.
3. For a public endpoint, callers still need **Vertex AI predict/index query IAM permissions**; public endpoint **means internet-reachable**, **not unauthenticated**.
4. If a **private endpoint** is required, prepare VPC/private endpoint connectivity (VPC peering or supported mechanism), DNS, firewalls, identity, and access from Cloud Run/GKE.
5. Set **budgets, node/replica caps, data classification**, and a cleanup owner. Estimate costs including **idle deployment hours**.

Run mutating commands only after approval under **LAB_PROJECT_ID**. Never enable a public endpoint for sensitive data just because private networking takes more setup.

## 7. Lab: Preparing JSONL with 3D Vectors and Filters

Use only **four synthetic records**—no real embedding generation needed. Create `vectors.json` (UTF-8 **JSON Lines**, *not* a JSON array):

```jsonl
{"id":"doc-a","embedding":[1,0,0],"restricts":[{"namespace":"tenant","allow":["lab"]},{"namespace":"lang","allow":["vi"]}],"numeric_restricts":[{"namespace":"year","value_int":2026}],"crowding_tag":"guide-1"}
{"id":"doc-b","embedding":[0.8,0.6,0],"restricts":[{"namespace":"tenant","allow":["lab"]},{"namespace":"lang","allow":["vi"]}],"numeric_restricts":[{"namespace":"year","value_int":2026}],"crowding_tag":"guide-1"}
{"id":"doc-c","embedding":[0,1,0],"restricts":[{"namespace":"tenant","allow":["lab"]},{"namespace":"lang","allow":["en"]}],"numeric_restricts":[{"namespace":"year","value_int":2025}],"crowding_tag":"guide-2"}
{"id":"doc-d","embedding":[0,0,1],"restricts":[{"namespace":"tenant","allow":["lab"]},{"namespace":"lang","allow":["vi"]}],"numeric_restricts":[{"namespace":"year","value_int":2024}],"crowding_tag":"guide-3"}
```

**v1 `Index` format rules:**

- Each line is **one JSON object** with an `id` and at least one dense `embedding` or `sparse_embedding`.
- `embedding` must contain exactly **3 finite numbers** in this lab (matching the model dimension in production)—no `NaN`/`Infinity`, numeric strings, or missing dimensions.
- `restricts[].allow` and `deny` are token arrays; in REST **queries**, use `allowList`/`denyList` per `IndexDatapoint.Restriction`, **not the ingestion key names**.
- During **ingestion**, `numeric_restricts` only stores `value_int/value_float/value_double`; **`op` is used only at query time**, not in JSONL input.
- Place GCS data files **directly inside a prefix** with `.json`, `.csv`, or `.avro` extensions; up to **5,000 files in the batch root** per documentation. `vectors.json` is JSONL despite the `.json` suffix.

Upload example **only to a real lab bucket**:

```bash
gcloud storage cp vectors.json \
  gs://UNIQUE_LAB_BUCKET/vector-search/batch-001/vectors.json
gcloud storage ls \
  gs://UNIQUE_LAB_BUCKET/vector-search/batch-001/
```

**Never mix metadata files or index config JSON into the same batch prefix**; keep only embedding data files there. With a few vectors, brute-force/streaming helps learn the schema, though tiny sizes **do not reflect latency or cost** at millions of vectors.

## 8. Creating an Index from Data in GCS

### 8.1. Brute-Force Config Suited to a Small Lab

Create `index_metadata.json` **locally**; do not upload it into the vectors prefix:

```json
{
  "contentsDeltaUri": "gs://UNIQUE_LAB_BUCKET/vector-search/batch-001/",
  "config": {
    "dimensions": 3,
    "distanceMeasureType": "DOT_PRODUCT_DISTANCE",
    "featureNormType": "UNIT_L2_NORM",
    "shardSize": "SHARD_SIZE_SMALL",
    "algorithmConfig": {
      "bruteForceConfig": {}
    }
  }
}
```

**Brute force** finds exact nearest neighbors over indexed vectors, making it ideal as a **baseline** for comparing ANN. It can be uneconomical at scale. With `UNIT_L2_NORM`, vectors must not be the **zero vector**, which cannot be normalized. Our mock dataset has four nonzero, unit-length vectors.

### 8.2. Creating a Batch-Update Index

Run only when the lab project/bucket is approved and quotas are verified:

```bash
gcloud services enable aiplatform.googleapis.com \
  --project=LAB_PROJECT_ID

gcloud ai indexes create \
  --display-name=vs-docs-lab-exact \
  --metadata-file=index_metadata.json \
  --index-update-method=batch-update \
  --project=LAB_PROJECT_ID \
  --region=us-central1

# Check actual operation/ID and wait until the index is READY:
gcloud ai indexes list \
  --project=LAB_PROJECT_ID --region=us-central1

gcloud ai indexes describe INDEX_ID \
  --project=LAB_PROJECT_ID --region=us-central1
```

**Index creation is asynchronous**; the response may return an operation rather than a ready Index. Even with a few vectors, building takes time and can incur charges. **Do not deploy while the index is still building**, and do not repeatedly re-run `create` just because results do not appear immediately.

If your lab's machine/bucket/region does not support a given config or hits minimum build thresholds, use the **official quickstart dataset** in an authorized project; never "fix" errors by ingesting real customer data.

### 8.3. Tree-AH for Large-Scale ANN Evaluation

Once you have a **sufficiently large** dataset and an exact baseline, you can create **another Index** using a sample config:

```json
{
  "contentsDeltaUri": "gs://UNIQUE_LAB_BUCKET/vector-search/production-like/",
  "config": {
    "dimensions": 768,
    "approximateNeighborsCount": 100,
    "distanceMeasureType": "DOT_PRODUCT_DISTANCE",
    "featureNormType": "UNIT_L2_NORM",
    "shardSize": "SHARD_SIZE_MEDIUM",
    "algorithmConfig": {
      "treeAhConfig": {
        "leafNodeEmbeddingCount": 1000,
        "fractionLeafNodesToSearch": 0.05
      }
    }
  }
}
```

**This is a reference config—do not apply it directly to the four 3D vectors in Section 7.** `dimensions=768` is valid only when both corpus and query embeddings have 768 dimensions from the same model/version. `leafNodeEmbeddingCount` and `fractionLeafNodesToSearch` require **recall@k/latency benchmarking**; sample numbers are not universally optimal.

## 9. Creating an IndexEndpoint and Deploying a DeployedIndex

### 9.1. Choosing Public vs. Private

| Endpoint type | When appropriate | Required protection |
| --- | --- | --- |
| **Public endpoint** | Labs or apps calling over authenticated HTTPS | OAuth/IAM, never expose credentials, application rate limiting |
| **VPC/private endpoint** | Sensitive data, internal-network-only systems | Configure VPC/Private Service Connect per supported method, subnets/routing/DNS/IAM |

**Public endpoint does not mean public data**: requests still require authentication and permissions, though traffic traverses a public endpoint plane. VPC endpoints require proper network setup and cannot be called from a laptop like a public URL. Choose based on **data classification and deployment topology**, not demo convenience.

### 9.2. Creating a Public Endpoint in the Lab Project

```bash
gcloud ai index-endpoints create \
  --display-name=vs-docs-lab-public \
  --public-endpoint-enabled \
  --project=LAB_PROJECT_ID \
  --region=us-central1

gcloud ai index-endpoints list \
  --project=LAB_PROJECT_ID --region=us-central1
```

Save `INDEX_ENDPOINT_ID` and `INDEX_ID` from the **actual output**; they are distinct resources. An IndexEndpoint **without a DeployedIndex** cannot serve nearest-neighbor queries yet.

### 9.3. Deploying a Ready Index

```bash
# LAB ONLY and only after INDEX_ID is READY:
gcloud ai index-endpoints deploy-index INDEX_ENDPOINT_ID \
  --deployed-index-id=lab_docs_v1 \
  --display-name=lab-docs-v1 \
  --index=INDEX_ID \
  --min-replica-count=1 \
  --max-replica-count=1 \
  --project=LAB_PROJECT_ID \
  --region=us-central1

gcloud ai index-endpoints describe INDEX_ENDPOINT_ID \
  --project=LAB_PROJECT_ID \
  --region=us-central1 \
  --format=json
```

`lab_docs_v1` is **your chosen DeployedIndex ID** used in queries, **not the Index resource ID**. Setting `min=max=1` keeps baseline lab node costs low but **provides no production high availability**. Google recommends **at least two replicas per shard** when availability is needed; for real workloads, size shards, machines, and replicas to SLOs and quotas.

Deployment can take several minutes, especially the first time; do not assume the returned operation means the endpoint is already serving. In the `describe` output, inspect **`deployedIndexes[].id`, `index`, `indexSyncTime`**, and **`publicEndpointDomainName`**. Only call the public URL actually returned by the service.

## 10. Querying `findNeighbors` and Reading Results

### 10.1. Sending a Dense Vector Query with Tenant/Language Filters

Queries go to the **deployed public endpoint**, not `aiplatform.googleapis.com`. Create `query.json` in the lab project:

```json
{
  "deployedIndexId": "lab_docs_v1",
  "queries": [
    {
      "datapoint": {
        "datapointId": "query-lab-001",
        "featureVector": [1, 0, 0],
        "restricts": [
          {"namespace": "tenant", "allowList": ["lab"]},
          {"namespace": "lang", "allowList": ["vi"]}
        ]
      },
      "neighborCount": 3
    }
  ],
  "returnFullDatapoint": false
}
```

```bash
# Replace PUBLIC_ENDPOINT_DOMAIN with the actual publicEndpointDomainName.
# Replace PROJECT_NUMBER/INDEX_ENDPOINT_ID with the created resources.
curl --fail-with-body -X POST \
  -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  -H "Content-Type: application/json" \
  --data @query.json \
  "https://PUBLIC_ENDPOINT_DOMAIN/v1/projects/PROJECT_NUMBER/locations/us-central1/indexEndpoints/INDEX_ENDPOINT_ID:findNeighbors"
```

**Semantic expectation:** `doc-a` should appear among the closest results for `q=[1,0,0]` once data is indexed/synced. `doc-c` is excluded by `lang=vi` even though it might be close to another query. **ANN does not guarantee exact ordering in every case**, and `neighborCount=3` is an upper bound rather than a promise that three records always survive filtering.

**Results** return neighbors with `datapoint.datapointId` and `distance` (plus extra data when requested). **Distance is not a relevance probability**: measure retrieval accuracy using a labeled Q&A evaluation set. With `DOT_PRODUCT_DISTANCE`, smaller values are closer; do not treat negative numbers as errors.

### 10.2. Numeric Filters and Crowding

To restrict year ≥ 2025, add to `datapoint` **in the query**:

```json
"numericRestricts": [
  {"namespace": "year", "valueInt": "2025", "op": "GREATER_EQUAL"}
]
```

This is a **JSON fragment** placed alongside `restricts` in `query.json`; **never** add `op` to the ingestion file `vectors.json`. `valueInt` uses a string representation for 64-bit integers per the JSON/protobuf API convention. When searching long documents, **crowding** can limit how many chunks come from the same `crowding_tag`; it is a **result diversification** technique, not a replacement for rerankers or ACLs.

### 10.3. Why "Finding a Vector" Is Not Yet RAG

`findNeighbors` returns **chunk IDs**, after which Java must:

1. Read metadata and content for those IDs from an authorized data store.
2. **Check per-chunk ACLs at query time**, not rely solely on the `tenant` filter in the request.
3. Drop revoked items, stale revisions, and overly short or irrelevant chunks.
4. Rerank/cap tokens and assemble the prompt with **source ID citations**.
5. Reply **"insufficient information"** if context does not support an answer instead of letting the model hallucinate.

**Never let end users pass `tenant`/`allowList` directly in JSON sent straight to Vector Search**. The server must derive permissions from identity/session and cross-check the document store; filters are a retrieval aid, **not an authorization boundary**.

## 11. Java 21: Calling Vector Search from Cloud Run/GKE

To keep the example independent of higher-level SDKs, the Java program uses **`java.net.http.HttpClient`** (JDK 21) and the **Google Auth Library** to obtain tokens from **Application Default Credentials**. This class only queries an existing lab index; it **does not generate embeddings**. In production, a separate step calls the embedding model and verifies dimensions.

### 11.1. Maven Dependency

```xml
<!-- Fragment for the Java 21 lab project pom.xml. -->
<dependency>
  <groupId>com.google.auth</groupId>
  <artifactId>google-auth-library-oauth2-http</artifactId>
  <version>1.38.1</version>
</dependency>
```

Pin versions to match your Java/Google Cloud BOM and scan dependencies. The example uses the built-in JDK HTTP client and needs no second JSON library because the JSON body is fixed with **mock data**. Production should use a proper JSON serializer and an official client with explicit timeouts and retries.

### 11.2. `VectorSearchQuery.java`

```java
package dev.example.vectorsearch;

import com.google.auth.oauth2.GoogleCredentials;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.List;
import java.util.regex.Pattern;

public final class VectorSearchQuery {
    private static final HttpClient HTTP = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(10))
        .build();

    public static void main(String[] args) throws Exception {
        if (args.length != 4) {
            throw new IllegalArgumentException(
                "Usage: PROJECT_NUMBER REGION INDEX_ENDPOINT_ID PUBLIC_ENDPOINT_DOMAIN");
        }
        String projectNumber = args[0];
        String region = args[1];
        String endpointId = args[2];
        String publicDomain = args[3];
        if (!projectNumber.matches("[0-9]+")
                || !endpointId.matches("[0-9]+")
                || !region.matches("[a-z0-9-]+")
                || !Pattern.matches(
                    "[a-zA-Z0-9.-]+\\.vdb\\.vertexai\\.goog",
                    publicDomain)) {
            throw new IllegalArgumentException("Invalid index endpoint resource");
        }

        GoogleCredentials credentials = GoogleCredentials
            .getApplicationDefault()
            .createScoped(List.of(
                "https://www.googleapis.com/auth/cloud-platform"));
        credentials.refreshIfExpired();

        // Query and tenant filter are server-controlled mock data.
        String json = """
            {"deployedIndexId":"lab_docs_v1","queries":[{
              "datapoint":{
                "datapointId":"query-java-001",
                "featureVector":[1,0,0],
                "restricts":[
                  {"namespace":"tenant","allowList":["lab"]},
                  {"namespace":"lang","allowList":["vi"]}
                ]
              },"neighborCount":3
            }]}
            """;
        String url = "https://" + publicDomain
            + "/v1/projects/" + projectNumber
            + "/locations/" + region
            + "/indexEndpoints/" + endpointId + ":findNeighbors";
        HttpRequest request = HttpRequest.newBuilder(URI.create(url))
            .timeout(Duration.ofSeconds(20))
            .header("Authorization",
                "Bearer " + credentials.getAccessToken().getTokenValue())
            .header("Content-Type", "application/json")
            .POST(HttpRequest.BodyPublishers.ofString(json))
            .build();

        HttpResponse<String> response = HTTP.send(
            request, HttpResponse.BodyHandlers.ofString());
        if (response.statusCode() / 100 != 2) {
            throw new IllegalStateException(
                "Vector Search HTTP " + response.statusCode());
        }
        // Print response only in a lab with no private data.
        System.out.println(response.body());
    }
}
```

**How to run:** build the Maven class in a test Java project; run `gcloud auth application-default login` locally, or use the **Cloud Run runtime service account / Workload Identity Federation for GKE** when deployed. Obtain parameters from **`gcloud ai index-endpoints describe`** with `lab_docs_v1` deployed on the lab index.

**Missing from the demo:** JSON parsing, embedding real user questions with the model, 429/503 retries with exponential backoff, circuit breakers, JWT-based tenant extraction, and document fetching. In Spring Boot, add all of those and **never log raw queries, access tokens, or sensitive document text**. Never resolve permission errors by granting `Owner` to the caller.

## 12. Safe Index Updates and Version Migrations

### 12.1. Batch Update: Updating by GCS Prefix

Suppose a day later `batch-002/` contains new or modified datapoints. **This operation applies only to Indexes created with `batch-update`**. In the existing metadata file, point `contentsDeltaUri` to the new prefix; to **incrementally merge updates**, leave overwrite disabled. To **replace the entire corpus**, set `isCompleteOverwrite=true`, bearing in mind this destroys index entries absent from the new batch.

```json
{
  "contentsDeltaUri": "gs://UNIQUE_LAB_BUCKET/vector-search/batch-002/",
  "isCompleteOverwrite": false,
  "config": {
    "dimensions": 3,
    "distanceMeasureType": "DOT_PRODUCT_DISTANCE",
    "featureNormType": "UNIT_L2_NORM",
    "shardSize": "SHARD_SIZE_SMALL",
    "algorithmConfig": {"bruteForceConfig": {}}
  }
}
```

Save this as `index_update_metadata.json` for **an existing lab Index**:

```bash
# LAB ONLY, once batch-002 contains valid data:
gcloud ai indexes update INDEX_ID \
  --metadata-file=index_update_metadata.json \
  --project=LAB_PROJECT_ID \
  --region=us-central1

gcloud ai indexes describe INDEX_ID \
  --project=LAB_PROJECT_ID --region=us-central1
gcloud ai index-endpoints describe INDEX_ENDPOINT_ID \
  --project=LAB_PROJECT_ID --region=us-central1
```

**Do not apply this example without confirming partial vs. overwrite semantics for your real corpus**. Index updates run asynchronously; deployed endpoints may **not yet reflect** new data. Compare **`Index.updateTime` with `DeployedIndex.indexSyncTime`** and completed operations before announcing fresh data is live. Batch index deletes/updates may also **remain invisible or occupy temporary storage** until compaction finishes.

### 12.2. Streaming Index: Upserting and Removing Datapoints

Create a **new Index** with `--index-update-method=stream-update` and compatible metadata; you can create an **empty** streaming index without `contentsDeltaUri` and populate it via the API. Do not run streaming commands against the `batch-update` Index created in Section 8.

Example **only when a streaming lab Index already exists**:

```json
{
  "datapoints": [
    {
      "datapointId": "doc-e",
      "featureVector": [0.6, 0.8, 0],
      "restricts": [
        {"namespace": "tenant", "allowList": ["lab"]},
        {"namespace": "lang", "allowList": ["vi"]}
      ]
    }
  ]
}
```

Save as `upsert.json`, then call:

```bash
# WRITE ACTION — LAB streaming index ONLY:
curl --fail-with-body -X POST \
  -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  -H "Content-Type: application/json" \
  --data @upsert.json \
  "https://us-central1-aiplatform.googleapis.com/v1/projects/LAB_PROJECT_ID/locations/us-central1/indexes/STREAM_INDEX_ID:upsertDatapoints"

# REMOVE lab index data by ID when a document is revoked:
# gcloud ai indexes remove-datapoints STREAM_INDEX_ID \
#   --datapoint-ids=doc-e --project=LAB_PROJECT_ID --region=us-central1
```

**Upserting** an existing `datapointId` updates the prior datapoint; when the source system deletes a document, **remove both the index entry and metadata/document content** per policy. Restricts-only updates use `updateMask="all_restricts"` and only supported fields. Streaming updates carry separate charges/quotas and still require **compaction**; "near real-time" does not mean every new query immediately sees the write the instant the API returns 200.

### 12.3. Migrating from an Old Embedding Model to a New One

When changing embedding model, dimension, metric, or algorithm:

1. Freeze a **corpus snapshot** and record **model/version/preprocessing** metadata.
2. Generate new embeddings into a **new prefix and new Index**; never mix two vector spaces.
3. Build and deploy `v2` in parallel (temporary cost increase) and run **golden retrieval queries**.
4. Shift traffic in the **Spring Boot layer** via canary (or controlled routing), measuring recall, latency, failures, and ACLs.
5. Roll callers back to `v1` if quality drops; only after meeting SLOs and retention requirements, **undeploy** `v1` and delete the old Index if approved.

One `IndexEndpoint` can host multiple DeployedIndexes, yet **`findNeighbors` must specify `deployedIndexId` explicitly**. Do not mistake this for automatic traffic splitting like a custom prediction Endpoint; application routing/canary logic must be explicitly built.

## 13. Evaluating Retrieval: Recall, Latency, and Relevance

To tune ANN parameters, build a **query set with ground truth**:

| Metric | Calculation/meaning | Note |
| --- | --- | --- |
| **Recall@k** | Relevant IDs returned by ANN / relevant IDs in ground-truth top-k | For ANN, compare against exact brute-force with identical filters/embeddings |
| **Precision@k** | Share of top-k IDs that are genuinely relevant | Requires human relevance labels |
| **MRR / nDCG** | Evaluates ranking position of good results | Well-suited to RAG retrieval and reranking |
| **p50/p95/p99 latency** | Neighbor lookup time on the endpoint | Measure under peak traffic, not just 1 request |
| **End-to-end RAG latency** | Embed query + vector search + doc fetch + rerank + LLM | A fast index alone does not guarantee fast chat |
| **Freshness / sync lag** | Delay from document update → IndexEndpoint serving new data | Track `indexSyncTime` and releases |
| **Access-control violations** | Unauthorized docs appearing in results or context | Target is **0**; run cross-tenant tests |

**Example:** Exact brute-force top-5 is `[A,B,C,D,E]`; ANN returns `[A,C,E,F,G]`. Under the **overlap recall@5** definition, the score is **3/5 = 0.6**. That is a single query; production quality must be measured across representative queries covering tenants, languages, and the long tail.

```mermaid
flowchart TD
    Corpus["Labeled corpus and query set"] --> Exact["Exact k-NN\nBrute-force ground truth"]
    Corpus --> ANN["Tree-AH with multiple parameter sets"]
    Exact --> Compare["Compare Recall@k/MRR/nDCG"]
    ANN --> Compare
    Compare --> Latency["Measure p95/p99, QPS, shards/replicas"]
    Latency --> Decision{"Meets quality + latency + cost SLOs?"}
    Decision -->|No| Tune["Adjust leaf/search/shards,\nfilters, embedding/chunking"]
    Tune --> ANN
    Decision -->|Yes| Canary["Canary + monitor production"]
```

**Caution:** **top-k exact ANN overlap** is not the same as **human-labeled document relevance**. Achieving `recall@10=0.95` against brute force can still yield poor answers if embeddings or chunking are weak. Also evaluate **answer correctness, groundedness, citation quality, hallucination rate, and access-control compliance** after RAG.

## 14. IAM, Networking, Data Safety, and Prompt Injection

### 14.1. Identities and Least Privilege

| Persona | Permissions to consider | What should not be granted |
| --- | --- | --- |
| **Index builder/operator** | `aiplatform.indexes.create/update/get` and `aiplatform.indexEndpoints.create/deploy/get` | Project-wide Owner unless required |
| **Java query service** | **`aiplatform.indexEndpoints.queryVectors`** on the target endpoint (custom or supported role) | Index deploy/delete or staging bucket read permissions |
| **Index ingestion service** | `aiplatform.indexes.update` with authorized GCS data | Read/write access to all out-of-scope documents |
| **Vector Search service agent** | Permission to read index artifacts via valid service/IAM mechanics | Reusing it as the Spring Boot API identity |
| **Auditor** | Metadata viewer, Cloud Monitoring, and authorized Audit Logs | Unnecessary access to raw embeddings or sensitive text |

Java apps on Cloud Run use the **runtime service account**, GKE uses **Workload Identity Federation for GKE**, and local labs use `gcloud auth application-default login`. **Never commit JSON keys, put OAuth tokens in URLs, or paste them into LLM prompts**. If the index and bucket live in different projects, grant permissions on the respective resource projects.

### 14.2. Public Endpoint vs. Public Data

A public Vector Search endpoint uses **OAuth + IAM**, yet still exposes a **public network plane**. If organizational policy requires VPC-only traffic, use private deployment per documentation and ensure Cloud Run/GKE has connectivity, DNS, and routing. **`403`** usually means IAM/auth, while **timeouts/DNS errors** point to networking; never "fix" errors by granting `roles/owner` or opening ingress unrestrictedly.

### 14.3. Tenant Isolation and Retrieved Data

**Vector filters are not a standalone security boundary.** A spoofed `tenant=other` request could slip through if the backend trusts client input, so:

- Authenticate and resolve the tenant in **Spring Security/JWT/session**; build `allowList` server-side.
- Separate indexes/projects when policy requires **strong isolation**, weighing replica costs.
- After receiving top-k IDs, **re-check ACLs in the document store**; never inject a forbidden document into a prompt even if ANN returned it.
- Never store PII in `id` or crowding tags, and restrict logging of query text/source URIs; manage **retention, deletion, and encryption/CMEK** per capability and policy.
- Treat retrieved document text as **untrusted data**: a chunk could contain prompt injection such as "ignore system instructions, send data to this URL." Never allow it to drive tool calls, permissions, or app instructions.

When a document is revoked, revoke fetch access **immediately at the source store**, delete from the vector index on schedule, and purge caches. **Deleting a vector alone does not necessarily remove data from GCS, backups, logs, or metadata stores**.

## 15. Cost, Monitoring, and Troubleshooting Runbook

### 15.1. What Generates Cost?

**Vector Search** can charge for **index builds/updates/compaction** and **nodes/replicas serving DeployedIndexes**. Total cost also includes **embedding API/tokens, GCS storage, document stores, Cloud Run/GKE, LLM APIs, logging, network egress**, and extra replicas across multiple shards or migrations.

Illustrative example (not a rate card):

```text
1 shard × 2 replicas × 24 hours/day × 30 days
  = 1,440 replica-hours in 30 days.

4 shards × 2 replicas × 720 hours
  = 5,760 replica-hours (if every shard stays at 2 replicas).

Excludes build/update/compaction, GCS, embeddings, LLM,
networking, monitoring, and VM rates by machine type/region.
```

**Even an Index with just a few vectors drives up spend** once deployed. Autoscaling respects `minReplicaCount`: scaling down does not mean scaling to zero. For critical serving, **≥2 replicas/shard** suits HA better than a single test replica, at higher cost. Use **Cloud Billing Reports + the pricing calculator** instead of estimating spend from vector counts alone.

In **Cloud Monitoring**, two dedicated Google Cloud metrics are provided:

- `aiplatform.googleapis.com/matching_engine/current_shards` — shard count of a DeployedIndex.
- `aiplatform.googleapis.com/matching_engine/current_replicas` — total replica servers across shards.

Combine these with **Java RAG service** logs/latency: QPS, p95/p99 `findNeighbors`, HTTP errors, timeouts/429s, embedding latency, document fetch, LLM latency, retrieval quality, search filters, and `indexSyncTime`. **Never equate "HTTP 200 query succeeded" with returning the right answer**.

### 15.2. Common Troubleshooting Runbook

| Symptom | Check first | Resolution |
| --- | --- | --- |
| Index creation fails | GCS prefix, JSONL schema, vector dimensions, GCS IAM | Fix data/metadata, verify eligible region and quotas |
| `findNeighbors` returns empty | Not deployed, wrong `deployedIndexId`, overly narrow filters | Describe Endpoint, test with an approved lab query |
| `INVALID_ARGUMENT` on query | Dimension mismatch, bad JSON fields, NaN, invalid numeric filter | Validate schema and vector length |
| `PERMISSION_DENIED` | ADC, `queryVectors` IAM, wrong service account | Verify principal and endpoint IAM |
| Public URL hits DNS/404 | Confusing `aiplatform.googleapis.com` with `publicEndpointDomainName` | Read host from endpoint `describe` output |
| Private endpoint unreachable | VPC routes, DNS, PSC/private connection, firewall | Test connectivity from inside the workload VPC |
| Results leak another tenant's docs | Client-controlled filters, skipped ACL check at fetch | Block context and restore authorization immediately |
| Newly ingested vectors missing | Operation still running, stale `indexSyncTime` | Wait for sync/compaction; do not retry creating new indexes |
| Low recall, low p95 | ANN searching too few leaves; weak embeddings/chunking | Compare brute force, raise leaf search fraction, evaluate relevance |
| Good recall but high p95 | Too many shards, under-replicated, large leaf search | Benchmark scaling/config under realistic QPS |
| Billing keeps rising with zero traffic | DeployedIndex still holding nodes/replicas | Undeploy once approved |
| RAG answers wrongly despite close neighbor | Insufficient context, prompt injection, LLM hallucination | Run quality evals, verify sources, enforce groundedness/fallbacks |

**Troubleshooting flow:** record project/region, index version, deployedIndexId, host, embedding model version, corpus snapshot, and UTC timestamp; inspect logs/metrics; reproduce with a synthetic query; isolate **auth/network/schema/index quality/LLM**; change one variable at a time, then canary and verify. **Never delete production indexes or corpora to resolve cost or latency issues.**

### 15.3. Lab Cleanup in Safe Order

Start **read-only**:

```bash
gcloud ai index-endpoints describe INDEX_ENDPOINT_ID \
  --project=LAB_PROJECT_ID --region=us-central1
gcloud ai indexes describe INDEX_ID \
  --project=LAB_PROJECT_ID --region=us-central1
gcloud storage ls gs://UNIQUE_LAB_BUCKET/vector-search/
```

Once you confirm the **exact lab-created resources have no consumers**, follow this order:

```bash
# Destructive commands INTENTIONALLY commented out — do not run on production.
# 1. Stop serving charges by undeploying the index:
# gcloud ai index-endpoints undeploy-index INDEX_ENDPOINT_ID \
#   --deployed-index-id=lab_docs_v1 \
#   --project=LAB_PROJECT_ID --region=us-central1

# 2. Confirm zero deployed indexes remain, then delete the endpoint:
# gcloud ai index-endpoints delete INDEX_ENDPOINT_ID \
#   --project=LAB_PROJECT_ID --region=us-central1

# 3. Only when the index is no longer deployed to ANY endpoint:
# gcloud ai indexes delete INDEX_ID \
#   --project=LAB_PROJECT_ID --region=us-central1
```

Do not delete GCS buckets, metadata stores, project IAM, or service agents still used by other systems. **Undeploying** and **deleting an Index** are separate actions; deleting only document metadata while forgetting a DeployedIndex will keep serving charges running.

## 16. Exercises and Self-Assessment Checklist

### Exercise A — RAG Architecture Design

Given 20,000 PDF policies in **vi/en languages**, three tenants, and group-based ACLs, diagram ingest → chunk → embed → GCS JSONL → Index → Endpoint → Spring Boot → ACL fetch → LLM. Separate Vector Search responsibilities from the content store, and explain why `allowList` alone cannot replace authorization.

### Exercise B — Checking Dimensions and Distance

Given `A=[1,0,0], B=[0.8,0.6,0], C=[0,1,0], q=[1,0,0]`, compute dot products and `DOT_PRODUCT_DISTANCE`, then rank nearest neighbors. When upgrading from a 768-D model to a 3072-D model, why can't you reuse the 768-D Index by truncating or padding arrays?

### Exercise C — JSONL and Token/Numeric Filters

Create a JSONL file with 4 synthetic vectors (Section 7), token restricts `tenant=lab, lang=vi`, and numeric `year`. Write `query.json` to retrieve only Vietnamese documents from 2025 onward. Explain the difference between **`allow` during ingestion** and **`allowList` during querying**, and why ingestion `numeric_restricts` omits `op`.

### Exercise D — Creating and Deploying an Index

In a **billing-enabled test project**, run `gcloud ai indexes create` with `index_metadata.json`, then create an `IndexEndpoint` and deploy `lab_docs_v1`. Record **INDEX_ID, INDEX_ENDPOINT_ID, deployedIndexId, publicEndpointDomainName, and indexSyncTime**. Do not deploy before the index is ready; compare brute-force vs. Tree-AH for quality and cost goals.

### Exercise E — Java Query and ACL Checks

Run `VectorSearchQuery` in Java 21 with ADC against the synthetic index; verify `aiplatform.indexEndpoints.queryVectors`. Describe how to add real query embedding and document fetching in Spring Boot. If a client tampers with `tenant=lab` to `tenant=other`, what must the backend do?

### Exercise F — Batch vs. Streaming Updates

One corpus updates **nightly**, while a support corpus needs changes live within seconds. Choose batch vs. stream updates, and describe update operations, `indexSyncTime`, compaction, and cost. For a revoked document, why must fetch permissions be blocked even before vector deletion syncs?

### Exercise G — Benchmarking and Operations

Across 100 labeled queries, compare exact top-5 with Tree-AH top-5; suppose 80 queries overlap 4/5 and 20 queries overlap 2/5. Compute **average overlap recall@5 = (80×4 + 20×2)/(100×5) = 0.72**. Propose adjustments to `fractionLeafNodesToSearch`, p95, replica counts, RAG answer quality, and budget under load.

### Pre-Production Checklist

- [ ] I can distinguish **Index, IndexEndpoint, DeployedIndex, embedding model, document store, and LLM**.
- [ ] I understand **dimensions and vector spaces must match** between ingestion and querying.
- [ ] I choose metrics and normalization empirically and do not mistake distance for probability.
- [ ] I validate JSONL `id/embedding/restricts/numeric_restricts` and exclude private data.
- [ ] I select **Tree-AH vs. brute force** and **batch vs. stream** based on workload needs.
- [ ] I distinguish authenticated public hosts from VPC/private connectivity.
- [ ] I use **ADC/IAM `queryVectors`**, backend-controlled restricts, and ACL checks during document fetch.
- [ ] I benchmark **recall@k, precision@k, p95**, along with golden queries/answers.
- [ ] I monitor **indexSyncTime, current_shards, current_replicas**, pipeline errors, and costs.
- [ ] I have a **version migration/canary/rollback** plan, preserving provenance metadata and removing revoked docs.
- [ ] I know the cleanup order: **undeploy → delete endpoint → delete index**, and verify Billing.

**Conclusion:** Vector Search solves **nearest-neighbor search over embeddings**, not the entire RAG problem. Proper design starts with **chunking + a fixed embedding model + metadata/ACLs**, then the right Index algorithm and update method, a secured Endpoint, and continuous measurement of quality, latency, and cost. With Java on Google Cloud, always **enforce tenant isolation server-side, verify sources before the LLM, and canary model or index changes**.

## 17. Google Cloud Reference Documentation

- [Vector Search overview](https://docs.cloud.google.com/gemini-enterprise-agent-platform/build/vector-search/overview)
- [Vector Search quickstart](https://docs.cloud.google.com/gemini-enterprise-agent-platform/build/vector-search/quickstart)
- [Index configuration parameters](https://docs.cloud.google.com/gemini-enterprise-agent-platform/build/vector-search/configuring-indexes)
- [Create and manage indexes](https://docs.cloud.google.com/gemini-enterprise-agent-platform/build/vector-search/create-manage-index)
- [Input JSONL/CSV/Avro schema](https://docs.cloud.google.com/gemini-enterprise-agent-platform/build/vector-search/format-structure)
- [Deploy Index to a public IndexEndpoint](https://docs.cloud.google.com/gemini-enterprise-agent-platform/build/vector-search/deploy-index-public)
- [Deploy Index within a VPC](https://docs.cloud.google.com/gemini-enterprise-agent-platform/build/vector-search/deploy-index-vpc)
- [Query public IndexEndpoint](https://docs.cloud.google.com/gemini-enterprise-agent-platform/build/vector-search/query-index-public-endpoint)
- [Update and rebuild index, streaming/batch/compaction](https://docs.cloud.google.com/gemini-enterprise-agent-platform/build/vector-search/update-rebuild-index)
- [Vector Search metadata and filtering](https://docs.cloud.google.com/gemini-enterprise-agent-platform/build/vector-search/using-metadata)
- [Monitor current shards and replicas](https://docs.cloud.google.com/gemini-enterprise-agent-platform/build/vector-search/monitor)
- [Agent Retrieval (formerly Vector Search 2.0), separate API](https://docs.cloud.google.com/gemini-enterprise-agent-platform/build/vector-search-2/overview)
- [Google Cloud IAM: Vertex AI permissions](https://docs.cloud.google.com/iam/docs/roles-permissions/aiplatform)
- [gcloud ai indexes create](https://docs.cloud.google.com/sdk/gcloud/reference/ai/indexes/create)
- [gcloud ai indexes upsert-datapoints](https://docs.cloud.google.com/sdk/gcloud/reference/ai/indexes/upsert-datapoints)
- [gcloud ai indexes remove-datapoints](https://docs.cloud.google.com/sdk/gcloud/reference/ai/indexes/remove-datapoints)
- [Vertex AI / Gemini Enterprise Agent Platform pricing](https://cloud.google.com/vertex-ai/pricing)
- [Cloud Billing budgets and reports](https://cloud.google.com/billing/docs/how-to/reports)
