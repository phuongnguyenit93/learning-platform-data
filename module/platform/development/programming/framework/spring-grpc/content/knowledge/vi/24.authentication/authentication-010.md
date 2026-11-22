# Metadata không an toàn khi dùng plaintext

## 1. Metadata không tự được mã hóa

Trong **Spring gRPC**, metadata mang thông tin phụ trợ cho RPC như bearer token, tenant context, correlation ID, locale hoặc thông tin tracing. Metadata được truyền cùng HTTP/2 headers và trailers của gRPC. API Metadata chỉ cung cấp cách biểu diễn và chuyển các giá trị; nó không mã hóa hay xác thực dữ liệu.

Nếu client kết nối bằng HTTP/2 plaintext (h2c), toàn bộ lưu lượng trên kết nối không được TLS bảo vệ. Điều này bao gồm:

- Metadata request như authorization, tenant hoặc API key.
- Metadata response/trailers như thông tin lỗi hoặc token refresh nếu ứng dụng tự đặt.
- Protobuf message body và các response message.
- Thông tin giao thức có thể tiết lộ method, kích thước và nhịp giao tiếp.

Vì vậy, bearer token đặt trong metadata không an toàn chỉ vì nó nằm trong header thay vì Protobuf body. Trên đường truyền plaintext, người có khả năng quan sát hoặc can thiệp mạng có thể đọc hoặc sửa dữ liệu.

## 2. Plaintext (h2c) tạo ra rủi ro gì?

Khi dùng plaintext, client không thiết lập TLS cho kết nối gRPC. Trên mạng không đáng tin cậy, một bên có vị trí quan sát phù hợp có thể:

- **Đọc credential:** lấy bearer token, API key hoặc thông tin nhận diện được gửi trong metadata.
- **Đọc dữ liệu nghiệp vụ:** xem request/response body, kể cả khi metadata không chứa dữ liệu nhạy cảm.
- **Sửa dữ liệu trên đường truyền:** thay đổi metadata hoặc message nếu có thể can thiệp kết nối.
- **Giả mạo peer:** client không xác minh certificate của server vì không có TLS handshake.
- **Phát lại credential bị lộ:** dùng token còn hiệu lực để gọi service trong phạm vi quyền của token.

H2c không có nghĩa là chỉ metadata bị lộ. Toàn bộ dữ liệu ứng dụng đi qua kết nối đều thiếu tính bí mật và tính toàn vẹn do TLS cung cấp.

~~~mermaid
flowchart LR
    C[gRPC client] -->|HTTP/2 plaintext| N((Mạng))
    N --> S[Spring gRPC server]
    A[Người quan sát hoặc kẻ can thiệp] -.->|Có thể đọc hoặc sửa| N
~~~

Không nên xem mạng nội bộ, VPC hoặc Kubernetes cluster là vùng tự động an toàn. Một workload bị xâm nhập, node dùng chung, cấu hình network sai hoặc proxy không tin cậy có thể tạo đường quan sát lưu lượng.

## 3. Metadata nào thường nhạy cảm?

| Metadata | Ví dụ | Rủi ro khi plaintext |
| --- | --- | --- |
| Authorization | Bearer access token | Chiếm quyền gọi API cho tới khi token hết hạn/thu hồi |
| API key | Key của ứng dụng tích hợp | Mạo danh ứng dụng hoặc vượt quota |
| Tenant/user context | Tenant ID, user ID, role | Lộ cấu trúc khách hàng và ngữ cảnh truy cập |
| Session/correlation token | Token nối nhiều thao tác | Có thể liên kết hoặc chiếm phiên nếu token có quyền |
| Internal routing data | Tên service, cluster, route | Tiết lộ topology và thông tin nội bộ |
| Custom response trailers | Error detail hoặc dữ liệu nghiệp vụ | Rò rỉ thông tin qua response metadata |

Không phải mọi metadata đều là bí mật. Request ID hoặc trace ID thường có thể dùng để correlation, nhưng vẫn cần đánh giá chính sách riêng tư và khả năng liên kết dữ liệu. Hãy phân loại metadata theo độ nhạy cảm thay vì mặc định mọi header đều vô hại.

## 4. ASCII và binary metadata không phải cơ chế bảo mật

gRPC Java biểu diễn metadata bằng key và value có kiểu:

- Key metadata là tên ASCII viết thường.
- Value ASCII dùng Metadata.ASCII_STRING_MARSHALLER.
- Binary metadata dùng key có hậu tố -bin và Metadata.BINARY_BYTE_MARSHALLER.

