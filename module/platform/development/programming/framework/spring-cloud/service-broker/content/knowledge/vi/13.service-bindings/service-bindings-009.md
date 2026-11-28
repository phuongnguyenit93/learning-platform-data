# Cấp phát tài khoản riêng cho từng binding hoặc dùng chung có kiểm soát

## Bối cảnh

Trong Open Service Broker API (OSB API), service instance là tài nguyên được cấp phát cho một ứng dụng hoặc một phạm vi sử dụng. Binding tạo mối liên kết giữa instance đó với một consumer, thường là ứng dụng cần kết nối tới database, cache, message broker hoặc dịch vụ bên ngoài. Broker trả thông tin kết nối và credential trong response của thao tác tạo binding.

Một service instance có thể được nhiều ứng dụng hoặc nhiều thành phần của cùng một ứng dụng sử dụng. Khi đó, broker phải chọn cách cấp danh tính truy cập:

- **Tài khoản riêng cho từng binding:** mỗi binding có principal, user hoặc credential riêng, với quyền được giới hạn theo nhu cầu của consumer.
- **Dùng chung có kiểm soát:** nhiều binding cùng sử dụng một danh tính backend hoặc một nhóm quyền chung, nhưng broker vẫn quản lý phạm vi sử dụng, secret, mapping và khả năng thu hồi.

Quyết định này ảnh hưởng trực tiếp tới bảo mật, audit, khả năng thu hồi độc lập, vận hành khi rotate secret và mức độ phức tạp của provider adapter. Trong service broker triển khai bằng Spring Cloud Open Service Broker, logic cấp credential nên nằm trong application service và adapter hạ tầng; lớp OSB chỉ nhận request model và trả response model theo hợp đồng.

## 1. Binding là ranh giới cấp quyền cho consumer

Platform tạo binding bằng request tới endpoint:

~~~http
PUT /v2/service_instances/{instance_id}/service_bindings/{binding_id}
X-Broker-API-Version: 2.17
Content-Type: application/json
~~~

Trong đó:

- service instance ID xác định tài nguyên mà consumer muốn sử dụng.
- binding ID xác định một liên kết cụ thể giữa instance và consumer.
- request có thể chứa app GUID, bind_resource, parameters và context tùy nền tảng.
- response trả thông tin kết nối cần thiết cho consumer, thường nằm trong trường credentials.

Ví dụ response:

~~~http
HTTP/1.1 201 Created
Content-Type: application/json

{
  "credentials": {
    "uri": "postgresql://db.example.internal:5432/orders",
    "host": "db.example.internal",
    "port": 5432,
    "database": "orders",
    "username": "orders_binding_a81f",
    "password": "<generated-secret>",
    "sslmode": "verify-full"
  }
}
~~~

Response thực tế phụ thuộc loại service và schema mà consumer mong đợi. Ví dụ trên minh họa database binding; broker chỉ trả những thuộc tính cần thiết để consumer kết nối. Không đưa thông tin nội bộ không cần thiết hoặc secret của tài khoản quản trị provider vào response.

Binding là một đơn vị cấp quyền có vòng đời riêng. Khi Platform yêu cầu unbind, broker phải biết chính xác credential, role, token hoặc mapping nào thuộc binding đó để thu hồi đúng phạm vi.

## 2. Mô hình tài khoản riêng cho từng binding

Với mô hình này, mỗi binding được cấp một principal riêng ở provider. Nếu một database instance có ba binding, broker tạo ba user hoặc credential độc lập:

~~~text
Service instance: orders-db
  |
  +-- binding-api
  |     +-- database role: orders_api_a81f
  |     +-- secret: secret-api
  |
  +-- binding-worker
  |     +-- database role: orders_worker_c920
  |     +-- secret: secret-worker
  |
  +-- binding-report
        +-- database role: orders_report_4b12
        +-- secret: secret-report
~~~

