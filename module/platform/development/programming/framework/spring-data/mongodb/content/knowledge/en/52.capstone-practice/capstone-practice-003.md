# Setting Up a Replica Set Environment and Seeding Sample Data

## 1. Objectives of the Capstone Practice

A **Spring Data MongoDB** application can access MongoDB using **MongoTemplate**, **MongoRepository**, **ReactiveMongoTemplate**, or reactive repositories. To additionally practice features such as transactions, change streams, and integration testing, you need a MongoDB environment with an appropriate topology and a stable sample dataset.

This lesson sets up a **single-node replica set** using Docker Compose, initializes a sales database, and seeds the **customers**, **products**, and **orders** collections. By the end, a Spring application can connect to run queries, document mapping, and subsequent labs. Beyond CRUD, you will test a rolled-back transaction and observe an insert event via change stream to confirm the replica set actually works.

**Upon completion, learners should have:**

- A MongoDB container running with **replSet = rs0** whose member has reached the **PRIMARY** state.
- A **shop_capstone** database containing **5 customers, 6 products, and 8 orders** with verifiable IDs and totals.
- Indexes for email, SKU, and selected order queries.
- A connection URI for a Spring Data MongoDB application running **on the host machine**.
- Query read results from **MongoTemplate/MongoRepository** and proof that transactions and change streams work.

**Scope:** this is a **local development and learning environment** using a single-node replica set without authentication enabled, and must not be treated as a production-safe configuration. A single-node replica set supports basic transaction and change stream tests, but does not verify failover, primary re-election, or replication lag.

## 2. Architecture and Required Tools

### 2.1. Architecture

~~~mermaid
flowchart TB
    Host["Developer machine<br/>Spring Boot + Java"]
    CLI["Terminal<br/>docker compose / mongosh"]
    Port["127.0.0.1:27017<br/>published port"]
    RS[("MongoDB container<br/>mongod --replSet rs0<br/>Single PRIMARY + oplog")]
    Vol[("Named Docker volume<br/>mongo_rs_data")]
    DB["shop_capstone<br/>customers / products / orders"]
    Host -->|"mongodb://localhost:27017"| Port
    CLI -->|"docker compose exec"| RS
    Port --> RS
    RS --> Vol
    RS --> DB
~~~

**Key point:** the Spring application in this lesson runs **directly on the host machine**, so MongoDB advertises the replica set member address as **localhost:27017**. If you later move Spring into another container, you must change networking and the advertised replica set member address; you cannot copy the **localhost** URI into an application container and expect it to reach MongoDB.

### 2.2. Minimum Requirements

| Tool | Purpose | Self-check command |
| --- | --- | --- |
| Docker Engine / Docker Desktop | Run the MongoDB container | **docker version** |
| Docker Compose v2 | Manage services and volumes | **docker compose version** |
| MongoDB Docker image | Run **mongod** and **mongosh** inside the container | **docker compose pull mongo** |
| Project-compatible JDK | Run the Spring Boot application | **java -version** |
| Project Maven/Gradle wrapper | Build and run the application | **mvnw / gradlew** per OS |
| Terminal/PowerShell | Create the two sample files and manage containers | Current terminal |

The examples below use the **mongo:7.0** image, Spring Boot **3.x**, and compatible Spring Data MongoDB. These are **illustrative versions**, not claims about the latest release. If a project uses a different Boot/driver/server version, check the compatibility matrix and verify APIs and configuration properties for that version.

### 2.3. Two Files to Create for the Practice

In a standalone practice folder, create:

~~~text
mongo-capstone/
├── compose.yaml
└── seed.js
~~~

The snippets below are **sample file contents** you can copy into your practice folder. No Spring Data MongoDB source code edits are needed to initialize the database first.

## 3. Creating a MongoDB Replica Set with Docker Compose

### 3.1. Contents of compose.yaml

~~~yaml
services:
  mongo:
    image: mongo:7.0
    command:
      - mongod
      - --replSet
      - rs0
      - --bind_ip_all
    ports:
      # Publish only to the developer machine's loopback address.
      - "127.0.0.1:27017:27017"
    volumes:
      - mongo_rs_data:/data/db
    restart: unless-stopped

volumes:
  mongo_rs_data:
~~~

**Configuration notes:**

1. **--replSet rs0** starts mongod in replica set member mode named **rs0**, though **member configuration is not initialized yet**.
2. **--bind_ip_all** lets the process listen on the container network. **ports** binds the port only to the host's loopback address for this lab.
3. **mongo_rs_data** is a named volume storing data files. Removing the container normally does not delete data in the volume.
4. **restart: unless-stopped** restarts the container when Docker starts, though it does not guarantee mongod has become **PRIMARY** the instant the TCP port opens.

