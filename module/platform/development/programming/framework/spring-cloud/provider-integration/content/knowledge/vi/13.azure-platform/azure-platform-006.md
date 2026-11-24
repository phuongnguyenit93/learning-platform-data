# Phân biệt quyền quản lý tài nguyên và quyền truy cập dữ liệu bằng Azure RBAC

Một ứng dụng Spring Boot có thể tạo được Azure Storage Account nhưng lại nhận lỗi **403** khi upload Blob. Ngược lại, một service chỉ có quyền ghi Blob có thể upload dữ liệu thành công nhưng không được phép cập nhật cấu hình Storage Account. Hai trường hợp này không mâu thuẫn: **quyền quản lý tài nguyên** và **quyền truy cập dữ liệu** phục vụ các nhóm thao tác khác nhau.

Trong chương **Nền tảng Azure** của module **SPRING_CLOUD_PROVIDER_INTEGRATION**, người học tích hợp Spring Boot với dịch vụ managed trên AWS, Azure và Google Cloud thông qua các thư viện Spring Cloud tương ứng. Bài này đi sâu vào Azure RBAC, cách xác định quyền khi truy cập storage, messaging, cơ sở dữ liệu và secret, cũng như cách kiểm thử danh tính và phân quyền trong ứng dụng Java.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt **management plane** và **data plane** theo loại thao tác, endpoint và cơ chế ủy quyền.
2. Đọc **role definition** với các trường **Actions**, **NotActions**, **DataActions**, **NotDataActions** và hiểu giới hạn của mỗi trường.
3. Giải thích **role assignment = principal + role + scope**, tính kế thừa quyền và nguyên tắc ít quyền nhất.
4. Nhận diện role phù hợp cho Blob Storage, Service Bus, Event Hubs, Key Vault, App Configuration và cơ chế đặc thù của Cosmos DB.
5. Cấp và kiểm tra quyền của managed identity cho một Spring Boot service bằng Azure CLI trong môi trường lab.
6. Chẩn đoán việc **đăng nhập thành công nhưng bị từ chối truy cập dữ liệu**, phân biệt lỗi RBAC với sai endpoint, token và network.
7. Thiết kế test dương tính/âm tính và so sánh phân quyền Azure với AWS IAM và Google Cloud IAM.

## 2. Management plane và data plane là gì?

**Management plane** là mặt phẳng quản lý tài nguyên Azure, thường đi qua **Azure Resource Manager (ARM)** để tạo, cấu hình, liệt kê hoặc xóa resource. **Data plane** là mặt phẳng thao tác với dữ liệu hoặc nghiệp vụ mà dịch vụ đó cung cấp.

| Tình huống | Management plane | Data plane |
| --- | --- | --- |
| Azure Blob Storage | Tạo Storage Account, cấu hình replication hoặc network rule | Upload, download, liệt kê và xóa Blob |
| Azure Service Bus | Tạo namespace, queue, topic và cấu hình thực thể | Gửi hoặc nhận message |
| Azure Key Vault | Tạo vault, cấu hình network/permission model | Đọc hoặc cập nhật giá trị secret |
| Azure Event Hubs | Tạo namespace, event hub và cấu hình hạ tầng | Publish và consume event |
| Azure Cosmos DB | Tạo account, database/container qua management API tương ứng | Đọc, ghi, truy vấn document theo API dữ liệu |
| Azure App Configuration | Tạo store và cấu hình tài nguyên | Đọc/ghi key-value hoặc feature flag |

### Hai đường đi từ ứng dụng Spring Boot

~~~mermaid
flowchart TD
    A[Spring Boot application] --> B{Ứng dụng cần làm gì?}
    B -->|Tạo hoặc quản lý tài nguyên| C[ARM / Management SDK]
    B -->|Thao tác dữ liệu| D[Service Data SDK]
    C --> E[management.azure.com]
    D --> F[Blob / Service Bus / Key Vault endpoint]
    E --> G[Quyền management plane]
    F --> H[Quyền data plane hoặc access model dịch vụ]
    I[Microsoft Entra principal và TokenCredential] --> C
    I --> D
~~~

Ví dụ: lệnh ARM gửi tới **https://management.azure.com** dùng resource ID chứa subscription và resource group. Còn **BlobServiceClient** gửi request tới endpoint dạng **https://{account}.blob.core.windows.net** để upload dữ liệu. Chúng có thể dùng cùng một Microsoft Entra principal nhưng cần **những quyền tương ứng với từng thao tác**.

Không phải mọi dịch vụ đều tách hai plane một cách giống nhau. Một số thao tác quản trị container hoặc dữ liệu có thể có cả API tương ứng ở management plane và data plane. Khi xác minh quyền, phải dựa vào **operation và cơ chế authorization thực tế** của API đang gọi.

## 3. Azure RBAC giải quyết bài toán gì?

**Azure role-based access control (Azure RBAC)** cho phép gán một role xác định tập quyền cho một principal trong một scope cụ thể.

~~~text
Role assignment
    = Security principal
    + Role definition
    + Scope
    + (điều kiện áp dụng, nếu có và được hỗ trợ)
~~~

Ba thành phần cốt lõi:

| Thành phần | Ví dụ | Điều cần kiểm tra |
| --- | --- | --- |
| **Principal** | User, group, service principal hoặc managed identity | **Object/principal ID** thực tế trong tenant |
| **Role definition** | Reader, Contributor, Storage Blob Data Contributor | Những Actions/DataActions mà role cho phép |
| **Scope** | Subscription, resource group, storage account hoặc phạm vi con được hỗ trợ | Role có bao phủ **resource đích** không |

Một ứng dụng Spring Boot chạy trên App Service có **system-assigned managed identity** được Azure quản lý. Nếu identity đó được gán role **Storage Blob Data Contributor** trên storage account **stordersprod01**, nó có thể thực hiện các thao tác Blob được role cho phép tại scope phù hợp. Danh tính của người triển khai ứng dụng không tự động trở thành danh tính của ứng dụng.