Các tài khoản có thể truy cập cùng một database nhưng nhận quyền khác nhau. API có thể được phép đọc và ghi một số bảng; worker có quyền cập nhật trạng thái xử lý; reporting chỉ được đọc dữ liệu đã công bố.

### Quy trình cấp phát

1. Nhận binding request và xác định service instance.
2. Kiểm tra instance đang ở trạng thái cho phép binding.
3. Xác minh caller, Platform scope, app identity và quyền bind.
4. Tải policy quyền tương ứng với service/plan và loại consumer.
5. Sinh principal hoặc credential mới có entropy đủ mạnh.
6. Tạo tài khoản ở provider với quyền tối thiểu.
7. Lưu binding record và secret theo cách bảo vệ được việc retry.
8. Trả credentials trong CreateServiceInstanceBindingResponse.

Nếu tạo tài khoản provider thành công nhưng ghi binding record thất bại, broker cần có cơ chế reconcile hoặc cleanup tài khoản mồ côi. Nếu lưu record trước khi provider tạo tài khoản, record phải có trạng thái trung gian để worker có thể tiếp tục hoặc bù trừ khi lỗi.

### Ví dụ phân quyền PostgreSQL

Một cách triển khai là tạo role dùng chung chỉ chứa quyền, sau đó tạo login role riêng cho mỗi binding:

~~~sql
CREATE ROLE orders_runtime NOLOGIN;
GRANT CONNECT ON DATABASE orders TO orders_runtime;
GRANT USAGE ON SCHEMA app TO orders_runtime;
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA app TO orders_runtime;

CREATE ROLE orders_api_a81f LOGIN PASSWORD '<unique-secret>' INHERIT;
GRANT orders_runtime TO orders_api_a81f;
~~~

Role orders_runtime gom nhóm quyền chuẩn. Mỗi binding có login riêng nên broker có thể thu hồi một consumer mà không cần thay password của các consumer khác. Trong production, cần quản lý default privileges cho object mới, quyền sequence, schema, function và các giới hạn theo tenant. Không ghép identifier từ input không tin cậy trực tiếp vào câu lệnh SQL; dùng quy tắc sinh tên và quoting an toàn của provider.

### Ưu điểm và chi phí

| Khía cạnh | Tài khoản riêng |
|---|---|
| Cô lập | Có thể giới hạn quyền theo consumer hoặc binding |
| Audit | Dễ truy dấu hoạt động theo principal |
| Unbind | Thu hồi một binding mà không ảnh hưởng binding khác |
| Rotation | Có thể rotate từng credential độc lập |
| Sự cố lộ secret | Phạm vi ảnh hưởng thường nhỏ hơn |
| Tài nguyên | Tăng số lượng user, role, token hoặc connection identity |
| Vận hành | Cần quản lý quota, naming, cleanup và vòng đời credential |

Mô hình này thường phù hợp khi service instance được nhiều ứng dụng độc lập sử dụng, dữ liệu nhạy cảm, cần audit theo consumer hoặc có yêu cầu thu hồi riêng từng binding.

## 3. Mô hình dùng chung có kiểm soát

Không phải provider nào cũng hỗ trợ tạo user riêng với chi phí thấp. Một số dịch vụ có giới hạn số principal, thời gian tạo credential dài hoặc chỉ cung cấp một service account cho mỗi instance. Trong những trường hợp đó, có thể dùng chung một danh tính backend hoặc nhóm quyền, nhưng phải phân biệt ba thiết kế khác nhau.

### 3.1. Dùng chung một credential cho mọi binding

Mọi binding nhận cùng username/password hoặc token:

~~~text
Service instance: shared-cache
  |
  +-- binding-api ----+
  |                   |
  +-- binding-worker -+--> shared principal: cache_runtime
  |                   |      shared secret
  +-- binding-report -+
~~~

Thiết kế này đơn giản và giảm số lượng principal. Tuy nhiên, nó có giới hạn bảo mật lớn:

- Provider nhìn thấy cùng một principal cho mọi consumer.
- Audit không phân biệt được consumer nào thực hiện thao tác.
- Unbind một binding không thể thu hồi credential mà không làm hỏng các binding còn lại.
- Nếu secret bị lộ ở một consumer, mọi consumer dùng chung secret đều bị ảnh hưởng.
- Rotation thường phải phối hợp cập nhật tất cả consumer.

Vì vậy, chỉ nên dùng khi các consumer thuộc cùng một trust boundary, có cùng mức quyền và chấp nhận tác động thu hồi/rotation đồng loạt. Không nên chọn chỉ vì cách này dễ triển khai.

### 3.2. Dùng chung quyền backend nhưng credential riêng theo binding

Đây thường là lựa chọn cân bằng hơn. Các binding cùng sử dụng một nhóm quyền hoặc một service account nền, nhưng mỗi binding nhận một credential/token riêng được gateway hoặc credential broker ánh xạ về quyền backend đó.

~~~text
binding-api    -> token-api    --+
binding-worker -> token-worker ---+--> credential gateway
binding-report -> token-report --+       |
                                         v
                                  shared backend identity
                                         |
                                         v
                                  service instance
~~~

Credential gateway cần xác thực token, kiểm tra binding ID, áp dụng policy và ghi audit trước khi thực hiện truy cập backend. Khi unbind, broker thu hồi token hoặc mapping của binding đó. Các binding khác tiếp tục hoạt động.

Lưu ý: nếu consumer kết nối trực tiếp tới database bằng cùng username/password, việc lưu riêng ba bản copy của cùng secret không tạo ra ba danh tính. Muốn thu hồi độc lập, provider phải hỗ trợ token riêng, proxy identity, role riêng hoặc một lớp gateway có thể nhận diện từng consumer.

### 3.3. Dùng chung một role quyền, tạo login riêng

Một biến thể hữu ích cho database là dùng một role không đăng nhập làm nhóm quyền, nhưng vẫn tạo login role riêng cho từng binding. Về mặt quyền, các binding dùng chung policy; về mặt danh tính, mỗi binding vẫn độc lập.

Mô hình này tránh lặp lại GRANT ở từng tài khoản và vẫn giữ được audit/revocation theo login. Nó thường dễ vận hành hơn việc dùng một username/password duy nhất.

## 4. So sánh và chọn mô hình

| Tiêu chí | Credential chung hoàn toàn | Quyền backend chung, token riêng | Principal riêng theo binding |
|---|---|---|---|
| Số principal backend | Một | Có thể một | Nhiều |
| Phân biệt consumer | Hạn chế | Theo token/mapping | Theo principal |
| Thu hồi một binding | Khó nếu cùng secret trực tiếp | Có thể thu hồi token riêng | Thu hồi principal riêng |
| Rotation độc lập | Không | Có nếu gateway hỗ trợ | Có |
| Audit | Thường chỉ thấy shared identity | Gateway ghi theo token/binding | Provider ghi theo principal |
| Chi phí provider | Thấp | Thấp đến trung bình | Cao hơn |
| Độ phức tạp | Thấp lúc đầu, khó khi vận hành | Cần gateway và policy | Cần quản lý nhiều principal |
| Phạm vi ảnh hưởng khi lộ secret | Tất cả binding | Một token nếu mapping được cô lập | Thường một binding |

### Câu hỏi quyết định

Trước khi chọn mô hình, broker nên trả lời:

1. Provider có hỗ trợ nhiều user/role/token cho một instance không?
2. Có thể cấp quyền khác nhau theo consumer không?
3. Khi unbind, có thể vô hiệu hóa duy nhất credential của binding đó không?
4. Có cần audit theo app hoặc binding ID không?
5. Secret có được consumer lưu lâu dài hay được cấp ngắn hạn?
6. Có giới hạn số principal, connection hoặc token trên mỗi instance không?
7. Nếu shared credential bị lộ, kế hoạch rotation ảnh hưởng bao nhiêu ứng dụng?

