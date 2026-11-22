# Phân quyền Key Vault bằng Azure RBAC

Một ứng dụng Spring Boot chạy trên **Azure Container Apps** cần đọc mật khẩu truy cập database từ **Azure Key Vault**. Một worker khác cần ký dữ liệu bằng khóa bất đối xứng mà không lấy private key ra khỏi vault. Nhóm bảo mật thì phải luân chuyển chứng chỉ và giám sát truy cập. Nếu gán **Key Vault Administrator** cho mọi ứng dụng để tránh lỗi 403, mỗi workload bị tấn công có thể truy cập nhiều bí mật không liên quan. Ngược lại, nếu chỉ gán **Contributor** trên resource group, ứng dụng có thể **vẫn không đọc được secret** vì quyền quản lý resource khác quyền truy cập nội dung.

**Phân quyền Key Vault bằng Azure RBAC** là gán đúng **principal**, **role**, **scope** và kiểm soát **permission model**, để một danh tính Microsoft Entra ID chỉ thực hiện các thao tác cần thiết trên secrets, keys và certificates. Kiểm soát quyền phải đi cùng network security, quản trị access, giám sát, rotation và xác minh hoạt động thực tế từ đúng identity của workload.

Bài học thuộc chương **Secret, khóa và chứng chỉ** của module **CLOUD_PROVIDERS_AZURE**, trong hành trình học Microsoft Azure từ subscription, resource group, Microsoft Entra ID, mạng ảo đến compute, storage, dữ liệu, bảo mật, giám sát và kiểm soát chi phí.

> **Phạm vi:** tập trung vào **Azure Key Vault** dùng permission model **Azure role-based access control (Azure RBAC)**, không nhầm với Azure Managed HSM. Built-in roles, data actions, API/schema, network behavior, SKU, limits và giá có thể thay đổi; hãy xác minh role definitions và tài liệu Microsoft hiện hành trước khi áp dụng production. Ví dụ có placeholder, không dùng giá trị secret thật.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **management plane** và **data plane** của Azure Key Vault.
2. So sánh **vault access policies** và **Azure RBAC permission model**.
3. Giải thích principal, role definition, role assignment, scope, inheritance, deny assignment và PIM.
4. Chọn các built-in Key Vault roles phù hợp cho read secret, quản lý secret, crypto operations và certificates.
5. Gán quyền tối thiểu cho system-assigned/user-assigned managed identity hoặc service principal.
6. Kiểm tra role assignment bằng Portal, Azure CLI và ví dụ IaC.
7. Đọc secret bằng **Azure SDK for Java** nhưng không ghi lộ giá trị.
8. Hiểu tại sao có role đúng vẫn có thể gặp 403 do firewall/Private Endpoint/DNS.
9. Lên kế hoạch migration từ access policy sang RBAC mà không gây mất quyền.
10. Áp dụng logging, Azure Monitor, Azure Policy, PIM, rotation, soft delete và security review.
11. Viết runbook điều tra 401/403/404, propagation, secret state và lỗi network.
12. Thiết kế kiến trúc tách vaults/identities theo dev, staging, prod và business risk.

## 2. Tình huống: Contributor nhưng vẫn bị 403

~~~text
Subscription: sub-commerce-prod
Resource group: rg-commerce-prod
Key Vault: kv-commerce-prod
Secret: db-password
App: Spring Boot trên Azure Container Apps
Managed identity: mi-commerce-api-prod
~~~

Người vận hành gán **Contributor** tại `rg-commerce-prod` rồi ứng dụng gọi:

~~~java
KeyVaultSecret secret = secretClient.getSecret("db-password");
~~~

Lời gọi có thể thất bại với **403 Forbidden** nếu vault dùng RBAC permission model. Những câu hỏi cần trả lời:

- Principal trong access token có đúng **object/principal ID** của ứng dụng đang chạy không?
- Vault dùng **Azure RBAC** hay **Vault access policy**?
- Principal có **Key Vault Secrets User**, hoặc role có data action đọc secret value, ở scope hợp lệ không?
- Assignment từ parent scope hoặc group/PIM có tác động không?
- Vault firewall hoặc private networking đang chặn đường đi không?
- Secret có tồn tại, enabled, version hợp lệ và application đang dùng đúng URI không?
- Quyền mới cấp đã propagation đến data plane chưa?

**Không chữa lỗi bằng Owner/Administrator toàn subscription.** Trước hết xác định đúng chặng lỗi, rồi cấp tối thiểu quyền cần thiết.

## 3. Secrets, keys và certificates khác nhau

| Đối tượng | Bản chất | Ví dụ thao tác |
|---|---|---|
| **Secret** | Giá trị bí mật được lưu và trả về khi principal được phép | Get, set, list metadata, delete, recover |
| **Key** | Vật liệu và chính sách khóa mật mã, có thể không cho phép export private key | Sign, verify, wrap/unwrap, encrypt/decrypt, rotate |
| **Certificate** | Certificate và vòng đời phát hành/renew; có thể có backing key/secret | Create/import, get, list, renew, retrieve content |
| **Vault** | Boundary resource chứa objects, networking, IAM, diagnostics | Configure settings, permission model, policies |

### Secret

Một secret như `db-password` có thể có **nhiều versions**. App đọc latest hoặc version cụ thể tùy SDK/API. RBAC quyết định identity có quyền đọc object; nó **không tự xoay mật khẩu database** khi secret đổi.

### Key

Với Key Vault crypto key, app thường gọi cryptographic operation từ Key Vault, **không cần nhận private key material**. Quyền **Key Vault Crypto User** khác quyền quản trị keys của **Crypto Officer**.

### Certificate

Một Key Vault certificate có thể gắn với **backing secret** và key. Đọc metadata/public certificate, sử dụng private key hoặc export nội dung chứng chỉ có các permission requirements riêng. Không suy rằng quyền đọc metadata certificate tự cho phép lấy private key, và cũng không cấp toàn quyền secret chỉ vì consumer cần public certificate.

## 4. Hai permission models của Key Vault

Một Key Vault có thể được cấu hình **Vault access policy** hoặc **Azure role-based access control** để kiểm soát **data-plane**.

| Khía cạnh | Access policy mode | Azure RBAC mode |
|---|---|---|
| Nguồn quyền data-plane | Access policies trên vault | Role assignments có data actions |
| Cấp quyền | Các permissions secret/key/cert theo access policy | Built-in/custom roles và scope |
| Thừa kế từ subscription/RG | Không theo hierarchy Azure RBAC role assignment | Có thể kế thừa từ parent scopes |
| Quản trị quyền | Sửa access policies tại vault | Azure authorization role assignment management |
| Giám sát | Vault configuration và audit | ARM Activity Log, IAM/PIM và data-plane audit |
| Governance | Cần hạn chế người có quyền chỉnh access policies | Hỗ trợ role scope, PIM, policy và assignment conditions |

**Quy tắc bắt buộc:** khi vault bật **Azure RBAC authorization**, **access policies cũ không còn dùng cấp data-plane access**. Không có chuyện “quyền từ access policy cộng thêm RBAC”. Ngược lại, trong access policy mode, gán Key Vault Secrets User bằng RBAC **không đủ** thay access policy data-plane hiện tại.

Thay permission model trên vault đang vận hành có thể khiến ứng dụng, cert automation, backup/restore hoặc rotation mất quyền. Luôn lập inventory, map roles và chuẩn bị kiểm thử trước cutover.

## 5. Management plane và data plane

~~~mermaid
flowchart LR
  ADMIN["Infra admin / Azure CLI"] --> ARM["Azure Resource Manager"]
  ARM -->|"Management RBAC actions"| CONFIG["Vault configuration, role assignments"]
  APP["App managed identity"] -->|"Entra access token"| ENDPOINT["Key Vault data endpoint"]
  ENDPOINT -->|"Data-plane RBAC dataActions"| OBJECTS["Secrets / Keys / Certificates"]
  CONFIG -.->|"Không mặc nhiên đọc values"| OBJECTS
