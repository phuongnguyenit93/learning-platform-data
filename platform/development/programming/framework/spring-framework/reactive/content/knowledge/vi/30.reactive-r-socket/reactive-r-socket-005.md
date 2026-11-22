# RSocket: Route, metadata và định dạng dữ liệu

**RSocket** là giao thức nhị phân cho trao đổi thông điệp hai chiều, bất đồng bộ và có hỗ trợ backpressure. Khác REST qua HTTP, RSocket không dùng một đường dẫn URL và HTTP method cho từng lời gọi nghiệp vụ. Client kết nối bằng TCP hoặc WebSocket, gửi frame SETUP để thống nhất các thông số của connection, rồi gửi nhiều request trên kết nối đó. Mỗi request có thể mang **data** (nội dung nghiệp vụ) và **metadata** (thông tin điều khiển như route, authentication, tracing).

Trong Spring, `RSocketRequester` tạo request; `RSocketMessageHandler` tìm handler theo route trong metadata và gọi method `@MessageMapping`. `RSocketStrategies` cùng encoder/decoder quyết định cách chuyển đổi giữa Java object và byte.

Các khái niệm cần phân biệt:

- **Route:** tên logic để chọn handler, ví dụ `orders.get.42` hay `orders.list`; thường nằm trong routing metadata, không phải URL HTTP.
- **Data:** nội dung nghiệp vụ của một request/response, có thể là JSON, CBOR, text hoặc binary.
- **Metadata:** thông tin bổ sung, chẳng hạn route, client tag, token, tenant, trace ID.
- **Data MIME type:** định dạng dữ liệu sử dụng trên connection, ví dụ `application/json`.
- **Metadata MIME type:** định dạng vùng metadata, thông thường là `message/x.rsocket.composite-metadata.v0`.
- **Transport:** TCP/WebSocket dùng vận chuyển frame. WebSocket transport path và business route là hai khái niệm độc lập.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích data và metadata trong payload RSocket.
2. Hiểu data MIME và metadata MIME của frame SETUP.
3. Tạo request với `route()`, `metadata()` và `data()`.
4. Ánh xạ route qua `@MessageMapping` và biến qua `@DestinationVariable`.
5. Phân biệt bốn interaction: Request-Response, Request-Stream, Fire-and-Forget, Request-Channel.
6. Dùng `@Header` để lấy metadata đã đăng ký extraction.
7. Tùy biến `RSocketStrategiesCustomizer` và `metadataExtractorRegistry`.
8. Hiểu vai trò `@ConnectMapping` và metadata push.
9. Chọn codec JSON/CBOR và tránh MIME mismatch.
10. Phân biệt RSocket TCP port, WebSocket mapping path và route.
11. Thiết kế metadata an toàn, version schema và giới hạn tài nguyên.
12. Viết và kiểm thử ứng dụng RSocket Spring Boot với Java 17.

## 2. Message Format: data và metadata

Một RSocket payload gồm hai vùng:

~~~text
RSocket Payload
+----------------------------------------+
| Metadata (optional)                    |
| - routing: orders.get.42               |
| - clientTag: web                        |
| - authentication/tracing...            |
+----------------------------------------+
| Data (optional)                        |
| - JSON / CBOR / plain text / binary    |
| - request hoặc response payload        |
+----------------------------------------+
~~~

Metadata được dùng để định tuyến và truyền thông tin điều khiển; data mang thông tin nghiệp vụ. Ví dụ lấy đơn hàng 42:

| Thành phần | Giá trị |
| --- | --- |
| Transport | TCP localhost:7000 |
| Route | `orders.get.42` |
| Metadata phụ | clientTag = web |
| Request data | Trống |
| Response data | `OrderView("42", "accepted", "web")` |
| Data MIME | application/json |
| Metadata MIME | composite metadata |

Có thể thiết kế route cố định `orders.get` rồi gửi ID trong data. Hai lựa chọn đều hợp lệ. Hãy thống nhất hợp đồng và tránh gửi hai bản ID khác nhau ở route và payload.

### 2.1. Metadata không phải HTTP header

Với TCP, RSocket không có tập HTTP headers ở mỗi request. Spring cung cấp `@Header` để lấy một giá trị metadata đã được extract thành message header. Đây không phải HTTP `@RequestHeader`.

Với RSocket over WebSocket, HTTP headers chỉ xuất hiện tại bước nâng cấp WebSocket; những RSocket interaction sau đó vẫn mang route và metadata trong frame RSocket, không nằm trong HTTP headers.

### 2.2. Metadata theo request và theo connection

Route thường xuất hiện trong frame khởi tạo interaction, ví dụ `REQUEST_RESPONSE`, `REQUEST_STREAM`, `REQUEST_CHANNEL` hoặc `REQUEST_FNF`. Các frame `REQUEST_N` sau đó gửi tín hiệu demand chứ không lặp route trên từng item.

Metadata push là cơ chế khác: `METADATA_PUSH` gửi thông tin metadata cấp kết nối mà không thuộc request cụ thể. Không nhầm metadata push với request-response.

## 3. SETUP frame, data MIME và metadata MIME

