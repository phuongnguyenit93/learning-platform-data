# Truyền lỗi Reactor và chuyển thành phản hồi OSB

Trong Spring Cloud service broker, các handler thường trả về Reactor Mono để biểu diễn kết quả xử lý theo kiểu reactive. Khi một thao tác provision, update, bind hoặc deprovision thất bại, lỗi có thể xuất hiện từ validation, trạng thái instance, database broker, provider API hoặc chính pipeline Reactor. Broker cần truyền lỗi qua các lớp mà vẫn giữ được nguyên nhân nghiệp vụ, sau đó chuyển nó thành phản hồi HTTP đúng hợp đồng Open Service Broker API (OSB API).

Có hai việc cần phân biệt. Reactor biểu diễn lỗi bằng tín hiệu onError trong publisher. OSB API biểu diễn lỗi ở cấp giao thức bằng HTTP status và error response có cấu trúc. Việc một Mono phát tín hiệu lỗi không tự quyết định platform sẽ nhận HTTP 400, 404, 409, 422 hay 5xx. Ứng dụng cần có quy tắc phân loại và ánh xạ lỗi rõ ràng; Spring Cloud Open Service Broker có thể cung cấp cơ chế xử lý lỗi theo phiên bản thư viện, nhưng broker vẫn phải ném đúng loại exception và giữ thông tin nghiệp vụ cần thiết.

Bài học trình bày cách Reactor truyền lỗi, cách sử dụng các operator xử lý lỗi, cách phân loại lỗi nghiệp vụ và lỗi provider, cách ánh xạ sang phản hồi OSB, cùng những khác biệt quan trọng giữa lỗi đồng bộ và lỗi của asynchronous operation.

## 1. Hai lớp lỗi trong service broker

Một yêu cầu OSB đi qua nhiều lớp. Ví dụ platform yêu cầu provision một PostgreSQL instance:

1. HTTP request đi vào OSB endpoint.
2. Framework giải mã request thành request model.
3. Handler hoặc application service kiểm tra service ID, plan ID, tenant và parameters.
4. Broker lưu trạng thái instance và operation.
5. Provider adapter gọi API nhà cung cấp.
6. Broker tạo response hoặc chấp nhận thao tác bất đồng bộ.

Lỗi có thể xảy ra ở bất kỳ bước nào. Reactor chịu trách nhiệm truyền tín hiệu lỗi bên trong pipeline; lớp giao thức chuyển lỗi đó thành HTTP response mà platform hiểu.

~~~mermaid
flowchart TD
    A[OSB HTTP request] --> B[Framework và handler]
    B --> C[Application service]
    C --> D[Repository / quota / state]
    C --> E[Provider adapter]
    D --> F{Có lỗi?}
    E --> F
    F -->|Không| G[Response thành công]
    F -->|Có| H[Reactor onError]
    H --> I[Phân loại lỗi nghiệp vụ]
    I --> J[OSB error mapping]
    J --> K[HTTP status và error response]
~~~

Hai lớp có mục tiêu khác nhau:

- Reactor cần giữ lỗi trong chuỗi xử lý để subscriber hoặc framework nhận được.
- OSB cần mã lỗi và HTTP status phù hợp để platform quyết định có thể sửa request, retry hay dừng thao tác.

Không nên trả HTTP 200 với một object mô tả lỗi chỉ vì pipeline Reactor đã hoàn tất bằng một giá trị. Điều đó khiến platform hiểu request đã thành công.

## 2. Reactor biểu diễn lỗi bằng tín hiệu onError

Một Mono có thể phát ra tối đa một giá trị rồi hoàn tất, hoàn tất mà không có giá trị, hoặc phát ra lỗi. Lỗi được truyền dưới dạng tín hiệu onError.

Ví dụ:

~~~java
Mono<String> success =
        Mono.just("ready");

Mono<String> empty =
        Mono.empty();

Mono<String> failure =
        Mono.error(new IllegalStateException("provider unavailable"));
~~~

Ba trường hợp có ý nghĩa khác nhau:

| Publisher | Tín hiệu | Ý nghĩa |
|---|---|---|
| Mono.just(value) | onNext rồi onComplete | Có kết quả |
| Mono.empty() | onComplete | Không có kết quả |
| Mono.error(error) | onError | Xử lý thất bại |

Mono.empty không tự động có nghĩa là lỗi. Nếu repository trả Mono.empty khi không tìm thấy service instance, broker cần chuyển tình huống đó thành lỗi nghiệp vụ phù hợp, thay vì để endpoint hoàn tất mà không có response.

Ví dụ:

~~~java
return instanceRepository.findById(instanceId)
        .switchIfEmpty(Mono.error(
                new InstanceNotFoundException(instanceId)));
~~~

switchIfEmpty thay publisher rỗng bằng một publisher lỗi. Khi đó lỗi được truyền tiếp trong cùng reactive pipeline.

