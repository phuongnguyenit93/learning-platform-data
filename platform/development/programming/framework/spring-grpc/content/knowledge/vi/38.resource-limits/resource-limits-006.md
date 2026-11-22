# Giới hạn metadata

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích metadata của gRPC và phân biệt metadata với protobuf message body.
- Phân biệt giới hạn metadata nhận vào ở server và client với việc kiểm soát metadata gửi đi.
- Cấu hình giới hạn inbound metadata bằng grpc-java Netty builder.
- Thiết kế metadata key/value, ASCII và binary metadata đúng quy tắc.
- Giới hạn số entry, độ dài key/value và dữ liệu lặp ở application boundary.
- Dùng metadata cho authentication, tracing và correlation mà không biến headers thành kênh truyền payload.
- Hiểu metadata của streaming RPC và trailing metadata.
- Kiểm thử metadata gần ngưỡng, vượt ngưỡng và xác minh cấu hình Spring gRPC thực tế.

## 1. Metadata là gì và vì sao cần giới hạn?

Trong **SPRING_GRPC**, metadata là tập key/value đi kèm một RPC. Client thường gửi metadata ban đầu cùng request headers; server có thể gửi metadata ban đầu và metadata kết thúc (trailers) về client. Metadata thường mang thông tin điều khiển như credential, trace context, correlation ID, locale hoặc routing hint.

Metadata không phải protobuf message body. Một RPC unary có thể có request protobuf nhỏ nhưng headers lại chứa token, danh sách claim hoặc nhiều giá trị tùy ý rất lớn. Ngược lại, một message protobuf có thể lớn trong khi metadata chỉ vài entry. Hai loại dữ liệu cần giới hạn độc lập.

Nếu metadata không được giới hạn, caller có thể gửi rất nhiều header hoặc value rất dài. Transport phải giữ và xử lý chúng trước khi service handler chạy; điều này tiêu tốn memory, CPU và có thể làm tăng chi phí parsing, logging, authentication. Metadata response lớn cũng có thể gây lỗi ở client hoặc làm lộ dữ liệu không nên trả về headers.

**Giới hạn metadata** kiểm soát kích thước metadata mà một endpoint chấp nhận nhận vào. Nên kết hợp receive limit ở transport với validation về key, value, số entry và nội dung ở application.

~~~mermaid
flowchart TD
    A["RPC bắt đầu"] --> B["HTTP/2 headers / gRPC metadata"]
    B --> C{"Inbound metadata dưới giới hạn?"}
    C -- "Không" --> D["Từ chối tại transport"]
    C -- "Có" --> E["Authentication và interceptor"]
    E --> F["Validate key/value và policy"]
    F --> G["Service handler"]
    G --> H["Response headers / trailers"]
    H --> I["Client inbound metadata limit"]
~~~

Giới hạn cần được cấu hình ở cả hai đầu: server bảo vệ khỏi request metadata quá lớn; client bảo vệ khỏi response metadata hoặc trailers quá lớn.

## 2. Inbound metadata limit theo chiều request và response

Luôn xác định sender và receiver cho từng chiều:

| Metadata | Sender | Receiver | Giới hạn cần quan tâm |
| --- | --- | --- | --- |
| Request headers | Client | Server | Server inbound metadata limit |
| Response initial headers | Server | Client | Client inbound metadata limit |
| Response trailers | Server | Client | Client receive-side metadata handling/limit theo transport |
| Metadata của outbound call từ service A | Service A client stub | Service B server | Server B inbound limit và validation ở A |

Giới hạn inbound trên server không giới hạn metadata mà server tự gửi. Tương tự, giới hạn inbound trên client không giới hạn request metadata client gửi đi. Nếu server cần trả response headers lớn, client phải có receive limit phù hợp; nhưng response metadata vẫn nên nhỏ và chỉ chứa dữ liệu điều khiển.

Một sender có thể tạo metadata lớn hơn mức receiver chấp nhận. Vì vậy, client SDK nên tuân thủ contract của server và kiểm tra dữ liệu trước khi gắn vào Metadata. Receiver vẫn là hàng rào cuối cùng vì caller có thể dùng client khác hoặc gửi raw HTTP/2/gRPC request.

Không giả định một giới hạn ở connection hay message body sẽ tự động giới hạn metadata. Message size, metadata size và HTTP/2 frame/header limits là các lớp khác nhau.

