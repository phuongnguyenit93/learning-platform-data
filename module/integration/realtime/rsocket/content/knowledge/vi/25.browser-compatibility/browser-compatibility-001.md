# Luồng kết nối RSocket từ ứng dụng trình duyệt qua WebSocket

## Mục tiêu bài học

Trình duyệt không cung cấp API TCP socket tùy ý cho JavaScript chạy trong trang web. Khi một ứng dụng web cần giao tiếp RSocket, nó thường dùng WebSocket làm transport. RSocket vẫn giữ nguyên các interaction type, metadata và backpressure; WebSocket chỉ cung cấp kênh hai chiều để mang các frame nhị phân.

Sau bài này, bạn có thể:

- Giải thích vì sao trình duyệt dùng WebSocket thay cho RSocket TCP.
- Mô tả luồng từ HTTP WebSocket Upgrade đến RSocket SETUP và request đầu tiên.
- Tạo client browser bằng `rsocket-js` và `rsocket-websocket-client`.
- Gửi route metadata và payload JSON tương thích với Spring.
- Cấu hình Spring Boot để cung cấp RSocket qua WebSocket.
- Phân biệt endpoint WebFlux tích hợp với WebSocket server độc lập.
- Xử lý WSS, Origin, xác thực, codec và lỗi kết nối.
- Quản lý stream, demand, cancellation và reconnect trong vòng đời trang web.

## Vì sao trình duyệt cần WebSocket?

Ứng dụng Java hoặc Node.js có thể mở TCP socket trực tiếp nếu môi trường cho phép. JavaScript chạy trong trang web bị giới hạn bởi sandbox của trình duyệt và không có API raw TCP socket tổng quát. Vì vậy, browser client cần một transport được trình duyệt hỗ trợ, phổ biến nhất là WebSocket.

RSocket là giao thức ứng dụng có thể chạy trên nhiều byte-stream transport. Khi dùng WebSocket:

- Trình duyệt tạo kết nối WebSocket tới một URL `ws://` hoặc `wss://`.
- WebSocket cung cấp kết nối hai chiều và truyền dữ liệu nhị phân.
- RSocket JS đóng gói request, response, stream, metadata và control frame vào dữ liệu WebSocket.
- Server giải mã frame RSocket và chuyển request tới responder hoặc handler Spring.

WebSocket không thay thế RSocket. Nó chỉ là transport. Các mô hình request-response, fire-and-forget, request-stream và request-channel vẫn do RSocket định nghĩa.

| Thành phần | Trách nhiệm |
|---|---|
| Browser WebSocket API | Tạo kết nối hai chiều qua HTTP Upgrade |
| `rsocket-websocket-client` | Chuyển dữ liệu WebSocket thành transport cho RSocket |
| `rsocket-core` | Quản lý SETUP, frame, stream và interaction |
| Spring RSocket | Nhận request, giải mã payload và định tuyến tới `@MessageMapping` |
| JSON/CBOR codec | Chuyển đổi object ứng dụng thành byte và ngược lại |

## Toàn bộ luồng kết nối

Một kết nối từ trang web tới Spring Boot thường trải qua các bước sau:

~~~mermaid
sequenceDiagram
    participant B as Browser application
    participant W as WebSocket endpoint
    participant R as RSocket responder
    participant H as Spring handler
    B->>W: WebSocket handshake (HTTP Upgrade)
    W-->>B: 101 Switching Protocols
    Note over B,W: WebSocket đã mở
    B->>R: RSocket SETUP (MIME types, keepAlive, lifetime)
    R->>R: Kiểm tra SETUP và khởi tạo session
    B->>R: REQUEST_RESPONSE + route metadata + JSON data
    R->>H: Decode payload và tìm @MessageMapping
    H-->>R: Mono<Response>
    R-->>B: PAYLOAD response
    Note over B,R: Các request và stream tiếp tục trên cùng kết nối
~~~

### Bước 1: ứng dụng chọn endpoint WebSocket

Client tạo URL chứa host, port và path đã được server cấu hình:

- `ws://localhost:8080/rsocket` cho môi trường local không TLS.
- `wss://api.example.com/rsocket` cho môi trường HTTPS có TLS.

Path là địa chỉ WebSocket endpoint. Nó không phải route RSocket. Ví dụ, `/rsocket` là mapping path ở tầng WebSocket; route `inventory.lookup` là metadata bên trong request RSocket.