Khi RSocket connection được tạo, requester gửi `SETUP`. Trong frame này có hai MIME type:

- `dataMimeType`: cách encode/decode data payload của connection.
- `metadataMimeType`: cách serialize metadata của connection.

Ví dụ:

~~~java
RSocketRequester requester = builder
    .dataMimeType(
        MimeTypeUtils.parseMimeType("application/json")
    )
    .tcp("localhost", 7000);
~~~

Spring dùng JSON cho data theo cấu hình này. Metadata MIME có thể để mặc định của Spring, thông thường là composite metadata.

### 3.1. Không phải HTTP Content-Type/Accept

MIME type của RSocket được khai báo ở SETUP, không phải hai HTTP headers `Content-Type`/`Accept` cho từng route. Một connection đã chọn JSON không tự thương lượng CBOR cho mỗi request theo kiểu HTTP content negotiation.

Nếu hệ thống cần nhiều format, phải thiết kế cách chọn format theo connection hoặc một envelope có contract rõ ràng, và bảo đảm client/server có codec thích hợp.

### 3.2. Composite Metadata

MIME phổ biến:

~~~text
message/x.rsocket.composite-metadata.v0
~~~

Composite metadata cho phép nhiều metadata entry, mỗi entry có MIME riêng:

~~~text
SETUP:
  data MIME     = application/json
  metadata MIME = message/x.rsocket.composite-metadata.v0

REQUEST:
  metadata entry 1:
    MIME  = message/x.rsocket.routing.v0
    value = orders.get.42

  metadata entry 2:
    MIME  = text/plain
    value = web

  data:
    (empty)
~~~

Entry route có MIME `message/x.rsocket.routing.v0` theo routing extension. Entry khác dùng `text/plain` cho một client tag đơn giản. Hai entry này có thể tồn tại chung trong cùng một metadata region.

Nếu client không dùng composite metadata mà lại muốn gửi nhiều entry khác MIME, cần kiểm tra giao thức của peer và cấu hình metadata extractor phù hợp. Đừng chỉ thay tên MIME rồi giả định Spring tự hiểu.

### 3.3. MIME không phải codec

MIME type là hợp đồng định dạng; codec thực hiện chuyển đổi byte và object. Chọn `application/cbor` không tự thêm Jackson CBOR decoder. Spring Boot starter có auto-configuration cho các codec thường gặp, còn custom format cần đăng ký encoder/decoder chủ động.

## 4. Route trong Spring RSocket

Spring responder có thể khai báo:

~~~java
@Controller
class OrderController {

    @MessageMapping("orders.get")
    Mono<OrderView> get(OrderQuery query) {
        return orderService.find(query.id());
    }
}
~~~

Đoạn trên là ví dụ minh họa, giả định `orderService` tồn tại. Requester gọi:

~~~java
Mono<OrderView> result = requester
    .route("orders.get")
    .data(new OrderQuery("42"))
    .retrieveMono(OrderView.class);
~~~

Luồng nội bộ:

~~~text
RSocketRequester.route("orders.get")
              |
              v
Routing metadata entry
              |
              v
MetadataExtractor => "route"
              |
              v
RSocketMessageHandler
              |
              v
@MessageMapping("orders.get")
              |
              v
Decode data -> handler -> encode response
~~~

### 4.1. Route không phải HTTP URL

Với TCP, `orders.get` không tương ứng với URL nào. Với WebSocket transport, `/rsocket` là transport path dùng mở một WebSocket connection; route `orders.get` vẫn được gửi bên trong RSocket metadata.

Không dùng HTTP `@GetMapping` để nhận RSocket route thuần TCP. Dùng `@MessageMapping` với controller hoặc một responder implementation phù hợp.

### 4.2. Quy ước phân cấp

Ví dụ:

~~~text
catalog.products.get
catalog.products.search
orders.get
orders.list
orders.status.{id}
audit.log
text.upper
~~~

Route matcher mặc định của Spring RSocket dùng dấu chấm làm separator, không dùng quy tắc giải mã URL path của HTTP. Khi thiết kế phân cấp, đặt prefix theo domain và action để tránh trùng route giữa module.

### 4.3. @DestinationVariable

Responder:

~~~java
@MessageMapping("orders.status.{id}")
Mono<String> status(
        @DestinationVariable("id") String id) {

    return Mono.just("status:" + id);
}
~~~

Requester:

~~~java
Mono<String> result = requester
    .route("orders.status.{id}", "42")
    .retrieveMono(String.class);
~~~

`route(String, Object...)` cho phép truyền route template và các biến, còn `@DestinationVariable` lấy giá trị tại handler. Không tự ghép route bằng nối chuỗi với dữ liệu client chưa kiểm tra. Sau khi extract, vẫn phải validation ID và kiểm tra authorization.

### 4.4. Route versioning

Khi thay đổi không tương thích, có thể dùng `orders.v1.get` và `orders.v2.get`, hoặc version schema bên trong data. Không cần version route chỉ vì thêm một trường JSON tùy chọn tương thích ngược. Nên công bố schema, theo dõi mức dùng route cũ và có kế hoạch migration.

## 5. Bốn interaction RSocket

