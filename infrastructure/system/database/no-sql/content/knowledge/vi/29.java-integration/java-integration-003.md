# Client/session dùng chung, vòng đời tài nguyên và an toàn đa luồng khi kết nối Java với NoSQL

## 1. Bài toán mở đầu: dùng chung thứ gì, và đóng lúc nào?

Một API Java phục vụ hàng nghìn request mỗi giây, truy cập MongoDB để đọc đơn hàng, Redis để lấy cache, và một worker xử lý sự kiện từ hàng đợi. Một lập trình viên viết:

```java
// Minh họa anti-pattern: tạo client trong mỗi request.
public Order findOrder(String orderId) {
    MongoClient client = MongoClients.create(connectionString);
    try {
        MongoDatabase db = client.getDatabase("shop");
        // Truy vấn rồi chuyển thành Order...
        return loadOrder(db, orderId);
    } finally {
        client.close();
    }
}
```

Một người khác tối ưu bằng cách giữ mọi thứ thành `static`:

```java
// Một anti-pattern khác: đem cả session đang thực thi đi dùng chung.
static MongoClient client = MongoClients.create(connectionString);
static ClientSession session = client.startSession();

// Nhiều request/thread cùng dùng session này.
```

Phương án đầu có thể gây **connection churn, tốn thời gian thiết lập TLS/authentication, tạo pool liên tục và giảm throughput**. Phương án sau lại có thể làm nhiều request **trộn transaction context, tranh trạng thái cursor/session và gặp lỗi an toàn đa luồng**.

Tư duy đúng không phải “mọi thứ phải dùng singleton” hay “mọi thứ phải tạo mới”, mà là:

> **Chia sẻ những đối tượng client được thư viện cam kết thread-safe và được thiết kế cho vòng đời dài; tạo session, transaction, result cursor hoặc kết nối mượn từ pool theo phạm vi sử dụng; đóng mỗi tài nguyên đúng chủ sở hữu và đúng thời điểm.**

Trong chương **Kết nối Java** của module **Database No SQL**, bài này hướng dẫn xây dựng một lớp kết nối bền vững khi dùng MongoDB, Redis, Cassandra, DynamoDB, Neo4j và các NoSQL driver khác, đặc biệt dưới tải đa luồng, async và khi application khởi động/tắt hoặc database failover.

## 2. Các tầng thường bị gọi chung là “connection”

Một hệ Java có thể có:

```text
                Java application (one JVM)
                         |
                 Shared SDK client
                         |
               Cluster/topology metadata
                         |
              Connection pool / transport
                /        |         \
               /         |          \
           Socket A   Socket B    Socket C
               \         |          /
                \        |         /
                  NoSQL cluster

Each incoming request:
   request context
       -> session/transaction scope when needed
       -> execute command
       -> consume result/cursor
       -> release scoped resources
```

**Client** thường là đối tượng cấu hình cấp ứng dụng, có thể quản lý pool, topology discovery, retry và background I/O. **Physical connection** là socket/transport đến một node. **Logical session** là context cho một chuỗi thao tác. **Transaction** là phạm vi atomicity/isolation được engine hỗ trợ. **Cursor** là đối tượng đọc kết quả có thể dùng tài nguyên tại server/client.

Không có chuẩn Java thống nhất buộc mọi NoSQL SDK gọi các khái niệm này bằng đúng tên hoặc có cùng an toàn đa luồng.

| Đối tượng | Thường nên sống bao lâu? | Có thể chia sẻ đa luồng? | Ai đóng? |
|---|---|---|---|
| `MongoClient`, `CqlSession`, `DynamoDbClient`, `Driver` Neo4j | Theo vòng đời ứng dụng/service | Thường có, theo tài liệu SDK | Application/DI container |
| Redis Lettuce `RedisClient` | Theo ứng dụng | Được thiết kế chia sẻ | Application |
| Redis Lettuce `StatefulRedisConnection` | Có thể dài hạn cho thao tác thông thường | Phần lớn thao tác được hỗ trợ, nhưng có ngoại lệ | Owner connection |
| Jedis `JedisPool` | Theo ứng dụng | Pool hỗ trợ nhiều thread mượn | Application |
| Jedis `Jedis` mượn từ pool | Theo một tác vụ/borrow scope | **Không** dùng chung tùy ý | Tác vụ đóng để trả về pool |
| MongoDB `ClientSession` | Một chuỗi thao tác/transaction | **Không** chạy đồng thời trên cùng session | Unit of work |
| Neo4j `Session` | Unit of work | **Không** chia sẻ đa luồng | Unit of work |
| Cursor/result stream | Thời gian duyệt kết quả | Tùy API, thường không chia sẻ iterator | Caller |
| Mutable request builder / mutable accumulator | Theo thread/request | **Không** nếu thiếu đồng bộ | Owner scope |

**Lưu ý:** Bảng là hướng dẫn định hướng theo các Java SDK thông dụng, không thay thế hợp đồng phiên bản đang triển khai. Ví dụ `CqlSession` của DataStax Java Driver không có cùng semantics với `ClientSession` của MongoDB dù đều có chữ “Session”.

## 3. Phải phân biệt ba loại “session”

### 3.1. Session như client kết nối dài hạn

Trong Cassandra Java Driver 4.x, `CqlSession` là entry point cấp ứng dụng, thường được tạo một lần và **dùng chung giữa các thread**. Nó có metadata, transport và connection management.

### 3.2. Session như đơn vị công việc

Trong MongoDB, `ClientSession` mang thông tin session/transaction, có state thay đổi và **không dành cho nhiều luồng chạy đồng thời**. Có thể tạo một session cho một chuỗi thao tác rồi đóng.

Neo4j `Session` cũng là một context làm việc ngắn hạn; `Driver` mới là đối tượng thiết kế để share.

### 3.3. Session bảo mật người dùng

Một **HTTP login session**, JWT hoặc security principal là vấn đề xác thực/phân quyền. Nó không phải MongoDB `ClientSession`. Đừng đặt `ClientSession` singleton theo người dùng hoặc dùng một transaction database như bằng chứng user có quyền.

### Quy tắc dùng tên

Khi một SDK có tên `Session`, hãy hỏi:

1. Đây là **client/transport handle** hay **transaction context**?
2. Nó có mutable state theo thao tác không?
3. Tài liệu có công bố thread-safe không?
4. Resource có cần `close()` không?
5. Đóng nó có đóng socket/pool của toàn ứng dụng không?

Chỉ trả lời sau khi biết **SDK và version**, không suy từ tên class.

## 4. Thread-safe nghĩa là gì — và không nghĩa là gì?

Một client được công bố thread-safe có nghĩa nhiều thread có thể **gọi các API được hỗ trợ** mà không phá trạng thái nội bộ của client. Nó không bảo đảm:

- Hai write tới cùng document sẽ không tranh chấp.
- Một chuỗi `read -> modify -> write` của ứng dụng tự thành transaction.
- Một command không idempotent có thể retry an toàn sau timeout.
- Một connection được phép dùng cho mọi trạng thái transaction/blocking/pub-sub.
- Một cursor có thể được chia sẻ giữa nhiều consumer.
- Client có thể dùng lại sau khi đã `close()`.
- Tài khoản A và B được phép chia sẻ cùng credential trong mọi mô hình đa tenant.

Ví dụ:

```text
Thread 1: sharedClient.updateOne(id=K, increment +1)
Thread 2: sharedClient.updateOne(id=K, increment +1)
```

Hai thao tác có thể an toàn về **bộ nhớ của client và giao thức kết nối**, nhưng bảo đảm giá trị kết quả thuộc về **atomicity của database và loại update**.

Ngược lại, nếu hai thread dùng chung `ClientSession` để chạy transaction, thread-safe của `MongoClient` **không được truyền sang session**.

### Quy tắc ba cấp

1. **Thread-safe client:** có thể share theo hợp đồng SDK.
2. **Operation scope:** một logical request/unit of work sở hữu session và cursor của mình.
3. **Business concurrency:** dùng conditional update, unique constraint, transaction, CAS/version hoặc idempotency để bảo vệ dữ liệu.

Ba cấp giải quyết ba loại rủi ro khác nhau.

## 5. Vì sao tạo client theo request là một anti-pattern?

Một SDK client có thể phải:

- Khởi tạo connection pool.
- Phân giải DNS/SRV và topology discovery.
- Thiết lập TCP/TLS và authentication.
- Khởi động background maintenance threads/timers.
- Khởi tạo serializer, mapper, retry policy và metrics.
- Duy trì cache metadata schema/shard/token/cluster.
- Warm up transport hoặc HTTP connection reuse.

Nếu mỗi request tạo client riêng:

```text
1,000 HTTP requests
  -> 1,000 new SDK clients
  -> each client opens transport/pool
  -> repeated handshakes and topology discovery
  -> resource churn, higher p99 latency
```

Các hậu quả có thể gồm:

| Triệu chứng | Nguyên nhân thường gặp |
|---|---|
 `Too many open files` | Nhiều socket/client chưa đóng |
 Latency cao ở đầu mỗi request | Tạo client, TLS, DNS, auth |
 Nhiều connection tới một node | Mỗi client có pool riêng |
 Tăng heap/direct memory | Buffers, metadata và background resources |
 Thread count tăng | Mỗi client/transport có worker threads |
 Pool metrics khó hiểu | Có nhiều pool ngoài dự kiến |
 Khi restart CPU/network tăng vọt | Mọi request cùng reconnect |

