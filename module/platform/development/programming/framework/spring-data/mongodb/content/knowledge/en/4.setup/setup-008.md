# Loading Seed Data and Keeping Connection Secrets Out of Source Code

In a **Spring Data MongoDB** application, successfully connecting to MongoDB Server is only the first step. Developers typically need a set of **seed data** to verify repositories, `MongoTemplate`, queries, and UI screens. At the same time, a connection URI may contain usernames, passwords, hostnames, or authentication parameters: this sensitive information must be managed **outside source code**.

This lesson belongs to the **Setup** chapter of the `SPRING_DATA_MONGODB` module. We will prepare a development database, configure Spring Boot to read the URI from the environment, load sample products using Spring Data MongoDB, verify the loaded data, and identify common query, index, permission, and security pitfalls. These techniques also establish clean input data for learning aggregation, transactions, reactive access, testing, and performance diagnostics.

After this lesson, you will be able to:

- Configure connections via environment variables or a secret manager without committing credentials.
- Write **idempotent** seed logic that only modifies authorized databases.
- Choose among `MongoTemplate`, repositories, and `mongoimport` when preparing datasets.
- Verify document counts, mappings, indexes, queries, and common connection issues.

## 1. Participating Components

```mermaid
flowchart TD
    ENV[Environment variable or secret manager] --> BOOT[Spring Boot: reads config, creates beans]
    BOOT --> DATA[Spring Data MongoDB: MongoTemplate, Repository]
    DATA --> DRIVER[Java Driver: MongoClient, protocol, pool]
    DRIVER <--> MONGO[(MongoDB Server: collections, indexes, data)]
    SEED[ApplicationRunner for local environment only] --> DATA
```

**Spring Boot** reads configuration and initializes beans, **Spring Data MongoDB** translates Java calls into data operations, **MongoDB Java Driver** sends commands and manages connections, and **MongoDB Server** actually stores and queries BSON documents. Seed data is written to the server through these layers; Boot does not generate sample data automatically simply because the MongoDB dependency was added.

Two common approaches are used to prepare data:

| Approach | Best suited when | Things to watch |
| --- | --- | --- |
| `ApplicationRunner` combined with `MongoTemplate` | You want to seed using Java domain types, Spring Data mapping, and runtime configuration flags | Must be disabled by default, restricted by profile/database, and avoid overwriting existing data |
| `mongoimport` or `mongosh` scripts | You already have JSON/CSV fixtures and need to import many documents independently of the app | Pick the right database, control upsert/overwrite behavior, and preserve BSON types on import |

## 2. Keeping Connection Details Outside Source Code

### 2.1. Never Hardcode Sensitive URIs in the Repository

Here is a **configuration pattern to avoid** if the URI contains credentials:

```yaml
# DO NOT commit real URIs containing passwords into source code.
spring:
  data:
    mongodb:
      uri: "mongodb://user:password-placeholder@db.internal:27017/shop"
```

Credentials can leak via Git history, pull requests, backups, build artifacts, screenshots, and CI logs. Removing credentials in a later commit does not erase prior history. If a real credential is ever exposed, **revoke/rotate it immediately** and assess impact scope.

With **Spring Boot 3.x**, declare a placeholder instead:

```yaml
# src/main/resources/application.yml
spring:
  data:
    mongodb:
      uri: ${MONGODB_URI}

app:
  seed:
    enabled: false
```

`${MONGODB_URI}` tells Spring to resolve `MONGODB_URI` from the process environment. A missing value should be treated as a configuration error; **never put a real password as a fallback value**. MongoDB property names may differ across Spring Boot versions; always check the documentation for the exact version you run.

In the example above, `app.seed.enabled` defaults to `false`. Add configuration for the local development profile so seeding runs only when explicitly requested:

```yaml
# src/main/resources/application-local.yml
app:
  seed:
    enabled: ${SEED_SAMPLE_DATA:false}
```

`${SEED_SAMPLE_DATA:false}` reads `SEED_SAMPLE_DATA`, defaulting to `false`. The `application*.yml` files in the repository contain only **variable names and control flags**, never secrets.