RSocket hỗ trợ bốn mô hình trao đổi chính:

| Interaction | Input | Output | API requester |
| --- | --- | --- | --- |
| Request-Response | 0 hoặc 1 | 1 | `retrieveMono(T.class)` |
| Fire-and-Forget | 0 hoặc 1 | 0 data | `send()` |
| Request-Stream | 0 hoặc 1 | Nhiều | `retrieveFlux(T.class)` |
| Request-Channel | Nhiều | 0, 1 hoặc nhiều | `data(Flux)` + phương thức lấy response phù hợp |

Ví dụ:

~~~java
// Request-Response
Mono<OrderView> one = requester.route("orders.get")
    .data(new OrderQuery("42"))
    .retrieveMono(OrderView.class);

// Fire-and-Forget
Mono<Void> sent = requester.route("audit.log")
    .data("order-42 opened")
    .send();

// Request-Stream
Flux<OrderView> many = requester.route("orders.list")
    .data(new ListQuery(3))
    .retrieveFlux(OrderView.class);

// Request-Channel
Flux<String> upper = requester.route("text.upper")
    .data(Flux.just("alpha", "beta"))
    .retrieveFlux(String.class);
~~~

Spring xác định interaction dựa trên cardinality của input và output trong annotated responder. Dữ liệu có một item có thể là concrete object hoặc Mono; nhiều item là Flux; không có response data thường thể hiện bằng void hoặc Mono<Void>.

### 5.1. Fire-and-Forget không có business ACK

`send()` hoàn tất nghĩa là thông điệp được gửi theo hợp đồng của requester. Nó **không** bảo đảm remote business handler đã commit dữ liệu. Nếu cần xác nhận xử lý, dùng Request-Response với receipt có trạng thái rõ ràng.

### 5.2. Backpressure

RSocket hỗ trợ demand trên stream bằng các frame như `REQUEST_N`. Với Request-Stream/Channel, responder cần tôn trọng demand, không sản xuất vô hạn vào buffer không giới hạn. Khi requester cancel, các nguồn dữ liệu/tài nguyên downstream cần được dừng và cleanup.

## 6. Gửi metadata phụ bằng RSocketRequester

Khi dùng composite metadata, requester thêm metadata tùy biến:

~~~java
Mono<OrderView> result = requester
    .route("orders.get.{id}", "42")
    .metadata("web", MimeTypeUtils.TEXT_PLAIN)
    .retrieveMono(OrderView.class);
~~~

`route()` thêm routing metadata. `metadata("web", TEXT_PLAIN)` thêm entry khác với MIME text/plain.

**Điểm cần nhớ:** Chỉ thêm metadata ở requester chưa khiến phía responder tự có `@Header("clientTag")`. Responder phải đăng ký extractor phù hợp.

### 6.1. MetadataExtractor

`MetadataExtractor` chuyển metadata bytes thành map giá trị có tên. `DefaultMetadataExtractor` đã hỗ trợ routing metadata và đặt dưới key `route`.

Với metadata khác, phải đăng ký MIME type, kiểu giá trị cần decode và tên header:

~~~java
strategies.metadataExtractorRegistry(registry ->
    registry.metadataToExtract(
        MimeTypeUtils.TEXT_PLAIN,
        String.class,
        "clientTag"
    )
);
~~~

Đoạn mã là callback trong `RSocketStrategies.Builder`. Cần decoder hỗ trợ String/text/plain. Khi đăng ký thành công, responder có thể nhận:

~~~java
@MessageMapping("orders.get.{id}")
Mono<OrderView> get(
        @DestinationVariable("id") String id,
        @Header("clientTag") String clientTag) {

    return Mono.just(
        new OrderView(id, "accepted", clientTag)
    );
}
~~~

`@Header` ở đây chỉ tới extracted RSocket metadata, không phải HTTP header.

### 6.2. @Headers Map

Spring cũng cho phép nhận một map metadata đã được extract:

~~~java
@Headers Map<String, Object> headers
~~~

Map chỉ chứa các mục extractor biết cách lấy. Nó không phải toàn bộ metadata bytes và không tự động chứa mọi entry lạ.

### 6.3. Metadata có DTO

Nếu metadata phức tạp, dùng MIME vendor, ví dụ:

~~~text
application/vnd.example.tenant+json
~~~

Bên server:

~~~java
MimeType tenantMime = MimeTypeUtils.parseMimeType(
    "application/vnd.example.tenant+json"
);

strategies.metadataExtractorRegistry(registry ->
    registry.metadataToExtract(
        tenantMime,
        TenantMetadata.class,
        "tenant"
    )
);
~~~

Đây là mẫu cấu hình minh họa: `TenantMetadata` là DTO ứng dụng; cần encoder/decoder hỗ trợ MIME vendor đã chọn. Chỉ gọi `metadataToExtract` không tự cài codec mới.

### 6.4. MIME cho metadata thông dụng

