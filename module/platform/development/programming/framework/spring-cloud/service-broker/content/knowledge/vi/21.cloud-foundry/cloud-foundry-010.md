# Đăng ký một broker với nhiều foundation bằng platformInstanceId

Trong module **SPRING_CLOUD_SERVICE_BROKER**, một tổ chức có thể vận hành nhiều Cloud Foundry foundation, chẳng hạn development, staging và production, nhưng muốn dùng chung một dịch vụ Spring Cloud Service Broker. Mỗi foundation đăng ký broker với cùng endpoint, cùng catalog offering và plan, trong khi các service instance được tạo ở từng foundation phải được quản lý độc lập.

Thách thức xuất hiện khi mỗi foundation gửi các request OSB API tới cùng một broker. Các foundation có thể tạo ra những service instance ID hoặc binding ID giống nhau về mặt giá trị, nhưng chúng thuộc các platform khác nhau. Nếu broker chỉ dùng instance ID làm khóa toàn cục, dữ liệu và thao tác giữa các foundation có thể va chạm. Một request deprovision từ foundation A thậm chí có nguy cơ tác động nhầm tài nguyên được tạo bởi foundation B nếu broker không xác định đúng nguồn.

Open Service Broker API cung cấp query parameter **platformInstanceId** để phân biệt các platform instance khi một broker được đăng ký với nhiều platform instance. Broker cần dùng giá trị này như một phần của namespace định danh, kết hợp với instance ID, binding ID và operation ID. Bài học này trình bày cách đăng ký broker dùng chung trên nhiều Cloud Foundry foundation, cách tiếp nhận platformInstanceId, tổ chức persistence và idempotency, bảo vệ ranh giới tin cậy và vận hành an toàn.

## 1. Mô hình một broker dùng chung nhiều foundation

Giả sử một tổ chức có ba Cloud Foundry foundation:

- **cf-dev:** môi trường phát triển.
- **cf-staging:** môi trường kiểm thử trước phát hành.
- **cf-prod:** môi trường production.

Cả ba foundation đăng ký cùng một broker endpoint, ví dụ service broker chạy tại một URL nội bộ. Broker công bố một catalog PostgreSQL và các plan small, standard, enterprise. Người dùng ở mỗi foundation có thể provision service instance theo quyền của foundation đó.

~~~mermaid
flowchart TD
    A["Cloud Foundry foundation DEV"] -->|OSB API + platformInstanceId DEV| B["Shared Spring Cloud Service Broker"]
    C["Cloud Foundry foundation STAGING"] -->|OSB API + platformInstanceId STAGING| B
    D["Cloud Foundry foundation PROD"] -->|OSB API + platformInstanceId PROD| B
    B --> E["Platform namespace / instance registry"]
    E --> F["Provider adapters"]
    F --> G["Cloud database / Kubernetes / infrastructure"]
~~~

Broker có một deployment hoặc một cụm deployment dùng chung, nhưng nhận diện mỗi foundation như một platform namespace riêng. Các foundation có thể dùng cùng service offering ID và plan ID vì chúng đang tiêu thụ cùng catalog. Tuy nhiên, instance và binding được tạo từ những foundation khác nhau phải được lưu trong phạm vi platformInstanceId tương ứng.

Cần phân biệt hai khái niệm:

- **Một broker endpoint:** địa chỉ HTTP mà nhiều foundation gọi tới.
- **Nhiều platform instances:** các foundation riêng biệt cùng sử dụng endpoint đó.

Dùng chung endpoint không có nghĩa dùng chung dữ liệu tenant, service instance, binding hoặc quyền truy cập. Broker phải cô lập các resource theo foundation và theo tenant bên trong foundation.

## 2. platformInstanceId là gì?

**platformInstanceId** là một định danh do platform gửi trong query string của request OSB API để broker biết request đến từ platform instance nào. Khi broker được đăng ký với nhiều foundation, giá trị này giúp phân biệt các foundation đang gọi chung một endpoint.

Ví dụ minh họa:

~~~http
PUT /v2/service_instances/instance-7f3a?platformInstanceId=cf-foundation-dev
X-Broker-API-Version: 2.17
Content-Type: application/json
~~~

Cùng một instance ID có thể xuất hiện trong request từ foundation khác:

