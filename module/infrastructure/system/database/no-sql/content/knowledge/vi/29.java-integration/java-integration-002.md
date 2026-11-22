# Phân biệt driver gốc, lớp ánh xạ dữ liệu, Spring Data và JDBC khi có

## 1. Vì sao cùng một NoSQL nhưng Java có nhiều cách kết nối?

Khi một ứng dụng Java sử dụng MongoDB, Cassandra, Redis, DynamoDB, Elasticsearch, Neo4j hoặc một NoSQL khác, người học thường gặp nhiều lựa chọn:

- **Java driver / SDK gốc** do nhà cung cấp hoặc cộng đồng duy trì;
- **Lớp ánh xạ dữ liệu (data mapping, object mapping, mapper)** biến dữ liệu trong database thành object Java;
- **Spring Data** với `Repository`, `Template`/`Operations`, annotations và tích hợp Spring;
- **JDBC** nếu database cung cấp một driver JDBC hoặc một giao diện SQL tương thích.

Các lựa chọn này **không nhất thiết là bốn công nghệ thay thế trực tiếp cho nhau**. Chúng thường là **những tầng khác nhau của cùng đường truy cập dữ liệu**.

Ví dụ, một ứng dụng Spring Boot dùng `MongoRepository<Customer, String>` vẫn có driver MongoDB Java ở phía dưới. Một class dùng `MongoTemplate` có thể ánh xạ object qua `MappingMongoConverter`. Một công cụ BI dùng JDBC tới SQL endpoint của một hệ NoSQL có thể không đi qua Spring Data và thậm chí không dùng cùng giao thức như driver gốc.

### 1.1. Câu hỏi cần trả lời

1. Tầng nào thực sự mở kết nối và gửi request?
2. Tầng nào chuyển `Document`, row, key-value hoặc JSON thành POJO?
3. Tầng nào sinh câu truy vấn và quản lý lifecycle qua Spring?
4. Tầng nào hỗ trợ tính năng đặc thù: partition key, aggregation, TTL, consistency, vector search, change streams?
5. Khi ứng dụng cần transaction, driver/API có hỗ trợ đúng phạm vi không?
6. Khi xuất hiện JDBC, nó đang gọi SQL server thật, SQL gateway hay một lớp chuyển dịch?
7. Khi cần hiệu năng, có nên bỏ `Repository` để dùng driver gốc không?
8. Các loại API synchronous, asynchronous và reactive khác nhau ở đâu?

**Mục tiêu:** lựa chọn tầng tích hợp theo access pattern và yêu cầu sản phẩm, không theo cảm giác “framework cao hơn thì luôn tốt hơn”.

## 2. Sơ đồ các tầng kết nối Java

Một kiến trúc thường gặp:

```text
                    Business Service
                          |
         +----------------+----------------+
         |                |                |
         v                v                v
  Spring Data Repo   Template/Operations  Native SDK API
         |                |                |
         +--------+-------+                |
                  |                        |
                  v                        |
          Mapping/Conversion               |
                  |                        |
                  +-----------+------------+
                              |
                              v
                    Native Driver / SDK
                              |
                    Pool / Sessions / Codec
                              |
                              v
                        NoSQL Server
```

Một đường JDBC riêng:

```text
Java application / BI Tool
          |
          v
JDBC API: Connection / PreparedStatement / ResultSet
          |
          v
Vendor JDBC driver / SQL bridge
          |
          v
NoSQL SQL endpoint, query service hoặc translator
          |
          v
Underlying NoSQL storage/query engine
```

Lưu ý:

- Native SDK có thể **tích hợp mapper riêng**.
- Spring Data có nhiều module; không phải module nào cũng có mọi abstraction hoặc cùng mức hỗ trợ.
- Một số sản phẩm cung cấp JDBC bên cạnh native driver, nhưng JDBC chỉ có ý nghĩa trong **phạm vi SQL/query service của sản phẩm ấy**.
- Không phải NoSQL nào cũng có SQL/JDBC chính thức; không nên cố sử dụng một JDBC driver bất kỳ chỉ vì muốn giữ API quen thuộc.

## 3. Driver gốc là gì?

**Native driver** là thư viện Java giao tiếp trực tiếp với giao thức/API chính thức của hệ NoSQL, thường có các chức năng:

- Quản lý kết nối, endpoint, authentication và TLS;
- Serialize/deserialize dữ liệu theo wire format;
- Gửi và nhận lệnh đọc/ghi;
- Thực thi query, paging hoặc cursor;
- Timeout, retries, routing và topology discovery;
- Cấu hình read/write consistency hay write concern nếu có;
- Session/transaction theo API native;
- Expose error codes và metadata đặc thù.

Một số ví dụ:

| Hệ thống | Giao diện Java gốc thường gặp | Ngôn ngữ/tính năng |
|---|---|---|
| MongoDB | MongoDB Java Driver | BSON, find/aggregate, sessions, change streams |
| Cassandra | Apache Cassandra Java Driver / nhánh driver tương thích | CQL, prepared statements, token-aware routing |
| Redis | Lettuce hoặc Jedis | Redis commands, pipeline, pub/sub, scripts |
| DynamoDB | AWS SDK for Java v2 | Item APIs, condition expressions, transactions, streams |
| Elasticsearch | Elasticsearch Java API Client | JSON DSL, search, bulk, aggregations |
| OpenSearch | OpenSearch Java client/SDK thích hợp | Search DSL, index, bulk; khác biệt phiên bản |
| Neo4j | Neo4j Java Driver | Cypher, sessions, managed transactions |
| Couchbase | Couchbase Java SDK | KV, SQL++/query, CAS, scopes/collections |
| HBase | HBase Java Client | Get/Put/Scan, filters, families |
| Cosmos DB | Azure Cosmos DB Java SDK | Container/item, partition key, request options |

Tên package và API thay đổi theo phiên bản. Khi viết code thực tế, chọn **driver tương thích với server/service**, kiểm tra support matrix và tài liệu cho phiên bản đang dùng.

### 3.1. “Native” không có nghĩa mọi request đều đi thẳng tới một node

Một driver có thể:

- Dùng DNS/seed hosts để khám phá topology;
- Route theo partition key hoặc token;
- Chọn read replica theo chính sách;
- Tự thực hiện server selection;
- Dùng HTTP transport tới một managed service;
- Gửi câu query đến coordinator;
- Retry khi gặp lỗi transient.

Native nghĩa là dùng **API đặc thù/hợp đồng chính thức**, không phải “tự mở socket tới đúng một node”.

### 3.2. Khi nên ưu tiên driver gốc

- Cần tính năng mới chưa có abstraction trong Spring Data;
- Cần điều khiển trực tiếp query/paging, batches, sessions, hints hoặc consistency;
- Viết thư viện hạ tầng không phụ thuộc Spring;
- Cần pipeline/bulk ingestion tối ưu;
- Cần dùng async APIs với điều khiển chi tiết;
- Cần đọc mã lỗi/cấu trúc response đặc thù;
- Muốn tránh một số giới hạn mapping của framework.

### 3.3. Đánh đổi

- Nhiều boilerplate mapping và lifecycle;
- Phải tự thống nhất error handling;
- Khó chuẩn hóa model conversions trên nhiều modules;
- Dễ nhúng truy vấn hạ tầng vào business code;
- Unit testing có thể cần adapter/fake rõ;
- Đội Java phải hiểu API của từng database.

**Driver gốc cho nhiều quyền kiểm soát; không tự đồng nghĩa mã luôn nhanh hơn hoặc an toàn hơn.**

## 4. Native driver và SDK có khác nhau không?

Trong thực tế, tài liệu dùng hai từ tương đối linh hoạt.

- **Driver:** thường nhấn mạnh giao thức/kết nối, query và serialization.
- **SDK:** thường là gói API rộng hơn, có request builders, credentials, retry strategy, enhanced client, pagination và dịch vụ liên quan.

Ví dụ AWS SDK cho DynamoDB không nên bị mô tả như một JDBC driver. Nó gọi **DynamoDB service API**, có request models và options riêng.

### 4.1. Đừng trộn APIs chỉ vì cùng là Java

```text
MongoDB Driver:
  collection.find(filter)

DynamoDB SDK:
  client.getItem(request)

Redis commands:
  commands.get(key)

Cassandra Driver:
  session.execute(preparedStatement)

Neo4j Driver:
  session.run(cypherQuery)
```

Mỗi API biểu diễn **mô hình dữ liệu và đường truy cập khác nhau**. Một abstraction Java thống nhất mọi NoSQL đôi khi sẽ che những khác biệt quyết định hiệu năng và correctness.

## 5. Lớp ánh xạ dữ liệu là gì?

**Data mapping** chuyển giữa dữ liệu lưu trữ và object Java.

Ví dụ một document:

```json
{
  "_id": "U42",
  "displayName": "An",
  "address": {
    "city": "Hà Nội",
    "country": "VN"
  },
  "createdAt": "2026-11-14T08:30:00Z"
}
```

Model Java:

```java
import java.time.Instant;

public record Customer(
        String id,
        String displayName,
        Address address,
        Instant createdAt
) {
    public record Address(
            String city,
            String country
    ) {}
}
```

Một mapper xử lý:

```text
BSON/JSON/Row
     |
     v
Field/Type Conversion
     |
     v
Customer object
```

### 5.1. Những việc mapper có thể làm

- Tên field: `_id` ↔ `id`;
- Giá trị null và field thiếu;
- Object lồng nhau hoặc collection;
- Ngày/giờ với `Instant`, `LocalDate`, timezone;
- Enum, UUID, BigDecimal, binary;
- ID kiểu `ObjectId`, `String`, `UUID`;
- Custom converters/serializers;
- Polymorphic types và type discriminator;
- Constructor binding/records;
- Version metadata;
- Mapping quan hệ giữa các entities nếu framework hỗ trợ.

### 5.2. Mapper không thay query engine

Nếu database thiếu index cho access pattern, mapper không tạo đường truy cập tối ưu một cách thần kỳ. Nó chủ yếu xử lý **biểu diễn dữ liệu**, đôi khi được tích hợp với query builder.

### 5.3. Một mapper có thể tồn tại mà không có Spring

Native MongoDB driver có POJO codec; DynamoDB Enhanced Client có bean/table schema mapping; Jackson có thể ánh xạ JSON; Couchbase SDK hỗ trợ serialization.

Do vậy **“mapping” không đồng nghĩa “Spring Data”**.

## 6. Mapping khác ORM theo quan niệm quan hệ

**ORM** thường gắn với mô hình relational như JPA/Hibernate: entity lifecycle, persistence context, quan hệ bảng, lazy loading, dirty checking và SQL generation.

