# Lưu credentials trong kho bí mật và mã hóa dữ liệu nhạy cảm

Service broker xử lý nhiều loại dữ liệu nhạy cảm: password của service binding, token mà broker dùng để gọi provider, private key, client secret và thông tin xác thực của nền tảng. Nếu lưu các giá trị này trực tiếp trong bảng nghiệp vụ, file cấu hình hoặc log, một sự cố đọc database hay truy cập repository có thể làm lộ quyền truy cập tới nhiều tài nguyên.

Trong module **SPRING_CLOUD_SERVICE_BROKER**, bảo vệ credentials là một phần của thiết kế vòng đời service instance và binding. Open Service Broker API (OSB API) yêu cầu broker trả credentials cho consumer khi bind; một số offering còn hỗ trợ truy xuất lại binding. Spring Cloud Open Service Broker (SCOSB) cung cấp request/response model và service abstraction, còn ứng dụng broker phải quản lý việc tạo, lưu, đọc, rotate và thu hồi secret một cách an toàn.

Bài học này trình bày cách phân loại dữ liệu, sử dụng secret manager, mã hóa dữ liệu nhạy cảm bằng envelope encryption và KMS, giới hạn quyền đọc secret, tích hợp với Spring, bảo vệ credentials binding/provider, xử lý rotation, backup, audit và kiểm thử.

## 1. Xác định dữ liệu nào cần được bảo vệ

Không phải mọi dữ liệu của broker đều cần cùng một cơ chế bảo vệ. Trước khi chọn secret manager hoặc thuật toán mã hóa, hãy phân loại dữ liệu theo tác động nếu bị lộ.

| Nhóm dữ liệu | Ví dụ | Mức độ nhạy cảm | Nơi lưu phù hợp |
|---|---|---|---|
| Metadata công khai | Service ID, plan ID, mô tả catalog | Thấp | Database, catalog |
| Metadata nội bộ | Instance ID, provider resource ID, tenant reference | Trung bình | Database có kiểm soát truy cập |
| Cấu hình nghiệp vụ | Region, quota, storage size, feature flags | Tùy dữ liệu | Database; mã hóa nếu chứa thông tin nhạy cảm |
| Binding credentials | Username, password, connection token, certificate | Cao | Secret manager hoặc kho mã hóa chuyên biệt |
| Provider credentials | API key, client secret, private key, refresh token | Rất cao | Secret manager, workload identity hoặc KMS |
| Encryption key | Data encryption key, key encryption key | Rất cao | KMS/HSM, không lưu cùng dữ liệu đã mã hóa |
| Audit metadata | Actor, secret ID, operation ID, timestamp | Trung bình | Audit store, không chứa secret payload |

Ví dụ một service instance PostgreSQL có thể lưu các trường không bí mật trong database broker:

~~~text
instance_id = instance-pg-100
service_id = svc-postgresql
plan_id = plan-standard
provider_resource_id = db-9a8f
state = READY
~~~

Credentials dành cho ứng dụng được lưu riêng:

~~~text
secret reference = secret://broker/bindings/binding-orders-204
secret version = 7

username = orders_app
password = <secret>
host = pg.internal.example
port = 5432
database = orders
~~~

Bảng binding chỉ cần giữ secret reference và version. Worker hoặc service được phân quyền mới đọc nội dung secret khi thực sự cần.

### Không coi mọi dữ liệu có tên credentials là cùng một loại

Cần phân biệt:

- **Provider credential:** broker dùng để gọi cloud API, Kubernetes API hoặc database administration API.
- **Binding credential:** consumer dùng để kết nối service đã bind.
- **Platform credential:** platform dùng để xác thực khi gọi broker.
- **Encryption key:** khóa dùng để mã hóa hoặc giải mã dữ liệu.

Các credential này có chủ thể, phạm vi và vòng đời khác nhau. Không tái sử dụng provider credential làm binding credential; không lưu platform password trong bản ghi service instance; không dùng encryption key như một credential để gọi provider.

## 2. Secret manager giải quyết vấn đề gì?

Secret manager là hệ thống chuyên lưu trữ, phân phối, kiểm soát truy cập, version và audit secret. Ví dụ có thể dùng HashiCorp Vault, AWS Secrets Manager, Google Secret Manager, Azure Key Vault hoặc dịch vụ nội bộ có cùng đặc tính.

