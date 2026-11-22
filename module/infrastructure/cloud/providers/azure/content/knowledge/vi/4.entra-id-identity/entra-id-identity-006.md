# Managed identity do hệ thống và người dùng quản lý

Trong module **CLOUD_PROVIDERS_AZURE**, chúng ta khám phá hệ sinh thái Microsoft Azure từ subscription, resource group và Microsoft Entra ID đến mạng ảo, tính toán, lưu trữ và dữ liệu, đồng thời học cách triển khai, giám sát, bảo vệ và kiểm soát chi phí một kiến trúc ứng dụng trên Azure. Ở chương **Danh tính với Microsoft Entra ID**, câu hỏi quan trọng là: ứng dụng có thể truy cập Azure Key Vault, Storage hoặc Azure SQL bằng cách nào mà không phải lưu mật khẩu hay client secret trong mã nguồn?

**Managed identity** (danh tính được quản lý) cho phép một workload chạy trên Azure lấy access token do Microsoft Entra ID cấp, trong khi Azure quản lý thông tin xác thực của danh tính phía nền tảng. Có hai loại: **system-assigned managed identity** (danh tính do hệ thống gán) và **user-assigned managed identity** (danh tính do người dùng tạo và gán).

Sau bài học, bạn có thể phân biệt hai loại danh tính theo vòng đời và khả năng tái sử dụng, gán quyền truy cập phù hợp, triển khai ví dụ với Azure CLI và Java SDK, chẩn đoán lỗi, cũng như thiết kế danh tính an toàn cho một hệ thống nhiều môi trường.

## 1. Vì sao workload cần một danh tính?

Giả sử API đặt hàng chạy trên Azure App Service cần đọc một secret từ Azure Key Vault. Nếu API giữ client secret của một service principal trong file cấu hình, pipeline hoặc biến môi trường, đội vận hành phải phân phối, xoay vòng và bảo vệ secret đó. Khi thông tin đăng nhập bị lộ, kẻ tấn công có thể giả mạo ứng dụng.

Managed identity giải quyết nhu cầu lưu credential dài hạn của **chính danh tính Azure này**: khi workload đang chạy trên một dịch vụ Azure có hỗ trợ, Azure cung cấp cơ chế lấy token để ứng dụng xác thực với dịch vụ đích. Azure Identity SDK có thể thực hiện luồng lấy token và làm mới token cho ứng dụng.

```text
Ứng dụng chạy trên Azure
    |
    | (1) Yêu cầu access token cho dịch vụ đích
    v
Cơ chế managed identity của Azure
    |
    | (2) Xác thực workload qua Microsoft Entra ID
    v
Access token của danh tính workload
    |
    | (3) Gửi token đến Key Vault / Storage / Azure SQL
    v
Dịch vụ đích kiểm tra token và quyền truy cập
    |
    +-- Đủ quyền: thực hiện thao tác
    +-- Thiếu quyền hoặc điều kiện: từ chối
```

Sơ đồ mô tả nguyên lý; endpoint và chi tiết cấp token tùy thuộc dịch vụ lưu trữ workload và thư viện khách. Ứng dụng thường nên dùng SDK chính thức thay vì tự xây dựng các lệnh HTTP đến endpoint cấp token.

Phải phân biệt:

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| **Identity** | Workload đang hoạt động với tư cách nào | Principal của API đặt hàng |
| **Authentication** | Danh tính được xác thực để nhận token | Entra ID cấp access token |
| **Authorization** | Principal được phép làm gì tại tài nguyên đích | Đọc secret cụ thể trong Key Vault |

**Bật managed identity không tự cấp quyền đọc dữ liệu.** Bạn vẫn phải gán quyền ở dịch vụ đích thông qua Azure RBAC hoặc mô hình cấp quyền thích hợp, đồng thời đáp ứng các giới hạn mạng và chính sách của dịch vụ.

## 2. Managed identity và Microsoft Entra ID

