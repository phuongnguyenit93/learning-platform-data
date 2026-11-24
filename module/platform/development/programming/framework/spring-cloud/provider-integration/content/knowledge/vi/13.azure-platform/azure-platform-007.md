# Tùy chỉnh Azure client builder, HTTP pipeline và proxy

Khi một ứng dụng Spring Boot dùng Azure Blob Storage, Key Vault hoặc Service Bus, cấu hình mặc định của Spring Cloud Azure thường đủ cho những kết nối cơ bản. Tuy nhiên, trong hệ thống doanh nghiệp có **HTTP proxy**, **Private Endpoint**, yêu cầu **timeout**, **retry**, **HTTP logging** hoặc **observability**, lập trình viên cần hiểu sâu hơn cách Azure SDK for Java xây dựng client và gửi request.

Một lỗi quen thuộc là upload Blob thành công trên laptop nhưng khi chạy trong môi trường CI hoặc mạng doanh nghiệp lại gặp **407 Proxy Authentication Required**, lỗi TLS, timeout hoặc không lấy được access token. Để xử lý đúng, cần phân biệt cấu hình **Azure service client**, **HTTP transport**, **HTTP pipeline** và **credential**; mỗi lớp có thể dùng cơ chế kết nối riêng.

Bài thuộc chương **Nền tảng Azure** của module **SPRING_CLOUD_PROVIDER_INTEGRATION**: thực hành tích hợp Spring Boot với các dịch vụ managed trên AWS, Azure và Google Cloud qua các thư viện Spring Cloud tương ứng; chú trọng danh tính/quyền, storage, messaging, dữ liệu, secret, kiểm thử tích hợp và so sánh khác biệt giữa cloud provider.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Phân biệt **service client builder**, **transport HttpClient**, **HttpPipeline**, **HttpPipelinePolicy** và **TokenCredential** trong Azure SDK for Java.
2. Tạo và tái sử dụng **BlobServiceClient** bằng **BlobServiceClientBuilder** với endpoint, identity, HTTP client và logging được cấu hình.
3. Cấu hình HTTP proxy cho một transport cụ thể, hiểu vai trò của HTTPS CONNECT, TLS, authentication và proxy bypass.
4. Giải thích giới hạn của proxy HTTP đối với dịch vụ dùng **AMQP**, WebSockets và một số kết nối database.
5. Lựa chọn giữa **Spring Cloud Azure auto-configuration** và tự định nghĩa bean client khi cần tùy chỉnh.
6. Xây dựng chính sách retry/timeout, logging/tracing an toàn và kiểm thử kết nối trong local, CI và Azure runtime.
7. Chẩn đoán proxy, DNS, TLS, credential, Azure RBAC và lỗi SDK mà không làm lộ secret.

## 2. Bức tranh các lớp kết nối trong Azure SDK

~~~mermaid
flowchart TD
    A[Spring Boot service] --> B[Azure service client\nBlobServiceClient / SecretClient]
    B --> C[Azure SDK HTTP pipeline]
    C --> D[Authentication policy\nTokenCredential]
    C --> E[Retry / logging / custom policies]
    C --> F[HTTP transport: Netty / OkHttp / ...]
    F --> G{Mạng có proxy?}
    G -->|Có| H[HTTP proxy / HTTPS CONNECT]
    G -->|Không| I[DNS / private routing]
    H --> J[Azure data endpoint]
    I --> J
    D --> K[Microsoft Entra token endpoint]
~~~

Sơ đồ là mô hình **khái niệm**: thứ tự thực thi pipeline, vị trí xử lý retry và cách Azure Identity SDK thực hiện HTTP request tùy phiên bản/thư viện. Những request lấy token tới Microsoft Entra có thể sử dụng **HTTP transport của credential** khác với transport gọi Blob nếu không cấu hình thống nhất.

| Lớp | Trách nhiệm | Ví dụ |
| --- | --- | --- |
| **Service client** | Cung cấp API nghiệp vụ của dịch vụ Azure | **BlobServiceClient**, **BlobClient**, **SecretClient** |
| **Client builder** | Nhận endpoint, credential, transport và tùy chọn để tạo client | **BlobServiceClientBuilder** |
| **HTTP pipeline** | Áp dụng các policy quanh request/response HTTP | Authentication, retry, telemetry, log |
| **HttpPipelinePolicy** | Thành phần xử lý request/response trong pipeline | Header policy, tracing/correlation |
| **HttpClient** (Azure Core) | Thực hiện HTTP request qua transport thực tế | Netty, OkHttp tùy dependency |
| **Proxy** | Trung gian chuyển tiếp kết nối theo chính sách mạng | Corporate HTTP CONNECT proxy |
| **TokenCredential** | Cấp access token thích hợp cho dịch vụ | DefaultAzureCredential, ManagedIdentityCredential |
| **Azure RBAC** | Quyết định principal có được thao tác trên resource không | Storage Blob Data Contributor |

**Client builder không phải một kết nối mạng đã mở.** Nhiều Azure SDK tạo đối tượng client mà chưa lấy token hoặc liên lạc với Azure; cấu hình chỉ thực sự được thử ở request đầu tiên.

## 3. Service client builder: tùy chỉnh ở đâu?

Azure SDK for Java cung cấp các builder theo dịch vụ. Mỗi builder nhận những tham số phù hợp với API dịch vụ đó.

| Dịch vụ | Builder tiêu biểu | Tùy chỉnh quan trọng |
| --- | --- | --- |
| Azure Blob Storage | **BlobServiceClientBuilder** | Endpoint/account, TokenCredential, HTTP transport, retry, logging |
| Azure Key Vault Secrets | **SecretClientBuilder** | Vault URL, credential, HTTP transport, policy/logging |
| Azure App Configuration | **ConfigurationClientBuilder** | Store endpoint, credential, transport và retry |
| Azure Service Bus | **ServiceBusClientBuilder** | Namespace, credential, AMQP transport, processor/producer options |
| Azure Event Hubs | **EventHubClientBuilder** hoặc builder chuyên biệt | Namespace/event hub, credential, AMQP transport và processing |
| Azure Cosmos DB | **CosmosClientBuilder** | Endpoint, credential, consistency, direct/gateway và connection settings |

