# Truy cập Key Vault bằng Azure SDK for Java

Một ứng dụng Java chạy trên Azure App Service cần gọi API thanh toán bằng một khóa bí mật. Trong giai đoạn phát triển, lập trình viên thường đặt khóa trong file cấu hình, biến môi trường hoặc source code. Nhưng khi ứng dụng triển khai qua nhiều môi trường, cần xoay vòng khóa, kiểm toán truy cập và ngăn nhân viên/địch thủ vô tình lấy được khóa, cách làm đó nhanh chóng bộc lộ rủi ro.

**Azure Key Vault** là dịch vụ Azure được quản lý để bảo vệ và kiểm soát truy cập tới **secrets, cryptographic keys và certificates**. **Azure SDK for Java** cho phép ứng dụng truy cập dữ liệu trong vault bằng các clients chuyên biệt và xác thực qua **Microsoft Entra ID**. Thay vì hard-code một bí mật hoặc phát tán access key, ứng dụng thường dùng **managed identity** để gọi Key Vault và chỉ nhận giá trị khi thực sự cần.

Bài học thuộc chương **Azure SDK cho Java** của module **CLOUD_PROVIDERS_AZURE**. Đây là một phần trong lộ trình khám phá hệ sinh thái Microsoft Azure từ subscription, resource group và Entra ID đến mạng ảo, dịch vụ tính toán, lưu trữ và dữ liệu. Nội dung tập trung vào việc **triển khai, giám sát, bảo vệ và kiểm soát chi phí** của kiến trúc ứng dụng Java trên Azure.

Trọng tâm là **Azure Key Vault Secrets** và thư viện **azure-security-keyvault-secrets**, kết hợp **azure-identity**. Key Vault Keys/Certificates được so sánh để biết khi nào cần chuyển sang client khác; bài không nhầm việc đọc secret với thao tác ký số bằng khóa bất đối xứng.

> **Nguyên tắc bảo mật:** Key Vault giảm nhu cầu phân phát secret và bổ sung authentication, authorization, auditing. Nó **không** làm một bí mật đã trả về JVM trở nên không thể lộ. Sau khi lấy secret, mã Java vẫn phải hạn chế lifetime, logging, đối tượng có quyền truy cập và cách sử dụng nó.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **vault, secret, secret name, secret version, secret identifier và properties**.
2. Nhận diện sự khác biệt giữa **Secrets, Keys, Certificates** và Managed HSM.
3. Giải thích Azure Key Vault **control plane** so với **data plane**, Azure RBAC và access policy.
4. Chọn **DefaultAzureCredential**, **ManagedIdentityCredential** và workload identity trong bối cảnh phù hợp.
5. Xác định role **Key Vault Secrets User**, **Key Vault Secrets Officer**, **Key Vault Reader** và giới hạn từng quyền.
6. Tạo một Key Vault lab bằng Azure CLI, gán quyền đọc cho identity cụ thể và kiểm tra URL.
7. Cấu hình Maven cho **azure-security-keyvault-secrets** cùng **azure-identity**.
8. Viết ứng dụng Java hoàn chỉnh để **đọc secret**, xử lý lỗi và tuyệt đối không ghi log giá trị.
9. Thực hành tạo version mới, lấy secret theo version và đọc metadata bằng Java SDK.
10. Thiết kế rotation, cache, refresh, startup failure và khả năng phục hồi khi vault tạm gián đoạn.
11. Giải thích firewall, Private Endpoint, private DNS và các lỗi **401, 403, 404, 429**.
12. So sánh Java SDK với **Key Vault references** trong App Service/Functions và cách tích hợp Spring.
13. Thiết lập monitoring, diagnostic logs, least privilege, CI/CD, testing, incident response và FinOps.
14. Đánh giá kiến trúc production trước khi cho phép Java workload dùng secrets thật.

## 2. Tình huống xuyên suốt: Java Orders API cần API key

Giả sử dịch vụ **Orders API** chạy trên Azure App Service hoặc AKS. Khi xử lý đơn hàng, nó cần gọi dịch vụ đối tác thông qua một API key.

Yêu cầu:

- **Không commit** API key vào Git, JAR, Dockerfile, image layer, Helm values hoặc file properties không được bảo vệ.
- **Không** gửi key xuống trình duyệt.
- Java workload có danh tính riêng được Azure xác thực.
- Mỗi environment dùng Key Vault hoặc secret scope được quản lý đúng.
- Chỉ Orders API được đọc secret mà nó cần.
- Có quyền xoay vòng key và rollback khi secret version mới không hoạt động.
- Secret có thể được đổi mà không phải xây lại binary.
- Lỗi vault hoặc hết hạn key được phát hiện sớm và có runbook.

Kiến trúc mẫu:

~~~mermaid
flowchart LR
    DEV["Developer local<br/>az login"] --> CREDS["Azure Identity SDK<br/>TokenCredential"]
    APP["Orders API<br/>App Service / AKS"] --> CREDS
    ID["Microsoft Entra ID"] --> CREDS
    CREDS --> SDK["SecretClient<br/>azure-security-keyvault-secrets"]
    SDK --> VAULT["Azure Key Vault<br/>orders-payment-api-key"]
    VAULT --> SDK
    SDK --> APP
    APP --> PARTNER["Partner payment API"]
    AUDIT["Azure Monitor<br/>Key Vault diagnostics"] -. "traces/metrics" .-> VAULT
~~~

**Vòng đời xử lý điển hình:**

1. Ứng dụng có managed identity hoặc một phương thức xác thực Entra hợp lệ.
2. Azure Identity SDK lấy **access token** cho Key Vault.
3. SecretClient gọi **data-plane HTTPS endpoint** của vault.
4. Key Vault xác nhận token, quyền truy cập và network rules.
5. Vault trả secret value và metadata cho caller được phép.
6. Ứng dụng dùng value trong kết nối tới đối tác, **không log, không trả trong response**.
7. Khi secret được xoay vòng, ứng dụng tải lại theo cơ chế đã thiết kế.

Một token Entra để gọi vault **không phải** bản thân secret thanh toán. Không nhầm token truy cập vault, secret value, API key của đối tác và tài khoản Azure quản trị vault.

## 3. Key Vault quản lý những loại đối tượng gì?

| Loại | Mục đích | Java client thường dùng | Ví dụ |
|---|---|---|---|
| **Secret** | Lưu giá trị bí mật và metadata phiên bản | **SecretClient** | API key, mật khẩu kết nối, token của bên thứ ba |
| **Key** | Khóa mật mã để ký/xác minh, mã hóa/giải mã hoặc wrap/unwrap theo quyền và loại khóa | **KeyClient**, **CryptographyClient** | RSA/EC key, key-encryption key |
| **Certificate** | Quản lý vòng đời certificate, policy và các phần liên quan tùy certificate type | **CertificateClient** | TLS certificate của dịch vụ |
| **Managed HSM** | Dịch vụ chuyên biệt quản lý khóa trong HSM theo mô hình quyền/tính năng riêng | Các client được dịch vụ hỗ trợ | Nhu cầu mật mã và compliance đặc thù |

### 3.1. Secret không giống Key

Một **Secret** có giá trị trả trực tiếp về ứng dụng khi được phép. Một **Key** có thể cung cấp các phép toán mật mã mà không phải xuất private key khỏi dịch vụ, tùy loại khóa và yêu cầu bảo vệ.

**Không lưu private key không được phép xuất** dưới dạng Key Vault Secret rồi nghĩ rằng nó có cùng bảo đảm HSM như Key Vault Keys. Nếu nghiệp vụ yêu cầu ký số bằng HSM-backed key, dùng CryptographyClient và key policy phù hợp.

### 3.2. Secret thường chứa gì?

- API key của SaaS/đối tác.
- Password của hệ thống bên ngoài chưa hỗ trợ managed identity.
- Shared secret dùng xác minh một webhook.
- Token signing secret, nếu kiến trúc buộc phải dùng shared symmetric key.
- Connection string chứa mật khẩu, khi không thể chuyển sang identity-based authentication.

Tuy nhiên, **không phải credential nào cũng nên trở thành secret**. Khi Azure SQL, Storage, Service Bus hoặc dịch vụ khác hỗ trợ **Microsoft Entra/managed identity**, thường nên dùng cơ chế đó thay vì tiếp tục lưu account key trong Key Vault.

### 3.3. Key Vault không phải một config database thông thường

Đừng đặt hàng nghìn cờ tính năng công khai, localized strings hoặc trạng thái phiên người dùng vào Key Vault chỉ để “đỡ phải có database”. Với non-secret configuration, xem **Azure App Configuration**, application configuration service hoặc cơ chế triển khai phù hợp.

Dùng Key Vault khi có **giá trị cần bảo vệ**, yêu cầu cấp quyền và vòng đời bí mật. Mỗi cuộc gọi vault có latency, quota và khả năng phát sinh phí.

## 4. Cấu trúc vault, name, version và identifier

~~~text
Azure subscription
└── Resource group
    └── Key Vault: kv-orders-prod-example
        ├── Secrets
        │   ├── orders-payment-api-key
        │   │   ├── version aaaaa...
        │   │   └── version bbbbb...
        │   ├── legacy-database-password
        │   └── external-webhook-signing-key
        ├── Keys
        └── Certificates
~~~

### 4.1. Vault URI

Một Key Vault thường có data-plane URL:

~~~text
https://<vault-name>.vault.azure.net/
~~~

Đây là **vault URI**, chưa phải URL cụ thể của một secret.

### 4.2. Secret name

Secret có **name** như:

~~~text
orders-payment-api-key
~~~

Tên phải tuân theo quy định ký tự/độ dài của Key Vault và nên ổn định. Ví dụ những tên có dấu cách hoặc chứa dấu phân cấp không đúng có thể không hợp lệ. Không đặt username/PII vào tên secret chỉ vì tiện debug.

### 4.3. Secret version

Khi đặt một giá trị mới cho **cùng secret name**, Key Vault thường tạo **một version mới**. Các phiên bản là đối tượng quan trọng cho rotation, kiểm toán và rollback.

~~~text
Secret name: orders-payment-api-key

Version A: DEMO_KEY_V1
Version B: DEMO_KEY_V2  ← latest enabled version theo trạng thái dịch vụ
~~~

Đây là mô hình; trong production không hiển thị giá trị thật theo cách này.

### 4.4. Secret identifier

Secret ID là URI:

~~~text
https://kv-orders-prod-example.vault.azure.net/secrets/orders-payment-api-key/<version>
~~~

Một **versionless URI** có dạng:

~~~text
https://kv-orders-prod-example.vault.azure.net/secrets/orders-payment-api-key
~~~

Dùng **versionless lookup** thường giúp ứng dụng nhận version mới sau khi refresh. Dùng **version-pinned** khi cần khả năng tái lập hoặc rollout/rollback có kiểm soát. Dù dùng versionless, SDK hoặc ứng dụng có thể có cache; không mặc định nó đổi ngay trong cùng một HTTP request.

### 4.5. Secret properties

Mỗi version có metadata tùy khả năng hỗ trợ:

- Name, ID và version.
- Enabled/disabled.
- CreatedOn, UpdatedOn.
- ExpiresOn, NotBefore.
- ContentType.
- Tags.
- Recovery/deletion metadata trong các thao tác phù hợp.

**SecretProperties không phải Secret value**. Metadata có thể không nhạy cảm như value nhưng vẫn có thể tiết lộ tên hệ thống hoặc cách đặt phiên bản. Chỉ log các trường cần thiết.

## 5. Kiến trúc bảo mật: ba lớp cần phân biệt

Một lời gọi Java getSecret có thể thất bại ở ba lớp hoàn toàn khác nhau.

~~~mermaid
flowchart TD
    APP["Java workload"] --> AUTH["1. Microsoft Entra ID<br/>TokenCredential"]
    AUTH --> NET["2. Network access<br/>firewall / Private Endpoint / DNS"]
    NET --> RBAC["3. Key Vault data-plane authorization<br/>RBAC hoặc access policies"]
    RBAC --> SECRET["Get secret value"]
