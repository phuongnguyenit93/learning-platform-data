# Đánh giá thời gian giữ giao dịch và kết nối

Trong ứng dụng Spring Data Relational R2DBC, thời gian thực thi một câu SQL không phải là toàn bộ thời gian database connection bị chiếm dụng. Một connection có thể được giữ trong lúc chờ lấy kết nối từ pool, chạy nhiều câu lệnh, xử lý logic ứng dụng, chờ dịch vụ bên ngoài, stream kết quả hoặc commit/rollback transaction. Nếu chỉ đo thời gian query, ứng dụng có thể bỏ sót nguyên nhân khiến connection pool cạn và request phải chờ.

Để đánh giá hiệu năng đúng, cần tách ít nhất ba khoảng thời gian: thời gian chờ lấy connection, thời gian connection được mượn (connection hold/lease time) và thời gian transaction tồn tại. Đồng thời, cần đo thời gian từng câu SQL, thời gian xử lý giữa các câu lệnh, số connection đang dùng và số request đang chờ pool. Các số liệu này giúp xác định connection bị giữ lâu do database chậm, transaction quá rộng, xử lý ngoài database hoặc stream kéo dài.

## 1. Phân biệt các khoảng thời gian

Một request reactive có thể đi qua các mốc sau:

```text
T0  Publisher được subscribe
T1  Bắt đầu yêu cầu lấy connection từ pool
T2  Có connection được cấp cho thao tác
T3  Bắt đầu transaction (nếu có)
T4  Bắt đầu câu SQL thứ nhất
T5  Câu SQL thứ nhất hoàn tất
T6  Logic ứng dụng / câu SQL tiếp theo
T7  Commit hoặc rollback hoàn tất
T8  Connection được trả về pool
T9  Publisher phát terminal signal cho downstream
```

Tùy implementation và driver, một số mốc có thể rất gần nhau hoặc không quan sát trực tiếp được từ tầng ứng dụng. Tuy vậy, các khoảng thời gian khái niệm vẫn hữu ích:

| Chỉ số | Cách hiểu | Nó giúp trả lời câu hỏi nào? |
| --- | --- | --- |
| Pool acquisition time | T2 trừ T1 | Request phải chờ bao lâu để có connection? |
| Connection hold time | T8 trừ T2 | Connection bị giữ bao lâu trước khi trả về pool? |
| Transaction duration | T7 trừ T3 | Transaction tồn tại bao lâu từ lúc bắt đầu đến commit/rollback? |
| SQL execution time | Thời gian một statement từ lúc execute đến khi result hoàn tất | Database/driver xử lý câu lệnh mất bao lâu? |
| Application gap time | Khoảng giữa các statement hoặc giữa SQL và commit | Ứng dụng đang làm gì trong khi vẫn giữ transaction/connection? |
| End-to-end request time | T9 trừ T0 | Người dùng phải đợi bao lâu để nhận kết quả cuối? |

Không nên dùng một metric chung tên `database latency` để đại diện cho tất cả. Một query có thể chạy trong 10 ms nhưng transaction giữ connection 800 ms vì service chờ một HTTP call trước khi commit.

## 2. Connection acquisition time khác connection hold time

Với connection pool, ứng dụng không nhất thiết tạo một TCP/database connection mới cho mỗi request. Nó yêu cầu pool cấp một connection đã được tạo hoặc tạo mới theo cấu hình. Nếu pool hết connection rảnh, request phải chờ connection được trả về.

**Acquisition time** là thời gian từ lúc yêu cầu connection tới lúc pool cấp connection. Thời gian này tăng khi:

- Pool đã dùng hết số connection cho phép.
- Các connection đang được giữ quá lâu.
- Database chậm hoặc không nhận thêm kết nối.
- Tạo connection mới mất nhiều thời gian.
- Có nhiều request đồng thời hơn năng lực pool/database.

**Hold time** là thời gian từ lúc connection được cấp tới lúc được release. Hold time tăng khi:

- Transaction chứa nhiều thao tác hoặc logic ứng dụng kéo dài.
- Query stream có nhiều hàng và downstream tiêu thụ chậm.
- Ứng dụng gọi HTTP, broker hoặc filesystem trong transaction.
- Một publisher không hoàn tất hoặc không được hủy đúng cách.
- Connection được giữ thủ công mà cleanup không chạy đúng.

Hai chỉ số có quan hệ nhưng không thay thế nhau. Acquisition time cao thường là biểu hiện của pool contention; hold time cao thường là một nguyên nhân tạo contention.

## 3. Transaction duration không luôn bằng SQL duration

Một transaction có thể chạy nhiều statement:

```java
return transactionalOperator.transactional(
        orderRepository.save(order)
                .flatMap(saved -> inventoryRepository.reserve(
                        saved.getProductId(), saved.getQuantity()))
                .flatMap(reservation -> auditRepository.save(
                        AuditEntry.orderCreated(order.getId())))
                .thenReturn(order)
);
```

Nếu ba thao tác SQL lần lượt mất 20 ms, 30 ms và 10 ms, tổng thời gian SQL là khoảng 60 ms. Nhưng nếu pipeline còn chờ một dịch vụ ngoài 500 ms, transaction có thể tồn tại trên 560 ms hoặc lâu hơn. Connection được transaction manager giữ trong suốt transaction, vì vậy nó không được trả về pool sau câu SQL đầu tiên.

Transaction duration bao gồm thời gian:

- Bắt đầu transaction và thiết lập connection.
- Thực thi các câu SQL.
- Chờ kết quả của publisher phụ thuộc.
- Chạy logic Java giữa các thao tác.
- Chờ lock hoặc database scheduling.
- Commit/rollback và cleanup transaction.

SQL duration chỉ đo thời gian thực thi một câu lệnh hoặc một nhóm result cụ thể. Khi transaction duration lớn hơn nhiều tổng SQL duration, hãy tìm khoảng trống trong application pipeline và các thao tác đang chờ.