Managed identity là danh tính dành cho workload, không phải tài khoản của người dùng tương tác. Azure tạo và quản lý một **service principal** tương ứng trong tenant Microsoft Entra ID. Khi workload gọi dịch vụ có hỗ trợ Entra ID, ứng dụng lấy token đại diện cho principal đó.

Các ID quan trọng:

| Tên | Diễn giải | Mục đích |
|---|---|---|
| `tenantId` | ID tenant chứa danh tính | Xác định tenant của principal |
| `principalId` / Object ID | ID của service principal trong Entra ID | Dùng khi gán role và đối chiếu quyền |
| `clientId` | ID nhận diện danh tính cho ứng dụng/SDK | Giúp chọn đúng user-assigned identity |
| `id` / Azure Resource ID | Đường dẫn resource của user-assigned identity | Dùng để gán identity cho host Azure |

Không được dùng lẫn `principalId`, `clientId` và Resource ID. Ví dụ, Azure CLI có thể cần `--assignee-object-id` là principal ID khi tạo role assignment, nhưng `--identities` thường nhận Azure Resource ID của user-assigned identity.

Managed identity thích hợp cho giao tiếp **ứng dụng đến dịch vụ**. Nó không tự đại diện cho người dùng cuối đang đăng nhập; nếu API cần gọi một dịch vụ thay mặt người dùng, bạn phải thiết kế cơ chế xác thực và delegated authorization của người dùng riêng.

## 3. System-assigned managed identity

**System-assigned identity** được bật trên chính một Azure resource hỗ trợ tính năng này, ví dụ một Azure App Service, Function App hoặc virtual machine.

Vòng đời:

1. Tạo resource lưu trữ ứng dụng.
2. Bật system-assigned identity trên resource.
3. Azure tạo và gắn service principal do nền tảng quản lý.
4. Cấp quyền cho `principalId` tại các dịch vụ đích.
5. Khi xóa resource hoặc tắt system-assigned identity, danh tính gắn với resource đó bị xóa.

Mỗi resource có tối đa **một system-assigned identity** của chính nó. Danh tính này không thể được tách riêng để gán lại trực tiếp cho resource khác. Nếu xóa rồi tạo lại App Service, principal ID mới có thể khác, vì vậy quyền đã cấp cho principal cũ cần được cấu hình lại.

**Khi dùng:** một API có vòng đời độc lập chỉ cần quyền của riêng nó, hoặc một môi trường thử nghiệm được tạo và xóa cùng bộ tài nguyên. System-assigned identity thường giảm nhu cầu quản lý thêm một Azure resource dành cho identity.

## 4. User-assigned managed identity

**User-assigned identity** được tạo trước như một Azure resource độc lập trong resource group. Sau đó bạn chủ động gán nó cho một hoặc nhiều Azure resource được hỗ trợ.

Vòng đời:

1. Tạo resource user-assigned identity và Azure quản lý principal tương ứng trong Entra ID.
2. Gán identity cho host Azure được hỗ trợ.
3. Gán quyền cho `principalId` tại dịch vụ đích.
4. Khi thay thế hoặc xóa host, identity vẫn tồn tại nếu không bị xóa riêng.
5. Có thể gán identity đó cho host khác khi phù hợp với nhu cầu bảo mật và quy định hỗ trợ.

**Khi dùng:** cần một principal ổn định qua các lần thay App Service, hoặc cần chia sẻ có chủ đích cùng một tập quyền cho nhiều workload. Việc chia sẻ cũng làm tăng phạm vi ảnh hưởng: nếu workload A bị xâm phạm, kẻ tấn công có thể sử dụng quyền của identity chung mà workload B cũng dùng.

Tên gọi **user-assigned** chỉ cách *người quản trị tạo và gán danh tính*. Nó **không phải tài khoản cá nhân của một người dùng** và cũng không yêu cầu người dùng tự xoay vòng mật khẩu của managed identity.

## 5. So sánh hai loại managed identity