~~~

**Lớp 1 – Authentication:** Java chứng minh danh tính qua Entra ID, nhận token có audience/scope phù hợp.

**Lớp 2 – Network:** vault có thể từ chối public network, giới hạn IP/VNet hoặc yêu cầu Private Endpoint và private DNS.

**Lớp 3 – Data-plane authorization:** identity phải có quyền đọc giá trị secret theo mô hình được cấu hình trong vault.

Có token đúng nhưng **không có Secret Get permission** → lỗi authorization. Có role đúng nhưng DNS không đi qua private endpoint → timeout/network error. Một số network denials cũng có thể biểu hiện thành HTTP 403 với thông tin riêng; đọc error code và request ID.

### 5.1. Control plane và data plane

| Plane | Nhiệm vụ | Ví dụ |
|---|---|---|
| **Control plane (Azure Resource Manager)** | Tạo vault, thay network, backup settings, role assignments theo quyền được cấp | Azure Portal, ARM/Bicep, az keyvault create |
| **Data plane (Key Vault endpoint)** | Get/set/list/delete/rotate secret theo quyền dữ liệu | Java SecretClient, az keyvault secret show |
| **Ứng dụng đối tác** | Dùng secret để gọi dịch vụ nghiệp vụ | HTTP Authorization header tới partner API |

**Azure Contributor** ở resource group không tự đồng nghĩa với quyền lấy giá trị secrets. Tương tự, **Key Vault Reader** không đồng nghĩa đọc được secret value.

### 5.2. Azure RBAC và vault access policies

Key Vault có những mô hình authorization khác nhau tùy cấu hình:

- **Azure RBAC permission model:** dùng Azure role assignments tại scope vault hoặc resource phù hợp. Là hướng thường được ưu tiên cho quản trị phân quyền hiện đại.
- **Vault access policy model:** vault cấp data-plane permissions qua access policies. Dùng khi tổ chức hoặc ứng dụng cũ yêu cầu và hiểu rủi ro/chiến lược migration.

**Không trộn hai mô hình và cho rằng cả hai đồng thời tự cấp quyền.** Phải kiểm tra vault đang chọn permission model nào.

### 5.3. Một số roles phổ biến

| Role | Chức năng khái quát | Khi dùng |
|---|---|---|
| **Key Vault Secrets User** | Đọc nội dung secrets | Java workload chỉ cần get secret |
| **Key Vault Secrets Officer** | Quản lý secrets (không quản lý phân quyền) | Rotation service hoặc operator được duyệt |
| **Key Vault Reader** | Đọc metadata không đọc secret values | Audit/inventory theo nhu cầu |
| **Key Vault Administrator** | Quyền data plane rộng trên vault | Quản trị đặc biệt, hạn chế |
| **Key Vault Crypto User** | Các thao tác mật mã với keys theo quyền | Ứng dụng dùng KeyClient/CryptographyClient |
| **Key Vault Certificates Officer** | Quản lý certificate lifecycle theo role | Nhóm certificate management |

Role names và data actions có thể được cập nhật; kiểm tra role definition thực và cấp **scope nhỏ nhất khả thi**.

### 5.4. Principle of least privilege

Một Orders API chỉ cần đọc **orders-payment-api-key** không nên có quyền tạo/xóa mọi secret. Nếu tổ chức cần hạn quyền đến từng secret theo RBAC scope hoặc access policy phù hợp, phải kiểm tra tính năng/scope được hỗ trợ và chi phí quản trị; đừng mặc định data plane role ở vault scope tự tách mỗi secret.

Rotation worker thường cần quyền **set** và **get** riêng với read-only application. Tách identities giúp giảm blast radius.

## 6. Microsoft Entra ID và TokenCredential

### 6.1. DefaultAzureCredential

Trong Java, **azure-identity** cung cấp các triển khai **TokenCredential**. **DefaultAzureCredential** thử các credential sources được hỗ trợ theo cấu hình/môi trường, giúp một code path dùng được ở local và Azure.

Ví dụ:

~~~java
TokenCredential credential =
    new DefaultAzureCredentialBuilder().build();
~~~

Các nguồn danh tính có thể bao gồm environment credentials, managed/workload identity và developer tooling như Azure CLI, tùy version và environment. **Không giả định credential chain và thứ tự là bất biến**, nhất là khi có nhiều accounts hoặc environment variables.

### 6.2. Local development

Ở máy phát triển:

~~~bash
az login
az account set --subscription "<lab-subscription-id>"
az account show --output table
~~~

Local identity lấy từ Azure CLI chỉ có thể đọc secret nếu **user identity đó có data-plane quyền** trên vault. Chạy az login thành công **không tự có quyền đọc Key Vault**.

Khi trong environment đã có biến credentials khác, DefaultAzureCredential có thể chọn một identity khác account đang hiển thị trong CLI. Khi 403, kiểm tra principal thực của access token và credential source trước khi đổi RBAC mù quáng.

### 6.3. Managed identity trong Azure

Với **system-assigned managed identity** của App Service/Function/VM:

1. Bật identity trên workload.
2. Gán identity role **Key Vault Secrets User** theo scope phù hợp.
3. App dùng DefaultAzureCredential hoặc ManagedIdentityCredential.
4. Không dùng client secret để chứng minh identity.
5. Kiểm tra network/TLS và RBAC propagation.

Với **user-assigned managed identity**, phải chỉ rõ client ID khi environment có nhiều identities:

~~~java
import com.azure.core.credential.TokenCredential;
import com.azure.identity.ManagedIdentityCredentialBuilder;

String clientId = System.getenv("AZURE_CLIENT_ID");
if (clientId == null || clientId.isBlank()) {
    throw new IllegalArgumentException("Missing AZURE_CLIENT_ID");
}

TokenCredential credential =
    new ManagedIdentityCredentialBuilder()
        .clientId(clientId)
        .build();
~~~

**Client ID không phải secret**, nhưng vẫn phải quản lý chính xác theo environment. Không được nhầm **client ID** với principal object ID dùng cho role assignment.

### 6.4. AKS workload identity

Trong AKS, có thể dùng **Microsoft Entra Workload ID** với Kubernetes ServiceAccount và federated identity credential theo cấu hình cluster/add-on, thay vì mount shared vault credentials trong pod.

- TokenCredential được cấu hình theo các environment variables và projected tokens của workload identity.
- Role Key Vault được gán cho Entra principal tương ứng.
- Pod ServiceAccount/namespace/federated subject phải khớp.
- Không tự cho rằng mọi pod trong cluster được đọc mọi secrets.
- Điều kiện mạng và outbound DNS tới Key Vault vẫn phải thỏa.

Không sao chép Kubernetes Secret chứa account key để “làm workload identity” nếu mục tiêu là loại bỏ static credentials.

### 6.5. Service principal trong CI/CD

CI/CD có thể dùng **federated identity/OIDC** khi hệ thống hỗ trợ; đây thường là phương án tốt hơn client secret sống lâu. Nếu buộc dùng service principal credential, phải cấp đúng quyền, lưu secret trong secret store CI, rotation và không đưa vào log/build artifact.

Không dùng identity của developer cá nhân để triển khai production pipeline.

## 7. Luồng Java SDK gọi Key Vault

~~~mermaid
sequenceDiagram
    participant APP as Java Orders API
    participant ID as Azure Identity SDK
    participant EN as Microsoft Entra ID
    participant KV as Azure Key Vault
    participant EXT as Partner API
    APP->>ID: Build TokenCredential
    ID->>EN: Acquire access token
    EN-->>ID: Token for Key Vault
    APP->>KV: GET secret via SecretClient + token
    KV->>KV: Check network & data-plane permissions
    KV-->>APP: Secret value + properties
    APP->>EXT: Call API using secret in secure header
    EXT-->>APP: Result
~~~

**Azure SDK** xử lý phần HTTP/auth/retry theo policy của client, nhưng người viết ứng dụng vẫn phải:

- Bảo vệ secret value trong memory.
- Không log/serialize secret.
- Không tái tạo client cho mỗi HTTP request.
- Không retry vô hạn với 403 hoặc 404.
- Có timeout và hành vi degrade/fail-closed phù hợp.
- Quyết định khi nào refresh cache/rotation.
- Truy vết lỗi bằng status, request ID và correlation mà không lộ secret.

## 8. Cấu trúc Maven và Azure SDK modules

Với **Java 17** và Maven, hai dependency cốt lõi:

| Maven artifact | Vai trò |
|---|---|
| **com.azure:azure-security-keyvault-secrets** | SecretClient, KeyVaultSecret, SecretProperties |
| **com.azure:azure-identity** | DefaultAzureCredential, ManagedIdentityCredential |
| **com.azure:azure-core** | TokenCredential và HTTP/core types (thường là transitive dependency) |

**Không nhầm** với:

- **azure-security-keyvault-keys**: thao tác keys.
- **azure-security-keyvault-certificates**: certificates.
- SDK Azure Storage hoặc Azure App Configuration.

### 8.1. pom.xml mẫu

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>com.example</groupId>
  <artifactId>keyvault-java-demo</artifactId>
  <version>1.0.0-SNAPSHOT</version>

  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>

  <dependencies>
    <dependency>
      <groupId>com.azure</groupId>
      <artifactId>azure-security-keyvault-secrets</artifactId>
      <version>4.10.0</version>
    </dependency>
    <dependency>
      <groupId>com.azure</groupId>
      <artifactId>azure-identity</artifactId>
      <version>1.16.0</version>
    </dependency>
  </dependencies>

  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.13.0</version>
        <configuration>
          <release>17</release>
        </configuration>
      </plugin>
      <plugin>
        <groupId>org.codehaus.mojo</groupId>
        <artifactId>exec-maven-plugin</artifactId>
        <version>3.5.0</version>
      </plugin>
    </plugins>
  </build>
</project>
~~~

Hai versions được đặt **làm ví dụ về major version** cho SDK v4/v1 và phải được xác minh, cập nhật theo dependency policy/CVE scans của dự án trước khi build. Nếu tổ chức dùng **Azure SDK BOM**, nên quản lý version tập trung thay vì pin rời rạc. Không đồng nhất “phiên bản SDK trong ví dụ” với “phiên bản mới nhất”.

### 8.2. Build và chạy

~~~bash
# Cấu trúc project:
# src/main/java/com/example/keyvault/ReadSecretDemo.java

mvn -q -DskipTests compile
mvn -q exec:java -Dexec.mainClass=com.example.keyvault.ReadSecretDemo
~~~

Tại local, phải đăng nhập Entra, có data-plane role và đặt **KEY_VAULT_URL** cùng tên secret. Lệnh trên chưa hoạt động nếu vault/secret chưa được chuẩn bị hoặc dependency chưa resolve.

## 9. Thiết kế tên và lifecycle của secrets

Một convention minh họa:

~~~text
Vault per environment:
    kv-orders-dev-example
    kv-orders-test-example
    kv-orders-prod-example

Secret names:
    orders-payment-api-key
    orders-webhook-signing-secret
    legacy-db-password
~~~

Không có quy tắc rằng bắt buộc mỗi microservice một vault; cân nhắc ownership, data classification, network, RBAC boundaries, quotas, rotation và cost. Không đặt tất cả secrets của hàng trăm ứng dụng nhạy cảm vào cùng vault với cùng một reader identity.

### 9.1. Versioned secrets

Quy trình rotation thường:

1. Tạo credential mới ở hệ thống đối tác.
2. Ghi **secret version mới** trong Key Vault.
3. Xác minh quyền đọc và cập nhật ứng dụng theo rollout.
4. Chuyển traffic hoặc chờ cache refresh có kiểm soát.
5. Theo dõi lỗi authentication/HTTP 401 từ đối tác.
6. Thu hồi credential cũ sau thời gian chuyển tiếp.
7. Có rollback nếu đối tác cho phép và policy chấp nhận.
8. Ghi audit, owner, date và next-rotation time.

**Key Vault cập nhật secret không tự sửa credential ở hệ thống đối tác.** Hai bên phải được điều phối cùng workflow.

