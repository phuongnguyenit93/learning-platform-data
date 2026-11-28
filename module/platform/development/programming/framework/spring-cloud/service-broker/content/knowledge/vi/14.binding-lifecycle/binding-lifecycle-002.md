# Cài đặt getServiceInstanceBinding() và trả dữ liệu liên kết được phép

Trong Open Service Broker API (OSB API), sau khi tạo service binding, platform có thể cần đọc lại thông tin liên kết đã được broker cấp. Ví dụ, platform khôi phục dữ liệu sau khi restart, đồng bộ lại cấu hình consumer hoặc kiểm tra credentials hiện hành. Broker hỗ trợ thao tác này qua endpoint **GET /v2/service_instances/{instance_id}/service_bindings/{binding_id}**.

Với Spring Cloud Open Service Broker (SCOSB), nghiệp vụ đọc binding được triển khai qua phương thức **getServiceInstanceBinding()** của **ServiceInstanceBindingService**. Phương thức tra cứu binding đã tồn tại, kiểm tra quyền truy cập và trả về đúng dữ liệu liên kết được phép công bố cho binding đó. Nó không tạo binding mới, không cấp credentials mới một cách ngẫu nhiên và không thu hồi quyền truy cập.

Bài học thuộc module **SPRING_CLOUD_SERVICE_BROKER**, tập trung vào hợp đồng GET binding, capability **bindings_retrievable**, request/response model của SCOSB, cách lưu và đọc credentials an toàn, phạm vi dữ liệu được trả về, xử lý binding không tồn tại và kiểm thử.

## 1. Khi nào platform cần đọc lại service binding?

Khi platform tạo binding, broker thường trả credentials hoặc thông tin kết nối để ứng dụng sử dụng service. Trong vòng đời vận hành, platform có thể cần lấy lại dữ liệu đó. Một số tình huống thường gặp:

- Platform khôi phục trạng thái sau khi restart hoặc phục hồi dữ liệu điều khiển.
- Một thành phần quản trị cần đồng bộ lại binding metadata đã được broker cấp.
- Platform cần xác minh binding hiện có trước khi tiếp tục một quy trình.
- Platform muốn lấy lại dữ liệu binding theo API thay vì dựa hoàn toàn vào bản response đã lưu từ lần bind trước.

OSB API định nghĩa endpoint:

~~~http
GET /v2/service_instances/{instance_id}/service_bindings/{binding_id}
~~~

Ví dụ:

~~~http
GET /v2/service_instances/instance-pg-100/service_bindings/binding-app-204
X-Broker-API-Version: 2.17
Authorization: Basic <broker-credentials>
~~~

Trong đó:

- **instance_id** xác định service instance mà binding thuộc về.
- **binding_id** xác định một binding cụ thể của instance đó.
- **GET** là thao tác đọc dữ liệu liên kết hiện có.
- Broker trả thông tin binding theo response contract của OSB API và capability mà broker công bố trong catalog.

Một service instance có thể có nhiều binding cho nhiều ứng dụng hoặc consumer khác nhau. Vì vậy, chỉ tra cứu bằng instance ID là chưa đủ. Broker cần xác định đúng cặp **instance_id + binding_id** và kiểm tra binding thuộc đúng tenant, consumer và service instance.

## 2. Phân biệt bindable và bindings_retrievable

Trong catalog OSB API, hai thuộc tính có ý nghĩa khác nhau:

| Thuộc tính | Ý nghĩa |
|---|---|
| **bindable** | Offering có hỗ trợ tạo service binding hay không |
| **bindings_retrievable** | Broker có hỗ trợ đọc lại một service binding bằng GET endpoint hay không |

Một service có thể hỗ trợ tạo binding nhưng không hỗ trợ truy xuất lại dữ liệu binding. Ví dụ, broker chỉ lưu hash của credential sau khi trả response lần đầu, không có cách lấy lại mật khẩu gốc và cũng không thể tái tạo an toàn. Khi đó, broker có thể đặt **bindable=true** nhưng **bindings_retrievable=false**.

Nếu broker triển khai đầy đủ khả năng GET binding, có thể công bố:

~~~json
{
  "services": [
    {
      "id": "svc-postgresql",
      "name": "postgresql",
      "description": "Managed PostgreSQL database",
      "bindable": true,
      "bindings_retrievable": true,
      "plans": [
        {
          "id": "plan-pg-standard",
          "name": "standard",
          "description": "Standard PostgreSQL database"
        }
      ]
    }
  ]
}
~~~

**bindings_retrievable** là capability ở cấp service offering. Nó thông báo cho platform rằng broker hỗ trợ endpoint GET binding đối với offering đó. Không nên bật cờ này nếu broker chưa thể truy xuất các trường dữ liệu mà response binding cần cung cấp.

### Khai báo trong Spring Cloud Open Service Broker

Trong model **ServiceDefinition**, có thể khai báo capability bằng builder tương ứng:

~~~java
import java.util.List;

import org.springframework.cloud.servicebroker.model.catalog.Catalog;
import org.springframework.cloud.servicebroker.model.catalog.Plan;
import org.springframework.cloud.servicebroker.model.catalog.ServiceDefinition;

Catalog catalog = Catalog.builder()
        .serviceDefinitions(List.of(
                ServiceDefinition.builder()
                        .id("svc-postgresql")
                        .name("postgresql")
                        .description("Managed PostgreSQL database")
                        .bindable(true)
                        .bindingsRetrievable(true)
                        .plans(List.of(
                                Plan.builder()
                                        .id("plan-pg-standard")
                                        .name("standard")
                                        .description("Standard PostgreSQL database")
                                        .build()
                        ))
                        .build()
        ))
        .build();
~~~

Tên builder và cách serialize field cần được xác minh theo phiên bản SCOSB đang dùng. Về mặt hợp đồng, **bindingsRetrievable(true)** tương ứng với capability **bindings_retrievable** trong catalog. Nếu chưa hỗ trợ GET binding, giữ giá trị false hoặc giá trị mặc định của model.

## 3. Request và response của getServiceInstanceBinding()

SCOSB cung cấp các model cho thao tác truy xuất binding:

- **GetServiceInstanceBindingRequest**: chứa định danh service instance và binding, cùng các thông tin service/plan/context mà framework có thể cung cấp.
- **GetServiceInstanceBindingResponse**: biểu diễn dữ liệu binding trả về platform, chẳng hạn credentials và các thuộc tính response được OSB API hỗ trợ.

Phương thức trong **ServiceInstanceBindingService** có dạng:

~~~java
Mono<GetServiceInstanceBindingResponse> getServiceInstanceBinding(
        GetServiceInstanceBindingRequest request);
~~~

Đây là phương thức reactive. Khi repository hoặc secret vault trả về publisher, có thể ghép các bước tra cứu và xây dựng response bằng Reactor mà không chặn thread.

Request thường cung cấp những thông tin quan trọng sau:

| Thông tin | Mục đích |
|---|---|
| service instance ID | Tìm instance sở hữu binding |
| binding ID | Tìm binding cần truy xuất |
| service definition | Xác định offering và capability liên quan nếu framework cung cấp |
| plan information | Xác định plan của instance |
| context/originating identity | Cung cấp ngữ cảnh platform hoặc caller khi có |

Tên accessor cụ thể có thể thay đổi giữa các phiên bản. Trong implementation, chỉ lấy những dữ liệu cần thiết từ request model; các thông tin về tenant và quyền phải được xác minh bằng ngữ cảnh xác thực đáng tin cậy.

Response có thể chứa các trường theo hợp đồng binding:

| Trường response | Mục đích |
|---|---|
| **credentials** | Thông tin xác thực dành riêng cho consumer của binding |
| **syslog_drain_url** | URL nhận log nếu service cung cấp khả năng syslog drain |
| **route_service_url** | URL đích nếu service cung cấp route service |
| **volume_mounts** | Danh sách volume mount nếu service hỗ trợ |
| **endpoints** | Metadata endpoint nếu phiên bản API và model đang dùng hỗ trợ |

Không phải binding nào cũng cần tất cả trường. Chỉ trả những trường mà service thực sự cung cấp và platform được phép nhận.

## 4. Phân biệt GET binding với create binding

