# ReactiveMongoTemplate.changeStream và tiêu thụ bằng Flux

> **Module:** `SPRING_DATA_MONGODB` — Sử dụng Spring Data MongoDB để kết nối, ánh xạ document và thao tác MongoDB qua `MongoTemplate` hoặc repository. Thực hành thiết kế truy vấn, aggregation, index, transaction, reactive access, kiểm thử và chẩn đoán hiệu năng dữ liệu.
>
> **Chương:** Change stream.
>
> **Trọng tâm:** dùng `ReactiveMongoTemplate.changeStream(...)` nhận sự kiện thay đổi MongoDB dưới dạng `Flux<ChangeStreamEvent<T>>`, xử lý chúng bằng Reactor đúng cách và giữ khả năng tiếp tục khi dịch vụ khởi động lại.

## 1. Vấn đề cần giải quyết

Giả sử hệ thống bán hàng có collection `orders`. Khi đơn chuyển sang `PAID`, một thành phần khác cần cập nhật màn hình quản trị, tính toán báo cáo hoặc đẩy dữ liệu sang chỉ mục tìm kiếm. Cách đơn giản là liên tục truy vấn:

```text
SELECT orders WHERE updatedAt > lastCheckedAt
```

Nhưng polling đặt ra các vấn đề: độ trễ phụ thuộc chu kỳ quét, truy vấn lặp khi không có dữ liệu mới, dễ bỏ sót nếu trường thời gian không đáng tin cậy, và xử lý phức tạp khi bản ghi bị xóa.

**MongoDB Change Streams** cho phép theo dõi các thay đổi mà MongoDB công bố trên collection, database hoặc deployment được hỗ trợ. Với Spring Data MongoDB reactive, `ReactiveMongoTemplate` trả về một **`Flux` liên tục** thay vì một danh sách kết quả hữu hạn.

Ví dụ luồng xử lý:

```text
Ứng dụng ghi đơn hàng
        │
        ▼
MongoDB replica set / sharded cluster
        │  (đã ghi vào luồng thay đổi)
        ▼
ReactiveMongoTemplate.changeStream(...)
        │
        ▼
Flux<ChangeStreamEvent<Order>>
        │
        ├── lọc loại sự kiện
        ├── giải mã payload
        ├── xử lý tuần tự hoặc có giới hạn đồng thời
        └── lưu resume token sau khi xử lý thành công
                        │
                        ▼
            projection / thông báo / dịch vụ khác
```

Change stream là một nguồn thông báo thay đổi hữu ích; nó không tự cung cấp hàng đợi công việc có consumer group, checkpoint nghiệp vụ hay giao dịch phân tán cho những tác vụ ở bên ngoài MongoDB.

### Mục tiêu học tập

Sau bài học, người đọc có thể:

1. Nhận biết điều kiện triển khai Change Streams và quyền truy cập cần thiết.
2. Mở `Flux<ChangeStreamEvent<T>>` qua `ReactiveMongoTemplate.changeStream`.
3. Phân biệt việc **khai báo pipeline** với **subscribe** thực sự, hiểu vòng đời và cách hủy luồng.
4. Xử lý `INSERT`, `UPDATE`, `REPLACE` và `DELETE`, kể cả khi `getBody()` là `null`.
5. Kết hợp các toán tử Reactor như `filter`, `concatMap`, `flatMap`, `doOnError` và `retryWhen` mà không làm mất dữ liệu do xử lý bất đồng bộ.
6. Thiết kế checkpoint dựa trên **resume token**, nêu rõ giới hạn của cơ chế xử lý lặp và phục hồi.
7. Xây dựng kiểm thử tích hợp với MongoDB thật có replica set và quan sát vấn đề hiệu năng.

## 2. Điều kiện trước khi dùng Change Streams

### 2.1. Topology MongoDB

Change Streams được hỗ trợ trên **replica set** và **sharded cluster** của MongoDB có phiên bản và cấu hình phù hợp. Một tiến trình MongoDB **standalone** thông thường không thể mở change stream như replica set.

Trong phát triển local, có thể chạy **single-node replica set** để thử nghiệm. Đó vẫn là topology replica set; chỉ chạy một MongoDB container ở chế độ standalone rồi gọi `changeStream` sẽ gặp lỗi.

Cần kiểm tra:

- MongoDB đã khởi tạo replica set hoặc sharded cluster, driver kết nối đến topology được hỗ trợ.
- Người dùng có quyền `changeStream` và `find` trên tài nguyên cần theo dõi; mức quyền cụ thể tùy collection, database hoặc cluster.
- Oplog có dung lượng và khoảng thời gian giữ lịch sử đủ để khôi phục từ resume token khi ứng dụng ngừng chạy.
- Ứng dụng kết nối được với MongoDB qua TLS, thông tin xác thực và các tùy chọn driver đúng môi trường.
- Chức năng reactive dùng dependency Spring Data MongoDB Reactive và MongoDB Reactive Streams Driver tương thích với phiên bản ứng dụng.

Ví dụ cấu hình khởi đầu cho Spring Boot:

```yaml
spring:
  data:
    mongodb:
      uri: mongodb://app_user:secret@mongo1:27017,mongo2:27017,mongo3:27017/shop?replicaSet=rs0&authSource=admin
```

Đây chỉ là cấu trúc ví dụ. Lấy URI, mật khẩu và tên replica set từ quản lý cấu hình hoặc secret manager; không hardcode credential vào mã nguồn, Docker image hay Git. Trong môi trường Atlas, dùng URI cluster do Atlas cấp.

### 2.2. Ứng dụng sử dụng reactive stack

Sử dụng `ReactiveMongoTemplate` khi xử lý đầu vào/đầu ra theo Reactor, đặc biệt với Spring WebFlux, reactive repository và các API bất đồng bộ khác. `MongoTemplate` dạng đồng bộ có cơ chế lắng nghe khác; không tạo `Flux` chỉ bằng cách chuyển tên phương thức.