## 3. Cấu hình inbound metadata ở grpc-java

Với Netty transport, grpc-java builder cung cấp cấu hình inbound metadata size. Ví dụ giới hạn request metadata ở server:

~~~java
import io.grpc.Server;
import io.grpc.netty.shaded.io.grpc.netty.NettyServerBuilder;

public final class GrpcServerFactory {

    private static final int MAX_INBOUND_METADATA_BYTES = 16 * 1024;

    public Server createServer(int port) {
        return NettyServerBuilder.forPort(port)
                .maxInboundMetadataSize(MAX_INBOUND_METADATA_BYTES)
                .build();
    }
}
~~~

Ở client, giới hạn metadata nhận từ server:

~~~java
import io.grpc.ManagedChannel;
import io.grpc.netty.shaded.io.grpc.netty.NettyChannelBuilder;

public final class GrpcChannelFactory {

    private static final int MAX_INBOUND_METADATA_BYTES = 16 * 1024;

    public ManagedChannel createChannel(String host, int port) {
        return NettyChannelBuilder.forAddress(host, port)
                .maxInboundMetadataSize(MAX_INBOUND_METADATA_BYTES)
                .build();
    }
}
~~~

Các con số 16 KiB chỉ là ví dụ, không phải default phổ quát hoặc khuyến nghị cho mọi hệ thống. Chọn ngưỡng theo headers thực tế, token size, tracing baggage, số interceptor và yêu cầu của client.

API cụ thể phụ thuộc grpc-java version và transport. Nếu dùng transport khác Netty, kiểm tra builder tương ứng. Đừng sao chép property name từ một starter khác mà chưa xác nhận phiên bản dự án có hỗ trợ.

Trong Spring gRPC, starter thường quản lý server/channel lifecycle. Áp dụng giới hạn qua builder customizer/configurer hoặc extension point được phiên bản starter hỗ trợ. Không tạo server thứ hai chỉ để đặt limit. Viết Spring application integration test để xác nhận builder mà Spring thực sự dùng đã nhận giá trị mong muốn.

Không dựa vào default của thư viện như một phần contract lâu dài. Đặt giá trị tường minh và ghi rõ giới hạn metadata trong tài liệu client/server.

## 4. Metadata size không phải message size hay HTTP/2 frame size

gRPC metadata được ánh xạ vào HTTP/2 headers và trailers. HTTP/2 dùng HPACK để nén header block; transport có thể chia header block thành các frame. Vì vậy, không được đồng nhất:

- **Metadata size:** kích thước danh sách key/value theo cách tính của gRPC/transport.
- **Compressed header bytes:** số byte thực tế sau HPACK trên wire.
- **HTTP/2 frame size:** kích thước từng frame transport.
- **gRPC message size:** kích thước protobuf message body.
- **Total RPC bytes:** tổng dữ liệu của cả call hoặc stream.

Giới hạn metadata của grpc-java được áp dụng theo semantics của builder/transport; không tự suy ra nó bằng số byte HPACK trên network. Cách tính overhead và binary metadata có thể phụ thuộc implementation/version. Hãy kiểm thử trên đúng transport đang chạy.

Metadata thường được gửi lúc call bắt đầu, còn streaming message tiếp theo đi trong message body. Gửi thêm nhiều protobuf message không làm tăng số metadata headers của call; tuy vậy, tổng stream vẫn cần quota message/byte riêng.

## 5. Quy tắc key và value trong grpc-java

Metadata key là tên dạng ASCII viết thường. Key dành cho binary value phải có hậu tố **-bin**. Các key có prefix **grpc-** được dành riêng cho giao thức; ứng dụng không tự định nghĩa key transport-reserved.

Ví dụ tạo key:

~~~java
import io.grpc.Metadata;

public final class AppMetadataKeys {

    public static final Metadata.Key<String> CORRELATION_ID =
            Metadata.Key.of(
                    "x-correlation-id",
                    Metadata.ASCII_STRING_MARSHALLER);

    public static final Metadata.Key<byte[]> SIGNED_CONTEXT =
            Metadata.Key.of(
                    "x-signed-context-bin",
                    Metadata.BINARY_BYTE_MARSHALLER);

    private AppMetadataKeys() {}
}
~~~

