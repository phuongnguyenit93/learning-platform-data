# Kiểm thử tích hợp SDK bằng emulator và tài nguyên thử nghiệm

Trong module **CLOUD_PROVIDERS_AZURE**, chúng ta khám phá hệ sinh thái Microsoft Azure từ subscription, resource group, Microsoft Entra ID đến mạng ảo, dịch vụ tính toán, lưu trữ và dữ liệu. Mục tiêu là biết triển khai, giám sát, bảo vệ và kiểm soát chi phí một kiến trúc ứng dụng trên Azure. Trong chương **Azure SDK cho Java**, bài học này trình bày cách **kiểm thử tích hợp (integration testing)** những ứng dụng Java sử dụng Azure SDK bằng **emulator cục bộ** và **tài nguyên Azure thử nghiệm có kiểm soát**.

Hãy xét một dịch vụ `order-ingestion` viết bằng Java 17/Spring Boot: khi nhận đơn hàng, ứng dụng upload chứng từ lên Azure Blob Storage, gửi công việc vào Azure Queue Storage, sau đó một worker đọc hàng đợi và ghi trạng thái. Unit test có thể mock `BlobClient` và `QueueClient` để kiểm tra business logic; tuy nhiên mock không chứng minh SDK thực sự **serialize request, ký xác thực, tạo blob, đọc metadata hay xử lý lỗi HTTP** đúng cách. Test trực tiếp trên storage account production lại nguy hiểm và tốn thời gian. Vì thế cần nhiều tầng kiểm thử với **phạm vi bảo đảm khác nhau**.

Sau bài học, bạn có thể:

- Phân biệt **unit test, contract test, emulator integration test, cloud integration test và end-to-end smoke test**.
- Chọn emulator thích hợp: **Azurite** cho Azure Storage Blob/Queue/Table; cân nhắc **Cosmos DB Emulator**, **Event Hubs Emulator** hoặc **Service Bus Emulator** khi chúng hỗ trợ đúng tính năng cần thử.
- Tạo Blob Storage client bằng Azure SDK for Java, viết **JUnit 5 integration test** thực sự đọc/ghi với Azurite, và dùng **Testcontainers** để cấp container test độc lập.
- Cấu hình client qua environment/endpoint/credential thay vì hard-code production connection string.
- Provision tài nguyên Azure thật riêng cho test, sử dụng **DefaultAzureCredential/managed identity, Microsoft Entra ID và Azure RBAC** đúng data plane.
- Thiết kế fixture, isolation, idempotent cleanup, retry/polling có deadline, negative tests, CI/CD, budget và runbooks.
- Hiểu rõ giới hạn của emulator và những hành vi **bắt buộc xác minh trên dịch vụ Azure thật** trước khi phát hành.

## 1. “Integration test” của Azure SDK thực sự kiểm tra điều gì?

Một integration test có ý nghĩa phải đi qua **ít nhất một ranh giới tích hợp thật**: SDK serialization, HTTP/AMQP protocol, service endpoint, credential, storage semantics hoặc cơ chế retry. Nếu test chỉ trả về một mock response của `BlobClient`, đó chủ yếu là **unit test**, dù class đang được test mang tên `AzureStorageIntegrationService`.

```text
                         Source code Java
                               |
                     Business logic + adapters
                               |
          +--------------------+-------------------+
          |                    |                   |
          v                    v                   v
      Unit tests       Emulator integration   Real Azure integration
      Fake ports       Azure SDK -> Azurite   Azure SDK -> test resource
      Fast/offline      Protocol & basic I/O  IAM/network/quotas/service
          |                    |                   |
          +--------------------+-------------------+
                               |
                          Release gates
                               |
                      Production deployment
```

### 1.1. Những lớp lỗi khác nhau

| Loại lỗi | Mock/unit | Emulator | Tài nguyên Azure thật |
|---|---|---|---|
| Mapping business DTO, validation | Rất phù hợp | Có thể | Có thể nhưng thường tốn hơn |
| Tạo SDK request/response, đọc Blob content | Không bảo đảm | Tốt nếu feature có hỗ trợ | Có |
| Azure identity, token audience, RBAC | Giả lập được logic, không xác minh Azure | Thường **không** | **Bắt buộc** |
| Private Endpoint, DNS, TLS CA/hostname | Không | Emulator local không tương đương | **Bắt buộc** |
| Quota, throttling, scale limits | Có thể inject lỗi giả | Chỉ một phần | **Bắt buộc đánh giá** |
| Geo-replication, availability zone, failover | Không thực | Không đầy đủ | Chỉ test trên môi trường/quy trình cho phép |
| Eventual consistency, concurrency thật | Chỉ một phần | Tùy emulator | Có |
| API/features mới của Azure service | Không | Có thể chưa hỗ trợ | Xác minh tại tier/region thực tế |

**Không có “một test xanh” bao trùm mọi rủi ro.** Emulator giúp chạy nhanh, lặp lại được; test resource trên Azure giúp phát hiện khoảng cách do tính năng cloud, quyền, hạ tầng, cấu hình và hợp đồng dịch vụ.

### 1.2. Kiểm thử ứng dụng, không chỉ “ping Azure”

Một test upload Blob đúng cần kiểm tra **cả dữ liệu đọc lại**, metadata, key/path, exception khi không tồn tại, và dọn dẹp. Chỉ kiểm tra HTTP 201 hoặc lời gọi mock `upload()` chưa đủ. Với Queue, kiểm tra message có thể đọc, xử lý, xóa hoặc trở lại visible theo semantics; không suy từ `sendMessage()` thành exactly-once business processing.

## 2. Tháp kiểm thử thực dụng cho Azure SDK Java

| Tầng | Nơi chạy | Mục tiêu | Tần suất gợi ý |
|---|---|---|---|
| **Unit/contract test** | JVM với fake/mock | Business rules, mapping, validation, retry classifier | Mỗi commit/PR |
| **Emulator integration** | Docker/Testcontainers cục bộ | HTTP/serialization/data operations, cơ bản về lỗi | Mỗi PR nếu container sẵn |
| **Cloud integration** | Subscription/resource group test | Identity, RBAC, endpoint, TLS, real API/feature behavior | Nightly, trước release hoặc PR quan trọng |
| **End-to-end smoke** | Staging giống production | App→Azure dependency→worker→output, telemetry | Trước release/deploy |
| **Resilience/performance** | Dedicated environment | Throttling, failover, high concurrency, chi phí | Theo kế hoạch riêng, không mỗi PR |

### 2.1. Vì sao không chạy mọi test trên Azure thật?

Provision storage/database/messaging resources mỗi commit có thể tạo **chi phí, latency, quota contention, flaky network, dữ liệu sót** và rủi ro lộ secrets. Emulator nhanh hơn và không cần internet sau khi có image/dependencies. Nhưng chỉ chạy local sẽ bỏ sót các lỗi như **Managed Identity chưa được cấp data-plane role** hoặc firewall private endpoint sai.

### 2.2. Test quyết định đường đi của một lỗi

Ví dụ service bị lỗi `403 AuthorizationPermissionMismatch`:

- Unit test kiểm tra application đổi lỗi thành exception/reporting phù hợp.
- Azurite test kiểm tra Shared Key connection string local và Blob operations; **không** xác minh Entra RBAC.
- Azure real test đăng nhập bằng identity dự kiến, kiểm tra role scope và token, thực hiện đọc/ghi Blob.
- Staging smoke xác minh workload chạy trên AKS/App Service có kết nối qua mạng và chính sách production-like.

### 2.3. Test contract đối với Azure SDK version

SDK là dependency có thể thay đổi HTTP API version, response parsing và retry implementation. Cần **pin/lock version** qua Maven BOM và CI, kiểm tra release notes khi nâng. Unit test trên fake chỉ bảo đảm code business; emulator và cloud test phát hiện incompatibility khi nâng SDK hoặc đổi API behavior.

## 3. Bản đồ emulator và giới hạn cần biết

Không có một “Azure emulator” mô phỏng đầy đủ tất cả Azure services. Mỗi emulator là sản phẩm/tiện ích riêng, có phạm vi và phiên bản.

| Dịch vụ Azure | Công cụ local | Có thể kiểm tra | Giới hạn quan trọng |
|---|---|---|---|
| **Blob/Queue/Table Storage** | **Azurite** | CRUD, HTTP request/response, basic authentication/emulated storage semantics | Không đầy đủ mọi feature/API version, Entra RBAC, replication, lifecycle, network/cloud quotas |
| **Azure Cosmos DB for NoSQL** | Cosmos DB Emulator (bản/OS/container được hỗ trợ) | Document CRUD, query, partition-key behavior cơ bản | Khác cloud về throughput, consistency, multi-region, feature parity, chứng chỉ |
| **Azure Event Hubs** | Event Hubs Emulator khi có bản phù hợp | Publish/consume, consumer group, protocol basics | Giới hạn namespace/tính năng, throughput/quota, capture và cloud IAM |
| **Azure Service Bus** | Service Bus Emulator khi có bản phù hợp | Một số queue/topic và AMQP message workflows | Không thay thế đầy đủ SKU features, HA, networking/RBAC, quota, scheduled/advanced features theo bản |
| **Azure Functions local** | Azure Functions Core Tools + emulator hỗ trợ trigger/binding | Chạy function code, test một số bindings với Azurite | Không mô phỏng đầy đủ hosting/scale/identity/network |
| **Azure SQL Database** | SQL Server/container hoặc test database riêng | SQL schema/query và JDBC cơ bản | Azure-specific behavior, geo-HA, Entra/network và service limits không giống |
| **Key Vault, Entra ID, Private Link, Azure RBAC** | Fake/local contract tests, hoặc real Azure test resources | Test application logic qua abstraction | Không có emulator thay thế đầy đủ xác thực/quyền và network Azure |

**Phải xác minh trạng thái hỗ trợ và feature matrix của đúng phiên bản emulator** trước khi chọn test; không giả định tên “Emulator” đồng nghĩa tương thích 100% với managed service. Có trường hợp Azure SDK mới sử dụng service API chưa được emulator phát hành hỗ trợ.

### 3.1. Vì sao Azurite là điểm khởi đầu?

Azurite dễ dùng để tạo Blob/Queue/Table với endpoint local và một development account. Nó rất phù hợp để học cách xây dựng **test thực sự qua Azure Storage SDK**. Tuy nhiên Azurite không kiểm tra được **managed identity, Azure RBAC, private endpoint, Azure Storage redundancy, Azure Monitor hay production-level throttling**.

### 3.2. Cosmos DB Emulator khác một mock repository

Cosmos emulator có thể kiểm tra một phần **SQL API for NoSQL, partition key, request serialization và query logic**. Nó **không** bảo đảm cùng RU charge, indexing cost, distributed replication, consistency level hoặc regional failover với Azure Cosmos DB thật. Với chi phí/hiệu năng, vẫn cần cloud test có RU/latency metrics.

### 3.3. Messaging emulator và vận chuyển thông điệp

Event Hubs và Service Bus là hai sản phẩm khác nhau. **Event Hubs** tối ưu event streaming/partitions/consumer offsets; **Service Bus** tối ưu enterprise messaging queues/topics, locks, settlement, DLQ và các workflows khác. Không dùng emulator của dịch vụ này để chứng minh semantics của dịch vụ kia. Kiểm tra compose/config/support matrix cho version trước khi tích hợp vào Testcontainers.

### 3.4. Tính năng không có emulator thì sao?

Tạo **contract tests** bằng fake cho application behavior, sau đó có **cloud integration test** nhỏ nhất cần thiết trên tài nguyên có quyền, cost cap và cleanup. Không bịa một emulator Key Vault/RBAC “đủ tương đương” để bỏ qua cloud test.

## 4. Thiết kế Java dễ kiểm thử bằng dependency injection

Một anti-pattern:

```java
public final class OrderService {
    public void save(String orderId, byte[] bytes) {
        // Sai: tạo client và nhúng storage credential trong business method.
        String connectionString = "AccountKey=<production-secret>";
        // new BlobServiceClientBuilder().connectionString(...).buildClient();
        // ...
    }
}
```

Nó khó unit test, rò rỉ credentials, dễ kết nối nhầm production và tạo client liên tục. Nên tách **port (business contract)** và **Azure SDK adapter**.

### 4.1. Business port

```java
public interface DocumentStore {
    void put(String key, byte[] content);
    byte[] get(String key);
    boolean exists(String key);
    void delete(String key);
}
```

`DocumentStore` là interface do ứng dụng **tự định nghĩa**, không phải API có sẵn của Azure Storage SDK. Unit test dùng in-memory fake; integration test dùng `AzureBlobDocumentStore` thực sự.

### 4.2. Adapter dùng Azure SDK

```java
import com.azure.core.util.BinaryData;
import com.azure.storage.blob.BlobContainerClient;
import com.azure.storage.blob.BlobClient;

public final class AzureBlobDocumentStore implements DocumentStore {
    private final BlobContainerClient container;

    public AzureBlobDocumentStore(BlobContainerClient container) {
        this.container = container;
    }

    @Override
    public void put(String key, byte[] content) {
        BlobClient blob = container.getBlobClient(key);
        blob.upload(BinaryData.fromBytes(content), true);
    }

    @Override
    public byte[] get(String key) {
        return container.getBlobClient(key)
                .downloadContent()
                .toBytes();
    }

    @Override
    public boolean exists(String key) {
        return container.getBlobClient(key).exists();
    }

    @Override
    public void delete(String key) {
        container.getBlobClient(key).deleteIfExists();
    }
}
```

Adapter này cố ý ngắn: production cần **timeout/retry policy, metadata, content type, validation key, logging, authorization, overwrite semantics và cancellation**. Nhưng sự tách biệt giúp một test dùng cùng business code với cả emulator và Azure thật.

### 4.3. Inject clock/ID generator

Test retries, token expiration, SAS expiry hoặc TTL không nên `Thread.sleep(60_000)`. Dùng `java.time.Clock`, injectable ID generator và fake scheduler cho unit tests. Với service thật, không thể giả lập **toàn bộ server-side thời gian** bằng Clock Java, nên có một số integration tests theo time budget thực tế.

### 4.4. Test không dựa vào một global connection string

Thay vì class service gọi `System.getenv("AZURE_STORAGE_CONNECTION_STRING")` ở mọi method, tạo client **một lần tại composition root** dựa trên `test profile/emulator profile/staging profile`. Bảo đảm emulator profile không bao giờ vô tình lấy production secret do environment variable trùng tên.

## 5. Chuẩn bị Java, Maven và test libraries

Ví dụ dùng **Java 17+**, Maven, **Azure Storage Blob SDK**, **Azure Identity**, JUnit Jupiter và Testcontainers. Chọn phiên bản tương thích, đã được xác minh theo JDK/CI runner; không trộn tùy tiện các phiên bản `azure-core` và SDK.

### 5.1. Các dependency cơ bản

```xml
<!-- POM fragment; khai báo version qua Azure SDK BOM được kiểm thử. -->
<dependencyManagement>
  <dependencies>
    <dependency>
      <groupId>com.azure</groupId>
      <artifactId>azure-sdk-bom</artifactId>
      <version>${azure.sdk.bom.version}</version>
      <type>pom</type>
      <scope>import</scope>
    </dependency>
    <dependency>
      <groupId>org.testcontainers</groupId>
      <artifactId>testcontainers-bom</artifactId>
      <version>${testcontainers.version}</version>
      <type>pom</type>
      <scope>import</scope>
    </dependency>
  </dependencies>
</dependencyManagement>

<dependencies>
  <dependency>
    <groupId>com.azure</groupId>
    <artifactId>azure-storage-blob</artifactId>
  </dependency>
  <dependency>
    <groupId>com.azure</groupId>
    <artifactId>azure-identity</artifactId>
  </dependency>
  <dependency>
    <groupId>org.junit.jupiter</groupId>
    <artifactId>junit-jupiter</artifactId>
    <version>${junit.jupiter.version}</version>
    <scope>test</scope>
  </dependency>
  <dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>junit-jupiter</artifactId>
    <scope>test</scope>
  </dependency>
</dependencies>
```

