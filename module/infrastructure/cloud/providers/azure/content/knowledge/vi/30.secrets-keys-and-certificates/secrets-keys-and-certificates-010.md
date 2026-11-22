# Audit truy cập secret và xử lý sự cố xác thực

Một dịch vụ Java chạy trên Azure App Service nhận lỗi **403 Forbidden** khi lấy API key từ Azure Key Vault. Người vận hành thấy role **Contributor** trên resource group và cho rằng ứng dụng đã có quyền. Một tình huống khác, chính ứng dụng vẫn lấy được secret nhưng hệ thống phát hiện hàng trăm lần đọc secret ngoài giờ làm việc từ một danh tính chưa từng được phê duyệt. Hai trường hợp đều cần hiểu **ai đã truy cập secret nào, ở thời điểm nào, bằng danh tính nào, qua mạng nào, thao tác được chấp nhận hay bị từ chối**, đồng thời không làm lộ giá trị secret trong quá trình điều tra.

**Azure Key Vault** lưu trữ và quản lý vòng đời của **secrets, cryptographic keys và certificates**. Một thiết kế an toàn không dừng ở việc cất credential trong vault: cần **bật audit**, phân quyền tối thiểu, kiểm soát đường mạng, cảnh báo truy cập bất thường, phân loại lỗi xác thực và quy trình ứng cứu khi credential bị lộ. Bài học tập trung vào **audit các thao tác trên secrets** và điều tra sự cố **Microsoft Entra ID, Azure RBAC/access policy, firewall/Private Link và ứng dụng sử dụng secret**. Những khác biệt về Keys/Certificates được nêu khi có ảnh hưởng tới audit hoặc quyền.

Bài thuộc chương **Secret, khóa và chứng chỉ** của module **CLOUD_PROVIDERS_AZURE**. Theo phạm vi module, người học khám phá hệ sinh thái Microsoft Azure từ subscription, resource group và Entra ID tới compute, network, storage và data, sau đó triển khai, giám sát, bảo vệ và kiểm soát chi phí một kiến trúc ứng dụng thực tế.

> **Quy tắc an toàn:** Audit log giúp **quan sát thao tác và kết quả truy cập**, không chứng minh rằng mọi secret value đã đọc đều được sử dụng hợp lệ, cũng không thay thế việc rotate/revoke credential tại hệ thống đích. Không bật chế độ debug in **secret value, Authorization header, access token, request/response body chứa secret** chỉ để “xem lỗi”.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **Key Vault data-plane AuditEvent**, **Azure Activity Log**, **Microsoft Entra sign-in/workload identity telemetry** và **application logs**.
2. Giải thích một secret **Get/List/Set/Delete/Recover/Purge** tạo dấu vết và quyền gì; không nhầm metadata access với đọc value.
3. Thiết lập diagnostic settings tới **Log Analytics workspace**, Storage hoặc Event Hubs theo quyền và chính sách.
4. Đọc các trường audit quan trọng: time, operation, status/result, resource, caller IP, identity claims, request/correlation ID.
5. Tạo những truy vấn KQL phân tích failed access, nhiều lần Get, hoạt động lạ theo principal/địa chỉ IP và diễn biến trước/sau thay đổi role.
6. Phân biệt **401 Unauthorized**, **403 Forbidden**, **404 Not Found**, **429 Too Many Requests**, 5xx, timeout/DNS/TLS và hiện tượng bearer challenge.
7. Chẩn đoán **control plane khác data plane**, Azure RBAC so với Key Vault access policies, role scope và propagation.
8. Kiểm tra **DefaultAzureCredential**, managed identity, user-assigned identity, AKS workload identity và token audience/tenant.
9. Giải thích Private Endpoint, public firewall, private DNS và vì sao 403 có thể là network restriction chứ không phải thiếu role.
10. Thiết kế Java SDK logging/exception handling không lộ secret và retry có giới hạn.
11. Xây dựng runbook cho **credential bị lộ**, **đọc bất thường**, **ứng dụng không lấy được secret** và **rotation thất bại**.
12. Định nghĩa thời gian lưu log, chứng cứ điều tra, least privilege, cảnh báo, SLO và cost controls.
13. Thực hiện một lab có dữ liệu giả, kiểm tra cả successful/denied requests mà không chạm vào vault production.
14. Lập checklist và negative tests để đảm bảo hệ thống đã sẵn sàng trước khi đưa workload vào production.

## 2. Tình huống xuyên suốt: Orders API và secret thanh toán

Giả sử một doanh nghiệp chạy **Orders API** viết bằng Java 17/Spring Boot trên Azure App Service. Ứng dụng cần **orders-payment-api-key** để gọi đối tác thanh toán. Các thành phần:

- **Subscription/resource group:** quản lý vault, application, role assignments và monitoring.
- **Microsoft Entra ID:** cấp danh tính và access token cho managed identity của Orders API.
- **Azure Key Vault:** chứa secret theo tên và nhiều versions, xử lý data-plane authorization.
- **App Service/AKS:** nơi Java workload chạy; mạng outbound phải tới vault.
- **Azure Monitor/Log Analytics:** tập hợp audit/operational telemetry.
- **Partner API:** hệ thống dùng API key để xác minh request nghiệp vụ.
- **Rotation operator/pipeline:** có quyền quản lý secret riêng với app reader.

Sơ đồ:

~~~mermaid
flowchart LR
    APP["Orders API<br/>Java + Managed Identity"] --> ENTRA["Microsoft Entra ID<br/>access token"]
    APP --> KV["Azure Key Vault<br/>SecretGet"]
    KV --> PARTNER["Secret value used by<br/>backend Partner API client"]
    APP --> PARTNER
    KV --> DIAG["Diagnostic settings<br/>AuditEvent"]
    DIAG --> LAW["Log Analytics Workspace"]
    ARM["ARM / IAM / vault settings"] --> ACT["Azure Activity Log"]
    ENTRA --> IDLOG["Identity/sign-in telemetry"]
    APP --> APM["Application Insights<br/>sanitized traces"]
    LAW --> SOC["Security operations<br/>KQL + alerts"]
    ACT --> SOC
    IDLOG --> SOC
    APM --> SOC
~~~

**Câu hỏi nghiệp vụ cần điều tra:**

- Có bao nhiêu lần **SecretGet** thành công cho vault trong 24 giờ?
- Identity nào gọi secret vào 02:00 UTC? Có nằm trong allowlist workload/region không?
- Một 403 do **RBAC** hay do **firewall**?
- Ai đã thay permission model hoặc thêm role assignment trước khi truy cập bất thường?
- Ứng dụng có chọn đúng **managed identity** hay vô tình lấy một developer/service-principal credential?
- Secret version nào đang được dùng, có bị disable/expire hay ứng dụng cache version cũ?
- Nếu API key đã bị lộ thì xóa bản trong Key Vault có đủ ngăn kẻ tấn công dùng key ở partner không?

## 3. Các khái niệm phải phân biệt

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| **Secret value** | Giá trị cần bảo vệ, được ứng dụng dùng để xác thực bên ngoài | API key thật |
| **Secret name** | Tên logic do app dùng để tìm bí mật | orders-payment-api-key |
| **Secret version** | Phiên bản giá trị của cùng name, có identifier riêng | GUID-like version string |
| **Secret ID** | URI trỏ tới name/version trong vault | https://vault.vault.azure.net/secrets/name/version |
| **Vault URI** | Data-plane endpoint của Key Vault | https://vault.vault.azure.net/ |
| **Caller identity** | Principal/token thực hiện thao tác data-plane | Managed identity của Orders API |
| **Control plane** | ARM quản lý resource/IAM/network, khác việc lấy value | Update vault firewall |
| **Data plane** | REST operations đọc/ghi secret/key/certificate | SecretGet |
| **Diagnostic setting** | Quy tắc chuyển logs/metrics sang destination | AuditEvent → Log Analytics |
| **Audit event** | Bản ghi thao tác; không nhất thiết có secret value | SecretGet, status 200/403 |
| **Correlation/request ID** | Dấu nối để đối chiếu các tầng service/app | Một request tracking ID |
| **Rotation** | Thay credential và đưa ứng dụng sang credential mới | Partner key v1 → v2 |
| **Revocation** | Làm credential cũ không thể dùng tại nơi kiểm chứng | Disable partner API key v1 |

### 3.1. Secret vs key vs certificate

**Secret**: nếu caller có quyền đọc, secret value có thể được trả về JVM. **Key**: với HSM-backed/non-exportable key, một số phép toán mật mã thực hiện bằng CryptoClient/CryptographyClient mà không đưa private key ra ngoài. **Certificate** có lifecycle, chính sách và quyền riêng, có thể có liên kết tới key/secret khi hình thức certificate yêu cầu.

Khi audit **đọc secret**, tập trung thao tác **SecretGet**, không nhầm **KeySign**, **KeyDecrypt** hay **CertificateGet** với việc tải secret value. Một người được phép xem metadata của vault chưa chắc được phép đọc value.

### 3.2. Secret có nhiều phiên bản

~~~text
Vault: kv-orders-prod-example
  Secret: orders-payment-api-key
    Version V1: legacy credential
    Version V2: replacement credential
~~~

**getSecret(name)** và **getSecret(name, version)** có semantics khác nhau. Khi điều tra rotation, cần biết ứng dụng đang dùng version nào. Không ghi giá trị V1/V2 vào log; version ID/metadata cũng phải được xử lý theo chính sách an toàn và có thể được băm/ẩn.

### 3.3. Authentication, authorization và network

Một luồng **Get Secret** có ba điều kiện độc lập:

~~~mermaid
flowchart TD
    A["Java caller"] --> B["Authentication<br/>Entra token issued"]
    B --> C["Network path<br/>firewall / Private Endpoint"]
    C --> D["Authorization<br/>Key Vault RBAC / access policies"]
    D --> E["Secret lifecycle state<br/>exists/enabled/valid"]
    E --> F["Return secret value to authorized app"]
~~~

Sơ đồ là mô hình logic, **không khẳng định thứ tự đánh giá nội bộ** của Key Vault cho mọi request. Chẩn đoán phải phân biệt token sai, mạng bị chặn, role thiếu và trạng thái secret.

## 4. Bốn nguồn chứng cứ và ranh giới của chúng

### 4.1. Key Vault data-plane audit logs

**Key Vault diagnostic logs** là nguồn chính để điều tra những thao tác data-plane trên vault, khi đã được bật và gửi tới destination. Nhóm logs thường sử dụng category **AuditEvent** theo hỗ trợ của Key Vault/SKU. Các event có thể ghi nhận operation, time, caller IP, identity-related claims, kết quả và mã lỗi.

**Audit không nên chứa plaintext secret value**, nhưng log vẫn có thể chứa **tên secret, secret URI, identity, IP và metadata nhạy cảm**. Phải giới hạn quyền đọc logs và retention.

**Không suy rằng log đã tồn tại từ trước khi bật diagnostic settings**. Việc bật hôm nay không tạo lại đầy đủ những lần getSecret trước đó.

### 4.2. Azure Activity Log

**Azure Activity Log** là nguồn quan trọng cho **control-plane** operations, ví dụ:

- Tạo/xóa vault resource.
- Thay public network access/firewall settings hoặc private endpoints theo resource.
- Thay permission model Azure RBAC/access policies.
- Gán/hủy Azure role assignments (có thể là events của Microsoft.Authorization).
- Update diagnostic settings.
- Những deployment và policy operations liên quan.

**Activity Log không phải danh sách đầy đủ mỗi lần lấy secret value**. Một SecretGet thành công nằm ở Key Vault data plane; muốn thấy phải thiết kế data-plane audit.

### 4.3. Microsoft Entra identity telemetry

Identity/sign-in/workload logs có thể giúp xác minh:

- Identity nào đang xin token.
- Authentication succeeded/failed, policy/conditional access khi áp dụng.
- Service principal hay managed identity nào được dùng.
- Tenant/subject/resource audience.
- Thay đổi credential/federated identity và principal configuration.

Một token được cấp thành công **không chứng minh** caller đã có data-plane quyền Key Vault. Ngoài ra, token/identity logging có các loại, giới hạn, licensing, retention và độ trễ khác nhau. Không mặc định tất cả token acquisition được log dưới cùng một bảng hoặc luôn nhìn thấy mọi request.

### 4.4. Application telemetry

Application Insights/OpenTelemetry hoặc app logs giúp biết:

- Java component nào gọi getSecret.
- Startup vs refresh vs business-request path.
- Latency, retry attempts, cache hit/miss.
- Đã chọn secret name/version/credential type nào (trong phạm vi log an toàn).
- Kết quả dùng secret ở **Partner API**, ví dụ HTTP 401 từ đối tác.

**Rất quan trọng:** 401 từ **Partner API** không phải 401 từ **Key Vault**, mặc dù đều có chữ Unauthorized. Phải ghi **dependency name + endpoint/service** trong telemetry để tìm đúng nguyên nhân.

### 4.5. Đặt câu hỏi theo chứng cứ

