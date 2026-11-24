# Vòng đời client, khả năng dùng chung và đóng tài nguyên

Một ứng dụng Spring Boot có thể gọi hàng nghìn lần tới Amazon S3, Azure Blob Storage hoặc Google Cloud Storage trong suốt thời gian chạy. Nếu mỗi lần gọi đều tạo một SDK client mới, ứng dụng phải lặp lại việc cấu hình credential, khởi tạo transport, tạo hoặc lấy kết nối, và cuối cùng xử lý các tài nguyên mạng chưa được giải phóng. Nếu đóng một client đang được nhiều request dùng chung quá sớm, các request đang chạy lại có thể thất bại. Vì vậy, quyết định **ai tạo client, ai được dùng chung và ai chịu trách nhiệm đóng** là một phần của kiến trúc tích hợp, không đơn thuần là thao tác dọn dẹp lúc chương trình kết thúc.

Bài thuộc chương **Kiến trúc tích hợp** của mô-đun **SPRING_CLOUD_PROVIDER_INTEGRATION**. Phạm vi thực hành là tích hợp Spring Boot với các dịch vụ managed của **AWS, Azure và Google Cloud** qua thư viện Spring Cloud tương ứng: cấu hình danh tính và quyền, storage, messaging, dữ liệu, secret, kiểm thử tích hợp và so sánh provider. Bài này tập trung vào vòng đời **SDK client, kết nối và tài nguyên I/O** trong Spring application context, kể cả client đồng bộ, bất đồng bộ và các listener chạy nền.

## 1. Kết quả cần đạt

Sau bài học, bạn có thể:

- Phân biệt vòng đời **Spring bean**, **SDK client**, **HTTP/gRPC transport**, **connection pool**, **credential provider** và tài nguyên phát sinh từ từng request.
- Giải thích vì sao thường **tái sử dụng client** cho nhiều request, đồng thời chỉ ra điều kiện để một client thực sự có thể dùng chung an toàn.
- Cấu hình một AWS SDK v2 client do Spring sở hữu và đóng đúng lúc application context kết thúc.
- Phân biệt hai trường hợp SDK tự sở hữu transport và ứng dụng truyền vào một transport đã tạo sẵn.
- Nhận diện khác biệt về đóng tài nguyên giữa AWS SDK, Azure SDK, Google Cloud client libraries, listener messaging và database pool.
- Thiết kế graceful shutdown, kiểm thử việc đóng client và chẩn đoán rò rỉ connection, thread, buffer hoặc resource handle.

## 2. Vòng đời từ startup đến shutdown

Trong một ứng dụng sử dụng Spring Cloud starter, client thường có bốn giai đoạn:

1. **Tạo và cấu hình:** Spring Boot đọc properties, đánh giá auto-configuration, tạo bean SDK client/template, gắn region/project/account, credential provider và transport.
2. **Sẵn sàng phục vụ:** Bean được inject vào adapter/service. Một số SDK lấy credential và khởi tạo kết nối **khi thực hiện lời gọi đầu tiên**; khởi động Spring thành công không chứng minh endpoint hay quyền cloud hợp lệ.
3. **Tái sử dụng trong runtime:** Nhiều request/worker dùng cùng client theo hợp đồng thread safety, trong khi connection pool, executor, credential provider hoặc gRPC channel phục vụ hoạt động bên dưới.
4. **Dừng và giải phóng:** Hệ thống ngừng nhận việc mới, xử lý hoặc dừng công việc còn chạy theo giới hạn thời gian, rồi đóng những thành phần mà ứng dụng sở hữu.

~~~mermaid
flowchart LR
    A[Boot: đọc cấu hình] --> B[Auto-config / @Bean]
    B --> C[SDK client bean]
    D[Credential provider] --> C
    T[HTTP / gRPC transport] --> C
    C --> E[Spring service / adapter]
    E --> R[Nhiều request và background worker]
    R --> CLOUD[Managed service]
    Z[ApplicationContext shutdown] --> STOP[Dừng nhận công việc mới]
    STOP --> DRAIN[Chờ tác vụ đang chạy có giới hạn]
    DRAIN --> CLOSE[Đóng client sở hữu]
    CLOSE --> TRANS[Giải phóng transport sở hữu]
~~~

**Thứ tự đóng** rất quan trọng: một listener vẫn đang nhận message không nên mất client trước khi hoàn tất ack/cleanup; một SDK client vẫn đang gọi cloud không nên bị đóng transport dưới chân. Ở runtime, đường gọi thực tế vẫn đi từ **service → adapter → SDK → cloud**, còn Spring chịu trách nhiệm tạo và quản lý các bean.

## 3. Các tài nguyên dễ bị nhầm là một