**Note on `.env` files:** Spring Boot does not read an arbitrary `.env` file in the project directory by default. To use one, an external tool or launcher must load it into process environment variables beforehand. Never commit `.env` containing secrets; you may keep an `.env.example` with dummy values for documentation. Environment variables are also not an absolute vault: anyone with access to the process or host can inspect them.

### 2.2. Running Locally on Windows

Assume local MongoDB listens only on loopback and **does not require authentication in an isolated learning environment**. PowerShell example:

```powershell
$env:MONGODB_URI = 'mongodb://127.0.0.1:27017/shop_local'
$env:SPRING_PROFILES_ACTIVE = 'local'
$env:SEED_SAMPLE_DATA = 'true'

# Example if the project uses Maven Wrapper:
.\mvnw.cmd spring-boot:run
```

If running from an IDE or Gradle, add **the exact same variables** to the corresponding run configuration. An IDE may not inherit variables set in a separate terminal window.

When a URI contains a username/password, never paste the real URI into command examples, commits, tickets, or logs. For staging/production, use a secret manager, platform secret injection, or CI/CD variables at runtime. Avoid passing URIs containing passwords directly as CLI arguments, since they can appear in shell history or process listings.

### 2.3. Principles for Protecting Connections in Real Environments

- **Isolate environments:** local, test, staging, and production use separate databases, accounts, and secrets.
- **Least privilege:** the application account only gets privileges required for its own database; accounts managing indexes/migrations can be separated.
- **Protect data in transit:** enable TLS over untrusted networks; verify DNS, replica set config, `authSource`, and authentication options for your deployment.
- **Prevent observation leaks:** never log `MONGODB_URI`, config dumps, passwords, or exception objects containing sensitive strings. Be careful with debug logs and configuration endpoints.
- **Manage credential lifecycle:** support revocation and rotation; URL-encode special characters in credentials when embedding them in URIs as required by the format.

## 3. Preparing a Sample Product Dataset

We will use the `products` collection in the `shop_local` database. Each document includes `_id`, `sku`, `name`, `priceVnd`, `stock`, and `active`:

```javascript
// shop_local.products
{
  _id: "demo-book-001",
  sku: "BK-001",
  name: "Notebook",
  priceVnd: NumberLong("85000"),
  stock: 40,
  active: true
}
{
  _id: "demo-pen-002",
  sku: "PN-002",
  name: "Fountain Pen",
  priceVnd: NumberLong("25000"),
  stock: 100,
  active: true
}
```

Choosing deterministic `_id` values prefixed with `demo-` helps separate fixtures from other data. Fields must be clearly specified so repositories, aggregations, and tests share a consistent shape. `priceVnd` uses integer VND (`long` in Java) to avoid floating-point rounding issues for integer currency amounts.

A well-designed seeder has three properties:

1. **Idempotent:** running multiple times never duplicates records.
2. **Scoped:** runs only in permitted environments and databases.
3. **Clear update rules:** never unexpectedly wipes a collection or overwrites changes a developer made while testing.

Never put `deleteMany({})` or `drop()` inside application startup logic. If a reset is needed, implement a separate explicit command with confirmation and target database checks.

## 4. Seeding with Spring Data MongoDB

### 4.1. Mapping `Product`

Examples use Java 17+ and Spring Data MongoDB. Place these Java snippets in appropriate files when integrating into your project:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "products")
public record Product(
        @Id String id,
        String sku,
        String name,
        long priceVnd,
        int stock,
        boolean active
) {}
```

`@Document` specifies the collection and `@Id` maps `id` to `_id`. Spring Data handles conversion between Java and BSON via the Java Driver. Because the sample `demo-*` IDs are not ObjectId strings, this example intentionally uses string IDs.

### 4.2. Seeder Guarded by Profile and Configuration Flag

We use `ApplicationRunner` to run after Spring Boot builds the application context, combined with `@Profile("local")` and `@ConditionalOnProperty` so it executes only when explicitly enabled. `MongoTemplate.upsert` with `setOnInsert` writes fields only when the document does not yet exist:

```java
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Profile;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import org.springframework.stereotype.Component;

