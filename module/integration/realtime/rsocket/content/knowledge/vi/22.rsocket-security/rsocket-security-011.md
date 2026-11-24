# Giới hạn kích thước, số luồng và tốc độ để chống lạm dụng

RSocket multiplex nhiều tương tác trên một kết nối và hỗ trợ truyền dữ liệu theo luồng. Những đặc điểm này giúp ứng dụng realtime hiệu quả, nhưng cũng tạo ra nhiều tài nguyên mà một client lỗi hoặc độc hại có thể tiêu thụ: bộ nhớ để nhận payload lớn, CPU để giải mã metadata, stream đang hoạt động, truy vấn tới dịch vụ phụ thuộc, hàng đợi và băng thông mạng.

Muốn chống lạm dụng, server cần áp dụng giới hạn ở nhiều tầng: kích thước frame và payload, số kết nối và stream đồng thời, số request trong một khoảng thời gian, nhu cầu dữ liệu của stream, thời gian xử lý và dung lượng queue. Một giới hạn đơn lẻ không đủ bảo vệ toàn bộ hệ thống. Ví dụ, backpressure kiểm soát tốc độ phát dữ liệu của stream nhưng không giới hạn số request-response mới được gửi mỗi giây; rate limit kiểm soát số request nhưng không ngăn một request duy nhất gửi payload rất lớn.

## 1. Những tài nguyên cần bảo vệ

Các tình huống lạm dụng thường gặp:

- Gửi payload hoặc metadata rất lớn khiến server tốn bộ nhớ để nhận, ghép mảnh và giải mã.
- Mở nhiều kết nối hoặc khởi tạo quá nhiều stream đồng thời.
- Gửi request liên tục tới một route tốn CPU hoặc truy vấn cơ sở dữ liệu.
- Mở stream dài hạn nhưng tiêu thụ rất chậm, khiến tài nguyên phía server bị giữ lâu.
- Gửi channel với tốc độ cao hơn khả năng xử lý của handler.
- Tạo queue hoặc buffer không giới hạn để giữ dữ liệu đang chờ.
- Mở kết nối rồi không gửi `SETUP`, hoặc gửi request nhưng không hoàn tất trong thời gian hợp lý.
- Dùng nhiều tài khoản hoặc nhiều IP để vượt qua giới hạn được áp dụng riêng lẻ ở một lớp.

Hãy coi mỗi request là một khoản chi phí. Server cần giới hạn kích thước dữ liệu, số công việc đang chạy và tổng tốc độ phát sinh công việc từ mỗi danh tính cũng như toàn hệ thống.

## 2. Ma trận giới hạn theo từng tầng

| Tài nguyên | Giới hạn nên có | Phạm vi áp dụng |
|---|---|---|
| Kết nối TCP/WebSocket | Số kết nối, tốc độ mở kết nối, timeout handshake | IP, principal, gateway và toàn server |
| Frame transport | Kích thước frame tối đa | Transport hoặc WebSocket server |
| Payload đã ghép mảnh | Kích thước data và metadata sau reassembly | Mỗi payload nhận vào |
| Metadata | Số byte, số entry và độ dài từng trường | Mỗi payload hoặc SETUP |
| Stream | Số stream đang hoạt động | Mỗi kết nối, principal/tenant và toàn server |
| Request | Số request trong một cửa sổ thời gian | Principal, tenant, route và toàn hệ thống |
| Xử lý nghiệp vụ | Số tác vụ đồng thời, thời gian xử lý | Từng route và dịch vụ phụ thuộc |
| Stream output | Nhu cầu `REQUEST_N`, prefetch và buffer | Mỗi subscription |
| Queue | Số phần tử hoặc tổng byte đang chờ | Mỗi producer/consumer và toàn ứng dụng |

Nên kết hợp giới hạn cứng ở transport với giới hạn theo danh tính ở tầng ứng dụng. Giới hạn theo IP hữu ích trước xác thực, nhưng không đủ khi nhiều người dùng hợp lệ cùng đi qua NAT hoặc một người dùng có thể đổi IP.

## 3. Phân biệt frame size, payload size và fragmentation

RSocket frame và payload là hai khái niệm khác nhau:

- **Frame size** là kích thước một frame RSocket được transport chuyển tới tầng giao thức.
- **Payload size** là tổng data và metadata của một thông điệp sau khi các fragment được ghép lại.
- **Fragment size/MTU** là ngưỡng kích thước frame mà sender dùng để chia payload lớn thành nhiều fragment.

