# Phân biệt tích hợp thư viện Azure với nền tảng lưu trú ứng dụng

Một ứng dụng Spring Boot có thể dùng **Spring Cloud Azure** để đọc Blob Storage và gửi message qua Service Bus nhưng được triển khai trên **Azure App Service**, **Azure Kubernetes Service (AKS)**, một máy ảo, máy chủ tại doanh nghiệp hoặc thậm chí trên AWS/Google Cloud. Chiều ngược lại cũng đúng: một ứng dụng chạy trên Azure không nhất thiết phải thêm bất kỳ Spring Cloud Azure starter nào nếu không tích hợp các dịch vụ Azure bằng những thư viện đó.

Hiểu rõ sự khác biệt giữa **thư viện tích hợp dịch vụ** và **nền tảng lưu trú (hosting)** giúp tránh chọn sai dependency, cấp sai quyền, thiết kế sai network và nhầm trách nhiệm giữa developer và đội platform.

Bài thuộc chương **Nền tảng Azure**, trong module **SPRING_CLOUD_PROVIDER_INTEGRATION**: thực hành tích hợp Spring Boot với dịch vụ managed của AWS, Azure và Google Cloud thông qua các thư viện Spring Cloud tương ứng; chú trọng danh tính/quyền, storage, messaging, dữ liệu, secret, kiểm thử tích hợp và đánh giá khác biệt giữa các cloud provider.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích sự khác nhau giữa **Spring Cloud Azure**, **Azure SDK for Java**, **Spring Boot**, **nền tảng hosting** và **dịch vụ Azure managed** được ứng dụng gọi đến.
2. Phân biệt việc **đóng gói/chạy Spring Boot** với việc **tích hợp Blob Storage, Service Bus, Key Vault, Cosmos DB** ở tầng Java.
3. Đánh giá App Service, Azure Container Apps, AKS, Azure Functions, VM và nền tảng ngoài Azure theo nhu cầu triển khai.
4. Thiết kế cấu hình application, danh tính workload, Azure RBAC, DNS/Private Endpoint và observability cho từng môi trường.
5. Minh họa cùng một lớp nghiệp vụ Spring Boot chạy trên local và App Service mà không phải viết lại logic gọi Blob.
6. Nhận biết giới hạn của managed identity, migration giữa provider và các trường hợp nên dùng Azure SDK trực tiếp thay vì starter.
7. Xây dựng bài kiểm thử chứng minh client thực sự gọi được dịch vụ dưới **danh tính của runtime**.

## 2. Ba lớp cần phân biệt trong một kiến trúc Azure

~~~mermaid
flowchart TB
    U[Người dùng hoặc hệ thống gọi API] --> A[Spring Boot application]
    subgraph Host["Lớp lưu trú ứng dụng"]
      A
      H[App Service / Container Apps / AKS / VM / môi trường khác]
    end
    A --> L[Spring Cloud Azure starter hoặc Azure SDK for Java]
    L --> I[Azure Identity / TokenCredential]
    L --> D[Blob Storage / Service Bus / Key Vault / Cosmos DB]
    I --> E[Microsoft Entra ID]
    P[Azure RBAC và chính sách dịch vụ] -.-> D
    N[DNS / VNet / firewall / Private Endpoint] -.-> D
~~~

| Lớp | Vai trò | Câu hỏi cần đặt |
| --- | --- | --- |
| **Mã và framework ứng dụng** | Xử lý API, nghiệp vụ, giao dịch, security của người dùng, cấu hình Spring Boot | Ứng dụng làm gì? |
| **Thư viện tích hợp** | Cấu hình/khởi tạo client và gọi Azure data APIs | Ứng dụng giao tiếp Azure bằng API/SDK nào? |
| **Nền tảng lưu trú** | Khởi chạy tiến trình/container, cung cấp CPU/RAM, scale, cấu hình runtime, triển khai và đường mạng | Chương trình chạy ở đâu và được vận hành thế nào? |
| **Managed service Azure** | Lưu trữ dữ liệu, message, database, secret, configuration | Dữ liệu/nghiệp vụ phụ trợ nằm ở đâu? |
| **Identity, RBAC, network** | Xác thực và giới hạn quyền truy cập giữa workload và dịch vụ | Ai được gọi gì, bằng đường nào? |

**Điểm cốt lõi:** thư viện tích hợp và nền tảng chạy là **hai quyết định độc lập nhưng có ảnh hưởng lẫn nhau**. App Service/AKS có thể cung cấp cơ chế lấy credential, network và vận hành; Spring Cloud Azure/Azure SDK vẫn quyết định cách code Java kết nối đến dịch vụ.

### Ví dụ ngắn

- **Spring Boot + spring-cloud-azure-starter-storage-blob + App Service:** starter cấu hình Blob client; App Service chạy ứng dụng, có thể cung cấp managed identity.
- **Spring Boot + azure-storage-blob + AKS:** code tự dựng SDK client; AKS chạy Pod, có thể dùng Workload Identity để lấy token.
- **Spring Boot + spring-cloud-azure-starter-servicebus + máy chủ tại doanh nghiệp:** vẫn gọi Service Bus nếu endpoint truy cập được và credential phù hợp.
- **Spring Boot + Spring Data JPA + PostgreSQL tự quản trên App Service:** ứng dụng chạy trên Azure nhưng không bắt buộc phải có Spring Cloud Azure.
- **Spring Boot + SDK AWS S3 chạy trên Azure Container Apps:** hosting ở Azure, dịch vụ dữ liệu nằm ở AWS; thiết kế credential và network theo AWS.

## 3. Spring Cloud Azure thực sự cung cấp điều gì?

**Spring Cloud Azure** là tập thư viện tích hợp các dịch vụ Azure với hệ sinh thái Spring, thường thông qua **Spring Boot auto-configuration**, externalized configuration, dependency injection và các tích hợp Spring Data, Spring Integration hoặc Spring Security theo starter cụ thể.

