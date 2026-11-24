# Tiếp nhận SETUP và METADATA_PUSH bằng @ConnectMapping

Trong RSocket, một connection có vòng đời riêng bên cạnh các request và stream nghiệp vụ. Khi client mở connection, nó gửi frame SETUP để hai phía thống nhất các tham số ban đầu và có thể gửi kèm data hoặc metadata nhận diện client. Trong thời gian connection hoạt động, một phía còn có thể gửi METADATA_PUSH để thông báo metadata mới ở phạm vi toàn connection.

Spring Framework cung cấp annotation <code>@ConnectMapping</code> để tiếp nhận cả hai loại thông điệp connection-level này. Handler có thể đăng ký client vừa kết nối, kiểm tra thông tin thiết lập, cập nhật ngữ cảnh tenant hoặc nhận thay đổi metadata trong lúc phiên đang hoạt động. Đây là cơ chế xử lý vòng đời connection, khác với <code>@MessageMapping</code> vốn xử lý các tương tác request trên từng stream.

## 1. SETUP và METADATA_PUSH khác nhau như thế nào?

SETUP là frame đầu tiên client gửi khi tạo một RSocket connection mới. Frame này mang thông tin thiết lập giao thức như phiên bản, keepalive interval, lifetime, data MIME type và metadata MIME type. Client có thể đính kèm data, metadata hoặc cả hai để cung cấp thông tin ban đầu cho server.

METADATA_PUSH là frame connection-level có thể được gửi sau khi connection đã được thiết lập. Nó mang metadata mới mà không gắn với một request hoặc stream nghiệp vụ cụ thể. Hai phía có thể dùng nó để thông báo ngữ cảnh mới trong suốt vòng đời connection.

| Đặc điểm | SETUP | METADATA_PUSH |
| --- | --- | --- |
| Thời điểm | Khi bắt đầu connection | Sau khi connection đã được thiết lập |
| Mục đích | Khởi tạo session và cung cấp thông tin ban đầu | Cập nhật hoặc thông báo metadata ở phạm vi connection |
| Data | Có thể có data và metadata | Chỉ mang metadata |
| Route | Có thể có route trong metadata thiết lập | Có thể có route trong metadata push để chọn handler |
| Tần suất | Một lần cho mỗi connection mới | Có thể nhiều lần trong vòng đời connection |
| Phạm vi | Toàn connection | Toàn connection |
| Kiểu phản hồi | Không phải request-response nghiệp vụ | Không có response nghiệp vụ |

Một điểm quan trọng: SETUP không phải một request tới route thông thường. Nó thiết lập session trước khi các request nghiệp vụ bắt đầu. Tương tự, METADATA_PUSH không mở stream mới và không thay thế request-response.

## 2. @ConnectMapping xử lý những frame nào?

<code>@ConnectMapping</code> ánh xạ method tới frame SETUP ban đầu và các thông báo metadata push tiếp theo. Method hỗ trợ các kiểu tham số tương tự <code>@MessageMapping</code>, nhưng dữ liệu được lấy từ SETUP hoặc METADATA_PUSH.

Annotation có thể khai báo route pattern:

- <code>@ConnectMapping("client.connect")</code> chỉ nhận các connection setup hoặc metadata push có route khớp <code>client.connect</code>.
- <code>@ConnectMapping("client.context")</code> nhận metadata push có route <code>client.context</code>.
- <code>@ConnectMapping</code> không có pattern khớp với tất cả connection setup và metadata push.

Route được lấy từ routing metadata. Khi dùng Composite Metadata, route là một entry có MIME type <code>message/x.rsocket.routing.v0</code>; các entry metadata khác có thể mang tenant, client context hoặc tracing data.

Một controller có thể khai báo các handler riêng cho SETUP và METADATA_PUSH:

~~~java
@Controller
public class ConnectionLifecycleController {

    private final ClientRegistry clientRegistry;

    public ConnectionLifecycleController(ClientRegistry clientRegistry) {
        this.clientRegistry = clientRegistry;
    }

    @ConnectMapping("client.connect")
    Mono<Void> onConnect(
            @Payload ClientSetup setup,
            @Header("tenant") TenantMetadata tenant,
            RSocketRequester requester) {

        return clientRegistry.register(
            setup.clientId(),
            tenant.tenantId(),
            requester
        );
    }