**Dùng client dài hạn** thường giúp tái sử dụng kết nối, giảm overhead và cho phép SDK quản lý topology/failover tốt hơn.

### Có khi nào tạo nhiều client là hợp lý?

Có, ví dụ:

- Truy cập **hai cụm độc lập** với endpoints khác nhau.
- Dùng **hai credential/security domains** không được phép trộn.
- Một workload có transport/pool settings riêng vì isolation/SLO.
- Blue-green migration có hai cụm song song.

Nhưng “một client cho mỗi user/request” hiếm khi là cách tối ưu đúng nếu mọi request truy cập cùng một cụm/credential.

## 6. Mô hình ownership: ai tạo thì phải biết ai đóng

Một nguyên tắc Java hữu ích:

> **Đối tượng sở hữu tài nguyên dài hạn phải có trách nhiệm đóng nó; đối tượng chỉ mượn thì không được đóng thay chủ sở hữu.**

Ví dụ:

```text
Application container
    owns MongoClient
        |
        +-- OrderRepository borrows MongoClient
        +-- UserRepository borrows MongoClient
        +-- BackgroundWorker borrows MongoClient

Request handler
    owns ClientSession (optional)
    owns FindIterable/MongoCursor while iterating

Application shutdown
    closes shared MongoClient ONCE
```

**Không** để một repository tự `close()` `MongoClient` sau mỗi query nếu client được container sử dụng chung. Ngược lại, không để một cursor/session mượn từ request sống vô hạn chỉ vì không đóng được client tổng.

### Một hợp đồng vòng đời rõ ràng

| Thành phần | Khởi tạo | Đóng |
|---|---|---|
| Container/app | Startup | Graceful shutdown |
| Shared client | Startup hoặc lazy init có đồng bộ | Shutdown |
| Per-request session | Bắt đầu unit of work | `finally` / `try-with-resources` |
| Per-request cursor | Khi query tạo cursor | Sau khi duyệt xong/lỗi |
| Borrowed pool connection | Khi cần I/O | Trả về pool ngay sau thao tác |
| Transaction | Khi nghiệp vụ cần atomic group | Commit hoặc abort và đóng |
| Async task/subscription | Khi dispatch | Complete/cancel, cleanup callbacks |

Ownership không chỉ là coding style: nó quyết định liệu tắt ứng dụng có làm **mất request đang chạy**, liệu pool có bị leak và ai được phép hủy một giao dịch.

## 7. Dependency Injection: tạo một client cho application

Một cách đơn giản trong Spring:

```java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class MongoConnectionConfig {
    @Bean(destroyMethod = "close")
    public MongoClient mongoClient() {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException("Missing MONGODB_URI");
        }
        return MongoClients.create(uri);
    }
}
```

Repository nhận dependency:

```java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoCollection;
import org.bson.Document;
import org.springframework.stereotype.Repository;

@Repository
public final class OrderRepository {
    private final MongoCollection<Document> orders;

    public OrderRepository(MongoClient client) {
        this.orders = client
            .getDatabase("shop")
            .getCollection("orders");
    }

    public Document findById(String id) {
        return orders.find(new Document("_id", id)).first();
    }
}
```

### Điểm cần hiểu

- Spring container sở hữu `MongoClient` và gọi `close()` khi context đóng.
- Repository giữ **collection handle** để tái sử dụng; mỗi `find()` tạo một operation context mới.
- Không gắn một mutable `ClientSession` vào field singleton.
- Không hardcode username/password vào source; dùng secret/config quản lý phù hợp.
- Đường query thực tế phải xác thực/ủy quyền tenant; ví dụ rút gọn chỉ minh họa lifecycle.
- Với Spring Data MongoDB, framework có thể cung cấp `MongoTemplate`/bean quản lý client. Nếu đã có cấu hình Spring Boot auto-configuration, tránh tự tạo thêm client ngoài ý muốn.

### Tránh singleton tự viết không có shutdown

```java
// Không nên để một static client tồn tại không rõ ai đóng:
static final MongoClient CLIENT =
    MongoClients.create("mongodb://example.invalid");
```

Một singleton không được container quản lý dễ gây leak trong test, redeploy hoặc application context refresh. **Singleton scope là ý tưởng hữu ích; ownership và cleanup vẫn là điều bắt buộc.**

## 8. MongoDB: share `MongoClient`, không share `ClientSession`

Với MongoDB Java Sync Driver, quy tắc thường dùng:

- `MongoClient`: thiết kế thread-safe, quản lý pool và cluster metadata; dùng chung trong process.
- `MongoDatabase`/`MongoCollection` handles: có thể tái sử dụng cho nhiều operation; method thường trả handles với config read/write concern tương ứng.
- `ClientSession`: scope của các operation/transaction, **không dùng đồng thời từ nhiều thread**.
- `MongoCursor`: sở hữu tài nguyên duyệt kết quả, nên được đóng khi hoàn tất.

### Ví dụ transaction với session riêng

```java
import com.mongodb.client.ClientSession;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Updates;
import org.bson.Document;

public final class OrderService {
    private final MongoClient client;
    private final MongoCollection<Document> orders;
    private final MongoCollection<Document> ledger;

    public OrderService(MongoClient client) {
        this.client = client;
        var db = client.getDatabase("shop");
        this.orders = db.getCollection("orders");
        this.ledger = db.getCollection("requestLedger");
    }

    public void submit(String orderId, String requestId) {
        // Per invocation: do not share this session with another request.
        try (ClientSession session = client.startSession()) {
            session.withTransaction(() -> {
                var result = orders.updateOne(
                    session,
                    Filters.and(
                        Filters.eq("_id", orderId),
                        Filters.eq("state", "DRAFT")
                    ),
                    Updates.set("state", "SUBMITTED")
                );

                if (result.getMatchedCount() != 1) {
                    throw new IllegalStateException(
                        "Order missing or not DRAFT");
                }

                ledger.insertOne(
                    session,
                    new Document("_id", requestId)
                        .append("orderId", orderId)
                        .append("state", "COMMITTED")
                );

                return null;
            });
        }
    }
}
```

**Đây là ví dụ học thuật**: một service thật cần xác thực quyền sở hữu, idempotency ledger được kiểm tra **trước** khi mutate, xử lý unique index/retry, phù hợp write/read concern và các giới hạn distributed transactions của MongoDB. Callback `withTransaction` có thể được driver chạy lại trong tình huống retry phù hợp; **không đưa email, charge, publish event ngoài transaction không idempotent vào callback**.

### Không dùng session chung giữa hai transaction

```java
// Anti-pattern:
private final ClientSession sharedSession = client.startSession();

// Thread A: sharedSession.startTransaction();
// Thread B: sharedSession.startTransaction();
// Thread A: commitTransaction();
```

Session mang state giao dịch hiện tại. Hai thread cùng sửa nó có thể gây exception, transaction context bị trộn hoặc hành vi không được SDK bảo đảm. Thread-safe của `MongoClient` không lan sang `ClientSession`.

### Không chạy parallel operations trên cùng transaction/session

```java
// Không khuyến nghị:
CompletableFuture.allOf(
    CompletableFuture.runAsync(() -> orders.updateOne(session, ...)),
    CompletableFuture.runAsync(() -> ledger.insertOne(session, ...))
).join();
```

Ngay cả khi database nhận nhiều command song song, cùng `ClientSession`/transaction không được sử dụng như một đối tượng concurrent shared nếu tài liệu driver không hỗ trợ. Hãy thực hiện tuần tự trong transaction hoặc chia lại ranh giới công việc theo hợp đồng.

## 9. MongoDB cursor: kết quả query cũng có vòng đời

Một truy vấn có thể trả cursor duyệt nhiều batch. Cursor có thể giữ tài nguyên tại server/driver cho đến khi được duyệt hết hoặc đóng.

```java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoCursor;
import org.bson.Document;

public void processOrders(MongoCollection<Document> orders) {
    try (MongoCursor<Document> cursor = orders.find(
            new Document("state", "SUBMITTED")
        ).iterator()) {
        while (cursor.hasNext()) {
            Document order = cursor.next();
            processOne(order);
        }
    }
}
```

### Vì sao try-with-resources?

- Nếu `processOne` ném exception ở giữa, cursor vẫn được đóng.
- Đọc hàng triệu document có thể dùng server-side cursor/batches; không được giữ vô hạn.
- Không cho cursor sống qua transaction/session đã đóng.
- Không chia cùng một mutable cursor cho nhiều worker threads rồi gọi `next()` đồng thời.

### Streaming không phải materialize toàn bộ

```java
// Rủi ro bộ nhớ nếu result quá lớn:
List<Document> all = orders.find().into(new ArrayList<>());
```

Nếu workload lớn, cân nhắc pagination/keyset/batching, cursor và backpressure. Nhưng phải hiểu semantics query/snapshot nếu dữ liệu thay đổi trong lúc phân trang.

### Session scope không chỉ là Java GC

Một session là tài nguyên logic có thể chiếm server resources; GC không tạo một lời hứa rằng `close()` được gọi kịp thời. Dùng `try-with-resources`/`finally` theo API.

## 10. Redis Lettuce: có thể share connection cho lệnh thông thường, nhưng có ngoại lệ

Lettuce sử dụng transport bất đồng bộ và được thiết kế cho thread-safe sharing của **`RedisClient`**; một `StatefulRedisConnection` có thể được dùng bởi nhiều thread cho phần lớn command thông thường theo hợp đồng SDK.

