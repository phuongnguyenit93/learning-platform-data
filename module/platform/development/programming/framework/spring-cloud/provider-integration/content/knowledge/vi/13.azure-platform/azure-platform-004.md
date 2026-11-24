# DefaultAzureCredential và lựa chọn danh tính trong từng môi trường

Khi ứng dụng Spring Boot truy cập Azure Blob Storage, Service Bus, Key Vault hoặc Cosmos DB, câu hỏi đầu tiên không chỉ là “điền khóa nào vào **application.yml**?”. Ứng dụng phải biết **nó đang chạy với danh tính nào**, danh tính ấy lấy token theo cách nào và có được cấp quyền trên tài nguyên đích hay không.

**DefaultAzureCredential** của **Azure Identity SDK for Java** cung cấp một chuỗi nguồn credential phù hợp với các môi trường phát triển và triển khai khác nhau. Nhờ đó, cùng một phần lớn mã gọi Azure SDK có thể chạy trên máy lập trình viên, CI và Azure runtime. Tuy nhiên, tính thuận tiện này đòi hỏi hiểu rõ cơ chế chọn danh tính để không vô tình dùng sai principal hoặc vượt quá quyền cần thiết.

Bài học thuộc chương **Nền tảng Azure** của module **SPRING_CLOUD_PROVIDER_INTEGRATION**: thực hành tích hợp Spring Boot với các dịch vụ managed của AWS, Azure và Google Cloud thông qua thư viện Spring Cloud tương ứng; trọng tâm là danh tính và quyền, storage, messaging, dữ liệu, quản lý secret, kiểm thử tích hợp và đánh giá khác biệt giữa các cloud provider.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích **TokenCredential**, access token và vai trò của **DefaultAzureCredential** trong Azure SDK for Java.
2. Phân biệt user identity, service principal, system-assigned managed identity, user-assigned managed identity và workload identity.
3. Chọn phương án xác thực cho máy phát triển, CI/CD, App Service/VM/Functions, AKS và workload ngoài Azure.
4. Dùng cùng một kiến trúc Spring Boot với **Spring Cloud Azure** hoặc **Azure SDK trực tiếp**, đưa endpoint và lựa chọn danh tính vào cấu hình.
5. Phân biệt lỗi **không lấy được token**, **lấy token cho sai danh tính**, **thiếu Azure RBAC** và **lỗi mạng/endpoint**.
6. Kiểm thử tích hợp theo danh tính thật mà không nhúng client secret, access key hoặc token vào mã nguồn.

## 2. Bốn lớp cần tách biệt

Xét ứng dụng **Documents API** ghi tệp vào Azure Blob Storage:

~~~mermaid
flowchart LR
    A[Spring Boot Documents API] --> B[Azure SDK BlobServiceClient]
    B --> C[TokenCredential]
    C --> D[Microsoft Entra ID]
    B --> E[Blob Storage endpoint]
    F[Azure RBAC trên storage account / container] -.-> E
    G[Firewall / VNet / Private Endpoint] -.-> E
~~~

Ứng dụng thành công khi cả bốn điều kiện phù hợp:

| Lớp | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Đích** | Client gọi đúng tài nguyên chưa? | **https://stexample.blob.core.windows.net** |
| **Xác thực** (authentication) | Credential có lấy được token thích hợp không? | Managed identity, Azure CLI, workload identity |
| **Ủy quyền** (authorization) | Principal được phép làm thao tác đó không? | Role **Storage Blob Data Contributor** trên tài nguyên phù hợp |
| **Mạng** | Runtime có truy cập được endpoint theo chính sách không? | DNS, firewall, private endpoint, proxy, TLS |

**Một token hợp lệ không đồng nghĩa có quyền ghi Blob.** Tương tự, đã được gán role đúng vẫn có thể gặp timeout nếu endpoint sai hoặc private DNS chưa hoạt động.

Một số Azure SDK cũng hỗ trợ **connection string**, **shared key** hoặc **SAS**. Các cơ chế này có ngữ nghĩa và rủi ro riêng; trong bài này ưu tiên **Microsoft Entra token** thông qua **TokenCredential** để kiểm soát quyền theo danh tính.

## 3. TokenCredential và DefaultAzureCredential là gì?

**TokenCredential** là abstraction trong Azure SDK nhận yêu cầu token cho một hoặc nhiều scope và trả về access token nếu xác thực thành công. Các client SDK như **BlobServiceClient** có thể dùng một **TokenCredential** mà không phải biết chi tiết mã nguồn đăng nhập.

Các kiểu triển khai thường gặp:

| Credential | Nguồn danh tính | Khi nào phù hợp |
| --- | --- | --- |
| **DefaultAzureCredential** | Thử một chuỗi nguồn credential được hỗ trợ | Phát triển và cấu hình chung giữa nhiều môi trường, khi kiểm soát được nguồn credential |
| **AzureCliCredential** | Phiên đăng nhập Azure CLI của người đang phát triển | Công cụ/lab cục bộ, cần chọn rõ Azure CLI |
| **ManagedIdentityCredential** | Managed identity gắn với tài nguyên Azure hỗ trợ | Azure runtime, muốn ép rõ đường đăng nhập managed identity |
| **WorkloadIdentityCredential** | Liên kết tin cậy OIDC với một workload và Entra ID | AKS hoặc workload có cơ chế federation phù hợp |
| **EnvironmentCredential** | Biến môi trường theo một hình thức xác thực được SDK hỗ trợ | Môi trường đã quản lý credential rõ ràng; lưu ý nguy cơ dùng client secret |
| **ClientSecretCredential** | Tenant ID, client ID và client secret | Chỉ khi chưa thể dùng managed/workload identity; phải quản lý và luân chuyển secret an toàn |
| **ClientCertificateCredential** | Chứng chỉ của ứng dụng | Workload có PKI và quản lý vòng đời chứng chỉ phù hợp |

