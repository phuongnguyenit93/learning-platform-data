# Truy cập kho phi quan hệ qua API và driver tương ứng

Không phải dữ liệu nào trong một ứng dụng Java cũng phù hợp để truy cập bằng JDBC và câu lệnh SQL. Một hệ thống bán hàng có thể lưu hồ sơ sản phẩm dạng tài liệu, dùng kho key–value cho cache, ghi chuỗi sự kiện với tốc độ cao vào kho wide-column, lập chỉ mục tìm kiếm toàn văn và lưu quan hệ kết nối phức tạp trong cơ sở dữ liệu đồ thị. Mỗi hệ lưu trữ cung cấp **mô hình dữ liệu, API, driver và bảo đảm nhất quán** riêng.

Đây là bài học thuộc chương **Hệ sinh thái Java** của module **DATA_PERSISTENCE_FUNDAMENTALS**. Mục tiêu không phải học thuộc tên thư viện, mà là **chọn đúng cách truy cập kho phi quan hệ từ Java**, xây dựng ranh giới persistence, quản lý client và tài nguyên, hiểu giao dịch/cô lập/độ bền, xử lý lỗi kết nối và thử lại an toàn. Một driver chỉ giải quyết việc giao tiếp với hệ lưu trữ; nó **không tự làm cho mô hình dữ liệu hoặc nghiệp vụ trở nên đúng**.

## 1. Kho phi quan hệ là gì và vì sao không có một JDBC chung cho mọi kho?

“Phi quan hệ” (*non-relational*, thường gọi chung là *NoSQL*) là nhóm hệ lưu trữ không lấy mô hình bảng quan hệ cùng phép JOIN và SQL chuẩn làm giao diện chính. Đây **không phải** một loại database duy nhất. Các hệ NoSQL rất khác nhau về cách lưu, truy vấn, giao dịch, phân phối dữ liệu và mục tiêu hiệu năng.

| Nhóm lưu trữ | Ví dụ công nghệ | Đơn vị dữ liệu/truy vấn nổi bật | Java API thường dùng |
| --- | --- | --- | --- |
| **Document** | MongoDB | Tài liệu BSON/JSON-like, filter, aggregation, index | MongoDB Java Sync/Async/Reactive Streams Driver |
| **Key–value / cache** | Redis | Khóa và các kiểu string, hash, set, sorted set, stream | Lettuce hoặc Jedis |
| **Wide-column / phân tán theo partition** | Apache Cassandra | Bảng truy vấn theo partition key và clustering key, CQL | Cassandra Java Driver |
| **Graph** | Neo4j | Node, relationship, pattern matching bằng Cypher | Neo4j Java Driver |
| **Search engine** | OpenSearch, Elasticsearch | Tài liệu được lập chỉ mục, tìm kiếm toàn văn, aggregation | Java API Client tương ứng qua HTTP |
| **Object storage** | API tương thích S3 | Object theo bucket/key, metadata, stream nội dung | AWS SDK for Java hoặc SDK nhà cung cấp |

Object storage và search engine thường được sử dụng **bên cạnh** các database giao dịch; không nên coi mọi hệ trong bảng là lựa chọn thay thế trực tiếp cho một RDBMS.

Một số hệ NoSQL có SQL-like query hoặc JDBC wrapper, nhưng driver chuyên dụng thường bộc lộ đầy đủ hơn các khả năng đặc thù: filter theo BSON, atomic command, consistency level, cursor, graph traversal hoặc search aggregation. Chọn JDBC wrapper chỉ vì quen thuộc có thể **che mất semantics quan trọng**.

**Câu hỏi phải trả lời trước khi chọn driver:** hệ lưu trữ nào là *source of truth*, dữ liệu có hình dạng gì, thao tác đọc/ghi chủ yếu ra sao, yêu cầu atomicity và latency thế nào, và mất kết nối sau ghi sẽ được xử lý ra sao?

## 2. Nhìn đường đi của một yêu cầu Java

Một lớp nghiệp vụ không nhất thiết phải biết trực tiếp `MongoCollection`, `RedisCommands`, `CqlSession` hay `Neo4j Driver`. Thông thường nên tách:

~~~mermaid
flowchart TD
    A[HTTP Controller / Message Consumer] --> B[Application Service]
    B --> C[Domain và hợp đồng Repository / Port]
    C -. được triển khai bởi .-> D[Mongo / Redis / Cassandra / Graph Adapter]
    D --> E[Driver / Java SDK]
    E --> F[(Kho dữ liệu chuyên biệt)]
    B --> G[Transaction / Idempotency / Outbox policy]
~~~

Ví dụ một application service chỉ cần năng lực `reserveIfAvailable(productId, quantity)`. MongoDB adapter có thể dùng một lệnh cập nhật tài liệu có điều kiện, Redis adapter có thể dùng command/script nguyên tử theo yêu cầu, còn hệ quan hệ có thể dùng `UPDATE ... WHERE stock >= ?`. **Hợp đồng giống về ý nghĩa không có nghĩa mọi backend đều có cùng bảo đảm.** Nếu một backend không thể thực hiện nguyên tử hoặc bền vững như hợp đồng yêu cầu, phải sửa thiết kế, không chỉ thay thư viện.

Một cách phân trách nhiệm:

- **Domain/application:** ràng buộc nghiệp vụ, quyền truy cập, idempotency, ranh giới thao tác và lựa chọn nguồn dữ liệu chính.
- **Repository/port:** định nghĩa đầu vào, kết quả, lỗi, tính nhất quán và đơn vị nguyên tử cần được bảo vệ.
- **Adapter:** chuyển object miền thành lệnh phù hợp với kho; đọc kết quả, chuyển lỗi driver, quản lý session/cursor.
- **Driver/SDK:** kết nối, giao thức, định tuyến, pooling, serialization, timeout và một phần chính sách retry.
- **Database:** áp dụng những bảo đảm thật sự về atomicity, consistency, durability và replication.

## 3. Chọn thư viện và tương thích phiên bản

Một số tọa độ phụ thuộc thường gặp trong ứng dụng Java:

| Kho | Ví dụ artifact | Ghi chú khi tích hợp |
| --- | --- | --- |
| MongoDB | `org.mongodb:mongodb-driver-sync` | Có nhiều API sync/async/reactive khác nhau; chọn một mô hình nhất quán với kiến trúc |
| Redis (Lettuce) | `io.lettuce:lettuce-core` | Hỗ trợ sync, async, reactive trên nền kết nối Redis |
| Redis (Jedis) | `redis.clients:jedis` | Có các API kết nối/pool riêng; không trộn ví dụ của Lettuce và Jedis |
| Cassandra | `com.datastax.oss:java-driver-core` ở dòng driver 4.x tương ứng | Kiểm tra dòng driver được duy trì, namespace và mức tương thích với cluster |
| Neo4j | `org.neo4j.driver:neo4j-java-driver` | Làm việc với Bolt, session và transaction |
| OpenSearch | `org.opensearch.client:opensearch-java` | API và phiên bản client phải phù hợp server |
| Elasticsearch | `co.elastic.clients:elasticsearch-java` | Client không đồng nhất với OpenSearch, dù có nhiều khái niệm tương tự |
| S3 | `software.amazon.awssdk:s3` | SDK cho object storage, không phải JDBC database driver |

Các tên trên là **ví dụ nhận diện thư viện**, không khóa vào một số phiên bản. Cần dùng version/BOM do dự án quản lý và kiểm tra tài liệu tương thích **driver ↔ server ↔ JDK ↔ framework** trước khi nâng cấp. Một SDK quá cũ có thể thiếu tính năng hoặc bản vá bảo mật; SDK mới hơn cũng có thể đổi package/API.

Ví dụ khai báo dependency bằng Gradle theo version catalog của dự án:

~~~kotlin
dependencies {
    implementation(libs.mongodb.driver.sync)
    implementation(libs.lettuce.core)
    // Chỉ khai báo các driver ứng dụng thực sự cần.
}
~~~

Đoạn trên **giả định** `libs.mongodb.driver.sync` và `libs.lettuce.core` đã được định nghĩa trong version catalog của project; đây không phải tên mặc định có sẵn ở mọi dự án. Không nên thêm hàng loạt driver chỉ vì bảng so sánh có liệt kê: mỗi driver làm tăng bề mặt cấu hình, lỗi và bảo trì.

## 4. MongoDB Java Sync Driver: truy vấn tài liệu

MongoDB lưu tài liệu BSON, thường được thao tác qua `MongoClient`, `MongoDatabase` và `MongoCollection`. Một mẫu sử dụng:

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import org.bson.Document;

public class MongoBootstrap {
    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException("Thiếu MONGODB_URI");
        }

        // Ví dụ chạy độc lập. Trong service, tạo client một lần lúc startup.
        try (MongoClient client = MongoClients.create(uri)) {
            MongoDatabase db = client.getDatabase("catalog");
            MongoCollection<Document> products =
                    db.getCollection("products");
            System.out.println("Collection: " +
                    products.getNamespace().getCollectionName());
        }
    }
}
~~~

`MongoClient` được thiết kế để **tái sử dụng và quản lý kết nối**. Trong web service, nên tạo nó một lần ở mức application/container và đóng khi ứng dụng tắt, không mở/đóng một `MongoClient` cho mỗi HTTP request. Driver có cơ chế pooling, khám phá topology và quản lý socket; khởi tạo client liên tục gây chi phí không cần thiết.

### 4.1. Filter và mapping kết quả

Giả sử tài liệu sản phẩm có các field `_id`, `tenantId`, `name` và `available`:

~~~json
{
  "_id": "p-42",
  "tenantId": "tenant-501",
  "name": "Bàn làm việc",
  "available": 12
}
~~~

Repository có thể dùng filter builder thay vì tạo truy vấn JSON bằng nối chuỗi:

~~~java
import static com.mongodb.client.model.Filters.and;
import static com.mongodb.client.model.Filters.eq;
import static com.mongodb.client.model.Filters.gte;
import static com.mongodb.client.model.Updates.inc;

import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.result.UpdateResult;
import java.util.Optional;
import org.bson.Document;

public final class MongoProductRepository {
    private final MongoCollection<Document> products;

    public record ProductView(String id, String name, int available) {}

    public MongoProductRepository(MongoClient client) {
        this.products = client.getDatabase("catalog")
                .getCollection("products");
    }

    public Optional<ProductView> findById(String tenantId, String id) {
        Document doc = products.find(and(
                eq("_id", id),
                eq("tenantId", tenantId))).first();
        if (doc == null) {
            return Optional.empty();
        }
        // Schema được xác thực: available là số nguyên, name là String.
        return Optional.of(new ProductView(
                doc.getString("_id"),
                doc.getString("name"),
                doc.getInteger("available")));
    }

    public boolean reserve(String tenantId, String id, int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity phải dương");
        }
        UpdateResult result = products.updateOne(
                and(eq("_id", id), eq("tenantId", tenantId),
                    gte("available", quantity)),
                inc("available", -quantity));
        return result.getModifiedCount() == 1;
    }
}
~~~

Ví dụ `reserve()` chỉ thay đổi **một tài liệu** và gắn điều kiện `available >= quantity` ngay trong thao tác cập nhật. MongoDB cung cấp atomicity cho cập nhật **một document**; điều đó phù hợp khi bất biến tồn kho nằm trong document đó. Đây **không** là giao dịch nguyên tử giữa cập nhật tồn kho với tạo đơn hàng ở collection khác.

Lưu ý:

- Nếu dữ liệu không có field `available` đúng kiểu, việc đọc bằng `getInteger` có thể lỗi hoặc giá trị `null` không phù hợp; adapter phải kiểm soát schema và mapping.
- Dùng `tenantId` đến từ **ngữ cảnh xác thực**, không lấy một tenant ID tùy ý từ input chưa được ủy quyền.
- Các method của driver có thể ném lỗi kết nối, timeout, lỗi xác thực hoặc lỗi ghi; `Optional.empty()` chỉ dùng cho trường hợp **không tìm thấy**, không dùng để nuốt lỗi hạ tầng.
- Lệnh ghi có thể có retry behavior do driver/config quy định; không đồng nhất một lệnh ghi idempotent với một workflow chứa nhiều side effect.