**There is no username/password or TLS in this setup.** Use it only in a private, controlled development environment. Never publish the port to **0.0.0.0** on shared machines or deploy this configuration as-is to a publicly reachable server.

### 3.2. Starting the Container

From the folder containing **compose.yaml**:

~~~bash
docker compose up -d
docker compose ps
docker compose logs mongo
~~~

Launch the MongoDB shell directly inside the container:

~~~bash
docker compose exec mongo mongosh
~~~

At this point **mongod** is running with the replica set flag, but it may **not be initiated yet**. The next step should be run once per new data volume.

### 3.3. Initiating the Replica Set

In the newly opened **mongosh** session:

~~~javascript
rs.initiate({
  _id: "rs0",
  members: [
    { _id: 0, host: "localhost:27017" }
  ]
});
~~~

A successful result typically includes **ok: 1**. The replica set takes a brief moment to complete primary election; check status rather than guessing readiness:

~~~javascript
rs.status();
db.hello();
~~~

Expected output:

~~~text
Replica set name: rs0
Single member state: PRIMARY
db.hello().isWritablePrimary: true
~~~

You can check the expressions directly:

~~~javascript
db.hello().setName
db.hello().isWritablePrimary
rs.status().members.map(m => ({
  name: m.name,
  state: m.stateStr
}))
~~~

**Only run rs.initiate on an unconfigured replica set.** If the volume has already been used and **rs.status()** shows a valid replica set, do not re-initiate. If you see an **already initialized** error, inspect the current status rather than deleting data to rerun the command.

### 3.4. Why Must the Hostname Be localhost in This Example?

The MongoDB driver does not connect only to the seed address. With a replica set URI, the driver **discovers topology** and connects to the member addresses advertised by the replica set. In this example, the app runs on the host, so it needs **localhost:27017**, which is reachable from the host.

| Where does the app run? | Usable topology address | Notes |
| --- | --- | --- |
| On the same host machine as Docker | **localhost:27017** | Matches the setup in this guide |
| In another container on the same Compose network | Internal DNS name such as **mongo:27017** | Configure the replica set address resolvable by that client |
| On another machine | Hostname/IP reachable by both client and members | Requires appropriate networking, TLS, and auth |

When moving from host to container, consistently redesign the **advertised hostname** and URI, or use Testcontainers designed for test contexts. **directConnection=true** can help in certain single-node diagnostics, but it is not a general fix for a wrong replica set hostname in a multi-node deployment.

## 4. Preparing the Database and Sample Data Model

### 4.1. Choosing a Realistic Domain Model

The **shop_capstone** database has three collections:

| Collection | Contents | Sample operations |
| --- | --- | --- |
| **customers** | Customer ID, name, email, creation date | Find by email, entity mapping |
| **products** | SKU, product name, price in minor units, stock | Unique index, stock update |
| **orders** | Customer, status, line items, total, creation date | Derived query, aggregation, transaction, change stream |

