# Tích hợp Azure Files File Share trong Spring Boot với Spring Cloud Azure

## 1. Mục tiêu và bối cảnh

Trong module **SPRING_CLOUD_PROVIDER_INTEGRATION**, chúng ta thực hành tích hợp Spring Boot với dịch vụ managed của AWS, Azure và Google Cloud qua các thư viện Spring Cloud tương ứng; đồng thời học cấu hình danh tính, quyền truy cập, storage, messaging, bảo vệ secret và kiểm thử. Bài này thuộc chương **Azure Storage**, tập trung vào **Azure Files (File Share)** và cách sử dụng dịch vụ từ Spring Boot theo khả năng mà Spring Cloud Azure cung cấp.

Giả sử một ứng dụng quản lý hồ sơ kế toán đang lưu báo cáo tại thư mục dùng chung. Nhiều máy chủ cần đọc và ghi cùng cấu trúc thư mục; một số module cũ đã dùng Java NIO, trong khi module mới muốn thao tác file qua HTTPS mà không phải mount ổ đĩa. Azure Files hỗ trợ cả hai hướng: **SMB/NFS với filesystem API của hệ điều hành** và **FileREST API với Azure Storage File Shares SDK**. Spring Cloud Azure bổ sung **Spring Resource abstraction** để ứng dụng dùng Resource, ResourceLoader và WritableResource.

Sau bài học, bạn có thể:

- Phân biệt Azure Files với Blob Storage và chọn đúng cách truy cập: mount SMB/NFS, Spring Resource abstraction hoặc FileREST SDK.
- Khai báo dependency spring-cloud-azure-starter-storage-file-share và cấu hình account/endpoint trong Spring Boot.
- Dùng URI azure-file:// để đọc, ghi và tìm file thông qua Spring Resource.
- Biết khi nào cần dùng trực tiếp ShareClient, ShareDirectoryClient, ShareFileClient.
- Phân biệt quyền FileREST OAuth với quyền share/ACL khi mount SMB và yêu cầu của NFS.
- Tổ chức provision, streaming, kiểm thử tích hợp, xử lý lỗi và vận hành File Share an toàn.

## 2. Azure Files là gì?

**Azure Files** là dịch vụ file share được quản lý trong Azure Storage. Một file share có cấu trúc thư mục và file tương tự một file server truyền thống:

~~~text
Storage account: accountingstore
└── File service
    ├── Share: reports
    │   ├── 2026/
    │   │   ├── january.csv
    │   │   └── february.csv
    │   └── templates/
    │       └── summary.xlsx
    └── Share: team-documents
        └── policies/
            └── retention.pdf
~~~

Azure Files hỗ trợ các phương thức truy cập chính:

- **SMB (Server Message Block):** mount file share thành đường dẫn filesystem trên Windows/Linux (tùy cấu hình và hệ điều hành). Ứng dụng dùng java.io, java.nio.file như thao tác với file thông thường.
- **NFS (Network File System):** mount share qua NFS trên các cấu hình/loại share được hỗ trợ; thường gắn với môi trường Linux và yêu cầu mạng, quyền filesystem tương ứng.
- **FileREST API:** gọi HTTPS để thao tác share, directory và file. Azure Storage File Shares SDK for Java cung cấp các client Java trên FileREST.

Azure Files phù hợp khi ứng dụng cần **thư mục chia sẻ, đường dẫn filesystem, khả năng tương thích file server hoặc thao tác file/directory**. Nếu chỉ cần lưu object như ảnh, video hoặc PDF theo key để tải qua HTTP, hãy đánh giá Blob Storage trước; Blob và File Share có ngữ nghĩa truy cập khác nhau.

## 3. Chọn cách tích hợp trong Spring Boot

Spring Cloud Azure cung cấp starter spring-cloud-azure-starter-storage-file-share. Starter tích hợp Azure Files với **Spring Resource abstraction**. Tùy yêu cầu, có ba hướng:

| Hướng | Cách ứng dụng truy cập | Khi nên dùng | Phần chịu trách nhiệm |
|---|---|---|---|
| **Spring Resource + File Share starter** | ResourceLoader, URI azure-file://, Resource/WritableResource | Đọc/ghi file cơ bản trong ứng dụng Spring, muốn dùng API thống nhất | Spring Cloud Azure cấu hình resolver và kết nối Storage |
| **Azure Storage File Shares SDK (FileREST)** | ShareClient, ShareDirectoryClient, ShareFileClient | Cần tạo directory/file rõ ràng, metadata, lease, copy, range, xử lý nâng cao | Ứng dụng gọi trực tiếp Azure SDK |
| **Mount SMB/NFS** | Path, Files, FileChannel trên mount point | Ứng dụng cũ đã dùng filesystem hoặc cần tương tác như ổ chia sẻ | Hạ tầng/hệ điều hành mount share; Java thao tác trên đường dẫn |

