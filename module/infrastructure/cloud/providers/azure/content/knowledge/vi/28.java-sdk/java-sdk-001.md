# Cấu trúc Azure SDK for Java và quản lý phiên bản thư viện

Một ứng dụng Java dùng Azure có thể cần đọc tệp từ Blob Storage, lấy bí mật từ Key Vault, đưa thông điệp vào Service Bus và gọi các API quản trị tài nguyên. Mỗi dịch vụ có thư viện Java riêng. Nếu dự án nhập các phiên bản không tương thích, dùng lớp SDK cũ lẫn với SDK mới hoặc nâng dependency mà không kiểm thử, ứng dụng có thể gặp lỗi biên dịch, lỗi thiếu phương thức lúc chạy, xung đột Reactor/Netty hoặc sự cố xác thực khó điều tra.

**Azure SDK for Java** là hệ sinh thái các thư viện Java giúp ứng dụng làm việc với dịch vụ Microsoft Azure. Những thư viện hiện đại có cấu trúc tương đối nhất quán: **service client**, **client builder**, **authentication credential**, **HTTP pipeline/transport**, **model types**, các API **synchronous/asynchronous** và cơ chế log/retry. Việc quản lý phiên bản thư viện, đặc biệt bằng **Bill of Materials (BOM)**, giúp dự án kiểm soát một tập dependency thay vì tự ghép từng phiên bản có thể không phù hợp.

Bài thuộc chương **Azure SDK cho Java** của mô-đun **CLOUD_PROVIDERS_AZURE**. Đây là cầu nối giữa kiến thức về subscription, resource group, Microsoft Entra ID, mạng ảo, compute, storage, dữ liệu và thao tác triển khai/giám sát/bảo vệ/kiểm soát chi phí trên Azure từ ứng dụng Java.

> **Giới hạn bài học:** Ví dụ tập trung vào thế hệ Azure SDK for Java hiện đại, thường gọi là **Track 2**. Tên artifact, versions, JDK baseline và SDK surface thay đổi theo dịch vụ và thời điểm. Không lấy số phiên bản minh họa làm bản phát hành mới nhất: chọn phiên bản BOM/SDK đã được xác minh từ trang phát hành chính thức, compatibility matrix và chính sách bảo mật của dự án. Những đoạn code gọi Azure trong bài được đánh dấu rõ đọc-only hoặc có thay đổi dữ liệu.

## Mục tiêu học tập

Sau bài, bạn có thể:

1. Mô tả các lớp **azure-core**, **azure-identity**, thư viện cho từng dịch vụ, HTTP transport và management SDK.
2. Phân biệt **data plane SDK** với **management plane SDK**, cũng như thư viện **Track 1** và **Track 2**.
3. Đọc cấu trúc **ClientBuilder → Client → Operation → Model/Response** và tìm package tương ứng.
4. Hiểu clients đồng bộ/bất đồng bộ, **Reactor Mono/Flux**, **PagedIterable/PagedFlux** và **SyncPoller/PollerFlux**.
5. Sử dụng **DefaultAzureCredential** và managed identity đúng cách, không nhúng access key vào source.
6. Quản lý phiên bản bằng **com.azure:azure-sdk-bom** trong Maven và Gradle.
7. Phân biệt **Azure SDK BOM**, **Spring Cloud Azure BOM**, BOM cho thư viện quản trị và các versions không do BOM bao phủ.
8. Chẩn đoán xung đột dependencies, JDK/framework compatibility và lỗi **NoSuchMethodError/ClassNotFoundException**.
9. Thiết lập quy trình nâng cấp, kiểm thử, ghi nhận SBOM, rà soát CVE và rollback.
10. Xây checklist chọn SDK, bảo mật, retry, performance, telemetry và triển khai production.

## 1. Azure SDK giúp làm việc gì?

Không có một Java JAR duy nhất chứa mọi tính năng Azure. Thay vào đó, nhà phát triển chọn client library theo dịch vụ và loại thao tác.

~~~text
Ứng dụng Java
     |
     +-- azure-storage-blob ------------> Blob Storage: GET/PUT/list
     |
     +-- azure-security-keyvault-secrets -> Key Vault: get/set secrets
     |
     +-- azure-messaging-servicebus ----> Service Bus: send/receive
     |
     +-- azure-messaging-eventhubs -----> Event Hubs: produce/consume
     |
     +-- azure-cosmos ------------------> Cosmos DB: items/query
     |
     +-- azure-resourcemanager* --------> Azure Resource Manager operations
     |
     +-- azure-identity ----------------> Microsoft Entra credentials
     |
     +-- azure-core --------------------> common pipeline/models/paging
~~~

Dấu * thể hiện nhóm management SDK có **tọa độ Maven và cách quản lý versions riêng** so với nhiều service-client libraries. Không suy đoán mọi thư viện đều nằm trong cùng một BOM.

### Tại sao dùng SDK thay vì gọi REST thủ công?

- Client xử lý authentication headers/token acquisition theo credential.
- Service models giúp dùng kiểu dữ liệu Java rõ ràng.
- Cơ chế retry/paging/polling được chuẩn hóa một phần.
- Hỗ trợ HTTP pipeline, diagnostics và tracing theo thư viện.
- Giảm việc tự ghép request URIs và xử lý response status.

Nhưng **SDK không thay thế việc hiểu service**. Một phương thức list blobs có thể tốn nhiều requests, một lần ghi Key Vault secret vẫn là thay đổi security-sensitive, và retry một lệnh không idempotent có thể tạo dữ liệu trùng.

## 2. Data plane và management plane

Đây là phân biệt quan trọng ngay từ đầu:

| Loại API | Mục đích | Ví dụ |
|---|---|---|
| **Data plane** | Đọc/ghi/sử dụng dữ liệu, messages hoặc secrets của dịch vụ | Đọc blob, nhận Service Bus message, truy vấn Cosmos DB, lấy Key Vault secret |
| **Management plane** | Tạo/cấu hình/xóa Azure resources qua Azure Resource Manager | Tạo storage account, bật diagnostic settings, cấu hình resource group |

~~~text
                  Java application
                         |
                  +------+------+
                  |             |
                  v             v
             Data-plane      Management-plane
             SDK client      SDK/ARM client
                  |             |
                  v             v
             Blob endpoint   management.azure.com
             Key Vault URI   ARM resource providers
             Service Bus     Azure subscription/RG
~~~

### Quyền cũng khác

Một managed identity có vai trò **Storage Blob Data Reader** có thể đọc blobs theo scope, nhưng không nhất thiết được tạo storage account. Ngược lại, có Azure management-role ở subscription không nên tự suy ra có quyền đọc mọi data trong Blob/Key Vault.

Không cấp **Owner** trên resource group chỉ vì ứng dụng cần đọc một file; cần phân biệt đúng hành động và Azure RBAC data-plane/management-plane.

## 3. Các nhóm thư viện Azure SDK for Java

| Nhóm | Artifact/package ví dụ | Vai trò |
|---|---|---|
| **Common core** | com.azure:azure-core | Cấu trúc HTTP pipeline, logging, paging/polling, model chung |
| **Authentication** | com.azure:azure-identity | DefaultAzureCredential, ManagedIdentityCredential và các credential builders |
| **HTTP transport** | com.azure:azure-core-http-netty | Transport HTTP dùng Netty cho SDK phù hợp |
| **Transport thay thế** | com.azure:azure-core-http-okhttp | HTTP client dựa trên OkHttp khi thích hợp |
| **Storage** | com.azure:azure-storage-blob | Blob clients và request/response models |
| **Key Vault** | com.azure:azure-security-keyvault-secrets | SecretClient, SecretAsyncClient |
| **Service Bus** | com.azure:azure-messaging-servicebus | Producers, receivers/processors |
| **Event Hubs** | com.azure:azure-messaging-eventhubs | Event producer/consumer |
| **Cosmos** | com.azure:azure-cosmos | CosmosClient/async clients, data operations |
| **Resource management** | com.azure.resourcemanager:* | ARM fluent clients cho các dịch vụ hỗ trợ |
| **Spring integrations** | com.azure.spring:* | Spring Cloud Azure starters và configuration |

**Không phải mọi thư viện cùng groupId đều có mặt trong azure-sdk-bom**, đặc biệt preview, Spring Cloud Azure và resource-manager libraries. BOM quản lý **những artifacts đã được liệt kê trong BOM**, không áp đặt version lên cả Maven Central.

### Core có phải SDK dịch vụ?

Không. **azure-core** chứa các khái niệm dùng chung, nhưng riêng nó không cho phép gọi **BlobClient** hoặc **SecretClient** nếu chưa thêm service-specific artifact.

### azure-identity có tạo Azure resources không?

Không. Nó cung cấp cách nhận token/credentials. Muốn đọc Blob cần Blob client; muốn tạo resource group cần management API và quyền tương ứng.

## 4. Sơ đồ dependency điển hình

~~~text
                Java REST API
                     |
       +-------------+----------------+
       |                              |
       v                              v
 azure-storage-blob              azure-identity
       |                              |
       +--------------+---------------+
                      |
                      v
                  azure-core
                      |
               HTTP client interface
                      |
                 +----+----+
                 |         |
                 v         v
              Netty      OkHttp
         (tùy dependency/transport)
                      |
                      v
            Azure service endpoint
~~~

Đây là **sơ đồ khái niệm**, không phải dependency graph chính xác cho mọi version. Các SDK còn dùng các thư viện phụ như Reactor, Netty, Jackson hoặc các thành phần khác; một artifact có thể kéo thêm dependency transitively.

### Tại sao graph quan trọng?

Ứng dụng có thể thêm azure-storage-blob mà không khai báo trực tiếp azure-core. Maven/Gradle vẫn đưa azure-core vào **runtimeClasspath** qua dependency bắc cầu. Nếu một dependency khác ép azure-core phiên bản không tương thích, runtime có thể xảy ra lỗi dù compile từng module riêng lẻ thành công.

## 5. Track 1 và Track 2

Azure từng có các thế hệ Java SDK. Nhiều gói cũ dùng **com.microsoft.azure** hoặc API/client patterns khác. SDK hiện đại thường dùng **com.azure** cho data-plane libraries, có thiết kế nhất quán hơn.

| Nội dung | Track 1 / legacy | Track 2 / modern |
|---|---|---|
| Maven group/package thường gặp | com.microsoft.azure hoặc gói SDK cũ | com.azure và com.azure.resourcemanager theo loại |
| Client construction | Khác nhau theo thế hệ | Thường qua *ClientBuilder* |
| Authentication | Credential APIs đời trước | azure-identity với TokenCredential |
| Async model | Tùy thư viện cũ | Thường Reactor Mono/Flux |
| Common pipeline | Kiến trúc cũ và API không đồng nhất | azure-core, HTTP policy patterns |
| Release management | Legacy version lines | Azure SDK BOM và release guidance của thư viện hiện đại |