~~~mermaid
erDiagram
    CUSTOMERS ||--o{ ORDERS : "customerId"
    ORDERS ||--|{ ORDER_ITEMS : "items"
    PRODUCTS ||--o{ ORDER_ITEMS : "productId"
    CUSTOMERS {
        string _id
        string name
        string email
        date createdAt
    }
    PRODUCTS {
        string _id
        string sku
        string name
        long priceCents
        int stock
    }
    ORDERS {
        string _id
        string customerId
        string status
        long totalCents
        date createdAt
    }
    ORDER_ITEMS {
        string productId
        int quantity
        long unitPriceCents
    }
~~~

**The customerId/productId links are ID references in domain data**, not MongoDB-enforced foreign keys. **Order items** are embedded inside the order document. This example stores a **unitPriceCents** snapshot per line item so future product price changes do not mutate totals of existing orders.

To avoid floating-point errors in monetary math, the example uses **NumberLong** in mongosh and **long** in Java. The names **priceCents/unitPriceCents/totalCents** represent counts of the smallest currency unit. The sample dataset uses illustrative integers; when building a real VND system, name the unit appropriately and standardize rounding rules.

### 4.2. Fields and Consistency Rules

- Customer IDs follow **C001**..., emails must be unique.
- Product IDs follow **P001**..., SKUs must be unique.
- Order IDs follow **O1001**..., statuses belong to **PENDING**, **PAID**, **SHIPPED**, **DELIVERED**, **CANCELLED**.
- **totalCents** equals the sum of **quantity × unitPriceCents** across line items; tax, shipping fees, and coupons are not included yet.
- **createdAt** is stored as a **BSON Date** via **ISODate**, corresponding to **Instant** in Java entities.

Database relationships or transactions are not required solely to seed this dataset; each document is inserted/upserted independently. Transactions will be tested once the replica set is active.

## 5. Writing seed.js for Repeatable Data Seeding

To avoid creating duplicate records when running the seed multiple times, use **updateOne** with **$setOnInsert** and **upsert: true** on fixed IDs. Existing records remain untouched; missing records are inserted. This fits an initialization dataset, though it is **not meant to overwrite prices or statuses of already existing records**.

### 5.1. Complete Contents of seed.js

~~~javascript
// seed.js - run in mongosh, no Spring Boot required.
const shop = db.getSiblingDB("shop_capstone");

// Only insert a document if no matching _id exists yet.
function insertMissing(collection, documents) {
  for (const item of documents) {
    const { _id, ...fields } = item;
    collection.updateOne(
      { _id },
      { $setOnInsert: fields },
      { upsert: true }
    );
  }
}

insertMissing(shop.customers, [
  {
    _id: "C001",
    name: "Nguyen Mai",
    email: "mai@example.test",
    createdAt: ISODate("2026-10-01T08:00:00Z")
  },
  {
    _id: "C002",
    name: "Tran Binh",
    email: "binh@example.test",
    createdAt: ISODate("2026-10-02T08:00:00Z")
  },
  {
    _id: "C003",
    name: "Le An",
    email: "an@example.test",
    createdAt: ISODate("2026-10-03T08:00:00Z")
  },
  {
    _id: "C004",
    name: "Pham Linh",
    email: "linh@example.test",
    createdAt: ISODate("2026-10-04T08:00:00Z")
  },
  {
    _id: "C005",
    name: "Vo Khoa",
    email: "khoa@example.test",
    createdAt: ISODate("2026-10-05T08:00:00Z")
  }
]);

insertMissing(shop.products, [
  {
    _id: "P001", sku: "KEY-001",
    name: "Mechanical Keyboard",
    priceCents: NumberLong(1299000), stock: 15
  },
  {
    _id: "P002", sku: "MOU-001",
    name: "Wireless Mouse",
    priceCents: NumberLong(499000), stock: 25
  },
  {
    _id: "P003", sku: "HUB-001",
    name: "USB-C Hub",
    priceCents: NumberLong(799000), stock: 12
  },
  {
    _id: "P004", sku: "STD-001",
    name: "Laptop Stand",
    priceCents: NumberLong(349000), stock: 30
  },
  {
    _id: "P005", sku: "MON-001",
    name: "Monitor 27 inch",
    priceCents: NumberLong(3999000), stock: 8
  },
  {
    _id: "P006", sku: "CAB-001",
    name: "USB-C Cable",
    priceCents: NumberLong(149000), stock: 40
  }
]);

insertMissing(shop.orders, [
  {
    _id: "O1001", customerId: "C001", status: "PAID",
    items: [
      { productId: "P001", quantity: 1,
        unitPriceCents: NumberLong(1299000) },
      { productId: "P002", quantity: 2,
        unitPriceCents: NumberLong(499000) }
    ],
    totalCents: NumberLong(2297000),
    createdAt: ISODate("2026-10-10T09:00:00Z")
  },
  {
    _id: "O1002", customerId: "C002", status: "PENDING",
    items: [
      { productId: "P003", quantity: 1,
        unitPriceCents: NumberLong(799000) }
    ],
    totalCents: NumberLong(799000),
    createdAt: ISODate("2026-10-11T09:00:00Z")
  },
  {
    _id: "O1003", customerId: "C003", status: "SHIPPED",
    items: [
      { productId: "P005", quantity: 1,
        unitPriceCents: NumberLong(3999000) },
      { productId: "P006", quantity: 2,
        unitPriceCents: NumberLong(149000) }
    ],
    totalCents: NumberLong(4297000),
    createdAt: ISODate("2026-10-12T09:00:00Z")
  },
  {
    _id: "O1004", customerId: "C001", status: "CANCELLED",
    items: [
      { productId: "P004", quantity: 2,
        unitPriceCents: NumberLong(349000) }
    ],
    totalCents: NumberLong(698000),
    createdAt: ISODate("2026-10-13T09:00:00Z")
  },
  {
    _id: "O1005", customerId: "C004", status: "PAID",
    items: [
      { productId: "P002", quantity: 1,
        unitPriceCents: NumberLong(499000) },
      { productId: "P003", quantity: 1,
        unitPriceCents: NumberLong(799000) }
    ],
    totalCents: NumberLong(1298000),
    createdAt: ISODate("2026-10-14T09:00:00Z")
  },
  {
    _id: "O1006", customerId: "C005", status: "PENDING",
    items: [
      { productId: "P006", quantity: 3,
        unitPriceCents: NumberLong(149000) }
    ],
    totalCents: NumberLong(447000),
    createdAt: ISODate("2026-10-15T09:00:00Z")
  },
  {
    _id: "O1007", customerId: "C002", status: "PAID",
    items: [
      { productId: "P001", quantity: 1,
        unitPriceCents: NumberLong(1299000) }
    ],
    totalCents: NumberLong(1299000),
    createdAt: ISODate("2026-10-16T09:00:00Z")
  },
  {
    _id: "O1008", customerId: "C003", status: "DELIVERED",
    items: [
      { productId: "P004", quantity: 1,
        unitPriceCents: NumberLong(349000) },
      { productId: "P006", quantity: 1,
        unitPriceCents: NumberLong(149000) }
    ],
    totalCents: NumberLong(498000),
    createdAt: ISODate("2026-10-17T09:00:00Z")
  }
]);

// Unique indexes protecting business keys.
shop.customers.createIndex(
  { email: 1 },
  { unique: true, name: "ux_customers_email" }
);
shop.products.createIndex(
  { sku: 1 },
  { unique: true, name: "ux_products_sku" }
);

// Indexes supporting common query patterns.
shop.orders.createIndex(
  { customerId: 1, createdAt: -1 },
  { name: "ix_orders_customer_created" }
);
shop.orders.createIndex(
  { status: 1, createdAt: -1 },
  { name: "ix_orders_status_created" }
);

printjson({
  database: shop.getName(),
  customers: shop.customers.countDocuments({}),
  products: shop.products.countDocuments({}),
  orders: shop.orders.countDocuments({})
});
~~~

**Why use string _id values?** Codes like **C001**, **P001**, and **O1001** are easy to inspect visually. Spring Data MongoDB can convert String **@Id** values that resemble valid ObjectIds into BSON ObjectIds; the codes in this lesson do not have that format, so they are stored as Strings. If a real application uses ObjectIds, align the BSON and Java types explicitly rather than inferring from this exercise's ID format.

### 5.2. Running the Seed File

Inside the **mongo-capstone** directory:

~~~bash
# Copy the file from host into the container filesystem.
docker compose cp ./seed.js mongo:/tmp/seed.js

# Execute via mongosh inside the container.
docker compose exec mongo mongosh /tmp/seed.js
~~~

Using **docker compose cp** avoids differences in input redirection syntax between Bash and Windows PowerShell. Copying the file into the container is just for running the seed; actual data lives in the MongoDB volume.

Expected output after the first run:

~~~text
{
  database: 'shop_capstone',
  customers: 5,
  products: 6,
  orders: 8
}
~~~

Rerunning the same seed file will **not create additional documents** with duplicate IDs. However, if you have created extra customers, products, or orders during practice, counts may exceed those values. Distinguish between a **freshly seeded environment** and a modified one.

**Do not put dropDatabase() in routine seed scripts.** When you want to start fresh, use a dedicated practice volume and make sure you understand that deleting a volume destroys its data.

## 6. Verifying Sample Data with mongosh

Open the shell:

~~~bash
docker compose exec mongo mongosh
~~~

Select the database:

~~~javascript
use shop_capstone

db.customers.countDocuments({})
db.products.countDocuments({})
db.orders.countDocuments({})
~~~

In a freshly seeded environment, the counts are:

~~~text
5
6
8
~~~

### 6.1. Querying an Order and Checking Totals

~~~javascript
db.orders.findOne({ _id: "O1001" });
~~~

Order **O1001** has one keyboard at **1,299,000** and two mice at **499,000**:

~~~text
1 × 1,299,000 + 2 × 499,000 = 2,297,000
~~~

Verify totals across **all** orders with aggregation:

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      totalCents: 1,
      calculatedCents: {
        $sum: {
          $map: {
            input: "$items",
            as: "line",
            in: {
              $multiply: [
                "$$line.quantity",
                "$$line.unitPriceCents"
              ]
            }
          }
        }
      }
    }
  },
  {
    $match: {
      $expr: { $ne: ["$totalCents", "$calculatedCents"] }
    }
  }
]);
~~~