| Thành phần | Vai trò | Ai thường sở hữu? | Khi nào cần đóng? |
| --- | --- | --- | --- |
| **Spring bean** | Đối tượng do ApplicationContext quản lý | Spring context | Khi context đóng, theo destruction callback hợp lệ |
| **SDK service client** | API gọi một dịch vụ cloud | Spring bean hoặc người trực tiếp tạo client | Theo hợp đồng SDK; nhiều AWS SDK v2 client có **close()** |
| **HTTP client / connection pool** | Kết nối, socket, TLS, keep-alive, giới hạn concurrent I/O | SDK hoặc người truyền transport vào | Khi **owner** kết thúc, sau khi mọi client dùng chung đã dừng |
| **gRPC channel / executor** | Quản lý kết nối và thread nền cho một số SDK | Client library hoặc cấu hình ứng dụng | Theo API shutdown/close riêng của thư viện |
| **Credential provider** | Tìm, lấy và refresh danh tính/token | SDK hoặc ứng dụng | Nếu provider thực sự sở hữu resource đóng được, theo hợp đồng provider |
| **Listener container / subscriber** | Poll/receive message và gọi handler | Spring Cloud hoặc ứng dụng | Dừng nhận message và xử lý ack trước khi đóng client |
| **Response stream / file handle** | Giữ dữ liệu của **một thao tác** | Code gọi thao tác | Đóng sớm nhất khi đã đọc/ghi xong, thường bằng try-with-resources |

Không được đồng nhất **GC thu hồi Java object** với **giải phóng tài nguyên mạng có giới hạn**. Dù object không còn tham chiếu, thread, socket, connection pool hay native buffer có thể tồn tại lâu hơn mong đợi. Đồng thời, không phải client nào của mọi provider cũng triển khai cùng interface đóng tài nguyên: phải kiểm tra API và hướng dẫn **đúng thư viện, đúng phiên bản**.

## 4. Khả năng dùng chung: client khác request builder và response stream

Các service client chính của **AWS SDK for Java v2** được thiết kế để tái sử dụng và hỗ trợ nhiều lời gọi đồng thời; ví dụ **S3Client** không cần tạo mới cho mỗi upload. Nhiều client được cung cấp bởi **Azure SDK for Java** cũng được thiết kế để tái sử dụng/thread-safe. Với **Google Cloud Java client libraries**, cần đối chiếu thread-safety và cách quản lý resource của đúng client/transport dùng trong dự án.

Sự an toàn của một SDK client **không kéo theo** mọi đối tượng đi kèm đều thread-safe:

- **Request builder** là đối tượng cấu hình mutable: nên tạo builder mới cho từng thao tác, không chia sẻ rồi chỉnh cùng lúc giữa nhiều thread.
- **Request/response stream**, iterator, upload session và các đối tượng mang trạng thái của một request có vòng đời riêng; thường không nên dùng chung đồng thời.
- **Client** có thể tái sử dụng, nhưng **pool** vẫn giới hạn connection, stream hoặc số call đồng thời. Thread-safe không có nghĩa capacity vô hạn.
- **Credential provider** thường có chiến lược cache/refresh riêng. Không cần tạo client mới cho mỗi lần token hết hạn nếu SDK/provider được thiết kế để tự refresh.
- **Client gắn với region, endpoint, account và identity** cụ thể. Không dùng chung client cho những security boundary khác nhau nếu cách chia sẻ khiến quyền hoặc dữ liệu có thể bị trộn.

Ví dụ đơn giản về hai adapter cùng dùng một **S3Client** được Spring quản lý:

~~~java
import org.springframework.stereotype.Component;
import software.amazon.awssdk.services.s3.S3Client;

@Component
public class InvoiceObjectAdapter {
    private final S3Client s3;

    public InvoiceObjectAdapter(S3Client s3) {
        this.s3 = s3;
    }
}

@Component
public class ReportObjectAdapter {
    private final S3Client s3;

    public ReportObjectAdapter(S3Client s3) {
        this.s3 = s3;
    }
}
~~~

Hai adapter nhận **cùng một bean singleton** khi context có đúng một bean **S3Client** phù hợp. Code trên chỉ minh họa injection; phương thức nghiệp vụ sẽ gọi các API khác nhau qua trường **s3**. **Singleton** là scope mặc định của Spring bean, nhưng SDK không tự biến thành singleton nếu code tự gọi **S3Client.builder().build()** mỗi lần request.

## 5. Để Spring Cloud starter sở hữu SDK client khi không cần tùy chỉnh

Với **Spring Boot 3 + Spring Cloud AWS 3.x**, starter S3 có thể cung cấp SDK client bean thông qua auto-configuration nếu các điều kiện tương ứng được đáp ứng. Khai báo Maven minh họa, với version do BOM tương thích quản lý:

~~~xml
<dependency>
    <groupId>io.awspring.cloud</groupId>
    <artifactId>spring-cloud-aws-starter-s3</artifactId>
</dependency>
~~~

~~~yaml
spring:
  cloud:
    aws:
      region:
        static: ap-southeast-1
app:
  storage:
    bucket: ${APP_STORAGE_BUCKET}
~~~

Trong cấu hình này, **spring.cloud.aws.region.static** phục vụ cấu hình AWS của starter; **app.storage.bucket** là property ứng dụng tự định nghĩa. Bucket không phải credential; ưu tiên IAM role/workload identity và quyền tối thiểu khi chạy trên cloud. Khi chỉ cần client đã được starter tạo, hãy **inject bean**, tránh khai báo thêm một bean mới chỉ vì muốn sử dụng SDK.

Spring Boot quản lý vòng đời các bean do cấu hình tạo ra. Tuy nhiên, **việc starter có tạo loại client nào, tự đóng loại resource nào và có thể thay client mặc định bằng bean tự tạo hay không phụ thuộc phiên bản**. Cần kiểm tra condition report, bean graph và hướng dẫn của đúng starter. Một bean có mặt khi startup không khẳng định credentials hoặc IAM/RBAC đã được kiểm chứng.

