# Tự cấu hình RSocketStrategies, RSocketMessageHandler và RSocketRequester.Builder

## Bối cảnh: thống nhất cách mã hóa và xử lý RSocket ở cả hai phía

Trong ứng dụng Spring Boot dùng RSocket, các route thường nhận và trả về DTO Java thay vì thao tác trực tiếp với byte array. Để chuyển DTO thành payload và giải mã payload thành đối tượng, Spring cần biết bộ encoder, decoder, cách xử lý metadata và cách định tuyến message.

Ba thành phần giữ vai trò trung tâm:

- **RSocketStrategies** tập hợp codec và các chiến lược xử lý data, metadata cho RSocket.
- **RSocketMessageHandler** kết nối message của RSocket với các phương thức xử lý như @MessageMapping và @ConnectMapping.
- **RSocketRequester.Builder** tạo client requester, cấu hình codec, MIME type, metadata và transport trước khi thiết lập kết nối.

Khi các thành phần này dùng cấu hình không thống nhất, client có thể gửi JSON nhưng server lại giải mã theo định dạng khác, metadata không được ánh xạ vào header mong muốn hoặc route không được xử lý như dự kiến. Tự cấu hình đúng giúp kiểm soát định dạng trao đổi, cách trích xuất metadata và cách tạo requester tới từng endpoint.

Bài học này trình bày cách khai báo ba thành phần trong Spring Boot, cách chúng phối hợp với nhau, cách cấu hình TCP/WebSocket và những điểm cần kiểm tra khi Spring Boot đã có auto-configuration.

## 1. Vai trò và mối quan hệ giữa ba thành phần

| Thành phần | Trách nhiệm | Thường được dùng ở đâu |
|---|---|---|
| RSocketStrategies | Đăng ký encoder, decoder, metadata extractor và các chiến lược hỗ trợ | Server handler và client requester |
| RSocketMessageHandler | Nhận message, tìm route, giải mã tham số và gọi handler method | Phía server, hoặc peer có nhận message mapping |
| RSocketRequester.Builder | Cấu hình và tạo RSocketRequester để gửi request | Phía client |

Có thể hình dung luồng xử lý như sau:

~~~mermaid
flowchart TD
    A["RSocketRequester.Builder"] --> B["RSocketRequester"]
    B --> C["Mã hóa DTO và metadata"]
    C --> D["RSocket transport"]
    D --> E["RSocketMessageHandler"]
    E --> F["RSocketStrategies"]
    F --> G["Giải mã payload và trích xuất metadata"]
    G --> H["@MessageMapping handler"]
    H --> I["Mono / Flux response"]
    I --> F
    F --> J["Mã hóa response"]
    J --> D
~~~

RSocketStrategies không tự mở kết nối mạng và cũng không trực tiếp xử lý nghiệp vụ. Nó cung cấp các thành phần mà requester và message handler sử dụng. RSocketMessageHandler điều phối message tới phương thức ứng dụng. RSocketRequester.Builder tạo requester có cấu hình phù hợp để giao tiếp với peer.

Trong một ứng dụng hai chiều, mỗi peer có thể vừa gửi vừa nhận request. Khi đó, vai trò requester và message handler không nhất thiết gắn cố định với client hoặc server theo nghĩa HTTP.

## 2. RSocketStrategies: cấu hình codec và metadata

RSocketStrategies là tập hợp các thành phần mà Spring dùng để mã hóa và giải mã nội dung RSocket. Những cấu hình quan trọng thường gồm:

- Encoder để chuyển đối tượng Java thành data hoặc metadata.
- Decoder để chuyển data hoặc metadata thành đối tượng Java.
- Metadata extractor để trích xuất metadata thành giá trị có thể truy cập trong handler.
- Route matcher để áp dụng quy tắc khớp route nếu ứng dụng cần tùy chỉnh.

### Đăng ký Jackson JSON codec

Ví dụ sau cấu hình Jackson encoder và decoder dùng chung một ObjectMapper:

~~~java
@Configuration
class RSocketConfiguration {

    @Bean
    RSocketStrategies rSocketStrategies(ObjectMapper objectMapper) {
        return RSocketStrategies.builder()
            .encoders(encoders ->
                encoders.add(new Jackson2JsonEncoder(objectMapper)))
            .decoders(decoders ->
                decoders.add(new Jackson2JsonDecoder(objectMapper)))
            .build();
    }
}
~~~

ObjectMapper có thể là bean do Spring Boot cung cấp. Dùng chung mapper giúp quy tắc JSON nhất quán với phần còn lại của ứng dụng, ví dụ naming strategy, Java Time module hoặc custom serializer.

Đoạn cấu hình chỉ thêm codec tùy chỉnh vào danh sách encoder/decoder. Nếu ứng dụng dùng codec mặc định của Spring, hãy kiểm tra danh sách codec trước khi thêm để tránh đăng ký trùng hoặc tạo thứ tự lựa chọn không mong muốn. Chỉ thêm Jackson codec tường minh khi cần kiểm soát cấu hình hoặc định dạng.

Các lớp cấu hình ở mục này và ví dụ metadata bên dưới là hai cách minh họa độc lập. Nếu dùng metadata extractor trong cùng ứng dụng, hãy gộp phần đăng ký extractor vào một bean RSocketStrategies duy nhất thay vì khai báo hai bean cùng tên.

Các import thường dùng trong ví dụ:

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.codec.json.Jackson2JsonDecoder;
import org.springframework.http.codec.json.Jackson2JsonEncoder;
import org.springframework.messaging.rsocket.RSocketStrategies;
~~~

### Chọn data MIME type nhất quán

Codec cho biết cách chuyển đổi đối tượng; MIME type cho biết định dạng payload mà hai peer thỏa thuận sử dụng. Nếu client gửi JSON, data MIME type cần thể hiện JSON và server cần có decoder tương ứng.

Ví dụ, client cấu hình JSON:

~~~java
RSocketRequester.Builder builder = RSocketRequester.builder()
    .rsocketStrategies(strategies)
    .dataMimeType(MimeTypeUtils.APPLICATION_JSON);
~~~

Các MIME type phải được thống nhất giữa các peer. Việc đăng ký Jackson codec không tự động bảo đảm peer bên kia đã chọn cùng data MIME type. Khi kết nối, MIME type được trao đổi trong thông tin SETUP và được dùng để diễn giải data của payload.

Nếu ứng dụng dùng CBOR hoặc protobuf, hãy đăng ký codec tương ứng và cấu hình data MIME type phù hợp. Không nên gửi JSON nhưng khai báo MIME type của CBOR hoặc ngược lại.

### Cấu hình metadata extractor

RSocket metadata có thể chứa routing, authentication, tracing hoặc thông tin theo dõi request. Với composite metadata, mỗi entry có MIME type riêng. Spring có thể trích xuất một loại metadata thành header để handler đọc bằng @Header.

Ví dụ, ứng dụng có metadata trace riêng:

~~~java
record TraceContext(String traceId, String source) {}

@Configuration
class RSocketMetadataConfiguration {

    static final MimeType TRACE_MIME =
        MimeType.valueOf("application/vnd.example.trace+json");

    @Bean
    RSocketStrategies rSocketStrategies(ObjectMapper objectMapper) {
        return RSocketStrategies.builder()
            .encoders(encoders ->
                encoders.add(new Jackson2JsonEncoder(objectMapper)))
            .decoders(decoders ->
                decoders.add(new Jackson2JsonDecoder(objectMapper)))
            .metadataExtractorRegistry(registry ->
                registry.metadataToExtract(
                    TRACE_MIME,
                    TraceContext.class,
                    "trace"
                ))
            .build();
    }
}
~~~

Khi client gửi metadata với MIME type TRACE_MIME, extractor giải mã entry đó thành TraceContext và đưa vào header có tên trace. Handler có thể nhận giá trị này:

~~~java
@MessageMapping("sensor.status")
Mono<DeviceStatus> status(
        @Payload SensorQuery query,
        @Header("trace") TraceContext traceContext) {
    log.debug("traceId={}", traceContext.traceId());
    return sensorService.findStatus(query.sensorId());
}
~~~

Đây là metadata do ứng dụng định nghĩa. Tên MIME type phải được thống nhất giữa client và server; nếu metadata mang thông tin xác thực, server vẫn phải xác thực và phân quyền dựa trên dữ liệu đã kiểm tra. Không xem một userId, tenantId hoặc trace value do client gửi là bằng chứng danh tính.

## 3. RSocketMessageHandler: ánh xạ message tới handler method

RSocketMessageHandler là thành phần của Spring Messaging dùng để xử lý message RSocket theo mô hình annotation. Nó tìm phương thức phù hợp dựa trên route và các annotation như @MessageMapping, sau đó dùng RSocketStrategies để giải mã payload, metadata và mã hóa kết quả.

### Khai báo bean và gắn RSocketStrategies

~~~java
@Configuration
class RSocketHandlerConfiguration {

    @Bean
    RSocketMessageHandler rSocketMessageHandler(
            RSocketStrategies strategies) {
        RSocketMessageHandler handler = new RSocketMessageHandler();
        handler.setRSocketStrategies(strategies);
        return handler;
    }
}
~~~

Khi tự tạo handler, cần gắn đúng RSocketStrategies để codec và metadata extractor mà server sử dụng trùng với cấu hình đã định nghĩa. Nếu không, client có thể mã hóa được DTO nhưng handler không có decoder tương ứng.

Trong Spring Boot, auto-configuration thường cung cấp RSocketMessageHandler mặc định khi có RSocket server. Khi khai báo bean tùy chỉnh, cấu hình tự động có điều kiện sẽ lùi lại cho bean do ứng dụng cung cấp. Hãy bảo đảm bean tùy chỉnh vẫn được cấu hình đầy đủ và được server bootstrap sử dụng.

### Viết handler bằng @MessageMapping

Ví dụ controller xử lý request-response và request-stream:

~~~java
@Controller
class SensorRSocketController {

    private final SensorService sensorService;

    SensorRSocketController(SensorService sensorService) {
        this.sensorService = sensorService;
    }

    @MessageMapping("sensor.status")
    Mono<DeviceStatus> status(@Payload SensorQuery query) {
        return sensorService.findStatus(query.sensorId());
    }

    @MessageMapping("sensor.readings")
    Flux<Reading> readings(@Payload SensorQuery query) {
        return sensorService.readings(query.sensorId());
    }
}
~~~

@MessageMapping khai báo route mà client gọi qua RSocketRequester.route(...). Tham số @Payload nhận data đã được decoder chuyển thành DTO. Kiểu trả về Mono hoặc Flux thể hiện response đơn lẻ hoặc luồng nhiều response.

Nếu route cần metadata, có thể nhận thêm header đã được trích xuất:

~~~java
@MessageMapping("sensor.status")
Mono<DeviceStatus> status(
        @Payload SensorQuery query,
        @Header("trace") TraceContext trace) {
    return sensorService.findStatus(query.sensorId())
        .doOnSuccess(result ->
            log.debug("Handled trace {}", trace.traceId()));
}
~~~

Trong thực tế, cần xử lý trường hợp Mono.empty(), lỗi nghiệp vụ, timeout và quyền truy cập theo hợp đồng route. Tránh ghi metadata nhạy cảm vào log.

### RSocketMessageHandler không phải transport server

Handler chỉ xử lý message sau khi RSocket runtime nhận được chúng. Nó không tự mở TCP port hoặc WebSocket endpoint. Với Spring Boot, server bootstrap có thể sử dụng handler cùng các thuộc tính spring.rsocket.server.*. Nếu dùng Spring Framework mà không có Boot, ứng dụng phải tự tạo RSocketServer, cung cấp handler.responder() làm SocketAcceptor và bind một ServerTransport.