| Thành phần | Vai trò điển hình | Ví dụ |
| --- | --- | --- |
| **Spring Boot** | Xây dựng ứng dụng Java, tạo application context, quản lý bean/config, chạy web service | Spring MVC REST API |
| **Azure SDK for Java** | Cung cấp API Java để thao tác với từng dịch vụ Azure | BlobServiceClient, ServiceBusSenderClient, SecretClient |
| **Spring Cloud Azure starter** | Kéo theo SDK và tự cấu hình các bean/integration thích hợp | spring-cloud-azure-starter-storage-blob |
| **Azure Identity SDK** | Cung cấp TokenCredential để lấy token của principal | DefaultAzureCredential, ManagedIdentityCredential |
| **Azure hosting** | Chạy file JAR/container, quản lý triển khai và vận hành | App Service, AKS, Container Apps |

Spring Cloud Azure **dùng Azure SDK bên dưới**, không thay thế API Azure SDK. Khi ứng dụng inject một **BlobServiceClient** do starter tạo, phương thức upload vẫn là API của Azure Storage SDK.

Starter **không tự tạo Storage Account**, **không tự tạo queue**, **không bật managed identity**, **không cấp role Azure RBAC** và **không bảo đảm network thông suốt**. Các thành phần đó thuộc bước quản lý hạ tầng và triển khai.

### Chọn starter theo nhu cầu dịch vụ

| Nhu cầu | Lựa chọn thư viện thường gặp | Hosting có bắt buộc không? |
| --- | --- | --- |
| Lưu file vào Blob | Spring Cloud Azure Blob starter hoặc Azure Storage Blob SDK | Có thể chạy ở bất cứ nơi nào có kết nối và credential |
| Gửi/nhận Service Bus | Spring Cloud Azure Service Bus starter hoặc Service Bus SDK | Không bắt buộc chạy trên Azure |
| Đọc Key Vault secret | Spring Cloud Azure Key Vault starter hoặc Secrets SDK | Không bắt buộc chạy trên Azure |
| Dùng Cosmos DB với Spring Data | Spring Data Cosmos integration phù hợp | Có thể chạy ngoài Azure nếu đáp ứng kết nối và xác thực |
| Đọc App Configuration | Spring Cloud Azure App Configuration starter / SDK | Không buộc cùng subscription/hosting |
| Triển khai REST API đơn thuần | Không cần Azure starter nếu không dùng tích hợp tương ứng | Có thể chạy trên Azure App Service |

Tên artifact và API có thể khác theo phiên bản. Luôn chọn **Spring Cloud Azure BOM** tương thích với **Spring Boot/JDK** và đối chiếu hướng dẫn starter đang sử dụng.

## 4. Azure hosting giải quyết những vấn đề nào?

Nền tảng hosting quyết định **quy trình triển khai và runtime**, ví dụ:

- Chạy Java runtime trực tiếp hoặc container image.
- Lựa chọn CPU/RAM, autoscaling và giới hạn tài nguyên.
- Quản lý cấu hình môi trường, restart, health checks và secrets injection.
- Expose HTTP endpoint, TLS ở ingress, routing, load balancing.
- Kết nối VNet, DNS, outbound egress, firewall và Private Endpoint.
- Khởi tạo identity cho workload thông qua cơ chế được nền tảng hỗ trợ.
- Thu thập metrics, logs, traces, quản lý rollout/rollback và availability.

Những khả năng này **không phụ thuộc vào việc có Spring Cloud Azure starter**. Một ứng dụng Spring Boot chỉ gọi database bên ngoài cũng cần các quyết định hosting như vậy.

### Bảng so sánh các lựa chọn phổ biến

| Nền tảng | Mô hình vận hành | Khi nào cân nhắc | Phần vẫn cần tự thiết kế |
| --- | --- | --- | --- |
| **Azure App Service** | PaaS chạy web app/API bằng runtime hoặc container được hỗ trợ | REST API Spring Boot, muốn giảm phần quản lý hạ tầng | App config, identity, outbound network, scale, deployment slots theo cấu hình |
| **Azure Container Apps** | Nền tảng managed cho container và microservice, có revision/scale | Workload container, HTTP API hoặc background processing, cần vận hành gọn | Container image, ingress, secrets/config, managed identity, networking, scale triggers |
| **AKS** | Kubernetes managed control plane; đội ngũ vận hành workload và nhiều thành phần cluster | Nhiều microservice cần Kubernetes ecosystem, custom controllers/policies | Namespace, service account, workload identity, ingress, resource limits, observability |
| **Azure Functions** | Mô hình function/event-driven theo hosting plan và language model | Tác vụ theo trigger hoặc sự kiện, phù hợp cách đóng gói Functions | Trigger/binding, cold start, vòng đời function, khả năng tích hợp Spring cụ thể |
| **Azure VM** | IaaS, tự quản nhiều thành phần hệ điều hành/runtime | Cần kiểm soát sâu OS, agent, network hoặc ứng dụng legacy | Patching, process lifecycle, scaling, monitoring, bảo vệ VM |
| **Môi trường ngoài Azure** | On-prem, AWS, GCP, container platform khác | Hệ thống đa cloud hoặc yêu cầu dữ liệu/hosting cụ thể | Egress tới Azure, federation/credential, latency và chi phí mạng |
| **Azure Spring Apps (tên nền tảng từng được sử dụng)** | PaaS dành riêng cho Spring workloads | Chỉ đánh giá sau khi kiểm tra trạng thái dịch vụ và kế hoạch hỗ trợ hiện hành | Không đồng nhất sản phẩm hosting này với thư viện Spring Cloud Azure |

**Lưu ý về vòng đời sản phẩm:** tình trạng hỗ trợ, khu vực khả dụng, lộ trình và thời hạn chuyển đổi của từng dịch vụ Azure thay đổi theo thời gian. Khi lựa chọn nền tảng mới, cần tra thông báo vòng đời chính thức của dịch vụ và chính sách tổ chức. Không lấy tên **Azure Spring Apps** làm bằng chứng rằng dự án phải dùng sản phẩm đó để chạy Spring Cloud Azure.