## 3. Lỗi phát sinh trong pipeline và lỗi khi dựng pipeline

Lỗi có thể phát sinh khi pipeline đang chạy, ví dụ trong map, flatMap hoặc lời gọi provider. Reactor chuyển exception phát sinh bên trong các operator thành onError.

~~~java
return repository.findById(instanceId)
        .map(instance -> {
            if (!instance.isActive()) {
                throw new InstanceStateException(
                        "Instance is not active");
            }
            return instance;
        });
~~~

Nếu instance không ở trạng thái ACTIVE, exception được phát thành onError và đi tới subscriber hoặc error handler.

Tuy nhiên, một method có thể ném exception đồng bộ trước khi trả về Mono:

~~~java
public Mono<Result> execute(Command command) {
    validateCommandSynchronously(command);
    return providerClient.execute(command);
}
~~~

Nếu validateCommandSynchronously ném lỗi, method chưa trả publisher nào. Lỗi thoát ra ở thời điểm gọi method. Framework web vẫn có thể xử lý exception đồng bộ theo cơ chế của nó, nhưng nếu muốn thống nhất lỗi trong reactive pipeline, có thể dùng Mono.defer:

~~~java
public Mono<Result> execute(Command command) {
    return Mono.defer(() -> {
        validateCommandSynchronously(command);
        return providerClient.execute(command);
    });
}
~~~

Mono.defer trì hoãn việc gọi supplier đến lúc có subscription. Exception phát sinh trong supplier được chuyển thành onError. Cách này hữu ích khi việc khởi tạo pipeline có thể thực hiện validation hoặc gọi method ném exception.

## 4. Các operator xử lý lỗi thường dùng

Reactor cung cấp nhiều operator cho những mục tiêu khác nhau. Cần chọn đúng operator để không vô tình biến lỗi thành thành công.

### 4.1. onErrorMap — chuyển loại lỗi

onErrorMap chuyển một lỗi thành lỗi khác. Đây là cách phù hợp để chuyển exception kỹ thuật thành exception nghiệp vụ hoặc exception đã chuẩn hóa.

~~~java
return providerClient.createDatabase(command)
        .onErrorMap(
                ProviderAuthenticationException.class,
                error -> new ProviderAccessException(
                        "Broker cannot access the provider",
                        error));
~~~

Lỗi gốc nên được giữ làm cause để phục vụ điều tra nội bộ. Thông điệp public không nên chứa nội dung response thô hoặc credential của provider.

Không nên dùng onErrorMap để biến mọi lỗi thành cùng một RuntimeException chung nếu broker cần phân biệt validation, quota, conflict và lỗi tạm thời.

### 4.2. onErrorResume — chuyển sang publisher thay thế

onErrorResume cho phép xử lý lỗi bằng một publisher khác. Có thể dùng khi có fallback hợp lệ hoặc cần thực hiện một bước bù trừ.

~~~java
return cacheClient.getResource(resourceId)
        .onErrorResume(CacheUnavailableException.class,
                error -> databaseClient.getResource(resourceId));
~~~

Fallback chỉ nên được dùng khi ngữ nghĩa nghiệp vụ cho phép. Ví dụ, không nên chuyển sang một provider khác để tạo database mới chỉ vì provider hiện tại timeout, bởi tài nguyên ở provider đầu tiên có thể đã được tạo.

Nếu lỗi không thể phục hồi bằng fallback, hãy truyền tiếp lỗi:

~~~java
return providerClient.create(command)
        .onErrorResume(error -> {
            if (isRecoverable(error)) {
                return recoveryService.recover(command, error);
            }
            return Mono.error(error);
        });
~~~

### 4.3. doOnError — quan sát lỗi, không xử lý thay thế

doOnError thực hiện side effect như ghi log hoặc tăng metric. Nó không tiêu thụ lỗi và không thay đổi tín hiệu lỗi.

~~~java
return providerClient.create(command)
        .doOnError(error ->
                metrics.recordProviderFailure("create", error));
~~~

Sau doOnError, lỗi vẫn tiếp tục tới downstream. Không dùng doOnError như thể nó đã chuyển lỗi thành response OSB.

Log cần có correlation ID, operation ID và provider key. Không ghi toàn bộ request/response nếu chúng có thể chứa secret.

### 4.4. onErrorReturn — trả giá trị mặc định

onErrorReturn thay lỗi bằng một giá trị. Cách này phù hợp với một số truy vấn có fallback an toàn, nhưng nguy hiểm trong thao tác vòng đời.

~~~java
return healthClient.checkProvider()
        .onErrorReturn(ProviderHealth.unavailable());
~~~

Ví dụ trên có thể phù hợp vì trạng thái health unavailable là một kết quả nghiệp vụ được định nghĩa. Nhưng không nên dùng onErrorReturn để trả một ProvisionResponse rỗng khi provider create thất bại. Platform sẽ có thể hiểu thao tác đã thành công.