### 4.2. Cursor và giao dịch MongoDB

`find(...).first()` tiện cho truy vấn một tài liệu. Với nhiều kết quả, có thể dùng `MongoCursor` và đóng bằng `try-with-resources`:

~~~java
import com.mongodb.client.MongoCursor;

try (MongoCursor<Document> cursor = products
        .find(eq("tenantId", tenantId)).iterator()) {
    while (cursor.hasNext()) {
        Document product = cursor.next();
        processProduct(product);
    }
}
~~~

Đừng giữ cursor khi gọi HTTP hoặc làm việc kéo dài; tránh tải toàn bộ collection nếu cần phân trang.

MongoDB còn hỗ trợ **transaction nhiều tài liệu** trong những cấu hình triển khai đáp ứng yêu cầu. Khi cần thao tác nhiều collection nguyên tử, phải dùng session/transaction thích hợp và xét write concern, retry transaction cùng những giới hạn vận hành. Không suy rằng `updateOne()` tự tạo transaction xuyên collection, và không dùng transaction dài cho tác vụ bên ngoài DB.

## 5. Redis từ Java qua Lettuce: thao tác key–value

Redis có các kiểu dữ liệu và lệnh phù hợp với cache, counter, queue-like stream và các cấu trúc truy cập nhanh. Java có thể dùng **Lettuce** hoặc **Jedis**. Ví dụ sau dùng Lettuce; API và cách quản lý kết nối của hai thư viện **không giống nhau**.

~~~java
import io.lettuce.core.RedisClient;
import io.lettuce.core.api.StatefulRedisConnection;
import io.lettuce.core.api.sync.RedisCommands;

public final class RedisExample {
    public static void main(String[] args) {
        String uri = System.getenv("REDIS_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException("Thiếu REDIS_URI");
        }

        RedisClient client = RedisClient.create(uri);
        try {
            try (StatefulRedisConnection<String, String> connection =
                         client.connect()) {
                RedisCommands<String, String> redis = connection.sync();

                redis.setex("cache:product:p-42", 60, "available=12");
                String cached = redis.get("cache:product:p-42");
                Long newCount = redis.incr("metrics:product:p-42:views");

                System.out.println(cached + " / views=" + newCount);
            }
        } finally {
            client.shutdown();
        }
    }
}
~~~

Đây là chương trình chạy độc lập. Trong service, nên cấu hình **RedisClient** và chiến lược kết nối/pooling ở mức ứng dụng, đóng lúc shutdown; không khởi tạo client cho từng request. Lettuce hỗ trợ API sync, async, reactive với các quy tắc thread-safety/connection khác nhau; cần đọc hợp đồng của loại connection và loại lệnh đang dùng trước khi chia sẻ đồng thời.

### 5.1. Atomic command và thao tác nhiều bước

Redis thực thi từng lệnh như `INCR` hoặc `DECRBY` với semantics nguyên tử của **một lệnh** trên server, nhưng:

~~~text
GET stock:42       -> 10
Java: stock = 10 - 1
SET stock:42 9
~~~

không tự bảo vệ khoảng trống giữa `GET` và `SET`. Hai yêu cầu cùng đọc `10` có thể đều ghi `9`, gây lost update. Với bộ đếm, nên dùng `INCR`/`INCRBY`; với bất biến “chỉ trừ khi còn đủ”, cần cơ chế kiểm tra và cập nhật nguyên tử thích hợp như **Lua script**, một số command hỗ trợ điều kiện, hoặc `WATCH` + `MULTI/EXEC` với xử lý xung đột. Không được suy rằng chỉ dùng một driver Redis đã đủ bảo đảm mọi logic read–modify–write.

### 5.2. TTL, cache và độ bền

`setex(..., 60, ...)` đặt thời hạn 60 giây cho key cache trong ví dụ. Dữ liệu cache có thể hết hạn hoặc bị loại bỏ theo chính sách bộ nhớ; Redis còn có các cấu hình RDB, AOF và replication ảnh hưởng durability. Vì vậy:

- Nếu Redis chỉ là **cache**, ứng dụng phải xử lý cache miss bằng nguồn dữ liệu chính, kiểm tra invalidation và tránh dùng cache cũ để quyết định nghiệp vụ quan trọng.
- Nếu Redis là **primary store** cho một loại dữ liệu, cần thiết kế backup, persistence, recovery, replication, TTL và chính sách mất dữ liệu phù hợp; mặc định “Redis chạy trong bộ nhớ” không có nghĩa mọi giá trị đã ghi tồn tại sau crash.
- Một lệnh thành công ở Redis **không** commit được transaction SQL hoặc MongoDB nằm ngoài Redis.

## 6. Cassandra: driver, CQL và thiết kế theo partition

Apache Cassandra là kho dữ liệu phân tán thường được dùng khi cần mở rộng lưu trữ và truy cập theo các mẫu truy vấn xác định. Khác với một RDBMS mà ứng dụng có thể bắt đầu từ bảng chuẩn hóa rồi JOIN, thiết kế Cassandra cần xuất phát từ **query patterns và partition key**.

Ví dụ lược đồ:

~~~sql
CREATE TABLE orders_by_customer (
    customer_id uuid,
    order_id uuid,
    status text,
    PRIMARY KEY (customer_id, order_id)
);
~~~

Ở đây `customer_id` là partition key; `order_id` là clustering key. Truy vấn theo cả hai khóa rất phù hợp với cấu trúc bảng, còn truy vấn tự do theo `status` trên toàn bộ dữ liệu không mặc nhiên có hiệu năng tốt.

Ví dụ sử dụng Cassandra Java Driver dạng session được tiêm vào repository:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import java.util.Optional;
import java.util.UUID;

public final class CassandraOrderStatusRepository {
    private final CqlSession session;
    private final PreparedStatement findById;

