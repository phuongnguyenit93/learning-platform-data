# Subscription, resource group, tenant và endpoint dịch vụ trên Azure

Khi tích hợp Spring Boot với Azure, lập trình viên thường gặp các giá trị **tenant ID**, **subscription ID**, **resource group**, **resource ID**, **resource name** và **endpoint**. Chúng cùng mô tả một hệ thống Azure nhưng trả lời những câu hỏi khác nhau. Nhầm lẫn giữa chúng có thể khiến ứng dụng gọi sai tài nguyên, lấy token từ sai tenant, thiếu quyền dữ liệu hoặc không kết nối được dù thông tin đăng nhập hợp lệ.

Bài thuộc chương **Nền tảng Azure**, trong module **SPRING_CLOUD_PROVIDER_INTEGRATION**: thực hành tích hợp Spring Boot với dịch vụ managed của AWS, Azure và Google Cloud qua các thư viện Spring Cloud tương ứng. Những khái niệm dưới đây làm nền cho cấu hình danh tính và quyền, truy cập storage, messaging, dữ liệu, bảo vệ secret, kiểm thử tích hợp và đánh giá khác biệt giữa các cloud provider.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt **Microsoft Entra tenant**, **Azure subscription**, **resource group**, **resource** và **service endpoint**.
2. Đọc và phân tích **Azure resource ID**; hiểu mối liên hệ giữa subscription, resource group và tài nguyên.
3. Giải thích vì sao gọi Azure SDK data plane thường cần **endpoint + credential + quyền**, còn tạo/quản lý tài nguyên cần thêm **management scope**.
4. Cấu hình một ứng dụng Spring Boot dùng Spring Cloud Azure/Azure SDK để kết nối Blob Storage đúng account và đúng danh tính.
5. Chẩn đoán lỗi sai subscription, sai tenant, sai endpoint, thiếu RBAC và cấu hình Private Endpoint/DNS.
6. So sánh mô hình tổ chức tài nguyên Azure với các khái niệm tương ứng trong AWS và Google Cloud.

## 2. Bức tranh tổng thể: mỗi thành phần chịu trách nhiệm gì?

| Khái niệm | Trả lời câu hỏi | Ví dụ minh họa | Không phải là |
| --- | --- | --- | --- |
| **Tenant** (Microsoft Entra ID) | Danh tính người dùng/workload thuộc hệ thống định danh nào? | Tenant ID dạng GUID | Địa chỉ Blob hoặc nhóm tài nguyên |
| **Subscription** | Tài nguyên được quản lý và tính chi phí trong đơn vị Azure nào? | Subscription ID dạng GUID | Tài khoản đăng nhập ứng dụng |
| **Resource group** | Những tài nguyên nào được tổ chức và quản lý cùng một vòng đời/phạm vi? | `rg-orders-prod` | Một mạng riêng hay một vùng triển khai đồng nhất |
| **Resource** | Đang sử dụng thực thể Azure cụ thể nào? | Storage account `stordersprod01` | Một SDK/client bên trong Java |
| **Endpoint** | Client gửi request đến host/URL nào? | `https://stordersprod01.blob.core.windows.net` | Azure resource ID hoặc thông tin cấp quyền |
| **Principal và role assignment** | Ai được phép thao tác gì trên phạm vi tài nguyên nào? | Managed identity có role ghi Blob | Tự động được suy ra từ một URL hợp lệ |

**Một cách ghi nhớ:** tenant và principal liên quan **danh tính**; subscription/resource group/resource liên quan **tổ chức, quản trị và phạm vi quyền**; endpoint liên quan **đích giao tiếp qua mạng**. Những trục này kết nối với nhau nhưng không hoán đổi được.

### Sơ đồ quan hệ

~~~mermaid
flowchart TD
    T["Microsoft Entra tenant A\nChứa danh tính người dùng / ứng dụng"] --> S1["Subscription S1"]
    T --> S2["Subscription S2"]
    S1 --> RG1["Resource group rg-orders-prod"]
    S1 --> RG2["Resource group rg-network-prod"]
    S2 --> RG3["Resource group rg-data-shared"]
    RG1 --> APP["App Service hoặc AKS workload"]
    RG3 --> ST["Storage account"]
    RG3 --> SB["Service Bus namespace"]
    APP -. "HTTPS đến endpoint + token + RBAC" .-> ST
    APP -. "AMQP/HTTPS + token + RBAC" .-> SB
~~~

Mũi tên từ tenant tới subscription biểu thị **quan hệ quản trị/danh tính** trong tình huống thông thường, không có nghĩa tất cả resource trong subscription đều tự động cho mọi principal trong tenant truy cập. Các mũi tên nét đứt biểu thị **kết nối data plane**: ứng dụng có thể truy cập tài nguyên ở **subscription khác** khi thỏa mãn điều kiện danh tính, quyền và mạng.

## 3. Tenant: ranh giới danh tính của Microsoft Entra ID

**Microsoft Entra ID** (trước đây là Azure Active Directory) là hệ thống quản lý danh tính và truy cập. Một **tenant** là một instance/đơn vị thư mục Entra của tổ chức. Tenant chứa các thực thể như người dùng, nhóm, ứng dụng đã đăng ký và service principal; managed identity cũng có biểu diễn principal trong hệ thống danh tính.

