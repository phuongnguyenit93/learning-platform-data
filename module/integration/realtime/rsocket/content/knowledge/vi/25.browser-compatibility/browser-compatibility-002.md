# Lựa chọn thư viện phía trình duyệt và kiểm tra phiên bản tương thích

JavaScript chạy trong trình duyệt có thể dùng RSocket để giao tiếp hai chiều với server, nhưng không thể mở raw TCP socket như một ứng dụng Node.js hoặc Java. Vì vậy, lựa chọn thực tế cho browser là thư viện RSocket JavaScript đi kèm WebSocket transport. Khi chọn thư viện, cần kiểm tra đồng thời API của phiên bản, khả năng đóng gói cho browser, transport server, MIME type và các giới hạn của WebSocket API.

Điểm quan trọng là không có một ma trận phiên bản trình duyệt chính thức, đầy đủ cho từng bản phát hành `rsocket-js`. Tài liệu dự án xác nhận thư viện dành cho browser và Node.js, còn khả năng chạy trên từng browser phụ thuộc vào WebSocket API, gói JavaScript được chọn, cú pháp JavaScript mà build tạo ra và cách ứng dụng xử lý vòng đời kết nối. Vì thế, cần xác định rõ browser tối thiểu của sản phẩm và kiểm thử trên chính các phiên bản đó.

## 1. Kiến trúc RSocket trong trình duyệt

Browser cung cấp WebSocket API, còn RSocket là giao thức ứng dụng chạy bên trên transport. Client JavaScript đóng gói RSocket frame thành binary WebSocket message; server giải mã frame rồi xử lý các interaction như request-response, fire-and-forget, request-stream hoặc request-channel.

```text
Browser
  Web application
       |
       v
  rsocket-core
       |
       v
  rsocket-websocket-client
       |
       v
  Native WebSocket API
       |
       |  WSS / binary WebSocket messages
       v
  Reverse proxy / Load balancer
       |
       v
  Spring Boot WebFlux + RSocket
       |
       v
  @MessageMapping handlers
```

Các thành phần có nhiệm vụ khác nhau:

- `rsocket-core`: quản lý setup, payload, stream ID, interaction model và protocol frame.
- `rsocket-websocket-client`: chuyển RSocket frame qua WebSocket transport; trong browser, thư viện dùng WebSocket API có sẵn.
- `WebSocket`: mở kết nối hai chiều qua HTTP Upgrade và chuyển binary message giữa browser và server.
- Spring RSocket: nhận WebSocket connection, giải mã RSocket frame và chuyển request tới handler.

Không nhầm WebSocket với RSocket. WebSocket chỉ cung cấp transport hai chiều; route, request-response, stream, channel, metadata và flow control là chức năng của RSocket.

## 2. Chọn transport đúng cho browser

RSocket JavaScript có nhiều transport, nhưng browser không có API raw TCP tùy ý. Do đó:

| Transport package | Môi trường phù hợp | Lựa chọn cho browser |
| --- | --- | --- |
| `rsocket-websocket-client` | Browser và Node.js với WebSocket implementation | Dùng cho web app |
| `rsocket-tcp-client` | Node.js hoặc môi trường có quyền mở TCP socket | Không dùng trong browser |
| Transport tùy chỉnh | Môi trường có API mạng riêng | Chỉ dùng khi đã triển khai và kiểm thử adapter tương thích |

Tài liệu `rsocket-js` ghi rõ `RSocketTCPClient` không được hỗ trợ trong browser và khuyến nghị `RSocketWebsocketClient` cho môi trường này. Không thể khắc phục giới hạn đó bằng cách đổi URL từ `ws://` sang `tcp://`; browser sandbox không cung cấp raw TCP API cho JavaScript trang web.

Nếu ứng dụng web cần kết nối tới server RSocket Java, hãy mở endpoint WebSocket ở server và cấu hình client dùng đúng URL, ví dụ `wss://api.example.com/rsocket`.

## 3. Chọn dòng phiên bản rsocket-js

`rsocket-js` có hai dòng API cần phân biệt:

| Dòng | Đặc điểm | Lưu ý tương thích |
| --- | --- | --- |
| `0.x.x` | API Flow cũ, hướng dẫn browser hiện có dùng `RSocketClient` và `RSocketWebsocketClient` | Các ví dụ 0.x chỉ áp dụng cho các package cùng dòng API tương thích |
| `1.0.0-alpha.x` | Bản viết lại bằng TypeScript, có thay đổi API đáng kể | Dự án đánh dấu artifact là unstable/preview và cảnh báo breaking changes |

Hướng dẫn client trên rsocket.io hiện vẫn ghi rõ áp dụng cho `0.x` và yêu cầu không dùng package `1.0.0-alpha` khi sao chép ví dụ. Bản viết lại TypeScript đã thay đổi API của các package hiện có, bổ sung các package như `rsocket-messaging`, `rsocket-composite-metadata`, `rsocket-adapter-rxjs` và loại bỏ `rsocket-flowable` khỏi nhánh mới.

Tại thời điểm biên soạn, npm hiển thị `0.0.29-alpha.0` là tag `latest` cho `rsocket-core` và `rsocket-websocket-client`, nhưng đây vẫn là bản pre-release và đã được phát hành từ năm 2024. Nhánh TypeScript mới cũng đang ở trạng thái alpha. Từ `latest` trên npm không đồng nghĩa với một bản stable được hỗ trợ dài hạn.

Các package trong monorepo được phát hành độc lập. Khi chọn phiên bản:

1. Chọn một dòng API (`0.x` hoặc `1.0-alpha`) trước.
2. Đọc ví dụ và changelog đúng dòng đó.
3. Kiểm tra phiên bản của `rsocket-core`, transport và các package metadata/adapter được sử dụng.
4. Pin phiên bản chính xác trong `package.json` và commit lockfile.
5. Không trộn `rsocket-core` 0.x với transport hoặc adapter 1.0-alpha chỉ vì tên package giống nhau.

Ví dụ cài đặt theo API 0.x mà hướng dẫn browser đang sử dụng:

```bash
npm install --save-exact \
  rsocket-core@0.0.29-alpha.0 \
  rsocket-websocket-client@0.0.29-alpha.0
```

Đây là ví dụ pin theo phiên bản được công bố, không phải khuyến nghị rằng bản alpha này phù hợp cho mọi ứng dụng production. Trước khi đưa vào sản phẩm, hãy đánh giá tình trạng bảo trì, issue đã biết, dependency tree, yêu cầu bảo mật và khả năng nâng cấp. Nếu chọn API TypeScript alpha, phải dùng đúng ví dụ và package set của nhánh đó thay vì sao chép code 0.x bên dưới.

## 4. Kiểm tra package có thể build cho browser

Không phải package JavaScript nào cũng được thiết kế cho browser. Một số package có thể tham chiếu Node built-in như `net`, `Buffer` hoặc module `ws`. Hãy kiểm tra entry point và dependency graph trước khi đưa vào bundle web.

Với browser client:

- Chỉ thêm `rsocket-core` và `rsocket-websocket-client` nếu đó là các package cần thiết.
- Không import `rsocket-tcp-client` vào bundle web.
- Không thêm `ws` chỉ để tạo WebSocket trong browser; browser đã có `WebSocket` global.
- Không polyfill Node TCP APIs để cố chạy transport TCP trong browser.
- Kiểm tra package build có ESM/CJS entry phù hợp với bundler và target browser.
- Kiểm tra bundle cuối không chứa shim Node không cần thiết hoặc package server-side.

Tài liệu WebSocket client của rsocket-js cho biết `wsCreator` được dùng ở môi trường non-browser để cung cấp một WebSocket implementation. Browser đã có WebSocket sẵn nên không cần tự truyền `wsCreator` trong cấu hình browser.

## 5. Tạo client WebSocket trong browser

Ví dụ dưới đây dùng API 0.x theo hướng dẫn chính thức. `RSocketWebsocketClient` nhận URL endpoint; browser tự cung cấp WebSocket implementation.