Một bộ dependency điển hình trong Spring Boot là:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-mongodb-reactive</artifactId>
</dependency>
```

Version MongoDB driver và Spring Data thường do BOM của Spring Boot quản lý. Kiểm tra API thực tế khi nâng phiên bản, đặc biệt các overload và builder option của Change Streams.

## 3. Hiểu `Flux<ChangeStreamEvent<T>>`

`Flux` trong Project Reactor biểu diễn một luồng từ 0 đến nhiều tín hiệu `onNext`, có thể kết thúc qua `onComplete` hoặc `onError`. Luồng Change Streams thường **sống lâu và không kết thúc theo số lượng bản ghi cố định**.

| Thành phần | Ý nghĩa đối với change stream |
| --- | --- |
| `Flux<ChangeStreamEvent<Order>>` | Publisher phát sự kiện thay đổi đơn hàng |
| `subscribe()` | Kích hoạt subscription và nhu cầu dữ liệu từ publisher |
| `onNext(event)` | Nhận một sự kiện thay đổi, không đồng nghĩa tác vụ nghiệp vụ đã hoàn thành |
| `onError(error)` | Pipeline thất bại và kết thúc subscription nếu không có cơ chế phục hồi |
| `onComplete()` | Có thể xuất hiện khi bị giới hạn bằng `take(...)`, đóng nguồn hoặc các điều kiện khác; không nên chờ nó như tác vụ hữu hạn |
| `cancel / Disposable.dispose()` | Hủy subscription; giải phóng tài nguyên khi dừng dịch vụ |
| `request(n)` và backpressure | Consumer thể hiện nhu cầu tiêu thụ; tốc độ sự kiện và tài nguyên vẫn phải được quan sát |

Trong đa số trường hợp, publisher là **cold**: mỗi lần subscribe tạo một quá trình theo dõi riêng và có thể mở thêm cursor trên server. Đừng tạo nhiều subscription chỉ để “chia việc” mà không thiết kế điều phối.

### 3.1. Các loại thay đổi thường gặp

| `operationType` | Ý nghĩa | Đặc điểm payload |
| --- | --- | --- |
| `INSERT` | Thêm document mới | Thường có `fullDocument` |
| `REPLACE` | Thay thế document | Thường có `fullDocument` |
| `UPDATE` | Sửa một phần document | Mặc định có mô tả cập nhật, có thể không có `fullDocument` |
| `DELETE` | Xóa document | Không có document đầy đủ; cần dựa trên `documentKey` |
| `INVALIDATE` | Stream không còn hợp lệ, ví dụ khi drop/rename ở phạm vi theo dõi thích hợp | Cần kế hoạch tạo stream mới; `resumeAfter` có giới hạn riêng |
| Các sự kiện mở rộng theo phiên bản | Ví dụ thao tác DDL hoặc thay đổi topology khi bật khả năng hỗ trợ | Kiểm tra khả năng và phiên bản MongoDB |

Điểm dễ sai: `ChangeStreamEvent<T>.getBody()` **có thể trả về `null`**. Vì vậy không được giả định sự kiện nào cũng có entity đang tồn tại.

### 3.2. Resume token và metadata

Mỗi sự kiện có một **resume token** (đối với các sự kiện được hỗ trợ). Token là dữ liệu opaque do MongoDB tạo ra để xác định vị trí có thể tiếp tục trong luồng:

```java
event.getResumeToken();    // Token để tiếp tục stream
event.getOperationType();  // INSERT, UPDATE, REPLACE, DELETE, ...
event.getBody();           // Có thể null, nhất là với DELETE / UPDATE
```

Không diễn giải, chỉnh sửa, tạo token từ timestamp của ứng dụng hay giả định token có thứ tự từ điển. Hãy lưu lại theo định dạng BSON phù hợp, có nhận diện **consumer và phạm vi stream**.

## 4. Tạo dữ liệu mẫu và mở luồng đơn giản

Định nghĩa document `Order`:

```java
import java.math.BigDecimal;
import java.time.Instant;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document("orders")
public class Order {

    @Id
    private String id;

    private String customerId;
    private String status;
    private BigDecimal total;
    private Instant updatedAt;

    // Constructor, getters và setters (hoặc dùng record phù hợp với mapper)
}
```

Ở lớp service, tạo một publisher Change Streams với `ReactiveMongoTemplate`:

```java
import org.springframework.data.mongodb.core.ChangeStreamEvent;
import org.springframework.data.mongodb.core.ChangeStreamOptions;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import reactor.core.publisher.Flux;

public class OrderChangeStreams {

    private final ReactiveMongoTemplate template;

    public OrderChangeStreams(ReactiveMongoTemplate template) {
        this.template = template;
    }

    public Flux<ChangeStreamEvent<Order>> changes() {
        ChangeStreamOptions options =
                ChangeStreamOptions.builder().build();

        return template.changeStream(
                "orders",
                options,
                Order.class
        );
    }
}
```

**Phân tích:**

- `"orders"` là tên **collection MongoDB thực tế** được theo dõi.
- `ChangeStreamOptions` mô tả tùy chọn của nguồn Change Streams.
- `Order.class` yêu cầu Spring Data chuyển `fullDocument` sang entity `Order` khi trường này tồn tại.
- Phương thức trả về publisher; nó **chưa bắt đầu tự xử lý** nếu chưa có subscription.
- Không thêm `.collectList()` hay `.blockLast()` trên một luồng cần chạy liên tục. Những phép này chờ luồng kết thúc và có thể không bao giờ trả kết quả.

### 4.1. Dùng `Flux` để quan sát trong bài thực hành

```java
Flux<ChangeStreamEvent<Order>> changes = service.changes();

Disposable subscription = changes
        .doOnNext(event -> System.out.println(
                "type=" + event.getOperationType()
                + ", token=" + event.getResumeToken()))
        .doOnError(error -> System.err.println(error.getMessage()))
        .subscribe();

// Ở điểm dừng được quản lý, hủy subscription:
subscription.dispose();
```

Cần import `reactor.core.Disposable` cho biến `subscription`. Trong mã production, dùng logger, xác định owner của subscription và quản lý vòng đời theo ứng dụng. Lệnh `dispose` trong ví dụ là hành động dừng có chủ đích, không đặt ngay sau `subscribe` vì sẽ dừng stream trước khi nhận sự kiện.

### 4.2. Phát sinh sự kiện để quan sát

Sau khi publisher đã subscribe và watch cursor đã được mở:

```javascript
use shop

db.orders.insertOne({
  _id: "O-1001",
  customerId: "C-01",
  status: "NEW",
  total: 1200000,
  updatedAt: new Date()
});

db.orders.updateOne(
  { _id: "O-1001" },
  {
    $set: {
      status: "PAID",
      updatedAt: new Date()
    }
  }
);

db.orders.deleteOne({ _id: "O-1001" });
```

Các sự kiện sẽ mang loại `INSERT`, `UPDATE` và `DELETE` tương ứng. Mã nhận sự kiện phải kiểm tra loại và dữ liệu thực tế thay vì giả định mỗi event có `Order`.

**Lưu ý về thời điểm mở cursor:** việc tạo `Flux` chưa đảm bảo đã mở watch cursor. Nếu muốn nhận cả sự kiện xảy ra trước lúc consumer sẵn sàng, cần khởi động từ checkpoint/operation time hợp lệ, hoặc bảo đảm luồng đã sẵn sàng trước khi ghi trong bài kiểm thử. Những ví dụ “subscribe rồi insert ngay” có thể có race trong một số cách sắp lịch.

## 5. Lọc sự kiện từ MongoDB bằng `ChangeStreamOptions`

Thay vì nhận mọi loại thao tác và xử lý tại Java, có thể đẩy một phần điều kiện xuống pipeline Change Streams. Spring Data cung cấp `ChangeStreamOptions.builder().filter(...)` để truyền aggregation filter vào stream.

Ví dụ chỉ theo dõi `insert`, `update`, `replace`, `delete`:

```java
import static org.springframework.data.mongodb.core.aggregation.Aggregation.match;
import static org.springframework.data.mongodb.core.aggregation.Aggregation.newAggregation;

