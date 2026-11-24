# Kiểm thử thiếu quyền, token hết hạn, throttling và đứt kết nối

> **Chương:** Kiểm thử tích hợp  
> **Module:** SPRING_CLOUD_PROVIDER_INTEGRATION  
> **Mục tiêu:** Thiết kế negative integration test cho lỗi xác thực và phân quyền; mô phỏng token hết hạn, throttling, timeout, connection reset và gián đoạn mạng; xác minh retry, backoff, idempotency và cách ánh xạ lỗi của AWS, Azure và Google Cloud.

## 1. Vì sao phải kiểm thử các tình huống thất bại?

Ứng dụng Spring Boot tích hợp managed cloud service thường chạy tốt trong môi trường developer vì tài khoản local có quyền rộng, token còn hạn và mạng ổn định. Sau khi triển khai, workload identity có thể thiếu một action IAM, role assignment chưa có hiệu lực, access token hết hạn, dịch vụ giới hạn tốc độ hoặc kết nối bị ngắt giữa lúc request đang chạy.

Nếu chỉ kiểm thử happy path, các lỗi này thường xuất hiện muộn trong production. Chúng có thể làm request thất bại, tạo dữ liệu trùng, mất message, retry vô hạn hoặc che giấu một cấu hình quyền sai.

Một negative integration test tốt phải trả lời được bốn câu hỏi:

1. **Lỗi được nhận diện thế nào?** 401, 403, 429, 5xx, timeout hay lỗi transport?
2. **Ứng dụng phản ứng ra sao?** Refresh credential, trả lỗi nghiệp vụ, retry, chờ hay dừng?
3. **Tác động có an toàn không?** Có phát sinh object/message trùng hoặc side effect một phần không?
4. **Có thể quan sát và chẩn đoán không?** Log có request ID, service error code, attempt count và correlation ID không?

Không nên gom mọi lỗi cloud vào một exception chung rồi retry. Thiếu quyền và token hết hạn cần xử lý khác throttling; timeout sau khi gửi request có thể để lại kết quả không xác định.

## 2. Phân loại lỗi theo nguyên nhân

| Nhóm lỗi | Ví dụ | Phản ứng thường phù hợp |
| --- | --- | --- |
| Không xác thực được | Token hết hạn, token sai audience, credential không lấy được | Thử refresh/reauth theo credential provider; nếu không được thì dừng |
| Không đủ quyền | IAM action bị deny, thiếu Azure RBAC, thiếu Google IAM role | Không retry mù quáng; sửa identity hoặc role assignment |
| Throttling/quota | HTTP 429, AWS throttling, Google RESOURCE_EXHAUSTED | Backoff có jitter, tôn trọng Retry-After, giới hạn attempts |
| Lỗi dịch vụ tạm thời | HTTP 500/502/503/504, gRPC UNAVAILABLE | Có thể retry nếu operation an toàn và còn deadline |
| Timeout | Connect timeout, read timeout, gRPC DEADLINE_EXCEEDED | Phân biệt chưa gửi request với kết quả không rõ sau khi gửi |
| Đứt kết nối | Connection reset, socket closed, proxy timeout | Retry có giới hạn nếu operation idempotent |
| Lỗi cấu hình/permanent | Invalid endpoint, TLS hostname mismatch, validation 400 | Fail fast và báo lỗi cấu hình |
| Resource không tồn tại | 404, NOT_FOUND | Không retry trừ khi workflow có eventual consistency được thiết kế rõ |

Một status code không đủ để kết luận nguyên nhân. Ví dụ HTTP 401 có thể là token hết hạn, token sai audience hoặc credential không hợp lệ; HTTP 403 thường biểu thị principal đã được nhận diện nhưng không được phép thực hiện action. Hãy đọc error code và response metadata của provider, không chỉ nhìn status.

## 3. Chọn đúng tầng kiểm thử

Không phải mọi lỗi đều có thể xác minh bằng cùng một test environment.

| Tầng | Cách tạo lỗi | Điều có thể xác minh |
| --- | --- | --- |
| Unit test | Mock port, credential provider hoặc retry collaborator | Exception mapping, quyết định retry, nhánh nghiệp vụ |
| Adapter test | Mock SDK client hoặc HTTP response có cấu trúc provider | Ánh xạ status/error code và request metadata |
| Component test | Fake identity, fake storage/broker hoặc local HTTP stub | Phối hợp nhiều component, refresh flow do ứng dụng quản lý |
| Fault-injection test | Toxiproxy, MockWebServer hoặc WireMock | Latency, connection cut/reset, 429/503, timeout |
| Cloud integration test | Identity test riêng với IAM/RBAC thật | Permission, token audience, workload identity và policy thực |
| Staging/E2E | Cloud resource và network path gần production | Luồng end-to-end, quota, private endpoint và service behavior |

Mock 403 chỉ chứng minh code xử lý exception đúng. Nó không chứng minh policy IAM thực tế đang deny đúng action. Toxiproxy có thể cắt kết nối tới container hoặc service test; nó không chứng minh private endpoint của production hoạt động.

Một chiến lược hợp lý dùng unit test cho nhiều nhánh lỗi, fault injection cho retry/timeout, và một số cloud test nhỏ với identity có quyền tối thiểu.

## 4. Chuẩn hóa lỗi tại adapter boundary

Business service không nên phụ thuộc trực tiếp vào AwsServiceException, RequestFailedException hoặc ApiException. Adapter nên chuyển lỗi SDK thành lỗi ứng dụng ổn định.