| Dữ liệu | MIME | Ghi chú |
| --- | --- | --- |
| Routing | `message/x.rsocket.routing.v0` | Extract mặc định thành route |
| Tag text | `text/plain` | Phải đăng ký extractor để đọc bằng @Header |
| Tenant object | `application/vnd.example.tenant+json` | Cần codec hỗ trợ MIME vendor |
| Bearer authentication | `message/x.rsocket.authentication.bearer.v0` | Theo extension authentication; cần security configuration |
| Tracing | MIME theo hệ thống | Không log secret hoặc dữ liệu nhạy cảm |

Metadata có thể xuất hiện trong log hoặc tracing. Không đặt token trong route hoặc ghi raw authentication metadata ra log.

## 7. Spring Boot RSocket auto-configuration

Dependency `spring-boot-starter-rsocket` cung cấp hạ tầng Spring Messaging RSocket và codec thường gặp. Spring Boot tự tạo `RSocketStrategies`, `RSocketMessageHandler` và requester builder nếu dependency và điều kiện auto-configuration phù hợp.

### 7.1. TCP transport

~~~properties
spring.rsocket.server.port=7000
spring.rsocket.server.transport=tcp
~~~

RSocket TCP server độc lập với HTTP server; `spring.rsocket.server.port` không phải `server.port`. Route nghiệp vụ không phải port hoặc TCP URL path.

### 7.2. WebSocket transport

Trong ứng dụng WebFlux muốn dùng RSocket trên WebSocket tích hợp vào Reactor Netty HTTP server:

~~~properties
spring.rsocket.server.transport=websocket
spring.rsocket.server.mapping-path=/rsocket
~~~

Trong chế độ gắn vào WebFlux server, không cấu hình `spring.rsocket.server.port` riêng. Client:

~~~java
RSocketRequester requester = builder.webSocket(
    URI.create("ws://localhost:8080/rsocket")
);
~~~

Path `/rsocket` chỉ mở transport connection. Sau khi kết nối, client vẫn gọi `route("orders.get")` hoặc `route("orders.list")` theo metadata, không theo URL path.

### 7.3. Spring Framework thuần

Nếu không dùng Spring Boot, có thể cấu hình `RSocketMessageHandler`:

~~~java
RSocketMessageHandler handler = new RSocketMessageHandler();
handler.setRSocketStrategies(strategies);
handler.routeMatcher(new PathPatternRouteMatcher());
~~~

Đây là snippet cấu hình, chưa phải ứng dụng chạy độc lập: phải cung cấp `strategies`, đăng ký annotated responder, tạo `RSocketServer` và bind `handler.responder()` vào TCP/WebSocket transport. Với Boot, tránh tự tạo handler trùng với auto-configured bean.

## 8. JSON, CBOR, String và định dạng dữ liệu

### 8.1. Data MIME và encoder/decoder

Cùng Java DTO có thể được mã hóa khác nhau:

~~~text
Java OrderView
      |
      +--> Jackson JSON Encoder --> JSON UTF-8 bytes
      |
      +--> Jackson CBOR Encoder --> CBOR binary bytes
~~~

Spring Boot RSocket starter cung cấp Jackson CBOR và JSON support. Với client/server khác công nghệ, hãy chỉ định rõ MIME type được thống nhất. Ví dụ:

~~~java
RSocketRequester requester = builder
    .dataMimeType(
        MimeTypeUtils.parseMimeType("application/json")
    )
    .tcp("localhost", 7000);
~~~

Muốn CBOR, dùng `application/cbor` và chắc chắn hai đầu có codec hỗ trợ. Không sửa mismatch codec bằng cách đổi route name.

### 8.2. Text/plain

Với dữ liệu text, có thể dùng:

~~~java
builder.dataMimeType(MimeTypeUtils.TEXT_PLAIN);
~~~

Decoder text/plain phù hợp với String; nó không tự chuyển chuỗi thành một Java record phức tạp. Nếu gửi object JSON qua data MIME text/plain, cần một encoder/decoder ứng dụng rõ ràng, không dựa vào trùng hợp.

### 8.3. MIME được đặt lúc SETUP

Không coi mỗi interaction như một HTTP request có thể đổi Content-Type bất kỳ. Chọn format theo kết nối hoặc một contract envelope riêng, đồng thời cấu hình codec phù hợp. Một client có thể tạo nhiều requester cho nhiều đích hoặc format.

### 8.4. Schema compatibility

Ví dụ JSON:

~~~json
{"id":"42","status":"accepted","clientTag":"web"}
~~~

Khi thêm field, kiểm tra client cũ xử lý unknown fields như thế nào. Với thay đổi không tương thích, dùng route/schema version; với thay đổi tương thích, có thể giữ route. Thêm validation cho dữ liệu thiếu, sai kiểu, kích thước quá lớn và dữ liệu không được phép.

### 8.5. Codec tùy biến

Để hỗ trợ format mới:

1. Xác định MIME chính thức.
2. Xây dựng encoder và decoder.
3. Đăng ký với `RSocketStrategies` hoặc `RSocketStrategiesCustomizer`.
4. Thống nhất data MIME trong SETUP.
5. Test payload đúng, sai schema và kích thước giới hạn.

`metadataExtractorRegistry` chỉ chọn cách extract **metadata**. Nó không tự giải mã data payload mới.

## 9. @ConnectMapping và metadata cấp connection

