# Thiết kế giao diện bộ điều hợp cho từng nhà cung cấp dịch vụ

Một Spring Cloud service broker có thể cung cấp cùng một loại dịch vụ thông qua nhiều nhà cung cấp hạ tầng. Ví dụ, PostgreSQL có thể chạy trên dịch vụ database managed của một cloud provider, trên Kubernetes thông qua operator hoặc trên một nền tảng nội bộ. Mỗi nhà cung cấp có API, mô hình tài nguyên, cách xác thực, trạng thái thao tác và quy tắc lỗi riêng.

Nếu đưa toàn bộ khác biệt đó vào handler của Open Service Broker API (OSB API), mã nghiệp vụ sẽ phụ thuộc trực tiếp vào từng SDK và API nhà cung cấp. Khi thêm provider mới, nhiều phần của broker phải thay đổi; khi provider đổi API, logic provision, update, binding và deprovision có thể bị ảnh hưởng dây chuyền.

Provider adapter giải quyết vấn đề bằng cách đặt một giao diện nghiệp vụ ổn định giữa service broker và từng nhà cung cấp. Lớp OSB xử lý hợp đồng với platform; application service điều phối vòng đời; provider adapter chuyển các lệnh nghiệp vụ thành lời gọi API cụ thể và chuẩn hóa kết quả về mô hình mà broker hiểu.

Bài học trình bày cách thiết kế giao diện adapter, xác định ranh giới giữa mô hình chung và đặc thù provider, lựa chọn adapter theo service plan, xử lý capability, lỗi, idempotency và thao tác bất đồng bộ, đồng thời tổ chức kiểm thử để có thể thay đổi nhà cung cấp mà không làm hỏng phần nghiệp vụ của broker.

## 1. Vì sao cần provider adapter?

Giả sử broker cung cấp PostgreSQL với plan small và production. Có hai cách triển khai hạ tầng:

- Provider A cung cấp REST API tạo database instance, trả về resource ID và operation ID.
- Provider B cung cấp Kubernetes operator; broker tạo Custom Resource rồi theo dõi trạng thái qua Kubernetes API.

Cùng một yêu cầu OSB provision nhưng hai provider có cách thực hiện khác nhau. Provider A có thể cần project ID, region và instance class. Provider B cần namespace, tên Custom Resource, storage class và Kubernetes context.

Nếu handler tự gọi từng SDK, code có thể dần trở thành:

~~~java
if (providerName.equals("provider-a")) {
    // Gọi REST API của Provider A
} else if (providerName.equals("provider-b")) {
    // Tạo Custom Resource trên Kubernetes
} else if (providerName.equals("internal")) {
    // Gọi API của hạ tầng nội bộ
}
~~~

Cách làm này khiến handler biết quá nhiều về hạ tầng. Mỗi nhánh có thể có quy tắc retry, timeout, xác thực và xử lý lỗi khác nhau. Việc thêm provider mới làm tăng độ phức tạp của tất cả nơi có điều kiện phân nhánh.

Với adapter, application service chỉ làm việc với một contract chung:

~~~text
OSB Handler
    |
    v
Application Service
    |
    v
Provider Adapter Interface
    |
    +---- Provider A Adapter ---- Provider A API
    |
    +---- Provider B Adapter ---- Kubernetes API
    |
    +---- Internal Adapter ------ Internal Platform API
~~~

Application service không cần biết provider dùng REST, SDK hay Kubernetes client. Nó chỉ gửi lệnh theo mô hình nghiệp vụ và nhận kết quả theo contract đã định nghĩa.

Adapter giúp:

- Cô lập SDK, endpoint và kiểu dữ liệu riêng của provider.
- Giữ logic OSB không phụ thuộc vào một nhà cung cấp cụ thể.
- Chuẩn hóa kết quả provision, update, binding và deprovision.
- Áp dụng chính sách retry, timeout và error mapping nhất quán.
- Kiểm thử nghiệp vụ broker bằng fake adapter.
- Thêm hoặc thay provider với phạm vi thay đổi rõ ràng.

Adapter không làm các provider trở nên giống nhau hoàn toàn. Nó tạo một ranh giới có chủ đích để phần chung chỉ phụ thuộc vào những khả năng mà broker thực sự cần.

## 2. Xác định ranh giới trách nhiệm

Trước khi thiết kế interface, cần quyết định lớp nào sở hữu từng loại logic.