**Điểm cần hiểu đúng:** starter cung cấp một cách dùng Spring Resource cho Blob/File Share. Không nên mặc định mọi loại client hoặc thao tác quản trị của Azure Files đều xuất hiện thành bean Spring có thể inject. Khi cần API chuyên biệt, hãy dùng trực tiếp Azure Storage File Shares SDK.

~~~mermaid
flowchart TD
    A[Spring Boot application] --> B{Cách truy cập}
    B -->|Resource abstraction| C[File Share starter]
    B -->|FileREST nâng cao| D[Azure Storage File Shares SDK]
    B -->|Filesystem API| E[SMB/NFS mount]
    C --> F[(Azure Files)]
    D --> F
    E --> F
~~~

## 4. Khai báo Spring Cloud Azure File Share starter

### 4.1. Maven dependency

Khai báo BOM Spring Cloud Azure tương thích với phiên bản Spring Boot của dự án và starter File Share:

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
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter</artifactId>
    </dependency>
    <dependency>
        <groupId>com.azure.spring</groupId>
        <artifactId>spring-cloud-azure-starter-storage-file-share</artifactId>
    </dependency>
</dependencies>
~~~

spring-cloud-azure.version là property do dự án quản lý. Chọn BOM theo **bảng tương thích Spring Boot ↔ Spring Cloud Azure**, không tự lấy phiên bản bất kỳ. Nếu ứng dụng cũng dùng Blob/Queue, có thể thêm starter tương ứng hoặc cân nhắc starter tổng spring-cloud-azure-starter-storage theo nhu cầu.

### 4.2. Cấu hình application.yml

~~~yaml
spring:
  cloud:
    azure:
      storage:
        fileshare:
          enabled: true
          account-name: ${AZURE_STORAGE_ACCOUNT_NAME}
          endpoint: ${AZURE_STORAGE_FILESHARE_ENDPOINT}

app:
  files:
    share-name: ${AZURE_FILES_SHARE:reports}
~~~

Các thuộc tính File Share của Spring Cloud Azure có prefix spring.cloud.azure.storage.fileshare:

- enabled: bật/tắt dịch vụ File Share trong auto-configuration; mặc định thường là true khi starter được thêm.
- account-name: tên storage account.
- endpoint: endpoint File Share, thường có dạng https://<account>.file.core.windows.net đối với Azure public cloud.
- account-key: có thể cấu hình trong một số kịch bản dùng Shared Key, nhưng **không nên commit key vào file cấu hình**.

Nếu dùng Microsoft Entra ID/managed identity, không khai báo account key; cấu hình credential dùng chung của Spring Cloud Azure theo môi trường. Với **user-assigned managed identity**, có thể khai báo spring.cloud.azure.credential.client-id bằng client ID của identity được gắn vào workload. Với system-assigned identity, để SDK/runtime chọn identity gắn với resource.

Ví dụ chỉ định user-assigned identity (đưa vào profile Azure khi cần):

~~~yaml
spring:
  cloud:
    azure:
      credential:
        client-id: ${AZURE_CLIENT_ID}
~~~

Không dùng AZURE_CLIENT_ID thay cho **principal/object ID** khi cấp role. Client ID dùng để chọn identity trong cấu hình; role assignment được gán cho principal tương ứng.

### 4.3. Tài nguyên phải được provision trước

Starter giúp ứng dụng kết nối và thao tác với resource, nhưng không nên coi việc thêm dependency là đã tạo storage account hoặc file share. Hãy provision bằng **Bicep, Terraform, ARM template, Azure CLI hoặc quy trình hạ tầng**:

- Storage account và file share.
- Quota/dung lượng, redundancy và cấu hình network.
- Danh tính workload và role assignment.
- Directory cần có trước nếu luồng ghi phụ thuộc vào cấu trúc thư mục đã tồn tại.

Tách quyền provision resource khỏi quyền runtime. Một API chỉ đọc/ghi file trong share có sẵn không cần quyền tạo storage account hoặc thay đổi cấu hình subscription.

## 5. Dùng Spring Resource abstraction với azure-file://

### 5.1. Lấy Resource bằng @Value

Spring Cloud Azure đăng ký cơ chế phân giải URI azure-file://. Có thể inject trực tiếp một Resource:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.io.Resource;
import org.springframework.stereotype.Component;

@Component
public class ReportResource {
    @Value("azure-file://reports/2026/summary.csv")
    private Resource summaryFile;

    public Resource getSummaryFile() {
        return summaryFile;
    }
}
~~~

Trong URI:

- reports là **tên file share**.
- 2026/summary.csv là đường dẫn directory/file bên trong share.
- URI này được resolver của Spring Cloud Azure xử lý; không phải URL public để trình duyệt tải trực tiếp.

Không đưa đường dẫn do người dùng gửi trực tiếp vào annotation hoặc ghép chuỗi tùy tiện. Với đường dẫn động, phải kiểm tra document ID/quyền nghiệp vụ và chuẩn hóa path trước khi yêu cầu resolver.