import org.springframework.data.mongodb.core.ChangeStreamOptions;
import org.springframework.data.mongodb.core.aggregation.Aggregation;
import org.springframework.data.mongodb.core.query.Criteria;

Aggregation filter = newAggregation(
        match(Criteria.where("operationType")
                .in("insert", "update", "replace", "delete"))
);

ChangeStreamOptions options = ChangeStreamOptions.builder()
        .filter(filter)
        .build();

Flux<ChangeStreamEvent<Order>> changes =
        template.changeStream("orders", options, Order.class);
```

Lưu ý các giá trị `operationType` trong aggregation là **chuỗi lowercase** của event MongoDB; còn API Java có thể trả enum như `OperationType.INSERT`.

Đối với stream tiêu thụ dài hạn, filter giúp giảm dữ liệu phải chuyển về ứng dụng. Tuy nhiên filter cũng có giới hạn: nếu chỉ nhận `PAID` từ `fullDocument.status`, bạn cần hiểu rằng các sự kiện `UPDATE` mặc định có thể không chứa `fullDocument`. Lọc trên `updateDescription.updatedFields.status` (khi có) là cách tiếp cận khác, nhưng phải xử lý cả replace và các cập nhật không có field đó.

### 5.1. Có thể dùng `fullDocument` trên cập nhật không?

Theo mặc định, cập nhật một phần thường cho phép quan sát dữ liệu trong `updateDescription` và khóa document. Để yêu cầu MongoDB tra cứu lại document đầy đủ cho sự kiện cập nhật, dùng chính sách **`updateLookup`**; cách gọi builder tương ứng có thể khác giữa các phiên bản Spring Data.

Với API Spring Data MongoDB có hỗ trợ `returnFullDocumentOnUpdate()`:

```java
ChangeStreamOptions options = ChangeStreamOptions.builder()
        .returnFullDocumentOnUpdate()
        .build();

Flux<ChangeStreamEvent<Order>> changes =
        template.changeStream("orders", options, Order.class);
```

**Giới hạn quan trọng:** `updateLookup` thực hiện tra cứu trạng thái document, và kết quả có thể là **phiên bản mới hơn chính sự kiện UPDATE** nếu nhiều thay đổi liên tiếp xảy ra. Nó cũng có thể là `null` nếu document đã bị xóa. Vì vậy không dùng `getBody()` từ update lookup làm bằng chứng duy nhất để tái dựng chính xác từng giá trị trung gian. Khi cần biết trường nào thay đổi, hãy xem `updateDescription` trong event gốc.

### 5.2. Giữ `_id` và tính hợp lệ của resume token

Trong kết quả Change Streams, trường `_id` của event chứa resume token. Không dùng `$project`, `$replaceRoot` hay stage khác để xóa/sửa trường `_id` này trong change-stream pipeline. MongoDB cần token để hỗ trợ resume; biến đổi token sẽ làm stream không hoạt động đúng hoặc bị từ chối.

Đừng nhầm `_id` của **change event** với `_id` của **document đơn hàng**. Khi cần khóa document, đọc `documentKey._id` từ thông tin sự kiện.

## 6. Xử lý bằng Reactor: chọn toán tử theo mục đích

Vì handler thường cần ghi dữ liệu hoặc gọi service khác, xử lý sự kiện là một tác vụ **bất đồng bộ**. Việc chọn toán tử quyết định tính thứ tự, đồng thời và thời điểm báo “xử lý xong”.

### 6.1. `doOnNext` chỉ dành cho side effect đồng bộ

Không nên viết:

```java
changes.doOnNext(event -> {
    projectionRepository.save(convert(event)).subscribe();
}).subscribe();
```

Lỗi ở đây là tạo một subscription lồng bên trong: outer stream không chờ `save` thành công, lỗi xử lý có thể không nổi lên, và một checkpoint ở outer stream có thể được ghi sớm.

Thay bằng một toán tử composition trả về publisher:

```java
Flux<Void> processing = changes.concatMap(event ->
        projectionService.apply(event)
);
```

Giả sử `projectionService.apply(event)` trả về `Mono<Void>` và chỉ hoàn tất khi side effect mong muốn đã thực sự hoàn thành.

### 6.2. Khi nào dùng `concatMap`?

`concatMap` subscribe lần lượt từng publisher con, đợi publisher trước hoàn thành mới xử lý publisher sau. Nó phù hợp với consumer cần bảo toàn thứ tự và tiến độ checkpoint:

```java
Flux<Void> processing = changes.concatMap(event ->
        projectionService.apply(event)
);
```

Ưu điểm: đơn giản hóa thứ tự xử lý. Nhược điểm: throughput bị giới hạn bởi độ trễ của một sự kiện. Một event chậm có thể chặn các event sau.

### 6.3. Khi nào dùng `flatMap`?

`flatMap` cho phép các tác vụ xử lý song song và có thể phát kết quả **không theo thứ tự đầu vào**:

```java
Flux<Void> processing = changes.flatMap(
        event -> notificationService.publish(event),
        8 // Giới hạn 8 tác vụ đồng thời
);
```

Chỉ phù hợp khi các sự kiện xử lý **độc lập và idempotent**, đồng thời checkpoint không giả định mọi event trước token mới nhất đều đã hoàn tất. Nếu xử lý song song nhưng chỉ lưu token của event hoàn thành cuối cùng, ứng dụng có thể mất các event đứng trước còn đang xử lý khi restart.

Có thể phân hoạch theo khóa đơn hàng và xử lý tuần tự trong từng nhóm, nhưng thiết kế đó phải có chiến lược checkpoint toàn cục/partition thích hợp; một MongoDB change stream không tự cung cấp offset cho mỗi nhóm.

### 6.4. Các toán tử hữu ích khác

| Toán tử | Cách dùng | Cần tránh |
| --- | --- | --- |
| `filter` | Chặn sự kiện Java không liên quan | Bỏ event trước khi checkpoint mà không xác định chính sách resume |
| `handle` | Lọc và chuyển đổi một lần, xử lý body có thể `null` | Chuyển `null` thành tín hiệu `onNext` |
| `map` | Biến đổi dữ liệu đồng bộ | Gọi API blocking trong lambda |
| `concatMap` | Xử lý async theo thứ tự | Giữ publisher con không bao giờ hoàn tất |
| `flatMap(mapper, concurrency)` | Xử lý độc lập có giới hạn đồng thời | Dùng unbounded concurrency rồi checkpoint sai thứ tự |
| `doOnNext` / `doOnError` | Logging, metrics, quan sát | Đưa persistence chính vào callback mà không compose publisher |
| `onErrorResume` | Chủ động chuyển sang fallback có kiểm soát | Nuốt lỗi và đánh dấu event thành công khi thực tế thất bại |
| `retryWhen` | Tạo retry với backoff cho lỗi tạm thời | Retry vô hạn lỗi không thể phục hồi hoặc lỗi token hết hạn |
| `take(n)` | Bài kiểm thử hữu hạn | Nhầm luồng production đã hoàn tất sau n sự kiện |

## 7. Xử lý các loại event và payload `null`

Tạo một handler có đầu ra `Mono<Void>` để bảo đảm hoàn thành xử lý trước khi tiến checkpoint.

```java
import org.springframework.data.mongodb.core.ChangeStreamEvent;
import reactor.core.publisher.Mono;