### Azure Spring Apps và Spring Cloud Azure là hai khái niệm khác nhau

- **Spring Cloud Azure**: các Java libraries/starter mà ứng dụng thêm vào file build.
- **Azure Spring Apps**: tên một dịch vụ hosting được phát triển cho Spring workloads; không phải dependency Maven của Spring Cloud Azure.
- **Spring Boot**: framework tạo ứng dụng, không gắn độc quyền với hosting của Microsoft.

Một service **được triển khai trên App Service** vẫn có thể dùng Spring Cloud Azure bình thường. Một ứng dụng **chạy trên VM ở GCP** cũng có thể dùng Azure Blob SDK nếu có cách xác thực và network hợp lệ. Ngược lại, triển khai JAR lên dịch vụ hosting không tự biến mọi dependency Azure thành bean trong Spring.

## 5. Ma trận quyết định: thư viện và nơi chạy là hai trục

| Ứng dụng chạy ở đâu? | Không dùng dịch vụ Azure | Dùng Azure SDK trực tiếp | Dùng Spring Cloud Azure starter |
| --- | --- | --- | --- |
| Local developer | Ứng dụng Spring Boot thông thường | Dùng AzureCliCredential hoặc credential phù hợp | Starter tự cấu hình client khi dependency và properties hợp lệ |
| App Service | Chạy được | Có thể dùng managed identity qua Azure Identity | Có thể dùng starter và managed identity |
| Container Apps | Chạy được | SDK qua managed identity nếu runtime được cấu hình | Starter tương tự, kiểm tra cấu hình credential |
| AKS | Chạy được | SDK qua AKS Workload ID hoặc cơ chế xác thực phù hợp | Starter cũng dùng được nếu phần identity/network hoàn chỉnh |
| VM on Azure | Chạy được | SDK + identity VM hoặc credential được hỗ trợ | Starter và properties Spring hoạt động nếu runtime đáp ứng |
| AWS/GCP/on-prem | Chạy được | Azure SDK với federation/credential hợp lệ và mạng tới Azure | Vẫn dùng starter được; identity Azure không tự xuất hiện |

**Không có quy tắc “Spring Cloud Azure chỉ chạy trên Azure”.** Khả năng tương thích của JDK, dependency, credential, data endpoint và network mới là điều kiện kỹ thuật then chốt.

Tuy nhiên, chạy app ở provider khác rồi gọi Azure có thể phát sinh **latency**, **egress/inter-region charges**, data residency và rủi ro phụ thuộc chéo cloud. Quyết định hosting cần xem cả phi chức năng, không chỉ là “SDK gọi được hay không”.

## 6. Trách nhiệm giữa nhóm ứng dụng và nhóm platform

| Câu hỏi | Nhóm ứng dụng thường chịu trách nhiệm | Nhóm platform/identity thường chịu trách nhiệm |
| --- | --- | --- |
| Chọn Blob hay Service Bus | Phân tích nghiệp vụ và API | Tham gia đánh giá vận hành/giới hạn |
| Thêm starter/SDK và quản lý BOM | Khai báo dependency, code client, test | Chính sách version/security nếu có |
| Tạo Storage Account/Service Bus namespace | Cung cấp yêu cầu tài nguyên và vùng | Provision qua IaC/pipeline |
| Bật managed identity hoặc Workload ID | Cung cấp nhu cầu/identity mode | Gắn identity vào runtime, thiết lập trust |
| Gán role dữ liệu | Liệt kê thao tác và scope tối thiểu cần thiết | Gán role với quyền quản trị được ủy quyền |
| Kết nối Private Endpoint | Cấu hình endpoint đúng, test từ runtime | VNet, private DNS, network policy và route |
| Health check, retry, idempotency | Code và ứng dụng/SDK | Theo dõi resource capacity và platform observability |
| Deployment và rollback | Version ứng dụng, migrations, smoke tests | Pipeline, môi trường, health và scale policies |

Đây là cách phân trách nhiệm **tham khảo**, không phải quy định áp dụng cho mọi tổ chức. Điều quan trọng là có người sở hữu rõ ràng từng đầu việc, nhất là **identity, RBAC và đường mạng**.

## 7. Cùng một ứng dụng Spring Boot gọi Blob Storage

Giả sử **Documents API** nhận tài liệu, lưu vào container Blob **documents** và trả về tên đối tượng. Ứng dụng phải hoạt động trên local và Azure hosting mà không thay đổi lớp nghiệp vụ.

### 7.1. Chọn một phương án dependency

Với Spring Cloud Azure, ví dụ Maven dependency:

~~~xml
<!-- Trích đoạn: import Spring Cloud Azure BOM tương thích trong
     dependencyManagement của pom.xml trước khi khai báo starter. -->
<dependency>
    <groupId>com.azure.spring</groupId>
    <artifactId>spring-cloud-azure-starter-storage-blob</artifactId>
</dependency>
~~~

Trong **dependencyManagement**, BOM thường là:

~~~xml
<dependency>
    <groupId>com.azure.spring</groupId>
    <artifactId>spring-cloud-azure-dependencies</artifactId>
    <version>${spring-cloud-azure.version}</version>
    <type>pom</type>
    <scope>import</scope>
</dependency>
~~~

Đây là **các trích đoạn**, không phải một POM hoàn chỉnh. Thuộc tính **spring-cloud-azure.version** phải là giá trị đã xác nhận tương thích với Spring Boot/JDK của dự án. Không viết cứng version từng Azure SDK nếu BOM đã quản lý.

### 7.2. application.yml cho Spring Cloud Azure

~~~yaml
spring:
  cloud:
    azure:
      storage:
        blob:
          account-name: ${AZURE_STORAGE_ACCOUNT}