@Component
@Profile("local")
@ConditionalOnProperty(name = "app.seed.enabled", havingValue = "true")
public class LocalProductSeeder implements ApplicationRunner {
    private final MongoTemplate mongoTemplate;

    public LocalProductSeeder(MongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }

    @Override
    public void run(ApplicationArguments args) {
        String databaseName = mongoTemplate.getDb().getName();
        if (!"shop_local".equals(databaseName)) {
            throw new IllegalStateException(
                    "Seeding is only allowed on database shop_local, current: "
                            + databaseName
            );
        }

        insertIfMissing("demo-book-001", "BK-001", "Notebook",
                85_000L, 40, true);
        insertIfMissing("demo-pen-002", "PN-002", "Fountain Pen",
                25_000L, 100, true);
    }

    private void insertIfMissing(
            String id, String sku, String name,
            long priceVnd, int stock, boolean active
    ) {
        Query query = Query.query(Criteria.where("_id").is(id));
        Update update = new Update()
                .setOnInsert("sku", sku)
                .setOnInsert("name", name)
                .setOnInsert("priceVnd", priceVnd)
                .setOnInsert("stock", stock)
                .setOnInsert("active", active);

        mongoTemplate.upsert(query, update, Product.class);
    }
}
```

Purpose of each guard:

- `@Profile("local")`: the bean is registered only when the `local` profile is active.
- `app.seed.enabled=true`: requires the runner to explicitly turn the flag on; off by default.
- `shop_local`: double-checks the target database before performing any writes.
- Deterministic `_id` and `$setOnInsert`: if the document already exists, avoids inserting duplicates or overwriting `stock`/`name` modified during local testing.

Spring Data translates `upsert` into a MongoDB operation, and the driver sends it to the server. Each single-document upsert is atomic at the document level; seeding multiple documents is **not implicitly a transaction**. Also, if you edit fixture values in source code later, `$setOnInsert` will **not update** existing documents; if intentional updates are needed, design an explicit `$set`/fixture-versioning policy or a controlled, scoped reset.

### 4.3. Verifying via Repository and Indexes

```java
import java.util.Optional;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface ProductRepository
        extends MongoRepository<Product, String> {
    Optional<Product> findBySku(String sku);
}
```

`findBySku("BK-001")` verifies mapping from MongoDB to `Product`. However, Spring Data does not automatically guarantee the server has an appropriate index. On the local database, you can create an index on SKU:

```javascript
// Run only after verifying there are no duplicate SKUs.
db.products.createIndex({ sku: 1 }, { unique: true });
```

`@Indexed(unique = true)` is Spring Data mapping metadata; automatic index creation depends on configuration. In real deployments, manage indexes deliberately via migrations/scripts and verify them on MongoDB Server.

## 5. Loading Sample JSON with `mongoimport`

When sample data already exists as JSON/CSV files, you do not have to boot the Java application just to load fixtures. `mongoimport`, part of **MongoDB Database Tools**, can import an array of documents into a collection.

Example `products.json` using **MongoDB Extended JSON** to preserve the 64-bit BSON integer type for `priceVnd`:

```json
[
  {
    "_id": "demo-book-001",
    "sku": "BK-001",
    "name": "Notebook",
    "priceVnd": {"$numberLong": "85000"},
    "stock": 40,
    "active": true
  },
  {
    "_id": "demo-pen-002",
    "sku": "PN-002",
    "name": "Fountain Pen",
    "priceVnd": {"$numberLong": "25000"},
    "stock": 100,
    "active": true
  }
]
```

In PowerShell, if MongoDB runs **locally without authentication**, you can import with:

```powershell
mongoimport --host 127.0.0.1 --port 27017 `
    --db shop_local --collection products `
    --file products.json --jsonArray `
    --mode upsert --upsertFields _id
```

Here:

- `--db` and `--collection` specify the **destination**, which must be double-checked before running.
- `--jsonArray` indicates the file contains a JSON array.
- `--mode upsert --upsertFields _id` matches existing documents by `_id` before inserting, preventing duplicate documents for the same ID.