Không tạo thêm một server độc lập nếu Boot đã quản lý server trên cùng port. Hãy chọn một nơi sở hữu việc bind transport để tránh xung đột cổng và lifecycle.

## 4. RSocketRequester.Builder: cấu hình client requester

RSocketRequester.Builder là builder dùng để tạo RSocketRequester. Builder có thể cấu hình:

- RSocketStrategies dùng để encode/decode.
- Data MIME type và metadata MIME type.
- SETUP route, setup data hoặc setup metadata nếu ứng dụng cần.
- Transport TCP, WebSocket hoặc một ClientTransport khác.
- Các tùy chọn kết nối và xử lý interaction.

### Tạo builder bean dùng chung chiến lược

~~~java
@Configuration
class RSocketClientConfiguration {

    @Bean
    @Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
    RSocketRequester.Builder rSocketRequesterBuilder(
            RSocketStrategies strategies) {
        return RSocketRequester.builder()
            .rsocketStrategies(strategies)
            .dataMimeType(MimeTypeUtils.APPLICATION_JSON)
            .metadataMimeType(
                MimeType.valueOf(
                    "message/x.rsocket.composite-metadata.v0"
                )
            );
    }
}
~~~

Builder là đối tượng có trạng thái cấu hình. Prototype scope tạo builder mới cho mỗi lần inject, tránh việc một component thay đổi route, MIME type hoặc tùy chọn của builder làm ảnh hưởng component khác. Nếu Spring Boot đã cung cấp builder phù hợp, chỉ khai báo bean riêng khi thật sự cần thay đổi cấu hình mặc định; không tạo hai bean cùng loại mà không có quy tắc phân giải rõ ràng.

metadataMimeType trong ví dụ chọn composite metadata để có thể mang nhiều metadata entry, chẳng hạn routing và trace. Nếu ứng dụng chỉ dùng metadata đơn giản, hãy chọn định dạng phù hợp với hợp đồng và khả năng của peer.

### Kết nối TCP

Một client có thể thiết lập kết nối tới RSocket server qua TCP:

~~~java
RSocketRequester requester = builder
    .connectTcp("localhost", 7000)
    .block();
~~~

connectTcp trả về Mono<RSocketRequester>. Ví dụ dùng block() ở ranh giới khởi tạo để minh họa một requester đã kết nối. Không gọi block() trên event loop hoặc trong controller reactive. Với ứng dụng reactive, có thể giữ publisher kết nối và compose các request sau khi kết nối hoàn tất.

### Kết nối WebSocket

Với WebSocket, client chỉ định URI endpoint:

~~~java
Mono<RSocketRequester> requesterMono = builder
    .connectWebSocket(URI.create("ws://localhost:8080/rsocket"));
~~~

URI và mapping path phải khớp cấu hình server. Khi dùng TLS, sử dụng wss:// và cấu hình chứng thư, proxy hoặc load balancer phù hợp. WebSocket là transport; các interaction model RSocket vẫn được giữ nguyên.

### Gửi request qua requester

Sau khi có requester đã kết nối, client có thể gọi route và gửi DTO:

~~~java
Mono<DeviceStatus> status = requester
    .route("sensor.status")
    .data(new SensorQuery("sensor-01"))
    .retrieveMono(DeviceStatus.class);
~~~

Request-stream dùng retrieveFlux:

~~~java
Flux<Reading> readings = requester
    .route("sensor.readings")
    .data(new SensorQuery("sensor-01"))
    .retrieveFlux(Reading.class);
~~~

Nếu cần gửi metadata trace:

~~~java
TraceContext trace = new TraceContext(
    "trace-7f21",
    "dashboard"
);

Mono<DeviceStatus> status = requester
    .route("sensor.status")
    .metadata(trace, RSocketMetadataConfiguration.TRACE_MIME)
    .data(new SensorQuery("sensor-01"))
    .retrieveMono(DeviceStatus.class);
~~~

Metadata MIME type phải được server đăng ký trong metadata extractor. Client và server cần thống nhất tên header, kiểu dữ liệu và MIME type.

