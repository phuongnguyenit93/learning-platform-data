# Chọn driver/SDK theo sản phẩm, giao thức và phiên bản hỗ trợ

## 1. Tình huống mở đầu: kết nối thành công chưa có nghĩa ứng dụng tương thích

Một nhóm Java đang xây dịch vụ lưu đơn hàng. Môi trường phát triển dùng MongoDB, trong khi production chạy một dịch vụ managed quảng bá khả năng tương thích với **MongoDB wire protocol**. Nhóm thêm dependency của MongoDB Java Driver, chạy thử `ping` thành công rồi kết luận toàn bộ ứng dụng đã tương thích.

Sau khi triển khai, một số thao tác mới bộc lộ vấn đề:

- Connection và `find` hoạt động, nhưng một aggregation stage hoặc transaction không được dịch vụ đích hỗ trợ.
- Driver mới dùng một tính năng giao thức mà máy chủ cũ không hiểu.
- URI khai báo `mongodb+srv` nhưng mạng production không phân giải được DNS SRV record.
- Ứng dụng chạy được trên JDK 17, nhưng một thư viện khác kéo về phiên bản Netty/codec không tương thích và phát sinh lỗi runtime.
- Đường ghi có thể được retry tự động, nhưng business operation tạo ID mới mỗi lần thử và tạo dữ liệu trùng.

Những sự cố này có cùng gốc: **chọn được một thư viện có tên phù hợp chưa đủ để chọn đúng driver/SDK cho hệ NoSQL đang dùng**.

Cần xác minh ít nhất năm thứ: **sản phẩm thực tế, API/giao thức endpoint, phiên bản server/managed service, khả năng tương thích với Java và phiên bản driver, cùng các tính năng ứng dụng thực sự sử dụng**.

Bài học thuộc chủ đề **Database No SQL → Kết nối Java**, tập trung vào quyết định lựa chọn client library trước khi viết hàng trăm dòng repository code.

## 2. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **database product**, **API model**, **wire protocol**, **driver**, **SDK**, **framework abstraction** và **giao thức do dịch vụ giả lập**.
2. Lập ma trận hỗ trợ gồm JDK, driver, server/API version, TLS, authentication, topology và tính năng nghiệp vụ.
3. Chọn thư viện Java phù hợp cho MongoDB, Cassandra, Redis, DynamoDB, Elasticsearch/OpenSearch, Couchbase, Neo4j và một số dịch vụ managed.
4. Hiểu vì sao **cùng cú pháp truy vấn** hoặc **cùng giao thức kết nối** không đồng nghĩa hỗ trợ mọi tính năng.
5. Chọn blocking, asynchronous hoặc reactive client theo mô hình concurrency và backpressure.
6. Quản lý dependency/BOM/transitive dependencies trong Maven, Gradle và Spring Boot.
7. Cấu hình connection, timeout, retry, security và vòng đời client đúng phạm vi.
8. Xác minh tương thích bằng integration/contract test thay vì chỉ “khởi tạo client thành công”.
9. Lập quy trình nâng cấp driver có rollback, observability và kiểm soát rủi ro.
10. Tránh các lỗi runtime phổ biến như `NoSuchMethodError`, handshake failure, authentication mismatch và unsupported feature.

## 3. Bảy lớp cần phân biệt khi chọn thư viện

Một ứng dụng Java đi tới dữ liệu qua nhiều lớp:

```mermaid
flowchart TD
    A["Business code: OrderRepository"] --> F["Framework adapter / data access abstraction"]
    F --> D["Java driver hoặc cloud SDK"]
    D --> P["Wire protocol / HTTP / gRPC / binary transport"]
    P --> E["Endpoint: server, proxy, managed gateway"]
    E --> S["Database engine / cluster / service"]
    S --> M["Storage, replication và query semantics"]
```

Các lớp thường bị gọi chung là “driver”, nhưng không phải một.

| Lớp | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Product/service** | Dữ liệu thực sự do hệ nào quản lý? | MongoDB, Cassandra, DynamoDB, Redis |
| **Data/API model** | Ứng dụng thao tác theo mô hình nào? | Document, key–value, wide-column, graph, search |
| **Endpoint/protocol** | Client nói chuyện với server bằng gì? | MongoDB wire protocol, CQL native protocol, RESP, HTTPS, Bolt |
| **Driver/SDK** | Thư viện Java trực tiếp thực hiện protocol/API? | MongoDB Java Driver, Lettuce, AWS SDK |
| **Framework integration** | Mapping repository, template, DI, transactions? | Spring Data MongoDB, Spring Data Redis |
| **Runtime/dependencies** | JDK, classpath, TLS và event loop? | Java 17, Netty, Reactor, Jackson |
| **Operational contract** | Timeout, consistency, retry, pooling và auth? | Majority write, conditional write, IAM, TLS |

Một framework có thể tiện hơn khi viết code, nhưng cuối cùng vẫn dựa trên driver/SDK cụ thể và phiên bản tương thích.

### 3.1. Driver khác SDK ra sao?

**Driver** thường là thư viện nói trực tiếp giao thức hoặc API của database.

**SDK** có thể bao gồm client giao tiếp mạng, request/response models, credential chain, retry, pagination, signing, discovery và tiện ích cloud service.

Ví dụ AWS SDK for Java kết nối DynamoDB qua dịch vụ AWS và cơ chế ký request; bạn không mở socket CQL hay MongoDB wire protocol tới DynamoDB.

Trong thực tế hai từ có thể chồng lấn. Quan trọng là hiểu **thư viện nào sở hữu HTTP/TCP calls, retry, serialization và topology**.

### 3.2. Spring Data không làm mọi NoSQL giống nhau

Một interface repository có thể trông gần giống:

```java
interface OrderRepository {
    Optional<Order> findById(String id);
    void save(Order order);
}
```

Nhưng cùng interface không làm mọi backend hỗ trợ:

- Transaction nhiều entities.
- JOIN và arbitrary sorting.
- Strong read trong mọi secondary index.
- Atomic increment có cùng điều kiện.
- Consistency/quorum tùy chọn.
- Query filtering không tốn scan.
- Unique constraint toàn cầu.

**Abstraction che cú pháp, không xóa semantics của storage engine.**

## 4. Thu thập yêu cầu trước khi mở Maven Central

Trước khi chọn dependency, hãy ghi một bản mô tả ngắn:

```yaml
databaseProduct: MongoDB
deployment: managed
endpointApi: MongoDB wire protocol
serverOrCompatibilityVersion: theo tài liệu deployment
javaRuntime: Java 17
framework: Spring Boot (version cụ thể)
executionStyle: blocking
topology: multi-node replica set
authentication: SCRAM hoặc mechanism được endpoint hỗ trợ
tls: required
operations:
  - find by tenantId
  - conditional upsert
  - aggregate by day
  - change stream
  - multi-document transaction
consistency:
  write: majority
  read: theo yêu cầu nghiệp vụ
network:
  - private endpoint
  - DNS SRV availability
```

Đây là **ví dụ thông tin đầu vào**, không phải cấu hình hợp lệ cho mọi hệ.

### 4.1. Mười câu hỏi quyết định

1. Tên **sản phẩm/dịch vụ** thật sự là gì?
2. Endpoint công bố **API/giao thức** nào?
3. Server hoặc compatibility layer ở **phiên bản/feature level** nào?
4. Client phải chạy trên **JDK nào**?
5. Ứng dụng dùng **Spring Boot/Data phiên bản nào**?
6. Dùng sync, async, reactive hay virtual threads?
7. Cần những API đặc thù nào: transaction, CDC, vector search, bulk write, TTL?
8. Cách xác thực: user/password, SCRAM, IAM, x.509, TLS client cert, OAuth?
9. Đọc/ghi cần consistency, retry/idempotency và độ trễ nào?
10. Ai chịu trách nhiệm cập nhật security patches và theo dõi lifecycle của driver?

Nếu chưa trả lời được những câu này, rất dễ chọn thư viện chỉ dựa trên tên sản phẩm hoặc ví dụ tutorial cũ.

## 5. Bảng định hướng sản phẩm, giao thức và thư viện Java

| Hệ / dịch vụ | Endpoint hoặc protocol chính | Lựa chọn Java thường gặp | Lưu ý |
| --- | --- | --- | --- |
| **MongoDB** | MongoDB wire protocol | MongoDB Java Driver sync / Reactive Streams | Server support, auth, topology, transactions |
| **Apache Cassandra** | CQL native protocol | Cassandra Java Driver phù hợp bản phát hành | CQL protocol, local DC, paging, LWT |
| **Redis** | RESP qua TCP/TLS | Lettuce hoặc Jedis | Cluster, Sentinel, async, pooling, blocking commands |
| **Amazon DynamoDB** | AWS HTTPS service API | AWS SDK for Java v2 | Region, credential chain, capacity, GSI/transaction |
| **Elasticsearch** | HTTP/JSON REST | Elasticsearch Java API Client phù hợp | Client/server version và endpoint capabilities |
| **OpenSearch** | HTTP/JSON REST | OpenSearch Java Client phù hợp | Không đồng nhất vô điều kiện với Elasticsearch |
| **Couchbase** | Native SDK protocols và query services | Couchbase Java SDK | KV, SQL++ query, TLS, cluster feature set |
| **Neo4j** | Bolt | Neo4j Java Driver | `bolt`/`neo4j` URI, routing, transactions |
| **Apache HBase** | HBase client RPC APIs | HBase Java Client theo cluster version | Hadoop dependency và server version |
| **Cloud Bigtable** | Google Cloud service APIs/gRPC | Google Cloud Bigtable Java libraries | Không tự đồng nhất với HBase ở mọi trường hợp |
| **Cloud Firestore** | Google Cloud service API/gRPC | Google Cloud Firestore Java client | Transactions, indexes, IAM, emulator differences |
| **Azure Cosmos DB for NoSQL** | Cosmos DB NoSQL service API | Azure Cosmos Java SDK | Phân biệt với Cosmos MongoDB/Cassandra APIs |
| **Azure Cosmos DB MongoDB API** | MongoDB-compatible endpoint | MongoDB Java Driver nếu mode hỗ trợ | Chỉ tin feature/version matrix của mode |
| **Azure Cosmos DB Cassandra API** | Cassandra-compatible endpoint | Cassandra driver theo hướng dẫn dịch vụ | API compatibility không phải toàn bộ Cassandra |
| **Aerospike** | Native protocol | Aerospike Java Client | Client/server compatibility, policies, TLS |
| **Document-oriented REST service** | HTTP/JSON | Official SDK hoặc HTTP client được hỗ trợ | Auth, ETag, pagination, retries do SDK/ứng dụng đảm nhiệm |

Tên sản phẩm và khả năng hỗ trợ thay đổi theo phiên bản, gói dịch vụ và chế độ deployment. Bảng chỉ là **định hướng ban đầu**; quyết định cuối phải đối chiếu release notes và compatibility documentation của đúng bản triển khai.

### 5.1. Không tồn tại một “NoSQL driver” chung

NoSQL là một nhóm mô hình lưu trữ, không phải một wire protocol thống nhất.

Không thể giả định:

```text
NoSQL Driver -> MongoDB + Redis + DynamoDB + Cassandra
```

và mọi thao tác có cùng consistency/transaction semantics.

Một thư viện HTTP/JDBC wrapper có thể tạo giao diện chung, nhưng phải hỏi: **nó chuyển đổi tính năng nào, giới hạn nào bị che và ai sở hữu lỗi?**

