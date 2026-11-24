# Khởi tạo requester bằng builder và lựa chọn TCP hoặc WebSocket

`RSocketRequester` là API phía client của Spring để gửi request RSocket mà không phải tự tạo frame hoặc thao tác trực tiếp với `Payload`. Builder giúp cấu hình codec, MIME type, dữ liệu trong SETUP và các tùy chọn của `RSocketConnector`; sau đó client chọn transport TCP hoặc WebSocket để mở kết nối.

Trong module `INTEGRATION_REALTIME_RSOCKET`, cùng một `RSocketRequester` có thể gọi Request-Response, Fire-and-Forget, Request-Stream và Request-Channel. Việc chọn TCP hay WebSocket chỉ quyết định cách kết nối và vận chuyển frame. Route, payload, metadata và mô hình tương tác vẫn được xử lý ở tầng RSocket/Spring.

## 1. Vai trò của RSocketRequester.Builder

`RSocketRequester.Builder` là nơi chuẩn bị các thiết lập trước khi kết nối. Một quy trình khởi tạo thường gồm:

1. Chọn `RSocketStrategies` và codec để chuyển đổi DTO thành payload và ngược lại.
2. Chọn MIME type cho data và metadata.
3. Khai báo thông tin gửi trong SETUP nếu server cần dữ liệu khởi tạo phiên.
4. Tùy chỉnh `RSocketConnector` cho keepalive, Resume hoặc các thiết lập giao thức khác.
5. Chọn transport bằng `connectTcp(...)`, `connectWebSocket(...)` hoặc `connect(...)` với transport tự tạo.

```text
RSocketRequester.builder()
          |
          +-- RSocketStrategies / codecs
          +-- data MIME type / metadata MIME type
          +-- SETUP route, data, metadata
          +-- RSocketConnector options
          |
          v
   connectTcp(...)  hoặc  connectWebSocket(...)
          |
          v
   Mono<RSocketRequester>
          |
          v
   requester.route(...).retrieveMono / retrieveFlux / send
```

Các thiết lập builder thuộc về quá trình tạo kết nối. `route(...)` được gọi sau khi có requester để định tuyến từng tương tác nghiệp vụ. Không nhầm `setupRoute(...)` với `route(...)`: `setupRoute` là metadata của frame SETUP lúc mở phiên, còn `route` là route của từng request sau khi kết nối đã được thiết lập.

## 2. Khởi tạo requester qua TCP

TCP phù hợp khi client và server là các ứng dụng Java/native có thể mở socket trực tiếp tới host và port của nhau, thường gặp trong mạng nội bộ hoặc giao tiếp service-to-service.

```java
import org.springframework.messaging.rsocket.RSocketRequester;
import reactor.core.publisher.Mono;

Mono<RSocketRequester> requesterMono = RSocketRequester.builder()
    .connectTcp("rsocket-service", 7000);
```

`connectTcp(host, port)` trả về `Mono<RSocketRequester>`. Kết nối chỉ được thực hiện khi publisher được subscribe. Trong ứng dụng reactive, nên giữ publisher này và kết hợp vào luồng xử lý thay vì gọi `block()` trên event-loop thread.

Nếu cần một requester đồng bộ trong chương trình console hoặc bước khởi tạo ứng dụng chạy ngoài event loop, có thể chờ kết nối:

```java
RSocketRequester requester = RSocketRequester.builder()
    .connectTcp("localhost", 7000)
    .block();
```

Trong môi trường production, host và port nên đến từ cấu hình theo môi trường. Không hardcode `localhost` nếu server chạy ở container hoặc máy khác; `localhost` luôn chỉ chính máy/container đang chạy client.

## 3. Khởi tạo requester qua WebSocket

WebSocket phù hợp khi client chạy trong trình duyệt hoặc kết nối cần đi qua HTTP ingress/reverse proxy hỗ trợ WebSocket Upgrade. Client truyền URI đầy đủ gồm scheme, host, port và path:

```java
import java.net.URI;
import org.springframework.messaging.rsocket.RSocketRequester;
import reactor.core.publisher.Mono;

URI endpoint = URI.create("wss://api.example.com/rsocket");

Mono<RSocketRequester> requesterMono = RSocketRequester.builder()
    .connectWebSocket(endpoint);
```

`ws://` dùng WebSocket không mã hóa ở tầng transport; `wss://` bảo vệ kết nối bằng TLS. URI phải trỏ tới đúng WebSocket endpoint do server hoặc reverse proxy công bố. Nếu server mapping path `/rsocket`, client phải dùng đúng path này.

Ví dụ kết nối WebSocket local không TLS:

```java
RSocketRequester requester = RSocketRequester.builder()
    .connectWebSocket(URI.create("ws://localhost:8080/rsocket"))
    .block();
```

Kết nối WebSocket vẫn mang frame RSocket sau khi handshake Upgrade hoàn tất. Các handler Spring, route metadata và interaction model không cần thay đổi chỉ vì client đổi từ TCP sang WebSocket.

## 4. Cấu hình builder trước khi kết nối

Builder cho phép thiết lập codec và MIME type. Điều này giúp hai phía thống nhất cách mã hóa data và metadata.

```java
import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.util.MimeTypeUtils;

RSocketRequester.Builder builder = RSocketRequester.builder()
    .dataMimeType(MimeTypeUtils.APPLICATION_JSON);

Mono<RSocketRequester> requesterMono = builder
    .connectTcp("rsocket-service", 7000);
```

`dataMimeType(...)` khai báo định dạng của payload data, ví dụ JSON. Metadata có MIME type riêng; khi dùng routing hoặc composite metadata, cần bảo đảm client và server có cấu hình `RSocketStrategies` tương thích. Không thay metadata MIME type một cách tùy tiện nếu server đang chờ định dạng metadata khác.

### 4.1. RSocketStrategies và codec

`RSocketStrategies` tập hợp encoder, decoder và các thành phần hỗ trợ chuyển đổi message. Trong ứng dụng Spring Boot, strategies được cấu hình tự động theo classpath và cấu hình ứng dụng; có thể tùy chỉnh khi cần codec riêng hoặc kiểu dữ liệu đặc thù.

Ví dụ tạo strategies và đưa vào builder:

```java
RSocketStrategies strategies = RSocketStrategies.builder()
    .encoders(encoders -> encoders.add(new CustomEventEncoder()))
    .decoders(decoders -> decoders.add(new CustomEventDecoder()))
    .build();

RSocketRequester.Builder builder = RSocketRequester.builder()
    .rsocketStrategies(strategies)
    .dataMimeType(MimeTypeUtils.APPLICATION_JSON);
```

`CustomEventEncoder` và `CustomEventDecoder` là ví dụ về codec do ứng dụng cung cấp. Chỉ thêm codec khi định dạng hoặc kiểu dữ liệu của ứng dụng yêu cầu; với DTO JSON thông thường, cấu hình mặc định của Spring Boot thường đã đủ.

### 4.2. Dữ liệu khởi tạo trong SETUP

SETUP được gửi khi client tạo một logical connection. Có thể đính kèm route, data hoặc metadata để server biết thông tin khởi tạo client/phiên:

```java
RSocketRequester.Builder builder = RSocketRequester.builder()
    .setupRoute("client.connect")
    .setupData(new ClientInfo("dashboard", "2.4"));
```

Nếu cần metadata riêng, dùng `setupMetadata(value, mimeType)` với MIME type mà server hiểu. SETUP chỉ diễn ra khi tạo kết nối; không dùng nó để gửi thông tin thay đổi theo từng request. Dữ liệu như `deviceId`, bộ lọc hoặc command nên nằm trong route/payload của tương tác tương ứng.

### 4.3. Tùy chỉnh RSocketConnector