~~~http
PUT /v2/service_instances/instance-7f3a?platformInstanceId=cf-foundation-prod
X-Broker-API-Version: 2.17
Content-Type: application/json
~~~

Hai request này thuộc hai namespace platform khác nhau. Broker không được coi chúng là cùng một service instance chỉ vì path chứa cùng instance ID.

Một số nguyên tắc:

- Xem platformInstanceId là giá trị opaque do platform cung cấp; không tự phân tích theo quy tắc tên foundation nếu contract không quy định.
- Lưu giá trị chính xác sau khi validate độ dài và định dạng cho phép.
- Không dùng platformInstanceId thay cho service instance ID, binding ID hoặc tenant ID.
- Không coi platformInstanceId tự nó là credential hoặc bằng chứng authorization.
- Giữ giá trị ổn định theo vòng đời platform instance; nếu thay đổi, cần có kế hoạch migration và mapping.
- Nếu broker dùng chung nhiều foundation, không được bỏ qua parameter rồi gộp tất cả resource vào một namespace toàn cục.

Giá trị thực tế được Cloud Foundry gửi phụ thuộc phiên bản và cấu hình platform. Broker cần xác minh behavior của từng foundation đang tích hợp và tuân theo phiên bản OSB API mà platform hỗ trợ.

## 3. platformInstanceId khác context và tenant ID

Ba loại định danh thường bị nhầm:

| Giá trị | Đại diện cho | Ví dụ |
|---|---|---|
| **platformInstanceId** | Một platform instance/foundation | cf-foundation-prod |
| **tenant_id** | Khách hàng hoặc phạm vi sở hữu bên trong platform | tenant-payments |
| **service_instance_id** | Một service instance do platform định danh | instance-7f3a |

Một foundation có thể chứa nhiều organization, space hoặc tenant. Một tenant có thể có nhiều service instance. Vì vậy, platformInstanceId chỉ tạo namespace ở cấp platform; nó không thay thế tenant scoping.

Context trong body request có thể chứa organization GUID, space GUID hoặc metadata khác. Broker cần dùng platform adapter để xác thực và chuẩn hóa context, sau đó resolve tenant. Không lấy tenant ID từ platformInstanceId hoặc suy luận tenant từ chuỗi tên foundation.

Một mô hình nội bộ:

~~~text
platformInstanceId
    └── tenant_id
          └── service_instance_id
                └── binding_id
                      └── provider credential/resource
~~~

Khi xử lý request, broker nên kiểm tra cả platform namespace lẫn tenant ownership. Request có platformInstanceId hợp lệ nhưng context tenant không khớp owner của instance vẫn phải bị từ chối.

## 4. Đăng ký broker trên từng Cloud Foundry foundation

Mỗi foundation quản lý broker registration của riêng nó. Với Cloud Foundry CLI, administrator đăng nhập vào foundation đích rồi đăng ký cùng broker endpoint trong foundation đó.

Ví dụ minh họa:

~~~bash
cf api https://api.cf-dev.example.invalid
cf login
cf create-service-broker shared-postgres-broker BROKER_USERNAME BROKER_PASSWORD https://broker.example.invalid
cf enable-service-access postgresql
~~~

Thực hiện quy trình đăng ký tương tự trên foundation staging và production:

~~~bash
cf api https://api.cf-staging.example.invalid
cf login
cf create-service-broker shared-postgres-broker BROKER_USERNAME BROKER_PASSWORD https://broker.example.invalid
cf enable-service-access postgresql

cf api https://api.cf-prod.example.invalid
cf login
cf create-service-broker shared-postgres-broker BROKER_USERNAME BROKER_PASSWORD https://broker.example.invalid
cf enable-service-access postgresql
~~~

Các URL, broker name, credential và service access trong ví dụ là minh họa. Trong triển khai thật, administrator cần dùng endpoint API và tên foundation thực tế, secret được quản lý an toàn, cùng quyền service access phù hợp.

Mỗi foundation có bản ghi registration riêng, dù URL broker giống nhau. Platform gọi endpoint catalog để lấy danh sách offering/plan và gọi các endpoint lifecycle khi người dùng provision, update, bind hoặc deprovision.

### 4.1. Cùng catalog hay catalog riêng?