~~~

### Management plane

Các thao tác qua ARM:

- Tạo, xem, cập nhật hoặc xóa resource Key Vault.
- Cấu hình network/firewall, tags, permission model, diagnostics.
- Quản trị role assignments khi principal có quyền `Microsoft.Authorization/roleAssignments/write` và đáp ứng policy/condition.

Roles như **Contributor**, **Owner**, **User Access Administrator** hoặc **Role Based Access Control Administrator** chủ yếu liên quan management plane và kiểm soát IAM. **Key Vault Contributor** quản lý resource Key Vault nhưng **không tự có quyền đọc secret value trong RBAC mode**.

### Data plane

Các yêu cầu tới endpoint:

~~~text
https://<VAULT>.vault.azure.net/secrets/...
https://<VAULT>.vault.azure.net/keys/...
https://<VAULT>.vault.azure.net/certificates/...
~~~

Ví dụ: `get secret value`, `set secret`, `sign`, `decrypt`, `get certificate`. Đây là quyền từ role **dataActions** khi vault dùng RBAC.

### Một người có thể có hai loại quyền

Có thể có một platform engineer vừa quản lý cấu hình vault vừa được phép xem secrets theo quy trình, nhưng đó nên là **hai quyết định cấp quyền có căn cứ**, không phải một quyền mở rộng vô điều kiện.

## 6. Các thành phần Azure RBAC

| Thành phần | Nghĩa |
|---|---|
| **Principal** | User, group, service principal, managed identity được Entra nhận diện |
| **Role definition** | Tập `actions`/`notActions`, `dataActions`/`notDataActions` |
| **Role assignment** | Gắn principal và role tại một scope |
| **Scope** | Subscription, resource group, vault hoặc child object được hỗ trợ |
| **Inheritance** | Quyền assignment ở scope cha có thể áp dụng scope con |
| **Deny assignment** | Cơ chế từ chối có thể tác động effective access |
| **Role assignment condition** | Giới hạn khả năng gán/thu hồi một số roles trong những trường hợp hỗ trợ |
| **PIM** | Quản lý quyền đủ điều kiện/kích hoạt theo thời hạn và phê duyệt khi hỗ trợ |

Vai trò được **gán theo principal ID**, không phải “ứng dụng có tên giống vậy”. Một assignment chuẩn gồm:

~~~text
Principal: mi-commerce-api-prod (principal object ID)
Role: Key Vault Secrets User
Scope:
  /subscriptions/<SUB_ID>/resourceGroups/rg-commerce-prod/
  providers/Microsoft.KeyVault/vaults/kv-commerce-prod
~~~

## 7. Scope và inheritance: quyền có thể rộng hơn bạn nghĩ

~~~mermaid
flowchart TD
  SUB["Subscription"] --> RG["Resource group"]
  RG --> KV1["kv-commerce-prod"]
  RG --> KV2["kv-reports-prod"]
  KV1 --> SEC1["db-password"]
  KV1 --> SEC2["payment-provider-token"]
  SUB -.->|"Role assignments inherited"| KV1
  RG -.->|"Role assignments inherited"| KV2
~~~

Nếu người vận hành được cấp role Key Vault Administrator ở **subscription**, họ có thể có data-plane privileges trên nhiều vaults trong subscription khi các vault dùng RBAC. Tương tự, assignment trên **resource group** có thể ảnh hưởng mọi vaults con.

### Hướng chọn scope

- **Vault scope** là điểm bắt đầu tốt cho một ứng dụng có quyền trên các secrets cùng vault.
- **Subscription/RG scope** chỉ khi có nhu cầu rõ và policy phê duyệt; phải tính cả vaults hiện có/tương lai.
- **Object-level scope** với secret/key/certificate có thể được hỗ trợ, nhưng tăng overhead quản trị; nên cân nhắc vault riêng khi ứng dụng/tenant cần isolation rõ.
- Kiểm tra assignments thừa kế, group membership, PIM activations và role definition.
- Với multi-tenant business data, **Key Vault vault boundary không thay logic tenant ownership của ứng dụng**.

## 8. Các built-in Key Vault roles cần nhớ

| Role | Nhiệm vụ phù hợp | Giới hạn quan trọng |
|---|---|---|
| **Key Vault Reader** | Đọc metadata của vault/objects theo quyền được định nghĩa | Không được đọc giá trị secret chỉ nhờ role này |
| **Key Vault Secrets User** | Đọc secret values | Không phải quyền tự thay/xóa secrets |
| **Key Vault Secrets Officer** | Quản lý secrets và các data-plane operations của secrets | Không tự gán Azure RBAC roles |
| **Key Vault Crypto User** | Thực hiện cryptographic operations được phép trên keys | Không mặc nhiên tạo/xóa keys |
| **Key Vault Crypto Officer** | Quản lý keys và crypto activities theo role | Không mặc nhiên quản trị role assignments |
| **Key Vault Certificate User** | Truy cập nội dung certificates theo role definitions | Không mặc nhiên đọc mọi secrets khác |
| **Key Vault Certificates Officer** | Quản trị certificate lifecycle | Không phải Owner của subscription |
| **Key Vault Administrator** | Quyền data plane rất rộng trên keys/secrets/certificates | Không tự đồng nghĩa Owner management-plane |
| **Key Vault Contributor** | Quản lý vault resource/control plane | Không tự đọc secret values khi RBAC mode |
| **Key Vault Data Access Administrator** | Quản lý assignments của một nhóm Key Vault data roles theo điều kiện có sẵn | Không phải unconstrained Owner |
| **Key Vault Purge Operator** | Các purge operations chuyên biệt khi được hỗ trợ | Không thay Data Administrator hoặc Reader |

**Lưu ý:** đây là hướng chọn role, **không thay cho bảng `actions` và `dataActions` thực**. Đặc biệt với certificate backing secrets, crypto algorithms, list metadata, purge và rotation operations, phải kiểm tra role definition đúng phiên bản và thử API thực tế.

### Chọn đúng role theo nhu cầu

~~~text
App API chỉ get DB password:     Key Vault Secrets User
Automation cần set/rotate:       Key Vault Secrets Officer
App ký hóa đơn:                  Key Vault Crypto User
Key management team:             Key Vault Crypto Officer
Certificate operator:            Key Vault Certificates Officer
Metadata-only auditor:           Key Vault Reader
Human emergency data access:     Key Vault Administrator + PIM, scope hẹp
~~~

Không dùng **Key Vault Administrator** như cách sửa nhanh mọi lỗi 403 của ứng dụng.

## 9. Ai có quyền gán role?

**Có quyền đọc secrets** khác với **quyền cấp người khác đọc secrets**.

Principal tạo role assignment phải có Azure management authorization tương ứng, ví dụ:

- **Owner** hoặc **User Access Administrator** theo scope/policy.
- **Role Based Access Control Administrator** theo điều kiện/giới hạn thực tế.
- **Key Vault Data Access Administrator** hỗ trợ một nhóm Key Vault roles với role assignment conditions, không phải quyền gán tất cả Azure roles.

**Key Vault Secrets Officer/Administrator** chủ yếu là data-plane roles, không tự động cho phép thêm IAM role assignments.

### Đường vòng nâng quyền cần chặn

Một người có quyền cập nhật vault configuration, nhất là **permission model**, có thể tìm đường chuyển về access policy mode rồi tự cấp quyền access policy nếu các guardrails cho phép. Dùng **Azure Policy**, change management, IaC review và phân quyền hạn chế cho người có `Microsoft.KeyVault/vaults/write` để tránh bypass RBAC governance.

## 10. Identity: client ID khác principal ID

| Giá trị | Bản chất | Dùng để |
|---|---|---|
| **Tenant ID** | Directory chứa danh tính | Xác định tenant/issuer |
| **Application/client ID** | ID của app/managed identity client | Client configuration; chọn UAMI khi SDK cần |
| **Principal/object ID** | ID của security principal trong tenant | **Gán role bằng `--assignee-object-id`** |
| **Vault ARM ID** | Resource ID của vault | Scope role assignment |
| **Vault URI** | HTTPS data-plane endpoint | SDK SecretClient/CryptographyClient |

