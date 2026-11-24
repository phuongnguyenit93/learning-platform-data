# Khai báo setupRoute, setupData và setupMetadata

Trong RSocket, một connection bắt đầu bằng frame **SETUP**. Frame này mang các tham số khởi tạo session, MIME type cho data và metadata, cùng data hoặc metadata ban đầu nếu requester có cung cấp. Spring Framework cho phép cấu hình phần nội dung đó qua ba phương thức của **RSocketRequester.Builder**: **setupRoute**, **setupData** và **setupMetadata**.

Ba phương thức này phục vụ ngữ cảnh cấp connection. Chúng hữu ích khi client cần giới thiệu loại kết nối, gửi thông tin khởi tạo, cung cấp credential hoặc chọn một handler xử lý sự kiện kết nối ở phía server. Chúng không thay thế route, data và metadata của từng request sau khi session đã được thiết lập.

Bài học đặt các API này trong bối cảnh RSocket realtime qua TCP hoặc WebSocket, với ví dụ Java và Spring Messaging. Trọng tâm là hiểu chính xác thông tin nào thuộc SETUP, cách mã hóa MIME type và cách server nhận dữ liệu bằng **@ConnectMapping**.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích vai trò của SETUP frame trong vòng đời RSocket connection.
- Phân biệt setupRoute, setupData và setupMetadata.
- Cấu hình data MIME type và metadata MIME type cho connection.
- Dùng composite metadata khi kết hợp route với nhiều metadata entry.
- Gửi thông tin khởi tạo bằng RSocketRequester.Builder.
- Nhận setup data, route và metadata ở server bằng @ConnectMapping.
- Cấu hình metadata extractor và codec tương ứng.
- Phân biệt metadata cấp connection với metadata của từng request.
- Bảo vệ credential và quản lý vòng đời requester.

## 1. SETUP frame và nội dung khởi tạo connection

Requester thiết lập transport trước, sau đó gửi RSocket SETUP frame để hai phía thống nhất các tham số của session. SETUP có thể khai báo:

- Data MIME type dùng để diễn giải data của connection.
- Metadata MIME type dùng để diễn giải metadata của connection.
- Setup data tùy chọn.
- Setup metadata tùy chọn, có thể chứa route hoặc các metadata entry khác.

Luồng khởi tạo:

~~~mermaid
sequenceDiagram
    participant C as RSocketRequester
    participant S as RSocket server
    participant H as @ConnectMapping
    C->>S: Mở TCP hoặc WebSocket transport
    C->>S: SETUP (MIME types, setup data, setup metadata)
    S->>H: Dispatch sự kiện kết nối và nội dung SETUP
    H-->>S: Hoàn tất xử lý Mono<Void>
    S-->>C: Connection sẵn sàng
    C->>S: REQUEST_RESPONSE / REQUEST_STREAM / ...
~~~

Setup data và setup metadata đều là tùy chọn. Nếu không có dữ liệu cấp connection cần gửi, requester có thể bỏ qua chúng. Không cần tạo một object rỗng chỉ để lấp đầy SETUP frame.

### 1.1. MIME type có phạm vi connection

Data MIME type và metadata MIME type được khai báo trong SETUP và áp dụng cho các message trên connection đó. Điều này giúp hai phía biết cách giải mã data và metadata mà không phải thương lượng lại ở mỗi request.

MIME type của data và metadata là hai cấu hình độc lập:

| Cấu hình | Dùng để diễn giải |
|---|---|
| dataMimeType | Data trong SETUP và payload của các request/response |
| metadataMimeType | Metadata trong SETUP và payload của các request/response |

Với data, Spring có thể suy ra MIME type từ decoder đã đăng ký. Với metadata, mặc định là composite metadata để có thể mang nhiều entry với MIME type riêng. Thông thường không cần thay đổi hai giá trị mặc định nếu client và server dùng cùng bộ codec.

## 2. Phân biệt ba phương thức

Ba phương thức cấu hình các phần khác nhau của SETUP:

| Phương thức | Nội dung | Ví dụ |
|---|---|---|
| setupRoute(route, vars...) | Route trong metadata của SETUP | client.connect.{tenant} |
| setupData(data) | Data ban đầu của connection | Tên ứng dụng, phiên bản client |
| setupMetadata(value, mimeType) | Một metadata entry ban đầu | Bearer token, client context |

### 2.1. setupRoute: route cho sự kiện kết nối