**DefaultAzureCredential** kết hợp một số nguồn trong danh sách trên và có thể cả tích hợp IDE/CLI khác. **Thứ tự, các nguồn khả dụng và quy tắc tiếp tục hay dừng khi một nguồn lỗi có thể thay đổi theo phiên bản Azure Identity SDK**. Vì thế không nên chép một danh sách thứ tự cố định từ ví dụ cũ rồi xem đó là hợp đồng bảo mật lâu dài.

### Credential chain chọn danh tính ra sao?

~~~mermaid
flowchart TD
    A[DefaultAzureCredential] --> B{Có nguồn credential hợp lệ?}
    B -->|Không| C[CredentialUnavailable / AuthenticationFailed]
    B -->|Có| D[Lấy token cho principal được chọn]
    D --> E[Azure SDK gửi request tới dịch vụ]
    E --> F{Được phép trên tài nguyên đích?}
    F -->|Có| G[Thao tác thành công]
    F -->|Không| H[401 / 403 hoặc lỗi quyền tương ứng]
~~~

Đây là **sơ đồ khái niệm**. Trong quá trình thử nguồn, SDK phân biệt nguồn không khả dụng với nguồn đã thử xác thực nhưng thất bại; quy tắc fallback có thể phụ thuộc bản SDK và loại nguồn credential. Đừng mặc định SDK sẽ luôn tiếp tục đến Azure CLI sau khi một credential triển khai đã xác thực thất bại.

**Điểm quan trọng:** credential chain không kiểm tra “danh tính nào có nhiều quyền nhất” hoặc “danh tính nào đúng với business environment” để tự lựa chọn. Nó vận hành theo thứ tự và điều kiện đã cấu hình. Ứng dụng phải kiểm soát danh tính được phép sử dụng.

## 4. Những danh tính thường gặp trên Azure

### 4.1. Danh tính người dùng trên máy phát triển

Một lập trình viên có thể đăng nhập bằng **az login** hoặc IDE được Azure Identity hỗ trợ. Azure CLI lưu phiên đăng nhập để **AzureCliCredential** yêu cầu token khi cần.

Lợi ích: không cần phát một client secret riêng cho từng người. Nhưng quyền của developer phải được cấp cho **tài nguyên test**, và không nên phụ thuộc vào tài khoản cá nhân để chạy workload sản xuất.

### 4.2. Service principal

**Service principal** là biểu diễn danh tính ứng dụng trong tenant Microsoft Entra. Nó có **object/principal ID**, được gán role trên tài nguyên, và có thể dùng nhiều hình thức xác thực: secret, certificate hoặc **federated credential**.

Cần phân biệt:

- **Tenant ID:** tenant phát token/định danh principal.
- **Client ID:** định danh ứng dụng/identity được chọn để xác thực.
- **Principal/Object ID:** đối tượng thực tế thường được dùng khi gán hoặc tra role.
- **Client secret:** bí mật xác thực, **không phải** client ID và không nên xuất hiện trong repository.

Một service principal dùng client secret có thể hoạt động nhưng tạo chi phí bảo vệ, rotation và quản lý lộ lọt secret. Khi có điều kiện, nên dùng federation hoặc managed identity.

### 4.3. System-assigned managed identity

**System-assigned managed identity** gắn với vòng đời của một tài nguyên Azure có hỗ trợ loại identity đó. Azure quản lý thông tin xác thực nền, ứng dụng lấy token qua cơ chế managed identity của runtime; không cần lưu client secret.

Ví dụ: một App Service được bật system-assigned identity, rồi được gán role ghi Blob trên storage account đích. Nếu tài nguyên bị xóa, danh tính system-assigned có thể bị xóa theo.

### 4.4. User-assigned managed identity

**User-assigned managed identity** là một Azure resource độc lập, có thể gán cho nhiều tài nguyên hỗ trợ. Vòng đời của nó tách khỏi từng workload.

Khi một runtime có nhiều identity hoặc cần chỉ rõ identity, ứng dụng có thể cung cấp **client ID** của user-assigned managed identity. Không nhầm **client ID** với **principal ID** khi chọn credential hay khi gán role.

**Lưu ý:** Managed identity tồn tại được không có nghĩa mọi môi trường đều có endpoint lấy token managed identity; phải gắn identity vào runtime có hỗ trợ và kiểm tra cấu hình của dịch vụ hosting.

### 4.5. Workload identity federation

**Federated workload identity** cho phép một workload có token từ identity provider đáng tin cậy (thường theo OIDC) đổi lấy Microsoft Entra access token, tránh lưu client secret dài hạn.

Hai tình huống tiêu biểu:

- **AKS với Microsoft Entra Workload ID:** service account Kubernetes và cấu hình federation liên kết workload với Entra application hoặc user-assigned managed identity.
- **CI/CD như GitHub Actions hoặc Azure DevOps:** danh tính job/pipeline được liên kết với Entra qua trust và các claim giới hạn đối tượng/nhánh/môi trường phù hợp.

Đây là cơ chế **federation**, không giống việc cho mọi container tự động dùng managed identity của node/cluster. Phải cấu hình issuer, subject, audience, service account hoặc pipeline identity đúng với nguồn token thực tế.

## 5. Chọn danh tính theo môi trường