Dùng ASCII marshaller cho giá trị text theo quy tắc metadata; dùng binary marshaller cho bytes. Không tự Base64 encode một giá trị rồi gắn vào key text nếu API đã có binary metadata, trừ khi contract bên ngoài yêu cầu biểu diễn text cụ thể.

Metadata có thể chứa nhiều giá trị cho cùng một key. Nếu application chỉ cho phép một correlation ID hoặc một authorization credential, hãy kiểm tra duplicate key và từ chối trường hợp mơ hồ. Đừng giả định mọi key chỉ xuất hiện đúng một lần.

Không đặt key tùy ý bắt đầu bằng grpc-. Không dùng chữ hoa trong metadata key. Không dùng metadata key để mô phỏng method name hoặc override thông tin transport đã có trong server-side call descriptor.

## 6. Giới hạn số entry và độ dài từng value

Inbound metadata size limit là hàng rào tổng ở transport. Application vẫn cần allowlist các key được chấp nhận và giới hạn từng value.

Ví dụ validation cho correlation ID:

~~~java
private static final int MAX_CORRELATION_ID_LENGTH = 128;

static String validateCorrelationId(String value) {
    if (value == null || value.isBlank()) {
        throw new IllegalArgumentException("Correlation ID is required");
    }

    if (value.length() > MAX_CORRELATION_ID_LENGTH) {
        throw new IllegalArgumentException("Correlation ID is too long");
    }

    if (!value.matches("[A-Za-z0-9._-]+")) {
        throw new IllegalArgumentException("Correlation ID has invalid characters");
    }

    return value;
}
~~~

Một policy metadata nên quy định:

- Danh sách key được phép cho từng service/method.
- Độ dài tối đa của mỗi text value.
- Kích thước tối đa của binary value.
- Số lần xuất hiện tối đa cho key lặp.
- Tổng số entry của application metadata.
- Quy tắc xử lý key không biết hoặc key trùng.
- Dữ liệu nào được phép forward tới downstream.

Không chỉ kiểm tra tổng bytes. Một metadata block có thể nằm dưới tổng limit nhưng chứa nhiều entry nhỏ gây chi phí parsing và logging. Ngược lại, một binary value duy nhất có thể chiếm phần lớn budget. Kết hợp tổng limit với per-key limit và số entry.

Tránh log toàn bộ Metadata. Token, signed context và binary value có thể chứa dữ liệu nhạy cảm. Log key được cho phép, kích thước và correlation ID đã được sanitize; không log credential.

## 7. Authentication và tracing không phải lý do để metadata tăng vô hạn

Metadata thường mang bearer token, mTLS-related context, traceparent, baggage hoặc correlation ID. Những giá trị này hữu ích nhưng cần giới hạn.

Với authentication:

- Chỉ chấp nhận credential theo contract, ví dụ một authorization value.
- Giới hạn chiều dài token trước khi gọi verifier nếu application nhận được metadata.
- Không forward token tới service không cần xác minh nó.
- Không đưa access token hoặc toàn bộ claim vào response headers.
- Nếu token lớn do chứa nhiều claim, cân nhắc token reference hoặc thiết kế claim tối thiểu.

Với tracing:

- Giới hạn số baggage entry và chiều dài mỗi value.
- Chỉ propagate field cần thiết.
- Không đưa user ID, email hoặc dữ liệu cá nhân vào baggage nếu không cần.
- Tránh biến trace baggage thành nơi truyền object hoặc danh sách dài.

Metadata đến server được transport nhận trước khi application interceptor có thể kiểm tra từng key. Vì vậy, application validation không thay thế inbound transport limit. Transport limit chặn header block quá lớn; application policy kiểm soát nội dung sau khi metadata được chấp nhận.

## 8. Gửi metadata ở client và kiểm tra trước khi attach

Client có thể tạo metadata bằng interceptor hoặc per-call headers. Nên tập trung việc tạo headers để kiểm soát số lượng và độ dài value trước khi gửi.

Ví dụ client interceptor:

~~~java
public final class CorrelationClientInterceptor
        implements ClientInterceptor {

    private final Supplier<String> correlationIdSupplier;

    public CorrelationClientInterceptor(
            Supplier<String> correlationIdSupplier) {
        this.correlationIdSupplier = correlationIdSupplier;
    }

    @Override
    public <ReqT, RespT> ClientCall<ReqT, RespT> interceptCall(
            MethodDescriptor<ReqT, RespT> method,
            CallOptions callOptions,
            Channel next) {

        ClientCall<ReqT, RespT> call =
                next.newCall(method, callOptions);

        return new ForwardingClientCall
                .SimpleForwardingClientCall<ReqT, RespT>(call) {

            @Override
            public void start(
                    Listener<RespT> responseListener,
                    Metadata headers) {

                String id = validateCorrelationId(
                        correlationIdSupplier.get());

                headers.put(AppMetadataKeys.CORRELATION_ID, id);
                super.start(responseListener, headers);
            }
        };
    }
}
~~~

Ví dụ chỉ thêm một correlation ID. Nếu có nhiều interceptor cùng thêm metadata, cần một policy chung để tránh duplicate hoặc vượt ngân sách. Không tạo một metadata object khổng lồ trong mỗi call và không attach toàn bộ HTTP request headers vào gRPC.

Nếu outbound metadata vượt receive limit của server, server có thể từ chối call trước khi handler chạy. Kiểm tra phía client giúp phát hiện lỗi sớm, nhưng không thay thế receive limit ở server.

## 9. Server response headers và trailers cũng phải nhỏ

Server có thể gửi metadata ban đầu trước response đầu tiên và trailing metadata khi call kết thúc. Dùng chúng cho thông tin điều khiển nhỏ như version, request correlation hoặc reason code đã được công bố trong contract.

Không đưa toàn bộ validation errors, danh sách record, stack trace hoặc payload nghiệp vụ vào trailers. Dữ liệu lớn nên nằm trong protobuf response message hoặc một API phù hợp.

Với server response metadata, client là receiver. Client inbound metadata limit cần đủ cho headers/trailers hợp lệ. Tuy nhiên, không tăng client limit vô hạn để chấp nhận response bất thường. Server cũng nên kiểm tra số lượng key/value và chỉ phát metadata được phép.

Với streaming RPC, initial metadata thường được gửi một lần ở đầu call; trailers được gửi ở terminal event. Không thêm metadata headers cho từng message. Nếu mỗi event cần mang cursor, sequence hoặc trạng thái riêng, đặt chúng trong protobuf message schema.

## 10. Metadata trong streaming RPC

Một streaming call có thể kéo dài và truyền nhiều message, nhưng metadata của call có lifecycle riêng:

- Request metadata được gửi khi client mở RPC.
- Server có thể gửi initial response metadata trước hoặc cùng thời điểm response bắt đầu.
- Message stream mang dữ liệu trong protobuf body.
- Trailers kết thúc call và có thể mang status detail/metadata cuối.

Do đó, metadata limit không thay thế message-size limit, message-count limit, total stream bytes hoặc deadline. Một stream có thể mở bằng headers nhỏ nhưng truyền hàng triệu message; cần các resource limit riêng.

Với stream dài, đừng đặt session state lớn vào metadata. Chỉ gửi credential, trace context và selector nhỏ đã được xác minh. State của stream nên ở application object hoặc storage có quota/lifecycle rõ ràng.

## 11. Xử lý khi metadata vượt giới hạn

Khi inbound metadata vượt transport limit, gRPC runtime thường từ chối call trước khi service handler chạy. Status thường gặp là **RESOURCE_EXHAUSTED**, nhưng chi tiết status/description và thời điểm phát hiện phụ thuộc grpc-java version và transport.

Phân biệt:

| Tình huống | Kết quả thường dùng | Xử lý |
| --- | --- | --- |
| Tổng inbound metadata vượt transport limit | RESOURCE_EXHAUSTED | Giảm headers hoặc điều chỉnh receive limit có kiểm soát |
| Một key/value vượt application policy | INVALID_ARGUMENT hoặc status contract | Từ chối key/value cụ thể |
| Có key không được phép | INVALID_ARGUMENT hoặc PERMISSION_DENIED tùy ý nghĩa | Áp dụng allowlist |
| Caller thiếu credential | UNAUTHENTICATED | Cung cấp credential hợp lệ |
| Caller có credential nhưng thiếu quyền | PERMISSION_DENIED | Cấp quyền phù hợp |
| Response metadata vượt client receive limit | Client từ chối response | Giảm metadata server trả về hoặc thống nhất contract |

Không dựa vào status description cụ thể để điều khiển logic client; dùng status code và reason code ổn định nếu API cung cấp. Không retry nguyên metadata block quá lớn vì retry không làm headers nhỏ đi.

