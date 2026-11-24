# Tích hợp OCI Vault và nguồn cấu hình bí mật

Ứng dụng Spring Boot thường cần mật khẩu database, API token, khóa ký, thông tin xác thực SMTP hoặc credential để gọi một dịch vụ khác. Nếu lưu các giá trị này trong source code, application.yaml hoặc image container, chúng có thể bị lộ qua Git, build log, artifact, backup hoặc quyền truy cập không cần thiết.

Oracle Cloud Infrastructure (OCI) Vault cung cấp nơi lưu trữ và quản lý secret tập trung. Spring Cloud OCI Vault starter kết nối dịch vụ này với Spring theo hai cách: đưa secret vào Spring Environment như một property source, hoặc cung cấp VaultTemplate để ứng dụng truy xuất secret khi cần.

Hai cách dùng giải quyết hai nhu cầu khác nhau. Property source phù hợp với cấu hình được nạp cùng ứng dụng; VaultTemplate phù hợp với thao tác lấy secret theo yêu cầu và quản lý vòng đời secret. Cả hai đều cần identity và IAM policy đúng, kế hoạch rotation, cache hợp lý và cách xử lý khi Vault tạm thời không truy cập được.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt OCI Vault, encryption key, secret và secret bundle.
2. Chọn đúng Spring Cloud OCI Vault starter.
3. Cấu hình Vault như một nguồn property cho Spring Environment.
4. Inject secret vào cấu hình ứng dụng mà không ghi giá trị bí mật vào repository.
5. Dùng VaultTemplate để truy xuất secret theo nhu cầu.
6. Hiểu secret version, rotation state và quy trình promote version.
7. Thiết kế refresh, cache và rotation cho singleton bean/connection pool.
8. Cấp IAM policy chỉ cho phép workload đọc đúng secret cần thiết.
9. Phân biệt quyền đọc secret với quyền quản trị Vault và encryption key.
10. Xử lý timeout, 401, 403, secret chưa tồn tại và Vault unavailable.
11. Kiểm thử property source, VaultTemplate, rotation và least privilege.
12. Vận hành secret an toàn qua local development, CI/CD và production.

## 2. OCI Vault gồm những thành phần nào?

Tên gọi Vault thường được dùng cho cả dịch vụ và nơi chứa secret, nhưng cần phân biệt một số khái niệm:

- **Vault:** tài nguyên trong OCI Key Management Service, nơi quản lý encryption key và các cấu hình liên quan.
- **Key:** khóa mã hóa được dùng để bảo vệ dữ liệu/secret theo cấu hình dịch vụ.
- **Secret:** tài nguyên logic đại diện cho một giá trị nhạy cảm, ví dụ database password hoặc API token.
- **Secret version:** một phiên bản nội dung của secret. Khi nội dung thay đổi, OCI tạo version mới.
- **Secret bundle:** dữ liệu trả về khi đọc secret, gồm nội dung secret, thông tin version và metadata liên quan.
- **Secret Management Service:** API quản lý secret và API đọc secret bundle. Hai nhóm operation có endpoint riêng.

~~~mermaid
flowchart TD
    A[OCI Vault] --> B[Encryption Key]
    A --> C[Secret Management]
    C --> D[Secret: invoice-db-password]
    D --> E[Version 1: PREVIOUS]
    D --> F[Version 2: CURRENT]
    D --> G[Version 3: PENDING]
    F --> H[Secret Bundle]
    H --> I[Spring Cloud OCI Vault]
    I --> J[Spring Environment]
    I --> K[VaultTemplate]
    J --> L[Spring Boot configuration]
    K --> M[Application service]
~~~

Một ứng dụng chỉ đọc secret thường cần quyền đọc secret bundle. Nó không nhất thiết cần quyền tạo Vault, tạo encryption key, rotate key hoặc xóa secret. Tách quyền runtime khỏi quyền quản trị để giảm phạm vi ảnh hưởng khi credential của ứng dụng bị lộ.

### Vault không phải nơi lưu mọi loại dữ liệu

Chọn dịch vụ theo loại dữ liệu:

| Dữ liệu | Dịch vụ phù hợp |
| --- | --- |
| Password, API token, credential | OCI Vault Secret |
| Encryption key cần quản lý vòng đời | OCI Key Management/Vault |
| File PDF, ảnh, archive | OCI Object Storage |
| Dữ liệu nghiệp vụ có truy vấn | Database |
| Cấu hình không nhạy cảm | Spring configuration, Config Server hoặc nguồn cấu hình phù hợp |

Không đưa file lớn hoặc dữ liệu nghiệp vụ thông thường vào secret chỉ vì Vault có thể lưu chuỗi.

## 3. Chọn Spring Cloud OCI Vault starter

Maven:

~~~xml
<dependency>
    <groupId>com.oracle.cloud.spring</groupId>
    <artifactId>spring-cloud-oci-starter-vault</artifactId>
    <version>${spring-cloud-oci.version}</version>