## 4. Vòng đời connection trong Spring Data R2DBC

Khi dùng Spring Data repository, `R2dbcEntityTemplate` hoặc `DatabaseClient`, Spring quản lý việc lấy và release connection theo lifecycle của thao tác. Khi không có transaction đang hoạt động, một thao tác thường lấy connection để thực thi rồi release sau khi result được tiêu thụ hoặc publisher kết thúc.

Khi có `R2dbcTransactionManager`, connection được lấy khi transaction bắt đầu và được gắn vào reactive transaction context. Các thao tác database tương thích trong cùng context sử dụng connection được quản lý. Connection được release khi transaction commit/rollback và quá trình cleanup hoàn tất.

Điều này có nghĩa một transaction kéo dài sẽ giữ connection lâu hơn một thao tác SQL đơn lẻ. Không nên giả định repository đã phát xong một entity thì connection chắc chắn được trả về pool nếu publisher vẫn còn nằm trong một transaction chưa kết thúc.

## 5. Reactive subscription quyết định thời điểm thực thi

Các publisher Reactor thường lazy: gọi repository method tạo publisher, còn việc truy cập database diễn ra khi publisher được subscribe. Vì vậy, không đo thời gian từ lúc gọi method và trả về `Mono`/`Flux` nếu muốn đo thời gian thực thi.

Ví dụ:

```java
Mono<Order> publisher = orderRepository.findById(orderId);
```

Đoạn code trên chưa nhất thiết lấy connection. Subscription mới kích hoạt thao tác:

```java
StepVerifier.create(publisher)
        .expectNextCount(1)
        .verifyComplete();
```

Trong ứng dụng, WebFlux hoặc một subscriber khác quản lý subscription. Nếu publisher được subscribe nhiều lần, query có thể được thực hiện nhiều lần và mỗi subscription có lifecycle riêng. Khi đo thời gian, đặt instrumentation bên trong `Mono.defer`/`Flux.defer` nếu cần bắt đầu đồng hồ cho từng subscription.

Không gọi `subscribe()` thủ công trong service chỉ để bắt đầu query. Việc đó tách công việc khỏi HTTP lifecycle, transaction context, cancellation và error handling của caller.

## 6. Đo end-to-end transaction duration bằng Micrometer

Có thể dùng Micrometer `Timer` để đo thời gian từ khi transaction publisher được subscribe tới khi transaction kết thúc. Đặt timer bên ngoài `TransactionalOperator` để đo cả phần thực thi và tín hiệu hoàn tất sau commit/rollback.

Ví dụ minh họa:

```java
public Mono<Order> createOrder(Order order) {
    return Mono.defer(() -> {
        Timer.Sample sample = Timer.start(meterRegistry);

        return transactionalOperator.transactional(
                        orderRepository.save(order)
                                .flatMap(saved -> auditRepository.save(
                                                AuditEntry.created(saved.getId()))
                                        .thenReturn(saved)))
                .doFinally(signal -> {
                    String outcome = switch (signal) {
                        case ON_COMPLETE -> "complete";
                        case ON_ERROR -> "error";
                        case CANCEL -> "cancel";
                        default -> "other";
                    };

                    sample.stop(meterRegistry.timer(
                            "app.r2dbc.transaction.duration",
                            "operation", "create-order",
                            "outcome", outcome));
                });
    });
}
```

`Mono.defer` tạo một `Timer.Sample` cho mỗi subscription. `doFinally` ở ngoài publisher do `transactionalOperator.transactional(...)` trả về quan sát terminal signal sau khi transaction operator xử lý hoàn tất, lỗi hoặc cancellation. Tên metric và tag trong ví dụ là metric ứng dụng tự định nghĩa, không phải tên metric mặc định của Spring Boot.

Không đưa order ID, email, tenant ID tùy ý hoặc SQL đầy đủ vào metric tag vì cardinality có thể tăng không giới hạn và làm lộ dữ liệu. Dùng các nhãn có tập giá trị nhỏ như operation, outcome và datasource label đã được kiểm soát.

Nếu service dùng `@Transactional`, có thể đặt instrumentation trong method quanh publisher trả về, nhưng cần bảo đảm nó đo subscription chứ không chỉ đo thời gian tạo publisher. Khi cần đo chính xác ranh giới transaction, `TransactionalOperator` tường minh thường dễ đặt metric hơn.

## 7. Phân biệt thời gian trong transaction với thời gian bên ngoài transaction

Có thể đo riêng phần thân công việc và toàn bộ transaction:

```java
public Mono<Order> createOrder(Order order) {
    return Mono.defer(() -> {
        Timer.Sample transactionSample = Timer.start(meterRegistry);

        Mono<Order> work = Mono.defer(() -> {
            Timer.Sample workSample = Timer.start(meterRegistry);

            return orderRepository.save(order)
                    .flatMap(saved -> auditRepository.save(
                                    AuditEntry.created(saved.getId()))
                            .thenReturn(saved))
                    .doFinally(signal -> workSample.stop(
                            meterRegistry.timer("app.r2dbc.transaction.work")));
        });

        return transactionalOperator.transactional(work)
                .doFinally(signal -> transactionSample.stop(
                        meterRegistry.timer("app.r2dbc.transaction.total")));
    });
}
```

Metric `work` ở trong transaction đo thời gian publisher nghiệp vụ; metric `total` ở ngoài đo thời gian transaction boundary hoàn tất. Chênh lệch có thể phản ánh begin/commit/rollback và cleanup, nhưng không phải phép đo tuyệt đối của connection lease. Muốn biết connection thực sự được release khi nào, cần quan sát pool hoặc instrument connection lifecycle.

Không đặt `doFinally` chỉ quanh lời gọi tạo publisher:

```java
Mono<Order> wrongMeasurement = orderRepository.save(order)
        .doFinally(signal -> recordDuration());
```

Đoạn trên chỉ hữu ích nếu timer bắt đầu tương ứng trong cùng subscription. Nếu timer bắt đầu ở thời điểm method được gọi và publisher được subscribe muộn, kết quả sẽ bao gồm thời gian chờ trước subscription và có thể bị sai lệch.

## 8. Đo thời gian từng câu SQL

Transaction duration không cho biết statement nào chậm. Cần đo query latency theo loại thao tác, repository/query name hoặc datasource. Có thể dùng:

- Micrometer observation/tracing tích hợp với Spring Framework và driver nếu phiên bản hỗ trợ.
- Log SQL và thời gian thực thi ở driver/database, với chính sách che dữ liệu nhạy cảm.
- Database query statistics như `pg_stat_statements` trên PostgreSQL.
- Custom instrumentation quanh `DatabaseClient` hoặc repository method cho các query quan trọng.
- Tracing span để liên kết request, transaction và statement.

Một query metric nên ghi nhận thời gian từ lúc statement được thực thi tới khi result hoàn tất hoặc bị hủy, không chỉ tới lúc nhận row đầu tiên nếu mục tiêu là đo toàn bộ query stream.

Với query trả nhiều hàng, nên tách:

- Time to first row: thời gian tới khi nhận hàng đầu tiên.
- Result consumption duration: thời gian tiêu thụ toàn bộ result.
- Rows emitted: số hàng đã phát.
- Cancellation outcome: result bị hủy trước khi hoàn tất hay không.

Query trả 100.000 hàng có thể có time-to-first-row thấp nhưng result consumption kéo dài. Nếu chỉ đo tới hàng đầu, metric sẽ đánh giá thấp thời gian connection bị giữ.

## 9. Connection pool metrics cho biết áp lực sử dụng

Nếu dùng `r2dbc-pool`, pool có thể cung cấp các metric như số connection đang được mượn, số connection được cấp phát, số connection idle và số request đang pending. Tên metric và cách đăng ký phụ thuộc phiên bản R2DBC Pool, Spring Boot và cấu hình Micrometer.

Những đại lượng thường cần theo dõi:

| Đại lượng | Cách diễn giải |
| --- | --- |
| Acquired/borrowed | Số connection hiện đang được ứng dụng mượn |
| Allocated | Số connection vật lý đã được tạo trong pool |
| Idle | Số connection sẵn sàng được mượn |
| Pending | Số yêu cầu đang chờ pool cấp connection |
| Maximum allocated/acquired | Giới hạn pool hoặc mức sử dụng cực đại được báo cáo |
| Acquire timeout count | Số lần không lấy được connection trong thời hạn cấu hình, nếu có instrumentation |

Với Spring Boot Actuator, có thể khám phá các metric đang được đăng ký qua endpoint `/actuator/metrics` nếu endpoint được bật và bảo vệ phù hợp. Không giả định tên hoặc tag giống hệt giữa mọi phiên bản; hãy xem danh sách metric thực tế trong ứng dụng.

Pool gauge phản ánh số lượng tại một thời điểm. `acquired` cao không trực tiếp cho biết một connection cụ thể đã bị giữ bao lâu. Muốn đo hold-time distribution, cần instrumentation quanh acquire/release hoặc observation phù hợp của pool/driver.

## 10. Không nhầm `max-acquire-time` với connection hold time

R2DBC Pool có thể cấu hình giới hạn thời gian chờ lấy connection, ví dụ:

```yaml
spring:
  r2dbc:
    pool:
      enabled: true
      initial-size: 5
      max-size: 30
      max-acquire-time: 2s
      max-create-connection-time: 3s
      max-idle-time: 20m
      max-life-time: 60m
```

Các thuộc tính cụ thể và format duration phụ thuộc phiên bản Spring Boot/R2DBC Pool. `max-acquire-time` giới hạn thời gian chờ pool cấp connection. Nó không giới hạn thời gian ứng dụng giữ connection sau khi đã được cấp.

Các khái niệm khác:

- `max-create-connection-time`: giới hạn thời gian tạo connection mới.
- `max-idle-time`: giới hạn thời gian connection nằm idle trong pool theo cấu hình pool.
- `max-life-time`: giới hạn tuổi thọ vật lý của connection trong pool.
- `max-acquire-time`: giới hạn thời gian request chờ mượn connection.

Không dùng `max-life-time` như một cơ chế timeout transaction. Một connection có tuổi thọ vật lý dài vẫn có thể được mượn/trả nhiều lần; hold time của một lần mượn là khoảng khác.

## 11. Dùng `EXPLAIN` và thống kê database đúng mục đích

Database statistics giúp tìm query chậm, lock và mức tải server. Ví dụ PostgreSQL có `EXPLAIN (ANALYZE, BUFFERS)` để xem execution plan và thời gian thực thi trên dữ liệu thực tế. `pg_stat_activity` cho biết session/query đang hoạt động; `pg_stat_statements` tổng hợp thống kê theo query fingerprint nếu extension được bật.

Những công cụ này đo phía database, không tự cho biết connection đã bị ứng dụng giữ bao lâu trước/sau query. Hãy ghép dữ liệu database với metric pool và tracing ứng dụng.

Ví dụ một transaction giữ connection 2 giây nhưng SQL chỉ chạy 40 ms. Database query statistics có thể cho thấy câu SQL nhanh; trace ứng dụng mới cho thấy service chờ một API thanh toán 1,8 giây trong transaction. Hai góc nhìn bổ sung cho nhau.

Không bật `EXPLAIN ANALYZE` tùy tiện cho mọi query production vì nó thực thi query và có overhead. Dùng có kiểm soát trên query đại diện hoặc môi trường phù hợp.

## 12. Nhận diện transaction quá rộng

