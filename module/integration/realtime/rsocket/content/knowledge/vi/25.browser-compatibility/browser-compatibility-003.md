# Thống nhất route, composite metadata và định dạng dữ liệu giữa Java và JavaScript

Một ứng dụng Java/Spring có thể giao tiếp với trình duyệt qua RSocket mà không cần đổi interaction model. Phần cần thống nhất là hợp đồng trên wire: transport, route, MIME type của data, MIME type của metadata, cách mã hóa từng metadata entry và schema của payload. Nếu Java và JavaScript dùng cùng các quy ước này, hai bên có thể trao đổi request-response, fire-and-forget, stream và channel trên một kết nối WebSocket.

Trong trình duyệt, RSocket thường chạy trên WebSocket vì browser không mở raw TCP socket. Java server vẫn có thể dùng RSocket Java và Spring Messaging; WebSocket chỉ là transport mang các RSocket frame. Bài học này xây dựng một hợp đồng mẫu với route devices.status, composite metadata và JSON, sau đó chỉ ra cách mở rộng khi cần metadata tùy chỉnh hoặc dữ liệu streaming.

## Mục tiêu học tập

Sau bài học, người học có thể:

- Giải thích vai trò của WebSocket khi trình duyệt giao tiếp với RSocket server.
- Thống nhất route giữa @MessageMapping của Spring và client JavaScript.
- Phân biệt MIME type của toàn bộ metadata với MIME type của từng entry trong composite metadata.
- Mã hóa route bằng encodeRoute và encodeCompositeMetadata trong rsocket-js.
- Cấu hình Java/Spring và JavaScript cùng sử dụng application/json cho data.
- Chọn serializer và binary encoder tương thích ở client JavaScript.
- Đăng ký decoder cho metadata tùy chỉnh ở Spring.
- Thiết kế schema JSON dùng chung, bao gồm ngày giờ, số nguyên lớn và trường tùy chọn.
- Kiểm thử kết nối browser-to-Java và chẩn đoán lỗi route, metadata, codec, WebSocket.

## 1. Hợp đồng liên thông gồm những gì?

RSocket tách một message thành hai phần độc lập:

- **Data** chứa nội dung nghiệp vụ, ví dụ JSON mô tả thiết bị cần truy vấn.
- **Metadata** chứa thông tin điều khiển hoặc ngữ cảnh, ví dụ route, authentication, tracing và correlation ID.

Hai phần này có thể dùng encoding khác nhau. MIME type của data và metadata được khai báo trong frame SETUP và áp dụng cho connection. Metadata của từng request có thể chứa nhiều entry độc lập nếu connection dùng composite metadata.

| Thành phần | Giá trị trong ví dụ | Phạm vi |
|---|---|---|
| Transport | WebSocket | Connection giữa browser và server |
| Endpoint | /rsocket | Đường dẫn WebSocket trên server |
| Data MIME type | application/json | Data của các payload trên connection |
| Metadata MIME type | message/x.rsocket.composite-metadata.v0 | Cách đóng gói metadata trên connection |
| Routing entry MIME type | message/x.rsocket.routing.v0 | Một entry bên trong composite metadata |
| Route | devices.status | Chọn handler Spring |
| Data schema | DeviceStatusQuery | Nội dung request JSON |
| Response schema | DeviceStatus | Nội dung response JSON |

Có thể xem hợp đồng này như một giao ước hai lớp: route và metadata quyết định request được gửi tới đâu; data MIME type cùng schema quyết định hai bên hiểu nội dung ra sao.

~~~mermaid
flowchart TD
    B[Browser application] --> JS[rsocket-js client]
    JS --> WS[WebSocket binary frames]
    WS --> SERVER[Spring Boot RSocket server]
    SERVER --> ROUTE[Composite metadata]
    ROUTE --> HANDLER[@MessageMapping devices.status]
    SERVER --> JSON[application/json data]
    JSON --> DTO[DeviceStatusQuery DTO]
    HANDLER --> RESPONSE[DeviceStatus JSON]
    RESPONSE --> B
~~~

Điểm quan trọng: devices.status là route nằm trong metadata. Không cần lặp route trong JSON body, trừ khi route đó cũng là một trường nghiệp vụ có ý nghĩa riêng.

## 2. Browser dùng WebSocket transport