setupRoute thêm route vào metadata của SETUP frame. Ở server, route này có thể được dùng để chọn @ConnectMapping tương ứng. Ví dụ:

~~~java
.setupRoute("client.connect.{tenant}", tenantId)
~~~

Route này mô tả loại connection hoặc nhóm xử lý lúc kết nối. Nó không trở thành route mặc định cho mọi request sau đó. Mỗi request nghiệp vụ vẫn cần route riêng qua requester.route(...).

### 2.2. setupData: data ban đầu

setupData đưa một giá trị vào data section của SETUP:

~~~java
.setupData("client=dashboard;version=2.4")
~~~

Thông tin phù hợp có thể là tên ứng dụng, phiên bản client hoặc cấu hình khởi tạo không nhạy cảm. Server nhận giá trị này trong @ConnectMapping thông qua tham số payload.

Không dùng setup data làm nơi gửi truy vấn nghiệp vụ của từng thao tác. Dữ liệu thay đổi theo request phải nằm trong payload của request tương ứng.

### 2.3. setupMetadata: metadata ban đầu

setupMetadata thêm một metadata entry vào SETUP cùng MIME type:

~~~java
.setupMetadata(accessToken, BEARER_MIME_TYPE)
~~~

Metadata phù hợp với thông tin cấp connection như credential, client capability hoặc context được xác định khi mở session. Giá trị phải có encoder tương thích ở client và decoder/extractor tương ứng ở server.

Không gửi trace context của từng request trong setup metadata nếu mỗi request có trace riêng. Thông tin chỉ có ý nghĩa ở một interaction nên được gửi bằng metadata trên request đó.

## 3. Cấu hình RSocketRequester.Builder

Ví dụ sau mở connection TCP và gửi đủ route, data cùng hai metadata entry:

~~~java
import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.util.MimeTypeUtils;
import org.springframework.util.MimeType;
import org.springframework.security.rsocket.metadata.BearerTokenMetadata;

public class DeviceConnectionFactory {

    private static final MimeType COMPOSITE_METADATA =
            MimeType.valueOf(
                    "message/x.rsocket.composite-metadata.v0");

    private static final MimeType CLIENT_CONTEXT_MIME_TYPE =
            MimeType.valueOf(
                    "message/vnd.acme.client-context.v1");

    public RSocketRequester connect(
            String host,
            int port,
            String tenantId,
            String accessToken,
            String clientContext) {

        return RSocketRequester.builder()
                .dataMimeType(MimeTypeUtils.TEXT_PLAIN)
                .metadataMimeType(COMPOSITE_METADATA)
                .setupRoute("client.connect.{tenant}", tenantId)
                .setupData("client=dashboard;version=2.4")
                .setupMetadata(
                        new BearerTokenMetadata(accessToken),
                        BearerTokenMetadata.BEARER_AUTHENTICATION_MIME_TYPE)
                .setupMetadata(
                        clientContext,
                        CLIENT_CONTEXT_MIME_TYPE)
                .tcp(host, port);
    }
}
~~~

Ví dụ dùng chuỗi làm setup data và client context để dễ theo dõi. Nếu dùng BearerTokenMetadata, hãy thêm Spring Security RSocket tương thích vào dependency và cấu hình cơ chế xác thực ở server.

Các điểm cần chú ý:

1. dataMimeType được đặt là text/plain vì ví dụ gửi chuỗi.
2. metadataMimeType là composite metadata.
3. setupRoute thêm route cho SETUP.
4. setupData thêm data ban đầu.
5. Hai lần gọi setupMetadata thêm hai entry độc lập.
6. tcp(host, port) tạo requester sử dụng TCP.

RSocketRequester có thể được tạo trước khi transport thực sự kết nối. Connection được thiết lập khi ứng dụng bắt đầu gửi request; requester sử dụng connection dùng chung cho các request tiếp theo theo vòng đời của nó.

### 3.1. Kết nối bằng WebSocket

Cùng cấu hình setup có thể dùng WebSocket thay cho TCP:

~~~java
RSocketRequester requester = RSocketRequester.builder()
        .setupRoute("client.connect.{tenant}", tenantId)
        .setupData("client=dashboard;version=2.4")
        .setupMetadata(accessToken, BEARER_MIME_TYPE)
        .websocket(URI.create(
                "https://api.example.com/rsocket"));
~~~