**Không có một quy tắc tự động “tất cả com.microsoft.* đều là Track 1”**; đây là dấu hiệu để kiểm tra đúng package/docs. Một số service có migration guide riêng.

### Ví dụ khác biệt Azure Storage

- SDK Blob đời cũ có classes/artifacts khác với BlobServiceClient/BlobClient hiện đại.
- Thay Maven coordinates **không đủ**: cần chỉnh imports, authentication, client construction, paging, request models và error handling.
- Một số features/overloads không có tương đương một-một.

### Quy tắc khi nâng cấp

**Không trộn mã sample Track 1 và Track 2 trong cùng một file rồi kỳ vọng tự tương thích.** Lập danh sách legacy classes và kiểm tra hướng dẫn migration theo từng dịch vụ, kèm tests.

## 6. Tổ chức package của SDK hiện đại

Lấy Blob Storage làm ví dụ:

~~~text
com.azure.storage.blob
   BlobServiceClientBuilder
   BlobServiceClient
   BlobServiceAsyncClient
   BlobContainerClient
   BlobContainerAsyncClient
   BlobClient
   BlobAsyncClient

com.azure.storage.blob.models
   BlobItem
   BlobProperties
   BlobStorageException
   ...

com.azure.identity
   DefaultAzureCredentialBuilder
   ManagedIdentityCredentialBuilder

com.azure.core
   credential.TokenCredential (theo package thực)
   http/policy, util, exception, ...
~~~

Các class minh họa mô hình library; trước khi viết import phải kiểm tra **Javadoc của đúng artifact/version**.

### Thường có bốn loại class

1. **Builder:** cấu hình endpoint, credential, HTTP client, retry, logging.
2. **Client:** gửi thao tác tới dịch vụ.
3. **Model/Options:** truyền parameters và chứa dữ liệu response.
4. **Exception/Response:** biểu diễn lỗi, status, headers và diagnostics.

SDK có thể thêm **specialized client** cho một phạm vi service; không phải mọi phương thức đều nằm trên một “god client”.

## 7. Builder pattern trong Azure SDK

Kiểu sử dụng thường thấy:

~~~java
SomeServiceClient client = new SomeServiceClientBuilder()
    .endpoint("https://service-endpoint")
    .credential(credential)
    .buildClient();
~~~

Đây là **pseudocode** để minh họa Builder, không phải tên class thực.

### Một Builder thường cần

- **Endpoint:** hostname/URI đúng của Azure resource.
- **Credential:** cách lấy token hoặc key, tùy dịch vụ.
- **HTTP client:** transport theo default hoặc custom.
- **Client options/policies:** retry, logging, tracing, user agent hoặc transport tuning khi API hỗ trợ.
- **Sync/async choice:** buildClient() hay buildAsyncClient() nếu có cả hai.

### Cẩn trọng với builder methods

Tên phương thức **không đồng nhất cho mọi SDK**. Ví dụ Blob builder khác Cosmos DB builder và Service Bus builder. Không giả định .retryOptions() hoặc .endpoint() có cùng overload trên tất cả các libraries.

## 8. Ví dụ thật: BlobServiceClientBuilder

Đây là ví dụ Java **chỉ đọc**, dùng Microsoft Entra credentials để kiểm tra sự tồn tại của một blob đã biết. Không upload hoặc xóa dữ liệu.

~~~java
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.storage.blob.BlobClient;
import com.azure.storage.blob.BlobServiceClient;
import com.azure.storage.blob.BlobServiceClientBuilder;

public final class BlobReadOnlyCheck {
    public static void main(String[] args) {
        String endpoint = required("AZURE_BLOB_ENDPOINT");
        String containerName = required("AZURE_BLOB_CONTAINER");
        String blobName = required("AZURE_BLOB_NAME");

        BlobServiceClient serviceClient =
            new BlobServiceClientBuilder()
                .endpoint(endpoint)
                .credential(
                    new DefaultAzureCredentialBuilder().build()
                )
                .buildClient();

        BlobClient blob = serviceClient
            .getBlobContainerClient(containerName)
            .getBlobClient(blobName);

        // exists() thực hiện service request đọc metadata,
        // đòi quyền dữ liệu và có thể phát sinh transaction charges.
        System.out.println("Blob exists: " + blob.exists());
    }

    private static String required(String key) {
        String value = System.getenv(key);
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                "Missing environment variable: " + key);
        }
        return value;
    }
}
~~~

### Giải thích

1. **AZURE_BLOB_ENDPOINT** là endpoint như HTTPS FQDN của account đã được cấp quyền; không thêm SAS token vào source.
2. **DefaultAzureCredential** thử nguồn danh tính phù hợp môi trường, không tự cấp Storage Blob Data Reader.
3. **getBlobContainerClient/getBlobClient** xây đối tượng client; **exists()** mới gửi request tới Azure.
4. Nếu blob không tồn tại, exists() thường trả false; lỗi 403/network vẫn có thể ném exception.
5. Cần TLS/Private Endpoint/DNS/RBAC đúng để hoạt động.
6. Tạo và tái sử dụng service clients theo vòng đời ứng dụng; không khởi tạo lại trong mỗi HTTP request.
7. **Không được suy ra đọc-only nghĩa là không phát sinh chi phí**: Azure Storage vẫn tính transactions theo pricing.

### Điều kiện để chạy

- Dependency **azure-storage-blob** và **azure-identity** tương thích.
- JDK version được thư viện hỗ trợ.
- Người chạy đã đăng nhập/có managed identity.
- Quyền Storage data-plane tối thiểu.
- Storage endpoint, container và blob name hợp lệ.
- Java process đi được qua network/firewall.

## 9. Đồng bộ (sync) và bất đồng bộ (async)

Azure SDK hiện đại thường cung cấp cả sync và async clients (tùy dịch vụ).

| Khía cạnh | Sync client | Async client |
|---|---|---|
| Kết quả | Trả giá trị hoặc exception trực tiếp | Mono/Flux hoặc API reactive khác |
| Thread model | Thread gọi thường chờ request | Non-blocking flows với subscriptions |
| Phù hợp | CLI, batch nhỏ, ứng dụng thread-per-request | Reactive service, high-concurrency I/O |
| Tính dễ đọc | Trực quan | Cần hiểu reactive streams/cancellation |
| Lỗi thường gặp | Block thread quá lâu | Quên subscribe, block event loop, không xử lý errors |

### Ví dụ Sync

~~~java
boolean present = blob.exists();
System.out.println(present);
~~~

### Ví dụ Async

~~~java
import com.azure.storage.blob.BlobAsyncClient;

BlobAsyncClient asyncBlob = asyncServiceClient
    .getBlobContainerAsyncClient(containerName)
    .getBlobAsyncClient(blobName);

asyncBlob.exists()
    .subscribe(
        exists -> System.out.println("Exists: " + exists),
        error -> System.err.println(
            "Azure Blob read failed: " + error.getClass().getSimpleName()
        )
    );
~~~

Đoạn Async minh họa giả định **asyncServiceClient** đã được tạo qua **BlobServiceClientBuilder.buildAsyncClient()**. Nó không chứng minh process đã chờ subscription hoàn tất: trong chương trình main ngắn, cần cơ chế quản lý lifecycle/completion; không chỉ gọi subscribe() rồi exit.

### Mono và Flux

**Mono<T>** biểu diễn tối đa một kết quả hoặc error; **Flux<T>** biểu diễn nhiều phần tử. Reactor là một phần quan trọng ở nhiều async Azure SDK; xử lý subscription/cancel/backpressure phải theo contract của thư viện.

**Không gọi .block() trên event-loop thread** của một dịch vụ WebFlux chỉ để “đổi async thành sync”: có thể gây deadlock hoặc giảm throughput. Nếu code đang theo imperative style, dùng sync client phù hợp.

## 10. Paging: PagedIterable và PagedFlux

Một API liệt kê hàng triệu blobs hoặc secrets không nhất thiết trả toàn bộ trong một HTTP response. Azure SDK có những tiện ích paging chung.

~~~text
Java call listItems()
        |
        v
Page 1 (continuation token)
        |
        v
Page 2 (continuation token)
        |
        v
Page 3 ...
~~~

### Sync: PagedIterable

~~~java
import com.azure.storage.blob.BlobContainerClient;
import com.azure.storage.blob.models.BlobItem;

BlobContainerClient container = serviceClient
    .getBlobContainerClient(containerName);

// Chỉ thử trên container LAB nhỏ đã được cấp quyền.
int count = 0;
for (BlobItem item : container.listBlobs()) {
    System.out.println(item.getName());
    if (++count >= 10) {
        break;
    }
}
~~~

### Cảnh báo về chi phí và bảo mật

- Việc lặp qua **PagedIterable** có thể thực hiện các HTTP requests trong quá trình duyệt.
- In tên blobs trên production có thể làm lộ dữ liệu nhạy cảm.
- Dừng sau 10 items không chắc SDK chỉ gọi đúng một HTTP request.
- Muốn tìm một blob cụ thể, **point lookup** thường tốt hơn list toàn bộ container.
- Với container lớn cần prefix filters, pagination và telemetry phù hợp.

### Async: PagedFlux

Nhiều dịch vụ cung cấp **PagedFlux<T>** để streaming pages/items. Không nên thu toàn bộ kết quả vào RAM bằng collectList() nếu dữ liệu rất lớn. Dùng limit/cancellation và backpressure theo Reactor.

## 11. Long-running operations: pollers

Một số management operations (tạo/xóa resources, kích hoạt deployment) không hoàn tất ngay. SDK có thể dùng:

- **SyncPoller** cho flows đồng bộ.
- **PollerFlux** cho flows reactive, theo thư viện.

~~~text
Client request: create resource
      |
      v
Azure trả trạng thái Accepted/InProgress
      |
      v
Poller theo dõi trạng thái
      |
      +-- InProgress
      +-- Succeeded
      +-- Failed / Canceled
~~~

### Vì sao cần quan tâm?

- Submit lệnh không đồng nghĩa resource đã sẵn sàng.
- Poll quá thường xuyên có thể tạo overhead.
- Cần timeout, cancellation và error handling.
- Phải xem trạng thái cuối và kết quả, không chỉ HTTP 202.
- Với thao tác tạo/xóa resources, cần áp nguyên tắc quyền, approval và rollback.

Không tự viết vòng while polling vô hạn nếu SDK đã có poller phù hợp; đồng thời không tin poller áp dụng giống nhau cho mọi SDK/operation.

## 12. Azure Core và HTTP pipeline

Một service request đi qua nhiều lớp:

~~~text
ServiceClient.method(...)
      |
      v
Serialize request/model
      |
      v
HTTP pipeline
  - authentication / request signing
  - retry policy
  - diagnostics/logging/tracing
  - custom policies khi hỗ trợ
      |
      v