### 5.2. Lấy Resource bằng ResourceLoader

Khi cần xác định resource ở runtime, inject ResourceLoader:

~~~java
import org.springframework.core.io.Resource;
import org.springframework.core.io.ResourceLoader;
import org.springframework.stereotype.Service;

@Service
public class FileShareResourceService {
    private final ResourceLoader resourceLoader;

    public FileShareResourceService(ResourceLoader resourceLoader) {
        this.resourceLoader = resourceLoader;
    }

    public Resource getFile(String shareName, String relativePath) {
        String location = "azure-file://" + shareName + "/" + relativePath;
        return resourceLoader.getResource(location);
    }
}
~~~

Đây là ví dụ minh họa cơ chế resolver. Trong ứng dụng thực, shareName và relativePath phải đến từ dữ liệu đã được kiểm tra quyền; tránh cho client truyền chuỗi path chứa ../, tên share khác tenant hoặc đường dẫn không nằm trong vùng được phép.

### 5.3. Đọc file bằng InputStream

Resource cung cấp getInputStream() để đọc nội dung theo luồng:

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import org.springframework.core.io.Resource;

public String readSmallText(Resource resource) throws IOException {
    try (InputStream input = resource.getInputStream()) {
        return new String(input.readAllBytes(), StandardCharsets.UTF_8);
    }
}
~~~

Ví dụ dùng readAllBytes() chỉ dành cho **file nhỏ đã giới hạn kích thước**. Với file lớn, copy theo stream sang output hoặc xử lý từng chunk để tránh giữ toàn bộ nội dung trong heap:

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import org.springframework.core.io.Resource;

public void downloadToLocalFile(Resource resource, Path target)
        throws IOException {
    try (InputStream input = resource.getInputStream();
         OutputStream output = Files.newOutputStream(target)) {
        input.transferTo(output);
    }
}
~~~

Đoạn code này dùng Java 9+ và giả định thư mục đích đã tồn tại. Khi truyền file cho HTTP response, cần kiểm tra quyền người dùng trước, đặt Content-Type/Content-Disposition phù hợp và xử lý trường hợp client ngắt kết nối.

### 5.4. Ghi file bằng WritableResource

Để ghi, cast resource sang WritableResource:

~~~java
import java.io.IOException;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import org.springframework.core.io.Resource;
import org.springframework.core.io.WritableResource;

public void writeText(Resource resource, String content)
        throws IOException {
    if (!(resource instanceof WritableResource writable)) {
        throw new IllegalArgumentException("Resource không hỗ trợ ghi");
    }

    try (OutputStream output = writable.getOutputStream()) {
        output.write(content.getBytes(StandardCharsets.UTF_8));
    }
}
~~~

getOutputStream() mở luồng ghi tới file resource. Hành vi khi file đã tồn tại phụ thuộc implementation và phiên bản resolver; không mặc định rằng thao tác luôn append. Hãy xác định rõ nghiệp vụ **tạo mới, ghi đè hay nối thêm**, kiểm tra file/directory tồn tại và kiểm thử hành vi đó với phiên bản starter đang dùng.

Tài liệu Spring Cloud Azure về resource handling ghi nhận **file lớn hơn 4 MiB được upload song song** trong luồng multipart upload của resolver. Đây là hành vi triển khai của starter, không phải cam kết rằng mọi cấu hình ứng dụng đều có cùng throughput; đo thực tế với kích thước file, concurrency, network và phiên bản SDK của hệ thống.

### 5.5. Tìm resource theo pattern

Spring Cloud Azure có protocol resolver cho Blob và File Share. Với File Share, AzureStorageFileProtocolResolver có thể tìm file theo pattern azure-file://:

~~~java
import org.springframework.core.io.Resource;
import com.azure.spring.cloud.core.resource.AzureStorageFileProtocolResolver;

public Resource[] findTextFiles(
        AzureStorageFileProtocolResolver resolver) {
    return resolver.getResources("azure-file://reports/**/*.txt");
}
~~~

Pattern search hữu ích cho tác vụ batch hoặc đọc một nhóm file. Không dùng để thay database query trên kho dữ liệu lớn; cần phân trang, giới hạn số kết quả, quyền truy cập và chi phí liệt kê. Ví dụ import ở trên dùng package của các bản Spring Cloud Azure hiện hành; xác minh package/class cụ thể với BOM của dự án khi nâng cấp major version.

## 6. Khi cần API chuyên biệt: Azure Storage File Shares SDK

Spring Resource phù hợp cho thao tác file cơ bản. Khi cần tạo directory/file tường minh, quản lý metadata/SMB properties, lease, copy, list chi tiết hoặc thao tác range, dùng **Azure Storage File Shares SDK for Java**.

### 6.1. Dependency SDK

Thêm artifact azure-storage-file-share và Azure Identity. Quản lý version bằng Azure SDK BOM hoặc dependency management tương thích với Spring Cloud Azure hiện có:

~~~xml
<dependency>
    <groupId>com.azure</groupId>
    <artifactId>azure-storage-file-share</artifactId>
</dependency>
<dependency>
    <groupId>com.azure</groupId>
    <artifactId>azure-identity</artifactId>
</dependency>
~~~

Nếu BOM Spring Cloud Azure của dự án đã quản lý version các Azure SDK tương ứng, không tự override một version khác. Nếu dùng SDK độc lập, có thể import azure-sdk-bom để giữ các Azure SDK cùng bộ version.

### 6.2. Tạo ShareClient với Microsoft Entra ID

ShareClient là điểm bắt đầu để truy cập một file share. Dùng DefaultAzureCredential cho local developer identity và workload identity/managed identity khi chạy trên Azure:

~~~java
import com.azure.core.credential.TokenCredential;
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.storage.file.share.ShareClient;
import com.azure.storage.file.share.ShareClientBuilder;

String accountName = System.getenv("AZURE_STORAGE_ACCOUNT_NAME");
String shareName = "reports";
String endpoint = "https://" + accountName + ".file.core.windows.net";

TokenCredential credential =
        new DefaultAzureCredentialBuilder().build();

ShareClient shareClient = new ShareClientBuilder()
        .endpoint(endpoint)
        .shareName(shareName)
        .credential(credential)
        .buildClient();
~~~

Đoạn code giả định endpoint Azure public cloud và share đã được tạo. Với sovereign cloud hoặc endpoint tùy chỉnh, dùng endpoint tương ứng. Không hardcode account key/connection string trong source; nếu môi trường buộc phải dùng Shared Key, đưa secret vào kho quản lý secret và giới hạn người được truy cập.

### 6.3. Tạo directory và file

Các client chính:

| Client | Phạm vi | Ví dụ thao tác |
|---|---|---|
| ShareClient | Một file share | Lấy root directory, tạo client directory, truy cập snapshot |
| ShareDirectoryClient | Một directory | Tạo/list directory, tạo file, xóa file hoặc directory rỗng |
| ShareFileClient | Một file | Upload/download, properties, metadata, lease, delete |

Ví dụ tạo directory và một file mới:

~~~java
import com.azure.storage.file.share.ShareDirectoryClient;
import com.azure.storage.file.share.ShareFileClient;

ShareDirectoryClient root = shareClient.getRootDirectoryClient();
ShareDirectoryClient yearDirectory =
        root.createSubdirectoryIfNotExists("2026");

long fileSize = 1024;
ShareFileClient file = yearDirectory.createFile("summary.csv", fileSize);
~~~

createFile(fileName, maxSize) tạo file với kích thước tối đa/được khai báo theo API. Khi file đã tồn tại, thao tác tạo có thể trả xung đột; hãy dùng tên mới hoặc một quy trình cập nhật file có kiểm soát. Không dùng getFileClient() rồi giả định file đã được tạo trên Azure.

### 6.4. Upload từ file local

~~~java
import com.azure.storage.file.share.ShareFileClient;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public void uploadNewFile(
        ShareDirectoryClient directory,
        Path source,
        String fileName) throws IOException {

    long size = Files.size(source);
    ShareFileClient target = directory.createFile(fileName, size);
    target.uploadFromFile(source.toString());
}
~~~

Đoạn code tạo file mới rồi upload nội dung từ file local. Với dữ liệu lớn, SDK có API upload hỗ trợ ParallelTransferOptions; cần cấu hình transfer theo RAM/băng thông và giới hạn của FileREST. Nếu ghi vào file đã có, cần đặt lại size/range hoặc sử dụng quy trình cập nhật tương ứng, không giả định uploadFromFile tự xử lý mọi trường hợp ghi đè an toàn.

### 6.5. Download ra OutputStream

~~~java
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;

public void downloadFile(
        ShareFileClient source,
        Path destination) throws IOException {
    try (OutputStream output = Files.newOutputStream(destination)) {
        source.download(output);
    }
}
~~~

ShareFileClient.download(OutputStream) ghi dữ liệu ra stream. Tránh dùng ByteArrayOutputStream cho file lớn vì nó giữ toàn bộ dữ liệu trong heap. Nếu muốn SDK ghi ra file local, downloadToFile(path) có sẵn; theo tài liệu SDK, file đích phải chưa tồn tại.

### 6.6. Liệt kê và xóa

~~~java
for (var item : yearDirectory.listFilesAndDirectories()) {
    System.out.println(
            (item.isDirectory() ? "[DIR] " : "[FILE] ") + item.getName());
}

boolean deleted = yearDirectory.deleteFileIfExists("summary.csv");
~~~

Directory chỉ có thể xóa khi rỗng; cần xử lý các file và subdirectory bên trong theo chính sách trước khi xóa. Không cho người dùng cuối truyền đường dẫn tùy ý để xóa file mà chưa kiểm tra quyền sở hữu, tenant và trạng thái nghiệp vụ.