Một **NoSQL data mapper** có thể ánh xạ POJO sang document/row/key nhưng **không nhất thiết có** những semantics trên.

Ví dụ:

- MongoDB document embedding khác SQL JOIN.
- Cassandra partition/clustering keys không phải foreign keys.
- Redis key-value không tự có relationship traversal.
- DynamoDB một item với access patterns/GSI không giống một bảng chuẩn hóa.
- Neo4j graph relationships có semantics riêng, không phải JPA `@OneToMany` theo relational database.

### 6.1. Đừng giả định lazy loading

Nếu một Spring Data MongoDB entity có trường `orders`, không được mặc định truy cập `customer.getOrders()` sẽ sinh một JOIN tối ưu hoặc tự load vô điều kiện như JPA.

### 6.2. Đừng giả định transaction xuyên entity

Việc hai POJO được lưu bởi cùng mapper không bảo đảm thao tác trên chúng là một atomic transaction. Transaction scope do **NoSQL engine và API** quyết định.

### 6.3. “Object graph” khác “storage graph”

Một object Java có nested objects có thể được embed thành một MongoDB document, split thành nhiều items hoặc lưu dưới dạng graph nodes; mapper phải phù hợp với truy vấn và invariant.

## 7. Những vấn đề mapping phải thiết kế trước

### 7.1. ID types

MongoDB `_id` có thể là BSON ObjectId hoặc chuỗi. DynamoDB partition/sort key có kiểu nhất định. Cassandra primary key có composite partition+clustering keys.

Không nên tự chuyển tất cả thành `Long` auto-increment như relational nếu mô hình không hỗ trợ hoặc tạo điểm nóng.

### 7.2. Tên field

```java
private String displayName;
```

có thể ánh xạ sang `display_name` hoặc `displayName`. Nên có quy ước nhất quán và migration strategy.

### 7.3. `null` khác field không tồn tại

Trong document databases, một field thiếu, field có giá trị `null` và trường đang có giá trị cụ thể có thể tương tác khác nhau với query/index/update.

Ví dụ patch:

```json
{"phone": null}
```

có thể được hiểu là “xóa số điện thoại”, “gán null” hoặc “không cập nhật” tùy API/schema. Không để mapper tự chọn ngữ nghĩa nghiệp vụ mơ hồ.

### 7.4. Dates và timezone

Lưu thời điểm tuyệt đối bằng `Instant`/epoch với unit rõ. `LocalDateTime` không mang timezone; mapper và driver có thể áp dụng conversion gây sai nếu cấu hình không nhất quán.

### 7.5. Numeric precision

Tiền nên dùng minor units (`long amountMinor`) hoặc decimal type phù hợp. Không tự dùng `double` rồi mong serializer giữ số tiền chính xác.

### 7.6. Unknown fields

Schema evolution có thể tạo documents chứa fields model cũ không biết. Cần xác định bỏ qua, giữ lại hay từ chối, nhất là khi full-document replacement có nguy cơ làm mất dữ liệu mới.

### 7.7. Type metadata

Framework có thể lưu discriminator metadata để tái dựng polymorphic types. Cần kiểm soát để không lộ Java class names không cần thiết hoặc tạo rủi ro khi đổi package.

## 8. Spring Data là gì trong bối cảnh NoSQL?

**Spring Data** là họ dự án tích hợp truy cập dữ liệu với Spring, cung cấp các abstraction có khả năng khác nhau theo module.

Thường bao gồm:

- Mapping và converters;
- `Repository` interfaces;
- `Template`/`Operations` cho thao tác linh hoạt;
- Query derivation hoặc `@Query`;
- Auditing, pagination/sorting;
- Exceptions translation;
- Tích hợp transactions khi database và module hỗ trợ;
- Reactive variants cho một số modules.

Các module NoSQL phổ biến gồm:

- Spring Data MongoDB;
- Spring Data Redis;
- Spring Data Cassandra;
- Spring Data Elasticsearch;
- Spring Data Neo4j;
- Spring Data Couchbase.

**Không có nghĩa tất cả sản phẩm NoSQL đều có một Spring Data module chính thức, và mọi module có cùng feature set.** DynamoDB thường dùng AWS SDK/Enhanced Client hoặc integrations bên thứ ba, không nên giả định `spring-boot-starter-data-dynamodb` là một Spring Data core starter phổ quát.

### 8.1. Spring Data thường dùng driver bên dưới

```text
Spring Boot Service
       |
       v
MongoRepository / MongoTemplate
       |
       v
MappingMongoConverter
       |
       v
MongoDB Java Driver
       |
       v
MongoDB
```

Dùng `MongoRepository` **không bỏ đi driver**; framework dựa trên driver và mapping infrastructure.

### 8.2. Spring Boot khác Spring Data

- **Spring Boot:** cấu hình tự động, starters, application lifecycle, configuration.
- **Spring Data:** APIs và infrastructure để truy cập database.
- **Native driver:** giao tiếp tới database.

Spring Boot có thể tự cấu hình MongoClient nhưng business code vẫn có thể dùng driver gốc, template hoặc repository.

## 9. Repository trong Spring Data

Repository che bớt boilerplate cho các thao tác theo entity/aggregate.

Ví dụ ý tưởng:

```java
interface CustomerRepository
        extends MongoRepository<Customer, String> {

    Optional<Customer> findByEmail(String email);

    List<Customer> findByStatus(String status);
}
```

Framework có thể suy query từ method name hoặc từ `@Query`, tùy module.

### 9.1. Ưu điểm

- CRUD đơn giản nhanh;
- Code theo domain repository;
- Test service có thể mock repository interface;
- Pagination/sorting được tích hợp ở mức phù hợp;
- Tập trung model/converters;
- Ít lặp lại query builder trong business code.

### 9.2. Giới hạn

- Derived methods có thể không biểu diễn hết aggregation/geo/vector query;
- Dễ không nhìn ra query plan thực tế;
- Một method `findByXAndY` vẫn cần index đúng;
- Một save toàn document có thể tạo lost update nếu không có version;
- Semantics transaction/consistency không tự mạnh hơn native database;
- Repository abstraction có thể bỏ qua knobs hiệu năng đặc thù.

### 9.3. Repository không phải network cache

`findById()` vẫn có thể tạo database request. Không mặc định có JPA-style first-level cache hoặc lazy relationship semantics.

## 10. Template/Operations trong Spring Data

`MongoTemplate`, `RedisTemplate`, `CassandraTemplate`, `ElasticsearchOperations` và APIs tương ứng cho phép thao tác linh hoạt hơn một repository CRUD.

Ví dụ tư duy:

```text
Repository:
  findByEmail(email)

MongoTemplate:
  Query + Criteria + Update + FindAndModify

Native driver:
  collection.findOneAndUpdate(BsonFilter, BsonUpdate, Options)
```

### 10.1. Khi dùng Template

- Query động với nhiều điều kiện;
- Conditional update;
- Aggregation;
- Bulk operations;
- Projection;
- Query tuning hoặc options module hỗ trợ;
- Cần mapping POJO nhưng không muốn viết repository method phức tạp.

### 10.2. Template không luôn expose mọi tính năng native

Nếu Spring Data module chưa hỗ trợ một server feature, có thể lấy native client/driver và gọi trực tiếp qua một adapter. Không cần bỏ toàn bộ Spring Data.

### 10.3. Một service có thể dùng nhiều tầng

Một thiết kế thực tế:

```text
CustomerRepository        -> CRUD
MongoTemplate             -> dynamic queries
MongoClient               -> new native feature / custom command
```

Điều quan trọng là cùng hiểu transactions, sessions, converters và consistency khi trộn API.

## 11. JDBC là gì và vì sao NoSQL đôi khi có JDBC?

**JDBC (Java Database Connectivity)** là API Java chuẩn cho truy cập dữ liệu theo mô hình:

```java
Connection
PreparedStatement
ResultSet
```

Nó thường dùng với relational SQL, nhưng một số NoSQL/search/analytical engines cung cấp **JDBC driver hoặc SQL-compatible endpoint**.

Ví dụ ứng dụng SQL tooling có thể kết nối tới:

- SQL query service của một search engine;
- SQL/SQL++ gateway của một document database;
- Analytical engine nằm trên NoSQL storage;
- Bridge/translator do nhà cung cấp hoặc bên thứ ba cung cấp.

### 11.1. JDBC không tự làm database thành quan hệ

Một JDBC driver có thể nhận:

```sql
SELECT id, status
FROM orders
WHERE customer_id = ?
```

rồi:

- Dịch thành native query;
- Gửi tới SQL endpoint;
- Thực hiện scan/query service;
- Chuyển documents thành rows.

Nó **không tự tạo** foreign keys, joins hiệu quả, transaction ACID hoặc relational optimizer nếu backend không cung cấp.

### 11.2. Không phải NoSQL nào cũng có JDBC chính thức

Nếu sản phẩm không có driver JDBC phù hợp, không thể trỏ một PostgreSQL/MySQL JDBC URL vào một NoSQL server và mong giao thức hoạt động.

### 11.3. Driver JDBC không nhất thiết dùng chung đường network với native driver

Một NoSQL JDBC driver có thể đi qua BI connector, gateway hoặc REST SQL endpoint. Latency, authentication, quota và query semantics có thể khác native API.

### 11.4. Cần kiểm tra cụ thể

- JDBC driver vendor/phiên bản;
- SQL dialect hỗ trợ;
- Read-only hay read/write;
- DDL, transactions, batch, prepared statements;
- Pagination/streaming;
- Mapping JSON/array/nested types;
- Authentication, TLS, failover;
- Query cost, limits, indexing;
- JDBC metadata: column types, nullable, catalog/schema.

**Dùng JDBC là một yêu cầu về giao diện và SQL semantics, không phải nâng cấp tự động của NoSQL.**

## 12. JDBC khác Spring JDBC, Spring Data JDBC và R2DBC

Bốn tên này dễ bị nhầm:

| Công nghệ | Vai trò |
|---|---|
| JDBC | Java API `java.sql` kết nối tới JDBC driver |
| Spring JDBC / `JdbcTemplate` | Spring abstraction trên JDBC, giảm boilerplate SQL/row mapping |
| Spring Data JDBC | Module Spring Data phục vụ relational aggregate persistence thông qua JDBC |
| R2DBC | API truy cập relational database theo mô hình reactive, không phải JDBC |

### 12.1. Spring Data JDBC không phải “Spring Data dành cho mọi NoSQL có JDBC”

Nó thiết kế cho relational aggregates và SQL/JDBC semantics. Một NoSQL JDBC bridge có thể không hỗ trợ SQL/transaction/DDL mà module kỳ vọng.