| Tiêu chí | System-assigned | User-assigned |
|---|---|---|
| Cách tạo | Bật trên Azure resource | Tạo identity thành Azure resource riêng |
| Vòng đời | Gắn với resource chủ | Tồn tại độc lập với các resource sử dụng |
| Xóa host | Identity gắn với host bị xóa | Identity riêng có thể tiếp tục tồn tại |
| Gán cho nhiều host | Không | Có, với host được hỗ trợ |
| Một resource có thể dùng bao nhiêu | Tối đa một system-assigned | Có thể dùng nhiều user-assigned nếu dịch vụ hỗ trợ |
| Chọn token | Thường dùng identity gắn với resource | Thường chọn bằng `clientId` hoặc bộ chọn được SDK hỗ trợ |
| Điểm mạnh | Ít đối tượng quản lý, quyền bám sát workload | Principal ổn định, dễ dùng trong quy trình thay host |
| Rủi ro chính | Tạo lại resource thì phải gán quyền cho principal mới | Chia sẻ sai có thể mở rộng phạm vi quyền |

Một số Azure resource cho phép bật system-assigned identity đồng thời gán user-assigned identities. Khi có nhiều identity, ứng dụng phải chọn rõ identity mong muốn; một token hợp lệ của principal A không đồng nghĩa principal A có quyền của principal B.

Chọn **system-assigned** nếu chỉ một workload cần quyền và danh tính nên biến mất theo host. Chọn **user-assigned** nếu danh tính cần duy trì qua thay host hoặc thực sự phải được nhiều resource dùng chung. Nếu các workload có quyền khác nhau, ưu tiên principal riêng để tuân thủ nguyên tắc ít quyền nhất.

## 6. RBAC: xác thực thành công chưa chắc được phép truy cập

Sau khi managed identity nhận access token, dịch vụ đích kiểm tra token và quyền của principal. Token phải được cấp cho đúng **audience/resource**. Token dùng cho Azure Resource Manager không mặc nhiên cho phép đọc dữ liệu trong Key Vault.

Với Azure RBAC, hãy chọn **role** và **scope** đúng nhu cầu:

| Nhu cầu | Vai trò tham khảo | Phạm vi nên cân nhắc |
|---|---|---|
| Đọc giá trị secret trong Key Vault | `Key Vault Secrets User` | Key Vault cần dùng |
| Đọc blob trong Storage | `Storage Blob Data Reader` | Container hoặc Storage Account phù hợp |
| Đọc/ghi blob | `Storage Blob Data Contributor` | Chỉ phạm vi dữ liệu cần ghi |
| Xem metadata quản lý tài nguyên | `Reader` | Resource hoặc resource group tương ứng |

Các quyền **control plane** (quản lý Azure resources) khác với quyền **data plane** (đọc/ghi dữ liệu bên trong dịch vụ). Gán `Contributor` ở resource group không tự động cấp quyền đọc secret của Key Vault hoặc dữ liệu blob.

Azure Key Vault có hai mô hình cấp quyền thường gặp: **Azure RBAC** và **vault access policies**. Ví dụ thực hành dưới đây giả định Key Vault đang dùng **Azure RBAC permission model**. Nếu vault dùng access policy, phải cấu hình quyền theo đúng mô hình của vault; một role assignment RBAC chưa đủ để đọc secret.

## 7. Thực hành: system-assigned identity cho App Service

Giả sử API `orders-api` chạy trên Azure App Service cần đọc một secret từ Key Vault. Resource group, Web App và Key Vault đã tồn tại. Người thao tác có quyền chỉnh identity trên Web App và cấp role tại vault. Các tên sau là minh họa; thay bằng tài nguyên thực tế và kiểm tra subscription trước khi dùng:

```bash
APP_RG=rg-orders-prod-app
APP_NAME=app-orders-prod-001
VAULT_NAME=kv-orders-prod-001

az account show --output table
az account set --subscription "<subscription-id>"
```

### Bước 1: Bật identity