Ví dụ:

```java
import io.lettuce.core.RedisClient;
import io.lettuce.core.api.StatefulRedisConnection;

public final class RedisCache implements AutoCloseable {
    private final RedisClient client;
    private final StatefulRedisConnection<String, String> connection;

    public RedisCache(String redisUri) {
        this.client = RedisClient.create(redisUri);
        this.connection = client.connect();
    }

    public String get(String key) {
        return connection.sync().get(key);
    }

    public void put(String key, String value) {
        connection.sync().set(key, value);
    }

    @Override
    public void close() {
        connection.close();
        client.shutdown();
    }
}
```

Tạo `RedisCache` một lần ở application startup và đóng khi shutdown; **không tạo client + connection trong mỗi `get`**.

### Ngoại lệ quan trọng

Không hiểu “connection thread-safe” thành “mọi lệnh được phép trộn chung trên một socket”:

- **`MULTI/EXEC`:** transaction state có thể gắn với connection; những thread khác gửi command vào cùng connection có thể làm transaction sai ý định.
- **Blocking commands:** lệnh kiểu `BLPOP` hoặc các tác vụ chiếm connection có thể cản trở traffic thường; dùng connection riêng khi cần.
- **Pub/Sub:** có trạng thái subscription và command restrictions; nên có connection/pattern quản lý riêng.
- **Long-running commands/large responses:** có thể gây head-of-line blocking hoặc memory pressure.
- **Pipeline/manual flush settings:** phải đọc quy tắc thread/concurrency của các chế độ đặc biệt.

Với Lettuce, share một connection thường hữu ích cho **lệnh ngắn, không mang connection-local state đặc biệt**. Dùng connection pool hoặc connection riêng cho **blocking/transactional isolation** tùy workload và docs.

### Chú ý shutdown order

Đóng connection trước, sau đó shutdown `RedisClient` mà ứng dụng sở hữu. Không shutdown client khi worker vẫn còn gửi lệnh.

## 11. Redis Jedis: chia sẻ pool, mượn client theo tác vụ

Jedis có mô hình API khác Lettuce. Với cách dùng `JedisPool` thông dụng:

- `JedisPool` được chia sẻ cho các thread.
- Mỗi thread/request mượn `Jedis` bằng `getResource()`.
- `Jedis` đang mượn **không** được dùng chung đồng thời tùy ý.
- `close()` của tài nguyên mượn từ pool thường **trả nó về pool**, không đóng toàn bộ pool.

```java
import redis.clients.jedis.Jedis;
import redis.clients.jedis.JedisPool;

public final class JedisCache implements AutoCloseable {
    private final JedisPool pool;

    public JedisCache(String host, int port) {
        this.pool = new JedisPool(host, port);
    }

    public String get(String key) {
        try (Jedis jedis = pool.getResource()) {
            return jedis.get(key);
        }
    }

    public void set(String key, String value) {
        try (Jedis jedis = pool.getResource()) {
            jedis.set(key, value);
        }
    }

    @Override
    public void close() {
        pool.close();
    }
}
```

### Không giữ resource mượn trong singleton

```java
// Anti-pattern: một Jedis mượn rồi để field cho nhiều thread dùng.
class WrongService {
    private final Jedis sharedBorrowedJedis;

    WrongService(JedisPool pool) {
        sharedBorrowedJedis = pool.getResource();
    }
}
```

Đoạn này vừa có nguy cơ non-thread-safe, vừa không trả connection về pool. Một thread có thể đang trong transaction/subscription state khi thread khác gọi lệnh.

### Biến thể SDK

Jedis có thêm các wrapper/API hiện đại như `JedisPooled` hoặc cluster clients với hợp đồng concurrency khác. Đừng suy mọi object trong thư viện Jedis đều có cùng quy tắc với một `Jedis` mượn từ `JedisPool`; kiểm tra phiên bản/client class cụ thể.

## 12. So sánh Lettuce và Jedis theo hành vi chia sẻ

| Mục tiêu | Lettuce kiểu thường dùng | Jedis pool kiểu thường dùng |
|---|---|---|
 Shared application-level owner | `RedisClient` | `JedisPool` |
 Thao tác thông thường từ nhiều thread | Có thể dùng shared `StatefulRedisConnection` theo docs | Mỗi worker mượn `Jedis` riêng |
 Transaction blocking/pubsub | Connection riêng/pool theo mode | Borrow riêng, không trộn trạng thái |
 Release per task | Không cần close shared connection mỗi query | `try(Jedis jedis=pool.getResource())` |
 Shutdown application | Close connections, shutdown client | Close pool khi không còn borrower |
 Backpressure | Cần kiểm soát lượng command outstanding | Cần kiểm soát pool wait/borrowers |

Không có “cứ dùng singleton connection là tối ưu” áp dụng cả hai. Bản chất thread safety và connection-local state của SDK quyết định mô hình.

## 13. Cassandra Java Driver: `CqlSession` dùng chung

DataStax/Apache Cassandra Java Driver 4.x dùng `CqlSession` làm điểm vào kết nối cluster. Thông thường **một `CqlSession` per target cluster/application** được tạo lúc startup và chia sẻ giữa các threads.

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

public final class AccountDao {
    private final CqlSession session;
    private final PreparedStatement byId;

    public AccountDao(CqlSession session) {
        this.session = session;
        this.byId = session.prepare(
            "SELECT email FROM accounts_by_id WHERE account_id = ?"
        );
    }

    public String emailOf(String accountId) {
        Row row = session.execute(
            byId.bind(accountId)
        ).one();
        return row == null ? null : row.getString("email");
    }
}
```

Application owner:

```java
import com.datastax.oss.driver.api.core.CqlSession;
import java.net.InetSocketAddress;

public final class CassandraRuntime implements AutoCloseable {
    private final CqlSession session;

    public CassandraRuntime() {
        session = CqlSession.builder()
            .addContactPoint(new InetSocketAddress("127.0.0.1", 9042))
            .withLocalDatacenter("dc1")
            .build();
    }

    public CqlSession session() {
        return session;
    }

    @Override
    public void close() {
        session.close();
    }
}
```

Các host/DC là minh họa môi trường lab. Cluster thật cần authentication/TLS, discovery/driver config, connection limits và schema phù hợp.

### Prepared statement có thể tái sử dụng

`PreparedStatement` là lựa chọn tốt để cache/tái sử dụng cho query nhiều lần. Khi bind:

```java
var bound = byId.bind(accountId);
session.execute(bound);
```

Tránh mutate một builder/dữ liệu param dùng chung giữa threads. Những immutable bound statements/statement values theo hợp đồng driver có thể chuyển qua thread, nhưng **mutable builders, iterators/result paging state** cần giữ đúng scope.

### Async và paging

`CqlSession.executeAsync` cho phép async I/O, nhưng việc có một shared session không nghĩa có thể phát **vô hạn request cùng lúc**. Cần concurrency bounds, timeout, retry budget và kiểm soát paging/backpressure.

### Không nhầm `CqlSession` với MongoDB `ClientSession`

Tên giống nhau nhưng vòng đời và thread-safety khác căn bản. Đây là một trong những lỗi học thuộc mẫu `try(session)` rồi áp máy móc sang mọi NoSQL SDK.

## 14. DynamoDB Java SDK v2: share service client, tạo request theo lời gọi

Trong AWS SDK for Java v2, `DynamoDbClient` và `DynamoDbAsyncClient` được thiết kế là **service clients thread-safe** và có thể dùng chung trong ứng dụng khi cấu hình phù hợp.

```java
import java.util.Map;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.dynamodb.DynamoDbClient;
import software.amazon.awssdk.services.dynamodb.model.AttributeValue;
import software.amazon.awssdk.services.dynamodb.model.GetItemRequest;
import software.amazon.awssdk.services.dynamodb.model.GetItemResponse;

public final class DynamoCustomerRepository {
    private final DynamoDbClient db;

    public DynamoCustomerRepository(DynamoDbClient db) {
        this.db = db;
    }

    public GetItemResponse getCustomer(String id) {
        var key = Map.of(
            "customerId", AttributeValue.builder().s(id).build()
        );

        var request = GetItemRequest.builder()
            .tableName("Customers")
            .key(key)
            .build();

        return db.getItem(request);
    }
}
```

Application creates once:

```java
DynamoDbClient db = DynamoDbClient.builder()
    .region(Region.AP_SOUTHEAST_1)
    .build();

try {
    DynamoCustomerRepository repo =
        new DynamoCustomerRepository(db);
    repo.getCustomer("C001");
} finally {
    db.close();
}
```

**Đây là demo lifecycle**, không có exception mapping, retry policy, credential/security boundary hay tenant authorization đầy đủ.

### Request objects khác mutable builders

SDK v2 thường sử dụng **request immutable** sau khi `build()`. Có thể tạo request mới cho mỗi operation, hoặc tái sử dụng immutable value nếu hợp đồng an toàn. Không chia sẻ một **mutable builder** giữa các thread rồi thay key/value liên tục.

### Sync vs async transport

Một `DynamoDbAsyncClient` có HTTP async transport riêng. Đừng tạo sync client per request rồi gọi nó từ async callback chỉ để “không block main thread”. Chọn API/HTTP client phù hợp, control concurrency, timeout và lifecycle của transport nếu được inject/managed riêng.

### Không coi client thread-safe là transaction-safe của business logic

Hai thread gọi `UpdateItem` đồng thời có thể hợp lệ về SDK thread safety nhưng vẫn tranh cùng item. Sử dụng `ConditionExpression`/version/`TransactWriteItems` khi cần bất biến, và request idempotency để xử lý unknown outcome.

## 15. Neo4j Java Driver: `Driver` chia sẻ, `Session` theo unit of work

Neo4j phân biệt rõ:

- `Driver`: thread-safe, tương đối tốn tài nguyên để tạo, nên share.
- `Session`: không thread-safe, nhẹ hơn, dùng ngắn hạn.
- Transaction/cursor/`Result`: theo phạm vi session/operation; kết quả cần được tiêu thụ trước khi đóng session theo API.

Ví dụ:

```java
import org.neo4j.driver.AuthTokens;
import org.neo4j.driver.Driver;
import org.neo4j.driver.GraphDatabase;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;
import org.neo4j.driver.Values;