Nếu cần revocation độc lập hoặc audit theo consumer, credential dùng chung hoàn toàn thường không đáp ứng yêu cầu. Hãy ưu tiên principal riêng hoặc token riêng có mapping được kiểm soát.

## 5. Quản lý binding record và secret

Broker cần lưu trạng thái binding để hỗ trợ retry, retrieve (nếu được triển khai), unbind, rotation và điều tra sự cố.

Một mô hình dữ liệu tham khảo:

~~~text
ServiceBinding
  platformId
  instanceId
  bindingId
  appGuid
  bindResource
  credentialMode
  providerPrincipalId
  secretReference
  permissionsProfile
  state
  createdAt
  rotatedAt
  revokedAt
  requestFingerprint
~~~

credentialMode có thể là DEDICATED_PRINCIPAL, SHARED_TOKEN hoặc SHARED_CREDENTIAL. Không lưu password dạng plaintext trong database thông thường. Có thể lưu secret trong secret manager và chỉ giữ secret reference; nếu broker phải trả lại đúng credentials khi xử lý retry, cần lưu secret ở dạng mã hóa có thể giải mã bởi service được cấp quyền. Hash một chiều phù hợp cho xác minh password nhưng không đủ để trả lại password ban đầu cho Platform khi retry.

Các nguyên tắc bảo vệ:

- Mã hóa secret khi lưu trữ bằng KMS hoặc secret manager.
- Hạn chế service account nào được đọc secret và ghi audit việc truy cập.
- Không ghi credentials, authorization header hoặc binding response đầy đủ vào log.
- Không đưa secret vào metric label, trace attribute hoặc exception message.
- Không trả lại credential của binding khác khi lookup theo binding ID.
- Phân vùng dữ liệu theo Platform/tenant nếu broker phục vụ nhiều nền tảng.
- Đặt retention cho secret đã revoke và xóa theo chính sách.

## 6. Sinh credential và nguyên tắc least privilege

Credential cho mỗi binding cần được sinh bằng bộ sinh số ngẫu nhiên an toàn mật mã. Không dùng timestamp, instance ID, binding ID hoặc chuỗi ngẫu nhiên thông thường làm password. Tên principal có thể được tạo từ prefix và một phần định danh ngẫu nhiên, nhưng secret phải độc lập với tên.

Ví dụ Java:

~~~java
private static final SecureRandom RANDOM = new SecureRandom();
private static final char[] ALPHABET =
        "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789-_".toCharArray();

static String newSecret(int length) {
    char[] value = new char[length];
    for (int i = 0; i < length; i++) {
        value[i] = ALPHABET[RANDOM.nextInt(ALPHABET.length)];
    }
    return new String(value);
}
~~~

Ví dụ này minh họa cách dùng SecureRandom; production nên dùng thư viện hoặc secret manager đã được chuẩn hóa, độ dài và alphabet phù hợp với giới hạn của provider. Tránh modulo bias khi tự viết bộ sinh tùy biến nếu yêu cầu bảo mật cao; ưu tiên API sinh password/token chuyên dụng.

Least privilege có nghĩa là mỗi binding chỉ nhận quyền cần cho chức năng của consumer:

| Consumer | Quyền ví dụ |
|---|---|
| API backend | SELECT/INSERT/UPDATE trên bảng nghiệp vụ được phép |
| Background worker | Đọc job và cập nhật trạng thái xử lý |
| Reporting | SELECT trên view hoặc schema báo cáo |
| Migration job | Quyền DDL tạm thời trong cửa sổ migration, không cấp thường trực |
| Monitoring | Quyền đọc metric hoặc health metadata, không đọc dữ liệu nghiệp vụ |

Không cấp quyền superuser hoặc quyền quản trị instance cho ứng dụng chỉ vì dễ cấu hình. Nếu provider chỉ có thể cấp một nhóm quyền cố định, broker cần mô tả rõ giới hạn đó trong catalog/service documentation.

## 7. Idempotency khi tạo binding