```javascript
import {
  RSocketClient,
  JsonSerializer,
  IdentitySerializer,
  APPLICATION_JSON,
  MESSAGE_RSOCKET_COMPOSITE_METADATA,
  MESSAGE_RSOCKET_ROUTING,
  encodeRoute,
  encodeCompositeMetadata,
} from "rsocket-core";
import RSocketWebsocketClient from "rsocket-websocket-client";

export function createBrowserRSocketClient(endpoint) {
  const client = new RSocketClient({
    serializers: {
      data: JsonSerializer,
      // Composite metadata đã là binary buffer được encode sẵn.
      metadata: IdentitySerializer,
    },
    setup: {
      keepAlive: 30_000,
      lifetime: 90_000,
      dataMimeType: APPLICATION_JSON.string,
      metadataMimeType: MESSAGE_RSOCKET_COMPOSITE_METADATA.string,
    },
    transport: new RSocketWebsocketClient({
      url: endpoint,
    }),
  });

  return client;
}
```

Khởi tạo kết nối từ một endpoint an toàn:

```javascript
const endpoint = new URL("/rsocket", window.location.href);
endpoint.protocol = endpoint.protocol === "https:" ? "wss:" : "ws:";

const client = createBrowserRSocketClient(endpoint.toString());
client.connect().subscribe({
  onComplete(rsocket) {
    console.log("RSocket setup completed");
    // Lưu rsocket trong service/provider để các component dùng chung.
  },
  onError(error) {
    console.error("RSocket connection failed", error);
  },
});
```

`connect()` của API 0.x trả về `Single<RSocket>` theo Flow API của thư viện. Ứng dụng subscribe vào `Single` để nhận RSocket sau khi setup hoàn tất và xử lý lỗi kết nối theo API Flow tương ứng. Không coi việc tạo object `RSocketClient` là kết nối đã mở; transport chỉ được mở khi gọi `connect()`.

Ví dụ dùng `JsonSerializer` cho data và `IdentitySerializer` cho metadata. Nếu ứng dụng truyền `String` hoặc binary trực tiếp, có thể dùng identity serializer cho data và khai báo `dataMimeType` tương ứng. Metadata cũng cần được encode theo đúng MIME type; nếu dùng routing metadata chuẩn của Spring, hãy dùng `encodeCompositeMetadata` cùng `encodeRoute` như ví dụ tiếp theo thay vì tự đặt route vào data JSON.

## 6. Gửi request tới Spring RSocket

Sau khi kết nối thành công, RSocket client có các interaction API như `requestResponse`, `fireAndForget`, `requestStream` và `requestChannel`. Trong API 0.x, `requestResponse` trả về `Single`, còn `requestStream` trả về `Flowable`; subscriber cần đăng ký và yêu cầu demand để nhận phần tử.

Ví dụ tạo routing metadata theo API 0.x của `rsocket-core`:

```javascript
const routeMetadata = encodeCompositeMetadata([
  [MESSAGE_RSOCKET_ROUTING, encodeRoute("orders.find")],
]);

const payload = {
  data: { orderId: "ORD-2026-018" },
  metadata: routeMetadata,
};

rsocket.requestResponse(payload).subscribe({
  onComplete(response) {
    renderOrder(response.data);
  },
  onError(error) {
    showRequestError(error);
  },
});
```

`encodeRoute` tạo entry routing theo extension `message/x.rsocket.routing.v0`; `encodeCompositeMetadata` đóng gói entry thành composite metadata binary. `IdentitySerializer` giữ nguyên buffer đã encode. Không gửi chuỗi route thuần vào `metadata` khi server đang chờ composite metadata binary.

Với request-stream, client cần quản lý demand:

```javascript
const stream = rsocket.requestStream({
  data: { deviceId: "sensor-014" },
  metadata: encodeCompositeMetadata([
    [MESSAGE_RSOCKET_ROUTING, encodeRoute("sensors.live")],
  ]),
});

let subscription;
stream.subscribe({
  onSubscribe(currentSubscription) {
    subscription = currentSubscription;
    subscription.request(16);
  },
  onNext(reading) {
    renderReading(reading);
    // Yêu cầu thêm khi UI đã xử lý đủ số phần tử.
    subscription.request(1);
  },
  onError(error) {
    showConnectionError(error);
  },
  onComplete() {
    markStreamComplete();
  },
});
```

