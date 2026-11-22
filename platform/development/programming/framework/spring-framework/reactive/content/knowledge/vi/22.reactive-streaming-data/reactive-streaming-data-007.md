# Kết nối chậm, backpressure và chính sách giới hạn dữ liệu

**Module:** Spring Framework – reactive  
**Chủ đề cha:** Truyền dữ liệu liên tục

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích backpressure theo Reactive Streams và cách demand truyền ngược từ subscriber tới publisher.
2. Phân tích điều gì xảy ra khi client đọc HTTP chậm, downstream xử lý chậm hoặc upstream phát dữ liệu nhanh hơn khả năng tiêu thụ.
3. Phân biệt publisher có thể tuân theo demand với nguồn dữ liệu nóng (hot source) không thể tạm dừng.
4. Chọn chính sách bounded buffer, drop, latest hoặc error theo yêu cầu nghiệp vụ.
5. Dùng các operator Reactor như `limitRate`, `onBackpressureBuffer`, `onBackpressureDrop`, `onBackpressureLatest`, `flatMap` và `timeout` đúng mục đích.
6. Giới hạn bộ nhớ, số phần tử, concurrency, prefetch, kích thước body và thời gian chờ để tránh tích lũy dữ liệu vô hạn.
7. Xử lý overflow, cancellation và slow consumer trong WebFlux HTTP/SSE.
8. Xây dựng và kiểm thử một endpoint streaming có buffer hữu hạn bằng Spring Boot và `WebTestClient`.

## 1. Backpressure giải quyết vấn đề gì?

Một pipeline reactive thường gồm publisher tạo dữ liệu, các operator biến đổi dữ liệu và subscriber tiêu thụ dữ liệu. Nếu publisher phát nhanh hơn tốc độ subscriber xử lý, phần dữ liệu chưa tiêu thụ có thể tích lũy trong queue, buffer hoặc bộ nhớ của các tầng trung gian.

Backpressure là cơ chế điều tiết tốc độ phát bằng **demand**. Subscriber yêu cầu số lượng phần tử mà nó sẵn sàng nhận thông qua `Subscription.request(n)`. Publisher tuân theo Reactive Streams chỉ được phát tối đa số phần tử đã được yêu cầu, cho tới khi nhận thêm demand.

```text
Publisher / source
       |
       | onNext(item) theo demand
       v
Operator A
       |
       v
Operator B
       |
       v
Subscriber / HTTP writer
       |
       | request(n): cần thêm n phần tử
       +-------------------------------> demand truyền ngược upstream

Nếu consumer chậm:
- demand mới đến chậm hơn
- publisher có thể giảm hoặc tạm dừng phát
- queue có giới hạn giúp tránh tích lũy vô hạn
```

Các tín hiệu cơ bản của Reactive Streams:

- `onSubscribe(subscription)`: subscriber nhận subscription.
- `request(n)`: subscriber báo nhu cầu nhận thêm n phần tử.
- `onNext(value)`: publisher phát một phần tử khi có demand.
- `onError(error)`: publisher kết thúc bằng lỗi.
- `onComplete()`: publisher hoàn tất bình thường.
- `cancel()`: subscriber hủy việc tiêu thụ; upstream nên dừng và giải phóng tài nguyên phù hợp.

Demand đếm **số phần tử**, không phải số byte. Một phần tử có thể là chuỗi vài byte hoặc một object chứa payload lớn. Vì vậy, backpressure phải đi cùng giới hạn kích thước phần tử/body và chính sách bộ nhớ.

## 2. Vì sao kết nối chậm có thể làm hệ thống tích lũy dữ liệu?

Hãy xét một endpoint SSE phát trạng thái thiết bị:

- Producer tạo 500 sự kiện mỗi giây.
- Client chỉ đọc và xử lý được 20 sự kiện mỗi giây.
- Chênh lệch là 480 sự kiện mỗi giây.

Nếu ứng dụng giữ tất cả sự kiện trong một queue không giới hạn, sau 60 giây có thể tích lũy 28.800 sự kiện chưa được tiêu thụ cho riêng client đó. Nếu nhiều client cùng chậm, lượng dữ liệu tăng theo số kết nối và kích thước từng sự kiện.

Các vị trí có thể tích lũy dữ liệu gồm:

1. Queue của nguồn dữ liệu nóng hoặc message listener.
2. Buffer của Reactor operator, chẳng hạn buffer, window hoặc prefetch.
3. Queue trong publisher/consumer adapter.
4. Bộ mã hóa HTTP và write queue của server transport.
5. Socket buffer của hệ điều hành.
6. Reverse proxy, load balancer và buffer ở phía client.

WebFlux có thể truyền backpressure từ HTTP writer ngược vào reactive publisher khi các tầng tham gia hỗ trợ demand. Tuy nhiên, điều đó **không bảo đảm toàn bộ đường mạng không có buffer**. TCP flow control, queue của proxy và thư viện client là những cơ chế riêng. Một nguồn nóng hoặc callback bên ngoài có thể tiếp tục phát dù subscriber đã giảm demand.

Do đó, cần xác định dữ liệu đang bị dồn ở tầng nào. Chỉ tăng buffer có thể trì hoãn lỗi và làm mức tiêu thụ bộ nhớ lớn hơn.

### 2.1. Ba tình huống cần phân biệt