| Môi trường | Lựa chọn ưu tiên thường gặp | Nguồn trong Azure Identity | Quyền và rủi ro cần kiểm soát |
| --- | --- | --- | --- |
| **Máy lập trình viên** | Tài khoản developer qua Azure CLI/IDE | **DefaultAzureCredential** hoặc **AzureCliCredential** | Chỉ cấp quyền vào tài nguyên dev; cảnh giác biến môi trường credential còn sót |
| **CI/CD có OIDC federation** | Service principal hoặc managed identity được cấu hình federated credential | Workload federation, đôi khi do bước CI login cung cấp cho CLI | Giới hạn trust theo repo/branch/environment; tách quyền deploy và quyền dữ liệu |
| **App Service / Azure Functions** | System-assigned hoặc user-assigned managed identity | **ManagedIdentityCredential** hoặc DefaultAzureCredential | Gán role data plane trên tài nguyên đích, không chỉ quyền management |
| **Azure VM / workload hỗ trợ managed identity** | Managed identity được gắn vào runtime | **ManagedIdentityCredential** | Không dựa vào Azure CLI hoặc file credential cá nhân trong sản xuất |
| **AKS có Workload ID** | Workload identity federation theo Kubernetes service account | **WorkloadIdentityCredential** hoặc DefaultAzureCredential nếu cấu hình tương ứng | Kiểm tra service-account annotation, pod mutation, federated credential và role |
| **Container/host ngoài Azure** | Federation nếu nền tảng hỗ trợ, nếu không dùng credential tổ chức quản lý | Credential thích hợp với môi trường | Không giả định managed identity tự hoạt động ngoài Azure |
| **Test tự động cục bộ** | Fake/mock credential cho unit test; identity lab cho integration test | Mock **TokenCredential** hoặc credential môi trường lab | Tách tài nguyên test; không phụ thuộc tài khoản cá nhân trong CI |

**Nguyên tắc lựa chọn:** ưu tiên danh tính không cần lưu secret dài hạn; cấp quyền ở **scope nhỏ nhất**; xác định rõ principal của mỗi môi trường.

### DefaultAzureCredential có nên dùng trong production?

Có thể dùng nếu môi trường được cấu hình chặt chẽ và đã xác minh nguồn credential thực sự được chọn. Tuy nhiên, với workload production cần đường đăng nhập xác định, dùng **ManagedIdentityCredential** hoặc **WorkloadIdentityCredential** tường minh có thể giúp giảm ambiguity.

**DefaultAzureCredential không phải cơ chế khóa cứng identity.** Ví dụ một container có biến môi trường cho service principal ngoài ý muốn có thể khiến chain chọn credential khác với managed identity dự kiến. Khi chính sách đòi hỏi principal xác định, hãy chọn credential cụ thể hoặc cấu hình loại trừ các nguồn không cho phép theo API phiên bản SDK đang sử dụng.

## 6. Lựa chọn tenant, subscription và principal

Trước khi cấu hình credential, cần tránh ba nhầm lẫn phổ biến:

1. **Tenant ID** xác định không gian danh tính Microsoft Entra.
2. **Subscription ID** xác định phạm vi quản trị/triển khai/billing của Azure Resource Manager.
3. **Client ID** xác định ứng dụng hoặc user-assigned identity muốn dùng để xác thực.

Ví dụ, ứng dụng chạy trong subscription **app-prod**, Blob Storage nằm trong subscription **data-prod**, nhưng cả hai thuộc cùng tenant. Managed identity của app vẫn có thể được gán role **Storage Blob Data Contributor** cho storage account ở **data-prod**. Khi đó Blob SDK cần **endpoint account + credential đúng + role + mạng**, không cần truyền subscription ID vào từng lệnh upload.

Ngược lại, khi dùng Azure Resource Manager SDK để **tạo storage account**, cần xác định subscription/resource group và quyền management plane tương ứng.

**Tương tác đa tenant** cần thiết kế rõ quyền truy cập và cơ chế federation/ủy quyền; không mặc định identity của tenant A gọi được data plane ở tenant B chỉ vì có endpoint.

### Cấu hình theo scope, không theo tên người dùng

Một role assignment thường liên kết:

~~~text
Principal (định danh người dùng/workload)
           +
Role definition (quyền được phép)
           +
Scope (management group / subscription / resource group / resource)
           =
Quyền được áp dụng trong phạm vi tương ứng
~~~

Một số dịch vụ có cơ chế ủy quyền data plane bổ sung hoặc riêng; chẳng hạn Azure Cosmos DB for NoSQL cần xét mô hình data-plane RBAC của chính dịch vụ. Vì vậy “Contributor” quản trị tài nguyên không tự động đồng nghĩa được đọc mọi secret hoặc ghi mọi Blob.

## 7. Thực hành xác thực trên máy phát triển

Giả sử môi trường lab có tenant **11111111-1111-1111-1111-111111111111** và storage account **stexample**. GUID và account name chỉ là ví dụ; thay bằng giá trị test thực tế.

### 7.1. Đăng nhập Azure CLI

~~~bash
# Đăng nhập bằng tài khoản được cấp quyền vào tenant dev.
az login --tenant "11111111-1111-1111-1111-111111111111"

# Xem tenant và subscription Azure CLI đang dùng.
az account show --query "{tenant:tenantId, subscription:id, name:name}" --output json

# Nếu cần quản lý resource bằng CLI, chỉ định subscription tương ứng.
az account set --subscription "<subscription-id>"
~~~

**az account set** đổi ngữ cảnh subscription mặc định cho các lệnh CLI/ARM; nó không thay đổi hostname Blob đã hard-code hoặc cấu hình trước đó. Nếu dùng **DefaultAzureCredential**, IDE credential hoặc biến môi trường có thể được chọn trước Azure CLI theo chain của phiên bản SDK. Vì vậy **az login thành công không chứng minh ứng dụng đã dùng danh tính từ Azure CLI**.

### 7.2. Cấp quyền thử nghiệm

Trước khi upload, quản trị viên hoặc người có quyền gán role cần cấp role dữ liệu đúng scope cho principal đang sử dụng. Với nhu cầu ghi Blob:

- Role ví dụ: **Storage Blob Data Contributor**.
- Scope: container/account đích nếu mô hình role assignment và thao tác hỗ trợ; ưu tiên scope nhỏ nhất.
- Quyền mạng: storage firewall/private endpoint phải cho phép runtime dev hoặc môi trường test.