**Key trade-off:** using `mongoimport` in `upsert` mode **overwrites existing documents with the file's contents**. This differs from `$setOnInsert` in the Java seeder, which only sets fields on initial insert. Only use overwriting imports when re-syncing fixtures is intentional.

The sample command contains no username/password and is strictly for a local database. Against authenticated databases, supply credentials safely via platform/tool-supported mechanisms; avoid typing real URIs with passwords directly on the command line. Fixtures should contain **synthetic data only**—never copy real user personal data or passwords.

### 5.1. Which Approach Should You Choose?

| Need | Appropriate Solution |
| --- | --- |
| Create a few baseline records when running a demo app | Conditional `ApplicationRunner` with `MongoTemplate` |
| Fixtures tied to domain logic, mappings, or custom converters | Seed via Spring Data and test mapping |
| Load thousands of sample records from existing files | `mongoimport` or a dedicated data import script |
| Tests requiring distinct datasets per test case | Set up fixtures per test using an isolated database/container |
| Real production bootstrap data | Controlled migration/job with a rollback plan; keep local seeders disabled |

## 6. Verifying After Loading Seed Data

Reading "seed completed" in logs is not enough. Verify the **exact database**, document count, field values, BSON types, and query behavior.

With development MongoDB on loopback, open the shell:

```powershell
mongosh mongodb://127.0.0.1:27017/shop_local
```

Then run:

```javascript
db.getName(); // expected: "shop_local"

db.products.find(
  { _id: { $in: ["demo-book-001", "demo-pen-002"] } },
  { _id: 1, sku: 1, name: 1, priceVnd: 1, stock: 1 }
);

db.products.countDocuments({
  _id: { $in: ["demo-book-001", "demo-pen-002"] }
}); // expected: 2

db.products.getIndexes();

db.products.find({ sku: "BK-001" }).explain("executionStats");
```

Expected results:

1. Database name is `shop_local`.
2. Both sample IDs are found, each appearing once since `_id` is unique.
3. `priceVnd`, `stock`, and `active` values are accurate; the repository maps them cleanly into `Product`.
4. The index on `sku` appears if the index creation command was run.
5. On a second run of the Java seeder, the count **for the two sample IDs** stays 2.

Count only the two sample IDs because the collection may hold other experimental products. Do not assert `countDocuments({}) == 2` unless the local environment is guaranteed empty.

`explain("executionStats")` shows the query plan and execution stats, letting you observe `IXSCAN` vs. `COLLSCAN`. With only two documents, the server may pick a collection scan even when an index exists; that is not automatically a bug. When studying performance optimization, use a dataset large enough and access patterns realistic enough to draw valid conclusions.

If seeding via Spring Data code, you can also verify at the application layer:

```java
Product product = productRepository.findBySku("BK-001")
        .orElseThrow(() -> new IllegalStateException("Missing sample data"));

if (product.priceVnd() != 85_000L) {
    throw new IllegalStateException("Sample product price is incorrect");
}
```

This snippet illustrates verification inside a method where `productRepository` is available. In real tests, use test-framework assertions for clearer failure reporting.

## 7. Testing and Environment Isolation

`@DataMongoTest` supports testing MongoDB access slices in Spring Boot. For behaviors such as index creation, upserts, aggregations, transactions, or BSON mapping, test against a **real MongoDB instance in an isolated test environment**, such as MongoDB managed by Testcontainers. Mocking repositories only tests mock behavior and does not prove the driver communicates properly with the server.

Recommended test scenarios:

| Scenario | Expected Result |
| --- | --- |
| `local` profile + seed flag enabled + URI pointing to `shop_local` | Seeder writes the exact two sample IDs |
| Calling the seeder or restarting a second time | No duplicates created, and existing values are preserved due to `setOnInsert` |
| Any profile other than `local` | Seeder bean is not created |
| `local` profile with seed flag disabled | Seeder does not run |
| URI accidentally points to another database | Seeder refuses to write via database name check |
| `ProductRepository.findBySku` check | Reads back the record and declared Java types accurately |
| Unique index on `sku` | Server rejects duplicate SKUs when the index exists |

