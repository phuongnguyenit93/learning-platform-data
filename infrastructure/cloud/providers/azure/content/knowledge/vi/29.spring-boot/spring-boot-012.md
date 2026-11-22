# Quản lý secret Spring Boot bằng Azure Key Vault

Một ứng dụng Spring Boot triển khai trên Azure App Service cần kết nối cơ sở dữ liệu và gọi một hệ thống thanh toán. Nếu mật khẩu database hay API token bị viết trong application.yml, đưa vào Git, đóng gói JAR hoặc Docker image, bất kỳ ai có quyền đọc artifact hoặc lịch sử repository đều có thể truy cập bí mật đó. Việc thay đổi secret còn đòi hỏi sửa nhiều môi trường, restart không kiểm soát và khó biết ứng dụng nào đang dùng credential nào.

**Azure Key Vault** giúp lưu và quản lý secret tập trung với **Microsoft Entra ID**, phân quyền dữ liệu, phiên bản, nhật ký truy cập và những cơ chế bảo vệ ở cấp mạng. **Spring Cloud Azure** giúp Spring Boot đọc secret như một **PropertySource** trong Spring Environment, hoặc dùng **Azure SDK for Java** để truy xuất theo nhu cầu bằng **SecretClient**. Kết hợp với managed identity/workload identity, ứng dụng không cần giữ một client secret khác chỉ để truy cập vault.

Bài học thuộc chương **Spring Boot trên Azure**, nằm trong mô-đun **CLOUD_PROVIDERS_AZURE**: từ subscription, resource group, Entra ID, networking đến triển khai, quan sát, bảo mật và kiểm soát chi phí ứng dụng Azure. Bài tập trung vào **secret values**; Key Vault còn có **keys** và **certificates**, nhưng ba loại đối tượng này có APIs và quyền khác nhau.

**Phạm vi và giới hạn:** mã nguồn dưới đây minh họa Spring Boot 3.5.x cùng dòng Spring Cloud Azure tương thích theo tài liệu chính thức, Azure public cloud và một vault trong môi trường lab. Không ghi secret thật vào tài liệu, source control hoặc logs. Không tự tạo hay thay đổi tài nguyên Azure production khi chưa được phê duyệt. Phiên bản SDK, permission model và cấu hình có thể thay đổi; kiểm tra BOM và tài liệu theo phiên bản đang triển khai.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích secret là gì và tại sao application.yml, container images, Git history hay logs không phải nơi lưu secrets.
2. Phân biệt **Key Vault Secrets, Keys và Certificates**; hiểu secret name, value, version, enabled, expiration, tags.
3. Vẽ luồng Spring Boot → Entra ID/managed identity → Key Vault → bean/database.
4. Phân biệt Azure **management plane** với **Key Vault data plane**, RBAC và access policy.
5. Cấu hình Spring Cloud Azure **spring-cloud-azure-starter-keyvault-secrets** với BOM tương thích.
6. Dùng Key Vault **PropertySource** để cung cấp giá trị cho @Value, @ConfigurationProperties và Spring auto-configuration.
7. Dùng **SecretClient/SecretClientBuilder** để đọc secret khi cần và xử lý errors đúng.
8. Đăng nhập local bằng Azure CLI và triển khai bằng managed identity hoặc AKS workload identity.
9. Áp dụng least privilege, vai trò **Key Vault Secrets User**, phân tách vault theo môi trường và giới hạn các secret được nạp.
10. Hiểu quy tắc tên secret, ánh xạ dấu gạch nối, property precedence và trường hợp nhiều vault.
11. Thiết kế rotate secret có version, rollback, cutover và tránh gián đoạn kết nối.
12. Phân biệt PropertySource refresh với bean rebind, HikariCP datasource credentials và token cache.
13. Kết nối Key Vault qua Private Endpoint, DNS và TLS; xử lý 401/403, timeout và throttling.
14. Giữ bí mật không rò rỉ qua Spring Actuator, HTTP endpoints, logs, exception, traces hay CI/CD.
15. Lập kế hoạch kiểm thử, quan sát, ứng phó sự cố, khôi phục, retention và chi phí.

## 2. Bí mật ứng dụng là gì?

### 2.1. Những ví dụ thường gặp

- Mật khẩu JDBC cho Azure SQL Database hoặc PostgreSQL khi chưa dùng Entra/passwordless.
- API key gọi đối tác thanh toán.
- Client secret của một ứng dụng bên thứ ba.
- Signing secret/HMAC key cho webhook nếu nghiệp vụ dùng kiểu chia sẻ bí mật.
- SMTP password hoặc credential một dịch vụ legacy.
- Connection string chứa username/password hoặc account key.
- Token truy cập dài hạn của một SaaS bên ngoài.

Không phải mọi giá trị cấu hình đều là secret:

| Loại dữ liệu | Ví dụ | Nơi lưu gợi ý |
|---|---|---|
| Public/non-secret config | Tên môi trường, endpoint URL, thời hạn cache | application.yml, App Configuration |
| Secret | DB password, API token, signing secret | Key Vault Secrets |
| Khóa mật mã cần quản lý crypto operation | Encryption/signing key | Key Vault Keys khi khả năng hỗ trợ phù hợp |
| Chứng chỉ TLS/xác thực | X.509 certificate và private key liên quan | Key Vault Certificates hoặc giải pháp chứng chỉ phù hợp |
| Runtime access token ngắn hạn từ Entra ID | TokenCredential acquisition | Azure Identity/managed identity, không hard-code thành secret lâu dài |

**Không lưu mật khẩu database vào Key Vault khi Azure service hỗ trợ và kiến trúc cho phép dùng trực tiếp managed identity/Entra authentication.** Giảm số lượng secrets thường an toàn và đơn giản hơn chỉ di chuyển mật khẩu từ file sang vault.

### 2.2. Những vị trí làm rò rỉ secret

~~~mermaid
flowchart TD
    S["Application secret"] --> G["Git commit / history"]
    S --> I["Container image layers"]
    S --> L["Application / CI logs"]
    S --> E["Environment / process inspection"]
    S --> A["Actuator /env, /configprops"]
    S --> H["HTTP response / exception"]
    S --> D["Heap dump / diagnostic artifacts"]
    S --> B["Backup / exported config"]
~~~

Chỉ chuyển secret sang Key Vault **không tự loại bỏ** nguy cơ rò rỉ sau khi ứng dụng đọc secret vào RAM. Secrets có thể được copy ra logs, crash dumps hoặc gửi nhầm vào response. Vì vậy phải quản lý **toàn bộ vòng đời bí mật**.

## 3. Azure Key Vault giải quyết bài toán nào?

### 3.1. Tài nguyên và mô hình

~~~mermaid
flowchart LR
    APP["Spring Boot trên App Service / AKS / VM"] --> ID["Microsoft Entra ID"]
    ID -->|Access token| APP
    APP -->|TLS HTTPS + token| KV["Azure Key Vault"]
    KV --> SEC["Secret name + versions"]
    APP --> DB["Database / external API"]
    KV -. "Audit / metrics" .-> MON["Azure Monitor"]
    APP -. "App logs / traces" .-> MON
~~~

Luồng chi tiết:

1. Ứng dụng biết **vault endpoint** (URL, không phải secret) qua cấu hình triển khai.
2. Azure Identity lấy token của principal hiện hành.
3. Ứng dụng kết nối endpoint Key Vault qua HTTPS/TLS.
4. Key Vault kiểm tra identity, permission model, network policy và trạng thái secret.
5. Nếu hợp lệ, trả secret value của version được yêu cầu.
6. Spring gắn value vào PropertySource hoặc logic Java sử dụng SecretClient.
7. Logs/metrics ghi lại sự kiện vận hành theo phạm vi được phép, không ghi raw value.

Một vault name, URI và subscription ID **không phải bí mật**; không cần lưu chúng trong vault. Nhưng vẫn nên kiểm soát cấu hình để tránh trỏ nhầm vault production và tiết lộ topology không cần thiết.

### 3.2. Key Vault Secrets, Keys, Certificates

| Loại | Nội dung | API/thao tác |
|---|---|---|
| **Secrets** | Value bí mật dạng chuỗi/bytes được dịch vụ hỗ trợ | set/get/list versions/disable/delete |
| **Keys** | Khóa mật mã, có thể bảo vệ vật liệu khóa theo chính sách | encrypt/decrypt/sign/verify/wrap/unwrap |
| **Certificates** | Vòng đời và metadata chứng chỉ X.509 | import/create/manage certificates |

Đặt một private key PEM làm secret có thể hoạt động về mặt lưu chuỗi, nhưng **không tự có chính sách Key Vault Keys** về sử dụng khóa, HSM hoặc audit cryptographic operations. Chọn đúng object type theo mục tiêu.

### 3.3. Các khái niệm cơ bản

- **Vault:** tài nguyên Azure có endpoint dạng https://<vault-name>.vault.azure.net/ trong Azure public cloud.
- **Secret name:** tên logic như payment-api-token.
- **Secret version:** phiên bản riêng được tạo khi set value mới; có version ID.
- **Current/latest:** version mà một Get không chỉ định version sẽ đọc theo service semantics.
- **Enabled:** version có được phép dùng hay không.
- **Expires/Not before:** metadata giới hạn thời gian hợp lệ theo service/client checks.
- **Tags:** metadata cho owner, service, rotation policy; không đặt secret value trong tags.
- **Soft delete/purge protection:** bảo vệ dữ liệu khỏi xóa ngoài ý muốn theo retention và cấu hình.

**Expired không phải “tự xoay vòng”**. Nếu không có pipeline rotation và ứng dụng được cập nhật tương ứng, secret hết hạn có thể làm dịch vụ dừng.

### 3.4. Key Vault không thay thế authorization ứng dụng

Key Vault quyết định principal có được đọc secret nào hay không. Nó không tự biết HTTP user A có được truy cập tenant B. Nếu Spring Boot dùng một managed identity chung để đọc DB password và truy vấn dữ liệu của mọi tenant, ứng dụng vẫn cần **authorization ở API/database layer**.

## 4. Ba cách tích hợp secret trong Spring Boot

| Cách | Luồng | Phù hợp | Cần lưu ý |
|---|---|---|---|
| **Spring Cloud Azure PropertySource** | Key Vault → Spring Environment → @Value/auto-config | Datasource password và config cần từ startup | Nạp sớm, precedence, refresh và bean lifecycle |
| **Azure SDK SecretClient** | Java code gọi Key Vault lúc cần | Token truy xuất theo sự kiện, kiểm tra version/metadata | Caching/throttling/exception cần tự quản |
| **Platform reference/mount** | App Service Key Vault reference hoặc AKS CSI/secret mount → env/file → Spring | Khi platform quản lý secret injection | Refresh, identity, sync, file permissions khác nhau |

Cả ba không phải cách dùng đồng thời bắt buộc. Tránh một secret bị nạp qua nhiều con đường với precedence khác nhau rồi không biết bản nào đang có hiệu lực.

### 4.1. PropertySource: “secret trở thành cấu hình”

Spring Cloud Azure load secrets thành một nguồn property trong Spring Environment **sớm**, trước khi tạo nhiều beans. Vì vậy có thể cấu hình:

~~~text
Key Vault:  db-password = <secret-value>
      ↓
Spring Environment: db-password
      ↓
spring.datasource.password = placeholder db-password
      ↓
Spring DataSource/HikariCP khởi tạo
~~~

Phù hợp với secret cần dùng trong Spring auto-configuration như datasource credentials, nhưng phải hiểu: **nạp lại PropertySource không đồng nghĩa mọi bean đã xây dựng đều tự động đổi credential**.

### 4.2. SecretClient: “đọc secret theo thao tác”

~~~text
PaymentService
   ↓ gọi provider lấy token khi cần
SecretClient.getSecret("payment-api-token")
   ↓
Key Vault trả KeyVaultSecret
   ↓
Token được dùng trong memory, không in logs
~~~

Phù hợp khi cần biết version, expiry, metadata hoặc tự quản caching/refresh. Nhưng gọi getSecret **trong từng request web** có thể gây latency/429/chi phí và phụ thuộc trực tiếp vào khả năng sẵn sàng của vault.

### 4.3. Platform reference: “runtime nạp secret”

Ví dụ trên App Service, một App Setting có thể chứa một **Key Vault reference** để nền tảng resolve giá trị qua managed identity. Trên AKS, Secrets Store CSI Driver có thể mount secret vào filesystem hoặc đồng bộ Kubernetes Secret khi được cấu hình phù hợp.

