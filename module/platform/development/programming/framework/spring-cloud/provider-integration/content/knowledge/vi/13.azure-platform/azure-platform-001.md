# Spring Cloud Azure, Azure SDK for Java và phạm vi các starter

Trong một ứng dụng Spring Boot triển khai trên Azure, có hai cách thường gặp để giao tiếp với dịch vụ đám mây: dùng **Azure SDK for Java** trực tiếp hoặc dùng **Spring Cloud Azure** để tích hợp SDK vào cơ chế cấu hình và quản lý bean của Spring. Hiểu đúng sự khác biệt giúp chọn phụ thuộc vừa đủ, cấu hình xác thực nhất quán và tránh nhầm lẫn giữa tiện ích tự động cấu hình với khả năng thực sự của dịch vụ Azure.

Bài học thuộc chương **Nền tảng Azure**, trong phạm vi module **SPRING_CLOUD_PROVIDER_INTEGRATION**: thực hành kết nối Spring Boot với dịch vụ managed của AWS, Azure và Google Cloud thông qua thư viện Spring Cloud tương ứng; chú trọng danh tính, quyền truy cập, storage, messaging, dữ liệu, secret, kiểm thử tích hợp và khả năng so sánh giữa các nhà cung cấp.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích vai trò khác nhau của Azure SDK for Java, Spring Cloud Azure và một Spring Cloud Azure starter.
2. Nhận diện nhóm starter phù hợp với Blob Storage, Service Bus, Event Hubs, Key Vault, Cosmos DB, App Configuration và tích hợp Microsoft Entra ID.
3. Cấu hình dependency management để giảm xung đột phiên bản và sử dụng danh tính Azure thay cho việc nhúng khóa vào mã nguồn.
4. Tự tích hợp Blob Storage theo hai hướng: Spring Cloud Azure tự cấu hình client hoặc Azure SDK tạo client trực tiếp.
5. Xác định ranh giới trách nhiệm giữa ứng dụng, thư viện, hệ thống IAM/RBAC, tài nguyên cloud và kiểm thử tích hợp.

## 2. Ba lớp cần phân biệt

| Thành phần | Trách nhiệm chính | Đơn vị điển hình | Khi nào chọn |
| --- | --- | --- | --- |
| **Azure SDK for Java** | Gọi API dữ liệu/quản trị của dịch vụ Azure; quản lý HTTP pipeline, xác thực, retry và đối tượng client theo API SDK | Thư viện **azure-storage-blob**, **azure-messaging-servicebus**, **azure-identity** | Ứng dụng Java thuần hoặc cần điều khiển SDK chi tiết, kể cả trong Spring Boot |
| **Spring Cloud Azure** | Kết nối các Azure SDK với mô hình **Spring Boot auto-configuration**, cấu hình ngoài ứng dụng, dependency injection và các tích hợp thuộc hệ sinh thái Spring | Các module dưới group **com.azure.spring** | Dự án Spring Boot muốn giảm mã cấu hình lặp lại và theo quy ước Spring |
| **Spring Cloud Azure starter** | Gói phụ thuộc theo một nhu cầu tích hợp, thường kéo theo phần tự cấu hình cùng các SDK cần thiết | **spring-cloud-azure-starter-storage-blob** | Đã xác định rõ dịch vụ hoặc kiểu tích hợp cần dùng |

Hai lớp đầu không loại trừ nhau. **Spring Cloud Azure sử dụng Azure SDK ở bên dưới**: khi inject một **BlobServiceClient** từ Spring, ứng dụng vẫn gọi các API của Azure SDK. Starter giúp đăng ký, cấu hình và quản lý client; nó không tạo ra Blob container, Service Bus namespace, Cosmos DB account hoặc cấp quyền Azure thay cho đội vận hành.

~~~mermaid
flowchart TD
    A[REST API / service Spring Boot] --> B[Bean Azure client do Spring Cloud Azure tự cấu hình]
    B --> C[Azure SDK for Java]
    C --> D[azure-identity / TokenCredential]
    C --> E[Azure Blob / Service Bus / Cosmos DB ...]
    F[application.yml + biến môi trường] --> B
    G[Microsoft Entra ID và Azure RBAC] --> D
    D --> E