app:
  documents:
    container-name: ${AZURE_BLOB_CONTAINER:documents}
~~~

Ví dụ với Azure public cloud, account name **stordersdev01** thường dẫn tới endpoint dạng **https://stordersdev01.blob.core.windows.net** theo cách tự cấu hình của phiên bản phù hợp. Nếu dùng cloud environment khác, emulator hoặc endpoint đặc biệt, phải cấu hình theo tài liệu của phiên bản Spring Cloud Azure.

Không đưa connection string, account key, client secret hoặc SAS token vào Git. Spring Boot có thể nhận biến môi trường từ máy dev, App Service application settings, Container Apps configuration hoặc Kubernetes Pod.

### 7.3. Viết lớp nghiệp vụ độc lập hosting

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
            @Value("${app.documents.container-name}") String containerName) {
        this.container = blobServiceClient.getBlobContainerClient(containerName);
    }

    public void upload(String name, byte[] bytes) {
        container.getBlobClient(name).upload(
                new ByteArrayInputStream(bytes), bytes.length, false);
    }
}
~~~

**DocumentsStorage** không chứa code “nếu chạy trên App Service thì…” hoặc “nếu chạy trên AKS thì…”. Nó dùng bean **BlobServiceClient** do Spring Cloud Azure tạo và không quan tâm nơi process đang chạy.

Mục tiêu của kiến trúc là **thay đổi cấu hình môi trường và cách cấp identity**, trong khi logic lưu tài liệu không đổi. Ví dụ dùng **overwrite=false** để không âm thầm thay nội dung một blob trùng tên. Production cần thêm kiểm soát kích thước, streaming, validation, idempotency, xử lý conflict và quyền của người gọi API.

### 7.4. Nếu cần Azure SDK trực tiếp

Một ứng dụng không cần auto-configuration có thể tạo client như bean Spring:

~~~java
import com.azure.core.credential.TokenCredential;
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.storage.blob.BlobServiceClient;
import com.azure.storage.blob.BlobServiceClientBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class AzureBlobConfiguration {

    @Bean
    public TokenCredential tokenCredential() {
        return new DefaultAzureCredentialBuilder().build();
    }

    @Bean
    public BlobServiceClient blobServiceClient(
            TokenCredential tokenCredential,
            @Value("${app.azure.blob.endpoint}") String blobEndpoint) {
        return new BlobServiceClientBuilder()
                .endpoint(blobEndpoint)
                .credential(tokenCredential)
                .buildClient();
    }
}
~~~

Với phương án này, cần đặt **app.azure.blob.endpoint** trong application.yml và cấp đúng hai dependency **azure-identity** và **azure-storage-blob** được quản lý version nhất quán. Nếu đã dùng starter tự cấu hình **BlobServiceClient**, không tự tạo thêm bean cùng kiểu nếu chưa xử lý rõ auto-configuration và qualifier.

**Quan sát:** lớp DocumentsStorage không đổi khi chuyển giữa bean do starter tạo và bean do ứng dụng tự tạo, miễn hợp đồng API client đáp ứng nhu cầu.

## 8. Môi trường A: phát triển trên laptop

Ở máy developer, JDK/Spring Boot chạy local; chỉ dịch vụ dữ liệu nằm trên Azure. Một phương án phổ biến là đăng nhập bằng Azure CLI:

~~~bash
az login

az account show   --query "{tenant:tenantId, subscription:id, name:name}"   --output json
~~~

Với **DefaultAzureCredential**, Azure Identity SDK thử các nguồn phù hợp theo chain/phiên bản; Azure CLI chỉ là **một** nguồn. Nếu cần ép môi trường lab sử dụng tài khoản CLI để tránh nhầm identity, có thể chọn **AzureCliCredential** cụ thể.

Để app upload, tài khoản developer vẫn cần role **Storage Blob Data Contributor** ở Storage Account/container test phù hợp. Đăng nhập CLI và có quyền xem resource metadata qua ARM **không đồng nghĩa** có quyền dữ liệu Blob.

Máy developer có thể có Internet trực tiếp, nhưng môi trường production có proxy hoặc Private Endpoint. Vì vậy thành công trên local chưa chứng minh đường mạng của hosting.

## 9. Môi trường B: Azure App Service và managed identity

App Service có thể chạy ứng dụng Java bằng mô hình runtime hoặc container được hỗ trợ, nhận app settings và cung cấp managed identity nếu được bật.

### 9.1. Quy trình triển khai logic

1. Provision App Service cùng runtime/container, region và network theo yêu cầu.
2. Bật **system-assigned managed identity** hoặc gắn **user-assigned managed identity** khi phù hợp.
3. Lấy **principal ID** của identity và gán quyền dữ liệu trên Storage Account/container đích.
4. Đưa **AZURE_STORAGE_ACCOUNT** và **AZURE_BLOB_CONTAINER** vào application settings.
5. Deploy JAR/container và kiểm tra một request upload thật.
6. Thiết lập health check, log, metrics, scale và rollback; bảo đảm outbound DNS/VNet đến Blob hoạt động.

Ví dụ Azure CLI cho App Service đã tồn tại:

~~~bash
az webapp identity assign   --resource-group "<app-resource-group>"   --name "<app-service-name>"

az webapp identity show   --resource-group "<app-resource-group>"   --name "<app-service-name>"   --query "{principalId:principalId, tenantId:tenantId}"   --output json
~~~

Gán data role trên Storage Account phù hợp bằng tài khoản **có quyền cấp role**:

~~~bash
az role assignment create   --assignee-object-id "<app-managed-identity-principal-id>"   --assignee-principal-type ServicePrincipal   --role "Storage Blob Data Contributor"   --scope "<storage-account-resource-id>"
~~~

Các lệnh là **mẫu lab**; thay placeholder bằng giá trị thực, chỉ thực hiện trên tài nguyên được phép và ghi lại scope. Sau khi role được gán, có thể cần thời gian để quyền có hiệu lực.