Một transaction nên bao phủ các thay đổi database cần cùng commit/rollback. Không nên mở transaction từ đầu một workflow rồi giữ nó trong lúc làm các việc không cần atomic với database.

Ví dụ transaction quá rộng:

```java
@Transactional
public Mono<Order> placeOrder(OrderCommand command) {
    return orderRepository.save(Order.pending(command))
            .flatMap(saved -> paymentClient.authorize(command.payment()))
            .flatMap(payment -> inventoryClient.reserve(command.items()))
            .flatMap(result -> orderRepository.markConfirmed(command.orderId()));
}
```

Nếu payment hoặc inventory service mất 2 giây, connection database có thể bị giữ trong suốt thời gian chờ đó. Các service bên ngoài cũng không tham gia transaction R2DBC, nên giữ connection không tạo ra atomicity xuyên hệ thống.

Thiết kế thường tốt hơn là:

1. Transaction ngắn: tạo order `PENDING` và ghi outbox command.
2. Commit và trả connection về pool.
3. Worker xử lý payment/inventory bên ngoài transaction database.
4. Mỗi kết quả được ghi bằng transaction ngắn riêng.
5. Chuyển order sang trạng thái cuối hoặc chạy compensation khi một bước thất bại.

Transactional Outbox/Saga giúp giữ trạng thái bền vững mà không giữ một connection trong lúc chờ dịch vụ khác.

## 13. Không thực hiện network call trong transaction nếu không cần thiết

Đoạn code sau làm connection bị giữ trong lúc HTTP call:

```java
return transactionalOperator.transactional(
        customerRepository.save(customer)
                .flatMap(saved -> profileClient.refresh(saved.getId())
                        .thenReturn(saved)));
```

Nếu việc refresh profile không cần cùng atomicity với insert customer, hãy tách nó khỏi transaction:

```java
return transactionalOperator.transactional(
                customerRepository.save(customer))
        .flatMap(saved -> profileClient.refresh(saved.getId())
                .thenReturn(saved));
```

Trong cách thứ hai, transaction insert hoàn tất trước khi gọi HTTP. Tuy nhiên, nếu HTTP call thất bại, customer đã được lưu. Nếu nghiệp vụ cần bảo đảm việc refresh được thực hiện, ghi một outbox event cùng transaction rồi xử lý bất đồng bộ thay vì dựa vào một HTTP call đồng bộ sau commit.

Không tách transaction chỉ vì muốn giảm hold time nếu điều đó phá vỡ bất biến nghiệp vụ. Hãy xác định rõ phần nào cần atomic và phần nào có thể eventual consistency.

## 14. Query streaming có thể giữ connection lâu

Một `Flux<T>` từ repository có thể phát dữ liệu dần. Connection cần được giữ đủ lâu để driver tiêu thụ result và hoàn tất query. Nếu endpoint HTTP stream dữ liệu cho client chậm, backpressure có thể làm việc tiêu thụ kéo dài; connection có thể tiếp tục bị giữ trong khoảng đó.

Ví dụ:

```java
@GetMapping(value = "/orders/export", produces = MediaType.APPLICATION_NDJSON_VALUE)
public Flux<OrderLine> export() {
    return orderRepository.findAll()
            .map(OrderLine::from);
}
```

Đây có thể là streaming HTTP, nhưng một query lớn có thể giữ connection trong suốt quá trình client đọc. Nếu endpoint còn nằm trong một transaction reactive, transaction cũng có thể kéo dài tới khi stream hoàn tất hoặc bị hủy.

Với export lớn, cân nhắc:

- Giới hạn số hàng và thời gian stream.
- Dùng keyset pagination theo từng batch nhỏ để query và release connection giữa các batch.
- Không bao toàn bộ HTTP stream trong một transaction dài nếu không có yêu cầu snapshot cụ thể.
- Tạo file export nền rồi cho client tải sau nếu dữ liệu rất lớn.
- Xử lý cancellation khi client disconnect và xác minh driver dừng result đúng cách.

Không giả định `Flux` tự động làm connection được trả về sau mỗi hàng. Connection thường cần tồn tại trong khi result của statement còn được tiêu thụ.

## 15. Dùng keyset pagination để giảm thời gian giữ connection

Với danh sách lớn, một query stream có thể giữ connection lâu. Keyset pagination chia công việc thành các query hữu hạn:

```sql
SELECT id, created_at, total
FROM orders
WHERE (created_at, id) < (:lastCreatedAt, :lastId)
ORDER BY created_at DESC, id DESC
LIMIT :pageSize;
```

Ứng dụng lấy một trang, xử lý và hoàn tất query; sau đó mới lấy trang kế tiếp. Khi không giữ transaction xuyên suốt toàn bộ export, connection có thể được trả về pool giữa các trang.

Điều này giảm thời gian giữ connection liên tục nhưng thay đổi semantics nhất quán: các trang có thể nhìn thấy dữ liệu ở những thời điểm khác nhau. Nếu cần snapshot cố định, phải thiết kế cutoff/version hoặc cơ chế snapshot khác. Không giữ một transaction mở nhiều phút chỉ để có snapshot nếu điều đó làm cạn pool; hãy đánh giá trade-off và mô hình dữ liệu.

## 16. Tránh concurrency quá cao trên cùng transaction connection

Một transaction R2DBC thường gắn với một connection. Việc dùng `flatMap` concurrency cao để chạy nhiều statement đồng thời trên cùng connection không nhất thiết tăng throughput; driver/database có thể tuần tự hóa hoặc không hỗ trợ các thao tác concurrent theo cách mong muốn.

Ví dụ cần thận trọng:

```java
return transactionalOperator.transactional(
        Flux.fromIterable(commands)
                .flatMap(repository::save, 32));
```

Đoạn này yêu cầu nhiều publisher con đồng thời trong cùng transaction context. Nếu chúng dùng cùng connection transaction-bound, việc thực thi concurrent có thể không hiệu quả hoặc tạo hành vi phụ thuộc driver.