Các định danh thường gặp:

| Tên | Ý nghĩa | Dùng ở đâu |
| --- | --- | --- |
| **Tenant ID** / directory ID | Định danh thư mục Entra, thường là GUID | Xác định tổ chức phát hành token hoặc cấu hình authority |
| **Application (client) ID** | Định danh một ứng dụng đã đăng ký hoặc client identity | Lựa chọn ứng dụng/managed identity tương ứng trong flow xác thực |
| **Object ID / principal ID** | Định danh đối tượng cụ thể trong một tenant | Role assignment và tra cứu principal |
| **Subscription ID** | Định danh subscription Azure Resource Manager | Quản lý tài nguyên, phân quyền theo scope, billing |

**Client ID khác object/principal ID**. Với user-assigned managed identity, client ID có thể dùng để chọn identity khi lấy token, còn principal ID thường dùng để xác định đối tượng được cấp role. Không sao chép nhầm hai giá trị khi cấu hình.

### Một tenant có thể có nhiều subscription

Ví dụ, tổ chức có tenant `tenant-company` và hai subscription `sub-dev`, `sub-prod`. Người dùng đăng nhập cùng tenant nhưng chỉ được xem tài nguyên ở `sub-dev` nếu role assignment của họ không bao phủ `sub-prod`. **Đăng nhập vào tenant không đồng nghĩa được phép truy cập tất cả subscription thuộc tenant đó**.

Một Azure subscription thường gắn với **một Microsoft Entra directory tại một thời điểm**. Các kịch bản truy cập nhiều tổ chức có thể dùng B2B guest, multi-tenant application hoặc mô hình ủy quyền phù hợp; không nên suy luận rằng một managed identity trong tenant A tự động có quyền tại tenant B.

### Xác thực và ủy quyền là hai bước khác nhau

- **Authentication:** Entra hoặc một nguồn credential phù hợp xác định caller và phát token cho dịch vụ/đối tượng nhận phù hợp.
- **Authorization:** dịch vụ Azure kiểm tra principal có quyền với thao tác và tài nguyên đích không; tùy dịch vụ có thể là Azure RBAC, data-plane RBAC riêng hoặc cơ chế policy/access control.
- **Network admission:** firewall, private endpoint, network rule và DNS có thể vẫn ngăn kết nối dù token và role hợp lệ.

Ví dụ: ứng dụng lấy token thành công từ managed identity nhưng upload lên Blob Storage bị **403**. Nguyên nhân có thể là thiếu role **Storage Blob Data Contributor** ở đúng scope; cũng cần kiểm tra network policy và phản hồi chi tiết của dịch vụ. Thay tenant ID một cách ngẫu nhiên không giải quyết thiếu quyền dữ liệu.

## 4. Subscription: đơn vị quản trị, quota và chi phí

**Azure subscription** là phạm vi quản lý tài nguyên qua Azure Resource Manager (ARM). Mỗi subscription có **subscription ID**; bên trong có resource groups và resources. Các vấn đề thường gắn với subscription bao gồm:

- **Billing và cost tracking:** tài nguyên phát sinh chi phí được ghi nhận theo cấu trúc tài khoản thanh toán/subscription liên quan.
- **Governance:** Azure Policy, resource locks, role assignments và một số giới hạn/quota.
- **Triển khai tài nguyên:** ARM thao tác với resource ID chứa subscription ID; IaC cần chọn subscription đích.
- **Môi trường:** tổ chức thường tách dev/test/prod hoặc nhóm sản phẩm ra các subscription để quản trị độc lập hơn.

Subscription **không phải** DNS namespace cho mọi dịch vụ. Hai storage account có thể nằm ở hai subscription nhưng cùng dùng đuôi DNS Azure Blob; bản thân tên và endpoint của storage account xác định đích kết nối dữ liệu.

### Management group và phân cấp phạm vi

Một tổ chức có thể quản lý nhiều subscription bằng **Azure management groups**. Vai trò, chính sách và kiểm soát quản trị có thể được áp dụng hoặc kế thừa theo phân cấp:

~~~text
Tenant / tổ chức
└── Management group(s) (nếu cấu hình)
    └── Subscription
        └── Resource group
            └── Resource
~~~

**Role assignment scope** thường chọn ở mức management group, subscription, resource group hoặc resource, tùy quyền và loại dịch vụ. Cấp role ở phạm vi rộng có thể áp dụng quyền cho nhiều resource con; nguyên tắc **least privilege** thường ưu tiên scope nhỏ nhất đáp ứng nhu cầu. Không xem subscription là một “mạng” hay một “vùng địa lý”: tài nguyên trong cùng subscription có thể nằm ở nhiều region và nhiều mạng khác nhau.

### Khi nào ứng dụng cần subscription ID?

- Khi sử dụng **Azure Resource Manager SDK/REST** để tạo, liệt kê, cập nhật hoặc xóa Azure resources theo subscription/resource group.
- Khi triển khai ARM/Bicep/Terraform hoặc tự động hóa hoạt động quản trị.
- Khi xác định scope RBAC, Azure Policy, tài nguyên theo resource ID và thông tin chi phí.