GET binding là thao tác đọc lại kết quả của một binding đã tồn tại. Nó khác với create binding ở cả side effect lẫn trách nhiệm.

| Nội dung | Create binding | Get binding |
|---|---|---|
| Mục tiêu | Tạo quyền truy cập cho consumer | Đọc lại dữ liệu binding đã cấp |
| Tạo credential | Có thể tạo credential mới | Không tạo credential mới chỉ vì GET |
| Ghi dữ liệu | Tạo binding record và secret reference | Thông thường chỉ đọc |
| Provider call | Có thể gọi provider để tạo user/role | Không cần gọi provider nếu dữ liệu đã lưu đầy đủ |
| Response | Trả thông tin vừa tạo | Trả thông tin hiện hành của binding |
| Retry | Cần idempotency để tránh tạo credential trùng | Cần ổn định và không có side effect |
| Khi binding không tồn tại | Tạo mới nếu request hợp lệ | Trả lỗi not found theo hợp đồng |

Nếu mỗi lần GET lại tạo username/password mới, platform có thể nhận credentials khác với credentials mà consumer đang sử dụng. Điều đó gây lỗi kết nối và có thể làm lộ nhiều credential không cần thiết. Việc rotate credential phải là một nghiệp vụ riêng có kiểm soát; GET chỉ đọc phiên bản credential hiện hành được liên kết với binding.

## 5. Thiết kế dữ liệu binding để có thể truy xuất

Để hỗ trợ GET binding, broker phải lưu đủ thông tin để tái tạo response mà không phải suy đoán hoặc tạo credential mới. Một binding record có thể có cấu trúc:

| Trường | Ý nghĩa |
|---|---|
| binding_id | Định danh binding do platform gửi |
| instance_id | Service instance sở hữu binding |
| tenant_id | Tenant/organization sở hữu binding |
| service_id, plan_id | Offering và plan liên quan |
| consumer_id | Consumer/app được cấp quyền |
| state | Trạng thái binding, ví dụ ACTIVE hoặc REVOKING |
| credentials_secret_ref | Tham chiếu đến secret được lưu an toàn |
| syslog_drain_url | URL đã cấp nếu có |
| route_service_url | URL đã cấp nếu có |
| volume_mounts | Metadata volume mount nếu có |
| credential_version | Phiên bản credential hiện hành |
| created_at, updated_at | Thời điểm tạo và cập nhật |

Ví dụ mô hình Java nội bộ:

~~~java
import java.time.Instant;
import java.util.List;

public record BindingRecord(
        String bindingId,
        String instanceId,
        String tenantId,
        String serviceId,
        String planId,
        String consumerId,
        BindingState state,
        String credentialsSecretRef,
        String syslogDrainUrl,
        String routeServiceUrl,
        List<VolumeMountInfo> volumeMounts,
        long credentialVersion,
        Instant createdAt,
        Instant updatedAt
) {
}

public enum BindingState {
    ACTIVE,
    REVOKING,
    REVOKED,
    FAILED
}
~~~

Đây là mô hình nội bộ minh họa. Ứng dụng có thể lưu các trường trong nhiều bảng hoặc kết hợp database với secret manager. Điều quan trọng là mỗi binding phải có quan hệ rõ ràng với service instance, tenant và consumer.

### Không lưu credential plaintext trong bảng binding

Một thiết kế an toàn thường lưu credential trong secret manager hoặc một kho mã hóa, còn database chỉ lưu tham chiếu:

~~~text
binding record
  binding_id = binding-app-204
  instance_id = instance-pg-100
  tenant_id = org-42
  consumer_id = app-orders
  state = ACTIVE
  credentials_secret_ref = secret://broker/bindings/binding-app-204
  credential_version = 3

secret manager
  secret://broker/bindings/binding-app-204
    username = app_orders_204
    password = <encrypted secret>
    host = pg.internal.example
    port = 5432
    database = orders
~~~

Nếu broker chỉ lưu password hash thì không thể trả lại password gốc qua GET binding. Hash phù hợp cho xác minh password, nhưng không thể khôi phục secret. Vì vậy, nếu offering yêu cầu **bindings_retrievable=true** và response cần credentials, broker phải có thiết kế lưu trữ hoặc cơ chế tái tạo an toàn đáp ứng yêu cầu đó.

