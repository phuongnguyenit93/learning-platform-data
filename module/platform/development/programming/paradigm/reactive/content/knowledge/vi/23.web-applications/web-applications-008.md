# Áp lực ngược qua ranh giới HTTP và giới hạn của giao thức

Trong **REACTIVE_PROGRAMMING**, `Mono` và `Flux` truyền dữ liệu bất đồng bộ qua hợp đồng `Publisher–Subscriber`. Subscriber có thể yêu cầu số phần tử bằng `request(n)`, nhờ đó upstream điều tiết lượng dữ liệu được phát. Khi pipeline đi qua một ứng dụng web, dữ liệu còn phải đi qua HTTP server/client, socket, TCP hoặc QUIC, proxy và các bộ đệm của hệ điều hành.

Điểm quan trọng là **HTTP không truyền trực tiếp tín hiệu Reactive Streams `request(n)` qua mạng**. Các tầng mạng có cơ chế flow control riêng, thường tính theo byte hoặc cửa sổ truyền tải. Spring WebFlux và Reactor Netty có thể phối hợp demand của Publisher với khả năng đọc/ghi của transport, nhưng các buffer ở client, server, proxy và kernel khiến backpressure không phải lúc nào cũng lan truyền nguyên vẹn từ consumer cuối đến producer từ xa.

## 1. Hai lớp điều tiết khác nhau

Reactive Streams và HTTP flow control cùng giúp tránh gửi dữ liệu vượt quá khả năng tiếp nhận, nhưng hoạt động ở các lớp khác nhau:

| Cơ chế | Đơn vị điều tiết | Phạm vi | Tín hiệu chính |
|---|---|---|---|
| Reactive Streams backpressure | Phần tử (`onNext`) | Giữa Publisher và Subscriber trong một pipeline | `Subscription.request(n)` và `cancel()` |
| TCP flow control | Byte | Giữa hai đầu TCP | Receive window và ACK |
| HTTP/2 flow control | Byte trong từng stream và connection | Các stream HTTP/2 trên một connection | WINDOW_UPDATE và kích thước cửa sổ |
| HTTP/3 flow control | Byte trong stream và connection QUIC | Các stream QUIC | MAX_DATA và MAX_STREAM_DATA |
| Application rate limit | Request hoặc thao tác trong một khoảng thời gian | API hoặc nghiệp vụ | Token bucket, quota, 429/Retry-After |

Ví dụ, một Subscriber gọi `request(10)` có nghĩa nó sẵn sàng nhận tối đa mười phần tử tiếp theo theo hợp đồng Reactive Streams. Điều này không tương đương với việc mở một cửa sổ mạng đủ chứa mười message. Mỗi message có thể có kích thước khác nhau; transport thường kiểm soát byte chứ không hiểu ý nghĩa của một đối tượng Java.

Ngược lại, TCP receive window còn chỗ không có nghĩa Subscriber đã yêu cầu thêm phần tử. Socket có thể nhận và giữ byte trong buffer trong khi ứng dụng chưa giải mã hoặc chưa tiêu thụ chúng.

## 2. HTTP không có trường request(n) của Reactive Streams

Trong cùng một tiến trình Java, một `Flux<T>` có thể truyền demand ngược qua các operator đến nguồn. Khi đi qua HTTP, request và response được biểu diễn bằng message, header và body theo giao thức HTTP. Không có header chuẩn nào tương đương với `Subscription.request(64)` cho từng phần tử của một response thông thường.

Vì vậy, không nên suy luận rằng:

- Client gọi `request(1)` thì server từ xa chắc chắn chỉ tạo một bản ghi.
- `limitRate(32)` ở một phía sẽ buộc producer ở phía kia chỉ phát 32 phần tử mỗi lần.
- TCP window đầy thì ứng dụng server chắc chắn biết Subscriber Java đang thiếu demand.
- HTTP chunked transfer tự cung cấp backpressure ở mức phần tử.