### 9.2. Cấu hình môi trường, không đưa bí mật vào mã

~~~bash
az webapp config appsettings set   --resource-group "<app-resource-group>"   --name "<app-service-name>"   --settings AZURE_STORAGE_ACCOUNT="<storage-account-name>" AZURE_BLOB_CONTAINER="documents"
~~~

Client vẫn dùng cùng **DocumentsStorage**. Phần khác nhau chủ yếu là app settings và credential chain/identity của runtime.

**Chú ý:** nếu có nhiều identity hoặc nguồn environment credential, DefaultAzureCredential có thể chọn principal không mong muốn. Với production cần danh tính xác định, hãy dùng cấu hình credential cụ thể theo API Azure Identity/Spring Cloud Azure của phiên bản đang dùng, và kiểm chứng principal thực tế qua cách quan sát an toàn.

## 10. Môi trường C: AKS và Workload Identity

AKS lưu trú Spring Boot trong một Kubernetes Pod. AKS hỗ trợ cấu hình **Microsoft Entra Workload ID** để Pod có thể dùng danh tính Entra mà không lưu client secret dài hạn trong image.

Điều khác biệt so với App Service nằm ở **cách cung cấp identity**, không phải việc viết lại tất cả lớp nghiệp vụ Blob.

### 10.1. Những thành phần cần có

| Thành phần | Trách nhiệm |
| --- | --- |
| **AKS OIDC issuer** | Phát token định danh workload theo cấu hình cluster |
| **Kubernetes service account** | Đại diện cho workload trong namespace |
| **Federated credential trong Entra** | Tin cậy issuer/subject/audience của workload cụ thể |
| **Entra identity** | Principal nhận access token để gọi Azure |
| **Role assignment** | Cho phép principal ghi Blob ở scope cần thiết |
| **Pod label/annotation và token projection** | Cung cấp thông tin/token cho Azure Identity SDK theo cấu hình Workload ID |

Minh họa service account:

~~~yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: documents-api
  namespace: documents
  annotations:
    azure.workload.identity/client-id: "<user-assigned-managed-identity-client-id>"
~~~

Pod template trong Deployment:

~~~yaml
spec:
  template:
    metadata:
      labels:
        app: documents-api
        azure.workload.identity/use: "true"
    spec:
      serviceAccountName: documents-api
      containers:
        - name: app
          image: "<registry>/documents-api:<tag>"
          env:
            - name: AZURE_STORAGE_ACCOUNT
              value: "<storage-account-name>"
            - name: AZURE_BLOB_CONTAINER
              value: "documents"
~~~

Đây là **trích đoạn Deployment**, không phải manifest deploy hoàn chỉnh. Cần cấu hình selector, deployment metadata, resource requests/limits, readiness/liveness probes và security policy theo môi trường.

### 10.2. Spring Cloud Azure có cần mã AKS riêng?

Nếu SDK và starter hỗ trợ workload identity của phiên bản đang sử dụng, phần Bean Blob Service và nghiệp vụ có thể giữ nguyên. Tuy nhiên AKS **không tự cấp Entra identity chỉ vì Pod có nhãn đúng**. Phải bật OIDC/Workload ID, tạo federated credential khớp issuer/subject/audience, gán role đúng và đảm bảo token projection.

Điều quan trọng khác: **node identity khác Pod/workload identity**. Không lấy việc node AKS có quyền vào Storage làm bằng chứng Pod đã dùng Workload Identity đúng.

### 10.3. Các rủi ro runtime Kubernetes

- Khi Pod scale thành nhiều replicas, phải kiểm soát retry/idempotency cho upload/message processing.
- Cần route, DNS và network policy để Pod gọi Azure Blob cũng như Microsoft Entra token endpoint.
- Nếu dùng **Private Endpoint**, cần cấu hình private DNS ở mạng AKS.
- Nếu chạy sidecar/service mesh/proxy, cần kiểm tra đường lấy token và đường gọi data plane.
- Không nhầm readiness probe thành phép kiểm tra RBAC; startup thành công chưa chắc request đầu tiên gọi Azure thành công.

## 11. Môi trường D: Azure Container Apps, Azure Functions và VM

### Azure Container Apps

Container Apps phù hợp khi muốn chạy container và dùng các khả năng nền tảng như revision/scale mà không quản lý toàn bộ Kubernetes cluster. Ứng dụng Spring Boot vẫn được build thành image và lắng nghe HTTP port phù hợp.

Nền tảng có thể hỗ trợ managed identity và cấu hình networking/secrets, nhưng đội triển khai vẫn cần bật/gắn identity, cấp role trên resource đích và cấu hình đúng endpoint.

Với tác vụ background nhận Service Bus message, không chỉ xét khả năng container start mà phải thiết kế **queue consumer**, retry, concurrency, scale signal và cách xử lý message trùng.

### Azure Functions

Functions là mô hình event-driven: ứng dụng thường triển khai theo **function entrypoint/trigger và runtime contract**. Một Spring Boot web server đóng gói như JAR không mặc nhiên trở thành Azure Function chỉ vì đưa lên Azure.

Nếu sử dụng Spring Cloud Function adapter hoặc mô hình tích hợp hỗ trợ, phải xem tài liệu của runtime/extension đang chọn. Spring Cloud Azure starter có thể tham gia một số tích hợp, nhưng **quy trình đóng gói và khởi tạo function** vẫn là quyết định hosting.

### Azure VM

VM cho quyền kiểm soát sâu hệ điều hành, JVM và agent. Nếu VM có managed identity, Azure Identity SDK có thể lấy token qua cơ chế của môi trường. Tuy nhiên đội vận hành phải quản lý OS patching, daemon/service process, health checks, log rotation, restart, firewall và scale.

Có VM trên Azure **không đồng nghĩa** identity được bật hoặc đã có quyền dữ liệu. Azure SDK không tự bật identity cho VM.

## 12. Chạy Spring Boot ngoài Azure nhưng gọi managed service Azure