Không giả định tất cả builder đều có cùng phương thức, dù cùng thuộc Azure SDK. Ví dụ một builder dùng **endpoint(URL)**, builder khác dùng **fullyQualifiedNamespace(hostname)**. Một số SDK dùng transport TCP/AMQP, nên cấu hình **HttpClient** của Azure Core không phải nút điều khiển toàn bộ kết nối.

### Tạo BlobServiceClient trực tiếp

~~~java
import com.azure.core.credential.TokenCredential;
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.storage.blob.BlobServiceClient;
import com.azure.storage.blob.BlobServiceClientBuilder;

public final class AzureBlobClients {

    private AzureBlobClients() {}

    public static BlobServiceClient create(String endpoint) {
        TokenCredential credential =
                new DefaultAzureCredentialBuilder().build();

        return new BlobServiceClientBuilder()
                .endpoint(endpoint)
                .credential(credential)
                .buildClient();
    }
}
~~~

Ví dụ endpoint trên Azure public cloud: **https://stordersdev01.blob.core.windows.net**. Không đưa Azure Resource Manager ID dạng **/subscriptions/...** vào vị trí endpoint của Blob client.

Client SDK thường được thiết kế để **tái sử dụng**. Với Spring Boot, nên giữ client ở dạng **singleton bean** thay vì tạo một builder/client cho mỗi request HTTP. Việc tạo client liên tục có thể tăng chi phí tài nguyên, làm phân tán cấu hình và gây khó khăn khi kiểm tra connection pool.

### Đồng bộ và bất đồng bộ

Blob Storage cung cấp client đồng bộ và bất đồng bộ trong phạm vi API tương ứng. Từ cùng builder có thể xây client thông qua các phương thức phù hợp, chẳng hạn **buildClient()** hoặc **buildAsyncClient()** khi API hỗ trợ. Chọn dựa trên kiến trúc:

- Spring MVC xử lý đơn giản thường dùng client đồng bộ.
- Spring WebFlux hoặc xử lý thông lượng cao có thể dùng client async và quản lý backpressure.
- Không gọi API đồng bộ chặn thread trên event loop WebFlux.
- Không tạo mới HTTP transport/connection pool trong từng item của luồng dữ liệu.

## 4. Các loại cấu hình HTTP thường gặp

| Nhu cầu | Vị trí cấu hình thích hợp | Cẩn trọng |
| --- | --- | --- |
| Đích Azure | Builder **endpoint** hoặc **fullyQualifiedNamespace** | Đúng DNS/cloud environment và resource |
| Principal/token | **TokenCredential** hoặc cơ chế credential theo builder | Đúng tenant, identity và RBAC |
| Proxy HTTP | HTTP transport hoặc cấu hình transport được SDK hỗ trợ | Không suy luận mọi giao thức cùng dùng proxy |
| Timeout kết nối | HTTP transport hoặc connection options | Phân biệt connect, read, response, toàn operation |
| Retry | Retry options của SDK dịch vụ hoặc HTTP pipeline | Không retry không giới hạn và không làm mất idempotency |
| Header/telemetry | Pipeline policy hoặc SDK diagnostics được hỗ trợ | Không ghi token, SAS và dữ liệu nhạy cảm |
| Certificate/trust | Trust store và chính sách TLS của runtime/transport | Không tắt certificate validation |
| Socket/concurrency | HTTP client pool, SDK connection settings | Theo tải và giới hạn dịch vụ |
| Private Endpoint | DNS, route, VNet, firewall ở hạ tầng | Không thay hostname dịch vụ bằng IP tùy ý |

**Không có một cấu hình duy nhất áp dụng cho toàn bộ Azure SDK.** Mỗi dịch vụ dùng stack transport phù hợp; nhiều ứng dụng còn có nhiều HTTP clients khác nhau: Spring WebClient, Azure Blob client và Azure Identity credential client.

## 5. HTTP pipeline hoạt động như thế nào?

Azure Core HTTP pipeline kết hợp các **HttpPipelinePolicy** trước/sau khi request đi qua **HttpClient**. Các nhóm thường có vai trò:

1. Bổ sung header chung và metadata request.
2. Xác thực request bằng token hoặc cơ chế credential thích hợp.
3. Ghi log/tracing/metrics theo thiết lập.
4. Thực hiện retry/backoff với lỗi phù hợp khi SDK hỗ trợ.
5. Gửi request qua HTTP transport và nhận response.

Thứ tự, số lần gọi policy và policy nào chạy lại trong retry phụ thuộc **SDK và cấu hình pipeline thực tế**. Không dựa vào thứ tự trong ví dụ mô tả để xây logic nhạy cảm như ký request hoặc giới hạn bảo mật.

### Thêm policy tùy chỉnh ở cấp builder

Ví dụ tạo một policy chỉ bổ sung header mang thông tin kỹ thuật **không nhạy cảm**:

~~~java
import com.azure.core.http.HttpPipelineCallContext;
import com.azure.core.http.HttpPipelineNextPolicy;
import com.azure.core.http.HttpResponse;
import com.azure.core.http.policy.HttpPipelinePolicy;
import reactor.core.publisher.Mono;

public final class ComponentHeaderPolicy implements HttpPipelinePolicy {

    @Override
    public Mono<HttpResponse> process(
            HttpPipelineCallContext context,
            HttpPipelineNextPolicy next) {

        context.getHttpRequest()
                .setHeader("x-app-component", "documents-api");
        return next.process();
    }
}
~~~