### 4.5. retryWhen — thử lại có điều kiện

retryWhen resubscribe vào publisher khi lỗi thỏa điều kiện retry. Với lệnh có tác dụng phụ như create hoặc delete, chỉ retry khi thao tác có idempotency hoặc có thể xác định chắc chắn kết quả lần trước.

~~~java
return providerClient.getOperation(operationId)
        .retryWhen(
                Retry.backoff(3, Duration.ofSeconds(1))
                        .filter(this::isTransientProviderError));
~~~

Ví dụ này phù hợp hơn cho truy vấn trạng thái có thể lặp an toàn. Với create resource, cần idempotency key hoặc lookup/reconciliation trước khi retry.

Thứ tự operator có ý nghĩa. Retry nên áp dụng cho lỗi kỹ thuật mà broker xác định có thể thử lại; sau khi hết retry, lỗi mới được chuẩn hóa và chuyển tới lớp OSB.

### 4.6. onErrorComplete — kết thúc mà không báo lỗi

onErrorComplete thay onError bằng onComplete. Điều này có thể hữu ích cho một tác vụ best-effort, nhưng không phù hợp với thao tác OSB bắt buộc phải biết kết quả.

Không dùng onErrorComplete để che lỗi provision, update, bind hoặc deprovision. Nếu broker hoàn tất publisher mà không có response, framework có thể trả kết quả rỗng hoặc lỗi kỹ thuật khác, trong khi nguyên nhân ban đầu đã bị mất.

## 5. Không nhầm onError với Mono.empty

Một lỗi phổ biến là dùng Mono.empty khi không tìm thấy instance:

~~~java
return repository.findById(instanceId)
        .flatMap(this::deprovision);
~~~

Nếu không tìm thấy instance, pipeline hoàn tất rỗng. Không có exception để OSB error mapper xử lý. Tùy endpoint và framework, kết quả có thể không phải response mong muốn.

Hãy chuyển trạng thái không tồn tại thành một lỗi rõ ràng:

~~~java
return repository.findById(instanceId)
        .switchIfEmpty(Mono.error(
                new InstanceNotFoundException(instanceId)))
        .flatMap(this::deprovision);
~~~

Tương tự, một provider API có thể trả response 204 không có body. Adapter cần quyết định đây là thành công rỗng hợp lệ hay thiếu dữ liệu cần thiết. Không nên tự động coi mọi response không có body là lỗi hoặc thành công; phải dựa vào contract của API provider.

## 6. Phân loại lỗi theo nguồn và ý nghĩa nghiệp vụ

Một service broker nên có taxonomy lỗi chung để mọi handler và provider adapter áp dụng nhất quán.

Ví dụ:

~~~java
public enum BrokerFailureKind {
    INVALID_REQUEST,
    UNAUTHENTICATED,
    FORBIDDEN,
    INSTANCE_NOT_FOUND,
    BINDING_NOT_FOUND,
    CONFLICT,
    QUOTA_EXCEEDED,
    UNSUPPORTED,
    ASYNC_REQUIRED,
    PROVIDER_UNAVAILABLE,
    PROVIDER_TIMEOUT_UNKNOWN,
    PROVIDER_REJECTED,
    INTERNAL
}
~~~

Có thể phân loại theo nguồn:

| Nguồn | Ví dụ | Loại lỗi cần biểu diễn |
|---|---|---|
| Request validation | Thiếu service ID, plan ID hoặc parameters sai | INVALID_REQUEST |
| Authentication | Platform credentials không hợp lệ | UNAUTHENTICATED |
| Authorization | Tenant không được thao tác instance | FORBIDDEN |
| Broker state | Instance không tồn tại hoặc đang có operation xung đột | INSTANCE_NOT_FOUND / CONFLICT |
| Quota | Tenant đã dùng hết quota | QUOTA_EXCEEDED |
| Capability | Service không hỗ trợ binding hoặc update | UNSUPPORTED |
| Provider | Provider trả lỗi tạm thời hoặc từ chối request | PROVIDER_UNAVAILABLE / PROVIDER_REJECTED |
| Network | Timeout sau khi provider có thể đã nhận lệnh | PROVIDER_TIMEOUT_UNKNOWN |
| Application | Lỗi không dự kiến | INTERNAL |

Phân loại theo ý nghĩa giúp broker quyết định retry, trả lỗi client hay cảnh báo vận hành. Không nên chỉ phân loại theo Java exception class hoặc HTTP status gốc của provider.

## 7. Thiết kế exception nghiệp vụ

Có thể tạo một exception chung chứa loại lỗi, mã lỗi nội bộ và nguyên nhân gốc:

~~~java
public class BrokerOperationException extends RuntimeException {

    private final BrokerFailureKind kind;
    private final String errorCode;
    private final boolean retryable;