Theo đặc tả RSocket, kích thước tối đa của một frame là 16.777.215 byte. Fragmentation cho phép một payload được truyền qua nhiều frame nhỏ hơn, nhưng không tự giới hạn tổng kích thước payload sau khi ghép. Vì vậy, đặt `fragment-size` nhỏ không có nghĩa là đã ngăn client gửi một payload tổng thể rất lớn.

RSocket Java cung cấp `maxInboundPayloadSize(...)` trên `RSocketServer` và `RSocketConnector` để giới hạn kích thước payload được reassemble. Giá trị này phải ít nhất 64 byte và lớn hơn hoặc bằng `Transport.maxFrameLength()` của transport đang dùng. Nếu muốn đặt giới hạn nhỏ hơn frame length mặc định, cần cấu hình transport tương ứng để hai giới hạn tương thích.

Ví dụ cấu hình mức thấp cho server RSocket Java:

```java
RSocketServer.create(acceptor)
    .maxInboundPayloadSize(maxInboundPayloadBytes)
    .fragment(16 * 1024)
    .maxTimeToFirstFrame(Duration.ofSeconds(10))
    .bind(transport);
```

Trong đó:

- `maxInboundPayloadSize` giới hạn payload inbound sau khi ghép fragment.
- `fragment(16 * 1024)` đặt MTU cho frame outbound do server gửi.
- `maxTimeToFirstFrame` giới hạn thời gian server chờ frame đầu tiên như `SETUP` sau khi nhận kết nối.
- `transport` phải có `maxFrameLength()` không vượt quá `maxInboundPayloadBytes`.

Phía client cũng có thể đặt giới hạn payload inbound để bảo vệ bộ nhớ của chính client:

```java
RSocketConnector.create()
    .maxInboundPayloadSize(maxInboundPayloadBytes)
    .connect(clientTransport);
```

Không chọn giới hạn chỉ dựa trên khả năng tối đa của giao thức. Hãy đo payload thực tế của ứng dụng, chọn mức đủ cho request hợp lệ và chừa khoảng an toàn cho metadata cùng overhead.

## 4. Cấu hình giới hạn WebSocket trong Spring Boot

Với RSocket chạy qua WebSocket, Spring Boot cung cấp các thuộc tính cho WebSocket server. Ví dụ:

```yaml
spring:
  rsocket:
    server:
      transport: websocket
      mapping-path: /rsocket
      fragment-size: 16KB
      spec:
        max-frame-payload-length: 64KB
```

`spring.rsocket.server.spec.max-frame-payload-length` giới hạn frame payload mà WebSocket server chấp nhận. Thuộc tính này chỉ áp dụng cho WebSocket transport. `spring.rsocket.server.fragment-size` điều khiển kích thước frame khi phân mảnh dữ liệu gửi đi. Hai thuộc tính này không thay thế giới hạn tổng payload sau reassembly ở tầng RSocket Java.

Với TCP, không có WebSocket frame spec. Cần cấu hình giới hạn ở RSocket transport/runtime và ở tầng ứng dụng. Hãy kiểm tra đúng transport trước khi áp dụng một thuộc tính cấu hình; không giả định mọi thuộc tính trong `spring.rsocket.server.spec` đều có tác dụng với TCP.

## 5. Kiểm tra data và metadata ở tầng ứng dụng

Giới hạn ở tầng giao thức bảo vệ bộ nhớ khi nhận và ghép frame. Sau khi payload đã được giải mã, ứng dụng vẫn cần kiểm tra cấu trúc và kích thước theo nghiệp vụ:

- Số phần tử trong một batch, ví dụ không nhận một request chứa hàng trăm nghìn ID.
- Độ dài chuỗi, tên file, trường tìm kiếm hoặc nội dung chat.
- Số entry trong composite metadata và độ dài từng giá trị.
- Số bộ lọc, điều kiện truy vấn hoặc trường sắp xếp mà client yêu cầu.
- Kích thước file hoặc nội dung nhị phân mà nghiệp vụ cho phép.

Ví dụ kiểm tra DTO trước khi gọi service:

```java
@MessageMapping("orders.batch-find")
public Flux<OrderView> findBatch(@Payload BatchOrderRequest request) {
    if (request.orderIds() == null || request.orderIds().size() > 100) {
        return Flux.error(new InvalidException("Batch size must be between 1 and 100"));
    }

    if (request.orderIds().stream().anyMatch(id -> id == null || id.length() > 40)) {
        return Flux.error(new InvalidException("Invalid order id"));
    }

    return orderService.findAll(request.orderIds());
}
```