| Thành phần | Trách nhiệm |
|---|---|
| OSB Handler | Nhận request OSB, kiểm tra cấu trúc giao thức và tạo command |
| Application Service | Điều phối state machine, quota, tenant, operation và transaction |
| Provider Adapter | Chuyển command sang API provider và chuẩn hóa kết quả |
| Provider SDK/HTTP Client | Thực hiện giao tiếp kỹ thuật với hệ thống bên ngoài |
| Repository | Lưu instance mapping, operation và binding |
| Operation Worker | Chạy tác vụ dài, retry và cập nhật trạng thái |
| Adapter Registry/Resolver | Chọn adapter theo service, plan hoặc provider profile |

Các quy tắc quan trọng:

- Handler không nên chứa tên class SDK hoặc kiểu response riêng của provider.
- Provider adapter không nên tự quyết định platform OSB cần nhận HTTP status nào.
- Application service sở hữu state transition và chính sách vòng đời của broker.
- Repository lưu mapping giữa OSB ID và provider resource ID.
- Adapter chỉ chuyển đổi dữ liệu và thực hiện thao tác provider trong phạm vi contract.
- Secret được lấy qua cơ chế quản lý secret; không truyền credential dạng rõ qua nhiều lớp nếu không cần thiết.

Ví dụ, provider trả HTTP 409 khi resource đã tồn tại. Adapter có thể chuyển kết quả này thành ProviderConflictException. Application service quyết định đó là retry idempotent có thể chấp nhận, xung đột request cần từ chối hay trạng thái cần reconciliation. OSB handler cuối cùng mới ánh xạ kết quả nghiệp vụ thành response theo hợp đồng OSB.

## 3. Thiết kế mô hình nghiệp vụ trung lập với provider

Contract chung nên sử dụng các kiểu dữ liệu của miền service broker thay vì để lộ kiểu dữ liệu của SDK.

Ví dụ một lệnh provision trung lập:

~~~java
public record ProvisionResourceCommand(
        String serviceInstanceId,
        String serviceId,
        String planId,
        String tenantId,
        String providerAccount,
        String region,
        String idempotencyKey,
        Map<String, Object> parameters) {
}
~~~

Mô hình này chứa các dữ liệu mà application service cần chuyển tới provider. Trong ứng dụng production, nên thay Map parameters bằng DTO có schema hoặc một kiểu tham số đã được validate theo service/plan. Map chỉ phù hợp khi adapter cần hỗ trợ một tập tham số mở đã được kiểm soát.

Kết quả provision có thể biểu diễn:

~~~java
public record ProviderResourceReference(
        String provider,
        String account,
        String region,
        String resourceId,
        String resourceName) {
}

public record ProviderOperationReference(
        String operationId,
        ProviderOperationState state) {
}

public enum ProviderOperationState {
    ACCEPTED,
    IN_PROGRESS,
    SUCCEEDED,
    FAILED,
    UNKNOWN
}

public record ProvisionSubmission(
        ProviderResourceReference resource,
        ProviderOperationReference operation) {
}
~~~

Resource reference và operation reference được tách riêng vì một provider có thể tạo resource ngay nhưng vẫn đang chạy cấu hình bổ sung, hoặc chỉ trả operation ID trước khi có resource ID.

Không nên dùng một chuỗi id chung cho cả instance, resource và operation. Các định danh có phạm vi khác nhau và được dùng ở những bước khác nhau của vòng đời.

## 4. Xác định contract tối thiểu của ProviderAdapter

Một interface tổng quát có thể cung cấp các thao tác mà broker cần:

~~~java
public interface ProviderAdapter {

    ProviderKey key();

    ProviderCapabilities capabilities();

    Mono<ProvisionSubmission> provision(
            ProvisionResourceCommand command);

    Mono<ProviderOperationStatus> getOperation(
            ProviderOperationReference operation);

    Mono<ProviderResourceSnapshot> getResource(
            ProviderResourceReference resource);

    Mono<ProviderOperationReference> update(
            UpdateResourceCommand command);

    Mono<ProviderOperationReference> deprovision(
            DeprovisionResourceCommand command);

    Mono<BindingSubmission> bind(
            BindResourceCommand command);

    Mono<Void> unbind(
            UnbindResourceCommand command);
}
~~~

Đây là contract minh họa ở tầng ứng dụng. Tên kiểu dữ liệu, chữ ký method và việc dùng Mono cần phù hợp với kiến trúc reactive hoặc imperative của dự án. Nếu adapter dùng blocking SDK, không nên giả vờ rằng lời gọi đã trở thành non-blocking chỉ bằng cách bọc trong Mono; cần cô lập blocking I/O trên scheduler phù hợp hoặc dùng client reactive.

