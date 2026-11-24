# Managed identity, SAS và quyền truy cập Azure Storage trong Spring Boot

## 1. Bài toán và mục tiêu

Trong module **SPRING_CLOUD_PROVIDER_INTEGRATION**, chúng ta tích hợp Spring Boot với các dịch vụ managed của AWS, Azure và Google Cloud qua hệ sinh thái Spring Cloud tương ứng. Bài này thuộc chương **Azure Storage** và giải quyết ba câu hỏi luôn xuất hiện khi kết nối ứng dụng với Blob Storage, Queue Storage hoặc Azure Files:

1. **Ứng dụng là ai?** Azure xác thực danh tính bằng cách nào khi code chạy trên máy nhà phát triển, trên Azure App Service hay trong một container?
2. **Danh tính được làm gì?** Quyền đọc, ghi, xóa blob; gửi/nhận queue message; hoặc truy cập file share được cấp ở đâu?
3. **Làm sao cấp quyền tạm thời cho trình duyệt hoặc dịch vụ khác?** Khi nào nên dùng **Shared Access Signature (SAS)** và làm sao giới hạn phạm vi, thời gian, hành động?

Ví dụ xuyên suốt: một API Spring Boot nhận hồ sơ PDF, lưu vào container riêng tư `documents`, gửi job xử lý qua Azure Queue Storage; người dùng đã đăng nhập được tải tài liệu mình sở hữu. API chạy trong Azure bằng **managed identity**. Trình duyệt chỉ nhận một **URL SAS đọc một blob** nếu backend đã xác minh quyền.

Mục tiêu sau bài học:

- Phân biệt **authentication** (xác thực danh tính), **authorization** (ủy quyền truy cập) và **network access** (đường mạng).
- Chọn đúng **system-assigned** hoặc **user-assigned managed identity** và biết nguyên tắc lấy token.
- Cấp quyền **data plane** tối thiểu cho Blob, Queue và hiểu giới hạn của Azure Files SMB/NFS/REST.
- Phân biệt **user delegation SAS**, **service SAS**, **account SAS**, nắm rủi ro của account key và SAS bị lộ.
- Cấu hình Spring Cloud Azure/Azure SDK theo môi trường, tạo SAS ngắn hạn, chẩn đoán lỗi 401/403 và thiết kế kiểm thử.

## 2. Ba lớp kiểm soát truy cập: danh tính, quyền và mạng

Một request thành công thường cần đồng thời thỏa mãn:

~~~mermaid
flowchart LR
    A[Spring Boot / Client] --> I{Xác thực}
    I -->|Microsoft Entra token / SAS / key| R{Ủy quyền}
    R -->|RBAC hoặc chữ ký SAS và scope| N{Network}
    N -->|Firewall / endpoint / DNS / TLS| S[(Azure Storage)]
    I -->|Sai| E1[Từ chối]
    R -->|Sai| E2[Từ chối]
    N -->|Sai| E3[Không kết nối hoặc bị chặn]
~~~

Ba lớp có trách nhiệm khác nhau:

| Lớp | Câu hỏi chính | Ví dụ |
|---|---|---|
| Authentication | Ai đang gọi? Hoặc request mang bằng chứng truy cập nào? | Microsoft Entra ID token của managed identity; SAS token; account key |
| Authorization | Principal/token được làm hành động gì trên resource nào? | `Storage Blob Data Reader` ở container `documents`; SAS chỉ có quyền `r` trên một blob |
| Network | Request có đến được endpoint không? | Storage firewall, private endpoint, NSG, DNS, HTTPS |

**Không nhầm management plane với data plane.** Một tài khoản có quyền `Contributor` trên Azure Resource Manager có thể quản lý resource Azure nhưng chưa chắc đọc được dữ liệu Blob/Queue bằng Microsoft Entra token. Ngược lại, danh tính có `Storage Blob Data Reader` đọc blob được cấp quyền nhưng không tự có quyền tạo storage account. Một số quyền management plane, đặc biệt quyền **liệt kê account key**, gián tiếp tạo khả năng truy cập dữ liệu qua Shared Key; vì vậy phải kiểm soát cả hai lớp.

**SAS là bearer credential:** ai sở hữu URL SAS hợp lệ đều có thể sử dụng trong phạm vi nó cấp, trừ khi bị chặn bởi những điều kiện khác (như mạng, hạn dùng, IP/protocol được giới hạn). SAS **không tự kiểm tra** người dùng cuối đang đăng nhập vào ứng dụng là ai.

## 3. Managed identity là gì?

**Managed identity** là danh tính ứng dụng được Azure quản lý trong Microsoft Entra ID. Tài nguyên chạy ứng dụng có thể yêu cầu **access token** để gọi Azure Storage mà không phải lưu client secret hoặc password trong code. SDK dùng token đó để gửi request tới các endpoint Azure Storage hỗ trợ OAuth.

### 3.1. System-assigned và user-assigned

| Tiêu chí | System-assigned managed identity | User-assigned managed identity |
|---|---|---|
| Vòng đời | Gắn với một Azure resource; khi xóa resource, danh tính gắn theo bị xóa | Là tài nguyên Azure độc lập, có vòng đời riêng |
| Tái sử dụng | Thường gắn cho đúng resource đó | Có thể gán cho nhiều resource được hỗ trợ |
| Cấu hình client | Runtime thường tự nhận diện danh tính gắn với resource | Có thể cần **client ID** (hoặc định danh khác được SDK hỗ trợ) để chọn đúng identity |
| Phân quyền | Gán RBAC cho principal của resource | Gán RBAC cho principal của user-assigned identity |
| Khi phù hợp | Một ứng dụng độc lập, vòng đời identity theo ứng dụng | Nhiều deployment dùng chung identity hoặc muốn giữ identity qua thay đổi hạ tầng |

