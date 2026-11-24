# Azurite cho Storage và giới hạn các dịch vụ Azure được giả lập

> **Chương:** Kiểm thử tích hợp  
> **Module:** SPRING_CLOUD_PROVIDER_INTEGRATION  
> **Mục tiêu:** Dùng Azurite trong integration test Spring Boot để kiểm tra Blob, Queue và Table Storage; cấu hình Azure SDK với endpoint local; quản lý container bằng Testcontainers; nhận diện giới hạn về API, xác thực, mạng và các dịch vụ Azure không thuộc phạm vi Azurite.

## 1. Azurite là gì?

Azurite là emulator mã nguồn mở của Azure Storage, chạy cục bộ để developer và CI kiểm tra ứng dụng dùng Azure Storage SDK. Ứng dụng gửi request qua Storage REST API và nhận response từ một service đang chạy, vì vậy Azurite hữu ích hơn mock khi cần xác minh cách SDK tạo request, serialize dữ liệu, xử lý metadata hoặc đọc/ghi object.

Azurite hiện hỗ trợ ba service:

- **Blob Storage:** container và blob, upload/download, metadata, properties, lease và nhiều thao tác Blob API được hỗ trợ.
- **Queue Storage:** queue và message theo mô hình Azure Storage Queue.
- **Table Storage:** table và entity; hỗ trợ hiện vẫn ở trạng thái preview.

Azurite không phải một Azure cloud thu nhỏ. Nó mô phỏng một phần Azure Storage API để phát triển và kiểm thử. Nó không triển khai Azure Files hoặc Azure Data Lake Storage Gen2. Nó cũng không giả lập Service Bus, Event Hubs, Cosmos DB, Key Vault hay mọi dịch vụ managed khác.

Trong module Spring Cloud Provider Integration, hãy dùng Azurite để kiểm tra adapter storage và luồng ứng dụng cần Blob/Queue/Table. Khi cần xác minh Entra ID, RBAC, private endpoint, quota, replication hoặc behavior chỉ có trên managed service, cần test với Azure test account/subscription phù hợp.

## 2. Phân biệt Azurite với các emulator Azure khác

Không nên dùng tên “Azure emulator” như thể mọi service đều chạy trong một container. Các dịch vụ có protocol, dependency và feature set khác nhau.

| Dịch vụ Azure | Emulator/công cụ | Phạm vi kiểm tra điển hình |
| --- | --- | --- |
| Blob Storage | Azurite | Upload/download, container, metadata, content type, properties và API Blob được hỗ trợ |
| Queue Storage | Azurite | Create queue, gửi, nhận, peek, cập nhật và xóa message trong phạm vi API được hỗ trợ |
| Table Storage | Azurite | CRUD entity và truy vấn cơ bản; service đang preview |
| Azure Files | Không có trong Azurite | Cần test trên Azure Files thật hoặc test double cho logic độc lập |
| Data Lake Storage Gen2 | Không có trong Azurite | Cần Azure thật để xác minh hierarchical namespace, ACL và Data Lake API |
| Azure Service Bus | Service Bus emulator riêng | Queue/topic, sender/processor và một phần AMQP behavior |
| Azure Event Hubs | Event Hubs emulator riêng | Producer/consumer và partition configuration trong phạm vi emulator |
| Azure Cosmos DB | Cosmos DB emulator riêng | Client/API Cosmos DB, cấu hình TLS và certificate |
| Azure Key Vault | Không thuộc Azurite | Dùng fake cho logic ứng dụng và Azure test vault cho identity, RBAC, network, rotation |

Testcontainers Java Azure module cung cấp các container riêng cho Azurite, Service Bus emulator, Event Hubs emulator và Cosmos DB emulator. Azure module được đánh dấu **incubating**; API có thể thay đổi giữa các version. Không dùng Azurite để kiểm tra message broker semantics của Service Bus: Queue Storage và Service Bus là hai dịch vụ khác nhau.

## 3. Thêm Azurite vào Testcontainers

### 3.1. Dependency Maven

Dùng Testcontainers BOM để giữ version của core, JUnit và Azure module đồng nhất. Ví dụ dùng version 2.0.5; hãy chọn một version đã được xác minh với JDK và Spring Boot của dự án.

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.testcontainers</groupId>
            <artifactId>testcontainers-bom</artifactId>
            <version>2.0.5</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>org.testcontainers</groupId>
        <artifactId>testcontainers-junit-jupiter</artifactId>
        <scope>test</scope>
    </dependency>

    <dependency>
        <groupId>org.testcontainers</groupId>
        <artifactId>testcontainers-azure</artifactId>
        <scope>test</scope>
    </dependency>

    <dependency>
        <groupId>com.azure</groupId>
        <artifactId>azure-storage-blob</artifactId>
        <scope>test</scope>
    </dependency>

    <dependency>
        <groupId>com.azure</groupId>
        <artifactId>azure-storage-queue</artifactId>
        <scope>test</scope>
    </dependency>

    <dependency>
        <groupId>com.azure</groupId>
        <artifactId>azure-data-tables</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

Chỉ thêm Azure SDK artifact mà test hoặc adapter sử dụng. Nếu các SDK đã được khai báo trong main dependencies của ứng dụng, không cần khai báo lặp lại ở test scope.

### 3.2. Dependency Gradle