public interface OrderEventHandler {

    // Hợp đồng: hoàn thành thành công khi side effect đã được ghi bền vững.
    Mono<Void> apply(ChangeStreamEvent<Order> event);
}
```

Gợi ý cách triển khai:

```java
public Mono<Void> apply(ChangeStreamEvent<Order> event) {
    return switch (event.getOperationType()) {
        case INSERT, REPLACE -> {
            Order body = event.getBody();
            if (body == null) {
                yield Mono.error(new IllegalStateException(
                        "Thiếu fullDocument cho insert/replace"));
            }
            yield projection.upsert(body);
        }
        case UPDATE -> projection.applyUpdate(event);
        case DELETE -> projection.deleteByDocumentKey(event);
        default -> Mono.empty();
    };
}
```

Đoạn trên minh họa logic của một implementation có các phương thức `projection.upsert`, `projection.applyUpdate` và `projection.deleteByDocumentKey` riêng. Những phương thức này cần trả `Mono<Void>` và xử lý idempotency. Cách dùng switch expression phù hợp Java hiện đại; với Java thấp hơn có thể dùng `switch` hoặc `if`.

Đối với `DELETE`, `fullDocument` thường vắng mặt: lấy ID từ `documentKey` (có thể qua raw event) để xóa projection hoặc phát tombstone. Không dùng `event.getBody().getId()` cho thao tác này.

Đối với `UPDATE`, tùy chính sách hệ thống:

- Áp dụng trực tiếp `updatedFields` và `removedFields` từ `updateDescription`; cần giải quyết nested fields, arrays và thay đổi schema.
- Sử dụng `updateLookup` để lấy trạng thái hiện tại khi projection chỉ cần “trạng thái mới nhất”, chấp nhận có thể bỏ qua trạng thái trung gian.
- Đọc lại document nguồn theo `documentKey` nếu nhu cầu chỉ là đồng bộ trạng thái cuối cùng; trường hợp đã xóa thì xử lý như tombstone.

**Không tự động bỏ event có `getBody() == null`** khi logic nghiệp vụ còn cần biết UPDATE hoặc DELETE.

## 8. Quản lý subscription theo vòng đời ứng dụng

Một consumer thường chạy dài hạn và cần một chủ sở hữu rõ ràng. Khi ứng dụng khởi động, bật subscription. Khi ứng dụng dừng, cancel. Không tạo một stream mới mỗi request HTTP.

Ví dụ lớp quản lý lifecycle đơn giản:

```java
import jakarta.annotation.PreDestroy;
import java.util.concurrent.atomic.AtomicReference;

import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

import reactor.core.Disposable;
import reactor.core.publisher.Flux;

@Component
public class OrderChangeStreamRunner {

    private final OrderEventConsumer consumer;
    private final AtomicReference<Disposable> current =
            new AtomicReference<>();

    public OrderChangeStreamRunner(OrderEventConsumer consumer) {
        this.consumer = consumer;
    }

    @EventListener(ApplicationReadyEvent.class)
    public void start() {
        Disposable subscription = consumer.consume()
                .subscribe(
                        ignored -> { },
                        error -> System.err.println(
                                "Order change stream stopped: " + error),
                        () -> System.out.println(
                                "Order change stream completed")
                );

        Disposable previous = current.getAndSet(subscription);
        if (previous != null) {
            previous.dispose();
        }
    }

    @PreDestroy
    public void stop() {
        Disposable subscription = current.getAndSet(null);
        if (subscription != null) {
            subscription.dispose();
        }
    }
}
```

Trong production, thay `System.out` bằng logger có dữ liệu correlation, đặt guard chống gọi `start()` nhiều lần và giám sát lỗi dừng luồng. Đoạn trên minh họa cách sở hữu subscription; chưa có chính sách retry, checkpoint hoặc cơ chế leader election.

**Lưu ý:** `@EventListener(ApplicationReadyEvent.class)` chỉ xác định lúc ứng dụng bắt đầu tạo subscription; không bảo đảm ứng dụng đã sẵn sàng tiêu thụ event. Đối với hệ thống cần readiness thực sự, xây dựng một trạng thái health/readiness riêng theo tiến trình mở cursor hoặc thời điểm đã xác nhận nhận sự kiện.

### 8.1. Nếu chạy nhiều instance thì sao?

Mỗi instance tự subscribe vào một Change Stream có thể nhận cùng các sự kiện; MongoDB không tự chia mỗi event cho một instance như cơ chế consumer group. Tùy nhu cầu:

- Nếu mọi instance đều cần thông báo, broadcast có thể phù hợp.
- Nếu chỉ một instance được phép cập nhật một projection chung, dùng **distributed lease/leader election**, gồm hạn thuê và fencing để tránh hai chủ hoạt động đồng thời.
- Nếu muốn phân vùng công việc, cần thiết kế cơ chế điều phối/queue riêng thay vì giả định Change Streams tự chia tải.

## 9. Resume token: phục hồi sau restart

### 9.1. Vì sao `retryWhen` chưa đủ?

Driver có cơ chế tự resume một số lỗi mạng phù hợp. Nhưng ứng dụng còn có những tình huống:

- Service restart hoặc deploy.
- Side effect nghiệp vụ thất bại sau khi nhận event.
- Hết thời gian giữ oplog và token không còn dùng được.
- Thay đổi filter hoặc phạm vi stream không tương thích với token trước.
- Collection bị drop/rename khiến stream invalidated.

Nếu chỉ khởi tạo lại stream từ thời điểm “bây giờ”, các sự kiện trong thời gian service dừng có thể bị bỏ qua. Vì vậy production consumer cần **checkpoint bền vững**.

### 9.2. Chọn thời điểm lưu checkpoint

Quy tắc cốt lõi cho một consumer tuần tự:

```text
event từ MongoDB
     │
     ▼
xử lý nghiệp vụ (Mono<Void>)
     │
     ├─ lỗi ──> KHÔNG ghi token mới
     │
     ▼ thành công
lưu resume token bền vững
     │
     ▼
được phép nhận event tiếp theo
```

Nếu ghi token **trước** side effect, ứng dụng chết ở giữa sẽ bỏ qua event khi khởi động lại. Nếu chỉ ghi token **sau** side effect, ứng dụng chết trước khi checkpoint có thể xử lý lại event. Đây là lý do consumer phải **idempotent** và thường có ngữ nghĩa **at least once** đối với việc xử lý nghiệp vụ.

Resume token không đảm bảo “exactly once” cho side effect bên ngoài (gửi email, HTTP, Kafka, hệ thống thanh toán). Với những thao tác đó, sử dụng idempotency key hoặc outbox/inbox phù hợp.

### 9.3. Mẫu consumer có checkpoint

Định nghĩa hai hợp đồng phụ thuộc rõ ràng:

```java
import org.bson.BsonDocument;
import org.springframework.data.mongodb.core.ChangeStreamEvent;
import reactor.core.publisher.Mono;