Trong Spring Framework hiện hành, phương thức builder là websocket(URI). URI HTTP/HTTPS được dùng làm địa chỉ WebSocket endpoint; HTTPS tương ứng với WebSocket bảo mật ở transport.

Transport chỉ quyết định cách kết nối. Ý nghĩa của setupRoute, setupData và setupMetadata không thay đổi giữa TCP và WebSocket.

## 4. setupRoute và @ConnectMapping ở server

@ConnectMapping xử lý SETUP frame khi connection bắt đầu. Nếu khai báo route pattern, Spring có thể chọn handler dựa trên route được gửi qua setupRoute.

Ví dụ:

~~~java
@Controller
public class ConnectionController {

    private final ConnectionRegistry connectionRegistry;

    public ConnectionController(
            ConnectionRegistry connectionRegistry) {
        this.connectionRegistry = connectionRegistry;
    }

    @ConnectMapping("client.connect.{tenant}")
    public Mono<Void> onConnect(
            @DestinationVariable("tenant") String tenant,
            @Payload String setupData) {

        return connectionRegistry.register(
                tenant,
                setupData);
    }
}
~~~

Khi client gửi setupRoute("client.connect.{tenant}", tenantId), Spring dispatch sự kiện setup đến handler có route pattern tương ứng. @DestinationVariable nhận giá trị tenant đã được tách từ route, còn @Payload nhận setup data.

Route chỉ là dữ liệu định tuyến do client gửi. Không coi tenant trong route là bằng chứng client được phép truy cập tenant đó. Server cần xác thực credential và kiểm tra quyền trước khi đăng ký hoặc cấp tài nguyên cho connection.

### 4.1. Handler không có route pattern

Nếu không khai báo route pattern, @ConnectMapping có thể nhận mọi connection:

~~~java
@ConnectMapping
public Mono<Void> onAnyConnection(
        @Payload(required = false) String setupData) {

    return connectionRegistry.recordSetup(setupData);
}
~~~

Có thể dùng handler tổng quát để ghi nhận kết nối hoặc áp dụng chính sách chung. Nếu ứng dụng có nhiều loại client, route pattern giúp tách các nhóm setup theo mục đích.

### 4.2. Quy tắc trả về của @ConnectMapping

@ConnectMapping là handler ở cấp connection, không phải một request-response endpoint thông thường:

- Method phải trả về void hoặc Mono<Void>.
- Method không trả response payload.
- Nếu xử lý setup phát lỗi, connection mới có thể bị từ chối.
- Việc xử lý setup phải hoàn tất trước khi các request trên connection bắt đầu.

Không giữ @ConnectMapping chờ một request khác được gửi qua chính connection vừa thiết lập. Nếu server cần chủ động gửi request đến client sau khi kết nối, hãy khởi chạy công việc đó độc lập sau khi setup handler hoàn tất.

## 5. Nhận setup metadata

Metadata trong SETUP có thể chứa nhiều entry. Spring dùng RSocketStrategies và MetadataExtractor để giải mã metadata thành các giá trị có tên, sau đó handler có thể nhận chúng qua @Header hoặc @Headers.

Ví dụ đăng ký một metadata MIME type tùy chỉnh:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.rsocket.RSocketStrategies;
import org.springframework.util.MimeType;

@Configuration
public class RSocketMetadataConfiguration {

    static final MimeType CLIENT_CONTEXT_MIME_TYPE =
            MimeType.valueOf(
                    "message/vnd.acme.client-context.v1");

    @Bean
    RSocketStrategies rSocketStrategies() {
        return RSocketStrategies.builder()
                .metadataExtractorRegistry(registry ->
                        registry.metadataToExtract(
                                CLIENT_CONTEXT_MIME_TYPE,
                                String.class,
                                "clientContext"))
                .build();
    }
}
~~~

Khi đó @ConnectMapping có thể nhận metadata đã giải mã:

~~~java
@ConnectMapping("client.connect.{tenant}")
public Mono<Void> onConnect(
        @DestinationVariable("tenant") String tenant,
        @Payload String setupData,
        @Header("clientContext") String clientContext) {

    return connectionRegistry.register(
            tenant,
            setupData,
            clientContext);
}
~~~

Tên clientContext là tên header do ứng dụng đăng ký trong metadata extractor. MIME type và kiểu dữ liệu phải khớp với giá trị mà requester gửi. Nếu metadata là object phức tạp, cần đăng ký encoder/decoder phù hợp thay vì giả định mọi kiểu Java đều tự serialize được.

