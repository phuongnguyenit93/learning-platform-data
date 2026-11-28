# Tích hợp một dịch vụ cơ sở dữ liệu hoặc bộ nhớ đệm thực tế

Một service broker chỉ thực sự có giá trị khi các thao tác OSB làm thay đổi một dịch vụ có thể sử dụng được. Catalog phải mô tả đúng sản phẩm; provision phải tạo tài nguyên ở provider; binding phải cấp thông tin kết nối; update phải áp dụng được thay đổi được hỗ trợ; deprovision phải thu hồi tài nguyên và credentials. Bài capstone này xây dựng một broker Spring Cloud tích hợp PostgreSQL thực tế theo mô hình một database logic cho mỗi service instance và một database role riêng cho mỗi binding.

PostgreSQL được chọn để minh họa vì có thể kiểm tra trực tiếp database, role, grant, transaction và kết nối ứng dụng. Cùng kiến trúc đó có thể thay provider adapter bằng Redis để cấp cache, user/ACL và endpoint. Bài tập đi xuyên suốt từ API Open Service Broker đến provider, bao gồm state, operation bất đồng bộ, idempotency, bảo mật, kiểm thử và vận hành.

## 1. Mục tiêu và phạm vi capstone

Sau khi hoàn thành, broker cần:

- Công bố một PostgreSQL service và ít nhất hai service plan.
- Nhận provision request theo Open Service Broker API và tạo database logic trên PostgreSQL.
- Trả kết quả đồng bộ khi thao tác hoàn tất nhanh, hoặc dùng async operation khi cần.
- Tạo binding riêng với username/password và quyền truy cập đúng database.
- Thu hồi binding bằng cách vô hiệu hóa role và quyền tương ứng.
- Xử lý update theo các thuộc tính plan mà provider thực sự hỗ trợ.
- Deprovision database và giải phóng quota sau khi xác nhận cleanup.
- Chống request lặp, worker retry và provider timeout mà không tạo database hoặc role trùng.
- Có integration tests chạy với PostgreSQL thật trong môi trường test.

Phạm vi triển khai đầu tiên dùng một PostgreSQL cluster do operator quản lý. Mỗi OSB service instance tương ứng với một database logic riêng trên cluster đó. Đây là mô hình phù hợp cho môi trường học tập hoặc một số dịch vụ multi-tenant có ranh giới bảo mật phù hợp. Nó không tương đương với một PostgreSQL server/cluster riêng cho từng khách hàng; CPU, RAM, storage, failure domain và một số quyền quản trị vẫn được chia sẻ ở cấp cluster.

Nếu yêu cầu cách ly mạnh, noisy-neighbor isolation hoặc SLA riêng, provider adapter cần tạo managed database instance/cluster riêng qua cloud API. Các bước OSB, operation store và binding contract vẫn tương tự, nhưng provisioner gọi API tạo cluster thay vì chạy CREATE DATABASE trên cluster dùng chung.

## 2. Kiến trúc tổng thể

Tách broker protocol, nghiệp vụ vòng đời và tích hợp PostgreSQL:

~~~text
Cloud Foundry / Kubernetes platform
              |
              | Open Service Broker API
              v
     Spring Cloud OSB Controller
              |
       Catalog / Lifecycle
              |
      Application Services
       |       |        |
       |       |        +---- Quota and Policy
       |       +------------- Operation Store
       |                       + Outbox
       |
       +---- PostgreSQL Provider Adapter
                    |
              Admin Connection
                    |
             PostgreSQL Cluster
              |             |
        Database per     Role per
        instance         binding

       Secret Manager / KMS
       Metrics / Logs / Traces
~~~

| Thành phần | Trách nhiệm |
|---|---|
| OSB controller | Nhận request catalog, provision, update, deprovision, bind và unbind |
| Catalog service | Công bố service definition, plans, bindability và schemas |
| Application service | Kiểm tra policy và điều phối lifecycle |
| Operation store | Lưu operation, state, attempt, checkpoint và kết quả |
| Outbox/worker | Dispatch và xử lý operation bền vững |
| Quota service | Reserve, commit và release quota |
| PostgreSQL provider adapter | Tạo/xóa database, tạo/revoke role, kiểm tra actual state |
| Secret manager | Lưu hoặc mã hóa thông tin quản trị và credential cần giữ |
| Observability | Thu metrics, logs, traces và audit events |