</dependency>
~~~

Gradle:

~~~groovy
dependencies {
    implementation("com.oracle.cloud.spring:spring-cloud-oci-starter-vault:${springCloudOciVersion}")
}
~~~

Version starter phải tương thích với Spring Boot và Spring Cloud OCI release line mà ứng dụng đang dùng. Không lấy version của Spring Cloud release train hoặc Oracle Database starter để gán cho OCI Vault starter. Kiểm tra release notes và dependency graph của đúng version.

Vault starter dựa trên core authentication của Spring Cloud OCI. Nếu ứng dụng đã có service starter khác kéo core vào, kiểm tra dependency graph trước khi khai báo core thêm lần nữa.

## 4. Cấu hình OCI Vault

Spring Cloud OCI Vault có thể dùng chung OCI authentication, region và compartment đã cấu hình ở core starter. Ngoài ra, Vault integration cần biết compartment và Vault OCID.

Các property chính:

| Property | Ý nghĩa | Bắt buộc |
| --- | --- | --- |
| spring.cloud.oci.vault.enabled | Bật/tắt OCI Vault integration | Không; mặc định true theo tài liệu starter |
| spring.cloud.oci.vault.compartment | Compartment cho Vault API và property sources | Có |
| spring.cloud.oci.vault.vault-id | Vault OCID dùng cho Vault API | Có khi dùng VaultTemplate/API theo cấu hình |
| spring.cloud.oci.vault.property-refresh-interval | Chu kỳ refresh property source | Không; mặc định 10m |
| spring.cloud.oci.vault.property-sources | Danh sách Vault dùng làm Spring property source | Không |
| spring.cloud.oci.vault.property-sources[i].vault-id | Vault OCID của một property source | Có với từng entry |

Ví dụ cấu hình cơ bản:

~~~yaml
spring:
  cloud:
    oci:
      config:
        type: INSTANCE_PRINCIPAL
      region:
        static: ${OCI_REGION}
      vault:
        enabled: true
        compartment: ${OCI_COMPARTMENT_OCID}
        vault-id: ${OCI_VAULT_OCID}
~~~

Các giá trị in hoa trong ví dụ là placeholder. Trong ứng dụng thật, truyền chúng qua environment variables, secret mount hoặc cấu hình deployment. Không commit OCID môi trường thật hoặc secret content vào repository nếu chính sách tổ chức coi chúng là thông tin nhạy cảm.

### Region và compartment

- Region phải khớp region chứa Vault và secret.
- Compartment property là mặc định cho các operation Vault integration sử dụng property này.
- Secret có thể nằm trong compartment khác với Vault resource; kiểm tra scope thực tế của secret và policy.
- Property compartment không tự cấp IAM permission.
- Nếu ứng dụng truy cập nhiều region hoặc nhiều Vault, cấu hình từng nguồn rõ ràng.

### Chọn authentication

Các kiểu authentication phổ biến:

| Môi trường | Cách xác thực gợi ý |
| --- | --- |
| Máy developer | FILE hoặc SESSION_TOKEN |
| OCI Compute | INSTANCE_PRINCIPAL |
| OCI Functions | RESOURCE_PRINCIPAL |
| OKE | WORKLOAD_IDENTITY nếu cluster/workload đã cấu hình |
| CI ngoài OCI | Identity/federation được tổ chức phê duyệt |

Không dùng API key cá nhân của developer làm credential dài hạn cho workload production nếu có thể dùng workload identity.

## 5. Dùng Vault như Spring property source

Đây là cách đơn giản để đưa secret vào Spring Environment. Starter tải secret từ các Vault được khai báo trong property-sources; tên secret trở thành tên property.

Ví dụ:

~~~yaml
spring:
  cloud:
    oci:
      config:
        type: INSTANCE_PRINCIPAL
      region:
        static: ${OCI_REGION}
      vault:
        enabled: true
        compartment: ${OCI_COMPARTMENT_OCID}
        property-refresh-interval: 10m
        property-sources:
          - vault-id: ${OCI_VAULT_OCID}
~~~

Giả sử Vault có secret tên invoice-db-password. Ứng dụng có thể đọc property bằng Spring:

~~~java
@Configuration
public class DatabaseCredentialConfig {

    @Value("${invoice-db-password}")
    private String databasePassword;

    // Dùng databasePassword khi cấu hình DataSource
}
~~~

Trong ví dụ thực tế, tên secret phải tuân thủ naming convention của tổ chức và tương thích cách Spring property resolution xử lý tên. Nên dùng tên đơn giản, nhất quán, tránh tạo nhiều secret có tên chỉ khác chữ hoa/chữ thường hoặc dấu phân cách.

### 5.1. Property source hoạt động như thế nào?

Quy trình khái quát:

1. Spring Boot khởi động và nạp cấu hình.
2. OCI authentication provider tạo danh tính cho ứng dụng.
3. Vault integration gọi Secret Management API.
4. Secret bundle được lấy và giải mã nội dung theo SDK/starter.
5. Secret được đưa vào Spring Environment dưới tên property tương ứng.
6. Bean có thể resolve property qua @Value hoặc @ConfigurationProperties.

Giá trị trong Spring Environment là plaintext trong bộ nhớ ứng dụng. Vault bảo vệ dữ liệu khi lưu trữ và truyền tải; nó không làm cho secret biến mất khỏi heap, debugger, heap dump hoặc process memory sau khi ứng dụng đã đọc.

### 5.2. Nhiều Vault/property source

Ứng dụng có thể khai báo nhiều Vault trong property-sources:

~~~yaml
spring:
  cloud:
    oci:
      vault:
        enabled: true
        compartment: ${OCI_COMPARTMENT_OCID}
        property-sources:
          - vault-id: ${OCI_APPLICATION_VAULT_OCID}
          - vault-id: ${OCI_DATABASE_VAULT_OCID}
~~~

Tách Vault theo môi trường, domain hoặc quyền truy cập giúp quản lý ownership. Tuy nhiên, nếu hai Vault chứa secret trùng tên, cần xác định rõ thứ tự và quy tắc precedence của PropertySource trong version đang dùng. Không để ứng dụng phụ thuộc vào tên trùng mà không có test xác nhận.

### 5.3. Refresh property source

Tài liệu Spring Cloud OCI mô tả property-refresh-interval là chu kỳ reload property từ Vault. Giá trị mặc định là 10 phút; đặt duration lớn hơn 0 để bật refresh theo chu kỳ. Ví dụ 10000ms tương đương 10 giây:

~~~yaml
spring:
  cloud:
    oci:
      vault:
        property-refresh-interval: 10m
~~~

Chu kỳ quá ngắn làm tăng số lần gọi Secret Management API, tải hệ thống và nguy cơ throttling. Chu kỳ quá dài khiến ứng dụng tiếp tục giữ giá trị cũ sau khi secret được rotate.

Chọn interval dựa trên:

- Tần suất rotation.
- Mức độ khẩn cấp khi thu hồi credential.
- Số instance/replica.
- Rate limit và latency của OCI API.
- Khả năng reconnect/recreate client.
- Mức chấp nhận thời gian tồn tại của credential cũ.

Refresh property source không đồng nghĩa mọi object đã inject secret đều tự thay đổi. Một singleton bean có trường @Value thường giữ giá trị được inject lúc tạo bean. Với credential của DataSource, HTTP client hoặc SDK client, cần cơ chế refresh/recreate cụ thể hoặc đọc giá trị động qua một abstraction được quản lý. Kiểm thử rotation trên bean thực tế, không chỉ kiểm tra Environment đã nhận giá trị mới.

## 6. Dùng VaultTemplate để truy xuất secret theo yêu cầu

Vault starter tự cấu hình VaultTemplate bean trong Spring ApplicationContext. Có thể dùng template khi service cần lấy secret theo tên trong lúc chạy hoặc cần thực hiện các operation quản lý secret được cấp quyền.

Ví dụ cấu hình:

~~~yaml
spring:
  cloud:
    oci:
      config:
        type: INSTANCE_PRINCIPAL
      region:
        static: ${OCI_REGION}
      vault:
        enabled: true
        compartment: ${OCI_COMPARTMENT_OCID}
        vault-id: ${OCI_VAULT_OCID}
~~~

Ví dụ đọc secret:

~~~java
@Service
public class SecretLookupService {

    private final VaultTemplate vaultTemplate;

    public SecretLookupService(VaultTemplate vaultTemplate) {
        this.vaultTemplate = vaultTemplate;
    }

    public String getSecretByName(String secretName) {
        GetSecretBundleByNameResponse bundle =
                vaultTemplate.getSecret(secretName);

        return vaultTemplate.decodeBundle(bundle);
    }
}
~~~

Tên class và method ở ví dụ theo API được tài liệu Spring Cloud OCI công bố; xác minh import/package trong Javadoc của release đang dùng.

### 6.1. Vì sao có decodeBundle?

Secret bundle có thể chứa nội dung được mã hóa Base64 theo format secret content. VaultTemplate cung cấp decodeBundle để lấy nội dung đã giải mã theo cách tích hợp của starter.

Không tự lấy một trường response rồi giả định đó là plaintext. Không decode Base64 hai lần. Dùng đúng API của starter và kiểm tra format của secret đã tạo.

### 6.2. Khi nào nên dùng VaultTemplate?

Phù hợp khi:

- Tên secret được xác định theo tenant hoặc workload.
- Ứng dụng cần lấy secret theo operation thay vì nạp tất cả lúc startup.
- Có nhiều credential với vòng đời khác nhau.
- Cần chủ động đọc version hoặc kiểm soát thời điểm refresh theo API hỗ trợ.
- Một integration adapter cần che giấu chi tiết OCI Vault khỏi business service.