## 7. Mount SMB/NFS và dùng Java NIO

Nếu ứng dụng đã được thiết kế quanh filesystem, có thể mount Azure File Share vào máy chủ/container rồi dùng Java I/O:

~~~java
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;

Path mountedShare = Path.of(System.getenv("AZURE_FILES_MOUNT"));
Path report = mountedShare.resolve("2026/summary.csv");

Files.createDirectories(report.getParent());
Files.copy(
        Path.of("local/summary.csv"),
        report,
        StandardCopyOption.REPLACE_EXISTING);
~~~

Đoạn code chỉ thao tác **đường dẫn đã mount**; Spring Boot không tự mount share. Hạ tầng triển khai phải:

- Cấu hình SMB hoặc NFS theo loại share và hệ điều hành được hỗ trợ.
- Thiết lập network, DNS, firewall và thông tin xác thực phù hợp.
- Gắn volume/mount point vào máy hoặc container.
- Cấp quyền filesystem/ACL cho tiến trình Java.
- Theo dõi kết nối, handle, lock và lỗi I/O khi share/network gián đoạn.

SMB có thể dùng identity-based authentication với share-level permission và ACL ở file/directory. NFS dùng mô hình quyền và điều kiện network riêng. Không giả định một cấu hình RBAC cho FileREST sẽ tự cấp quyền mount SMB/NFS.

## 8. Authentication và authorization cho Azure Files

### 8.1. Phân biệt FileREST với SMB/NFS

| Cách truy cập | Xác thực/ủy quyền | Điểm cần lưu ý |
|---|---|---|
| Spring Resource/FileREST | Microsoft Entra ID/OAuth hoặc cơ chế được SDK/resolver hỗ trợ | Role data-plane phải đủ cho operation FileREST |
| Azure Storage File Shares SDK/FileREST | TokenCredential, ví dụ DefaultAzureCredential | Một số thao tác ở cấp share không hỗ trợ OAuth như thao tác file/directory; kiểm tra API cụ thể |
| SMB mount | Identity-based authentication hoặc cơ chế xác thực SMB được cấu hình | Kết hợp share-level permission và ACL trên file/directory |
| NFS mount | Quyền POSIX/UID/GID và network theo cấu hình share | Không coi đây là cùng mô hình OAuth/RBAC với FileREST |

### 8.2. Role cho FileREST OAuth

Với các ví dụ FileREST sử dụng Microsoft Entra ID, tài liệu Azure Files hướng dẫn gán role **Storage File Data Privileged Contributor** cho security principal. Role này có quyền đọc, ghi, sửa ACL và xóa dữ liệu trên các share trong phạm vi cấu hình, kể cả khi ACL cấp file/directory hạn chế; đây là role **rất mạnh**, cần cân nhắc kỹ.

Chỉ cấp role rộng này cho workload thực sự cần các quyền privileged. Nếu workload chỉ đọc, kiểm tra role read-only phù hợp và operation được hỗ trợ; không tự động cấp Contributor cho mọi service.

Với SMB, có các role theo mô hình share-level như **Storage File Data SMB Share Reader**, **Storage File Data SMB Share Contributor** hoặc **Storage File Data SMB Share Elevated Contributor**, kết hợp ACL/NTFS permission theo cấu hình identity. Role SMB không phải một bản thay thế trực tiếp cho role FileREST OAuth.

### 8.3. Giới hạn ở cấp share

Không phải mọi thao tác Azure Files đều hỗ trợ Microsoft Entra OAuth như nhau. Tài liệu Azure Files lưu ý OAuth token không được chấp nhận cho một số thao tác **data plane ở cấp file share**, chẳng hạn các thao tác snapshot/share-level được mô tả trong SDK guide; những operation này có thể yêu cầu Shared Key hoặc cơ chế quản trị phù hợp. Vì vậy:

- Dùng Entra ID cho các thao tác FileREST file/directory mà dịch vụ hỗ trợ.
- Provision share và quản lý tài nguyên cấp account/share qua IaC hoặc Azure Resource Manager khi phù hợp.
- Kiểm tra yêu cầu authorization của từng API trước khi thiết kế một identity dùng cho tất cả thao tác.
- Không fallback âm thầm sang account key khi OAuth bị 403.

### 8.4. Bảo vệ secret và network

- Ưu tiên managed identity trong Azure; local dùng developer identity theo chính sách tổ chức.
- Không commit account key/connection string vào Git, không log token hoặc secret.
- Nếu buộc dùng Shared Key, lưu trong Azure Key Vault hoặc secret manager tương đương, giới hạn quyền đọc và có kế hoạch xoay vòng.
- Cấu hình HTTPS/TLS cho FileREST; kiểm tra storage firewall, private endpoint, DNS và network route.
- Với SMB/NFS, kiểm tra protocol/port, mount option và khả năng kết nối từ subnet/container.