Tạo managed identity **chưa đủ để đọc/ghi Blob**: vẫn phải gán vai trò **data-plane** phù hợp trên storage account hoặc container. Ngược lại, gán role cho một identity **không làm ứng dụng tự sử dụng identity đó** nếu cấu hình chọn credential sai.

### 3.2. Luồng cấp access token

~~~mermaid
sequenceDiagram
    participant APP as Spring Boot
    participant SDK as Azure Identity SDK
    participant MI as Managed identity endpoint
    participant ST as Azure Blob Storage
    APP->>SDK: Yêu cầu token cho Azure Storage
    SDK->>MI: Lấy token của managed identity đã gán
    MI-->>SDK: Access token có hạn dùng
    SDK-->>APP: Credential quản lý token/refresh
    APP->>ST: Gọi API với Bearer token
    ST->>ST: Kiểm tra token và quyền data-plane
    ST-->>APP: Dữ liệu hoặc lỗi 401/403
~~~

Token có hạn sử dụng; Azure Identity SDK có cơ chế quản lý việc lấy/làm mới token. Không tự lưu access token lâu dài vào database, không ghi token vào log, không cố định token thành biến cấu hình application.

### 3.3. Local, CI/CD và production

- **Local:** developer có thể đăng nhập bằng `az login` hoặc IDE tương thích để SDK lấy token; phải gán quyền vào **danh tính developer** hoặc dùng tài nguyên test.
- **Azure production:** ưu tiên managed identity; cấp RBAC cho **principal của identity đang chạy**. Đối với user-assigned identity, cần đảm bảo ứng dụng chọn đúng client ID.
- **CI/CD:** nếu cần làm việc với Azure, ưu tiên workload identity federation/OIDC hoặc danh tính không có secret lâu dài; tách quyền deploy resource khỏi quyền truy cập dữ liệu ứng dụng.

`DefaultAzureCredential` thuận tiện vì thử các nguồn danh tính được hỗ trợ, nhưng chính tính linh hoạt này đòi hỏi kiểm soát: một ứng dụng chạy local có thể dùng danh tính developer, còn Azure production dùng managed identity với quyền hoàn toàn khác. Khi chẩn đoán, xác định **principal thực tế**, thay vì chỉ nói “đã bật managed identity”.

## 4. Azure RBAC cho Blob, Queue và Azure Files

### 4.1. Phân biệt scope và operation

Một role assignment thường gồm **principal + role + scope**:

~~~text
Principal: Managed identity của document-api
Role:      Storage Blob Data Contributor
Scope:     Storage account / container documents

Principal: Managed identity của document-worker
Role:      Storage Queue Data Message Processor
Scope:     Queue document-jobs (nếu phạm vi được hỗ trợ)
~~~

Chọn scope nhỏ nhất đáp ứng yêu cầu. Không mở quyền ở subscription chỉ vì dễ cấu hình; một app đọc một container thì nên được cấp quyền ở container nếu mô hình RBAC/operation cho phép.

| Bài toán | Role hoặc lớp quyền nên xem xét | Lưu ý |
|---|---|---|
| Đọc/blob list/download | **Storage Blob Data Reader** | Có quyền đọc dữ liệu tại scope được gán; app vẫn cần kiểm tra quyền người dùng cuối |
| Upload, sửa, xóa blob | **Storage Blob Data Contributor** | Rộng hơn Reader; chỉ cấp cho service thực sự cần ghi |
| Gửi Queue message | **Storage Queue Data Message Sender** | Phù hợp producer chỉ enqueue |
| Nhận/xử lý/xóa Queue message | **Storage Queue Data Message Processor** | Phù hợp worker xử lý job |
| Quản lý nhiều thao tác Queue data | **Storage Queue Data Contributor** | Xem xét thay vì gom producer và worker chung một principal |
| Tạo user delegation key cho Blob | **Storage Blob Delegator** hoặc role có action tương ứng | Quyền xin key có scope riêng, xem mục 6 |
| Azure Files qua SMB | Vai trò **Storage File Data SMB Share ...** cùng quyền filesystem/ACL khi áp dụng | Cần xác định phương thức xác thực SMB và mức quyền share/file |
| Azure Files qua REST | Credential và vai trò REST/OAuth được hỗ trợ theo API/tính năng đang dùng | Không suy ra quyền REST từ role SMB |
| Azure Files qua NFS | Xem mô hình bảo mật, network và quyền POSIX của NFS | Không đánh đồng với Entra OAuth của Blob |

Tên role có thể thay đổi theo tính năng và môi trường; trước khi triển khai, kiểm tra danh sách built-in role hiện hành của Azure Storage và quyền hành động thực tế. Role assignment có thể cần thời gian lan truyền: sau khi gán quyền, một lỗi 403 tức thời chưa chứng minh code sai.

### 4.2. Ví dụ gán role bằng Azure CLI

Giả sử đã có **principal object ID** của managed identity (khác **client ID**) và resource ID của container. Người thực hiện lệnh cần quyền tạo role assignment, ví dụ Role Based Access Control Administrator hoặc User Access Administrator ở scope phù hợp:

~~~bash
STORAGE_ACCOUNT_ID="/subscriptions/<sub-id>/resourceGroups/<rg>/providers/Microsoft.Storage/storageAccounts/<account>"
CONTAINER_SCOPE="$STORAGE_ACCOUNT_ID/blobServices/default/containers/documents"
MI_PRINCIPAL_ID="<managed-identity-principal-object-id>"

az role assignment create \
  --assignee-object-id "$MI_PRINCIPAL_ID" \
  --assignee-principal-type ServicePrincipal \
  --role "Storage Blob Data Contributor" \
  --scope "$CONTAINER_SCOPE"
~~~

Ví dụ thể hiện **cú pháp và ý tưởng scope**, không phải lệnh đã áp dụng lên tài khoản nào. Shell ví dụ dùng Bash; khi chạy PowerShell trên Windows, đổi cú pháp biến và xuống dòng cho phù hợp. Trong môi trường thực tế, cấp quyền bằng IaC/terraform/Bicep để có thể review và audit.

Đối với service sinh **user delegation key**, action `Microsoft.Storage/storageAccounts/blobServices/generateUserDelegationKey/action` phải được cho phép ở scope có thể chứa action này, thường ở storage account, resource group hoặc subscription. Gán role chỉ trong một container chưa chắc đủ để xin user delegation key, dù principal có quyền đọc blob ở container đó.

### 4.3. Lưu ý riêng của Azure Files

Azure Files cung cấp nhiều cách truy cập không hoàn toàn tương đương:

- **SMB:** identity-based authentication cần cấu hình giải pháp directory phù hợp; authorization thường kết hợp **share-level permission** và ACL trên directory/file. Không chỉ gán `Storage Blob Data Contributor` rồi mong mount SMB sẽ được.
- **NFS:** cần xét các cơ chế bảo mật của NFS, quyền UNIX/POSIX, network isolation và điều kiện của loại file share; không được giả định NFS dùng cơ chế RBAC OAuth tương tự Blob.
- **REST/SDK:** có cơ chế cấp quyền và khả năng dùng OAuth tùy phiên bản API, loại thao tác, điều kiện hỗ trợ; kiểm tra tài liệu Azure Files riêng.

Nếu bài toán chỉ lưu/đọc object qua API, Blob thường là lựa chọn đơn giản hơn. Chỉ chọn File Share khi cần filesystem và các hành vi đặc trưng của SMB/NFS.

## 5. Cấu hình danh tính trong Spring Cloud Azure

### 5.1. Dependency và cấu hình cơ bản

Spring Cloud Azure có starter tích hợp Azure Storage; ví dụ ứng dụng sử dụng Blob và Queue:

~~~xml
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
    <dependency>
        <groupId>com.azure.spring</groupId>
        <artifactId>spring-cloud-azure-starter-storage-queue</artifactId>
    </dependency>
</dependencies>
~~~

Chọn property `spring-cloud-azure.version` theo **bảng tương thích với Spring Boot** của bản Spring Cloud Azure dự án sử dụng. Các tên class, starter và thuộc tính tự cấu hình có thể được mở rộng giữa các bản phát hành; đối chiếu hướng dẫn của phiên bản đã chọn trước khi vận hành.

Trong `application.yml`:

~~~yaml
spring:
  cloud:
    azure:
      storage:
        blob:
          account-name: ${AZURE_STORAGE_ACCOUNT_NAME}
        queue:
          account-name: ${AZURE_STORAGE_ACCOUNT_NAME}

app:
  storage:
    documents-container: ${DOCUMENTS_CONTAINER:documents}
    jobs-queue: ${JOBS_QUEUE:document-jobs}
~~~

Ví dụ này **không khai báo account key, connection string hay client secret**. Credential được lấy qua cấu hình Azure Identity/Spring Cloud Azure và môi trường thực thi. Trường hợp production sử dụng managed identity, cấu hình để chọn đúng identity đã được gán cho ứng dụng.

### 5.2. Chọn identity khi có nhiều môi trường

Một số phiên bản Spring Cloud Azure hỗ trợ cấu hình managed identity bằng các thuộc tính dạng sau:

~~~yaml
# Chỉ áp dụng cho profile triển khai trên Azure; xác minh với version đang dùng.
spring:
  cloud:
    azure:
      credential:
        managed-identity-enabled: true
        client-id: ${AZURE_CLIENT_ID}
~~~

- Với **user-assigned managed identity**, `AZURE_CLIENT_ID` là **client ID** của identity được gắn vào tài nguyên chạy ứng dụng, không phải principal object ID.
- Với **system-assigned identity**, không khai báo `client-id` nếu framework/SDK mặc định sử dụng system-assigned identity.
- Đừng ép local profile dùng managed identity endpoint khi chạy ngoài Azure. Local nên có profile hoặc chuỗi credential dành cho developer.
- Nếu dự án bật auto-configuration, tránh tự tạo thêm bean client trùng kiểu mà không có chủ đích.

Trong một kiến trúc cần **chọn identity tường minh**, Azure SDK có builder riêng:

~~~java
import com.azure.core.credential.TokenCredential;
import com.azure.identity.ManagedIdentityCredentialBuilder;
import com.azure.storage.blob.BlobServiceClient;
import com.azure.storage.blob.BlobServiceClientBuilder;

String account = System.getenv("AZURE_STORAGE_ACCOUNT_NAME");
String userAssignedClientId = System.getenv("AZURE_CLIENT_ID");
if (account == null || account.isBlank()) {
    throw new IllegalStateException("Thiếu AZURE_STORAGE_ACCOUNT_NAME");
}