Secret manager giúp broker:

- Lưu secret ngoài source code và bảng nghiệp vụ thông thường.
- Kiểm soát service identity nào được đọc hoặc ghi từng secret.
- Quản lý version khi thay đổi credentials.
- Hỗ trợ rotation và thu hồi.
- Audit việc đọc, ghi và xóa secret.
- Mã hóa secret khi lưu và khi truyền.
- Tích hợp KMS/HSM để quản lý encryption key.

Secret manager không tự động làm cho hệ thống an toàn. Nếu mọi pod broker đều có quyền đọc toàn bộ secret của mọi tenant, một pod bị xâm nhập vẫn có thể làm lộ tất cả credentials. Cần giới hạn quyền theo workload, provider account, tenant hoặc secret path.

### Cấu trúc lưu trữ nên dùng

Một binding record có thể lưu:

~~~json
{
  "binding_id": "binding-orders-204",
  "instance_id": "instance-pg-100",
  "tenant_id": "org-orders",
  "state": "ACTIVE",
  "credentials_secret_ref": "secret://broker/tenants/org-orders/bindings/binding-orders-204",
  "credential_version": 7
}
~~~

Nội dung secret ở secret manager:

~~~json
{
  "username": "orders_app",
  "password": "<secret-value>",
  "host": "pg.internal.example",
  "port": 5432,
  "database": "orders",
  "sslmode": "require"
}
~~~

Database broker chỉ lưu reference, version và metadata cần truy vấn. Không lưu cả JSON credentials vào cột metadata hoặc parameters nếu không có cơ chế mã hóa và phân quyền tương đương secret manager.

## 3. Thiết kế đường dẫn secret theo tenant và resource

Đường dẫn secret cần có cấu trúc ổn định để phân quyền, rotation và điều tra. Ví dụ:

~~~text
broker/
  providers/
    aws-account-a/
      credential
    kubernetes-cluster-prod/
      credential
  tenants/
    org-orders/
      instances/
        instance-pg-100/
          admin-connection
      bindings/
        binding-orders-204/
          credentials
        binding-worker-205/
          credentials
~~~

Các nguyên tắc thiết kế:

- Có namespace hoặc prefix riêng cho ứng dụng broker.
- Tách secret provider khỏi secret binding.
- Có tenant reference đã được xác minh trong đường dẫn.
- Mỗi binding có secret riêng hoặc secret object với policy riêng.
- Tránh đặt secret trực tiếp trong tên path, tag hoặc metadata.
- Không cho request OSB API tự quyết định secret path tùy ý.
- Giới hạn quyền theo prefix hoặc secret ID nếu secret manager hỗ trợ.
- Dùng ID ổn định và không tái sử dụng secret path cho một binding khác sau khi thu hồi.

Đường dẫn secret là một định danh, không phải cơ chế authorization. Broker vẫn phải kiểm tra quyền truy cập instance, binding và tenant trước khi yêu cầu secret manager đọc giá trị.

## 4. Mã hóa khi truyền và khi lưu

Có hai lớp bảo vệ cơ bản:

**Mã hóa khi truyền (in transit):** bảo vệ dữ liệu khi đi qua network. Dùng TLS cho kết nối platform-to-broker, broker-to-secret-manager, broker-to-provider và các kết nối tới database. Với môi trường có yêu cầu cao, cân nhắc mutual TLS để xác thực cả hai phía.

**Mã hóa khi lưu (at rest):** bảo vệ dữ liệu trên database, disk, object storage, backup và secret store. Có thể dùng mã hóa volume/database do cloud cung cấp, mã hóa cột hoặc envelope encryption cho dữ liệu đặc biệt nhạy cảm.

| Vị trí | Biện pháp |
|---|---|
| HTTP platform-to-broker | TLS, certificate validation, mTLS nếu phù hợp |
| Broker-to-provider | TLS, kiểm tra hostname/certificate, token ngắn hạn |
| Broker-to-secret-manager | TLS và workload identity |
| Database broker | Storage encryption; mã hóa trường nhạy cảm nếu cần |
| Secret manager | Encryption at rest, KMS/HSM và access policy |
| Backup/snapshot | Mã hóa riêng, quyền restore hạn chế |
| Log/trace | Loại bỏ secret trước khi ghi, không dựa vào mã hóa log để cho phép ghi secret |

