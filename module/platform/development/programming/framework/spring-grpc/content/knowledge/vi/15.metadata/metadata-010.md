# Không log credential hoặc token

Trong Spring gRPC, thông tin xác thực thường đi qua request metadata, chẳng hạn `authorization: Bearer ...`, API key hoặc credential do `CallCredentials` cung cấp. Metadata giúp client chứng minh danh tính khi gọi service, nhưng giá trị credential phải được giữ bí mật trong toàn bộ vòng đời xử lý. **Không ghi credential hoặc token vào log, trace, metric, exception hay dữ liệu chẩn đoán.**

Một dòng log hữu ích vẫn có thể cho biết RPC nào được gọi, kết quả ra sao, mất bao lâu và request ID nào liên quan. Những thông tin vận hành này đủ để điều tra phần lớn sự cố mà không cần lưu bí mật. Bài học tập trung vào cách tránh rò rỉ khi xử lý metadata và xây dựng logging an toàn cho client/server gRPC.

## 1. Những dữ liệu nào phải được xem là bí mật?

Không chỉ bearer token mới cần bảo vệ. Hãy xem các dữ liệu sau là secret hoặc dữ liệu nhạy cảm:

| Dữ liệu | Ví dụ vị trí | Quy tắc log |
| --- | --- | --- |
| Access token | `authorization: Bearer ...` | Không log value, một phần token hoặc chuỗi đã decode |
| Refresh token | Metadata, body hoặc kết quả đăng nhập | Không log |
| API key | `x-api-key`, custom metadata | Không log |
| Basic credentials | `authorization: Basic ...` | Không log |
| Cookie/session ID | `cookie`, `set-cookie` | Không log |
| Client certificate/private key material | TLS configuration hoặc lỗi nạp certificate | Không log nội dung private key; hạn chế thông tin định danh certificate theo policy |
| Password, one-time code | Message hoặc metadata tùy ứng dụng | Không log |
| Signed URL | URL upload/download có query signature | Không log URL đầy đủ; chữ ký có thể cấp quyền truy cập |

Một giá trị vẫn là bí mật ngay cả khi nó được Base64, URL-encode, chuyển thành JSON hoặc đặt trong binary metadata. Biến đổi định dạng không làm credential trở nên an toàn để ghi log. Với JWT, payload thường chỉ được mã hóa Base64URL chứ không được mã hóa bí mật; decode token để debug cũng có thể làm lộ claim và thông tin cá nhân.

## 2. Credential có thể rò rỉ ở đâu?

Rò rỉ thường xảy ra ở những điểm được thêm vào để chẩn đoán:

- **Client interceptor:** ghi toàn bộ `Metadata` trước khi gửi request, hoặc log đối tượng credentials.
- **Server interceptor:** log toàn bộ request headers khi nhận call hoặc toàn bộ trailers khi đóng call.
- **Service:** ghi `request.toString()`, exception hoặc payload chứa credential.
- **HTTP/2 và gRPC debug logging:** bật log wire/transport quá chi tiết ở môi trường thật.
- **Reverse proxy/API gateway:** access log cấu hình thu thập header `authorization`, cookie hoặc signed URL.
- **Tracing:** copy mọi metadata vào span attributes hoặc baggage để tiện tìm kiếm.
- **Metrics:** đưa token hoặc user-specific value vào label.
- **CI/test report:** in test fixture chứa token thật hoặc exception có chứa credential.
- **Crash report/support bundle:** thu thập request, environment hoặc cấu hình có secret.

Sơ đồ đường đi cần kiểm soát:

```text
Client credentials
       |
       v
ClientCall / CallCredentials / ClientInterceptor
       |
       v
HTTP/2 request headers
       |
       v
Gateway / proxy access logs
       |
       v
ServerInterceptor / authentication
       |
       v
Service / exception handling
       |
       v
Application logs, traces, metrics, support reports

Secret phải được bảo vệ tại mọi điểm; không chỉ ở logger của service.
```

Ví dụ nguy hiểm:

```java
// KHÔNG LÀM: có thể ghi access token và mọi metadata khác.
logger.debug("incoming metadata={}", headers);

// KHÔNG LÀM: request có thể chứa password, token hoặc dữ liệu cá nhân.
logger.info("request={}", request);

// KHÔNG LÀM: exception có thể chứa nguyên value credential.
logger.warn("authentication failed: {}", exception.getMessage());
```

Không thể dựa vào việc một môi trường hiện tại chưa in token để kết luận cách log này an toàn. Khi thêm interceptor, debug flag hoặc thư viện mới, nội dung được ghi có thể thay đổi.

## 3. Dùng allowlist thay vì log toàn bộ rồi cố che secret

Cách an toàn hơn là **chỉ chọn những trường đã được duyệt để log**. Đây là allowlist:

| Trường có thể log (nếu policy cho phép) | Vì sao hữu ích |
| --- | --- |
| RPC full method name | Xác định phương thức như `orders.v1.OrderService/GetOrder` |
| gRPC status code | Biết call thành công hay thất bại |
| Duration | Phân tích độ trễ |
| Request ID do hệ thống tạo/đã kiểm tra | Liên kết log giữa các thành phần |
| Client version | Phân tích tương thích nếu không chứa dữ liệu cá nhân |
| Error category nội bộ | Phân nhóm sự cố mà không đưa message nhạy cảm ra log |

Các trường mặc định không được log:

- Toàn bộ `Metadata`, request message, response message hoặc trailers.
- Value của `authorization`, `proxy-authorization`, `cookie`, `set-cookie`, `x-api-key` và các key credential riêng của ứng dụng.
- Raw token, token fragment, JWT claims chưa được duyệt, password, private key hoặc signed URL.
- Exception message nếu chưa biết chắc nó không chứa input nhạy cảm.
- Toàn bộ baggage hoặc span attributes được sao chép tự động từ metadata.

**Allowlist phải được áp dụng ở nơi tạo log.** Một bộ lọc chỉ che key `authorization` nhưng vẫn cho log các custom key khác có thể bỏ sót secret do ứng dụng bổ sung sau này. Không dùng denylist ngắn như `remove("authorization")` rồi ghi tất cả phần còn lại.

## 4. Viết server interceptor chỉ log trường an toàn

Ví dụ sau ghi tên RPC, status code, thời gian và request ID đã được giới hạn định dạng. Nó không đọc hoặc ghi log `authorization`, không in `headers`/`trailers` và không đưa `status.getDescription()` vào log.

```java
import io.grpc.ForwardingServerCall;
import io.grpc.Metadata;
import io.grpc.ServerCall;
import io.grpc.ServerCallHandler;
import io.grpc.ServerInterceptor;
import io.grpc.Status;
import java.util.concurrent.TimeUnit;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class SafeRpcLoggingInterceptor implements ServerInterceptor {
    private static final Logger log =
        LoggerFactory.getLogger(SafeRpcLoggingInterceptor.class);

    private static final Metadata.Key<String> REQUEST_ID =
        Metadata.Key.of(
            "x-request-id",
            Metadata.ASCII_STRING_MARSHALLER);

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        String requestId = headers.get(REQUEST_ID);
        // Chỉ chấp nhận ID ngắn, không có ký tự điều khiển.
        if (requestId != null
                && !requestId.matches("[A-Za-z0-9._-]{1,64}")) {
            requestId = null;
        }

        final String safeRequestId = requestId;
        final String method = call.getMethodDescriptor().getFullMethodName();
        final long startedAt = System.nanoTime();

        ServerCall<ReqT, RespT> wrapped =
            new ForwardingServerCall.SimpleForwardingServerCall<ReqT, RespT>(
                    call) {
                @Override
                public void close(Status status, Metadata trailers) {
                    long durationMs = TimeUnit.NANOSECONDS.toMillis(
                        System.nanoTime() - startedAt);

                    log.info(
                        "grpc_server_call method={} status={} duration_ms={} request_id={}",
                        method,
                        status.getCode(),
                        durationMs,
                        safeRequestId);

                    // Giữ nguyên status và trailers của gRPC.
                    super.close(status, trailers);
                }
            };

        return next.startCall(wrapped, headers);
    }
}
```

Đây là logging interceptor tối giản, không phải authentication interceptor. Request ID từ client vẫn là input không tin cậy; regex chỉ giới hạn hình thức và ngăn ký tự điều khiển, không chứng minh danh tính. Với hệ thống public, nên tạo ID tại gateway/server tin cậy hoặc dùng ID đã được kiểm tra trước khi log.

Trong production, có thể bổ sung error category đã chuẩn hóa hoặc tenant pseudonym nếu policy cho phép. Không thêm `status.getDescription()`, `headers.toString()` hoặc `trailers.toString()` chỉ để tăng chi tiết log.

## 5. Xử lý lỗi xác thực mà không lộ token

Server cần đủ thông tin để phân biệt lỗi xác thực, nhưng không cần ghi credential để làm điều đó.

| Tình huống | Log an toàn | Log không an toàn |
| --- | --- | --- |
| Không có credential | `auth_result=missing` | Dump toàn bộ headers để xem token có vắng mặt không |
| Token sai chữ ký | `auth_result=invalid_signature` hoặc category cố định | In token hoặc JWT payload |
| Token hết hạn | `auth_result=expired` | In toàn bộ claim hoặc token |
| Audience không đúng | `auth_result=audience_mismatch` | In token và toàn bộ thông tin xác thực |
| Backend introspection unavailable | `auth_result=verification_unavailable` | In request/exception chứa authorization value |
| Caller thiếu quyền | `authz_result=denied`, policy code | In toàn bộ principal/token hoặc dữ liệu tài nguyên |

