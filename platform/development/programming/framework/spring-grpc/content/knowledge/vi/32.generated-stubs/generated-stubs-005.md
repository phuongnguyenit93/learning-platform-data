# withDeadline và withCallCredentials

Generated stub của gRPC Java cho phép cấu hình ngân sách thời gian và thông tin xác thực ngay trên từng lời gọi. Hai API thường dùng là **withDeadline / withDeadlineAfter** để giới hạn thời gian RPC và **withCallCredentials** để gắn credential vào metadata của call. Cả hai đều trả về stub mới vì generated stub là immutable.

Trong **Spring gRPC**, cách dùng phổ biến là quản lý channel và stub nền theo vòng đời ứng dụng, sau đó tạo stub dẫn xuất gần thời điểm gọi để áp deadline theo nghiệp vụ. Credential có thể được cung cấp dưới dạng Spring bean dùng chung nếu implementation thread-safe và lấy token động cho từng RPC. Deadline và credential giải quyết hai vấn đề khác nhau: deadline giới hạn thời gian chờ; credential chứng minh danh tính hoặc quyền truy cập của caller.

## 1. Phân biệt hai API

| API | Mục đích | Kết quả |
| --- | --- | --- |
| withDeadline(deadline) | Dùng một mốc hết hạn tuyệt đối đã có | Stub mới mang deadline được chỉ định |
| withDeadlineAfter(duration, unit) | Tạo mốc hết hạn từ thời lượng tương đối tại thời điểm gọi | Stub mới mang deadline được tính ngay lúc cấu hình |
| withCallCredentials(credentials) | Gắn cơ chế tạo metadata xác thực cho RPC | Stub mới mang CallCredentials trong CallOptions |

Ví dụ:

~~~java
var baseStub = PaymentServiceGrpc.newBlockingStub(channel);

var securedStub = baseStub.withCallCredentials(bearerCredentials);

var boundedStub = securedStub.withDeadlineAfter(
    700, TimeUnit.MILLISECONDS);

PaymentResponse response = boundedStub.getPayment(request);
~~~

securedStub và boundedStub là hai đối tượng mới; baseStub không bị thay đổi. Stub dẫn xuất giữ cấu hình đã đặt trước đó, nên boundedStub vừa có credential vừa có deadline.

## 2. withDeadline và withDeadlineAfter

### Deadline tuyệt đối

Deadline phù hợp khi nhiều thao tác thuộc cùng một logical request phải chia sẻ một mốc kết thúc. Có thể tạo deadline một lần rồi truyền cho các lời gọi con:

~~~java
Deadline overall = Deadline.after(
    1200, TimeUnit.MILLISECONDS);

PaymentResponse response = baseStub
    .withDeadline(overall)
    .getPayment(request);
~~~

Deadline dựa trên clock đơn điệu, tránh phụ thuộc việc đồng hồ hệ thống bị chỉnh giờ trong lúc request chạy. Không lưu deadline đã tạo vào singleton để dùng cho các request sau; mốc hết hạn vẫn tiếp tục trôi.

### Deadline tương đối

withDeadlineAfter phù hợp khi mỗi RPC có ngân sách riêng tính từ thời điểm chuẩn bị call:

~~~java
PaymentResponse response = baseStub
    .withDeadlineAfter(500, TimeUnit.MILLISECONDS)
    .getPayment(request);
~~~

Stub nền vẫn dùng được cho lần gọi tiếp theo. Tuy nhiên, không tạo stub có withDeadlineAfter trong constructor của Spring bean rồi giữ nó lâu dài. Deadline được tính ngay lúc phương thức được gọi; stub lưu lâu có thể hết hạn trước khi request kế tiếp bắt đầu.

## 3. Giữ deadline cha cho lời gọi downstream

Trong một service Spring gRPC, RPC hiện tại có thể gọi thêm service khác. Ngân sách downstream phải nằm trong deadline còn lại của request cha. Có thể chọn deadline sớm hơn giữa ngân sách con và deadline của Context hiện hành:

~~~java
private PaymentServiceBlockingStub stubForCurrentCall(
        Duration childBudget) {

    if (childBudget.isZero() || childBudget.isNegative()) {
        throw new IllegalArgumentException(
            "childBudget must be positive");
    }

    Deadline child = Deadline.after(
        childBudget.toNanos(), TimeUnit.NANOSECONDS);
    Deadline parent = Context.current().getDeadline();

    if (parent != null && parent.isBefore(child)) {
        child = parent;
    }

    return baseStub.withDeadline(child);
}
~~~

Nếu deadline cha đã hết, call con cũng hết hạn; không cấp lại một khoảng thời gian mới để kéo dài request. Nếu service cha cần thời gian xử lý response, hãy trừ phần dự phòng khỏi childBudget trước khi tạo deadline.

Khi offload công việc sang executor khác, capture Context trước khi submit và dùng Context.wrap hoặc fixedContextExecutor. Nếu context cha bị mất, lời gọi con có thể không còn nhận đúng cancellation và deadline của request ban đầu.

## 4. withCallCredentials gắn credential vào RPC

CallCredentials là abstraction của gRPC Java để tạo metadata xác thực cho một call. Nó thích hợp cho bearer token, token dịch vụ hoặc credential được làm mới định kỳ. Credential không nên được nối thủ công vào từng request business message.

Ví dụ gắn credential vào stub:

~~~java
CallCredentials credentials = bearerTokenCredentials;

PaymentServiceBlockingStub securedStub =
    PaymentServiceGrpc.newBlockingStub(channel)
        .withCallCredentials(credentials);
~~~

Khi RPC được tạo, gRPC gọi applyRequestMetadata của credential để lấy metadata cần gửi. Credential có thể được gọi nhiều lần và trên các call đồng thời; implementation phải an toàn khi dùng từ nhiều thread.

## 5. Tạo Bearer CallCredentials không chặn executor

Ví dụ dưới đây dùng TokenProvider trả về CompletionStage để việc lấy token có thể bất đồng bộ. Phần metadata chỉ được tạo khi call cần credential:

~~~java
import io.grpc.CallCredentials;
import io.grpc.Metadata;
import io.grpc.SecurityLevel;
import io.grpc.Status;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.Executor;

public final class BearerTokenCredentials extends CallCredentials {

    private static final Metadata.Key<String> AUTHORIZATION =
        Metadata.Key.of(
            "authorization",
            Metadata.ASCII_STRING_MARSHALLER);

    private final TokenProvider tokenProvider;

    public BearerTokenCredentials(TokenProvider tokenProvider) {
        this.tokenProvider = tokenProvider;
    }

    @Override
    public void applyRequestMetadata(
            RequestInfo requestInfo,
            Executor appExecutor,
            MetadataApplier applier) {

        if (requestInfo.getSecurityLevel()
                != SecurityLevel.PRIVACY_AND_INTEGRITY) {
            applier.fail(Status.UNAUTHENTICATED.withDescription(
                "bearer token requires a protected transport"));
            return;
        }

        CompletionStage<String> tokenStage;
        try {
            tokenStage = tokenProvider.fetchAccessToken();
        } catch (RuntimeException ex) {
            applier.fail(Status.UNAUTHENTICATED
                .withDescription("unable to obtain access token")
                .withCause(ex));
            return;
        }

        tokenStage.whenCompleteAsync((token, error) -> {
            if (error != null) {
                applier.fail(Status.UNAUTHENTICATED
                    .withDescription("access token request failed")
                    .withCause(error));
                return;
            }
            if (token == null || token.isBlank()) {
                applier.fail(Status.UNAUTHENTICATED
                    .withDescription("access token is empty"));
                return;
            }

            Metadata headers = new Metadata();
            headers.put(AUTHORIZATION, "Bearer " + token);
            applier.apply(headers);
        }, appExecutor);
    }
}
~~~

TokenProvider là interface của ứng dụng, ví dụ:

~~~java
public interface TokenProvider {
    CompletionStage<String> fetchAccessToken();
}
~~~

Implementation không chặn appExecutor để gọi token endpoint. Nếu token được cache, cần quản lý expiry, refresh trước thời điểm hết hạn, đồng bộ khi nhiều RPC cùng yêu cầu refresh và không ghi token vào log. Mỗi call chỉ nên nhận token còn hiệu lực cho đúng audience/scope.

