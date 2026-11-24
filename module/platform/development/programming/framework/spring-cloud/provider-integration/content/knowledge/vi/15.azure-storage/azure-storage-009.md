# Dùng Azurite để kiểm thử các khả năng được giả lập

## 1. Bối cảnh và mục tiêu

Trong module **SPRING_CLOUD_PROVIDER_INTEGRATION**, chúng ta thực hành tích hợp Spring Boot với dịch vụ managed của AWS, Azure và Google Cloud qua các thư viện Spring Cloud tương ứng. Người học cần biết cấu hình danh tính và quyền, truy cập storage/messaging/data, bảo vệ secret, kiểm thử tích hợp và đánh giá khác biệt giữa các cloud provider. Bài này thuộc chương **Azure Storage**, tập trung vào **Azurite** — trình giả lập Azure Storage chạy local, giúp phát triển và kiểm thử một số thao tác mà không cần kết nối storage account trên cloud.

Giả sử một API Spring Boot nhận tài liệu, lưu file vào Blob Storage và gửi job qua Queue Storage. Mỗi lần chạy test, nhóm phát triển muốn kiểm tra upload/download, gửi/nhận message, xử lý lỗi và cleanup tài nguyên. Tạo một storage account Azure riêng cho mỗi lần chạy sẽ tốn thời gian và cần credential. Azurite cung cấp môi trường local để kiểm tra các luồng cơ bản này.

Sau bài học, bạn có thể:

- Nêu rõ **Azurite giả lập dịch vụ nào** và những dịch vụ/tính năng nào không được hỗ trợ hoặc chỉ hỗ trợ một phần.
- Cài đặt, khởi động Azurite bằng npm hoặc Docker, cấu hình workspace và cổng dịch vụ.
- Kết nối Azure Storage SDK for Java và Spring Cloud Azure bằng connection string dành riêng cho emulator.
- Viết integration test cho Blob và Queue với dữ liệu cô lập, cleanup và kiểm tra kết quả.
- Đưa Azurite vào quy trình CI để kiểm tra storage logic lặp lại được.
- Phân biệt test với emulator và test trên Azure thật, đặc biệt đối với Microsoft Entra ID, RBAC, network, Azure Files, lifecycle, tier và hiệu năng.

## 2. Azurite là gì và giả lập những gì?

**Azurite** là emulator mã nguồn mở do Microsoft phát triển, chạy trên Node.js, mô phỏng một phần Azure Storage API cho môi trường local. Azurite hỗ trợ ba nhóm dịch vụ:

| Dịch vụ | Cổng mặc định | Mức độ sử dụng trong bài |
|---|---:|---|
| **Blob Storage** | 10000 | Kiểm thử container, block blob và các thao tác blob phổ biến |
| **Queue Storage** | 10001 | Kiểm thử tạo queue, gửi, nhận, cập nhật và xóa message |
| **Table Storage** | 10002 | Có hỗ trợ nhưng trạng thái hiện tại là **Preview**; cần xác minh operation thực tế |

Azurite hữu ích để kiểm tra code gọi Azure Storage SDK, logic upload/download, xử lý message và các luồng tích hợp cơ bản. Nó không phải bản Azure thu nhỏ với đầy đủ tính năng, SLA hoặc khả năng vận hành production.

### 2.1. Những gì không được giả lập

Azurite hiện **không hỗ trợ Azure Files và Azure Data Lake Storage Gen2**. Nó cũng không phải emulator cho **Azure Service Bus, Event Hubs, Cosmos DB, Azure SQL** hoặc các dịch vụ managed khác.

| Chủ đề | Có thể dùng Azurite? | Cần môi trường nào để xác minh đầy đủ? |
|---|---|---|
| Blob upload/download cơ bản | Có | Azure Storage test account để kiểm tra tương thích dịch vụ |
| Blob ETag/conditional request | Có thể kiểm tra operation được Azurite hỗ trợ | Azure thật để xác minh mọi API/điều kiện/version đang dùng |
| Queue send/receive/delete | Có | Azure thật để kiểm tra quyền, network, tải và hành vi production |
| Table Storage | Có, nhưng hỗ trợ đang Preview | Azure Table Storage thật cho tính năng và độ tin cậy cần thiết |
| Azure Files File Share | Không | Azure Files account/share test |
| ADLS Gen2/hierarchical namespace | Không | Storage account bật tính năng ADLS Gen2 |
| Managed identity và RBAC thật | Không xác minh đầy đủ | Workload identity và role assignment trên Azure |
| Lifecycle, access tier, Archive/rehydration | Không thay thế được kiểm thử dịch vụ thật | Azure Storage account có cấu hình phù hợp |
| Firewall/private endpoint/DNS | Không | Mạng và storage account Azure thực tế |
| Azure Service Bus | Không | Service Bus namespace test |