### Bước 2: WebSocket handshake

Trình duyệt gửi HTTP request với các header Upgrade cần thiết, trong đó có `Origin`, `Sec-WebSocket-Key` và `Sec-WebSocket-Version`. Server hoặc reverse proxy chấp nhận handshake và trả về trạng thái `101 Switching Protocols`.

Sau đó kết nối chuyển sang WebSocket hai chiều. Với RSocket WebSocket transport, dữ liệu RSocket được gửi dưới dạng binary WebSocket messages. Ứng dụng không tự tạo HTTP request cho từng request-response hoặc từng payload stream.

WebSocket handshake thành công chỉ cho biết transport đã mở. RSocket session vẫn cần được khởi tạo bằng SETUP.

### Bước 3: RSocket SETUP

Client gửi frame SETUP để hai phía thống nhất các tham số kết nối. Các cấu hình quan trọng gồm:

- `dataMimeType`: định dạng dữ liệu ứng dụng, ví dụ `application/json`.
- `metadataMimeType`: định dạng metadata, thường là composite metadata.
- `keepAlive`: khoảng thời gian giữa các frame KEEPALIVE mà client gửi.
- `lifetime`: thời gian tối đa client chờ server phản hồi KEEPALIVE trước khi coi server không còn hoạt động.

Server có thể chấp nhận hoặc từ chối SETUP. Chỉ sau khi session được thiết lập, client mới bắt đầu gửi các interaction RSocket.

### Bước 4: gửi request có route và data

Một request tới Spring handler thường có:

- Data: object nghiệp vụ đã serialize, ví dụ JSON `{"sku":"SKU-42"}`.
- Metadata: route được encode theo routing metadata MIME type.
- Interaction: request-response, request-stream, fire-and-forget hoặc request-channel.

Spring giải mã Data, đọc route metadata và gọi method `@MessageMapping` tương ứng.

### Bước 5: giữ kết nối và xử lý vòng đời

Một WebSocket có thể mang nhiều stream RSocket đồng thời. Khi một request-response hoàn tất, kết nối WebSocket vẫn mở và các stream khác tiếp tục hoạt động. Ứng dụng nên tái sử dụng session thay vì mở một WebSocket mới cho mỗi thao tác.

## Cài đặt RSocket JS trong ứng dụng web

RSocket JS cung cấp `RSocketClient` và transport WebSocket. Với API 0.x được tài liệu hướng dẫn, có thể cài các package:

~~~bash
npm install rsocket-core rsocket-websocket-client
~~~

Tài liệu client hiện hành trên rsocket.io cho ví dụ API 0.x. Repository rsocket-js cũng có nhánh TypeScript viết lại API với các thay đổi đáng kể và các artifact 1.0 alpha được đánh dấu chưa ổn định. Vì vậy:

- Chọn một dòng API và khóa phiên bản các package tương thích trong lockfile.
- Không trộn package 0.x với package 1.0 alpha trong cùng client.
- Khi nâng cấp, đọc ví dụ của đúng phiên bản và kiểm tra thay đổi import, serializer, transport và reactive API.

Các ví dụ JavaScript trong bài này dùng API 0.x của `rsocket-core` và `rsocket-websocket-client`.

## Tạo RSocket client trong trình duyệt

Ví dụ sau dùng browser-native WebSocket, JSON cho Data và composite metadata cho route:

~~~javascript
import {
  RSocketClient,
  BufferEncoders,
  MESSAGE_RSOCKET_COMPOSITE_METADATA,
  MESSAGE_RSOCKET_ROUTING,
  encodeCompositeMetadata,
  encodeRoute,
} from "rsocket-core";

import RSocketWebsocketClient from "rsocket-websocket-client";

const jsonSerializer = {
  serialize(value) {
    return value == null
      ? null
      : new TextEncoder().encode(JSON.stringify(value));
  },
  deserialize(bytes) {
    return bytes == null
      ? null
      : JSON.parse(new TextDecoder().decode(bytes));
  },
};

const identitySerializer = {
  serialize(value) {
    return value;
  },
  deserialize(value) {
    return value;
  },
};