Không nên mã hóa secret bằng một khóa hard-code trong source code hoặc lưu khóa giải mã cạnh ciphertext trong cùng bảng. Dùng secret manager/KMS, phân quyền đọc tối thiểu, rotation và audit truy cập.

## 6. Cài đặt getServiceInstanceBinding() trong Spring

Nên tách phần tra cứu binding khỏi controller và khỏi logic tạo binding. Service đọc binding record, kiểm tra trạng thái và quyền, lấy credentials từ secret vault rồi chuyển thành response model.

Ví dụ repository:

~~~java
import reactor.core.publisher.Mono;

public interface BindingRepository {

    Mono<BindingRecord> findByInstanceIdAndBindingId(
            String instanceId,
            String bindingId);
}
~~~

Ví dụ secret vault:

~~~java
import java.util.Map;
import reactor.core.publisher.Mono;

public interface BindingSecretStore {

    Mono<Map<String, Object>> readCredentials(String secretReference);
}
~~~

Component xử lý lookup:

~~~java
import java.util.Map;

import org.springframework.stereotype.Service;

import org.springframework.cloud.servicebroker.model.binding.GetServiceInstanceBindingRequest;
import org.springframework.cloud.servicebroker.model.binding.GetServiceInstanceBindingResponse;

import reactor.core.publisher.Mono;

@Service
public class BindingLookupService {

    private final BindingRepository bindingRepository;
    private final BindingSecretStore secretStore;
    private final BindingAuthorizationService authorizationService;

    public BindingLookupService(
            BindingRepository bindingRepository,
            BindingSecretStore secretStore,
            BindingAuthorizationService authorizationService) {
        this.bindingRepository = bindingRepository;
        this.secretStore = secretStore;
        this.authorizationService = authorizationService;
    }

    public Mono<GetServiceInstanceBindingResponse> getServiceInstanceBinding(
            GetServiceInstanceBindingRequest request) {

        String instanceId = request.getServiceInstanceId();
        String bindingId = request.getBindingId();

        return authorizationService.authorizeRead(request)
                .then(bindingRepository.findByInstanceIdAndBindingId(
                        instanceId, bindingId))
                .filter(binding -> binding.state() == BindingState.ACTIVE)
                .switchIfEmpty(Mono.error(
                        new BindingNotFoundException(instanceId, bindingId)))
                .flatMap(binding -> secretStore
                        .readCredentials(binding.credentialsSecretRef())
                        .map(credentials -> toResponse(binding, credentials)));
    }

    private GetServiceInstanceBindingResponse toResponse(
            BindingRecord binding,
            Map<String, Object> credentials) {

        return GetServiceInstanceBindingResponse.builder()
                .credentials(credentials)
                .syslogDrainUrl(binding.syslogDrainUrl())
                .routeServiceUrl(binding.routeServiceUrl())
                .build();
    }
}
~~~

Đây là component minh họa phần tra cứu. Trong implementation đầy đủ, phương thức **getServiceInstanceBinding()** của class triển khai **ServiceInstanceBindingService** có thể ủy quyền cho component này; class adapter vẫn cần triển khai các phương thức lifecycle khác theo phiên bản SCOSB đang dùng.

Các builder method cho syslog drain URL, route service URL, volume mounts hoặc field mở rộng có thể khác theo version của model. Chỉ thêm các field mà phiên bản framework và OSB API đang dùng hỗ trợ.

### Phân tích luồng xử lý

1. Lấy instance ID và binding ID từ request model.
2. Xác thực quyền đọc binding trong ngữ cảnh platform/caller.
3. Truy vấn binding theo cả instance ID và binding ID.
4. Chỉ chấp nhận binding ở trạng thái có thể truy xuất, thường là ACTIVE.
5. Dùng secret reference đã lưu để đọc credentials hiện hành.
6. Xây dựng **GetServiceInstanceBindingResponse** với những trường được phép trả về.
7. Trả response mà không tạo hoặc thu hồi tài nguyên.