Gắn policy vào Blob client builder ở phiên bản có hỗ trợ **addPolicy**:

~~~java
BlobServiceClient client = new BlobServiceClientBuilder()
        .endpoint(blobEndpoint)
        .credential(credential)
        .addPolicy(new ComponentHeaderPolicy())
        .buildClient();
~~~

Policy trên giúp minh họa điểm mở rộng pipeline. Không dùng nó để chèn **Authorization header**, tự tạo SAS, lưu access token, thay đổi nội dung request tùy tiện hoặc cố vượt qua security policy.

**Header tùy chỉnh có thể được gửi ra Azure và qua proxy**, nên chỉ chứa thông tin được phép công bố cho hệ thống đích. Nếu muốn gắn correlation ID theo từng request, cần có thiết kế trace/context propagation thích hợp; không ghi một ID tĩnh rồi tưởng mỗi request được phân biệt.

### Chú ý khi policy được thực thi nhiều lần

Retry có thể khiến một request được xử lý hơn một lần trong những lớp pipeline nhất định. Vì thế policy nên **không có side effect nguy hiểm**; đừng gửi thêm message hoặc ghi database trực tiếp từ policy chỉ vì thấy nó chạy trên một HTTP request.

## 6. Cấu hình HTTP logging và tracing an toàn

Azure SDK cung cấp những tùy chọn HTTP logging theo version, ví dụ **HttpLogOptions** và mức **HttpLogDetailLevel**.

~~~java
import com.azure.core.http.policy.HttpLogDetailLevel;
import com.azure.core.http.policy.HttpLogOptions;
import com.azure.storage.blob.BlobServiceClient;
import com.azure.storage.blob.BlobServiceClientBuilder;

HttpLogOptions logOptions = new HttpLogOptions()
        .setLogLevel(HttpLogDetailLevel.BASIC);

BlobServiceClient client = new BlobServiceClientBuilder()
        .endpoint(blobEndpoint)
        .credential(credential)
        .httpLogOptions(logOptions)
        .buildClient();
~~~

Mức **BASIC** dùng để minh họa ghi log metadata HTTP ở mức hạn chế. Chi tiết trường được ghi phụ thuộc SDK/version và logger settings; kiểm tra output thật trong test, đặc biệt khi endpoint hoặc URL chứa dữ liệu nhạy cảm.

**Tuyệt đối không log:** access token, refresh token, **Authorization**, account key, SAS query parameter, connection string, nội dung secret, request/response body có dữ liệu cá nhân hoặc credential của proxy.

Khi cần quan sát production:

- Dùng **request ID/correlation ID**, thời lượng, status, số retry, tỉ lệ lỗi và circuit metrics ở mức phù hợp.
- Tích hợp tracing/OpenTelemetry theo hỗ trợ của SDK và hệ thống giám sát đang dùng.
- Áp dụng sampling và giới hạn retention để tránh log khổng lồ.
- Giữ đúng ngữ cảnh trace khi request đi qua HTTP proxy; không tự ghi hoặc truyền token vào span attributes.

Logging HTTP là công cụ điều tra; nó không thay thế giám sát lỗi ở tầng nghiệp vụ và metric Azure service.

## 7. Proxy HTTP là gì và HTTPS CONNECT dùng để làm gì?

Một **HTTP forward proxy** là máy chủ trung gian mà client có thể phải đi qua để truy cập Internet. Với request tới dịch vụ **HTTPS**, client thường dùng **CONNECT** để thiết lập tunnel qua proxy, sau đó xác thực TLS với hostname đích theo cấu hình transport và proxy.

~~~mermaid
sequenceDiagram
    participant A as Spring Boot / Azure HTTP client
    participant P as Corporate HTTP proxy
    participant S as Azure Blob HTTPS endpoint
    A->>P: CONNECT stexample.blob.core.windows.net:443
    P-->>A: HTTP 200 Connection Established
    A->>S: TLS handshake qua tunnel
    S-->>A: TLS certificate cho hostname Azure
    A->>S: HTTPS request (token + Blob operation)
    S-->>A: Response theo RBAC / service policy
~~~

Tùy doanh nghiệp, proxy có thể cần xác thực hoặc thực hiện TLS inspection theo chính sách. Hệ thống phải tin cậy certificate chain hợp lệ qua trust store được quản lý; **không tắt TLS hostname verification hoặc certificate validation** để vượt qua lỗi proxy.

### HTTP proxy khác Private Endpoint

| Cơ chế | Chức năng | Điều cần nhớ |
| --- | --- | --- |
| **HTTP forward proxy** | Điều hướng/kiểm soát outbound HTTP(S) | Client/transport cần dùng proxy theo chính sách |
| **Private Endpoint / Private Link** | Cung cấp đường truy cập private IP tới Azure service trong mạng được hỗ trợ | DNS và route từ runtime phải đúng |
| **Firewall/VNet rule** | Hạn chế luồng truy cập được phép | RBAC đúng nhưng network sai vẫn thất bại |
| **Corporate TLS inspection** | Trung gian xử lý TLS theo chính sách | Cần trust chain đúng; không bỏ qua validation |

Với Private Endpoint, ứng dụng thường vẫn gọi **hostname chuẩn** của service (ví dụ **stexample.blob.core.windows.net**), còn DNS trong mạng riêng phân giải tới private IP. Nếu gửi mọi request qua corporate proxy ngoài VNet mà không có đường tới private endpoint, có thể vô tình phá vỡ tuyến private. Cần áp dụng **proxy bypass** theo thiết kế mạng tổ chức và kiểm tra nơi DNS thực sự được phân giải.

## 8. Cấu hình Netty HTTP transport với proxy