### 9.2. Disabled, not-before và expiration

- Secret **disabled** không dùng được theo điều kiện dịch vụ.
- **NotBefore** kiểm soát thời điểm version có hiệu lực.
- **ExpiresOn** nêu thời điểm hết hạn.
- SDK có thể nhận lỗi nếu ứng dụng cố đọc value không còn được phép dùng.

Không coi ExpiresOn tự động xoay vòng hoặc xóa mọi bản sao secret ra khỏi memory/các thiết bị. Ứng dụng phải có refresh/revocation strategy.

### 9.3. Secret version pinning

Version pinning giúp rollout cố định nhưng có rủi ro: sau khi rotation, application vẫn sử dụng version cũ. Versionless lookup giúp nhận version mới sau refresh nhưng cần theo dõi compatibility và tránh surprise change giữa những requests của một giao dịch.

Quyết định chính sách theo từng loại secret: API key, signing secret, database password, certificate chain có yêu cầu khác nhau.

## 10. Lab Azure CLI: tạo vault và phân quyền đúng

Các lệnh dưới chỉ là **hướng dẫn**, không có tài nguyên Azure nào được tạo khi soạn bài. Key Vault có thể tính phí theo số thao tác và những tính năng/tier riêng. Chỉ chạy trong subscription lab có budget, permission và tên tài nguyên đã được phê duyệt.

### 10.1. Điều kiện ban đầu

- Azure CLI mới phù hợp với tổ chức.
- Subscription lab và quyền tạo resource group/vault.
- Quyền tạo Azure role assignment do **Owner**, **User Access Administrator**, **Role Based Access Control Administrator** hoặc role phù hợp cho phép.
- Không trùng tên vault production; tên vault có phạm vi duy nhất theo quy tắc Key Vault.
- Không dùng secret thật trong tài liệu hay terminal transcript.
- Biết vault dùng RBAC hay access policy; ví dụ này **chọn RBAC**.

### 10.2. Tạo resource group và vault RBAC

~~~bash
az login
az account set --subscription "<lab-subscription-id>"
az account show --output table

RG="rg-keyvault-java-lab"
LOCATION="southeastasia"
VAULT="<globally-unique-vault-name>"

az group create \
  --name "$RG" \
  --location "$LOCATION"

az keyvault create \
  --name "$VAULT" \
  --resource-group "$RG" \
  --location "$LOCATION" \
  --enable-rbac-authorization true
~~~

**Lưu ý:** không chạy lệnh create trên tên vault đã thuộc tổ chức khác; nếu vault tồn tại thì phải kiểm tra ownership. Soft-delete mặc định và purge protection/retention phải được xác nhận theo cấu hình và policy hiện hành, đặc biệt trước production.

### 10.3. Kiểm tra vault không làm lộ secret

~~~bash
az keyvault show \
  --name "$VAULT" \
  --query "{id:id,name:name,vaultUri:properties.vaultUri,rbac:properties.enableRbacAuthorization}" \
  --output json

VAULT_ID=$(az keyvault show \
  --name "$VAULT" \
  --query id \
  --output tsv)
~~~

Một ví dụ **vault URI**:

~~~text
https://<vault-name>.vault.azure.net/
~~~

Nếu vault dùng Private Endpoint và bạn ở ngoài mạng cho phép, các lệnh data-plane có thể không hoạt động dù lệnh quản lý ARM vẫn hoạt động.

### 10.4. Gán role cho developer lab

**Chỉ người quản trị được phép** mới chạy lệnh role assignment. Người tạo vault chưa chắc đã có data-plane role đọc secrets.

~~~bash
MY_OBJECT_ID=$(az ad signed-in-user show \
  --query id \
  --output tsv)

az role assignment create \
  --assignee-object-id "$MY_OBJECT_ID" \
  --assignee-principal-type User \
  --role "Key Vault Secrets Officer" \
  --scope "$VAULT_ID"
~~~

**Key Vault Secrets Officer** được dùng ở đây chỉ để developer lab có thể **tạo secret giả** và kiểm chứng quản lý phiên bản. Trong production, developer không nên được cấp role rộng trên vault chứa secret thật chỉ để chạy một sample GET; có thể yêu cầu operator tạo sẵn secret và cấp developer **Key Vault Secrets User** ở scope phù hợp.

### 10.5. Tạo một secret mẫu không có giá trị bảo mật

~~~bash
az keyvault secret set \
  --vault-name "$VAULT" \
  --name "orders-payment-api-key" \
  --value "DEMO_ONLY_NOT_A_REAL_SECRET" \
  --query id \
  --output tsv
~~~

**Cảnh báo:** đối số --value trong command line có thể bị ghi vào shell history/process list; chỉ dùng **chuỗi demo công khai không phải bí mật**. Với production cần cơ chế provisioning secrets được phê duyệt để hạn chế lộ trên logs, history, pipelines hoặc file tạm. Không copy credential thật vào câu lệnh minh họa.

### 10.6. Xem metadata, không hiển thị value

~~~bash
az keyvault secret show \
  --vault-name "$VAULT" \
  --name "orders-payment-api-key" \
  --query "{id:id,enabled:attributes.enabled,expires:attributes.expires}" \
  --output json

az keyvault secret list \
  --vault-name "$VAULT" \
  --query "[].{name:name,id:id}" \
  --output table
~~~

Lưu ý các CLI data-plane commands có thể **truy xuất dữ liệu nội bộ trước khi lọc output**. Hạn chế logging/command history và không để người chưa có quyền chạy trên vault production.

### 10.7. Gán quyền cho managed identity của ứng dụng

Khi App Service hoặc VM đã có managed identity, người quản trị lấy **principal object ID** từ identity thực rồi gán role đọc:

~~~bash
APP_PRINCIPAL_ID="<managed-identity-principal-object-id>"

az role assignment create \
  --assignee-object-id "$APP_PRINCIPAL_ID" \
  --assignee-principal-type ServicePrincipal \
  --role "Key Vault Secrets User" \
  --scope "$VAULT_ID"
~~~

Đây là role ở **vault scope** cho dễ hiểu. Nếu security policy yêu cầu scope chặt hơn, dùng ranh giới tài nguyên và RBAC scope tương ứng theo tính năng được hỗ trợ. Không chạy với placeholder. Cần có quyền role assignment; **Contributor đơn thuần** chưa chắc được cấp phép.

**Đừng nhầm:**

- **Application (client) ID**: dùng chỉ định user-assigned identity.
- **Principal object ID**: nhận diện service principal/managed identity để RBAC assignment.
- **Subscription ID**: scope Azure resource.
- **Tenant ID**: Entra directory context.
- **Secret ID**: URL của một secret version.

### 10.8. Role propagation

Sau khi tạo role assignment, quyền data plane có thể cần thời gian để áp dụng. Nếu getSecret trả 403 ngay sau cấp quyền, kiểm tra identity/scope/permission model, đợi sự lan truyền trong giới hạn runbook rồi thử lại. Không khắc phục bằng cách cấp Azure Owner hoặc tắt network policy.

## 11. Java: ví dụ đọc secret hoàn chỉnh

Đặt file **src/main/java/com/example/keyvault/ReadSecretDemo.java**.

~~~java
package com.example.keyvault;

import com.azure.core.credential.TokenCredential;
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.security.keyvault.secrets.SecretClient;
import com.azure.security.keyvault.secrets.SecretClientBuilder;
import com.azure.security.keyvault.secrets.models.KeyVaultSecret;

public final class ReadSecretDemo {

    private ReadSecretDemo() {}

    public static void main(String[] args) {
        String vaultUrl = requiredEnv("KEY_VAULT_URL");
        String secretName = requiredEnv("KEY_VAULT_SECRET_NAME");

        TokenCredential credential =
            new DefaultAzureCredentialBuilder().build();

        SecretClient secretClient =
            new SecretClientBuilder()
                .vaultUrl(vaultUrl)
                .credential(credential)
                .buildClient();

        KeyVaultSecret secret = secretClient.getSecret(secretName);
        String secretValue = secret.getValue();

        if (secretValue == null || secretValue.isBlank()) {
            throw new IllegalStateException(
                "Secret was empty or unavailable");
        }

        // Trong ứng dụng thực, đưa secretValue cho component
        // dùng credential ở server-side, không log/in ra console.
        // Ví dụ chỉ xác minh truy xuất thành công.
        System.out.println(
            "Key Vault secret retrieved successfully; value omitted.");
    }

    private static String requiredEnv(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                "Required environment variable missing: " + name);
        }
        return value;
    }
}
~~~

### 11.1. Cấu hình môi trường

Ví dụ cho terminal phát triển với dữ liệu demo:

~~~bash
export KEY_VAULT_URL="https://<vault-name>.vault.azure.net/"
export KEY_VAULT_SECRET_NAME="orders-payment-api-key"

az login
mvn -q compile
mvn -q exec:java -Dexec.mainClass=com.example.keyvault.ReadSecretDemo
~~~

Đối với Windows PowerShell, cách khai báo environment variables là:

~~~powershell
$env:KEY_VAULT_URL = "https://<vault-name>.vault.azure.net/"
$env:KEY_VAULT_SECRET_NAME = "orders-payment-api-key"
~~~

Đây là **hai biến không nhạy cảm** chứa endpoint/name. **Không** đặt giá trị secret trong các biến trên; chương trình sẽ lấy giá trị qua Azure SDK.

### 11.2. Vì sao không in secret?

Những câu như sau nguy hiểm:

~~~java
// KHÔNG làm ở production:
System.out.println(secret.getValue());
logger.info("Payment key = {}", secret.getValue());
throw new RuntimeException("Invalid key: " + secret.getValue());
~~~

Console logs, APM traces, exception messages, crash dumps, shell logs hoặc build output có thể tồn tại lâu và được nhiều người đọc. Không lưu secret vào telemetry để “dễ debug”.

### 11.3. Có thể xóa secret String khỏi RAM không?

Azure SDK trả giá trị secret ở dạng **Java String**, vốn bất biến. Java garbage collector quyết định khi nào thu hồi đối tượng; bạn **không thể bảo đảm zeroization** chỉ bằng đặt biến về null. Chuyển String thành char[] cũng không xóa bản String trước đó. Biện pháp thực tế là:

- Giảm số bản sao và phạm vi sống của secret.
- Không giữ secret trong static global/debug state nếu không cần.
- Không serialize ra JSON/HTTP response.
- Hạn chế diagnostics/coredumps và quyền truy cập memory.
- Dùng managed identity để **khỏi cần secret** khi có thể.

## 12. Java SecretClient cho version, metadata và list

### 12.1. Đọc latest và version cụ thể

~~~java
import com.azure.security.keyvault.secrets.SecretClient;
import com.azure.security.keyvault.secrets.models.KeyVaultSecret;

String secretName = "orders-payment-api-key";

KeyVaultSecret latest = secretClient.getSecret(secretName);

// Lấy version khi muốn pin một release cụ thể.
String version = latest.getProperties().getVersion();
KeyVaultSecret pinned = secretClient.getSecret(secretName, version);

// KHÔNG in latest.getValue() hoặc pinned.getValue().
// Metadata được dùng để ghi audit theo policy.
System.out.println("Resolved version metadata available: " +
    (version != null));
~~~

Trong đoạn code, **secretClient đã được tạo ở mục 11**. Versionless getSecret(name) giải quyết secret version theo dịch vụ; nó không mang nghĩa “luôn lấy version mới nhất kể cả disabled/not-before/expired mà không có kiểm tra”.

### 12.2. Liệt kê metadata của các secrets

~~~java
import com.azure.security.keyvault.secrets.models.SecretProperties;

for (SecretProperties properties :
        secretClient.listPropertiesOfSecrets()) {

    // Tên secret cũng có thể tiết lộ cấu trúc hệ thống.
    // Chỉ ghi log nếu chính sách cho phép.
    System.out.println("Secret metadata inspected");
}
~~~