Khi các thao tác cần thứ tự, dùng `concatMap`:

```java
return transactionalOperator.transactional(
        Flux.fromIterable(commands)
                .concatMap(repository::save)
                .then());
```

Nếu cần song song hóa, chia thành các transaction độc lập có concurrency được giới hạn rõ ràng và xác định trước semantics khi một chunk thất bại. Không tăng concurrency vô hạn để bù cho query chậm hoặc pool nhỏ.

## 17. Transaction timeout và query timeout không giống nhau

Transaction timeout, statement/query timeout, pool acquire timeout và HTTP timeout có phạm vi khác nhau:

| Timeout | Phạm vi |
| --- | --- |
| Pool acquire timeout | Thời gian chờ lấy connection |
| Connection creation timeout | Thời gian tạo connection vật lý |
| Statement/query timeout | Thời gian thực thi một câu SQL, nếu driver/database hỗ trợ |
| Transaction timeout | Thời gian cho transaction theo khả năng transaction manager/driver |
| Reactor `.timeout(...)` | Thời gian publisher được phép chạy trước khi phát timeout error/cancel upstream |
| HTTP/proxy timeout | Thời gian request/response hoặc khoảng idle trên đường truyền |

Không giả định Reactor `.timeout` luôn hủy câu SQL ngay lập tức. Nó phát lỗi/cancellation ở pipeline; khả năng dừng statement phụ thuộc driver và database. Tương tự, timeout ở proxy không nhất thiết rollback một transaction đã commit.

Chọn timeout theo mục tiêu và xác minh bằng integration test. Nếu timeout xảy ra khi commit, client có thể không biết chắc database đã commit hay chưa; thao tác có thể retry cần idempotency key hoặc business key duy nhất.

## 18. Dấu hiệu chẩn đoán từ các metric kết hợp

Đọc các metric cùng nhau giúp khoanh vùng nhanh hơn:

| Quan sát | Khả năng cần kiểm tra |
| --- | --- |
| Acquisition time tăng, pending tăng, acquired gần max | Pool bị bão hòa; kiểm tra hold time, concurrency và max size |
| Hold time tăng, SQL latency ổn định/thấp | Transaction rộng, network call hoặc logic ứng dụng đang giữ connection |
| Transaction duration tăng và SQL latency cũng tăng | Query plan, lock contention, database load hoặc network tới database |
| Time-to-first-row thấp nhưng result duration rất cao | Result lớn, client/downstream chậm hoặc fetch/encode kéo dài |
| Pool acquired cao nhưng request throughput không tăng | Connection bị giữ lâu, query bị khóa hoặc concurrency không hiệu quả |
| Acquire timeout xuất hiện khi database CPU thấp | Connection pool có thể nhỏ, connection bị leak/giữ lâu hoặc workload bị giới hạn ở tầng ứng dụng |
| Database query nhanh nhưng HTTP response chậm | Encode, proxy buffering, client chậm hoặc logic sau query |
| Transaction duration cao hơn tổng SQL duration nhiều | Khoảng chờ trong application pipeline hoặc công việc ngoài database |
| Cancel tăng cùng connection hold time | Client disconnect hoặc stream dài; kiểm tra cleanup và driver cancellation |

Đây là các giả thuyết chẩn đoán, không phải kết luận tự động. Hãy đối chiếu trace, log và database activity trước khi thay đổi pool hoặc transaction design.

## 19. Dùng tracing để tìm khoảng thời gian connection bị giữ

Distributed tracing có thể biểu diễn request thành các span:

```text
HTTP POST /orders                 950 ms
  R2DBC transaction create-order  900 ms
    INSERT order                   18 ms
    SELECT inventory               12 ms
    HTTP payment authorize        820 ms
    UPDATE order                    9 ms
    COMMIT                         25 ms
```

Trace cho thấy SQL chỉ chiếm một phần nhỏ; HTTP payment call nằm trong transaction là nguyên nhân chính khiến transaction kéo dài. Khi đưa payment ra khỏi transaction hoặc chuyển sang outbox/saga, connection có thể được release sớm hơn.

Span nên có tên operation ổn định và tag an toàn như datasource label, outcome, transaction type. Không gắn raw SQL parameter, thông tin khách hàng hoặc token vào span. Dùng trace ID để liên kết với log và metric.

Nếu instrumentation chỉ tạo span cho query mà không tạo span cho transaction, khoảng trống giữa các query khó quan sát. Có thể bổ sung span/Timer ở service transaction boundary cho các use case quan trọng.

## 20. Đo connection hold time chính xác hơn

Pool gauge cho biết số connection đang được mượn nhưng không nhất thiết ghi lại thời điểm từng connection được acquire/release. Nếu cần phân phối hold time p50/p95/p99, cần instrumentation ở ranh giới lease.

Các lựa chọn:

- Dùng metric/observation của R2DBC Pool hoặc thư viện instrumentation nếu phiên bản đang dùng cung cấp thời gian acquire/release.
- Bọc `ConnectionFactory` bằng decorator để ghi timestamp khi `create()` phát connection và khi `Connection.close()` được gọi.
- Dùng tracing/driver instrumentation có span cho acquire và release.
- Với code SPI tự quản lý connection, đo trực tiếp quanh `ConnectionFactory.create()` và `Connection.close()`.

Khi viết decorator, phải bảo toàn đầy đủ semantics của SPI: transaction, metadata, statement, batch, validation, close, cancellation và lỗi. Không chỉ bọc `close()` sơ sài rồi làm mất các interface hoặc method khác của `Connection`. Nếu không có nhu cầu rõ ràng, ưu tiên metric tích hợp của pool/driver.

Ví dụ khái niệm cho code tự quản lý connection bằng SPI:

```java
Mono.usingWhen(
        Mono.defer(() -> {
            long acquireStarted = System.nanoTime();
            return Mono.from(connectionFactory.create())
                    .doOnNext(connection ->
                            metrics.recordAcquireTime(
                                    System.nanoTime() - acquireStarted));
        }),
        connection -> executeWork(connection),
        connection -> Mono.from(connection.close())
                .doFinally(signal -> metrics.recordRelease(signal)),
        (connection, error) -> Mono.from(connection.close())
                .doFinally(signal -> metrics.recordRelease(signal)),
        connection -> Mono.from(connection.close())
                .doFinally(signal -> metrics.recordRelease(signal))
);
```

Đây chỉ là khung minh họa; để đo hold time cần lưu thời điểm acquire trong resource wrapper cùng connection, rồi tính hiệu khi close hoàn tất. Với `DatabaseClient`/repository, Spring quản lý acquire/release nên không tự bọc connection ở service. Cần decorator ở `ConnectionFactory` hoặc instrumentation cấp pool để đo chính xác mà vẫn giữ nguyên lifecycle.

## 21. Tách thời gian tạo connection khỏi thời gian chờ pool

Khi pool không còn connection idle, nó có thể tạo connection mới nếu chưa đạt max size. Acquisition time có thể gồm cả thời gian chờ connection sẵn có và thời gian tạo kết nối mới.

Nên phân biệt:

- Pool wait: thời gian đợi connection được trả lại hoặc có slot.
- Connection creation: thời gian mở kết nối vật lý, xác thực và thiết lập session.
- Validation: thời gian kiểm tra connection trước khi cấp, nếu pool thực hiện.
- Lease duration: thời gian ứng dụng giữ connection sau khi được cấp.

Nếu connection creation chậm, kiểm tra DNS, TLS, database connection limit, network và xác thực. Nếu pool wait cao nhưng creation time thấp, kiểm tra hold time và pool capacity. Không tăng `max-size` khi database đã chạm giới hạn connection hoặc CPU; việc mở thêm connection có thể làm contention tệ hơn.

## 22. Ước lượng nhu cầu pool bằng throughput và hold time

Một ước lượng đơn giản từ Little's Law:

\[
N \approx \lambda \times W
\]

Trong đó:

- (N) là số connection trung bình đang được mượn.
- (lambda) là tốc độ thao tác cần connection (lần/giây).
- (W) là thời gian giữ connection trung bình (giây).

Ví dụ, nếu hệ thống cần 80 transaction mỗi giây và mỗi transaction giữ connection trung bình 0,25 giây:

\[
N \approx 80 \times 0.25 = 20
\]

Khoảng 20 connection là mức sử dụng trung bình theo giả định đó, chưa phải cấu hình max-size. Cần thêm headroom cho burst, tail latency, tác vụ nền và các query khác. Dùng p95/p99 hold time để hiểu các đợt chiếm dụng dài, đồng thời kiểm tra giới hạn database.

Nếu có 8 instance ứng dụng, mỗi instance cấu hình pool max-size 30, tổng số connection lý thuyết có thể lên tới 240, chưa kể job, migration và công cụ vận hành. Pool size phải được tính trên toàn hệ thống, không chỉ trên một pod.

Đây là ước lượng ban đầu, không thay thế load test. Connection pool lớn hơn không luôn làm throughput tăng; database có thể xử lý tốt hơn với ít connection hoạt động và ít lock contention hơn.

## 23. Tránh giữ connection trong khi chờ client

Một transaction reactive không nên bao trùm việc chờ người dùng, HTTP request khác hoặc một stream vô hạn. Ví dụ:

```java
return transactionalOperator.transactional(
        orderRepository.findById(orderId)
                .flatMap(order -> confirmationGateway.waitForUser(order)
                        .flatMap(confirmed -> orderRepository.save(
                                order.withConfirmed(confirmed)))));
```

Nếu `waitForUser` mất vài phút, transaction và connection có thể bị giữ trong toàn bộ thời gian đó. Thiết kế nên lưu trạng thái chờ trong transaction ngắn, kết thúc transaction, rồi xử lý callback/user confirmation bằng một request mới và transaction ngắn khác.

Transaction bảo vệ một chuỗi thao tác database cần atomicity; nó không phải nơi giữ workflow đang chờ một tác nhân bên ngoài.

## 24. Tác động của lock và transaction dài

Transaction dài có thể giữ lock hoặc snapshot lâu tùy database, isolation level và loại thao tác. Hệ quả có thể gồm:

- Transaction khác phải chờ lock.
- Deadlock dễ xảy ra hơn khi nhiều transaction giữ lock lâu và theo thứ tự khác nhau.
- Database phải giữ phiên bản row cũ lâu hơn trong các hệ thống MVCC.
- Cleanup/vacuum hoặc quản lý transaction ID có thể bị ảnh hưởng tùy database.
- Connection pool bị chiếm dụng lâu hơn, làm request khác chờ.

Không phải mọi transaction dài đều giữ lock trên mọi row; read/write mode, isolation và database engine quyết định chi tiết. Tuy nhiên, transaction dài làm tăng khoảng thời gian tài nguyên và snapshot có thể bị giữ, vì vậy cần theo dõi `idle in transaction`, lock wait và transaction age ở database khi có dấu hiệu.

## 25. Phân biệt `idle in transaction` với connection idle trong pool

Hai trạng thái này rất khác nhau:

- **Idle connection trong pool:** connection không được ứng dụng mượn và sẵn sàng cấp cho request khác.
- **Idle in transaction:** session database vẫn nằm trong transaction nhưng hiện không thực thi câu lệnh; ứng dụng có thể đang chờ một publisher khác hoặc logic bên ngoài.

Một connection ở trạng thái `idle in transaction` vẫn bị giữ bởi transaction và không thể được pool cấp cho request khác. Trên PostgreSQL, có thể quan sát session qua `pg_stat_activity` và trạng thái `idle in transaction`.

