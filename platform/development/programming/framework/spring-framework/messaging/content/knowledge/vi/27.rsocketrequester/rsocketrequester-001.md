# Tạo RSocketRequester.Builder và cấu hình kết nối

`RSocketRequester` là API fluent của Spring để gửi request RSocket bằng object Java và nhận kết quả dưới dạng `Mono` hoặc `Flux`. Ở phía client, `RSocketRequester.builder()` tạo builder để cấu hình connection, `SETUP` frame, MIME type, codec và transport. Sau khi gọi `tcp(...)` hoặc `websocket(...)`, ta nhận một `RSocketRequester` có thể tái sử dụng cho nhiều request trên cùng connection.

Bài này tập trung vào cách tạo client requester với Spring Framework 6.x. RSocket là giao thức ứng dụng hai chiều, hỗ trợ nhiều kiểu tương tác và có thể chạy trên TCP hoặc WebSocket.

## 1. RSocketRequester và vòng đời kết nối

RSocket là giao thức ứng dụng cho giao tiếp hai chiều (duplex), multiplex trên một kết nối. Sau khi connection được thiết lập, cả hai đầu đều có thể gửi request; khái niệm client và server chỉ mô tả vai trò trong một request cụ thể.

RSocket hỗ trợ bốn kiểu tương tác chính:

| Kiểu | Ý nghĩa | Kết quả thường dùng |
|---|---|---|
| Request-Response | Gửi một message và nhận một message trả lời | `Mono<T>` |
| Request-Stream | Gửi một request và nhận một stream message | `Flux<T>` |
| Fire-and-Forget | Gửi một message một chiều, không chờ response | `Mono<Void>` báo hoàn tất gửi |
| Request-Channel | Gửi một stream request và nhận một stream response | `Flux<T>` hai chiều |

Với stream, RSocket sử dụng Reactive Streams demand và backpressure để requester có thể điều tiết tốc độ responder phát dữ liệu. Đây là một điểm khác biệt so với việc chỉ gửi nhiều HTTP request độc lập.

`RSocketRequester` che giấu phần lớn thao tác với `io.rsocket.Payload`, `ByteBuf` hoặc `DataBuffer`. Ứng dụng làm việc với object Java, route và metadata thông qua API cấp cao hơn.

## 2. Tạo requester bằng TCP hoặc WebSocket

Cách đơn giản nhất là gọi static factory `RSocketRequester.builder()` rồi chọn transport:

~~~java
import java.net.URI;
import org.springframework.messaging.rsocket.RSocketRequester;

RSocketRequester tcpRequester =
        RSocketRequester.builder().tcp("localhost", 7000);

RSocketRequester websocketRequester =
        RSocketRequester.builder().websocket(
                URI.create("ws://localhost:8080/rsocket"));
~~~

Hai phương thức tạo requester khác nhau ở transport:

- `tcp(host, port)` kết nối tới RSocket server đang lắng nghe trên TCP host và port tương ứng.
- `websocket(uri)` kết nối tới RSocket endpoint được expose qua WebSocket. URI thường dùng `ws://` hoặc `wss://`.
- `transport(ClientTransport)` cho phép truyền vào một `ClientTransport` đã được khởi tạo nếu cần transport tùy chỉnh.

Endpoint và transport phải khớp với cách server được cấu hình. Ví dụ, TCP server phải lắng nghe đúng port; WebSocket server phải expose đúng path `/rsocket`. URL REST thông thường không tự động trở thành RSocket endpoint chỉ vì dùng HTTP port.

### Connection được tạo khi nào?

`tcp(...)` và `websocket(...)` trả về `RSocketRequester`; chúng không buộc ứng dụng phải mở kết nối ngay tại thời điểm tạo object. Connection được thiết lập khi request đầu tiên được subscribe và cần gửi đi. Các request sau có thể dùng chung connection; requester hỗ trợ nhiều request đồng thời và connection có thể được thiết lập lại khi có request tiếp theo sau khi kết nối trước bị mất.

Ví dụ:

~~~java
RSocketRequester requester =
        RSocketRequester.builder().tcp("localhost", 7000);

// Chưa có request nào được subscribe ở thời điểm này.
Mono<Product> productMono = requester.route("catalog.find")
        .data("SKU-42")
        .retrieveMono(Product.class);