public interface ResumeTokenStore {
    Mono<BsonDocument> load(String consumerId);
    Mono<Void> save(String consumerId, BsonDocument token);
}

public interface OrderChangeProcessor {
    Mono<Void> process(ChangeStreamEvent<Order> event);
}
```

- `load` phát một token nếu đã có; trả `Mono.empty()` nếu chưa có checkpoint.
- `save` phải báo hoàn thành khi checkpoint đã ghi bền vững đến mức hệ thống yêu cầu.
- `process` xử lý idempotent và chỉ hoàn tất sau side effect cần thiết.
- Cần lưu token ở collection riêng, ví dụ `consumer_offsets`, **không** trong collection `orders` đang watch để tránh tự tạo vòng lặp khi checkpoint.

Ví dụ phối hợp:

```java
import java.util.Optional;

import org.bson.BsonDocument;
import org.springframework.data.mongodb.core.ChangeStreamEvent;
import org.springframework.data.mongodb.core.ChangeStreamOptions;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public final class OrderEventConsumer {

    private static final String CONSUMER_ID = "order-projector-v1";

    private final ReactiveMongoTemplate template;
    private final ResumeTokenStore tokens;
    private final OrderChangeProcessor processor;

    public OrderEventConsumer(
            ReactiveMongoTemplate template,
            ResumeTokenStore tokens,
            OrderChangeProcessor processor
    ) {
        this.template = template;
        this.tokens = tokens;
        this.processor = processor;
    }

    // Mỗi subscription mới phải đọc lại checkpoint từ storage.
    public Flux<Void> consume() {
        return Flux.defer(() ->
                tokens.load(CONSUMER_ID)
                        .map(Optional::of)
                        .defaultIfEmpty(Optional.empty())
                        .flatMapMany(saved -> changeEvents(
                                saved.orElse(null)))
                        .concatMap(this::processAndCheckpoint)
        );
    }

    private Flux<ChangeStreamEvent<Order>> changeEvents(
            BsonDocument resumeToken
    ) {
        ChangeStreamOptions options = resumeToken == null
                ? ChangeStreamOptions.builder().build()
                : ChangeStreamOptions.builder()
                        .resumeToken(resumeToken)
                        .build();

        return template.changeStream("orders", options, Order.class);
    }

    private Mono<Void> processAndCheckpoint(
            ChangeStreamEvent<Order> event
    ) {
        return processor.process(event).then(
                Mono.defer(() -> {
                    BsonDocument token = event.getResumeToken();

                    if (token == null) {
                        return Mono.error(new IllegalStateException(
                                "Change stream event thiếu resume token"));
                    }

                    return tokens.save(CONSUMER_ID, token);
                })
        );
    }
}
```

Cấu trúc này có ý nghĩa:

1. `Flux.defer` bảo đảm lúc subscribe lại, chuỗi **load checkpoint → mở stream** được thực hiện lại.
2. `Optional.empty()` thể hiện trường hợp chưa có token; không tạo `Mono.just(null)` vì Reactor cấm phần tử `null`.
3. `resumeToken(...)` yêu cầu MongoDB tiếp tục sau token đã lưu; cần API builder tương thích với phiên bản Spring Data đang dùng.
4. `concatMap` chỉ bắt đầu xử lý event mới sau khi cả `processor.process` lẫn `tokens.save` của event trước kết thúc.
5. Nếu xử lý hoặc ghi checkpoint lỗi, publisher phát `onError`; phía quản lý subscription quyết định retry hay dừng có cảnh báo.
6. Thay đổi `CONSUMER_ID` khi cần một consumer độc lập với vị trí/định nghĩa stream riêng.

**Giới hạn ví dụ:** đây là mẫu kiến trúc cần hiện thực `ResumeTokenStore`, `OrderChangeProcessor` và chính sách startup/retry. Nó không phải dịch vụ end-to-end có thể chạy khi chưa cài đặt các thành phần đó.

### 9.4. Lưu token dạng BSON, không chuyển đổi tùy ý

Resume token thường là `BsonDocument`. Khi lưu dưới dạng BSON/Extended JSON, hãy bảo toàn đúng kiểu dữ liệu:

```java
String encoded = token.toJson();
BsonDocument decoded = BsonDocument.parse(encoded);
```

Đây là minh họa cho quá trình tuần tự hóa/giải tuần tự hóa bằng BSON Extended JSON. Trong ứng dụng thực tế, chọn schema và codec cho storage, ghi kèm `consumerId`, phạm vi namespace và thông tin cấu hình stream. Không sử dụng `token.toString()` làm hợp đồng lưu trữ mặc định nếu chưa kiểm chứng round-trip.

Khi nhiều worker có thể ghi cùng checkpoint, dùng lease/fencing và điều kiện ghi nguyên tử để một consumer cũ không ghi đè token tiến độ của consumer mới.

## 10. Resume sau lỗi và quy tắc retry

### 10.1. Phân biệt lỗi tạm thời và lỗi không thể tự khắc phục

| Nhóm lỗi | Ví dụ | Ứng xử phù hợp |
| --- | --- | --- |
| Tạm thời | Network timeout, kết nối chập chờn, failover có thể phục hồi | Backoff có jitter, mở lại từ checkpoint |
| Logic nghiệp vụ | Mapping DTO lỗi, ID không hợp lệ, projection thiếu dữ liệu | Ghi nhận lỗi/đưa vào xử lý lỗi có chủ đích, không retry vô hạn |
| Quyền hoặc cấu hình | Thiếu `changeStream`, sai URI/topology | Báo lỗi, sửa cấu hình |
| Token hết hiệu lực | Oplog không còn sự kiện tại vị trí token | Có quy trình resync/snapshot, không tự ý bỏ checkpoint |
| Stream invalidate | Drop/rename collection tùy phạm vi | Xác định cách tạo stream mới; cân nhắc `startAfter` khi phù hợp |

Reactor cho phép cấu hình `Retry` có backoff:

```java
import java.time.Duration;
import reactor.util.retry.Retry;

Flux<Void> monitored = consumer.consume()
        .retryWhen(Retry.backoff(8, Duration.ofSeconds(2))
                .maxBackoff(Duration.ofSeconds(30))
                .filter(this::isTransientChangeStreamFailure));