Không nên gọi Vault cho mỗi HTTP request nếu credential có thể được cache an toàn theo thời hạn. Mỗi lần gọi Vault làm tăng latency, phụ thuộc mạng và lượng API request.

### 6.3. Giữ VaultTemplate trong adapter

Không để domain service phụ thuộc trực tiếp vào OCI SDK response. Tạo interface nội bộ:

~~~java
public interface SecretProvider {
    String getRequiredSecret(String name);
}
~~~

Adapter triển khai interface và dùng VaultTemplate:

~~~java
@Component
public class OciVaultSecretProvider implements SecretProvider {

    private final VaultTemplate vaultTemplate;

    public OciVaultSecretProvider(VaultTemplate vaultTemplate) {
        this.vaultTemplate = vaultTemplate;
    }

    @Override
    public String getRequiredSecret(String name) {
        GetSecretBundleByNameResponse bundle =
                vaultTemplate.getSecret(name);

        return vaultTemplate.decodeBundle(bundle);
    }
}
~~~

Business service chỉ biết SecretProvider. Unit test có thể mock interface mà không cần gọi OCI.

## 7. VaultTemplate và quyền quản trị secret

VaultTemplate hỗ trợ thao tác với secret như tạo, cập nhật, liệt kê và xóa theo khả năng của module. Nhưng một ứng dụng runtime chỉ cần đọc password không nên được cấp quyền quản trị toàn bộ secret.

Tách trách nhiệm:

| Workload | Quyền cần cân nhắc |
| --- | --- |
| Business API runtime | Đọc secret bundle cần thiết |
| Rotation job | Tạo version mới/promote/rotate theo quy trình |
| Platform provisioning | Tạo Vault, key, secret và policy |
| Auditor | Đọc metadata/audit theo quyền được cấp; tránh đọc nội dung secret nếu không cần |

Nếu dùng VaultTemplate chỉ để đọc, cấp quyền read secret-bundles cho workload. Nếu ứng dụng còn tạo hoặc cập nhật secret, cấp thêm quyền riêng cho operation đó và xem xét tách thành một service/job quản trị.

Không cấp quyền delete hoặc manage secrets cho mọi replica chỉ vì template có API quản trị.

## 8. OCI IAM policy cho workload đọc secret

OCI Secret Management tích hợp IAM. Một dynamic group hoặc user group cần policy cho phép đọc secret bundle.

Ví dụ Instance Principal chỉ được đọc một secret:

~~~text
Allow dynamic-group InvoiceComputeInstances to read secret-bundles in compartment InvoiceSecrets where target.secret.id = 'SECRET_OCID'
~~~

Nếu workload cần đọc nhiều secret trong một compartment:

~~~text
Allow dynamic-group InvoiceComputeInstances to read secret-bundles in compartment InvoiceSecrets
~~~

Ví dụ Resource Principal cho Function:

~~~text
Allow dynamic-group InvoiceFunctions to read secret-bundles in compartment InvoiceSecrets where target.secret.id = 'SECRET_OCID'
~~~

Các statement trên minh họa scope. Thay tên dynamic group, compartment và OCID bằng giá trị thực; kiểm tra policy grammar và identity domain của tenancy. Giới hạn theo target.secret.id khi workload chỉ cần một secret.

### Quyền đọc secret khác quyền dùng encryption key

Đọc secret bundle và quản lý encryption key là các permission/resource type khác nhau. Ứng dụng thường không cần quyền tạo, rotate hoặc xóa key chỉ để lấy secret. Cấu hình Vault/key access theo yêu cầu của OCI Secret Management và policy reference; không cấp thêm quyền key management theo suy đoán.

### Secret compartment và Vault compartment

Secret và Vault có thể được di chuyển/quản lý trong các compartment riêng. Policy phải được viết theo compartment chứa secret và resource scope thực tế. Di chuyển secret sang compartment khác có thể làm policy cũ không còn áp dụng. Không suy ra quyền đọc secret chỉ từ việc principal có quyền trên Vault resource.

## 9. Secret version và rotation state

Mỗi secret có ít nhất một version. Khi nội dung thay đổi, OCI tạo version mới. Version number tăng dần; version có thể được xác định bằng số, tên hoặc rotation state.

Các rotation state thường gặp:

| State | Ý nghĩa |
| --- | --- |
| CURRENT | Version đang được dùng để truy cập target system |
| PENDING | Version đã được tạo nhưng chưa đưa vào sử dụng |
| PREVIOUS | Version trước đó |
| DEPRECATED | Version không còn được dùng làm credential hiện hành |
| LATEST | Version mới nhất theo tiêu chí version, có thể chưa phải CURRENT |

