# Đăng ký broker với nền tảng OSB và chạy toàn bộ vòng đời dịch vụ

## Mục tiêu capstone

Trong bài thực hành tổng hợp này, bạn sẽ xây dựng và triển khai một service broker bằng Spring Cloud Open Service Broker, đăng ký broker với một platform hỗ trợ Open Service Broker API (OSB API), sau đó chạy trọn vòng đời từ catalog đến provision, binding, update, unbinding và deprovision.

Tình huống thực hành: xây dựng broker cung cấp PostgreSQL được quản lý. Broker công bố một service offering với các plan như basic và standard. Developer tạo một service instance cho ứng dụng đơn hàng, bind ứng dụng để nhận thông tin kết nối, cập nhật plan khi nhu cầu tăng, sau đó thu hồi binding và deprovision instance khi không còn sử dụng.

Capstone kết hợp các năng lực chính của module Spring Cloud Service Broker:

- Thiết kế catalog và service plan theo OSB API.
- Xây dựng handler provision, update, deprovision, bind và unbind.
- Lưu trạng thái instance, binding và operation bền vững.
- Xử lý bất đồng bộ với worker, operation token và polling.
- Bảo đảm idempotency khi platform retry request.
- Xác thực platform, kiểm tra tenant ownership và bảo vệ credentials.
- Tích hợp Cloud Foundry; hiểu cách kết nối Kubernetes thông qua controller hoặc adapter được duy trì.
- Kiểm thử contract, lifecycle, lỗi provider và phục hồi sau restart.

Kết quả cuối cùng là một broker có thể được platform đăng ký, hiển thị trong marketplace hoặc catalog, tạo và quản lý service instance, cấp binding credentials và thu hồi tài nguyên đúng cách.

## 1. Kịch bản và tiêu chí hoàn thành

### 1.1. Kịch bản nghiệp vụ

Giả sử một nhóm phát triển có ứng dụng orders-api. Nhóm cần một PostgreSQL database được broker quản lý.

Broker công bố:

| Service | Plan | Dung lượng ví dụ | Khả năng |
|---|---|---:|---|
| managed-postgresql | basic | 10 GB | Provision, bind, deprovision |
| managed-postgresql | standard | 100 GB | Provision, bind, update, deprovision |

Các giá trị chỉ là thông số của bài thực hành. Trong triển khai thật, plan phải được ánh xạ tới quota và cấu hình mà provider thực sự cung cấp.

Luồng người dùng:

1. Operator triển khai broker và đăng ký với platform.
2. Platform đọc catalog và công bố service/plan.
3. Developer tạo instance orders-db.
4. Broker yêu cầu provider tạo PostgreSQL database.
5. Developer bind orders-api vào orders-db.
6. Broker cấp credentials riêng cho binding.
7. Ứng dụng nhận credentials qua cơ chế binding của platform.
8. Developer nâng plan từ basic lên standard nếu broker và provider hỗ trợ update.
9. Developer unbind ứng dụng và deprovision instance khi kết thúc.

### 1.2. Tiêu chí hoàn thành

Capstone được xem là hoàn tất về mặt kỹ thuật khi:

- Catalog trả service ID và plan ID ổn định.
- Platform đăng ký và xác thực được broker.
- Provision tạo đúng một backend resource dù request được gửi lại.
- Async operation có thể tiếp tục sau khi broker restart.
- last_operation trả trạng thái chính xác.
- Binding tạo credentials riêng và unbind revoke được quyền cũ.
- Update kiểm tra plan, parameters, quota và trạng thái instance.
- Deprovision không xóa nhầm resource của tenant khác.
- Log, audit và response không làm lộ secret.
- Test xác nhận cả success path và failure/recovery path.

## 2. Kiến trúc tổng thể

Broker là lớp điều phối giữa platform và provider. Platform chỉ biết OSB API; broker chịu trách nhiệm ánh xạ yêu cầu đó sang API của PostgreSQL provider hoặc hệ thống backend khác.