Không để OSB handler tự chạy SQL quản trị hoặc tự tạo password. Handler chuyển request thành command; application service kiểm tra state và policy; provider adapter thực hiện thao tác hạ tầng.

## 3. Chuẩn bị môi trường PostgreSQL

Tạo một PostgreSQL instance dành cho môi trường phát triển và test. Broker cần hai loại kết nối:

- **Admin connection:** dùng bởi provider adapter để tạo database, role và grant. Tài khoản này có quyền quản trị cần thiết, được giữ trong secret manager.
- **Application/binding connection:** thông tin broker trả cho consumer để kết nối database logic đã provision. Không dùng admin credential làm binding credential.

Tạo role quản trị riêng cho broker thay vì dùng superuser. Quyền cần thiết phụ thuộc cách quản lý database, role, ownership và PostgreSQL version. Với mô hình database logic, adapter thường cần quyền tạo database và role, cấp/revoke quyền trên database. Kiểm tra chính sách của managed PostgreSQL provider vì một số dịch vụ không cho phép CREATEDB, CREATEROLE hoặc một số câu lệnh quản trị.

Các điều kiện hạ tầng:

- Broker kết nối được PostgreSQL qua private network.
- TLS được bật và client xác minh certificate/hostname.
- PostgreSQL chỉ mở port cho broker và consumer network được phép.
- Admin secret được cấp qua secret manager hoặc Kubernetes Secret được bảo vệ.
- Có database/role quản trị dành riêng cho broker metadata nếu cần.
- Có backup và restore policy cho dữ liệu của khách hàng.
- Có giới hạn connection để tổng binding không làm cạn connection capacity của cluster.

Không đưa admin password vào source code, Docker image, Git, application log hoặc command line. Dùng cấu hình ngoài ứng dụng và phân quyền đọc secret cho đúng workload.

## 4. Thiết kế service và plan

Ví dụ broker công bố service có ID cố định là postgres-db:

| Plan ID | Tên | Giới hạn minh họa | Bindable |
|---|---|---|---|
| starter | PostgreSQL Starter | Tối đa 10 binding, connection budget thấp | Có |
| production | PostgreSQL Production | Tối đa 50 binding, connection budget cao hơn | Có |

Plan ID phải ổn định qua các lần deploy. Tên hiển thị và description có thể thay đổi mà không làm mất định danh plan mà platform đã lưu.

Một service definition có thể công bố service ID và name, description, metadata, documentation link, danh sách plans, bindable capability, plan update capability nếu thực sự hỗ trợ, cùng provisioning/binding parameter schemas.

Ví dụ parameters do consumer có thể cung cấp khi provision:

~~~json
{
  "databaseName": "orders",
  "encoding": "UTF8",
  "connectionLimit": 30
}
~~~

Không dùng databaseName trực tiếp làm tên database trong cluster. Broker tạo physical identifier riêng từ instance ID, ví dụ một chuỗi có prefix cố định và phần hash/base32 rút gọn. Tên do consumer gửi chỉ là display metadata đã validate, tránh va chạm và SQL injection.

Plan có thể quyết định connection budget, feature entitlement, backup policy hoặc maintenance policy. Không quảng cáo tính năng mà provider adapter chưa triển khai.

### Lưu ý về giới hạn storage PostgreSQL

PostgreSQL không có hard per-database storage quota tổng quát được bảo đảm chỉ bằng một thuộc tính database. Nếu catalog công bố storage 100 GB như hard limit, broker phải có cơ chế thực sự thực thi và đo lường được. Có thể dùng managed service có quota riêng, cluster/volume riêng, tablespace và policy vận hành phù hợp, hoặc mô hình khác đã được kiểm chứng. Không coi một metric cảnh báo dung lượng là hard quota.

Trong capstone này, quota chính được minh họa bằng số instance, connection budget và số binding. Storage được giám sát như observed usage; chỉ công bố storage cap khi provider adapter có cơ chế thực thi cụ thể.

## 5. Cấu trúc package đề xuất

~~~text
broker/
  catalog/
    BrokerCatalogService
    CatalogAssembler
  lifecycle/
    ProvisionApplicationService
    UpdateApplicationService
    DeprovisionApplicationService
    BindingApplicationService
  operation/
    OperationRepository
    OperationWorker
    OutboxPublisher
  quota/
    QuotaService
    QuotaReservation
  provider/
    DatabaseProvider
    PostgreSqlDatabaseProvider
    PostgreSqlAdminClient
  security/
    CredentialGenerator
    SecretStore
  persistence/
    ServiceInstanceEntity
    BindingEntity
    OperationEntity