Ví dụ kiểm tra SecurityLevel yêu cầu transport có bảo vệ tính bí mật và toàn vẹn. Vì vậy, bearer token chỉ được gửi qua TLS; không hạ bảo vệ transport để làm test pass. Trong test, dùng TLS test certificate hoặc mock credential/provider phù hợp.

## 6. Kết hợp deadline và credential trên cùng stub

Hai phương thức cấu hình thay đổi các phần khác nhau của CallOptions, nên có thể chain:

~~~java
PaymentResponse response = baseStub
    .withCallCredentials(bearerCredentials)
    .withDeadlineAfter(600, TimeUnit.MILLISECONDS)
    .getPayment(request);
~~~

Hoặc:

~~~java
PaymentResponse response = baseStub
    .withDeadlineAfter(600, TimeUnit.MILLISECONDS)
    .withCallCredentials(bearerCredentials)
    .getPayment(request);
~~~

Trong cả hai cách, RPC được gọi trên stub cuối cùng và có cả deadline lẫn credential. Không bỏ qua stub được trả về ở bất kỳ bước nào.

Lưu ý: CallOptions giữ một CallCredentials. Nếu gọi withCallCredentials lần nữa trên stub đã có credential, cấu hình mới thay thế credential trước đó thay vì tự động cộng dồn hai credential. Nếu cần nhiều nguồn metadata xác thực, hãy hợp nhất chúng trong một implementation CallCredentials có kiểm soát hoặc thiết kế một credential provider tổng hợp.

## 7. Deadline bao gồm cả thời gian lấy credential

Việc lấy token diễn ra trong quá trình chuẩn bị metadata cho RPC và có thể tiêu thụ thời gian của call. Nếu token endpoint chậm, deadline ngắn có thể hết trước khi request nghiệp vụ được gửi tới server.

Do đó:

- Token provider cần timeout riêng và không chờ vô hạn.
- Token nên được cache an toàn theo expiry/scope để tránh gọi auth server cho mọi RPC nếu chính sách cho phép.
- Không đặt deadline nghiệp vụ quá ngắn mà không tính thời gian xác thực.
- Khi deadline hết trong lúc lấy token, không tiếp tục gửi request với credential đã đến muộn.
- Không tạo deadline mới sau khi token được lấy xong; call vẫn phải tuân theo ngân sách ban đầu.

## 8. Phân biệt CallCredentials với interceptor và metadata

| Cơ chế | Dùng cho | Ghi chú |
| --- | --- | --- |
| CallCredentials | Credential xác thực gắn với từng call | Có callback bất đồng bộ, nhận thông tin call và security level |
| ClientInterceptor | Cross-cutting behavior như trace, correlation ID, logging hoặc policy call | Có thể thay đổi CallOptions hoặc bọc ClientCall |
| Metadata thủ công | Header cụ thể cho một call | Dễ lặp code và dễ làm lộ credential nếu quản lý không đúng |

Không đặt bearer token cố định vào interceptor dùng chung nếu token cần refresh hoặc khác nhau theo user/tenant. CallCredentials phù hợp hơn cho thông tin xác thực động. Interceptor có thể bổ sung trace ID, nhưng không nên ghi lại authorization metadata.

## 9. Tích hợp credential trong Spring

Có thể đăng ký TokenProvider và CallCredentials thành bean:

~~~java
@Configuration
public class PaymentCredentialConfiguration {

    @Bean
    CallCredentials paymentCallCredentials(TokenProvider tokenProvider) {
        return new BearerTokenCredentials(tokenProvider);
    }

    @Bean
    PaymentServiceBlockingStub paymentStub(
            ManagedChannel paymentChannel,
            CallCredentials paymentCallCredentials) {
        return PaymentServiceGrpc.newBlockingStub(paymentChannel)
            .withCallCredentials(paymentCallCredentials);
    }
}
~~~