~~~mermaid
flowchart TD
    U[Developer / Operator] --> P[Platform: Cloud Foundry]
    P -->|OSB API over HTTPS| API[Spring Cloud Service Broker]
    API --> SEC[Authentication and Authorization]
    SEC --> APP[Application Services]
    APP --> CAT[Catalog]
    APP --> LIFE[Instance and Binding Lifecycle]
    LIFE --> DB[(Broker Database)]
    LIFE --> OUT[Transactional Outbox]
    OUT --> Q[Worker Queue]
    Q --> W[Async Workers]
    W --> AD[Provider Adapter]
    AD --> PG[PostgreSQL Provider]
    API --> OBS[Logs, Metrics and Traces]
    W --> OBS
~~~

Các thành phần:

| Thành phần | Trách nhiệm |
|---|---|
| OSB API layer | Nhận request catalog và lifecycle từ platform |
| Security layer | Xác thực platform và áp dụng authorization |
| Catalog service | Công bố service offering, plan, schema và capability |
| Lifecycle services | Điều phối provision, update, deprovision, bind và unbind |
| Broker database | Lưu instance, binding, operation và external resource reference |
| Outbox/queue | Giao việc bất đồng bộ một cách bền vững |
| Worker | Thực hiện tác vụ provider và cập nhật operation |
| Provider adapter | Đóng gói HTTP/SDK call tới PostgreSQL provider |
| Observability | Log, metrics, trace và audit |

Một request OSB có thể kết thúc trước khi provider hoàn tất công việc. Vì vậy broker phải lưu operation trước khi trả response async; không thể chỉ giữ trạng thái trong memory của một pod.

## 3. Chuẩn bị project và môi trường

### 3.1. Thành phần cần có

Môi trường thực hành nên gồm:

- JDK và Spring Boot version tương thích với phiên bản Spring Cloud Open Service Broker được chọn.
- Spring Cloud Open Service Broker dependency.
- Spring WebFlux hoặc stack HTTP mà phiên bản framework yêu cầu.
- Database quan hệ để lưu broker state.
- Queue hoặc transactional outbox cho worker.
- PostgreSQL provider thật hoặc provider stub trong môi trường test.
- Cloud Foundry foundation thử nghiệm hoặc một OSB client tương thích.
- TLS certificate và secret store cho credentials.

Không trộn các major version của Spring Boot, Spring Cloud và Spring Cloud Open Service Broker. Chọn release train tương thích rồi khóa dependency bằng dependency management của project.

### 3.2. Cấu trúc module gợi ý

~~~text
service-broker/
  src/main/java/
    config/
      BrokerSecurityConfiguration.java
      BrokerProperties.java
    catalog/
      BrokerCatalogService.java
    instance/
      ProvisionService.java
      UpdateService.java
      DeprovisionService.java
    binding/
      BindingService.java
    operation/
      OperationService.java
      OperationWorker.java
      OutboxPublisher.java
    provider/
      PostgresProviderClient.java
      PostgresProviderAdapter.java
    persistence/
      ServiceInstanceRepository.java
      ServiceBindingRepository.java
      OperationRepository.java
    security/
      PlatformAuthenticationService.java
      OwnershipPolicy.java
    observability/
      BrokerAuditService.java
  src/test/java/
    catalog/
    lifecycle/
    provider/
    security/
    support/
~~~

Đây là cấu trúc tham khảo. Hãy theo convention của project và API thực tế của Spring Cloud Open Service Broker version đã chọn.

### 3.3. Cấu hình môi trường

Ví dụ cấu hình khái niệm:

~~~yaml
server:
  port: 8080

broker:
  api:
    username: BROKER_API_USERNAME
    password: BROKER_API_PASSWORD
  features:
    async-provisioning: true
    binding: true
    plan-update: true

provider:
  postgres:
    base-url: https://postgres-provider.example.test
    credential-reference: postgres-provider-secret
~~~

Tên property là do ứng dụng định nghĩa, không phải toàn bộ đều là property mặc định của Spring. Credentials thật phải được cấp qua secret store hoặc environment injection an toàn; không commit password, token hoặc private key vào source control.

## 4. Thiết kế catalog và plan

Catalog là hợp đồng đầu tiên mà platform đọc từ broker. Service ID và plan ID phải ổn định qua các lần deploy.

Catalog minh họa:

~~~json
{
  "services": [
    {
      "id": "service-postgresql",
      "name": "managed-postgresql",
      "description": "Managed PostgreSQL database",
      "bindable": true,
      "plan_updateable": true,
      "plans": [
        {
          "id": "plan-basic",
          "name": "basic",
          "description": "PostgreSQL with 10 GB storage"
        },
        {
          "id": "plan-standard",
          "name": "standard",
          "description": "PostgreSQL with 100 GB storage"
        }
      ]
    }
  ]
}
~~~

Catalog phải phản ánh đúng backend capability:

- bindable=true chỉ khi broker có thể bind và unbind an toàn.
- plan_updateable=true chỉ khi broker hỗ trợ update theo contract và provider có thể thực thi.
- Không công bố plan chưa có backend mapping.
- Không tạo service/plan ID mới mỗi lần ứng dụng khởi động.
- Không đưa provider credentials hoặc dữ liệu nhạy cảm vào catalog.

Nếu plan có parameters, hãy công bố schema theo OSB API version và framework hỗ trợ. Broker vẫn phải validate parameters ở server vì client có thể gửi payload cũ hoặc bỏ qua schema.

### 4.1. Ánh xạ plan sang provider configuration

| Plan ID | Provider tier | Storage quota | Feature |
|---|---|---:|---|
| plan-basic | small | 10 GB | Backup cơ bản |
| plan-standard | medium | 100 GB | Backup và monitoring nâng cao |

Ánh xạ này nên nằm trong cấu hình được quản lý hoặc catalog model, không rải string literal trong nhiều handler. Khi thay đổi provider tier, cần kiểm tra ảnh hưởng tới instance đã provision.

## 5. Thiết kế dữ liệu và state machine

Broker cần lưu đủ thông tin để tiếp tục operation sau restart và nhận diện request retry.

### 5.1. Các bảng cốt lõi

Schema gợi ý:

~~~sql
CREATE TABLE service_instance (
    instance_id          VARCHAR(255) PRIMARY KEY,
    platform_id          VARCHAR(255) NOT NULL,
    tenant_id            VARCHAR(255),
    service_id            VARCHAR(255) NOT NULL,
    plan_id               VARCHAR(255) NOT NULL,
    parameters_json       TEXT,
    state                 VARCHAR(32) NOT NULL,
    external_resource_id  VARCHAR(255),
    catalog_revision      VARCHAR(64),
    created_at            TIMESTAMP NOT NULL,
    updated_at            TIMESTAMP NOT NULL
);

CREATE TABLE service_binding (
    binding_id            VARCHAR(255) PRIMARY KEY,
    instance_id           VARCHAR(255) NOT NULL,
    platform_id           VARCHAR(255) NOT NULL,
    consumer_id           VARCHAR(255),
    state                 VARCHAR(32) NOT NULL,
    external_binding_id   VARCHAR(255),
    credential_reference  VARCHAR(255),
    created_at            TIMESTAMP NOT NULL,
    updated_at            TIMESTAMP NOT NULL
);

CREATE TABLE broker_operation (
    operation_id          VARCHAR(255) PRIMARY KEY,
    instance_id           VARCHAR(255) NOT NULL,
    operation_type        VARCHAR(32) NOT NULL,
    idempotency_key       VARCHAR(255) NOT NULL UNIQUE,
    state                 VARCHAR(32) NOT NULL,
    attempt_count         INTEGER NOT NULL,
    last_error_code       VARCHAR(128),
    last_error_message    TEXT,
    created_at            TIMESTAMP NOT NULL,
    updated_at            TIMESTAMP NOT NULL
);
~~~

Đây là schema minh họa. Có thể bổ sung unique constraint, foreign key, tenant index, optimistic locking và mã hóa dữ liệu nhạy cảm theo yêu cầu hệ thống. Không lưu password binding dạng plaintext trong bảng; lưu secret reference hoặc dùng cơ chế mã hóa phù hợp.

### 5.2. Trạng thái service instance

Ví dụ state machine:

~~~mermaid
stateDiagram-v2
    [*] --> PROVISIONING
    PROVISIONING --> READY
    PROVISIONING --> FAILED
    READY --> UPDATING
    UPDATING --> READY
    UPDATING --> FAILED
    READY --> DEPROVISIONING
    FAILED --> DEPROVISIONING
    DEPROVISIONING --> DEPROVISIONED
    DEPROVISIONING --> FAILED