Nếu các foundation dùng chung một sản phẩm, broker thường công bố cùng service ID, plan ID, schema và capability cho tất cả. Mỗi foundation có thể áp dụng service access hoặc entitlement riêng ở phía Cloud Foundry.

Nếu catalog hoặc capability khác nhau đáng kể theo foundation, cần xác định rõ broker có thể biểu diễn sự khác biệt đó theo contract và phiên bản platform hay không. Không nên thay đổi cùng một service ID theo cách khiến foundation đang cache catalog hiểu sai semantics. Nếu cần các catalog độc lập hoàn toàn, có thể cần broker endpoint hoặc deployment/configuration riêng thay vì cố gộp mọi khác biệt vào một broker dùng chung.

## 5. Request OSB API mang platformInstanceId

Khi platform hỗ trợ cơ chế multi-platform identification, broker nhận platformInstanceId trong query string của các request service lifecycle tương ứng.

Ví dụ provision:

~~~http
PUT /v2/service_instances/instance-7f3a?platformInstanceId=cf-foundation-dev&accepts_incomplete=true
X-Broker-API-Version: 2.17
Content-Type: application/json
~~~

Ví dụ create binding:

~~~http
PUT /v2/service_instances/instance-7f3a/service_bindings/binding-billing?platformInstanceId=cf-foundation-dev
X-Broker-API-Version: 2.17
Content-Type: application/json
~~~

Ví dụ update:

~~~http
PATCH /v2/service_instances/instance-7f3a?platformInstanceId=cf-foundation-dev
X-Broker-API-Version: 2.17
Content-Type: application/json
~~~

Ví dụ deprovision:

~~~http
DELETE /v2/service_instances/instance-7f3a?platformInstanceId=cf-foundation-dev&accepts_incomplete=true
X-Broker-API-Version: 2.17
~~~

Ví dụ last operation:

~~~http
GET /v2/service_instances/instance-7f3a/last_operation?platformInstanceId=cf-foundation-dev&operation=op-123
X-Broker-API-Version: 2.17
~~~

Các query parameter và endpoint cụ thể phải tuân theo phiên bản OSB API mà foundation gửi. Broker không nên giả định platformInstanceId luôn xuất hiện trên mọi request trong mọi phiên bản. Hãy xác minh request thực tế và contract của phiên bản được hỗ trợ, đồng thời xử lý rõ trường hợp thiếu parameter khi multi-foundation mode đang bật.

Catalog là metadata mô tả offering và plan, thường được dùng chung. Không đưa dữ liệu instance hoặc tenant vào catalog chỉ để phân biệt foundation. Với endpoint catalog, hãy tuân theo contract OSB API/platform tương ứng; không tự yêu cầu platformInstanceId nếu endpoint và phiên bản không quy định.

## 6. Tạo namespace composite cho resource identity

Trong mô hình một foundation, broker có thể dùng instance ID làm khóa chính. Khi nhiều foundation cùng gọi một broker, nên chuyển sang khóa composite.

Một số khóa gợi ý:

| Entity | Khóa nghiệp vụ |
|---|---|
| Service instance | platform_instance_id + instance_id |
| Service binding | platform_instance_id + instance_id + binding_id |
| Async operation | platform_instance_id + operation_id |
| Request idempotency | platform_instance_id + resource identity + operation type |
| Tenant mapping | platform_instance_id + platform tenant reference |
| Provider resource mapping | provider account + external resource key |

Ví dụ, hai foundation tạo instance cùng có ID instance-7f3a:

| platform_instance_id | instance_id | tenant_id | provider_resource_id |
|---|---|---|---|
| cf-foundation-dev | instance-7f3a | tenant-dev | pg-dev-991 |
| cf-foundation-prod | instance-7f3a | tenant-prod | pg-prod-441 |

Hai bản ghi hợp lệ vì platform namespace khác nhau. Nếu broker chỉ có unique constraint trên instance_id, request thứ hai sẽ bị xem nhầm là duplicate hoặc ghi đè tài nguyên thứ nhất.

### 6.1. Database schema minh họa

~~~sql
CREATE TABLE service_instance (
    platform_instance_id VARCHAR(128) NOT NULL,
    instance_id VARCHAR(128) NOT NULL,
    tenant_id VARCHAR(128) NOT NULL,
    service_id VARCHAR(128) NOT NULL,
    plan_id VARCHAR(128) NOT NULL,
    provider_resource_id VARCHAR(256),
    lifecycle_state VARCHAR(32) NOT NULL,
    version BIGINT NOT NULL DEFAULT 0,
    PRIMARY KEY (platform_instance_id, instance_id)
);