~~~

**Chốt ranh giới:** starter quyết định *cách nối SDK vào Spring*; Azure SDK quyết định *cách gọi dịch vụ*; Azure identity/RBAC và hạ tầng quyết định *lời gọi có được cho phép và kết nối được hay không*.

## 3. Azure SDK for Java gồm những gì?

Azure SDK for Java là tập hợp thư viện theo từng dịch vụ, không phải một client duy nhất cho toàn bộ Azure.

- **azure-core**: các thành phần chung như pipeline, HTTP, phản hồi, policy, lỗi và cơ chế retry.
- **azure-identity**: các triển khai **TokenCredential**, ví dụ **DefaultAzureCredential**, **ManagedIdentityCredential** và **ClientSecretCredential**.
- **azure-storage-blob**: **BlobServiceClient**, **BlobContainerClient**, **BlobClient** và các biến thể async để thao tác object trong Blob Storage.
- **azure-messaging-servicebus**: gửi/nhận message, xử lý queue hoặc topic/subscription.
- **azure-messaging-eventhubs**: trao đổi sự kiện thông lượng cao qua Event Hubs.
- **azure-security-keyvault-secrets**: **SecretClient** cho Azure Key Vault Secrets.
- **azure-cosmos**: client thao tác Azure Cosmos DB.

Đa số client SDK có kiểu **đồng bộ** và/hoặc **bất đồng bộ**. Chọn client theo mô hình thực thi: một ứng dụng Spring MVC thông thường có thể dùng client đồng bộ; một luồng xử lý không chặn cần đánh giá client async và cơ chế backpressure. Không gọi các thao tác chặn của SDK ngay trên event loop của WebFlux.

Client SDK thường được thiết kế để **tái sử dụng**, vì thế nên quản lý vòng đời tập trung (singleton/bean) thay vì tạo client mới cho mỗi HTTP request. HTTP pipeline, kết nối, chính sách retry và logging cần được quan sát theo SDK và phiên bản thực tế.

### Xác thực với TokenCredential

**DefaultAzureCredential** thử các nguồn thông tin đăng nhập được hỗ trợ trong môi trường chạy, chẳng hạn biến môi trường phù hợp, workload identity, managed identity hoặc phiên đăng nhập công cụ phát triển. Các nguồn cụ thể và thứ tự có thể thay đổi theo phiên bản SDK và nền tảng.

- **Máy phát triển:** lập trình viên có thể đăng nhập Azure CLI và cấp quyền dữ liệu thích hợp cho danh tính của mình.
- **Azure runtime:** ưu tiên managed identity hoặc workload identity khi môi trường hỗ trợ, gán role ở phạm vi nhỏ nhất có thể.
- **CI/CD:** dùng liên kết danh tính liên hợp (federated identity) nếu hạ tầng hỗ trợ; tránh lưu client secret dài hạn.
- **Sản xuất:** hiểu danh tính nào thực tế được chọn. Credential chain thuận tiện trong phát triển nhưng có thể chọn nhầm danh tính nếu môi trường chứa nhiều nguồn credential.

Xác thực thành công chỉ cho biết Azure đã nhận diện principal. **Authorization** vẫn phụ thuộc RBAC hoặc chính sách truy cập của từng dịch vụ. Ví dụ, đăng nhập thành công không đồng nghĩa được upload blob.

## 4. Phạm vi của các Spring Cloud Azure starter

Tên artifact có thể thay đổi hoặc được tách theo dòng phiên bản. Bảng dưới đây nêu các starter phổ biến trong hệ Spring Cloud Azure hiện đại; trước khi thêm dependency, cần kiểm tra **bảng tương thích Spring Boot / Spring Cloud Azure** và tài liệu của phiên bản đang dùng.