Ngược lại, đối với phần lớn lệnh **Blob data plane** như upload một blob bằng `BlobClient`, SDK cần endpoint account, credential và quyền ghi thích hợp. **Subscription ID không nhất thiết phải xuất hiện trong đoạn code upload**. Danh tính vẫn có thể truy cập account ở subscription khác nếu có quyền và mạng hợp lệ.

## 5. Resource group: đơn vị tổ chức và vòng đời tài nguyên

Một **resource group (RG)** là container logic thuộc **một subscription**. Mỗi resource ARM thông thường thuộc một resource group tại một thời điểm; mỗi resource group chứa các resource có thể khác region và khác loại.

Resource group giúp:

1. **Triển khai theo ứng dụng/hệ thống** bằng ARM, Bicep, Terraform hoặc pipeline.
2. **Phân quyền** ở phạm vi RG khi nhiều resource có cùng người vận hành.
3. **Áp policy, lock và gắn tag** cho hoạt động quản trị theo mô hình được tổ chức chọn.
4. **Quản lý vòng đời:** xóa RG có thể xóa các tài nguyên bên trong, do đó yêu cầu kiểm soát thay đổi nghiêm ngặt.

Ví dụ:

| Subscription | Resource group | Resource | Mục đích |
| --- | --- | --- | --- |
| `sub-app-prod` | `rg-orders-app-prod` | App Service hoặc AKS | Chạy dịch vụ Spring Boot |
| `sub-data-prod` | `rg-orders-data-prod` | Storage account, Service Bus | Lưu file và xử lý message |
| `sub-network-prod` | `rg-shared-network-prod` | VNet, private DNS zone, Private Endpoint | Mạng dùng chung theo thiết kế |

Đây là cách tổ chức **minh họa**, không phải quy tắc bắt buộc. Tên RG tự nó không tạo kết nối mạng hoặc quyền truy cập; ứng dụng vẫn cần endpoint, credential, RBAC và kết nối thực tế.

### Resource group cũng có location, nhưng có ý nghĩa khác

Khi tạo RG, Azure yêu cầu một **location cho metadata của resource group**. Vị trí này không buộc mọi tài nguyên trong RG phải triển khai cùng region. Mỗi tài nguyên có vị trí và khả năng triển khai riêng; một số resource là global hoặc dùng mô hình region/replication khác.

Ví dụ: RG metadata ở Southeast Asia vẫn có thể chứa một storage account ở East Asia nếu dịch vụ/chính sách cho phép. Vì vậy không suy ra Azure service endpoint hoặc vị trí dữ liệu chỉ từ location của RG.

## 6. Resource ID, resource name và endpoint khác nhau thế nào?

Giả sử ta có:

- Tenant `11111111-1111-1111-1111-111111111111` (ID ví dụ).
- Subscription `22222222-2222-2222-2222-222222222222` (ID ví dụ).
- Resource group `rg-orders-data-prod`.
- Storage account `stordersprod01`.

**Azure resource ID** của storage account có cấu trúc ARM:

~~~text
/subscriptions/22222222-2222-2222-2222-222222222222
/resourceGroups/rg-orders-data-prod
/providers/Microsoft.Storage/storageAccounts/stordersprod01
~~~

Đây là **một resource ID duy nhất**; ví dụ được xuống dòng để dễ đọc. Khi đi vào cấu hình API hoặc CLI, các đoạn phải nối liền trên một dòng:

~~~text
/subscriptions/22222222-2222-2222-2222-222222222222/resourceGroups/rg-orders-data-prod/providers/Microsoft.Storage/storageAccounts/stordersprod01
~~~

Còn **data endpoint** Blob Storage thường là:

~~~text
https://stordersprod01.blob.core.windows.net
~~~

| Thành phần | Hình dạng | Dùng để |
| --- | --- | --- |
| **Resource ID (ARM)** | `/subscriptions/.../resourceGroups/.../providers/...` | Xác định chính xác một tài nguyên trong Azure Resource Manager, IAM, deployment |
| **Resource name** | `stordersprod01` | Đặt tên tài nguyên; với một số dịch vụ được dùng trong DNS |
| **Service/data endpoint** | `https://stordersprod01.blob.core.windows.net` | Gửi request dữ liệu Blob từ Azure SDK/HTTP |
| **Management endpoint** | `https://management.azure.com` (Azure public cloud) | Gửi ARM REST API để tạo/cập nhật/liệt kê tài nguyên |
| **Identity authority** | Ví dụ `https://login.microsoftonline.com/{tenantId}` | Lấy token theo tenant và flow xác thực được hỗ trợ |

**Không** truyền resource ID ARM vào tham số endpoint của `BlobServiceClientBuilder`. Tương tự, không dùng endpoint Blob làm subscription ID. Nếu cần quản lý storage account, sử dụng Azure Resource Manager/ARM SDK với subscription, resource group và resource ID; nếu cần upload blob, sử dụng Azure Storage Blob SDK với data endpoint.

### Phạm vi duy nhất của tên tài nguyên