Không phải provider nào cũng hỗ trợ tất cả thao tác. Có thể tách interface theo capability để tránh một contract quá lớn:

- ProvisioningProvider: tạo và tra cứu tài nguyên.
- UpdatingProvider: cập nhật tài nguyên.
- BindingProvider: tạo và thu hồi binding.
- DeprovisioningProvider: xóa tài nguyên.
- OperationTrackingProvider: theo dõi tác vụ provider bất đồng bộ.

Tách interface hữu ích khi có nhiều loại backing service với khả năng khác nhau. Tuy nhiên, không nên chia nhỏ quá mức đến mức application service phải ghép quá nhiều interface thủ công. Hãy bắt đầu từ những thao tác thực sự cần và mở rộng khi xuất hiện khác biệt có ý nghĩa.

## 5. Capability là một phần của contract

Một provider có thể hỗ trợ provision và deprovision nhưng không hỗ trợ update plan. Provider khác có thể hỗ trợ binding credentials nhưng không hỗ trợ volume attachment.

Broker cần biết khả năng trước khi gọi thao tác. Có thể định nghĩa:

~~~java
public record ProviderCapabilities(
        boolean supportsUpdate,
        boolean supportsAsyncProvision,
        boolean supportsAsyncUpdate,
        boolean supportsAsyncDeprovision,
        boolean supportsBinding,
        boolean supportsVolumeMount,
        boolean supportsLogDrain,
        boolean supportsIdempotencyKey) {
}
~~~

Application service dùng capability để kiểm tra tính khả thi của yêu cầu:

- Nếu plan cho phép update nhưng adapter không hỗ trợ update, broker phải xác định chính sách tương thích hoặc từ chối thao tác.
- Nếu platform không chấp nhận asynchronous operation nhưng provider chỉ có API async, broker cần quyết định có thể chờ hoàn tất trong giới hạn timeout hay trả lỗi theo OSB.
- Nếu service công bố bindable nhưng adapter không hỗ trợ binding, catalog và implementation đang không nhất quán.
- Nếu broker công bố volume_mount hoặc syslog_drain, cần có adapter và platform có thể thực thi capability đó.

Capability của provider và capability công bố trong OSB catalog là hai lớp khác nhau. Catalog phản ánh khả năng mà broker cung cấp cho platform sau khi xét plan, provider và chính sách. Không được lấy nguyên capability thô của provider rồi công bố mà không kiểm tra phần broker đã triển khai.

## 6. Chọn adapter theo service và plan

Một broker có thể kết nối nhiều provider. Việc chọn adapter nên dựa trên cấu hình định tuyến ổn định, thường gắn với service ID, plan ID hoặc provider profile.

Ví dụ cấu hình:

~~~yaml
broker:
  provider-routing:
    - service-id: postgres-service-id
      plan-id: postgres-small-plan-id
      adapter: cloud-postgres
      account: development-account
      region: ap-southeast-1

    - service-id: postgres-service-id
      plan-id: postgres-production-plan-id
      adapter: managed-postgres
      account: production-account
      region: ap-southeast-1

    - service-id: redis-service-id
      plan-id: redis-cache-plan-id
      adapter: kubernetes-redis
      account: cluster-main
      region: local
~~~

Cấu hình này là namespace nội bộ của ứng dụng, không phải trường chuẩn của OSB API. Nó cho phép broker ánh xạ lựa chọn trong catalog tới provider và phạm vi tài nguyên thực tế.

Resolver có thể nhận service ID và plan ID:

~~~java
public interface ProviderAdapterResolver {
    ProviderAdapter resolve(String serviceId, String planId);
}
~~~

Resolver cần kiểm tra cấu hình duy nhất cho mỗi cặp service/plan. Nếu không tìm thấy adapter hoặc có cấu hình trùng, broker nên phát hiện sớm khi khởi động hoặc từ chối request với lỗi cấu hình rõ ràng. Không tự chọn adapter mặc định có quyền rộng hơn.

Không nên để client tự gửi tên adapter hoặc provider account rồi broker tin tưởng trực tiếp. Những giá trị này phải đến từ cấu hình đã được quản trị và được kiểm tra theo tenant policy.

## 7. Chuẩn hóa resource mapping