const client = new RSocketClient({
  serializers: {
    data: jsonSerializer,
    metadata: identitySerializer,
  },
  setup: {
    keepAlive: 60000,
    lifetime: 180000,
    dataMimeType: "application/json",
    metadataMimeType: MESSAGE_RSOCKET_COMPOSITE_METADATA.string,
  },
  transport: new RSocketWebsocketClient(
    {
      url: "wss://api.example.com/rsocket",
    },
    BufferEncoders
  ),
});

const rsocket = await client.connect();
~~~

Giải thích cấu hình:

- `RSocketClient` quản lý giao thức và session RSocket.
- `RSocketWebsocketClient` tạo transport WebSocket trong trình duyệt.
- Trình duyệt đã có sẵn WebSocket API nên không cần `wsCreator`. Tùy chọn `wsCreator` thường dùng trong Node.js để cung cấp implementation WebSocket như package `ws`.
- `BufferEncoders` cung cấp cách encode/decode buffer cho transport của API 0.x.
- `jsonSerializer` chuyển object thành UTF-8 JSON bytes và ngược lại.
- `identitySerializer` giữ nguyên composite metadata đã được encode thành buffer.
- `metadataMimeType` phải thống nhất với server. Composite metadata cho phép route và các entry metadata khác cùng tồn tại.
- `client.connect()` mở WebSocket và khởi tạo session RSocket.

Đoạn code giả định ứng dụng chạy trong browser bundle có hỗ trợ các package RSocket JS 0.x. Nếu dùng TypeScript, hãy dùng type definition tương ứng với đúng phiên bản đã khóa.

## Tạo route metadata và gọi request-response

Spring dùng route metadata để chọn handler. Trong RSocket JS 0.x, có thể encode route vào composite metadata:

~~~javascript
function routeMetadata(route) {
  return encodeCompositeMetadata([
    [MESSAGE_RSOCKET_ROUTING, encodeRoute(route)],
  ]);
}

function requestResponse(rsocket, route, data) {
  return new Promise((resolve, reject) => {
    rsocket.requestResponse({
      data,
      metadata: routeMetadata(route),
    }).subscribe({
      onComplete: resolve,
      onError: reject,
    });
  });
}

const result = await requestResponse(
  rsocket,
  "inventory.lookup",
  { sku: "SKU-42" }
);

console.log("Inventory response:", result);
~~~

Trong ví dụ:

- `encodeRoute("inventory.lookup")` tạo nội dung routing metadata.
- `encodeCompositeMetadata(...)` đóng gói entry route theo định dạng composite.
- `data` là object JavaScript được JSON serializer chuyển thành byte.
- `requestResponse()` trả về một `Single`; subscribe để nhận response hoặc lỗi.

Nếu server dùng Spring `@MessageMapping("inventory.lookup")`, route phải khớp chính xác. Route không phải URL path của WebSocket.

## Cấu hình Spring Boot để nhận browser client

Spring Boot có thể expose RSocket qua WebSocket theo hai cách: gắn endpoint vào WebFlux server hiện có hoặc chạy một WebSocket server RSocket độc lập.

### WebFlux tích hợp với HTTP server

Với ứng dụng WebFlux reactive và Reactor Netty, cấu hình mapping path:

Các dependency Maven cần có gồm `spring-boot-starter-rsocket` và `spring-boot-starter-webflux` (để ứng dụng chạy bằng WebFlux server):

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-rsocket</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
</dependency>
~~~

~~~yaml
server:
  port: 8080

spring:
  rsocket:
    server:
      transport: websocket
      mapping-path: /rsocket
~~~

Các điều kiện:

- Ứng dụng chạy theo kiểu WebFlux reactive.
- Có dependency `spring-boot-starter-rsocket` và `spring-boot-starter-webflux` phù hợp.
- `transport` là `websocket`.
- `mapping-path` chỉ định path WebSocket trong web server hiện có.
- Kiểu tích hợp này được Spring Boot hỗ trợ với Reactor Netty.

Khi đó browser kết nối tới:

~~~text
wss://api.example.com/rsocket
~~~

Nếu local không dùng TLS:

~~~text
ws://localhost:8080/rsocket
~~~

Cổng 8080 là cổng web server. Không cần khai báo một RSocket port độc lập cho kiểu mapping này.

### WebSocket server RSocket độc lập

Nếu muốn một listener riêng:

~~~yaml
spring:
  rsocket:
    server:
      transport: websocket
      port: 9898
~~~

Browser kết nối tới port riêng đó, ví dụ `wss://api.example.com:9898`. Cần cấu hình TLS cho listener, mở port trong firewall/container/network service và bảo đảm endpoint được expose qua proxy phù hợp.

Không nhầm hai chế độ: WebFlux mapping dùng `mapping-path` trên HTTP server; server độc lập dùng port riêng. Nếu cấu hình cả hai mà không hiểu cách auto-configuration lựa chọn, ứng dụng có thể mở endpoint ở nơi khác với URL client đang gọi.

## Viết handler Spring nhận request từ browser

Ví dụ handler request-response:

~~~java
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Mono;

record InventoryRequest(String sku) {}

record InventoryView(String sku, int available) {}

@Controller
class InventoryController {

    private final InventoryService inventoryService;

    InventoryController(InventoryService inventoryService) {
        this.inventoryService = inventoryService;
    }

    @MessageMapping("inventory.lookup")
    Mono<InventoryView> lookup(@Payload InventoryRequest request) {
        return inventoryService.find(request.sku());
    }
}
~~~

Spring nhận route metadata `inventory.lookup`, giải mã JSON Data thành `InventoryRequest`, sau đó gọi handler. Kết quả `Mono<InventoryView>` được encode thành response payload.

Với request-stream, handler có thể trả về `Flux`:

~~~java
record PriceWatch(String symbol) {}
record PriceTick(String symbol, long sequence, double price) {}

@MessageMapping("prices.watch")
Flux<PriceTick> watch(@Payload PriceWatch request) {
    return priceService.watch(request.symbol());
}
~~~

Browser gọi route `prices.watch` bằng `requestStream()` và nhận các `PriceTick` theo demand. Spring/Reactor chuyển tín hiệu backpressure và cancellation theo vòng đời stream.

Browser và server phải thống nhất:

| Thành phần | Browser | Spring |
|---|---|---|
| Route | `inventory.lookup` | `@MessageMapping("inventory.lookup")` |
| Data MIME type | `application/json` | JSON decoder/encoder |
| Metadata MIME type | Composite metadata | Composite metadata extractor |
| Data schema | `{ sku: string }` | `InventoryRequest` |
| Response schema | `{ sku, available }` | `InventoryView` |

Spring Boot tự cấu hình `RSocketStrategies` và các codec phổ biến khi dùng starter RSocket. Nếu ứng dụng thay đổi codec hoặc MIME type, cần kiểm tra hai phía vẫn tương thích. JSON object ở browser không tự động tương thích với DTO Java nếu tên field hoặc schema khác nhau.

## Gọi request-stream từ trình duyệt

Với request-stream, browser gửi một request ban đầu rồi nhận nhiều payload. Ví dụ theo dõi giá:

~~~javascript
const subscriptionRef = { current: null };

rsocket.requestStream({
  data: { symbol: "ACME" },
  metadata: routeMetadata("prices.watch"),
}).subscribe({
  onSubscribe(subscription) {
    subscriptionRef.current = subscription;
    subscription.request(8);
  },
  onNext(payload) {
    renderPrice(payload);
    subscriptionRef.current?.request(1);
  },
  onError(error) {
    showStreamError(error);
  },
  onComplete() {
    showStreamComplete();
  },
});
~~~

`request(8)` yêu cầu tối đa tám phần tử ban đầu. Mỗi khi xử lý một phần tử, client yêu cầu thêm một phần tử. Đây là demand ở tầng Reactive Streams, không phải số byte hay số WebSocket messages.

Khi giao diện không còn cần stream, hãy cancel subscription theo API của phiên bản đang dùng. Cancellation giúp server dừng công việc và giải phóng subscription hoặc tài nguyên nguồn nếu handler hỗ trợ cleanup.

Không yêu cầu số lượng phần tử cực lớn chỉ để tránh viết logic demand. Với stream dài hạn, hãy xử lý từng phần tử và duy trì demand theo khả năng thực tế của UI.

## Các interaction type browser có thể gọi

RSocket JS client có thể gọi các interaction tương tự client Java:

| API phía browser | Interaction | Khi dùng |
|---|---|---|
| `requestResponse(payload)` | Request-response | Gửi một yêu cầu và nhận một kết quả |
| `fireAndForget(payload)` | Fire-and-forget | Gửi thông điệp một chiều, không cần response nghiệp vụ |
| `requestStream(payload)` | Request-stream | Đăng ký nhận nhiều cập nhật từ server |
| `requestChannel(flowable)` | Request-channel | Gửi và nhận luồng dữ liệu hai chiều |

Với request-channel, browser cần cung cấp publisher/Flowable cho chiều request và subscriber cho chiều response. Hai phía đều quản lý demand. Không chuyển một mảng lớn thành một payload duy nhất nếu mục tiêu là gửi từng message theo luồng.

Fire-and-forget không cung cấp acknowledgement nghiệp vụ. Nếu giao diện cần biết server đã ghi nhận lệnh, hãy dùng request-response với receipt hoặc thiết kế trạng thái nghiệp vụ riêng.

## Xác thực khi kết nối từ trình duyệt

WebSocket API của trình duyệt không cho JavaScript tùy ý thêm các HTTP request header như `Authorization` vào constructor `new WebSocket(url)`. Tham số thứ hai của constructor dành cho subprotocol, không phải custom header.

Các lựa chọn thường gặp:

- **Cookie phiên:** trình duyệt tự gửi cookie theo domain, path, Secure và SameSite rules. Server phải xác thực cookie và kiểm tra Origin.
- **RSocket SETUP metadata:** phù hợp khi danh tính gắn với toàn bộ connection/session. Token được gửi trong SETUP metadata theo extension xác thực đã thống nhất.
- **Request metadata:** phù hợp khi mỗi request có token hoặc principal riêng. Cần dùng composite metadata và MIME type xác thực chuẩn.
- **Ticket ngắn hạn:** browser lấy một ticket dùng một lần hoặc thời hạn ngắn qua HTTPS, sau đó dùng cơ chế đã thiết kế để xác thực WebSocket/RSocket.

Không đưa access token dài hạn vào query string URL. URL có thể xuất hiện trong access log, proxy log, telemetry hoặc lịch sử công cụ. Không coi route hoặc Origin là bằng chứng xác thực.

Với cookie authentication, chú ý nguy cơ Cross-Site WebSocket Hijacking. Server/proxy cần allowlist Origin hợp lệ, xác thực phiên và áp dụng authorization cho từng route. Cấu hình CORS cho REST API không tự động chứng minh WebSocket endpoint đã kiểm tra Origin đúng cách.

## WSS, HTTPS và mixed content

Nếu trang web được tải bằng HTTPS, browser nên kết nối tới WSS. Một trang HTTPS kết nối tới WS không mã hóa thường bị chặn vì mixed content.

| Trang web | Endpoint realtime | Kết quả |
|---|---|---|
| HTTP local | `ws://localhost:8080/rsocket` | Phù hợp cho phát triển local |
| HTTPS production | `wss://api.example.com/rsocket` | Phù hợp cho production |
| HTTPS production | `ws://api.example.com/rsocket` | Thường bị browser chặn |
| HTTP production | `wss://api.example.com/rsocket` | Có thể kết nối, nhưng nên dùng HTTPS cho toàn trang |

WSS dùng TLS để mã hóa WebSocket handshake và dữ liệu sau khi Upgrade. Certificate phải hợp lệ với hostname, chain phải được browser tin cậy và endpoint cần được cấu hình TLS ở Spring Boot hoặc reverse proxy.

## Origin, CSP và chính sách trình duyệt

Browser gửi header `Origin` trong WebSocket handshake. Server hoặc reverse proxy nên kiểm tra Origin theo allowlist, ví dụ chỉ chấp nhận các domain frontend chính thức.

Cần lưu ý:

- Origin không phải danh tính người dùng; nó chỉ cho biết trang web khởi tạo kết nối.
- Không cho phép mọi Origin khi endpoint dùng cookie phiên hoặc có quyền truy cập dữ liệu.
- Cấu hình Content Security Policy với `connect-src` cho phép endpoint `wss://` dự kiến.
- Kiểm tra chính sách proxy, firewall và gateway có cho phép WebSocket Upgrade hay không.
- Không để một endpoint public chấp nhận mọi route chỉ vì transport đã mã hóa.

CSP là chính sách phía trình duyệt; nó không thay thế kiểm soát truy cập ở server.