Ví dụ user-assigned managed identity (UAMI):

~~~text
name: mi-commerce-api-prod
clientId:    <CLIENT_GUID>
principalId: <PRINCIPAL_OBJECT_GUID>

RBAC assignment uses: principalId
Java/Azure Identity UAMI selection uses: clientId
~~~

Không hoán đổi hai GUID này. Khi **system-assigned identity** bị xóa cùng compute và compute được tạo lại, principalId có thể đổi. Role assignments cũ có thể trỏ orphaned principal; triển khai mới phải reconcile và cấp quyền cho principalId mới.

## 11. Đường đi của một request đọc secret

~~~mermaid
sequenceDiagram
  participant A as Java app
  participant E as Microsoft Entra ID
  participant V as Key Vault
  A->>E: Lấy access token bằng managed identity
  E-->>A: Token cho Key Vault resource
  A->>V: GET /secrets/db-password + Bearer
  V->>V: Check token, vault permission model, networking
  V->>V: Evaluate RBAC dataActions + scope + principal
  alt authorized
    V-->>A: Secret value + metadata
  else not authorized
    V-->>A: 403 + diagnostic error
  end
~~~

Sơ đồ là mô hình logic, không khẳng định dịch vụ gọi Azure Resource Manager cho **từng** request. Quyền thực tế có caching/propagation.

### Phân biệt hai lớp lỗi

- **Azure Identity token acquisition lỗi:** SDK chưa lấy được access token, do runtime identity unavailable, credential chain, tenant hoặc network tới authority.
- **Key Vault 403:** API đã xử lý request nhưng từ chối vì authorization, permission model, network policy hoặc object operation.

Thành công khi `DefaultAzureCredential` lấy token **không chứng minh** principal có `Key Vault Secrets User`.

## 12. Tạo vault RBAC bằng Azure Portal

1. Xác minh **subscription/resource group** và tenant cho lab.
2. Tạo **Key Vault** có tên hợp lệ và region phù hợp.
3. Trong **Access configuration / Permission model**, chọn **Azure role-based access control**.
4. Kiểm tra soft delete/purge protection/retention theo chính sách.
5. Chọn firewall/public network access/Private Endpoint phù hợp; không mở public cho production chỉ để test.
6. Tạo vault, ghi **Vault URI** và **ARM resource ID**.
7. Vào **Access control (IAM)**, xem các role assignments hiện có/kế thừa.
8. **Add role assignment** cho identity ứng dụng, chọn **Key Vault Secrets User** và vault scope.
9. Phân quyền rotation/certificate/security admins bằng roles riêng.
10. Đợi propagation, kiểm thử API thực bằng đúng workload identity/network.

Tạo vault thành công không mặc nhiên cấp người tạo quyền đọc mọi secret value. Nếu Portal chỉ thấy metadata và không xem được values, trước tiên kiểm tra role data-plane của principal đang đăng nhập.

## 13. Azure CLI: đọc cấu hình vault

Ví dụ Bash trong Azure Cloud Shell/Linux terminal đã đăng nhập theo quy trình approved:

~~~bash
az account show \
  --query "{subscription:name,subscriptionId:id,tenantId:tenantId}" \
  -o json

RG="rg-commerce-lab"
KV="kv-commerce-lab"

az keyvault show \
  --resource-group "$RG" \
  --name "$KV" \
  --query "{id:id,name:name,rbac:properties.enableRbacAuthorization,network:properties.publicNetworkAccess}" \
  -o json
~~~

Tùy CLI version, schema trả về có thể khác hoặc thuộc tính được flatten. Nếu `rbac` hiển thị `null`, phải kiểm tra actual response/Portal; **không tự kết luận RBAC off chỉ vì JMESPath query không đúng**.

Lấy vault ARM scope:

~~~bash
KV_ID=$(az keyvault show \
  --resource-group "$RG" \
  --name "$KV" \
  --query id -o tsv)

echo "$KV_ID"
~~~

Dạng:

~~~text
/subscriptions/<SUB_ID>/resourceGroups/rg-commerce-lab/providers/Microsoft.KeyVault/vaults/kv-commerce-lab
~~~

## 14. CLI: xem role definitions và inherited assignments

~~~bash
az role definition list \
  --name "Key Vault Secrets User" \
  --query "[].{name:roleName,id:id,permissions:permissions}" \
  -o json

az role definition list \
  --name "Key Vault Contributor" \
  --query "[].{name:roleName,id:id,permissions:permissions}" \
  -o json
~~~

Phân biệt `actions`/`notActions` dành management plane và `dataActions`/`notDataActions` cho data plane. Một role tên “Contributor” không phải bằng chứng có `getSecret` data action.

Xem role assignments:

~~~bash
az role assignment list \
  --scope "$KV_ID" \
  --include-inherited \
  -o table
~~~

`--include-inherited` giúp nhìn quyền từ subscription/RG. Với group assignment, PIM, deny assignments hoặc CLI principal lookup restrictions, cần xem **effective access** và tenant identity bằng các công cụ IAM phù hợp, không chỉ đối chiếu display name.

## 15. Gán Key Vault Secrets User đúng principal và scope

Ví dụ **thay đổi quyền thực**; chỉ chạy trong vault lab hoặc theo change approval:

~~~bash
RG="rg-commerce-lab"
KV="kv-commerce-lab"

KV_ID=$(az keyvault show \
  --resource-group "$RG" --name "$KV" \
  --query id -o tsv)

PRINCIPAL_OBJECT_ID="<MANAGED_IDENTITY_PRINCIPAL_ID>"

az role assignment create \
  --assignee-object-id "$PRINCIPAL_OBJECT_ID" \
  --assignee-principal-type ServicePrincipal \
  --role "Key Vault Secrets User" \
  --scope "$KV_ID"
~~~

`--assignee-object-id` là **object/principal ID**, **không phải client ID**. `ServicePrincipal` đúng với identity loại service principal/managed identity; với user/group dùng principal type thực tế. `--scope` chỉ vault, không toàn subscription.

### Các lỗi thường gặp

- Caller thiếu quyền `Microsoft.Authorization/roleAssignments/write` ở scope.
- Vault còn dùng **access policy mode**.
- PrincipalId lấy từ UAMI khác ứng dụng đang sử dụng.
- Assignment tồn tại nhưng chưa propagation.
- Role gán ở vault khác hoặc parent scope bị deny/conditional constraints.
- IAM role đúng nhưng network/firewall từ workload vẫn không vào được vault.

**Không chạy create role assignment lặp nhiều lần để “đợi hết 403”.** Đầu tiên kiểm tra assignment ID và thực tế caller principal.

## 16. User-assigned identity: truy xuất clientId và principalId

~~~bash
UAMI_RG="rg-identities-lab"
UAMI_NAME="mi-commerce-api-lab"

az identity show \
  --resource-group "$UAMI_RG" \
  --name "$UAMI_NAME" \
  --query "{principalId:principalId,clientId:clientId,id:id}" \
  -o json

UAMI_PRINCIPAL_ID=$(az identity show \
  --resource-group "$UAMI_RG" --name "$UAMI_NAME" \
  --query principalId -o tsv)

az role assignment create \
  --assignee-object-id "$UAMI_PRINCIPAL_ID" \
  --assignee-principal-type ServicePrincipal \
  --role "Key Vault Secrets User" \
  --scope "$KV_ID"
~~~

Nếu ứng dụng Azure gắn nhiều user-assigned identities, SDK có thể yêu cầu `clientId`/environment variable `AZURE_CLIENT_ID` để chọn đúng identity. **Role assignment dùng `principalId`**, còn cấu hình chọn identity runtime thường dùng **`clientId`**.

### System-assigned identity