Các Maven properties `azure.sdk.bom.version`, `testcontainers.version` và `junit.jupiter.version` phải được định nghĩa bằng **phiên bản thực tế được kiểm thử** trong dự án. Đây là **fragment**, không phải POM hoàn chỉnh; cần cấu hình Maven compiler, Surefire/Failsafe và dependency lifecycle theo môi trường. Không suy một version cụ thể là mới nhất hoặc supported chỉ dựa trên bài học.

### 5.2. Quy ước chạy tests

Một convention:

- `*Test.java`: unit tests nhanh.
- `*IT.java`: integration tests trên emulator hoặc Azure.
- JUnit 5 `@Tag("emulator")` và `@Tag("azure")` để phân loại.
- Maven Surefire/Failsafe hoặc Gradle tasks tương ứng chọn đúng nhóm test.

Điều quan trọng là **CI chạy đúng nhóm**, không phải tên hậu tố. Cấu hình CI phải fail nếu một test quan trọng bị skip vì thiếu Docker/credential mà pipeline lại báo xanh.

### 5.3. Kiểm tra Docker

Azurite/Testcontainers cần môi trường chạy container phù hợp (Docker Engine, Podman với cấu hình được hỗ trợ hoặc runner tương đương). Testcontainers cần quyền truy cập daemon/runtime; trong CI không nên vô tình chạy privileged Docker với quyền quá rộng trên cùng runner chứa production secrets.

## 6. Azurite: chạy Azure Storage emulator cục bộ

Azurite cung cấp endpoint mặc định cho các storage services:

| Service | Endpoint local thông dụng | Mục đích |
|---|---|---|
| Blob | `http://127.0.0.1:10000/devstoreaccount1` | Object/file operations |
| Queue | `http://127.0.0.1:10001/devstoreaccount1` | Storage queue messages |
| Table | `http://127.0.0.1:10002/devstoreaccount1` | Table entities |

Đây là **địa chỉ/cổng mặc định** ở chế độ Azurite local. Khi chạy container/Testcontainers có port mapping động, **host/port có thể khác**. Không sử dụng HTTP emulator local như chuẩn production: Azure thật phải dùng TLS và authentication phù hợp.

### 6.1. Chạy bằng Docker

```bash
docker run --rm --name azurite-it \
  -p 127.0.0.1:10000:10000 \
  -p 127.0.0.1:10001:10001 \
  -p 127.0.0.1:10002:10002 \
  mcr.microsoft.com/azure-storage/azurite:latest
```

Ví dụ chỉ bind host loopback để không công khai emulator ra LAN. Trong hệ thống CI, **pin image tag/digest đã kiểm thử** thay vì luôn dùng `latest`; cấu hình volume/persistence nếu cần điều tra, nhưng trong test isolation thường ưu tiên dữ liệu tạm. Không expose Azurite account ra Internet; development account dùng **khóa public well-known**, không phải bí mật production.

### 6.2. Development storage account

Azurite thông thường sử dụng tài khoản phát triển `devstoreaccount1` và **khóa dev well-known** được tài liệu Azurite công bố. Một connection string cục bộ thường có dạng:

```text
DefaultEndpointsProtocol=http;
AccountName=devstoreaccount1;
AccountKey=<Azurite-development-account-key>;
BlobEndpoint=http://127.0.0.1:10000/devstoreaccount1;
QueueEndpoint=http://127.0.0.1:10001/devstoreaccount1;
TableEndpoint=http://127.0.0.1:10002/devstoreaccount1;
```

**Đây là cấu trúc nhiều dòng để dễ đọc**; khi dùng trong environment variable phải là **một chuỗi liền**, bỏ line breaks. Lấy key dev chính xác từ hướng dẫn Azurite/tập cấu hình đã kiểm thử; không đoán hoặc đem Azure storage account key thật sang emulator. Một số SDK/tooling còn chấp nhận `UseDevelopmentStorage=true` theo khả năng riêng; với Azure Storage SDK Java, dùng **connection string endpoints rõ ràng** thường ít mơ hồ hơn trong test.

### 6.3. Tách môi trường test bằng biến

```bash
# Không ghi account key production vào source code.
export AZURITE_BLOB_CONNECTION_STRING="<single-line-Azurite-connection-string>"
export AZURE_INTEGRATION_TARGET="emulator"
```

PowerShell có cú pháp gán env var khác Bash; CI nên inject từ settings/secret provider phù hợp. Tuy đây là dev key công khai, **vẫn đặt tên rõ và kiểm tra endpoint** để không đọc nhầm account thật từ một variable có tên chung.

### 6.4. Azurite và API-version mismatch

SDK có thể mặc định gọi service API version mới hơn Azurite đã hỗ trợ. Khi thấy lỗi `UnsupportedApiVersion` hoặc request không được emulator nhận, **không vội kết luận code Java hỏng hay Azure thật cũng lỗi**. Cập nhật/pin Azurite version tương thích; nếu cần chế độ “loose” để debug, không dùng nó làm bằng chứng parity. Dành cloud integration test cho feature chưa được emulator mô phỏng.

## 7. Java SDK kết nối Azurite: ví dụ round-trip Blob

Đoạn code dùng **synchronous Blob SDK** để tạo container, upload, download và dọn dữ liệu. Nó thực sự gọi HTTP endpoint của Azurite; không dùng mock `BlobClient`.

### 7.1. Mã Java minh họa

```java
import com.azure.core.util.BinaryData;
import com.azure.storage.blob.BlobContainerClient;
import com.azure.storage.blob.BlobServiceClient;
import com.azure.storage.blob.BlobServiceClientBuilder;

import java.nio.charset.StandardCharsets;
import java.util.Objects;
import java.util.UUID;

public final class AzuriteRoundTrip {
    public static void main(String[] args) {
        String connectionString = Objects.requireNonNull(
                System.getenv("AZURITE_BLOB_CONNECTION_STRING"),
                "Set AZURITE_BLOB_CONNECTION_STRING before running");

        BlobServiceClient service = new BlobServiceClientBuilder()
                .connectionString(connectionString)
                .buildClient();

        String containerName =
                "it-" + UUID.randomUUID().toString().replace("-", "");
        BlobContainerClient container =
                service.getBlobContainerClient(containerName);
        container.createIfNotExists();

        try {
            byte[] original = "Xin chào Azure SDK".getBytes(
                    StandardCharsets.UTF_8);
            String key = "receipts/order-1042.txt";

            container.getBlobClient(key).upload(
                    BinaryData.fromBytes(original), true);
            byte[] downloaded = container.getBlobClient(key)
                    .downloadContent().toBytes();

            if (!java.util.Arrays.equals(original, downloaded)) {
                throw new AssertionError("Content mismatch");
            }
            System.out.println("Blob round-trip passed");
        } finally {
            // Xóa đúng container ngẫu nhiên do bài test tạo.
            container.deleteIfExists();
        }
    }
}
```

Để chạy cần dependency `azure-storage-blob`, Azurite đang hoạt động và biến môi trường chứa đúng **local connection string**. Không dùng `container.deleteIfExists()` với một container không thuộc test: tên ở đây là **unique test-owned resource**.

### 7.2. Kết quả cần xác minh

Một round-trip đúng phải:

1. Tạo container thành công và nhận được response của service/emulator.
2. Upload bytes đúng key.
3. Download lại và so sánh **nội dung thực**, không chỉ status code.
4. Dọn dữ liệu dù assertion/SDK call thất bại.
5. Không in connection string/key vào log.

### 7.3. Cần test gì thêm?

- Upload không overwrite khi blob đã tồn tại.
- Download blob không tồn tại trả lỗi tương ứng.
- Content type/metadata được lưu và đọc lại.
- Tên blob có ký tự Unicode, dấu cách hoặc slash được SDK encode đúng.
- Blob size boundaries (nhỏ, rỗng, lớn trong phạm vi test).
- Upload/download stream bị ngắt giữa chừng.
- Conditional writes bằng ETag/`If-Match` nếu nghiệp vụ cần chống lost updates.
- Delete và verify not found sau delete.

Không nên copy dữ liệu customer/PII thật sang local emulator chỉ để tăng kích thước fixture. Dùng generated/synthetic bytes.

## 8. JUnit 5: viết một integration test thật

Mẫu dưới đây dùng một Azurite đã được khởi động trước và biến môi trường `AZURITE_BLOB_CONNECTION_STRING`. Không có env var thì test **fail rõ ràng**, không tự skip; điều này giúp tránh CI “xanh” khi integration test chưa thực sự chạy.

```java
import com.azure.core.util.BinaryData;
import com.azure.storage.blob.BlobContainerClient;
import com.azure.storage.blob.BlobServiceClient;
import com.azure.storage.blob.BlobServiceClientBuilder;
import com.azure.storage.blob.models.BlobStorageException;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

import java.nio.charset.StandardCharsets;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.*;

@Tag("emulator")
class BlobStoreAzuriteIT {
    private BlobContainerClient container;
    private AzureBlobDocumentStore store;

    @BeforeEach
    void setUp() {
        String cs = System.getenv("AZURITE_BLOB_CONNECTION_STRING");
        assertNotNull(cs, "Azurite must be configured in CI");
        assertTrue(cs.contains("127.0.0.1")
                        || cs.contains("localhost"),
                "Refusing a non-local emulator endpoint");

        BlobServiceClient service = new BlobServiceClientBuilder()
                .connectionString(cs)
                .buildClient();
        String testName =
                "it-" + UUID.randomUUID().toString().replace("-", "");
        container = service.getBlobContainerClient(testName);
        container.createIfNotExists();
        store = new AzureBlobDocumentStore(container);
    }

    @AfterEach
    void tearDown() {
        if (container != null) {
            container.deleteIfExists();
        }
    }

    @Test
    void shouldUploadAndReadRealBlob() {
        byte[] expected =
                "integration-check".getBytes(StandardCharsets.UTF_8);
        String key = "invoices/order-1042.txt";

        store.put(key, expected);

        assertTrue(store.exists(key));
        assertArrayEquals(expected, store.get(key));
    }

    @Test
    void shouldReturnNotFoundFromStorageService() {
        BlobStorageException ex = assertThrows(
                BlobStorageException.class,
                () -> container.getBlobClient("not-there.txt")
                        .downloadContent());

        assertEquals(404, ex.getStatusCode());
    }

    @Test
    void shouldDeleteExistingBlob() {
        store.put("temp.txt", new byte[]{1, 2, 3});
        assertTrue(store.exists("temp.txt"));
        store.delete("temp.txt");
        assertFalse(store.exists("temp.txt"));
    }
}
```

**Đây là code JUnit 5 sử dụng adapter ở phần 4**, nên cần đưa cả hai class và Maven dependencies vào dự án lab trước khi chạy. Điều kiện `localhost` chỉ là **guard minh họa** cho Azurite chạy trực tiếp trên cùng máy; không dùng guard này cho Testcontainers/CI remote runtime nơi Docker host có hostname khác. Trong production-quality tests, xác minh **target kind và allowlisted resource ID/endpoint** thay vì chỉ tìm substring hostname.

### 8.1. Ba nguyên tắc isolation

- **Tên tài nguyên duy nhất:** container và blob keys có random suffix để tests chạy song song không đụng nhau.
- **Không chia sẻ mutable state:** test đọc/ghi dữ liệu của chính mình, không phụ thuộc thứ tự tests.
- **Cleanup có bảo vệ:** chỉ xóa resources do test tạo, dù test thất bại, và có cơ chế xử lý artifact sót khi CI job bị kill.

### 8.2. Vì sao kiểm tra 404 có ích?

SDK phải parse error response thành `BlobStorageException` với status code. Đó là **contract thật qua HTTP** mà một mock `when(blob.downloadContent()).thenThrow(...)` không xác minh được. Tuy nhiên, service Azure thật vẫn có thể có các mã lỗi/rate limit/authorization khác emulator, nên test cloud vẫn cần thiết.

### 8.3. Test được phép song song đến mức nào?

Với mỗi test tạo một container ngẫu nhiên, đa số CRUD tests có thể song song. Nhưng **account-level quotas**, container listings, transient conflicts hoặc mã static shared client không an toàn có thể gây flakiness. Với test ghi cùng blob, phải tạo **barrier/coordination** nếu muốn kiểm thử concurrency thật chứ không dựa vào may rủi scheduler.

## 9. Testcontainers: tự quản lý vòng đời Azurite cho test

Khi CI chạy trên runner có Docker, **Testcontainers** giúp khởi động Azurite trước tests, map dynamic ports và dừng khi xong. Ưu điểm là tránh phụ thuộc local port `10000` đang rảnh hay người chạy đã tự bật service.

### 9.1. Ví dụ JUnit + Testcontainers

```java
import com.azure.core.util.BinaryData;
import com.azure.storage.blob.BlobContainerClient;
import com.azure.storage.blob.BlobServiceClient;
import com.azure.storage.blob.BlobServiceClientBuilder;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

import java.nio.charset.StandardCharsets;
import java.util.Objects;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.*;

@Testcontainers
@Tag("emulator")
class BlobTestcontainersIT {
    @Container
    static final GenericContainer<?> AZURITE =
            new GenericContainer<>(
                    DockerImageName.parse(
                            "mcr.microsoft.com/azure-storage/azurite:latest"))
                    .withExposedPorts(10000);

    private static BlobContainerClient container;

    @BeforeAll
    static void init() {
        // Dùng đúng built-in dev account key công bố cho Azurite.
        // Giá trị cần được lấy từ config test, không phải production key.
        String devKey = Objects.requireNonNull(
                System.getenv("AZURITE_DEV_ACCOUNT_KEY"),
                "AZURITE_DEV_ACCOUNT_KEY must hold the Azurite dev key");

        String endpoint = "http://" + AZURITE.getHost() + ":"
                + AZURITE.getMappedPort(10000) + "/devstoreaccount1";
        String cs = "DefaultEndpointsProtocol=http;"
                + "AccountName=devstoreaccount1;"
                + "AccountKey=" + devKey + ";"
                + "BlobEndpoint=" + endpoint + ";";

        BlobServiceClient service = new BlobServiceClientBuilder()
                .connectionString(cs)
                .buildClient();

        String name =
                "it-" + UUID.randomUUID().toString().replace("-", "");
        container = service.getBlobContainerClient(name);
        container.createIfNotExists();
    }

    @AfterAll
    static void cleanUp() {
        if (container != null) {
            container.deleteIfExists();
        }
    }

    @Test
    void blobRoundTripOverMappedPort() {
        String key = "samples/greeting.txt";
        String content = "Chào Testcontainers";
        container.getBlobClient(key).upload(
                BinaryData.fromBytes(content.getBytes(
                        StandardCharsets.UTF_8)), true);
        assertEquals(content,
                container.getBlobClient(key)
                        .downloadContent().toString());
    }
}
```

Ví dụ sử dụng `latest` **chỉ để diễn giải cú pháp**; CI cần **pin image digest/tag** đã xác nhận hỗ trợ SDK/service API version. `AZURITE_DEV_ACCOUNT_KEY` phải khớp khóa mặc định đã công bố của Azurite – không tạo giá trị random rồi kỳ vọng emulator tự nhận. Với cấu hình **custom Azurite account**, phải cấu hình cùng account/key ở phía container và connection string.

### 9.2. Docker host và port mapping động

Testcontainers trả `getHost()` và `getMappedPort(10000)`, vì cổng trên host không nhất thiết là 10000. Không hard-code `localhost:10000` trong test khi chạy CI có Docker-in-Docker hoặc daemon từ xa. Nếu SDK phản hồi redirect/hostname khác dự kiến, kiểm tra cấu hình emulator endpoint, Docker network và proxy.