Quy tắc đặt tên **khác nhau tùy dịch vụ**: một số tên phải duy nhất toàn cục theo DNS (như tên storage account trong Azure public cloud); những loại khác có thể chỉ cần duy nhất trong resource group, subscription hoặc parent resource. Không mặc định mọi resource đều có cùng quy tắc tên hay cùng mẫu endpoint.

## 7. Endpoint phổ biến khi tích hợp Spring Boot với Azure

Bảng sau mô tả **Azure public cloud** với endpoint thường dùng. National/sovereign clouds có suffix và authority khác; dịch vụ, vùng và cấu hình mạng cũng có thể thay đổi endpoint thực tế. Luôn lấy endpoint đúng từ trang thuộc tính dịch vụ hoặc tài liệu của cloud environment hiện dùng.

| Dịch vụ managed | Endpoint/namespace tiêu biểu | Azure SDK / tích hợp Spring thường gặp | Chú ý |
| --- | --- | --- | --- |
| **Blob Storage** | `https://{account}.blob.core.windows.net` | Azure Storage Blob SDK; Spring Cloud Azure Blob starter | Account name khác container name; blob path tiếp tục sau host |
| **Service Bus** | `{namespace}.servicebus.windows.net` | Azure Service Bus SDK; Spring Cloud Azure Service Bus starter | Queue/topic là entity nằm trong namespace, không phải phần hostname bắt buộc |
| **Event Hubs** | `{namespace}.servicebus.windows.net` | Azure Event Hubs SDK; Spring Cloud Azure Event Hubs starter | Endpoint namespace có thể cùng dạng suffix với Service Bus nhưng protocol/semantics khác |
| **Key Vault Secrets** | `https://{vault}.vault.azure.net/` | Azure Key Vault Secrets SDK; Spring Cloud Azure Key Vault starter | Cần quyền đọc secret phù hợp; không suy ra Keys/Certificates là cùng API |
| **Azure App Configuration** | `https://{store}.azconfig.io` | Azure App Configuration SDK; Spring Cloud Azure App Configuration starter | Store endpoint khác Key Vault endpoint |
| **Azure Cosmos DB (NoSQL)** | `https://{account}.documents.azure.com:443/` | Azure Cosmos SDK; Spring Data Cosmos | Endpoint có thể khác theo API/môi trường; cần đúng endpoint do account cung cấp |
| **Azure Resource Manager** | `https://management.azure.com` | ARM REST / Azure Resource Manager SDK | Management plane; thường cần subscription ID, RG và resource ID |
| **Microsoft Entra authority** | `https://login.microsoftonline.com/{tenantId}` | Azure Identity SDK | Authority xác thực; không phải data endpoint của Blob hay Service Bus |

**Chú ý TLS và giao thức:** một số SDK nhận **fully qualified namespace** (ví dụ `ns.servicebus.windows.net`) thay vì URL bắt đầu `https://`; dịch vụ khác yêu cầu URL endpoint đầy đủ. Phải tuân thủ đúng kiểu tham số của SDK.

### Endpoint không luôn chứa subscription/resource group

Host `stordersprod01.blob.core.windows.net` thường không biểu diễn subscription ID hay resource group. Chúng thuộc **lớp quản lý ARM**, trong khi hostname là địa chỉ kết nối data plane. Việc tách biệt này cho phép một ứng dụng truy cập dữ liệu theo endpoint khi đã có quyền, bất kể cách đội hạ tầng tổ chức subscription/RG.

Không suy đoán endpoint chỉ từ một resource ID nếu dịch vụ có endpoint tùy chỉnh, nhiều region, cloud riêng hoặc private networking. Nên đọc **endpoint được phát hành bởi chính tài nguyên**.

## 8. Data plane, management plane và yêu cầu quyền

Một ứng dụng có thể dùng **hai nhóm API** rất khác nhau:

~~~mermaid
flowchart LR
    A["Spring Boot application"] --> B["Azure Identity\nTokenCredential"]
    A --> C["Azure SDK data client"]
    A --> D["ARM / management client"]
    B --> C
    B --> D
    C --> E["Service endpoint\nBlob / Service Bus / Key Vault"]
    D --> F["management.azure.com\nSubscription + RG + Resource"]
~~~

| Tác vụ | Plane | Đầu vào thường cần | Quyền ví dụ |
| --- | --- | --- | --- |
| Upload blob vào container đã có | **Data plane** | Blob endpoint, container/blob name, credential | **Storage Blob Data Contributor** ở scope đủ hẹp |
| Nhận message từ Service Bus queue | **Data plane** | Namespace, queue name, credential | **Azure Service Bus Data Receiver** |
| Đọc secret từ Key Vault | **Data plane** | Vault URL, secret name, credential | **Key Vault Secrets User** khi vault dùng Azure RBAC permission model |
| Tạo một storage account mới | **Management plane** | Subscription, resource group, location, cấu hình tài nguyên | Role quản lý phù hợp, ví dụ Contributor ở scope cần thiết |
| Gán role cho một principal | **Management plane / IAM** | Scope resource ID, principal ID, role definition | Quyền tạo role assignment, thường thuộc role quản trị quyền truy cập phù hợp |

