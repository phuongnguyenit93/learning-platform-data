# Tạo MongoClient, quản lý vòng đời và dùng lại kết nối trong MongoDB Java Driver

Khi một ứng dụng Java cần đọc/ghi MongoDB, bước đầu tiên thường là tạo đối tượng **MongoClient**. Tuy nhiên, có một lỗi kiến trúc rất phổ biến: mỗi HTTP request, mỗi lần gọi repository hoặc mỗi thao tác `insertOne()` đều tạo một `MongoClient` mới rồi đóng nó ngay sau đó. Cách làm này không những lãng phí thời gian kết nối mà còn tạo nhiều **connection pools**, tăng số socket, áp lực xác thực và chi phí khám phá topology của MongoDB.

Thiết kế đúng thường đơn giản hơn: **tạo một MongoClient cho mỗi cấu hình MongoDB/cluster trong phạm vi vòng đời ứng dụng, chia sẻ cho nhiều thao tác và nhiều thread, rồi đóng khi ứng dụng thực sự kết thúc**. Đối tượng này không phải một socket TCP đơn lẻ. Nó là một client quản lý topology, thiết lập và giám sát kết nối, sử dụng connection pool và cung cấp các handle `MongoDatabase` / `MongoCollection`.

Bài học thuộc chương **Java Driver** và giải thích:

1. Vai trò và chi phí của `MongoClient` so với `MongoDatabase`, `MongoCollection` và connection vật lý.
2. Tạo client qua `MongoClients.create()`, `ConnectionString` và `MongoClientSettings`.
3. Vòng đời client trong chương trình CLI, service chạy lâu, Spring Boot, batch job và unit/integration tests.
4. Vì sao cần **dùng lại MongoClient** và giới hạn an toàn khi chia sẻ giữa các thread.
5. Connection pooling: tạo kết nối theo nhu cầu, cấu hình và hành vi khi quá tải.
6. URI, timeout, TLS, xác thực, topology discovery và tác động đến số kết nối.
7. Xử lý cursor, session, transaction và shutdown đúng cách.
8. Cách tổ chức repository/service có dependency injection, không tạo client trong từng method.
9. Theo dõi số connection, đo hiệu năng, phòng tránh lỗi cạn pool và connection leaks.
10. Ví dụ thực hành Java Sync Driver, Spring Boot, bài tập và tình huống xử lý sự cố.

**Phạm vi:** Ví dụ chính dùng **MongoDB Java Sync Driver**, package `com.mongodb.client` và API `MongoClients.create()`. Reactive Streams Driver dùng mô hình reactive khác; một số chi tiết về thread/cursor và lifecycle không nên sao chép máy móc giữa hai driver. Khi triển khai, cần dùng phiên bản driver tương thích với MongoDB server và tài liệu chính thức của phiên bản đó.

## 1. Bức tranh tổng quan: MongoClient quản lý gì?

Một ứng dụng Java có thể có cấu trúc:

~~~text
Java application process
 |
 +-- MongoClient (tồn tại suốt thời gian app chạy)
      |
      +-- Cluster / server topology discovery
      +-- Connection pool tới những server thích hợp
      +-- Monitoring và server selection
      +-- TLS / authentication configuration
      +-- Codec registry, read/write concern, retry options
      |
      +-- MongoDatabase("shop")
            |
            +-- MongoCollection("orders")
            +-- MongoCollection("customers")
            +-- MongoCollection("inventory")
~~~

Các thành phần cần phân biệt:

| Thành phần | Bản chất | Nên tạo/dùng thế nào? |
|---|---|---|
| `MongoClient` | Chủ sở hữu cấu hình kết nối, topology state và pool | Tạo ít, dùng lại lâu dài, đóng lúc shutdown |
| `MongoDatabase` | Handle logic cho database với options liên quan | Lấy từ client, nhẹ, dùng lại nếu tiện |
| `MongoCollection<T>` | Handle logic cho collection và codec/options | Lấy từ database, nhẹ, có thể chia sẻ |
| Connection vật lý | Socket/network connection tới MongoDB server | Driver/pool tự cấp phát và tái sử dụng |
| `MongoCursor<T>` | Cursor đang duyệt kết quả | Dùng trong phạm vi ngắn, đóng khi xong |
| `ClientSession` | Phiên logic của client, cần cho transaction | Tạo theo workflow, không dùng chung đồng thời |
| `ClientSession` transaction | Ngữ cảnh một chuỗi thao tác nhất quán | Commit/abort, xử lý lỗi và close session |

**Một MongoClient không đồng nghĩa một TCP connection**. Một client có thể giữ nhiều socket đến các server khác nhau và có nhiều thao tác chạy đồng thời.

## 2. Vì sao không tạo MongoClient ở mỗi request?

Giả sử API có endpoint:

~~~http
GET /orders/ORDER-1001
~~~

Thiết kế không nên dùng:

~~~java
// Ví dụ chống chỉ định cho web service có nhiều request.
public Document findOrder(String orderId) {
    try (MongoClient client =
                 MongoClients.create(System.getenv("MONGODB_URI"))) {
        return client.getDatabase("shop")
                .getCollection("orders")
                .find(Filters.eq("_id", orderId))
                .first();
    }
}
~~~

Mỗi lần gọi `findOrder()`:

1. Tạo client mới, cấu hình mới và tài nguyên liên quan.
2. Thiết lập lại quá trình chọn server, pool và các socket cần dùng.
3. Có thể phải bắt tay TLS, xác thực và chờ kết nối sẵn sàng.
4. Đóng client ngay sau query, loại bỏ khả năng tái sử dụng pool.
5. Nếu nhiều request đồng thời, nhiều client/pool có thể tồn tại chồng nhau.

Ngoài độ trễ, cách làm này khiến ứng dụng khó kiểm soát **tổng số kết nối** tới MongoDB. Đóng mỗi client đúng cách không biến chiến lược này thành hiệu quả.

### 2.1. Cách đúng: chia sẻ client

~~~text
App start
   |
   v
MongoClient shared
   |
   +-- request 1 -> find order
   +-- request 2 -> insert order
   +-- request 3 -> update customer
   +-- scheduler -> aggregate daily report
   |
   v
App shutdown -> client.close()
~~~

Mỗi request tạo **query/filter**, không tạo MongoClient mới. Đối tượng `MongoCollection` được lấy từ client chung.

### 2.2. Khi nào có thể có nhiều MongoClient?

Không phải mọi ứng dụng bắt buộc đúng một MongoClient. Nhiều client có thể hợp lý khi:

- Kết nối đến **những cluster MongoDB khác nhau**.
- Cần **credentials hoặc TLS configuration khác nhau** không thể chia sẻ an toàn.
- Có những workload cần **pool và timeout độc lập**, đã được đo và phê duyệt.
- Một quy trình migration tạm thời cần đọc cluster cũ và ghi cluster mới.

Nhưng không nên tạo client riêng cho từng tenant chỉ vì có trường `tenantId`, nếu tất cả tenant dùng cùng cluster/credentials và yêu cầu phân quyền có thể được đáp ứng bằng thiết kế server-side phù hợp.

**Nguyên tắc:** một client cho mỗi **bộ cấu hình kết nối có ý nghĩa**, không phải một client cho mỗi collection, repository, user hay HTTP request.

## 3. Dependency của MongoDB Java Sync Driver

Với Maven:

~~~xml
<properties>
    <mongodb.driver.version>5.x.y</mongodb.driver.version>
</properties>

<dependencies>
    <dependency>
        <groupId>org.mongodb</groupId>
        <artifactId>mongodb-driver-sync</artifactId>
        <version>${mongodb.driver.version}</version>
    </dependency>
</dependencies>
~~~

`5.x.y` là ký hiệu thay thế: cần chọn **bản phát hành cụ thể** tương thích với runtime/server, theo dependency management hoặc BOM của dự án. Không copy nguyên `5.x.y` thành số phiên bản khi build.

Với Gradle (Groovy DSL):

~~~groovy
dependencies {
    implementation "org.mongodb:mongodb-driver-sync:${mongodbDriverVersion}"
}
~~~

Nếu dùng Spring Boot và Spring Data MongoDB, framework thường có dependency management cho driver. Tránh khai báo **hai phiên bản driver khác nhau** trong cùng dependency graph mà không kiểm tra compatibility.

Các class thường gặp:

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.MongoCollection;
import org.bson.Document;
~~~

Đối với Java Sync Driver hiện đại, không sử dụng mẫu API legacy `new com.mongodb.MongoClient(...)` trong code mới nếu dự án đã chọn namespace/API `com.mongodb.client.MongoClients`.

## 4. Tạo MongoClient đơn giản bằng Connection String

### 4.1. Kết nối MongoDB chạy local

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoDatabase;

public class HelloMongo {
    public static void main(String[] args) {
        try (MongoClient client =
                 MongoClients.create("mongodb://localhost:27017")) {
            MongoDatabase database =
                    client.getDatabase("java_learning");

            database.runCommand(new org.bson.Document("ping", 1));
            System.out.println("MongoDB ping succeeded");
        }
    }
}
~~~

`try-with-resources` phù hợp ở đây vì **toàn bộ vòng đời chương trình chỉ thực hiện một workflow ngắn**; sau lệnh `ping`, chương trình kết thúc và client có thể được đóng.

### 4.2. Dùng MongoDB URI từ biến môi trường

~~~java
String uri = System.getenv("MONGODB_URI");
if (uri == null || uri.isBlank()) {
    throw new IllegalStateException("MONGODB_URI is required");
}

MongoClient client = MongoClients.create(uri);
~~~

Không hard-code mật khẩu trực tiếp:

~~~java
// Không đưa username/password thật vào source code.
String uri = "mongodb://admin:real-password@host:27017/app";
~~~

Credential nên đến từ môi trường/secret manager có giới hạn quyền truy cập. Không in nguyên URI ra log vì nó có thể chứa password, username hoặc thông tin hạ tầng nhạy cảm.

### 4.3. URI có các thành phần gì?

Ví dụ minh họa (không chứa credential thật):

~~~text
mongodb://user:ENCODED_PASSWORD@db1.example:27017,db2.example:27017/shop?replicaSet=rs0&authSource=admin&tls=true
~~~

| Thành phần | Vai trò |
|---|---|
| `mongodb://` | Scheme kết nối thông thường |
| `mongodb+srv://` | Dùng SRV DNS discovery khi deployment phù hợp |
| `user:password@` | Credentials; phải encode ký tự đặc biệt đúng chuẩn |
| `db1,db2` | Danh sách seed hosts để khám phá deployment |
| `/shop` | Database trong URI; không nhất thiết là auth database |
| `replicaSet=rs0` | Yêu cầu/chỉ định tên replica set |
| `authSource=admin` | Database dùng cho xác thực, nếu cần |
| `tls=true` | Bật TLS |

Đối với Atlas, nên sử dụng **connection string được cung cấp cho cluster**, thiết lập network access/TLS và quản lý credentials phù hợp. Với `mongodb+srv`, DNS có thể cung cấp danh sách hosts và các tùy chọn kết nối; không tự thay nó bằng `localhost` hoặc một host tùy ý.

### 4.4. Constructor thường không phải phép thử kết nối

~~~java
MongoClient client = MongoClients.create(uri);
~~~

Chỉ tạo client không chứng minh ứng dụng đã:

- Chọn được primary/secondary phù hợp.
- Bắt tay TLS thành công.
- Xác thực với MongoDB thành công.
- Có quyền đọc/ghi database mong muốn.

MongoDB Java Driver khởi tạo và sử dụng nhiều tài nguyên/kết nối theo nhu cầu. Muốn kiểm tra khả năng liên lạc, hãy thực hiện một thao tác thực tế:

~~~java
client.getDatabase("admin")
        .runCommand(new Document("ping", 1));
~~~

**Ping thành công** xác nhận một bước kết nối/command, không chứng minh user đã có quyền trên mọi collection. Cần kiểm tra riêng các thao tác nghiệp vụ quan trọng.