## Backpressure, browser event loop và giao diện

RSocket JS dùng Reactive Streams semantics với demand-driven Flowable trong API 0.x. Tuy nhiên, browser UI có giới hạn riêng:

- Một callback xử lý payload quá lâu có thể chặn main thread và làm giao diện giật.
- Render DOM cho từng event tốc độ cao có thể tốn CPU.
- Nếu consumer chậm, cần điều tiết demand hoặc gom cập nhật theo batch.
- Nếu dữ liệu có thể bỏ qua, có thể coalesce trạng thái mới nhất thay vì render mọi mẫu.
- Nếu dữ liệu không được phép mất, cần thiết kế replay/cursor hoặc lưu bền vững ở server.

Không dùng buffer vô hạn ở browser. Giới hạn số phần tử đang chờ, giảm tần suất render và đưa xử lý nặng sang Web Worker khi phù hợp. Web Worker vẫn không tự tạo raw TCP; kết nối vẫn dùng WebSocket transport.

## Xử lý mất kết nối và vòng đời trang

WebSocket có thể đóng khi người dùng đổi mạng, laptop sleep, tab bị đóng, server restart hoặc proxy hết idle timeout. Ứng dụng nên quản lý trạng thái kết nối rõ ràng:

~~~mermaid
stateDiagram-v2
    [*] --> DISCONNECTED
    DISCONNECTED --> CONNECTING: open WebSocket
    CONNECTING --> CONNECTED: WebSocket + RSocket SETUP thành công
    CONNECTING --> DISCONNECTED: handshake/setup error
    CONNECTED --> DISCONNECTED: close/error/timeout
    DISCONNECTED --> CONNECTING: retry với backoff
    CONNECTED --> CLOSING: người dùng rời trang
    CLOSING --> [*]
~~~

Các nguyên tắc:

- Hiển thị trạng thái connecting, connected, reconnecting và offline cho người dùng khi cần.
- Retry với exponential backoff và jitter để nhiều browser không reconnect đồng loạt.
- Giới hạn số lần thử hoặc dùng circuit breaker khi server đang quá tải.
- Cancel stream và giải phóng listener khi component hoặc trang không còn dùng.
- Khi reconnect tạo session mới, khôi phục subscription theo route và cursor nghiệp vụ.
- Dùng idempotency key cho lệnh có tác dụng phụ vì client có thể không biết server đã xử lý trước khi kết nối mất hay chưa.

Không giả định session resumption luôn được bật hoặc luôn khả dụng trong mọi phiên bản RSocket JS và server. Hãy xác nhận implementation hỗ trợ, cấu hình và giữ được session state. Nếu resume thất bại, ứng dụng cần reconnect và khôi phục trạng thái ở tầng nghiệp vụ.

## Reverse proxy và triển khai production

Khi WSS đi qua reverse proxy hoặc load balancer, proxy phải hỗ trợ WebSocket Upgrade và giữ kết nối lâu dài.

Cần kiểm tra:

- Proxy chuyển tiếp đúng path, ví dụ `/rsocket`.
- HTTP Upgrade và các header WebSocket cần thiết được giữ nguyên.
- Idle timeout lớn hơn chu kỳ keepalive và phù hợp với thời gian kết nối dự kiến.
- Load balancer có giới hạn thời gian sống hoặc giới hạn kết nối phù hợp.
- Backend TLS hoặc mTLS nếu cần mã hóa đoạn proxy tới service.
- Origin allowlist được kiểm tra ở lớp thích hợp.
- Số lượng kết nối đồng thời, buffer và giới hạn request được giám sát.

Nếu TLS kết thúc ở proxy, WSS chỉ bảo vệ đoạn browser tới proxy. Đoạn proxy tới Spring Boot có thể là plaintext nếu không cấu hình TLS tiếp.

## Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| WebSocket handshake trả 404 | Sai mapping path hoặc proxy route | Kiểm tra URL và `mapping-path` |
| Handshake trả 400/426 | Upgrade headers hoặc WebSocket protocol không được proxy hỗ trợ | Kiểm tra cấu hình Upgrade và HTTP version |
| Browser báo mixed content | Trang HTTPS gọi endpoint WS | Chuyển sang WSS |
| WebSocket mở nhưng SETUP lỗi | MIME type, serializer hoặc protocol version không tương thích | Kiểm tra `dataMimeType`, `metadataMimeType` và package versions |
| No handler for destination | Route metadata sai hoặc không phải composite routing entry | Kiểm tra `encodeRoute` và `@MessageMapping` |
| Metadata malformed | Serializer xử lý lại composite metadata như JSON | Dùng identity serializer cho metadata đã encode |
| Payload deserialize lỗi | Data MIME type hoặc schema không khớp | Kiểm tra JSON codec và DTO |
| Kết nối bị đóng sau thời gian im lặng | Keepalive/idle timeout của proxy hoặc server | So sánh keepAlive với proxy idle timeout |
| Chỉ lỗi ở browser, Node chạy được | Browser policy, Origin, TLS hoặc custom header | Kiểm tra DevTools, certificate và authentication design |
| Stream tăng bộ nhớ | Không cancel, buffer vô hạn hoặc consumer không theo kịp | Kiểm tra subscription, demand và queue |

## Quy trình kiểm thử end-to-end

Một quy trình kiểm thử thực tế:

1. Khởi động Spring Boot với `transport: websocket` và mapping path rõ ràng.
2. Mở frontend từ origin được phép.
3. Kiểm tra DevTools Network, lọc theo WS và xác nhận handshake thành công.
4. Xác nhận browser gửi binary WebSocket messages sau Upgrade.
5. Tạo RSocket client và chờ `connect()` hoàn tất.
6. Gửi request-response có route metadata và JSON data.
7. Kiểm tra handler Spring được gọi và response deserialize đúng.
8. Mở request-stream, xác nhận demand và cancel hoạt động.
9. Kiểm tra authentication, Origin allowlist và WSS certificate.
10. Thử sai path, sai route, token hết hạn, server restart và mạng bị ngắt.
11. Kiểm tra reconnect có backoff và không tạo nhiều socket trùng.
12. Đóng trang hoặc component và xác nhận subscription được cleanup.

DevTools có thể xác nhận WebSocket handshake và frames, nhưng không thay thế integration test xác minh handler, serialization, authorization và vòng đời stream.

## Checklist trước khi đưa browser client vào production

1. Browser đang dùng WebSocket transport, không dùng TCP client?
2. URL endpoint, port và mapping path có khớp server không?
3. Trang HTTPS có kết nối qua WSS không?
4. Server có kiểm tra Origin theo allowlist không?
5. CSP `connect-src` cho phép endpoint cần thiết không?
6. Data MIME type và metadata MIME type có thống nhất hai phía không?
7. Route metadata có được encode thành composite metadata đúng chuẩn không?
8. Token/cookie được xác thực và authorization ở server được kiểm tra chưa?
9. Browser không phụ thuộc vào custom Authorization header mà WebSocket API không hỗ trợ?
10. Stream có demand, cancellation và buffer giới hạn không?
11. Reconnect có backoff, jitter và khôi phục trạng thái nghiệp vụ không?
12. Proxy hỗ trợ Upgrade và idle timeout phù hợp không?
13. Package rsocket-js đã khóa phiên bản tương thích và tránh trộn 0.x với alpha chưa?
14. Integration test đã chạy trong browser thật qua WSS chưa?

Luồng kết nối RSocket từ browser bắt đầu bằng WebSocket handshake, tiếp tục bằng RSocket SETUP, rồi mới trao đổi request và stream. Khi dùng `rsocket-websocket-client`, cấu hình MIME type và route metadata tương thích với Spring, bảo vệ endpoint bằng WSS và kiểm soát Origin, ứng dụng trình duyệt có thể dùng đầy đủ các interaction model RSocket qua một kết nối hai chiều.

## Tài liệu tham khảo

- [RSocket JS: WebSocket Client](https://rsocket.io/guides/rsocket-js/client/rsocket-websocket-client/)
- [RSocket JS: Client API](https://rsocket.io/guides/rsocket-js/client/)
- [RSocket JS: Package and API status](https://rsocket.io/guides/rsocket-js/)
- [RSocket Protocol Specification](https://rsocket.io/about/protocol/)
- [Spring Boot Reference: RSocket server auto-configuration](https://docs.spring.io/spring-boot/reference/messaging/rsocket.html)
- [Spring Framework Reference: RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [RSocket JS GitHub repository and releases](https://github.com/rsocket/rsocket-js)