Framework và connector có thể chuyển trạng thái demand thành việc tạm dừng đọc socket, điều chỉnh việc ghi hoặc hủy request. Đây là sự phối hợp giữa nhiều tầng implementation, không phải một tín hiệu `request(n)` được gửi nguyên dạng qua HTTP.

## 3. HTTP/1.1, HTTP/2 và HTTP/3 kiểm soát truyền dữ liệu ra sao?

### HTTP/1.1 và TCP

HTTP/1.1 thường dùng một kết nối TCP cho một trao đổi đang hoạt động tại một thời điểm trên connection đó, trừ các cơ chế pipelining ít được dùng. TCP điều tiết byte bằng receive window. Nếu phía nhận đọc chậm, buffer TCP có thể đầy và cửa sổ nhận thu hẹp, khiến phía gửi giảm tốc hoặc chờ.

Chunked transfer encoding chia body thành các chunk để truyền nội dung có độ dài chưa biết trước. Chunk là cách đóng khung body, không phải cơ chế demand theo từng phần tử. Ứng dụng vẫn cần tự quản lý việc giải mã, buffer và tốc độ tiêu thụ.

### HTTP/2

HTTP/2 multiplex nhiều stream trên một connection. Nó có flow control ở hai cấp: cửa sổ của từng stream và cửa sổ chung của connection. Điều này giúp một stream có thể bị điều tiết mà không nhất thiết dừng mọi stream khác trên connection.

Các cửa sổ HTTP/2 tính theo byte. Chúng không biết một phần tử `Event` trong `Flux<Event>` tương ứng bao nhiêu đối tượng nghiệp vụ; việc ánh xạ giữa frame, byte và phần tử được thực hiện ở tầng codec/application.

### HTTP/3

HTTP/3 chạy trên QUIC. QUIC cung cấp flow control cho connection và từng stream, đồng thời xử lý truyền tải trên UDP. Cửa sổ vẫn kiểm soát lượng byte có thể được gửi trước khi cần cập nhật giới hạn mới; nó không thay thế demand ở cấp Publisher.

## 4. Backpressure khi server phát response streaming

Spring WebFlux cho phép controller trả `Flux` để phát response theo từng phần tử, chẳng hạn NDJSON hoặc Server-Sent Events (SSE):

```java
@RestController
class EventController {

    private final EventService eventService;

    EventController(EventService eventService) {
        this.eventService = eventService;
    }

    @GetMapping(value = "/events", produces = MediaType.APPLICATION_NDJSON_VALUE)
    Flux<EventView> events() {
        return eventService.stream()
            .limitRate(64)
            .map(EventView::from);
    }
}
```

`limitRate(64)` điều chỉnh cách Reactor chia nhỏ demand gửi upstream trong pipeline của server. Nó có thể giúp giới hạn lượng phần tử được yêu cầu trước từ `eventService`, tùy operator và nguồn. Nó không đặt quota 64 message cho mỗi giây và cũng không gửi một lệnh `request(64)` qua HTTP đến producer từ xa.

Khi client đọc response chậm, WebFlux/connector có thể điều phối việc ghi dựa trên khả năng ghi của channel và trạng thái subscription. Tuy nhiên, dữ liệu vẫn có thể đang nằm trong queue của operator, buffer của Netty, kernel socket buffer, reverse proxy hoặc thư viện phía client. Vì vậy, cần giới hạn buffer ở những nơi ứng dụng kiểm soát được và đo hành vi thực tế qua toàn tuyến.

## 5. Backpressure khi server nhận request body streaming

Với request body lớn hoặc dạng stream, tránh gom toàn bộ body vào một collection nếu nghiệp vụ có thể xử lý từng phần tử. Một endpoint nhận NDJSON có thể dùng `Flux<EventInput>`:

```java
@PostMapping(
    path = "/events/import",
    consumes = MediaType.APPLICATION_NDJSON_VALUE
)
Mono<Void> importEvents(@RequestBody Flux<EventInput> events) {
    return events
        .limitRate(64)
        .flatMap(eventService::store, 8)
        .then();
}
```