Nếu thấy nhiều session idle in transaction với thời gian dài, tìm các khoảng chờ giữa SQL trong service, HTTP call trong transaction, publisher không hoàn tất hoặc luồng response chậm. Đừng nhầm chúng với connection idle sẵn sàng trong pool.

## 26. Kiểm soát connection leak và cleanup

Khi dùng repository/`DatabaseClient`, Spring quản lý connection theo lifecycle. Khi dùng R2DBC SPI trực tiếp, ứng dụng chịu trách nhiệm release connection đúng cách.

Ví dụ quản lý resource bằng `usingWhen`:

```java
public Mono<Void> runDirectStatement() {
    return Mono.usingWhen(
            Mono.from(connectionFactory.create()),
            connection -> {
                Statement statement = connection.createStatement(
                        "DELETE FROM expired_token WHERE expires_at < CURRENT_TIMESTAMP");

                return Flux.from(statement.execute())
                        .concatMap(result -> Flux.from(result.getRowsUpdated()))
                        .then();
            },
            connection -> Mono.from(connection.close()),
            (connection, error) -> Mono.from(connection.close()),
            connection -> Mono.from(connection.close())
    );
}
```

`usingWhen` xác định cleanup cho hoàn tất, lỗi và cancellation. Không lấy connection trực tiếp rồi quên gọi `close()`. Không đóng connection đang được Spring transaction manager quản lý bằng cách tự ý gọi close ở giữa transaction.

Nếu pool có metric acquired tăng liên tục nhưng không giảm sau khi request hoàn tất, kiểm tra code SPI trực tiếp, publisher không được subscribe/không kết thúc, cleanup callback và driver. Một connection bị giữ lâu không nhất thiết là leak; cần phân biệt hold time dài hợp lệ với connection không bao giờ được release.

## 27. Cancellation và thời gian release

Khi subscriber hủy publisher, Spring/driver có thể hủy statement và release connection theo lifecycle. Tuy nhiên, cancellation là tín hiệu bất đồng bộ; việc dừng query vật lý và hoàn tất cleanup có thể không tức thời.

Với HTTP stream, client có thể đóng socket. WebFlux hủy subscription, nhưng database driver có thể cần thời gian để dừng result. Hãy đo thời gian từ cancellation tới lúc connection trở về pool nếu endpoint thường bị client ngắt giữa chừng.

Không dùng `doOnCancel` như cơ chế release connection nếu Spring hoặc `usingWhen` đã quản lý resource. Callback này chỉ nên dùng để ghi nhận metric/log hoặc hủy resource riêng do ứng dụng sở hữu.

## 28. Tối ưu sau khi xác định nguyên nhân

Chọn cách sửa theo metric và trace:

| Nguyên nhân được xác nhận | Hướng cải thiện |
| --- | --- |
| Query chậm do scan/sort | Tối ưu SQL, index, filter, projection và execution plan |
| Lock wait cao | Rút ngắn transaction, chuẩn hóa thứ tự lock, giảm contention |
| Transaction chứa HTTP call | Đưa call ra ngoài transaction hoặc dùng outbox/saga |
| Query stream quá lớn | Giới hạn dữ liệu, keyset pagination, export nền |
| Pool acquisition cao vì hold time dài | Rút ngắn connection lease và transaction trước khi tăng pool |
| Pool quá nhỏ nhưng database còn dư năng lực | Điều chỉnh max-size sau load test và tính tổng pool trên mọi instance |
| Connection creation chậm | Dùng pool phù hợp, kiểm tra network/TLS/credentials và database limit |
| Publisher không kết thúc/cancel cleanup chậm | Sửa pipeline, timeout/cancellation và resource lifecycle |
| `flatMap` concurrency quá cao | Giới hạn concurrency hoặc tuần tự hóa thao tác cùng connection |
| Chỉ một vài endpoint giữ connection lâu | Tách use case, query hoặc transaction boundary riêng |

Không tăng pool size để che một transaction đang giữ connection vài giây. Điều đó có thể chỉ chuyển vấn đề từ pool sang database và làm tăng tổng số session.

## 29. Kiểm thử và load test thời gian giữ connection

Một test chức năng chỉ xác minh kết quả đúng chưa đủ để đánh giá hold time. Có thể kết hợp:

1. Unit test service để xác minh publisher không gọi dịch vụ ngoài bên trong transaction boundary.
2. Integration test với R2DBC driver thật để xác minh commit/rollback và cleanup.
3. Test cancellation để xác minh connection được release khi client/subscriber hủy.
4. Load test có nhiều request đồng thời để quan sát acquired, idle, pending và acquisition latency.
5. Test query stream lớn với client nhanh và client chậm để đo connection hold time.
6. Trace các transaction dài và so sánh tổng SQL duration với transaction duration.
7. Kiểm tra database session/lock để phát hiện `idle in transaction`.

Ví dụ dùng `StepVerifier` để xác minh publisher kết thúc:

```java
StepVerifier.create(orderService.createOrder(command))
        .expectNextMatches(order -> order.getId() != null)
        .verifyComplete();
```

Test này xác minh publisher hoàn tất bình thường; metric/trace hoặc instrumentation pool mới cho biết connection được release khi nào. Không dùng `Thread.sleep` để suy đoán connection đã được trả về. Nếu cần kiểm tra pool, đọc metric hoặc dùng một thao tác thứ hai có kiểm soát sau khi publisher hoàn tất.

Trong load test, tăng concurrency từng bước và quan sát throughput, p95/p99 latency, pool pending, database CPU/locks và lỗi timeout. Khi throughput không tăng nhưng pending tăng, hệ thống có thể đã chạm giới hạn database hoặc connection lease.