Truy vấn kết hợp hai ID ngăn trường hợp một binding thuộc instance A bị trả về khi platform gửi instance B. Trong môi trường multi-tenant, nên thêm tenant scope vào câu truy vấn hoặc đảm bảo authorization layer đã ràng buộc tenant trước khi đọc record.

## 7. Chỉ trả dữ liệu liên kết được phép

Không phải mọi dữ liệu mà broker lưu đều được phép trả cho platform. Response cần được xây dựng từ allowlist các trường thuộc hợp đồng binding.

Ví dụ credentials cho một ứng dụng PostgreSQL:

~~~json
{
  "credentials": {
    "username": "app_orders_204",
    "password": "<binding-specific-secret>",
    "host": "pg.internal.example",
    "port": 5432,
    "database": "orders",
    "sslmode": "require"
  }
}
~~~

Đây là credentials dành riêng cho binding **binding-app-204**. Không trả user quản trị database, password của binding khác, provider API token hoặc thông tin kết nối nội bộ không dành cho consumer.

Một response có thể bao gồm metadata bổ sung khi service hỗ trợ:

~~~json
{
  "credentials": {
    "username": "app_orders_204",
    "password": "<binding-specific-secret>",
    "host": "pg.internal.example",
    "port": 5432,
    "database": "orders"
  },
  "syslog_drain_url": "https://logs.example.internal/drain/orders",
  "route_service_url": "https://route.example.internal/orders"
}
~~~

Các trường URL trong ví dụ chỉ là dữ liệu minh họa. Chỉ trả **syslog_drain_url** hoặc **route_service_url** khi offering thực sự hỗ trợ chức năng đó và URL đã được kiểm tra theo chính sách của broker. Với volume service, chỉ trả các mount entry được cấp cho binding đó.

### Không trả toàn bộ binding record

Các trường sau thường là dữ liệu nội bộ và không nên đưa vào response:

- provider resource ID và provider account ID.
- tenant ID nội bộ nếu không thuộc hợp đồng response.
- secret reference hoặc đường dẫn secret manager.
- access token dùng để broker gọi provider.
- thông tin xác thực quản trị hoặc credential của consumer khác.
- trạng thái nội bộ, lock token, retry counter và stack trace.
- endpoint quản trị hoặc địa chỉ mạng không dành cho consumer.

Response DTO nên được tạo tường minh từ allowlist. Tránh serialize trực tiếp entity database hoặc object provider vì chúng có thể chứa field nội bộ mới được thêm trong tương lai.

## 8. Bảo đảm credentials nhất quán qua các lần GET

Platform có thể gọi GET binding nhiều lần. Với cùng một binding đang ACTIVE, broker phải có hành vi ổn định và có thể dự đoán.

Một số nguyên tắc:

- GET không tự sinh username/password mới.
- Credentials trả về phải là credential hiện hành được gắn với binding.
- Nếu credential đã được rotate qua một quy trình riêng, binding record phải trỏ đến phiên bản hiện hành.
- Không trả credential đã bị revoke.
- Không trả dữ liệu của binding khác dù cùng service instance.
- Nếu secret store tạm thời không truy cập được, trả lỗi server phù hợp; không thay bằng credentials rỗng hoặc secret giả.
- Không ghi response credentials vào log.

Nếu provider chỉ cho đọc credential một lần lúc tạo user, broker cần thiết kế từ trước cách lưu an toàn để hỗ trợ fetch. Có thể lưu ciphertext trong vault, hoặc dùng cơ chế credential có thể tái tạo một cách xác định và an toàn. Không thể dùng hash một chiều để phục hồi password.

Nếu hệ thống không thể cung cấp lại credentials một cách an toàn, không nên công bố **bindings_retrievable=true**. Capability phải phản ánh đúng khả năng thực tế của broker.

## 9. Xử lý binding không tồn tại hoặc không còn hoạt động

Các trường hợp cần phân biệt:

| Tình huống | Hướng xử lý |
|---|---|
| Service instance không tồn tại | Trả lỗi not found theo mapping OSB API |
| Binding ID không tồn tại trong instance | Trả lỗi not found |
| Binding tồn tại nhưng thuộc instance khác | Không trả dữ liệu binding đó |
| Binding đã REVOKED | Không trả credentials đã thu hồi |
| Binding đang REVOKING | Áp dụng chính sách nhất quán; thường không trả secret mới nếu quyền đã bị chặn |
| Secret reference không tồn tại | Ghi nhận lỗi dữ liệu/vault; không trả credentials rỗng như thể thành công |
| Secret manager tạm lỗi | Trả lỗi server có thể retry, không tạo binding mới |
| Caller không có quyền | Trả lỗi authorization phù hợp và không tiết lộ binding của tenant khác |

Không nên trả HTTP 200 với object credentials rỗng khi binding không tồn tại. Platform có thể hiểu nhầm rằng binding hợp lệ nhưng không cần credentials. Cần dùng exception mapping của SCOSB và OSB API version đang triển khai để trả status phù hợp.

Nếu không tìm thấy binding, cũng không nên tự động gọi create binding. GET là thao tác đọc. Tạo binding mới phải đi qua endpoint bind và quy trình xác thực riêng.

## 10. Kết hợp với vòng đời bind và unbind

GET binding chỉ có ý nghĩa khi broker quản lý được vòng đời binding.

~~~mermaid
stateDiagram-v2
    [*] --> CREATING: Bind request
    CREATING --> ACTIVE: Credentials stored and response ready
    CREATING --> FAILED: Provider bind failed
    ACTIVE --> ACTIVE: GET binding
    ACTIVE --> ROTATING: Credential rotation workflow
    ROTATING --> ACTIVE: New credential version committed
    ACTIVE --> REVOKING: Unbind request
    REVOKING --> REVOKED: Provider access revoked
    REVOKING --> FAILED: Revoke failed
    FAILED --> REVOKING: Retry/reconcile revoke
    REVOKED --> [*]
~~~

Khi bind thành công, broker nên lưu binding record và secret reference trước hoặc đồng bộ với thời điểm trả response để GET có thể đọc lại ngay sau đó. Nếu response bind trả credentials nhưng database chưa lưu secret, platform có thể nhận được credential mà broker không thể truy xuất lại.

Khi unbind:

1. Chuyển binding sang trạng thái REVOKING hoặc trạng thái tương đương.
2. Chặn các lần fetch credentials mới theo chính sách bảo mật.
3. Gọi provider để revoke user, role hoặc credential.
4. Xác nhận credential không còn hiệu lực.
5. Xóa hoặc đánh dấu secret không còn sử dụng theo chính sách retention.
6. Đánh dấu binding REVOKED và hoàn tất operation.

Sau khi unbind hoàn tất, GET binding không được trả lại credentials đã bị revoke. Cần xử lý race condition giữa GET và unbind: ví dụ một request GET bắt đầu trước khi unbind nhưng secret được đọc sau khi credential đã bị thu hồi. Có thể dùng version/state check, transaction hoặc kiểm tra lại trạng thái ngay trước khi tạo response để tránh trả secret cũ sau khi quyền truy cập đã bị chặn.

## 11. Bảo mật và phân quyền

Credentials là dữ liệu nhạy cảm. Endpoint GET binding cần được bảo vệ như endpoint cấp credential, không phải một endpoint đọc metadata công khai.

Các biện pháp nên có:

- Xác thực platform bằng cơ chế broker đã cấu hình.
- Kiểm tra quyền truy cập service instance và binding theo tenant/consumer.
- Tra cứu binding bằng instance ID, binding ID và tenant scope.
- Chỉ trả credentials thuộc đúng binding.
- Dùng secret manager hoặc mã hóa mạnh khi lưu credential.
- Giới hạn quyền đọc secret cho service identity của broker.
- Audit việc đọc secret nhưng không ghi secret vào audit log.
- Không đưa password, token, private key hoặc secret reference vào description và log.
- Giới hạn tốc độ truy xuất để tránh dò binding ID.
- Dùng TLS cho kết nối giữa platform và broker.
- Không tiết lộ sự tồn tại của binding thuộc tenant khác qua thông báo lỗi quá chi tiết.