public final class GraphCustomerService implements AutoCloseable {
    private final Driver driver;

    public GraphCustomerService(String uri, String user, String password) {
        driver = GraphDatabase.driver(
            uri, AuthTokens.basic(user, password)
        );
    }

    public String customerName(String id) {
        try (Session session = driver.session(
                SessionConfig.forDatabase("neo4j"))) {
            return session.executeRead(tx -> {
                var result = tx.run(
                    "MATCH (c:Customer {id: $id}) RETURN c.name AS name",
                    Values.parameters("id", id)
                );
                return result.single().get("name").asString();
            });
        }
    }

    @Override
    public void close() {
        driver.close();
    }
}
```

Ví dụ dùng các API tên `executeRead` của Neo4j Java Driver phiên bản mới; tên method có thể khác giữa major versions. Production cần xử lý không tìm thấy/nhiều record, validation, authorization, TLS/credential và retries.

### Transaction function có thể được retry

Driver có thể retry một managed transaction function khi gặp lỗi transient phù hợp. Không thực hiện side effect bên ngoài như charge/email trong callback mà chưa có idempotency.

### Không gửi một session vào parallel stream

```java
// Anti-pattern:
Session session = driver.session();
ids.parallelStream().forEach(id -> {
    session.run("MATCH ..."); // shared mutable session
});
```

Mỗi task có thể mở session riêng trong scope hoặc batching hợp lý; phải chặn fan-out không giới hạn và đóng session khi hoàn tất.

## 16. Couchbase, Elasticsearch/OpenSearch và các SDK khác

Không phải SDK nào cũng có class tên `Client`.

### Couchbase Java SDK

Một `Cluster`/`Bucket`/`Scope`/`Collection` handle thường được thiết kế tái sử dụng thay vì kết nối mới mỗi request. Ví dụ minh họa:

```java
import com.couchbase.client.java.Cluster;
import com.couchbase.client.java.Collection;

Cluster cluster = Cluster.connect(
    "couchbase://127.0.0.1", "user", "password"
);

try {
    Collection collection =
        cluster.bucket("shop").defaultCollection();
    var result = collection.get("order::1001");
    System.out.println(result.contentAsObject());
} finally {
    cluster.disconnect();
}
```

Với SDK/Couchbase server thật, cần kiểm tra readiness của bucket, SDK configuration, timeout, TLS, lỗi key không tồn tại và scopes. Đừng đặt `Cluster.disconnect()` sau mỗi lần `collection.get()`.

### Elasticsearch Java API Client

`ElasticsearchClient` là facade gắn với `ElasticsearchTransport` và một HTTP transport/client nền có connection pooling. Thường tạo và chia sẻ client/transport theo application lifecycle, tạo request builders/response handlers theo lời gọi.

**Ownership quan trọng:** nếu transport hoặc HTTP client được một factory tạo cho nhiều service dùng, không đóng nó bên trong một repository. Nếu ứng dụng sở hữu transport, đóng nó đúng một lần khi tắt. Các API/transport classes khác nhau giữa Elasticsearch Java API Client, RestHighLevelClient phiên bản cũ và OpenSearch clients; không copy lifecycle của một thư viện sang thư viện khác.

### Kafka không phải NoSQL client nhưng thường đồng hành

Một hệ có thể có Kafka consumer/producer cho CDC/outbox. Producer, consumer và admin client có **quy tắc thread-safety riêng**; đặc biệt không suy Kafka `Consumer` được phép chia sẻ đa luồng chỉ vì một database client khác thread-safe.

## 17. API contract quan trọng hơn tên thư viện

Một quy tắc thực tế: trước khi share object X, tra trong tài liệu version của X:

- Có từ khóa **thread-safe**, **not thread-safe**, **one per application**, **one per thread** hoặc **one per transaction** không?
- Builder và kết quả trả về có **immutable** không?
- Có connection-local state như transaction, pipelining, subscription không?
- Có API `close`, `shutdown`, `dispose`, `cancel` không?
- `close` có block, cancel in-flight hay trả resource về pool?
- Retry policy có thể gọi lại callback không?
- Một result iterator có dùng server cursor hoặc paging token không?
- Các object này có lifecycle khác nhau giữa sync/async/reactive API không?

Không nên “đoán thread-safe” bằng việc chạy một test load không thấy exception. Race có thể chỉ xảy ra khi failover, callback retry hoặc pool bị áp lực.

## 18. Mutable state trong repository singleton

Ngay cả khi repository giữ thread-safe client, code ứng dụng có thể không thread-safe:

```java
// Anti-pattern: mutable request state trong singleton repository.
public final class WrongCustomerRepository {
    private final StringBuilder filterBuilder = new StringBuilder();

    public String buildFilter(String customerId) {
        filterBuilder.setLength(0);
        filterBuilder.append("id=").append(customerId);
        return filterBuilder.toString();
    }
}
```

Hai threads có thể xen kẽ `setLength(0)` và `append`, tạo chuỗi sai.

### Cách sửa

```java
public String buildFilter(String customerId) {
    StringBuilder local = new StringBuilder();
    return local.append("id=").append(customerId).toString();
}
```

Nhưng với query, tốt hơn nên dùng **typed parameter/bind variables**, không tự ghép chuỗi từ input. Ví dụ MongoDB `Filters.eq("customerId", customerId)` hoặc Cassandra prepared statements, Neo4j parameters.

### Những dữ liệu không nên làm field singleton mutable

- `currentTenantId`.
- `currentUserId`.
- `currentClientSession`.
- `currentTransaction`.
- `currentCursor`.
- `lastOperationResult` nếu được dùng để quyết định nghiệp vụ.
- Một reusable builder đang thay đổi params.

Các giá trị này thuộc **request/unit-of-work scope**. Nếu đặt vào singleton, request A có thể đọc/ghi với context của request B.

## 19. Stateless service không phải service không có state nào

Một service singleton có thể có các field bất biến:

```java
private final MongoClient client;
private final MongoCollection<Document> orders;
private final Clock clock;
```

Đó là dependencies/configuration được inject, không phải trạng thái nghiệp vụ của request.

Một phương thức có thể sử dụng local variables:

```java
public boolean updateOrder(String tenantId, String orderId) {
    var filter = Filters.and(
        Filters.eq("tenantId", tenantId),
        Filters.eq("_id", orderId)
    );
    return orders.updateOne(
        filter,
        Updates.set("state", "READY")
    ).getMatchedCount() == 1;
}
```

Các local objects chỉ thuộc một invocation, nên tránh race ở Java object level. Nhưng thao tác database vẫn cần kiểm tra **điều kiện trạng thái, version và authorization**.

### Thread confinement

Một `ClientSession` nên được **confine** cho một luồng hoặc một chuỗi async operations tuần tự được kiểm soát, không dùng đồng thời. “Thread confinement” là cách giảm rủi ro, nhưng điều quan trọng về mặt hợp đồng là **không có concurrent access trái quy định** và lifecycle rõ, kể cả khi async continuation chạy trên thread khác.

## 20. Async I/O: thread-safe client không cho phép vô hạn concurrency

Giả sử API nhận 10.000 request và gọi database bất đồng bộ:

```text
10,000 in-flight requests
       |
       v
Shared async client
       |
       v
Transport pools / event loops / DB capacity
```

Nếu không giới hạn in-flight operations, queue và memory có thể tăng nhanh, p99 timeout và retry storm.

### Backpressure cơ bản

Giới hạn số operation đồng thời:

```java
import java.util.concurrent.Semaphore;

public final class BoundedDbInvoker {
    private final Semaphore permits = new Semaphore(100);

    public <T> T call(DbCall<T> action) throws Exception {
        permits.acquire();
        try {
            return action.run();
        } finally {
            permits.release();
        }
    }

    @FunctionalInterface
    public interface DbCall<T> {
        T run() throws Exception;
    }
}
```

**Ví dụ dùng cho blocking operations**: semaphore bound 100 là số minh họa. Với async API, permit phải được giữ đến khi **future thật sự hoàn tất**, không release ngay sau khi dispatch.

### Async semaphore cần release trong completion

```java
// Pseudocode — minh họa semantic, không phải utility production.
acquirePermitAsync()
  .thenCompose(permit ->
      databaseAsyncCall()
        .whenComplete((value, error) -> permit.close())
  );