ManagedIdentityCredentialBuilder credentialBuilder =
        new ManagedIdentityCredentialBuilder();
if (userAssignedClientId != null && !userAssignedClientId.isBlank()) {
    credentialBuilder.clientId(userAssignedClientId);
}
TokenCredential credential = credentialBuilder.build();

BlobServiceClient blobService = new BlobServiceClientBuilder()
        .endpoint("https://" + account + ".blob.core.windows.net")
        .credential(credential)
        .buildClient();
~~~

Đây là đoạn Java dùng **khi ứng dụng chạy trên nền tảng hỗ trợ managed identity** và cần cấu hình Azure SDK trực tiếp. Nó không thể tự xác thực bằng managed identity trên mọi máy local. Với local development hoặc khi muốn hỗ trợ nhiều nguồn đăng nhập có kiểm soát, dùng `DefaultAzureCredentialBuilder` phù hợp hơn; với production muốn đảm bảo **chỉ managed identity** được chọn, builder tường minh giúp loại bỏ khả năng SDK âm thầm dùng một nguồn credential khác.

Nếu áp dụng SDK trực tiếp, cần các thư viện `azure-identity` và `azure-storage-blob` tương thích; không tạo hai bộ cấu hình client cạnh tranh với Spring Cloud Azure starter. Trong Azure sovereign cloud hoặc môi trường endpoint tùy chỉnh, URL và cấu hình authority phải tương thích cloud đích.

### 5.3. Kết nối SDK từ Spring Boot

Khi starter auto-configure `BlobServiceClient` và `QueueServiceClient`, code nghiệp vụ chỉ cần inject client:

~~~java
import com.azure.storage.blob.BlobServiceClient;
import com.azure.storage.queue.QueueServiceClient;
import org.springframework.stereotype.Service;

@Service
public class StorageGateway {
    private final BlobServiceClient blobService;
    private final QueueServiceClient queueService;

    public StorageGateway(BlobServiceClient blobService,
                          QueueServiceClient queueService) {
        this.blobService = blobService;
        this.queueService = queueService;
    }

    public void putDocument(String blobName, byte[] smallPdf) {
        // Minh họa dữ liệu nhỏ; file lớn nên dùng stream.
        var container = blobService.getBlobContainerClient("documents");
        var blob = container.getBlobClient(blobName);
        blob.upload(
                new java.io.ByteArrayInputStream(smallPdf),
                smallPdf.length,
                false);
    }

    public void enqueue(String blobName) {
        queueService.getQueueClient("document-jobs")
                .sendMessage(blobName);
    }
}
~~~

Đoạn code minh họa cách client dùng credential chung để gọi Storage. Ứng dụng thật phải xác thực người dùng, kiểm soát định dạng/dung lượng, dùng stream cho file lớn, xử lý blob đã tồn tại, bảo đảm queue đã provision và có cơ chế khôi phục nếu ghi Blob thành công nhưng enqueue thất bại.

## 6. Shared Access Signature (SAS) là gì?

**SAS** là token truy cập có chữ ký, mô tả **resource, quyền, hạn dùng** và các điều kiện tùy chọn như thời gian bắt đầu, giao thức, dải IP. Trình duyệt hoặc đối tác có thể gửi request trực tiếp tới Azure Storage bằng URL chứa SAS mà không cần cầm account key hoặc token Entra của backend.

### 6.1. Ba loại SAS cần phân biệt

| Loại | Ai ký? | Phạm vi/phương thức | Điểm quan trọng |
|---|---|---|---|
| **User delegation SAS** | User delegation key được cấp dựa trên Microsoft Entra ID | **Blob Storage** (và trường hợp ADLS Gen2 phù hợp) | Ưu tiên cho Blob khi có thể; không cần dùng account key để ký |
| **Service SAS** | Storage account key; có thể liên kết stored access policy khi dịch vụ/resource hỗ trợ | Resource của một storage service (Blob, Queue, Files, Table...) | Cần bảo vệ account key và hiểu cơ chế thu hồi |
| **Account SAS** | Storage account key | Có thể cấp phạm vi service/resource type/operation rộng hơn | Không hỗ trợ stored access policy; phạm vi rộng làm tăng tác động khi token lộ |

**User delegation SAS không phải SAS phổ quát cho Azure Queue hay Azure Files.** Nếu cần truy cập Queue bằng ứng dụng backend, ưu tiên Entra token/RBAC thông qua SDK thay vì phát account-key SAS. Với Azure Files, chọn cơ chế truy cập phù hợp SMB/REST và kiểm tra khả năng cấp quyền thực tế.

### 6.2. SAS và role RBAC có quan hệ gì?

Đối với user delegation SAS, principal cấp key phải được Azure cho phép xin **user delegation key**. Quyền truy cập qua SAS còn phụ thuộc các điều kiện của user delegation SAS và quyền được ủy quyền theo mô hình dịch vụ. Với **service/account SAS ký bởi account key**, người nhận token sử dụng quyền trong token hợp lệ; không cần được gán role RBAC trên chính tài khoản Entra của người nhận.

Đừng nghĩ “SAS ký bằng account key cũng được RBAC của backend tự giới hạn như user delegation SAS”. Một account key có đặc quyền cao; nếu lộ, kẻ tấn công có thể ký SAS với quyền khác hoặc truy cập trực tiếp theo Shared Key trong phạm vi tài khoản cho phép.

