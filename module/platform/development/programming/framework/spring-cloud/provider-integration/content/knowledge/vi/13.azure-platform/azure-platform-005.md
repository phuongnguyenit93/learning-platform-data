# Azure CLI, managed identity và workload identity

Trong quá trình phát triển Spring Boot tích hợp Azure, cùng một tính năng có thể chạy thành công trên máy lập trình viên nhưng thất bại sau khi triển khai lên App Service, AKS hoặc pipeline CI. Một nguyên nhân phổ biến là **nguồn danh tính thay đổi theo môi trường**: laptop dùng phiên đăng nhập **Azure CLI**, ứng dụng chạy trên Azure có thể dùng **managed identity**, còn Pod trên AKS hoặc job CI thường phù hợp với **workload identity federation**.

Bài thuộc chương **Nền tảng Azure** của module **SPRING_CLOUD_PROVIDER_INTEGRATION**, thực hành tích hợp Spring Boot với dịch vụ managed của AWS, Azure và Google Cloud thông qua thư viện Spring Cloud tương ứng. Chủ đề tập trung vào thao tác thiết lập và xác minh danh tính Azure để truy cập storage, messaging, dữ liệu và secret; đồng thời tạo nền tảng cho kiểm thử tích hợp và so sánh cách quản lý quyền của các cloud provider.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Dùng **Azure CLI** để xác nhận tenant, subscription, principal, resource và quyền trong môi trường phát triển.
2. Phân biệt **system-assigned managed identity**, **user-assigned managed identity**, service principal và workload identity federation.
3. Bật managed identity cho một Azure workload, cấp quyền data plane cho đúng principal và scope.
4. Mô tả quy trình thiết lập **Microsoft Entra Workload ID** trên AKS: OIDC issuer, federated credential, Kubernetes service account và Pod.
5. Chọn **AzureCliCredential**, **ManagedIdentityCredential**, **WorkloadIdentityCredential** hoặc **DefaultAzureCredential** trong Spring Boot theo điều kiện chạy.
6. Chẩn đoán các lỗi xác thực, ủy quyền và mạng; thiết kế integration test an toàn theo từng môi trường.

## 2. Cần phân biệt ba công cụ, ba nhiệm vụ

| Thành phần | Cung cấp điều gì? | Vị trí sử dụng điển hình | Điều nó không tự thực hiện |
| --- | --- | --- | --- |
| **Azure CLI** | Công cụ chạy lệnh Azure và đăng nhập vào tenant, subscription | Máy lập trình viên, terminal quản trị, pipeline được cấp phép | Không tự cấp quyền cho Spring Boot đang chạy ở nơi khác |
| **Managed identity** | Danh tính workload do Azure quản lý, gắn với tài nguyên Azure hỗ trợ | App Service, Functions, VM và các dịch vụ hỗ trợ | Không tự mang quyền ghi Blob, gửi message hay đọc secret |
| **Workload identity federation** | Liên kết token từ workload/identity provider tin cậy với Microsoft Entra | AKS Workload ID, CI/CD có OIDC | Không tự chọn đúng namespace/service account hoặc Azure RBAC |

Cần thêm một lớp phía ứng dụng: **Azure Identity SDK for Java**, cung cấp các triển khai **TokenCredential**. Trong một ứng dụng Spring Boot, các client của Azure SDK sử dụng token từ credential này khi gọi dịch vụ.

~~~mermaid
flowchart LR
    L[Máy dev / Azure CLI] --> C[AzureCliCredential]
    M[App Service / VM] --> D[ManagedIdentityCredential]
    W[AKS / OIDC token] --> E[WorkloadIdentityCredential]
    C --> SDK[Azure SDK client]
    D --> SDK
    E --> SDK
    SDK --> S[Blob / Service Bus / Key Vault]
    R[RBAC / policy] -. kiểm soát quyền .-> S
~~~

**Authentication** chứng minh workload hoặc người dùng là ai; **authorization** quyết định thao tác nào được phép; **network reachability** quyết định request có tới được endpoint hay không. Ba điều kiện cần được kiểm tra riêng.

## 3. Những định danh không được nhầm lẫn

Giả sử hệ thống có một Spring Boot service cần truy cập Azure Blob Storage:

| Giá trị | Ý nghĩa | Ví dụ sử dụng |
| --- | --- | --- |
| **Tenant ID** | Định danh Microsoft Entra directory | Cấp token và cấu hình federation |
| **Subscription ID** | Đơn vị quản lý tài nguyên, billing và governance của ARM | Tạo App Service, Storage Account, Azure RBAC scope |
| **Resource group** | Nhóm logic thuộc subscription | Tìm App Service, identity, Storage Account |
| **Client ID** | Định danh application/user-assigned identity | Chọn user-assigned managed identity |
| **Principal/Object ID** | Định danh service principal/đối tượng được cấp quyền | Tạo Azure role assignment |
| **Resource ID** | Đường dẫn ARM xác định resource | Chọn scope RBAC hoặc gắn identity |
| **Service endpoint** | Host/URL để SDK giao tiếp với dịch vụ dữ liệu | Địa chỉ Blob, Service Bus hoặc Key Vault |

Trong đa số lời gọi **Blob data plane**, ứng dụng cần **Blob endpoint + credential + quyền dữ liệu**; nó không truyền subscription ID trong mỗi lệnh upload. Subscription và resource group trở nên quan trọng khi quản trị tài nguyên, phân quyền hoặc tìm đúng account.

Một user-assigned managed identity có cả **client ID**, **principal ID** và **resource ID**. Ba giá trị này không thay thế nhau.

## 4. Azure CLI trên máy phát triển