HTTP transport (Netty/OkHttp/...)
      |
      v
Azure service endpoint
      |
      v
HTTP response -> deserialize -> model/error
~~~

**azure-core** cung cấp những primitive/abstractions dùng chung cho pipeline, policies, HTTP requests/responses, paging, polling, exceptions và tracing. Từng service SDK có thể thêm custom policies và defaults riêng.

### Thay HTTP client có giải quyết mọi lỗi?

Không. Nếu lỗi là 403 vì RBAC, thay Netty bằng OkHttp sẽ không tự cấp quyền. Nếu lỗi là timeout do firewall, đổi retry policy có thể chỉ kéo dài thời gian thất bại.

## 13. Transport: Netty và OkHttp

Hai transport artifacts thường gặp:

- **com.azure:azure-core-http-netty**
- **com.azure:azure-core-http-okhttp**

Thư viện service có thể phụ thuộc HTTP transport mặc định hoặc cho phép cấu hình transport riêng.

| Điều kiện | Hướng chọn |
|---|---|
| Dùng SDK theo cấu hình mặc định đã kiểm thử | Giữ transport mặc định khi phù hợp |
| Ứng dụng đã dùng Netty/Reactor mạnh | Kiểm tra version alignment và lifecycle |
| Tổ chức đã chuẩn hóa OkHttp | Xem API transport và compatibility của SDK |
| Có yêu cầu proxy hoặc network đặc biệt | Đánh giá transport options theo tài liệu SDK |
| Có lỗi TLS/ALPN/connection pool | Phân loại network/JDK/dependency trước khi đổi transport |

### Không thêm cả hai chỉ vì “phòng hờ”

Nhiều HTTP clients trên classpath có thể làm dependency graph phức tạp; SDK có cơ chế tìm transport theo factory/config. Nếu muốn dùng một client cụ thể, **cấu hình rõ ràng và kiểm thử runtime classpath**.

### Connection pooling và thread lifecycle

Service clients thường được thiết kế để **tái sử dụng**. Tạo nhiều clients trong mỗi request có thể làm tăng sockets, TLS handshakes và threads. Tuy nhiên đóng clients có shared transport có thể có tác động khác so với client tự sở hữu transport: đọc đúng lifecycle contract của phiên bản SDK.

## 14. Xác thực: azure-identity

Để dùng Microsoft Entra ID, SDK cung cấp các credential builders thông qua artifact **com.azure:azure-identity**.

### Các lựa chọn phổ biến

| Credential | Tình huống | Lưu ý |
|---|---|---|
| **DefaultAzureCredential** | Dev/local và nhiều workloads Azure | Credential chain phụ thuộc môi trường; cần kiểm soát nguồn danh tính |
| **ManagedIdentityCredential** | App Service, VM, Azure Functions, Container Apps... theo hỗ trợ | Không lưu client secret; phải cấp role đúng |
| **WorkloadIdentityCredential** | Workloads hỗ trợ federation như AKS Workload Identity | Cần federation/OIDC/service account và role |
| **AzureCliCredential** | Local development đã az login | Không nên làm cơ chế auth production |
| **ClientSecretCredential** | Automation khi chưa thể tránh secret | Secret rotation và Key Vault |
| **ClientCertificateCredential** | Automation với certificate | Quản lý certificate/private key an toàn |

SDK nhận TokenCredential và gọi dịch vụ theo scopes/audience do client library/service yêu cầu.

### DefaultAzureCredential

~~~java
import com.azure.core.credential.TokenCredential;
import com.azure.identity.DefaultAzureCredentialBuilder;

TokenCredential credential =
    new DefaultAzureCredentialBuilder().build();
~~~

**Không có gì trong đoạn code cấp quyền cho identity**. Quyền được cấu hình trong Entra ID/Azure RBAC và data-plane systems.

### Tình huống dễ nhầm danh tính

Laptop của developer có nhiều tenant hoặc có biến môi trường cho service principal. DefaultAzureCredential có thể chọn một nguồn credential khác dự định. Vì vậy:

1. Xác định tenant/subscription.
2. Kiểm soát biến môi trường auth.
3. Kiểm tra principal thực tế trong logs an toàn và Azure activity/audit.
4. Không log raw access tokens.
5. Ở production, cân nhắc explicit managed/workload identity khi cần tính dự đoán được.

## 15. Managed identity cho ứng dụng Java

~~~text
Java app trên Azure (managed identity)
      |
      v
Azure Identity SDK lấy token
      |
      v
Azure Blob SDK gửi request qua TLS
      |
      v
Storage data-plane authorization
      |
      +-- Allowed -> data/metadata response
      +-- Denied  -> 403
~~~

### Ví dụ chọn user-assigned managed identity

~~~java
import com.azure.core.credential.TokenCredential;
import com.azure.identity.ManagedIdentityCredentialBuilder;

String clientId = System.getenv("AZURE_CLIENT_ID");
if (clientId == null || clientId.isBlank()) {
    throw new IllegalStateException("Missing AZURE_CLIENT_ID");
}
TokenCredential credential =
    new ManagedIdentityCredentialBuilder()
        .clientId(clientId)
        .build();
~~~

Client ID là định danh identity, không phải secret. **Managed identity phải được gắn vào compute resource** và được cấp quyền service data plane. Nếu compute chưa hỗ trợ hoặc identity không được attach, credential không thể tự hoạt động.

### Quyền ví dụ

Một API chỉ cần xem blob có thể được cấp **Storage Blob Data Reader** trong phạm vi container/resource cần thiết. Nếu ứng dụng cần upload, quyền phải xem xét lại; không nâng lên subscription Owner như một cách sửa tạm.

## 16. Kết nối tới Azure: TLS, DNS và Private Endpoint

~~~text
Java app (AKS/App Service)
          |
          | TLS HTTPS to service FQDN
          v
Private DNS / approved public DNS
          |
          v
Private Endpoint / service route
          |
          v
Azure Blob/Key Vault/Service Bus
~~~

Các SDK không tự cấu hình VNet, firewall hoặc private DNS. Khi một API client báo **UnknownHostException**, **ConnectTimeoutException**, **SSLHandshakeException** hoặc 403, cần chẩn đoán theo lớp:

| Lớp | Cần kiểm tra |
|---|---|
| DNS | FQDN, private DNS zone, resolver, network namespace |
| TCP/network | NSG, UDR, firewall, routing, allowed port |
| TLS | JDK truststore, certificate chain, hostname verification |
| Identity | Token/tenant/principal, managed identity assignment |
| Authorization | Data-plane role, ACL, resource scope |
| Service | Quota, request parameters, endpoint version, service state |

**Không tắt chứng chỉ TLS hoặc mở public access toàn Internet để “sửa” lỗi SDK**. Private Endpoint không thay TLS và Entra ID không thay quyền ở data plane.

## 17. Client exceptions và xử lý lỗi

Azure SDK có exceptions biểu thị những lớp lỗi:

- **ClientAuthenticationException**: vấn đề credential/authentication theo thư viện.
- **HttpResponseException** và các subclasses: service trả HTTP error.
- **ResourceNotFoundException**: một số trường hợp tài nguyên không tồn tại.
- **ServiceRequestException**: có thể liên quan network/request.
- **ServiceResponseException**: vấn đề response/protocol, tùy SDK.
- **Service-specific exceptions**: ví dụ BlobStorageException có thông tin mã lỗi Blob.

### Không nuốt lỗi một cách mù quáng

~~~java
import com.azure.storage.blob.models.BlobStorageException;

try {
    boolean exists = blob.exists();
    System.out.println("Present: " + exists);
} catch (BlobStorageException ex) {
    // Không log URI có SAS, access tokens hoặc secret.
    System.err.println(
        "Blob request failed, HTTP status: " + ex.getStatusCode()
    );
    throw ex;
}
~~~

Đây là snippet trong ngữ cảnh biến **blob** đã được xây ở mục 8. Với lỗi khác như DNS/auth, cần catch/telemetry ở tầng xử lý thích hợp thay vì coi mọi exception là BlobStorageException.

### Phân biệt thường gặp

| Mã/lỗi | Ý nghĩa thường gặp | Hướng kiểm tra |
|---|---|---|
| **401** | Auth token/credential không hợp lệ hoặc thiếu | Credential type, audience, tenant |
| **403** | Thiếu quyền hoặc network/firewall policy chặn theo service | Data-plane role/ACL, firewall |
| **404** | Tài nguyên/path không tồn tại hoặc không được nhìn thấy | Endpoint, container, blob name |
| **409** | Conflict/state mismatch | Resource state, operation semantics |
| **412** | Preconditions/ETag không khớp | Optimistic concurrency |
| **429** | Throttling/rate limit | Retry-after, quota, throughput |
| **5xx** | Server/transient failure | Bounded retry và diagnostics |
| **NoSuchMethodError** | Java runtime linkage/dependency conflict | Version alignment, dependency tree |

HTTP mapping thực tế tùy Azure service; **không dựa riêng một status code để suy ra nguyên nhân**, xem error code, request ID và service diagnostics.

## 18. Retry: mặc định hữu ích nhưng không phải phép màu

SDK có chính sách retry mặc định hoặc cấu hình được tùy service. Các hoạt động chịu ảnh hưởng bởi:

- Request type và **idempotency**.
- HTTP status/service error code.
- **Retry-After** headers hoặc backoff.
- Tổng deadline của request.
- Throttle/quota.
- Khả năng cancel request.

### Hai sai lầm

1. **Retry vô hạn** khi service trả 403: lỗi quyền không được sửa bằng cách lặp.
2. **Retry ghi không idempotent** sau timeout: một request có thể đã được server xử lý dù response bị mất.

Ví dụ tải:

~~~text
100 instances gửi request
  -> Azure service throttle / network timeout
  -> mỗi instance retry ngay 10 lần
  -> tải bùng lên 1.000 requests
  -> lỗi càng kéo dài
~~~

### Quy tắc

1. Dùng defaults của service SDK khi đủ phù hợp.
2. Có retry limits, backoff + jitter và tổng request deadline.
3. Không kết hợp nhiều tầng retry để vượt quá deadline (SDK + Spring Retry + gateway).
4. Với write, xác định idempotency key, ETag hoặc conditional operation khi cần.
5. Đo số retries và latency cuối cùng, không chỉ thời gian của một attempt.

Không sao chép một **RetryOptions** code từ Blob sang Cosmos DB mà không xem builder/API của đúng SDK và version.

## 19. Tại sao quản lý phiên bản Azure SDK khó?

Giả sử API Java sử dụng:

~~~text
azure-storage-blob
azure-identity
azure-security-keyvault-secrets
azure-messaging-servicebus
spring-boot-starter-web
spring-webflux (một phần hệ thống)
~~~

Mỗi thư viện có dependencies riêng. Một phiên bản Blob SDK có thể dùng azure-core và Netty; Azure Identity có các phụ thuộc nhận token; Spring Boot có BOM riêng để quản lý nhiều thư viện Java thông dụng.