Đối với system-assigned identity, lấy principal ID từ chính Azure resource compute đang chạy; khi VM/Container App bị recreate, cần kiểm tra identity mới thay vì tin assignment cũ theo resource name.

## 17. Java SDK: truy cập secret bằng DefaultAzureCredential

Trong module Spring Boot/Java, sử dụng Azure SDK for Java với các dependencies:

~~~xml
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
<dependencies>
  <dependency>
    <groupId>com.azure</groupId>
    <artifactId>azure-identity</artifactId>
  </dependency>
  <dependency>
    <groupId>com.azure</groupId>
    <artifactId>azure-security-keyvault-secrets</artifactId>
  </dependency>
</dependencies>
~~~

Đây là POM fragment; `azure.sdk.bom.version` phải được project khai báo bằng version đã kiểm tra, không dùng giá trị đoán.

~~~java
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.security.keyvault.secrets.SecretClient;
import com.azure.security.keyvault.secrets.SecretClientBuilder;
import com.azure.security.keyvault.secrets.models.KeyVaultSecret;

public final class VaultReader {
    private final SecretClient client;

    public VaultReader(String vaultUrl) {
        this.client = new SecretClientBuilder()
            .vaultUrl(vaultUrl)
            .credential(new DefaultAzureCredentialBuilder().build())
            .buildClient();
    }

    public boolean canGetDemoSecret() {
        KeyVaultSecret item = client.getSecret("demo-config");
        // Tuyệt đối KHÔNG ghi item.getValue() vào logs.
        return item != null;
    }
}
~~~

**Lưu ý kỹ thuật:** `getSecret` lấy secret **value vào process memory** dù method chỉ trả boolean. Nó là bài test **data-plane get** thực sự, không phải metadata-only probe. Chỉ dùng secret lab không nhạy cảm cho thử nghiệm; với production đọc bằng logic nghiệp vụ cần thiết và bảo vệ giá trị trong memory. Nếu chỉ muốn xem metadata, sử dụng APIs/roles đọc metadata phù hợp.

### Identity khi chạy local và trên Azure

- **Local:** DefaultAzureCredential có thể lấy token từ developer tooling theo chain được hỗ trợ.
- **Azure:** có thể lấy từ system-assigned/user-assigned managed identity hoặc workload identity theo cấu hình.
- Hai môi trường có thể gọi cùng `getSecret` nhưng **hai principal khác nhau** → một nơi thành công, nơi khác 403.

## 18. Spring Boot: SecretClient singleton và cấu hình

Tránh tạo credential/client mới mỗi HTTP request hoặc request trực tiếp từ business code.

~~~java
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.security.keyvault.secrets.SecretClient;
import com.azure.security.keyvault.secrets.SecretClientBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class VaultConfiguration {

    @Bean
    public SecretClient secretClient(
            @Value("${app.key-vault.url}") String vaultUrl) {
        return new SecretClientBuilder()
            .vaultUrl(vaultUrl)
            .credential(new DefaultAzureCredentialBuilder().build())
            .buildClient();
    }
}
~~~

Cấu hình ngoài source:

~~~yaml
app:
  key-vault:
    url: ${AZURE_KEYVAULT_URL}
~~~

Ví dụ URL:

~~~text
AZURE_KEYVAULT_URL=https://kv-commerce-lab.vault.azure.net/
AZURE_CLIENT_ID=<USER_ASSIGNED_IDENTITY_CLIENT_ID_IF_REQUIRED>
~~~

Không log secret values/access tokens, không commit client secrets, và tách quyền runtime **Secrets User** với quyền rotation **Secrets Officer**. Trong production, lên kế hoạch cache/refresh/rotation: đọc Key Vault mỗi request có thể tăng độ trễ, chi phí operations và nguy cơ throttling; nhưng cache quá lâu khiến password mới không được dùng. Không có cache TTL chung phù hợp mọi workload.

Nếu dùng Spring Cloud Azure Key Vault configuration integration, cần kiểm tra chính xác version, precedence và refresh semantics; ví dụ SecretClient này **không tự kích hoạt Spring property sources**.

## 19. Key Vault Crypto User: ký và mã hóa mà không lấy private key

Một service phát hành hóa đơn cần tạo chữ ký điện tử cho hóa đơn nhưng không cần quản trị keys. Thiết kế nên là:

~~~text
Workload: mi-invoice-signer-prod
Vault: kv-signing-prod
Key: invoice-signing-key
Actions cần: sign/verify theo thuật toán và phiên bản khóa được hỗ trợ
Role candidate: Key Vault Crypto User
Actions không cần: create/delete keys, get secrets, assign IAM roles
~~~

### Phân biệt sử dụng key và quản trị key

- **Key Vault Crypto User** phù hợp khi ứng dụng thực hiện **cryptographic operations** được role/key policy cho phép.
- **Key Vault Crypto Officer** phục vụ identity quản trị keys theo quyền định nghĩa, không phải role mặc định cho app chỉ ký.
- **Key Vault Administrator** quá rộng cho một signing workload thông thường.
- **Key Vault Reader** có thể xem metadata mà không được ký/decrypt theo role đó.

Một `CryptographyClient` có thể gọi `sign`, `verify`, `encrypt`, `decrypt`, `wrapKey` hoặc `unwrapKey` theo loại khóa, algorithm và permitted key operations. **Không phải mọi key cho phép mọi algorithm**, và không phải mọi key material đều exportable.

### Key version và rotation

Một key identifier có thể chứa version:

~~~text
https://kv-signing-prod.vault.azure.net/keys/invoice-signing-key/<VERSION>
~~~

Nếu ký dữ liệu cần kiểm toán lâu dài, lưu version/algorithm cần thiết để verify chữ ký sau khi khóa được rotate. Quyết định dùng “latest key” hay pin version phải dựa vào giao thức nghiệp vụ, không để mặc định một cách mù quáng. Với CMK cho dịch vụ Azure, ngoài Crypto User còn có roles/permissions chuyên biệt của service; **không gán role rộng chỉ vì gọi là encryption**.

## 20. Certificate lifecycle và những quyền dễ bị nhầm

Một certificate trong Key Vault có thể liên kết tới object certificate, key và **backing secret**. Các nhu cầu khác nhau:

| Nhu cầu | Quyền cần đánh giá |
|---|---|
| Xem metadata: subject, expiry, issuer | Role có quyền metadata |
| Đọc certificate contents/public certificate | **Key Vault Certificate User** khi phù hợp |
| Tạo/import/renew certificate | **Key Vault Certificates Officer** theo role definitions |
| Đọc private-key-containing PFX qua backing secret | Xác minh chính xác certificate/secret data actions và exportability |
| Sử dụng key để ký/decrypt mà không export | Crypto role và key operation tương ứng |
| Gán thêm certificate consumer | Role-assignment management, không phải Certificate Officer đơn thuần |

**Không kết luận Certificates User có quyền đọc toàn bộ arbitrary secrets trong vault.** Ngược lại, cũng không giả định certificate consumer chỉ cần metadata nếu triển khai TLS cần private key theo cơ chế dịch vụ.

### Các lỗi certificate phổ biến

- Certificate expired do automation chưa renew.
- Key/certificate disabled.
- Private key export không hỗ trợ theo policy.
- Consumer service chưa refresh version mới.
- Thiếu quyền đọc backing object cần thiết.
- Vault private endpoint không reachable từ App Service/Application Gateway.
- Identity của consumer không phải identity được gán role.

**RBAC không tự gia hạn chứng chỉ.** Cần quản lý owner, expiry alert, renewal job, consumer reload và rollback.

## 21. Network security là lớp độc lập với Azure RBAC

~~~mermaid
flowchart LR
  APP["App / Managed identity"] --> AUTH["Entra token"]
  AUTH --> NET{"Key Vault DNS, route và firewall?"}
  NET -->|Blocked| NERR["Network denied / timeout / firewall 403"]
  NET -->|Allowed| VAULT["Key Vault data plane"]
  VAULT --> RBAC{"DataActions + scope cho principal?"}
  RBAC -->|No| F403["Authorization 403"]
  RBAC -->|Yes| OK["Get secret / crypto / certificate"]