### Quản lý vòng đời requester

Requester thường đại diện cho một kết nối được tái sử dụng cho nhiều request. Không nên tạo kết nối mới cho từng message nếu ứng dụng cần một session lâu dài và có thể tái sử dụng. Hãy tạo requester ở tầng quản lý kết nối, theo dõi trạng thái kết nối và đóng RSocket khi ứng dụng shutdown hoặc khi requester không còn được dùng.

Nếu kết nối được tạo bằng connectTcp hoặc connectWebSocket, publisher kết nối có thể được subscribe nhiều lần. Nếu muốn chia sẻ một kết nối giữa nhiều request, hãy giữ một requester đã kết nối hoặc chia sẻ kết quả kết nối theo lifecycle có kiểm soát; tránh vô tình mở nhiều kết nối chỉ vì cùng một Mono được subscribe lặp lại.

## 5. Kết hợp cấu hình với Spring Boot auto-configuration

Spring Boot có thể tự cấu hình RSocket server và một số bean nền tảng khi có dependency phù hợp. Việc tự cấu hình nên bổ sung đúng phần ứng dụng cần thay đổi.

### Cấu hình transport server bằng application.yml

Ví dụ TCP server:

~~~yaml
spring:
  rsocket:
    server:
      transport: tcp
      port: 7000
~~~

Ví dụ WebSocket server:

~~~yaml
spring:
  rsocket:
    server:
      transport: websocket
      mapping-path: /rsocket
      port: 8080
~~~

Các thuộc tính có thể khác nhau theo dòng Spring Boot đang dùng; hãy đối chiếu với phiên bản dependency management của dự án. Với TCP, client kết nối tới host và port. Với WebSocket, client dùng URI chứa host, port và mapping path.

Khi Boot quản lý server, Boot tạo bootstrap và bind transport theo cấu hình. RSocketMessageHandler được dùng để xử lý các route annotation. Nếu ứng dụng khai báo handler tùy chỉnh, hãy cấu hình strategies và kiểm tra rằng bean này được dùng trong server context.

### Bean nào nên tự khai báo?

| Thành phần | Khi nào nên tự khai báo |
|---|---|
| RSocketStrategies | Cần codec, ObjectMapper, metadata extractor hoặc route matcher riêng |
| RSocketMessageHandler | Cần handler tùy chỉnh và muốn gắn strategies cụ thể |
| RSocketRequester.Builder | Cần mặc định MIME type, strategies hoặc setup metadata cho client |
| RSocketRequester | Cần một kết nối client dùng chung tới endpoint cụ thể |

Nếu auto-configuration đã tạo bean mặc định, khai báo một bean cùng kiểu có thể khiến cấu hình tự động lùi lại hoặc phát sinh nhiều bean cạnh tranh. Dùng @ConditionalOnMissingBean trong cấu hình thư viện dùng chung; với ứng dụng, thường chỉ cần khai báo bean tùy chỉnh và xác nhận bean mặc định đã back off.

Không nên tự tạo RSocketServer và bind cùng cổng nếu Boot đã khởi động server. Nếu cần tự kiểm soát toàn bộ transport lifecycle, hãy tắt hoặc loại cấu hình server tự động tương ứng và để một thành phần duy nhất chịu trách nhiệm bind.

## 6. Ví dụ cấu hình tổng hợp

Một cấu hình tối giản có thể đặt strategies, message handler và requester builder trong cùng một lớp cấu hình. Trong dự án lớn, có thể tách cấu hình server và client để dễ quản lý.

~~~java
@Configuration
class RSocketApplicationConfiguration {

    @Bean
    RSocketStrategies rSocketStrategies(ObjectMapper objectMapper) {
        return RSocketStrategies.builder()
            .encoders(encoders ->
                encoders.add(new Jackson2JsonEncoder(objectMapper)))
            .decoders(decoders ->
                decoders.add(new Jackson2JsonDecoder(objectMapper)))
            .build();
    }