Role **Reader/Contributor** trên ARM management plane không nhất thiết cấp quyền đọc/ghi dữ liệu trong Blob, Service Bus hay Key Vault. Một số dịch vụ có cơ chế data-plane authorization riêng (ví dụ Cosmos DB for NoSQL). Cần kiểm tra mô hình cấp quyền **theo từng dịch vụ**, thay vì coi mọi Azure role là tương đương.

Có ba câu hỏi độc lập trước mỗi request:

1. **Đúng đích chưa?** Endpoint, resource/account/namespace, container hoặc queue name.
2. **Đúng danh tính chưa?** Credential thực sự được chọn, tenant phát token, audience của token.
3. **Đủ quyền và đường mạng chưa?** RBAC/policy, firewall, private DNS, TLS, route.

## 9. Thực hành: xem ngữ cảnh Azure CLI trước khi tích hợp

Với tài khoản được cấp quyền truy cập, các lệnh dưới đây giúp **quan sát** tenant/subscription đang chọn. Các giá trị minh họa như `<subscription-id>` phải thay bằng ID thực tế trong môi trường lab.

~~~bash
# Đăng nhập Azure CLI bằng danh tính được phép dùng trong môi trường học.
az login

# Liệt kê các subscription mà Azure CLI thấy.
az account list --output table

# Xem subscription và tenant đang được Azure CLI chọn.
az account show --query "{subscription:id, tenant:tenantId, name:name}" --output json

# Đổi subscription mặc định cho các lệnh Azure CLI tiếp theo.
az account set --subscription "<subscription-id>"

# Kiểm tra lại trước khi tạo/quản lý tài nguyên.
az account show --query "{subscription:id, tenant:tenantId, name:name}" --output json
~~~

Nếu cần đăng nhập trong tenant xác định, có thể dùng `az login --tenant "<tenant-id>"` theo chính sách của tổ chức. Trên môi trường headless cần phương án đăng nhập phi tương tác thích hợp; với workload ứng dụng, ưu tiên managed identity hoặc workload identity.

**Điểm dễ nhầm:** `az account set` thay đổi **subscription mặc định cho các lệnh CLI/ARM dùng ngữ cảnh đó**. Nó không biến một endpoint Blob của account A thành account B, không tự gán RBAC và không bảo đảm mọi SDK client sẽ tự động chuyển đích. SDK client data plane vẫn gọi endpoint đã được cấu hình.

### Xem resource và endpoint đúng mục tiêu

~~~bash
# Xem storage account trong resource group đã chọn.
az storage account show \
  --name "<storage-account-name>" \
  --resource-group "<resource-group-name>" \
  --query "{id:id, location:location, name:name, endpoints:primaryEndpoints}" \
  --output json
~~~

Lệnh này đọc thông tin **management plane**; cần quyền đọc tài nguyên phù hợp. Nếu account nằm ở subscription khác, chọn đúng subscription hoặc dùng tùy chọn `--subscription` nếu lệnh hỗ trợ. Không phụ thuộc vào cách tên resource group gợi ý region; hãy đọc thuộc tính `location` của resource.

## 10. Cấu hình Spring Boot với endpoint và danh tính

### 10.1. Phương án Spring Cloud Azure starter cho Blob Storage

Với ứng dụng Spring Boot đã chọn một phiên bản **Spring Cloud Azure** tương thích và thêm starter **`com.azure.spring:spring-cloud-azure-starter-storage-blob`**, có thể cấu hình account name qua `application.yml`:

~~~yaml
spring:
  cloud:
    azure:
      storage:
        blob:
          account-name: ${AZURE_STORAGE_ACCOUNT}
~~~

Ví dụ đặt biến `AZURE_STORAGE_ACCOUNT=stordersprod01`. Với Azure public cloud và cơ chế cấu hình mặc định phù hợp phiên bản, starter có thể xây dựng client cho storage account đó. Nếu dùng endpoint tùy chỉnh, emulator hoặc cloud environment khác, cần cấu hình endpoint/credential theo **đúng tài liệu của phiên bản Spring Cloud Azure**.

Ứng dụng sử dụng client SDK đã được Spring tự cấu hình:

~~~java
import com.azure.storage.blob.BlobContainerClient;
import com.azure.storage.blob.BlobServiceClient;
import org.springframework.stereotype.Service;

@Service
public class DocumentLocator {

    private final BlobServiceClient blobServiceClient;

    public DocumentLocator(BlobServiceClient blobServiceClient) {
        this.blobServiceClient = blobServiceClient;
    }

    public BlobContainerClient documents() {
        return blobServiceClient.getBlobContainerClient("documents");
    }
}
~~~

Đoạn code chỉ **lấy tham chiếu client tới container**; container `documents` phải được tạo sẵn nếu nghiệp vụ tiếp theo cần thao tác trên nó. **Resource group và subscription ID không xuất hiện** vì tác vụ truy cập Blob data plane không cần dùng trực tiếp chúng để hình thành endpoint.

Thông tin credential nên lấy từ cơ chế được Azure Identity và Spring Cloud Azure hỗ trợ (ví dụ đăng nhập nhà phát triển, workload identity, managed identity). Không commit storage account key, connection string, client secret hoặc SAS token vào `application.yml`.

### 10.2. Phương án Azure SDK trực tiếp