```

`isTransientChangeStreamFailure(Throwable)` là hàm **do ứng dụng hiện thực** để phân loại lỗi bằng mã MongoDB/driver, nhãn lỗi và chính sách nghiệp vụ. Không dùng `retryWhen(Retry.max(Long.MAX_VALUE))` cho mọi exception: token đã hết hạn hoặc cấu hình sai sẽ tạo vòng lặp không có tiến triển.

Khi retry một publisher `consume()` như mục trước, subscription mới **đọc lại checkpoint** trước khi mở stream. Nếu error xảy ra sau xử lý thành công nhưng trước khi token lưu bền vững, event có thể phát lại: handler phải idempotent.

### 10.2. `resumeAfter`, `startAfter` và operation time

MongoDB cung cấp các cách xác định vị trí bắt đầu khác nhau:

- **`resumeAfter`:** dùng resume token để tiếp tục từ vị trí event đã xử lý trong stream có thể resume.
- **`startAfter`:** có những trường hợp hỗ trợ mở stream mới sau event `invalidate`; không coi nó giống `resumeAfter` trong mọi hoàn cảnh.
- **`startAtOperationTime`:** bắt đầu từ một thời điểm thao tác MongoDB hợp lệ nếu API và topology hỗ trợ, nhưng còn phụ thuộc lịch sử oplog.

Không thể resume nếu lịch sử cần thiết đã bị cắt khỏi oplog. Việc giữ timestamp do Java tạo ra không thay thế được token MongoDB. Khi token không còn dùng được, hệ thống phải xác định cách dựng lại trạng thái từ nguồn, chấp nhận khoảng mất dữ liệu hoặc dùng cơ chế ingest khác.

### 10.3. Những thông tin phải log và đo

Một consumer production nên có:

- Consumer ID, collection/database đang watch, phiên bản bộ lọc, session/lifecycle và mức độ sẵn sàng.
- Số event nhận được, xử lý thành công, thất bại, retry, thời gian từ event đến hoàn tất.
- Tuổi của checkpoint và khoảng cách giữa thời gian event và thời gian xử lý hiện tại.
- Thời gian xử lý p50/p95/p99, độ trễ lưu token, kích thước hàng đợi nếu có.
- Số subscription đang tồn tại, reconnect, lỗi mạng, quyền và token không hợp lệ.

Log token theo mức độ cần thiết, tránh ghi toàn bộ nội dung tài liệu chứa dữ liệu nhạy cảm.

## 11. Bảo toàn ngữ nghĩa nghiệp vụ

### 11.1. Ít nhất một lần, không phải chính xác một lần

Giả sử process thành công, sau đó tiến trình chết trước khi lưu token:

```text
T0: nhận event E123
T1: cập nhật projection thành công
T2: tiến trình dừng
T3: khởi động lại từ token E122
T4: event E123 được xử lý lần nữa
```

Thiết kế an toàn cần chịu được việc lặp E123, chẳng hạn:

- Upsert projection theo document ID và version.
- Ghi một `processed_event` với khóa duy nhất phù hợp trước hoặc cùng transaction với side effect trong cùng MongoDB.
- Gán idempotency key cho call ngoài hoặc đưa lệnh gửi ra outbox.
- Khi phải bảo toàn thứ tự theo document, kiểm tra version hoặc sequence hợp lệ trước khi ghi.

Ngược lại, nếu lưu token E123 trước khi cập nhật projection, service có thể chết khiến lần khởi động sau bỏ qua E123 hoàn toàn. **Thứ tự checkpoint sau side effect là điều kiện cần**, nhưng vẫn cần idempotency để đối phó duplicate.

### 11.2. Transaction và Change Streams

Nếu một transaction MongoDB thay đổi nhiều document, các thay đổi của transaction chỉ hiển thị trong Change Streams sau khi transaction được commit. Transaction bị abort không tạo ra các thay đổi đã commit để consumer xử lý.

Bản thân `watch` là nguồn đọc dài hạn; không bọc toàn bộ subscription Change Streams trong một transaction kéo dài vô hạn. Nếu processor cần cập nhật một số collection liên quan, có thể dùng transaction ngắn riêng cho **một event** nếu topology hỗ trợ, nhưng phải kiểm tra session, reactive context và checkpoint tương ứng.

### 11.3. Đề phòng out-of-order khi xử lý song song

Ngay cả khi MongoDB cung cấp thứ tự event của nguồn, việc dùng `flatMap` có thể làm **kết quả xử lý hoàn thành khác thứ tự**. Với một projection chung phụ thuộc tuần tự, ưu tiên `concatMap`. Nếu phải tăng throughput, thiết kế phân luồng theo key và checkpoint dựa trên những event đã hoàn tất liên tiếp; không chỉ lấy “token mới nhất thấy được”.

### 11.4. Không dùng Change Streams để thay thế xác minh giao dịch

Change Stream hữu ích để cập nhật view/projection và hệ thống thứ cấp. Nếu client cần biết một lệnh đặt hàng đã commit hay chưa, ứng dụng nên dựa vào kết quả giao dịch và đọc dữ liệu nguồn theo chính sách nhất quán phù hợp, không đợi event Change Stream làm tín hiệu xác nhận duy nhất.

## 12. Backpressure và giới hạn tài nguyên

Reactive Streams hỗ trợ cơ chế `request(n)`; driver có thể điều tiết việc phân phối event theo nhu cầu downstream. Tuy nhiên:

- MongoDB vẫn nhận ghi và oplog vẫn thay đổi trong khi consumer chậm.
- Backpressure không kéo dài vô hạn khoảng lịch sử có thể resume trong oplog.
- `flatMap` không giới hạn hoặc một queue tự tạo không giới hạn có thể ăn hết RAM.
- `bufferTimeout` và `onBackpressureBuffer` cần kích thước giới hạn, chiến lược lỗi và checkpoint phù hợp; nếu drop event tùy ý thì luồng đã mất ngữ nghĩa xử lý đầy đủ.
- Thao tác blocking (`Thread.sleep`, `.block()`, JDBC đồng bộ) bên trong operator có thể chặn event-loop hoặc driver thread. Khi buộc phải gọi code blocking, tách sang `Schedulers.boundedElastic()` có giới hạn, nhưng ưu tiên API reactive xuyên suốt.

Ví dụ giới hạn số tác vụ độc lập:

```java
Flux<Void> notifications = stream
        .flatMap(
                event -> notifier.publish(event)
                        .timeout(Duration.ofSeconds(5)),
                4
        );