| Starter (group **com.azure.spring**) | Phạm vi giải quyết | Điều không nên suy diễn |
| --- | --- | --- |
| **spring-cloud-azure-starter** | Hạ tầng cấu hình Azure chung và các thành phần nền cho tích hợp Spring | Không tự động kích hoạt mọi dịch vụ Azure |
| **spring-cloud-azure-starter-storage-blob** | Cấu hình và sử dụng Azure Blob Storage client trong Spring Boot | Không tự tạo storage account/container, không cấp quyền đọc/ghi |
| **spring-cloud-azure-starter-servicebus** | Tích hợp Service Bus queue và topic/subscription qua các thành phần được hỗ trợ | Không biến Service Bus thành giao thức Kafka; không thay thế thiết kế xử lý trùng message |
| **spring-cloud-azure-starter-eventhubs** | Tích hợp Azure Event Hubs để thu phát luồng sự kiện | Không tự cung cấp nghiệp vụ checkpoint, partition strategy hoặc retention |
| **spring-cloud-azure-starter-keyvault-secrets** | Tải/truy cập secret từ Key Vault, bao gồm tích hợp nguồn cấu hình khi được cấu hình đúng | Không mặc nhiên hỗ trợ mọi API của Key Vault Keys/Certificates |
| **spring-cloud-azure-starter-data-cosmos** | Kết hợp Azure Cosmos DB với các cơ chế Spring Data được hỗ trợ | Không phải starter cho mọi loại database Azure hay mọi API Cosmos |
| **spring-cloud-azure-starter-appconfiguration** | Tích hợp Azure App Configuration với cấu hình ứng dụng, một số cơ chế refresh/feature flag theo phiên bản | Không thay thế secret vault hoặc hệ thống quản trị cấu hình triển khai |
| **spring-cloud-azure-starter-active-directory** | Tích hợp Microsoft Entra ID với các luồng xác thực/ủy quyền được hỗ trợ của Spring Security | Không tự gán Azure RBAC cho ứng dụng khi truy cập Blob, Key Vault hay Service Bus |

Cách nhóm nhu cầu thực tế:

- **Storage:** Blob là object storage; không đồng nhất với Azure Files hoặc Storage Queues. Chọn starter đúng dịch vụ và đúng kiểu dữ liệu.
- **Messaging:** Service Bus phù hợp command, tác vụ bất đồng bộ và pub/sub nghiệp vụ; Event Hubs phù hợp ingestion/streaming lượng lớn. Hai hệ thống có mô hình tiêu thụ và vận hành khác nhau.
- **Dữ liệu:** Cosmos DB là dịch vụ database; starter Spring Data giúp thao tác theo abstraction của Spring, nhưng thiết kế partition key, consistency và RU vẫn là trách nhiệm ứng dụng.
- **Bảo mật/cấu hình:** Key Vault lưu secret; App Configuration lưu cấu hình ứng dụng; Entra ID thực hiện định danh. Các hệ thống này bổ sung cho nhau nhưng không thay thế nhau.
- **Ngoài phạm vi starter:** nếu một API Azure chưa có starter tương ứng hoặc starter thiếu chức năng nâng cao, sử dụng **Azure SDK trực tiếp** là hướng hợp lệ.

**Quy tắc chọn:** bắt đầu từ *khả năng của dịch vụ cần tích hợp*, sau đó xem có starter hỗ trợ phần API mong muốn không. Không thêm tất cả starter vào một ứng dụng chỉ vì cùng dùng Azure.

## 5. Dependency management và tương thích phiên bản

Spring Boot, Spring Cloud Azure và Azure SDK cùng tham gia dependency graph. Một phiên bản starter không phù hợp với Spring Boot, hoặc các phiên bản **azure-core / azure-identity** bị ép riêng lẻ, có thể dẫn đến lỗi khởi tạo bean hay lỗi linkage khi chạy.

Với Maven, một dự án Spring Boot có thể import BOM của Spring Cloud Azure rồi khai báo starter không ghi phiên bản từng artifact:

~~~xml
<!-- Trích đoạn pom.xml: khai báo thuộc tính spring-cloud-azure.version
     theo bảng tương thích chính thức với Spring Boot đang dùng. -->
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.azure.spring</groupId>
            <artifactId>spring-cloud-azure-dependencies</artifactId>
            <version>${spring-cloud-azure.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>com.azure.spring</groupId>
        <artifactId>spring-cloud-azure-starter-storage-blob</artifactId>
    </dependency>
</dependencies>
~~~

Đây là **trích đoạn**, chưa phải toàn bộ POM: dự án cần có Spring Boot parent hoặc cách quản lý dependency Spring Boot tương đương, cùng giá trị thực của **spring-cloud-azure.version**. Không chọn một số version ngẫu nhiên; tra bảng tương thích của chính release trước khi build. Trong các dự án chỉ dùng SDK trực tiếp, có thể cân nhắc **com.azure:azure-sdk-bom** để đồng bộ nhóm thư viện Azure SDK.

Khi phát sinh xung đột, kiểm tra cây phụ thuộc bằng **mvn dependency:tree** (hoặc cơ chế tương đương của Gradle), loại bỏ version override không cần thiết và xem release notes khi nâng cấp. Không trộn tùy tiện các artifact của thế hệ Spring Cloud Azure cũ với nhóm **com.azure.spring** hiện đại.

## 6. Thực hành: Spring Boot ghi tệp vào Azure Blob Storage

### 6.1. Chuẩn bị tài nguyên và quyền

Giả sử ứng dụng cần lưu tài liệu vào container **documents** thuộc storage account **myappstorage**. Cần có:

1. Storage account và Blob container **documents** đã được tạo bằng portal, IaC hoặc công cụ quản trị.
2. Danh tính của người chạy ứng dụng đã đăng nhập hoặc danh tính workload/managed identity của runtime.
3. Quyền dữ liệu tối thiểu, chẳng hạn role **Storage Blob Data Contributor** ở phạm vi container hoặc storage account phù hợp nếu ứng dụng phải ghi blob.
4. Đường mạng và DNS cho endpoint Blob Storage, đặc biệt khi dùng firewall/private endpoint.

Không nên nhầm role quản lý tài nguyên (management plane) với role truy cập dữ liệu Blob (data plane). Sau khi gán RBAC có thể cần thời gian để quyền có hiệu lực.

### 6.2. Cấu hình Spring Cloud Azure

Thêm **spring-cloud-azure-starter-storage-blob** theo BOM ở phần trước. Trong **application.yml**:

~~~yaml
spring:
  cloud:
    azure:
      storage:
        blob:
          account-name: ${AZURE_STORAGE_ACCOUNT}
~~~

Khai báo biến môi trường **AZURE_STORAGE_ACCOUNT=myappstorage** ở môi trường chạy. Ví dụ dùng cơ chế credential mặc định mà Spring Cloud Azure hỗ trợ trong phiên bản đã chọn; không đặt connection string hoặc access key trong repository. Nếu cần chỉ định credential hoặc endpoint riêng, dùng đúng thuộc tính được tài liệu hóa cho version đang triển khai.

Dịch vụ lưu tài liệu có thể nhận **BlobServiceClient** do starter tự cấu hình:

~~~java
import com.azure.storage.blob.BlobClient;
import com.azure.storage.blob.BlobContainerClient;
import com.azure.storage.blob.BlobServiceClient;
import java.io.ByteArrayInputStream;
import org.springframework.stereotype.Service;

@Service
public class DocumentStorageService {

    private final BlobContainerClient containerClient;

    public DocumentStorageService(BlobServiceClient blobServiceClient) {
        this.containerClient =
                blobServiceClient.getBlobContainerClient("documents");
    }

    public String upload(String blobName, byte[] bytes) {
        BlobClient blobClient = containerClient.getBlobClient(blobName);
        blobClient.upload(
                new ByteArrayInputStream(bytes), bytes.length, true);
        return blobClient.getBlobUrl();
    }
}
~~~

Phương thức minh họa upload với tùy chọn **overwrite=true**; ứng dụng thực tế phải cân nhắc nguy cơ ghi đè, chuẩn hóa tên blob, kiểm soát kích thước, loại nội dung và quy tắc phân quyền. **getBlobUrl()** trả về địa chỉ blob, **không có nghĩa URL này được truy cập công khai**. Nếu container private, người đọc vẫn phải có quyền hợp lệ hoặc URL có ủy quyền như SAS được cấp theo nhu cầu.

Ứng dụng trên không cần tự dựng **BlobServiceClientBuilder** vì starter làm nhiệm vụ cấu hình bean. Nếu application context có nhiều bean cùng kiểu hoặc cần nhiều storage account, hãy cấu hình bean/named client một cách tường minh theo version đang sử dụng.

### 6.3. Cùng bài toán với Azure SDK trực tiếp

Nếu không dùng starter, lập trình viên tự tạo SDK client, endpoint và credential. Ví dụ sau dùng các thư viện **azure-identity** và **azure-storage-blob**:

~~~java
import com.azure.core.credential.TokenCredential;
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.storage.blob.BlobServiceClient;
import com.azure.storage.blob.BlobServiceClientBuilder;

public final class AzureBlobClients {

    public static BlobServiceClient create(String accountName) {
        TokenCredential credential =
                new DefaultAzureCredentialBuilder().build();

        return new BlobServiceClientBuilder()
                .endpoint("https://" + accountName + ".blob.core.windows.net")
                .credential(credential)
                .buildClient();
    }
}
~~~

Trong Spring Boot, có thể đặt đoạn tạo client này vào một phương thức **@Bean** và inject client ở nơi sử dụng. Cách SDK trực tiếp hữu ích khi cần nhiều tài khoản, cấu hình pipeline chuyên biệt, một API chưa được starter hỗ trợ hoặc tái sử dụng logic ở ứng dụng không chạy Spring.

**So sánh hai hướng:** phần nghiệp vụ upload sử dụng cùng API **BlobClient**; khác biệt nằm ở nơi khởi tạo client, nạp cấu hình và quản lý vòng đời. Không cần tạo client thủ công thứ hai nếu bean do starter cung cấp đã đáp ứng yêu cầu.

## 7. Mở rộng từ Blob sang các nhóm dịch vụ khác

### Service Bus và Event Hubs

Một đơn hàng có thể phát thông điệp **OrderCreated** vào Service Bus queue để worker xử lý bất đồng bộ. Một luồng telemetry hàng triệu sự kiện phù hợp Event Hubs hơn. Dù dùng starter hay SDK, cần xác định:

- **At-least-once:** phía tiêu thụ phải xử lý message trùng bằng idempotency key hoặc trạng thái đã xử lý.
- **Retry và dead-letter:** lỗi tạm thời và lỗi nghiệp vụ phải có chính sách khác nhau; giám sát dead-letter queue đối với Service Bus.
- **Thứ tự và phân vùng:** không giả định thứ tự toàn cục khi chạy nhiều consumer; Event Hubs có khái niệm partition và checkpoint.
- **Danh tính/ủy quyền:** principal gửi và nhận cần các role dữ liệu tương ứng, chẳng hạn **Azure Service Bus Data Sender/Receiver** hoặc **Azure Event Hubs Data Sender/Receiver**.

### Cosmos DB

Starter Spring Data Cosmos có thể giảm phần wiring repository, song thiết kế **partition key**, mô hình truy vấn, consistency, throughput/RU, index và chiến lược xử lý **429/throttling** vẫn quyết định hiệu quả hệ thống. Không dùng repository abstraction để che giấu chi phí đọc chéo partition hoặc hiểu nhầm tính nhất quán.

### Key Vault và App Configuration

Key Vault thích hợp lưu mật khẩu, token hoặc secret cần quản lý vòng đời; App Configuration thích hợp quản lý khóa cấu hình và feature flag. Truy cập secret thông qua danh tính dịch vụ thay vì chép secret vào file YAML. Trong vận hành cần quản lý rotation, độ trễ refresh/cache, quyền đọc secret và failure mode khi Key Vault/App Configuration không khả dụng.

## 8. Lựa chọn starter hay SDK trực tiếp

| Tiêu chí | Chọn Spring Cloud Azure starter | Chọn Azure SDK trực tiếp |
| --- | --- | --- |
| Ứng dụng Spring Boot, một dịch vụ Azure phổ biến | Thường phù hợp nhờ auto-configuration, Spring properties, injection | Hợp lệ nhưng cần nhiều mã wiring hơn |
| Ứng dụng Java không dùng Spring | Không phù hợp với mục tiêu tích hợp | Phù hợp |
| Nhiều account/tenant, endpoint hoặc pipeline riêng | Cần kiểm tra hỗ trợ cấu hình nhiều client của version | Chủ động tạo các client tách biệt |
| API đặc biệt hoặc chưa có starter | Có thể cần SDK bổ sung | Phù hợp trực tiếp |
| Tối ưu số dependency và kiểm soát lifecycle | Kiểm tra dependency graph của starter | Có thể chỉ lấy đúng các SDK cần thiết |
| Test theo phong cách Spring Boot | Có thể override/mock bean và dùng test context | Có thể inject client/interface qua cấu hình ứng dụng |

Có thể kết hợp hai hướng trong một hệ thống, ví dụ starter cho Blob Storage và SDK trực tiếp cho một API Azure chuyên biệt. Tuy nhiên phải giữ các phiên bản SDK nhất quán và định rõ nơi quản lý từng client để tránh bean trùng hoặc credential phân tán.

## 9. Kiểm thử, quan sát và xử lý sự cố

Một dự án tích hợp Azure không nên chỉ dừng ở việc Spring context khởi động thành công. Nên kiểm thử theo ba tầng:

1. **Unit test:** mock/wrap lớp truy cập Blob, mô phỏng upload thành công, lỗi quyền, timeout và trùng tên; không cần tài khoản Azure.
2. **Integration test ở môi trường cục bộ:** với Blob, có thể dùng **Azurite** cho những API được emulator hỗ trợ. Phải nêu rõ khác biệt giữa emulator và Azure thật, nhất là xác thực/RBAC, network, một số API và behavior.
3. **Integration test trên tài nguyên Azure thử nghiệm:** dùng danh tính thật để xác minh RBAC, private endpoint/DNS, chính sách bảo mật, retry/throttling, quyền đọc/ghi và cleanup tài nguyên thử nghiệm. Những dịch vụ không có emulator đủ tương đương cần môi trường kiểm thử chuyên biệt.

Bảng chẩn đoán ban đầu:

| Dấu hiệu | Khả năng thường gặp | Hướng kiểm tra |
| --- | --- | --- |
| Spring không khởi tạo được Azure client bean | Thiếu starter, cấu hình không phù hợp version, dependency xung đột | Kiểm tra auto-configuration, thuộc tính ứng dụng và dependency tree |
| Credential chain không tìm được danh tính | Chưa đăng nhập CLI, workload identity/managed identity chưa cấu hình hoặc môi trường không đúng | Xác minh nguồn credential thực sự được chọn và thiết lập runtime |
| **401** khi gọi API | Token thiếu, hết hạn hoặc không hợp lệ với dịch vụ | Kiểm tra đối tượng cấp token, audience/endpoint và cấu hình tenant |
| **403** dù đã đăng nhập | Thiếu role data-plane, gán sai scope hoặc policy mạng | Kiểm tra RBAC ở đúng tài nguyên, firewall/private endpoint |
| **404** hoặc **409** với Blob | Sai tên account/container/blob, tài nguyên chưa tồn tại hoặc xung đột trạng thái | Kiểm tra endpoint, tên tài nguyên và điều kiện thao tác |
| **429**, timeout hay lỗi mạng thoáng qua | Throttling, giới hạn tài nguyên, DNS/kết nối hoặc lưu lượng đột biến | Theo dõi metric, hạn mức, retry/backoff có giới hạn và idempotency |

Khi ghi log/trace, có thể ghi mã lỗi, correlation/request ID, tên operation và thời lượng, nhưng **không ghi access token, connection string, nội dung secret, SAS URL hoặc dữ liệu nhạy cảm**. Với upload/retry, kiểm tra tác động của việc chạy lại thao tác: retry thư viện không thay thế chính sách idempotency của nghiệp vụ.

## 10. Liên hệ bài học tích hợp đa cloud

| Mục đích | Azure | AWS | Google Cloud |
| --- | --- | --- | --- |
| Client Java cấp thấp | Azure SDK for Java | AWS SDK for Java | Google Cloud Java client libraries |
| Tích hợp theo hệ sinh thái Spring | Spring Cloud Azure | Spring Cloud AWS | Spring Cloud GCP |
| Object storage | Azure Blob Storage | Amazon S3 | Cloud Storage |
| Queue/pub-sub | Service Bus / Event Hubs tùy bài toán | SQS / SNS / Kinesis tùy bài toán | Pub/Sub |
| Danh tính workload | Managed Identity / Workload Identity + Entra ID | IAM Role / temporary credentials | Service Account / Workload Identity |
| Quản lý secret | Azure Key Vault | AWS Secrets Manager | Secret Manager |

Đây là **bản đồ khái niệm**, không phải khẳng định các dịch vụ có cùng semantics. Khi chuyển provider, vẫn phải phân tích lại cơ chế phân quyền, endpoint, consistency, event ordering, retry, chi phí và giới hạn dịch vụ. Việc ẩn SDK sau một interface nghiệp vụ có thể giúp giảm phụ thuộc trực tiếp, nhưng không xóa bỏ khác biệt về mô hình dữ liệu và vận hành.

## 11. Bài tập tự thực hành

Xây một Spring Boot API nhận nội dung tệp và trả về blob name sau khi lưu vào container private:

1. Tạo storage account/container thử nghiệm và cấp quyền dữ liệu ghi đúng scope cho danh tính chạy app.
2. Dùng BOM tương thích, thêm **spring-cloud-azure-starter-storage-blob**, cấu hình account name qua biến môi trường.
3. Inject **BlobServiceClient**, kiểm tra điều kiện đầu vào, tải blob lên và trả về định danh. Thử với hai blob cùng tên để quan sát hậu quả của overwrite.
4. Viết unit test mô phỏng lỗi upload; sau đó thử một integration test bằng Azurite hoặc tài nguyên Azure test phù hợp.
5. Thay bean do starter cung cấp bằng client tạo thủ công từ **DefaultAzureCredential** trong nhánh thực hành, ghi lại phần cấu hình bổ sung phải tự chịu trách nhiệm.
6. So sánh với S3/GCS ở mức danh tính, role, cấu hình endpoint, cách upload, trường hợp lỗi và chi phí vận hành.

**Câu hỏi tự kiểm tra:** Nếu Spring Boot tạo được **BlobServiceClient** nhưng API upload trả về **403**, nên tìm lỗi ở Spring starter hay quyền truy cập Azure? Vì sao? Nếu ứng dụng chuyển từ Service Bus sang Event Hubs, phần nào của thiết kế consumer không thể giữ nguyên?

## 12. Ghi nhớ

- **Azure SDK** cung cấp API thực hiện thao tác với dịch vụ; **Spring Cloud Azure** cung cấp cách nối các API đó vào ứng dụng Spring; **starter** đóng gói phần phụ thuộc/tự cấu hình theo nhu cầu.
- Bắt đầu từ dịch vụ và khả năng cần dùng, chọn starter tối thiểu, quản lý dependency bằng BOM và kiểm tra ma trận tương thích của phiên bản.
- Ưu tiên danh tính workload/managed identity và RBAC tối thiểu; **authentication**, **authorization** và **network access** là các điều kiện độc lập.
- Auto-configuration không thay thế thiết kế idempotency, retry, partitioning, observability, kiểm thử trên tài nguyên thật hoặc quản lý chi phí.
