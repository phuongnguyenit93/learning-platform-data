# Kiểm thử phân quyền nhiều khách hàng và không rò rỉ credentials

## Bối cảnh

Một Spring Cloud Service Broker thường phục vụ nhiều khách hàng, tổ chức hoặc platform trên cùng một ứng dụng. Mỗi khách hàng có thể tạo service instance, binding, operation và credentials riêng. Broker phải bảo đảm mọi request chỉ đọc hoặc thay đổi tài nguyên thuộc phạm vi mà caller được phép quản lý. Đồng thời, username, password, token, connection URI và secret reference của một khách hàng không được xuất hiện trong response, log, cache, trace hay workload của khách hàng khác.

Lỗi phân quyền nhiều khách hàng thường không nằm ở một endpoint đơn lẻ. Một request provision có thể được xác thực đúng nhưng worker chạy nền lại không giữ tenant context. Repository có thể lọc instance theo ID nhưng quên platform scope. Cache có thể dùng instance ID làm key nên trả dữ liệu của tenant trước. Binding endpoint có thể kiểm tra instance nhưng không kiểm tra binding ID. Log exception có thể vô tình ghi nguyên provider response chứa credentials.

Vì vậy, kiểm thử bảo mật phải bao phủ toàn bộ luồng:

1. Xác thực platform và người dùng.
2. Xác định tenant/platform scope từ danh tính đã xác thực.
3. Kiểm tra quyền trên service, instance, operation và binding.
4. Truy vấn repository theo tenant scope.
5. Gọi provider và secret manager trong đúng phạm vi.
6. Trả response OSB chỉ chứa dữ liệu của consumer được phép.
7. Truyền tenant context an toàn qua queue, worker và cache.
8. Ghi log, audit và telemetry mà không làm lộ credentials.

Bài học này tập trung vào cách xây dựng test có thể phát hiện truy cập chéo tenant (cross-tenant access), IDOR/BOLA, giả mạo tenant context và rò rỉ credentials trong service broker triển khai theo Open Service Broker API (OSB API).

## 1. Mô hình tenant và ranh giới tin cậy

Trước khi viết test, cần xác định chính xác tenant trong hệ thống. Một broker có thể phục vụ:

- Nhiều Cloud Foundry foundation hoặc platform.
- Nhiều organization trong một foundation.
- Nhiều space trong một organization.
- Nhiều namespace hoặc workload trên Kubernetes.
- Nhiều tài khoản provider hoặc project cloud.
- Nhiều khách hàng độc lập trên cùng database và broker deployment.

Không phải hệ thống nào cũng cần mọi cấp. Điều quan trọng là định nghĩa khóa phạm vi tài nguyên và kiểm tra quyền nhất quán ở mọi lớp.

### Phạm vi định danh

Một mô hình tham khảo:

| Định danh | Ý nghĩa | Dùng để |
|---|---|---|
| platform_id | Platform/foundation đã xác thực | Phân biệt các platform gọi cùng broker |
| tenant_id | Khách hàng hoặc tổ chức trong platform | Phân vùng dữ liệu và policy |
| organization_id | Organization do platform quản lý | Kiểm soát phạm vi tổ chức |
| space_id | Space hoặc môi trường con | Giới hạn instance/consumer theo space |
| instance_id | Service instance theo OSB API | Nhận diện instance trong platform scope |
| binding_id | Một binding của instance | Nhận diện credentials/quyền của consumer |
| operation_id | Một thao tác async | Theo dõi provision/update/deprovision/binding |
| provider_resource_id | Tài nguyên thực tế phía provider | Gọi API provider và reconcile |

Nếu OSB instance ID chỉ duy nhất trong một platform, khóa nghiệp vụ của broker nên là cặp hoặc bộ khóa gồm platform scope và instance ID, ví dụ **(platform_id, instance_id)**. Nếu hệ thống xác định tenant ở mức organization/space thì có thể cần thêm tenant hoặc scope ID. Không giả định một ID do caller gửi luôn duy nhất toàn hệ thống.

### Nguồn tenant đáng tin cậy

Tenant scope phải được suy ra từ danh tính đã xác thực và mapping do broker quản lý. Không dùng một header tùy ý như X-Tenant-ID hoặc trường tenant trong JSON body làm bằng chứng duy nhất để cấp quyền.

Với Cloud Foundry, request có thể chứa context mô tả foundation, organization hoặc space. Context giúp broker gắn tài nguyên với phạm vi platform, nhưng context không tự nó là credential xác thực. Broker cần xác thực caller/platform theo cấu hình broker registration, sau đó kiểm tra context theo policy và mapping đã tin cậy.

Với Kubernetes, namespace trong request cũng không phải bằng chứng caller có quyền trên namespace đó. Broker phải xác định namespace từ platform/tenant đã xác thực và policy server-side. Service account của broker chỉ nên có quyền cần thiết trên những namespace được phép.

### Threat model