## 9. Quản lý share và resource ở cấp hạ tầng

File Share starter tập trung vào **truy cập file theo Spring Resource**. Khi cần tạo/xóa storage account hoặc file share ở cấp resource, hãy dùng Azure Resource Manager/IaC hoặc Azure Storage management libraries. Đây là lớp quản lý hạ tầng, có quyền và vòng đời khác với thao tác file/directory.

| Nhiệm vụ | Công cụ nên cân nhắc |
|---|---|
| Tạo storage account, cấu hình network | Bicep/Terraform/ARM |
| Tạo file share, đặt quota | IaC hoặc Azure Storage management library |
| Đọc/ghi file bằng URI azure-file:// | Spring Cloud Azure File Share starter |
| Tạo directory/file, list, copy, lease qua FileREST | Azure Storage File Shares SDK |
| Dùng đường dẫn filesystem có sẵn | SMB/NFS mount + Java NIO |

Không gán quyền subscription Owner cho runtime chỉ để ứng dụng có thể tạo một file share. Nếu cần tự động provision share, dùng một quy trình quản trị riêng có quyền giới hạn và audit.

## 10. Lock, concurrency và khác biệt SMB/FileREST

Azure Files có các cơ chế phối hợp truy cập khác nhau:

- SMB dùng file-system locking/handle do giao thức và hệ điều hành quản lý.
- FileREST SDK có thể sử dụng **lease** để quản lý quyền ghi/xóa trên file qua lease ID.
- Khi cùng truy cập một file qua SMB và FileREST, không nên giả định mọi loại lock có cùng ngữ nghĩa hoặc tự động tương thích.

Ví dụ ứng dụng legacy có thể dùng FileChannel.lock() trên mount SMB:

~~~java
import java.nio.channels.FileChannel;
import java.nio.channels.FileLock;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

Path file = Path.of(
        System.getenv("AZURE_FILES_MOUNT"), "reports/summary.csv");

try (FileChannel channel = FileChannel.open(
        file, StandardOpenOption.WRITE, StandardOpenOption.READ);
     FileLock lock = channel.lock()) {
    // Thực hiện cập nhật trong thời gian giữ lock.
}
~~~

Ví dụ lease ở FileREST có API riêng như ShareLeaseClient. Khi dùng lease, cần acquire, renew (nếu cần) và release đúng vòng đời; nếu tiến trình chết, phải có chiến lược xử lý lease hết hạn. Không dùng SMB file lock trong một module và FileREST lease trong module khác rồi mặc định chúng điều phối hoàn hảo nếu chưa kiểm thử.

## 11. Kiểm thử tích hợp

### 11.1. Azurite không thay thế Azure Files

Azurite hữu ích để mô phỏng một số API Azure Storage như Blob/Queue/Table, nhưng **không cung cấp một Azure Files share đầy đủ** để kiểm thử starter/FileREST/SMB/NFS. Vì vậy:

- Unit test có thể mock interface nghiệp vụ để kiểm tra luồng service.
- Integration test File Share cần **Azure Storage account thử nghiệm** với share riêng.
- Kiểm thử SMB/NFS phải chạy trên môi trường OS/container có mount và network thật.
- Kiểm thử Entra ID/RBAC/private endpoint cần principal và cấu hình Azure tương ứng.

Không đưa account key production vào test; dùng identity hoặc secret riêng cho môi trường test và dọn tài nguyên theo quy trình an toàn.

### 11.2. Các ca kiểm thử nên có

| Ca kiểm thử | Kết quả mong đợi |
|---|---|
| ResourceLoader mở azure-file://share/path/file | Đọc đúng nội dung khi share/file tồn tại và identity có quyền |
| WritableResource.getOutputStream() | Ghi nội dung theo semantics của resolver/version đang dùng |
| File lớn hơn 4 MiB | Xác minh upload thành công, throughput và mức sử dụng RAM thực tế |
| Đường dẫn hoặc share không tồn tại | Lỗi được phân loại rõ; không tạo tài nguyên ngoài ý muốn |
| Identity thiếu role FileREST | Request bị từ chối; ứng dụng không fallback sang key hardcode |
| SMB mount thiếu quyền ACL | Java I/O báo lỗi phù hợp; role/share permission/ACL được kiểm tra riêng |
| File Share network gián đoạn | Timeout/retry có giới hạn; không treo thread vô hạn |
| Hai tiến trình cùng ghi một file | Kiểm tra lock/lease hoặc quy tắc ghi đè theo thiết kế |
| File đích đã tồn tại | Xác minh hành vi overwrite/append được mô tả và xử lý đúng |
| File lớn tải xuống | Dùng stream/file output, không giữ toàn bộ nội dung trong heap |
| Xóa directory không rỗng | Từ chối theo quy tắc dịch vụ hoặc xóa nội dung theo quy trình có kiểm soát |

### 11.3. Ví dụ kiểm tra Resource round-trip