| Tình huống | Đặc điểm | Hướng xử lý |
| --- | --- | --- |
| Upstream có thể tuân theo demand | Nguồn chỉ phát khi downstream yêu cầu | Để backpressure truyền ngược; tránh queue không cần thiết. |
| Upstream nóng, không thể tạm dừng | Timer, callback, event bus hoặc producer bên ngoài vẫn phát | Chọn buffer hữu hạn, drop, latest hoặc reject/error. |
| Consumer HTTP chậm hoặc ngắt kết nối | Write demand giảm hoặc subscriber cancel | Giữ pipeline streaming, giới hạn queue, xử lý cancellation và timeout. |

Ví dụ nguồn có thể tuân theo demand: một reactive database driver trả `Flux<Row>` và chỉ đọc thêm khi subscriber yêu cầu. Ví dụ nguồn nóng: cảm biến phần cứng phát sự kiện theo clock riêng, bất kể client đang đọc nhanh hay chậm.

### 2.2. Backpressure khác TCP flow control

TCP dùng receive window để điều chỉnh lượng byte bên gửi được phép truyền trước khi nhận xác nhận. Reactive Streams dùng demand để điều chỉnh **phần tử** giữa publisher và subscriber trong ứng dụng.

Hai cơ chế có thể phối hợp qua HTTP server adapter, nhưng không đồng nhất:

- TCP có thể làm chậm việc ghi xuống socket khi phía nhận không đọc kịp.
- Reactive backpressure có thể làm publisher giảm việc phát object khi HTTP writer không yêu cầu thêm.
- Proxy hoặc tầng trung gian có thể vẫn buffer dữ liệu.
- Một producer không hỗ trợ demand vẫn cần chính sách overflow ở phía ứng dụng.

Không nên kết luận rằng dùng WebFlux là không thể đầy bộ nhớ. Queue không giới hạn, payload lớn, quá nhiều kết nối hoặc thao tác gom toàn bộ body vẫn có thể làm bộ nhớ tăng mạnh.

## 3. Chọn chính sách khi consumer chậm

Không có một chính sách overflow phù hợp cho mọi loại dữ liệu. Câu hỏi đầu tiên là: **khi không thể xử lý kịp, sự kiện cũ có còn giá trị không?**

| Chính sách | Hành vi | Hợp với | Đánh đổi |
| --- | --- | --- | --- |
| Backpressure thuần | Yêu cầu upstream giảm phát theo demand | Reactive database, file stream, nguồn có thể pause | Không áp dụng được cho mọi hot source. |
| Buffer hữu hạn | Giữ tối đa N phần tử đang chờ | Burst ngắn, dữ liệu cần giữ trong giới hạn | Queue đầy thì phải chọn cách xử lý overflow. |
| Drop incoming | Bỏ phần tử mới khi consumer chưa sẵn sàng | Metrics, telemetry có thể mất mẫu | Mất dữ liệu mới nhất. |
| Drop oldest / giữ latest | Loại phần tử cũ để giữ trạng thái mới | Dashboard, trạng thái cảm biến | Không phù hợp với audit/event phải lưu đủ. |
| Latest | Chỉ giữ giá trị mới nhất trong lúc consumer chậm | Trạng thái hiện tại, snapshot | Các trạng thái trung gian bị bỏ qua. |
| Error/reject | Kết thúc stream hoặc từ chối producer khi đầy | Giao dịch, lệnh cần được xác nhận rõ | Client phải xử lý lỗi/retry hoặc lưu bền vững. |
| Durable queue | Ghi vào broker/database có retention và acknowledgement | Sự kiện không được phép mất | Tăng độ phức tạp và chi phí vận hành. |

Quyết định phải xuất phát từ semantics dữ liệu:

- **Giá trị trạng thái hiện tại:** giữ latest thường hợp lý; trạng thái cũ không còn cần thiết.
- **Metric tần suất cao:** drop hoặc sample có thể chấp nhận được nếu có metric đếm số mẫu bị bỏ.
- **Lệnh thanh toán, audit hoặc sự kiện nghiệp vụ:** không âm thầm drop; cần xác nhận, lưu bền vững hoặc reject rõ ràng khi quá tải.
- **Burst ngắn:** buffer nhỏ có thể hấp thụ dao động tạm thời; buffer không giải quyết tình trạng producer liên tục nhanh hơn consumer.

## 4. Các operator backpressure trong Reactor

### 4.1. limitRate: điều tiết request theo lô

`limitRate(highTide)` chia demand thành các đợt request nhỏ hơn. Nó hữu ích khi muốn upstream nhận request theo batch thay vì một request lớn.

```java
Flux<Row> rows = repository.findAll()
        .limitRate(64);
```

Đây là **đoạn minh họa**. Giá trị 64 là ngưỡng request theo lô, không phải giới hạn 64 row mỗi giây và cũng không phải giới hạn tổng số row của stream.

Có thể cấu hình cả high-tide và low-tide:

```java
Flux<Row> rows = repository.findAll()
        .limitRate(64, 32);
```

High-tide là ngưỡng request; low-tide điều chỉnh khi nào Reactor bù demand tiếp theo. Tham số cụ thể nên được chọn theo chi phí xử lý và prefetch của upstream.

**Điểm dễ nhầm:** `limitRate` không phải rate limiter theo thời gian. Nó không bảo đảm tối đa X sự kiện/giây. Nếu cần giới hạn tốc độ theo thời gian, dùng rate limiter/token bucket ở ranh giới phù hợp, hoặc điều tiết phát theo thời gian với operator thích hợp. `delayElements` làm chậm từng phần tử nhưng không tự giới hạn số HTTP request mới vào server.

### 4.2. onBackpressureBuffer: buffer có giới hạn