```groovy
dependencies {
    testImplementation platform("org.testcontainers:testcontainers-bom:2.0.5")
    testImplementation "org.testcontainers:testcontainers-junit-jupiter"
    testImplementation "org.testcontainers:testcontainers-azure"

    testImplementation "com.azure:azure-storage-blob"
    testImplementation "com.azure:azure-storage-queue"
    testImplementation "com.azure:azure-data-tables"
}
```

Testcontainers Azure module hiện được đánh dấu incubating. Nên pin BOM, Azure SDK version và image Azurite; khi nâng một trong các version này, chạy lại các test adapter liên quan.

### 3.3. Khởi chạy Azurite container

Với Testcontainers 2.x, class nằm trong package org.testcontainers.azure:

```java
import org.testcontainers.azure.AzuriteContainer;

AzuriteContainer azurite = new AzuriteContainer(
        "mcr.microsoft.com/azure-storage/azurite:3.37.0");

azurite.start();

try {
    String connectionString = azurite.getConnectionString();
    // Tạo Azure SDK client và chạy test.
} finally {
    azurite.stop();
}
```

Trong JUnit 5, có thể để extension quản lý lifecycle:

```java
import org.junit.jupiter.api.Test;
import org.testcontainers.azure.AzuriteContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.assertj.core.api.Assertions.assertThat;

@Testcontainers
class AzuriteSmokeIT {

    @Container
    static final AzuriteContainer azurite =
            new AzuriteContainer(
                    "mcr.microsoft.com/azure-storage/azurite:3.37.0");

    @Test
    void containerExposesStorageConnectionString() {
        assertThat(azurite.isRunning()).isTrue();
        assertThat(azurite.getConnectionString())
                .contains("BlobEndpoint=http://")
                .contains("QueueEndpoint=http://")
                .contains("TableEndpoint=http://");
    }
}
```

Container static được chia sẻ trong phạm vi test class và dừng khi class kết thúc. Dùng tên container, queue và table riêng cho từng test để tránh các method ghi đè dữ liệu của nhau.

Không hard-code host port trong test. Testcontainers ánh xạ cổng container ra host; getConnectionString() tạo connection string phù hợp với endpoint mà test JVM có thể truy cập.

## 4. Endpoint và connection string

### 4.1. Ba cổng mặc định

Azurite dùng các cổng nội bộ mặc định:

| Storage service | Cổng trong container |
| --- | ---: |
| Blob | 10000 |
| Queue | 10001 |
| Table | 10002 |

Khi chạy Docker trực tiếp, các cổng này thường được publish ra host. Với Testcontainers, cổng host có thể là cổng ngẫu nhiên. Hãy dùng connection string do container cung cấp thay vì tự nối localhost:10000.

Ví dụ dạng connection string mặc định:

```text
DefaultEndpointsProtocol=http;
AccountName=devstoreaccount1;
AccountKey=<Azurite-development-key>;
BlobEndpoint=http://127.0.0.1:10000/devstoreaccount1;
QueueEndpoint=http://127.0.0.1:10001/devstoreaccount1;
TableEndpoint=http://127.0.0.1:10002/devstoreaccount1;
```

Đây là credential phát triển công khai của emulator, không phải secret của Azure Storage account. Không dùng nó để kết nối production và không nhầm nó với credential cloud thật.

### 4.2. Endpoint local khác endpoint Azure thật

Một Azure Storage account thật thường dùng hostname có account name:

```text
https://<account-name>.blob.core.windows.net/<container>/<blob>
```

Azurite thường dùng URL path-style trên local:

```text
http://<host>:<mapped-port>/<account-name>/<container>/<blob>
```

Vì vậy, không nên ghép thủ công URL Azure production rồi thay domain bằng localhost. Dùng getConnectionString() hoặc endpoint mà AzuriteContainer cung cấp để SDK nhận đúng account, service port và path.

Nếu tự cấu hình endpoint cho nhiều service, giữ đúng endpoint riêng cho Blob, Queue và Table. Chỉ expose Blob port không làm Queue hoặc Table endpoint tự hoạt động.

### 4.3. Test JVM và application container dùng endpoint khác nhau

Khi JVM test chạy trên host, dùng azurite.getConnectionString() là lựa chọn đơn giản nhất.

Nếu ứng dụng cũng chạy trong một Docker container trên cùng network với Azurite, endpoint 127.0.0.1 hoặc host-mapped port có thể không truy cập được từ application container. Khi đó:

1. Đặt Azurite và application container vào cùng Docker network.
2. Gán network alias, ví dụ azurite.
3. Cấu hình endpoint bằng hostname azurite và port nội bộ 10000/10001/10002.
4. Dùng account/key của test tương ứng với endpoint đó.

Không dùng localhost từ application container để gọi một container khác; localhost bên trong container là chính container đó.

## 5. Kiểm thử Blob Storage

Blob là service thường được dùng nhiều nhất trong ứng dụng lưu file. Với Azurite, có thể kiểm tra upload/download, container lifecycle, metadata, content type và một số thao tác Blob API.

### 5.1. Tạo Blob client bằng connection string