**Quy tắc:** dùng Azurite để kiểm tra logic và giao tiếp API được giả lập; dùng Azure thật để xác minh tính năng cloud, authorization, network, hiệu năng và vận hành.

## 3. Kiến trúc khi chạy test local

Azurite chạy như một process hoặc container riêng. Spring Boot kết nối tới endpoint local qua Azure Storage SDK; test tạo resource có tên riêng, thực hiện thao tác rồi dọn dữ liệu.

~~~mermaid
flowchart LR
    T[JUnit integration tests] --> A[Spring Boot application]
    A -->|Blob SDK / HTTP| B[(Azurite Blob :10000)]
    A -->|Queue SDK / HTTP| Q[(Azurite Queue :10001)]
    A -->|Table SDK / HTTP| TB[(Azurite Table :10002)]
    B --> W[Local workspace]
    Q --> W
    TB --> W
~~~

Cổng mặc định:

- Blob: **http://127.0.0.1:10000**
- Queue: **http://127.0.0.1:10001**
- Table: **http://127.0.0.1:10002**

Azurite thường dùng tài khoản mặc định **devstoreaccount1** và một account key dành riêng cho emulator. Endpoint mặc định đưa account name vào **đường dẫn URI**, ví dụ:

~~~text
http://127.0.0.1:10000/devstoreaccount1/container/blob.txt
http://127.0.0.1:10001/devstoreaccount1/document-jobs
http://127.0.0.1:10002/devstoreaccount1/Tables
~~~

Khác với Azure public cloud, tên account mặc định không nằm trong hostname kiểu account.blob.core.windows.net. Do đó phải dùng connection string/endpoint của Azurite, không tái sử dụng endpoint production rồi chỉ thay account name.

## 4. Cài đặt và khởi động Azurite

Có thể cài Azurite bằng npm, Docker hoặc extension Visual Studio Code. Hai cách dưới đây phù hợp cho môi trường phát triển và CI.

### 4.1. Cài bằng npm trên máy local

Cần Node.js và npm. Cài Azurite:

~~~powershell
npm install --global azurite
~~~

Tạo thư mục lưu dữ liệu và khởi động ba dịch vụ:

~~~powershell
New-Item -ItemType Directory -Force .\azurite-data | Out-Null
azurite --silent --location .\azurite-data --debug .\azurite-data\debug.log
~~~

Giải thích:

- **--location**: workspace lưu dữ liệu emulator; nếu không chỉ định, Azurite dùng thư mục làm việc hiện tại.
- **--debug**: ghi thông tin request và lỗi chi tiết vào file log. Chỉ bật khi cần chẩn đoán; kiểm tra log trước khi chia sẻ vì nó có thể chứa thông tin request.
- **--silent**: tắt access log trên console; không làm thay đổi dữ liệu hay quyền.
- Mặc định Azurite lắng nghe Blob/Queue/Table trên các cổng 10000/10001/10002.

Kiểm tra phiên bản và tùy chọn:

~~~powershell
azurite --version
azurite --help
~~~

Giữ terminal chạy Azurite trong lúc test. Khi dừng process, dữ liệu trên đĩa trong azurite-data vẫn còn; nếu dùng chế độ in-memory, dữ liệu sẽ mất khi process kết thúc.

### 4.2. Chạy bằng Docker trên Windows

Tạo thư mục lưu dữ liệu:

~~~powershell
New-Item -ItemType Directory -Force .\azurite-data | Out-Null
~~~

Khởi động container, publish cổng về loopback và mount workspace:

~~~powershell
docker run --rm -p 127.0.0.1:10000:10000 -p 127.0.0.1:10001:10001 -p 127.0.0.1:10002:10002 -v "$((Get-Location).Path)/azurite-data:/data" mcr.microsoft.com/azure-storage/azurite
~~~

Volume azurite-data giúp dữ liệu tồn tại qua lần khởi động container. Nếu không mount volume, dữ liệu nằm trong filesystem của container và có thể mất khi container bị xóa.

Trên Linux/macOS có thể dùng cùng image và thay đường dẫn volume theo shell, ví dụ:

~~~bash
docker run --rm -p 127.0.0.1:10000:10000 -p 127.0.0.1:10001:10001 -p 127.0.0.1:10002:10002 -v "$(pwd)/azurite-data:/data" mcr.microsoft.com/azure-storage/azurite
~~~

Trong CI, pin image version nếu cần build lặp lại ổn định; tránh để pipeline tự đổi behavior khi tag image thay đổi.

### 4.3. Chỉ chạy dịch vụ cần thiết

Nếu test chỉ dùng Blob, có thể chạy riêng Blob service:

~~~bash
docker run --rm -p 127.0.0.1:10000:10000 mcr.microsoft.com/azure-storage/azurite azurite-blob --blobHost 0.0.0.0 --blobPort 10000
~~~