Java RSocket hỗ trợ TCP và WebSocket. Trình duyệt cung cấp WebSocket API nhưng không cung cấp raw TCP socket cho JavaScript chạy trong trang web. Vì vậy, kiến trúc thường có dạng:

- Browser mở ws:// trong môi trường phát triển hoặc wss:// trong môi trường production.
- WebSocket mang các RSocket frame dạng binary.
- RSocket server xử lý SETUP, request, response, stream và flow control như bình thường.

RSocket over WebSocket là giao thức RSocket được đóng gói trực tiếp trên WebSocket. Nó không phải STOMP over WebSocket, SockJS hay một giao thức JSON tự định nghĩa.

### Cấu hình Spring Boot WebSocket endpoint

Với ứng dụng WebFlux dùng Reactor Netty, Spring Boot có thể gắn RSocket vào Web Server:

~~~yaml
spring:
  rsocket:
    server:
      transport: websocket
      mapping-path: /rsocket
~~~

Trong cấu hình này, endpoint được phục vụ qua Web Server hiện có, ví dụ ws://localhost:8080/rsocket. Khi dùng kiểu tích hợp này, không khai báo spring.rsocket.server.port; WebSocket dùng cổng HTTP của ứng dụng. Việc gắn RSocket vào Web Server yêu cầu Reactor Netty.

Nếu muốn chạy một RSocket WebSocket server độc lập, cấu hình transport và port theo mô hình embedded server của Spring Boot. Hãy phân biệt hai cách triển khai để tránh kết nối nhầm cổng hoặc nhầm path.

### Lưu ý khi triển khai qua browser

- Production nên dùng wss:// để bảo vệ data và metadata trên đường truyền.
- Reverse proxy phải hỗ trợ HTTP Upgrade và giữ kết nối WebSocket lâu dài.
- Path của client phải khớp mapping-path trên server.
- Server hoặc gateway cần kiểm tra Origin theo danh sách website được phép.
- Browser WebSocket API không cho ứng dụng tùy ý gắn HTTP header vào handshake như một số HTTP client. Nếu dùng token, hãy truyền qua RSocket setup metadata hoặc request metadata theo chính sách bảo mật.
- Không đưa access token vào query string của WebSocket URL vì URL thường xuất hiện trong log, proxy và công cụ quan sát.
- WebSocket API trong browser dùng native WebSocket; không cần ws package. ws thường dùng cho môi trường Node.js.

## 3. Thống nhất route Java và JavaScript

Trong Spring, route được khai báo bằng @MessageMapping. Trong JavaScript, route được mã hóa thành một metadata entry có MIME type message/x.rsocket.routing.v0.

Ví dụ chọn một route duy nhất:

~~~text
devices.status
~~~

Handler phía Java:

~~~java
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Mono;

@Controller
public class DeviceStatusController {

    private final DeviceStatusService statusService;

    public DeviceStatusController(DeviceStatusService statusService) {
        this.statusService = statusService;
    }

    @MessageMapping("devices.status")
    public Mono<DeviceStatus> status(
            @Payload DeviceStatusQuery query) {

        return statusService.findStatus(query.deviceId());
    }
}
~~~

Khi client gửi request tới route devices.status, Spring tìm handler tương ứng và giải mã data thành DeviceStatusQuery.

Quy ước route nên được thống nhất:

- Dùng chữ thường và dấu chấm để phân tách nhóm chức năng, ví dụ devices.status, devices.events, devices.readings.
- Không dùng dấu gạch chéo ở một phía và dấu chấm ở phía còn lại nếu chưa có quy tắc ánh xạ rõ ràng.
- Giữ nguyên chữ hoa/chữ thường; không dựa vào việc một framework có thể tự chuẩn hóa route.
- Dùng route version khi cần thay đổi hợp đồng lớn, ví dụ devices.status.v2.
- Đặt route trong metadata; đặt dữ liệu nghiệp vụ trong data payload.

Spring hỗ trợ route prefix ở cấp class và route con ở cấp method. Ví dụ @MessageMapping("devices") trên class và @MessageMapping("status") trên method tạo route đầy đủ devices.status. Khi phối hợp Java và JavaScript, hãy ghi route đầy đủ vào hợp đồng API để tránh hiểu nhầm cách ghép prefix.

