# Chọn Java Driver đồng bộ hoặc Reactive Streams theo ứng dụng MongoDB

## 1. Câu hỏi kiến trúc: nên chọn Sync Driver hay Reactive Streams Driver?

Khi một ứng dụng Java kết nối MongoDB, có hai cách lập trình phổ biến với driver chính thức:

- **MongoDB Java Sync Driver**: API đồng bộ; lời gọi thường chỉ trả kết quả khi công việc MongoDB cần thiết đã hoàn tất hoặc gặp lỗi. Mã lệnh tuần tự, thuận tiện cho request/response truyền thống, batch jobs, thư viện blocking và nhiều ứng dụng Spring MVC.
- **MongoDB Java Reactive Streams Driver**: API dựa trên chuẩn **Reactive Streams**; các thao tác truy cập database trả về **`Publisher<T>`**, cho phép kết hợp với Reactor (`Mono`/`Flux`), RxJava hoặc `Subscriber` tự triển khai. Công việc được thực hiện **bất đồng bộ**, có hỗ trợ tín hiệu nhu cầu (*demand/backpressure*) và hủy đăng ký (*cancellation*).

Cả hai kết nối tới MongoDB Server/Atlas, sử dụng connection pool, xác thực, TLS, cơ chế BSON/codec và những tính năng database phù hợp driver/version. Đây **không phải** lựa chọn giữa hai loại MongoDB Server khác nhau.

**Không có nguyên tắc “Reactive luôn nhanh hơn Sync”.** Quyết định phải dựa vào **mô hình concurrency của ứng dụng, framework, số request đồng thời, pipeline I/O, yêu cầu codebase, khả năng vận hành và năng lực đội phát triển**.

Ví dụ:

- REST API với Spring MVC, vài trăm request/s, xử lý chủ yếu tuần tự và thư viện JDBC blocking: **Sync Driver thường hợp lý hơn**.
- Spring WebFlux xử lý stream dữ liệu, nhiều tác vụ I/O bất đồng bộ và pipeline đã dùng Reactor: **Reactive Streams Driver** giúp giữ chuỗi non-blocking nhất quán.
- Batch import/ETL Java thuần, cần transactions và code dễ debug: **Sync** là mặc định đáng cân nhắc.
- SSE/WebSocket đẩy dữ liệu từ MongoDB Change Streams đến nhiều subscribers: **Reactive** có lợi về tích hợp stream và hủy subscriber.
- REST API trên JDK 21+ dùng virtual threads: **Sync** có thể xử lý concurrency tốt hơn so với mô hình platform-thread truyền thống, nhưng vẫn phải benchmark connection pool và database limits.

### Bạn sẽ học được gì?

1. Phân biệt **blocking**, **non-blocking**, **asynchronous**, **reactive**, **parallelism** và **backpressure**.
2. Đọc đúng dependency `mongodb-driver-sync` và `mongodb-driver-reactivestreams`.
3. Viết cùng một bài toán CRUD bằng hai API, so sánh cách trả kết quả.
4. Hiểu **cold Publisher**, `subscribe()`, `request(n)`, `cancel()`, `Mono`, `Flux` và error/completion signals.
5. Chọn driver phù hợp Spring MVC, Spring WebFlux, Spring Data, Java virtual threads, batch và message consumer.
6. Quản trị `MongoClient`, connection pools, timeouts, transactions, contexts và error handling.
7. Tránh gọi `block()` hoặc Sync Driver trực tiếp trên event-loop thread.
8. Định nghĩa benchmark hợp lý theo p95/p99, throughput, CPU, heap, threads, connection pool và DB load.
9. Có checklist và scorecard để quyết định cho hệ thống thực.

---

## 2. Hai API chính thức nằm ở đâu?

### 2.1. Java Sync Driver

Namespace thường gặp:

```java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.FindIterable;
```

Cách sử dụng:

```java
Document doc = collection.find(eq("sku", "SKU-1")).first();
```

Giá trị trả là `Document` hoặc `null`. Thread gọi phương thức trên **đợi kết quả** theo semantics blocking. Lỗi thường được ném qua exception.

### 2.2. Java Reactive Streams Driver

Namespace khác:

```java
import com.mongodb.reactivestreams.client.MongoClient;
import com.mongodb.reactivestreams.client.MongoClients;
import com.mongodb.reactivestreams.client.MongoDatabase;
import com.mongodb.reactivestreams.client.MongoCollection;

import org.reactivestreams.Publisher;
```

Ví dụ:

```java
Publisher<Document> publisher =
    collection.find(eq("sku", "SKU-1")).first();
```

Đây là một **mô tả công việc bất đồng bộ**. Lấy `Publisher` không có nghĩa query đã được thực thi. Trên driver Reactive Streams hiện hành, publisher là **cold**: database operation bắt đầu khi có subscription.

### 2.3. Hai namespace dễ nhập nhầm

| Sync | Reactive Streams |
| --- | --- |
| `com.mongodb.client.MongoClient` | `com.mongodb.reactivestreams.client.MongoClient` |
| `com.mongodb.client.MongoCollection` | `com.mongodb.reactivestreams.client.MongoCollection` |
| `FindIterable<Document>` | `FindPublisher<Document>` |
| `Document` trả trực tiếp khi `first()` | `Publisher<Document>` từ `first()` |
| `MongoClients.create(uri)` từ sync package | `MongoClients.create(uri)` từ reactive package |

Trong cùng file Java, **không import cả hai `MongoClient` cùng tên** rồi mong trình biên dịch tự phân biệt. Dùng fully qualified name hoặc tổ chức modules rõ ràng nếu có lý do cần cả hai.

### 2.4. Vì sao MongoDB cung cấp cả hai?

Bài toán sử dụng MongoDB có hai cách tổ chức ứng dụng khác nhau:

- **Imperative/đồng bộ**: gọi MongoDB là một bước trong hàm đang chạy, chờ hoàn thành rồi xử lý kết quả. Tối ưu cho sự đơn giản, đọc hiểu và tích hợp blocking.
- **Reactive/asynchronous**: mô tả chuỗi công việc và truyền dữ liệu/kết quả qua publisher; thread không cần bị giữ để chờ network response theo cách truyền thống. Tối ưu cho I/O orchestration và event-driven pipelines được thiết kế toàn diện.

Cả hai phải tôn trọng giới hạn tài nguyên của MongoDB deployment. Reactive không biến một truy vấn `COLLSCAN` thành `IXSCAN` và không tự tăng throughput của một shard đang bão hòa CPU.

---

## 3. Đồng bộ, bất đồng bộ, non-blocking và reactive khác gì nhau?

### 3.1. Blocking

```text
Thread T1:
  nhận request
  gọi MongoDB find()
      |
      | đợi network + server + response
      v
  nhận Document
  xử lý business logic
  trả response
```

Trong mô hình thread-per-request truyền thống, một platform thread có thể bị chiếm giữ trong khi chờ I/O. Điều đó tăng nhu cầu thread/memory khi số request đồng thời lớn.

**Blocking không phải lỗi thiết kế mặc định.** Với workload hợp lý và thread pools được quản lý, nó có thể rất hiệu quả và đơn giản.

### 3.2. Non-blocking asynchronous

```text
Request handler:
  tạo operation
  đăng ký callback/subscriber
  không chờ đồng bộ
      |
      v
Driver I/O layer:
  gửi MongoDB command
  nhận response sau đó
  phát onNext/onComplete
      |
      v
Handler continuation:
  transform + respond
```

Một thread có thể xử lý công việc khác trong thời gian chờ network. Điều đó **không miễn phí**: cần quản lý callbacks, demand, state, errors và lifetime.

### 3.3. Reactive Streams còn có backpressure

Reactive Streams chuẩn hóa giao thức giữa bên **phát dữ liệu** và bên **nhận dữ liệu**:

- `Publisher<T>`: nguồn phát.
- `Subscriber<T>`: bên nhận.
- `Subscription`: kết nối điều khiển.
- `request(n)`: subscriber cho biết muốn nhận tối đa bao nhiêu items tiếp theo.
- `cancel()`: subscriber không muốn tiếp tục nhận.

Một reactive stream có thể phát nhiều documents qua nhiều lần `onNext`, rồi kết thúc bằng `onComplete` hoặc `onError`.

### 3.4. Reactive không đồng nghĩa parallel

`Flux.from(collection.find(...))` là luồng kết quả có thể bất đồng bộ. Nhưng:

- Một query không nhất thiết chạy song song trên nhiều CPU cores.
- Nhiều `flatMap` có thể khởi chạy nhiều database operations cùng lúc, tạo fan-out.
- MongoDB vẫn chịu giới hạn connection pool, read/write capacity và transactions.
- Backpressure điều tiết demand theo publisher, không tự phân phối tải công bằng trên mọi tenant.

**Parallelism** là số công việc có thể thực sự tiến triển đồng thời; **asynchrony** là việc không phải chờ đồng bộ để tiếp tục.

---

## 4. So sánh nhanh theo tiêu chí kiến trúc

| Tiêu chí | Java Sync Driver | Reactive Streams Driver |
| --- | --- | --- |
| Phong cách | Imperative, gọi và đợi | Publisher, composition, subscription |
| Kết quả | `Document`, `List`, `MongoCursor`, update result | `Publisher<T>`, thường bọc `Mono`/`Flux` |
| I/O ở caller | Blocking | Non-blocking/asynchronous |
| Quản lý concurrency | Threads, executors, virtual threads | Scheduler/event loop + demand |
| Tích hợp Spring MVC | Tự nhiên | Có thể dùng nhưng thường tăng complexity |
| Tích hợp Spring WebFlux | Cần tránh blocking event loop | Tự nhiên qua Spring Data Reactive |
| Batch/CLI | Rõ ràng, dễ tuần tự | Thường nhiều abstraction hơn |
| Streaming | Cursor blocking/iterative | Publisher và backpressure |
| Hủy | Interrupt/timeout và cleanup cursor | Cancellation signal, cleanup không phải rollback |
| Transactions | Imperative session/`withTransaction` | Reactive session được truyền theo reactive chain |
| Debugging | Stack trace tuần tự | Asynchronous stack/context phức tạp hơn |
| Resource risk | Thread saturation | Unbounded flatMap, buffer, event-loop blocking |
| MongoDB performance | Phụ thuộc query/pool/server | Phụ thuộc query/pool/server |
| Kết nối | Connection pool | Connection pool |
| Độ phù hợp | Framework blocking | Pipeline non-blocking end-to-end |