Đây là ví dụ theo subscriber contract của `Flowable` 0.x. Trong code thật, giữ reference subscription ở đúng scope để tránh yêu cầu demand sau khi đã cancel hoặc stream kết thúc.

## 7. Cấu hình Spring Boot mở endpoint WebSocket

Spring Boot hỗ trợ expose RSocket qua WebSocket từ ứng dụng WebFlux. Ví dụ cấu hình:

```yaml
spring:
  rsocket:
    server:
      transport: websocket
      mapping-path: /rsocket
```

Khi đó browser có thể kết nối tới `wss://api.example.com/rsocket` sau khi ứng dụng được triển khai sau TLS termination phù hợp.

Điều kiện quan trọng: việc gắn RSocket WebSocket transport vào web server được Spring Boot hỗ trợ cho ứng dụng reactive WebFlux và Reactor Netty. Nếu chạy RSocket server độc lập, cấu hình `spring.rsocket.server.port` để mở server embedded riêng và thiết lập endpoint WebSocket theo transport đó.

Ví dụ handler phía server:

```java
@Controller
public class BrowserController {

    @MessageMapping("orders.find")
    public Mono<OrderView> find(FindOrder command) {
        return orderService.find(command.orderId());
    }

    @MessageMapping("sensors.live")
    public Flux<SensorReading> live(SensorQuery query) {
        return sensorService.stream(query.deviceId());
    }
}
```

Client và server phải thống nhất route, data MIME type, metadata MIME type, cấu trúc payload và protocol version. WebSocket handshake thành công chỉ chứng minh transport đã được nâng cấp; RSocket `SETUP` vẫn phải được gửi và chấp nhận trước khi interaction hoạt động.

## 8. Browser compatibility: API nào cần có?

RSocket JS browser client dựa vào WebSocket API và các primitive JavaScript để xử lý binary data. WebSocket API được MDN đánh dấu Baseline/Widely available và có mặt trên các browser phổ biến trong nhiều năm. `WebSocket.binaryType` cho phép nhận binary message dưới dạng `ArrayBuffer` thay vì `Blob` và cũng được hỗ trợ rộng rãi.

Tuy nhiên, tài liệu rsocket-js không cung cấp bảng phiên bản tối thiểu cho Chrome, Edge, Firefox, Safari hoặc browser mobile. Vì vậy bảng dưới đây là ma trận kiểm thử đề xuất cho ứng dụng, không phải cam kết hỗ trợ chính thức của thư viện:

| Browser / runtime | Kiểm tra chính | Lưu ý |
| --- | --- | --- |
| Chrome desktop | WebSocket binary, TLS, reconnect, request-stream | Kiểm tra browser hiện hành và phiên bản thấp nhất sản phẩm hỗ trợ |
| Edge desktop | Handshake, binary frame, proxy và enterprise policy | Kiểm tra môi trường proxy/VPN doanh nghiệp |
| Firefox desktop | WebSocket lifecycle, binary payload, stream cancel | Kiểm tra xử lý khi tab ngủ hoặc mạng đổi |
| Safari macOS | WSS, binary message, reconnect, page lifecycle | Kiểm tra idle timeout và sleep/wake |
| Safari trên iOS/iPadOS | Background/foreground, chuyển Wi-Fi/mobile, reconnect | Mobile browser có thể suspend tab và timer |
| Chrome Android | WSS, mạng di động, tab background, reconnect | Kiểm tra thiết bị thật với mạng yếu |
| Firefox Android / Samsung Internet | WebSocket và bundle compatibility | Chạy smoke test trên browser nằm trong support policy |
| WebView / browser nhúng | WebSocket API, TLS trust, proxy và cookie policy | Phải kiểm thử theo phiên bản WebView do ứng dụng phân phối |

Hãy ghi rõ phiên bản tối thiểu được sản phẩm hỗ trợ trong tài liệu phát hành. Không suy ra browser minimum chỉ từ việc `WebSocket` được hỗ trợ; bundler target, syntax JavaScript, dependency và tính năng browser khác cũng có thể nâng mức tối thiểu.