Ví dụ:

~~~java
import io.grpc.Metadata;

Metadata headers = new Metadata();

Metadata.Key<String> authorization =
        Metadata.Key.of(
                "authorization",
                Metadata.ASCII_STRING_MARSHALLER);

Metadata.Key<byte[]> opaqueContext =
        Metadata.Key.of(
                "app-context-bin",
                Metadata.BINARY_BYTE_MARSHALLER);

headers.put(authorization, "Bearer <access-token>");
headers.put(opaqueContext, new byte[] { 1, 2, 3 });
~~~

Hậu tố -bin chỉ báo giá trị metadata là dữ liệu nhị phân và được serialize theo quy tắc gRPC. Nó không mã hóa, không ký và không che giấu giá trị. Base64, encoding hoặc chuyển token thành byte array cũng không tạo ra confidentiality.

Không đưa dữ liệu lớn vào metadata. Metadata được truyền như HTTP/2 headers/trailers và thường chịu giới hạn kích thước ở client, server hoặc proxy. Payload nghiệp vụ nên nằm trong Protobuf message; credential và metadata nhạy cảm cần được bảo vệ bằng TLS.

## 5. TLS bảo vệ metadata và message trên đường truyền

TLS cung cấp ba thuộc tính quan trọng cho kết nối:

- **Confidentiality:** mã hóa metadata, message body và trailers trên đoạn kết nối được bảo vệ.
- **Integrity:** phát hiện dữ liệu bị sửa trên đường truyền.
- **Server authentication:** client xác minh server thông qua certificate và hostname.

Khi client dùng TLS đúng cách, người quan sát mạng không thể đọc trực tiếp bearer token hoặc Protobuf payload trong kết nối đã mã hóa. Client vẫn phải xác minh certificate chain và hostname. Tắt kiểm tra certificate hoặc dùng trust manager chấp nhận mọi certificate làm mất bảo đảm server authentication.

Ví dụ client gRPC Java:

~~~java
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;

ManagedChannel channel = ManagedChannelBuilder
        .forAddress("catalog.internal.example", 9090)
        .useTransportSecurity()
        .build();
~~~

Channel sử dụng TLS và xác minh certificate theo trust configuration của runtime. Trong môi trường dùng private CA, cấu hình trust store/certificate authority phù hợp và bảo đảm hostname trong certificate khớp địa chỉ client sử dụng.

Chỉ dùng usePlaintext() cho môi trường local/test được kiểm soát, chẳng hạn loopback hoặc test channel không mang credential thật. Không dùng nó như cách sửa lỗi certificate trong staging/production.

## 6. Gửi bearer token qua metadata trên channel TLS

Sau khi channel được bảo vệ bằng TLS, client có thể gửi access token trong authorization metadata. Ví dụ minh họa với header tĩnh:

~~~java
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;
import io.grpc.Metadata;
import io.grpc.stub.MetadataUtils;
import com.example.catalog.v1.CatalogServiceGrpc;
import com.example.catalog.v1.GetItemRequest;
import com.example.catalog.v1.GetItemResponse;

Metadata headers = new Metadata();
Metadata.Key<String> authorization =
        Metadata.Key.of(
                "authorization",
                Metadata.ASCII_STRING_MARSHALLER);
headers.put(authorization, "Bearer <access-token>");

ManagedChannel channel = ManagedChannelBuilder
        .forAddress("catalog.internal.example", 9090)
        .useTransportSecurity()
        .build();

CatalogServiceGrpc.CatalogServiceBlockingStub stub =
        CatalogServiceGrpc.newBlockingStub(channel)
                .withInterceptors(
                        MetadataUtils.newAttachHeadersInterceptor(headers));

GetItemResponse response = stub.getItem(
        GetItemRequest.newBuilder()
                .setItemId("item-42")
                .build());
~~~

Đây là ví dụ minh họa việc gắn header cố định vào call. Với token hết hạn hoặc thay đổi theo người dùng, nên dùng CallCredentials để lấy credential theo từng RPC, refresh theo chính sách identity provider và tránh chia sẻ mutable token state giữa nhiều request.

TLS bảo vệ token khi truyền trên kết nối. Nó không thay thế việc xác minh chữ ký, issuer, audience, expiry và authorization ở server. Server vẫn phải xác thực token và kiểm tra quyền trước khi xử lý nghiệp vụ.

## 7. TLS kết thúc ở gateway: bảo vệ theo từng hop

