# Tái sử dụng client, connection pool và HTTP transport

Một ứng dụng Spring Boot có thể gọi hàng nghìn request mỗi phút tới S3, Azure Blob Storage, Cosmos DB, PostgreSQL, Pub/Sub hoặc các REST API. Nếu mỗi request lại tạo một SDK client hay HTTP client mới, ứng dụng liên tục phải khởi tạo credential, DNS lookup, TCP/TLS handshake và connection pool. Kết quả là độ trễ tăng, CPU và memory bị lãng phí, số socket tăng nhanh và hệ thống dễ gặp lỗi cạn connection hoặc cạn ephemeral port.

Thiết kế phổ biến cho workload server là **tạo client lâu dài theo một cấu hình kết nối, tái sử dụng client đó giữa các request và quản lý connection pool theo vòng đời ứng dụng**. AWS SDK for Java 2.x, Azure SDK for Java, Google Cloud Java libraries và Spring Boot đều có cơ chế hỗ trợ cách làm này. Tuy vậy, mỗi SDK có ranh giới chia sẻ transport và quy tắc đóng tài nguyên riêng; không nên áp dụng một công thức giống hệt cho cả ba cloud.

Bài thuộc chương **Hiệu năng và chi phí** của mô-đun **SPRING_CLOUD_PROVIDER_INTEGRATION**. Mô-đun thực hành tích hợp Spring Boot với các dịch vụ managed của AWS, Azure và Google Cloud qua thư viện Spring Cloud tương ứng, bao gồm cấu hình danh tính/quyền, storage, messaging, dữ liệu, bảo vệ secret, kiểm thử tích hợp và đánh giá khác biệt giữa cloud provider. Bài này tập trung vào tái sử dụng client, HTTP transport, connection pool và vòng đời tài nguyên khi chạy production.

## 1. Kết quả học tập

Sau bài học, bạn có thể:

- Phân biệt service client, HTTP transport, connection pool, socket và credential provider.
- Giải thích vì sao SDK client nên có vòng đời dài và thường được chia sẻ giữa nhiều thread.
- Đăng ký AWS, Azure và Google Cloud client thành Spring singleton bean.
- Phân biệt pool nằm trong service client hay trong HTTP transport được chia sẻ.
- Cấu hình Apache 5, Netty, Azure HTTP pipeline và Google gRPC channel theo workload.
- Chọn pool size, concurrency, pending queue và timeout theo tải thực tế.
- Quản lý stream response, connection reuse, DNS, keepalive và shutdown.
- Đo connection acquisition latency, pool saturation, request latency và chi phí tài nguyên.

## 2. Các lớp tài nguyên trong một request

Khi gọi một dịch vụ cloud qua SDK, ứng dụng thường đi qua nhiều lớp:

~~~mermaid
flowchart TD
    A[Spring service / application request] --> B[Cloud SDK service client]
    B --> C[Credential provider]
    B --> D[HTTP pipeline / policies]
    D --> E[HTTP transport]
    E --> F[Connection pool]
    F --> G[TCP socket / TLS session]
    G --> H[Managed cloud endpoint]
~~~

- **Service client:** API cấp cao như `S3Client`, `BlobServiceClient`, `Storage` hoặc `KeyManagementServiceClient`. Nó biết endpoint, region/project, credential và cách gọi API.
- **Credential provider:** lấy hoặc làm mới token/credential. Việc khởi tạo nhiều provider có thể nhân số lần đọc file, gọi metadata endpoint hoặc trao đổi token.
- **HTTP pipeline:** chạy authentication, retry, logging, tracing, telemetry và các policy trước/sau request.
- **HTTP transport:** thực hiện network I/O, ví dụ Apache HttpClient, Netty, OkHttp hoặc JDK HttpClient.
- **Connection pool/channel:** giữ kết nối đã mở để request tiếp theo tái sử dụng; với gRPC, tài nguyên tương ứng là channel và các HTTP/2 stream.
- **TCP/TLS:** tạo socket, phân giải DNS, bắt tay TCP và thương lượng TLS. Đây là chi phí đáng kể nếu lặp lại cho từng request.

Một service client có thể sở hữu transport riêng hoặc dùng transport được ứng dụng chia sẻ. Vì vậy, cần đọc đúng mô hình của SDK trước khi quyết định số client và số pool. Tạo thêm service client không phải lúc nào cũng tạo thêm socket pool; ngược lại, hai client riêng có thể đang tạo hai pool dù cùng gọi một host.

## 3. Vì sao nên tái sử dụng client?

### 3.1. Chi phí của client-per-request

Một cách triển khai dễ viết nhưng tốn tài nguyên:

~~~java
public BlobClient createBlobClient(String container, String blob) {
    return new BlobClientBuilder()
        .endpoint(endpoint)
        .credential(credential)
        .containerName(container)
        .blobName(blob)
        .buildClient();
}

public byte[] download(String container, String blob) {
    BlobClient client = createBlobClient(container, blob);
    return client.downloadContent().toBytes();
}
~~~

Nếu method này được gọi liên tục, ứng dụng có thể liên tục tạo pipeline, transport, pool, background thread hoặc cache credential. Một số SDK dùng tài nguyên toàn cục nên không phải lần tạo client nào cũng tạo một socket mới; tuy nhiên, tạo client liên tục vẫn lặp lại phần khởi tạo và làm khó quản lý vòng đời.

### 3.2. Dùng client lâu dài

Tạo client một lần khi ứng dụng khởi động rồi inject vào service:

~~~java
@Service
public class BlobDownloadService {
    private final BlobContainerClient container;

    public BlobDownloadService(BlobContainerClient container) {
        this.container = container;
    }

    public byte[] download(String blobName) {
        return container.getBlobClient(blobName)
            .downloadContent()
            .toBytes();
    }
}
~~~

Đối tượng con như `BlobClient` thường chỉ là wrapper cho endpoint/container/blob; tạo wrapper theo từng thao tác có thể nhẹ hơn tạo lại transport. Hãy xem API của SDK để biết builder nào tạo tài nguyên mạng và builder nào chỉ tạo đối tượng mô tả resource.

Lợi ích chính của tái sử dụng:

- Giảm DNS lookup, TCP connect và TLS handshake lặp lại.
- Giảm số pool, socket, event-loop và background thread.
- Tận dụng credential/token cache và các pipeline policy đã khởi tạo.
- Giảm latency đầu request và áp lực lên hệ điều hành/NAT.
- Có một nơi tập trung để cấu hình timeout, proxy, TLS, retry và metrics.

### 3.3. Client nào có thể chia sẻ?

Không nên dùng một client cho mọi endpoint hoặc mọi identity. Một client thường gắn với một bộ cấu hình bất biến:

`(service type, endpoint, region/project, credential, transport, policy)`

Nếu một trong các yếu tố này thay đổi, tạo client riêng cho cấu hình đó. Ví dụ ứng dụng gọi hai AWS region, hai Azure storage account hoặc hai Google Cloud project có thể cần các client riêng. Với ứng dụng đa tenant có endpoint/credential động, dùng registry có giới hạn số lượng và chính sách eviction; không giữ một client vô hạn cho mỗi user.

## 4. Spring quản lý client theo singleton bean

Spring bean mặc định có scope singleton trong một ApplicationContext. Đây là nơi phù hợp để tạo SDK client dùng chung:

~~~java
@Configuration(proxyBeanMethods = false)
public class CloudClientConfiguration {

    @Bean
    SomeCloudClient someCloudClient() {
        return SomeCloudClient.builder()
            .endpoint(System.getenv("SERVICE_ENDPOINT"))
            .build();
    }
}
~~~

Đây là ví dụ cấu trúc; builder và quy tắc shutdown cụ thể phụ thuộc SDK. Service chỉ nhận client qua constructor injection. Không gọi builder trong controller, repository method hoặc vòng lặp xử lý từng message.

### 4.1. Singleton không có nghĩa là một client cho mọi cấu hình

Có thể khai báo nhiều singleton bean theo endpoint/region khác nhau:

~~~java
@Bean("primaryStorage")
StorageClient primaryStorage() {
    return buildStorageClient(primaryEndpoint);
}

@Bean("archiveStorage")
StorageClient archiveStorage() {
    return buildStorageClient(archiveEndpoint);
}
~~~

Đoạn code minh họa cấu trúc bean; `buildStorageClient`, `primaryEndpoint` và `archiveEndpoint` là hàm/giá trị cấu hình của ứng dụng.

Mỗi bean đại diện cho một cấu hình ổn định. Đặt tên bean rõ ràng và inject bằng `@Qualifier` khi cần. Không thay endpoint hoặc credential dùng chung trong một client đang phục vụ request đồng thời.

### 4.2. Builder và client có vòng đời khác nhau

Builder thường là đối tượng cấu hình tạm thời, không nên dùng chung giữa nhiều thread nếu API không bảo đảm thread-safe. Tạo builder trong cấu hình bean, gọi `build()` một lần rồi chia sẻ client. Với Spring Boot `WebClient.Builder` và `RestClient.Builder`, builder được auto-configure và có thể mang trạng thái; clone khi cần các biến thể cấu hình khác nhau.

## 5. AWS SDK for Java 2.x

### 5.1. Service client là thread-safe

AWS SDK for Java 2.x xác nhận service client là thread-safe và khuyến nghị tạo một instance cho mỗi cấu hình dịch vụ rồi dùng lại trong toàn ứng dụng. Mỗi service client mặc định có HTTP connection pool riêng. Tạo nhiều client cho cùng một service/configuration có thể tạo nhiều pool nhỏ, lãng phí connection và tài nguyên.

Nếu cần dùng chung pool cho nhiều service client, SDK cho phép truyền cùng một HTTP client instance vào nhiều builder. Khi làm vậy, ứng dụng chịu trách nhiệm đóng HTTP client được chia sẻ sau khi các service client đã dừng.

### 5.2. Cấu hình synchronous client với Apache 5