Nếu metadata chứa token hoặc baggage, lỗi vượt limit không được ghi toàn bộ header vào log. Chỉ log method, status, kích thước tổng nếu runtime cung cấp, và correlation ID đã được xử lý an toàn.

## 12. Chọn giới hạn theo contract và quan sát thực tế

Không có một con số phù hợp cho mọi hệ thống. Ngưỡng phụ thuộc token size, tracing baggage, số interceptor, số key và yêu cầu tương thích client.

Khi chọn limit:

1. Thu thập kích thước headers hợp lệ từ client thực tế.
2. Đo p50/p95/p99 và các trường hợp token lớn nhất hợp lệ.
3. Dành headroom hợp lý cho trace context và metadata mới.
4. Đặt giới hạn server và client nhất quán theo từng chiều.
5. Đặt per-key length và entry-count policy.
6. Kiểm thử client cũ và các gateway/proxy nằm giữa hai bên.
7. Theo dõi reject rate sau khi triển khai.

Không tăng limit chỉ vì một client đang gửi toàn bộ cookie hoặc HTTP headers không cần thiết. Sửa client để chỉ propagate metadata cần cho RPC.

Metric hữu ích:

- Inbound metadata rejection theo method.
- Kích thước metadata bucket theo request/response.
- Số entry và số duplicate key bị từ chối.
- Tỷ lệ RESOURCE_EXHAUSTED liên quan metadata.
- Số response trailers gần ngưỡng.
- Latency authentication/tracing khi metadata lớn.

Không dùng raw token, user ID tùy ý hoặc toàn bộ metadata làm metric label. Tránh log payload và credential.

## 13. Kiểm thử metadata boundary

Test cần kiểm tra cả server inbound và client inbound, đồng thời phân biệt transport limit với application policy:

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| Request metadata nhỏ hơn server limit | Server nhận và dispatch RPC |
| Request metadata vượt server limit | Transport từ chối; handler không chạy |
| Response metadata nhỏ hơn client limit | Client nhận response |
| Response headers/trailers vượt client limit | Client receive path từ chối |
| Key hợp lệ nhưng value quá dài theo policy | Application interceptor từ chối |
| Có duplicate authorization key | Từ chối theo policy |
| Có key không nằm trong allowlist | Từ chối hoặc bỏ qua theo contract rõ |
| Binary metadata hợp lệ | Được decode bằng binary marshaller |
| Metadata nhỏ nhưng message body lớn | Message-size limit xử lý độc lập |
| Streaming có headers nhỏ và nhiều message | Metadata limit không thay stream quota |

Dùng grpc-java in-process hoặc transport integration test để xác minh hành vi thực tế. Nếu transport in-process không mô phỏng đúng giới hạn metadata của Netty, bổ sung test với Netty server/channel trong môi trường test. Đừng giả định test tự dựng interceptor chain chứng minh receive limit của transport.

Các assertion quan trọng:

1. Request vượt inbound metadata limit không vào handler.
2. Response vượt client receive limit không được client chấp nhận.
3. Application per-key validation phân biệt với transport-level size rejection.
4. Binary metadata dùng đúng marshaller.
5. Duplicate/unknown keys được xử lý theo contract.
6. Message body và stream quota được kiểm tra độc lập.
7. Spring application test xác nhận builder customizer thực tế đã cấu hình đúng giá trị.

## 14. Tích hợp trong Spring gRPC

Trong ứng dụng Spring, tách rõ ba phần:

- **Transport configuration:** inbound metadata limit trên server/channel builder.
- **Metadata policy:** allowlist key, per-key length, duplicate handling và validation.
- **Interceptor wiring:** authentication, tracing và application metadata policy.

Đăng ký interceptor bằng extension point của Spring gRPC starter đang dùng. Xác minh thứ tự: transport đã nhận headers trong receive limit; authentication đọc credential; metadata policy kiểm tra các key ứng dụng; authorization quyết định quyền; handler chạy sau cùng.

Không để mỗi service tự tạo một bộ key và policy khác nhau. Đặt Metadata.Key dùng chung trong một lớp, dùng naming convention và policy theo method/service. Nếu có gateway hoặc proxy, kiểm tra giới hạn header của từng hop vì request có thể bị từ chối trước khi tới gRPC server.