| Tác nhân hoặc lỗi | Hành vi cần kiểm tra |
|---|---|
| Caller tenant A | Thử đọc, bind, update hoặc xóa instance của tenant B |
| Caller đã xác thực nhưng thiếu role | Gọi endpoint quản trị hoặc lấy credentials không thuộc quyền |
| Caller giả mạo tenant | Gửi header/body/context khai tenant khác |
| Request retry | Dùng lại ID để truy cập resource của tenant khác hoặc gây side effect trùng |
| Worker async | Nhận job thiếu hoặc sai tenant scope |
| Cache dùng chung | Trả dữ liệu/credentials của request trước |
| Provider adapter | Gọi nhầm account, project, namespace hoặc resource ID |
| Logging/observability | Ghi password, token, URI hoặc provider response nhạy cảm |
| Operator/administrator | Truy cập cross-tenant vượt quyền hỗ trợ được cấp |

## 2. Nguyên tắc phân quyền cần kiểm thử

Một request được phép xử lý khi đồng thời thỏa mãn các điều kiện:

1. Caller đã xác thực.
2. Caller có quyền thực hiện action tương ứng.
3. Resource thuộc platform/tenant scope của caller hoặc caller có quyền hỗ trợ đặc biệt được audit.
4. Resource đang ở trạng thái cho phép action.
5. Các tham số và quan hệ instance-binding-operation nhất quán.

Không nên chỉ kiểm tra role chung như BROKER_USER. Role cho phép gọi API không đồng nghĩa với quyền sở hữu mọi instance.

### Authentication và authorization

Authentication trả lời caller là ai. Authorization trả lời caller đó được làm gì trên resource cụ thể.

Ví dụ:

| Caller | Action | Resource | Kết quả |
|---|---|---|---|
| Platform A đã xác thực | GET instance | Instance A | Cho phép nếu endpoint được hỗ trợ |
| Platform A đã xác thực | DELETE instance | Instance B | Từ chối |
| Platform A đã xác thực | PUT binding | Instance A, binding mới | Cho phép nếu offering bindable và policy hợp lệ |
| Platform A đã xác thực | GET credentials | Binding B | Từ chối |
| Operator support có scope | Read metadata instance B | Tenant B được phân công | Cho phép và ghi audit |
| Caller không xác thực | Bất kỳ action bảo vệ nào | Bất kỳ resource | Từ chối |

### Kiểm tra ownership tại service layer

Không chỉ bảo vệ controller bằng annotation role. Application service phải nhận tenant scope đã xác thực và truy vấn resource theo scope:

~~~java
public ServiceInstance requireInstance(
        TenantScope scope,
        String instanceId) {

    return instanceRepository
            .findByPlatformIdAndTenantIdAndInstanceId(
                    scope.platformId(),
                    scope.tenantId(),
                    instanceId)
            .orElseThrow(ResourceNotFoundException::new);
}
~~~

Đây là ví dụ về ý tưởng truy vấn. Tên repository method phụ thuộc implementation. Điểm cần giữ là tenant scope đi vào điều kiện truy vấn ngay từ đầu, thay vì tìm instance toàn cục rồi chỉ kiểm tra sau khi đã lấy dữ liệu nhạy cảm.

Với resource không tồn tại và resource thuộc tenant khác, broker thường nên trả cùng một loại response bên ngoài để tránh tiết lộ sự tồn tại của tài nguyên. Chọn status/error theo endpoint và contract OSB đang triển khai; test phải bảo đảm không có thông tin phân biệt tenant B tồn tại hay không.

## 3. Ma trận kiểm thử truy cập

Xây dựng ma trận trước khi viết test giúp tránh bỏ sót endpoint:

| Tài nguyên | Tenant sở hữu | Tenant khác | Platform admin | Operator support |
|---|---|---|---|---|
| Catalog công khai trong platform | Read | Read nếu catalog được chia sẻ | Read | Read |
| Service instance | Theo quyền | Deny | Theo policy | Theo scope được cấp |
| Operation | Theo instance owner | Deny | Theo policy | Theo scope được cấp |
| Binding metadata | Theo instance và binding owner | Deny | Theo policy | Theo scope được cấp |
| Binding credentials | Chỉ consumer được phép | Deny | Không mặc định được đọc secret | Chỉ khi có quyền break-glass được audit |
| Provider resource reference | Theo instance owner | Deny | Theo policy | Hạn chế và audit |
| Audit record | Theo tenant/policy | Deny | Theo policy | Theo scope được cấp |

Catalog có thể được chia sẻ giữa nhiều tenant, nhưng metadata nội bộ, giá tùy chỉnh hoặc offering bị giới hạn quyền có thể cần lọc theo platform/tenant. Không giả định catalog luôn công khai hoặc luôn riêng tư; test theo policy thật của broker.

## 4. Thiết kế test fixture nhiều tenant

Test phải có dữ liệu của ít nhất hai tenant độc lập để phát hiện lỗi truy cập chéo. Không dùng một tenant duy nhất rồi thay đổi ID trong từng test, vì cách đó không chứng minh được isolation.

Fixture mẫu:

| Dữ liệu | Tenant A | Tenant B |
|---|---|---|
| platform_id | cf-prod | cf-prod |
| tenant_id | retail | finance |
| instance_id | db-orders-01 | db-ledger-01 |
| binding_id | orders-api | ledger-worker |
| operation_id | op-retail-100 | op-finance-200 |
| provider_resource_id | provider-db-a | provider-db-b |
| username | orders_user | ledger_user |
| secret | secret-A-test | secret-B-test |

Nên có thêm tình huống hai platform cùng dùng một instance ID:

| Dữ liệu | Platform A | Platform B |
|---|---|---|
| platform_id | cf-east | cf-west |
| instance_id | shared-id-01 | shared-id-01 |
| tenant_id | tenant-east | tenant-west |
| provider resource | resource-east | resource-west |

Test này phát hiện repository/cache sử dụng riêng instance ID làm khóa toàn cục. Mọi fixture secret phải là giá trị giả, chỉ dùng trong test, không lấy từ môi trường production hoặc tài khoản cloud thật.

### Factory tạo fixture

Có thể dùng factory để tạo dữ liệu rõ ràng:

~~~java
TenantFixture retail = tenantFixture("cf-prod", "retail")
        .instance("db-orders-01")
        .binding("orders-api")
        .credentials("orders_user", "secret-A-test")
        .build();

TenantFixture finance = tenantFixture("cf-prod", "finance")
        .instance("db-ledger-01")
        .binding("ledger-worker")
        .credentials("ledger_user", "secret-B-test")
        .build();
~~~

Đây là pseudocode fixture; test factory thực tế có thể dùng builder, Test Data Builder hoặc repository setup. Mỗi test nên tạo dữ liệu cô lập và dọn dẹp sau khi chạy.

## 5. Kiểm thử authorization tại HTTP boundary

Các test controller cần xác minh request không vượt qua được security filter khi thiếu hoặc sai credential. Với Spring MVC có thể dùng MockMvc; với WebFlux dùng WebTestClient. Nên có ít nhất một nhóm integration test chạy qua security configuration thật, không chỉ gọi method controller trực tiếp.