Azure CLI là công cụ để quản lý tài nguyên và thiết lập phiên làm việc với Microsoft Entra. Nó hữu ích để đối chiếu cấu hình môi trường dev trước khi chạy ứng dụng Spring Boot.

### 4.1. Đăng nhập và kiểm tra ngữ cảnh

~~~bash
# Đăng nhập tương tác bằng danh tính developer.
az login

# Nếu tổ chức yêu cầu một tenant cụ thể:
az login --tenant "<tenant-id>"

# Xem các subscription mà danh tính hiện có thể truy cập.
az account list --output table

# Xem tenant và subscription mặc định.
az account show   --query "{tenant:tenantId, subscription:id, name:name}"   --output json

# Đổi subscription mặc định cho các thao tác CLI tiếp theo.
az account set --subscription "<subscription-id>"
~~~

**az account set** chọn ngữ cảnh subscription cho Azure CLI; lệnh này không gán quyền mới, không đổi tenant cho mọi client và không thay endpoint của một **BlobServiceClient** đã tạo.

Máy phát triển có thể có nhiều nguồn credential cùng tồn tại: Azure CLI, IDE, biến môi trường service principal hoặc những công cụ khác. **DefaultAzureCredential** không nhất thiết chọn Azure CLI chỉ vì developer đã chạy **az login**. Khi cần thử nghiệm đúng phiên CLI, hãy chọn **AzureCliCredential** tường minh.

### 4.2. Xác minh tài nguyên đích

~~~bash
# Đọc thông tin quản lý storage account.
az storage account show   --name "<storage-account-name>"   --resource-group "<resource-group-name>"   --query "{id:id, name:name, location:location, endpoints:primaryEndpoints}"   --output json
~~~

Lệnh dùng quyền **management plane** để đọc resource. Kết quả có **resource ID** và endpoint; nó chưa chứng minh người dùng được đọc/ghi dữ liệu Blob.

Muốn kiểm tra data plane bằng token đăng nhập Azure CLI:

~~~bash
# Container phải tồn tại; account và quyền dữ liệu phải đúng.
az storage blob list   --account-name "<storage-account-name>"   --container-name "<container-name>"   --auth-mode login   --output table
~~~

Tùy thao tác, yêu cầu quyền data plane phù hợp, ví dụ **Storage Blob Data Reader** cho đọc hoặc **Storage Blob Data Contributor** cho ghi. Một người có role **Contributor** trên management plane không mặc nhiên có quyền đọc blob.

### 4.3. Khi nào không dùng Azure CLI?

Không dùng tài khoản đăng nhập cá nhân làm cơ chế xác thực thường trực của dịch vụ production. Máy chủ không nên phụ thuộc cache **az login**, phiên MFA của người phát triển hoặc thao tác đăng nhập thủ công sau khi khởi động lại.

**Azure CLI vẫn có thể có trong pipeline**, nhưng phải đảm bảo pipeline đăng nhập qua identity được quản lý đúng cách và Java SDK thật sự sử dụng nguồn credential dự kiến. CI chạy lệnh **az login** không đồng nghĩa mọi JVM process tự động nhận được **WorkloadIdentityCredential**.

## 5. Managed identity: bản chất và hai kiểu

**Managed identity** là danh tính được Azure quản lý để workload được Azure hỗ trợ có thể lấy Microsoft Entra access token mà không tự lưu client secret dài hạn.

| Tiêu chí | System-assigned | User-assigned |
| --- | --- | --- |
| Đơn vị quản lý | Danh tính gắn trực tiếp vào một resource hỗ trợ | Một Azure resource identity độc lập |
| Vòng đời | Gắn với resource; resource bị xóa thì identity gắn với nó không còn | Tồn tại độc lập, có thể tái sử dụng |
| Tái sử dụng giữa workload | Không phải mục tiêu chính | Có thể gắn vào nhiều resource hỗ trợ |
| Chọn identity ở runtime | Thường có thể dùng mặc định nếu chỉ có identity phù hợp | Nên cung cấp client ID/resource ID theo API để chọn đúng identity |
| Quyền truy cập tài nguyên khác | Cần role assignment phù hợp | Cần role assignment phù hợp |

Managed identity **không phải một cách viết khác của subscription**: cùng một managed identity có thể được cấp role trên tài nguyên đích ở subscription khác nếu mô hình danh tính và quyền cho phép.

## 6. Tạo managed identity và gắn vào workload

### 6.1. Bật system-assigned identity cho App Service

Giả sử một Spring Boot service đã được triển khai lên Azure App Service. Người có quyền quản lý resource có thể bật identity:

~~~bash
az webapp identity assign   --resource-group "<app-resource-group>"   --name "<app-service-name>"
~~~

Lệnh trả về hoặc cho phép tra cứu thông tin identity. Có thể đọc principal ID:

~~~bash
az webapp identity show   --resource-group "<app-resource-group>"   --name "<app-service-name>"   --query "{principalId:principalId, tenantId:tenantId, type:type}"   --output json
~~~

**Principal ID** là đối tượng dùng khi phân quyền cho identity. App Service phải thật sự hỗ trợ cơ chế managed identity và đã bật identity trước khi SDK trong ứng dụng có thể lấy token.

### 6.2. Tạo user-assigned managed identity

~~~bash
az identity create   --resource-group "<identity-resource-group>"   --name "<user-assigned-identity-name>"

az identity show   --resource-group "<identity-resource-group>"   --name "<user-assigned-identity-name>"   --query "{id:id, clientId:clientId, principalId:principalId, tenantId:tenantId}"   --output json
~~~

Kết quả gồm:

- **id:** resource ID của identity, dùng khi tham chiếu resource này.
- **clientId:** dùng để lựa chọn danh tính user-assigned trong một số credential/runtime.
- **principalId:** dùng để gán quyền Azure RBAC.
- **tenantId:** tenant quản lý danh tính.

Có thể gắn user-assigned identity vào App Service thông qua ID của identity, nếu dịch vụ và quyền quản trị hỗ trợ:

~~~bash
az webapp identity assign   --resource-group "<app-resource-group>"   --name "<app-service-name>"   --identities "<user-assigned-identity-resource-id>"
~~~

Việc tạo identity hoặc gắn vào App Service không tự cấp quyền dữ liệu Blob, Service Bus hay Key Vault.

### 6.3. Chọn user-assigned identity trong Java

~~~java
import com.azure.core.credential.TokenCredential;
import com.azure.identity.ManagedIdentityCredentialBuilder;

String clientId = System.getenv("AZURE_CLIENT_ID");
if (clientId == null || clientId.isBlank()) {
    throw new IllegalStateException("AZURE_CLIENT_ID is required");
}

TokenCredential credential = new ManagedIdentityCredentialBuilder()
        .clientId(clientId)
        .build();
~~~

**AZURE_CLIENT_ID** phải là **client ID** của user-assigned managed identity đã gắn vào runtime. Nếu dự án muốn dùng system-assigned identity, có thể khởi tạo **new ManagedIdentityCredentialBuilder().build()** trong môi trường phù hợp.

Không nên cấu hình một client ID rồi mặc định identity đó có thể được chọn trên bất kỳ máy hoặc Pod nào. **ManagedIdentityCredential** cần hạ tầng cấp token của dịch vụ Azure hosting hỗ trợ và gắn danh tính tương ứng.

## 7. Cấp quyền dữ liệu cho managed identity

Giả sử App Service cần upload Blob vào storage account. Cần xác định:

1. Principal ID của managed identity.
2. Resource ID của storage account hoặc scope nhỏ hơn mà role assignment hỗ trợ.
3. Role cho hoạt động dữ liệu, ví dụ **Storage Blob Data Contributor**.
4. Người/lệnh tạo role assignment phải có **quyền quản lý gán role** ở scope tương ứng.

Từ terminal quản trị có quyền:

~~~bash
# Gán role cho principal ID, không dùng client ID ở đây.
az role assignment create   --assignee-object-id "<managed-identity-principal-id>"   --assignee-principal-type ServicePrincipal   --role "Storage Blob Data Contributor"   --scope "<storage-account-resource-id>"
~~~

Chẳng hạn **storage-account-resource-id** có hình dạng:

~~~text
/subscriptions/<subscription-id>/resourceGroups/<rg-name>/providers/Microsoft.Storage/storageAccounts/<account-name>
~~~

Role assignment có thể cần thời gian để lan truyền. Nếu sau khi cấp quyền request chưa hoạt động, kiểm tra thời gian, scope, principal thực tế và response của dịch vụ trước khi thử lại có kiểm soát.

**Nguyên tắc phân quyền:** không cấp **Owner/Contributor** trên toàn subscription chỉ để một service ghi blob. Một application có thể cần quyền **Storage Blob Data Contributor** ở storage account test và quyền **Azure Service Bus Data Sender** ở namespace/queue được chỉ định, nhưng không cần quyền quản lý mọi resource.

### Kiểm tra role assignment

~~~bash
az role assignment list   --assignee "<managed-identity-principal-id>"   --scope "<storage-account-resource-id>"   --include-inherited   --output table
~~~

Kết quả phải được đối chiếu với phạm vi và role thực tế. Quyền có thể được cấp ở scope cha hoặc theo cơ chế riêng của dịch vụ. Với Azure Cosmos DB for NoSQL, authorization data plane cần phân tích mô hình role đặc thù của Cosmos DB thay vì suy luận mọi quyền từ Azure RBAC quản lý tài nguyên.

## 8. Managed identity vận hành trong Spring Boot như thế nào?

Trong Azure runtime, Azure Identity SDK dùng cơ chế managed identity mà nền tảng cung cấp để lấy token. SDK tự gọi endpoint/token broker thích hợp của môi trường; ứng dụng không cần truy cập thủ công metadata endpoint hoặc tự phân tích token.

~~~mermaid
sequenceDiagram
    participant A as Spring Boot app
    participant C as ManagedIdentityCredential
    participant M as Azure managed identity endpoint
    participant S as Blob Storage
    A->>C: Yêu cầu token cho Storage
    C->>M: Yêu cầu token của identity gắn với runtime
    M-->>C: Access token
    C-->>A: TokenCredential cung cấp token
    A->>S: Upload blob bằng HTTPS + token
    S-->>A: Cho phép hoặc từ chối theo RBAC/policy
~~~

### 8.1. Cấu hình Spring Cloud Azure

Với starter **com.azure.spring:spring-cloud-azure-starter-storage-blob** tương thích phiên bản Spring Boot, cấu hình cơ bản có thể là:

~~~yaml
spring:
  cloud:
    azure:
      storage:
        blob:
          account-name: ${AZURE_STORAGE_ACCOUNT}
~~~

Ví dụ ứng dụng inject **BlobServiceClient** được starter tự cấu hình:

~~~java
import com.azure.storage.blob.BlobServiceClient;
import com.azure.storage.blob.BlobContainerClient;
import org.springframework.stereotype.Service;

@Service
public class BlobContainerLocator {

    private final BlobServiceClient blobServiceClient;

    public BlobContainerLocator(BlobServiceClient blobServiceClient) {
        this.blobServiceClient = blobServiceClient;
    }

