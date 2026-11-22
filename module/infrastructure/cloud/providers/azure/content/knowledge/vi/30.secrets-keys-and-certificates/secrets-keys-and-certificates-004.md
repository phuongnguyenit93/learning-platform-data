# Quản lý khóa và thao tác mã hóa với Key Vault

> **Chương:** Secret, khóa và chứng chỉ  
> **Module:** `CLOUD_PROVIDERS_AZURE` — Khám phá hệ sinh thái Microsoft Azure từ subscription, resource group và Entra ID đến mạng ảo, dịch vụ tính toán, lưu trữ và dữ liệu. Học cách triển khai, giám sát, bảo vệ và kiểm soát chi phí một kiến trúc ứng dụng trên Azure.

## Mục tiêu bài học

Sau bài học, bạn có thể:

1. Phân biệt **Azure Key Vault Keys, Secrets và Certificates**, Key Vault Standard/Premium và **Azure Managed HSM**, cùng các ranh giới tin cậy của khóa mã hóa.
2. Giải thích sự khác nhau giữa **mã hóa bất đối xứng RSA**, **ký/xác minh chữ ký**, **wrap/unwrap key** và **AES-256-GCM mã hóa đối xứng**, biết thao tác nào không phù hợp để mã hóa file lớn.
3. Quản trị vòng đời khóa: **tạo, bật/tắt, đặt thời gian hiệu lực, phiên bản, rotation, soft delete, purge protection, backup/restore và decommission**.
4. Cấp quyền bằng **Microsoft Entra ID, managed identity, Azure RBAC** ở phạm vi tối thiểu; hiểu khác biệt control plane, data plane và access-policy model cũ.
5. Thực hiện thao tác crypto an toàn với **Azure CLI và Azure SDK cho Java**: KeyClient, CryptographyClient, RSA-OAEP-256, wrap/unwrap, RSA sign/verify.
6. Thiết kế **envelope encryption**: tạo data encryption key (DEK) cục bộ, AES-GCM cho payload, dùng Key Vault key-encryption key (KEK) để bảo vệ DEK, lưu versioned key ID.
7. Kết nối **Private Endpoint, Private DNS, TLS**, thiết lập auditing, giám sát lỗi 401/403/404/429 và phân tích độ trễ/chi phí.
8. Nhận diện tình huống rủi ro: xóa key nhầm, rotation làm mất khả năng giải mã, quyền crypto quá rộng, nonce reuse, lộ plaintext DEK, mã hóa không xác thực và lỗi retry.
9. Thiết kế bài lab, ma trận test quyền, runbook xử lý sự cố và checklist production cho ứng dụng Azure.

## 1. Bối cảnh: dữ liệu được mã hóa nhưng ai giữ khóa?

Một hệ thống thương mại điện tử lưu file hóa đơn ở Azure Blob Storage, hồ sơ định danh trong cơ sở dữ liệu và một số nội dung nhạy cảm cần mã hóa trước khi lưu. Ứng dụng Java chạy trên Azure App Service hoặc Azure Container Apps, dùng **managed identity** để gọi Key Vault.

Nếu ứng dụng lưu khóa mã hóa AES cố định trong `application.properties`, Docker image hoặc Git, khi bị lộ khóa thì attacker có thể giải mã cả kho dữ liệu. Nếu mọi developer đều có `Key Vault Administrator` và quyền xóa khóa, việc phân quyền yếu vẫn làm mã hóa mất tác dụng.

Cần thiết kế rõ:

- **Dữ liệu nhạy cảm nào cần mã hóa ở tầng ứng dụng?** Không phải mọi file đều cần tự mã hóa vì Azure Storage đã hỗ trợ encryption at rest; yêu cầu có thể đến từ compliance/tenant separation.
- **Khóa nào bảo vệ dữ liệu?** Phân biệt **Data Encryption Key (DEK)** và **Key Encryption Key (KEK)**.
- **Ai có quyền gọi operation gì?** Đọc metadata khóa, wrap, unwrap, encrypt, decrypt và quản trị lifecycle là các quyền khác nhau.
- **Khóa có thể bị xuất plaintext ra ngoài không?** Khóa bất đối xứng được tạo/lưu trong Key Vault/HSM có protection boundary; private key dùng crypto operation qua dịch vụ, không phải giá trị ứng dụng được đọc bằng API như secret.
- **Nếu key bị tắt, xóa hoặc rotation, dữ liệu cũ có đọc được không?** Phải lưu version ID và có lịch sử khóa hợp lệ.
- **Mạng, logging và recovery có đáp ứng an toàn không?** Key Vault authorization không thay thế Private Link/TLS, audit hay business authorization.

~~~mermaid
flowchart LR
    U["Người dùng"]
    API["Java API\nBusiness authorization"]
    MI["Managed identity\nEntra ID"]
    KV["Azure Key Vault\nKEK asymmetric key"]
    AES["Local AES-256-GCM\nDEK per object"]
    BLOB["Azure Blob Storage\nEncrypted object"]
    DB["Metadata DB\nWrapped DEK + key ID"]
    OBS["Azure Monitor\nDiagnostics + alerts"]
    U --> API
    MI -.->|"Token"| API
    API --> AES
    AES -->|"Wrap / unwrap DEK"| KV
    AES -->|"Ciphertext"| BLOB
    API -->|"Metadata"| DB
    KV -.-> OBS
    API -.-> OBS
~~~

**Ví dụ xuyên suốt:** mỗi hóa đơn có một DEK ngẫu nhiên. Nội dung hóa đơn được mã hóa bằng AES-GCM ở Java; Key Vault chỉ xử lý **wrap/unwrap DEK nhỏ**, không nhận toàn bộ file nhiều GiB.

## 2. Key Vault lưu Keys, Secrets và Certificates khác nhau

### 2.1. Ba loại đối tượng

| Loại | Mục đích | API/SDK phù hợp | Cảnh báo |
| --- | --- | --- | --- |
| **Keys** | Quản lý khóa bất đối xứng và crypto operations như encrypt/decrypt, wrap/unwrap, sign/verify | `azure-security-keyvault-keys` | Không phải kho lưu mọi giá trị bí mật tùy ý |
| **Secrets** | Lưu password, API key, connection string và bytes/text secret theo giới hạn | `azure-security-keyvault-secrets` | Đọc secret trả về **giá trị plaintext** cho principal được cấp quyền |
| **Certificates** | Quản lý vòng đời chứng chỉ TLS/X.509, certificate policy và liên hệ khóa/secret | `azure-security-keyvault-certificates` | Không đồng nghĩa một certificate public chứa private key có thể xuất tùy ý |

Một **Key Vault key** có metadata, public key (đối với asymmetric key), policy và các crypto operations. Một **Secret** được đọc dưới dạng giá trị, nên lưu AES master key trong secret khiến mọi principal có `get secret` có thể lấy plaintext key. Với bài toán bảo vệ khóa bằng boundary được quản lý, nên xem **Keys/HSM + wrap/unwrap** thay vì lấy secret chứa key vào app.

### 2.2. Standard, Premium và Managed HSM

| Lựa chọn | Đặc trưng | Phù hợp |
| --- | --- | --- |
| **Azure Key Vault Standard** | Lưu trữ khóa software-protected và secrets/certs theo khả năng của dịch vụ | Phần lớn ứng dụng cần key management và crypto operations |
| **Azure Key Vault Premium** | Bổ sung các lựa chọn khóa HSM-protected được hỗ trợ | Workload cần HSM-backed key protection và policy tương ứng |
| **Azure Key Vault Managed HSM** | Dịch vụ HSM riêng cho khóa, có cách quản trị/backup, network và billing khác Key Vault thường | Quy định kiểm soát nghiêm ngặt hoặc nhu cầu quản trị HSM chuyên biệt |

Không suy rằng “Premium” tự biến **mọi khóa** thành HSM-protected: khi tạo khóa cần chọn **key type/đích lưu trữ** phù hợp. Các tính năng, chuẩn compliance, khu vực và mức giá có thể thay đổi; kiểm tra giới hạn dịch vụ và yêu cầu chứng nhận cụ thể trước khi đưa production.

### 2.3. Không nhầm Key Vault và Managed HSM

- Vault có endpoint dạng `https://<vault-name>.vault.azure.net/`.
- Managed HSM có endpoint và permission/security domain/backup model riêng.
- Command `az keyvault key ...` và Java Key Vault SDK tập trung vào khả năng Key Vault cụ thể; không mặc định ví dụ trong bài có thể dùng nguyên vẹn với Managed HSM.
- Key Vault Premium HSM keys và Managed HSM không có cùng mọi tính năng/giới hạn.
- Trước khi thiết kế yêu cầu FIPS/compliance, cần đối chiếu tài liệu chứng nhận và SKU/algorithm được tổ chức chấp thuận.

### 2.4. Key identifier gồm phiên bản

Một Key Vault key có thể được tham chiếu:

~~~text
https://kv-orders-prod.vault.azure.net/keys/invoice-kek
https://kv-orders-prod.vault.azure.net/keys/invoice-kek/KEY_VERSION
~~~

- URI thứ nhất là **versionless key identifier**: thao tác có thể đi theo latest/current version theo cơ chế API/SDK.
- URI thứ hai là **versioned key identifier**: cố định phiên bản khóa cụ thể.
- Khi mã hóa dữ liệu dài hạn, **lưu chính xác versioned key ID đã dùng** trong envelope metadata. Không mặc định dùng phiên bản mới nhất để giải mã dữ liệu cũ.
- Version ID là giá trị của dịch vụ, không được client tự suy đoán từ ngày tháng hoặc đặt một tên key khác mà vẫn coi là cùng khóa.

## 3. Các thuật toán và thao tác cần hiểu

### 3.1. Asymmetric key: RSA và EC

**RSA** có public/private key, hỗ trợ các thao tác tùy key type/operations được cấu hình:

- Mã hóa/giải mã **dữ liệu rất nhỏ** với RSA-OAEP khi được hỗ trợ.
- **Wrap/unwrap** khóa đối xứng ngắn như AES DEK.
- **Sign/verify** theo thuật toán ký phù hợp.

**Elliptic Curve (EC)** trong Key Vault thường dùng cho **chữ ký số ECDSA**, không phải drop-in replacement cho `RSA-OAEP` encrypt/wrap. Không tạo EC key rồi gọi `encrypt(RSA_OAEP_256, ...)`.

### 3.2. RSA-OAEP-256 dùng cho thông điệp nhỏ

RSA-2048 có modulus dài 256 bytes. Với OAEP sử dụng SHA-256, độ dài plaintext tối đa theo giới hạn tiêu chuẩn là:

\[
mLen \le k - 2hLen - 2 = 256 - 64 - 2 = 190\ \text{bytes}.
\]

Do đó **không mã hóa file PDF 10 MiB trực tiếp bằng RSA-OAEP-256**. Dùng mã hóa lai/envelope encryption: AES-GCM xử lý dữ liệu lớn, RSA-OAEP-256 chỉ wrap DEK 32 bytes.

Với RSA-3072/4096, giới hạn payload lớn hơn nhưng vẫn không biến RSA thành thuật toán bulk encryption. Không sử dụng RSA-OAEP sai padding; tránh RSA PKCS#1 v1.5 encryption cho thiết kế mới nếu không có yêu cầu tương thích đã được đánh giá.

### 3.3. AES-256-GCM là mã hóa có xác thực

AES-GCM cung cấp **confidentiality và integrity/authentication tag** cho ciphertext khi dùng đúng:

- AES key 256 bits (32 bytes).
- Nonce/IV điển hình 96 bits (12 bytes).
- Authentication tag phổ biến 128 bits.
- **AAD** (Additional Authenticated Data) để ràng buộc tenant ID, object ID, schema version mà không mã hóa chúng.
- **Không được tái sử dụng cùng IV với cùng DEK**: điều này phá bảo đảm an toàn của GCM.

Mẫu tốt: **một DEK ngẫu nhiên mới cho mỗi object**, một IV ngẫu nhiên mới, mã hóa file bằng AES-GCM, wrap DEK bằng Key Vault. Với file quá lớn hoặc streaming nhiều chunks, cần giao thức chunked AEAD được thiết kế/kiểm chứng riêng, không tái dùng cùng nonce cho mọi chunk.

### 3.4. Encrypt/decrypt, wrap/unwrap, sign/verify không giống nhau

| Thao tác Key Vault | Đầu vào | Đầu ra | Công dụng |
| --- | --- | --- | --- |
| **Encrypt** | Plaintext nhỏ + algorithm | Ciphertext | Mã hóa dữ liệu nhỏ theo key algorithm |
| **Decrypt** | Ciphertext + algorithm | Plaintext | Giải mã dữ liệu nhỏ |
| **Wrap Key** | Raw DEK nhỏ + key wrap algorithm | Wrapped DEK | Bảo vệ khóa đối xứng dùng cho payload |
| **Unwrap Key** | Wrapped DEK + algorithm | Raw DEK | Lấy DEK để local decrypt |
| **Sign** | Digest/đầu vào theo API + signature algorithm | Digital signature | Xác nhận nguồn gốc/tính toàn vẹn của dữ liệu |
| **Verify** | Digest + signature + algorithm | Verification result | Xác minh chữ ký |
| **Get key** | Key name/version | Public metadata/key material được phép | Không phải xuất private key HSM ra ngoài |

**Mã hóa không tạo chữ ký số** và chữ ký số không làm nội dung bí mật. Dùng AEAD cho payload integrity; dùng signature khi cần bằng chứng nguồn gốc bên ký và mô hình PKI/trust phù hợp.