| Câu hỏi | Nguồn phù hợp | Không thể tự suy ra |
|---|---|---|
| Có SecretGet tới vault trong khoảng thời gian X? | Key Vault AuditEvent | Giá trị secret đã được dùng vào hành động nào |
| Ai gán quyền Key Vault Secrets User? | Azure Activity Log / authorization audit | Principal có thực sự gọi getSecret không |
| Java đang dùng identity nào? | Identity SDK diagnostics đã sanitize, app context, Entra logs | Mọi claims trong Key Vault nếu không ghi log |
| Vì sao Java GET bị 403? | Key Vault failure details + audit + RBAC + network | Chỉ nhìn permission trong Portal là đủ |
| Secret đã bị sử dụng ở partner API? | Partner audit, application telemetry | Audit Key Vault không quan sát partner request |
| Có bị lộ key trong CI logs? | CI log inspection/scanner và incident review | Không có SecretGet bất thường không chứng minh không bị lộ |

## 5. Mô hình quyền: Azure RBAC và access policy

### 5.1. Control plane khác data plane

Một Azure **Contributor** trên resource group có thể được phép thay đổi nhiều thuộc tính resource, nhưng **không tự có data-plane permission đọc secret value** dưới mô hình Azure RBAC.

Tương tự, **Key Vault Reader** chủ yếu đọc metadata, không đồng nghĩa có quyền **Secret Get value**. **Key Vault Secrets User** là role thường dùng cho một ứng dụng chỉ đọc secret; **Key Vault Secrets Officer** cho người/rotation workload quản lý secret; **Key Vault Administrator** có data-plane quyền rộng và không nên cấp cho application thông thường.

| Nhiệm vụ | Quyền cần xem xét | Principal ví dụ |
|---|---|---|
| Đọc API key ở runtime | Key Vault Secrets User / Secret Get | Orders API managed identity |
| Tạo version mới/rotate | Key Vault Secrets Officer theo policy | Rotation service |
| Kiểm kê metadata | Key Vault Reader nếu đủ | Inventory operator |
| Đổi vault firewall | ARM management role phù hợp | Platform team |
| Tạo role assignment | Owner / User Access Administrator / RBAC Administrator được ủy quyền | IAM operator |
| Cấu hình diagnostic settings | Monitoring/ARM permissions phù hợp + destination access | Platform monitoring team |
| Xem Log Analytics audit | Workspace/table/query RBAC phù hợp | SOC/SRE |

Role names và exact **dataActions**, scope, conditional assignments có thể tiến hóa; đối chiếu role definitions trong tenant hiện tại. **Đừng cấp Owner cho ứng dụng để chữa 403**.

### 5.2. Permission model là một quyết định cấp vault

Key Vault có:

- **Azure role-based access control** (Azure RBAC) làm data-plane permission model.
- **Vault access policies** (legacy/compatibility model) cấp các get/list/set/delete permissions theo principal.

Kiểm tra **vault đang bật mô hình nào**. Tạo RBAC role trên vault dùng access policy model hoặc thêm access policy vào vault RBAC model không mặc nhiên đạt hiệu quả mong muốn.

### 5.3. Scope và least privilege

Một role gán tại subscription/resource group có thể ảnh hưởng nhiều vaults hơn so với vault-level assignment. Với secret data nhạy cảm, nên chọn **scope hẹp nhất có thể hỗ trợ và vận hành được**, cân nhắc secret-scoped assignments khi nghiệp vụ/tính năng cho phép. Tách vaults nếu cần ranh giới bảo mật rõ giữa production và development.

Đặc biệt chú ý **access policy model**: người có quyền đổi vault access policies ở control plane có thể tự mở data access, nếu governance không chặn; đây là lý do nên kiểm soát chặt role cấp phát và permission model.

### 5.4. Authorization propagation và token cache

Role assignment mới hoặc bị thu hồi có thể không tác dụng tức thì do **propagation/caching**. Khi có rủi ro khẩn, không chỉ remove một role rồi tuyên bố toàn bộ truy cập đã bị chặn. Cần kiểm tra thực tế, cân nhắc containment nhiều lớp (identity, network, vault, partner credential rotation) và theo runbook của tổ chức.

## 6. Cấu hình audit trước khi có sự cố

### 6.1. Diagnostic settings

Key Vault **diagnostic settings** có thể gửi logs/metrics tới những destinations phù hợp:

- **Log Analytics workspace:** chạy Kusto Query Language, alert rules, analytics.
- **Azure Storage account:** lưu logs theo retention/archival/compliance.
- **Azure Event Hubs:** stream audit events cho SIEM/data pipeline.
- Những destinations khác khi Azure Monitor/tier hỗ trợ.

Một số lựa chọn schema là **AzureDiagnostics** (legacy/common table) hoặc **resource-specific tables**; tên bảng và cột phụ thuộc diagnostic setting, thời điểm và loại resource. **Không giả định mọi workspace đều có bảng AZKVAuditLogs** nếu diagnostics chưa dùng resource-specific mode.

### 6.2. Chọn log sources đầy đủ

Để điều tra sự cố xác thực end-to-end, thường cần:

1. **Key Vault AuditEvent**: data-plane operations.
2. **Azure Activity Log** của subscription/resource group: resource changes.
3. **IAM / role-assignment change events**: quyền được thay lúc nào, ai làm.
4. **Microsoft Entra workload/service principal/managed identity logs** khi có.
5. **Application/HTTP dependency telemetry** của Java runtime.
6. **Network telemetry** khi dùng firewall/private endpoints/VNet/Azure Firewall.
7. **Partner API audit** khi secret được dùng xác thực với hệ thống bên ngoài.

Chỉ một nguồn log khó chứng minh nguyên nhân của mọi sự cố.

### 6.3. Audit log không phải bản sao secret

**Không log secret value**, dù ở backend debug level. Log của Key Vault không được thiết kế làm kho khôi phục plaintext secret. Backup/recovery và rotation của Key Vault là bài toán khác; không lấy log analytics export làm “secret backup”.

### 6.4. Retention, time và chain of custody

- Bật logs **trước khi triển khai** ứng dụng production.
- Định nghĩa retention theo bảo mật, pháp lý, môi trường và ngân sách.
- Dùng UTC timestamps cho correlation; đồng bộ đồng hồ hệ thống.
- Bảo vệ workspace/storage/event streaming bằng RBAC và least privilege.
- Kiểm soát quyền xóa/sửa logs và destination settings.
- Định nghĩa archive/immutable storage nếu policy yêu cầu.
- Khi incident xảy ra, bảo toàn bản ghi theo quy trình chứng cứ; ghi người truy cập, phạm vi, thời gian, query và hash/export metadata.
- Data minimization: danh tính, IP và secret names vẫn có thể là thông tin nhạy cảm.

### 6.5. Diagnostic settings cũng cần audit

Kẻ tấn công có quyền quản trị có thể cố tắt/chuyển diagnostic settings trước khi đọc secret. Cần cảnh báo **thay đổi monitoring configuration** ở control plane, không chỉ cảnh báo SecretGet. Log retention và destinations cũng là tài sản phải bảo vệ.

## 7. Lab Azure: bật audit có kiểm soát

Các lệnh là **hướng dẫn**, không có thao tác triển khai Azure thật trong bài. Chỉ thực hiện trên subscription, resource group và vault lab được duyệt; các dịch vụ Key Vault/Log Analytics có thể phát sinh phí.

### 7.1. Kiểm tra vault và permission model

~~~bash
az login
az account set --subscription "<lab-subscription-id>"
az account show --output table

VAULT="<approved-lab-vault-name>"
RG="<lab-resource-group>"

az keyvault show \
  --name "$VAULT" \
  --resource-group "$RG" \
  --query "{name:name,uri:properties.vaultUri,rbac:properties.enableRbacAuthorization,publicNetworkAccess:properties.publicNetworkAccess}" \
  --output json

VAULT_ID=$(az keyvault show \
  --name "$VAULT" \
  --resource-group "$RG" \
  --query id --output tsv)
~~~

**az keyvault show** là control-plane query, không phải SecretGet. Có thể đọc thông tin vault mà vẫn không có quyền lấy secret value.

### 7.2. Xem categories và diagnostic settings

~~~bash
az monitor diagnostic-settings categories list \
  --resource "$VAULT_ID" \
  --output table

az monitor diagnostic-settings list \
  --resource "$VAULT_ID" \
  --output json
~~~

Tìm **AuditEvent** theo tính năng hiện có. Nếu có diagnostics đã cấu hình, không tự ghi đè, xóa hoặc chuyển destination đang được SOC sử dụng.

### 7.3. Gửi AuditEvent tới Log Analytics

~~~bash
WORKSPACE_RG="<monitoring-resource-group>"
WORKSPACE="<approved-log-analytics-workspace>"

WORKSPACE_ID=$(az monitor log-analytics workspace show \
  --resource-group "$WORKSPACE_RG" \
  --workspace-name "$WORKSPACE" \
  --query id --output tsv)

az monitor diagnostic-settings create \
  --name "kv-audit-lab" \
  --resource "$VAULT_ID" \
  --workspace "$WORKSPACE_ID" \
  --logs '[{"category":"AuditEvent","enabled":true}]'

az monitor diagnostic-settings show \
  --name "kv-audit-lab" \
  --resource "$VAULT_ID" \
  --output json
~~~

Chỉ chạy nếu vault lab chưa có diagnostic setting cùng tên và operator có đủ quyền. Cú pháp CLI/options/diagnostic mode có thể thay đổi theo version; xác minh qua CLI help và Portal. Có thể chọn destination khác như Storage hoặc Event Hubs khi policy yêu cầu. **Ingestion có độ trễ**: không kết luận audit hỏng vì một event chưa xuất hiện trong vài giây.

### 7.4. Tạo hoạt động thử với secret giả

Dùng identity được phép và một secret có giá trị **DEMO_ONLY**, không dùng production key:

~~~bash
az keyvault secret show \
  --vault-name "$VAULT" \
  --name "lab-audit-demo" \
  --query "{id:id,enabled:attributes.enabled}" \
  --output json
~~~

Dù output chỉ chọn metadata, lệnh show có thể thực hiện **data-plane Get** trả value về CLI trước khi format output. Vì vậy không chạy trên secret thật để “thử cho biết”. Có thể thử identity lab không được phép để tạo sự kiện denied theo kế hoạch được owner phê duyệt.

### 7.5. Chuẩn bị quyền truy vấn logs

Operator được cấp quyền xem workspace cần xác nhận:

- Diagnostic setting đã bật và gửi đến **đúng workspace**.
- Logs và schema xuất hiện theo bảng được chọn.
- Retention và table-level/RBAC access đúng.
- Có khả năng tra Azure Activity Log/IAM changes.
- Có ứng dụng test sinh correlation và status an toàn.
- Log không chứa secret value, tokens hoặc full Authorization headers.
- Không xóa diagnostic settings/logs vừa có khi dọn lab nếu retention policy chưa cho phép.

## 8. AzureDiagnostics, resource-specific table và schema

Key Vault AuditEvent có thể tới **AzureDiagnostics** (bảng dùng chung) hoặc resource-specific table như **AZKVAuditLogs** theo diagnostic configuration. Table names và columns có thể khác theo mode, loại resource và thời điểm.

### 8.1. Khám phá AzureDiagnostics

~~~kusto
AzureDiagnostics
| where TimeGenerated >= ago(1h)
| where ResourceProvider =~ "MICROSOFT.KEYVAULT"
| where Category =~ "AuditEvent"
| take 10
~~~

Sau đó kiểm tra schema:

~~~kusto
AzureDiagnostics
| getschema
~~~

### 8.2. Khám phá resource-specific table khi có

~~~kusto
AZKVAuditLogs
| where TimeGenerated >= ago(1h)
| take 10
~~~

**Không chạy trên workspace không có bảng này.** Nếu query lỗi table-not-found, xác minh diagnostic mode và destination; không suy rằng vault chưa có truy cập.

### 8.3. Các thuộc tính cần điều tra

| Nhóm field | Ý nghĩa | Cảnh báo |
|---|---|---|
| TimeGenerated | Thời điểm event | Ingestion delay và UTC |
| ResourceId / _ResourceId | Vault tương ứng | Chọn đúng vault để tránh gộp |
| OperationName | SecretGet/SecretList/SecretSet... | Cách đặt tên tùy schema |
| ResultType/ResultSignature/status | Success/403/404/429... | Phải xem field thực |
| CallerIPAddress | Nguồn gọi qua NAT/proxy | Không chắc là địa chỉ end user |
| Identity claims, oid/appid | Principal gọi data plane | Có thể thiếu trong một số records |
| RequestUri | Đường dẫn secret | Metadata nhạy cảm |
| Correlation/request ID | Liên kết điều tra | Không phải mọi tầng dùng chung ID |
| Duration/latency | Performance | Phân biệt client/server timings |

Ví dụ JSON **chuẩn hóa do bài học tự đặt**, không phải schema chính thức:

~~~json
{
  "timeUtc": "2026-11-20T04:30:00Z",
  "vault": "kv-orders-prod-example",
  "operation": "SecretGet",
  "statusCode": 403,
  "result": "Forbidden",
  "principalId": "example-principal-object-id",
  "callerIp": "198.51.100.20",
  "requestId": "example-request-id"
}
~~~

Những trường như **URI, IP, secret name và identity** phải được bảo vệ dù bản thân secret value không nằm trong audit logs.

## 9. Truy vấn KQL cho data-plane audit

Các truy vấn sau áp dụng cho **AzureDiagnostics** khi có các cột tương ứng. Với resource-specific table, đối chiếu schema rồi sửa table/fields; không thay tên bảng một cách mù quáng.