Sau khi cấp RBAC có thể có độ trễ truyền quyền. Nếu ứng dụng vẫn nhận 403, cần đối chiếu **principal thực tế** và chi tiết lỗi từ dịch vụ, thay vì chỉ kiểm tra rằng tài khoản cá nhân đã đăng nhập.

## 8. Cấu hình Azure SDK trực tiếp trong Spring Boot

Ví dụ ứng dụng Spring Boot 3.x lưu file trong Blob Storage. Dependency cần **azure-identity** và **azure-storage-blob**, dùng BOM tương thích để quản lý version, đồng thời có Spring Boot starter phù hợp cho ứng dụng. Ví dụ chỉ tập trung phần cấu hình identity/client.

### 8.1. application.yml và biến môi trường

~~~yaml
app:
  azure:
    blob:
      endpoint: ${AZURE_BLOB_ENDPOINT}
      container: ${AZURE_BLOB_CONTAINER:documents}
~~~

Ví dụ biến môi trường:

~~~text
AZURE_BLOB_ENDPOINT=https://stexample.blob.core.windows.net
AZURE_BLOB_CONTAINER=documents
~~~

Endpoint không chứa secret. Với Azure public cloud, Blob endpoint của account thường có dạng **https://{account}.blob.core.windows.net**. Ở sovereign cloud, custom domain hoặc private networking, phải dùng endpoint được dịch vụ công bố cho môi trường thực tế.

### 8.2. Tạo bean TokenCredential và BlobServiceClient

~~~java
import com.azure.core.credential.TokenCredential;
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.storage.blob.BlobServiceClient;
import com.azure.storage.blob.BlobServiceClientBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class AzureBlobConfiguration {

    @Bean
    public TokenCredential azureCredential() {
        return new DefaultAzureCredentialBuilder().build();
    }

    @Bean
    public BlobServiceClient blobServiceClient(
            TokenCredential azureCredential,
            @Value("${app.azure.blob.endpoint}") String endpoint) {

        return new BlobServiceClientBuilder()
                .endpoint(endpoint)
                .credential(azureCredential)
                .buildClient();
    }
}
~~~

Với mã này, cùng một **BlobServiceClient** gọi Azure SDK trong các môi trường khác nhau, trong khi **TokenCredential** giải quyết phần lấy token. Tạo client thành công chưa xác nhận có quyền: cần thực hiện một request thử đến dịch vụ.

**Lưu ý khi dùng Spring Cloud Azure starter:** nếu starter đã tự cấu hình **BlobServiceClient** hoặc **TokenCredential** cùng kiểu, việc tạo thêm bean có thể gây ambiguity hoặc làm thay đổi auto-configuration. Hãy chọn một cơ chế tạo client rõ ràng, hoặc khai báo bean qualifier/primary có chủ đích.

### 8.3. Dịch vụ thao tác Blob

~~~java
import com.azure.storage.blob.BlobContainerClient;
import com.azure.storage.blob.BlobServiceClient;
import java.io.ByteArrayInputStream;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

@Service
public class DocumentStorageService {

    private final BlobContainerClient containerClient;

    public DocumentStorageService(
            BlobServiceClient blobServiceClient,
            @Value("${app.azure.blob.container}") String containerName) {

        this.containerClient =
                blobServiceClient.getBlobContainerClient(containerName);
    }

    public void upload(String blobName, byte[] content) {
        containerClient.getBlobClient(blobName).upload(
                new ByteArrayInputStream(content), content.length, false);
    }
}
~~~

Ví dụ cố ý dùng **overwrite=false** để tránh âm thầm thay nội dung đã tồn tại. Trong ứng dụng thật, cần kiểm soát tên blob, kích thước tệp, MIME type, cách đọc streaming và quyền của từng người dùng nghiệp vụ. Client SDK không tự tạo container và không tự cấp RBAC.

**Blob URL không đương nhiên là URL công khai.** Với container private, client đọc dữ liệu vẫn cần xác thực hoặc hình thức ủy quyền được cấp an toàn.

## 9. Spring Cloud Azure starter tự cấu hình credential như thế nào?

Nếu ứng dụng đã dùng starter **com.azure.spring:spring-cloud-azure-starter-storage-blob**, Spring Cloud Azure cung cấp auto-configuration để ứng dụng có thể inject client SDK. Ví dụ phần cấu hình thường gặp:

~~~yaml
spring:
  cloud:
    azure:
      storage:
        blob:
          account-name: ${AZURE_STORAGE_ACCOUNT}
~~~

Trong Azure public cloud, SDK/starter có thể xác định endpoint Blob từ account name theo cấu hình mặc định của phiên bản phù hợp. Với endpoint riêng, sovereign cloud, emulator hoặc danh tính đặc biệt, cần kiểm tra **thuộc tính cấu hình chính thức của đúng phiên bản Spring Cloud Azure**.

Một Spring service có thể nhận **BlobServiceClient**:

~~~java
import com.azure.storage.blob.BlobServiceClient;
import org.springframework.stereotype.Service;

@Service
public class BlobHealthProbe {

    private final BlobServiceClient client;

    public BlobHealthProbe(BlobServiceClient client) {
        this.client = client;
    }

    public String endpoint() {
        return client.getAccountUrl();
    }
}
~~~

Phương thức trên chỉ trả về endpoint cấu hình để hỗ trợ kiểm tra nội bộ, **không thử quyền truy cập** và không nên xuất tài nguyên nội bộ ra API công khai không kiểm soát.

**Quan hệ giữa các thư viện:**

- **Spring Cloud Azure starter:** cấu hình bean, quy ước properties và tích hợp Spring Boot.
- **Azure SDK for Java:** gửi request đến Blob/Service Bus/Key Vault.
- **azure-identity:** lấy token theo **TokenCredential**.
- **Microsoft Entra ID + Azure RBAC:** xác thực principal và quyết định quyền của nó trên dịch vụ.