CREATE TABLE service_binding (
    platform_instance_id VARCHAR(128) NOT NULL,
    instance_id VARCHAR(128) NOT NULL,
    binding_id VARCHAR(128) NOT NULL,
    principal_id VARCHAR(256),
    credential_ref VARCHAR(512),
    status VARCHAR(32) NOT NULL,
    PRIMARY KEY (platform_instance_id, instance_id, binding_id),
    FOREIGN KEY (platform_instance_id, instance_id)
      REFERENCES service_instance(platform_instance_id, instance_id)
);
~~~

Đây là schema minh họa. Production schema cần thêm index, timestamp, foreign key phù hợp, encryption và migration. Mọi query repository phải luôn bao gồm platform_instance_id trong điều kiện tìm kiếm và cập nhật.

### 6.2. Không chỉ thêm cột mà quên unique key

Nếu thêm platform_instance_id vào entity nhưng vẫn giữ unique constraint toàn cục trên instance_id hoặc binding_id, broker vẫn gặp collision. Cần rà soát đồng bộ:

- Primary key.
- Unique constraints.
- Foreign keys.
- Repository query methods.
- Cache keys.
- Distributed lock keys.
- Idempotency keys.
- Provider external names.
- Audit and metrics dimensions.

Mỗi lớp cần dùng cùng namespace để tránh một request được tìm đúng trong database nhưng nhầm trong cache hoặc distributed lock.

## 7. Idempotency phải nằm trong phạm vi foundation

Platform có thể retry request do timeout. Cùng instance ID từ hai foundation không phải cùng một resource. Vì vậy request fingerprint và idempotency key phải chứa platformInstanceId.

Ví dụ khóa idempotency:

~~~text
cf-foundation-dev:instance-7f3a:provision
cf-foundation-prod:instance-7f3a:provision
~~~

Khi nhận retry:

1. Resolve platformInstanceId.
2. Tạo resource identity composite.
3. Chuẩn hóa request và tạo fingerprint.
4. Tra cứu reservation hoặc operation trong namespace đó.
5. Nếu cùng fingerprint, trả hoặc tiếp tục kết quả hiện có.
6. Nếu fingerprint khác, trả conflict theo policy.
7. Nếu không có bản ghi, reserve resource trong transaction.

Không được tìm operation chỉ theo instance ID. Nếu foundation DEV và PROD cùng có instance ID, một request retry từ DEV không được trả operation của PROD.

Với binding, fingerprint cần gắn với cả platformInstanceId, instance ID và binding ID. Unbind cũng phải tìm đúng binding composite để không thu hồi credential của foundation khác.

## 8. Async operation và last_operation trong multi-foundation mode

Khi provision, update hoặc deprovision bất đồng bộ, platform poll last operation bằng instance ID và operation token. Broker phải namespace operation theo platformInstanceId.

Một operation record:

| Field | Ý nghĩa |
|---|---|
| **platform_instance_id** | Foundation sở hữu operation |
| **operation_id** | Token operation được trả cho platform |
| **instance_id** | Instance liên quan |
| **operation_type** | Provision, update hoặc deprovision |
| **state** | Accepted, running, succeeded hoặc failed |
| **request_fingerprint** | Nhận diện retry |
| **provider_request_id** | ID request phía provider |
| **created_at / updated_at** | Thời điểm |
| **completed_at** | Thời điểm kết thúc |

Khi platform gửi last_operation, broker phải kiểm tra đồng thời platformInstanceId, instance ID và operation ID. Token operation không phải authorization credential; broker vẫn xác thực foundation và kiểm tra ownership.

Một khóa database có thể là:

~~~sql
CREATE UNIQUE INDEX uq_operation_platform_token
ON service_operation(platform_instance_id, operation_id);
~~~

Nếu broker dùng operation token ngẫu nhiên toàn cục, vẫn nên lưu platformInstanceId và kiểm tra namespace. Không dựa vào xác suất token không trùng để bỏ qua kiểm tra ownership.

## 9. Catalog và plan khi nhiều foundation cùng đăng ký