**Điểm thực tế:** Chọn driver theo **cách hệ thống được viết và triển khai**, không theo tên “mới hơn”, “hiện đại hơn” hoặc benchmark một query riêng lẻ.

---

## 5. Dependency Maven/Gradle và version

MongoDB khuyến nghị dùng **MongoDB Driver BOM** để giữ các artifacts liên quan ở phiên bản tương thích. Có thể dùng một MongoDB BOM cho cả hai drivers, nhưng không nhất thiết phải thêm cả hai artifacts vào một application.

**Version trong ví dụ dưới đây là biến cấu hình**: thay `<mongo-driver-version>` bằng phiên bản hiện hành đã được duyệt, tương thích JDK, MongoDB Server và các libraries đi kèm. Không copy nguyên placeholder rồi mong Maven build thành công.

### 5.1. Maven — Sync Driver

```xml
<properties>
    <mongodb.driver.version>5.x.y</mongodb.driver.version>
</properties>

<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.mongodb</groupId>
            <artifactId>mongodb-driver-bom</artifactId>
            <version>${mongodb.driver.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>org.mongodb</groupId>
        <artifactId>mongodb-driver-sync</artifactId>
    </dependency>
</dependencies>
```

Trong ví dụ này, `5.x.y` là placeholder, **không phải Maven version hợp lệ**. Chọn version thực và để BOM quản lý các artifacts liên quan.

**Chú ý về cú pháp:** Maven dùng cú pháp `${mongodb.driver.version}` để tham chiếu tới property đã khai báo. Thay giá trị `5.x.y` của property bằng một version số thực đã kiểm tra; không đổi tên property trong tham chiếu.

### 5.2. Gradle Kotlin DSL — Sync Driver

```kotlin
val mongodbVersion = "5.x.y" // Thay bằng version thực.

dependencies {
    implementation(platform("org.mongodb:mongodb-driver-bom:$mongodbVersion"))
    implementation("org.mongodb:mongodb-driver-sync")
}
```

### 5.3. Gradle Kotlin DSL — Reactive Streams Driver

```kotlin
val mongodbVersion = "5.x.y" // Thay bằng version thực.

dependencies {
    implementation(platform("org.mongodb:mongodb-driver-bom:$mongodbVersion"))
    implementation("org.mongodb:mongodb-driver-reactivestreams")

    // Chỉ khi muốn dùng Project Reactor:
    implementation("io.projectreactor:reactor-core:<approved-version>")
}
```

`reactor-core` cần version đã được quản lý phù hợp hoặc dùng Reactor BOM/Spring Boot dependency management. Driver **không buộc ứng dụng dùng Reactor**: nó xuất `Publisher` theo Reactive Streams; Reactor là thư viện tiện dụng để compose.

### 5.4. Maven — Reactive Streams Driver

```xml
<dependency>
    <groupId>org.mongodb</groupId>
    <artifactId>mongodb-driver-reactivestreams</artifactId>
</dependency>
```

Thêm dòng trên vào `<dependencies>` trong `pom.xml` đã import BOM, đồng thời cấu hình Reactor BOM nếu ứng dụng dùng `reactor-core`. Không cần thêm `mongodb-driver-sync` chỉ để sử dụng reactive driver.

### 5.5. Khi dùng Spring Boot

Với Spring Boot:

- `spring-boot-starter-data-mongodb` thường đưa bạn đến **Spring Data MongoDB imperative** (dựa trên sync driver).
- `spring-boot-starter-data-mongodb-reactive` đưa bạn đến **Spring Data MongoDB reactive** (dựa trên reactive streams driver).
- Spring Boot quản lý các version của Spring Data, MongoDB Java Driver và Reactor trong dependency BOM tương ứng.

**Ưu tiên Boot BOM** nếu đang dùng Boot. Đừng tự override MongoDB driver version mà không đối chiếu compatibility giữa Spring Data release train, Spring Boot và driver.

### 5.6. Chỗ nào xem version và compatibility?

- MongoDB Java Sync Driver docs: `https://www.mongodb.com/docs/drivers/java/sync/current/`.
- MongoDB Reactive Streams Driver docs: `https://www.mongodb.com/docs/languages/java/reactive-streams-driver/current/`.
- Driver compatibility/release notes của đúng major.
- Spring Boot dependency versions và Spring Data MongoDB compatibility.

MongoDB có thể thay đổi các version dẫn đầu trong tài liệu. Bài này không giả định rằng version được dùng hôm nay vẫn là lựa chọn tối ưu cho project sau một năm.

---

## 6. Thiết kế dữ liệu lab chung cho hai driver

Dùng MongoDB local hoặc Atlas development cluster được phép. Mục tiêu là có cùng database, collection và truy vấn để so sánh API.

Mở `mongosh` và chạy **chỉ trên lab**:

```javascript
const lab = db.getSiblingDB("java_driver_choice_lab");

lab.orders.drop();

lab.orders.insertMany([
  {
    _id: "O-101",
    tenantId: "A",
    status: "PAID",
    amount: NumberDecimal("150.00"),
    createdAt: ISODate("2026-11-14T08:00:00Z")
  },
  {
    _id: "O-102",
    tenantId: "A",
    status: "NEW",
    amount: NumberDecimal("29.99"),
    createdAt: ISODate("2026-11-14T08:10:00Z")
  },
  {
    _id: "O-103",
    tenantId: "B",
    status: "PAID",
    amount: NumberDecimal("450.50"),
    createdAt: ISODate("2026-11-14T09:00:00Z")
  },
  {
    _id: "O-104",
    tenantId: "A",
    status: "PAID",
    amount: NumberDecimal("12.00"),
    createdAt: ISODate("2026-11-14T09:15:00Z")
  }
]);

lab.orders.createIndex(
  { tenantId: 1, status: 1, createdAt: -1 },
  { name: "ix_tenant_status_createdAt" }
);
```

Truy vấn nghiệp vụ:

> “Tìm tối đa 10 đơn `PAID` của tenant A, mới nhất trước, chỉ trả những fields ứng dụng cần.”

Kết quả fixture mong đợi (không tính `_id` nếu projection bỏ):

```text
O-104  PAID  2026-11-14T09:15:00Z
O-101  PAID  2026-11-14T08:00:00Z
```

Cả hai driver phải thực hiện **cùng filter, sort, limit và projection**; nếu không, benchmark không công bằng.

---

## 7. Java Sync Driver: ví dụ CRUD hoàn chỉnh

Đây là ứng dụng Java đơn giản kết nối MongoDB, lấy đơn hàng, đếm số lượng, thêm một đơn thử nghiệm rồi đóng client. Đặt `MONGODB_URI` ở environment variable của tiến trình thay vì hardcode credential.

```java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.FindIterable;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Projections;
import com.mongodb.client.model.Sorts;
import org.bson.Document;

public class SyncMongoExample {
    public static void main(String[] args) {
        String uri = System.getenv().getOrDefault(
            "MONGODB_URI", "mongodb://127.0.0.1:27017"
        );

        try (MongoClient client = MongoClients.create(uri)) {
            MongoDatabase database =
                client.getDatabase("java_driver_choice_lab");
            MongoCollection<Document> orders =
                database.getCollection("orders");

            FindIterable<Document> result = orders.find(
                    Filters.and(
                        Filters.eq("tenantId", "A"),
                        Filters.eq("status", "PAID")
                    ))
                .sort(Sorts.descending("createdAt"))
                .limit(10)
                .projection(Projections.include(
                    "tenantId", "status", "createdAt", "amount"
                ));

            for (Document order : result) {
                System.out.println(order.toJson());
            }

            long paidCount = orders.countDocuments(
                Filters.and(
                    Filters.eq("tenantId", "A"),
                    Filters.eq("status", "PAID")
                )
            );

            System.out.println("PAID orders: " + paidCount);
        }
    }
}
```

### 7.1. Các điểm đáng chú ý

- `MongoClients.create(uri)` tạo client có connection pool; **không tạo client mới cho mỗi query/request**.
- `getDatabase` và `getCollection` là API truy cập database/collection, không nhất thiết kích hoạt network round trip ngay.
- `find(...)` tạo `FindIterable`; công việc thực thi khi iterate/first/etc.
- `for (Document order : result)` đọc cursor. Thread hiện tại chờ I/O cần thiết.
- `try-with-resources` phù hợp **CLI/demo**. Với application server, nên tạo `MongoClient` một lần theo lifecycle của service/container, đóng khi shutdown.
- Có thể dùng BSON codecs/POJO mapping thay `Document`.
- Exception có thể được catch bằng các nhóm `MongoException` phù hợp; không nuốt lỗi hoặc tự động retry vô hạn.

### 7.2. Lấy một document

```java
Document order = orders.find(
    Filters.eq("_id", "O-101")
).first();

if (order == null) {
    System.out.println("Not found");
} else {
    System.out.println(order.getString("status"));
}
```

Ưu điểm: biểu thức dễ hiểu với người quen imperative code. Nhưng đoạn `first()` là điểm chờ I/O; không gọi trực tiếp trên Netty event loop của WebFlux.

### 7.3. WriteResult và lỗi

```java
import com.mongodb.client.result.UpdateResult;
import com.mongodb.client.model.Updates;

UpdateResult updated = orders.updateOne(
    Filters.eq("_id", "O-102"),
    Updates.set("status", "PAID")
);

System.out.println("Matched: " + updated.getMatchedCount());
System.out.println("Modified: " + updated.getModifiedCount());
```

Kết quả chỉ có ý nghĩa theo write concern/transaction semantics và điều kiện ứng dụng. Có thể `matchedCount=1` nhưng `modifiedCount=0` nếu giá trị đã như cũ.