### 6.3. Ví dụ SAS và cách đọc phạm vi

Một URL minh họa (chữ ký giả, **không có hiệu lực**):

~~~text
https://storage-example.blob.core.windows.net/documents/contracts/a123.pdf
  ?sv=<api-version>
  &sr=b
  &sp=r
  &st=<start-time>
  &se=<expiry-time>
  &spr=https
  &sig=<signature>
~~~

- `sr=b`: SAS đang tham chiếu một **blob**.
- `sp=r`: quyền **read**, không chứa write/delete.
- `st` và `se`: khoảng thời gian SAS hợp lệ, phụ thuộc đồng hồ và quy tắc xác thực của Azure.
- `spr=https`: chỉ cho phép HTTPS khi được dùng.
- `sig`: chữ ký xác thực; không sao chép lên log, ticket công khai hoặc ảnh chụp màn hình.

Ví dụ chỉ nhằm giải thích **cấu trúc chung** của SAS; tham số cụ thể thay đổi theo loại SAS, API version và resource. SAS thực do Azure SDK sinh, không tự nối query string để ký thủ công.

## 7. Tạo user delegation SAS đọc một blob bằng Java

Trường hợp: backend đã kiểm tra `userId` có quyền đọc hồ sơ, rồi tạo URL chỉ đọc có hạn dùng ngắn cho đúng blob đó. Backend có `BlobServiceClient` xác thực bằng **Microsoft Entra token**, không phải account key.

### 7.1. Điều kiện quyền cần có

Danh tính backend cần:

1. Quyền **đọc blob cần chia sẻ** theo data-plane RBAC, ví dụ `Storage Blob Data Reader` ở container phù hợp.
2. Quyền gọi action `Microsoft.Storage/storageAccounts/blobServices/generateUserDelegationKey/action`, thường thông qua **Storage Blob Delegator** tại scope storage account hoặc scope cha phù hợp.
3. Kết nối network được phép tới Blob endpoint và thời gian hệ thống đủ chính xác.

Tình huống phổ biến: một identity chỉ có quyền Reader tại **container** vẫn có thể thất bại khi gọi `getUserDelegationKey` vì action xin key có scope ở cấp khác. Không khắc phục bằng cách cấp `Owner` ở subscription; gán đúng action/scope cần thiết.

### 7.2. Ví dụ service

~~~java
import com.azure.storage.blob.BlobClient;
import com.azure.storage.blob.BlobServiceClient;
import com.azure.storage.blob.models.UserDelegationKey;
import com.azure.storage.blob.sas.BlobSasPermission;
import com.azure.storage.blob.sas.BlobServiceSasSignatureValues;
import com.azure.storage.common.sas.SasProtocol;
import java.net.URI;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import org.springframework.stereotype.Service;

@Service
public class PrivateDocumentLinkService {
    private final BlobServiceClient blobService;

    public PrivateDocumentLinkService(BlobServiceClient blobService) {
        this.blobService = blobService;
    }

    public URI createReadLink(String authorizedBlobName) {
        // Caller đã kiểm tra người dùng hiện tại được phép đọc tài liệu.
        BlobClient blob = blobService
                .getBlobContainerClient("documents")
                .getBlobClient(authorizedBlobName);

        OffsetDateTime now = OffsetDateTime.now(ZoneOffset.UTC);
        OffsetDateTime starts = now.minusMinutes(5);
        OffsetDateTime expires = now.plusMinutes(10);

        // Principal phải được quyền generateUserDelegationKey.
        UserDelegationKey key =
                blobService.getUserDelegationKey(starts, expires);

        BlobSasPermission permission = new BlobSasPermission()
                .setReadPermission(true);
        BlobServiceSasSignatureValues values =
                new BlobServiceSasSignatureValues(expires, permission)
                        .setStartTime(starts)
                        .setProtocol(SasProtocol.HTTPS_ONLY);

        String sas = blob.generateUserDelegationSas(values, key);
        return URI.create(blob.getBlobUrl() + "?" + sas);
    }
}
~~~

Đoạn này là **service tạo URL**, không phải controller công khai. Trước khi gọi `createReadLink`, tầng nghiệp vụ phải đọc record theo ID, kiểm tra chủ sở hữu/tenant, chính sách download và đảm bảo blob nằm trong container được phép. Không nhận blob name tùy ý từ client rồi ký URL cho tất cả những blob mà identity backend đọc được.

Các mốc thời gian chỉ là ví dụ. `starts = now − 5 phút` giúp giảm lỗi lệch đồng hồ, `expires = now + 10 phút` giới hạn khả năng lạm dụng. User delegation key không được cấp vượt giới hạn tối đa do Azure quy định (thông thường tối đa **7 ngày**); SAS có thể dùng hạn ngắn hơn. Với lưu lượng request lớn, cân nhắc **cache user delegation key an toàn** trong khoảng hợp lệ rồi dùng lại để ký URL, thay vì xin key mới cho mọi download; vẫn phải duy trì hạn SAS ngắn và cơ chế xoay vòng.

**Lưu ý bảo mật:** kết quả là **URL chứa bearer credential**. Bảo vệ URL khỏi lịch sử chia sẻ, log query string, hệ thống analytics, Referer và clipboard không cần thiết; sử dụng HTTPS và header `Cache-Control` phù hợp ở backend. Khi SAS hết hạn, trình duyệt cần xin link mới sau khi backend kiểm tra quyền một lần nữa.

### 7.3. SAS cho upload trực tiếp