If the sample dataset has not been modified, the query above must return **zero documents**: every order total matches its line items. This validates business data consistency, not just document counts.

### 6.2. Summarizing Order Counts and Totals by Status

~~~javascript
db.orders.aggregate([
  {
    $group: {
      _id: "$status",
      orderCount: { $sum: 1 },
      amountCents: { $sum: "$totalCents" }
    }
  },
  { $sort: { _id: 1 } }
]);
~~~

Expected result:

| Status | Orders | Total amountCents |
| --- | ---: | ---: |
| **CANCELLED** | 1 | 698000 |
| **DELIVERED** | 1 | 498000 |
| **PAID** | 3 | 4894000 |
| **PENDING** | 2 | 1246000 |
| **SHIPPED** | 1 | 4297000 |
| **All** | **8** | **11633000** |

**Total amountCents** in this table sums order values per status and is **not accounting revenue**: CANCELLED/PENDING orders and potentially uncompleted orders are not counted as realized revenue.

### 6.3. Inspecting Indexes

~~~javascript
db.customers.getIndexes();
db.products.getIndexes();
db.orders.getIndexes();

db.orders.find({ customerId: "C001" })
  .sort({ createdAt: -1 })
  .explain("executionStats");
~~~

Expect **orders** to have **ix_orders_customer_created** and **ix_orders_status_created** in addition to the default **_id** index. In the explain output, inspect **winning plan**, **totalDocsExamined**, and **nReturned** to see which plan the query actually selected.