~~~

Các tên lớp là thiết kế tham khảo. Dùng interface và chữ ký thực tế của phiên bản Spring Cloud Open Service Broker đang cài đặt. Không cần tạo một lớp cho mỗi tên trong sơ đồ nếu dự án nhỏ; điều quan trọng là tách protocol mapping khỏi provider-specific SQL.

## 6. Cấu hình kết nối và quản lý secret

Ví dụ cấu hình logic:

~~~yaml
broker:
  postgres:
    host: <BROKER_PG_HOST>
    port: 5432
    admin-database: postgres
    ssl-mode: verify-full
    connection-timeout: 5s
    statement-timeout: 20s
  operations:
    lease-duration: 60s
    max-attempts: 8
~~~

Admin username/password nên được bind từ secret manager hoặc external secret integration, không đặt giá trị mặc định trong YAML. Không log object cấu hình vì có thể chứa secret.

Dùng connection pool giới hạn cho admin client. Provision worker có concurrency hữu hạn; không mở một admin connection cho mỗi request vô hạn. Đặt connect timeout, statement timeout và query timeout. Nếu provider call timeout, operation cần chuyển sang reconcile state thay vì mặc định kết luận database chưa được tạo.

## 7. Thiết kế provider adapter

Tạo abstraction để application service không phụ thuộc PostgreSQL:

~~~java
public interface DatabaseProvider {
    Mono<DatabaseResource> provision(ProvisionSpec spec);
    Mono<BindingCredentials> bind(BindingSpec spec);
    Mono<Void> unbind(UnbindSpec spec);
    Mono<DatabaseResource> update(UpdateSpec spec);
    Mono<Void> deprovision(DeprovisionSpec spec);
    Mono<ProviderResourceState> describe(String externalId);
}
~~~

Đây là interface minh họa. Có thể thay Mono bằng kiểu reactive mà dự án sử dụng, hoặc dùng blocking adapter trên bounded-elastic scheduler nếu JDBC driver là blocking. Không chạy JDBC blocking trực tiếp trên Reactor event-loop.

Provider adapter cần:

- Nhận các ID nội bộ đã được xác thực và spec đã validate.
- Sinh physical database/role identifiers theo quy tắc an toàn.
- Không ghép raw user input vào SQL.
- Có idempotency theo instance ID, binding ID và operation ID.
- Kiểm tra resource đã tồn tại trước khi tạo lại sau timeout.
- Lưu external resource ID và ownership metadata.
- Chuẩn hóa lỗi provider thành domain error có thể retry hoặc terminal.
- Có timeout, retry policy và logging không chứa secret.

## 8. An toàn khi tạo database và role

Giá trị SQL như database name và role name là identifier, không phải parameter value. Prepared statement không thể bind identifier ở vị trí tên database hoặc tên role. Vì vậy:

1. Sinh identifier từ ID nội bộ bằng alphabet cố định.
2. Giới hạn chiều dài theo PostgreSQL identifier limit.
3. Quote identifier bằng thư viện/utility chuyên dụng đã kiểm chứng.
4. Không dùng databaseName do consumer gửi làm identifier.
5. Dùng bind parameters cho các value như password, timeout hoặc metadata khi driver/statement hỗ trợ.
6. Không nối chuỗi SQL với input không tin cậy.

Ví dụ tên nội bộ:

~~~java
String databaseName =
        "svc_" + base32(sha256(instanceId)).substring(0, 20);

String roleName =
        "bind_" + base32(sha256(bindingId)).substring(0, 20);
~~~

Đây là pseudocode; cần xử lý collision và kiểm tra độ dài identifier thực tế. Lưu mapping giữa OSB ID và physical identifier trong broker database. Không giải mã physical name để suy ra tenant hoặc instance.

Một điểm quan trọng của PostgreSQL: CREATE DATABASE không được chạy bên trong transaction block thông thường. Provider adapter phải dùng connection/transaction boundary phù hợp và kiểm thử đúng driver. Không bao bọc toàn bộ provisioning bằng một transaction giả định có thể rollback cả CREATE DATABASE. Provisioning là workflow nhiều bước; nếu bước sau lỗi, dùng compensation/reconciliation.