TLS chỉ bảo vệ đoạn kết nối giữa hai peer thực hiện handshake. Nếu kiến trúc có gateway/proxy kết thúc TLS rồi mở một kết nối plaintext tới backend, metadata sẽ được giải mã tại gateway và tiếp tục đi qua mạng nội bộ dưới dạng plaintext.

~~~mermaid
flowchart LR
    C[Client] -->|TLS| G[Gateway / TLS termination]
    G -->|Plaintext h2c| S[Spring gRPC service]
    X[Observer trên mạng backend] -.->|Có thể đọc metadata và payload| S
~~~

Các lựa chọn triển khai:

1. **TLS end-to-end:** client thiết lập TLS trực tiếp tới gRPC service, nếu topology cho phép.
2. **TLS ở cả hai hop:** client-to-gateway dùng TLS và gateway-to-service cũng dùng TLS.
3. **mTLS giữa các workload:** gateway và service xác minh certificate của nhau, đồng thời mã hóa hop nội bộ.

Nếu gateway cần đọc metadata để định tuyến hoặc xác thực, gateway là một trust boundary. Hạn chế ai có quyền quản trị gateway, không ghi credential vào access log và chỉ chuyển tiếp những metadata được cho phép.

## 8. mTLS bảo vệ service-to-service

Mutual TLS yêu cầu cả client và server xác minh certificate của peer. Nó phù hợp để bảo vệ kết nối giữa gateway, service và workload nội bộ:

| Thành phần | Việc xác minh |
| --- | --- |
| Client workload | Xác minh server certificate và hostname |
| Server workload | Xác minh client certificate theo trust chain/policy |
| Identity mapping | Ánh xạ certificate identity/SAN sang workload principal |
| Authorization | Quyết định workload được gọi method nào |

mTLS vừa mã hóa metadata/payload trên hop vừa xác thực workload ở tầng transport. Tuy nhiên, certificate của gateway không tự chứng minh người dùng cuối có quyền đọc một đơn hàng. Nếu request mang user access token, service vẫn phải xác thực token và áp dụng authorization cho user hoặc delegated principal.

Không dùng một certificate dùng chung cho mọi workload nếu cần audit và thu hồi theo từng service. Quản lý vòng đời certificate, rotation, trust bundle và thu hồi theo quy trình của nền tảng.

## 9. Metadata có thể lộ sau khi TLS đã giải mã

TLS không bảo vệ metadata khỏi chính endpoint hoặc intermediary được tin cậy nhưng cấu hình sai. Metadata có thể xuất hiện trong:

- Gateway access log hoặc debug log.
- gRPC interceptor log toàn bộ headers/trailers.
- Distributed tracing baggage hoặc span attributes.
- Exception message và error reporting.
- APM agent, packet capture hoặc diagnostic dump ở endpoint.

Vì vậy:

- Redact authorization, cookie, API key và custom secret headers.
- Không ghi toàn bộ Metadata object vào log.
- Chỉ đưa allowlist các trường an toàn vào trace.
- Hạn chế quyền truy cập log/trace và đặt retention phù hợp.
- Không phản chiếu token hoặc credential trong response trailers.
- Kiểm tra cấu hình proxy để không forward header nhạy cảm sang service không cần chúng.

TLS bảo vệ dữ liệu khi truyền qua mạng; kiểm soát log/tracing bảo vệ dữ liệu sau khi endpoint đã giải mã.

## 10. Chọn metadata tối thiểu và an toàn

Trước khi thêm metadata custom, xác định mục đích, chủ sở hữu và vòng đời:

| Trường | Nên dùng? | Quy tắc |
| --- | --- | --- |
| authorization | Có khi API dùng bearer token | Chỉ gửi qua TLS; redact trong log |
| traceparent / tracing context | Có theo tracing standard | Không đưa secret hoặc PII vào baggage |
| x-request-id | Có nếu cần correlation | Dùng ID không mang dữ liệu nhạy cảm |
| tenant-id | Chỉ khi contract yêu cầu | Server phải đối chiếu với principal đã xác thực |
| user-role | Tránh tin trực tiếp | Role phải đến từ credential/policy đã xác minh |
| password/API secret | Tránh gửi lặp qua metadata | Ưu tiên token ngắn hạn hoặc credential mechanism phù hợp |
| business payload | Không dùng metadata | Đặt trong Protobuf message |

Metadata từ client là input không đáng tin cậy. Server không được dùng tenant, role hoặc user ID do client tự gửi làm căn cứ cấp quyền nếu chưa đối chiếu với principal đã xác thực.