### 7.4. Sync cursor và resource ownership

Khi muốn điều khiển cursor trực tiếp:

```java
import com.mongodb.client.MongoCursor;

try (MongoCursor<Document> cursor =
         orders.find(Filters.eq("tenantId", "A")).iterator()) {
    while (cursor.hasNext()) {
        Document doc = cursor.next();
        // Xử lý một document.
    }
}
```

Đóng cursor giúp giải phóng tài nguyên phía client/server khi kết thúc sớm. Với thư viện xử lý lượng dữ liệu lớn, tránh `into(new ArrayList<>())` vô hạn nếu không kiểm soát kết quả.

---

## 8. Java Reactive Streams Driver với Project Reactor

Reactive driver trả về `Publisher`. Project Reactor cung cấp `Mono` (0–1 item) và `Flux` (0–N items) để chuyển Publisher thành pipeline dễ thao tác.

### 8.1. Ví dụ truy vấn

```java
import com.mongodb.reactivestreams.client.MongoClient;
import com.mongodb.reactivestreams.client.MongoClients;
import com.mongodb.reactivestreams.client.MongoCollection;
import com.mongodb.reactivestreams.client.MongoDatabase;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Projections;
import com.mongodb.client.model.Sorts;
import org.bson.Document;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public class ReactiveMongoExample {
    public static void main(String[] args) {
        String uri = System.getenv().getOrDefault(
            "MONGODB_URI", "mongodb://127.0.0.1:27017"
        );

        MongoClient client = MongoClients.create(uri);

        MongoDatabase database =
            client.getDatabase("java_driver_choice_lab");

        MongoCollection<Document> orders =
            database.getCollection("orders");

        Flux<Document> paidOrders = Flux.from(
            orders.find(
                    Filters.and(
                        Filters.eq("tenantId", "A"),
                        Filters.eq("status", "PAID")
                    ))
                .sort(Sorts.descending("createdAt"))
                .limit(10)
                .projection(Projections.include(
                    "tenantId", "status", "createdAt", "amount"
                ))
        );

        // Trong ứng dụng reactive thực tế:
        // return paidOrders.map(Document::toJson);
        // Framework sẽ subscribe và quản lý lifecycle.

        // CHỈ demo CLI: subscribe/đợi completion để main không thoát sớm.
        try {
            java.util.List<Document> result =
                paidOrders.collectList().block(
                    java.time.Duration.ofSeconds(10)
                );

            if (result != null) {
                result.forEach(doc -> System.out.println(doc.toJson()));
            }
        } finally {
            client.close();
        }
    }
}
```

**Cảnh báo quan trọng:** `.block()` ở cuối ví dụ chỉ dùng để giữ chương trình **CLI/main** chờ kết quả. Trong endpoint WebFlux/reactive pipeline, **không được dùng `block()` trên event-loop thread**. Ở đó hãy **trả `Mono`/`Flux` cho framework**.

### 8.2. Truy vấn một document

```java
Mono<Document> byId = Mono.from(
    orders.find(Filters.eq("_id", "O-101")).first()
);

Mono<String> status = byId
    .map(doc -> doc.getString("status"))
    .defaultIfEmpty("NOT_FOUND");
```

Nếu không có document, publisher kết thúc **rỗng**; không tự phát `null` qua `onNext` (Reactive Streams cấm `null`). Đây là điểm khác Sync `first()` có thể trả `null`.

### 8.3. Update

```java
import com.mongodb.client.model.Updates;
import com.mongodb.client.result.UpdateResult;

Mono<UpdateResult> update = Mono.from(
    orders.updateOne(
        Filters.eq("_id", "O-102"),
        Updates.set("status", "PAID")
    )
);

Mono<Long> matched = update.map(UpdateResult::getMatchedCount);
```

Tạo `update` hay `matched` **không gửi lệnh DB ngay**. Chỉ khi có subscription, MongoDB operation mới chạy.

### 8.4. Không tự subscribe trong service nếu framework là subscriber

Ví dụ nguy hiểm trong WebFlux:

```java
public Mono<String> updateStatus() {
    Mono.from(
        orders.updateOne(
            Filters.eq("_id", "O-102"),
            Updates.set("status", "PAID")
        )
    ).subscribe(); // BẮT ĐẦU side effect nhưng không nối vào response.

    return Mono.just("accepted");
}
```

Endpoint có thể trả `accepted` trước khi write thành công. Exception của write bị xử lý ở chuỗi khác, rất khó gắn vào request.

Cách đúng:

```java
public Mono<String> updateStatus() {
    return Mono.from(
        orders.updateOne(
            Filters.eq("_id", "O-102"),
            Updates.set("status", "PAID")
        )
    ).map(result ->
        result.getMatchedCount() > 0 ? "updated" : "not-found"
    );
}
```

Framework subscribe khi có HTTP request; error signal đi theo cùng pipeline, có thể map thành HTTP error và trace.

---

## 9. Cold Publisher và lỗi “không có gì xảy ra”

Reactive driver trả về **cold publishers**: tạo Publisher không thực thi truy vấn cho đến khi có `subscribe`.

```java
Mono<Document> query = Mono.from(
    orders.find(Filters.eq("_id", "O-101")).first()
);

// Đến đây chưa phát sinh query do chưa subscribe.
```

Khi:

```java
query.subscribe(
    doc -> System.out.println(doc.toJson()),
    error -> System.err.println(error.getMessage()),
    () -> System.out.println("Completed")
);
```

driver mới thực hiện công việc và phát tín hiệu đến Subscriber.

### 9.1. Subscribe hai lần thường có hai database operations

```java
Mono<Document> query = Mono.from(
    orders.find(Filters.eq("_id", "O-101")).first()
);

query.subscribe(doc -> System.out.println("A: " + doc));
query.subscribe(doc -> System.out.println("B: " + doc));
```

Mỗi subscription tới publisher do reactive driver tạo đại diện một operation riêng; có thể phát sinh **hai reads**. Trong Reactor, toán tử như `cache()` có thể thay semantics và chia sẻ kết quả, nhưng có trade-off về memory, staleness và error caching. Không cache dữ liệu nhạy cảm/đổi liên tục mà thiếu chiến lược TTL/tenant isolation.

### 9.2. Publisher không phải Future

Một `Publisher` chưa subscribe không tương đương một `CompletableFuture` đã khởi chạy tác vụ. Muốn interop, cần chuyển đổi đúng lifecycle, ownership, cancellation và timeout. Tự gọi `subscribe` rồi trả `CompletableFuture` mà không propagate cancellation/error có thể tạo leak.

### 9.3. Reactor signals

```text
onSubscribe(subscription)
    |
request(n)
    |
onNext(document) 0..n lần
    |
onComplete()  hoặc  onError(error)
```

Sau một terminal signal (`onComplete` hoặc `onError`), stream không phát thêm `onNext`.

---

## 10. Backpressure trong thực tế

### 10.1. Bài toán producer nhanh hơn consumer

Giả sử MongoDB trả nhiều document, còn ứng dụng cần gọi một HTTP API chậm cho mỗi item:

```text
MongoDB finds: 1000 documents/s
Remote service: 20 requests/s
```

Nếu ứng dụng materialize tất cả documents rồi mở hàng nghìn network requests, memory và connection pools có thể bị bão hòa.

Reactive Streams cho phép Subscriber/Operator truyền **demand** và giới hạn số items trong pipeline. Nhưng **backpressure không tự quyết định business concurrency**; developer vẫn phải đặt giới hạn.

### 10.2. Giới hạn số công việc đồng thời

```java
Flux<Document> source = Flux.from(
    orders.find(Filters.eq("status", "PAID"))
);

Flux<String> transformed = source.flatMap(
    order -> callRemoteService(order), // Mono<String> non-blocking.
    16                                 // Tối đa 16 inner subscriptions.
);
```

`callRemoteService` là hàm **giả định** trả `Mono<String>`. Trong ứng dụng thực, nó cần dùng non-blocking HTTP client như Reactor Netty/WebClient, không chạy Java blocking HTTP call ngay trong lambda.

Tăng concurrency lên 1000 có thể làm downstream quá tải và không tăng throughput. Tuning phải đo pool usage, latency, errors và retry rates.

### 10.3. Buffer và giới hạn bộ nhớ

Các toán tử như `collectList()`, `buffer()`, `onBackpressureBuffer()` có thể tích lũy dữ liệu. Ví dụ:

```java
Mono<java.util.List<Document>> all = Flux.from(
    orders.find()
).collectList();
```

Đoạn này có thể đưa **toàn bộ collection vào RAM** nếu không giới hạn query. Reactive code vẫn có thể bị `OutOfMemoryError`.

Tốt hơn với endpoint trả danh sách giới hạn:

```java
Flux<Document> page = Flux.from(
    orders.find(Filters.eq("tenantId", "A"))
      .sort(Sorts.descending("createdAt", "_id"))
      .limit(50)
);
```

Với streaming vô hạn, cần thiết kế demand, queue, timeouts và cancellation.

### 10.4. Backpressure không biến MongoDB thành broker

Khi dùng Change Streams hoặc tailable cursors, backpressure giúp quản lý lượng dữ liệu ứng dụng nhận, nhưng **không thay** durable offset/resume token, consumer checkpoint, lưu dữ liệu và chính sách phục hồi. MongoDB vẫn có oplog/change-stream retention và server cursor behavior riêng.

---

## 11. Web framework là tiêu chí chọn driver quan trọng nhất

### 11.1. Spring MVC / Servlet

```text
HTTP request -> servlet worker thread
    -> service method
    -> Sync MongoDB driver
    -> result
    -> HTTP response
```

Ưu điểm:

- Luồng code dễ theo dõi.
- Hợp với JDBC, legacy SDKs và nhiều thư viện blocking.
- Validation, transactions và security context theo thread thường dễ xử lý.
- Dễ onboarding cho Java developers đã quen imperative style.

Nhược điểm:

- Nếu mỗi request giữ một platform thread trong lúc chờ DB, số thread/memory có thể tăng dưới high concurrency.
- Cần thread pool/timeout/backpressure ở ingress.
- Không thể giải quyết database pool saturation chỉ bằng tăng số servlet threads.

**Phù hợp khi** service xử lý tuần tự, concurrency thấp/vừa, team ưu tiên simplicity, hoặc dependencies đã blocking.

### 11.2. Spring WebFlux / Reactor Netty

```text
HTTP request -> event loop
    -> Mono/Flux service
    -> Reactive MongoDB publisher
    -> async completion
    -> HTTP response
```

Ưu điểm:

- Giữ non-blocking pipeline end-to-end.
- Hợp với reactive WebClient, message streams, SSE.
- Không cần chiếm một platform thread cho mỗi request đang chờ MongoDB.
- Dễ compose timeout/cancel/retry ở mức pipeline.

Nhược điểm:

- Debugging, context propagation và transaction lifetime phức tạp.
- Chỉ một lời gọi blocking có thể làm nghẽn event-loop.
- Toán tử dùng sai có thể tạo fan-out, buffer và subscription leaks.
- Đội phát triển cần hiểu error, demand và scheduler semantics.

**Phù hợp khi** ứng dụng đã dùng WebFlux và các dependencies chính đều non-blocking.

### 11.3. Spring WebFlux nhưng dùng Sync Driver?

Không nên gọi Sync Driver trực tiếp trong code thực thi trên event-loop:

```java
// SAI trong handler WebFlux nếu chạy trên event-loop:
public Mono<String> findStatus() {
    Document doc = syncOrders.find(eq("_id", "O-101")).first();
    return Mono.just(doc == null ? "missing" : doc.getString("status"));
}
```

Thao tác `first()` blocking trước khi `Mono.just` được tạo, chiếm event-loop.

**Giải pháp chuyển tiếp** khi chưa thể đổi driver:

```java
import reactor.core.scheduler.Schedulers;

public Mono<String> findStatus() {
    return Mono.fromCallable(() -> {
        Document doc =
            syncOrders.find(Filters.eq("_id", "O-101")).first();
        return doc == null ? "missing" : doc.getString("status");
    }).subscribeOn(Schedulers.boundedElastic());
}
```

Đây là **bridge** để offload blocking I/O sang boundedElastic threads, không biến Sync Driver thành non-blocking và không nên được coi tương đương native reactive driver khi load lớn. BoundedElastic cũng có giới hạn threads/queues.

### 11.4. Dùng Reactive Driver trong Spring MVC?

Có thể, nhưng phải quyết định request sẽ trả `Mono/Flux` theo cơ chế MVC async hay chặn chờ. Nếu gọi `block()` rồi trả DTO trong controller MVC, bạn đang trả lại mô hình blocking nhưng thêm complexity.

Điều đó không tự sai nếu chỉ tích hợp tạm, nhưng nên hỏi: **lợi ích cụ thể là gì và có benchmark chứng minh không?** Nếu framework/application chủ yếu blocking, Sync thường dễ vận hành hơn.

---

## 12. Spring Data MongoDB: chọn tầng abstraction nhất quán

Trong Spring Boot, đội ngũ thường không gọi raw driver trực tiếp mà dùng Spring Data:

| Imperative | Reactive |
| --- | --- |
| `MongoTemplate` | `ReactiveMongoTemplate` |
| `MongoRepository<T, ID>` | `ReactiveMongoRepository<T, ID>` |
| Trả `T`, `List<T>`, `Optional<T>` | Trả `Mono<T>`, `Flux<T>` |
| `MongoTransactionManager` | `ReactiveMongoTransactionManager` |
| `spring-boot-starter-data-mongodb` | `spring-boot-starter-data-mongodb-reactive` |

### 12.1. Imperative repository

```java
import org.springframework.data.mongodb.repository.MongoRepository;
import java.util.List;

public interface OrderRepository
        extends MongoRepository<Order, String> {
    List<Order> findByTenantIdAndStatus(
        String tenantId,
        String status
    );
}
```

`Order` là domain entity do ứng dụng định nghĩa với mapping ID/type phù hợp. Method trả `List` và tương tác blocking theo Spring Data imperative.

### 12.2. Reactive repository

```java
import org.springframework.data.mongodb.repository.ReactiveMongoRepository;
import reactor.core.publisher.Flux;

public interface ReactiveOrderRepository
        extends ReactiveMongoRepository<Order, String> {
    Flux<Order> findByTenantIdAndStatus(
        String tenantId,
        String status
    );
}
```

Service:

```java
public Flux<Order> paidOrders(String tenantId) {
    return repository.findByTenantIdAndStatus(
        tenantId, "PAID"
    );
}
```

Trong Spring WebFlux controller, trả `Flux<Order>` hoặc `Mono<Response>` để framework subscribe. Không gọi `subscribe()` trong repository/service.

### 12.3. Không nhầm reactive repository với non-blocking toàn hệ thống

Một endpoint có reactive repository nhưng:

- gọi JDBC blocking,
- gọi REST bằng `RestTemplate`,
- đọc file lớn đồng bộ,
- chạy CPU-heavy transform trực tiếp trên event loop,

thì **toàn pipeline không còn non-blocking thực sự**.

Đặt câu hỏi về **mọi thành phần I/O trên critical path**, không chỉ MongoDB driver.

---

## 13. Java Virtual Threads có thay đổi lựa chọn không?

**Virtual threads** có mặt ổn định trong Java **21+** (Project Loom). Chúng làm việc viết **mã blocking kiểu imperative** nhưng phục vụ nhiều tasks concurrent trở nên thực tế hơn so với mô hình một platform thread cho mỗi request.

### 13.1. Ví dụ Java 21+

```java
import java.util.concurrent.Executors;

try (var executor =
         Executors.newVirtualThreadPerTaskExecutor()) {

    for (String orderId : java.util.List.of(
            "O-101", "O-102", "O-103")) {

        executor.submit(() -> {
            Document order =
                orders.find(Filters.eq("_id", orderId)).first();

            System.out.println(
                orderId + " -> " +
                (order == null ? "missing" : order.getString("status"))
            );
        });
    }
}
```

Ở đây `orders` là một `MongoCollection<Document>` của Sync Driver đã được tạo và giữ sống trong khi tasks chạy. Executor `close()` đợi các tasks hoàn tất theo semantics Java hiện hành.

**Ý tưởng:** Giữ code imperative dễ đọc, nhưng không nhất thiết giữ một OS thread cho mỗi request đang chờ.

### 13.2. Virtual threads không làm được gì?

Chúng **không**:

- Giảm số MongoDB operations.
- Tăng giới hạn server connections.
- Làm query thiếu index chạy nhanh.
- Loại bỏ network latency.
- Thay thế timeouts hoặc circuit breaking.
- Bảo đảm không có pinning hoặc CPU saturation.
- Tự làm cho mọi library blocking tương tác tốt với scheduler.

Nếu 5.000 virtual threads cùng chờ 100 connections, pool vẫn có giới hạn; request queues và p99 vẫn có thể tăng.

### 13.3. Khi nào Sync + virtual threads là một lựa chọn mạnh?

- Ứng dụng JDK 21+.
- Codebase imperative có nhiều thư viện blocking.
- Concurrency cao nhưng mỗi request không CPU-heavy.
- Team muốn tránh complexity của reactive composition.
- Thread/memory trước đây là bottleneck chính.
- Benchmark chứng minh DB pool/server vẫn đáp ứng SLO.

Reactive vẫn có ưu thế khi **đã dùng Reactor/stream composition end-to-end**, cần backpressure sâu và cancellation của stream. Virtual threads không đơn giản thay thế hoàn toàn semantics Publisher.

---

## 14. MongoClient và connection pool của cả hai driver

Cả Sync và Reactive Streams Driver đều có **connection pooling**.

### 14.1. Không tạo một client cho mỗi request

**Sai**:

```java
public Document loadOne(String uri, String id) {
    try (com.mongodb.client.MongoClient client =
             com.mongodb.client.MongoClients.create(uri)) {
        return client.getDatabase("app")
            .getCollection("orders")
            .find(Filters.eq("_id", id))
            .first();
    }
}
```

Nếu gọi mỗi request, code tạo client/pools/monitoring threads rồi đóng, có thể làm tăng connection setup, TLS handshake và latency.

**Đúng:** Ứng dụng tạo một `MongoClient` sống theo service/container lifecycle, dùng chung cho các requests và đóng khi shutdown.

### 14.2. Pool được quản lý theo server

Theo MongoDB Java Sync Driver docs, mỗi `MongoClient` có connection pool cho mỗi server phù hợp topology. Driver theo dõi servers bằng monitoring connections.

Có thể cấu hình URI:

```text
mongodb://localhost:27017/?maxPoolSize=100&minPoolSize=0&maxConnecting=2
```

Các giá trị trên là **ví dụ**, không phải cấu hình tối ưu universal.

- `maxPoolSize`: số connections tối đa của mỗi pool.
- `minPoolSize`: connections tối thiểu.
- `maxConnecting`: giới hạn việc tạo connections đồng thời.
- `maxIdleTimeMS`: thời gian idle trước khi connection có thể bị bỏ.
- Các timeout khác được định nghĩa theo driver version.

Trong nhiều driver versions, `maxPoolSize` mặc định **100 mỗi server**. Hãy xác minh default của version đang dùng; không coi nó là giới hạn concurrency của toàn ứng dụng.

### 14.3. Tính tổng số connections

Giả sử:

- 4 application instances.
- 1 MongoClient mỗi instance.
- Kết nối tới 3 servers.
- `maxPoolSize=100`.

Số pooled connections **tiềm năng tối đa**:

\[
4 \times 3 \times 100 = 1200
\]

Đó là lý thuyết khi mọi pools mở tới tối đa, chưa tính monitoring sockets và những yếu tố topology. Không có nghĩa MongoDB sẽ mở ngay 1.200 connections lúc startup.

Dù dùng reactive, concurrent in-flight operations vẫn bị giới hạn bởi pool/server capacity. Async giúp giảm blocking-thread cost, **không tạo ra vô hạn database connections**.