## 6. Tự định nghĩa AWS SDK client và giao quyền đóng cho Spring

Nếu cần kiểm soát builder hoặc một cấu hình mà starter không hỗ trợ, có thể tự đăng ký **S3Client** dưới dạng singleton bean:

~~~java
// AwsClientConfiguration.java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;

@Configuration(proxyBeanMethods = false)
public class AwsClientConfiguration {

    @Bean(destroyMethod = "close")
    S3Client s3Client(@Value("${app.aws.region}") String region) {
        return S3Client.builder()
            .region(Region.of(region))
            .build();
    }
}
~~~

~~~yaml
app:
  aws:
    region: ap-southeast-1
~~~

**@Bean(destroyMethod = "close")** yêu cầu Spring gọi **S3Client.close()** khi bean bị hủy, thường lúc application context đóng. Spring cũng có cơ chế suy luận phương thức **close/shutdown** cho nhiều bean khai báo bằng **@Bean**, nhưng khai báo tường minh giúp người đọc thấy ngay ai sở hữu vòng đời. Bean được tạo một lần trong singleton scope, dùng nhiều lần và chỉ đóng khi context kết thúc. Spring không tự gọi **close** sau mỗi phương thức của adapter.

Ví dụ **không hard-code access key**. Khi không chỉ định credential provider, AWS SDK dùng cơ chế tìm credentials mặc định theo môi trường của SDK. Phải cấp quyền ghi/đọc tài nguyên cụ thể cho workload. Nếu Spring Cloud AWS starter cũng được sử dụng, chỉ nên đăng ký một client tùy chỉnh sau khi xác minh **@ConditionalOnMissingBean** hoặc điều kiện tương ứng: không mặc định rằng mọi phiên bản starter đều tự back off.

**Điểm tránh nhầm:** Dùng **try-with-resources** để tạo và đóng một S3Client là hợp lý với một chương trình CLI hoặc công việc có vòng đời độc lập:

~~~java
try (S3Client s3 = S3Client.builder()
        .region(Region.AP_SOUTHEAST_1)
        .build()) {
    // Thực hiện các thao tác của một tác vụ ngắn hạn.
}
~~~

Trong REST controller hoặc message handler phục vụ liên tục, tạo client bên trong một **try** ở mỗi request sẽ gây churn connection/resource và làm mất lợi ích pooling. Khi bean đã được Spring sở hữu, **không gọi s3.close() trong handler**: các request khác có thể vẫn dùng bean đó.

## 7. Quyền sở hữu transport: builder khác client có sẵn

SDK client không phải tài nguyên duy nhất. AWS SDK v2 có thể sử dụng một HTTP transport do **SDK tạo từ builder** hoặc một **HTTP client instance do ứng dụng đưa vào**. Hai kiểu mang trách nhiệm đóng khác nhau.

### 7.1. SDK tự quản lý HTTP client do builder tạo

~~~java
// Một phương án thay thế cấu hình S3Client ở phần 6.
@Bean(destroyMethod = "close")
S3Client s3Client(@Value("${app.aws.region}") String region) {
    return S3Client.builder()
        .region(Region.of(region))
        .httpClientBuilder(
            ApacheHttpClient.builder().maxConnections(64))
        .build();
}
~~~

Đoạn code cần import **ApacheHttpClient**, **S3Client**, **Region**, **@Bean**, **@Value** và dependency transport **software.amazon.awssdk:apache-client** (phiên bản đồng bộ qua AWS SDK BOM). Khi truyền **httpClientBuilder(...)**, SDK tạo và sở hữu HTTP client nội bộ; đóng **S3Client** sẽ đóng transport do nó sở hữu theo hợp đồng AWS SDK v2.

Không nhất thiết cấu hình số connection như ví dụ. Giá trị phù hợp phụ thuộc request concurrency, độ trễ I/O, kích thước payload, quota và khả năng chạy của ứng dụng. Nếu chỉ cần mặc định, để SDK chọn HTTP transport bằng dependency/config tương thích thường đơn giản hơn.

### 7.2. Ứng dụng sở hữu một HTTP client dùng chung

Nếu nhiều SDK client cần chia sẻ cùng một HTTP transport, ứng dụng có thể tạo nó thành **bean riêng**:

~~~java
// AwsSharedTransportConfiguration.java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import software.amazon.awssdk.http.SdkHttpClient;
import software.amazon.awssdk.http.apache.ApacheHttpClient;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.sqs.SqsClient;

@Configuration(proxyBeanMethods = false)
public class AwsSharedTransportConfiguration {

    @Bean(destroyMethod = "close")
    SdkHttpClient sharedAwsHttpClient() {
        return ApacheHttpClient.builder()
            .maxConnections(80)
            .build();
    }

    @Bean(destroyMethod = "close")
    S3Client s3Client(
            SdkHttpClient sharedAwsHttpClient,
            @Value("${app.aws.region}") String region) {
        return S3Client.builder()
            .region(Region.of(region))
            .httpClient(sharedAwsHttpClient)
            .build();
    }

    @Bean(destroyMethod = "close")
    SqsClient sqsClient(
            SdkHttpClient sharedAwsHttpClient,
            @Value("${app.aws.region}") String region) {
        return SqsClient.builder()
            .region(Region.of(region))
            .httpClient(sharedAwsHttpClient)
            .build();
    }
}
~~~