Nếu một binding được cấp cho app A, app B không được đọc credentials của app A chỉ vì cùng chia sẻ một service instance. Binding ID không phải bằng chứng ủy quyền. Broker cần ràng buộc record với consumer và xác minh caller theo ngữ cảnh đã xác thực.

## 12. Kiểm thử getServiceInstanceBinding()

Nên kiểm thử cả component lookup và HTTP endpoint. Các test cần chứng minh broker trả đúng dữ liệu, không lộ secret của binding khác và không tạo side effect.

Ví dụ unit test với JUnit, Mockito và StepVerifier:

~~~java
import static org.mockito.Mockito.when;

import java.util.Map;

import org.junit.jupiter.api.Test;
import org.mockito.Mockito;

import org.springframework.cloud.servicebroker.model.binding.GetServiceInstanceBindingRequest;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class BindingLookupServiceTest {

    private final BindingRepository repository =
            Mockito.mock(BindingRepository.class);

    private final BindingSecretStore secretStore =
            Mockito.mock(BindingSecretStore.class);

    private final BindingAuthorizationService authorization =
            Mockito.mock(BindingAuthorizationService.class);

    private final BindingLookupService service =
            new BindingLookupService(repository, secretStore, authorization);

    @Test
    void returnsCredentialsForTheRequestedBinding() {
        var request = GetServiceInstanceBindingRequest.builder()
                .serviceInstanceId("instance-pg-100")
                .bindingId("binding-app-204")
                .build();

        var binding = TestBindings.active(
                "instance-pg-100",
                "binding-app-204",
                "secret://binding-app-204");

        when(authorization.authorizeRead(request))
                .thenReturn(Mono.empty());
        when(repository.findByInstanceIdAndBindingId(
                "instance-pg-100", "binding-app-204"))
                .thenReturn(Mono.just(binding));
        when(secretStore.readCredentials("secret://binding-app-204"))
                .thenReturn(Mono.just(Map.of(
                        "username", "app_orders_204",
                        "password", "test-secret",
                        "database", "orders"
                )));

        StepVerifier.create(service.getServiceInstanceBinding(request))
                .expectNextMatches(response ->
                        "app_orders_204".equals(
                                response.getCredentials().get("username")))
                .verifyComplete();
    }
}
~~~

Các factory **TestBindings.active()** và model repository là thành phần test giả định. Builder/accessor chính xác của SCOSB cần đối chiếu theo version dependency thực tế.

Bộ test nên bổ sung:

| Ca kiểm thử | Kết quả mong đợi |
|---|---|
| Binding ACTIVE và secret có trong vault | Trả đúng credentials của binding |
| Binding ID không tồn tại | Trả lỗi not found |
| Instance ID không khớp binding | Không trả dữ liệu |
| Caller không có quyền | Từ chối truy cập trước khi đọc secret |
| Binding REVOKED | Không trả credentials |
| Binding đang REVOKING | Áp dụng chính sách chặn fetch đã định |
| Secret store timeout | Trả lỗi server phù hợp, không trả credentials giả |
| Secret reference bị thiếu | Ghi nhận lỗi dữ liệu, không trả object rỗng |
| Gọi GET nhiều lần | Không tạo credential mới và không gọi provider bind |
| Hai binding cùng instance | Mỗi binding chỉ nhận credentials của chính nó |
| Credential đã rotate | Trả phiên bản hiện hành theo binding record |
| GET chạy đồng thời với unbind | Không trả credential sau khi quyền đã bị revoke |
| Response serialization | Không có provider ID, secret reference hoặc field nội bộ |

HTTP integration test nên gọi trực tiếp endpoint GET binding qua controller SCOSB, xác minh path, status, response JSON, capability catalog và exception mapping. Một test quan trọng là kiểm tra service offering chỉ công bố **bindings_retrievable=true** khi GET binding thực sự hoạt động.

## 13. Lỗi thường gặp khi triển khai

**Bật bindings_retrievable nhưng chỉ lưu password hash.** Hash không thể khôi phục credential để trả lại. Cần thiết kế secret storage trước khi công bố capability.

**Tra cứu chỉ bằng binding_id.** Một binding có thể bị truy xuất nhầm qua instance khác. Dùng truy vấn theo cả instance ID và binding ID, thêm tenant scope.