### 12.2. `JdbcTemplate` vẫn là JDBC

```text
JdbcTemplate
    |
    v
java.sql.Connection
    |
    v
Vendor JDBC Driver
```

Nó không tự thay native mapper của MongoDB, Cassandra hay DynamoDB.

### 12.3. JPA/Hibernate cũng khác

JPA/Hibernate ORM thường dựa trên relational SQL/JDBC infrastructure. Không nên giả định `JpaRepository` hoạt động trực tiếp với một NoSQL collection chỉ vì có JDBC bridge.

### 12.4. Reactive MongoDB không cần R2DBC

Reactive MongoDB sử dụng reactive MongoDB driver và Spring Data MongoDB Reactive. R2DBC là giải pháp khác, không phải lớp wrapper chung cho tất cả NoSQL drivers.

## 13. Bảng so sánh bốn cách tiếp cận

| Tiêu chí | Native driver/SDK | Data mapper | Spring Data | JDBC nếu có |
|---|---|---|---|---|
| Gửi request tới DB | Trực tiếp qua native API | Thường dùng driver bên dưới | Dùng driver/module bên dưới | Qua JDBC driver/SQL endpoint |
| Ánh xạ POJO | Manual hoặc codec/enhanced client | Trọng tâm | Tích hợp annotation/converter | RowMapper/manual qua ResultSet |
| Query | Native DSL/API/CQL/Cypher | Tùy mapper | Repository/Template/native escape hatch | SQL dialect hỗ trợ |
| Độ đặc thù NoSQL | Cao | Giữ tùy abstraction | Cao-vừa, theo module | Có thể bị hạn chế |
| Tính di động cross-database | Thấp | Thấp-vừa | API chung một phần, semantics khác | Giao diện chung, SQL dialect vẫn khác |
| Transaction | Native capability | Không tự tạo | Dùng khả năng của backend | Tùy driver/SQL service |
| Index/partition awareness | Thường rõ ràng | Tùy thiết kế | Có thể bị che | Dễ bị SQL abstraction che |
| Mapping cost | Tùy cách dùng | Có overhead conversion | Có conversion/proxy/repo overhead | Row conversion/SQL translation |
| Debug query | Bám native command | Cần nhìn mapper | Cần xem generated query | Cần xem SQL explain/backend plan |
| Dùng cho BI/SQL tooling | Ít phù hợp | Ít phù hợp | Ít phù hợp | Thường phù hợp khi có SQL |
| Dùng cho domain CRUD trong Spring | Nhiều boilerplate hơn | Tùy thư viện | Thường thuận lợi | Tùy SQL support |
| Hỗ trợ feature mới | Thường sớm | Có thể chờ mapper | Có thể chờ module | Có thể không expose |
| Async/reactive | Tùy driver | Tùy mapper | Tùy module | JDBC chuẩn blocking |

Không có một cột “tốt nhất” cho mọi use case. Quyết định dựa trên access pattern, tốc độ phát triển, tương thích, correctness và chi phí vận hành.

## 14. MongoDB native Java driver: đọc/ghi Document

Ví dụ Java sử dụng MongoDB driver sync:

```java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.model.Filters;
import org.bson.Document;

public final class NativeMongoExample {

    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");

        try (MongoClient client = MongoClients.create(uri)) {
            MongoDatabase db = client.getDatabase("learning");
            MongoCollection<Document> customers =
                    db.getCollection("customers");

            customers.insertOne(new Document("_id", "U42")
                    .append("displayName", "An")
                    .append("city", "Hà Nội"));

            Document customer = customers
                    .find(Filters.eq("_id", "U42"))
                    .first();

            if (customer != null) {
                System.out.println(
                        customer.getString("displayName")
                );
            }
        }
    }
}
```

Ở đây:

- `MongoClient` là native client.
- `MongoDatabase`/`MongoCollection` là native handles.
- `org.bson.Document` là BSON document representation.
- `Filters.eq` tạo BSON filter.
- Không có `@Document` của Spring Data.
- Client được đóng cuối chương trình minh họa.

### 14.1. Trong server, không tạo MongoClient mỗi request

Một production service thường tạo **một shared client theo cấu hình**, vì client có pool/topology monitoring. Tạo và đóng client trong mỗi HTTP request sẽ gây connection churn, handshake overhead và dễ quá tải.

### 14.2. Query cần index đúng

```java
customers.find(Filters.eq("email", email)).first();
```

Không phải vì dùng driver gốc mà query trên `email` luôn O(1). Cần index phù hợp, selectivity và kiểm tra execution plan.

### 14.3. Driver không biết tất cả business rules

Native `insertOne()` không tự bảo vệ unique `email` nếu database chưa có unique index/constraint thích hợp và ứng dụng không dùng authority đúng.

## 15. MongoDB native mapping thủ công

Một ứng dụng có thể tự map Document thành object:

```java
import org.bson.Document;

public record CustomerView(
        String id,
        String displayName,
        String city
) {
    public static CustomerView fromBson(Document doc) {
        return new CustomerView(
                doc.getString("_id"),
                doc.getString("displayName"),
                doc.getString("city")
        );
    }
}
```

### 15.1. Khi hợp lý?

- DTO rất nhỏ, ít fields;
- Query chỉ trả projection;
- Hệ cần kiểm soát chính xác wire schema;
- Chưa muốn thêm framework;
- Muốn tách domain object khỏi MongoDB dependencies.

### 15.2. Khi bắt đầu khó?

- Nhiều nested objects;
- `ObjectId`, `Instant`, binary;
- Optional/missing fields;
- Polymorphism;
- Schema versions;
- Giá trị chuyển đổi custom;
- Bulk operations và partial updates.

Lúc này mapper/codecs có thể giảm boilerplate và sai sót.

## 16. MongoDB POJO Codec: mapping ngay trong native driver

MongoDB Java driver hỗ trợ codec registry và POJO mapping cho các class phù hợp.

Một cấu hình minh họa:

```java
import com.mongodb.MongoClientSettings;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import org.bson.codecs.configuration.CodecProvider;
import org.bson.codecs.configuration.CodecRegistry;

import static org.bson.codecs.configuration.CodecRegistries.*;
import static org.bson.codecs.pojo.PojoCodecProvider.*;

public final class NativePojoCodecExample {

    public static MongoCollection<CustomerPojo> collection(
            MongoClient client
    ) {
        CodecProvider provider = builder()
                .automatic(true)
                .build();

        CodecRegistry registry = fromRegistries(
                MongoClientSettings.getDefaultCodecRegistry(),
                fromProviders(provider)
        );

        MongoDatabase db = client.getDatabase("learning")
                .withCodecRegistry(registry);

        return db.getCollection(
                "customers",
                CustomerPojo.class
        );
    }

    public static final class CustomerPojo {
        private String id;
        private String displayName;

        public CustomerPojo() {}

        public String getId() { return id; }
        public void setId(String id) { this.id = id; }

        public String getDisplayName() {
            return displayName;
        }

        public void setDisplayName(String value) {
            this.displayName = value;
        }
    }
}
```

Đây là ví dụ định hướng; phải cấu hình ID/field conventions phù hợp với BSON schema thực tế, đặc biệt `_id` và POJO property `id`. Trên hệ thật, không nên dùng automatic codec mapping không kiểm soát với dữ liệu không đáng tin.

### 16.1. Điểm cần nhớ

**POJO mapping có thể được cung cấp ngay trong driver**, không nhất thiết yêu cầu Spring Data.

### 16.2. Mapping không tự có repositories

Có codec giúp đọc/ghi `CustomerPojo`; vẫn cần tự viết query, pagination và service APIs nếu không dùng một tầng cao hơn.

## 17. Spring Data MongoDB: entity mapping

Một entity Spring Data MongoDB:

```java
import java.time.Instant;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.mongodb.core.index.Indexed;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;

@Document("customers")
public class Customer {

    @Id
    private String id;

    @Indexed(unique = true)
    private String email;

    @Field("display_name")
    private String displayName;

    private Instant createdAt;

    @Version
    private Long version;

    protected Customer() {}

    public Customer(String email, String displayName) {
        this.email = email;
        this.displayName = displayName;
    }

    // getters/setters hoặc constructor binding
}
```

Ý nghĩa:

- `@Document("customers")`: mapping collection.
- `@Id`: ID field mapping.
- `@Field`: tên field lưu trữ khác property.
- `@Indexed`: mô tả index metadata; phải kiểm tra index creation/migration policy thực tế.
- `@Version`: hỗ trợ optimistic locking theo Spring Data module/version thích hợp.

### 17.1. Annotation không thay index management

Có `@Indexed(unique = true)` không có nghĩa deployment luôn đã tạo index trong production. Nhiều hệ tắt tự động index creation hoặc quản lý index bằng migration riêng.

### 17.2. `save()` không đồng nghĩa patch

Lưu lại toàn entity có thể ảnh hưởng các fields chưa được client đọc nếu không dùng version control/partial update. Với API PATCH nên hiểu rõ mapper/save semantics.

## 18. Spring Data MongoRepository

```java
import java.util.List;
import java.util.Optional;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface CustomerRepository
        extends MongoRepository<Customer, String> {

    Optional<Customer> findByEmail(String email);

    List<Customer> findByDisplayName(String displayName);
}
```

Business service:

```java
import org.springframework.stereotype.Service;

@Service
public class CustomerService {
    private final CustomerRepository repository;

    public CustomerService(CustomerRepository repository) {
        this.repository = repository;
    }

    public Customer getByEmail(String email) {
        return repository.findByEmail(email)
                .orElseThrow(() ->
                        new IllegalArgumentException(
                                "Customer not found"
                        ));
    }
}
```

### 18.1. Ưu điểm

- Không cần tự gọi `getCollection` cho mọi CRUD.
- Type-safe object model ở mức repository interface.
- Dễ giữ business code tập trung vào aggregate.
- Tận dụng Spring DI, exception translation và conversion.

### 18.2. Hạn chế

- Method name không bảo đảm query có index.
- Thiếu kiểm soát trực tiếp một số native options.
- Cần biết `save()` vs atomic update semantics.
- `Page` có thể cần count query tốn chi phí.
- Repository không tạo cross-document transaction tự động chỉ vì gọi hai methods liên tiếp.

### 18.3. Không giả định module nào cũng dùng cùng method names

`MongoRepository`, `CassandraRepository`, `ElasticsearchRepository`, `Neo4jRepository` có những tương đồng nhưng **khác query model và semantics**. Một API di chuyển từ MongoDB sang Cassandra không chỉ là thay import.

## 19. MongoTemplate: query linh hoạt và conditional update

Dùng `MongoTemplate` cho partial update có điều kiện:

```java
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import org.springframework.stereotype.Component;

@Component
public final class CustomerUpdater {
    private final MongoTemplate mongo;

    public CustomerUpdater(MongoTemplate mongo) {
        this.mongo = mongo;
    }

    public boolean changeName(
            String id,
            long expectedVersion,
            String newName
    ) {
        Query query = new Query(
                Criteria.where("_id").is(id)
                        .and("version").is(expectedVersion)
        );

        Update update = new Update()
                .set("display_name", newName)
                .inc("version", 1);

        return mongo.updateFirst(
                query,
                update,
                Customer.class
        ).getModifiedCount() == 1;
    }
}
```

**Lưu ý quan trọng:** đây là ví dụ atomic conditional update thủ công với trường version. Khi cũng sử dụng `@Version` và Spring Data mapping, cần kiểm tra hành vi version/converter ở phiên bản dùng để không double-increment hoặc trộn hai cơ chế OCC không nhất quán.

### 19.1. Query mapping

Dùng `Customer.class` giúp `MongoTemplate` ánh xạ property/field theo model. Nhưng khi trộn tên Java property với physical field name, cần kiểm tra generated query thực tế.

### 19.2. Đừng quên unique index

Version check ngăn stale update trên một customer, nhưng business uniqueness như email có thể vẫn cần unique index/conditional authority.

### 19.3. Vì sao không dùng repository `save()` cho mọi thứ?

Với high-contention counters, atomic update trên field có thể hiệu quả và đúng hơn read–modify–save toàn document. Lựa chọn tùy mutation semantics, không phải do repository “yếu”.

## 20. Spring Boot và cấu hình client

Một ứng dụng Spring Boot có thể cấu hình MongoDB URI qua cấu hình môi trường:

```yaml
spring:
  data:
    mongodb:
      uri: ${MONGODB_URI}
```

Trong production:

- Lấy URI từ secret manager hoặc environment;
- Không commit user/password lên Git;
- Bật TLS phù hợp deployment;
- Chọn connection/pool/socket timeouts;
- Quan sát server selection;
- Cấu hình credential rotation;
- Kiểm soát read/write concerns theo yêu cầu;
- Không tạo nhiều MongoClients ngoài ý muốn.

### 20.1. Starter không thay compatibility matrix

Dùng `spring-boot-starter-data-mongodb` không nghĩa mọi version MongoDB server và mọi driver đều phù hợp. Đối chiếu Spring Boot, Spring Data, MongoDB Java Driver và server version.

### 20.2. Multiple clusters

Nếu ứng dụng có hai MongoDB clusters, cần phân biệt `MongoClient`, `MongoDatabaseFactory`, `MongoTemplate` và transaction managers. Autoconfiguration mặc định không tự biết service method muốn đi cluster nào.

### 20.3. Transactions

Có thể dùng Spring transaction integration nếu deployment MongoDB hỗ trợ transactions và `MongoTransactionManager` được cấu hình đúng. Việc thêm annotation `@Transactional` không tự khiến two-database hoặc HTTP call trở thành một transaction.

## 21. Một local transaction khác workflow xuyên nhiều services

Ví dụ một service lưu Order và Outbox trong cùng MongoDB:

```text
Order Service
  |
  +-- local transaction:
  |      save Order PENDING
  |      insert Outbox Event
  |      COMMIT
  |
  +-- Relay -> Kafka
                 |
                 v
           Inventory Service
```

`MongoTemplate`, `MongoRepository` hoặc native driver đều phải tham gia **đúng session/transaction context** nếu muốn operations atomic với nhau.

### 21.1. Spring Data `@Transactional` có ranh giới

`@Transactional` của Order Service không tự rollback:

- Payment provider HTTP request;
- Redis command nằm ngoài transaction manager;
- Một Cassandra cluster khác;
- Message broker publish riêng;
- Email đã gửi.

### 21.2. Không gọi external API trong callback transaction retryable

Native driver hoặc Spring transaction infrastructure có thể retry một số hoạt động. Nếu callback gọi charge payment, retry có thể nhân đôi side effect.

### 21.3. Outbox/inbox

Outbox ghi intent event atomically cùng state nguồn; relay publish at-least-once; consumer dùng idempotency/inbox. Đây là tầng kiến trúc **độc lập với việc code thao tác MongoDB qua driver hay Spring Data**.

## 22. Redis: native client so với Spring Data Redis

Redis là ví dụ tốt để thấy NoSQL không phải document repository.

### 22.1. Lettuce native API

Ví dụ khái niệm với Lettuce sync commands:

```java
import io.lettuce.core.RedisClient;
import io.lettuce.core.api.StatefulRedisConnection;
import io.lettuce.core.api.sync.RedisCommands;

public final class LettuceExample {

    public static void main(String[] args) {
        String uri = System.getenv("REDIS_URI");
        RedisClient client = RedisClient.create(uri);

        try (StatefulRedisConnection<String, String> connection =
                     client.connect()) {
            RedisCommands<String, String> commands =
                    connection.sync();

            commands.set("profile:U42:city", "Hà Nội");
            System.out.println(
                    commands.get("profile:U42:city")
            );
        } finally {
            client.shutdown();
        }
    }
}
```

Native Lettuce/Jedis expose Redis commands và connection/pipeline/pubsub APIs theo version.

### 22.2. Spring `StringRedisTemplate`

```java
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Component;

@Component
public final class ProfileCache {
    private final StringRedisTemplate redis;

    public ProfileCache(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void cacheCity(String userId, String city) {
        redis.opsForValue().set(
                "profile:" + userId + ":city",
                city
        );
    }

    public String getCity(String userId) {
        return redis.opsForValue().get(
                "profile:" + userId + ":city"
        );
    }
}
```

### 22.3. Spring Data Redis không biến Redis thành JPA

- Key design và data types vẫn quyết định hiệu quả.
- `RedisTemplate` serializers phải nhất quán giữa writers/readers.
- Hashes, strings, streams, sorted sets có semantics riêng.
- Atomicity Redis command/script không tự là transaction relational.
- Redis Cluster có constraints về hash slots cho multi-key operations.
- Replication/failover durability vẫn phụ thuộc cấu hình Redis.

### 22.4. TTL

```java
redis.opsForValue().set(key, value, Duration.ofMinutes(10));
```

TTL đúng chỗ có thể hữu ích cho cache. Nhưng TTL ở cache không phải deadline authoritative của inventory reservation trừ khi thiết kế phù hợp và có recovery.

### 22.5. Khi cần Lua hoặc pipeline

Có thể sử dụng `RedisTemplate.execute(...)` với script hoặc native Lettuce/Jedis; phải hiểu atomicity trên Redis server, serialization và execution blocking. Không giả định script chạy qua nhiều independent Redis cluster nodes như một transaction toàn cụm.

## 23. Cassandra: native CQL driver vs Spring Data Cassandra

Cassandra nhấn mạnh partition key, clustering columns và query-driven data modeling.

### 23.1. Native Java driver

Ví dụ với API kiểu DataStax/Apache Cassandra Java Driver 4:

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;

public final class NativeCassandraExample {
    public static void main(String[] args) {
        try (CqlSession session = CqlSession.builder().build()) {
            PreparedStatement stmt = session.prepare(
                    "SELECT status FROM orders_by_id " +
                    "WHERE order_id = ?"
            );

            var row = session.execute(
                    stmt.bind("O100")
            ).one();

            if (row != null) {
                System.out.println(
                        row.getString("status")
                );
            }
        }
    }
}
```

Đoạn ví dụ giả định contact points, authentication, keyspace và datacenter đã được cấu hình bằng driver config. Production cần kết nối an toàn và cấu hình routing/timeouts riêng.

### 23.2. Spring Data Cassandra entity

```java
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("orders_by_id")
public class OrderById {
    @PrimaryKey
    private String orderId;
    private String status;

    protected OrderById() {}

    // getters/setters
}
```

Repository:

```java
import org.springframework.data.cassandra.repository.CassandraRepository;

public interface OrderByIdRepository
        extends CassandraRepository<OrderById, String> {
}
```

### 23.3. Giới hạn không được quên

- Primary key/partition key là phần của access pattern, không chỉ annotation cho tiện.
- Không phải query nào theo một field bất kỳ cũng hiệu quả hoặc hợp lệ.
- Secondary index/materialized view có semantics và đánh đổi riêng.
- Paging Cassandra là stateful/page-token theo driver/protocol, không nhất thiết offset.
- Read/write consistency levels cần chọn cho từng operation khi cần.
- Regular write `QUORUM` không tự là compare-and-set.
- LWT/conditional operations có coordination cost và serial consistency semantics.

### 23.4. Khi native driver có lợi

Khi cần kiểm soát prepared statement, execution profile, token-aware routing, paging state, LWT response hoặc batch semantics. Nhưng có thể vẫn dùng Spring Data Cassandra cho CRUD theo bảng đã thiết kế và native driver cho operations đặc biệt.

## 24. DynamoDB: native AWS SDK và Enhanced Client

DynamoDB khác MongoDB ở chỗ Java SDK giao tiếp với **dịch vụ DynamoDB API**, không có một `java.sql.Connection` phổ quát tới bảng.

### 24.1. Low-level SDK v2

```java
import java.util.Map;
import software.amazon.awssdk.services.dynamodb.DynamoDbClient;
import software.amazon.awssdk.services.dynamodb.model.AttributeValue;
import software.amazon.awssdk.services.dynamodb.model.GetItemRequest;

public final class DynamoLowLevelExample {

    public static void main(String[] args) {
        try (DynamoDbClient client = DynamoDbClient.create()) {
            GetItemRequest request = GetItemRequest.builder()
                    .tableName("Orders")
                    .key(Map.of(
                            "PK", AttributeValue.fromS("ORDER#O100"),
                            "SK", AttributeValue.fromS("META")
                    ))
                    .build();

            var response = client.getItem(request);
            System.out.println(response.item());
        }
    }
}
```

Cần có AWS credentials/region/environment phù hợp. Dùng IAM least privilege và không hardcode access keys.

### 24.2. Enhanced Client

AWS SDK v2 cung cấp **DynamoDB Enhanced Client** để ánh xạ objects sang items theo table schema.

```java
import software.amazon.awssdk.enhanced.dynamodb.mapper.annotations.DynamoDbBean;
import software.amazon.awssdk.enhanced.dynamodb.mapper.annotations.DynamoDbPartitionKey;

@DynamoDbBean
public class OrderItem {
    private String pk;
    private String status;

    @DynamoDbPartitionKey
    public String getPk() {
        return pk;
    }

    public void setPk(String value) {
        this.pk = value;
    }

    public String getStatus() {
        return status;
    }