    @ConnectMapping("client.context")
    Mono<Void> onMetadataPush(
            @Header("client-context") ClientContext context) {

        return clientRegistry.updateContext(context);
    }
}
~~~

Ví dụ minh họa hai route khác nhau. Handler đầu đọc payload thiết lập và metadata tenant; handler thứ hai nhận một metadata entry được gửi sau khi connection đã hoạt động. Các kiểu <code>ClientSetup</code>, <code>TenantMetadata</code>, <code>ClientContext</code> và <code>ClientRegistry</code> là kiểu miền do ứng dụng định nghĩa.

## 3. Gửi thông tin SETUP từ client

<code>RSocketRequester.Builder</code> cho phép tùy chỉnh frame SETUP trước khi mở connection:

| Phương thức | Tác dụng |
| --- | --- |
| <code>dataMimeType(MimeType)</code> | Chọn MIME type cho data trên connection |
| <code>metadataMimeType(MimeType)</code> | Chọn MIME type cho metadata trên connection |
| <code>setupData(Object)</code> | Đưa data ban đầu vào SETUP |
| <code>setupRoute(String, Object...)</code> | Đưa route vào metadata của SETUP |
| <code>setupMetadata(Object, MimeType)</code> | Thêm một metadata entry vào SETUP |

Ví dụ client khai báo route và dữ liệu nhận diện:

Giả sử <code>strategies</code> là instance <code>RSocketStrategies</code> đã đăng ký encoder/decoder cho các kiểu dữ liệu của ứng dụng như phần tiếp theo.

~~~java
MimeType tenantMimeType = TENANT_MIME;

RSocketRequester requester = RSocketRequester.builder()
    .rsocketStrategies(strategies)
    .setupRoute("client.connect")
    .setupData(new ClientSetup("client-17", "desktop"))
    .setupMetadata(
        new TenantMetadata("tenant-42"),
        tenantMimeType
    )
    .tcp("localhost", 7000);
~~~

Đoạn code tạo một <code>RSocketRequester</code> dùng TCP. Builder có thể chuẩn bị requester trước; kết nối được thiết lập khi requester bắt đầu thực hiện tương tác. Khi connection được mở, client gửi SETUP với route <code>client.connect</code>, data <code>ClientSetup</code> và metadata tenant. Server dùng <code>@ConnectMapping("client.connect")</code> để nhận thông tin đó.

Với WebSocket, có thể thay lời gọi <code>tcp</code> bằng <code>webSocket(URI.create("ws://localhost:8080/rsocket"))</code> nếu server cung cấp endpoint tương ứng. Cách gửi SETUP và cách xử lý bằng <code>@ConnectMapping</code> không thay đổi theo transport.

Data và metadata trong SETUP là tùy chọn. Nếu gửi object Java thay vì <code>String</code> hoặc <code>byte[]</code>, client và server cần cấu hình encoder/decoder tương thích thông qua <code>RSocketStrategies</code>. Data MIME type và metadata MIME type đã chọn ở cấp connection được áp dụng cho các message trên connection đó.

## 4. Giải mã metadata thành header

<code>@Header</code> không tự giải mã mọi metadata entry. Spring dùng <code>MetadataExtractor</code> để chuyển metadata đã serialize thành các cặp tên-giá trị có thể truy cập như header trong method handler.

<code>DefaultMetadataExtractor</code> có hỗ trợ sẵn routing metadata và lưu route dưới key <code>route</code>. Với MIME type tùy chỉnh, ứng dụng cần có decoder phù hợp và đăng ký entry cần trích xuất.

Ví dụ đăng ký metadata tenant:

~~~java
private static final MimeType TENANT_MIME =
    MimeTypeUtils.parseMimeType("application/vnd.example.tenant+json");
private static final MimeType CONTEXT_MIME =
    MimeTypeUtils.parseMimeType("application/vnd.example.client-context+json");