### 9.1. Phân bố operations trong 24 giờ

~~~kusto
AzureDiagnostics
| where TimeGenerated >= ago(24h)
| where ResourceProvider =~ "MICROSOFT.KEYVAULT"
| where Category =~ "AuditEvent"
| summarize Requests = count() by OperationName
| order by Requests desc
~~~

### 9.2. Kết quả và IP nguồn

~~~kusto
AzureDiagnostics
| where TimeGenerated >= ago(24h)
| where ResourceProvider =~ "MICROSOFT.KEYVAULT"
| where Category =~ "AuditEvent"
| extend Result = strcat(
    tostring(column_ifexists("ResultType", "")), " ",
    tostring(column_ifexists("ResultSignature", "")))
| extend Caller = tostring(
    column_ifexists("CallerIPAddress", ""))
| summarize Requests = count() by OperationName, Result, Caller
| order by Requests desc
~~~

Result type có thể chứa text hoặc mã; nếu cần numeric HTTP status, xác minh cột trong một event thật. **Không coi một kết quả dạng status text là xác suất hoặc mức độ rủi ro.**

### 9.3. Đỉnh request theo giờ

~~~kusto
AzureDiagnostics
| where TimeGenerated >= ago(7d)
| where ResourceProvider =~ "MICROSOFT.KEYVAULT"
| where Category =~ "AuditEvent"
| summarize Calls = count()
    by bin(TimeGenerated, 1h), OperationName
| order by TimeGenerated asc
~~~

Biểu đồ này giúp đối chiếu deployment, scale-out và rotation schedule. Đỉnh sau deployment có thể bình thường; đỉnh từ principal mới không có change ticket là một tín hiệu cần điều tra.

### 9.4. Lọc các dấu hiệu 401/403

~~~kusto
AzureDiagnostics
| where TimeGenerated >= ago(24h)
| where ResourceProvider =~ "MICROSOFT.KEYVAULT"
| where Category =~ "AuditEvent"
| extend Outcome = strcat(
    tostring(column_ifexists("ResultType", "")), " ",
    tostring(column_ifexists("ResultSignature", "")))
| where Outcome has_any ("Forbidden", "Unauthorized", "401", "403")
| project TimeGenerated, ResourceId, OperationName,
          Outcome, CallerIPAddress
| order by TimeGenerated desc
~~~

Đây là bước điều tra dựa trên text representation. Nếu status ở numeric field khác, query cần thay bằng tên field thực. Không kết luận “không có 403” chỉ vì schema không có từ Forbidden.

### 9.5. Theo dõi một secret khi schema có request URI

~~~kusto
let TargetSecret = "orders-payment-api-key";
AzureDiagnostics
| where TimeGenerated >= ago(24h)
| where ResourceProvider =~ "MICROSOFT.KEYVAULT"
| where Category =~ "AuditEvent"
| extend Path = tostring(
    column_ifexists("requestUri_s", ""))
| where Path has TargetSecret
| project TimeGenerated, OperationName, Path, ResultType
| order by TimeGenerated desc
~~~

**Nếu Path trống**, có thể bảng không có cột requestUri_s hoặc cách lưu khác. Phải inspect schema; một query rỗng không chứng minh secret chưa từng được đọc.

### 9.6. Đọc principal có điều kiện

Các claims có thể là cột chuyên biệt hoặc JSON/dynamic field. Nếu workspace dùng cột identity_claim_oid_g, có thể khám phá:

~~~kusto
AzureDiagnostics
| where TimeGenerated >= ago(24h)
| where ResourceProvider =~ "MICROSOFT.KEYVAULT"
| where Category =~ "AuditEvent"
| extend Principal = tostring(
    column_ifexists("identity_claim_oid_g", ""))
| summarize Calls = count() by Principal, OperationName
| order by Calls desc
~~~

Nếu Principal rỗng cho đa số events, **không kết luận anonymous access**. Cần xem trường identity tương đương trong actual schema và client auth context.

## 10. Activity Log và role assignment events

**AzureActivity** ở Log Analytics chỉ có nếu Activity Log được route đến workspace. Nếu không, dùng Azure Portal Activity Log hoặc destination hiện tại.

### 10.1. Thay đổi Key Vault resource

~~~kusto
AzureActivity
| where TimeGenerated >= ago(7d)
| where ResourceProviderValue =~ "MICROSOFT.KEYVAULT"
| project TimeGenerated, OperationNameValue,
          ActivityStatusValue, Caller, ResourceId, CorrelationId
| order by TimeGenerated desc
~~~

### 10.2. Thay đổi Azure RBAC role assignments

~~~kusto
AzureActivity
| where TimeGenerated >= ago(7d)
| where OperationNameValue has "roleAssignments"
| project TimeGenerated, OperationNameValue,
          ActivityStatusValue, Caller, ResourceId, CorrelationId
| order by TimeGenerated desc
~~~

Role assignment thường thuộc **Microsoft.Authorization** và có thể ghi ở scope khác vault. Chỉ lọc provider Key Vault sẽ **bỏ sót IAM changes**. Cần xem scope thực: subscription, resource group, vault hoặc secret.

### 10.3. Tạo timeline có chứng cứ

~~~text
04:05 UTC  Role assignment created for principal X
04:06 UTC  SecretList from principal X
04:07 UTC  SecretGet for secret Y
04:09 UTC  Partner API anomaly observed
04:15 UTC  SOC acknowledges alert
~~~

Đây là ví dụ giả định. Không mặc định hai events xảy ra gần nhau chứng minh causality: phải kiểm tra **principal ID, role scope, time, log ingestion lag, request details và partner telemetry**.

### 10.4. Không suy từ IP đơn lẻ

Một Caller IP có thể là NAT/firewall shared egress của nhiều pods/instances. Địa chỉ IP lạ có thể hợp lệ nếu workload chuyển VNet/NAT sau deployment; địa chỉ IP quen thuộc vẫn có thể bị attacker dùng từ compromised host. Luôn kết hợp IP với identity, service, operation, time và network telemetry.

## 11. Ghép chứng cứ end-to-end: WHO–WHAT–WHEN–WHERE–RESULT

Một investigator không nên dựa vào một screenshot role assignment hoặc một dòng 403 duy nhất. Hãy lập bảng:

| Câu hỏi | Bằng chứng cần tìm |
|---|---|
| **WHO** | Principal object ID, app/client ID, tenant, credential source |
| **WHAT** | SecretGet/List/Set/Delete, secret name/version nếu phù hợp |
| **WHEN** | UTC timestamps, token validity, ingestion delay |
| **WHERE** | Vault resource ID, region, caller IP/NAT, network route |
| **RESULT** | Final HTTP status, service error code, request ID, latency |
| **WHY** | Deployment, startup, refresh, approved rotation hoặc hoạt động bất thường |
| **FOLLOW-ON** | Partner API đã sử dụng key chưa, có rò dữ liệu không |

### 11.1. Cùng một HTTP request qua nhiều tầng

~~~mermaid
sequenceDiagram
    participant U as User/Job trigger
    participant APP as Java Orders API
    participant EN as Entra ID
    participant KV as Key Vault
    participant P as Partner API
    U->>APP: Business call, traceId A
    APP->>EN: Acquire token (if needed)
    EN-->>APP: Access token
    APP->>KV: GET secret, dependency span B
    KV-->>APP: Status + x-ms-request-id C
    APP->>P: Business API using secret
    P-->>APP: Partner response
    APP-->>U: Business outcome
~~~

Trace ID của HTTP request, Key Vault request ID và Entra token issuance identifiers **không nhất thiết giống nhau**. Application telemetry nên ghi **service dependency, UTC time, sanitized secret alias, operation, status, latency và request ID** để join dữ liệu theo thời gian/danh tính.

### 11.2. Key Vault thấy app principal, không luôn thấy user cuối

Nếu Orders API dùng **một managed identity** để đọc secret, Key Vault AuditEvent phản ánh app principal chứ không phải từng người gọi API. Một SecretGet ở startup có thể phục vụ hàng nghìn requests thông qua cache. Muốn nối đến user end-to-end phải có **application traces** với data minimization, không suy user từ Key Vault log.

### 11.3. Phát hiện bất thường có baseline

Nên xây baseline theo:

- Vault và secret name/classification.
- Principal/managed identity được phê duyệt.
- Operation types: SecretGet vs SecretList vs SecretSet/Delete.
- Nguồn network/IP/VNet expected.
- Giờ hoạt động, time zone và rotation window.
- Số GET khi startup, scale-out và refresh.
- Những version/secret không còn dùng.

Một đỉnh SecretGet sau scale-out có thể hợp lệ; SecretList do workload chỉ cần Get theo tên có thể đáng ngờ. **Không tự phân loại chỉ dựa số request**.

## 12. Chẩn đoán HTTP 401: authentication, token và bearer challenge

### 12.1. 401 không luôn là một sự cố

Một số Key Vault clients có **challenge-based authentication**. Request đầu có thể nhận HTTP **401** kèm **WWW-Authenticate**, SDK lấy token thích hợp rồi thực hiện lại thành công. Vì vậy **một 401 trong dependency trace không đủ kết luận app hỏng hoặc có kẻ tấn công**. Cần xem **final outcome**, chuỗi requests, SDK version và thời điểm credential acquisition.

### 12.2. Những nguyên nhân cần phân biệt

- Token hết hạn hoặc clock skew ảnh hưởng validity.
- Access token không dành cho Key Vault resource/audience.
- App dùng tenant sai.
- Managed identity chưa bật hoặc không available ở runtime.
- User-assigned identity có **client ID** sai.
- DefaultAzureCredential chọn environment credential vô tình cấu hình từ CI/dev.
- AKS Workload ID issuer/subject/audience federation không khớp.
- Proxy/TLS/network làm lỗi token acquisition từ Entra.
- Client library quá cũ hoặc auth handshake không đúng.

### 12.3. Runbook 401

1. Xác định **service trả 401**: Key Vault hay partner/payment API.
2. Lấy status, service error code, request ID, time và trace ID; không lưu raw JWT.
3. Kiểm tra Java runtime ở local, App Service, VM, Container Apps hay AKS.
4. Kiểm tra loại credential thực mà SDK chọn.
5. Kiểm tra principal/client/tenant từ cấu hình được phê duyệt, không tin tên environment variable đơn lẻ.
6. Xem managed identity/workload identity có được bật và identity nào được bind.
7. Kiểm tra token scope/resource khi code tự xây TokenCredential; thông thường SDK xử lý.
8. Kiểm tra đồng hồ, proxy, DNS/TLS, token endpoint.
9. Nếu 401 challenge rồi Get thành công, không lập incident chỉ từ challenge.
10. Khi authentication thành công, tiếp tục bước **authorization** để giải thích 403 nếu còn.

### 12.4. Không debug bằng cách log token

Access token/bearer token là credential. Không copy toàn bộ vào Jira, chat, Git, Java exception, browser console hoặc Application Insights custom dimension. Nếu phải xem claims để điều tra, dùng công cụ/kênh được phê duyệt, tối thiểu hóa dữ liệu và bảo vệ retention.

## 13. Chẩn đoán HTTP 403: RBAC, access policy hay mạng?

### 13.1. 403 là lớp lỗi phổ biến nhất

**Forbidden** có thể đến từ nhiều nguyên nhân:

| Nhóm | Ví dụ | Cách kiểm tra |
|---|---|---|
| Data-plane RBAC | App thiếu **Key Vault Secrets User** | Role/scope và permission model |
| Access policy | Vault dùng legacy access policy nhưng app chưa có Get | Vault access policy list |
| Sai principal | Role cho managed identity A nhưng app chạy identity B | Object ID/client ID thực |
| Sai scope | Role gán ở vault khác/resource group khác | Full resource IDs |
| Chờ propagation | Role vừa được cấp | Audit assignment và thời gian |
| Network restriction | Public firewall/IP/VNet/Private Endpoint rule chặn | Error details, DNS, routes |
| Disabled secret/version | Secret lifecycle không cho đọc | Secret properties và service error |
| Authorization boundary khác | Vault/tenant/config khác dự định | Endpoint, subscription, tenant |

Một số network restrictions có thể trả HTTP 403, nên **không nên chỉ nhìn mã 403 rồi cấp Owner**.

### 13.2. Runbook có thứ tự

1. Lấy **final HTTP response**, Key Vault error code/message đã sanitize và request ID.
2. Kiểm tra **vault URI** và tenant/environment.
3. Kiểm tra token principal; nó có đúng app managed identity không?
4. Kiểm tra **enableRbacAuthorization** và access policy mode của vault.
5. Nếu dùng RBAC, kiểm tra role **Key Vault Secrets User** ở scope vault/secret phù hợp.
6. Nếu legacy access policy, kiểm tra permissions **get** và **list** riêng; Get không mặc nhiên cần List.
7. Kiểm tra public network access, firewall, allowed networks/IP, Private Endpoint approval.
8. Trên host/pod thực, kiểm tra DNS và network path tới vault FQDN.
9. Nếu role mới gán, chờ propagation theo runbook và retest trên principal chính xác.
10. Kiểm tra secret name/version và lifecycle status.
11. Tương quan audit event Key Vault với Azure Activity Log role/network changes.
12. Sau khi sửa, kiểm thử thành công bằng một **secret demo**, không in value.

### 13.3. Azure CLI kiểm tra RBAC read-only