## 6. Chọn đúng API trước khi chọn thư viện

Cùng một nhà cung cấp có thể công bố nhiều API.

Ví dụ một dịch vụ database đa mô hình có các endpoint khác nhau:

```text
Account / service instance
   |
   +--> Native document API
   +--> MongoDB-compatible API
   +--> Cassandra-compatible API
   +--> Graph API
```

Một driver chỉ kết nối được khi **endpoint thực sự nói protocol driver hiểu**.

### 6.1. Nhầm sản phẩm với protocol

Sai tư duy:

> “Tên dịch vụ có chữ MongoDB nên chắc chắn dùng mọi command MongoDB mới nhất.”

Đúng hơn:

> “Endpoint nói MongoDB-compatible protocol ở mức công bố; phải xác minh command/feature support, server API level, auth và lỗi trả về.”

Có thể `ping`, `find`, `insert` đều thành công trong khi transaction, change stream hoặc aggregation tùy stage không khả dụng.

### 6.2. Một protocol có nhiều đời

Một server nói cùng protocol family nhưng phiên bản thấp hơn có thể:

- Không hiểu một command mới.
- Không nhận một option mới.
- Yêu cầu một authentication mechanism khác.
- Không hỗ trợ compression codec mới.
- Không cung cấp transaction hoặc watch API.
- Có giới hạn BSON/JSON/CQL khác.

**Protocol handshake thành công là cần, nhưng chưa đủ cho feature compatibility.**

## 7. Ma trận tương thích: nhiều trục hơn version number

Một compatibility matrix nên có nhiều trục:

| Trục | Ví dụ cần ghi | Câu hỏi kiểm chứng |
| --- | --- | --- |
| **Java runtime** | JDK 11/17/21 | Driver chạy được trên JDK mục tiêu? |
| **Driver/SDK** | Phiên bản và artifact | Bản nào còn hỗ trợ/bảo mật? |
| **Database server** | Major/minor/patch hoặc service mode | Có trong supported range? |
| **Wire/API version** | CQL/REST/Mongo compatibility | Negotiation và commands có hoạt động? |
| **Framework** | Spring Boot/Data/Reactor | Dependency và mapping có tương thích? |
| **Transport/TLS** | TLS policy, proxy, cert | Endpoint yêu cầu gì? |
| **Authentication** | IAM/SCRAM/OAuth/cert | Driver hỗ trợ mechanism và refresh? |
| **Topology** | Standalone, replica, cluster, region | Driver discover/routing đúng? |
| **Features** | CDC, transaction, change streams | Có thật trên server/mode này không? |
| **Deployment** | Managed/VPC/air-gapped | DNS, egress, port và proxy ra sao? |
| **Operational policy** | Consistency, timeout, retry | Defaults có phù hợp nghiệp vụ? |

Một ô “driver version X tương thích với server Y” thường chỉ nói **mức hỗ trợ tổng quát**. Những features cụ thể có thể còn phụ thuộc **server capabilities, service tier và cấu hình**.

### 7.1. Cột thông tin không nên thiếu

Trong quyết định nâng cấp, ghi riêng:

```text
Minimum supported Java
Supported driver branch
Target server API range
Deprecated APIs
End-of-support date
Security/CVE status
Known incompatibilities
Recommended migration notes
Proof from integration tests
```

Không dựa vào ví dụ trên blog đã lâu năm để suy chính sách hỗ trợ hiện tại.

## 8. SemVer không thay thế compatibility notes

Một thư viện công bố `major.minor.patch` nhưng không nhất thiết bảo đảm mọi server/API đều tương thích theo cùng quy tắc.

Cần tách:

1. **Source compatibility:** code cũ có compile với API mới?
2. **Binary compatibility:** bytecode đã compile có chạy với JAR mới không?
3. **Wire compatibility:** client và server trao đổi protocol được không?
4. **Behavioral compatibility:** retry, query, serialization có giữ semantics không?
5. **Operational compatibility:** TLS, pooling, observability và resource usage có thay đổi?
6. **Framework compatibility:** Spring/Netty/Jackson/Reactor có bị lệch phiên bản?

Một update “chỉ đổi dependency” có thể làm application **compile thành công nhưng fail khi gặp một code path hiếm trong production**.

### 8.1. Ví dụ binary compatibility

Một lỗi có thể xuất hiện:

```text
java.lang.NoSuchMethodError:
  some.library.SomeClient.someMethod(...)
```

Nguyên nhân có thể do runtime nạp phiên bản JAR khác phiên bản compiler dùng hoặc các thư viện transitives xung đột.

Không vội kết luận database server lỗi. Cần xem dependency graph, artifact thực được đóng gói và classpath khi chạy.

### 8.2. Patch nhỏ vẫn cần thử

Một bản patch có thể sửa security hoặc behavior. Với SDK dùng network, hãy test:

- Handshake/authentication.
- Basic read/write.
- Query/paging.
- Retry/timeout.
- TLS/proxy.
- Serialization.
- Background refresh/threads.
- Shutdown.

## 9. Quy trình tìm nguồn tương thích đáng tin

Khi cần chọn **phiên bản cụ thể**, thứ tự tham khảo hợp lý:

1. Tài liệu chính thức của database/service **đúng phiên bản**.
2. Compatibility matrix của **official driver/SDK**.
3. Release notes và migration guide cho cả server/client.
4. Framework dependency management/BOM của Spring Boot hoặc nền tảng đang dùng.
5. CVE/security advisories và end-of-support.
6. Test với bản server/managed service giống production.

Không lấy kết quả một package repository làm bằng chứng tính năng. Repository chỉ cho biết artifact tồn tại và metadata; **không khẳng định command X được server Y hỗ trợ**.

### 9.1. Khi tài liệu mâu thuẫn

Ví dụ trang tổng quan nói “hỗ trợ giao thức MongoDB”, nhưng trang compatibility theo mode ghi transaction không có.

Ưu tiên **tài liệu scope hẹp, version-specific và service mode cụ thể**. Nếu vẫn không rõ, thực hiện feature probe trong môi trường thử nghiệm được phê duyệt và mở ticket cho nhà cung cấp thay vì tự suy đoán.

### 9.2. Không đóng đinh “phiên bản mới nhất” vào bài học kiến trúc

Một hướng dẫn bền vững nên mô tả cách chọn version và kiểm tra support hơn là khuyên dùng một số version cố định sau vài tháng đã lỗi thời.

Trong dự án thực, vẫn phải **pin version** hoặc dùng BOM/lockfile có kiểm soát để build có thể tái tạo.

## 10. MongoDB Java Driver: chọn sync hay reactive đúng mục tiêu

MongoDB có driver Java đồng bộ và driver dựa trên Reactive Streams. Các artifact phổ biến trong những dòng hiện đại:

```text
org.mongodb:mongodb-driver-sync
org.mongodb:mongodb-driver-reactivestreams
```

Và các modules core/BSON theo nhóm version tương ứng.

### 10.1. Khi dùng synchronous driver

Phù hợp với ứng dụng:

- Servlet/REST blocking.
- Business logic tuần tự dễ đọc.
- Throughput và concurrency vừa phải.
- Codebase đang dùng Spring Data MongoDB blocking.
- Có connection pool và timeout được kiểm soát.

Ví dụ console Java (driver sync; URI lấy từ môi trường):

```java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import org.bson.Document;

public final class MongoDemo {
    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");

        try (MongoClient client = MongoClients.create(uri)) {
            MongoCollection<Document> orders =
                client.getDatabase("shop").getCollection("orders");

            Document order = orders.find(
                new Document("tenantId", "T01")
                    .append("_id", "O1001")
            ).first();

            if (order != null) {
                System.out.println(order.getString("status"));
            }
        }
    }
}
```

**Quan trọng:** ví dụ tạo rồi đóng client trong `main`. Trong web service, `MongoClient` thường được **dùng chung lâu dài**; không `create()` và `close()` ở mỗi HTTP request.

### 10.2. Khi dùng Reactive Streams driver

Phù hợp khi toàn bộ đường xử lý:

- Dựa trên Reactive Streams/Reactor.
- Cần non-blocking I/O ở scale phù hợp.
- Có cách điều tiết demand và backpressure.
- Không xen blocking calls tùy tiện trên event-loop.

Một Reactive Streams publisher **không tự thực thi** cho đến khi có subscription phù hợp. Ứng dụng phải quản lý cancellation, error signal, resource scope và timeout.

### 10.3. Không trộn sync/reactive thiếu chủ đích

Nếu dùng WebFlux mà repository gọi Mongo sync driver và thực thi trên event-loop, có thể chặn loop. Ngược lại, thêm driver reactive vào một codebase hoàn toàn synchronous không tự tăng throughput.

Hãy chọn theo toàn bộ concurrency model, và kiểm tra Spring Data adapter có yêu cầu đúng driver generation.

### 10.4. Kiểm tra server capabilities

Trước khi dùng:

```text
Transactions
Change streams
Aggregation stages
Retryable writes
Read/write concern
Collation
Atlas/managed features
```

phải đối chiếu phiên bản MongoDB hoặc endpoint tương thích. Một driver hiện đại có thể gửi API hợp lệ về phía client nhưng server đích không hỗ trợ.

### 10.5. Connection URI

Có thể gặp:

```text
mongodb://host:27017
mongodb+srv://cluster.example.net
```

`mongodb+srv` phụ thuộc DNS SRV/TXT resolution và TLS/URI semantics tương ứng. URI trong production cần xử lý percent-encoding nếu chứa ký tự đặc biệt, authentication database, TLS CA và network routes.

Không hardcode user/password vào source, logs hoặc exception trace.

## 11. Cassandra Java Driver: CQL native protocol và local DC

Apache Cassandra dùng CQL native protocol. Driver Java quản lý connection, topology, node discovery, load balancing, prepared statements, paging và consistency policies.

Tên artifact/nhóm phát hành có thể khác giữa **các dòng driver và thời kỳ phát hành**; dự án nên chọn một lineage được hỗ trợ, không trộn hai major generations.

### 11.1. Ví dụ Java cơ bản

Ví dụ với API `CqlSession` thuộc dòng Java Driver tương thích:

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

import java.net.InetSocketAddress;
import java.util.UUID;