### 5.1. Metadata route có hỗ trợ sẵn

Spring RSocket hỗ trợ routing metadata message/x.rsocket.routing.v0 và composite metadata theo mặc định. Route từ setupRoute có thể được dùng cho việc dispatch @ConnectMapping.

Với metadata MIME type tùy chỉnh, ứng dụng phải đăng ký cách giải mã. Metadata không được đăng ký extractor có thể không xuất hiện dưới dạng header trong handler.

## 6. Composite metadata và thứ tự cấu hình

Mặc định, metadata MIME type của RSocketRequester là:

~~~text
message/x.rsocket.composite-metadata.v0
~~~

Composite metadata cho phép một metadata section chứa nhiều entry, mỗi entry có MIME type riêng. Ví dụ:

| Entry | MIME type | Giá trị |
|---|---|---|
| Routing | message/x.rsocket.routing.v0 | client.connect.tenant-42 |
| Authentication | message/x.rsocket.authentication.bearer.v0 | Bearer token |
| Client context | message/vnd.acme.client-context.v1 | dashboard;version=2.4 |

Composite metadata cần được dùng khi:

- Gọi setupMetadata nhiều lần.
- Kết hợp setupRoute với setupMetadata.
- Cần nhiều loại metadata độc lập trong cùng SETUP frame.

Nếu đặt metadata MIME type thành một MIME type đơn tùy chỉnh, Spring sẽ giả định route (nếu có) cũng được mã hóa theo MIME type đó. Khi cần route chuẩn cùng các entry khác, giữ composite metadata hoặc cấu hình định dạng mà cả hai phía hiểu.

### 6.1. Tránh trộn nhiều định dạng không tương thích

Client và server phải thống nhất:

- Metadata section có phải composite metadata hay không.
- MIME type của từng entry.
- Kiểu dữ liệu sau giải mã.
- Codec dùng để encode/decode.
- Tên header được metadata extractor tạo ra.

Một client gửi chuỗi theo MIME type tùy chỉnh trong khi server chờ JSON object sẽ dẫn đến lỗi giải mã hoặc metadata không được ánh xạ như mong đợi.

## 7. Codec cho setup data và metadata

setupData được encode theo data MIME type đã cấu hình. setupMetadata dùng MIME type được truyền ở lời gọi và encoder phù hợp. Do đó, khai báo builder thôi chưa đủ nếu ứng dụng gửi kiểu dữ liệu tùy chỉnh.

Spring RSocket có RSocketStrategies để quản lý encoder, decoder, route matcher và metadata extractor. Các codec cơ bản hỗ trợ những kiểu như String, byte array và ByteBuffer. Với DTO hoặc record, cần thêm codec tương ứng, chẳng hạn Jackson JSON hoặc CBOR khi dependency hỗ trợ.

Ví dụ setup data dạng String không cần định nghĩa DTO riêng:

~~~java
.dataMimeType(MimeTypeUtils.TEXT_PLAIN)
.setupData("client=dashboard;version=2.4")
~~~

Nếu dùng một record:

~~~java
public record ClientSetup(
        String clientName,
        String version,
        String locale) {
}
~~~

Hãy đăng ký encoder/decoder tương thích trong RSocketStrategies ở requester và server, sau đó dùng:

~~~java
.setupData(new ClientSetup(
        "dashboard",
        "2.4",
        "vi-VN"))
~~~

Không serialize DTO thành JSON thủ công rồi lại để Spring serialize chuỗi JSON lần nữa nếu không có chủ đích. Chọn một biểu diễn dữ liệu và MIME type rõ ràng.

## 8. Setup metadata và bảo mật connection

Setup metadata thường được dùng cho thông tin bảo mật cấp connection, ví dụ bearer token. Tuy nhiên, việc gửi token trong SETUP không tự xác thực client. Server cần cấu hình Spring Security RSocket hoặc một authentication mechanism tương ứng để xác minh credential.

Ví dụ gửi bearer metadata:

~~~java
MimeType bearerMimeType =
        BearerTokenMetadata.BEARER_AUTHENTICATION_MIME_TYPE;

RSocketRequester requester = RSocketRequester.builder()
        .setupMetadata(
                new BearerTokenMetadata(accessToken),
                bearerMimeType)
        .tcp("localhost", 7000);
~~~

Ở server:

- Xác minh chữ ký hoặc tra cứu token theo cơ chế đã chọn.
- Kiểm tra issuer, audience, expiration và các claim cần thiết.
- Tạo Principal/Authentication đã xác thực.
- Dùng Principal để phân quyền route và tenant.
- Không dùng tenant, role hoặc user ID tự khai trong setup data làm nguồn cấp quyền.

Không ghi token vào log. Nếu cần truy vết connection, dùng một connection ID nội bộ hoặc fingerprint an toàn thay cho credential.

### 8.1. Metadata cấp connection không phải metadata của từng request

Setup metadata được gửi khi connection được thiết lập. Nếu token hết hạn hoặc bị thu hồi trong khi connection vẫn mở, việc gửi token mới trong một request không tự thay đổi setup metadata cũ.

Hệ thống cần có chính sách cho vòng đời credential:

- Giới hạn thời gian sống của connection.
- Đóng và thiết lập lại connection khi cần thay token.
- Hoặc dùng cơ chế xác thực theo request nếu mô hình bảo mật yêu cầu.

Với dữ liệu thay đổi theo từng thao tác như trace ID, correlation ID hoặc deadline, hãy dùng metadata trên request:

~~~java
requester.route("orders.find")
        .metadata(correlationId, CORRELATION_ID_MIME_TYPE)
        .data(new OrderQuery(orderId))
        .retrieveMono(Order.class);
~~~

## 9. Setup route không thay thế request route

Một lỗi thiết kế phổ biến là nghĩ setupRoute khai báo route mặc định cho mọi message. Trên thực tế:

| API | Thời điểm | Mục đích |
|---|---|---|
| setupRoute(...) | SETUP frame | Định tuyến sự kiện kết nối tới @ConnectMapping |
| route(...) | Mỗi request | Định tuyến request tới @MessageMapping |

Ví dụ:

~~~java
RSocketRequester requester = RSocketRequester.builder()
        .setupRoute("client.connect.{tenant}", tenantId)
        .setupData("dashboard;version=2.4")
        .tcp("localhost", 7000);

Mono<DeviceStatus> status = requester
        .route("devices.status")
        .data(new DeviceQuery("sensor-17"))
        .retrieveMono(DeviceStatus.class);
~~~

client.connect.tenant-42 dùng cho xử lý lúc mở connection. devices.status là route của request lấy trạng thái thiết bị. Hai route có vòng đời và mục đích khác nhau.

## 10. Vòng đời requester và thay đổi setup

Setup chỉ được gửi một lần khi tạo RSocket session. Vì vậy, các giá trị setup không thể được thay đổi bằng cách gọi lại setupData hoặc setupMetadata trên một requester đã được tạo.

Nếu ứng dụng cần thay đổi context cấp connection:

1. Tạo requester mới với setup data/metadata mới.
2. Thiết lập connection mới.
3. Chuyển các request mới sang requester mới.
4. Đóng requester cũ khi không còn interaction cần dùng.

Không tạo requester mới cho mỗi request thông thường. Một requester có thể phục vụ nhiều request đồng thời trên cùng connection. Chỉ tạo connection mới khi endpoint, danh tính hoặc context cấp connection thực sự thay đổi.

## 11. Kiểm thử setupRoute, setupData và setupMetadata

Một kiểm thử tích hợp nên xác nhận dữ liệu ở cả hai phía:

1. Khởi động RSocket server và đăng ký @ConnectMapping.
2. Tạo requester với setupRoute có route variable.
3. Gửi setupData và một hoặc nhiều setupMetadata entry.
4. Xác minh handler nhận đúng route variable và data.
5. Xác minh metadata extractor giải mã entry theo MIME type.
6. Gửi request nghiệp vụ bằng route(...) để chứng minh setupRoute không thay route của request.
7. Thử MIME type hoặc codec sai để quan sát lỗi setup.
8. Thử credential sai và xác minh connection bị từ chối theo security policy.

Ví dụ kiểm tra logic đăng ký connection ở cấp service:

~~~java
StepVerifier.create(
        connectionRegistry.register(
                "tenant-42",
                "client=dashboard;version=2.4",
                "desktop"))
        .verifyComplete();
~~~

Đây là unit test cho service được @ConnectMapping gọi. Integration test vẫn cần một RSocket requester thực sự để kiểm tra encoding, transport, SETUP frame và metadata extraction.

### 11.1. Các tình huống cần kiểm tra