Nếu developer chọn một tập versions bằng cách nhìn vào ví dụ cũ trên blog:

- **azure-core** có thể bị ép xuống phiên bản thiếu method mà một SDK mới gọi.
- **reactor-core** hoặc Netty có thể bị đẩy về version không tương thích.
- Một security patch có thể chỉ nằm ở bản SDK/transport mới hơn.
- **NoSuchMethodError** có thể chỉ xuất hiện lúc gọi Azure API.
- Các môi trường build/running dùng dependency trees khác nhau khiến bug khó tái hiện.

### Mục tiêu quản lý dependencies

1. **Một nguồn quyết định versions rõ ràng**.
2. **Phân giải phụ thuộc tái lập được**.
3. **Kiểm tra compatibility** với JDK, framework và thư viện khác.
4. **Áp security patches có kiểm soát**.
5. **Có lịch nâng cấp và rollback**.

## 20. Azure SDK Bill of Materials (BOM) là gì?

**BOM (Bill of Materials)** trong Maven ecosystem là một **POM quản lý phiên bản dependency** của một nhóm artifacts. **com.azure:azure-sdk-bom** cung cấp tập versions được Azure SDK team lựa chọn cho những thư viện **có mặt trong BOM release đó**.

~~~text
Application POM / Gradle build
           |
           v
Azure SDK BOM (một phiên bản được phê duyệt)
           |
           +--> azure-core                : aligned version
           +--> azure-identity            : aligned version
           +--> azure-storage-blob        : aligned version
           +--> azure-security-keyvault-* : aligned version
           +--> ... những artifacts nằm trong BOM
~~~

### BOM làm gì?

- Cho phép bỏ version ở khai báo dependency nằm trong BOM.
- Giảm lỗi chọn từng phiên bản không đồng bộ.
- Giúp đội dự án tập trung vào **một version BOM** khi nâng cấp tập SDK.
- Thuận tiện đối chiếu release notes/security updates.

### BOM không làm gì?

- Không **tự thêm** azure-storage-blob vào classpath nếu chưa khai báo dependency.
- Không tự chạy migration code khi APIs thay đổi.
- Không quản lý mọi dependency ngoài danh sách.
- Không bảo đảm tương thích với mọi phiên bản Spring/JDK khác.
- Không áp dụng bản vá CVE nếu bạn không nâng BOM hoặc cấu hình đã override versions.
- Không bảo đảm mọi Azure service preview library có trong BOM.

### BOM version và SDK version là hai thứ khác nhau

Một bản BOM có version riêng, ví dụ **BOM_RELEASE_X**, và quản lý những service SDK có versions độc lập. Không được suy ra mọi artifacts sẽ mang version **BOM_RELEASE_X**.

## 21. Maven: import azure-sdk-bom đúng cách

Trong **pom.xml** của dự án Maven Java thông thường:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="
           http://maven.apache.org/POM/4.0.0
           https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>example.org</groupId>
  <artifactId>azure-sdk-lab</artifactId>
  <version>1.0.0-SNAPSHOT</version>

  <properties>
    <maven.compiler.release>17</maven.compiler.release>
  </properties>

  <dependencyManagement>
    <dependencies>
      <dependency>
        <groupId>com.azure</groupId>
        <artifactId>azure-sdk-bom</artifactId>
        <version>REPLACE_WITH_APPROVED_BOM_VERSION</version>
        <type>pom</type>
        <scope>import</scope>
      </dependency>
    </dependencies>
  </dependencyManagement>

  <dependencies>
    <dependency>
      <groupId>com.azure</groupId>
      <artifactId>azure-identity</artifactId>
    </dependency>
    <dependency>
      <groupId>com.azure</groupId>
      <artifactId>azure-storage-blob</artifactId>
    </dependency>
    <dependency>
      <groupId>com.azure</groupId>
      <artifactId>azure-security-keyvault-secrets</artifactId>
    </dependency>
  </dependencies>
</project>
~~~

**Bắt buộc thay** chuỗi **REPLACE_WITH_APPROVED_BOM_VERSION** bằng version thực đã được xác minh. Đây là template có chủ ý, không phải POM chạy được ngay nguyên trạng.

### Vì sao dependency không cần version?

Vì **dependencyManagement** đặt version mặc định cho coordinates tương ứng. Maven vẫn cần một **dependency entry** trong dependencies để library được sử dụng trực tiếp. Chỉ import BOM mà không khai báo azure-storage-blob thì không có Blob SDK cho mã Java.

### Vì sao JDK release = 17?

Đây là **JDK LTS minh họa** cho dự án thực hành. JDK baseline và support của từng Azure SDK, framework, build plugins và runtime image phải được đối chiếu riêng. Không suy ra mọi artifact bắt buộc JDK 17 hoặc mọi tổ hợp JDK đều được hỗ trợ.

### Có thể thêm version trực tiếp cho Blob SDK?

Có thể, nhưng nếu bạn khai báo:

~~~xml
<dependency>
  <groupId>com.azure</groupId>
  <artifactId>azure-storage-blob</artifactId>
  <version>MANUALLY_SELECTED_VERSION</version>
</dependency>
~~~

Version trực tiếp có thể override version được BOM quản lý. Điều này làm giảm lợi ích alignment và cần lý do cùng integration test. **Không khuyến khích tự override chỉ vì thấy blog có phiên bản cao hơn**.

## 22. Gradle: dùng BOM với platform

Với Gradle Groovy DSL trong **build.gradle**:

~~~groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation platform(
        'com.azure:azure-sdk-bom:REPLACE_WITH_APPROVED_BOM_VERSION'
    )

    implementation 'com.azure:azure-identity'
    implementation 'com.azure:azure-storage-blob'
    implementation 'com.azure:azure-security-keyvault-secrets'
}
~~~

Trong Gradle Kotlin DSL (**build.gradle.kts**):

