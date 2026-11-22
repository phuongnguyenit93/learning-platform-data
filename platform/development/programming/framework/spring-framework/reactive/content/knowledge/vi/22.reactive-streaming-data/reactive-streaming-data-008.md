# Ngắt kết nối, hủy chuỗi và giải phóng tài nguyên

**Ngữ cảnh:** Spring Framework Reactive → **Truyền dữ liệu liên tục**.

Trong WebFlux, một request có thể giữ publisher hoạt động lâu hơn một request/response thông thường: SSE, NDJSON, tải file, truy vấn cursor, kết nối tới message broker hoặc một luồng dữ liệu liên tục. Khi client đóng tab, hủy subscription, mất mạng hoặc không còn đọc response, server cần dừng công việc không còn người nhận và giải phóng tài nguyên đã mở.

Ba khái niệm phải phân biệt:

- **Disconnect:** kết nối hoặc HTTP stream giữa client và server không còn sử dụng được. Đây là sự kiện ở tầng transport/server adapter.
- **Cancellation:** subscriber phía dưới gửi tín hiệu cancel qua Reactive Streams subscription để yêu cầu publisher phía trên ngừng phát dữ liệu. Trong Reactor, cancellation là một terminal condition riêng, không phải `onError`.
- **Cleanup/release:** đóng cursor, connection, file handle, subscription, timer, buffer hoặc resource khác đã được cấp cho pipeline.

Một client disconnect thường dẫn tới cancellation của response publisher, nhưng việc phát hiện có thể bị trễ tới lần ghi dữ liệu tiếp theo. Cancellation có thể lan ngược qua chuỗi reactive, nhưng **không tự động đảo ngược mọi side effect đã xảy ra**. Ứng dụng phải gắn resource với lifecycle của subscription và định nghĩa cách đóng chúng cho cả complete, error lẫn cancel.

## 1. Vòng đời của một response streaming

Ví dụ endpoint SSE trả dữ liệu theo thời gian:

```java
@GetMapping(path = "/updates",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
public Flux<ServerSentEvent<Update>> updates() {
    return updateService.stream()
            .map(update -> ServerSentEvent.builder(update).build())
            .doOnCancel(() -> log.info("client cancelled updates stream"))
            .doFinally(signal ->
                    log.info("updates stream finished: {}", signal));
}
```

Đây là snippet WebFlux cần service, DTO, logger và imports. Controller trả `Flux` cho framework; server adapter đăng ký subscriber để ghi các event ra HTTP response. Nếu client ngắt kết nối khi stream đang hoạt động, server có thể hủy subscription ghi body. `doOnCancel` và `doFinally` giúp quan sát lifecycle đó.

Luồng tổng quát:

```text
Client                         WebFlux server
  |                                  |
  | GET /updates                    |
  |--------------------------------->|
  |                                  | subscribe response Flux
  |<---------------------------------| HTTP 200 + headers
  |                                  |
  |<---------------------------------| event 1
  |<---------------------------------| event 2
  |                                  |
  X client closes tab / network lost |
                                     | transport detects write failure
                                     | cancel response subscription
                                     v
                              response Flux receives cancel
                                     |
                                     v
                              cancellation propagates upstream
                                     |
                                     v
                              resource cleanup runs
```

Không phải mọi disconnect đều được phát hiện ngay tại thời điểm dây mạng đứt. OS, TCP, TLS, reverse proxy và server có thể giữ dữ liệu trong buffer; server chỉ biết client không còn nhận được khi một thao tác I/O phát hiện lỗi hoặc timeout xảy ra.

Spring nhấn mạnh rằng với streaming response như `text/event-stream`, `application/jsonl` hoặc `application/x-ndjson`, ứng dụng nên gửi dữ liệu định kỳ để phát hiện client disconnect sớm hơn. Một SSE comment, event rỗng hoặc dữ liệu no-op có thể làm heartbeat nếu phù hợp giao thức. Khoảng heartbeat phải ngắn hơn idle timeout của proxy/load balancer và được chọn theo môi trường triển khai.

## 2. Disconnect không phải lúc nào cũng xuất hiện thành một exception