~~~

Không phải mọi transition đều hợp lệ trong mọi hệ thống. Ví dụ update chỉ được chấp nhận khi instance READY; deprovision có thể được phép từ READY hoặc FAILED nếu broker có thể xác định và thu hồi resource.

Mỗi transition cần kiểm tra trạng thái hiện tại trong transaction. Không chỉ dựa vào trạng thái mà client gửi.

### 5.3. Trạng thái binding

Binding có vòng đời riêng:

- CREATING: đang tạo backend principal/credential.
- READY: credentials đã cấp và có thể dùng.
- REVOKING: đang thu hồi quyền.
- REVOKED: quyền đã thu hồi.
- FAILED: thao tác thất bại và cần xử lý/reconcile.

Không đánh dấu binding REVOKED chỉ vì đã xóa Kubernetes Secret hoặc metadata broker. Cần xác minh backend principal hoặc grant đã bị thu hồi.

## 6. Xây dựng OSB API handlers

Spring Cloud Open Service Broker cung cấp abstraction để triển khai catalog và lifecycle services. Tên interface, kiểu trả về và registration API thay đổi theo version; hãy sử dụng contract của dependency đã khóa trong project.

Ở mức nghiệp vụ, broker cần xử lý các operation sau:

| OSB operation | HTTP method và resource | Hành vi |
|---|---|---|
| Catalog | GET /v2/catalog | Trả service và plan |
| Provision | PUT /v2/service_instances/{instance_id} | Tạo instance |
| Last operation | GET /v2/service_instances/{instance_id}/last_operation | Trả trạng thái async |
| Update | PATCH /v2/service_instances/{instance_id} | Thay đổi plan/parameters |
| Deprovision | DELETE /v2/service_instances/{instance_id} | Thu hồi instance |
| Bind | PUT /v2/service_instances/{instance_id}/service_bindings/{binding_id} | Tạo binding |
| Unbind | DELETE /v2/service_instances/{instance_id}/service_bindings/{binding_id} | Thu hồi binding |

Các query parameters và response phụ thuộc OSB API version. Provision/update có thể dùng accepts_incomplete=true khi platform chấp nhận async. Deprovision cũng có thể cần async theo capability và contract. Binding/unbinding trong OSB API chuẩn là synchronous operations.

### 6.1. Catalog handler

Catalog handler trả catalog đã được cấu hình và kiểm tra. Nó không nên gọi provider để tạo resource. Có thể cache catalog nếu nội dung ổn định và cache được invalidated khi catalog revision thay đổi.

### 6.2. Provision handler

Provision handler cần:

1. Xác thực platform.
2. Kiểm tra service ID và plan ID.
3. Validate parameters và quota.
4. Kiểm tra instance ID đã tồn tại chưa.
5. Kiểm tra idempotency và ownership.
6. Tạo instance record cùng operation/outbox nếu async.
7. Gọi provider hoặc giao việc cho worker.
8. Trả response theo chế độ sync/async được chấp nhận.

Nếu instance ID đã được provision với cùng owner và cùng request identity, request retry phải trả kết quả phù hợp theo OSB contract thay vì tạo database mới.

### 6.3. Update handler

Update cần kiểm tra:

- Service ID có đúng instance không.
- Plan ID đích có thuộc service không.
- Plan update có được catalog công bố không.
- Parameters thay đổi có hợp lệ không.
- Provider có hỗ trợ thay đổi tương ứng không.
- Instance có đang ở operation xung đột không.
- Caller có quyền trên instance không.

Nếu update cần async, lưu operation và sử dụng worker như provision. Không cập nhật plan_id trong database thành công trước khi provider transition đã được xác nhận hoặc có trạng thái trung gian rõ ràng.

### 6.4. Deprovision handler

Deprovision cần tìm đúng instance trong phạm vi platform/tenant, xác định external resource ID và xử lý cleanup. Nếu instance không tồn tại, response cần tuân theo idempotency semantics của OSB API và broker policy.