### Role assignment không đồng nghĩa authentication

Ứng dụng trước hết cần **credential hợp lệ** để lấy access token. Token xác định principal, còn dịch vụ/ARM đánh giá quyền của principal trên scope tài nguyên. Cấp role vào principal A nhưng runtime thực tế dùng principal B thì B vẫn bị từ chối.

**Azure subscription ID**, **client ID** và **principal ID** có ý nghĩa khác nhau. Dùng **principal ID** khi xác định đối tượng cần phân quyền; dùng **client ID** khi SDK cần chọn một user-assigned managed identity; dùng **subscription ID** khi quản lý scope ARM.

## 4. Đọc role definition: Actions khác DataActions

Một Azure role definition thường mô tả quyền qua các trường dưới đây:

| Thuộc tính | Ý nghĩa khái quát | Ví dụ thao tác |
| --- | --- | --- |
| **Actions** | Thao tác **management plane** được cho phép | Đọc cấu hình storage account, tạo/cập nhật resource |
| **NotActions** | Loại trừ một số management operations khỏi **chính role đó** | Không cho thao tác quản lý được liệt kê trong role |
| **DataActions** | Thao tác **data plane** được cho phép theo cơ chế Azure RBAC của dịch vụ | Đọc hoặc ghi Blob |
| **NotDataActions** | Loại trừ một số data operations khỏi **chính role đó** | Loại trừ một loại thao tác dữ liệu |
| **AssignableScopes** | Phạm vi cho phép tạo role assignment đối với role definition này | Subscription, resource group hoặc phạm vi được hỗ trợ |

**NotActions/NotDataActions không phải một lệnh deny tuyệt đối.** Nếu principal nhận nhiều role assignment, một role khác có thể cấp lại thao tác mà role đầu tiên loại trừ. Để xác định quyền hiệu lực phải xét các assignment và scope liên quan, cùng điều kiện role assignment, deny assignments và các kiểm soát dịch vụ/hạ tầng thích hợp.

### Tại sao Contributor chưa chắc được ghi Blob qua Microsoft Entra token?

Role **Contributor** chủ yếu cấp khả năng quản lý Azure resources và thường không tự cấp **DataActions ghi Blob**. Một principal có Contributor trên Storage Account có thể được phép sửa cấu hình tài nguyên nhưng request data plane dùng Microsoft Entra token vẫn bị từ chối nếu thiếu role dữ liệu.

Tương tự:

- **Reader** có thể xem thông tin cấu hình tài nguyên ARM, nhưng không vì thế mà đọc được nội dung Blob private hoặc secret.
- **Storage Blob Data Reader** cho quyền đọc dữ liệu Blob phù hợp với scope; không cho phép chỉnh cấu hình network/firewall của Storage Account.
- **Storage Blob Data Contributor** cho quyền dữ liệu cần thiết để đọc/ghi/xóa Blob theo role; không đồng nghĩa quyền tạo Storage Account mới.
- **Owner** có quyền quản lý quyền truy cập ở scope được cấp, nhưng không nên coi mọi data-plane token call tự được cấp **DataActions** tương ứng.

### Ngoại lệ bảo mật cần hiểu: gián tiếp lấy dữ liệu từ management plane

Một số role quản lý tài nguyên có thể được phép thực hiện thao tác như **listKeys** đối với dịch vụ hỗ trợ access key. Nếu tài nguyên cho phép xác thực bằng Shared Key, việc lấy được key có thể tạo ra **đường truy cập dữ liệu gián tiếp** dù role không trực tiếp có DataActions tương ứng.

Ví dụ với Azure Storage, cần đánh giá cẩn thận ai có quyền lấy account key, có nên vô hiệu hóa **Shared Key authorization** theo kiến trúc dịch vụ hay không và những ứng dụng còn phụ thuộc key. Vì vậy **“Contributor không cấp Blob DataActions” không có nghĩa role quản lý luôn vô hại đối với dữ liệu**.

Thực hành bảo mật tốt là dùng Microsoft Entra token, role dữ liệu tối thiểu và hạn chế quyền lấy key/secret, thay vì coi access key là lối tắt để vượt qua lỗi 403.

## 5. Scope và tính kế thừa của role assignment

Azure RBAC có hệ phân cấp scope quản lý:

~~~text
Management group
└── Subscription
    └── Resource group
        └── Resource
            └── Scope con được dịch vụ hỗ trợ (nếu có)
~~~

Khi được gán role ở scope cha, các tài nguyên con trong phạm vi kế thừa thường nhận quyền tương ứng. Gán ở scope nhỏ hơn chỉ bao phủ phần đó; ví dụ role ghi Blob có thể được giới hạn tới storage account hoặc Blob container khi nền tảng và thao tác hỗ trợ scope đó.

| Scope ví dụ | Tác động điển hình | Đánh giá cho app chỉ ghi Blob |
| --- | --- | --- |
| Cả subscription | Có thể bao phủ rất nhiều resource hiện tại/tương lai | Quá rộng cho đa số ứng dụng |
| Resource group | Bao phủ các resource con trong RG | Chỉ phù hợp khi có lý do rõ ràng |
| Storage account | Bao phủ dữ liệu Blob trong account theo role | Thường là điểm bắt đầu hợp lý |
| Blob container | Giới hạn phạm vi data plane vào container được hỗ trợ | Tốt hơn nếu ứng dụng chỉ dùng một container |

**Không gộp nhầm scope với network.** Cùng một resource group không đồng nghĩa cùng VNet/region. Một App Service ở subscription A có thể truy cập Storage Account ở subscription B nếu identity có quyền trên account đích, network cho phép và thiết lập tenant/trust phù hợp.