`@MessageMapping` xử lý interaction thông thường. `@ConnectMapping` xử lý frame SETUP và metadata push ở cấp kết nối.

Ví dụ minh họa:

~~~java
@Controller
class SetupController {

    @ConnectMapping("client.init")
    Mono<Void> connected(String clientName) {
        if (clientName == null || clientName.isBlank()) {
            return Mono.error(
                new IllegalArgumentException("Client name required")
            );
        }
        return Mono.empty();
    }
}
~~~

Requester:

~~~java
RSocketRequester requester = builder
    .setupRoute("client.init")
    .setupData("web-app")
    .tcp("localhost", 7000);
~~~

Nếu handler SETUP phát error, connection bị từ chối. `@ConnectMapping` không gửi response data: method trả `void` hoặc `Mono<Void>`.

Không chờ kết quả một outbound request trên chính connection ngay trong SETUP handler; connection chưa hoàn tất thiết lập để peer phục vụ request. Tách các interaction chủ động sau khi kết nối đã sẵn sàng.

### 9.1. Metadata push

`sendMetadata()` gửi `METADATA_PUSH`, thông báo metadata cấp kết nối. Đây không phải một route Request-Response, cũng không mang kết quả nghiệp vụ trả về như retrieveMono.

### 9.2. Setup authentication

Một số hệ thống kiểm tra authentication metadata khi SETUP để xác thực peer. Nhưng authorization trên từng route/resource vẫn cần thực hiện sau đó, đặc biệt khi client có thể truy cập nhiều tenant hoặc đối tượng với quyền khác nhau.

## 10. Bảo mật route, metadata và transport

Metadata không mặc nhiên đáng tin cậy. Client có thể giả clientTag, tenant, route variable và thậm chí cung cấp token không hợp lệ. Cần phân biệt:

- **Authentication:** chứng minh peer là ai (mTLS/TLS, setup hoặc request authentication).
- **Authorization:** xác định peer có quyền gọi route/resource cụ thể không.
- **Transport encryption:** TCP không mã hóa nếu chưa bật TLS; WebSocket không TLS dùng ws.
- **Validation:** route ID, DTO, metadata đều là input chưa tin cậy.
- **Observability:** log không chứa raw token hoặc thông tin nhạy cảm.

### 10.1. Authentication metadata

RSocket có extension bearer authentication, ví dụ MIME:

~~~text
message/x.rsocket.authentication.bearer.v0
~~~

Requester có thể gửi metadata entry loại này. Tuy nhiên, chỉ thêm `metadata(token, mimeType)` không tự xác thực token; server phải có Spring Security RSocket/interceptor phù hợp để xác minh signature, expiry, scope rồi kiểm tra quyền route.

Đừng đọc một chuỗi qua `@Header("token")` rồi coi đó là authenticated principal. Metadata extraction và xác thực là hai lớp riêng.

### 10.2. Route không phải bí mật

Không đưa password/token vào route:

~~~text
orders.get.42.token=secret
~~~

Route có thể xuất hiện trong log và metric. Nếu cần truyền credential, dùng authentication metadata được bảo vệ bằng TLS, kết hợp mask log và giới hạn quyền.

### 10.3. Tenant và authorization

Nếu route có `tenant.{tenantId}.orders.{orderId}`, responder phải đối chiếu tenantId với principal đã được xác thực. Không dựa vào route variable hoặc metadata client gửi để quyết định truy vấn dữ liệu của tenant khác.

## 11. Ví dụ Java 17 chạy được: RSocket route + metadata + JSON

Ví dụ dùng Java 17, Spring Boot **3.4.13** và TCP server. Các endpoint:

| Route | Interaction | Hợp đồng |
| --- | --- | --- |
| orders.get.{id} | Request-Response | Route ID + clientTag metadata -> OrderView |
| orders.list | Request-Stream | ListQuery -> Flux<OrderView> |
| audit.log | Fire-and-Forget | Một String, không trả data |
| text.upper | Request-Channel | Flux<String> -> Flux<String> |

### 11.1. Cấu trúc dự án

~~~text
rsocket-routing-demo/
├── build.gradle
└── src/
    ├── main/
    │   ├── java/demo/RsocketApplication.java
    │   ├── java/demo/OrderController.java
    │   ├── java/demo/OrderView.java
    │   ├── java/demo/ListQuery.java
    │   ├── java/demo/MetadataConfiguration.java
    │   └── resources/application.properties
    └── test/java/demo/RsocketIntegrationTest.java
~~~

### 11.2. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.4.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-rsocket'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Spring Boot quản lý các phiên bản Jackson, Reactor và RSocket. Starter cung cấp JSON/CBOR codecs để serialize Java records.

### 11.3. application.properties

~~~properties
spring.application.name=rsocket-routing-demo
spring.rsocket.server.port=7000
spring.rsocket.server.transport=tcp
spring.rsocket.server.address=127.0.0.1
~~~

Server bind loopback để thử cục bộ. Nếu truy cập từ máy khác, cần cấu hình network, firewall, TLS và authentication; không mở raw TCP service ra Internet khi chưa bảo vệ.