Thao tác **listPropertiesOfSecrets** trả metadata chứ không tự trả mọi giá trị secret. Tuy nhiên role chỉ được **get một secret** không nhất thiết được phép **list vault**; không phụ thuộc vào việc list nếu ứng dụng đã biết name.

### 12.3. Liệt kê versions

~~~java
import com.azure.security.keyvault.secrets.models.SecretProperties;

for (SecretProperties props :
        secretClient.listPropertiesOfSecretVersions(
            "orders-payment-api-key")) {

    String version = props.getVersion();
    Boolean enabled = props.isEnabled();

    // Không lấy value của các version chỉ để thống kê.
    recordVersionMetadata(version, enabled);
}
~~~

Hàm **recordVersionMetadata** là hàm minh họa phải do ứng dụng định nghĩa; đoạn này chỉ tập trung vào SDK. Nếu không chắc field/accessor tại phiên bản đang pin, kiểm tra API reference của SecretProperties và dùng getters hiện có.

### 12.4. Paged results

Các list operations của SDK thường trả dạng **PagedIterable/AsyncPagedIterable**, có thể phát sinh nhiều HTTP requests trong lúc lặp. Không chạy inventory trên vault có hàng nghìn secrets trong đường xử lý một HTTP request; cần pagination, rate limit và cơ chế background job.

## 13. Tạo secret version mới bằng Java: chỉ cho operator

**Mã đọc secret** không nên đồng thời tự ghi/rotate secret trong mỗi startup. Chỉ một rotation service/operator được cấp **Key Vault Secrets Officer** theo policy mới được set version.

Ví dụ minh họa trên vault lab:

~~~java
import com.azure.security.keyvault.secrets.SecretClient;
import com.azure.security.keyvault.secrets.models.KeyVaultSecret;

String name = "orders-payment-api-key";
String value = "DEMO_NEW_VERSION_NOT_A_REAL_SECRET";

KeyVaultSecret created = secretClient.setSecret(name, value);

// Chỉ ghi metadata cần thiết, KHÔNG in created.getValue().
String version = created.getProperties().getVersion();
System.out.println("Created demo secret version: " + version);
~~~

**Không bao giờ** nhúng giá trị thật trong source như ví dụ. Ở production, credential mới phải đến từ hệ thống cấp phát an toàn, không từ một literal trong code hoặc file cấu hình không được bảo vệ.

### 13.1. SetSecret tạo một version, không đảm bảo đối tác đã đổi key

Sau khi set:

- Vault có version mới.
- Ứng dụng khác vẫn có thể dùng cache/version cũ.
- Hệ thống đối tác có thể chưa chấp nhận giá trị mới.
- Có thể cần khoảng dual-key overlap nếu đối tác hỗ trợ.
- Rollout phải có health checks, alerts và kế hoạch rollback.

Không đặt expiration tự động và cho rằng điều đó đồng nghĩa rotation hoàn thành.

### 13.2. Cập nhật metadata, không thay value

SecretProperties có các thuộc tính có thể cập nhật theo SDK/tính năng hỗ trợ. Quy trình thông thường:

~~~java
import com.azure.security.keyvault.secrets.models.KeyVaultSecret;
import com.azure.security.keyvault.secrets.models.SecretProperties;
import java.time.OffsetDateTime;

KeyVaultSecret current =
    secretClient.getSecret("orders-payment-api-key");

SecretProperties properties = current.getProperties();
properties.setExpiresOn(
    OffsetDateTime.now().plusMonths(3));

secretClient.updateSecretProperties(properties);
~~~

**Đây là thao tác quản trị**, không chạy trong request handler. Nó cần quyền quản lý secret properties, có thể thay metadata của một version nhưng **không tự đổi value** hoặc thu hồi key ngoài Key Vault. Với critical secrets, ngày hết hạn phải xuất phát từ security policy và rotation calendar chứ không cộng bừa ba tháng.

### 13.3. Đừng dùng secret value làm version ID

Version là định danh do dịch vụ cấp. Không mã hóa nguyên API key trong name/version/tags hoặc URL để truy vết; các trường này có thể xuất hiện trong logs và audit.

## 14. Sync và async clients trong Azure SDK

Azure SDK for Java có:

- **SecretClient** (synchronous): phù hợp đường code blocking, background job hoặc startup initialization.
- **SecretAsyncClient** (asynchronous/reactive): phù hợp ứng dụng đã dùng Reactor/WebFlux và cần non-blocking composition.

Ví dụ tạo async client:

~~~java
import com.azure.security.keyvault.secrets.SecretAsyncClient;
import com.azure.security.keyvault.secrets.SecretClientBuilder;

SecretAsyncClient asyncClient =
    new SecretClientBuilder()
        .vaultUrl(vaultUrl)
        .credential(credential)
        .buildAsyncClient();

// Không block bên trong event-loop của Spring WebFlux.
// Chain Mono để ứng dụng quản lý request lifecycle.
var secretValueMono =
    asyncClient.getSecret("orders-payment-api-key")
        .map(secret -> secret.getValue());
~~~

**Không dùng .block() bừa bãi trong reactive event loop**. Với sync Spring MVC, sync client có thể đơn giản hơn; với high-concurrency reactive app, compose async flow và thiết kế caching/timeouts.

### 14.1. Tái sử dụng client

Nên tái sử dụng SecretClient theo service lifetime và dependency injection, thay vì tạo mới mỗi request, vì SDK quản lý HTTP connections, token acquisition và retry policies. Không tạo một new credential + client trong vòng lặp xử lý hàng nghìn HTTP requests.

### 14.2. Token cache khác secret cache

Azure Identity SDK có cơ chế lấy/refresh Entra token, nhưng **không có nghĩa** nó tự cache giá trị Key Vault secret cho mọi ứng dụng. Nếu cần cache secret value, đó là quyết định riêng về TTL, invalidation, rotation và memory exposure.

## 15. Xử lý lỗi Java đúng lớp

Một lời gọi getSecret có thể thất bại do credentials, network, RBAC hoặc trạng thái secret.

### 15.1. HTTP status thường gặp

| Triệu chứng | Khả năng | Cách xác minh |
|---|---|---|
| **401 Unauthorized** | Access token invalid/expired/audience sai | Credential source, tenant, token scope |
| **403 Forbidden** | Thiếu data-plane role, access policy hoặc network firewall | Vault permission model, principal, firewall/private endpoint |
| **404 Not Found** | Sai secret name/version, disabled/deleted hoặc đường dẫn không tồn tại tùy error code | Vault URL, name, version, Key Vault error details |
| **429 Too Many Requests** | Vượt throttling/quota | Rate metrics, Retry-After, per-vault traffic |
| **5xx/transient** | Dịch vụ hoặc đường truyền gặp sự cố | Azure Service Health, request IDs, retry budget |
| **Timeout/DNS/TLS** | Route, Private DNS, proxy, certificate, firewall | Network tracing, Private Endpoint DNS |
| **PermissionDenied khi set** | Reader role chỉ đọc | Phân quyền Officer/operator, không cấp Owner tùy tiện |
| **Secret expired/disabled** | Lifecycle condition không còn hợp lệ | SecretProperties, rotation runbook |

Không coi mọi 403 là “chưa gán role”; network policy cũng có thể chặn trước khi thao tác data plane.

### 15.2. Bắt lỗi mà không in giá trị secret

~~~java
import com.azure.core.exception.HttpResponseException;
import com.azure.security.keyvault.secrets.models.KeyVaultSecret;

try {
    KeyVaultSecret secret =
        secretClient.getSecret("orders-payment-api-key");

    consumeSecretWithoutLogging(secret.getValue());

} catch (HttpResponseException error) {
    int status = error.getResponse() == null
        ? -1
        : error.getResponse().getStatusCode();

    // Log status và correlation ID qua telemetry sanitization.
    System.err.println("Key Vault access failed, HTTP " + status);
    throw error;
}
~~~

**consumeSecretWithoutLogging** là adapter nghiệp vụ minh họa cần được định nghĩa. Không tự in **error.getMessage()** lên public logs nếu chưa kiểm tra có chứa URI hoặc metadata nhạy cảm. Khi xử lý production cần các exception types đúng SDK, OpenTelemetry và redaction rules.

### 15.3. Retry đúng cách

- 429/503/transport transient: có thể retry theo built-in SDK policy và Retry-After nếu có.
- 401: kiểm tra credential/token/audience thay vì loop.
- 403: kiểm tra identity/role/network; không retry liên tục hàng phút.
- 404: kiểm tra secret name/version/deletion, không tạo secret mới ngầm trong application.
- Expiration/revocation: fail closed hoặc transition theo business security policy.
- Những lỗi cấu hình không thể phục hồi nên fail-fast khi startup nếu ứng dụng không thể vận hành an toàn.

**Không chồng nhiều lớp retry không giới hạn**: retry trong SDK + retry trong Spring + retry từ API gateway có thể khuếch đại tải và Key Vault throttling.

## 16. Cơ chế xác thực khi chạy trên các Azure runtimes

| Runtime | Identity được khuyến nghị | Điểm cần cấu hình |
|---|---|---|
| **App Service** | System-assigned hoặc user-assigned managed identity | Enable identity, RBAC, VNet integration nếu cần |
| **Azure Functions** | Managed identity | Host/app settings và quyền data plane |
| **Azure VM** | Managed identity | Identity endpoint và role assignments |
| **AKS** | Microsoft Entra Workload ID | ServiceAccount, federated credential, role |
| **Container Apps** | Managed identity | Identity config, egress/network |
| **Local dev** | Azure CLI/dev tooling | az login, đúng tenant và lab data role |
| **CI/CD** | Federated identity/OIDC khi hỗ trợ | Scope/issuer/subject, least privilege |

Một container image chạy ở AKS và cùng image chạy local có thể dùng **DefaultAzureCredential** nhưng lấy identity khác nhau. Phải có test kiểm chứng principal thật, không chỉ dựa vào việc code không đổi.

### 16.1. Chỉ định user-assigned identity

Nếu workload có nhiều user-assigned identities, dùng client ID được cấu hình chính xác trong runtime (ví dụ **AZURE_CLIENT_ID** cho credential chain theo khả năng hỗ trợ). Không dùng object ID làm client ID. Nếu dùng ManagedIdentityCredentialBuilder, thiết lập **clientId** như ví dụ mục 6.

### 16.2. Khi nào không dùng DefaultAzureCredential cho production?

DefaultAzureCredential tiện dùng qua môi trường, nhưng chain có thể chọn một source ngoài ý muốn nếu runtime bị cấu hình thêm credentials. Với hệ thống security-sensitive, có thể **ràng buộc credential rõ ràng** theo environment:

- Production: ManagedIdentityCredential hoặc WorkloadIdentityCredential đúng identity.
- Local: AzureCliCredential hoặc developer credential tương ứng.
- Test: fake TokenCredential/injected SecretClient abstraction.

Quyết định dựa trên SDK version và runtime identity platform; không hard-code production principal secrets để “tránh chain”.

## 17. Đọc secret khi startup hay mỗi request?

### 17.1. Tránh getSecret cho mọi HTTP request

Nếu API phục vụ 1.000 req/s và mỗi request tự gọi Key Vault:

~~~text
1.000 app requests/s
× 1 Key Vault GET/request
= 1.000 Key Vault data-plane calls/s
~~~

Đây là ví dụ tải giả định; Key Vault có throttling/latency và chi phí tùy operation/tier. Kiểu thiết kế này tăng rủi ro 429, làm request latency phụ thuộc vault và giảm khả năng chịu outage.

### 17.2. Startup fetch

Ứng dụng đọc secret lúc khởi động:

- Đơn giản, rõ readiness.
- Fail-fast nếu thiếu credential.
- Không thêm network call vào mỗi request.
- Nhưng **không tự refresh** khi secret đổi version.
- Secret value tồn tại lâu trong memory; xem security policy.
- Nếu Key Vault outage lúc scale-out, tất cả instances mới có thể fail startup.

Phù hợp khi rotation điều khiển bằng deployment/restart.

### 17.3. Cache có TTL và refresh

Một phương án:

~~~mermaid
flowchart TD
    CALL["Partner API call"] --> C{"Cached secret usable?"}
    C -->|Có| USE["Use current in-memory value"]
    C -->|Không| KV["Fetch latest version from Key Vault"]
    KV --> VALID["Validate state/version"]
    VALID --> UPDATE["Atomically update cache"]
    UPDATE --> USE
~~~

Chọn TTL theo yêu cầu rotation/latency và threat model. Có thể refresh background trước TTL, dùng jitter để tránh hàng nghìn instances đồng thời gọi vault, và giới hạn retries.

### 17.4. Cách xử lý secret cũ khi vault mất kết nối

Không có chính sách chung:

- Với API key của partner có thể chấp nhận stale vài phút nếu key còn hợp lệ và security policy cho phép.
- Với secret bị nghi lộ/thu hồi hoặc sensitive crypto material, **fail-closed** có thể là yêu cầu bắt buộc.
- Với secret hết hạn, không coi cache stale là hợp lệ chỉ vì server còn giữ String.
- Có thể giữ last-known-good một khoảng rất ngắn theo risk acceptance và báo alert.

**Không tự ý fallback sang hard-coded backup key trong code**.

## 18. Rotation và version pinning trong Java

### 18.1. Quy trình canary rotation

~~~mermaid
flowchart TD
    O["Operator tạo key mới ở partner"] --> SET["Set new Key Vault version"]
    SET --> CANARY["Canary app reads new secret version"]
    CANARY --> TEST{"Partner authentication works?"}
    TEST -->|Không| ROLLBACK["Rollback app reference<br/>giữ key cũ theo policy"]
    TEST -->|Có| ROLL["Roll out versionless refresh<br/>hoặc explicit version"]
    ROLL --> OBS["Monitor partner 401/403, latency"]
    OBS --> REVOKE["Revoke old partner key after overlap"]
~~~

### 18.2. Secret version không phải partner key version

Hai hệ thống có state riêng:

- Key Vault version.
- Credential thực tế tại partner.
- Application cache version.
- Deployment configuration/release version.

Nếu chỉ update Key Vault mà partner chưa tạo key mới, ứng dụng dùng version mới có thể lỗi. Nếu partner thu hồi key cũ trước khi app refresh xong, các instances có thể bị mất kết nối.

### 18.3. Cách kiểm thử

1. Tạo hai demo secret versions.
2. App đọc bằng name (latest) và bằng version cụ thể.
3. Quan sát version ID mà không log value.
4. Simulate refresh TTL hoặc restart.
5. Giả lập partner authentication failed.
6. Rollback app reference có kiểm soát.
7. Giám sát metric retrieval/partner auth.
8. Xóa credential demo ngoài partner khi không còn dùng.

**Không dùng rotation lab để chỉnh secret production hoặc account credentials thật**.

## 19. Key Vault và network: public firewall, Private Endpoint, DNS

### 19.1. URL của vault không đổi khi dùng private endpoint

Ứng dụng vẫn kết nối qua:

~~~text
https://<vault-name>.vault.azure.net/
~~~

Khi cấu hình **Azure Private Endpoint** đúng, DNS của network riêng đưa hostname đến private IP theo chuỗi phân giải do dịch vụ quản lý. Với Key Vault, private DNS zone thường là:

~~~text
privatelink.vaultcore.azure.net
~~~

Không thay vault URL trong SecretClient bằng private IP vì điều đó có thể phá TLS hostname validation, certificate verification và routing.

### 19.2. Kiến trúc mạng minh họa

~~~mermaid
flowchart TB
    APP["App Service / AKS / VM<br/>private networking"] --> DNS["DNS resolver<br/>private zone integration"]
    DNS --> PE["Private Endpoint IP"]
    PE --> KV["Azure Key Vault data plane"]
    AUTH["Microsoft Entra token endpoint"] --> APP
    ADMIN["Azure ARM control plane"] -. "management" .-> KV
~~~

Cần tính đường đi Entra ID và các dịch vụ khác. Private Endpoint tới Key Vault không tự làm toàn bộ authentication traffic đi riêng hoặc cấp thêm RBAC.

### 19.3. App Service VNet Integration khác Private Endpoint

- **VNet Integration** của App Service là cách ứng dụng truy cập tài nguyên qua outbound path theo cấu hình.
- **Private Endpoint** của Key Vault cho phép truy cập vault qua IP riêng trong VNet.
- **Private Endpoint của App Service** là inbound private access tới chính App Service, khác với outbound access tới Key Vault.
- DNS/NSG/firewall/route cần đúng ở từng bên.

Không chỉ bật private endpoint rồi kỳ vọng các ứng dụng ngoài VNet vẫn đọc được secret. Local developer có thể cần VPN/ExpressRoute hoặc jump host được cho phép.

### 19.4. Cách chẩn đoán DNS/firewall

1. Kiểm tra Key Vault endpoint được cấu hình đúng.
2. Kiểm tra nơi ứng dụng chạy (local, App Service, pod, VM).
3. Kiểm tra DNS resolution của **vault-name.vault.azure.net** từ đúng network.
4. Kiểm tra private endpoint/zone links và routing.
5. Kiểm tra TLS handshake, không bỏ certificate validation.
6. Kiểm tra Azure Firewall, NSG, proxy, app egress policy.
7. Sau khi network thông, kiểm tra data-plane RBAC.
8. Quan sát HTTP status/error code và correlation ID.

**Không bật public network access “cho chạy được”** khi policy yêu cầu private. Sửa DNS/network chính xác.

### 19.5. Multiple region và recovery

Key Vault cung cấp các cơ chế availability/replication do dịch vụ quản lý theo khả năng/vùng. Không tự suy ra một vault sẽ hoạt động với **RTO=0, RPO=0** trong mọi sự cố region. Nếu production có yêu cầu failover đặc biệt, thiết kế vault/secret distribution, identity/permissions và application fallback rõ ràng, thử DR trước khi tin tưởng.

Không tự copy secret giữa vùng bằng script không được phê duyệt; việc đó tạo thêm bản sao cần quản lý/audit/rotation.

## 20. App Service và Azure Functions: Key Vault reference hay Java SDK?

Có hai cách thông dụng để một Java workload dùng secret.

### 20.1. Cách A: Java SDK trực tiếp

~~~text
Java application
→ SecretClient / Managed Identity
→ Key Vault
→ secret value trong Java process
~~~

Ưu điểm:

- Tự quyết định khi nào đọc/refresh/version.
- Xử lý metadata, expiration, business fallback.
- Có thể dùng chung logic trên App Service/AKS/VM.
- Có telemetry ở cấp code và kiểm tra chính xác secret name.

Đánh đổi:

- Thêm SDK dependency và code lifecycle/retry.
- Phải thiết kế secret cache/rotation/exception handling.
- Chú ý không gọi vault liên tục mỗi request.

### 20.2. Cách B: Key Vault reference trong app settings

Một số Azure runtimes như App Service/Functions hỗ trợ đặt **Key Vault reference** ở application settings, ví dụ:

~~~text
Setting name: PAYMENT_API_KEY

Setting value:
@Microsoft.KeyVault(SecretUri=https://<vault-name>.vault.azure.net/secrets/orders-payment-api-key/)
~~~

Platform sẽ resolve reference theo identity được cấu hình, rồi **ứng dụng Java đọc giá trị qua environment/app setting** như cấu hình thường. Không cần Java SecretClient cho riêng biến đó.

Điều cần hiểu:

- Runtime vẫn nhận được **secret value** trong cấu hình/process environment; không ghi log/dump.
- Vault RBAC/network vẫn phải cho phép identity của app.
- Identity dùng resolve reference có thể được chọn theo cấu hình runtime.
- Một reference không pin version có cơ chế cache/refresh riêng của platform, **không đảm bảo giá trị mới có hiệu lực tức thì**.
- Chỉ xem reference là thay thế SDK khi ứng dụng thực sự không cần metadata/version/rotation logic đặc biệt.
- Cú pháp và giới hạn Key Vault reference phải được xác minh theo runtime/tier hiện hành.

### 20.3. Quyết định

| Nhu cầu | Java SDK | Key Vault reference |
|---|---|---|
| Cần đọc secret value tại startup | Có | Có nếu runtime hỗ trợ |
| Cần get theo secret version cụ thể | Có | Có theo URI/cấu hình hỗ trợ |
| Cần xem metadata/expiration | Có | Không thuận tiện cho Java |
| Cần ứng dụng chủ động refresh | Có | Phụ thuộc refresh platform |
| Muốn ít code Java hơn | Cần SDK | Thường đơn giản hơn |
| Chạy trên nhiều cloud runtimes | Java SDK linh hoạt | Tính năng phụ thuộc Azure runtime |
| Cần quản lý nhiều secrets động theo tenant | Có thể, nhưng phải cân nhắc quota/permissions | Không thích hợp với số settings lớn |
| Hạn chế quyền ứng dụng | Data-plane RBAC vẫn cần | Data-plane RBAC vẫn cần |

**Không dùng Key Vault reference như cơ chế authorization của người dùng cuối.** Nó chỉ quản lý cách backend lấy configuration secret.

## 21. Spring Boot: tiêm SecretClient và tách SecretProvider

### 21.1. Spring bean

Với ứng dụng đã có Spring Boot dependencies, cấu hình SecretClient dưới dạng singleton bean:

~~~java
package com.example.keyvault;

import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.security.keyvault.secrets.SecretClient;
import com.azure.security.keyvault.secrets.SecretClientBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class KeyVaultBeans {

    @Bean
    public SecretClient secretClient() {
        String vaultUrl = System.getenv("KEY_VAULT_URL");

        if (vaultUrl == null || vaultUrl.isBlank()) {
            throw new IllegalStateException("Missing KEY_VAULT_URL");
        }

        return new SecretClientBuilder()
            .vaultUrl(vaultUrl)
            .credential(new DefaultAzureCredentialBuilder().build())
            .buildClient();
    }
}
~~~

**Spring Boot dependencies không nằm trong Maven POM đơn giản ở mục 8.** Đoạn này là ví dụ tích hợp cho project Spring Boot đã tồn tại, không phải phần có thể biên dịch độc lập với POM demo.

### 21.2. Không cho mọi controller tự gọi vault

Một interface giúp tách infrastructure và domain:

~~~java
package com.example.keyvault;

public interface SecretProvider {
    String requireSecret(String name);
}

public final class KeyVaultSecretProvider
        implements SecretProvider {

    private final com.azure.security.keyvault.secrets.SecretClient client;

    public KeyVaultSecretProvider(
            com.azure.security.keyvault.secrets.SecretClient client) {
        this.client = client;
    }

    @Override
    public String requireSecret(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("Secret name required");
        }
        String value = client.getSecret(name).getValue();
        if (value == null || value.isBlank()) {
            throw new IllegalStateException("Secret value unavailable");
        }
        return value;
    }
}
~~~

Ví dụ tách trách nhiệm, **chưa triển khai caching/retry/rotation**. Với Spring, mỗi public top-level type phải nằm trong Java file tương ứng. Inject interface SecretProvider vào service nghiệp vụ giúp unit test không phải gọi Key Vault thật.

### 21.3. Spring config và secret lifecycle

- Properties chứa **vault URL, secret name, refresh interval**, không chứa secret value.
- Với secret phải đọc ở startup, fail-fast và hiển thị lỗi đã sanitize.
- Với dynamic rotation, tổ chức một cache/refresh service có synchronization và metrics.
- Không bật debug HTTP body logging của SDK/WebClient cho endpoints chứa secrets.
- Không expose secret value qua Spring Actuator **/env**, **/configprops**, health details hoặc exception page.
- Giới hạn các actuator endpoints trong private/admin scope và bật sanitization.

## 22. Unit test và integration test không làm lộ secrets

### 22.1. Unit tests dùng fake

Ví dụ:

~~~java
package com.example.keyvault;

import java.util.Map;

public final class FakeSecretProvider implements SecretProvider {
    private final Map<String, String> values;

    public FakeSecretProvider(Map<String, String> values) {
        this.values = values;
    }