`flatMap(..., 8)` giới hạn tối đa tám Publisher con đang được xử lý đồng thời tại operator đó. `limitRate(64)` điều chỉnh demand theo từng đợt lên upstream. Nếu `store` là thao tác bất đồng bộ và tôn trọng cancellation, pipeline có thể điều tiết việc tiêu thụ body khi các tác vụ lưu trữ chậm.

Đây là giới hạn ở tầng ứng dụng. Trước khi controller nhận `EventInput`, byte có thể đã được đọc vào socket buffer, Netty buffer hoặc codec buffer. Nếu một proxy phía trước đã nhận toàn bộ request body, demand của controller không làm proxy trả lại byte đã buffer. Hãy kiểm tra cấu hình buffering và giới hạn body ở ingress/reverse proxy khi xử lý upload lớn.

## 6. Không gom body lớn vào bộ nhớ một cách vô tình

Các thao tác như `collectList()`, `DataBufferUtils.join(...)` hoặc giải mã một body lớn thành một object duy nhất có thể cần giữ nhiều dữ liệu trong bộ nhớ. Chúng phù hợp khi kích thước body có giới hạn và ứng dụng thực sự cần toàn bộ nội dung cùng lúc.

Với stream lớn, ưu tiên xử lý từng phần tử hoặc từng buffer. Nếu API cần aggregate, đặt giới hạn kích thước rõ ràng. Ví dụ, Spring codec có thể cấu hình `maxInMemorySize` cho các trường hợp cần buffer để giải mã:

```java
ExchangeStrategies strategies = ExchangeStrategies.builder()
    .codecs(codecs -> codecs.defaultCodecs()
        .maxInMemorySize(256 * 1024))
    .build();

WebClient client = WebClient.builder()
    .exchangeStrategies(strategies)
    .build();
```

Giới hạn này áp dụng cho các đường giải mã cần buffer nội dung trong codec; nó không phải giới hạn tổng byte của mọi response streaming. Với stream được giải mã và tiêu thụ từng phần tử, cần xem thêm giới hạn ở operator, queue, client và proxy.

Nếu làm việc trực tiếp với `DataBuffer` pooled, cần quản lý ownership và release khi phần tử được tiêu thụ hoặc bị discard. Không được giữ buffer trong collection vô thời hạn hoặc release buffer trong khi downstream vẫn còn tham chiếu đến vùng nhớ của nó.

## 7. Client đọc response chậm

Một client WebClient có thể tiêu thụ response dưới dạng `Flux` và điều chỉnh demand ở phía ứng dụng:

```java
Flux<EventView> events = webClient.get()
    .uri("/events")
    .accept(MediaType.APPLICATION_NDJSON)
    .retrieve()
    .bodyToFlux(EventView.class)
    .limitRate(32);
```

`limitRate(32)` ảnh hưởng đến demand mà pipeline Reactor phía client truyền lên decoder/source. Nó không đảm bảo server từ xa biết con số 32 hoặc dừng tạo event ngay lập tức. Nếu client ngừng đọc, transport flow control có thể làm chậm việc truyền byte; các buffer ở server, proxy và mạng vẫn có thể chứa dữ liệu đã được gửi trước đó.

Nếu consumer không còn cần response, hãy hủy subscription. Ví dụ, `take(100)` hoàn tất sau 100 phần tử và yêu cầu hủy upstream:

```java
Flux<EventView> firstHundred = events.take(100);
```

Cancellation có thể khiến client đóng hoặc ngừng đọc response. Server có thể nhận biết peer đóng kết nối hoặc stream bị reset và dừng công việc tương ứng, nhưng thời điểm nhận biết phụ thuộc transport, proxy và cách server xử lý disconnect.

## 8. Buffer ở proxy và gateway có thể làm thay đổi hành vi

Một tuyến HTTP thường không chỉ có hai đầu:

```text
Producer
   |
   v
HTTP server / Reactor Netty
   |
   v
Ingress / reverse proxy / API gateway
   |
   v
Network buffers
   |
   v
HTTP client / decoder
   |
   v
Reactive Subscriber
```