    public void setStatus(String value) {
        this.status = value;
    }
}
```

### 24.3. Enhanced Client không phải Spring Data

Nó là mapping layer của AWS SDK, có table schemas và typed operations. Một ứng dụng Spring Boot có thể inject AWS SDK clients mà không sử dụng Spring Data repository.

### 24.4. Quan trọng hơn mapping

- Partition/sort key chọn theo access patterns;
- GSI và hot partitions;
- Query vs Scan;
- `ConditionExpression`;
- `TransactWriteItems`;
- Consistent reads và global tables semantics;
- TTL, Streams;
- Request capacity/throttling;
- Pagination bằng last evaluated key.

Một `OrderItem` POJO đẹp không sửa được một partition key dẫn tới full-table Scan.

## 25. Elasticsearch/OpenSearch: Search client khác repository CRUD thông thường

Search engine thường được dùng làm **read/search projection**, không luôn là nguồn dữ liệu transaction.

### 25.1. Native Java API Client

Một ví dụ kiểu Elasticsearch Java API Client:

```java
import co.elastic.clients.elasticsearch.ElasticsearchClient;
import co.elastic.clients.elasticsearch.core.SearchResponse;

public final class ProductSearch {
    private final ElasticsearchClient client;

    public ProductSearch(ElasticsearchClient client) {
        this.client = client;
    }

    public SearchResponse<ProductDocument> search(
            String keyword
    ) throws java.io.IOException {
        return client.search(s -> s
                        .index("products")
                        .query(q -> q.match(m -> m
                                .field("title")
                                .query(keyword)
                        )),
                ProductDocument.class);
    }

    public record ProductDocument(
            String id,
            String title
    ) {}
}
```

Ví dụ giả định `ElasticsearchClient`/transport được cấu hình và index mapping phù hợp. Cú pháp client và mapping DTO có thể thay đổi theo phiên bản.

### 25.2. Spring Data Elasticsearch

`ElasticsearchRepository` hoặc `ElasticsearchOperations` hỗ trợ document mapping và query theo abstraction module.

### 25.3. Một khác biệt quan trọng

- Database source có thể commit Product mới.
- Outbox/CDC gửi event sang Search index.
- Search chưa refresh nên vẫn chưa thấy Product mới.

Dùng Spring Data Elasticsearch không làm search projection tự đồng bộ tức thì với source DB.

### 25.4. JDBC SQL endpoint của search engine

Một số search engines có SQL interface/JDBC driver. SQL SELECT có thể phù hợp BI/reporting nhưng không expose hoàn toàn native search DSL, vector queries, scoring, aggregations hoặc index lifecycle.

Đừng ép mọi full-text/vector search thành JDBC SELECT chỉ để reuse `JdbcTemplate`.

## 26. Neo4j: Cypher driver vs Spring Data Neo4j

Neo4j là graph database: query traversal và relationship là yếu tố trung tâm.

### 26.1. Native Java driver

```java
import org.neo4j.driver.AuthTokens;
import org.neo4j.driver.Driver;
import org.neo4j.driver.GraphDatabase;
import org.neo4j.driver.Values;

public final class NativeNeo4jExample {

    public static void main(String[] args) {
        String uri = System.getenv("NEO4J_URI");
        String username = System.getenv("NEO4J_USER");
        String password = System.getenv("NEO4J_PASSWORD");

        try (Driver driver = GraphDatabase.driver(
                uri,
                AuthTokens.basic(username, password)
        )) {
            try (var session = driver.session()) {
                String name = session.executeRead(tx -> {
                    var record = tx.run(
                            "MATCH (u:User {id: $id}) " +
                            "RETURN u.name AS name",
                            Values.parameters("id", "U42")
                    ).single();
                    return record.get("name").asString();
                });
                System.out.println(name);
            }
        }
    }
}
```

Đoạn code giả định node tồn tại; production xử lý kết quả rỗng/driver exceptions, config database và TLS.

### 26.2. Spring Data Neo4j mapping

```java
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;
import org.springframework.data.neo4j.core.schema.Relationship;

@Node("User")
public class UserNode {
    @Id
    private String id;

    private String name;

    @Relationship(type = "FOLLOWS")
    private java.util.Set<UserNode> follows;

    // constructors/getters/setters
}
```

Repository abstraction hữu ích khi graph model và traversal phù hợp. Nhưng graph query cost, cycles, relationship depth và transaction behavior phải được đánh giá theo Neo4j.

### 26.3. Một model graph không phải JPA entity graph

Đừng giả định mọi nested object đều được lazy-loaded với JPA semantics, hay một `save()` graph aggregate xử lý đúng mọi relationship dưới mọi version/cấu hình.

### 26.4. JDBC cho Neo4j nếu được hỗ trợ

Một số sản phẩm/version có driver JDBC hoặc SQL/Cypher bridge riêng; cần xác minh semantics và query dialect của driver cụ thể. JDBC không thay native Cypher driver khi cần toàn bộ graph traversal behavior.

## 27. JDBC trên một hệ NoSQL có SQL endpoint

Một chương trình Java dùng JDBC driver hợp lệ do nhà cung cấp NoSQL/SQL service cung cấp:

```java
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.util.Properties;

public final class SqlFacadeExample {

    public static void main(String[] args) throws Exception {
        String jdbcUrl = System.getenv("NOSQL_SQL_JDBC_URL");

        Properties props = new Properties();
        props.setProperty(
                "user",
                System.getenv("NOSQL_SQL_USER")
        );
        props.setProperty(
                "password",
                System.getenv("NOSQL_SQL_PASSWORD")
        );

        try (Connection conn =
                     DriverManager.getConnection(jdbcUrl, props);
             PreparedStatement statement =
                     conn.prepareStatement(
                             "SELECT id, status FROM orders " +
                             "WHERE customer_id = ?"
                     )) {

            statement.setString(1, "U42");

            try (ResultSet rows = statement.executeQuery()) {
                while (rows.next()) {
                    System.out.println(
                            rows.getString("id") + ": " +
                            rows.getString("status")
                    );
                }
            }
        }
    }
}
```

**Đây là mẫu JDBC giả định**, không phải lệnh SQL được hứa chạy trên một NoSQL cụ thể. Muốn thực thi, cần:

- Cài JDBC driver thật;
- Dùng đúng JDBC URL;
- Xác minh SQL dialect và tên column;
- Biết SELECT có dùng index hay scan;
- Kiểm tra support cho parameter binding;
- Biết schema metadata được suy từ documents/collections ra sao.

### 27.1. PreparedStatement có luôn được server prepare không?

Không nhất thiết. Một số JDBC drivers có thể dịch/bind tại client hoặc SQL gateway. Cần kiểm tra chính sách SQL injection protection và prepared statement semantics của vendor.

### 27.2. `conn.setAutoCommit(false)` có tạo transaction không?

Không được giả định. Một số SQL endpoints chỉ hỗ trợ reads hoặc không hỗ trợ transactions như relational. Kiểm tra `DatabaseMetaData`, driver contract và thử trên đúng deployment.

### 27.3. Join và GROUP BY

Một SQL query có JOIN hợp lệ cú pháp không đảm bảo join được pushdown hiệu quả. SQL bridge có thể giới hạn joins, scan lớn hoặc chuyển đổi dữ liệu tốn kém.

### 27.4. JSON/array/nested fields

Một document có nested arrays không luôn map tự nhiên sang một ResultSet phẳng. Driver có thể trả JSON text, vendor-specific JDBC types hoặc phẳng hóa dữ liệu. Phải rõ mất mát thông tin và type conversions.

## 28. JDBC metadata và khả năng hỗ trợ thực

Một JDBC tool như DBeaver hoặc BI platform thường hỏi metadata:

```java
var meta = conn.getMetaData();
boolean transactions = meta.supportsTransactions();
boolean batches = meta.supportsBatchUpdates();
```

Những câu hỏi quan trọng:

- Driver hỗ trợ `getTables()`/`getColumns()` đầy đủ không?
- SQL types ánh xạ như thế nào?
- `setFetchSize()` có hiệu lực hay bị bỏ qua?
- Cursor có streaming hay load hết vào RAM?
- Driver có read-only mode không?
- Có join/aggregation/cast/window functions không?
- Có transaction isolation levels nào?
- Có SSL/SSO/service authentication không?
- Có documented row/query limits không?

### 28.1. `DatabaseMetaData` không thay tài liệu vendor

Metadata có thể thiếu hoặc không phản ánh mọi tình huống. Cần test access pattern thật, đặc biệt DDL, transactions và performance.

### 28.2. JDBC bridge có thể phù hợp báo cáo nhưng không hợp write path

Một reporting tool dùng SQL SELECT từ NoSQL analytics endpoint có thể tốt. Nhưng ứng dụng checkout cần conditional reservation của native API: không nên thay bằng `UPDATE inventory SET ... WHERE ...` qua một bridge không bảo đảm atomicity thích hợp.

## 29. Chọn mô hình: đồng bộ, bất đồng bộ và reactive

Java có nhiều phong cách API:

- **Synchronous/blocking:** gọi method và đợi response;
- **Asynchronous/future-based:** API trả `CompletionStage`, `CompletableFuture` hoặc future riêng;
- **Reactive:** dòng dữ liệu với backpressure theo Reactive Streams/Project Reactor, nếu driver hỗ trợ.

### 29.1. Blocking driver

Dễ đọc và phù hợp nhiều Spring MVC services. Với concurrency lớn, cần tính số threads, connections và độ trễ I/O.

### 29.2. Async driver

Hữu ích khi muốn xử lý nhiều requests I/O mà không giữ một thread blocking cho mỗi operation. Nhưng phải quản lý future failures, cancellations, deadlines và resource lifecycle.

### 29.3. Reactive Spring Data

Reactive repositories/template chỉ hữu ích khi **tầng driver và pipeline hỗ trợ nonblocking/reactive đúng**.

```text
HTTP Reactive Handler
        |
        v
Reactive Repository
        |
        v
Reactive NoSQL Driver
        |
        v