### Cách tính quyền hiệu lực

Ở mức khái niệm, cần xét:

1. Principal thực sự đang dùng và các group membership có liên quan.
2. Các role assignment trực tiếp và kế thừa từ scope cha.
3. Role definition: Actions, DataActions và các exclusions.
4. **Role assignment conditions** (nếu có), ví dụ một số điều kiện Azure ABAC cho Blob Storage.
5. **Deny assignments**, trạng thái kích hoạt quyền theo cơ chế tổ chức như PIM, và policy khác.
6. Cơ chế ủy quyền riêng của dịch vụ cùng các giới hạn network/endpoint.

Azure Policy, lock, firewall và các cơ chế governance khác có thể hạn chế thao tác nhưng **không nên xem chúng thay thế role authorization**. Chẳng hạn resource lock chủ yếu tác động đến management operations và không phải là công cụ phổ quát bảo vệ mọi data-plane action.

## 6. Các role tích hợp sẵn nên nhận diện

Role cần chọn theo **nghiệp vụ**, không theo tên đội phát triển. Bảng sau minh họa các role thông dụng; quyền chính xác có thể thay đổi theo bản role definition và permission model của dịch vụ.

| Dịch vụ / nhu cầu | Role thường phù hợp | Điều cần lưu ý |
| --- | --- | --- |
| Xem resource ARM | **Reader** | Chủ yếu đọc metadata/quản lý; không phải quyền đọc dữ liệu |
| Quản lý tài nguyên thông thường | **Contributor** | Không tự cấp quyền tạo role assignment; đánh giá các management actions nhạy cảm |
| Quản lý role assignment | **Role Based Access Control Administrator**, **User Access Administrator** hoặc quyền phù hợp | Không mặc định cần cho ứng dụng runtime |
| Đọc Blob private | **Storage Blob Data Reader** | Chọn scope account/container thích hợp |
| Đọc/ghi/xóa Blob theo nhu cầu | **Storage Blob Data Contributor** | Không dùng thay cho quyền ARM |
| Gửi message Service Bus | **Azure Service Bus Data Sender** | Có thể cần scope namespace/entity phù hợp |
| Nhận message Service Bus | **Azure Service Bus Data Receiver** | Consumer thường cần thiết kế retry/idempotency |
| Publish event vào Event Hubs | **Azure Event Hubs Data Sender** | Khác với role quản lý namespace |
| Consume event từ Event Hubs | **Azure Event Hubs Data Receiver** | Cần kiểm tra quyền checkpoint store nếu dùng |
| Đọc giá trị secret từ Key Vault dùng RBAC model | **Key Vault Secrets User** | Khác quyền quản lý vault và khác Keys/Certificates |
| Đọc key-value từ App Configuration | **App Configuration Data Reader** | Không tự bao gồm quyền truy cập secret trong Key Vault |

**Không tự gán role Owner/Contributor cấp subscription cho ứng dụng production** nếu chỉ cần đọc một secret hoặc gửi vài message. Role quản lý quyền truy cập nên giới hạn cho nhóm/cơ chế vận hành được ủy quyền.

### Key Vault có hai mô hình quyền cần phân biệt

Azure Key Vault có thể sử dụng:

- **Azure role-based access control permission model:** gán các role data-plane tương ứng như **Key Vault Secrets User** để đọc secret.
- **Vault access policy permission model:** các access policy của vault quy định quyền với key, secret hoặc certificate theo cơ chế tương ứng.

Trước khi chẩn đoán 403, hãy kiểm tra **permission model của vault hiện tại**. Thêm role Secrets User không bảo đảm có hiệu lực như mong đợi nếu vault đang dùng mô hình access policy khác; ngược lại, cấu hình access policy không phải phương án khi đang dùng Azure RBAC model.

**Key Vault Contributor** quản lý chính tài nguyên vault và các thuộc tính management plane; không nên xem nó là role đọc mọi secret value. Ngoài RBAC, network rule/private endpoint và secret state vẫn có thể cản thao tác.

### Cosmos DB cần đọc kỹ cơ chế data-plane riêng

**Azure Cosmos DB for NoSQL** có mô hình **data-plane RBAC** với role definition/assignment riêng, ví dụ **Cosmos DB Built-in Data Reader** và **Cosmos DB Built-in Data Contributor**. Đây không phải trường hợp nên áp dụng máy móc lệnh **az role assignment create** dùng role ARM thông thường.

Tùy API và phiên bản dịch vụ, data-plane permission có thể dùng Cosmos DB native role assignment, keys hoặc cơ chế khác. Ví dụ Cosmos DB for NoSQL có nhóm lệnh **az cosmosdb sql role assignment** và **az cosmosdb sql role definition** để quản lý quyền dữ liệu. Trước khi cấp quyền, cần chốt rõ loại Cosmos DB API, thư viện Java sử dụng và mô hình authorization của account.

## 7. Ví dụ đầy đủ: Spring Boot ghi Blob bằng managed identity

**Bối cảnh:** Spring Boot Documents API chạy trên Azure App Service, lưu nội dung trong Blob container **documents** thuộc storage account **stordersprod01**. Đội hạ tầng được phép tạo và quản lý resource; ứng dụng chỉ cần ghi/đọc Blob.

### 7.1. Ranh giới trách nhiệm

| Thành phần | Quyền/đầu vào | Ai thường quản lý |
| --- | --- | --- |
| Azure subscription và resource group | Quyền ARM để triển khai hạ tầng | Platform/IaC pipeline |
| Storage account và container | Tài nguyên đã tạo, có network rule phù hợp | Platform/data team |
| App Service managed identity | Principal của ứng dụng | Platform/IAM |
| Role dữ liệu trên Storage account/container | **Storage Blob Data Contributor** ở scope cần thiết | IAM quản lý role assignment |
| Spring Boot Blob client | Blob endpoint, TokenCredential, container name | Nhóm ứng dụng |
| Người dùng gọi API | Quyền nghiệp vụ upload/download tại service | Spring Security/ứng dụng |