```java
import java.nio.charset.StandardCharsets;
import java.util.UUID;
import com.azure.storage.blob.BlobContainerClient;
import com.azure.storage.blob.BlobServiceClient;
import com.azure.storage.blob.BlobServiceClientBuilder;

BlobServiceClient serviceClient =
        new BlobServiceClientBuilder()
                .connectionString(azurite.getConnectionString())
                .buildClient();

String containerName = "it-" +
        UUID.randomUUID().toString().replace("-", "");

BlobContainerClient container =
        serviceClient.createBlobContainer(containerName);
```

Tên container phải tuân theo quy tắc tên của Azure Blob Storage. Dùng UUID giúp các test chạy song song không tranh chấp một container cố định.

### 5.2. Upload, download và xác minh nội dung

```java
import java.nio.charset.StandardCharsets;
import java.util.UUID;
import com.azure.core.util.BinaryData;
import com.azure.storage.blob.BlobClient;
import com.azure.storage.blob.BlobContainerClient;
import com.azure.storage.blob.BlobServiceClient;
import com.azure.storage.blob.BlobServiceClientBuilder;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

@Test
void uploadsAndDownloadsBlob() {
    BlobServiceClient serviceClient =
            new BlobServiceClientBuilder()
                    .connectionString(azurite.getConnectionString())
                    .buildClient();

    String containerName = "it-" +
            UUID.randomUUID().toString().replace("-", "");

    BlobContainerClient container =
            serviceClient.createBlobContainer(containerName);

    try {
        BlobClient blob = container.getBlobClient("document.txt");
        String expected = "Spring Boot with Azure Storage";

        blob.upload(BinaryData.fromString(expected), true);

        String actual = new String(
                blob.downloadContent().toBytes(),
                StandardCharsets.UTF_8);

        assertThat(actual).isEqualTo(expected);
        assertThat(blob.exists()).isTrue();
    } finally {
        container.deleteIfExists();
    }
}
```

Test này xác minh Azure Blob SDK gửi request qua endpoint Azurite và có thể đọc lại nội dung đã ghi. Nó phù hợp để kiểm tra adapter mapping và basic storage flow.

### 5.3. Kiểm tra content type và metadata

Ứng dụng thường cần giữ content type, metadata hoặc HTTP headers để file được phục vụ đúng cách. Hãy kiểm tra chúng qua SDK:

```java
import java.util.Map;
import com.azure.core.util.BinaryData;
import com.azure.storage.blob.BlobClient;
import com.azure.storage.blob.models.BlobHttpHeaders;
import com.azure.storage.blob.models.BlobProperties;

BlobClient blob = container.getBlobClient("report.pdf");

blob.upload(BinaryData.fromBytes(pdfBytes), true);

blob.setHttpHeaders(
        new BlobHttpHeaders()
                .setContentType("application/pdf"));

blob.setMetadata(Map.of(
        "documentid", "doc-101",
        "source", "integration-test"));

BlobProperties properties = blob.getProperties();

assertThat(properties.getContentType())
        .isEqualTo("application/pdf");
assertThat(properties.getMetadata())
        .containsEntry("documentid", "doc-101");
```

Metadata key/value cần theo quy tắc của Azure Storage. Nên dùng key lowercase để tránh khác biệt khi SDK hoặc service chuẩn hóa header.

### 5.4. Những assertion hữu ích cho Blob adapter

| Hành vi | Assertion gợi ý |
| --- | --- |
| Tạo container | Container tồn tại sau khi create |
| Upload | Blob tồn tại và content đọc lại khớp |
| Overwrite | Nội dung mới được lưu theo overwrite policy của adapter |
| Content type | getProperties() trả đúng MIME type |
| Metadata | Metadata key/value được giữ |
| Download object thiếu | Adapter ánh xạ 404 thành kết quả hoặc exception theo port contract |
| Delete | Blob không còn tồn tại sau delete |
| ETag/conditional write | Request điều kiện được ánh xạ và response được xử lý đúng trong API được hỗ trợ |

Không cần kiểm tra mọi thao tác trong một test lớn. Tách từng behavior để khi Azurite hoặc SDK báo lỗi, nguyên nhân dễ xác định hơn.

## 6. Kiểm thử Queue Storage

Azure Queue Storage cung cấp queue đơn giản để lưu message. Azurite hỗ trợ một phần Queue Storage REST API như tạo queue, gửi/nhận/peek, cập nhật và xóa message.

Queue Storage không phải Azure Service Bus. Nó không cung cấp toàn bộ semantics của Service Bus như topic/subscription, session, dead-letter queue, transaction hoặc broker lock model. Nếu ứng dụng dùng các tính năng đó, hãy dùng Service Bus emulator riêng hoặc Azure test namespace.

### 6.1. Tạo queue và gửi/nhận message

```java
import java.nio.charset.StandardCharsets;
import java.util.UUID;
import com.azure.storage.queue.QueueClient;
import com.azure.storage.queue.QueueServiceClient;
import com.azure.storage.queue.QueueServiceClientBuilder;
import com.azure.storage.queue.models.QueueMessageItem;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

@Test
void sendsAndReceivesQueueMessage() {
    QueueServiceClient serviceClient =
            new QueueServiceClientBuilder()
                    .connectionString(azurite.getConnectionString())
                    .buildClient();

    String queueName = "it-" +
            UUID.randomUUID().toString().replace("-", "");

    QueueClient queue = serviceClient.createQueue(queueName);

    try {
        queue.sendMessage("document-uploaded");

        QueueMessageItem received = queue.receiveMessage();

        assertThat(received).isNotNull();
        assertThat(new String(
                received.getBody().toBytes(),
                StandardCharsets.UTF_8))
                .isEqualTo("document-uploaded");

        queue.deleteMessage(
                received.getMessageId(),
                received.getPopReceipt());
    } finally {
        queue.deleteIfExists();
    }
}
```