Đây là cấu hình **thay thế** cấu hình ở phần 6, không dùng đồng thời hai lớp tạo **S3Client**. Cần dependency AWS SDK **s3**, **sqs**, **apache-client** và phiên bản SDK đồng bộ; **spring-cloud-aws-starter-s3** hoặc **-sqs** có thể kéo theo các dependency liên quan nhưng phải kiểm tra build thực tế. Cả S3Client và SqsClient nhận cùng **SdkHttpClient instance**. Khi truyền **httpClient(instance)**, **AWS SDK không chịu trách nhiệm đóng instance do caller quản lý**. Vì thế Spring được khai báo đóng ba bean; khi context hủy, các client phụ thuộc phải ngừng trước khi bean transport được đóng.

<u>Quy tắc ownership:</u> **Bên tạo và sở hữu tài nguyên đóng nó, sau khi tất cả người dùng tài nguyên đó đã dừng.** Spring thường theo dõi dependency giữa các bean, vì vậy inject transport vào bean client giúp thiết lập quan hệ hủy theo thứ tự phù hợp. Nếu tự dùng static singleton hoặc truyền transport từ bên ngoài context, cần có owner rõ ràng; không đóng từ một adapter riêng vì các adapter khác còn sử dụng.

| Cách truyền HTTP client trong AWS SDK v2 | Owner thông thường | Hành động đóng |
| --- | --- | --- |
| Không cấu hình HTTP client thủ công | SDK client | Đóng SDK client; SDK quản lý transport nội bộ |
| **httpClientBuilder(builder)** | SDK client | Đóng SDK client để SDK đóng transport được tạo |
| **httpClient(instance)** | Caller / Spring bean tạo transport | Đóng các SDK client, sau đó đóng instance transport do caller sở hữu |

Nếu một shared transport bị đóng trước S3Client, mọi request còn chờ I/O có thể lỗi. Nếu không bao giờ đóng shared transport, connection và executor có thể tồn tại sau khi application context đã kết thúc.

## 8. Client bất đồng bộ: quản lý cả Netty, task và completion

Các client bất đồng bộ như **S3AsyncClient** không giữ thread gọi trong lúc đợi response theo cách thông thường của sync SDK, nhưng vẫn có tài nguyên thật: event loop, connection, executor, buffer, queue chờ và callback. Chúng cần được tái sử dụng và đóng đúng owner như client sync.

~~~java
// Một cấu hình độc lập dành cho async S3.
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import software.amazon.awssdk.http.nio.netty.NettyNioAsyncHttpClient;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3AsyncClient;

@Configuration(proxyBeanMethods = false)
public class AsyncAwsClientConfiguration {

    @Bean(destroyMethod = "close")
    S3AsyncClient s3AsyncClient(
            @Value("${app.aws.region}") String region) {
        return S3AsyncClient.builder()
            .region(Region.of(region))
            .httpClientBuilder(
                NettyNioAsyncHttpClient.builder().maxConcurrency(64))
            .build();
    }
}
~~~

Mẫu này cần module **software.amazon.awssdk:netty-nio-client** ở đúng phiên bản SDK. Vì truyền **builder**, SDK client sở hữu transport và giải phóng khi **S3AsyncClient.close()**. Cần phân biệt **maxConcurrency** của Netty async transport với **maxConnections** của Apache sync transport; không copy một giá trị mặc định cho mọi workload. Nếu tự tạo **SdkAsyncHttpClient instance** rồi truyền bằng **httpClient(instance)**, caller lại chịu trách nhiệm đóng transport đó.

**Đóng async client không phải bằng chứng mọi future đã hoàn tất.** Một request async có thể đã gửi lên cloud nhưng chưa nhận response; nếu tắt ứng dụng, future có thể complete exceptionally, bị cancel hoặc mất người tiêu thụ kết quả. Trước lúc đóng client, cần dừng nhận việc mới và chờ những thao tác quan trọng theo deadline, ghi lại operation ID để có thể retry/reconcile an toàn sau restart.

Ví dụ quy trình logic:

~~~text
Shutdown signal
  -> Ngừng tạo/upload công việc mới
  -> Theo dõi và chờ future quan trọng (có timeout tổng)
  -> Đánh dấu việc chưa hoàn tất để phục hồi sau restart
  -> Đóng S3AsyncClient
  -> SDK giải phóng Netty transport mà nó sở hữu
~~~

Không gọi **join()** chỉ để “chờ tất cả” vô hạn trong shutdown hook. Điều kiện phải có timeout và quy tắc xử lý phần chưa hoàn tất. Với Reactor, **cancel subscription** cũng không bảo đảm yêu cầu đã gửi được rollback ở cloud; do đó idempotency vẫn cần được thiết kế ở mức nghiệp vụ.

## 9. Azure và Google Cloud: không áp quy tắc close() của AWS cho mọi client

Các thư viện do provider phát hành **không thống nhất** về interface đóng tài nguyên và cấp độ sở hữu transport.