```

**Không lấy pipeline `flatMap` này làm cơ chế checkpoint tuần tự** nếu các task có thể hoàn thành đảo thứ tự.

Tối ưu hiệu năng cần đo bằng dữ liệu thật: kích thước document, tốc độ write, thời gian xử lý downstream, hiệu ứng failover và thời gian giữ oplog.

## 13. Thiết kế filter và mapping an toàn

Không phải mọi event đều nên gửi nguyên raw payload ra ngoài:

- Filter càng sớm càng tốt theo `operationType`, namespace hoặc các field mà Change Streams cho phép.
- Hạn chế full document lookup khi không cần; đọc thêm dữ liệu có thể tăng chi phí và độ trễ.
- Không đưa thông tin cá nhân, bí mật hay trường nội bộ vào log hoặc thông báo bên thứ ba nếu không cần.
- Dùng đúng tên field MongoDB trong pipeline filter, nhất là khi entity dùng `@Field` để đổi tên.
- Đối với thay đổi schema của entity, quy định cách xử lý document cũ và event lạ; tránh crash liên tục tại một token do mapping cứng.
- Khi cấu hình pipeline mới, xem xét khả năng resume token đã lưu còn tương thích với namespace, phạm vi và chuỗi filter hay không.

Trường hợp ghi chỉ mục tìm kiếm thứ cấp: có thể chỉ cần `documentKey`, sau đó đọc document mới nhất để dựng lại index. Tuy nhiên cần chấp nhận eventual consistency và biến mất document giữa hai bước; `DELETE` phải xóa hoặc đánh tombstone đúng bản ghi.

## 14. Kiểm thử Change Streams với Reactor

Một bài kiểm thử đơn vị mock `Flux` có thể xác nhận logic operator, nhưng không chứng minh MongoDB thực sự phát Change Streams, hỗ trợ resume hay hoạt động sau failover. Cần **integration test** trên replica set thực hoặc Testcontainers dựng MongoDB có bật replica set.

### 14.1. Ma trận kiểm thử nên có

| Trường hợp | Kỳ vọng |
| --- | --- |
| Insert một order | Phát `INSERT`, map được entity |
| Update `status` | Phát `UPDATE`, quan sát updateDescription và chính sách fullDocument |
| Delete order | Phát `DELETE`, body vắng nhưng documentKey có thể dùng |
| Handler thành công | Checkpoint tiến sau xử lý |
| Handler lỗi | Checkpoint không tiến, lỗi nổi lên hoặc vào cơ chế retry rõ ràng |
| Restart từ token cũ | Event chưa checkpoint được xử lý lại |
| Token không hợp lệ / hết oplog | Consumer dừng có cảnh báo/resync theo quy trình |
| Nhiều instance | Không vô tình chạy hai consumer ghi projection chung |
| Burst event lớn | Không mất thứ tự bắt buộc, không tăng RAM không giới hạn |
| Thay đổi schema | Mapping và handler xử lý đúng hoặc báo lỗi có kiểm soát |

### 14.2. Test logic với `StepVerifier`

Một consumer nhận `Flux` có thể được kiểm tra bằng publisher giả lập. Ví dụ kiểm tra rằng `concatMap` giữ thứ tự và chỉ xử lý event sau khi tác vụ trước hoàn thành:

```java
import java.time.Duration;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.assertj.core.api.Assertions.assertThat;

class SequentialProcessingTest {

    @Test
    void concatMapWaitsForPreviousTask() {
        List<Integer> completed = new CopyOnWriteArrayList<>();

        Flux<Integer> source = Flux.just(1, 2, 3);

        Flux<Integer> result = source.concatMap(number ->
                Mono.delay(Duration.ofMillis(20))
                        .map(ignored -> number)
                        .doOnNext(completed::add)
        );

        StepVerifier.create(result)
                .expectNext(1, 2, 3)
                .verifyComplete();

        assertThat(completed).containsExactly(1, 2, 3);
    }
}
```

Test này chỉ chứng minh hành vi Reactor. Nó không mô phỏng đầy đủ driver, MongoDB resume token hoặc quyền truy cập cluster.

### 14.3. Integration test thực tế

Quy trình khuyến nghị:

1. Khởi động MongoDB replica set thử nghiệm, sử dụng URI của replica set.
2. Tạo collection `orders`, dọn dữ liệu test riêng.
3. Mở change stream và có cơ chế xác định watch cursor đã sẵn sàng; tránh giả định `subscribe()` đồng nghĩa cursor chắc chắn đã mở.
4. Insert, update, delete dữ liệu từ connection khác hoặc cùng client theo kế hoạch có kiểm soát.
5. Dùng `take(n)` và `StepVerifier` với timeout để giới hạn thời gian kiểm thử.
6. Tách kiểm thử `resumeToken`: lưu token sau event A, dừng subscription, tạo event B rồi subscribe lại từ token A; xác nhận B được nhận.
7. Dùng fault injection để xác nhận checkpoint sau xử lý và idempotency.
8. Dọn tài nguyên, hủy subscription và tắt replica set sau test.

Ví dụ một phần kiểm thử tính chất event stream khi có nguồn dữ liệu được tạo bởi fixture:

```java
Flux<ChangeStreamEvent<Order>> updates = template
        .changeStream(
                "orders",
                ChangeStreamOptions.builder().build(),
                Order.class
        )
        .filter(event -> event.getOperationType() != null)
        .take(3);

StepVerifier.create(updates)
        .expectNextCount(3)
        .expectComplete()
        .verify(Duration.ofSeconds(20));