Queue message có visibility timeout và pop receipt. Khi test nhận message, hãy dùng message ID cùng pop receipt hiện tại để xóa hoặc cập nhật message. Không giả định receive message đồng nghĩa message đã bị xóa.

### 6.2. Test các nhánh lỗi và message lifecycle

Nên kiểm tra:

- Queue chưa tồn tại.
- Queue được tạo hai lần theo create/create-if-not-exists policy.
- Message được gửi và nhận với body đúng.
- Message được peek mà không bị consume.
- Message được update với pop receipt hợp lệ.
- Message bị xóa sau khi nhận.
- Queue bị xóa khi test kết thúc.

Azurite giúp kiểm tra request/response của Queue Storage trong phạm vi API hỗ trợ. Nếu nghiệp vụ cần guarantee về ordering, duplicate detection, session, lock renewal hoặc dead-letter processing của Service Bus, không dùng Queue Storage emulator để suy ra kết quả.

## 7. Kiểm thử Table Storage

Azurite có Table Storage service, nhưng hỗ trợ Table hiện vẫn là preview. Chỉ dùng nó cho smoke test và các thao tác cơ bản đã xác minh trên image/version đang pin.

### 7.1. Tạo table và ghi entity

```java
import java.util.UUID;
import com.azure.data.tables.TableClient;
import com.azure.data.tables.TableServiceClient;
import com.azure.data.tables.TableServiceClientBuilder;
import com.azure.data.tables.models.TableEntity;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

@Test
void createsTableAndStoresEntity() {
    TableServiceClient serviceClient =
            new TableServiceClientBuilder()
                    .connectionString(azurite.getConnectionString())
                    .buildClient();

    String tableName = "It" +
            UUID.randomUUID().toString().replace("-", "");

    TableClient table = serviceClient.createTable(tableName);

    try {
        TableEntity entity = new TableEntity(
                "documents",
                "doc-101")
                .addProperty("status", "READY");

        table.createEntity(entity);

        TableEntity loaded =
                table.getEntity("documents", "doc-101");

        assertThat(loaded.getProperties())
                .containsEntry("status", "READY");
    } finally {
        serviceClient.deleteTable(tableName);
    }
}
```

Table name và key phải tuân theo quy tắc của Azure Table Storage. Partition key và row key cùng xác định entity; nên dùng chúng để tạo ID ổn định trong test.

### 7.2. Giới hạn của Table preview

Không coi một test Table chạy thành công trên Azurite là bằng chứng mọi Table Storage API được hỗ trợ. Một số thao tác service properties, ACL, batch transaction hoặc truy vấn phức tạp có thể chưa có hoặc khác cloud. Kiểm tra support matrix của đúng phiên bản Azurite trước khi dựa vào một API cụ thể.

Với luồng quan trọng, chạy contract test trên Azure Storage account test thật. Nếu ứng dụng phụ thuộc Table API chưa được emulator hỗ trợ, dùng fake cho logic repository độc lập và cloud test cho adapter.

## 8. Tích hợp Azurite với Spring Boot

### 8.1. Truyền connection string qua DynamicPropertySource

Nếu application có một property riêng cho connection string, test có thể đăng ký giá trị động:

```java
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.boot.test.context.SpringBootTest;
import org.testcontainers.azure.AzuriteContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@SpringBootTest
@Testcontainers
class DocumentStorageIntegrationTest {

    @Container
    static final AzuriteContainer azurite =
            new AzuriteContainer(
                    "mcr.microsoft.com/azure-storage/azurite:3.37.0");

    @DynamicPropertySource
    static void storageProperties(
            DynamicPropertyRegistry registry) {

        registry.add(
                "app.azure.storage.connection-string",
                azurite::getConnectionString);
    }
}
```

app.azure.storage.connection-string là property do ứng dụng ví dụ định nghĩa. Bean configuration cần đọc property này để tạo Azure SDK client. Không giả định Spring Boot tự động chuyển mọi Azure SDK client sang Azurite chỉ vì có Testcontainers.

### 8.2. Tạo Blob client bean

```java
import com.azure.storage.blob.BlobServiceClient;
import com.azure.storage.blob.BlobServiceClientBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;

@Configuration(proxyBeanMethods = false)
class AzureStorageClientConfiguration {

    @Bean
    BlobServiceClient blobServiceClient(Environment environment) {
        String connectionString = environment.getRequiredProperty(
                "app.azure.storage.connection-string");

        return new BlobServiceClientBuilder()
                .connectionString(connectionString)
                .buildClient();
    }
}
```

Trong production, connection string hoặc credential được cấp từ cấu hình bảo mật phù hợp. Test profile có thể override property bằng connection string từ Azurite. Giữ cách tạo client trong configuration/adapter giúp test thay endpoint mà không sửa business logic.

### 8.3. Dùng Spring Cloud Azure service connection nếu version hỗ trợ