## 5. Tạo MongoClient bằng MongoClientSettings

Khi cần điều chỉnh pool, server selection hoặc application name, sử dụng **MongoClientSettings.Builder**:

~~~java
import com.mongodb.ConnectionString;
import com.mongodb.MongoClientSettings;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;

import java.util.concurrent.TimeUnit;

public final class MongoClientFactory {
    private MongoClientFactory() {
    }

    public static MongoClient create(String uri) {
        ConnectionString connectionString = new ConnectionString(uri);

        MongoClientSettings settings =
                MongoClientSettings.builder()
                        .applyConnectionString(connectionString)
                        .applicationName("orders-service")
                        .applyToConnectionPoolSettings(pool -> pool
                                .maxSize(50)
                                .minSize(0)
                                .maxConnecting(2)
                                .maxWaitTime(5, TimeUnit.SECONDS))
                        .applyToClusterSettings(cluster -> cluster
                                .serverSelectionTimeout(
                                        5, TimeUnit.SECONDS))
                        .applyToSocketSettings(socket -> socket
                                .connectTimeout(
                                        3, TimeUnit.SECONDS))
                        .build();

        return MongoClients.create(settings);
    }
}
~~~

Các con số **50/0/2/5s/3s** chỉ là bộ **giá trị minh họa**, không phải khuyến nghị mặc định cho mọi hệ thống. Chúng phải được điều chỉnh theo số replica/pod, số request đồng thời, độ dài thao tác, tài nguyên server và mục tiêu độ trễ.

Thứ tự cấu hình cũng quan trọng: `applyConnectionString()` đưa các tùy chọn URI vào builder; các thiết lập gọi **sau đó** có thể ghi đè giá trị liên quan. Nên chọn một nguồn cấu hình chính và tránh cùng lúc đặt `maxPoolSize` trong URI lẫn `maxSize` trong code mà không có quy tắc ưu tiên rõ ràng.

### 5.1. ConnectionString, settings và MongoClient khác nhau thế nào?

~~~text
ConnectionString
  -> Phân tích URI / hosts / auth / TLS / options

MongoClientSettings
  -> Cấu hình client (pool, topology, retry, concern, codec...)

MongoClients.create(settings)
  -> Tạo MongoClient thực tế với resource lifecycle riêng
~~~

`ConnectionString` và `MongoClientSettings` không phải bản thân connection pool. **MongoClient** được tạo từ settings là đối tượng sở hữu tài nguyên liên quan, cần được đóng đúng lúc.

### 5.2. Application name

~~~java
.applicationName("orders-service")
~~~

Giúp nhận diện client trong các thông tin quan sát được MongoDB ghi nhận khi kết nối/handshake. Đặt tên dễ truy vết như `orders-service`, `billing-worker` hoặc `monthly-report-job`; tránh nhét token, user email, credential hoặc dữ liệu nhạy cảm vào application name.

### 5.3. Hạn chế việc cấu hình bằng hàng chục tùy chọn chưa hiểu

Một cấu hình có:

~~~text
maxPoolSize=500
minPoolSize=500
maxConnecting=100
socketTimeoutMS=0
serverSelectionTimeoutMS=0
~~~

không tự làm MongoDB nhanh hơn. Nó có thể tăng socket/memory và làm lỗi khó chẩn đoán. Đầu tiên dùng cấu hình tối giản có đo đạc, sau đó thay đổi theo một giả thuyết về throughput/latency và kiểm nghiệm bằng metrics.

## 6. Vòng đời trong ứng dụng chạy lâu

Với service HTTP, consumer, scheduler hoặc backend sống hàng giờ/ngày, MongoClient nên có vòng đời:

~~~text
SERVICE STARTUP
    |
    v
Create MongoClient once
    |
    v
Create repositories/services from client
    |
    v
Handle many operations concurrently
    |
    v
Stop accepting new work
    |
    v
Finish/cancel outstanding tasks safely
    |
    v
Close cursors/sessions as appropriate
    |
    v
mongoClient.close()
    |
    v
PROCESS EXIT
~~~

### 6.1. Provider quản lý quyền sở hữu client

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoDatabase;

public final class MongoResource implements AutoCloseable {
    private final MongoClient client;

    public MongoResource(String uri) {
        this.client = MongoClients.create(uri);
    }

    public MongoDatabase database(String databaseName) {
        return client.getDatabase(databaseName);
    }

    @Override
    public void close() {
        client.close();
    }
}
~~~

Một service bootstrap:

~~~java
MongoResource mongo = new MongoResource(
        System.getenv("MONGODB_URI")
);
try {
    MongoDatabase database = mongo.database("shop");
    OrderRepository orders = new OrderRepository(
            database.getCollection("orders")
    );

    // Start HTTP server, consumers, scheduled jobs...
    // Những thành phần đó dùng chung OrderRepository/MongoResource.
} finally {
    // Chỉ chạy sau khi các tác vụ dùng DB đã dừng an toàn.
    mongo.close();
}
~~~

Code bootstrap ở trên chỉ minh họa **ownership**. Trong framework web thực, không đặt một `finally` ngay sau `startServerAsync()` nếu hàm start trả về lập tức, vì như vậy client có thể bị đóng trong lúc server vẫn đang nhận request.

### 6.2. Ai có quyền gọi close()?

Quy tắc dễ áp dụng:

> **Thành phần tạo và sở hữu MongoClient chịu trách nhiệm đóng MongoClient.** Repository/service nhận MongoClient hoặc MongoCollection qua dependency injection **không tự ý đóng** tài nguyên chung.

Ví dụ không tốt:

~~~java
public class OrderRepository {
    private final MongoClient sharedClient;

    public OrderRepository(MongoClient sharedClient) {
        this.sharedClient = sharedClient;
    }

    public void findSomething() {
        // ...
        sharedClient.close(); // Sai: phá kết nối của service khác.
    }
}
~~~

Một client đã bị đóng không phải một resource mà application có thể tiếp tục sử dụng. Nếu muốn khởi động lại, cần xây client mới ở đúng tầng ownership.

### 6.3. Shutdown hook trong Java thuần

Trong một daemon Java không có framework quản lý lifecycle, có thể đăng ký shutdown hook:

~~~java
MongoClient client = MongoClients.create(
        System.getenv("MONGODB_URI")
);

Runtime.getRuntime().addShutdownHook(new Thread(() -> {
    client.close();
}, "mongo-client-shutdown"));
~~~

Đây là giải pháp đơn giản, nhưng không đủ cho mọi tình huống:

- Hook không được bảo đảm chạy khi process bị kill cưỡng bức hoặc máy mất điện.
- Các tác vụ dùng MongoDB nên được dừng trước khi đóng client.
- Cần tránh việc nhiều thành phần đóng cùng client không đồng bộ.
- Trong Spring Boot, Jakarta EE hoặc container managed runtime, nên để **lifecycle container** quản lý thay vì thêm hook trùng.

### 6.4. Try-with-resources: đúng và sai

**Đúng cho chương trình ngắn:**

~~~java
try (MongoClient client = MongoClients.create(uri)) {
    client.getDatabase("admin")
            .runCommand(new Document("ping", 1));
}
~~~

**Không đúng trong mỗi HTTP request:**

~~~java
public Order loadOrder(String id) {
    try (MongoClient client = MongoClients.create(uri)) {
        // Đọc một document rồi đóng cả pool.
    }
}
~~~

Không phải `try-with-resources` xấu, mà là **scope được chọn sai**. Scope của MongoClient cần khớp vòng đời owner; scope của cursor/session lại thường ngắn hơn.

## 7. Thiết kế Repository với dependency injection

Một repository nên nhận `MongoCollection` từ tầng bootstrap, thay vì tự biết credentials/URI.

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Updates;
import org.bson.Document;

public final class OrderRepository {
    private final MongoCollection<Document> orders;

    public OrderRepository(MongoCollection<Document> orders) {
        this.orders = orders;
    }

    public Document findById(String orderId) {
        return orders.find(
                Filters.eq("_id", orderId)
        ).first();
    }

    public void markPaid(String orderId) {
        orders.updateOne(
                Filters.eq("_id", orderId),
                Updates.set("status", "PAID")
        );
    }

    public void insert(String orderId, String customerId) {
        orders.insertOne(
                new Document("_id", orderId)
                        .append("customerId", customerId)
                        .append("status", "NEW")
        );
    }
}
~~~

Bootstrap:

~~~java
try (MongoClient client = MongoClients.create(uri)) {
    MongoDatabase database = client.getDatabase("shop");
    MongoCollection<Document> collection =
            database.getCollection("orders");

    OrderRepository repository =
            new OrderRepository(collection);

    repository.insert("ORDER-1001", "CUSTOMER-7");
    System.out.println(repository.findById("ORDER-1001"));
    repository.markPaid("ORDER-1001");
}
~~~

Trong chương trình trên, `MongoClient` tồn tại cho **toàn bộ chuỗi thao tác**. Với service web, provider còn sống lâu hơn và repository sẽ được inject vào các handlers dùng chung.

### 7.1. Repository không cần tạo pool riêng

~~~text
MongoClient shared
      |
      +--> MongoDatabase("shop")
              |
              +--> OrderRepository -> "orders"
              +--> CustomerRepository -> "customers"
              +--> InventoryRepository -> "inventory"
~~~

Mỗi repository có thể giữ `MongoCollection<T>` tương ứng. Những handle này không phải một connection vật lý riêng và không yêu cầu `close()`.

### 7.2. Tách giao tiếp dữ liệu khỏi config hạ tầng

Nên tập trung cấu hình MongoDB tại một nơi:

- URI/KMS/TLS/credentials.
- Tên database.
- Pool/timeouts/read/write concerns.
- Khởi tạo và đóng client.

Repository chỉ có trách nhiệm dựng filter/update/aggregation. Như vậy dễ mock/test, thay môi trường, đo connection pool và không có hàng chục class tự ý tạo MongoClient.

## 8. MongoClient có thread-safe không?

**MongoClient của Java Sync Driver được thiết kế để chia sẻ an toàn giữa nhiều thread.** Các handle như `MongoDatabase`, `MongoCollection` cũng phù hợp để dùng lại và dựng ra các operations đồng thời.

Ví dụ:

~~~java
ExecutorService executor = Executors.newFixedThreadPool(8);
try {
    for (int i = 0; i < 100; i++) {
        final int orderIndex = i;
        executor.submit(() -> {
            String id = "ORDER-" + orderIndex;
            Document value = orders.find(
                    Filters.eq("_id", id)
            ).first();
            // Xử lý value cho request của riêng thread.
        });
    }
} finally {
    executor.shutdown();
}
~~~

Trong ví dụ, **orders** là `MongoCollection<Document>` lấy từ client dùng chung. Cần đảm bảo executor hoàn tất các tác vụ trước khi đóng MongoClient; `shutdown()` chỉ ngừng nhận task mới, không chờ mọi task đã xong.

### 8.1. Các đối tượng không nên chia sẻ bừa bãi giữa thread

| Đối tượng | Nguyên tắc |
|---|---|
| `MongoClient` | Thread-safe, dùng chung được |
| `MongoDatabase`, `MongoCollection` | Handle phù hợp để chia sẻ |
| `ClientSession` | **Không thread-safe**; không dùng cùng session đồng thời ở nhiều thread |
| `MongoCursor` | Dùng/đóng trong scope thao tác; không chia sẻ xuyên request |
| `Document` đang được thay đổi | Mutable; không sửa chung đồng thời nếu thiếu đồng bộ |
| `MongoClientSettings.Builder` | Dùng để dựng cấu hình khi bootstrap, không phải resource để nhiều thread thay đổi |

**Thread-safe MongoClient không có nghĩa mọi object được trả về đều thread-safe.** Một request có thể tự tạo `Document`, `Bson` filters, cursor/session theo nhu cầu; không cần tạo MongoClient mới.