    public CassandraOrderStatusRepository(CqlSession session) {
        this.session = session;
        this.findById = session.prepare(
                "SELECT status FROM orders_by_customer " +
                "WHERE customer_id = ? AND order_id = ?");
    }

    public Optional<String> findStatus(UUID customerId, UUID orderId) {
        Row row = session.execute(
                findById.bind(customerId, orderId)).one();
        return row == null
                ? Optional.empty()
                : Optional.ofNullable(row.getString("status"));
    }
}
~~~

**Session được tạo lúc khởi động theo cấu hình cluster và đóng khi ứng dụng dừng**; không mở một `CqlSession` mới mỗi lần đọc. Prepared statement giúp truyền tham số đúng kiểu và có thể được tái sử dụng. Nếu driver/backend dùng API bất đồng bộ, quản lý concurrency, timeout và cancellation theo hợp đồng của nó.

Những khác biệt cần ghi nhớ:

- Cassandra có **consistency level điều chỉnh theo thao tác** và mô hình phân phối/replication riêng. Không suy từ một truy vấn thành công rằng mọi replica đã có bản cập nhật mới nhất.
- Cassandra không hỗ trợ giao dịch đa hàng/đa partition có semantics ACID giống transaction JDBC thông thường. Các khả năng atomicity, batch và **lightweight transaction** có phạm vi/chi phí đặc thù; cần đọc hợp đồng của phiên bản/cluster được dùng.
- Không dùng `ALLOW FILTERING` bừa bãi để “chữa” một query pattern không phù hợp. Hãy thiết kế bảng dựa trên access path, tránh partition quá lớn hoặc hot partition.
- CQL `BATCH` không đồng nghĩa với tối ưu hóa bulk insert tùy ý và không thay thế transaction nghiệp vụ xuyên nhiều partition.
- Với compare-and-set cần xem xét các câu điều kiện `IF` và lightweight transaction, đồng thời xử lý trường hợp điều kiện không được áp dụng.

## 7. Graph, search và object storage: API còn khác nhau hơn

### 7.1. Neo4j Java Driver

Với cơ sở dữ liệu đồ thị, ứng dụng gửi truy vấn **Cypher** theo node và relationship. Java driver thường quản lý `Driver` dùng lâu dài và tạo `Session` ngắn hạn cho từng phạm vi sử dụng; các transaction có thể được thực thi qua transaction function để driver xử lý retry theo chính sách.

Ví dụ minh họa cách tham số hóa Cypher:

~~~cypher
MATCH (u:User {id: $userId})-[:PURCHASED]->(p:Product)
RETURN p.id AS productId
LIMIT 20
~~~

Tham số `$userId` phải được truyền qua API driver, thay vì ghép dữ liệu người dùng trực tiếp vào chuỗi Cypher. Chú ý session, transaction, bookmark và phạm vi nhất quán khi có nhiều request; một graph database có hỗ trợ transaction không có nghĩa truy vấn graph tự động tham gia transaction của SQL database khác.

### 7.2. OpenSearch/Elasticsearch Java API Client

Search engine lập chỉ mục tài liệu phục vụ **full-text search, filter, ranking và aggregation**. Java client thường kết nối qua HTTP, xây dựng request dạng typed builder/JSON và giải mã response.

Khác biệt quan trọng với kho giao dịch:

- Một document vừa index có thể chưa xuất hiện ngay trong truy vấn search cho đến khi cơ chế **refresh** làm nó có thể tìm kiếm.
- Lập chỉ mục và tìm kiếm không tự mang bảo đảm transaction của hệ thống đơn hàng.
- Reindex và thay đổi mapping có thể là thao tác vận hành lớn; cần kế hoạch schema/index evolution.
- Không dùng kết quả search có thể trễ để quyết định tồn kho, thanh toán hoặc phân quyền cần trạng thái authoritative.

Nếu cần tìm kiếm sản phẩm, có thể lưu sản phẩm chính trong một transactional/document store và cập nhật search index theo sự kiện đã commit. Cơ chế đồng bộ có thể phải chấp nhận độ trễ nhất định và cần reconciliation khi sự kiện bị trễ hoặc xử lý lặp.

### 7.3. Object storage qua SDK

Kho object như S3 cung cấp thao tác `put/get/list/delete` theo bucket và key qua SDK, phù hợp với file, ảnh, backup và dữ liệu kích thước lớn. Nó **không** là hệ thực thi SQL JOIN hoặc cập nhật nguyên tử nhiều hàng.

Khi dùng Java SDK, phải quản lý stream/phản hồi, thời gian tải, multipart upload, checksum, credential và vòng đời HTTP client. Nếu database lưu metadata còn object store lưu file, **hai nơi không cùng một transaction**. Để xử lý upload thành công nhưng ghi metadata thất bại (hoặc ngược lại), cần quy trình trạng thái `PENDING`/`READY`, dọn object mồ côi và đối soát.

## 8. Khác biệt về atomicity, isolation và consistency

Không nên nói chung rằng “mọi NoSQL đều eventual consistency” hoặc “NoSQL không có transaction”. Mỗi công nghệ và từng thao tác có bảo đảm khác nhau.

| Kho / kiểu thao tác | Đơn vị và bảo đảm cần quan tâm | Không nên suy diễn |
| --- | --- | --- |
| MongoDB cập nhật **một document** | Thao tác ghi một document có atomicity ở phạm vi document | Hai cập nhật ở hai collection tự động cùng commit |
| MongoDB transaction nhiều document | Có cơ chế transaction khi cấu hình triển khai hỗ trợ | Transaction dài/qua nhiều hệ thống là miễn phí |
| Redis một command `INCR` | Command có thao tác nguyên tử trên server | Hai command `GET` rồi `SET` là một transaction |
| Cassandra CQL | Consistency level, partition key, LWT và batch semantics | Mọi query có serializable isolation như RDBMS |
| Neo4j transaction | Phạm vi transaction của graph DB | Cùng transaction với SQL/MongoDB khác |
| OpenSearch/Elasticsearch indexing | Ghi tài liệu và khả năng thấy qua search có thể khác thời điểm | Index xong là mọi search lập tức thấy |
| S3/object storage | API object theo hợp đồng nhà cung cấp | Một thao tác object cũng commit metadata ở RDBMS |