### 14.4. Pool checkout wait

Nếu tất cả connections của server liên quan đang bận:

```text
Incoming request
    |
    +-- Pool full
    |
    +-- Wait/queue
    |
    +-- Checkout connection
    |
    +-- MongoDB operation
```

p95/p99 có thể cao dù server query execution time thấp. Cần đo:

- Connection checkout wait.
- Connections checked out/available.
- Wait queue.
- Server selection time.
- Socket/network latency.
- MongoDB execution time.
- Application end-to-end latency.

Tăng pool lên vô hạn có thể làm server quá tải hơn. Tối ưu theo measured capacity.

---

## 15. Timeouts và cancellation: khác nhưng cùng quan trọng

### 15.1. Các loại thời gian chờ

| Loại | Vai trò |
| --- | --- |
| Server selection timeout | Chờ tìm server phù hợp read preference/topology |
| Connection establishment timeout | Chờ mở TCP/TLS connection |
| Pool checkout wait | Chờ connection rảnh |
| Socket timeout | Chờ send/receive trên socket |
| Operation timeout / CSOT (khi driver hỗ trợ) | Giới hạn end-to-end operation |
| Server `maxTimeMS` | Yêu cầu server giới hạn thời gian thực thi thao tác |
| Reactive `timeout(Duration)` | Timeout ở pipeline, có thể phát cancellation |

Các giá trị default và semantics thay đổi theo driver releases; tra docs đúng version.

### 15.2. Sync query với maxTime

```java
Document result = orders
    .find(Filters.eq("tenantId", "A"))
    .maxTime(2, java.util.concurrent.TimeUnit.SECONDS)
    .first();
```

`maxTime` áp dụng giới hạn xử lý phía server theo tính năng operation. Nó không thay thế network timeout và không tự tạo business SLA trong mọi tình huống.

### 15.3. Reactive timeout

```java
Mono<Document> result = Mono.from(
    orders.find(Filters.eq("_id", "O-101")).first()
).timeout(java.time.Duration.ofSeconds(2));
```

Khi timeout, Reactor thường hủy subscription upstream; nhưng **cancellation không phải rollback transaction hay chứng nhận một write chưa đến server**. Với writes, có thể xảy ra trường hợp client timeout nhưng server vẫn đã áp dụng thay đổi. Thiết kế idempotency và kiểm chứng kết quả là bắt buộc.

### 15.4. Retry có thể gây duplicate writes

```java
Mono<UpdateResult> operation = Mono.from(
    orders.updateOne(
        Filters.eq("_id", "O-101"),
        Updates.inc("retryCounter", 1)
    )
);
```

Nếu tự thêm Reactor `retry(3)` một cách vô điều kiện, một lệnh `$inc` có thể được gửi nhiều lần trong các tình huống lỗi mơ hồ hoặc khi subscription mới được tạo. Không giả định `retry` của pipeline tương đương retryable writes của driver.

Muốn an toàn:

- Dùng operation idempotent khi có thể.
- Dùng unique/idempotency keys.
- Phân biệt transient vs permanent errors.
- Thiết kế timeout và retry budgets.
- Tránh thác retry từ HTTP proxy → app → driver → database.
- Có telemetry số retries.

---

## 16. Exception và error signals

### 16.1. Sync: exception trực tiếp

```java
try {
    Document order =
        orders.find(Filters.eq("_id", "O-101")).first();
    // Sử dụng kết quả.
} catch (com.mongodb.MongoTimeoutException e) {
    // Log theo request context, trả lỗi phù hợp.
} catch (com.mongodb.MongoException e) {
    // Xử lý database error được phân loại.
}
```

Không catch `Exception` rồi trả success mặc định. Cần phân loại lỗi timeout, auth, duplicate key, validation, write concern...

### 16.2. Reactive: onError signal

```java
Mono<Document> query = Mono.from(
    orders.find(Filters.eq("_id", "O-101")).first()
);

return query
    .doOnError(error -> logDatabaseError(error))
    .onErrorMap(error -> toApplicationException(error));
```

`logDatabaseError` và `toApplicationException` là hai hàm **minh họa** bạn tự định nghĩa. Mục tiêu: lỗi đi theo cùng pipeline để framework map HTTP response, tracing và metrics.

Không viết:

```java
query.subscribe(
    doc -> process(doc),
    error -> System.out.println("ignored")
);
return Mono.just("OK");
```

trong handler vì nó **tách side effect ra khỏi request lifecycle**, mất propagation và rất dễ báo thành công giả.

### 16.3. Không dùng onErrorResume nuốt mọi lỗi

```java
// CẦN CẨN THẬN: fallback rỗng có thể che database outage.
Mono<Document> result = query.onErrorResume(
    error -> Mono.empty()
);
```

Nếu trả kết quả không tìm thấy trong khi thực tế DB timeout, hệ thống có thể gây quyết định nghiệp vụ sai. Chỉ fallback khi business semantics cho phép và có metric/log.

---

## 17. Reactive context và ThreadLocal

Trong imperative Spring MVC, một số thư viện dựa trên `ThreadLocal` để giữ:

- Request ID.
- Security context.
- Transaction state.
- MDC logging.
- Locale.

Trong reactive pipeline, execution có thể chuyển qua nhiều threads. Không giả định `ThreadLocal` luôn truyền chính xác tới mọi operator.

### 17.1. Reactor Context

Reactor hỗ trợ **Context** gắn với subscription, không phải thread cụ thể:

```java
Mono<String> message = Mono.deferContextual(ctx -> {
    String requestId =
        ctx.getOrDefault("requestId", "unknown");
    return Mono.just("request=" + requestId);
});

Mono<String> requestScoped = message.contextWrite(
    ctx -> ctx.put("requestId", "req-123")
);
```

Dữ liệu được lấy trong reactive chain khi subscription xảy ra. Trong Spring, nên dùng các cơ chế security/tracing context propagation chính thức thay vì tự trộn MDC/ThreadLocal không kiểm soát.

### 17.2. Tác động tới transactions

Imperative transactions thường gắn context với thread; reactive transactions gắn với Reactor subscriber context/session lifecycle qua framework. Không gọi `@Transactional` imperative trên reactive repository rồi mong nó tự thành reactive transaction.

---

## 18. Transactions: tính năng chung, cách tổ chức khác nhau

MongoDB hỗ trợ multi-document transactions trên các deployment phù hợp. Cả Sync và Reactive Streams drivers có API session/transaction, nhưng cách quản lý lifecycle khác nhau.

### 18.1. Sync transaction

Ví dụ tư duy với hai collections thuộc cùng `MongoClient`:

```java
import com.mongodb.client.ClientSession;
import org.bson.Document;

try (ClientSession session = client.startSession()) {
    session.startTransaction();

    try {
        orders.insertOne(
            session,
            new Document("_id", "O-TX-1")
                .append("status", "NEW")
        );

        audit.insertOne(
            session,
            new Document("event", "ORDER_CREATED")
                .append("orderId", "O-TX-1")
        );

        session.commitTransaction();
    } catch (RuntimeException error) {
        session.abortTransaction();
        throw error;
    }
}
```

`client`, `orders` và `audit` là những biến **đã được khởi tạo trước**, và code giả định server topology hỗ trợ transactions.

Đây là ví dụ đơn giản để hiểu session; production cần xử lý retryable transaction errors, `UnknownTransactionCommitResult`, commit/abort edge cases và timeout đúng theo driver API.

### 18.2. Reactive transaction cần composition đúng session

Trong Reactive Streams Driver:

- `startSession()` trả Publisher của `ClientSession`.
- Các thao tác trong transaction phải dùng **đúng session** và đúng `MongoClient`.
- `startTransaction` là thao tác quản lý state của session; `commitTransaction`/`abortTransaction` tham gia asynchronous flow.
- Không mở session một nơi, `subscribe()` lẻ từng lệnh ở nơi khác rồi mong transaction được bảo toàn.
- Không chạy những thao tác song song trên cùng session/transaction nếu API không hỗ trợ; MongoDB transaction operations cần thứ tự đúng.

Tư duy pipeline:

```text
subscribe
   |
startSession publisher
   |
startTransaction
   |
write A with session
   |
write B with same session
   |
commitTransaction publisher
   |
close session
   |
complete / error
```

Trong Spring Data Reactive, có thể ưu tiên `ReactiveMongoTransactionManager` và cơ chế `TransactionalOperator` / reactive transaction management được Spring hỗ trợ. Đừng tự viết một pipeline transaction phức tạp khi framework đã có abstraction đúng.

### 18.3. Chọn driver chỉ vì transactions?

Không. Cả hai hỗ trợ transactions theo điều kiện MongoDB Server/version. Điều quyết định là **transaction boundaries của ứng dụng** và cách error/retry/context được triển khai.

---

## 19. Streaming kết quả lớn và Change Streams

### 19.1. Sync cursor

```java
try (MongoCursor<Document> cursor =
         orders.find().batchSize(100).iterator()) {
    while (cursor.hasNext()) {
        Document doc = cursor.next();
        processDocument(doc); // Hàm blocking/imperative.
    }
}
```

Nếu `processDocument` chậm, thread hiện tại chờ. Cần kiểm soát cursor lifetime, batchSize, timeouts và memory.

### 19.2. Reactive cursor

```java
Flux<Document> stream = Flux.from(
    orders.find().batchSize(100)
);

Flux<String> transformed = stream.map(
    doc -> doc.getString("status")
);
```

Bên downstream kiểm soát subscription và demand theo Reactor semantics. Đây không có nghĩa toàn bộ kết quả đã nằm trong RAM.

### 19.3. Change Streams

Sự kiện thay đổi có thể phục vụ audit, event propagation, SSE và near-real-time processing.

Sync (ý tưởng):

```java
try (var cursor = collection.watch().iterator()) {
    while (cursor.hasNext()) {
        var event = cursor.next();
        // Xử lý event.
    }
}
```

Reactive:

```java
Flux<?> changes = Flux.from(collection.watch());
```