Database
```

### 29.4. Không “reactive hóa” JDBC blocking bằng cách đổi return type

Nếu một function dùng `ResultSet.next()` blocking rồi trả `Mono`, bản chất I/O vẫn blocking; có thể chuyển phần blocking sang scheduler riêng nhưng không trở thành native nonblocking JDBC.

### 29.5. Không trộn blocking calls lên event-loop

Trong Spring WebFlux hoặc một event-loop based stack, gọi blocking native driver/JDBC trực tiếp trên event-loop có thể làm nghẽn mọi requests. Cần dùng reactive driver hoặc cô lập blocking I/O theo chiến lược phù hợp.

### 29.6. Backpressure không làm biến mất database limits

Reactive stream không tự giảm hot partition, request cost hoặc write contention. Cần pagination, batching, rate limiting, connection pools và capacity planning.

## 30. Connection pool, client lifecycle và thread safety

### 30.1. Shared client

Các native clients như MongoDB `MongoClient`, AWS SDK client hay Elasticsearch client thường được thiết kế để reuse theo lifecycle ứng dụng (theo hợp đồng riêng). Không tạo mỗi request một client rồi handshakes liên tục.

### 30.2. Session không luôn thread-safe

Một `MongoClient` có thể dùng chung, nhưng một transaction session không được mặc định dùng đồng thời từ nhiều request threads. Một `ResultSet`/`Connection` cũng có lifecycle/ownership riêng.

### 30.3. Cassandra CqlSession

`CqlSession` thường được chia sẻ và quản lý lifecycle, không tạo mỗi query. Prepared statements có thể cache/reuse theo chiến lược driver.

### 30.4. Redis client và connection

Lettuce/Jedis có đặc điểm connection pooling, thread-safety và API sync/async riêng. Không suy một `StatefulRedisConnection` hoặc `Jedis` object bất kỳ có thể chia sẻ giữa mọi threads mà không kiểm tra docs, nhất là khi có transaction/blocking commands.

### 30.5. Timeouts

Cần phân biệt:

- Connection timeout;
- Server selection timeout;
- Socket/read timeout;
- Query/execution deadline;
- Pool wait timeout;
- Transaction timeout;
- Client request deadline;
- Overall HTTP request timeout.

Một request timeout không chứng minh write chưa commit. Cần operation ID/conditional idempotency cho đường ghi có side effects.

## 31. Retry, idempotency và lỗi không rõ kết quả

Tầng driver hoặc Spring Data có thể retry một số lỗi transient. Nhưng **retry không tự an toàn cho mọi operation**.

### 31.1. Read retry

Một read idempotent thường có thể retry, nhưng cần xử lý deadline, read consistency và cost.

### 31.2. Write retry

Một `SET K=v` vô điều kiện có thể idempotent theo state; một `INCREMENT` hoặc `INSERT order with new UUID` có thể nhân business effect nếu retry như request mới.

### 31.3. Unknown outcome

```text
Client -> DB: Reserve inventory
DB commits
ACK lost
Client timeout
```

Không được tự suy operation thất bại. Có thể tra `reservationId`/`operationId` hoặc retry có conditional guard và identity ổn định.

### 31.4. Spring retry không thay business dedupe

`@Retryable` hay driver retry policy không bảo đảm exactly-once payment/inventory. Cần unique constraints, CAS, idempotency key và reconciliation phù hợp.

### 31.5. Error translation

Spring Data có thể chuyển native errors thành họ `DataAccessException`. Khi cần phân biệt duplicate key, throttling, conditional conflict, transient network hay unavailable quorum, cần kiểm tra mapping lỗi và giữ đủ diagnostic context.

## 32. Transaction scopes theo sản phẩm

| Database/API | Giao dịch/atomicity thường cần xét | Điều không được suy |
|---|---|---|
| MongoDB | Atomic document; multi-document transaction khi topology hỗ trợ | Không tự atomic với HTTP/Redis/broker |
| DynamoDB | Atomic item conditions; TransactWriteItems trong giới hạn dịch vụ | Không tự transaction global tables mọi mode |
| Cassandra | Partition writes/regular CL; LWT conditional semantics theo phiên bản | Regular QUORUM hoặc logged BATCH không tự serializable multi-partition |
| Redis | Single commands/scripts/transaction semantics theo node/cluster | Không tự rollback transaction kiểu RDBMS; failover durability tùy config |
| Cosmos DB for NoSQL | Transactional batch trong cùng logical partition scope | Không tự nhiều partition hoặc external API |
| Firestore | Transactions/atomic batches theo limits | Callback retry không được chứa side effects |
| Neo4j | Graph transactions theo database/API | Không tự bao phủ hệ khác |
| Elasticsearch | Per-document operations/bulk với per-item results | Bulk request không tự all-or-nothing |
| SQL gateway/JDBC | Tùy SQL endpoint/driver | Không mặc định hỗ trợ JDBC commit/rollback |

Mục tiêu của bảng là **nhắc kiểm tra đúng hợp đồng**, không thay release documentation.

## 33. Performance: framework overhead hay query design?

Một sai lầm là thấy một query chậm rồi kết luận `MongoRepository` chậm hơn native driver.

### 33.1. Các nguyên nhân thường lớn hơn

- Query không có index phù hợp;
- Scan nhiều documents/rows;
- Cross-partition fan-out;
- Over-fetch fields;
- N+1 fetch logic ở application;
- Large JSON/BSON payload;
- Serialization lớn;
- Read/write concern quá mạnh cho yêu cầu không cần;
- Network RTT hoặc cross-region;
- Connection pool exhaustion;
- Inefficient pagination;
- Retry storm;
- Hot keys/partitions;
- Aggregation/sort spill.

### 33.2. Mapper cũng có chi phí

Converting hàng triệu documents sang POJO có thể tốn CPU, allocations và GC. Khi chỉ cần vài fields, dùng projections/DTO hoặc lower-level cursor có thể giảm overhead.

### 33.3. Không bỏ mapper trước khi đo

So native vs template vs repository cần **cùng query shape, index, result count, connection reuse, warm cache và consistency level**. Nếu một phía dùng covered index còn phía khác scan toàn table, so sánh không có ý nghĩa.

### 33.4. JDBC bridge có thể thêm bước chuyển đổi

JDBC SQL translation, schema inference, ResultSet conversion và gateway hops có thể tăng latency. Nhưng với batch analytics, SQL endpoint có thể thực thi vectorized/aggregation workload tốt hơn một client fetch tất cả documents về Java. Đo theo use case thật.

## 34. Query plan, index và access patterns vẫn là trọng tâm

### 34.1. MongoDB

Query:

```java
repository.findByEmail(email);
```

vẫn cần index trên `email` và unique constraint nếu nghiệp vụ yêu cầu.

### 34.2. Cassandra

Một repository `findByStatus("PAID")` có thể không tương ứng đường truy cập hợp lệ/hiệu quả nếu partition key là `orderId`. Cần bảng theo query hoặc index phù hợp với hệ.

### 34.3. DynamoDB

`Query` với đúng partition key thường hợp lý hơn `Scan` và filter nhiều dữ liệu. Enhanced Client không làm Scan trở nên rẻ.

### 34.4. Redis

Một `GET` theo key hiệu quả, nhưng một `KEYS *` trên production có thể ảnh hưởng lớn. Spring `RedisTemplate` cũng không đổi độ phức tạp của command.

### 34.5. Elasticsearch

Search phải quan sát shard fan-out, mapping, analyzers, deep pagination, index refresh và aggregation cost. Repository query không tự chặn query đắt.

### 34.6. Neo4j

Graph traversals cần điểm bắt đầu/index phù hợp và giới hạn mở rộng. Mapping node không tự tránh supernode traversal khổng lồ.

## 35. Security và vận hành kết nối

### 35.1. Credentials

- Secret manager hoặc platform identity;
- Least-privilege database role/IAM policy;
- Không đưa passwords vào Git, stack trace hoặc sample config production;
- Credential rotation;
- Phân biệt read-only/reporting user và writer.

### 35.2. TLS và endpoint verification

Dùng TLS theo sản phẩm và kiểm tra chứng chỉ. Không tắt hostname verification chỉ để “chạy được”.

### 35.3. Injection

- MongoDB: tránh nhận raw BSON operators không kiểm soát từ client.
- Cassandra: dùng prepared CQL statements.
- Neo4j: parameterized Cypher, không nối chuỗi user input trực tiếp.
- SQL/JDBC: dùng bind parameters khi driver hỗ trợ đúng.
- Redis: validate key namespace và quyền lệnh; không tạo tên key/commands thiếu kiểm soát.

### 35.4. Query budgets

Cần timeouts, limits, max result size và admission control khi có queries đắt. JDBC reporting endpoints không nên dùng cùng credentials/quotas với checkout-critical operations nếu gây noisy neighbor.

### 35.5. Observability

Theo dõi:

- Connection pool in-use/wait;
- Request latency p50/p95/p99;
- Driver timeouts/retries;
- Error codes/throttling;
- Read/write volume;
- Query plan/scan amplification;
- Mapping conversion errors;
- Active sessions/transactions;
- Reactive backpressure/queue length;
- Source–projection lag;
- API business conflicts/idempotency.

Không log raw documents có PII chỉ để debug mapper.

## 36. Kiểm thử tầng tích hợp

### 36.1. Unit test cho mapping

Test `Document`/row ↔ POJO với:

- Null và missing fields;
- Enum unknown;
- Date/time;
- Nested objects;
- Numeric precision;
- Polymorphism;
- Schema evolution;
- ID conversion.

### 36.2. Integration test với database thật

Mock `MongoRepository` chỉ xác nhận service gọi đúng method; **không chứng minh generated query và index đúng**. Cần tests trên database tương thích server version.

### 36.3. Testcontainers khi phù hợp

Có thể dùng Testcontainers cho MongoDB/Redis/Cassandra/Neo4j trong development CI nếu container phù hợp với môi trường. Với managed cloud APIs, cân nhắc local emulator/test account và giới hạn fidelity.

### 36.4. DynamoDB Local không thay cloud behavior

DynamoDB Local hữu ích để test schema/request patterns, nhưng không mô phỏng đầy đủ IAM, global tables, capacity/throttling, latency hoặc regional failover.

### 36.5. Test JDBC bridge

Test SQL dialect, ResultSet column types, `getMetaData`, transactions, pagination, large result streaming và prepared statements trên driver/service thật.

### 36.6. Concurrency tests

Nếu dùng repository `save()` cho state machine, test hai writers cùng sửa version cũ. Kiểm tra `@Version`/CAS hoặc unique constraint ngăn lost updates.

### 36.7. Failure injection

Mô phỏng timeout sau commit, replica failover, pool exhaustion, stale read, retries và duplicate events. Tầng framework không thay các test phân tán.

## 37. Migration: chuyển từ driver gốc sang Spring Data

Một team hiện dùng MongoDB native driver:

```text
Controller -> Service -> MongoCollection<Document>
```

Muốn chuyển sang:

```text
Controller -> Service -> CustomerRepository
                           |
                           +-- MongoTemplate (advanced query)