Ví dụ giả định channel đã được cấu hình TLS và do Spring quản lý. Nếu starter cung cấp channel/stub bean riêng, hãy dùng extension point của starter và tránh tạo channel trùng. TokenProvider nên được inject từ cơ chế identity/OAuth của ứng dụng; không hard-code client secret hoặc access token trong source.

Service có thể tạo deadline riêng cho mỗi method:

~~~java
public PaymentResponse getPayment(PaymentRequest request) {
    return paymentStub
        .withDeadlineAfter(500, TimeUnit.MILLISECONDS)
        .getPayment(request);
}
~~~

Credential được kế thừa từ stub nền, còn deadline được tạo mới cho logical RPC.

## 10. Kiểm thử deadline và CallCredentials

Kiểm thử nên bao phủ:

1. Stub dẫn xuất có deadline và credential; server nhận authorization metadata hợp lệ.
2. Stub nền không bị thay đổi sau khi tạo stub dẫn xuất có deadline khác.
3. Call có deadline ngắn kết thúc bằng DEADLINE_EXCEEDED khi server chậm.
4. Token provider trả lỗi hoặc token rỗng; client không gửi RPC thiếu credential và nhận lỗi xác thực phù hợp.
5. Transport không có SecurityLevel bảo mật; credential từ chối gửi bearer token.
6. Token provider chậm; deadline vẫn giới hạn toàn bộ thời gian chuẩn bị và thực hiện call.
7. Hai call đồng thời dùng cùng credential bean nhưng nhận token/context đúng theo chính sách.
8. Gọi withCallCredentials lần thứ hai không vô tình ghi đè credential cần thiết.

Có thể dùng in-process transport để test deadline và logic callback, nhưng test yêu cầu SecurityLevel.PRIVACY_AND_INTEGRITY cần transport TLS thật hoặc test credential tách riêng. Không dùng trust-all trong integration test TLS.

## 11. Lỗi thường gặp và cách xử lý

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Gọi withDeadlineAfter nhưng bỏ qua stub trả về | Deadline không áp dụng cho RPC | Gọi method trên stub dẫn xuất cuối cùng |
| Lưu stub đã có deadline tương đối trong singleton | Các call sau có thể hết hạn ngay | Lưu stub nền, tạo deadline theo từng call |
| Dùng token tĩnh trong stub lâu dài | Token hết hạn nhưng vẫn được gửi | Dùng CallCredentials lấy token còn hiệu lực |
| Lấy token blocking trên callback executor | Làm nghẽn executor cấp metadata | Dùng token provider bất đồng bộ có timeout |
| Gọi withCallCredentials nhiều lần để cộng dồn | Credential trước có thể bị thay thế | Dùng một credential tổng hợp có chủ đích |
| Gửi bearer token qua plaintext | Lộ credential trên mạng | Yêu cầu TLS và kiểm tra security level |
| Tạo deadline mới sau khi lấy token | Tổng thời gian vượt SLA caller | Giữ một deadline cho toàn bộ logical call |

## 12. Ghi nhớ và tự kiểm tra

**withDeadline/withDeadlineAfter giới hạn thời gian; withCallCredentials cung cấp metadata xác thực.** Cả hai trả về stub immutable mới và có thể kết hợp trên cùng một stub dẫn xuất. Dùng stub nền dùng chung, tạo deadline gần thời điểm gọi, truyền deadline cha cho downstream và để CallCredentials lấy token động một cách bất đồng bộ qua TLS.

Tự kiểm tra:

1. Khi nào dùng withDeadline thay vì withDeadlineAfter?
2. Vì sao không lưu stub đã cấu hình withDeadlineAfter trong Spring singleton?
3. CallCredentials khác ClientInterceptor ở mục đích và vòng đời metadata như thế nào?
4. Vì sao token provider cần bất đồng bộ và có timeout riêng?
5. Điều gì xảy ra khi gọi withCallCredentials lần thứ hai trên stub đã có credential?
6. Vì sao deadline phải bao gồm thời gian lấy token?

Kết hợp deadline theo từng RPC với CallCredentials đúng cách giúp client Spring gRPC vừa giới hạn thời gian chờ, vừa gửi credential an toàn và nhất quán mà không làm cấu hình của request này ảnh hưởng request khác.