Một người dùng HTTP có quyền gọi endpoint Documents API **không tự trở thành principal Azure**. Backend phải kiểm tra quyền người dùng ở lớp ứng dụng; managed identity thay mặt backend gọi Blob theo những quyền backend được cấp.

### 7.2. Sơ đồ đường đi

~~~mermaid
sequenceDiagram
    participant U as Người dùng API
    participant A as Spring Boot Documents API
    participant I as Managed identity / Entra
    participant B as Azure Blob Storage
    U->>A: POST tài liệu
    A->>A: Kiểm tra quyền nghiệp vụ
    A->>I: Yêu cầu access token cho Storage
    I-->>A: Token của managed identity
    A->>B: Upload Blob + token
    B->>B: Kiểm tra quyền data plane / network
    B-->>A: Thành công hoặc 401/403/lỗi khác
    A-->>U: Kết quả nghiệp vụ
~~~

**Quyền management của người triển khai App Service không được tự động “truyền” cho managed identity của tiến trình Java.** Phải gán role dữ liệu trực tiếp cho đúng principal hoặc group chứa principal ở scope thích hợp.

### 7.3. Cấu hình Spring Cloud Azure starter

Với phiên bản **Spring Cloud Azure** phù hợp Spring Boot, thêm starter Blob:

~~~xml
<dependency>
    <groupId>com.azure.spring</groupId>
    <artifactId>spring-cloud-azure-starter-storage-blob</artifactId>
</dependency>
~~~

POM này là **trích đoạn**. Dự án cần quản lý phiên bản qua BOM **com.azure.spring:spring-cloud-azure-dependencies** tương thích với dòng Spring Boot đang dùng, thay vì ghi số version tùy ý tại starter.

Cấu hình **application.yml**:

~~~yaml
spring:
  cloud:
    azure:
      storage:
        blob:
          account-name: ${AZURE_STORAGE_ACCOUNT}

app:
  blob:
    container: ${AZURE_BLOB_CONTAINER:documents}
~~~

Ví dụ đặt **AZURE_STORAGE_ACCOUNT=stordersprod01** ở môi trường triển khai. Azure Identity sẽ sử dụng nguồn credential được cấu hình theo cơ chế của Spring Cloud Azure/SDK đã chọn. Với production có managed identity, cần xác minh **đúng identity được sử dụng**; nếu runtime có nhiều nguồn credential, nên cấu hình hoặc tiêm credential tường minh theo tài liệu của phiên bản.

### 7.4. Dịch vụ Java dùng BlobServiceClient

~~~java
import com.azure.storage.blob.BlobContainerClient;
import com.azure.storage.blob.BlobServiceClient;
import java.io.ByteArrayInputStream;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

@Service
public class DocumentsStorage {

    private final BlobContainerClient container;

    public DocumentsStorage(
            BlobServiceClient blobServiceClient,
            @Value("${app.blob.container}") String containerName) {
        this.container = blobServiceClient.getBlobContainerClient(containerName);
    }

    public void upload(String blobName, byte[] bytes) {
        container.getBlobClient(blobName).upload(
                new ByteArrayInputStream(bytes),
                bytes.length,
                false
        );
    }
}
~~~

Phương thức **upload** sử dụng **overwrite=false** để tránh âm thầm ghi đè. Đây là ví dụ quản lý dữ liệu; code không tạo storage account, không gán role và không tự tạo container. Ở ứng dụng thật, cần giới hạn kích thước tệp, xác minh quyền người dùng API, chuẩn hóa tên Blob, streaming, retry và xử lý conflict phù hợp.

**BlobServiceClient được tạo thành công không chứng minh có DataActions cần thiết**. Phải chạy request thật; nhiều SDK client trì hoãn xác thực/kết nối cho đến khi sử dụng.

### 7.5. Nếu dùng SDK trực tiếp

Khi không dùng starter, vẫn dùng credential Azure Identity và Azure Storage SDK:

~~~java
import com.azure.core.credential.TokenCredential;
import com.azure.identity.ManagedIdentityCredentialBuilder;
import com.azure.storage.blob.BlobServiceClient;
import com.azure.storage.blob.BlobServiceClientBuilder;

TokenCredential identity =
        new ManagedIdentityCredentialBuilder().build();

BlobServiceClient client = new BlobServiceClientBuilder()
        .endpoint("https://stordersprod01.blob.core.windows.net")
        .credential(identity)
        .buildClient();
~~~

Ví dụ này chỉ chạy thành công khi môi trường **hỗ trợ managed identity**, identity đã được bật/gắn đúng và có quyền data plane phù hợp. Có thể dùng **DefaultAzureCredential** trong môi trường kiểm soát được credential chain; nó không tự chọn danh tính dựa vào role quyền cao nhất.

## 8. Thực hành Azure CLI: xem role và gán quyền đúng scope

Các lệnh dưới đây dành cho **lab có tài nguyên test và quyền quản trị được cấp**. Giá trị trong dấu ngoặc nhọn/góc là placeholder; không chạy trực tiếp trên subscription production nếu chưa có quy trình thay đổi quyền phù hợp.

### 8.1. Xác định đúng subscription và resource ID

~~~bash
az login

az account show   --query "{subscription:id, tenant:tenantId, name:name}"   --output json

az account set --subscription "<subscription-id>"

az storage account show   --resource-group "<resource-group>"   --name "<storage-account>"   --query "{id:id, name:name, endpoints:primaryEndpoints}"   --output json
~~~

Tài nguyên Storage Account có ARM ID điển hình:

~~~text
/subscriptions/<subscription-id>/resourceGroups/<resource-group>/providers/Microsoft.Storage/storageAccounts/<storage-account>
~~~

**Resource ID** là scope để quản lý và phân quyền cho resource, còn Blob data endpoint có hình thức **https://{account}.blob.core.windows.net**. Không dùng ARM resource ID làm URL trong BlobServiceClient.

### 8.2. Xem principal của managed identity

Với App Service đã bật system-assigned managed identity:

~~~bash
az webapp identity show   --resource-group "<app-resource-group>"   --name "<app-service>"   --query "{principalId:principalId, tenantId:tenantId, type:type}"   --output json
~~~

Với user-assigned managed identity:

~~~bash
az identity show   --resource-group "<identity-resource-group>"   --name "<identity-name>"   --query "{id:id, clientId:clientId, principalId:principalId}"   --output json
~~~

Chú ý: **client ID** dùng để chỉ định identity trong một số Azure Identity credential builders; **principal ID** là định danh cần dùng khi gán role cho identity.

### 8.3. Xem role definition, phân biệt Actions và DataActions

~~~bash
az role definition list   --name "Contributor"   --output json

az role definition list   --name "Storage Blob Data Contributor"   --output json
~~~

Trong kết quả, tìm trường **permissions** gồm **actions/notActions/dataActions/notDataActions**. Có thể so sánh vai trò quản lý và vai trò dữ liệu. Không kết luận role chỉ từ nhãn hiển thị; kiểm tra role definition và phạm vi gán thực tế.

### 8.4. Gán role Blob Data Contributor

Người dùng thực hiện lệnh phải có quyền tạo role assignment ở scope phù hợp, chẳng hạn role quản lý truy cập được ủy quyền:

~~~bash
az role assignment create   --assignee-object-id "<managed-identity-principal-id>"   --assignee-principal-type ServicePrincipal   --role "Storage Blob Data Contributor"   --scope "<storage-account-resource-id>"
~~~

Lệnh gán role cho **đúng principal ID** trên **đúng storage account**. Đối với ứng dụng chỉ truy cập một container, có thể cân nhắc scope container khi được hỗ trợ và khi khả thi về vận hành.

Không cần cấp **Owner** toàn subscription chỉ để service ghi Blob. Sau khi gán role, có thể cần thời gian để quyền được cập nhật trong dịch vụ và token/cache liên quan.

### 8.5. Xem quyền đã gán

~~~bash
az role assignment list   --assignee "<managed-identity-principal-id>"   --scope "<storage-account-resource-id>"   --include-inherited   --output table
~~~

Nếu không thấy role mong đợi, kiểm tra tenant/subscription, principal ID, scope, quyền của người tra cứu và tính kế thừa. Có role trong danh sách chưa chắc request thành công nếu dịch vụ dùng mô hình authorization khác hoặc network chưa cho phép.

### 8.6. Kiểm thử bằng Azure CLI có một giới hạn quan trọng

Có thể dùng tài khoản developer để thử đọc Blob bằng Microsoft Entra token:

~~~bash
az storage blob list   --account-name "<storage-account>"   --container-name "documents"   --auth-mode login   --output table
~~~

Lệnh trên kiểm chứng quyền **của identity đang đăng nhập Azure CLI**, không nhất thiết là managed identity của App Service. Nếu CLI thành công nhưng Spring Boot runtime thất bại, không thể kết luận ứng dụng đã có quyền. **Integration test phải chạy dưới đúng runtime identity của ứng dụng**.

Để xác thực quyền của App Service managed identity, gọi một thao tác Blob thực tế từ ứng dụng đã triển khai và thu thập mã lỗi/request ID thích hợp.

## 9. Vai trò RBAC theo dịch vụ: chọn sao cho đúng

### 9.1. Blob Storage

Một hệ thống lưu tài liệu có thể tách các principal:

| Principal | Nghiệp vụ | Role phù hợp |
| --- | --- | --- |
| Documents API | Upload và cập nhật Blob | **Storage Blob Data Contributor** |
| Reporting API | Chỉ tải Blob để đọc | **Storage Blob Data Reader** |
| Platform deployment | Tạo/cấu hình Storage Account | Quyền quản lý tài nguyên theo IaC/scope |
| IAM operator | Tạo role assignment | Quyền quản trị role assignment được ủy quyền |

Trong Storage, một số thao tác **liệt kê containers** hoặc quản lý metadata có khác biệt API/plane. Quyền cụ thể phải kiểm tra theo operation: không suy ra chỉ từ “có quyền Reader trên Storage Account”.

**Shared Key/SAS** là đường xác thực khác RBAC token. Nếu ứng dụng dùng connection string chứa account key, request có thể thành công mà không phản ánh quyền **Storage Blob Data Contributor** của principal. Khi học RBAC, nên dùng **--auth-mode login** hoặc SDK **TokenCredential** để tránh phép thử sai cơ chế.

### 9.2. Service Bus

Azure Service Bus phân biệt quản trị queue/topic với xử lý message:

- Nhóm quản trị có thể tạo queue/topic và cấu hình thuộc tính thực thể.
- Producer chỉ cần role **Azure Service Bus Data Sender** trên scope phù hợp.
- Consumer chỉ cần role **Azure Service Bus Data Receiver** trên scope phù hợp.
- Một workload vừa gửi vừa nhận có thể cần kết hợp role theo nghiệp vụ; không nhất thiết cấp role toàn quyền.

Spring Cloud Azure Service Bus starter giúp cấu hình client và tích hợp Spring, nhưng không tự tạo role assignment. Một **ServiceBusSenderClient** được tạo không chứng minh principal có quyền gửi message; lỗi có thể xuất hiện khi thực sự send.

### 9.3. Event Hubs