@Bean
RSocketStrategies rsocketStrategies() {
    return RSocketStrategies.builder()
        .encoders(encoders -> encoders.add(new Jackson2JsonEncoder()))
        .decoders(decoders -> decoders.add(new Jackson2JsonDecoder()))
        .metadataExtractorRegistry(registry -> {
            registry.metadataToExtract(
                TENANT_MIME,
                TenantMetadata.class,
                "tenant"
            );
            registry.metadataToExtract(
                CONTEXT_MIME,
                ClientContext.class,
                "client-context"
            );
        })
        .build();
}
~~~

Ví dụ dùng Jackson JSON encoder/decoder và đăng ký metadata entry thành header <code>tenant</code>. Các class encoder/decoder cần có trong classpath; dự án phải chọn codec phù hợp với MIME type đã thống nhất giữa client và server. Nếu metadata được gửi dưới dạng JSON, cả hai phía phải dùng cùng schema và quy tắc serialize.

Sau khi cấu hình extractor, handler có thể nhận giá trị bằng <code>@Header("tenant")</code>. Nếu extractor chưa đăng ký MIME type tùy chỉnh hoặc không có decoder tương ứng, header có thể không xuất hiện hoặc không giải mã được. Khi đó cần kiểm tra cấu hình <code>RSocketStrategies</code>, MIME type và encoder/decoder của hai phía.

## 5. Nhận SETUP bằng @ConnectMapping

SETUP thường chứa thông tin cần thiết để xác định connection và khởi tạo ngữ cảnh ban đầu. Những thông tin thường gặp gồm:

- Client ID hoặc loại client.
- Tenant hoặc phạm vi dữ liệu được phép truy cập.
- Phiên bản hợp đồng ứng dụng.
- Metadata phục vụ xác thực hoặc tracing theo cơ chế đã thống nhất.
- Thông tin cấu hình ban đầu như locale hoặc nhóm subscription.

Ví dụ handler có thể đăng ký connection vào registry:

~~~java
@ConnectMapping("client.connect")
Mono<Void> onConnect(
        @Payload ClientSetup setup,
        @Header("tenant") TenantMetadata tenant,
        RSocketRequester requester) {

    if (setup == null || setup.clientId() == null
            || setup.clientId().isBlank() || tenant == null) {
        return Mono.error(
            new IllegalArgumentException("clientId is required")
        );
    }

    return clientRegistry.register(
        setup.clientId(),
        tenant.tenantId(),
        requester
    );
}
~~~

<code>RSocketRequester</code> là requester gắn với connection đó. Server có thể giữ requester để gửi request chủ động tới client sau này, ví dụ yêu cầu client đồng bộ trạng thái hoặc gửi thông báo. Cần quản lý requester theo vòng đời connection và loại bỏ khi connection đóng.

Nếu xử lý SETUP trả về lỗi, connection mới có thể bị từ chối. Đây là điểm phù hợp để kiểm tra điều kiện thiết lập bắt buộc, nhưng không nên dùng handler như nơi thực hiện toàn bộ công việc khởi động tốn thời gian.

## 6. Nhận METADATA_PUSH sau khi connection hoạt động

Sau khi connection được thiết lập, client có thể gửi metadata mới bằng <code>sendMetadata()</code>. API này thực hiện một METADATA_PUSH và trả về <code>Mono&lt;Void&gt;</code>.

Ví dụ client cập nhật ngôn ngữ hiển thị và trạng thái ứng dụng:

~~~java
MimeType contextMimeType = CONTEXT_MIME;

Mono<Void> updateContext = requester
    .route("client.context")
    .metadata(
        new ClientContext("vi-VN", "FOREGROUND"),
        contextMimeType
    )
    .sendMetadata();

updateContext.subscribe(
    ignored -> {},
    error -> log.error("Không gửi được client context", error)
);
~~~

<code>route("client.context")</code> đưa route vào metadata để chọn handler. <code>metadata(...)</code> thêm entry ngữ cảnh. <code>sendMetadata()</code> phát METADATA_PUSH thay vì một request-response thông thường.

Ở server, handler nhận metadata push:

~~~java
@ConnectMapping("client.context")
Mono<Void> onClientContext(
        @Header("client-context") ClientContext context) {

    return clientRegistry.updateContext(context);
}
~~~