## 4. Composite metadata: một payload chứa nhiều entry

Composite metadata là định dạng metadata cho phép gộp nhiều entry có MIME type riêng vào một metadata payload. Ví dụ một request có thể chứa:

- Routing entry: message/x.rsocket.routing.v0.
- Authentication entry: MIME type authentication do RSocket định nghĩa.
- Tracing entry: MIME type tracing.
- Metadata tùy chỉnh của ứng dụng: MIME type riêng.

MIME type của toàn bộ metadata payload là:

~~~text
message/x.rsocket.composite-metadata.v0
~~~

MIME type của route entry là:

~~~text
message/x.rsocket.routing.v0
~~~

Hai giá trị này có vai trò khác nhau. metadataMimeType trong SETUP khai báo cách đóng gói toàn bộ metadata. Mỗi entry bên trong composite metadata có MIME type riêng để responder biết cách giải mã entry đó.

~~~mermaid
flowchart TD
    P[Metadata payload] --> CM[Composite metadata]
    CM --> R[Routing entry]
    CM --> A[Authentication entry]
    CM --> T[Tracing entry]
    CM --> X[Custom application entry]
    R --> RT[message/x.rsocket.routing.v0]
    A --> AT[Authentication MIME]
    T --> TT[Tracing MIME]
    X --> XT[Custom MIME]
~~~

Spring RSocketRequester mặc định dùng composite metadata. Khi gọi .route("devices.status"), Spring tự mã hóa routing entry. Phía JavaScript cần mã hóa route entry và composite metadata rõ ràng.

Không đặt metadataMimeType thành application/json rồi truyền một buffer composite metadata vào đó. Khi làm vậy, server sẽ diễn giải bytes composite như JSON metadata và có thể báo metadata malformed hoặc không tìm được route.

## 5. JavaScript mã hóa route bằng rsocket-js

Ví dụ dưới đây sử dụng API rsocket-js dòng 0.x để minh họa các hàm encodeRoute và encodeCompositeMetadata. Các package npm của rsocket-js được phát hành độc lập; cần khóa các package về cùng một dòng API tương thích trong lockfile.

Cài package cho ví dụ:

~~~bash
npm install --save-exact rsocket-core@0.0.29-alpha.0 rsocket-websocket-client@0.0.29-alpha.0
~~~

Ví dụ browser client:

~~~javascript
import {
  RSocketClient,
  JsonSerializer,
  IdentitySerializer,
  BufferEncoders,
  APPLICATION_JSON,
  MESSAGE_RSOCKET_COMPOSITE_METADATA,
  MESSAGE_RSOCKET_ROUTING,
  encodeCompositeMetadata,
  encodeRoute,
} from "rsocket-core";

import RSocketWebsocketClient from "rsocket-websocket-client";

const client = new RSocketClient({
  serializers: {
    data: JsonSerializer,
    metadata: IdentitySerializer,
  },
  setup: {
    keepAlive: 60000,
    lifetime: 180000,
    dataMimeType: APPLICATION_JSON.string,
    metadataMimeType: MESSAGE_RSOCKET_COMPOSITE_METADATA.string,
  },
  transport: new RSocketWebsocketClient(
    {
      url: "wss://api.example.com/rsocket",
    },
    BufferEncoders
  ),
});

async function findDeviceStatus(deviceId) {
  const socket = await client.connect();

  const metadata = encodeCompositeMetadata([
    [
      MESSAGE_RSOCKET_ROUTING,
      encodeRoute("devices.status"),
    ],
  ]);

  return new Promise((resolve, reject) => {
    socket.requestResponse({
      data: {
        deviceId,
      },
      metadata,
    }).subscribe({
      onComplete: (response) => resolve(response.data),
      onError: (error) => reject(error),
    });
  });
}

findDeviceStatus("sensor-17")
  .then((status) => console.log("Device status:", status))
  .catch((error) => console.error("RSocket request failed:", error));
~~~

Trong ví dụ:

- dataMimeType khai báo data dùng JSON.
- metadataMimeType khai báo toàn bộ metadata là composite metadata.
- JsonSerializer chuyển object JavaScript thành JSON khi gửi và chuyển JSON nhận được thành object.
- IdentitySerializer giữ nguyên metadata buffer đã được mã hóa.
- BufferEncoders cung cấp binary encoding cần thiết cho metadata composite.
- encodeRoute("devices.status") tạo routing metadata theo định dạng extension.
- encodeCompositeMetadata(...) đóng gói routing entry vào metadata payload.
- requestResponse(...) gửi data và metadata trên cùng một request.