    public BlobContainerClient documents() {
        return blobServiceClient.getBlobContainerClient("documents");
    }
}
~~~

Đây là ví dụ **truy cập dữ liệu**, không phải tạo Azure storage account hay gán role. Khi starter dùng chuỗi credential mặc định theo phiên bản, managed identity được chọn nếu môi trường cung cấp identity thích hợp và các nguồn credential khác không làm thay đổi lựa chọn.

Nếu muốn ép dùng identity cụ thể, cần cấu hình credential/bean theo **phiên bản Spring Cloud Azure** đang sử dụng. Tránh đồng thời tạo thêm **BlobServiceClient** thủ công cùng kiểu khi starter đã tự cấu hình, trừ khi thiết kế bean được thực hiện rõ ràng.

### 8.2. Cấu hình Azure SDK trực tiếp

Nếu không dùng starter, ứng dụng có thể quản lý client SDK như bean Spring:

~~~java
import com.azure.core.credential.TokenCredential;
import com.azure.identity.ManagedIdentityCredentialBuilder;
import com.azure.storage.blob.BlobServiceClient;
import com.azure.storage.blob.BlobServiceClientBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class BlobClientConfiguration {

    @Bean
    public TokenCredential managedIdentityCredential(
            @Value("${app.azure.identity.client-id:}") String clientId) {

        ManagedIdentityCredentialBuilder builder =
                new ManagedIdentityCredentialBuilder();

        if (!clientId.isBlank()) {
            builder.clientId(clientId);
        }
        return builder.build();
    }

    @Bean
    public BlobServiceClient blobServiceClient(
            TokenCredential managedIdentityCredential,
            @Value("${app.azure.blob.endpoint}") String endpoint) {

        return new BlobServiceClientBuilder()
                .endpoint(endpoint)
                .credential(managedIdentityCredential)
                .buildClient();
    }
}
~~~

File cấu hình:

~~~yaml
app:
  azure:
    identity:
      client-id: ${AZURE_CLIENT_ID:}
    blob:
      endpoint: ${AZURE_BLOB_ENDPOINT}
~~~

Trường **client-id** để trống nếu dùng system-assigned managed identity và runtime tương thích. Với user-assigned identity, cung cấp đúng client ID của identity đã gắn. Endpoint Blob là thông tin đích và có thể thuộc subscription khác subscription chạy app; quyền vẫn gắn với identity trên tài nguyên đích.

## 9. Workload identity federation là gì?

**Workload identity federation** giải quyết bài toán: một workload nằm trong Kubernetes hoặc một hệ thống CI đã có bằng chứng danh tính từ identity provider đáng tin cậy; làm sao để workload truy cập Azure mà không phải lưu một client secret dài hạn?

Microsoft Entra thiết lập một **federated identity credential** gắn với application hoặc identity được hỗ trợ, xác định **issuer, subject và audience** đáng tin cậy. Workload nhận một token từ issuer, dùng token đó làm bằng chứng để đổi lấy Azure access token cho principal đã cấu hình.

~~~mermaid
sequenceDiagram
    participant W as AKS Pod / CI job
    participant O as OIDC issuer
    participant E as Microsoft Entra ID
    participant A as Azure managed service
    W->>O: Nhận OIDC token từ môi trường
    W->>E: Trao đổi OIDC token theo federated trust
    E-->>W: Access token cho identity được liên kết
    W->>A: Request Azure SDK với access token
    A-->>W: Đánh giá RBAC / policy và trả kết quả
~~~

Ba thuộc tính federation cần **khớp chính xác**:

| Thuộc tính | Ý nghĩa | Ví dụ AKS |
| --- | --- | --- |
| **Issuer** | Nguồn phát OIDC token được Entra tin cậy | OIDC issuer URL của cluster |
| **Subject** | Danh tính workload cụ thể được tin cậy | **system:serviceaccount:orders:orders-api** |
| **Audience** | Đối tượng của token dùng để trao đổi | **api://AzureADTokenExchange** trong thiết lập AKS phổ biến |

**Token OIDC của service account không phải access token để gọi Azure Blob trực tiếp.** Azure Identity đổi nó lấy token thích hợp qua Microsoft Entra; sau đó SDK gửi token tới dịch vụ Azure.

## 10. Thiết lập Microsoft Entra Workload ID trên AKS

Một quy trình điển hình gồm tạo/gắn user-assigned identity, bật OIDC issuer và workload identity ở AKS, thiết lập federated credential, khai báo Kubernetes service account, gán role dữ liệu rồi chạy Pod.

Các lệnh sau là **mẫu thao tác cho môi trường lab**, yêu cầu quyền quản trị Azure/AKS và thay thế mọi giá trị trong dấu **<...>**. Trước khi áp dụng lên cluster đã có workload, cần kiểm tra ảnh hưởng thay đổi và tài liệu đúng phiên bản AKS/CLI.

### 10.1. Bật OIDC issuer và workload identity

~~~bash
az aks update   --resource-group "<aks-resource-group>"   --name "<aks-cluster-name>"   --enable-oidc-issuer   --enable-workload-identity

# Đọc OIDC issuer URL thật từ AKS.
az aks show   --resource-group "<aks-resource-group>"   --name "<aks-cluster-name>"   --query "oidcIssuerProfile.issuerUrl"   --output tsv
~~~

Với cluster mới, có thể cấu hình các tính năng tương ứng trong bước tạo cluster. Việc bật trên cluster hiện có là **thay đổi cấu hình hạ tầng**; không thực hiện trên production khi chưa có quy trình thay đổi phù hợp.

### 10.2. Tạo user-assigned identity

~~~bash
az identity create   --resource-group "<identity-resource-group>"   --name "<orders-identity-name>"