Create isolated fixtures per test suite, or enable seeding explicitly only if genuinely needed. Never let tests depend on execution order or share state in a shared database. In staging/production, the local seed flag must always remain **disabled**, and read/write accounts must be separated per environment.

If a seed batch requires updating multiple documents in an "all-or-nothing" manner, design transactions on a **supporting MongoDB deployment** with a configured Spring Data transaction manager. Never assume a local standalone MongoDB supports multi-document transactions. Small seeders built on independent upserts usually do not need transactions.

For reactive applications, you can use `ReactiveMongoTemplate` or `ReactiveMongoRepository` and initialize data along a proper `Mono`/`Flux` chain. Never invoke blocking `MongoTemplate` inside a reactive pipeline and assume it becomes non-blocking. Rules around connection secrets, database scoping, and idempotency remain identical in reactive apps.

## 8. Common Errors and Resolutions

| Symptom | Possible Causes | How to Check |
| --- | --- | --- |
| App fails to start when `MONGODB_URI` is missing | Variable not passed to the process, wrong property name for Boot version | Check run configuration, active profile, and placeholder syntax |
| `Connection refused` or timeout | MongoDB not running, wrong host/port, firewall/VPN, DNS, or topology | Check server status, address, and connectivity from the app host |
| `Authentication failed` | Wrong username, password, `authSource`, or permissions | Verify secret in secret manager, user, and roles without logging credentials |
| App runs, but sample data is missing | Profile/seed flag not enabled, bean outside component scan, wrong database | Check profile, `app.seed.enabled`, `db.getName()`, and query via shell |
| Rerunning creates duplicate records | Seed uses random IDs or unguarded inserts | Use deterministic `_id` values and conditional upserts |
| `E11000 duplicate key` | Duplicate `_id` or unique index conflict on `sku` | Inspect data and indexes; fix fixtures before rerunning |
| Sample product retains old price after editing seeder code | `$setOnInsert` does not update existing documents | Design an intentional update policy or controlled fixture reset |
| SKU query becomes slow on large datasets | Missing/unsuitable index, high volume, or non-selective filter | Run `getIndexes()`, `explain("executionStats")`, and benchmark real queries |
| URI/password appears in logs or pipelines | Printing config, overly verbose debug logs, secrets on CLI | Stop leakage, mask values, and revoke/rotate exposed credentials |

A real-world pitfall: `MONGODB_URI` is exported in PowerShell, yet the app is launched from an IDE that was opened earlier. The IDE may not inherit newly set shell variables, causing failures even though the terminal prints the right value. Check the **environment of the actual process** running the app and use your IDE/platform's native secret injection where supported.

## 9. End-to-End Practice Checklist

1. Prepare a development MongoDB Server, connecting strictly to the `shop_local` database.
2. Create a Spring Boot 3.x configuration with `spring.data.mongodb.uri: ${MONGODB_URI}` and `app.seed.enabled` defaulting to `false`.
3. Supply `MONGODB_URI` via environment variable or secret manager; confirm no credentials are committed.
4. Implement `Product`, `ProductRepository`, and `LocalProductSeeder` with deterministic IDs, `local` profile, seed flag, and target database guard.
5. Run the app with `local` profile and `SEED_SAMPLE_DATA=true`; verify the two records via `mongosh` and the repository.
6. Restart to verify idempotency; test disabling the seed flag or changing the database to confirm the write guard rejects seeding.
7. Create an index supporting `findBySku`, inspect `explain`, and test against an isolated test MongoDB instance.
8. For staging/production deployments, inject connections via a secret manager, enforce least privilege and proper TLS, and keep the local seeder disabled.

**Remember:** sample data for development is only safe with clear **scope, deterministic keys, and explicit write rules**. Spring Boot reads connection configuration from the environment; Spring Data MongoDB builds queries and updates; the Java Driver communicates with the server; and MongoDB Server stores the data. The goal is to reproducibly set up your learning state, explore repositories/aggregations/indexes, and diagnose performance without leaking connection secrets or touching real data unintentionally.