With only eight sample orders, MongoDB may choose a collection scan for some queries because the cost is negligible. **Do not assume an index is used merely because it exists**; read explain output on a realistic dataset.

## 7. Connecting from Spring Data MongoDB

### 7.1. Host Machine Connection String

With Spring Boot 3.x, sample configuration in **application.yml**:

~~~yaml
spring:
  data:
    mongodb:
      uri: "mongodb://localhost:27017/shop_capstone?replicaSet=rs0"
~~~

**replicaSet=rs0** instructs the driver to discover the corresponding topology. The URI uses **shop_capstone** as the application's default database. If using a Spring Boot version with changed MongoDB property names, check the configuration properties documentation for that exact version rather than copying YAML verbatim.

### 7.2. Declaring Java Documents

You can place each type in its own file within your application package:

~~~java
// Customer.java
import java.time.Instant;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document("customers")
public record Customer(
    @Id String id,
    String name,
    String email,
    Instant createdAt
) {}
~~~

~~~java
// Product.java
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document("products")
public record Product(
    @Id String id,
    String sku,
    String name,
    long priceCents,
    int stock
) {}
~~~

~~~java
// OrderLine.java
public record OrderLine(
    String productId,
    int quantity,
    long unitPriceCents
) {}
~~~

~~~java
// ShopOrder.java
import java.time.Instant;
import java.util.List;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document("orders")
public record ShopOrder(
    @Id String id,
    String customerId,
    String status,
    List<OrderLine> items,
    long totalCents,
    Instant createdAt
) {}
~~~

The **class name ShopOrder** avoids collisions with **Order** in other libraries. Seeded documents lack a **_class** field, yet because the repository specifies the concrete target type **ShopOrder**, the data still maps by matching fields. When writing new documents via Spring Data, the default converter may add **_class**; keep this in mind if multiple applications share the BSON schema.

### 7.3. Repositories and Queries

~~~java
// ShopOrderRepository.java
import java.util.List;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface ShopOrderRepository
        extends MongoRepository<ShopOrder, String> {

    List<ShopOrder> findByCustomerIdOrderByCreatedAtDesc(
        String customerId
    );

    long countByStatus(String status);
}
~~~

~~~java
// ShopQueryService.java
import java.util.List;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.stereotype.Service;

@Service
public class ShopQueryService {
    private final ShopOrderRepository orders;
    private final MongoTemplate mongoTemplate;

    public ShopQueryService(
        ShopOrderRepository orders,
        MongoTemplate mongoTemplate
    ) {
        this.orders = orders;
        this.mongoTemplate = mongoTemplate;
    }

    public List<ShopOrder> ordersOfCustomer(String customerId) {
        return orders.findByCustomerIdOrderByCreatedAtDesc(customerId);
    }

    public List<ShopOrder> paidOrders() {
        Query query = Query.query(
            Criteria.where("status").is("PAID")
        );
        return mongoTemplate.find(query, ShopOrder.class);
    }
}
~~~