Với browser, RSocketWebsocketClient dùng WebSocket có sẵn của trình duyệt. Nếu chạy ví dụ trong Node.js, cần cung cấp WebSocket implementation phù hợp cho môi trường Node theo hướng dẫn của package.

### Vì sao metadata dùng IdentitySerializer?

encodeCompositeMetadata(...) đã tạo ra bytes đúng định dạng protocol. Nếu dùng JsonSerializer cho metadata, serializer có thể biến buffer composite thành chuỗi JSON hoặc một biểu diễn khác, làm thay đổi bytes mà server cần giải mã.

Quy tắc thực hành:

- Data là object nghiệp vụ: dùng JsonSerializer nếu connection khai báo application/json.
- Metadata composite đã mã hóa: dùng IdentitySerializer.
- Transport phải dùng binary encoder tương thích với dữ liệu metadata đã mã hóa.

Không tự ghép route bằng cách nối chuỗi hoặc tự viết byte length nếu đã có encodeRoute. Hàm này đảm nhận quy tắc encoding của routing extension.

### Chú ý về phiên bản rsocket-js

Tài liệu WebSocket client trên rsocket.io ghi rõ các ví dụ cũ áp dụng cho API 0.x. Nhánh TypeScript 1.0.0-alpha là một lần viết lại có thay đổi breaking ở package và API; tài liệu 0.x không thể được sao chép nguyên xi sang nhánh alpha.

Đoạn code trong bài dùng API 0.x để minh họa. Không trộn package rsocket-core, transport và composite metadata từ các dòng phiên bản khác nhau. Trước khi dùng trong hệ thống production, kiểm tra tình trạng phát hành, bảo trì, bảo mật và khả năng tương thích của phiên bản npm đang chọn; hậu tố alpha cho biết API chưa đạt cam kết ổn định 1.0.

## 6. Cấu hình Java/Spring cùng hợp đồng JSON

Spring Boot cung cấp RSocketRequester.Builder và RSocketStrategies. Với spring-boot-starter-rsocket, Boot tự cấu hình các codec Jackson CBOR/JSON khi dependency tương ứng có mặt. Để hợp đồng với browser rõ ràng, client Java nên khai báo application/json tường minh.

Ví dụ Java client kết nối cùng WebSocket endpoint:

~~~java
import java.net.URI;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.util.MimeTypeUtils;

@Configuration
public class RSocketClientConfiguration {

    @Bean
    RSocketRequester browserCompatibleRequester(
            RSocketRequester.Builder builder) {

        return builder
                .dataMimeType(MimeTypeUtils.APPLICATION_JSON)
                .metadataMimeType(MimeTypeUtils.parseMimeType(
                        "message/x.rsocket.composite-metadata.v0"))
                .webSocket(URI.create(
                        "wss://api.example.com/rsocket"));
    }
}
~~~

Khi gọi:

~~~java
public Mono<DeviceStatus> findStatus(String deviceId) {
    return requester
            .route("devices.status")
            .data(new DeviceStatusQuery(deviceId))
            .retrieveMono(DeviceStatus.class);
}
~~~

Spring tự mã hóa route thành routing metadata và serialize DTO bằng encoder phù hợp với application/json. Đây là cùng route và cùng data contract với browser client ở phần trước.

Không phải lúc nào cũng cần tự cấu hình RSocketStrategies. Nếu Boot đã đăng ký JSON codecs, dùng builder được auto-configure là đủ. Nếu tự tạo strategies, phải bảo đảm có cả encoder và decoder cho JSON ở client/server; chỉ khai báo dataMimeType không tự cài thêm codec.

## 7. DTO và JSON schema phải giống nhau

Ví dụ DTO phía Java:

~~~java
public record DeviceStatusQuery(
        String deviceId
) {}

public record DeviceStatus(
        String deviceId,
        String state,
        String observedAt
) {}
~~~

Request JSON do browser gửi:

~~~json
{
  "deviceId": "sensor-17"
}
~~~