~~~bash
VAULT="<approved-vault-name>"

VAULT_ID=$(az keyvault show \
  --name "$VAULT" \
  --query id --output tsv)

az keyvault show \
  --name "$VAULT" \
  --query "{rbac:properties.enableRbacAuthorization,publicNetworkAccess:properties.publicNetworkAccess}" \
  --output json

az role assignment list \
  --assignee "<application-principal-object-id>" \
  --scope "$VAULT_ID" \
  --include-inherited \
  --output table
~~~

**Không bao giờ chạy role assignment với placeholder** hoặc một object ID đoán từ tên ứng dụng. Công cụ read-only vẫn có thể yêu cầu quyền đọc IAM; thiếu quyền xem assignments không chứng minh role không tồn tại.

### 13.4. App role và User role là hai thứ khác nhau

Developer có thể đã được cấp **Secrets Officer** để tạo secret lab, nhưng Orders API **không chạy bằng developer identity** ở production. App Service system-assigned identity, user-assigned identity và AKS Workload ID đều là principal khác, cần role assignment riêng.

### 13.5. Permission scope và propagation

Role at subscription/resource group có thể tạo blast radius rộng; role at vault (hoặc secret scope theo khả năng hỗ trợ) thường hẹp hơn. Thu hồi role trong incident có thể mất một thời gian mới có hiệu lực trên mọi access path. Đặt thêm network containment, rotate credential và quan sát logs để xác nhận chặn.

## 14. 404, 429 và lỗi vận hành khác

### 14.1. 404: sai tên/version hoặc lifecycle

Một **404** có thể xuất hiện vì:

- Sai vault URI hoặc secret name.
- Secret chưa được tạo hoặc đã bị xóa.
- Application pin một version ID không còn.
- Secret đang ở trạng thái không sẵn sàng theo lifecycle/API.
- Một wrapper của ứng dụng chuyển một lỗi khác thành thông báo “not found”.

Runbook:

1. Kiểm tra vault URI của đúng environment.
2. Kiểm tra secret name chính xác trong config.
3. Kiểm tra version-pinned hay versionless fetch.
4. Kiểm tra soft-delete/recovery state bằng identity quản trị được phép.
5. Kiểm tra latest version enabled/notBefore/expiresOn phù hợp.
6. Không tự tạo secret rỗng hoặc hard-code backup khi Get thất bại.
7. Nếu phải phục hồi, tuân thủ approval và audit của secret owner.

**Không mặc định disabled/expired luôn trả 404**; error type có thể khác. Đọc service error code thực.

### 14.2. 429: throttling

Key Vault có giới hạn theo operation/tier/scope. Nguyên nhân phổ biến:

- Mỗi HTTP request gọi SecretGet thay vì dùng cache.
- Hàng trăm instances restart cùng lúc và GET hàng loạt.
- Rotation/inventory job LIST/GET quá nhiều.
- SDK retry + app retry + gateway retry bị chồng.
- Một vault bị dùng chung cho quá nhiều workloads không được điều tiết.

Biện pháp:

1. Đo requests/sec theo operation/principal.
2. Đọc HTTP status và Retry-After khi có.
3. Exponential backoff + jitter, bounded concurrency, retry budget.
4. Cache secret có **TTL và rotation policy** được duyệt.
5. Không dùng liveness probe gọi Key Vault thường xuyên.
6. Scale/cấu trúc vaults theo quota/baseline thực, không “cấp Owner”.
7. Báo alert nếu 429 kéo dài và các app không thể khởi động.

### 14.3. 5xx và timeout

- 5xx có thể là sự cố dịch vụ hoặc dependency.
- Timeout/DNS/TLS có thể phát sinh ở app network/Private Endpoint/proxy trước khi Key Vault xử lý.
- Một request không đến Key Vault có thể **không tạo audit event** data-plane tương ứng.
- Không tự suy “không có AuditEvent = không có request”; có thể thất bại trước data plane hoặc logs đang trễ/mất.
- Kiểm tra Azure Service Health, client telemetry, DNS/firewall traces và logs ingestion.

### 14.4. Lỗi partner API khác lỗi Key Vault

~~~text
Key Vault GET = 200
Orders API caches key version V1
Partner API = 401 Unauthorized
~~~

Trường hợp này **Key Vault authentication thành công**, nhưng partner key có thể đã bị revoke hoặc không phù hợp. Phải kiểm tra **partner credential rotation**, application cache và downstream auth, không đổi role Key Vault.

## 15. Mạng riêng: firewall, Private Endpoint và DNS

### 15.1. Key Vault FQDN không đổi

Client tiếp tục gọi:

~~~text
https://<vault-name>.vault.azure.net/
~~~

Khi có Private Endpoint, DNS của môi trường riêng phải đưa hostname qua private network theo cấu hình. Private DNS zone của Key Vault thường liên quan **privatelink.vaultcore.azure.net**.

**Không đổi vault URL thành raw private IP** và không tắt TLS hostname verification.

### 15.2. Azure App Service VNet integration

- **VNet Integration** là outbound access từ App Service vào VNet.
- **Key Vault Private Endpoint** là private endpoint để truy cập vault.
- **App Service Private Endpoint** thường là inbound private access tới app; không thay outbound VNet Integration.
- DNS, firewall, route tables và NSG cần đúng.
- Entra token acquisition có network requirements khác với đường đi Key Vault data plane.

### 15.3. AKS networking

Trong AKS:

- Pod outbound DNS phải phân giải vault FQDN đúng.
- CNI/network policies, NAT/firewall, route rules có thể chặn egress.
- ServiceAccount/Workload ID tạo identity riêng; **network reachable không cấp RBAC**.
- Một node/pod có thể dùng nhiều egress IP, nên CallerIPAddress trong audit phải được đối chiếu với NAT setup.

### 15.4. Sơ đồ mạng

~~~mermaid
flowchart LR
    POD["App Service / AKS<br/>Java workload"] --> DNS["VNet DNS resolver"]
    DNS --> PE["Key Vault Private Endpoint<br/>private IP"]
    PE --> KV["Key Vault"]
    POD --> ID["Microsoft Entra token endpoint"]
    AUTH["Key Vault data-plane RBAC"] --> KV
    LOG["Key Vault AuditEvent"] --> SOC["Log Analytics / SOC"]
    KV --> LOG
~~~

### 15.5. Checklist DNS/network

1. Xác nhận vault public network access và firewall policy.
2. Từ **đúng host/pod**, resolve **vault-name.vault.azure.net**.
3. Kiểm tra private DNS zone link và forwarding resolvers.
4. Kiểm tra Private Endpoint connection approval/status.
5. Kiểm tra route/firewall/NSG/proxy egress.
6. Kiểm tra TLS certificate validation và hostname.
7. Dùng sanitized dependency trace để biết lỗi trước hay sau HTTP response.
8. Khi network thông, kiểm tra identity và data role.
9. Không mở public network toàn cầu để giải quyết một lỗi DNS.

### 15.6. “Trusted services” không có nghĩa mọi workload được phép

Một số Azure services có cơ chế bypass/exception được công bố theo cấu hình, nhưng không nên suy tất cả app chạy trên Azure thuộc trusted services. Cần kiểm tra danh sách/điều kiện chính thức và ưu tiên private connectivity theo policy.

## 16. Java SDK: đọc secret và log trạng thái an toàn

Một ứng dụng Java thường dùng **com.azure:azure-security-keyvault-secrets** kết hợp **com.azure:azure-identity**.

### 16.1. Maven dependencies

~~~xml
<dependencies>
  <!-- Sử dụng Azure SDK BOM hoặc pin versions phù hợp project. -->
  <dependency>
    <groupId>com.azure</groupId>
    <artifactId>azure-security-keyvault-secrets</artifactId>
  </dependency>
  <dependency>
    <groupId>com.azure</groupId>
    <artifactId>azure-identity</artifactId>
  </dependency>
</dependencies>
~~~

Đây là **POM fragment**, cần Azure SDK BOM/explicit versions, JDK và plugin/build config của project. Không giả vờ các placeholders đã được build kiểm thử.

### 16.2. Java 17 SecretClient

~~~java
package com.example.orders.security;

import com.azure.core.credential.TokenCredential;
import com.azure.core.exception.HttpResponseException;
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.security.keyvault.secrets.SecretClient;
import com.azure.security.keyvault.secrets.SecretClientBuilder;
import com.azure.security.keyvault.secrets.models.KeyVaultSecret;

public final class KeyVaultAuditDemo {
    private KeyVaultAuditDemo() {}

    public static void main(String[] args) {
        String vaultUrl = requiredEnv("KEY_VAULT_URL");
        String secretName = requiredEnv("SECRET_NAME");

        TokenCredential credential =
            new DefaultAzureCredentialBuilder().build();

        SecretClient client = new SecretClientBuilder()
            .vaultUrl(vaultUrl)
            .credential(credential)
            .buildClient();

        try {
            KeyVaultSecret secret = client.getSecret(secretName);
            String value = secret.getValue();

            if (value == null || value.isBlank()) {
                throw new IllegalStateException(
                    "Required secret unavailable");
            }

            // Dùng value trong server-side component phù hợp.
            // KHÔNG log/in/serialize secret value.
            System.out.println(
                "Secret dependency available; value not displayed.");

        } catch (HttpResponseException error) {
            int status = error.getResponse() == null
                ? -1 : error.getResponse().getStatusCode();

            // Chỉ status + sanitized correlation,
            // KHÔNG in body chứa credential.
            System.err.println(
                "Key Vault dependency failed; status=" + status);
            throw error;
        }
    }

    private static String requiredEnv(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                "Missing required environment variable " + name);
        }
        return value;
    }
}
~~~

Code minh họa thành công nhưng **không hiển thị secret value**. Hai biến môi trường chỉ chứa vault URL và secret name, không chứa credential. SDK có thể có exception loại khác như token acquisition exception/transport exception; code production cần xử lý riêng và không log error body bừa bãi.

### 16.3. Những điều production cần bổ sung

- **Singleton SecretClient/TokenCredential** qua dependency injection thay vì tạo mỗi request.
- Timeout, cancellation, bounded SDK retry theo 429/5xx và policy.
- Sanitized structured logs với dependency name, status, operation, duration, correlation.
- Cache/refresh secret theo rotation contract, không cache vô hạn.
- Alert khi getSecret thất bại tại startup; readiness rõ.
- Không cấu hình SDK HTTP wire logging cho **request/response bodies**, headers chứa secrets/token.
- Không đưa secret value vào exception, thread name, metric label, config dump hoặc traces.
- Test user-assigned identity/AKS workload federation khi áp dụng.
- Tách 401 từ Key Vault với 401 từ partner API trong OpenTelemetry service name.

### 16.4. Java String và memory

SecretClient trả secret value ở dạng **String**. Java String immutable, không có phương thức zeroize bảo đảm xóa ngay bản đã tạo. Giảm số bản sao, phạm vi sống, tránh crash dumps và không serialize; nếu Azure service hỗ trợ Entra/managed identity trực tiếp thì ưu tiên **không dùng static secret**.

### 16.5. Chẩn đoán DefaultAzureCredential

Ở local, SDK có thể dùng developer tool credential; trên Azure có thể dùng managed identity. **Cùng một code path không đồng nghĩa cùng một principal**. Nếu có environment variables mang credentials của service principal, credential chain có thể chọn identity khác dự định tùy SDK version.

Với production nhạy cảm, cân nhắc explicit **ManagedIdentityCredential** hoặc **WorkloadIdentityCredential** theo runtime, pin SDK version và test principal thực. Khi dùng user-assigned identity, kiểm tra **client ID** được chỉ định chính xác và phân biệt với **principal object ID** khi gán role.

### 16.6. Không tự nới quyền khi xử lý exception

Anti-pattern:

~~~java
// SAI: cố sửa RBAC hoặc chọn admin credential
// khi SecretGet trả 403, rồi retry vô hạn.
~~~

Runtime reader phải không có permission sửa role assignments. Thay role là thao tác của platform/IAM team với approval, audit và rollback, không phải cơ chế tự phục hồi của app.

## 17. Khi audit phát hiện đọc secret bất thường

Một phát hiện có thể là:

~~~text
Alert: successful SecretGet spike
Vault: kv-orders-prod-example
Time: 02:05–02:20 UTC
Principal: new service-principal
Caller IP: unexpected egress
Operation: SecretGet and SecretList
~~~

Đây là ví dụ giả định; SOC cần so với allowlist deployments, rotation window và network inventory. Một **Get thành công** là dấu hiệu truy cập được xử lý, không tự chứng minh dữ liệu đã exfiltrate.

### 17.1. Cấp độ xử lý

| Tình huống | Phản ứng khởi điểm |
|---|---|
| Known app scale-out, nhiều GET lúc startup | Đối chiếu deployment, baseline, kiểm tra cache |
| Role mới và GET từ principal không có change ticket | Mở security investigation |
| GET secret nhạy cảm từ principal không được phê duyệt | Ưu tiên containment + incident |
| SecretList hàng loạt từ workload vốn chỉ Get theo name | Investigate intent và possible credential misuse |
| Partner key xuất hiện trong public logs/repository | Xem là potential credential exposure, rotate/revoke |
| Diagnostic settings bị tắt sát thời điểm GET | High-severity telemetry tampering signal |
| Xem log thấy 403 nhưng không có 200 | Có thể là probing hoặc misconfiguration, cần xác minh |