    public BrokerOperationException(
            BrokerFailureKind kind,
            String errorCode,
            boolean retryable,
            String safeMessage,
            Throwable cause) {
        super(safeMessage, cause);
        this.kind = kind;
        this.errorCode = errorCode;
        this.retryable = retryable;
    }

    public BrokerFailureKind kind() {
        return kind;
    }

    public String errorCode() {
        return errorCode;
    }

    public boolean retryable() {
        return retryable;
    }
}
~~~

Application service có thể ném lỗi cụ thể:

~~~java
return quotaService.reserve(command)
        .switchIfEmpty(Mono.error(
                new BrokerOperationException(
                        BrokerFailureKind.QUOTA_EXCEEDED,
                        "TENANT_QUOTA_EXCEEDED",
                        false,
                        "Tenant quota is exhausted",
                        null)));
~~~

Ví dụ này giả định quotaService biểu diễn việc không thể reserve bằng Mono.empty. Một dự án có thể chọn trả kiểu Result hoặc ném exception trực tiếp; điều quan trọng là lỗi được chuẩn hóa và không bị mất khi đi qua pipeline.

Không nên đưa HTTP status vào mọi exception nghiệp vụ nếu muốn giữ domain độc lập với giao thức. Một lớp OSB error mapper có thể chịu trách nhiệm ánh xạ BrokerFailureKind sang loại exception hoặc response mà framework hỗ trợ.

## 8. Ánh xạ lỗi sang hợp đồng OSB

OSB error response có cấu trúc máy đọc được, thường gồm trường error và description. Ví dụ minh họa:

~~~http
HTTP/1.1 409 Conflict
Content-Type: application/json
~~~

~~~json
{
  "error": "Conflict",
  "description": "A conflicting operation is already in progress"
}
~~~

HTTP status cho biết nhóm kết quả ở cấp giao thức. Trường error cung cấp mã lỗi để client hoặc người vận hành nhận diện; description giải thích ngắn gọn.

Một số nhóm status thường gặp:

| HTTP status | Trường hợp thường dùng |
|---|---|
| 400 Bad Request | Request không hợp lệ hoặc thiếu dữ liệu bắt buộc |
| 401 Unauthorized | Xác thực broker client thất bại |
| 403 Forbidden | Client đã xác thực nhưng không có quyền |
| 404 Not Found | Tài nguyên hoặc endpoint không tồn tại theo ngữ nghĩa phù hợp |
| 409 Conflict | Trạng thái hiện tại xung đột với thao tác |
| 410 Gone | Tài nguyên đã bị thu hồi hoặc không còn tồn tại theo ngữ nghĩa endpoint |
| 422 Unprocessable Entity | Request hợp lệ về cú pháp nhưng không thể xử lý theo điều kiện OSB, ví dụ asynchronous operation không được client chấp nhận |
| 500 Internal Server Error | Lỗi nội bộ không dự kiến |
| 502 Bad Gateway | Broker nhận phản hồi không hợp lệ từ dependency hoặc provider theo chính sách gateway của ứng dụng |
| 503 Service Unavailable | Broker hoặc dependency tạm thời không sẵn sàng |
| 504 Gateway Timeout | Dependency không phản hồi trong giới hạn thời gian |

Bảng này là hướng dẫn phân loại, không thay thế quy tắc cụ thể của phiên bản OSB API. Một số điều kiện có error code và status được đặc tả riêng; cần dùng đúng contract mà framework và platform đang hỗ trợ.

Đặc biệt, không sao chép HTTP status từ provider một cách máy móc. Ví dụ provider trả 404 vì resource phía provider không tồn tại có thể là dấu hiệu mapping bị lệch, trong khi platform đang thao tác với một service instance hợp lệ. Broker phải diễn giải theo ngữ nghĩa nghiệp vụ trước khi trả lỗi OSB.

## 9. Dùng cơ chế exception của Spring Cloud Open Service Broker

Spring Cloud Open Service Broker cung cấp abstraction và cơ chế xử lý request/response OSB. Các phiên bản thư viện có thể cung cấp các exception chuyên biệt cho những trường hợp như instance không tồn tại, binding không tồn tại, request không hợp lệ hoặc broker không khả dụng.

Khi triển khai:

1. Kiểm tra phiên bản framework đang dùng và danh sách exception/response model được hỗ trợ.
2. Ưu tiên ném loại exception của framework khi nó diễn tả đúng lỗi OSB.
3. Với lỗi riêng của domain hoặc provider, dùng lớp adapter để chuyển sang exception framework tương ứng.
4. Để framework thực hiện việc serialize và ánh xạ HTTP theo contract mà nó hỗ trợ.
5. Chỉ bổ sung custom exception handler khi cần xử lý trường hợp framework không bao phủ và đã xác minh không xung đột với handler mặc định.

Không nên giả định mọi phiên bản framework có cùng tên class, constructor hoặc cách ánh xạ. Hãy đối chiếu API của đúng release đang dùng. Tránh tự viết một WebExceptionHandler toàn cục chỉ để đổi mọi exception thành 500; cách đó có thể ghi đè xử lý OSB mặc định và làm mất error semantics.