Catalog thường được dùng chung nếu broker phục vụ cùng một sản phẩm cho mọi foundation. Những trường như service ID, plan ID, tags, metadata, schemas, bindable và plan_updateable cần ổn định giữa các foundation.

Một catalog minh họa:

~~~json
{
  "services": [
    {
      "id": "service-postgresql",
      "name": "postgresql",
      "description": "Managed PostgreSQL",
      "bindable": true,
      "plan_updateable": true,
      "plans": [
        {
          "id": "plan-small",
          "name": "small",
          "description": "Plan cho workload nhỏ"
        },
        {
          "id": "plan-standard",
          "name": "standard",
          "description": "Plan cho production"
        }
      ]
    }
  ]
}
~~~

Cần giữ service ID và plan ID ổn định giữa các foundation nếu chúng biểu diễn cùng một offering. Nếu plan ID có cùng giá trị nhưng semantics khác nhau giữa foundation, broker cần có policy rõ và tránh làm platform hiểu nhầm rằng plan là tương đương.

Một số khác biệt có thể được kiểm soát ở foundation thông qua service access, quota hoặc entitlement. Không đưa secret hoặc foundation-specific tenant data vào catalog dùng chung.

## 10. Xác thực platform và liên kết credential với platformInstanceId

platformInstanceId là query parameter do platform gửi; broker không nên tin nó một cách độc lập. Nếu mọi foundation dùng chung một bộ Basic Auth credential, một foundation bị xâm nhập có thể thử gửi platformInstanceId của foundation khác.

Một phương án mạnh hơn là cấp credential riêng cho từng foundation:

| Foundation | Broker username/principal | platformInstanceId được phép |
|---|---|---|
| cf-dev | cf-dev-broker-client | cf-foundation-dev |
| cf-staging | cf-staging-broker-client | cf-foundation-staging |
| cf-prod | cf-prod-broker-client | cf-foundation-prod |

Sau khi xác thực request, broker xác định principal đã đăng nhập và kiểm tra platformInstanceId thuộc principal đó. Nếu không khớp, từ chối request trước khi truy cập resource.

Nếu platform registration hoặc môi trường không hỗ trợ credential riêng, cần có biện pháp trust khác như mTLS identity, network allowlist hoặc gateway assertion đã ký. Không xem source IP đơn lẻ là danh tính bền vững nếu traffic đi qua proxy hoặc NAT dùng chung.

### 10.1. Authentication và authorization là hai bước riêng

- Authentication xác định foundation/platform client đang gọi broker.
- platformInstanceId chọn namespace resource trong request.
- Context được dùng để resolve tenant/organization/space bên trong foundation.
- Authorization kiểm tra caller có quyền thao tác đúng instance hoặc binding.
- Provider adapter dùng service identity có scope tối thiểu để thực hiện side effect.

Một request có credential hợp lệ nhưng platformInstanceId không thuộc credential đó phải bị từ chối. Một request có platformInstanceId hợp lệ nhưng tenant context không khớp owner cũng phải bị từ chối.

## 11. Provider resource naming và tag attribution

Broker có thể tạo tài nguyên trên một cloud account hoặc Kubernetes cluster dùng chung. Tên resource nên tránh collision giữa foundation.

Một external key có thể được tạo từ platformInstanceId và instance ID:

~~~text
cfdev-pg-instance-7f3a
cfprod-pg-instance-7f3a
~~~

Không nên dùng nguyên platformInstanceId nếu giá trị có thể dài, chứa ký tự không hợp lệ hoặc tiết lộ thông tin nội bộ. Có thể tạo prefix từ hash rút gọn ổn định, đồng thời lưu mapping đầy đủ trong database.

Tags/labels provider nên chứa reference đã chuẩn hóa:

~~~json
{
  "managed_by": "spring-cloud-service-broker",
  "platform_instance_ref": "pfi-dev-7a91",
  "broker_instance_ref": "instance-7f3a",
  "service_id": "service-postgresql",
  "plan_id": "plan-standard"
}
~~~

Tags hỗ trợ inventory và reconciliation, nhưng database mapping vẫn là nguồn chuẩn. Không dùng tag có thể bị người dùng sửa làm bằng chứng authorization.

## 12. Cache và distributed lock phải có namespace

Một lỗi dễ bỏ sót là database đã dùng composite key nhưng cache vẫn dùng instance ID đơn lẻ.