Không bắt buộc khai báo mọi thuộc tính tenant/client ID trong application.yml nếu runtime managed/workload identity đã cung cấp đúng thông tin. Tên property và cơ chế auto-configuration có thể thay đổi giữa các dòng Spring Cloud Azure, nên đối chiếu documentation theo phiên bản.

## 10. Managed identity trên App Service, Functions và VM

### 10.1. System-assigned identity

Các bước logic:

1. Bật **system-assigned managed identity** trên Azure resource chạy ứng dụng (khi dịch vụ hỗ trợ).
2. Ghi nhận **principal ID** của identity.
3. Gán role dữ liệu cho principal ở tài nguyên cần truy cập, ví dụ **Storage Blob Data Contributor** trên Blob Storage account/container.
4. Cấu hình đúng Blob endpoint trong Spring Boot.
5. Triển khai ứng dụng và kiểm tra request thật bằng danh tính workload.

Với hệ thống chỉ sử dụng một system-assigned identity ở runtime phù hợp, **DefaultAzureCredential** có thể nhận token bằng managed identity nếu các nguồn ưu tiên khác không can thiệp. Nếu muốn đảm bảo chỉ dùng managed identity, có thể tạo bean credential tường minh:

~~~java
import com.azure.core.credential.TokenCredential;
import com.azure.identity.ManagedIdentityCredentialBuilder;

TokenCredential credential =
        new ManagedIdentityCredentialBuilder().build();
~~~

Đây là trích đoạn khởi tạo credential; khi dùng trong Spring Boot, hãy cung cấp nó dưới dạng bean để client tái sử dụng.

### 10.2. User-assigned identity

Nếu runtime đã được gắn user-assigned managed identity và cần chọn rõ danh tính:

~~~java
import com.azure.core.credential.TokenCredential;
import com.azure.identity.ManagedIdentityCredentialBuilder;

String managedIdentityClientId = System.getenv("AZURE_CLIENT_ID");

if (managedIdentityClientId == null ||
        managedIdentityClientId.isBlank()) {
    throw new IllegalStateException(
            "AZURE_CLIENT_ID is required for this user-assigned identity");
}

TokenCredential credential =
        new ManagedIdentityCredentialBuilder()
                .clientId(managedIdentityClientId)
                .build();
~~~

**AZURE_CLIENT_ID** ở đây là client ID của user-assigned identity, **không phải principal ID**. Bản thân biến này không cấp quyền; identity phải được gắn vào runtime và có role ở dịch vụ đích.

Với **DefaultAzureCredential**, Azure Identity cũng có những cách cấu hình chọn user-assigned managed identity, ví dụ cơ chế builder hoặc biến môi trường theo phiên bản. Nếu hệ thống có nhiều identity, hãy cấu hình tường minh để tránh dùng nhầm principal.

## 11. Workload identity trên AKS

AKS Workload ID sử dụng cơ chế federation giữa Kubernetes service account và Microsoft Entra. Một luồng cấu hình tiêu biểu gồm:

~~~mermaid
sequenceDiagram
    participant P as Spring Boot Pod
    participant K as Kubernetes Service Account / OIDC
    participant E as Microsoft Entra ID
    participant S as Azure Storage
    P->>K: Nhận projected service-account token
    P->>E: Đổi token OIDC theo federated trust
    E-->>P: Access token cho principal đã cấu hình
    P->>S: HTTPS request + Entra access token
    S-->>P: Cho phép hoặc từ chối theo RBAC/policy
~~~

Các giá trị cần đồng bộ:

| Thành phần | Ý nghĩa |
| --- | --- |
| **Issuer** | Nguồn phát OIDC token cho AKS cluster |
| **Subject** | Kubernetes service account cụ thể được liên kết |
| **Audience** | Đối tượng token được cấu hình cho quá trình federation |
| **Client ID** | Entra application hoặc user-assigned managed identity nhận token |
| **Tenant ID** | Tenant chứa danh tính Entra tương ứng |
| **Federated credential** | Liên kết tin cậy giữa issuer, subject, audience và identity |
| **Azure data role** | Quyền cho principal trên Blob, Service Bus, Key Vault... |

Trong một cấu hình AKS Workload ID phù hợp, pod có thể được cung cấp các biến như:

~~~text
AZURE_CLIENT_ID=<client-id-cua-danh-tinh-duoc-lien-ket>
AZURE_TENANT_ID=<tenant-id>
AZURE_FEDERATED_TOKEN_FILE=<duong-dan-token-duoc-projected>
~~~

Đây là **các biến runtime**, không phải giá trị nên tự hard-code trong repository. Hệ thống phải hỗ trợ OIDC issuer, gán service account đúng và cấu hình pod để token được projected. **DefaultAzureCredential** ở phiên bản Azure Identity hỗ trợ workload identity có thể sử dụng các giá trị đó; cũng có thể dùng **WorkloadIdentityCredential** riêng nếu chính sách yêu cầu.

**Lỗi phổ biến:** pod có service account đúng nhưng thiếu federated credential matching issuer/subject/audience, hoặc Entra đã cấp token nhưng principal không có role dữ liệu ở storage account. Hai lỗi này nằm ở hai bước khác nhau và cần cách kiểm tra khác nhau.

## 12. CI/CD: ưu tiên federation và quyền tối thiểu

Một pipeline có thể cần hai nhóm quyền:

- **Deployment plane:** tạo/cập nhật ứng dụng hoặc các tài nguyên qua ARM trong subscription/resource group.
- **Data plane:** đọc/ghi Blob, nhận/gửi Service Bus hoặc đọc Key Vault secret trong integration test.

Nếu pipeline chỉ triển khai artifact, không nên cấp sẵn quyền ghi Blob production cho nó. Nên tách **identity triển khai** với **identity runtime**; integration test dùng identity test và tài nguyên test riêng.

### Mô hình CI có OIDC