Không xóa metadata trước khi lưu đủ thông tin để retry deprovision. Một request delete có thể timeout sau khi provider đã xóa resource; lần retry cần lookup hoặc xác nhận absence thay vì giả định backend vẫn còn.

## 7. Provision bất đồng bộ và transactional outbox

Tạo database có thể mất nhiều giây hoặc lâu hơn. Nếu broker không thể hoàn tất trong request, platform phải chấp nhận incomplete operation.

Luồng:

~~~mermaid
sequenceDiagram
    participant P as Platform
    participant B as Broker
    participant DB as Broker DB
    participant W as Worker
    participant V as Provider
    P->>B: PUT provision + accepts_incomplete=true
    B->>DB: Insert instance, operation, outbox
    B-->>P: 202 Accepted + operation token
    W->>DB: Claim outbox/operation
    W->>V: Create PostgreSQL resource
    V-->>W: External resource ID
    W->>DB: Mark instance READY and operation SUCCEEDED
    P->>B: GET last_operation
    B->>DB: Read operation state
    B-->>P: succeeded
~~~

### 7.1. Ghi operation trước response 202

Trong một transaction database:

- Tạo hoặc cập nhật service instance sang PROVISIONING.
- Tạo operation với token/idempotency key ổn định.
- Ghi outbox event.
- Commit transaction.

Chỉ sau commit mới trả 202. Nếu broker crash ngay sau khi trả 202, outbox publisher hoặc worker vẫn có thể tiếp tục.

### 7.2. Worker và retry

Worker cần:

- Claim operation bằng lock/lease hoặc cơ chế cạnh tranh an toàn.
- Đọc operation và external resource reference.
- Gọi provider với idempotency key ổn định.
- Lưu kết quả provider trước khi đánh dấu operation thành công.
- Phân loại lỗi permanent và transient.
- Retry có backoff, jitter và giới hạn.
- Đưa operation quá hạn vào reconciliation/dead-letter workflow.

Không để hai worker đồng thời thực hiện side effect cho cùng operation nếu provider không hỗ trợ idempotency.

### 7.3. Last operation

Endpoint last_operation đọc trạng thái từ database bền vững. Response thường có state như in progress, succeeded hoặc failed, cùng description an toàn khi cần.

Không suy ra trạng thái chỉ từ việc worker còn chạy. Operation phải phản ánh kết quả đã được commit. Nếu provider đã tạo resource nhưng broker chưa lưu external ID do crash, operation cần ở trạng thái reconciliation/unknown thay vì báo thành công hoặc tạo lại resource một cách mù quáng.

## 8. Idempotency và xử lý request retry

Platform có thể retry khi network timeout hoặc không nhận được response. Broker cần bảo đảm cùng một request logic không tạo nhiều backend resources.

Một khóa idempotency có thể được suy ra từ:

- Platform identity.
- Operation type.
- Instance ID hoặc binding ID.
- Request identity/fingerprint.
- Operation generation nếu cùng instance có nhiều lần update hợp lệ.

Ví dụ logic:

~~~java
public Mono<ProvisionResult> provision(ProvisionCommand command) {
    return operationRepository
            .findByIdempotencyKey(command.idempotencyKey())
            .flatMap(existing -> resultFrom(existing))
            .switchIfEmpty(
                    createOperationAndProvision(command)
            );
}
~~~

Đây là pseudocode. Cần bảo đảm insert và unique constraint là atomic; mẫu find-then-insert đơn thuần có thể gặp race khi hai request đồng thời.

### 8.1. Cùng ID nhưng payload khác

Nếu platform gửi lại cùng instance ID nhưng parameters hoặc plan khác, broker không được coi đó là retry giống hệt. Hãy so sánh request identity và trả conflict theo contract/policy nếu instance đã được tạo bằng yêu cầu khác.

### 8.2. Timeout sau side effect

Provider có thể tạo database nhưng response bị mất. Broker phải tra cứu theo idempotency key, deterministic resource name hoặc metadata tag trước khi gửi create lần nữa.

Nếu provider không hỗ trợ idempotency hay lookup, broker cần một quy trình reconciliation đủ tin cậy. Không thể đảm bảo exactly-once chỉ bằng retry ở HTTP client.

## 9. Binding và credentials cho workload