`onBackpressureBuffer(maxSize)` giữ các phần tử chờ trong buffer khi upstream phát nhanh hơn demand. Luôn chọn giới hạn hữu hạn cho dữ liệu có kích thước hoặc tần suất đáng kể.

```java
Flux<Reading> readings = hotSource
        .onBackpressureBuffer(128);
```

Khi vượt giới hạn, pipeline có thể kết thúc bằng overflow error. Nếu muốn quyết định rõ phần tử nào bị loại, dùng overload có overflow callback và strategy:

```java
Flux<Reading> readings = hotSource.onBackpressureBuffer(
        128,
        dropped -> metrics.incrementDropped(),
        BufferOverflowStrategy.DROP_OLDEST);
```

Đây là **đoạn minh họa**; `metrics` là thành phần ứng dụng. `DROP_OLDEST` bỏ phần tử cũ nhất trong buffer khi đầy để ưu tiên dữ liệu mới hơn. Các lựa chọn thường gặp của `BufferOverflowStrategy` gồm `ERROR`, `DROP_OLDEST` và `DROP_LATEST`. Hãy chọn theo ý nghĩa dữ liệu, không chỉ theo throughput.

Buffer chỉ hữu ích nếu có giới hạn. Một buffer vô hạn biến slow consumer thành bài toán cạn heap, chỉ là lỗi xuất hiện muộn hơn.

### 4.3. onBackpressureDrop: bỏ phần tử không thể nhận

`onBackpressureDrop()` loại phần tử phát ra khi downstream chưa có demand. Có thể gắn callback để đếm hoặc quan sát phần tử bị bỏ:

```java
Flux<Metric> metrics = hotMetricsSource
        .onBackpressureDrop(dropped ->
                meterRegistry.counter("metrics.dropped").increment());
```

Đây là **đoạn minh họa**. Chỉ dùng khi mất mẫu được chấp nhận. Callback nên nhẹ và không block vì nó chạy trên đường phát dữ liệu.

### 4.4. onBackpressureLatest: giữ trạng thái mới nhất

`onBackpressureLatest()` giữ phần tử mới nhất trong khi downstream chưa sẵn sàng; các giá trị trung gian có thể bị thay thế:

```java
Flux<DeviceState> state = hotStateSource
        .onBackpressureLatest();
```

Phù hợp với dashboard chỉ cần trạng thái hiện tại, ví dụ nhiệt độ hiện tại hoặc vị trí mới nhất. Không phù hợp với chuỗi giao dịch mà mỗi event đều cần được xử lý.

### 4.5. onBackpressureError: lỗi rõ ràng khi thiếu demand

`onBackpressureError()` chuyển tình huống phát vượt demand thành lỗi thay vì âm thầm tích lũy hoặc drop:

```java
Flux<Command> commands = hotCommandSource
        .onBackpressureError();
```

Cách này thích hợp khi ứng dụng muốn fail fast và có cơ chế xử lý lỗi/khôi phục rõ ràng. Với stream HTTP đã commit, lỗi giữa luồng không thể biến response thành một JSON 503 mới; client sẽ thấy stream kết thúc hoặc lỗi transport theo giao thức.

### 4.6. Không xếp chồng operator một cách tùy tiện

Không nên ghép buffer lớn, latest, drop và retry liên tiếp mà không xác định operator nào sở hữu chính sách overflow. Thứ tự operator làm thay đổi nơi demand được điều tiết và nơi phần tử bị bỏ.

Ví dụ:

```java
Flux<Reading> bounded = hotSource
        .onBackpressureBuffer(
                128,
                dropped -> metrics.incrementDropped(),
                BufferOverflowStrategy.DROP_OLDEST)
        .limitRate(32);
```

Đoạn này đặt một queue hữu hạn ở ranh giới hot source và giới hạn cách downstream yêu cầu dữ liệu theo batch. Cần đo queue depth, số overflow và latency để xác nhận cấu hình thực sự phù hợp.

## 5. Giới hạn concurrency và prefetch

Backpressure kiểm soát demand, nhưng một pipeline có thể tạo nhiều công việc đồng thời. `flatMap` cho phép xử lý các phần tử bất đồng bộ song song; nếu không đặt concurrency phù hợp, nhiều request I/O có thể cùng mở hoặc cùng chờ.

```java
Flux<EnrichedOrder> result = orderIds
        .flatMap(
                id -> remoteService.loadOrder(id),
                8,
                1);
```

Trong ví dụ:

- `8` là số inner publisher tối đa được subscribe đồng thời.
- `1` là prefetch cho mỗi inner publisher.
- `flatMap` vẫn có thể phát kết quả theo thứ tự hoàn tất, không bảo đảm thứ tự đầu vào.

Nếu cần giữ thứ tự, cân nhắc `flatMapSequential`. Nếu cần xử lý tuần tự từng phần tử, dùng `concatMap`:

```java
Flux<Result> sequential = inputs.concatMap(this::process);
```

Concurrency quá cao làm tăng số kết nối DB/HTTP, số object đang sống và số kết quả đang chờ downstream. Prefetch quá lớn có thể làm tăng queue. Hãy đặt concurrency theo năng lực thực tế của dependency và ngân sách bộ nhớ, sau đó đo latency/error/queue.

### 5.1. Giới hạn số phần tử và thời gian stream

Một stream vô hạn cần có vòng đời và quota rõ ràng. Có thể giới hạn số phần tử:

```java
Flux<Event> firstThousand = eventSource.take(1_000);
```