### 11.4. RsocketApplication.java

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RsocketApplication {

    public static void main(String[] args) {
        SpringApplication.run(RsocketApplication.class, args);
    }
}
~~~

### 11.5. OrderView.java

~~~java
package demo;

public record OrderView(
    String id,
    String status,
    String clientTag
) {}
~~~

### 11.6. ListQuery.java

~~~java
package demo;

public record ListQuery(int limit) {}
~~~

### 11.7. MetadataConfiguration.java

Đăng ký cách lấy custom metadata từ entry text/plain và đặt tên extracted header là clientTag:

~~~java
package demo;

import org.springframework.boot.rsocket.messaging.RSocketStrategiesCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.util.MimeTypeUtils;

@Configuration
public class MetadataConfiguration {

    @Bean
    RSocketStrategiesCustomizer clientTagMetadata() {
        return strategies ->
            strategies.metadataExtractorRegistry(registry ->
                registry.metadataToExtract(
                    MimeTypeUtils.TEXT_PLAIN,
                    String.class,
                    "clientTag"
                )
            );
    }
}
~~~

`metadataToExtract` đăng ký MIME, Java type và tên header. Client chỉ cần encoder String/text/plain để gửi metadata. Bên responder phải có decoder phù hợp.

### 11.8. OrderController.java

~~~java
package demo;

import java.util.Locale;

import org.springframework.messaging.handler.annotation.DestinationVariable;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.stereotype.Controller;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Controller
public class OrderController {

    @MessageMapping("orders.get.{id}")
    public Mono<OrderView> get(
            @DestinationVariable("id") String id,
            @Header("clientTag") String clientTag) {

        return Mono.just(new OrderView(
            id, "accepted", clientTag
        ));
    }

    @MessageMapping("orders.list")
    public Flux<OrderView> list(ListQuery query) {
        int count = Math.max(0, Math.min(query.limit(), 5));

        return Flux.range(1, count)
            .map(i -> new OrderView(
                "O-" + i, "queued", "server"
            ));
    }

    @MessageMapping("audit.log")
    public Mono<Void> audit(String message) {
        return Mono.fromRunnable(() ->
            System.out.println("audit: " + message)
        );
    }

    @MessageMapping("text.upper")
    public Flux<String> uppercase(Flux<String> messages) {
        return messages.map(text ->
            text.toUpperCase(Locale.ROOT)
        );
    }
}
~~~

Route `get` trả một OrderView; `list` trả nhiều item; `audit` không có response data; `uppercase` nhận và trả stream. Giới hạn tối đa 5 trong list là quy tắc demo để tránh request tùy ý phát quá nhiều kết quả.

### 11.9. RsocketIntegrationTest.java

Test mở một TCP server thật trên cổng ngẫu nhiên. `@LocalRSocketServerPort` cung cấp RSocket port thực tế, không phải HTTP port.

~~~java
package demo;

import java.time.Duration;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.rsocket.server.LocalRSocketServerPort;
import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.util.MimeTypeUtils;

import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(properties = "spring.rsocket.server.port=0")
class RsocketIntegrationTest {

    @LocalRSocketServerPort
    int port;

    @Autowired
    RSocketRequester.Builder builder;

    private RSocketRequester requester;

    @BeforeEach
    void connect() {
        requester = builder
            .dataMimeType(
                MimeTypeUtils.parseMimeType("application/json")
            )
            .tcp("127.0.0.1", port);
    }

    @AfterEach
    void dispose() {
        if (requester != null) {
            requester.rsocket().dispose();
        }
    }

    @Test
    void routeVariableAndTextMetadata() {
        StepVerifier.create(
            requester.route("orders.get.{id}", "42")
                .metadata("web", MimeTypeUtils.TEXT_PLAIN)
                .retrieveMono(OrderView.class)
        )
        .assertNext(value -> {
            assertEquals("42", value.id());
            assertEquals("accepted", value.status());
            assertEquals("web", value.clientTag());
        })
        .verifyComplete();
    }

    @Test
    void requestStreamUsesJsonData() {
        StepVerifier.create(
            requester.route("orders.list")
                .data(new ListQuery(3))
                .retrieveFlux(OrderView.class)
        )
        .expectNextMatches(v -> v.id().equals("O-1"))
        .expectNextMatches(v -> v.id().equals("O-2"))
        .expectNextMatches(v -> v.id().equals("O-3"))
        .verifyComplete();
    }

    @Test
    void channelStreamsBothDirections() {
        StepVerifier.create(
            requester.route("text.upper")
                .data(Flux.just("alpha", "beta"))
                .retrieveFlux(String.class)
        )
        .expectNext("ALPHA", "BETA")
        .verifyComplete();
    }

    @Test
    void fireAndForgetCompletesWithoutDataResponse() {
        StepVerifier.create(
            requester.route("audit.log")
                .data("order-42 opened")
                .send()
        )
        .verifyComplete();
    }

    @Test
    void unknownRouteEmitsError() {
        StepVerifier.create(
            requester.route("unknown.route")
                .retrieveMono(OrderView.class)
        )
        .expectError()
        .verify(Duration.ofSeconds(5));
    }
}
~~~