Khi muốn điều khiển endpoint rõ ràng, có thể tạo `BlobServiceClient` từ `DefaultAzureCredential`. Phần dependency là **azure-identity** và **azure-storage-blob**; nên quản lý version nhất quán bằng BOM phù hợp.

~~~java
import com.azure.core.credential.TokenCredential;
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.storage.blob.BlobServiceClient;
import com.azure.storage.blob.BlobServiceClientBuilder;

public final class BlobClientFactory {

    private BlobClientFactory() {}

    public static BlobServiceClient create(String blobEndpoint) {
        TokenCredential credential =
                new DefaultAzureCredentialBuilder().build();

        return new BlobServiceClientBuilder()
                .endpoint(blobEndpoint)
                .credential(credential)
                .buildClient();
    }
}
~~~

Ví dụ gọi:

~~~java
BlobServiceClient client = BlobClientFactory.create(
        "https://stordersprod01.blob.core.windows.net");
~~~

Trong Spring Boot thực tế, hãy khai báo client là bean có vòng đời ứng dụng, lấy endpoint từ cấu hình ngoài ứng dụng và xác thực format URL khi cần. **DefaultAzureCredential** thử các nguồn credential thích hợp với môi trường; danh tính được chọn phải có data-plane permission với **đúng storage account** đó.

Việc tạo `BlobServiceClient` thành công thường mới chỉ xác nhận cấu hình đối tượng client hợp lệ; request thật khi đọc/ghi Blob mới kiểm tra kết nối, token và quyền tại dịch vụ.

### 10.3. Vì sao không đưa subscription ID vào tất cả các client?

Đối với Blob data client, `endpoint + TokenCredential` thường là đủ để xác định đích và danh tính. Nếu cùng một Spring Boot service cần truy cập Blob ở hai subscription:

~~~text
Application principal
├── role ghi ở subscription A / account stordersprod01
│   └── client A → https://stordersprod01.blob.core.windows.net
└── role đọc ở subscription B / account stshareddata02
    └── client B → https://stshareddata02.blob.core.windows.net
~~~

Có thể tạo hai client với hai endpoint khác nhau nhưng cùng một credential, **nếu** principal có quyền tương ứng trên cả hai tài nguyên và network cho phép. Không cần sửa subscription ID ở mỗi lần gọi API dữ liệu; cần cấu hình nhiều client rõ ràng và kiểm soát role theo từng account.

Trường hợp API quản lý resource (tạo storage account, liệt kê RG, gán role) lại phải xác định **subscription/resource group/scope** theo ARM SDK và quyền management plane.

## 11. Endpoint khi dùng Private Link/Private Endpoint

Trong hệ thống production, đội hạ tầng có thể tắt truy cập mạng công khai và dùng **Azure Private Endpoint**. Đây là một giao diện mạng được gán private IP bên trong VNet để truy cập dịch vụ Azure qua đường mạng riêng.

Điểm quan trọng: **Private Endpoint thay đổi đường đi mạng và cách DNS phân giải, không làm thay đổi ý nghĩa tenant, subscription hay RBAC**.

Thông thường ứng dụng vẫn dùng **hostname chuẩn của dịch vụ**, ví dụ:

~~~text
stordersprod01.blob.core.windows.net
~~~

Khi Private Endpoint và DNS được cấu hình đúng, hostname đó có thể phân giải qua alias/vùng `privatelink` tới private IP phù hợp từ môi trường mạng được phép. Không tùy tiện thay hostname chuẩn trong source code bằng IP hoặc một tên `privatelink` tự chế: có thể làm hỏng TLS hostname validation hoặc cách SDK xác định endpoint.

Để kết nối Private Endpoint, cần đồng thời:

- Private Endpoint được tạo cho **đúng dịch vụ/subresource** (ví dụ Blob, không phải một subresource Storage khác).
- VNet và workload có đường mạng đến private IP.
- Private DNS zone và liên kết VNet/forwarder được cấu hình đúng theo kiến trúc.
- Firewall/public network access và route cho phép traffic dự kiến.
- Principal vẫn có quyền data plane cần thiết.

**Triệu chứng chẩn đoán:** developer gọi Blob thành công từ laptop nhưng ứng dụng chạy trong VNet bị timeout; đây thường là hướng điều tra DNS, route, proxy, firewall hoặc Private Endpoint. Ngược lại, kết nối thành công nhưng nhận 403 cần xem cả authorization và chính sách network của dịch vụ. Không suy luận chỉ từ HTTP status mà bỏ qua log/diagnostic của Azure.

## 12. Những lỗi thường gặp và cách xử lý