Mã hóa at rest không thay thế phân quyền. Nếu attacker lấy được quyền đọc ứng dụng hoặc quyền gọi KMS để giải mã, dữ liệu vẫn có thể bị lộ. Cần kiểm soát cả database access, secret access và key usage.

## 5. Envelope encryption và vai trò của KMS

Với dữ liệu nhạy cảm cần mã hóa trong database, một mẫu thường dùng là **envelope encryption**. Ứng dụng tạo một Data Encryption Key (DEK) để mã hóa payload; KMS quản lý Key Encryption Key (KEK) và dùng KEK để bảo vệ DEK.

Luồng tổng quát:

~~~mermaid
flowchart TD
    A["Sensitive payload"] --> B["Generate or obtain DEK"]
    B --> C["Encrypt payload with DEK"]
    B --> D["Wrap DEK using KMS KEK"]
    C --> E["Ciphertext"]
    D --> F["Wrapped DEK"]
    E --> G["Store ciphertext + wrapped DEK + metadata"]
    F --> G
    G --> H["Read with authorized workload"]
    H --> I["Ask KMS to unwrap DEK"]
    I --> J["Decrypt payload in memory"]
~~~

Khi lưu, broker ghi ciphertext, wrapped DEK, key version và metadata thuật toán. Khi đọc, workload được phân quyền yêu cầu KMS unwrap DEK, sau đó giải mã payload trong memory.

Không lưu plaintext DEK cạnh ciphertext. Wrapped DEK có thể được lưu cùng ciphertext vì chỉ KMS hoặc principal được phép mới có thể unwrap nó.

### Vì sao không tự tạo một khóa AES cố định trong code?

Một khóa cố định trong source code hoặc image dễ bị lộ qua repository, artifact, backup hay quyền truy cập máy chủ. Nếu cùng một khóa mã hóa mọi tenant, sự cố của khóa ảnh hưởng toàn bộ dữ liệu.

Dùng KMS/HSM để quản lý KEK, kiểm soát quyền sử dụng key và audit. DEK có thể được tạo theo từng record hoặc nhóm record tùy yêu cầu hiệu năng và threat model. Không tự thiết kế thuật toán mã hóa; sử dụng thư viện và chế độ authenticated encryption đã được kiểm chứng.

## 6. Chọn thuật toán và lưu metadata mã hóa

Khi ứng dụng phải tự mã hóa payload trước khi ghi database, dùng authenticated encryption để vừa bảo mật nội dung vừa phát hiện dữ liệu bị sửa đổi. Một lựa chọn phổ biến là AES-GCM với nonce duy nhất cho mỗi lần mã hóa bằng cùng một key.

Các nguyên tắc:

- Không tái sử dụng nonce với cùng một AES-GCM key.
- Dùng thư viện mật mã chuẩn của nền tảng.
- Lưu nonce, authentication tag, ciphertext và key version theo format rõ ràng.
- Có version cho format mã hóa để hỗ trợ thay đổi thuật toán.
- Không tự cắt ghép ciphertext hoặc bỏ qua authentication tag.
- Không dùng mã hóa tự chế hoặc XOR/base64 như biện pháp bảo mật.
- Không dùng hash một chiều khi cần khôi phục credential để trả cho platform.

Ví dụ record lưu dữ liệu đã mã hóa:

~~~json
{
  "format_version": 1,
  "algorithm": "AES-256-GCM",
  "key_reference": "kms://broker/data-key",
  "key_version": "12",
  "wrapped_dek": "<base64-ciphertext-of-dek>",
  "nonce": "<base64-nonce>",
  "ciphertext": "<base64-encrypted-payload>"
}
~~~

Đây là cấu trúc minh họa. Trong triển khai thực tế, format cần được chuẩn hóa, xác thực đầu vào, giới hạn kích thước và quản lý version. Không đưa plaintext hoặc DEK vào log khi xử lý lỗi.

Nếu secret manager đã mã hóa và quản lý secret an toàn, broker thường không cần mã hóa lại secret bằng một khóa ứng dụng tự quản lý mà không có lý do rõ ràng. Mã hóa nhiều lớp chỉ có ích khi mỗi lớp có ranh giới quyền và mục đích độc lập; nếu không, nó làm tăng độ phức tạp rotation và phục hồi.

## 7. Lưu provider credentials