```

### 37.1. Việc cần giữ ổn định

- Collection name;
- `_id` type;
- Field names;
- BSON numeric/date types;
- Index definitions;
- Write concern/read preference;
- Transaction/session semantics;
- Null/absent field behavior;
- Query results;
- Exception handling;
- Partial update semantics;
- Optimistic concurrency;
- Latency và connection pool behavior.

### 37.2. Tránh migration “đổi import là xong”

Nếu driver cũ ghi `_id` là BSON ObjectId, mapper mới coi nó là String theo convention khác, dữ liệu đọc/ghi có thể sai.

Nếu native code dùng `$inc` để cập nhật counter, chuyển thành `findById` rồi `save()` có thể tạo lost update.

### 37.3. Di chuyển từng đường truy cập

- CRUD đơn giản → repository;
- Complex aggregation → template/native;
- Special transaction or change stream → native adapter nếu abstraction thiếu;
- Mapping common conversions → centralized converter;
- Contract tests để so trước-sau.

### 37.4. Đừng xóa native driver dependency bừa bãi

Spring Data module thường vẫn cần native driver transitively. Việc xóa/trộn versions có thể làm runtime lỗi binary compatibility.

## 38. Có thể dùng JDBC để “tránh vendor lock-in” không?

JDBC cung cấp **giao diện Java chung**, nhưng không giải quyết mọi khác biệt:

1. SQL dialect giữa vendors khác.
2. NoSQL SQL endpoints có semantics/limits riêng.
3. Partition key, TTL, vector search, consistency và transactions không đồng nhất.
4. Nested documents/arrays không map tự nhiên thành rows.
5. Chiến lược index/query execution có thể khác nhiều.
6. Authentication và connection topology vẫn vendor-specific.
7. JDBC driver có thể read-only hoặc không expose native features.

### 38.1. Portability có nhiều mức

- **Compile-time API portability:** cùng `Connection`/`PreparedStatement`;
- **Query syntax portability:** cùng SQL query chạy ở nhiều engines;
- **Data model portability:** cùng schema/nested types;
- **Behavior portability:** cùng transaction/consistency semantics;
- **Operational portability:** cùng deployment, recovery, performance.

JDBC chủ yếu giúp mức đầu tiên, có thể một phần mức thứ hai; không tự cung cấp các mức còn lại.

### 38.2. Abstraction tốt hơn là port theo nghiệp vụ

Ví dụ:

```java
public interface ReservationStore {
    ReservationResult tryReserve(
            String inventoryId,
            String reservationId,
            int quantity
    );
}
```

Implementation có thể dùng DynamoDB `ConditionExpression`, MongoDB conditional update hoặc Cassandra LWT, nhưng **contract `tryReserve` phải nói rõ atomicity/idempotency**.

Điều này tốt hơn một `GenericNoSqlRepository.save(Object)` không biểu diễn được invariant.

## 39. Kiến trúc ports and adapters cho Java NoSQL

Một hệ dễ bảo trì có thể tách:

```text
                       Domain
                         |
                    ReservationPort
                         |
                   Application Service
                         |
                 Infrastructure Adapter
                /          |           \
               v           v            v
          Mongo Native   Spring Data   DynamoDB SDK
                \          |           /
                 +---------+----------+
                           |
                      Database
```

**Domain** không cần biết `Document`, `Bson`, `ResultSet` hoặc AWS `AttributeValue`.

### 39.1. Port diễn đạt nghiệp vụ

```java
public interface InventoryPort {
    ReserveResult reserve(
            String productId,
            String reservationId,
            int quantity
    );

    boolean release(String reservationId);
}
```

### 39.2. Adapter có thể dùng tầng thấp hoặc cao

```text
MongoInventoryAdapter:
    MongoTemplate + atomic update

DynamoInventoryAdapter:
    DynamoDbClient + ConditionExpression

CassandraInventoryAdapter:
    CqlSession + LWT
```

### 39.3. Tránh abstraction phẳng quá mức

Một `save(T)` tổng quát không nói được:

- Có condition check không?
- Dữ liệu có được ghi trong transaction nào?
- Nếu timeout, outcome là gì?
- TTL bao lâu?
- Version nào?
- Có idempotency theo reservationId không?

Port nên thể hiện những bất biến quan trọng thay vì giấu chúng.

### 39.4. Không nhất thiết có bốn lớp cho CRUD nhỏ

Nếu ứng dụng nội bộ chỉ đọc một collection, Spring Data repository gọi trực tiếp từ service có thể đủ. Tạo quá nhiều adapters/generic factories khi không có yêu cầu thực chỉ làm code phức tạp hơn.

## 40. Ma trận chọn giải pháp theo tình huống

| Tình huống | Hướng khởi đầu | Lý do |
|---|---|---|
| Spring Boot CRUD MongoDB đơn giản | `MongoRepository` | Ngắn gọn, typed domain model |
| MongoDB conditional update/bulk/aggregation | `MongoTemplate` hoặc native driver | Kiểm soát query/update rõ |
| MongoDB new server feature chưa có trong Spring Data | Native Java Driver | API mới, native options |
| Java service không dùng Spring | Native driver + codec/mapper | Ít dependency framework |
| Redis cache trong Spring | `StringRedisTemplate`/`RedisTemplate` | Tích hợp conversion/DI |
| Redis advanced pipeline/stream command | Native Lettuce/Jedis hoặc Spring API phù hợp | Điều khiển cụ thể |
| Cassandra query theo partition key, Spring app | Spring Data Cassandra | Mapping và CRUD |
| Cassandra execution profile/LWT/paging đặc thù | `CqlSession` native | Trực tiếp kiểm soát CQL semantics |
| DynamoDB ứng dụng Java | AWS SDK v2 | API native, conditional items |
| DynamoDB typed table mapping | Enhanced Client | POJO/table schema mapping |
| Elasticsearch search DSL, bulk, vector | Native Java API Client | Full feature/native query |
| Search document CRUD trong Spring | Spring Data Elasticsearch | Mapping/repository tiện lợi |
| Neo4j graph domain trong Spring | Spring Data Neo4j | Domain graph mapping |
| Neo4j Cypher nâng cao | Native Neo4j Driver | Kiểm soát queries/transactions |
| BI/reporting SQL trên NoSQL | JDBC nếu có SQL endpoint | Tương thích SQL tooling |
| Checkout/inventory invariant | Native conditional/transaction API | Không chọn chỉ theo framework |
| Nhiều services, payment ngoài DB | Saga/TCC + outbox/idempotency | Không có một local transaction xuyên hệ |

**Cách dùng thực tế thường kết hợp nhiều tầng**, thay vì cố buộc cả codebase chỉ dùng repository hoặc chỉ native SDK.

## 41. Case study: hệ thương mại điện tử dùng nhiều NoSQL

Một hệ có:

```text
                       Java API
                          |
       +------------------+-------------------+
       |                  |                   |
       v                  v                   v
   Customer DB        Inventory DB        Search Index
    MongoDB             DynamoDB          Elasticsearch
       |                  |                   |
       v                  v                   v
  Spring Data Mongo    AWS SDK v2      Elasticsearch Java Client
       |                  |                   |
       +------------------+-------------------+
                          |
                       Event Bus
                          |
                     Redis Cache
                          |
                  StringRedisTemplate