Một adapter có thể có dạng khái niệm:

~~~java
public RuntimeException toFrameworkException(
        BrokerOperationException failure) {

    return switch (failure.kind()) {
        case INVALID_REQUEST ->
                frameworkErrors.badRequest(failure);
        case INSTANCE_NOT_FOUND ->
                frameworkErrors.instanceNotFound(failure);
        case BINDING_NOT_FOUND ->
                frameworkErrors.bindingNotFound(failure);
        case CONFLICT, QUOTA_EXCEEDED ->
                frameworkErrors.conflict(failure);
        case PROVIDER_UNAVAILABLE ->
                frameworkErrors.serviceUnavailable(failure);
        default ->
                frameworkErrors.internalError(failure);
    };
}
~~~

frameworkErrors ở đây là facade minh họa của ứng dụng, không phải API có sẵn của thư viện. Mục đích là giữ logic phân loại tập trung, thay vì để từng handler tự chọn HTTP status.

## 10. Ánh xạ lỗi theo từng thao tác OSB

Cùng một lỗi kỹ thuật có thể mang ý nghĩa khác nhau tùy thao tác. Cần xét endpoint và trạng thái hiện tại.

| Thao tác | Tình huống | Cách xử lý ở broker |
|---|---|---|
| Catalog | Cấu hình catalog không hợp lệ | Không công bố catalog sai; báo lỗi nội bộ và log có kiểm soát |
| Provision | Plan ID không được hỗ trợ | Trả lỗi request phù hợp theo OSB |
| Provision | Instance ID đã tồn tại với request khác | Xử lý conflict/idempotency |
| Provision | Provider tạm thời không khả dụng | Retry có điều kiện hoặc trả lỗi tạm thời |
| Update | Instance không tồn tại | Trả lỗi theo semantics endpoint |
| Update | Instance đang có update khác | Trả conflict hoặc xử lý cùng operation nếu là retry |
| Bind | Service không bindable | Từ chối theo capability và contract |
| Bind | Instance chưa ACTIVE | Trả lỗi trạng thái hoặc conflict phù hợp |
| Unbind | Binding không tồn tại | Xử lý theo semantics unbind và contract của framework |
| Deprovision | Provider timeout sau khi gửi delete | Trạng thái chưa xác định; đối soát trước khi retry |

Không nên dùng cùng một response cho tất cả lỗi chỉ để đơn giản hóa code. Platform cần phân biệt request sai, thiếu quyền, xung đột trạng thái và lỗi dependency để có hành động phù hợp.

## 11. Xử lý lỗi provider trong adapter

Provider adapter nên chuyển lỗi riêng của SDK hoặc HTTP client thành loại lỗi chung. Ví dụ provider trả HTTP 429, 503 hoặc timeout.

~~~java
return providerClient.createResource(command)
        .onErrorMap(ProviderHttpException.class, error -> {
            if (error.statusCode() == 429) {
                return new BrokerOperationException(
                        BrokerFailureKind.PROVIDER_UNAVAILABLE,
                        "PROVIDER_RATE_LIMITED",
                        true,
                        "Provider rate limit was reached",
                        error);
            }

            if (error.statusCode() >= 500) {
                return new BrokerOperationException(
                        BrokerFailureKind.PROVIDER_UNAVAILABLE,
                        "PROVIDER_TEMPORARY_FAILURE",
                        true,
                        "Provider is temporarily unavailable",
                        error);
            }

            return new BrokerOperationException(
                    BrokerFailureKind.PROVIDER_REJECTED,
                    "PROVIDER_REQUEST_REJECTED",
                    false,
                    "Provider rejected the operation",
                    error);
        });
~~~

Ví dụ chỉ minh họa phân loại cơ bản. Cần xử lý riêng các mã 401/403, 404, 409 và timeout. Không phải mọi lỗi 5xx đều an toàn để retry một request tạo tài nguyên; cần idempotency key hoặc tra cứu trạng thái trước khi thử lại.

Nếu provider timeout sau khi đã nhận lệnh create, broker không biết chắc tài nguyên đã được tạo hay chưa. Hãy biểu diễn trạng thái UNKNOWN, giữ operation đang chờ đối soát và tránh trả lỗi theo cách khiến platform tạo một instance mới ngoài ý muốn.

## 12. Retry trước hay sau khi chuẩn hóa lỗi?

Thứ tự operator ảnh hưởng đến loại lỗi mà retryWhen nhìn thấy.

Một cách triển khai là phân loại lỗi provider trước, sau đó retry những lỗi đã được đánh dấu retryable:

~~~java
return providerClient.getResource(resourceId)
        .onErrorMap(providerErrorMapper::toBrokerException)
        .retryWhen(
                Retry.backoff(3, Duration.ofSeconds(1))
                        .filter(error ->
                                error instanceof BrokerOperationException
                                && ((BrokerOperationException) error)
                                        .retryable()));