Những cách này thay đổi điểm chịu trách nhiệm refresh và quyền:
- App Service reference có chu kỳ cache/refresh theo platform.
- CSI-mounted file có file permissions, sync/rotation và scheduling riêng.
- Kubernetes Secret là object cần RBAC/encryption/retention riêng.
- Environment variables của process thường **không tự cập nhật khi nền tảng thay value** nếu runtime không khởi động lại/bind lại.

Không coi refresh của Key Vault PropertySource, App Service references và CSI driver là một cơ chế giống nhau.

## 5. Thiết kế quyền: Microsoft Entra ID và Key Vault

### 5.1. Hai mặt phẳng quyền

- **Management plane (Azure Resource Manager):** tạo/sửa vault, network, settings, IAM.
- **Data plane (Key Vault):** get/list/set/delete secrets, keys, certificates.

Một principal có role **Contributor** trên resource group không mặc định được đọc secret value của vault dùng permission model Azure RBAC. Ngược lại, principal có quyền đọc secrets không nhất thiết được thay firewall, tạo vault hoặc gán RBAC.

### 5.2. Vai trò RBAC thông dụng

| Vai trò | Quyền điển hình | Dùng cho |
|---|---|---|
| **Key Vault Reader** | Đọc metadata, **không đọc secret value** | Giám sát/khám phá metadata |
| **Key Vault Secrets User** | Đọc giá trị secrets | Runtime Spring Boot chỉ cần get/list |
| **Key Vault Secrets Officer** | Quản lý secrets nhưng không gán roles | Quy trình phát hành/rotation có kiểm soát |
| **Key Vault Administrator** | Quản lý data-plane objects rộng | Quản trị đặc biệt, không gán cho app |
| **Key Vault Data Access Administrator** | Gán/quản lý một tập Key Vault data roles theo điều kiện | Identity/governance team |

Nếu app chỉ cần đọc token, **Key Vault Secrets User** thường phù hợp hơn Secrets Officer/Administrator. Role ở mức vault có thể cho app đọc nhiều secrets hơn nhu cầu; có thể cân nhắc vault tách theo ứng dụng hoặc scoping/ABAC khi đáp ứng feature support và chính sách.

### 5.3. Azure RBAC và legacy access policies

Key Vault có thể dùng:
- **Azure role-based access control (RBAC)**; hoặc
- **Vault access policy** theo mô hình cũ/cấu hình hiện tại.

Hai phương án **không giống nhau**. Không thêm Key Vault Secrets User RBAC role rồi kỳ vọng nó thay thế access policy khi vault đang ở chế độ access policy. Ngược lại, nếu đang dùng RBAC, thêm một access policy không tự giải quyết 403.

Kiểm tra permission model trước rồi mới cấp quyền; chuyển mô hình permission trong production là thay đổi nhạy cảm, cần approval và plan tránh khóa nhầm chính quản trị viên.

### 5.4. Phân tách principals

Một thiết kế tối thiểu:

~~~mermaid
flowchart LR
    DEV["Developer identity"] -->|Lab access có giới hạn| KVD["kv-orders-dev"]
    RUNTIME["Orders runtime managed identity"] -->|Secrets User read| KVP["kv-orders-prod"]
    CICD["Release/rotation identity"] -->|Secrets Officer theo approval| KVP
    ADMIN["Security platform admin"] -->|Quản lý IAM/network| KVP
~~~

Ứng dụng production không dùng cùng credential developer. CI/CD tạo/rotate secret không cần mặc định chạy bằng identity của ứng dụng runtime. Tách principals và vault giúp giảm blast radius khi token bị lộ.



## 6. Chuẩn bị môi trường lab an toàn

### 6.1. Điều kiện trước khi bắt đầu

- Một Azure subscription được phép dùng lab, có quyền đọc thông tin resource group/vault và xin cấp role khi cần.
- Một Key Vault **đã được cấp phép sử dụng**; không tạo vault mới trong production chỉ vì không tìm thấy.
- Microsoft Entra identity của developer hoặc workload đã được định danh rõ.
- JDK và Spring Boot phù hợp với Spring Cloud Azure BOM.
- Maven hoặc Gradle.
- Azure CLI cho việc xác minh môi trường.
- Kết nối mạng có thể tới vault và Microsoft Entra token endpoints.
- Một endpoint vault ví dụ **https://kv-orders-dev.vault.azure.net/**; thay bằng tên vault lab thật.

Để tránh chi phí và thay đổi ngoài ý muốn, phần lớn lệnh bên dưới chỉ đọc metadata. Lệnh tạo role/secret chỉ chạy ở **lab được cấp quyền**.

### 6.2. Kiểm tra subscription và vault

Trên Bash/Azure Cloud Shell:

~~~bash
az login
az account show --query "{subscription:id, tenant:tenantId, name:name}" -o json

# Thay bằng vault đã được nhóm nền tảng cấp.
VAULT_NAME="kv-orders-dev"

az keyvault show --name "$VAULT_NAME" \
  --query "{id:id,uri:properties.vaultUri,rbac:properties.enableRbacAuthorization}" \
  -o json
~~~

**Không in access token, credential JSON hoặc secret values vào log build.** Với môi trường automation không dùng đăng nhập tương tác; dùng workload federation/managed identity và đúng permission model.

### 6.3. Kiểm tra secret metadata, không đọc value

~~~bash
az keyvault secret list \
  --vault-name "$VAULT_NAME" \
  --query "[].{name:name,enabled:attributes.enabled}" \
  -o table

# In URI/version ID của secret cụ thể, không in .value.
az keyvault secret show \
  --vault-name "$VAULT_NAME" \
  --name "payment-api-token" \
  --query "id" \
  -o tsv
~~~

Nếu lệnh list hoặc show thất bại 403, chưa chắc vault hỏng: kiểm tra permission model và data-plane permissions của identity đang đăng nhập. Nếu không tồn tại secret, lệnh show có thể trả 404. Tên secret là metadata có thể nhạy cảm trong một số tổ chức, nên cũng hạn chế logging.

### 6.4. Cấp role đọc secret cho runtime identity

Với vault dùng **Azure RBAC**, platform team có quyền quản trị có thể cấp vai trò đọc secret:

~~~bash
VAULT_ID="/subscriptions/<sub-id>/resourceGroups/<rg>/providers/Microsoft.KeyVault/vaults/<vault-name>"
APP_PRINCIPAL_OBJECT_ID="<managed-identity-principal-object-id>"

az role assignment create \
  --assignee-object-id "$APP_PRINCIPAL_OBJECT_ID" \
  --assignee-principal-type ServicePrincipal \
  --role "Key Vault Secrets User" \
  --scope "$VAULT_ID"
~~~

Lệnh này **thay đổi IAM**; không chạy nếu chưa có approval. **Principal object ID** là định danh RBAC của managed identity, **không phải** client ID của ứng dụng. Nếu role chỉ ở mức vault, mọi secret trong vault có thể nằm trong scope đọc của principal theo quyền thực tế; cân nhắc tách vault/secret scoping phù hợp.

Lệnh chỉ có tác dụng đúng với vault đang dùng RBAC. Với access-policy permission model phải thực hiện theo quản trị policy phù hợp; không trộn lẫn hai cơ chế.

### 6.5. Tạo một giá trị giả trong lab

Nếu chưa có secret test và được phép tạo:

~~~bash
# Chỉ dùng chuỗi giả, không phải mật khẩu/token thật.
az keyvault secret set \
  --vault-name "$VAULT_NAME" \
  --name "payment-api-token" \
  --value "lab-demo-value-not-a-real-secret" \
  --output none
~~~

**Cảnh báo:** tham số dòng lệnh có thể lộ qua shell history, process inspection hoặc CI logs. Cách này chỉ để minh họa với chuỗi công khai. Secret production phải được chuyển qua **quy trình vault/secret provisioning được phê duyệt**, công cụ bảo mật, hoặc pipeline tránh in/ghi lộ value. Không lưu secret thật trong tệp không mã hóa, source control hay terminal history.

### 6.6. Bằng chứng lab cần thu thập

- Đúng subscription/tenant và vault URI.
- Vault permission model đã được xác nhận.
- Identity của app và data-plane role/scope đúng.
- Endpoint reachable từ developer/runtime.
- Secret name/version tồn tại; không chụp màn hình giá trị.
- App đọc được một secret giả qua PropertySource hoặc SDK.
- Logs/traces không chứa secret value.
- Có bước cleanup đối với tài nguyên/role cấp tạm trong lab.

## 7. Khai báo dependencies Maven hoặc Gradle

### 7.1. Spring Cloud Azure BOM

Các dòng Spring Boot và Spring Cloud Azure cần tương thích. Theo tài liệu Microsoft Learn được kiểm tra khi viết bài:

| Spring Boot | Spring Cloud Azure BOM gợi ý từ tài liệu | Lưu ý |
|---|---|---|
| 4.0.x | 7.4.0 | Kiểm tra Java/Spring compatibility |
| 3.5.x | 6.5.0 | Dòng minh họa chính của bài |
| 3.1.x–3.5.x | 5.25.0 | Dòng 5.x được tài liệu liệt kê |
| 2.x | 4.20.0 | Legacy; xem vòng đời support |

Các con số thể hiện tài liệu tại thời điểm tác giả kiểm tra, **không phải bảo đảm latest vĩnh viễn**. Nếu dự án dùng Boot 3.3 hay 3.4, đừng máy móc lấy BOM 6.5.0 chỉ vì ví dụ đang dùng Boot 3.5. Nên dùng BOM của Spring Cloud Azure và khóa phiên bản trong dependency management, tránh pin ngẫu nhiên từng module.

### 7.2. Maven với Spring Boot 3.5

Ví dụ **phần cần thêm vào pom.xml**, giả định dự án đã có Spring Boot parent hoặc dependency management phù hợp:

~~~xml
<properties>
    <spring-cloud-azure.version>6.5.0</spring-cloud-azure.version>
</properties>