### 9.3. Đảm bảo container “ready”

Thông thường Testcontainers có cơ chế chờ container startup, nhưng các image/services phức tạp có thể cần **wait strategy** theo log/HTTP endpoint/port được tài liệu hỗ trợ. Với Azurite, tránh sleep cứng 15 giây như giải pháp lâu dài; cấu hình test chờ khả năng kết nối và fail có nguyên nhân rõ. Đối với Service Bus/Event Hubs Emulator có nhiều containers phụ thuộc, healthchecks/compose readiness càng quan trọng.

### 9.4. Reuse containers hay tạo mới?

- Local developer có thể dùng container reuse để tăng tốc **nếu dữ liệu được reset và config đồng nhất**.
- CI nên ưu tiên môi trường rõ ràng, resource names unique, không dựa vào trạng thái cũ.
- Không để các suites sửa cùng queue/container rồi fail ngẫu nhiên.
- Những bài test cần sạch hoàn toàn nên tạo account/container name mới hoặc reset emulator data theo cách an toàn.

### 9.5. Vì sao không tự skip khi Docker không sẵn?

Một integration gate phải **thất bại với thông báo “Docker unavailable”** nếu CI bắt buộc chạy nhóm đó. Có thể tách job `emulator-it` và đánh dấu optional cho developer laptop, nhưng pipeline release không được báo “verified integration” khi mọi emulator tests bị disabled/skipped.

## 10. Mở rộng test Blob: metadata, ETag và lỗi thật

Từ adapter cơ bản, thêm các trường hợp:

### 10.1. Content type và metadata

Một tài liệu PDF khi upload nên có `Content-Type: application/pdf`. Nếu không, consumer/CDN/download có thể xử lý sai. Test nên:

1. Upload Blob với `BlobHttpHeaders` và metadata.
2. Đọc `BlobProperties` từ emulator.
3. Assert content type/metadata thực.
4. Chạy một cloud test nhỏ để phát hiện khác biệt API/feature.

Ví dụ:

```java
import com.azure.storage.blob.models.BlobHttpHeaders;

var blob = container.getBlobClient("receipts/1042.pdf");
blob.upload(BinaryData.fromBytes(new byte[]{1, 2, 3}), true);
blob.setHttpHeaders(
        new BlobHttpHeaders().setContentType("application/pdf"));

assertEquals("application/pdf",
        blob.getProperties().getContentType());
```

Đây là **snippet trong test** có `container` và JUnit assertions, không phải class độc lập. Payload 3 bytes không phải PDF hợp lệ; dùng synthetic PDF fixture nếu cần test file-format pipeline, nhưng để kiểm tra metadata SDK thì bytes giả đã đủ.

### 10.2. Optimistic concurrency bằng ETag

Hai writers cùng cập nhật blob có thể ghi đè nhau. Nếu workflow cần chống lost update, dùng conditional request `If-Match: ETag` theo API overload hỗ trợ, và test:

```text
Writer A GET properties -> ETag E1
Writer B ghi bản mới   -> ETag E2
Writer A upload với If-Match E1
  -> kỳ vọng lỗi precondition, không ghi đè B
```

Ở Azure SDK Java, các điều kiện ETag thường nằm trong `BlobRequestConditions`/options theo method/version. Cần chọn **đúng overload** và assert error code/precondition theo SDK, không giả lập bằng việc đọc ETag rồi ghi upload không điều kiện.

### 10.3. Test overwrite semantics

Một ứng dụng tạo invoice phải tránh làm mất tài liệu cũ. Kiểm tra:

- Upload lần đầu thành công.
- Upload cùng key với overwrite disabled cho lỗi xung đột đúng contract.
- Khi có legitimate update, use version/ETag thay vì bật overwrite tùy tiện.
- Unit tests xác minh business policy và integration tests xác minh HTTP conditional operations.

### 10.4. Test tên tài nguyên hợp lệ

Azure Blob container name có yêu cầu định dạng (chữ thường, dấu gạch nối, độ dài phù hợp), còn Blob name có quy tắc khác. Dùng generator tạo tên container hợp lệ và assert negative tests với tên sai. Không chỉ dựa vào emulator cho toàn bộ naming/service limits; cloud real test nên kiểm tra những giới hạn ảnh hưởng nghiệp vụ.

## 11. Queue Storage: semantics khác Blob và test khác

Azure Queue Storage là một hàng đợi đơn giản; **không bảo đảm business exactly-once**. Nhận message có thể đặt nó **invisible tạm thời**, worker cần delete bằng `messageId` và `popReceipt` phù hợp. Nếu worker lỗi trước delete, message có thể hiển thị lại và được xử lý lặp.

### 11.1. Flow đúng

```text
Java API --sendMessage--> Azure Queue
                                 |
                           Worker receive
                                 |
                           Mark invisible
                                 |
                     Process idempotently
                                 |
                      Delete using pop receipt
                                 |
                         Success / audit
```

### 11.2. Java Queue SDK snippet

```java
import com.azure.storage.queue.QueueClient;
import com.azure.storage.queue.QueueClientBuilder;
import com.azure.storage.queue.models.QueueMessageItem;

import java.util.Iterator;

String cs = System.getenv("AZURITE_QUEUE_CONNECTION_STRING");
QueueClient queue = new QueueClientBuilder()
        .connectionString(cs)
        .queueName("it-work-items")
        .buildClient();

queue.createIfNotExists();
queue.sendMessage("job-1042");

Iterator<QueueMessageItem> messages =
        queue.receiveMessages(1).iterator();

if (!messages.hasNext()) {
    throw new AssertionError("Expected one queued message");
}

QueueMessageItem item = messages.next();
// Process nghiệp vụ cần idempotency, không chỉ print message.
queue.deleteMessage(item.getMessageId(), item.getPopReceipt());
```

Đây là **fragment** dùng `azure-storage-queue` dependency bổ sung theo BOM và một queue riêng của lab. Cấu hình connection string và tên queue phải là test-owned; đoạn ví dụ không chứa cleanup queue để người học có thể quan sát state, nhưng test thật phải dọn bằng `queue.deleteIfExists()` sau khi xác minh. Tùy SDK version, tên class, overload hoặc cấu trúc message content có thể khác; kiểm tra API đang dùng.

### 11.3. Những test bắt buộc với Queue

| Test | Thao tác | Assertion |
|---|---|---|
| Happy path | Send → receive → delete | Queue không còn message sau delete |
| Worker crash | Receive, không delete, đợi visibility timeout | Message có thể được nhận lại |
| Duplicate | Gửi cùng business job ID nhiều lần | Worker chỉ tạo một business effect |
| Poison message | Payload malformed/unsupported | Không retry vô hạn; có quarantine/poison handling |
| Queue empty | Receive khi không có message | App không crash hoặc báo sai |
| Expiry | Message TTL hết | Không xử lý message quá hạn |
| Scale workers | Nhiều consumers | Không đòi thứ tự tuyệt đối/exactly-once |

**Tránh test timeout bằng sleep dài** trong mọi PR. Unit test state machine bằng fake clock, integration test một vài visibility timeout ngắn trong thời hạn được service hỗ trợ, và chạy cloud test riêng cho các trường hợp quan trọng.

### 11.4. Khác biệt với Service Bus

Azure Queue Storage không có đầy đủ những tính năng enterprise messaging của **Azure Service Bus** như sessions, dead-letter subqueues, duplicate detection hoặc settlement semantics ở cấp Service Bus. Không copy test assertion của `ServiceBusReceiverClient.completeMessage()` sang `QueueClient.deleteMessage()` và cho rằng hai hệ thống giống nhau.

## 12. Azure Table Storage và Azurite

Azurite còn mô phỏng **Table Storage** ở mức tính năng được hỗ trợ. Với Java, dùng **Azure Data Tables SDK** (thường artifact `azure-data-tables`) để kiểm tra entity CRUD, `PartitionKey`/`RowKey`, OData query và ETag update.

### 12.1. Mô hình entity

```text
Table: DeviceReadings
  PartitionKey = "site-hcm-02"
  RowKey       = "device-0042-20261120T0900"
  TemperatureC = 4.2
  Status       = "HEALTHY"
```

Table Storage không giống **Azure Cosmos DB for NoSQL** dù đều có từ “partition”. Cách index, partition strategy, request units, consistency và query language khác nhau.

### 12.2. Test quan trọng

- Tạo và xóa bảng test duy nhất.
- Insert entity với `PartitionKey` + `RowKey`.
- Read entity đúng key.
- Query theo partition, lọc và phân trang nếu API hỗ trợ.
- Insert trùng key gây conflict đúng hợp đồng.
- ETag conditional update không ghi đè stale version.
- Lỗi entity chưa tồn tại và data type serialization.

### 12.3. Không suy từ Azurite sang mọi tính năng production

Table SDK có thể gọi features/service API versions mới không được bản Azurite đang pin hỗ trợ. Storage account thật còn có auth/RBAC, quota và network restrictions. Với một feature có tác động nghiệp vụ như batch transaction trong cùng partition hoặc ETag concurrency, thêm cloud real test khi chuẩn bị release.

## 13. Azure Cosmos DB Emulator cho Java SDK

**Azure Cosmos DB Emulator** cho phép kiểm thử một phần Azure Cosmos DB for NoSQL API trên máy/container theo nền tảng được hỗ trợ. Việc cài đặt/khởi động phụ thuộc **emulator version, hệ điều hành, image và hỗ trợ Docker/Windows**. Vì vậy bài học không tự gán một command Docker cố định cho tất cả môi trường.

### 13.1. Những gì test có thể chứng minh

| Hành vi | Emulator phù hợp? | Cần cloud xác minh thêm |
|---|---|---|
| Serialize POJO thành JSON item | Có | SDK/service API compatibility |
| Create, read, replace, delete item | Có ở API hỗ trợ | IAM, network, account consistency behavior |
| Partition key truyền đúng | Có | Real partition distribution/throughput/skew |
| SQL query và pagination cơ bản | Có | Query RU, indexing, cross-partition cost |
| Optimistic concurrency bằng ETag | Có ở tính năng hỗ trợ | Concurrency thực và retry under load |
| RU charge, autoscale, multi-region replication | Không đại diện đầy đủ | **Bắt buộc cloud** |
| Private Link, Entra authorization, CMK | Không đầy đủ | **Bắt buộc cloud** |

### 13.2. Java Cosmos SDK: client injection

Đối với Java Cosmos NoSQL SDK, client thường được xây từ endpoint và credential theo kiểu SDK/version:

```java
import com.azure.cosmos.CosmosClient;
import com.azure.cosmos.CosmosClientBuilder;

String endpoint = System.getenv("COSMOS_TEST_ENDPOINT");
String key = System.getenv("COSMOS_TEST_KEY");

CosmosClient client = new CosmosClientBuilder()
        .endpoint(endpoint)
        .key(key)
        .gatewayMode()
        .buildClient();

try {
    // Create test database/container, write/read items,
    // assert partition key, ETag và query results ở đây.
} finally {
    client.close();
}
```

Đây là **fragment** dùng `azure-cosmos` dependency, chỉ áp dụng **key-based emulator/test account** theo phiên bản hỗ trợ. Với Azure thật có Entra authentication, dùng credential overload/role assignment phù hợp thay vì hard-code account key. **Cosmos DB data-plane RBAC khác Azure management-plane RBAC**; một Contributor quản lý resource không tự được quyền CRUD items.

### 13.3. Self-signed emulator certificate

Một số Cosmos Emulator cung cấp HTTPS endpoint với **development certificate** cần được Java truststore tin cậy theo hướng dẫn phiên bản. Lỗi `SSLHandshakeException` trên emulator không nên được “sửa” bằng cách đặt TLS trust-all trong production code. Cấu hình truststore **chỉ cho test runtime/emulator** và không đưa development CA vào production truststore.

### 13.4. Direct vs gateway mode

Cosmos Java SDK có thể hỗ trợ **Gateway** và **Direct** connection modes theo API/SDK. Môi trường emulator/container/firewall có thể yêu cầu Gateway; cloud production có thể dùng mode khác phù hợp networking và performance. Một emulator test qua Gateway không chứng minh Direct mode đến Azure thật hoạt động qua firewall/private endpoint; cloud integration test phải dùng **cùng mode dự kiến deploy**.

### 13.5. Partition key test không chỉ là happy path

Nếu container partition theo `/tenantId`, test nên có:

- Cùng `id` ở hai tenants khác nhau theo semantics key/ID.
- Đọc item bằng đúng partition key.
- Query thiếu partition key gây fan-out/cost theo service semantics.
- Wrong partition key không đọc nhầm item.
- ETag conflict khi update một item.
- Duplicate `id + partitionKey` không tạo hai bản ghi.
- Delete/recreate và kiểm tra idempotency.

**Không lấy RU/s hoặc latency emulator làm tiêu chí sizing Cosmos DB production.** RU request charge, indexing cost, autoscale và hot partition cần đo trên cloud tier phù hợp.

## 14. Service Bus Emulator: kiểm thử messaging đúng phạm vi

Khi dùng Azure Service Bus SDK Java (`azure-messaging-servicebus`), có thể sử dụng **Service Bus Emulator** được Microsoft phát hành, nếu **tính năng/SKU/phiên bản** phù hợp. Từng bản emulator có thể cần **Docker Compose**, cấu hình queue/topic/subscription và service phụ trợ như SQL Server container; không nên viết “`docker run servicebus`” chung chung rồi kỳ vọng mọi thứ hoạt động.

### 14.1. Những workflow cần test

```text
Producer (ServiceBusSenderClient)
          |
          | messageId, correlationId, payload
          v
Service Bus queue / topic-subscription
          |
          v
Consumer (ServiceBusReceiverClient)
          |
          +-- complete on success
          +-- abandon/retry on transient failure
          +-- dead-letter on poison message theo policy
```

### 14.2. Mẫu Java receiver có business boundary

```java
// Fragment minh họa: đã tạo ServiceBusReceiverClient bằng
// ServiceBusClientBuilder theo SDK và connection config test.
var messages = receiver.receiveMessages(1);

for (var message : messages) {
    String logicalId = message.getMessageId();
    try {
        // Business layer phải idempotent theo logicalId.
        processIdempotently(logicalId, message.getBody().toBytes());
        receiver.complete(message);
    } catch (PermanentInvalidPayloadException ex) {
        receiver.deadLetter(message);
    } catch (Exception transientFailure) {
        receiver.abandon(message);
    }
}
```

Các method/type ở trên là **fragment ứng dụng**: `processIdempotently` và `PermanentInvalidPayloadException` do dự án định nghĩa; `receiver` được cấu hình theo API/version hỗ trợ và dùng **PEEK_LOCK** mode cho settlement. Trong bản SDK/overload cụ thể, có thể cần sửa cách lấy `Iterable`/receiver mode; không copy code production trước khi đối chiếu docs và chạy integration test.

### 14.3. Emulator test không thay cloud feature test

Những tính năng như **sessions, duplicate detection, scheduling, transactions, premium networking, geo-DR, quotas, RBAC và message size** có thể được emulator hỗ trợ một phần hoặc không hỗ trợ tùy phiên bản. Lập **feature matrix** đối chiếu các tính năng thực sự dùng. Nếu production dùng sessions hoặc Premium-specific capacity, phải có **real Azure Service Bus test** thích hợp.

### 14.4. Settlement không đồng nghĩa exactly-once

Nếu worker ghi Azure SQL rồi crash trước `complete`, message có thể được giao lại. Cần **idempotency key/inbox** ở database; emulator có thể test retry delivery nhưng **không thay invariant nghiệp vụ** và cloud failover behavior.

### 14.5. Service Bus Emulator cần bảo vệ môi trường test

- Không dùng connection string của production namespace.
- Dùng namespace/config/test queue riêng; không xóa queue dùng chung của developer khác.
- Pin compose images và resource configs.
- Chờ readiness của phụ thuộc, không chỉ container process running.
- Đảm bảo CI cleanup containers/volumes trong phạm vi job.