Provider trả resource ID theo quy tắc riêng. Adapter cần chuyển ID đó thành ProviderResourceReference và broker lưu mapping với OSB service instance.

Ví dụ:

| Provider | Định danh riêng | Mapping chung |
|---|---|---|
| Cloud database API | db-7f8a | provider resource ID |
| Kubernetes | namespace/name hoặc UID | provider resource ID |
| Internal platform | allocationKey | provider resource ID |
| Object storage | bucket ARN hoặc bucket ID | provider resource ID |

Mapping cần giữ thêm provider key, account/project, region hoặc cluster nếu resource ID chỉ duy nhất trong phạm vi đó.

Ví dụ entity mapping:

~~~java
public record ProviderResourceReference(
        String provider,
        String account,
        String region,
        String resourceId,
        String resourceName) {
}
~~~

Broker dùng OSB instance ID để tìm bản ghi nội bộ, sau đó lấy provider reference để gọi adapter. Không yêu cầu platform biết resource ID của provider.

Nếu adapter phải tạo tên tài nguyên deterministic, hãy lưu cả tên và resource ID do provider trả về. Tên có thể giúp lookup sau timeout; ID trả về vẫn là định danh ưu tiên khi gọi API nếu provider hỗ trợ.

## 8. Idempotency xuyên qua adapter

Platform có thể retry provision hoặc deprovision. Worker cũng có thể nhận lại message. Adapter cần hỗ trợ việc gọi provider một cách an toàn khi có retry.

Command nên mang idempotency key do application service tạo. Ví dụ:

~~~text
service-instance-id : operation-type : operation-generation
~~~

Provider adapter chuyển key sang header hoặc request token tương ứng nếu provider hỗ trợ.

Contract cần quy định:

- Cùng key và cùng nội dung request phải trả lại kết quả tương đương.
- Cùng key nhưng payload khác phải được phát hiện là xung đột.
- Adapter không tự tạo key mới mỗi lần retry.
- Nếu provider không hỗ trợ idempotency, adapter cần lookup theo tag/name hoặc trả kết quả UNKNOWN để application service reconciliation.
- Không retry create khi chưa xác định call trước đã thành công hay chưa.

Ví dụ command:

~~~java
public record ProvisionResourceCommand(
        String serviceInstanceId,
        String serviceId,
        String planId,
        String tenantId,
        String idempotencyKey,
        ResourceProfile profile) {
}
~~~

Adapter có thể dùng idempotency key trong API request của provider, đồng thời gắn serviceInstanceId vào tag hoặc metadata để tra cứu khi broker mất response.

Idempotency nên được thực thi ở nhiều lớp: database broker, operation worker và provider adapter. Chỉ có key trong interface mà provider không hỗ trợ hoặc adapter không sử dụng thì chưa đủ.

## 9. Chuẩn hóa trạng thái operation bất đồng bộ

Provider có thể trả các trạng thái khác nhau:

- Provider A: PENDING, RUNNING, AVAILABLE, ERROR.
- Provider B: Accepted, Reconciling, Ready, Failed.
- Provider C: task ID và kết quả chỉ có sau khi polling.

Adapter chuyển chúng thành mô hình trạng thái chung mà application service hiểu:

| Trạng thái chung | Ý nghĩa |
|---|---|
| ACCEPTED | Provider đã nhận thao tác |
| IN_PROGRESS | Tác vụ vẫn đang chạy |
| SUCCEEDED | Tác vụ đã hoàn tất theo tiêu chí provider |
| FAILED | Provider xác nhận thao tác thất bại |
| UNKNOWN | Chưa thể xác định kết quả |

UNKNOWN rất quan trọng. Timeout hoặc mất kết nối không đồng nghĩa thao tác thất bại. Adapter không nên chuyển mọi exception thành FAILED nếu provider có thể đã thực hiện tác dụng phụ.

Khi provider có operation ID, adapter lưu hoặc trả ProviderOperationReference để worker gọi getOperation. Nếu provider không có operation endpoint, adapter có thể kiểm tra resource state hoặc sử dụng callback/watch mechanism phù hợp.

OSB operation ID vẫn do broker quản lý. Adapter không nên để platform phụ thuộc trực tiếp vào mã task của provider.

## 10. Chuẩn hóa lỗi provider

Mỗi provider có HTTP status, exception class và error code khác nhau. Application service cần một taxonomy chung để quyết định retry, từ chối hay yêu cầu operator.