Với Docker image, kiểm tra entrypoint và cú pháp command của image version đang dùng. Chỉ mở cổng của dịch vụ cần thiết giúp giảm tài nguyên và tránh nhầm endpoint.

## 5. Kết nối bằng connection string của emulator

Azurite cung cấp account mặc định devstoreaccount1 và account key cố định dành riêng cho môi trường giả lập. Với cổng mặc định, connection string đầy đủ cho Blob và Queue có dạng:

~~~text
DefaultEndpointsProtocol=http;
AccountName=devstoreaccount1;
AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw==;
BlobEndpoint=http://127.0.0.1:10000/devstoreaccount1;
QueueEndpoint=http://127.0.0.1:10001/devstoreaccount1;
~~~

Nếu cần Table, thêm endpoint:

~~~text
TableEndpoint=http://127.0.0.1:10002/devstoreaccount1;
~~~

Đây là **key công khai dành cho emulator**, không phải account key của Azure thật. Dù vậy, chỉ dùng connection string này trong profile/test local; không đưa vào cấu hình production hoặc dùng làm mẫu cho việc quản lý secret cloud.

### 5.1. Connection string riêng cho Blob

~~~text
DefaultEndpointsProtocol=http;
AccountName=devstoreaccount1;
AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw==;
BlobEndpoint=http://127.0.0.1:10000/devstoreaccount1;
~~~

### 5.2. Connection string riêng cho Queue

~~~text
DefaultEndpointsProtocol=http;
AccountName=devstoreaccount1;
AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw==;
QueueEndpoint=http://127.0.0.1:10001/devstoreaccount1;
~~~

Đặt các chuỗi này trong biến môi trường local:

~~~powershell
$env:AZURITE_BLOB_CONNECTION_STRING = "DefaultEndpointsProtocol=http;AccountName=devstoreaccount1;AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw==;BlobEndpoint=http://127.0.0.1:10000/devstoreaccount1;"
$env:AZURITE_QUEUE_CONNECTION_STRING = "DefaultEndpointsProtocol=http;AccountName=devstoreaccount1;AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw==;QueueEndpoint=http://127.0.0.1:10001/devstoreaccount1;"
~~~

### 5.3. Khi Spring Boot cũng chạy trong Docker

Trong container ứng dụng, **127.0.0.1 trỏ về chính container ứng dụng**, không phải container Azurite. Khi hai container ở cùng Docker network, hãy dùng hostname/service name của Azurite, ví dụ azurite, trong endpoint:

~~~text
BlobEndpoint=http://azurite:10000/devstoreaccount1;
QueueEndpoint=http://azurite:10001/devstoreaccount1;
~~~

Nếu ứng dụng trong container cần truy cập emulator chạy trên host, Docker Desktop thường cung cấp hostname host.docker.internal; kiểm tra khả năng phân giải tên trên môi trường CI/Linux cụ thể. Endpoint trong connection string phải là hostname mà **process Spring Boot thực sự truy cập được**, không nhất thiết là hostname mà trình duyệt trên host nhìn thấy.

## 6. Cấu hình Spring Cloud Azure với profile Azurite

### 6.1. Dependencies

Ví dụ Maven dùng Spring Cloud Azure Blob và Queue starter. Chọn BOM tương thích với phiên bản Spring Boot của dự án:

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
        <artifactId>spring-cloud-azure-starter-storage-blob</artifactId>
    </dependency>
    <dependency>
        <groupId>com.azure.spring</groupId>
        <artifactId>spring-cloud-azure-starter-storage-queue</artifactId>
    </dependency>
</dependencies>
~~~

spring-cloud-azure.version phải được khai báo theo bảng tương thích Spring Boot/Spring Cloud Azure. Không tự chọn version khác nhau cho các Azure SDK mà BOM đang quản lý.

### 6.2. Profile application-azurite.yml

Spring Cloud Azure có cấu hình connection string theo từng dịch vụ:

~~~yaml
spring:
  cloud:
    azure:
      storage:
        blob:
          connection-string: ${AZURITE_BLOB_CONNECTION_STRING}
          container-name: integration-documents
        queue:
          connection-string: ${AZURITE_QUEUE_CONNECTION_STRING}
          queue-name: integration-jobs
~~~

Các property quan trọng:

- spring.cloud.azure.storage.blob.connection-string: kết nối Blob SDK tới Azurite.
- spring.cloud.azure.storage.queue.connection-string: kết nối Queue SDK tới Azurite.
- container-name và queue-name: tài nguyên mặc định mà auto-configuration sử dụng khi property tương ứng được hỗ trợ trong BOM đã chọn.

Kích hoạt profile khi chạy test:

~~~powershell
$env:SPRING_PROFILES_ACTIVE = "azurite"
~~~

Hoặc dùng ActiveProfiles("azurite") trong test Spring Boot. Không để profile này tự động bật trong production. Profile cloud thật cần endpoint/credential riêng và ưu tiên Microsoft Entra ID/managed identity; emulator dùng connection string Shared Key giả lập.

### 6.3. Inject client auto-configured

Sau khi starter và cấu hình hợp lệ, có thể inject Azure SDK client do Spring Cloud Azure auto-configure:

~~~java
import com.azure.storage.blob.BlobServiceClient;
import com.azure.storage.queue.QueueServiceClient;
import org.springframework.stereotype.Component;

@Component
public class StorageClients {
    private final BlobServiceClient blobServiceClient;
    private final QueueServiceClient queueServiceClient;

    public StorageClients(
            BlobServiceClient blobServiceClient,
            QueueServiceClient queueServiceClient) {
        this.blobServiceClient = blobServiceClient;
        this.queueServiceClient = queueServiceClient;
    }
}
~~~

Điểm cần kiểm tra trong test context là ứng dụng đã chọn đúng profile, property đã được nạp và các bean kết nối tới **endpoint local**. Không chỉ nhìn thấy bean được tạo rồi kết luận emulator đang hoạt động; hãy thực hiện một request thật và xác minh kết quả.

## 7. Kết nối trực tiếp bằng Azure SDK for Java

Khi muốn test riêng Azure SDK, có thể tạo client từ connection string mà không cần Spring context.

### 7.1. BlobServiceClient

~~~java
import com.azure.storage.blob.BlobServiceClient;
import com.azure.storage.blob.BlobServiceClientBuilder;

String connectionString =
        System.getenv("AZURITE_BLOB_CONNECTION_STRING");
if (connectionString == null || connectionString.isBlank()) {
    throw new IllegalStateException("Thiếu connection string cho Azurite Blob");
}

BlobServiceClient blobServiceClient =
        new BlobServiceClientBuilder()
                .connectionString(connectionString)
                .buildClient();
~~~

### 7.2. QueueServiceClient

~~~java
import com.azure.storage.queue.QueueServiceClient;
import com.azure.storage.queue.QueueServiceClientBuilder;

String connectionString =
        System.getenv("AZURITE_QUEUE_CONNECTION_STRING");
if (connectionString == null || connectionString.isBlank()) {
    throw new IllegalStateException("Thiếu connection string cho Azurite Queue");
}

QueueServiceClient queueServiceClient =
        new QueueServiceClientBuilder()
                .connectionString(connectionString)
                .buildClient();
~~~

Client được tái sử dụng qua nhiều thao tác trong cùng ứng dụng/test fixture. Không tạo lại HTTP pipeline và client cho mỗi blob hoặc message.

## 8. Integration test cho Blob Storage

Một integration test cơ bản nên xác minh **ghi dữ liệu rồi đọc lại đúng nội dung**. Tạo container riêng cho test, không dùng chung tên cố định giữa các test chạy song song.

~~~java
import com.azure.core.util.BinaryData;
import com.azure.storage.blob.BlobClient;
import com.azure.storage.blob.BlobContainerClient;
import com.azure.storage.blob.BlobServiceClient;
import com.azure.storage.blob.BlobServiceClientBuilder;
import org.junit.jupiter.api.Test;
import java.util.UUID;
import static org.junit.jupiter.api.Assertions.assertEquals;

class AzuriteBlobIntegrationTest {
    @Test
    void uploadAndDownloadBlob() {
        String connection =
                System.getenv("AZURITE_BLOB_CONNECTION_STRING");
        BlobServiceClient service =
                new BlobServiceClientBuilder()
                        .connectionString(connection)
                        .buildClient();

        String containerName =
                "it-" + UUID.randomUUID().toString().replace("-", "");
        BlobContainerClient container =
                service.getBlobContainerClient(containerName);
        container.createIfNotExists();

        try {
            BlobClient blob = container.getBlobClient("hello.txt");
            blob.upload(BinaryData.fromString("hello-azurite"), true);

            String actual = blob.downloadContent().toString();
            assertEquals("hello-azurite", actual);
        } finally {
            container.deleteIfExists();
        }
    }
}
~~~

Đây là ví dụ minh họa; trong test class đầy đủ cần kiểm tra biến môi trường trước khi build client và dùng assertion phù hợp. downloadContent() đưa nội dung vào bộ nhớ nên chỉ dùng với payload nhỏ. Với file lớn, dùng stream hoặc file output và so sánh checksum/kích thước theo từng phần.

### 8.1. Các trường hợp Blob nên kiểm tra