Phân biệt thao tác tạo namespace/event hub với publish/consume sự kiện. Dùng **Azure Event Hubs Data Sender** hoặc **Azure Event Hubs Data Receiver** theo nhu cầu.

Nếu một consumer dùng Blob Storage để lưu checkpoint, nó có thể cần **role Blob riêng cho checkpoint store**. Quyền đọc event trên Event Hubs không tự cấp quyền ghi checkpoint Blob; một lỗi tưởng chừng đến từ Event Hubs có thể thực tế nằm ở Storage Account khác.

### 9.4. Key Vault và App Configuration

Một Spring Boot service đọc cấu hình từ App Configuration và lấy secret từ Key Vault có **hai resource và hai nhóm quyền dữ liệu**:

| Resource | Nhu cầu | Permission điển hình |
| --- | --- | --- |
| App Configuration store | Đọc key-value/feature flags | **App Configuration Data Reader** |
| Key Vault | Đọc secret value | **Key Vault Secrets User** nếu dùng RBAC model |
| Cùng tài nguyên ở management plane | Tạo/vận hành resource | Role quản lý tương ứng |

App Configuration tham chiếu secret từ Key Vault không có nghĩa quyền ở App Configuration tự mở quyền đọc Key Vault. Trước khi cấp role Key Vault, phải xác minh vault dùng **Azure RBAC** hay **access policy**.

### 9.5. Cosmos DB

Với Cosmos DB for NoSQL, một Spring Data Cosmos repository muốn đọc/ghi item phải dùng authorization được hỗ trợ bởi **Cosmos DB data plane**. Trong cơ chế native RBAC, role như **Cosmos DB Built-in Data Contributor** được gán bằng cơ chế **Cosmos DB SQL role assignment**.

Không nên dùng role **Contributor** trên Cosmos DB account để suy ra **CosmosAsyncClient** có quyền truy vấn hoặc upsert item khi dùng Entra token. Đồng thời không mặc định các API Cosmos DB khác nhau có chung tập role/SDK/authentication.

## 10. Authentication, RBAC và network: phân loại lỗi chính xác

Một request tới dịch vụ có thể thất bại ở các tầng khác nhau:

~~~mermaid
flowchart TD
    A[Spring Boot gọi Azure SDK] --> B{Đúng service endpoint?}
    B -->|Không| E1[Sửa account / namespace / URL]
    B -->|Có| C{Credential lấy được token?}
    C -->|Không| E2[Kiểm tra tenant / identity / token source]
    C -->|Có| D{Request tới được dịch vụ?}
    D -->|Không| E3[Kiểm tra DNS / firewall / Private Endpoint]
    D -->|Có| F{Principal có quyền thao tác?}
    F -->|Không| E4[Kiểm tra DataActions / scope / permission model]
    F -->|Có| G[Kiểm tra nghiệp vụ, quota, conflict, throttling]
~~~

| Triệu chứng | Khả năng thường gặp | Hướng xác minh |
| --- | --- | --- |
| **CredentialUnavailableException** | Runtime không có nguồn credential được hỗ trợ | Kiểm tra managed/workload identity, biến môi trường và credential chain |
| **AuthenticationFailedException** | Tenant, issuer, federated trust hoặc credential không hợp lệ | Xác định identity thật, token source và cấu hình Entra |
| Client có token nhưng Blob upload **403** | Thiếu DataActions ghi Blob, scope không bao phủ resource, policy/network | Kiểm tra Storage Blob Data Contributor và mã lỗi Azure Storage |
| Azure CLI đọc ARM resource được nhưng liệt kê Blob thất bại | Principal có management role nhưng thiếu quyền data plane | So sánh role Contributor/Reader với Blob Data Reader |
| Key Vault trả **403** | Thiếu quyền secret hoặc permission model của vault khác kỳ vọng | Kiểm tra vault RBAC/access policy, role và scope |
| Service Bus gửi message bị từ chối | Principal thiếu role Data Sender hoặc sai namespace | Xác minh entity đích và data role |
| SDK timeout | DNS, private endpoint, outbound route hoặc firewall | Kiểm tra kết nối từ chính App Service/Pod/VM |
| **401** khi gọi dịch vụ | Token không hợp lệ, không đúng audience/authority hoặc hết hạn | Xác định endpoint, SDK và nguồn token |
| **404/409/429** | Sai tên resource, conflict, quota hoặc throttling | Đọc error code cụ thể, không vội kết luận thiếu RBAC |

**Không suy luận 403 luôn có nghĩa thiếu role.** Một số dịch vụ dùng 403 cho network policy, và những hệ thống khác có thể trả về mã lỗi đặc thù. Kiểm tra **service error code**, request ID, principal và endpoint để định vị chính xác.

### Tác động của role propagation và token cache

Một role assignment vừa được tạo có thể chưa lập tức có hiệu lực do quá trình cập nhật quyền và cache. Không nên khắc phục bằng cách cấp role rộng hơn. Hãy xác minh đúng assignment/scope, đợi theo hướng dẫn dịch vụ rồi chạy lại request có kiểm soát. Token và cơ chế cache theo SDK/runtime có thể làm thời điểm cập nhật khác nhau.

Nếu tổ chức dùng **Privileged Identity Management (PIM)** hoặc quyền đủ điều kiện (eligible), kiểm tra role đã **active** chưa; role ở trạng thái eligible có thể cần activation trước khi sử dụng.

## 11. Thiết kế kiểm thử quyền theo nguyên tắc ít quyền nhất

Chỉ chạy unit test kiểm tra việc tạo Spring context là chưa đủ. Để xác minh RBAC, phải có phép thử thực sự gọi dịch vụ bằng **danh tính đã định**.

### 11.1. Unit test

- Mock hoặc giả lập adapter xung quanh Azure SDK để kiểm tra xử lý nghiệp vụ khi request trả thành công/403/404/409.
- Kiểm tra API của ứng dụng không cho người dùng không có quyền nghiệp vụ gọi thao tác ghi/xóa.
- Không bắt unit test phụ thuộc Azure CLI login, client secret hoặc subscription của developer.