### 8.2. Một HTTP request tương ứng một connection?

Không bắt buộc. Một thao tác database có thể checkout connection từ pool trong lúc thực hiện lệnh, rồi trả connection về pool. Có những ngoại lệ như cursor/getMore, transaction/session pinning, streaming hoặc topology đặc biệt.

Không suy ra mỗi HTTP request phải được “gán một socket MongoDB cố định” từ lúc bắt đầu tới lúc kết thúc. Driver điều phối pool dựa trên từng thao tác và điều kiện runtime.

## 9. Connection pooling: MongoClient không phải một socket

Khi nhiều thread thực hiện I/O tới MongoDB, Java Driver dùng các **connection pools** được quản lý nội bộ. Một pool có thể phục vụ nhiều thao tác theo thời gian, tránh lặp lại toàn bộ công đoạn mở socket, TLS handshake và xác thực.

### 9.1. Vòng đời cơ bản của một connection

~~~text
Thread A                       MongoDB Java Driver
   |                                  |
   |          execute find()          |
   +--------------------------------->|
   |                                  |
   |                      Select suitable server
   |                                  |
   |                      Checkout from its pool
   |                                  |
   |                         Connection available?
   |                           /          \
   |                         yes           no
   |                          |            |
   |                      Reuse        Open new if
   |                      socket       capacity allows,
   |                          |        otherwise wait
   |                          +------------+
   |                                       |
   |                           Send MongoDB command
   |                                       |
   |                           Receive response
   |                                       |
   |                           Return connection
   |                           to pool when eligible
   |                                       |
   <---------------------------------------+
           result / exception
~~~

Pool tái sử dụng các kết nối còn hợp lệ. Nó không cam kết một thao tác sẽ luôn dùng cùng socket vật lý với thao tác trước đó.

### 9.2. Pool theo server, không chỉ theo client

Với replica set gồm nhiều members, driver cần kết nối/giám sát những server trong topology. Số socket tổng không đơn giản bằng giá trị `maxPoolSize` trong cấu hình.

Ví dụ khái niệm:

~~~text
MongoClient
   |
   +-- Server A -> operation connection pool
   +-- Server B -> operation connection pool
   +-- Server C -> operation connection pool
   +-- Monitoring/topology connections
~~~

Các pool vận hành trong phạm vi **server/connection targets** theo topology. Còn có các kết nối phục vụ giám sát. Nếu ứng dụng có 20 pods và mỗi pod có một MongoClient, tổng sockets có thể lớn hơn nhiều so với chỉ nhìn vào `maxPoolSize` của một client.

### 9.3. Pool tạo kết nối theo nhu cầu

Nếu cấu hình:

~~~text
maxPoolSize = 100
minPoolSize = 0
~~~

không nên hiểu cứ tạo MongoClient là MongoDB có ngay 100 connections nghiệp vụ. Pool thường tăng theo nhu cầu đến các giới hạn cấu hình; số connections thực tế phụ thuộc tải, server selection và hoạt động giám sát.

Nếu `minPoolSize` lớn hơn 0, driver có thể duy trì một số lượng connections tối thiểu theo chính sách và trạng thái topology. Điều này giúp giảm cold starts ở một số workload nhưng cũng tăng số socket khi nhiều service replicas chạy đồng thời.

## 10. Các tham số pool quan trọng

| Tùy chọn URI / Java builder | Ý nghĩa | Tác động cần quan sát |
|---|---|---|
| `maxPoolSize` / `maxSize()` | Giới hạn số operation connections của pool tương ứng | Throughput đồng thời, chờ checkout |
| `minPoolSize` / `minSize()` | Số kết nối tối thiểu cần giữ theo policy | Cold-start, sockets nền |
| `maxConnecting` | Giới hạn số kết nối đang được thiết lập đồng thời trong pool | Tốc độ mở rộng pool khi tải tăng đột ngột |
| `maxIdleTimeMS` / `maxConnectionIdleTime()` | Tuổi idle tối đa trước khi connection có thể bị loại khỏi pool | Socket nhàn rỗi, kết nối cũ |
| `maxLifeTimeMS` / `maxConnectionLifeTime()` | Giới hạn tuổi sống của connection | Recycle kết nối định kỳ |
| `waitQueueTimeoutMS` / `maxWaitTime()` | Thời gian tối đa đợi checkout từ pool | Timeout khi pool bận |

Cú pháp builder/URI có thể thay đổi hoặc bị deprecate giữa các bản Java Driver. Tên trong bảng dùng để giải thích khái niệm; khi áp dụng cần xem API version đang dùng.

### 10.1. maxPoolSize không phải số request tối đa

Nếu `maxPoolSize=50`, điều đó không có nghĩa service nhận tối đa 50 HTTP requests. Service có thể nhận hàng nghìn requests nhưng chỉ một số thao tác MongoDB đang dùng connections cùng lúc; những tác vụ khác có thể đợi checkout hoặc bị giới hạn ở tầng application.

Ngược lại, một request có thể thực hiện nhiều DB commands nối tiếp nhau hoặc có nhiều thao tác đang chạy đồng thời. Cần đo **active/check-out connections**, queue/wait latency và throughput thay vì quy đổi trực tiếp HTTP RPS sang maxPoolSize.

### 10.2. Khi pool đã đầy

Giả sử:

~~~text
maxPoolSize = 20
Connection checked out = 20
Incoming operation = 21st
~~~

Operation mới không tự tạo connection thứ 21 vượt quá giới hạn pool. Nó có thể chờ một connection được trả về theo chính sách wait queue, và gặp lỗi nếu vượt thời hạn chờ.

Quá tải pool có thể do:

- Tải đột biến thực sự.
- Query/aggregation chậm, giữ tài nguyên lâu.
- Transaction kéo dài.
- Cursor/streaming không được xử lý đúng.
- Các tác vụ song song không có backpressure.
- Pool đặt quá nhỏ so với concurrency thực tế.

**Tăng maxPoolSize không phải lúc nào cũng là cách xử lý đúng.** Nếu gốc vấn đề là query thiếu index hoặc transaction kéo dài, tăng connections có thể đẩy nhiều workload chậm hơn vào MongoDB và làm server quá tải nặng hơn.

### 10.3. maxConnecting khác maxPoolSize

`maxConnecting` giới hạn số lần **thiết lập connection mới đồng thời** cho pool trong lúc cần mở rộng. Nó không phải số connections có thể hoạt động cùng lúc lâu dài.

Ví dụ minh họa:

~~~text
maxPoolSize = 80
maxConnecting = 2
~~~

Pool có thể mở rộng tới 80 connections khi cần, nhưng không bắt đầu mở 80 socket đồng thời. Đây là một cơ chế kiểm soát áp lực mở kết nối.

### 10.4. Cân nhắc minPoolSize khi có nhiều pods

Giả sử 40 service instances, mỗi instance có nhiều pool theo topology, cấu hình `minPoolSize=30`. Số connections duy trì có thể rất lớn dù traffic nhỏ.

Một ứng dụng có traffic không đều thường nên bắt đầu với cấu hình min pool thấp, đo hiệu ứng cold start rồi mới tăng nếu cần. Không đặt `minPoolSize=maxPoolSize` chỉ để đảm bảo “client luôn nhanh”.

### 10.5. Idle time và lifetime

Kết nối idle quá lâu có thể bị proxy, firewall hoặc load balancer đóng. Driver có cơ chế theo dõi/tái lập kết nối; cấu hình idle/lifetime có thể hỗ trợ tái chế nhưng không thay được cấu hình mạng đúng.

Đừng đặt lifetime cực ngắn để “làm mới cho sạch” nếu điều đó tạo chu kỳ TLS/auth handshake dày đặc và gây latency. Cũng đừng giữ vô hạn các connection không còn phù hợp với môi trường mà không theo dõi lỗi stale socket.

## 11. Timeout: nhiều kiểu chờ khác nhau

Một request có thể mất thời gian ở những khâu riêng:

~~~text
Select server
      |
      v
Wait for pool connection
      |
      v
Establish socket/TLS if required
      |
      v
Send/receive MongoDB command
      |
      v
Fetch cursor batches
~~~

Vì vậy không nên đặt một tên chung “MongoDB timeout” cho mọi lỗi.

| Timeout/giới hạn | Chờ hoặc giới hạn điều gì? |
|---|---|
| Server selection timeout | Driver tìm server thích hợp theo topology/read preference |
| Pool checkout wait timeout | Chờ kết nối có thể sử dụng trong connection pool |
| Connect timeout | Thiết lập TCP connection tới server |
| Socket read timeout / network timeout | Chờ hoạt động mạng/nhận phản hồi theo chính sách driver |
| `maxTimeMS` cho operation | Ngân sách thời gian xử lý lệnh phù hợp phía MongoDB |
| Application/HTTP request timeout | Deadline tổng ở tầng web/app |
| Unified client-side timeout (CSOT) nếu phiên bản hỗ trợ | Một giới hạn tổng cho operation theo API của driver |

**Điểm quan trọng:** tăng `serverSelectionTimeoutMS` không chữa được việc pool checkout quá tải; tăng socket timeout không làm một query thiếu index chạy nhanh.

### 11.1. Server selection timeout

~~~java
MongoClientSettings settings = MongoClientSettings.builder()
        .applyConnectionString(new ConnectionString(uri))
        .applyToClusterSettings(cluster -> cluster
                .serverSelectionTimeout(5, TimeUnit.SECONDS))
        .build();
~~~

Nếu client không chọn được node phù hợp trong thời gian quy định, operation báo lỗi. Nguyên nhân có thể là sai DNS, network, không tìm thấy primary cho write, TLS lỗi, topology chưa ổn định hoặc cấu hình replica set sai.

### 11.2. Checkout timeout

~~~java
.applyToConnectionPoolSettings(pool -> pool
        .maxSize(50)
        .maxWaitTime(3, TimeUnit.SECONDS))
~~~

Nếu pool không cấp connection kịp, thao tác có thể thất bại khi hết thời gian chờ. Cần quan sát **checked-out count**, queue wait latency, query duration và số operations song song.

### 11.3. Connect timeout

~~~java
.applyToSocketSettings(socket -> socket
        .connectTimeout(3, TimeUnit.SECONDS))
~~~

Giới hạn phần thiết lập socket theo driver. Nếu hết connect timeout, đừng mặc định lỗi là “MongoDB thiếu index”: operation còn chưa có network connection sẵn để chạy query.

### 11.4. maxTime trên query

~~~java
import java.util.concurrent.TimeUnit;

Document order = collection.find(
        Filters.eq("customerId", "CUSTOMER-7"))
        .maxTime(2, TimeUnit.SECONDS)
        .first();
~~~

`maxTime()` yêu cầu MongoDB giới hạn thời gian thực thi operation theo semantics của lệnh; nó không nhất thiết bao phủ mọi thời gian trong client như DNS, checkout hoặc mạng. Với một SLA end-to-end, cần đo deadline ở tầng ứng dụng và tính đến **CSOT/unified timeout** của phiên bản driver nếu được hỗ trợ.

### 11.5. Đừng gộp ba lỗi khác nhau

~~~text
MongoTimeoutException: Timed out after waiting for a server
    -> kiểm tra topology/server selection

Timed out waiting for connection from pool
    -> kiểm tra pool saturation/checkout

Socket timeout during command
    -> kiểm tra network/slow operation/timeout settings
~~~

Thông báo chính xác thay đổi theo phiên bản driver, nhưng phân loại nguyên nhân rất khác nhau.

### 11.6. Deadline ở tầng request

Nếu HTTP gateway timeout sau 1 giây nhưng MongoDB operation cho phép chờ 30 giây, server/backend có thể tiếp tục giữ tài nguyên sau khi user đã bỏ cuộc. Hãy thiết kế deadlines nhất quán với SLA, cancellation và retry policy.