Both query approaches target the same database and collection. **MongoRepository** is convenient for derived queries, while **MongoTemplate** is useful when building custom filters, aggregations, updates, or transactions.

### 7.4. Testing Reads Against Seeded Data

In a Spring Boot project with **spring-boot-starter-data-mongodb** and **spring-boot-starter-test**, you can write an integration test:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;

@DataMongoTest
class SampleDataIntegrationTest {

    @Autowired
    ShopOrderRepository repository;

    @Test
    void canReadSeededOrderAndLines() {
        ShopOrder order =
            repository.findById("O1001").orElseThrow();

        assertEquals("C001", order.customerId());
        assertEquals("PAID", order.status());
        assertEquals(2, order.items().size());
        assertEquals(2_297_000L, order.totalCents());
    }

    @Test
    void canReadAllPaidOrders() {
        assertEquals(3L, repository.countByStatus("PAID"));
    }
}
~~~

**This is a conditional integration test:** before running, the MongoDB replica set and matching seed data must exist, and the Spring context must be configured to connect to **shop_capstone**. **@DataMongoTest** configures the MongoDB slice under test, but does not automatically seed sample data or start the server. If your project uses Boot 4.x, the slice test annotation package may have changed; follow the API of your version.

Because this test reads seeded data from a shared database, **do not run it in parallel with exercises that modify orders**. To run independently in CI, spin up a dedicated test database and seed automatically before tests, or use Testcontainers with an appropriate replica set.

## 8. Verifying Transaction Capability with mongosh

A replica set can report **PRIMARY** while the application service configuration is still wrong. Before writing complex services, run a small smoke test to confirm MongoDB transaction support.

### 8.1. Prepare the Collection Outside the Transaction

In **mongosh**:

~~~javascript
const shop = db.getSiblingDB("shop_capstone");
if (!shop.getCollectionNames().includes("tx_probe")) {
  shop.createCollection("tx_probe");
}
~~~

Creating the collection upfront keeps the test focused on rollback semantics rather than version-dependent implicit collection creation inside transactions.

### 8.2. Write and Abort

~~~javascript
const probeId = "TX-" + new ObjectId().toString();
const session = db.getMongo().startSession();

try {
  session.startTransaction();
  session.getDatabase("shop_capstone")
    .getCollection("tx_probe")
    .insertOne({
      _id: probeId,
      kind: "ROLLBACK_CHECK",
      at: new Date()
    });

  session.abortTransaction();
} finally {
  session.endSession();
}

shop.tx_probe.countDocuments({ _id: probeId });
~~~

The expected result is **0**, because the document inserted inside the transaction was aborted. This is a MongoDB server smoke test; it **does not yet verify @Transactional in Spring**. For imperative Spring Data MongoDB, configure **MongoTransactionManager** and test the service through a Spring proxy. For reactive access, configure **ReactiveMongoTransactionManager** and test within a reactive transaction context.

For thorough testing, write two separate cases: a **successful commit** making multiple documents appear together, and a **runtime failure** rolling back all operations in the transaction. Do not merely assert that the transaction did not throw an exception.

## 9. Verifying Change Streams with Two mongosh Windows

A change stream requires a subscriber/cursor **actively watching before changes are written**. If you insert first and call watch afterward, the test may miss the event that already happened.

### 9.1. Window A: Open the Stream

Open mongosh:

~~~bash
docker compose exec mongo mongosh
~~~

Run:

~~~javascript
const shop = db.getSiblingDB("shop_capstone");
if (!shop.getCollectionNames().includes("stream_probe")) {
  shop.createCollection("stream_probe");
}

const stream = shop.stream_probe.watch([
  { $match: { operationType: "insert" } }
]);

while (stream.hasNext()) {
  printjson(stream.next());
}
~~~

**The loop will wait for events**. Keep Window A open while performing the next step.

### 9.2. Window B: Create a New Change

Open a second mongosh session and run:

~~~javascript
db.getSiblingDB("shop_capstone")
  .getCollection("stream_probe")
  .insertOne({
    _id: "EV-" + new ObjectId().toString(),
    kind: "REPLICA_CHECK",
    createdAt: new Date()
  });
~~~

Switch back to Window A. Expect an event with **operationType = "insert"**, **ns.coll = "stream_probe"**, and **fullDocument.kind = "REPLICA_CHECK"**. The event's **_id** field holds the **resume token**, which differs from **fullDocument._id**. Stop the loop in Window A with **Ctrl+C**.