Một Spring application integration test nên khởi động đúng Spring context, gửi request metadata gần và vượt ngưỡng, rồi xác minh handler invocation, status và log/metric. In-process test bổ sung coverage nhanh cho logic interceptor, còn transport test xác minh giới hạn thật.

## 15. Những lỗi triển khai thường gặp

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Nhầm metadata với protobuf body | Chỉ cấu hình message-size limit | Cấu hình metadata receive limit riêng |
| Nghĩ server inbound limit giới hạn response headers | Client vẫn nhận response metadata quá lớn | Cấu hình client inbound metadata limit |
| Chỉ giới hạn tổng bytes | Một key lặp quá nhiều lần hoặc value không hợp lệ | Thêm entry-count và per-key policy |
| Forward toàn bộ HTTP headers | Token/cookie/baggage lớn và lộ dữ liệu | Allowlist metadata cần thiết |
| Dùng key grpc- tùy ý | Xung đột trường transport dành riêng | Dùng namespace key ứng dụng |
| Dùng ASCII marshaller cho binary value | Decode sai hoặc dữ liệu hỏng | Dùng binary key hậu tố -bin |
| Log toàn bộ metadata | Lộ credential và thông tin cá nhân | Redact, log kích thước và key an toàn |
| Tăng limit để sửa client gửi headers thừa | Tăng bề mặt DoS | Sửa client, chỉ propagate field cần thiết |
| Chỉ test application interceptor | Bỏ sót transport receive limit | Thêm Netty transport integration test |
| Giả định trailers không cần kiểm soát | Client có thể từ chối response cuối | Kiểm tra response headers và trailers |

## 16. Bài thực hành và câu hỏi tự kiểm tra

### Bài thực hành

1. Cấu hình inbound metadata limit cho Netty server và client bằng builder phù hợp phiên bản.
2. Tạo key text cho correlation ID và key binary cho signed context.
3. Viết validator giới hạn độ dài, số entry, duplicate key và allowlist.
4. Tạo client interceptor chỉ attach correlation ID đã validate.
5. Tạo server interceptor kiểm tra metadata ứng dụng sau khi transport chấp nhận headers.
6. Thử response initial metadata và trailers ở phía server, kiểm tra client inbound limit.
7. Viết test request headers dưới, sát và vượt ngưỡng; xác minh handler không chạy khi transport từ chối.
8. Khởi động Spring application context để kiểm tra builder configuration và interceptor wiring thực tế.

### Câu hỏi tự kiểm tra

**1. Metadata khác protobuf message body thế nào?**  
Metadata là key/value ở headers/trailers của RPC; protobuf message body mang dữ liệu request/response.

**2. Server inbound metadata limit bảo vệ chiều nào?**  
Bảo vệ server khi nhận request metadata từ client.

**3. Ai giới hạn response metadata server gửi về?**  
Client là receiver và cần inbound metadata limit riêng.

**4. Metadata limit có thay message-size limit không?**  
Không. Hai giới hạn bảo vệ hai phần khác nhau của RPC.

**5. Key binary metadata phải có dạng nào?**  
Tên key kết thúc bằng hậu tố -bin và dùng binary marshaller.

**6. Vì sao cần per-key validation khi đã có tổng metadata limit?**  
Để kiểm soát value quá dài, duplicate key và số entry bất thường trong tổng budget.

**7. Metadata của streaming RPC có được gửi lại cho mỗi message không?**  
Không. Metadata thuộc lifecycle của call; các message tiếp theo đi trong protobuf body.

**8. Status nào thường gặp khi inbound metadata vượt transport limit?**  
Thường là RESOURCE_EXHAUSTED; chi tiết phụ thuộc transport/version.

## Tổng kết

Giới hạn metadata bảo vệ headers và trailers của gRPC, tách biệt với giới hạn protobuf message body. Server inbound limit kiểm soát request metadata nhận từ client; client inbound limit kiểm soát response metadata nhận từ server. Kết hợp transport limit với allowlist key, giới hạn value, số entry và xử lý duplicate. Dùng metadata cho credential, trace và correlation nhỏ; không forward toàn bộ HTTP headers hoặc đưa payload nghiệp vụ vào headers. Kiểm thử cả request, response headers/trailers, binary metadata và Spring builder wiring trên đúng transport để chứng minh giới hạn thực sự được áp dụng.