Với Sync Driver, thread có thể đang bị block trong một operation. Đừng nghĩ hủy một `CompletableFuture` bên ngoài luôn lập tức chấm dứt mọi I/O trong driver; phải dựa trên cơ chế timeout/cancellation hỗ trợ và shutdown coordination phù hợp.

## 12. Server selection, read preference và topology

MongoClient hiểu những kiểu MongoDB deployment như standalone, replica set hoặc sharded cluster (qua mongos/router) theo URI và quá trình khám phá topology.

### 12.1. Primary và secondary

Trong replica set, các write thông thường cần chọn primary. Các read có thể chọn primary hoặc secondary theo **ReadPreference** đã cấu hình.

~~~java
MongoClientSettings settings = MongoClientSettings.builder()
        .applyConnectionString(new ConnectionString(uri))
        .readPreference(
                com.mongodb.ReadPreference.primary())
        .build();
~~~

Một read preference như `secondaryPreferred` có thể làm đọc từ secondary trong những điều kiện phù hợp, nhưng có rủi ro **replication lag**. Không đổi toàn hệ thống sang secondary chỉ vì muốn giảm tải primary mà bỏ qua consistency yêu cầu.

### 12.2. Read concern và write concern

`ReadConcern` và `WriteConcern` xác định những đảm bảo đọc/ghi riêng. Có thể cấu hình ở client, database, collection hoặc operation tùy API.

~~~java
MongoDatabase database = client.getDatabase("shop")
        .withReadConcern(
                com.mongodb.ReadConcern.MAJORITY)
        .withWriteConcern(
                com.mongodb.WriteConcern.MAJORITY);
~~~

Đây là các **handle với options khác**, không tạo một MongoClient mới hoặc pool mới chỉ vì gọi `withReadConcern()`/`withWriteConcern()`.

### 12.3. Topology thay đổi trong lúc ứng dụng chạy

Khi primary failover, node restart hoặc DNS update, driver có cơ chế khám phá lại topology và chọn server phù hợp. Một MongoClient sống lâu **không mặc định bị buộc mãi vào một host cố định**.

Không xây cơ chế “cứ failover là tạo thêm MongoClient mới cho mọi request” nếu lỗi vốn là tạm thời trong server selection. Thay vào đó, sử dụng retry semantics phù hợp với tính idempotent của nghiệp vụ và điều kiện của driver.

### 12.4. Khi cần kiểm tra tình trạng kết nối

`client.getDatabase("admin").runCommand(new Document("ping",1))` là một probe đơn giản. Nhưng health check không nên đồng thời:

- Tạo rồi đóng client mới liên tục.
- Đòi tất cả thành viên replica set healthy trong mọi thời điểm.
- Xem ping thành công là bằng chứng có quyền ghi.
- Block startup vô hạn nếu điều kiện hạ tầng chưa đáp ứng.

Nên phân biệt **liveness** (process còn chạy), **readiness** (sẵn sàng phục vụ workload chính) và **dependency health**, theo chính sách sản phẩm.

## 13. Cursor: vòng đời ngắn hơn MongoClient

Một truy vấn có thể trả về nhiều document theo các batches. Sync Driver cung cấp `MongoCursor<T>` để duyệt kết quả, và cursor nên được **đóng khi không dùng nữa**.

### 13.1. Duyệt và đóng cursor

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoCursor;
import com.mongodb.client.model.Filters;
import org.bson.Document;

public void processActiveOrders(
        MongoCollection<Document> orders) {

    try (MongoCursor<Document> cursor = orders.find(
            Filters.eq("status", "ACTIVE"))
            .batchSize(200)
            .iterator()) {

        while (cursor.hasNext()) {
            Document order = cursor.next();
            process(order);
        }
    }
}

private void process(Document order) {
    System.out.println(order.getString("_id"));
}
~~~

Khi `try` kết thúc, cursor được đóng, kể cả khi processing ném exception. **MongoClient chung vẫn mở** và có thể được các operations khác dùng tiếp.

### 13.2. Iterator, cursor và collection handle không cùng scope

~~~text
MongoClient:     entire application lifetime
MongoCollection: reused among services/threads
MongoCursor:     one query iteration
Document:        one result / unit of work
~~~

Đừng gọi `mongoClient.close()` để thay cho `cursor.close()` ở cuối mỗi truy vấn.

### 13.3. Tránh giữ cursor qua thời gian người dùng nghĩ

Không giữ `MongoCursor` như một field trong singleton rồi để request sau tiếp tục duyệt. Cursor có thể hết hạn phía server, gắn với session hoặc gặp lỗi topology; còn có nguy cơ nhiều thread thao tác cùng cursor.

Nếu cần pagination, dùng những trang truy vấn có **sort/index/keyset** phù hợp; không giữ một cursor server-side cho toàn bộ phiên duyệt UI kéo dài nhiều giờ.

### 13.4. `first()` và `into()`

~~~java
Document one = orders.find(
        Filters.eq("_id", "ORDER-1001"))
        .first();
~~~

`first()` giúp lấy một phần tử, không yêu cầu service tự duyệt một cursor dài. Tương tự:

~~~java
List<Document> page = orders.find(
        Filters.eq("status", "ACTIVE"))
        .limit(100)
        .into(new ArrayList<>());
~~~

Driver xử lý iteration cho những convenience methods; lập trình viên vẫn cần giới hạn kích thước tập kết quả để không dồn hàng triệu document vào bộ nhớ. Nếu lấy nhiều dữ liệu, ưu tiên xử lý theo batches/cursor.

### 13.5. Cursor đóng không có nghĩa socket bị đóng

Giải phóng cursor có thể kết thúc tài nguyên cursor ở server và trả các tài nguyên liên quan theo trạng thái driver. Connection pool không vì vậy bị phá hủy; MongoClient tiếp tục tái sử dụng connections.

Đây là lý do cần phân biệt rõ **resource của một query** với **resource của cả ứng dụng**.

## 14. ClientSession: tạo theo workflow, không chia sẻ tùy tiện

`MongoClient` an toàn để dùng chung, nhưng `ClientSession` **không được dùng đồng thời bởi nhiều thread**. Session có thể được tạo khi cần liên kết nhiều thao tác hoặc mở transaction.

### 14.1. Dùng session trong scope ngắn

~~~java
import com.mongodb.client.ClientSession;
import com.mongodb.client.MongoClient;

try (ClientSession session = client.startSession()) {
    Document order = orders.find(
            session, Filters.eq("_id", "ORDER-1001"))
            .first();

    System.out.println(order);
}
~~~

Session được đóng cuối block; **client chung** vẫn sống.

### 14.2. Transaction đơn giản

~~~java
try (ClientSession session = client.startSession()) {
    session.startTransaction();

    try {
        orders.updateOne(
                session,
                Filters.eq("_id", "ORDER-1001"),
                Updates.set("status", "PAID")
        );

        payments.insertOne(
                session,
                new Document("_id", "PAY-1001")
                        .append("orderId", "ORDER-1001")
                        .append("amount", 20000)
        );

        session.commitTransaction();
    } catch (RuntimeException e) {
        try {
            session.abortTransaction();
        } catch (RuntimeException abortError) {
            e.addSuppressed(abortError);
        }
        throw e;
    }
}
~~~

Đây là ví dụ cấu trúc; transaction thực tế cần topology hỗ trợ, write concern/read concern phù hợp, logic retry đúng theo **transient transaction errors/unknown commit outcome**, idempotency và kiểm soát business invariants. Không nên copy thành logic thanh toán production mà thiếu xử lý lỗi.

### 14.3. Không giữ session ở singleton

Sai:

~~~java
public final class BadRepository {
    private final ClientSession sharedSession;

    public BadRepository(MongoClient client) {
        this.sharedSession = client.startSession();
    }

    // Nhiều request cùng dùng sharedSession là thiết kế không an toàn.
}
~~~

Đúng hơn: tạo session ở **application service cho một workflow**, truyền xuống repository trong phạm vi workflow đó, đóng sau khi hoàn tất.

### 14.4. Session có giữ connection liên tục không?

Không nên mô tả mọi session luôn pin một TCP connection riêng từ lúc startSession đến lúc close. Hành vi checkout/pinning phụ thuộc loại operation, transaction và topology; một số trạng thái transaction có thể giữ/pin resources.

Vì thế **session/transaction kéo dài** có thể ảnh hưởng pool, nhưng không thể suy ra đơn giản “100 sessions tương đương 100 sockets” trong mọi deployment.

### 14.5. Implicit sessions

Driver có thể tự quản lý logical sessions cho những operations hỗ trợ. Ứng dụng không cần gọi `startSession()` cho mọi `findOne()`. Chỉ dùng explicit session khi workflow thực sự yêu cầu.

## 15. Spring Boot: để container quản lý MongoClient

Với **Spring Boot + Spring Data MongoDB**, framework thường tự cấu hình `MongoClient` và các thành phần liên quan khi dependency/properties hợp lệ. Đây là đối tượng thuộc **application context**, không phải resource tạo mới ở mỗi repository method.

### 15.1. Cấu hình bằng properties

Ví dụ:

~~~yaml
spring:
  data:
    mongodb:
      uri: ${MONGODB_URI}
~~~

`MONGODB_URI` đến từ environment/secret store; không để credential thật trong `application.yml`.

Trong các phiên bản Spring Boot khác nhau, tên cấu hình MongoDB (hoặc namespace của một số property bổ sung) có thể thay đổi. Cần tham chiếu **Spring Boot documentation của version dự án đang dùng**; nếu Boot đã tự tạo MongoClient, không tự khai báo một MongoClient thứ hai chỉ vì muốn gọi `MongoTemplate`.

### 15.2. Repository qua Spring Data

~~~java
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.stereotype.Repository;
import org.bson.Document;

@Repository
public final class OrderStore {
    private final MongoTemplate mongoTemplate;

    public OrderStore(MongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }

    public Document getOrder(String id) {
        return mongoTemplate.findById(
                id, Document.class, "orders");
    }
}
~~~

Framework injects `MongoTemplate`, nó sử dụng client do Spring quản lý. `OrderStore` không tạo hoặc đóng MongoClient.

### 15.3. Nếu cần tạo bean thủ công

Khi auto-configuration không phù hợp, có thể cấu hình riêng:

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class MongoConfiguration {
    @Bean(destroyMethod = "close")
    public MongoClient mongoClient(
            org.springframework.core.env.Environment environment) {
        String uri = environment.getRequiredProperty(
                "app.mongodb.uri");
        return MongoClients.create(uri);
    }
}
~~~

Bean là **singleton theo mặc định** trong Spring; Spring gọi `close()` khi context đóng đúng cách. Nếu tự tạo bean như trên, cần xem cơ chế auto-configuration và cấu hình `MongoDatabaseFactory`/`MongoTemplate` phù hợp, tránh hai beans ngoài ý muốn.

### 15.4. Không đóng client trong @PreDestroy của mọi repository

~~~java
@PreDestroy
public void stop() {
    sharedMongoClient.close();
}
~~~

nếu nhiều repository cùng nhận một bean MongoClient, mỗi repository tự đóng sẽ gây ownership rối và có thể ảnh hưởng shutdown order. Thông thường nên để Spring quản lý việc đóng **bean MongoClient** một lần.

### 15.5. Sync Driver không biến thành reactive chỉ vì chạy trong Spring

Nếu ứng dụng dùng **Spring WebFlux** hoặc event-loop nonblocking, các lời gọi Sync Driver là **blocking I/O**. Không gọi trực tiếp từ event-loop với giả định nó không block.

Có thể sử dụng **Reactive Streams Driver/Spring Data Reactive MongoDB** hoặc di chuyển blocking operations sang thread pool phù hợp theo thiết kế. Dù vậy, nguyên tắc **reusing client và quản lý lifecycle** vẫn giữ vai trò quan trọng, nhưng API và publisher/cancellation khác nhau.

## 16. Batch job, scheduler và CLI

### 16.1. Batch job chạy vài phút