Đoạn kiểm tra dưới đây minh họa đọc/ghi qua ResourceLoader. Trong bộ test thực, dùng JUnit, file name duy nhất và cleanup:

~~~java
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import org.springframework.core.io.Resource;
import org.springframework.core.io.ResourceLoader;
import org.springframework.core.io.WritableResource;

String location = "azure-file://test-share/integration/hello.txt";
Resource resource = resourceLoader.getResource(location);

if (!(resource instanceof WritableResource writable)) {
    throw new IllegalStateException("Resource không hỗ trợ ghi");
}

try (OutputStream output = writable.getOutputStream()) {
    output.write("hello-file-share".getBytes(StandardCharsets.UTF_8));
}

try (InputStream input = resource.getInputStream()) {
    String actual = new String(input.readAllBytes(), StandardCharsets.UTF_8);
    if (!"hello-file-share".equals(actual)) {
        throw new AssertionError("Nội dung đọc lại không khớp");
    }
}
~~~

Ví dụ giả định share, directory và quyền truy cập đã được chuẩn bị; kiểm tra việc tạo file/parent directory theo version resolver đang dùng. Test này dùng chuỗi nhỏ; với file lớn, xác minh stream và không dùng readAllBytes().

## 12. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân cần kiểm tra | Hướng xử lý |
|---|---|---|
| Không phân giải được azure-file:// | Thiếu File Share starter, resolver chưa được auto-configure hoặc URI sai | Kiểm tra dependency, profile, prefix và version |
| HTTP 403 | Thiếu quyền FileREST OAuth, identity sai hoặc Shared Key bị chặn | Xác định principal, role, operation và auth mode |
| SMB Access denied | Share-level role hoặc ACL/NTFS permission không đủ | Kiểm tra identity provider, share role và ACL trên file/directory |
| HTTP 404 | Sai share/path hoặc directory/file chưa được tạo | Kiểm tra resource và provision path |
| HTTP 409 | Share/file/directory đã tồn tại hoặc conflict do thao tác đồng thời | Dùng tên duy nhất hoặc create-if-not-exists theo API |
| Timeout khi mount | Network, DNS, protocol/port hoặc firewall | Kiểm tra route, private endpoint và cấu hình mount |
| Ghi file bị ghi đè ngoài ý muốn | OutputStream/SDK upload đang dùng semantics overwrite | Xác định create/update/append; dùng tên mới hoặc lock/condition |
| File lớn upload chậm | Transfer option, concurrency, network và giới hạn dịch vụ | Đo throughput; điều chỉnh parallel transfer và giới hạn đồng thời |
| Không dùng được OAuth cho share operation | Operation cấp share không hỗ trợ Entra OAuth theo API đang dùng | Dùng management plane hoặc cơ chế được tài liệu operation yêu cầu |
| Azurite test chạy nhưng Azure Files lỗi | Emulator không mô phỏng File Share | Chạy integration test trên Azure account test |

Khi điều tra, log operation, share/path đã được chuẩn hóa, correlation ID và error code; không log account key, connection string hoặc token. Phân biệt lỗi **authentication**, **authorization**, **network** và **resource path** trước khi thay đổi quyền.

## 13. Bảo mật và vận hành production

Một số nguyên tắc khi đưa File Share vào production:

1. **Chọn đúng protocol:** FileREST khi cần API cloud-native; SMB/NFS khi cần filesystem. Tránh dùng cả hai trên cùng dữ liệu nếu chưa hiểu lock, cache và consistency.
2. **Tách quyền runtime và provision:** service xử lý file không cần quyền tạo storage account hoặc thay đổi role assignment.
3. **Dùng identity tối thiểu:** FileREST OAuth role và SMB share-level role/ACL là các mô hình khác nhau; chỉ cấp quyền cho operation thực tế.
4. **Quản lý path an toàn:** ánh xạ ID nghiệp vụ sang đường dẫn do server kiểm soát; không cho phép path traversal hoặc truy cập share ngoài tenant.
5. **Giới hạn tài nguyên:** giới hạn upload size, số tác vụ song song, timeout, thread pool và dung lượng file tạm.
6. **Có phương án phục hồi:** backup/snapshot theo yêu cầu, kiểm tra restore và retention; không coi mount share là backup.
7. **Quan sát:** theo dõi latency, số byte, request lỗi, network disconnect, file handle/lease và dung lượng/quota share.
8. **Kiểm thử khi nâng version:** xác minh URI resolver, authentication, parallel upload và behavior của SDK sau mỗi lần nâng BOM.

## 14. Bài tập tình huống và câu hỏi tự kiểm tra

**Tình huống A — Ứng dụng legacy:** Một ứng dụng Java đang dùng Files.copy() và FileChannel.lock() trên thư mục chia sẻ. Hãy chọn SMB mount, liệt kê các điều kiện hạ tầng và quyền cần cấu hình, rồi giải thích vì sao chỉ thêm File Share starter không tự mount share.