    @Override
    public String requireSecret(String name) {
        String value = values.get(name);
        if (value == null) {
            throw new IllegalArgumentException("Unknown demo secret");
        }
        return value;
    }
}
~~~

Unit test:

~~~java
SecretProvider secrets = new FakeSecretProvider(
    java.util.Map.of(
        "orders-payment-api-key", "DEMO_ONLY_FOR_UNIT_TEST"));

String demo = secrets.requireSecret("orders-payment-api-key");
if (!"DEMO_ONLY_FOR_UNIT_TEST".equals(demo)) {
    throw new AssertionError("Unexpected demo secret");
}
~~~

Không cần gọi Entra hoặc Key Vault trong unit tests. Fake giúp thử business logic và tránh flaky tests phụ thuộc mạng.

### 22.2. Integration tests với vault riêng

Khi thực sự cần verify Azure SDK end-to-end:

1. Có Key Vault lab riêng và role assignment đã duyệt.
2. Tạo demo value không có giá trị bảo mật.
3. Chạy test xác minh getSecret thành công.
4. Thử identity không có quyền → 403 hoặc lỗi tương ứng.
5. Thử secret name sai → lỗi phù hợp.
6. Test latest/versioned reads.
7. Test rotation và application refresh.
8. Test network restriction từ môi trường không được phép.
9. Thu thập request IDs/metrics không log value.
10. Dọn demo secrets/vault lab theo retention policy.

Không ghi real Key Vault secrets vào JUnit snapshots, screenshots, CI logs hoặc test reports.

### 22.3. Không dùng tests để thay quyền

Nếu integration test thiếu quyền, không cho test runner tự cấp **Key Vault Administrator** hoặc tự tắt firewall. CI job phải có role được xác định bằng IaC/policy và không có quyền nâng privilege của chính nó nếu không cần.

### 22.4. Kiểm thử rotation trong staging

- App A dùng version V1.
- Operator set V2 ở vault.
- App B canary refresh V2.
- Partner auth nhận V2.
- App A restart/refresh theo lịch.
- Thu hồi V1 khi tất cả dùng V2.
- Theo dõi error budget, 401 từ partner, Key Vault 403/429.
- Thử rollback theo runbook nếu V2 lỗi.

## 23. Soft-delete, purge protection và khôi phục

Key Vault hỗ trợ cơ chế **soft-delete** và tùy chọn **purge protection** giúp giảm nguy cơ xóa vĩnh viễn ngoài ý muốn. Tính năng/retention và khả năng thay đổi chính sách phụ thuộc loại vault và thời điểm tạo, vì vậy luôn xác minh trước khi tạo production vault.

### 23.1. Xóa secret không đồng nghĩa purge

Các khái niệm:

- **Delete secret:** đưa secret vào trạng thái đã xóa, có thể recover trong soft-delete retention khi được phép.
- **Recover deleted secret:** phục hồi khi còn trong retention và điều kiện cho phép.
- **Purge:** xóa vĩnh viễn theo quyền và điều kiện bảo vệ.
- **Purge protection:** chặn purge trước khi hết retention theo chính sách, thường là lựa chọn quan trọng cho production.

**Không tự chạy purge trong bài lab** chỉ để dọn cho sạch; purge có thể không thể phục hồi và purge protection có thể ngăn thao tác đó. Không lấy việc “xóa resource group” làm cam kết rằng mọi vault names/secrets lập tức có thể tái sử dụng.

### 23.2. Khi nghi lộ secret

Một kế hoạch incident response:

1. Xác định secret nào có khả năng bị lộ và phạm vi blast radius.
2. Thu hồi hoặc vô hiệu hóa credential ở **hệ thống đối tác** khi thích hợp.
3. Tạo key mới và rotate trong Key Vault qua kênh an toàn.
4. Cập nhật/refresh tất cả app identities và workload caches.
5. Xem Key Vault audit logs, app logs, CI logs, source history.
6. Đối chiếu phiên bản và access permissions.
7. Giới hạn/quarantine compromised principals; nếu cần revoke tokens/sessions theo security runbook.
8. Kiểm tra hệ thống ổn định với key mới.
9. Viết postmortem và kiểm tra các đường rò còn tồn tại.

**Xóa một secret trong vault không tự thu hồi bản sao đã bị lấy trước đó**, cũng không thu hồi key tại partner. Rotation và revoke tại nơi kiểm chứng secret mới là hành động quyết định.

## 24. Giám sát và audit Key Vault

### 24.1. Các lớp telemetry

| Lớp | Chỉ số hoặc logs | Mục đích |
|---|---|---|
| **Key Vault service** | Requests, latency, throttling/error codes theo tính năng | Theo dõi health và quota |
| **Key Vault data-plane diagnostics** | Secret get/set/list/delete access metadata và kết quả theo diagnostic settings | Audit truy cập |
| **Azure Activity Log** | Thay đổi vault resource/network/role assignment | Audit control plane |
| **Java application** | Credential acquisition failures, getSecret latency, cache hit/refresh | SLO ứng dụng |
| **Rotation service** | Versions created, credential activation, rollback events | Đảm bảo lifecycle |
| **Microsoft Entra logs** | Identity/token anomalies theo log permissions | Điều tra authentication |
| **Partner API** | Unauthorized responses sau rotation, external latency | Kiểm chứng key thật hoạt động |

Tên metric và log category có thể thay đổi theo tài nguyên/tier/diagnostic mode; không khẳng định tất cả sẵn có ngay khi tạo vault. Chọn diagnostic settings và retention phù hợp.

### 24.2. Log an toàn

~~~json
{
  "event": "KEYVAULT_SECRET_RESOLVE",
  "vaultName": "kv-orders-prod-example",
  "secretName": "orders-payment-api-key",
  "status": "SUCCESS",
  "durationMs": 48,
  "correlationId": "corr-example-481"
}
~~~

Đây là JSON mô tả telemetry giả định. Không chứa **secretValue**, access token, connection string, Authorization header hoặc raw HTTP body. Kể cả secretName có thể tiết lộ internal topology; trong môi trường hạn chế có thể chỉ log hash/alias.

### 24.3. Cảnh báo cần có

- Vault requests 403/401 tăng bất thường.
- Key Vault 429/throttling hoặc p95 latency tăng.
- Thất bại khi refresh cache hoặc lấy secret ở startup.
- Secret/certificate approaching expiry theo metadata/event khi có.
- Rotation quá hạn hoặc ứng dụng vẫn sử dụng version cũ.
- Role assignments/network/firewall changes không được duyệt.
- Bất thường về volume đọc secrets ngoài giờ.
- Logs hoặc build artifacts vô tình chứa secret material.

### 24.4. Expiry notifications

Có thể dùng **Azure Event Grid** với các sự kiện Key Vault liên quan tới secret/certificate near-expiry, expired hoặc version change theo khả năng hỗ trợ. Tuy nhiên:

- Notification là tín hiệu; không thay lịch rotation được quản lý.
- Không giả định event được gửi đúng một lần hoặc tự xoay vòng partner credential.
- Consumers cần idempotency và có runbook khi subscription/DLQ xảy ra lỗi.
- Nên kiểm tra periodic inventory/metadata để chống mất event.

### 24.5. Observability không được thành đường lộ secret

Không bật **HTTP BODY logging** cho Key Vault SDK trong production nếu có nguy cơ response chứa secret value. Không gắn giá trị secret làm trace attribute, metric label hoặc exception message. Log status code, endpoint/vault alias, request ID, duration và credential type theo policy; sanitize nội dung.

## 25. Availability, caching và fail-closed behavior

### 25.1. Trường hợp Key Vault outage

Ứng dụng có thể đang ở các trạng thái:

| Trạng thái | Rủi ro | Chiến lược |
|---|---|---|
| Instance đang chạy, secret đã cache | Vẫn có thể gọi partner nếu credential còn valid | Sử dụng cache theo TTL/security policy |
| Instance mới start, không lấy được secret | Startup fail hoặc service unavailable | Fail-fast/readiness false, retry bounded |
| Secret vừa bị thu hồi | Cache chứa credential không an toàn | Fail-closed/forced refresh theo incident policy |
| Vault trả 429 | Retry storm | Backoff, cap concurrent fetches, giảm refresh frequency |
| Mất DNS/private network | Request timeout | Sửa networking, không tắt TLS |
| Partner đổi key trước app | App auth lỗi | Rotation rollback/dual-key transition |

### 25.2. Readiness khác liveness

**Không** để liveness probe gọi Key Vault mỗi 5 giây; khi vault chậm, Kubernetes có thể restart tất cả pods và tạo thundering herd. Liveness kiểm tra process còn hoạt động; readiness xem app đã có cấu hình cần thiết và thực sự xử lý request an toàn chưa.

Nếu Key Vault outage nhưng secret đang cache còn hợp lệ, app có thể giữ readiness; nếu không có credential hoặc credential đã bị revoke, app phải ngừng phục vụ những routes yêu cầu secret theo policy.

### 25.3. Cache refresh với jitter

Giả sử 100 instances, tất cả refresh cùng giây:

~~~text
100 concurrent Key Vault GET
→ dễ tạo spike/throttling nếu nhiều secrets và vault nhỏ
~~~

Thêm jitter vào refresh window; cấu hình TTL phù hợp rotation, per-service quota và security needs. Không tăng TTL vô hạn để che lỗi mạng.

### 25.4. Không fallback sang key trong binary

Anti-pattern:

~~~java
String key;
try {
    key = secretClient.getSecret(name).getValue();
} catch (Exception ignored) {
    key = "HARDCODED_BACKUP_KEY";
}
~~~

Một fallback như vậy làm lộ credential và có thể khiến app chạy với key đã bị thu hồi. Thay bằng lỗi rõ, cache có chính sách hoặc credentialless mode được duyệt.

## 26. Quota, hiệu năng và chi phí

### 26.1. Không gọi vault mỗi request

Giả sử Orders API nhận **1.000 requests/s** và mỗi request gọi một secret:

~~~text
1.000 × 60 × 60 × 24
= 86.400.000 Key Vault GET/ngày
~~~

Đây là phép tính **giả định**, không phải quota Azure. Nó làm tăng calls, cost và latency.

Nếu 50 instances đọc một secret mỗi **10 phút** theo cache TTL đơn giản:

~~~text
50 instances × 6 lần/giờ × 24 giờ
= 7.200 GET/ngày
~~~

Chưa tính instance restarts, rotation events, concurrent refresh, retries và nhiều secret names. Quy mô minh họa cho thấy sự khác biệt rất lớn giữa per-request fetch và caching có kiểm soát.

### 26.2. Cost components

| Thành phần | Nguồn chi phí |
|---|---|
| Key Vault operations | Giá theo số API operations và loại/tier được sử dụng |
| Premium/HSM-related features | Có thể có mức tính khác so với standard |
| Key rotation và versions | Số thao tác quản lý, dữ liệu/lifecycle theo khả năng |
| Azure Monitor | Diagnostic logs ingestion/retention/alerts |
| Private Endpoint và networking | Private Link, NAT/firewall, dữ liệu cross-region theo model |
| App runtime | App Service, AKS, VM, Container Apps/Functions |
| High availability/DR | Tài nguyên hoặc kế hoạch đa vùng thêm |
| CI/CD | Integration tests, repeated provisioning, audit |

Không đưa mức giá cố định vào code hoặc kiến trúc: cần dùng bảng giá Azure, Cost Management và budgets theo **region/tier/thời điểm thực**.

### 26.3. Cost không phải yếu tố duy nhất

Cache TTL lớn có thể giảm operations nhưng tăng thời gian app dùng secret cũ sau rotation/revocation. Quyết định từ:

- Rotation recovery time.
- Exposure risk.
- SLO latency.
- Quota và max burst.
- Security/compliance requirements.
- Khả năng failover của app.

**Chi phí tiết kiệm không nên làm mất bảo đảm bảo mật đã cam kết.**

## 27. Câu chuyện triển khai thực tế: Orders API trên App Service