az identity show   --resource-group "<identity-resource-group>"   --name "<orders-identity-name>"   --query "{clientId:clientId, principalId:principalId, id:id}"   --output json
~~~

Lưu **client ID** cho Kubernetes service account và **principal ID** cho RBAC. Không lưu secret vì user-assigned identity không đòi hỏi client secret để sử dụng trong workload federation được cấu hình đúng.

### 10.3. Tạo federated identity credential

~~~bash
az identity federated-credential create   --resource-group "<identity-resource-group>"   --identity-name "<orders-identity-name>"   --name "orders-api-federation"   --issuer "<aks-oidc-issuer-url>"   --subject "system:serviceaccount:orders:orders-api"   --audiences "api://AzureADTokenExchange"
~~~

Ở đây:

- **orders** là Kubernetes namespace.
- **orders-api** là tên Kubernetes service account.
- Nếu đổi namespace hoặc tên service account, **subject của federated credential phải được cập nhật**.
- Issuer phải là URL thực của cluster có bật OIDC issuer.
- Audience phải khớp với cấu hình federation của workload.

Bản ghi federation không tự cấp role dữ liệu Azure: vẫn cần role assignment cho principal ID của identity trên tài nguyên như Blob/Service Bus/Key Vault.

### 10.4. Khai báo Kubernetes service account và Pod

Ví dụ service account:

~~~yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: orders-api
  namespace: orders
  annotations:
    azure.workload.identity/client-id: "<user-assigned-identity-client-id>"
~~~

Pod template của Deployment cần gán đúng service account và label để webhook Workload ID xử lý:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-api
  namespace: orders
spec:
  replicas: 1
  selector:
    matchLabels:
      app: orders-api
  template:
    metadata:
      labels:
        app: orders-api
        azure.workload.identity/use: "true"
    spec:
      serviceAccountName: orders-api
      containers:
        - name: api
          image: "<container-registry>/orders-api:<image-tag>"
          ports:
            - containerPort: 8080
~~~

Đoạn YAML là khung triển khai để minh họa phần identity; production cần thêm health probes, resources, security context và cấu hình ứng dụng phù hợp.

Khi Pod được xử lý đúng bởi Workload ID, môi trường có thể được cung cấp những biến như:

~~~text
AZURE_CLIENT_ID=<client-id>
AZURE_TENANT_ID=<tenant-id>
AZURE_FEDERATED_TOKEN_FILE=<path-to-projected-oidc-token>
~~~

Các biến này là **đầu vào cho Azure Identity SDK**, không phải nơi đặt secret thủ công. Không tự copy token file vào image container, không đưa OIDC token vào log hoặc Git.

### 10.5. Java dùng WorkloadIdentityCredential

~~~java
import com.azure.core.credential.TokenCredential;
import com.azure.identity.WorkloadIdentityCredentialBuilder;

TokenCredential credential =
        new WorkloadIdentityCredentialBuilder().build();
~~~

Trong môi trường đã thiết lập đúng biến/token file ở trên, builder có thể lấy thông tin từ môi trường. Nếu SDK version yêu cầu cấu hình tường minh hoặc tên biến khác, phải dùng API tương ứng với release đang triển khai.

Một ứng dụng có thể dùng **DefaultAzureCredential** để tận dụng hỗ trợ workload identity của phiên bản Azure Identity tương thích. Tuy vậy, nếu production yêu cầu chỉ sử dụng federation, **WorkloadIdentityCredential** tường minh giúp lỗi bộc lộ rõ khi thiếu cấu hình.

**Điểm cần tránh:** cho Pod dùng danh tính node hay cache CLI rồi kết luận workload federation đã hoạt động. Integration test cần chứng minh request xuất phát từ identity được federated theo đúng service account.

## 11. Workload identity trong CI/CD

Nhiều hệ thống CI có thể phát **OIDC token** cho job. Microsoft Entra có thể tin cậy issuer/subject/audience được giới hạn theo repository, branch, environment hoặc loại job, tùy nhà cung cấp CI.

Ví dụ tư duy triển khai:

1. Đăng ký ứng dụng hoặc tạo danh tính Entra được hỗ trợ cho CI.
2. Cấu hình **federated identity credential** gắn với đối tượng CI cụ thể.
3. Cho job quyền yêu cầu OIDC token theo cơ chế provider.
4. Sử dụng cơ chế đăng nhập Azure hỗ trợ federation trong job.
5. Chỉ cấp quyền **deploy** nếu job cần triển khai; dùng identity/quyền khác cho integration test nếu cần truy cập dữ liệu.
6. Kiểm tra JVM test thực sự sử dụng credential source đã cấu hình.

Nếu dùng GitHub Actions, job thường cần permission **id-token: write** để nhận OIDC token, và giải pháp đăng nhập Azure tương thích OIDC. Nhưng các chi tiết của action/phiên bản, claim subject và môi trường tổ chức phải được xác minh theo tài liệu hiện hành trước khi triển khai.

**Một lỗi kiến trúc phổ biến:** pipeline đăng nhập Azure CLI thành công rồi chạy integration test Java với **DefaultAzureCredential**, nhưng SDK chọn một nguồn environment credential khác; test dùng sai principal. Muốn xác định được danh tính, hãy chọn credential cụ thể cho test hoặc kiểm soát danh sách credential sources và quan sát source thực sự được dùng.

### Deploy identity khác runtime identity