## 4. Vòng đời khóa trong Key Vault

### 4.1. Các trạng thái và thao tác

~~~mermaid
flowchart LR
    C["Create / import"]
    A["Enabled key version"]
    R["Rotate\nNew version"]
    D["Disabled / expired"]
    S["Soft-deleted"]
    RE["Recover"]
    P["Purge after rules"]
    C --> A
    A --> R
    R --> A
    A --> D
    A --> S
    D --> A
    S --> RE --> A
    S --> P
~~~

Đây là **sơ đồ khái niệm**, không có nghĩa mọi chuyển trạng thái đều tự do. Purge protection, retention, permissions, expiration, service restrictions và incident policy có thể ngăn một số bước.

### 4.2. Key version và thời hạn sử dụng

Key có thể có:

- **Name** ổn định như `invoice-kek`.
- **Version** mới sau rotation.
- **Enabled/disabled**.
- **Not-before (nbf)** và **expires (exp)**.
- **Allowed key operations** (`encrypt`, `decrypt`, `wrapKey`, `unwrapKey`, `sign`, `verify`) theo tính năng và policy.
- **Tags** phục vụ owner, data class và quản trị.
- **Rotation policy** với lịch/điều kiện theo loại key và khả năng dịch vụ.

**Thời điểm hết hạn khóa** và **dữ liệu đã mã hóa vẫn cần đọc trong 7 năm** là hai vấn đề khác. Nếu phiên bản khóa cũ bị tắt/xóa và không thể dùng để unwrap, ciphertext cũ có thể trở nên không thể giải mã mặc dù tệp còn nguyên.

### 4.3. Rotation an toàn

1. Đánh giá lý do rotation: lịch định kỳ, thay đổi compliance hoặc compromise.
2. Xác định key versions hiện có và dữ liệu tham chiếu mỗi version.
3. Tạo/rotate sang **key version mới** theo policy.
4. Chuyển **new encrypt/wrap** sang version mới.
5. **Giữ old versions** còn khả dụng cho old ciphertext cho tới khi **rewrap** hoàn tất hoặc retention kết thúc.
6. Với envelope encryption, **rewrap DEK** bằng KEK mới mà không cần tải/giải mã lại toàn bộ data file khi được thực hiện đúng quyền và quy trình.
7. Test dữ liệu mã hóa ở nhiều versions và rollback.
8. Chỉ disable/decommission old key version sau sign-off và inventory xác nhận không còn phụ thuộc.

Rotation **không tự động re-encrypt mọi Blob/DB ciphertext** được ứng dụng tự mã hóa. Với CMK tích hợp dịch vụ Azure, behavior/refresh khác theo resource integration và thiết lập; không suy từ đó sang app-managed envelope.

### 4.4. Soft delete và purge protection

- **Soft delete** giữ deleted vault/key objects trong retention window theo khả năng dịch vụ.
- **Purge protection** ngăn xóa vĩnh viễn trước khi retention kết thúc theo chính sách được áp dụng.
- **Recover** khác **purge**. Recover có thể khôi phục object đang soft-deleted nếu còn trong retention và đủ quyền.
- Không dùng quyền purge như thao tác dọn lab thông thường.
- Không giả định có thể tắt purge protection sau khi bật; thiết kế môi trường và retention ngay từ đầu.

Với hệ thống dùng **customer-managed keys (CMK)** cho Azure Storage, database hoặc compute, mất key có thể khiến resource không giải mã được dữ liệu. Soft delete/purge protection thường là điều kiện quan trọng trong thiết kế CMK.

### 4.5. Backup/restore key không phải tải private key

Key Vault có APIs **backup/restore key object** theo điều kiện hỗ trợ; bản backup thường được bảo vệ/mã hóa bởi dịch vụ và **không phải export plaintext private key**. Phạm vi restore có thể có ràng buộc về subscription, geography, vault type và key protection boundary. Phải kiểm thử trên đúng SKU/region và tuân thủ runbook DR.

Đối với khóa HSM-backed, không tự giả định có thể extract private key ở dạng PEM để chuyển sang mọi hệ thống khác. **Backup key + lưu ciphertext + giữ đúng key version/DEK manifest** mới tạo nên phương án phục hồi có ý nghĩa.

## 5. Azure RBAC, managed identity và phạm vi quyền

### 5.1. Phân biệt control plane và data plane

**Control plane (Azure Resource Manager):** tạo vault, cấu hình networking, tags, diagnostic settings, access model và tài nguyên.

**Data plane (Key Vault endpoint):** tạo/quản lý key, wrap/unwrap, encrypt/decrypt, sign/verify và các thao tác key/secret/cert cụ thể.

Một principal có Azure `Reader` trên resource group **không tự** có `unwrapKey`. Ngược lại, principal có quyền sửa cấu hình access policy legacy hoặc gán Azure RBAC role theo IAM có thể có **khả năng tăng quyền gián tiếp**; phải review quyền quản trị.

### 5.2. Những role thường dùng

| Built-in role | Mục đích chung | Không nên sử dụng khi |
| --- | --- | --- |
| **Key Vault Crypto User** | Thực hiện cryptographic operations với keys theo phạm vi được cấp | Không cần unwrap/decrypt nhưng role cấp quyền vượt nhu cầu |
| **Key Vault Crypto Officer** | Quản trị khóa và các crypto operations được hỗ trợ | Chỉ là runtime mã hóa dữ liệu |
| **Key Vault Administrator** | Quản trị data plane các đối tượng trong vault, rất mạnh | Ứng dụng business thông thường |
| **Key Vault Reader** | Đọc metadata của đối tượng theo role được hỗ trợ, không đọc giá trị secret hoặc private key | Muốn thao tác encrypt/unwrap |
| **Key Vault Secrets User** | Đọc giá trị secrets theo role | Chỉ cần sử dụng Key Vault keys |
| **Key Vault Crypto Service Encryption User** | Vai trò cho một số service integrations dùng CMK khi cấu hình phù hợp | Gắn cho mọi user/app không có tích hợp |
| **Azure Owner/User Access Administrator** | Có quyền liên quan role assignment ở ARM scope | Cấp mặc định cho workload |

Các role **không có semantics giống nhau**: kiểm tra `DataActions`/Key Vault RBAC support và scope. Một ứng dụng chỉ cần `wrapKey` có thể cần custom role hoặc chính sách được thiết kế phù hợp nếu built-in role quá rộng; tránh tự thêm `unwrapKey` nếu không có nghiệp vụ đọc giải mã.

### 5.3. RBAC và legacy access policies

Key Vault hỗ trợ các mô hình authorization tùy vault/configuration:

- **Azure RBAC authorization:** role assignments ở scope thích hợp, thường được ưu tiên cho cách quản trị quyền nhất quán.
- **Vault access policies (legacy):** permissions riêng của vault; có nguy cơ người quản trị control plane có quyền sửa policy rồi tự cấp quyền key/secret nếu không kiểm soát.

**Không trộn lẫn rằng cả RBAC và access policy luôn cùng được áp dụng như hai tầng.** Vault cấu hình authorization model nào sẽ có behavior tương ứng. Khi chuyển model ở production, cần preflight role assignments và tránh outage.

### 5.4. Managed identity cho Java

~~~text
Java application on Azure
  → Managed identity / workload identity
  → Microsoft Entra OAuth token
  → Key Vault HTTPS endpoint
  → Evaluate RBAC/data permissions + network
  → Crypto result
~~~

Ưu tiên identity theo **môi trường** và **chức năng**: `mi-orders-encrypt` có thể chỉ cần public encrypt/wrap; `mi-orders-decrypt` cần unwrap ở phạm vi được phê duyệt; operator rotation có identity riêng.

**Không cấp Key Vault Administrator cho runtime** chỉ để bỏ lỗi `403`. Cần kiểm tra principal object ID, assignment scope, role, propagation, vault firewall và đúng key operation.


## 6. Azure CLI: kiểm tra vault, tạo khóa và xem phiên bản

### 6.1. Điều kiện thực hành

- Azure subscription, resource group và **Key Vault lab** đã có và được phép sử dụng.
- Vault dùng Azure RBAC authorization hoặc bạn biết chính xác nó đang dùng legacy access policies.
- Người thực hiện thao tác quản trị key có quyền riêng; **ứng dụng runtime không cần quyền tạo/xóa keys**.
- DNS/TLS và firewall/Private Endpoint cho phép client đến endpoint vault.
- Trước khi tạo keys có phí hoặc HSM operations, xem SKU/region, ngân sách và resource owner.

Các lệnh trong bài chỉ là ví dụ; **không chạy trên production** hoặc vault có dữ liệu thật nếu chưa có approval.

### 6.2. Xác nhận Azure context

~~~bash
az login

az account show \
  --query "{subscription:name,subscriptionId:id,tenantId:tenantId}" \
  --output json

az account set --subscription "<SUBSCRIPTION_ID>"

RG="rg-crypto-lab"
VAULT="kv-crypto-lab-unique"
KEY_NAME="invoice-kek"

az keyvault show \
  --resource-group "$RG" \
  --name "$VAULT" \
  --output json
~~~

Kiểm tra authorization model, purge protection, soft-delete retention, network rules và location trong output thực. `az keyvault show` là metadata/control-plane; thành công ở đây **không chứng minh** quyền `unwrapKey` trên data plane.

### 6.3. Đọc khóa và các phiên bản

~~~bash
az keyvault key list \
  --vault-name "$VAULT" \
  --output table

az keyvault key show \
  --vault-name "$VAULT" \
  --name "$KEY_NAME" \
  --output json

az keyvault key list-versions \
  --vault-name "$VAULT" \
  --name "$KEY_NAME" \
  --output table
~~~

Các lệnh `key ...` yêu cầu network path và data-plane permissions phù hợp. Kết quả có thể có **public key** và key metadata nhưng không phải RSA private key plaintext. Không đưa endpoint/metadata nhạy cảm vào log không được bảo vệ.

### 6.4. Tạo RSA key 3072-bit trong vault lab

~~~bash
# THAO TÁC GHI: chỉ thực hiện nếu đã có quyền và approval.
az keyvault key create \
  --vault-name "$VAULT" \
  --name "$KEY_NAME" \
  --kty RSA \
  --size 3072 \
  --output json
~~~

`--kty RSA` tạo software-protected RSA key theo khả năng SKU. Nếu muốn HSM-backed RSA key và vault đủ điều kiện, phải chọn kiểu tương ứng như `RSA-HSM` khi Azure CLI/service hỗ trợ. **Vault Premium không làm mọi key tự chuyển sang HSM**.

Một vault lab nên có tên khóa riêng, không dùng key ID production. Không chạy tạo/rotate key nhiều lần để “test idempotency” mà chưa biết behavior của command với existing key version.

### 6.5. RBAC assignments đọc được khác quyền crypto

~~~bash
VAULT_ID=$(az keyvault show \
  --resource-group "$RG" \
  --name "$VAULT" \
  --query id -o tsv)

az role assignment list \
  --scope "$VAULT_ID" \
  --include-inherited \
  --output table
~~~

RBAC permission đến từ assignments trực tiếp, scope cha và group memberships; trong mô hình access policy cũ phải kiểm tra policy riêng. Kết quả `role assignment list` không tự thể hiện một test hiệu dụng cho mọi key operations.

### 6.6. Cấp Crypto User cho managed identity (khi được duyệt)

~~~bash
PRINCIPAL_OBJECT_ID="<MANAGED_IDENTITY_PRINCIPAL_OBJECT_ID>"

# THAY ĐỔI QUYỀN: chỉ do người có quyền IAM thực hiện.
az role assignment create \
  --assignee-object-id "$PRINCIPAL_OBJECT_ID" \
  --assignee-principal-type ServicePrincipal \
  --role "Key Vault Crypto User" \
  --scope "$VAULT_ID"
~~~

- ID phải là **principal object ID** của managed identity, không phải client ID/application ID.
- `Key Vault Crypto User` cấp các crypto operations được role định nghĩa; hãy đọc `DataActions`, vì role có thể rộng hơn nhu cầu chỉ wrap.
- Nếu chỉ một workload dùng vault, scope theo vault có thể phù hợp. Với nhiều workloads, cân nhắc phân tách vaults, keys hoặc roles/scopes khác được hỗ trợ.
- Role assignment có thể cần thời gian propagation; không tự nâng thành `Key Vault Administrator`.
- Access model đang là legacy access policies thì **role assignment có thể không tạo ra quyền data-plane như mong muốn** cho vault đó.

### 6.7. Đọc rotation policy

~~~bash
az keyvault key rotation-policy show \
  --vault-name "$VAULT" \
  --name "$KEY_NAME" \
  --output json

az keyvault key rotate --help
az keyvault key rotation-policy update --help
~~~

Bài học chỉ dùng lệnh `show` để đọc. Không tự chạy rotate/delete/disable/purge trên vault chứa dữ liệu thật. Khi thiết lập automatic rotation, xem tính năng hỗ trợ theo key type/SKU/version, lịch/thông báo và yêu cầu ứng dụng giữ old key versions cho decrypt.

### 6.8. Khi vô hiệu hóa hoặc xóa old key version

Trước khi thay đổi:

1. Tìm các envelope records còn tham chiếu version đó.
2. Chạy decrypt/unwrap regression tests trên old ciphertext.
3. Rewrap wrapped DEKs sang KEK version mới nếu chính sách yêu cầu.
4. Xác nhận backup, retention và purge protection.
5. Có change approval và rollback plan.
6. Chỉ sau đó mới disable key version theo lịch.