When using **ReactiveMongoTemplate.changeStream(...)** or **ChangeStreamOptions**, ensure there is an active subscription and the stream is open before writing. An unsubscribed **Flux** variable is not automatically receiving events. In automated tests, use bounded timeouts, filter by document ID, and close cursors/subscriptions.

## 10. Application-Level Verification Checklist for Sample Data

When combining multiple parts of the module, create a data-verification check before building complex transactions or aggregations:

| Condition | Query / verification API | Expectation after initial seed |
| --- | --- | --- |
| Server is an initialized replica set | **rs.status()** | Set **rs0**, one **PRIMARY** member |
| Server accepts writes | **db.hello().isWritablePrimary** | **true** |
| Customers seeded | **customers.countDocuments({})** | **5** |
| Products seeded | **products.countDocuments({})** | **6** |
| Orders seeded | **orders.countDocuments({})** | **8** |
| PAID order count | **orders.countDocuments({status:"PAID"})** | **3** |
| Total value across all orders | Aggregation **$group/$sum** | **11633000** |
| No order has mismatched total | Compare totalCents against line items | **0 mismatched documents** |
| Entity mapping works | **findById("O1001")** | **totalCents = 2297000**, 2 items |
| Transaction abort works | **tx_probe** by probeId | **0 documents** |
| Change stream works | Stream receives insert event | One **REPLICA_CHECK** event |

**Interpreting results:** if document counts are low, check the seed step first. If mongosh reads data properly but Spring does not, check the database name in the URI, **@Document/@Id** mappings, field types, or converters. If regular queries work while transactions or change streams fail, check topology and session configuration first.

## 11. Common Errors and Troubleshooting

| Symptom | Common cause | Verification / fix |
| --- | --- | --- |
| **Connection refused** to localhost:27017 | Container not running, port not published, or port taken by another process | **docker compose ps**, **docker compose logs mongo**, check port binding |
| **ReplicaSetNoPrimary** or server selection timeout | Not initiated, PRIMARY not elected yet, wrong replica set name, or advertised hostname unreachable | **rs.status()**, **db.hello()**, check URI and hostname |
| Driver receives **mongo:27017** while app runs on host | Docker DNS name does not resolve on host | Configure topology with addresses the client can actually reach |
| App inside container connects to **localhost:27017** | localhost inside app container refers to the app container itself | Redesign networking/replica set hostname; do not reuse host URI verbatim |
| **Transaction numbers are only allowed on a replica set member or mongos** | App connects to standalone instance or wrong deployment | Check URI and actual replica set state |
| **$changeStream is only supported on replica sets** | MongoDB not running in a change-stream-capable topology | Check **--replSet**, **rs.initiate**, and server status |
| Re-running seed does not overwrite edited data | **$setOnInsert** only inserts missing documents | Intended behavior; do not confuse with overwrite/migration |
| **DuplicateKey** on email or SKU | Duplicate unique value already exists under a different ID | Inspect collection, legacy data, and indexes before inserting |
| Seed ran but Spring sees 0 orders | URI points to another database or wrong replica set | Compare **shop_capstone** in URI with **db.getName()** |
| Spring reads wrong date/money types | Seeded BSON types differ from Java or inconsistent custom converters | Inspect raw documents, **ISODate/NumberLong**, and entity mapping |
| Transaction test still sees document after error | Missing transaction manager, self-invocation, or write outside transaction | Check **MongoTransactionManager**, proxy/session, and MongoDB state |
| Change stream misses events | Started watching after write or cursor/subscriber not ready | Start observer first; use two windows and a deadline |
| **docker compose cp** cannot find service | Wrong Compose folder, service stopped, or different service name | Run from folder containing **compose.yaml**, check **docker compose ps** |
| Other tests alter data counts | Shared database across lessons, unreset seed | Use isolated test database/volume and standardize cleanup |

### 11.1. What to Check in Logs?

~~~bash
docker compose ps
docker compose logs mongo
docker compose exec mongo mongosh
~~~

In mongosh:

~~~javascript
rs.status();
db.hello();
db.getSiblingDB("shop_capstone").orders.countDocuments({});
~~~

Do not assume the replica set is ready just because **docker compose ps** shows the container running. The **PRIMARY** state is essential for write and transaction labs.

### 11.2. Want to Use a Hostname Other Than localhost?

Ensure the address in **rs.conf()** can be resolved and reached by all relevant clients. Across multiple containers, you can use a service name on a shared Docker network; from external hosts, use proper DNS/routing. Changing a replica set hostname via **rs.reconfig()** alters topology and must follow the documentation for your exact MongoDB version—never experiment casually on important data.