| Danh tính | Quyền cần có | Không nên cấp mặc định |
| --- | --- | --- |
| **CI deployer** | Quyền cập nhật App Service/AKS resource hoặc deploy artifact theo scope cần thiết | Quyền đọc mọi secret và dữ liệu production |
| **Spring Boot runtime** | Quyền dữ liệu tối thiểu trên Blob, Service Bus, Key Vault hoặc Cosmos tương ứng | Quyền Owner trên subscription |
| **Integration test** | Quyền trên tài nguyên thử nghiệm và cleanup test data | Quyền thao tác production ngoài mục tiêu test |

Nếu một pipeline cần cả triển khai và kiểm thử, cân nhắc sử dụng các job/identity riêng, scope cụ thể và điều kiện môi trường phù hợp.

## 12. Chọn Azure Identity credential trong ứng dụng Spring Boot

### 12.1. Bảng quyết định

| Môi trường | Credential nên cân nhắc | Điều kiện bắt buộc |
| --- | --- | --- |
| Laptop developer | **AzureCliCredential** hoặc DefaultAzureCredential có kiểm soát | Developer đã đăng nhập, có role trên tài nguyên dev |
| App Service/VM/Functions có identity | **ManagedIdentityCredential** | Identity gắn vào runtime và có role trên resource |
| AKS có Entra Workload ID | **WorkloadIdentityCredential** | Service account, pod label, OIDC/federation và RBAC đúng |
| CI có OIDC | Credential/phương án đăng nhập được CI provider hỗ trợ | Federated trust + job token + role scope rõ ràng |
| Môi trường hỗn hợp dùng chuỗi credential | **DefaultAzureCredential** | Chấp nhận được các nguồn và đã xác minh danh tính được chọn |

**DefaultAzureCredential** là lựa chọn tiện lợi khi di chuyển giữa môi trường, nhưng nó **không phải cam kết chọn đúng danh tính nghiệp vụ**. Khi tính xác định quan trọng, hãy cấu hình credential tường minh và để deployment cung cấp thông tin tương ứng.

### 12.2. Ví dụ factory credential theo environment

~~~java
import com.azure.core.credential.TokenCredential;
import com.azure.identity.AzureCliCredentialBuilder;
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.identity.ManagedIdentityCredentialBuilder;
import com.azure.identity.WorkloadIdentityCredentialBuilder;

public final class AzureIdentityFactory {

    private AzureIdentityFactory() {}

    public static TokenCredential create(
            String mode, String managedIdentityClientId) {

        switch (mode) {
            case "cli":
                return new AzureCliCredentialBuilder().build();

            case "managed":
                ManagedIdentityCredentialBuilder managed =
                        new ManagedIdentityCredentialBuilder();
                if (managedIdentityClientId != null &&
                        !managedIdentityClientId.isBlank()) {
                    managed.clientId(managedIdentityClientId);
                }
                return managed.build();

            case "workload":
                return new WorkloadIdentityCredentialBuilder().build();

            case "default":
                return new DefaultAzureCredentialBuilder().build();

            default:
                throw new IllegalArgumentException(
                        "Unknown Azure identity mode: " + mode);
        }
    }
}
~~~

Đây là factory minh họa; trong ứng dụng Spring Boot, có thể expose kết quả dưới dạng **@Bean TokenCredential** và inject cho client SDK. Các mode này phải được quyết định ở tầng triển khai/cấu hình đã tin cậy; không cho người gọi API chọn identity tùy ý.

### 12.3. Kết nối với Azure SDK

~~~java
import com.azure.core.credential.TokenCredential;
import com.azure.storage.blob.BlobServiceClient;
import com.azure.storage.blob.BlobServiceClientBuilder;

TokenCredential credential =
        AzureIdentityFactory.create("managed", System.getenv("AZURE_CLIENT_ID"));

BlobServiceClient blobServiceClient = new BlobServiceClientBuilder()
        .endpoint("https://<account-name>.blob.core.windows.net")
        .credential(credential)
        .buildClient();
~~~

Chỉ dùng cách này khi chạy trong **môi trường đã cung cấp managed identity**. Với local developer, chọn mode **cli**; với AKS Workload ID, chọn **workload** sau khi OIDC và projected token được cấu hình đúng.

Trong môi trường Spring Cloud Azure starter, có thể dùng auto-configuration để tạo client; khi cần sử dụng bean tự tạo, phải kiểm soát xung đột bean và thuộc tính credential theo version Spring Cloud Azure.

## 13. Kiểm thử: chứng minh đúng danh tính, đúng quyền

Một bài kiểm thử tốt phải phân biệt được **build thành công**, **client tạo được**, **lấy token được** và **thao tác dữ liệu thực sự thành công**.

### 13.1. Unit test

- Mock adapter quanh Azure SDK hoặc client phù hợp với kiến trúc.
- Kiểm tra behavior nghiệp vụ khi upload thành công, timeout, conflict và lỗi quyền.
- Không dùng Azure CLI cache hoặc credential production trong unit test.
- Không cần gọi live Azure service để chứng minh xử lý nghiệp vụ.

### 13.2. Local integration test

- Dùng tài nguyên Azure dev và danh tính dev được cấp role cụ thể.
- Nếu dùng **Azurite** cho Blob, ghi rõ rằng emulator không kiểm chứng Microsoft Entra managed identity, OIDC federation hay Azure RBAC thật.
- Kiểm tra endpoint được chọn và khả năng thao tác trên container thử nghiệm, không truy cập dữ liệu thật ngoài scope test.

### 13.3. Cloud integration test

Với App Service hoặc AKS:

1. Chạy bằng identity runtime dự kiến, không dùng tài khoản developer.
2. Kiểm tra danh tính/nguồn credential bằng diagnostics được phép.
3. Thực hiện một thao tác nhỏ trên resource test, ví dụ upload blob có tên riêng.
4. Thử một tình huống thiếu quyền trên tài nguyên test để nhận diện lỗi authorization.
5. Xóa dữ liệu thử nghiệm và lưu request/correlation ID cho việc điều tra.