## 30. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Chỉ đo thời gian SQL | Bỏ qua thời gian connection bị giữ giữa các query | Đo transaction duration và connection hold time riêng |
| Đo từ lúc gọi repository method | Publisher có thể chưa được subscribe | Bắt đầu timer trong `defer` tại subscription |
| Nhầm acquisition time với hold time | Sửa sai nguyên nhân pool contention | Đo thời gian chờ cấp connection và thời gian mượn riêng |
| Cho rằng transaction duration bằng query duration | Bỏ sót HTTP call, lock wait và logic ứng dụng | So sánh transaction span với các SQL span |
| Tăng pool max-size ngay khi pending tăng | Có thể làm database quá tải hơn | Kiểm tra hold time, query, concurrency và giới hạn DB trước |
| Dùng `max-acquire-time` như timeout giữ connection | Connection có thể vẫn bị giữ lâu sau khi cấp | Thiết kế timeout transaction/query và rút ngắn hold time |
| Gọi HTTP trong transaction | Giữ connection khi chờ network | Tách transaction hoặc dùng outbox/saga |
| Stream vô hạn trong transaction | Connection bị giữ không giới hạn | Không bao event stream bằng transaction dài |
| Gọi `collectList()` trên dữ liệu lớn | Tăng memory và giữ query/result lâu | Xử lý theo Flux hoặc keyset batch |
| `flatMap` concurrency cao trong cùng transaction | Tranh chấp trên một connection hoặc driver behavior khó đoán | Dùng `concatMap` hoặc transaction độc lập có giới hạn |
| Đo `acquired` gauge như hold duration | Gauge không cho biết tuổi của từng lease | Dùng acquire/release instrumentation hoặc tracing |
| Bọc connection thủ công nhưng không cleanup khi cancel | Connection leak | Dùng `usingWhen` hoặc decorator giữ đủ lifecycle |
| Dùng `doOnCancel` thay cho release | Resource có thể không được đóng đúng | Để Spring/usingWhen quản lý cleanup |
| Đo publisher creation thay vì subscription | Metric không phản ánh thời gian thực thi | Dùng `Mono.defer`/`Flux.defer` và timer theo subscription |

## 31. Quy trình đánh giá một endpoint R2DBC

Khi một endpoint có latency cao hoặc pool pending tăng, thực hiện theo trình tự:

1. Ghi nhận end-to-end request latency và throughput theo endpoint.
2. Đo pool acquisition time, số acquired/idle/pending và acquire timeout.
3. Đo transaction duration từ subscription tới commit/rollback hoàn tất.
4. Đo connection hold time nếu pool/driver instrumentation hỗ trợ; nếu không, bổ sung acquire/release tracing.
5. Đo từng SQL span, time-to-first-row và result consumption duration.
6. So sánh tổng SQL time với transaction duration để tìm khoảng chờ trong ứng dụng.
7. Kiểm tra network call, scheduler, `collectList`, stream dài, `flatMap` concurrency và publisher không hoàn tất.
8. Kiểm tra database query plan, lock wait và session `idle in transaction`.
9. Thay đổi transaction boundary, query, pagination hoặc pool theo nguyên nhân đã xác nhận.
10. Load test lại và so sánh p50/p95/p99, throughput, pending, connection count và database load.

## 32. Nguyên tắc thực hành

- Phân biệt pool acquisition time, connection hold time, transaction duration, SQL duration và request latency.
- Bắt đầu đo reactive work khi publisher được subscribe, không chỉ khi method được gọi.
- Đo transaction ở ngoài `TransactionalOperator` để bao gồm commit/rollback và cleanup boundary.
- Đo SQL riêng và so sánh với transaction duration để tìm thời gian ứng dụng chờ giữa các query.
- Theo dõi pool acquired/allocated/idle/pending; nhớ rằng gauge không trực tiếp đo hold time.
- Kiểm tra tên metric và tag thực tế của R2DBC Pool/Spring Boot thay vì giả định giống mọi phiên bản.
- Không nhầm `max-acquire-time`, `max-idle-time` hoặc `max-life-time` với giới hạn transaction/lease.
- Không gọi dịch vụ ngoài hoặc chờ người dùng trong transaction database nếu không cần atomicity.
- Tránh giữ transaction/connection trong HTTP stream dài hoặc export không giới hạn.
- Dùng keyset pagination/batch hữu hạn khi phù hợp và chấp nhận rõ semantics nhất quán.
- Giới hạn concurrency, prefetch và buffer; tránh nhiều statement cạnh tranh trên cùng transaction connection.
- Dùng `usingWhen` cho connection lấy trực tiếp qua SPI và cleanup ở complete/error/cancel.
- Xem xét lock wait, `idle in transaction`, query plan và connection creation cùng metric ứng dụng.
- Tính pool size trên tổng số instance và giới hạn database; không tăng pool để che hold time cao.
- Kiểm thử commit, rollback, cancellation và load bằng driver/database tương thích production.

## 33. Kết luận

Đánh giá hiệu năng R2DBC cần phân biệt thời gian chờ lấy connection, thời gian connection được giữ, thời gian transaction tồn tại và thời gian từng câu SQL. Pool acquisition cao cho thấy request đang chờ connection; hold time cao cho thấy connection được mượn lâu; transaction duration cao hơn tổng SQL duration thường chỉ ra khoảng chờ hoặc logic ứng dụng nằm bên trong transaction.

Hãy đo theo subscription reactive, kết hợp Micrometer/tracing với metric pool và thống kê database. Transaction reactive giữ connection cho tới khi commit/rollback và cleanup hoàn tất; vì vậy, network call, user wait, HTTP streaming dài hoặc publisher không kết thúc có thể làm pool cạn dù query riêng lẻ rất nhanh. Rút ngắn transaction, giới hạn result/concurrency, dùng pagination khi phù hợp và điều chỉnh pool dựa trên số liệu thực tế sẽ cải thiện throughput mà không chuyển áp lực không cần thiết sang database.