Một batch job thực hiện nhiều lần `insertMany`, `updateOne`, `aggregate` nên dùng **một client cho toàn bộ job**, rồi đóng sau khi job hoàn tất.

~~~java
public static void main(String[] args) {
    String uri = System.getenv("MONGODB_URI");

    try (MongoClient client = MongoClients.create(uri)) {
        MongoDatabase db = client.getDatabase("reporting");
        MongoCollection<Document> events =
                db.getCollection("events");

        // Nhiều queries/batches dùng cùng client.
        runImport(events);
        buildSummary(events);
        verifyCounts(events);
    }
}
~~~

### 16.2. Scheduled task trong một backend

Nếu `@Scheduled` chạy mỗi 5 phút trong cùng Spring Boot service, không tạo một MongoClient mới cho mỗi lần scheduler thức dậy. Dùng `MongoTemplate` hoặc repository đã inject.

### 16.3. Serverless function

Trong môi trường serverless, **cold starts** và **instance reuse** khác với daemon truyền thống. Thường có lợi khi đặt MongoClient ở scope **process/container có thể tái sử dụng** thay vì tạo lại mỗi invocation, nhưng cần xem:

- Thời gian sống thực tế của instance.
- Số concurrent invocations per instance.
- Idle sockets khi instance bị freeze.
- Timeout/network permissions.
- Tổng số instances tăng đột biến.

Đừng phụ thuộc vào shutdown hook luôn chạy trong mọi tình huống serverless. Và đừng tạo hàng nghìn clients cho cùng một warm instance.

### 16.4. Desktop app hoặc chương trình tương tác lâu

Vòng đời MongoClient nên gắn với **main application session** hoặc module kết nối được người dùng mở/đóng. Nếu user đổi cluster/credentials, application có thể cần **đóng client cũ rồi tạo client mới** theo một quy trình chuyển cấu hình có kiểm soát.

## 17. Quan sát connection pool và sự kiện driver

Không nên điều chỉnh pool chỉ bằng cảm giác. MongoDB Java Driver có cơ chế **Connection Pool Monitoring** theo CMAP, cho phép ứng dụng theo dõi khi connection được tạo, checkout, check-in, đóng hoặc khi wait queue lỗi.

### 17.1. Đăng ký ConnectionPoolListener

~~~java
import com.mongodb.ConnectionString;
import com.mongodb.MongoClientSettings;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.event.ConnectionCheckedOutEvent;
import com.mongodb.event.ConnectionCheckedInEvent;
import com.mongodb.event.ConnectionCheckOutFailedEvent;
import com.mongodb.event.ConnectionPoolListener;

public final class PoolMonitoringExample {
    public static MongoClient create(String uri) {
        ConnectionPoolListener listener =
                new ConnectionPoolListener() {
                    @Override
                    public void connectionCheckedOut(
                            ConnectionCheckedOutEvent event) {
                        System.out.println("Connection checked out");
                    }

                    @Override
                    public void connectionCheckedIn(
                            ConnectionCheckedInEvent event) {
                        System.out.println("Connection checked in");
                    }

                    @Override
                    public void connectionCheckOutFailed(
                            ConnectionCheckOutFailedEvent event) {
                        System.out.println(
                                "Connection checkout failed: "
                                        + event.getReason());
                    }
                };

        MongoClientSettings settings =
                MongoClientSettings.builder()
                        .applyConnectionString(
                                new ConnectionString(uri))
                        .applyToConnectionPoolSettings(pool ->
                                pool.addConnectionPoolListener(listener))
                        .build();

        return MongoClients.create(settings);
    }
}
~~~

Đây là ví dụ trực quan. Ở production, không nên in từng checkout ra console vì tốc độ log có thể cao và callback chậm sẽ làm ảnh hưởng hiệu năng. Hãy thu thập counter/timer qua một hệ thống metrics với nhãn có cardinality được kiểm soát, và xem đúng event API của driver version đang dùng.

### 17.2. Những metrics quan trọng

| Metric | Điều muốn biết |
|---|---|
| Connection created/closed | Pool có mở/đóng bất thường không? |
| Checked-out connections | Có bao nhiêu connection đang được sử dụng? |
| Available/idle connections | Có connection sẵn để cấp không? |
| Checkout wait p95/p99 | Tác vụ phải đợi pool bao lâu? |
| Checkout failures | Pool đã hết tài nguyên hoặc connection bị lỗi? |
| Concurrent operations | Service gửi bao nhiêu tác vụ tới DB? |
| Command latency | Query server chậm hay chỉ pool đang chờ? |
| Client instances/pods | Có tạo quá nhiều pool không? |
| Server connection count | Cluster phải duy trì bao nhiêu sockets? |
| CPU/I/O/query scanned | MongoDB có bị nghẽn do workload không? |

Các tên trên là **nhóm metrics cần thu thập**, không phải một tập key cố định được mọi MongoDB Java Driver xuất sẵn.

### 17.3. Xem kết nối phía MongoDB server

Khi có quyền phù hợp:

~~~javascript
db.serverStatus().connections
~~~

Kết quả có thể chứa các trường như current, available, totalCreated tùy phiên bản. Đây là góc nhìn **server**, bao gồm nhiều applications và monitoring connections, không phải riêng một MongoClient Java.

### 17.4. Command monitoring không được lộ dữ liệu

Java Driver có CommandListener để đo thời gian và kết quả commands. Khi đăng ký listener, chỉ nên thu thập command name, duration, trạng thái, thông tin correlation an toàn. Không log toàn bộ command payload vì nó có thể chứa PII, credentials hoặc dữ liệu nghiệp vụ nhạy cảm.

Đo command latency giúp phân biệt server query chậm với pool checkout chậm, nhưng không thay việc kiểm tra explain/index khi workload cần tối ưu.

## 18. Quy mô triển khai và connection storm

### 18.1. Nhiều ứng dụng replicas

Giả sử có 12 service instances, mỗi instance một client, maxPoolSize cho một server là 40. Không thể nói hệ thống luôn có đúng **12 × 40 = 480** connections, vì:

- 40 là giới hạn, không phải số luôn được mở.
- Pool tồn tại theo server và topology phù hợp.
- Read preference làm thay đổi node nhận workload.
- Có sockets dành cho monitoring, reconnect và background work.
- minPoolSize và tải thực tế ảnh hưởng số sockets.

Tuy vậy, **480** là mốc ước lượng năng lực một loại operation pool tới một server nếu tất cả 12 instances đều tải hết 40 kết nối. Tổng số cần tính cho toàn topology và các thành phần khác.

### 18.2. Autoscaling có thể gây connection storm

~~~text
Deployment tăng từ 5 lên 100 pods
            |
            v
Mỗi pod tạo MongoClient
            |
            v
Topology discovery + TLS + authentication
            |
            v
Nhiều connections được tạo khi traffic tăng
~~~

Hướng giảm tác động: kiểm soát scale rate, không tạo nhiều clients mỗi pod, điều chỉnh minPoolSize/maxConnecting/maxPoolSize, giới hạn concurrency, kiểm tra network/server connection capacity.

### 18.3. Pool đầy do query chậm

~~~text
maxPoolSize = 30
30 aggregations đang chạy, mỗi phép mất 20 giây
Các thao tác CRUD khác phải chờ checkout
~~~

Không nên tăng pool lên 300 ngay mà bỏ qua nguyên nhân. Cần xem explain/index, giới hạn số expensive jobs đồng thời, giảm dữ liệu quét và đo khả năng server. Tăng connections vào một MongoDB đã quá tải có thể làm độ trễ chung tệ hơn.

## 19. Phân biệt client leak, cursor leak và session leak

### 19.1. Client leak

~~~java
public void handleRequest() {
    MongoClient client = MongoClients.create(uri);
    // Không đóng và không dùng lại. Mỗi request có thể thêm resource mới.
}
~~~

Quá nhiều clients tạo nhiều connection pools, topology monitors và connections không được giải phóng. Cách sửa đúng là **dùng chung client theo vòng đời ứng dụng**, không chỉ thêm lệnh close vào cuối mỗi request.

### 19.2. Cursor leak

~~~java
MongoCursor<Document> cursor = collection.find().iterator();
// Code thoát method khi lỗi mà không đóng cursor.
~~~

Dù chỉ có một MongoClient, cursor chưa đóng có thể giữ resource không cần thiết. Dùng try-with-resources cho MongoCursor.

### 19.3. Session leak

~~~java
ClientSession session = client.startSession();
// Không đóng session sau workflow.
~~~

ClientSession cần được đóng khi hoàn tất, đặc biệt khi transaction lỗi hoặc bị hủy. Không dựa vào server timeout để thay trách nhiệm giải phóng resource tại client.

### 19.4. Không dựa vào garbage collector

Garbage collection không bảo đảm các tài nguyên network được đóng đúng hạn. Cơ chế finalization của Java cũng không phù hợp để quản lý external resources theo SLA. Hãy chọn ownership cụ thể và chủ động close.

## 20. Kiểm thử lifecycle và repository

### 20.1. Unit test và integration test

Repository nhận MongoCollection qua constructor dễ tách logic nghiệp vụ khỏi hạ tầng. Có thể unit test xử lý dữ liệu, nhưng các hành vi về serialization, network, sessions, pool, failover và transaction cần **integration tests với MongoDB thực trong môi trường kiểm thử**.

### 20.2. Testcontainers

Một ví dụ JUnit 5, MongoDB Java Sync Driver và Testcontainers (dependency/API phải khớp version):

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import org.bson.Document;
import org.junit.jupiter.api.Test;
import org.testcontainers.containers.MongoDBContainer;
import org.testcontainers.utility.DockerImageName;

import static org.junit.jupiter.api.Assertions.assertEquals;

class OrderRepositoryIntegrationTest {
    @Test
    void storesAndReadsAnOrder() {
        try (MongoDBContainer mongo =
                     new MongoDBContainer(
                             DockerImageName.parse("mongo:7.0"))) {
            mongo.start();

            try (MongoClient client = MongoClients.create(
                    mongo.getReplicaSetUrl())) {
                MongoCollection<Document> collection =
                        client.getDatabase("test_shop")
                                .getCollection("orders");

                OrderRepository repository =
                        new OrderRepository(collection);

                repository.insert("O-1", "C-1");

                Document result = repository.findById("O-1");
                assertEquals("C-1",
                        result.getString("customerId"));
            }
        }
    }
}
~~~

Client trong test được tạo cho **toàn bộ phép thử tích hợp**, không phải mỗi MongoDB operation. Có thể tái sử dụng container/client giữa nhiều tests nếu thiết kế isolation và cleanup phù hợp.

**Lưu ý phiên bản:** module/class MongoDBContainer, MongoDB image và replica set setup của Testcontainers thay đổi theo release. Chọn image/API tương thích môi trường thay vì coi tên image trong ví dụ là bắt buộc.

### 20.3. Những điều cần kiểm thử

- Chỉ một client được tạo cho bộ cấu hình tương ứng trong application context.
- Hai repository khác nhau thực sự dùng chung resource.
- Session và cursor được đóng khi có exception.
- Shutdown không đóng client khi worker đang dùng.
- Pool saturation không làm request vô hạn thời gian.
- Khi primary failover, ứng dụng có failure/retry behavior được thiết kế.
- Không log credentials khi connection failure.
- Không ghi/xóa dữ liệu trên database production từ test.

### 20.4. Test shutdown và bất thường

Trong integration tests, có thể kiểm tra việc các operations sau khi client đã đóng không được phép dùng client như còn sống. Tuy nhiên, không nên chủ động đóng MongoClient chung giữa lúc những unit tests khác cùng dùng nó, nếu tests chia sẻ container/application context.

## 21. Retryable reads và writes không thay thiết kế pool

Trong điều kiện được hỗ trợ, Java Driver có thể retry một số thao tác đọc/ghi:

~~~java
MongoClientSettings settings = MongoClientSettings.builder()
        .applyConnectionString(new ConnectionString(uri))
        .retryReads(true)
        .retryWrites(true)
        .build();