### 11.2. Integration test trong môi trường Azure lab

Ví dụ chuẩn bị ba identity riêng trên storage account thử nghiệm:

| Identity test | Role | Kết quả mong đợi |
| --- | --- | --- |
| **reader-test** | Storage Blob Data Reader | Đọc blob thành công, ghi blob bị từ chối |
| **writer-test** | Storage Blob Data Contributor | Đọc/ghi blob trong scope được cấp |
| **management-test** | Reader ở management plane, không có data role | Xem metadata resource nếu có quyền, nhưng không đọc private Blob bằng Entra token |

Với identity mang quyền management mạnh hơn, cần lưu ý **đường truy cập key gián tiếp** đã nêu ở phần 4. Để phép thử thật sự đánh giá RBAC token, không dùng connection string chứa account key.

Những phép thử “phải bị từ chối” cần được chạy trên **resource lab**, không thu hồi quyền của ứng dụng sản xuất hoặc thay đổi role chung của cả nhóm.

### 11.3. Kiểm thử bằng emulator có giới hạn

**Azurite** hữu ích để kiểm tra nhiều thao tác Blob/Queue trong quá trình phát triển, nhưng không tương đương hoàn toàn Microsoft Entra, Azure RBAC, deny assignment, PIM hay private networking của Azure thật. Nó không chứng minh principal runtime có quyền đúng trên production storage account.

**Ứng dụng có thể chạy trong Spring Boot nhưng vẫn chưa xác thực RBAC:** nhiều Azure SDK client chỉ thực sự lấy token/gọi endpoint khi thực hiện request đầu tiên.

### 11.4. Ghi log và khả năng điều tra

Nên thu thập có kiểm soát:

- **Operation** và resource/endpoint hostname.
- HTTP/gRPC/AMQP error code hoặc service-specific error code.
- **Azure request ID/correlation ID**, timestamp, retry count và latency.
- Loại credential/identity đang dùng ở mức metadata được phép công bố nội bộ.
- Scope và role assignment liên quan khi có cuộc điều tra được ủy quyền.

**Tuyệt đối không log** access token, refresh token, account key, connection string, SAS URL, secret value hay nội dung workload federation token. Tenant/principal/resource ID cũng cần xử lý phù hợp chính sách dữ liệu nội bộ.

## 12. Tình huống phân tích: cùng một principal, hai loại quyền

**Tình huống A — Platform engineer:** cần tạo Storage Account và thiết lập network rule bằng Bicep/Terraform; sau đó ứng dụng Documents API ghi tệp.

- Identity triển khai cần quyền **management plane** phù hợp để tạo/cấu hình resource.
- Identity của Documents API cần **Storage Blob Data Contributor** trên account/container đúng phạm vi.
- Nếu ứng dụng không cần tạo Storage Account, không cấp quyền quản lý resource cho ứng dụng.
- Quyền của CI deployer và App Service managed identity có thể được tách hoàn toàn.

**Tình huống B — Service Bus consumer:** ứng dụng đọc message và ghi checkpoint vào Blob Storage.

- Quyền **Azure Service Bus Data Receiver** cho namespace/entity cần đọc.
- Quyền Blob thích hợp trên account/container checkpoint nếu thư viện consumer sử dụng storage để lưu checkpoint.
- Không cần Azure Service Bus Contributor trên cả subscription chỉ vì consumer phải xử lý message.

**Tình huống C — Spring Boot đọc cấu hình và secret:**

- Quyền **App Configuration Data Reader** trên store cấu hình.
- Quyền **Key Vault Secrets User** nếu Key Vault dùng RBAC model, hoặc access policy tương ứng nếu vault dùng mô hình đó.
- Nếu thiếu quyền Key Vault, app vẫn có thể đọc key-value thông thường nhưng thất bại khi resolve Key Vault reference.

### Bảng quyết định theo thao tác

| Cần làm gì? | Loại quyền cần tìm trước |
| --- | --- |
| Tạo hoặc xóa resource Azure qua ARM | Management Actions |
| Tạo role assignment | Quyền quản trị role assignment ở scope |
| Upload hoặc đọc blob bằng Entra token | DataActions của Storage |
| Gửi/nhận Service Bus message | Data role Sender/Receiver |
| Đọc Key Vault secret | Data permission theo RBAC/access policy của vault |
| Truy vấn Cosmos DB for NoSQL | Cosmos DB native data-plane authorization |
| Vượt qua firewall/private network | Cấu hình network hợp lệ; RBAC không thay thế mạng |

## 13. Liên hệ với tích hợp đa cloud

Các cloud đều có cơ chế danh tính, role/policy và resource scope, nhưng không đồng nhất chi tiết:

| Khái niệm | Azure | AWS | Google Cloud |
| --- | --- | --- | --- |
| Danh tính workload | Managed Identity / Workload Identity | IAM Role / STS temporary credentials | Service Account / Workload Identity |
| Quản lý tài nguyên | Azure Resource Manager + management Actions | Service API/control plane + IAM policy theo API | Cloud Resource Manager + service APIs / IAM |
| Truy cập dữ liệu | Azure RBAC DataActions hoặc mô hình quyền riêng của dịch vụ | IAM actions/resource policies tùy dịch vụ | IAM permissions/roles và service-level access model |
| Phạm vi tổ chức | Management group, subscription, resource group, resource | Organization, account, resource | Organization, folder, project, resource |
| Object storage | Azure Blob Storage | Amazon S3 | Cloud Storage |

Ví dụ, không ánh xạ máy móc role **Storage Blob Data Contributor** thành một “role chung” cho S3 và GCS mà bỏ qua khác biệt về IAM policy, ACL, bucket scope, object prefix, public access, service account và cơ chế token.