Một ví dụ nghiệp vụ có **bất biến số lượng**:

~~~text
Trước: stock = 1
Request A: reserve(1)
Request B: reserve(1)
Yêu cầu: chỉ một request được chấp nhận; stock không âm.
~~~

Ở MongoDB có thể dùng `updateOne` với filter `available >= 1` và `inc(-1)` trên một document. Ở Redis cần một thao tác atomically test-and-decrement phù hợp. Ở Cassandra phải chọn mô hình điều kiện/consistency tương ứng. Trong SQL quan hệ có thể dùng `UPDATE stock = stock - 1 WHERE stock >= 1`. **Dù cùng interface `reserve`, cách đạt bảo đảm phụ thuộc kho lưu trữ.**

Khi một use case cần thay đổi **hai kho khác nhau**, application service không thể tạo giao dịch ACID xuyên hai hệ chỉ bằng một annotation `@Transactional` thông thường. Cần thiết kế nguồn sự thật, outbox, idempotency, trạng thái trung gian, compensation và quy trình khôi phục.

## 9. Thiết kế khóa, index và truy vấn theo mô hình dữ liệu

Trong kho quan hệ, ứng dụng thường nghĩ theo foreign key, JOIN và index B-tree. Với kho phi quan hệ, câu hỏi cần đặt theo từng sản phẩm:

| Công nghệ | Truy vấn hiệu quả thường phụ thuộc | Ví dụ sai lầm |
| --- | --- | --- |
| MongoDB | Filter, compound index, document shape, cardinality | Truy vấn theo field không có index trên collection lớn |
| Redis | Thiết kế key, TTL, data structure, giới hạn bộ nhớ | Dùng `KEYS *` trên môi trường dữ liệu lớn để liệt kê khóa |
| Cassandra | Partition key, clustering key, kích thước partition | Truy vấn theo field không có đường truy cập, tạo hot partition |
| Graph | Label/relationship và index/constraint phù hợp, dạng traversal | Truy vấn lan quá rộng, không giới hạn tập khởi đầu |
| Search | Mapping, analyzer, tokenization, refresh, shard | Dùng full-text analyzer cho mã định danh cần match chính xác |
| Object storage | Bucket/key prefix, object size, phân trang list, stream | List toàn bộ bucket để tìm một object đã biết key |

Ví dụ chỉ mục MongoDB cho đọc sản phẩm theo tenant và ID tự định nghĩa:

~~~java
import static com.mongodb.client.model.Indexes.ascending;

products.createIndex(ascending("tenantId", "sku"));
~~~

Nếu nghiệp vụ cần `sku` duy nhất **trong một tenant**, tạo **unique compound index** tương ứng (không chỉ index thường); phải kiểm tra dữ liệu trùng trước khi thêm ràng buộc. Với `_id`, MongoDB đã có index định danh; một index thêm không nên được tạo khi không phục vụ truy vấn thực tế.

Tương tự, Redis `SCAN` thường phù hợp hơn `KEYS` cho việc duyệt khóa có kiểm soát, nhưng `SCAN` có semantics lặp/không phản ánh snapshot ổn định khi dữ liệu đang đổi. Hãy tránh biến key scan thành đường truy vấn chính cho nghiệp vụ.

## 10. Đóng client, connection, cursor và stream đúng phạm vi

Một khác biệt lớn với JDBC là **đối tượng Java có cùng tên “client” không nhất thiết tương đương một Connection mượn từ pool**:

| Tài nguyên | Vòng đời thường phù hợp |
| --- | --- |
| `MongoClient` | Một/few instance dùng chung trong ứng dụng; đóng khi shutdown |
| `MongoCursor` | Ngắn hạn, `try-with-resources` quanh vòng lặp |
| `RedisClient` (Lettuce) | Dùng chung, shutdown khi ứng dụng dừng |
| `StatefulRedisConnection` | Theo chiến lược kết nối/pool và loại workload; đóng/hoàn trả đúng hợp đồng |
| `CqlSession` | Tái sử dụng cho nhiều request; đóng khi shutdown |
| Neo4j `Driver` | Dùng chung; đóng khi shutdown |
| Neo4j `Session` | Ngắn hạn; đóng sau đơn vị công việc |
| HTTP search client / S3 SDK client | Tái sử dụng transport/pool; đóng khi shutdown nếu API hỗ trợ |
| HTTP response body / object input stream | Đóng sau khi đọc/xử lý xong |

Lỗi phổ biến là **khởi tạo client mới mỗi request**, tạo socket/pool/tài nguyên mạng không cần thiết. Ngược lại, một cursor hoặc response stream cần giải phóng sớm lại bị giữ cho tới lúc ứng dụng tắt.

Không suy rằng mọi client đều thread-safe ở mọi cấp API. Client dài hạn thường được thiết kế cho nhiều request, nhưng session, cursor, blocking operation và transaction context có thể không an toàn khi truy cập đồng thời. Luôn kiểm tra hợp đồng concurrency của **kiểu đối tượng cụ thể**.

## 11. Sync, async và reactive: chọn nhất quán với ứng dụng

Nhiều driver cung cấp những mô hình xử lý khác nhau:

| Mô hình | Đặc điểm | Điều cần kiểm soát |
| --- | --- | --- |
| **Synchronous/blocking** | Gọi API và chờ kết quả trên thread hiện tại | Thread pool, timeout, connection pool |
| **Asynchronous** | Trả future/callback, hoàn tất sau | Error propagation, cancellation, concurrency limit |
| **Reactive** | Xử lý qua publisher/stream và backpressure | Subscription, cancellation, resource lifecycle, blocking ẩn |

Một application dùng Spring MVC/JDBC blocking có thể chọn MongoDB sync driver vì đơn giản. Một pipeline reactive với WebFlux có thể chọn reactive driver; nhưng **đừng gọi MongoDB sync driver trực tiếp trên event-loop** rồi kỳ vọng hệ thống trở thành nonblocking chỉ vì controller trả `Mono`.