Response JSON từ Java:

~~~json
{
  "deviceId": "sensor-17",
  "state": "ONLINE",
  "observedAt": "2026-11-22T09:30:00Z"
}
~~~

JavaScript nhận object có cùng tên field:

~~~javascript
{
  deviceId: "sensor-17",
  state: "ONLINE",
  observedAt: "2026-11-22T09:30:00Z"
}
~~~

Một số quy ước schema nên được thống nhất trước:

| Kiểu dữ liệu | Quy ước liên thông |
|---|---|
| Tên field | Dùng cùng camelCase hoặc cấu hình mapping rõ ràng |
| Ngày giờ | Chuỗi ISO-8601 có timezone, ưu tiên UTC |
| Enum | Chuỗi có giá trị ổn định như ONLINE, OFFLINE |
| Boolean | Chỉ dùng true hoặc false, không thay bằng chuỗi |
| Số nguyên lớn | Dùng chuỗi thập phân nếu có thể vượt giới hạn integer an toàn của JavaScript |
| Tiền hoặc số thập phân chính xác | Dùng chuỗi decimal hoặc quy ước decimal rõ ràng |
| Binary | Dùng Base64 trong JSON hoặc một payload binary có MIME type riêng |
| Trường tùy chọn | Quy định rõ khác biệt giữa thiếu field và null |
| Version | Dùng route version hoặc trường schemaVersion theo hợp đồng |

Java long có thể chứa giá trị lớn hơn giới hạn số nguyên an toàn của JavaScript (2^53 - 1). Nếu Java gửi số lớn như JSON number, JavaScript có thể làm tròn và mất chính xác. Với ID, sequence hoặc counter có thể vượt giới hạn này, hãy serialize thành chuỗi.

Tương tự, BigDecimal không nên chuyển tùy tiện thành JavaScript number nếu cần giữ chính xác. Dùng chuỗi decimal hoặc một quy ước số học đã được kiểm thử ở cả hai phía.

## 8. Data MIME type và metadata MIME type không thể thay thế nhau

Có hai MIME type cấp connection:

- dataMimeType: định dạng của data payload, ví dụ application/json.
- metadataMimeType: định dạng đóng gói metadata, ví dụ message/x.rsocket.composite-metadata.v0.

Trong composite metadata, từng entry lại có MIME type riêng. Ví dụ route entry có MIME type message/x.rsocket.routing.v0; metadata tracing có thể dùng MIME type tracing; metadata của ứng dụng có thể dùng MIME type riêng.

| Cấp | Ví dụ | Được dùng để |
|---|---|---|
| Data MIME type | application/json | Giải mã body thành DTO |
| Metadata payload MIME type | message/x.rsocket.composite-metadata.v0 | Giải mã cấu trúc composite metadata |
| Metadata entry MIME type | message/x.rsocket.routing.v0 | Giải mã route |
| Metadata entry MIME type tùy chỉnh | text/plain hoặc MIME type của ứng dụng | Giải mã correlation ID, tenant hint hoặc context khác |

Không đặt route vào application/json chỉ vì data đang dùng JSON. Cũng không đặt composite metadata thành application/json; đây là hai encoding độc lập.

## 9. Đọc metadata tùy chỉnh ở Spring

Spring DefaultMetadataExtractor có hỗ trợ sẵn routing metadata message/x.rsocket.routing.v0 và trích route thành header route. Với entry metadata khác, ứng dụng cần cung cấp decoder và đăng ký cách trích xuất.

Ví dụ nếu browser gửi thêm correlation ID dưới dạng text/plain, Java có thể đăng ký metadata extractor:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.codec.json.Jackson2JsonDecoder;
import org.springframework.http.codec.json.Jackson2JsonEncoder;
import org.springframework.messaging.rsocket.RSocketStrategies;
import org.springframework.util.MimeTypeUtils;

@Configuration
public class RSocketMetadataConfiguration {

    @Bean
    RSocketStrategies rSocketStrategies() {
        return RSocketStrategies.builder()
                .encoders(encoders -> encoders.add(new Jackson2JsonEncoder()))
                .decoders(decoders -> decoders.add(new Jackson2JsonDecoder()))
                .metadataExtractorRegistry(registry ->
                        registry.metadataToExtract(
                                MimeTypeUtils.TEXT_PLAIN,
                                String.class,
                                "clientContext"))
                .build();
    }
}
~~~