Khi ứng dụng bind vào instance orders-db, broker tạo một principal hoặc credential riêng cho binding. Cách này giúp revoke từng consumer mà không ảnh hưởng các consumer khác.

Binding response minh họa:

~~~json
{
  "credentials": {
    "uri": "jdbc:postgresql://db.example.test:5432/orders",
    "username": "orders_api_binding",
    "password": "REDACTED_TEST_SECRET"
  }
}
~~~

Trong môi trường thật, credentials phải được tạo từ provider hoặc secret manager và trả về theo response contract. Không dùng secret cố định trong source code.

### 9.1. Bind

- Xác thực platform và kiểm tra ownership instance.
- Xác minh instance READY và plan cho phép binding.
- Kiểm tra binding ID đã tồn tại chưa.
- Tạo principal/credential riêng ở provider.
- Lưu external binding ID và secret reference.
- Trả binding credentials theo OSB API.

### 9.2. Unbind

- Kiểm tra binding thuộc đúng instance và platform.
- Chuyển binding sang REVOKING.
- Gọi provider revoke user/grant.
- Xác nhận quyền cũ không còn hiệu lực.
- Đánh dấu REVOKED rồi dọn secret reference theo policy.

Nếu provider revoke timeout, không xóa metadata cần để retry. Một credential chưa revoke vẫn có thể truy cập backend dù platform đã bỏ binding.

## 10. Bảo mật và multi-tenancy

Broker là điểm trung gian có quyền tạo và thu hồi tài nguyên. Cần bảo vệ cả platform-to-broker và broker-to-provider.

### 10.1. Platform authentication

- Dùng HTTPS.
- Xác thực credentials mà platform dùng khi gọi broker.
- Không ghi Authorization header vào log.
- Rotate credentials có overlap và xác nhận.
- Giới hạn endpoint management theo network và role.

### 10.2. Authorization và ownership

Mỗi instance và binding cần lưu platform/tenant owner. Trước update, bind, unbind hoặc deprovision, kiểm tra caller có quyền trên resource đó.

Không dùng instance ID hoặc tenant ID từ request làm bằng chứng ownership. Có thể trả 404 thay vì 403 nếu policy cần che existence của tài nguyên tenant khác, nhưng audit nội bộ vẫn phân biệt hai trường hợp.

### 10.3. Provider credentials và binding secrets

- Provider API token lưu trong secret store.
- Broker database chỉ lưu secret reference hoặc dữ liệu đã mã hóa.
- Binding credentials không dùng chung nếu cần revoke riêng.
- Response error không chứa provider token hoặc stack trace.
- Log và trace che parameters nhạy cảm.
- Quyền backend service account theo least privilege.

## 11. Đăng ký broker với Cloud Foundry

Cloud Foundry là platform thực hành chính cho luồng OSB trong capstone. Broker cần được deploy với route HTTPS mà Cloud Controller có thể truy cập.

### 11.1. Kiểm tra catalog trước khi đăng ký

Gọi GET /v2/catalog bằng credentials test và header version tương thích. Xác minh service/plan IDs, bindable, plan_updateable và schema.

### 11.2. Đăng nhập và đăng ký

Ví dụ:

~~~bash
cf api https://api.example-cf.test
cf login
cf target -o platform-ops -s broker-test

cf create-service-broker spring-cloud-broker broker-cf-user "<broker-password>" https://broker.example-cf.test
cf service-brokers
~~~

Tài khoản CLI cần quyền quản trị foundation phù hợp. cf create-service-broker lưu broker registration để Cloud Controller gọi broker. Tên đăng ký này khác tên service offering trong catalog.

### 11.3. Cấp quyền service access và kiểm tra marketplace

~~~bash
cf enable-service-access managed-postgresql --org product-team
cf marketplace
~~~

Cú pháp tùy chọn có thể khác theo phiên bản CF CLI; kiểm tra cf help enable-service-access trong môi trường mục tiêu.

Nếu broker đã đăng ký nhưng service không xuất hiện trong marketplace, kiểm tra catalog và service access trước khi sửa lifecycle handler.

### 11.4. Chạy lifecycle từ Cloud Foundry CLI

~~~bash
cf create-service managed-postgresql basic orders-db
cf service orders-db