Hoặc timeout nếu upstream không phát tín hiệu trong khoảng thời gian cho phép:

```java
Mono<Response> response = remoteCall()
        .timeout(Duration.ofSeconds(3));
```

Với `Flux.timeout(Duration)`, timeout thường áp dụng cho khoảng chờ giữa các tín hiệu; một stream vẫn hoạt động đều có thể chạy lâu. Nếu nghiệp vụ yêu cầu deadline tổng thể, hãy thiết kế deadline/cancellation riêng cho toàn request.

Timeout không phải cách giải quyết queue đầy. Nó chỉ kết thúc công việc khi điều kiện thời gian bị vi phạm; queue vẫn cần giới hạn và overflow policy.

## 6. Ngân sách bộ nhớ: giới hạn queue theo kích thước dữ liệu

Backpressure đếm số item, trong khi heap được tiêu thụ theo byte và object overhead. Buffer 1.000 phần tử nhỏ khác rất nhiều buffer 1.000 phần tử chứa JSON lớn.

Nếu mỗi client có queue riêng, có thể ước lượng payload thô:

```text
Memory payload ≈ số client chậm
               × số item tối đa mỗi queue
               × kích thước trung bình mỗi item
```

Ví dụ:

- 150 client đồng thời chậm.
- Mỗi client được giữ tối đa 64 item.
- Mỗi item có payload trung bình 2 KiB.

Ước lượng payload là:

```text
150 × 64 × 2 KiB = 19,660,800 bytes ≈ 18.75 MiB
```

Đây chỉ là payload thô. Object header, reference, queue node, byte buffer, encoder và transport buffer làm mức sử dụng thực tế cao hơn. Nếu một pipeline có nhiều queue, phải cộng ngân sách của từng tầng.

Một cấu hình an toàn thường có:

- Giới hạn số client/kết nối đồng thời.
- Giới hạn queue hoặc buffer trên mỗi client.
- Giới hạn kích thước một item và tổng body khi cần.
- Giới hạn concurrency/prefetch cho công việc I/O.
- Timeout và cancellation để giải phóng tài nguyên.
- Metric cho queue depth, overflow, dropped item, active stream và thời gian xử lý.

Không chọn buffer capacity chỉ dựa trên một lần benchmark nhanh. Hãy kiểm tra khi có nhiều client chậm đồng thời và payload ở kích thước lớn gần giới hạn.

## 7. Giới hạn request body và codec trong WebFlux

Một vấn đề khác là client gửi body lớn hoặc rất chậm. Khi dùng `bodyToMono(MyDto.class)` hoặc `@RequestBody MyDto`, codec thường cần tích lũy đủ nội dung để decode thành object. Nếu body vượt giới hạn bộ nhớ cấu hình, WebFlux có thể phát `DataBufferLimitException`.

Có thể đặt giới hạn bộ nhớ cho codec bằng cấu hình Spring Boot:

```properties
spring.codec.max-in-memory-size=1MB
```

Hoặc cấu hình trực tiếp:

```java
@Configuration
public class WebFluxCodecConfig implements WebFluxConfigurer {
    @Override
    public void configureHttpMessageCodecs(
            ServerCodecConfigurer configurer) {
        configurer.defaultCodecs().maxInMemorySize(1024 * 1024);
    }
}
```

Giới hạn này áp dụng cho dữ liệu codec phải buffer/aggregate trong quá trình đọc hoặc ghi. Nó **không phải quota byte tổng quát cho mọi request streaming** nếu ứng dụng tự tiêu thụ `Flux<DataBuffer>` và không gom body vào memory. Với upload hoặc API cần giới hạn tổng request bytes, cần thêm giới hạn ở server/proxy hoặc đếm byte trong pipeline rồi hủy request khi vượt ngưỡng.

### 7.1. Streaming body thay vì gom tất cả

Với file lớn hoặc dữ liệu liên tục, tránh đọc toàn bộ vào một `byte[]` hoặc `List<T>`:

```java
@PostMapping("/import")
public Mono<Void> importData(@RequestBody Flux<ImportRow> rows) {
    return rows
            .limitRate(32)
            .concatMap(importService::process);
}
```

Đây là **đoạn minh họa**. `concatMap` xử lý từng row tuần tự và chỉ chuyển tiếp theo demand; `limitRate` điều chỉnh batch request. Nếu cần xử lý song song, đặt concurrency hữu hạn bằng `flatMap(mapper, concurrency, prefetch)`.

Tránh:

```java
return rows.collectList()
        .flatMap(importService::processAll);
```

`collectList()` giữ toàn bộ phần tử cho đến khi nguồn hoàn tất. Với stream dài hoặc không kết thúc, bộ nhớ có thể tăng không giới hạn hoặc operation không bao giờ chạy tới bước xử lý cuối. Chỉ dùng khi kích thước đầu vào đã có giới hạn rõ và việc gom toàn bộ là yêu cầu thực sự.

### 7.2. Đếm byte khi phải giới hạn raw body

Nếu cần giới hạn tổng byte của raw body, có thể đếm `DataBuffer.readableByteCount()` trong pipeline và hủy khi vượt ngưỡng. Ví dụ minh họa:

```java
AtomicLong received = new AtomicLong();

Flux<DataBuffer> boundedBody = request.getBody()
        .handle((buffer, sink) -> {
            long total = received.addAndGet(buffer.readableByteCount());
            if (total > MAX_BODY_BYTES) {
                DataBufferUtils.release(buffer);
                sink.error(new PayloadTooLargeException());
            } else {
                sink.next(buffer);
            }
        });
```