Một ứng dụng chạy trên AWS, Google Cloud hoặc trong data center có thể gọi Azure Blob hay Service Bus nếu đáp ứng đủ:

1. **Service endpoint:** biết đúng hostname/namespace và yêu cầu protocol.
2. **Danh tính:** thiết lập credential hợp lệ với Microsoft Entra hoặc hình thức ủy quyền khác được dịch vụ hỗ trợ.
3. **RBAC:** principal có quyền dữ liệu phù hợp trên resource Azure đích.
4. **Mạng:** Internet/VPN/peering/proxy/private connectivity thỏa chính sách của Azure service.
5. **Độ trễ, độ tin cậy và chi phí:** tính đến data transfer, failure domain, retry và observability liên cloud.

**ManagedIdentityCredential** gắn với Azure runtime không tự xuất hiện trên VM AWS hoặc Pod GKE thông thường. Nếu môi trường ngoài Azure hỗ trợ OIDC, có thể cân nhắc **workload identity federation** tới Microsoft Entra với trust cấu hình đúng; nếu không, dùng cơ chế credential phù hợp và quản lý bí mật an toàn theo chính sách.

**Một số hạn chế đáng chú ý:**

- Private Endpoint của Storage trong VNet Azure không tự accessible từ mọi AWS/GCP workload; cần định tuyến và DNS phù hợp.
- Service Bus/Event Hubs có tính chất message ordering, at-least-once delivery và khác biệt protocol. Không mặc định thay được bằng SQS/Pub/Sub mà không sửa kiến trúc.
- Data residency và chi phí egress có thể quyết định nên đặt workload gần dữ liệu hơn.
- Container hosting có thể có lifecycle/scale khác Azure, dù cùng image và code.

## 13. Identity của runtime khác identity của pipeline triển khai

Một lỗi thiết kế phổ biến là **CI/CD deploy thành công**, sau đó suy ra ứng dụng sẽ đọc được Key Vault hay Blob. Trong thực tế có hai principal:

~~~mermaid
flowchart LR
    CI[CI/CD deployer] -->|ARM deployment permission| H[App Service / Container Apps / AKS]
    H --> APP[Spring Boot runtime identity]
    APP -->|Data-plane permission| B[Blob / Service Bus / Key Vault]
    P[Pipeline IAM role] -.-> CI
    R[Runtime data role] -.-> APP
~~~

| Đối tượng | Quyền cần thiết | Thường không cần |
| --- | --- | --- |
| **CI deployer** | Quyền cập nhật tài nguyên/triển khai artifact trong scope đã chọn | Đọc tất cả secret và dữ liệu production |
| **Runtime managed/workload identity** | Quyền dữ liệu tối thiểu trên Blob/Service Bus/Key Vault/Cosmos tương ứng | Quyền Owner trên subscription |
| **Developer local** | Quyền trên tài nguyên dev/test và log phù hợp | Quyền ứng dụng production |
| **Integration-test identity** | Quyền tài nguyên test và cleanup có kiểm soát | Quyền sửa dữ liệu thật ngoài scope lab |

Với Blob, một số role quản lý có thể có quyền gián tiếp lấy access key; vì vậy phải đánh giá kỹ **management actions** nhạy cảm, không chỉ xem DataActions. Ở Key Vault/Cosmos, cần xác định mô hình data-plane authorization của chính dịch vụ.

## 14. Network và endpoint: khác nhau theo nơi lưu trú

**Hosting** ảnh hưởng trực tiếp đến đường mạng; **thư viện** chỉ gửi request theo endpoint và transport đã cấu hình.

| Môi trường | Kiểm tra mạng đặc thù |
| --- | --- |
| Laptop | Internet/proxy doanh nghiệp, certificate trust, firewall máy |
| App Service | Outbound routing/VNet integration, DNS, access restrictions |
| Container Apps | VNet/environment network, egress và DNS |
| AKS | Pod DNS, CNI/network policy, node egress, private DNS, service mesh |
| VM | NSG/firewall, route, DNS, proxy, VM network settings |
| AWS/GCP/on-prem | Cross-cloud connectivity, egress IP, VPN/private network, DNS resolver |

### Hai luồng mạng cần kiểm tra riêng

Khi ứng dụng dùng **DefaultAzureCredential** hoặc managed/workload identity, có thể phát sinh hai luồng:

~~~text
Spring Boot runtime
    ├── identity/token flow → Entra / managed identity endpoint / token broker
    └── data flow → Blob / Service Bus / Key Vault service endpoint
~~~

Một HTTP proxy được cấu hình cho Blob client không chắc cũng được dùng bởi Azure Identity SDK khi lấy token. Một số client messaging sử dụng **AMQP** qua TCP/WebSockets, không dùng cùng HTTP transport với Blob. Thiết kế network phải xét **giao thức thật** của từng dịch vụ.

### Private Endpoint không thay thế Azure RBAC

Trong Azure VNet, một Storage Account có Private Endpoint thường vẫn được gọi bằng hostname dịch vụ chuẩn; DNS nội bộ có thể phân giải tới private IP qua cấu hình Private Link. Sử dụng IP trực tiếp hoặc hostname tự chế có thể gây lỗi TLS/endpoint.

Dù lưu trú ở AKS hay App Service, **Private Endpoint chỉ giải quyết tuyến mạng**; principal vẫn cần role Data Contributor/Reader tương ứng trên tài nguyên.

## 15. Vận hành: hosting và SDK chịu trách nhiệm phần nào?