Với tệp lớn, backend có thể tạo **blob name ngẫu nhiên** và phát SAS chỉ cho phép **create/write** lên đúng blob:

~~~java
BlobSasPermission uploadPermission = new BlobSasPermission()
        .setCreatePermission(true)
        .setWritePermission(true);
// Dùng permission này để tạo BlobServiceSasSignatureValues
// rồi generateUserDelegationSas giống mẫu chỉ đọc ở trên.
~~~

Quyền `write` có thể cho phép sửa/ghi đè trong phạm vi resource, nên cần kiểm tra chính xác quyền được cấp, tránh dùng lại blob name có dữ liệu quan trọng, và áp dụng điều kiện ghi phù hợp ở client. SAS **không tự áp đặt giới hạn kích thước tệp** cho nghiệp vụ; backend phải xác minh kích thước, loại nội dung và quét file sau upload trước khi đánh dấu `READY`.

Một luồng an toàn:

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant A as Spring Boot API
    participant B as Azure Blob
    participant DB as Database
    U->>A: Xin upload (đã đăng nhập, size dự kiến)
    A->>DB: Tạo document PENDING + blobName riêng
    A-->>U: SAS create/write đúng blob, hạn ngắn
    U->>B: Upload trực tiếp qua HTTPS
    B-->>U: Kết quả ghi blob
    U->>A: Báo hoàn tất
    A->>B: Kiểm tra blob size, metadata, trạng thái
    A->>DB: Đổi sang READY sau khi kiểm tra
    A-->>U: Hoàn tất
~~~

## 8. Thu hồi, xoay vòng và quản trị SAS

### 8.1. Không phải SAS nào cũng thu hồi riêng được ngay

| Cơ chế | Cách hết quyền thường gặp | Điều cần nhớ |
|---|---|---|
| SAS ngắn hạn | Đến `expiry time` | Cách đơn giản nhất để giới hạn rủi ro |
| Service SAS gắn stored access policy (nơi hỗ trợ) | Sửa hoặc xóa policy tương ứng | Chỉ áp dụng khi service/resource hỗ trợ cơ chế này |
| Service/account SAS ký trực tiếp bằng key | Xoay storage account key dùng để ký | Có thể ảnh hưởng nhiều ứng dụng/SAS cùng dùng key; phải có kế hoạch |
| User delegation SAS | Hết hạn SAS hoặc delegation key; có thể thu hồi delegation key theo cơ chế Blob service | Thu hồi key ảnh hưởng mọi SAS ký bởi các key bị thu hồi, không phải xóa một URL độc lập |

**Account SAS không hỗ trợ stored access policy.** **User delegation SAS cũng không gắn stored access policy** như service SAS. Nếu nghiệp vụ yêu cầu “thu hồi ngay quyền tải chỉ của một người”, cần cân nhắc API proxy qua backend, lưu trạng thái authorization tại ứng dụng, hoặc các chiến lược cấp link ngắn hạn; SAS còn hiệu lực đã phát hành không tự kiểm tra lại database quyền người dùng sau mỗi request.

### 8.2. Quản lý account key

Account key có phạm vi quyền rất rộng và có thể ký nhiều dạng SAS. Không đưa key vào source code, biến frontend, file log hoặc hệ thống CI/CD không cần thiết. Restrict quyền management-plane `listKeys`, audit việc truy cập key, xoay vòng có kế hoạch và tách môi trường test/prod.

Khi workload hỗ trợ, xem xét **vô hiệu hóa Shared Key authorization** để buộc truy cập dữ liệu qua Microsoft Entra ID. **Đánh giá tương thích trước khi bật**: Azure Files, một số API hoặc ứng dụng cũ có nhu cầu dùng account key/SAS khác nhau, và thay đổi cấu hình có thể làm mất khả năng truy cập của các client hiện tại.

### 8.3. Điều kiện bảo vệ SAS

- Quyền tối thiểu: `r` cho download, các quyền create/write tối thiểu cho upload; không cấp list/delete nếu không cần.
- Resource tối thiểu: một blob cụ thể tốt hơn SAS cho cả container nếu yêu cầu chỉ là một file.
- Thời hạn: vừa đủ cho tác vụ, có dự phòng độ lệch đồng hồ hợp lý; người dùng cần xin lại sau khi hết hạn.
- Giao thức: HTTPS-only. Có thể giới hạn IP khi topology/địa chỉ client ổn định; tránh làm hỏng trải nghiệm người dùng di động thay đổi IP.
- Đăng ký audit ở **thời điểm cấp SAS** với userId/documentId/expiry và correlation ID, **không log giá trị SAS**; kết hợp Storage logging khi cần điều tra truy cập.

## 9. Kiến trúc an toàn cho Blob + Queue

Giả sử API cần lưu PDF và phát sinh công việc OCR:

~~~mermaid
flowchart TB
    U[Client đã xác thực] --> A[Spring Boot API]
    A -->|Managed identity + Blob Data Contributor| B[(Private Blob container)]
    A -->|Managed identity + Queue Message Sender| Q[(Storage Queue)]
    Q -->|Receive| W[OCR Worker]
    W -->|Queue Message Processor| Q
    W -->|Blob Data Reader| B
    U -->|Xin link tài liệu| A
    A -->|Kiểm tra quyền trên DB| D[(Database)]
    A -->|User delegation SAS chỉ đọc| U
    U -->|GET đúng blob qua HTTPS + SAS| B
~~~

Một số quyết định:

1. **Tách identity theo dịch vụ.** API ghi Blob và gửi Queue; OCR worker đọc Blob và nhận/xóa Queue. Mỗi identity chỉ cần quyền cho phần việc của mình, không nhất thiết dùng chung `Storage Blob Data Contributor` và `Storage Queue Data Contributor`.
2. **Container private.** User không có quyền data-plane mặc định; backend kiểm tra quyền nghiệp vụ rồi cấp SAS hoặc proxy file.
3. **Dữ liệu lớn đặt ở Blob; Queue chỉ chứa tham chiếu.** Message chứa `documentId`/`blobName` và job ID, không chứa PDF; worker xử lý idempotent vì Queue có thể giao lại message.
4. **Theo dõi trạng thái.** Blob upload và Queue enqueue không có transaction xuyên dịch vụ; nếu ghi Blob thành công nhưng gửi message thất bại, cần retry/đối soát/outbox.
5. **Không dùng một storage account key chung** để né RBAC hoặc chia sẻ key cho tất cả microservice.

Khi dùng Azure Files, kiến trúc quyền thay đổi theo giao thức SMB/NFS/REST. Không tái sử dụng nguyên mẫu gán Blob role cho dịch vụ mount share.

## 10. Chẩn đoán lỗi xác thực và phân quyền

| Hiện tượng | Khả năng cao | Cách kiểm tra |
|---|---|---|
| 401 Unauthorized | Thiếu/hỏng token hoặc credential không hợp lệ | Xác nhận phương thức auth, audience token, cấu hình Azure Identity |
| 403 AuthorizationPermissionMismatch | Token/SAS hợp lệ nhưng thiếu quyền hành động | Kiểm tra RBAC data-plane, SAS `sp`, resource/scope |
| 403 khi gọi `getUserDelegationKey` | Principal không có `generateUserDelegationKey/action` ở scope phù hợp | Kiểm tra role Delegator và scope ở cấp storage account/cha |
| 403 vì Shared Key bị tắt | Ứng dụng vẫn đang dùng key hoặc SAS dựa trên key không được chấp nhận | Chuyển sang Entra token/user delegation SAS khi service hỗ trợ |
| 403 / kết nối thất bại với storage firewall | Endpoint bị giới hạn network hoặc private endpoint/DNS sai | Kiểm tra public network setting, private endpoint, DNS, firewall |
| Local chạy, production lỗi | Local dùng developer identity; production dùng principal khác | Xác nhận principal ID, role assignment và thời gian propagation |
| User-assigned identity không được chọn | Nhầm **client ID** với **principal object ID** hoặc chưa attach identity vào host | Kiểm tra cấu hình identity của resource và SDK |
| SAS hoạt động trên máy này nhưng thất bại trên máy khác | SAS có IP restriction, thời gian lệch, mạng khác hoặc URL bị biến đổi | Kiểm tra `st`/`se`/`spr`/`sip` và URL encoding |
| SAS đọc được nhưng không upload/xóa | SAS chỉ có `read`, thiếu quyền và loại resource phù hợp | Cấp đúng permission ở đúng scope |
| Azure Files SMB báo Access denied | Chưa thiết lập share-level permission/ACL hoặc xác thực SMB | Kiểm tra identity provider, share role, NTFS ACL và môi trường mount |

Không in token/SAS để debug. Log request ID, operation, tên tài nguyên đã được rút gọn, thông tin principal an toàn và error code. Chú ý: 403 có thể do **data-plane RBAC**, **SAS**, **chính sách Shared Key** hoặc **network**; nên kiểm tra theo từng lớp thay vì cấp role cao hơn một cách mù quáng.

### 10.1. Bài kiểm tra thiết yếu khi deploy

~~~text
1. Azure resource có managed identity đang bật và được attach đúng?
2. Ứng dụng chọn system-assigned hay user-assigned identity đúng ý định?
3. Principal object ID nào được Azure thấy khi cấp role?
4. Role data-plane nào, gán ở scope nào, đã có thời gian lan truyền?
5. Endpoint Blob/Queue/Files có đúng cloud/account và DNS không?
6. Storage firewall/private endpoint cho phép workload này không?
7. SAS (nếu có) được ký bằng phương thức phù hợp và hạn/ngữ cảnh đúng?
8. Backend đã kiểm tra quyền của người dùng trước khi truy cập hoặc cấp link?
~~~

## 11. Kiểm thử tích hợp và các tình huống bảo mật

### 11.1. Test local với Azurite có giới hạn gì?

**Azurite** hữu ích để kiểm thử API Blob/Queue và logic upload/download/enqueue trên máy local. Tuy nhiên, một test dùng connection string emulator **không xác minh được cấu hình Microsoft Entra RBAC, managed identity hoặc private endpoint của Azure production**. Để kiểm tra quyền thực, phải chạy trên storage account Azure dành riêng cho integration tests, với principal/identity có role tối thiểu.

Không copy account key production vào emulator/test fixture. Tách account và dữ liệu test khỏi production, cleanup tài nguyên và tránh test hủy container thật.

### 11.2. Ma trận kiểm thử