## 9. Luồng provision end-to-end

Khi platform gửi provision request:

1. OSB handler parse request, API version, instance ID, service ID, plan ID và parameters.
2. Application service xác thực service/plan có tồn tại và caller có quyền.
3. Validate parameters theo schema và policy server-side.
4. Kiểm tra instance ID đã tồn tại chưa và so sánh request fingerprint để xử lý retry.
5. Reserve instance/connection quota trong transaction.
6. Tạo service instance record, operation record và outbox event trong cùng transaction.
7. Nếu request không cho phép async nhưng operation cần async, trả AsyncRequired trước khi chấp nhận side effect.
8. Nếu được chấp nhận async, trả 202 cùng operation key; worker tiếp tục provision.
9. Worker claim operation, gọi PostgreSQL provider adapter và lưu checkpoint.
10. Khi database đã được xác minh tồn tại, lưu external ID, chuyển reservation thành committed usage và đánh dấu operation thành công.

Với thao tác có thể hoàn tất nhanh, broker có thể trả kết quả đồng bộ. Nếu provider call kéo dài hoặc workflow có nhiều bước, dùng async operation theo OSB contract. Không trả 202 trước khi operation/outbox được lưu bền vững.

~~~text
REQUESTED
    |
    v
VALIDATED
    |
    v
QUOTA_RESERVED
    |
    v
PROVISIONING
    |
    +---- provider failure ----> RETRY_WAIT / FAILED
    |
    v
DATABASE_VERIFIED
    |
    v
ACTIVE
~~~

Nếu provider timeout sau CREATE DATABASE, worker mới phải describe hoặc tra cứu physical identifier trước khi chạy lại lệnh tạo. Nếu database đã tồn tại và ownership mapping khớp, tiếp tục workflow; nếu resource có cùng tên nhưng không xác định được owner, dừng và báo conflict để tránh nhận nhầm dữ liệu.

## 10. Idempotency cho provision

Platform có thể retry cùng request khi response bị mất. Broker cần phân biệt retry cùng ý định với request mới có payload khác.

Một request fingerprint có thể được tính từ instance ID, service ID, plan ID, parameters đã canonicalize và context cần thiết theo OSB contract.

Quy tắc:

- Cùng instance ID và cùng fingerprint: trả trạng thái/kết quả hiện có theo contract.
- Cùng instance ID nhưng fingerprint khác khi operation đang chạy: trả conflict phù hợp.
- Instance đã ACTIVE với cùng plan/request semantics: không tạo database thứ hai.
- Provider đã tạo database nhưng broker chưa lưu external ID: reconcile theo deterministic physical name và ownership metadata.

Không dùng password hoặc raw secret trong fingerprint/log. Với parameters nhạy cảm, fingerprint cần dùng HMAC hoặc cách xử lý bảo vệ phù hợp thay vì hash đơn giản có thể bị dò ngược từ giá trị yếu.

## 11. Tạo binding và cấp credential

Binding tạo một principal riêng cho mỗi binding ID:

1. Xác nhận instance ACTIVE và service/plan bindable.
2. Kiểm tra binding ID chưa được dùng với request khác.
3. Tạo role login riêng với password ngẫu nhiên đủ mạnh.
4. Cấp CONNECT trên đúng database.
5. Cấp USAGE/CREATE hoặc quyền schema cần thiết theo contract dịch vụ.
6. Cấp quyền bảng/sequence hiện có và default privileges cho object tạo về sau nếu cần.
7. Giới hạn connection và quyền role theo plan.
8. Lưu binding record và secret reference an toàn.
9. Trả credentials trong binding response theo OSB contract.

Ví dụ credentials response:

~~~json
{
  "hostname": "postgres.internal.example",
  "port": 5432,
  "database": "svc_4h6k...",
  "username": "bind_8m2p...",
  "password": "<generated-secret>",
  "sslmode": "verify-full"
}
~~~

Đây là hình dạng minh họa; response model thực tế phải theo Spring Cloud Open Service Broker và contract của platform. Không trả admin credential, internal management URL hoặc quyền superuser.

Không ghi password vào log, trace, exception, metric, tag provider hoặc audit event. Nếu cần lưu để trả lại credentials khi request bind lặp, mã hóa bằng KMS/secret manager và lưu reference; chỉ đọc secret trong luồng được cấp quyền. Nếu contract và platform cho phép tạo lại credential mới, có thể thiết kế rotation rõ ràng thay vì lưu plaintext.