| Tình huống | Kết quả mong đợi |
|---|---|
| Có setupRoute phù hợp | @ConnectMapping đúng route được gọi |
| Không có setupRoute | Handler tổng quát có thể xử lý connection |
| Setup data là String | Handler nhận đúng nội dung |
| Có nhiều setupMetadata entry | Composite metadata giải mã được từng entry |
| MIME type không có decoder | Metadata không giải mã được hoặc setup bị lỗi theo cấu hình |
| Credential không hợp lệ | Security layer từ chối connection |
| Setup handler phát lỗi | Connection mới bị từ chối |
| Request sau setup dùng route khác | @MessageMapping theo request route được gọi |

## 12. Lỗi thường gặp

### Dùng setupRoute thay cho route của request

setupRoute chỉ gắn route vào SETUP. Mỗi request vẫn cần route(...) nếu server định tuyến bằng route metadata.

### Dùng setupData cho dữ liệu nghiệp vụ thay đổi liên tục

Setup data có vòng đời connection. Query, command hoặc payload thay đổi theo thao tác phải được gửi trong request.

### Gọi setupMetadata nhiều lần nhưng không dùng composite metadata

Composite metadata là định dạng phù hợp để mang nhiều entry hoặc kết hợp route với metadata khác. Hãy giữ MIME type mặc định hoặc cấu hình tương thích ở cả hai phía.

### Đặt một MIME type đơn tùy chỉnh rồi vẫn gửi route chuẩn

Khi metadata MIME type không phải composite, route nếu có sẽ được giả định mã hóa theo MIME type đó. Điều này có thể khiến server không đọc được routing metadata chuẩn.

### Gửi DTO nhưng không đăng ký codec

RSocketStrategies cần encoder/decoder tương ứng. Kiểm tra data MIME type, metadata MIME type và codec trên cả client lẫn server.

### Tin tenant hoặc role trong setup payload

Setup route và data đều do client gửi. Chúng là đầu vào cần kiểm tra, không phải bằng chứng xác thực hoặc phân quyền.

### Giữ token setup quá lâu

Token trong SETUP gắn với session. Có chính sách hết hạn, thu hồi và tái tạo connection phù hợp với vòng đời credential.

### Làm @ConnectMapping chờ request trên chính connection đó

SETUP cần được xử lý xong trước khi request có thể bắt đầu. Handler chỉ thực hiện công việc connection-level rồi hoàn tất; khởi chạy giao tiếp tiếp theo độc lập.

## 13. Checklist triển khai

Trước khi dùng setup APIs trong production, hãy xác nhận:

1. setupRoute chỉ được dùng cho xử lý connection-level.
2. setupData chứa thông tin khởi tạo phù hợp, không chứa truy vấn nghiệp vụ thay đổi từng request.
3. setupMetadata có MIME type rõ ràng và codec tương thích.
4. dataMimeType và metadataMimeType được thống nhất giữa hai phía.
5. Composite metadata được dùng khi có nhiều entry hoặc kết hợp setupRoute với setupMetadata.
6. @ConnectMapping nhận đúng route, payload và metadata đã giải mã.
7. Handler setup trả về void hoặc Mono<Void> và không chờ request trên connection chưa hoàn tất setup.
8. Credential được xác minh bởi security layer.
9. Tenant context được kiểm tra quyền dựa trên Principal.
10. Token và secret không xuất hiện trong log.
11. Request nghiệp vụ vẫn dùng route/data/metadata riêng.
12. Có integration test cho SETUP frame và metadata extraction.

## 14. Tổng kết

setupRoute, setupData và setupMetadata là ba cách cấu hình nội dung của SETUP frame trong RSocketRequester.Builder. setupRoute cung cấp route cho sự kiện kết nối; setupData mang data ban đầu; setupMetadata thêm các entry metadata có MIME type riêng. Các giá trị này có phạm vi connection và được server tiếp nhận qua @ConnectMapping.

Khi kết hợp route với nhiều metadata entry, dùng composite metadata để giữ định dạng định tuyến và các entry độc lập. Cấu hình codec và MIME type nhất quán ở cả hai phía, xác minh credential trước khi tin context và dùng route(), data() cùng metadata() cho từng request nghiệp vụ. Thiết kế đúng ranh giới giữa setup và request giúp RSocket connection mang đủ ngữ cảnh khởi tạo mà vẫn giữ từng interaction rõ ràng.

## Tài liệu tham khảo

- [Spring Framework Reference — RSocketRequester và Connection Setup](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [RSocketRequester.Builder API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/rsocket/RSocketRequester.Builder.html)