Kiểm tra trong handler diễn ra sau bước nhận và decode payload. Vì vậy, nó không thay thế `maxInboundPayloadSize`; hai lớp kiểm soát bảo vệ hai giai đoạn khác nhau.

Metadata cũng cần giới hạn riêng. Không cho phép metadata tùy ý chứa chuỗi lớn, hàng nghìn entry hoặc cấu trúc lồng nhau sâu. Chỉ chấp nhận MIME type và schema đã định nghĩa, đồng thời giới hạn độ dài các giá trị như route variable, correlation ID và tenant context.

## 6. Giới hạn số kết nối và stream đồng thời

RSocket multiplex nhiều stream trên một kết nối. Một client không cần mở một kết nối mới cho mỗi request, nhưng cũng không nên được phép tạo số stream không giới hạn. Nên áp dụng ít nhất ba mức:

1. **Per connection**: giới hạn số stream đồng thời trên một kết nối.
2. **Per principal/tenant**: giới hạn tổng số stream của một người dùng hoặc tenant, kể cả khi họ mở nhiều kết nối.
3. **Global**: giới hạn tổng số công việc đang chạy trên một instance hoặc toàn cụm.

Ví dụ dùng `Semaphore` để giới hạn số request-response đang thực thi đồng thời trong một instance:

```java
private final Semaphore requestSlots = new Semaphore(128);

@MessageMapping("orders.find")
public Mono<OrderView> find(@Payload FindOrderRequest request) {
    return Mono.defer(() -> {
        if (!requestSlots.tryAcquire()) {
            return Mono.error(new RejectedException("Server is busy"));
        }

        return orderService.findById(request.orderId())
            .doFinally(signal -> requestSlots.release());
    });
}
```

`tryAcquire()` từ chối ngay khi hết slot, tránh tạo một hàng đợi chờ không giới hạn. `doFinally` giải phóng slot khi publisher hoàn tất, phát lỗi hoặc bị hủy. Dùng `Mono.defer` để việc lấy slot xảy ra khi mỗi subscription bắt đầu, không phải khi Spring tạo publisher.

Ví dụ trên là giới hạn toàn cục trong một instance. Muốn giới hạn theo connection hoặc principal, cần duy trì counter/permit theo định danh đáng tin cậy và giải phóng khi stream kết thúc. Không dùng `tenantId` do client tự khai báo làm khóa quota trước khi xác minh danh tính. Trong môi trường nhiều instance, semaphore cục bộ không tạo ra quota toàn cụm; cần gateway hoặc bộ giới hạn phân tán nếu quota phải có hiệu lực toàn hệ thống.

Đối với stream dài hạn, giữ permit trong suốt thời gian stream hoạt động:

```java
private final Semaphore watchSlots = new Semaphore(64);

@MessageMapping("orders.watch")
public Flux<OrderEvent> watch(@Payload OrderWatchRequest request) {
    return Flux.defer(() -> {
        if (!watchSlots.tryAcquire()) {
            return Flux.error(new RejectedException("Too many active streams"));
        }

        return orderService.watch(request.customerId())
            .doFinally(signal -> watchSlots.release());
    });
}
```

Permit chỉ được giữ cho tới khi stream hoàn tất, lỗi hoặc bị cancel. Nếu client giữ stream mở lâu nhưng không tiêu thụ, flow control và timeout vẫn cần thiết để tránh giữ tài nguyên vô thời hạn.

## 7. Giới hạn số tác vụ song song trong request-channel

Một request-channel có thể mang nhiều payload đầu vào. Nếu handler dùng `flatMap` mà không đặt concurrency, nhiều thao tác phụ thuộc có thể chạy cùng lúc và làm cạn connection pool hoặc thread pool.

Ví dụ giới hạn tối đa 16 tác vụ xử lý song song:

```java
@MessageMapping("events.ingest")
public Flux<EventAck> ingest(@Payload Flux<ClientEvent> events) {
    return events.flatMap(
        event -> eventService.accept(event)
            .map(result -> new EventAck(event.eventId(), result.status())),
        16
    );
}
```

Nếu cần giữ thứ tự sự kiện, dùng `concatMap` để xử lý tuần tự:

```java
return events.concatMap(event -> eventService.accept(event)
    .map(result -> new EventAck(event.eventId(), result.status())));
```

`flatMap(..., 16)` giới hạn số publisher con đang hoạt động ở pipeline này; `concatMap` chỉ xử lý một publisher con tại một thời điểm. Hãy chọn theo yêu cầu thứ tự và năng lực của dịch vụ phụ thuộc. Giới hạn concurrency của một handler không thay thế quota tổng thể theo tenant hoặc toàn server.

## 8. Backpressure và REQUEST_N

RSocket dùng cơ chế credit-based flow control cho `request-stream` và `request-channel`. Requester gửi `REQUEST_N` để cấp quyền cho responder phát thêm một số payload. Responder chỉ được phát trong phạm vi demand đã được cấp; khi hết credit, nó phải chờ requester cấp thêm.

Điều này bảo vệ consumer chậm khỏi việc bị đẩy dữ liệu vô hạn. Tuy nhiên, backpressure không giới hạn:

- Số request-response hoặc fire-and-forget mà client khởi tạo trong một giây.
- Số stream mới được mở đồng thời.
- Kích thước một payload đơn lẻ.
- Chi phí CPU của một request hoặc truy vấn dữ liệu.

Vì vậy, hãy dùng backpressure cho stream, đồng thời dùng payload cap, concurrency limit và rate limit cho những tài nguyên còn lại.

Ví dụ giới hạn tốc độ prefetch ở responder bằng `LimitRateInterceptor` của RSocket Java:

```java
RSocketServer.create(acceptor)
    .interceptors(registry -> registry.forResponder(
        LimitRateInterceptor.forResponder(64)
    ))
    .bind(transport);
```

Interceptor này áp dụng `Flux.limitRate` lên các stream outbound để điều chỉnh cách demand từ peer được chuyển thành batch prefetch. Nó hữu ích để kiểm soát lượng phần tử mà publisher lấy trước, nhưng **không phải rate limiter cho số request mới** và cũng không giới hạn byte của mỗi payload.

Không đặt `onBackpressureBuffer()` với dung lượng không giới hạn. Nếu nguồn dữ liệu là hot publisher và không thể giảm tốc, hãy dùng buffer có giới hạn cùng chính sách overflow rõ ràng, hoặc loại bỏ sự kiện cũ/mới theo yêu cầu nghiệp vụ.

## 9. Giới hạn số request theo thời gian bằng RSocket LEASE

RSocket có extension **Leasing** để responder cấp cho requester một số lượng request được phép gửi trong một khoảng thời gian. Một lease gồm:

- `numberOfRequests`: số request được phép thực hiện.
- `timeToLive`: khoảng thời gian lease còn hiệu lực.
- Metadata tùy chọn nếu ứng dụng cần truyền thêm ngữ cảnh.

LEASE giới hạn số request mà peer được phép khởi tạo trong thời gian lease, áp dụng cho các interaction type. Nó không giới hạn số payload trong một stream, không giới hạn kích thước payload và không thay thế kiểm soát đồng thời ở handler.

Ví dụ server cấp tối đa 40 request mỗi giây:

```java
RSocketServer.create(acceptor)
    .lease(spec -> spec.sender(() ->
        Flux.interval(Duration.ofSeconds(1))
            .map(tick -> Lease.create(Duration.ofSeconds(1), 40))
    ))
    .bind(transport);
```

Client phải bật khả năng lease và tôn trọng quota được cấp:

```java
RSocketConnector.create()
    .lease(spec -> spec.maxPendingRequests(16))
    .connect(clientTransport);
```

`maxPendingRequests(16)` giới hạn số request đang chờ lease được cấp. Giá trị này không phải số request mỗi giây; quota theo thời gian được xác định bởi các `Lease` mà server phát.

Leasing là cơ chế điều tiết ở cấp kết nối/requester. Nếu server có nhiều client hoặc cần quota theo user/tenant/route, vẫn phải kết hợp rate limiter ở tầng ứng dụng. Không nên giả định một lease chung tự chia đều tài nguyên giữa các tenant.

## 10. Rate limiting ở tầng ứng dụng

Rate limiter thường dùng token bucket hoặc sliding window. Với token bucket:

1. Bucket có dung lượng tối đa, cho phép một burst ngắn.
2. Token được bổ sung đều theo thời gian.
3. Mỗi request tiêu thụ một hoặc nhiều token tùy chi phí.
4. Nếu không đủ token, server từ chối request hoặc yêu cầu client thử lại sau.

