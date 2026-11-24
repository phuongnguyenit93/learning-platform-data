# Streaming upload/download và tác động của bộ lọc body trong Spring Cloud Gateway

Một API Gateway có thể chuyển tiếp những request rất nhỏ, nhưng cũng có thể phải xử lý **upload file nhiều gigabyte**, **download file lớn**, hoặc **luồng sự kiện kéo dài hàng phút/hàng giờ**. Khi đó, sự khác nhau giữa *chuyển tiếp theo dòng dữ liệu* (**streaming**) và *đọc hết body vào bộ nhớ* (**buffering/aggregation**) quyết định khả năng phục vụ, độ trễ, mức dùng bộ nhớ và hành vi khi client ngắt kết nối.

Trong **SPRING_CLOUD_GATEWAY**, Gateway Server WebFlux kết hợp Spring WebFlux, Reactor và Reactor Netty để xử lý HTTP theo cách reactive, có backpressure. Tuy nhiên, một filter đọc hoặc biến đổi body sai cách có thể khiến ưu thế streaming biến mất. Bài thuộc chương **WebSocket và truyền luồng**, tập trung vào **streaming upload/download và tác động của bộ lọc body**: cách nhận diện buffering vô tình, thiết kế filter an toàn, bảo vệ memory và độ trễ, cũng như kiểm thử tải dài hạn.

Ngữ cảnh xuyên suốt là Gateway có route predicate, filter chain, thay đổi path/header, khám phá dịch vụ (`lb://`), xác thực, rate limiting, circuit breaker, retry, TLS và observability. Mỗi chức năng có thể tác động đến streaming, nhưng **không nên vì tiện xử lý body mà làm Gateway lưu toàn bộ file hoặc stream trong RAM**.

> **Phạm vi:** Nội dung hướng đến **Spring Cloud Gateway Server WebFlux**. Gateway Server MVC dùng servlet stack và cơ chế mở rộng khác. Tên starter, namespace `spring.cloud.gateway.*`, behavior của codec, filter factory và timeout có thể khác giữa các Spring Cloud release train. Các ví dụ là mô hình kỹ thuật cần kiểm tra với **phiên bản Gateway/Boot/Reactor Netty thật**, không phải cam kết mọi API đều hỗ trợ streaming giống nhau.

## 1. Streaming khác buffering thế nào?

Giả sử client gửi file `2 GiB` đến endpoint `POST /api/files/upload`.

**Streaming** có nghĩa Gateway xử lý dữ liệu dần khi các khối dữ liệu (`DataBuffer`) đi qua pipeline. Nó **không cần giữ toàn bộ 2 GiB body cùng lúc** chỉ để chuyển tiếp. Nhưng vẫn cần bộ đệm socket, TLS, queue, connection pool và một số buffers; “streaming” **không đồng nghĩa sử dụng 0 byte bộ nhớ**.

**Buffering/aggregation** có nghĩa một thành phần đọc và gom các khối thành một đối tượng lớn, chẳng hạn `String`, `byte[]`, `DataBuffer` tổng hợp hoặc một giá trị JSON đã decode. Dung lượng giữ lại có thể tăng theo body và số request đồng thời.

| Tiêu chí | Streaming | Buffering toàn body |
|---|---|---|
| Khi backend bắt đầu nhận dữ liệu | Có thể trước khi client upload xong | Thường sau khi đã đọc/gom đủ body |
| Bộ nhớ thêm ở Gateway | Phụ thuộc bounded buffers, tốc độ các bên | Có thể tỉ lệ với kích thước body × số request |
| First-byte/first-chunk latency | Thường thấp hơn khi hạ tầng hỗ trợ | Thường đợi aggregation hoàn tất |
| Xử lý từng chunk | Thuận lợi | Có thể mất ranh giới chunk |
| Biến đổi toàn JSON/body | Khó hoặc cần parser streaming | Dễ hơn với body nhỏ |
| Retry request đã gửi một phần | Phức tạp, không đảm bảo replay | Có thể replay nếu đã cache, đổi lại tốn bộ nhớ |
| Rủi ro khi upload/download lớn | Backpressure, timeout, cancel, proxy buffering | OOM, GC pressure, codec memory limits |

Một API tải file thường **không cần Gateway hiểu nội dung file**. Gateway có thể xác thực request, kiểm tra quota và định tuyến dựa trên metadata đáng tin cậy; để backend/object storage nhận và xử lý bytes.

### Luồng streaming qua Gateway WebFlux

~~~mermaid
flowchart LR
    C["Client gửi body theo chunks"] --> N["Netty HTTP server"]
    N --> F["Gateway filter chain"]
    F --> R["NettyRoutingFilter / HTTP client"]
    R --> B["Upload backend / object storage adapter"]
    B --> D["Response streaming"]
    D --> W["Gateway response writer"]
    W --> C
    Q["Backpressure / cancel"] -.-> N
    Q -.-> F
    Q -.-> R
~~~

Sơ đồ là **mô hình pipeline**, không nói các chunks giữ kích thước hay ranh giới ban đầu khi đi qua HTTP/Netty. Network framing, TLS, codecs và HTTP transfer encoding có thể chia/gộp dữ liệu khác nhau.

## 2. Upload, download, SSE và WebSocket không phải cùng một protocol

Trong cùng chương **WebSocket và truyền luồng**, cần phân biệt các tình huống:

| Loại traffic | Kết nối/hướng dữ liệu | Ví dụ | Điểm nhạy cảm |
|---|---|---|---|
| HTTP upload | Client → backend | PUT binary, POST multipart | Body lớn, replay, request limits |
| HTTP download | Backend → client | File CSV, PDF, object download | Response chunking, Range, headers |
| **SSE** (Server-Sent Events) | Chủ yếu server → client trên HTTP | `text/event-stream` | Kết nối lâu, flush từng event, heartbeat |
| NDJSON / streamed JSON lines | Server → client hoặc upload theo luồng | `application/x-ndjson` | Ranh giới dòng, parse từng bản ghi |
| **WebSocket** | Nâng cấp kết nối thành kênh hai chiều theo frames/messages | Chat, notification bidirectional | HTTP handshake/Upgrade, frame/message limits |
| gRPC/HTTP/2 streaming | HTTP/2 và protocol semantics riêng | RPC stream | Không đồng nhất với HTTP/1.1 chunked |

**HTTP body filter không tương đương WebSocket frame filter.** Sau WebSocket handshake, dữ liệu đi trong **frames WebSocket** theo đường routing phù hợp (`ws://`/`wss://` trong Gateway hỗ trợ). Một filter đọc `ServerHttpRequest.getBody()` như HTTP upload không tự đọc được toàn bộ frames của kết nối đã upgrade.

## 3. Định tuyến upload/download mà không đụng body

Ví dụ Gateway Server WebFlux có hai dịch vụ:

- `upload-service` nhận `POST /upload/**`;
- `download-service` phục vụ `GET /download/**`.