Azure SDK for Java có các HTTP transport như **azure-core-http-netty** và **azure-core-http-okhttp**. Khi dùng Netty, có thể tạo một **HttpClient** rồi truyền vào Blob builder.

Ví dụ dùng Netty transport và một HTTP proxy nội bộ:

~~~java
import com.azure.core.http.HttpClient;
import com.azure.core.http.ProxyOptions;
import com.azure.core.http.netty.NettyAsyncHttpClientBuilder;
import com.azure.core.credential.TokenCredential;
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.storage.blob.BlobServiceClient;
import com.azure.storage.blob.BlobServiceClientBuilder;

import java.net.InetSocketAddress;

public final class ProxyBlobClientFactory {

    private ProxyBlobClientFactory() {}

    public static BlobServiceClient create(
            String endpoint, String proxyHost, int proxyPort) {

        ProxyOptions proxyOptions = new ProxyOptions(
                ProxyOptions.Type.HTTP,
                new InetSocketAddress(proxyHost, proxyPort));

        HttpClient httpClient = new NettyAsyncHttpClientBuilder()
                .proxy(proxyOptions)
                .build();

        TokenCredential credential =
                new DefaultAzureCredentialBuilder().build();

        return new BlobServiceClientBuilder()
                .endpoint(endpoint)
                .credential(credential)
                .httpClient(httpClient)
                .buildClient();
    }
}
~~~

Đây là ví dụ **proxy cho HTTP transport của Blob client**. Để biên dịch, dự án cần dependency cung cấp **NettyAsyncHttpClientBuilder**, thường là **com.azure:azure-core-http-netty**; quản lý phiên bản đồng bộ với Spring Cloud Azure/Azure SDK BOM.

**Giới hạn quan trọng:** đoạn code trên **chưa bảo đảm các request lấy token của DefaultAzureCredential cũng đi qua proxy**. Azure Identity có thể dùng HTTP client riêng. Nếu môi trường chỉ cho phép outbound qua proxy, hãy cấu hình transport cho **credential/token acquisition** theo API của phiên bản Azure Identity đang dùng; kiểm chứng cả kết nối đến **Microsoft Entra** lẫn kết nối Blob.

### Những thứ không nên giả định