Builder cho phép tùy chỉnh connector nền. Ví dụ, thiết lập chu kỳ KEEPALIVE và thời gian tối đa chờ peer phản hồi:

```java
import java.time.Duration;

RSocketRequester.Builder builder = RSocketRequester.builder()
    .rsocketConnector(connector -> connector.keepAlive(
        Duration.ofSeconds(20),
        Duration.ofSeconds(90)
    ));
```

Có thể dùng callback này để cấu hình những tính năng được RSocket Java hỗ trợ trong phiên bản dự án, chẳng hạn Resume hoặc fragmentation. Các tham số cần phù hợp với server và hạ tầng mạng. KEEPALIVE giúp phát hiện peer không phản hồi; nó không thay thế retry nghiệp vụ hoặc chính sách reconnect của ứng dụng.

## 5. Chọn transport theo môi trường

| Tiêu chí | TCP | WebSocket |
|---|---|---|
| API builder | `connectTcp(host, port)` | `connectWebSocket(URI)` |
| Địa chỉ | Host và port | URI `ws://` hoặc `wss://` có path |
| Client điển hình | Java service, ứng dụng native | Browser, ứng dụng qua HTTP ingress |
| Hạ tầng | Cần cho phép kết nối TCP tới cổng dịch vụ | Proxy/ingress phải hỗ trợ HTTP Upgrade và giữ kết nối hai chiều |
| TLS | Cấu hình TLS cho TCP transport theo yêu cầu | Dùng `wss://` và trust chain phù hợp |
| Định tuyến | Host/port | Host/path, thuận tiện cho reverse proxy |

Chọn TCP khi các service kiểm soát được network path và muốn kết nối trực tiếp. Chọn WebSocket khi cần browser client hoặc cần đi qua hạ tầng HTTP hiện có. WebSocket có thêm HTTP handshake và WebSocket framing; TCP có ít lớp đóng gói hơn. Hiệu năng thực tế còn phụ thuộc TLS, proxy, kích thước payload, số stream và độ trễ mạng, vì vậy nên đo trong môi trường triển khai.

Transport phía client phải khớp endpoint phía server. TCP client không thể kết nối vào WebSocket endpoint, và WebSocket client không thể kết nối vào TCP port chỉ vì cả hai đều dùng RSocket protocol.

## 6. Dùng một builder cho cấu hình chung

Nếu ứng dụng hỗ trợ cả TCP và WebSocket theo môi trường, có thể xây dựng một builder đã cấu hình codec/connector chung rồi chọn transport ở bước kết nối:

```java
RSocketRequester.Builder baseBuilder = RSocketRequester.builder()
    .dataMimeType(MimeTypeUtils.APPLICATION_JSON)
    .rsocketConnector(connector -> connector.keepAlive(
        Duration.ofSeconds(20),
        Duration.ofSeconds(90)
    ));

Mono<RSocketRequester> connectTcp = baseBuilder
    .connectTcp("rsocket-service", 7000);

Mono<RSocketRequester> connectWebSocket = baseBuilder
    .connectWebSocket(URI.create("wss://api.example.com/rsocket"));
```

Đây là cách minh họa chia sẻ các tùy chọn chung. Trong ứng dụng thực tế, hãy kiểm tra cách builder được sử dụng trong phiên bản Spring đang chạy; tránh sửa trạng thái builder đồng thời từ nhiều thread hoặc dùng chung một builder mutable giữa các lần khởi tạo không được kiểm soát. Có thể tạo builder mới từ factory cho mỗi kết nối nếu cần các cấu hình riêng.

Nếu cần transport tùy chỉnh, builder cũng có thể kết nối qua API nhận `ClientTransport`. Cách này hữu ích khi cần cấu hình TLS, Netty client hoặc transport đặc thù mà hai phương thức tiện ích TCP/WebSocket không biểu diễn đủ.

## 7. Quản lý Mono kết nối và vòng đời requester

Các phương thức `connectTcp`, `connectWebSocket` và `connect` trả publisher. Điều này có nghĩa:

- Chưa subscribe thì chưa có kết nối được tạo.
- Lỗi DNS, connection refused, TLS handshake hoặc SETUP có thể xuất hiện khi subscribe.
- Không nên tạo kết nối mới cho từng message nếu nhiều request có thể dùng chung một session.
- Cần xác định component nào sở hữu requester và chịu trách nhiệm đóng kết nối khi dừng.

Trong một ứng dụng reactive, có thể kết hợp requester vào pipeline:

```java
Mono<DeviceStatus> loadStatus(String deviceId) {
    return requesterMono.flatMap(requester ->
        requester.route("devices.{deviceId}.status.get", deviceId)
            .data(new StatusQuery())
            .retrieveMono(DeviceStatus.class)
    );
}
```

Nếu requester được tạo một lần và dùng lại, hãy quản lý nó như một tài nguyên cấp ứng dụng hoặc cấp component. Khi ứng dụng dừng, đóng underlying RSocket theo API của phiên bản Spring/RSocket Java đang dùng; không để socket sống ngoài lifecycle của component sở hữu.

Ví dụ khởi tạo đồng bộ trong một component có lifecycle:

```java
@Component
public class DeviceClient implements DisposableBean {
    private final RSocketRequester requester;

    public DeviceClient(RSocketRequester.Builder builder) {
        this.requester = builder
            .connectTcp("rsocket-service", 7000)
            .block();
    }

    public Mono<DeviceStatus> status(String deviceId) {
        return requester.route("devices.{deviceId}.status.get", deviceId)
            .data(new StatusQuery())
            .retrieveMono(DeviceStatus.class);
    }

    @Override
    public void destroy() {
        requester.rsocket().dispose();
    }
}
```

Ví dụ này dùng blocking trong constructor để minh họa một cách sở hữu kết nối ở startup; chỉ phù hợp khi thời điểm khởi tạo không nằm trên event-loop thread và ứng dụng chấp nhận chờ kết nối. Với hệ thống cần startup không blocking, hãy quản lý `Mono<RSocketRequester>` và lifecycle bất đồng bộ tương ứng. Cách đóng requester cần được xác nhận theo phiên bản Spring Framework/RSocket Java của dự án.

## 8. Xử lý lỗi kết nối và reconnect

Lỗi khi tạo requester có thể xuất phát từ DNS, port, WebSocket path, TLS, proxy, server chưa sẵn sàng hoặc SETUP bị từ chối. Nên phân loại lỗi và giới hạn retry:

```java
Mono<RSocketRequester> requesterMono = RSocketRequester.builder()
    .connectTcp("rsocket-service", 7000)
    .retryWhen(Retry.backoff(3, Duration.ofSeconds(1))
        .maxBackoff(Duration.ofSeconds(8))
        .jitter(0.5));
```

Đây là retry cho quá trình thiết lập requester ban đầu. Nó không tự động tái tạo mọi request đang chạy sau khi kết nối đã được thiết lập rồi bị mất. Reconnect sau disconnect là một chính sách vòng đời khác; cần quyết định tạo session mới hay thử Resume, cách khôi phục subscription và cách xử lý lệnh có thể đã được server thực hiện trước khi kết nối đứt.

Không retry vô hạn với khoảng cách cố định. Dùng backoff, jitter, giới hạn số lần và quan sát trạng thái kết nối để tránh nhiều client cùng dồn tải vào server vừa phục hồi.

## 9. Sử dụng requester sau khi kết nối

Sau khi có `RSocketRequester`, các lời gọi nghiệp vụ không phụ thuộc transport đã chọn:

```java
// Request-Response
Mono<DeviceStatus> status = requester
    .route("devices.{deviceId}.status.get", deviceId)
    .data(new StatusQuery())
    .retrieveMono(DeviceStatus.class);

// Fire-and-Forget
Mono<Void> sent = requester
    .route("devices.{deviceId}.telemetry.publish", deviceId)
    .data(event)
    .send();

// Request-Stream
Flux<TelemetryReading> readings = requester
    .route("devices.{deviceId}.telemetry.watch", deviceId)
    .data(new WatchRequest())
    .retrieveFlux(TelemetryReading.class);

// Request-Channel
Flux<DeviceUpdate> updates = requester
    .route("devices.{deviceId}.control.channel", deviceId)
    .data(commands, DeviceCommand.class)
    .retrieveFlux(DeviceUpdate.class);
```

Các lời gọi trên thể hiện bốn interaction model. `retrieveMono` phù hợp với một kết quả, `send()` gửi không cần response payload, `retrieveFlux` nhận một luồng response; Request-Channel dùng publisher đầu vào trong `.data(...)` và nhận `Flux` đầu ra. Nếu đổi từ TCP sang WebSocket, các route và lời gọi này vẫn giữ nguyên.

## 10. Các lỗi cấu hình thường gặp

- **Sai scheme hoặc transport:** dùng `connectTcp` cho endpoint WebSocket hoặc dùng `ws://` khi server yêu cầu `wss://`.
- **Sai WebSocket path:** client kết nối `/` trong khi server/ingress công bố `/rsocket`.
- **Sai host trong container:** `localhost` trỏ về container client, không phải container server.
- **Codec không tương thích:** client gửi JSON nhưng server giải mã theo MIME type hoặc codec khác.
- **SETUP metadata bị nhầm với route request:** `setupRoute` chỉ gửi khi mở phiên, không định tuyến mọi request sau đó.
- **Không subscribe vào connect Mono:** requester chưa được tạo nhưng code đã cố dùng nó.
- **Block trên event loop:** `.block()` có thể làm tắc scheduler reactive.
- **Retry không giới hạn:** nhiều client reconnect đồng thời gây áp lực lớn lên server.
- **Không đóng socket:** connection và tài nguyên Netty tồn tại sau khi component dừng.

## 11. Kiểm thử khởi tạo requester

Nên kiểm thử cả builder và network path:

1. Khởi động RSocket server TCP và kết nối bằng `connectTcp(host, port)`.
2. Khởi động WebSocket endpoint và kết nối bằng `connectWebSocket(uri)` với đúng path.
3. Kiểm tra SETUP route/data/metadata được server nhận đúng.
4. Kiểm tra codec và MIME type bằng DTO ở cả hai phía.
5. Gọi bốn interaction model qua requester và xác nhận kiểu phản hồi tương ứng.
6. Kiểm tra lỗi khi server không chạy, sai port, sai path hoặc sai TLS certificate.
7. Kiểm tra retry ban đầu có giới hạn và không tạo nhiều kết nối thừa.
8. Đóng requester/component; xác nhận socket và tài nguyên transport được giải phóng.
9. Chạy WebSocket qua reverse proxy thực tế để xác nhận Upgrade, path, TLS và idle timeout.

Trong production, theo dõi thời gian kết nối, số connect failure theo transport, lỗi SETUP, số requester đang hoạt động, số lần reconnect, thời gian sống session và lỗi đóng kết nối. Không log thông tin xác thực hoặc metadata nhạy cảm trong quá trình chẩn đoán.

## 12. Kết luận

`RSocketRequester.builder()` tạo cấu hình chung cho codec, MIME type, SETUP và `RSocketConnector`; `connectTcp(host, port)` mở kết nối TCP, còn `connectWebSocket(uri)` mở kết nối WebSocket theo URI/path. Các phương thức kết nối trả `Mono<RSocketRequester>`, vì vậy cần quản lý subscription, lỗi khởi tạo và vòng đời socket rõ ràng. Chọn TCP cho kết nối trực tiếp giữa service, WebSocket cho browser hoặc hạ tầng HTTP, rồi kiểm thử codec, SETUP, TLS, proxy và graceful shutdown trên đúng môi trường triển khai.