**Severity** phải dựa trên data classification, bằng chứng, blast radius và impact, không dựa một con số cố định cho mọi vault.

### 17.2. Quy trình TRIAGE

1. **Xác nhận alert:** Query log thật, xem UTC, ingestion delay, resource ID, status và operation.
2. **Đối chiếu principal:** object ID, app ID, tenant, owner, approved identity inventory.
3. **Đối chiếu change events:** deployment, role assignment, vault firewall, access policy, diagnostic setting changes.
4. **Đối chiếu network:** caller IP/NAT, VNet, Private Endpoint, egress route.
5. **Xác định secret scope:** những names/versions có thể đã truy xuất, không tải value chỉ để điều tra.
6. **Xác minh application path:** startup, refresh, inventory job hay business request.
7. **Tìm follow-on evidence:** partner API logs, app egress, CI secret scans, anomalous downstream actions.
8. **Đánh giá rủi ro:** credential bị đọc trái phép có còn dùng được không? Có môi trường/tenant nào liên quan?
9. **Escalate** theo playbook security khi principal hoặc secret nhạy cảm có khả năng compromised.
10. **Lưu chứng cứ và timeline** trước khi thao tác phá hủy dữ liệu/đổi config.

### 17.3. Điều không nên làm

- Không in secret value từ vault để “xem có bị thay không”.
- Không chia sẻ request logs/raw tokens qua kênh chat không được phê duyệt.
- Không xóa vault hay purge secret để “loại bỏ dấu vết”.
- Không cấp role mới rộng hơn chỉ để lấy thông tin điều tra.
- Không kết luận nguyên nhân từ IP đơn lẻ.
- Không vô hiệu hóa monitoring để giảm cảnh báo.
- Không chỉ xóa Key Vault secret mà bỏ qua secret ở partner hoặc cache trên app.

## 18. Incident runbook: nghi ngờ secret value bị lộ

Một credential có thể bị lộ qua repo, CI logs, client-side bundle, crash dump, APM traces, malicious insider hoặc một principal dùng Key Vault quá quyền. **Dù log AuditEvent không thấy bất thường, secret vẫn có thể đã bị lộ từ bản sao trước đó.**

### 18.1. Mục tiêu ứng cứu

- **Contain:** chặn đường truy cập trái phép hoặc giảm blast radius.
- **Preserve evidence:** giữ audit, identity, role/network và app/partner logs.
- **Revoke:** làm credential cũ không được hệ thống đích chấp nhận.
- **Rotate:** phát hành credential mới, chuyển ứng dụng an toàn.
- **Verify:** xác thực các workloads đã dùng key mới; kẻ tấn công không còn lợi dụng key cũ.
- **Learn:** khắc phục nguyên nhân, bổ sung detection và kiểm thử.

### 18.2. Một timeline ứng cứu

~~~mermaid
flowchart TD
    DET["Detect suspected exposure"] --> TRIAGE["Validate alert + classify secret"]
    TRIAGE --> EVID["Preserve logs, trace, change timeline"]
    EVID --> CON["Contain principal/network access"]
    CON --> NEW["Issue replacement credential at partner"]
    NEW --> KV["Set new Key Vault version"]
    KV --> CAN["Canary app uses new version"]
    CAN --> DEC{"Partner auth + business SLO OK?"}
    DEC -->|No| FIX["Repair/controlled rollback"]
    DEC -->|Yes| ROLL["Roll out all app instances"]
    ROLL --> REVOKE["Revoke old partner credential"]
    REVOKE --> VERIFY["Verify no unauthorized use, audit"]
    VERIFY --> RETRO["Post-incident review + tests"]
~~~

**Thứ tự tuyệt đối phụ thuộc mức độ khẩn cấp**: với credential đang bị khai thác, có thể cần revoke ngay trước khi canary sẵn sàng, chấp nhận gián đoạn. Khi có khả năng dual-key và đối tác hỗ trợ, một chuyển tiếp có kiểm soát giúp giảm downtime. Security incident commander quyết định theo risk.

### 18.3. Containment quyền và mạng

- Disable/quarantine compromised application deployment hoặc workload identity federation khi thích hợp.
- Thu hồi role/access policy cấp quyền quá mức.
- Vô hiệu hóa static credentials và rotate service-principal secrets/certificates nếu bị lộ.
- Thắt network path/firewall/Private Endpoint access theo policy.
- Kiểm tra quyền ở parent scopes (resource group/subscription) và role inheritance.
- Đối chiếu Entra sign-ins và application/infrastructure changes.
- **Không mặc định remove role có hiệu lực tức thì** vì token caches/propagation.

### 18.4. Rotation tại hệ thống đích mới là quyết định

Giả sử Key Vault chứa API key của đối tác thanh toán:

1. Tạo key mới **ở partner system**.
2. Kiểm tra key mới active theo API/token policy của partner.
3. Ghi key mới thành **secret version mới trong Key Vault**.
4. Cập nhật application cache/version reference bằng rollout có kiểm soát.
5. Test giao dịch demo/canary với key mới, không ghi raw key.
6. Revoke key cũ **ở partner**.
7. Theo dõi partner 401/403/abnormal usage và vault Get logs.
8. Đảm bảo không còn instances giữ old cached credential ngoài retention được duyệt.
9. Kiểm tra bản sao trong logs, source histories, snapshots, backups theo policy.

**Xóa hoặc disable secret trong Key Vault không tự vô hiệu hóa giá trị key đã được copy ra ngoài**. Nếu kẻ tấn công đã có API key, chỉ xóa bản trong vault không ngăn họ dùng nó tại partner.

### 18.5. Khi là database password

Khi secret là mật khẩu DB legacy:

- Thay password tại DB/identity authority.
- Cập nhật Key Vault version.
- Điều phối DB connection pool/lifetime và restart cần thiết.
- Dự kiến các kết nối cũ có thể còn sống theo DB auth/session semantics.
- Kiểm tra quyền SQL/Azure RBAC và audit connections.
- Chuyển sang Entra managed identity nếu hỗ trợ để giảm password sprawl.

### 18.6. Khi là certificate/private key

- Kiểm tra certificate issuance/CA policy, private key exportability.
- Nếu private key bị lộ, có thể cần revoke/reissue certificate và cập nhật trust/consumers.
- Với non-exportable Key Vault Key/HSM, việc ký bất thường không đồng nghĩa private key đã bị export; xem **key operation audit**, service permissions và cryptographic usage.
- Không áp cùng một playbook cho Secret, Key và Certificate nếu trust chain khác nhau.

### 18.7. Chứng minh kết thúc incident

Không đủ nói “đã tạo version mới”. Cần evidence:

- Tất cả active workloads dùng credential mới.
- Partner đã không còn nhận credential cũ.
- Quyền network/identity bất thường đã bị containment.
- Vault/partner logs không còn hoạt động trái phép sau cutover theo observation window.
- Monitoring được khôi phục/bảo vệ.
- Các artifacts có secret đã bị xử lý theo policy.
- Incident timeline/root cause/corrective actions được lưu và review.

## 19. Runbook: ứng dụng không thể đọc secret sau deployment

Một sự cố vận hành khác: release mới lên App Service bị **HTTP 403** và toàn bộ checkout trả 503.

### 19.1. Chẩn đoán dựa trên dependency chain

~~~text
Application startup
   |
   +-- Azure Identity TokenCredential?
   |      +-- Tenant / client ID / managed identity source
   |
   +-- Key Vault reachability?
   |      +-- Vault FQDN / DNS / firewall / private endpoint
   |
   +-- Key Vault authorization?
   |      +-- Permission model / principal / role scope
   |
   +-- Secret lifecycle?
   |      +-- Name / version / enabled / expiry
   |
   +-- Application binding?
          +-- Cache / env / dependency injection / partner key
~~~

### 19.2. Quy trình không phá dữ liệu

1. Kiểm tra application health/status trước deployment.
2. Xác minh lỗi từ **Key Vault**, không phải partner.
3. Dùng sanitized logs và Key Vault data-plane audit để tìm status, time.
4. Đối chiếu App Service/AKS identity với role assignments.
5. Kiểm tra tenant và vault URI của đúng environment.
6. Kiểm tra VNet/private DNS/firewall qua container/host tương ứng.
7. Kiểm tra last successful secret retrieval/version metadata.
8. Kiểm tra role propagation nếu vừa cấp.
9. Không dùng production secret value trong manual diagnostics.
10. Rollback binary/config hoặc khóa feature phụ thuộc nếu an toàn.
11. Khi sửa, test bằng minimal allowed SecretGet; giám sát dependency p95/availability.
12. Ghi regression test/infrastructure assertion.

### 19.3. Fail-fast hay last-known-good?

| Trạng thái | Hành vi có thể chấp nhận |
|---|---|
| Instance mới chưa từng lấy credential | Không phục vụ route phụ thuộc secret; fail startup/readiness |
| Instance đang có cached key còn valid | Có thể tiếp tục trong stale window được policy chấp nhận |
| Credential nghi lộ/revoked | Fail closed; không giữ old cached key vì availability |
| Rotation tới version mới nhưng partner lỗi | Canary rollback/dual-key theo runbook |
| Key Vault 429 ngắn hạn | Backoff/jitter; không GET per request |
| Key Vault outage kéo dài | Escalate, DR/runbook và risk decision |

Đừng hard-code một backup key vào JAR hoặc silently dùng credential dev để cứu production.

### 19.4. Readiness/liveness

Kubernetes/App Service health probes không nên gọi **Key Vault Get mỗi vài giây**. Nếu vault outage, liveness restart tất cả instances có thể làm bùng phát GET và 429. Readiness phản ánh app có đủ config/credential an toàn phục vụ workload hay không; liveness phản ánh process không bị deadlock.

## 20. Secret rotation và audit phiên bản

### 20.1. Một quá trình rotation tiêu chuẩn

~~~text
V1 active at partner + Key Vault
→ V2 created at partner
→ Key Vault Set creates V2 secret version
→ Canary uses V2 (optionally pinned)
→ Validate partner authentication and business outcomes
→ Roll out V2 to all instances
→ Revoke partner V1
→ Audit, close rotation ticket
~~~

Trong audit timeline có thể thấy SecretSet/SecretGet/List hoặc metadata operations tùy SDK/operation. Nhưng **SecretGet từ ứng dụng không chứng minh nó sử dụng đúng version trong cache**; cần app telemetry version metadata theo quy định.

### 20.2. Versionless vs version-pinned

- **Versionless GET** thường lấy version hiện hành theo service semantics, nhưng app-side cache/refresh có thể giữ old value.
- **Version-pinned GET** hỗ trợ reproducible rollout; app sẽ không tự chuyển V2 khi pin V1.
- **Secret expiry/notBefore/disabled** ảnh hưởng availability; metadata cần được kiểm tra.
- Không đặt ExpiresOn rồi tin đối tác đã rotate key.
- Khi dùng App Service Key Vault references hoặc Azure App Configuration references, phải hiểu **refresh/cache semantics riêng**.

### 20.3. Log rotation không lộ value

Metadata có thể log:

~~~json
{
  "event": "SECRET_ROTATION_APPLIED",
  "vaultAlias": "kv-orders-prod",
  "secretAlias": "payment-key",
  "versionHash": "sha256-demo-prefix",
  "result": "SUCCESS",
  "timeUtc": "2026-11-20T05:30:00Z"
}
~~~

Đây là telemetry giả định; **versionHash** không phải hash của secret value, mà chỉ là mã đại diện cho **version ID** đã được ẩn/băm khi cần. Không log plaintext secret, signed JWT, token, partner headers hoặc key material.

### 20.4. Audit thấy Set nhưng app vẫn lỗi?

Có thể Key Vault version mới được tạo nhưng:

- Partner chưa kích hoạt key.
- App đang pin version cũ.
- Một số instances cache secret cũ.
- Vault role/network thay đổi và Get bị chặn.
- New version bị disabled/notBefore.
- HTTP client đã khởi tạo với old Authorization header.
- Downstream partner API từ chối quyền khác ngoài API key.

Do đó rotation phải đo đồng thời **vault audit, app configuration, partner API outcomes**.

## 21. Soft-delete, recover, purge và bảo toàn chứng cứ

Key Vault có **soft-delete** và có thể bật **purge protection** theo loại vault/policy. Cần hiểu:

| Hành động | Ý nghĩa | Audit/incident consideration |
|---|---|---|
| Delete Secret | Secret chuyển sang deleted state theo service lifecycle | Có thể cần recovery; đừng xóa trong incident vô cớ |
| Recover | Khôi phục nếu còn trong retention và có quyền | Cần approval/audit |
| Purge | Xóa vĩnh viễn nếu được phép | Không thể khôi phục; có thể bị purge protection chặn |
| Rotate | Tạo credential/version mới và chuyển consumers | Không xóa bản copy tại partner |
| Disable | Không cho một version được sử dụng theo policy | Không revoke bản key ở external system |
| Backup/restore | Theo Key Vault API và giới hạn tương ứng | Không lấy diagnostic logs làm secret backup |

**Không chạy Purge trong lab hoặc production** chỉ để tái dùng tên. Các thao tác xóa/phục hồi là thay đổi data-plane nhạy cảm, cần audit/approvals.

### 21.1. Evidence preservation

Trong security incident:

- Giữ audit records, Activity Log, identity logs, relevant app/partner logs.
- Xuất logs theo approved chain of custody; tính hash cho files export nếu quy trình yêu cầu.
- Tránh chia sẻ không kiểm soát names/URIs/IPs có thể nhạy cảm.
- Không tắt retention hoặc xóa settings trước khi incident commander cho phép.
- Audit quyền đọc logs; các log readers cũng có thể là privileged.
- Bảo vệ compliance/regulatory hold nếu được áp dụng.

### 21.2. Bí mật đã bị đọc không thể “gọi lại”

Một người có quyền Get có thể đã lấy secret value ra ngoài. **Không có tính năng Key Vault nào thu hồi những bytes đã đọc từ máy người nhận**. Biện pháp khắc phục thực chất là revoke/rotate tại nơi secret được dùng và hạn chế tất cả các đường lấy bản cũ.

## 22. Detection engineering: alert đúng, giảm false positives

### 22.1. Không alert trên mọi GET

Một ứng dụng có 100 instances refresh một secret mỗi giờ có thể tạo 100 GET gần đồng thời. Sau một deployment, vài trăm GET có thể bình thường. Thay vì cảnh báo tất cả:

- Xây baseline riêng theo vault/principal/operation/time.
- Allowlist những identities được duyệt và secret access patterns.
- Theo dõi **new principal** hoặc caller network bất thường.
- Theo dõi **GET/LIST ratio** và rate thay đổi.
- Theo dõi **write/delete/purge operations** ngoài change windows.
- Correlate role assignment với subsequent data-plane access.
- Theo dõi diagnostic settings changes như tín hiệu tampering.

### 22.2. Một detection giả định

~~~text
Trigger:
  Principal mới chưa nằm trong approved inventory
  AND có SecretGet thành công tới vault production
  AND không có deployment/rotation change ticket
Window:
  15 phút
Severity:
  High nếu secret classified critical
Actions:
  Create security incident
  Preserve Key Vault / Activity / Entra logs
  Verify principal and network
  Request containment approval
~~~

Đây là **quy tắc ví dụ**, không phải Azure Alert Rule đã được triển khai. Một detection cần suppression, exceptions, seasonality và incident ownership.

### 22.3. Failed access có thể là lỗi triển khai

Nhiều 403 sau rolling release có thể do:

- Role gán sai principal.
- Managed identity chưa enable.
- Access policy vs Azure RBAC mismatch.
- Private DNS chưa ổn.
- App gọi secret khác tên.

Do đó alert nên bao gồm deployment correlation và số instances bị ảnh hưởng để phân loại **SRE incident** hoặc **security probing**.

### 22.4. Alert về log pipeline

Cảnh báo data-plane audit mất:

- Diagnostic settings bị xóa/tắt hoặc destination bị đổi.
- Workspace ingestion không còn nhận category AuditEvent trong thời gian bất thường.
- Event Hubs/Storage export thất bại theo monitoring nếu có.
- Permission/log retention thay đổi ngoài approval.

**Không dùng vắng events một mình** làm bằng chứng log bị tấn công; vault có thể thực sự không có traffic. Kết hợp service request metrics, heartbeats lab nếu được phép và Activity Log changes.

## 23. Managed identity, service principal và workload identity trong audit

### 23.1. Các định danh dễ nhầm

| Định danh | Ý nghĩa | Dùng để |
|---|---|---|
| **Tenant ID** | Microsoft Entra directory | Xác định nơi quản lý identity |
| **Application (client) ID** | Application/client identifier | Chọn user-assigned managed identity hoặc ứng dụng |
| **Principal object ID** | Object của service principal/managed identity trong directory | Azure RBAC role assignment và điều tra principal |
| **Resource ID** | Azure ARM path | Xác định vault/scope có role |
| **Secret name** | Tên bí mật | Get/list/rotate theo ứng dụng |
| **Secret version** | ID phiên bản | Phân tích rotation/rollback |
| **Key Vault request ID** | Identifier của request ở service | Correlation data-plane logs |

Đừng gán role cho **client ID** khi công cụ yêu cầu **principal object ID**, và không xem subscription ID như tenant ID.

### 23.2. App Service system-assigned identity

- Bật identity trên đúng App Service.
- Ghi **principal object ID** trong inventory và IaC output an toàn.
- Gán **Key Vault Secrets User** theo scope cần.
- Kiểm tra app thực sự dùng managed identity ấy, không dùng environment service principal.
- Bảo đảm outbound network tới vault.
- Khi ứng dụng được xóa/tạo lại, **system-assigned principal có thể thay**, role cũ không tự gán cho principal mới.
- Audit lịch sử phải hiểu principal cũ và principal mới của cùng một service logical name.

### 23.3. User-assigned managed identity

- Identity là một Azure resource riêng, có client ID và principal ID.
- Một workload có nhiều identities có thể cần cấu hình explicit client ID.
- Không mặc định SDK sẽ chọn identity đúng nếu environment có nhiều options.
- Role phải được gán cho user-assigned identity **thực**.
- Audit Get sẽ phản ánh principal sử dụng, không phản ánh tên App Service như human-readable label một cách bảo đảm.

### 23.4. AKS Microsoft Entra Workload ID

Các thành phần cần đối chiếu:

- AKS OIDC issuer.
- Kubernetes ServiceAccount namespace/name.
- Federated identity credential subject/audience.
- Entra application/managed identity principal.
- Projected service account token và Azure Identity SDK.
- Key Vault data-plane RBAC trên đúng principal.
- DNS/egress từ pod tới vault.

Nếu sai federation, token acquisition có thể thất bại trước data-plane; **Key Vault audit không nhất thiết có event** vì request có thể chưa tới vault.

### 23.5. Service principal client secret/certificate

Nếu CI hoặc ứng dụng cũ dùng service principal credentials:

- Credential phải được quản lý bằng secret store và rotation.
- Không log client secret/certificate private key/token.
- Kiểm tra secret expiration và token audience.
- Ưu tiên OIDC federation/managed identity khi môi trường hỗ trợ.
- Nếu principal compromised, thu hồi credential, quyền và downstream credentials theo incident plan.

**Đổi client secret** của Entra service principal khác với **rotate Key Vault Secret** do ứng dụng lưu. Có thể phải xử lý cả hai khi một principal bị xâm nhập.

## 24. Phân quyền log và nghĩa vụ bảo mật

### 24.1. Audit logs cũng cần least privilege

Chỉ một số vai trò như security analysts, incident responders, SRE có nhu cầu hợp lệ mới được query Key Vault audit logs. App runtime **không cần quyền xem toàn bộ logs** để làm việc.

Tách:

- **Vault data reader**: get secret value theo nhiệm vụ.
- **Vault data manager/rotator**: set/update/recover khi được phê duyệt.
- **Diagnostic setting operator**: bật đường xuất logs.
- **Log reader**: query workspace hoặc storage audit.
- **Incident commander**: điều phối containment và evidence retention.

### 24.2. Phạm vi dữ liệu nhạy cảm trong audit

Không có plaintext secret vẫn có thể có:

- Tên vault/secret cho biết topology.
- IP/host vùng mạng nội bộ.
- Application/principal object IDs.
- URI path hoặc version.
- Time pattern lộ giờ hoạt động/schedule rotation.
- User/service principal claims hoặc tenant metadata.

Tuân thủ các yêu cầu về privacy, retention, access reviews và downstream SIEM sharing. Redact trước khi đưa logs vào ticket/public dashboard nếu cần.

### 24.3. Không dùng audit làm “cách đọc giá trị secret gián tiếp”

Nếu một lệnh manual debug tạo log chứa request body/response body, đó là **rò thông tin**, không phải hoạt động audit cần thiết. Đừng tắt SDK redaction/HTTP header sanitation hoặc lưu HAR/raw packet capture chứa Authorization header mà không có incident approval.

### 24.4. Log tampering và evidence integrity

- Cảnh báo thay đổi/delete diagnostic settings.
- Bảo vệ workspace/storage bằng RBAC, policies và retention phù hợp.
- Ghi change tickets/approvals khi sửa log destinations.
- Với compliance yêu cầu evidence bất biến, xem immutable storage/legal hold theo chính sách.
- Ghi ai đã export/truy vấn data, nơi lưu và hash nếu quy trình đòi hỏi.
- Không tự xóa bản ghi bị xem là “false positive” khỏi central logs.

## 25. Đặt SLO/SLI cho bảo mật và vận hành

### 25.1. Những SLI có ích

| SLI | Ví dụ đo | Lưu ý |
|---|---|---|
| **Audit coverage** | Tỷ lệ production vaults có AuditEvent diagnostics enabled | Kiểm kê trên ARM + diagnostic settings |
| **Successful Get rate** | Get 2xx / all Get attempts | Đừng tính initial 401 challenge thành final failure |
| **Denied request rate** | 401/403 theo principal và env | Tách auth/network/role |
| **Refresh latency** | Thời gian từ rotation đến tất cả app instances dùng version mới | Cần app telemetry |
| **Time-to-detect** | Từ suspicious event đến alert | Ingestion delay cần đo |
| **Time-to-contain** | Từ alert đến chặn principal/credential | Có thể phụ thuộc approval |
| **Old credential revocation** | Thời gian partner ngừng chấp nhận V1 | Partner audit cần thiết |
| **Identity drift** | Runtime identity không nằm inventory | IaC + policy validation |
| **Diagnostics freshness** | Time since last event theo traffic baseline | Vắng traffic không tự là lỗi |

### 25.2. SLO minh họa

- 100% production vaults có data-plane audit destination được phê duyệt.
- 99% Key Vault Get của approved Orders API thành công trong operating window, ngoại trừ những challenge không tính là final error.
- 95% audit events hữu ích xuất hiện trong monitoring trong thời gian mục tiêu được tổ chức thống nhất.
- 100% rotations critical có **partner-side revoke evidence**.
- Mọi production IAM/network/diagnostic settings change có change ticket và audit.
- Khi có access từ principal không được duyệt, SOC nhận alert trong detection SLO.

**Các chỉ tiêu chỉ là chính sách minh họa**, không phải SLA do Azure cam kết. Cần đo baseline thực và xác định điều gì làm denominator.

### 25.3. Tránh metric sai

Không dùng:

~~~text
Key Vault SecretGet success = 100%
⇒ Mọi thanh toán đều bảo mật
~~~

Suy luận này sai: partner API có thể từ chối credential, secret có thể bị sao chép khỏi app memory, hoặc app bỏ qua kiểm tra nghiệp vụ. Bảo mật end-to-end yêu cầu xác minh nhiều tầng.

## 26. Capacity và chi phí audit

### 26.1. Ảnh hưởng của per-request SecretGet

Giả sử Orders API nhận **600 requests/s**, mỗi request tự gọi Key Vault một lần:

~~~text
600 GET/s × 60 × 60 × 24
= 51.840.000 GET/ngày
~~~

Đây là phép tính giả định, không phải quota. Nó làm tăng Key Vault operations, latency, throttling và khối lượng audit logs.

Nếu **30 app instances**, mỗi instance lấy secret tại startup và refresh **mỗi 10 phút**:

~~~text
30 instances × 6 lần/giờ × 24 giờ
= 4.320 GET/ngày
~~~

Số thật khác do startup churn, retries, nhiều secrets, token challenge, cache, SDK và feature-specific calls. Không xem đây là số billable chính xác.

### 26.2. Chi phí monitoring

| Thành phần | Có thể phát sinh phí |
|---|---|
| Key Vault | Data-plane operations, tier, Key/HSM operations khi có |
| Log Analytics | Ingestion theo dung lượng/tier, retention/query/feature theo plan |
| Storage archive | Lưu trữ và truy xuất logs |
| Event Hubs/SIEM | Streaming, ingestion, processing |
| Application Insights | Telemetry ingestion, sampling, retention |
| Private Link/Firewall/NAT | Network resources và transfer |
| Alert rules | Query/rule execution và action groups theo model |
| App/Rotation workers | Compute, scheduler, retry traffic |

Dùng bảng giá theo **region, tier và thời điểm thực**. Không đưa con số đơn giá cố định khi giá/quota có thể thay đổi.

### 26.3. Tối ưu mà không bỏ audit

- Cache secret value theo thời hạn **được security policy chấp nhận**.
- Không gọi Key Vault trên mọi business request.
- Hạn chế inventory LIST/GET không cần thiết.
- Sampling **application debug telemetry** theo policy, nhưng **không tùy tiện làm mất audit bắt buộc** của vault.
- Chọn retention tiers và archive policy phù hợp, không “tắt AuditEvent để tiết kiệm”.
- Loại bỏ duplicated logs không cần thiết ở app layer.
- Đặt alert theo principal/operation để giảm noise/incident handling cost.
- Phân tách workload identities/vaults khi blast radius lớn, có thể tăng baseline cost nhưng giảm rủi ro.

### 26.4. Tính operational cost per authorized access

Một chỉ số bổ sung:

~~~text
Monitoring cost per investigated incident
= (data ingestion + retention + analytics
   + investigation time + corrective work)
  / số incident có kết luận hữu ích
~~~

Đừng tối ưu phép chia này bằng cách **không phát hiện sự cố**. Ưu tiên audit coverage, evidence quality và time-to-contain.

## 27. Decision tree cho xác thực và truy cập secret