~~~

Điều này **không có nghĩa** mọi business request đều an toàn để thử lại. Ví dụ một payment endpoint có side effect phải sử dụng idempotency key và những ràng buộc nghiệp vụ, ngoài cơ chế retry của driver.

Retry cũng không chữa được DNS/TLS sai, credentials bị từ chối hoặc pool bão hòa do một query rất chậm. Nó thậm chí có thể làm độ trễ/tải tăng lên nếu ứng dụng retry liên tục.

### 21.1. Có nên tạo MongoClient mới khi query thất bại?

Thường là **không**. Client có topology monitoring/reconnection và driver retry theo chính sách. Tạo client mới ở mọi catch block có thể gây connection storm và đánh mất connection reuse.

Chỉ chủ động tạo client mới khi owner thực sự đóng client cũ, có thay đổi cluster/credentials/config cần thiết, hoặc có lifecycle đặc biệt đã được kiểm chứng.

### 21.2. Idempotency và lỗi không rõ kết quả

Một write có thể thành công phía server nhưng client mất kết nối trước khi nhận acknowledgment. Nếu application tự retry mà không phân biệt kết quả, có thể tạo duplicate business records.

Nên:

- Dùng khóa _id hoặc business id ổn định.
- Thiết kế idempotent upsert khi phù hợp.
- Kiểm tra error categories và write concern.
- Không gắn mọi exception của driver với hành động “insert lại bằng ID mới”.
- Xem retryable writes như một khả năng của driver trong phạm vi hỗ trợ, không phải lời bảo đảm mọi nghiệp vụ có exactly-once side effect.

## 22. Các lỗi thường gặp khi tạo và dùng MongoClient

### 22.1. Tạo MongoClient thành công nhưng query đầu tiên timeout

**Dấu hiệu:** MongoClients.create() không ném lỗi; find() hoặc ping() mới gặp timeout.

**Giải thích:** create() không nhất thiết thực hiện đầy đủ thao tác network/connect/auth để chứng minh deployment sẵn sàng. Server selection, connect và authorization có thể xảy ra khi operation đầu tiên chạy.

**Hướng xử lý:** xem DNS/hostname, VPN/network, Atlas IP allowlist, TLS, credentials, replica set name, port; thử ping bằng **chính client cấu hình production** trong môi trường an toàn.

### 22.2. Pool chờ lâu nhưng CPU MongoDB bình thường

**Khả năng:** quá nhiều thao tác chờ checkout; pool nhỏ, connection bị pin/giữ lâu, tạo connection mới chậm hoặc có vấn đề ứng dụng.

**Hướng xử lý:** quan sát checked-out count, checkout wait histogram, active sessions/transactions, query duration và network. Đừng nhìn CPU rồi khẳng định không có contention ở pool.

### 22.3. Tăng maxPoolSize không cải thiện throughput

**Nguyên nhân có thể:** bottleneck ở query/index/disk/locks/CPU hoặc một external service; thêm connections chỉ làm nhiều operations tranh tài nguyên.

**Hướng xử lý:** profiling và explain những truy vấn nặng, đo latency end-to-end, tối ưu index/batch/concurrency. Thay pool size từng bước với một baseline rõ.

### 22.4. Database có hàng nghìn connections khi service ít traffic

**Nguyên nhân:** nhiều application replicas, mỗi repository/mỗi request tạo client, minPoolSize quá cao hoặc có nhiều pool theo topology.

**Hướng xử lý:** kiểm tra số MongoClient được tạo mỗi process, wiring Spring, autoscaling và minPoolSize. Không chẩn đoán chỉ dựa trên một serverStatus.connections.current tổng toàn cluster.

### 22.5. `MongoClient has been closed` trong lúc service còn chạy

**Nguyên nhân:** một repository hoặc scope ngắn đã gọi close trên client đang được nhiều component chia sẻ; Spring bean lifecycle có thể bị đóng trước khi jobs xong.

**Hướng xử lý:** xác định owner và shutdown sequence; chỉ owner đóng client khi đã dừng nhận request và hoàn tất/hủy các operations đang chạy.

### 22.6. `MongoTimeoutException` khi tìm primary

**Nguyên nhân có thể:** primary đang failover, network partition, sai replicaSet, DNS, TLS hoặc topology không có node phù hợp.

**Hướng xử lý:** kiểm tra thông tin từ driver về server selection, MongoDB replica set health và kết nối. Không tự chuyển tất cả reads/writes sang một secondary nếu yêu cầu dữ liệu không cho phép.

### 22.7. Authentication failed

**Nguyên nhân:** user/password/authSource sai, credential bị rotate mà service chưa cập nhật, URI chứa ký tự đặc biệt chưa percent-encode hoặc cơ chế auth không phù hợp.

**Hướng xử lý:** kiểm tra secret source, authSource và user roles. Không log raw URI/password để debug.

### 22.8. TLS handshake error

**Nguyên nhân:** truststore/CA chain không được tin cậy, hostname validation fail, certificate hết hạn hoặc kết nối tới endpoint không đúng.

**Hướng xử lý:** sửa cấu hình TLS/cert/hostname; không tắt certificate validation trong production như một “cách chữa nhanh”.

### 22.9. `waitQueueTimeout` khi traffic đột biến

**Nguyên nhân:** nhiều operations đồng thời cần connection và checkout không kịp.

**Hướng xử lý:** đo active checkout vs maxPoolSize, query duration, maxConnecting, số pods và downstream pressure. Áp dụng bounded concurrency/backpressure, tối ưu query; sau đó mới cân nhắc thay maxPoolSize hoặc timeout.

### 22.10. Query rất chậm dù pool còn nhiều connection

Pool availability không đồng nghĩa index/query tốt. Cần xem execution plan, số documents scanned, sort/aggregation stages, kích thước response, server load. Tăng connection count không giúp một collection scan trở thành index scan.

### 22.11. Memory tăng khi đọc một collection lớn

**Nguyên nhân:** gọi .into(new ArrayList<>()) hoặc toList trên hàng triệu documents, buffer toàn bộ kết quả vào JVM.

**Hướng xử lý:** dùng cursor theo batch, đóng cursor đúng scope, giới hạn dữ liệu, aggregate/filter/projection phù hợp và xử lý streaming theo workflow.

### 22.12. Dùng cùng ClientSession trong nhiều CompletableFuture

**Nguyên nhân:** session không thread-safe nhưng bị share sang các task song song.

**Hướng xử lý:** thao tác liên quan một transaction/session theo luồng điều phối phù hợp; không sử dụng session đồng thời từ nhiều threads, và đảm bảo close.

### 22.13. Production có hai MongoClient do Spring wiring

**Nguyên nhân:** framework auto-config tạo bean, rồi dự án tạo thủ công thêm bean hoặc một service gọi MongoClients.create() riêng.

**Hướng xử lý:** xem application context và component initialization; chọn một nguồn cấu hình theo yêu cầu kết nối, tránh lifecycle trùng và pool dư.

### 22.14. App không thoát sau khi job hoàn thành

**Nguyên nhân có thể:** MongoClient chưa đóng, executor/worker threads chưa dừng hoặc background process khác vẫn chạy.

**Hướng xử lý:** xác định owner; đóng client của CLI/batch khi workflow xong, shutdown executor và thread pools đúng thứ tự. Không chỉ ép System.exit(0) để bỏ qua resource lifecycle.

### 22.15. “Connection refused” sau khi đổi cluster

**Nguyên nhân có thể:** app vẫn giữ client cấu hình URI cũ hoặc endpoint mới chưa mở network access. MongoClientSettings được tạo tại startup; sửa một biến môi trường ở runtime không tự làm client cũ đổi server.

**Hướng xử lý:** dùng một quy trình rollout/recreate client khi đổi configuration có chủ đích. Đừng thay URI bằng reflection trong một client đang chạy.

### 22.16. MongoDB server báo Too many connections

**Nguyên nhân:** tổng các client/pools/pods và monitoring connections vượt giới hạn server hoặc môi trường hosting.

**Hướng xử lý:** kiểm kê số replicas, clients/process, minPoolSize, server connection capacity; giảm client churn, cân nhắc throttling và điều chỉnh hạ tầng có đo đạc. Không chỉ tăng server max connections mà bỏ qua những clients bị leak.

## 23. Bảo mật kết nối và secret management

MongoClient là entry point tới database; cấu hình sai có thể làm lộ thông tin dù code CRUD hoàn toàn hợp lệ.

### 23.1. Không lưu password trong repository

Ví dụ sai:

~~~java
String connectionString =
        "mongodb://root:SuperSecretPassword@db.internal:27017";
~~~

Tốt hơn:

~~~java
String uri = System.getenv("MONGODB_URI");
if (uri == null || uri.isBlank()) {
    throw new IllegalStateException("Missing MONGODB_URI");
}
MongoClient client = MongoClients.create(uri);
~~~

Môi trường production nên lấy secret từ hệ thống quản lý secrets, áp dụng rotation và RBAC. Không ghi nguyên URI trong exception wrapping, log cấu hình, metrics hoặc startup banner.

### 23.2. TLS và certificate verification

Đối với kết nối đi qua mạng không tin cậy, áp dụng TLS và xác minh certificate/hostname. Nếu dùng Atlas, hãy dùng TLS configuration đúng cho endpoint.

Không tạo một MongoClient với TLS verification bị tắt chỉ để “tránh lỗi chứng chỉ” trên production. Thay vào đó sửa trust chain, hostname, DNS và certificate.

### 23.3. Least privilege

Một service orders chỉ cần truy cập database/collections phục vụ nghiệp vụ của nó, không nhất thiết sử dụng admin/root credentials. Tách users/roles cho:

- Runtime đọc/ghi nghiệp vụ.
- Migration/index management.
- Backup/restore.
- Monitoring hoặc read-only diagnostics.

MongoClient dùng credentials nào sẽ có quyền tương ứng trên server; việc chia sẻ client giữa nhiều threads không có nghĩa mọi HTTP user có cùng quyền nghiệp vụ. Ứng dụng vẫn cần authorization theo tenant, role và document.

### 23.4. Không để client trở thành endpoint public

Chỉ backend đáng tin cậy mới nên giữ MongoDB credentials/URI. Không nhúng connection string có quyền database vào JavaScript frontend hoặc một ứng dụng mobile dễ giải nén.

### 23.5. Đổi credentials khi service đang chạy

Một MongoClient đang hoạt động được cấu hình bằng credentials tại lúc tạo. Khi secrets rotate, cần có quy trình cập nhật client/instances và theo dõi lỗi auth trong giai đoạn chuyển tiếp. Không giả định sửa file secret ở bên ngoài là mọi socket và credential object đang chạy lập tức thay đổi.

### 23.6. Phân biệt kết nối và quyền nghiệp vụ

MongoDB authentication kiểm tra danh tính service; business authorization kiểm tra người dùng có quyền đọc/sửa order nào. Cả hai đều cần thiết:

~~~text
User request
   |
   v
App authenticates user
   |
   v
App checks tenant/role/document rights
   |
   v
Shared MongoClient authenticates as service principal
   |
   v
MongoDB query contains mandatory business filters
~~~

Không lấy việc một MongoClient kết nối thành công làm bằng chứng mọi request user đều được phép truy cập toàn bộ database.

## 24. Bảng quyết định: vòng đời nào cho từng loại ứng dụng?