Async không tự giải quyết backpressure. Nếu đưa 100.000 thao tác vào driver mà không giới hạn đồng thời, có thể làm quá tải pool và database. Cần điều chỉnh số request outstanding, timeout, queue, retry budget và resource cleanup; khi subscription bị hủy, bảo đảm cursor/stream được giải phóng theo thư viện.

## 12. Lỗi kết nối và retry: cùng tên lỗi, khác ý nghĩa

Một request truy cập kho dữ liệu có thể thất bại ở nhiều bước:

1. Chưa kết nối được: DNS, TLS, xác thực, topology discovery, connection pool timeout.
2. Gửi lệnh nhưng chưa nhận phản hồi: mạng đứt, request timeout, server quá tải.
3. Lệnh bị từ chối: schema/type, duplicate key, conditional update không thỏa, permission denied.
4. Ghi được nhưng phản hồi mất: **kết quả thao tác chưa rõ** ở phía ứng dụng.

Phải phân loại lỗi trước khi retry:

| Loại lỗi | Retry? | Lý do |
| --- | --- | --- |
| Input sai schema/kiểu dữ liệu | Thường không | Gửi lại cùng payload không sửa được lỗi |
| Duplicate key của ràng buộc nghiệp vụ | Không retry mù | Cần xác định trùng là request cũ hay xung đột thực |
| Timeout kết nối trước khi gửi | Có thể, có giới hạn | Chưa thực hiện thao tác, nhưng cần biết driver thật sự đã gửi chưa |
| Timeout sau khi gửi/đúng lúc nhận kết quả ghi | Chỉ khi có idempotency/đối soát phù hợp | Lệnh có thể đã được áp dụng |
| Lỗi tạm thời do failover/overload | Có thể retry hữu hạn với backoff/jitter | Tránh tạo retry storm |
| Conditional update trả 0 dòng | Thường là kết quả nghiệp vụ/xung đột | Cần đọc lại hoặc báo không đủ điều kiện, không lặp ngay như lỗi mạng |

Ví dụ lệnh cập nhật “trừ tồn kho 1” có thể **không lũy đẳng** nếu bị gửi lại sau khi server đã trừ nhưng phản hồi bị mất. Một số driver có cơ chế retryable writes/commands riêng, nhưng không được suy rằng **toàn bộ workflow** sẽ chỉ thực thi đúng một lần. Với tạo đơn, thanh toán hoặc ghi log nghiệp vụ, thiết kế **idempotency key**, unique constraint và kết quả truy vấn lại là cần thiết.

Không nên bắt mọi exception rồi trả `Optional.empty()`; điều đó biến lỗi hạ tầng thành “không có dữ liệu”. Một adapter nên chuyển lỗi kỹ thuật thành những lỗi ổn định theo hợp đồng port, đồng thời giữ cause và thông tin truy vết thích hợp.

## 13. Durability, replication và xác nhận ghi

Một lệnh ghi trả thành công **không có cùng ý nghĩa durability ở mọi kho**:

- MongoDB: write concern và mức replication/acknowledgement ảnh hưởng lời hứa ghi được xác nhận; read concern và read preference ảnh hưởng dữ liệu nhìn thấy.
- Redis: độ bền liên quan RDB/AOF và cấu hình đồng bộ, replica và failover; cache có thể bị loại bỏ hoặc hết hạn.
- Cassandra: consistency level và replication factor cùng hành vi cluster ảnh hưởng mức xác nhận và đọc sau ghi; không đồng nghĩa backup đầy đủ.
- Graph database: transaction commit và cơ chế clustering của hệ cụ thể cần được xem xét.
- Search engine: xác nhận index và thời điểm tài liệu xuất hiện trong kết quả search có thể cách nhau.
- Object storage: hợp đồng write/read/overwrite theo nhà cung cấp cần được xem riêng; đồng bộ metadata ở kho khác là một workflow khác.

Vì thế, câu hỏi đúng là: **sau khi API trả thành công, lỗi nào có thể xảy ra mà dữ liệu vẫn được bảo toàn?** Một hệ có replication nhưng không backup vẫn có thể mất dữ liệu do xóa nhầm, lỗi ứng dụng hoặc tài khoản bị xâm nhập. Backup, khôi phục và diễn tập restore vẫn là trách nhiệm vận hành.

## 14. Bảo mật truy cập kho phi quan hệ

NoSQL không loại bỏ yêu cầu bảo mật vốn có của persistence:

- **Xác thực và quyền tối thiểu:** dùng tài khoản/role riêng cho service, không dùng tài khoản quản trị để chạy ứng dụng; giới hạn collection, key prefix, keyspace, index và bucket phù hợp.
- **TLS và xác thực server:** cấu hình truyền dữ liệu mã hóa, CA/certificate và hostname verification phù hợp môi trường. Không tắt kiểm tra TLS chỉ để “kết nối cho nhanh”.
- **Quản lý bí mật:** đọc URI/token/credential từ secret manager hoặc biến môi trường được bảo vệ, xoay vòng credential; không hardcode mật khẩu trong source hoặc log.
- **Chống injection:** dùng builder và tham số hóa filter/CQL/Cypher, danh sách cho phép cho tên field/sort động, tránh ghép trực tiếp JSON, CQL hoặc Cypher từ dữ liệu người dùng.
- **Multi-tenant isolation:** scope query theo tenant đã xác thực và test đường đọc/ghi để không truy cập chéo tenant.
- **Bảo vệ dữ liệu:** giới hạn log payload nhạy cảm, mã hóa dữ liệu at rest theo yêu cầu, kiểm soát retention và quyền truy cập dữ liệu backup.

Khóa Redis dạng `tenant:501:user:42` chỉ là **quy ước định danh**, không phải kiểm soát truy cập. Nếu một service có quyền đọc toàn bộ keyspace, việc dùng key prefix không tự tạo hàng rào bảo mật giữa các tenant.