Provider credential cho phép broker gọi API quản trị. Đây thường là dữ liệu có quyền rộng và cần được bảo vệ nghiêm ngặt.

Ưu tiên theo thứ tự:

1. Workload identity hoặc managed identity, không lưu static secret.
2. Token ngắn hạn được cấp từ identity provider.
3. Secret manager với API key/client secret có rotation.
4. File credential mount chỉ khi môi trường yêu cầu và có quyền filesystem tối thiểu.

Provider credential nên được tách theo môi trường và account. Nếu broker phục vụ nhiều cloud account, mỗi account reference cần policy riêng. Không dùng một access key có quyền quản trị toàn bộ organization chỉ để giảm số cấu hình.

Ví dụ cấu hình Spring chỉ giữ metadata:

~~~yaml
broker:
  provider:
    credential-mode: workload-identity
    account-reference: cloud-account-a
    region: ap-southeast-1
~~~

Với provider chưa hỗ trợ workload identity:

~~~yaml
broker:
  provider:
    credential-mode: secret-manager
    account-reference: legacy-account
    secret-reference: secret://broker/providers/legacy-account/credential
~~~

Không đặt access key, secret key hoặc client secret trực tiếp trong YAML. Cấu hình chỉ tham chiếu tới nguồn secret đã được cấp quyền.

## 8. Lưu binding credentials và đáp ứng OSB API

Khi xử lý bind, broker thường tạo một user, role hoặc token riêng cho consumer rồi trả credentials trong response OSB API. Broker cần giữ khả năng quản lý vòng đời credential đó để hỗ trợ fetch/retrieval nếu offering công bố capability tương ứng.

Luồng bind gợi ý:

1. Xác thực platform và kiểm tra quyền bind trên service instance.
2. Tạo binding ID và binding record ở trạng thái CREATING.
3. Yêu cầu provider tạo principal/credential với quyền tối thiểu.
4. Lưu credentials vào secret manager dưới path của binding.
5. Lưu secret reference và version vào binding record.
6. Chuyển binding sang ACTIVE sau khi các bước cần thiết đã commit.
7. Trả response binding theo OSB API.

Ví dụ response có thể chứa credentials:

~~~json
{
  "credentials": {
    "username": "orders_app",
    "password": "<binding-secret>",
    "host": "pg.internal.example",
    "port": 5432,
    "database": "orders",
    "sslmode": "require"
  }
}
~~~

Response này chỉ chứa credential dành riêng cho consumer. Không trả provider API token, database admin password hoặc secret reference nội bộ.

### GET binding và bindings_retrievable

Nếu service offering công bố **bindings_retrievable=true**, broker cần có cách trả lại thông tin binding hiện hành qua endpoint GET binding. Vì vậy, chỉ lưu password hash là không đủ nếu response cần password gốc. Hash một chiều không thể khôi phục credential.

Có thể lưu credentials trong secret manager để lấy lại khi platform yêu cầu. Khi GET binding:

1. Xác thực caller và kiểm tra quyền trên instance/binding.
2. Tra cứu binding theo cả instance ID và binding ID.
3. Kiểm tra binding đang ACTIVE và chưa bị revoke.
4. Đọc đúng secret version hiện hành.
5. Xây dựng response chỉ gồm field được OSB API hỗ trợ.
6. Không tạo credential mới và không gọi provider bind lại chỉ vì GET.

Nếu không thể lưu hoặc tái tạo credentials an toàn, không công bố capability retrieval cho offering đó.

## 9. Không để secret đi vào log, trace hoặc error response

Một lỗi phổ biến là log toàn bộ request/response để debug. Response bind có thể chứa password; provider SDK exception có thể chứa Authorization header hoặc URL có token; HTTP client wiretap có thể ghi payload.

Cần có chính sách redaction tập trung:

- Không log Authorization header, Cookie, access token, refresh token hoặc private key.
- Không log body response bind chứa credentials.
- Không log object chứa secret bằng toString().
- Không đưa secret vào exception message hoặc error description của last_operation.
- Mask field nhạy cảm trong tracing và telemetry.
- Không đưa secret vào metric label.
- Không lưu raw request vào dead-letter queue nếu payload có secret.
- Không bật HTTP wire logging trong production nếu chưa có redaction đáng tin cậy.

Log nên ghi các thông tin đủ điều tra mà không tiết lộ secret:

~~~text
event=provider_credential_read
tenant_ref=org-orders
binding_id=binding-orders-204
secret_version=7
result=SUCCESS
correlation_id=trace-8c12
~~~

Không ghi giá trị password, token hoặc nội dung secret. Secret reference cũng có thể tiết lộ cấu trúc tenant; mask hoặc giới hạn quyền đọc log nếu cần.

## 10. Kiểm soát quyền truy cập secret

Áp dụng nguyên tắc least privilege ở cả hai lớp: broker authorization và secret manager policy.

**Broker authorization** xác minh caller có quyền trên tenant, instance và binding. **Secret manager authorization** xác minh workload identity của broker có quyền đọc đúng secret path.

Một quy trình GET binding nên đi theo thứ tự:

~~~mermaid
sequenceDiagram
    participant P as Platform
    participant B as Broker
    participant DB as Broker database
    participant SM as Secret manager

    P->>B: GET binding
    B->>B: Authenticate and authorize
    B->>DB: Find binding by instance + binding ID
    DB-->>B: ACTIVE + secret reference + version
    B->>SM: Read permitted secret version
    SM-->>B: Binding credentials
    B->>B: Build allowlisted response
    B-->>P: Binding response
~~~

Không đọc secret trước khi kiểm tra authorization. Nếu caller không có quyền, broker không nên gọi secret manager để tránh lộ dữ liệu qua side channel hoặc audit.

Các quyền gợi ý:

| Principal | Quyền |
|---|---|
| OSB request handler | Đọc secret binding sau khi authorization thành công |
| Provision worker | Đọc provider credential và ghi secret resource cần thiết |
| Binding worker | Tạo/ghi secret cho binding mà worker sở hữu |
| Reconciliation worker | Đọc metadata/secret cần thiết cho resource đang đối chiếu |
| Support/operator | Truy cập qua quy trình break-glass có phê duyệt và audit |
| Consumer application | Nhận credential binding của chính mình; không có quyền đọc secret manager |

Nếu secret manager hỗ trợ policy theo path/version, dùng policy hẹp. Nếu tất cả broker replica đều có quyền đọc mọi secret, cân nhắc tách worker role hoặc secret namespace theo tenant/provider account.

## 11. Rotation và versioning

Credentials cần được rotate khi hết hạn, theo lịch hoặc khi có dấu hiệu bị lộ. Rotation phải đồng bộ giữa provider, secret manager, database reference và consumer.

Một quy trình rotation an toàn khi provider hỗ trợ hai credential đồng thời:

1. Tạo credential mới tại provider với quyền giống credential hiện hành.
2. Ghi credential mới thành version mới trong secret manager.
3. Kiểm tra credential mới bằng một thao tác xác thực an toàn.
4. Cập nhật binding record sang secret version mới hoặc alias hiện hành.
5. Bảo đảm consumer/platform nhận được credential mới theo cơ chế của offering.
6. Theo dõi kết nối và lỗi xác thực.
7. Thu hồi credential cũ khi không còn consumer sử dụng.
8. Ghi audit record về version, actor và thời điểm.

Nếu provider chỉ cho phép một credential, cần có cửa sổ chuyển đổi hoặc cơ chế tạo principal thay thế. Không ghi đè secret cũ trước khi đã có phương án rollback và xác nhận credential mới hoạt động.

### Version và alias

Secret manager thường cung cấp version bất biến và alias như current/latest. Với operation đang chạy, nên lưu rõ version đã sử dụng để có thể tái hiện hoặc điều tra. Alias tiện cho lần đọc mới nhưng không nên là bằng chứng duy nhất về version đã dùng.

Khi rotate, binding record có thể lưu:

~~~json
{
  "credentials_secret_ref": "secret://broker/tenants/org-orders/bindings/binding-orders-204",
  "credential_version": 8,
  "credential_state": "ACTIVE"
}
~~~

Không xóa version cũ ngay nếu còn operation đang chạy hoặc cần rollback. Sau thời hạn retention, thu hồi hoặc xóa version theo chính sách.

## 12. Thu hồi secret khi unbind hoặc deprovision

Khi platform gọi unbind, broker phải thu hồi quyền của consumer tại provider. Chỉ xóa secret trong vault chưa đủ nếu user hoặc token ở provider vẫn còn hiệu lực.

Trình tự gợi ý:

1. Đánh dấu binding REVOKING để chặn GET binding mới.
2. Gọi provider disable/revoke principal hoặc token.
3. Xác nhận quyền truy cập không còn hiệu lực.
4. Xóa, disable hoặc đánh dấu secret hết hiệu lực theo policy.
5. Đánh dấu binding REVOKED.
6. Giữ metadata tối thiểu phục vụ audit và retry.

Khi deprovision service instance, cần xác định binding còn hoạt động và xử lý theo hợp đồng OSB API cùng chính sách provider. Không xóa secret và record quá sớm khiến broker mất dữ liệu cần thiết để retry thu hồi quyền.

Nếu provider revoke thành công nhưng broker không cập nhật được database, reconciliation phải phát hiện và hoàn tất trạng thái. Nếu secret manager không truy cập được, operation cần giữ trạng thái phù hợp để retry; không đánh dấu unbind thành công chỉ vì database đã xóa secret reference.

## 13. Backup, restore và disaster recovery

Secret manager và database broker có thể có backup lifecycle riêng. Cần bảo đảm backup được mã hóa và quyền restore được kiểm soát.

- Mã hóa backup database và snapshot bằng key được quản lý.
- Secret manager có versioning, replication và backup phù hợp với SLA.
- Giữ key metadata và KMS configuration cần thiết để giải mã backup.
- Hạn chế quyền restore vì restore có thể khôi phục secret đã bị revoke.
- Kiểm thử khôi phục trong môi trường cô lập.
- Sau restore, đối chiếu secret version với provider state trước khi mở traffic.
- Không đưa secret backup vào artifact hoặc bucket công khai.
- Có quy trình xử lý khi KMS key bị disable, scheduled deletion hoặc mất quyền truy cập.

### Tránh khôi phục credential đã bị thu hồi

Giả sử backup database từ tuần trước chứa secret reference version 4, trong khi credential đã được rotate lên version 6 và version 4 đã bị revoke. Sau restore, broker không được trả version 4 như credential hiện hành.

Cần đối chiếu binding state và version với secret manager/provider. Nếu credential cũ không còn hợp lệ, broker phải lấy version hiện hành đã được xác nhận hoặc đánh dấu binding cần reconciliation. Backup không được xem là nguồn có thẩm quyền hơn trạng thái thu hồi hiện tại.

## 14. Tích hợp secret manager với Spring

Nên đặt một abstraction giữa nghiệp vụ broker và nhà cung cấp secret. Nhờ đó, service instance/binding service không phụ thuộc trực tiếp vào API cụ thể của Vault hoặc cloud secret manager.

Ví dụ interface reactive:

~~~java
import java.util.Map;
import reactor.core.publisher.Mono;

public interface SecretStore {

    Mono<SecretVersion> write(
            String secretReference,
            Map<String, Object> value);

    Mono<Map<String, Object>> read(
            String secretReference,
            String version);

    Mono<Void> revoke(
            String secretReference,
            String version);
}

public record SecretVersion(
        String reference,
        String version
) {
}
~~~

Implementation có thể dùng Spring Cloud Vault, SDK của cloud secret manager hoặc HTTP client tới hệ thống secret nội bộ. Việc chọn thư viện phụ thuộc nền tảng triển khai và phiên bản Spring.

Ví dụ application service lưu credentials cho binding:

~~~java
import java.util.Map;
import reactor.core.publisher.Mono;

public class BindingCredentialService {

    private final SecretStore secretStore;
    private final BindingRepository bindingRepository;

    public BindingCredentialService(
            SecretStore secretStore,
            BindingRepository bindingRepository) {
        this.secretStore = secretStore;
        this.bindingRepository = bindingRepository;
    }

    public Mono<BindingRecord> persistCredentials(
            BindingRecord binding,
            Map<String, Object> credentials) {

        String reference = secretReferenceFor(
                binding.tenantId(), binding.bindingId());

        return secretStore.write(reference, credentials)
                .flatMap(secretVersion ->
                        bindingRepository.activate(
                                binding.bindingId(),
                                reference,
                                secretVersion.version()));
    }

    private String secretReferenceFor(
            String tenantId,
            String bindingId) {
        return "secret://broker/tenants/" + tenantId
                + "/bindings/" + bindingId;
    }
}
~~~