Khi đó JavaScript có thể bổ sung entry:

~~~javascript
import {
  TEXT_PLAIN,
  MESSAGE_RSOCKET_ROUTING,
  encodeCompositeMetadata,
  encodeRoute,
} from "rsocket-core";

const metadata = encodeCompositeMetadata([
  [
    MESSAGE_RSOCKET_ROUTING,
    encodeRoute("devices.status"),
  ],
  [
    TEXT_PLAIN,
    "web-dashboard",
  ],
]);
~~~

Phía handler Spring có thể nhận metadata đã trích xuất qua header:

~~~java
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;

@MessageMapping("devices.status")
public Mono<DeviceStatus> status(
        @Payload DeviceStatusQuery query,
        @Header("clientContext") String clientContext) {

    log.debug("Request source: {}", clientContext);
    return statusService.findStatus(query.deviceId());
}
~~~

clientContext chỉ là ví dụ metadata không nhạy cảm. Không dùng một giá trị do client tự khai báo để quyết định quyền truy cập hoặc tenant security boundary. Với metadata tùy chỉnh, hãy thống nhất MIME type, encoding và decoder ở cả hai phía; nếu entry không được đăng ký decoder, Spring không thể tự hiểu nội dung của nó.

Nếu dùng RSocketStrategies tùy chỉnh trong ứng dụng Spring Boot, cần bảo đảm strategies đó vẫn có các encoder/decoder JSON mà ứng dụng cần. Có thể mở rộng cấu hình Boot hiện có thay vì thay thế toàn bộ codec registry bằng một cấu hình thiếu JSON.

## 10. Authentication metadata và routing metadata

Authentication cũng có thể là một entry riêng trong composite metadata. Ví dụ bearer token dùng MIME type của RSocket Authentication Metadata Extension. Route và token có thể cùng nằm trong composite metadata của request:

~~~javascript
import {
  MESSAGE_RSOCKET_ROUTING,
  MESSAGE_RSOCKET_AUTHENTICATION,
  encodeCompositeMetadata,
  encodeRoute,
  encodeBearerAuthMetadata,
} from "rsocket-core";

const metadata = encodeCompositeMetadata([
  [
    MESSAGE_RSOCKET_ROUTING,
    encodeRoute("devices.status"),
  ],
  [
    MESSAGE_RSOCKET_AUTHENTICATION,
    encodeBearerAuthMetadata(accessToken),
  ],
]);
~~~

Tên hàm và constant cần import từ đúng phiên bản rsocket-js đã chọn. Server cần cấu hình Spring Security RSocket để hiểu authentication metadata tương ứng.

Trong API rsocket-js 0.x của ví dụ, MESSAGE_RSOCKET_AUTHENTICATION là MIME type của authentication extension; encodeBearerAuthMetadata mã hóa scheme bearer cùng token. Ở phía Spring Security, bật JWT authentication bằng DSL .jwt(...) và cung cấp ReactiveJwtDecoder. Không thay entry này bằng một chuỗi token tự đặt MIME type nếu muốn dùng bộ giải mã chuẩn của Spring Security.

Một số nguyên tắc:

- Không đưa token vào data JSON nếu server đã hỗ trợ authentication metadata.
- Không log composite metadata có chứa credential.
- Browser nên gửi token trong SETUP hoặc request metadata theo mô hình bảo mật đã chọn; không đưa token vào query string.
- Dùng wss:// trong production.
- Authentication và authorization vẫn phải được thực hiện ở server; route không phải cơ chế bảo mật.

Nếu dùng một connection cho nhiều user, credential theo từng request thường giúp mỗi request được xác thực theo principal tương ứng. Nếu danh tính gắn ở SETUP, hãy quản lý connection theo identity và không chia sẻ connection đó giữa các principal.

## 11. Tương tác streaming vẫn dùng cùng route và codec

Request-stream và request-channel cũng sử dụng cùng cách mã hóa route và metadata. Khác biệt là lifecycle của interaction và số lượng payload.

Java handler trả stream:

~~~java
@MessageMapping("devices.readings")
public Flux<DeviceReading> readings(
        @Payload DeviceReadingQuery query) {

    return readingService.stream(query.deviceId());
}
~~~