```bash
az webapp identity assign \
  --resource-group "$APP_RG" \
  --name "$APP_NAME"

az webapp identity show \
  --resource-group "$APP_RG" \
  --name "$APP_NAME" \
  --output json
```

Lấy ID của principal và ID của vault:

```bash
APP_PRINCIPAL_ID=$(az webapp identity show \
  --resource-group "$APP_RG" \
  --name "$APP_NAME" \
  --query principalId --output tsv)

VAULT_RESOURCE_ID=$(az keyvault show \
  --name "$VAULT_NAME" \
  --query id --output tsv)
```

### Bước 2: Kiểm tra mô hình phân quyền và cấp quyền

```bash
az keyvault show \
  --name "$VAULT_NAME" \
  --query properties.enableRbacAuthorization \
  --output tsv
```

Khi kết quả là `true`, có thể cấp quyền đọc secret cho principal theo RBAC:

```bash
az role assignment create \
  --assignee-object-id "$APP_PRINCIPAL_ID" \
  --assignee-principal-type ServicePrincipal \
  --role "Key Vault Secrets User" \
  --scope "$VAULT_RESOURCE_ID"
```

Scope là một vault cụ thể, không phải toàn subscription. Role assignment có thể cần thời gian để được áp dụng đầy đủ. Nếu Key Vault dùng access policy, áp dụng phương thức quản lý quyền tương ứng của vault thay vì chỉ chạy lệnh trên.

### Bước 3: Cấu hình địa chỉ Key Vault

```bash
az webapp config appsettings set \
  --resource-group "$APP_RG" \
  --name "$APP_NAME" \
  --settings KEY_VAULT_URL="https://$VAULT_NAME.vault.azure.net/"
```

`KEY_VAULT_URL` là địa chỉ dịch vụ, không phải client secret. Mã ứng dụng sẽ dùng managed identity để lấy token.

### Bước 4: Đọc secret bằng Azure SDK cho Java

Ứng dụng Java cần các thư viện tương thích `azure-identity` và `azure-security-keyvault-secrets`. Trong môi trường Azure đã bật system-assigned identity, có thể dùng `DefaultAzureCredential`:

```java
import com.azure.core.credential.TokenCredential;
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.security.keyvault.secrets.SecretClient;
import com.azure.security.keyvault.secrets.SecretClientBuilder;

public final class OrdersSecrets {
    public static String readToken() {
        String vaultUrl = System.getenv("KEY_VAULT_URL");
        if (vaultUrl == null || vaultUrl.isBlank()) {
            throw new IllegalStateException("KEY_VAULT_URL is required");
        }

        TokenCredential credential =
                new DefaultAzureCredentialBuilder().build();

        SecretClient client = new SecretClientBuilder()
                .vaultUrl(vaultUrl)
                .credential(credential)
                .buildClient();

        return client.getSecret("orders-service-token").getValue();
    }
}
```

SDK sẽ dùng nguồn xác thực phù hợp với môi trường. Trên máy phát triển, `DefaultAzureCredential` có thể chọn tài khoản đã đăng nhập bằng công cụ phát triển tương thích; trên Azure nó có thể chọn managed identity. Vì vậy, danh tính chạy local và danh tính của App Service **không nhất thiết giống nhau**. Phải cấp quyền và kiểm tra riêng trong từng môi trường.

Không ghi giá trị secret hoặc access token vào log, stdout, thông báo lỗi hay telemetry. Nếu cần bảo đảm ứng dụng production chỉ sử dụng managed identity, có thể chọn `ManagedIdentityCredential` tường minh thay cho chuỗi credential tổng hợp.

## 8. Thực hành: user-assigned identity có vòng đời độc lập

Giả sử đội vận hành sẽ thay thế App Service trong một đợt nâng cấp nhưng muốn danh tính truy cập Key Vault và các role assignments vẫn được duy trì. Có thể tạo một user-assigned identity độc lập.

### Bước 1: Tạo identity và lấy các định danh

Giả sử resource group dành cho identities đã tồn tại:

```bash
IDENTITY_RG=rg-orders-prod-identities
IDENTITY_NAME=id-orders-prod-kv

az identity create \
  --resource-group "$IDENTITY_RG" \
  --name "$IDENTITY_NAME" \
  --location southeastasia
```

Lấy Azure Resource ID, principal ID và client ID:

```bash
UAMI_RESOURCE_ID=$(az identity show \
  --resource-group "$IDENTITY_RG" \
  --name "$IDENTITY_NAME" \
  --query id --output tsv)

UAMI_PRINCIPAL_ID=$(az identity show \
  --resource-group "$IDENTITY_RG" \
  --name "$IDENTITY_NAME" \
  --query principalId --output tsv)

UAMI_CLIENT_ID=$(az identity show \
  --resource-group "$IDENTITY_RG" \
  --name "$IDENTITY_NAME" \
  --query clientId --output tsv)
```

Phân biệt cách dùng:

- `UAMI_RESOURCE_ID` dùng để gán identity cho Azure resource.
- `UAMI_PRINCIPAL_ID` dùng làm đối tượng nhận quyền trên dịch vụ đích.
- `UAMI_CLIENT_ID` giúp SDK chọn đúng identity khi workload có nhiều danh tính.

### Bước 2: Gán user-assigned identity cho App Service

```bash
az webapp identity assign \
  --resource-group "$APP_RG" \
  --name "$APP_NAME" \
  --identities "$UAMI_RESOURCE_ID"

az webapp identity show \
  --resource-group "$APP_RG" \
  --name "$APP_NAME" \
  --output json
```

Kiểm tra phần `userAssignedIdentities` trong kết quả và xác nhận identity đúng đã được gán. Nếu resource đồng thời sử dụng system-assigned identity, xác nhận trạng thái của cả hai loại identity sau thao tác. Azure resource chỉ có thể sử dụng những danh tính và cách gán mà dịch vụ đó hỗ trợ.

### Bước 3: Cấp quyền đọc secret cho user-assigned principal

```bash
az role assignment create \
  --assignee-object-id "$UAMI_PRINCIPAL_ID" \
  --assignee-principal-type ServicePrincipal \
  --role "Key Vault Secrets User" \
  --scope "$VAULT_RESOURCE_ID"
```

Sau đó, kiểm tra role assignment ở phạm vi vault. Quyền được gán cho **identity độc lập**, nên có thể tiếp tục có hiệu lực khi bạn thay đổi host và gán lại identity đó cho workload thay thế. Điều này không loại bỏ các điều kiện về quyền truy cập mạng, tên tài nguyên, tenant và dịch vụ hỗ trợ.

### Bước 4: Chỉ định identity cho ứng dụng

Đặt Client ID và URL của vault trong cấu hình App Service:

```bash
az webapp config appsettings set \
  --resource-group "$APP_RG" \
  --name "$APP_NAME" \
  --settings AZURE_CLIENT_ID="$UAMI_CLIENT_ID" \
             KEY_VAULT_URL="https://$VAULT_NAME.vault.azure.net/"
```

Trong Java, có thể chọn danh tính theo Client ID bằng `ManagedIdentityCredentialBuilder`:

```java
import com.azure.core.credential.TokenCredential;
import com.azure.identity.ManagedIdentityCredentialBuilder;
import com.azure.security.keyvault.secrets.SecretClient;
import com.azure.security.keyvault.secrets.SecretClientBuilder;

public final class UserAssignedVaultClient {
    public static SecretClient create() {
        String clientId = System.getenv("AZURE_CLIENT_ID");
        String vaultUrl = System.getenv("KEY_VAULT_URL");

        if (clientId == null || clientId.isBlank()) {
            throw new IllegalStateException("AZURE_CLIENT_ID is required");
        }
        if (vaultUrl == null || vaultUrl.isBlank()) {
            throw new IllegalStateException("KEY_VAULT_URL is required");
        }

        TokenCredential credential = new ManagedIdentityCredentialBuilder()
                .clientId(clientId)
                .build();

        return new SecretClientBuilder()
                .vaultUrl(vaultUrl)
                .credential(credential)
                .buildClient();
    }
}
```