`collection` trong hai đoạn trên là collection của driver tương ứng; chúng không được import chồng trong cùng một class.

**Điểm quan trọng cho Change Streams:**

- Resume token để phục hồi sau gián đoạn.
- Oplog/change stream retention window.
- Consumer checkpoint và duplicate processing.
- Retry/backoff theo error type.
- Không subscribe vô hạn mà không có shutdown/cancellation.
- Reactive backpressure không tự tạo durable queue.

### 19.4. SSE/WebSocket: Reactive đáng cân nhắc

Một endpoint mở stream liên tục cho nhiều clients là trường hợp Reactive + WebFlux phù hợp, vì subscriptions có thể hủy khi client disconnect và không buộc giữ một platform thread cho từng socket chờ I/O.

Tuy nhiên vẫn phải có fan-out, buffering, slow-consumer và reconnect policy; không biến Change Stream thành pub/sub system hoàn chỉnh chỉ nhờ `Flux`.

---

## 20. Chọn driver cho từng kiểu ứng dụng

| Ứng dụng | Driver mặc định đáng cân nhắc | Lý do |
| --- | --- | --- |
| Spring MVC CRUD service | Sync | Đồng bộ với servlet/request lifecycle |
| REST API Java thuần, đơn giản | Sync | Ít abstraction, dễ debug |
| Spring WebFlux với WebClient/Reactor | Reactive Streams | Non-blocking end-to-end |
| SSE hoặc WebSocket streaming | Reactive Streams | Publisher, cancellation, backpressure |
| Batch ETL một luồng hoặc ít threads | Sync | Dễ control ordering/errors |
| Batch ETL fan-out async, downstream non-blocking | Reactive Streams | Composition và bounded concurrency |
| Kafka consumer xử lý tuần tự | Sync hoặc Reactive | Phụ thuộc consumer model/backpressure |
| Java 21 virtual-thread REST | Sync | Imperative code với concurrency chi phí thấp hơn |
| Quarkus/Micronaut non-blocking app | Theo extension/framework | Giữ nhất quán integration |
| Ứng dụng legacy dùng JDBC/HTTP blocking | Sync | Reactive DB đơn lẻ ít lợi ích |
| Event processing pipeline nhiều stream | Reactive Streams | Phù hợp operator/composition |
| CLI tooling/migration script | Sync | Đơn giản, vòng đời hữu hạn |
| Transaction workflow phức tạp imperative | Sync | Session/exception flow dễ theo dõi |
| Microservice đang dùng Spring Data Reactive | Reactive Streams | Không block trên event loop |

**Quy tắc tổng quát:** Nếu bạn phải chặn `block()` ở hầu hết các chỗ mới dùng được reactive driver, có khả năng **Sync Driver phù hợp hơn** hoặc kiến trúc cần được thiết kế lại thực sự.

---

## 21. Decision tree đơn giản

```text
Ứng dụng hiện là reactive/non-blocking end-to-end?
    |
    +-- Có ----> Các dependency chính có non-blocking?
    |                |
    |                +-- Có -> Ưu tiên Reactive Streams Driver
    |                |
    |                +-- Không -> Cân nhắc refactor hoặc bridge
    |                           bằng boundedElastic có giới hạn;
    |                           benchmark trước.
    |
    +-- Không --> Có yêu cầu streaming dài hạn / nhiều
                  I/O pipelines non-blocking rõ ràng?
                    |
                    +-- Có -> Cân nhắc thiết kế reactive
                    |         toàn pipeline, không chỉ DB.
                    |
                    +-- Không -> Ưu tiên Sync Driver,
                                 đặc biệt Spring MVC/CLI.
                                 Java 21 virtual threads
                                 là lựa chọn đáng benchmark.
```

Quyết định cuối còn phụ thuộc SLO, throughput, skill của đội và operational risk.

---

## 22. Performance: vì sao reactive không bảo đảm latency thấp hơn?

Một MongoDB query mất 30ms trên server không trở thành 10ms chỉ vì driver non-blocking. Phần query execution trên database vẫn phụ thuộc:

- Index và query planner.
- Data size/cardinality.
- Read concern/read preference.
- Write concern/transactions.
- CPU, disk, network và caching.
- Connection pools/queues.
- Batch sizes, number of documents, serialization.

Reactive có thể giúp **sử dụng threads hiệu quả hơn khi có nhiều request I/O chờ**, từ đó cải thiện throughput hoặc tail latency tại một mức concurrency cụ thể. Nhưng nó cũng có thể chậm hơn nếu pipeline tạo quá nhiều work, buffering lớn hoặc switching schedulers thiếu kiểm soát.

### 22.1. Mô hình đơn giản bằng Little's Law

Ở trạng thái ổn định:

\[
L = \lambda W
\]

Trong đó:

- \(L\): số requests trung bình đang trong hệ thống.
- \(\lambda\): throughput (requests/s).
- \(W\): average response time (s).

Nếu 200 requests/s, trung bình 100ms:

\[
L = 200 \times 0.1 = 20
\]

Khoảng 20 requests in flight trung bình. Nhưng đây **không phải cam kết** chỉ cần 20 connections, 20 threads hay 20 subscribers: thực tế còn spikes, parallel queries, retries và tail latency.

### 22.2. Giới hạn connection pool là trục độc lập

Giả sử:

- 500 concurrent HTTP requests.
- MongoDB max pool size = 100 ở node thực thi.
- Mỗi request cần một DB operation tại một thời điểm.

Dù app dùng 500 platform threads, 500 virtual threads hay 500 reactive subscriptions, vẫn có thể có operations **đợi connection**. Không có mô hình concurrency nào cho phép bỏ qua server capacity.

### 22.3. CPU-heavy không được lợi từ reactive I/O

Nếu mỗi document phải giải nén, mã hóa hoặc tính hash CPU-heavy, đặt việc đó trực tiếp trên Netty event loop có thể gây nghẽn. Cần CPU executor/scheduler phù hợp, giới hạn concurrency và đo performance. Reactive thích hợp cho I/O orchestration, không phải cách tự động tăng tốc CPU computation.

---

## 23. Benchmark hai driver một cách công bằng

Không nên benchmark:

- Sync driver chạy với cache cold trong khi reactive cache warm.
- Sync query trả 50 documents, Reactive chỉ trả 1.
- Sync đọc từ primary, Reactive từ secondary.
- Sync dùng index còn Reactive thiếu index.
- Reactive benchmark chỉ đo thời gian tạo Publisher **không subscribe**.
- Reactive `subscribe()` rồi lập tức dừng đồng hồ trước khi có `onComplete`.
- Sync dùng một client mới cho mỗi query, reactive tái sử dụng client singleton.
- Error/timeout requests bị bỏ khỏi latency report.

### 23.1. Khối lượng thí nghiệm

Dùng cùng:

- MongoDB deployment/server version.
- Dataset/corpus và index definitions.
- Query filters, sort, projection, batch size.
- Read preference, read/write concern.
- Network latency/region.
- MongoDB credentials/TLS.
- `maxPoolSize`/connection settings tương ứng.
- JVM version, heap, GC, runtime container resources.
- Warmup và query mix.
- Concurrency levels.

So ứng dụng ở mức **thực sự làm việc xong**, không chỉ thời điểm gọi API.

### 23.2. Đo những gì?

| Metric | Tại sao? |
| --- | --- |
| Throughput đạt được (RPS/QPS) | Năng lực xử lý thực |
| p50/p95/p99 end-to-end | Trải nghiệm người dùng |
| Database command latency | Tách phần DB |
| Driver pool checkout wait | Tìm bottleneck connections |
| JVM threads/platform threads | Lợi ích concurrency |
| CPU utilization | Efficiency |
| Heap/RSS/GC pauses | Memory pressure |
| Database CPU/IOPS/ops/s | Tải đẩy xuống MongoDB |
| Error/timeout/retry rates | Không bỏ qua thất bại |
| P99 tại concurrency cao | Tail behavior |
| Streaming memory per request | Buffer/backpressure |
| Cancellation propagation | Bỏ việc không còn cần |

### 23.3. Concurrency sweep

Ví dụ:

```text
1, 10, 50, 100, 200, 500 concurrent requests
```

Ở mỗi mức, ghi throughput thực, latency distribution, errors, pool waits, CPU/memory và database utilization.

Khi throughput bão hòa mà p99 tăng vọt, tiếp tục tăng subscribers/threads thường chỉ tạo queue lớn hơn. Giới hạn ingress concurrency/load shedding có thể giúp ổn định tail latency.

### 23.4. Kiểm tra độ công bằng của dữ liệu

Khi benchmark query theo `tenantId`, nên có tenant nhỏ/lớn và filter chọn lọc khác nhau. Cache, shard targeting và index cardinality quyết định nhiều hơn cú pháp driver.

---

## 24. Observability và tracing cho cả Sync lẫn Reactive

Một hệ thống tốt phải trả lời:

- Request nào tạo query?
- Query nào chậm?
- Thời gian chờ connection là bao nhiêu?
- Thời gian server thực thi là bao nhiêu?
- Có retries/timeouts không?
- Reactive pipeline có fan-out quá lớn không?
- Event-loop bị blocking hay scheduler queue quá dài?

### 24.1. Command monitoring

MongoDB Java drivers có **CommandListener** cho command started/succeeded/failed events. Có thể ghi metrics:

- Command type, namespace/collection.
- Duration.
- Error category.
- Request/trace correlation.
- Server address.

**Không log toàn bộ command documents** vì có thể chứa PII, filters nhạy cảm hoặc credentials. Nên redact literals và chỉ thu metadata cần thiết.

### 24.2. Pool monitoring

Connection pool events giúp nhìn:

- Connections created/closed.
- Checkout started/succeeded/failed.
- Pool cleared.
- Pool size và wait behavior.

Không mặc định “async code chạy chậm vì MongoDB Server”; có thể nằm trong driver pool.

### 24.3. Reactive tracing

Reactive pipeline có thể chuyển threads, nên context propagation phải được tích hợp đúng với OpenTelemetry/Spring Reactor. Thread name không phải request ID đáng tin. Dùng trace/span IDs trong context chính thức thay vì dựa hoàn toàn trên `ThreadLocal`.