JavaScript khởi tạo request-stream:

~~~javascript
const metadata = encodeCompositeMetadata([
  [
    MESSAGE_RSOCKET_ROUTING,
    encodeRoute("devices.readings"),
  ],
]);

socket.requestStream({
  data: {
    deviceId: "sensor-17",
  },
  metadata,
}).subscribe({
  onSubscribe: (subscription) => {
    subscription.request(32);
  },
  onNext: (reading) => {
    console.log("Reading:", reading);
  },
  onError: (error) => {
    console.error("Stream failed:", error);
  },
  onComplete: () => {
    console.log("Stream completed");
  },
});
~~~

Số 32 là demand ban đầu trong ví dụ; client có thể yêu cầu thêm item khi đã xử lý xong một phần dữ liệu. Đây là backpressure của RSocket/Reactive Streams. Không yêu cầu số lượng vô hạn nếu ứng dụng không có lý do và không kiểm soát được tốc độ producer.

Nếu stream dài hạn, cần xử lý cancellation khi component UI bị unmount hoặc người dùng rời màn hình. Không giữ subscription không còn được sử dụng, vì server có thể tiếp tục tạo dữ liệu và giữ tài nguyên.

## 12. Route versioning và thay đổi schema

Route và JSON schema là hai hợp đồng có thể tiến hóa độc lập. Một thay đổi không tương thích có thể yêu cầu version route mới:

~~~text
devices.status.v1
devices.status.v2
~~~

Khi thay đổi schema theo hướng tương thích, ưu tiên:

- Thêm field tùy chọn thay vì đổi kiểu field đang tồn tại.
- Giữ nguyên ý nghĩa và tên field cũ.
- Đặt default rõ ràng khi client cũ không gửi field mới.
- Không đổi enum value đã phát hành nếu client có thể lưu/cache giá trị đó.
- Chỉ loại bỏ field sau khi các client cũ đã được nâng cấp hoặc có thời gian sunset.

Ví dụ DeviceStatusQuery phiên bản mới có thể bổ sung includeMetrics là field tùy chọn. Server cũ có thể bỏ qua field không biết nếu Jackson được cấu hình phù hợp; nhưng hai phía vẫn phải thống nhất cách xử lý unknown fields. Không dựa vào mặc định của serializer mà không kiểm thử.

## 13. Kiểm thử liên thông Java và browser

Một integration test nên xác minh từng lớp của hợp đồng thay vì chỉ kiểm tra rằng WebSocket mở thành công.

| Kiểm tra | Browser client | Java/Spring server |
|---|---|---|
| Transport | Kết nối đúng wss://host/rsocket | WebSocket mapping path đúng |
| SETUP | Gửi application/json | Chấp nhận data MIME type JSON |
| Metadata payload | Gửi composite metadata | Giải mã composite metadata |
| Routing | Encode devices.status | Match @MessageMapping("devices.status") |
| Data | Gửi JSON object đúng schema | Decode thành DeviceStatusQuery |
| Response | Decode JSON object | Encode DeviceStatus |
| Custom metadata | Gửi entry có MIME type riêng | Đăng ký metadata extractor/decoder |
| Authentication | Gửi token đúng vị trí | Xác thực và phân quyền |
| Streaming | Request demand và cancel | Tôn trọng backpressure và cancellation |
| Failure | Hiển thị lỗi protocol/transport | Log route và nguyên nhân xử lý |

Các ca kiểm thử nên có:

1. Browser gọi request-response và nhận đúng DeviceStatus.
2. Route sai bị từ chối hoặc không tìm thấy handler theo chính sách.
3. Thiếu routing metadata bị từ chối.
4. metadataMimeType sai làm client nhận lỗi metadata, xác minh log ở cả hai phía.
5. Data MIME type không tương thích khiến JSON decoder không xử lý được payload.
6. JSON thiếu field bắt buộc được validation theo hợp đồng.
7. Custom metadata được trích đúng vào header.
8. Token sai hoặc hết hạn bị từ chối.
9. Stream chỉ phát số item theo demand và dừng khi client cancel.
10. WebSocket proxy giữ Upgrade, path và kết nối lâu dài.