- Tạo container, upload blob và download đúng byte.
- List blob theo prefix và kiểm tra metadata/Content-Type nếu API đó được dùng.
- Upload trùng tên với overwrite bật/tắt theo yêu cầu nghiệp vụ.
- Conditional request/ETag cho các operation được Azurite hỗ trợ.
- Xóa blob/container và kiểm tra cleanup.
- Lỗi khi container không tồn tại hoặc tên resource không hợp lệ.

Không kết luận Azurite đã kiểm thử đầy đủ versioning, lifecycle, tier, soft delete hoặc Archive chỉ vì một test upload/download thành công. Những tính năng phụ thuộc cloud service cần test trên Azure thật.

## 9. Integration test cho Queue Storage

Test Queue cần kiểm tra gửi, nhận và xóa bằng pop receipt của lần nhận:

~~~java
import com.azure.storage.queue.QueueClient;
import com.azure.storage.queue.QueueClientBuilder;
import com.azure.storage.queue.models.QueueMessageItem;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class AzuriteQueueIntegrationTest {
    @Test
    void sendReceiveAndDeleteMessage() {
        String connection =
                System.getenv("AZURITE_QUEUE_CONNECTION_STRING");
        String queueName =
                "it-" + UUID.randomUUID().toString().replace("-", "");

        QueueClient queue = new QueueClientBuilder()
                .connectionString(connection)
                .queueName(queueName)
                .buildClient();
        queue.createIfNotExists();

        try {
            queue.sendMessage("{\"jobId\":\"job-42\"}");

            Iterable<QueueMessageItem> received = queue.receiveMessages(1);
            var iterator = received.iterator();
            assertTrue(iterator.hasNext(), "Message phải được nhận");

            QueueMessageItem message = iterator.next();
            assertEquals("{\"jobId\":\"job-42\"}", message.getMessageText());

            queue.deleteMessage(
                    message.getMessageId(),
                    message.getPopReceipt());
        } finally {
            queue.deleteIfExists();
        }
    }
}
~~~

Ví dụ kiểm tra thao tác queue cơ bản. Trong bộ test thực, quản lý cleanup cả khi tạo queue lỗi giữa chừng và tránh dùng chung queue giữa test song song.

### 9.1. Các trường hợp Queue nên kiểm tra

- Producer gửi JSON và consumer đọc đúng message body.
- Consumer xóa message bằng message ID/pop receipt hợp lệ.
- Message không bị xóa có thể xuất hiện lại sau visibility timeout.
- Update message/visibility và sử dụng pop receipt mới theo API được hỗ trợ.
- Queue rỗng, queue chưa tồn tại và tên queue không hợp lệ.
- Message quá giới hạn hoặc encoding không thống nhất.

Azurite giúp kiểm tra luồng SDK và logic consumer; Azure thật vẫn cần thiết để xác minh role data-plane, throttling, scale và hành vi dịch vụ ở tải thực.

## 10. Kiểm thử với Spring Boot Test

Nếu ứng dụng dùng Spring Cloud Azure auto-configuration, nên có ít nhất một test khởi động Spring context với profile Azurite. Ví dụ cấu trúc:

~~~java
import com.azure.storage.blob.BlobServiceClient;
import com.azure.storage.queue.QueueServiceClient;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import static org.junit.jupiter.api.Assertions.assertNotNull;

@SpringBootTest
@ActiveProfiles("azurite")
class StorageAutoConfigurationTest {
    @Autowired
    BlobServiceClient blobServiceClient;

    @Autowired
    QueueServiceClient queueServiceClient;

    @Test
    void storageClientsAreConfigured() {
        assertNotNull(blobServiceClient);
        assertNotNull(queueServiceClient);
        assertNotNull(blobServiceClient.getBlobContainerClient(
                "integration-documents"));
        assertNotNull(queueServiceClient.getQueueClient(
                "integration-jobs"));
    }
}
~~~

Test này chỉ xác minh bean và client được cấu hình. Để chứng minh kết nối thực sự, cần gọi một thao tác như getProperties, createIfNotExists, sendMessage hoặc upload/download và kiểm tra kết quả.

Nếu service của ứng dụng phụ thuộc interface riêng, có thể viết test service bằng client thật trỏ tới Azurite, thay vì mock mọi SDK method. Mock vẫn hữu ích cho unit test nhánh lỗi, nhưng không kiểm tra serialization HTTP, endpoint và tương tác SDK/emulator.

## 11. Cô lập dữ liệu và cleanup

Azurite mặc định lưu dữ liệu vào workspace, vì vậy dữ liệu có thể còn sau khi test kết thúc. Nếu mọi test cùng dùng một container/queue cố định, các lần chạy có thể ảnh hưởng lẫn nhau.

Một số nguyên tắc:

1. Dùng tên resource có prefix test và UUID/run ID.
2. Dọn container, queue và blob trong finally hoặc lifecycle hook, kể cả khi assertion thất bại.
3. Không để test xóa container dùng chung của developer hoặc test suite khác.
4. Với test song song, mỗi test hoặc mỗi worker dùng resource riêng.
5. Có thể xóa workspace Azurite khi cần reset toàn bộ dữ liệu, nhưng chỉ thực hiện khi emulator đã dừng và workspace đó dành riêng cho test.
6. Không dùng --inMemoryPersistence nếu cần giữ dữ liệu qua lần restart; nếu bật chế độ này, toàn bộ dữ liệu mất khi process kết thúc.

Một chiến lược đơn giản là **resource-per-test** cho container/queue, còn một chiến lược khác là **resource-per-test-run** rồi cleanup toàn bộ sau suite. Chọn cách phù hợp với số lượng test và mức song song.

## 12. Tích hợp Azurite vào CI

Trong CI, Azurite có thể chạy như một service/container trước khi test bắt đầu. Pipeline cần:

- Khởi động Azurite và chờ cổng Blob/Queue sẵn sàng.
- Cấp connection string emulator qua environment variable.
- Chạy test Spring Boot/JUnit.
- Thu thập test report và log khi thất bại.
- Dọn container và workspace sau job.

Ví dụ các biến môi trường cho test runner:

~~~text
AZURITE_BLOB_CONNECTION_STRING=<connection-string-blob-local>
AZURITE_QUEUE_CONNECTION_STRING=<connection-string-queue-local>
SPRING_PROFILES_ACTIVE=azurite
~~~

Nếu test runner chạy trong container khác, endpoint trong connection string phải dùng **tên service/container** trên cùng Docker network thay cho 127.0.0.1. Nếu pipeline dùng cổng động, truyền endpoint/port được cấp vào test configuration thay vì hardcode.

Không cần đưa Azure account key thật vào CI cho các bài test emulator. Tuy nhiên, pipeline riêng chạy **Azure integration test** cần identity/credential riêng, role tối thiểu và storage account test tách khỏi production.

## 13. Những giới hạn phải biết trước khi tin kết quả test

Azurite được thiết kế cho phát triển và kiểm thử, không có bảo đảm hiệu năng hoặc khả năng scale như Azure Storage. Một số khác biệt quan trọng:

| Giới hạn | Ảnh hưởng đến test |
|---|---|
| Chỉ mô phỏng Blob, Queue và Table; Table đang Preview | Không dùng để xác minh Azure Files, ADLS Gen2 hoặc Table feature cần độ tin cậy production |
| Một số API/header/parameter chưa được hỗ trợ đầy đủ | Test pass không chứng minh mọi operation của Azure thật sẽ pass |
| Error message có thể khác Azure, dù status code có thể tương đồng | Không phụ thuộc nội dung chuỗi lỗi để phân loại nghiệp vụ |
| Không có performance guarantee, không hỗ trợ số lượng lớn client như production | Không dùng làm benchmark throughput, latency hoặc scale test |
| Default account dùng Shared Key giả lập | Không chứng minh managed identity/RBAC production hoạt động |
| OAuth basic chỉ kiểm tra một số claim như issuer, audience, expiry; không xác minh chữ ký token và quyền | Không coi đây là bài test bảo mật Microsoft Entra ID |
| Chạy trên local network | Không mô phỏng đầy đủ firewall, private endpoint, DNS, routing, TLS trust và failover của Azure |
| Không mô phỏng Service Bus | Không kiểm thử topic, subscription, session, DLQ hay Service Bus transaction |

### 13.1. Strict mode, loose mode và API version

Azurite có chế độ strict mặc định để từ chối một số header/parameter không được hỗ trợ. Tùy chọn **--loose** khiến emulator bỏ qua một số thành phần không hỗ trợ:

~~~bash
azurite --loose
~~~

Chỉ dùng loose mode khi có lý do cụ thể để thử nghiệm tương thích. Không bật nó chỉ để làm test pass, vì như vậy có thể che giấu việc ứng dụng gửi request không phù hợp.

Azurite cũng kiểm tra API version của request. **--skipApiVersionCheck** có thể bỏ qua kiểm tra phiên bản, nhưng không có nghĩa emulator đã triển khai đầy đủ API version đó. Khi SDK nâng cấp, nên xác minh API version và operation mà Azurite hỗ trợ; nếu khác biệt ảnh hưởng chức năng, tạo Azure integration test.

### 13.2. OAuth và giới hạn kiểm thử danh tính

Azurite có tùy chọn OAuth basic và yêu cầu HTTPS khi bật OAuth. Chế độ này có thể kiểm tra một số thông tin token như issuer, audience và expiry, nhưng **không kiểm tra chữ ký token hoặc quyền của principal** như Azure Storage thực hiện.