**Không chỉ kiểm tra Spring context khởi động.** Nhiều client Azure được dựng mà không liên lạc với dịch vụ; lỗi credential/RBAC có thể chỉ xuất hiện ở request đầu tiên.

## 14. Xử lý sự cố theo tầng

| Triệu chứng | Nguyên nhân thường gặp | Điều cần kiểm tra |
| --- | --- | --- |
| Local **az login** thành công, ứng dụng không lấy được token | Azure CLI không phải source SDK đang chọn hoặc process không có CLI/session phù hợp | Credential chain, môi trường chạy, Azure Identity diagnostics |
| **az login --identity** thất bại trên laptop | Laptop không chạy trong managed identity-enabled Azure host | Dùng user login trên local; chỉ dùng --identity ở runtime được hỗ trợ |
| App Service nhận **CredentialUnavailableException** | Chưa bật identity hoặc SDK không phát hiện managed identity endpoint | Identity của App Service, runtime configuration, SDK version |
| User-assigned identity bị chọn sai | Nhầm client ID với principal ID hoặc gắn sai identity | Client ID khi tạo credential, principal ID khi cấp RBAC |
| Pod AKS không có token file federation | Thiếu Pod label, service-account annotation hoặc Workload ID wiring | Pod spec, service account, webhook, token projection |
| OIDC exchange bị từ chối | Issuer/subject/audience hoặc client/tenant không khớp | Federated credential trong Entra và token metadata |
| SDK lấy token được nhưng Blob trả **403** | Principal thiếu role, scope sai hoặc storage network policy | Role data plane, resource đích, firewall/Private Endpoint |
| Service Bus sender báo không được phép | Thiếu role **Azure Service Bus Data Sender**, sai namespace/entity | Namespace endpoint, principal và role gửi |
| Key Vault báo 403 | Vault permission model, thiếu quyền secret, sai principal | Key Vault RBAC/access policy theo cấu hình vault |
| Timeout khi gọi Azure | DNS, proxy, outbound route hoặc Private Endpoint | Reachability từ chính workload, không chỉ từ máy dev |
| Role đã gán nhưng chưa có hiệu lực ngay | Độ trễ propagation hoặc token/role state chưa cập nhật | Scope, principal, thời gian, test lại có kiểm soát |

### Quy trình debug có thứ tự

~~~mermaid
flowchart TD
    A[Request Azure thất bại] --> B{Đúng endpoint chưa?}
    B -->|Chưa| C[Sửa URL / account / namespace]
    B -->|Rồi| D{Có lấy được token?}
    D -->|Không| E[Kiểm tra credential source và identity setup]
    D -->|Có| F{Principal đúng chưa?}
    F -->|Không| G[Chọn identity tường minh]
    F -->|Có| H{Đủ quyền / mạng?}
    H -->|Không| I[Kiểm tra RBAC, scope, DNS, firewall]
    H -->|Có| J[Kiểm tra retry, throttling, service errors]
~~~

Cần phân biệt lỗi **credential chain**, **authentication**, **authorization** và **network**. Không sửa version SDK một cách ngẫu nhiên khi lỗi rõ ràng liên quan role assignment hoặc Private Endpoint.

### Logging an toàn

Để kiểm tra SDK credential source, dùng logging chẩn đoán của **azure-identity** theo version và phạm vi được phép. Có thể ghi:

- Tên operation, endpoint hostname, mã lỗi và request/correlation ID.
- Loại credential đang được thử hoặc được chọn.
- Thông tin định danh tối thiểu đã được che/masking theo quy định nội bộ.

**Không ghi access token, OIDC token file, client secret, certificate private key, connection string, SAS URL hoặc toàn bộ biến môi trường.** Tránh in chi tiết JWT ra log chỉ để xem principal; dùng công cụ chẩn đoán được cấp phép và chỉ giữ thông tin cần thiết.

## 15. Bảo mật và vận hành

1. **Quyền tối thiểu:** gán role data plane ở scope nhỏ nhất hỗ trợ nhu cầu của ứng dụng.
2. **Tách danh tính:** dev, CI deployer, integration test và production runtime dùng principal riêng khi phù hợp.
3. **Không lưu secret dài hạn:** ưu tiên managed identity hoặc federation; nếu buộc dùng client secret/certificate, quản lý qua kho bí mật và rotation theo chính sách.
4. **Kiểm soát OIDC trust:** giới hạn chính xác issuer, subject, audience, repo/branch/environment; không mở trust cho mọi workflow.
5. **Quản lý vòng đời identity:** kiểm tra role assignment cũ khi thay workload, xóa identity hoặc chuyển môi trường.
6. **Tránh fallback không mong muốn:** production có yêu cầu principal xác định nên dùng credential tường minh hoặc giới hạn chain.
7. **Kiểm tra dữ liệu và mạng:** role đúng nhưng private DNS/firewall sai vẫn khiến hệ thống không hoạt động.
8. **Audit thường xuyên:** theo dõi role assignment, access log và identity sử dụng trên resource quan trọng.

## 16. Liên hệ với AWS và Google Cloud