~~~kotlin
plugins {
    java
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

dependencies {
    implementation(
        platform("com.azure:azure-sdk-bom:REPLACE_WITH_APPROVED_BOM_VERSION")
    )
    implementation("com.azure:azure-identity")
    implementation("com.azure:azure-storage-blob")
    implementation("com.azure:azure-security-keyvault-secrets")
}
~~~

### platform khác enforcedPlatform ở đâu?

**platform** đưa các constraints từ Maven BOM vào cơ chế chọn dependency của Gradle; tùy graph, một số version constraints khác có thể ảnh hưởng kết quả. **enforcedPlatform** áp ràng buộc mạnh và có thể gây xung đột với các libraries/framework, kể cả khi dependency được xuất bản sang consumer khác.

Không dùng enforcedPlatform như lựa chọn mặc định chỉ để che một lỗi dependency. Trước tiên xem graph, lý do chọn version và compatibility.

### Maven và Gradle có luôn chọn cùng một dependency graph?

**Không nên mặc định**. Maven dependency mediation và Gradle conflict resolution có quy tắc khác. Dù cùng BOM, plugin, dependency constraints và direct overrides có thể làm classpath cuối khác nhau. Phải kiểm tra resolved versions từ công cụ build thực sự dùng.

## 23. Dependency management khác dependency declaration

~~~text
Import BOM vào dependency management
               |
               v
Quản lý phiên bản khả dụng
               |
               +-- Có dependency declaration --> thư viện có thể vào graph
               |
               +-- Không có declaration --> không tự thêm thư viện
~~~

### Ví dụ

Dự án đã import BOM, rồi mã Java thêm:

~~~java
import com.azure.storage.blob.BlobServiceClientBuilder;
~~~

Nhưng **pom.xml không có azure-storage-blob**. Compiler sẽ báo thiếu package dù BOM có quản lý version của azure-storage-blob. Cách sửa là thêm dependency artifact, **không phải import thêm một BOM khác ngẫu nhiên**.

### Dependency tree vẫn có transitive versions

Khai báo azure-storage-blob có thể kéo theo azure-core và HTTP transport; nếu graph có nhiều đường phụ thuộc, phải kiểm tra version được chọn. Sự hiện diện của BOM không thay thế việc xem dependency tree khi có lỗi linkage/runtime.

## 24. BOM không quản lý tất cả libraries

Một dự án Java trên Azure còn dùng:

- Spring Boot và Spring Cloud Azure.
- Azure Resource Manager management SDK.
- Micrometer/OpenTelemetry.
- Reactor, Netty, Jackson.
- JDBC driver cho SQL Server/Azure SQL.
- MSAL4J hoặc thư viện auth khác trong những tích hợp riêng.
- HTTP clients và utilities khác.

Những thư viện này **không nhất thiết được com.azure:azure-sdk-bom quản lý**. Đặc biệt:

| Library family | Hướng quản lý |
|---|---|
| **Azure data-plane SDK** | azure-sdk-bom nếu artifact nằm trong BOM |
| **Spring Boot** | Spring Boot dependency management/BOM và compatibility |
| **Spring Cloud Azure** | BOM/dependencies của Spring Cloud Azure và compatibility matrix |
| **Azure management SDK** | Quản lý theo release/BOM riêng nếu có và được xác minh |
| **Reactor/Netty/Jackson** | Kiểm tra resolved graph và framework constraints |
| **Preview/beta service SDK** | Kiểm tra artifact có được BOM bao phủ hay phải pin riêng |

### Đặc biệt với beta/preview

Một library preview có thể phát hành thay đổi API hoặc behavior không tương thích giữa các phiên bản. Không giả định đã được BOM stable quản lý và không nâng tùy tiện lên preview chỉ vì version number trông lớn hơn.

## 25. Spring Boot và Spring Cloud Azure BOM

Khi ứng dụng dùng Spring Boot, hệ dependency đã có version constraints cho Spring Framework, Reactor, Netty, logging và nhiều thư viện khác. **Spring Cloud Azure** cung cấp những starter integrations để truy cập Azure theo mô hình Spring.

Ví dụ artifact:

~~~text
com.azure.spring:spring-cloud-azure-starter-storage-blob
com.azure.spring:spring-cloud-azure-dependencies
~~~

### Lựa chọn theo cách tích hợp

| Bạn đang làm gì? | Lựa chọn ban đầu |
|---|---|
| Viết Java app thuần với BlobServiceClient | azure-storage-blob + azure-identity, BOM Azure SDK |
| Dùng Spring property binding/autoconfiguration | Spring Cloud Azure starter/BOM phù hợp |
| Cùng app dùng Spring starters và direct Azure SDK | Kiểm tra cả BOM/version graph; tránh hai nơi ép azure-core trái nhau |
| App chỉ cần một REST endpoint gọi Blob | Direct SDK có thể đủ; không bắt buộc thêm starter |

### Ví dụ Maven fragment theo hướng Spring

~~~xml
<!-- Trong ứng dụng Spring Boot đã cấu hình parent/BOM phù hợp. -->
<dependencyManagement>
  <dependencies>
    <dependency>
      <groupId>com.azure.spring</groupId>
      <artifactId>spring-cloud-azure-dependencies</artifactId>
      <version>APPROVED_SPRING_CLOUD_AZURE_VERSION</version>
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

Đây là **fragment cho một dự án Spring đã có dependency management**, không phải POM hoàn chỉnh. Phải chọn **Spring Boot ↔ Spring Cloud Azure compatibility matrix** phù hợp rồi xác minh resolved Azure SDK versions. Không dán hai khối dependencyManagement riêng lẻ y nguyên nếu POM đã có một khối; hợp nhất vào cấu trúc Maven hợp lệ.

### Có cần import cả Azure SDK BOM không?

Không có đáp án chung. Nếu Spring Cloud Azure BOM đã quản lý một số Azure libraries, việc import thêm Azure SDK BOM khác có thể tạo version mediation không mong muốn. **Chọn chiến lược BOM rõ ràng**, kiểm tra thứ tự/import rules và dependency tree, sau đó integration test. Với mô-đun dùng Azure SDK trực tiếp nhưng không dùng Spring Cloud Azure, Azure SDK BOM thường dễ quản lý hơn.

## 26. Azure Resource Manager SDK là một nhánh riêng

Azure Resource Manager dùng cho operations như tạo/cấu hình storage accounts, virtual machines hoặc resource groups. Một số Java packages:

~~~text
com.azure.resourcemanager
com.azure.resourcemanager.storage
com.azure.resourcemanager.compute
com.azure.resourcemanager.resources
~~~

Không nên viết BlobServiceClient để tạo Azure storage account: đó là management operation khác. Ngược lại, resource-manager client không thay cho BlobClient đọc file trực tiếp.

### Versioning cần tách

Artifacts thuộc group **com.azure.resourcemanager** có chính sách/version và các cơ chế dependency management khác so với nhiều **com.azure** data-plane artifacts. **Xác minh có BOM phù hợp cho management SDK và version được công bố** thay vì mặc định azure-sdk-bom sẽ quản lý hết.

### Quyền và nguy cơ

Management SDK có thể tạo, xóa, đổi capacity hoặc network configuration. Dù service code chạy bằng managed identity, nó vẫn có thể thực hiện thay đổi lớn nếu identity có quyền rộng. Tách identity runtime data-plane khỏi automation identity quản lý resource khi có thể.

## 27. Semantic Versioning và ý nghĩa số phiên bản

Nhiều Java artifacts hiển thị dạng:

~~~text
major.minor.patch
    |    |     |
    |    |     +--> maintenance/bug/security fixes
    |    +--------> features/compatible evolution theo chính sách
    +-------------> thay đổi lớn có thể breaking
~~~

Đây là **cách hiểu định hướng**, không phải luật bất biến của mọi Azure SDK:

- Release notes và migration guide mới là nguồn xác định breaking changes thực tế.
- Minor/patch có thể chứa behavioral changes liên quan bug fixes.
- Preview/beta có chính sách stability khác stable.
- Một phiên bản mới có thể tăng JDK baseline hoặc thay đổi dependency transitives.
- Version của SDK client không đồng nghĩa **REST API version** của service.

### Hai số phiên bản không được nhầm

**Artifact version:** phiên bản JAR Java mà Maven/Gradle tải.

**Service API version:** phiên bản giao thức/API mà client gọi tới Azure, thường được SDK/service chọn hoặc cấu hình theo khả năng.

Nâng service API version có thể thay đổi features/serialization; nâng JAR có thể thay đổi implementation, dependencies hoặc REST API selection. Không suy ra cùng một thay đổi.

## 28. JDK, compiler và runtime compatibility

Một hệ thống có ba thành phần phiên bản:

~~~text
JDK dùng compile
       |
       v
Class file bytecode target
       |
       v
JRE/JDK dùng chạy trên Azure
       |
       +-- Spring Boot runtime
       +-- Azure SDK libraries
       +-- Reactor/Netty/HTTP transport
~~~

### Những lỗi thường gặp

- Compile với JDK mới, chạy bằng Java cũ → **UnsupportedClassVersionError**.
- Library nâng minimum JDK nhưng build pipeline chưa nâng → lỗi compile/bytecode.
- Spring Boot version không tương thích với Spring Cloud Azure version.
- Runtime container base image chứa CA certificates quá cũ, gây lỗi TLS.
- Dev chạy Java 21 nhưng production container còn Java 17 với bytecode target chưa phù hợp.

### Quy tắc

1. Ghi rõ **JDK LTS được hỗ trợ** trong dự án.
2. Dùng Maven compiler release/Gradle toolchains.
3. Pin base container image và kiểm tra CVEs.
4. CI build/test trên JDK tương ứng production.
5. Kiểm tra compatibility matrix của mỗi thư viện quan trọng.
6. Không chọn “SDK version mới nhất” nếu runtime/framework của tổ chức chưa hỗ trợ.

## 29. Maven multi-module: BOM nên đặt ở đâu?

Một repository có:

~~~text
java-azure-service/
  pom.xml                (parent)
  api/
    pom.xml
  storage-adapter/
    pom.xml
  messaging-adapter/
    pom.xml
~~~

Nếu tất cả modules dùng cùng BOM, thường quản lý Azure SDK version ở **parent pom.xml** trong dependencyManagement để modules không mỗi nơi nhập version riêng.

~~~text
Parent BOM_VERSION
      |
      +-- api                 -> dependency declarations
      +-- storage-adapter     -> azure-storage-blob (no version)
      +-- messaging-adapter   -> azure-messaging-servicebus (no version)
~~~

### Những điểm cần nhớ

- Child modules phải thực sự kế thừa parent hoặc cấu hình BOM đúng nơi.
- BOM trong parent không tự thêm dependency vào từng child.
- Import BOM ở các child với versions khác nhau làm giảm reproducibility.
- Khi parent quản lý Spring Boot và Azure SDK, cần kiểm tra import precedence/version mediation.
- Mỗi executable app cần kiểm tra **runtimeClasspath cuối**, không chỉ dependencies của một adapter module.

## 30. Gradle multi-module và version catalogs

Gradle có thể quản lý các coordinates bằng **version catalogs** cùng dependency constraints/platforms. Một chiến lược:

~~~text
settings.gradle(.kts)
  |
  +--> Version catalog: Azure SDK BOM approved version
  |
  +--> Project modules
        +-- api
        +-- storage-adapter
        +-- messaging-adapter
~~~

Version catalog giúp định danh BOM/artifacts tập trung, nhưng **catalog chỉ chứa aliases/versions**; nó không tự áp mọi dependency alignment nếu các modules không dùng platform hoặc convention plugin phù hợp.

### Khi dùng Gradle Kotlin DSL

~~~kotlin
dependencies {
    implementation(
        platform("com.azure:azure-sdk-bom:REPLACE_WITH_APPROVED_BOM_VERSION")
    )
    implementation("com.azure:azure-storage-blob")
}
~~~

Nếu mỗi module khai báo platform riêng, cần đảm bảo cùng version. Một **convention plugin** được tổ chức phê duyệt có thể giúp áp dependency constraints nhất quán.

## 31. Kiểm tra dependency tree trước khi nâng cấp

**Không thể kết luận version Azure SDK runtime chỉ từ pom.xml hoặc build.gradle**. Cần kiểm tra resolved dependencies.

### Maven

~~~bash
# Chạy ở dự án Java thực hành; KHÔNG chạy trong workflow worker.
mvn dependency:tree -Dincludes=com.azure

# Xem mọi phụ thuộc nếu cần điều tra sâu:
mvn dependency:tree
~~~

### Gradle

~~~bash
# Groovy/Kotlin Gradle dự án Java; chỉ là lệnh tham khảo.
./gradlew dependencies --configuration runtimeClasspath

./gradlew dependencyInsight \
  --dependency azure-core \
  --configuration runtimeClasspath
~~~

Trên Windows có thể dùng **gradlew.bat** thay wrapper POSIX. Các lệnh có thể cần tải metadata từ repository hoặc kích hoạt Gradle plugins, nên phải chạy trong môi trường và scope được cho phép; **worker không thực thi build** cho nhiệm vụ viết bài này.

### Những điều cần ghi

| Artifact | Version được yêu cầu | Version thực tế resolved | Vì sao cần xem |
|---|---|---|---|
| azure-storage-blob | BOM hoặc direct | Dependency tree | Service client API |
| azure-identity | BOM hoặc direct | Dependency tree | Authentication |
| azure-core | Transitive/BOM | Dependency tree | Common API compatibility |
| azure-core-http-netty | Transitive/BOM | Dependency tree | HTTP transport |
| reactor-core | Framework/transitive | Dependency tree | Async client runtime |
| netty-handler | Framework/transitive | Dependency tree | TLS/security/performance |
| jackson-databind | Framework/transitive | Dependency tree | JSON/serialization |

**Không tự nâng Netty/Reactor riêng rẽ** để che một CVE mà không kiểm tra tương thích Azure SDK/Spring Boot: có thể sửa security warning nhưng tạo lỗi runtime.

## 32. Diagnosing: NoSuchMethodError, ClassNotFoundException và linkage

### NoSuchMethodError

Ứng dụng compile với một class/method nhưng runtime load một JAR phiên bản khác không còn phương thức đó.

~~~text
Compile-time:
    Azure SDK X -> azure-core version A

Runtime:
    Một dependency khác chọn azure-core version B (thiếu method)

Kết quả:
    java.lang.NoSuchMethodError
~~~

### ClassNotFoundException/NoClassDefFoundError

Có thể do artifact thiếu, dependency bị exclude, build packaging sai hoặc class không còn trong version runtime.

### UnsupportedClassVersionError

JAR/class được compile cho JDK cao hơn runtime.

### Cách điều tra có hệ thống

1. Xác định **class/method và artifact** xuất hiện trong stack trace.
2. Xem actual runtime dependency graph và packaging (fat JAR/container).
3. Kiểm tra BOM, explicit versions, exclusions và shaded JARs.
4. Xem JDK baseline/runtime image.
5. So với release notes/compatibility matrix.
6. Sửa nguyên nhân alignment rồi chạy integration tests.

**Không thêm hàng chục exclusions mù quáng**. Một exclusion có thể sửa conflict tạm thời nhưng làm mất HTTP transport/serializer ở runtime.

## 33. Dependency conflicts khi dùng Spring

Ví dụ một ứng dụng Spring Boot WebFlux dùng Reactor/Netty. Azure Blob SDK cũng dùng HTTP transport có thể dựa trên Netty.

~~~text
spring-boot-starter-webflux
   -> spring-webflux
   -> reactor-netty
       -> netty-*

azure-storage-blob
   -> azure-core
   -> azure-core-http-netty
       -> netty-*
~~~

### Những gì có thể xảy ra

- Gradle chọn một Netty version theo resolution rules; Maven có cơ chế mediation khác.
- Spring Boot BOM và Azure SDK BOM có thể đề xuất versions khác.
- Một phần ứng dụng có thể chạy bình thường, nhưng khi gọi Azure mới vướng lỗi.
- Vulnerability scanner có thể báo CVE trong transitive Netty.

### Cách xử lý

1. Xác định **resolved Netty/Reactor versions**.
2. Kiểm tra Spring Boot ↔ Azure SDK/HTTP transport compatibility.
3. Nếu dùng Spring Cloud Azure, ưu tiên documented integration và BOM phù hợp.
4. Chỉ override version khi có bằng chứng compatibility.
5. Chạy TLS/integration/load tests trên JDK và image production.

Không tự kết luận “BOM Azure luôn thắng Spring BOM” hoặc ngược lại; kết quả phụ thuộc build tool/import order/constraints và direct versions.

## 34. Kiểm soát alpha/beta/preview dependencies

Đôi khi một Azure feature mới chỉ có SDK preview:

~~~text
azure-some-service:version-beta.N
~~~

### Rủi ro

- API signatures có thể đổi giữa preview releases.
- Runtime behavior hoặc REST API có thể chưa ổn định.
- Artifact có thể chưa xuất hiện trong BOM stable.
- Có giới hạn hỗ trợ production/SLA tùy service.
- Migration sang stable có thể cần code refactor.

### Policy gợi ý

- Ghi lý do cần preview và tính năng phụ thuộc.
- Pin exact preview artifact version.
- Có feature flag/adapter để cô lập preview API.
- Theo dõi release notes và retirement notices.
- Đặt test riêng để thử upgrade.
- Không âm thầm chuyển dependency stable sang preview khi cập nhật BOM.

Nếu service API chưa có Java SDK, xem REST API/HTTP client theo tài liệu chính thức hoặc thư viện được hỗ trợ; không tự sử dụng package trên Maven Central không rõ nhà phát hành.

## 35. Đọc release notes và chọn phiên bản trước khi nâng cấp

Một quy trình nâng cấp Azure SDK cần trả lời:

1. **Artifact đang dùng:** tọa độ Maven nào và version thực tế?
2. **BOM hiện tại:** version nào, có bao phủ artifact đó không?
3. **BOM/SDK ứng viên:** stable hay preview?
4. **Thay đổi API:** phương thức nào bị deprecated hoặc thay signatures?
5. **Thay đổi runtime:** JDK, Reactor, Netty, Jackson hoặc HTTP transport requirements?
6. **Security:** có CVE/fix quan trọng hoặc retirement notice?
7. **Service contract:** REST API, default behavior, retry/timeout thay đổi?
8. **Thử nghiệm:** có đủ tests cho hành vi Azure thật?

### Checklist đối chiếu nguồn chính thức

| Nguồn | Cần tìm |
|---|---|
| Azure SDK release notes | Features, fixes, breaking changes, deprecated APIs |
| Maven Central/Maven metadata | Artifact coordinates, published versions |
| Azure SDK BOM release | Versions được BOM quản lý |
| Javadoc của artifact/version | API methods/overloads/imports đúng |
| GitHub changelog/issues | Known problems, security fixes, migration advice |
| Spring Cloud Azure docs | Spring Boot compatibility và starter support |
| Azure service documentation | REST API, security, region/tier constraints |

**Không xem blog cũ làm nguồn duy nhất** cho dependency versions; cũng không tự suy ra version cao nhất là bản release được dự án hỗ trợ.

## 36. Quy trình nâng cấp BOM không gây bất ngờ

Một bản nâng cấp an toàn:

~~~text
Baseline:
  BOM currently approved
  Dependency graph snapshot
  Test results + runtime JDK
          |
          v
Select candidate BOM from official release
          |
          v
Read release notes / API changes / CVEs
          |
          v
Update BOM version in one controlled change
          |
          v
Resolve and compare dependencies
          |
          v
Compile + unit + integration + security tests
          |
          v
Staging/canary on Azure
          |
          v
Production rollout + monitor
          |
          v
Rollback if thresholds breached
~~~

### Giai đoạn 1: thiết lập baseline

Lưu những thông tin:

- Application commit/tag.
- Current Maven/Gradle versions.
- JDK/toolchain và base image digest.
- Current Azure SDK BOM version.
- Resolved dependency tree hoặc SBOM.
- Danh sách Azure services và API operations thực tế.
- Test/latency/error-rate baseline.

### Giai đoạn 2: cập nhật riêng BOM

Không gộp quá nhiều thay đổi: nâng Azure SDK BOM, nâng Spring Boot major, đổi JDK, thay Netty và tái cấu trúc ứng dụng trong cùng một PR gây khó chẩn đoán.

### Giai đoạn 3: so sánh dependency graph

Chỉ thay một dòng BOM vẫn có thể thay nhiều SDK/artifacts. Xem sự khác biệt để biết:

- azure-core/azure-identity đổi thế nào.
- HTTP transport/Netty/Reactor đổi không.
- Có dependency mới/exclusions không.
- Artifact nào vẫn bị explicit version override.

### Giai đoạn 4: test hành vi

Biên dịch thành công chưa đủ. Cần test **authentication, TLS, read/write, pagination, retries, timeouts, error mapping, serialization** và deployment theo dịch vụ thực.

### Giai đoạn 5: canary + quan sát

Đưa một lượng traffic nhỏ tới bản mới, so sánh p95/p99, error rates, 401/403/429/5xx, retries, thread count, memory, Azure service charges. Khi thất bại, rollback artifact/binary theo kế hoạch đã duyệt.

## 37. CVE, SBOM và supply-chain security

Các thư viện Java phụ thuộc nhiều JAR khác nhau. Một lỗ hổng có thể nằm ở:

- Azure SDK service module.
- azure-core hoặc azure-identity.
- Netty/OpenSSL/JDK TLS stack.
- Jackson hoặc JSON parser.
- Reactor.
- Spring Framework/Spring Boot.
- Container base image hoặc native libraries.

### SBOM là gì?

**Software Bill of Materials** là danh mục những components/versions trong artifact phần mềm. Nó **khác Azure SDK BOM**:

| Khái niệm | Định nghĩa | Mục đích |
|---|---|---|
| **Azure SDK BOM** | POM quản lý versions của nhóm Azure SDK | Dependency alignment |
| **SBOM** | Danh sách components/dependencies thực tế của phần mềm | Kiểm toán, CVE/vulnerability management, supply chain |

Một application sử dụng Azure SDK BOM vẫn có thể có CVE từ dependency transitive hoặc base image. Do đó:

1. Sinh và lưu SBOM cho release theo công cụ được tổ chức hỗ trợ.
2. Scan dependencies và container images.
3. Triage theo exploitability và actual runtime paths.
4. Ưu tiên security patches tương thích.
5. Nếu cần explicit override, ghi lý do, thời hạn và tests.
6. Xem cả **direct** và **transitive** dependencies.

### Không nên xử lý CVE bằng force-version mù quáng

Ví dụ một scanner đề xuất phiên bản Netty mới, nhưng Azure SDK HTTP transport đang dùng một API không tương thích. Bắt buộc phải kiểm tra compatibility và network tests. Một bản vá phá application availability vẫn là rủi ro; đôi khi giải pháp an toàn là nâng **Azure SDK BOM/Spring BOM đồng bộ** thay vì ép Netty riêng.

## 38. Chính sách versions trong CI/CD

Một chính sách mẫu:

| Nhóm dependency | Chính sách |
|---|---|
| Azure stable SDKs | BOM version cố định theo kỳ release |
| Azure preview SDKs | Pin exact version, cần owner/phê duyệt riêng |
| Spring Boot/Cloud Azure | Upgrade theo compatibility matrix |
| JDK | LTS được phê duyệt, image digest/tag cố định |
| Critical security patches | Ưu tiên review ngoài chu kỳ thông thường |
| Transitive overrides | Chỉ khi có documented reason và tests |
| Snapshot dependencies | Hạn chế/không cho phép trong production releases |
| Build plugins | Pin versions và kiểm tra plugin upgrades |

### Lock files và dependency resolution

Gradle có **dependency locking** tùy cấu hình để giữ resolved versions. Maven có thể tái lập tốt hơn bằng explicit parent/BOM versions, dependency verification hoặc các công cụ quản lý riêng.

Locking không thay thế BOM: **BOM quản lý constraints**, còn lock files/verification giúp xác định một graph cụ thể theo công cụ build. Cần kiểm tra khi nâng BOM để cập nhật lock state đúng và review diff.

### Tránh dependency ranges/snapshots không kiểm soát

Đặt version range mở cho Azure SDK hoặc kéo SNAPSHOT từ repository bên ngoài khiến hai lần build có thể tạo sản phẩm khác nhau. Sử dụng phiên bản được phê duyệt và repository artifact đáng tin; tránh tải dependencies từ địa chỉ lạ không có kiểm soát.

## 39. Release và rollback trong dự án Java trên Azure

~~~text
Release v1
  Azure SDK BOM B1
  JDK image I1
  Dependency/SBOM snapshot S1
       |
       v
Canary release v2
  BOM B2
  JDK image I1
  SBOM S2
       |
       +--> Metrics tốt -> tăng traffic
       |
       +--> NoSuchMethodError/5xx -> rollback v1
~~~

### Những yếu tố rollback cần giữ

- Original commit/tag và build artifact không bị ghi đè.
- Original container image digest.
- Original BOM và resolved graph.
- IaC/Helm/App Service deployment configuration.
- Monitoring dashboards và error budget.
- Kiến thức về data migrations/schema changes.

**Rollback Java JAR không tự rollback dữ liệu đã ghi**. Nếu SDK update đi kèm đổi schema, API version hoặc thay đổi dữ liệu trong Azure, cần kế hoạch backward compatibility và dữ liệu riêng.

### Hai giai đoạn khác nhau

**Canary:** quan sát ứng dụng dưới lượng traffic nhỏ.

**Rollback:** chuyển về artifact cũ đã kiểm thử, không phải cố gắng sửa BOM trực tiếp trên pod đang chạy.

## 40. Observability và diagnostics của Azure SDK

Khi một client gặp lỗi, cần thông tin:

- Azure service operation và HTTP status.
- Service request/correlation ID khi response cung cấp.
- Retry count/backoff và tổng thời gian request.
- Network/TLS/authentication failure category.
- Endpoint/service region (không tiết lộ secrets).
- Application trace/span ID.
- SDK versions và JDK version trong release metadata.

### Những nội dung không được log

- Access tokens, SAS query strings.
- Storage account keys, connection strings chứa bí mật.
- Key Vault secret values.
- PII trong request/response bodies.
- Full authorization headers.
- Client certificate/private keys.

### HTTP logging có rủi ro

Một số service builders hỗ trợ **HttpLogOptions** hoặc logging policies. Chi tiết body/headers có thể chứa thông tin nhạy cảm. Trước khi bật logging chi tiết trong production:

1. Xác định loại operation.
2. Dùng redaction/allowlist theo SDK và logging system.
3. Giới hạn quyền đọc logs, retention, storage và export.
4. Đặt sampling/volume budget.
5. Test rằng authorization/connection strings không xuất hiện.

**Debug logging không nên tự động bật lâu dài** chỉ để giải quyết một lỗi 403.

## 41. Azure SDK và OpenTelemetry

Trong hệ microservices Java, tracing giúp phân biệt:

~~~text
HTTP incoming request
     |
     +--> Spring controller
     |
     +--> Azure Blob SDK call
     |       +--> DNS/network
     |       +--> retries
     |       +--> Azure Storage response
     |
     +--> Azure Service Bus SDK call
     |
     v
HTTP response
~~~

Azure SDK có những hooks hoặc integrations phục vụ telemetry theo thư viện/phiên bản. Hãy sử dụng cấu hình supported (OpenTelemetry, Azure Monitor, Micrometer hoặc tracing options phù hợp), không tự ghi access tokens vào spans.

### Metrics cần có

| Metric | Công dụng |
|---|---|
| SDK request latency p50/p95/p99 | SLO và hiệu năng |
| HTTP status distribution | Phân loại lỗi service |
| Number of retries | Phát hiện throttling/network |
| 401/403 error rate | Credential/authorization issues |
| 429 rate | Capacity/quota/throttling |
| Connection/TLS errors | Transport/network diagnosis |
| Thread/connection pool size | Resource exhaustion |
| Service costs/transactions | Quản lý chi phí |
| Dependency version | Truy vết regression sau release |

Một số metrics cần instrument thủ công hoặc qua agent; không mặc định mọi tên metric có sẵn trong Azure Monitor.

## 42. Test pyramid khi dùng Azure SDK

| Cấp test | Ví dụ | Hạn chế |
|---|---|---|
| **Unit test** | Mock adapter/interface để kiểm logic không gọi Azure | Không kiểm auth/network/API contract |
| **Contract test** | Kiểm DTO, serialization, endpoint/options | Không thay service thật |
| **Integration test** | Gọi Azure resource lab với identity/network thực | Có chi phí, quota, cleanup |
| **Performance test** | Kiểm concurrency, retry, latency, memory | Cần môi trường và load policy |
| **Security test** | Role least privilege, secret redaction, TLS | Cần identities/permissions thực |
| **Release canary** | Một phần traffic production dùng SDK mới | Cần rollback và telemetry |

### Nên bọc SDK bằng adapter

~~~text
Business service
     |
     v
BlobMetadataReader (interface)
     |
     +--> Fake/Stub implementation for unit tests
     |
     +--> AzureBlobMetadataReader -> BlobClient for integration
~~~

Adapter giúp unit test không phụ thuộc cloud credentials và tránh unit tests vô tình gọi Azure production. Tuy vậy, mock quá nhiều cũng che lỗi integration; cả hai cấp kiểm thử đều cần.

## 43. Ví dụ adapter Java tách business logic khỏi SDK

Giao diện đơn giản:

~~~java
public interface BlobMetadataReader {
    boolean exists(String blobName);
}
~~~

Implementation dùng Azure Blob:

~~~java
import com.azure.storage.blob.BlobContainerClient;

public final class AzureBlobMetadataReader
        implements BlobMetadataReader {

    private final BlobContainerClient container;

    public AzureBlobMetadataReader(
            BlobContainerClient container) {
        this.container = container;
    }

    @Override
    public boolean exists(String blobName) {
        return container
            .getBlobClient(blobName)
            .exists();
    }
}
~~~

Stub trong unit test:

~~~java
import java.util.Set;

public final class FakeBlobMetadataReader
        implements BlobMetadataReader {

    private final Set<String> existing;

    public FakeBlobMetadataReader(Set<String> existing) {
        this.existing = existing;
    }

    @Override
    public boolean exists(String blobName) {
        return existing.contains(blobName);
    }
}
~~~

### Giá trị của adapter

- Business service không cần import BlobServiceClient trực tiếp.
- Unit tests không cần token/HTTP/network.
- Migration Blob SDK có điểm sửa giới hạn.
- Có thể thêm metrics/retry/error translation trong một adapter.

### Giới hạn

Stub không kiểm hành vi thật khi Blob trả 403, 429 hoặc timeout. Cần integration tests với identity và Azure resources lab. Không dùng unit tests làm bằng chứng duy nhất rằng BOM mới tương thích production.

## 44. Lab A: xây đồ thị phiên bản Maven

**Mục tiêu:** sử dụng Azure SDK BOM để thống nhất versions mà không tạo tài nguyên Azure. Bài này là **hướng dẫn để người học tự thực hiện** trong một Java project lab; worker tạo tài liệu không chạy Maven/Gradle.

### Chuẩn bị

1. JDK LTS được phê duyệt và Maven phù hợp.
2. Repository Maven Central/proxy được tổ chức tin cậy.
3. POM mẫu từ mục 21 đã thay version BOM bằng bản thực được kiểm duyệt.
4. Quyền tải dependencies trong môi trường dev.

### Các bước

1. Tạo dự án Maven lab riêng.
2. Thêm Azure SDK BOM ở dependencyManagement.
3. Thêm **azure-identity**, **azure-storage-blob**.
4. Chạy lệnh xem dependencies:

~~~bash
mvn dependency:tree -Dincludes=com.azure
~~~

5. Xem versions của **azure-core** và service SDK.
6. Kiểm tra POM thật không còn direct version overrides không có lý do.
7. Thêm thư viện **azure-security-keyvault-secrets** không khai báo version.
8. Xem graph thay đổi thế nào.
9. Nếu có bom release mới được duyệt, thay **chỉ BOM version** và so sánh diff.
10. Không gọi Azure service thật nếu chưa có account lab và permission.

### Nghiệm thu

| Câu hỏi | PASS khi |
|---|---|
| BOM imported? | Maven import thành công |
| Service SDK declared? | Có đúng dependency cần dùng |
| Version source? | Version đến từ BOM hoặc override có giải thích |
| azure-core resolved? | Biết version cuối cùng |
| Build environment? | JDK/runtime target rõ |
| Security? | Không tải JAR từ repository không tin cậy |
| Output? | Có dependency tree snapshot để review |

### Phân biệt lỗi

- **Maven không resolve BOM**: placeholder chưa thay, repository/offline/network lỗi.
- **Package không tìm thấy**: thiếu service dependency.
- **NoSuchMethodError khi runtime**: xem resolved graph và packaging.
- **403 khi gọi Azure**: thường liên quan identity/data-plane rights/network, không đồng nghĩa BOM lỗi.

## 45. Lab B: Gradle dependencyInsight

Trong dự án Gradle riêng:

1. Thêm platform Azure SDK BOM như mục 22.
2. Thêm azure-identity và azure-storage-blob không ghi versions.
3. Kiểm tra **runtimeClasspath**:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

4. Tìm cách Gradle chọn azure-core:

~~~bash
./gradlew dependencyInsight \
  --dependency azure-core \
  --configuration runtimeClasspath
~~~

5. Thử thêm một library/framework do dự án đã có và so sánh version selection.
6. Nếu thấy xung đột, không áp enforcedPlatform trước khi có đánh giá.
7. Ghi lại dependency graph và phương án nâng BOM hợp lệ.

### Kiểm tra cần ghi

~~~text
Selected azure-core version: <resolved-version>
Selection reason:             <BOM/constraint/conflict-resolution>
Azure Blob SDK version:       <resolved-version>
Azure Identity version:       <resolved-version>
Runtime JDK:                  <tested-jdk>
~~~

Kết quả placeholder phải được thay bằng output thực của lab; không điền con số đoán.

## 46. Lab C: thực hiện read-only Blob call

**Mục tiêu:** chứng minh sau khi dependency graph ổn, Java client có thể xác thực và đọc metadata trên Azure.

### Điều kiện

- Storage account/container/blob **lab** đã được cấp quyền.
- Environment variables: AZURE_BLOB_ENDPOINT, AZURE_BLOB_CONTAINER, AZURE_BLOB_NAME.
- Developer identity hoặc managed identity có **Storage Blob Data Reader**.
- TLS và đường mạng hợp lệ.
- POM/Gradle dùng các libraries tương thích.

### Quy trình

1. Xem resolved dependency graph.
2. Chạy chương trình Java ở mục 8 trong dự án lab.
3. Quan sát output **Blob exists: true/false**.
4. Chạy thử identity không có data-plane role **nếu đã được phê duyệt**, quan sát lỗi quyền.
5. Thu thập request duration/status ở mức an toàn, không log credentials.
6. Sau khi nâng BOM theo kế hoạch, chạy lại cùng test.
7. So sánh behavior, errors và latency, không chỉ so phiên bản.

### Kết quả mong đợi

**PASS kỹ thuật** khi đã xác định được client xây thành công, credential lấy token đúng identity, request tới Blob trả kết quả được phép và logs không lộ secrets. **False không nhất thiết lỗi**, vì blob có thể không tồn tại; lỗi auth/network cần phân loại riêng.

## 47. Case study: Spring Boot API dùng bốn dịch vụ Azure

Một công ty chạy Java 17/Spring Boot trong AKS:

- Azure Blob Storage: lưu tài liệu khách hàng.
- Azure Key Vault: cung cấp secret nghiệp vụ không thể tránh.
- Azure Service Bus: gửi sự kiện đơn hàng.
- Azure Cosmos DB: đọc ghi giỏ hàng.
- Microsoft Entra Workload ID: authentication từ pods.
- Private Endpoints và outbound firewall được kiểm soát.
- CI/CD sử dụng Gradle multi-module.
- Một nhóm muốn nâng Azure SDK vì CVE, nhóm khác đang định nâng Spring Boot major.

### Nhiệm vụ

1. Phân loại artifacts **data-plane SDK, identity/core, Spring integrations và management SDK**.
2. Chọn dùng direct Azure SDK hay Spring Cloud Azure starters cho từng integration, giải thích.
3. Thiết kế BOM ownership cho các Gradle modules.
4. Kiểm tra azure-core, Reactor, Netty versions trên **runtimeClasspath**.
5. Giải thích vì sao không đồng thời nâng SDK BOM và Spring Boot major trong một thay đổi khó rollback.
6. Mô tả cách AKS Workload Identity cung cấp TokenCredential.
7. Gán RBAC tối thiểu cho Blob/Key Vault/Service Bus/Cosmos.
8. Kiểm tra Private DNS/TLS tới từng Azure endpoint.
9. Phân biệt retry an toàn của GET Blob và publish/gửi message nghiệp vụ.
10. Thiết kế adapter/test để business service không gắn chặt với SDK classes.
11. Tạo danh sách integration tests cho 401, 403, 404, 429, 5xx và timeout.
12. Ghi SBOM và các artifact versions trong release.
13. Phân biệt quyền xem Key Vault resource với quyền get secret.
14. Lập canary/rollback plan cho cập nhật dependency.
15. Giải thích vì sao không dùng management SDK của runtime API để tạo storage account trong mỗi request.

### Gợi ý giải pháp

~~~text
Spring Boot Java API
     |
     +-- Business interfaces/adapters
     |      |
     |      +-- Blob SDK
     |      +-- Key Vault SDK
     |      +-- Service Bus SDK
     |      +-- Cosmos SDK
     |
     +-- Managed/Workload Identity -> azure-identity
     |
     +-- Approved BOM(s) + JDK toolchain
     |
     +-- OpenTelemetry/Micrometer instrumentation
     |
     v
AKS runtime with private DNS + approved egress
     |
     v
Azure data-plane services
~~~

Chọn chiến lược BOM từ **compatibility matrix**: nếu dự án dùng nhiều Spring Cloud Azure starters, cần ưu tiên combo Spring Boot/Spring Cloud Azure được hỗ trợ và kiểm tra Azure SDK versions thực tế. Nếu chỉ dùng direct SDK, Azure SDK BOM có thể là baseline thuận tiện. Không tự thêm một BOM thứ hai chỉ vì kết quả dependency tree chưa vừa ý.

## 48. Lỗi phổ biến khi sử dụng Azure SDK for Java

| Nhận định/sai lầm | Vì sao nguy hiểm | Cách làm đúng |
|---|---|---|
| “Một Azure SDK JAR chứa mọi dịch vụ” | Thiếu đúng client library | Chọn artifact theo service |
| “Import BOM là có sẵn BlobClient” | BOM chỉ quản lý versions | Khai báo azure-storage-blob dependency |
| “Mọi com.azure.* có trong azure-sdk-bom” | BOM chỉ quản lý tập artifacts cụ thể | Kiểm tra BOM release contents |
| “BOM version bằng azure-core version” | Hai version schemes khác nhau | Kiểm tra resolved artifact versions |
| “Có azure-identity là tự có quyền Azure” | Credential khác RBAC | Gán identity và role đúng |
| “Contributor có quyền đọc mọi blob” | Data plane khác management plane | Kiểm tra Storage data roles |
| “Client builder gọi Azure ngay” | Builder/client creation có thể chưa gửi service request | Xác minh operation thực |
| “Async Mono không cần subscribe” | Lazy execution có thể không chạy | Quản lý subscription/lifecycle đúng |
| “Dùng block() trong WebFlux không sao” | Có thể block event-loop | Dùng reactive chain hoặc sync API ở thread phù hợp |
| “List blobs miễn phí vì chỉ đọc” | Có service requests và transaction costs | Paging/filters/monitoring |
| “HTTP 202 nghĩa là resource sẵn sàng” | Long-running operation đang chạy | Theo dõi Poller |
| “BOM xử lý mọi CVE” | Transitives/base images vẫn có thể lỗi | SBOM + scanning |
| “Nâng SDK và Spring major cùng lúc luôn tốt” | Khó cô lập regression | Nâng từng lớp có test |
| “Force Netty version sẽ sửa tất cả” | Có thể phá transport compatibility | Review dependency tree và matrix |
| “ClassNotFound do Azure outage” | Thường là classpath/packaging | Kiểm tra runtime graph |
| “Cứ retry 403 cho đến khi thành công” | Thiếu quyền không được sửa bằng retry | Sửa identity/RBAC |
| “Tắt TLS verification để fix PKIX” | Nguy cơ MITM | Sửa DNS/truststore/certificate |
| “Dùng service principal secret trong Git tiện hơn” | Rò rỉ credentials | Managed identity/Key Vault |
| “Roll back JAR là dữ liệu quay lại” | Data changes tồn tại độc lập | Kế hoạch schema/data rollback |
| “Unit tests mock thành công là production-ready” | Chưa test Azure service thật | Integration/canary tests |

## 49. Checklist triển khai và nâng cấp production

| Nhóm | Điều phải xác nhận |
|---|---|
| Service selection | Chọn đúng artifact cho từng Azure service |
| SDK generation | Không trộn Track 1/Track 2 không có migration plan |
| Data vs management | Runtime identity chỉ có quyền cần thiết |
| BOM | Có một nguồn version rõ; artifacts nằm trong BOM được xác nhận |
| Spring integration | Spring Boot/Cloud Azure matrix được kiểm tra |
| Build tools | Maven/Gradle versions và plugins phù hợp |
| JDK | Toolchain/bytecode/runtime/JDK security updates khớp |
| Dependency graph | Runtime versions của azure-core/Netty/Reactor được ghi |
| SBOM/security | Có dependency và image scanning, CVE triage |
| Preview libraries | Pin exact version, có approval và exit plan |
| Identity | Managed identity/Workload ID, không hard-code tokens |
| RBAC | Data-plane roles/ACL tối thiểu |
| Network | Private DNS, firewall, TLS certificates và trusted CAs |
| Client lifecycle | Reuse clients, transport/thread ownership rõ |
| Retry/timeouts | Bounded retries, deadlines, no retry storm |
| Paging | Không list toàn bộ data không cần thiết |
| Error handling | 401/403/404/409/412/429/5xx phân loại đúng |
| Logging | Không lộ SAS, tokens, secrets hoặc PII |
| Monitoring | p95/p99 latency, status codes, retries, service charges |
| Test coverage | Unit/integration/performance/security tests |
| Canary | Rollout có giới hạn và ngưỡng rollback |
| Backups | Dữ liệu/metadata quan trọng có phương án khôi phục |
| Cost | Theo dõi transactions, requests, storage, logs, egress |
| Documentation | Ghi versions, owners, release notes và rollback |

## 50. Câu hỏi tự kiểm tra

1. Azure SDK for Java là một JAR duy nhất hay nhiều libraries?
2. Phân biệt data plane và management plane SDK.
3. azure-core và azure-identity có chức năng khác nhau thế nào?
4. BlobServiceClientBuilder được dùng để làm gì?
5. Builder tạo BlobClient có tự gửi HTTP request không?
6. Khi nào nên tái sử dụng service client?
7. Track 1 và Track 2 khác nhau ở những điểm nào?
8. Sync client và async client khác ở cách trả kết quả ra sao?
9. Mono và Flux biểu diễn loại kết quả nào?
10. Vì sao quên subscribe có thể khiến async operation không chạy?
11. Vì sao gọi block() trên WebFlux event-loop có rủi ro?
12. PagedIterable giúp giải quyết vấn đề gì?
13. Vì sao list hàng triệu blobs có thể tốn tiền?
14. Poller và HTTP 202 liên quan như thế nào?
15. HTTP pipeline thường có những policies nào?
16. Netty/OkHttp nằm ở lớp nào?
17. DefaultAzureCredential có tự cấp Storage Blob Data Reader không?
18. ManagedIdentityCredential khác AzureCliCredential ở môi trường sử dụng thế nào?
19. Tại sao lỗi 403 không nên retry vô hạn?
20. BOM là gì, và import BOM có tự thêm service SDK không?
21. Maven dependencyManagement khác dependencies như thế nào?
22. Vì sao Gradle platform không luôn tương đương enforcedPlatform?
23. BOM version có phải bằng version của mọi SDK không?
24. azure-sdk-bom có quản lý Spring Cloud Azure không?
25. Vì sao cần xem Spring Boot ↔ Spring Cloud Azure compatibility matrix?
26. Management SDK artifacts có thể cần cơ chế version riêng không?
27. Preview SDK có những rủi ro release nào?
28. JDK runtime thấp hơn bytecode target gây lỗi gì?
29. Dependency tree khác file build dependency declarations ở đâu?
30. NoSuchMethodError và ClassNotFoundException có thể do nguyên nhân gì?
31. Tại sao cần kiểm tra Reactor/Netty khi nâng Azure SDK trong WebFlux?
32. Version lock khác BOM ở mục đích gì?
33. Azure SDK BOM và SBOM khác nhau thế nào?
34. Vì sao một CVE trong dependency transitive vẫn có thể tồn tại dù dùng BOM?
35. Những bước nào nên thực hiện khi đổi BOM version?
36. Vì sao cần canary và rollback binary image digest?
37. Tại sao rollback JAR không tự rollback dữ liệu?
38. Những gì không được log trong HTTP client diagnostics?
39. Unit test với fake BlobMetadataReader kiểm điều gì, và không kiểm điều gì?
40. Những tiêu chí nào chứng minh nâng Azure SDK an toàn trong ứng dụng Java production?

## Tài liệu tham khảo

- Microsoft Learn — *Azure SDK for Java overview*: https://learn.microsoft.com/azure/developer/java/sdk/overview
- Microsoft Learn — *Get started with Azure SDK for Java*: https://learn.microsoft.com/azure/developer/java/sdk/get-started
- Microsoft Learn — *Use Azure SDK for Java with Maven*: https://learn.microsoft.com/azure/developer/java/sdk/get-started
- Azure SDK for Java — *SDK release index and packages*: https://azure.github.io/azure-sdk/releases/latest/java.html
- Azure SDK — *Java libraries GitHub repository*: https://github.com/Azure/azure-sdk-for-java
- Azure SDK — *Dependency/BOM guidance in SDK repository*: https://github.com/Azure/azure-sdk-for-java/tree/main/sdk/boms
- Maven Central — *Azure SDK BOM artifact*: https://central.sonatype.com/artifact/com.azure/azure-sdk-bom
- Microsoft Learn — *Authenticate Java apps with Azure Identity*: https://learn.microsoft.com/azure/developer/java/sdk/authentication/overview
- Microsoft Learn — *DefaultAzureCredential in Java*: https://learn.microsoft.com/azure/developer/java/sdk/authentication/credential-chains
- Microsoft Learn — *Azure Storage Blob Java SDK*: https://learn.microsoft.com/azure/storage/blobs/storage-quickstart-blobs-java
- Microsoft Learn — *Manage Azure resources with Azure SDK for Java*: https://learn.microsoft.com/azure/developer/java/sdk/management
- Microsoft Learn — *Spring Cloud Azure*: https://learn.microsoft.com/azure/developer/java/spring-framework/
- Spring Cloud Azure — *Reference documentation*: https://microsoft.github.io/spring-cloud-azure/current/reference/html/index.html
- Microsoft Learn — *Azure SDK design guidelines*: https://azure.github.io/azure-sdk/java_introduction.html
- Maven — *Dependency mechanism*: https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html
- Gradle — *Platforms and dependency constraints*: https://docs.gradle.org/current/userguide/platforms.html
- Gradle — *Viewing dependencies*: https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html
- Azure Pricing Calculator: https://azure.microsoft.com/pricing/calculator/