Ví dụ kiểm thử Basic Authentication nếu broker đang dùng HTTP Basic:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class BrokerAuthenticationIT {

    @Autowired
    MockMvc mvc;

    @Test
    void rejectsRequestWithoutBrokerCredentials() throws Exception {
        mvc.perform(get("/v2/catalog")
                        .header("X-Broker-API-Version", "2.17"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void rejectsInvalidBrokerCredentials() throws Exception {
        mvc.perform(get("/v2/catalog")
                        .with(httpBasic("unknown-platform", "wrong-secret"))
                        .header("X-Broker-API-Version", "2.17"))
                .andExpect(status().isUnauthorized());
    }
}
~~~

Ví dụ giả định security configuration của ứng dụng dùng HTTP Basic và endpoint catalog được bảo vệ. Nếu hệ thống dùng mTLS, OAuth2 client credentials hoặc cơ chế khác, thay helper xác thực tương ứng và giữ nguyên mục tiêu kiểm thử.

### Không bỏ qua filter trong integration test

Một lỗi phổ biến là dùng @WebMvcTest hoặc mock controller mà không import security configuration. Test có thể pass dù production endpoint không có authorization. Nên chia:

- Unit test cho policy/service method.
- MVC/WebFlux slice test có security filter phù hợp.
- Integration test khởi động ứng dụng với authentication provider và repository test thật.
- Contract test xác nhận status/body OSB.

Test không nên vô hiệu hóa security filter để làm cho request dễ chạy. Nếu cần helper đăng nhập, helper phải đi qua cùng cơ chế xác thực mà production dùng.

## 6. Kiểm thử IDOR/BOLA giữa tenant

IDOR (Insecure Direct Object Reference) hoặc BOLA (Broken Object Level Authorization) xảy ra khi API chấp nhận ID resource do caller gửi nhưng không kiểm tra caller có quyền trên resource đó.

Với OSB API, các ID cần kiểm tra gồm instance ID, binding ID và operation reference. Người tấn công có thể đoán hoặc biết ID từ log, ticket, tên resource hay request khác. ID khó đoán không thay thế authorization.

### Test đọc instance chéo tenant

1. Tạo instance A và instance B trong hai tenant.
2. Xác thực caller thuộc tenant A.
3. Gửi request đọc instance ID của tenant B.
4. Xác nhận response không chứa plan, parameters, provider reference, state nội bộ hoặc metadata của B.
5. Xác nhận repository không trả dữ liệu B cho application service.

Ví dụ service-level test:

~~~java
@Test
void tenantCannotReadAnotherTenantsInstance() {
    var scopeA = new TenantScope("cf-prod", "retail");
    var instanceB = fixture.instance("cf-prod", "finance", "db-ledger-01");

    when(repository.findByPlatformIdAndTenantIdAndInstanceId(
            "cf-prod", "retail", "db-ledger-01"))
            .thenReturn(Optional.empty());

    assertThrows(ResourceNotFoundException.class,
            () -> service.requireInstance(scopeA, "db-ledger-01"));

    verify(providerClient, never()).describe(instanceB.providerResourceId());
}
~~~

Test này minh họa kiểm tra ở application layer. Cần có thêm HTTP integration test để xác minh response OSB thực tế và không có dữ liệu B trong body.

### Test update/deprovision chéo tenant

Đây là test có side effect nên phải kiểm tra provider không bị gọi:

~~~java
@Test
void tenantCannotDeprovisionAnotherTenantsInstance() {
    var scopeA = new TenantScope("cf-prod", "retail");

    when(repository.findByPlatformIdAndTenantIdAndInstanceId(
            "cf-prod", "retail", "db-ledger-01"))
            .thenReturn(Optional.empty());

    assertThrows(ResourceNotFoundException.class,
            () -> service.deprovision(scopeA, "db-ledger-01"));

    verify(providerClient, never()).delete(any());
    verify(operationRepository, never()).create(any());
}
~~~

Áp dụng cùng nguyên tắc cho PATCH update, create binding, delete binding, fetch operation và fetch instance. Với mọi request trái quyền, xác nhận không có provider call, không tạo operation và không thay đổi database.

### Không làm lộ sự tồn tại của resource

So sánh response khi:

- ID không tồn tại.
- ID tồn tại nhưng thuộc tenant khác.

Nếu policy chọn che giấu resource ngoài scope, hai trường hợp cần có status, error code và description tương đương. Không trả thông báo như "instance belongs to finance tenant" hoặc "resource exists but access denied" cho caller không có quyền.

## 7. Kiểm thử giả mạo tenant context

Caller có thể gửi header hoặc JSON body nhằm chuyển scope:

~~~http
X-Tenant-ID: finance
X-Organization-ID: org-finance
~~~

Hoặc body có trường:

~~~json
{
  "context": {
    "organization_guid": "org-finance",
    "space_guid": "space-finance"
  }
}
~~~

Nếu tenant scope đã được xác định từ platform credential, request không được phép tự đổi scope bằng header tùy ý. Với OSB context, broker cần kiểm tra nó thuộc platform đã xác thực và mapping hợp lệ trước khi dùng cho policy. Không dùng context như một cơ chế authentication độc lập.

Test cần bao gồm:

- Tenant A gửi X-Tenant-ID của B.
- Tenant A thay organization/space trong context.
- Tenant A gửi platform ID của B trong body.
- Caller không xác thực gửi context hợp lệ của tenant B.
- Caller hợp lệ gửi context bị thiếu hoặc không khớp với platform mapping.
- Header trùng lặp hoặc giá trị không hợp lệ gây parser ambiguity.

Kết quả phải là từ chối hoặc bỏ qua trường không đáng tin theo policy đã định nghĩa; tuyệt đối không truy cập dữ liệu tenant B. Test phải xác nhận tenant scope trong service vẫn là tenant A sau khi request được parse.

## 8. Kiểm thử instance ID trùng giữa các platform

Một broker có thể đăng ký với nhiều platform. Nếu hai platform dùng cùng chuỗi instance ID, broker phải phân biệt bằng platform scope.

Test:

1. Tạo platform A với instance ID shared-id-01 và provider resource A.
2. Tạo platform B với cùng instance ID và provider resource B.
3. Gửi deprovision từ platform A.
4. Xác nhận chỉ resource A bị xóa.
5. Gửi GET last_operation từ platform B.
6. Xác nhận operation B không thay đổi.

Kiểm tra unique key database:

~~~sql
CREATE TABLE service_instance (
    platform_id VARCHAR(128) NOT NULL,
    tenant_id VARCHAR(128) NOT NULL,
    instance_id VARCHAR(128) NOT NULL,
    provider_resource_id VARCHAR(256) NOT NULL,
    PRIMARY KEY (platform_id, tenant_id, instance_id)
);
~~~

Schema là ví dụ. Cần chọn khóa chính theo tenant model thật. Không tạo unique constraint chỉ trên instance_id nếu ID chỉ duy nhất trong platform scope.

## 9. Kiểm thử binding và credentials

Binding là một điểm nhạy cảm vì response có thể chứa password, token, URI hoặc certificate. Test phải chứng minh:

- Chỉ caller được phép mới tạo binding cho instance.
- Binding ID thuộc đúng instance và tenant.
- Một binding không thể bị truy cập bằng cách thay instance ID hoặc binding ID.
- Credentials của binding A không xuất hiện trong response binding B.
- Retry create binding không sinh thêm principal ngoài ý muốn.
- Delete binding thu hồi quyền tại provider và secret store.
- Binding đã bị revoke không thể dùng credential cũ để truy cập provider.

### Test không trả credentials của tenant khác

~~~java
@Test
void bindingResponseContainsOnlyAuthorizedBindingCredentials() {
    var scopeA = new TenantScope("cf-prod", "retail");
    var bindingA = binding("db-orders-01", "orders-api",
            "orders_user", "secret-A-test");

    when(bindingService.create(scopeA, "db-orders-01", "orders-api"))
            .thenReturn(bindingA);

    var response = bindingController.create(
            scopeA, "db-orders-01", "orders-api");

    assertThat(response.credentials().get("username"))
            .isEqualTo("orders_user");
    assertThat(response.credentials().get("password"))
            .isEqualTo("secret-A-test");
    assertThat(response.toString()).doesNotContain("secret-B-test");
}
~~~

Trong test thực tế, tránh gọi controller trực tiếp nếu mục tiêu là HTTP serialization. Gửi request qua MockMvc/WebTestClient, parse JSON response rồi kiểm tra chính xác các trường credentials. Đoạn mã trên chỉ minh họa kiểm tra nội dung ở service boundary.

### Kiểm thử binding IDOR

Thử các cặp sau:

| Instance ID | Binding ID | Caller scope | Kết quả |
|---|---|---|---|
| Instance A | Binding A | Tenant A | Theo policy cho phép |
| Instance B | Binding B | Tenant A | Từ chối |
| Instance A | Binding B | Tenant A | Từ chối nếu binding không thuộc instance A |
| Instance B | Binding A | Tenant B | Từ chối nếu binding A thuộc instance A |
| Instance A | Binding A | Tenant B | Từ chối |

Không chỉ kiểm tra binding ID độc lập. Binding phải được tra cứu cùng instance ID và tenant scope để tránh thay một path segment rồi truy cập binding khác.

### Kiểm thử retry và credential rotation

Khi Platform retry create binding sau timeout, broker cần nhận diện binding đã tồn tại theo scope và request intent. Test phải xác minh:

- Không tạo thêm principal nếu lần đầu đã thành công ở provider.
- Không trả credential của binding khác.
- Có thể trả lại credentials đã lưu an toàn hoặc tái tạo theo policy.
- Nếu secret không thể đọc lại, broker xử lý rotation/recovery theo contract thay vì trả một giá trị rỗng hoặc secret của tenant khác.
- Delete binding lặp không làm ảnh hưởng binding khác.

Khi rotate credential, test phải kiểm tra thời điểm credential mới có hiệu lực, credential cũ bị revoke và workload nhận dữ liệu mới theo cơ chế platform.

## 10. Kiểm thử rò rỉ credentials trong response và lỗi

Credentials có thể rò rỉ ngoài endpoint binding:

- Error response chứa provider exception.
- Validation error in lại toàn bộ request body.
- Debug endpoint hoặc actuator trả environment/configuration.
- Log HTTP ghi response body.
- Trace span ghi attributes chứa password/token.
- Retry/dead-letter message chứa secret dạng rõ.
- Cache hoặc exception message giữ object credentials.

### Test response không chứa secret ngoài ý muốn

Tạo danh sách secret canary chỉ dùng trong test, ví dụ:

~~~text
secret-A-test
token-B-test
postgres://user:password@db.example.test/orders
private-key-test-material
~~~

Gửi request gây lỗi provider, lỗi authorization và lỗi validation. Sau đó kiểm tra:

- Response body không chứa canary ngoài endpoint được phép trả credentials.
- Error description không chứa raw provider response.
- Header response không có Authorization, Set-Cookie hoặc secret header bất ngờ.
- Stack trace không xuất hiện trong body.
- JSON error chỉ chứa trường đã được thiết kế.

Không kiểm tra bằng cách tìm một từ khóa chung như "password" rồi kết luận an toàn. Cần kiểm tra giá trị canary cụ thể và các vị trí rò rỉ phổ biến.

### Safe error mapping

Provider adapter nên chuyển exception thành error category và safe description. Không nối nguyên văn message của SDK vào OSB error response.

~~~java
catch (ProviderAuthorizationException ex) {
    log.warn("Provider authorization failed for operation {}",
            operationId);
    throw new BrokerDependencyException(
            "The broker could not access the service provider.");
}
~~~

Không log ex hoặc stack trace một cách mặc định nếu exception có thể chứa request/response nhạy cảm. Có thể ghi stack trace vào log bảo mật đã mask theo policy, nhưng phải có test xác nhận token/password không xuất hiện.

## 11. Kiểm thử log, trace, metric và audit

Credentials có thể rời khỏi API response qua observability. Cần kiểm tra các sink sau:

| Sink | Dữ liệu được phép | Dữ liệu không được ghi |
|---|---|---|
| Application log | tenant ID, instance ID, operation ID, error category | password, token, private key, Authorization header |
| Audit log | actor, action, resource reference, outcome | secret material |
| Trace/span | operation type, route template, safe correlation ID | credentials, raw request/response body |
| Metric | endpoint, status class, operation type, provider category | secret, tenant-specific high-cardinality ID |
| Queue/dead-letter | operation ID, resource reference, safe metadata | password/token nếu không được mã hóa và kiểm soát |
| Error response | safe description và error code | stack trace, provider response thô |

### Capture log trong test

Có thể dùng appender test hoặc output capture để thu log của một request:

~~~java
@Test
void logsNeverContainBindingSecrets() {
    var secret = "secret-A-test";

    service.createBinding(scopeA, instanceA, bindingA);

    var captured = logCapture.allEventsAsText();
    assertThat(captured).doesNotContain(secret);
    assertThat(captured).doesNotContain("Authorization:");
}
~~~

Đây là pseudocode cho log capture. Cấu hình test cần thu log từ các logger liên quan, bao gồm HTTP client/provider SDK nếu chúng có thể ghi request/response. Test chỉ capture logger của application service có thể bỏ sót log ở tầng transport.

### Metric cardinality

Không đưa password, token, instance ID hoặc tenant ID không giới hạn vào metric label. Ngoài rủi ro lộ dữ liệu, label có cardinality cao làm tăng chi phí và giảm độ ổn định của monitoring. Dùng metric tổng hợp theo endpoint, operation type, provider, status class và error category.

## 12. Kiểm thử tenant context trong asynchronous operation

Provision/update/deprovision có thể trả 202 rồi được xử lý bởi worker. Tenant context phải được lưu cùng operation và được xác thực lại trước mỗi side effect.

Không dựa vào ThreadLocal hoặc request-scoped bean sau khi HTTP request kết thúc. Queue message nên mang operation ID và reference cần thiết; worker tải tenant scope từ bản ghi operation đã lưu, rồi kiểm tra ownership trước khi gọi provider.

Ví dụ message an toàn:

~~~json
{
  "operation_id": "op-retail-100",
  "platform_id": "cf-prod",
  "tenant_id": "retail",
  "instance_id": "db-orders-01",
  "operation_type": "PROVISION"
}
~~~

Không đưa password hoặc raw credentials vào message nếu worker có thể truy xuất secret bằng reference an toàn.

### Test worker không bị đổi tenant

1. Tạo operation của tenant A.
2. Enqueue message có operation ID của A.
3. Cố tình sửa tenant ID trong message thành B.
4. Worker phải tải operation theo ID, so sánh metadata và từ chối mismatch.
5. Xác nhận provider client không được gọi với resource của B.
6. Xác nhận operation A không bị ghi đè trạng thái bởi message giả mạo.

Worker không nên tin tenant ID trong queue message hơn bản ghi operation bền vững. Message có thể bị sửa, replay hoặc được phát lại từ dead-letter queue.

### Test stale job và fencing

Một worker cũ có thể chạy sau khi operation đã bị hủy hoặc thay thế. Test cần xác minh fencing token/version ngăn worker cũ:

- Xóa resource thuộc tenant khác.
- Ghi đè operation mới hơn.
- Cấp lại credentials đã bị revoke.
- Ghi kết quả succeeded sau khi operation đã terminal.

## 13. Kiểm thử repository, database và cache

### Repository query phải có tenant scope

Mỗi method đọc hoặc thay đổi resource cần tenant/platform scope trong điều kiện truy vấn. Test repository với database thật qua Testcontainers có thể phát hiện khác biệt giữa H2 và production database, đặc biệt với index, collation, row-level security và transaction isolation.

Test cần xác minh:

- Find instance theo platform + tenant + instance ID.
- Update/deprovision chỉ ảnh hưởng row trong scope.
- Binding query có đủ instance ID và binding ID.
- Operation query kiểm tra quyền qua instance owner.
- Unique constraint ngăn trùng trong scope nhưng cho phép cùng ID ở scope khác nếu contract yêu cầu.
- Bulk update/delete không bỏ qua tenant predicate.

### Row-Level Security

Nếu database hỗ trợ Row-Level Security (RLS), có thể dùng RLS làm lớp phòng thủ bổ sung. Tuy nhiên RLS không thay thế authorization ở application layer. Test phải chạy bằng database role giống production; superuser hoặc owner có thể bypass policy tùy cấu hình.

Kiểm tra:

- Tenant A không SELECT được row B.
- Tenant A không UPDATE/DELETE được row B.
- Connection pool không giữ session variable tenant A khi tái sử dụng cho tenant B.
- Transaction rollback/reset tenant context sau mỗi request.
- Background worker thiết lập tenant scope trước khi truy vấn.

### Cache key phải bao gồm scope

Cache key chỉ dùng instance ID có thể gây rò rỉ nếu ID trùng giữa platform/tenant. Key nên bao gồm platform scope, tenant scope, resource type và resource ID:

~~~text
service-instance:{platform_id}:{tenant_id}:{instance_id}
binding:{platform_id}:{tenant_id}:{instance_id}:{binding_id}
operation:{platform_id}:{tenant_id}:{operation_id}
~~~

Test:

1. Đọc instance ID X của tenant A để cache.
2. Đọc instance ID X của tenant B.
3. Xác nhận cache không trả object A cho B.
4. Xóa cache tenant A và xác nhận entry B không bị xóa ngoài ý muốn.
5. Kiểm tra cache invalidation sau deprovision và secret rotation.

## 14. Kiểm thử provider adapter và secret manager

Provider adapter cần nhận một context có kiểu rõ ràng, trong đó có platform/tenant scope và provider account/project đã được broker chọn. Không cho phép request body tùy ý chỉ định provider account hoặc resource ID ngoài phạm vi.

Test adapter nên mock hoặc dùng sandbox provider:

- Tenant A gọi provider account A.
- Tenant B gọi provider account B.
- Caller A không thể thay account ID để gọi provider B.
- Resource reference lấy từ repository sau authorization, không lấy trực tiếp từ input tùy ý.
- Provider error không làm lộ secret.
- Timeout/retry không tạo resource trùng.
- Delete chỉ xóa resource có owner metadata khớp.

### Secret manager

Nếu broker dùng Vault, cloud secret manager hoặc Kubernetes Secret, kiểm tra:

- Secret path/key chứa tenant scope.
- IAM/RBAC giới hạn quyền đọc đúng secret.
- Secret reference được lưu trong database, không lưu plaintext nếu kiến trúc không yêu cầu.
- Rotation cập nhật secret version đúng binding.
- Unbind revoke credential và xóa/expire secret theo retention.
- Secret của tenant A không thể được resolve bằng reference tenant B.
- Log và error khi secret manager lỗi không chứa secret value.

Với Kubernetes, cần test namespace isolation và RBAC bằng service account thực tế. Không chỉ mock Kubernetes client rồi kết luận policy RBAC đúng.

## 15. Kiểm thử concurrency và race condition

Hai request đồng thời có thể cùng cố tạo hoặc xóa một binding. Một request của tenant A cũng có thể chạy song song với một request giả mạo tenant B dùng cùng ID.

Các tình huống:

- Hai provision request cùng instance ID, cùng tenant và cùng fingerprint.
- Hai provision request cùng ID nhưng payload khác nhau.
- Hai tenant cùng dùng một instance ID.
- Update và deprovision chạy đồng thời trên cùng instance.
- Create binding và delete binding chạy đồng thời.
- Secret rotation xảy ra trong lúc application đang lấy binding.
- Worker cũ hoàn thành sau worker mới.

Test nên dùng barrier/latch để đồng bộ thời điểm, không dựa vào Thread.sleep tùy ý. Xác minh:

- Chỉ một logical operation được tạo cho retry tương đương.
- Không có unique-key collision làm ghi đè dữ liệu tenant khác.
- Provider side effect chỉ xảy ra theo đúng scope.
- Optimistic lock/fencing ngăn worker cũ.
- Operation và binding cuối cùng có trạng thái hợp lệ.

## 16. Bộ công cụ kiểm thử cho Spring Cloud Service Broker

Một bộ test thường kết hợp:

| Công cụ | Mục đích |
|---|---|
| JUnit 5 | Test runner và lifecycle |
| Spring Security Test | Kiểm tra authentication/authorization |
| MockMvc | Kiểm thử HTTP boundary với Spring MVC |
| WebTestClient | Kiểm thử WebFlux hoặc reactive endpoint |
| Mockito | Kiểm tra tương tác repository/provider |
| Testcontainers | Chạy database, Redis hoặc dependency cô lập |
| WireMock/mock HTTP server | Giả lập provider API và response lỗi |
| Awaitility | Chờ async operation đạt trạng thái mong muốn |
| Log capture/appender | Phát hiện credentials trong log |
| Property-based testing | Sinh nhiều tổ hợp tenant/resource/ID để kiểm tra invariant |

Không cần dùng tất cả trong mọi test. Chọn công cụ theo lớp cần kiểm chứng. Mock phù hợp cho unit test policy; database/container và security filter thật phù hợp cho integration test; provider sandbox phù hợp cho kiểm tra contract có side effect.

### Cấu hình test profile

Test profile nên:

- Dùng database/container riêng, schema được tạo lại có kiểm soát.
- Dùng secret giả và provider endpoint giả.
- Tắt outbound network tới production provider.
- Dùng broker credentials riêng cho test.
- Không import file secret production.
- Tắt hoặc mask log request/response body.
- Có cleanup fixture kể cả khi test thất bại.
- Chạy song song mà không chia sẻ tenant ID hoặc secret canary.

Không để test tự động provision tài nguyên cloud thật ngoài ý muốn. Nếu cần sandbox thật, phải có tài khoản test riêng, quota, tag cleanup và giới hạn chi phí.

## 17. Ví dụ kiểm thử HTTP end-to-end

Ví dụ sau mô tả ý tưởng test qua HTTP boundary. Helper xác thực và endpoint cụ thể cần điều chỉnh theo security scheme và phiên bản Spring Cloud Open Service Broker của dự án.

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class TenantIsolationIT {

    @Autowired
    MockMvc mvc;

    @Autowired
    ServiceInstanceRepository instances;

    @Autowired
    ProviderClient provider;

    @Test
    void tenantACannotDeleteTenantBInstance() throws Exception {
        var tenantBInstance = instances.save(
                instance("cf-prod", "finance", "db-ledger-01"));

        mvc.perform(delete(
                        "/v2/service_instances/{instanceId}",
                        "db-ledger-01")
                .with(httpBasic("cf-retail", "test-secret"))
                .header("X-Broker-API-Version", "2.17")
                .param("service_id", "postgres")
                .param("plan_id", "standard"))
            .andExpect(status().isNotFound());

        assertThat(instances.existsById(tenantBInstance.id())).isTrue();
        verify(provider, never()).delete(any());
    }
}
~~~

Status 404 ở ví dụ là policy che giấu sự tồn tại resource ngoài scope; implementation có thể chọn mapping khác nếu OSB contract và security policy yêu cầu. Dù status nào, test phải xác nhận không tiết lộ metadata và không có side effect.

### Test response binding qua HTTP

Một integration test riêng cần gửi request create binding của tenant A, parse response JSON và xác nhận:

- Response chỉ chứa credentials của binding A.
- Không chứa canary secret của tenant B.
- Không trả provider account, secret path hoặc internal token không thuộc contract.
- Content-Type và status đúng OSB API.
- Header correlation không chứa secret.

Sau đó thử cùng request từ tenant B với instance/binding ID của A và xác nhận không thể lấy lại credentials A.

## 18. Property-based và fuzz testing

Một số invariant có thể kiểm tra trên nhiều tổ hợp dữ liệu:

- Với mọi tenant A khác tenant B, A không thể đọc hoặc thay đổi resource B.
- Với mọi binding thuộc instance B, request scope A không thể lấy credentials.
- Thay tenant header không được thay authenticated scope.
- Cùng ID ở hai platform không được map tới cùng provider resource.
- Mọi error response đều không chứa secret canary.
- Mọi operation async đều giữ tenant scope nhất quán từ lúc accept đến terminal state.

Property-based test có thể sinh ngẫu nhiên platform ID, tenant ID, instance ID, binding ID và operation ID. Cần bao gồm giá trị trùng, chuỗi rỗng, ký tự Unicode, ký tự phân cách, ID rất dài và giá trị có thể gây lỗi canonicalization. Fuzz test không thay thế test nghiệp vụ, nhưng hữu ích để phát hiện assumption về định dạng ID.

## 19. Test negative assertions và side effect

Một test authorization không nên chỉ kiểm tra status 403/404. Nó cần kiểm tra điều không xảy ra:

- Provider không nhận request.
- Repository không update/delete row ngoài scope.
- Operation mới không được tạo.
- Binding credentials không được sinh hoặc trả ra.
- Cache không bị ghi dữ liệu của tenant khác.
- Secret manager không được gọi với path ngoài scope.
- Audit log ghi attempted access nhưng không ghi secret.

Ví dụ:

~~~java
verify(providerClient, never()).createDatabase(any());
verify(providerClient, never()).delete(any());
verify(secretManager, never()).read(any());
verify(operationRepository, never()).save(any());
~~~

Các verify cần phù hợp với luồng thật. Một request trái quyền có thể được ghi audit record an toàn, vì vậy không nên cấm mọi database write nếu audit là hành vi mong đợi. Cần phân biệt audit write với business side effect.

## 20. Checklist test trước khi phát hành

- [ ] Xác định tenant model và resource ownership rõ ràng.
- [ ] Authentication được kiểm tra qua security filter thật.
- [ ] Authorization kiểm tra cả role và resource scope.
- [ ] Repository query luôn có platform/tenant predicate.
- [ ] Test ít nhất hai tenant có instance, binding và credentials riêng.
- [ ] Test cùng instance ID trên hai platform.
- [ ] Test IDOR/BOLA cho instance, operation và binding.
- [ ] Test giả mạo tenant header, body và OSB context.
- [ ] Test update/deprovision trái quyền không tạo provider side effect.
- [ ] Test binding response chỉ chứa credentials của consumer hợp lệ.
- [ ] Test secret rotation, unbind và credential revocation.
- [ ] Test response/error không chứa stack trace hoặc secret canary.
- [ ] Capture log, trace và queue message để tìm secret canary.
- [ ] Test worker async tải tenant scope từ operation đã lưu.
- [ ] Test stale job, replay, fencing token và retry.
- [ ] Test cache key bao gồm platform/tenant scope.
- [ ] Test database isolation/RLS bằng database role phù hợp.
- [ ] Test Secret manager/Kubernetes RBAC và namespace boundary.
- [ ] Test concurrency và duplicate request.
- [ ] Test không có test profile nào truy cập production provider hoặc secret.
- [ ] Test negative assertions cho repository, provider và secret manager.
- [ ] Ghi audit cho access denied mà không lưu credentials.

## Kết luận

Kiểm thử phân quyền nhiều khách hàng phải chứng minh tenant A không thể đọc, thay đổi, xóa hoặc lấy credentials của tenant B, kể cả khi biết ID của tài nguyên. Tenant scope cần được lấy từ danh tính đã xác thực, truyền nhất quán qua application service, repository, provider adapter, cache và worker bất đồng bộ. Binding credentials phải được giới hạn theo consumer, thu hồi đúng lúc và không xuất hiện trong error, log, trace hoặc queue ngoài policy. Kết hợp test HTTP qua security filter thật, test repository/database, provider mock, secret canary, negative assertions và concurrency test sẽ phát hiện nhiều lỗi IDOR/BOLA và rò rỉ dữ liệu trước khi service broker được đưa vào môi trường nhiều tenant.

## Tài liệu tham khảo

- [Open Service Broker API Specification](https://github.com/cloudfoundry/servicebroker/blob/master/spec.md)
- [Spring Security Reference — Testing](https://docs.spring.io/spring-security/reference/servlet/test/index.html)
- [OWASP API Security Top 10 — Broken Object Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/)
- [OWASP Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html)
- [Testcontainers Documentation](https://testcontainers.com/)