Trong source của `rsocket-core` 0.x có cảnh báo riêng rằng Internet Explorer và Microsoft Edge đời cũ có thể không ổn định với WebSocket nếu `keepAlive` lớn hơn 30 giây. Ví dụ ở trên dùng 30 giây. Nếu sản phẩm còn hỗ trợ các browser legacy này, hãy kiểm tra cảnh báo theo đúng bản package và đo lại timeout của proxy/server; không áp dụng cảnh báo Edge Legacy cho mọi phiên bản Edge Chromium hiện nay.

## 9. Kiểm tra binary WebSocket và WebSocket API

Browser nhận binary WebSocket message dưới dạng `Blob` mặc định hoặc `ArrayBuffer` khi `binaryType` được đặt tương ứng. RSocket transport phải xử lý đúng binary frame. Không được chuyển frame thành text UTF-8 tùy tiện vì RSocket là giao thức binary.

Có thể kiểm tra khả năng cơ bản trước khi tạo client:

```javascript
export function hasBrowserWebSocketSupport() {
  return typeof window !== "undefined" &&
    typeof window.WebSocket === "function" &&
    typeof window.ArrayBuffer === "function";
}
```

Nếu cần kiểm tra handshake ở môi trường test, có thể tạo một WebSocket thuần:

```javascript
const socket = new WebSocket("wss://api.example.com/rsocket");
socket.binaryType = "arraybuffer";

socket.addEventListener("open", () => {
  console.log("WebSocket handshake succeeded");
  socket.close();
});

socket.addEventListener("error", () => {
  console.error("WebSocket handshake failed");
});
```

Đoạn kiểm tra này chỉ xác nhận WebSocket handshake. Nó không gửi RSocket `SETUP`, không kiểm tra MIME type, route hay interaction. Muốn kiểm tra end-to-end phải dùng `RSocketClient` và chờ kết nối RSocket được thiết lập.

## 10. HTTPS, WSS và Content Security Policy

Nếu trang web được tải bằng HTTPS, hãy dùng `wss://` cho WebSocket. Kết nối `ws://` từ trang bảo mật có thể bị browser chặn như mixed content.

Nếu ứng dụng có Content Security Policy, directive `connect-src` phải cho phép endpoint WebSocket:

```http
Content-Security-Policy: default-src 'self'; connect-src 'self' wss://api.example.com
```

Đừng chỉ kiểm tra local development qua `ws://localhost`. Môi trường staging và production cần chứng thư TLS hợp lệ, hostname khớp, proxy cho phép HTTP Upgrade và route WebSocket được chuyển tiếp tới đúng server.

Reverse proxy/load balancer cần:

- Hỗ trợ WebSocket Upgrade và giữ kết nối hai chiều.
- Chuyển tiếp binary message mà không biến đổi nội dung.
- Có idle timeout tương thích với RSocket keepalive.
- Không buffer toàn bộ response stream theo cách làm tăng độ trễ.
- Có giới hạn frame/message phù hợp với payload lớn.
- Cho phép cấu hình giới hạn số kết nối và thời gian sống kết nối.

## 11. CORS, Origin và xác thực browser

WebSocket handshake không sử dụng cơ chế CORS/preflight giống `fetch` thông thường. Browser gửi header `Origin` trong handshake; server cần kiểm tra origin theo allowlist rõ ràng. Không coi `Access-Control-Allow-Origin` là biện pháp thay thế cho kiểm tra Origin trên WebSocket handshake.

`Origin` giúp bảo vệ khỏi Cross-Site WebSocket Hijacking khi browser tự gửi cookie phiên, nhưng không phải authentication. Client không phải browser có thể giả mạo Origin. Server vẫn phải xác thực credential và phân quyền request.

Browser `WebSocket` constructor không cho phép ứng dụng tùy ý thêm HTTP header như `Authorization` vào handshake. Vì vậy với RSocket browser client, thường dùng:

- Cookie phiên được browser gửi tự động, kèm SameSite phù hợp và kiểm tra Origin nghiêm ngặt.
- Authentication metadata trong RSocket `SETUP` để xác thực danh tính gắn với kết nối.
- Authentication metadata trong request để xác thực từng interaction khi kết nối được chia sẻ.
- Vé kết nối ngắn hạn, dùng một lần nếu cần kiểm soát trước khi chấp nhận WebSocket handshake.

Lưu ý thứ tự: RSocket `SETUP` chỉ được gửi sau khi WebSocket handshake thành công. Nếu server cần xác thực trước khi nâng cấp WebSocket, phải dùng cơ chế ở tầng handshake (ví dụ cookie hoặc ticket) và vẫn xác thực RSocket theo chính sách ứng dụng. Không đặt access token dài hạn trong query string vì URL có thể xuất hiện trong log, proxy hoặc công cụ giám sát.

## 12. Backpressure và giới hạn của WebSocket trong browser

RSocket hỗ trợ flow control bằng `REQUEST_N`, vì vậy request-stream và request-channel có thể điều tiết số payload logic mà subscriber muốn nhận. Tuy nhiên, WebSocket API tiêu chuẩn của browser không cung cấp backpressure cho message event. Nếu server gửi nhanh hơn khả năng xử lý JavaScript, browser có thể tích lũy message trong bộ nhớ hoặc làm event loop quá tải.

Do đó, cần áp dụng cả hai lớp:

1. **RSocket demand:** chỉ yêu cầu số payload mà ứng dụng có thể xử lý; tiếp tục gọi `request(n)` sau khi tiêu thụ.
2. **Application queue:** giới hạn queue trong UI/store/worker; khi đầy, tạm dừng demand, drop dữ liệu có thể bỏ hoặc hủy stream theo chính sách.

Ví dụ dashboard chỉ cần giá trị mới nhất có thể gộp các update chưa render thành một giá trị cuối thay vì lưu vô hạn mọi mẫu. Ngược lại, ứng dụng giao dịch không được tự ý drop sự kiện; cần buffer có giới hạn và lưu bền ở server nếu client mất kết nối.

RSocket flow control không làm WebSocket browser API tự có backpressure. Đây là hai tầng khác nhau và cần kiểm thử riêng.

## 13. Keepalive, reconnect và vòng đời trang

Browser có thể chuyển tab sang background, suspend JavaScript timer, chuyển mạng hoặc đóng kết nối khi thiết bị ngủ. Server/proxy cũng có thể đóng kết nối idle. Ứng dụng cần quản lý vòng đời RSocket theo trang và theo phiên người dùng.

Các nguyên tắc:

- Chọn `keepAlive` và `lifetime` phù hợp với timeout của proxy/load balancer.
- Không dùng timer phía browser làm nguồn thời gian chính xác khi tab có thể bị throttle.
- Xử lý `close`, `error` và lỗi terminal của RSocket; tránh tạo reconnect loop không giới hạn.
- Dùng exponential backoff có jitter và giới hạn số lần thử liên tiếp.
- Khi reconnect, tạo connection mới và thực hiện SETUP/authentication lại; không giả định các stream cũ tự tiếp tục.
- Nếu cần phục hồi vị trí dữ liệu, dùng sequence/cursor hoặc durable subscription ở cấp ứng dụng.
- Đóng connection khi người dùng logout hoặc khi trang kết thúc phiên làm việc; cân nhắc `pagehide` và lifecycle của SPA.

Không tạo một RSocket connection mới mỗi lần component UI render. Quản lý một connection ở tầng service/provider phù hợp, chia sẻ nó cho các component và đóng đúng lúc.

## 14. Kiểm tra tương thích giữa client và server

Hai phía phải tương thích ở nhiều lớp hơn là chỉ cùng transport:

| Lớp | Cần khớp |
| --- | --- |
| RSocket protocol | Phiên bản protocol và các extension được sử dụng |
| Transport | Browser WebSocket client và server WebSocket endpoint |
| Data MIME type | JSON, CBOR, Protobuf hoặc binary theo hợp đồng |
| Metadata MIME type | Composite metadata, routing metadata và custom metadata |
| Route | Tên route phía client và `@MessageMapping` phía Spring |
| Interaction | Request-response, FNF, stream hoặc channel được cả hai phía hỗ trợ |
| Flow control | Cách yêu cầu demand, cancel và xử lý slow consumer |
| Security | Authentication metadata, TLS, Origin policy và authorization |
| Payload size | Giới hạn frame/payload của client, server và proxy |

Bảng implementations công khai của RSocket (trang được cập nhật ngày 13-10-2024) phân biệt core protocol support, resumption, leasing và RPC. Không giả định mọi implementation hoặc mọi release đều hỗ trợ tất cả extension. Nếu ứng dụng phụ thuộc leasing, resumption hoặc một extension cụ thể, hãy xác nhận trong implementation matrix và chạy interoperability test với đúng version đã pin.

Implementation matrix hiện đánh dấu RSocket JS hỗ trợ core protocol và resumption, nhưng không đánh dấu leasing. Nếu thiết kế phụ thuộc LEASE để điều tiết số request, hãy xác minh lại matrix và source của đúng release; không suy ra hỗ trợ chỉ từ việc một implementation hỗ trợ các interaction model cơ bản.

## 15. Ma trận kiểm thử browser thực tế

Tạo một ma trận test dựa trên support policy của sản phẩm. Tối thiểu nên có:

| Nhóm test | Chrome/Edge | Firefox | Safari/iOS | Android/WebView |
| --- | --- | --- | --- | --- |
| WebSocket handshake qua WSS | ✓ | ✓ | ✓ | ✓ |
| RSocket SETUP và request-response | ✓ | ✓ | ✓ | ✓ |
| Binary payload lớn/fragmentation | ✓ | ✓ | ✓ | ✓ |
| Request-stream và demand | ✓ | ✓ | ✓ | ✓ |
| Request-channel nếu sử dụng | ✓ | ✓ | ✓ | ✓ |
| Authentication metadata | ✓ | ✓ | ✓ | ✓ |
| Reconnect sau offline/online | ✓ | ✓ | ✓ | ✓ |
| Tab background/foreground | ✓ | ✓ | ✓ | ✓ |
| Proxy/idle timeout | ✓ | ✓ | ✓ | ✓ |
| CSP và Origin allowlist | ✓ | ✓ | ✓ | ✓ |

Một quy trình kiểm thử hiệu quả:

1. Xây dựng production bundle bằng đúng bundler và target browser.
2. Mở trang trên từng browser/device được hỗ trợ.
3. Xác nhận handshake WSS tới đúng path.
4. Xác nhận RSocket SETUP thành công và kiểm tra data/metadata MIME type.
5. Gọi request-response để xác minh route và codec.
6. Mở request-stream, kiểm soát demand và hủy subscription.
7. Gửi payload lớn để kiểm tra fragmentation và giới hạn message.
8. Mô phỏng mất mạng, đổi Wi-Fi sang mobile data, sleep/wake và reconnect.
9. Kiểm tra token hết hạn, logout, origin không hợp lệ và CSP từ chối.
10. Quan sát memory, queue depth, số connection và tốc độ phát/nhận dưới tải.

Không chỉ chạy test trong Chrome desktop rồi kết luận tương thích mọi browser. Safari trên iOS, WebView và browser doanh nghiệp có thể có chính sách mạng, lifecycle hoặc proxy khác biệt.