`ManagedIdentityCredential` cần host hoặc môi trường được SDK hỗ trợ để lấy managed identity token. Chạy đoạn code này trên laptop thông thường không tự có danh tính Azure. Khi phát triển local, có thể dùng `DefaultAzureCredential` với tài khoản nhà phát triển đã đăng nhập và có quyền phù hợp.

Nếu ứng dụng dùng `DefaultAzureCredential` trong môi trường Azure, `AZURE_CLIENT_ID` là một cách thường dùng để chỉ định user-assigned managed identity. Tuy nhiên, chuỗi `DefaultAzureCredential` có thể kiểm tra các nguồn credential khác, vì vậy với production cần xác nhận credential thực sự được chọn và tránh cấu hình dư thừa có thể làm thay đổi principal.

## 9. Thiết kế cho kiến trúc nhiều workload và môi trường

Giả sử hệ thống thương mại điện tử có API trên App Service, một Azure Function xử lý hóa đơn, Azure Storage và Key Vault. Mỗi môi trường dev, test và production cần được quản lý và phân quyền riêng.

Một thiết kế tham khảo:

| Workload | Danh tính đề xuất | Quyền | Lý do |
|---|---|---|---|
| `orders-api-dev` | System-assigned riêng | Đọc secret và dữ liệu dev cần thiết | Được tạo/xóa cùng môi trường dev |
| `orders-api-prod` | System-assigned riêng | Đọc secret production của API | Phân quyền riêng cho API |
| `invoice-worker-prod` | System-assigned riêng | Chỉ dữ liệu hóa đơn hoặc queue cần thiết | Không chia sẻ quyền nhạy cảm của API |
| Host cũ và host mới trong kế hoạch thay thế một workload | User-assigned có quản lý tập trung | Quyền cố định của workload đó | Duy trì principal khi chuyển host |

Ở ví dụ trên, Key Vault có thể cấp quyền cho **nhiều principals riêng**. Hai ứng dụng cùng đọc một vault không bắt buộc phải chia sẻ một user-assigned identity.

Các nguyên tắc:

1. **Phân tách dev/test/prod:** identity ở môi trường dev không nên có quyền tới dữ liệu production.
2. **Least privilege:** cấp role nhỏ nhất và scope hẹp nhất đáp ứng yêu cầu.
3. **Ranh giới trách nhiệm:** mỗi identity nên có owner, mục đích, danh sách dịch vụ đích và các workload sử dụng rõ ràng.
4. **Infrastructure as Code:** quản lý gán identity và role assignments trong Bicep, ARM hoặc công cụ IaC được tổ chức sử dụng.
5. **Quy trình thay host:** cập nhật danh sách resource gán identity, kiểm thử lấy token và quyền thực tế trước khi ngừng host cũ.

Managed identity không thay thế xác thực cho người dùng cuối. Nếu ứng dụng cần biết nhân viên nào đang gọi API, vẫn phải xác thực người dùng và thực hiện phân quyền người dùng ở tầng ứng dụng.

## 10. Chẩn đoán sự cố

Thông báo lỗi thường giúp phân biệt không lấy được token, lấy được token nhưng thiếu quyền, và kết nối mạng bị chặn.