**Tạo credential mới trong GET.** Platform có thể nhận một password không khớp với credential consumer đang dùng. GET phải trả dữ liệu hiện hành của binding.

**Serialize trực tiếp entity database.** Response có thể làm lộ tenant ID, provider resource ID hoặc secret reference. Dùng response DTO và allowlist field.

**Trả credentials của service instance thay vì binding.** Một instance có nhiều consumer; mỗi binding cần credential và quyền riêng. Không dùng một credential quản trị chung cho tất cả ứng dụng.

**Không phối hợp GET với unbind.** GET có thể trả secret đã bị thu hồi hoặc sắp thu hồi. Cần state check và xử lý race condition.

**Trả HTTP 200 với credentials rỗng khi không tìm thấy.** Platform có thể hiểu nhầm binding còn hợp lệ. Hãy trả lỗi phù hợp với OSB API.

**Ghi credentials vào log để debug.** Log thường có phạm vi truy cập rộng và retention dài. Chỉ log binding ID, correlation ID, kết quả và mã lỗi đã chuẩn hóa.

## 14. Quy trình triển khai thực tế

Khi bổ sung khả năng truy xuất binding, có thể triển khai theo trình tự:

1. Xác định service offering có cần hỗ trợ GET binding hay không.
2. Chỉ bật **bindings_retrievable** khi broker có thể trả dữ liệu binding hiện hành.
3. Thiết kế binding record với quan hệ instance, tenant, consumer và secret reference.
4. Chọn secret manager hoặc cơ chế mã hóa đáp ứng khả năng khôi phục credentials.
5. Xây dựng repository truy vấn theo instance ID và binding ID.
6. Xây dựng authorization check trước khi đọc secret.
7. Implement **getServiceInstanceBinding()** trong **ServiceInstanceBindingService** hoặc ủy quyền cho lookup component.
8. Tạo response từ allowlist các trường credentials và metadata được phép.
9. Đồng bộ fetch với trạng thái rotate/unbind và chính sách retention.
10. Kiểm thử unit, HTTP integration, authorization, secret handling và race condition.
11. Xác minh platform đích hỗ trợ capability và phiên bản OSB API đang công bố.

## Kết luận

**getServiceInstanceBinding()** cho phép platform đọc lại dữ liệu của một binding đã tồn tại qua endpoint **GET /v2/service_instances/{instance_id}/service_bindings/{binding_id}**. Trong Spring Cloud Open Service Broker, triển khai phương thức này qua **ServiceInstanceBindingService**, truy vấn đúng binding theo instance ID và binding ID, kiểm tra quyền, đọc credentials từ kho bí mật và xây dựng response chỉ gồm các trường được phép. Capability **bindings_retrievable** trong catalog phải phản ánh đúng khả năng lưu và khôi phục dữ liệu của broker. Khi GET không tạo side effect, credentials được bảo vệ và trạng thái binding được đồng bộ với rotate/unbind, platform có thể khôi phục thông tin liên kết mà không làm sai lệch quyền truy cập của consumer.

## Tài liệu tham khảo

- [Open Service Broker API Specification](https://github.com/openservicebrokerapi/servicebroker/blob/master/spec.md) — GET service binding, bindings_retrievable và response binding.
- [Spring Cloud Open Service Broker Reference Documentation](https://docs.spring.io/spring-cloud-open-service-broker/docs/current/reference/) — ServiceInstanceBindingService và request/response model.
- [Spring Cloud Open Service Broker — ServiceInstanceBindingService API](https://docs.spring.io/spring-cloud-open-service-broker/docs/current/apidocs/org/springframework/cloud/servicebroker/service/ServiceInstanceBindingService.html) — contract xử lý vòng đời binding.
- [Spring Cloud Open Service Broker — GetServiceInstanceBindingResponse API](https://docs.spring.io/spring-cloud-open-service-broker/docs/current/apidocs/org/springframework/cloud/servicebroker/model/binding/GetServiceInstanceBindingResponse.html) — model response khi truy xuất binding.
- [OWASP Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html) — lưu trữ, truy cập, rotation và audit secret.