Đây là **mã minh họa tầng thấp**, không phải đoạn copy/paste hoàn chỉnh cho mọi transport. Khi chuyển buffer downstream, phải bảo toàn ownership; khi discard/cancel/error phải giải phóng buffer đúng một lần. Cần kiểm tra cả đường buffer bị drop/discard và cách server kết thúc request. Với endpoint thông thường, ưu tiên giới hạn của server/codec và body DTO có kích thước hữu hạn thay vì tự xử lý DataBuffer.

## 8. Xử lý slow HTTP client và cancellation

Khi client đọc response chậm, demand ở phía HTTP writer có thể giảm. Nếu upstream reactive có thể tuân theo demand, nó sẽ phát chậm hơn. Nếu upstream là hot source, buffer/overflow policy quyết định điều gì xảy ra.

Khi client đóng kết nối, subscriber có thể gửi `cancel`. Pipeline nên truyền cancellation upstream để dừng query, timer hoặc công việc không còn cần thiết. Không giữ subscription trong field singleton và không tạo subscription phụ bằng `subscribe()`.

Ví dụ quan sát lifecycle:

```java
return eventService.stream()
        .doOnCancel(() -> log.info("client cancelled stream"))
        .doFinally(signal -> releaseRequestResources());
```

Đây là **đoạn minh họa**. `doOnCancel` quan sát cancellation; `doFinally` chạy khi complete, error hoặc cancel. Cleanup cần idempotent nếu có nhiều đường kết thúc và phải dùng API phù hợp cho resource bất đồng bộ.

### 8.1. Timeout và idle client

Timeout giúp tránh giữ tài nguyên vô thời hạn khi upstream ngừng phát hoặc dependency phản hồi quá chậm. Tuy nhiên, timeout giữa các event và deadline tổng thể là hai mục tiêu khác nhau.

Với stream SSE, nếu đã gửi response headers và một số event, timeout không thể biến status thành 504 kèm JSON body mới. Có thể phát event lỗi theo schema đã định nghĩa hoặc kết thúc stream. Với request chưa commit response, lỗi timeout có thể được map sang status thích hợp qua error handler.

### 8.2. Không retry vô hạn khi overflow

Khi queue đầy, retry ngay lập tức có thể làm producer phát thêm dữ liệu và khiến queue càng nhanh đầy. Retry chỉ có ý nghĩa khi có điều kiện phục hồi, giới hạn số lần và backoff. Với producer cần được chấp nhận rõ ràng, trả 429/503 hoặc ghi vào durable queue để client/worker xử lý lại theo contract.

## 9. Chương trình Spring Boot 3.3.5 chạy được

Ví dụ dùng **Java 17+**, **Maven**, **Spring Boot 3.3.5** và `spring-boot-starter-webflux`. Một nguồn nóng phát sự kiện qua Reactor Sink có buffer tối đa 32 item. Khi consumer chậm làm buffer đầy, producer nhận kết quả overflow và endpoint trả HTTP 503 thay vì tiếp tục tích lũy bộ nhớ.

Cấu trúc:

```text
webflux-backpressure-demo/
├── pom.xml
└── src/
    ├── main/java/demo/
    │   ├── BackpressureApplication.java
    │   ├── ReadingFeed.java
    │   └── ReadingController.java
    └── test/java/demo/
        └── ReadingControllerTest.java
```

### 9.1. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>webflux-backpressure-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

### 9.2. application.properties

```properties
server.port=8080
spring.codec.max-in-memory-size=1MB
```

Giới hạn codec ở đây là 1 MiB cho các trường hợp cần buffer/aggregate; body streaming thô vẫn cần chính sách giới hạn tổng byte riêng nếu API yêu cầu.

### 9.3. BackpressureApplication.java

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BackpressureApplication {
    public static void main(String[] args) {
        SpringApplication.run(BackpressureApplication.class, args);
    }
}
```

### 9.4. ReadingFeed.java

```java
package demo;

import org.springframework.stereotype.Component;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Sinks;

@Component
public class ReadingFeed {
    private final Sinks.Many<Reading> sink;
    private long nextId;

    public ReadingFeed() {
        this(32);
    }

    ReadingFeed(int capacity) {
        this.sink = Sinks.many()
                .multicast()
                .onBackpressureBuffer(capacity);
    }

    public Flux<Reading> stream() {
        return sink.asFlux();
    }

    public synchronized Sinks.EmitResult publish(String value) {
        long id = nextId + 1;
        Sinks.EmitResult result =
                sink.tryEmitNext(new Reading(id, value));

        if (result.isSuccess()) {
            nextId = id;
        }
        return result;
    }

    public record Reading(long id, String value) {}
}
```

`Sinks.Many` là nguồn nóng có thể nhận dữ liệu từ producer bên ngoài. `onBackpressureBuffer(32)` tạo buffer hữu hạn cho multicast sink. Phương thức `tryEmitNext` trả kết quả ngay; khi buffer đầy, kết quả là `FAIL_OVERFLOW`. Phương thức publish được đồng bộ hóa để các producer trong ví dụ phát tuần tự, tránh `FAIL_NON_SERIALIZED` do hai thread emit đồng thời. Không có thao tác I/O blocking trong vùng đồng bộ này.

### 9.5. ReadingController.java

```java
package demo;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.publisher.Sinks;

@RestController
public class ReadingController {
    private final ReadingFeed feed;

    public ReadingController(ReadingFeed feed) {
        this.feed = feed;
    }