cf bind-service orders-api orders-db
cf env orders-api

cf update-service orders-db -p standard

cf unbind-service orders-api orders-db
cf delete-service orders-db
~~~

Lệnh update minh họa yêu cầu platform và service plan hỗ trợ plan update; xác minh cú pháp CF CLI của phiên bản đang dùng. Không chạy các lệnh destructive trên dữ liệu production.

Theo dõi operation bằng cf service và broker logs. Khi async operation vẫn đang chạy, không gửi lại create hoặc delete chỉ vì CLI chưa hiển thị trạng thái cuối.

## 12. Tích hợp Kubernetes

Kubernetes core không cung cấp sẵn một OSB marketplace tương đương Cloud Foundry. Dự án Kubernetes Service Catalog cũ đã trở thành legacy và không nên được mặc định chọn cho cluster mới.

Nếu cần tích hợp broker OSB với Kubernetes, có thể xây một controller/operator được duy trì:

- CRD đại diện service instance và binding.
- Controller gọi OSB API.
- Status conditions phản ánh operation.
- Secret được tạo trong namespace được phép.
- Finalizer bảo đảm unbind/deprovision trước khi xóa object.
- Retry, idempotency và reconciliation được lưu bền vững.

Ví dụ CRD do tổ chức tự định nghĩa:

~~~yaml
apiVersion: platform.example.io/v1alpha1
kind: BrokerServiceInstance
metadata:
  name: orders-db
  namespace: product-team
spec:
  brokerRef: postgres-broker
  serviceId: service-postgresql
  planId: plan-basic
  parameters:
    storageGb: 10
status:
  phase: Provisioning
  operationId: provision-001
~~~

Đây là API minh họa, không phải resource Kubernetes built-in. Controller cần bảo vệ broker credentials, xác minh tenant scope, lưu operation ID và tiếp tục reconcile sau restart.

Một phương án khác là dùng Crossplane/provider hoặc operator chuyên biệt nếu chúng phù hợp backend. Service Binding Specification có thể giúp đưa binding data tới workload nhưng bản thân nó không thay thế provisioning/deprovisioning. Hãy phân biệt rõ controller nào sở hữu lifecycle và controller nào chỉ phân phối credentials.

## 13. Kiểm thử toàn bộ capstone

### 13.1. Unit và contract tests

- Catalog có ID ổn định và metadata đúng.
- Plan validation từ chối plan không thuộc service.
- Parameters validation từ chối dữ liệu sai.
- Version negotiation từ chối OSB version không hỗ trợ.
- Security trả 401 khi credentials sai.
- Authorization từ chối tenant không sở hữu instance.
- Provider adapter serialize/deserialize đúng contract.

### 13.2. Lifecycle integration tests

| Test | Kết quả cần xác nhận |
|---|---|
| Provision thành công | Một instance và một provider resource |
| Provision gửi lại cùng request | Không tạo resource thứ hai |
| Cùng instance ID nhưng payload khác | Conflict theo policy |
| Provider timeout trước khi gửi request | Operation retry có giới hạn |
| Provider tạo resource nhưng response mất | Lookup/reconciliation không tạo duplicate |
| Async provision | 202, operation bền vững và last_operation đúng |
| Worker restart | Operation tiếp tục sau restart |
| Binding thành công | Credentials riêng được cấp |
| Bind gửi lại | Không tạo principal trùng |
| Unbind | Credential cũ bị revoke |
| Update plan | Plan và backend configuration nhất quán |
| Deprovision | Resource được thu hồi đúng một lần |
| Caller sai tenant | Không có provider side effect |

### 13.3. End-to-end test trên platform

Trong foundation thử nghiệm:

1. Đăng ký broker.
2. Kiểm tra catalog và marketplace.
3. Tạo instance.
4. Theo dõi operation.
5. Bind application.
6. Xác nhận application nhận credentials.
7. Thử update plan.
8. Unbind và xác nhận credential cũ không còn dùng được.
9. Deprovision và xác nhận provider resource đã bị xóa.
10. Kiểm tra audit, logs và metrics.

Test end-to-end cần dùng resource và dữ liệu riêng. Có thể dùng provider sandbox hoặc fake provider có state để không ảnh hưởng dịch vụ thật.