Ví dụ cache key sai:

~~~text
service-instance:instance-7f3a
~~~

Cache key có namespace:

~~~text
service-instance:cf-foundation-dev:instance-7f3a
service-instance:cf-foundation-prod:instance-7f3a
~~~

Tương tự, distributed lock cho provision/update/deprovision phải bao gồm platformInstanceId. Nếu không, thao tác trên foundation DEV có thể khóa nhầm hoặc giải phóng khóa của foundation PROD.

Áp dụng cùng nguyên tắc cho:

- Redis cache.
- Lock provider.
- In-memory cache.
- Request deduplication.
- Rate limiting nếu giới hạn theo foundation.
- Metrics và audit aggregation.

Không dùng chuỗi platformInstanceId chưa validate trực tiếp làm key nếu có thể chứa separator hoặc ký tự gây nhập nhằng. Hãy encode hoặc cấu trúc key bằng các thành phần riêng.

## 13. Migration từ single-foundation sang multi-foundation

Nếu broker ban đầu chỉ phục vụ một foundation, dữ liệu hiện tại có thể chỉ có instance ID làm khóa. Khi bật multi-foundation, cần migration có kiểm soát.

Một quy trình:

1. Xác định foundation hiện tại và platformInstanceId sẽ đại diện cho nó.
2. Thêm cột platform_instance_id vào các bảng instance, binding, operation và reservation.
3. Backfill dữ liệu cũ bằng platformInstanceId đã xác minh của foundation hiện hữu.
4. Tạo composite primary/unique keys và foreign keys.
5. Cập nhật repository queries, cache keys, lock keys và idempotency.
6. Cập nhật API boundary để parse platformInstanceId.
7. Ràng buộc credential của foundation với platformInstanceId.
8. Kiểm thử request từ foundation cũ trước khi bật foundation mới.
9. Bật registration trên foundation thứ hai sau khi migration và kiểm thử hoàn tất.
10. Theo dõi collision, missing platformInstanceId và cross-foundation access.

Không backfill platformInstanceId bằng một giá trị đoán từ tên môi trường hoặc hostname. Phải xác minh foundation sở hữu từng resource cũ. Nếu không thể xác định, đưa record vào quy trình điều tra thay vì gán mặc định.

### 13.1. Chế độ tương thích tạm thời

Trong giai đoạn chuyển tiếp, broker có thể cần hỗ trợ request không có platformInstanceId từ foundation cũ. Chỉ cho phép fallback khi broker đang ở chế độ single-foundation rõ ràng và chỉ có một namespace được cấu hình.

Khi đã đăng ký nhiều foundation, request thiếu platformInstanceId phải bị từ chối nếu broker không thể xác định duy nhất nguồn. Không tự gán về foundation mặc định vì có thể truy cập nhầm resource.

## 14. Spring Cloud: xử lý platformInstanceId ở API boundary

Trong Spring Cloud Service Broker, nên parse platformInstanceId tại lớp HTTP/request adapter và chuyển nó thành một phần của command nội bộ. Không để mọi repository tự đọc query string hoặc tự suy luận foundation.

Một model nội bộ:

~~~java
public record PlatformScope(
    String platformInstanceId,
    String authenticatedPlatformPrincipal,
    String tenantId
) {}

public record ServiceInstanceKey(
    String platformInstanceId,
    String instanceId
) {}

public record ServiceBindingKey(
    String platformInstanceId,
    String instanceId,
    String bindingId
) {}
~~~

Pseudocode resolver:

~~~java
public PlatformScope resolveScope(
        String platformInstanceId,
        AuthenticatedPlatformPrincipal principal,
        Map<String, Object> context) {

    PlatformRegistration registration =
        platformRegistry.requireByPrincipal(principal.id());

    if (!registration.platformInstanceId().equals(platformInstanceId)) {
        throw new PlatformInstanceMismatchException();
    }

    TenantId tenantId = tenantResolver.requireTenant(
        registration,
        context
    );

    return new PlatformScope(
        registration.platformInstanceId(),
        principal.id(),
        tenantId.value()
    );
}
~~~

Đây là pseudocode về trách nhiệm; cách Spring Cloud Open Service Broker expose query parameters và request metadata phụ thuộc phiên bản thư viện. Hãy dùng extension point phù hợp để lấy query parameter và authenticated principal, sau đó truyền PlatformScope vào application service.