Mỗi tầng có thể đọc trước và buffer dữ liệu. Một reverse proxy có thể buffer request body trước khi chuyển đến upstream, hoặc buffer response trước khi gửi đến client. Khi đó, client chậm không nhất thiết làm producer ứng dụng chậm ngay; proxy có thể tiếp tục nhận và giữ dữ liệu cho đến khi buffer đạt giới hạn.

Với response streaming, cần kiểm tra tính năng response buffering của proxy và cấu hình tương ứng. Với upload, cần kiểm tra request buffering, giới hạn body, timeout và dung lượng tạm. Tên cấu hình cụ thể tùy sản phẩm ingress/gateway đang dùng; không nên giả định WebFlux có thể điều khiển queue của proxy.

Nếu cần streaming thực sự, hãy xác minh dữ liệu được chuyển tiếp theo từng phần tử hoặc chunk và proxy không gom toàn bộ body trước khi chuyển tiếp. Kiểm thử trực tiếp qua tuyến production-like, không chỉ gọi controller trong unit test.

## 9. HTTP streaming không đồng nghĩa mọi giao thức đều có cùng flow control

Một số kiểu truyền dữ liệu phổ biến có đặc tính khác nhau:

| Kiểu truyền | Cách đóng khung dữ liệu | Điều tiết và giới hạn |
|---|---|---|
| HTTP response thông thường | Một response body | TCP/HTTP transport flow control; không có demand theo phần tử ở wire |
| NDJSON | Mỗi dòng là một JSON document | Framing ở tầng ứng dụng; flow control vẫn do transport và buffer đảm nhiệm |
| Server-Sent Events | Các event text theo định dạng SSE | Streaming một chiều server-to-client; không có `request(n)` trong SSE |
| WebSocket | Message hai chiều trên connection | Transport flow control; cần quy tắc ACK/credit ở tầng ứng dụng nếu muốn giới hạn message theo nghiệp vụ |
| gRPC streaming | Message gRPC trên HTTP/2 | Có cơ chế flow control ở gRPC và HTTP/2; API gRPC có thể cho ứng dụng điều khiển nhận message |

NDJSON và SSE giúp ứng dụng chia body thành đơn vị có thể xử lý dần. Chúng không tự định nghĩa demand theo phần tử. WebSocket cũng không tự biết consumer đã xử lý xong một message hay chưa; nếu nghiệp vụ cần giới hạn số message outstanding, hai phía có thể phải thiết kế acknowledgement hoặc credit protocol.

gRPC có flow control cho streaming RPC và cung cấp API để quản lý việc nhận message. Đây là semantics của gRPC được xây dựng trên HTTP/2, không phải HTTP response thông thường tự có `Subscription.request(n)`.

## 10. Kết hợp backpressure với giới hạn tải ứng dụng

Backpressure không thay thế các giới hạn bảo vệ dịch vụ. Một endpoint nên kết hợp nhiều cơ chế tùy yêu cầu:

- **Demand/prefetch:** điều chỉnh lượng phần tử được yêu cầu trước giữa các Publisher trong cùng tiến trình.
- **Concurrency:** giới hạn số thao tác downstream đang hoạt động, chẳng hạn `flatMap(mapper, 8)`.
- **Buffer hữu hạn:** hấp thụ burst ngắn, có chính sách overflow rõ ràng.
- **Rate limit:** giới hạn số request theo giây hoặc theo cửa sổ thời gian.
- **Admission control:** từ chối sớm khi hệ thống đã đạt ngưỡng công việc đang xử lý.
- **Timeout/deadline:** giới hạn thời gian chờ và tránh giữ tài nguyên vô hạn.
- **Quota ở gateway:** bảo vệ dịch vụ trước lượng request đến từ nhiều client.

Ví dụ, một endpoint có thể giới hạn concurrency và timeout cho thao tác lưu:

```java
Mono<Void> importEvents(Flux<EventInput> events) {
    return events
        .flatMap(
            event -> eventService.store(event)
                .timeout(Duration.ofSeconds(3)),
            8,
            1
        )
        .then();
}
```