### Quyền PostgreSQL cần cấp

Không cấp SUPERUSER, CREATEDB hoặc CREATEROLE cho binding role. Cấp quyền tối thiểu theo use case:

- CONNECT vào database tương ứng.
- USAGE trên schema cần truy cập.
- SELECT/INSERT/UPDATE/DELETE trên bảng phù hợp.
- USAGE/SELECT/UPDATE trên sequence nếu ứng dụng cần.
- Default privileges cho object mới nếu cần và được quản lý bởi owner role chuyên biệt.

Quyền CREATE trên schema có thể cho phép consumer tạo object; chỉ cấp nếu service contract yêu cầu. Tách schema owner/migration role khỏi runtime binding role để consumer không thể thay đổi quyền hoặc xóa object ngoài phạm vi.

## 12. Unbind và thu hồi quyền truy cập

Unbind cần thu hồi quyền của đúng binding:

1. Xác định binding record và physical role.
2. Chặn việc cấp credential mới cho binding đang unbinding.
3. Revoke quyền database/schema/table/sequence đã cấp.
4. Revoke CONNECT hoặc cập nhật policy để role không thể mở kết nối mới.
5. Terminate session hiện tại của role nếu chính sách yêu cầu thu hồi ngay.
6. Xóa grant/ownership còn lại theo đúng database scope.
7. Drop role sau khi không còn dependency.
8. Đánh dấu binding đã unbound và giải phóng binding quota.

PostgreSQL role là đối tượng ở cấp cluster, còn grant/schema object thuộc database cụ thể. Adapter phải thu hồi quyền trong đúng database và kiểm tra role không còn sở hữu object trước DROP ROLE. Không dùng DROP OWNED BY một cách rộng rãi trên cluster vì có thể ảnh hưởng object ngoài phạm vi binding.

Unbind phải idempotent. Nếu role đã bị xóa, lần gọi lại có thể hoàn tất thành công theo state đã xác minh. Nếu provider timeout sau revoke, truy vấn role/grant/session để xác định kết quả trước khi lặp.

## 13. Update service instance

Chỉ công bố plan update capability khi broker có thể thực hiện update và xử lý các giới hạn tương thích. Với PostgreSQL logical database, một số thuộc tính có thể cập nhật:

- Connection budget/connection limit theo instance hoặc plan.
- Statement timeout hoặc policy runtime nếu broker quản lý được.
- Feature flags như backup schedule hoặc maintenance window nếu provider hỗ trợ.
- Metadata và cấu hình được lưu ở broker.

Một số thay đổi như storage capacity có thể thuộc volume/cluster bên dưới và không thể thực hiện bằng một câu lệnh ALTER DATABASE đơn giản. Thay đổi plan không tự động làm tăng disk quota. Broker phải xác định rõ thuộc tính nào có thể cập nhật đồng bộ, thuộc tính nào cần async và thuộc tính nào không hỗ trợ.

Update workflow:

1. Đọc instance version và current plan.
2. Validate target plan và parameters.
3. Kiểm tra compatibility, quota và active bindings.
4. Tạo update operation với expected version.
5. Gọi provider adapter.
6. Verify actual settings.
7. Commit plan/configuration mới và quota adjustment.
8. Hoàn tất operation.

Nếu hai update đồng thời cùng dùng một version, chỉ một update được commit; update còn lại nhận conflict hoặc được xếp hàng theo policy. Không ghi plan mới trước khi provider xác nhận thay đổi cần thiết.

## 14. Deprovision và xóa database an toàn

Deprovision phải xác minh instance ownership và trạng thái trước khi xóa:

1. Xác nhận instance thuộc broker và đúng provider account/cluster.
2. Kiểm tra binding còn active; theo policy có thể yêu cầu unbind trước.
3. Chuyển instance sang DEPROVISIONING và tạo operation bền vững.
4. Ngăn bind/update mới trên instance.
5. Kiểm tra backup/retention policy và yêu cầu giữ dữ liệu nếu có.
6. Terminate connection nếu policy yêu cầu.
7. Drop database theo physical identifier đã lưu.
8. Verify database không còn tồn tại.
9. Thu hồi mapping/secret liên quan.
10. Giải phóng committed quota và đánh dấu DEPROVISIONED.