| Chủ đề | AWS SDK for Java v2 | Azure SDK for Java | Google Cloud Java libraries |
| --- | --- | --- | --- |
| Client storage điển hình | **S3Client / S3AsyncClient** | **BlobServiceClient / BlobServiceAsyncClient** | **Storage** của Cloud Storage |
| Cách tái sử dụng | SDK service clients được thiết kế dùng chung giữa request | Azure SDK clients nói chung được thiết kế dùng chung | Kiểm tra API và thread-safety của đúng client/version |
| Giao diện đóng | Nhiều SDK clients có **close()** | Không mặc định mọi Blob client có **close()** | Tùy library; storage, gRPC/GAX client và transport có API khác nhau |
| Thành phần có thể cần shutdown | Apache/Netty HTTP transport, client async | HTTP transport, reactor resources, credential resources nếu sở hữu riêng | gRPC channel, background executor, stream/reader/writer, client được tạo |
| Khi dùng Spring Cloud | Spring Cloud AWS auto-config có thể tạo client/template/listener | Spring Cloud Azure có thể tạo bean client và credential | Spring Cloud GCP có thể tạo bean client/template/subscriber |

**Azure Blob Storage:** thường inject client từ starter hoặc cấu hình Spring của ứng dụng rồi tái sử dụng cho nhiều thao tác. Không viết **BlobServiceClient.close()** nếu đúng class/version không cung cấp method này. Nếu ứng dụng tự quản lý HTTP client/transport hoặc Reactor resources riêng, cần đóng **chúng** theo hợp đồng thư viện. Điều tương tự áp dụng cho credential provider có thể quản lý kết nối/token cache; không suy diễn rằng mỗi TokenCredential đều là AutoCloseable.

**Google Cloud:** một số client lưu trữ dùng HTTP/REST, trong khi các thư viện dựa trên gRPC/GAX có các client và background resources với phương thức **close/shutdown** tương ứng. Ví dụ một client **SecretManagerServiceClient** tạo bằng Google Cloud Java library có vòng đời và API đóng khác với **Storage**. Khi tự tạo channel/provider/executor rồi đưa vào builder, phải xác định ai sở hữu những thành phần đó. Không được gọi chung một phương thức **close** cho mọi SDK client chỉ vì các class đều có tên hậu tố Client.

**Lời khuyên nhất quán:** nếu starter tạo bean, xác định nó đã quản lý resource nào; nếu ứng dụng tạo client hoặc transport riêng, công bố owner và callback dọn dẹp đúng API. Thử shutdown trong test environment để xác minh process không còn thread/connection do ứng dụng sở hữu. Thư viện nào không cung cấp close trên client thì không thêm phương thức giả; kiểm tra transport hoặc background resource thực sự cần giải phóng.

## 10. Tài nguyên phát sinh theo từng request vẫn phải đóng sớm

Tái sử dụng **SDK client** không có nghĩa giữ mãi **response stream**. Khi tải object từ S3 theo streaming, SDK trả một stream có thể giữ kết nối mạng tới khi đọc xong hoặc được đóng. Phải đóng stream sau mỗi thao tác:

~~~java
import java.io.IOException;
import java.io.OutputStream;
import software.amazon.awssdk.core.ResponseInputStream;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.GetObjectRequest;
import software.amazon.awssdk.services.s3.model.GetObjectResponse;

public void copyObjectTo(
        S3Client s3, String bucket, String key, OutputStream output)
        throws IOException {
    GetObjectRequest request = GetObjectRequest.builder()
        .bucket(bucket)
        .key(key)
        .build();

    try (ResponseInputStream<GetObjectResponse> input =
            s3.getObject(request)) {
        input.transferTo(output);
    }
}
~~~

Ở ví dụ này **input** do method mở nên được đóng bằng **try-with-resources**. **output** được caller đưa vào nên method không tự đóng nếu hợp đồng không trao quyền sở hữu. **S3Client** tiếp tục sống để phục vụ request khác. Đóng response stream quá muộn có thể làm connection pool cạn dù client bean được quản lý đúng.

Các trường hợp tương tự:

- Azure Blob có API mở input stream; stream đó phải được đọc/đóng theo hướng dẫn của Azure SDK.
- Google Cloud Storage có thể dùng **ReadChannel/WriteChannel** hoặc stream tùy client API; channel và stream có vòng đời riêng.
- JDBC connection, result set và statement phải được đóng/trả về pool đúng lúc; dùng Spring Data/JdbcTemplate giúp quản lý nhiều trường hợp nhưng không cho phép giữ một borrowed connection suốt vòng đời application.
- Multipart/resumable upload và publisher/subscriber streaming cần xử lý hủy, buffer release, timeout và cleanup theo đúng SDK; không mặc định “client là singleton” giải quyết toàn bộ resource leak.

## 11. Messaging listener và subscriber phải dừng trước client

Với **Amazon SQS**, **Azure Service Bus** hoặc **Google Pub/Sub**, một listener/subscriber thường duy trì polling, subscription, connection, thread hoặc background executor. Vì vậy vòng đời không kết thúc chỉ bằng việc đóng một SDK client:

~~~mermaid
sequenceDiagram
    participant O as Orchestrator / Spring
    participant L as Listener / subscriber
    participant H as Business handler
    participant C as Messaging client
    participant Q as Cloud queue / topic
    O->>L: Ngừng nhận công việc mới
    L-->>O: Không poll/receive thêm
    L->>H: Chờ handler đang chạy (có giới hạn)
    H-->>L: Thành công hoặc cần retry
    L->>Q: Ack/delete/complete phù hợp
    O->>L: Stop/close container
    O->>C: Close/shutdown client và transport sở hữu
~~~