## 11. Kiểm thử plaintext và TLS

Kiểm thử cần chứng minh cả transport security và hành vi metadata:

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| Client plaintext kết nối server chỉ bật TLS | Handshake/kết nối thất bại; không xử lý RPC |
| Client TLS với certificate server hợp lệ | Kết nối thành công |
| Certificate hết hạn hoặc không thuộc trust chain | Client từ chối handshake |
| Hostname không khớp certificate | Client từ chối server identity |
| Bearer token gửi qua TLS | Server nhận metadata và xác minh token |
| Token sai chữ ký hoặc hết hạn | UNAUTHENTICATED |
| Token hợp lệ nhưng thiếu quyền | PERMISSION_DENIED |
| Metadata binary kết thúc bằng -bin | Được parse theo binary marshaller nhưng vẫn chỉ an toàn khi transport được bảo vệ |
| Gateway kết thúc TLS rồi gọi backend plaintext | Xác định rõ hop backend là trust boundary; test cấu hình TLS/mTLS nếu cần |
| Logging/tracing bật debug | Authorization và secret headers bị redact |

Trong test, dùng certificate và token giả lập riêng. Không dùng credential production để kiểm tra plaintext hoặc packet capture. Kiểm tra cả metadata request và response trailers; tránh để secret bị phản chiếu qua error path.

## 12. Sai lầm thường gặp

1. **Cho rằng metadata tự được mã hóa.** Metadata chỉ là headers/trailers; plaintext transport để lộ giá trị.
2. **Cho rằng hậu tố -bin là encryption.** Binary marshalling chỉ định dạng dữ liệu.
3. **Chỉ bảo vệ metadata mà quên message body.** h2c làm cả request/response payload thiếu TLS.
4. **Dùng usePlaintext() trong production.** Token và dữ liệu nghiệp vụ có thể bị đọc/sửa.
5. **Tắt certificate verification để sửa lỗi TLS.** Client có thể kết nối nhầm server.
6. **Cho rằng TLS ở gateway bảo vệ luôn hop backend.** Mỗi hop cần được đánh giá và bảo vệ riêng.
7. **Để proxy/interceptor ghi authorization metadata.** Credential vẫn có thể lộ sau khi TLS kết thúc.
8. **Tin tenant/role trong metadata do client gửi.** Metadata là input; authorization phải dựa trên principal đã xác minh.
9. **Coi mTLS là authorization của user.** mTLS xác thực workload/peer, không tự cấp quyền nghiệp vụ cho người dùng.

## 13. Bài tập vận dụng

Với catalog.v1.CatalogService/GetItem:

1. Tạo channel plaintext trong môi trường test và ghi nhận server TLS-only từ chối kết nối.
2. Cấu hình client TLS với trust store phù hợp; thử certificate sai CA và hostname không khớp.
3. Gửi bearer token trong authorization metadata qua TLS; xác minh server kiểm tra token.
4. Thêm một binary metadata key kết thúc bằng -bin và giải thích vì sao nó không phải encryption.
5. Mô phỏng TLS termination ở gateway; kiểm tra gateway-to-service hop có TLS/mTLS hay đang plaintext.
6. Bật logging/tracing và xác minh authorization, API key cùng secret custom headers được redact.
7. Thử tenant ID do client tự gửi khác tenant trong principal; xác minh server từ chối hoặc bỏ qua giá trị không đáng tin cậy.

**Tiêu chí hoàn thành:** người học giải thích được metadata không có bảo mật riêng, nhận diện rủi ro của h2c, cấu hình TLS/mTLS đúng cho từng hop, gửi credential qua metadata an toàn và ngăn rò rỉ qua proxy/log/tracing.

### Tài liệu tham khảo

- [gRPC Metadata](https://grpc.io/docs/guides/metadata/): metadata headers/trailers trong gRPC.
- [gRPC Authentication](https://grpc.io/docs/guides/auth/): TLS, mTLS và credential.
- [gRPC Java Metadata API](https://grpc.github.io/grpc-java/javadoc/io/grpc/Metadata.html): ASCII và binary metadata.
- [gRPC Java ManagedChannelBuilder API](https://grpc.github.io/grpc-java/javadoc/io/grpc/ManagedChannelBuilder.html): cấu hình transport security trên client channel.
- [Spring gRPC Reference](https://docs.spring.io/spring-grpc/reference/): tích hợp gRPC client/server trong Spring.