public final class CassandraDemo {
    public static void main(String[] args) {
        try (CqlSession session = CqlSession.builder()
            .addContactPoint(
                new InetSocketAddress("127.0.0.1", 9042)
            )
            .withLocalDatacenter("dc1")
            .build()) {

            PreparedStatement ps = session.prepare(
                "SELECT name FROM app.users WHERE user_id = ?"
            );

            Row row = session.execute(
                ps.bind(UUID.fromString(
                    "73c65b1a-8630-44fa-b8c2-0a861d62a130"
                ))
            ).one();

            if (row != null) {
                System.out.println(row.getString("name"));
            }
        }
    }
}
```

Cần thay contact point, local data center, keyspace và schema theo cluster. Ví dụ không mô tả cách cấu hình credentials/TLS/cloud bundle.

### 11.2. Local DC không phải chi tiết trang trí

Driver thường cần biết **local data center** hoặc profile topology tương đương để định tuyến request phù hợp, tránh vô tình gửi xuyên WAN.

Một lỗi cấu hình DC có thể gây timeout, unavailable hosts hoặc tăng cross-region cost dù DNS/port vẫn mở.

### 11.3. Prepared statement và protocol version

Prepared statements, paging và query options phụ thuộc API driver và CQL protocol/capabilities của server. **Không ép protocol version mới hơn chỉ để “nhanh hơn”** nếu deployment không hỗ trợ.

### 11.4. Cloud Cassandra-compatible endpoint

Dịch vụ managed có thể yêu cầu:

- Secure connect bundle hoặc TLS profile đặc biệt.
- Authentication token/mechanism do nhà cung cấp công bố.
- Proxy/port khác cluster tự quản.
- CQL feature subset.
- Consistency level hạn chế.
- Prepared statement behavior đặc thù.

Cùng từ “Cassandra-compatible” không đảm bảo `ALTER TABLE`, LWT, batch hoặc mọi system table có cùng semantics với Cassandra bản tự quản.

## 12. Redis: Lettuce, Jedis và mô hình kết nối

Redis sử dụng RESP protocol với các biến thể theo phiên bản/khả năng server. Hai Java clients phổ biến:

```text
io.lettuce:lettuce-core
redis.clients:jedis
```

Chọn dựa trên:

- Sync/async/reactive nhu cầu thực.
- Redis standalone, Sentinel hay Cluster.
- TLS và auth/ACL.
- Pipeline và blocking commands.
- Threading/pooling.
- Redis server/module commands được sử dụng.
- Spring Data Redis integration.

### 12.1. Lettuce

Lettuce hỗ trợ những mô hình sync/async/reactive phù hợp với driver version, thường dựa trên Netty.

Ví dụ standalone:

```java
import io.lettuce.core.RedisClient;
import io.lettuce.core.api.StatefulRedisConnection;

public final class LettuceDemo {
    public static void main(String[] args) {
        RedisClient client = RedisClient.create(
            "redis://127.0.0.1:6379"
        );

        try (StatefulRedisConnection<String, String> connection =
                 client.connect()) {
            String value = connection.sync().get("product:P100");
            System.out.println(value);
        } finally {
            client.shutdown();
        }
    }
}
```

Trong service, `RedisClient` và những connections được thiết kế để dùng chung theo lifecycle phù hợp. **Không mở connection mới mỗi request** nếu thư viện cung cấp pooling/concurrency model phù hợp.

### 12.2. Jedis

Jedis có API synchronous quen thuộc và các loại connection/client cho standalone, pooled, cluster tùy generation.

Một ứng dụng legacy dùng Jedis có thể vẫn hợp lý nếu:

- Bản driver còn được hỗ trợ.
- Tính năng RESP/TLS/Cluster cần thiết có sẵn.
- Pool đúng size và không chia sẻ connection không an toàn.
- Dependency/framework không bị xung đột.

Không đổi sang một client khác chỉ vì “reactive hiện đại hơn”, nếu workload thực tế không cần và migration rủi ro lớn.

### 12.3. Blocking commands và Pub/Sub

Các lệnh blocking hoặc Pub/Sub có thể cần connection chuyên biệt theo API client. Dùng một connection cho mọi loại thao tác có thể gây head-of-line blocking hoặc lifecycle lỗi.

### 12.4. Redis Cluster và hash slots

Một Redis client hoạt động tốt với standalone **không chứng minh** nó được cấu hình đúng cho Redis Cluster. Cần kiểm tra:

- Slot discovery.
- Redirects `MOVED`/`ASK`.
- Reconnect/failover.
- TLS, auth trên từng node.
- Multi-key commands cùng hash slot khi bắt buộc.
- Topology refresh.
- Cross-slot scripts.

**Client hỗ trợ Cluster** là điều kiện cần; application schema cũng phải phù hợp hash-slot semantics.

## 13. DynamoDB: AWS SDK v2 không phải JDBC driver

DynamoDB là managed service sử dụng API AWS. Java thường dùng nhóm:

```text
software.amazon.awssdk:dynamodb
software.amazon.awssdk:dynamodb-enhanced
```

nằm trong hệ AWS SDK for Java v2, cùng các module HTTP client, auth, region và retry.

### 13.1. Ví dụ synchronous GetItem

```java
import java.util.Map;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.dynamodb.DynamoDbClient;
import software.amazon.awssdk.services.dynamodb.model.AttributeValue;
import software.amazon.awssdk.services.dynamodb.model.GetItemRequest;

public final class DynamoDemo {
    public static void main(String[] args) {
        try (DynamoDbClient client = DynamoDbClient.builder()
            .region(Region.AP_SOUTHEAST_1)
            .build()) {

            GetItemRequest request = GetItemRequest.builder()
                .tableName("Orders")
                .key(Map.of(
                    "PK",
                    AttributeValue.builder().s("ORDER#O1001").build()
                ))
                .consistentRead(true)
                .build();

            var response = client.getItem(request);
            System.out.println(response.item());
        }
    }
}
```

Ví dụ giả định table có **partition key PK duy nhất**; nếu table dùng sort key, request phải truyền cả key schema. Region và table name phải đúng thực tế.

Trong production, dùng một `DynamoDbClient` chia sẻ theo lifecycle của application. SDK mặc định có thể tìm credentials qua **default credentials provider chain**, cần cấp IAM policy tối thiểu theo workload.

### 13.2. Vì sao Enhanced Client?

Enhanced Client hỗ trợ schema/mapping Java bean/record theo API của SDK, giúp giảm boilerplate `AttributeValue` cho những use case thích hợp.

Nhưng Enhanced Client không thay đổi:

- Capacity model.
- Partition key query requirement.
- Consistency của GSI.
- Transaction limits.
- Filter-after-read semantics.
- Conditional write rules.

### 13.3. Sync hay async?

AWS SDK có `DynamoDbClient` và `DynamoDbAsyncClient`. Async cần HTTP transport/runtime và quản lý futures phù hợp.

Không đồng bộ một `CompletableFuture` bằng `.join()` trong event-loop rồi mặc nhiên coi pipeline non-blocking.

### 13.4. `consistentRead` không áp dụng mọi đường đọc

Một GetItem/Query trên base table có thể yêu cầu strong read theo API và cấu hình phù hợp. Nhưng **GSI không hỗ trợ strong-consistent reads theo cùng cách**, và global/multi-region semantics còn phụ thuộc mode.

Chọn SDK đúng không thay đổi guarantee của service.

## 14. Elasticsearch và OpenSearch: đừng chọn client chỉ vì JSON giống nhau

Cả Elasticsearch và OpenSearch đều cung cấp nhiều thao tác qua HTTP/JSON REST, nhưng chúng có **những dòng sản phẩm, API và clients khác nhau**.

Các artifact thường thấy:

```text
co.elastic.clients:elasticsearch-java
org.opensearch.client:opensearch-java
```

Hãy chọn theo **endpoint thực tế và compatibility matrix**, không tự hoán đổi hai clients vì cùng JSON hoặc cùng dùng HTTP.

### 14.1. Các kiểu thư viện

- Java typed client với request/response models.
- Low-level REST/HTTP client.
- Framework integration do cộng đồng hoặc vendor cung cấp.
- Legacy high-level clients có thể đã deprecated trong dòng sản phẩm tương ứng.

Một low-level HTTP client có thể giúp gọi endpoint chưa có model typed, nhưng khi đó application tự sở hữu request JSON, versioning và error handling nhiều hơn.

### 14.2. Kiểm tra những API ứng dụng thật sự dùng

```text
Bulk indexing
Search + aggregations
Scroll / search_after / PIT
Index templates / mappings
Aliases
Vector or k-NN search
Security/auth
Index lifecycle
Task APIs
```

Một managed fork/older version có thể khác tên endpoint, request fields hoặc phản hồi. Không khẳng định “tương thích” sau một lệnh `GET /`.

### 14.3. JSON shape vẫn có vấn đề

Các thay đổi giữa generations có thể ảnh hưởng:

- Typed request models.
- Jackson hoặc JSON-P mapper.
- Response variants.
- HTTP transport classes.
- Deprecations.
- Authentication setup.
- Error mapping.

Nếu một feature quan trọng chưa được typed client hỗ trợ, có thể cân nhắc **client/library version phù hợp hoặc gọi HTTP API được hỗ trợ có kiểm soát**, thay vì cố dùng API không tồn tại.

### 14.4. Search không phải nguồn ghi nghiệp vụ mặc định

Một Search SDK trả indexing success không nhất thiết đồng nghĩa document đã searchable trước refresh. Search index thường là projection của authoritative source, cần revision, retry và rebuild.

## 15. Couchbase Java SDK: KV và query là hai đường khác nhau

Couchbase cung cấp Java SDK cho cluster/bucket/scope/collection và query services. Ví dụ ý tưởng:

```java
import com.couchbase.client.java.Cluster;
import com.couchbase.client.java.Collection;
import com.couchbase.client.java.json.JsonObject;

public final class CouchbaseDemo {
    public static void main(String[] args) {
        String user = System.getenv("COUCHBASE_USER");
        String password = System.getenv("COUCHBASE_PASSWORD");

        Cluster cluster = Cluster.connect(
            "couchbase://127.0.0.1", user, password
        );

        try {
            Collection collection = cluster
                .bucket("shop")
                .defaultCollection();

            JsonObject data = collection.get("ORDER#O1001")
                .contentAsObject();

            System.out.println(data.getString("status"));
        } finally {
            cluster.disconnect();
        }
    }
}
```

Cấu hình production có thể dùng TLS (`couchbases://` khi endpoint hỗ trợ), truststore, multiple bootstrap nodes và timeouts phù hợp.

### 15.1. KV vs SQL++

Dùng `collection.get(id)` khác với query SQL++ trên query service. Chúng có performance/index/consistency semantics riêng.

Một CRUD demo thành công không chứng minh:

- Query index đã sẵn.
- Transaction multi-document hoạt động.
- Durability level đáp ứng mục tiêu.
- Truy cập Scope/Collection được phân quyền.
- Server hỗ trợ feature của SDK version.

### 15.2. SDK environment có lifecycle

Cluster/client object thường quản lý các connections và background resources. Tạo lại mỗi request có thể gây handshake, pool pressure, CPU/GC và chi phí lớn.

## 16. Neo4j: Bolt driver và routing URI

Neo4j Java Driver giao tiếp qua Bolt, không phải JDBC query API thông thường.

Một mẫu:

```java
import org.neo4j.driver.AuthTokens;
import org.neo4j.driver.Driver;
import org.neo4j.driver.GraphDatabase;
import org.neo4j.driver.Session;

public final class Neo4jDemo {
    public static void main(String[] args) {
        String uri = System.getenv("NEO4J_URI");
        String user = System.getenv("NEO4J_USER");
        String password = System.getenv("NEO4J_PASSWORD");

        try (Driver driver = GraphDatabase.driver(
                uri, AuthTokens.basic(user, password))) {
            driver.verifyConnectivity();

            try (Session session = driver.session()) {
                String name = session.executeRead(tx ->
                    tx.run(
                        "MATCH (u:User {id: $id}) RETURN u.name AS name",
                        java.util.Map.of("id", "U01")
                    ).single().get("name").asString()
                );

                System.out.println(name);
            }
        }
    }
}
```

Ứng dụng cần xử lý trường hợp query không trả row thay vì gọi `single()` mù trong production.

### 16.1. `bolt` và `neo4j` schemes

Các URI schemes có thể biểu thị hành vi routing khác nhau tùy driver/server. Hãy chọn theo tài liệu topology:

- Single server.
- Cluster routing.
- TLS certificate scheme.
- Managed endpoint.
- Read/write transactions.

Không đổi URI scheme mà không test discovery và failover.

### 16.2. Session và Driver không cùng lifecycle

`Driver` thường chia sẻ ở cấp application; `Session`/transaction scope thường ngắn hơn. Không tạo Driver cho mỗi query, và không dùng session đồng thời vượt hợp đồng thread safety.

## 17. Managed services có nhiều chế độ tương thích

Những điểm cần nhận diện:

### 17.1. Cosmos DB

Nếu endpoint là **Azure Cosmos DB for NoSQL**, lựa chọn là SDK tương ứng cho API đó.

Nếu endpoint là **Cosmos DB MongoDB-compatible API**, có thể dùng MongoDB driver theo mode/version mà service hỗ trợ.

Nếu endpoint là **Cassandra-compatible API**, có thể dùng Cassandra driver với cấu hình do dịch vụ công bố.

**Ba lựa chọn không hoán đổi chỉ vì cùng là Cosmos DB**.

### 17.2. Google Cloud Firestore

Dùng thư viện client phù hợp với Firestore API và Google Cloud credentials. Không chọn MongoDB driver vì Firestore cũng lưu document.

Chú ý:

- Firestore transaction/batch semantics.
- Compound indexes.
- Emulator behavior.
- IAM/service account.
- Region.
- Timestamp types.
- Pagination.

### 17.3. Cloud Bigtable và HBase

Bigtable và HBase cùng thuộc họ wide-column, nhưng không phải mọi Java API, filter, admin command hoặc cluster behavior đều tương đương.

Chọn chính xác client theo **service endpoint** và phần compatibility mà vendor công bố. Không suy một HBase Java client bất kỳ có thể kết nối managed Bigtable ở mọi version.

### 17.4. Protocol bridge là một lớp rủi ro mới

Nếu giữa driver và database có gateway/proxy/compatibility layer, cần kiểm tra:

```text
Java Driver -> Protocol Bridge -> Storage Engine
```

Bridge có thể khác nguồn gốc ở:

- Error codes.
- Transactions.
- Query parsing.
- Pagination.
- Consistency.
- Server-side timeouts.
- Authentication.
- Compression.
- Topology discovery.

Khả năng tương thích phải kiểm chứng **end-to-end**, không chỉ với driver hoặc chỉ với database gốc.

## 18. Chọn thư viện cho ứng dụng Spring

Một Spring Boot service có thể dùng:

```text
spring-data-mongodb
spring-data-redis
spring-data-cassandra
spring-data-elasticsearch
```

hoặc SDK trực tiếp tùy use case.

### 18.1. Spring Data hỗ trợ điều gì?

- Repository abstractions.
- Object mapping.
- Template operations.
- Dependency injection.
- Một số transaction integration.
- Query creation.
- Configuration/lifecycle.

### 18.2. Spring Data không thể thay server capability

Ví dụ phương thức repository:

```java
List<Order> findByTenantIdOrderByCreatedAtDesc(
    String tenantId
);
```

chỉ thuận tiện nếu backend có index/access path phù hợp. Không phải vì method được sinh tự động mà query sẽ targeted hoặc nhanh.

### 18.3. Kiểm tra dependency management

Spring Boot BOM quản lý những dependency tương thích trong tập nó công bố. Khi bạn **override riêng driver version** trong một framework stack, có thể phá tương thích giữa:

```text
Spring Data module
Driver core
Codec/serialization
Reactive Streams/Reactor
Netty/HTTP transport
```

Nếu cần override vì CVE hoặc feature mới, phải xác minh compatibility cụ thể và chạy integration tests đủ sâu.

### 18.4. Blocking vs reactive ở framework

- Spring MVC/blocking: synchronous driver thường tự nhiên.
- Spring WebFlux: ưu tiên non-blocking đường I/O nếu thiết kế reactive.
- Virtual threads: có thể giúp xử lý blocking I/O theo mô hình Java mới nếu library/framework hỗ trợ, nhưng không tự cải biến driver thành async hoặc giải quyết server bottleneck.

**Không chọn driver reactive chỉ vì muốn có “tốc độ nhanh hơn” khi app đang `.block()` mọi nơi.**

## 19. Maven: quản lý tọa độ và phiên bản

Không thêm cùng lúc ba dòng driver MongoDB thuộc những generations không tương thích chỉ vì các dependencies đều có chữ `mongodb`.

Ví dụ Maven với **một dependency được quản lý phiên bản bởi parent/BOM phù hợp**:

```xml
<dependencies>
    <dependency>
        <groupId>org.mongodb</groupId>
        <artifactId>mongodb-driver-sync</artifactId>
    </dependency>
</dependencies>
```

Nếu không có dependency management, phải khai báo **phiên bản được chọn có kiểm chứng** và đồng bộ related artifacts.

### 19.1. Sử dụng BOM khi vendor hỗ trợ