    @Bean
    RSocketMessageHandler rSocketMessageHandler(
            RSocketStrategies strategies) {
        RSocketMessageHandler handler = new RSocketMessageHandler();
        handler.setRSocketStrategies(strategies);
        return handler;
    }

    @Bean
    @Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
    RSocketRequester.Builder rSocketRequesterBuilder(
            RSocketStrategies strategies) {
        return RSocketRequester.builder()
            .rsocketStrategies(strategies)
            .dataMimeType(MimeTypeUtils.APPLICATION_JSON)
            .metadataMimeType(
                MimeType.valueOf(
                    "message/x.rsocket.composite-metadata.v0"
                )
            );
    }
}
~~~

Controller server:

~~~java
@Controller
class DeviceController {

    private final DeviceService deviceService;

    DeviceController(DeviceService deviceService) {
        this.deviceService = deviceService;
    }

    @MessageMapping("device.status")
    Mono<DeviceStatus> status(@Payload DeviceQuery query) {
        return deviceService.findStatus(query.deviceId());
    }

    @MessageMapping("device.events")
    Flux<DeviceEvent> events(@Payload DeviceQuery query) {
        return deviceService.events(query.deviceId());
    }
}
~~~

Client component có thể nhận builder prototype và kết nối ở ranh giới lifecycle:

~~~java
@Component
class DeviceRSocketClient {

    private final RSocketRequester requester;

    DeviceRSocketClient(RSocketRequester.Builder builder) {
        this.requester = builder
            .connectTcp("localhost", 7000)
            .block();
    }

    Mono<DeviceStatus> status(String deviceId) {
        return requester
            .route("device.status")
            .data(new DeviceQuery(deviceId))
            .retrieveMono(DeviceStatus.class);
    }

    Flux<DeviceEvent> events(String deviceId) {
        return requester
            .route("device.events")
            .data(new DeviceQuery(deviceId))
            .retrieveFlux(DeviceEvent.class);
    }
}
~~~

Đoạn client dùng kết nối được tạo một lần trong constructor để minh họa tái sử dụng requester. Trong ứng dụng thực tế, nên xử lý lỗi khởi tạo kết nối, timeout, reconnect và đóng connection khi context shutdown. Nếu không muốn chặn startup thread, hãy quản lý Mono<RSocketRequester> theo lifecycle reactive và chia sẻ kết quả kết nối một cách có chủ đích.

Ví dụ trên giả định các DTO, service, ObjectMapper và dependency RSocket đã được cấu hình. Các import của RSocketMessageHandler nằm trong package annotation support của Spring Messaging; hãy dùng đúng package theo phiên bản Spring Framework đang triển khai.

Các import Spring chính thường dùng trong cấu hình tổng hợp:

~~~java
import org.springframework.beans.factory.config.ConfigurableBeanFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Scope;
import org.springframework.http.codec.json.Jackson2JsonDecoder;
import org.springframework.http.codec.json.Jackson2JsonEncoder;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.messaging.rsocket.RSocketStrategies;
import org.springframework.messaging.rsocket.annotation.support.RSocketMessageHandler;
import org.springframework.stereotype.Component;
import org.springframework.stereotype.Controller;
import org.springframework.util.MimeType;
import org.springframework.util.MimeTypeUtils;
~~~

Các import cho DTO, service, logger và ObjectMapper phụ thuộc vào package của ứng dụng. Các snippet cấu hình ở những mục trước minh họa từng phần riêng; khi ghép vào một project, hãy giữ một bean RSocketStrategies, một handler server và một builder bean với scope phù hợp.

## 7. Kiểm thử cấu hình

Không nên chỉ kiểm tra rằng Spring context khởi động được. Cấu hình cần được kiểm tra ở cả cấp codec, route, metadata và transport.