1. Identity provider của CI phát token cho job sau khi kiểm tra điều kiện repository/branch/environment.
2. Entra đã cấu hình federated credential tương ứng.
3. Job đổi OIDC token lấy Azure access token, qua một cơ chế được công cụ CI/SDK hỗ trợ.
4. Tác vụ deploy hoặc integration test sử dụng token trong phạm vi quyền đã cấp.
5. Không lưu client secret cố định trong biến môi trường CI nếu federation đã đáp ứng yêu cầu.

**Azure Login action/task không đồng nghĩa DefaultAzureCredential trong ứng dụng Java tự nhận mọi ngữ cảnh CI.** Nếu pipeline chạy integration test JVM, cần xác minh credential source mà SDK Java thực sự nhìn thấy: session Azure CLI trong runner, workload token file hoặc credential khác được cung cấp. Đồng thời bảo đảm nguồn đó phù hợp môi trường và thời hạn token.

### Biến môi trường: hữu ích nhưng có thể gây chọn nhầm danh tính

Một số cấu hình theo chuẩn Azure Identity gồm:

| Biến | Chức năng thường gặp |
| --- | --- |
| **AZURE_TENANT_ID** | Chỉ định tenant cho credential thích hợp |
| **AZURE_CLIENT_ID** | Chỉ định client application hoặc user-assigned identity tùy cơ chế credential |
| **AZURE_CLIENT_SECRET** | Secret cho cấu hình service-principal theo client-secret flow |
| **AZURE_FEDERATED_TOKEN_FILE** | Đường dẫn đến OIDC token file cho workload identity |
| **AZURE_AUTHORITY_HOST** | Chỉ định authority host ở cloud environment được hỗ trợ |

Một biến đơn lẻ không nhất thiết kích hoạt được toàn bộ credential. Nhưng **bộ biến cấu hình đầy đủ** cho một nguồn ưu tiên có thể thay đổi principal mà **DefaultAzureCredential** chọn.

Tránh sao chép mẫu chứa **AZURE_CLIENT_SECRET** vào cấu hình production nếu đang sử dụng managed identity hoặc federation. Với Kubernetes, không nên coi một environment variable secret là giải pháp quản lý danh tính dài hạn.

## 13. Chọn credential tường minh khi cần tính xác định

Một cách tổ chức là quyết định **identity mode** ở tầng triển khai:

| Identity mode | Môi trường phù hợp | Credential Java |
| --- | --- | --- |
| **developer** | Máy cá nhân hoặc lab | AzureCliCredential nếu muốn ép dùng Azure CLI |
| **managed-identity** | App Service, Functions, VM... | ManagedIdentityCredential |
| **workload-identity** | AKS/OIDC federation | WorkloadIdentityCredential |
| **default** | Môi trường đã kiểm soát credential chain | DefaultAzureCredential |

Ví dụ một factory đơn giản theo profile cấu hình:

~~~java
import com.azure.core.credential.TokenCredential;
import com.azure.identity.AzureCliCredentialBuilder;
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.identity.ManagedIdentityCredentialBuilder;

public final class IdentitySelector {

    private IdentitySelector() {}

    public static TokenCredential choose(
            String mode, String managedIdentityClientId) {

        switch (mode) {
            case "developer":
                return new AzureCliCredentialBuilder().build();

            case "managed-identity":
                if (managedIdentityClientId != null &&
                        !managedIdentityClientId.isBlank()) {
                    return new ManagedIdentityCredentialBuilder()
                            .clientId(managedIdentityClientId)
                            .build();
                }
                return new ManagedIdentityCredentialBuilder().build();

            case "default":
                return new DefaultAzureCredentialBuilder().build();

            default:
                throw new IllegalArgumentException(
                        "Unsupported Azure identity mode: " + mode);
        }
    }
}
~~~

Đây là **minh họa cách chọn rõ credential**, không phải một thư viện bắt buộc. Chế độ **workload-identity** có thể được bổ sung bằng **WorkloadIdentityCredentialBuilder** sau khi xác định đầy đủ tenant/client ID, token file và hỗ trợ của version SDK. Không dùng các mode giả lập để đổi danh tính trong runtime production theo request của người dùng cuối.

**Lợi ích:** production có thể fail sớm nếu managed identity chưa được cung cấp, thay vì bất ngờ dùng thông tin đăng nhập nhà phát triển hoặc credential từ môi trường khác.

## 14. RBAC theo từng dịch vụ và giới hạn của credential

Một credential lấy token cho identity, nhưng **dịch vụ đích** mới kiểm tra thao tác được phép.

| Nghiệp vụ | Dịch vụ | Quyền ví dụ |
| --- | --- | --- |
| Upload/ghi Blob | Azure Blob Storage | **Storage Blob Data Contributor** |
| Đọc Blob private | Azure Blob Storage | **Storage Blob Data Reader** |
| Gửi message | Azure Service Bus | **Azure Service Bus Data Sender** |
| Nhận message | Azure Service Bus | **Azure Service Bus Data Receiver** |
| Đọc secret (vault dùng Azure RBAC model) | Azure Key Vault | **Key Vault Secrets User** |
| Thao tác dữ liệu Cosmos DB for NoSQL | Azure Cosmos DB | Role dữ liệu tương ứng trong Cosmos DB data-plane RBAC |

Danh sách là **ví dụ định hướng**, không thay thế việc đọc scope/permission chính xác và mô hình ủy quyền riêng của dịch vụ. Với Key Vault còn có mô hình access policy ở một số tài nguyên; permission model của vault phải được kiểm tra.

**Cùng một credential có thể dùng cho nhiều Azure service**. Client SDK sẽ yêu cầu token thích hợp cho từng dịch vụ. Nhưng principal vẫn cần role riêng tương ứng với từng endpoint/resource.

### Quyền cho workload không phải quyền người dùng nghiệp vụ

Nếu Documents API dùng managed identity được quyền ghi Blob, quyền đó thuộc về **ứng dụng**. Người gọi HTTP endpoint của Documents API không tự động được cấp quyền Azure RBAC tương ứng. Ứng dụng phải kiểm tra authentication/authorization của **người dùng nghiệp vụ** trước khi thực hiện thao tác đại diện cho họ.