| Triệu chứng | Phân biệt nguyên nhân | Cách kiểm tra |
| --- | --- | --- |
| Azure CLI tạo resource ở subscription không mong muốn | CLI đang chọn subscription khác | `az account show`, dùng subscription ID rõ ràng trong IaC |
| Nhìn thấy RG nhưng không thấy storage account mong đợi | Sai subscription/RG, lọc sai tên hoặc thiếu quyền đọc | Kiểm tra resource ID thực tế, quyền Reader/ARM và portal |
| SDK dùng account A trong khi cần account B | Sai `account-name` hoặc endpoint được inject | In ra cấu hình endpoint đã chuẩn hóa (không lộ secret), đối chiếu resource properties |
| Không lấy được token hoặc lỗi tenant | Credential chain/authority/tenant hoặc workload identity chưa đúng | Xác định nguồn credential, tenant và app/client ID thực tế |
| Token hợp lệ nhưng upload bị **403** | Thiếu data role, gán scope sai hoặc policy mạng | Kiểm tra **Storage Blob Data Contributor** ở account/container, firewall và response details |
| Key Vault đọc secret bị **403** | Sai vault, sai principal hoặc thiếu quyền secret | Kiểm tra vault URI, RBAC permission model/access policy và role |
| Service Bus kết nối được namespace nhưng gửi thất bại | Sai queue/topic, quyền sender hoặc network | Kiểm tra entity, role **Azure Service Bus Data Sender**, namespace hostname |
| Timeout trong VNet dù endpoint hợp lệ | Private DNS/route/firewall/proxy chưa đúng | Kiểm tra phân giải DNS từ chính workload, private IP và network diagnostics |
| TLS certificate/hostname mismatch | Dùng IP trực tiếp, endpoint tùy chế hoặc proxy sai | Dùng hostname được dịch vụ công bố, xác minh TLS/SNI |
| Tạo client thành công nhưng request thất bại | Client construction chưa chứng minh service reachable | Thử một thao tác ít tác động trên tài nguyên test, ghi correlation ID |

Cần log **tên operation, endpoint hostname, mã trạng thái, Azure request ID/correlation ID và thời gian phản hồi**, đồng thời che thông tin nhạy cảm. **Không ghi access token, secret, connection string, SAS URL hoặc thông tin đăng nhập**. Khi chia sẻ log, bảo đảm tenant/subscription/resource ID không vi phạm quy định bảo mật của tổ chức.

### Một quy trình debug ngắn, có thứ tự

1. **Xác nhận resource đích:** đúng tenant quản trị, subscription, RG, resource ID và tên endpoint.
2. **Xác nhận caller:** runtime đang chạy với principal nào, credential nào được chọn.
3. **Xác nhận quyền:** role/data permission ở đúng account, container, namespace hoặc vault.
4. **Xác nhận mạng:** DNS từ nơi chạy app, cổng/protocol, private endpoint, firewall và proxy.
5. **Xác nhận cấu hình SDK/Spring:** đúng starter/version, property và object client được inject.
6. **Tái hiện bằng thao tác nhỏ trên môi trường test:** đọc/ghi một đối tượng thử, dùng request ID để tra log phía dịch vụ.

## 13. Ví dụ kiến trúc nhiều subscription

Giả sử ứng dụng **Orders API** chạy trong `sub-app-prod`, dữ liệu dùng chung nằm trong `sub-data-prod`; cả hai subscription hiện thuộc cùng Entra tenant.

| Thành phần | Nằm ở đâu | Cấu hình cần thiết |
| --- | --- | --- |
| Spring Boot Orders API | RG `rg-orders-app`, subscription `sub-app-prod` | Managed identity hoặc workload identity |
| Storage account | RG `rg-orders-data`, subscription `sub-data-prod` | Blob endpoint + role Storage Blob Data Contributor cho principal app |
| Service Bus namespace | RG `rg-orders-data`, subscription `sub-data-prod` | Fully qualified namespace + role Data Sender/Receiver theo nghiệp vụ |
| Key Vault | RG `rg-security`, subscription `sub-data-prod` hoặc subscription bảo mật riêng | Vault URL + quyền secret tương ứng |
| Private Endpoint và DNS | Theo mạng của workload | Route và DNS từ app tới các service endpoint |

**Lưu đồ khi Orders API ghi Blob:**

~~~mermaid
sequenceDiagram
    participant A as Orders API
    participant I as Azure Identity / Entra
    participant D as DNS / Network
    participant B as Azure Blob Storage
    A->>I: Lấy token cho Azure Storage
    I-->>A: Access token theo danh tính
    A->>D: Phân giải Blob hostname / kết nối
    D-->>A: Địa chỉ và đường mạng
    A->>B: HTTPS upload + token
    B->>B: Xác minh quyền dữ liệu và chính sách truy cập
    B-->>A: Thành công hoặc mã lỗi chi tiết
~~~

**Subscription của workload không quyết định subscription của data endpoint**. Quyền truy cập được đánh giá theo danh tính, role ở tài nguyên đích, chính sách dịch vụ và đường mạng. Nếu hai subscription ở **khác tenant**, cần thiết kế xác thực liên tenant/ủy quyền cụ thể, không mặc định mô hình này hoạt động nguyên trạng.

## 14. So sánh với AWS và Google Cloud