~~~mermaid
flowchart TD
    START["Java getSecret failed"] --> SERVICE{"Response từ dịch vụ nào?"}
    SERVICE -->|Partner API| PARTNER["Verify partner key/rotation<br/>not Key Vault RBAC"]
    SERVICE -->|Key Vault| HTTP{"HTTP status / transport"}
    HTTP -->|401| ID["Token/tenant/audience<br/>challenge vs final failure"]
    HTTP -->|403| FORB{"Network policy denial?"}
    FORB -->|Yes| NET["Firewall/VNet/private DNS"]
    FORB -->|No| RBAC["Vault permission model<br/>principal ID/role/scope"]
    HTTP -->|404| NAME["Vault/name/version/<br/>deleted/disabled state"]
    HTTP -->|429| THROTTLE["Retry-After/backoff<br/>cache/scale"]
    HTTP -->|5xx| TRANSIENT["Service health/retry budget"]
    HTTP -->|DNS/TLS timeout| ROUTE["Hostname/routing/cert"]
    ID --> FIX["Apply approved fix + safe retest"]
    NET --> FIX
    RBAC --> FIX
    NAME --> FIX
    THROTTLE --> FIX
    TRANSIENT --> FIX
    ROUTE --> FIX
    PARTNER --> FIX
    FIX --> AUDIT["Check app + KV audit<br/>record root cause"]
~~~

**Câu hỏi quyết định đầu tiên:** lỗi ở **Key Vault**, **Entra**, **network** hay **partner API**? Đây là cách nhanh nhất tránh sửa sai hệ thống.

### 27.1. Triệu chứng và kiểm tra đầu tiên

| Triệu chứng | Kiểm tra đầu tiên | Không nên làm |
|---|---|---|
| Local OK, prod 403 | Prod managed identity principal, RBAC, network | Copy developer secret vào prod |
| Nhiều 401 nhưng final 200 | Challenge sequence/SDK | Alert mọi 401 như tấn công |
| 403 sau khi bật Private Endpoint | DNS/VNet firewall | Tắt firewall toàn bộ |
| 404 chỉ với một secret | Name/version/deletion state | Auto-create production secret |
| 429 sau scale-out | Startup GET burst, cache refresh | Retry vô hạn |
| App 200 Key Vault nhưng partner 401 | Key rotation/downstream auth | Cấp Key Vault Administrator |
| Audit không thấy event | Diagnostic destination/table/ingestion lag, network failure trước KV | Kết luận không có request |
| Principal lạ đọc secret | Correlate role/network/deploy, classify exposure | Chỉ xóa log hoặc xóa secret |
| Rotation Set thành công, app vẫn V1 | Cache/version pinning/app rollout | Tin rằng Set đồng nghĩa revoke |
| IAM role bị remove nhưng vẫn còn activity | Token/authorization caching, inherited roles, alternate identity | Tuyên bố đã containment đủ |

## 28. Lab điều tra end-to-end trên dữ liệu giả

Mục tiêu: có một vault lab, một secret giả, data-plane audit destination, hai danh tính (authorized/denied) và một ứng dụng Java test không in value.

### 28.1. Kịch bản A: thành công

1. Xác nhận vault đã bật AuditEvent diagnostics.
2. Identity A có data-plane **Key Vault Secrets User**.
3. Dùng Java SecretClient getSecret(name) trên demo value.
4. Chỉ log status, duration và correlation metadata.
5. Sau ingestion delay, tìm SecretGet trong workspace.
6. So principal/operation/result với app trace.
7. Xác nhận không có secret value trong logs.

### 28.2. Kịch bản B: RBAC denial

1. Identity B không có Secret Get permission.
2. Dùng cùng vault/secret demo và cùng network path.
3. Gọi getSecret bằng B, ghi status/error code sanitized.
4. Truy vấn AuditEvent và tìm failed access nếu đã tới Key Vault.
5. Đối chiếu vault permission model và role assignments.
6. Chỉ người quản trị được phép mới có thể thay quyền; ứng dụng không tự cấp.
7. Xác nhận identity B vẫn không xem được value từ bất kỳ đường khác.

### 28.3. Kịch bản C: network denial

1. Chỉ trên lab, áp firewall/Private Endpoint test theo approval.
2. Gọi từ host không thuộc network allowed.
3. Đo lỗi HTTP 403/network timeout và DNS behavior.
4. Kiểm tra data-plane logs nếu request tới service và network traces.
5. Không đổi vault URL sang private IP và không tắt TLS.
6. Khôi phục network setting đã phê duyệt.

### 28.4. Kịch bản D: secret name/version sai

1. Gọi getSecret với name/version demo không tồn tại.
2. Ghi error type/status đã sanitize.
3. Xem Query Key Vault AuditEvent và app dependency trace.
4. Không tạo secret tự động hoặc fallback hard-coded.

### 28.5. Kịch bản E: rotation

1. Operator tạo version V1 và V2 đều là demo.
2. App đọc versionless và pinned V1 để so lifecycle.
3. Ghi version metadata alias, không ghi values.
4. Simulate application cache refresh.
5. Kết nối data-plane Set/Get audit cùng change ticket.
6. Thử rollback theo policy và chỉ dọn lab khi owner duyệt.

### 28.6. Mẫu báo cáo lab

| Field | Giá trị ví dụ |
|---|---|
| TestCase | Denied SecretGet |
| Resource | kv-audit-lab |
| Principal | lab-identity-B |
| Start UTC | 2026-11-20T08:00:00Z |
| Expected | Denied / no secret disclosure |
| Observed | HTTP 403, sanitized |
| Evidence | Key Vault AuditEvent + app trace |
| Root cause | Missing Get permission |
| Fix | None; expected negative test |
| Secrets in logs? | No |
| Owner | Lab operator |

Chỉ dùng metadata; không đính kèm giá trị demo hoặc production secret vào report.

## 29. Negative tests và diễn tập staging

| Test | Kết quả cần đạt |
|---|---|
| Identity không có Secret Get | Không lấy value, denied audit phù hợp |
| App có Azure Contributor nhưng không có data-plane role | Không tự có quyền Get |
| Vault RBAC mode, chỉ thêm legacy access policy | Không coi đây là role hiệu lực |
| Legacy access policy mode, chỉ gán Data Reader role không phù hợp | Vẫn bị từ chối theo model |
| App Service chọn user-assigned client ID sai | Token/authorization failure được phân loại |
| AKS federation subject sai | Không lấy token; xác nhận không có KV event tương ứng có thể bình thường |
| Role ở resource khác | Không được coi là đủ quyền |
| Role vừa gán | Theo dõi propagation, không retry vô hạn |
| Network chặn public endpoint | Không bypass firewall để test |
| Private DNS không đúng | FQDN/TLS route fail rõ, không nối raw IP |
| Secret name sai | Không tự tạo fallback |
| Version đã disable/expire | Application fail policy; không dùng revoked cached key |
| 100 instances cùng start | Retry bounded/jitter, không làm quá tải vault |
| Một 401 challenge rồi 200 | Không cảnh báo sai như failure |
| Partner API trả 401 trong khi KV Get=200 | Debug downstream credential |
| Audit settings bị tắt | Detection và change audit có signal |
| Log query table mismatch | Inspect diagnostic mode/schema, không kết luận mất events |
| App error log vô tình chứa secret | Scanner phát hiện, incident process và rotation |
| Rotation V1→V2 | Partner revoke V1 và all app instances converged |
| Identity compromised | Containment, evidence preservation và verification |

Diễn tập bằng **staging/lab**, không cố ý làm hỏng vault production, vô hiệu monitoring hoặc thử purge trên tài nguyên shared.

## 30. Bảng quyết định xử lý sự cố thường gặp

| Dấu hiệu | Phân loại bước đầu | Hành động ưu tiên |
|---|---|---|
| SecretGet 200 từ principal được duyệt lúc startup | Có thể bình thường | Đối chiếu deployment, rotation window, baseline |
| SecretGet 200 từ principal mới không có change ticket | Nghi vấn security | Audit role changes, principal, network và partner usage |
| SecretList hàng loạt từ một workload chỉ cần Get | Nghi vấn privilege misuse | Xác minh principal, scope, owner, access pattern |
| 401 ban đầu rồi 200 | Authentication challenge có thể bình thường | Kiểm tra final response, không báo incident chỉ từ một 401 |
| Final 401 Key Vault | Authentication/token issue | Credential source, audience, tenant, clock |
| 403 Key Vault | Authorization hoặc network | Permission model/RBAC/identity/firewall/Private DNS |
| 404 Key Vault | Resource/name/version/lifecycle | Vault URI, secret name, version, deleted state |
| 429 Key Vault | Throttling | Backoff/jitter, cache, giảm concurrency |
| TLS/DNS timeout | Network path | DNS FQDN, VNet, Private Endpoint, firewall/proxy |
| Key Vault Get thành công, partner 401 | Downstream credential | Partner rotation, app cache và revocation |
| Role assignment bất thường | Control-plane incident | Preserve Activity Log, review principal/scope và containment |
| Diagnostic setting bị tắt | Monitoring tampering hoặc change chưa duyệt | Activity Log, restore approved config, security investigation |
| Deleted secret nhưng partner vẫn nhận key | Credential vẫn còn giá trị ngoài vault | Revoke/rotate tại partner, không chỉ delete vault |
| Secret trong application log | Exfiltration risk | Incident, restrict logs, revoke/rotate, kiểm tra bản sao |
| App còn dùng version V1 sau rollout V2 | Rotation propagation | Kiểm tra pinned version, TTL/cache, instances, partner |
| Không có AuditEvent sau lỗi client | Có thể lỗi trước data-plane hoặc ingestion delay | Client traces, network, diagnostics destination |
| Local chạy, Azure app lỗi | Runtime identity/network khác | Kiểm tra managed identity, role scope, VNet DNS |

### 30.1. Phân biệt ưu tiên operational và security

**Operational incident**: đa số là app không đọc được secret do role/network/configuration, ảnh hưởng availability và cần rollback/fix được phê duyệt.

**Security incident**: có bằng chứng truy cập trái phép, credential rò, principal bị compromise hoặc audit pipeline bị can thiệp. Cần bảo toàn chứng cứ và điều phối response; không chữa bằng cách cấp thêm quyền.

Hai loại có thể cùng xảy ra: sau một IAM change bất thường, app vừa mất quyền trong khi principal khác lấy được secret. Phải phối hợp SRE, IAM và SOC.

## 31. Checklist production cho audit và authentication

### 31.1. Thiết kế danh tính và quyền

- [ ] Mỗi workload có managed identity/workload identity rõ ràng, có owner.
- [ ] Danh tính runtime được gán quyền **Get secrets** tối thiểu.
- [ ] Không cấp Key Vault Administrator/Secrets Officer cho app chỉ cần đọc.
- [ ] Không dùng Azure Contributor làm thay data-plane Secrets User.
- [ ] Đã chọn rõ RBAC permission model hoặc access policy model.
- [ ] Các inherited role assignments và scope được review.
- [ ] User-assigned client ID và principal object ID không bị nhầm.
- [ ] AKS federation issuer/subject/audience đã được kiểm thử nếu sử dụng.
- [ ] Local developer credential không được mang sang production.
- [ ] Identity/permission changes có approval, change ticket và audit.
- [ ] Đã có phương án containment khi revoke role không có hiệu lực ngay do caching.

### 31.2. Audit và logging

- [ ] AuditEvent diagnostics bật cho mọi vault production phù hợp policy.
- [ ] Azure Activity Log và IAM change events có retention/destination được quản lý.
- [ ] Entra identity events và Java dependency telemetry có thể join theo thời gian/principal.
- [ ] Logs được phân biệt data-plane vs control-plane.
- [ ] Team biết workspace dùng **AzureDiagnostics hay resource-specific table**.
- [ ] KQL queries được kiểm thử trên schema thực, không chỉ bản demo.
- [ ] Có đủ status, operation, principal, resource, time và request ID metadata.
- [ ] Không ghi secret value, access token hoặc Authorization header.
- [ ] Diagnostic settings và destination changes được cảnh báo.
- [ ] SOC/IR có read access audit nhưng không mặc nhiên có Secret Get.
- [ ] Retention, legal hold, export/chain of custody theo policy.
- [ ] Đã có alert trên principal lạ, SecretList bất thường và failed access spikes.
- [ ] Đã có phương pháp giảm false positives sau deployment/scale-out.
- [ ] Monitoring ingestion delay và request/alert availability được đo.

### 31.3. Mạng và Key Vault operation

- [ ] Vault public network/firewall/Private Endpoint design được duyệt.
- [ ] DNS vault-name.vault.azure.net hoạt động từ đúng host/pod.
- [ ] Private DNS zone/link và route được xác minh.
- [ ] Không disable TLS/certificate verification để vượt DNS lỗi.
- [ ] App có valid token đúng tenant và Key Vault audience.
- [ ] Secret names/versions được cấu hình theo environment.
- [ ] Startup cache/refresh TTL và failure behavior được xác định.
- [ ] Không gọi getSecret cho mọi request hoặc liveness probe.
- [ ] 401 challenge/final outcome được phân biệt.
- [ ] 403 được phân loại network vs RBAC/policy.
- [ ] 404 có runbook name/version/deleted state.
- [ ] 429 có retry budget/backoff/jitter, tôn trọng Retry-After.
- [ ] 5xx/timeout có strategy degraded service và health checks.
- [ ] Partner auth failures được tách khỏi Key Vault failures.