Tối đa tám thao tác lưu đang hoạt động tại operator này; mỗi inner Publisher có prefetch 1. Timeout giới hạn thời gian của từng thao tác lưu. Đây không phải rate limit theo giây và cũng không đặt giới hạn tổng số byte mà proxy có thể buffer.

Nếu server đã quá tải, có thể trả `429 Too Many Requests` khi giới hạn theo client/quota hoặc `503 Service Unavailable` khi năng lực phục vụ tạm thời không còn. Nếu có thể, cung cấp `Retry-After` để client biết thời điểm phù hợp để thử lại. Không nên retry tức thì mọi lỗi 429/503 vì nhiều client có thể đồng loạt tạo thêm tải.

## 11. Cancellation, timeout và disconnect

Ba tình huống này có quan hệ nhưng không đồng nhất:

- **Cancellation:** Subscriber trong tiến trình yêu cầu hủy subscription. Đây là tín hiệu trong hợp đồng Reactive Streams.
- **Timeout:** một operator hoặc tầng transport kết thúc thao tác vì quá thời hạn; thường dẫn đến cancellation upstream và tín hiệu lỗi timeout downstream.
- **Client disconnect:** kết nối hoặc stream mạng bị đóng/reset. Server framework phát hiện sự kiện này rồi hủy hoặc dừng việc ghi response theo khả năng implementation.

Khi server nhận disconnect, công việc đang chạy cần có khả năng dừng hoặc giải phóng tài nguyên. Nếu pipeline đã khởi chạy một tác vụ không thể cancel, nó có thể tiếp tục chạy dù client không còn chờ kết quả. Vì vậy, các thao tác downstream nên tôn trọng cancellation, đặt timeout và quản lý resource bằng `usingWhen` hoặc cơ chế tương đương.

Không nên giả định mọi side effect đã bắt đầu đều có thể hoàn tác khi client ngắt kết nối. Một giao dịch database có thể đã commit trước khi server phát response. Với thao tác ghi, hãy thiết kế idempotency và trạng thái giao dịch rõ ràng để client không tạo dữ liệu trùng khi thử lại.

## 12. Kiểm thử demand ở cấp Publisher và hành vi HTTP thực tế

Một unit test với `StepVerifier` có thể chứng minh service Publisher tôn trọng demand:

```java
StepVerifier.create(eventService.stream(), 0)
    .expectSubscription()
    .thenRequest(1)
    .expectNextMatches(EventView::isValid)
    .thenRequest(1)
    .expectNextMatches(EventView::isValid)
    .thenCancel()
    .verify();
```

Test này kiểm tra Publisher trong JVM. Nó không chứng minh proxy, TCP hoặc HTTP client đã truyền flow control theo đúng cùng nhịp.

Với endpoint HTTP, có thể dùng `WebTestClient` để xác minh response streaming và tiêu thụ body theo từng phần tử:

```java
FluxExchangeResult<EventView> result = webTestClient.get()
    .uri("/events")
    .accept(MediaType.APPLICATION_NDJSON)
    .exchange()
    .expectStatus().isOk()
    .returnResult(EventView.class);

StepVerifier.create(result.getResponseBody(), 0)
    .expectSubscription()
    .thenRequest(1)
    .expectNextMatches(EventView::isValid)
    .thenCancel()
    .verify();
```

Test này xác minh response body được giải mã thành Publisher và subscriber test có thể yêu cầu/cancel theo bước. Tuy nhiên, `WebTestClient` có thể dùng connector và server trong cùng môi trường test; nó không tự đại diện cho toàn tuyến production có reverse proxy, TLS termination và network buffer.

Để kiểm chứng hành vi qua ranh giới thật, nên có integration test với server chạy trên socket, client đọc chậm có kiểm soát và proxy giống môi trường triển khai. Quan sát thời gian phát, số byte, queue, cancellation và lượng dữ liệu đã buffer. Với HTTP/2, cần test đúng protocol nếu ứng dụng phụ thuộc multiplexing hoặc flow-control window.

## 13. Các chỉ số cần theo dõi