```

### 41.1. Customer profile

CRUD và findByEmail phù hợp Spring Data MongoDB. Có unique index cho email, optimistic locking cho cập nhật đồng thời, partial updates khi cần.

### 41.2. Inventory

Điều kiện `available >= quantity` phải nằm tại DynamoDB item authority. AWS SDK v2 hoặc Enhanced Client giúp gọi conditional writes; dùng một mapper generic không thay invariant.

### 41.3. Search

Sản phẩm index vào Elasticsearch qua outbox/CDC. Search Java API client có thể dùng query DSL/aggregations. Search là projection nên cần freshness SLO và version guard.

### 41.4. Cache

Redis giảm read pressure cho catalog, nhưng không dùng cache stale để quyết định bán đơn vị hàng cuối. `StringRedisTemplate` phù hợp key-value cache đơn giản.

### 41.5. BI

Analyst có thể dùng một SQL/JDBC endpoint nếu search/analytics platform hỗ trợ. Không cho SQL bridge sử dụng credentials có thể mutate inventory authority.

### 41.6. Business workflow

Tạo Order, reserve Inventory, authorize Payment cần một Saga hoặc workflow phù hợp, dù mỗi service bên trong sử dụng Spring Data hay native driver.

## 42. Bài tập thực hành

### Bài tập 1 — Phân lớp

`MongoRepository` gọi MongoDB và chuyển BSON thành `Customer`.

**Câu hỏi:** Có bỏ qua native Java driver không?

**Gợi ý:** Không, Spring Data sử dụng driver bên dưới.

### Bài tập 2 — Mapping vs query

Một query `findByEmail` quét toàn collection.

**Câu hỏi:** Thay mapper có giải quyết không?

**Gợi ý:** Không trực tiếp. Cần index/access path phù hợp.

### Bài tập 3 — Native feature

MongoDB phát hành feature mới, module Spring Data đang dùng chưa expose.

**Câu hỏi:** Hướng xử lý?

**Gợi ý:** Native driver adapter trong cùng service, kiểm tra compatibility.

### Bài tập 4 — POJO codec

Code dùng MongoDB native driver với POJO codec.

**Câu hỏi:** Có phải code đã dùng Spring Data?

**Gợi ý:** Không; mapping có thể nằm trong native driver.

### Bài tập 5 — Spring Data JDBC

Một NoSQL cung cấp JDBC bridge read-only.

**Câu hỏi:** Có nên dùng `Spring Data JDBC` để lưu entity như relational mặc định không?

**Gợi ý:** Không suy; bridge có thể thiếu DML/DDL/transaction semantics.

### Bài tập 6 — JDBC vs native

Elasticsearch JDBC hỗ trợ SQL SELECT, ứng dụng cần custom vector scoring DSL.

**Câu hỏi:** Nên chọn đường nào?

**Gợi ý:** Native search API nếu JDBC SQL endpoint không expose đúng feature.

### Bài tập 7 — JDBC transaction

Một driver JDBC NoSQL có `Connection.setAutoCommit(false)`.

**Câu hỏi:** Có thể mặc định rollback hai documents không?

**Gợi ý:** Không. Phải xem driver/backend transaction support.

### Bài tập 8 — Redis serializer

Một service ghi JSON string, service khác dùng Java binary serializer cho cùng Redis key.

**Câu hỏi:** Điều gì xảy ra?

**Gợi ý:** Deserialize failure hoặc dữ liệu không tương thích; thống nhất encoding.

### Bài tập 9 — Redis cache TTL

Cache key hết hạn thì có đồng nghĩa một Inventory hold authoritative hết hạn không?

**Gợi ý:** Không mặc định. Phải dùng source authority/deadline protocol.

### Bài tập 10 — Cassandra query

`orders_by_id` partition key là `order_id`, developer viết `findByStatus`.

**Câu hỏi:** Derived repository method đảm bảo query tốt không?

**Gợi ý:** Không. Query-driven modeling/partition key phải phù hợp.

### Bài tập 11 — DynamoDB Enhanced Client

Ứng dụng có `@DynamoDbBean`.

**Câu hỏi:** Đây là Spring Data annotation không?

**Gợi ý:** Không; thuộc AWS SDK Enhanced Client.

### Bài tập 12 — DynamoDB Scan

Một table có hàng chục triệu items, code dùng `Scan` rồi filter.

**Câu hỏi:** Mapping library có làm rẻ Scan không?

**Gợi ý:** Không; cần Query/GSI/partition model phù hợp.

### Bài tập 13 — Reactive

Spring WebFlux handler gọi synchronous JDBC trực tiếp trên event-loop.

**Câu hỏi:** Rủi ro gì?

**Gợi ý:** Blocking event-loop làm giảm concurrency; dùng reactive driver hoặc cô lập blocking IO.

### Bài tập 14 — Pool

Ứng dụng tạo `MongoClient` mới cho mỗi request.

**Câu hỏi:** Ảnh hưởng?

**Gợi ý:** Connection churn, handshake cost, tăng connections, mất lợi ích pool.

### Bài tập 15 — Transaction boundary

`@Transactional` trong Order Service gọi Payment Service HTTP.

**Câu hỏi:** Nếu Order DB rollback, charge tự rollback không?

**Gợi ý:** Không; cần idempotent workflow/compensation.

### Bài tập 16 — Spring mapping ID

Native data lưu BSON `ObjectId`, Spring model mới dùng `String id`.

**Câu hỏi:** Cần kiểm tra gì?

**Gợi ý:** Converter/ID mapping và data compatibility khi migration.

### Bài tập 17 — `save()` lost update

Hai clients đọc cùng Customer rồi cùng `save()` bản đầy đủ.

**Câu hỏi:** Có thể mất update không?

**Gợi ý:** Có; dùng version/OCC hoặc partial update.

### Bài tập 18 — MongoTemplate

Cần tăng `reserved` khi `available>=1`.

**Câu hỏi:** Dùng read-modify-save hay atomic update?

**Gợi ý:** Atomic conditional update nếu invariant trên một document.

### Bài tập 19 — Query performance

Native driver benchmark nhanh hơn repository nhưng query khác index.

**Câu hỏi:** So sánh hợp lệ chưa?

**Gợi ý:** Chưa. Cần cùng query shape/data/index/consistency.

### Bài tập 20 — JDBC SQL injection

Vendor JDBC bridge hỗ trợ `PreparedStatement`.

**Câu hỏi:** Nên nối thẳng user input vào SQL không?

**Gợi ý:** Không; dùng parameter binding và xác minh semantics.

### Bài tập 21 — Search consistency

Order commit ở MongoDB, search qua Elasticsearch chưa thấy.

**Câu hỏi:** Spring Data Elasticsearch có làm source transaction sai không?

**Gợi ý:** Không; search projection có refresh/CDC lag riêng.

### Bài tập 22 — Java exception

Spring Data chuyển lỗi native thành `DataAccessException`.

**Câu hỏi:** Có nên catch chung rồi retry mọi lỗi không?

**Gợi ý:** Không; phân biệt duplicate/condition-failed/throttle/network/unknown outcome.

### Bài tập 23 — Migration

Đổi Mongo driver `$inc` sang repository `findById` + `save`.

**Câu hỏi:** Rủi ro?

**Gợi ý:** Lost increments khi concurrent writers; giữ atomic update semantics.

### Bài tập 24 — Port thiết kế theo business

Một interface `GenericNoSqlRepository.save(Object)` được dùng cho inventory reservation.

**Câu hỏi:** Thiếu thông tin gì?

**Gợi ý:** Atomic condition, idempotency, expected version, quantity, outcome.

### Bài tập 25 — Hệ nhiều NoSQL

MongoDB cho Customers, DynamoDB cho Inventory, Redis cho Cache, Elasticsearch cho Search, BI dùng SQL.

**Yêu cầu:** Chọn driver/mapper/Spring Data/JDBC cho mỗi phần và giải thích transaction/freshness boundaries.

**Gợi ý:** Spring Data MongoDB cho CRUD; AWS SDK cho conditional inventory; StringRedisTemplate cho cache; native Elasticsearch client cho DSL; JDBC cho BI khi có SQL endpoint. Workflow xuyên hệ cần Saga/outbox/idempotency.

### Bài tập 26 — Server compatibility

Spring Boot nâng version khiến driver client không còn tương thích với database server cũ.

**Câu hỏi:** Cần kiểm soát gì?

**Gợi ý:** Release matrix, dependency management, staging integration tests, rolling upgrade.

### Bài tập 27 — Neo4j graph query

Team dùng Spring Data Neo4j nhưng một traversal qua supernode quá chậm.

**Câu hỏi:** Đổi sang native driver sẽ chữa gốc vấn đề không?

**Gợi ý:** Không chắc; cần profile Cypher, index và fan-out/graph model.

### Bài tập 28 — JDBC nested types

Một document có nested arrays; SQL JDBC returns JSON text.

**Câu hỏi:** Có thể dùng một `RowMapper` phẳng mà không mất semantics không?

**Gợi ý:** Cần explicit decode/type contract; không tự có relational representation đầy đủ.

### Bài tập 29 — Async retries

Một driver tự retry `increment`, response đầu bị mất.

**Câu hỏi:** Có nguy cơ nhân đôi effect không?

**Gợi ý:** Phụ thuộc retry protocol/driver/database; cần idempotency/operation ID cho business effect không được lặp.

### Bài tập 30 — Kiến trúc mở rộng

Viết `InventoryPort.reserve(productId, reservationId, quantity)` và hai implementations MongoDB/DynamoDB.

**Yêu cầu:** Nêu các contract không được thay đổi khi chuyển backend.

**Gợi ý:** Atomic condition, reservation identity, idempotency, error outcome, deadline, version, read freshness và concurrency behavior.

## 43. Checklist chọn tầng Java cho NoSQL

- [ ] Đã xác định loại database, query language và access patterns.
- [ ] Biết native Java driver/SDK chính thức hoặc được hỗ trợ.
- [ ] Đã kiểm tra server/driver/Spring compatibility matrix.
- [ ] Hiểu driver gốc vẫn tồn tại dưới Spring Data.
- [ ] Phân biệt mapping POJO với transaction/query engine.
- [ ] Không nhầm Spring Data với ORM JPA/Hibernate.
- [ ] Không giả định mọi Spring Data modules có APIs/semantics giống nhau.
- [ ] Đã chọn repository cho CRUD và template/native khi cần.
- [ ] Đã kiểm tra converter cho `_id`, null, dates và numeric precision.
- [ ] Có policy schema evolution và unknown fields.
- [ ] Đã tạo/migrate indexes thật, không chỉ annotation.
- [ ] Có query plan/scan metrics cho các method quan trọng.
- [ ] Không dùng full-document `save()` thay atomic update nếu có contention.
- [ ] Có CAS/version/unique constraint cho business invariants.
- [ ] Có transaction/session phù hợp với engine và scope.
- [ ] Không suy `@Transactional` bao phủ HTTP/broker.
- [ ] Nếu dùng JDBC, có driver/SQL endpoint chính thức hoặc rõ nguồn hỗ trợ.
- [ ] Đã xác minh SQL dialect, DML/transaction, metadata và types của JDBC bridge.
- [ ] Không coi Spring Data JDBC là framework NoSQL phổ quát.
- [ ] Không mặc định JDBC standard API đem lại performance portability.
- [ ] Đã chọn blocking/async/reactive có chủ ý, không block event-loop.
- [ ] Shared clients và pools được quản lý lifecycle đúng.
- [ ] Có TLS, IAM/roles, secrets rotation và query parameterization.
- [ ] Retry chỉ khi an toàn, có idempotency cho unknown writes.
- [ ] Có integration tests trên database/service tương thích thật.
- [ ] Có tests cho concurrency, stale reads, failover, timeouts.
- [ ] Có metrics pool, retries, latency, query cost và mapping errors.
- [ ] Nếu migration, giữ data/schema/transaction semantics và kiểm tra trước-sau.
- [ ] Không chọn một tầng abstraction chỉ vì “code ngắn hơn”.
- [ ] Ports/Adapters thể hiện invariant nghiệp vụ thay vì `save(Object)` mơ hồ.

## 44. Tổng kết

Trong kết nối Java với NoSQL, bốn khái niệm cần phân biệt rõ:

**1. Driver gốc / SDK:** lớp trực tiếp giao tiếp với database/service, expose query/command API, sessions, retries, topology, consistency và tính năng native. Đây thường là lớp nằm dưới những abstraction khác.

**2. Data mapping:** chuyển BSON, JSON, key-value, CQL row hoặc graph record thành POJO và ngược lại. Mapper có thể nằm trong native SDK hoặc Spring Data. Nó **không tự tạo transaction và cũng không sửa query plan xấu**.

**3. Spring Data:** tích hợp với Spring bằng repositories, templates/operations, converters, auditing và transaction integration tùy module. Nó **thường dùng native driver bên dưới** và không xóa đi khác biệt giữa MongoDB, Cassandra, Redis, Neo4j, Elasticsearch.

**4. JDBC khi có:** API Java dạng `Connection`–`PreparedStatement`–`ResultSet`, thích hợp khi NoSQL cung cấp **driver/SQL query endpoint** và workload cần SQL/BI integration. JDBC **không tự biến NoSQL thành relational database** hoặc tạo ACID/joins mà backend chưa hỗ trợ. Spring JDBC, Spring Data JDBC, JPA và R2DBC là những abstraction/stack khác, không được trộn tên.

Lựa chọn thường hợp lý là:

- **Repository** cho CRUD rõ ràng trong Spring.
- **Template/mapper** cho query động và partial update.
- **Native driver/SDK** cho features đặc thù, controls và đường ghi có invariant cần biểu diễn chính xác.
- **JDBC** cho SQL reporting/tooling khi sản phẩm có hợp đồng hỗ trợ phù hợp.
- **Domain ports/adapters** khi cần tách business invariant khỏi công nghệ lưu trữ.

**Nguyên tắc quan trọng nhất:** *Chọn tầng Java theo đúng đường truy cập dữ liệu, ranh giới transaction và đặc tính NoSQL bên dưới. Abstraction tốt giúp code dễ dùng hơn; nó không thay những bảo đảm về partitioning, index, consistency và idempotency mà ứng dụng phải thiết kế.*