Một số version Spring Cloud Azure cung cấp connection details cho Azurite qua ServiceConnection. Cơ chế này thuộc tích hợp Spring Cloud Azure, không phải mặc định chung cho mọi Azure SDK client trong Spring Boot.

Nếu dùng cơ chế đó, kiểm tra tài liệu của đúng version Spring Cloud Azure và loại service connection được hỗ trợ. Nếu chưa có factory/connection details phù hợp, DynamicPropertySource là cách tường minh để truyền endpoint vào cấu hình client.

### 8.4. Cẩn thận với Spring context cache

JUnit Testcontainers extension có thể dừng container sau test class, trong khi Spring TestContext cache vẫn giữ ApplicationContext. Context được tái sử dụng có thể giữ BlobServiceClient trỏ tới endpoint container đã dừng.

Khi nhiều test class dùng chung Spring context, hãy cân nhắc quản lý Azurite container theo lifecycle của Spring context hoặc dùng cấu hình context nhất quán. Không chia sẻ context có bean phụ thuộc container đã bị dừng.

## 9. Cấu hình tài khoản và khóa test

### 9.1. Tài khoản mặc định

Azurite có tài khoản development mặc định và key công khai dành cho emulator. getConnectionString() của AzuriteContainer tạo connection string cho tài khoản mặc định.

Không dùng credential mặc định để truy cập Azure thật. Không đưa connection string của production vào test fixture.

### 9.2. Tạo tài khoản test riêng

Khi muốn kiểm tra cấu hình nhiều tài khoản/key, có thể truyền biến môi trường AZURITE_ACCOUNTS:

```java
AzuriteContainer azurite =
        new AzuriteContainer(
                "mcr.microsoft.com/azure-storage/azurite:3.37.0")
                .withEnv(
                        "AZURITE_ACCOUNTS",
                        "itaccount:test-key-one:test-key-two");

azurite.start();

String connectionString =
        azurite.getConnectionString(
                "itaccount",
                "test-key-one");
```

Có thể tạo nhiều account trong cùng container:

```text
AZURITE_ACCOUNTS=account1:key1:key2;account2:key3
```

Dùng key chỉ dành cho test và không tái sử dụng secret production. Test này giúp xác minh ứng dụng lấy đúng account/key và adapter không hard-code credential mặc định.

### 9.3. SAS và Shared Key

Azurite hỗ trợ Shared Key và các dạng SAS trong phạm vi hỗ trợ của emulator. Có thể dùng test để kiểm tra việc tạo client với SAS hoặc request bị từ chối khi chữ ký không hợp lệ.

Tuy nhiên, test SAS trên Azurite chỉ chứng minh behavior mà emulator triển khai. Không dùng nó làm bằng chứng rằng mọi policy, expiration, stored access policy hoặc authorization behavior trên Azure thật đã được xác minh.

## 10. OAuth và giới hạn kiểm thử danh tính

Azurite có thể bật OAuth basic khi cấu hình HTTPS và tùy chọn OAuth. Đây là một chế độ kiểm tra hạn chế, không phải bản mô phỏng đầy đủ của Microsoft Entra ID.

Ở mức OAuth basic, Azurite kiểm tra một số thuộc tính token như issuer, audience và expiry, nhưng không kiểm tra chữ ký token và quyền truy cập resource. Vì vậy:

- Không dùng OAuth basic để chứng minh token signature được xác minh như Azure thật.
- Không dùng nó để chứng minh RBAC role assignment hoặc data-plane permission.
- Không suy ra Managed Identity hoạt động chỉ vì client gọi Azurite thành công.
- Không dùng Azurite để kiểm tra token acquisition qua workload identity hoặc private endpoint production.

Nếu cần thử OAuth basic, phải bật HTTPS và cấu hình certificate cho emulator. Test đó chỉ kiểm tra nhánh token validation giới hạn mà Azurite hỗ trợ.

Đối với ứng dụng Spring Boot chạy trên Azure, hãy có cloud integration test dùng Managed Identity hoặc workload identity thực tế với role tối thiểu. Kiểm tra quyền đọc/ghi/xóa đúng resource và có negative test cho thao tác không được cấp.

## 11. Giới hạn kỹ thuật quan trọng của Azurite

### 11.1. Chỉ ba Storage service

Azurite hỗ trợ Blob, Queue và Table. Nó không hỗ trợ Azure Files hoặc Azure Data Lake Storage Gen2. Nếu ứng dụng dùng file share, hierarchical namespace, directory ACL hoặc Data Lake API, cần môi trường Azure thật hoặc một test double dành cho domain logic.

### 11.2. Table Storage đang preview

Table service của Azurite đang preview. Feature coverage có thể thiếu hoặc thay đổi. Tránh dùng emulator làm cổng kiểm thử duy nhất cho một hệ thống phụ thuộc Table API nâng cao.

### 11.3. API version không đồng nghĩa feature support

Azure SDK mới có thể gửi request với API version mà image Azurite hiện tại không chấp nhận. Testcontainers Azure module có withCommandOptions() để truyền cờ như --skipApiVersionCheck:

```java
AzuriteContainer azurite =
        new AzuriteContainer(
                "mcr.microsoft.com/azure-storage/azurite:3.37.0")
                .withCommandOptions("--skipApiVersionCheck");
```