| Ngữ cảnh | Phạm vi MongoClient hợp lý | Khi nào close? |
|---|---|---|
| Java CLI chạy vài commands | Một client cho cả chương trình | Sau khi toàn bộ commands xong |
| Import CSV hàng triệu bản ghi | Một client cho toàn bộ batch job | Khi worker đã hoàn tất, kể cả error |
| REST API server | Singleton/application-scoped client | Khi server dừng và requests đã ngừng |
| Spring Boot + Spring Data | Bean MongoClient do container quản lý | Khi application context đóng |
| Scheduler bên trong service | Dùng chung bean/client với service | Không close ở cuối mỗi lần scheduler |
| Kafka/queue consumer | Một client theo process hoặc container | Sau khi consumer dừng nhận và xử lý messages |
| Serverless function | Tái sử dụng client trong warm process khi phù hợp | Theo lifecycle runtime, không dựa vào per-invocation close |
| JUnit integration test đơn lẻ | Client theo test fixture/test container | Sau test hoặc test suite tương ứng |
| Migration qua hai clusters | Một client cho nguồn, một client cho đích | Sau cutover/cleanup từng cluster |
| Nhiều MongoDB credentials riêng biệt | Client theo từng nhóm cấu hình thực sự cần | Khi owner của nhóm kết nối dừng |

Không chọn scope bằng cách nhìn xem method dài hay ngắn. Chọn scope theo **thành phần sở hữu kết nối và sự thay đổi cấu hình cần thiết**.

### 24.1. Khi nào không nên dùng singleton toàn JVM?

Không bắt buộc tạo một **static global MongoClient** dùng cho mọi nhiệm vụ, mọi cluster và mọi credential. Singleton theo **dependency injection container/application context** dễ kiểm soát hơn vì có lifecycle và test isolation.

Nếu có nhiều cluster/credentials hoặc application tạo nhiều isolated contexts, mỗi context có thể sở hữu client phù hợp. Tránh dùng một static mutable variable bị các tests và modules thay đổi ngầm.

### 24.2. Static holder có phải luôn sai?

Một chương trình Java nhỏ có thể có:

~~~java
public final class MongoHolder {
    private static final MongoClient CLIENT =
            MongoClients.create(System.getenv("MONGODB_URI"));

    public static MongoClient get() {
        return CLIENT;
    }
}
~~~

Cách này tạo client một lần cho classloader, nhưng **khó quản lý shutdown**, khó override URI trong tests và có nguy cơ initialization exceptions trước khi app sẵn sàng. Dùng dependency injection hoặc owner rõ ràng thường dễ quản trị hơn.

### 24.3. Có cần cache MongoDatabase/MongoCollection không?

Việc lấy `client.getDatabase("shop")` hoặc `database.getCollection("orders")` là thao tác lấy handle logic tương đối nhẹ, không mở một MongoClient mới.

Có thể lưu `MongoCollection` trong repository để code rõ ràng hoặc lấy từ client khi cần. **Tối ưu quan trọng nhất là dùng lại MongoClient**, không cần xây một cache toàn cục phức tạp cho mỗi tên collection.

## 25. Ví dụ end-to-end: một MongoClient, hai repository, nhiều thao tác

Ví dụ Java Sync Driver sau cho thấy một ứng dụng nhỏ tạo client một lần, sử dụng nhiều collection và đóng đúng khi hoàn tất.

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Updates;
import org.bson.Document;

public final class SharedMongoClientDemo {
    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException("MONGODB_URI missing");
        }

        try (MongoClient client = MongoClients.create(uri)) {
            MongoDatabase db = client.getDatabase("java_learning");

            MongoCollection<Document> customers =
                    db.getCollection("customers");
            MongoCollection<Document> orders =
                    db.getCollection("orders");

            customers.updateOne(
                    Filters.eq("_id", "CUSTOMER-1"),
                    Updates.set("name", "An"),
                    new com.mongodb.client.model.UpdateOptions()
                            .upsert(true)
            );

            orders.updateOne(
                    Filters.eq("_id", "ORDER-1"),
                    Updates.combine(
                            Updates.set("customerId", "CUSTOMER-1"),
                            Updates.set("status", "NEW")
                    ),
                    new com.mongodb.client.model.UpdateOptions()
                            .upsert(true)
            );

            Document customer = customers.find(
                    Filters.eq("_id", "CUSTOMER-1")
            ).first();

            Document order = orders.find(
                    Filters.eq("_id", "ORDER-1")
            ).first();

            System.out.println("Customer found: "
                    + (customer != null));
            System.out.println("Order found: "
                    + (order != null));
        }
    }
}
~~~

Ở ví dụ này:

- **Chỉ một MongoClient** được tạo trong main.
- Hai MongoCollection handles cùng xuất phát từ một MongoDatabase.
- Nhiều update/read dùng chung pool của client.
- Không đóng client sau mỗi thao tác.
- Sau khi main xử lý xong, try-with-resources đóng client.
- UpdateOptions.upsert(true) giúp ví dụ có thể chạy lại trong collection thử nghiệm; không thay những quy tắc concurrency/idempotency cho sản phẩm thực.

**Không chạy ví dụ trên dữ liệu production** khi chưa có database riêng và quyền ghi phù hợp. Hai `_id` cố định chỉ để tiện minh họa lifecycle.

## 26. Bài tập thực hành và câu hỏi tình huống

Các bài tập kiểm tra cách **tạo, chia sẻ và giải phóng MongoClient**. Người học có thể thực hiện trên MongoDB local/test cluster; không cần thay đổi cấu hình server production.

### Bài 1. Có bao nhiêu MongoClient?

Code:

~~~java
public Document getById(String id) {
    MongoClient c = MongoClients.create(uri);
    return c.getDatabase("shop")
            .getCollection("orders")
            .find(Filters.eq("_id", id))
            .first();
}
~~~

**Câu hỏi:** Nếu endpoint gọi 10.000 lần, đoạn này có thể tạo bao nhiêu MongoClient? Lỗi thiết kế nào xuất hiện?

**Đáp án định hướng:** Có thể tạo tới 10.000 instances nếu mỗi lần gọi đều thực thi code đó. Chúng không được close và không được reuse. Cần move client creation lên application bootstrap, inject MongoCollection/Repository, đóng khi app kết thúc.

### Bài 2. Try-with-resources có luôn đúng?

~~~java
try (MongoClient client = MongoClients.create(uri)) {
    return loadOneOrder(client);
}
~~~

**Câu hỏi:** Đúng trong CLI hay trong HTTP endpoint?

**Đáp án:** Đúng khi block bao phủ toàn bộ vòng đời chương trình ngắn. Không tối ưu nếu block chạy cho mỗi HTTP request, vì tạo/đóng pool liên tục.

### Bài 3. Thread-safe

Một ứng dụng có 100 worker threads cần cùng đọc collection orders.

**Câu hỏi:** Có cần tạo 100 MongoClient không?

**Đáp án:** Không. Một MongoClient có thể được chia sẻ giữa threads, cùng với MongoCollection handles. Driver quản lý pooling. Phải phân biệt ClientSession/cursor không thread-safe như client.

### Bài 4. MongoClient và TCP socket

**Câu hỏi:** Một MongoClient có thể có hơn một socket không?

**Đáp án:** Có. MongoClient quản lý pools theo server/topology, và có sockets cho các mục đích khác như monitoring. Một client không phải một TCP connection duy nhất.

### Bài 5. maxPoolSize=100

Ngay sau khi tạo client, service chưa chạy query nào.

**Câu hỏi:** Có chắc 100 connections đã được mở ngay không?

**Đáp án:** Không. Pool thường mở theo nhu cầu và cấu hình minPoolSize/topology. maxPoolSize là giới hạn, không phải số luôn tồn tại.

### Bài 6. Pool đầy

maxPoolSize=20, có 20 operations đang sử dụng connection, một operation thứ 21 đến.

**Câu hỏi:** Driver sẽ luôn mở connection thứ 21 không?

**Đáp án:** Không. Operation có thể chờ connection được trả về và gặp timeout nếu vượt checkout wait limit.

### Bài 7. maxConnecting=2

maxPoolSize=80 và maxConnecting=2.

**Câu hỏi:** Có phải service chỉ chạy tối đa hai operations đồng thời?

**Đáp án:** Không. maxConnecting giới hạn số kết nối mới đang được thiết lập đồng thời; không phải tổng số connections sử dụng lâu dài.

### Bài 8. Nhiều pods

Có 20 service instances, mỗi instance có một client, minPoolSize khá lớn.

**Câu hỏi:** Vì sao nhiều kết nối vẫn xuất hiện dù traffic thấp?

**Định hướng:** Mỗi process duy trì pool riêng theo server/topology, và minPoolSize có thể khiến sockets tồn tại ngay cả khi workload nhỏ. Cần xem số replicas, client instances và pool config.

### Bài 9. Server selection timeout và checkout timeout

Một trường hợp app không tìm được primary, trường hợp khác primary khỏe nhưng pool đã bận hết.

**Câu hỏi:** Hai lỗi có cùng nguyên nhân không?

**Đáp án:** Không. Trường hợp đầu là server selection/topology/network; trường hợp sau là pool checkout/concurrency. Cần metrics và cấu hình khác nhau để điều tra.

### Bài 10. `MongoClients.create()` thành công

**Câu hỏi:** Có chắc password, TLS và quyền ghi đều đúng?

**Đáp án:** Không. Thao tác đầu tiên như ping/find/insert mới kiểm tra những điều kiện tương ứng; ping cũng không chứng minh quyền ghi trên collection đích.

### Bài 11. Dùng client bị đóng

Một repository gọi sharedMongoClient.close() sau `findOne()`.

**Câu hỏi:** Service khác có thể gặp vấn đề gì?

**Đáp án:** Các thao tác tiếp theo qua client chung có thể thất bại vì client đã đóng. Owner của MongoClient mới được đóng khi toàn ứng dụng đã dừng sử dụng.

### Bài 12. Cursor

Code:

~~~java
MongoCursor<Document> cursor =
        collection.find().iterator();
while (cursor.hasNext()) {
    process(cursor.next());
}
~~~

**Câu hỏi:** Thay đổi gì nếu process() ném exception?

**Đáp án:** Bao cursor trong try-with-resources để đảm bảo close khi xử lý hoàn tất hoặc có lỗi. Không đóng MongoClient để thay close cursor.

### Bài 13. Session

Hai CompletableFuture cùng dùng một ClientSession đang chạy transaction.

**Câu hỏi:** Có an toàn không?

**Đáp án:** Không. ClientSession không thread-safe và không được sử dụng đồng thời từ nhiều threads. Các thao tác thuộc cùng transaction cần được điều phối theo semantics được driver hỗ trợ.

### Bài 14. Spring Boot

Ứng dụng đã có Spring Data MongoDB và `MongoTemplate`. Một developer thêm `new MongoClients.create(...)` trong mọi repository.

**Câu hỏi:** Cần sửa thế nào?

**Đáp án:** Dùng bean/framework-managed client và inject MongoTemplate/MongoCollection phù hợp, tránh tạo pool trùng và đóng theo application context.

### Bài 15. Batch job

Một job import 1 triệu records, mỗi batch 500 documents.

**Câu hỏi:** Tạo client mỗi batch hay một client cho toàn job?

**Đáp án:** Một client cho toàn job, dùng lại trong các batches, sau đó close khi hoàn tất hoặc khi cleanup error. Mỗi batch có thể có cursor, request payload và logic retry riêng.

### Bài 16. Serverless

Một function được gọi hàng trăm lần trên cùng một warm container.

**Câu hỏi:** Có nên tạo client ở đầu mỗi invocation?

**Định hướng:** Nên cân nhắc cache/reuse client ở process/container scope, theo concurrency và lifecycle serverless; không coi warm instance luôn tồn tại hoặc shutdown hook luôn chạy.

### Bài 17. Replica set failover

Primary đổi node giữa hai write operations.

**Câu hỏi:** Có cần tự tạo MongoClient khác cho mọi request để tìm primary mới?

**Đáp án:** Thường không. Driver có topology monitoring và server selection. Cần timeout/retry/idempotency phù hợp, không gây connection storm bằng cách thay client liên tục.

### Bài 18. Query chậm làm pool cạn

Có 30 expensive aggregations đồng thời, pool maxSize=30.

**Câu hỏi:** Chỉ tăng maxSize=300 có chắc cải thiện không?