<code>sendMetadata()</code> không tạo response nghiệp vụ từ server. Việc <code>Mono&lt;Void&gt;</code> hoàn tất cho biết thao tác gửi metadata đã hoàn tất theo API client; nó không phải xác nhận rằng server đã cập nhật context thành công. Nếu client cần xác nhận nghiệp vụ, hãy gửi một request-response riêng hoặc thiết kế một route acknowledgement.

METADATA_PUSH có phạm vi connection-level. Không dùng nó để thay thế metadata riêng của từng request, chẳng hạn correlation ID hoặc quyền truy cập của một thao tác cụ thể. Metadata của request nên được gắn vào chính request đó.

## 7. @ConnectMapping không trả dữ liệu

Method <code>@ConnectMapping</code> không phải handler request-response và không được trả về payload cho peer. Giá trị trả về phải là <code>void</code> hoặc <code>Mono&lt;Void&gt;</code>.

~~~java
@ConnectMapping("client.connect")
Mono<Void> register(ClientSetup setup) {
    return clientRegistry.register(setup);
}
~~~

<code>Mono&lt;Void&gt;</code> cho phép thực hiện công việc bất đồng bộ trước khi hoàn tất xử lý connection setup. Khi xử lý một connection mới kết thúc bằng lỗi, connection có thể bị từ chối. Đối với metadata push trên một connection đã hoạt động, handler vẫn không tạo response payload; lỗi cần được ghi nhận và xử lý theo chính sách của ứng dụng.

Không trả về <code>Mono&lt;ClientInfo&gt;</code>, <code>Flux&lt;Event&gt;</code> hoặc một object nghiệp vụ từ <code>@ConnectMapping</code>. Nếu cần phản hồi cho client, hãy dùng một route <code>@MessageMapping</code> riêng với request-response.

## 8. Không chặn SETUP handler bằng request ngược tới client

Trong <code>@ConnectMapping</code>, server có thể nhận <code>RSocketRequester</code> để gửi request ngược tới client. Tuy nhiên, việc xử lý SETUP phải hoàn tất trước khi connection sẵn sàng cho các request thông thường. Nếu handler chờ một request ngược hoàn tất rồi mới trả <code>Mono&lt;Void&gt;</code>, hai phía có thể bị chờ lẫn nhau hoặc làm quá trình thiết lập bị trì hoãn.

Hãy tách request ngược thành tác vụ bất đồng bộ độc lập:

~~~java
@ConnectMapping("client.connect")
Mono<Void> onConnect(
        ClientSetup setup,
        RSocketRequester requester) {

    requester.route("client.initialize")
        .data(new InitializeClient("welcome"))
        .retrieveMono(Void.class)
        .subscribe(
            ignored -> {},
            error -> log.warn("Client initialization request failed", error)
        );

    return clientRegistry.register(setup);
}
~~~

Ví dụ minh họa việc khởi chạy request ngược mà không chờ nó trong luồng xử lý SETUP. Trong hệ thống thật, cần quản lý subscription, timeout và lỗi của tác vụ độc lập; tránh tạo tác vụ nền không có vòng đời hoặc không được giám sát.

Nếu client cần gửi xác nhận rằng khởi tạo đã xong, hãy thiết kế một route riêng như <code>client.initialize.ack</code> và xử lý nó bằng <code>@MessageMapping</code>.

## 9. Dùng metadata push để cập nhật ngữ cảnh connection

Metadata push hữu ích cho thông tin có phạm vi toàn connection và có thể thay đổi trong lúc session tồn tại:

| Thông tin | Dùng METADATA_PUSH? | Lưu ý |
| --- | --- | --- |
| Locale hoặc timezone của client | Có thể | Nếu áp dụng chung cho các tương tác tiếp theo trên connection. |
| Trạng thái foreground/background | Có thể | Hữu ích cho chính sách gửi thông báo hoặc dữ liệu. |
| Subscription preferences | Có thể | Cần đồng bộ với các stream đang hoạt động theo chính sách rõ ràng. |
| Tenant ID | Cẩn trọng | Phải xác minh tenant với danh tính đã xác thực; không tin metadata do client tự khai báo. |
| Access token hoặc thông tin xác thực mới | Có thể theo thiết kế bảo mật | Phải kiểm tra, xoay vòng và thu hồi quyền đúng cách. |
| Correlation ID của một request | Không nên | Nên gửi trong metadata của request tương ứng. |
| Payload nghiệp vụ lớn | Không phù hợp | Dùng request hoặc stream chuyên biệt. |