Ví dụ các loại lỗi:

~~~java
public enum ProviderFailureKind {
    VALIDATION,
    NOT_FOUND,
    CONFLICT,
    QUOTA_EXCEEDED,
    AUTHENTICATION,
    AUTHORIZATION,
    RATE_LIMITED,
    TEMPORARY_UNAVAILABLE,
    TIMEOUT_UNKNOWN,
    UNSUPPORTED,
    INTERNAL
}
~~~

Một exception chuẩn hóa có thể chứa:

~~~java
public class ProviderException extends RuntimeException {

    private final ProviderFailureKind kind;
    private final String providerCode;
    private final boolean retryable;

    public ProviderException(
            ProviderFailureKind kind,
            String providerCode,
            boolean retryable,
            String safeMessage,
            Throwable cause) {
        super(safeMessage, cause);
        this.kind = kind;
        this.providerCode = providerCode;
        this.retryable = retryable;
    }

    public ProviderFailureKind kind() {
        return kind;
    }

    public String providerCode() {
        return providerCode;
    }

    public boolean retryable() {
        return retryable;
    }
}
~~~

Adapter chịu trách nhiệm chuyển lỗi kỹ thuật của provider thành loại lỗi chung. Application service quyết định chính sách retry và state transition. OSB handler ánh xạ lỗi nghiệp vụ thành response theo hợp đồng OSB.

Ví dụ:

| Lỗi provider | Lỗi chuẩn hóa | Hành vi gợi ý |
|---|---|---|
| HTTP 400 do tham số không hợp lệ | VALIDATION | Không retry |
| HTTP 404 khi tra cứu resource | NOT_FOUND | Kiểm tra mapping và state |
| HTTP 409 do resource đã tồn tại | CONFLICT | Lookup và đối chiếu idempotency |
| HTTP 429 | RATE_LIMITED | Retry theo Retry-After/backoff |
| HTTP 503 | TEMPORARY_UNAVAILABLE | Retry có giới hạn |
| Timeout sau khi gửi create | TIMEOUT_UNKNOWN | Reconcile trước khi tạo lại |
| HTTP 401/403 | AUTHENTICATION/AUTHORIZATION | Dừng retry tự động, cảnh báo |
| API không hỗ trợ update | UNSUPPORTED | Từ chối theo capability |

Không đưa raw response body, credential hoặc endpoint nội bộ nhạy cảm vào message trả platform. Có thể lưu provider error code đã chuẩn hóa và correlation ID để điều tra.

## 11. Quản lý cấu hình và secret của từng provider

Adapter thường cần endpoint, account, project, region, credential hoặc client certificate. Những giá trị này nên được quản lý ngoài code và tách theo provider profile.

Ví dụ cấu hình không chứa secret:

~~~yaml
broker:
  providers:
    cloud-postgres:
      base-url: https://api.provider-a.example
      account: development-account
      region: ap-southeast-1
      credential-reference: secret://broker/provider-a/dev
    kubernetes-redis:
      cluster: cluster-main
      namespace: service-broker
      credential-reference: secret://broker/kubernetes/main
~~~

credential-reference là tham chiếu tới secret manager, không phải URI chuẩn. Ứng dụng phải dùng integration phù hợp để lấy credential khi cần.

Không nên:

- Commit API key hoặc password vào Git.
- Ghi credential vào log khi khởi tạo adapter.
- Truyền secret qua command hoặc event payload nếu chỉ cần secret reference.
- Cho request OSB chỉ định tùy ý provider account hoặc cluster.
- Dùng một credential có quyền quản trị toàn bộ cloud nếu adapter chỉ cần quyền tạo một loại resource.

Nên cấp quyền tối thiểu cho mỗi adapter và tách account theo môi trường hoặc tenant khi chính sách yêu cầu.

## 12. Versioning của adapter contract

Provider adapter contract là API nội bộ của broker. Khi thêm field hoặc thay đổi semantics, cần xem xét ảnh hưởng tới mọi adapter hiện có.

Một số nguyên tắc:

- Thêm trường tùy chọn khi có thể duy trì tương thích.
- Không đổi ý nghĩa của một field đang được adapter sử dụng.
- Dùng kiểu command/result riêng cho operation có semantics khác nhau.
- Đánh dấu capability rõ ràng thay vì suy đoán qua việc method có tồn tại.
- Khi phải thay đổi breaking, nâng phiên bản contract và cập nhật tất cả adapter trong một release có kiểm soát.
- Kiểm thử các adapter cũ với application service mới trước khi phát hành.