## 16. Chẩn đoán lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| `WebSocket is not supported` hoặc lỗi module `net` | Bundle đã import TCP transport hoặc dependency Node-only | Loại `rsocket-tcp-client`, kiểm tra dependency graph |
| Handshake 404 | Sai `mapping-path` hoặc reverse proxy path | So khớp URL client với Spring Boot mapping path |
| Handshake 400/403 | Origin policy, cookie hoặc proxy từ chối | Kiểm tra request Upgrade và allowlist Origin |
| Trang HTTPS không kết nối được | Client dùng `ws://` gây mixed content | Dùng `wss://` và chứng thư TLS hợp lệ |
| WebSocket mở nhưng RSocket setup lỗi | MIME type, protocol version, setup metadata hoặc server transport sai | Kiểm tra SETUP frame và server log |
| Route không tìm thấy | Metadata route chưa encode đúng composite format | Kiểm tra metadata MIME type và route encoder |
| JSON decode lỗi | Serializer hoặc data MIME type hai phía không khớp | Kiểm tra `JsonSerializer`, codec và payload thực tế |
| Kết nối bị đóng khi tab nền | Browser suspend hoặc proxy idle timeout | Điều chỉnh keepalive và reconnect policy |
| UI lag hoặc tăng memory | Stream nhận nhanh hơn tốc độ xử lý; WebSocket API không có backpressure | Giảm demand, giới hạn queue và cancel khi không cần |
| API import không tồn tại | Trộn ví dụ 0.x và package 1.0-alpha | Kiểm tra lockfile, package version và docs cùng dòng |

## 17. Checklist chọn thư viện và phát hành

- [ ] Xác định browser tối thiểu và thiết bị thực tế nằm trong support policy.
- [ ] Chọn `rsocket-websocket-client` cho browser; không dùng TCP client.
- [ ] Chọn một dòng API `rsocket-js` và đọc đúng tài liệu của dòng đó.
- [ ] Pin version chính xác cho `rsocket-core`, WebSocket transport và metadata/adapter packages.
- [ ] Không trộn API 0.x Flow với API TypeScript 1.0-alpha.
- [ ] Xác nhận bundle không kéo Node TCP modules hoặc `ws` vào browser.
- [ ] Cấu hình Spring Boot WebSocket mapping path đúng với URL client.
- [ ] Dùng `wss://`, cấu hình CSP `connect-src` và kiểm tra Origin allowlist.
- [ ] Xác thực bằng cookie/ticket hoặc RSocket metadata; không dựa riêng vào Origin.
- [ ] Thống nhất protocol, data MIME type, metadata MIME type, route và interaction model.
- [ ] Giới hạn demand và application queue vì WebSocket browser API không có backpressure.
- [ ] Kiểm thử reconnect, background tab, mobile network, proxy và payload lớn.
- [ ] Đánh giá tình trạng bảo trì, dependency, security issue và khả năng nâng cấp của package trước production.

Với browser, lựa chọn thực tế là RSocket JavaScript chạy trên WebSocket transport. Khả năng tương thích cần được đánh giá ở cả browser API, dòng phiên bản thư viện, bundler, endpoint Spring và chính sách mạng/bảo mật. Khi pin đúng package set, dùng WSS, giới hạn demand và kiểm thử trên ma trận browser thực tế, ứng dụng có thể khai thác các interaction model RSocket mà vẫn kiểm soát được khác biệt giữa desktop, mobile và WebView.

## Tài liệu tham khảo

- [RSocket JS — Client guide](https://rsocket.io/guides/rsocket-js/client/)
- [RSocket JS — WebSocket client](https://rsocket.io/guides/rsocket-js/client/rsocket-websocket-client/)
- [RSocket JS — TCP client browser limitation](https://rsocket.io/guides/rsocket-js/client/rsocket-tcp-client/)
- [RSocket JS — GitHub repository and release status](https://github.com/rsocket/rsocket-js)
- [npm — `rsocket-core` versions](https://www.npmjs.com/package/rsocket-core)
- [npm — `rsocket-websocket-client` versions](https://www.npmjs.com/package/rsocket-websocket-client)
- [RSocket JS — Flowable and Single](https://rsocket.io/guides/rsocket-js/rsocket-flowable/)
- [RSocket implementations compatibility matrix](https://rsocket.io/about/implementations/)
- [Spring Boot — RSocket WebSocket server](https://docs.spring.io/spring-boot/reference/messaging/rsocket.html)
- [MDN — WebSocket API](https://developer.mozilla.org/en-US/docs/Web/API/WebSockets_API)
- [MDN — WebSocket binaryType](https://developer.mozilla.org/en-US/docs/Web/API/WebSocket/binaryType)
- [OWASP — WebSocket Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/WebSocket_Security_Cheat_Sheet.html)