| Triệu chứng | Khả năng xảy ra | Cách kiểm tra |
|---|---|---|
| Không tìm thấy managed identity | Identity chưa bật/gán, chạy ở host không hỗ trợ hoặc cấu hình sai | Kiểm tra mục Identity của resource và môi trường thực thi |
| Không chọn được identity giữa nhiều lựa chọn | Thiếu Client ID hoặc chọn sai identity | Chỉ định đúng `AZURE_CLIENT_ID` / `clientId` và xác nhận identity được gán |
| Lấy token được nhưng dịch vụ trả `403 Forbidden` | Thiếu quyền data plane, sai scope, vault dùng access policy hoặc chính sách khác từ chối | Đối chiếu principal ID, role, scope và mô hình cấp quyền |
| Dịch vụ trả `401 Unauthorized` | Token thiếu, sai audience, hết hạn hoặc không hợp lệ | Kiểm tra cách SDK yêu cầu và gửi token |
| Role đúng nhưng không tới được Key Vault | Firewall, private endpoint, DNS hoặc tuyến mạng bị chặn | Kiểm tra networking riêng với kiểm tra identity |
| Vừa cấp role nhưng vẫn bị từ chối | RBAC chưa lan truyền hoàn toàn hoặc token/cache cũ | Đối chiếu thời điểm cấp quyền, thử sau khi quyền được áp dụng |
| Tạo lại App Service thì mất quyền | System-assigned principal mới khác principal cũ | Cấp role cho principal mới theo pipeline/IaC |
| Nhiều workload đồng thời lỗi sau khi xóa một identity | Có user-assigned identity dùng chung đã bị xóa | Kiểm kê những host cùng sử dụng identity và kế hoạch thay thế |

Quy trình chẩn đoán có thứ tự:

1. Xác định workload đang chạy ở đâu, có hỗ trợ managed identity không và identity nào đã được bật/gán.
2. Xác định principal thực sự được SDK sử dụng. Không in access token hoặc secret ra log để kiểm tra.
3. Kiểm tra xem bước lấy token có thành công không. Nếu thất bại, tập trung vào host, identity configuration và client selector.
4. Nếu lấy token được nhưng gọi dịch vụ thất bại, kiểm tra role assignment, scope, thời gian áp dụng quyền và mô hình phân quyền của dịch vụ đích.
5. Kiểm tra mạng, DNS, firewall và private endpoint nếu lỗi liên quan đến kết nối.
6. Đối chiếu log ứng dụng, Azure Activity Log và các nhật ký chẩn đoán của dịch vụ/Entra ID có sẵn.

Không khắc phục `403` bằng cách cấp `Owner` trên subscription hoặc tắt toàn bộ firewall. Hãy sửa đúng vấn đề về principal, role, scope hoặc mạng.

## 11. Vòng đời và nguyên tắc bảo mật

Managed identity giảm việc lưu client secret phục vụ xác thực workload, nhưng không có nghĩa workload miễn nhiễm với tấn công. Nếu kẻ tấn công điều khiển được ứng dụng, họ có thể sử dụng các quyền mà identity của ứng dụng đang có.

Khi vận hành, hãy:

- Hạn chế quyền của identity bằng vai trò và phạm vi tối thiểu; tránh dùng chung identity giữa ứng dụng có mức độ tin cậy khác nhau.
- Không ghi access token, giá trị secret hoặc dữ liệu nhạy cảm vào logs, trace và exception.
- Bảo vệ máy chủ và pipeline triển khai; kiểm soát ai được phép sửa ứng dụng, gán identity và tạo role assignments.
- Theo dõi lịch sử thay đổi RBAC và identity; rà soát định kỳ những quyền không còn sử dụng.
- Đảm bảo thay đổi hoặc thu hồi quyền có thể cần thời gian để phát huy tác dụng do token đang còn hiệu lực hoặc cache.
- Quản lý user-assigned identity như một resource có owner, quy tắc đặt tên, tags, yêu cầu kiểm kê và kế hoạch ngừng sử dụng.

Khi xóa **system-assigned identity**, workload không thể tiếp tục dùng principal đó để lấy token mới. Hãy kiểm tra và dọn những role assignments không còn cần thiết. Khi xóa **user-assigned identity**, phải kiểm kê tất cả resource đang sử dụng nó và di chuyển chúng sang danh tính thay thế theo kế hoạch; việc xóa sai có thể ảnh hưởng đồng thời nhiều ứng dụng.

Managed identity yêu cầu nền tảng Azure hỗ trợ chức năng này. Workload chạy ngoài môi trường được hỗ trợ cần hình thức xác thực Microsoft Entra ID phù hợp khác, ví dụ workload identity federation trong trường hợp được hỗ trợ. Managed identity cũng không tự động cấp delegated permissions thay mặt người dùng cuối.