### 24.4. Bảo mật

- TLS và xác minh certificates.
- Least privilege cho application database users.
- Không hardcode connection URI có password.
- Không để profiler/command logs chứa PII.
- Không in nguyên Document từ production vào logs không kiểm soát.

---

## 25. Migration từ Sync sang Reactive và ngược lại

Đổi driver **không chỉ là thay import**.

### 25.1. Các bước chuyển Sync → Reactive

1. Xác định mục tiêu: giảm platform threads, giữ WebFlux non-blocking, streaming hay xử lý concurrency?
2. Đo baseline throughput, p95/p99, CPU/heap/pool trước migration.
3. Xác định call graph của service/repository: phần nào còn blocking?
4. Thay dependencies theo BOM/framework.
5. Đổi API trả trực tiếp thành `Mono`/`Flux`/`Publisher`.
6. Thay control flow, error propagation và timeout semantics.
7. Chuyển transaction boundaries sang reactive session/manager.
8. Quản lý Reactor Context/security/tracing.
9. Không gọi `subscribe()` trong tầng service ngoài trường hợp có lý do/chủ sở hữu lifecycle rõ.
10. Không lạm dụng `block()`; các bridge phải giới hạn và có metric.
11. Kiểm thử idempotency/retries/cancellation.
12. Load test cùng corpus và traffic.
13. Canary rollout và có rollback plan.

### 25.2. Chuyển Reactive → Sync

Có thể hợp lý khi:

- Project chuyển WebFlux sang Spring MVC/virtual threads.
- Các dependencies chính là blocking.
- Đội ngũ gặp nhiều sự cố context/subscription/cancellation.
- Benchmark cho thấy reactive không mang lại lợi ích cần thiết.
- Mục tiêu đơn giản hóa maintenance.

**Không tự chặn một Publisher vô hạn** (ví dụ Change Streams `collectList().block()`) vì nó có thể không bao giờ hoàn tất và tích lũy vô hạn trong RAM.

### 25.3. Có thể dùng cả hai trong một ứng dụng không?

Có thể, ví dụ một ứng dụng có batch module imperative và một realtime module reactive. Nhưng cần kiểm soát:

- Hai `MongoClient` riêng biệt và **hai connection pools** nếu tạo cả hai.
- Config TLS/auth/read preference/timeout đồng bộ.
- Memory và thread resource tổng.
- Transaction/session không thể tùy tiện dùng chung giữa hai client APIs.
- Logging/metrics theo driver.
- Không phát sinh dependency conflict do versions lệch.

Trước khi chọn hỗn hợp, hãy tính complexity và operational cost; nhiều khi tách services/modules rõ ràng tốt hơn.

---

## 26. Những lỗi phổ biến và cách sửa

| Lỗi | Tại sao xảy ra | Cách xử lý |
| --- | --- | --- |
| Tạo Reactive Publisher nhưng không có kết quả | Không subscribe | Trả pipeline về framework hoặc subscribe ở boundary đúng |
| Gọi `subscribe()` trong service, trả success ngay | Side effect ngoài request lifecycle | Compose bằng `map`/`flatMap` |
| Gọi `block()` trên WebFlux event loop | Chặn event loop | Trả `Mono`/`Flux`; bridge boundedElastic chỉ khi cần |
| Sync MongoDB call trực tiếp trong `Mono.just(...)` | Eager blocking trước subscription | `Mono.fromCallable(...).subscribeOn(boundedElastic())` |
| Reactive `collectList()` trên toàn collection | Materialization lớn | Limit/pagination/stream bounded |
| `flatMap` concurrency không giới hạn | Quá nhiều operations | Giới hạn concurrency và queues |
| Cứ dùng reactive là nhanh hơn | Server/pool/query mới là bottleneck | Benchmark p95/p99 |
| Tạo MongoClient mỗi request | Connection churn | Singleton client lifecycle |
| Tăng maxPoolSize không giới hạn | Server saturation | Đo checkout waits/server capacity |
| Catch hoặc onErrorResume mọi lỗi | Che outages và consistency errors | Phân loại error, log/metrics |
| Retry toàn bộ write pipeline | Có thể duplicate side effects | Idempotency/retry policy |
| Dùng ThreadLocal như reactive context | Thread switching | Reactor Context và tracing integration |
| Transaction operations subscribe riêng | Mất sequencing/session lifetime | Compose trong một reactive transaction |
| Không close cursor/client | Resource leaks | Lifecycle và cleanup đúng |
| Dùng virtual threads mà không đo pool | Pool vẫn giới hạn | Benchmark resource usage |
| Benchmark chỉ đo tạo Publisher | Chưa có network I/O | Đo sau terminal signal |
| Nhầm `com.mongodb.client` với reactive package | Type/import mismatch | Tách imports/module |
| Copy version `5.x.y` vào build | Không resolve được dependency | Dùng version thực/BOM được duyệt |
| Dùng reactive MongoDB nhưng JDBC blocking trong event loop | Vẫn nghẽn event loop | Non-blocking alternative hoặc offload |
| Không có timeout | Requests có thể treo lâu | Timeout budgets phù hợp |
| Subscriber bị hủy nhưng tưởng write rollback | Cancellation không đồng nghĩa rollback | Đảm bảo write idempotency/verification |

---

## 27. Decision scorecard

Giả sử hai phương án:

- **S:** Spring MVC + Java Sync Driver (có thể dùng virtual threads).
- **R:** Spring WebFlux + Java Reactive Streams Driver + Reactor.

Đặt các tiêu chí bắt buộc:

1. Có đáp ứng được concurrency ở peak traffic?
2. p95/p99 end-to-end có dưới SLO?
3. Đội ngũ có vận hành/debug được?
4. Tất cả dependencies trên critical path có phù hợp execution model?
5. Connection pool/DB throughput có đáp ứng?
6. Transactions, authorization và observability có đúng?
7. Migration cost/rollback có chấp nhận được?

Bảng điểm **minh họa**, không phải benchmark MongoDB:

| Tiêu chí | S | R |
| --- | --- | --- |
| Spring MVC và JDBC blocking sẵn có | Rất phù hợp | Cần offload/đổi kiến trúc |
| WebFlux + WebClient đang dùng | Cần bridge | Rất phù hợp |
| Codebase imperative lớn | Chi phí chuyển thấp | Migration lớn |
| SSE/stream liên tục | Cần thread/cursor planning | Dễ compose stream |
| Nhiều I/O không blocking | Virtual threads đáng thử | Mô hình tự nhiên |
| Transactions imperative | Rõ ràng | Cần reactive session/context |
| Số request rất lớn | Benchmark platform/virtual thread | Benchmark Reactor/DB pool |
| Team chưa có kinh nghiệm Reactor | Dễ triển khai | Tăng rủi ro lỗi |
| Chỉ một truy vấn MongoDB nhanh/chậm | Không phân định | Không phân định |

**Không quyết định bằng điểm tổng tùy ý nếu còn vi phạm yêu cầu bắt buộc** như bảo mật, transaction correctness hoặc SLO.

---

## 28. Bài tập thực hành

### Bài 1 — Chọn driver cơ bản

Một ứng dụng Spring MVC CRUD với thư viện JDBC blocking và lưu lượng vừa phải. Nên bắt đầu với driver nào?

**Đáp án định hướng:** Sync Driver, vì khớp execution model và đơn giản hơn.

### Bài 2 — WebFlux end-to-end

Một ứng dụng Spring WebFlux dùng WebClient và SSE. Nếu dùng Sync Driver trong event-loop có nguy cơ gì?

**Đáp án:** Chặn event-loop khi chờ MongoDB, ảnh hưởng nhiều requests khác.

### Bài 3 — Namespace

Phân biệt `com.mongodb.client.MongoClient` và `com.mongodb.reactivestreams.client.MongoClient`.

### Bài 4 — Cold Publisher

Đoạn mã:

```java
Publisher<Document> p =
    collection.find(Filters.eq("_id", "O-101")).first();
```

đã chắc chắn gửi DB command chưa?

**Đáp án:** Chưa; reactive driver publisher cold, cần subscription.

### Bài 5 — Hai subscriptions

Subscribe cùng một Publisher hai lần có thể tạo bao nhiêu DB operations?

**Đáp án:** Hai operations độc lập nếu không có layer caching/sharing.

### Bài 6 — Mono rỗng

Sync `first()` không có bản ghi có thể trả `null`. Reactive `Mono.from(first())` sẽ làm gì?

**Đáp án:** Hoàn tất rỗng; không phát `null`.

### Bài 7 — map và flatMap

Trong Reactor, khi hàm phụ trả `Mono<String>`, nên dùng `map` hay `flatMap` để tránh `Mono<Mono<String>>`?

**Đáp án:** `flatMap`.

### Bài 8 — WebFlux block

Vì sao `Mono.from(publisher).block()` trong handler event-loop là lỗi? Cách sửa?

**Đáp án:** Blocking event loop. Trả `Mono` cho framework; nếu buộc dùng blocking library thì offload có giới hạn.

### Bài 9 — fromCallable bridge

Viết bridge để gọi Sync Driver trong WebFlux qua `Mono.fromCallable` và `Schedulers.boundedElastic()`. Nó có làm I/O trở thành native non-blocking không?

**Đáp án:** Không, chỉ chuyển blocking sang bounded worker threads.

### Bài 10 — Backpressure

Producer có thể trả 1.000 items/s còn consumer 20 items/s. Làm thế nào giới hạn concurrency và không giữ tất cả items trong RAM?

### Bài 11 — collectList

Vì sao `Flux.from(collection.find()).collectList()` nguy hiểm nếu collection có hàng chục triệu documents?

### Bài 12 — Connection pools

Với 4 app instances, 3 servers và maxPoolSize 100/server, số pooled connections lý thuyết tối đa là bao nhiêu?

**Đáp án:** 1.200, chưa kể monitoring/connection overhead.

### Bài 13 — Singleton client