Ví dụ contract:

```java
public enum CloudFailureKind {
    AUTHENTICATION_EXPIRED,
    AUTHENTICATION_INVALID,
    ACCESS_DENIED,
    THROTTLED,
    SERVICE_UNAVAILABLE,
    NETWORK_TIMEOUT,
    CONNECTION_LOST,
    RESOURCE_NOT_FOUND,
    INVALID_REQUEST,
    UNKNOWN
}

public record CloudFailure(
        CloudFailureKind kind,
        String provider,
        String service,
        String operation,
        Integer statusCode,
        String providerCode,
        String requestId,
        boolean retryable) {
}

public class CloudOperationException extends RuntimeException {
    private final CloudFailure failure;

    public CloudOperationException(
            CloudFailure failure,
            Throwable cause) {
        super("Cloud operation failed: " + failure.kind(), cause);
        this.failure = failure;
    }

    public CloudFailure failure() {
        return failure;
    }
}
```

Không đưa access token, secret key, connection string hoặc toàn bộ request body vào CloudFailure. Chỉ giữ thông tin cần để phân loại, chẩn đoán và liên kết log.

### 4.1. Quy tắc phân loại tối thiểu

- 401 hoặc UNAUTHENTICATED: kiểm tra credential, expiry, issuer và audience.
- 403 hoặc PERMISSION_DENIED: kiểm tra principal, action, resource scope và policy.
- 429 hoặc RESOURCE_EXHAUSTED: phân loại throttling/quota, đọc retry hint nếu có.
- 500/502/503/504 hoặc UNAVAILABLE: có thể là lỗi tạm thời, cần xét operation và retry budget.
- Timeout/reset: xác định request đã được gửi hay chưa; kết quả ghi có thể không xác định.
- 400/INVALID_ARGUMENT: thường là lỗi request, không retry.
- 404/NOT_FOUND: xử lý theo semantics resource; không biến thành retry vô hạn.

Không chỉ dùng một điều kiện `statusCode >= 500`. Provider có thể trả 500 cho một lỗi không nên retry, hoặc 400 cùng error code thể hiện throttling/transient condition. Hãy ưu tiên error code chính thức và retry policy của SDK.

## 5. Thiếu quyền: kiểm tra deny thực tế

### 5.1. Tạo principal riêng cho negative test

Dùng workload identity hoặc service principal riêng cho integration test. Cấp đúng quyền cần cho happy path, sau đó dùng một principal thứ hai thiếu đúng một action để kiểm tra deny.

Ví dụ với Document Service:

- Identity A có thể ghi object vào bucket/container và phát event.
- Identity B chỉ có quyền đọc object.
- Test upload bằng Identity B phải bị từ chối.
- Test đọc bằng Identity B phải thành công nếu resource tồn tại và policy cho phép.
- Test không được thay bằng admin credential khi chạy assertion.

Tách principal giúp xác minh permission boundary thực tế. Không sửa policy production để tạo lỗi; dùng account, project, subscription hoặc resource test riêng.

### 5.2. AWS IAM

AWS SDK for Java 2.x thường ném AwsServiceException hoặc subclass khi AWS service trả lỗi; AccessDenied thường là lỗi không retry. Đối với S3, error code có thể là `AccessDenied`; với các dịch vụ khác, code và HTTP mapping có thể khác.

Một negative test có thể gọi operation thật bằng role test chỉ có quyền đọc:

```java
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.catchThrowableOfType;

@Test
void readOnlyRoleCannotUploadObject() {
    S3Client s3 = createClientUsingReadOnlyTestRole();

    S3Exception failure = catchThrowableOfType(
            () -> s3.putObject(
                    PutObjectRequest.builder()
                            .bucket(testBucket)
                            .key("negative/doc-1.pdf")
                            .build(),
                    RequestBody.fromBytes(new byte[] {1, 2, 3})
            ),
            S3Exception.class);

    assertThat(failure.statusCode()).isEqualTo(403);
    assertThat(failure.awsErrorDetails().errorCode())
            .isEqualTo("AccessDenied");
}
```

Đây là ví dụ cấu trúc. Helper tạo client phải dùng role test đã được cấp policy chỉ đọc; bucket và key phải là resource thử nghiệm. Không dùng tài khoản có quyền quản trị rồi giả lập AccessDenied bằng mock để tuyên bố IAM đã được kiểm tra.

### 5.3. Azure RBAC

Azure Storage data-plane permission được cấp qua role phù hợp, ví dụ Storage Blob Data Reader hoặc Storage Blob Data Contributor. Role assignment có scope ở subscription, resource group, storage account hoặc container tùy thiết kế. Role assignment có thể cần thời gian để propagation.

Kiểm thử cần xác minh:

- Principal đã đăng nhập đúng tenant và subscription.
- Token có audience dành cho Azure Storage.
- Role được gán ở đúng scope.
- Operation đọc/ghi/xóa có đúng yêu cầu role không.
- Negative test trả 403 hoặc service error tương ứng khi thiếu data action.

Azure SDK for Java có thể ném RequestFailedException với status code và error code; lỗi lấy token có thể xuất hiện dưới dạng ClientAuthenticationException hoặc CredentialUnavailableException. Phân biệt lỗi token acquisition với lỗi service từ chối quyền.

### 5.4. Google Cloud IAM