**Spring Cloud Azure, Spring Cloud AWS và Spring Cloud GCP** giúp tích hợp client SDK vào Spring Boot, nhưng không thay thế bước thiết kế **quyền tối thiểu** riêng của mỗi provider. Khi viết adapter đa cloud, cần đưa vào thiết kế cả **principal**, **permission scope**, **service endpoint** và **failure semantics**, không chỉ tên phương thức upload/download.

## 14. Bài thực hành: chứng minh sự khác biệt giữa hai plane

**Bối cảnh:** tạo một Spring Boot Documents API truy cập Blob container private **documents** trong account lab. Mục tiêu là quan sát khi thay đổi role management và data.

1. **Chuẩn bị lab:** tạo hoặc được cấp Storage Account, Blob container và hai identity thử nghiệm; ghi lại subscription ID, account resource ID và Blob endpoint. Không dùng production.
2. **Xác minh ARM:** với identity có quyền đọc management plane, dùng Azure CLI xem metadata Storage Account qua **az storage account show**.
3. **Chỉ cấp management Reader:** dùng một principal chưa có Blob Data Reader; thử liệt kê Blob bằng **--auth-mode login** hoặc SDK TokenCredential. Ghi nhận kết quả và service error code.
4. **Cấp Blob Data Reader:** trên scope account/container được hỗ trợ, thử đọc Blob; thử upload và xác nhận không được cấp quyền ghi.
5. **Cấp Blob Data Contributor:** xác minh upload một Blob tên riêng thành công; đọc lại rồi cleanup.
6. **Thử Spring Boot:** inject BlobServiceClient từ Spring Cloud Azure starter hoặc tạo client bằng Azure Identity SDK; chạy tác vụ dưới managed identity thật, không kết luận từ phiên CLI của developer.
7. **Mở rộng:** thêm một Service Bus queue hoặc Key Vault trong tài nguyên test, thử nghiệm role Data Sender/Secrets User đúng mô hình quyền của dịch vụ.
8. **Báo cáo:** lập bảng role definition, principal ID, scope, endpoint, thao tác ARM/data, mã lỗi và giải thích. Thu hồi các role assignment tạm thời do lab tạo theo quy trình môi trường test.

### Câu hỏi tự kiểm tra

1. Vì sao một người có role **Reader** có thể xem Storage Account nhưng không đọc được nội dung Blob private qua Entra token?
2. Role **Contributor** có tự bao gồm tất cả **DataActions** của Storage không? Có đường truy cập dữ liệu gián tiếp nào phải cân nhắc?
3. Vì sao **NotDataActions** của một role không phải deny áp dụng cho mọi role assignment khác?
4. Nếu Documents API nhận **403** khi upload, cần kiểm tra những thông tin nào trước khi cấp thêm role?
5. Vì sao kết quả thành công của **az storage blob list --auth-mode login** trên máy developer không xác nhận quyền của App Service managed identity?
6. Tại sao một Event Hubs consumer dùng Blob checkpoint có thể cần quyền ở hai dịch vụ khác nhau?
7. Khi Key Vault dùng access policy model, điều gì xảy ra nếu chỉ dựa vào role RBAC Secrets User mà không xem permission model?
8. Vì sao không thể dùng role management ARM thông thường để kết luận Cosmos DB for NoSQL cho phép query document bằng Entra token?

## 15. Ghi nhớ

- **Management plane** quản lý tài nguyên; **data plane** thao tác với dữ liệu/dịch vụ. Một principal có quyền ở plane này chưa chắc được phép thao tác ở plane kia.
- **Azure RBAC = principal + role definition + scope**; xác định **Actions** và **DataActions**, tính kế thừa, điều kiện/deny assignment và quyền hiệu lực thay vì chỉ nhìn tên role.
- **Contributor/Reader/Owner** có semantics quản lý khác **Storage Blob Data Reader/Contributor**; các thao tác quản lý nhạy cảm như **listKeys** có thể tạo đường truy cập dữ liệu gián tiếp.
- **Key Vault** cần kiểm tra RBAC hoặc access policy model; **Cosmos DB for NoSQL** có cơ chế data-plane RBAC riêng; **Service Bus/Event Hubs** có role gửi/nhận phù hợp.
- Trong Spring Boot, **Spring Cloud Azure starter và Azure SDK** không tự cấp quyền. Kiểm chứng bằng request thật với **đúng runtime identity**, endpoint, RBAC scope và đường mạng.
- Phân quyền tối thiểu, tách deploy identity với runtime identity, bảo vệ secret và kiểm thử cả trường hợp bị từ chối trên tài nguyên lab.

## Tài liệu tham khảo

- [What is Azure RBAC?](https://learn.microsoft.com/azure/role-based-access-control/overview)
- [Understand Azure role definitions](https://learn.microsoft.com/azure/role-based-access-control/role-definitions)
- [Understand Azure role assignments](https://learn.microsoft.com/azure/role-based-access-control/role-assignments)
- [Azure RBAC best practices](https://learn.microsoft.com/azure/role-based-access-control/best-practices)
- [Assign an Azure role using Azure CLI](https://learn.microsoft.com/azure/role-based-access-control/role-assignments-cli)
- [Authorize access to blobs using Microsoft Entra ID](https://learn.microsoft.com/azure/storage/blobs/authorize-access-azure-active-directory)
- [Azure Key Vault RBAC guide](https://learn.microsoft.com/azure/key-vault/general/rbac-guide)
- [Azure Cosmos DB for NoSQL role-based access control](https://learn.microsoft.com/azure/cosmos-db/nosql/security/how-to-grant-data-plane-role-based-access)
- [Spring Cloud Azure documentation](https://learn.microsoft.com/azure/developer/java/spring-framework/)