## 15. Event Hubs Emulator: producer/consumer và checkpoint

**Azure Event Hubs** phục vụ high-throughput event streaming; SDK Java thường dùng `azure-messaging-eventhubs` và `EventProcessorClient`/checkpoint store cho consumer groups. Event Hubs Emulator giúp thử một số luồng publish/consume tại local, nhưng phải dùng **supported emulator image/config**, thường có dependencies được hướng dẫn qua Compose.

### 15.1. Test case phù hợp

1. Producer gửi batch có event ID và partition key hợp lệ.
2. Consumer group riêng đọc events và xác minh payload/correlation.
3. Checkpoint được lưu qua checkpoint store phù hợp, nếu emulator/config hỗ trợ.
4. Restart consumer và kiểm tra resume behavior trong test.
5. Xử lý duplicates/late events idempotent.
6. Tắt consumer để giả lập processing lag và đo recovery.

### 15.2. Không nhầm checkpoint với broker ACK

Một consumer nhận event và checkpoint quá sớm rồi fail trước khi ghi database có thể **mất xử lý** từ góc nhìn ứng dụng. Ngược lại, ghi database thành công nhưng chưa checkpoint có thể khiến event được xử lý lại sau restart. Cần **idempotent sink** và xác định ranh giới commit/checkpoint.

### 15.3. Những gì bắt buộc cloud test

- Throughput units/capacity limits và throttling thật.
- Multi-partition load balancing/scale-out với consumer groups.
- Network/private endpoints, Entra authorization và SAS policy theo config.
- Event Hubs Capture/retention/namespace tier-specific features.
- Availability/failover/region/network behavior theo kiến trúc.

Không áp throughput emulator trên laptop thành số partition/số throughput units cần mua trên Azure.

### 15.4. Phân biệt Event Hubs Emulator với Azurite

Event Hubs Emulator **không phải** một module của Azurite. Chúng có thể được ghép trong Docker Compose cho một workflow có checkpoint trên Blob Storage, nhưng feature support của từng emulator tách biệt. Mỗi container phải có endpoint/credential và readiness kiểm chứng riêng.

## 16. Azure Functions Core Tools với emulator

Một Azure Function viết bằng Java có thể được chạy local bằng **Azure Functions Core Tools** (hoặc plugin tooling phù hợp). Các triggers/bindings như Blob/Queue có thể dùng **Azurite** cho một số kịch bản; `local.settings.json` thường chứa cấu hình local connection để Functions runtime nhận.

### 16.1. Sơ đồ test

```text
JUnit / HTTP client
       |
       v
Local Azure Functions host (Java function)
       |
       +-- Blob/Queue binding --> Azurite
       |
       +-- Business service --> test database/fake
       |
       v
Assertions on real blob/queue state
```

### 16.2. Giới hạn quan trọng

- Local Functions host **không mô phỏng đầy đủ** Azure Functions scaling, consumption plan, storage/network/managed identity.
- Trigger batching/locking/retries và extensions có version/host setting riêng.
- Local settings và secret values **không** được commit vào repository.
- Một integration test local chạy thành công không chứng minh Azure deployment có correct app settings, VNet integration hoặc RBAC.

### 16.3. Test đúng boundary

Nếu Function trigger là Queue, có thể test **send → trigger runs → observed Blob/DB output**. Chỉ gọi function handler Java trực tiếp là unit test function logic, chưa xác minh queue trigger/binding/runtime host.

## 17. Các dịch vụ không nên giả lập toàn bộ

Một số tích hợp sẽ cần Azure thật:

- **Key Vault**: authentication và secrets/certificate permissions, firewall/private endpoint, versioning và rotation.
- **Microsoft Entra ID / managed identity**: tenant, audience, token scopes và RBAC.
- **Azure App Configuration**: labels, feature flags, refresh và auth.
- **Azure SQL / PostgreSQL Flexible Server**: database identity, firewalls, TLS, network, HA.
- **AKS workload identity**: federated credential, service account claims, token exchange.
- **Storage encryption/network controls**, geo-redundancy và service feature gating.

Đối với unit tests có thể fake credential providers/client adapters để kiểm tra behavior, nhưng **không tuyên bố Azure IAM “đã được test”** khi chỉ mock `DefaultAzureCredential` trả token giả.

### 17.1. Contract test với giả lập HTTP

Khi chưa có emulator, một HTTP stub (WireMock hoặc custom test server) có thể kiểm tra **app gửi path/header/body đúng và xử lý status codes**. Tuy nhiên nó không xác minh service-side policy, DNS, token audience, throttling và API-specific nuances. Ghi rõ test label là **contract/stub**, không gọi nó cloud integration.

### 17.2. Fake provider có ích ở đâu?

- Clock/UUID/retry scheduler để kiểm soát thời gian.
- Secret provider để kiểm tra rotation logic.
- Blob/Queue port để kiểm tra business orchestration.
- Command receiver để inject timeout, conflict, throttling và network resets.
- Metrics/tracing sink để assert không log secrets.

Fake không nên che tên service thật trong test report: cần biết bài test đã sử dụng **fake, emulator hay Azure**.

## 18. Khi nào bắt buộc kiểm thử trên tài nguyên Azure thật?

**Emulator green không phải cloud-ready.** Sau khi code qua unit/emulator, những test sau cần chạy trên subscription/resource group **không chứa production workloads**:

1. **Microsoft Entra ID authentication** từ đúng principal/runtime.
2. **Azure data-plane RBAC** cho đọc/ghi/xóa theo quyền tối thiểu.
3. **TLS, endpoint, hostname và DNS** đúng, nhất là Private Endpoint/VNet.
4. **Service API version, feature support, region, tier** thật.
5. **Timeout/retry/quota** trong điều kiện load và configuration dự kiến.
6. **Concurrency/ETag** hoặc messaging lock/settlement behavior thật khi business cần.
7. **Observability**: traces/logs/metrics và error classification từ cloud.
8. **Cost**: bytes scanned, request units, message operations, compute và resource lifecycle.

Không nhất thiết chạy **mọi** trường hợp mỗi PR. Nhưng nếu production phụ thuộc một tính năng cloud **không có emulator**, phải có một cloud test định kỳ hoặc release gate kiểm tra nó.

### 18.1. Chọn subscription test riêng

Một thiết kế tốt:

```text
Azure tenant
  |
  +-- Non-production subscription / billing scope
         |
         +-- rg-sdk-it-<run-id>
         |      |
         |      +-- storage account created by IaC
         |      +-- temporary test queue/blob container
         |      +-- narrow RBAC role assignments
         |
         +-- central test logs/budget policy
```

Có thể dùng một **resource group tạm cho mỗi test run** hoặc resource dùng chung theo team với **namespace tài nguyên test riêng cho mỗi run**. Lựa chọn phụ thuộc tốc độ provision, chi phí, quota và khả năng cleanup. Dùng shared account có thể giảm startup time nhưng phải ngăn chặn tests xóa dữ liệu của nhau.

### 18.2. Không thử vào production bằng nhãn “test”

Một container tên `test-container` trong một production storage account **vẫn là tác động production**: có thể bị ảnh hưởng bởi RBAC, policy, logging, quota, billing và cleanup sai. Hãy yêu cầu **resource ID allowlist**, subscription ID và guardrails trong CI. Không chỉ dựa vào tên “test” do developer tự đặt.

### 18.3. Test cần đủ giống production nhưng không quá đắt

Cloud test account nên giống production ở những đặc tính quyết định correctness: **service API, network model, TLS, identity mode, tier feature**. Không cần copy khối lượng production thật hoặc dữ liệu nhạy cảm để xác minh một Blob upload. Hiệu năng/scale tests có thể chạy trong môi trường chuyên biệt và được phê duyệt.

## 19. Provision Azure Storage thử nghiệm có vòng đời rõ

Ví dụ Bash/Azure CLI bên dưới chỉ là **lab provisioning script**. Cần đăng nhập đúng non-production subscription, có quyền tạo resource và đặt budget/quotas phù hợp. **Không thực thi trực tiếp trên production subscription**.

### 19.1. Tạo resource group và storage account

```bash
az login
az account set --subscription "<non-production-subscription-id>"
az account show --output table

RUN_SUFFIX="<unique-lowercase-digits-suffix>"
REGION="southeastasia"
RG="rg-sdk-it-$RUN_SUFFIX"
STORAGE="stsdk$RUN_SUFFIX"

# Storage account name: globally unique, lowercase/numeric, 3..24 chars.
az group create \
  --name "$RG" \
  --location "$REGION" \
  --tags purpose=sdk-integration-test owner=data-platform environment=testing

az storage account create \
  --resource-group "$RG" \
  --name "$STORAGE" \
  --location "$REGION" \
  --sku Standard_LRS \
  --kind StorageV2 \
  --allow-blob-public-access false \
  --min-tls-version TLS1_2 \
  --https-only true

STORAGE_ID=$(az storage account show \
  --resource-group "$RG" \
  --name "$STORAGE" \
  --query id -o tsv)

echo "Created a test-owned account ID; verify before using:"
echo "$STORAGE_ID"
```

Chọn region/tier hỗ trợ theo subscription hiện tại. **Đây là resource có tính phí**, dù được gọi “test”; Azure Storage account, transactions, diagnostic logs và network có thể phát sinh phí. Với account có network policy **deny-by-default** hoặc Private Endpoint, script phải thêm network/identity setup theo IaC tương ứng trước khi test có thể kết nối.

### 19.2. Cấp data-plane role cho principal chạy test

```bash
IDENTITY_OBJECT_ID="<object-id-of-test-service-principal-or-managed-identity>"

az role assignment create \
  --assignee-object-id "$IDENTITY_OBJECT_ID" \
  --assignee-principal-type ServicePrincipal \
  --role "Storage Blob Data Contributor" \
  --scope "$STORAGE_ID"
```

Role này chỉ là ví dụ cho **Blob CRUD test**, không nên cấp quyền cấp subscription. Nếu test cần Queue Storage, dùng role data-plane phù hợp **Queue** thay vì giả định Blob Data Contributor đủ quyền queue. **RBAC assignment có độ trễ hiệu lực**: test nên phân biệt role chưa propagation xong với code bug, dùng polling có deadline.

### 19.3. Bảo vệ xóa resource

Sau khi test và lấy logs:

```bash
# Xác minh tên/ràng buộc trước khi xóa.
case "$RG" in
  rg-sdk-it-*) echo "Expected test RG prefix" ;;
  *) echo "Refusing to delete non-test RG"; exit 1 ;;
esac

# Chỉ xóa RG thực sự do job này tạo, trong subscription đã xác minh.
az group delete --name "$RG" --yes
```

**Prefix không phải cơ chế bảo vệ duy nhất.** Trong CI, lưu `run_id, subscription_id, resource_group_id` từ provision step, xác minh owner tag/manifest và dùng principal chỉ có quyền với test RG. Nếu cleanup được chạy trong job khác, không xóa chỉ bằng cách tìm “mọi RG bắt đầu bằng rg-sdk-it-”; có thể có job khác vẫn dùng.

### 19.4. Rủi ro cleanup thất bại

Process/runner có thể bị kill trước `finally`/post step. Cần **scheduled janitor hoặc TTL policy** cho resources tạm, với điều kiện xóa theo **owner, run ID, creation timestamp và age**, sau khi bảo đảm không còn test đang chạy. Không gỡ resource locks hoặc xóa các tài nguyên không thuộc sở hữu job chỉ để đạt “zero leaked resources”.

## 20. DefaultAzureCredential trên cloud test account

Trên Azure thật, ứng dụng nên dùng **token-based authentication** nếu dịch vụ/SDK hỗ trợ. Ví dụ Blob SDK:

```java
import com.azure.identity.DefaultAzureCredential;
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.storage.blob.BlobServiceClient;
import com.azure.storage.blob.BlobServiceClientBuilder;

String account = System.getenv("AZURE_TEST_STORAGE_ACCOUNT");
if (account == null || !account.startsWith("stsdk")) {
    throw new IllegalStateException(
            "Only the allowlisted integration-test account may be used");
}

String endpoint = "https://" + account + ".blob.core.windows.net";
DefaultAzureCredential credential =
        new DefaultAzureCredentialBuilder().build();

BlobServiceClient service = new BlobServiceClientBuilder()
        .endpoint(endpoint)
        .credential(credential)
        .buildClient();
```

`DefaultAzureCredential` là **credential chain**: trên developer laptop có thể chọn Azure CLI/IDE; trên cloud CI/deployment có thể chọn workload identity/managed identity hoặc credentials thích hợp theo môi trường/version. **Bài test phải xác minh tenant, subscription, principal thực tế được chọn**, nếu không có thể “thành công” bằng danh tính của một developer thay vì identity production dự kiến.

### 20.1. Emulator thường không thể thay thế identity test

Azurite local dùng **development Shared Key**/một số auth modes riêng; nó **không mô phỏng Azure RBAC/managed identity** tương đương account thật. Vì vậy code Azure client factory thường cần hai paths:

```text
Emulator profile:
  explicit local connection string + Azurite endpoint

Cloud test profile:
  HTTPS account endpoint + explicit intended TokenCredential
  + service data-plane RBAC role assignment

Production profile:
  HTTPS/Private Endpoint + managed/workload identity
  + least privilege + policy + observability
```

Không chuyển production sang account key chỉ vì test Azurite yêu cầu key. Điều đó làm giảm bảo mật và bỏ qua mục tiêu của cloud integration test.

### 20.2. Tách credential khỏi logic SDK adapter

Nên inject một `BlobServiceClient` hoặc `BlobContainerClient` đã cấu hình vào adapter, thay vì đặt `DefaultAzureCredentialBuilder` bên trong từng business method. Test có thể inject Azurite client/cloud test client/fake port tùy tầng.

### 20.3. Trong AKS cần kiểm thử workload identity thật

Với AKS Workload Identity, service account token phải khớp **federated credential issuer, subject, audience**, managed identity/client ID và data-plane RBAC. Unit test không xác minh được trust exchange này. Test deployment trong staging nên chạy pod với cùng workload identity pattern, kiểm tra token acquisition và Blob operation **từ pod**, không chỉ từ laptop operator.

### 20.4. Azure RBAC khác API authorization

Cloud integration test có thể pass vì identity được cấp `Storage Blob Data Contributor`, nhưng ứng dụng web còn phải kiểm tra **tenant/document ownership** để một khách hàng không đọc Blob của khách hàng khác. Unit/business tests cho authorization và cloud tests cho data-plane permissions là **hai bảo đảm khác nhau**.

## 21. Cloud integration test: an toàn và cô lập

Một cloud test tốt phải định nghĩa:

- **Resource ownership:** test đã tạo resource nào, ai sở hữu và lúc nào xóa.
- **Target allowlist:** subscription/resource group/account IDs.
- **Principal identity:** tenant/object ID, expected role và scope.
- **Test namespace:** container/key prefix có run ID, không đụng dữ liệu khác.
- **Data classification:** chỉ dùng synthetic fixture, không copy production PII.
- **Cost budget:** giới hạn requests/data volumes/compute/test duration.
- **Failure policy:** một lỗi auth/network có phải fail gate hay được retry?
- **Cleanup guarantee:** `try/finally`, CI post step và janitor định kỳ.

### 21.1. Một đoạn test cloud dùng lại adapter

```java
@Tag("azure")
@Test
void shouldRoundTripInRealTestStorage() {
    BlobServiceClient service = buildCloudTestBlobClient();
    String runId = java.util.UUID.randomUUID()
            .toString().replace("-", "");
    String containerName = "it-" + runId;

    // buildCloudTestBlobClient phải kiểm tra resource ID/tenant
    // và chỉ cho phép test account trước khi trả client.
    BlobContainerClient container =
            service.getBlobContainerClient(containerName);
    container.createIfNotExists();

    try {
        DocumentStore store =
                new AzureBlobDocumentStore(container);
        byte[] data = "cloud-integration".getBytes(
                java.nio.charset.StandardCharsets.UTF_8);
        store.put("samples/check.txt", data);
        assertArrayEquals(data, store.get("samples/check.txt"));
    } finally {
        container.deleteIfExists();
    }
}
```