Một BOM giúp quản lý các modules thuộc cùng hệ:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>software.amazon.awssdk</groupId>
            <artifactId>bom</artifactId>
            <version>${aws.sdk.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>software.amazon.awssdk</groupId>
        <artifactId>dynamodb</artifactId>
    </dependency>
    <dependency>
        <groupId>software.amazon.awssdk</groupId>
        <artifactId>dynamodb-enhanced</artifactId>
    </dependency>
</dependencies>
```

Ở đây `${aws.sdk.version}` là property dự án phải được đặt thành bản đã phê duyệt, không phải một version mặc định.

### 19.2. Xem dependency tree

```bash
mvn dependency:tree
```

Để tìm xung đột có thể lọc theo nhóm artifact phù hợp. Cần xem **effective POM** và artifact cuối đóng gói, vì parent/BOM/transitive dependencies có thể ảnh hưởng phiên bản thực.

### 19.3. Không thêm driver bằng copy toàn bộ JAR

Copy thủ công JAR vào một thư mục `lib/` không quản lý dễ gây:

- Version drift.
- Không có metadata CVE/license.
- Bỏ sót transitive dependencies.
- Không tái tạo được build.
- Bị classpath shadowing.

Ưu tiên dependency management có lock và inventory phù hợp chính sách dự án.

## 20. Gradle: cấu hình dependency có kiểm soát

Ví dụ Gradle Kotlin DSL dùng một tọa độ library với version do catalog quản lý:

```kotlin
dependencies {
    implementation(libs.mongodb.driver.sync)
}
```

Một version catalog có thể chứa tên được chọn:

```toml
[versions]
mongo-driver = "VERSION_APPROVED_BY_PROJECT"

[libraries]
mongodb-driver-sync = {
    module = "org.mongodb:mongodb-driver-sync",
    version.ref = "mongo-driver"
}
```

`VERSION_APPROVED_BY_PROJECT` chỉ là placeholder mô tả. Trong dự án thực cần thay bằng **một version hợp lệ đã kiểm tra**; snippet không phải TOML chạy nguyên trạng cho đến lúc cấu hình phiên bản.

### 20.1. Xem cây dependency

```bash
./gradlew dependencies --configuration runtimeClasspath
```

Tìm lý do một phiên bản được chọn:

```bash
./gradlew dependencyInsight \
  --dependency netty \
  --configuration runtimeClasspath
```

Đây là những lệnh tham khảo cho quá trình phát triển, **không yêu cầu chạy trên module bài học này**.

### 20.2. Dependency constraints và lock

Khi cần reproducible builds:

- Pin/lock resolved dependencies.
- Dùng version catalog hoặc platform/BOM.
- Xem conflict-resolution rules.
- Không dùng `latest.release` hoặc dynamic versions trong artifact quan trọng mà không kiểm soát.
- Review transitive updates trong PR.
- Test fat JAR/container image cuối thay vì chỉ compile.

## 21. Transitive dependencies: điểm hay bị bỏ qua

Driver/SDK có thể kéo theo:

```text
Netty
Jackson / JSON-P
Reactive Streams
Reactor
Netty tcnative/OpenSSL
gRPC / Protobuf
HTTP client
SLF4J / logging
Compression libraries
```

Một ứng dụng đã dùng các dependency ấy cho framework khác có thể có xung đột.

### 21.1. Các triệu chứng thường gặp

```text
NoSuchMethodError
NoClassDefFoundError
ClassCastException
UnsupportedClassVersionError
ServiceLoader configuration error
SSL handshake error
```

Không phải mọi lỗi do driver. Một `UnsupportedClassVersionError` có thể là **JAR được compile bằng Java mới hơn JRE lúc chạy**.

### 21.2. Fat JAR và shading

Một build với shadow/shading có thể relocate packages hoặc vô tình loại bỏ metadata/resources cần cho `ServiceLoader`, codecs, HTTP providers và native transports.

Cần test **artifact đã đóng gói** trong container runtime tương tự production. Compile trong IDE thành công chưa đủ.

### 21.3. Không tự nâng từng module Netty vô cớ

Nếu driver/framework công bố một tập dependencies tương thích, override riêng `netty-common` mà không nâng các module liên quan có thể gây binary mismatch.

Nên đối chiếu BOM/platform version và vendor guidance khi xử lý CVE, thay vì ghép tùy tiện các module theo tên phiên bản lớn nhất.

## 22. Java runtime và các dạng triển khai

Các yếu tố:

- Minimum Java language/runtime level.
- JPMS/module path support.
- Java 17/21 reflection và encapsulation.
- Virtual threads khi có.
- Container CPU/memory limits.
- GraalVM native image support.
- Android/Quarkus/Micronaut/Spring khác nhau nếu ứng dụng dùng.
- TLS provider/certificate store.

### 22.1. Java version khi compile và khi chạy

Ví dụ:

```text
Build JDK = 21
Gradle toolchain target = 17
Production JRE = 17
```

Có thể hợp lệ nếu build target và dependencies thực sự hỗ trợ Java 17. Nhưng nếu driver JAR yêu cầu bytecode Java 21, runtime Java 17 vẫn lỗi dù source code của ứng dụng compile với target 17.

### 22.2. Native image

Một số SDK sử dụng reflection/dynamic proxies/native transports/serialization. Native image cần cấu hình hoặc support cụ thể. Không giả định driver chạy trong JVM thì chạy được nguyên vẹn dưới native image.

### 22.3. Virtual threads

Virtual threads hữu ích cho nhiều blocking tasks theo thiết kế Java phù hợp, nhưng:

- Server vẫn có finite connections và IOPS.
- Driver có thể có pinning/blocking semantics riêng.
- Không tăng write capacity per partition.
- Không xóa yêu cầu timeouts/backpressure.
- Không tự làm một SDK không tương thích thành tương thích.

## 23. Chọn blocking, asynchronous hay reactive

| Kiểu | Cơ chế thường thấy | Phù hợp | Điểm cần lưu ý |
| --- | --- | --- | --- |
| **Blocking sync** | Thread chờ kết quả | Code nghiệp vụ tuần tự, framework blocking | Thread/connection budgets |
| **Async future** | `CompletableFuture` hoặc callback | Nhiều I/O độc lập, SDK async | Error/cancellation propagation |
| **Reactive Streams** | Publisher + demand | Reactive pipeline với backpressure | Không block event-loop |
| **Virtual threads + blocking I/O** | Nhiều virtual threads | Workload phù hợp, Java/runtime hỗ trợ | Connection pool/server saturation vẫn còn |

### 23.1. Một sơ đồ quyết định

```mermaid
flowchart TD
    A["Ứng dụng đang dùng gì?"] --> B{"Có pipeline reactive thực sự?"}
    B -->|Có| C["Dùng driver reactive/async tương thích"]
    B -->|Không| D{"Blocking API đáp ứng SLO?"}
    D -->|Có| E["Giữ synchronous driver với pool phù hợp"]
    D -->|Không| F["Đo bottleneck trước: pool, I/O, server, GC"]
    F --> G["Cân nhắc async/virtual threads và test"]
    C --> H["Backpressure, cancellation, retry"]
    E --> H
    G --> H
```

### 23.2. Async không làm query engine xử lý ít dữ liệu hơn

Nếu query phải scan 10 triệu records, async client chỉ thay đổi cách **ứng dụng chờ**, không tự giảm scan cost. Phải tối ưu shard key, filter, index, pagination và query model riêng.

### 23.3. Tránh callback chồng callback không kiểm soát

Với nhiều async requests, nên giới hạn concurrency. Tạo 100.000 futures gửi cùng lúc có thể làm pool queue/throttle và p99 xấu hơn.

## 24. Connection lifecycle và pooling

Một driver hiện đại thường quản lý:

- TCP/TLS connections.
- Pools per node/endpoint.
- Topology discovery.
- Heartbeats/health checks.
- Credential refresh.
- Event-loop threads hoặc worker pools.
- Buffers/serialization.
- Retry/circuit breaker.

**Client-level object** thường được tạo một lần ở application startup và đóng khi shutdown. **Request/session/transaction object** có vòng đời ngắn hơn.

### 24.1. Anti-pattern: client mỗi request

```java
public Order findById(String id) {
    // KHÔNG NÊN: khởi tạo SDK/connection pool mới
    // cho từng request trong web service.
    try (SomeDatabaseClient client = createClient()) {
        return query(client, id);
    }
}
```

Đoạn code mang tính khái niệm, không phải class compile được. Vấn đề: handshake, TLS, DNS, thread creation, pool warmup và resource churn.

### 24.2. Singleton không đồng nghĩa mọi object thread-safe

Một `MongoClient` hoặc `DynamoDbClient` được thiết kế chia sẻ ở cấp service khác với:

- Transaction session.
- Redis blocking connection.
- Cursor/result iterator.
- Mutable query builder.
- Per-request auth context.

Luôn kiểm tra thread-safety contract của **từng loại object**, không chỉ class tên `Client`.

### 24.3. Close và graceful shutdown

Khi service dừng:

1. Ngừng nhận requests mới.
2. Cho in-flight operations hoàn tất trong deadline phù hợp.
3. Đóng cursors/sessions/streams.
4. Đóng client/pool.
5. Bảo đảm background retry/outbox checkpoint được xử lý đúng.

Không `close()` một singleton client đang được nhiều concurrent requests sử dụng.

## 25. TLS và certificate validation

Một endpoint production thường yêu cầu TLS.

Cần xác minh:

- Scheme/flag bắt TLS.
- Truststore CA.
- Server certificate hostname.
- Client certificate/mTLS nếu có.
- TLS protocol/cipher policy.
- Proxy/load balancer termination.
- Certificate rotation.
- JDK truststore và runtime image.
- DNS name dùng trong certificate có khớp địa chỉ connect.

### 25.1. Không tắt kiểm tra certificate để “sửa lỗi nhanh”

Những cấu hình như “trust all certificates” hoặc bỏ hostname verification có thể biến lỗi deploy thành lỗ hổng MITM.

Trong môi trường test có CA nội bộ, cách đúng là thêm trust material được phê duyệt, không tắt TLS verification toàn cục.

### 25.2. Lỗi handshake cần phân loại

`SSLHandshakeException` có thể do:

- CA không được tin cậy.
- Hostname sai.
- Certificate hết hạn.
- TLS versions/ciphers không giao nhau.
- mTLS thiếu client cert.
- Proxy chặn hoặc thay certificate.
- SNI/ALPN/protocol mismatch ở transport.

Không mặc định cập nhật driver sẽ chữa được mọi lỗi TLS.

## 26. Authentication và credential lifecycle

Các cơ chế tùy sản phẩm:

| Nhóm | Ví dụ | Cần kiểm tra |
| --- | --- | --- |
| User/password | MongoDB SCRAM, Redis ACL, Neo4j | Auth database, roles, rotation |
| Cloud identity | AWS IAM, Google service account, Azure identity | Scope, region/project, token refresh |
| Certificates | mTLS/x.509 | CA, key store, expiration |
| Bearer tokens | Cloud managed gateway | Expiry, refresh, audience |
| API keys | Search/cloud services | Header, privilege, rotation |
| Kerberos/enterprise | Một số cluster | Ticket renewal, Java config |

### 26.1. SDK credential chain

Cloud SDK thường có credential provider chain. Không hardcode access key để “cho chắc” nếu workload có workload identity/role.

Cần test:

- Local dev credentials.
- CI credentials.
- Workload identity ở cluster.
- Permissions chỉ đủ cho table/index/collection cần.
- Token refresh trong service chạy nhiều ngày.
- Auth failure mapping và log redaction.

### 26.2. Không log URI đầy đủ

Một `mongodb://user:password@host` hoặc URL chứa key có thể xuất hiện trong exception. Logs/traces phải scrub credentials, connection strings và request payload nhạy cảm.

### 26.3. Credential rotation

Một client sống lâu phải có kế hoạch khi credential bị rotate: provider refresh, reconnect, secret rotation signal và behavior với in-flight requests.

Một kết nối thành công tại startup không bảo đảm service vẫn xác thực được sau 30 ngày.

## 27. Timeouts: phải phân loại

Đừng dùng một biến `timeout=5000` cho mọi tầng.

| Timeout | Ý nghĩa |
| --- | --- |
| DNS/connect timeout | Mất bao lâu để thiết lập connection |
| TLS handshake timeout | Mất bao lâu cho TLS |
| Pool acquisition timeout | Chờ connection rảnh |
| Request/read timeout | Chờ kết quả operation |
| Server execution timeout | Giới hạn công việc server |
| Transaction timeout | Giới hạn scope transaction |
| Cursor/socket idle timeout | Stream rảnh bao lâu |
| Retry total deadline | Tổng ngân sách các attempts |
| HTTP API deadline | SLO của request người dùng |

### 27.1. Timeout không chứng minh write thất bại

Một write có thể đã commit và response bị mất. Nếu driver hoặc ứng dụng retry, cần stable operation ID/conditional write/idempotency theo business semantics.

Ví dụ nguy hiểm:

```text
Attempt 1: increment inventory reservation count -> committed
Network timeout
Attempt 2: increment again -> duplicate business effect
```

Chọn driver có retryable writes không làm một `INCREMENT` tùy biến mặc nhiên idempotent.

### 27.2. Deadline phải xuyên tầng

Nếu HTTP API có deadline 2 giây nhưng driver chờ 20 giây và retry thêm nhiều lần, backend có thể tiếp tục ghi sau khi client đã bỏ cuộc.

Thiết kế cần timeout budget hợp lý, cancellation propagation theo khả năng SDK và outcome lookup nếu effect đã ambiguous.

## 28. Retry: hiểu defaults và phân loại lỗi

Driver/SDK có thể retry:

- Lỗi network transient.
- Throttling.
- Replica failover.
- Idempotent reads.
- Một số writes theo protocol/transaction semantics.
- Redirect/topology refresh.

Nhưng behavior có thể khác theo **SDK version, mode, operation và config**.

### 28.1. Không bật retry vô hạn

Nên có:

- Bounded attempt count.
- Bounded total deadline.
- Backoff + jitter.
- Retry-after hints khi có.
- Per-operation idempotency.
- Observability of attempts.
- Circuit breaker/admission control nếu thích hợp.

### 28.2. Phân loại exception

| Nhóm lỗi | Hành động |
| --- | --- |
| Validation/payload sai | Không retry |
| Unauthorized/auth failure | Sửa config/credential, không retry nóng |
| Conditional write failed | Đọc lại state, xử lý business conflict |
| Timeout/network after write | Outcome unknown; lookup/retry cùng ID |
| Throttle/capacity | Bounded backoff, xem partition hot |
| Unsupported command/protocol | Chọn feature/client/server tương thích |
| Cursor expired | Tái lập pagination theo contract |
| Topology/failover transient | Driver routing/retry theo capability |
| Schema/serialization error | Sửa mapping, không mù quáng retry |
| Transaction unknown commit | Theo commit retry protocol của engine |

Không dùng `catch (Exception) { retry(); }` cho mọi NoSQL operations.

## 29. Consistency và transaction là thuộc tính của backend

Một driver Java có thể cung cấp method:

```text
transaction()
readConsistency()
writeConcern()
consistentRead()
```

nhưng không đồng nghĩa các method đó có cùng semantics ở mọi database.

Ví dụ:

- MongoDB read/write concern và transaction.
- Cassandra consistency level, LWT/Paxos semantics.
- DynamoDB eventually/strong reads và transaction APIs.
- Redis command atomicity, replication và failover.
- Elasticsearch refresh/search visibility.
- Couchbase durability/transaction support.

### 29.1. `read your writes` không luôn mặc định

Client ghi vào leader rồi đọc một replica/secondary có thể thấy state cũ, tùy policy. Nếu API cần trả ngay kết quả ghi cho cùng session, phải chọn read path/consistency thích hợp.

### 29.2. `majority` không phải cú pháp chung

Không tự chuyển:

```text
MongoDB majority
Cassandra QUORUM
DynamoDB strongly consistent read
```

thành một khái niệm “mức 2” chung. Chúng dựa trên topology, replication và contract khác nhau.

### 29.3. Transaction capability phải được thử đúng use case

Nếu business cần atomic update hai entities, phải chạy test thật:

```text
Write A
Write B
Inject failure
Verify both-or-neither per contract
```

Một tài liệu giới thiệu “supports transactions” có thể chỉ nói một scope hẹp, hoặc yêu cầu topology/version đặc thù.

## 30. Mapping dữ liệu: BSON, JSON, CQL và Java types

Đúng driver vẫn có thể sai schema mapping.

| Java type | Rủi ro |
| --- | --- |
| `String` ID | Mismatch với ObjectId/UUID/binary key |
| `UUID` | Binary representation/order giữa drivers |
| `Instant` | Timezone, precision, server timestamp conversion |
| `BigDecimal` | Decimal precision/range |
| `long` | Overflow hoặc độ lớn số |
| `byte[]` | Binary handling và encoding |
| `List`/`Map` | Nested representation và ordering |
| Enum | Rename enum hoặc unknown values |
| Optional/null | Missing field khác explicit null |
| Timestamp | Source clock và độ phân giải khác nhau |

### 30.1. MongoDB ObjectId

Nếu `_id` lưu `ObjectId`, query bằng chuỗi hex không mặc nhiên match:

```java
new Document("_id", "64...hex...")
```

vì type BSON có thể khác. Cần codec/mapping đúng kiểu ID.

### 30.2. DynamoDB `AttributeValue`

DynamoDB có các types như `S`, `N`, `B`, list/map/sets/boolean/null. Một số value được biểu diễn dạng string trong SDK API, nên serializer cần quản lý decimal/numeric precision hợp lệ.

### 30.3. Cassandra CQL types

CQL partition key, clustering columns, collections và timestamp/UUID mapping phụ thuộc driver codec. Không ép Java DTO mọi kiểu thành String để giảm code nếu làm mất tính đúng đắn.

### 30.4. Schema evolution

Trong rolling upgrade, code cũ và mới có thể cùng chạy:

```text
Writer v2 adds field
Reader v1 sees unknown field
```

Chọn codec/mapper phải có policy về unknown fields, default values và migrations.

## 31. Pagination và streaming: SDK API khác nhau

| Hệ | Cơ chế thường gặp |
| --- | --- |
| MongoDB | Cursor/batch size, sort/index, close cursor |
| Cassandra | Page size, paging state, row iterator |
| DynamoDB | `LastEvaluatedKey`, Query/Scan paginators |
| Elasticsearch/OpenSearch | `search_after`, PIT, scroll theo mục đích |
| Redis | SCAN cursor, stream/group APIs |
| Couchbase | Query row streaming/KV operations tùy SDK |
| Neo4j | Result cursor/stream, session transaction scope |

### 31.1. Không tải hết kết quả theo mặc định

Đoạn code:

```java
List<Order> all = queryEverything().toList();
```

có thể khiến heap phình to khi query trả hàng triệu rows.

Cần xem:

- Page size/fetch size.
- Buffer limit.
- Cursor lifecycle.
- Backpressure.
- Cancellation.
- Timeout.
- Retry và duplicate pages.
- Snapshot/sort stability.

### 31.2. Bản chất cursor khác nhau

Redis SCAN **không phải snapshot traversal** mặc định; pagination trong DynamoDB có semantics riêng về evaluated items/filter; search `search_after` cần stable sort tuple.

Không tạo một interface `nextPage()` rồi giả định mọi backend bảo đảm no-duplicates/no-missing khi dữ liệu thay đổi.

## 32. Topology: standalone, cluster, proxy và multi-region

Driver có thể cần biết:

```text
Seed nodes
Replica set members
Data center/region
Cluster slots
Shard metadata
Leader/read replica routing
DNS SRV
Proxies
```

### 32.1. Endpoint trong local khác production

Local:

```text
127.0.0.1:27017
```

Production:

```text
private DNS endpoint + TLS + multi-node topology
```

Ứng dụng có thể kết nối local tốt nhưng fail khi server trả danh sách nodes nội bộ mà client không route được.

### 32.2. Region locality

Đặt client ở Region A nhưng driver mặc định route reads/coordination tới Region B có thể tăng latency, cost và data sovereignty concerns.

Cần phân biệt:

- Client region.
- Leader region.
- Replica placement.
- Consistency policy.
- Failover routing.
- Multi-region writes conflict handling.

### 32.3. DNS failover

Một SDK có thể cache DNS/topology lâu hơn mong đợi. Test region failover/reconnect và xác minh phiên bản driver có hỗ trợ service discovery thích hợp.

Không biến `connect OK` lúc startup thành bảo đảm failover behavior.

## 33. Kiểm tra feature support bằng contract tests

Một “smoke test”:

```text
Client starts
Ping succeeds
```

chỉ xác minh một phần transport/auth.

Một contract test đầy đủ hơn cho ứng dụng Order có thể gồm:

1. Kết nối qua TLS và credentials production-like.
2. Tạo document/item đúng schema.
3. Đọc theo primary key.
4. Conditional update giữ invariant.
5. Pagination qua nhiều pages.
6. Query/aggregation dùng thực tế.
7. Transaction hoặc batch atomicity theo requirement.
8. Retry sau network timeout.
9. Failover/leader change.
10. Codec timestamp/decimal/UUID.
11. Delete/TTL và read model visibility.
12. Cursor/session close.
13. Concurrent writes tạo conflict.
14. Authentication rotation.
15. Reconnect sau idle time.
16. Observability logs/traces không rò secrets.

### 33.1. Test đúng version

Một test container dùng server mới nhất không chứng minh tương thích với server production cũ. Một emulator cloud không tự có mọi semantics/limit của managed service.

Nên có:

```text
Local unit tests
Integration tests on supported local server version
Staging tests on same managed mode/version as production
Feature-specific fault tests
Canary on production
```

### 33.2. Nên làm feature probe riêng?

Có thể dùng một tập truy vấn không phá dữ liệu hoặc test fixtures được phê duyệt để xác minh API. Không chạy một lệnh ghi nguy hiểm lên production chỉ vì client khởi động cần “tự khám phá capability”.

## 34. Kiểm thử nhiều phiên bản

Khi một SDK cần hỗ trợ nhiều database versions, lập matrix:

| Test case | Server cũ được hỗ trợ | Server hiện tại | Managed compatible API |
| --- | --- | --- | --- |
| Connect/auth/TLS | Phải pass | Phải pass | Phải pass |
| Basic CRUD | Pass | Pass | Pass |
| Conditional writes | Theo feature contract | Theo feature contract | Theo mode |
| Bulk operations | Theo API | Theo API | Theo mode |
| Pagination | Pass | Pass | Pass |
| Transaction | Có/không theo support | Có/không | Có/không |
| CDC/change stream | Có/không | Có/không | Có/không |
| Retry/failover | Test riêng | Test riêng | Test riêng |
| Codec/time/numeric | Pass | Pass | Pass |
| Security/credential rotation | Pass | Pass | Pass |

Không đánh dấu xanh một ô không được kiểm tra. Nếu API không hỗ trợ, dùng **NOT_SUPPORTED** thay vì **PASS**.

### 34.1. Kiểm tra backward và forward

- **Driver mới + server cũ:** cần kiểm tra minimum server support và negotiation.
- **Driver cũ + server mới:** có thể hoạt động cơ bản nhưng thiếu features/security fixes.
- **Driver mới + framework cũ:** compile/runtime conflict.
- **Server upgrade + same driver:** behavior/protocol/authorization có thể thay.

## 35. Observability: nhìn thấy client đang làm gì

Driver/SDK có thể cung cấp metrics, events hoặc instrumentation hooks. Những metric hữu ích:

| Metric | Mục đích |
| --- | --- |
| Connection pool size/in-use/wait | Phân biệt pool bottleneck |
| Connection creation/close | Churn, leak |
| Request p50/p95/p99 | Trải nghiệm và tail latency |
| Server execution vs client wait | Xác định nơi nghẽn |
| Retry attempts by reason | Retry storm |
| Throttled operations | Partition/service capacity |
| Cursor/stream count | Resource leak |
| Failed TLS/auth attempts | Security/config |
| Topology changes/failover | Routing behavior |
| Request timeout count | Deadline misses |
| Operation outcome unknown | Ambiguous writes |
| Pagination pages per request | Fan-out/data volume |
| Bytes sent/received | Cost và amplification |
| Codec/serialization errors | Schema drift |
| Client version deployed | Điều tra rolling upgrade |

Metric names tùy SDK/instrumentation, không có nghĩa hệ phát hành đúng tên trong bảng.

### 35.1. Không log full query secrets

Ví dụ một query chứa tenant ID, email, access token hoặc PII. Driver debug logs có thể vô tình tiết lộ.

Trước khi bật verbose wire logging/profiling trong production, kiểm tra data classification, sampling, access và retention.

### 35.2. Trace span nên có gì?

Một span NoSQL có thể ghi:

```text
db.system
db.operation.name
db.collection.name
peer.service
server.address
retry.count
error.type
```

Tên cụ thể theo OpenTelemetry semantic conventions phiên bản đang dùng; không đưa raw user IDs vào high-cardinality tags.

### 35.3. Phân biệt driver latency và server latency

Nếu:

```text
Client latency p99 = 900 ms
Server execution p99 = 20 ms
Pool wait p99 = 800 ms
```

đổi index hoặc shard key không phải hướng đầu tiên; xem pool/concurrency/retry.

## 36. Security và multi-tenancy

Chọn SDK không chỉ là performance decision.

### 36.1. Least privilege

- Database user chỉ có quyền trên tables/collections cần thiết.
- Cloud role chỉ có actions/resources hợp lệ.
- Read-only analytics service không cần quyền delete.
- Outbox publisher không cần quyền sửa payment ledger.
- Tenant context được enforce ở server side.

### 36.2. Không tin client-supplied tenant ID

Một method:

```java
repository.findByTenantId(userInputTenantId);
```

có thể làm lộ dữ liệu nếu API không xác thực ownership. Framework query derivation **không tự áp tenant authorization**.

### 36.3. Managed identity và rotation

Cho cloud SDK, ưu tiên credentials tạm thời, workload identity và provider chain khi hạ tầng hỗ trợ. Cần đảm bảo service dài hạn refresh được token.

### 36.4. Vấn đề supply chain

Một thư viện có nhiều downloads không tự được bảo mật. Cần:

- Source/release provenance.
- Signed artifact/checksums nếu workflow yêu cầu.
- CVE assessment.
- License review.
- End-of-support.
- SBOM và inventory.
- Update cadence và rollback.
- Repo mirror/proxy tin cậy.

## 37. Dấu hiệu lựa chọn driver sai

| Triệu chứng | Giả thuyết | Điều kiểm tra |
| --- | --- | --- |
| `NoSuchMethodError` | JAR mismatch | Dependency tree/runtime classpath |
| `UnsupportedClassVersionError` | JDK chạy quá cũ | Bytecode level, runtime image |
| Unknown command/option | Server/API không hỗ trợ | Compatibility matrix, feature probe |
| TLS handshake failure | CA/cipher/hostname/mTLS | Transport config, cert chain |
| Authentication failed | Mechanism/roles/credentials | Auth configuration, rotation |
| Connect local OK, cluster fail | Topology discovery/routing | SRV, node addresses, seed list |
| Query timeout sau deploy | Pool, routing, server plan | Metrics + execution plan |
| Async callback không chạy | Không subscribe/await | Reactive/future semantics |
| Application bị deadlock/pin | Blocking trên event-loop | Thread dumps, scheduler |
| P99 cao dù server nhanh | Connection wait/retry | Pool metrics, trace |
| Missing fields | Codec/schema mismatch | Serialized representation |
| Duplicate order sau timeout | Retry không idempotent | Operation IDs, write semantics |
| Redis multi-key CROSSSLOT | Khác hash slot | Cluster/key design |
| Cassandra unavailable/local DC issue | DC/profile sai | Topology and CL |
| Search query feature fails | Client/server API mismatch | Endpoint/version release notes |
| DynamoDB filter quá tốn | Access pattern sai | Query vs Scan, read capacity |
| Throttling tăng sau upgrade | Changed concurrency/retry defaults | SDK config and workload |
| Memory leak | Cursors/sessions/client lifecycle | Heap, resource counts |

Bảng giúp tạo giả thuyết, không phải bằng chứng đủ. Cần thu thập logs, metrics và reproduction.

## 38. Một quyết định mẫu: Java Order Service và MongoDB

Yêu cầu:

```text
JDK 17
Spring MVC
MongoDB replica set
CRUD và aggregate theo tenant
Transaction tạo Order + outbox
500 RPS
P99 dưới SLO được đặt
```

### 38.1. Lựa chọn

- MongoDB synchronous driver hoặc Spring Data MongoDB blocking tương thích.
- Connection pool cấu hình theo concurrency thực.
- Driver version nằm trong compatibility matrix server/JDK/framework.
- Majority write concern hoặc policy durability theo nghiệp vụ.
- Transaction chỉ cho Order+outbox trong phạm vi DB.
- Operation ID idempotency cho CreateOrder.
- Publisher outbox riêng.

### 38.2. Vì sao không cần reactive ngay?

Nếu bottleneck là database plan hoặc thiếu index, reactive driver không làm query ít scan hơn. Với concurrency và p99 trong budget, sync code có thể đơn giản để bảo trì.

### 38.3. Những điều vẫn phải test

- Crash sau DB commit/ACK lost.
- Transaction callback retry.
- Replica failover.
- Connection pool acquisition.
- TLS và credential rotation.
- Query sort/index.
- BSON codecs và schema migration.

## 39. Một quyết định mẫu: Redis cache trong WebFlux

Yêu cầu:

```text
Spring WebFlux
Reactive request chain
Redis Cluster
Hot read keys
TTL và cache invalidation
```

### 39.1. Lựa chọn

- Spring Data Redis reactive adapter tương thích, thường dựa trên client có khả năng reactive.
- Kết nối Redis Cluster đúng topology.
- TLS, ACL và timeout.
- Key design tránh CROSSSLOT khi multi-key operation cần co-location.
- Cache expiry/invalidation semantics theo freshness contract.
- Request coalescing khi hot keys hết TTL.

### 39.2. Kiểm chứng

- Không `.block()` trên event-loop.
- Reactive pipeline có subscription/cancellation đúng.
- Keyspace/slot discovery sau failover.
- Connection reconnect và auth rotation.
- Cache stampede load test.
- Redis không trở thành nguồn authoritative cho stock/payment nếu consistency không đủ.

## 40. Một quyết định mẫu: DynamoDB và serverless Java

Yêu cầu:

```text
Java service trên managed compute
DynamoDB ở region xác định
Get/Put/Query theo partition key
Conditional reservation
Burst traffic
```

### 40.1. Lựa chọn

- AWS SDK for Java v2 phù hợp runtime và deployment.
- IAM role/workload identity, không hardcode keys.
- Client reuse trong execution environment, tránh tạo mỗi invocation nếu platform cho phép.
- Sync hoặc async theo concurrency model.
- Conditional writes với stable operation IDs.
- Retry budget và capacity/throttling metrics.

### 40.2. Những lỗi cần tránh

- Dùng Scan+FilterExpression thay Query đúng key.
- Tưởng `consistentRead(true)` trên mọi GSI.
- Chạy full table scan trong mỗi API request.
- Gộp timeout và conditional conflict thành một retry branch.
- Tưởng tăng tổng capacity luôn chữa hot partition.
- Không kiểm tra behavior của SDK HTTP transport trong cold starts.

## 41. Một quyết định mẫu: chuyển Elasticsearch sang OpenSearch

Đội có ứng dụng dùng một Java typed client và muốn thay endpoint sang hệ mới.

Không nên chỉ sửa:

```text
https://old-search.example
->
https://new-search.example
```

mà coi đã migration xong.

Cần một checklist:

1. Xác định product/engine version và API compatibility.
2. Chọn official client tương ứng.
3. So query DSL, aggregations, templates, mappings.
4. So authentication và TLS.
5. So index lifecycle/aliases và task APIs.
6. So sorting/pagination và consistency.
7. Test typed request/response decoding.
8. Test bulk indexing retry/idempotency.
9. Rebuild index và CDC catch-up nếu cần.
10. Canary search traffic; đo relevance/latency.
11. Có rollback và dual-read comparison khi phù hợp.

**Tương thích HTTP/JSON cơ bản không chứng minh tương đương query behavior, ranking và aggregation.**

## 42. Nâng cấp driver/SDK theo quy trình

### Bước 1 — Lập inventory hiện tại

```text
Driver artifact and version
Transitive transport/codec versions
JDK version
Framework version
Database product + server/API mode
Critical features used
TLS/auth configuration
Connection topology
Retry and timeout policies
```

### Bước 2 — Đọc official compatibility và migration notes

Xem minimum/maximum support, changed defaults, deprecations, security, client config và server capabilities.

### Bước 3 — Chọn một target đã kiểm chứng

Không nâng cả framework, server, driver và schema trong cùng một thay đổi nếu có thể tách, vì khó phân biệt nguyên nhân khi lỗi.

### Bước 4 — Chạy static/dependency checks

Review BOM, classpath, duplicate classes, CVEs, licenses và Java bytecode requirements.

### Bước 5 — Chạy contract tests

CRUD, pagination, codec, aggregation, transaction, timeout, TLS, auth và failover trên deployment giống production.

### Bước 6 — So hành vi retry/consistency

Một default retry thay đổi có thể làm tăng load hoặc double business effect khi app chưa có idempotency.

### Bước 7 — Staging với traffic thực tế mô phỏng

Bao gồm data distribution, hot partitions, large documents và concurrency, không chỉ vài record thử.

### Bước 8 — Canary

Rollout một tỷ lệ nhỏ instances, so:

```text
Error rate
P95/P99
Pool wait
Retry amplification
DB read/write load
CPU/memory/GC
Business correctness
```

### Bước 9 — Rollback ready

Giữ artifact/config cũ có thể triển khai lại. Với schema/event protocol mới, bảo đảm backward compatibility trong rolling upgrade.

### Bước 10 — Ghi lại support matrix

Sau khi xác nhận thành công, cập nhật dependency inventory, runbook, ADR và lịch theo dõi EOL/CVE.

## 43. ADR mẫu cho quyết định chọn driver

Có thể viết Architecture Decision Record:

```markdown
# ADR: Java client cho Order MongoDB

## Context
- Java runtime:
- Framework:
- Database product and API version:
- Required features:
- Topology and region:
- Security requirements:

## Options
1. MongoDB sync driver
2. MongoDB Reactive Streams driver
3. Spring Data MongoDB adapter

## Compatibility evidence
- Official matrix:
- Migration/release notes:
- Contract tests:
- Known unsupported features:

## Decision
- Chosen library and pinned version:
- Reasoning:
- BOM/dependency constraints:

## Operational configuration
- Pool/lifecycle:
- TLS/auth:
- Timeouts/retry:
- Read/write concern:
- Metrics/tracing:

## Risks
- Failover:
- Schema/codec:
- Framework upgrades:
- Managed compatibility gaps:

## Rollback
- Previous version:
- Deployment and validation plan:
```

ADR không cần dài, nhưng phải nêu **căn cứ phiên bản và bằng chứng thử nghiệm**. Nếu người duyệt chỉ thấy “dùng bản mới nhất vì phổ biến”, còn thiếu lý do về sản phẩm/giao thức.

## 44. Quy trình quyết định rút gọn

```mermaid
flowchart TD
    A["Xác định database product / service mode"] --> B["Xác định endpoint API và protocol"]
    B --> C["Ghi JDK + framework + execution model"]
    C --> D["Liệt kê features thực sự cần"]
    D --> E["Tra official compatibility matrix và EOL"]
    E --> F{"Có client được hỗ trợ?"}
    F -->|Không| G["Đổi API/client/feature hoặc service design"]
    F -->|Có| H["Chọn sync/async/reactive phù hợp"]
    H --> I["Pin BOM/dependencies và kiểm tra TLS/auth"]
    I --> J["Integration + fault + version tests"]
    J --> K{"Pass cả behavior contract?"}
    K -->|Không| G
    K -->|Có| L["Canary, observe, rollback plan"]
```

### 44.1. Mẫu bảng để so lựa chọn

| Tiêu chí | Ứng viên A | Ứng viên B |
| --- | --- | --- |
| Official support | Có/không, phạm vi | Có/không, phạm vi |
| Java version | Compatible? | Compatible? |
| Server API range | Documented? | Documented? |
| Required features | Pass/fail | Pass/fail |
| Framework integration | Dễ/khó | Dễ/khó |
| Sync/async behavior | Theo workload | Theo workload |
| Security/auth/TLS | Pass/fail | Pass/fail |
| Retry/consistency | Phù hợp? | Phù hợp? |
| CVE/EOL posture | Rủi ro | Rủi ro |
| Operations/support | Ai sở hữu? | Ai sở hữu? |
| Contract test | Kết quả | Kết quả |

Điều quan trọng không phải “đếm số dấu tick” mà là **loại trừ ứng viên vi phạm một yêu cầu bắt buộc**, ví dụ transaction cần có nhưng backend API không hỗ trợ.

## 45. Những ngộ nhận thường gặp

| Ngộ nhận | Cách hiểu đúng |
| --- | --- |
| “NoSQL có driver chung.” | Mỗi product/API/protocol có client khác |
| “Cùng document model thì dùng chung driver.” | Firestore không tự nói MongoDB wire protocol |
| “Tên service có MongoDB là mọi MongoDB feature hoạt động.” | Compatibility layer có feature subset |
| “Ping thành công là ứng dụng tương thích.” | Phải test feature/semantics thực |
| “Driver bản mới nhất luôn tốt với server cũ.” | Minimum server/API support có thể thay |
| “Semantic version tự bảo đảm wire compatibility.” | Cần docs/matrix |
| “Spring Data làm mọi database giống nhau.” | Abstraction không thay storage semantics |
| “Reactive driver luôn nhanh hơn sync.” | Phụ thuộc toàn pipeline và workload |
| “Async client tránh mọi timeout.” | Server vẫn có capacity/deadlines |
| “Virtual threads thay thế driver async trong mọi trường hợp.” | Có giới hạn transport/pool/backend |
| “Tạo client mỗi request cho an toàn.” | Gây connection churn/pool pressure |
| “Client object nào cũng thread-safe.” | Session/connection/cursor có contracts riêng |
| “Đổi endpoint Elastic→OpenSearch là đủ.” | API/client versions, mappings và behavior khác |
| “Redis Cluster = Redis standalone với nhiều IP.” | Slots, redirects và multi-key limits |
| “DynamoDB là SQL qua JDBC.” | Service API và access-pattern model riêng |
| “DynamoDB GSI có strong read giống base table.” | GSI eventual |
| “Cassandra driver tự biết mọi DC qua một localhost.” | Topology/local DC phải cấu hình đúng |
| “BOM không cần vì Maven tự chọn bản mới nhất.” | Dependency mediation có thể chọn bản không mong muốn |
| “Compile là đủ xác nhận tương thích.” | Runtime/classpath/TLS/feature vẫn có thể lỗi |
| “Tắt TLS verification sẽ sửa connection.” | Tạo rủi ro bảo mật |
| “Retry timeout là an toàn cho mọi write.” | Write có thể đã commit |
| “SDK hỗ trợ transaction nghĩa bao gồm broker.” | Transaction có phạm vi cụ thể |
| “Có cache driver thì source không cần index.” | Cache không thay query/storage design |
| “Emulator pass là production pass.” | Emulator có thể khác service |
| “API version giống nhau thì error mapping giống nhau.” | Managed gateways có thể khác |
| “Tăng pool luôn tăng throughput.” | Có thể làm backend quá tải |
| “Thêm nhiều nodes chữa hot key.” | Một item/partition vẫn có thể là bottleneck |
| “Log toàn bộ connection URI giúp debug tốt.” | Có thể lộ credentials |
| “Một smoke test đủ cho release.” | Cần compatibility contract và fault tests |

## 46. Checklist triển khai

Trước khi chấp nhận một driver/SDK Java cho NoSQL, hãy xác nhận:

- **Đã xác định đúng database product và endpoint API chưa?**
- **Endpoint dùng protocol nào, version/capabilities nào?**
- **Driver đã được nhà cung cấp hỗ trợ cho server/mode đó chưa?**
- **JDK runtime có đáp ứng minimum requirements không?**
- **Framework/BOM có hỗ trợ driver generation được chọn không?**
- **Có trộn nhiều major versions trong classpath không?**
- **Dependency tree và artifact cuối có được kiểm tra không?**
- **Có CVE/EOL/license issues chưa xử lý không?**
- **Tính năng quan trọng có contract tests không?**
- **TLS/hostname/cert/auth được bật đúng và không lộ secrets không?**
- **Region, topology, DNS, proxy và local DC cấu hình đúng không?**
- **Client/pool lifecycle và thread safety có rõ không?**
- **Blocking/async/reactive style có khớp framework không?**
- **Timeout/connection wait/retry budgets có được định nghĩa không?**
- **Write retry có idempotency/unknown outcome handling không?**
- **Consistency/transaction/read replica semantics có được hiểu đúng không?**
- **BSON/CQL/JSON/UUID/Decimal/Instant mapping có được test không?**
- **Pagination/cursor/stream có giới hạn bộ nhớ và đóng tài nguyên không?**
- **Cluster failover/reconnect/credential rotation có được thử không?**
- **Telemetry có pool wait, retry, error reason và p99 không?**
- **Deployment rollout có canary và rollback plan không?**
- **Tài liệu ADR và support matrix được lưu đúng phiên bản không?**

## 47. Bài tập thực hành

### Bài 1 — Chọn client theo protocol

Một managed document service cung cấp endpoint HTTP/JSON riêng và không công bố MongoDB wire protocol.

**Hỏi:** Có nên chọn MongoDB Java Driver chỉ vì dữ liệu dạng document?

**Gợi ý:** Không. Chọn SDK/HTTP API đúng endpoint.

### Bài 2 — Mongo-compatible service

`ping`, `find`, `insert` hoạt động; transaction bị từ chối.

**Hỏi:** Lỗi library hay khoảng trống tương thích nào cần xác minh?

**Gợi ý:** Xem API compatibility mode và transaction support, không suy từ ping.

### Bài 3 — JDK mismatch

Ứng dụng compile trên JDK21 nhưng production JRE11 báo `UnsupportedClassVersionError`.

**Hỏi:** Kiểm tra những gì?

**Gợi ý:** Java bytecode level của app và driver/dependencies, runtime image và toolchain.

### Bài 4 — Binary dependency mismatch

Sau khi nâng driver, ứng dụng báo `NoSuchMethodError` ở Netty.

**Hỏi:** Có nên thay server database không?

**Gợi ý:** Ưu tiên dependency tree, BOM và packaged runtime classpath.

### Bài 5 — Mongo sync hay reactive?

Ứng dụng Spring MVC dùng blocking repositories và đáp ứng SLO.

**Hỏi:** Có bắt buộc chuyển sang reactive driver?

**Gợi ý:** Không. Cân theo workload và độ phức tạp; đo bottleneck trước.

### Bài 6 — WebFlux `.block()`

Team dùng reactive driver nhưng mọi controller gọi `.block()` ngay trên event loop.

**Hỏi:** Rủi ro gì?

**Gợi ý:** Blocking event-loop, giảm lợi ích non-blocking và có thể gây latency.

### Bài 7 — Cassandra local DC

Cluster có DC1/DC2. Driver chọn DC2 dù API chạy gần DC1.

**Hỏi:** Có thể ảnh hưởng gì?

**Gợi ý:** WAN latency/cost, consistency routing và timeout; cấu hình local DC/load balancing.

### Bài 8 — Cassandra-compatible endpoint

Một dịch vụ managed nhận CQL nhưng không hỗ trợ một số LWT/DDL.

**Hỏi:** Chọn driver Cassandra là đủ chưa?

**Gợi ý:** Chưa. Phải xác minh feature subset và protocol/auth.

### Bài 9 — Redis Cluster

Jedis/Lettuce kết nối standalone tốt, nhưng Redis Cluster trả `CROSSSLOT`.

**Hỏi:** Do server hỏng không?

**Gợi ý:** Kiểm tra hash slots, multi-key semantics và cluster client configuration.

### Bài 10 — Redis blocking command

Một service dùng cùng connection cho GET thông thường và blocking pop lâu.

**Hỏi:** Vấn đề gì có thể xảy ra?

**Gợi ý:** Head-of-line blocking; cần connection/lifecycle phù hợp.

### Bài 11 — DynamoDB strong read

Application bật `consistentRead=true` cho truy vấn GSI và gặp lỗi.

**Hỏi:** Vì sao?

**Gợi ý:** GSI không hỗ trợ strongly consistent reads theo API chuẩn.

### Bài 12 — DynamoDB Scan

Một team chọn SDK đúng nhưng API dùng Scan+Filter mỗi request.

**Hỏi:** Driver mới hơn có tự sửa performance không?

**Gợi ý:** Không. Cần partition-key Query/GSI/read model.

### Bài 13 — AWS credential chain

Local chạy nhờ profile cá nhân, production không có access key trong environment.

**Hỏi:** Cần làm gì?

**Gợi ý:** Cấp workload identity/role IAM và quyền tối thiểu, test provider chain.

### Bài 14 — Elasticsearch vs OpenSearch

Một typed Elasticsearch client cũ được trỏ vào cluster OpenSearch mới.

**Hỏi:** Các điểm phải xác minh?

**Gợi ý:** Product-specific client, API versions, query models, security, mappings và feature tests.

### Bài 15 — Couchbase SDK

KV GetItem hoạt động nhưng SQL++ query thất bại vì thiếu index/quyền.

**Hỏi:** Có chứng minh Java SDK không tương thích không?

**Gợi ý:** Chưa; kiểm tra query service, index và RBAC.

### Bài 16 — Neo4j routing

Ứng dụng dùng URI dành cho single instance trong khi production chạy cluster routing.

**Hỏi:** Rủi ro?

**Gợi ý:** Không route đúng leader/read replicas hoặc failover; xem URI scheme và driver support.

### Bài 17 — URI và TLS

`mongodb+srv` fail trên production nhưng `mongodb://localhost` chạy local.

**Hỏi:** Điều gì cần kiểm tra?

**Gợi ý:** DNS SRV/TXT, network/proxy, TLS CA, hostname, URI options.

### Bài 18 — Client per request

Service tạo `DynamoDbClient` trong mỗi request HTTP.

**Hỏi:** Những vấn đề có thể thấy?

**Gợi ý:** HTTP connection churn, cold setup, threads/buffers, GC/latency; reuse client.

### Bài 19 — Session thread safety

Team chia sẻ một transaction session giữa 100 requests đồng thời.

**Hỏi:** Có thể suy nó thread-safe vì Client thread-safe không?

**Gợi ý:** Không. Kiểm tra contract riêng của session/transaction.

### Bài 20 — Timeout và retry

Driver timeout sau khi gửi conditional write; API tạo request ID mới cho retry.

**Hỏi:** Rủi ro gì?

**Gợi ý:** Kết quả ghi cũ có thể đã commit; retry phải giữ operation identity.

### Bài 21 — `Instant` serialization

Java ghi timestamp độ phân giải nanosecond, DB lưu millisecond.

**Hỏi:** Có thể round-trip chính xác mọi chữ số không?

**Gợi ý:** Không nếu storage mất precision; test mapping và comparison.

### Bài 22 — Emulator

DynamoDB Local test pass; production throttle hot key.

**Hỏi:** Vì sao test local chưa đủ?

**Gợi ý:** Managed capacity/partition throttling và topology khác emulator.

### Bài 23 — Gradle version conflict

Build có hai dependencies kéo hai versions `netty-common`.

**Hỏi:** Làm sao truy nguyên bản được chọn?

**Gợi ý:** `dependencies`, `dependencyInsight`, BOM/constraints và runtimeClasspath.

### Bài 24 — Test server mới nhất

CI chỉ test MongoDB phiên bản mới nhất, còn production dùng một phiên bản cũ được hỗ trợ.

**Hỏi:** Đủ chưa?

**Gợi ý:** Chưa; test đúng version/capability và migration path.

### Bài 25 — Security

Để xử lý TLS error, developer bật trust-all certificates.

**Hỏi:** Có nên đưa production không?

**Gợi ý:** Không. Sửa CA/hostname/mTLS/cipher config đúng.

### Bài 26 — Canaries

Nâng SDK thành công trong staging nhưng p99 production tăng, DB QPS cũng tăng.

**Hỏi:** Điều tra gì?

**Gợi ý:** Changed retry defaults, concurrency/pool, timeout, query behavior, trace.

### Bài 27 — Managed API mismatch

Một dịch vụ tên Cosmos DB có native NoSQL API và MongoDB-compatible API.

**Hỏi:** Dùng cùng Java SDK cho cả hai được không?

**Gợi ý:** Không tự động; chọn client theo endpoint API/mode.

### Bài 28 — Pagination

MongoDB cursor và DynamoDB `LastEvaluatedKey` đều trả trang dữ liệu.

**Hỏi:** Có thể coi cả hai là snapshot cursor giống hệt nhau không?

**Gợi ý:** Không; semantics khác, cần consistency và pagination contract riêng.

### Bài 29 — ADR

Team chọn thư viện vì có nhiều GitHub stars.

**Hỏi:** ADR còn thiếu gì?

**Gợi ý:** Support matrix, protocol/API, server version, JDK/framework, security, feature tests, rollback.

### Bài 30 — Thiết kế thực tế

Một ứng dụng Java cần MongoDB cho Orders, Redis Cluster cache, DynamoDB cho user preferences và OpenSearch cho search.

**Hỏi:** Hãy đề xuất mỗi SDK/driver, lifecycle, sync/async choice, secrets/TLS, consistency, retry và test plan.

**Gợi ý:** Chọn official libraries theo từng API; có client/pool per backend, idempotent writes, Redis slot-aware client, DynamoDB SDK v2, search index eventual và versioned projections, BOM/dependency tests, staging/canary.

## 48. Kết luận

**Chọn driver/SDK Java cho NoSQL là một quyết định tương thích nhiều lớp, không phải thao tác tìm dependency có tên giống database.** Trước khi chọn, phải xác định **sản phẩm và API endpoint thật**, wire protocol/feature level, JDK/framework, runtime style, topology, TLS/auth và khả năng transaction/consistency mà ứng dụng yêu cầu.

MongoDB, Cassandra, Redis, DynamoDB, Elasticsearch/OpenSearch, Couchbase, Neo4j và các dịch vụ managed có **client libraries, cách phân trang, retry, security và semantics riêng**. Một `ping` thành công hoặc một CRUD demo chạy được không bảo đảm aggregation, failover, change stream hay idempotent business write cũng đúng. Bên cạnh driver version, còn phải kiểm tra BOM, transitive dependencies và artifact runtime thực tế.

Quy trình bền vững là **lập ma trận tương thích từ tài liệu chính thức, pin dependency, kiểm thử feature-specific contracts trên đúng deployment, dùng client theo lifecycle phù hợp, cấu hình bảo mật và retry có chủ đích, theo dõi lỗi trong canary và luôn giữ đường rollback**. Chọn đúng thư viện giúp Java kết nối được với NoSQL; hiểu đúng **protocol, version và behavioral guarantees** mới giúp ứng dụng vận hành an toàn.