Một trình tự triển khai gọn và có kiểm tra:

1. Tạo resource group, app plan và App Service trên subscription được phê duyệt.
2. Enable system-assigned managed identity cho Orders API.
3. Tạo Key Vault, bật RBAC và security/network settings theo IaC.
4. Operator tạo **orders-payment-api-key** qua kênh an toàn.
5. Gán Key Vault Secrets User cho principal ID của App Service.
6. Nếu cần private access, cấu hình VNet Integration, Private Endpoint, DNS và firewall.
7. Set **KEY_VAULT_URL**, **KEY_VAULT_SECRET_NAME** (không chứa value).
8. Deploy JAR và khởi tạo một singleton SecretClient qua DI.
9. Đọc secret ở startup hoặc cache refresh theo thiết kế; readiness chỉ true khi app đủ điều kiện phục vụ.
10. Test partner API bằng credential nhưng không log value/header.
11. Bật application/Key Vault metrics và audit.
12. Diễn tập rotation key qua canary.
13. Kiểm tra incident path: key bị thu hồi, vault 403, timeout/429, partner 401.
14. Định kỳ review roles, orphaned vaults, expiry và cost.

**Không có thao tác Azure thật được thực hiện khi viết bài.** Các bước là runbook minh họa cho người học hoặc nhóm triển khai.

## 28. Các anti-pattern thường gặp

| Anti-pattern | Vì sao nguy hiểm | Cách cải thiện |
|---|---|---|
| Commit secret trong application.properties | Source/history/artifact leak | Key Vault + managed identity |
| Dùng account key của Azure service dù hỗ trợ Entra | Secret sprawl | Identity-based auth trực tiếp |
| Cấp Key Vault Administrator cho mọi app | Blast radius lớn | Secrets User chỉ đọc |
| Cho rằng Azure Contributor đọc được secret value | Nhầm control/data plane | Data-plane RBAC riêng |
| Copy secret value qua CI environment log | Rò credential | Secret provisioning/rotation an toàn |
| Mỗi HTTP request tạo SecretClient | Overhead HTTP/token/calls | Singleton DI client |
| Mỗi HTTP request getSecret | 429/cost/latency | Startup fetch hoặc cache refresh |
| Không version hóa rotation | Khó rollback/audit | Secret versions và rollout plan |
| Dùng version-pinned mãi mãi | App không nhận key mới | Versionless refresh hoặc planned rollout |
| Đặt expiresOn rồi nghĩ đã tự xoay vòng | Partner key vẫn cũ | Rotation service/runbook |
| Bỏ qua partner-side revoke | Secret bị lộ vẫn dùng được | Thu hồi ở source of truth |
| Lộ secret trong logs/exception | Credential leak | Sanitized telemetry |
| Chuyển Key Vault URL thành private IP | TLS/hostname lỗi | FQDN + private DNS |
| Bật firewall public vô hạn để sửa 403 | Mở đường truy cập | Sửa identity/network đúng lớp |
| Retry 403/404 vô hạn | DDoS chính vault | Phân loại lỗi |
| Dùng liveness probe getSecret | Restart storm | Readiness riêng, cache |
| Cache secret cũ không giới hạn | Không nhận rotation/revoke | TTL, refresh, security policy |
| Dùng fake unit tests gọi production vault | Tốn phí/lộ data/flaky | Fake provider + lab integration |
| Xóa/purge secret để dọn nhanh | Có thể mất khả năng phục hồi | Soft-delete/purge-protection policy |
| Xem Key Vault thay config database | Chi phí/độ phức tạp | App Configuration cho non-secret data |

## 29. Runbook chẩn đoán theo triệu chứng

### 29.1. Java nhận 403 dù vault tồn tại

Kiểm tra theo thứ tự:

1. Đọc status code, error code và request/correlation ID **không ghi secret value**.
2. Xác định code đang chạy trên local, App Service, AKS hay CI.
3. Xác định TokenCredential thực tế được chọn và **principal object ID**.
4. Đọc vault permission model: Azure RBAC hay access policies.
5. Đọc role assignment/access policy của principal ở đúng scope.
6. Phân biệt quyền **Key Vault Secrets User** với Key Vault Reader/Azure Contributor.
7. Xem Azure RBAC propagation nếu role mới cấp.
8. Kiểm tra network restrictions, firewall, private endpoint và DNS.
9. Kiểm tra tenant ID, token audience và managed identity client ID.
10. Dùng một secret demo có quyền để test, không in value.
11. Nếu vẫn lỗi, thu thập sanitized diagnostics và đối chiếu Azure Monitor/Key Vault audit.
12. Ghi root cause thành regression test/IaC permission test.

Không tự tăng quyền thành Owner/Administrator để “chữa nhanh” nếu chưa biết lỗi do network, scope hay token.

### 29.2. Java nhận 404 Not Found

Khả năng:

- Sai **vault URL** (dev/test/prod).
- Sai secret name hoặc casing/format theo API.
- Dùng version ID của secret khác.
- Secret/version bị xóa, không tồn tại hoặc bị vô hiệu theo trạng thái.
- Permission/network error bị ứng dụng wrapper chuyển thành 404 vì che thông tin.

Hành động:

1. Kiểm tra KEY_VAULT_URL và KEY_VAULT_SECRET_NAME.
2. Kiểm tra vault thuộc đúng subscription/region/tenant.
3. Kiểm tra metadata qua kênh admin được phép, không in value.
4. Xem version đã pin, và liệu rotation đã tạo version mới hay chưa.
5. Kiểm tra app configuration cache/version.
6. Không tự tạo một secret giá trị rỗng khi get thất bại.

### 29.3. 429 khi scale out

Triệu chứng: Key Vault request latency tăng, SDK retry nhiều, pod mới không ready.

Cách điều tra:

1. Đo số instances, requests/sec, GET/SET/LIST distribution.
2. Kiểm tra app có đang gọi getSecret cho mỗi HTTP request không.
3. Xem retry policy có bị chồng nhiều tầng không.
4. Dùng TTL cache hoặc startup cache khi nghiệp vụ cho phép.
5. Thêm jitter/điều phối refresh và bounded concurrency.
6. Tôn trọng Retry-After.
7. Thử số instances thấp rồi tăng có kiểm soát.
8. Xem quota và giới hạn per-vault theo tài liệu/tier hiện hành.
9. Không tắt retries hoàn toàn nếu SDK đã được cấu hình đúng, nhưng cần retry budget rõ.

### 29.4. Chạy local được, App Service thất bại

- Local credential là user Entra, production là managed identity khác.
- Role gán cho developer nhưng chưa gán cho App Service principal.
- KEY_VAULT_URL hoặc tenant của production sai.
- App Service dùng user-assigned identity nhưng clientId không được chọn.
- Production VNet/DNS/firewall khác local.
- App Service app setting chứa Key Vault reference chưa resolve do thiếu quyền.
- App bị restart/scale trước khi identity/role propagation hoàn tất.

Cách sửa: kiểm tra identity thực và scope, network, dependency readiness; không sao chép client secret của developer sang production.

### 29.5. Rotation rồi nhưng Java vẫn dùng key cũ

- App cache version cũ.
- Code dùng getSecret(name, pinnedVersion).
- App Service Key Vault reference cache chưa refresh.
- Partner API vẫn nhận key cũ, health check không phát hiện.
- Một số instances đã refresh, số khác chưa.
- Secret mới được set nhưng bị disabled/not-before/expired.
- Không có chuyển tiếp dual-key hoặc partner chưa kích hoạt credential mới.

Runbook: so version metadata của các instances, canary một instance mới, xác nhận partner-side key state, điều phối refresh/restart và revoke cũ đúng thời điểm. Không log cả key cũ và key mới để “so sánh”.

### 29.6. Private Endpoint lỗi TLS hoặc DNS

- SecretClient phải dùng **vault FQDN**, không kết nối raw private IP.
- Xác minh private DNS zone **privatelink.vaultcore.azure.net** và liên kết VNet.
- Kiểm tra outbound VNet Integration của App Service hoặc pod network.
- Kiểm tra route/NSG/Azure Firewall/proxy.
- Không bỏ qua certificate validation.
- Không coi Entra token thành công là bằng chứng network tới vault đã thông.

### 29.7. SDK trả lỗi do expired/disabled secret

- Xác định metadata version nào thực sự được đọc.
- Kiểm tra ExpiresOn/NotBefore/Enabled.
- Kiểm tra rotation owner và incident rules.
- Không tự quay về secret cũ nếu đã bị revoke vì rò dữ liệu.
- Với system critical, đưa route phụ thuộc secret về trạng thái không sẵn sàng theo policy.
- Có escalation/alert và kế hoạch khôi phục an toàn.

## 30. Kiểm thử bảo mật và độ tin cậy

| Test case | Thao tác | Kết quả mong đợi |
|---|---|---|
| Happy path local | Developer được cấp Secrets User đọc secret demo | getSecret thành công, không log value |
| No data role | Identity không có quyền đọc | 403 hoặc denial tương ứng, không lộ value |
| Reader metadata-only | Identity có Key Vault Reader | Không được đọc secret value |
| Wrong vault URL | Trỏ tới vault không tồn tại | Lỗi rõ, không fallback hard-coded |
| Wrong secret name | Gọi tên không có | Không tự tạo secret |
| Wrong version | getSecret với version sai | Error, không âm thầm lấy latest |
| Disabled/expired | Đọc version không khả dụng | Fail/alert theo policy |
| Redis/cache không liên quan | Không có secret cache hoặc cache miss | Nạp từ Key Vault có giới hạn |
| Concurrent startup | 100 instances cùng start | Không tạo retry storm |
| Rotation | Set V2, refresh app | App dùng version mới theo contract |
| Partner rejects V2 | API đối tác trả 401 | Rollback/quarantine theo runbook |
| Vault 429 | Simulate throttling | Backoff có giới hạn, metrics đầy đủ |
| DNS/network down | Private endpoint không tới được | Error sanitized, không tắt TLS |
| Secret leaked in log | Test scanning logs | Không có secret value/token |
| Managed identity changed | Principal không còn role | Không truy cập được secret |
| Role revocation | Remove data-plane permission | Access bị từ chối theo propagation |
| Service restart | Cache mất | Tải lại hoặc fail closed theo policy |
| App setting reference refresh | Versionless reference đổi | App nhận mới theo cơ chế platform |
| Dev/prod separation | Secret prod không được mở từ dev identity | Permission denied |
| Secret delete recovery | Soft-delete trong lab có approval | Khôi phục theo policy, không purge |

Không thử xoay vòng secret production, tắt firewall thật hoặc xóa tài nguyên shared nếu chưa được owner phê duyệt.

## 31. Checklist trước production

- [ ] Đã xác định secret nào **không thể thay bằng Entra managed identity**.
- [ ] Vault thuộc subscription/resource group/region/owner đúng.
- [ ] Đã chọn permission model RBAC hoặc access policies có chủ đích.
- [ ] Application identity chỉ có **Key Vault Secrets User** hoặc quyền dữ liệu tối thiểu.
- [ ] Rotation identity được tách riêng, không dùng quyền ghi cho app reader.
- [ ] Managed identity/workload identity đã bật và principal/client ID được kiểm tra.
- [ ] Không đưa developer identity, client secret hoặc admin key vào production config.
- [ ] Secret value không nằm trong Git, Docker image, JAR, CI logs, IaC state không được bảo vệ.
- [ ] SDK dependencies được pin bằng version/BOM và quét CVEs.
- [ ] SecretClient được tái sử dụng qua DI.
- [ ] Ứng dụng không getSecret trên mọi request.
- [ ] Cách cache TTL, refresh, version pinning và stale secret được định nghĩa.
- [ ] Fail-fast/fail-closed behavior khi vault hoặc partner không sẵn sàng rõ ràng.
- [ ] Java logs, traces, HTTP body logging và exception redaction đã được kiểm tra.
- [ ] Secret name/URL và các config không nhạy cảm được quản lý theo environment.
- [ ] Private Endpoint/VNet integration/firewall/DNS đúng nếu policy yêu cầu.
- [ ] TLS/certificate verification không bị vô hiệu hóa.
- [ ] RBAC propagation và identity rotation đã được test trên staging.
- [ ] Có vòng đời soft-delete/purge protection và quyền recovery.
- [ ] Có rotation owner, lịch nhắc, expiration và partner-side revoke.
- [ ] Đã chạy thử V1→V2 canary và rollback.
- [ ] Có test 401/403/404/429, timeout và concurrent startup.
- [ ] Có alert unauthorized requests, throttling, rotation overdue, secret expiry.
- [ ] Audit logs và retention phù hợp data classification.
- [ ] App Service Key Vault reference cache/refresh semantics được hiểu nếu sử dụng.
- [ ] Spring Actuator hoặc configuration endpoints không expose secret.
- [ ] Không dùng Key Vault làm database cho non-secret configuration.
- [ ] Đã đo Key Vault calls/s và ước tính chi phí/tier/quota.
- [ ] Có incident response plan khi secret bị rò hoặc identity bị xâm nhập.
- [ ] Tài nguyên lab/production có tags, budgets và cost alerts.
- [ ] Có documentation về ownership và những identities đang đọc mỗi secret.