Khi client đóng kết nối, server có thể quan sát:

- Lỗi ghi response từ transport.
- Cancellation của subscriber đang ghi body.
- Timeout khi không có tiến triển I/O.
- Lỗi đọc request body nếu client ngắt trong lúc upload.
- Không có tín hiệu ngay lập tức nếu chưa có I/O tiếp theo để phát hiện.

Do đó, không nên thiết kế cleanup chỉ dựa vào `doOnError`. Một disconnect có thể đi vào nhánh cancellation mà không phát `onError` tới publisher nghiệp vụ.

| Tình huống | Tín hiệu reactive có thể quan sát | Ý nghĩa |
|---|---|---|
| Publisher kết thúc bình thường | `onComplete` | Luồng hoàn tất thành công |
| Service phát lỗi | `onError` | Luồng thất bại |
| Client hủy subscription | `cancel` | Subscriber không còn muốn nhận dữ liệu |
| Server phát hiện socket write failure | Có thể error hoặc cancel tùy adapter/đường ghi | Transport không còn ghi được |
| Client im lặng nhưng chưa gửi FIN/RST | Chưa có tín hiệu ngay | Cần heartbeat/timeout để phát hiện |

Cancellation không có HTTP status riêng. Nếu response chưa commit, server có thể vẫn có cơ hội xử lý lỗi theo cơ chế HTTP. Nhưng nếu status/header đã gửi và stream body đã bắt đầu, server không thể quay lại đổi response thành JSON 500. Khi client đã rời đi, việc cố gửi thêm error body cũng không có ích.

## 3. Cancellation là tín hiệu riêng, không phải onError

Reactive Streams có ba tín hiệu kết thúc thường cần quan sát:

- `onComplete`: publisher hoàn tất bình thường.
- `onError`: publisher kết thúc do lỗi.
- `Subscription.cancel()`: subscriber yêu cầu publisher dừng.

Trong Reactor, `doOnCancel` quan sát việc hủy; `doFinally` nhận `SignalType.CANCEL` ngoài `ON_COMPLETE` và `ON_ERROR`.

Ví dụ:

```java
Flux<Long> stream = Flux.interval(Duration.ofSeconds(1))
        .doOnCancel(() -> log.info("upstream cancel received"))
        .doFinally(signal ->
                log.info("upstream terminal signal: {}", signal));

return stream.take(5);
```

Khi `take(5)` đã nhận đủ năm item, nó hoàn tất với downstream và hủy upstream vì không cần thêm dữ liệu. Đây là cancellation do operator, không phải client disconnect. Nó minh họa rằng bất kỳ operator nào không còn cần upstream đều có thể tạo cancellation.

**Không dùng `onErrorResume` để bắt cancellation.** Cancellation không phải error signal, nên fallback error không phải cơ chế cleanup cho disconnect. Nếu cần dọn resource, gắn cleanup vào resource scope hoặc cancellation lifecycle.

## 4. Cancellation lan ngược qua chuỗi reactive

Giả sử pipeline:

```java
return repository.openCursor()
        .flatMapMany(cursor -> cursor.readRows())
        .map(this::toDto)
        .filter(this::visibleToClient)
        .publishOn(Schedulers.parallel())
        .doFinally(signal -> metrics.record(signal.name()));
```

Nếu downstream hủy subscription, cancellation được truyền ngược qua các operator về source. Operator có thể dừng yêu cầu thêm item, hủy inner publisher và dọn queue nội bộ theo contract của nó.

Một số operator tạo hoặc quản lý subscription con:

- `flatMap` có thể hủy các inner publisher đang hoạt động.
- `switchMap` hủy publisher cũ khi chuyển sang publisher mới.
- `take` hủy upstream sau khi đủ số item.
- `timeout` hủy nguồn khi quá thời gian.
- `next` chỉ cần item đầu tiên rồi hủy phần còn lại.
- `publishOn` và operator prefetch có thể đang giữ item trong queue; các item bị bỏ cần được cleanup nếu kiểu dữ liệu yêu cầu.