| Vấn đề | Thuộc platform hosting | Thuộc app/SDK |
| --- | --- | --- |
| Bật số instance, CPU/RAM | Hosting autoscale và resource limits | Kiểm soát concurrency, connection pool |
| HTTP ingress/TLS tới người dùng | Ingress/reverse proxy/certificate configuration | Endpoint API, Spring Security |
| Credential cung cấp cho workload | Gắn managed identity, projected token, runtime env | TokenCredential, xác minh source được chọn |
| Gọi Blob thành công | Egress/network và resource reachable | Đúng endpoint, upload API, retry, error handling |
| Gửi/nhận Service Bus | Kết nối mạng, scale worker | Ack/settlement, retries, idempotency, DLQ |
| Metrics/log | Platform collection và monitoring backend | Business metrics, Azure SDK diagnostics, correlation IDs |
| Deployment rollback | Slots/revisions/rolling updates | Backward compatibility của schema và config |
| Bảo vệ secret | Secure environment/secret store, access policy | Không ghi token/secret ra log, không nhúng credential |

**Retry và scale** đặc biệt cần phối hợp: khi AKS hoặc Container Apps tăng replicas của consumer, cùng một queue có thể bị xử lý trùng hoặc tăng tải phụ trợ. SDK gửi message thành công không đảm bảo exactly-once ở tầng nghiệp vụ; cần idempotency và thiết kế luồng xử lý rõ ràng.

## 16. Kiểm thử sự độc lập giữa thư viện và hosting

### 16.1. Unit test phần nghiệp vụ

Đặt logic lưu trữ sau interface/adapter hoặc mock client phù hợp để kiểm tra:

- Dữ liệu đầu vào hợp lệ được chuyển thành lệnh upload đúng.
- Lỗi 403/404/409 và timeout được chuyển thành phản hồi nghiệp vụ thích hợp.
- Không cần Azure account/managed identity hay App Service đang chạy.
- Không buộc test phụ thuộc Azure CLI cache trên laptop.

Unit test khẳng định logic code, **chưa chứng minh identity/network**.

### 16.2. Integration test trên Azure dev/test

Chạy một thao tác thật với **runtime identity** tương ứng:

1. Bật đúng identity tại hosting; cấu hình endpoint và role trên Storage Account test.
2. Deploy ứng dụng hoặc job thử nghiệm.
3. Upload một blob có tên riêng, đọc lại rồi xóa/cleanup.
4. Ghi request ID, status/error code, latency, credential source ở mức được phép.
5. Kiểm thử trường hợp thiếu role trên resource test và trường hợp DNS/proxy sai có kiểm soát.
6. Xác minh test chạy bằng identity runtime, không phải phiên Azure CLI cá nhân.

**Azurite** giúp kiểm tra một phần API Blob ở local; nó không thay thế hoàn toàn Entra managed identity, Azure RBAC, private network hoặc managed service thật.

### 16.3. Smoke test sau deploy

Một kiểm tra chỉ xác nhận **Spring context khởi động** chưa đủ: nhiều Azure client khởi tạo mà chưa gọi service. Nên có một smoke test truy cập dữ liệu test hoặc một operation không phá hoại phù hợp, được giám sát và không vô tình làm tăng tải production.

### 16.4. Ma trận test chéo hosting

| Kiểm tra | Local | App Service | AKS |
| --- | --- | --- | --- |
| Spring Boot context khởi động | Có | Có | Có |
| Bean BlobServiceClient được cấu hình | Có | Có | Có |
| Credential của môi trường hoạt động | Azure CLI/dev identity | Managed identity | Workload identity |
| Data role đúng principal | Dev identity | App Service identity | Pod identity |
| DNS/egress tới endpoint | Laptop network | VNet/outbound | Pod/VNet network |
| Upload thử bằng đúng runtime identity | Có | Có | Có |

Các tiêu chí về code tương tự, nhưng **kết quả identity, network và scale không thể suy ra từ một môi trường duy nhất**.

## 17. Chẩn đoán lỗi: sai lớp nào?

| Triệu chứng | Lớp có thể liên quan | Hướng xử lý |
| --- | --- | --- |
| Build không tìm thấy starter | Dependency/BOM | Chọn đúng artifact và ma trận tương thích Spring Boot |
| Spring không tạo được BlobServiceClient | Auto-configuration/bean | Kiểm tra starter, application properties, bean ambiguity |
| App Service deploy thành công nhưng upload 403 | Runtime identity/RBAC hoặc network policy | Xác minh principal thực tế, data role, scope và service error |
| Local chạy nhưng AKS báo CredentialUnavailable | Workload identity wiring | Kiểm tra OIDC, service account, pod label, token file |
| Blob SDK timeout trong AKS | DNS/route/network | Debug từ Pod, Private Endpoint, outbound policy |
| App start rồi Function trigger không chạy | Hosting model | Kiểm tra Function runtime/trigger và cách đóng gói ứng dụng |
| Service Bus sender nhận 401/403 | Credential/authorization hoặc endpoint | Kiểm tra namespace, Entra token, Data Sender role |
| CI có quyền tạo Storage nhưng app không đọc được blob | Tách deploy identity và runtime identity | Gán role data plane cho đúng application identity |
| Cùng code chạy GCP nhưng không lấy được managed identity | Credential không phù hợp hosting | Thiết kế federation hoặc credential khác được hỗ trợ |
| Sai URL Blob dù subscription đúng | Service endpoint | Đối chiếu endpoint/account, tránh nhầm ARM resource ID |
| Nhiều replica tạo message trùng | Nghiệp vụ/scale | Idempotency, message settlement, retry và concurrency |

Một **403 từ Azure Blob** khác với **407 từ HTTP proxy**, cũng khác với **CredentialUnavailableException**. Cần đọc root cause, error code và xác định request có thật sự đến Azure hay chưa trước khi thay dependency hoặc gán role rộng hơn.

## 18. Bài thực hành: cùng một Spring Boot API trên hai nơi lưu trú

**Bối cảnh:** phát triển Documents API lưu file vào Blob container private **documents**. Mục tiêu là giữ lớp nghiệp vụ Java giống nhau khi chạy local và App Service, rồi phân tích cách chuyển sang AKS.

### Phần A — Chuẩn bị ứng dụng và dữ liệu test