Các bước biểu diễn **thứ tự mong muốn**, không có một API stop/ack thống nhất cho mọi provider. Spring Cloud AWS listener, Service Bus processor và Pub/Sub subscriber có lifecycle, auto-ack, manual-ack, lock hoặc visibility timeout khác nhau. Phải kiểm tra framework có thực sự chờ completion của handler **async** trước khi ack hay không.

Trong shutdown, một message đã được nhận nhưng chưa ack có thể được giao lại khi visibility/lock/ack deadline hết hạn. Đây là tình huống bình thường với nhiều cơ chế at-least-once. Handler cần **idempotency** theo message/event ID, không chỉ cố kéo dài shutdown vô hạn. Nếu có thao tác ghi database và phát message, **transactional outbox** là một cách giảm rủi ro giữa hai hệ thống.

## 12. Database pool, secret client và credential lifecycle

Không phải “cloud client” nào cũng là một HTTP client thuần túy:

**Managed relational database:** Spring Boot thường tạo **DataSource** dùng connection pool, ví dụ HikariCP, và Spring Data JPA/JDBC sử dụng pool đó. Pool nên sống cùng application context, còn connection mượn từ pool chỉ sống trong phạm vi giao dịch/thao tác. **HikariDataSource.close()** khi dừng ứng dụng đóng pool; **connection.close()** của connection được mượn thường trả nó về pool theo wrapper, không có nghĩa đóng cả DataSource. Không tạo một Hikari pool mới cho mỗi repository hoặc request.

**Secret manager:** AWS **SecretsManagerClient** có close theo AWS SDK v2. Azure Key Vault **SecretClient** có vòng đời dựa trên Azure SDK và HTTP transport liên quan; không mặc định nó cần một lời gọi close trực tiếp. Google Cloud **SecretManagerServiceClient** và một số GAX/gRPC clients có khả năng close/shutdown, quản lý background resources. Chọn đúng cleanup API theo loại bean.

**Credential/token refresh:** service client có thể sử dụng credential provider tự tìm và làm mới danh tính. Chỉ vì token hết hạn không có nghĩa phải đóng và tạo lại cả SDK client. Trường hợp thay đổi **identity, tenant, endpoint, region hoặc cấu hình kết nối** thực sự có thể cần client mới; khi thay, phải quản lý khách hàng đang dùng client cũ và đóng nó sau khi hoàn tất. Không ghi access key, secret, token, SAS hoặc connection string vào log trong quá trình khởi tạo/đóng.

## 13. Chia sẻ một client hay tạo nhiều client?

**Một client dùng chung** thường là lựa chọn đầu tiên khi có cùng provider, region/endpoint, cấu hình transport và trust boundary. Nhưng không phải lúc nào cũng nên chỉ có đúng một client:

| Tình huống | Lựa chọn cân nhắc | Lý do |
| --- | --- | --- |
| Hàng nghìn request S3 trong cùng region, cùng identity | Một **S3Client** singleton với pool được cấu hình hợp lý | Tái sử dụng connection và tránh lặp khởi tạo |
| Ứng dụng đồng thời truy cập hai AWS region hoặc account | Hai client được đặt tên và **@Qualifier** rõ ràng | Region/credential có thể khác nhau; đừng ngầm chọn bean |
| Nhiều tenant có identity khác nhau | Client theo identity/trust boundary, router/cache có giới hạn | Tránh quyền tenant này được dùng cho tenant khác |
| Nhiều SDK clients cùng dùng Apache HTTP transport | Shared **SdkHttpClient** bean nếu có lợi và được hỗ trợ | Chia pool nhưng phải đóng theo owner và tránh tranh chấp capacity |
| Job CLI chạy một lần, không có Spring context dài hạn | Tạo SDK client cho scope công việc và dùng try-with-resources | Vòng đời ngắn, owner rõ ràng |
| SDK async đang phục vụ task chạy dài | Một async client được quản lý, có cơ chế drain | Tránh đóng khi future hoặc upload chưa hoàn tất |

Với **multi-tenant**, nguy cơ lớn nhất không phải số lượng bean mà là **nhầm danh tính và dữ liệu**. Nếu client được cache theo tenant, cache phải có kích thước/TTL/eviction phù hợp; chỉ đóng một entry khi chắc chắn không còn thao tác đang dùng. Không cấp tự động credential từ tenant ID do caller tự khai báo mà không xác minh authorization. Một connection pool chia sẻ giữa nhiều loại workload cũng có thể gây **noisy neighbor**; đo throughput và latency trước khi tối ưu.

## 14. Từ Spring shutdown đến SIGTERM và Kubernetes

Spring Boot cung cấp lifecycle cho bean và, với web server hỗ trợ, **graceful shutdown** của HTTP. Có thể cấu hình:

~~~yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 30s
~~~

**server.shutdown=graceful** đề nghị web server ngừng nhận request mới và cho request đang xử lý hoàn tất trong giới hạn cấu hình. **spring.lifecycle.timeout-per-shutdown-phase** giới hạn thời gian chờ theo phase của lifecycle; nó **không** tự quản lý tất cả future, message listener hoặc upload tự tạo trong ứng dụng.

Một kế hoạch shutdown thực tế nên:

1. Chuyển ứng dụng sang trạng thái không sẵn sàng nhận traffic mới (phối hợp readiness/ingress/load balancer).
2. Dừng scheduler và listener tạo công việc mới; ngừng poll hoặc subscribe thêm message.
3. Đợi các công việc đang chạy **có giới hạn thời gian**, hoàn thành hoặc ghi trạng thái để phục hồi.
4. Xử lý ack/nack, checkpoint, outbox hoặc trạng thái công việc theo cơ chế provider.
5. Đóng listener/client và các transport, pool, executor do ứng dụng sở hữu theo thứ tự phụ thuộc.
6. Kết thúc process khi đã dọn dẹp hoặc hết deadline đã định; không để shutdown hook chờ vô hạn.

Trên **Kubernetes**, cần cân đối **terminationGracePeriodSeconds**, thời gian ngừng nhận traffic, thời gian drain và deadline đóng bean. Nếu orchestrator gửi **SIGKILL** trước khi ứng dụng hoàn thành, tài nguyên bị dừng cưỡng bức và message/operation chưa hoàn tất có thể cần khôi phục. Graceful shutdown không thay thế **idempotency, durable checkpoint hoặc outbox**.

Với Spring beans có lifecycle đặc biệt, có thể dùng **SmartLifecycle**, **@PreDestroy** hoặc callback của starter theo đúng contract để dừng listener và worker. Tránh tự viết **@PreDestroy** gọi **client.close()** nếu bean client đã được cấu hình **@Bean(destroyMethod="close")** và có owner riêng; hai nơi cùng cố đóng cùng một tài nguyên làm ownership khó kiểm soát.

## 15. Vấn đề hiệu năng và dấu hiệu rò rỉ tài nguyên

Việc tái sử dụng client giảm overhead, nhưng hiệu năng vẫn phụ thuộc pool và tải:

- **HTTP sync:** số thread đang chờ, acquired/available connections, connection acquisition wait, timeout, socket/TLS.
- **HTTP async:** event-loop saturation, số request đồng thời, pending acquire, inflight futures, queued callbacks, heap/direct memory.
- **gRPC/GAX:** channel state, in-flight RPC, executor threads, shutdown timeout và trạng thái background resource.
- **Database:** active/idle/pending connections, thời gian lấy connection, slow query và transaction giữ connection quá lâu.
- **Messaging:** active consumer, outstanding messages, ack/lock deadline, redelivery, dead-letter và backlog.

Tín hiệu vận hành thường gặp:

| Triệu chứng | Nghi ngờ đầu tiên | Kiểm tra |
| --- | --- | --- |
| Số thread/socket tăng theo số request rồi không giảm | Tạo SDK/HTTP client mỗi request hoặc không đóng stream | Bean scope, nơi gọi builder, thread dump, response stream |
| Timeout lấy connection dù cloud không lỗi | Pool quá nhỏ, stream không đóng hoặc concurrency vượt giới hạn | Acquired/pending pool metrics, thời gian giữ connection |
| Lỗi sau lúc một tác vụ kết thúc | Một nhánh đã gọi **close()** trên client dùng chung | Owner, bean destroy, lifecycle của task |
| Thread còn sống sau khi Spring context đã đóng | Shared transport/executor/gRPC resource chưa được đóng | Bean destroy callback, ai tạo resource, shutdown report |
| Pod dừng giữa chừng làm message được xử lý lại | Shutdown drain/ack chưa xong trước SIGKILL | Termination grace, handler idempotency, consumer stop order |
| Mỗi request tạo credential mới và chậm bất thường | Khởi tạo client/provider thường xuyên | Cấu hình bean singleton, credential cache/refresh |
| 403 chỉ xảy ra ở một tenant hoặc region | Client/cache bị route sang identity/resource không đúng | Principal, tenant binding, region, endpoint, resource scope |

Không giải quyết mọi vấn đề bằng cách tăng pool size hoặc timeout. Nếu stream không được đóng, tăng pool chỉ trì hoãn sự cố. Nếu quota cloud giới hạn concurrency, tăng client/pool có thể làm throttling nặng hơn. Nếu lỗi là IAM/RBAC, tái tạo client liên tục cũng không cấp thêm quyền.

## 16. Kiểm thử vòng đời và ownership

### 16.1. Kiểm thử Spring đóng tài nguyên đúng lúc

Có thể kiểm tra lifecycle của một bean tự tạo bằng một tài nguyên giả, không cần kết nối AWS/Azure/GCP:

~~~java
// SpringClientLifecycleTest.java
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.concurrent.atomic.AtomicBoolean;
import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

class SpringClientLifecycleTest {

    static class TrackedResource implements AutoCloseable {
        private final AtomicBoolean closed = new AtomicBoolean();

        boolean isClosed() {
            return closed.get();
        }