Để biết backpressure có đang giúp hệ thống hay dữ liệu chỉ chuyển sang một buffer khác, hãy theo dõi:

1. Tốc độ phần tử được tạo, nhận, xử lý và phát ra downstream.
2. Demand, prefetch và concurrency tại các ranh giới operator quan trọng.
3. Queue depth và số phần tử bị drop/overflow.
4. Active connection, pending acquire và số stream HTTP đang mở.
5. Số byte đọc/ghi, thời gian response body và thời gian chờ socket.
6. Buffer của proxy/gateway nếu sản phẩm cung cấp metrics.
7. Số request bị 429/503, timeout, disconnect và retry.
8. Heap, direct memory, DataBuffer ownership và garbage collection.

Nếu queue trong JVM nhỏ nhưng proxy buffer tăng, áp lực đã chuyển ra khỏi ứng dụng. Nếu pending connection tăng trong khi demand downstream thấp, connection có thể đang bị giữ bởi response body chưa tiêu thụ. Nếu byte đã được gửi nhanh nhưng consumer xử lý chậm, cần kiểm tra buffer phía client và chính sách tiêu thụ.

## 14. Những nhầm lẫn thường gặp

| Nhầm lẫn | Thực tế |
|---|---|
| `request(n)` được gửi qua HTTP như một header | Reactive Streams demand là tín hiệu trong tiến trình; HTTP không có header chuẩn tương ứng |
| TCP window tương đương demand theo phần tử | TCP điều tiết byte, không hiểu object hoặc message nghiệp vụ |
| HTTP/2 WINDOW_UPDATE cho biết consumer đã xử lý message | Nó cập nhật cửa sổ byte ở tầng transport, không xác nhận xử lý nghiệp vụ |
| `limitRate` giới hạn message/giây | Nó điều chỉnh cách yêu cầu demand theo lô trong pipeline Reactor |
| NDJSON/SSE tự cung cấp backpressure | Chúng định dạng/framing body; flow control do transport và implementation đảm nhiệm |
| Client cancel thì server side effect chắc chắn bị hoàn tác | Tác vụ có thể đã hoàn tất hoặc commit trước khi disconnect được nhận biết |
| Unit test StepVerifier chứng minh toàn tuyến không buffer | Nó kiểm tra Publisher trong JVM; proxy, kernel và client cần integration test riêng |

## 15. Checklist thiết kế HTTP streaming

Trước khi đưa một API streaming vào vận hành, hãy trả lời:

1. Body được phát/nhận theo phần tử hay được aggregate toàn bộ?
2. Giao thức là HTTP/1.1, HTTP/2 hay HTTP/3; có cần gRPC hoặc acknowledgement ở tầng ứng dụng không?
3. `Flux` có được trả trực tiếp cho WebFlux hay bị subscribe/collect ở giữa pipeline?
4. Demand và prefetch trong JVM được giới hạn ở operator nào?
5. Có buffer ở server, client, codec, kernel, proxy hoặc gateway không?
6. Buffer và body size có giới hạn hữu hạn không?
7. Client chậm hoặc disconnect thì server dừng công việc và giải phóng tài nguyên ra sao?
8. Concurrency, rate limit, timeout và admission control có phù hợp với năng lực dependency không?
9. Request ghi có idempotent khi client retry sau timeout/disconnect không?
10. Test có tách biệt unit test Publisher với integration test transport/proxy không?

Reactive Streams backpressure điều tiết phần tử giữa Publisher và Subscriber trong pipeline; HTTP và transport kiểm soát truyền byte bằng cơ chế riêng. WebFlux và Reactor Netty kết nối hai lớp này bằng cách phối hợp demand, đọc/ghi channel và cancellation, nhưng buffer ở codec, socket, proxy và client vẫn có thể giữ dữ liệu. Muốn bảo vệ hệ thống qua ranh giới HTTP, hãy stream body theo phần tử, giới hạn concurrency và buffer, đặt timeout/rate limit phù hợp, xử lý disconnect và kiểm thử trên tuyến mạng gần thực tế.