    public record PublishRequest(String value) {}
    public record PublishResult(String status) {}

    @PostMapping(
            value = "/readings",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<ResponseEntity<PublishResult>> publish(
            @RequestBody PublishRequest request) {

        if (request.value() == null || request.value().isBlank()) {
            return Mono.just(ResponseEntity.badRequest()
                    .body(new PublishResult("VALUE_REQUIRED")));
        }

        Sinks.EmitResult result = feed.publish(request.value());

        if (result.isSuccess()) {
            return Mono.just(ResponseEntity.accepted()
                    .body(new PublishResult("QUEUED")));
        }

        String code = result == Sinks.EmitResult.FAIL_OVERFLOW
                ? "BACKPRESSURE_OVERFLOW"
                : "FEED_UNAVAILABLE";

        return Mono.just(ResponseEntity.status(
                        HttpStatus.SERVICE_UNAVAILABLE)
                .body(new PublishResult(code)));
    }

    @GetMapping(
            value = "/events",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<ServerSentEvent<ReadingFeed.Reading>> events() {
        return feed.stream()
                .limitRate(16)
                .map(reading -> ServerSentEvent.builder(reading)
                        .id(Long.toString(reading.id()))
                        .event("reading")
                        .build());
    }
}
```

Endpoint `POST /readings` nhận dữ liệu từ producer và trả 202 khi sink chấp nhận. Khi buffer đầy, nó trả 503 với code `BACKPRESSURE_OVERFLOW`. Endpoint `GET /events` stream các reading qua SSE. `limitRate(16)` điều tiết batch demand của subscriber; nó không phải giới hạn 16 event mỗi giây. Buffer 32 trong sink là giới hạn hàng chờ của ví dụ.

### 9.6. Chạy và quan sát

Tại thư mục chứa `pom.xml`:

```bash
mvn spring-boot:run
```

Mở một terminal để nhận SSE:

```bash
curl -N -H "Accept: text/event-stream" http://localhost:8080/events
```

Ở terminal khác, gửi một reading:

```bash
curl -i -X POST http://localhost:8080/readings \
  -H "Content-Type: application/json" \
  -d '{"value":"temperature=25"}'
```

Response POST khi sink nhận dữ liệu:

```http
HTTP/1.1 202 Accepted
Content-Type: application/json

{"status":"QUEUED"}
```

Terminal SSE nhận event có dạng:

```text
id:1
event:reading
data:{"id":1,"value":"temperature=25"}

```

ID tăng theo reading được sink chấp nhận. Dữ liệu JSON và thứ tự field minh họa theo record/Jackson; header phụ thuộc server và cấu hình môi trường.

Nếu có subscriber không yêu cầu/tiêu thụ đủ nhanh, buffer hữu hạn có thể đầy. Khi đó producer nhận `FAIL_OVERFLOW` và endpoint trả HTTP 503. Trong một hệ thống thực tế, hãy đo overflow và quyết định producer có retry với backoff, ghi durable queue hay báo lỗi cho upstream.

## 10. Kiểm thử backpressure và overflow

Ví dụ test dưới đây kiểm tra hai điều:

1. Một client SSE đã subscribe nhận event do POST publish.
2. Một subscriber chưa yêu cầu phần tử chỉ có thể để buffer giữ tối đa hai reading; lần emit thứ ba nhận `FAIL_OVERFLOW`.

```java
package demo;

import java.time.Duration;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.test.web.reactive.server.WebTestClient;
import reactor.core.publisher.Sinks;
import reactor.test.StepVerifier;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class ReadingControllerTest {
    @Autowired
    WebTestClient client;

    @Test
    void connectedSseClientReceivesPublishedReading() {
        var result = client.get()
                .uri("/events")
                .accept(MediaType.TEXT_EVENT_STREAM)
                .exchange()
                .expectStatus().isOk()
                .returnResult(
                        new ParameterizedTypeReference<
                                ServerSentEvent<ReadingFeed.Reading>>() {});

        StepVerifier.create(result.getResponseBody())
                .then(() -> client.post()
                        .uri("/readings")
                        .contentType(MediaType.APPLICATION_JSON)
                        .bodyValue(
                                new ReadingController.PublishRequest(
                                        "temperature=25"))
                        .exchange()
                        .expectStatus().isAccepted())
                .assertNext(event -> {
                    assertThat(event.event()).isEqualTo("reading");
                    assertThat(event.data().value())
                            .isEqualTo("temperature=25");
                })
                .thenCancel()
                .verify(Duration.ofSeconds(3));
    }

    @Test
    void boundedSinkRejectsThirdItemWhenSubscriberHasNoDemand() {
        ReadingFeed feed = new ReadingFeed(2);

        StepVerifier.create(feed.stream(), 0)
                .then(() -> {
                    assertThat(feed.publish("one"))
                            .isEqualTo(Sinks.EmitResult.OK);
                    assertThat(feed.publish("two"))
                            .isEqualTo(Sinks.EmitResult.OK);
                    assertThat(feed.publish("three"))
                            .isEqualTo(Sinks.EmitResult.FAIL_OVERFLOW);
                })
                .thenRequest(2)
                .expectNextMatches(reading ->
                        reading.value().equals("one"))
                .expectNextMatches(reading ->
                        reading.value().equals("two"))
                .thenCancel()
                .verify(Duration.ofSeconds(2));
    }
}
```

Dependency `reactor-test` đã được thêm trong `pom.xml` để dùng `StepVerifier`. Chạy:

```bash
mvn test
```

Test thứ nhất kiểm tra đường HTTP/SSE end-to-end. Test thứ hai mô phỏng subscriber chưa có demand và xác nhận buffer có capacity 2 từ chối item thứ ba. Khi chạy test thực tế, cần giữ đúng version Reactor do Spring Boot BOM quản lý.

## 11. Đo lường và vận hành

Không thể đánh giá backpressure chỉ bằng việc ứng dụng không crash. Cần quan sát cả tốc độ producer, tốc độ consumer và queue.

Các chỉ số hữu ích:

| Chỉ số | Cho biết | Cách dùng |
| --- | --- | --- |
| Active streams/connections | Số consumer đang mở | Đặt giới hạn và phát hiện client treo. |
| Queue depth / buffer occupancy | Mức dữ liệu đang chờ | Cảnh báo trước khi overflow. |
| Overflow count | Số lần buffer đầy | Điều chỉnh producer, consumer hoặc policy. |
| Dropped/latest replaced count | Số item không được chuyển tiếp | Đánh giá mức mất dữ liệu có chấp nhận được. |
| Demand/request rate | Tốc độ subscriber yêu cầu item | Phát hiện consumer chậm. |
| Producer rate / consumer rate | Chênh lệch tốc độ | Xác định bottleneck. |
| End-to-end latency | Thời gian từ phát tới xử lý | Phát hiện queue làm dữ liệu cũ. |
| Cancellation/timeout count | Stream bị hủy hoặc quá hạn | Phân biệt client disconnect với lỗi server. |
| Heap/direct memory | Áp lực bộ nhớ | Phát hiện buffer/object accumulation. |

Khi buffer thường xuyên đạt gần capacity, hãy xem đó là tín hiệu hệ thống đang thiếu năng lực tiêu thụ hoặc policy không phù hợp. Tăng capacity chỉ nên là quyết định có ngân sách và thời gian rõ ràng; nếu tốc độ producer luôn lớn hơn consumer, queue lớn hơn chỉ kéo dài thời gian tới overflow.

## 12. Rate limiting khác backpressure

Hai khái niệm thường được nhắc cùng nhau nhưng giải quyết hai vấn đề khác nhau:

| Cơ chế | Giới hạn điều gì? | Ví dụ |
| --- | --- | --- |
| Backpressure | Số phần tử subscriber sẵn sàng nhận | `request(32)`, `limitRate(32)` |
| Bounded buffering | Số phần tử có thể chờ | `onBackpressureBuffer(128)` |
| Rate limiting | Số request/event trong một khoảng thời gian | 100 request/phút theo client |
| Concurrency limiting | Số tác vụ đang chạy đồng thời | `flatMap(mapper, 8, 1)` |
| Payload/body limit | Kích thước byte hoặc item | codec max memory, max upload bytes |
| Timeout/deadline | Thời gian chờ hoặc thời gian xử lý | `timeout(Duration.ofSeconds(3))` |

Một client có thể gửi ít request mỗi giây nhưng mỗi request tải file rất lớn. Một stream có thể có demand tốt nhưng item rất lớn. Một nguồn có thể phát 10 item/giây nhưng mỗi item kích hoạt 100 tác vụ đồng thời. Vì vậy, hệ thống thực tế cần phối hợp nhiều giới hạn.

`limitRate` không thay thế token bucket hoặc rate limiter ở API gateway. `onBackpressureBuffer` không thay thế giới hạn body. `timeout` không thay thế giới hạn queue.

## 13. Lỗi thường gặp và cách xử lý

| Sai lầm | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Cho rằng WebFlux tự bảo đảm bộ nhớ không tăng | Hot source, proxy hoặc queue vẫn có thể buffer | Xác định từng tầng và đặt giới hạn hữu hạn. |
| Dùng buffer vô hạn cho producer nhanh | Heap tăng theo thời gian khi consumer luôn chậm | Dùng buffer có capacity và overflow policy. |
| Chỉ tăng buffer khi overflow | Chỉ trì hoãn lỗi nếu producer liên tục nhanh hơn consumer | Đo tốc độ, giảm producer, tăng consumer hoặc drop/reject có chủ đích. |
| Dùng `limitRate(32)` như rate limit 32 event/giây | Hiểu sai demand batching thành tốc độ theo thời gian | Dùng rate limiter/token bucket hoặc pacing theo thời gian. |
| Dùng `onBackpressureDrop` cho audit event | Mất dữ liệu không thể tái tạo | Dùng durable queue/acknowledgement hoặc reject producer. |
| Dùng `onBackpressureLatest` cho command | Lệnh cũ có thể bị thay thế | Chỉ dùng cho state snapshot có thể bỏ qua trung gian. |
| Gom stream vô hạn bằng `collectList()` | Không hoàn tất hoặc cạn bộ nhớ | Xử lý từng item, window/chunk hoặc giới hạn số phần tử. |
| Đặt concurrency quá lớn trong `flatMap` | Mở quá nhiều request DB/HTTP và tăng memory | Chọn concurrency/prefetch theo năng lực dependency. |
| Nghĩ codec max memory là giới hạn mọi request bytes | Raw streaming body vẫn có thể vượt tổng số byte đó | Thêm tổng body limit ở server/proxy hoặc đếm byte trong pipeline. |
| Không xử lý cancellation khi client disconnect | Công việc upstream vẫn chạy và giữ resource | Truyền cancellation, cleanup bằng lifecycle hook phù hợp. |
| Retry ngay khi buffer đầy | Producer có thể làm quá tải nặng hơn | Backoff, giới hạn retry hoặc reject rõ ràng. |
| Chỉ đo CPU mà không đo queue | Queue tăng trước khi CPU đạt cao | Theo dõi queue depth, overflow, dropped count và latency. |
| Gọi `subscribe()` riêng để tiêu thụ stream | Tạo pipeline tách rời, khó điều tiết và hủy | Return/compose publisher trong request lifecycle. |
| Đọc toàn bộ file/body vào byte array | Tạo bản sao lớn và mất streaming | Dùng `Flux<DataBuffer>` hoặc streaming codec. |
| Không giới hạn số client SSE | Mỗi kết nối có thể giữ subscription và buffer riêng | Giới hạn concurrent streams và đặt quota theo user/tenant. |
| Trả 200 khi producer bị từ chối do overflow | Client tưởng event đã được nhận | Trả 429/503 hoặc contract lỗi rõ ràng. |

## 14. Câu hỏi tự kiểm tra

**Câu 1.** Backpressure trong Reactive Streams được biểu diễn bằng tín hiệu nào?  
**Đáp án:** Subscriber gọi `Subscription.request(n)` để báo số phần tử muốn nhận; publisher tuân theo demand không phát quá số lượng đã yêu cầu.

**Câu 2.** Vì sao hot source cần overflow policy?  
**Đáp án:** Nguồn nóng có thể phát theo clock/callback riêng và không tạm dừng khi downstream giảm demand. Dữ liệu chưa tiêu thụ cần được buffer hữu hạn, drop, latest hoặc reject/error.

**Câu 3.** `limitRate(64)` có nghĩa tối đa 64 item mỗi giây không?  
**Đáp án:** Không. Nó điều chỉnh cách Reactor phát request theo batch; không phải time-based rate limiter.

**Câu 4.** Khi nào dùng `onBackpressureLatest`?  
**Đáp án:** Khi chỉ cần trạng thái mới nhất, như nhiệt độ hiện tại hoặc dashboard state; các giá trị trung gian có thể bỏ.

**Câu 5.** Tại sao không nên dùng buffer vô hạn?  
**Đáp án:** Nếu producer lâu dài nhanh hơn consumer, queue tăng không giới hạn và có thể làm cạn heap/direct memory.

**Câu 6.** `flatMap(mapper, 8, 1)` kiểm soát điều gì?  
**Đáp án:** Tối đa tám inner publisher được xử lý đồng thời và prefetch một phần tử cho mỗi inner publisher.

**Câu 7.** `spring.codec.max-in-memory-size` giới hạn điều gì?  
**Đáp án:** Giới hạn dữ liệu codec cần buffer/aggregate trong một số thao tác encode/decode; không tự tạo quota byte tổng quát cho mọi raw streaming request.

**Câu 8.** Client ngắt SSE thì reactive pipeline nên nhận tín hiệu gì?  
**Đáp án:** Subscriber có thể cancel; cancellation nên truyền upstream để dừng producer/query và giải phóng tài nguyên.

**Câu 9.** Vì sao không nên retry liên tục khi sink trả FAIL_OVERFLOW?  
**Đáp án:** Queue chưa có chỗ trống; retry ngay làm producer tiếp tục gây áp lực. Cần backoff, giảm tốc, durable queue hoặc trả lỗi để upstream quyết định.

**Câu 10.** Một queue 64 item có chắc chắn chỉ dùng ít bộ nhớ không?  
**Đáp án:** Không. Phải xét kích thước trung bình/tối đa của mỗi item, số client, object overhead và các buffer ở tầng khác.

## Ghi nhớ

- Backpressure là demand-based flow control giữa publisher và subscriber; demand đếm item, không đếm byte.
- Nguồn có thể tuân theo demand nên được để backpressure truyền ngược. Hot source cần chính sách rõ ràng khi consumer chậm.
- Buffer phải hữu hạn. Chọn buffer/drop/latest/error theo semantics; không âm thầm bỏ sự kiện nghiệp vụ quan trọng.
- `limitRate` điều chỉnh request theo batch, không giới hạn tốc độ theo giây. Dùng rate limiter riêng khi cần quota thời gian.
- Giới hạn concurrency/prefetch, body bytes, codec memory, số item, số kết nối và timeout để quản lý ngân sách tài nguyên.
- Khi client cancel hoặc queue overflow, truyền tín hiệu đúng lifecycle; đo queue, dropped, overflow, latency và memory để vận hành có căn cứ.

### Tài liệu tham khảo

1. [Reactive Streams Specification](https://www.reactive-streams.org/): publisher, subscriber, subscription và demand.
2. [Project Reactor Reference – Backpressure](https://projectreactor.io/docs/core/release/reference/coreFeatures/backpressure.html): demand, backpressure operators và xử lý nguồn nóng.
3. [Project Reactor Flux Javadoc](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html): `limitRate`, `onBackpressureBuffer`, `onBackpressureDrop`, `onBackpressureLatest` và `flatMap`.
4. [Project Reactor Sinks Reference](https://projectreactor.io/docs/core/release/reference/coreFeatures/sinks.html): tạo hot source, multicast và xử lý emit result.
5. [Spring Framework – WebFlux Reactive Core](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html): reactive server, publisher và WebFlux lifecycle.
6. [Spring Framework – WebFlux Codec Configuration](https://docs.spring.io/spring-framework/reference/web/webflux/config.html): cấu hình message codecs và giới hạn buffering.
7. [Spring Boot – Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/index.html): cấu hình `spring.codec.max-in-memory-size`.