Chỉ bật cờ này khi đã xác định request API version bị từ chối dù operation được emulator hỗ trợ. Bỏ qua kiểm tra version không bổ sung API còn thiếu, không biến emulator thành Azure Storage thật và có thể che khác biệt compatibility. Ưu tiên pin Azure SDK và Azurite image version tương thích.

### 11.4. Endpoint và URL khác cloud

Azurite dùng endpoint local, port local và thường dùng path-style URL. Azure thật dùng hostname theo account/service. Những test phụ thuộc DNS, private endpoint, firewall, VNet integration hoặc private DNS zone cần cloud environment.

### 11.5. Hiệu năng và scale

Azurite dành cho development/test và không đưa ra bảo đảm hiệu năng như Azure Storage. Không dùng kết quả benchmark trên Azurite để ước lượng throughput, latency, concurrency hoặc scale của production.

### 11.6. Error behavior có khác biệt

Azurite cố gắng tương thích logic xử lý lỗi của Azure Storage, nhưng message lỗi có thể khác. HTTP status code có thể tương đồng trong một số trường hợp, song test không nên phụ thuộc exact error text. Assert theo status, error code hoặc exception contract ổn định mà adapter cam kết.

### 11.7. Replication, durability và data lifecycle

Azurite có thể mô phỏng một số thao tác storage nhưng không thay thế kiểm thử durability, geo-replication, failover, lifecycle policy, soft delete, versioning và backup/restore trên Azure thật. Chỉ kiểm tra feature nếu support matrix của phiên bản emulator xác nhận có hỗ trợ.

### 11.8. Authentication và authorization

Shared Key/SAS local hữu ích để kiểm tra cấu hình SDK. OAuth basic có giới hạn như phần trên. RBAC, role propagation, Managed Identity, resource scope, storage firewall và private endpoint cần test trên Azure thật.

## 12. Azurite không thay thế emulator của Service Bus, Event Hubs và Cosmos DB

Một số Azure service có emulator riêng trong Testcontainers Azure module:

| Dịch vụ | Container riêng | Dependency/điểm cần lưu ý |
| --- | --- | --- |
| Service Bus | ServiceBusEmulatorContainer | Cần SQL Server, cấu hình entity và Docker network chung |
| Event Hubs | EventHubsEmulatorContainer | Cần cấu hình namespace/entity; có thể cần Azurite làm dependency theo emulator version |
| Cosmos DB | CosmosDBEmulatorContainer | Cần xử lý certificate/truststore khi client dùng HTTPS |
| Storage | AzuriteContainer | Blob/Queue/Table; không thay thế các broker hoặc database trên |

Không cài đặt các service này bằng cách bật thêm port trong Azurite. Mỗi emulator có image, protocol, configuration và giới hạn riêng.

### 12.1. Queue Storage khác Service Bus

| Tiêu chí | Azure Queue Storage | Azure Service Bus |
| --- | --- | --- |
| Mô hình | Queue đơn giản thuộc Storage account | Messaging broker |
| Topic/subscription | Không | Có |
| Session | Không có semantics Service Bus session | Có |
| Dead-letter queue | Không có DLQ broker như Service Bus | Có |
| Lock/settlement | Visibility timeout và pop receipt | Peek-lock, complete, abandon, dead-letter |
| Emulator | Azurite | Service Bus emulator riêng |

Nếu ứng dụng dùng QueueClient thì Azurite là lựa chọn phù hợp cho API Queue Storage. Nếu ứng dụng dùng ServiceBusClientBuilder, hãy test với Service Bus emulator hoặc Azure test namespace.

### 12.2. Khi cần emulator khác hoặc Azure thật?

- Dùng Service Bus emulator để test sender/processor và queue/topic flow cơ bản.
- Dùng Event Hubs emulator để test producer/consumer flow và partition configuration trong phạm vi hỗ trợ.
- Dùng Cosmos DB emulator để test document database client/API và SSL trust setup.
- Dùng Azure thật để kiểm tra Entra ID, RBAC, Managed Identity, private network, quota, tier và behavior chưa được emulator hỗ trợ.
- Dùng fake/test double để test domain logic không phụ thuộc Azure SDK.

## 13. Ma trận kiểm thử Azurite và Azure thật

| Rủi ro/hành vi | Azurite | Azure test account |
| --- | --- | --- |
| Blob upload/download | Có, trong API hỗ trợ | Có |
| Container create/delete | Có | Có |
| Metadata/content type | Có | Có |
| Queue send/receive | Có, trong API hỗ trợ | Có |
| Table CRUD cơ bản | Có, preview | Có |
| Azure Files | Không | Có |
| Data Lake Gen2 | Không | Có |
| API version compatibility | Có thể kiểm tra theo image/SDK | Có |
| Shared Key/SAS cơ bản | Có trong phạm vi hỗ trợ | Có |
| Entra ID token signature/authorization đầy đủ | Không | Có |
| RBAC role assignment | Không | Có |
| Managed Identity | Không | Có |
| Private endpoint/DNS/VNet | Không | Có |
| Quota/throttling/scale production | Không đại diện | Có |
| Replication/failover production | Không đại diện đầy đủ | Có |
| Azure Storage lifecycle/retention | Chỉ feature được hỗ trợ | Có |