## 12. Bài tập và câu hỏi tự kiểm tra

Một công ty có hai thành phần:

- `orders-api` trên App Service, cần đọc một secret trong Key Vault.
- `orders-worker` trên Azure Functions, cần đọc blob trong Storage; công ty dự kiến thường xuyên thay thế host của worker nhưng muốn giữ nguyên principal truy cập dữ liệu.

Hãy thiết kế cách cấp danh tính và quyền:

1. Chọn system-assigned hoặc user-assigned cho từng workload và giải thích theo vòng đời.
2. Nêu ID dùng khi gán identity cho host, ID dùng khi cấp role, ID dùng khi chọn identity trong SDK.
3. Đề xuất vai trò và phạm vi quyền của mỗi workload.
4. Mô tả các bước kiểm tra sau triển khai, gồm nhận token, gọi dịch vụ đích và kiểm tra 403.
5. Nêu hậu quả khi xóa host sử dụng system-assigned identity hoặc xóa user-assigned identity đang dùng chung.

**Hướng giải tham khảo:** `orders-api` có thể dùng system-assigned identity và role `Key Vault Secrets User` ở vault cần đọc. `orders-worker` có thể dùng user-assigned identity để duy trì principal khi thay host; cấp `Storage Blob Data Reader` ở phạm vi Storage/Container phù hợp. Hai workload không cần chia sẻ quyền của nhau.

Tự trả lời:

- User-assigned identity có phải tài khoản của một nhân viên không?
- Vì sao lấy access token thành công vẫn có thể bị `403`?
- Khi thay thế App Service, điều gì xảy ra với system-assigned identity?
- Vì sao phải chỉ định Client ID khi có nhiều user-assigned identities?
- Khi nào nên tách user-assigned identities dù nhiều ứng dụng dùng cùng một Key Vault?

Các đáp án cốt lõi lần lượt là: identity dành cho workload; phân quyền dịch vụ đích vẫn cần thiết; principal của host mới có thể khác; SDK phải chọn đúng danh tính; và tách khi các ứng dụng có tập quyền, chủ sở hữu hoặc mức độ tin cậy khác nhau.

## 13. Checklist trước khi dùng trong production

- [ ] Host Azure hỗ trợ loại managed identity đã chọn.
- [ ] Đã chọn identity theo vòng đời resource và yêu cầu tái sử dụng.
- [ ] Đã phân biệt `principalId`, `clientId` và Azure Resource ID.
- [ ] Đã gán đúng role và scope trên dịch vụ đích.
- [ ] Đã phân biệt quyền control plane và data plane.
- [ ] Đã kiểm tra mô hình quyền của Key Vault hoặc dịch vụ tương ứng.
- [ ] Đã thử kết nối mạng, firewall, DNS và private endpoint khi áp dụng.
- [ ] Đã dùng Azure Identity SDK, không nhúng client secret của managed identity.
- [ ] Đã kiểm tra identity thực sự được chọn ở từng môi trường.
- [ ] Đã có quy trình quản lý role assignments, thay host, tháo gán và xóa identity.

## Kết luận

Managed identity giúp workload trên Azure xác thực với dịch vụ hỗ trợ Microsoft Entra ID mà không phải tự duy trì client secret của danh tính đó. **System-assigned** phù hợp khi danh tính có vòng đời gắn với một resource; **user-assigned** phù hợp khi danh tính cần tồn tại độc lập hoặc được sử dụng lại có chủ đích.

Lựa chọn loại identity chỉ là bước đầu. Một ứng dụng Azure an toàn còn cần đúng quyền data plane, scope RBAC phù hợp, cấu hình mạng, giám sát và quy trình thay đổi. Khi từng identity có mục đích và chủ sở hữu rõ ràng, hệ thống dễ kiểm soát truy cập và vận hành hơn.