Không drop database chỉ dựa trên tên do caller gửi. Dùng external resource ID/physical identifier trong broker state và kiểm tra ownership metadata. Nếu database không tìm thấy, xác minh đúng cluster và region trước khi kết luận đã xóa.

Nếu deprovision timeout sau DROP DATABASE, worker retry phải kiểm tra database đã biến mất chưa. Nếu đã mất và mapping xác nhận đúng instance, tiếp tục hoàn tất state; không xem NOT_FOUND là lỗi terminal trong một thao tác cleanup lặp lại.

## 15. State model và dữ liệu cần lưu

Một mô hình dữ liệu tối thiểu:

| Entity | Field quan trọng |
|---|---|
| ServiceInstance | instance_id, tenant_ref, service_id, plan_id, status, external_database_id, version |
| Binding | binding_id, instance_id, role_name, secret_ref, status |
| Operation | operation_id, instance_id, type, status, attempt, lease, checkpoint, last_error |
| QuotaReservation | operation_id, tenant_ref, resource_type, amount, status |
| ProviderMapping | provider_account, cluster_ref, database_name, broker_instance_id |
| OutboxEvent | event_id, operation_id, event_type, publish_status |

State transition phải có guard:

- PROVISIONING -> ACTIVE hoặc FAILED.
- ACTIVE -> UPDATING -> ACTIVE hoặc FAILED theo compensation policy.
- ACTIVE -> DEPROVISIONING -> DEPROVISIONED.
- ACTIVE -> BINDING -> ACTIVE; binding có lifecycle riêng.
- DEPROVISIONING chặn bind/update mới.

Không lưu password plaintext trong Binding entity. Lưu secret reference hoặc ciphertext có envelope encryption. Có retention policy cho operation/audit records và tombstone để nhận diện request lặp sau deprovision.

## 16. Xử lý lỗi và retry

Phân loại lỗi provider để quyết định retry:

| Lỗi | Hành vi |
|---|---|
| Connection timeout trước khi gửi SQL | Retry có backoff |
| Timeout sau CREATE DATABASE | Describe database trước khi retry |
| Database đã tồn tại và ownership khớp | Tiếp tục workflow idempotent |
| Database tồn tại nhưng không xác định owner | Conflict/manual investigation |
| Permission denied | Không retry liên tục; kiểm tra admin role/config |
| Too many connections | Backoff và giới hạn worker concurrency |
| Invalid plan/parameters | Terminal validation error |
| Deadlock/serialization failure | Retry transaction ngắn theo policy |
| Cluster unavailable | Retry có giới hạn, giữ operation/reservation |

Dùng exponential backoff có jitter và giới hạn attempt. Với thao tác đã có side effect, retry phải bắt đầu bằng reconcile. Không giữ transaction database broker mở trong lúc chờ PostgreSQL provider call.

## 17. Kiểm thử với PostgreSQL thật

Mock provider adapter hữu ích cho unit test application service, nhưng không chứng minh SQL, role grant và database behavior đúng. Dùng Testcontainers PostgreSQL hoặc một database test cô lập để kiểm thử tích hợp.

| Nhóm | Kiểm tra |
|---|---|
| Catalog contract | Service/plan IDs, bindable, schemas và metadata |
| Provision | Database được tạo đúng tên nội bộ và encoding |
| Idempotency | Provision retry không tạo database thứ hai |
| Binding | Role riêng được tạo, credential kết nối được |
| Least privilege | Binding role không có superuser/CREATEROLE/CREATEDB |
| Isolation | Binding của instance A không truy cập database B |
| Unbind | Role bị revoke và không mở được kết nối mới |
| Update | Chỉ các thuộc tính được hỗ trợ được thay đổi |
| Deprovision | Database được xóa, retry vẫn hoàn tất an toàn |
| Timeout recovery | Provider side effect đã xảy ra nhưng broker chưa checkpoint |
| Quota | Concurrent provision không vượt limit |
| Security | SQL identifier injection, secret logging và TLS validation |
| OSB HTTP | Status/body cho sync, async, conflict và error |

Ví dụ integration test khái niệm:

~~~java
@Test
void provisionCreatesDatabaseAndRetryIsIdempotent() {
    ProvisionSpec spec = provisionSpec("instance-42");

    StepVerifier.create(provider.provision(spec))
            .assertNext(resource ->
                    assertThat(resource.databaseName())
                            .startsWith("svc_"))
            .verifyComplete();

    StepVerifier.create(provider.provision(spec))
            .assertNext(resource ->
                    assertThat(resource.databaseName())
                            .isEqualTo(expectedDatabaseName(spec)))
            .verifyComplete();

    assertThat(countDatabase(expectedDatabaseName(spec)))
            .isEqualTo(1);
}
~~~