Đây là **JUnit method fragment** (imports và `buildCloudTestBlobClient` của ứng dụng chưa có trong đoạn). Không dùng một account name check yếu như `startsWith("stsdk")` làm lớp bảo vệ duy nhất; trong implementation thật, có **subscription/resource ID allowlist, principal scoping và deny-by-default**.

### 21.2. Negative test cho RBAC

Chỉ kiểm tra principal có thể upload chưa chứng minh quyền tối thiểu. Nên có:

| Principal | Test | Kỳ vọng |
|---|---|---|
| **Writer test identity** | Upload/download Blob trong test container | Thành công |
| **Read-only test identity** | Download Blob | Thành công |
| **Read-only test identity** | Upload/delete Blob | Bị từ chối theo data-plane RBAC |
| **No-role test identity** | Read/write Blob | Bị từ chối |
| **Wrong tenant/principal** | Authenticate/access | Bị từ chối, không fallback sang shared key |

Đừng cố tạo negative test bằng cách tạm xóa role của identity production. Dùng **test principals riêng**, scope test resource, kiểm soát propagation và ghi nhận expected status/error. Một request bị firewall chặn không chứng minh RBAC deny đúng: cần phân loại auth vs network.

### 21.3. Role propagation và phép retry hợp lệ

Sau `az role assignment create`, data plane có thể mất thời gian nhận quyền mới. Test provisioning có thể **poll permission** với deadline giới hạn, nhưng không retry tất cả `403` mãi mãi. Nếu quá deadline, báo rõ “RBAC not effective / wrong principal or scope” để operator điều tra.

### 21.4. Dọn sạch dữ liệu cloud

Một test chỉ nên xóa container `it-<runId>` do chính nó tạo. Nếu chạy song song trong shared storage account, **không chạy `az storage container delete --name $CONTAINER_FROM_CONFIG`** khi $CONTAINER có thể trỏ sang production hay data của team khác. Quản lý ownership ID trong manifest thay vì suy từ tên.

## 22. Private Endpoint, TLS và DNS phải test từ đúng nơi chạy

Một cloud test chạy trên laptop developer có public network access không chứng minh ứng dụng AKS qua Private Endpoint sẽ kết nối được.

```text
Developer laptop -> Public Blob endpoint -> success

AKS workload -> Private DNS -> Private Endpoint -> Storage
                         |
                         +-- NSG / route / firewall
                         +-- DNS resolution
                         +-- TLS hostname verification
                         +-- Managed identity
```

### 22.1. Test cơ bản trên runtime thực tế

1. Đo DNS resolution từ **pod/VM/Function** dùng trong staging.
2. Xác minh endpoint FQDN của SDK phù hợp certificate và private DNS.
3. Xem TCP/TLS connect và service response.
4. Xác minh identity/token/data-plane RBAC.
5. Thử upload/download fixture nhỏ.
6. Xem connection resets, proxy settings, SNAT/NAT pressure khi tải.

### 22.2. Không tắt TLS để pass test

Azurite local thường dùng HTTP mặc định, còn Azure thật dùng HTTPS. **Không** bật “trust all certificates”, tắt hostname verification hoặc hạ TLS trong production profile chỉ vì local emulator hoạt động với HTTP. Nếu emulator dùng HTTPS dev certificate, cô lập truststore vào môi trường test.

### 22.3. Network-denied test

Có thể viết negative test ở staging với một principal/runner **không thuộc network được phép** để xác nhận account firewall từ chối theo policy. Không tùy tiện đổi firewall rules trên resource dùng chung và gây outage; dùng resource riêng và IaC được phê duyệt.

## 23. Data safety: fixture, namespace và cleanup

### 23.1. Fixture phải là synthetic

Không upload invoice thật, production user tokens, medical data hay full logs nhạy cảm vào emulator hoặc test Azure subscription. Tạo bytes/JSON tổng hợp, cấu trúc đủ giống nghiệp vụ để test serialization và encoding.

```json
{
  "orderId": "IT-1042",
  "customerId": "synthetic-customer-7",
  "amount": 150000,
  "currency": "VND",
  "traceId": "integration-test-42"
}
```

### 23.2. Đừng dựa vào clock hiện tại làm khóa duy nhất

Hai tests chạy cùng giây có thể tạo cùng container/key. Dùng **UUID hoặc run ID đủ ngẫu nhiên**, có length/character guard phù hợp tên Azure resource, và giữ namespace một cách rõ ràng trong báo cáo test.

### 23.3. Không xóa trước khi thu failure evidence

Cleanup có thể xóa chứng cứ cần debug. Đối với CI:

- Giữ **logs/test report/trace ID** an toàn.
- Nếu cần giữ test data khi fail, chuyển nó vào test-only artifact storage với TTL và access control.
- Không để container tồn tại vô hạn chỉ vì một assertion thất bại.
- Có policy tránh giữ PII/secrets trong artifact.

### 23.4. Idempotent teardown

`deleteIfExists()` phù hợp hơn `delete()` nếu cleanup có thể chạy lặp. Nếu cleanup network fail, log resource IDs và để janitor xử lý. **Không nuốt mọi cleanup exception rồi tuyên bố leak-free**: test có thể xanh nhưng hóa đơn âm thầm tăng vì resources không được xóa.

### 23.5. Isolation khi shared resource

Resource dùng chung phải hỗ trợ:

```text
account: stsdksharedtest
container: it-run-8f2a...   # thuộc một CI run
blob path: suite-orders/<test-case-id>/...
tags/metadata: owner, runId, expiresAt
```

Nếu queue/table/database không có namespace phù hợp hoặc test cần thay toàn configuration, tạo **resource riêng** thay vì chạy song song vào shared namespace.

## 24. Failure injection: kiểm thử khi SDK gặp lỗi

Một hệ thống chạy tốt khi emulator khỏe chưa chứng minh nó phục hồi đúng khi **HTTP timeout, 429 throttling, 503 service unavailable, network reset hoặc response bị mất sau server-side write**. Cần mô phỏng lỗi ở **tầng thích hợp**.

### 24.1. Inject lỗi ở đâu?

| Điểm inject | Công cụ/kiểu test | Thích hợp |
|---|---|---|
| Business port | Fake `DocumentStore` hoặc Mockito | Validation, fallback và exception mapping |
| HTTP boundary | Local stub/WireMock hoặc custom `HttpClient` test | Error status/headers, request timeout, retry classifier |
| Network | Toxiproxy hoặc network fault tool trong lab | Disconnect, latency, connection reset |
| Emulator service | Stop/restart Azurite container, cấu hình test | Client reconnect và lỗi khi service unavailable |
| Azure real test | Resource policies/controlled throttle khi được phép | RBAC, 429, service-specific behavior |
| Application worker | Kill process ở bước xác định trong staging | Idempotency, checkpoint, duplicate delivery |

Đặt câu hỏi **failure mode nào cần chứng minh**. Nếu chỉ cần kiểm tra mapping lỗi 404 sang `DocumentNotFoundException`, không cần stop container. Nếu muốn biết retry sau mất ACK có gây duplicate billing không, unit test alone không đủ.

### 24.2. Các mã lỗi quan trọng

- **400/InvalidRequest:** payload/schema/headers sai, thường sửa code.
- **401/Authentication:** token/credential không hợp lệ hoặc hết hạn, không retry mù.
- **403/Authorization:** data-plane role, scope, network policy hoặc permission; cần phân tích error code.
- **404/NotFound:** tài nguyên không tồn tại; có thể là business result hoặc lỗi config.
- **409/Conflict:** resource already exists, optimistic concurrency hoặc state conflict tùy API.
- **412/PreconditionFailed:** ETag/If-Match không thỏa; cần refresh state, không overwrite mù.
- **429/TooManyRequests:** throttling; dùng retry policy có backoff và service hints khi hỗ trợ.
- **5xx:** có thể transient, nhưng với **write có side effect** phải xét kết quả chưa rõ.
- **Timeout/connection reset:** phân biệt trước khi gửi request, trong lúc gửi hay sau khi service đã xử lý.

Đây là **mẫu phân loại tổng quát**. Mỗi Azure service có response code, error code, Retry-After và behavior riêng; không tự áp một whitelist cho mọi SDK.

### 24.3. SDK retry không thay business idempotency

Azure SDK thường có retry policy trong HTTP pipeline/service clients. Nhưng nếu request ghi Blob/Queue bị mất ACK, app có thể không biết server đã thực hiện chưa. **Không bật retry vô hạn** cho nghiệp vụ phát sinh chi phí, tạo message hoặc ghi database.

Ví dụ:

```text
Java producer
  |
  | send queue message (businessKey=order-1042)
  v
Azure Queue
  |
  | message đã được accepted
  |
  X response thất lạc
  |
Java nhận timeout, retry send
  |
  v
Queue có thể chứa 2 messages cùng businessKey
```

Giải pháp là **idempotent consumer**, unique business key/inbox store và handling duplicates, không chỉ chỉnh số lần retry của `QueueClient`.

### 24.4. Test retry có deadline

Một policy hợp lý cần:

1. **Max attempts** và **max elapsed time**; không loop vô hạn.
2. Exponential backoff + jitter khi áp dụng.
3. Tôn trọng `Retry-After` khi service trả và API hỗ trợ.
4. Không sleep giữ DB transaction/worker lock không cần thiết.
5. Distinguish idempotent read với non-idempotent write.
6. Cancellation/interruption xử lý đúng khi request bị hủy.
7. Log attempt count/error code/correlation ID mà không lộ credentials.

Test bằng **fake clock/scheduler** cho logic retry; một số integration tests có network fault để xác minh SDK behavior. Không chạy fault load lớn trên tài nguyên Azure dùng chung.

### 24.5. Không assert chi tiết nội bộ SDK quá cứng

Một test “SDK phải retry chính xác 3 lần trong 210ms” dễ vỡ khi nâng SDK/config và bị flakiness do scheduling. Test nên assert **outcome và bounded budget**: số attempts không vượt policy bạn sở hữu, command không chạy duplicate side effect và latency trong tolerance của môi trường.

### 24.6. Fault injection không được làm yếu production TLS

Để test SSL lỗi, dùng một test certificate/truststore tách biệt hoặc stub HTTPS có CA test; không thêm code `trustAllCerts=true` rồi vô tình deploy lên production. Network fault chỉ được inject ở môi trường lab/staging được phê duyệt.

## 25. Async SDK, concurrency và resource lifecycle

Azure SDK for Java có nhiều client types **sync và async**; một số dùng Reactor/Netty và HTTP transport. Kiểm thử phải phù hợp mô hình thread/reactive của ứng dụng.

### 25.1. Một async test cần subscribe và await

Anti-pattern:

```java
// Sai nếu đây là một Mono/Flux lazy:
asyncBlobClient.upload(data, true); // Không subscribe/await.
// Test kết thúc, không có assertion cho kết quả thực.
```

Tùy SDK overload và nguồn `data`, đoạn này là **pseudocode ý tưởng**. Với Reactor publisher, operation thường chỉ chạy khi có subscription; test phải dùng `StepVerifier` hoặc `block(Duration)` trong môi trường test, có timeout để tránh treo.

### 25.2. Ví dụ Reactor test

```java
// Fragment minh họa: client async và Mono<byte[]> do adapter trả.
import reactor.test.StepVerifier;
import java.time.Duration;

StepVerifier.create(documentStoreAsync.get("samples/check.txt"))
        .expectNextMatches(bytes ->
                java.util.Arrays.equals(bytes, expected))
        .expectComplete()
        .verify(Duration.ofSeconds(10));
```

`documentStoreAsync` là adapter **do ứng dụng định nghĩa**, `expected` là fixture. Để chạy cần `reactor-test` ở test dependencies, không giả định `BlobAsyncClient` trực tiếp có method `get(String)` như trên. Giữ reactor callback logic không block event loop và đừng dùng `Thread.sleep` trong reactive pipeline.

### 25.3. Đóng tài nguyên và tắt background threads

Một integration test có thể pass nhưng JVM không thoát vì Reactor schedulers, Event Hubs processor, AMQP receiver, Cosmos client hoặc custom executor còn sống. Thiết kế teardown:

- Stop event processor/receiver đúng lifecycle.
- Dispose subscriptions/cancel in-flight operations.
- Close `CosmosClient`/messaging clients/HTTP resources khi SDK cho phép.
- Chờ graceful shutdown có deadline.
- Kiểm tra thread/resource leaks ở CI khi nhiều suites chạy.

Không tự gọi `System.exit(0)` trong test để che một client không được đóng.

### 25.4. Concurrency test phải có invariant

Ví dụ hai writers cùng đổi Blob có ETag. Test tạo **đồng bộ barrier** để cả hai đọc cùng version, rồi cạnh tranh update:

- Kỳ vọng đúng **một writer** thành công nếu dùng conditional write.
- Writer kia nhận precondition conflict theo contract.
- Blob cuối có một version hợp lệ, không silently lost update.

Không dựa vào `Thread.sleep(10)` để “ép race”, vì CPU/CI scheduling thay đổi sẽ làm test flaky.

### 25.5. Giới hạn concurrency và quotas

Một load test tạo 1000 async requests cùng lúc có thể thất bại do local emulator CPU, Java thread pool hoặc NAT, không phản ánh Azure production throughput. Đo riêng **client-side in-flight, connection pool, request latency, server error/throttling** trước khi quy lỗi cho Azure service.

## 26. Observability: test phải để lại bằng chứng

Một integration test chỉ trả PASS/FAIL khó điều tra khi fail trên CI nhưng pass local. Ghi **diagnostic evidence** đủ để biết đã gọi resource nào, qua identity nào, SDK version nào và request ở giai đoạn nào.

### 26.1. Những trường nên ghi (không chứa secret)

```json
{
  "testSuite": "BlobAzuriteIT",
  "testCase": "shouldUploadAndReadRealBlob",
  "targetKind": "emulator",
  "environment": "ci",
  "sdkComponent": "azure-storage-blob",
  "resourceAlias": "it-run-8f2a",
  "operation": "BlobUploadDownload",
  "result": "PASS",
  "durationMs": 231,
  "traceId": "trace-integration-42"
}
```

Thời gian/alias trong ví dụ là **số giả lập**. Log thêm HTTP error code, sanitized service request ID, retry count và exception class nếu thất bại. **Không** log Shared Key, SAS tokens, bearer tokens, full connection strings hoặc raw PII.

### 26.2. Azure SDK diagnostics

Azure SDK Java có HTTP logging/tracing/metrics integration theo library và configuration. Có thể liên kết với **OpenTelemetry/Application Insights** theo giải pháp được hỗ trợ. Không bật wire-level logging với body/headers không che secrets trong CI có artifacts công khai. Ghi token scopes/audience ở mức cấu hình an toàn, không ghi token value.

### 26.3. Correlation IDs

Một flow:

```text
HTTP request traceId=tr-42
   |
   +-- Upload Blob (client request ID)
   |
   +-- Send Queue Message (business command ID)
   |
   +-- Worker receives (same business ID)
   |
   +-- Insert order status (DB transaction ID)
   |
   +-- Test checks final state
```

Test phải kiểm tra **business correlation ID** được truyền đúng giữa components khi ứng dụng cần audit. Azure service request ID hỗ trợ support/debug, nhưng không thay business command ID.

### 26.4. Metric cho CI integration