Đây là lý do cần phân biệt **workload identity** với **end-user identity**. Sử dụng một identity dịch vụ để truy cập tài nguyên thường phù hợp với backend, nhưng không thay thế kiểm soát quyền ở tầng API.

## 15. Kiểm thử và quan sát danh tính thực tế

### 15.1. Unit test

Mục tiêu unit test là kiểm tra nghiệp vụ khi Azure SDK trả thành công, 403, timeout hoặc conflict, **không cần token và resource Azure thật**. Có thể tiêm một adapter quanh BlobServiceClient rồi mock adapter, hoặc mock SDK client phù hợp với kiến trúc.

Nếu code tạo credential ngay trong mỗi phương thức nghiệp vụ, unit test sẽ khó kiểm soát hơn; nên inject **TokenCredential** và client qua Spring bean theo nhu cầu.

### 15.2. Integration test cục bộ

**Azurite** có thể mô phỏng một phần Azure Storage, phù hợp để kiểm tra những API Blob được hỗ trợ. Tuy nhiên Azurite **không thay thế được kiểm thử Microsoft Entra ID, managed identity hoặc Azure RBAC thật**. Khi thử emulator, cấu hình credential/endpoint có thể khác hẳn môi trường Azure live.

### 15.3. Integration test trên Azure test resource

Cần ít nhất một bài test với:

1. Identity test được cung cấp bởi môi trường CI/runtime.
2. Role dữ liệu đúng scope, có thời gian cho role assignment có hiệu lực.
3. Endpoint và DNS thực tế của tài nguyên test.
4. Một thao tác ít tác động, ví dụ tạo blob có tên ngẫu nhiên rồi xóa.
5. Cleanup và quan sát mã lỗi/request ID, không làm ảnh hưởng dữ liệu sản xuất.

**Đừng chỉ kiểm tra Spring context có khởi động không.** Nhiều Azure client được tạo mà chưa gọi dịch vụ; lỗi credential hoặc RBAC chỉ xuất hiện khi request đầu tiên cần access token hoặc truy cập endpoint.

### 15.4. Logging an toàn

Khi cần tìm credential chain đang dùng nguồn nào, bật logging chẩn đoán **azure-identity/Azure SDK** theo hướng dẫn của phiên bản và dùng mức log phù hợp trong môi trường test. Có thể quan sát:

- Credential source nào khả dụng hoặc thất bại.
- Mã loại lỗi và nguyên nhân (ví dụ không có endpoint managed identity).
- Endpoint hostname, operation, HTTP status và Azure request/correlation ID.
- Tenant/client ID hoặc principal identity **chỉ khi được phép đưa vào log nội bộ**, có cơ chế che/masking phù hợp.

**Không log access token, refresh token, secret, connection string, SAS URL hoặc nội dung file token federation**. Cũng không in toàn bộ biến môi trường vì có thể chứa bí mật ngoài Azure.

## 16. Chẩn đoán lỗi DefaultAzureCredential

| Triệu chứng | Vùng nghi vấn | Bước kiểm tra đầu tiên |
| --- | --- | --- |
| **CredentialUnavailableException** | Không có nguồn credential phù hợp hoặc nguồn chưa sẵn sàng | Xem credential chain, môi trường đang chạy, thông tin managed/workload identity |
| **AuthenticationFailedException** | Một nguồn credential đã cố xác thực nhưng thất bại | Kiểm tra tenant, issuer/federated credential, secret/certificate nếu có và SDK diagnostics |
| Local chạy được, deploy lỗi credential | Runtime không có phiên Azure CLI/IDE như laptop | Bật managed identity hoặc cấu hình workload federation trên runtime |
| Runtime dùng nhầm identity | Biến môi trường credential, nhiều user-assigned identity hoặc nguồn ưu tiên khác | Xác định principal được chọn; dùng credential tường minh khi cần |
| Lấy token được nhưng Blob trả **403** | RBAC data plane, scope sai hoặc policy mạng | Xem role trên **đúng storage account/container**, kiểm tra network policy |
| Key Vault trả **403** | Quyền đọc secret, permission model, principal hoặc vault URI | Kiểm tra Key Vault RBAC/access policy và tenant, không chỉ ARM Reader |
| Service Bus từ chối sender/receiver | Namespace/entity sai, thiếu role gửi/nhận hoặc mạng | Kiểm tra namespace, queue/topic, role Data Sender/Receiver |
| **401** từ dịch vụ | Token không hợp lệ hoặc không dành cho endpoint/audience phù hợp | Xác minh SDK/service target, authority và credential chain |
| Timeout ở Azure runtime | Private DNS, firewall, outbound route, proxy | Kiểm tra DNS và reachability từ chính container/VM/pod |
| Kết nối Azure đúng nhưng local CLI xem resource khác | CLI chọn subscription khác hoặc CLI không phải nguồn SDK đã chọn | Kiểm tra CLI context và account/endpoint trong ứng dụng |

### Quy trình xử lý có thứ tự

~~~mermaid
flowchart TD
    A[Ứng dụng gọi Azure thất bại] --> B{Có lấy được access token?}
    B -->|Không| C[Kiểm tra credential source / tenant / federation]
    B -->|Có| D{Request tới đúng endpoint?}
    D -->|Không| E[Sửa account / namespace / DNS / cấu hình SDK]
    D -->|Có| F{Có 401 hoặc 403?}
    F -->|Có| G[Kiểm tra audience, principal, role, policy mạng]
    F -->|Không| H[Kiểm tra timeout, quota, retry, operation semantics]
~~~

Luôn xem **root cause** và thông tin dịch vụ thực tế. Ví dụ một lỗi 403 có thể đến từ authorization của Storage hoặc một số network rule; không nên mặc định mọi 403 đều là thiếu role.