Đây là pseudocode; các helper và record accessor phụ thuộc implementation. Test phải kiểm tra cả kết quả provider lẫn số lượng database thực tế.

Test binding cần kết nối bằng credential được trả về, chạy một câu SELECT hợp lệ, sau đó thử truy cập database khác hoặc thực hiện lệnh quản trị và xác nhận bị từ chối. Không chỉ kiểm tra response JSON có trường password.

## 18. Kiểm thử OSB contract qua HTTP

Ngoài provider integration test, gọi broker endpoint như platform thật:

- GET /v2/catalog trả đúng service và plans.
- PUT /v2/service_instances/{instance_id} provision sync/async theo capability.
- GET /v2/service_instances/{instance_id}/last_operation trả state phù hợp.
- PUT /v2/service_instances/{instance_id}/service_bindings/{binding_id} trả credentials.
- DELETE binding revoke role.
- PATCH instance chỉ được hỗ trợ nếu API version và framework contract cho phép.
- DELETE instance deprovision theo semantics OSB.

Dùng WebTestClient cho reactive web stack hoặc HTTP test client phù hợp với cấu hình Spring. Xác minh API version header, status, JSON body, operation key và error code. Không giả định endpoint PATCH/update tồn tại ở mọi OSB API version; phải kiểm tra phiên bản framework và contract broker hỗ trợ.

## 19. Chạy local bằng container

Môi trường local có thể gồm:

- Một PostgreSQL container làm provider cluster.
- Một PostgreSQL database riêng cho broker metadata nếu cần.
- Broker Spring Boot application.
- Secret/config cho admin connection.
- Test runner dùng Testcontainers.

Các bước chạy:

1. Khởi động PostgreSQL test cluster.
2. Tạo admin role giới hạn quyền theo adapter.
3. Cấu hình broker kết nối qua private Docker network.
4. Chạy migration cho broker state store.
5. Khởi động broker và kiểm tra health/readiness.
6. Gọi GET catalog.
7. Gửi provision, đợi operation hoàn tất.
8. Dùng psql hoặc client kiểm tra database vật lý.
9. Gửi bind, dùng credentials kết nối và kiểm tra quyền.
10. Gửi unbind/deprovision, xác minh role/database đã được thu hồi.

Không expose PostgreSQL admin port ra public network. Nếu cần publish port cho local developer, bind vào loopback và dùng secret riêng cho môi trường local.

## 20. Triển khai trên Kubernetes

Khi triển khai:

- Chạy broker HTTP và worker riêng nếu cần scale độc lập.
- Lưu admin credential trong secret manager hoặc Kubernetes Secret được mã hóa và giới hạn RBAC.
- Dùng NetworkPolicy chỉ cho broker/worker kết nối PostgreSQL provider.
- Cấu hình TLS verify-full và CA trust phù hợp.
- Đặt resource requests/limits và connection pool giới hạn.
- Có readiness/liveness probes phù hợp.
- Worker ngừng claim operation mới khi graceful shutdown.
- Operation/outbox được lưu bền vững để pod restart không mất việc.
- Database migration theo expand-and-contract nếu worker cũ/mới chạy đồng thời.
- Có backup/restore drill và quy trình rotate admin/binding credentials.

Nếu PostgreSQL provider ở ngoài cluster, dùng private endpoint/VPN/peering và egress policy. Không mở rộng network access chỉ để xử lý một lỗi kết nối tạm thời.

## 21. Observability và vận hành

Theo dõi các chỉ số:

- Provision/update/deprovision duration và success rate.
- Số operation PENDING/RUNNING/RETRY_WAIT và tuổi operation lớn nhất.
- Số database/role được tạo và thu hồi.
- Số binding active theo plan/tenant scope.
- PostgreSQL connection count, pool saturation, query latency và error rate.
- Quota committed/reserved và quota rejection.
- Provider timeout, permission denied, deadlock và too many connections.
- Số orphan database/role phát hiện qua reconciliation.

Log nên có correlation ID, instance ID, binding ID, operation ID và provider request reference. Không log password, full connection URI có secret hoặc raw admin configuration. Metric label không nên chứa instance ID/tenant ID có cardinality cao.