- Thiết lập biến **HTTPS_PROXY** có thể hữu ích nhưng **không mặc định được mọi Java transport/SDK đọc theo cùng một cách**.
- JVM properties như **https.proxyHost**/**https.proxyPort** không bảo đảm Netty và mọi Azure SDK áp dụng như một HTTP client JDK thông thường.
- Một HTTP proxy chỉ định cho Blob client **không tự cấu hình** Service Bus AMQP client hay Cosmos DB direct TCP transport.
- **NO_PROXY** hoặc danh sách bypass cũng phải được kiểm tra ở thư viện và runtime cụ thể.

Các thuộc tính proxy authentication, bypass, timeout và pool có thể khác nhau theo phiên bản HTTP provider. Nếu proxy yêu cầu tài khoản/mật khẩu, phải dùng API cấu hình proxy được transport hỗ trợ và lấy bí mật từ nơi quản lý secret; không đưa password vào source code hay log.

## 9. Ví dụ Spring Boot: cấu hình client trực tiếp qua bean

Khi ứng dụng cần proxy có điều kiện theo môi trường, có thể quản lý client ở tầng **@Configuration** và lấy thông số từ biến môi trường.

### 9.1. application.yml

~~~yaml
app:
  azure:
    blob:
      endpoint: ${AZURE_BLOB_ENDPOINT}
      container: ${AZURE_BLOB_CONTAINER:documents}
    proxy:
      host: ${APP_HTTP_PROXY_HOST:}
      port: ${APP_HTTP_PROXY_PORT:0}
~~~

Ở máy phát triển có thể để **APP_HTTP_PROXY_HOST** trống nếu được đi trực tiếp. Trong môi trường mạng có proxy, đặt host và port theo cấu hình được quản trị.

Không nên lưu username/password của proxy vào file cấu hình được commit lên Git. Nếu cần proxy authentication, dùng secret store/cơ chế cung cấp credential của nền tảng.

### 9.2. Spring @Configuration

~~~java
import com.azure.core.credential.TokenCredential;
import com.azure.core.http.HttpClient;
import com.azure.core.http.ProxyOptions;
import com.azure.core.http.netty.NettyAsyncHttpClientBuilder;
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.storage.blob.BlobServiceClient;
import com.azure.storage.blob.BlobServiceClientBuilder;
import java.net.InetSocketAddress;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class AzureBlobClientConfiguration {

    @Bean
    public BlobServiceClient blobServiceClient(
            @Value("${app.azure.blob.endpoint}") String endpoint,
            @Value("${app.azure.proxy.host:}") String proxyHost,
            @Value("${app.azure.proxy.port:0}") int proxyPort) {

        TokenCredential credential =
                new DefaultAzureCredentialBuilder().build();

        BlobServiceClientBuilder builder =
                new BlobServiceClientBuilder()
                        .endpoint(endpoint)
                        .credential(credential);

        if (!proxyHost.isBlank()) {
            if (proxyPort < 1 || proxyPort > 65535) {
                throw new IllegalArgumentException(
                        "Proxy port must be between 1 and 65535");
            }

            ProxyOptions options = new ProxyOptions(
                    ProxyOptions.Type.HTTP,
                    new InetSocketAddress(proxyHost, proxyPort));

            HttpClient httpClient = new NettyAsyncHttpClientBuilder()
                    .proxy(options)
                    .build();

            builder.httpClient(httpClient);
        }

        return builder.buildClient();
    }
}
~~~

Ví dụ chọn proxy có điều kiện cho **Blob HTTP transport**. Nếu credential cũng phải đi qua proxy, cần bổ sung cấu hình tương ứng cho **Azure Identity** dựa trên SDK version; nếu không, app vẫn có thể thất bại ngay bước lấy token.

Spring Boot quản lý **BlobServiceClient** như một bean dùng lại. Không tạo nó trong từng controller method. Trong các hệ thống lớn, có thể định nghĩa config properties riêng và validation cho hostname, port, endpoint, retry và timeout.

### 9.3. Dịch vụ nghiệp vụ

~~~java
import com.azure.storage.blob.BlobContainerClient;
import com.azure.storage.blob.BlobServiceClient;
import java.io.ByteArrayInputStream;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

@Service
public class DocumentBlobStorage {

    private final BlobContainerClient container;

    public DocumentBlobStorage(
            BlobServiceClient client,
            @Value("${app.azure.blob.container}") String containerName) {
        this.container = client.getBlobContainerClient(containerName);
    }

    public void upload(String name, byte[] bytes) {
        container.getBlobClient(name).upload(
                new ByteArrayInputStream(bytes), bytes.length, false);
    }
}
~~~

Hàm chỉ thao tác dữ liệu, không biết proxy host hay credential details. **Blob container phải tồn tại**, identity cần role ghi phù hợp và mạng phải cho phép request. Với dữ liệu lớn, nên chuyển sang streaming/multipart theo API phù hợp; không giữ toàn bộ file trong byte array ở mọi tình huống production.

## 10. Dùng Spring Cloud Azure starter hay tự định nghĩa builder?

Một dự án đã sử dụng **spring-cloud-azure-starter-storage-blob** có thể inject **BlobServiceClient** do starter tự cấu hình. Điều này phù hợp khi chỉ cần endpoint/account, identity và các property phổ biến mà phiên bản Spring Cloud Azure hỗ trợ.

Khi cần proxy/pipeline đặc thù, có hai hướng:

| Hướng | Ưu điểm | Cần kiểm tra |
| --- | --- | --- |
| **Giữ auto-configuration, dùng thuộc tính hoặc điểm mở rộng được hỗ trợ** | Giữ quy ước Spring Cloud Azure và dependency wiring của starter | Property/customizer cụ thể **phụ thuộc phiên bản**; không tự đoán tên cấu hình |
| **Tự khai báo BlobServiceClient bean** | Kiểm soát endpoint, transport, credential, policy và pool | Tránh tạo trùng bean, điều kiện auto-configuration, qualifier và dependency |

Trước khi thêm cấu hình, kiểm tra **tài liệu chính thức theo phiên bản Spring Cloud Azure**. Một số starter có cơ chế tùy chỉnh riêng; không giả định mọi starter đều có cùng tên property hoặc một customizer dùng được cho mọi client Azure.

### Vấn đề bean trùng và cấu hình thiếu nhất quán

Nếu starter đã tạo một **BlobServiceClient** mà ứng dụng lại tạo thêm một bean cùng kiểu, constructor injection có thể bị ambiguous hoặc một cấu hình ưu tiên bean khác. Các khả năng tùy theo điều kiện auto-configuration:

- Spring Boot có thể bỏ qua một bean tự động nếu đã tồn tại bean ứng dụng cùng kiểu.
- Có thể có nhiều client cho nhiều Azure account khi ứng dụng chủ động định nghĩa.
- Nếu cần nhiều client, nên dùng **@Qualifier** và đặt tên bean rõ nghĩa.

Không dựa vào việc “bean nào tình cờ thắng” để quyết định client production. Nên kiểm tra **condition evaluation report** và integration test xác nhận endpoint/credential thực sự được dùng.

## 11. Riêng với Service Bus và Event Hubs: AMQP khác HTTP

Blob Storage, Key Vault Secrets và nhiều SDK khác dùng HTTP(S) cho data plane, nhưng **Azure Service Bus** và **Azure Event Hubs** chủ yếu dùng giao thức **AMQP** cho messaging. Vì vậy một HttpClient Netty cấu hình proxy cho Blob **không tự điều khiển** kết nối AMQP của messaging client.

Thông thường:

- **AMQP over TCP** sử dụng cổng và giao thức riêng, thường là **5671/TLS**.
- Một số Azure messaging SDK có chế độ **AMQP over WebSockets** để đi qua **443**, hữu ích ở mạng chặn cổng AMQP trực tiếp.
- WebSockets trên 443 **không tự bảo đảm** tương thích với mọi corporate proxy; phải kiểm tra hỗ trợ proxy trong SDK transport cụ thể.
- Event Hubs có mô hình partition/checkpoint; quyền đọc event không tự cấp quyền Blob nếu consumer lưu checkpoint trong Blob Storage.

Ví dụ chọn transport qua WebSockets đối với Service Bus Java SDK ở phiên bản hỗ trợ:

~~~java
import com.azure.core.amqp.AmqpTransportType;
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.messaging.servicebus.ServiceBusClientBuilder;

ServiceBusClientBuilder builder = new ServiceBusClientBuilder()
        .fullyQualifiedNamespace("orders-dev.servicebus.windows.net")
        .credential(new DefaultAzureCredentialBuilder().build())
        .transportType(AmqpTransportType.AMQP_WEB_SOCKETS);
~~~

Đây chỉ là phần cấu hình **builder**, chưa tạo sender/receiver hoặc gửi message. SDK/version có thể có thêm thiết lập proxy riêng cho AMQP transport; phải tham khảo tài liệu dịch vụ và xác nhận trong môi trường mạng thực tế. **Không truyền Blob HttpClient vào Service Bus builder theo suy đoán**.

### Cosmos DB cũng có các chế độ kết nối khác

Azure Cosmos DB Java SDK có thể dùng **direct mode** hoặc **gateway mode** tùy API và cấu hình. Direct mode liên quan kết nối/giao thức khác HTTPS gateway. Nếu mạng yêu cầu tất cả lưu lượng đi qua HTTP proxy, cần xem lại lựa chọn mode, connection settings và hỗ trợ proxy thực tế của **CosmosClientBuilder**. Không cho rằng cùng một property proxy Java sẽ tự điều hướng cả direct TCP.

## 12. Retry, timeout và idempotency

Azure SDK thường có retry mặc định hoặc các tùy chọn retry riêng theo từng dịch vụ. Khi tùy chỉnh, cần phân biệt:

| Khái niệm | Nghĩa | Rủi ro khi đặt sai |
| --- | --- | --- |
| **Connect timeout** | Giới hạn thời gian thiết lập TCP/TLS/tunnel theo transport | Quá ngắn gây lỗi giả khi mạng/proxy có độ trễ |
| **Read/response timeout** | Giới hạn thời gian chờ dữ liệu/phản hồi | Quá dài làm treo luồng; quá ngắn gây retry thừa |
| **Operation timeout/budget** | Thời gian tổng cho một thao tác theo SDK/API | Thiếu giới hạn khiến request kéo dài |
| **Retry count** | Số lần thử lại với lỗi được coi là có thể khôi phục | Nhiều retry gây tải tăng và chi phí lớn |
| **Backoff/jitter** | Khoảng nghỉ tăng dần và phân tán giữa các lần retry | Không có backoff có thể tạo retry storm |
| **Idempotency** | Gọi lại có làm thay đổi kết quả nghiệp vụ không | Upload/ghi đè hoặc gửi message lặp |

Không tự viết retry mọi lỗi. Chẳng hạn **401/403 do sai identity hoặc quyền** thường không được giải quyết bằng retry lặp vô hạn; **429 hoặc 503** có thể cần backoff theo tín hiệu/thông báo của dịch vụ. Nếu hệ thống gửi Service Bus message, phải xét trường hợp một request **đã được xử lý nhưng client mất response**; retry có thể tạo message trùng và cần thiết kế deduplication theo nghiệp vụ.

### Các lớp retry có thể chồng nhau

Một service có thể có retry ở:

1. HTTP client/SDK.
2. Spring Retry hoặc retry ở application service.
3. Reverse proxy/service mesh.
4. Queue worker hoặc một job scheduler.

Nếu mỗi lớp retry ba lần, tổng số request thực tế có thể tăng nhiều hơn dự định. Hãy chọn **một chính sách ngân sách retry rõ ràng**, đo độ trễ đầu-cuối và chỉ bật retry ở lớp cần thiết.

### Proxy timeout không phải Azure service timeout

Proxy có thể chủ động ngắt một tunnel hoặc kết nối idle. Khi đó SDK thường thấy timeout, connection reset hoặc 502/504 từ proxy, không nhất thiết là Azure service quá tải. Cần so sánh log proxy với request ID phía Azure; nếu request chưa tới Azure, sẽ không có request ID dịch vụ tương ứng.

## 13. Chẩn đoán lỗi kết nối theo lớp

| Dấu hiệu | Nghi vấn | Kiểm tra |
| --- | --- | --- |
| **407 Proxy Authentication Required** | Proxy yêu cầu credential, cấu hình proxy auth không đúng | Xác minh proxy hostname/port và credential qua cơ chế được duyệt |
| **502/504 từ proxy** | Proxy không tới được upstream, timeout hoặc policy chặn | So sánh proxy log, route, DNS và thời điểm lỗi |
| **UnknownHostException** | DNS sai hoặc proxy thực hiện DNS theo cách khác dự kiến | Kiểm tra DNS từ chính runtime và nơi proxy chạy |
| **PKIX path building failed / SSLHandshakeException** | CA trust chain, TLS inspection, hostname mismatch | Kiểm tra certificate/trust store; không tắt validation |
| **ConnectTimeoutException** | Không có đường TCP, proxy sai hoặc firewall | Kiểm tra outbound, VNet, endpoint, cổng |
| Lấy được Blob endpoint nhưng **credential unavailable** | Azure Identity token request không đi qua đúng môi trường mạng hoặc identity chưa cấu hình | Kiểm tra token endpoint, managed/workload identity và transport của credential |
| **401/403 từ Blob** | Token/audience, RBAC, Shared Key/SAS hoặc network policy | Xác minh principal, DataActions, scope và mã lỗi Azure |
| **429/503** | Throttling, tải hoặc sự cố dịch vụ | Xem Retry-After, metric, backoff và concurrency |
| Service Bus không kết nối qua TCP/5671 | Firewall/proxy chặn AMQP trực tiếp | Kiểm tra AMQP over WebSockets/443 và proxy support thực tế |
| Blob hoạt động, Event Hubs không | Hai client dùng transport/protocol khác nhau | Kiểm tra builder/port/proxy riêng của Event Hubs |
| Local chạy được, AKS timeout | Pod DNS, VNet, Private Endpoint hoặc egress policy khác laptop | Test từ Pod/runtime đích, không chỉ từ developer machine |
| Chỉ lỗi khi upload file lớn | Proxy body size/idle timeout, SDK transfer setting, memory | Xem log proxy, chunking, stream, timeout và giới hạn dịch vụ |

**Không vội đổi RBAC khi lỗi là 407 hoặc TLS handshake.** Ngược lại, sửa proxy không giải quyết role **Storage Blob Data Contributor** đang thiếu. Mỗi tầng có log và thông tin chẩn đoán riêng.

### Quy trình debug thực tế

~~~mermaid
flowchart TD
    A[Azure SDK call thất bại] --> B{Endpoint/hostname đúng?}
    B -->|Không| C[Sửa endpoint và cloud environment]
    B -->|Có| D{Có kết nối qua DNS/proxy/TLS?}
    D -->|Không| E[Kiểm tra proxy, route, trust store]
    D -->|Có| F{Credential lấy được token?}
    F -->|Không| G[Kiểm tra identity source và token network path]
    F -->|Có| H{Azure trả 401/403?}
    H -->|Có| I[Kiểm tra audience, RBAC, scope, service policy]
    H -->|Không| J[Kiểm tra retry, quota, payload và service response]
~~~

**Thứ tự chẩn đoán có thể thay đổi** vì Azure Identity token acquisition cũng cần kết nối mạng trước khi gọi resource. Điểm chính là chia lỗi thành hai luồng độc lập: kết nối lấy token và kết nối tới dịch vụ dữ liệu.

## 14. Kiểm thử HTTP pipeline và proxy

### 14.1. Unit test

Ở mức unit test, không cần kết nối Azure thật:

- Test policy có thêm header đúng với request giả lập mà không làm thay đổi Authorization header.
- Test việc chọn HTTP transport có proxy khi host/port được cấu hình.
- Test validation của endpoint, proxy port và trường hợp không có proxy.
- Mock/fake adapter truy cập Azure để kiểm tra business logic khi SDK trả 401, 403, 429 hoặc timeout.

Nếu cần kiểm thử pipeline HTTP chi tiết, có thể dùng **Azure Core test utilities** hoặc fake HTTP transport theo API tương ứng với bản SDK đang dùng. Không kết nối production service trong unit test.

### 14.2. Integration test cục bộ

Một môi trường lab có thể dùng:

1. **Azurite** để kiểm tra một phần thao tác Blob Storage qua HTTP(S) được emulator hỗ trợ.
2. Một **HTTP test proxy** hoặc proxy thật trong môi trường dev để xác minh CONNECT, logging và rule bypass.
3. Certificate/trust store test an toàn nếu doanh nghiệp có TLS inspection.
4. Một endpoint mô phỏng lỗi 429/503/timeout để kiểm tra policy retry.

Azurite không thay thế đầy đủ **Microsoft Entra**, **Azure RBAC**, Private Endpoint hoặc behavior của dịch vụ Azure thật. Test proxy cục bộ cũng không chứng minh đường đi mạng production sẽ giống hệt.

### 14.3. Integration test trong Azure

Triển khai Spring Boot với danh tính và mạng giống môi trường thực tế:

- Chọn đúng managed identity/workload identity và role data plane trên tài nguyên test.
- Xác nhận request lấy token và request Blob đều đi qua route/proxy được cho phép.
- Thử trường hợp không bật proxy, bật proxy, proxy chặn, timeout và 403 có kiểm soát.
- Kiểm tra request ID, số retry và thời lượng thực tế; tránh log token và secret.
- Với Service Bus/Event Hubs, kiểm tra **AMQP hoặc WebSockets** theo network profile, không dùng kết quả Blob HTTP thay thế.

Kiểm tra context Spring Boot khởi động là cần nhưng **chưa đủ**: một số lỗi chỉ xuất hiện khi client thực sự kết nối hoặc cần access token.

## 15. Bảo mật khi tùy chỉnh network và pipeline

Các nguyên tắc nên giữ xuyên suốt:

1. **Không tắt TLS verification** để vượt proxy hoặc certificate error. Cài CA hợp lệ theo chính sách và sử dụng hostname của dịch vụ.
2. **Không đưa token/secret vào header tùy chỉnh hoặc HTTP log**; các thông tin này có thể đi qua proxy và hệ thống quan sát.
3. **Không commit proxy credentials** vào **application.yml**, **gradle.properties**, Dockerfile hay scripts.
4. **Giảm quyền Azure RBAC:** network connectivity không cấp quyền data plane; principal vẫn cần role trên resource đích.
5. **Kiểm soát egress:** chỉ cho phép endpoint cần thiết, bao gồm Microsoft Entra endpoint khi credential cần token.
6. **Không mở rộng proxy bypass tùy tiện:** đối chiếu với kiến trúc Private Endpoint, VNet và cơ chế DNS.
7. **Tái sử dụng HTTP client/connection pool:** tránh tạo transport cho mỗi request và tăng nguy cơ resource exhaustion.
8. **Chỉ dùng policy có chủ đích:** có test đối với tác động retry, observability và lỗi khi giao tiếp qua proxy.
9. **Giám sát tài nguyên:** connection count, retry, timeout, 407, 429 và 5xx theo từng endpoint.
10. **Version compatibility:** quản lý **azure-core**, transport và Azure SDK bằng BOM phù hợp với Spring Cloud Azure/Spring Boot đang dùng.

## 16. So sánh Azure với AWS và Google Cloud

| Vấn đề | Azure SDK for Java | AWS SDK for Java v2 | Google Cloud Java libraries |
| --- | --- | --- | --- |
| Client construction | **BlobServiceClientBuilder**, **SecretClientBuilder**, các builder theo dịch vụ | Builder theo service, ví dụ S3 client builder | Client/settings builder theo từng Google Cloud API |
| HTTP transport | Azure Core HttpClient: Netty/OkHttp tùy module | Apache/Netty/JDK/CRT transport tùy client | HTTP/JSON hoặc gRPC transport tùy service |
| Credential | **TokenCredential**, DefaultAzureCredential | **AwsCredentialsProvider**, provider chain | **GoogleCredentials**, Application Default Credentials |
| Proxy | Cấu hình theo HTTP provider hoặc SDK dịch vụ | Cấu hình theo HTTP client/protocol | Cấu hình theo HTTP/gRPC transport tương ứng |
| Retry/tracing | HTTP pipeline/policy và SDK-specific options | SDK interceptor/retry strategy theo client | Client settings/retry/gRPC interceptors tùy dịch vụ |
| Quyền | Microsoft Entra + Azure RBAC hoặc data authorization riêng | IAM policies/roles và service policy | Cloud IAM và authorization theo service |

Điểm chung là cần tách **client settings**, **transport**, **credential** và **authorization**. Điểm khác biệt là không thể copy một biến proxy hoặc timeout từ Azure sang AWS/GCP rồi mặc định hiệu lực giống nhau. Chẳng hạn AWS S3 và Azure Blob đều dùng HTTP nhưng vẫn có khác biệt về endpoint, signing/token, retry và data consistency; Google Cloud SDK có thể dùng gRPC.

## 17. Bài thực hành: Blob client chạy qua corporate proxy

**Bối cảnh:** ứng dụng Spring Boot Documents API có thể chạy trực tiếp trên laptop nhưng môi trường CI chỉ được truy cập Azure qua proxy. Mục tiêu là cấu hình client an toàn, kiểm thử cả việc lấy token và upload Blob.

1. **Chuẩn bị lab:** Storage Account và container private **documents**, một identity test có **Storage Blob Data Contributor**, Blob endpoint và proxy test được cấp phép.
2. **Chọn dependencies:** Spring Boot tương thích, BOM **spring-cloud-azure-dependencies** khi dùng Spring Cloud Azure starter hoặc Azure SDK BOM khi dùng SDK trực tiếp; bảo đảm có Netty HTTP provider nếu sử dụng code tương ứng.
3. **Tạo Spring bean:** sử dụng BlobServiceClientBuilder, endpoint từ biến môi trường, DefaultAzureCredential hoặc một credential tường minh theo môi trường.
4. **Thêm proxy:** dùng NettyAsyncHttpClientBuilder với ProxyOptions; validation proxy host/port. Thực hiện upload test.
5. **Kiểm tra token acquisition:** xác định nguồn danh tính; nếu login Entra thất bại do proxy, cấu hình đường HTTP của Azure Identity theo SDK version và thử lại.
6. **Thêm logging BASIC:** quan sát endpoint, status, latency và request ID; xác nhận không lộ Authorization, SAS hoặc proxy secret.
7. **Thử lỗi có kiểm soát:** cấu hình proxy sai, chặn upstream test, thu hồi data role trên identity test rồi ghi nhận khác biệt **407/TLS/timeout/403**.
8. **Thử Private Endpoint nếu lab hỗ trợ:** so sánh DNS và route khi proxy bypass cho endpoint private, không đổi hostname chuẩn một cách tùy tiện.
9. **Mở rộng messaging:** dùng Service Bus sender ở môi trường mạng hạn chế, so sánh AMQP/TCP với WebSockets/443 và cấu hình proxy riêng.
10. **Tổng hợp báo cáo:** bảng endpoint, principal, transport, proxy mode, TLS, retry, mã lỗi, request ID và giải thích tầng gây lỗi.

### Câu hỏi tự kiểm tra

1. Vì sao khởi tạo **BlobServiceClient** thành công chưa chứng minh mạng hoặc RBAC hoạt động?
2. **HttpClient** của Azure SDK khác **BlobServiceClient** ở trách nhiệm nào?
3. Vì sao cấu hình HTTP proxy cho Blob client có thể chưa giúp DefaultAzureCredential lấy token?
4. HTTP CONNECT có vai trò gì khi client gọi Blob endpoint HTTPS?
5. Có nên tắt TLS certificate validation để xử lý lỗi PKIX từ corporate proxy không? Vì sao?
6. Vì sao Service Bus AMQP qua 5671 và WebSockets qua 443 cần được kiểm tra riêng với Blob HTTP?
7. Lỗi **407 Proxy Authentication Required** nên được xử lý ở lớp nào, khác **403 từ Azure Blob** ra sao?
8. Nếu cùng lúc bật retry ở SDK, Spring và proxy, điều gì xảy ra với số request thực tế?
9. Spring Cloud Azure starter có thể bị ảnh hưởng thế nào khi ứng dụng tự tạo thêm một BlobServiceClient bean?
10. Một test Azurite qua proxy chứng minh điều gì và còn thiếu bằng chứng nào về managed identity/RBAC?

## 18. Ghi nhớ

- **Service builder** chọn endpoint, credential và cấu hình client; **HTTP pipeline** áp dụng policy; **HTTP transport** gửi request; **proxy** là một phần của đường mạng.
- **DefaultAzureCredential** có thể cần đường mạng để lấy token riêng với kết nối data endpoint; cấu hình proxy cho Blob chưa chắc cấu hình proxy cho Azure Identity.
- **Spring Cloud Azure starter** giảm phần wiring Spring Boot. Khi cần tùy chỉnh chuyên sâu, dùng điểm mở rộng được phiên bản hỗ trợ hoặc bean client tường minh và kiểm soát xung đột bean.
- **Service Bus/Event Hubs** dùng AMQP/WebSockets; **Cosmos DB** có thể dùng direct/gateway. Không áp đặt HTTP proxy của Blob cho mọi dịch vụ.
- Quản lý **retry, timeout, TLS, logging và connection pool** có chủ đích; không log token/secret, không tắt xác minh chứng chỉ và luôn kiểm thử request thật với identity/network phù hợp.

## Tài liệu tham khảo

- [Azure SDK for Java — Get started](https://learn.microsoft.com/azure/developer/java/sdk/get-started)
- [Azure SDK for Java — HTTP clients](https://learn.microsoft.com/azure/developer/java/sdk/http-client-pipelines)
- [Azure Core SDK for Java API](https://learn.microsoft.com/java/api/overview/azure/core-readme)
- [Azure Storage Blob client library for Java](https://learn.microsoft.com/java/api/overview/azure/storage-blob-readme)
- [Azure Identity client library for Java](https://learn.microsoft.com/java/api/overview/azure/identity-readme)
- [Azure Service Bus client library for Java](https://learn.microsoft.com/java/api/overview/azure/messaging-servicebus-readme)
- [Spring Cloud Azure documentation](https://learn.microsoft.com/azure/developer/java/spring-framework/)