Một pipeline cân bằng có thể chạy Azurite integration test trên pull request, sau đó chạy cloud integration test theo lịch, trước release hoặc khi thay đổi identity/network/storage policy.

## 14. Tổ chức test data và cleanup

### 14.1. Tên resource riêng cho từng test

Dùng prefix it- cộng UUID cho container/queue/table. Với blob, dùng key chứa test run ID hoặc test method ID. Điều này giảm va chạm khi chạy song song.

### 14.2. Cleanup resource

- Xóa blob container sau khi test hoàn tất.
- Xóa queue/table do test tạo.
- Dùng try/finally hoặc fixture cleanup để chạy cả khi assertion thất bại.
- Nếu test dùng một Azurite container cho cả class, bảo đảm mỗi test dùng resource riêng.
- Không bật persistence volume dùng chung trong CI trừ khi test đang kiểm tra persistence.

Azurite lưu dữ liệu trong workspace directory của emulator. Container được tạo mới không gắn volume sẽ không giữ dữ liệu của container test cũ. Nếu gắn volume để debug, cần reset workspace để state cũ không ảnh hưởng lần chạy tiếp theo.

### 14.3. Không để test phụ thuộc thứ tự

Một test không nên cần test trước tạo container hoặc queue. Mỗi test phải tự tạo dữ liệu cần thiết và cleanup resource của chính nó. Nếu có test song song, không dùng chung tên resource cố định.

## 15. Troubleshooting

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Connection refused | Dùng sai host/port hoặc container chưa ready | Dùng getConnectionString() và wait strategy phù hợp |
| SDK gọi sai endpoint | Tự ghép URL hoặc dùng endpoint cloud production | Dùng connection string từ AzuriteContainer |
| Blob client hoạt động nhưng Queue client lỗi | Chỉ expose/start Blob service hoặc cấu hình thiếu Queue endpoint | Kiểm tra connection string và Queue service port |
| API version rejected | SDK gửi version Azurite chưa hỗ trợ | Pin version tương thích; chỉ cân nhắc --skipApiVersionCheck khi operation đã được hỗ trợ |
| Operation trả unsupported | Emulator chưa triển khai API/feature đó | Kiểm tra support matrix; chuyển sang Azure test thật |
| Table test flaky | Table API preview hoặc feature chưa hỗ trợ ổn định | Giữ test ở mức smoke/basic và test cloud cho behavior quan trọng |
| Client dùng account/key sai | Custom account không khớp connection string | Dùng getConnectionString(account, key) và kiểm tra AZURITE_ACCOUNTS |
| App container không truy cập được Azurite | Dùng localhost/mapped host port từ container khác | Dùng Docker network alias và port nội bộ |
| OAuth test không giống Azure | OAuth basic không xác minh signature/permission đầy đủ | Dùng cloud test với Entra ID/RBAC |
| Test pass local nhưng fail CI | Docker network, mapped host, image pull hoặc shared data khác nhau | Pin image, lấy endpoint động, cô lập resource và lưu container logs |
| Dữ liệu cũ còn xuất hiện | Workspace volume được giữ giữa các lần chạy | Xóa/reset workspace hoặc dùng container mới không gắn volume |

Khi lỗi xuất hiện, ghi lại Azure SDK version, Azurite image tag, API version request, service endpoint và status/error code. Không ghi connection string hoặc account key vào log CI.

## 16. Bài thực hành: kiểm thử Document Storage bằng Azurite

**Bối cảnh:** Document Service dùng Spring Boot và Azure Blob Storage để lưu file PDF. Service lưu metadata vào database và phát event sau khi upload thành công. Hãy kiểm tra storage adapter với Azurite và xác định những assertion cần Azure thật.

### Phần A — Thiết lập Azurite

- Thêm Testcontainers Azure module và Azure Blob SDK.
- Tạo AzuriteContainer với image version được pin.
- Dùng @Testcontainers và @Container để quản lý lifecycle.
- Lấy connection string qua getConnectionString().
- Tạo một test smoke xác minh Blob endpoint có thể truy cập.

### Phần B — Blob adapter

- Tạo container riêng theo test ID.
- Upload file PDF với content type application/pdf.
- Đọc lại nội dung và metadata.
- Test overwrite, delete và object không tồn tại.
- Kiểm tra adapter ánh xạ lỗi storage thành exception của application port.

### Phần C — Spring Boot wiring

- Đăng ký app.azure.storage.connection-string qua @DynamicPropertySource.
- Tạo BlobServiceClient bean từ property đó.
- Inject storage adapter vào use case.
- Xác minh use case lưu object và trả metadata đúng.
- Không đưa Azure production connection string vào test config.

### Phần D — Queue/Table nếu ứng dụng sử dụng

- Dùng Queue Storage SDK và tạo queue có tên riêng.
- Gửi/nhận message và xóa message bằng pop receipt.
- Nếu dùng Table, viết smoke test CRUD cơ bản và ghi rõ API preview.
- Không dùng Queue Storage test để kết luận Service Bus session/DLQ/transaction đúng.

### Phần E — Kiểm thử cloud thật

- Dùng workload identity hoặc Managed Identity trong Azure test environment.
- Cấp RBAC tối thiểu cho đúng storage account/container.
- Test positive permission và negative permission.
- Nếu production dùng private endpoint, chạy test từ network path tương ứng.
- Xác minh quota, encryption, lifecycle, replication hoặc Data Lake/Files nếu ứng dụng phụ thuộc.