Cancellation không đảm bảo mọi thư viện hoặc API bên ngoài dừng tức thì. Một publisher hợp tác với Reactive Streams có thể truyền cancel, nhưng driver, SDK, native call hoặc blocking operation phía dưới có thể cần API hủy riêng.

## 5. doOnCancel và doFinally

Hai operator này có mục đích khác nhau:

| Operator | Khi chạy | Dùng cho |
|---|---|---|
| `doOnCancel(Runnable)` | Khi subscriber gọi cancel; callback chạy trước khi cancel được truyền upstream | Ghi nhận client/operator hủy, tăng counter |
| `doFinally(Consumer<SignalType>)` | Sau khi complete, error hoặc cancel đã được truyền downstream/upstream theo lifecycle | Metrics terminal signal, thời gian, log kết thúc |
| `doOnError(Consumer)` | Khi có error signal | Ghi nhận lỗi, phân loại exception |
| `doOnComplete(Runnable)` | Khi complete bình thường | Quan sát hoàn tất thành công |

Ví dụ:

```java
return eventService.stream()
        .doOnCancel(() -> metrics.increment("stream.cancelled"))
        .doOnError(error ->
                log.warn("stream failed", error))
        .doFinally(signal ->
                metrics.recordTermination(signal.name()));
```

Lưu ý:

1. `doOnCancel` không chạy khi publisher complete hoặc error bình thường.
2. `doOnError` không chạy chỉ vì subscriber cancel.
3. `doFinally` chạy cho cả complete, error và cancel.
4. Callback của `doFinally` là callback đồng bộ, không trả về publisher để chờ cleanup bất đồng bộ.
5. `doFinally` được thực thi sau khi terminal signal đã được chuyển tiếp; vì vậy code downstream có thể hoàn tất trước khi side effect trong callback chạy xong.
6. Nhiều `doFinally` nối tiếp có thể quan sát thứ tự callback ngược nhau do mỗi callback chạy sau khi signal đã đi qua operator.

Hãy dùng các operator quan sát cho logging/metrics. Đừng coi `doOnCancel` là nơi duy nhất đóng database connection, file hoặc cursor nếu việc đóng cần bảo đảm và có thể bất đồng bộ.

## 6. Quản lý resource bằng using

Reactor `using` tương tự try-with-resources: tạo resource cho mỗi subscription, tạo publisher dùng resource đó, rồi cleanup khi sequence complete, error hoặc cancel.

Ví dụ với cursor đóng đồng bộ:

```java
Flux<Row> rows = Flux.using(
        cursorFactory::open,
        cursor -> cursor.readRows(),
        Cursor::close);
```

Đây là snippet minh họa; `CursorFactory` và `Cursor` là abstraction của ứng dụng. Mỗi subscriber có resource riêng. Cleanup được gọi khi sequence kết thúc hoặc subscriber hủy.

`using` phù hợp với resource có thao tác đóng đồng bộ, nhanh và không chặn event-loop. Nếu `close()` có thể block lâu, không gọi trực tiếp trên thread xử lý I/O; dùng API async hoặc chuyển phần blocking sang scheduler phù hợp.

Không tạo cursor một lần trong field singleton rồi chia sẻ cho mọi subscriber. Một client cancel có thể đóng resource mà client khác vẫn đang sử dụng.

## 7. Quản lý cleanup bất đồng bộ bằng usingWhen

Database connection, lease, remote subscription hoặc transaction có thể cần đóng bất đồng bộ. Dùng `usingWhen` để khai báo cleanup riêng cho ba đường kết thúc:

```java
Flux<Row> rows = Flux.usingWhen(
        connectionFactory.acquire(),
        connection -> queryRows(connection),
        connection -> connection.closeAsync(),
        (connection, error) ->
                connection.rollbackAsync()
                        .then(connection.closeAsync()),
        connection -> connection.closeAsync()
);
```

Đây là ví dụ cấu trúc; `acquire`, `queryRows`, `closeAsync` và `rollbackAsync` đại diện API của resource thực tế. Các cleanup function phải trả Publisher. Nếu hệ thống không có transaction, nhánh error có thể chỉ đóng resource; không gọi rollback khi không có transaction.

Các overload thường dùng:

- `usingWhen(resourcePublisher, resourceClosure, asyncCleanup)`: dùng một cleanup publisher chung cho mọi terminal path.
- `usingWhen(resourcePublisher, resourceClosure, asyncComplete, asyncError, asyncCancel)`: cleanup riêng khi complete, error hoặc cancel.

Điều quan trọng là mọi thao tác cần resource còn mở phải nằm trong `resourceClosure`. Đừng dùng connection bên ngoài publisher scope sau khi cleanup đã chạy.

Cleanup bất đồng bộ có thể thất bại. Reactor có thể chuyển lỗi cleanup thành terminal error thay cho terminal signal ban đầu trong một số đường xử lý. Hãy log/metric cleanup failure, đặt timeout phù hợp cho thao tác đóng và xác định chính sách nếu đóng resource không thành công.

## 8. Database transaction và cancellation

Trong một transaction reactive, vòng đời transaction phải gắn với publisher được framework/transaction manager quản lý. Với R2DBC, dùng Spring reactive transaction management hoặc `TransactionalOperator` thay vì tự mở connection rồi tự subscribe.

Ví dụ:

```java
return transactionalOperator.transactional(
        orderRepository.save(order)
                .then(auditRepository.save(auditRecord))
);
```

Nếu pipeline kết thúc bằng error, transaction manager có thể rollback. Nếu subscription bị cancel trước khi transaction hoàn tất, transaction manager sẽ thực hiện cleanup/rollback theo semantics của transaction resource và manager đang dùng.

Tuy nhiên:

- Cancellation không phải lệnh rollback phổ quát cho mọi hệ thống.
- Một HTTP call tới payment provider đã được gửi không tự được hoàn tác.
- Một message đã publish tới broker có thể đã tới consumer.
- Một file đã ghi hoặc email đã gửi không tự biến mất khi client disconnect.
- Database commit có thể đã xảy ra trước khi cancellation được quan sát.

Với thao tác có side effect quan trọng, cần transaction boundary, idempotency key, outbox, trạng thái job hoặc reconciliation phù hợp. Không dùng cancellation như cơ chế đảm bảo exactly-once.

## 9. DataBuffer và pooled memory

Trong WebFlux, `DataBuffer` đại diện vùng byte. Với một số server như Reactor Netty, buffer có thể được pooled và reference-counted. Nếu code ứng dụng trực tiếp tiêu thụ hoặc tạo `DataBuffer`, phải hiểu rõ ownership và thời điểm release.

Khi dùng `@RequestBody Mono<Dto>`, `Flux<Dto>` hoặc response DTO thông thường, hãy để codec và HTTP layer quản lý buffer. Thường không cần tự gọi release.

Khi code tự xử lý `Flux<DataBuffer>`:

- Nếu đọc xong buffer, release đúng một lần bằng `DataBufferUtils.release(buffer)` khi code của bạn chịu trách nhiệm ownership.
- Nếu giữ buffer để đọc sau, bảo đảm release khi đã dùng xong và trên cả error/cancel.
- Nếu operator có thể loại bỏ item hoặc giữ item trong prefetch queue, xem xét `doOnDiscard(DataBuffer.class, DataBufferUtils::release)` tại đúng vị trí.
- Không release buffer do framework/codec vẫn sở hữu.
- Không retain nếu không cần; nếu gọi retain, phải có release tương ứng.
- Không đọc buffer sau khi đã release.

Ví dụ đọc raw body và release buffer sau khi sao chép bytes:

```java
Flux<byte[]> chunks = request.getBody()
        .map(buffer -> {
            try {
                byte[] bytes = new byte[buffer.readableByteCount()];
                buffer.read(bytes);
                return bytes;
            }
            finally {
                DataBufferUtils.release(buffer);
            }
        });
```

Đây là snippet minh họa khi ứng dụng đã nhận quyền tiêu thụ buffer. Nếu upstream operator có thể prefetch hoặc discard DataBuffer trước khi đến `map`, cần thêm cleanup cho các item bị discard và xác nhận ownership ở từng bước.

Ví dụ hook discard:

```java
Flux<DataBuffer> filtered = request.getBody()
        .filter(this::isAccepted)
        .doOnDiscard(
                DataBuffer.class,
                DataBufferUtils::release);
```