Có thể dùng browser devtools để kiểm tra WebSocket handshake, trạng thái connection và frame binary. Nội dung RSocket frame là binary; không thể đọc route hay JSON bằng cách nhìn như một HTTP request body thông thường. Dùng RSocket frame logger hoặc công cụ kiểm thử protocol để quan sát khi cần.

## 14. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| WebSocket 404 | Sai mapping path | Đối chiếu URL browser với mapping-path |
| WebSocket handshake bị từ chối | Proxy không hỗ trợ Upgrade hoặc Origin không được phép | Kiểm tra gateway, Origin policy và WebFlux server |
| Connection mở nhưng SETUP bị reject | MIME type hoặc setup payload không hợp lệ | So sánh dataMimeType và metadataMimeType |
| Spring không tìm thấy handler | Route thiếu hoặc mã hóa sai | Dùng encodeRoute và kiểm tra tên @MessageMapping |
| metadata is malformed | Composite metadata bị serialize lại hoặc MIME type sai | Dùng IdentitySerializer cho metadata composite |
| Route đúng nhưng body không decode | Data serializer hoặc data MIME type khác nhau | Thống nhất application/json và JSON codec |
| Spring không thấy custom metadata | Chưa đăng ký decoder/extractor | Cấu hình metadataExtractorRegistry |
| Server đọc ra chuỗi JSON thay vì DTO | Decoder hoặc content type không phù hợp | Kiểm tra JSON decoder và data MIME type |
| JSON number bị sai ở browser | Giá trị vượt giới hạn integer an toàn của JavaScript | Serialize số lớn thành string |
| Browser không kết nối được TCP | Browser không hỗ trợ raw TCP | Dùng WebSocket transport |
| Stream tiêu thụ nhiều bộ nhớ | Demand quá lớn hoặc không cancel subscription | Điều chỉnh demand và vòng đời subscription |

## 15. Checklist hợp đồng trước khi tích hợp

- [ ] Browser và server dùng cùng RSocket protocol version tương thích.
- [ ] Browser dùng WebSocket endpoint và server hỗ trợ WebSocket transport.
- [ ] Path và scheme ws/wss khớp môi trường.
- [ ] Hai bên khai báo cùng data MIME type.
- [ ] Hai bên khai báo cùng metadata payload MIME type.
- [ ] Java và JavaScript dùng cùng route string.
- [ ] Route được mã hóa bằng routing metadata extension.
- [ ] Composite metadata được giữ nguyên dạng binary.
- [ ] JSON schema có tên field, kiểu dữ liệu và quy tắc null thống nhất.
- [ ] Số nguyên lớn, decimal và ngày giờ có quy ước rõ.
- [ ] Custom metadata có MIME type và decoder tương ứng.
- [ ] Authentication metadata được bảo vệ và không bị log.
- [ ] Streaming có backpressure và cancellation.
- [ ] Có integration test chạy browser client với Java server.

## Kết luận

Để Java/Spring và JavaScript trong trình duyệt giao tiếp qua RSocket, hãy thống nhất transport WebSocket, route, MIME type và schema dữ liệu. Route được đặt trong routing metadata message/x.rsocket.routing.v0; khi có nhiều entry, chúng được đóng gói trong composite metadata message/x.rsocket.composite-metadata.v0. Data có thể dùng application/json, với Jackson ở Java và JsonSerializer ở JavaScript. Spring tự mã hóa route qua RSocketRequester.route(...), trong khi rsocket-js dùng encodeRoute(...) và encodeCompositeMetadata(...). Khi các quy ước này giống nhau, hai nền tảng có thể trao đổi request-response và streaming mà không cần chia sẻ implementation nội bộ.

## Tài liệu tham khảo

- [Spring Framework Reference – RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [Spring Boot Reference – RSocket](https://docs.spring.io/spring-boot/reference/messaging/rsocket.html)
- [RSocket Protocol](https://rsocket.io/about/protocol/)
- [RSocket JavaScript Guide](https://rsocket.io/guides/rsocket-js/)
- [RSocket JavaScript WebSocket Client Guide](https://rsocket.io/guides/rsocket-js/client/rsocket-websocket-client/)
- [rsocket-js npm package – rsocket-core](https://www.npmjs.com/package/rsocket-core)
- [rsocket-js npm package – rsocket-websocket-client](https://www.npmjs.com/package/rsocket-websocket-client)