Ứng dụng thông thường cần CURRENT. Không nhầm LATEST với CURRENT: một version mới nhất có thể đang PENDING và chưa được target system chấp nhận.

### 9.1. Tạo version mới

Khi cập nhật secret content, OCI tạo secret version mới. Có thể tạo version ở trạng thái PENDING để kiểm tra trước khi đưa vào sử dụng.

Quy trình minh họa:

1. Tạo credential mới trên target system hoặc khởi động quy trình rotation của target.
2. Tạo secret version mới trong Vault.
3. Đặt version mới ở PENDING nếu cần staging.
4. Kiểm tra ứng dụng hoặc test job có thể dùng credential mới.
5. Đồng bộ target system và secret version theo quy trình rotation.
6. Promote version đã sẵn sàng thành CURRENT.
7. Refresh/recreate client hoặc connection pool.
8. Theo dõi authentication failure.
9. Chỉ retire credential cũ khi không còn consumer nào dùng.

Thứ tự chính xác phụ thuộc target system và cơ chế auto-rotation. Không promote một password mới trước khi database/API target thực sự chấp nhận password đó.

### 9.2. Rollback

Nếu version mới không hoạt động:

- Kiểm tra target system còn chấp nhận credential cũ không.
- Promote version phù hợp trở lại CURRENT nếu quy trình cho phép.
- Refresh/recreate client đang giữ credential cũ/mới.
- Theo dõi lỗi kết nối và audit.
- Không xóa version cũ ngay khi vừa rotate.

Rollback chỉ thành công nếu target system còn chấp nhận credential tương ứng. Việc đổi CURRENT trong Vault không tự đổi password trên database hoặc dịch vụ đích.

### 9.3. Scheduled deletion

OCI hỗ trợ lên lịch xóa secret hoặc secret version. Secret đang pending deletion có thể khiến workload phụ thuộc vào nó mất khả năng truy cập; secret version đã schedule deletion cũng không còn phù hợp cho rotation/update thông thường. Việc xóa cuối cùng là không thể đảo ngược sau khi hết thời gian chờ.

Không schedule deletion secret đang được ứng dụng sử dụng. Trước khi xóa, xác minh không còn workload, deployment, replica hoặc rollback procedure nào phụ thuộc vào secret đó.

## 10. Thiết kế rotation cho ứng dụng Spring Boot

Rotation không chỉ là thay một chuỗi trong Vault. Ứng dụng có thể đã tạo DataSource, HTTP client hoặc SDK client với credential cũ.

### Credential được nạp lúc startup

Ví dụ DataSource nhận password khi bean được tạo. Khi property source refresh, DataSource hiện tại không nhất thiết tự mở lại pool bằng password mới.

Cần thiết kế một trong các cách:

- Refresh/recreate DataSource hoặc connection pool có kiểm soát.
- Dùng pool hỗ trợ cập nhật credential theo cơ chế được xác minh.
- Tạo credential overlap để credential cũ và mới cùng hợp lệ trong giai đoạn chuyển tiếp.
- Triển khai rolling restart sau khi secret CURRENT đã thay đổi.
- Dùng dynamic credential provider nếu target service và integration hỗ trợ.

Không thay password trên database rồi kỳ vọng mọi connection đang mở tự nhận password mới.

### Credential lấy theo yêu cầu

Với VaultTemplate, adapter có thể đọc secret khi cần. Nhưng gọi Vault trên mỗi operation vẫn có chi phí. Có thể cache giá trị trong bộ nhớ với TTL phù hợp, nhưng phải có:

- TTL ngắn hơn thời hạn rotation/revocation mà hệ thống chấp nhận.
- Cơ chế invalidate khi rotation.
- Giới hạn số lần retry khi Vault unavailable.
- Không ghi cache ra disk hoặc distributed cache không được bảo vệ.
- Không log giá trị khi cache miss hoặc decode lỗi.

### Rotation nhiều replica

Nếu có nhiều instance:

1. Đảm bảo target system chấp nhận credential mới.
2. Promote version mới thành CURRENT.
3. Chờ property source refresh hoặc chủ động refresh từng instance.
4. Recreate/reconnect client theo cơ chế ứng dụng.
5. Xác minh tất cả replica dùng credential mới.
6. Chỉ sau đó thu hồi credential cũ.

Không thu hồi credential cũ ngay sau khi promote CURRENT nếu replica vẫn còn cache hoặc connection pool cũ.

## 11. Property source, VaultTemplate hay secret mount?

Ba cách có thể cùng tồn tại nhưng có trade-off khác nhau.

| Cách | Ưu điểm | Hạn chế |
| --- | --- | --- |
| Vault property source | Tích hợp trực tiếp Spring Environment; cấu hình đơn giản | Secret được nạp vào Environment; bean đã inject có thể cần refresh riêng |
| VaultTemplate | Lấy secret theo yêu cầu; adapter chủ động kiểm soát cache/version | Cần code xử lý lỗi, cache và lifecycle |
| Secret mount/env injection | Ứng dụng không cần gọi Vault API trực tiếp | Rotation và file/environment refresh phụ thuộc platform/sidecar/deployment |