Test bao phủ route variable, metadata text/plain, JSON DTO trong Request-Stream, channel, fire-and-forget và lỗi route. Completion của send() không đồng nghĩa audit side effect đã được commit, nên test không assert điều đó.

### 11.10. Chạy thử

Chạy test:

~~~bash
./gradlew test
~~~

Trên Windows:

~~~powershell
.\gradlew.bat test
~~~

Chạy server:

~~~bash
./gradlew bootRun
~~~

Trên Windows:

~~~powershell
.\gradlew.bat bootRun
~~~

Ứng dụng chạy TCP port 7000 khi chạy bootRun, còn trong integration test port 0 để hệ điều hành chọn port rảnh. Client nên inject RSocketRequester.Builder do Boot cấu hình sẵn; nếu tự dùng `RSocketRequester.builder()` thì phải cấu hình codec JSON/CBOR tương thích trước khi gửi Java records.

## 12. Kiểm thử metadata, MIME và errors

### 12.1. Thiếu metadata bắt buộc

Nếu handler dùng `@Header("clientTag")` mà request không gửi entry tương ứng, việc resolve argument có thể lỗi. Với metadata bắt buộc, fail rõ ràng. Với metadata tùy chọn, đặt default hợp lý và ghi trong contract.

Không dùng clientTag tự khai như principal đã xác thực.

### 12.2. Data MIME mismatch

Nếu requester chọn text/plain nhưng cố gửi DTO phức tạp mà encoder không hỗ trợ, lỗi có thể xảy ra ngay tại client. Nếu phía server không có decoder cho MIME data đã khai báo, request sẽ lỗi ở codec layer. Không sửa bằng cách đổi route.

### 12.3. Metadata MIME mismatch

Nếu client dùng định dạng metadata không tương thích với route extractor, server có thể không tìm được route. Kiểm tra:
- Metadata MIME khai báo trong SETUP.
- Có composite metadata khi cần nhiều entry?
- Có routing entry theo MIME của routing extension?
- Đã đăng ký custom metadata MIME trong MetadataExtractor?
- Codec có decode đúng giá trị metadata không?

### 12.4. Unknown route

Khi route không có handler, requester thường nhận error ở tầng RSocket messaging. Đừng gọi nó là HTTP 404: TCP RSocket không truyền HTTP status cho interaction.

### 12.5. Test demand với StepVerifier

~~~java
StepVerifier.create(
    requester.route("orders.list")
        .data(new ListQuery(3))
        .retrieveFlux(OrderView.class),
    0
)
.thenRequest(1)
.expectNextCount(1)
.thenRequest(2)
.expectNextCount(2)
.verifyComplete();
~~~

Đây là test theo demand của requester. Để đánh giá memory thật, cần thêm load test với số kết nối/stream đồng thời, buffer bounds, thời gian chờ và cancellation.

### 12.6. Phân loại lỗi hữu ích

| Lỗi | Thường xảy ra ở đâu? |
| --- | --- |
| Không hỗ trợ codec | Encode/decode data hoặc metadata |
| Không match route | Metadata extraction/routing |
| Missing header | Resolve extracted metadata |
| Validation lỗi | Handler/business service |
| Authorization fail | Security/interceptor/handler |
| Timeout/cancel | Connection hoặc stream lifecycle |

Phân loại giúp khắc phục đúng tầng thay vì thử đổi MIME/route ngẫu nhiên.

## 13. Thiết kế route và metadata cho production

### 13.1. Bản hợp đồng nên ghi đủ

| Route | Interaction | Data MIME | Input | Metadata | Output |
| --- | --- | --- | --- | --- | --- |
| orders.get.{id} | Request-Response | JSON | Không | clientTag (demo) | OrderView |
| orders.list | Request-Stream | JSON | ListQuery | Không | Flux<OrderView> |
| audit.log | FNF | JSON | String | Auth trong production | Không có data |
| text.upper | Channel | JSON | Flux<String> | Không | Flux<String> |

Các route có phân quyền phải nêu rõ required scopes/roles và chủ thể cần kiểm tra. Trong production, không dùng clientTag text/plain cho authentication.

### 13.2. Giữ metadata nhỏ

Metadata dành cho route, trace, token và field điều khiển nhỏ. Không đặt file lớn hoặc toàn bộ business DTO trong metadata. Thiết kế limit cho frame/message, số request đồng thời và kích thước metadata.

### 13.3. Backpressure và cancellation

Request-Stream và Channel có thể sống lâu. Dùng Flux thay vì lưu mọi item vào list; không tự `subscribe()` trong controller; giới hạn prefetch/concurrency khi dùng flatMap; cleanup tài nguyên khi cancel/disconnect. Không có bảo đảm memory bounded chỉ vì giao thức hỗ trợ backpressure nếu ứng dụng tự tạo queue không giới hạn.

### 13.4. Versioning và migration

Khi đổi schema không tương thích:
1. Công bố contract mới.
2. Cho chạy song song route v1/v2 nếu cần.
3. Thêm tests cho client cũ và mới.
4. Theo dõi lượng traffic route cũ.
5. Ngừng route cũ theo mốc đã công bố.

### 13.5. Observability