Google Cloud phân biệt UNAUTHENTICATED và PERMISSION_DENIED. PERMISSION_DENIED thường ánh xạ HTTP 403; UNAUTHENTICATED biểu thị caller không được xác thực. RESOURCE_EXHAUSTED thường ánh xạ HTTP 429 và liên quan quota/resource exhaustion.

Với Cloud Storage, tạo service account test chỉ có role cần thiết, ví dụ object viewer cho đọc hoặc object creator cho tạo object. Test upload bằng principal chỉ có quyền đọc phải thất bại; test đọc object được phép phải thành công.

Không cấp Project Editor hoặc Owner cho integration test. Dùng resource scope hẹp, thu hồi quyền sau test nếu test tự tạo role binding, và tránh chạy role mutation song song với suite khác.

### 5.5. Kiểm tra permission denial có ý nghĩa

Một test thiếu quyền phải kiểm tra cả ba điều:

1. SDK nhận đúng principal dự kiến.
2. Provider từ chối đúng operation/resource.
3. Ứng dụng ánh xạ lỗi thành AccessDenied/PermissionDenied và không retry.

Nếu test chỉ assert một exception bất kỳ, nó có thể pass do sai endpoint, token hỏng hoặc network timeout. Kiểm tra status, provider error code và request ID để chắc chắn đang thử đúng tình huống.

## 6. Token hết hạn và lỗi xác thực

### 6.1. Phân biệt token hết hạn với thiếu quyền

| Tình huống | Dấu hiệu thường gặp | Hành động |
| --- | --- | --- |
| Token hết hạn | 401, UNAUTHENTICATED, ExpiredToken hoặc invalid token response | Refresh hoặc lấy credential mới nếu credential source hỗ trợ |
| Token sai audience/issuer | 401 hoặc invalid token | Sửa cấu hình identity; không retry liên tục |
| Credential source không khả dụng | Không lấy được token trước khi gửi request | Kiểm tra metadata endpoint, workload identity, CLI/SSO session |
| Principal không có quyền | 403, PERMISSION_DENIED, AccessDenied | Sửa IAM/RBAC; không refresh token để giải quyết |
| Principal đã bị thu hồi | Token còn hạn nhưng policy deny | Cấp lại role đúng nếu cần; refresh không tự cấp quyền |

Token hết hạn và permission denied là hai lỗi khác nhau. Refresh token không thể cấp thêm quyền cho một principal vốn không có role phù hợp.

### 6.2. AWS: temporary credentials và IAM Identity Center

AWS SDK for Java 2.x dùng credentials provider để lấy và ký request. Temporary credentials thường gồm access key, secret key và session token; chúng có thời hạn. Provider có khả năng refresh có thể lấy credential mới trước khi session hết hạn.

Với IAM Identity Center (SSO), SDK có thể refresh access token bằng refresh token nếu phiên access portal còn hiệu lực. Nếu phiên portal đã hết hạn, cần đăng nhập lại; SDK không thể tự khôi phục một phiên đã hết hạn hoàn toàn.

Các tình huống nên kiểm tra:

- Credentials provider refresh thành công trước khi credential hết hạn.
- Refresh token hoặc SSO session hết hạn, request mới thất bại rõ ràng.
- Static credentials chứa session token cũ không được dùng lâu dài.
- Khi provider không thể lấy credential mới, ứng dụng báo authentication failure và không retry service operation vô hạn.
- Client và provider không bị đóng sớm trong khi ứng dụng còn sử dụng.

Không dùng StaticCredentialsProvider để đại diện cho workload identity production nếu ứng dụng thực tế dùng AssumeRole, Web Identity hoặc IAM Identity Center.

### 6.3. Azure: TokenCredential và Azure Identity

Azure SDK for Java nhận token thông qua TokenCredential. Các credential như DefaultAzureCredential, ManagedIdentityCredential hoặc ClientSecretCredential quản lý việc lấy token theo môi trường.

Azure Identity có các exception cần phân biệt:

- ClientAuthenticationException: quá trình xác thực thất bại.
- CredentialUnavailableException: credential hiện tại không thể sử dụng trong môi trường này; credential chain có thể thử provider tiếp theo.
- RequestFailedException 401/403: service trả lời nhưng từ chối request; cần kiểm tra token hoặc quyền theo status/error code.

Test credential chain nên xác minh credential được chọn đúng trong CI. Ví dụ, một runner có Azure CLI login của developer hoặc service account khác có thể khiến DefaultAzureCredential lấy nhầm identity. Hãy log loại credential được chọn ở mức an toàn và xác minh principal trong cloud test.

### 6.4. Google Cloud: ADC và refresh token

Google Cloud Client Libraries for Java thường dùng Application Default Credentials (ADC). ADC hỗ trợ nhiều nguồn credential và có thể quản lý việc refresh token tùy loại credential.

Nếu tự tạo credentials từ một access token cố định, token đó không tự động được refresh. Đây là điểm dễ gây lỗi khi code cache token thủ công hoặc truyền token từ một service khác.

Ưu tiên ADC, service account impersonation hoặc Workload Identity Federation cho môi trường phù hợp. Tránh tải và lưu service account key lâu dài nếu có thể dùng identity federation.

### 6.5. Kiểm thử token hết hạn có kiểm soát

Không nên đợi một token thật hết hạn theo thời gian trong test tự động. Cách đó làm suite chậm và không ổn định. Dùng một trong các cách sau:

- Unit test credential wrapper với clock có thể điều khiển.
- Fake TokenCredential hoặc token source trả token có expiry xác định.
- Stub token endpoint để kiểm tra refresh thành công và refresh thất bại.
- Mock service trả 401/UNAUTHENTICATED để xác minh adapter phân loại lỗi.
- Cloud integration test riêng với workload identity/session ngắn hạn nếu cần xác minh credential chain thật.

Một test nên bao gồm cả refresh thành công và refresh thất bại. Khi refresh thất bại, ứng dụng phải dừng request và phát ra lỗi authentication có thể chẩn đoán, không quay vòng retry service call.

### 6.6. Không log token

Không ghi access token, refresh token, client secret, private key, AWS session token hoặc connection string vào log/test report. Khi cần kiểm tra token refresh, chỉ ghi loại credential, thời điểm expiry, số lần refresh và correlation ID. Che token trong debug output.

## 7. Throttling và quota

### 7.1. Nhận diện throttling

Throttling xảy ra khi request rate, concurrency hoặc mức sử dụng quota vượt giới hạn. Provider có thể trả 429, 503 hoặc error code riêng.

| Provider | Dấu hiệu thường gặp | Ghi chú |
| --- | --- | --- |
| AWS | ThrottlingException, TooManyRequestsException, ProvisionedThroughputExceededException, SlowDown hoặc status 429/5xx | SDK phân loại lỗi theo error code và status |
| Azure Storage | 503 Server Busy, 500 Operation Timeout; một số Azure service trả 429 | Azure Storage thường khuyến nghị exponential backoff |
| Azure Resource Manager | 429 Too Many Requests cùng Retry-After | Phải chờ thời gian server chỉ định |
| Google Cloud | RESOURCE_EXHAUSTED, thường ánh xạ 429 | Retryable code phụ thuộc từng RPC/service |

Không coi mọi 429 là cùng một loại quota. Có thể là quota theo project, per-user, resource, partition hoặc giới hạn tạm thời của service. Error details và metric provider giúp xác định phạm vi.

### 7.2. Retry policy an toàn

Một retry policy thường có:

- Exponential backoff: khoảng chờ tăng theo số lần thử.
- Jitter: thêm ngẫu nhiên để nhiều client không retry cùng lúc.
- Maximum attempts: giới hạn số lần gọi.
- Total deadline/timeout: giới hạn thời gian của cả operation.
- Retryable error classification: chỉ retry lỗi đã được xác định là transient.
- Retry-After: tôn trọng thời gian server yêu cầu khi SDK/service cung cấp.
- Idempotency: bảo đảm retry không tạo side effect trùng.

Ví dụ thời gian chờ minh họa:

| Lần retry | Backoff cơ sở | Khoảng chờ sau jitter (ví dụ) |
| ---: | ---: | ---: |
| 1 | 200 ms | 100–300 ms |
| 2 | 400 ms | 200–600 ms |
| 3 | 800 ms | 400–1.200 ms |
| 4 | 1.600 ms | 800–2.400 ms |

Đây chỉ là minh họa. Giá trị production phải theo SDK/provider, latency budget và quota của service. Không hard-code bảng này làm default chung cho AWS, Azure và Google Cloud.

### 7.3. AWS SDK for Java 2.x

AWS SDK for Java 2.x có ba retry strategy: standard, legacy và adaptive. Standard được AWS khuyến nghị cho use case thông thường; mode mặc định và số attempts có thể phụ thuộc phiên bản SDK, service client hoặc cấu hình bên ngoài. Khi cần test ổn định, hãy chọn mode rõ ràng và đo số request thực tế.

Ví dụ cấu hình rõ số lần thử:

```java
import software.amazon.awssdk.core.retry.RetryMode;

S3Client s3 = S3Client.builder()
        .overrideConfiguration(configuration ->
                configuration.retryStrategy(RetryMode.STANDARD))
        .build();
```

Nếu cần thay đổi số attempts, dùng retry strategy builder tương ứng với version SDK, ví dụ `retryStrategy(builder -> builder.maxAttempts(3))`. Kiểm tra import và API đúng với phiên bản AWS SDK đang dùng. Không vừa tăng retries trong SDK vừa bọc cùng operation bằng application retry mà không tính tổng số attempts; hai lớp retry có thể nhân số request lên nhiều lần.

### 7.4. Azure SDK for Java

Azure SDK có retry policy ở Azure Core và cấu hình riêng ở một số service client như Azure Storage. Azure Core RetryOptions mặc định retry một số response 408, 429 và 5xx, ngoại trừ 501/505, cùng các exception theo policy. Azure Storage có RequestRetryOptions với retry type, max tries, try timeout, retry delay và max retry delay.

Không giả định một giá trị default áp dụng cho tất cả Azure service. Đọc tài liệu của client cụ thể và xác minh SDK có tôn trọng Retry-After hay không.

Với Azure Storage, 503 Server Busy và 500 Operation Timeout có thể liên quan throttling/hot partition. Exponential backoff giúp giảm áp lực; naming/partitioning hợp lý cũng quan trọng. Retry không thể chữa một workload liên tục dồn traffic vào cùng partition.

### 7.5. Google Cloud Java client libraries

Google Cloud Java client libraries cấu hình retry theo từng RPC. Mỗi RPC có thể có tập retryable status code và RetrySettings riêng. Không được giả định mọi API đều retry RESOURCE_EXHAUSTED hoặc UNAVAILABLE giống nhau.