// Connection được sử dụng khi publisher được subscribe.
productMono.subscribe(
        product -> System.out.println(product.name()),
        error -> System.err.println("RSocket request failed: " + error.getMessage()));
~~~

Không gọi `block()` trong WebFlux event loop hoặc trong một reactive handler. Nếu ứng dụng đang dùng reactive end-to-end, hãy trả về `Mono`/`Flux` cho framework subscribe. `block(Duration)` chỉ phù hợp ở ranh giới imperative như chương trình dòng lệnh hoặc startup code có chủ đích chờ kết quả.

### Tên API hiện hành

Dùng `tcp(host, port)` và `websocket(uri)` trong Spring Framework 6.x. Các phương thức cũ `connectTcp(...)` và `connectWebSocket(...)` đã deprecated từ Spring Framework 5.3 để chuyển sang API trả về `RSocketRequester` trực tiếp.

## 3. Cấu hình RSocketRequester.Builder

Builder cho phép cấu hình các phần sau trước khi tạo requester:

| Phương thức | Vai trò |
|---|---|
| `dataMimeType(MimeType)` | MIME type cho data trên connection, khai báo trong `SETUP` |
| `metadataMimeType(MimeType)` | MIME type cho metadata trên connection |
| `rsocketStrategies(...)` | Encoder, decoder và chiến lược xử lý route/metadata |
| `setupData(Object)` | Data tùy chọn gửi trong `SETUP` |
| `setupRoute(String, Object...)` | Route tùy chọn gắn với `SETUP` |
| `setupMetadata(Object, MimeType)` | Metadata tùy chọn gắn với `SETUP` |
| `rsocketConnector(...)` | Tùy chỉnh trực tiếp `RSocketConnector` bên dưới |

Ví dụ cấu hình JSON và kết nối TCP:

~~~java
package com.example.rsocket;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.codec.json.Jackson2JsonDecoder;
import org.springframework.http.codec.json.Jackson2JsonEncoder;
import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.messaging.rsocket.RSocketStrategies;
import org.springframework.util.MimeTypeUtils;

@Configuration
public class RSocketClientConfiguration {

    @Bean
    public RSocketStrategies rsocketStrategies() {
        return RSocketStrategies.builder()
                .encoders(encoders -> encoders.add(new Jackson2JsonEncoder()))
                .decoders(decoders -> decoders.add(new Jackson2JsonDecoder()))
                .build();
    }

    @Bean(destroyMethod = "dispose")
    public RSocketRequester catalogRequester(RSocketStrategies strategies) {
        return RSocketRequester.builder()
                .dataMimeType(MimeTypeUtils.APPLICATION_JSON)
                .rsocketStrategies(strategies)
                .tcp("localhost", 7000);
    }
}
~~~

Ví dụ giả định ứng dụng có các dependency tương thích của Spring Messaging, Spring Web/codecs, Jackson và RSocket TCP transport. Phía server phải hỗ trợ cùng data MIME type và route được client gọi.

`@Bean(destroyMethod = "dispose")` cho Spring biết cần dispose requester khi application context dừng. Nếu tạo requester ngoài Spring container, ứng dụng phải tự quản lý vòng đời và gọi `dispose()` khi không còn sử dụng connection.

## 4. RSocketStrategies và chuyển đổi dữ liệu

`RSocketStrategies` tập hợp các thành phần Spring dùng để encode và decode data/metadata. Builder nhận strategies qua `rsocketStrategies(...)`.

Mặc định, các codec cơ bản từ `spring-core` hỗ trợ `String`, `byte[]` và `ByteBuffer`. Khi cần trao đổi DTO, JSON, CBOR hoặc định dạng khác, hãy đăng ký encoder/decoder tương ứng. Các codec JSON/CBOR của Spring nằm trong `spring-web`; định dạng JSON còn cần Jackson trên classpath.

Ví dụ:

~~~java
RSocketStrategies strategies = RSocketStrategies.builder()
        .encoders(encoders -> encoders.add(new Jackson2JsonEncoder()))
        .decoders(decoders -> decoders.add(new Jackson2JsonDecoder()))
        .build();
~~~

Encoder dùng để chuyển object gửi đi thành data bytes; decoder chuyển data nhận được thành object đích. Hai đầu phải thống nhất MIME type và định dạng payload. Chỉ thêm decoder ở client không làm server tự động hiểu định dạng đó.