**Tình huống B — Dịch vụ xử lý file qua REST:** Một API cần đọc/ghi file theo ID mà không muốn mount volume. Hãy dùng spring-cloud-azure-starter-storage-file-share, ResourceLoader và URI azure-file://; xác định những thao tác nào nên chuyển sang File Shares SDK.

**Tình huống C — File Share OAuth trả 403:** Local developer chạy được nhưng managed identity trên Azure bị từ chối. Hãy kiểm tra identity đang được chọn, role File Data phù hợp, loại operation (file/directory hay share-level), endpoint và network.

**Tình huống D — Upload báo conflict:** Hai request cùng tạo summary.csv. Hãy thiết kế tên file duy nhất hoặc quy trình update có kiểm soát; giải thích vì sao getFileClient() chỉ lấy client tham chiếu chứ không tạo file.

**Tình huống E — So sánh đa cloud:** Azure Files cung cấp SMB/NFS/FileREST; AWS có các dịch vụ file như Amazon EFS/FSx với giao thức và đặc tính khác nhau; Google Cloud có Filestore cho NFS. So sánh theo **giao thức mount, API SDK, danh tính/quyền, semantics lock và khả năng tương thích ứng dụng**, không giả định một starter hoặc một API có thể thay thế trực tiếp ở mọi provider.

### Câu hỏi tự kiểm tra

1. **Spring Cloud Azure File Share starter cung cấp gì?** Spring Resource abstraction và resolver azure-file:// để đọc/ghi resource trong File Share theo mô hình Spring.
2. **Starter có tự mount SMB/NFS vào máy chạy ứng dụng không?** Không. Mount là trách nhiệm hệ điều hành/hạ tầng; Java NIO chỉ thao tác trên mount point.
3. **Khi nào cần azure-storage-file-share SDK trực tiếp?** Khi cần API chuyên biệt như ShareClient/DirectoryClient/FileClient, create/list/delete, metadata, lease, copy hoặc range.
4. **azure-file://reports/2026/summary.csv gồm những thành phần nào?** Share reports và đường dẫn 2026/summary.csv bên trong share.
5. **Vì sao role Blob Data Contributor không cấp quyền File Share?** Blob và Files là các dịch vụ data-plane riêng; role và authorization model phải phù hợp với File Share.
6. **Vì sao FileREST OAuth và SMB ACL không thể coi là cùng một cơ chế?** FileREST dùng token/role theo operation được hỗ trợ; SMB kết hợp share-level permission và ACL filesystem.
7. **Azurite có đủ để kiểm thử Azure Files không?** Không; cần Azure Storage account test cho File Share và môi trường mount thật cho SMB/NFS.

## 15. Tổng kết

Azure Files cung cấp file share managed có thể truy cập qua **SMB, NFS hoặc FileREST**. Trong Spring Boot, spring-cloud-azure-starter-storage-file-share tích hợp File Share với **Spring Resource abstraction** thông qua URI azure-file://, ResourceLoader, Resource và WritableResource. Khi cần kiểm soát thao tác share/directory/file chi tiết, hãy dùng azure-storage-file-share SDK; khi cần tương thích filesystem, mount SMB/NFS và dùng Java NIO.

Điểm quan trọng là chọn đúng **mô hình truy cập và authorization**: FileREST OAuth, SMB share permission/ACL và NFS POSIX/network có yêu cầu khác nhau. Kết hợp managed identity, quyền tối thiểu, provision bằng IaC, kiểm thử trên Azure thật và giám sát đường truyền để tích hợp File Share ổn định trong Spring Cloud Azure.

### Tài liệu tham khảo chính thức

- [Microsoft Learn — Spring Cloud Azure resource handling](https://learn.microsoft.com/azure/developer/java/spring-framework/resource-handling)
- [Microsoft Learn — Spring Cloud Azure configuration reference](https://learn.microsoft.com/azure/developer/java/spring-framework/configuration)
- [Microsoft Learn — Develop for Azure Files with Java](https://learn.microsoft.com/azure/storage/files/storage-java-how-to-use-file-storage)
- [Microsoft Learn — Azure Files identity-based authentication for SMB](https://learn.microsoft.com/azure/storage/files/storage-files-identity-auth-smb)
- [Microsoft Learn — Azure Storage File Shares client library for Java](https://learn.microsoft.com/java/api/com.azure.storage.file.share)
- [Microsoft Learn — ShareFileClient Java API](https://learn.microsoft.com/java/api/com.azure.storage.file.share.sharefileclient)
- [Microsoft Learn — ShareDirectoryClient Java API](https://learn.microsoft.com/java/api/com.azure.storage.file.share.sharedirectoryclient)
- [Microsoft Learn — Auto-configure Azure SDK clients with Spring Cloud Azure](https://learn.microsoft.com/azure/developer/java/spring-framework/auto-configure-azure-sdk-clients)