Nên đặt quota theo nhiều chiều:

- Principal đã xác thực.
- Tenant đã được xác minh.
- Route hoặc nhóm thao tác.
- IP/gateway cho lưu lượng trước xác thực.
- Tổng quota của toàn dịch vụ.

Ví dụ áp dụng rate limiter trong handler bằng một interface do ứng dụng triển khai:

```java
@MessageMapping("orders.find")
public Mono<OrderView> find(@Payload FindOrderRequest request) {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .flatMap(authentication -> {
            String principal = authentication.getName();

            if (!rateLimiter.tryAcquire(principal, "orders.find")) {
                return Mono.error(new RejectedException("Rate limit exceeded"));
            }

            return orderService.findById(request.orderId());
        });
}
```

`rateLimiter` ở đây là thành phần ứng dụng cung cấp thuật toán token bucket hoặc sliding window. Khóa quota phải lấy từ principal đã xác thực, không lấy trực tiếp từ trường `userId` hoặc `tenantId` trong payload. Với hệ thống nhiều replica, cần đồng bộ quota hoặc đặt rate limiter ở API gateway để tránh mỗi instance cấp một quota riêng làm tổng quota vượt mức.

Đoạn mã giả định route đã được Spring Security xác thực và security context luôn có mặt. Nếu không có principal, ứng dụng phải fail closed theo chính sách xác thực; không được bỏ qua bước rate limit hoặc trả kết quả rỗng như thể request đã thành công.

Khi từ chối trước khi bắt đầu xử lý nghiệp vụ, có thể dùng `RejectedException` để phát RSocket `REJECTED`. Responder cần từ chối trước side effect để caller biết request chưa được xử lý. Client nên retry có backoff nếu contract cho phép; retry ngay lập tức sẽ làm tình trạng quá tải nặng hơn.

## 11. Timeout và giới hạn thời gian sống của công việc

Giới hạn kích thước và tốc độ vẫn chưa đủ nếu một request có thể giữ tài nguyên vô thời hạn. Cần đặt timeout phù hợp cho:

- Thời gian chờ frame đầu tiên/SETUP sau khi transport được chấp nhận.
- Thời gian xử lý request-response.
- Thời gian chờ dịch vụ phụ thuộc như database hoặc HTTP service.
- Thời gian idle tối đa của stream realtime.
- Thời gian giữ kết nối không hoạt động.

RSocket Java có `maxTimeToFirstFrame(Duration)` trên `RSocketServer` để giới hạn thời gian chờ frame đầu tiên sau khi accept connection. Ở tầng ứng dụng, dùng timeout theo route và theo SLA:

```java
@MessageMapping("reports.generate")
public Mono<ReportView> generate(@Payload ReportRequest request) {
    return reportService.generate(request)
        .timeout(Duration.ofSeconds(5));
}
```

Với stream, timeout có thể là thời gian chờ giữa các tín hiệu hoặc deadline tổng tùy operator được chọn. `Flux.timeout(Duration)` thường là timeout khi không có tín hiệu trong khoảng thời gian đó, không phải tự động là giới hạn tổng thời gian stream. Nếu cần deadline tổng, hãy thiết kế deadline riêng và hủy subscription khi hết hạn.

Khi timeout hoặc client cancel, handler cần propagate cancellation tới truy vấn và dịch vụ phụ thuộc để giải phóng tài nguyên. Không chỉ dừng việc gửi response mà vẫn để công việc nền tiếp tục chạy.

## 12. Queue hữu hạn và load shedding

Nếu hệ thống nhận công việc nhanh hơn tốc độ xử lý, queue sẽ tăng. Queue vô hạn chỉ trì hoãn thời điểm cạn bộ nhớ. Nên đặt:

- Số phần tử tối đa trong queue.
- Tổng byte tối đa nếu phần tử có kích thước khác nhau.
- Thời gian tối đa một phần tử được phép chờ.
- Chính sách khi queue đầy: từ chối, drop, coalesce hoặc ghi vào broker bền vững.

Ví dụ với một nguồn hot publisher không thể điều tiết, có thể dùng buffer giới hạn:

```java
Flux<MetricEvent> boundedMetrics = hotMetrics
    .onBackpressureBuffer(
        500,
        dropped -> metrics.counter("rsocket.metrics.dropped").increment(),
        BufferOverflowStrategy.DROP_OLDEST
    );
```