```

Nếu release permit trước khi DB call xong, giới hạn concurrency chỉ là ảo. Nếu callback ném exception hoặc request bị canceled, phải bảo đảm permit vẫn được trả về đúng một lần.

### Không block event-loop thread

Nhiều HTTP/Redis/Cassandra async libraries có event-loop/I/O executor riêng. Gọi `join()`, `get()`, `Thread.sleep` hoặc một blocking SDK trên event-loop có thể làm chậm toàn bộ pipeline, gây timeouts hàng loạt.

Phân biệt:

- Async I/O completion callbacks.
- CPU-intensive transformations.
- Blocking downstream calls.

Nếu cần xử lý CPU/blocking, dùng worker executor/boundedElastic hợp lý theo framework, tránh kéo dài callback chạy trên network event loop.

## 21. Reactive Streams: subscription, cancellation và lifecycle

Một API reactive có thể trả `Publisher` hoặc `Flux`. Không nên nghĩ “trả publisher là query đã hoàn thành”:

```text
Build Publisher
    |
    v
Subscribe
    |
    v
Request(n) / emit batches
    |
    v
Complete / Error / Cancel
```

Connection hoặc cursor có thể được giữ **trong suốt subscription**, không chỉ lúc xây publisher.

### Các lỗi thường gặp

- Subscribe trong repository rồi bỏ qua kết quả/cancellation.
- Không propagate cancellation tới query nếu SDK/framework hỗ trợ.
- Tạo publisher nhưng không subscribe, tưởng DB đã được update.
- Dùng blocking code trong reactive chain.
- Không giới hạn `flatMap` concurrency khi gọi DB.
- Shared mutable state giữa nhiều subscriptions.
- Đóng client trước khi mọi subscription cần thiết hoàn tất.

### Cancellation không đồng nghĩa transaction rollback

Subscriber cancel có thể khiến driver ngừng fetch/cursor, nhưng một update đã commit **không bị đảo ngược**. Nếu mạng ngắt sau commit trước ACK, client vẫn có kết quả **unknown**.

### Scope tài nguyên trong reactive API

Với tài nguyên cần mở và đóng theo subscription, dùng operator dành cho **resource ownership** của framework (ví dụ dạng `using`/`usingWhen` khi phù hợp). Không mở session ở singleton constructor rồi gắn vào mọi subscription.

## 22. Connection pool: kích thước và giới hạn

Pool tránh việc lập TCP connection cho mỗi command, nhưng không miễn phí:

- Mỗi connection dùng socket/buffer/server session.
- Pool quá nhỏ gây **wait queue** và tăng p99.
- Pool quá lớn gây nhiều sockets/CPU/memory phía client và database.
- Pool mỗi application instance được nhân lên theo số instance.

### Ví dụ tính nhẩm tổng connection

```text
App replicas: 20
Configured max connections per client to a target node: 100
Potential total connections to that node: up to 2,000
```

Đây là **ước lượng trên một node/kiểu pool**, không tự nói database chắc mở 2.000 sockets; topology, lazy connections, pool per endpoint và thực tế tải quyết định số hiện hữu.

### Little's Law cho concurrency

Trong điều kiện ổn định:

\[
L \approx \lambda W
\]

với:

- \(L\): số request đang chờ/đang xử lý trung bình.
- \(\lambda\): arrival rate trung bình (requests/second).
- \(W\): thời gian xử lý trung bình (second).

Nếu service nhận 1.000 requests/s và mỗi DB operation mất 50 ms, lượng concurrent cần về bậc độ lớn:

\[
L \approx 1000 \times 0.05 = 50
\]

Điều này **không có nghĩa max pool chính xác phải là 50**, vì burstiness, node routing, commands dùng nhiều round trips, thread scheduling và tail latency. Nó là điểm bắt đầu để suy luận thay vì chọn 1.000 connections một cách cảm tính.

### Cấu hình quan trọng

| Tham số | Ảnh hưởng |
|---|---|
| Max pool size | Số connection có thể dùng |
| Min idle / warm-up | Khả năng tránh cold latency, đổi lại resource |
| Pool wait timeout | Đợi được bao lâu khi không có connection |
| Connection establishment timeout | Kết nối tới node |
| Socket/command timeout | Đợi I/O/operation |
| Max lifetime / idle timeout | Tái tạo connection cũ |
| Keepalive | Phát hiện idle broken connections theo stack |
| Retry budget | Tránh tăng tải khi có lỗi |
| Max in-flight | Bảo vệ transport và database |

Tên config phụ thuộc SDK. **Không dùng chung một timeout cho mọi tầng** và không điều chỉnh chỉ bằng cách tăng pool khi root cause là slow query/hot shard.

## 23. Đo pool wait và database execution riêng

Request latency:

```text
Request
  |
  +-- wait for connection   30 ms
  +-- network RTT           10 ms
  +-- DB execution          20 ms
  +-- decode response        5 ms
  +-- application mapping    3 ms
  |
Total ≈ 68 ms (minh họa)
```

Nếu p99 tăng từ 70 ms lên 500 ms do **pool wait**, thêm index cho query có thể không giải quyết triệt để; phải xem pool saturation, long-running cursor, blocked connections, thói quen không close resource.

Nếu p99 tăng vì **DB execution**, tăng pool có thể làm database quá tải hơn. Phải đọc execution plan, shard routing, hot key, locks, compaction, throttling hoặc quota.

### Đừng lẫn các loại timeout

- **Connect timeout:** chưa thiết lập kết nối.
- **Pool acquire timeout:** không mượn được connection đúng hạn.
- **Socket read timeout:** command có thể đã tới server, outcome chưa rõ.
- **Server max execution time:** database có thể giới hạn một operation.
- **Business deadline:** toàn chuỗi công việc vượt ngân sách.

Một timeout bất kỳ không tự chứng minh write chưa commit.

## 24. Session và transaction khi dùng async/multi-thread

Giả sử một request thanh toán cần:

```text
1. Load order
2. Transition DRAFT -> SUBMITTED
3. Store request ledger
4. Commit transaction
```

Ranh giới unit of work:

```text
HTTP request / job
    |
    v
Acquire transaction/session scope
    |
    +-- sequential operations required by session contract
    |
    v
Commit or abort
    |
    v
Close session
```

### Những điều không được làm

- Cache một session toàn cục để mọi request dùng chung.
- Đưa session vào một parallel stream.
- Đóng session ở thread A khi thread B còn query.
- Tái sử dụng transaction handle sau commit/abort.
- Gửi async operation rồi đóng session trước khi future hoàn tất.
- Nhét external payment vào transaction callback có thể bị retry mà không có provider idempotency.

### Một thread có thể xử lý nhiều session

Không phải “session thuộc một thread vĩnh viễn”. Một thread pool worker có thể xử lý nhiều request tuần tự, mỗi request tạo session riêng; một request async có thể tiếp tục ở thread khác theo framework. Điều cần bảo vệ là **lifecycle và không concurrent access trái contract**, không phải gán một session cho một thread suốt đời.

## 25. Đừng lạm dụng `ThreadLocal` để giữ session

Một anti-pattern:

```java
static final ThreadLocal<ClientSession> CURRENT =
    new ThreadLocal<>();
```

Trong servlet thread pool, nếu quên `remove()` ở `finally`, thread được tái sử dụng cho request khác có thể mang transaction/session cũ.

Với async/reactive flow, continuation có thể chạy trên **thread khác**, khiến `ThreadLocal` không còn cùng context, hoặc context bị mất/mix.

### Nếu framework có transaction context

Dùng API transaction/context propagation chính thức của framework, không tự giả định `ThreadLocal` có thể truyền qua mọi `CompletableFuture` hoặc reactive chain.

### Nếu cần tự quản lý context

Truyền explicit scope/token qua phương thức hoặc builder được thiết kế:

```java
void updateOrder(ClientSession session, String id) {
    // Call happens within a single controlled unit of work.
}
```

Tuy nhiên không đưa session vào những callback parallel; phải kết thúc tất cả công việc trước khi đóng.

## 26. Graceful shutdown: dừng nhận việc trước, đóng client sau

Quy trình:

```text
RUNNING
   |
   v
Stop accepting new requests / jobs
   |
   v
Drain or cancel in-flight operations by policy
   |
   v
Finish/mark unknown work with durable status
   |
   v
Close sessions/cursors/borrowed connections
   |
   v
Close shared clients/transports/pools
   |
   v
TERMINATED
```

Nếu đóng client ngay khi nhận shutdown signal trong khi hàng trăm request còn dùng nó, có thể tạo hàng loạt lỗi I/O, timeout và outcome chưa rõ.

### Spring bean lifecycle

```java
@Bean(destroyMethod = "close")
MongoClient mongoClient() {
    return MongoClients.create(
        System.getenv("MONGODB_URI")
    );
}
```

Container có thể đóng client khi application context shutdown; nhưng **graceful drain** cần cấu hình ở HTTP server, message consumer và workload scheduler để hạn chế lệnh mới đến trong lúc đó.

### Một ví dụ với ExecutorService

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.TimeUnit;

public static void stopWorkers(ExecutorService workers)
        throws InterruptedException {
    workers.shutdown(); // do not accept new jobs

    if (!workers.awaitTermination(20, TimeUnit.SECONDS)) {
        workers.shutdownNow(); // cooperative interruption attempt
        workers.awaitTermination(5, TimeUnit.SECONDS);
    }
}
```

Trong production, `InterruptedException` cần được xử lý theo policy; thường khôi phục interrupt flag sau khi cleanup thích hợp. `shutdownNow()` **không** rollback database write đã commit hoặc đảm bảo remote work dừng.