Trong những release train dùng cú pháp `spring.cloud.gateway.routes`:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: upload-stream
          uri: lb://upload-service
          predicates:
            - Path=/api/files/upload/**
            - Method=POST
          filters:
            - StripPrefix=2

        - id: download-stream
          uri: lb://download-service
          predicates:
            - Path=/api/files/download/**
            - Method=GET
          filters:
            - StripPrefix=2
~~~

Theo cấu hình này:

~~~text
POST /api/files/upload/media       → POST /upload/media
GET  /api/files/download/report42  → GET  /download/report42
~~~

`StripPrefix=2` chỉ xóa hai phân đoạn đường dẫn `api` và `files`, không yêu cầu đọc body. `Path` và `Method` route predicates cũng không cần consume upload stream.

**Điều kiện thực tế:** có DiscoveryClient/LoadBalancer phù hợp để resolve `lb://`. Nếu chỉ làm lab một backend, tạm dùng `http://localhost:9090`. Không thêm `CacheRequestBody` hoặc `ModifyRequestBody` chỉ vì route đang chuyển upload.

### Headers quan trọng phải giữ đúng

- `Content-Type`: định dạng payload, với multipart còn mang `boundary`.
- `Content-Length` hoặc transfer encoding: thể hiện HTTP framing; có thể không biết trước độ dài khi stream.
- `Content-Encoding`: gzip hoặc encoding khác; phải khớp bytes thực.
- `Authorization`/cookie: chỉ chuyển đến backend theo trust boundary đã duyệt.
- `Content-Range`/`Range`: quan trọng với partial upload/download khi API hỗ trợ.
- `Expect: 100-continue`: behavior do client/server/proxy quyết định; không tự giả định từng Gateway version giữ nguyên.

**Không tự thay `Content-Length`** bằng chiều dài của một chunk hoặc chiều dài trước khi rewrite body. Nếu đổi kích thước bytes, phải để pipeline tạo HTTP framing/headers đúng hoặc tính lại có kiểm soát.

## 4. DataBuffer, Flux và backpressure trong WebFlux

Ở Spring WebFlux, `ServerHttpRequest.getBody()` trả một `Flux<DataBuffer>`, chứ không phải một `byte[]` duy nhất. Mỗi `DataBuffer` là vùng chứa bytes; một số implementation dựa trên pooled Netty buffers và có **reference counting**.

~~~java
Flux<DataBuffer> body = exchange.getRequest().getBody();
~~~

Ví dụ trên chỉ là minh họa chữ ký. Để hiểu pipeline:

1. Nguồn HTTP phát các `DataBuffer` khi dữ liệu đến và được subscriber yêu cầu.
2. Reactor operators có thể quan sát, chuyển đổi hoặc ghép các buffers.
3. Routing filter chuyển body tới HTTP client outbound theo lifecycle reactive.
4. Backpressure có thể hạn chế tốc độ một phần pipeline khi downstream chậm.
5. Khi client abort, cancellation có thể được truyền qua subscription; **không cam kết mọi side effect ở backend đã bị hủy ngay**.

### “Không blocking” không có nghĩa “không buffering”

Một đoạn code dùng `Mono`/`Flux` vẫn có thể gom toàn bộ body:

~~~java
// PHẢN VÍ DỤ: với body lớn, gom tất cả bytes vào một buffer.
return DataBufferUtils.join(exchange.getRequest().getBody())
    .flatMap(joined -> {
        // ... xử lý joined, sau đó phải giải quyết lifecycle/replay ...
        return Mono.empty();
    });
~~~

Đoạn trên **không phải một filter hoàn chỉnh** và không được dùng nguyên trong production. `DataBufferUtils.join(...)` có thể giữ lượng dữ liệu lớn; sử dụng phiên bản có giới hạn `maxByteCount` và xử lý ownership/release đúng khi thực sự cần aggregate. Ngoài ra, nếu đã consume request body rồi không phát lại, downstream có thể nhận body rỗng.

**Một subscriber không đồng nghĩa một request:** filter có thể được áp dụng lại bởi Retry hoặc được subscribe lại trong những chuỗi xử lý phù hợp. Code tự giữ state, đo byte count hoặc đọc toàn body phải hiểu semantics replay/cancellation.

### DataBuffer được sở hữu bởi ai?

Khi một filter **chỉ quan sát** buffer và chuyển nguyên nó qua chain, thông thường pipeline downstream chịu trách nhiệm lifecycle. Khi filter **giữ lại**, **drop** hoặc **tạo DataBuffer mới**, phải hiểu cách retain/release theo framework và tránh memory leak/`IllegalReferenceCountException`.

Nguyên tắc:

- Không gọi `DataBufferUtils.release(buffer)` trước khi chuyển buffer ấy xuống downstream.
- Không giữ `DataBuffer` vào cache/list rồi sử dụng lại sau khi nguồn đã giải phóng mà không có ownership phù hợp.
- Nếu lọc bỏ một buffer không được truyền tiếp, phải xử lý release theo contract của implementation.
- Không tự `subscribe()` vào request body để log rồi để routing lại subscribe lần nữa.
- Không chuyển pooled buffers sang thread khác hoặc lưu sau request lifecycle khi chưa xử lý reference counting.

Đối với Java code phức tạp cần buffer/replay, ưu tiên tích hợp chính thức của Gateway hoặc các API helper của Spring Framework hơn tự quản lý Netty reference counts.

## 5. Tác động của các body filters trong Gateway

Có nhiều loại filter can thiệp trực tiếp hoặc gián tiếp đến body:

| Filter / kỹ thuật | Cần đọc body? | Tác động tiềm năng với upload/download lớn |
|---|---|---|
| `StripPrefix` / `RewritePath` | Không | Thường không cần buffer body |
| `AddRequestHeader` / `SetRequestHeader` | Không | Thường không cần buffer body |
| `CacheRequestBody` | **Có** | Caching/decoding request body có thể giữ dữ liệu lớn |
| `ModifyRequestBody` | **Có** | Decode, biến đổi, encode lại; có thể làm mất streaming |
| `ModifyResponseBody` | **Có** | Biến đổi response, có thể buffer output trước trả client |
| Route predicate dựa trên body | Có nếu implementation phải đọc body | Có thể cần cache để downstream đọc lại |
| `Retry` với body | Có thể phải giữ/replay body | Tăng memory và số outbound attempts |
| `LocalResponseCache` | Cache response đủ điều kiện | Không phù hợp mặc định cho unbounded live streams |
| Custom logging filter đọc body | Thường có | Dễ phá stream hoặc lộ dữ liệu |
| `RequestSize` / ingress upload limit | Kiểm soát kích thước | Không thay thế thiết kế streaming an toàn; kiểm tra behavior/version |

**Tác động không phải thuộc tính cố định của từng tên filter trong mọi bản Gateway**. Ví dụ một response converter có thể có các kỹ thuật streaming khác nhau tùy kiểu dữ liệu. Điều cần xác minh là **nó có aggregate hay giữ payload trong RAM/disk, có thay đổi bytes/headers không và có bị subscribe/retry lại không**.

## 6. CacheRequestBody: đọc và lưu để tái sử dụng không miễn phí

`CacheRequestBody` thường được dùng khi downstream filter cần đọc lại request body. Ở những bản Gateway hỗ trợ, có thể khai báo `bodyClass` để chỉ kiểu cần chuyển đổi:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: small-json-inspection
          uri: http://localhost:9090
          predicates:
            - Path=/api/json/**
            - Method=POST
          filters:
            - name: CacheRequestBody
              args:
                bodyClass: java.lang.String
~~~

Mục đích là làm việc với body theo kiểu `String` và giữ nội dung cho bước dùng sau, **không phải cách tối ưu hóa upload 2 GiB**. Kích thước thực được giữ phụ thuộc codec, cách decode và implementation.

Trong những flow cụ thể, cached body có thể được lưu ở exchange attribute như `ServerWebExchangeUtils.CACHED_REQUEST_BODY_ATTR`; **không biến attribute ấy thành một hợp đồng public cho mọi custom filter và mọi release train**. Cần dùng đúng API và xác minh lifecycle cleanup.

### Khi nào CacheRequestBody hợp lý?

- Body JSON nhỏ, có giới hạn size rõ.
- Nhu cầu nghiệp vụ thật sự cần kiểm tra nội dung trước routing.
- Có test body được forward **đầy đủ** sau khi filter đọc.
- Có giới hạn RAM/concurrency và codec aggregation.
- Không có request body nhạy cảm bị lưu/traced/logged ngoài chính sách.

### Khi nào cần tránh?

- Upload file hoặc multipart lớn.
- NDJSON truyền liên tục theo stream.
- SSE (là response stream, không phải request body để cache).
- WebSocket frames.
- API cần time-to-first-byte thấp và memory bounded.
- Request không có giới hạn kích thước từ ingress/Gateway/backend.

**Tăng `spring.codec.max-in-memory-size` để “sửa” một `DataBufferLimitException` không phải giải pháp mặc định.** Nó có thể cho phép một lần aggregate lớn hơn, nhưng **không kiểm soát tổng bộ nhớ khi có nhiều request đồng thời** và không làm pipeline trở thành streaming.

## 7. ModifyRequestBody: phù hợp JSON nhỏ, không mặc định phù hợp file lớn

`ModifyRequestBody` cho phép lấy body ở kiểu vào và tạo body mới ở kiểu ra. Với Gateway Server WebFlux, loại filter này trong nhiều phiên bản được cấu hình **qua Java DSL**. Ví dụ chỉ minh họa biến đổi `String` của một endpoint JSON nhỏ:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.http.MediaType;
import org.springframework.cloud.gateway.route.RouteLocator;
import org.springframework.cloud.gateway.route.builder.RouteLocatorBuilder;
import reactor.core.publisher.Mono;

@Bean
RouteLocator smallJsonRoute(RouteLocatorBuilder builder) {
    return builder.routes()
        .route("small-json-transform", r -> r
            .path("/api/json/**")
            .filters(f -> f.modifyRequestBody(
                String.class,
                String.class,
                MediaType.APPLICATION_JSON_VALUE,
                (exchange, body) -> Mono.justOrEmpty(body)
            ))
            .uri("http://localhost:9090"))
        .build();
}
~~~

Đây là **ví dụ cơ chế đổi body**, không thực hiện thay đổi thực chất: nó trả nội dung cũ. Việc decode cả body thành `String` có thể cần aggregate; chỉ dùng cho endpoint đã có **request-size limit nhỏ**. Không áp dụng cấu hình này cho file lớn chỉ để “đi qua filter”.

### Những hệ quả khi biến đổi bytes

Nếu filter thêm/bớt nội dung, phải xét:

- `Content-Length` cũ có còn đúng không?
- `Content-Type` và charset có đúng với dữ liệu mới không?
- `Content-Encoding` có còn phản ánh bytes đã nén không?
- Header `Digest`/checksum, chữ ký request hoặc signature canonicalization có bị sai không?
- Đối với multipart, `boundary`/từng part headers có được tạo lại đúng không?
- Backend có dùng HMAC/signature trên raw body không? Khi body thay đổi, chữ ký cũ có thể không còn hợp lệ.

**Không sửa body rồi giữ nguyên metadata vốn phụ thuộc body cũ**. Với những request đã được ký end-to-end, Gateway thường nên **không biến đổi body**, hoặc phải có hợp đồng ký/xác minh mới được thiết kế rõ.

### Khi body rỗng

Một số API `ModifyRequestBody` sử dụng publisher như `Mono.empty()` để biểu diễn body không có nội dung. Đừng ép body thành literal `"null"` hoặc chuỗi rỗng khi backend phân biệt **không có body** và **body chứa JSON null**. Kiểm thử cả trường hợp body absent, zero-byte, JSON null và body lỗi định dạng.

## 8. ModifyResponseBody: nguy cơ làm mất đặc tính streamed download

Một backend có thể vừa tạo dữ liệu vừa gửi ra HTTP response, chẳng hạn file CSV được xuất theo từng batch. Nếu Gateway dùng `ModifyResponseBody` chuyển toàn response thành `String` hoặc đối tượng JSON để thay chữ, nó có thể phải **chờ nhiều dữ liệu hoặc toàn bộ response** trước khi trả.

Trong nhiều phiên bản Gateway Server WebFlux, `ModifyResponseBody` cũng được cấu hình theo **Java DSL**, phù hợp nhất với response body **nhỏ và hữu hạn**.

Ví dụ minh họa về mặt DSL:

~~~java
@Bean
RouteLocator smallResponseRoute(RouteLocatorBuilder builder) {
    return builder.routes()
        .route("small-response-transform", r -> r
            .path("/api/small-response/**")
            .filters(f -> f.modifyResponseBody(
                String.class,
                String.class,
                (exchange, body) -> Mono.justOrEmpty(body)
            ))
            .uri("http://localhost:9090"))
        .build();
}
~~~

Đoạn này cũng là phép chuyển đổi identity, **không phải bộ lọc streaming**. Các kiểu đầu vào/đầu ra và codec quyết định cách body được materialize.

### Tại sao download lớn dễ bị ảnh hưởng?

1. Client chỉ bắt đầu nhận dữ liệu khi filter phát output; nếu cần đọc hết mới đổi được thì **time to first byte (TTFB) tăng**.
2. Mỗi download đồng thời có thể giữ một phần lớn response trong memory.
3. Nếu client hủy kết nối giữa chừng, pipeline phải cleanup buffers và hoạt động backend.
4. Nếu bytes đổi, `Content-Length`, `Content-Encoding`, `ETag` và `Content-Range` có thể không hợp lệ.
5. Filter response post-processing có thể chạy **sau khi response đã commit**, khi đó không thể đổi status/headers tùy ý.

**Không dùng `ModifyResponseBody(String.class, ...)` cho file ZIP/PDF/video lớn hoặc SSE không kết thúc** nếu chưa có kiểm chứng rằng implementation xử lý đúng cách stream và giới hạn memory.

## 9. Quan sát streaming body mà không tiêu thụ body

Có nhu cầu đo tổng số bytes Gateway forward, nhưng không muốn đọc body trước khi routing. Một cách ở tầng WebFlux là dùng `ServerHttpRequestDecorator` để **quan sát mỗi DataBuffer khi nó đi qua** và để subscriber phía sau tiếp tục tiêu thụ buffer.

Ví dụ kỹ thuật minh họa trong ứng dụng Gateway Server WebFlux:

~~~java
package example.gateway.streaming;

import java.util.concurrent.atomic.AtomicLong;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.cloud.gateway.filter.GatewayFilterChain;
import org.springframework.cloud.gateway.filter.GlobalFilter;
import org.springframework.core.Ordered;
import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.http.server.reactive.ServerHttpRequestDecorator;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Component
public final class UploadByteCounterFilter implements GlobalFilter, Ordered {

    private static final Logger log =
        LoggerFactory.getLogger(UploadByteCounterFilter.class);

    @Override
    public int getOrder() {
        return 0; // Ví dụ; kiểm tra order thực khi triển khai.
    }

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            GatewayFilterChain chain) {

        AtomicLong observedBytes = new AtomicLong();

        ServerHttpRequestDecorator request =
            new ServerHttpRequestDecorator(exchange.getRequest()) {
                @Override
                public Flux<DataBuffer> getBody() {
                    return super.getBody()
                        .doOnNext(buffer ->
                            observedBytes.addAndGet(
                                buffer.readableByteCount()));
                }
            };

        ServerWebExchange decorated =
            exchange.mutate().request(request).build();

        return chain.filter(decorated)
            .doFinally(signal ->
                log.debug("upload stream observedBytes={}, signal={}",
                    observedBytes.get(), signal));
    }
}
~~~

Đoạn code **không đọc `read(...)` trên DataBuffer, không join body, không gọi `subscribe()` và không giữ buffers để replay**. Nó chỉ quan sát `readableByteCount()` khi các buffers đi qua subscriber phía sau.

**Các giới hạn quan trọng:**

- Đây là **mẫu đo đơn giản**, không phải counter byte chuẩn có thể dùng làm billing/quota.
- `GlobalFilter` chỉ tham gia những Gateway routes được chọn; nó không đảm bảo đo cả request bị security chặn trước routing.
- Một request body có thể không được subscribe nếu route/filter dừng sớm, vì vậy tổng đếm có thể là 0.
- Nếu Retry hoặc body re-subscription xảy ra sau decorator, bytes có thể được đếm nhiều lần; cần phân biệt **client bytes**, **downstream bytes** và **outbound attempts**.
- Không có đảm bảo tất cả requests đã flush hết xuống backend khi `doFinally` được gọi.
- Chỉ log aggregate bytes, signal, route ID/correlation ID hợp lệ; không log raw body, token hay cookie.
- Bắt buộc kiểm thử cancellation, empty body, multi-part, load và leak detection ở phiên bản runtime.

Muốn đo throughput production chính xác, có thể đo tại HTTP server/client, Netty metrics hoặc các điểm instrumentation phù hợp; không khẳng định một custom filter như trên là nguồn duy nhất đáng tin.

## 10. Upload multipart/form-data: boundary, parts và bộ nhớ

Một upload trình duyệt thường gửi:

~~~http
POST /api/files/upload/media HTTP/1.1
Content-Type: multipart/form-data; boundary=----example-boundary
Content-Length: 52428800
~~~

Body chứa nhiều parts với header và bytes riêng. Nếu Gateway chỉ **proxy thông suốt**, nó không cần parse toàn bộ multipart thành các `FilePart` rồi ghép lại. Nếu một custom filter gọi các API decode multipart/form data để kiểm tra từng part, framework có thể dùng **buffering và/hoặc temporary storage** tùy codec và cấu hình.

### Hai chiến lược

| Mục tiêu | Cách tiếp cận |
|---|---|
| Auth, quota, route upload đến backend | Xác thực/định tuyến bằng metadata trước, **không parse file** ở Gateway |
| Kiểm tra virus/MIME thực/metadata của file | Chuyển tới **upload service** chuyên dụng, hoặc pipeline streaming/scanner được thiết kế cụ thể |
| Cần chỉnh một trường form nhỏ | Cân nhắc xử lý ở backend thay vì Gateway proxy |
| Upload rất lớn | Giới hạn kích thước ở ingress và backend, cân nhắc upload trực tiếp đến object storage bằng URL/token có thời hạn |
| Cần resume/restart upload | Thiết kế multipart/resumable API có offset/checksum/idempotency; đừng trông chờ retry HTTP chung |

### Multipart boundary không được thay đổi tùy tiện

Nếu filter tạo lại body multipart nhưng giữ `Content-Type` với boundary cũ, backend có thể không parse được. Tương tự, nếu filter nối/chia chunks và sửa bytes nhưng giữ checksum hoặc `Content-Length` cũ, upload có thể lỗi hoặc hỏng dữ liệu.

**Không gửi trực tiếp `FilePart` của Spring WebFlux vào một custom `GatewayFilter` mà chưa xác định ownership và temp-file lifecycle**. Những abstraction tiện xử lý upload ở controller không phải mặc định cần dùng trong proxy.

## 11. Giới hạn kích thước upload và codec memory limit

Một thiết kế upload cần nhiều tầng giới hạn:

| Tầng | Kiểm soát | Vì sao cần |
|---|---|---|
| CDN/Ingress/WAF | Request body limit, thời gian đọc, rate/connection | Chặn upload bất thường trước Gateway |
| Gateway route | `RequestSize` hoặc chính sách request-size phù hợp phiên bản | Tránh cho payload vượt policy vào backend |
| Spring WebFlux codec | `max-in-memory-size` cho những thao tác **aggregation/decoding** | Giới hạn một lần codec giữ body |
| Upload backend | Giới hạn file, loại file, quota user/tenant, checksum | Bảo vệ nghiệp vụ |
| Object storage | Multipart/part size, quota, lifecycle | Bảo vệ lưu trữ |
| Network/TLS | Timeouts, bandwidth, connection limits | Chống giữ tài nguyên quá lâu |

Một cấu hình minh họa cho Gateway hỗ trợ `RequestSize`:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: upload-with-size-policy
          uri: http://localhost:9090
          predicates:
            - Path=/api/files/upload/**
          filters:
            - name: RequestSize
              args:
                maxSize: 100MB
~~~

**Kiểm tra chính xác semantics của `RequestSize` ở Gateway phiên bản đang dùng**: nó có thể dựa trên `Content-Length` hoặc cơ chế riêng của filter; **không tự suy rằng mọi luồng chunked không khai báo length đều bị dừng đúng tại byte thứ 100.000.000**. Cần kiểm thử request có/không có Content-Length, HTTP chunked, multipart và request ngắt giữa chừng.

### Lỗi DataBufferLimitException

Nếu một body filter cố decode JSON/file lớn và vượt giới hạn in-memory, có thể gặp `DataBufferLimitException` hoặc lỗi tương tự. Hướng xử lý đúng là:

1. Xác định **filter/codec nào đang aggregate**.
2. Nếu là upload/file lớn, **loại thao tác aggregate** và chuyển streaming đúng nghĩa.
3. Nếu là JSON nhỏ, thiết lập giới hạn body có chủ đích, phù hợp concurrency.
4. Không tăng codec limit vô hạn chỉ để che lỗi.
5. Theo dõi heap, Netty direct memory, GC, pending connections và upload concurrency.

Giới hạn `max-in-memory-size` **không phải quota upload tổng** cho một route streaming không decode toàn body.

## 12. Download streaming, Range requests và HTTP metadata

Với download file, Gateway nên giữ semantics của HTTP representation. Một client có thể gửi:

~~~http
GET /api/files/download/report42 HTTP/1.1
Range: bytes=0-1048575
Accept: application/octet-stream
~~~

Backend hỗ trợ range có thể trả:

~~~http
HTTP/1.1 206 Partial Content
Content-Range: bytes 0-1048575/8388608
Content-Length: 1048576
Content-Type: application/octet-stream
Accept-Ranges: bytes
ETag: "report42-v3"
~~~

**Không tự biến `206 Partial Content` thành `200 OK` hoặc nối các chunks để trả body khác mà giữ `Content-Range`.** Nếu một response filter thay bytes, tất cả metadata liên quan representation có thể cần được tái tính hoặc loại bỏ.

### Các trường quan trọng

- `Content-Length`: nếu body được transform và thay kích thước, header cũ không còn đúng.
- `Content-Encoding`: body gzip không thể bị treat như text thường.
- `ETag` / `Last-Modified`: validator cần tương ứng representation mới.
- `Content-Range` và status `206`: phải đúng với byte range.
- `Accept-Ranges`: chỉ công bố khả năng range nếu end-to-end thực sự hỗ trợ.
- `Content-Disposition`: kiểm tra tên file/encoding an toàn, không dùng input không tin cậy.
- `Cache-Control`: response riêng tư cần policy thích hợp, không tự bật shared cache.
- `Access-Control-Expose-Headers`: browser JS chỉ đọc những response headers được phép theo CORS.

Với file lớn, một chiến lược thường tốt hơn là **không sửa response body tại Gateway**, bảo toàn Content-Range/ETag và để chuyên trách download service/object storage xử lý.

## 13. SSE và NDJSON: các luồng không nên chờ hoàn tất

**SSE** dùng HTTP response với `Content-Type: text/event-stream`. Server gửi từng sự kiện, ví dụ:

~~~text
event: progress
data: {"percent":10}

event: progress
data: {"percent":20}

: heartbeat

event: completed
data: {"percent":100}

~~~

Mỗi sự kiện thường được kết thúc bằng **dòng trống** theo định dạng SSE. Luồng có thể chạy lâu; `heartbeat` giúp một số proxy/client nhận biết kết nối còn hoạt động, tùy timeout và buffer behavior.

**NDJSON** gửi nhiều đối tượng JSON theo từng dòng:

~~~text
{"id":1,"state":"started"}
{"id":2,"state":"running"}
{"id":3,"state":"finished"}
~~~

Đây là **một luồng các JSON documents**, không phải một JSON array duy nhất. Một body transform coi toàn luồng là một `String` hoặc một POJO có thể chờ đến khi kết thúc, làm mất hiệu quả streaming.

### Route SSE không cần body filter

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: events-stream
          uri: lb://event-service
          predicates:
            - Path=/api/events/**
            - Method=GET
          filters:
            - StripPrefix=1
~~~

Client test:

~~~bash
curl -N -i "http://localhost:8080/api/events/orders"
~~~

Tùy backend, `curl -N` tắt output buffering ở phía cURL để in dữ liệu sớm hơn. Điều đó **không vô hiệu hóa buffering ở Gateway, ingress, TLS proxy hoặc backend**.

### Streaming response cần timeout phù hợp

Một SSE response có thể **không kết thúc**, nên `response-timeout` cấu hình quá ngắn hoặc idle timeout ở ingress/proxy có thể đóng kết nối. Tuy nhiên, tăng tất cả timeout thành “vô hạn” có nguy cơ làm đầy connection pool và tài nguyên.

Cần xác định:

- Timeout nào kiểm tra **chờ byte đầu tiên**, timeout nào kiểm tra **idle giữa các chunks**, timeout nào là **tổng lifetime**.
- Có heartbeat phù hợp với proxy idle timeout không.
- Browser/EventSource có reconnect không, có `Last-Event-ID` để resume không.
- Backend có ngừng việc khi client đã disconnect không.
- Concurrent connections và fan-out có bị giới hạn để tránh memory/FD exhaustion không.

**Không đồng nhất `spring.cloud.gateway.httpclient.response-timeout` với lifetime chính xác của mọi loại stream**; behavior phụ thuộc Reactor Netty/Gateway version và loại I/O. Hãy thử SSE trên từng hop thực, gồm ingress và TLS termination.

## 14. WebSocket: khác HTTP body streaming ở điểm nào?

Một WebSocket connection bắt đầu bằng HTTP handshake, sau đó nâng cấp giao thức và truyền **frames/messages** hai chiều.

Trong Gateway WebFlux hỗ trợ WebSocket routing, route có thể dùng scheme `ws://` hoặc `wss://`:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: chat-websocket
          uri: lb:ws://chat-service
          predicates:
            - Path=/ws/chat/**
~~~

**Lưu ý version:** cú pháp `lb:ws://` có thể được sử dụng để kết hợp load balancing và WebSocket ở các bản Gateway hỗ trợ. Nếu đang dùng một phiên bản khác, đối chiếu `Websocket Routing Filter`/`ReactiveLoadBalancerClientFilter` của bản đó. Không chuyển toàn bộ traffic WebSocket bằng `http://` rồi giả định upgrade tự hoạt động.

### Những khác biệt quan trọng

| HTTP streaming body | WebSocket |
|---|---|
| Request/response body HTTP đi qua filter chain | Sau upgrade, dữ liệu truyền theo WebSocket frames |
| `ModifyRequestBody` xử lý HTTP request payload | Không là bộ biến đổi các WebSocket frames |
| `Content-Length`/`Transfer-Encoding` liên quan framing HTTP | WebSocket có framing riêng |
| Retry HTTP có thể làm lại request | Không tự reconnect/replay messages an toàn |
| SSE thường server → client | WebSocket hai chiều |
| HTTP status/response headers còn dùng trước commit | Sau handshake, lỗi ở frames không thể đơn giản đổi HTTP status |

Spring Security/CORS/origin checks cần giải quyết **từ lúc handshake**; authorization trên từng message/action có thể còn là trách nhiệm của backend WebSocket app. Không xem WebSocket `Origin` header là bằng chứng danh tính; phải kiểm tra session/token và trust boundary theo thiết kế.

Một rate limiter cho request handshake **không tự giới hạn số WebSocket messages/giây** sau khi kết nối đã mở. Muốn chống lạm dụng, backend hoặc một gateway message-aware được thiết kế riêng phải có message/frame size limits, per-connection budgets và chính sách close.

## 15. Retry, CircuitBreaker và fallback trên upload/download stream

Retry đặc biệt nguy hiểm với các luồng **đã gửi một phần**.

### Upload bị đứt giữa chừng

~~~mermaid
sequenceDiagram
    participant C as Upload client
    participant G as Gateway
    participant B as Upload backend
    C->>G: POST body 200 MiB
    G->>B: Forward chunks đầu tiên
    B->>B: Đã ghi một phần dữ liệu
    B--xG: Kết nối đứt sau 80 MiB
    Note over G: Gateway không chắc backend đã commit gì
    G-->>C: Error / status theo policy
    Note over C,B: Retry tự động có thể tạo dữ liệu trùng nếu thiếu idempotency
~~~

Nếu `Retry` cần replay body, Gateway có thể phải **cache request body** hoặc dựa vào cơ chế body replay của pipeline. Với upload lớn, đó là chi phí bộ nhớ lớn; nếu backend đã ghi một phần file trước khi connection reset, retry có thể dẫn đến file trùng hoặc dữ liệu lỗi.

**Mặc định không bật Retry cho POST upload không idempotent**. Nếu bắt buộc retry upload, thiết kế **resumable uploads**, part IDs, checksums, idempotency keys, transaction/commit semantics và cleanup ở upload service.

### Download bị lỗi sau khi response đã commit

~~~text
Backend trả 200 và gửi được 3 MiB đầu
    ↓
Gateway đã gửi headers + 3 MiB cho client
    ↓
Backend bị đứt kết nối
    ↓
Không thể luôn đổi response đã commit thành HTTP 503 JSON fallback mới
~~~

Circuit breaker/fallback có thể hỗ trợ trước khi response commit, nhưng sau khi bytes đã gửi, việc thay status/body thường không còn khả thi. Cần định nghĩa contract cho partial download, retry **ở phía client theo Range** nếu backend hỗ trợ, hoặc để client phát hiện checksum/độ dài không khớp.

### Các mối tương tác

| Cơ chế | Lưu ý với stream |
|---|---|
| `RequestRateLimiter` | Thường giới hạn **request**, không tự tính bytes/sec hoặc WebSocket messages |
| `Retry` | Có thể buộc replay/cache body; có nguy cơ duplicate side effects |
| `CircuitBreaker` | Một luồng dài có thể tạo latency/error semantics khác call ngắn |
| `FallbackHeaders` | Truyền error metadata sang fallback, không thể sửa response đã commit |
| `LocalResponseCache` | Không phù hợp mặc định cho SSE/unbounded streams hoặc private file |
| `lb://` | Chọn instance; không bảo đảm stream migrate khi instance chết |
| TLS/mTLS | Bảo vệ chặng, nhưng có chi phí handshake, buffers và timeout |
| Spring Security | AuthN/AuthZ trước route; cần backend kiểm tra quyền đối tượng/file |

## 16. Timeouts, backpressure và cancellation trong sản xuất

Một kết nối streaming có ba thời gian khác nhau:

1. **Connect timeout:** Gateway mất bao lâu để kết nối backend.
2. **Read/response idle timeout:** chờ bytes/chunks tiếp theo bao lâu trước khi coi là không phản hồi.
3. **Total lifetime/deadline:** toàn upload/download được phép sống bao lâu.

Nếu đặt mỗi loại quá thấp, upload mạng chậm bị đóng oan. Nếu không đặt giới hạn, client chậm có thể giữ connection, memory và file descriptors rất lâu (**slow upload / slow client**).

### Budget phải theo loại API

| API | Gợi ý chính sách |
|---|---|
| JSON nhỏ | Timeout ngắn và codec max-in-memory-size có giới hạn |
| Upload file lớn | Tổng duration/idle limits phù hợp kích thước; giới hạn concurrency và bytes |
| Download file lớn | Timeout chờ origin, client disconnect cleanup, Range/checksum |
| SSE | Heartbeat + idle policy phù hợp, max connections và reconnect strategy |
| WebSocket | Handshake timeout, frame/message size, ping/pong/idle, max connections |
| Nền tảng nhiều tenants | Byte quota và concurrency quota theo principal/tenant đáng tin |

**Backpressure giúp điều tiết tốc độ giữa publisher và subscriber**, nhưng không thể thay thế quota bandwidth, request-size limit, timeout hay bảo vệ hạ tầng. Một filter tự `subscribe()`, dùng unbounded queue hoặc buffer tất cả có thể làm mất tác dụng của backpressure.

### Khi client hủy request

Hủy HTTP request thường dẫn tới tín hiệu cancellation ở reactive pipeline, nhưng:

- Backend có thể đã commit file/DB transaction.
- TCP socket có thể chưa đóng ngay nếu còn buffering/retry.
- Cache/temporary files có thể cần cleanup.
- Một số external jobs không nhận được cancellation.
- Không thể dùng cancellation làm bằng chứng side effect chưa xảy ra.

Cần thiết kế **idempotency, cleanup và job status** riêng cho thao tác kéo dài.

## 17. Kiểm thử trực tiếp upload/download qua Gateway

### Môi trường lab

Giả định:

- Gateway WebFlux chạy `http://localhost:8080`.
- Backend upload/download test chạy `http://localhost:9090`.
- Route direct HTTP đến backend tương ứng với `/api/files/upload/**` và `/api/files/download/**`.
- Backend test có endpoint ghi file và trả checksum, cùng endpoint trả file/stream theo chunks.
- Không có CDN cache hoặc reverse proxy buffer trong thử nghiệm đầu tiên.
- Có quyền test tải lớn trên môi trường **không chứa dữ liệu cá nhân**.

**Không nên dùng file chứa bí mật thực** để làm phép đo memory hoặc log payload.

### Bước 1 — Tạo file thử và đo kích thước

Ở môi trường POSIX có thể dùng:

~~~bash
# Tạo 32 MiB dữ liệu giả. Không dùng file production.
dd if=/dev/zero of=upload-test.bin bs=1M count=32
wc -c upload-test.bin
~~~

Trên Windows dùng công cụ tương đương của môi trường test. Mục tiêu là có payload xác định để so sánh, không phải cố định file phải bằng 32 MiB.

### Bước 2 — Upload trực tiếp backend

~~~bash
curl -i -X POST \
  -H "Content-Type: application/octet-stream" \
  --data-binary "@upload-test.bin" \
  "http://localhost:9090/upload/media"
~~~

Backend test phải có endpoint `POST /upload/media`. Ghi lại bytes nhận, checksum, thời gian upload và memory baseline.

### Bước 3 — Upload qua Gateway không có body filter

~~~bash
curl -i -X POST \
  -H "Content-Type: application/octet-stream" \
  --data-binary "@upload-test.bin" \
  "http://localhost:8080/api/files/upload/media"
~~~

Với route `StripPrefix=2` ở phần 3, backend sẽ nhận path `/upload/media`. So sánh:

- Bytes và checksum của file ở backend.
- HTTP status/response body.
- Latency, throughput và CPU/memory ở Gateway.
- Có request nào bị limit/timeout từ ingress hoặc Gateway không.
- Gateway có giữ memory tăng gần tương ứng toàn file × concurrency không.

Kết quả **đúng** không nhất thiết có cùng số chunks hoặc cùng `Transfer-Encoding` ở mỗi hop, nhưng **payload và hợp đồng HTTP phải tương đương**.

### Bước 4 — Thử multipart

~~~bash
curl -i \
  -F "description=demo" \
  -F "file=@upload-test.bin;type=application/octet-stream" \
  "http://localhost:8080/api/files/upload/media"
~~~

Bài test này cần backend hỗ trợ `multipart/form-data`. Kiểm tra `description`, tên file, số bytes và `Content-Type` boundary hợp lệ. Khi Gateway không sửa body, backend vẫn phải đọc đúng từng part.

### Bước 5 — Download và so checksum

~~~bash
curl -fS \
  -o download-via-gateway.bin \
  "http://localhost:8080/api/files/download/report42"

# Khi có endpoint trực tiếp tương ứng:
curl -fS \
  -o download-direct.bin \
  "http://localhost:9090/download/report42"

sha256sum download-via-gateway.bin download-direct.bin
~~~

Nếu cùng backend version/tài nguyên bất biến, checksum phải khớp. Nếu tài nguyên có thể thay đổi trong lúc test, dùng ETag/version cố định hoặc object immutable.

### Bước 6 — Range request

~~~bash
curl -i \
  -H "Range: bytes=0-1023" \
  "http://localhost:8080/api/files/download/report42"
~~~

Nếu backend hỗ trợ byte range và Gateway không làm hỏng metadata, kiểm tra `206`, `Content-Range`, số bytes nhận, `ETag`. Không tự kỳ vọng mọi backend đều hỗ trợ Range; nếu backend trả 200 nguyên file, đó là contract backend cần được xác minh.

### Bước 7 — Đo SSE có gửi chunk sớm

~~~bash
curl -N -i --max-time 12 \
  "http://localhost:8080/api/events/orders"
~~~

So sánh thời điểm nhận từng `data:` với gọi thẳng event backend. Nếu tất cả sự kiện chỉ xuất hiện sau khi stream kết thúc hoặc sau khoảng buffering lớn, kiểm tra codecs/body filters, ingress proxy buffering, compression và flushing.

### Bước 8 — So sánh có/không có body filter

Chỉ trên **route lab** và payload nhỏ có giới hạn:

1. Đo baseline streaming không body filters.
2. Bật `CacheRequestBody` với `String` trên route test nhỏ, theo dõi heap/GC.
3. Bật `ModifyRequestBody` qua Java DSL trên route JSON nhỏ, đo TTFB và memory.
4. Tăng số requests đồng thời trong mức kiểm soát, ghi memory peak và lỗi `DataBufferLimitException` nếu có.
5. Không áp các bước aggregation này lên file lớn/trên production chỉ để chứng minh hệ thống có thể hỏng.

**Mục tiêu:** chứng minh body filter nào có thể làm tăng memory/độ trễ và lựa chọn **không dùng body filter** trên route streaming khi không cần.

## 18. Ma trận kiểm thử correctness và khả năng chịu tải

| Case | Điều cần khẳng định |
|---|---|
| Upload 0 byte | Backend nhận đúng body rỗng, không tự thành literal null |
| Upload binary chứa byte 0x00 | Không bị coi là chuỗi UTF-8 và sửa bytes |
| Upload nhiều chunks | Số byte/checksum giữ nguyên dù ranh giới chunks đổi |
| Upload multipart | Boundary, phần form và file được backend parse đúng |
| Client abort giữa upload | Gateway/backend cleanup hợp lý, không có resource leak |
| Backend abort giữa download | Client thấy lỗi/truncated body phù hợp, không tự đổi 503 sau commit |
| Download Range `206` | Content-Range, bytes, length và validator khớp |
| Gzip/identity | Content-Encoding khớp bytes thực |
| SSE long-lived | Sự kiện được flush sớm, không đợi stream kết thúc |
| NDJSON | Các dòng được chuyển liên tục, không buộc gom toàn JSON |
| WebSocket upgrade | Handshake thành công, frames đi đúng tuyến, không áp HTTP body transform |
| RequestSize vượt giới hạn | Policy có hiệu lực với Content-Length và trường hợp chunked theo version |
| Codec memory limit | Body JSON quá lớn bị từ chối hoặc xử lý theo policy, không OOM |
| Retry + POST upload | Không tạo side effects trùng khi đường truyền đứt |
| LocalResponseCache | Không giữ stream riêng tư/unbounded làm shared entry |
| JWT/cookie/tenant | Không rò quyền/file giữa users và tenants |
| 50+ concurrent uploads (lab có giới hạn) | Memory/FD/GC/latency được giám sát, không tăng không kiểm soát |
| Nhiều Gateway instances | Routing, headers, checksum và timeout nhất quán |
| TLS/ingress thực | Không buffer tùy tiện, các idle timeouts tương thích |

Kết quả cần đo từ **client, Gateway và backend**, không chỉ xem một response 200. Một server có thể trả HTTP 200 sớm rồi thất bại khi ghi file; test phải kiểm tra **kết quả cuối** và cleanup.

## 19. Troubleshooting lỗi do body filters

| Triệu chứng | Nguyên nhân thường gặp | Kiểm tra |
|---|---|---|
| Upload lớn bị `DataBufferLimitException` | Có filter/codec aggregate body | Xác định `CacheRequestBody`/`ModifyRequestBody` hoặc multipart decoding |
| Body downstream rỗng | Custom filter đã consume body mà không replay | Kiểm tra một subscription và request decorator |
| Gateway tăng heap/direct memory mạnh | Caching/buffering/retry body, concurrency lớn | Heap/direct memory, Netty leak detector, GC |
| Stream SSE chỉ ra khi kết thúc | Response body bị aggregate hoặc proxy buffering | Tắt body transform, kiểm tra flushing từng hop |
| Multipart parser ở backend báo sai boundary | Body bị sửa nhưng `Content-Type` chưa đổi | So body raw/headers và cách encode |
| Download bị lỗi checksum | Filter biến đổi bytes, compression/encoding mismatch | So checksum trực tiếp backend/Gateway |
| `206` trả sai số bytes | Range handling hoặc body transform làm sai Content-Range | Test partial bytes và metadata |
| `Content-Length` không khớp | Body đã đổi size nhưng header cũ còn | Kiểm tra framing và content metadata |
| Retry làm xuất hiện file trùng | POST upload được replay sau khi backend đã ghi | Thiết kế idempotency/resumable upload |
| SSE bị 504 dù backend khỏe | Timeout/idle policy không hợp stream | Xem timeouts Netty, ingress và heartbeat |
| Client disconnect nhưng backend còn ghi | Cancellation không dừng side effect đã bắt đầu | Kiểm tra cleanup/idempotency và backend logs |
| WebSocket handshake fail | Scheme/upgrade/proxy khác với HTTP route | Kiểm tra `ws/wss`, headers, LB và Origin/auth |
| WebSocket frames không qua body filter | Đây không phải HTTP request body | Dùng WebSocket message-aware component |
| Mất `Authorization` khi forward | Header filter/security policy sai | Kiểm tra trust boundary và filter order |
| Tất cả uploads qua một instance kém | Discovery/LoadBalancer hoặc connection pool | Ghi instance ID, metrics và health |
| Test chỉ chạy đúng khi không có TLS | Proxy/TLS buffering, timeout, certificate trust | Test end-to-end qua ingress |
| Response bị cố đổi status sau khi đã gửi bytes | Response đã commit | Thiết kế streaming error contract |

### Sáu câu hỏi khi điều tra

1. Request/response có thật sự **streaming**, hay body bị decode/join/cached ở đâu?
2. Factory nào trong **route filter chain** đọc/sửa body; có filter mặc định/global khác không?
3. Gateway có giữ quá nhiều `DataBuffer` hoặc replay body do `Retry` không?
4. HTTP headers `Content-Length`, `Content-Encoding`, `Content-Range`, `Content-Type` có khớp bytes sau filter không?
5. Timeout xảy ra ở **client, ingress, Gateway HTTP client hay backend**?
6. Lỗi phát sinh **trước response commit hay sau commit**; có cần thiết kế resume/checksum/idempotency khác không?

Không chẩn đoán chỉ từ HTTP 200, và không bật log raw request/response bodies ở production để “xem cho rõ”.

## 20. Checklist trước khi đưa vào production

- [ ] Tôi phân biệt HTTP upload, download, SSE/NDJSON và WebSocket frames.
- [ ] Tôi biết streaming **không cần aggregate toàn body**, nhưng vẫn có network/TLS/Netty buffers.
- [ ] Tôi biết `Flux<DataBuffer>`, pooled buffer lifecycle và backpressure/cancellation.
- [ ] Tôi không tự `subscribe()`, `block()` hoặc giữ `DataBuffer` ngoài lifecycle khi chưa quản lý ownership.
- [ ] Tôi không gọi `DataBufferUtils.join(...)` vô giới hạn trên upload lớn.
- [ ] Tôi phân loại `CacheRequestBody`/`ModifyRequestBody`/`ModifyResponseBody` theo khả năng aggregate.
- [ ] Tôi không áp body transforms cho file lớn/SSE/unbounded streaming chỉ vì muốn log nội dung.
- [ ] Tôi kiểm tra `RequestSize`, ingress size limit và `spring.codec.max-in-memory-size` đúng vai trò.
- [ ] Tôi giữ nguyên multipart boundary và các HTTP framing/content headers khi không đổi bytes.
- [ ] Nếu sửa body, tôi xử lý `Content-Length`, `Content-Encoding`, `ETag`, chữ ký và checksum.
- [ ] Tôi kiểm thử HTTP `Range`/`206`/`Content-Range` cho download nếu API hỗ trợ.
- [ ] Tôi biết `Retry` với body có thể đòi buffering/replay và tạo side effect trùng.
- [ ] Tôi chỉ retry upload khi backend có contract idempotency/resumable rõ ràng.
- [ ] Tôi không kỳ vọng fallback đổi status/body sau khi response đã commit.
- [ ] Tôi có heartbeat, timeout/idle policy và reconnect/resume cho stream dài.
- [ ] Tôi không coi rate limiting theo HTTP request là byte quota hoặc WebSocket message quota.
- [ ] Tôi bảo vệ file access theo user/tenant ở Gateway và backend, không tin header giả mạo.
- [ ] Tôi kiểm soát TLS, service discovery, slow clients, connection pools và max concurrency.
- [ ] Tôi đo TTFB, throughput, backend bytes, heap, direct memory, GC và connection count.
- [ ] Tôi kiểm thử cancel, upload partial, multipart, Range, SSE, WebSocket và multi-instance end-to-end.
- [ ] Tôi không log raw file bytes, access tokens, session cookies hoặc dữ liệu nhạy cảm.
- [ ] Tôi có kế hoạch tắt body filter/rollback khi memory leak hoặc data corruption được phát hiện.

## Tài liệu tham khảo chính thức

- [Spring Cloud Gateway Reference](https://docs.spring.io/spring-cloud-gateway/reference/) — các mục **CacheRequestBody**, **ModifyRequestBody**, **ModifyResponseBody**, **RequestSize**, **Retry**, WebSocket routing và Gateway Server WebFlux theo phiên bản.
- [Spring Framework — WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux.html) — request/response streaming, multipart, SSE và reactive HTTP.
- [Spring Framework — Data Buffers and Codecs](https://docs.spring.io/spring-framework/reference/core/databuffer-codec.html) — `DataBuffer`, `DataBufferUtils`, reference counting và codec limits.
- [Spring Framework — WebSocket](https://docs.spring.io/spring-framework/reference/web/webflux-websocket.html) — WebSocket handshake, messages và lifecycle.
- [Project Reactor Reference](https://projectreactor.io/docs/core/release/reference/) — `Flux`/`Mono`, backpressure, cancellation và operator behavior.
- [Reactor Netty Reference](https://projectreactor.io/docs/netty/release/reference/) — HTTP client/server, connection pooling, timeout và metrics.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110) — framing/representation metadata, Range requests, status `206` và validators.
- [MDN — Server-sent events](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events) — định dạng SSE và kết nối `EventSource`.

**Ghi nhớ:** Trong Gateway Server WebFlux, upload/download và SSE có thể đi qua pipeline **`Flux<DataBuffer>`** theo từng phần, nhưng một filter đọc/cached/biến đổi toàn body có thể **biến streaming thành buffering**, tăng memory và trễ TTFB. Hãy ưu tiên **route theo path/header mà không đọc bytes**, chỉ biến đổi body nhỏ có giới hạn, kiểm soát reference counting/cancellation, bảo toàn HTTP metadata, và kiểm thử end-to-end cả checksum, Range, SSE, thời gian chờ và abort. Với WebSocket, **frames sau handshake là một mô hình khác**, không phải request body để `ModifyRequestBody` xử lý.