| Kiểm thử | Kết quả mong đợi |
|---|---|
| Managed identity có Blob Data Reader | Đọc được blob ở scope cho phép, không ghi/xóa được |
| Managed identity có Blob Data Contributor | Upload được blob trong container được gán, không tự có quyền ở container khác |
| Queue producer chỉ có Message Sender | Gửi message được; không nhận/xóa như worker |
| Queue worker chỉ có Message Processor | Nhận/xử lý message trong scope được cấp; không giả định có quyền quản trị storage account |
| Principal không có Blob Delegator | Tạo user delegation key bị từ chối dù có thể đọc blob |
| SAS đọc một blob, hạn ngắn | GET được blob đúng; không ghi/xóa hoặc list ngoài phạm vi |
| SAS hết hạn hoặc bị sửa chữ ký | Request bị từ chối |
| SAS lộ sau khi app thu hồi quyền người dùng | Hiểu rằng SAS còn hiệu lực có thể vẫn hoạt động; áp dụng hạn ngắn/biện pháp thu hồi |
| Storage firewall chặn workload | Không thể truy cập dù RBAC đã đúng |
| Azure Files SMB thiếu ACL | Không thể mở file dù quyền share có vẻ đúng |
| API người dùng truy cập tài liệu tenant khác | Backend từ chối **trước khi** cấp SAS |

Với kiểm thử âm tính, dùng danh tính thực sự ít quyền thay vì giả lập `if (hasPermission)` trong code; mục tiêu là xác minh cấu hình IAM và hành vi dịch vụ. Xem lại log và Azure activity/diagnostic logs để xác nhận role/scope, nhưng loại bỏ SAS/token/secret khỏi telemetry.

### 11.3. Bài tập thực hành

**Tình huống A — API upload ảnh:** API chạy trên App Service và chỉ được ghi Blob ở container `avatars`. Hãy chọn loại managed identity, role, scope và cách xác thực client. Giải thích vì sao không cần cấp storage account key.

**Tình huống B — Worker OCR:** API gửi message vào queue, worker nhận và xóa message. Hãy tách hai identity, chọn hai role khác nhau để giảm phạm vi quyền, và giải thích tác động nếu worker bị xâm nhập.

**Tình huống C — Link PDF 10 phút:** Một người dùng được cấp quyền đọc hợp đồng. Hãy mô tả backend kiểm tra quyền, lấy user delegation key, tạo read-only SAS và tránh log URL. Người dùng bị thu hồi quyền giữa chừng: cơ chế nào khiến link cũ vẫn có thể dùng, và cách thiết kế để hạn chế?

**Tình huống D — File Share legacy:** Một ứng dụng Windows chạy trên VM mount Azure Files qua SMB. Một kỹ sư gán `Storage Blob Data Contributor` nhưng vẫn Access denied. Hãy giải thích tại sao role đó không giải quyết bài toán và nêu các lớp quyền cần kiểm tra trong Azure Files SMB.

**Tình huống E — Migration đa cloud:** AWS thường dùng IAM role cho workload truy cập S3, GCP dùng service account/workload identity truy cập Cloud Storage, Azure dùng managed identity/Entra RBAC cho Blob. So sánh theo cùng bốn trục: danh tính workload, role/permission, short-lived credential và cơ chế cấp URL truy cập tạm thời. Không giả định IAM action hoặc cách ký URL giống hệt giữa các provider.

## 12. Tổng kết

Kết nối Azure Storage an toàn cần xác định rõ **ai gọi**, **được làm gì** và **đi qua mạng nào**. Với Spring Boot trên Azure, hãy ưu tiên **managed identity + Microsoft Entra ID + data-plane RBAC** để SDK gọi Blob/Queue mà không chứa secret. Với client cần thao tác trực tiếp lên Blob, cấp **user delegation SAS ngắn hạn** cho đúng resource và permission sau khi backend đã kiểm tra quyền. Đối với **Azure Files**, phải xét riêng phương thức truy cập SMB/NFS/REST và các lớp quyền tương ứng.

Tư duy này cũng là nền tảng khi tích hợp storage của AWS và GCP: luôn tách **workload identity**, **policy authorization**, **network control**, **temporary delegation**, **audit** và **integration test thực tế**. Cú pháp thư viện và permission cụ thể thay đổi theo provider, nhưng nguyên tắc quyền tối thiểu và credential ngắn hạn vẫn có giá trị chung.

### Tài liệu tham khảo chính thức

- [Microsoft Learn — Managed identities for Azure resources](https://learn.microsoft.com/entra/identity/managed-identities-azure-resources/overview)
- [Microsoft Learn — Authorize access to Blob data with Microsoft Entra ID](https://learn.microsoft.com/azure/storage/blobs/authorize-access-azure-active-directory)
- [Microsoft Learn — Assign an Azure role for access to blob data](https://learn.microsoft.com/azure/storage/blobs/assign-azure-role-data-access)
- [Microsoft Learn — Grant limited access to Azure Storage resources using shared access signatures](https://learn.microsoft.com/azure/storage/common/storage-sas-overview)
- [Microsoft Learn — Create a user delegation SAS for a blob with Java](https://learn.microsoft.com/azure/storage/blobs/storage-blob-user-delegation-sas-create-java)
- [Microsoft Learn — Authorize access to Azure Queue Storage using Microsoft Entra ID](https://learn.microsoft.com/azure/storage/queues/authorize-access-azure-active-directory)
- [Microsoft Learn — Azure Files identity-based authentication](https://learn.microsoft.com/azure/storage/files/storage-files-identity-auth-smb)
- [Microsoft Learn — Spring Cloud Azure](https://learn.microsoft.com/azure/developer/java/spring-framework/)
- [Microsoft Learn — Use the Azurite emulator for local Azure Storage development](https://learn.microsoft.com/azure/storage/common/storage-use-azurite)