Đây là pseudocode minh họa. Trong implementation thực tế, cần xác minh tenant ID đã được broker xác thực và chuẩn hóa trước khi đưa vào path. Nếu secret write thành công nhưng database update thất bại, cần cleanup hoặc reconciliation để xử lý secret mồ côi. Nếu database update thành công nhưng secret write chưa hoàn tất, binding không được chuyển sang ACTIVE.

### Không block reactive request path

Nếu secret SDK chỉ cung cấp blocking API, không gọi trực tiếp trên WebFlux event loop. Có thể bọc bằng Mono.fromCallable và chạy trên boundedElastic, hoặc sử dụng client reactive phù hợp. Giới hạn concurrency và timeout để secret manager chậm không làm cạn thread hoặc queue của broker.

Không gọi subscribe() fire-and-forget để ghi secret. Hãy trả publisher cho caller để transaction/workflow có thể kiểm soát thành công, lỗi và retry.

## 15. Xử lý lỗi khi đọc và ghi secret

Secret manager là dependency bên ngoài nên có thể timeout, throttling hoặc từ chối quyền.

| Tình huống | Hướng xử lý |
|---|---|
| Secret không tồn tại | Trả lỗi nội bộ phù hợp; không tạo credential giả |
| Workload không có quyền | Dừng thao tác, cảnh báo policy và audit |
| Secret manager timeout | Retry có giới hạn với backoff và jitter |
| Provider tạo credential nhưng secret write lỗi | Giữ operation chưa hoàn tất; retry hoặc revoke credential mồ côi |
| Secret write thành công nhưng DB commit lỗi | Reconciliation/cleanup secret theo binding ID |
| KMS key bị disable | Dừng giải mã, cảnh báo key state; không bypass mã hóa |
| Secret version bị revoke | Không trả version cũ; xác minh version hiện hành |
| Payload không giải mã được | Ghi mã lỗi, correlation ID; không log plaintext |
| Rotation thất bại giữa chừng | Giữ version cũ còn hợp lệ theo policy, rollback hoặc tiếp tục reconcile |

Không retry vô hạn. Nếu lỗi là permission denied hoặc key disabled, retry liên tục không giải quyết được nguyên nhân. Nếu timeout xảy ra sau khi secret manager có thể đã ghi thành công, hãy tra cứu theo reference/version hoặc idempotency token trước khi ghi lại.

## 16. Audit và giám sát truy cập secret

Audit cần ghi nhận ai truy cập secret nào, vào lúc nào, cho operation nào và kết quả ra sao. Nội dung secret không thuộc audit record.

Một audit event gợi ý:

| Trường | Mục đích |
|---|---|
| actor/workload identity | Principal thực hiện truy cập |
| tenant reference | Tenant đã được xác minh |
| secret reference | ID đã mask hoặc định danh được phép ghi log |
| secret version | Phiên bản được đọc/ghi |
| action | READ, WRITE, ROTATE, REVOKE |
| binding/instance ID | Đối tượng nghiệp vụ liên quan |
| operation ID | Operation gây ra truy cập |
| result | SUCCESS hoặc DENIED/FAILED |
| timestamp | Thời điểm |
| correlation ID | Liên kết với trace/log |

Theo dõi các chỉ số:

- Số lần đọc secret theo workload và tenant.
- Số lần truy cập bị từ chối.
- Số secret sắp hết hạn hoặc chưa rotate.
- Số lần rotate thất bại.
- Số secret reference không có binding tương ứng.
- Số binding ACTIVE nhưng thiếu secret version.
- Thời gian phản hồi và tỷ lệ lỗi secret manager.
- Số lần KMS decrypt/unwrap theo workload.

Cảnh báo khi một workload đọc secret bất thường, một tenant có số lần fetch tăng đột biến hoặc một secret bị truy cập từ principal ngoài dự kiến. Không dùng secret ID hoặc tenant ID có độ phân biệt cao làm metric label nếu tạo cardinality lớn.

## 17. Kiểm thử bảo vệ credentials

Kiểm thử phải chứng minh secret được lưu, đọc và thu hồi đúng quyền, đồng thời không rò rỉ qua response không phù hợp, log hay exception.