```

Đoạn này cần một **fixture độc lập** phát đủ ba sự kiện sau khi stream sẵn sàng; nếu thiếu fixture, test sẽ chờ đến timeout. Đây là skeleton cho integration test, chưa phải test chạy độc lập.

### 14.4. Vì sao virtual time không thay thế MongoDB?

`StepVerifier.withVirtualTime` rất hữu ích để thử `delay`, `timeout`, `retryBackoff` ở Reactor. Tuy nhiên MongoDB server, oplog, network và thay đổi topology chạy theo thời gian thực. Virtual time không thể chứng minh một resume token còn hợp lệ hay MongoDB đã phát event sau transaction commit.

## 15. Xử lý lỗi thường gặp

| Triệu chứng | Nguyên nhân phổ biến | Cách xử lý |
| --- | --- | --- |
| `$changeStream is only supported on replica sets` | MongoDB đang standalone | Dựng replica set hợp lệ hoặc dùng sharded cluster |
| Không có sự kiện dù đã ghi | Chưa subscribe, chưa mở cursor, đang watch sai namespace | Xác minh subscription, collection, filter và thời điểm watch bắt đầu |
| Nhận event nhưng `getBody() == null` | `UPDATE` không bật lookup hoặc `DELETE` | Xử lý dựa trên `operationType`, `updateDescription` và `documentKey` |
| Chỉ nhận event khi gọi HTTP API | Subscription đang bị tạo trong handler hoặc bị hủy sớm | Dời consumer sang lifecycle của ứng dụng |
| Lỗi không xuất hiện | Dùng `subscribe()` lồng bên trong `doOnNext` | Dùng `concatMap` / `flatMap` và propagate `Mono` |
| Sự kiện bị lặp sau restart | Đã xử lý nhưng chưa checkpoint | Thiết kế idempotent và lưu token sau xử lý |
| Sự kiện bị mất sau restart | Lưu token trước side effect hoặc reset consumer về hiện tại | Sửa thứ tự checkpoint; resync dữ liệu nếu cần |
| Retry liên tục không tiến | Token hết hạn, thiếu quyền hoặc lỗi schema | Phân loại lỗi, dừng với cảnh báo, khôi phục có chủ đích |
| Kết quả cập nhật “quá mới” | Dùng fullDocument update lookup | Chuyển sang patch từ updateDescription nếu cần trạng thái theo từng event |
| CPU/RAM cao | Handler chậm, buffer hoặc concurrency không giới hạn | Giới hạn concurrency, đo lag, tối ưu filter và side effect |
| Hai instance cập nhật chồng nhau | Cả hai đều subscribe cùng stream | Thêm lease/fencing hoặc thiết kế idempotent đa consumer |
| Consumer dừng sau drop collection | Stream invalidated | Xử lý invalidate và khởi tạo namespace/stream mới phù hợp |

## 16. So sánh các cách tiêu thụ sự kiện

| Cách làm | Ưu điểm | Đánh đổi |
| --- | --- | --- |
| `changes.subscribe(event -> log(event))` | Dễ quan sát trong demo | Không có checkpoint hoặc quy trình lỗi |
| `changes.concatMap(handler::apply)` | Giữ thứ tự xử lý, chờ side effect | Một event chậm chặn event sau |
| `changes.flatMap(handler::apply, n)` | Thông lượng tốt với tác vụ độc lập | Đảo thứ tự hoàn thành, checkpoint phức tạp |
| `concatMap(process → checkpoint)` | Có thể phục hồi, ngữ nghĩa xử lý rõ | Cần storage bền vững và handler idempotent |
| `changeStream + outbox/queue` | Tách side effect và hỗ trợ nhiều consumer với hàng đợi chuyên dụng | Tăng thành phần hệ thống, cần thiết kế đồng bộ nhất quán |

Không có một toán tử Reactor nào tự tạo ra exact-once end-to-end. Tính chất hệ thống phụ thuộc vào **thứ tự xử lý**, **lưu checkpoint**, **idempotency** và **cách xử lý lỗi**.

## 17. Bài tập thực hành

**Bài 1 — Quan sát cơ bản.** Tạo collection `orders` với các trường `_id`, `status`, `customerId`. Mở `ReactiveMongoTemplate.changeStream` và log `operationType`. Insert, update và delete một đơn. Giải thích tại sao `getBody()` có thể khác nhau giữa các event.

**Bài 2 — Filter.** Chỉ nhận `insert`, `update`, `replace`, `delete` trong ChangeStreamOptions. So sánh filter phía MongoDB và `Flux.filter` ở phía Java. Cho ví dụ filter `UPDATE` dựa trên `updateDescription.updatedFields.status` và mô tả điểm còn thiếu khi có `REPLACE`.

**Bài 3 — Xử lý tuần tự.** Tạo handler giả lập trả `Mono.delay`, cho nhiều event đến liên tiếp. So sánh `concatMap` và `flatMap`. Dùng `StepVerifier` chứng minh thứ tự thực thi; giải thích tại sao checkpoint không được dùng token mới nhất khi `flatMap` còn task cũ.

**Bài 4 — Resume token.** Lưu token theo consumer ID vào collection khác. Xử lý ba event, chủ động dừng sau event thứ hai, thêm một event mới, rồi khởi động lại. Chứng minh chỉ những event chưa checkpoint cần được xử lý tiếp; nếu event cuối lặp, handler vẫn không tạo side effect trùng.

**Bài 5 — Failure injection.** Cho projection thất bại sau khi đã ghi một phần. Kiểm tra checkpoint không tiến sai, retry có backoff, và idempotency hoạt động. Thử token không hợp lệ để bảo đảm ứng dụng ghi cảnh báo thay vì tự bỏ qua lỗi.

**Bài 6 — Nhiều instance.** Khởi động hai bản consumer. Đo số event được mỗi bản xử lý, sau đó thêm lease phân phối để một instance duy nhất nắm quyền làm projector. Thử dừng instance đang giữ lease và đánh giá cơ chế chuyển giao.

**Bài 7 — Đo hiệu năng.** Với tập dữ liệu vài nghìn event và handler có latency khác nhau, so sánh số lượng event/giây, lag và RAM khi dùng `concatMap`, `flatMap(concurrency=4)` và `flatMap(concurrency=16)`. Đưa ra quyết định có căn cứ về độ song song có thể chấp nhận.

## 18. Checklist đưa vào production

Trước khi bật consumer lâu dài, xác nhận:

- [ ] MongoDB đang chạy replica set/sharded cluster, account đủ quyền `find` và `changeStream`.
- [ ] Collection, database, entity mapping và phiên bản Spring Data đúng thực tế.
- [ ] Mỗi logical consumer có ID và nguồn checkpoint riêng.
- [ ] Resume token được lưu **sau** side effect thành công, bảo toàn định dạng BSON.
- [ ] Side effect idempotent; các sự kiện `DELETE` và `UPDATE` thiếu full document được xử lý.
- [ ] Chính sách retry chỉ áp dụng với lỗi tạm thời và có cảnh báo khi token không còn hợp lệ.
- [ ] Đã giới hạn concurrency, tránh unbounded buffer và blocking trong reactive pipeline.
- [ ] Lifecycle của subscription được quản lý, có dispose khi shutdown và readiness/health phù hợp.
- [ ] Có chiến lược singleton consumer hoặc đa consumer có fencing/idempotency.
- [ ] Test integration trên replica set gồm restart, duplicate, update/delete và lỗi.
- [ ] Theo dõi lag, tốc độ xử lý, tuổi checkpoint, lỗi driver và thời gian giữ oplog.

## 19. Nguồn tham khảo

1. [Spring Data MongoDB Reference — Change Streams](https://docs.spring.io/spring-data/mongodb/reference/mongodb/change-streams.html): `ReactiveMongoTemplate.changeStream` và các cơ chế theo dõi thay đổi.
2. [Spring Data MongoDB — ReactiveMongoTemplate API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/ReactiveMongoTemplate.html): overload và kiểu dữ liệu trả về theo phiên bản.
3. [Spring Data MongoDB — ChangeStreamOptions API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/ChangeStreamOptions.html): filter và resume options.
4. [MongoDB Manual — Change Streams](https://www.mongodb.com/docs/manual/changeStreams/): topology, loại event, oplog và resume.
5. [MongoDB Manual — Resume a Change Stream](https://www.mongodb.com/docs/manual/changeStreams/#resume-a-change-stream): resume token, resumeAfter và giới hạn.
6. [Project Reactor — Flux](https://projectreactor.io/docs/core/release/reference/): subscription, demand, composition, concurrency và retry.
7. [Project Reactor — Testing](https://projectreactor.io/docs/core/release/reference/testing.html): `StepVerifier`, virtual time và kiểm thử publisher.

### Tự đánh giá

Bạn đã hiểu bài khi trả lời được: **vì sao không dùng `doOnNext(event -> save(...).subscribe())`; vì sao lưu resume token trước xử lý là nguy hiểm; tại sao `getBody()` có thể `null`; và điều gì xảy ra khi hai instance cùng subscribe một stream?** Khả năng vận hành Change Streams đáng tin cậy đến từ thiết kế toàn bộ vòng đời của `Flux` và tiến độ xử lý, không chỉ từ một lệnh `changeStream()`.