Do đó, bài test dùng connection string Shared Key với Azurite chỉ chứng minh client có thể gọi emulator. Nó không chứng minh:

- Managed identity được gắn đúng vào App Service/VM/Container Apps.
- Role Storage Blob Data Contributor hoặc Storage Queue Data Message Processor đã được gán đúng principal/scope.
- Storage firewall/private endpoint cho phép workload.
- SAS có permission, expiry và phạm vi đúng trên Azure thật.

Những điều này phải được kiểm tra bằng một Azure test environment có cấu hình thực.

## 14. Quy trình kiểm thử hai tầng

Một quy trình hợp lý cho Spring Cloud Azure gồm hai lớp:

~~~mermaid
flowchart TD
    A[Code thay đổi] --> B[Unit tests: mock logic nghiệp vụ]
    B --> C[Integration tests với Azurite]
    C --> D{Blob/Queue API cơ bản pass?}
    D -->|Không| E[Sửa logic, config, serialization]
    E --> C
    D -->|Có| F[Azure integration tests]
    F --> G{RBAC, network, cloud features pass?}
    G -->|Không| H[Sửa identity, policy, endpoint hoặc operation]
    H --> F
    G -->|Có| I[Review và phát hành theo quy trình]
~~~

| Lớp kiểm thử | Công cụ/môi trường | Câu hỏi cần trả lời |
|---|---|---|
| Unit test | JUnit + mock/fake | Logic validate, retry, mapping, idempotency có đúng không? |
| Storage integration local | Azurite | SDK gọi đúng endpoint, upload/receive/metadata cơ bản có hoạt động không? |
| Azure integration | Storage account test | RBAC, managed identity, SAS, firewall, lifecycle, versioning/tier có hoạt động không? |
| Load/performance | Azure test environment có cấu hình gần production | Throughput, latency, concurrency, throttling và chi phí ra sao? |
| Recovery/operations | Azure staging và runbook | Khôi phục dữ liệu, rehydrate, xử lý lỗi và quan sát vận hành có đáp ứng không? |

Không nhất thiết mọi commit đều chạy toàn bộ Azure integration test; có thể chạy nhanh unit + Azurite ở mỗi pull request, rồi chạy cloud integration ở nhánh chính hoặc lịch định kỳ. Nhưng trước khi phát hành tính năng phụ thuộc cloud-specific behavior, phải có bằng chứng từ Azure thật.

## 15. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| Connection refused ở cổng 10000/10001 | Azurite chưa chạy hoặc service chưa mở cổng | Kiểm tra process/container và port mapping |
| Spring Boot kết nối 127.0.0.1 thất bại trong Docker | Localhost trỏ về app container | Dùng service hostname hoặc host gateway |
| HTTP 404 khi gọi Blob/Queue | Sai endpoint path/account name hoặc resource chưa tạo | Kiểm tra connection string và tên resource |
| Authentication failed | Connection string sai, thiếu endpoint hoặc key không khớp custom account | Dùng đúng default devstore account hoặc cấu hình account/key tương ứng |
| API version không được hỗ trợ | SDK dùng API version Azurite chưa mô phỏng | Cập nhật Azurite/SDK tương thích hoặc kiểm thử operation trên Azure thật |
| Table test không ổn định | Table API còn Preview hoặc operation chưa được hỗ trợ | Giới hạn test và xác minh trên Azure Table Storage |
| Test chạy riêng được nhưng chạy song song lỗi | Dùng chung tên container/queue/blob | Tạo tên duy nhất cho từng test/run |
| Dữ liệu cũ xuất hiện ở lần chạy sau | Workspace được persist trên đĩa | Cleanup resource hoặc reset workspace dành riêng cho test |
| Test pass nhưng production trả 403 | Azurite không kiểm tra RBAC production | Kiểm tra principal, role, scope và network trên Azure |
| Upload/download nhanh ở local nhưng chậm trên cloud | Emulator không đại diện hiệu năng và network cloud | Load test trên Azure staging |
| Loose mode làm test pass | Emulator bỏ qua header/parameter không hỗ trợ | Bỏ loose mode và xác minh operation trên Azure |

Khi debug, ghi lại endpoint, operation, status code, Azure request ID nếu có và version SDK/Azurite. Không ghi account key thật, SAS token hoặc nội dung nhạy cảm vào log. Nếu cần debug chi tiết, bật --debug trong môi trường local và không chia sẻ log trước khi rà soát.

## 16. Bài tập thực hành và câu hỏi tự kiểm tra

**Bài 1 — Khởi động Azurite:** Cài bằng npm hoặc Docker, lưu workspace vào thư mục riêng và xác nhận ba cổng Blob/Queue/Table đang hoạt động. Dùng Storage Explorer để quan sát container và queue sau khi chạy test.