## 32. Bài tập thực hành

### Bài 1: Chọn loại Key Vault object

Với từng yêu cầu, hãy chọn Secret, Key hay Certificate:

1. API key của đối tác.
2. Khóa RSA dùng ký dữ liệu mà không export private key.
3. TLS certificate của domain ứng dụng.
4. Mật khẩu của hệ thống cũ.
5. Non-secret feature flag.
6. Azure Storage được phép dùng Microsoft Entra identity.

Giải thích vì sao một số trường hợp không cần Key Vault secret.

### Bài 2: Tạo vault RBAC trong lab

1. Chọn subscription lab và resource group.
2. Tạo vault với Azure RBAC permission model.
3. Đọc vaultUri và metadata không nhạy cảm.
4. Xác định principal object ID của developer.
5. Chỉ operator được cấp permission tạo role assignment.
6. Tạo một secret có value **DEMO_ONLY_NOT_A_REAL_SECRET**.
7. Liệt kê name và ID mà không hiển thị value.
8. Ghi lại quyền/role nào cần cho từng bước.

### Bài 3: Java SecretClient

1. Tạo project Maven Java 17.
2. Thêm azure-security-keyvault-secrets và azure-identity theo BOM/version được duyệt.
3. Tạo ReadSecretDemo theo mục 11.
4. Đăng nhập local bằng az login.
5. Cấu hình KEY_VAULT_URL và KEY_VAULT_SECRET_NAME.
6. Gọi getSecret và chỉ hiển thị thông báo thành công.
7. Kiểm tra project không có hard-coded real credentials.

### Bài 4: Test principal có và không có quyền

Dùng hai identities trong lab:

- Identity A có **Key Vault Secrets User**.
- Identity B chỉ có **Key Vault Reader** hoặc không có data role.

Thử getSecret với hai identities, ghi status/errors (không ghi value), giải thích vì sao Azure Contributor hoặc Key Vault Reader chưa đủ.

### Bài 5: Version và rotation

1. Tạo version V1 với giá trị demo.
2. Tạo version V2 cũng là demo.
3. Đọc getSecret(name) và getSecret(name, V1).
4. So metadata version và giải thích sự khác nhau.
5. Giả lập partner chỉ chấp nhận V2.
6. Thiết kế rollout từ V1 sang V2 với canary/rollback.
7. Chỉ rõ khi nào thu hồi V1 ở partner.

### Bài 6: Tính hiệu năng

Ứng dụng có 20 instances và 500 requests/s. So sánh:

- Mỗi request gọi một Key Vault GET.
- Mỗi instance cache một secret trong 10 phút.
- Refresh có jitter và bounded retry.

Tính GET/ngày sơ bộ và giải thích vì sao cache quá lâu có thể vi phạm rotation SLA.

### Bài 7: Private Endpoint

Vẽ route từ App Service/AKS đến Key Vault:

- VNet Integration/outbound.
- Private Endpoint và IP.
- Private DNS zone.
- Vault FQDN.
- Entra token acquisition.
- RBAC data-plane check.

Giải thích vì sao việc kết nối private IP trực tiếp có thể làm TLS lỗi và vì sao network rules khác data roles.

### Bài 8: Spring integration

1. Tạo singleton SecretClient bean.
2. Tạo interface SecretProvider.
3. Unit test bằng FakeSecretProvider.
4. Chỉ controller nghiệp vụ có quyền gọi provider.
5. Thêm cache có refresh TTL/metrics khi thật sự cần.
6. Kiểm tra Spring Actuator không lộ value.

### Bài 9: Chẩn đoán 403

Developer đọc demo secret thành công, nhưng Orders API trên App Service nhận 403.

Hãy phân biệt:

- App managed identity principal chưa có role.
- App dùng user-assigned identity sai client ID.
- Vault ở access policy mode.
- Vault network firewall/private endpoint denial.
- RBAC chưa propagate.
- Azure tenant hoặc vault URI không khớp.

Đề xuất thứ tự kiểm tra, không dùng giải pháp “cấp Owner cho ứng dụng”.

### Bài 10: Incident khi secret lộ

Một logging statement vô tình in API key. Thiết kế incident response:

1. Cô lập log/access.
2. Revoke key ở partner.
3. Tạo credential mới và cập nhật Key Vault.
4. Refresh ứng dụng/canary.
5. Kiểm tra logs/CI/Git/history và audit.
6. Review RBAC, incident timeline và policy.
7. Thêm regression test chặn logging.

### Bài 11: So sánh SDK và Key Vault reference

Một Java App Service chỉ cần một API key lúc startup, còn một ứng dụng AKS cần runtime refresh khi rotation. Chọn Java SDK hoặc Key Vault reference và giải thích credential scope, latency, vòng đời cache và platform support.

### Bài 12: Review FinOps

Giả định 50 instances đọc 10 secrets mỗi 5 phút. Tính số Key Vault GET/ngày khi không có lỗi, thêm 10% retries giả định, rồi liệt kê những yếu tố làm phép tính không phản ánh đúng hóa đơn Azure.

## 33. Câu hỏi tự kiểm tra

1. Key Vault bảo vệ những loại đối tượng nào?
2. SecretClient dùng cho Secret hay Key cryptographic operations?
3. Một secret name có thể có bao nhiêu versions?
4. Vault URI khác Secret ID thế nào?
5. Versionless lookup có tự làm mọi app refresh ngay không?
6. Secret value khác SecretProperties ở đâu?
7. Tại sao Key Vault không nên chứa mọi non-secret config?
8. Managed identity giúp giảm loại credential nào?
9. DefaultAzureCredential có thể chọn danh tính nào ở local?
10. Vì sao az login thành công chưa chứng minh có quyền getSecret?
11. Principal object ID khác client ID thế nào?
12. Control plane khác data plane của Key Vault ở đâu?
13. Key Vault Secrets User khác Key Vault Secrets Officer thế nào?
14. Key Vault Reader có được xem secret value không?
15. Azure Contributor có luôn được đọc secret values không?
16. RBAC model và vault access policy model khác nhau thế nào?
17. VNet Integration khác Private Endpoint của Key Vault thế nào?
18. Private DNS zone Key Vault thường liên quan domain nào?
19. Khi dùng private endpoint có nên thay vault URL bằng private IP không?
20. Java SecretClientBuilder cần những thành phần nào?
21. Vì sao không nên in getSecret().getValue()?
22. Java String có thể được xóa khỏi RAM một cách chắc chắn không?
23. Vì sao tái sử dụng SecretClient tốt hơn tạo mỗi request?
24. SecretClient và SecretAsyncClient khác nhau thế nào?
25. Đọc secret mỗi HTTP request gây tác động gì?
26. Caching secret liên quan trade-off bảo mật nào?
27. TTL cache khác vòng đời secret version trong Key Vault ra sao?
28. Làm sao phân biệt 401 và 403?
29. Vì sao 403 có thể đến từ firewall dù data role đúng?
30. 404 do secret name và do version sai khác thế nào khi debug?
31. 429 nên được xử lý ra sao?
32. Có nên retry 403 vô hạn không?
33. Rotation Key Vault có tự rotate API key ở partner không?
34. Version pinning có giúp rollback không, và rủi ro là gì?
35. Soft-delete khác purge và purge protection thế nào?
36. Vì sao xóa secret không thu hồi credential bị lộ ở partner?
37. Key Vault reference trong App Service có làm Java khỏi cần SecretClient không?
38. Key Vault reference có làm secret không xuất hiện trong process environment không?
39. Spring Actuator có thể làm lộ secrets trong hoàn cảnh nào?
40. Khi nào liveness probe không nên gọi Key Vault?
41. Logs nào nên bật để kiểm toán secret access?
42. Những field nào tuyệt đối không được ghi trong telemetry?
43. Vì sao cần tách identity rotation worker và application reader?
44. Khi nào nên dùng Entra trực tiếp thay vì lưu service account password?
45. Những yếu tố nào ảnh hưởng chi phí Key Vault?
46. Có nên đưa admin key vào Dockerfile để giảm lỗi token không?
47. Khi đổi managed identity, cần sửa những phần nào?
48. Nếu vault bị outage và app chưa cache secret, phải làm gì?
49. Hãy kể ba negative tests quan trọng trước production.
50. Vai trò của Key Vault trong zero-trust architecture là gì và giới hạn của nó ở đâu?

## 34. Tài liệu tham khảo

- [Azure Key Vault documentation — Microsoft Learn](https://learn.microsoft.com/azure/key-vault/)
- [Azure Key Vault overview](https://learn.microsoft.com/azure/key-vault/general/overview)
- [About keys, secrets and certificates](https://learn.microsoft.com/azure/key-vault/general/about-keys-secrets-certificates)
- [Authenticate to Key Vault](https://learn.microsoft.com/azure/key-vault/general/authentication)
- [Azure RBAC for Key Vault](https://learn.microsoft.com/azure/key-vault/general/rbac-guide)
- [Assign a Key Vault access policy](https://learn.microsoft.com/azure/key-vault/general/assign-access-policy)
- [Azure Key Vault firewall and network settings](https://learn.microsoft.com/azure/key-vault/general/network-security)
- [Private Link for Azure Key Vault](https://learn.microsoft.com/azure/key-vault/general/private-link-service)
- [Azure Key Vault soft-delete overview](https://learn.microsoft.com/azure/key-vault/general/soft-delete-overview)
- [Azure Key Vault backup and recovery considerations](https://learn.microsoft.com/azure/key-vault/general/backup)
- [Azure Key Vault monitoring](https://learn.microsoft.com/azure/key-vault/general/monitor-key-vault)
- [Azure Key Vault secret management Java quickstart](https://learn.microsoft.com/azure/key-vault/secrets/quick-create-java)
- [Azure Key Vault Secrets Java SDK README](https://learn.microsoft.com/java/api/overview/azure/security-keyvault-secrets-readme)
- [Azure Identity Java SDK](https://learn.microsoft.com/java/api/overview/azure/identity-readme)
- [DefaultAzureCredential in Java](https://learn.microsoft.com/java/api/com.azure.identity.defaultazurecredential)
- [SecretClient Java API reference](https://learn.microsoft.com/java/api/com.azure.security.keyvault.secrets.secretclient)
- [Use Key Vault references for App Service and Azure Functions](https://learn.microsoft.com/azure/app-service/app-service-key-vault-references)
- [Managed identities for Azure resources](https://learn.microsoft.com/entra/identity/managed-identities-azure-resources/overview)
- [Microsoft Entra Workload ID on AKS](https://learn.microsoft.com/azure/aks/workload-identity-overview)
- [Azure SDK for Java guidelines](https://azure.github.io/azure-sdk/java_introduction.html)
- [Azure Key Vault pricing](https://azure.microsoft.com/pricing/details/key-vault/)
- [Azure pricing calculator](https://azure.microsoft.com/pricing/calculator/)