## 15. Ranh giới Repository/Adapter giữ miền độc lập công nghệ

Ví dụ use case cần đọc tồn kho và giữ chỗ:

~~~java
import java.util.Optional;

public record ProductId(String value) {}
public record ProductStock(ProductId id, int available) {}

public enum ReserveResult {
    RESERVED, NOT_FOUND, INSUFFICIENT_STOCK
}

public interface ProductStockPort {
    Optional<ProductStock> findById(String tenantId, ProductId id);
    ReserveResult reserveIfAvailable(
            String tenantId, ProductId id, int quantity);
}
~~~

Hợp đồng này **cần được hoàn thiện** nếu adapter không phân biệt được missing và out-of-stock chỉ bằng một lệnh ghi (chẳng hạn cập nhật 0 tài liệu). Có thể thực hiện một lần đọc bổ sung để phân loại, nhưng kết quả đọc sau có thể đã thay đổi; nên ghi rõ rằng phân loại là thông tin hiện thời, còn quyết định nguyên tử là việc reserve có thành công hay không.

Một implementation MongoDB có thể ánh xạ `reserveIfAvailable` sang `updateOne` có điều kiện. Với cache Redis, có thể **không nên** triển khai port này trên Redis nếu dữ liệu tồn kho chính nằm trong SQL/MongoDB: cache không được tự ý trở thành source of truth chỉ vì API của nó trả nhanh.

Quy tắc cho adapter:

1. Không trả `Document`, `Row` hay client-driver exception sang domain trừ khi hợp đồng có chủ đích phụ thuộc công nghệ.
2. Ghi rõ đơn vị atomicity và consistency. Một kiểu `boolean` không đủ nếu use case cần biết “đã ghi bền vững hay chưa”.
3. Không giấu hành vi retry chứa side effect trong adapter một cách không kiểm soát.
4. Mapping, validation và quyền truy cập tenant phải nhất quán giữa các backend.
5. Nếu một backend không đáp ứng yêu cầu nghiệp vụ, từ chối hoặc thay đổi thiết kế; không giả vờ mọi NoSQL adapter là drop-in replacement.

## 16. Kiểm thử tích hợp theo semantics của driver và server

Unit test có thể dùng fake port để kiểm tra luồng application service, nhưng **mock không xác minh** driver, serialization, timeout, consistency, cursor hay lock đúng thực tế. Những bài test quan trọng nên chạy với công nghệ gần production, có thể dùng container test hoặc môi trường tích hợp phù hợp.

| Nhóm test | Tình huống |
| --- | --- |
| **Kết nối & xác thực** | URI sai, credential hết hạn, TLS lỗi, server tạm ngắt |
| **Mapping** | Null/missing field, BSON type, JSON schema, enum, UUID, số lớn |
| **Query/index** | Filter theo tenant, query theo partition key, pagination/scan, index thực có |
| **Concurrent write** | Hai yêu cầu cùng giảm stock chỉ một được chấp nhận khi không đủ hàng |
| **Retry & uncertain write** | Ghi thành công nhưng client mất response; gửi lại cùng idempotency key không tạo tác động trùng |
| **Resource cleanup** | Cursor/stream/session/connection được đóng cả khi lỗi giữa chừng |
| **Consistency** | Read-after-write, đọc từ replica, indexing delay, TTL và cache invalidation |
| **Durability & recovery** | Backup/restore có thể khôi phục dữ liệu theo RPO/RTO đã đặt |
| **Security** | Tenant A không đọc/ghi dữ liệu tenant B, role thiếu quyền bị từ chối |

### Thử nghiệm cạnh tranh thực tế

Khởi tạo tài liệu sản phẩm có `available = 1`, mở hai luồng dùng **client kết nối chung đúng cách**, đồng bộ điểm bắt đầu bằng `CountDownLatch` rồi cho cả hai gọi `reserve(..., 1)`. Kiểm tra có **đúng một** thao tác thành công và giá trị cuối là `0`, không âm. Với Redis, dùng cơ chế nguyên tử được thiết kế để bảo vệ điều kiện số lượng; với Cassandra, dùng conditional write/LWT nếu kiến trúc yêu cầu.

Không chỉ dùng `Thread.sleep()` để “tạo race”, vì test sẽ không ổn định. Với failover hoặc crash-recovery, không nên làm gián đoạn dữ liệu sản xuất; dùng môi trường test và quy trình có kiểm soát.

## 17. Quan sát và tối ưu vận hành

Một service dùng nhiều kho sẽ có nhiều giới hạn tài nguyên và biểu hiện lỗi khác nhau. Cần giám sát theo **backend, operation và kết quả**, không chỉ tổng thời gian HTTP:

| Chỉ số | Ý nghĩa |
| --- | --- |
| p50/p95/p99 latency theo command/query | Truy vấn nào chậm và chậm do đâu |
| Active/pending connections, pool wait | Có mở quá nhiều client, pool cạn hoặc giữ connection lâu không |
| Request timeout, error type, retry count | Driver đang gặp failover/overload hay retry storm |
| Cache hit/miss và TTL distribution | Redis có thực sự cải thiện tải và độ trễ không |
| Mongo cursor duration, scan/index usage | Truy vấn document có dùng index và giải phóng cursor đúng không |
| Cassandra partition hotness, read/write latency | Data model có tạo hot partition hay kích thước partition quá lớn |
| Search indexing lag/refresh latency | Vì sao dữ liệu mới chưa tìm được qua search |
| Replica lag / consistency failures | Đọc stale hoặc thiếu xác nhận theo mức yêu cầu |
| Dung lượng, số object, backup/restore checks | Có thể khôi phục dữ liệu thật khi sự cố không |

Log nên chứa operation, collection/keyspace/index, trace ID, loại lỗi và thời gian ở mức cần thiết; **không** in connection string có credential hoặc toàn bộ dữ liệu khách hàng. Với các lệnh chậm, đánh giá query plan, index và data model **trước khi** tự động tăng pool hoặc retry.

## 18. Tình huống tổng hợp: một hệ bán hàng đa kho

Giả sử ứng dụng Java có các nhu cầu:

1. Quản lý thông tin sản phẩm thay đổi schema theo nhóm hàng.
2. Hiển thị trang sản phẩm thật nhanh.
3. Tìm kiếm theo tên, mô tả và bộ lọc.
4. Ghi sự kiện click/view ở lưu lượng cao.
5. Tạo đơn hàng và giữ tồn kho **không được trùng, không được âm**.

Một phương án **có thể cân nhắc**:

~~~mermaid
flowchart LR
    A[Java Application] --> B[Product Repository]
    B --> C[(Document Store)]
    A --> D[Cache Adapter]
    D --> E[(Redis)]
    A --> F[Search Adapter]
    F --> G[(Search Index)]
    A --> H[Event Adapter]
    H --> I[(Wide-column Store)]
    A --> J[Order / Inventory Service]
    J --> K[(Authoritative Transactional Store)]
    K --> L[Transactional Outbox]
    L --> M[Workers cập nhật cache / search / analytics]
~~~

Đây không phải kiến trúc bắt buộc: một hệ thống nhỏ có thể **chỉ cần một RDBMS** và đạt hiệu quả tốt hơn nhiều so với duy trì năm kho dữ liệu. Khi dùng nhiều kho:

- Chọn **một nguồn sự thật** cho mỗi loại dữ liệu quan trọng.
- Xác định đường ghi chính và cách cập nhật bản sao/cache/search sau commit.
- Phát sự kiện có idempotency; consumer phải chấp nhận xử lý lặp hoặc trễ.
- Xây dựng cơ chế reconciliation khi search index hoặc cache khác nguồn sự thật.
- Không dùng kết quả search/cache có thể stale để xác nhận đơn hoặc quyết định trừ tồn kho quan trọng.
- Đánh giá chi phí vận hành, backup/restore, bảo mật, migration và quan sát trước khi thêm một backend.

## 19. Bài tập vận dụng

**Tình huống A:** Một API tăng lượt xem sản phẩm trên Redis. Developer dùng `GET views`, cộng 1 ở Java rồi `SET views`. Khi 100 request đồng thời, tổng số lượt xem bị hụt.

**Câu hỏi:** Lỗi là gì, và nên thay đổi truy cập Redis thế nào?

**Gợi ý:** Đây là phép read–modify–write không nguyên tử. Dùng `INCR`/`INCRBY` thay vì GET–SET, hoặc thiết kế event ingestion nếu chỉ số cần độ bền/khả năng đối soát cao.

**Tình huống B:** Một product document MongoDB có `available = 2`. Hai request cùng cố giữ 2 đơn vị.

**Câu hỏi:** Có thể viết thao tác nào để chỉ một request thành công? Nếu cần đồng thời tạo order ở collection khác thì sao?

**Gợi ý:** Dùng `updateOne` với điều kiện `available >= 2` và `inc("available", -2)` trên document. Nếu cần atomically tạo order ở collection khác, cân nhắc transaction nhiều tài liệu trong triển khai hỗ trợ và các giới hạn của nó; hoặc thiết kế trạng thái/outbox phù hợp.

**Tình huống C:** Một đội dùng Cassandra để tìm tất cả đơn có `status = PENDING` trên toàn bộ khách hàng, nhưng bảng chỉ có primary key `(customer_id, order_id)`.

**Câu hỏi:** Vì sao query theo status không phù hợp, và nên thay đổi gì?

**Gợi ý:** Truy vấn không theo partition key chính của bảng. Cần thiết kế **bảng theo query**, materialized view/index nếu sản phẩm và workload cho phép, hoặc hệ truy vấn chuyên dụng, thay vì mặc định quét toàn bộ cluster.

**Tình huống D:** Sản phẩm đã được cập nhật trong database nhưng người dùng tìm kiếm vẫn thấy mô tả cũ trên search engine.

**Câu hỏi:** Đây có nhất thiết là dữ liệu đã commit bị mất không?

**Gợi ý:** Không. Search index có thể đang chậm nhận sự kiện, chưa refresh hoặc có lỗi pipeline. Kiểm tra nguồn sự thật, độ trễ indexing, retry/outbox và reconciliation.

## 20. Những điều cần ghi nhớ

- **Chọn Java driver theo mô hình kho**, không giả định mọi NoSQL đều dùng JDBC hoặc hỗ trợ cùng mức transaction.
- **Tái sử dụng client/session dài hạn**, đóng cursor, response và connection ngắn hạn đúng phạm vi; không tạo client mới cho mỗi request.
- **Dùng API typed/builder và tham số hóa** để tránh ghép dữ liệu người dùng vào câu truy vấn, đồng thời quản lý schema, kiểu dữ liệu và quyền tenant.
- **Phân biệt atomicity một lệnh/một document với atomicity của use case nhiều bước**; điều kiện cập nhật phải nằm ở tầng có khả năng bảo vệ nguyên tử.
- **Hiểu consistency và durability thật của từng backend**, nhất là cache TTL, Cassandra consistency level, MongoDB write/read concern và search indexing delay.
- **Retry phải phân loại lỗi và có idempotency**. Mất phản hồi sau khi ghi có thể nghĩa là server đã thực hiện thành công.
- **Giữ hợp đồng Repository theo nhu cầu miền**; adapter chuyển lệnh và lỗi driver, không hứa những bảo đảm backend không hỗ trợ.
- **Kiểm thử bằng backend thực và hai request cạnh tranh**, không chỉ mock client.
- **Không thêm NoSQL chỉ vì công nghệ có sẵn**: mỗi kho mới mang thêm chi phí bảo mật, dữ liệu đồng bộ, backup, monitoring và phục hồi.

Truy cập kho phi quan hệ từ Java là bài toán kết hợp **mô hình dữ liệu, driver/API và ranh giới nghiệp vụ**. Khi chọn đúng abstraction, hiểu cách client gửi lệnh và cách database xác nhận chúng, ứng dụng có thể tận dụng điểm mạnh của từng hệ lưu trữ mà vẫn giữ được tính đúng đắn và độ tin cậy của persistence.