### Transaction pending lúc shutdown

Nếu chưa commit, có thể abort theo API. Nếu commit response đã mất, kết quả có thể **unknown**; phải ghi requestId/ledger để xác minh sau restart, không tự đánh dấu tất cả là aborted.

## 27. Khởi động application: readiness không chỉ là tạo object

`MongoClients.create(...)` hoặc một builder có thể trả về đối tượng client trước khi mọi kết nối/network probe hoàn tất tùy SDK.

Phân biệt:

- **Constructed:** object Java đã tạo.
- **Transport initialized:** pool/network resources được khởi tạo.
- **Topology discovered:** client biết cluster/nodes.
- **Authentication succeeded:** đủ quyền theo credential.
- **Ready for required operations:** các thao tác và consistency cần thiết thực sự khả dụng.

### Startup strategy

1. Tạo clients trong container.
2. Nếu cần, thực hiện readiness probe có giới hạn timeout (ping/query nhẹ, đúng credential/region).
3. Không công bố ready cho traffic quan trọng trước khi dependency đạt ngưỡng cần thiết.
4. Nếu dependency tạm mất, liveness không nhất thiết phải chết; readiness có thể báo không nhận traffic theo policy.
5. Tránh tất cả instances cùng retry dồn dập; dùng backoff/jitter.

### Readiness probe có thể tạo tải

Không đặt một query scan lớn trong health check. Một ping thường không xác nhận uniqueness/transaction semantics đầy đủ; health check nên đo **khả năng phục vụ tối thiểu** và quan sát riêng những path nghiệp vụ quan trọng.

## 28. Retry, failover và kết quả ghi không rõ

Một shared client có thể tự retry những lỗi transient theo SDK. Nhưng khi client timeout sau write:

```text
Client -> DB: INCREMENT views
DB executes and commits
Network drops ACK
Client sees TIMEOUT
```

Nếu request được retry, counter có thể tăng hai lần. Đây không phải lỗi thread safety của client, mà là **idempotency/unknown commit outcome**.

### Ba kết quả

| Trạng thái | Ý nghĩa |
|---|---|
| Known committed | Có bằng chứng write đã commit theo hợp đồng |
| Known not committed | API/protocol bảo đảm chưa có effect |
| Unknown | Có thể đã commit; không đủ bằng chứng |

Khi unknown, không gửi lại non-idempotent mutation với **operation ID mới**. Cần:

- Stable `requestId`/`idempotencyKey`.
- Result ledger theo logical operation.
- Conditional write/unique guard trong cùng authority/transaction.
- Verify bằng authoritative read khi phù hợp.
- Backoff/retry có giới hạn.

### Retry transaction callback

Một số driver hỗ trợ callback transaction retry. Callback phải **không chứa side effect ngoài transaction mà không idempotent**, ví dụ gửi email/charge card/mutation Redis khác phạm vi. Hãy dùng outbox hoặc provider idempotency theo thiết kế nghiệp vụ.

### Failover và pool

Khi primary đổi, shared client có thể refresh topology và nối lại connections. Không coi một lỗi socket là bằng chứng “DB chưa ghi gì”. Client cần phân loại timeout, stale leader, transient transaction error và unknown commit theo SDK.

## 29. Cancellation: đóng future không đồng nghĩa đóng connection hoặc rollback

Một HTTP caller có thể hủy request, một `CompletableFuture` có thể bị canceled, hoặc reactive subscriber gọi cancel. Nhưng:

- Server có thể vẫn đang thực hiện command.
- Database có thể đã commit.
- Worker có thể tiếp tục trên queue.
- Result cursor có thể cần cleanup.
- Connection không nên bị đóng bừa nếu đang được share bởi các request khác.

Ví dụ:

```java
CompletableFuture<String> future =
    CompletableFuture.supplyAsync(() -> performDatabaseWrite());

future.cancel(true);
```

`CompletableFuture.cancel(true)` không tự bảo đảm interrupt supplier và **không phát rollback tới database**. Đừng dùng nó như business cancellation.

### Cancellation boundaries

Nếu cần hủy export dài, thiết kế job status/`CANCEL_REQUESTED` và worker checkpoints. Nếu cần hủy thanh toán, cần state machine, idempotency và compensation; không đóng shared database client để “ngăn” một request.

## 30. Multi-tenant: dùng chung client không được làm rò dữ liệu

Một client dùng credential của application có thể truy cập nhiều tenant. Điều này **không** có nghĩa một session/context có thể đổi `tenantId` giữa các request.

Sai:

```java
class WrongTenantRepository {
    private String currentTenantId; // shared mutable field

    void setTenant(String tenantId) {
        currentTenantId = tenantId;
    }

    // Concurrent request may use another user's tenant.
}
```

Đúng hơn:

```java
public Document findOne(String tenantId, String orderId) {
    return orders.find(
        Filters.and(
            Filters.eq("tenantId", tenantId),
            Filters.eq("_id", orderId)
        )
    ).first();
}
```

**Nhưng** `tenantId` phải lấy từ identity đã xác thực/ủy quyền; không chỉ tin tham số URL/body của client. Cần ràng buộc tenant ở mọi filter/write và ở các indexes/partition keys phù hợp.

### Một client cho nhiều tenant hay nhiều clients?

| Mô hình | Có thể làm | Cần lưu ý |
|---|---|---|
| Shared app credential, một cluster | Một thread-safe client | AuthZ phải được enforce theo request |
| Credentials riêng mỗi tenant | Có thể cần clients/security scopes riêng | Số clients/pools tăng, cần giới hạn |
| Cluster riêng mỗi tenant | Client theo cluster | Caching/eviction/lifecycle khi nhiều tenant |
| Region riêng theo policy | Client theo region/credential | Data residency, routing, retries |

Không dùng một client global duy nhất nếu nó vi phạm ranh giới bảo mật hoặc data residency. Nhưng cũng không sinh một pool mới cho **mọi HTTP request** khi cùng security domain.

### Secrets rotation

Khi credential/TLS cert được rotate, client/transport có thể cần reload/rebuild theo API. Không đóng client đang dùng trước khi client mới ready và requests cũ được drain. Cần quản lý số pool trong giai đoạn overlap.

## 31. Circuit breaker, rate limit và bulkhead

Một thread-safe client có thể được dùng bởi mọi endpoint. Nếu một endpoint tạo query rất nặng, nó có thể chiếm pool và làm các endpoint khác chậm.

Một mô hình:

```text
Shared MongoClient
   |
   +-- /orders/point-lookup      fast small query
   +-- /reports/full-scan        huge streaming query
   +-- /analytics/aggregation    CPU-heavy DB query
```

Các lớp bảo vệ:

- **Bulkhead:** giới hạn concurrency theo loại workload.
- **Rate limit:** kiểm soát yêu cầu đầu vào.
- **Circuit breaker:** ngừng gọi khi phụ thuộc có failure pattern.
- **Deadlines:** không giữ cursor/connection quá lâu.
- **Query limits:** page size, max time, projection/filter/index.
- **Dedicated pool/client** cho workload riêng khi có chứng cứ cần isolation và SDK hỗ trợ.

### Tách pool không thay business isolation

Hai clients riêng vẫn truy cập **cùng database** và có thể tranh locks, CPU, I/O hoặc hot partition. Bulkhead ở client chỉ kiểm soát một nguồn tải, không giải quyết truy vấn sai shard key hoặc counter hotspot.

## 32. Connection leak và cursor leak

Triệu chứng:

```text
Traffic stable
Connections in use:    increasing
Pool wait time:        increasing
Idle connections:      near zero
Requests completing:   decreasing
```

Nguyên nhân có thể:

- Quên đóng borrowed Jedis.
- Quên đóng MongoCursor/Neo4j Session.
- Async future không bao giờ complete nhưng giữ permit/resource.
- Transaction mở lâu rồi không commit/abort.
- Streaming result bị bỏ giữa chừng không dispose.
- Shutdown sequence tạo nhiều clients mới nhưng không close clients cũ.

### Đóng trong `finally`

```java
Jedis jedis = pool.getResource();
try {
    return jedis.get(key);
} finally {
    jedis.close(); // return to pool even on exception
}
```

`try-with-resources` rõ ràng hơn nếu class implements `AutoCloseable`.

### Leak không luôn là không đóng socket

Một server cursor, connection-local transaction hay stream subscription có thể giữ tài nguyên dù TCP socket vẫn còn và được xem là “connected”. Cần metrics theo **active sessions, cursor count, long-running operations và borrowed connection age**.

## 33. Bảng so sánh các NoSQL Java clients

| Hệ/SDK (dòng phổ biến) | Share dài hạn | Scoped object phải chú ý | Điểm đặc biệt |
|---|---|---|---|
| MongoDB Sync Java Driver | `MongoClient`, database/collection handle | `ClientSession`, `MongoCursor` | Không parallel transaction trên cùng session |
| Redis Lettuce | `RedisClient`; connection cho lệnh thường theo contract | Dedicated connection cho transactions/blocking/pubsub | Connection-local state và Netty event loop |
| Redis Jedis + pool | `JedisPool` | `Jedis` borrowed object | Đóng borrower để trả pool |
| Cassandra Driver 4.x | `CqlSession`, prepared statements | Result paging/iterator/builder scope | CqlSession **là shared client**, khác Mongo session |
| DynamoDB AWS SDK v2 | `DynamoDbClient`, `DynamoDbAsyncClient` | Per-call request builders/response | HTTP transport, retry/throttle |
| Neo4j Java Driver | `Driver` | `Session`, transaction/result | Managed transaction callback có thể retry |
| Couchbase Java SDK 3.x | `Cluster`, bucket/scope/collection handles | Operations/subscriptions/result handling | Disconnect cluster khi app shutdown |
| Elasticsearch Java API Client | `ElasticsearchClient`/transport | Request builders, response streams/tasks | Transport ownership và search task lifecycle |