**Đáp án:** Không. Có thể làm server quá tải hơn. Cần tối ưu aggregation/index, đặt concurrency limits và đo thông số before/after.

### Bài 19. Lấy nhiều documents vào bộ nhớ

~~~java
List<Document> all = collection.find()
        .into(new ArrayList<>());
~~~

Collection có 10 triệu documents.

**Câu hỏi:** Dùng client chia sẻ đã đủ an toàn bộ nhớ chưa?

**Đáp án:** Chưa. Việc materialize 10 triệu records có thể làm JVM hết RAM. Cần lọc/projection, limit, cursor và xử lý theo batch.

### Bài 20. Timeout nào?

Một request đợi connection trong pool, chưa gửi command tới MongoDB.

**Câu hỏi:** Tăng `maxTimeMS` của find() có chữa được không?

**Đáp án:** Không. maxTimeMS là giới hạn xử lý lệnh phía MongoDB, trong khi lỗi hiện tại ở pool checkout. Cần xem wait queue timeout, pool saturation và concurrency.

### Bài 21. Read preference

Service đọc từ secondary để giảm tải primary, nhưng user vừa update rồi query ngay lại thấy giá trị cũ.

**Câu hỏi:** Có thể do đâu?

**Đáp án:** Secondary có thể chưa bắt kịp replication. Cần chọn read preference/consistency theo nghiệp vụ, không coi mọi secondary read là read-your-writes.

### Bài 22. Java shutdown hook

Một app đã có Spring Boot quản lý MongoClient bean. Developer thêm một hook đóng cùng client.

**Câu hỏi:** Điều này có cần thiết không?

**Đáp án:** Thường không. Container đã sở hữu lifecycle. Hook trùng có thể làm shutdown order khó kiểm soát; tốt hơn để một owner chịu trách nhiệm đóng sau khi background jobs dừng.

### Bài 23. Testcontainers

Tại sao ví dụ test tạo MongoClient cho cả test, còn production dùng app-scoped client?

**Đáp án:** Vì **owner và vòng đời khác nhau**. Test fixture sở hữu tài nguyên đến khi test hoàn tất; service owner sở hữu đến khi app shutdown. Quy tắc cốt lõi vẫn là không tạo client cho từng CRUD operation.

### Bài 24. Mất kết nối sau network outage

Một developer đề xuất:

~~~text
catch every exception
    -> create another MongoClient
    -> retry original request blindly
~~~

**Câu hỏi:** Vì sao nguy hiểm?

**Định hướng:** Tạo thêm clients tạo pool churn/connection storm, che lỗi DNS/TLS/auth; retry business operations không idempotent có thể gây duplicate. Cần phân loại lỗi, dùng driver retry phù hợp và kiểm tra kết quả nghiệp vụ.

### Bài 25. Connection storm sau deploy

50 pods cùng khởi động, mỗi pod minPoolSize=100.

**Câu hỏi:** Điều gì xảy ra với cluster và cần đo gì?

**Định hướng:** Có thể tạo lượng lớn sockets/handshakes trong thời gian ngắn. Cần xem số replica, pool per-server, maxConnecting, TLS/auth load, server limits, startup readiness và autoscale policy.

### Bài 26. Thiết kế kiến trúc backend

Yêu cầu:

~~~text
Orders REST API       : ~200 requests/second
Customers REST API    : ~100 requests/second
Inventory background  : chạy mỗi phút
Same MongoDB cluster  : cùng service credentials
Deployment            : 8 application instances
~~~

Hãy mô tả:

1. MongoClient nằm ở tầng nào?
2. Ba repositories lấy MongoCollection như thế nào?
3. Khi nào đóng client?
4. Có cần ba pools riêng cho ba collections không?
5. Nếu aggregation inventory làm pool chờ lâu, xử lý bằng cách nào?
6. Khi scale từ 8 lên 30 instances, cần theo dõi gì?

**Đáp án định hướng:** Một client/container instance cho cùng cluster/config, được inject vào repositories và dùng chung. Close khi service shutdown. Không tạo pool theo collection. Giới hạn concurrency/tối ưu aggregation và dùng số liệu checkout latency, query latency, server capacity trước khi thay maxPoolSize; tính tổng connections khi scale.

## 27. Checklist trước khi triển khai

### 27.1. Cấu hình và bảo mật

- [ ] URI lấy từ secret/config nguồn đáng tin cậy, không ghi password trong repository.
- [ ] TLS, certificate verification, authSource và network access đúng môi trường.
- [ ] Driver version tương thích MongoDB server và framework/BOM.
- [ ] ReadPreference/ReadConcern/WriteConcern đáp ứng yêu cầu nghiệp vụ.
- [ ] Không log URI có credentials hoặc MongoDB documents nhạy cảm.

### 27.2. Vòng đời và chia sẻ

- [ ] MongoClient được tạo **một lần theo owner/config**, không theo request.
- [ ] Repositories dùng MongoCollection/MongoTemplate được inject.
- [ ] Chỉ owner hoặc framework lifecycle đóng client.
- [ ] Service ngừng nhận request/jobs và xử lý outstanding work trước khi close.
- [ ] Cursor dùng try-with-resources khi có explicit iterator.
- [ ] ClientSession có scope rõ, không share đồng thời giữa threads.
- [ ] Không trộn Sync Driver blocking I/O vào event-loop nonblocking mà không có chiến lược.

### 27.3. Pool, timeout và hiệu năng

- [ ] maxPoolSize/minPoolSize/maxConnecting được đặt theo đo đạc, không theo cảm tính.
- [ ] Đã tính tổng clients/pods và pool per-server trong topology.
- [ ] Có checkout wait timeout và server selection timeout phù hợp.
- [ ] Có operation deadlines/HTTP timeout nhất quán với SLA.
- [ ] Có metrics checked-out connections, checkout wait/failure và command latency.
- [ ] Có backpressure cho expensive jobs và high concurrency.
- [ ] Slow queries được tối ưu bằng index/explain thay vì chỉ tăng pool.

### 27.4. Kiểm thử và khôi phục

- [ ] Integration tests chạy trên database/container không phải production.
- [ ] Có kiểm thử startup khi MongoDB chưa sẵn sàng và lỗi auth/TLS.
- [ ] Có kiểm thử shutdown, cursor/session cleanup và retry behavior.
- [ ] Có kế hoạch ứng phó failover và connection storm khi autoscaling.
- [ ] Có owner chịu trách nhiệm thay URI/client khi credential hoặc cluster đổi.

## 28. Bảng ghi nhớ nhanh

| Câu hỏi | Trả lời ngắn |
|---|---|
| MongoClient có phải một socket? | Không, nó quản lý cấu hình, topology và pool |
| Mỗi collection có cần client riêng? | Không |
| Mỗi request có cần client riêng? | Không |
| MongoClient có dùng chung giữa threads được không? | Có |
| MongoCollection có cần close không? | Không; đó là handle |
| Cursor có nên close không? | Có, đặc biệt khi tự dùng iterator |
| Session có thread-safe không? | Không; không dùng đồng thời |
| Mỗi new MongoClient mở luôn maxPoolSize sockets? | Không; pool phát triển theo cấu hình và nhu cầu |
| Tăng pool có chữa được query thiếu index? | Không |
| try-with-resources luôn sai? | Không; sai khi dùng sai scope |
| Spring Boot có thể quản lý MongoClient? | Có, qua application context |
| Ping thành công có chứng minh quyền ghi? | Không |
| Query lỗi có nên tạo client mới ngay? | Thường không |
| Client đóng rồi có dùng tiếp được? | Không |
| Đổi URI ở env có tự đổi client đang chạy không? | Không |
| ServerStatus connections là số client của riêng app? | Không |
| Có nên log toàn bộ URI? | Không nếu có credentials hoặc thông tin nhạy cảm |

## 29. Tài liệu tham khảo

Khi áp dụng vào dự án, nên đối chiếu tài liệu chính thức của **MongoDB Java Driver version** đang sử dụng:

- [MongoDB Java Sync Driver — Connect to MongoDB](https://www.mongodb.com/docs/drivers/java/sync/current/connection/)
- [MongoDB Java Sync Driver — Connection Pools](https://www.mongodb.com/docs/drivers/java/sync/current/connection/specify-connection-options/connection-pools/)
- [MongoDB Java Sync Driver — Configure MongoClient](https://www.mongodb.com/docs/drivers/java/sync/current/connection/specify-connection-options/)
- [MongoDB Java Sync Driver — Connection String](https://www.mongodb.com/docs/drivers/java/sync/current/connection/connection-string/)
- [MongoDB Java Sync Driver — Monitoring](https://www.mongodb.com/docs/drivers/java/sync/current/monitoring/)
- [MongoDB Java Sync Driver — Transactions](https://www.mongodb.com/docs/drivers/java/sync/current/crud/transactions/)
- [MongoDB Manual — Connection Pool Overview](https://www.mongodb.com/docs/manual/administration/connection-pool-overview/)
- [MongoDB Java Driver — API Reference](https://mongodb.github.io/mongo-java-driver/)

Các đường dẫn có thể được tổ chức lại giữa các phiên bản tài liệu. Nếu một trang đã chuyển vị trí, hãy mở mục Java Sync Driver từ trang documentation hiện hành và chọn version tương ứng với dependency trong dự án.

## 30. Kết luận

Một MongoClient được quản lý đúng vòng đời là nền tảng để ứng dụng Java kết nối MongoDB ổn định, tiết kiệm tài nguyên và dễ quan sát:

~~~text
                         JAVA APPLICATION
                                |
                                v
                    ONE SHARED MongoClient
                     per connection config
                                |
            +-------------------+-------------------+
            |                   |                   |
            v                   v                   v
       OrderRepo           CustomerRepo         InventoryJob
            |                   |                   |
            +-------------------+-------------------+
                                |
                                v
                   Driver connection pools
                                |
                                v
                    MongoDB deployment
                                |
                                v
                 Reuse connections across work

 Shutdown: stop work -> close cursors/sessions -> close owner client
~~~

**Các nguyên tắc quan trọng nhất:**

1. **Tạo MongoClient ở scope ứng dụng hoặc job**, không tạo cho mỗi request/query/document.
2. **MongoClient thread-safe**, có thể dùng chung giữa repositories và nhiều threads.
3. **MongoDatabase/MongoCollection là handles nhẹ**, không có nghĩa mỗi handle sở hữu một socket/pool riêng.
4. **Connection pool được driver quản lý** và thường tồn tại theo server/topology; maxPoolSize là giới hạn, không phải số kết nối mở cố định.
5. **Cursor và session có vòng đời ngắn hơn client**; phải đóng đúng scope và không chia sẻ những đối tượng không thread-safe.
6. **Chỉ owner đóng client**, sau khi đã dừng tác vụ sử dụng DB; framework như Spring Boot nên quản lý lifecycle bằng bean.
7. **Phân biệt server selection, pool checkout, connect, socket và operation timeouts** để debug đúng nguyên nhân.
8. **Không dùng pool size để che query chậm**; cần đo command latency, checkout wait, server capacity và tối ưu indexing/concurrency.
9. **Tính đến tổng số service instances khi cấu hình pool**: autoscaling tạo thêm MongoClient và pool, có thể gây connection storm.
10. **Bảo vệ credentials, TLS và quyền ứng dụng**, vì connection reuse không thay xác thực và phân quyền nghiệp vụ.

Điểm cốt lõi là **dùng lại một MongoClient đúng scope không chỉ là tối ưu hiệu năng mà còn là cách quản lý tài nguyên có trách nhiệm**. Ứng dụng trở nên dễ bảo trì hơn khi repository không biết URI, thread không tự quản lý socket, cursor/session không sống quá workflow và shutdown có một owner rõ ràng. MongoDB Java Driver đã cung cấp pooling và topology monitoring; nhiệm vụ của kỹ sư ứng dụng là **tạo client đúng lúc, dùng chung đúng cách và đóng khi thật sự không còn ai sử dụng**.