## 17. Đối chiếu với AWS và Google Cloud

Các cloud đều có cơ chế lấy credential từ môi trường chạy, nhưng khác nhau về identity model và API:

| Nhu cầu | Azure | AWS | Google Cloud |
| --- | --- | --- | --- |
| Credential chain mặc định | **DefaultAzureCredential** | **DefaultCredentialsProvider** trong AWS SDK for Java v2 | **Application Default Credentials (ADC)** |
| Danh tính cho workload trên cloud | Managed identity / federated workload identity | IAM role và temporary credentials qua metadata/STS | Service account/Workload Identity Federation |
| Trên máy lập trình viên | Azure CLI/IDE hoặc credential được hỗ trợ | AWS profile/SSO hoặc credential source được hỗ trợ | gcloud ADC hoặc credential source được hỗ trợ |
| Quyền dữ liệu | Azure RBAC và authorization theo dịch vụ | IAM policy, resource policy | Cloud IAM và permission theo resource |
| Giảm secret dài hạn trong CI | OIDC federation với Microsoft Entra | OIDC federation/STS AssumeRole phù hợp | Workload Identity Federation |

**Không sao chép trực tiếp biến môi trường giữa các cloud.** Cùng khái niệm “credential chain” nhưng thứ tự nguồn, lựa chọn principal, audience và mô hình cấp quyền khác nhau. Khi viết tích hợp đa cloud, nên đưa identity/client vào adapter theo provider và định nghĩa rõ quyền tối thiểu cho mỗi dịch vụ.

## 18. Bài thực hành: một ứng dụng, ba môi trường

**Bài toán:** Spring Boot Documents API lưu file vào container Blob private **documents**. Dùng một lớp nghiệp vụ và triển khai ở ba nơi khác nhau.

**Môi trường A — máy phát triển:**

1. Đăng nhập Azure CLI vào tenant dev.
2. Gán **Storage Blob Data Contributor** cho tài khoản dev trên storage account lab.
3. Cấu hình endpoint bằng biến môi trường và chạy ứng dụng với **DefaultAzureCredential**.
4. Kiểm tra resource thực tế được ghi và nguồn credential qua SDK diagnostics an toàn.

**Môi trường B — Azure App Service:**

1. Bật managed identity cho App Service.
2. Cấp role ghi Blob cho **principal của App Service**, không dùng tài khoản cá nhân.
3. Triển khai cùng code, cấu hình endpoint account và kiểm thử upload.
4. Thử thu hồi quyền ghi trên tài nguyên test và ghi nhận response 403; khôi phục role để hoàn thành lab.

**Môi trường C — AKS Workload ID hoặc CI dùng OIDC:**

1. Thiết lập issuer, subject, audience và federated credential phù hợp.
2. Cấu hình service account/pipeline để workload nhận projected token.
3. Cấp role trên storage account test cho principal được federation chọn.
4. Chạy integration test không dùng client secret cố định.
5. Xác nhận credential source và role chính xác qua log/diagnostics phù hợp.

**Sản phẩm cần nộp:** bảng ba môi trường gồm **principal ID/client ID (không kèm secret)**, phương án credential, RBAC scope, Blob endpoint, test thành công/thất bại và cách tái hiện bằng pipeline.

### Câu hỏi tự kiểm tra

1. Vì sao **DefaultAzureCredential** chạy được trên laptop nhưng không tự động chạy được trong một container trống?
2. Cặp **client ID** và **principal ID** có thể dùng thay nhau trong mọi tình huống không?
3. Vì sao **az login** thành công chưa chứng minh Azure SDK đang sử dụng Azure CLI credential?
4. Khi nào **ManagedIdentityCredential** tường minh phù hợp hơn một credential chain nhiều nguồn?
5. Workload identity federation đòi hỏi những thành phần issuer/subject/audience nào khớp nhau?
6. Vì sao tài khoản có quyền tạo storage account qua ARM chưa chắc upload được Blob?
7. Test bằng Azurite có chứng minh RBAC và managed identity đã cấu hình đúng không?
8. Khi nhận **403**, vì sao phải kiểm tra cả **principal, RBAC scope và network policy**?

## 19. Ghi nhớ

- **DefaultAzureCredential** giúp SDK tìm nguồn lấy token theo môi trường; nó **không tự quyết định principal nào phù hợp nghiệp vụ**, không cấp quyền và không tạo tài nguyên Azure.
- Với dev, dùng identity nhà phát triển trên tài nguyên test; với runtime Azure, ưu tiên **managed identity**; với AKS/CI hoặc host hỗ trợ federation, ưu tiên **workload identity federation** khi phù hợp.
- Chỉ định credential tường minh khi production yêu cầu tính xác định. **Client ID, principal ID và tenant ID** có ý nghĩa khác nhau.
- Để request thành công cần **đúng endpoint, đúng identity, quyền data plane và đường mạng**. Spring Cloud Azure starter giúp cấu hình client, Azure Identity cấp token, Azure RBAC/chính sách dịch vụ quyết định quyền.
- Kiểm thử ít nhất một request thật trong môi trường đích; quan sát credential source an toàn và tuyệt đối không log token/secret.

## Tài liệu tham khảo

- [DefaultAzureCredential trong Azure Identity for Java](https://learn.microsoft.com/java/api/com.azure.identity.defaultazurecredential)
- [Authentication with Azure Identity client library for Java](https://learn.microsoft.com/azure/developer/java/sdk/authentication/overview)
- [Azure Managed Identity overview](https://learn.microsoft.com/entra/identity/managed-identities-azure-resources/overview)
- [Microsoft Entra Workload ID for AKS](https://learn.microsoft.com/azure/aks/workload-identity-overview)
- [Azure RBAC overview](https://learn.microsoft.com/azure/role-based-access-control/overview)
- [Spring Cloud Azure documentation](https://learn.microsoft.com/azure/developer/java/spring-framework/)