| Hạng mục | Nội dung cần kiểm tra |
|---|---|
| Bean wiring | Context có một RSocketStrategies, handler và requester builder phù hợp |
| Codec | DTO được encode/decode đúng với data MIME type đã chọn |
| Metadata | Metadata entry được trích xuất thành header đúng tên và kiểu |
| Routing | @MessageMapping nhận đúng route từ requester |
| Interaction | Request-response và request-stream trả đúng hình dạng dữ liệu |
| Transport | Client kết nối được qua TCP hoặc WebSocket theo cấu hình |
| Lifecycle | Requester được tái sử dụng và đóng khi ứng dụng shutdown |
| Error | Lỗi decode, route không tồn tại và kết nối bị ngắt được xử lý rõ ràng |

Một bài integration test nên khởi động Spring Boot context với transport thử nghiệm, kết nối bằng RSocketRequester và gọi ít nhất một route. Test metadata nên gửi entry có MIME type riêng rồi xác nhận handler nhận đúng @Header. Test codec nên dùng DTO có trường thời gian hoặc enum để phát hiện khác biệt cấu hình Jackson.

Khi test stream, cần xác nhận cancellation được truyền tới publisher server và tài nguyên upstream được giải phóng. Với lỗi transport, cần xác nhận client nhận lỗi phù hợp và không để một kết nối hỏng được dùng vô thời hạn.

## 8. Các lỗi cấu hình thường gặp

| Lỗi | Triệu chứng | Cách khắc phục |
|---|---|---|
| Client và server dùng data MIME type khác nhau | Decode lỗi hoặc payload không đọc được | Đồng bộ MIME type và codec |
| Chỉ đăng ký encoder mà thiếu decoder | Gửi được request nhưng không đọc được response | Đăng ký cả hai chiều theo nhu cầu |
| Handler dùng strategies khác client | DTO hoặc metadata giải mã không thống nhất | Dùng cùng cấu hình codec và hợp đồng |
| Quên gắn strategies vào handler tùy chỉnh | Route không giải mã được DTO theo codec mong muốn | Gọi setRSocketStrategies |
| Metadata MIME type không phải composite khi gửi nhiều entry | Metadata routing/custom không được giải mã như mong muốn | Chọn composite metadata và đăng ký extractor |
| Extractor không đăng ký MIME type custom | Handler không nhận được header mong đợi | Dùng metadataToExtract với MIME và kiểu dữ liệu chính xác |
| Dùng builder singleton có trạng thái mutable | Cấu hình của client này ảnh hưởng client khác | Dùng builder prototype hoặc tạo builder riêng |
| Tạo requester mới cho từng message | Tăng số kết nối và chi phí SETUP | Tái sử dụng requester theo lifecycle |
| Gọi block() trên event loop | Làm nghẽn xử lý reactive | Compose publisher hoặc chỉ block ở ranh giới khởi tạo imperative |
| Tự bind server khi Boot đã bind | Lỗi port đang được sử dụng | Chỉ để một thành phần quản lý server lifecycle |
| Dùng ws:// khi endpoint yêu cầu TLS | Handshake hoặc kết nối thất bại | Dùng wss:// và cấu hình TLS/proxy |
| Tin metadata do client gửi | Có thể sai tenant hoặc danh tính | Xác thực, phân quyền và kiểm tra metadata |

## Kết luận

RSocketStrategies, RSocketMessageHandler và RSocketRequester.Builder đảm nhiệm ba phần khác nhau nhưng cần thống nhất cấu hình. Strategies quyết định cách mã hóa, giải mã và trích xuất metadata; message handler ánh xạ message tới phương thức xử lý; requester builder tạo client với MIME type, metadata và transport phù hợp.

Trong Spring Boot, hãy tận dụng auto-configuration cho server và chỉ thay thế bean khi có nhu cầu rõ ràng. Khi tùy chỉnh, dùng chung chiến lược codec giữa handler và requester, chọn data/metadata MIME type nhất quán, quản lý builder có trạng thái theo scope phù hợp và tái sử dụng requester theo lifecycle. Cuối cùng, kiểm thử cả DTO, metadata, route, transport và cancellation để cấu hình hoạt động đúng trong giao tiếp realtime.