**Tiêu chí hoàn thành:** người học khởi chạy Azurite bằng Testcontainers, cấu hình Azure SDK từ connection string động, viết được Blob integration test, hiểu Queue Storage và Table Storage ở phạm vi emulator, và chỉ ra được các behavior cần Azure thật xác minh.

---

## 17. Checklist trước khi merge/release

| Nhóm | Câu hỏi |
| --- | --- |
| Dependency | Testcontainers Azure module và Azure SDK version đã pin chưa? |
| Emulator | Image Azurite tag đã pin và tương thích API version SDK chưa? |
| Lifecycle | Container có được start/stop tự động không? |
| Endpoint | Test dùng connection string động từ getConnectionString() chưa? |
| Blob | Có test upload/download, content type, metadata và delete không? |
| Queue | Có phân biệt Queue Storage với Service Bus không? |
| Table | Test có ghi rõ Table Storage preview và giới hạn feature không? |
| Account | Có dùng account/key test, không tái sử dụng production credential không? |
| OAuth | Có tránh xem OAuth basic như RBAC/Entra authorization đầy đủ không? |
| API version | Có dùng --skipApiVersionCheck một cách có chủ đích không? |
| Data isolation | Container/queue/table/blob name có unique theo test không? |
| Cleanup | Resource và workspace có cleanup/reset path không? |
| Networking | App container có dùng network alias thay cho localhost không? |
| Cloud gap | Có cloud test cho RBAC, Managed Identity, private endpoint và feature không được emulator hỗ trợ không? |
| CI | Runner có Docker-compatible runtime và quyền pull image không? |
| Diagnostics | Log có service name, SDK version, image tag và error code nhưng không chứa secret không? |

## Ghi nhớ

- Azurite là emulator cho Azure Storage, hiện hỗ trợ Blob, Queue và Table; Table đang preview.
- Azurite không hỗ trợ Azure Files hoặc Data Lake Storage Gen2.
- Queue Storage không phải Service Bus; Event Hubs, Service Bus và Cosmos DB có emulator riêng.
- Dùng Testcontainers AzuriteContainer và getConnectionString() để endpoint được ánh xạ đúng trên host.
- Với Spring Boot, có thể đưa connection string động qua DynamicPropertySource và tạo Azure SDK client trong configuration.
- withCommandOptions("--skipApiVersionCheck") chỉ bỏ qua kiểm tra API version; nó không bổ sung API mà emulator chưa hỗ trợ.
- OAuth basic có giới hạn và không chứng minh token signature hoặc RBAC permission đúng như Azure thật.
- Dùng Azure test account cho Entra ID, RBAC, Managed Identity, private endpoint, quota, replication và feature đặc thù cloud.
- Pin image/SDK, cô lập resource theo test, cleanup sau mỗi test và tránh ghi credential vào log.

Azurite giúp kiểm tra nhanh adapter và Storage API của ứng dụng Spring Boot mà không cần Azure subscription cho mỗi lần chạy. Giá trị của test nằm ở việc xác minh đúng API trong phạm vi emulator hỗ trợ và nhận diện rõ phần nào cần môi trường Azure thật. Khi tách bạch Blob/Queue/Table với Service Bus, Event Hubs, Cosmos DB và các dịch vụ identity, integration suite sẽ phản ánh đúng ranh giới của từng provider service.

### Tài liệu chính thức

- [Microsoft Learn — Use the Azurite emulator for local Azure Storage development](https://learn.microsoft.com/en-us/azure/storage/common/storage-use-azurite)
- [Microsoft Learn — Install and run Azurite emulator](https://learn.microsoft.com/en-us/azure/storage/common/storage-install-azurite)
- [Microsoft Learn — Connect to Azurite with SDKs and tools](https://learn.microsoft.com/en-us/azure/storage/common/storage-connect-azurite)
- [Microsoft Learn — Run automated tests by using Azurite](https://learn.microsoft.com/en-us/azure/storage/blobs/use-azurite-to-run-automated-tests)
- [Microsoft Learn — Azure Blob Storage client library for Java](https://learn.microsoft.com/en-us/java/api/overview/azure/storage-blob-readme?view=azure-java-stable)
- [Microsoft Learn — Azure Queue Storage client library for Java](https://learn.microsoft.com/en-us/java/api/overview/azure/storage-queue-readme?view=azure-java-stable)
- [Microsoft Learn — Azure Tables client library for Java](https://learn.microsoft.com/en-us/java/api/overview/azure/data-tables-readme?view=azure-java-stable)
- [Testcontainers for Java — Azure module](https://java.testcontainers.org/modules/azure/)
- [Azure/Azurite — Supported APIs, OAuth and limitations](https://github.com/Azure/Azurite)
- [Microsoft Learn — Spring Cloud Azure support for Testcontainers](https://learn.microsoft.com/en-us/azure/developer/java/spring-framework/testcontainers-support)

Trước khi nâng Azure SDK hoặc Azurite, kiểm tra API version mà SDK gửi và support matrix của image đang pin. Tài liệu Azurite, Azure SDK và Testcontainers module có thể cập nhật ở thời điểm khác nhau; chỉ bật compatibility flag khi đã hiểu chính xác lỗi cần xử lý.