Không nên tạo một interface khổng lồ chứa hàng chục method nullable chỉ để mọi provider implement cùng một contract. Nếu provider không hỗ trợ volume mount, không nên trả list rỗng rồi để application service đoán liệu đó là không hỗ trợ hay hiện không có volume. Capability cần thể hiện rõ.

## 13. Adapter registry và dependency injection trong Spring

Spring có thể quản lý nhiều adapter implementation như các bean. Registry xây dựng map theo provider key:

~~~java
@Component
public class ProviderAdapterRegistry {

    private final Map<ProviderKey, ProviderAdapter> adapters;

    public ProviderAdapterRegistry(List<ProviderAdapter> candidates) {
        this.adapters = candidates.stream()
                .collect(Collectors.toUnmodifiableMap(
                        ProviderAdapter::key,
                        Function.identity()));
    }

    public ProviderAdapter require(ProviderKey key) {
        ProviderAdapter adapter = adapters.get(key);
        if (adapter == null) {
            throw new IllegalStateException(
                    "No provider adapter configured for " + key.value());
        }
        return adapter;
    }
}
~~~

Ví dụ implementation:

~~~java
@Component
public class CloudPostgresAdapter implements ProviderAdapter {

    @Override
    public ProviderKey key() {
        return new ProviderKey("cloud-postgres");
    }

    @Override
    public ProviderCapabilities capabilities() {
        return new ProviderCapabilities(
                true, true, true, true,
                true, false, false, true);
    }

    // Các method provision, update, bind và deprovision
    // gọi client riêng của Provider A.
}
~~~

Đây là cấu trúc minh họa; các method còn lại cần implement theo contract thực tế. Nếu có hai bean cùng provider key, registry nên fail fast thay vì để kết quả phụ thuộc thứ tự injection.

Application service có thể nhận ProviderAdapterResolver hoặc Registry. Không nên inject trực tiếp mọi SDK provider vào service nghiệp vụ.

## 14. Ánh xạ service plan sang provider resource profile

Service plan mô tả lựa chọn sản phẩm mà platform nhìn thấy. Provider resource profile mô tả cách lựa chọn đó được thực thi trên provider.

Ví dụ cùng plan production:

| Thuộc tính plan | Provider A | Kubernetes Provider B |
|---|---|---|
| CPU | Instance class db-optimized-2 | CPU request/limit |
| Memory | Memory tier 8 GiB | Memory request/limit 8 GiB |
| Storage | Managed storage 200 GiB | PVC 200 GiB |
| Backup | Retention 14 ngày | Snapshot policy 14 ngày |
| Connections | Parameter group | Database config/connection pool |

Adapter chuyển profile chung sang cấu hình provider cụ thể. Không nên để provider-specific field xuất hiện trong catalog nếu người dùng không cần lựa chọn chúng.

Nếu hai provider không có khả năng tương đương, broker cần quyết định có nên công bố cùng plan hay tách thành plan/service riêng. Không nên gọi hai cấu hình hoàn toàn khác nhau bằng cùng tên production nếu SLA, dung lượng hoặc hành vi khác biệt đáng kể.

## 15. Retry, timeout và rate limiting trong adapter

Adapter là ranh giới tự nhiên để áp dụng các chính sách giao tiếp provider:

- Connection timeout và response timeout.
- Retry cho lỗi tạm thời.
- Exponential backoff và jitter.
- Tôn trọng Retry-After khi provider giới hạn tốc độ.
- Circuit breaker khi provider liên tục lỗi.
- Bulkhead để một provider chậm không làm cạn toàn bộ worker.
- Giới hạn concurrency theo account hoặc region.

Tuy nhiên, retry policy không nên được cài đặt tùy tiện trong mọi method adapter. Cần phân biệt request đọc an toàn với request tạo/xóa có tác dụng phụ.

Ví dụ:

| Thao tác | Retry có điều kiện |
|---|---|
| GET resource | Thường có thể retry lỗi tạm thời |
| GET operation | Có thể retry với backoff |
| POST create | Chỉ retry an toàn khi có idempotency hoặc lookup |
| PATCH update | Phụ thuộc semantics và version/concurrency |
| DELETE resource | Cần bảo đảm idempotent hoặc xử lý NOT_FOUND phù hợp |
| Bind tạo credential | Cần idempotency theo binding ID |
| Unbind | Cần xác định kết quả khi provider đã thu hồi trước timeout |