~~~

Với Java version hỗ trợ pattern matching, phần filter có thể viết ngắn hơn. Ví dụ trên dùng cú pháp phổ biến để dễ áp dụng.

Không retry validation, authentication hoặc authorization error. Retry có giới hạn cho lỗi tạm thời và cần exponential backoff cùng jitter. Với thao tác có tác dụng phụ, chỉ retry khi idempotency được bảo đảm.

Sau khi retry hết số lần, lỗi cuối cùng tiếp tục downstream. Lớp application hoặc OSB mapper có thể chuyển nó thành phản hồi giao thức hoặc cập nhật operation failed.

Không nên đặt onErrorResume trả success sau retry chỉ để tránh lỗi hiển thị. Nếu provider vẫn thất bại, broker phải phản ánh đúng trạng thái.

## 13. Bảo toàn nguyên nhân gốc nhưng không lộ chi tiết nội bộ

Exception chain nên giữ cause để log và trace nội bộ. Tuy nhiên, description trả platform phải an toàn.

Ví dụ lỗi nội bộ có thể chứa:

- Provider hostname và endpoint.
- Tên account hoặc project.
- Request/response body.
- SDK stack trace.
- Credential hoặc token.
- Query database.
- Thông tin tenant khác.

Không trả các dữ liệu này trong OSB error response. Có thể dùng error code ngắn và correlation ID:

~~~json
{
  "error": "ServiceUnavailable",
  "description": "Provider is temporarily unavailable. Reference: op-9c21"
}
~~~

Correlation ID phải cho phép người vận hành tìm log nội bộ có quyền truy cập. Không dùng description làm nơi truyền stack trace.

Log nên ghi exception gốc ở mức phù hợp, đã redaction. Không log password, access token, private key hoặc connection string chứa credential. Cũng cần cân nhắc tránh tiết lộ sự tồn tại của instance thuộc tenant khác qua khác biệt message quá chi tiết.

## 14. Lỗi đồng bộ và lỗi của asynchronous operation

Đây là khác biệt quan trọng trong OSB API.

Với thao tác đồng bộ, broker chưa trả response cuối cùng cho request ban đầu. Nếu pipeline thất bại, lỗi có thể được chuyển thành HTTP error response của request đó.

Với thao tác bất đồng bộ, broker đã trả HTTP 202 Accepted và operation ID. Request ban đầu đã kết thúc thành công ở cấp tiếp nhận. Nếu worker thất bại sau đó, broker không thể quay lại thay response 202 bằng HTTP 500 cho request cũ.

Khi worker lỗi:

1. Ghi operation state thành FAILED.
2. Lưu error code và description an toàn.
3. Cập nhật instance state theo quy tắc phục hồi.
4. Endpoint last_operation trả state failed.
5. Platform đọc kết quả và quyết định retry hoặc yêu cầu can thiệp.

~~~mermaid
sequenceDiagram
    participant P as Platform
    participant B as Broker
    participant W as Worker
    participant V as Provider
    P->>B: Provision request
    B->>B: Lưu operation ACCEPTED
    B-->>P: 202 Accepted + operation ID
    W->>V: Create resource
    V--xW: Provider failure
    W->>B: Lưu operation FAILED
    P->>B: GET last_operation
    B-->>P: state = failed
~~~

Không được biến lỗi worker sau 202 thành một response HTTP lỗi cho request đã hoàn tất. Trạng thái thất bại phải được truyền qua last_operation theo hợp đồng OSB.

Cũng cần phân biệt lỗi khi platform gọi chính endpoint last_operation, ví dụ operation ID không tồn tại, với việc operation đã tồn tại nhưng state là failed. Trường hợp thứ nhất là lỗi của request truy vấn; trường hợp thứ hai là kết quả nghiệp vụ của thao tác trước đó.

## 15. Không để lỗi bị mất khi chạy background worker

Nếu broker dùng queue hoặc executor để xử lý thao tác sau khi trả 202, lỗi trong worker không còn nằm trong subscription của request ban đầu. Worker phải tự bắt và lưu kết quả.

~~~java
public Mono<Void> executeOperation(String operationId) {
    return operationService.load(operationId)
            .flatMap(operation ->
                    providerAdapter.execute(operation.command()))
            .flatMap(result ->
                    operationService.markSucceeded(
                            operationId, result))
            .onErrorResume(error ->
                    operationService.markFailed(
                            operationId,
                            errorMapper.toSafeFailure(error)));
}
~~~

Ví dụ minh họa cho thấy worker chuyển lỗi thành trạng thái FAILED trong kho operation. Nếu việc ghi trạng thái FAILED cũng lỗi, không được âm thầm bỏ qua. Cần để message được retry hoặc đưa vào dead-letter/recovery flow theo chính sách.