`doOnDiscard` chỉ tác động lên những operator upstream hỗ trợ discard và các item mà operator đó loại bỏ. Hook không phải cơ chế giải phóng mọi object ở mọi path. Cleanup hook phải an toàn theo contract và tránh double release.

Với multipart streaming bằng `PartEvent`, nội dung của mỗi event phải được consume, relay sang nơi khác hoặc release. Nếu bỏ qua một file part mà không tiêu thụ/release các DataBuffer của nó, có thể gây rò pooled memory.

## 10. Blocking I/O và giới hạn của cancellation

Một lời gọi blocking không tự trở thành cancellable chỉ vì được đặt trong Reactor pipeline.

Ví dụ chuyển legacy blocking call ra khỏi event-loop:

```java
Mono<Result> result = Mono.fromCallable(
                () -> legacyClient.fetch(id))
        .subscribeOn(Schedulers.boundedElastic());
```

Đoạn này tránh chạy thao tác blocking trên thread I/O event-loop. Nhưng cancellation downstream **không bảo đảm** thư viện blocking dừng ngay. Có thể cần:

- Connect/read timeout trong HTTP client hoặc JDBC driver.
- API close/cancel statement của thư viện.
- Interruptible operation nếu thư viện hỗ trợ.
- Giới hạn thời gian và số tác vụ đang chờ.
- Driver reactive thực sự như R2DBC khi phù hợp.

Không gọi `block()` trong controller, WebFilter hoặc event-loop. Không tự gọi `subscribe()` để tách một công việc khỏi request mà không có owner/lifecycle riêng.

Nếu client disconnect nhưng nghiệp vụ phải tiếp tục, hãy enqueue job bền vững và trả job ID. Worker nền có lifecycle độc lập với HTTP subscription; đừng dựa vào một subscription của response đã mất client để làm durable background work.

## 11. Heartbeat cho SSE và stream dài

Một stream im lặng lâu có thể khiến proxy hoặc server không phát hiện client đã biến mất. Heartbeat tạo hoạt động định kỳ để tầng ghi sớm phát hiện lỗi kết nối.

Ví dụ SSE comment heartbeat:

```java
Flux<ServerSentEvent<Update>> heartbeats =
        Flux.interval(Duration.ofSeconds(20))
                .map(tick ->
                        ServerSentEvent.<Update>builder()
                                .comment("keep-alive")
                                .build());

Flux<ServerSentEvent<Update>> response =
        Flux.merge(
                updateService.stream()
                        .map(update ->
                                ServerSentEvent.builder(update).build()),
                heartbeats
        );
```

Đây là snippet cho stream sống lâu; cần chọn chu kỳ phù hợp idle timeout của reverse proxy/load balancer. SSE comment không tạo business event cho client, nhưng vẫn tạo dữ liệu ghi trên kết nối. Vì heartbeat là nguồn vô hạn, response sẽ tiếp tục mở ngay cả khi publisher update hoàn tất; đó là chủ ý với live stream. Nếu muốn response kết thúc cùng update source, hãy thiết kế lifecycle/merge phù hợp thay vì ghép một heartbeat vô hạn không giới hạn.

Heartbeat không chứng minh client đã xử lý event. Nó chỉ giúp phát hiện một số kết nối hỏng sớm hơn; TCP/proxy vẫn có thể buffer hoặc drop theo điều kiện riêng.

## 12. Nhiều subscriber và nguồn stream dùng chung

Cần phân biệt subscription của từng client với nguồn dữ liệu dùng chung:

- **Cold publisher:** mỗi subscriber có thể kích hoạt một lần thực thi độc lập. Client A cancel thì subscription của A dừng.
- **Hot publisher:** nguồn có thể phát độc lập với subscriber. Client A cancel không nhất thiết dừng nguồn.
- **Shared publisher:** nhiều client cùng dùng một nguồn đã multicast. Việc một client rời đi không nên đóng tài nguyên mà client khác còn cần.
- **Ref-counted source:** nguồn upstream có thể disconnect khi số subscriber còn lại giảm về ngưỡng đã cấu hình, ví dụ về 0.