Đây là **bản đồ khái niệm**, không phải hợp đồng không thay đổi qua các major versions. Trong code thật, kiểm tra JavaDoc của đúng SDK và chế độ sync/async/reactive được sử dụng.

## 34. Các anti-pattern thường gặp

| Anti-pattern | Rủi ro | Thay thế |
|---|---|---|
| Tạo `MongoClient` per HTTP request | Pool/TLS overhead, connections churn | Một client per app/cluster |
| `static ClientSession` cho mọi request | Shared mutable transaction state | Session per unit of work |
| Dùng `Jedis` borrowed chung nhiều threads | Non-thread-safe/connection state | `JedisPool`, borrow per operation |
| Dùng Lettuce transaction và lệnh thường chung connection | Command interleaving | Dedicated transactional connection |
| Dùng cùng mutable request builder giữa threads | Sai params/cross-tenant leak | Builders per operation |
| Lưu `currentTenantId` trong singleton | Cross-tenant data leak | Request-local context + authz |
| Không close cursor/transaction | Server resources giữ lâu | Try-with-resources/structured cleanup |
| Gửi async rồi đóng session lập tức | Operation chưa xong | Await completion trước close |
| Dùng `ThreadLocal` trên reactive chain | Context mất/trộn | Framework context propagation |
| Block event-loop bằng `join()` | Stalled I/O, timeout | Async composition/worker executor |
| Unbounded `flatMap` calls | Pool/DB overload | Bounded concurrency/backpressure |
| Client close khi còn in-flight writes | Unknown outcomes và lỗi hàng loạt | Drain rồi close |
| Retry increment sau timeout với ID mới | Double counting | Idempotency ledger |
| Dùng thread-safe client để thay conditional write | Race ở DB vẫn tồn tại | CAS/unique index/transaction |
| Cứ tăng pool để sửa p99 | Có thể tăng tải DB | Phân loại pool wait vs DB exec |
| New client cho mỗi tenant dù cùng credential/cluster | Pool explosion | Cache clients theo security domain |
| Share credential vượt ranh giới bảo mật | Unauthorized reads/writes | Client/security scopes phù hợp |
| Tin GC sẽ close resources | Leak sockets/cursors | Deterministic lifecycle |
| Tắt app mà không drain queue/requests | In-flight failures | Graceful shutdown + status recovery |

## 35. Quan sát và đo hiệu năng

### Metrics tại client

| Nhóm | Metric gợi ý |
|---|---|
| Connections | Active/idle/open/created/closed connections |
| Pool | Wait queue depth, acquisition latency p95/p99, timeouts |
| Operations | In-flight requests, throughput, success/error by operation |
| Retries | Retry attempts, error labels, unknown outcomes |
| Topology | Primary/leader changes, DNS discovery issues |
| Latency | Total operation p50/p95/p99 và client-side queuing |
| Resource | Client heap/direct memory, thread/event-loop utilization |
| Lifecycle | Active sessions/cursors, oldest open transaction |
| Shutdown | Drain duration, canceled/unfinished operations |

### Metrics tại database

- CPU, memory, disk IOPS, network per node.
- Connection count per app/client.
- Slow query/query execution time.
- Replication lag/leader election/resharding.
- Hot partition/key và throttling.
- Transactions in progress, conflicts/aborts.
- Read/write concern hoặc consistency failures.

Tên trên là **metric khái niệm**, cần map sang JMX/Micrometer/SDK telemetry, exporter và database metrics thực tế; không mặc định tồn tại nguyên tên.

### Trace một request

```text
traceId=TR-101
  HTTP handler .......................... 180ms
    pool acquire ........................  60ms
    DB command ..........................  90ms
    deserialization .....................  10ms
    app mapping .........................  20ms
```

Không log password, connection strings chứa secrets hoặc query payload có PII tràn lan. Với multi-tenant metrics, tránh dùng raw userId làm nhãn high-cardinality.

## 36. Kiểm thử đa luồng theo từng phạm vi

Không thể chứng minh thread-safety chỉ bằng nhìn code hoặc một lần chạy. Một bộ thử nghiệm hợp lý bao gồm:

### Test 1 — Shared client, nhiều requests

Khởi tạo một thread-safe client duy nhất; 100 workers đọc/ghi **các keys khác nhau** bằng operation contexts riêng. Theo dõi exceptions, pool waits, leaks.

### Test 2 — Cùng một key

100 workers increment cùng một counter bằng atomic operator. So kết quả với số operations **đã xác nhận commit**; sau đó mô phỏng lost response/retry để thấy khác biệt giữa atomicity và idempotency.

### Test 3 — Session không share

Mỗi worker dùng session/transaction riêng. Không cố “test rằng session chung có thể chạy” rồi dùng nếu thấy một lần không lỗi; việc SDK ghi **not thread-safe** là hợp đồng phải tuân thủ.

### Test 4 — Pool exhaustion

Giới hạn pool nhỏ trong lab, chạy nhiều requests; đo acquisition latency và response khi hết deadline. Kiểm tra tất cả borrowed resources được trả lại khi handler ném exception.

### Test 5 — Cursor early exit

Một query streaming xử lý 1 triệu records, worker dừng sau 100. Kiểm tra cursor/disposable được đóng và server resources không tăng.

### Test 6 — Async cancellation

Hủy subscription/future trong lúc operation đang chạy; đo resource cleanup và kiểm tra database commit outcome **không được suy từ Future canceled**.

### Test 7 — Shutdown dưới tải

Phát write liên tục, kích hoạt graceful shutdown, đảm bảo không nhận việc mới, xử lý in-flight theo deadline, đóng clients đúng thứ tự, ghi lại uncertain operations.

### Test 8 — Failover

Trong lab, đổi leader/primary trong khi app dùng shared client; quan sát reconnect/driver retries, transaction errors và idempotent result reconciliation.

### Test 9 — Multi-tenant concurrency

Gửi đồng thời request thuộc hai tenants. Bảo đảm không có một `currentTenantId` mutable chung làm dữ liệu của tenant A xuất hiện ở B.

### Test 10 — Reactive fan-out

So concurrency có giới hạn và không giới hạn; đo inflight/pool wait/heap/p99. Xác minh resource permit được release trong complete/error/cancel.

## 37. Java concurrency harness minh họa

Đoạn dưới dùng một repository abstraction; **nó không kiểm thử SDK cụ thể**. Mục đích là thể hiện cách tạo nhiều requests dùng chung repository/client và giữ mỗi operation độc lập.

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

interface CounterRepository {
    // Must implement an atomic or idempotent increment contract.
    void increment(String key, String operationId) throws Exception;

    long readAuthoritative(String key) throws Exception;
}