| Nhu cầu | Azure | AWS | Google Cloud |
| --- | --- | --- | --- |
| CLI cho nhà phát triển | Azure CLI **az login** | AWS CLI/profile/SSO | gcloud CLI |
| Credential discovery trong Java | Azure Identity **DefaultAzureCredential** | AWS SDK v2 **DefaultCredentialsProvider** | Application Default Credentials |
| Danh tính cho workload cloud | System/user-assigned managed identity | IAM role với temporary credentials | Service account / workload identity |
| Kubernetes workload federation | Microsoft Entra Workload ID cho AKS | IRSA / các mô hình workload identity phù hợp với EKS | Workload Identity Federation cho GKE |
| CI federation | OIDC token trao đổi với Microsoft Entra | OIDC → STS/AssumeRole | OIDC → Workload Identity Federation |
| Quyền dữ liệu | Azure RBAC hoặc quyền theo dịch vụ | IAM/resource policies | Cloud IAM |

Đây là **so sánh khái niệm**, không phải ánh xạ một-một về quyền hoặc API. Mỗi provider có cơ chế riêng để xác nhận issuer, audience, scope và tài nguyên. Khi xây lớp abstraction đa cloud cho storage/messaging, cần giữ rõ **credential provider**, **resource locator**, **authorization model** và **lifecycle** của danh tính.

## 17. Bài tập thực hành theo ba môi trường

**Bối cảnh:** ứng dụng Spring Boot lưu tài liệu vào Blob container private **documents** và phát sự kiện vào Service Bus sau khi upload thành công.

### Phần A — Developer với Azure CLI

1. Đăng nhập vào tenant lab bằng **az login** và xác nhận subscription với **az account show**.
2. Xác minh storage account và endpoint bằng **az storage account show**.
3. Cấp role dữ liệu cần thiết cho tài khoản dev ở resource test.
4. Chạy ứng dụng với **AzureCliCredential**, upload một Blob và kiểm tra log không chứa token.
5. Thu hồi quyền ghi ở môi trường test, quan sát lỗi rồi khôi phục quyền phù hợp.

### Phần B — App Service với managed identity

1. Bật system-assigned managed identity hoặc gắn user-assigned managed identity.
2. Lấy đúng **principal ID** và gán role Blob Data Contributor, Service Bus Data Sender ở resource đích.
3. Cấu hình managed identity credential, endpoint Blob và namespace Service Bus.
4. Triển khai cùng nghiệp vụ, kiểm thử upload và gửi message; bảo đảm runtime không phụ thuộc Azure CLI.
5. Giải thích vì sao application deploy được chưa đồng nghĩa có quyền data plane.

### Phần C — AKS với Workload ID

1. Bật OIDC issuer và Workload Identity nếu cluster lab đã được phép thay đổi.
2. Tạo user-assigned identity, thiết lập federated credential cho Kubernetes service account.
3. Gán annotation, Pod label và service account đúng trong Deployment.
4. Cấp quyền cho principal ID trên Blob/Service Bus test resource.
5. Chạy ứng dụng với **WorkloadIdentityCredential** và xác nhận request thành công.
6. Cố tình thay subject ở môi trường lab để quan sát lỗi token exchange, sau đó khôi phục cấu hình.

**Sản phẩm cần nộp:** bảng mỗi môi trường gồm **credential type**, **client/principal ID** (không kèm bí mật), **resource endpoint**, **RBAC scope**, **kết quả test**, **nguồn thông tin chẩn đoán** và **phương án rollback**.

### Câu hỏi tự kiểm tra

1. Vì sao Azure CLI đã đăng nhập không chứng minh một App Service được xác thực?
2. Khác biệt vòng đời của system-assigned và user-assigned managed identity là gì?
3. Khi nào cần client ID và khi nào cần principal ID?
4. Tại sao phải gán role data plane dù identity đã lấy được token?
5. Ba thuộc tính nào phải khớp giữa AKS service account token và federated credential?
6. Vì sao CI có thể dùng OIDC nhưng Java process vẫn xác thực nhầm principal?
7. Một integration test với Azurite chứng minh được gì, và chưa chứng minh được gì?
8. Lỗi 403 nên được phân tích khác với CredentialUnavailableException như thế nào?

## 18. Ghi nhớ

- **Azure CLI** phục vụ thao tác quản trị và phát triển; **managed identity** phục vụ workload trên Azure; **workload identity federation** cho phép workload như AKS/CI đổi OIDC token lấy Azure access token mà không cần client secret dài hạn.
- Mỗi môi trường phải xác định **principal thực tế**, **credential source**, **resource endpoint**, **role/scope** và **network**. Có token hợp lệ chưa đủ để truy cập dữ liệu.
- Với Spring Boot, có thể dùng **Spring Cloud Azure starter** để tự cấu hình client, hoặc dùng trực tiếp **Azure SDK + TokenCredential** khi cần điều khiển cách chọn identity.
- Trong production, ưu tiên managed/workload identity và giảm ambiguity của credential chain bằng cấu hình tường minh khi cần.
- Kiểm thử thực tế trên tài nguyên test, bảo vệ token/secret và phân biệt rõ lỗi xác thực, ủy quyền, endpoint và hạ tầng mạng.

## Tài liệu tham khảo

- [Authenticate to Azure using Azure CLI](https://learn.microsoft.com/cli/azure/authenticate-azure-cli)
- [Managed identities for Azure resources](https://learn.microsoft.com/entra/identity/managed-identities-azure-resources/overview)
- [Assign Azure roles using Azure CLI](https://learn.microsoft.com/azure/role-based-access-control/role-assignments-cli)
- [Microsoft Entra Workload ID for AKS](https://learn.microsoft.com/azure/aks/workload-identity-overview)
- [Deploy and configure workload identity on AKS](https://learn.microsoft.com/azure/aks/workload-identity-deploy-cluster)
- [Azure Identity SDK authentication for Java](https://learn.microsoft.com/azure/developer/java/sdk/authentication/overview)
- [Spring Cloud Azure](https://learn.microsoft.com/azure/developer/java/spring-framework/)