Timeout sau một lệnh tạo tài nguyên nên tạo kết quả UNKNOWN nếu không thể xác định provider đã xử lý hay chưa. Application service có thể lên lịch reconciliation thay vì retry mù quáng.

## 16. Quan sát và correlation xuyên qua các lớp

Khi một provision thất bại, người vận hành cần nối được request OSB với operation, adapter và request provider.

Nên truyền correlation metadata xuyên suốt:

- service_instance_id.
- broker operation_id.
- provider key.
- provider account/region.
- provider operation ID.
- request correlation ID.
- attempt number.

Không đưa secret hoặc dữ liệu parameters nhạy cảm vào metric label. Log nên ghi provider error code, thời gian gọi, kết quả và correlation ID đã chuẩn hóa.

Các metric hữu ích:

- Request count và latency theo provider/operation.
- Số lỗi theo failure kind.
- Số timeout UNKNOWN.
- Retry count và rate-limit count.
- Số operation đang chạy theo provider.
- Thời gian provider hoàn tất provision/update/deprovision.
- Số resource mapping không đối chiếu được.

Không nên dùng provider resource ID hoặc tenant ID làm label metric nếu số lượng giá trị có thể rất lớn. Những ID đó phù hợp hơn với log có kiểm soát truy cập hoặc trace attribute theo chính sách dữ liệu.

## 17. Kiểm thử contract chung cho mọi adapter

Một adapter mới phải đáp ứng cùng các quy tắc mà application service dựa vào. Có thể xây dựng bộ contract test dùng chung.

Ví dụ các nhóm kiểm thử:

| Nhóm | Điều cần xác minh |
|---|---|
| Provision | Trả resource reference hợp lệ hoặc operation reference |
| Idempotency | Lặp cùng key không tạo resource thứ hai |
| Update | Chỉ cập nhật resource đúng mapping và version |
| Deprovision | Retry không xóa nhầm resource khác |
| Binding | Binding ID gắn đúng instance và tenant |
| Unbind | Thu hồi đúng binding, không xóa instance gốc |
| Async operation | Operation state được chuẩn hóa |
| Error mapping | Provider error thành failure kind đúng |
| Capability | Khai báo khớp thao tác thực sự hỗ trợ |
| Security | Không log hoặc trả credential ngoài ý muốn |

Có thể định nghĩa abstract contract test để chạy với fake provider hoặc test fixture. Mỗi adapter có bộ integration test riêng trên sandbox của provider để xác minh API thực tế, quyền, network và hành vi retry.

Không nên chỉ mock mọi lời gọi provider rồi coi adapter đã được kiểm thử. Mock không phát hiện khác biệt về payload, pagination, eventual consistency hoặc mã lỗi của API thật.

## 18. Ví dụ luồng provision qua adapter

Giả sử platform gửi provision cho PostgreSQL production. Broker định tuyến plan tới cloud-postgres.

1. OSB handler chuyển request thành ProvisionCommand.
2. Application service xác thực tenant, quota và plan.
3. Provider resolver chọn CloudPostgresAdapter từ cấu hình.
4. Application service tạo operation và instance state.
5. Adapter nhận ProvisionResourceCommand cùng idempotency key.
6. Adapter gọi Provider A API.
7. Provider trả provider resource ID và operation ID.
8. Adapter chuẩn hóa kết quả thành ProvisionSubmission.
9. Application service lưu mapping và tiếp tục theo dõi operation.
10. Khi provider xác nhận database sẵn sàng, broker đánh dấu instance ACTIVE.
11. OSB layer trả trạng thái phù hợp cho platform.

~~~mermaid
sequenceDiagram
    participant P as Platform
    participant O as OSB Handler
    participant A as Application Service
    participant R as Adapter Resolver
    participant D as Provider Adapter
    participant V as Provider API
    participant DB as Broker Database
    P->>O: Provision request
    O->>A: ProvisionCommand
    A->>DB: Save instance and operation
    A->>R: Resolve(service, plan)
    R-->>A: CloudPostgresAdapter
    A->>D: ProvisionResourceCommand
    D->>V: Provider create request
    V-->>D: Resource ID + Provider operation ID
    D-->>A: ProvisionSubmission
    A->>DB: Save mapping and operation
    A-->>O: Accepted/completed result
    O-->>P: OSB response
~~~