Ví dụ xử lý lỗi:

```java
try {
    VerifiedPrincipal principal = tokenVerifier.verify(accessToken);
    // Tiếp tục xử lý với principal đã xác thực.
} catch (ExpiredTokenException ex) {
    logger.warn(
        "grpc_authentication_failed category={} rpc={}",
        "expired",
        methodName);
    throw Status.UNAUTHENTICATED
        .withDescription("Authentication required")
        .asRuntimeException();
} catch (InvalidTokenException ex) {
    logger.warn(
        "grpc_authentication_failed category={} rpc={}",
        "invalid",
        methodName);
    throw Status.UNAUTHENTICATED
        .withDescription("Authentication required")
        .asRuntimeException();
}
```

Tên exception và `tokenVerifier` là ví dụ theo ứng dụng. Không log `accessToken`, `ex` hoặc `ex.getMessage()` nếu thư viện xác thực có thể đưa input vào thông báo lỗi. Có thể ghi stack trace ở một hệ thống lỗi nội bộ đã được kiểm soát khi chắc chắn exception không mang secret; mặc định hãy ghi category và mã lỗi đã chuẩn hóa.

Không thay mọi lỗi thành `UNAUTHENTICATED`. Nếu dịch vụ xác minh token phụ thuộc bị ngừng hoạt động, trả status vận hành phù hợp như `UNAVAILABLE` và log category của dependency failure. Không cấp quyền khi không xác minh được credentials.

## 6. Tracing, baggage và metrics cũng phải tránh secret

Không chỉ application logger mới có thể lưu dữ liệu. OpenTelemetry span attributes, baggage, event và exporter có thể được lưu lâu dài, tìm kiếm rộng và chuyển tới nhiều hệ thống.

- Không đặt bearer token, API key hoặc password vào span attribute.
- Không đưa token vào W3C baggage; baggage được truyền tiếp qua các dịch vụ theo propagator.
- Không sao chép toàn bộ gRPC metadata vào span attributes.
- Chỉ thêm các thuộc tính đã được duyệt như RPC method, status code và duration.
- Không dùng token, session ID hoặc request ID riêng cho từng call làm metric label; chúng có thể gây rò rỉ và cardinality rất cao.
- Kiểm tra processor/exporter có cơ chế lọc/redact phù hợp, nhưng vẫn ngăn secret ngay từ nguồn.

Trace ID và span ID là định danh quan sát, không phải credential. Tuy nhiên, chúng vẫn có thể liên kết hoạt động người dùng; áp dụng chính sách truy cập và retention của hệ thống observability.

## 7. Cấu hình gateway, proxy và môi trường Spring

Một ứng dụng Spring gRPC có thể an toàn ở tầng service nhưng vẫn rò token ở gateway hoặc proxy:

1. **Reverse proxy/API gateway:** cấu hình access log chỉ ghi các header được duyệt. Loại bỏ hoặc che `authorization`, cookie, signed URL và custom credential headers khỏi log.
2. **Spring Boot logging:** tránh bật debug/trace toàn diện cho gRPC, authentication hoặc HTTP/2 ở production nếu chưa đánh giá nội dung log.
3. **Client credentials:** dùng `CallCredentials` hoặc integration phù hợp để gắn token; không log đối tượng credentials hoặc `Metadata` sau khi gắn.
4. **Server interceptors:** tách authentication khỏi logging. Authentication chỉ log kết quả đã chuẩn hóa; logging interceptor chỉ ghi allowlist.
5. **Error handling:** không đưa credential vào `Status` description, custom trailers, response message hoặc exception gửi về client.
6. **Log storage:** giới hạn quyền đọc, thời hạn lưu, khả năng tải xuống và việc đính kèm log vào ticket/support bundle.

Không có một mức logging mặc định áp dụng an toàn cho mọi phiên bản starter hoặc proxy. Hãy kiểm tra cấu hình thực tế của các thành phần triển khai, đặc biệt khi bật wire logging để điều tra sự cố.

## 8. Kiểm thử bảo đảm token không xuất hiện trong log

Một kiểm thử bảo mật nên dùng **canary secret giả** có giá trị duy nhất, ví dụ `test-secret-DO-NOT-LOG-7f3a`. Gửi nó qua metadata trong test, thực hiện RPC thành công và thất bại, rồi kiểm tra toàn bộ log được thu trong phạm vi test không chứa chuỗi đó.