Metadata push chỉ là thông báo. Nếu server cập nhật context nội bộ, cần quyết định các request đang chạy có dùng context cũ hay mới. Với các stream dài hạn, có thể áp dụng context mới cho message tiếp theo, hủy và đăng ký lại stream hoặc yêu cầu client mở connection mới. Không nên để hành vi này phụ thuộc vào race condition không được định nghĩa.

## 10. Bảo mật thông tin connection

SETUP và METADATA_PUSH đều mang thông tin ở phạm vi connection, vì vậy việc xử lý cần gắn với xác thực và quản lý vòng đời:

- Xác thực client bằng cơ chế phù hợp; không xem client ID hoặc tenant ID tự khai báo là bằng chứng danh tính.
- Kiểm tra quyền truy cập trước khi đăng ký connection hoặc cho phép route.
- Không ghi token, mật khẩu hoặc credential thô vào log.
- Giới hạn kích thước metadata và xác thực cấu trúc trước khi lưu.
- Ràng buộc metadata push với principal đã xác thực của connection.
- Khi credential hết hạn hoặc quyền bị thu hồi, đóng hoặc hạn chế connection theo chính sách.
- Không cho phép metadata push tùy ý thay đổi tenant hoặc nâng quyền.

Metadata có thể được bảo vệ bằng TLS trên transport. Tuy nhiên, mã hóa đường truyền không thay thế việc kiểm tra danh tính và quyền truy cập ở server.

## 11. Quản lý vòng đời requester và connection

Nếu server lưu <code>RSocketRequester</code> theo client ID, registry cần loại bỏ entry khi connection đóng. Nếu không, ứng dụng có thể giữ các requester đã chết và tiếp tục gửi dữ liệu vào session không còn hoạt động.

Một mô hình quản lý thường gồm:

1. Khi SETUP được chấp nhận, tạo entry gắn với connection ID và requester.
2. Gắn xử lý <code>onClose()</code> để phát hiện connection kết thúc.
3. Khi nhận METADATA_PUSH, cập nhật context của đúng connection.
4. Khi connection đóng, xóa entry, dừng các stream liên quan và giải phóng tài nguyên.
5. Nếu cùng client ID kết nối lại, dùng connection ID hoặc generation để tránh callback đóng của session cũ xóa entry mới.

Handler có thể nhận <code>RSocketRequester</code> và chuyển nó cho một registry có vòng đời rõ ràng. Việc theo dõi đóng connection nên được tích hợp ở tầng quản lý connection hoặc lifecycle phù hợp với phiên bản Spring/RSocket đang dùng; không giả định mọi requester đều luôn cung cấp một RSocket nội bộ có thể truy cập trực tiếp.

## 12. Kiểm thử SETUP và METADATA_PUSH

Nên kiểm thử hai loại frame riêng biệt vì chúng có thời điểm, dữ liệu và tác động khác nhau.

| Ca kiểm thử | Cách thực hiện | Kết quả mong đợi |
| --- | --- | --- |
| SETUP có route | Client dùng <code>setupRoute("client.connect")</code> | Handler <code>@ConnectMapping("client.connect")</code> được gọi. |
| SETUP có data | Client dùng <code>setupData(...)</code> | <code>@Payload</code> nhận đúng object sau decode. |
| SETUP có metadata tùy chỉnh | Client dùng <code>setupMetadata(...)</code> | Extractor giải mã metadata và <code>@Header</code> nhận đúng giá trị. |
| SETUP thiếu thông tin bắt buộc | Bỏ client ID hoặc tenant | Server từ chối connection theo chính sách. |
| METADATA_PUSH hợp lệ | Client gọi <code>route(...).metadata(...).sendMetadata()</code> | Handler metadata push tương ứng được gọi. |
| METADATA_PUSH nhiều lần | Gửi các context khác nhau | Server cập nhật đúng thứ tự xử lý theo contract. |
| Route metadata push không khớp | Gửi route khác | Handler có pattern cụ thể không được gọi. |
| Metadata sai MIME type | Dùng MIME type chưa đăng ký | Server xử lý lỗi giải mã hoặc bỏ metadata theo cấu hình; không nhận nhầm thành header hợp lệ. |
| Connection đóng | Dispose requester hoặc ngắt transport | Registry loại bỏ requester và cleanup được chạy. |