~~~

Role **Key Vault Secrets User** không tự tạo VPN, VNet peering hoặc Private Endpoint. Ngược lại, **Private Endpoint** không tự cấp quyền đọc secret.

Kiểm tra lần lượt:

1. App resolve đúng **vault FQDN**; private DNS có trả địa chỉ private khi dùng Private Endpoint không?
2. Route/NSG/firewall/egress cho phép kết nối HTTPS tới vault?
3. Private Endpoint connection đã Approved và đúng subresource không?
4. Vault public network access/firewall settings theo policy?
5. Workload có egress tới các endpoint xác thực Entra ID cần thiết không?
6. TLS trust store, proxy, DNS forwarder/Private Resolver hoạt động?
7. Sau đó mới kiểm tra **principal + RBAC role + permission model**.

### Trusted Microsoft services không phải allow-all

Một cấu hình cho phép **trusted services** chỉ áp dụng cho tập dịch vụ/hoạt động được Azure chỉ định, không có nghĩa mọi dịch vụ Azure và mọi tenant đều được đi qua firewall. Data-plane RBAC vẫn cần hợp lệ.

### On-prem và private routing

Nếu Java app đặt tại chỗ và vault chỉ có Private Endpoint trong Azure VNet, cần **VPN/ExpressRoute hoặc mạng được phép**, private DNS forwarding và route. Biết vault URI không đồng nghĩa có network reachability.

## 22. Thay access policy bằng Azure RBAC: kế hoạch migration

Đổi permission model của vault đang dùng thật có thể làm tất cả app mất quyền. Không bắt đầu bằng một câu lệnh `az keyvault update` mà chưa chuẩn bị.

### Quy trình an toàn

1. **Inventory:** lập danh sách vault, access policies, identities và consumers.
2. **Operations mapping:** ghi rõ get/list/set/delete secrets, sign/decrypt keys, get/renew certificates, backup/restore và rotation.
3. **Scope review:** kiểm tra quyền từ subscription/RG có thể mở rộng sau khi dùng RBAC.
4. **Roles design:** map thành built-in/custom roles tối thiểu, tách reader, writer, operator.
5. **Pre-assign:** tạo Azure RBAC assignments cho principals đúng object IDs, đợi propagation.
6. **Lab/pilot test:** kiểm thử trên vault tương đương dùng RBAC, gồm identity runtime và network thật.
7. **Change window:** thống nhất thời điểm chuyển, SLA, stakeholders, rollback và backup/recovery plan theo policy.
8. **Switch mode:** chuyển vault sang Azure RBAC sau phê duyệt.
9. **Smoke test:** thử get/rotate/sign/certificate operations bằng các identity thực.
10. **Observe:** giám sát 401/403/5xx, secret refresh, cert bindings và applications.
11. **Remediate:** xử lý thiếu role/scope đúng chỗ, không cấp Owner toàn subscription.
12. **Policy guardrail:** yêu cầu Azure RBAC mode bằng Azure Policy khi phù hợp, ngăn drift về access policy mode.
13. **Audit:** lưu change ticket, role assignment IDs và test evidence.

### Vì sao gán role trước khi switch chưa đủ chứng minh?

Khi vault còn ở **access policy mode**, các data-plane RBAC assignments có thể tồn tại nhưng chưa được dùng để cho phép thao tác. Bởi vậy phải kiểm thử **sau cutover** hoặc trên pilot vault cùng loại, không kết luận “đã tạo role assignment nên chắc chắn migration an toàn”.

### Lệnh chuyển model — chỉ khi được phê duyệt

~~~bash
# HIGH IMPACT: chỉ sử dụng theo change plan trên vault được cấp phép.
az keyvault update \
  --resource-group "$RG" \
  --name "$KV" \
  --enable-rbac-authorization true
~~~

**Hậu quả:** Access policies cũ không còn là nguồn cấp quyền data plane trong RBAC mode. Nếu bỏ sót rotator, backup automation hay certificate consumer, chúng có thể gặp 403 ngay khi chuyển. Cần ghi trạng thái trước, có kế hoạch rollback và kiểm tra các guardrails ngăn switch ngược.

## 23. Azure Policy: khóa governance của permission model

Ngay cả khi principal không có Secrets User, một quản trị viên có quyền sửa vault configuration có thể thay đổi **permission model** và tạo đường tự nâng quyền theo access policy trong một số tình huống. Do đó, cần áp thêm governance:

- Policy chỉ cho phép vaults sử dụng **Azure RBAC** theo chuẩn tổ chức.
- Policy hạn chế public network access hoặc yêu cầu private endpoints với vault quan trọng.
- Policy enforce purge protection/retention theo yêu cầu compliance.
- Kiểm soát `Microsoft.KeyVault/vaults/write` và các principals có quyền sửa RBAC assignments.
- Role assignment thông qua IaC/code review, PIM và approval.
- Cảnh báo khi đổi permission model, network rules hoặc gán role rộng.
- Audit role assignments ở subscription/RG để phát hiện inheritance quá rộng.
- Tách subscription hoặc resource groups khi boundary môi trường cần chặt chẽ.

**Azure Policy deny có thể chặn thay đổi kể cả caller có Owner.** Không tắt policy ở scope cha chỉ để làm một bài lab chạy được.

## 24. PIM, quyền tạm thời và con người quản trị

Dùng **Microsoft Entra Privileged Identity Management (PIM)** cho những roles quyền cao khi có hỗ trợ/licensing:

~~~text
Developer:
  Lab Secrets User -> quyền cần thiết, scope nhỏ

On-call:
  Eligible Key Vault Administrator -> vault production cụ thể
  Activate -> MFA + justification + approval, limited duration

Security/IAM:
  Data Access Administrator hoặc phù hợp role-assignment management role
  Scope -> vault, có review

Application:
  Managed Identity + Secrets User/Crypto User
  Không có quyền cấp IAM roles
~~~

PIM giúp giảm quyền **thường trực** nhưng không cứu được một role **quá rộng** sau khi kích hoạt. Cần **scope hẹp, thời hạn ngắn, approval, audit và periodic access review**. Một số PIM features phụ thuộc entitlement/licensing; không mặc định khả dụng ở mọi tenant.

### Break-glass

Tài khoản emergency access cần:

1. Được bảo vệ chặt, có owners và quy trình truy cập khẩn cấp.
2. Không được dùng cho routine secret reads.
3. Có break-glass event monitoring và post-incident review.
4. Role/scope/thời hạn theo policy.
5. Có phương án kiểm tra network/data-path riêng nếu Key Vault bị ảnh hưởng.
6. Thường xuyên diễn tập trong phạm vi được phê duyệt.

Không dùng một script gán Owner cho mọi người làm “break-glass runbook”.

## 25. Soft delete, purge protection và RBAC

**Soft delete** giúp khôi phục một số vaults/objects đã bị xóa trong retention period. **Purge protection** giúp ngăn xóa vĩnh viễn sớm hơn retention theo service semantics. Nhưng:

- Không phải hệ thống **backup đầy đủ** thay cho recovery planning.
- RBAC quyết định các operations delete/recover/purge theo role/permission model.
- Các privileges destructive cần giới hạn scope và audit riêng.
- App chỉ đọc secret **không cần delete hoặc purge**.
- Quyền purge chuyên biệt không nên cấp cho daily operators nếu không có phê duyệt.
- Retention và purge-protection state phải tương thích quy định, đặc biệt khi tài nguyên chứa keys được dùng cho mã hóa dữ liệu khác.

### Trường hợp khó

Nếu key dùng làm CMK cho storage/database bị xóa/purge, dữ liệu khác có thể **không đọc được** dù bản thân storage vẫn tồn tại. Khi lên lịch key rotation/delete cần kiểm kê dependent resources, backup/restore strategy và khả năng khôi phục.

## 26. Secret rotation: tách reader và writer