Chọn một đường đọc chính cho mỗi loại credential. Tránh vừa đọc property source, vừa VaultTemplate, vừa mount cùng một secret với ba quy tắc precedence khác nhau.

Với ứng dụng dùng Spring Cloud OCI, property source và VaultTemplate là hai tính năng có sẵn trong Vault starter. Secret mount là lựa chọn của deployment/runtime và có thể được phối hợp nếu có yêu cầu.

## 12. Precedence của Spring configuration

Spring Environment có nhiều PropertySource: command-line arguments, system properties, environment variables, application config, profile config và property sources được thêm bởi integration.

Khi cùng một key xuất hiện ở nhiều nguồn, nguồn có precedence cao hơn sẽ được chọn. Vì vậy cần quy định rõ secret có được override bằng environment variable hoặc test profile hay không.

Nguyên tắc:

- Không để secret production bị ghi đè vô tình bởi config mặc định.
- Không để test profile vô tình dùng credential production.
- Không in Environment hoặc configuration properties chứa secret vào log.
- Không expose Actuator env/configprops endpoint công khai.
- Kiểm tra precedence bằng integration test với secret giả.
- Tránh khai báo cùng tên secret ở nhiều Vault nếu chưa xác định rõ thứ tự.

Trong production, nên có một nguồn authoritative cho mỗi secret. Việc override thủ công cần được audit và giới hạn.

## 13. Bảo vệ secret trong ứng dụng

Khi secret đã được đọc vào JVM, ứng dụng cần bảo vệ nó như dữ liệu nhạy cảm.

Không:

- Commit secret vào Git.
- Đưa secret vào Docker build ARG hoặc image layer.
- In secret vào log, exception hoặc trace.
- Ghi secret vào metric label.
- Trả secret trong REST response hoặc error detail.
- Lưu secret vào file tạm không được bảo vệ.
- Ghi secret vào heap dump hoặc support bundle không kiểm soát.
- Gửi secret qua ticket/chat không được phê duyệt.

Nên:

- Dùng workload identity và least privilege.
- Giữ secret trong memory càng ngắn càng tốt nếu có thể.
- Mask giá trị trong log/test report.
- Dùng TLS và kiểm soát network path.
- Giới hạn quyền đọc secret ở từng service identity.
- Xoay credential và thu hồi credential cũ theo quy trình.
- Audit ai đọc, ai thay đổi và ai promote version.
- Phân tách quyền runtime khỏi quyền quản trị.

### Secret trong exception

Không đưa secret value vào exception message. Khi log lỗi, chỉ log secret name/OCID đã được phân loại phù hợp, operation, status code và request ID. Tên secret/OCID cũng có thể là metadata nhạy cảm theo policy tổ chức.

## 14. Xử lý lỗi và tính sẵn sàng

Vault là dependency bên ngoài. Ứng dụng phải quyết định hành vi khi không thể lấy secret.

| Lỗi | Hành vi gợi ý |
| --- | --- |
| 401 NotAuthenticated | Kiểm tra identity provider, token/signature và clock |
| 403 NotAuthorized | Kiểm tra policy read secret-bundles và compartment/secret scope |
| 404 NotFound | Kiểm tra vault-id, secret name, region và secret lifecycle |
| 429/throttling | Backoff có jitter, giới hạn retry và giảm refresh frequency |
| 5xx/service unavailable | Retry có giới hạn; dùng cache hợp lệ nếu policy cho phép |
| Timeout/network error | Timeout ngắn, retry budget rõ, circuit breaker nếu phù hợp |
| Decode/content format error | Kiểm tra secret type template và không tự decode nhiều lần |
| Secret hết hạn/target credential bị thu hồi | Rotation/recovery theo target system; không retry vô hạn |

### Fail fast hay dùng cache?

Với credential cần thiết để ứng dụng khởi động, có thể fail fast nếu không lấy được secret hợp lệ. Điều này tránh service khởi động với cấu hình thiếu hoặc credential mặc định không an toàn.

Với credential chỉ dùng cho một tác vụ tùy chọn, có thể giữ cache còn hiệu lực trong thời gian ngắn nếu policy cho phép. Không tiếp tục dùng cache vô thời hạn sau khi secret đã bị thu hồi.

Không dùng fallback password mặc định khi Vault unavailable. Nếu secret không lấy được, fail theo cách an toàn và phát cảnh báo phù hợp.

### Retry và circuit breaker

- Retry chỉ lỗi transient.
- Không retry 401/403/404 hoặc lỗi format vô hạn.
- Backoff có jitter.
- Giới hạn tổng thời gian chờ.
- Không tạo request storm khi nhiều replica cùng refresh.
- Có thể dùng jitter giữa các lần refresh.
- Theo dõi refresh failure và tuổi của secret cache.