Không dùng doOnError để chỉ ghi log rồi coi worker đã xử lý xong. Nếu queue được ack trong khi operation chưa được cập nhật, platform có thể polling mãi mà không biết kết quả.

## 16. Cancellation không đồng nghĩa rollback

Trong WebFlux, client đóng kết nối hoặc timeout có thể khiến subscription bị cancel. Cancellation là tín hiệu điều khiển luồng reactive, không phải một giao dịch rollback cho hệ thống bên ngoài.

Ví dụ provider đã tạo database nhưng platform đóng kết nối trước khi broker gửi response. Broker không thể giả định database đã bị xóa. Cần kiểm tra trạng thái provider và mapping trước khi xử lý retry.

Với operation đã được chấp nhận bền vững và trả 202, worker nên có vòng đời độc lập với HTTP subscription. Việc platform ngắt kết nối khi polling không được làm mất công việc đã được broker chấp nhận.

Có thể dùng doFinally để quan sát tín hiệu complete, error hoặc cancel, nhưng không nên tự động giải phóng quota hoặc xóa resource chỉ vì request bị cancel. Hành động bù trừ phải dựa trên state machine và kết quả provider thực tế.

## 17. Xử lý lỗi ở tầng handler và global exception handler

Nên có một điểm tập trung để chuyển lỗi nghiệp vụ sang exception hoặc response mà Spring Cloud Open Service Broker hỗ trợ.

Có thể tổ chức theo các lớp:

- Provider adapter chuẩn hóa lỗi SDK.
- Application service phát sinh lỗi nghiệp vụ.
- Error mapper chuyển BrokerFailureKind sang framework exception phù hợp.
- Framework OSB xử lý response serialization và HTTP status.
- Global exception handler chỉ xử lý các lỗi nằm ngoài cơ chế mặc định, sau khi xác minh không ghi đè contract OSB.

Không nên đặt một catch-all trong mọi handler rồi trả một response thành công giả. Cũng không nên bắt Throwable và chuyển tất cả thành 400, vì lỗi nội bộ hoặc provider outage không phải lỗi request của client.

Nếu dùng @ControllerAdvice hoặc WebExceptionHandler, cần kiểm tra thứ tự ưu tiên và phạm vi áp dụng. Một handler toàn cục có thể bắt exception trước cơ chế OSB của framework, làm response thiếu trường error hoặc sai status.

Trong hệ thống có nhiều loại endpoint, có thể giới hạn custom handler vào các route hoặc exception cụ thể. Hãy kiểm thử response HTTP thực tế, không chỉ kiểm tra exception được ném trong unit test.

## 18. Kiểm thử error mapping

Kiểm thử nên bao gồm cả tín hiệu Reactor và response HTTP cuối cùng.

| Kiểm thử | Kết quả cần xác minh |
|---|---|
| Mono.error từ validation | Được chuyển thành lỗi request phù hợp |
| Repository Mono.empty | Được chuyển thành lỗi not found nếu nghiệp vụ yêu cầu |
| Provider 429 | Được phân loại rate limit và retry có giới hạn |
| Provider timeout không rõ kết quả | Không tạo tác dụng phụ lặp; operation cần đối soát |
| Lỗi authentication | Không retry vô hạn và không lộ credential |
| Instance đang có operation khác | Response conflict phù hợp |
| Worker thất bại sau 202 | last_operation trả failed |
| last_operation không tìm thấy ID | Request truy vấn nhận lỗi phù hợp |
| Client cancel | Không giải phóng resource hoặc quota sai |
| Exception không dự kiến | Trả lỗi 5xx an toàn và có correlation ID |

Ví dụ kiểm thử pipeline:

~~~java
StepVerifier.create(service.execute(command))
        .expectErrorMatches(error ->
                error instanceof BrokerOperationException
                && ((BrokerOperationException) error).kind()
                        == BrokerFailureKind.QUOTA_EXCEEDED)
        .verify();
~~~

StepVerifier kiểm tra tín hiệu của publisher. Nó không chứng minh HTTP status và JSON error response đúng. Cần thêm kiểm thử tích hợp WebTestClient hoặc công cụ HTTP tương đương để gọi endpoint OSB, xác minh status, content type và body theo contract.

Kiểm thử lỗi cần xác nhận cả phần không được phép xuất hiện: stack trace, password, provider token và raw response body.

## 19. Các lỗi thiết kế thường gặp