Platform có thể retry PUT binding khi response bị timeout hoặc mất kết nối. Broker cần bảo đảm một binding ID không tạo nhiều principal hoặc nhiều credential ngoài ý muốn.

Khóa định danh nghiệp vụ thường gồm Platform ID, service instance ID và binding ID. Request fingerprint có thể bao gồm app GUID, bind_resource, parameters và policy có ảnh hưởng tới kết quả.

Quy tắc:

- Nếu binding ID chưa tồn tại, tạo binding theo policy.
- Nếu binding ID đã tồn tại và request fingerprint giống nhau, trả lại kết quả của binding hiện có theo contract.
- Nếu binding ID đã tồn tại nhưng request khác về consumer hoặc quyền, trả lỗi conflict phù hợp.
- Nếu provider đã tạo principal nhưng broker chưa lưu kết quả, tìm principal theo binding tag/operation ID và reconcile trước khi tạo mới.
- Nếu hai request cùng binding ID chạy đồng thời, unique constraint và transaction phải bảo vệ việc tạo binding.

Ví dụ pseudocode:

~~~java
BindingResult bind(BindCommand command) {
    var existing = bindings.find(
            command.platformId(),
            command.instanceId(),
            command.bindingId());

    if (existing != null) {
        if (!existing.requestFingerprint().equals(command.fingerprint())) {
            throw new BindingConflictException(command.bindingId());
        }
        return credentialStore.loadForResponse(existing.secretReference());
    }

    return bindingProvisioner.createAndPersist(command);
}
~~~

Đây là pseudocode mô tả quy tắc, không phải API class của Spring Cloud Open Service Broker. Việc tạo provider principal và lưu binding record có thể không nằm trong cùng transaction. Cần dùng trạng thái trung gian, idempotency key phía provider nếu có, tag nhận diện và reconciliation để xử lý lỗi giữa hai bước.

## 8. Unbind và thu hồi quyền

Platform yêu cầu xóa binding qua endpoint DELETE tương ứng. Khi nhận unbind, broker phải thu hồi đúng tài khoản, token hoặc mapping thuộc binding đó.

### Với principal riêng

1. Tải binding theo Platform ID, instance ID và binding ID.
2. Kiểm tra quyền và trạng thái.
3. Vô hiệu hóa login/token trước hoặc theo thứ tự an toàn của provider.
4. Xóa role/user hoặc thu hồi credential.
5. Xác minh principal không còn truy cập được.
6. Đánh dấu binding REVOKED/DELETED và dọn secret theo retention policy.

Nếu xóa user thất bại do còn session hoặc object ownership, broker có thể phải terminate session, chuyển ownership hoặc revoke login trước rồi mới drop principal. Không bỏ qua lỗi provider và đánh dấu binding đã xóa khi credential vẫn còn hiệu lực.

### Với credential dùng chung hoàn toàn

Không được xóa shared principal khi chỉ một binding bị unbind vì các binding khác vẫn phụ thuộc vào nó. Broker chỉ có thể xóa mapping nội bộ nếu mapping đó có ý nghĩa độc lập; nếu tất cả consumer dùng trực tiếp cùng password, việc vô hiệu hóa password sẽ ảnh hưởng tất cả.

Điều này làm lộ giới hạn cốt lõi của shared credential: không thể thu hồi độc lập một binding nếu provider không có lớp định danh riêng. Nếu yêu cầu thu hồi riêng xuất hiện, cần chuyển sang token/principal riêng hoặc thực hiện rotation toàn bộ và phối hợp cập nhật mọi consumer.

### Với shared backend và token riêng

Unbind chỉ cần revoke token/mapping của binding đó ở gateway, sau đó xác nhận token không còn được chấp nhận. Shared backend identity vẫn được giữ cho các binding còn lại. Gateway phải kiểm tra trạng thái token tại mỗi lần xác thực hoặc dùng cơ chế cache có thời hạn đủ ngắn để việc revoke có hiệu lực đúng yêu cầu.