~~~mermaid
flowchart LR
  ROT["Rotation job: Secrets Officer"] --> VAULT["Key Vault"]
  APP["App: Secrets User"] --> VAULT
  ROT --> BACK["Database / external service credential"]
  BACK --> VERIFY["Validate new credential"]
  VERIFY --> RELEASE["Deploy/refesh app secret version"]
  RELEASE --> MON["Monitor / rollback"]
~~~

RBAC cho phép application đọc và automation ghi secrets, **không tự đồng bộ password ở database**. Nếu database đổi password trước khi app refresh, ứng dụng có thể dừng hoạt động. Nếu Key Vault đổi secret nhưng target service chưa đổi password, cũng sẽ lỗi.

### Quy trình rotation có kiểm soát

1. Tạo credential mới tại target service theo khả năng dual credentials/overlap.
2. Set **new secret version** bằng rotation identity.
3. Kiểm thử credential mới, logs không chứa plaintext.
4. Deploy/reload ứng dụng dùng secret mới theo maintenance/rollout policy.
5. Quan sát error rate, connection pool, downstream 401/403.
6. Thu hồi credential cũ sau khi consumers không còn phụ thuộc.
7. Có rollback/compensation nếu rotation fail.
8. Ghi audit actor/time/version nhưng không lưu raw value.

Chỉ cấp **Key Vault Secrets User** cho runtime đọc. Automation chịu trách nhiệm rotation có thể dùng **Secrets Officer** tại scope phù hợp. Nếu rotation job còn cần sửa credential trong Azure SQL/external database, quyền bên đó **tách biệt** với Key Vault RBAC.

## 27. 403: phân loại trước khi thay quyền

~~~mermaid
flowchart TD
  E["Java SecretClient: failure"] --> STATUS{"Có HTTP response?"}
  STATUS -->|Không| NET["Network, DNS, proxy, TLS, auth endpoint"]
  STATUS -->|Có| CODE{"HTTP status / error code?"}
  CODE -->|401| ID["Token/credential/audience/tenant"]
  CODE -->|403 firewall| FIRE["Vault firewall/private endpoint"]
  CODE -->|403 authorization| MODE{"Vault RBAC mode?"}
  MODE -->|Không| POLICY["Access policies"]
  MODE -->|Có| ROLE["Object ID, role dataActions, scope, inheritance, propagation"]
  CODE -->|404| OBJ["Secret name/version/existence/visibility"]
  CODE -->|429/503| RETRY["Backoff/jitter/retry budget"]
~~~

### Ma trận troubleshooting

| Triệu chứng | Nguyên nhân khả dĩ | Kiểm tra |
|---|---|---|
| Contributor nhưng `getSecret` 403 | Management role không có dataActions | Secrets User tại vault scope |
| Secrets User, vault access policy mode | Sai permission model | Access configuration |
| Gán role cho UAMI clientId | Sai ID | Phải dùng principalId |
| App local OK, Azure 403 | Credentials/identity khác | Runtime managed identity |
| Role vừa gán vẫn 403 | Propagation/group/token cache | Kiểm tra assignment, đợi có giới hạn |
| 403 do firewall | Network không được phép | Private DNS/firewall/route |
| Role read nhưng `setSecret` 403 | Role không có write data action | Rotation identity + Secrets Officer |
| Metadata list OK nhưng value get 403 | Metadata role khác value role | Role definitions và API thực |
| Key sign 403 | Crypto role/algorithm/key state | Key Vault Crypto User/operations |
| Cert public OK nhưng private export fail | Certificate/backing secret/export policy | Exact API/role/cert properties |
| Role assignment create 403 | Caller thiếu ARM IAM write | Owner/UAA/KV Data Access Admin theo policy |
| Vault 404 | Tên resource/secret/version sai hoặc không có | Vault URL, object state |
| 429/503 | Throttling/transient failure | SDK retry, metrics, backoff |
| Connection timeout | DNS/VNet/Private Endpoint | Test từ đúng host |
| Access token acquisition fail | Managed identity unavailable | SDK credential chain, env |

**Service error codes thay đổi theo API/version**; có thể gặp các dạng `ForbiddenByRbac`, `ForbiddenByFirewall` hoặc message khác. Dựa trên **HTTP status, code thực tế và correlation ID** chứ không hard-code một chuỗi duy nhất.

## 28. Java SDK: xử lý lỗi an toàn

~~~java
import com.azure.core.exception.HttpResponseException;
import com.azure.security.keyvault.secrets.SecretClient;

public final class KeyVaultAccessProbe {
    private final SecretClient client;

    public KeyVaultAccessProbe(SecretClient client) {
        this.client = client;
    }

    public boolean canGetLabSecret(String name) {
        try {
            var item = client.getSecret(name);
            // Không in item.getValue(), token, headers hoặc raw response body.
            return item != null;
        } catch (HttpResponseException ex) {
            int status = ex.getResponse() == null
                ? -1 : ex.getResponse().getStatusCode();
            System.err.println("Key Vault request failed status=" + status);
            throw ex;
        }
    }
}
~~~

`getSecret` là request thực đọc giá trị secret, vì thế chỉ dùng một secret **lab không nhạy cảm** để thử. Production logs nên dùng **structured error category, requestId, operation và safe principal metadata** đã được redacted; không mặc định mọi exception message đều an toàn để công khai.

### Phân biệt retry và sửa quyền

- **401/403** do identity/role/network cấu hình sai: retry liên tục không chữa được.
- Vừa cấp role: có thể retest có giới hạn vì propagation, nhưng kiểm tra principal/scope trước.
- **429/503**: SDK retry/backoff có budget, tôn trọng service hints.
- Timeout: chẩn đoán DNS, proxy, TLS, Private Endpoint; không tự cấp thêm Owner.

## 29. Kiểm tra role assignments và data-plane test

**Role inspection** không thay được **API test thực**.

~~~bash
az role assignment list \
  --scope "$KV_ID" \
  --include-inherited \
  --query "[].{principal:principalId,role:roleDefinitionName,scope:scope}" \
  -o table
~~~

Khi dùng secret test lab, có thể kiểm tra data-plane `get` nhưng không in value:

~~~bash
az keyvault secret show \
  --vault-name "$KV" \
  --name "demo-config" \
  --query id \
  -o tsv
~~~

**Cảnh báo:** `secret show` **vẫn lấy secret value về tiến trình CLI** dù output filter chỉ in ID. Không dùng với secret production nếu không cần; để xem metadata-only hãy dùng API/list metadata phù hợp. Không test bằng một user Azure CLI có quyền khác identity mà ứng dụng sử dụng.

### Propagation không có thời gian bảo đảm cho mọi case

Sau role assignment, có thể có cache và độ trễ propagate ở Azure RBAC hoặc group/identity. Không ấn định thời gian chắc chắn 30 giây; đợi/retest bounded, giữ logs và xác minh assignments. Nếu role đúng nhưng vẫn 403 kéo dài, điều tra **tenant, principal, parent scope, PIM, deny assignment, vault mode, firewall**.

## 30. Azure Monitor: quản trị và data-plane audit

Có ít nhất hai luồng audit:

- **Management-plane**: Azure Activity Log cho role assignments, vault configuration và các thay đổi ARM.
- **Data-plane**: Key Vault diagnostic resource logs cho các operations secret/key/certificate theo categories và diagnostic settings được cấu hình.

| Cần quan sát | Nguồn / Ý nghĩa |
|---|---|
| Role assignment create/delete | Activity Log / IAM / PIM audit |
| Permission model switch | Activity Log, Azure Policy compliance |
| Secret get/set/delete outcomes | Key Vault resource audit logs |
| Key crypto operations failures | Key Vault audit logs |
| Purge/delete attempts | Data-plane/management audit tùy operation |
| Private endpoint/network changes | Network/ARM diagnostics |
| Secret/certificate expiry | Key Vault events/monitoring |
| Vault 403/429 và request latency | Resource metrics + application logs |
| Managed identity token errors | Workload logs/identity diagnostics |
| Cost spike | Cost Management, Logs ingestion |