        @Override
        public void close() {
            closed.set(true);
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class ResourceConfig {
        @Bean(destroyMethod = "close")
        TrackedResource trackedResource() {
            return new TrackedResource();
        }
    }

    @Test
    void closesOwnedResourceWhenContextStops() {
        TrackedResource resource;
        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(ResourceConfig.class)) {
            resource = context.getBean(TrackedResource.class);
            assertFalse(resource.isClosed());
            assertTrue(resource == context.getBean(TrackedResource.class));
        }

        assertTrue(resource.isClosed());
    }
}
~~~

Test chứng minh Spring gọi callback của bean sở hữu khi context được đóng và cùng context trả một singleton instance. Nó **không chứng minh một SDK thực tế quản lý mọi HTTP transport đúng cách**; phần đó cần test với bean/configuration và SDK tương ứng. Với multi-client transport, có thể dùng fake/tracked close callbacks để xác minh client dừng trước transport, đồng thời kiểm thử close không xảy ra giữa hai tác vụ đang dùng resource.

### 16.2. Kiểm thử adapter và integration

| Mức | Kiểm tra | Không nên suy ra |
| --- | --- | --- |
| Unit test application service | Nhiều use case dùng port/client bean đã inject, không tự tạo SDK | SDK thật đã kết nối cloud |
| Context test | Đúng số bean, singleton scope, qualifier, destroy method | IAM/RBAC đã đúng |
| SDK/adapter test | Request mapping, stream được đóng, xử lý lỗi/timeout | Emulator phản ánh đầy đủ cloud |
| Integration test | Kết nối tới LocalStack/Azurite/test project, quản lý body/response | IAM và network sản xuất giống hệt |
| Cloud smoke + shutdown test | Identity thật, quyền tối thiểu, stop listener, close pool/transport, recovery sau restart | Không bao giờ có message giao lại hoặc request trùng |

Với cloud thật, dùng bucket/container/topic test riêng, không dùng secret sản xuất, không mở log chứa credential. Đối với cleanup, kiểm tra rằng SDK client chỉ bị đóng khi Spring context kết thúc, response streams được đóng sau từng thao tác và listener không xử lý thêm message sau khi báo stop hoàn tất. Với async SDK, test cả trường hợp in-flight future ở thời điểm shutdown.

## 17. Bài tập thực hành

**Bài tập 1 — Tìm lỗi vòng đời.** Một REST controller tạo **S3Client.builder().build()** trong mỗi request và không đóng. Mô tả chi phí connection/credential của cách làm này. Chuyển sang Spring bean singleton được inject, ghi rõ nơi đóng client và cách quan sát pool.

**Bài tập 2 — Ai đóng shared transport?** Ứng dụng tạo một **SdkHttpClient** dùng chung cho S3Client và SqsClient qua **httpClient(instance)**. Khi dừng, S3 adapter gọi **sharedHttpClient.close()** trước khi SQS worker kết thúc. Tìm lỗi ownership và đề xuất bean graph cùng thứ tự shutdown an toàn.

**Bài tập 3 — Stream không đóng.** Một service dùng **s3.getObject** lấy **ResponseInputStream**, trả một phần byte rồi bỏ stream. Giải thích vì sao vài chục request sau có thể timeout lấy connection, dù SDK client là singleton. Viết lại bằng try-with-resources và nêu owner của output stream.

**Bài tập 4 — Async shutdown.** WebFlux service dùng **S3AsyncClient**; pod nhận SIGTERM khi còn 50 futures đang chạy. Thiết kế trình tự ngừng nhận request, đặt deadline, lưu operation ID còn dang dở, đóng client và phục hồi sau restart. Giải thích vì sao cancel một future không bảo đảm S3 đã rollback.

**Bài tập 5 — So sánh provider.** Với một ứng dụng lưu object trên AWS, Azure và GCP, lập bảng client nào có **close** trực tiếp, transport nào có owner riêng và resource từng request nào phải đóng. Chỉ sử dụng kết luận từ API/tài liệu **đúng version**; không suy diễn rằng BlobServiceClient hay Storage đều có phương thức close giống S3Client.

**Bài tập 6 — Multi-tenant và identity.** Hai tenant sử dụng credential và bucket khác nhau. Một singleton **S3Client** đang gắn với role của tenant A nhưng router dùng lại cho tenant B. Nêu rủi ro bảo mật và đề xuất cách chọn client, cách cache có giới hạn, đóng entry bị evict và kiểm thử cách ly quyền.

**Bài tập 7 — Listener và transaction.** Consumer Pub/Sub hoặc SQS đang xử lý message khi shutdown. Tại sao cần dừng nhận mới, chờ/ghi trạng thái handler và quản lý ack trước khi đóng SDK? Thiết kế idempotency để nhận lại message không tạo thêm business side effect.

## 18. Ghi nhớ

- **SDK client thường có vòng đời dài và được tái sử dụng; request builder, response stream và connection mượn từ pool có vòng đời ngắn hơn.** Thread-safe không có nghĩa mọi đối tượng và mọi lượng tải đều có thể chia sẻ vô hạn.
- **Spring bean có owner rõ ràng.** Với AWS SDK v2, đóng S3Client do Spring sở hữu bằng destroy callback khi context kết thúc; không tự đóng singleton ở cuối mỗi request.
- **Với HTTP client builder**, SDK thường sở hữu transport tạo ra; **với HTTP client instance truyền sẵn**, caller sở hữu và phải đóng khi không còn SDK client nào dùng. Cần kiểm tra hợp đồng đúng SDK và phiên bản.
- **Azure và Google Cloud có API lifecycle khác AWS.** Không mặc định mọi client đều cung cấp close(); hãy xác định đúng HTTP/gRPC transport, executor, stream và resource mà ứng dụng tự tạo.
- **Graceful shutdown là quy trình dừng nhận việc, drain, ack/checkpoint rồi đóng client và pool theo thứ tự.** SIGTERM, timeout hoặc cancellation không có nghĩa cloud đã hoàn tác thao tác đang chạy.
- Kiểm thử cả **tạo bean, chia sẻ instance, thứ tự đóng, stream cleanup, in-flight operations và phục hồi sau restart**; luôn bảo vệ credential và giới hạn IAM/RBAC khi chia sẻ client.