## 9. Rotation credential

Credential có thể cần rotate khi hết hạn, nghi ngờ bị lộ, thay đổi chính sách hoặc theo lịch định kỳ. Rotation phải tránh khoảng thời gian mà consumer không thể kết nối.

Một quy trình rotation an toàn:

1. Tạo credential mới hoặc token mới cho binding.
2. Lưu secret mới vào secret manager với trạng thái PENDING.
3. Cập nhật binding state để nhận diện credential generation mới.
4. Phân phối secret mới qua cơ chế binding/Platform được hỗ trợ.
5. Xác nhận consumer đã sử dụng credential mới hoặc hoàn tất cửa sổ chuyển đổi.
6. Thu hồi credential cũ.
7. Đánh dấu generation mới ACTIVE và ghi audit.

Nếu Platform không tự động cập nhật secret trong ứng dụng, broker cần xác định quy trình operator/rebind/redeploy tương ứng. Không thu hồi credential cũ trước khi consumer có thể chuyển sang credential mới, trừ khi sự cố bảo mật yêu cầu khóa khẩn cấp.

Với tài khoản riêng, rotation có thể thực hiện theo từng binding. Với shared credential hoàn toàn, rotation thường ảnh hưởng tất cả binding cùng lúc. Với token riêng ánh xạ tới shared backend, có thể rotate token của một binding độc lập nếu gateway hỗ trợ.

## 10. Tích hợp với Spring Cloud Open Service Broker

Spring Cloud Open Service Broker cung cấp abstraction cho binding lifecycle. Ứng dụng triển khai ServiceInstanceBindingService để xử lý tạo và xóa binding; request model cung cấp service instance ID, binding ID, app/resource context và parameters theo phiên bản thư viện.

Một kiến trúc nên tách các trách nhiệm:

| Thành phần | Trách nhiệm |
|---|---|
| Binding service implementation | Nhận OSB request và trả response model |
| Binding policy | Chọn dedicated principal, shared token hoặc mô hình dùng chung |
| Credential provisioner | Sinh principal/token và áp dụng quyền |
| Secret store | Lưu secret an toàn và cấp lại khi retry hợp lệ |
| Binding repository | Lưu binding ID, owner, credential mode và trạng thái |
| Provider adapter | Gọi database, cache, gateway hoặc API Kubernetes/cloud |
| Unbind service | Thu hồi đúng credential hoặc mapping |

Ví dụ Java minh họa:

~~~java
@Service
class DatabaseBindingService implements ServiceInstanceBindingService {

    private final BindingApplicationService bindingService;

    DatabaseBindingService(BindingApplicationService bindingService) {
        this.bindingService = bindingService;
    }

    @Override
    public CreateServiceInstanceBindingResponse createServiceInstanceBinding(
            CreateServiceInstanceBindingRequest request) {

        var result = bindingService.create(
                request.getServiceInstanceId(),
                request.getBindingId(),
                request.getAppGuid(),
                request.getBindResource(),
                request.getParameters());

        return CreateServiceInstanceBindingResponse.builder()
                .credentials(result.credentials())
                .build();
    }
}
~~~

Đây là ví dụ định hướng; method signature và accessor có thể khác theo phiên bản dependency. Hãy dùng interface và response builder đúng với Spring Cloud Open Service Broker đang cài đặt. Application service chịu trách nhiệm chọn mô hình credential, tạo principal, lưu secret và kiểm tra idempotency. Binding service chỉ chuyển request/response qua ranh giới OSB.

### Không để provider adapter quyết định policy bảo mật

Adapter có thể biết provider hỗ trợ bao nhiêu user, role hoặc token, nhưng policy về quyền consumer thuộc application/domain layer. Ví dụ adapter PostgreSQL tạo role; adapter Redis tạo ACL user; adapter API gateway cấp token. Cả ba nhận một lệnh đã được policy chuẩn hóa, không tự cấp quyền rộng hơn vì provider API thuận tiện.

## 11. Kiểm thử