Các tham số quan trọng gồm initial retry delay, retry delay multiplier, max retry delay, RPC timeout, total timeout và max attempts. Google Cloud libraries dùng jitter trong retry. Hãy xem generated StubSettings của đúng client để biết RPC nào retry và status nào được cấu hình.

### 7.6. Không retry lỗi permission

403/AccessDenied/PERMISSION_DENIED thường không phải transient. Retry nhiều lần chỉ tạo thêm request và che lỗi policy. Một ngoại lệ có thể là role assignment vừa thay đổi và propagation chưa hoàn tất; nếu cần test tình huống đó, dùng một poll có deadline rõ ràng để chờ permission có hiệu lực, không dùng retry vô hạn cho mọi 403.

## 8. Kiểm thử retry và throttling một cách xác định

### 8.1. Test error classifier riêng

Có thể viết unit test cho classifier trước khi kiểm tra SDK:

```java
class CloudFailureClassifierTest {

    @Test
    void permissionDeniedIsNotRetryable() {
        CloudFailure failure = new CloudFailure(
                CloudFailureKind.ACCESS_DENIED,
                "azure",
                "blob",
                "upload",
                403,
                "AuthorizationPermissionMismatch",
                "request-123",
                false);

        assertThat(failure.retryable()).isFalse();
    }

    @Test
    void throttlingIsRetryableWithinBudget() {
        CloudFailure failure = new CloudFailure(
                CloudFailureKind.THROTTLED,
                "gcp",
                "storage",
                "write",
                429,
                "RESOURCE_EXHAUSTED",
                "request-456",
                true);

        assertThat(failure.retryable()).isTrue();
    }
}
```

Classifier cần kiểm tra cả provider error code và status. Không chỉ kiểm tra status 500–599 rồi đánh dấu tất cả là retryable.

### 8.2. Test chuỗi 429 rồi thành công

Dùng MockWebServer hoặc WireMock để tạo response có thể kiểm soát. Ví dụ test một lớp retry do ứng dụng sở hữu:

```java
@Test
void retriesThrottledOperationAndStopsAfterSuccess() {
    AtomicInteger calls = new AtomicInteger();

    String result = retryingExecutor.execute(() -> {
        int attempt = calls.incrementAndGet();

        if (attempt == 1) {
            throw new CloudOperationException(
                    throttledFailure(),
                    null);
        }

        return "stored";
    });

    assertThat(result).isEqualTo("stored");
    assertThat(calls).hasValue(2);
}
```

`retryingExecutor` trong ví dụ là component của ứng dụng, nhận clock/sleeper/retry policy qua constructor để test không phải chờ thật. Nếu retry nằm hoàn toàn trong SDK, hãy kiểm tra request count ở HTTP stub hoặc proxy và cấu hình SDK thật thay vì test wrapper không được sử dụng.

### 8.3. Test không retry khi bị từ chối

```java
@Test
void doesNotRetryAccessDenied() {
    AtomicInteger calls = new AtomicInteger();

    assertThatThrownBy(() ->
            retryingExecutor.execute(() -> {
                calls.incrementAndGet();
                throw new CloudOperationException(
                        accessDeniedFailure(),
                        null);
            }))
            .isInstanceOf(CloudOperationException.class);

    assertThat(calls).hasValue(1);
}
```

Test này bảo vệ hệ thống khỏi retry storm khi policy sai. Đồng thời kiểm tra log/metric không gắn lỗi AccessDenied vào nhóm transient.

### 8.4. Test Retry-After và deadline

Với response có Retry-After:

- Kiểm tra SDK/policy chọn thời gian chờ không sớm hơn retry hint mà service yêu cầu.
- Kiểm tra total deadline vẫn giới hạn operation.
- Kiểm tra nếu Retry-After vượt thời gian còn lại, operation dừng thay vì kéo dài request vô hạn.
- Dùng fake clock/sleeper để kiểm tra thời gian mà không làm test suite chậm.

Không assert một thời gian jitter chính xác theo millisecond; jitter có yếu tố ngẫu nhiên. Assert khoảng hợp lệ, số attempts và total deadline.

## 9. Kiểm thử timeout và đứt kết nối

### 9.1. Phân biệt connect timeout và read timeout

- **Connect timeout:** client không thiết lập được TCP connection trong thời gian cho phép.
- **Read/response timeout:** connection đã được thiết lập nhưng response không đến đúng hạn.
- **Connection reset:** socket bị đóng bất ngờ trong lúc trao đổi dữ liệu.
- **DNS failure:** hostname không phân giải được.
- **TLS handshake/certificate failure:** handshake thất bại hoặc certificate/hostname không hợp lệ.

Connect timeout thường cho biết request chưa đến service. Read timeout sau khi gửi request có thể không rõ service đã thực hiện operation hay chưa. Không retry một write không idempotent chỉ vì client không nhận được response.

### 9.2. Dùng Testcontainers Toxiproxy

Toxiproxy cho phép chèn latency, jitter, bandwidth limit, timeout và cắt kết nối giữa test JVM với một container hoặc giữa hai container. Đây là cách xác định để kiểm tra resilience trong local/CI.

Dependency Maven với Testcontainers 2.x:

```xml
<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>testcontainers-toxiproxy</artifactId>
    <version>2.0.5</version>
    <scope>test</scope>
</dependency>
```

Ví dụ tạo network, service container và Toxiproxy:

```java
import eu.rekawek.toxiproxy.ToxiproxyClient;
import eu.rekawek.toxiproxy.model.Proxy;
import eu.rekawek.toxiproxy.model.ToxicDirection;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.containers.Network;
import org.testcontainers.containers.ToxiproxyContainer;

Network network = Network.newNetwork();

GenericContainer<?> target = new GenericContainer<>("redis:7.4-alpine")
        .withExposedPorts(6379)
        .withNetwork(network)
        .withNetworkAliases("redis");

ToxiproxyContainer toxiproxy =
        new ToxiproxyContainer("ghcr.io/shopify/toxiproxy:2.5.0")
                .withNetwork(network);

target.start();
toxiproxy.start();

ToxiproxyClient client = new ToxiproxyClient(
        toxiproxy.getHost(),
        toxiproxy.getControlPort());

Proxy proxy = client.createProxy(
        "redis",
        "0.0.0.0:8666",
        "redis:6379");

String proxyHost = toxiproxy.getHost();
int proxyPort = toxiproxy.getMappedPort(8666);
```

Code under test phải kết nối qua proxyHost và proxyPort, không gọi trực tiếp target. Test cần đóng target, toxiproxy và network trong teardown; có thể dùng JUnit lifecycle hoặc Testcontainers extension để quản lý tài nguyên. Với SDK cloud, có thể áp dụng pattern này cho local emulator hoặc service test có endpoint override. Khi proxy một endpoint HTTPS bên ngoài, phải giữ đúng hostname/SNI và certificate validation; không tắt TLS verification để làm test chạy được.

### 9.3. Tạo latency và cắt kết nối

```java
proxy.toxics()
        .latency("slow-downstream", ToxicDirection.DOWNSTREAM, 1_100)
        .setJitter(100);

// Sau khi xác minh behavior timeout, cắt cả hai chiều.
proxy.toxics().bandwidth(
        "cut-downstream",
        ToxicDirection.DOWNSTREAM,
        0);

proxy.toxics().bandwidth(
        "cut-upstream",
        ToxicDirection.UPSTREAM,
        0);

// Xác minh request thất bại trong deadline dự kiến.

// Khôi phục proxy sau assertion.
proxy.toxics().get("cut-downstream").remove();
proxy.toxics().get("cut-upstream").remove();
```

Sau khi khôi phục proxy, kiểm tra client có thể tạo connection mới và operation tiếp theo thành công. Connection pool có thể giữ socket đã hỏng; tùy HTTP client, cần đóng/recreate client hoặc chờ pool loại connection lỗi.

Toxiproxy test nên có cleanup trong finally hoặc lifecycle helper để không để toxic ảnh hưởng test khác.

### 9.4. DNS và TLS cần test riêng

Toxiproxy chủ yếu tác động TCP stream. DNS failure và certificate validation là những failure mode khác. Có thể dùng test DNS resolver/host mapping riêng hoặc HTTPS test server với certificate test để kiểm tra chúng.

Không dùng certificate tự ký rồi tắt hostname verification trong code production chỉ để làm integration test pass. Test TLS phải xác minh cả trust chain lẫn hostname.

## 10. Timeout có thể tạo kết quả không xác định

Một write request có thể đã được service commit trước khi response bị mất. Client thấy timeout nhưng object/message có thể đã tồn tại.

Ví dụ:

1. Service nhận request upload.
2. Service lưu object thành công.
3. Response bị cắt trước khi client nhận.
4. Client retry.
5. Ứng dụng có thể ghi đè, tạo bản thứ hai hoặc phát event trùng.

Vì vậy, retry an toàn cần một trong các cơ chế:

- Idempotency key ổn định cho một business operation.
- Object key xác định và điều kiện write phù hợp.
- Conditional request bằng ETag/generation/version.
- Message deduplication key hoặc consumer inbox.
- Transactional outbox để không phát event trùng do retry business transaction.
- Read-after-timeout/reconciliation trước khi quyết định ghi lại.

Không tự tạo UUID mới cho mỗi retry nếu UUID đó là idempotency key. Một operation cần giữ cùng key qua mọi attempt.

## 11. Kiểm thử idempotency và retry side effects

### 11.1. Object storage

Với S3/Azure Blob/GCS, test cần xác định retry upload dùng cùng object key hay tạo object mới. Kiểm tra metadata, content checksum, ETag/generation và versioning theo contract.

Một test fault injection nên mô phỏng response bị mất sau khi write đã thành công, sau đó retry cùng operation ID và xác minh chỉ có một logical document.

### 11.2. Message publishing

Publish timeout có thể để lại message trong broker dù producer chưa nhận được acknowledgement. Test cần xác minh:

- Message có event ID ổn định.
- Consumer có deduplicate theo event ID nếu business flow yêu cầu exactly-once effect.
- Retry producer không làm side effect downstream lặp.
- Outbox record được đánh dấu publish theo quy tắc nhất quán.
- Duplicate delivery được xử lý idempotent.

Không nhầm broker-level delivery guarantee với exactly-once business processing.

### 11.3. Database và outbox

Nếu ghi database và phát cloud event, test failure giữa hai bước. Kiểm tra outbox record cùng transaction với business state, sau đó publisher retry đến khi broker nhận. Một fake publisher chỉ kiểm tra logic; integration test database cần xác minh transaction và unique constraint thật.

## 12. Ma trận lỗi theo provider