**Thao tác xóa key và purge không phải housekeeping thông thường.** Xóa nhầm khóa không thể thay bằng một khóa mới có cùng tên để giải mã dữ liệu trước đó.

## 7. Java SDK cho Azure Key Vault Keys

### 7.1. Dependencies trong Maven

~~~xml
<dependencies>
    <dependency>
        <groupId>com.azure</groupId>
        <artifactId>azure-security-keyvault-keys</artifactId>
    </dependency>
    <dependency>
        <groupId>com.azure</groupId>
        <artifactId>azure-identity</artifactId>
    </dependency>
</dependencies>
~~~

Các dependencies cần versions do Maven parent POM/`dependencyManagement` hoặc Azure SDK BOM quản lý. Ví dụ:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
    <azure.sdk.bom.version>REPLACE_WITH_APPROVED_BOM_VERSION</azure.sdk.bom.version>
</properties>

<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.azure</groupId>
            <artifactId>azure-sdk-bom</artifactId>
            <version>${azure.sdk.bom.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Sau khi lưu vào `pom.xml`, cần dùng đúng Maven property chứa dấu dollar, dấu ngoặc nhọn và tên `azure.sdk.bom.version`. BOM version phải là phiên bản được duyệt, không copy nguyên placeholder. Với Java 17+, kiểm tra tương thích thư viện và Java compiler.

### 7.2. Cấu hình và xác thực

~~~text
KEY_VAULT_URL=https://kv-crypto-lab-unique.vault.azure.net/
KEY_NAME=invoice-kek
~~~

Sử dụng `DefaultAzureCredential` để có token của Microsoft Entra ID. Trong local dev, credential có thể đến từ Azure CLI/IDE. Ở Azure App Service, Container Apps hoặc AKS, chọn **managed/workload identity** phù hợp và kiểm tra principal đang được dùng thực sự.

### 7.3. KeyClient và CryptographyClient

~~~java
import com.azure.core.credential.TokenCredential;
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.security.keyvault.keys.KeyClient;
import com.azure.security.keyvault.keys.KeyClientBuilder;
import com.azure.security.keyvault.keys.models.KeyVaultKey;
import com.azure.security.keyvault.keys.cryptography.CryptographyClient;
import com.azure.security.keyvault.keys.cryptography.CryptographyClientBuilder;

public final class VaultClients {
    private VaultClients() {}

    public static TokenCredential credential() {
        return new DefaultAzureCredentialBuilder().build();
    }

    public static KeyClient keyClient(
            String vaultUrl, TokenCredential credential) {
        return new KeyClientBuilder()
            .vaultUrl(vaultUrl)
            .credential(credential)
            .buildClient();
    }

    public static CryptographyClient forVersion(
            String keyVersionId, TokenCredential credential) {
        return new CryptographyClientBuilder()
            .keyIdentifier(keyVersionId)
            .credential(credential)
            .buildClient();
    }

    public static String latestKeyId(
            KeyClient client, String name) {
        KeyVaultKey key = client.getKey(name);
        return key.getId(); // includes version
    }
}
~~~

**Giới hạn quan trọng:**

- `getKey` cần permission đọc key metadata tương ứng; không suy từ data role chung rằng mọi API sẽ thành công.
- `CryptographyClient` được xây từ **versioned key identifier** khi dữ liệu cần decrypt lâu dài. Versionless ID thích hợp với một số luồng encrypt/wrap “latest” nhưng phải đọc/ghi lại version thực.
- Không nhận tùy ý `vaultUrl` hoặc `keyVersionId` từ HTTP request rồi cấp quyền unwrap; phải allowlist vault/key cho tenant/workload.
- Nên chia sẻ clients/HTTP transport và token provider theo lifecycle, không tạo cho mỗi byte hoặc mỗi câu lệnh.
- Các SDK có thể tối ưu thao tác public-key ở local; đừng suy rằng mọi lệnh trên `CryptographyClient` đều là một remote HTTP request.

### 7.4. Tạo khóa trong Java chỉ dành cho provisioning

~~~java
import com.azure.security.keyvault.keys.KeyClient;
import com.azure.security.keyvault.keys.models.KeyVaultKey;

KeyVaultKey created = keyClient.createRsaKey("invoice-kek");
System.out.println("Key version ID: " + created.getId());
~~~

Đây là đoạn code minh họa bên trong context có sẵn `keyClient`. **Không chạy tạo khóa trong request handler**; runtime identity không nên có quyền create/rotate/delete. Để chọn key size, type, operations, tags, expiration, sử dụng options API hoặc provisioning IaC tương ứng đã kiểm tra SDK version.


## 8. Mã hóa và giải mã một thông điệp nhỏ với RSA-OAEP-256

### 8.1. Java mẫu có thể dùng trong lab

~~~java
import com.azure.core.credential.TokenCredential;
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.security.keyvault.keys.cryptography.CryptographyClient;
import com.azure.security.keyvault.keys.cryptography.CryptographyClientBuilder;
import com.azure.security.keyvault.keys.cryptography.models.EncryptionAlgorithm;
import com.azure.security.keyvault.keys.cryptography.models.EncryptResult;
import com.azure.security.keyvault.keys.cryptography.models.DecryptResult;

import java.nio.charset.StandardCharsets;
import java.util.Arrays;

public final class RsaSmallMessageDemo {
    public static void main(String[] args) {
        String keyId = System.getenv("KEY_VERSIONED_ID");
        if (keyId == null || keyId.isBlank()) {
            throw new IllegalStateException("KEY_VERSIONED_ID required");
        }

        TokenCredential credential =
            new DefaultAzureCredentialBuilder().build();
        CryptographyClient crypto =
            new CryptographyClientBuilder()
                .keyIdentifier(keyId)
                .credential(credential)
                .buildClient();

        byte[] plaintext = "Mã đơn hàng thử nghiệm"
            .getBytes(StandardCharsets.UTF_8);

        EncryptResult encrypted =
            crypto.encrypt(EncryptionAlgorithm.RSA_OAEP_256, plaintext);
        DecryptResult decrypted =
            crypto.decrypt(
                EncryptionAlgorithm.RSA_OAEP_256,
                encrypted.getCipherText()
            );

        System.out.println(
            "Round-trip valid: " +
            Arrays.equals(plaintext, decrypted.getPlainText())
        );

        // Không ghi plaintext/ciphertext/credential vào logs.
        Arrays.fill(plaintext, (byte) 0);
    }
}
~~~

**Chỉ dùng với RSA key và payload đủ nhỏ**. Với RSA-2048 + OAEP-SHA256, plaintext giới hạn 190 bytes. RSA key phải có algorithm/key operations phù hợp; app identity cần crypto permissions. Số byte UTF-8, **không phải số ký tự**, mới quyết định giới hạn đầu vào.

### 8.2. Lưu ciphertext cần những metadata gì?

~~~json
{
  "formatVersion": 1,
  "algorithm": "RSA-OAEP-256",
  "keyId": "https://kv-crypto-lab-unique.vault.azure.net/keys/invoice-kek/EXAMPLE_VERSION",
  "ciphertextBase64": "BASE64_EXAMPLE"
}
~~~

Đây là **cấu trúc dữ liệu minh họa**, không phải giá trị mã hóa hợp lệ. Key ID phải tham chiếu version đã dùng và được kiểm tra thuộc vault/key đã cho phép. Payload có thể lưu ở Blob Storage/DB, nhưng vẫn cần business authorization và data protection.

### 8.3. Vì sao không chia PDF thành nhiều đoạn RSA?

Mã hóa từng block nhỏ bằng RSA rồi ghép thủ công:

- Tạo nhiều crypto operations và độ trễ/chi phí cao.
- Không tự tạo một định dạng file authenticated, không có toàn vẹn liên khối.
- Giới hạn key size/padding phức tạp, dễ lỗi.
- Làm rotation và chuyển vùng khó hơn.

Giải pháp thực tiễn: **hybrid/envelope encryption** với AES-GCM cho nội dung và RSA key chỉ để **wrap/unwrap DEK**.

## 9. Wrap và unwrap một khóa AES

### 9.1. Key Wrap operations

`wrapKey` nhận raw DEK ngắn và trả **wrapped DEK**. `unwrapKey` nhận wrapped DEK và trả raw DEK cho ứng dụng được phép gọi.

~~~java
import com.azure.core.credential.TokenCredential;
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.security.keyvault.keys.cryptography.CryptographyClient;
import com.azure.security.keyvault.keys.cryptography.CryptographyClientBuilder;
import com.azure.security.keyvault.keys.cryptography.models.KeyWrapAlgorithm;
import com.azure.security.keyvault.keys.cryptography.models.WrapResult;
import com.azure.security.keyvault.keys.cryptography.models.UnwrapResult;

import javax.crypto.KeyGenerator;
import java.security.MessageDigest;
import java.util.Arrays;

public final class RsaWrapDemo {
    public static void main(String[] args) throws Exception {
        String keyId = System.getenv("KEY_VERSIONED_ID");
        TokenCredential credential =
            new DefaultAzureCredentialBuilder().build();
        CryptographyClient crypto =
            new CryptographyClientBuilder()
                .keyIdentifier(keyId)
                .credential(credential)
                .buildClient();

        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(256);
        byte[] dek = generator.generateKey().getEncoded();

        WrapResult wrapped = crypto.wrapKey(
            KeyWrapAlgorithm.RSA_OAEP_256, dek
        );
        UnwrapResult unwrapped = crypto.unwrapKey(
            KeyWrapAlgorithm.RSA_OAEP_256,
            wrapped.getEncryptedKey()
        );

        System.out.println(
            "DEK matches: " +
            MessageDigest.isEqual(dek, unwrapped.getKey())
        );

        Arrays.fill(dek, (byte) 0);
        Arrays.fill(unwrapped.getKey(), (byte) 0);
    }
}
~~~

**Lưu ý:** `Arrays.fill` chỉ cố xóa những mảng được tham chiếu trong code; **JVM/SDK có thể đã tạo bản sao**. Không khẳng định plaintext DEK đã bị xóa hoàn toàn khỏi mọi bộ nhớ. Raw DEK không được gửi vào logs, traces, message queues hoặc client browser.

### 9.2. KEK, DEK và wrapped DEK

| Thành phần | Lưu ở đâu? | Ai được dùng? |
| --- | --- | --- |
| **KEK** (RSA private key) | Key Vault/ranh giới HSM theo cấu hình | Chỉ cryptographic operations đã được ủy quyền |
| **DEK** (AES-256) | Tạm trong bộ nhớ ứng dụng khi xử lý | Runtime đã được xác thực, ủy quyền |
| **Wrapped DEK** | Envelope metadata/DB/Blob | Bảo vệ integrity và access policy |
| **Ciphertext** | Blob Storage/DB | Chỉ đọc bởi principals được phép |
| **Key version ID** | Envelope metadata | Cần allowlist và xác minh đúng vault/key |
| **AAD/IV/tag** | Envelope theo schema đã xác định | AAD phải khớp khi decrypt, IV phải không lặp với DEK |

Wrapped DEK **không phải plaintext secret**, nhưng cũng không nên public hóa metadata/số định danh đối tượng vì thông tin có thể hỗ trợ attacker. Cần bảo vệ storage và không cấp `unwrapKey` quá rộng.

### 9.3. Nguyên tắc phân quyền tách đọc và ghi

Một application chỉ cần **encrypt/write** nên cân nhắc:

- Được tạo/sinh DEK cục bộ.
- Được `wrapKey` bằng KEK được phê duyệt.
- Được ghi ciphertext/wrapped DEK vào storage phù hợp.
- **Không nhất thiết cần `unwrapKey`** nếu không phục vụ download/decrypt.

Một application chỉ cần **decrypt/read** cần quyền đọc ciphertext, `unwrapKey` và **business authorization**. Có thể dùng custom role/identity/vault riêng để tách hai đường quyền khi hỗ trợ và cần thiết, không dựa vào tên `Key Vault Crypto User` như thể nó mặc định “wrap-only”.

### 9.4. Không tạo lại KEK khi đọc dữ liệu cũ

Khi một version bị mất, gọi tạo key mới cùng tên không tái tạo private key đã dùng trước đó. Wrapped DEK là kết quả của **key material cụ thể**, không chỉ key name. Do đó version pinning, key backup/recovery và retention là yêu cầu cốt lõi.

## 10. Envelope encryption cho file và object

### 10.1. Các bước upload một object

1. API xác thực user và tenant; tính policy mã hóa của object.
2. Tạo **AES-256 DEK mới** bằng secure random provider.
3. Tạo **IV 12 bytes mới**, AAD là representation ổn định của tenant/object ID và schema.
4. Mã hóa plaintext bằng **AES/GCM/NoPadding**, thu ciphertext **kèm authentication tag**.
5. Dùng Key Vault `wrapKey` với RSA-OAEP-256 và **versioned KEK ID**.
6. Lưu ciphertext ở Blob Storage và envelope: `keyId`, `algorithm`, `wrappedDek`, `iv`, `aadVersion`, tag format.
7. Lưu trạng thái object READY trong DB sau khi dữ liệu và metadata đã commit/verify.
8. Không ghi DEK, plaintext hoặc full decrypted content vào logs.

~~~mermaid
flowchart TB
    P["Plaintext file"]
    D["Random AES DEK 256 bits"]
    N["Unique IV + stable AAD"]
    AES["AES-256-GCM"]
    KV["Key Vault RSA KEK\nwrapKey"]
    C["Ciphertext + GCM tag"]
    W["Wrapped DEK"]
    E["Envelope metadata\nkey version ID, IV, AAD version"]
    P --> AES
    D --> AES
    N --> AES
    D --> KV
    AES --> C
    KV --> W
    W --> E
    N --> E
    C --> S["Blob / data store"]
    E --> S
~~~

### 10.2. Ví dụ Java hoàn chỉnh cho payload nhỏ, theo cách envelope

Để người học nắm rõ thứ tự, ví dụ dưới đây giữ payload trong byte array **chỉ cho lab**. Với file lớn, dùng thiết kế streaming/chunked AEAD an toàn đã được kiểm định, không dùng `Files.readAllBytes` hàng GiB.

~~~java
import com.azure.core.credential.TokenCredential;
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.security.keyvault.keys.cryptography.CryptographyClient;
import com.azure.security.keyvault.keys.cryptography.CryptographyClientBuilder;
import com.azure.security.keyvault.keys.cryptography.models.KeyWrapAlgorithm;

import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.SecretKeySpec;

import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.util.Arrays;

public final class EnvelopeCryptoDemo {
    private static final SecureRandom RNG = new SecureRandom();
    private static final String WRAP_ALGORITHM = "RSA-OAEP-256";
    private static final int GCM_TAG_BITS = 128;
    private static final int GCM_IV_BYTES = 12;

    // Trong production cần serialization versioned, bounds checks,
    // authentication và storage schema được kiểm định riêng.
    public record Envelope(
        String keyVersionId,
        byte[] iv,
        byte[] wrappedDek,
        byte[] ciphertextAndTag
    ) {}

    private static CryptographyClient crypto(String keyVersionId) {
        TokenCredential credential =
            new DefaultAzureCredentialBuilder().build();
        return new CryptographyClientBuilder()
            .keyIdentifier(keyVersionId)
            .credential(credential)
            .buildClient();
    }

    private static byte[] aad(String tenantId, String objectId) {
        // Chỉ sử dụng các IDs server-side đã validate theo schema.
        String canonical = "v1|tenant=" + tenantId + "|object=" + objectId;
        return canonical.getBytes(StandardCharsets.UTF_8);
    }

    public static Envelope encrypt(
            String approvedKeyVersionId,
            String tenantId,
            String objectId,
            byte[] plaintext) throws Exception {

        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(256);
        SecretKey dek = generator.generateKey();
        byte[] rawDek = dek.getEncoded();

        try {
            byte[] iv = new byte[GCM_IV_BYTES];
            RNG.nextBytes(iv);

            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(
                Cipher.ENCRYPT_MODE, dek,
                new GCMParameterSpec(GCM_TAG_BITS, iv)
            );
            cipher.updateAAD(aad(tenantId, objectId));
            byte[] ciphertextAndTag = cipher.doFinal(plaintext);

            byte[] wrapped = crypto(approvedKeyVersionId)
                .wrapKey(KeyWrapAlgorithm.RSA_OAEP_256, rawDek)
                .getEncryptedKey();

            return new Envelope(
                approvedKeyVersionId, iv, wrapped, ciphertextAndTag
            );
        } finally {
            Arrays.fill(rawDek, (byte) 0);
        }
    }

    public static byte[] decrypt(
            Envelope envelope,
            String authorizedTenantId,
            String authorizedObjectId) throws Exception {

        // IMPORTANT: thực thi business authorization bên ngoài hàm này.
        // Validate/allowlist keyVersionId trước khi mở client.
        byte[] rawDek = crypto(envelope.keyVersionId())
            .unwrapKey(
                KeyWrapAlgorithm.RSA_OAEP_256,
                envelope.wrappedDek()
            ).getKey();

        try {
            SecretKey dek = new SecretKeySpec(rawDek, "AES");
            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(
                Cipher.DECRYPT_MODE, dek,
                new GCMParameterSpec(GCM_TAG_BITS, envelope.iv())
            );
            cipher.updateAAD(aad(
                authorizedTenantId, authorizedObjectId
            ));
            return cipher.doFinal(envelope.ciphertextAndTag());
        } finally {
            Arrays.fill(rawDek, (byte) 0);
        }
    }

    public static void main(String[] args) throws Exception {
        String approvedId = System.getenv("KEY_VERSIONED_ID");
        if (approvedId == null || approvedId.isBlank()) {
            throw new IllegalStateException("KEY_VERSIONED_ID required");
        }

        byte[] message = "Hóa đơn demo, không có PII"
            .getBytes(StandardCharsets.UTF_8);

        Envelope e = encrypt(approvedId, "tenant01", "order123", message);
        byte[] roundtrip = decrypt(e, "tenant01", "order123");

        System.out.println(
            "Envelope validated: " + Arrays.equals(message, roundtrip)
        );

        Arrays.fill(message, (byte) 0);
        Arrays.fill(roundtrip, (byte) 0);
    }
}
~~~

### 10.3. Giải thích vì sao code vẫn là lab, chưa phải production library

- `crypto(...)` tạo client/credential cho mỗi call: production nên **tái sử dụng** credential/client theo key version với lifecycle/connection pooling an toàn.
- Mẫu chưa serialize envelope sang JSON/binary, chưa validate length/encoding, IV length, algorithm ID, key ID allowlist và dữ liệu untrusted.
- Mẫu giữ toàn plaintext/ciphertext trong RAM: **không dùng cho file lớn**.
- Trong `encrypt`, `finally` cố xóa bản sao `rawDek` kể cả khi `wrapKey` lỗi. Production vẫn cần xử lý exception, memory-copy risk và client lifecycle kỹ hơn.
- Java/JCE/SDK có thể giữ bản sao của key/byte arrays; `Arrays.fill` là giảm rủi ro, không phải bảo đảm zeroization hoàn toàn.
- Mã ví dụ không giải quyết **multi-tenant authorization**, rate limiting, content scanning, key permissions hoặc atomic consistency Blob ↔ DB.
- Nonce được tạo random và DEK mới cho từng object. Khi triển khai **chunked stream**, không được copy cùng IV/DEK cho mọi chunks.
- AAD dùng chuỗi canonical ở mục ví dụ; ngoài thực tế phải validate IDs (hoặc length-prefix/binary encoding) để tránh ambiguous representations khi có ký tự phân cách.
- `Cipher.doFinal` ở decrypt sẽ báo lỗi nếu tag sai; **không bỏ xác thực tag** để cố đọc plaintext.
- Không tự tạo key ID từ HTTP request. Enforce vault/key/tenant allowlist trước khi giải mã.

### 10.4. Cấu trúc envelope lưu cùng object

~~~json
{
  "schemaVersion": 1,
  "dataAlgorithm": "AES-256-GCM",
  "keyWrapAlgorithm": "RSA-OAEP-256",
  "kekVersionId": "https://kv-crypto-lab-unique.vault.azure.net/keys/invoice-kek/EXAMPLE_VERSION",
  "ivBase64": "BASE64_12_BYTE_IV",
  "wrappedDekBase64": "BASE64_RSA_WRAPPED_DEK",
  "ciphertextFormat": "ciphertext-followed-by-16-byte-gcm-tag",
  "aadVersion": 1,
  "tenantObjectReference": "opaque-object-id"
}
~~~

Đây là **schema minh họa**, không phải cú pháp Azure Key Vault API. Ký hiệu Base64 là placeholders; **không được upload envelope giả rồi coi đã mã hóa thành công**. Các fields không mã hóa phải được ràng buộc bằng authenticated metadata/AAD hoặc cơ chế integrity phù hợp. Mặc dù IV có thể public, **IV reuse với cùng DEK** là lỗi nghiêm trọng.

### 10.5. Khi app tải hóa đơn xuống

1. Xác thực user/session và quyền đọc hóa đơn.
2. Tra object ID từ DB, lấy ciphertext và envelope đã được phê duyệt.
3. Validate schema, algorithm, vault/key ID/version, size limits và tenant binding.
4. Dùng `unwrapKey` trên **key version được lưu**.
5. Giải mã AES-GCM với đúng AAD; kiểm tra tag trong `doFinal`.
6. Nếu thất bại, **không trả plaintext một phần** và không tự thử bỏ AAD/tag.
7. Trả response qua kênh TLS và theo chính sách Content-Disposition/headers.
8. Ghi audit metadata về operation, principal, object ID, outcome; không ghi raw DEK/plaintext.

### 10.6. Đối với file hàng GiB

Không dùng `Cipher#doFinal` trên toàn byte array hoặc tải file vào RAM. Hai cách tiếp cận phù hợp hơn:

- Dùng giải pháp **streaming AEAD được kiểm chứng** với chunk numbers/IV derivation/chunk tags và manifest authenticated, có failure cleanup.
- Sử dụng **dịch vụ mã hóa at rest** của Azure với CMK nếu yêu cầu chỉ là bảo vệ dữ liệu lưu trữ, không bắt buộc app-level ciphertext.

Một thiết kế “tự chia AES-GCM thành các chunk rồi tái dùng cùng IV” là **không an toàn**. Với nhu cầu streaming nghiêm ngặt, chọn thư viện/protocol chuẩn hóa đã được security review thay vì tự xây cryptographic framing.


## 11. Chữ ký số: sign/verify khác encrypt/decrypt

### 11.1. Trường hợp cần chữ ký

Một batch ETL xuất dữ liệu đối soát. Ứng dụng cần xác minh **manifest được ký bởi một hệ thống đã ủy quyền** và không bị sửa sau khi phát hành.

- **Hash:** rút gọn dữ liệu thành digest; bản thân hash không chứng minh ai tạo dữ liệu.
- **Sign:** dùng private key/crypto operation được ủy quyền để tạo chữ ký trên digest theo signature algorithm.
- **Verify:** xác minh chữ ký bằng public key tương ứng.
- **Encrypt:** giữ bí mật nội dung; **không phải** chữ ký.

### 11.2. Java mẫu ký SHA-256 digest bằng RSA

~~~java
import com.azure.core.credential.TokenCredential;
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.security.keyvault.keys.cryptography.CryptographyClient;
import com.azure.security.keyvault.keys.cryptography.CryptographyClientBuilder;
import com.azure.security.keyvault.keys.cryptography.models.SignatureAlgorithm;
import com.azure.security.keyvault.keys.cryptography.models.SignResult;
import com.azure.security.keyvault.keys.cryptography.models.VerifyResult;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;

public final class SignVerifyDemo {
    public static void main(String[] args) throws Exception {
        String keyId = System.getenv("SIGN_KEY_VERSIONED_ID");
        TokenCredential credential =
            new DefaultAzureCredentialBuilder().build();

        CryptographyClient crypto =
            new CryptographyClientBuilder()
                .keyIdentifier(keyId)
                .credential(credential)
                .buildClient();

        byte[] payload = "approved-manifest-v1"
            .getBytes(StandardCharsets.UTF_8);

        byte[] digest =
            MessageDigest.getInstance("SHA-256").digest(payload);

        SignResult signature =
            crypto.sign(SignatureAlgorithm.RS256, digest);

        VerifyResult verification = crypto.verify(
            SignatureAlgorithm.RS256,
            digest,
            signature.getSignature()
        );

        System.out.println("Signature valid: " + verification.isValid());
    }
}
~~~

**Lưu ý:** `RS256` là thuật toán ký RSA với SHA-256 theo ngữ nghĩa SDK, không phải RSA-OAEP encryption. Với thiết kế mới, đánh giá RSA-PSS (`PS256` khi hỗ trợ) hoặc ECDSA theo security policy. Phải **cố định public key/version và trust chain phù hợp**, không cho người gửi tự chọn một key bất kỳ rồi tự xác minh bằng chính public key ấy và gọi đó là trusted signature.

### 11.3. Ký manifest, không ký từng byte truyền bằng HTTP

Với file lớn, ứng dụng có thể hash theo streaming thành SHA-256 digest, sau đó gọi `sign` trên digest thay vì gửi toàn file vào Key Vault. Manifest nên ghi:

~~~json
{
  "manifestVersion": 1,
  "objectId": "file-123",
  "sha256": "HEX_SHA256_OF_FILE",
  "signatureAlgorithm": "RS256",
  "signingKeyVersionId": "https://kv-crypto-lab-unique.vault.azure.net/keys/signing-key/EXAMPLE_VERSION",
  "signatureBase64": "BASE64_SIGNATURE"
}
~~~

Cần định nghĩa **canonical serialization** của bytes được ký. Nếu khi ký dùng digest của file nhưng khi verify lại hash chuỗi JSON khác định dạng, signature mismatch không nhất thiết do bị sửa dữ liệu.

**Chữ ký xác nhận nguồn gốc theo quyền giữ private key**, không chứng minh quá trình tạo dữ liệu ban đầu không có lỗi nghiệp vụ. Phải bảo vệ permission `sign` để không có service ngoài ý định ký tài liệu giả.

## 12. Rotation, key-version pinning và rewrap dữ liệu

### 12.1. Tình huống một KEK qua ba phiên bản

~~~text
invoice-kek / V1  → wrapped DEK for invoices from Jan–Apr
invoice-kek / V2  → wrapped DEK for invoices from May–Aug
invoice-kek / V3  → new writes from Sep onward
~~~

Nếu chương trình decrypt mọi hóa đơn cũ bằng `getKey("invoice-kek")` rồi lấy V3, các DEK được bọc bằng V1/V2 **không thể unwrap đúng chỉ với V3**. Metadata phải chứa **key identifier và version cụ thể** đã dùng.

### 12.2. Rotation KEK có thể không cần đổi payload ciphertext

Với AES-GCM ciphertext đã được mã hóa bằng một DEK:

1. Đọc `oldKeyVersionId` và `wrappedDekOld`.
2. Xác thực record, quyền của operator và khóa mới.
3. Dùng `unwrapKey` bằng **KEK version cũ**, thu raw DEK trong môi trường tin cậy.
4. Dùng `wrapKey` bằng **KEK version mới**.
5. Ghi `wrappedDekNew` và `newKeyVersionId` vào envelope một cách **atomically/conditional** theo cơ chế DB/Blob metadata.
6. Xác minh unwrap bằng new version và giải mã sample ciphertext.
7. Giữ old KEK version cho tới khi mọi records đã chuyển xong/retention kết thúc.

**Payload ciphertext và IV có thể giữ nguyên** nếu DEK không đổi. Đây là **rewrap**, không phải thay DEK hay re-encrypt toàn bộ dữ liệu.

### 12.3. Runbook rewrap an toàn

~~~mermaid
flowchart TD
    A["Read envelope metadata"]
    B["Validate tenant, object and old key ID"]
    C["Unwrap with old KEK version"]
    D["Wrap same DEK with new KEK version"]
    E["Conditional update of envelope"]
    F["Read back + sample decrypt"]
    G{"Validation PASS?"}
    H["Mark rewrapped / record audit"]
    X["Stop / rollback to old metadata"]
    A --> B --> C --> D --> E --> F --> G
    G -->|"Yes"| H
    G -->|"No"| X
~~~

**Điểm khó:** không được để cùng một record chuyển metadata sang new key ID **trước khi** wrapped DEK mới được lưu thành công. Nếu update xảy ra qua nhiều đối tượng/DB, dùng transaction/ETag phù hợp, trạng thái chuyển đổi và reconciliation worker. Không tự xóa old key version trong khi còn records chưa migrate.

### 12.4. Nếu cần đổi cả DEK

Rekey khác rewrap. Đổi DEK nghĩa là phải:

- Giải mã toàn bộ payload cũ bằng old DEK.
- Tạo DEK/IV mới.
- Mã hóa lại payload.
- Wrap DEK mới với KEK/version mục tiêu.
- Commit ciphertext + envelope đồng bộ theo thiết kế.
- Kiểm tra integrity, retention và cleanup old ciphertext.

Đây là quá trình tốn băng thông/compute và có rủi ro outage cao hơn rewrap. **Nếu lộ raw DEK**, chỉ rewrap DEK cũ bằng KEK mới **không khắc phục** việc DEK đã lộ; phải **re-encrypt bằng DEK mới** theo incident plan.

### 12.5. Crypto-erasure và key deletion

Việc hủy khả năng truy cập một key có thể làm ciphertext không thể giải mã, nhưng gọi đó là **crypto-erasure** chỉ khi thỏa mô hình: không còn bản sao của DEK, KEK, backup/versions và không có plaintext copy ở nơi khác. Soft delete/purge protection có thể giữ khả năng recovery theo chính sách; **không dùng key deletion như cách xóa dữ liệu kinh doanh hàng ngày** mà không có review pháp lý/backup.

### 12.6. Thay khóa sau compromise

- Nếu principal có `unwrapKey` bị lộ, giả định các DEKs/ciphertexts mà principal có thể đọc đã có nguy cơ.
- Nếu raw DEK bị lộ, cần re-encrypt affected objects bằng **DEK mới**.
- Nếu signer key bị lộ, cần revoke trust, thay key/version và đánh giá chữ ký đã cấp.
- Nếu vault key bị disable do nhầm lẫn nhưng chưa bị lộ, ưu tiên recovery/reenable theo approval thay vì tự tạo key cùng tên.
- Ghi incident timeline, authorization scope, audit logs và kết quả xác minh trước khi đóng sự cố.

## 13. CMK tích hợp dịch vụ Azure so với app-level envelope encryption

### 13.1. Hai mô hình khác nhau

**Mô hình A — Customer-managed key (CMK) cho service encryption at rest**

~~~text
Java application
  → Azure Blob Storage / Azure SQL / other service
  → Service-side storage encryption
  → Azure Key Vault KEK / identity integration theo cấu hình
~~~

Ứng dụng thường **không cần tự decrypt mọi file**. Dịch vụ Azure được cấu hình nhận key ID, identity và permissions phù hợp để quản lý encryption-at-rest, với điều kiện/giới hạn theo từng loại service.

**Mô hình B — Application-level envelope encryption**

~~~text
Java application
  → AES-GCM encrypt data before storage
  → Key Vault wraps DEK
  → Blob/DB stores only application ciphertext + envelope
~~~

Dữ liệu đã bị mã hóa **trước khi đến storage**; ứng dụng chịu trách nhiệm key-envelope format, integrity, rotation, phân quyền giải mã và restore.

### 13.2. So sánh

| Tiêu chí | CMK service-side | App-level envelope |
| --- | --- | --- |
| Ai mã hóa payload? | Azure service theo cơ chế tích hợp | Ứng dụng/thư viện |
| Thay đổi code ứng dụng | Thường ít hơn | Nhiều: crypto format, AAD, streaming |
| Key Vault operations | Do service integration thực hiện | Ứng dụng gọi wrap/unwrap |
| Chỉ riêng data owner giải mã? | Phụ thuộc data access/identity ở service | Có thể tách quyền giải mã ở tầng app |
| Rotation | Theo cơ chế refresh/key URI của dịch vụ | Ứng dụng phải quản lý key versions và rewrap |
| Search/query nội dung | Service có thể xử lý plaintext theo tính năng | Ciphertext có thể không query trực tiếp |
| Audit | Service/key operations theo integration | App-level access + Vault diagnostics |
| Sự cố mất key | Service có thể không truy cập dữ liệu | App không unwrap được DEK |
| Complexity | Tương đối thấp hơn | Tương đối cao hơn |

Không kết luận CMK **tự động** tạo tenant isolation hoặc ngăn Azure resource admins có quyền data plane đọc nội dung. CMK không thay access controls của storage/database.

### 13.3. Gán quyền cho service-managed identity

Tùy Azure resource (ví dụ Storage dùng key do khách hàng quản lý), service cần identity và key permissions/role được hỗ trợ như **Key Vault Crypto Service Encryption User** hoặc tương đương. Kiểm tra chính xác RBAC data actions, Key Vault firewall/Private Endpoint và key URI/rotation behavior của **từng tích hợp**, không cấp `Key Vault Administrator` cho service.

### 13.4. Khi nào dùng cả hai lớp?

Một doanh nghiệp có thể dùng **Storage encryption at rest bằng CMK** và đồng thời **mã hóa nội dung rất nhạy cảm bằng AES-GCM phía app**. Đây là hai lớp với key management, cost và recovery riêng. Chỉ triển khai khi threat model và compliance yêu cầu rõ; crypto tự chế làm tăng rủi ro nếu không có đội ngũ review giao thức, key lifecycle và incident handling.

## 14. Mạng, Private Endpoint và bảo vệ key access

### 14.1. Private Link không thay quyền

Key Vault có endpoint chính thức:

~~~text
https://kv-orders-prod.vault.azure.net/
~~~

Khi bật Private Endpoint, VNet và DNS được thiết kế để hostname này có thể phân giải theo đường riêng. Private DNS Zone thường sử dụng:

~~~text
privatelink.vaultcore.azure.net
~~~

Ứng dụng **vẫn dùng vault hostname chuẩn**. Không thay thành IP private để giải quyết DNS, vì TLS cần hostname/certificate verification. Không tắt certificate validation khi gặp lỗi.

### 14.2. Hai điều kiện độc lập

| Câu hỏi | Công cụ kiểm soát |
| --- | --- |
| Principal có được gọi `unwrapKey` trên key này không? | Entra identity + Key Vault data-plane RBAC/access model |
| Request có đi từ network/source được phép không? | Firewall, Private Endpoint, DNS, route, trusted services exceptions nếu có |
| User cuối có được giải mã object này không? | Business authorization trong app |
| Có cần chứng minh ai thực hiện thao tác không? | Audit logs và correlation IDs |

Một identity có quyền Crypto User nhưng nằm ngoài network path hợp lệ vẫn có thể bị chặn. Một pod nằm trong VNet có Private Endpoint nhưng không có data role vẫn có thể nhận 403. Không bật public network access `All networks` để chữa một RBAC error.

### 14.3. Kiểm tra DNS/TCP từ đúng client

Linux:

~~~bash
VAULT_HOST="kv-orders-prod.vault.azure.net"
nslookup "$VAULT_HOST"
nc -vz "$VAULT_HOST" 443
~~~

PowerShell:

~~~powershell
Resolve-DnsName kv-orders-prod.vault.azure.net
Test-NetConnection kv-orders-prod.vault.azure.net -Port 443
~~~

Những lệnh này chỉ kiểm tra DNS/TCP, **không xác nhận thao tác crypto được ủy quyền**. Phải test bằng identity của workload ở đúng VNet/region, không chỉ từ laptop.

### 14.4. Quy tắc chống cấu hình sai

- Không ghi client secret trong `application.yml`/Docker image.
- Không trao quyền Crypto Officer/Administrator cho mọi application.
- Không dùng vault duy nhất cho mọi tenant/team nếu threat model yêu cầu cô lập.
- Chỉ bật public access/trusted-services exemption khi policy yêu cầu và được review.
- Không ghi key material/plaintext/token hoặc full unredacted request vào telemetry.
- Enforce vault URL/key allowlist từ cấu hình; chặn SSRF-style dynamic key identifiers.
- Dùng TLS và kiểm tra CA/hostname.
- Hạn chế network egress khi workload chỉ cần một số endpoints.

## 15. Audit, monitoring, quotas và chi phí

### 15.1. Điều gì cần được giám sát?

| Tín hiệu | Ý nghĩa |
| --- | --- |
| Số crypto calls encrypt/decrypt/wrap/unwrap/sign/verify | Workload usage, cost và bất thường |
| HTTP 401/403 | Credential, RBAC, firewall hoặc policy |
| HTTP 404 | Key/vault/version không tồn tại hoặc bị xóa |
| HTTP 429 | Throttling/quotas hoặc nhiều operations |
| HTTP 5xx/timeouts | Transient dependency, network hoặc service issues |
| Duration p50/p95/p99 cho `unwrapKey` | Latency ảnh hưởng download/giải mã |
| Key version/rotation events | Khả năng giải mã old data |
| Key disabled/deleted/purge attempts | Security incident hoặc change trái phép |
| Role assignment changes | Nới quyền crypto |
| Vault network/private endpoint changes | Outage hoặc mở access |
| Audit/diagnostic settings disabled | Mất khả năng giám sát |
| Cost per wrapped DEK / per workload | FinOps và hiệu quả caching/routing |

### 15.2. Azure Monitor và diagnostic settings

Dùng Azure Monitor/Log Analytics để thu Key Vault diagnostic logs theo chính sách. **Azure Activity Log** chủ yếu phản ánh các thay đổi control plane; **Key Vault audit logs** (category/resource-specific theo cấu hình) phản ánh các thao tác data plane được dịch vụ ghi nhận.

Lệnh CLI chỉ đọc:

~~~bash
VAULT_ID=$(az keyvault show \
  --resource-group "$RG" \
  --name "$VAULT" \
  --query id -o tsv)

az monitor diagnostic-settings list \
  --resource "$VAULT_ID" \
  --output json

az monitor metrics list-definitions \
  --resource "$VAULT_ID" \
  --output table
~~~

Không suy rằng đã tạo Key Vault thì mọi crypto operation tự xuất ở Log Analytics: phải **cấu hình diagnostic settings, destination, retention và IAM**. Một số metrics/log tables/fields thay đổi theo resource/schema.

### 15.3. KQL ví dụ phân tích Key Vault audit

Ví dụ này áp dụng **nếu** workspace dùng bảng `AzureDiagnostics` và category `AuditEvent`:

~~~kusto
AzureDiagnostics
| where TimeGenerated > ago(24h)
| where ResourceProvider == "MICROSOFT.KEYVAULT"
| where Category == "AuditEvent"
| summarize Calls = count() by OperationName, ResultType
| order by Calls desc
~~~

Trong cấu hình resource-specific tables, cần tra **bảng và column names thực** rồi chỉnh KQL tương ứng. Không xem kết quả 0 rows là chứng minh không có key operations nếu logging chưa bật, workspace sai hoặc sampling/retention không phù hợp.

### 15.4. Application-level telemetry không ghi plaintext

Một trace span hợp lệ có thể gồm:

~~~json
{
  "operation": "keyvault.unwrap_key",
  "environment": "prod",
  "keyAlias": "invoice-kek",
  "keyVersionAlias": "v2026-11",
  "durationMs": 37,
  "status": "success",
  "objectCategory": "invoice",
  "requestId": "opaque-correlation-id"
}
~~~

Đây là **schema ứng dụng minh họa**, không phải một JSON mặc định của Key Vault. Không đưa raw DEK, ciphertext, wrapped DEK, plaintext, request bearer token hoặc object nội dung nhạy cảm vào log. Key version alias có thể dùng để giảm lộ cấu trúc key URI khi cần.

### 15.5. Throttling và retry

Key Vault crypto operations bị giới hạn throughput/quotas theo SKU, loại operation và phạm vi dịch vụ. Khi bị `429`:

1. Kiểm tra retry-after/header hướng dẫn nếu có.
2. Dùng backoff có jitter và **giới hạn attempts/deadline**.
3. Không nhân retry nhiều tầng (API gateway × app × SDK).
4. Giảm số crypto calls không cần thiết.
5. Xem key/region distribution và capacity theo policy.
6. Không tự dùng plain AES key tĩnh trong config để “bỏ Key Vault cho nhanh”.

**Lỗi 401/403/404 do authorization/phiên bản khóa thường không phải transient**; đừng retry vô hạn. Khi một operation unwrap thất bại, không tiếp tục trả plaintext hoặc fallback sang key khác không được kiểm chứng.

### 15.6. Chi phí có những thành phần nào?

- Vault SKU, HSM-backed keys/Managed HSM billing nếu áp dụng.
- Số lượng cryptographic operations theo loại và bậc giá.
- Compute/app latency và concurrency khi gọi Key Vault thường xuyên.
- Private Endpoints/network, cross-region data transfer nếu có.
- Diagnostic logs, Log Analytics ingestion/retention và alerts.
- Storage ciphertext, wrapped DEKs và envelope metadata.
- Key rotation/rewrap jobs và backup/DR test.
- Đội ngũ audit/compliance nếu quy định yêu cầu.

Giá phụ thuộc SKU, region, operation và thời điểm; **không đưa số giá giả thành giá Azure thực tế**. Dùng Azure Pricing Calculator và Cost Management để xác minh.

### 15.7. Vì sao envelope thường tốt hơn gọi Key Vault cho mỗi chunk?

Giả sử một file 1 GiB được chia thành 64.000 chunks 16 KiB. Nếu gọi Key Vault cho từng chunk, ứng dụng tạo rất nhiều remote crypto operations, làm tăng latency, cost và rủi ro throttling.

Với envelope encryption, thường **một wrap/unwrap DEK cho một object/session** và bulk crypto chạy local bằng AES-GCM. Tuy nhiên việc chia file lớn thành chunks vẫn phải có **chunked AEAD protocol đúng**, không dùng cùng nonce với cùng DEK.

### 15.8. Caching và key usage

- Có thể cache **public key/metadata** khi phù hợp với rotation/version/authorization model.
- Không cache raw DEK vĩnh viễn trong Redis/shared cache để bỏ qua unwrap.
- Khi thật sự cần plaintext DEK cache ngắn hạn, phải có threat modeling, TTL, memory controls, tenant isolation và audit.
- Không cache key ID “latest” mãi mà không cập nhật rotation.
- Không chia sẻ plaintext DEK cho nhiều tenants/objects ngoài ý định chỉ vì giảm số call.


## 16. Kế hoạch dự phòng, restore và xử lý mất khóa

### 16.1. RPO/RTO của dữ liệu mã hóa có phụ thuộc khóa không?

Giả sử Blob Storage có ba bản sao dữ liệu ciphertext nhưng **KEK version dùng wrap DEK** đã bị purge không thể khôi phục. Bạn có thể còn đủ ciphertext nhưng **không giải mã được**.

Vì thế kế hoạch disaster recovery (DR) cho dữ liệu mã hóa phải xem đồng thời:

- **RPO dữ liệu:** có thể mất bao nhiêu dữ liệu/giao dịch.
- **RTO dịch vụ:** ứng dụng có thể phục vụ trở lại sau bao lâu.
- **Khả năng phục hồi khóa:** vault/key versions/backup và quyền truy cập còn dùng được không.
- **Khả năng phục hồi envelope:** wrapped DEKs/IV/AAD/format metadata có còn khớp ciphertext không.
- **Tính tương thích vùng:** key backup/restore, region, identity và network theo hạn chế của dịch vụ.
- **Nghĩa vụ retention/legal hold:** không vô tình purging key khi dữ liệu còn cần đọc.

**Backup ciphertext mà không backup/recover key và metadata phù hợp không đủ cho DR.**

### 16.2. Những đối tượng phải được bảo vệ đồng thời

| Thành phần | Rủi ro | Phương án |
| --- | --- | --- |
| Blob ciphertext | Xóa nhầm, overwrite, region outage | Versioning/soft delete/replication/backup theo policy |
| Wrapped DEK | Mất record hoặc sửa sai key ID | Transactional metadata store, backups, integrity |
| KEK key version | Disable/delete/expire/compromise | Rotation runbook, retention, soft delete, purge protection |
| Vault IAM/network | Role bị thu hồi, DNS lỗi | IaC, audited role backup và break-glass |
| AES IV/AAD schema | Thiếu nonce, đổi serialization | Versioned envelope schema, regression tests |
| Application decrypt code | Lỗi tương thích SDK/model | Versioned releases, recovery build, tests |
| Audit evidence | Incident không truy xuất được | Diagnostic settings, retention và delegated access |

### 16.3. Restore rehearsal

Một restore drill không chỉ kiểm tra “Key Vault đã tạo lại được” mà phải:

1. Chọn một **object mã hóa thử nghiệm** và bản envelope có key version cụ thể.
2. Xác định vault/key có sẵn hoặc phương án phục hồi/restore được phép.
3. Khôi phục data ciphertext và envelope vào môi trường lab cô lập.
4. Khôi phục/configure key access và identity/network phù hợp.
5. Chạy `unwrapKey` và AES-GCM decrypt, xác minh tag/AAD.
6. Đối chiếu checksum, business object ID và expected plaintext.
7. Đo RTO thực tế và ghi mọi dependency.
8. Chỉ kết luận PASS nếu **dữ liệu thực sự đọc được**, không chỉ khi file hiện trong Storage.

### 16.4. Sự cố purge/key compromise cần ưu tiên khác nhau

- **Key bị disable nhầm:** xin phê duyệt enable lại, kiểm tra version/path, audit và root cause.
- **Key bị soft-delete:** nếu còn recovery window và đúng quyền, xem quy trình recover, không tự tạo một key mới cùng tên rồi hy vọng decrypt được.
- **Key bị purge hoặc retention kết thúc:** recovery có thể không còn khả thi; đánh giá backup/restore hợp lệ và incident impact, không hứa chắc phục hồi.
- **Raw DEK bị lộ:** rotate KEK **không đủ**; cần re-encrypt affected ciphertext bằng DEK mới.
- **Principal unwrap bị lộ:** cô lập/revoke quyền, rà scope ciphertext/envelopes đã tiếp cận và làm incident response.
- **Private key signing bị lộ:** thay trust anchors và đánh giá chữ ký cũ, không chỉ rotate khóa đang dùng.

## 17. Runbook chẩn đoán lỗi Key Vault

### 17.1. Bảng lỗi và hành động đầu tiên

| Triệu chứng | Nguyên nhân có thể | Hành động đầu tiên |
| --- | --- | --- |
| `401 Unauthorized` | OAuth token sai/hết hạn, credential configuration | Kiểm tra token audience/identity và managed identity |
| `403 Forbidden` | Thiếu `unwrapKey`/RBAC, firewall hoặc policy | Kiểm tra principal, role, error details, network |
| `404 Not Found` | Key/version không tồn tại, bị delete, vault sai | Đối chiếu versioned key ID và vault |
| `400 Bad Request` | Algorithm/key type không hỗ trợ, plaintext quá dài | Xem RSA/EC, OAEP size, SDK options |
| `429 Too Many Requests` | Key Vault throttle/quota | Backoff có giới hạn, metrics, giảm calls |
| `5xx / timeout` | Service/network/transient failure | Retry có deadline, xem status/health |
| `UnknownHost / DNS failure` | Private DNS/forwarding/VNet link sai | Resolve vault FQDN từ đúng workload |
| TLS handshake error | Hostname/CA/network interception | Sửa DNS/trust; không tắt TLS |
| `Unwrap` fail sau rotation | Key version bị đổi/tắt/xóa hoặc wrong key ID | Đọc envelope `kekVersionId`, khôi phục đúng version |
| AES-GCM bad tag | Ciphertext/IV/AAD/DEK sai hoặc bị sửa | Chặn plaintext, điều tra integrity/metadata |
| Java SDK tạo client nhưng crypto fail | Sai role, network, algorithm, operation permissions | Trace request/status, không dùng admin key |
| Key được tạo nhưng không export được private material | Key Vault/HSM protection boundary | Dùng crypto API, không coi là lỗi |
| Logs trống nhưng app gọi vault | Diagnostic settings/workspace sai | Xác minh pipeline logs và tables |
| Chi phí và latency tăng | Thêm crypto calls mỗi chunk, retry storm | Quan sát calls/request, optimize envelope |
| Không thể purge ngay | Purge protection/retention policy | Không cố bypass, tuân thủ retention |

### 17.2. Bước 1 — Xác định request và phạm vi ảnh hưởng

Ghi:

~~~text
timestamp_utc
subscription_id / resource_group
vault_alias / key_alias / key_version
application_release / sdk_version
managed_identity_principal_id
operation = encrypt | decrypt | wrap | unwrap | sign | verify
http_status / service_error_code
request_correlation_id
tenant_scope / object_category (được khử nhạy cảm)
~~~

**Không ghi:** raw key, DEK, token, ciphertext cần bảo mật, plaintext, user secret, key backup bytes hoặc private data vào public incident ticket.

### 17.3. Bước 2 — Xác minh DNS và quyền

~~~bash
az account show \
  --query "{subscriptionId:id,tenantId:tenantId}" \
  --output json

az keyvault show \
  --name "$VAULT" \
  --output json

az keyvault key show \
  --vault-name "$VAULT" \
  --name "$KEY_NAME" \
  --output json
~~~

Nếu CLI desktop truy cập được mà AKS pod thất bại, **đừng suy rằng workload có cùng identity, network route hoặc DNS**. Kiểm tra managed identity object ID và token source của pod, rồi các role assignments.

### 17.4. Bước 3 — Phân loại authorization đúng lớp

- **401:** credential/token/audience không hợp lệ hoặc request không xác thực đúng.
- **403:** có thể là data-role permission, Key Vault firewall, network access, key attributes hoặc access policy model. Đọc service error details và audit.
- **404:** key/version/vault path không tồn tại, đã bị xóa/đổi; không tự thay bằng latest version.
- **400:** payload RSA quá dài, dùng algorithm không tương thích (ví dụ EC key với RSA OAEP), invalid key operations.

Một số security configurations cố tình che thông tin existence; đánh giá error codes cùng vault diagnostics, không chỉ dựa status.

### 17.5. Bước 4 — Kiểm tra key version dùng bởi envelope

Đọc **phiên bản được ghi trong ciphertext metadata**, không dùng một vòng `getKey(latest)` khi điều tra decrypt:

~~~text
Envelope:
  keyId: invoice-kek/version-V1
Vault:
  invoice-kek: V1, V2, V3
Application:
  latest key lookup returns V3

Correct: decrypt using V1; new encrypt may use V3.
Incorrect: attempt to unwrap old DEK with V3.
~~~

Nếu V1 disabled/expired, cần theo runbook/approval để phục hồi access cho old data hoặc đã rewrap trước đó; không tắt chính sách một cách tùy tiện trong production.

### 17.6. Bước 5 — Kiểm tra AES-GCM integrity

Nếu `Cipher.doFinal` ném lỗi xác thực tag:

1. **Không trả plaintext từng phần** cho user.
2. So sánh ciphertext hash/size và envelope schema version.
3. Kiểm tra IV dài đúng, tag format, AAD canonical encoding.
4. Xác minh tenant/object IDs khi decrypt giống encrypt.
5. Kiểm tra wrapped DEK và version ID hợp lệ.
6. Xác định có migration/serialization/record split làm sai dữ liệu không.
7. Nếu nghi ngờ tampering, coi đây là integrity/security incident và giữ bằng chứng.

Không “sửa” bằng cách bỏ `GCMParameterSpec`, dùng ECB, hard-code IV hoặc bỏ AAD.

### 17.7. Bước 6 — Đánh giá 429, timeouts và retry

Key Vault là dependency qua mạng; các thao tác HSM đặc biệt có thể chịu throughput/latency khác software keys. Xem:

- Crypto calls trên một user request.
- Số retries trong SDK và tầng ứng dụng.
- Deadline và backoff.
- Number of vaults/keys, regions và quotas thực.
- Key rotation đang diễn ra làm tăng operations?
- App có đang gọi unwrap cho mỗi chunk thay vì một lần mỗi object/session?
- CPU/heap và network TLS connection reuse.

Không tự chuyển sang một AES master key cố định trong config để bỏ qua Key Vault sau khi gặp 429.

### 17.8. Bước 7 — Hậu kiểm

- Key versions đúng và đáp ứng quyền least privilege.
- Old/new envelopes đều decrypt được hoặc có migration decision rõ.
- AES-GCM tag và business authorization PASS.
- 401/403/429/5xx về ngưỡng chấp nhận.
- Rotation/backup/soft delete/purge protection được giữ.
- Không có plaintext DEK hay token bị lộ trong logs.
- Audit và alert hoạt động, business owner xác nhận.
- Chi phí/throughput phù hợp ngân sách.

### 17.9. Phân quyền break-glass

Trong sự cố mất quyền truy cập khóa, không cấp vĩnh viễn `Key Vault Administrator` cho tất cả SRE. Sử dụng quy trình break-glass có:

- Identity độc lập, chỉ kích hoạt khi có sự cố và đa bước phê duyệt.
- Quyền `just-in-time` / PIM khi khả dụng.
- Phạm vi vault/key rõ ràng và thời hạn ngắn.
- Audit operations, review sau sự cố và revoke đúng hạn.
- Negative test đảm bảo app runtime không giữ quyền quản trị sau incident.


## 18. Bài lab: tạo KEK và mã hóa một hóa đơn minh họa

### 18.1. Mục tiêu và phạm vi

Bài lab chỉ sử dụng **dữ liệu giả**, không phải hồ sơ cá nhân hay đơn hàng thật:

~~~text
Subscription:     Azure lab được phê duyệt
Resource group:   rg-crypto-lab
Key Vault:        kv-crypto-lab-unique
Key name:         invoice-kek
Key type:         RSA 3072 (software key cho demo)
Identity:         local Azure CLI identity / managed identity lab
Crypto SDK:       azure-security-keyvault-keys
Java version:     17+
Payload:          "Hóa đơn demo, không có PII"
Expected result:  decrypt đúng và GCM rejects tampering
~~~

Nếu không có subscription/quyền, hãy làm bài thiết kế trên giấy theo các câu hỏi sau. **Không bắt buộc tạo tài nguyên có tính phí để học bài này.**

### 18.2. Các bước thực hành

| Bước | Hành động | Bằng chứng |
| --- | --- | --- |
| 1 | `az account show` xác định subscription/tenant | Context đúng, không dùng production |
| 2 | `az keyvault show` xác nhận RBAC model, region, recovery | Có vault lab, policy đúng |
| 3 | `az keyvault key list`/`show` | Key name/version đã tồn tại hay chưa |
| 4 | Operator tạo key nếu được phép | RSA key versioned ID hợp lệ |
| 5 | Security admin gán Crypto role tối thiểu | Principal thực được cấp quyền |
| 6 | Đặt `KEY_VERSIONED_ID` | Chứa đúng vault, key và version |
| 7 | Chạy Java encrypt/decrypt payload nhỏ | Round-trip bằng RSA-OAEP-256 PASS |
| 8 | Chạy Java wrap/unwrap AES key | DEK bytes giống nhau |
| 9 | Chạy EnvelopeCryptoDemo | Plaintext sau decrypt giống ban đầu |
| 10 | Thay 1 byte của ciphertext, giữ tag cũ | AES-GCM decrypt FAIL |
| 11 | Giữ ciphertext nhưng thay tenant/object AAD | AES-GCM decrypt FAIL |
| 12 | Tạo phiên bản KEK mới trong lab có approval | Có old/new key IDs |
| 13 | Thử decrypt envelope cũ bằng old version | PASS |
| 14 | Mô phỏng rewrap DEK sang new version | Old payload giữ nguyên, new wrapped DEK |
| 15 | Chạy lại decrypt với new key version | PASS |
| 16 | Đo latency/timeouts và audit logs | Có request IDs, không log plaintext |
| 17 | Test principal chỉ có Key Vault Reader | Không được unwrap/decrypt |
| 18 | Test Private Endpoint/firewall khi lab hỗ trợ | Network error được phân loại |
| 19 | Xem số crypto calls và cost estimate | Không gọi per chunk |
| 20 | Cleanup theo policy và inventory | Không purge key chứa dữ liệu cần đọc |

Không trực tiếp chạy disable/delete/purge để tạo test thất bại trên vault dùng chung.

### 18.3. Negative test với AES-GCM

Ví dụ logic test:

~~~java
EnvelopeCryptoDemo.Envelope original =
    EnvelopeCryptoDemo.encrypt(
        approvedVersionedKeyId, "tenant01", "order123",
        "Invoice demo".getBytes(java.nio.charset.StandardCharsets.UTF_8)
    );

// Tạo bản sao dữ liệu để thử integrity failure.
byte[] tampered = original.ciphertextAndTag().clone();
tampered[0] ^= 1;

EnvelopeCryptoDemo.Envelope damaged =
    new EnvelopeCryptoDemo.Envelope(
        original.keyVersionId(),
        original.iv().clone(),
        original.wrappedDek().clone(),
        tampered
    );

boolean rejected = false;
try {
    EnvelopeCryptoDemo.decrypt(damaged, "tenant01", "order123");
} catch (javax.crypto.AEADBadTagException expected) {
    rejected = true;
}
if (!rejected) {
    throw new IllegalStateException("Tampered ciphertext accepted!");
}
~~~

Đây là **đoạn test bên trong class/method đã có các biến và quyền**; không phải chương trình độc lập. Một số JCE providers có thể báo lỗi xác thực tag bằng kiểu exception khác theo implementation; khi viết test portable, cần xem API/provider và không bắt tất cả lỗi rồi tuyên bố “tamper detected” nếu chúng đến từ network/configuration.

### 18.4. Positive và negative cases về quyền

| Principal | Quyền dự kiến | Kiểm thử |
| --- | --- | --- |
| Provisioner | Tạo/rotate key theo scope | Tạo key trên lab, không dùng runtime |
| Encrypt-only workload | Encrypt/wrap theo policy | Wrap được, unwrap **bị từ chối** nếu custom role hỗ trợ |
| Decrypt workload | Unwrap/decrypt theo policy | Giải mã object đã ủy quyền |
| Metadata reader | Chỉ đọc key metadata | `getKey` có thể PASS, `unwrapKey` DENIED |
| Operator incident | Quyền tạm theo approval | Restore/rotation với audit |
| User cuối | Không truy cập Key Vault trực tiếp | Chỉ gọi API đã business-authorize |
| Attacker từ mạng ngoài | Không có private route/credential | Không kết nối hoặc bị chặn |
| Key disabled/deleted | Không được dùng cryptography | Lỗi theo trạng thái key, dữ liệu không giải mã |

**Phải test bằng đúng identity/credential**. Nếu mọi test dùng tài khoản `Key Vault Administrator`, việc unwrap thành công không chứng minh least privilege.

### 18.5. Bài tính chi phí/latency

Giả sử có 50.000 file uploads/ngày. Nếu thiết kế gọi Key Vault **1 lần wrap mỗi file**, số wrap operations lý thuyết:

\[
50{,}000\ \text{wrap calls/ngày}.
\]

Nếu download cũng trung bình 20.000 lượt/ngày và mỗi download unwrap 1 lần:

\[
50{,}000 + 20{,}000 = 70{,}000\ \text{crypto operations/ngày}.
\]

Đây là **số lượng operations giả định**, không phải hóa đơn. Nếu có retries, rewrap jobs, signature verifications hoặc key metadata GET, số operations thực sẽ khác. Dùng Azure Pricing Calculator theo SKU/region/operation để ước tính, không tự gán giá USD cố định.

### 18.6. Bài lựa chọn kiến trúc

**Yêu cầu A:** PDF chỉ cần encryption at rest trong Storage, không có yêu cầu application-layer ciphertext.

**Lựa chọn:** đánh giá Storage encryption và CMK Key Vault integration nếu phù hợp thay vì tự xây AES-GCM envelope serialization.

**Yêu cầu B:** hồ sơ nhạy cảm phải được mã hóa trước khi lưu, DEK per object và key/tenant separation.

**Lựa chọn:** app-level envelope encryption, AES-GCM authenticated, Key Vault KEK wrap, versioned key IDs và strict authorization, kèm đánh giá thư viện/protocol cho streaming.

**Yêu cầu C:** cần xác minh file phát hành bởi một hệ thống nội bộ, không cần che nội dung.

**Lựa chọn:** digital signature/verify với signing key và signed manifest, không dùng encrypt để thay signature.

## 19. Tình huống thực tế và bài tập tư duy

### 19.1. Tình huống A — Rotation làm 10% dữ liệu cũ không đọc được

Ứng dụng mới chỉ gọi `getKey("invoice-kek")` để lấy version mới nhất rồi unwrap tất cả documents.

**Phân tích:** records cũ có wrapped DEK từ version trước. **Sửa:** lưu và đọc `kekVersionId` của từng envelope, giữ old versions hợp lệ hoặc triển khai rewrap có kiểm soát; không tạo mới KEK để thử giải mã.

### 19.2. Tình huống B — Một developer có Reader trên vault nhưng không xem được plaintext secret

**Phân tích:** Key Vault Reader chủ yếu xem metadata theo role, không nhất thiết đọc value secret/unwrap key. Azure management Reader cũng không là Key Vault data-plane Reader. Xác minh đúng role, authorization model, scope và network, không cấp Administrator chỉ để test.

### 19.3. Tình huống C — Kho Blob có mã hóa AES-GCM nhưng vẫn rò rỉ dữ liệu

API không kiểm tra owner và dùng managed identity có `unwrapKey` với mọi KEK. Người dùng A đoán object ID của B, API trả plaintext.

**Phân tích:** mã hóa **không thay business authorization**. Cần kiểm tra tenant/object ownership trước khi tải/unwrap, giảm scope key access và audit. Nếu có rò rỉ thật, xử lý như security incident.

### 19.4. Tình huống D — Rewrap sau khi raw DEK đã lộ

Đội vận hành nghĩ chỉ wrap lại DEK cũ bằng key mới đã xử lý compromise.

**Phân tích:** không đúng; attacker vẫn biết DEK. **Sửa:** re-encrypt affected payload với DEK/IV mới, wrap bằng KEK hợp lệ và xử lý old copies/retention theo incident runbook.

### 19.5. Tình huống E — Dùng cùng IV 12 bytes cho mọi phần của file

Ứng dụng tự chia file thành chunks, mỗi chunk dùng một DEK cố định và IV giống nhau.

**Phân tích:** **nguy cơ nghiêm trọng trong AES-GCM**. Không dùng; thiết kế streaming AEAD chuẩn hóa với unique nonce per key/chunk và manifest authentication hoặc thư viện đã được kiểm duyệt.

### 19.6. Tình huống F — Key Vault có private endpoint nhưng Java vẫn timeout

**Phân tích:** DNS/route/Private DNS Zone, network policy hoặc TLS hostname có thể sai. Kiểm tra `privatelink.vaultcore.azure.net`, VNet link và connectivity từ đúng workload; không dùng IP thô trong vault URL.

### 19.7. Tình huống G — Giá Key Vault tăng sau refactor upload

Pipeline cũ wrap 1 DEK/file, bản mới gọi remote RSA encrypt cho từng 4 KiB chunk.

**Phân tích:** remote crypto operations tăng mạnh, có thể gây quota/latency/cost issues. **Sửa:** quay về envelope model với AES-GCM local; vẫn phải thiết kế chunk encryption an toàn khi stream.

### 19.8. Tình huống H — Không thể xóa vĩnh viễn key ngay lập tức

Vault bật purge protection, operator muốn purge key để dọn môi trường.

**Phân tích:** purge protection là cơ chế bảo vệ retention, không phải lỗi cần bypass. Theo chính sách tài nguyên/lab và chờ retention; không ép hủy nếu ciphertext còn phụ thuộc.

### 19.9. Tình huống I — Một chữ ký số hợp lệ nhưng dữ liệu vẫn sai

Bản manifest được ký bởi app được ủy quyền, nhưng số tiền được tính sai do bug.

**Phân tích:** signature chứng minh nguồn ký và integrity theo trust model, **không bảo đảm tính đúng đắn của nghiệp vụ**. Cần validation và quy trình sửa dữ liệu riêng.

### 19.10. Tình huống J — Key Vault backup phục hồi nhưng file vẫn không đọc được

**Phân tích:** kiểm tra wrapped DEK, đúng versioned key ID, IV, AAD schema, ciphertext tag, encryption algorithm, IAM/network và bản app compatibility. Không coi backup key thành công là DR hoàn tất.

### 19.11. Tình huống K — HSM-backed key không thể export PEM private key

**Phân tích:** đây là mục tiêu của HSM protection boundary, không phải bug. Dùng crypto operation/managed lifecycle; nếu có requirement migration, xem backup/restore/service-specific model và restrictions được hỗ trợ.

### 19.12. Tình huống L — Entra identity được gán Crypto User nhưng vẫn 403

**Phân tích:** có thể dùng sai principal object ID, role chưa propagate, vault đang ở access-policy model, key op bị hạn chế, Private Endpoint/firewall từ chối hoặc app đang dùng identity khác. Thu error code/requests và xét từng lớp trước khi cấp thêm quyền.

## 20. Checklist thiết kế production

### 20.1. IAM và dữ liệu

- [ ] Có business data classification và quyết định rõ CMK hay app-level encryption.
- [ ] KEK/DEK hierarchy được ghi trong kiến trúc; không nhầm key với secret.
- [ ] Key operations được phép theo đúng RSA/EC/key type và chính sách.
- [ ] Managed identity/workload identity được cấu hình, không hard-code client secret.
- [ ] Azure RBAC data roles có phạm vi tối thiểu; runtime không được rotate/purge.
- [ ] Business authorization bảo vệ tenant/object trước khi unwrap.
- [ ] Không đưa raw DEK, plaintext, token hoặc signed URL nhạy cảm vào logs.
- [ ] Mọi ciphertext/envelope lưu versioned KEK ID, algorithm và AAD schema.
- [ ] Có negative tests để ngăn unauthorized unwrap/decrypt.
- [ ] AES-GCM dùng fresh DEK/unique IV và xác thực tag.
- [ ] Không dùng AES-ECB hoặc nonce reuse; không mã hóa file lớn bằng RSA trực tiếp.

### 20.2. Key lifecycle và khả năng phục hồi

- [ ] Có owner, purpose, crypto policy và rotation schedule cho mỗi key.
- [ ] Có phân biệt active version cho new writes và old versions cho reads.
- [ ] Rotation/rewrap quy trình kiểm thử, retry, reconciliation và rollback.
- [ ] Soft delete/purge protection/retention đúng yêu cầu compliance.
- [ ] Key backups/DR được kiểm thử theo SKU, region và restrictions.
- [ ] Restore drill thực sự decrypt được một object thử nghiệm.
- [ ] Có phương án re-encrypt khi raw DEK/KEK bị compromise.
- [ ] Không disable/purge old versions trước khi xong migration/sign-off.
- [ ] Có break-glass procedure và audit quyền đặc biệt.

### 20.3. Networking, monitoring và FinOps

- [ ] Vault FQDN/TLS và Private Endpoint/Private DNS hoạt động.
- [ ] Public access/trusted services exceptions chỉ có khi được phê duyệt.
- [ ] Diagnostics/Log Analytics/Azure Monitor bật đúng category/destination.
- [ ] 401/403/404/429/5xx và key-state changes có alerts/runbooks.
- [ ] Application có trace correlation, không log sensitive payload.
- [ ] Retry/backoff/deadline/circuit breaker có giới hạn rõ ràng.
- [ ] Không gọi Key Vault cho mỗi data chunk ngoài ý định.
- [ ] Crypto operations latency p95/p99 và cost được giám sát.
- [ ] IAM/network/key changes được review và có owner.
- [ ] Có sandbox/lab riêng, không chạy destructive tests trên production.


## 21. Câu hỏi tự kiểm tra

**Câu 1.** Azure Key Vault Key và Secret khác nhau cốt lõi ở đâu?

**Trả lời:** Key hỗ trợ quản lý key material và cryptographic operations theo service/key type; Secret lưu giá trị bí mật mà principal có quyền đọc có thể nhận plaintext. Dùng Keys để giữ KEK trong boundary của Key Vault thay vì lưu một master key trong Secret rồi phân phát cho ứng dụng.

**Câu 2.** Key Vault Standard, Premium và Managed HSM có giống nhau không?

**Trả lời:** Không. Standard có software-protected keys, Premium hỗ trợ lựa chọn HSM-backed keys theo tính năng, còn Managed HSM là dịch vụ HSM chuyên biệt với quản trị/backup/billing khác. Cần kiểm tra SKU và key type thực.

**Câu 3.** Vì sao RSA-OAEP-256 không phù hợp để mã hóa file 100 MiB?

**Trả lời:** RSA OAEP có giới hạn plaintext nhỏ theo modulus/padding và remote operations tốn chi phí/độ trễ. Dùng AES-GCM bulk encryption và Key Vault để wrap DEK.

**Câu 4.** RSA-2048 + OAEP-SHA256 có thể mã hóa tối đa bao nhiêu plaintext bytes?

**Trả lời:** 256 - 2×32 - 2 = **190 bytes** theo giới hạn RSA-OAEP, với key/algorithm đúng.

**Câu 5.** DEK là gì và khác KEK thế nào?

**Trả lời:** DEK là khóa đối xứng mã hóa dữ liệu; KEK bảo vệ DEK. Trong bài, DEK là AES-256 per object, KEK là RSA key version được giữ trong Key Vault.

**Câu 6.** Wrapped DEK có phải dữ liệu ciphertext của file không?

**Trả lời:** Không. Wrapped DEK là khóa dữ liệu đã được bọc bằng KEK; ciphertext của file là kết quả AES-GCM trên plaintext.

**Câu 7.** Vì sao cần IV/nonce riêng cho mỗi lần AES-GCM mã hóa với cùng DEK?

**Trả lời:** GCM nonce reuse với cùng key có thể phá confidentiality/integrity rất nghiêm trọng. Trong ví dụ mỗi object tạo DEK mới và IV ngẫu nhiên 12 bytes.

**Câu 8.** AAD dùng để làm gì?

**Trả lời:** Additional Authenticated Data không được mã hóa nhưng được xác thực, giúp ràng buộc ciphertext với tenant/object ID/schema version. Bản giải mã phải tái tạo AAD chính xác.

**Câu 9.** Lỗi tag AES-GCM có nên được bỏ qua để lấy plaintext?

**Trả lời:** Không. Đó là tín hiệu dữ liệu hoặc key/IV/AAD không khớp, có thể bị sửa; phải fail closed và điều tra.

**Câu 10.** ETag/version của Blob có thay thế versioned key ID không?

**Trả lời:** Không. Blob ETag/version quản lý phiên bản data object; key version ID xác định KEK thực dùng để wrap DEK. Hai metadata cần được quản lý độc lập.

**Câu 11.** Khi Key Vault key rotate từ V1 lên V2, old ciphertext có tự dùng V2 được không?

**Trả lời:** Không. Old DEKs được bọc bằng V1 cần được unwrap bằng V1, hoặc rewrap theo quy trình sang V2.

**Câu 12.** Rewrap có phải mã hóa lại toàn bộ file không?

**Trả lời:** Không nhất thiết. Rewrap đổi lớp bảo vệ DEK bằng KEK mới trong khi dữ liệu AES-GCM ciphertext vẫn giữ nguyên.

**Câu 13.** Khi raw DEK đã bị lộ, rewrap bằng KEK mới có đủ an toàn không?

**Trả lời:** Không. Kẻ tấn công vẫn giữ DEK đã lộ; cần re-encrypt payload bằng DEK mới và xử lý incident.

**Câu 14.** Tại sao phải giữ old key versions trong retention period?

**Trả lời:** Để decrypt/unwrap dữ liệu cũ và backup/historical objects còn tham chiếu version đó cho tới khi rewrap/re-encrypt hoặc hết retention hợp lệ.

**Câu 15.** Một key HSM-backed có thể xuất plaintext private key bằng `getKey` không?

**Trả lời:** Không như đọc secret plaintext. Key Vault/HSM bảo vệ private key theo boundary, cho crypto operations được phép thay vì cung cấp private key để dùng tự do.

**Câu 16.** `Key Vault Reader` có cho phép unwrap DEK không?

**Trả lời:** Không. Reader chủ yếu đọc metadata; crypto operations yêu cầu data-plane permissions/role phù hợp.

**Câu 17.** Azure resource group Contributor có tự là Key Vault Crypto User không?

**Trả lời:** Không trực tiếp. Tuy nhiên quyền control plane/IAM/access policy management có thể tạo đường nâng quyền gián tiếp tùy cấu hình, nên phải review effective privileges.

**Câu 18.** Nếu vault dùng access policies cũ, Azure RBAC role assignment có tự cho phép unwrap không?

**Trả lời:** Không được giả định. Authorization model nào đang bật quyết định cách data-plane permissions được áp dụng; cần kiểm tra và thiết kế migration.

**Câu 19.** Vì sao managed identity tốt hơn hard-coded client secret?

**Trả lời:** Giảm lưu/truyền static secrets trong code và cho phép quản trị quyền qua Entra ID/RBAC; vẫn phải bảo vệ identity, scope và network.

**Câu 20.** Một managed identity có Crypto User nhưng Key Vault private DNS sai, crypto call thành công không?

**Trả lời:** Có thể không. RBAC và network/TLS là các lớp độc lập; cần xác minh Private Endpoint/DNS/route từ workload.

**Câu 21.** Private Endpoint có thay thế authorization của user cuối không?

**Trả lời:** Không. Nó chỉ kiểm soát đường kết nối; Java API phải xác thực tenant/object owner trước khi decrypt.

**Câu 22.** `Sign` và `Encrypt` khác nhau ra sao?

**Trả lời:** Sign tạo chữ ký số dùng xác minh tính toàn vẹn/nguồn ký theo trust model; Encrypt giữ bí mật nội dung. Chữ ký không mã hóa plaintext.

**Câu 23.** Tại sao nên ký digest của file lớn thay vì đưa cả file qua Key Vault sign?

**Trả lời:** Sign API sử dụng digest theo thuật toán; ứng dụng có thể hash streaming local để giảm dữ liệu gửi qua mạng, với canonical signing protocol.

**Câu 24.** Nếu xóa KEK rồi tạo key cùng name, dữ liệu cũ có tự decrypt được không?

**Trả lời:** Không. Key name giống không có nghĩa private key material/version giống; cần recover/restore đúng key cũ theo khả năng dịch vụ.

**Câu 25.** Soft delete và purge protection có bảo đảm khôi phục được ciphertext không?

**Trả lời:** Chúng bảo vệ/key recovery trong điều kiện và retention nhất định, nhưng cần cả data/envelope/IV/AAD/versions, app compatibility và IAM/network mới decrypt được.

**Câu 26.** CMK tích hợp Azure Blob Storage có giống ứng dụng tự AES-GCM encrypt file không?

**Trả lời:** Không. Với CMK, Azure service thực hiện encryption at rest theo integration; app-level envelope mã hóa trước khi dữ liệu đến storage, có trách nhiệm vận hành riêng.

**Câu 27.** Có nên cấp Key Vault Administrator cho app chỉ cần wrap DEK không?

**Trả lời:** Không. Sử dụng least privilege, xem Key Vault Crypto User hoặc custom permissions/identity separation theo chính sách.

**Câu 28.** Vì sao không gọi Key Vault encrypt cho từng 4 KiB chunk?

**Trả lời:** Tăng remote operations, latency, cost/throttling và dễ thiết kế crypto format sai. Dùng AES-GCM local với quy trình chunked AEAD đã được kiểm chứng khi cần streaming.

**Câu 29.** Thấy HTTP 403 khi gọi Key Vault thì phải kiểm tra gì?

**Trả lời:** Principal thực, role/scope, authorization model, key operations/attributes, firewall/private endpoint/DNS và service error details, không tự cấp Administrator.

**Câu 30.** Vì sao cần test restore bằng một lần giải mã thật?

**Trả lời:** Restore key object hoặc ciphertext riêng lẻ không đủ; phải chứng minh app có thể unwrap DEK đúng version và xác minh AES-GCM tag/AAD trên dữ liệu cần phục hồi.

## 22. Thuật ngữ thường gặp

| Thuật ngữ | Ý nghĩa |
| --- | --- |
| **Key Vault** | Dịch vụ quản lý keys, secrets, certificates có identity/network controls |
| **KEK** | Key Encryption Key — khóa dùng bảo vệ DEK |
| **DEK** | Data Encryption Key — khóa mã hóa payload |
| **Key version** | Phiên bản key material và attributes được quản lý bởi vault |
| **Wrap/unwrap** | Mã hóa/giải mã khóa đối xứng bằng key wrapping algorithm |
| **RSA-OAEP-256** | RSA encryption/wrapping với OAEP-SHA256 |
| **AES-256-GCM** | Symmetric authenticated encryption, dùng DEK 256 bits |
| **IV/nonce** | Giá trị duy nhất theo key/operation; GCM không được tái sử dụng cùng DEK |
| **AAD** | Additional Authenticated Data; kiểm tra integrity của metadata liên quan |
| **Authentication tag** | Giá trị xác thực kết quả AEAD; mismatch phải fail |
| **HSM** | Hardware Security Module, boundary bảo vệ key theo cấu hình |
| **Entra ID** | Dịch vụ định danh xác thực người dùng/workload |
| **Key Vault RBAC** | Azure data-plane permissions được gán theo role/scope |
| **Access policy** | Mô hình ủy quyền Key Vault legacy theo permission entries |
| **Managed identity** | Identity của Azure resource/workload dùng token thay static secret |
| **CMK** | Customer-Managed Key tích hợp service encryption hoặc bài toán riêng |
| **Soft delete** | Giữ đối tượng đã xóa trong thời hạn recovery |
| **Purge protection** | Hạn chế xóa vĩnh viễn trước retention theo policy |
| **Rewrap** | Đổi KEK bảo vệ DEK, giữ nguyên payload ciphertext nếu DEK không đổi |
| **Re-encrypt** | Mã hóa lại dữ liệu bằng DEK/IV hoặc algorithm theo migration |
| **RPO/RTO** | Mức mất dữ liệu cho phép / thời gian khôi phục mục tiêu |
| **Zeroization** | Nỗ lực xóa key material khỏi memory; JVM không luôn bảo đảm xóa mọi bản sao |

## Ghi nhớ

- **Key Vault Keys, Secrets và Certificates khác nhau**; nếu cần giữ private KEK trong boundary dịch vụ và gọi crypto operations, dùng Key Vault Keys thay vì phát master secret plaintext.
- **RSA-OAEP-256 chỉ mã hóa payload nhỏ**; file lớn nên mã hóa bằng AES-GCM và Key Vault dùng để **wrap/unwrap DEK**.
- **AES-GCM yêu cầu IV/nonce không tái sử dụng với cùng DEK**, kiểm tra tag và AAD đúng; không tự viết chunk protocol thiếu integrity.
- **Lưu versioned key ID trong envelope**. Rotation sang new version không tự biến old wrapped DEKs thành wrapped DEKs mới.
- **Rewrap DEK khác re-encrypt payload**; khi raw DEK bị lộ, rewrap đơn thuần không xử lý compromise.
- **Key Vault RBAC, managed identity, Private Endpoint, TLS và business authorization** giải quyết những lớp bảo vệ khác nhau; không cấp quyền crypto admin cho runtime.
- **Soft delete, purge protection và restore drills** phải đảm bảo key version vẫn phục vụ được dữ liệu còn trong retention.
- **CMK service-side khác app-level envelope encryption**. Chọn thiết kế theo threat model và khả năng vận hành, tránh xây crypto không cần thiết.
- **Audit, metrics, retries có giới hạn, chi phí crypto calls, rotation runbooks và rollback** là những phần bắt buộc của vận hành Key Vault production.