Ví dụ `publish().refCount(1)` có thể ngắt upstream khi không còn subscriber. Điều đó phù hợp khi nguồn chỉ cần tồn tại trong lúc có ít nhất một client. Nếu nguồn phải chạy liên tục dù không có client, cần lifecycle quản lý riêng và chính sách shutdown riêng.

Không đặt mutable request-specific state trong field của singleton service hoặc dùng chung một cursor cho nhiều client. Tạo state theo subscription bằng `defer` hoặc resource operator phù hợp.

## 13. Cancellation không phải rollback và không phải retry

Cancellation có nghĩa subscriber không còn muốn nhận dữ liệu. Nó không khẳng định:

- Mọi lệnh đã gửi tới database đã bị hủy.
- Remote service chưa xử lý request.
- Broker chưa nhận message.
- Transaction đã rollback.
- Client có thể retry mà không tạo side effect trùng.

Retry trong Reactor chủ yếu xử lý error signal; cancellation không phải error để `retry()` tự khởi chạy lại. Nếu client reconnect và muốn tiếp tục stream, API cần một protocol resume rõ ràng, ví dụ event ID/sequence, Last-Event-ID cho SSE, cursor hoặc checkpoint.

Với command ghi dữ liệu, dùng idempotency key và optimistic concurrency để client có thể retry an toàn khi không biết server đã commit trước khi kết nối bị mất hay chưa.

## 14. Chương trình Java 17+ chạy độc lập: quan sát cancel và đóng resource

Ví dụ này dùng Reactor Core để mô phỏng một cursor đồng bộ. `take(1)` nhận một row rồi cancel upstream. `Flux.using` đóng cursor khi sequence bị cancel.

Cấu trúc:

```text
reactor-cancellation-demo/
├── pom.xml
└── src/main/java/demo/CancellationDemo.java
```

Tệp `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>reactor-cancellation-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-core</artifactId>
            <version>3.7.17</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.4.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Tệp `src/main/java/demo/CancellationDemo.java`:

```java
package demo;

import reactor.core.publisher.Flux;

public class CancellationDemo {

    static final class Cursor {
        void close() {
            System.out.println("cursor closed");
        }
    }

    public static void main(String[] args) {
        Flux.using(
                Cursor::new,
                cursor -> Flux.just("row-1", "row-2")
                        .doOnCancel(() ->
                                System.out.println("source doOnCancel"))
                        .doFinally(signal ->
                                System.out.println(
                                        "source doFinally=" + signal)),
                Cursor::close
        )
        .take(1)
        .doFinally(signal ->
                System.out.println(
                        "downstream doFinally=" + signal))
        .doOnNext(row -> System.out.println("row=" + row))
        .blockLast();
    }
}
```

Chạy với JDK 17+ và Maven:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.CancellationDemo
```

**Standard output dự kiến:**

```text
row=row-1
source doOnCancel
source doFinally=CANCEL
cursor closed
downstream doFinally=ON_COMPLETE
```

Giải thích:

1. `Flux.using` tạo cursor khi có subscription.
2. Source phát `row-1`; `take(1)` đã đủ dữ liệu nên hủy upstream.
3. Source quan sát cancel bằng `doOnCancel`.
4. `doFinally` ở source nhận `SignalType.CANCEL` sau khi cancel được truyền upstream.
5. `using` gọi `Cursor.close()` để giải phóng resource.
6. Downstream của `take(1)` hoàn tất bình thường, nên `doFinally` phía ngoài nhận `ON_COMPLETE`.
7. `blockLast()` chỉ dùng trong `main` để chương trình demo chờ; không đưa nó vào WebFlux handler.

Chương trình mô phỏng cancellation do operator. Khi client disconnect, server adapter là thành phần có thể phát cancellation tới response publisher; phần cleanup resource vẫn đi theo cùng nguyên tắc.

## 15. Kiểm thử cancellation

### 15.1. StepVerifier kiểm tra cancel và cleanup

Với pipeline Reactor thuần, `StepVerifier` có thể gửi cancel rõ ràng:

```java
AtomicBoolean cancelled = new AtomicBoolean();

Flux<Long> stream = Flux.interval(Duration.ofMillis(100))
        .doOnCancel(() -> cancelled.set(true));

StepVerifier.create(stream)
        .expectNext(0L)
        .thenCancel()
        .verify();

assertThat(cancelled).isTrue();
```

Đây là snippet test cần Reactor Test, JUnit/AssertJ và imports. `thenCancel()` kiểm tra publisher phản ứng với cancellation mà không cần `Thread.sleep`.

Nếu cần kiểm tra resource cleanup, dùng một resource fake có counter hoặc latch; assert cleanup được gọi đúng một lần. Với `usingWhen`, cleanup bất đồng bộ nên test chờ publisher cleanup hoàn tất bằng công cụ đồng bộ phù hợp hoặc StepVerifier timeout, không suy đoán bằng thời gian ngủ cố định.

### 15.2. Integration test qua HTTP thật

`WebTestClient.bindToController` hoặc bind trực tiếp router có thể kiểm tra handler logic nhưng không mô phỏng đầy đủ disconnect ở transport. Để kiểm tra hành vi client abort:

1. Khởi động ứng dụng WebFlux trên embedded server thật, thường với `RANDOM_PORT`.
2. Tạo một endpoint stream không kết thúc ngay, có `doOnCancel` hoặc cleanup marker.
3. Dùng client HTTP thật (ví dụ `WebClient`) subscribe vào response body.
4. Sau khi nhận một hoặc vài item, hủy subscription/đóng response.
5. Chờ tín hiệu cleanup bằng latch hoặc test probe có timeout.
6. Assert nguồn đã nhận cancel và resource được release.
7. Lặp lại với normal completion và error để xác nhận cả ba đường kết thúc.

Test transport phụ thuộc server adapter và proxy. Một test chạy qua in-memory exchange không đủ để chứng minh socket disconnect ngoài production.

### 15.3. Các trường hợp cần có trong test suite

- Complete bình thường đóng resource.
- Error đóng resource và giữ lỗi gốc theo policy.
- Cancel đóng resource.
- Cancel trước khi resource acquisition hoàn tất không để resource rò.
- Cleanup bất đồng bộ lỗi hoặc timeout được quan sát.
- Client chậm không làm queue tăng vô hạn.
- Heartbeat giúp phát hiện kết nối stale trong thời gian mong muốn.
- Một client cancel không làm hỏng stream của client khác khi nguồn được share.
- Request body upload bị hủy giải phóng DataBuffer/PartEvent đúng cách.
- Side effect có idempotency khi client reconnect hoặc retry.

## 16. Những lỗi thường gặp

1. **Chỉ dùng doOnError để cleanup.** Cancellation không phải error signal; dùng resource scope hoặc cancellation-aware cleanup.
2. **Chỉ dùng doOnComplete.** Callback này không chạy khi error hoặc cancel.
3. **Nghĩ doFinally tự chờ cleanup bất đồng bộ.** Callback doFinally không trả Publisher; dùng usingWhen cho async cleanup.
4. **Gọi close() trên event-loop nếu close block.** Chuyển sang API async hoặc scheduler phù hợp.
5. **Tạo resource ở ngoài publisher rồi chia sẻ cho nhiều subscriber.** Một subscriber cancel có thể đóng resource của subscriber khác.
6. **Dùng using cho async close dài.** Dùng usingWhen để chờ cleanup publisher.
7. **Quên nhánh cancel của usingWhen.** Nếu có cleanup khác nhau, cung cấp asyncCancel rõ ràng.
8. **Giả định disconnect được phát hiện tức thì.** Transport có thể chỉ phát hiện khi lần ghi tiếp theo hoặc timeout.
9. **Không gửi heartbeat cho stream im lặng dài.** Proxy có thể đóng idle connection hoặc server phát hiện disconnect muộn.
10. **Coi cancel là rollback.** Side effect bên ngoài có thể đã hoàn tất; cần transaction/idempotency/reconciliation.
11. **Coi cancel là retry.** Retry operator xử lý error, không tự resubscribe vì cancel.
12. **Tự subscribe trong controller để công việc tiếp tục sau disconnect.** Tạo công việc không có owner; nếu cần chạy nền, enqueue job bền vững.
13. **Gọi block trong reactive chain.** Chặn event-loop và phá cancellation/backpressure.
14. **Đọc DataBuffer mà không release.** Pooled memory có thể rò khi error/cancel.
15. **Release DataBuffer hai lần.** Có thể gây reference-count error; xác định owner và release đúng một lần.
16. **Cho rằng doOnDiscard xử lý mọi object bị bỏ.** Hook chỉ áp dụng cho operator upstream hỗ trợ discard và không thay thế cleanup toàn bộ lifecycle.
17. **Bỏ qua PartEvent khi upload multipart.** Mỗi content buffer phải được consume, relay hoặc release.
18. **Giữ connection/cursor trong field singleton.** Request đồng thời có thể dùng chung hoặc đóng nhầm resource.
19. **Dùng timeout như bằng chứng chắc chắn client đã disconnect.** Timeout chỉ nói không có tín hiệu trong khoảng đã chọn; nguyên nhân có thể là mạng, client chậm hoặc upstream chậm.
20. **Không test bằng server thật.** In-memory test không chứng minh được transport cancellation.