| Hiện tượng | Nguyên nhân | Hướng xử lý |
|---|---|---|
| Platform nhận HTTP 200 dù provider thất bại | onError bị thay bằng giá trị mặc định hoặc response giả | Giữ tín hiệu lỗi và ánh xạ qua OSB |
| Instance không tồn tại nhưng endpoint trả rỗng | Không chuyển Mono.empty thành lỗi nghiệp vụ | Dùng switchIfEmpty |
| Mọi lỗi thành HTTP 500 | Không có taxonomy và error mapper | Phân loại lỗi trước khi chuyển sang framework |
| Provider 429 bị trả thành lỗi nội bộ | Không chuẩn hóa provider error | Map rate limit và retry có điều kiện |
| Timeout create bị retry tạo resource trùng | Không phân biệt timeout chắc chắn và kết quả UNKNOWN | Idempotency key và reconciliation |
| Lỗi chỉ xuất hiện trong log, platform không thấy | doOnError bị hiểu nhầm là xử lý lỗi | Để lỗi tiếp tục hoặc lưu trạng thái operation |
| Worker thất bại nhưng last_operation vẫn in progress | Không ghi operation FAILED | Persist trạng thái lỗi và kiểm thử worker |
| Cancellation làm giải phóng quota sớm | Coi cancel như rollback | Dựa trên state machine và provider state |
| Global handler làm sai response OSB | Bắt exception trước framework handler | Kiểm tra thứ tự handler và giới hạn phạm vi |
| Response lỗi chứa stack trace | Dùng exception message thô | Tách public description và internal cause |

## 20. Quy trình thiết kế và triển khai

Khi bổ sung error handling cho một service broker, có thể thực hiện theo trình tự:

1. Liệt kê lỗi có thể phát sinh ở handler, application service, repository và provider adapter.
2. Phân loại lỗi theo ý nghĩa nghiệp vụ, khả năng retry và tính xác định của kết quả.
3. Tạo exception hoặc error model chung, giữ cause cho log nội bộ.
4. Chuẩn hóa lỗi provider trong adapter.
5. Dùng Reactor operator đúng mục tiêu: map, resume, retry hoặc side effect.
6. Chuyển lỗi nghiệp vụ sang exception framework OSB tương ứng.
7. Xác minh HTTP status và error body cho thao tác đồng bộ.
8. Với thao tác đã trả 202, lưu trạng thái FAILED và phục vụ qua last_operation.
9. Redact thông tin nhạy cảm và gắn correlation ID.
10. Kiểm thử StepVerifier cho pipeline và kiểm thử HTTP cho contract OSB.
11. Kiểm thử retry, timeout, cancellation và worker restart.
12. Theo dõi metric lỗi theo operation, provider và failure kind.

Cần kiểm tra đúng phiên bản Spring Cloud Open Service Broker mà dự án đang sử dụng. Các exception type, response model và cơ chế xử lý lỗi có thể khác giữa các release. Hãy dùng abstraction được phiên bản đó hỗ trợ thay vì giả định một tên class hoặc builder luôn tồn tại.

## 21. Checklist rà soát

- [ ] Hiểu Mono truyền lỗi bằng onError và phân biệt với Mono.empty.
- [ ] Exception trong pipeline được truyền tới subscriber/framework.
- [ ] Lỗi phát sinh đồng bộ khi dựng pipeline được xử lý có chủ đích.
- [ ] onErrorMap chỉ chuyển loại lỗi, không làm mất cause.
- [ ] onErrorResume chỉ dùng khi có fallback nghiệp vụ hợp lệ.
- [ ] doOnError chỉ dùng cho quan sát, không coi là đã xử lý lỗi.
- [ ] Không dùng onErrorReturn hoặc onErrorComplete để che lỗi vòng đời.
- [ ] Có taxonomy lỗi chung cho validation, authorization, conflict, quota và provider.
- [ ] Provider error được chuẩn hóa trước khi tới OSB mapper.
- [ ] Retry có giới hạn và chỉ áp dụng cho lỗi an toàn.
- [ ] Timeout không rõ kết quả được xử lý bằng idempotency và reconciliation.
- [ ] Lỗi đồng bộ được chuyển thành HTTP status và error body theo OSB.
- [ ] Lỗi worker sau 202 được lưu và trả qua last_operation.
- [ ] Cancellation không bị xem như rollback.
- [ ] Global exception handler không ghi đè xử lý mặc định của framework.
- [ ] Error response không chứa secret, stack trace hoặc raw provider body.
- [ ] Có correlation ID để nối response lỗi với log nội bộ.
- [ ] Đã kiểm thử cả Reactor signal và HTTP contract thực tế.

Reactor cung cấp cơ chế truyền lỗi trong pipeline; OSB API quy định cách broker thông báo lỗi cho platform. Một thiết kế tốt giữ được nguyên nhân gốc, phân loại lỗi theo ý nghĩa nghiệp vụ, retry có điều kiện và chuyển đúng loại lỗi sang framework. Với thao tác đồng bộ, lỗi được phản ánh trong HTTP response của request hiện tại. Với thao tác đã được chấp nhận bằng 202, lỗi xảy ra sau đó phải được lưu trong operation journal và trả qua last_operation. Khi hai lớp này được xử lý nhất quán, platform có thể phân biệt request sai, xung đột trạng thái, lỗi provider và sự cố nội bộ để phản ứng đúng.