`dataMimeType(...)` khai báo MIME type data ở cấp connection thông qua `SETUP`. Nếu không đặt rõ, Spring suy ra từ decoder đã cấu hình, ưu tiên decoder không phải mặc định đầu tiên. Khi ứng dụng trao đổi JSON, nên khai báo rõ `application/json` để hợp đồng giữa hai đầu dễ đọc và tránh phụ thuộc thứ tự codec.

`RSocketStrategies` có thể được dùng lại giữa client và server trong cùng ứng dụng, miễn là tập codec và route matcher phù hợp với cả hai vai trò. Không cần tạo một bộ strategies mới cho từng request.

## 5. Data MIME type và metadata MIME type

Mỗi RSocket message có thể chứa data, metadata hoặc cả hai. Hai phần có thể dùng định dạng khác nhau:

- Data thường chứa payload nghiệp vụ, chẳng hạn DTO, chuỗi hoặc byte array.
- Metadata thường chứa route, token xác thực, tracing information hoặc thông tin điều khiển.
- MIME type của data và metadata được khai báo trong `SETUP` và áp dụng cho connection.

`dataMimeType(...)` xác định cách mã hóa/giải mã data. `metadataMimeType(...)` xác định cách diễn giải metadata.

Mặc định Spring dùng composite metadata MIME type `message/x.rsocket.composite-metadata.v0`. Composite metadata cho phép một payload metadata chứa nhiều entry độc lập, mỗi entry có MIME type riêng. Đây là lựa chọn phù hợp khi request cần routing metadata cùng metadata xác thực hoặc tracing.

Thông thường không cần đổi `metadataMimeType(...)`. Nếu thay bằng một MIME type đơn, ứng dụng và server phải thống nhất định dạng mới; route được cung cấp cũng được mã hóa theo MIME type đó. Không thay metadata MIME type chỉ vì muốn thay JSON data MIME type: hai cấu hình có mục đích riêng.

## 6. Cấu hình SETUP frame

Sau khi transport được mở, client gửi một RSocket `SETUP` frame để khởi tạo connection. Builder cho phép thêm data, route và metadata vào frame này:

~~~java
RSocketRequester requester = RSocketRequester.builder()
        .dataMimeType(MimeTypeUtils.APPLICATION_JSON)
        .setupRoute("client.connect")
        .setupData(new ClientInfo("inventory-worker", "1.0"))
        .setupMetadata(
                "tenant-42",
                MimeType.valueOf("message/x.example.tenant.v1"))
        .rsocketStrategies(strategies)
        .tcp("localhost", 7000);
~~~

Trong ví dụ:

- `setupRoute(...)` gắn route với sự kiện thiết lập connection.
- `setupData(...)` thêm một data object vào payload của `SETUP`.
- `setupMetadata(...)` thêm metadata có MIME type riêng.
- `dataMimeType(...)` quyết định cách encode `setupData`.
- `metadataMimeType(...)` mặc định vẫn là composite metadata, cho phép route và metadata entry cùng tồn tại.

Data và metadata trong `SETUP` đều là tùy chọn. Server có thể xử lý nội dung này bằng `@ConnectMapping`. Route trong `SETUP` dùng để định tuyến xử lý sự kiện kết nối; nó không thay thế route của từng request được tạo bằng `requester.route(...)`.

Nếu gọi `setupMetadata(...)` nhiều lần hoặc kết hợp nó với `setupRoute(...)`, phải sử dụng composite metadata. Server cũng phải hỗ trợ decoder/metadata extractor tương ứng. Đừng gửi một kiểu metadata mà server không đăng ký xử lý.

### SETUP metadata và request metadata khác nhau

`setupMetadata(...)` áp dụng cho lần thiết lập connection. Nếu cần gửi metadata riêng cho từng request, dùng `metadata(value, mimeType)` trên request spec:

~~~java
MimeType tokenMimeType =
        MimeType.valueOf("message/x.rsocket.authentication.bearer.v0");

Mono<Account> accountMono = requester.route("accounts.current")
        .metadata(accessToken, tokenMimeType)
        .retrieveMono(Account.class);
~~~