### Kiểm tra diagnostic settings

~~~bash
KV_ID=$(az keyvault show \
  --resource-group "$RG" --name "$KV" \
  --query id -o tsv)

az monitor diagnostic-settings list \
  --resource "$KV_ID" \
  -o json
~~~

Đây là **lệnh chỉ đọc**. Có diagnostic setting không đồng nghĩa mọi audit categories đã bật, log đã gửi đúng workspace hoặc retention đúng. Kiểm tra cấu hình và dữ liệu thực.

### KQL ví dụ với AzureDiagnostics

Khi Log Analytics workspace dùng bảng `AzureDiagnostics` cho Key Vault logs:

~~~kusto
AzureDiagnostics
| where TimeGenerated >= ago(24h)
| where ResourceProvider =~ "MICROSOFT.KEYVAULT"
| summarize Events = count()
    by bin(TimeGenerated, 1h), ResultType, Resource
| order by TimeGenerated asc
~~~

Nếu dùng resource-specific tables, phải kiểm tra **tên bảng/cột thực** và viết query tương ứng; không khẳng định AzureDiagnostics luôn nhận dữ liệu. Không log raw secret values, private keys, tokens hoặc authorization headers. Secret names/URIs và caller identifiers cũng có thể nhạy cảm, cần privacy/log access policy.

## 31. Cảnh báo, access reviews và incident response

Alert khi:

1. Key Vault 403 tăng bất thường sau release hoặc migration.
2. Role **Key Vault Administrator** mới được gán ngoài change window.
3. Permission model bị đổi từ RBAC sang access policy ngoài quy trình.
4. Principal có secrets read bất thường theo IP/app/region/thời gian.
5. Có delete/purge/recover operations không mong đợi.
6. Certificate/secret sắp hết hạn nhưng rotation chưa hoàn tất.
7. Private Endpoint không available hoặc network egress bị chặn.
8. 429/latency tăng và làm nhiều applications fail startup.
9. 401/403 của managed identity xảy ra trên nhiều replicas.
10. Role assignments tại parent scope tạo quyền rộng ngoài chủ đích.

### Đừng báo động mọi lần đọc secret

Ứng dụng có cache refresh mỗi 10 phút có thể đọc secret hợp lệ theo lịch. Phân tích baseline theo principal, operation, endpoint, time window, và owner; alert cần ngưỡng có hành động thay vì tạo nhiễu.

### Access review hằng kỳ

- Inventory role assignments của vault và parent scopes.
- Kiểm tra principals không còn sử dụng, managed identities bị xóa.
- Kiểm tra role Administrator/Officer trong phạm vi không còn cần.
- Rà soát group membership và PIM activations.
- So permission map với code/application operations thật.
- Thu hồi quyền theo change approval, smoke-test workloads.
- Lưu evidence/owner/rationale cho ngoại lệ.

## 32. Bicep: quản lý role assignment như code

Ví dụ role assignment trên **vault đã tồn tại**, caller phải có `roleAssignments/write` theo policy:

~~~bicep
@description('Existing Key Vault name')
param vaultName string

@description('Managed identity principal/object ID')
param principalObjectId string

@description('Full ARM role definition ID of Key Vault Secrets User')
param secretsUserRoleDefinitionId string

resource vault 'Microsoft.KeyVault/vaults@2023-07-01' existing = {
  name: vaultName
}

resource grant 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(vault.id, principalObjectId, secretsUserRoleDefinitionId)
  scope: vault
  properties: {
    roleDefinitionId: secretsUserRoleDefinitionId
    principalId: principalObjectId
    principalType: 'ServicePrincipal'
  }
}
~~~

**Đây là minh họa schema cần xác minh** với phiên bản Bicep/ARM của dự án. Tham số role ID phải là **full ARM roleDefinitionId đúng** chứ không phải tên gõ tùy ý. File trên không tự tạo vault, managed identity, network hoặc chuyển permission model.

IaC giúp:

- Review thay role/scope trong pull request.
- Dùng role assignment GUID deterministic, tránh trùng.
- Theo dõi drift do thay đổi IAM thủ công.
- Quản lý khác biệt dev/staging/prod.
- Không lưu plaintext secret hoặc UAMI credentials trong repository.
- Reconcile principalId khi identity bị recreate.
- Kiểm thử đủ scope và guardrails trước deploy.

## 33. Chi phí và quota

Key Vault security design có ảnh hưởng đến chi phí:

| Khoản | Ví dụ |
|---|---|
| Vault/keys operations | Secret get/list/set, key crypto operations, certificates |
| Premium/HSM-backed keys | Phí phụ thuộc SKU, key type và pricing meter |
| Network | Private Endpoints, DNS Resolver, Firewall, egress |
| Compute | App/rotation job/Azure Functions/Container Apps |
| Monitoring | Azure Monitor/Log Analytics ingestion/retention |
| Operations | Cert renewal, backup, DR, security review |
| Retries | Excessive 403/429 hoặc đọc secret mỗi request |
| Environment separation | Nhiều vaults và policies cần quản lý |

Không tự ghi một đơn giá cố định vì giá phụ thuộc **region, tier, loại key, số lượng operations, dịch vụ liên quan và thời điểm**. Đo cost per successful secret retrieval hoặc crypto operation theo workload, không chỉ giá vault.

### Tối ưu không phá bảo mật

- Reuse SDK `SecretClient`, credential và HTTP connections.
- Cache secrets theo refresh/rotation SLO phù hợp, không dùng TTL vô hạn.
- Không đọc Key Vault mỗi HTTP request nếu một bản cache an toàn đáp ứng nhu cầu.
- Giới hạn retries khi permission sai, backoff khi 429/503.
- Chọn vault scope/roles theo ứng dụng, tránh roles rộng.
- Có tags owner/env/cost center, budgets và alerts.
- Log đủ điều tra nhưng không log mọi raw payload.

## 34. Case study: thương mại điện tử, signing và rotation

### Bối cảnh

Một sản phẩm thương mại điện tử có ba workloads:

- **commerce-api** (Spring Boot trên Container Apps): chỉ đọc secrets kết nối DB.
- **invoice-signer** (Java worker trên AKS): ký hóa đơn bằng key.
- **secret-rotator** (Azure Function): luân chuyển password định kỳ.

Công ty yêu cầu:

- Không secret plaintext trong Git/CI.
- Workloads không được tự cấp role IAM.
- API không đọc crypto signing key.
- Signing app không đọc payment provider token.
- Rotation job không được gán Owner toàn subscription.
- Có Private Endpoint, audit và break-glass runbook.

~~~mermaid
flowchart LR
  API["Container App + Managed Identity"] -->|Secrets User| V1["kv-commerce-secrets-prod"]
  SIGN["AKS Worker + Workload Identity"] -->|Crypto User| V2["kv-signing-prod"]
  ROT["Function rotation identity"] -->|Secrets Officer| V1
  SEC["Security / PIM"] --> IAM["Narrow scoped IAM management"]
  IAM -.-> V1
  IAM -.-> V2
  V1 --> MON["Monitor + Audit"]
  V2 --> MON
~~~

### Quyết định

1. Hai vaults có boundary riêng cho secrets và cryptographic keys.
2. Một identity riêng cho từng workload.
3. Role Secrets User tại `kv-commerce-secrets-prod` cho API.
4. Role Crypto User tại `kv-signing-prod` cho signer.
5. Role Secrets Officer tại vault secrets cho rotator.
6. IAM admin/PIM riêng cho role assignment changes.
7. Private endpoint, DNS và egress được kiểm tra từ từng host.
8. Secret rotation có validation, app refresh và rollback.
9. Alert cho 403/role changes/expiry/crypto failures.
10. Không gán Key Vault Administrator cho tất cả apps.

### Sự cố A: 403 dù vừa gán role

Team lấy **UAMI clientId** đưa vào lệnh gán role dùng `--assignee-object-id`. Sửa bằng cách truy vấn `principalId`, kiểm tra assignment đúng scope rồi retest; không gán Owner.