1. Tạo project Spring Boot với starter Blob hoặc Azure SDK trực tiếp theo BOM/JDK tương thích.
2. Tạo hoặc được cấp Storage Account và container **documents** trong môi trường lab.
3. Viết service **DocumentsStorage** có phương thức upload, cấu hình account/container bằng biến môi trường.
4. Viết unit test thao tác Blob qua một abstraction được mock; tránh yêu cầu live Azure ở unit test.

### Phần B — Chạy local

1. Đăng nhập **az login** bằng tài khoản dev.
2. Cấp quyền ghi Blob ở scope test phù hợp cho principal dev.
3. Chạy Spring Boot, upload một blob có tên riêng và đọc lại.
4. Ghi lại endpoint, credential source đã xác nhận, mã lỗi (nếu có), latency và request ID.

### Phần C — Chạy App Service

1. Đóng gói chính ứng dụng đó thành JAR/container theo phương án hosting.
2. Bật managed identity cho App Service và cấp **Storage Blob Data Contributor** trên account/container test cho đúng principal.
3. Đặt application settings cho **AZURE_STORAGE_ACCOUNT** và **AZURE_BLOB_CONTAINER**; cấu hình credential mode theo SDK/version nếu cần.
4. Deploy, thực hiện upload tương tự, kiểm tra network và identity runtime.
5. Thu hồi quyền trên tài nguyên test để quan sát lỗi 403, sau đó khôi phục quyền lab.

### Phần D — Phân tích AKS

1. Mô tả manifest Pod/Deployment với service account và label Workload ID.
2. Liệt kê các thành phần federation issuer/subject/audience và role assignment phải cấu hình.
3. Giải thích vì sao **DocumentsStorage** không cần đổi, nhưng cấu hình Pod và Azure Identity phải đổi.
4. Đánh giá readiness/liveness, scale, retry và Private Endpoint nếu triển khai thật.

**Bảng kết quả đề xuất:**

| Nội dung | Local | App Service | AKS (thiết kế) |
| --- | --- | --- | --- |
| Artifact | JAR Spring Boot | Cùng JAR/container | Cùng container |
| Library | Spring Cloud Azure Blob starter | Cùng starter | Cùng starter |
| Runtime identity | Developer/CLI | Managed identity | Workload identity |
| Data role | Dev principal | App Service principal | Pod/Entra principal |
| Network | Local egress | App Service outbound | Pod/VNet egress |
| Bằng chứng | Upload test + SDK log | Upload test + platform log | Manifest + kế hoạch test |

### Câu hỏi tự kiểm tra

1. Vì sao ứng dụng chạy trên App Service chưa chắc phải có dependency Spring Cloud Azure?
2. Spring Cloud Azure có bắt buộc ứng dụng chạy trên nền tảng Azure không?
3. Khi chuyển từ local lên App Service, những phần nào của ứng dụng có thể giữ nguyên và những cấu hình nào buộc phải thay đổi?
4. Việc bật managed identity ở App Service có tự cấp quyền ghi Blob không?
5. Sự khác nhau giữa identity của CI deployer và identity của Spring Boot runtime là gì?
6. Khi một Pod AKS dùng Workload Identity, vì sao quyền của node chưa phải bằng chứng Pod đã có quyền dữ liệu?
7. Vì sao Private Endpoint và RBAC giải quyết hai vấn đề khác nhau?
8. Khi đưa Spring Boot từ Azure sang AWS nhưng vẫn dùng Blob Storage, những rủi ro ngoài mã Java cần đánh giá?
9. Azure Functions có thể nhận mọi executable Spring Boot JAR làm HTTP Function mà không thay đổi đóng gói không?
10. Vì sao Spring context khởi động thành công chưa chứng minh Blob client đã truy cập được dữ liệu?

## 19. Ghi nhớ

- **Spring Cloud Azure / Azure SDK for Java** là lựa chọn tích hợp ở tầng thư viện. **App Service, Container Apps, AKS, Functions, VM** là lựa chọn lưu trú/vận hành ứng dụng.
- Ứng dụng Spring Boot chạy trên Azure không nhất thiết dùng Spring Cloud Azure; ứng dụng dùng Spring Cloud Azure không nhất thiết chạy trên Azure.
- Hosting cung cấp runtime, scale, network và khả năng identity; starter/SDK cung cấp client và API truy cập managed service. **Azure RBAC không được cấp tự động bởi cả hai.**
- Giữ code nghiệp vụ độc lập môi trường; cấu hình endpoint, credential mode, role và network ở ranh giới triển khai. Kiểm tra tương thích BOM/SDK, dependency và cloud service thực sự dùng.
- Kiểm thử bằng **danh tính và đường mạng của runtime đích**; phân biệt lỗi library, hosting, authentication, authorization và network.
- Khi làm tích hợp đa cloud AWS/Azure/GCP, phải so sánh **mô hình danh tính, data semantics, độ trễ, egress cost, khả năng quan sát và vòng đời dịch vụ** cùng với việc chọn starter.

## Tài liệu tham khảo

- [Spring Cloud Azure overview and documentation](https://learn.microsoft.com/azure/developer/java/spring-framework/)
- [Azure SDK for Java overview](https://learn.microsoft.com/azure/developer/java/sdk/overview)
- [Azure App Service overview](https://learn.microsoft.com/azure/app-service/overview)
- [Azure Container Apps overview](https://learn.microsoft.com/azure/container-apps/overview)
- [Azure Kubernetes Service overview](https://learn.microsoft.com/azure/aks/intro-kubernetes)
- [Azure Functions overview](https://learn.microsoft.com/azure/azure-functions/functions-overview)
- [Managed identities for Azure resources](https://learn.microsoft.com/entra/identity/managed-identities-azure-resources/overview)
- [Microsoft Entra Workload ID for AKS](https://learn.microsoft.com/azure/aks/workload-identity-overview)
- [Azure RBAC overview](https://learn.microsoft.com/azure/role-based-access-control/overview)