| Ca kiểm thử | Kết quả mong đợi |
|---|---|
| Bind thành công | Secret được ghi và binding giữ đúng reference/version |
| Secret write thất bại | Binding không chuyển ACTIVE |
| Database commit thất bại sau secret write | Secret mồ côi được cleanup hoặc đưa vào reconciliation |
| GET binding hợp lệ | Chỉ trả credentials của đúng binding |
| Caller không có quyền | Bị từ chối trước khi đọc secret |
| Binding đã REVOKED | Không trả secret cũ |
| Secret version bị thu hồi | Không dùng version đã revoke |
| Provider credential hết hạn | Refresh theo policy, không log token |
| KMS decrypt bị từ chối | Không trả plaintext hoặc fallback bằng key yếu |
| Ciphertext bị sửa | Authenticated decryption thất bại |
| Rotation | Version mới được xác minh trước khi revoke version cũ |
| Backup restore | Không khôi phục credentials đã bị thu hồi thành trạng thái active |
| Log/trace/exception | Không chứa password, token, private key hoặc plaintext |
| Multi-tenant | Tenant A không thể đọc secret của tenant B |
| Secret manager timeout | Retry có giới hạn và operation giữ trạng thái đúng |

Nên có integration test với secret manager sandbox hoặc test container nếu nền tảng hỗ trợ. Mock SecretStore phù hợp cho unit test luồng nghiệp vụ, nhưng không xác minh IAM policy, KMS permission, TLS hoặc audit thực tế.

## 18. Checklist trước production

- Phân loại provider, binding, platform credentials và encryption keys.
- Dùng secret manager hoặc workload identity cho provider credential.
- Database nghiệp vụ chỉ lưu secret reference/version.
- TLS được bật cho mọi kết nối có secret.
- Database, secret store và backup được mã hóa phù hợp.
- KMS/HSM quản lý key; key không nằm cùng ciphertext.
- Envelope encryption dùng authenticated encryption và nonce đúng cách.
- Secret path tách theo tenant, provider và binding.
- Authorization được kiểm tra trước khi đọc secret.
- Quyền secret manager theo least privilege.
- Không log secret, token, Authorization header hoặc response bind.
- Rotation có version, kiểm tra, rollback và thu hồi.
- Unbind/deprovision thu hồi cả provider principal và secret.
- Restore không làm sống lại credential đã bị revoke.
- Có audit và cảnh báo truy cập bất thường.
- Có test cho allow/deny, rotation, KMS failure, timeout và data leak.

## Kết luận

Credentials của service broker phải được quản lý như tài sản bảo mật có vòng đời riêng. Hãy lưu provider và binding secret trong secret manager, chỉ giữ reference/version trong database nghiệp vụ, mã hóa dữ liệu khi truyền và khi lưu, dùng KMS/HSM cho key, kiểm soát quyền đọc theo workload và tenant, đồng thời thiết kế rotation, revoke, backup, audit và recovery. Trong Spring Cloud Service Broker, một abstraction như **SecretStore** giúp application service thao tác secret nhất quán mà không phụ thuộc vào một nhà cung cấp cụ thể. Khi kết hợp với authorization trước khi đọc, response allowlist và quy trình bind/unbind có kiểm soát, broker có thể trả credentials cần thiết cho OSB platform mà vẫn hạn chế rò rỉ và quyền truy cập ngoài phạm vi.

## Tài liệu tham khảo

- [Spring Cloud Vault Reference](https://docs.spring.io/spring-cloud-vault/reference/) — tích hợp ứng dụng Spring với HashiCorp Vault.
- [Spring Boot Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html) — quản lý cấu hình từ nguồn bên ngoài.
- [HashiCorp Vault Documentation](https://developer.hashicorp.com/vault/docs) — secret engines, policy, lease, audit và rotation.
- [AWS Secrets Manager Documentation](https://docs.aws.amazon.com/secretsmanager/latest/userguide/intro.html) — lưu trữ, truy xuất và rotate secret.
- [Google Secret Manager Documentation](https://cloud.google.com/secret-manager/docs) — secret version, IAM và audit.
- [Azure Key Vault Documentation](https://learn.microsoft.com/en-us/azure/key-vault/general/overview) — secret, key và certificate management.
- [OWASP Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html) — nguyên tắc quản lý vòng đời secret.
- [NIST SP 800-57 Part 1](https://csrc.nist.gov/pubs/sp/800/57/pt1/r5/final) — khuyến nghị quản lý khóa mật mã.
- [Open Service Broker API Specification](https://github.com/openservicebrokerapi/servicebroker/blob/master/spec.md) — service binding, credentials và bindings_retrievable.