## 12. Cleaning Up, Restarting, and Preserving Data

When finishing a study session:

~~~bash
# Stop and remove containers/networks created by Compose.
docker compose down
~~~

A regular **docker compose down** **preserves the named volume**. So when starting again:

~~~bash
docker compose up -d
~~~

MongoDB reloads data and replica set configuration from the volume. **You do not need to run rs.initiate again** as long as the existing volume remains intact and valid.

If you want to wipe **all exercise data** and reinitialize from scratch, an action such as **docker compose down -v** deletes the project's named volume and all MongoDB data inside it. Use this only on a volume **dedicated to the lab**, after confirming it holds no data you need to keep. This is a destructive operation, not a required step of the exercise.

In CI pipelines, use an isolated database and container per job, seed automatically, and tear down at the end. For production, require authentication, TLS, backups, monitoring, and a multi-member replica set per availability requirements; never deploy this learning Compose file as-is.

## 13. Extension Exercises After Completing the Environment

### Exercise A — Derived Queries and Indexes

Write a repository method to fetch orders for customer **C001** sorted by **createdAt** descending. Expect two orders: **O1004** then **O1001**. Use **explain** to inspect the query plan and index usage; do not force the assumption that an eight-document dataset will always use an index.

### Exercise B — Aggregation by Customer

Build a pipeline grouping orders by **customerId**, counting orders and summing totals; then **$lookup** into customers to return the customer name. Verify **C001** has 2 orders and a combined amount of **2995000**.

### Exercise C — Transaction Updating Inventory

Write a service using **MongoTransactionManager** to create a new order and decrement product stock together. Inspect stock before and after commit; trigger a failure to prove rollback leaves no dangling order. For production, design **conditional updates** to prevent overselling under concurrent requests.

### Exercise D — Change Stream and Consumer

Write a consumer listening for inserts on **orders**. Insert a new order via MongoTemplate; verify the consumer receives the event with the matching ID. Add **resume token** checkpointing or idempotent processing to practice consumer restarts.

### Exercise E — Reactive Access

If your application uses **ReactiveMongoTemplate** or **ReactiveMongoRepository**, build an endpoint returning **Flux<ShopOrder>** for PAID orders and test it with **StepVerifier**. The reactive stack connects to the same server but uses the reactive MongoDB driver and reactive APIs; do not mix an imperative transaction manager into a reactive flow.

## 14. Acceptance Checklist

Check off each item after running it in your actual environment:

- [ ] MongoDB container starts cleanly from **compose.yaml**.
- [ ] **rs.status()** shows replica set **rs0** with one **PRIMARY**.
- [ ] **db.hello().isWritablePrimary** returns **true**.
- [ ] **seed.js** runs cleanly and rerunning does not duplicate data.
- [ ] Database **shop_capstone** has **5 customers**, **6 products**, and **8 orders** in a freshly seeded environment.
- [ ] Unique indexes and lookup indexes on **orders** exist.
- [ ] Total-amount verification aggregation finds no mismatched orders.
- [ ] Total value across all orders is **11633000**; there are **3 PAID orders**.
- [ ] Spring Data MongoDB reads order **O1001** via both repository and MongoTemplate.
- [ ] Transaction smoke test after **abort** leaves zero probe documents.
- [ ] Change stream receives the insert event when the watcher opens before the write.
- [ ] URI, MongoDB version, and any configuration pitfalls are documented for reproducibility.

## Conclusion

A **single-node replica set** environment is sufficient for many Spring Data MongoDB capstone labs, from document mapping and repository queries to verifying **transactions** and **change streams**. The decisive factors are that the server has become **PRIMARY**, the URI matches the hostname advertised by the replica set, and the seed dataset is verifiable and idempotent. With **customers, products, and orders** loaded, you have a solid base to continue practicing **MongoTemplate**, aggregation, indexing, transactions, reactive access, testing, and performance diagnostics with concrete data scenarios.

### References

- [MongoDB — Deploy a Replica Set](https://www.mongodb.com/docs/manual/tutorial/deploy-replica-set/)
- [MongoDB — rs.initiate()](https://www.mongodb.com/docs/manual/reference/method/rs.initiate/)
- [MongoDB — Transactions](https://www.mongodb.com/docs/manual/core/transactions/)
- [MongoDB — Change Streams](https://www.mongodb.com/docs/manual/changeStreams/)
- [Spring Data MongoDB — Reference](https://docs.spring.io/spring-data/mongodb/reference/)
- [Docker Compose — Overview](https://docs.docker.com/compose/)