public final class SharedClientConcurrencyDemo {
    public static void exercise(CounterRepository repo) throws Exception {
        int n = 100;
        ExecutorService pool = Executors.newFixedThreadPool(20);
        CountDownLatch start = new CountDownLatch(1);
        List<Future<Void>> results = new ArrayList<>();

        try {
            for (int i = 0; i < n; i++) {
                final int index = i;
                Callable<Void> task = () -> {
                    start.await();
                    repo.increment("test:counter", "request-" + index);
                    return null;
                };
                results.add(pool.submit(task));
            }

            start.countDown();

            for (Future<Void> result : results) {
                result.get(); // propagates exceptions from worker
            }

            long value = repo.readAuthoritative("test:counter");
            System.out.println("value=" + value);
        } finally {
            pool.shutdown();
        }
    }
}
```

### Những giới hạn quan trọng

- Chỉ so được `value==100` nếu counter ban đầu bằng 0, tất cả 100 thao tác đều thành công và repository cam kết semantics phù hợp.
- Nếu method ném exception vì timeout sau commit, `Future.get()` không biết business outcome; cần status/ledger.
- Đừng dùng một `ClientSession` chung bên trong repository khi triển khai.
- Nên chạy fault injection ở lab có primary failover, duplicate delivery và pool pressure, không chỉ happy path.
- Không kiểm thử bằng data production hoặc tài khoản/keys có quyền nhạy cảm.

## 38. Runbook khi Java app gặp timeout hoặc connection leak

### Bước 1 — Xác định phạm vi lỗi

Xem một endpoint, một tenant, một shard, một node hay toàn cluster bị ảnh hưởng. Ghi SDK version, pool size, app instance count.

### Bước 2 — Phân loại timeout

Pool acquisition, connection establishment, socket read, server execution, transaction timeout hay business deadline?

### Bước 3 — Kiểm tra tài nguyên client

Connections active/idle, waiters, long-lived cursors, sessions, event-loop saturation, GC pauses, in-flight futures.

### Bước 4 — Kiểm tra server

Slow queries, locks, hot partition, replication lag, failover, throttling và connection limit.

### Bước 5 — Tìm anti-pattern

Tạo client per request, thiếu `close()`, Jedis shared incorrectly, Mongo session singleton, mutable builder, reactive unbounded fan-out.

### Bước 6 — Giảm tải an toàn

Throttle/bulkhead, hạn chế query nặng, bounded retries. **Không đóng shared client giữa chừng như một cách giải phóng pool** nếu đang có writes.

### Bước 7 — Xử lý kết quả không rõ

Nếu write timeout, kiểm tra transaction/request ledger và idempotency keys. Không replay non-idempotent operation với ID mới.

### Bước 8 — Sửa và đánh giá

Chỉ thay một nhóm cấu hình mỗi lần, đo p99, error rate, pool waits và server metrics trước/sau. Dùng rollout có checkpoint và rollback plan.

### Bước 9 — Kiểm tra shutdown

Nếu redeploy, xem app đã drain in-flight, trả borrowed connections và đóng resources theo ownership chưa.

## 39. Bài tập thực hành

### Bài 1 — Tìm lỗi vòng đời

Một servlet gọi `MongoClients.create()` trong mỗi `doGet()` rồi `close()`. Nêu ba chi phí và thiết kế một Spring singleton bean thay thế.

### Bài 2 — MongoClient vs ClientSession

Vì sao `MongoClient` có thể share giữa threads nhưng một `ClientSession` không nên chạy hai transaction đồng thời? Đề xuất scope cho một unit of work.

### Bài 3 — Cursor leak

Một query trả 100.000 documents; sau 50 records, callback ném exception. Viết cách dùng `try-with-resources` đóng `MongoCursor`.

### Bài 4 — JedisPool

Một class singleton giữ `JedisPool` nhưng cũng giữ một `Jedis` trong field. Vấn đề gì? Chỉnh thành borrow/return per operation.

### Bài 5 — Lettuce connection

Một `StatefulRedisConnection` được dùng cho GET/SET đồng thời. Sau đó team muốn dùng `MULTI/EXEC` và `BLPOP` trên cùng connection. Vì sao cần xem connection-local state và có thể tách connections?

### Bài 6 — Cassandra CqlSession

Một lập trình viên tạo `CqlSession` cho mỗi request vì nghĩ `Session` luôn non-thread-safe. Vì sao suy luận sai? Vòng đời và prepared statements nên tổ chức ra sao?

### Bài 7 — DynamoDB requests

Hai threads dùng cùng `DynamoDbClient`, nhưng sửa cùng mutable `GetItemRequest.Builder`. Phân biệt thread safety của client và builder; viết phương án immutable request per call.

### Bài 8 — Neo4j

Một `Driver` singleton có một `Session` được dùng trong `parallelStream()`. Thiết kế lại session scope và cách tiêu thụ result trước khi đóng.

### Bài 9 — ThreadLocal

Servlet thread pool lưu MongoDB session vào `ThreadLocal` nhưng không gọi `remove()`. Nêu vấn đề khi thread được tái sử dụng. Còn nguy hiểm gì với async continuation?

### Bài 10 — Pool sizing

App có 20 replicas, mỗi client có max 100 connections tới một node. Tính số connection tiềm năng. Nếu node giới hạn 1.000 connections, cần xét gì ngoài việc giảm max pool?

### Bài 11 — Little's Law

Một service có trung bình 500 requests/s và DB operation mất 80 ms. Ước lượng concurrent operations trung bình; giải thích vì sao không thể chọn max pool chỉ dựa vào một con số đó.

### Bài 12 — Backpressure

Một reactive endpoint tạo 20.000 async DB calls đồng thời. Đề xuất giới hạn in-flight, quản lý permit qua complete/error/cancel và cách quan sát overload.

### Bài 13 — Blocking event loop

Một callback Netty gọi `future.join()` để chờ database. Điều gì có thể xảy ra cho những requests khác? Thiết kế async composition hoặc worker executor.

### Bài 14 — Transaction callback retry

Trong `withTransaction`, code charge payment provider rồi update MongoDB. Driver retry callback sau transient error. Rủi ro gì? Thiết kế outbox/ledger/provider idempotency.

### Bài 15 — Unknown outcome

Client timeout sau `INCR` Redis hoặc `$inc` MongoDB. Vì sao không biết đã commit hay chưa? Thiết kế stable `operationId`/ledger.

### Bài 16 — Graceful shutdown

Khi deploy, server còn 200 in-flight writes. Một shutdown hook gọi `mongoClient.close()` ngay. Phân tích rủi ro và đề xuất thứ tự drain → cleanup → close.

### Bài 17 — Multi-tenant race

Repository singleton có field `currentTenantId`. Hai requests thuộc tenant T1/T2 chạy đồng thời. Minh họa lịch sử làm rò dữ liệu, rồi sửa bằng request-local context và authorization.

### Bài 18 — Credential rotation

Một application cần thay certificate khi đang có traffic. Thiết kế giai đoạn overlap giữa client cũ và mới, readiness, drain và shutdown, tránh pool explosion.

### Bài 19 — Fault-injection

Thiết kế lab thử concurrent queries, pool exhaustion, cursor early exit, primary failover, timeout after commit và async cancellation. Những metrics nào chứng minh resource cleanup tốt?

### Bài 20 — Review kiến trúc

Một ứng dụng dùng MongoDB Sync Driver, Lettuce, Cassandra Driver và DynamoDB SDK. Vẽ sơ đồ application beans, chỉ ra object nào share, object nào per request, điểm đóng tài nguyên và ranh giới transaction của từng hệ.

## 40. Checklist trước khi triển khai

1. **SDK/version cụ thể là gì?** Client, session, connection và transaction trong thư viện đó mang nghĩa nào?
2. **Object nào được docs công bố thread-safe?** Những ngoại lệ nào cho blocking/transaction/pubsub?
3. **Ai sở hữu client và pool?** Có một nơi đóng đúng một lần không?
4. **Có tạo client trong request/job loop không?** Nếu có, vì sao cần?
5. **Có session/cursor/mutable builder nào bị giữ làm singleton field không?**
6. **Per-request resources có `try-with-resources`/`finally` không?**
7. **Async operations đã hoàn tất trước khi đóng session/transport chưa?**
8. **Có blocking operation trên event-loop thread không?**
9. **Số in-flight calls có giới hạn và backpressure không?**
10. **Pool sizing đã tính số app replicas và endpoints không?**
11. **Đã tách pool wait, network và DB execution latency chưa?**
12. **Timeout nào chỉ là client timeout?** Outcome của write có thể unknown không?
13. **Retry có giữ cùng logical request ID và dedup không?**
14. **Driver transaction callback có side effect ngoài không idempotent không?**
15. **Multi-tenant context có request-local và được xác thực không?**
16. **Health/readiness có kiểm tra đúng phụ thuộc và không tạo tải lớn không?**
17. **Shutdown có dừng nhận việc và drain trước khi close client không?**
18. **Có theo dõi active sessions, cursors, connections, pool waits và p99 không?**
19. **Đã thử failover, leak, cancellation và concurrent load trong lab chưa?**
20. **Có runbook phục hồi unknown commit và thay credential/transport không?**

## 41. Kết luận

Kết nối Java tới NoSQL không chỉ là “mở socket rồi chạy query”. Một ứng dụng dùng driver thực tế còn quản lý **thread-safe client objects, pool, topology, credential, session, transaction, cursor, async tasks và shutdown**.

Những nguyên tắc cốt lõi:

1. **Share đúng đối tượng.** `MongoClient`, `CqlSession`, `DynamoDbClient`, Neo4j `Driver` và nhiều shared SDK clients thường phù hợp vòng đời ứng dụng; còn MongoDB `ClientSession`, Neo4j `Session`, borrowed Jedis và cursors cần scope hẹp.
2. **Không suy từ tên class.** `CqlSession` không giống Mongo `ClientSession`; Lettuce shared connection không giống một `Jedis` borrowed.
3. **Thread-safe client không bảo vệ business race.** Cần CAS, unique constraints, transaction và idempotency cho dữ liệu.
4. **Vòng đời tài nguyên phải có chủ sở hữu.** Khởi tạo lúc startup, đóng per-request resources ngay, rồi drain và đóng shared clients khi shutdown.
5. **Async không tự tạo backpressure.** Giới hạn in-flight, tránh block event loop, giữ permit đến khi operation thực sự complete/cancel.
6. **Pool không nên quá ít hoặc quá nhiều.** Đo pool waits, topology và database bottlenecks; đừng chữa mọi timeout bằng tăng connections.
7. **Timeout không có nghĩa chưa commit.** Retry non-idempotent writes cần request ledger và status lookup.
8. **Isolation giữa tenants phải là thuộc tính ứng dụng.** Không giữ principal/tenant mutable trong shared repositories và không share credential vượt security boundary.
9. **Kiểm thử bằng lỗi thực tế.** Connection leaks, cursor early-exit, primary failover, callback retry, async cancellation và graceful shutdown mới bộc lộ nhiều sai lầm khó thấy.

Trước khi đặt bất kỳ object kết nối nào vào singleton, hãy tự hỏi:

> **“Object này được SDK cam kết thread-safe ở phạm vi nào? Ai tạo và ai đóng nó? Nó có chứa trạng thái phiên/transaction của một request không? Nếu 100 luồng cùng truy cập, nếu timeout hoặc failover xảy ra, tài nguyên và kết quả ghi có còn được xử lý đúng không?”**

Trả lời được những câu hỏi đó sẽ giúp ứng dụng Java dùng NoSQL **hiệu quả, dễ vận hành và an toàn khi đa luồng**, thay vì phải sửa những lỗi khó truy vết trong production.