| Tình huống | AWS | Azure | Google Cloud | Retry mặc định nên cân nhắc |
| --- | --- | --- | --- | --- |
| Thiếu quyền | AccessDenied / AccessDeniedException | 403, AuthorizationPermissionMismatch hoặc RBAC deny | PERMISSION_DENIED | Không |
| Token/session hết hạn | ExpiredToken, SSO session expired | 401 hoặc ClientAuthenticationException | UNAUTHENTICATED / expired access token | Refresh credential nếu provider hỗ trợ; không retry service vô hạn |
| Throttling | ThrottlingException, SlowDown, TooManyRequests | 429; Storage có thể 503/500 | RESOURCE_EXHAUSTED | Có, theo policy và quota |
| Service unavailable | 5xx, ServiceUnavailable | 503 | UNAVAILABLE | Có giới hạn |
| Deadline/timeout | socket timeout, request timeout | timeout/408/500 Operation Timeout | DEADLINE_EXCEEDED | Có điều kiện |
| Network reset | SdkClientException với I/O cause | transport exception | IOException/transport error | Có điều kiện, xét idempotency |
| Request sai | ValidationException, InvalidRequest | 400, InvalidArgument | INVALID_ARGUMENT | Không |

Bảng này mô tả nhóm lỗi phổ biến, không phải mapping tuyệt đối cho mọi dịch vụ. Cùng một provider có thể dùng exception và error code khác nhau giữa S3, SQS, Blob Storage, Service Bus, Pub/Sub hoặc Cloud Storage.

## 13. Observability khi test failure

Negative test nên xác minh cả telemetry mà ứng dụng phát ra. Các trường hữu ích:

- Provider và service name.
- Operation name.
- Failure kind đã chuẩn hóa.
- HTTP/gRPC status và provider error code.
- Provider request ID/correlation ID.
- Attempt number và total attempts.
- Retry delay hoặc Retry-After nếu có.
- Elapsed time và deadline còn lại.
- Resource identifier đã được làm sạch hoặc rút gọn.

Không log access token, refresh token, secret key, SAS token, private key, connection string hoặc payload chứa dữ liệu nhạy cảm.

Với permission failure, log nên giúp xác định principal và action cần quyền, nhưng không chứa credential. Với network failure, log nên phân biệt DNS, connect timeout, read timeout, TLS và connection reset. Với throttling, ghi attempt count và thời gian chờ để phát hiện retry storm.

## 14. Những anti-pattern thường gặp

| Anti-pattern | Rủi ro | Cách sửa |
| --- | --- | --- |
| Retry mọi exception | Retry 403, validation và lỗi cấu hình | Phân loại theo provider error code và operation |
| Retry vô hạn | Request treo, tăng tải và chi phí | Max attempts + total deadline |
| SDK retry và application retry cùng không giới hạn | Số request nhân lên theo từng tầng | Tính tổng retry budget, chỉ một tầng sở hữu policy chính |
| Refresh token khi thiếu IAM permission | Không giải quyết được 403 | Kiểm tra principal, action và resource scope |
| Dùng admin identity trong test | Không phát hiện thiếu quyền runtime | Principal test quyền tối thiểu |
| Chỉ mock 429 rồi kết luận SDK retry đúng | Không xác minh SDK policy thực tế | Test HTTP attempt count với client thật và response đúng format |
| Dùng sleep cố định để đợi token hết hạn | Test chậm và flaky | Fake clock/token source hoặc stub auth endpoint |
| Retry write với idempotency key mới | Tạo duplicate resource/message | Giữ key ổn định qua mọi attempt |
| Tắt TLS verification khi dùng proxy | Che lỗi certificate và mở lỗ hổng bảo mật | Dùng certificate test có hostname hợp lệ |
| Log toàn bộ exception/request | Có thể lộ token hoặc payload | Redact và log metadata an toàn |

## 15. Bài thực hành: kiểm thử Document Service khi cloud gặp lỗi

**Bối cảnh:** Document Service lưu file PDF vào object storage và phát DocumentUploaded lên message broker. Ứng dụng chạy với workload identity và SDK retry mặc định.

### Phần A — Thiếu quyền

- Tạo test principal chỉ có quyền đọc object.
- Thực hiện upload và xác minh provider trả AccessDenied/403/PERMISSION_DENIED.
- Xác minh adapter ánh xạ thành ACCESS_DENIED.
- Xác minh operation không retry.
- Dùng principal có quyền ghi để xác minh happy path vẫn hoạt động.

### Phần B — Token hết hạn

- Tạo fake credential/token source với expiry có thể điều khiển.
- Kiểm tra token được refresh trước khi hết hạn nếu provider hỗ trợ.
- Mô phỏng refresh thất bại và xác minh operation dừng với authentication error.
- Mô phỏng service trả 401 do token bị từ chối.
- Phân biệt 401 với 403 và không retry vô hạn.

### Phần C — Throttling

- Dùng HTTP stub trả 429/503 rồi trả success.
- Xác minh số attempts và total deadline.
- Kiểm tra Retry-After hoặc retry settings theo SDK.
- Trả 403 và xác minh không retry.
- Dùng fake clock để kiểm tra backoff/jitter trong application retry wrapper.

### Phần D — Đứt kết nối

- Khởi chạy một service test trong container.
- Đặt Toxiproxy giữa test JVM và service.
- Thêm latency vượt request timeout.
- Cắt kết nối sau khi operation bắt đầu.
- Khôi phục proxy và kiểm tra client có thể kết nối lại.
- Kiểm tra kết quả write không tạo duplicate object/event.