Log route (không kèm token), interaction type, outcome, latency, message size, connection ID tương ứng, error type và trạng thái cancellation. Đối với token/metadata nhạy cảm, mask; không đưa dữ liệu cá nhân vào tag metric có cardinality vô hạn.

## 14. Lỗi thường gặp và cách sửa

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Nghĩ route là HTTP URL | Gọi sai path hoặc nhầm transport | Route nằm trong RSocket metadata |
| Gửi route như data | Handler không được tìm thấy | Dùng requester.route(...) |
| Quên composite metadata | Không gửi đồng thời route và metadata phụ đúng cách | Dùng metadata MIME tương thích |
| Nghĩ @Header đọc mọi entry tự động | Không nhận clientTag | Đăng ký metadataExtractorRegistry |
| Chỉ đăng ký metadataToExtract nhưng thiếu decoder | Không thể giải mã metadata | Cung cấp decoder cho MIME |
| Nhầm dataMimeType và metadataMimeType | Lỗi codec/routing | Phân biệt hai MIME types của SETUP |
| Dùng HTTP Accept/Content-Type cho TCP route | Sai mô hình | Chọn MIME trên RSocket connection |
| Tự tạo requester builder không có Jackson | DTO encode/decode thất bại | Dùng Boot-managed builder hoặc đăng ký strategies |
| Dùng @GetMapping cho RSocket | Handler không nhận được | Dùng @MessageMapping |
| Nối route với biến chứa dấu chấm | Sai separator/matching | Dùng route template và DestinationVariable |
| Nghĩ send() xác nhận business commit | Xác nhận sai trạng thái | Dùng Request-Response với receipt |
| @ConnectMapping trả object data | Sai contract SETUP | Trả void hoặc Mono<Void> |
| Chờ request trên connection khi đang SETUP | Có thể treo handshake | Tách outbound request sau khi connect |
| Dùng block trong handler | Có thể chặn event-loop | Trả Mono/Flux |
| Không kiểm tra route authorization | Truy cập vượt quyền | Kiểm tra principal và resource |
| Tin tenant/tag tự gửi | Giả mạo metadata | Xác thực và authorize độc lập |
| Dùng queue không giới hạn trên stream | Tăng memory khi client chậm | Giới hạn queue/buffer, tôn trọng demand |
| Không test mismatch MIME | Lỗi chỉ xuất hiện khi tích hợp | Test codec, route, metadata và error |

## 15. Checklist triển khai

1. **Route:** tên ổn định, phân namespace, không trùng?
2. **Matcher:** route variables và dấu chấm đã được test?
3. **Interaction:** Mono/Flux đúng Request-Response/FNF/Stream/Channel?
4. **SETUP:** data MIME và metadata MIME thống nhất?
5. **Composite:** nhiều metadata entries được biểu diễn đúng?
6. **Routing:** có MIME `message/x.rsocket.routing.v0` và extractor phù hợp?
7. **Custom metadata:** đã đăng ký MIME, decoder, header name?
8. **Codec:** JSON/CBOR/text client và server hỗ trợ cùng contract?
9. **Transport:** TCP port hoặc WebSocket mapping path đúng?
10. **Security:** peer được xác thực, route/resource được authorize?
11. **Limits:** kích thước frame, concurrency và buffer bounded?
12. **Backpressure:** request stream/channel tuân thủ demand?
13. **Schema:** có versioning và migration plan?
14. **Tests:** route variable, metadata @Header, MIME, request stream, channel, unknown route?
15. **Operations:** log/metric không để lộ token hoặc dữ liệu nhạy cảm?

**Ghi nhớ:** Route trong RSocket là metadata logic, không phải HTTP URL. `RSocketRequester.route()` tạo routing metadata; `@MessageMapping` và `RSocketMessageHandler` điều phối đến method. Data MIME và metadata MIME được khai báo ở SETUP, composite metadata cho phép mang routing cùng metadata phụ. Để sử dụng `@Header` với metadata mới, đăng ký metadata extractor/decoder trong `RSocketStrategies`. Chọn định dạng dữ liệu rõ ràng, test codec và routing end-to-end, và bảo vệ authorization ở cả cấp connection lẫn interaction.

## Tài liệu tham khảo

- Spring Framework — RSocket, RSocketRequester, Annotated Responders, MetadataExtractor: https://docs.spring.io/spring-framework/reference/rsocket.html
- Spring Boot 3.4 — RSocket Auto-configuration, TCP and WebSocket: https://docs.spring.io/spring-boot/3.4/reference/messaging/rsocket.html
- Spring Framework — RSocketRequester Java API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/rsocket/RSocketRequester.html
- Spring Framework — RSocketStrategies Java API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/rsocket/RSocketStrategies.html
- Spring Framework — MetadataExtractor API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/rsocket/MetadataExtractor.html
- Spring Boot — RSocket Properties: https://docs.spring.io/spring-boot/3.4/appendix/application-properties/index.html
- RSocket — Routing Metadata Extension: https://github.com/rsocket/rsocket/blob/master/Extensions/Routing.md
- RSocket — Composite Metadata Extension: https://github.com/rsocket/rsocket/blob/master/Extensions/CompositeMetadata.md