| Câu hỏi | Azure | AWS | Google Cloud |
| --- | --- | --- | --- |
| Danh tính thuộc hệ thống nào? | Microsoft Entra tenant, principal và managed/workload identity | IAM principal/role trong account và cơ chế federation | Google Cloud IAM principal, service account/workload identity |
| Đơn vị quản trị và billing thường gặp | Azure subscription | AWS account (có thể thuộc AWS Organizations) | Google Cloud project, billing account và organization/folder |
| Nhóm logic của tài nguyên | Resource group | Tags, CloudFormation stack, organizational constructs theo nhu cầu | Project và resource hierarchy; labels, folders theo mục tiêu |
| ID mô tả tài nguyên | ARM resource ID | ARN hoặc ID theo dịch vụ | Fully qualified resource name/ID theo dịch vụ |
| Endpoint truy cập object storage | Azure Blob account endpoint | Amazon S3 endpoint theo region/kiểu truy cập | Cloud Storage endpoint/API |
| Quyền truy cập | Azure RBAC và cơ chế data-plane theo dịch vụ | IAM policies và resource policies theo dịch vụ | IAM bindings và điều kiện truy cập theo dịch vụ |

Sự tương đồng ở đây là **cách đặt câu hỏi về danh tính, tài nguyên, quyền và endpoint**, không phải sự giống hệt mô hình kỹ thuật. Không thể ánh xạ một Azure resource group thành một AWS account hoặc một Google Cloud project theo quan hệ một-một. Khi viết abstraction đa cloud, cần giữ rõ **provider**, **account/subscription/project context**, **resource locator**, **endpoint**, **credential** và **permission model**.

## 15. Bài thực hành

**Bối cảnh:** Spring Boot nhận một tệp và ghi lên Blob container `documents`. Ứng dụng chạy trong subscription A, storage account có thể ở subscription B.

1. Tạo hoặc chọn một storage account thử nghiệm và container `documents`; ghi lại **tenant ID**, **subscription ID**, **resource group**, **resource ID**, **account name**, **Blob endpoint** vào bảng riêng của môi trường lab.
2. Đăng nhập Azure CLI, dùng `az account show` xác nhận subscription khi xem thuộc tính account. Phân biệt giá trị dùng trong CLI với giá trị cần cho SDK data client.
3. Dùng **Spring Cloud Azure Blob starter** với `spring.cloud.azure.storage.blob.account-name`; cấu hình danh tính ngoài ứng dụng và cấp **Storage Blob Data Contributor** đúng scope thử nghiệm.
4. Viết dịch vụ upload một blob có tên duy nhất. Xác nhận request thực sự tới account đích; không suy luận thành công chỉ từ việc Spring context chạy.
5. Cố tình cấu hình account name sai, sau đó đổi quyền từ ghi sang chỉ đọc ở môi trường test và quan sát lỗi. Khôi phục cấu hình phù hợp để hoàn thành lab.
6. Nếu có Private Endpoint trong lab, kiểm tra DNS từ nơi ứng dụng chạy và so sánh host công khai chuẩn với IP đã phân giải trong mạng riêng.
7. Thử truy cập storage ở subscription B (cùng tenant, có quyền được cấp); giải thích tại sao cần **endpoint đúng và role đúng**, dù không đưa subscription B vào đoạn code upload.

### Câu hỏi tự kiểm tra

- Một subscription có thể thuộc nhiều tenant đồng thời không? Một tenant có thể quản lý nhiều subscription không?
- Resource group có bắt buộc chứa các resource cùng một region không?
- Vì sao `/subscriptions/.../resourceGroups/...` không phải URL upload blob?
- Vì sao `az account set` không tự động thay đích của một `BlobServiceClient` đã tạo?
- Role **Contributor** quản lý tài nguyên có chắc cho phép đọc secret hoặc ghi blob không?
- Khi dùng Private Endpoint, vì sao ứng dụng thường vẫn sử dụng hostname dịch vụ chuẩn?
- Nếu Spring Boot nhận 403, ba nhóm nguyên nhân nào phải phân biệt trước khi sửa code?

## 16. Ghi nhớ

- **Tenant** là ranh giới danh tính; **subscription** là phạm vi quản trị/chi phí; **resource group** là nhóm logic/vòng đời; **resource ID** xác định đối tượng ARM; **endpoint** là địa chỉ giao tiếp dịch vụ.
- **Data plane** thường cần đúng endpoint, principal, quyền và đường mạng; **management plane** thường cần subscription/RG/resource ID cùng quyền ARM.
- Resource ở subscription khác vẫn có thể được ứng dụng truy cập nếu cơ chế danh tính, quyền và mạng đáp ứng; không giả định tương tự cho trường hợp khác tenant.
- Trong Spring Boot, chọn starter Spring Cloud Azure phù hợp hoặc Azure SDK trực tiếp, lấy cấu hình từ môi trường và tránh lưu secret trong mã nguồn.
- Khi lỗi, kiểm tra lần lượt **đích tài nguyên → danh tính → RBAC/policy → DNS/network → cấu hình SDK**, dùng request ID để hỗ trợ chẩn đoán.

## Tài liệu tham khảo

- [Azure Resource Manager – Tổng quan](https://learn.microsoft.com/azure/azure-resource-manager/management/overview)
- [Azure role-based access control – Tổng quan](https://learn.microsoft.com/azure/role-based-access-control/overview)
- [Azure private endpoint DNS configuration](https://learn.microsoft.com/azure/private-link/private-endpoint-dns)
- [Spring Cloud Azure documentation](https://learn.microsoft.com/azure/developer/java/spring-framework/)
- [Azure Identity client library for Java](https://learn.microsoft.com/java/api/overview/azure/identity-readme)