**Bài 2 — Blob round-trip:** Viết JUnit test tạo container ngẫu nhiên, upload một file nhỏ, download lại và so sánh byte. Sau test, xác nhận container đã được xóa.

**Bài 3 — Queue message:** Viết test gửi JSON, nhận message, kiểm tra body và xóa bằng message ID/pop receipt. Mở rộng để chứng minh message có thể xuất hiện lại khi không xóa và visibility timeout hết.

**Bài 4 — Spring profile:** Tạo application-azurite.yml với connection string Blob/Queue riêng. Chạy Spring context bằng ActiveProfiles("azurite") và xác minh client bean thực hiện được một request.

**Bài 5 — CI:** Chạy Azurite như container service trong pipeline. Đảm bảo test runner chờ emulator sẵn sàng, dùng hostname đúng trong Docker network và cleanup resource.

**Bài 6 — Phân định phạm vi:** Lập danh sách tính năng dự án đang dùng: Blob, Queue, Files, Service Bus, RBAC, lifecycle, Archive. Đánh dấu phần nào test được bằng Azurite và phần nào bắt buộc phải test trên Azure.

### Câu hỏi tự kiểm tra

1. **Azurite hỗ trợ những dịch vụ nào?** Blob Storage, Queue Storage và Table Storage; Table đang Preview.
2. **Azurite có hỗ trợ Azure Files không?** Không. File Share cần Azure Storage account thật để integration test.
3. **Azurite có kiểm thử được Service Bus không?** Không. Service Bus cần namespace test riêng.
4. **Tại sao không dùng connection string 127.0.0.1 khi app ở container khác?** Vì localhost trỏ về container của ứng dụng; cần hostname trên Docker network hoặc host gateway.
5. **Default account của Azurite là gì?** devstoreaccount1 với account key dành riêng cho emulator và endpoint local.
6. **Test pass trên Azurite có chứng minh RBAC đúng không?** Không. Phải xác minh role assignment và managed identity trên Azure thật.
7. **Có nên dùng loose mode để mọi test đều pass không?** Không. Nó có thể bỏ qua header/parameter không hỗ trợ và che giấu khác biệt API.
8. **Có thể dùng Azurite để benchmark throughput production không?** Không. Azurite không có performance guarantee hoặc khả năng scale tương đương Azure.
9. **Vì sao phải dùng tên resource riêng cho mỗi test?** Để test song song và dữ liệu persist không ảnh hưởng lẫn nhau.
10. **Khi nào cần Azure integration test?** Khi tính năng phụ thuộc Entra ID/RBAC, Files, ADLS Gen2, lifecycle/tier, network, performance hoặc behavior cloud-specific.

## 17. Tổng kết

Azurite giúp rút ngắn vòng lặp phát triển bằng cách cung cấp môi trường local cho **Blob Storage, Queue Storage và Table Storage**. Với Spring Boot, có thể kết nối qua Azure Storage SDK for Java hoặc Spring Cloud Azure bằng connection string dành cho emulator, sau đó viết integration test để kiểm tra upload/download, gửi/nhận message và các luồng cơ bản. Tên resource cần được cô lập, dữ liệu phải cleanup và profile Azurite phải tách khỏi production.

Azurite có giới hạn rõ ràng: **Table đang Preview; Azure Files và ADLS Gen2 không được hỗ trợ; OAuth basic không xác minh chữ ký/quyền như Azure; hiệu năng và error behavior không bảo đảm giống cloud**. Hãy kết hợp unit test, Azurite integration test và Azure integration test để kiểm tra đầy đủ cả logic ứng dụng lẫn identity, RBAC, network và các tính năng managed thực tế.

### Tài liệu tham khảo chính thức

- [Microsoft Learn — Use the Azurite emulator for local Azure Storage development](https://learn.microsoft.com/azure/storage/common/storage-use-azurite)
- [Microsoft Learn — Install and run Azurite](https://learn.microsoft.com/azure/storage/common/storage-install-azurite)
- [Microsoft Learn — Connect to Azurite with SDKs and tools](https://learn.microsoft.com/azure/storage/common/storage-connect-azurite)
- [Microsoft Learn — Run automated tests by using Azurite](https://learn.microsoft.com/azure/storage/blobs/use-azurite-to-run-automated-tests)
- [Microsoft Learn — Azure Storage configuration properties for Spring Cloud Azure](https://learn.microsoft.com/azure/developer/java/spring-framework/configuration-properties-azure-storage)
- [Microsoft Learn — Azure Storage Queue configuration properties for Spring Cloud Azure](https://learn.microsoft.com/azure/developer/java/spring-framework/configuration-properties-azure-storage-queue)
- [Microsoft Learn — Azure Storage Blob configuration properties for Spring Cloud Azure](https://learn.microsoft.com/azure/developer/java/spring-framework/configuration-properties-azure-storage-blob)