### 14.1. Repository methods luôn nhận scope

Ví dụ:

~~~java
public interface ServiceInstanceRepository {
    Optional<ServiceInstance> findByKey(ServiceInstanceKey key);

    ServiceInstance save(ServiceInstance instance);

    void deleteByKey(ServiceInstanceKey key);
}
~~~

Không tạo method chỉ nhận instanceId cho các đường xử lý multi-foundation nếu nó có thể trả về resource từ namespace khác. Nếu có use case quản trị toàn cục, hãy tách method và yêu cầu quyền admin rõ ràng.

### 14.2. Provider adapter nhận resource mapping đã xác minh

Provider adapter nên nhận resource reference đã được broker resolve từ composite key. Không để adapter tự dựng provider resource name chỉ từ instance ID. Việc này giúp adapter không vô tình tác động resource của foundation khác.

## 15. Audit, metrics và vận hành theo foundation

Khi broker dùng chung nhiều foundation, log và metric cần cho biết request đến từ foundation nào mà không gây lộ dữ liệu nhạy cảm.

Structured log có thể chứa:

- platformInstanceId đã chuẩn hóa.
- Authenticated platform principal.
- Service instance ID hoặc binding ID theo policy log.
- Tenant reference nội bộ.
- OSB operation type.
- Correlation ID.
- Kết quả authorization.
- Provider resource reference đã làm sạch.

Không ghi Basic Auth password, originating identity raw payload hoặc credentials binding.

Metric nên có dimension platformInstanceId nếu số foundation hữu hạn và được kiểm soát. Không đưa instance ID, binding ID hoặc tenant ID có cardinality rất lớn vào metric label. Có thể dùng log/tracing cho định danh chi tiết.

Một dashboard vận hành nên theo dõi:

- Request count và error rate theo foundation.
- Request thiếu hoặc sai platformInstanceId.
- Authentication principal không khớp platformInstanceId.
- Provision/update/deprovision operation đang chạy theo foundation.
- Provider error và timeout theo foundation/provider.
- Quota reservation bị kẹt.
- Resource mapping thiếu hoặc duplicate.
- Cross-foundation mismatch bị từ chối.

## 16. Reconciliation và disaster recovery

Broker cần đối soát cả database nội bộ lẫn provider resource. Khi nhiều foundation cùng dùng một broker, reconciliation phải chạy trong từng namespace hoặc có bộ lọc rõ ràng.

Một quy trình reconciliation:

1. Đọc registry instance theo platformInstanceId.
2. Tra cứu provider resource bằng provider ID hoặc external key đã lưu.
3. Kiểm tra tag/label platform reference.
4. So sánh lifecycle state giữa broker và provider.
5. Phân loại missing, orphan, duplicate hoặc stale mapping.
6. Tạo issue theo foundation và tenant.
7. Thực hiện repair có kiểm soát, không xóa resource khi chưa xác minh owner.
8. Ghi audit và xác nhận kết quả.

Backup và restore cũng cần giữ mapping platformInstanceId. Nếu restore database từ snapshot nhưng mất platform registry hoặc credential mapping, broker có thể không xác định đúng foundation sở hữu resource. Lưu trữ cấu hình platform registration và secret reference cần có quy trình backup/rotation riêng.

## 17. Kiểm thử multi-foundation

Kiểm thử phải xác minh cùng một endpoint xử lý đúng request từ nhiều foundation.

| Test case | Foundation DEV | Foundation PROD | Kết quả mong đợi |
|---|---|---|---|
| Cùng instance ID | instance-7f3a | instance-7f3a | Hai instance độc lập |
| Cùng binding ID | binding-billing | binding-billing | Hai binding độc lập |
| Provision retry | Cùng platform ID + fingerprint | Không liên quan | Chỉ một resource trong DEV |
| Cross-foundation lookup | Query DEV namespace | Request PROD | Không đọc resource DEV |
| Deprovision | Xóa instance DEV | Instance PROD cùng ID | Chỉ xóa resource DEV |
| Async polling | Operation DEV | Operation PROD cùng token giả định | Không trả state chéo namespace |
| Credential mismatch | Principal DEV | platformInstanceId PROD | Bị từ chối |
| Missing platformInstanceId | Multi-foundation mode | Không có namespace | Bị từ chối an toàn |
| Catalog | Cùng service/plan IDs | Cùng service/plan IDs | Metadata nhất quán nếu catalog dùng chung |
| Cache | Cùng instance ID | Cùng instance ID | Cache entries tách biệt |
| Lock | Update DEV | Update PROD | Lock độc lập theo namespace |
| Migration | Legacy resource | Foundation thứ hai | Backfill đúng owner, không collision |