Ví dụ trên yêu cầu server có cơ chế xác thực và decoder phù hợp với bearer metadata. Không đưa token vào route hoặc payload nghiệp vụ. Trong môi trường production, bảo vệ transport bằng TLS (ví dụ `wss://` hoặc TCP transport có TLS) và áp dụng xác thực/phân quyền ở server.

## 7. Tùy chỉnh RSocketConnector và transport

Builder có `rsocketConnector(...)` để cấu hình `io.rsocket.core.RSocketConnector` bên dưới. Đây là điểm mở rộng cho các thiết lập cấp giao thức như keepalive, session resumption, interceptor và client-side acceptor.

~~~java
RSocketRequester requester = RSocketRequester.builder()
        .rsocketConnector(connector -> {
            // Cấu hình keepalive, resumption hoặc interceptor
            // theo phiên bản RSocket Java đang được ứng dụng sử dụng.
        })
        .tcp("localhost", 7000);
~~~

Không đặt các tham số keepalive một cách tùy tiện. Chúng phải phù hợp với timeout mạng, proxy, khả năng của server và yêu cầu vận hành. Keepalive của RSocket là cơ chế cấp protocol; nó không phải message nghiệp vụ và không thay thế timeout của từng request.

Nếu transport không phải TCP hoặc WebSocket mặc định, khởi tạo `ClientTransport` tương ứng rồi truyền vào `transport(...)`. Cách này hữu ích khi cần cấu hình TLS, địa chỉ mạng, event loop hoặc transport đặc thù. Đảm bảo client và server dùng transport tương thích.

Builder cũng hỗ trợ `transports(...)` với danh sách load-balancing target và strategy. Chỉ dùng API này khi ứng dụng có nhiều RSocket server target và đã xác định chính sách chọn target; với một endpoint đơn, `tcp(...)` hoặc `websocket(...)` đơn giản hơn.

## 8. Dùng requester sau khi cấu hình

Sau khi có `RSocketRequester`, mỗi request bắt đầu bằng route. Route là metadata dùng để tìm responder trên server; route không phải URL path HTTP.

Ví dụ request-response:

~~~java
Mono<Product> productMono = requester.route("catalog.find")
        .data("SKU-42")
        .retrieveMono(Product.class);
~~~

Request-stream:

~~~java
Flux<Product> products = requester.route("catalog.search")
        .data(new ProductSearch("keyboard"))
        .retrieveFlux(Product.class);
~~~

Fire-and-forget:

~~~java
Mono<Void> sent = requester.route("audit.record")
        .data(new AuditEvent("user-17", "viewed-catalog"))
        .send();
~~~

`send()` chỉ báo việc gửi message đã hoàn tất ở phía client; nó không chứng minh server đã xử lý nghiệp vụ thành công. Nếu cần response hoặc xác nhận nghiệp vụ, dùng request-response hoặc một giao thức xác nhận riêng.

Với request không cần data, có thể bỏ `.data(...)`:

~~~java
Mono<SystemStatus> status = requester.route("system.status")
        .retrieveMono(SystemStatus.class);
~~~

Các phương thức trả về Reactor `Mono`/`Flux`, nên request chỉ thực sự được thực thi khi publisher được subscribe. Hãy nối publisher vào reactive pipeline, hoặc subscribe ở ranh giới imperative có xử lý lỗi rõ ràng.

## 9. Quản lý connection, lỗi và tái sử dụng

Một requester được tạo từ `tcp(...)` hoặc `websocket(...)` có thể được dùng cho nhiều request đồng thời trên connection dùng chung. Không tạo một requester mới cho mỗi lần gọi service nếu cùng endpoint và cùng cấu hình connection.

Các điểm vận hành cần lưu ý:

- Tạo requester một lần ở application scope nếu endpoint và cấu hình không đổi.
- Dùng `dispose()` khi requester không còn được sử dụng; với bean Spring có thể khai báo `destroyMethod = "dispose"`.
- Theo dõi lỗi ở reactive chain vì lỗi DNS, connection refused, handshake, `SETUP`, timeout hoặc decode có thể xuất hiện khi publisher được subscribe.
- Thiết lập timeout và keepalive phù hợp ở tầng transport/connector; không mặc định một timeout cho mọi request.
- Nếu retry request, xem xét idempotency. Retry sau lỗi mạng có thể khiến ứng dụng không biết server đã xử lý request trước khi connection đứt hay chưa.
- Không coi connection được thiết lập thành công là bằng chứng mọi route đều tồn tại hoặc được cấp quyền.