Nếu provider là Kubernetes, application service vẫn gọi contract tương tự. Kubernetes adapter có thể tạo Custom Resource, lưu namespace/name/UID và theo dõi trạng thái Ready của operator. Khác biệt được giữ trong adapter.

## 19. Các lỗi thiết kế thường gặp

| Hiện tượng | Nguyên nhân | Hướng xử lý |
|---|---|---|
| Application service chứa nhiều if/else theo provider | Chưa có resolver hoặc adapter boundary | Đưa định tuyến và API-specific logic vào adapter |
| Interface có nhiều field Map không kiểm soát | Cố gắng mô hình hóa mọi provider bằng một payload chung | Dùng command/result typed và extension có schema |
| Adapter trả raw SDK response | Rò rỉ model provider vào application service | Map sang domain model trung lập |
| Provider không hỗ trợ update nhưng handler vẫn gọi | Không mô hình hóa capability | Kiểm tra capability trước thao tác |
| Timeout create bị retry và tạo duplicate | Thiếu idempotency hoặc reconciliation | Dùng key, tag và lookup |
| Mọi lỗi provider đều thành INTERNAL | Không có error taxonomy | Chuẩn hóa failure kind và retryability |
| Provider operation ID bị trả trực tiếp cho platform | Trộn ID nội bộ và OSB | Dùng broker operation ID riêng |
| Secret xuất hiện trong log | Adapter log toàn bộ request/response | Redact và log metadata an toàn |
| Thêm provider làm đổi catalog ngoài ý muốn | Catalog gắn trực tiếp vào SDK config | Tách catalog policy và provider routing |
| Unit test qua nhưng tích hợp lỗi | Chỉ mock provider | Bổ sung contract và sandbox integration test |

## 20. Quy trình thêm một provider mới

Có thể thực hiện theo trình tự:

1. Xác định backing service và các thao tác vòng đời broker cần hỗ trợ.
2. Lập capability matrix của provider.
3. Xác định provider account, region, credential và network requirements.
4. Thiết kế hoặc tái sử dụng command/result trung lập.
5. Implement adapter và chuyển đổi request/response của SDK.
6. Chuẩn hóa error mapping, operation state và resource reference.
7. Thêm cấu hình routing service/plan tới adapter.
8. Bổ sung idempotency, timeout, retry và rate limit.
9. Viết contract test và integration test với sandbox.
10. Kiểm tra catalog công bố capability đúng với platform mục tiêu.
11. Kiểm tra provision, update, bind, unbind và deprovision.
12. Bật provider theo từng môi trường và theo dõi metric trước khi mở rộng.

Không nên đưa provider mới vào production chỉ vì catalog có thể hiển thị plan. Cần kiểm thử cả vòng đời, phục hồi lỗi và quyền truy cập.

## 21. Checklist thiết kế provider adapter

- [ ] Contract adapter dùng domain model của broker, không phụ thuộc SDK provider.
- [ ] Trách nhiệm handler, application service, adapter và repository được phân tách.
- [ ] Có resolver chọn adapter theo service/plan từ cấu hình đáng tin cậy.
- [ ] Provider capability được khai báo rõ và kiểm tra trước khi gọi.
- [ ] Service plan được ánh xạ tới resource profile phù hợp.
- [ ] Resource ID, operation ID và binding ID được phân biệt.
- [ ] Idempotency key được giữ ổn định qua retry.
- [ ] Kết quả UNKNOWN được xử lý khi provider timeout không rõ kết quả.
- [ ] Provider operation được chuẩn hóa để worker theo dõi.
- [ ] Provider error được chuyển thành failure taxonomy chung.
- [ ] Retry, timeout, rate limit và circuit breaker có chính sách rõ.
- [ ] Secret lấy từ secret manager và không xuất hiện trong log.
- [ ] Adapter contract có versioning và kiểm thử tương thích.
- [ ] Có contract test chung và integration test riêng cho từng provider.
- [ ] Metric và correlation ID giúp truy vết request xuyên các lớp.

Provider adapter tạo ra ranh giới ổn định giữa service broker và hạ tầng cụ thể. OSB handler tiếp nhận hợp đồng của platform; application service quản lý quy tắc vòng đời và trạng thái; adapter chuyển command sang API provider rồi chuẩn hóa kết quả. Khi contract có capability rõ ràng, mapping bền vững, idempotency, error taxonomy và kiểm thử chung, broker có thể hỗ trợ nhiều nhà cung cấp mà không để khác biệt SDK lan vào logic nghiệp vụ.