<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.azure.spring</groupId>
            <artifactId>spring-cloud-azure-dependencies</artifactId>
            <version>${spring-cloud-azure.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>com.azure.spring</groupId>
        <artifactId>spring-cloud-azure-starter-keyvault-secrets</artifactId>
    </dependency>
</dependencies>
~~~

**Artifact chính xác:** com.azure.spring:spring-cloud-azure-starter-keyvault-secrets. Ngoài ra có starter rộng hơn **spring-cloud-azure-starter-keyvault** nếu dùng thêm Key Vault keys/certificates và đã xác minh cần những tính năng đó.

Không nhầm với các starters đời cũ như azure-spring-boot-starter-keyvault-secrets hoặc cấu hình azure.keyvault.* không còn phù hợp với phiên bản hiện đại.

### 7.3. Gradle với BOM

Ví dụ Gradle Groovy DSL khi plugin/dependency management của Spring Boot đã được cấu hình:

~~~groovy
dependencies {
    implementation platform(
        "com.azure.spring:spring-cloud-azure-dependencies:6.5.0"
    )
    implementation "com.azure.spring:spring-cloud-azure-starter-keyvault-secrets"
}
~~~

Khi dùng Gradle Kotlin DSL thì cú pháp tương ứng khác. Cần dùng cùng BOM cho toàn bộ Spring Cloud Azure dependencies. Không vô tình import hai BOM phiên bản không tương thích hoặc ép azure-core/azure-identity xuống bản cũ khiến NoSuchMethodError khi khởi động.

### 7.4. Khi chỉ muốn dùng Azure SDK thuần

Không cần PropertySource thì có thể chỉ dùng:

~~~xml
<dependency>
    <groupId>com.azure</groupId>
    <artifactId>azure-security-keyvault-secrets</artifactId>
</dependency>
<dependency>
    <groupId>com.azure</groupId>
    <artifactId>azure-identity</artifactId>
</dependency>
~~~

Ở trường hợp này phải quản lý versions bằng Azure SDK BOM hoặc cơ chế dependency management được hỗ trợ. **Spring Cloud Azure BOM không phải Azure SDK BOM cho mọi thư viện Java tùy ý**; tránh nhập hai BOM không kiểm soát. Ứng dụng không nhất thiết cần cả starter và client SDK trực tiếp nếu starter đã cung cấp bean SecretClient đúng nhu cầu.

## 8. Phương án A: Key Vault như Spring PropertySource

### 8.1. Cấu hình application.yml

Giả định vault có hai secret với tên **payment-api-token** và **db-password**. Endpoint được truyền qua biến môi trường không chứa secret:

~~~yaml
spring:
  application:
    name: orders-api
  cloud:
    azure:
      keyvault:
        secret:
          property-sources:
            - name: orders-secrets
              endpoint: ${AZURE_KEYVAULT_ENDPOINT}
              secret-keys:
                - payment-api-token
                - db-password
              refresh-interval: 30m

app:
  payment:
    token: ${payment-api-token}
~~~

Trong môi trường triển khai:

~~~text
AZURE_KEYVAULT_ENDPOINT=https://kv-orders-dev.vault.azure.net/
~~~

**Giải thích:**

- **property-sources** cho phép cấu hình một hoặc nhiều Key Vault PropertySources.
- **endpoint** là vault URI, không phải secret.
- **secret-keys** giới hạn các secret names cần nạp; nếu bỏ, PropertySource có thể cố tải toàn bộ secrets theo chính sách thư viện.
- **refresh-interval: 30m** là chu kỳ refresh dữ liệu của PropertySource trong các dòng Spring Cloud Azure được Microsoft Learn mô tả.
- **app.payment.token** dùng placeholder để đổi từ tên secret sang tên property của ứng dụng.

Không ghi giá trị bí mật thật trong YAML. Nếu chưa có Key Vault/permission/network, quá trình khởi động có thể fail hoặc property không được giải quyết theo cấu hình cụ thể; cần kiểm thử startup failure.

### 8.2. Đọc property bằng @Value

~~~java
package com.example.orders;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

@Service
public class PaymentTokenHolder {
    private final String token;

    public PaymentTokenHolder(
            @Value("${app.payment.token}") String token) {
        if (token == null || token.isBlank()) {
            throw new IllegalStateException(
                "Payment token chưa được cấu hình");
        }
        this.token = token;
    }

    // Token chỉ được dùng bên trong client gọi đối tác.
    // Không có getter/public endpoint để trả token ra ngoài.
    public boolean isConfigured() {
        return !token.isBlank();
    }
}
~~~

Ví dụ cố tình **không in token**, không trả value qua REST controller và không dùng Lombok @Data/@ToString trên class chứa secret. Một @Value được gắn vào singleton bean thường được resolve khi bean tạo. Nếu PropertySource refresh sau đó, **không giả định field token ở bean đã tạo tự đổi ngay**.

### 8.3. Dùng cho datasource password

Nếu database còn yêu cầu mật khẩu, có thể tạo secret Key Vault tên **spring-datasource-password**. Spring Cloud Azure hỗ trợ chuyển đổi một số dấu gạch nối thành dấu chấm để lookup property:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://<db-host>:5432/orders
    username: orders_user
    # spring.datasource.password có thể được lấy từ
    # Key Vault secret: spring-datasource-password
~~~

Tài liệu Spring Cloud Azure hỗ trợ ánh xạ tên secret **spring-datasource-password** thành property **spring.datasource.password**. Nếu muốn rõ ràng, có thể dùng placeholder:

~~~yaml
spring:
  datasource:
    password: ${db-password}
~~~

Khi cần URL/username/password cùng cấu hình, tránh lẫn tên secret và property: **db-password** dùng trong placeholder không phải tự tương đương **spring.datasource.password** trừ khi đã ánh xạ. Những tên như spring.datasource-url có semantics khác spring.datasource.url; nên dùng explicit placeholder khi tên có ký tự phức tạp.

**Cảnh báo rotation:** HikariCP/DataSource có thể giữ connection pool hoặc credential đã resolve khi khởi tạo. Đổi Key Vault version hay refresh PropertySource không đảm bảo các kết nối mới dùng password mới ngay. Thiết kế restart/bean reconfiguration/overlap migration theo mục 15.

### 8.4. So sánh @Value và @ConfigurationProperties

| Cách | Ưu điểm | Cẩn trọng |
|---|---|---|
| @Value | Ngắn, dùng placeholder trực tiếp | Nhiều fields rời rạc, bean không tự rebind |
| @ConfigurationProperties | Gom config type-safe, có validation | Không đưa secret vào toString/serialization |
| Spring auto-config | Ví dụ DataSource dùng property đã nạp | Bean được tạo sớm; đổi secret không tự cập nhật |
| SecretClient | Có thể đọc version/latest khi cần | Caching và Key Vault dependency |

**Đừng khai báo một REST controller trả toàn bộ Spring Environment** để kiểm tra secret. Kiểm tra bằng chức năng nghiệp vụ hoặc một health indicator chỉ báo boolean/status an toàn.

### 8.5. Chỉ nạp những secret cần dùng

Nếu vault có hàng nghìn secrets, không nhất thiết nạp tất cả:

~~~yaml
spring:
  cloud:
    azure:
      keyvault:
        secret:
          property-sources:
            - endpoint: ${AZURE_KEYVAULT_ENDPOINT}
              secret-keys:
                - payment-api-token
                - db-password
~~~

Tên trong **secret-keys phải khớp tên secret gốc chính xác** theo quy tắc cấu hình; việc property resolver không phân biệt hoa thường không có nghĩa có thể viết tùy ý tên secret được liệt kê.

Giới hạn danh sách giúp giảm lượng dữ liệu nạp và dễ phân tích ownership, nhưng **không thay đổi quyền data-plane của identity**: nếu principal có quyền đọc cả vault, ứng dụng vẫn có thể đọc secrets khác qua SecretClient. Phân quyền thật phải được thực thi ở Key Vault.

## 9. Phương án B: đọc theo nhu cầu bằng SecretClient

### 9.1. Vì sao dùng SDK trực tiếp?

Khi ứng dụng cần:
- Đọc metadata expiry, tags hoặc version.
- Lấy một secret cụ thể khi gọi một integration.
- Chọn version cũ khi chuyển đổi credential.
- Tự quản cache hoặc circuit breaker.
- Lưu audit về lần refresh/version (không ghi secret value).
- Không đưa secret vào Spring Environment hoặc bean properties.

Có thể dùng **SecretClient** trực tiếp.

### 9.2. Khai báo bean SecretClient

~~~java
package com.example.orders;

import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.security.keyvault.secrets.SecretClient;
import com.azure.security.keyvault.secrets.SecretClientBuilder;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class KeyVaultClientConfiguration {

    @Bean
    public SecretClient secretClient(
            @Value("${AZURE_KEYVAULT_ENDPOINT}") String endpoint) {
        return new SecretClientBuilder()
            .vaultUrl(endpoint)
            .credential(
                new DefaultAzureCredentialBuilder().build()
            )
            .buildClient();
    }
}
~~~

Trong Spring Cloud Azure starter hiện đại, có thể đã có **SecretClient auto-configured bean**. Khi đó ưu tiên inject bean sẵn; không đăng ký trùng bean cùng kiểu nếu chưa hiểu autoconfiguration/bean conditions. Ví dụ tự khai báo có ý nghĩa khi dùng azure-security-keyvault-secrets + azure-identity thuần, hoặc khi chủ động custom configuration.

### 9.3. Đọc value mà không in ra log

~~~java
package com.example.orders;

import com.azure.security.keyvault.secrets.SecretClient;
import com.azure.security.keyvault.secrets.models.KeyVaultSecret;
import org.springframework.stereotype.Service;

@Service
public class PaymentCredentialProvider {
    private final SecretClient client;

    public PaymentCredentialProvider(SecretClient client) {
        this.client = client;
    }

    // Chỉ gọi khi thực sự cần refresh trong một workflow.
    public String loadCurrentToken() {
        KeyVaultSecret secret = client.getSecret("payment-api-token");
        String value = secret.getValue();

        if (value == null || value.isBlank()) {
            throw new IllegalStateException(
                "Payment API token không hợp lệ");
        }
        return value;
    }
}
~~~

Đây là ví dụ đơn giản để minh họa API. **Không gọi loadCurrentToken cho mỗi HTTP request** nếu traffic cao; cần TTL cache, version policy và refresh scheduler được thiết kế tốt. Không đặt token vào HTTP response, log, @ToString hoặc metrics tags.

### 9.4. Phiên bản bí mật

~~~java
KeyVaultSecret latest = client.getSecret("payment-api-token");

// Khi biết một version ID được quản lý theo deployment:
// KeyVaultSecret pinned = client.getSecret(
//     "payment-api-token", "<version-id>");
// ...
~~~

Version-pinned reads giúp rollback/controlled cutover nhưng không tự rotate. Latest reads lấy version theo Key Vault semantics; app-level cache và runtime lifecycle có thể khiến dữ liệu thực được dùng vẫn là bản cũ.

Mặc dù bạn có thể kiểm tra **KeyVaultSecret.getProperties().getExpiresOn()**, hãy nhớ secret expiry chỉ là metadata/quy tắc hợp lệ của vault. Nó không tự đảm bảo downstream credential bị thu hồi đúng lúc, nên cần quản lý ngoài Key Vault với đối tác phát hành token.

### 9.5. Errors khi gọi SecretClient

| Tình huống | Khả năng | Ứng xử |
|---|---|---|
| Secret không tồn tại | 404/ResourceNotFoundException | Kiểm tra name/version/env, fail appropriately |
| Identity thiếu quyền | 403 | Không retry vô hạn; IAM check |
| Token/auth sai | 401 | Azure Identity/tenant/scope |
| Không kết nối được | DNS/TLS/timeout | Network diagnostics và bounded retry |
| Rate limited | 429 | Tôn trọng Retry-After, cache/limit calls |
| Secret disabled/expired | Trạng thái version không dùng được | Rotate/re-enable theo approval |
| Vault bị xóa/đổi | Endpoint sai hoặc tài nguyên không sẵn | Restore/rollback/IaC |

Không dùng câu lệnh catch(Exception) rồi trả một chuỗi placeholder như "NO_TOKEN" để tiếp tục gọi production API: điều đó có thể gây side effects sai và che mất sự cố. Với secret tối quan trọng, thường cần fail closed hoặc fallback có quy trình phê duyệt.



## 10. Local development: xác thực mà không lưu credential

### 10.1. Dùng Azure CLI credential chain

Trong môi trường developer đã được cấp quyền:

~~~bash
az login
az account set --subscription "<subscription-id>"
az account show \
  --query "{name:name,tenant:tenantId,subscription:id}" \
  -o json
~~~

**DefaultAzureCredential** của Azure Identity thử những nguồn credential theo trình tự/version được thư viện định nghĩa: biến môi trường, workload identity, managed identity và developer tools (ví dụ Azure CLI) theo môi trường. Với local development có Azure CLI, SDK có thể dùng credential người đang đăng nhập.

Điều này không đồng nghĩa app nên gắn quyền admin cho developer. Identity local nên chỉ đọc secrets lab, và phải rõ tenant/subscription hiện dùng. Azure CLI đăng nhập không đảm bảo Data-Plane RBAC đã được cấp.

### 10.2. Set endpoint không phải secret

Bash shell:

~~~bash
export AZURE_KEYVAULT_ENDPOINT="https://<vault-name>.vault.azure.net/"
~~~

PowerShell:

~~~powershell
$env:AZURE_KEYVAULT_ENDPOINT = "https://<vault-name>.vault.azure.net/"
~~~

Đây là URL tài nguyên, không phải token. Với dự án Spring, có thể lưu trong launch profile hoặc environment config không có secret. Không commit file chứa AZURE_CLIENT_SECRET hoặc password thật.

### 10.3. Kiểm tra app đọc được secret mà không lộ value

**Smoke test an toàn** có thể cho Spring service khởi tạo một bean và kiểm tra điều kiện boolean:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class SecretSmokeCheck {
    @Bean
    ApplicationRunner check(
            @Value("${payment-api-token}") String token) {
        return args -> {
            if (token == null || token.isBlank()) {
                throw new IllegalStateException(
                    "Chưa đọc được secret payment-api-token");
            }
            // Chỉ log trạng thái, không log độ dài/hash/value secret.
            System.out.println("Key Vault secret: configured");
        };
    }
}
~~~

Đây là mã lab minh họa; production có thể dùng test/health internal thay vì in ra console. Không phát HTTP endpoint cho người dùng công khai để kiểm tra secret trực tiếp.

### 10.4. Bẫy identity khác nhau

- Developer có thể dùng tài khoản Azure CLI khác người đăng nhập IDE.
- DefaultAzureCredential có thể chọn credential không mong muốn nếu developer machine còn biến môi trường service principal.
- Một principal có quyền trên vault dev không có quyền vault prod.
- Azure CLI chọn subscription chỉ ảnh hưởng command context, không luôn xác định tenant/token audience của mọi SDK call.
- Key Vault permission role assignments có thể mất thời gian propagation.
- Proxy/TLS/network local khác Azure App Service production.

Hãy ghi nhận **principal object ID**, tenant, vault URI và quyền truy cập, không log access token.

## 11. Triển khai production với managed identity

### 11.1. Vì sao managed identity?

Managed identity cung cấp danh tính Entra ID được Azure quản lý, giúp ứng dụng lấy token mà không lưu client secret. Có thể là:

- **System-assigned managed identity:** gắn với vòng đời tài nguyên Azure.
- **User-assigned managed identity:** tài nguyên identity riêng, có thể gán cho nhiều workload theo chính sách.

Secret value vẫn phải được ứng dụng đọc vào RAM; managed identity giải quyết **xác thực tới Key Vault**, không thay thế runtime secret hygiene.

### 11.2. App Service + system-assigned identity

Luồng:

~~~mermaid
sequenceDiagram
    participant A as Spring Boot App Service
    participant M as Managed Identity endpoint
    participant V as Azure Key Vault
    participant D as Downstream service
    A->>M: Request token for Key Vault
    M-->>A: Entra access token
    A->>V: GET secret with token
    V-->>A: Secret value/version
    A->>D: Use credential securely
~~~

Nhóm vận hành có thể bật identity trên App Service và gán role Key Vault Secrets User ở vault scope khi được phê duyệt. Một lệnh **chỉ đọc** để kiểm tra identity:

~~~bash
az webapp identity show \
  --resource-group "<app-rg>" \
  --name "<app-service-name>" \
  --query "{principalId:principalId,type:type}" \
  -o json
~~~

Bật identity bằng lệnh quản lý Azure là thao tác thay đổi production, phải có IaC/approval riêng. **Object ID/principalId** từ identity dùng cho RBAC assignment; **clientId** là thuộc tính khác, dùng khi chọn user-assigned identity.

### 11.3. User-assigned managed identity

Khi app có nhiều identity hoặc tổ chức yêu cầu identity riêng cho workload, cần chỉ rõ identity dùng để đọc vault. Với **PropertySource**, cấu hình production trong một profile được triển khai riêng:

~~~yaml
spring:
  cloud:
    azure:
      keyvault:
        secret:
          property-sources:
            - endpoint: ${AZURE_KEYVAULT_ENDPOINT}
              credential:
                managed-identity-enabled: true
                client-id: ${AZURE_CLIENT_ID}
~~~

**Cảnh báo:** cấu hình này dành cho môi trường có managed identity endpoint. Nếu dùng ngay trong local developer profile không có managed identity, có thể làm local login fail. Tách application-local/application-prod, hoặc chỉ cấu hình credential selection ở môi trường cần thiết. Với system-assigned MI, không cần giả định phải truyền client ID.

### 11.4. AKS và workload identity federation

AKS có thể dùng **Microsoft Entra Workload ID**, dựa trên Kubernetes ServiceAccount và federated identity credential; Pod lấy token không cần client secret dài hạn.

~~~mermaid
flowchart LR
    P["Spring Boot Pod"] --> SA["Kubernetes ServiceAccount / projected token"]
    SA --> E["Microsoft Entra token exchange"]
    E --> K["Key Vault data plane"]
    K --> P
~~~

Các bước logic:

1. AKS cluster hỗ trợ/đã bật OIDC issuer và workload identity theo cấu hình.
2. Tạo user-assigned managed identity cho workload.
3. Cấu hình federated credential tin service account subject/audience đúng.
4. Annotate ServiceAccount và gắn vào Pod; bật labels/env/token projection theo AKS guidance.
5. Gán Key Vault Secrets User cho identity tại scope thích hợp.
6. Azure Identity SDK dùng workload identity credentials/DefaultAzureCredential trong Pod.
7. Kiểm thử Pod thật, không chỉ kubeconfig của developer.

**Không ép managed-identity-enabled=true một cách tùy tiện cho Pod dùng workload identity federation**, vì credential path có thể khác IMDS/managed identity endpoint. Cần đảm bảo Spring Cloud Azure/azure-identity phiên bản tương thích, tenant/client/token-file env và cách SDK chọn identity.

### 11.5. Azure Functions, Container Apps và VMs

Tùy môi trường:
- Azure Functions có managed identity và network integration theo hosting plan.
- Azure Container Apps có managed identity và secret references/platform config riêng.
- Azure VM hỗ trợ managed identity qua Azure Instance Metadata Service.
- AKS ưu tiên workload identity hoặc cơ chế được tổ chức chuẩn hóa.

Không giả định mọi môi trường expose identity endpoint và refresh semantics giống nhau. Luôn kiểm thử token acquisition và Key Vault data-plane access từ **runtime thật**.

## 12. Quy tắc tên secret và ánh xạ Spring properties

### 12.1. Key Vault secret names

Theo Key Vault Secrets naming rules, tên chỉ dùng **chữ cái Latin, chữ số và dấu gạch nối (-)**. Không dùng dấu chấm, dấu gạch dưới, khoảng trắng hoặc dấu slash.

| Key Vault secret | Spring property muốn dùng | Giải pháp |
|---|---|---|
| payment-api-token | app.payment.token | Placeholder |
| spring-datasource-password | spring.datasource.password | Mapping hyphen/dot của Spring Cloud Azure |
| db-password | spring.datasource.password | Explicit placeholder |
| orders--api--token | Tên custom phức tạp | Tránh tên khó hiểu, dùng mapping có test |
| billing-v2-token | app.billing.token | Placeholder/typed config |

Không dựa vào phép biến đổi tên “gần giống” để chọn secret production; mapping phải được test, nhất là tên vừa có dấu gạch nối vừa có dấu chấm ở ứng dụng.

### 12.2. Placeholder là cách rõ ràng nhất khi tên không tương đương

Ví dụ:

~~~yaml
app:
  partner:
    token: ${payment-api-token}

spring:
  datasource:
    password: ${db-password}
~~~

Dùng tên secret rõ, rồi property Spring mang semantics nghiệp vụ. Khi thay tên vật lý trong Key Vault, chỉ cần điều chỉnh mapping theo release plan và policy.

### 12.3. Phân biệt hoa thường và secret-keys

Spring Cloud Azure PropertySource có cấu hình **case-sensitive** (mặc định thường false theo tài liệu). Còn danh sách **secret-keys** yêu cầu tên Key Vault thực **khớp chính xác**.

Ví dụ:

~~~yaml
spring:
  cloud:
    azure:
      keyvault:
        secret:
          property-sources:
            - endpoint: ${AZURE_KEYVAULT_ENDPOINT}
              case-sensitive: false
              secret-keys:
                - payment-api-token
                - db-password
~~~

Đừng đánh giá “nếu @Value lấy được Payment-API-Token thì secret-keys viết hoa tùy ý cũng được”. Hãy thống nhất names theo kebab-case và kiểm thử trên vault có các phiên bản thực tế.

### 12.4. Spring PropertySource precedence

Khi cùng key tồn tại ở nhiều sources, Spring chọn giá trị theo thứ tự ưu tiên của PropertySources. Trong cấu hình Spring Cloud Azure Key Vault Secrets được Microsoft Learn mô tả:

- Nếu tồn tại **SystemEnvironmentPropertySource**, environment variables có thể có **độ ưu tiên cao hơn KeyVaultPropertySource**.
- Giữa nhiều Key Vault PropertySources, thứ tự khai báo quyết định ưu tiên; source liệt kê trước có thể được ưu tiên hơn source sau.
- Thứ tự Spring property sources còn có các nguồn khác như command-line/system props, tùy bootstrap và Spring Boot version.

Điều này có nghĩa một environment variable vô tình chứa **giá trị cũ** có thể override secret mới trong Key Vault. Không kết luận rotation bị lỗi khi nguyên nhân là property shadowing.

### 12.5. Kiểm tra nguồn mà không log secret value

Các bước an toàn:
1. Xác định tên logical property.
2. Liệt kê những potential sources (env, file, vaults, CLI) theo config.
3. Kiểm tra config precedence qua tài liệu/diagnostic metadata.
4. Kiểm tra application health/behavior bằng credential test.
5. Không dump Spring Environment hoặc in secret để “xem thực tế”.
6. Nếu cần so version, log **secret version ID** đã phân loại dữ liệu thay vì value.
7. Không so/ghi raw hash secret vào logs nếu security policy không cho phép.

## 13. Nhiều Key Vault và phân tách môi trường

### 13.1. Hai vaults trong một ứng dụng

~~~yaml
spring:
  cloud:
    azure:
      keyvault:
        secret:
          property-sources:
            - name: app-owned
              endpoint: ${ORDERS_KEYVAULT_ENDPOINT}
              secret-keys:
                - payment-api-token
                - db-password
            - name: shared-owned
              endpoint: ${SHARED_KEYVAULT_ENDPOINT}
              secret-keys:
                - trusted-partner-token
~~~

Mỗi vault có policy, region, network và IAM riêng; identity app phải có quyền đọc ở những vaults được phép. Nếu hai vault có secret trùng tên, precedence giữa sources ảnh hưởng giá trị cuối.

### 13.2. Vì sao cần tách dev/test/prod?

| Môi trường | Nguyên tắc |
|---|---|
| Dev | Giá trị giả, identity developer, không có quyền production |
| Test/Staging | Secret riêng, kiểm thử gần production, role hạn chế |
| Prod | Identity runtime riêng, access approvals, audit, rotation |
| Disaster recovery | Secret/versions và access/network theo recovery plan |

Không dùng một vault production làm nguồn secret cho local laptop để tiết kiệm tạo vault dev. Điều đó mở rộng attack surface và khiến developer dùng nhầm credential thật.

### 13.3. Vault theo ứng dụng hay vault dùng chung?

- **Vault theo ứng dụng:** giảm blast radius, ownership rõ, RBAC đơn giản hơn; nhiều vaults/network/monitoring hơn.
- **Vault dùng chung:** tập trung quản lý, có thể giảm số vaults; permission scoping/rotation phức tạp và tăng blast radius.
- **Vault theo môi trường:** tối thiểu giúp dev không đọc prod.
- **Vault theo tenant:** cần cân nhắc hàng nghìn vaults, quotas, vận hành và data residency.

Không có một mô hình tốt cho mọi tổ chức. Chọn theo team ownership, số principals, data classification, chi phí và disaster recovery.

### 13.4. Đừng dùng prefix như security boundary duy nhất

Đặt tên secrets dạng orders-db-password và billing-db-password trong cùng vault không tự ngăn Orders identity đọc Billing secrets khi cả hai được gán quyền vault-wide.

Nếu thực sự cần isolation:
- Tách vaults hoặc scope roles/ABAC theo khả năng và policy.
- Không cấp Secrets Officer cho runtime.
- Dùng audit logs và owner reviews.
- Kiểm thử truy cập trái quyền (negative tests).

## 14. Refresh không đồng nghĩa bean reconfiguration

### 14.1. PropertySource có chu kỳ refresh

Theo tài liệu Spring Cloud Azure Secret Management được kiểm tra, **KeyVaultPropertySource** có refresh interval mặc định khoảng **30 phút**; cấu hình:

~~~yaml
spring:
  cloud:
    azure:
      keyvault:
        secret:
          property-sources:
            - endpoint: ${AZURE_KEYVAULT_ENDPOINT}
              refresh-interval: 60m
~~~

Trong các dòng thư viện có hỗ trợ, đặt **refresh-interval: 0** để **tắt auto refresh**. Cẩn thận phân biệt **thời điểm PropertySource đọc lại** với **thời điểm business bean/connection pool sử dụng value mới**.

### 14.2. @Value trong singleton

Một Spring singleton:

~~~java
@Service
public class PartnerClient {
    private final String token;

    public PartnerClient(@Value("${payment-api-token}") String token) {
        this.token = token;
    }
}
~~~

đã giữ token khi constructor chạy. Nếu underlying PropertySource được cập nhật, field token **không tự thay đổi**. Đừng coi refresh-interval=1m là chiến lược rotation đảm bảo mọi client nhận token mới sau đúng một phút.

### 14.3. @RefreshScope có phải giải pháp duy nhất?

Spring Cloud Context có **@RefreshScope** và các cơ chế refresh/rebind riêng, nhưng:
- Không phải mọi project đã import spring-cloud-context/Actuator refresh.
- PropertySource refresh không luôn tự kích hoạt Spring Context refresh theo cách bạn mong đợi.
- Bean đang phục vụ requests có thể còn giữ connection/client cũ.
- Tái tạo bean có thể ảnh hưởng thread safety và graceful switchover.
- DataSource/HikariCP và JPA EntityManager có lifecycle phức tạp.

Chỉ dùng @RefreshScope nếu đã xác minh **end-to-end refresh events, bean recreation, consumer behavior và SDK/Boot version**. Khi không có yêu cầu hot rotation, rolling restart an toàn thường dễ kiểm thử hơn.

### 14.4. SecretClient + application cache

Với SecretClient, có thể:
- Cất value trong RAM cache TTL ngắn với concurrency control.
- Refresh theo lịch hoặc sự kiện.
- Ghi lại version ID đang active (không log value).
- Cập nhật atomically reference tới credential mới.
- Giữ credential cũ trong một giai đoạn overlap nếu upstream cho phép.
- Xử lý 429/timeout bằng backoff; giới hạn số fetch.
- Không cache vô thời hạn khiến rotation không có hiệu lực.

Không xây cơ chế cache phức tạp nếu một startup-only secret và rolling restart đã đủ. Nhưng cũng không gọi Key Vault **trên từng HTTP request** cho workload có nghìn RPS.

### 14.5. Datasource password và connection pool

HikariCP/DataSource có thể giữ password đã bind và các DB connections hiện có. Khi đổi password:
1. App không tự động cập nhật connection pool.
2. New connections có thể dùng credential cũ.
3. Old connections có thể tiếp tục hoạt động trong một thời gian, tùy DB và policy.
4. Nếu DB revoke password cũ ngay, app có thể gặp 401/auth failure trên các kết nối mới.
5. Cần migration/rotation với overlap, bean restart/reconfigure hoặc rolling deployment theo thiết kế.

**Thay secret version trong Key Vault không trực tiếp đổi password ở database hoặc API nhà cung cấp.** Quy trình rotation phải cập nhật cả **nguồn phát hành credential** và **các consumers**.

## 15. Rotation: đổi bí mật không gây gián đoạn

### 15.1. Ba phiên bản trạng thái khác nhau

Một credential thực tế có:
- Version trong Key Vault.
- Version mà Spring Boot instance đang giữ trong RAM.
- Credential value thực sự được downstream DB/đối tác chấp nhận.

Nếu ba trạng thái không đồng bộ, dịch vụ lỗi dù vault báo latest secret thành công.

### 15.2. Quy trình API token có overlap

~~~mermaid
flowchart TD
    A["Old token active"] --> B["Issue new token at partner"]
    B --> C["Create new Key Vault secret version"]
    C --> D["Canary instance refresh/restart"]
    D --> E["Verify partner API with new token"]
    E --> F{"Health and metrics pass?"}
    F -->|Không| R["Rollback app to known working credential"]
    F -->|Có| G["Roll out to all instances"]
    G --> H["Verify all instances use new version"]
    H --> I["Revoke old partner token after overlap"]
    I --> J["Audit / remove stale access"]
~~~

Các bước an toàn:

1. Xác định secret owner, expiry, bên phát hành và thời điểm đổi.
2. Phát hành credential mới ở downstream, nếu cho phép cùng tồn tại hai token.
3. Ghi **version mới** vào Key Vault mà không ghi giá trị ra logs.
4. Giữ token cũ còn valid trong overlap window.
5. Canary test instance với version mới, kiểm tra business operation.
6. Rollout/refresh có kiểm soát; quan sát 401/403/429/p95.
7. Xác minh tất cả instances đã chuyển.
8. Revoke token cũ ở downstream sau khi an toàn.
9. Xem xét disable old Key Vault version theo policy, giữ rollback window hợp lý.
10. Ghi audit/evidence; không lưu secret value trong ticket.

### 15.3. Nếu downstream không hỗ trợ hai credential song song

Cần cửa sổ cutover:
- Có deployment coordination rõ.
- Dừng/queue requests nếu được phép.
- Chuyển password ở downstream và Key Vault gần đồng thời.
- Restart/reconfigure clients.
- Reconnect/health checks.
- Rollback plan với operator chịu trách nhiệm.
- Thông báo downtime/SLA nếu không thể zero-downtime.

Một dịch vụ legacy chỉ có một password có thể không xoay vòng zero downtime được chỉ bằng Key Vault refresh.

### 15.4. Secret versions và rollback

Key Vault giữ versions theo retention và lifecycle được hỗ trợ, nhưng:
- Một version cũ có thể bị disabled/expired.
- Downstream có thể đã revoke credential cũ.
- Latest version không được app dùng ngay nếu cache/bean giữ bản cũ.
- Rollback application sang version cũ **không có tác dụng** nếu bên thứ ba đã thu hồi token.

Rollback phải kiểm tra **Key Vault version + app state + downstream acceptance** chứ không chỉ chọn version ID.

### 15.5. Expiry alerts và rotation ownership

Nên quản lý:
- Metadata expiresOn và policy rotation calendar.
- Alert trước expiry theo số ngày đủ để đổi.
- Owner/backup owner và approval.
- Tài liệu hóa credential source và consumers.
- Log sự kiện rotate/disable/delete với timestamp UTC.
- Thử rotation và rollback định kỳ.
- Thiết lập Key Vault Event Grid event handlers hoặc automation nếu được hỗ trợ và cần thiết.

**Key Vault không tự tạo credential mới ở database/đối tác** chỉ vì SecretNearExpiry event xảy ra. Automation phải tích hợp đúng nguồn phát hành và xác minh trước khi thay.



## 16. Private networking, DNS và TLS

### 16.1. Kết nối Key Vault qua Private Endpoint

Với một Key Vault chỉ cho phép truy cập riêng, cấu hình thường gồm **Azure Private Endpoint**, VNet route và private DNS thích hợp.

~~~mermaid
flowchart LR
    APP["Spring Boot App Service / AKS Pod"] --> VNET["VNet integration / Pod egress"]
    VNET --> DNS["Private DNS resolver"]
    DNS --> PE["Key Vault Private Endpoint"]
    PE --> KV["Azure Key Vault data plane"]
    APP --> ENTRA["Microsoft Entra / Identity endpoint"]
~~~

Có **hai đường** phải thông: lấy token từ Entra/managed identity và kết nối HTTPS tới vault. Có token thành công không có nghĩa DNS tới vault đúng. Kết nối vault thành công chưa chứng minh principal có quyền đọc secret.

### 16.2. FQDN và vùng DNS

Trong Azure public cloud:

- Ứng dụng tiếp tục dùng URL chuẩn **https://<vault-name>.vault.azure.net/**.
- Private DNS Zone thường là **privatelink.vaultcore.azure.net**.
- DNS chain từ runtime trong mạng riêng phải trả về private IP khi cấu hình đúng.
- TLS vẫn xác minh hostname chuẩn theo certificate.
- Không dùng raw private IP làm vaultUrl trong Java code.

Nếu app chạy ở subnet khác, cần DNS forwarding, VNet links và NSG/route thích hợp. Không mở public access toàn cầu chỉ để chữa một lỗi DNS.

### 16.3. Kiểm tra từ runtime thật

1. App Service đã có VNet integration và outbound route phù hợp chưa?
2. AKS Pod thực tế đang dùng DNS resolver và route nào?
3. Private DNS Zone có link đúng VNet hoặc forwarding từ on-premises?
4. Private Endpoint đã approved/connected chưa?
5. NSG/Azure Firewall có cho HTTPS 443 đi qua?
6. TLS trust/hostname validation có đúng không?
7. Microsoft Entra token endpoints/managed identity endpoint reachable không?
8. Identity có data-plane permission đúng?
9. Vault firewall/public network policy có phù hợp route?
10. Có log status code và request ID an toàn để truy vết?

### 16.4. Lỗi mạng và lỗi phân quyền

| Dấu hiệu | Lớp cần kiểm tra |
|---|---|
| DNS resolution fail | Resolver, private zone, forwarding |
| DNS trả public IP từ Pod private | DNS chain/zone link sai |
| Connect timeout | Route/NSG/firewall/proxy |
| TLS handshake failure | CA trust/hostname/clock |
| 401 | Identity/token/tenant |
| 403 | RBAC/access policy hoặc vault firewall |
| 404 | Vault/secret/version sai |
| 429 | Key Vault throttling |
| 5xx | Transient service error, retry có giới hạn |

**Không tăng quyền thành Key Vault Administrator khi gặp 403** trước khi phân biệt firewall và RBAC. Không tắt certificate validation hoặc mở public access vô hạn để khắc phục tạm.

## 17. Platform integration: App Service references và AKS CSI

### 17.1. App Service Key Vault references

Azure App Service hỗ trợ **Key Vault reference** trong Application Settings: nền tảng resolve secret bằng identity và cung cấp value cho runtime.

~~~text
App Setting name:
  PAYMENT_API_TOKEN

App Setting value (ví dụ cấu trúc):
  @Microsoft.KeyVault(SecretUri=https://<vault-name>.vault.azure.net/secrets/payment-api-token/)
~~~

Cấu hình này **khác** Spring Cloud Azure PropertySource:

- App Service chịu trách nhiệm giao tiếp Key Vault cho reference.
- Spring nhận environment/application property đã được resolve.
- Refresh/cache của App Service reference theo chính sách nền tảng, không phải PropertySource refresh-interval.
- Environment variable của process và bean đã bind có thể không tự đổi khi reference được refresh.
- Nếu reference không resolve được, ứng dụng cần fail/alert thay vì coi chuỗi @Microsoft.KeyVault(...) là một API token hợp lệ.

App Service identity phải có Key Vault permissions/network route phù hợp; không dùng app setting chứa actual secret value từ repo để né IAM.

### 17.2. AKS Secrets Store CSI Driver

Azure Key Vault Provider for Secrets Store CSI Driver có thể:
- Mount secrets thành files trong Pod.
- Đồng bộ sang Kubernetes Secret khi cấu hình hỗ trợ.
- Được tích hợp với workload identity/managed identity theo setup cụ thể.
- Có cơ chế rotation/sync theo driver/provider và version.

Nhưng:
- Mounted file cần file permissions phù hợp với container user.
- Spring bean đọc file một lần không tự cập nhật khi file trên mount thay đổi.
- Nếu sync sang Kubernetes Secret, cần Kubernetes RBAC/encryption-at-rest/etcd backup policy.
- Secret của nhiều namespaces/tenants không được nằm trong một shared mount quá rộng.
- Không để Pod có quyền đọc mọi secret trong cluster.

### 17.3. Quyết định mô hình tích hợp

| Bối cảnh | Điểm bắt đầu đánh giá |
|---|---|
| Spring cần dùng secret để bind config | Spring Cloud Azure PropertySource |
| Cần version/metadata, refresh khi chạy | SecretClient và cache riêng |
| App Service đã chuẩn hóa KV references | App Settings Key Vault reference |
| AKS platform team chuẩn hóa secret mounts | CSI Driver theo workload identity |
| Database hỗ trợ Entra passwordless | Bỏ password secret, dùng identity |

Không nạp cùng một secret đồng thời bằng environment, platform reference và PropertySource nếu chưa hiểu precedence và cách rotate.

## 18. Spring Boot Actuator, logging và bảo vệ giá trị secret

### 18.1. Những nơi dễ làm lộ secrets

- Println secret trong CommandLineRunner hoặc health checks.
- Log toàn bộ Environment hoặc @ConfigurationProperties.
- Exception chứa connection string có mật khẩu.
- Spring Actuator /env, /configprops, /heapdump hoặc /logfile bị public.
- HTTP logging BODY hoặc BODY_AND_HEADERS của Azure SDK.
- Metric label chứa token, secret name nhạy cảm hoặc raw URL.
- ToString của DTO/record chứa secret.
- Heap dump/core dump lưu ở storage quá rộng quyền.
- CI/CD logging các biến môi trường hoặc command-line arguments.
- Web controller vô tình serialize bean chứa secret.

### 18.2. Cấu hình Actuator cẩn trọng

Nếu dự án sử dụng **spring-boot-starter-actuator**, cấu hình ví dụ:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info
  endpoint:
    env:
      show-values: never
    configprops:
      show-values: never
    health:
      show-details: never
~~~

Điều này làm giảm nguy cơ lộ config từ Actuator, nhưng **không thay authentication/authorization và network protection**. Các phiên bản Spring Boot có defaults khác nhau; kiểm thử các endpoints thực được expose, không suy luận chỉ từ YAML.

### 18.3. Những gì nên log

Có thể ghi:
- Key Vault operation category (READ/REFRESH/ROTATE).
- Vault identifier ở mức đã được chính sách cho phép.
- Response status/error class và latency.
- Request/correlation ID được kiểm soát.
- Source/version metadata khi cần, không chứa value.
- Application release/instance ID và UTC timestamp.
- Startup/rotation health trạng thái PASS/FAIL.

Không ghi:
- KeyVaultSecret.getValue().
- Authorization header/access token.
- JDBC connection string đầy đủ nếu có password.
- Raw PropertySources dump.
- SAS signature hoặc client secret.
- Hash/fingerprint secret nếu policy không cho phép.

### 18.4. HTTP logging, tracing và metrics

Azure SDK for Java có HttpLogOptions với những mức NONE, BASIC, HEADERS, BODY, BODY_AND_HEADERS. Khi liên quan secrets, bắt đầu từ **NONE/BASIC** và áp allowlist/redaction theo security policy.

Metrics nên có cardinality thấp, chẳng hạn operation, service, status class và environment. Không dùng raw URL/username/secret value làm tags. Application Insights/Log Analytics/traces cần RBAC và retention thích hợp.

### 18.5. Quy trình khi phát hiện secret bị lộ

1. Ngăn tiếp tục phát tán: khóa log/artifact/web endpoint.
2. Xác định phạm vi rò rỉ: repo, container, CI, logs, Actuator.
3. Rotate/revoke credential tại **downstream issuer**; chỉ đổi Key Vault version có thể chưa vô hiệu hóa token cũ.
4. Đánh giá quyền truy cập vault/identity và giảm scope nếu cần.
5. Thu thập audit evidence theo retention/incident policy.
6. Thay credentials ở mọi ứng dụng liên quan theo rollout plan.
7. Xử lý artifacts sao cho không phá legal hold.
8. Thực hiện security review và secret scanning.
9. Diễn tập lại tests và giám sát bất thường sau sự cố.



## 19. Resilience, caching, quota và chi phí

### 19.1. Key Vault là dependency quan trọng

Nếu PropertySource cần secret để khởi tạo DataSource mà vault unavailable, Spring Boot có thể **không hoàn thành startup**. Nếu hot-path gọi SecretClient mỗi HTTP request, Key Vault 429/timeout có thể làm latency API tăng mạnh.

Có thể áp dụng:
- Startup lookup và rolling deployment.
- PropertySource refresh theo khoảng kiểm soát.
- SecretClient với cache/atomic refresh.
- Bounded retry/backoff, tôn trọng Retry-After.
- Lựa chọn fail closed hoặc fallback được phê duyệt.
- Alert expiry, 401/403, 429 và Key Vault latency.
- Giới hạn số instance refresh cùng lúc.
- Kiểm tra quota và service availability theo tier/region.

### 19.2. Fail closed hay fail open?

**Fail closed:** nếu thiếu signing secret, payment token hoặc DB credential bắt buộc, dừng thao tác nhạy cảm và báo lỗi thay vì dùng giá trị giả.

**Fallback có điều kiện:** nếu vault tạm lỗi nhưng app giữ một token hợp lệ trong RAM cache, có thể tiếp tục trong thời gian hạn chế **chỉ khi security policy cho phép**. Không dùng token đã bị revoke hoặc expired.

Bảng quyết định:

| Tình huống | Hướng xử lý |
|---|---|
| Chưa từng đọc được payment token | Fail closed / readiness unhealthy |
| Token cache còn hạn, vault tạm mất | Cân nhắc dùng cache theo policy |
| Credential đã bị thu hồi ở downstream | Không dùng cache cũ |
| Feature flag không nhạy cảm | Fallback theo business policy |
| Hệ thống ký yêu cầu thanh toán | Không tự thay bằng signing secret mặc định |
| App cần DB password lúc khởi động | Fail/startup retry bounded, có alert |

**Không viết catch(Exception) return "default-token"** cho secrets quan trọng.

### 19.3. Retry và timeout của Spring Cloud Azure

Có thể cấu hình retry riêng cho Key Vault PropertySource:

~~~yaml
spring:
  cloud:
    azure:
      keyvault:
        secret:
          property-sources:
            - endpoint: ${AZURE_KEYVAULT_ENDPOINT}
              retry:
                mode: exponential
                exponential:
                  max-retries: 3
                  base-delay: PT0.2S
                  max-delay: PT5S
~~~

Các thông số chỉ là ví dụ. Spring Cloud Azure có các properties dành cho retry, timeout, proxy theo từng service/property source và global defaults. Chọn values theo API SLO và mạng thực tế, không copy một cấu hình vào mọi workload.

Phân biệt:
- Connect timeout.
- Response/read timeout.
- Retry attempts và backoff.
- Startup timeout.
- Total business operation deadline.
- Retry ở Spring Retry, queue trigger hoặc gateway.

Không chồng nhiều tầng retry mà không có tổng số attempts giới hạn.

### 19.4. Vì sao không gọi Key Vault trong từng request?

Giả sử Orders API nhận 1.000 requests/giây và mỗi request đọc 2 secrets:

~~~text
1,000 API requests/s × 2 Key Vault GETs
    = 2,000 Key Vault GETs/s
~~~

Đó là **lưu lượng minh họa**, không phải quota hay giá chính thức. Nếu có nhiều replicas và mỗi replica refresh toàn bộ vault, chi phí và throttling còn tăng thêm.

Cách tốt hơn:
1. Chỉ fetch secrets cần dùng.
2. Cache an toàn trong RAM theo freshness/security policy.
3. Refresh ngoài hot path hoặc theo event có kiểm soát.
4. Không giữ secret vô thời hạn nếu rotation phải có hiệu lực.
5. Phân biệt latest version với credential đang active.
6. Rate limit và giới hạn concurrent refreshes.
7. Theo dõi hit/miss, 429, latency, rotation success.

### 19.5. Startup storm

Một lần scale 100 pods cùng lúc, mỗi pod list/get 500 secrets, có thể tạo burst rất lớn.

Giảm rủi ro:
- Chỉ cấu hình **secret-keys** cần dùng.
- Tách vault/permission theo workload.
- Rolling deployment với tốc độ tăng instances hợp lý.
- Retry backoff/jitter đúng.
- App startup/readiness behavior rõ.
- Tránh nhiều background refresh triggers trùng nhau.
- Monitoring request rate/429/availability.

Không tăng quyền của identity lên Secrets Officer chỉ để tránh lỗi 429; role không phải công cụ điều tiết tải.

### 19.6. Tổng chi phí

~~~text
Total secret-management cost =
    Azure Key Vault operations/transactions theo pricing
  + Identity/network/Private Endpoint khi áp dụng
  + Azure App Service/AKS/Functions compute
  + Azure Monitor/Log Analytics ingestion + retention
  + Rotation automation, CI/CD, approval, audit
  + Chi phí retry, polling, startup storms
  + Incident/recovery operations
~~~

Đừng chỉ đo số lượng secret names. **Số GET/list, replicas, refresh rate và cache miss** ảnh hưởng mạnh đến số calls. Giá/quotas thay đổi theo SKU, region và thời gian; dùng Azure Pricing Calculator, Cost Management và Key Vault metrics hiện hành để dự toán.

## 20. Kiểm thử lặp lại và không dùng secret production

### 20.1. Unit test không cần vault thật

Trong application-test.yml có thể vô hiệu PropertySource và dùng value giả cho các bean:

~~~yaml
spring:
  cloud:
    azure:
      keyvault:
        secret:
          property-source-enabled: false

payment-api-token: fake-token-for-test-only
~~~

Khi test phải chỉ rõ active Spring profile và bảo đảm không vô tình load application-prod.yml. Giá trị fake không phải credential thật, dùng để kiểm thử binding; không làm app test gọi API payment production.

### 20.2. Mock SecretClient

~~~java
import static org.mockito.Mockito.when;
import static org.junit.jupiter.api.Assertions.assertEquals;

import com.azure.security.keyvault.secrets.SecretClient;
import com.azure.security.keyvault.secrets.models.KeyVaultSecret;
import org.junit.jupiter.api.Test;
import org.mockito.Mockito;

class PaymentCredentialProviderTest {
    @Test
    void readsFakeTokenWithoutAzureNetwork() {
        SecretClient client = Mockito.mock(SecretClient.class);

        when(client.getSecret("payment-api-token"))
            .thenReturn(new KeyVaultSecret(
                "payment-api-token", "fake-test-only"));

        PaymentCredentialProvider provider =
            new PaymentCredentialProvider(client);

        assertEquals("fake-test-only", provider.loadCurrentToken());
    }
}
~~~

Mã ví dụ giả định test class có JUnit 5 và Mockito dependencies tương thích. Unit test không liên hệ Key Vault thật, không kiểm thử TLS/Entra/RBAC; cần integration tests riêng trên staging.

### 20.3. Integration test matrix

| Test | Điều kiện kỳ vọng |
|---|---|
| Đúng vault, đúng identity | App đọc được secret giả, không log value |
| Sai role | 403 được phân loại, không retry vô hạn |
| Sai secret name | 404 được xử lý, không dùng default production |
| Secret disabled/expired | Startup/read path phản ứng theo policy |
| Sai tenant | Token/auth error được ghi metadata |
| Private DNS sai | Timeout được phát hiện ở tầng network |
| 429 | Bounded retry/cache, không gây storm |
| Trùng tên ở hai vaults | Precedence đúng theo cấu hình |
| Env override | Shadowed property được phát hiện bằng kiểm thử |
| Rotation value mới | App/bean/DB pool sử dụng đúng version theo rollout |
| Rollback | Chỉ dùng version cũ khi downstream chấp nhận |
| Multi-instance startup | Không vượt throughput/quota thiết kế |
| Actuator/logs | Không expose secret value |
| CSI/App Service reference | Refresh đúng nghĩa theo platform |
| Revoke identity | App mất quyền đúng, có alert |

### 20.4. Negative security tests

- Orders runtime identity không đọc được Billing vault.
- Anonymous HTTP user không xem được /env, /configprops, /heapdump.
- App không in TokenCredential/access token vào logs.
- Một environment variable secret giả không override production ngoài chủ đích.
- CI pipeline không in value khi rotate.
- Không tắt TLS hostname verification.
- Mất DNS không khiến app tự mở public Key Vault access.
- Khi secret không tồn tại, app không dùng fallback hard-coded.
- Khi rotation, credentials cũ được revoke sau overlap theo policy.

### 20.5. Evidence nên lưu

- BOM/Boot/JDK versions, deployment commit SHA.
- Vault URI, permission model và principal object ID.
- Role assignment scope và policy approval.
- Test case PASS/FAIL, status/error type, timestamps UTC.
- Secret names/version IDs khi chính sách cho phép, **không ghi values**.
- Latency/quota/retry metrics và log redaction test.
- Mốc rotation, readiness, rollback và incident owner.



## 21. Runbook sự cố Key Vault trong Spring Boot

### 21.1. Bảng lỗi theo dấu hiệu

| Triệu chứng | Nguyên nhân thường gặp | Chẩn đoán/hành động |
|---|---|---|
| Startup fail vì unresolved placeholder | Secret không được nạp, sai name, thiếu starter | Kiểm tra PropertySource config, secret-keys |
| 401 ở getSecret | Tenant/audience/credential sai | Xác nhận DefaultAzureCredential chain |
| 403 ở getSecret | Không có Secrets User/access policy | Kiểm tra data-plane permission model |
| 403 dù role đúng | Key Vault firewall/Private Link | Xem diagnostics, network access |
| 404 secret not found | Sai vault/name/version hoặc secret bị xóa | Xem metadata/tên và lifecycle |
| Không đọc được secret disabled | Version disabled | Kiểm tra enabled và rotation runbook |
| Secret hết hạn | ExpiresOn/consumer renewal không khớp | Phát hành credential mới |
| DNS trả public IP | Private DNS chưa đúng | Kiểm tra zone link/forwarder |
| Connection timeout | VNet/NSG/firewall/proxy | Kiểm tra từ runtime thật |
| 429 | Quá nhiều refresh/retry/replicas | Cache, secret-keys, backoff, rate limit |
| Bean vẫn dùng token cũ | @Value singleton/datasource đã bind | Rolling restart hoặc refresh bean có test |
| Local chạy, production fail | Developer credential khác managed identity | Xác định principal tại runtime |
| Production đọc vault dev | Endpoint/env config sai | Env allowlist, release verification |
| Env var thắng Key Vault | PropertySource precedence | Kiểm tra shadowing |
| Secret được rotate nhưng DB lỗi | Downstream password đổi không đồng bộ | Cutover/overlap plan |
| Logs có secret | Custom logging/Actuator | Chặn, revoke, audit |
| CSI file đã đổi nhưng app chưa đổi | App chưa reload file/client | Implement watcher/restart phù hợp |
| App Service reference chưa đổi | Platform cache/ref resolution | Kiểm tra config refresh và restart |
| Lỗi sau nâng Boot/SDK | BOM/classpath mismatch | Kiểm tra version mapping/dependencies |

### 21.2. Runbook: 403 khi Spring Boot khởi động

1. Ghi resource name, UTC timestamp, Java exception type, status code; không log value.
2. Kiểm tra vault endpoint trong environment/profile.
3. Xác định **principal thực** của Azure Identity ở runtime, không dựa tên dự kiến.
4. Kiểm tra tenant/subscription và Key Vault permission model.
5. Nếu dùng RBAC, xem role **Key Vault Secrets User** ở vault/secret scope thích hợp.
6. Nếu vault dùng access policy, kiểm tra policy data-plane thay vì RBAC role.
7. Kiểm tra role assignment đã propagate và secret enabled.
8. Nếu quyền chính xác, xem Key Vault network/firewall diagnostics.
9. Thử GET secret giả/metadata trong staging với cùng runtime identity.
10. Chỉ tăng quyền khi có bằng chứng và approval; không gán Administrator để “test nhanh”.

### 21.3. Runbook: thay secret nhưng ứng dụng chưa nhận

1. Xác định secret name, latest version ID, event rotation time.
2. Kiểm tra downstream đã cấp credential mới chưa.
3. Kiểm tra PropertySource refresh interval, danh sách secret-keys.
4. Kiểm tra environment variable/app setting có override property không.
5. Kiểm tra Spring bean giữ @Value khi khởi tạo hay đang đọc qua SecretClient.
6. Kiểm tra cache TTL và thời gian refresh thực tế.
7. Nếu dùng HikariCP/DataSource, xác định pool dùng password/connection nào.
8. Thử canary/restart một instance với value mới.
9. Đo lỗi 401, connection failures và business health.
10. Rollout toàn bộ hoặc rollback theo kế hoạch; revoke old credential đúng thời điểm.

### 21.4. Runbook: Key Vault private-only không truy cập được

1. Xác định App Service/AKS/VM/Functions deployment.
2. Thử DNS lookup hostname chuẩn của vault từ runtime.
3. Kiểm tra Private DNS Zone **privatelink.vaultcore.azure.net**.
4. Kiểm tra VNet link/forwarding, Private Endpoint connection.
5. Kiểm tra NSG, Azure Firewall, proxy và route table.
6. Kiểm tra TLS trust chain và đúng hostname.
7. Kiểm tra managed identity token endpoint/Entra reachability.
8. Xem Key Vault diagnostic logs để phân biệt network deny và 403 role.
9. Không tự mở public access toàn cầu.
10. Khôi phục network bằng IaC/change approval, kiểm thử mọi replicas.

### 21.5. Runbook: 429 và service latency tăng

1. Đo Key Vault GET/list operations theo thời gian.
2. Xác định số app instances, refresh intervals và secret-keys.
3. Kiểm tra có đang fetch mỗi HTTP request không.
4. Kiểm tra retry layers, Retry-After và total timeout.
5. Giới hạn concurrent refresh/startup, tăng jitter/backoff.
6. Dùng cache theo security freshness requirements.
7. Giảm số secrets được nạp và tách workloads khi phù hợp.
8. Kiểm tra pricing/quota/region và alerts.
9. Diễn tập trên staging trước khi scale-out lại.
10. Theo dõi p95/p99, 429, startup success và cost.

### 21.6. Runbook: xóa nhầm secret hoặc vault

1. Ngừng thao tác xóa/cleanup tiếp theo và khóa change window nếu cần.
2. Xác minh soft-delete state và retention/purge protection.
3. Không purge resource để “làm sạch”, vì có thể không khôi phục được.
4. Dùng recovery workflow có approval để restore vault/secret nếu còn trong thời hạn.
5. Kiểm tra version và trạng thái enabled, expiry.
6. Xác minh downstream credential vẫn còn hợp lệ.
7. Canary app với vault/secret đã phục hồi.
8. Đối soát những lần rotation/revoke xảy ra trong sự cố.
9. Ghi postmortem và cập nhật IaC guardrails/quyền delete.
10. Không in secret value trong incident ticket hoặc restore logs.

## 22. Case study: Spring Boot Orders API trên Azure

### 22.1. Yêu cầu

Một hệ thống quản lý đơn hàng có:
- Spring Boot Orders API trên Azure App Service.
- Azure SQL Database lưu orders; trong giai đoạn đầu một service legacy dùng password.
- Một đối tác thanh toán yêu cầu API token.
- Blob Storage lưu invoice files.
- App Configuration quản lý feature flags (không nhạy cảm).
- Key Vault quản lý token/password cần giữ bí mật.
- Application Insights giám sát latency/401/403/429.
- VNet/Private Endpoint theo yêu cầu bảo mật doanh nghiệp.
- Kế hoạch chuyển database sang Entra passwordless khi được hỗ trợ.

### 22.2. Kiến trúc tham khảo

~~~mermaid
flowchart LR
    U["Client / API Gateway"] --> APP["Spring Boot Orders API"]
    APP --> ID["Managed Identity / Entra"]
    APP --> KV["Azure Key Vault Secrets"]
    APP --> DB["Azure SQL Database"]
    APP --> BLOB["Azure Blob Storage"]
    APP --> CFG["Azure App Configuration"]
    APP --> PAY["Payment partner"]
    APP --> MON["Azure Monitor / App Insights"]
    KV -. "Audit + alerts" .-> MON
~~~

Không phải mọi resource bắt buộc dùng cùng VNet hoặc public network setting. Private Endpoint, DNS và identity được thiết kế theo từng service/deployment; sơ đồ là logical architecture.

### 22.3. Tách secrets và config

| Biến | Lưu ở đâu | Ai dùng |
|---|---|---|
| AZURE_KEYVAULT_ENDPOINT | App Setting (non-secret) | Spring Cloud Azure config |
| PAYMENT_API_TOKEN | Key Vault secret | Payment integration |
| LEGACY_DB_PASSWORD | Key Vault secret | JDBC DataSource tạm thời |
| FEATURE_CHECKOUT_V2 | App Configuration | Feature flag |
| Storage endpoint | App config (non-secret) | Blob SDK |
| Azure access token | Azure Identity lấy động | SDK data-plane access |
| Key Vault principal permissions | Azure RBAC/access policy | Runtime identity |

Lưu ý: đừng tạo một secret mới cho Azure Storage account key nếu có thể dùng Blob Data RBAC với managed identity. Tương tự, nên loại bỏ legacy DB password khi cơ sở dữ liệu và driver hỗ trợ Entra authentication theo yêu cầu.

### 22.4. Quy trình deployment

1. IaC/Platform team cấu hình App Service, managed identity và Vault.
2. Security team gán role đọc secrets tối thiểu.
3. Network team kiểm tra Key Vault Private Endpoint/DNS từ App Service.
4. Release pipeline deploy Spring Boot với endpoint **không nhạy cảm**.
5. Spring PropertySource nạp payment-api-token và db-password ở startup.
6. App readiness kiểm tra beans và kết nối downstream theo chính sách.
7. Smoke tests xác minh payment sandbox/DB và không log secret value.
8. Monitoring ghi secret read latency/429, startup error, downstream auth error.
9. Canary/rolling deployment rồi promote production.
10. Có rollback/rotation policy rõ.

### 22.5. Kịch bản 1: đổi payment token có overlap

- Đối tác phát hành token mới, giữ token cũ một thời gian.
- Rotation pipeline tạo version mới trong Key Vault.
- Canary App Service instance được restart hoặc refresh đúng cách.
- Test payment sandbox/low-risk operation thành công.
- Triển khai lần lượt tới mọi instance, đo 401/latency.
- Xác minh app fleet đã dùng token mới.
- Revoke token cũ ở đối tác sau overlap.
- Ghi audit, owner approval, không log token.

### 22.6. Kịch bản 2: đổi DB password không có overlap

Nếu DB chỉ hỗ trợ một password active cho user:
- Cần coordinated cutover/maintenance window.
- Tách DB credential rotation khỏi rollback app thông thường.
- Drain traffic/queue jobs theo business SLA.
- Update DB password và Key Vault version trong change window.
- Restart/reconfigure HikariCP/DataSource đúng cách.
- Xác minh JDBC new connections và transactions.
- Theo dõi connection errors và rollback thủ tục.
- Dài hạn cân nhắc Entra passwordless để bỏ shared password.

### 22.7. Tiêu chí chấp nhận

1. Không có secret thật trong repo, Docker image hoặc config artifact.
2. Runtime identity chỉ có quyền đọc vault của Orders.
3. Developer không có quyền đọc production vault mặc định.
4. Local test có thể dùng fake secret và Azure CLI lab identity.
5. Spring PropertySource resolve được đúng secret names.
6. SecretClient không được gọi trên từng HTTP request khi không cần.
7. @Value beans và DataSource có rotation/restart behavior được kiểm chứng.
8. Mạng private-only hoạt động từ runtime thật.
9. 401/403/404/429 được phân loại đúng, có runbook.
10. Không có secret value trong Actuator/logs/traces.
11. Rollout và rollback không dùng credential đã revoke.
12. Có budget/quota monitoring và audit evidence.

## 23. Những lỗi thiết kế nên tránh

| Sai lầm | Hệ quả | Cách đúng hơn |
|---|---|---|
| Đặt password trong application.yml | Lộ qua repo/build | Key Vault hoặc passwordless |
| Commit .env có credential thật | Secret trong Git history | Secret scanning, rotation |
| In getSecret().getValue() để debug | Lộ vào logs | Log status/version metadata |
| Gán Key Vault Administrator cho app | Blast radius lớn | Secrets User theo scope |
| Trộn RBAC và access policies | 403 khó hiểu | Kiểm tra permission model |
| Dùng vault prod cho developer local | Rủi ro truy cập ngoài scope | Vault/identity riêng |
| Bỏ secret-keys, load toàn vault | Tăng calls/exposure | Limit names |
| Tin rằng refresh update mọi @Value bean | Token cũ vẫn dùng | Rebind/restart theo test |
| Rotate vault nhưng không đổi upstream password | Credential mismatch | Đồng bộ issuer và consumer |
| Revoke old token trước khi app chuyển hết | Outage | Overlap/canary/verify |
| Gọi Key Vault mỗi API request | 429, latency, cost | Cache/refresh |
| In Spring Environment qua REST | Expose secret | Actuator security, no dump |
| Sửa DNS bằng cách tắt TLS | MITM risk | DNS/TLS fix |
| Thấy 403 liền cấp Owner | Sai permission/cấp quá rộng | Data-plane RBAC diagnosis |
| Bật public network cho private-only vault | Security policy breach | Fix VNet/Private DNS |
| Dùng App Service reference và PropertySource không kiểm soát | Shadowing/refresh khó hiểu | Chọn một nguồn chính |
| Coi SecretClient cache mặc định vĩnh viễn | Rotation stale | Cache policy rõ |
| Tin Key Vault expiry tự đổi mật khẩu DB | Service auth fail | Rotation workflow |
| Chọn tên secret tùy ý có dấu chấm | Tên invalid | Kebab-case, placeholders |
| Không có cleanup/soft-delete plan | Mất recoverability | Purge protection/approval |
| Mở body-level HTTP logs | Rò rỉ secret | NONE/BASIC và redaction |



## 24. Checklist production

### 24.1. Data classification và secret lifecycle

- [ ] Đã phân loại secret thật, non-secret configuration, keys và certificates.
- [ ] Đã xem khả năng **passwordless/Entra authentication** thay cho secret lưu trữ.
- [ ] Mỗi secret có owner, use case, consumers, expiration và rotation schedule.
- [ ] Key Vault secret names tuân thủ chữ cái/chữ số/dấu gạch nối.
- [ ] Có quy trình tạo version mới, canary, overlap, revoke và rollback.
- [ ] Không dùng giá trị production trong test fixtures, README hoặc CI logs.
- [ ] Tags/metadata không chứa secret value hoặc PII không cần thiết.
- [ ] Soft delete/purge protection và retention phù hợp recovery/compliance.
- [ ] Có alert trước expiry và owner được phân công.

### 24.2. Spring Boot integration

- [ ] BOM Spring Cloud Azure khớp Spring Boot/JDK, các starters đúng phiên bản.
- [ ] Chọn PropertySource, SecretClient hoặc platform reference có chủ đích.
- [ ] Endpoint vault đến từ cấu hình non-secret đã được kiểm tra.
- [ ] Secret-keys chỉ liệt kê những names cần thiết.
- [ ] Những property nhiều nguồn có precedence được test.
- [ ] Biến môi trường không vô tình override giá trị vault.
- [ ] Không có credentials hard-coded trong YAML, Docker image hoặc source.
- [ ] @Value/@ConfigurationProperties/auto-config beans sử dụng value đúng ở startup.
- [ ] Đã kiểm thử **refresh không đồng nghĩa bean rebind**.
- [ ] HikariCP/DataSource rotation được thực hành, không chỉ lý thuyết.
- [ ] SecretClient được reuse; cache/refresh policy rõ.
- [ ] Fallback khi mất Key Vault được security team phê duyệt.

### 24.3. Identity và least privilege

- [ ] Dev/staging/prod có identities và vaults tách biệt theo policy.
- [ ] Runtime dùng managed identity hoặc workload identity khi hỗ trợ.
- [ ] Principal object ID, client ID và tenant ID được phân biệt đúng.
- [ ] Vault permission model RBAC/access policy đã được xác minh.
- [ ] Runtime chỉ có **Key Vault Secrets User** hoặc quyền hẹp cần thiết.
- [ ] Rotation/deployment identity tách khỏi runtime.
- [ ] Không dùng service principal client secret khi có federation/managed identity phù hợp.
- [ ] Role assignments có owner/approval và review định kỳ.
- [ ] Negative test chứng minh app A không đọc được secrets của app B.

### 24.4. Networking và security

- [ ] Vault URI dùng hostname chuẩn, TLS validation vẫn bật.
- [ ] VNet/Private Endpoint/DNS được kiểm thử từ runtime thật.
- [ ] Private DNS Zone privatelink.vaultcore.azure.net và resolver được cấu hình đúng.
- [ ] Token endpoint/managed identity và Key Vault data plane đều reachable.
- [ ] Key Vault public access/firewall theo security policy.
- [ ] Actuator không công khai /env, /configprops, /heapdump.
- [ ] HTTP logs không ở BODY/BODY_AND_HEADERS production khi có secret.
- [ ] Logs, traces, metrics và exceptions không in secret values.
- [ ] Secret scanning ở Git, CI, container artifacts.
- [ ] Audit logs, access logs, diagnostic settings và retention được phê duyệt.

### 24.5. Resilience, cost và operations

- [ ] Có retry/backoff/timeout budget theo workload.
- [ ] 401/403/404/429/5xx được phân loại đúng.
- [ ] Không retry vô hạn để chữa role/network không hợp lệ.
- [ ] Refresh không diễn ra mỗi HTTP request khi không cần.
- [ ] Multi-instance deploy không tạo startup storm.
- [ ] Có metrics GET/list/latency/429, startup success và rotation status.
- [ ] Có cảnh báo expiry, disabled secret, configuration mismatch.
- [ ] Có staging tests cho rotation/rollback/secret outage.
- [ ] Có budget/Cost Management cho vault, Private Link, logging, automation.
- [ ] Có runbook principal/network/rotation/deletion và owner on-call.
- [ ] IaC triển khai roles/network không chứa secret values trong state/log thiếu bảo vệ.
- [ ] Có plan migration khỏi legacy passwords về Entra authentication.

## 25. Câu hỏi tự kiểm tra

1. **Secret là gì?** Giá trị cần giữ kín như password, API token hoặc signing secret.
2. **Tại sao không ghi secret trong application.yml?** Có thể lộ qua source control, JAR, Docker image và build artifacts.
3. **Key Vault có những loại object chính nào?** Secrets, Keys, Certificates.
4. **Secret version có tác dụng gì?** Lưu phiên bản của một secret name để kiểm soát thay đổi và rollback khi còn hợp lệ.
5. **ExpiresOn có tự tạo credential mới không?** Không.
6. **Key Vault có thay authorization ở API ứng dụng không?** Không.
7. **PropertySource làm gì?** Nạp Key Vault secret thành Spring Environment property.
8. **SecretClient làm gì?** Cho Java code đọc secret/value/version/metadata theo nhu cầu.
9. **Khi nào nên dùng PropertySource?** Secret cần khi startup cho bean/auto-config.
10. **Khi nào nên dùng SecretClient?** Cần đọc theo nhu cầu, quản lý version hoặc cache riêng.
11. **App Service Key Vault reference khác PropertySource thế nào?** Platform resolve reference, thay vì Spring Cloud Azure tự nạp vault property.
12. **CSI Driver thường làm gì?** Mount secrets vào Pod qua filesystem hoặc sync Secret theo cấu hình.
13. **Managed identity giải quyết việc gì?** Lấy Entra token mà không giữ client secret dài hạn.
14. **Developer local thường đăng nhập thế nào?** Azure CLI/developer credential chain theo Azure Identity.
15. **App Service production nên dùng identity nào?** Managed identity được cấp quyền tối thiểu.
16. **AKS workload identity dựa trên gì?** ServiceAccount/OIDC/federated identity credential.
17. **Azure Contributor mặc định đọc secret value được không?** Không khi vault dùng RBAC data-plane.
18. **Key Vault Reader có đọc secret value không?** Không, chỉ metadata theo quyền.
19. **Vai trò đọc secret thông dụng là gì?** Key Vault Secrets User.
20. **Secrets Officer nên gán cho app read-only không?** Không, quyền quá rộng.
21. **RBAC và vault access policy có giống nhau không?** Không, phải kiểm tra permission model.
22. **Secret names được dùng dấu chấm không?** Không; dùng chữ, số, dấu gạch nối.
23. **Đổi spring.datasource.password thành secret name nào trong Key Vault?** Có thể dùng spring-datasource-password hoặc mapping placeholder.
24. **secret-keys có giúp giảm nạp toàn vault không?** Có, nhưng không thay IAM.
25. **Secret-keys nên viết khác hoa thường tùy ý không?** Không; tên phải khớp giá trị trong vault.
26. **Env var có thể override Key Vault PropertySource không?** Có, theo precedence được tài liệu mô tả.
27. **Hai Key Vault PropertySources trùng key xử lý thế nào?** Theo thứ tự ưu tiên và cấu hình.
28. **PropertySource mặc định refresh bao lâu trong tài liệu hiện hành?** Khoảng 30 phút.
29. **refresh-interval: 0 thường dùng để làm gì?** Tắt auto refresh khi dòng SDK hỗ trợ.
30. **Refresh PropertySource có tự đổi field @Value trong singleton không?** Không tự động.
31. **Refresh có tự tạo lại HikariCP với password mới không?** Không được giả định.
32. **Rotate secret trong Key Vault có đổi password tại database không?** Không.
33. **Tại sao cần overlap khi đổi API token?** Để chuyển mọi consumers trước khi revoke token cũ.
34. **Nếu downstream không hỗ trợ hai password đồng thời thì sao?** Cần cutover/maintenance hoặc giải pháp chuyển đổi khác.
35. **Rollback Key Vault version cũ có luôn hoạt động không?** Không nếu downstream đã revoke credential cũ.
36. **Tại sao không fetch Key Vault mỗi HTTP request?** Gây latency, quota/429 và transaction cost.
37. **Một rủi ro của startup storm?** Hàng trăm replicas cùng get/list secrets và bị throttling.
38. **Vault private-only dùng endpoint nào trong Java?** Hostname chuẩn vault.azure.net, không phải raw private IP.
39. **Private DNS Zone Key Vault thường dùng trong Azure public cloud?** privatelink.vaultcore.azure.net.
40. **Có thể chữa Private DNS bằng cách tắt TLS không?** Không, nguy hiểm và sai nguyên nhân.
41. **401 khác 403 thế nào?** 401 thường là authentication, 403 thường authorization/network policy.
42. **404 khi get secret nghĩa gì?** Tên/version không tồn tại hoặc lifecycle không đáp ứng.
43. **429 khi get secret cần làm gì?** Cache/backoff/rate limit, tôn trọng retry policy.
44. **Secret có thể bị lộ qua Actuator ở đâu?** /env, /configprops, dumps hoặc custom endpoint.
45. **Có nên log KeyVaultSecret.getValue() không?** Không.
46. **Vì sao secret-scanning Git history quan trọng?** Xóa dòng hiện tại không làm mất secret khỏi commit cũ.
47. **Unit tests có bắt buộc dùng vault production không?** Không; dùng fake values/mock.
48. **Integration test cần kiểm tra gì?** Identity, RBAC, network, rotation, precedence, logs và failure modes.
49. **Soft delete/purge protection hỗ trợ gì?** Khôi phục và chống xóa ngoài ý muốn trong điều kiện/retention được hỗ trợ.
50. **Một thiết kế secret production tốt có gì?** Identity tối thiểu, vault phù hợp, lifecycle/rotation, network/TLS, caching, logging an toàn, monitoring, tests và runbook.

## 26. Tài liệu tham khảo

Các nguồn chính thức nên tra cứu lại theo phiên bản Spring Boot, Spring Cloud Azure và Azure Key Vault được dùng ở dự án:

- [Spring Cloud Azure secret management](https://learn.microsoft.com/en-us/azure/developer/java/spring-framework/secret-management) — PropertySource, secret-keys, refresh interval và precedence.
- [Spring Cloud Azure developer guide](https://learn.microsoft.com/en-us/azure/developer/java/spring-framework/developer-guide-overview) — BOM, starters, supported versions và integration.
- [Load a secret from Key Vault in a Spring Boot application](https://learn.microsoft.com/en-us/azure/developer/java/spring-framework/configure-spring-boot-starter-java-app-with-azure-key-vault) — PropertySource và SecretClient.
- [Azure Key Vault Secrets configuration properties](https://learn.microsoft.com/en-us/azure/developer/java/spring-framework/configuration-properties-azure-key-vault-secrets) — endpoint, credential, retry, refresh và logging.
- [Spring Cloud Azure configuration reference](https://learn.microsoft.com/en-us/azure/developer/java/spring-framework/configuration) — các cấu hình global/per-service.
- [Azure Identity library for Java](https://learn.microsoft.com/en-us/azure/developer/java/sdk/authentication/overview) — DefaultAzureCredential và managed identity.
- [Azure Key Vault Secrets Java SDK](https://learn.microsoft.com/en-us/java/api/overview/azure/security-keyvault-secrets-readme) — SecretClient và SecretClientBuilder.
- [Azure Key Vault overview](https://learn.microsoft.com/en-us/azure/key-vault/general/overview) — vault, keys, secrets, certificates.
- [Azure Key Vault RBAC guide](https://learn.microsoft.com/en-us/azure/key-vault/general/rbac-guide) — Key Vault Secrets User/Officer/Administrator.
- [Azure Key Vault security](https://learn.microsoft.com/en-us/azure/key-vault/general/security-features) — encryption, network và permission concepts.
- [Azure Key Vault Private Link](https://learn.microsoft.com/en-us/azure/key-vault/general/private-link-service) — private endpoint, DNS và vault connectivity.
- [Key Vault private link diagnostics](https://learn.microsoft.com/en-us/azure/key-vault/general/private-link-diagnostics) — DNS/Private Endpoint troubleshooting.
- [Azure Key Vault soft-delete and purge protection](https://learn.microsoft.com/en-us/azure/key-vault/general/soft-delete-overview) — deletion recovery.
- [Key Vault event notifications](https://learn.microsoft.com/en-us/azure/key-vault/general/event-grid-overview) — near expiry/new version events và automation.
- [Key Vault references for App Service](https://learn.microsoft.com/en-us/azure/app-service/app-service-key-vault-references) — platform secret injection.
- [AKS Azure Key Vault Secrets Store CSI Driver](https://learn.microsoft.com/en-us/azure/aks/csi-secrets-store-driver) — Pod mounts/rotation.
- [AKS Microsoft Entra Workload ID](https://learn.microsoft.com/en-us/azure/aks/workload-identity-overview) — federated workload identity.
- [Azure Key Vault monitoring](https://learn.microsoft.com/en-us/azure/key-vault/general/monitor-key-vault) — metrics, diagnostic settings và audit.
- [Azure Key Vault pricing](https://azure.microsoft.com/en-us/pricing/details/key-vault/) — pricing/transaction charges theo dịch vụ.
- [Azure Cost Management](https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/) — budgets, attribution và chi phí.

**Kết luận:** quản lý secret cho Spring Boot bằng Azure Key Vault là một thiết kế **identity, cấu hình, mạng, vận hành và vòng đời**, không phải chỉ thay mật khẩu bằng một lệnh GET. Spring Cloud Azure **PropertySource** giúp nạp secrets từ sớm để bind vào Spring Environment; **SecretClient** phù hợp khi cần đọc version/metadata theo nhu cầu; **App Service references/AKS CSI** là các phương án platform khác nhau. Hệ thống an toàn cần managed identity hoặc workload identity, quyền **Key Vault Secrets User** tối thiểu, phân tách vault theo môi trường, tránh lộ value trong logs/Actuator, hiểu rõ refresh khác bean rebind, có rotation với canary/overlap và downstream cutover, private networking/TLS đúng, retries/caching vừa đủ, giám sát expiry/429/403, kiểm thử thất bại và runbook khôi phục. Khi có thể, hãy loại bỏ password bằng **Entra passwordless authentication** thay vì tạo thêm secret lâu dài.