## 14. Quan sát và vận hành

Một broker có thể trả đúng HTTP response nhưng vẫn có operation mắc kẹt hoặc backend resource mồ côi. Cần theo dõi cả API và lifecycle.

Metric gợi ý:

| Metric | Ý nghĩa |
|---|---|
| broker_osb_requests_total | Request OSB theo endpoint/status |
| broker_provision_duration_seconds | Thời gian provision |
| broker_operation_age_seconds | Tuổi operation chưa hoàn tất |
| broker_operation_failed_total | Operation thất bại |
| broker_provider_requests_total | Request provider theo status |
| broker_provider_timeout_total | Timeout provider |
| broker_binding_revoke_failure_total | Lỗi thu hồi binding |
| broker_orphan_resource_total | Resource backend không còn mapping hợp lệ |

Log nên chứa correlation ID, operation ID, instance ID đã được kiểm soát, platform ID và error category. Không dùng credentials, password hoặc tenant ID không giới hạn làm metric label.

Thiết lập cảnh báo cho operation quá hạn, tỷ lệ provider timeout tăng, lỗi 401/403/412 bất thường và binding revoke thất bại.

## 15. Triển khai và nâng cấp an toàn

Khi phát hành phiên bản broker mới:

- Giữ service ID và plan ID ổn định.
- Không đổi schema theo cách làm request cũ mất hiệu lực nếu chưa có migration.
- Đảm bảo worker và API server cùng hiểu operation record version.
- Rollout code và cấu hình capability nhất quán giữa replica.
- Giữ handler deprovision/unbind cho tài nguyên đã tạo từ release cũ.
- Không tắt provider adapter cũ khi còn instance phụ thuộc.
- Có backup database và quy trình restore.
- Kiểm tra catalog từ platform sau rollout.

Nếu feature mới chưa sẵn sàng trên mọi replica, giữ feature flag tắt cho đến khi handler, provider và worker đều được triển khai. Không để một replica quảng bá capability mà replica khác từ chối.

## 16. Checklist nghiệm thu

- [ ] Broker khởi động và health check hoạt động.
- [ ] TLS và platform authentication được cấu hình.
- [ ] Catalog trả service/plan IDs ổn định.
- [ ] Catalog metadata phản ánh capability thực tế.
- [ ] Cloud Foundry đăng ký được broker.
- [ ] Service access và marketplace hoạt động.
- [ ] Provision tạo đúng một backend resource.
- [ ] Async operation được lưu bền vững.
- [ ] Worker tiếp tục operation sau restart.
- [ ] Last operation trả trạng thái chính xác.
- [ ] Idempotency ngăn duplicate khi retry.
- [ ] Binding tạo credential riêng.
- [ ] Unbind revoke credential cũ.
- [ ] Update kiểm tra plan và quota.
- [ ] Deprovision thu hồi resource đúng owner.
- [ ] Request trái quyền không tạo side effect.
- [ ] Error response không làm lộ secret.
- [ ] Logs, metrics và audit hỗ trợ điều tra.
- [ ] Test provider timeout, 429/5xx, connection reset và unknown outcome.
- [ ] Có quy trình backup, rollback và nâng cấp.

## Kết luận

Capstone đưa toàn bộ kiến thức Spring Cloud Service Broker vào một quy trình có thể triển khai: thiết kế catalog, đăng ký broker với platform, provision service instance, theo dõi async operation, bind workload, update plan, unbind và deprovision. Broker phải lưu trạng thái bền vững, dùng idempotency để chịu được retry, xác minh platform/tenant ownership và bảo vệ credentials trên cả hai đường platform-to-broker và broker-to-provider.

Cloud Foundry cung cấp luồng đăng ký và marketplace phù hợp để kiểm thử OSB API end-to-end. Với Kubernetes, hãy dùng controller/operator hoặc provider integration được duy trì để quản lý lifecycle và binding; không phụ thuộc mặc định vào Kubernetes Service Catalog legacy. Khi mọi operation có state rõ ràng, side effect có thể phục hồi và lifecycle được kiểm thử trên platform thật, service broker mới sẵn sàng cho môi trường vận hành.