AWS SDK 2.x có HTTP transport đồng bộ như Apache 5. Apache 4-based `ApacheHttpClient` đã bị deprecated vì Apache HttpClient 4.x đang ở chế độ maintenance; với cấu hình mới, ưu tiên `Apache5HttpClient`.

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>software.amazon.awssdk</groupId>
            <artifactId>bom</artifactId>
            <version>${aws.sdk.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>software.amazon.awssdk</groupId>
        <artifactId>s3</artifactId>
    </dependency>
    <dependency>
        <groupId>software.amazon.awssdk</groupId>
        <artifactId>apache5-client</artifactId>
    </dependency>
</dependencies>
~~~

Đăng ký HTTP client và S3 client thành bean:

~~~java
import java.time.Duration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import software.amazon.awssdk.http.SdkHttpClient;
import software.amazon.awssdk.http.apache5.Apache5HttpClient;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;

@Configuration(proxyBeanMethods = false)
public class AwsClientConfiguration {

    @Bean(destroyMethod = "close")
    SdkHttpClient awsSyncHttpClient() {
        return Apache5HttpClient.builder()
            .maxConnections(80)
            .connectionTimeout(Duration.ofSeconds(3))
            .connectionAcquisitionTimeout(Duration.ofSeconds(2))
            .connectionMaxIdleTime(Duration.ofSeconds(45))
            .build();
    }

    @Bean(destroyMethod = "close")
    S3Client s3Client(SdkHttpClient awsSyncHttpClient) {
        return S3Client.builder()
            .region(Region.AP_SOUTHEAST_1)
            .httpClient(awsSyncHttpClient)
            .overrideConfiguration(config -> config
                .apiCallAttemptTimeout(Duration.ofSeconds(10))
                .apiCallTimeout(Duration.ofSeconds(25)))
            .build();
    }
}
~~~

Các con số là ví dụ ban đầu để benchmark, không phải giá trị chuẩn cho mọi ứng dụng. `maxConnections` là giới hạn connection của HTTP client; `connectionAcquisitionTimeout` là thời gian chờ mượn connection; `apiCallAttemptTimeout` giới hạn một lần thử; `apiCallTimeout` giới hạn toàn bộ API call kể cả retry.

Nếu thêm `DynamoDbClient` hoặc service client khác và truyền cùng `SdkHttpClient`, chúng có thể dùng chung pool tương thích:

~~~java
import software.amazon.awssdk.services.dynamodb.DynamoDbClient;

@Bean(destroyMethod = "close")
DynamoDbClient dynamoDbClient(SdkHttpClient awsSyncHttpClient) {
    return DynamoDbClient.builder()
        .region(Region.AP_SOUTHEAST_1)
        .httpClient(awsSyncHttpClient)
        .build();
}
~~~

Service client và HTTP client đều là bean. Khi shutdown, Spring đóng các bean phụ thuộc trước dependency mà chúng sử dụng; xác minh thứ tự bean nếu dùng custom lifecycle. AWS service client được đóng trước, sau đó HTTP transport được chia sẻ mới đóng. Không đóng transport trong mỗi method nghiệp vụ.

### 5.3. Cấu hình asynchronous client với Netty

Với async client, AWS SDK dùng Netty hoặc AWS CRT. Netty có các giới hạn concurrency và hàng đợi chờ connection:

~~~java
import java.time.Duration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import software.amazon.awssdk.http.nio.netty.NettyNioAsyncHttpClient;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3AsyncClient;

@Configuration(proxyBeanMethods = false)
public class AwsAsyncClientConfiguration {

    @Bean(destroyMethod = "close")
    S3AsyncClient s3AsyncClient() {
        return S3AsyncClient.builder()
            .region(Region.AP_SOUTHEAST_1)
            .httpClientBuilder(NettyNioAsyncHttpClient.builder()
                .maxConcurrency(128)
                .maxPendingConnectionAcquires(256)
                .connectionTimeout(Duration.ofSeconds(3))
                .connectionAcquisitionTimeout(Duration.ofSeconds(2))
                .readTimeout(Duration.ofSeconds(20))
                .writeTimeout(Duration.ofSeconds(20)))
            .overrideConfiguration(config -> config
                .apiCallAttemptTimeout(Duration.ofSeconds(15))
                .apiCallTimeout(Duration.ofSeconds(35)))
            .build();
    }
}
~~~

Với HTTP/1.1, concurrency thường gắn với số connection hoạt động; với HTTP/2, nhiều stream có thể dùng chung một connection. Nếu vượt `maxConcurrency`, request có thể chờ trong pending queue; khi queue đầy hoặc chờ quá lâu, request bị từ chối/timeout. Đặt giới hạn pending hữu hạn để tạo backpressure ở client thay vì tích lũy request không giới hạn.

Nếu dùng nhiều async service client và muốn chia sẻ Netty transport, tạo một `SdkAsyncHttpClient` bean rồi truyền vào từng builder. Khi dùng instance chia sẻ, đóng từng service client trước và đóng transport sau. Nếu dùng `httpClientBuilder(...)`, SDK quản lý lifecycle transport được tạo cùng service client.

### 5.4. Đóng stream để trả connection về pool

Với S3 `getObject` trả `ResponseInputStream`, connection có thể chưa được tái sử dụng cho đến khi response body được đọc hết và stream được đóng. Dùng try-with-resources:

~~~java
import software.amazon.awssdk.core.ResponseInputStream;
import software.amazon.awssdk.services.s3.model.GetObjectRequest;
import software.amazon.awssdk.services.s3.model.GetObjectResponse;

GetObjectRequest request = GetObjectRequest.builder()
    .bucket(bucket)
    .key(key)
    .build();

// outputStream đã được tạo trước đó.
try (ResponseInputStream<GetObjectResponse> input =
        s3Client.getObject(request)) {
    input.transferTo(outputStream);
}
~~~

Nếu caller chỉ đọc vài byte rồi bỏ stream mà không đóng, connection có thể bị giữ lại và pool dần cạn. Cùng nguyên tắc áp dụng cho các API streaming/download của những SDK khác: đọc hoặc hủy stream theo contract và đóng response resource.

## 6. Azure SDK for Java

### 6.1. Client bất biến và HTTP pipeline

Azure SDK for Java dùng builder để tạo service client. Client được thiết kế immutable; sau khi tạo, endpoint, credential và client options không đổi. Dùng một client lâu dài cho một cấu hình là cách triển khai phù hợp.

Azure SDK dùng abstraction `com.azure.core.http.HttpClient`. Netty là transport mặc định; SDK cũng hỗ trợ OkHttp và JDK HttpClient. HTTP pipeline của từng service client chứa transport và các policy như authentication, retry, logging, telemetry và request ID.

Điểm cần phân biệt:

- Có thể chia sẻ cùng một `HttpClient` instance giữa nhiều Azure service client.
- Pipeline/policy và cấu hình riêng của từng service client vẫn có thể khác nhau.
- Interface `HttpClient` của Azure Core không có phương thức `close()`; không gắn `destroyMethod = "close"` cho bean kiểu này.
- Nếu tự tạo Reactor Netty `ConnectionProvider` hoặc event-loop resource, ứng dụng sở hữu resource đó và phải dispose theo lifecycle tương ứng.

### 6.2. Chia sẻ Azure HTTP transport

Ví dụ dùng một Netty transport cho Blob Storage và Queue Storage:

~~~xml
<dependency>
    <groupId>com.azure</groupId>
    <artifactId>azure-storage-blob</artifactId>
</dependency>
<dependency>
    <groupId>com.azure</groupId>
    <artifactId>azure-storage-queue</artifactId>
</dependency>
<dependency>
    <groupId>com.azure</groupId>
    <artifactId>azure-core-http-netty</artifactId>
</dependency>
<dependency>
    <groupId>com.azure</groupId>
    <artifactId>azure-identity</artifactId>
</dependency>
~~~

~~~java
import com.azure.core.credential.TokenCredential;
import com.azure.core.http.HttpClient;
import com.azure.core.http.netty.NettyAsyncHttpClientBuilder;
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.storage.blob.BlobServiceClient;
import com.azure.storage.blob.BlobServiceClientBuilder;
import com.azure.storage.queue.QueueServiceClient;
import com.azure.storage.queue.QueueServiceClientBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class AzureStorageClientConfiguration {

    @Bean
    TokenCredential azureCredential() {
        return new DefaultAzureCredentialBuilder().build();
    }

    @Bean
    HttpClient azureHttpClient() {
        return new NettyAsyncHttpClientBuilder().build();
    }

    @Bean
    BlobServiceClient blobServiceClient(
            TokenCredential credential,
            HttpClient azureHttpClient) {
        return new BlobServiceClientBuilder()
            .endpoint(System.getenv("AZURE_STORAGE_BLOB_ENDPOINT"))
            .credential(credential)
            .httpClient(azureHttpClient)
            .buildClient();
    }

    @Bean
    QueueServiceClient queueServiceClient(
            TokenCredential credential,
            HttpClient azureHttpClient) {
        return new QueueServiceClientBuilder()
            .endpoint(System.getenv("AZURE_STORAGE_QUEUE_ENDPOINT"))
            .credential(credential)
            .httpClient(azureHttpClient)
            .buildClient();
    }
}
~~~

Ví dụ cho thấy hai service client dùng chung credential và transport. Azure SDK service clients trong ví dụ không cần gọi `close()`; nếu thay bằng một transport custom có resource riêng như Reactor Netty `ConnectionProvider`, đăng ký resource đó thành bean riêng và dispose khi ứng dụng shutdown. Dùng Azure SDK BOM để đồng bộ phiên bản `azure-core`, transport và service libraries.

### 6.3. Cấu hình connection provider khi thực sự cần

Nếu workload cần giới hạn số connection, pending acquire hoặc idle time, có thể cung cấp Reactor Netty `ConnectionProvider`:

~~~java
import java.time.Duration;
import com.azure.core.http.HttpClient;
import com.azure.core.http.netty.NettyAsyncHttpClientBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import reactor.netty.resources.ConnectionProvider;

@Configuration(proxyBeanMethods = false)
public class AzureTransportConfiguration {

    @Bean(destroyMethod = "dispose")
    ConnectionProvider azureConnectionProvider() {
        return ConnectionProvider.builder("azure-cloud-services")
            .maxConnections(100)
            .pendingAcquireMaxCount(200)
            .pendingAcquireTimeout(Duration.ofSeconds(2))
            .maxIdleTime(Duration.ofSeconds(45))
            .maxLifeTime(Duration.ofMinutes(10))
            .build();
    }

    @Bean
    HttpClient azureHttpClient(ConnectionProvider azureConnectionProvider) {
        return new NettyAsyncHttpClientBuilder()
            .connectionProvider(azureConnectionProvider)
            .build();
    }
}
~~~

Các giá trị cần được đo theo số instance, số endpoint, tải và timeout của dịch vụ. Nếu pool provider được ứng dụng tạo ra, ứng dụng quản lý việc dispose; không dispose ngay sau khi tạo service client. Nếu dùng default Netty/global resources, tránh tự tạo một event loop hoặc provider mới cho mỗi service.

## 7. Google Cloud Java client libraries

### 7.1. Client dài hạn, credential cache và gRPC channel

Google Cloud Java client libraries khuyến nghị tái sử dụng client object thay vì tạo client cho từng request. Một session client có thể chia sẻ credential instance và access token cache; request đầu tiên có thể tốn thêm thời gian để xác thực và tạo token, các request sau tái sử dụng token còn hiệu lực. Tạo quá nhiều client trong thời gian ngắn có thể làm tăng số lần xác thực và gặp giới hạn tốc độ ở một số authentication strategy.

Các client Google Cloud có thể dùng REST/HTTP JSON hoặc gRPC tùy dịch vụ và thư viện. Với gRPC, client thường quản lý channel, executor và background resource. Đóng client khi ApplicationContext shutdown; với gRPC client, gọi `awaitTermination` sau khi `close()` nếu cần chờ các RPC đang chạy hoàn tất.

### 7.2. Spring bean cho Cloud Storage

Ví dụ tạo một Google Cloud Storage client:

~~~xml
<dependency>
    <groupId>com.google.cloud</groupId>
    <artifactId>google-cloud-storage</artifactId>
</dependency>
~~~

~~~java
import com.google.cloud.storage.Storage;
import com.google.cloud.storage.StorageOptions;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class GoogleCloudClientConfiguration {

    @Bean(destroyMethod = "close")
    Storage storageClient() {
        return StorageOptions.newBuilder()
            .setProjectId(System.getenv("GOOGLE_CLOUD_PROJECT"))
            .build()
            .getService();
    }
}
~~~

Service inject `Storage` qua constructor và gọi nhiều lần trên cùng client. Client lấy Application Default Credentials theo môi trường; production nên dùng workload identity/service account phù hợp, không nhúng key file vào image.

### 7.3. gRPC client và graceful shutdown

Ví dụ một Google KMS client:

~~~java
import com.google.cloud.kms.v1.KeyManagementServiceClient;
import java.io.IOException;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class GoogleKmsConfiguration {

    @Bean(destroyMethod = "close")
    KeyManagementServiceClient kmsClient() throws IOException {
        return KeyManagementServiceClient.create();
    }
}
~~~

Với gRPC client trong môi trường production, cần cho request đang chạy có thời gian hoàn tất trước khi process thoát. Google Cloud client lifecycle docs khuyến nghị gọi `close()`, sau đó `awaitTermination(timeout, unit)`; chỉ dùng `shutdownNow()` khi cần kết thúc khẩn cấp các tác vụ còn treo. Nếu Spring shutdown timeout quá ngắn, client có thể bị đóng khi request còn in-flight.

### 7.4. Khi nào cần channel pool?

Không phải client Google Cloud nào cũng cần nhiều gRPC channel. GAX có `ChannelPoolSettings` để phân phối RPC qua nhiều channel cho một số high-throughput workload; API này hiện được đánh dấu Beta và việc oversize pool có thể làm channel nhàn rỗi, tăng tail latency. Chỉ bật channel pool khi tài liệu service/client hỗ trợ, metrics cho thấy một channel là bottleneck và benchmark xác nhận lợi ích.

## 8. Spring Boot RestClient và WebClient

SDK cloud không phải đường HTTP duy nhất. Ứng dụng thường gọi thêm API nội bộ hoặc REST API của đối tác. Spring Boot cung cấp `RestClient` cho imperative application và `WebClient` cho reactive application.

### 8.1. WebClient

Spring Boot auto-configure `WebClient.Builder` và chia sẻ HTTP resources với server khi dùng Reactor Netty hoặc Jetty tương ứng. Inject builder và tạo WebClient một lần trong service:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

@Service
public class PartnerApiClient {
    private final WebClient webClient;

    public PartnerApiClient(WebClient.Builder builder) {
        this.webClient = builder
            .baseUrl("https://partner.example")
            .build();
    }

    public Mono<PartnerResponse> getStatus(String id) {
        return webClient.get()
            .uri("/v1/status/{id}", id)
            .retrieve()
            .bodyToMono(PartnerResponse.class);
    }
}
~~~

Không gọi `WebClient.create()` trong mỗi request nếu cần tái sử dụng resource/pool và auto-configuration. `WebClient.Builder` có trạng thái; nếu tạo nhiều client với cấu hình khác nhau, dùng `builder.clone()` trước khi thay đổi base URL/filter để tránh cấu hình vô tình ảnh hưởng client tạo sau.

### 8.2. RestClient

Với ứng dụng imperative, inject `RestClient.Builder` và build một client trong constructor hoặc bean configuration. Spring Boot auto-detect HTTP client dựa trên classpath; có thể dùng Apache HttpClient, Jetty, Reactor Netty hoặc JDK HttpClient. Đừng tạo request factory và pool mới cho mỗi method call.

### 8.3. Không chia sẻ nhầm transport giữa reactive và blocking

Một HTTP client đồng bộ và một HTTP client bất đồng bộ có thể có API, event-loop và lifecycle khác nhau. Không ép một transport blocking vào WebFlux event loop. Chọn connector phù hợp với programming model; chỉ chia sẻ resource khi Spring/transport chính thức hỗ trợ và cùng lifecycle.

## 9. Connection pool và concurrency

### 9.1. Pool size không phải số request tối đa của toàn ứng dụng

Pool thường thuộc một HTTP client instance. Nếu mỗi service client tự tạo transport, mỗi pool có giới hạn riêng. Nếu nhiều service client chia sẻ transport, giới hạn đó có thể là giới hạn chung cho tất cả service client đang dùng transport.

Với HTTP/1.1, một connection thường phục vụ một request đang hoạt động tại một thời điểm. Với HTTP/2, nhiều stream có thể multiplex trên cùng connection. Vì vậy:

- `maxConnections` thường nói về số TCP connection trong pool.
- `maxConcurrency` có thể là số request/stream đang được phép thực hiện.
- Số connection vật lý không nhất thiết bằng số request đồng thời.
- GAX gRPC channel pool có semantics riêng; không lấy số connection HTTP/1.1 để suy ra số channel.

Phạm vi giới hạn còn phụ thuộc implementation:

| Implementation | Tham số thường gặp | Phạm vi cần hiểu |
| --- | --- | --- |
| AWS Apache5 | `maxConnections` | Giới hạn connection của HTTP client/pool được tạo |
| AWS Netty async | `maxConcurrency` | Giới hạn request đồng thời; với HTTP/2 không đồng nghĩa số TCP connection và được áp dụng theo endpoint |
| Azure Reactor Netty | `ConnectionProvider.maxConnections` | Giới hạn pool theo remote address; nhiều host có thể tạo nhiều pool |
| Google GAX/gRPC | Channel pool settings | Số channel và số RPC/stream mỗi channel là hai khái niệm riêng |

Khi một transport phục vụ nhiều endpoint, hãy đọc semantics của đúng implementation. Không nhân hoặc cộng các giới hạn mà chưa xác định chúng là global, per-host hay per-endpoint.

### 9.2. Dùng Little's Law để ước lượng ban đầu

Một ước lượng đơn giản cho số request đang in-flight:

**L = λ × W**

Trong đó:

- **L:** số request trung bình đang chờ/đang xử lý.
- **λ:** throughput trung bình (request/giây).
- **W:** thời gian giữ tài nguyên trung bình (giây).

Ví dụ một instance gửi 120 request/giây, mỗi request giữ connection trung bình 0,25 giây:

**L = 120 × 0,25 = 30**

Khoảng 30 request có thể đang in-flight trung bình. Đây chưa phải giá trị `maxConnections`: cần xét burst, p95/p99, HTTP/2, thời gian response body, retry và số endpoint. Đặt pool đủ để xử lý peak hợp lý nhưng có giới hạn để bảo vệ downstream.

### 9.3. Tính tổng trên toàn deployment

Giả sử ứng dụng chạy 6 pod và mỗi pod có một pool tối đa 80 connection tới một dịch vụ:

[
**6 × 80 = 480 connections**
]

Nếu ứng dụng có thêm ba HTTP client khác nhau, mỗi client có pool riêng, tổng connection tiềm năng sẽ cao hơn. Tính cả:

- Số replica/pod/VM và số process trên mỗi host.
- Số service client/transport instance trong mỗi process.
- Số endpoint/region mà pool quản lý.
- Retry, streaming và connection giữ lâu.
- Giới hạn database, API gateway, NAT/SNAT và quota của dịch vụ.

Không chỉ nhìn `maxConnections` trong một pod rồi kết luận hệ thống vẫn an toàn.

## 10. Chọn timeout theo từng giai đoạn

Các timeout có ý nghĩa khác nhau:

| Timeout | Giới hạn | Khi hết hạn |
| --- | --- | --- |
| DNS resolution | Phân giải hostname | Không tìm được endpoint trong deadline |
| Connection timeout | Thiết lập TCP connection | Kết nối không mở được |
| TLS handshake timeout | Thương lượng TLS | Handshake không hoàn tất |
| Pool acquisition timeout | Chờ connection/slot rảnh | Pool đang bận hoặc queue quá tải |
| Read/write timeout | Gửi request hoặc nhận response | Network I/O quá chậm |
| Attempt timeout | Một lần gọi SDK | Có thể chuyển sang retry nếu policy cho phép |
| API/call timeout | Toàn bộ operation gồm retry | Kết thúc operation theo deadline |
| Caller/request deadline | Thời gian request đầu-cuối | Hủy hoặc trả timeout cho caller |

Đặt timeout theo thứ tự hợp lý: thời gian chờ pool và connect phải nằm trong deadline tổng; attempt timeout không vượt quá API timeout; API timeout không nên vượt xa deadline của HTTP request phía trên. Nếu retry ở nhiều tầng, tổng thời gian có thể nhân lên ngoài dự kiến.

Không tăng timeout khi nguyên nhân thật là pool exhaustion. Nếu pool acquisition timeout tăng, xem active connection, pending queue và thời gian response body trước khi nới giới hạn.

## 11. DNS, keepalive và tuổi thọ connection

Connection reuse giúp giảm handshake nhưng connection không nên giữ mãi bất kể môi trường:

- DNS record có thể thay đổi khi service failover, scale hoặc chuyển endpoint.
- Load balancer/NAT/firewall có thể đóng connection idle.
- Certificate hoặc TLS policy có thể được xoay vòng.
- Connection lâu năm có thể giữ route cũ hoặc không còn healthy.

Các HTTP client thường có cấu hình connection TTL, max idle time và keepalive. Chọn giá trị theo DNS TTL, idle timeout của mạng, hành vi service và thời gian xử lý request. Không đặt TTL quá ngắn khiến ứng dụng liên tục tạo TLS handshake; cũng không đặt vô hạn khi endpoint có failover/DNS rotation.

HTTP/2 và gRPC có keepalive ping và channel health riêng. Chỉ bật theo hướng dẫn dịch vụ; ping quá thường xuyên có thể bị server/proxy giới hạn hoặc tạo chi phí không cần thiết.

## 12. Streaming và giải phóng response

Pool chỉ tái sử dụng được connection khi response body đã được tiêu thụ hoặc đóng đúng cách. Những thao tác dễ giữ connection lâu:

- Download file từ S3/Blob/GCS.
- Đọc stream lớn hoặc xử lý response chậm.
- Giữ response object trong cache hoặc truyền qua nhiều layer trước khi đóng.
- Không cancel subscription khi caller không còn cần dữ liệu.

Ví dụ với AWS:

~~~java
try (ResponseInputStream<GetObjectResponse> stream =
        s3Client.getObject(request)) {
    stream.transferTo(destination);
}
~~~

Với Azure, dùng API download/stream và đóng response/stream theo contract của method. Với Google Cloud Storage, đóng `ReadChannel` hoặc stream được trả về sau khi đọc xong. Nếu API trả publisher, xử lý cancellation và tiêu thụ body; không bỏ qua response body rồi kỳ vọng pool tự thu hồi ngay.

## 13. Retry và idempotency ảnh hưởng đến pool

Retry làm tăng lượng request đi qua transport. Khi service chậm, retry đồng loạt có thể làm pool và downstream quá tải hơn:

1. Nhiều request ban đầu chiếm connection lâu.
2. Caller timeout và bắt đầu retry.
3. Retry mới xếp hàng trong pending queue.
4. Queue đầy, latency tăng và thêm timeout.

Đây là retry storm. Dùng retry có exponential backoff và jitter, giới hạn số lần thử/tổng deadline, circuit breaker hoặc concurrency limit nếu phù hợp. Không retry lỗi authentication/authorization hoặc validation như lỗi mạng transient.

Đối với thao tác ghi, phải xác định idempotency semantics. Timeout sau khi gửi request không chứng minh server chưa xử lý; retry một lệnh tăng counter, tạo resource hoặc charge payment có thể tạo side effect trùng. Dùng idempotency key, conditional write hoặc đối chiếu trạng thái trước khi retry.

## 14. Credential và client configuration

Client thường giữ credential provider hoặc tham chiếu tới credential provider. Tạo client liên tục có thể lặp việc:

- Đọc profile/credential file.
- Gọi metadata service của VM/container.
- Khởi tạo token cache.
- Trao đổi token với identity provider.
- Tạo gRPC channel hoặc HTTP authentication pipeline.

Tái sử dụng credential provider khi SDK cho phép. Azure Identity Java xác nhận credential implementations là thread-safe và một credential instance có thể tạo nhiều service client. Google client libraries khuyến nghị reuse session client để chia sẻ credential cache và refresh token. AWS SDK credential provider chain cũng nên được cấu hình ở client lifecycle, không tạo provider mới trong mỗi request.

Không chia sẻ client qua tenant/identity nếu làm sai ranh giới bảo mật. Nếu credential, endpoint, region hoặc policy khác nhau, tạo client riêng theo cấu hình đó và giới hạn số lượng.

## 15. Quan sát pool và transport

Chỉ số nên theo dõi ở cả application và client:

| Nhóm | Metric | Ý nghĩa |
| --- | --- | --- |
| Connection pool | Active/in-use connections | Số connection đang phục vụ request |
| Connection pool | Idle/available connections | Khả năng nhận request mới |
| Connection pool | Pending acquire / waiters | Số request đang đợi pool |
| Connection pool | Acquire latency/timeouts | Thời gian chờ mượn connection |
| Transport | Connect/TLS handshake duration | Chi phí mở kết nối mới |
| Transport | Connection creation/close rate | Pool có churn quá nhiều không |
| Request | p50/p95/p99 latency | Độ trễ đầu-cuối |
| Request | In-flight, success/error, retry | Mức tải và độ ổn định |
| Resource | File descriptor/socket, thread, event-loop | Nguy cơ cạn tài nguyên |
| Cloud | 429/throttling, quota, service latency | Downstream có đang quá tải không |

Với AWS SDK, xem metrics như available concurrency, pending concurrency acquires và concurrency acquire duration. Với Azure, kết hợp SDK diagnostics, Reactor Netty metrics và Azure Monitor. Với Google gRPC, theo dõi channel state, RPC latency, outstanding calls và executor saturation.

Không log access token, secret, signed URL hoặc dữ liệu nhạy cảm trong HTTP wire log. Chỉ bật wire-level logging có kiểm soát ở môi trường điều tra.

## 16. Lifecycle và graceful shutdown

Khi Spring ApplicationContext shutdown:

1. Ngừng nhận traffic mới và đánh dấu instance không ready.
2. Chờ request/message đang xử lý hoàn tất trong shutdown deadline.
3. Đóng service client hoặc client wrapper theo contract SDK.
4. Đóng HTTP transport dùng chung sau tất cả service client phụ thuộc.
5. Dispose custom connection provider/event-loop nếu ứng dụng sở hữu.
6. Với gRPC client, gọi `close()` và chờ `awaitTermination` trong giới hạn thời gian.

Không đóng transport khi request còn đang dùng. Không chỉ dựa vào garbage collection để giải phóng socket/thread. Với shared transport, ghi rõ bean nào sở hữu resource và bean nào chỉ mượn resource.

| SDK/resource | Vòng đời thường dùng |
| --- | --- |
| AWS service client | Bean singleton; gọi `close()` khi shutdown |
| AWS HTTP client được share | Bean riêng; đóng sau service clients |
| Azure service client | Client immutable, reuse; theo đúng lifecycle của service/client library |
| Azure `HttpClient` abstraction | Có thể share; interface không có `close()` |
| Azure custom Reactor `ConnectionProvider` | Ứng dụng sở hữu thì `dispose()` khi shutdown |
| Google Cloud client | Bean dài hạn; gọi `close()`; gRPC có thể cần `awaitTermination` |
| Spring WebClient/RestClient | Tạo một lần và để Spring/transport resources quản lý theo ApplicationContext |

## 17. Lỗi thường gặp

| Lỗi | Hệ quả | Cách sửa |
| --- | --- | --- |
| Tạo SDK client trong mỗi request | Lặp init, credential, pool và socket | Singleton bean theo cấu hình |
| Tạo nhiều client cùng endpoint/credential | Nhiều pool ít được dùng, tăng file descriptor | Chia sẻ service client/transport khi tương thích |
| Dùng chung client giữa hai region hoặc identity khác nhau | Gọi sai endpoint hoặc sai security boundary | Client riêng cho mỗi cấu hình ổn định |
| Share AWS HTTP client nhưng không đóng | Rò rỉ pool, thread và socket | Đóng service clients rồi đóng shared transport |
| Nghĩ Azure HttpClient có `close()` | Lifecycle bean sai | Quản lý custom ConnectionProvider; không gọi close trên interface không hỗ trợ |
| Tạo custom Netty provider nhưng không dispose | Event-loop/connection resource còn tồn tại | Dispose resource do ứng dụng sở hữu |
| Pool quá nhỏ | Pending queue và acquire timeout tăng | Đo concurrency, latency và tăng có kiểm soát |
| Pool quá lớn trên mọi pod | Quá nhiều connection tới database/API/NAT | Tính tổng theo replica và giới hạn downstream |
| Không đặt pending queue limit | Request tích lũy, memory tăng | Đặt queue hữu hạn và timeout acquire |
| Không đóng stream download | Connection không quay lại pool | Đóng stream/response bằng try-with-resources |
| Retry mọi lỗi | Retry storm và side effect trùng | Retry transient, idempotency và deadline |
| Tắt keepalive/TTL mà không hiểu mạng | Connection stale hoặc handshake lặp | Tune theo DNS/load balancer/idle timeout |
| Đóng client trước khi request hoàn tất | Request đang chạy bị fail | Drain traffic và graceful shutdown |

## 18. Kiểm thử và benchmark

### 18.1. Kiểm thử vòng đời

Viết integration test hoặc smoke test để xác minh:

- Spring tạo đúng một client bean cho mỗi cấu hình.
- Nhiều service request dùng cùng client/transport.
- Application shutdown gọi close/dispose đúng thứ tự.
- Shared transport không bị đóng khi một service client riêng lẻ kết thúc.
- Streaming response được đóng khi success và khi exception.
- Credential refresh không làm khởi tạo lại toàn bộ client.

### 18.2. Benchmark so sánh

So sánh hai phiên bản:

- **A:** tạo client/transport trong từng request.
- **B:** tái sử dụng singleton client và pool.

Dùng cùng endpoint, region, payload, concurrency và credential. Đo:

| Chỉ số | Mục đích |
| --- | --- |
| p50/p95/p99 latency | Thấy tác động của connection reuse và queue |
| Throughput | Số operation hoàn tất mỗi giây |
| TCP/TLS connection creation | Đo số handshake được tránh |
| Active/idle/pending pool | Xác định pool size và queue |
| CPU/memory/thread count | Đo chi phí client/transport |
| Socket/file descriptor | Phát hiện client churn hoặc leak |
| Retry/error/timeout | Phát hiện overload hoặc timeout sai |
| Cloud API request count/data transfer | Phân biệt chi phí transport với chi phí dịch vụ |

Warm-up trước khi lấy số liệu vì request đầu tiên có thể khởi tạo DNS, TLS, credential cache hoặc gRPC channel. Chạy đủ lâu để thấy pool ổn định và có giai đoạn peak. Không kết luận chỉ từ một request hoặc một lần chạy ngắn.

### 18.3. Không nhầm tiết kiệm transport với giảm hóa đơn API

Tái sử dụng client giảm chi phí compute, TLS handshake, socket, thread và latency ở phía ứng dụng. Nó **không tự giảm số API request tính phí** nếu số operation nghiệp vụ không đổi. Hóa đơn cloud còn phụ thuộc request count, data transfer, storage, database throughput, egress và SKU dịch vụ. Muốn giảm bill phải tối ưu thêm batching, caching, payload, query, transfer và service tier theo số đo.

## 19. Quy trình triển khai

~~~mermaid
flowchart TD
    A[Liệt kê service endpoint và identity] --> B[Chọn SDK client và transport]
    B --> C[Xác định client/pool ownership]
    C --> D[Đăng ký Spring singleton beans]
    D --> E[Đặt pool limits và timeout]
    E --> F[Đóng stream và định nghĩa shutdown]
    F --> G[Load test và quan sát metrics]
    G --> H{Pool có nghẽn hoặc quá dư?}
    H -->|Nghẽn| I[Điều chỉnh concurrency, queue, timeout]
    H -->|Quá dư| J[Giảm pool hoặc gộp transport]
    I --> G
    J --> G
    H -->|Cân bằng| K[Chốt cấu hình và alert]
~~~

Trước khi phát hành, trả lời:

1. Client được tạo ở đâu và có bao nhiêu instance trên mỗi pod?
2. Client có thread-safe theo tài liệu SDK không?
3. Pool nằm trong service client hay HTTP transport?
4. Transport được chia sẻ giữa những service client nào?
5. Ai sở hữu và đóng transport/connection provider?
6. Tổng connection tiềm năng trên tất cả pod là bao nhiêu?
7. Pending queue có giới hạn và timeout không?
8. Streaming response có được đóng trong mọi nhánh không?
9. Có metric để phân biệt pool exhaustion với downstream throttling không?
10. Retry và shutdown có giữ an toàn cho request in-flight không?

## 20. Bài tập thực hành

**Bài tập 1 — AWS singleton.** Tạo S3Client bean dùng Apache5HttpClient. Gọi `headBucket` và `listObjectsV2` từ nhiều request; so sánh số lần khởi tạo client, số connection và p95 trước/sau khi reuse.

**Bài tập 2 — AWS shared transport.** Dùng cùng `SdkHttpClient` cho S3Client và DynamoDbClient. Xác minh cả hai dùng chung pool, service client đóng trước transport và không còn thread/socket sau shutdown.

**Bài tập 3 — AWS async.** Cấu hình `S3AsyncClient` với `maxConcurrency`, pending acquire và timeout. Tăng tải dần để quan sát thời điểm queue tăng và request bắt đầu timeout.

**Bài tập 4 — Azure transport.** Tạo một Netty `HttpClient` và dùng cho BlobServiceClient cùng QueueServiceClient. Sau đó thay bằng custom ConnectionProvider, giới hạn maxConnections/pendingAcquire và kiểm tra dispose khi ApplicationContext dừng.

**Bài tập 5 — Google client lifecycle.** Đăng ký Storage hoặc KMS client thành singleton bean. Gửi nhiều request, kiểm tra credential cache, sau đó shutdown và xác minh client/gRPC channel đã được đóng.

**Bài tập 6 — Spring WebClient.** Tạo một WebClient trong constructor qua Spring Boot WebClient.Builder. So sánh với cách gọi `WebClient.create()` mỗi request; đo connection reuse và số TLS handshake.

**Bài tập 7 — Tính pool.** Một pod có 150 RPS tới dịch vụ A, thời gian giữ connection trung bình 120 ms; tính số request in-flight trung bình. Nếu có 8 pod, pool max 40 mỗi pod, tính số connection tối đa và đánh giá so với quota downstream.

**Bài tập 8 — Streaming leak.** Viết endpoint tải file S3 nhưng cố ý không đóng ResponseInputStream. Quan sát pool pending/acquire timeout; sửa bằng try-with-resources và xác minh connection được tái sử dụng.

**Bài tập 9 — Retry storm.** Giả lập dịch vụ downstream chậm. Quan sát pending queue, retry và p99. Thêm exponential backoff, jitter, deadline và concurrency limit; so sánh mức phục hồi.

## 21. Ghi nhớ

- **Tạo client lâu dài và tái sử dụng** là cách mặc định cho SDK client có thể chia sẻ; tạo client theo từng request gây lặp credential, pipeline, pool, socket và TLS handshake.
- AWS SDK for Java 2.x service clients thread-safe; mỗi client mặc định có pool riêng. Có thể chia sẻ HTTP client tương thích nhưng phải đóng transport sau service clients.
- Azure SDK Java dùng HTTP pipeline pluggable, mặc định Netty; cùng `HttpClient` instance có thể được truyền cho nhiều service client. Custom Reactor resources do ứng dụng tạo phải được dispose.
- Google Cloud Java clients được thiết kế long-lived; reuse giúp chia sẻ credential cache. Đóng client và chờ gRPC channel hoàn tất khi shutdown.
- Spring singleton bean là nơi thích hợp quản lý SDK clients. Tách client theo endpoint/region/credential/configuration khác nhau.
- Pool size cần dựa trên concurrency, thời gian giữ connection, số pod, endpoint và quota. Tính tổng connection toàn deployment, không chỉ từng process.
- Connection acquisition timeout, connect/TLS timeout, read/write timeout và API deadline là các giới hạn khác nhau.
- Đóng stream/response để connection quay lại pool; giới hạn pending queue để tránh tích lũy request.
- Retry phải có backoff, jitter, deadline và idempotency. Timeout không chứng minh thao tác chưa được thực hiện.
- Reuse client giảm chi phí tài nguyên và latency phía ứng dụng; không tự giảm số API request tính phí của cloud service.

## 22. Tài liệu tham khảo

- [AWS SDK for Java 2.x — Best practices](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/best-practices.html)
- [AWS SDK for Java 2.x — Singleton service clients](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/singleton-service-clients.html)
- [AWS SDK for Java 2.x — Configure the Apache 5 HTTP client](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/http-configuration-apache5.html)
- [AWS SDK for Java 2.x — Configure the Netty async HTTP client](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/http-configuration-netty.html)
- [AWS SDK for Java 2.x — Client configuration and shared HTTP clients](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/client-configuration.html)
- [AWS SDK for Java 2.x — Timeouts](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/timeouts.html)
- [Azure SDK for Java — Use the Azure SDK for Java](https://learn.microsoft.com/en-us/azure/developer/java/sdk/overview)
- [Azure SDK for Java — HTTP clients and pipelines](https://learn.microsoft.com/en-us/azure/developer/java/sdk/http-client-pipeline)
- [Azure SDK for Java — Netty HTTP client and ConnectionProvider](https://learn.microsoft.com/en-us/java/api/com.azure.core.http.netty.nettyasynchttpclientbuilder?view=azure-java-stable)
- [Azure SDK for Java — Azure Identity](https://learn.microsoft.com/en-us/java/api/overview/azure/identity-readme?view=azure-java-stable)
- [Google Cloud Java — Manage client lifecycles](https://docs.cloud.google.com/java/docs/client-lifecycle)
- [Google Cloud — Client libraries best practices](https://docs.cloud.google.com/apis/docs/client-libraries-best-practices)
- [Google Cloud GAX — ChannelPoolSettings](https://docs.cloud.google.com/java/docs/reference/gax/latest/com.google.api.gax.grpc.ChannelPoolSettings)
- [Spring Boot — Calling REST services](https://docs.spring.io/spring-boot/reference/io/rest-client.html)