| Metric | Ý nghĩa |
|---|---|
| Test pass/fail/skipped per tier | Có nhóm nào âm thầm không chạy? |
| Provision time | Tài nguyên Azure tạo có quá lâu? |
| Emulator startup time | Docker/image/runner issue |
| SDK operation p95 | Latency regression, phân biệt emulator/cloud |
| Auth/RBAC failure count | Identity/role drift |
| Retry count / 429 count | Throttling/capacity issues |
| Cleanup leaked resources | Chi phí và governance |
| Test cost per run | Có vượt budget định trước? |

Không so **Azurite laptop 10ms** với **Azure cloud remote 50ms** rồi kết luận code bị regression. So trên môi trường/region/network và data size tương đồng.

## 27. CI/CD: ba luồng kiểm thử thay vì một job khổng lồ

### 27.1. PR pipeline: unit + emulator

```text
Pull Request
  |
  +-- Compile + lint / SAST / secrets scan
  |
  +-- Unit tests (fake ports / mock)
  |
  +-- Start Testcontainers Azurite
  |
  +-- Emulator IT: Blob/Queue/Table basic contracts
  |
  +-- Publish JUnit reports + sanitized logs
  |
  v
Merge gate
```

Không cần Azure credential production cho PR chạy từ fork/untrusted contributors. GitHub-hosted/self-hosted runner Docker support cần được cấu hình đúng; không trao cloud write permissions cho workflow chạy code chưa review.

### 27.2. Nightly/release pipeline: cloud integration

```text
Trusted branch / scheduled integration job
  |
  +-- Federated CI identity / managed identity login
  |
  +-- Validate non-prod subscription/tenant
  |
  +-- Provision/test RG + resources via IaC
  |
  +-- Assign least-privilege data roles
  |
  +-- Wait for provisioning + RBAC readiness
  |
  +-- Run @Tag("azure") tests with synthetic data
  |
  +-- Run negative RBAC/network tests where approved
  |
  +-- Publish results/metrics and sanitized traces
  |
  +-- Finally: cleanup test resources / report leaks
  |
  v
Release gate
```

Nếu cần OIDC workload federation, cấu hình trust policy giới hạn **repository, environment, branch và principal scope**, tránh client secret tĩnh trong CI. Cloud integration tests phải được trigger từ **trusted code path** có approval phù hợp.

### 27.3. Ví dụ GitHub Actions workflow rút gọn

```yaml
name: java-sdk-tests

on:
  pull_request:

jobs:
  emulator-integration:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: "17"
      - name: Verify unit and Azurite integration
        run: mvn -B verify -P emulator-it
```

Đây là **skeleton**, không hoàn chỉnh nếu dự án chưa định nghĩa Maven profile `emulator-it`, cấu hình Testcontainers và dev key cho Azurite. Cần **pin GitHub Actions/runner dependencies**, quản lý versions và supply-chain policies của tổ chức. Không đánh dấu job này là cloud RBAC verification; nó chỉ chạy nhóm local/emulator.

### 27.4. Fail nếu test bị skip

Một số tests có thể dùng `Assumptions.assumeTrue(...)` để bỏ qua khi Docker không sẵn, nhưng nếu nhóm **emulator integration** là release gate thì skip phải khiến pipeline **FAIL** hoặc report coverage chưa đạt. Kiểm tra JUnit XML report test counts/status, đừng chỉ nhìn exit code của một Maven profile đã vô tình exclude mọi `*IT`.

### 27.5. Tách profile và cấu hình

```text
test profile unit:
  fake DocumentStore

test profile emulator:
  AZURITE_BLOB_CONNECTION_STRING
  AZURE_INTEGRATION_TARGET=emulator

test profile azure:
  AZURE_TEST_STORAGE_ACCOUNT
  AZURE_TEST_SUBSCRIPTION_ID
  AZURE_INTEGRATION_TARGET=azure
  intended workload identity / federated credential
```

Không cho một biến `AZURE_STORAGE_CONNECTION_STRING` chung tùy ý trỏ tới production account nếu profile emulator bị thiếu. Fail fast nếu target không thuộc allowlist, đặc biệt trước mọi destructive test.

### 27.6. Resource janitor

Một job định kỳ theo dõi resources test có tag `owner, runId, createdAt, expiresAt`, đối chiếu active builds rồi **chỉ xóa khi quá TTL và không còn owner active**. Có dry run, approval/canary và audit. Đừng tìm và xóa “tất cả storage accounts tên bắt đầu test” trong một subscription rộng.

## 28. Ước tính chi phí của cloud integration tests

Một resource test Azure có thể phát sinh phí kể cả khi không còn traffic:

| Thành phần | Chi phí tiềm ẩn | Kiểm soát |
|---|---|---|
| Storage account | Dung lượng, read/write transactions, redundancy | Synthetic small fixtures, TTL, LRS nếu đủ mục tiêu |
| Cosmos DB | Provisioned RU/s/serverless requests, storage | Tier phù hợp, auto-cleanup, giới hạn test data |
| Service Bus/Event Hubs | Namespace/tier/capacity, operations | Share có isolation hoặc ephemeral theo khả năng |
| Azure SQL Database | Compute/backup/storage | Chạy theo giờ có kiểm soát, cleanup |
| Network/Private Endpoint | Endpoint, gateway/egress | Chọn scope và region đúng |
| Diagnostics/Application Insights | Log ingestion/retention | Sample/redact, dùng retention ngắn đủ debug |
| Test compute | CI runners, containers, Azure-hosted agents | Chạy nhóm tests có mục đích, không full load mỗi PR |

### 28.1. Cost budget ví dụ

```text
Emulator PR tests:
  no Azure resource charge (vẫn có CI runner cost)

Cloud integration nightly:
  fixed maximum runtime
  small synthetic data size
  per-run resource group / per-run namespace
  monthly budget + forecast alert
  cleanup policy and leak detection

Performance/chaos:
  separate approved environment and explicit budget
```

Không đưa một mức giá cụ thể vì Azure SKU/region và pricing thay đổi. Dùng **Azure Pricing Calculator, Cost Management và actual resource usage** để tính.

### 28.2. “Free tier” không có nghĩa không cần cleanup

Một số dịch vụ có free tier/emulator mode nhưng phụ thuộc hạn mức, account và điều kiện. Network egress, logs, storage hoặc resources khác vẫn có thể tính phí. Nhóm test phải báo **total cost of ownership** thay vì nhìn duy nhất một SKU “free”.

### 28.3. Chọn test giá trị cao

Một cloud test **Blob upload + read + RBAC deny** nhỏ có thể phát hiện lỗi quan trọng hơn 10.000 mock tests cho SDK builder. Ưu tiên test những boundary khác biệt giữa emulator và Azure: IAM, networking, tier-specific behavior, quotas và persistence/consistency thật.

## 29. Case study: hệ thống nạp đơn hàng sử dụng Blob và Queue

### 29.1. Yêu cầu

Ứng dụng Java:

1. Nhận `POST /orders/{id}/receipt` với synthetic PDF/document bytes.
2. Ghi Blob `receipts/{orderId}/{contentHash}`.
3. Gửi Queue message yêu cầu worker kiểm tra và index chứng từ.
4. Worker đọc Blob, kiểm tra checksum, cập nhật business result store.
5. API cho phép tra cứu trạng thái `PENDING / PROCESSED / FAILED`.

Đội muốn chạy PR tests nhanh bằng Azurite, đồng thời bảo đảm release không lỗi IAM/Private Endpoint trên Azure.

### 29.2. Kiến trúc test

```text
                 JUnit 5 test
                     |
          synthetic receipt + orderId
                     |
                     v
             Java OrderIngestion
                     |
             +-------+--------+
             |                |
             v                v
      AzureBlobDocumentStore  QueueWorkPublisher
             |                |
             +--------+-------+
                      |
          Azurite Blob + Queue (PR)
              OR Azure Storage test (cloud)
                      |
                      v
              OrderReceiptWorker
                      |
             idempotent result store
                      |
                      v
           JUnit assert final business state
```

### 29.3. Các business invariants

| Invariant | Cách kiểm tra |
|---|---|
| Blob chứa đúng tài liệu gửi lên | Read-back + hash/byte comparison |
| Một logical order không bị index hai lần | Unique `orderId + documentVersion` trong result store |
| Queue message chứa key đúng | Parse actual message từ Azure Queue/SDK |
| Worker lỗi giữa process và delete không làm trùng | Idempotent worker + replay test |
| Error không làm mất command | Business command/outbox store hoặc recovery design |
| Test không để lại data | Mỗi run dùng container/queue namespace riêng và cleanup |
| Cloud identity đúng scope | Data-plane allow/deny tests trên test resource |

### 29.4. Thiết kế idempotency

Nếu API upload Blob thành công nhưng gửi Queue thất bại, cần **durable workflow** ghi nhận pending work và retry publishing. Nếu gửi Queue thành công nhưng HTTP response bị mất, producer có thể gửi lại cùng message. **Một Blob write và một Queue send không tự tạo giao dịch nguyên tử**.

Một thiết kế có thể dùng database/outbox:

```text
DB transaction: create order + outbox event
    |
    v
Dispatcher uploads Blob / sends queue with stable business ID
    |
    v
Worker processes idempotently with inbox/unique key
    |
    v
Complete Queue message after business commit
```

Tùy yêu cầu, có thể thay đổi thứ tự Blob upload/DB transaction, nhưng cần xác định **orphan Blob cleanup, retry, reconciliation và unknown outcome**. Không gắn nhãn exactly-once cho toàn workflow chỉ vì worker có delete message.

### 29.5. Bộ integration tests cụ thể

| Test | Emulator | Cloud test |
|---|---|---|
| Upload/download receipt bytes | Mỗi PR | Smoke |
| Queue publish/read/delete | Mỗi PR | Smoke |
| Duplicate message không duplicate status | Mỗi PR | Theo release |
| Missing blob → worker failure/compensation | Mỗi PR | Theo release |
| Blob ETag concurrency | Emulator | Có nếu business cần |
| Queue visibility timeout/re-delivery | Một test ngắn | Có nếu service semantics critical |
| Managed identity + RBAC | Không | **Bắt buộc** |
| Private Endpoint/DNS/TLS | Không | **Bắt buộc trong staging topology** |
| Quota/throttling/scale | Giả lập một phần | Dedicated test |
| Cleanup/tag/cost guard | Local/container | **Bắt buộc** |

### 29.6. Test thật phải kiểm tra cuối workflow

Một test end-to-end phù hợp:

```text
Arrange:
  create unique container + queue + orderId;
  synthetic file; start test worker;

Act:
  API ingests document;

Assert:
  actual Blob bytes and metadata match;
  worker processed message;
  result store has one logical result;
  no duplicate side effect after message replay;

Finally:
  stop worker and close clients;
  delete only resources owned by this run;
  record cleanup result.
```

Kết quả business state có thể là **eventually observable** do worker xử lý bất đồng bộ; test nên **poll đến deadline** thay vì `Thread.sleep(5000)` rồi đoán worker đã chạy.

### 29.7. Test để lộ lỗi thật

Giả sử code dùng Blob client khởi tạo với connection string `UseDevelopmentStorage=true` (hoặc tương đương local) ngay trong service, được inject khi unit test nhưng **không đổi sang token credential trong staging**. PR emulator tests xanh, cloud test thất bại 401/403 hoặc kết nối nhầm local endpoint. Kiến trúc dependency injection và test resource sẽ phát hiện mismatch này trước production.

## 30. Deterministic tests: chống flaky trong distributed systems

### 30.1. Tránh sleep cứng

Anti-pattern:

```java
sendQueueMessage();
Thread.sleep(3000);
assertEquals("PROCESSED", repository.getStatus(orderId));
```

Nếu runner CPU chậm, test fail; nếu worker lỗi nhưng sau đúng 3 giây vẫn không xử lý, thông tin lỗi mơ hồ. Tốt hơn dùng **polling có thời hạn**, log trạng thái cuối và khoảng thời gian:

```java
import java.time.Duration;
import java.time.Instant;

Instant deadline = Instant.now().plus(Duration.ofSeconds(15));
String status;

do {
    status = repository.getStatus(orderId);
    if ("PROCESSED".equals(status)) break;
    Thread.sleep(100);
} while (Instant.now().isBefore(deadline));

assertEquals("PROCESSED", status,
        "Worker did not finish within test deadline");
```

Đây là **code fragment** giả định `repository` và `orderId` tồn tại, method cho phép `InterruptedException`. Với production test harness, dùng Awaitility/StepVerifier hoặc helper polling tôn trọng interruption và request budget. Chỉ dùng polling cho **eventual behavior**; với Blob Storage read-after-write có strong consistency theo service semantics, đừng sleep vô lý để che một bug.

### 30.2. Dùng Awaitility khi phù hợp

Một helper Awaitility (nếu đã thêm test dependency):

```java
await()
    .atMost(Duration.ofSeconds(15))
    .pollInterval(Duration.ofMillis(100))
    .untilAsserted(() ->
        assertEquals("PROCESSED", repository.getStatus(orderId)));
```

`await()` thuộc Awaitility library, không phải JUnit 5 core. Test phải đưa dependency/version phù hợp và đảm bảo query side effect không tốn kém. Deadline phải đủ cho môi trường cloud được xác định nhưng không kéo dài vô hạn.

### 30.3. Không chia sẻ thứ tự test

Một suite dễ flaky:

```text
Test A creates queue
Test B reads Test A's message
Test C deletes queue
```

JUnit không bảo đảm thứ tự mặc định mà một bài test nên phụ thuộc. Gộp thành **một test scenario tự chứa** hoặc cấp resources riêng cho mỗi test; nếu cần sequence workflow, định nghĩa sequence bên trong test và ghi assert từng bước.

### 30.4. Nondeterministic IDs/clock

Random names giúp tránh collision nhưng làm debug khó nếu không ghi run ID. Ghi **test ID, resource alias, trace ID** nhưng che secrets. Clock giả hữu ích cho unit retry/TTL; test thực cần xác minh server/client clocks và timeout tolerance.

### 30.5. Network flakiness

Một cloud test thất bại một lần do mạng không nên tự động rerun 10 lần cho tới xanh rồi bỏ qua bằng chứng. Phân loại transient, retry trong budget và thống kê **flaky rate**. Một test chỉ pass sau 5 retries là dấu hiệu cần điều tra, không phải “ổn định”.

## 31. Troubleshooting: phân biệt lỗi emulator, SDK và Azure thật

| Triệu chứng | Nguyên nhân thường gặp | Kiểm tra đúng |
|---|---|---|
| `Connection refused 127.0.0.1:10000` | Azurite chưa chạy, port mapping sai | Docker logs, bind địa chỉ/cổng, Testcontainers mapped port |
| `AuthenticationFailed` trên Azurite | Sai dev key/account name, malformed connection string | So khớp account config/local key và endpoint |
| `UnsupportedApiVersion` | SDK mới hơn emulator feature support | Pin/nâng emulator hoặc cloud feature test |
| Docker image không pull được | Registry/proxy/network/pinning | Image reference, runner network, image digest |
| Testcontainers không thấy Docker | Runner thiếu daemon/permission | Docker runtime access, CI config |
| `SSLHandshakeException` Cosmos Emulator | Dev certificate/truststore | Test-only CA/truststore; không trust-all production |
| Azure Blob 401 | Token invalid/audience/tenant issue | Credential chain/principal/token config đã che secret |
| Azure Blob 403 | Data-plane RBAC, firewall/policy hoặc khác | Azure error code, role/scope, network/firewall |
| Blob cloud 404 ngay sau write | Sai account/container/key/version/path hoặc request lỗi | Inspect actual SDK endpoint/path/correlation, không sleep mù |
| Azure Queue message “mất” | Bị invisible, expired, consumed/deleted | Visibility timeout, TTL, pop receipt, workers |
| Service Bus message duplicate | Receiver crashed before settlement | Idempotency store, lock expiry/renewal, delivery count |
| Cosmos query cost cao trên cloud | Cross-partition/indexing/RU khác emulator | Partition keys, query metrics, RU consumed |
| CI cloud test “pass” bằng user cá nhân | DefaultAzureCredential chọn Azure CLI/IDE identity | Assert actual principal/client/tenant, use federated identity |
| Cleanup fail, tài nguyên tồn tại | Runner bị kill, thiếu delete role, resource lock | Run ID manifest, janitor policy, owner and scope |
| Test fail ngẫu nhiên khi song song | Shared container/queue/key, hard-coded names | Unique namespace, isolation, barrier synchronization |
| Emulator test pass nhưng staging fail | RBAC, Private Link, API feature, quota không được mô phỏng | Cloud integration matrix, network/auth diagnostics |