Kiểm thử phải xác minh cả credential response, trạng thái provider và khả năng thu hồi.

| Tình huống | Điều cần xác minh |
|---|---|
| Tạo binding riêng | Principal/secret mới chỉ thuộc binding đó |
| Hai binding cùng instance | Không dùng chung credential nếu policy yêu cầu dedicated |
| Binding cùng role quyền | Quyền nhất quán nhưng login principal khác nhau |
| Shared token | Token có mapping riêng và revoke độc lập |
| Shared credential trực tiếp | Tài liệu hóa rằng unbind không thể thu hồi riêng |
| Retry cùng binding ID | Trả lại credential hiện có, không tạo principal thứ hai |
| Cùng binding ID nhưng app/parameters khác | Conflict theo policy |
| Provider create thành công, DB save lỗi | Reconcile hoặc cleanup principal mồ côi |
| Unbind principal riêng | Credential bị vô hiệu hóa và principal được thu hồi |
| Unbind một shared token | Token đó bị revoke, token khác vẫn hoạt động |
| Rotation | Credential mới hoạt động trước khi credential cũ bị thu hồi theo policy |
| Secret handling | Không có password/token trong log, trace hoặc exception |
| Cross-tenant access | Không thể đọc hoặc thu hồi binding của tenant khác |

Nên có integration test qua HTTP endpoint thực của framework để kiểm tra response credentials theo OSB API. Unit test tập trung vào policy chọn credential mode, quyền và fingerprint. Adapter test kiểm tra lệnh tạo/revoke principal hoặc token. Với shared credential, cần test rõ tác động của rotation và unbind để tránh giả định sai rằng mỗi binding có thể thu hồi độc lập.

## 12. Checklist triển khai production

- [ ] Mỗi binding có binding ID và record riêng trong phạm vi Platform/instance.
- [ ] Policy xác định rõ dedicated principal, shared token hay shared credential.
- [ ] Ưu tiên credential riêng khi cần audit hoặc thu hồi độc lập.
- [ ] Nếu dùng chung hoàn toàn, xác định rõ trust boundary và tác động rotation/revoke đồng loạt.
- [ ] Nếu dùng chung backend, token/mapping của từng binding phải có thể revoke độc lập.
- [ ] Quyền được cấp theo least privilege và đúng loại consumer.
- [ ] Credential được sinh bằng nguồn ngẫu nhiên an toàn và không suy ra từ ID.
- [ ] Secret được lưu trong secret manager hoặc mã hóa bằng KMS.
- [ ] Retry cùng binding ID không tạo principal hoặc token trùng.
- [ ] Unbind thu hồi đúng phạm vi và xác minh credential không còn hiệu lực.
- [ ] Rotation có generation, giai đoạn chuyển tiếp và thời điểm revoke credential cũ.
- [ ] Không ghi secret vào log, trace, metric hoặc error description.
- [ ] Có audit theo binding ID, principal/token và hành động cấp phát/thu hồi.
- [ ] Có reconciliation cho principal mồ côi và thao tác provider thất bại một phần.

## Kết luận

Cấp tài khoản riêng cho từng binding tạo ranh giới bảo mật rõ ràng: mỗi consumer có principal hoặc credential riêng, có thể audit, rotate và thu hồi độc lập. Dùng chung có thể giảm chi phí và giới hạn số principal, nhưng chỉ an toàn khi broker kiểm soát được phạm vi consumer và khả năng revoke. Nếu mọi binding nhận cùng username/password trực tiếp, unbind một binding không thể vô hiệu hóa riêng credential đó. Một phương án cân bằng là dùng chung nhóm quyền backend nhưng cấp login role hoặc token riêng cho từng binding. Trong Spring Cloud Open Service Broker, hãy đặt policy ở application service, lưu binding state và secret bền vững, xử lý retry idempotent và thu hồi đúng credential khi unbind để bảo vệ service instance trên Cloud Foundry, Kubernetes và các Platform OSB API khác.