## 15. Kiểm thử OCI Vault integration

### Unit test

Mock SecretProvider/VaultTemplate boundary để kiểm tra:

- Service xử lý secret có/không có.
- Cache TTL và invalidate.
- Mapping lỗi OCI sang lỗi nội bộ.
- Secret không xuất hiện trong log.
- Retry chỉ với lỗi transient.

### Context test

Kiểm tra Vault starter tạo bean và property source trong cấu hình test. Dùng secret giả hoặc test profile; không dùng secret production.

### Integration test với OCI test compartment

1. Tạo Vault và encryption key test.
2. Tạo secret chứa giá trị giả.
3. Cấp policy read secret-bundles cho test identity.
4. Cấu hình Spring Cloud OCI Vault starter.
5. Xác minh property source resolve secret.
6. Xác minh VaultTemplate đọc và decode secret.
7. Cập nhật secret version.
8. Kiểm tra refresh behavior.
9. Kiểm tra policy negative test.
10. Dọn resource test theo quy trình.

### Rotation test

- Tạo version mới ở PENDING.
- Xác minh ứng dụng vẫn đọc CURRENT cũ.
- Promote version mới thành CURRENT.
- Chờ refresh hoặc kích hoạt refresh theo thiết kế.
- Kiểm tra bean/client thực tế dùng credential mới.
- Xác minh replica cũ không tiếp tục dùng credential đã thu hồi.
- Kiểm tra rollback nếu target vẫn chấp nhận credential trước đó.

Không chỉ test rằng Environment trả về chuỗi mới. Phải kiểm tra DataSource/HTTP client có thực sự reconnect bằng credential mới.

## 16. Observability cho Vault

Theo dõi các tín hiệu không chứa secret value:

| Metric/log | Ý nghĩa |
| --- | --- |
| vault_secret_read_total | Số lần đọc secret |
| vault_secret_read_failure_total | Số lần đọc thất bại |
| vault_secret_read_duration | Latency lấy secret |
| vault_property_refresh_total | Số lần refresh property source |
| vault_property_refresh_failure_total | Số lần refresh lỗi |
| vault_secret_cache_age | Tuổi giá trị secret trong cache |
| vault_secret_version | Version metadata nếu được phép ghi nhận |
| vault_auth_failure_total | Lỗi authentication |
| vault_authorization_failure_total | Lỗi policy |
| vault_throttling_total | Số lần bị throttling |

Log nên có:

- Operation và thời điểm.
- Service/region.
- Secret alias đã được phép log.
- HTTP status/error code.
- OCI request ID.
- Correlation ID.
- Refresh success/failure và version metadata phù hợp.

Không log secret content, encoded content, Authorization header, token hoặc toàn bộ secret bundle response.

## 17. Bài thực hành: đưa database password vào OCI Vault

**Bối cảnh:** Invoice Service chạy trên OCI Compute. Ứng dụng kết nối Oracle Database và cần password từ OCI Vault. Developer local dùng FILE profile; production dùng Instance Principal. Khi password được rotate, ứng dụng cần chuyển sang version mới mà không làm gián đoạn kéo dài.

### Phần A — Tạo secret

1. Tạo Vault và encryption key trong compartment bảo mật.
2. Tạo secret tên invoice-db-password.
3. Lưu password giả của database test.
4. Xác minh secret có version CURRENT.
5. Ghi lại Vault OCID và Secret OCID trong tài liệu cấu hình nội bộ được bảo vệ.

### Phần B — Cấu hình Spring Cloud OCI

1. Thêm spring-cloud-oci-starter-vault đúng version tương thích.
2. Cấu hình region, compartment và Vault OCID.
3. Dùng FILE cho local.
4. Dùng INSTANCE_PRINCIPAL cho Compute.
5. Cấp policy read secret-bundles giới hạn đúng secret OCID.
6. Xác minh application context khởi động.

### Phần C — Nạp secret

1. Cấu hình property-sources trỏ tới Vault.
2. Resolve invoice-db-password trong Spring Environment.
3. Hoặc dùng VaultTemplate qua SecretProvider adapter.
4. Không in giá trị secret vào log.
5. Xác minh DataSource dùng đúng credential test.

### Phần D — Rotation

1. Tạo credential mới trên database test.
2. Tạo secret version mới ở PENDING.
3. Kiểm tra credential mới bằng test connection.
4. Promote version mới thành CURRENT.
5. Refresh/recreate DataSource theo thiết kế.
6. Xác minh tất cả replica kết nối thành công.
7. Thu hồi password cũ sau khi không còn consumer sử dụng.

### Phần E — Failure test

1. Tạm bỏ policy đọc secret và xác minh lỗi 403 được ghi nhận an toàn.
2. Dùng secret name sai và xác minh xử lý NotFound.
3. Giả lập timeout/throttling và kiểm tra retry budget.
4. Tắt Vault endpoint trong môi trường test và kiểm tra cache/fail-fast policy.
5. Xác minh không có secret value trong log/test report.