Có thể dùng integration test với RSocket server và requester thật. Khi kiểm tra handler bất đồng bộ, dùng <code>StepVerifier</code> hoặc cơ chế chờ có timeout để xác nhận tác vụ đã hoàn tất. Không dùng sleep tùy tiện vì dễ tạo kiểm thử chập chờn.

## 13. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể có | Cách xử lý |
| --- | --- | --- |
| <code>@ConnectMapping</code> không được gọi | Client chưa gửi SETUP, route setup không khớp hoặc handler chưa được đăng ký. | Kiểm tra kết nối thực tế, <code>setupRoute</code> và controller discovery. |
| Handler SETUP không nhận được payload | Client chưa gọi <code>setupData</code> hoặc codec không tương thích. | Kiểm tra data MIME type và encoder/decoder. |
| <code>@Header</code> trả về thiếu metadata | Chưa đăng ký MIME type trong <code>MetadataExtractor</code>. | Cấu hình <code>RSocketStrategies</code> và decoder tương ứng. |
| METADATA_PUSH không tới handler mong muốn | Client không gửi route metadata hoặc route pattern không khớp. | Kiểm tra <code>.route(...).sendMetadata()</code> và route mapping. |
| Client tưởng server đã áp dụng metadata | Nhầm <code>Mono&lt;Void&gt;</code> của <code>sendMetadata()</code> là acknowledgement nghiệp vụ. | Dùng route request-response riêng nếu cần xác nhận. |
| Connection setup bị trì hoãn | Handler chờ request ngược tới client hoàn tất. | Tách request ngược khỏi luồng xử lý SETUP. |
| Registry còn requester đã đóng | Không cleanup theo lifecycle hoặc callback cũ xóa nhầm session mới. | Gắn generation/connection ID và cleanup có điều kiện. |

## 14. Ghi nhớ

- <code>@ConnectMapping</code> xử lý SETUP khi connection bắt đầu và METADATA_PUSH trong suốt vòng đời connection.
- SETUP có thể mang data, metadata và route thiết lập; METADATA_PUSH chỉ mang metadata connection-level.
- <code>RSocketRequester.Builder</code> dùng <code>setupRoute</code>, <code>setupData</code> và <code>setupMetadata</code> để chuẩn bị SETUP.
- Client dùng <code>route(...).metadata(...).sendMetadata()</code> để gửi METADATA_PUSH.
- <code>@ConnectMapping</code> hỗ trợ route pattern; nếu không khai báo pattern thì method có thể khớp mọi setup và metadata push.
- Method chỉ trả <code>void</code> hoặc <code>Mono&lt;Void&gt;</code>; không trả payload nghiệp vụ.
- <code>MetadataExtractor</code> và <code>RSocketStrategies</code> cần đăng ký decoder cho metadata tùy chỉnh trước khi đọc bằng <code>@Header</code>.
- Lỗi khi xử lý SETUP mới có thể khiến connection bị từ chối; không chờ request ngược trong luồng xử lý SETUP.
- METADATA_PUSH không có acknowledgement nghiệp vụ. Dùng request-response riêng khi cần xác nhận cập nhật.
- Quản lý requester, metadata context và cleanup theo vòng đời connection để tránh rò rỉ tài nguyên.

## Tài liệu tham khảo

- [Spring Framework — RSocket Reference: RSocketRequester và @ConnectMapping](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [Spring Framework — ConnectMapping API](https://docs.spring.io/spring-framework/docs/6.1.6/javadoc-api/org/springframework/messaging/rsocket/annotation/ConnectMapping.html)
- [Spring Framework — RSocketRequester.RequestSpec API](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/messaging/rsocket/RSocketRequester.RequestSpec.html)
- [Spring Framework — RSocketStrategies.Builder API](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/messaging/rsocket/RSocketStrategies.Builder.html)