| Ca kiểm thử | Điều cần xác minh |
| --- | --- |
| RPC với bearer token hợp lệ | Log không chứa token, JWT fragment hoặc header authorization |
| Token sai/hết hạn | Log chỉ có category/status, không có token hoặc exception message nhạy cảm |
| Key credential tùy biến | `x-api-key` và custom auth key không xuất hiện trong log |
| Binary metadata nhạy cảm | Không dump `byte[]`, Base64 hoặc object metadata vào log |
| Service exception | Request/exception `toString()` không được ghi nếu có thể chứa secret |
| Response trailers | Không ghi toàn bộ trailers; không trả credential trong custom metadata |
| Tracing | Span attributes và baggage không chứa canary secret |
| Gateway/proxy | Access log không chứa authorization, cookie hoặc signed URL |
| CI/test report | Test output, assertion message và fixture không chứa secret thật |

Ví dụ ý tưởng kiểm thử với Logback `ListAppender`:

```java
String canary = "test-secret-DO-NOT-LOG-7f3a";

// Gửi canary qua credentials/metadata tới test server.
// Thực hiện cả RPC thành công và RPC bị UNAUTHENTICATED.

String capturedLogs = listAppender.list.stream()
    .map(event -> event.getFormattedMessage())
    .reduce("", (left, right) -> left + "\n" + right);

assertFalse(capturedLogs.contains(canary));
assertFalse(capturedLogs.contains("Bearer " + canary));
```

Đây là phác thảo; cấu hình appender và logger phụ thuộc backend logging của dự án. Test cần thu log từ các logger liên quan đến interceptor, authentication và service. Kiểm tra thêm trace exporter và proxy access log trong integration/security test; chỉ kiểm tra một logger không chứng minh toàn hệ thống đã an toàn.

## 9. Nếu token đã bị ghi log

Nếu phát hiện credential thật trong log hoặc trace:

1. **Thu hồi hoặc rotate credential** theo cơ chế phát hành token/API key. Xem token đã bị lộ là có thể sử dụng được cho tới khi bị thu hồi hoặc hết hiệu lực.
2. Xác định nguồn ghi log và những hệ thống đã nhận bản sao: application log, gateway, tracing backend, CI, ticket, support bundle và bản export.
3. Hạn chế truy cập log liên quan; xử lý/xóa bản sao theo quy trình retention và incident response của tổ chức.
4. Kiểm tra dấu hiệu sử dụng bất thường bằng audit event và metadata không nhạy cảm; không tiếp tục sao chép token vào báo cáo sự cố.
5. Sửa nguồn logging và thêm test canary để ngăn tái diễn.

Chỉ xóa một dòng ở application log là chưa đủ nếu proxy hoặc tracing exporter đã lưu bản sao. Cần đánh giá toàn bộ nơi dữ liệu được chuyển tới.

## 10. Bài tập vận dụng

Một ứng dụng Spring gRPC dùng `authorization: Bearer ...` để gọi `PaymentService.AuthorizePayment`. Khi điều tra lỗi, nhóm phát hiện interceptor đang ghi `headers` ở mức DEBUG và gateway cũng log tất cả request headers.

**Yêu cầu:**

1. Chỉ ra các điểm rò rỉ trong client interceptor, server interceptor, gateway, tracing và exception handling.
2. Thay việc dump metadata bằng allowlist gồm RPC method, status code, duration và request ID đã kiểm tra.
3. Giữ nguyên token trong luồng xác thực nhưng loại bỏ nó khỏi log, trace attributes, baggage và metrics.
4. Chuẩn hóa log cho các trường hợp token thiếu, sai chữ ký, hết hạn và dependency xác minh bị unavailable.
5. Viết test canary secret để kiểm tra log của RPC thành công và thất bại không chứa token.
6. Mô tả cách rotate token và tìm các bản sao nếu credential thật đã xuất hiện trong log.

**Câu hỏi tự kiểm tra:**

- Vì sao Base64 hoặc decode JWT không làm token an toàn để ghi log?
- Vì sao allowlist an toàn hơn việc log tất cả rồi che một số key?
- Những thành phần nào ngoài application logger có thể lưu request metadata?
- Có nên đưa token vào OpenTelemetry baggage hoặc metric label không?
- Vì sao không nên log `exception.getMessage()` trong mọi lỗi xác thực?
- Khi phát hiện token thật trong log, vì sao cần rotate credential và rà soát các bản sao?

**Ghi nhớ:** Không log credential hoặc token ở bất kỳ dạng nào. Hãy giữ bí mật trong luồng xác thực, chỉ ghi các trường vận hành đã được duyệt, kiểm soát gateway/tracing/CI và dùng canary secret để kiểm tra log. Nếu token thật đã lộ, thu hồi hoặc rotate ngay và rà soát toàn bộ hệ thống đã nhận bản sao.