Ngoài unit test, nên có integration test chạy hai platform client độc lập, mỗi client có credential và platformInstanceId riêng. Kiểm tra cả database key, provider external name, cache key và audit event. Chỉ kiểm tra response HTTP là chưa đủ để phát hiện dữ liệu bị ghi chéo.

## 18. Những lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Bỏ qua platformInstanceId | Resource ID giữa các foundation có thể va chạm | Dùng composite identity |
| Xem platformInstanceId là tenant ID | Mất phân tách tenant bên trong foundation | Tách platform scope và tenant scope |
| Dùng chung Basic Auth mà không bind principal với platform ID | Foundation có thể giả namespace của foundation khác | Credential riêng hoặc trust assertion có kiểm soát |
| Chỉ thêm cột nhưng giữ unique instance_id toàn cục | Vẫn xảy ra collision | Sửa primary/unique key và mọi query |
| Cache key chỉ có instance ID | Trả dữ liệu chéo foundation | Namespace cache và lock |
| Operation lookup chỉ theo instance ID | Poll nhầm operation | Scope operation theo platformInstanceId |
| Provider resource name không có namespace | Provider resource collision | External key ổn định có platform reference |
| Fallback platform ID mặc định trong multi-foundation mode | Request thiếu ID có thể tác động sai foundation | Từ chối khi không thể resolve duy nhất |
| Dùng catalog metadata để lưu foundation state | Catalog sai phạm vi và khó cache | Tách catalog với instance registry |
| Backfill migration bằng giá trị đoán | Gán sai ownership tài nguyên cũ | Xác minh owner trước migration |
| Reconciliation không lọc platform | Có thể sửa hoặc xóa resource của foundation khác | Scope mọi đối soát theo platform namespace |

## 19. Checklist đăng ký một broker với nhiều foundation

Trước khi bật foundation mới, hãy xác nhận:

- [ ] Broker endpoint có thể được truy cập an toàn từ từng foundation.
- [ ] Mỗi foundation có broker registration và service access phù hợp.
- [ ] Catalog service ID và plan ID nhất quán nếu dùng chung offering.
- [ ] Broker nhận platformInstanceId theo phiên bản OSB API/platform hỗ trợ.
- [ ] platformInstanceId được validate và lưu như namespace opaque.
- [ ] Authentication principal được liên kết với platformInstanceId được phép.
- [ ] Tenant context được resolve riêng bên trong mỗi foundation.
- [ ] Instance identity dùng platformInstanceId + instance ID.
- [ ] Binding identity dùng platformInstanceId + instance ID + binding ID.
- [ ] Operation, idempotency key, cache và distributed lock có namespace.
- [ ] Provider resource naming và labels tránh collision giữa foundation.
- [ ] Request thiếu platformInstanceId được xử lý rõ, không fallback mơ hồ.
- [ ] Migration dữ liệu single-foundation đã xác minh ownership.
- [ ] Async polling và deprovision không thể truy cập operation/resource chéo foundation.
- [ ] Audit và metrics có thể phân tích theo foundation mà không lộ secret.
- [ ] Reconciliation, backup và restore giữ được platform mapping.
- [ ] Có integration tests với ít nhất hai platform identity độc lập.

Một broker có thể phục vụ nhiều Cloud Foundry foundation bằng một endpoint và catalog chung, nhưng mọi resource lifecycle phải được namespace theo platformInstanceId. Khi kết hợp platformInstanceId với instance ID, binding ID, operation ID, authentication principal và tenant context, broker phân biệt đúng nguồn request và tránh truy cập chéo foundation. Đây là nền tảng để Spring Cloud Service Broker mở rộng từ một foundation sang nhiều môi trường Cloud Foundry mà vẫn giữ được idempotency, ownership, bảo mật và khả năng đối soát.