## 17. Checklist thiết kế production

Trước khi đưa stream dài vào production, hãy kiểm tra:

- **Disconnect detection:** server adapter nào đang chạy? Proxy idle timeout là bao lâu? Có heartbeat không?
- **Cancellation path:** response publisher có nhận cancel? Operator nào đang giữ inner subscription hoặc queue?
- **Resource ownership:** cursor, connection, file, broker subscription được tạo theo subscriber nào?
- **Cleanup:** dùng `using` hay `usingWhen`? Complete, error và cancel đều có đường đóng resource?
- **Cleanup failure:** timeout, log và metric cho việc close thất bại đã có chưa?
- **DataBuffer:** ai sở hữu, ai retain/release, discard/error/cancel có được xử lý?
- **Blocking calls:** có timeout/cancel API thật hay chỉ chuyển sang boundedElastic?
- **Transaction:** transaction reactive có được gắn đúng publisher scope?
- **Side effects:** có thể đã commit trước disconnect không? Có idempotency key/outbox/reconciliation?
- **Shared streams:** một subscriber cancel có ảnh hưởng subscriber khác hoặc nguồn toàn cục không?
- **Background work:** tác vụ cần sống độc lập đã được chuyển sang durable job/queue chưa?
- **Observability:** phân biệt complete, error, cancel, transport reset, timeout và cleanup failure?
- **Testing:** có StepVerifier test và HTTP integration test qua server thật không?
- **Capacity:** số stream, heartbeat, connection, queue và cleanup task có giới hạn không?

**Ghi nhớ:** Disconnect là sự kiện transport; cancellation là tín hiệu Reactive Streams; cleanup là trách nhiệm quản lý resource. WebFlux có thể truyền cancellation từ response writer về publisher khi server phát hiện client không còn nhận dữ liệu. Hãy dùng `doOnCancel`/`doFinally` để quan sát, `using` cho resource đồng bộ, `usingWhen` cho cleanup bất đồng bộ, và quản lý `DataBuffer` theo ownership. Cancellation không tự rollback side effect; tác vụ cần tiếp tục sau khi client rời đi phải có lifecycle độc lập và bền vững.

## Tài liệu tham khảo

- Spring Framework — [Reactive Core: WebFlux streaming, disconnect detection and DataBuffer](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html).
- Spring Framework — [Data Buffers and Codecs: release, retain, join and discard](https://docs.spring.io/spring-framework/reference/core/databuffer-codec.html).
- Spring Framework — [Functional Endpoints: request body streaming and PartEvent ownership](https://docs.spring.io/spring-framework/reference/web/webflux-functional.html).
- Project Reactor — [Dealing with Objects that Need Cleanup](https://projectreactor.io/docs/core/release/reference/advancedFeatures/cleanup.html).
- Project Reactor — [Flux Javadoc: using and usingWhen](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html).
- Project Reactor — [Mono Javadoc: doOnCancel and doFinally](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html).