### Sự cố B: IAM đúng nhưng app timeout

Container Apps environment không resolve FQDN Key Vault tới private IP sau bật Private Endpoint. Sửa private DNS/route, không thay Key Vault role.

### Sự cố C: rotator mất quyền sau migration

Access policy cũ cho rotator `set` secrets. Sau khi chuyển RBAC, đội ngũ mới map quyền đọc cho app nhưng quên **Secrets Officer** cho rotator. Cần migration inventory/smoke test các service identities, không chỉ kiểm tra app chính.

## 35. Bài thực hành có kiểm soát

> **An toàn:** chỉ thao tác trên **subscription, resource group và Key Vault lab** được phê duyệt. Role assignments, permission model và network changes có thể ảnh hưởng quyền thực; không động đến production vault, không dùng secret thật hoặc in values.

### Phần A — Thiết lập

1. Xác định tenant/subscription/resource group lab và ngân sách.
2. Kiểm tra quyền tạo vault, gán role và mạng theo policy.
3. Tạo vault mới ở **Azure RBAC permission model**.
4. Xác nhận soft delete/purge protection và networking.
5. Xem Vault URI và ARM resource ID.
6. Tạo một **demo-config** secret không nhạy cảm bằng operator có quyền ghi.
7. Tạo/gắn managed identity lab.
8. Lấy principalId/clientId, ghi rõ mục đích của từng ID.
9. Đọc role definitions của Secrets User, Secrets Officer, Key Vault Reader.
10. Lập bảng expected access trước khi cấp quyền.

### Phần B — Cấp và kiểm tra RBAC

1. Gán Secrets User ở vault scope cho managed identity lab.
2. Dùng `az role assignment list --include-inherited` xác minh assignment.
3. Đợi propagation.
4. Đọc secret lab từ đúng workload identity/host.
5. Không in `getValue()` hoặc full secret JSON.
6. Test write/set bằng reader identity: phải bị từ chối.
7. Gán Secrets Officer cho rotation identity riêng.
8. Tạo phiên bản demo-config mới bằng rotator, audit operation.
9. Kiểm tra assignment inheritance/group/PIM trong Portal.
10. Dọn assignments lab theo change approval khi hoàn tất.

### Phần C — Kiểm thử network

1. Kiểm tra vault DNS/HTTPS từ Container Apps/VM test.
2. Nếu có Private Endpoint, xác nhận private IP resolution.
3. Test mạng đã allowed trước khi kết luận RBAC lỗi.
4. Thử unauthorised principal từ cùng mạng để thấy 403 role.
5. Thử network path không allowed trong environment cô lập để phân biệt firewall error.
6. Xác định principal thật của SDK qua provider config (không log token).
7. So sánh local developer credential với managed identity.
8. Kiểm tra logs/metrics của requests bị từ chối.
9. Không bật public access toàn Internet để vượt network policy.
10. Restore lab network configuration sau thử nghiệm.

### Phần D — Lập kế hoạch migration

1. Lập inventory access policies của một vault **giả định**.
2. Map principal/actions sang built-in roles tối thiểu.
3. Kiểm tra quyền từ subscription/RG kế thừa.
4. Chuẩn bị role assignments trước cutover.
5. Xây smoke-test matrix cho secrets reader, rotator, crypto user và certificate consumer.
6. Lập change window/rollback/incident escalation plan.
7. Giả lập role propagation chưa hiệu lực.
8. Giả lập rotator 403 sau migration, đưa ra remediation.
9. Đề xuất Policy guardrail bắt buộc RBAC mode.
10. Viết báo cáo least privilege và audit evidence.

## 36. Câu hỏi tự kiểm tra

**Câu 1.** Secret, key và certificate trong Key Vault có mục đích khác nhau như thế nào?

**Câu 2.** Management plane khác data plane ở những thao tác nào?

**Câu 3.** Vì sao Contributor/Key Vault Contributor không tự đọc được secret trong RBAC mode?

**Câu 4.** Vai trò của `dataActions` khác `actions` thế nào?

**Câu 5.** Access policies còn cấp data-plane access sau khi bật RBAC mode không?

**Câu 6.** Principal, role definition, role assignment và scope khác nhau thế nào?

**Câu 7.** Role assignment ở resource group có thể ảnh hưởng những vaults nào?

**Câu 8.** Vì sao Key Vault Administrator ở subscription là quá rộng?

**Câu 9.** Key Vault Reader có đọc được secret value không?

**Câu 10.** Secrets User và Secrets Officer dùng cho hai workloads nào?

**Câu 11.** Crypto User và Crypto Officer khác nhau ở trách nhiệm nào?

**Câu 12.** Certificates User có mặc nhiên đọc mọi arbitrary secret trong vault không?

**Câu 13.** Ai có quyền tạo Azure role assignment cho managed identity?

**Câu 14.** Vai trò đặc biệt của Key Vault Data Access Administrator là gì?

**Câu 15.** UAMI clientId khác principalId ở đâu?

**Câu 16.** System-assigned managed identity có thể thay principalId khi nào?

**Câu 17.** Có Secrets User nhưng vẫn 403 do vault firewall được không?

**Câu 18.** Private Endpoint có tự cấp RBAC quyền cho application không?

**Câu 19.** Vì sao không nên chuyển permission model mà chưa làm inventory?

**Câu 20.** Tại sao phải kiểm tra rotator/cert consumer khi migrate, không chỉ app reader?

**Câu 21.** Azure Policy giúp ngăn bypass RBAC bằng permission model change thế nào?

**Câu 22.** Vì sao gán role xong có thể vẫn gặp 403 vài phút?

**Câu 23.** App local dùng DefaultAzureCredential có chắc cùng principal với app Azure không?

**Câu 24.** Vì sao SDK test `getSecret` không nên in secret value?

**Câu 25.** Role assignment inspection và test data-plane operation khác nhau gì?

**Câu 26.** Secret rotation có tự thay password trong database khi chỉ set secret version không?

**Câu 27.** Soft delete/purge protection giải quyết gì và có thay backup không?

**Câu 28.** Audit log management-plane và data-plane khác nhau thế nào?

**Câu 29.** Vì sao các quyền Owner/Admin qua parent scopes phải nằm trong access reviews?

**Câu 30.** Tại sao không gán Secrets Officer cho mọi application chỉ đọc?

**Câu 31.** Vì sao read private key contents khác với thực hiện crypto operation tại Key Vault?

**Câu 32.** Điều gì quyết định chọn một hay nhiều vaults cho các security boundaries?

**Tiêu chí hoàn thành:** người học phân biệt đúng permission models và management/data plane, chọn role ít quyền nhất, gán Secrets User cho managed identity bằng principalId tại vault scope, kiểm chứng actual data-plane access từ đúng workload/network, giải thích 403/propagation/firewall, lập kế hoạch RBAC migration, security governance, rotation, logging và chi phí.

## Kết luận

**Phân quyền Key Vault bằng Azure RBAC** nghĩa là kiểm soát **principal nào**, có **role và data actions gì**, tại **scope nào**, trong **permission model** nào. **Contributor** là quyền quản trị resource, không tự cấp đọc secret value trong RBAC mode. Ứng dụng chỉ cần đọc secret nên bắt đầu bằng **Key Vault Secrets User**; signing workloads dùng crypto role, rotation identities dùng quyền ghi phù hợp và role assignments được quản trị bởi IAM/PIM theo scope hẹp.

Một hệ thống Azure an toàn còn cần **Microsoft Entra ID/managed identity, Private Endpoint và DNS/firewall, Azure Policy guardrails, monitoring/audit, propagation-aware troubleshooting, rotation, soft delete và access reviews**. Hãy thử đúng API từ đúng workload identity và network path; **role assignment được tạo thành công chưa phải bằng chứng dữ liệu đã được truy cập an toàn**, và giải pháp cho 403 không bao giờ nên mặc định là gán Administrator toàn subscription.