### Phần E — Cloud identity test

- Chạy test riêng trong AWS account, Azure subscription hoặc Google Cloud project thử nghiệm.
- Dùng IAM role, Managed Identity/workload identity hoặc service account với quyền tối thiểu.
- Kiểm tra một action được phép và một action bị từ chối.
- Thu thập provider request ID và xác minh principal thực tế.
- Cleanup resource và role binding do test tạo.

**Tiêu chí hoàn thành:** người học phân biệt authentication, authorization, throttling và transport failure; viết được negative test cho permission; kiểm tra token refresh/failure; xác minh retry có giới hạn; mô phỏng network fault bằng Toxiproxy; và bảo vệ side effect bằng idempotency.

---

## 16. Checklist trước khi merge/release

| Nhóm | Câu hỏi |
| --- | --- |
| Identity | Test có dùng principal riêng, đúng môi trường và quyền tối thiểu không? |
| Permission | Có positive test và negative test cho từng action quan trọng không? |
| Authentication | Có phân biệt token expired, invalid audience và credential unavailable không? |
| Error mapping | Adapter có giữ status, provider code và request ID không? |
| Retry | Retry chỉ áp dụng lỗi transient/throttling được xác định không? |
| Backoff | Có exponential backoff, jitter, max attempts và total deadline không? |
| Retry-After | Có tôn trọng retry hint của service khi có không? |
| Idempotency | Retry write có giữ operation ID/idempotency key ổn định không? |
| Network | Có test connect timeout, read timeout, reset và recovery không? |
| TLS/DNS | Có test riêng cho certificate/hostname và DNS khi hệ thống phụ thuộc không? |
| Observability | Có attempt count, failure kind, elapsed time và request ID không? |
| Secrets | Log/test report đã loại token, key và connection string chưa? |
| CI | Cloud test có resource riêng và cleanup khi failure không? |
| SDK version | Retry behavior đã được đối chiếu với version SDK thực tế chưa? |

## Ghi nhớ

- 401/UNAUTHENTICATED thường liên quan xác thực; 403/PERMISSION_DENIED thường liên quan quyền. Refresh token không sửa được thiếu IAM/RBAC.
- AWS, Azure và Google Cloud có exception, error code và retry defaults khác nhau; kiểm tra đúng service client và version SDK.
- Throttling cần backoff có jitter, giới hạn attempts, total deadline và tôn trọng Retry-After khi có.
- Không retry validation hoặc permission failure một cách mù quáng.
- Timeout sau khi gửi request có thể để lại side effect; retry write cần idempotency key hoặc cơ chế reconciliation.
- Dùng Toxiproxy để mô phỏng latency, timeout, bandwidth limit và connection cut trong test có kiểm soát.
- Test IAM/RBAC, workload identity và Managed Identity cần cloud test principal riêng với quyền tối thiểu.
- Log request ID, error code và attempt count; không log token hoặc secret.

Kiểm thử lỗi cloud không chỉ xác nhận ứng dụng ném exception. Nó phải chứng minh ứng dụng nhận diện đúng nguyên nhân, dừng khi không có quyền, làm mới credential khi có thể, retry có giới hạn khi lỗi tạm thời và giữ an toàn cho side effect khi kết quả request không rõ. Kết hợp fault injection ở local/CI với một số cloud identity test nhỏ giúp kiểm tra những failure mode quan trọng mà vẫn giữ integration suite ổn định.

### Tài liệu chính thức

- [AWS SDK for Java 2.x — Configure retry behavior](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/retry-strategy.html)
- [AWS SDK for Java 2.x — Handling exceptions](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/handling-exceptions.html)
- [AWS SDKs and Tools — Retry behavior](https://docs.aws.amazon.com/sdkref/latest/guide/feature-retry-behavior.html)
- [AWS SDKs and Tools — IAM Identity Center session expiration and refresh](https://docs.aws.amazon.com/sdkref/latest/guide/understanding-sso.html)
- [AWS SDK for Java 2.x — Credentials providers](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/credentials.html)
- [Azure SDK for Java — Troubleshoot authentication](https://learn.microsoft.com/en-us/azure/developer/java/sdk/troubleshooting-authentication-overview)
- [Azure SDK for Java — RetryOptions](https://learn.microsoft.com/en-us/java/api/com.azure.core.http.policy.retryoptions?view=azure-java-stable)
- [Azure Storage — Retry policy for Java](https://learn.microsoft.com/en-us/azure/storage/blobs/storage-retry-policy-java)
- [Azure Storage — Mitigate hot partitions](https://learn.microsoft.com/en-us/azure/storage/blobs/storage-performance-mitigate-hot-partitions)
- [Google Cloud Java — Configure client-side retries](https://docs.cloud.google.com/java/docs/client-retries)
- [Google Cloud Java — Authenticate requests](https://docs.cloud.google.com/java/docs/authentication)
- [Google Cloud Java — Status code definitions](https://docs.cloud.google.com/java/docs/reference/proto-google-common-protos/latest/com.google.rpc.Code)
- [Testcontainers for Java — Toxiproxy module](https://java.testcontainers.org/modules/toxiproxy/)

Retry defaults, status mappings và exception types có thể thay đổi theo service client và phiên bản SDK. Trước khi thay đổi policy, hãy kiểm tra tài liệu của đúng client, đặt deadline theo SLA nghiệp vụ và đo số request thực tế trong test.