### 31.4. Incident response và rotation

- [ ] Có inventory secret owner, data classification và partner/system dùng key.
- [ ] Có incident severity criteria và on-call contacts.
- [ ] Có cách giữ chứng cứ logs trước thay đổi phá hủy.
- [ ] Có playbook compromised identity/compromised secret.
- [ ] Có quy trình cấp key mới ở hệ thống đích rồi cập nhật vault.
- [ ] Có thể revoke credential cũ ở partner/DB/CA, không chỉ delete vault entry.
- [ ] Có canary, rollback và version metadata telemetry khi rotation.
- [ ] Có kiểm tra all instances đã nhận key mới.
- [ ] Có soft-delete/purge protection/recovery policy.
- [ ] Không purge hoặc disable production secrets nếu chưa phê duyệt.
- [ ] Logs, source code, CI artifacts và config snapshots được scan khi nghi leak.
- [ ] Có postmortem và regression tests cho root cause.
- [ ] Đã đo cost/quota/retention của log pipeline và SecretGet.
- [ ] Mọi thao tác thực hành phải dùng lab secrets, không dùng production values.

## 32. Bài tập thực hành

### Bài 1: Xác định nguồn logs

Cho ba events:

1. Java **SecretGet** tới Key Vault trả 403.
2. Admin thay firewall settings của vault.
3. Managed identity không lấy được access token do federation sai.

Hãy chọn **Key Vault AuditEvent**, **Azure Activity Log** hay **Entra/workload/application telemetry** làm nguồn đầu tiên, rồi giải thích vì sao một nguồn khác không thể chứng minh toàn bộ sự kiện.

### Bài 2: Bật audit cho vault lab

1. Chọn subscription/resource group được duyệt.
2. Xác minh vault permission model.
3. Xem danh mục diagnostic logs.
4. Bật AuditEvent tới Log Analytics đã được owner duyệt.
5. Đọc lại setting và workspace ID.
6. Thử một Get trên secret demo.
7. Chờ ingestion và tìm event.
8. Chỉ in operation/status/metadata, không in value.

### Bài 3: KQL baseline

Viết KQL thống kê:

- SecretGet/SecretList/SecretSet theo ngày.
- Số requests thành công/thất bại.
- Top principal/caller IP theo số operations.
- Tỷ lệ 403 sau deployment.
- Một đỉnh sau rotation được xác nhận hợp lệ.

Trước tiên dùng **getschema/take** với table thực; không giả định có requestUri_s nếu schema không chứa.

### Bài 4: Phân biệt 401 challenge

Một Java SDK tạo request:

~~~text
12:00:00 Key Vault GET returns 401 with challenge
12:00:00 Azure Identity obtains token
12:00:01 Key Vault GET returns 200
~~~

Đây có phải sự cố authentication? Cần cảnh báo theo **final outcome** thế nào để không tạo false positive?

### Bài 5: Điều tra 403 khi App Service chạy

Developer local đọc demo secret được, còn App Service production nhận 403.

Lập bảng kiểm tra:

1. App Service managed identity principal ID.
2. Vault authorization model RBAC/access policy.
3. Scope Key Vault Secrets User.
4. Role propagation.
5. Private Endpoint/firewall/DNS.
6. Vault URL và tenant.
7. Tương quan audit/request ID.

Không sử dụng giải pháp cấp Azure Owner cho app.

### Bài 6: Secret name/version gây 404

Ứng dụng pin version V1 và sau rotation V1 bị disable/xóa. Hãy thiết kế:

- Check secret URI/version.
- Quy trình xử lý 404/lifecycle error.
- Canary version V2.
- Cách kiểm tra partner sử dụng V2.
- Rollback/fail-closed theo risk.
- Cách log version metadata mà không lộ key.

### Bài 7: Khi partner trả 401

Key Vault Get trả 200, partner payment API trả 401. Hãy giải thích vì sao không sửa Key Vault RBAC. Thiết kế các kiểm tra: active partner key, app cache, V1/V2 rollout, Authorization header sanitation và partner audit.

### Bài 8: KQL tìm principal lạ

Một vault production có 10 approved identities. Một principal mới phát sinh 200 SecretGet trong 15 phút.

- Xem role assignment/owner.
- Kiểm tra deployment/change ticket.
- Đọc caller IP/NAT.
- Xác minh secret paths.
- Phân loại security vs operation.
- Thiết kế alert và containment.
- Ghi giới hạn của kết luận chỉ từ audit.

### Bài 9: Tắt diagnostic settings

Kết hợp Azure Activity Log và diagnostics inventory để phát hiện một người tắt AuditEvent trước thời điểm nghi có SecretGet. Nêu những khoảng chứng cứ đã mất mà không thể tự tạo lại từ log.

### Bài 10: Retry storm

100 application instances scale out, mỗi instance GET 5 secrets và retry 5 lần khi 429:

1. Tính số attempts tối đa giả định nếu mọi lần đều retry.
2. Đề xuất bounded concurrency và jitter.
3. So với một design caching tại startup, refresh mỗi 10 phút.
4. Xác định metrics cho Key Vault và application.
5. Nêu vì sao không dùng liveness probe gọi vault.

### Bài 11: Incident secret bị lộ trong CI

Một build log chứa API key của partner, dù Key Vault AuditEvent chỉ có Get hợp lệ.

Thiết kế runbook:

1. Restrict logs và bảo toàn evidence.
2. Phân loại credential exposure.
3. Phát hành key mới tại partner.
4. Update Key Vault version.
5. Canary/rollout app.
6. Revoke old partner key.
7. Review repo/CI/artifacts và audit.
8. Postmortem và redaction regression test.

### Bài 12: Negative tests RBAC

Hai identities:

- A: **Key Vault Secrets User** trên vault lab.
- B: **Key Vault Reader** hoặc không có data-plane Get.

Thử SecretGet, metadata listing và xem kết quả, đối chiếu với role definitions hiện hành. Tại sao Key Vault Reader không đồng nghĩa có quyền xem plaintext secret?

### Bài 13: Private Link failure

Một AKS pod có role đúng nhưng không resolve private vault FQDN.

- Vẽ DNS, private endpoint và route.
- Đo TLS/timeout từ pod.
- So app trace và Key Vault AuditEvent.
- Giải thích vì sao có thể không có event data-plane.
- Viết fix plan không tắt firewall hoặc TLS.

### Bài 14: Capacity và FinOps

Với 600 business req/s và một SecretGet/request, so số GET/ngày với 30 instances refresh mỗi 10 phút. Ước lượng tác động lên Key Vault operations và log ingestion nhưng **không tự bịa đơn giá**. Đề xuất TTL/rotation SLO phù hợp.

### Bài 15: Security tabletop

SOC nhận alert principal lạ đọc 3 secrets nhạy cảm. IAM team đang chờ RBAC propagation, SRE lo checkout outage, Partner API chưa hỗ trợ dual-key.

Hãy xác định:

- Ai là incident commander.
- Containment ưu tiên.
- Khi nào phải chấp nhận downtime để revoke.
- Những logs cần bảo toàn.
- Cách verify key cũ không còn dùng được.
- Criteria close incident và lessons learned.

## 33. Câu hỏi tự kiểm tra

1. Audit Key Vault data-plane khác Azure Activity Log như thế nào?
2. AuditEvent thường giúp trả lời những câu hỏi gì?
3. Diagnostic settings có retroactively tạo được logs trước khi bật không?
4. AzureDiagnostics khác resource-specific table như AZKVAuditLogs thế nào?
5. Khi một table không tồn tại, có thể kết luận vault chưa có request không?
6. Vì sao cần kiểm tra schema trước khi viết KQL?
7. Khi nào SecretList khác SecretGet?
8. Một successful SecretGet có chứng minh dữ liệu đã bị exfiltrate không?
9. Không có SecretGet lạ có chứng minh secret chưa bị leak không?
10. Vì sao CallerIPAddress không đủ xác định người dùng?
11. Một managed identity tương ứng với người dùng cuối trong logs không?
12. Control plane role và data-plane role khác nhau thế nào?
13. Azure Contributor có được đọc secret value theo mặc định không?
14. Key Vault Reader khác Key Vault Secrets User ở đâu?
15. Vault dùng RBAC mode có tự chấp nhận access policy không?
16. Một role assignment tại resource group có thể ảnh hưởng bao nhiêu vaults?
17. Vì sao cần inventory principal object ID và client ID?
18. App Service system-assigned identity có thể thay principal sau recreate không?
19. AKS Workload ID cần issuer/subject/audience nào được cấu hình?
20. Entra token acquisition thành công có nghĩa Key Vault Get được phép không?
21. Vì sao một 401 challenge có thể là hành vi bình thường?
22. Làm sao phân biệt final 401 với 401 challenge?
23. Những nguyên nhân nào gây 403 ngoài RBAC?
24. Network firewall deny có thể có HTTP 403 không?
25. Vì sao không nên tắt TLS để giải quyết lỗi private DNS?
26. Khi nào 404 cần kiểm tra secret version?
27. Vì sao không nên auto-create secret khi thấy 404?
28. 429 phát sinh do những thói quen gọi SDK nào?
29. Khi nào nên cache secret thay vì GET trên mọi request?
30. Token cache có đồng nghĩa secret value cache không?
31. Partner API 401 khác Key Vault 401 như thế nào?
32. Secret versionless có tự ép mọi JVM dùng version mới ngay không?
33. Key Vault Set version mới có revoke key cũ ở partner không?
34. Vì sao xóa vault secret không ngăn kẻ tấn công dùng key đã copy?
35. Soft-delete khác purge protection như thế nào?
36. Rotation cần audit những giai đoạn nào?
37. Những logs nào cần giữ khi nghi credential compromise?
38. Diagnostic settings change có nên có alert riêng không?
39. Vì sao không nên alert chỉ dựa vào một peak SecretGet?
40. Làm sao phân biệt scale-out hợp lệ với truy cập bất thường?
41. Vì sao IAM role removal không nên được coi là containment tức thời?
42. Application Insights nên log gì và tránh log gì?
43. Java String có bảo đảm xóa credential khỏi RAM ngay không?
44. Cần làm gì nếu secret xuất hiện trong CI log?
45. Khi nào phải fail closed thay vì dùng cached key?
46. Readiness và liveness khác nhau thế nào với Key Vault dependency?
47. KQL kết quả rỗng có thể là vấn đề field nào?
48. Vì sao audit logs cần phân quyền chặt dù không có secret value?
49. Nguồn chi phí nào ngoài Key Vault operations?
50. Thế nào là chứng cứ đầy đủ để đóng một incident secret exposure?

## 34. Tài liệu tham khảo

- [Azure Key Vault overview — Microsoft Learn](https://learn.microsoft.com/azure/key-vault/general/overview)
- [Key Vault authentication and authorization](https://learn.microsoft.com/azure/key-vault/general/authentication)
- [Azure RBAC for Key Vault](https://learn.microsoft.com/azure/key-vault/general/rbac-guide)
- [Key Vault access policies](https://learn.microsoft.com/azure/key-vault/general/assign-access-policy)
- [Monitor Azure Key Vault](https://learn.microsoft.com/azure/key-vault/general/monitor-key-vault)
- [Key Vault logging and diagnostics](https://learn.microsoft.com/azure/key-vault/general/logging)
- [Azure Monitor diagnostic settings](https://learn.microsoft.com/azure/azure-monitor/essentials/diagnostic-settings)
- [Azure Activity Log](https://learn.microsoft.com/azure/azure-monitor/essentials/activity-log)
- [Log Analytics Kusto Query Language](https://learn.microsoft.com/azure/azure-monitor/logs/log-query-overview)
- [Azure Monitor reference: AZKVAuditLogs](https://learn.microsoft.com/azure/azure-monitor/reference/tables/azkvauditlogs)
- [Azure Monitor reference: AzureDiagnostics](https://learn.microsoft.com/azure/azure-monitor/reference/tables/azurediagnostics)
- [Key Vault network security](https://learn.microsoft.com/azure/key-vault/general/network-security)
- [Azure Key Vault Private Link](https://learn.microsoft.com/azure/key-vault/general/private-link-service)
- [Key Vault soft-delete overview](https://learn.microsoft.com/azure/key-vault/general/soft-delete-overview)
- [Key Vault backup and restore](https://learn.microsoft.com/azure/key-vault/general/backup)
- [Azure Key Vault secret management with Java](https://learn.microsoft.com/azure/key-vault/secrets/quick-create-java)
- [Azure Key Vault Secrets Java SDK](https://learn.microsoft.com/java/api/overview/azure/security-keyvault-secrets-readme)
- [Azure Identity for Java SDK](https://learn.microsoft.com/java/api/overview/azure/identity-readme)
- [Microsoft Entra managed identities](https://learn.microsoft.com/entra/identity/managed-identities-azure-resources/overview)
- [AKS Microsoft Entra Workload ID](https://learn.microsoft.com/azure/aks/workload-identity-overview)
- [Azure Event Grid integration with Key Vault](https://learn.microsoft.com/azure/key-vault/general/event-grid-overview)
- [Azure Key Vault pricing](https://azure.microsoft.com/pricing/details/key-vault/)
- [Azure Monitor pricing](https://azure.microsoft.com/pricing/details/monitor/)
- [Azure Pricing Calculator](https://azure.microsoft.com/pricing/calculator/)