Ví dụ chọn `DROP_OLDEST` phù hợp với metric hoặc trạng thái realtime mà giá trị mới quan trọng hơn lịch sử cũ. Với lệnh thanh toán hoặc sự kiện nghiệp vụ không được mất, không dùng chính sách drop; hãy từ chối sớm hoặc ghi vào hàng đợi bền vững có dung lượng và chính sách retry rõ ràng.

Load shedding là từ chối có kiểm soát khi server đã gần ngưỡng bảo vệ. Dùng `RejectedException` khi request hợp lệ nhưng không được tiếp nhận vì thiếu năng lực. Ghi metric về số lần từ chối và tránh để client retry tức thì.

## 13. Giới hạn kết nối và chống mở kết nối hàng loạt

RSocket multiplex nhiều stream trên một kết nối, do đó client nên tái sử dụng kết nối cho các tương tác liên quan. Ở phía server và gateway, giới hạn:

- Số kết nối đồng thời trên mỗi IP hoặc principal.
- Tốc độ mở kết nối mới trong một khoảng thời gian.
- Số kết nối tổng thể mà mỗi instance có thể phục vụ.
- Thời gian chờ SETUP và số kết nối chưa hoàn tất xác thực.
- Số kết nối nhàn rỗi và thời gian giữ chúng.

Giới hạn trước xác thực nên dùng IP/gateway và có ngưỡng phù hợp với NAT. Sau xác thực, áp dụng quota theo principal/tenant để một người dùng không thể mở nhiều kết nối nhằm vượt giới hạn stream. Trong triển khai rolling, drain kết nối có kiểm soát để tránh reconnect storm.

## 14. Phân loại lỗi khi vượt giới hạn

Không phải mọi vi phạm quota đều cần đóng kết nối. Chọn phạm vi từ chối phù hợp:

| Tình huống | Cách phản hồi thường phù hợp | Phạm vi |
|---|---|---|
| Payload vượt giới hạn frame hoặc reassembly | Từ chối frame/payload theo cơ chế transport/protocol | Frame, payload hoặc kết nối tùy lỗi |
| DTO sai cấu trúc hoặc trường vượt giới hạn | `INVALID` hoặc lỗi ứng dụng theo contract | Request hiện tại |
| Hết quota request tạm thời | `REJECTED` | Request hiện tại |
| Hết slot xử lý đồng thời | `REJECTED` trước side effect | Request hiện tại |
| Stream bị requester hủy | `CANCEL` | Stream tương ứng |
| SETUP không đáp ứng chính sách | Từ chối setup | Kết nối mới |
| Vi phạm bảo mật nghiêm trọng hoặc lặp lại | Từ chối request, thu hồi session hoặc đóng kết nối theo chính sách | Request hoặc kết nối |

Thông báo lỗi nên cung cấp mã ổn định và thông tin retry an toàn nếu ứng dụng hỗ trợ. Không gửi chi tiết nội bộ, stack trace hoặc cấu hình quota nhạy cảm cho client.

## 15. Quan sát và cảnh báo

Theo dõi các chỉ số sau để phát hiện lạm dụng trước khi server cạn tài nguyên:

| Metric | Ý nghĩa |
|---|---|
| Active connections | Số kết nối TCP/WebSocket hiện hành |
| Active streams | Số stream đang chạy trên mỗi instance và mỗi connection |
| Rejected requests | Request bị từ chối do rate limit hoặc hết slot |
| Payload size distribution | Phân bố kích thước data và metadata |
| Frame/reassembly failures | Lỗi do frame hoặc payload vượt giới hạn |
| Requests per second by route | Tốc độ request theo route |
| In-flight handler count | Số handler đang thực thi |
| Queue depth and dropped events | Dung lượng queue và số phần tử bị drop |
| Stream lifetime and idle duration | Thời gian sống và thời gian idle của stream |
| Downstream pool saturation | Mức sử dụng connection pool và thread pool của dependency |

Tránh dùng user ID, token, session ID hoặc connection ID làm label metric có cardinality cao. Dùng principal đã che hoặc tenant tier để phân nhóm, còn điều tra từng request thì dùng log/tracing có kiểm soát.

## 16. Kiểm thử khả năng chống lạm dụng

Kiểm thử cần xác nhận cả request hợp lệ lẫn hành vi khi vượt giới hạn:

1. Gửi payload ngay dưới, đúng bằng và vượt ngưỡng cho phép.
2. Gửi metadata có nhiều entry hoặc một giá trị quá dài.
3. Mở stream đồng thời tới ngưỡng và vượt ngưỡng.
4. Gửi request theo burst ngắn rồi giữ tốc độ cao liên tục để kiểm tra token bucket.
5. Gửi request-stream/request-channel với subscriber tiêu thụ chậm để kiểm tra `REQUEST_N` và backpressure.
6. Gửi channel nhanh hơn năng lực service và xác nhận concurrency/queue có giới hạn.
7. Mở kết nối nhưng không gửi SETUP để kiểm tra timeout first-frame.
8. Hủy stream giữa chừng và xác nhận permit, listener, query được giải phóng.
9. Chạy nhiều instance để xác nhận quota phân tán không bị nhân lên ngoài ý muốn.
10. Gửi lại request sau `REJECTED` theo backoff và xác nhận server phục hồi bình thường.

Đo CPU, heap, direct memory, số kết nối, stream đang hoạt động, độ trễ p95/p99, queue depth và tỷ lệ từ chối. Một bài kiểm thử đạt yêu cầu khi tải hợp lệ vẫn có SLA, tải vượt ngưỡng bị chặn có kiểm soát và tài nguyên được giải phóng sau khi client cancel hoặc timeout.

## 17. Checklist triển khai

- [ ] Có giới hạn frame và payload inbound phù hợp với transport.
- [ ] Phân biệt `fragment-size` với giới hạn payload sau reassembly.
- [ ] Giới hạn kích thước data, metadata, batch và từng trường DTO.
- [ ] Giới hạn kết nối và stream đồng thời theo connection, principal/tenant và toàn hệ thống.
- [ ] Có rate limit theo principal/tenant/route và quota toàn cục.
- [ ] Dùng RSocket LEASE nếu cần điều tiết số request theo thời gian ở cấp kết nối.
- [ ] Dùng backpressure/REQUEST_N cho stream và channel; không coi đó là rate limiter cho request mới.
- [ ] Giới hạn concurrency trong `flatMap` và giữ `concatMap` khi cần thứ tự.
- [ ] Không dùng queue/buffer không giới hạn.
- [ ] Có timeout cho SETUP, request, dependency và stream idle/deadline.
- [ ] Từ chối sớm trước side effect khi hết quota hoặc slot.
- [ ] Theo dõi metric và kiểm thử burst, slow consumer, payload lớn và nhiều kết nối.
- [ ] Xác minh quota theo danh tính đã xác thực và có hiệu lực phù hợp khi chạy nhiều replica.

Chống lạm dụng RSocket cần nhiều lớp kiểm soát cùng hoạt động. Giới hạn frame và payload bảo vệ bộ nhớ; quota kết nối và stream bảo vệ số công việc đồng thời; rate limiting và LEASE kiểm soát tốc độ request; backpressure kiểm soát lượng dữ liệu của stream; timeout và queue hữu hạn bảo vệ vòng đời tài nguyên. Khi các giới hạn được đặt theo danh tính đáng tin cậy, đo lường và kiểm thử thường xuyên, server có thể từ chối tải bất thường mà vẫn duy trì dịch vụ cho client hợp lệ.

## Tài liệu tham khảo

- [RSocket Protocol — Frames, REQUEST_N và Flow Control](https://rsocket.io/about/protocol/)
- [Spring Framework — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [Spring Boot 3.5 — RSocket Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/)
- [RSocket Java 1.1.5 — RSocketServer](https://javadoc.io/static/io.rsocket/rsocket-core/1.1.5/io/rsocket/core/RSocketServer.html)
- [RSocket Java 1.1.5 — RSocketConnector](https://javadoc.io/static/io.rsocket/rsocket-core/1.1.5/io/rsocket/core/RSocketConnector.html)
- [RSocket Java 1.1.5 — LimitRateInterceptor](https://javadoc.io/static/io.rsocket/rsocket-core/1.1.5/io/rsocket/plugins/LimitRateInterceptor.html)
- [RSocket Java 1.1.5 — LeaseSpec](https://javadoc.io/static/io.rsocket/rsocket-core/1.1.5/io/rsocket/core/LeaseSpec.html)
- [RSocket Java 1.1.5 — RejectedException](https://javadoc.io/static/io.rsocket/rsocket-core/1.1.5/io/rsocket/exceptions/RejectedException.html)