### 31.1. Không đổi mọi cấu hình cùng lúc

Khi test Blob cloud fail `403`, đừng đồng thời mở public network, tắt TLS, cấp Subscription Owner và thay SDK version. Làm vậy vừa nguy hiểm vừa mất khả năng xác định nguyên nhân. Kiểm tra **identity → data-plane role → resource scope → firewall/Private Endpoint → SDK endpoint** theo thứ tự dựa trên lỗi.

### 31.2. Phân biệt HTTP 403 với network timeout

Nếu request nhận **HTTP response 403 từ Azure service**, kết nối TLS tới service có thể đã hoạt động; còn `ConnectTimeout` chưa chứng minh role sai. Nhưng một số service trả 403 khi **network ACL deny** hoặc policy khác, nên phải xem **service error code và logs** chứ không kết luận từ status đơn lẻ.

### 31.3. Debug credential chain

Với `DefaultAzureCredential`, developer laptop có thể dùng Azure CLI user không phải intended workload identity. Trong CI production-like, cần explicit credential selection/managed identity nếu phù hợp, log **principal ID/tenant ID ở mức không bí mật**, và xác minh RBAC. Không ghi bearer token hoặc token claims chứa dữ liệu nhạy cảm vào console CI.

### 31.4. Debug Azurite shared account

Azurite có built-in dev account và có thể hỗ trợ custom account configuration. Nếu key/account bạn cấu hình không khớp server, SDK sẽ báo authentication error. Đừng đổi code production Shared Key signing logic để phục vụ một emulator setup sai; sửa **test environment**.

## 32. Runbooks: xử lý sự cố integration pipeline

### 32.1. Runbook A – Toàn bộ emulator tests fail sau upgrade

1. Xem phiên bản Azure SDK BOM, Azurite image tag và JDK/CI runner vừa thay.
2. Đọc exception: unsupported API version hay connection refused/auth?
3. Kiểm tra Docker/port mapping/healthcheck.
4. Chạy một minimal Blob round-trip cùng image pinned.
5. Kiểm tra breaking changes trong SDK/emulator release notes phù hợp.
6. Sửa compatibility hoặc pin version đã kiểm thử, không dùng loose mode làm release proof.
7. Chạy lại full emulator suite và giữ incident evidence.
8. Xem có cloud test cần bổ sung cho feature chưa được emulator hỗ trợ.

**Không xóa bỏ hàng loạt assertions** chỉ để pipeline xanh sau nâng version.

### 32.2. Runbook B – Cloud IT thất bại 401/403

1. Xác nhận non-prod subscription/resource ID/tenant.
2. Xác minh principal thực tế của runner/pod, không chỉ credential type kỳ vọng.
3. Kiểm tra Storage data-plane RBAC role/scope và propagation.
4. Xem endpoint/TLS/network path, firewall/private endpoint deny.
5. So sánh emulator code path và cloud code path có nhầm connection string hay không.
6. Xem sanitized Azure service error code/correlation ID.
7. Sửa least-privilege role/network hoặc credential chain; không cấp Owner tùy tiện.
8. Re-run target cloud test, negative RBAC tests và cleanup.

**Không đưa Azure account key vào CI chỉ để tránh sửa managed identity** nếu mục tiêu test là Entra/RBAC.

### 32.3. Runbook C – Tài nguyên test còn tồn tại sau CI

1. Lấy provision manifest: run ID, RG, subscription, createdAt.
2. Xác minh build đã kết thúc thật, không có job song song còn cần resource.
3. Kiểm tra cleanup logs, resource locks, RBAC, network/IaC state.
4. Tạo dry-run report những resources do job sở hữu.
5. Xóa đúng RG/resource có owner và TTL hợp lệ, có audit.
6. Thống kê cost/leak count và sửa `finally`/post-job workflow.
7. Không tự xóa RG shared staging hoặc của run khác.

### 32.4. Runbook D – Queue worker xử lý hai lần

1. Kiểm tra message ID, business key, dequeue count và timeline.
2. Xem worker có crash sau DB write trước queue delete/settlement.
3. Xác minh queue visibility timeout/lock renewal và retry behavior.
4. Thêm/kiểm tra inbox/unique business key ở data store.
5. Unit test idempotency, emulator test duplicate delivery, cloud test nhỏ nếu cần.
6. Đối soát các side effects đã xảy ra, có compensation khi thích hợp.
7. Không tìm cách “tắt tất cả retries” để che invariant thiếu.

### 32.5. Runbook E – Cloud IT chậm và tốn tiền

1. Phân tách provision time, RBAC propagation, test operation time và cleanup time.
2. Xem test có tạo resource có phí giờ dù không dùng không.
3. Điều tra data size, repeated retries, unnecessary full scans và logs volume.
4. Chuyển basic CRUD tests về emulator, giữ cloud test cho feature gaps.
5. Tối ưu shared test resources có isolation nếu phù hợp.
6. Dùng schedules/auto-stop/TTL resources khi dịch vụ hỗ trợ.
7. Ghi baseline duration/cost, đặt budget alert và cleanup metrics.

## 33. Tích hợp với Spring Boot test profile

Đối với Spring Boot, nên tạo **client bean** theo profile để business service không tự biết Azurite/cloud endpoint. Một integration test có thể dùng Testcontainers và cấu hình app context thông qua `@DynamicPropertySource`.

### 33.1. Client configuration

```java
import com.azure.storage.blob.BlobContainerClient;
import com.azure.storage.blob.BlobServiceClient;
import com.azure.storage.blob.BlobServiceClientBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration
@Profile("emulator")
public class AzuriteBlobConfig {

    @Bean
    public BlobServiceClient blobServiceClient(
            @Value("${storage.emulator.connection-string}") String cs) {
        return new BlobServiceClientBuilder()
                .connectionString(cs)
                .buildClient();
    }
}
```

Đây là Spring Boot/Spring Framework bean setup khi project đã có `spring-boot-starter` và Azure Blob dependency. Để áp dụng port `DocumentStore`, tạo bean adapter với test-owned container name được cấp từ run ID. Không tạo production connection string bằng phép nối keys bên trong Spring config.

### 33.2. Cloud config tách riêng

```java
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.storage.blob.BlobServiceClient;
import com.azure.storage.blob.BlobServiceClientBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration
@Profile({"azure-test", "production"})
public class AzureBlobConfig {

    @Bean
    public BlobServiceClient blobServiceClient(
            @Value("${storage.azure.endpoint}") String endpoint) {
        return new BlobServiceClientBuilder()
                .endpoint(endpoint)
                .credential(new DefaultAzureCredentialBuilder().build())
                .buildClient();
    }
}
```

Trong production, cần xác định **credential chain được phép** và endpoint qua centrally validated configuration; dùng managed/workload identity nếu phù hợp. Hai profiles tách connection modes; application code chung dùng `BlobServiceClient`/`DocumentStore`.

### 33.3. DynamicPropertySource với Testcontainers

```java
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

// Fragment trong class @SpringBootTest @ActiveProfiles("emulator")
// có @Container AZURITE đã được cấu hình như phần 9.

@DynamicPropertySource
static void emulatorProperties(DynamicPropertyRegistry registry) {
    registry.add("storage.emulator.connection-string", () -> {
        String key = System.getenv("AZURITE_DEV_ACCOUNT_KEY");
        if (key == null) {
            throw new IllegalStateException("Missing Azurite dev key");
        }
        String endpoint = "http://" + AZURITE.getHost() + ":"
                + AZURITE.getMappedPort(10000) + "/devstoreaccount1";
        return "DefaultEndpointsProtocol=http;"
                + "AccountName=devstoreaccount1;AccountKey=" + key
                + ";BlobEndpoint=" + endpoint + ";";
    });
}
```

**Đây là fragment**, cần Spring Test dependencies, imports Testcontainers, Test class annotations và chính class config. Nếu resource có nhiều clients/services, inject những endpoints tương ứng. Cần bảo đảm Testcontainers **đã startup trước khi framework tạo client sử dụng property** theo JUnit/Spring integration lifecycle được cấu hình.

### 33.4. Spring `@MockBean`/bean override không đủ cho integration

Nếu test Spring Boot nhưng thay `BlobServiceClient` bằng mock, nó vẫn chủ yếu là unit/component test. Một integration test cần dùng **bean thật kết nối emulator hoặc Azure test** để kiểm tra HTTP operations, serialization và backend behavior. Cả hai loại test đều hữu ích, chỉ không được gán nhãn sai.

### 33.5. Đánh dấu profiles trong test report

Mỗi test suite nên ghi rõ:

```text
Test suite: OrderIngestionIT
Spring profile: emulator
Target kind: Azurite
Blob SDK version: project BOM-resolved
Testcontainer image: pinned digest/tag
Azure cloud RBAC test: NOT RUN in this suite
```

Điều này giúp reviewer không hiểu nhầm một local test đã xác minh identity/network production.

## 34. Ma trận nghiệm thu và release gates

Trước khi thông báo Azure SDK integration “ready”, có thể dùng ma trận:

| Hành vi | Unit | Emulator | Azure test | Bắt buộc release? |
|---|---|---|---|---|
| Validate order request | PASS | Không cần | Không cần | Có |
| Blob upload/download bytes | Fake/business test | PASS | PASS smoke | Có |
| Blob metadata/content type | Test mapping | PASS | PASS nếu critical | Tùy use case |
| Blob ETag conflict | Test classifier | PASS | PASS nếu concurrent writes | Tùy use case |
| Blob missing 404 | PASS | PASS | Spot check | Có |
| Queue send/receive/delete | Test state machine | PASS | PASS smoke | Có |
| Queue duplicate delivery | PASS idempotency | PASS | PASS nếu critical | Có |
| Cosmos partition key | Test repository | PASS trong emulator hỗ trợ | PASS nếu dùng Cosmos | Có nếu critical |
| Event Hubs checkpoint resume | Test checkpoint policy | PASS nếu emulator hỗ trợ | PASS | Có nếu dùng feature |
| Service Bus session/DLQ | Test state logic | Tùy emulator | PASS | Có nếu dùng feature |
| Entra ID token/tenant | Fake chain config | Không chứng minh | PASS | **Có** |
| Azure RBAC allow/deny | Policy/business test | Không chứng minh | PASS | **Có** |
| Private Endpoint/TLS | Test config | Không chứng minh | PASS trên staging runner | **Có nếu production dùng** |
| Throttling/retry budget | Unit policy | Inject/partial | Controlled cloud test | Có |
| Cleanup/leak policy | Test generator | PASS | PASS | Có |
| Cost budget/alerts | Test config | Không | Actual cloud usage | Có với cloud IT |

**PASS nếu feature thực sự được sử dụng.** Không bắt một dự án chỉ dùng Blob Storage phải chạy Service Bus/IoT Hub tests. Nhưng nếu ứng dụng dùng một capability không được emulator hỗ trợ, **không bỏ hàng “Azure test” khỏi ma trận để báo xanh**.

### 34.1. Một release gate nên kết luận gì?

```text
UNIT=PASS
EMULATOR_BLOB=PASS
EMULATOR_QUEUE=PASS
CLOUD_BLOB_AUTH=PASS
CLOUD_RBAC_NEGATIVE=PASS
CLOUD_PRIVATE_ENDPOINT=PASS
CLOUD_RESOURCE_CLEANUP=PASS
SKIPPED_CRITICAL_TESTS=0
BLOCKERS=NONE
```

Đây là format báo cáo **minh họa**, không phải output mặc định của một công cụ. Quan trọng là tách rõ **tested** và **not tested** theo môi trường.

### 34.2. Fail criteria

Release phải dừng khi:

- Test dùng sai subscription hoặc resource không nằm trong allowlist.
- Principal thực tế không khớp identity kỳ vọng.
- Critical cloud test bị skip vì credentials/Docker không sẵn.
- Có unit/emulator/cloud test thất bại nhưng pipeline ignore exit code.
- Test CRUD pass nhưng cleanup delete nhầm hoặc có resource leak nghiêm trọng.
- Có evidence dữ liệu production/PII bị đẩy vào test environment.
- Feature production chỉ được mock, chưa có cloud verification phù hợp.

### 34.3. Không đo “coverage” chỉ theo số test

1000 mocked SDK builder tests không thay thế một test real data-plane RBAC. Đánh giá coverage theo **failure modes, boundaries, IAM, network, data invariants và cost**, không chỉ statement/branch code coverage.

## 35. Bài tập thực hành

### Bài tập A – Blob round-trip với Azurite

**Đề bài:** triển khai `DocumentStore` từ phần 4, chạy Azurite local, tạo một JUnit test upload `receipt-1042.json` rồi download và so bytes.

**Yêu cầu:** container unique, UTF-8 fixture, thử Blob không tồn tại, cleanup trong `@AfterEach`.

**Tiêu chí đạt:** test gọi **SDK thực qua HTTP**, không dùng mock BlobClient; fail nếu Azurite chưa chạy.

### Bài tập B – Testcontainers dynamic ports

Chuyển test A sang Testcontainers. Không hard-code host port 10000, chỉ dùng `AZURITE.getMappedPort(10000)` và `getHost()`. Pin image version/digest đã kiểm thử.

**Tiêu chí đạt:** hai CI runs khác nhau không đụng local port/container name; test không phụ thuộc một Azurite do developer bật thủ công.

### Bài tập C – Negative test 404/409/412

Thêm tests:

1. Download missing Blob → assert service exception status.
2. Upload duplicate key without overwrite → conflict đúng contract.
3. ETag conditional write với stale ETag → precondition failure.

**Tiêu chí đạt:** test chứng minh HTTP conditional semantics; không tự build fake exception.

### Bài tập D – Queue visibility timeout và duplicate

Gửi message `job-1042`; worker nhận nhưng giả lập crash trước delete, sau timeout nhận lại và chạy handler idempotent.

**Yêu cầu:** business result store chỉ có một record theo stable job ID. Test cũng kiểm tra queue delete đúng pop receipt.

**Tiêu chí đạt:** duplicate message không tạo duplicate business effect.

### Bài tập E – Cosmos DB Emulator

Tạo container `orders` với partition key `/tenantId` trên Cosmos emulator tương thích:

- Insert hai synthetic tenants.
- Đọc item bằng đúng partition key.
- Thử wrong partition key.
- Kiểm tra ETag/conflict.
- Ghi rõ những gì **không** thể kết luận về RU, autoscale, region failover.

**Tiêu chí đạt:** test thật qua Cosmos SDK, tự tạo/xóa resources; không dùng tài khoản Azure production.

### Bài tập F – IAM/RBAC trên Azure Storage test

Trong non-prod subscription, tạo storage account riêng. Cho một managed/service test identity quyền **Storage Blob Data Contributor**, một identity khác chỉ có **Storage Blob Data Reader**.

**Nhiệm vụ:** test upload/read cho writer; read success + write denied cho reader; verify principal IDs và scope, không dùng account key.

**Tiêu chí đạt:** test phân biệt RBAC 403 với lỗi network/credential và cleanup account.

### Bài tập G – Private Endpoint

Giả sử Azure Blob account chỉ cho private network. Laptop developer không truy cập, nhưng AKS staging có VNet integration.