Tại sao không tạo và đóng `MongoClient` ở mỗi HTTP request?

### Bài 14 — Virtual threads

Vì sao Java 21 virtual threads làm Sync Driver đáng cân nhắc ở hệ thống high concurrency? Giới hạn nào không thay đổi?

**Đáp án:** Giảm platform-thread overhead cho blocking tasks, nhưng DB pool/server vẫn có giới hạn.

### Bài 15 — Query plan

Nếu cùng một MongoDB query `COLLSCAN` trên hai drivers, đổi Sync thành Reactive có chắc giảm latency không?

**Đáp án:** Không, cần tối ưu query/index.

### Bài 16 — Retry

Vì sao thêm Reactor `retry(3)` cho `updateOne($inc)` có thể gây vấn đề nghiệp vụ?

### Bài 17 — Timeouts

Phân biệt server selection timeout, pool checkout wait, socket timeout, `maxTimeMS` và Reactor `timeout`.

### Bài 18 — Cancellation

Client HTTP hủy reactive subscription ngay sau khi gửi MongoDB write. Có thể khẳng định write đã rollback không?

**Đáp án:** Không. Cần idempotency, verify và transaction semantics.

### Bài 19 — Transactions

Vì sao reactive transaction cần giữ cùng ClientSession và sequencing? Có nên tự `subscribe()` từng lệnh write không?

### Bài 20 — Reactive context

Vì sao `ThreadLocal` thuần có thể làm mất requestId trong reactive chain? Reactor Context giải quyết gì?

### Bài 21 — Change Streams

Một service stream MongoDB changes đến SSE clients. Nên cân nhắc driver nào và cần bổ sung gì ngoài backpressure?

**Gợi ý:** Reactive cho streaming, nhưng cần resume token, retention, slow-consumer policy và checkpoint.

### Bài 22 — Benchmark

Lập bảng so sánh Sync với Reactive có cùng dataset, index, read preference, maxPoolSize, concurrency, TLS, JVM và warmup. Ghi ít nhất bảy metrics.

### Bài 23 — Sai benchmark

Một benchmark Reactive chỉ đo thời gian gọi `collection.find(...)` rồi kết luận nó nhanh hơn Sync `first()`. Sai ở đâu?

**Đáp án:** Chưa subscribe/nhận terminal signal, nên chưa đo MongoDB operation.

### Bài 24 — Spring Data

Phân biệt `MongoTemplate` và `ReactiveMongoTemplate`, `MongoRepository` và `ReactiveMongoRepository`.

### Bài 25 — Hỗn hợp driver

Một service dùng cả Sync và Reactive. Những vấn đề resource/config cần theo dõi?

**Gợi ý:** Hai clients/pools, timeout/TLS/auth, phiên bản dependency, transaction ownership, monitoring và memory.

### Bài 26 — Dịch vụ chỉ có 1 DB query

Một API phần lớn thời gian chờ MongoDB nhưng concurrency thấp và latency 15ms. Có cần rewrite sang Reactor không?

**Đáp án định hướng:** Chưa có đủ bằng chứng; đo concurrency/SLO/maintenance cost trước.

### Bài 27 — Đầu ra reactive đúng

Viết một phương thức service trả `Mono<String>` kết nối từ `find().first()` và xử lý not found không dùng `block()`.

### Bài 28 — Lỗi onErrorResume

Một đoạn code chuyển mọi MongoDB errors thành `Mono.empty()`. Hậu quả với HTTP 404/200 và incident monitoring là gì?

### Bài 29 — Chi phí ownership

Team có 5 Java developers chưa quen Reactor, ứng dụng Spring MVC và nhiều dependencies blocking. Liệt kê chi phí học, migration, testing và debugging khi chuyển driver.

### Bài 30 — Ra quyết định

Cho ba sản phẩm:

1. CLI migration chạy theo lô.
2. Spring WebFlux API tích hợp nhiều downstream reactive.
3. Spring MVC trên Java 21 virtual threads.

Chọn driver mặc định hợp lý cho từng ứng dụng và giải thích bằng SLO, execution model và resource limits.

---

## 29. Checklist production

### Kiến trúc

- [ ] Driver khớp với Spring MVC/WebFlux/virtual-thread execution model.
- [ ] Không có blocking calls bất ngờ trên event-loop.
- [ ] Không subscribe thủ công trong service ngoài ownership rõ.
- [ ] Session/transaction lifecycle được quản lý nhất quán.
- [ ] Reactive context/security/tracing propagation được kiểm soát.
- [ ] Streaming pipelines có cancellation và backpressure policy.

### Connection và dữ liệu

- [ ] Dùng singleton MongoClient phù hợp application lifecycle.
- [ ] Pool size, maxConnecting và timeouts đã được benchmark.
- [ ] URI/TLS/auth được quản lý bằng secrets.
- [ ] Query filters, sort, projection và indexes phù hợp workload.
- [ ] Batch sizes và pagination không materialize dataset vô hạn.
- [ ] Retries có idempotency strategy, không nuốt errors.

### Monitoring

- [ ] Có p50/p95/p99 API latency, RPS, error rate.
- [ ] Có MongoDB command durations và pool checkout waits.
- [ ] Có JVM CPU, heap, GC, thread count, scheduler queue.
- [ ] Có Atlas/server CPU/disk, query targeting và replica lag.
- [ ] Tracing gắn requestId qua async boundaries.
- [ ] Log redaction ngăn lộ query literals/credentials.

### Delivery

- [ ] Driver/JDK/MongoDB Server/Spring Data versions được pin và tương thích.
- [ ] Có integration tests cho success, not-found, duplicate, timeout, cancellation.
- [ ] Có load tests đủ concurrency và data thực tế.
- [ ] Có rollback plan khi đổi driver/architecture.
- [ ] Đo tác động write latency, pool/DB CPU và application memory.
- [ ] Team có runbook điều tra reactive deadlocks/event-loop blocking.

---

## 30. Tổng kết

**MongoDB Java Sync Driver** và **Reactive Streams Driver** đều là công cụ hợp lệ để truy cập MongoDB; khác biệt nằm ở mô hình lập trình và concurrency:

1. **Sync** trả kết quả trực tiếp qua API blocking và phù hợp Spring MVC, CLI/batch, code imperative, integrations blocking; cũng đáng cân nhắc khi dùng Java 21 virtual threads.
2. **Reactive** trả cold `Publisher`, chạy khi subscribe; phù hợp Reactor/WebFlux, streaming và các pipeline I/O non-blocking.
3. **Non-blocking không tự có nghĩa nhanh hơn**. Query plan, indexes, connection pool, MongoDB Server và network vẫn quyết định nhiều phần latency.
4. **Reactive cần hiểu demand, cancellation và error signals**. Không gọi `block()` trên event-loop, không subscribe side effects ngoài request lifecycle.
5. **Cả hai cần MongoClient dùng lại, connection pooling, TLS, timeouts, transactions đúng và monitoring**.
6. **Benchmark công bằng** phải đo completion/end-to-end p95/p99, throughput, errors, CPU, memory và pool waits, không đo riêng thời điểm tạo Publisher.
7. **Chọn execution model nhất quán trên toàn request path** quan trọng hơn chọn API có vẻ hiện đại.

Một lựa chọn driver tốt là lựa chọn **đáp ứng SLO, giữ dữ liệu đúng, dễ vận hành và có chi phí bảo trì chấp nhận được** trong hệ thống của bạn.

### Tài liệu chính thức và tham khảo

- [MongoDB Java Sync Driver — Overview](https://www.mongodb.com/docs/drivers/java/sync/current/) — API đồng bộ, support và compatibility.
- [MongoDB Java Sync Driver — Get Started](https://www.mongodb.com/docs/drivers/java/sync/current/get-started/) — BOM, dependencies, MongoClient và query.
- [MongoDB Java Sync Driver — CRUD](https://www.mongodb.com/docs/drivers/java/sync/current/crud/) — reads, writes và BSON mapping.
- [MongoDB Java Sync Driver — Connection Pools](https://www.mongodb.com/docs/drivers/java/sync/current/connection/specify-connection-options/connection-pools/) — maxPoolSize, connections, pool settings.
- [MongoDB Java Sync Driver — Limit Server Execution Time](https://www.mongodb.com/docs/drivers/java/sync/current/connection/specify-connection-options/csot/) — timeouts và CSOT.
- [MongoDB Reactive Streams Driver — Overview](https://www.mongodb.com/docs/languages/java/reactive-streams-driver/current/) — API bất đồng bộ.
- [MongoDB Reactive Streams Driver — Download and Install](https://www.mongodb.com/docs/languages/java/reactive-streams-driver/current/get-started/download-and-install/) — BOM, reactive artifact và Reactor.
- [Reactive Streams Driver — Sample Subscriber Implementations](https://www.mongodb.com/docs/languages/java/reactive-streams-driver/current/custom-implementations/) — cold publishers, demand, subscription.
- [Reactive Streams Driver — Query Documents](https://www.mongodb.com/docs/languages/java/reactive-streams-driver/current/read/) — find, query và result publishers.
- [Reactive Streams Driver — Transactions](https://www.mongodb.com/docs/languages/java/reactive-streams-driver/current/crud/transactions/) — sessions và transaction management.
- [MongoDB — Connection Pool Tuning](https://www.mongodb.com/docs/manual/tutorial/connection-pool-performance-tuning/) — pool checkout và concurrency.
- [MongoDB — Explain](https://www.mongodb.com/docs/manual/reference/explain-results/) — performance và query plan.
- [Spring Data MongoDB — Reference](https://docs.spring.io/spring-data/mongodb/reference/) — imperative/reactive templates, repositories và transactions.
- [Project Reactor — Reference](https://projectreactor.io/docs/core/release/reference/) — Mono, Flux, schedulers, backpressure và Context.
- [Reactive Streams Specification](https://www.reactive-streams.org/) — Publisher/Subscriber/Subscription protocol.
- [Java Virtual Threads — OpenJDK JEP 444](https://openjdk.org/jeps/444) — Java 21 virtual threads.