Reconciliation định kỳ so sánh broker mappings với PostgreSQL database/role inventory. Không tự drop database/role chỉ vì không tìm thấy mapping trong một lần scan; xác minh ownership, grace period và operation history trước cleanup.

## 22. Mở rộng provider adapter sang Redis

Nếu chọn Redis cache thay cho PostgreSQL, giữ nguyên OSB lifecycle/application service và thay phần provider adapter:

| PostgreSQL | Redis |
|---|---|
| Database per instance | Key namespace hoặc Redis database/cluster theo isolation policy |
| Role per binding | ACL user per binding |
| GRANT privileges | ACL command/key patterns |
| Database connection credentials | Redis endpoint, username, password, TLS |
| Database size/connection policy | Memory, eviction, connection và throughput policy |
| DROP DATABASE | Xóa namespace hoặc thu hồi dedicated cache resource |
| PostgreSQL inventory | Redis keyspace, ACL user và cluster inventory |

Redis logical database index không tự tạo security boundary mạnh giữa tenants. Với isolation nghiêm ngặt, cân nhắc ACL key patterns, dedicated instance/cluster hoặc managed Redis database phù hợp. Không trả quyền admin/default user cho binding.

Redis provider adapter vẫn cần idempotency, secret rotation, revoke ACL user, quota, operation state và reconciliation. Các phần OSB protocol, catalog, plan validation, operation store, outbox và observability có thể tái sử dụng.

## 23. Tiêu chí nghiệm thu capstone

Capstone được xem là hoàn thành khi có thể trình diễn:

- Platform lấy được catalog với service và plans ổn định.
- Provision tạo đúng một database logic cho một instance ID.
- Retry cùng request không tạo database thứ hai.
- Operation async được lưu bền vững và last operation phản ánh tiến độ.
- Binding tạo role riêng và credentials kết nối được tới đúng database.
- Binding A không truy cập được database B.
- Unbind thu hồi quyền và credential không còn dùng được theo policy.
- Update chỉ áp dụng thuộc tính provider thực sự hỗ trợ.
- Deprovision xóa database đúng owner và giải phóng quota sau verify.
- Worker restart/timeout không làm mất operation hoặc tạo resource trùng.
- Admin credential không xuất hiện trong log hoặc response.
- Test suite có unit, provider integration và OSB HTTP contract tests.
- Có tài liệu triển khai, backup, secret rotation và troubleshooting cơ bản.

## 24. Những lỗi dễ gặp khi tích hợp provider thật

- Dùng superuser PostgreSQL làm credential của mọi binding.
- Dùng databaseName từ request để ghép SQL identifier.
- Nghĩ CREATE DATABASE có thể rollback trong transaction thông thường.
- Tạo role nhưng không thiết kế quy trình revoke grant và session.
- Không cấp default privileges nên binding mới không truy cập được bảng tạo sau đó.
- Cấp quyền CREATE/owner quá rộng cho runtime user.
- Cho rằng database logic riêng tương đương cluster isolation.
- Công bố hard storage quota nhưng không có cơ chế enforce.
- Retry CREATE DATABASE sau timeout mà không describe resource.
- Trả 202 trước khi operation/outbox được commit.
- Lưu password plaintext hoặc ghi credential vào log.
- Xóa database theo tên hiển thị thay vì external mapping đã xác minh.
- Test chỉ mock provider nên không phát hiện SQL/grant sai.
- Cho phép Redis logical DB index thay thế ACL/isolation policy.

## Kết luận

Capstone tích hợp PostgreSQL giúp kiểm chứng toàn bộ vòng đời service broker: catalog công bố plan, provision tạo database, binding cấp role riêng, unbind thu hồi quyền, update thay đổi cấu hình được hỗ trợ và deprovision xóa tài nguyên đúng owner. Thiết kế cần provider adapter riêng, operation/outbox bền vững, quota reservation, idempotency, secret management và reconciliation để xử lý timeout hoặc worker restart an toàn. PostgreSQL logical database per instance là cách triển khai thực tế để học luồng end-to-end, nhưng không thay thế cluster isolation và hard storage quota nếu sản phẩm cần các cam kết đó. Khi chuyển sang Redis, giữ nguyên OSB application flow và thay provider adapter bằng ACL/keyspace lifecycle với cùng yêu cầu về isolation, credential và đối soát.