### Sản phẩm cần nộp

- Sơ đồ Vault, key, secret và secret version.
- Maven/Gradle dependency của Vault starter.
- Cấu hình property source và VaultTemplate.
- IAM policy read secret-bundles giới hạn theo secret.
- Unit test và integration test.
- Bằng chứng rotation CURRENT/PENDING.
- Bằng chứng DataSource reconnect với credential mới.
- Dashboard refresh failure/secret cache age.
- Runbook rotate, rollback và revoke credential.

## 18. Câu hỏi tự kiểm tra

1. Vault, encryption key, secret và secret bundle khác nhau thế nào?
2. Vì sao ứng dụng đọc secret bundle không cần quyền quản trị Vault?
3. Spring Cloud OCI Vault starter có hai cách tích hợp chính nào?
4. Property source đưa secret vào Spring Environment ra sao?
5. property-refresh-interval có tác dụng gì và mặc định bao lâu?
6. Vì sao refresh Environment không đồng nghĩa singleton bean đã inject tự đổi giá trị?
7. VaultTemplate.getSecret và decodeBundle thực hiện vai trò gì?
8. Vì sao không nên gọi Vault cho mọi HTTP request?
9. Secret version CURRENT, PENDING, PREVIOUS và LATEST khác nhau thế nào?
10. Vì sao LATEST có thể chưa phải CURRENT?
11. Khi nào nên tạo version PENDING?
12. Vì sao phải phối hợp rotation với target database/API?
13. Policy read secret-bundles khác quyền manage secrets thế nào?
14. Làm sao giới hạn quyền đọc một secret theo target.secret.id?
15. Khi Vault trả 403, cần kiểm tra những gì?
16. Khi Vault unavailable, khi nào fail fast và khi nào dùng cache?
17. Làm sao chứng minh DataSource đã dùng credential mới sau rotation?

## 19. Ghi nhớ

- OCI Vault lưu trữ và quản lý secret; secret được bảo vệ bằng encryption key theo cấu hình dịch vụ.
- Spring Cloud OCI Vault starter cung cấp property source và VaultTemplate.
- Property source phù hợp với cấu hình nạp vào Spring Environment; VaultTemplate phù hợp với truy xuất theo yêu cầu.
- Secret bundle chứa nội dung và metadata/version; dùng decodeBundle theo API của starter.
- property-refresh-interval mặc định 10 phút; refresh property source không tự bảo đảm mọi singleton bean/client được cập nhật.
- CURRENT là version đang dùng; LATEST có thể là PENDING và chưa được target system chấp nhận.
- Rotation phải phối hợp giữa Vault, target credential, cache, connection pool và các replica.
- Runtime identity thường chỉ cần read secret-bundles; tách khỏi quyền tạo, update, rotate hoặc delete secret.
- Giới hạn IAM policy theo compartment và target.secret.id khi có thể.
- Không log, commit hoặc đóng gói secret vào image; bảo vệ plaintext trong memory và diagnostic artifact.
- Khi Vault lỗi, dùng retry có giới hạn và cache theo policy; không fallback sang password mặc định.
- Kiểm thử rotation trên DataSource/client thực tế, không chỉ kiểm tra Spring Environment.

## Tài liệu tham khảo

- [Spring Cloud OCI Vault integration](https://oracle.github.io/spring-cloud-oracle/site/docs/oci/vault/)
- [Spring Cloud Oracle latest reference — OCI Vault](https://oracle.github.io/spring-cloud-oracle/latest/reference/html/index.html)
- [OCI Secret Management Service overview](https://docs.oracle.com/en-us/iaas/Content/secret-management/overview.htm)
- [OCI Secret Versions and rotation states](https://docs.oracle.com/en-us/iaas/Content/secret-management/Concepts/secret-versions.htm)
- [OCI Creating a Secret Version](https://docs.oracle.com/en-us/iaas/Content/secret-management/Tasks/create-secret-version.htm)
- [OCI Promoting a Pending Secret Version](https://docs.oracle.com/en-us/iaas/Content/secret-management/Tasks/promote-secret-version.htm)
- [OCI Getting Secret Bundle Contents](https://docs.oracle.com/en-us/iaas/Content/secret-management/Tasks/get-secrets-contents.htm)
- [OCI Vault IAM policy reference](https://docs.oracle.com/en-us/iaas/Content/Identity/Reference/keypolicyreference.htm)
- [OCI Secret Management and IAM policy example](https://docs.oracle.com/en-us/iaas/autonomous-database-serverless/doc/vault-secret-credentials-oci.html)
- [OCI Scheduling deletion of a secret](https://docs.oracle.com/en-us/iaas/Content/secret-management/Tasks/delete-secret.htm)