Requester có thể thiết lập lại connection khi request tiếp theo cần dùng sau khi connection trước bị mất. Điều đó không có nghĩa request đang thất bại sẽ tự động được chạy lại an toàn. Chính sách retry và khôi phục trạng thái nghiệp vụ vẫn do ứng dụng quyết định.

## 10. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra hoặc sửa |
|---|---|---|
| Connection refused | Server chưa lắng nghe đúng host/port hoặc transport không khớp | Kiểm tra server RSocket, TCP port và cấu hình network. |
| WebSocket handshake thất bại | Sai scheme, host, port hoặc endpoint path | Kiểm tra URI ws/wss và path RSocket server expose. |
| Server không giải mã được DTO | Thiếu encoder/decoder hoặc data MIME type không thống nhất | Cấu hình RSocketStrategies ở cả hai đầu và kiểm tra dataMimeType. |
| Route không tìm thấy responder | Sai route hoặc server chưa đăng ký handler tương ứng | Đối chiếu requester.route(...) với route của responder. |
| Server không đọc được setup metadata | MIME type hoặc metadata extractor không tương thích | Dùng composite metadata khi cần nhiều entry và đăng ký decoder phía server. |
| setupRoute bị nhầm với request route | Hai route có vòng đời khác nhau | setupRoute thuộc SETUP frame; requester.route thuộc từng request. |
| Gọi block() làm nghẽn reactive thread | Chặn event loop hoặc thread xử lý reactive | Trả Mono/Flux hoặc chỉ block ở ranh giới imperative có kiểm soát. |
| Dùng requester sau khi đã dispose | Connection đã được đóng theo vòng đời ứng dụng | Quản lý requester theo application lifecycle và không giữ reference sau shutdown. |
| Retry gây xử lý lặp | Không biết request trước đã được server xử lý trước khi lỗi kết nối hay chưa | Dùng request id/idempotency key và thiết kế xử lý lặp an toàn. |
| Token metadata bị từ chối | Server chưa bật hoặc chưa cấu hình cơ chế xác thực metadata tương ứng | Kiểm tra RSocket Security, MIME type, metadata extractor và TLS. |

## 11. Checklist cấu hình kết nối

Trước khi đưa RSocket client vào production, hãy kiểm tra:

1. Dependency có spring-messaging, RSocket Java transport phù hợp và codec cần thiết.
2. Server đang expose TCP hoặc WebSocket đúng với transport client chọn.
3. Host, port, URI và endpoint path chính xác.
4. dataMimeType và metadataMimeType thống nhất với server.
5. RSocketStrategies có encoder/decoder cho mọi payload object được trao đổi.
6. setupData, setupRoute và setupMetadata chỉ được dùng khi server cần xử lý SETUP.
7. Request route trùng với route server responder đăng ký.
8. Connection được tái sử dụng và dispose theo vòng đời ứng dụng.
9. Timeout, keepalive, TLS, xác thực và retry được cấu hình theo yêu cầu hệ thống.
10. Integration test bao phủ kết nối thành công, route hợp lệ, sai MIME type, lỗi transport và đóng connection.

## Tài liệu tham khảo

- [Spring Framework Reference — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html): tổng quan giao thức, transport, `RSocketRequester`, client requester, SETUP, strategies và các kiểu request.
- [Spring Framework 6.1.21 Javadoc — RSocketRequester.Builder](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/messaging/rsocket/RSocketRequester.Builder.html): API `tcp`, `websocket`, `transport`, `dataMimeType`, `metadataMimeType`, `setupData`, `setupRoute`, `setupMetadata` và `rsocketStrategies`.
- [Spring Framework 6.1.21 Javadoc — RSocketRequester](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/messaging/rsocket/RSocketRequester.html): `builder()`, `route(...)`, `dispose()` và requester API.
- [Spring Framework 6.1 — RSocket](https://docs.spring.io/spring-framework/reference/6.1/rsocket.html): tài liệu theo nhánh 6.1 về client connection và cấu hình requester.
- [RSocket Protocol](https://rsocket.io/about/protocol/): các frame SETUP, request interactions, metadata và transport-independent behavior.