**Nhiệm vụ:** thiết kế test chạy từ đúng pod/runner; kiểm tra DNS FQDN, TLS, identity và Blob CRUD. Giải thích vì sao Azurite test local không xác minh điều này.

**Tiêu chí đạt:** không mở public access/tắt TLS; kết nối thành công từ đúng network path hoặc ghi blocker đúng.

### Bài tập H – Flaky CI

Một integration test gọi Queue send rồi `Thread.sleep(1000)` chờ worker, local pass nhưng CI fail ngẫu nhiên.

**Nhiệm vụ:** thay bằng polling/Awaitility deadline, unique job ID, business outcome assertion và diagnostics. Tách resource cleanup và retry logic.

**Tiêu chí đạt:** test không phụ thuộc arbitrary delay, khi fail có event trace.

### Bài tập I – SDK upgrade

Nâng một Azure SDK BOM version. Azurite test bắt đầu báo `UnsupportedApiVersion`, nhưng cloud test vẫn pass.

**Nhiệm vụ:** phân loại lỗi compatibility giữa emulator/API version, chọn pin/nâng emulator có kiểm thử hoặc tách feature test sang cloud. Không disable assertions hay hạ security flags tùy tiện.

**Tiêu chí đạt:** report ghi rõ emulator gap và Azure contract validation.

### Bài tập J – Cleanup governance

Một CI job bị hủy sau khi tạo test RG nhưng trước cleanup, resource còn lại 7 ngày.

**Nhiệm vụ:** thiết kế manifest run ID/subscription/owner/timestamp, `finally`, janitor TTL, dry-run và RBAC scope; không xóa resource đang dùng bởi job khác.

**Tiêu chí đạt:** kiểm soát resource leaks và chi phí mà không mở quyền xóa production.

### Bài tập K – Test phạm vi Service Bus

Ứng dụng sử dụng Service Bus sessions và dead-letter processing. Emulator version đang dùng chưa hỗ trợ đầy đủ một tính năng.

**Nhiệm vụ:** lập ma trận unit/stub/emulator/cloud; chọn test nào chạy mỗi PR, test nào nightly/release, mô tả giới hạn không được giả định.

**Tiêu chí đạt:** không đánh dấu session semantics verified chỉ bằng một Queue Storage/Azurite test.

### Bài tập L – End-to-end order ingestion

Tạo `OrderIngestionIT` từ case study phần 29:

- Upload synthetic document lên Blob.
- Send message với stable order ID.
- Worker đọc blob và ghi result.
- Assert final business state, retry duplicate không tăng kết quả.
- Force một lỗi giữa DB commit và queue delete.
- Cleanup/test resource manifest, ghi cost và traces.

**Tiêu chí đạt:** cùng business logic chạy trên emulator PR và cloud test account, chỉ khác **endpoint + credentials + profiles**; không chạm production.

## 36. Câu hỏi tự kiểm tra

**1. Integration test khác unit test ở đâu?** Integration test đi qua ranh giới tích hợp thật như SDK HTTP, emulator hoặc Azure resource; unit test có thể dùng fake/mock để kiểm tra logic riêng.

**2. Vì sao một mock `BlobClient.upload()` không chứng minh Azure Storage hoạt động?** Nó không thực sự serialize HTTP request, ký xác thực, gọi service hay đọc lại bytes.

**3. Azurite mô phỏng những Azure Storage services nào?** Thường là Blob, Queue và Table trong phạm vi tính năng/version được hỗ trợ.

**4. Azurite có kiểm tra Entra RBAC/managed identity production không?** Không theo cùng semantics với Azure thật; cần cloud test.

**5. Vì sao dùng dynamic port từ Testcontainers?** Để tránh xung đột host port và phù hợp Docker/CI networking.

**6. Development account `devstoreaccount1` có phải credential production không?** Không; đó là test account/key well-known của emulator, không dùng cho Azure thật.

**7. Vì sao không dùng `latest` cho emulator CI lâu dài?** Image thay đổi có thể làm tests không reproducible hoặc thay feature/API version mà không review.

**8. Một Blob round-trip test cần assert gì?** Tạo container, upload bytes, read/download và so nội dung, xử lý lỗi, cleanup resource đúng ownership.

**9. Vì sao test 404 từ SDK thực có giá trị hơn mock exception?** Nó xác minh SDK/service error serialization và exception mapping qua HTTP.

**10. Test ETag concurrency chứng minh điều gì?** Conditional write ngăn stale writer ghi đè thay đổi mới theo service/API semantics.

**11. `QueueClient.receiveMessages()` có nghĩa message được xóa khỏi queue chưa?** Không; thường cần delete với message ID + pop receipt sau xử lý.

**12. Vì sao Queue có thể giao lại message?** Visibility timeout hoặc lỗi trước delete, dẫn tới retry/duplicate delivery.

**13. Exactly-once business processing có được đảm bảo chỉ bằng Queue send/delete không?** Không. Cần idempotent consumer và durable business keys/inbox.

**14. Cosmos DB emulator có cho ước lượng RU/s chính xác production không?** Không. Cần cloud account/test metrics trên tier thực.

**15. Cosmos DB Gateway vs Direct mode có thể quan trọng vì sao?** Network/port/firewall/client behavior khác; cần test mode định deploy.

**16. Service Bus và Event Hubs emulator có thay nhau được không?** Không. Service Bus queues/topics/settlement và Event Hubs streams/checkpoints có semantics khác.

**17. Functions Core Tools có mô phỏng Azure Functions scaling/managed identity đầy đủ không?** Không; test local bindings và function code, còn cloud hosting/network/identity cần staging.

**18. `DefaultAzureCredential` có thể dùng identity nào trên laptop?** Có thể chọn Azure CLI/IDE credential theo chain/config, không bảo đảm đó là managed identity dự kiến.

**19. Vì sao management-plane Contributor chưa chắc được upload Blob?** Data-plane storage permissions/RBAC là quyền riêng.

**20. Cloud test account nên đặt ở đâu?** Trong non-prod subscription/resource group với allowlist, ownership, least privilege và cleanup.

**21. Tại sao không dùng production storage account có container tên `test`?** Vẫn ảnh hưởng billing/quota/policy và có rủi ro xóa/ghi dữ liệu nhầm.

**22. Nếu Azure test 403, nên kiểm tra gì?** Principal, tenant, role/scope, propagation, firewall/Private Endpoint và service error code; không tự cấp Owner.

**23. Azurite local HTTP có cho phép vô hiệu hóa TLS trên Azure thật không?** Không. Azure production cần HTTPS/certificate validation theo policy.

**24. Khi unit test timeout policy, vì sao inject fake clock?** Tránh chờ thật, kiểm thử edge cases và retry deadline một cách deterministic.

**25. Vì sao retry Queue send sau timeout có thể tạo duplicate?** Server có thể đã accepted message nhưng response thất lạc; lần gửi lại tạo message thứ hai.

**26. Một Testcontainers test pass có bảo đảm AKS Private Endpoint hoạt động không?** Không; phải test từ đúng workload/network trên Azure.

**27. Một test dùng `@SpringBootTest` và `@MockBean BlobClient` có là cloud integration không?** Không; nó chưa gọi Azure/SDK service thật.

**28. Dữ liệu fixture nên lấy từ đâu?** Synthetic/generated test data; không copy production PII/secret vào test environments.

**29. Vì sao cần unique container/key cho mỗi test?** Tránh collisions và phụ thuộc vào thứ tự test khi chạy song song.

**30. Cleanup chỉ dùng tên prefix có đủ an toàn không?** Không; cần owner/run ID/resource manifest/scope và xác minh resource thuộc test.

**31. CI release có thể báo PASS nếu mọi integration test đều skipped không?** Không. Critical skipped tests phải được coi là thiếu coverage/fail gate.

**32. Một Azure cloud test có thể bị flaky vì gì?** Network, RBAC propagation, noisy neighbor, quota, test namespace collision, hard sleep hoặc cleanup racing.

**33. Blob Storage có cần sleep tùy tiện sau write để read-after-write không?** Không theo strong consistency của Blob data plane; nếu 404 phải kiểm tra path/account/version/request outcome.

**34. Azure SDK retry có tự giải quyết business idempotency không?** Không. Phải thiết kế stable business key và xử lý unknown outcome.

**35. Metrics nào giúp điều tra CI cloud test chậm?** Provision time, RBAC readiness, SDK call latency/retries, throttling, cleanup time và resource cost.

**36. Có nên chạy heavy chaos/performance test trên resource Azure shared staging mỗi PR không?** Không. Tách môi trường, lịch, phê duyệt và budget.

**37. “Emulator PASS, Azure NOT RUN” nghĩa gì?** Đã kiểm tra basic SDK behavior tại local; cloud-specific IAM/network/tier/features chưa được xác minh.

**38. Điều kiện quan trọng nhất trước release là gì?** Những integration boundaries thực sự dùng được test ở tầng phù hợp, cloud identity/network đúng, data invariants giữ nguyên và cleanup/chi phí có kiểm soát.

## 37. Checklist triển khai kiểm thử Azure SDK Java

### 37.1. Kiến trúc và dependency

- [ ] Business code tách khỏi Azure SDK adapters qua interface/port rõ ràng.
- [ ] SDK clients tạo một lần theo cấu hình và được inject, không tạo per-request.
- [ ] Java/JDK, Azure SDK BOM, emulator image và Testcontainers versions được pin/kiểm thử.
- [ ] Unit tests dùng fake/mock để kiểm tra business rules, validation, timeout và retry classifier.
- [ ] Emulator tests gọi SDK thật qua endpoint/protocol, không chỉ mock.
- [ ] Cloud tests kiểm chứng feature gaps và Azure-specific behavior.
- [ ] Profiles/targets `unit`, `emulator`, `azure` và `production` được tách rõ.
- [ ] Test report ghi rõ tầng nào đã chạy và các trường hợp bị skip.

### 37.2. Azurite và Testcontainers

- [ ] Docker/Testcontainers availability đã được kiểm tra ở runner.
- [ ] Azurite image pin tag/digest và tương thích service API version.
- [ ] Dev account/key chỉ dùng local, không phải credential production.
- [ ] Endpoint dùng `getMappedPort`/`getHost` nếu container map dynamic ports.
- [ ] Unit/emulator test fixtures không chứa production PII/secrets.
- [ ] Blob test assert upload/download content, missing 404, metadata và cleanup.
- [ ] Queue test assert send/receive/delete, visibility timeout và duplicate processing.
- [ ] Table test kiểm tra PartitionKey/RowKey, ETag và query nếu dùng.
- [ ] Không dùng emulator để tuyên bố Azure RBAC, geo-DR hoặc network production verified.
- [ ] Có error message rõ nếu Docker/emulator chưa khởi động; CI không bỏ qua test âm thầm.

### 37.3. Cosmos/messaging/Functions khi sử dụng

- [ ] Đã đọc/ghi nhận feature matrix của đúng Cosmos/Service Bus/Event Hubs emulator version.
- [ ] Cosmos emulator có HTTPS test certificate/truststore riêng, không trust-all production.
- [ ] Cosmos cloud test đo partition key/index/RU/quota khi performance là yêu cầu.
- [ ] Service Bus tests bao gồm settlement/duplicate/DLQ/session theo tính năng thực sử dụng.
- [ ] Event Hubs tests kiểm tra consumer checkpoint và idempotent sink.
- [ ] Azure Functions local tests chạy qua trigger/binding thực sự nếu cần kiểm chứng trigger.
- [ ] Cloud tests bổ sung những features/identity/network mà emulator chưa hỗ trợ.

### 37.4. Azure tài nguyên thử nghiệm

- [ ] Chạy trong non-prod subscription/resource group với scope allowlist.
- [ ] Storage/DB/messaging accounts test tách khỏi production data.
- [ ] IaC/provisioning gắn owner/run ID/TTL và metadata chi phí.
- [ ] Test identity/tenant/object ID được xác minh, không dùng nhầm developer login.
- [ ] RBAC data-plane allow/deny được kiểm chứng bằng principals phù hợp.
- [ ] RBAC propagation có bounded polling, không retry 403 vô hạn.
- [ ] Private Endpoint/DNS/TLS được kiểm thử từ đúng runtime staging.
- [ ] Test runner không có quyền xóa resource ngoài phạm vi test.
- [ ] Test namespace unique, không phụ thuộc thứ tự hoặc trạng thái của test trước.
- [ ] Cleanup `finally`/CI post-step có manifest và janitor dự phòng.
- [ ] Không xóa tài nguyên shared/production chỉ vì tên có tiền tố “test”.

### 37.5. Reliability và data correctness

- [ ] Assertions kiểm tra dữ liệu thực và business outcome, không chỉ HTTP status.
- [ ] Negative tests có 401/403/404/409/412/429/5xx theo dịch vụ thực sử dụng.
- [ ] Retry có max attempts/time budget, không tạo duplicate side effects.
- [ ] Idempotent consumer và unique business key đã được thử với duplicate message.
- [ ] Network fault, lost ACK và process crash có tests ở phạm vi được phép.
- [ ] Async SDK tests thực sự subscribe/await với deadline.
- [ ] Clients/subscriptions/executors được đóng sau tests.
- [ ] Không dùng sleep cứng cho eventual behavior, dùng bounded polling.
- [ ] Concurrency tests có barrier/invariant, không dựa vào scheduler may rủi.
- [ ] Blob read-after-write và service-specific consistency được diễn giải đúng.

### 37.6. CI/CD, observability và chi phí

- [ ] Mỗi PR chạy unit + emulator tests ở runner hỗ trợ Docker.
- [ ] Nightly/release chạy cloud tests bằng trusted CI identity/OIDC/managed identity.
- [ ] Untrusted PRs không nhận cloud write credentials/secrets.
- [ ] Tests skipped/disabled được thống kê, critical skipped = fail gate.
- [ ] Ghi JUnit reports, sanitized SDK error codes, test resource aliases và correlation IDs.
- [ ] Không log Shared Key, connection string, SAS, bearer token hoặc raw sensitive data.
- [ ] Cloud tests có time/cost/data volume limits và ngân sách/alerts.
- [ ] Có runbook emulator incompatibility, cloud 401/403, resource leak, queue duplicate và cost regression.
- [ ] Có báo cáo ownership/cleanup PASS, leak count và active test resources.
- [ ] Chỉ kết luận **cloud-ready** sau khi những Azure-specific boundaries cần thiết đã thực sự được xác minh.

## 38. Kết luận

**Kiểm thử tích hợp Azure SDK bằng emulator và tài nguyên thử nghiệm** là một chiến lược nhiều lớp. **Unit tests** giúp kiểm tra business logic nhanh; **Azurite/Testcontainers** cho phép Java SDK thực sự giao tiếp với Blob/Queue/Table Storage trên môi trường có thể lặp lại; **Cosmos DB, Service Bus, Event Hubs và Functions emulators** có ích trong giới hạn tính năng/version được công bố. Nhưng emulator không tự chứng minh **Microsoft Entra ID, Azure RBAC, Private Endpoint, TLS, cloud quotas, HA, regional behavior hoặc feature parity**.

Với ứng dụng Java trên Microsoft Azure, hãy tạo client bằng **dependency injection, credential và endpoint đúng môi trường**, chạy JUnit integration tests với **synthetic data, unique resource names, idempotent assertions, timeout/retry có kiểm soát và cleanup bền vững**. Trên Azure thật, dùng **tài nguyên non-production** được provision bằng IaC, identity quyền tối thiểu, test allow/deny, quan sát logs/metrics và đặt budget/TTL. Một pipeline đáng tin không chỉ báo xanh khi API trả thành công, mà chứng minh **dữ liệu đúng, quyền đúng, lỗi được xử lý đúng, tài nguyên test được dọn sạch và không có tác động lên production**. Đó là nền tảng để nâng cấp Azure SDK cho Java và triển khai dịch vụ trên Azure một cách an toàn, có thể kiểm toán và bền vững.
