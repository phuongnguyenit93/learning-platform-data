# Thiết kế vòng đời SDK client và tái sử dụng kết nối

Một dịch vụ Java trên Amazon ECS có thể gọi Amazon S3 để tải tài liệu, DynamoDB để đọc trạng thái và Amazon SQS để gửi công việc. Nếu ứng dụng tạo mới một AWS SDK client cho mỗi HTTP request, hệ thống liên tục khởi tạo HTTP transport, DNS/TLS connections, connection pools và các background resources. Hậu quả có thể là **latency cao, connection churn, cạn socket/file descriptors, tăng CPU và khó kiểm soát shutdown**.

AWS SDK for Java 2.x được thiết kế để **tạo service client một lần cho mỗi cấu hình cần thiết, tái sử dụng client qua nhiều request và đóng client khi ứng dụng kết thúc**. Service clients an toàn khi dùng đồng thời từ nhiều threads; mỗi client giữ cấu hình Region, credentials provider, endpoint, retry và HTTP transport của nó. Tái sử dụng đúng vòng đời giúp tận dụng connection pooling, credential refresh và các tối ưu nội bộ của SDK.

Bài học thuộc chương **AWS SDK cho Java** của mô-đun **CLOUD_PROVIDERS_AWS**. Nội dung gắn cách viết ứng dụng Java với IAM, Region/AZ, VPC, compute, storage, database, integration và serverless, tập trung vào tính sẵn sàng, khả năng quan sát, phục hồi và chi phí vận hành.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích vòng đời của **AWS SDK for Java 2.x service client**, HTTP client và credentials provider.
2. Phân biệt **thread-safe service client**, builder và request/response objects.
3. Thiết kế client dùng lại theo application lifecycle trong Java SE, Spring Boot, ECS, EKS, EC2 và Lambda.
4. Chọn HTTP transport đồng bộ **Apache HTTP client** hoặc bất đồng bộ **Netty NIO**, hiểu quyền sở hữu và đóng tài nguyên.
5. Tái sử dụng HTTP connection pools, cấu hình max connections/concurrency, acquisition timeout và idle/TTL.
6. Phân biệt **API call timeout**, **attempt timeout**, **connection timeout**, **socket/read timeout** và retry.
7. Dùng Region/credentials provider chain đúng cách, tránh static credentials và client per request.
8. Phân biệt pool kết nối AWS APIs với **JDBC connection pool** tới RDS/Aurora.
9. Quản lý response streams, futures, shutdown và lỗi để không giữ kết nối quá lâu.
10. Kiểm thử, giám sát, xử lý connection leaks/throttling và tối ưu tổng chi phí.

## 2. Kiến trúc một AWS SDK client

Một service client như **S3Client**, **DynamoDbClient** hay **SqsClient** không chỉ là một object chứa endpoint. Nó điều phối các thành phần:

~~~mermaid
flowchart TD
    APP["Java application / request handlers"] --> CLIENT["AWS SDK service client<br/>S3Client / DynamoDbClient"]
    CLIENT --> CONFIG["Region + endpoint + retry<br/>API call timeouts"]
    CLIENT --> CRED["Credentials provider<br/>IAM role / profile / web identity"]
    CLIENT --> SIGN["AWS SigV4 signer"]
    CLIENT --> HTTP["HTTP transport + connection pool"]
    HTTP --> DNS["DNS / TCP / TLS"]
    DNS --> AWS["AWS service endpoint"]
    AWS --> RESP["HTTP response"]
    RESP --> CLIENT
    CLIENT --> APP
~~~

| Thành phần | Trách nhiệm | Vòng đời |
|---|---|---|
| **Service client** | Gọi API của một AWS service, ký request, parse response | Thường sống cùng application/container/runtime |
| **HTTP client/transport** | Quản lý sockets, TLS, connection pool, async event loops | Sống ít nhất bằng các service clients đang dùng nó |
| **Credentials provider** | Cung cấp và có thể refresh AWS credentials | Theo cấu hình provider và owner quản lý |
| **Region/endpoint configuration** | Chọn AWS Region và đích request | Cố định theo client sau khi build |
| **Request/response model** | Đại diện tham số và dữ liệu một API call | Theo từng thao tác |
| **Response stream** | Đọc body từ response, ví dụ S3 object | Phải được consume/close đúng cách |

**Client là lớp điều phối API.** Một S3Client không giữ kết nối tới đúng một bucket hay một object; nó dùng HTTP transport để gửi nhiều requests tới endpoint tương ứng. Connection pool có thể tái sử dụng kết nối TCP/TLS khi service, endpoint và transport cho phép.

### 2.1. Service client thread-safe và immutable sau khi build

Các service clients trong AWS SDK for Java 2.x được thiết kế **thread-safe**. Sau khi build, cấu hình client không thay đổi; nhiều request threads có thể gọi cùng một client. Điều này phù hợp với server Java có nhiều HTTP requests đồng thời.

- Tạo client khi khởi động application hoặc khi khởi tạo runtime/container.
- Dùng lại cùng instance cho các request phù hợp với cùng Region, credentials và endpoint configuration.
- Không tạo client mới trong controller, repository method hoặc mỗi lần gọi một AWS API.
- Không chia sẻ builder để nhiều threads cùng sửa cấu hình rồi build tùy tiện.
- Không đóng client sau từng request; đóng khi application owner kết thúc.

**Thread-safe không có nghĩa mọi thứ xung quanh đều thread-safe.** Một cache tự viết, mutable request payload, stream, database connection hoặc object state trong callback vẫn phải tuân theo quy tắc concurrency của chính nó.

### 2.2. Một client cho mọi trường hợp hay nhiều client?

Một service client thường được tái sử dụng cho **một cấu hình ổn định**. Tạo client riêng khi có lý do thực tế:

- **Region khác nhau:** client được cấu hình theo Region; có thể cần một client mỗi Region.
- **AWS accounts/roles khác nhau:** mỗi credentials provider/assumed role cần cấu hình rõ.
- **Endpoint khác nhau:** ví dụ AWS endpoint và LocalStack test endpoint.
- **Traffic isolation:** một service workload nặng không nên làm cạn pool dùng chung của critical API khác.
- **HTTP/TLS/timeout policy khác nhau:** có thể cần transport riêng theo latency/SLO.

Không tạo client theo từng user hoặc từng request nếu chỉ khác object key/table name. Những giá trị đó là **request parameters**, không phải client configuration.

## 3. Vòng đời client theo application lifecycle

~~~mermaid
flowchart TD
    START["Application startup"] --> CRED["Khởi tạo credentials/Region config"]
    CRED --> HTTP["Tạo HTTP transport nếu cần"]
    HTTP --> CLIENTS["Build service clients"]
    CLIENTS --> READY["Application ready"]
    READY --> REQUESTS["Nhiều requests dùng lại client"]
    REQUESTS --> READY
    READY --> STOP["Graceful shutdown"]
    STOP --> DRAIN["Ngừng nhận việc mới<br/>chờ requests/streams đang chạy"]
    DRAIN --> CLOSE["Đóng service clients"]
    CLOSE --> TRANSPORT["Đóng shared HTTP transport<br/>và owned resources"]
~~~

Vòng đời điển hình:

1. **Startup:** nạp cấu hình Region, endpoint, credentials provider và HTTP transport.
2. **Build:** tạo service clients sau khi cấu hình hoàn chỉnh.
3. **Operate:** chia sẻ client giữa request handlers, workers và scheduled jobs.
4. **Drain:** khi shutdown, ngừng nhận request mới và đợi các operations đang chạy trong giới hạn thời gian.
5. **Close:** đóng service clients, shared HTTP clients và các providers/STS clients do ứng dụng sở hữu theo đúng thứ tự.

### 3.1. Java SE: try-with-resources cho ứng dụng ngắn hạn

Với một command-line job hoặc batch process, client có thể sống trong phạm vi main:

~~~java
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.ListBucketsResponse;

public final class ListBucketsJob {
    public static void main(String[] args) {
        Region region = Region.AP_SOUTHEAST_1;

        try (S3Client s3 = S3Client.builder()
                .region(region)
                .build()) {

            ListBucketsResponse response = s3.listBuckets();
            response.buckets().forEach(
                bucket -> System.out.println(bucket.name())
            );
        }
    }
}
~~~

try-with-resources đóng client khi job kết thúc, kể cả khi có exception. Đây là pattern phù hợp cho **một lần chạy batch**; không đặt block này bên trong method được gọi cho từng HTTP request của server lâu dài.

### 3.2. Spring Boot: quản lý bằng dependency injection

Trong Spring Boot, tạo client thành **singleton bean** để container quản lý:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.dynamodb.DynamoDbClient;

@Configuration
public class AwsClientsConfiguration {

    @Bean(destroyMethod = "close")
    public S3Client s3Client() {
        return S3Client.builder()
            .region(Region.AP_SOUTHEAST_1)
            .build();
    }

    @Bean(destroyMethod = "close")
    public DynamoDbClient dynamoDbClient() {
        return DynamoDbClient.builder()
            .region(Region.AP_SOUTHEAST_1)
            .build();
    }
}
~~~

Spring singleton bean được chia sẻ giữa các components. Khi application context shutdown, destroyMethod = "close" gọi close() trên client. Nếu cấu hình Region/endpoint/credentials khác nhau theo profile, nên externalize chúng bằng application properties/environment và validate khi startup.

### 3.3. AWS Lambda: khởi tạo ngoài handler

Lambda có thể tái sử dụng execution environment giữa nhiều invocations. Đặt service client trong **static field** hoặc object được khởi tạo ngoài handler:

~~~java
import com.amazonaws.services.lambda.runtime.Context;
import com.amazonaws.services.lambda.runtime.RequestHandler;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.HeadObjectRequest;

public class ObjectMetadataHandler
        implements RequestHandler<ObjectRequest, ObjectMetadataResult> {

    private static final S3Client S3 = S3Client.builder()
        .region(Region.AP_SOUTHEAST_1)
        .build();

    @Override
    public ObjectMetadataResult handleRequest(
            ObjectRequest request, Context context) {

        var result = S3.headObject(HeadObjectRequest.builder()
            .bucket(request.bucket())
            .key(request.key())
            .build());

        return new ObjectMetadataResult(
            result.contentLength(),
            result.contentType()
        );
    }
}
~~~

Lambda execution role được SDK credentials provider chain sử dụng để lấy temporary credentials. **Không đóng S3Client sau mỗi invocation**, vì các invocation tiếp theo trong cùng execution environment có thể dùng lại client và pool. Không lưu dữ liệu request/user-specific vào static fields; client configuration có thể dùng chung nhưng request state phải tách biệt.

**ObjectRequest** và **ObjectMetadataResult** trong ví dụ là DTO của ứng dụng, không phải các lớp được AWS SDK cung cấp.

### 3.4. ECS, EKS và EC2

Với ứng dụng chạy dài hạn:

- **ECS/Fargate:** tạo client trong application startup; SDK lấy credentials từ task role provider. Không dùng task execution role thay cho application task role.
- **EKS:** dùng EKS Pod Identity hoặc IRSA để cấp credentials cho đúng Kubernetes service account; giữ client sống cùng Pod.
- **EC2:** dùng instance profile role; SDK default chain có thể lấy credentials qua instance metadata. Bật IMDSv2 và không hard-code keys.
- **Rolling deployment:** mỗi container mới tạo pool mới; sizing tổng số connections phải tính cả số replicas/Pods đang chạy đồng thời trong lúc rollout.

## 4. HTTP transport trong AWS SDK for Java 2.x

Service client gửi AWS API requests qua một **HTTP implementation**. AWS SDK for Java 2.x cung cấp các lựa chọn đồng bộ và bất đồng bộ; lựa chọn transport ảnh hưởng connection pooling, concurrency, memory, thread usage và timeout behavior.

| HTTP implementation | Loại | Thường dùng cho | Ghi chú |
|---|---|---|---|
| **Apache HTTP client** | Synchronous | S3Client, DynamoDbClient, SqsClient và các sync clients | Connection pool, max connections, socket/connection timeouts |
| **URLConnection HTTP client** | Synchronous | Ứng dụng cần transport đơn giản, dependency nhẹ | Không cung cấp connection pooling như Apache; cân nhắc kỹ với workload cần reuse/concurrency cao |
| **Netty NIO async HTTP client** | Asynchronous | S3AsyncClient, DynamoDbAsyncClient và async clients | Event loops, max concurrency, pending acquires, async read/write |

SDK có thể tự chọn HTTP implementation mặc định phù hợp theo service client và dependencies có trên classpath. Để kiểm soát production, nên **khai báo dependency và transport rõ ràng**, đọc đúng SDK version và kiểm tra startup logs/config thay vì phụ thuộc vào classpath tình cờ.

### 4.1. Apache HTTP client cho synchronous SDK clients

Thêm dependency Maven tương ứng với version AWS SDK đang dùng:

~~~xml
<dependency>
  <groupId>software.amazon.awssdk</groupId>
  <artifactId>apache-client</artifactId>
</dependency>
~~~

Ví dụ tạo một transport dùng chung cho S3 và DynamoDB:

~~~java
import java.time.Duration;
import software.amazon.awssdk.http.SdkHttpClient;
import software.amazon.awssdk.http.apache.ApacheHttpClient;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.dynamodb.DynamoDbClient;

public final class SharedSyncClients implements AutoCloseable {
    private final SdkHttpClient transport;
    private final S3Client s3;
    private final DynamoDbClient dynamoDb;

    public SharedSyncClients() {
        transport = ApacheHttpClient.builder()
            .maxConnections(100)
            .connectionTimeout(Duration.ofSeconds(2))
            .connectionAcquisitionTimeout(Duration.ofSeconds(3))
            .socketTimeout(Duration.ofSeconds(15))
            .connectionMaxIdleTime(Duration.ofSeconds(45))
            .build();

        s3 = S3Client.builder()
            .region(Region.AP_SOUTHEAST_1)
            .httpClient(transport)
            .build();

        dynamoDb = DynamoDbClient.builder()
            .region(Region.AP_SOUTHEAST_1)
            .httpClient(transport)
            .build();
    }

    public S3Client s3() {
        return s3;
    }

    public DynamoDbClient dynamoDb() {
        return dynamoDb;
    }

    @Override
    public void close() {
        // Đóng service clients trước, shared transport sau.
        dynamoDb.close();
        s3.close();
        transport.close();
    }
}
~~~

Trong ví dụ, **transport được tạo riêng và truyền qua httpClient(...)**; application sở hữu transport và phải đóng nó. Hai service clients chia sẻ cùng pool; số 100 là ví dụ, phải sizing theo concurrency và API latency thật.

### 4.2. Để service client tự quản lý HTTP client

Nếu chỉ có một service client và không cần share transport, dùng **httpClientBuilder(...)**:

~~~java
S3Client s3 = S3Client.builder()
    .region(Region.AP_SOUTHEAST_1)
    .httpClientBuilder(
        ApacheHttpClient.builder()
            .maxConnections(80)
            .connectionTimeout(Duration.ofSeconds(2))
            .socketTimeout(Duration.ofSeconds(15))
    )
    .build();
~~~

Trong cách này, service client sở hữu HTTP implementation được tạo từ builder và quản lý lifecycle của nó; đóng **S3Client** sẽ đóng resource nội bộ theo ownership của SDK. Đây là lựa chọn đơn giản khi không cần chia sẻ một HTTP pool giữa nhiều clients.

**Không truyền cùng một HTTP client instance cho nhiều owners rồi để từng owner tự đóng nó.** Phải quyết định rõ ai sở hữu transport. Nếu dùng builder do service client quản lý, SDK sở hữu transport đó; nếu truyền một instance qua **httpClient(...)**, ứng dụng phải quản lý shared transport.

### 4.3. Quy tắc đóng tài nguyên khi share HTTP client

| Cách cấu hình | Ai sở hữu HTTP transport? | Đóng thế nào? |
|---|---|---|
| **httpClientBuilder(builder)** | SDK service client tạo và quản lý transport | Đóng service client |
| **httpClient(existingInstance)** | Application cung cấp transport có sẵn | Đóng mọi service clients trước, rồi đóng transport |
| Nhiều clients share một instance | Application là owner chung | Đóng từng client khi dừng, đóng transport đúng một lần |

Trong Spring, có thể khai báo transport là bean riêng và truyền nó vào các service client beans; Spring quản lý dependency graph và destruction order. Trong plain Java, dùng một lifecycle owner duy nhất, không để nhiều classes cùng gọi close trên transport chung một cách tùy tiện.

## 5. Async clients và Netty event loops

Với workload nhiều I/O và muốn tránh chặn request threads khi chờ AWS, dùng async service client. **Netty NIO** dùng event loops để quản lý socket operations; application nhận **CompletableFuture** thay vì chờ API trả về đồng bộ.

### 5.1. Cấu hình Netty async transport

Maven dependency:

~~~xml
<dependency>
  <groupId>software.amazon.awssdk</groupId>
  <artifactId>netty-nio-client</artifactId>
</dependency>
~~~

Ví dụ tạo transport và S3AsyncClient:

~~~java
import java.time.Duration;
import software.amazon.awssdk.http.async.SdkAsyncHttpClient;
import software.amazon.awssdk.http.nio.netty.NettyNioAsyncHttpClient;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3AsyncClient;

SdkAsyncHttpClient asyncTransport = NettyNioAsyncHttpClient.builder()
    .maxConcurrency(200)
    .maxPendingConnectionAcquires(1000)
    .connectionTimeout(Duration.ofSeconds(2))
    .readTimeout(Duration.ofSeconds(30))
    .writeTimeout(Duration.ofSeconds(30))
    .build();

S3AsyncClient s3Async = S3AsyncClient.builder()
    .region(Region.AP_SOUTHEAST_1)
    .httpClient(asyncTransport)
    .build();
~~~

**maxConcurrency** giới hạn số HTTP requests đồng thời qua client; **maxPendingConnectionAcquires** giới hạn lượng requests chờ lấy connection theo cấu hình Netty. Hai tham số này không đồng nghĩa với số Java threads, Lambda concurrency hoặc số objects được tải. Giá trị cần được đo theo throughput, memory, downstream quotas và latency.

### 5.2. Gọi async API mà không block event loop

~~~java
import java.util.concurrent.CompletableFuture;
import software.amazon.awssdk.services.s3.model.HeadObjectRequest;

public CompletableFuture<Long> getObjectSize(
        S3AsyncClient client, String bucket, String key) {

    return client.headObject(HeadObjectRequest.builder()
            .bucket(bucket)
            .key(key)
            .build())
        .thenApply(response -> response.contentLength());
}
~~~

Đừng gọi **join()** hoặc **get()** bên trong Netty event loop/callback nếu không cần thiết; thao tác đó chặn thread đang xử lý I/O. Với Spring MVC hoặc framework blocking, async API chỉ có lợi khi toàn bộ pipeline được quản lý đúng; nếu ngay sau đó block để lấy kết quả, complexity tăng mà throughput có thể không cải thiện.

### 5.3. Async client cũng cần lifecycle rõ

Khi application dùng **httpClient(asyncTransport)** để share transport, application đóng các async service clients rồi đóng transport sau khi các operations đang chạy đã được drain. Không đóng Netty event loops ngay khi futures chưa hoàn thành. Nếu dùng **httpClientBuilder(...)**, SDK quản lý transport nội bộ theo lifecycle service client.

**Async không đồng nghĩa không giới hạn.** Nếu tạo hàng triệu futures cùng lúc, pending acquire queue và memory có thể tăng. Cần backpressure, bounded concurrency, batch/windowing và cancel operations phù hợp khi request hết deadline.

## 6. Tái sử dụng connection pool: vì sao tạo client mỗi request rất tốn?

Một HTTP request AWS thường cần resolve DNS, thiết lập TCP/TLS nếu chưa có connection sẵn, ký SigV4, gửi payload, nhận response và trả connection về pool. Với **persistent HTTP connections**, nhiều requests có thể dùng lại TCP/TLS connection đang mở thay vì handshake mới.

~~~mermaid
flowchart LR
    A["Request A"] --> POOL["HTTP connection pool"]
    B["Request B"] --> POOL
    C["Request C"] --> POOL
    POOL --> CONN1["Keep-alive connection 1"]
    POOL --> CONN2["Keep-alive connection 2"]
    CONN1 --> AWS["AWS endpoint"]
    CONN2 --> AWS
    AWS --> POOL
~~~

### 6.1. Hai cách triển khai

| Cách | Hành vi | Hệ quả |
|---|---|---|
| **Client per request** | Mỗi request tạo service client và thường tạo HTTP transport/pool mới | Connection churn, TLS handshakes, thread/resource overhead, khó close |
| **Application-scoped client** | Nhiều requests dùng cùng service client và pool | Tái sử dụng connections, giữ resource ổn định, dễ giám sát |

**Connection pooling chỉ phát huy tác dụng khi response được tiêu thụ hoặc đóng đúng cách.** Một response body/stream chưa đóng có thể giữ connection ở trạng thái bận, làm request khác phải đợi pool. Đây là nguyên nhân phổ biến khiến maxConnections nhỏ bị cạn dù traffic không cao.

### 6.2. Chia sẻ pool giữa service clients hay tách riêng?

Có thể share một **SdkHttpClient** giữa các synchronous service clients tương thích. Lợi ích là ít pools và ít threads/sockets hơn. Nhưng pool chung cũng tạo **resource contention**: một S3 download lớn có thể chiếm nhiều connections, khiến DynamoDB/SQS critical requests chờ.

Tách pools khi:

- Một service có payload lớn/streaming lâu, traffic cao hoặc latency khác biệt rõ.
- Một workload không quan trọng có thể làm cạn pool của API quan trọng.
- Các service cần HTTP/TLS/proxy/timeout settings khác nhau.
- Muốn cô lập blast radius khi transport gặp lỗi hoặc bị throttling.

Không share pool chỉ để giảm số dòng code. **Share khi workload tương đồng và có metrics chứng minh**, còn không thì mỗi service client có transport riêng cũng là thiết kế hợp lệ.

## 7. Sizing connection pool và tránh pool exhaustion

Pool phải đủ cho concurrency thực tế nhưng không nên lớn vô hạn. Với sync Apache transport, **maxConnections** giới hạn số connections mà pool có thể cấp. Với Netty async transport, **maxConcurrency** giới hạn số requests đồng thời; các requests vượt ngưỡng có thể phải chờ trong pending acquire queue hoặc bị lỗi khi chạm giới hạn/thời hạn chờ.

### 7.1. Những thông số cần hiểu

| Tham số | Ý nghĩa | Tăng quá cao/thấp gây gì? |
|---|---|---|
| **maxConnections** (Apache) | Số HTTP connections tối đa của pool | Quá thấp: chờ pool; quá cao: nhiều sockets/file descriptors và memory |
| **maxConcurrency** (Netty) | Số HTTP requests đang xử lý đồng thời | Quá thấp: giảm throughput; quá cao: gây áp lực downstream và memory |
| **maxPendingConnectionAcquires** (Netty) | Số yêu cầu được phép chờ lấy connection | Quá cao: queue chờ lớn; quá thấp: từ chối sớm khi burst |
| **connectionAcquisitionTimeout** | Thời gian chờ cấp connection từ pool | Quá ngắn: lỗi dưới burst; quá dài: request threads chờ lâu |
| **connectionTimeout** | Thời gian thiết lập connection TCP/TLS | Quá ngắn: lỗi trên network chậm; quá dài: startup/requests treo |
| **socketTimeout / readTimeout** | Thời gian chờ dữ liệu từ server theo transport | Quá ngắn: cắt response hợp lệ; quá dài: giữ tài nguyên khi server treo |
| **writeTimeout** (async) | Thời gian chờ ghi request data theo transport | Quá ngắn với upload chậm; quá dài khi client/network bị nghẽn |
| **connectionMaxIdleTime** | Tuổi idle tối đa trước khi connection bị loại theo cấu hình | Quá ngắn: tăng reconnect; quá dài: dễ gặp connection stale |
| **connectionTimeToLive** | Tuổi tối đa của một connection trước khi tái tạo | Quá ngắn: nhiều TLS handshakes; quá dài: giữ connection cũ lâu |

Tên method, defaults và tính khả dụng phụ thuộc **HTTP implementation và SDK version**. Đọc API docs đúng version của **ApacheHttpClient.Builder** hoặc **NettyNioAsyncHttpClient.Builder**; không copy cấu hình Netty sang Apache rồi giả định cùng semantics.

### 7.2. Ước lượng concurrency từ throughput

Một ước lượng ban đầu dựa trên Little's Law:

\[
L \approx \lambda \times W
\]

Trong đó:

- **L:** số requests đang in-flight trung bình.
- **λ:** throughput requests/giây.
- **W:** thời gian response trung bình tính bằng giây.

Ví dụ AWS API throughput **80 requests/giây**, thời gian trung bình **0,25 giây**:

\[
L \approx 80 \times 0,25 = 20
\]

Số 20 là ước lượng in-flight trung bình; pool thực tế cần headroom cho burst, p95/p99, retries và nhiều service clients. Không lấy đúng L làm maxConnections cuối cùng. Benchmark theo workload và đo **pending acquires, acquisition latency, in-flight requests, socket usage**.

### 7.3. Pool tổng khi scale nhiều containers

Nếu mỗi ECS task có Apache pool **100 connections** và autoscaling lên **20 tasks**, tổng tiềm năng là:

\[
20 \times 100 = 2.000\ \text{HTTP connections}
\]

Đây là số tối đa theo cấu hình, không phải số connections luôn mở. Tuy vậy, cần tính thêm rolling deployment, autoscaling overlap và các clients khác. AWS service có throttling/quota riêng; mở pool lớn không làm tăng quota dịch vụ.

### 7.4. Đừng giữ response stream quá lâu

Với S3, response body thường được đọc qua stream. Nếu ứng dụng giữ stream mở trong khi thực hiện công việc CPU/database kéo dài, connection HTTP có thể không được trả lại pool trong thời gian đó. Đọc/ghi theo chunks, đóng stream ngay khi xong và không giữ response stream trong object sống lâu.

## 8. Timeout, retry và deadline phải phối hợp

Một API call có thể thất bại ở nhiều lớp. Cần phân biệt:

| Timeout | Phạm vi |
|---|---|
| **connectionAcquisitionTimeout** | Chờ lấy một connection từ HTTP pool |
| **connectionTimeout** | Thiết lập TCP/TLS connection |
| **socketTimeout/readTimeout** | Chờ response data trên connection |
| **apiCallAttemptTimeout** | Giới hạn tổng thời gian của một attempt SDK |
| **apiCallTimeout** | Giới hạn tổng thời gian của cả API call, bao gồm retries |
| **Application/request deadline** | Thời hạn cuối mà HTTP request/job của ứng dụng phải hoàn tất |

### 8.1. Ví dụ cấu hình API call timeout

~~~java
import java.time.Duration;
import software.amazon.awssdk.core.client.config.ClientOverrideConfiguration;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.dynamodb.DynamoDbClient;

DynamoDbClient dynamoDb = DynamoDbClient.builder()
    .region(Region.AP_SOUTHEAST_1)
    .overrideConfiguration(ClientOverrideConfiguration.builder()
        .apiCallTimeout(Duration.ofSeconds(25))
        .apiCallAttemptTimeout(Duration.ofSeconds(8))
        .build())
    .build();
~~~

Trong ví dụ, **một attempt** bị giới hạn 8 giây và toàn bộ API call có tối đa 25 giây. Retry/backoff phải nằm trong tổng deadline; SDK không nên tiếp tục thử lại sau khi HTTP request bên ngoài đã hết hạn. Thực tế cần tính thêm thời gian queueing, serialization và response processing.

### 8.2. Retry không phải giải pháp cho mọi lỗi

AWS SDK retry strategy có thể thử lại một số lỗi transient/throttling theo retry mode, số attempts và backoff được cấu hình. Tuy nhiên:

- **AccessDenied, invalid parameters, validation errors** thường cần sửa cấu hình/quyền, không nên retry liên tục.
- **Throttling** có thể cần exponential backoff và jitter; tăng concurrency thường làm nặng thêm.
- **Network timeout** không chứng minh server chưa thực hiện request. Một write có thể đã thành công phía AWS nhưng response bị mất.
- **Non-idempotent operations** có thể tạo side effects trùng khi retry. Dùng idempotency token/client token hoặc application-level deduplication khi API/workflow hỗ trợ.
- **Retries consume time and requests**; đặt max attempts và API call timeout phù hợp với deadline của ứng dụng.

### 8.3. Cấu hình retry theo workload

| Workload | Hướng thiết kế |
|---|---|
| **Read-only GetItem/HeadObject** | Có thể retry lỗi transient; đặt deadline ngắn phù hợp SLO |
| **S3 multipart upload** | Dùng Transfer Manager/SDK retry và quản lý abort/cleanup khi fail |
| **Create resource** | Dùng client token/idempotency support nếu API cung cấp |
| **SendMessage/payment side effect** | Có deduplication/application idempotency; không giả định timeout nghĩa là request chưa chạy |
| **Batch job** | Deadline dài hơn nhưng bounded retry; lưu checkpoint và failed items |
| **Interactive HTTP request** | Không để retry/backoff kéo dài quá client deadline; trả lỗi có thể thử lại khi phù hợp |

Không cấu hình tất cả clients cùng một retry count lớn chỉ để “tăng reliability”. Một lỗi downstream có thể nhân lên thành **retry storm**. Giới hạn concurrency, backoff, jitter, circuit breaker ở application và alarm theo tỷ lệ retry.

## 9. Credentials provider và Region: cũng là một phần vòng đời

Service client cần **AWS credentials** để ký SigV4 và **Region** để chọn endpoint/signing scope. Không đưa static access keys vào constructor của mỗi request.

### 9.1. Default credentials provider chain

AWS SDK for Java 2.x hỗ trợ **DefaultCredentialsProvider** để tìm credentials theo các nguồn được cấu hình trong môi trường, ví dụ:

- Java system properties hoặc environment variables khi được dùng.
- Web identity token/role cho các môi trường Kubernetes/identity federation được hỗ trợ.
- Shared AWS profiles/credentials files.
- ECS container credentials.
- EC2 instance profile credentials qua instance metadata.

Thứ tự và nguồn cụ thể có thể khác theo SDK version và cấu hình. Trong production trên AWS, ưu tiên **IAM role credentials** do Lambda/ECS/EKS/EC2 cấp. Provider phù hợp có thể cache và tự refresh temporary credentials; static credentials không tự xoay vòng.

### 9.2. Tạo client dùng default chain

~~~java
import software.amazon.awssdk.auth.credentials.DefaultCredentialsProvider;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.sqs.SqsClient;

SqsClient sqs = SqsClient.builder()
    .region(Region.AP_SOUTHEAST_1)
    .credentialsProvider(DefaultCredentialsProvider.create())
    .build();
~~~

Khi ứng dụng chạy trên Lambda/ECS, provider chain có thể chọn credentials từ execution/task role. Cần bảo đảm IAM role đúng quyền service API; nếu lỗi AccessDenied, xác minh caller identity và policy thay vì chép access keys của developer vào container.

### 9.3. AssumeRole credentials provider

Với cross-account, ứng dụng có thể dùng **STS AssumeRole** và một credentials provider hỗ trợ refresh temporary credentials. Provider được quản lý theo application lifecycle; nếu ứng dụng tự tạo **StsClient** hoặc provider, phải đóng chúng theo ownership và không đóng provider dùng chung trong khi clients khác vẫn cần nó.

**Không assume role thủ công cho mỗi API call.** Dùng provider có cache/refresh để tránh tạo STS traffic không cần thiết và tránh hết hạn credentials giữa request. Trust policy của target role, source principal, external ID khi phù hợp và session duration phải được cấu hình riêng.

### 9.4. Region và nhiều Region

Client có Region cố định sau khi build:

- Dùng **Region.AP_SOUTHEAST_1** hoặc **Region.of(...)** theo cấu hình.
- Với nhiều Regions, tạo **client riêng cho từng Region** hoặc một registry có giới hạn và lifecycle rõ.
- Không thay endpoint/Region tùy tiện cho từng request trên cùng client.
- Kiểm tra **signing Region** và endpoint khi dùng custom endpoint, FIPS hoặc dual-stack.
- Không hard-code Region sai môi trường; inject qua configuration và validate startup.

### 9.5. Custom endpoint chỉ dành cho mục đích có chủ đích

LocalStack hoặc integration tests có thể dùng **endpointOverride(...)**. Trong production, endpoint override ngoài dự kiến có thể gửi signed requests tới sai endpoint. Nên tách test profile/config, không lấy URL tùy ý từ request user để build SDK client.

## 10. AWS SDK HTTP pool khác JDBC pool tới RDS

Đây là hai nhóm connections riêng biệt:

~~~mermaid
flowchart TD
    APP["Java application"]
    APP --> AWSCLIENT["AWS SDK service client"]
    AWSCLIENT --> HTTPPOOL["HTTP connection pool<br/>Apache / Netty"]
    HTTPPOOL --> S3["S3 / DynamoDB / SQS / STS APIs"]
    APP --> JDBC["JDBC DataSource<br/>HikariCP"]
    JDBC --> DBPOOL["Database connection pool"]
    DBPOOL --> RDS["RDS / Aurora TCP sessions"]
    APP --> PROXY["RDS Proxy (optional)"]
    PROXY --> RDS
~~~

| Connection pool | Dùng để kết nối tới | Cấu hình thường gặp | Không thay thế |
|---|---|---|---|
| **AWS SDK HTTP pool** | AWS service HTTPS endpoints | Apache maxConnections, Netty maxConcurrency | JDBC pool |
| **JDBC pool (HikariCP)** | RDS/Aurora database TCP endpoint | maximumPoolSize, connectionTimeout, idleTimeout, maxLifetime | AWS SDK HTTP pool |
| **RDS Proxy** | Proxy sessions giữa ứng dụng và DB | Proxy target group, maxConnectionsPercent, idle client timeout | Không phải AWS SDK HTTP transport |

Một ứng dụng gọi DynamoDB và RDS có thể đồng thời dùng **Apache HTTP pool** cho DynamoDB API và **HikariCP** cho JDBC. Tăng maxConnections của Apache không làm tăng số kết nối SQL. Tăng Hikari maximumPoolSize không làm tăng S3 throughput.

**Connection leak** cần được chẩn đoán theo đúng pool: nếu Hikari active connections không về idle, kiểm tra JDBC Connection/ResultSet/transaction; nếu Apache pending acquisition tăng, kiểm tra AWS response streams và HTTP pool metrics.

## 11. Quản lý response body, streams và futures

HTTP connection chỉ có thể được tái sử dụng khi response được xử lý đúng theo semantics của transport. Với các API trả body dạng stream, việc bỏ quên close có thể giữ connection, làm pool cạn dần dù service client vẫn được tái sử dụng.

### 11.1. S3 synchronous: luôn đóng ResponseInputStream

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import software.amazon.awssdk.core.ResponseInputStream;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.GetObjectRequest;
import software.amazon.awssdk.services.s3.model.GetObjectResponse;

public void download(
        S3Client s3, String bucket, String key, Path destination)
        throws IOException {

    GetObjectRequest request = GetObjectRequest.builder()
        .bucket(bucket)
        .key(key)
        .build();

    try (ResponseInputStream<GetObjectResponse> input = s3.getObject(request);
         var output = Files.newOutputStream(destination)) {
        input.transferTo(output);
    }
}
~~~

**ResponseInputStream** phải được đóng ngay cả khi ghi file lỗi. Không trả stream ra ngoài rồi quên ai sở hữu nó; nếu cần stream API cho tầng khác, quy định rõ caller phải close. Với file rất lớn, stream theo chunks thay vì đọc toàn bộ vào byte array.

### 11.2. S3 async: dùng response transformer

~~~java
import java.nio.file.Path;
import java.util.concurrent.CompletableFuture;
import software.amazon.awssdk.services.s3.S3AsyncClient;
import software.amazon.awssdk.services.s3.model.GetObjectRequest;
import software.amazon.awssdk.services.s3.model.GetObjectResponse;
import software.amazon.awssdk.core.async.AsyncResponseTransformer;

public CompletableFuture<GetObjectResponse> downloadAsync(
        S3AsyncClient s3, String bucket, String key, Path destination) {

    return s3.getObject(
        GetObjectRequest.builder()
            .bucket(bucket)
            .key(key)
            .build(),
        AsyncResponseTransformer.toFile(destination)
    );
}
~~~

Response transformer quản lý luồng ghi file và completion. Với custom **Publisher/Subscriber**, phải tuân theo Reactive Streams backpressure, consume/cancel đúng cách và xử lý exception/cancellation; không bỏ subscriber giữa chừng rồi kỳ vọng connection tự được giải phóng ngay.

### 11.3. Không giữ connection trong lúc xử lý nghiệp vụ dài

Sai lầm thường gặp: tải object thành stream, giữ stream mở trong khi gọi database hoặc chờ người dùng; trong lúc đó HTTP connection vẫn bận. Tốt hơn là đọc theo chunks và đóng stream trước khi chạy tác vụ dài nếu dung lượng/thiết kế cho phép, hoặc dùng **S3 Transfer Manager** cho upload/download lớn với concurrency và lifecycle được quản lý.

### 11.4. Đừng đọc mọi object vào memory

Phương thức **ResponseTransformer.toBytes()** hoặc cách đọc toàn bộ InputStream vào byte array tiện cho payload nhỏ. Với object lớn, memory allocation và GC pressure có thể gây latency spike hoặc OutOfMemoryError. Chọn streaming/file transformer, multipart transfer và giới hạn đồng thời theo disk/network/memory.

## 12. Graceful shutdown và thứ tự đóng tài nguyên

Đóng client ngay khi ứng dụng còn request đang chạy có thể làm operations thất bại. Shutdown cần **ngừng nhận việc mới, drain work hiện tại và đóng theo ownership**.

### 12.1. Thứ tự shutdown tham khảo

1. Readiness chuyển sang **not ready**, ngừng nhận HTTP requests mới.
2. Ngừng scheduled jobs, queue polling và producers tạo AWS requests mới.
3. Chờ in-flight synchronous calls, futures, streams và transfers trong giới hạn termination grace period.
4. Đóng các higher-level components như Transfer Manager hoặc worker services.
5. Đóng **service clients**.
6. Đóng **shared HTTP transport** do ứng dụng sở hữu.
7. Đóng credentials providers/STS clients và executor resources do ứng dụng tự tạo, theo dependency ownership.

**Đóng đúng một lần** đối với shared resources. Nếu nhiều clients cùng dùng provider hoặc HTTP transport, không để một bean/request handler đóng resource khi những consumers khác vẫn đang hoạt động.

### 12.2. Spring Boot bean dependency order

Nếu Spring quản lý shared HTTP transport và service clients:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import software.amazon.awssdk.http.SdkHttpClient;
import software.amazon.awssdk.http.apache.ApacheHttpClient;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.regions.Region;

@Configuration
public class SharedAwsTransportConfiguration {

    @Bean(destroyMethod = "close")
    SdkHttpClient awsHttpTransport() {
        return ApacheHttpClient.builder()
            .maxConnections(80)
            .build();
    }

    @Bean(destroyMethod = "close")
    S3Client s3Client(SdkHttpClient awsHttpTransport) {
        return S3Client.builder()
            .region(Region.AP_SOUTHEAST_1)
            .httpClient(awsHttpTransport)
            .build();
    }
}
~~~

Service client phụ thuộc vào transport bean; Spring quản lý thứ tự hủy dependency để service client được đóng trước dependency mà nó sử dụng. Vì transport được truyền qua **httpClient(...)**, application context cũng phải quản lý và đóng transport bean. Nếu tạo client bằng **httpClientBuilder(...)**, lifecycle của transport nội bộ do service client quản lý.

### 12.3. Lambda không nên dựa vào shutdown hook để giữ dữ liệu

Execution environment Lambda có thể bị tái sử dụng hoặc kết thúc bởi nền tảng. Dùng static clients để reuse là tốt; nhưng không phụ thuộc shutdown hook để flush giao dịch quan trọng hoặc bảo đảm một async future hoàn tất. Hoàn thành công việc cần thiết trước khi handler trả về, hoặc dùng kiến trúc queue/workflow để xử lý dài hạn.

## 13. Observability: biết pool đang khỏe hay bị nghẽn

Chỉ thấy API trả 200 không đủ để biết connection pool được cấu hình đúng. Theo dõi cả **application-level latency** và **SDK/HTTP-level behavior**.

### 13.1. Các chỉ số nên có

| Metric/Signal | Câu hỏi cần trả lời | Triệu chứng xấu |
|---|---|---|
| **API call duration p50/p95/p99** | AWS operation chậm tới mức nào? | p99 tăng nhưng CPU app thấp |
| **API attempt duration** | Một attempt kéo dài bao lâu? | Timeout ở network/service |
| **Retry count / throttling count** | SDK phải thử lại bao nhiêu? | Retry storm hoặc quota vượt |
| **Connection acquisition latency** | Requests chờ pool bao lâu? | Pool nhỏ hoặc response chưa close |
| **Pending connection acquires** | Có bao nhiêu requests đang chờ? | Burst/concurrency quá lớn |
| **Connection timeout/socket timeout** | Có lỗi network/endpoint/slow response? | DNS/TLS/route/service latency |
| **In-flight requests / max concurrency** | Pool có chạm giới hạn thường xuyên? | Saturation |
| **Response stream duration** | Body được đọc/đóng trong bao lâu? | Stream giữ connection quá lâu |
| **HTTP status/service exceptions** | AWS trả lỗi gì? | AccessDenied, throttling, 5xx |
| **Credential refresh failures** | Provider có lấy được temporary credentials? | Expired credentials hoặc metadata access |

### 13.2. AWS SDK metrics và application metrics

AWS SDK for Java 2.x có **metrics publishing SPI** và execution interceptors để quan sát API calls theo khả năng/version của SDK. Có thể tích hợp metrics publisher hoặc bridge sang hệ thống observability hiện có. Application cũng nên đo:

- Thời gian từ lúc handler bắt đầu gọi client đến lúc nhận response.
- Thời gian chờ pool/queueing nếu transport metrics có cung cấp.
- Số operations đồng thời theo service.
- Retry/error count theo operation và AWS error code.
- Payload size/streaming duration theo bucket/service nhưng tránh ghi nội dung nhạy cảm.

Không log AWS Authorization header, SigV4 signature, access key, session token, request body nhạy cảm hoặc presigned URLs có quyền truy cập. Với lỗi, lưu **AWS request ID**/extended request ID khi response metadata cung cấp, cùng correlation ID đã redaction.

### 13.3. Correlate application và AWS service metrics

Nếu DynamoDB API latency tăng, so sánh:

1. Application p95/p99 và SDK attempts/retries.
2. HTTP connection acquisition/pending counts.
3. DynamoDB throttling/consumed capacity/latency metrics.
4. VPC DNS/TLS/network path nếu client chạy private subnets.

Nếu pool acquisition latency cao nhưng DynamoDB service latency bình thường, bottleneck có thể nằm ở client pool/stream leak. Nếu pool còn capacity nhưng service trả throttling, cần điều chỉnh workload/partition/capacity chứ không chỉ tăng maxConnections.

## 14. Dependency management và version consistency

AWS SDK for Java 2.x có nhiều service modules và HTTP implementations. Nên dùng **AWS SDK BOM** để các module dùng cùng version, tránh trộn các artifact khác version gây lỗi class loading hoặc behavior không nhất quán.

### 14.1. Maven BOM minh họa

~~~xml
<dependencyManagement>
  <dependencies>
    <dependency>
      <groupId>software.amazon.awssdk</groupId>
      <artifactId>bom</artifactId>
      <version>REPLACE_WITH_AWS_SDK_VERSION</version>
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
    <artifactId>dynamodb</artifactId>
  </dependency>
  <dependency>
    <groupId>software.amazon.awssdk</groupId>
    <artifactId>apache-client</artifactId>
  </dependency>
</dependencies>
~~~

Thay **REPLACE_WITH_AWS_SDK_VERSION** bằng một SDK v2 version đã được tổ chức kiểm thử và quản lý cập nhật. Với async clients, thêm **netty-nio-client**; với STS assume-role provider, thêm **sts**. Không thêm mọi service modules chỉ vì “có thể cần sau này”.

### 14.2. Không trộn AWS SDK v1 và v2

SDK v1 dùng package **com.amazonaws...**; SDK v2 dùng **software.amazon.awssdk...**. Một ứng dụng migration có thể tạm thời chứa cả hai, nhưng phải phân biệt rõ dependencies, credential providers, client lifecycles và logging. Đừng truyền object/request/credentials provider của SDK v1 vào API v2 hoặc nghĩ chúng tương thích.

### 14.3. Theo dõi version và security updates

- Dùng BOM hoặc dependency management tập trung.
- Cập nhật SDK v2 theo lịch có kiểm thử, nhất là security fixes và retry/HTTP behavior changes.
- Kiểm tra Java runtime compatibility, driver/transport versions và dependency conflicts.
- Không ép một version của **netty** hoặc **Apache HTTP components** lệch khỏi version mà SDK module tương ứng yêu cầu nếu chưa đánh giá compatibility.
- Ghi nhận SDK version trong build artifact/SBOM để truy vết sự cố.

## 15. Kiểm thử vòng đời và connection reuse

Client reuse là hành vi cần kiểm chứng qua **application architecture và load tests**, không chỉ assert rằng một field là static.

### 15.1. Unit test: inject service client

Để business service nhận **S3Client** hoặc **DynamoDbClient** qua constructor, test có thể mock client interface. Không build AWS client thật trong mỗi unit test nếu không cần. Điều này cũng giúp phát hiện code đang tạo client sâu trong business method thay vì dùng dependency được quản lý.

~~~java
import static org.mockito.Mockito.*;
import org.junit.jupiter.api.Test;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.HeadObjectRequest;
import software.amazon.awssdk.services.s3.model.HeadObjectResponse;

class ObjectServiceTest {
    @Test
    void readsMetadataFromInjectedClient() {
        S3Client s3 = mock(S3Client.class);
        when(s3.headObject(any(HeadObjectRequest.class)))
            .thenReturn(HeadObjectResponse.builder()
                .contentLength(42L)
                .contentType("text/plain")
                .build());

        ObjectService service = new ObjectService(s3);
        var result = service.getMetadata("docs", "guide.txt");

        // Assert kết quả theo DTO của ứng dụng.
        verify(s3, times(1)).headObject(any(HeadObjectRequest.class));
    }
}
~~~

**ObjectService** và DTO là lớp thuộc ứng dụng minh họa. Test tập trung vào hành vi business; không kiểm tra internal connection pool của Apache bằng mock service client.

### 15.2. Integration test: LocalStack hoặc AWS test account

Một integration test có thể dùng **LocalStack** hoặc AWS account riêng với resource disposable. Ví dụ LocalStack:

~~~java
import java.net.URI;
import software.amazon.awssdk.auth.credentials.AwsBasicCredentials;
import software.amazon.awssdk.auth.credentials.StaticCredentialsProvider;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;

S3Client localS3 = S3Client.builder()
    .region(Region.US_EAST_1)
    .endpointOverride(URI.create("http://localhost:4566"))
    .credentialsProvider(
        StaticCredentialsProvider.create(
            AwsBasicCredentials.create("test", "test")
        )
    )
    .build();
~~~

Static test credentials và endpoint localhost **chỉ dành cho môi trường test**. Không tái sử dụng đoạn cấu hình này trong production. Khi test với AWS thật, tạo bucket/table/queue có tên riêng, cleanup tài nguyên và kiểm soát chi phí.

### 15.3. Test connection reuse có ý nghĩa

Để chứng minh pool hoạt động:

1. Build **một service client** và thực hiện nhiều API calls tới cùng AWS endpoint.
2. Đo client initialization time, p50/p95/p99, connection acquisition và retry.
3. So sánh với thử nghiệm client-per-request trong **test harness riêng**, không dùng làm production pattern.
4. Test concurrency/burst, response streaming và request cancellation.
5. Kiểm tra số sockets/threads, pool saturation, idle connections và memory.
6. Test shutdown khi có requests/futures đang chạy.

Không kết luận reuse thành công chỉ vì số lần gọi API nhiều hơn số client objects. Cần xem transport thực sự được share và response bodies có được đóng hay không.

### 15.4. Kiểm thử failure scenarios

- AWS API trả throttling/5xx.
- DNS lookup/TLS handshake thất bại.
- Credentials hết hạn hoặc role assume bị từ chối.
- HTTP pool hết connections hoặc pending acquire timeout.
- S3 stream bị client cancel giữa chừng.
- Async future hoàn thành sau khi application bắt đầu shutdown.
- ECS rolling deployment tạo nhiều pools đồng thời.
- Lambda cold start và warm invocation có latency khác nhau.

## 16. Bảo mật trong client lifecycle

### 16.1. Dùng IAM roles và credentials provider

- Ưu tiên **Lambda execution role, ECS task role, EKS Pod Identity/IRSA, EC2 instance profile**.
- Không commit access key/secret key vào Git, Docker image, Java properties hoặc CI logs.
- Tránh static credentials provider trong production trừ khi có use case được quản trị đặc biệt.
- Với AssumeRole, dùng provider refresh credentials; kiểm soát trust policy, session duration và external ID khi cần.
- Cấp IAM permissions theo **service actions và resource ARNs** tối thiểu.

### 16.2. Bảo vệ TLS và endpoint

- Dùng AWS endpoints HTTPS mặc định và giữ certificate verification.
- Không tắt hostname verification hoặc trust mọi certificates để xử lý lỗi tạm thời.
- Không cho request người dùng điều khiển **endpointOverride**.
- Với VPC endpoints/private networking, kiểm tra DNS và endpoint policies thay vì mở public access.
- Không lưu presigned URLs lâu hơn cần thiết; chúng là bearer credentials có quyền trong thời hạn.

### 16.3. Logging và request metadata

Không log:

- Access key ID/secret access key/session token.
- Authorization header, SigV4 signature, IAM database tokens hoặc secret values.
- Payload nhạy cảm, presigned URLs đầy đủ hoặc request bodies có PII.
- Nội dung response stream chỉ để debug.

Có thể log **AWS request ID**, service operation, duration, retry count, error code và correlation ID sau khi redaction. Nếu bật wire-level logging để chẩn đoán, giới hạn ở test/staging, giữ thời gian ngắn và bảo vệ logs.

### 16.4. Client lifecycle là vấn đề bảo mật

Client/transport sống quá lâu sau khi credentials/role configuration thay đổi có thể tiếp tục dùng provider/config cũ theo cách không mong muốn. Ngược lại, tạo client liên tục làm tăng bề mặt cấu hình và resource leaks. Quản lý lifecycle tập trung giúp **credential refresh, endpoint policy, TLS và auditing** nhất quán.

## 17. Anti-patterns và cách sửa

| Anti-pattern | Tác hại | Cách sửa |
|---|---|---|
| Tạo S3Client trong mỗi controller method | Client/pool churn | Inject application-scoped singleton |
| Gọi close sau mỗi API call | Các request khác dùng client bị lỗi | Close ở application shutdown |
| Không bao giờ close shared HTTP transport | Threads/sockets còn sống sau shutdown | Một owner đóng sau các service clients |
| Share transport cho workload không tương đồng | Một service chiếm hết pool | Tách pool theo SLO/traffic |
| maxConnections đặt cực lớn | Sockets và downstream pressure tăng | Load test, sizing theo in-flight requests |
| maxConcurrency Netty không giới hạn workload | Pending futures/memory tăng | Backpressure và bounded concurrency |
| Bỏ quên close S3 response stream | Pool connection bị giữ | try-with-resources hoặc transformer |
| Dùng join() trong event loop | Chặn I/O threads | Compose CompletableFuture, tránh blocking |
| Dùng static access keys | Credential leak/không tự refresh | IAM role và default provider chain |
| Tạo token/credentials mỗi request thủ công | STS/API overhead và race | Credentials provider có cache/refresh |
| Dùng một client cho mọi Region/role | Sai signing Region/permissions | Client riêng theo config ổn định |
| Retry tất cả lỗi vô hạn | Retry storm, duplicate writes | Bounded retry, backoff, idempotency |
| Dùng SDK HTTP pool thay HikariCP | Nhầm hai loại connections | Quản lý AWS HTTP và JDBC pools riêng |
| Log toàn bộ request/response | Lộ secret và PII | Log metadata có redaction |
| Đóng client trước khi drain futures | Requests in-flight thất bại | Graceful shutdown |

## 18. Runbook xử lý lỗi client và connection pool

~~~mermaid
flowchart TD
    A["AWS API call chậm hoặc lỗi"] --> B{"Lỗi ở bước nào?"}
    B -->|"Pool acquire"| POOL["maxConnections/maxConcurrency<br/>pending acquires, stream close"]
    B -->|"TCP/TLS connect"| NET["DNS, route, proxy, SG/NACL,<br/>connectionTimeout, CA"]
    B -->|"Credentials/signing"| CRED["Credentials provider refresh,<br/>Region, clock, SigV4"]
    B -->|"Service response"| SVC["AWS error code, IAM policy,<br/>quota, retry strategy"]
    POOL --> FIX["Sửa nguyên nhân gốc<br/>và kiểm thử lại"]
    NET --> FIX
    CRED --> FIX
    SVC --> FIX
    FIX --> VERIFY["Đo p95/p99, retry rate,<br/>pool usage và shutdown"]
~~~

### 18.1. Triệu chứng thường gặp

| Triệu chứng | Nguyên nhân khả dĩ | Kiểm tra |
|---|---|---|
| **SdkClientException: Unable to execute HTTP request** | Lỗi HTTP transport bọc lỗi DNS/TLS/socket/pool | Đọc root cause trong cause chain, không dừng ở exception ngoài |
| **Timeout waiting for connection from pool** | Pool cạn, stream chưa đóng, maxConnections thấp hoặc burst | Pending acquire, active connections, response stream lifecycle |
| **Connection pool shut down** | Client/transport đã bị close nhưng code vẫn dùng | Owner, shutdown order, close per request |
| **Too many open files / sockets** | Client/transport tạo liên tục hoặc không close | Số client instances, threads, sockets và process limits |
| **Connection reset / stale connection** | Network idle timeout, endpoint đóng connection, TTL quá dài | Keep-alive, idle time, connection TTL, retry |
| **UnknownHostException** | DNS resolver/endpoint/Region sai hoặc network DNS | Endpoint hostname, VPC DNS, resolver/route |
| **SSLHandshakeException** | Truststore/CA, TLS config, proxy hoặc clock | Certificate chain, hostname, TLS interception |
| **ExpiredToken / InvalidToken** | Temporary credentials hết hạn, provider không refresh, static creds cũ | Caller identity, provider chain, STS/role session |
| **SignatureDoesNotMatch** | Region/endpoint/clock/headers/payload ký không nhất quán | Region, custom endpoint, system time, request signing |
| **AccessDeniedException** | IAM identity/resource policy/SCP/endpoint policy | Caller ARN, action, resource, explicit Deny |
| **ThrottlingException / 429** | Vượt service quota hoặc burst | Retry count, service metrics, concurrency và quota |
| **Async pending acquires tăng mãi** | Producer tạo futures nhanh hơn consumer/service xử lý | Backpressure, maxConcurrency, pending queue, cancellation |
| **Lambda warm invocation chậm dần** | Pool/stream không được giải phóng, static state tăng | Memory, connection reuse, stream close, background tasks |
| **Shutdown treo** | In-flight requests/futures hoặc threads chưa kết thúc | Drain timeout, executor, transport ownership |

### 18.2. Thứ tự điều tra

1. Ghi nhận **service operation, AWS request ID, Region, caller role, timestamp và error code**; redact credentials/payload.
2. Đọc toàn bộ **cause chain** để phân biệt SDK exception wrapper với lỗi HTTP/TLS/DNS thật.
3. Nếu pool acquisition timeout, kiểm tra response streams, in-flight calls, maxConnections/maxConcurrency và pending acquire.
4. Nếu connect timeout, kiểm tra DNS, VPC route, proxy, security group, TLS handshake và endpoint.
5. Nếu signature/credential lỗi, xác minh credentials provider, refresh, Region và clock synchronization.
6. Nếu service trả AccessDenied/throttling, xem IAM/resource policy/quota; không tăng pool để chữa quyền.
7. Sửa trong staging, kiểm tra cả normal traffic, burst, retry và shutdown.

### 18.3. Connection pool cạn nhưng service không chậm

Một dấu hiệu điển hình là **application acquisition latency tăng**, trong khi AWS service latency thấp và số API requests không tăng. Tìm:

- S3 response streams không close.
- Requests đang đợi futures nhưng caller không consume.
- Shared pool bị một service workload lớn chiếm.
- Client per request tạo nhiều pools và không đóng.
- Max connections quá thấp so với concurrency.

Tăng maxConnections có thể giảm queueing tạm thời, nhưng nếu nguyên nhân là stream leak thì pool lớn hơn chỉ trì hoãn sự cố.

## 19. Chi phí và hiệu quả của tái sử dụng kết nối

**AWS SDK client và connection pool không có một dòng phí AWS riêng chỉ vì object được tạo.** Chi phí thực tế phát sinh từ AWS API requests, service capacity/storage, data transfer, retries, logs/metrics và compute/network mà ứng dụng sử dụng. Tối ưu client lifecycle giảm overhead trong ứng dụng và có thể giảm retry/churn, nhưng **không làm một API request hợp lệ trở nên miễn phí**.

| Thành phần | Ảnh hưởng chi phí |
|---|---|
| **Client per request** | Tăng CPU, TLS handshakes, memory, threads và nguy cơ autoscaling; gián tiếp tăng compute cost |
| **Connection reuse** | Giảm handshake/churn và latency; vẫn tính phí theo API requests/service usage |
| **Retries** | Tạo thêm API attempts, có thể tăng request charges và downstream load |
| **Pool quá lớn** | Tăng sockets/memory, có thể khiến app scale/compute tốn hơn |
| **Pool quá nhỏ** | Queueing/timeouts/retries, làm throughput giảm |
| **Logging/metrics** | CloudWatch ingestion, storage và queries có phí theo pricing hiện hành |
| **VPC endpoints/NAT** | Có thể phát sinh hourly/data processing/NAT charges tùy kiến trúc |
| **Lambda cold starts** | Client build mỗi execution environment có chi phí khởi tạo; reuse giảm work trong warm invocations |

### 19.1. Cách đo hiệu quả trước và sau

Đặt cùng workload, cùng Region/service quota, cùng payload và cùng concurrency; so:

- p50/p95/p99 của API operation và end-to-end handler.
- Client initialization time và số sockets/threads.
- HTTP pool acquisition latency/pending count.
- TLS connection churn, retries, throttling và error rate.
- CPU/memory của Java process, GC pauses và container scaling.
- AWS request counts và cost allocation theo service.

Không kết luận client reuse giúp giảm trực tiếp AWS request charges nếu số API calls không đổi. Lợi ích chính thường là **giảm latency, giảm tài nguyên app, giảm lỗi do churn và tăng khả năng dự đoán tải**.

## 20. Mẫu thiết kế production

### 20.1. Checklist chọn vòng đời

| Môi trường | Mô hình nên bắt đầu | Điểm cần xác minh |
|---|---|---|
| **CLI/batch một lần** | try-with-resources quanh service client | Đóng khi job kết thúc |
| **Spring Boot/ECS/EKS/EC2** | Singleton bean/application-scoped client | Graceful shutdown và pool sizing |
| **AWS Lambda** | Static/application-level client ngoài handler | Không close mỗi invocation, giới hạn concurrency |
| **Async high-throughput** | Async client + Netty shared/owned transport | Backpressure, maxConcurrency, event loop lifecycle |
| **Multi-Region** | Client riêng mỗi Region | Endpoint/signing Region và failover |
| **Cross-account** | Client dùng credentials provider/assumed role phù hợp | STS refresh, trust policy, lifecycle |
| **S3 large objects** | S3 client/Transfer Manager và streaming | Multipart concurrency, stream cleanup, memory/disk |
| **AWS APIs + RDS** | SDK HTTP pool riêng, JDBC pool riêng | Không nhầm maxConnections với DB pool size |

### 20.2. Ví dụ cấu hình theo properties

Không cần hard-code mọi con số trong Java class. Có thể inject các giá trị như:

~~~yaml
app:
  aws:
    region: ap-southeast-1
    http:
      max-connections: 80
      connection-timeout-ms: 2000
      acquisition-timeout-ms: 3000
      socket-timeout-ms: 15000
    api:
      call-timeout-ms: 25000
      attempt-timeout-ms: 8000
~~~

Đây là **cấu hình ứng dụng minh họa**, không phải cấu trúc properties chuẩn tự động được AWS SDK đọc. Application phải bind/validate các giá trị này và truyền vào SDK builders. Có thể đặt giới hạn min/max để không cho cấu hình môi trường làm pool vượt năng lực hạ tầng.

### 20.3. Một số quy tắc triển khai

1. **Một service client cho một cấu hình ổn định**; không tạo mới trong hot path.
2. **Thread-safe client dùng chung**, request data/streams quản lý riêng.
3. **HTTP transport có owner rõ ràng**; shared instance chỉ close một lần.
4. **Connection pool có giới hạn** và được sizing theo concurrency thực.
5. **Timeout tổng thể bao trùm retries**, phù hợp deadline của ứng dụng.
6. **Credentials provider có refresh** và dùng IAM roles trên AWS.
7. **Response streams/futures phải được hoàn tất hoặc cancel/close**.
8. **Shutdown drain trước khi close**; không đóng transport khi còn request.
9. **HTTP pool khác JDBC pool**; đo và tune riêng.
10. **Observability có request IDs, retries, pool waits và p95/p99** nhưng không log secrets.

## 21. Bài tập tình huống

### Tình huống A — S3Client được tạo trong mỗi REST request

Một Spring Boot controller gọi S3. Developer tạo **S3Client.builder().build()** mỗi lần upload, upload xong gọi close. Khi traffic tăng, latency và số TCP/TLS connections tăng.

**Câu hỏi:** cần thay đổi lifecycle thế nào?

**Gợi ý:** inject một singleton **S3Client bean**, để Spring close khi application shutdown. Đo connection reuse, pool size và upload concurrency. Nếu cần upload lớn, đánh giá Transfer Manager và multipart concurrency.

### Tình huống B — Shared HTTP transport bị đóng quá sớm

S3Client và DynamoDbClient cùng dùng một Apache HTTP client. Một repository gọi **s3.close()** sau request và DynamoDB bắt đầu lỗi **Connection pool shut down**.

**Câu hỏi:** ownership nằm ở đâu?

**Gợi ý:** transport là shared application resource; request handler không sở hữu nó. Không close service client/transport trong hot path. Application lifecycle owner đóng service clients và transport khi shutdown theo đúng thứ tự.

### Tình huống C — S3 download giữ pool mãi

Một method trả **ResponseInputStream** cho controller. Controller gửi headers rồi stream chậm cho client internet; đồng thời AWS HTTP pool chỉ có 20 connections.

**Câu hỏi:** vì sao các S3 requests khác chờ?

**Gợi ý:** response stream chưa được consume/close nên connection bị giữ lâu. Dùng download streaming với backpressure và capacity phù hợp, hoặc staging file/object rồi phục vụ từ một delivery layer; luôn close stream khi client cancel/disconnect.

### Tình huống D — Async client có hàng chục nghìn futures pending

Một worker tạo 50.000 futures cùng lúc nhưng Netty maxConcurrency là 100. Pending acquire tăng, heap memory tăng và shutdown không kết thúc.

**Câu hỏi:** có nên tăng maxConcurrency lên 50.000?

**Gợi ý:** trước tiên dùng **bounded concurrency/backpressure**, batch/windowing và cancellation. Chọn maxConcurrency theo service quota, memory, event loop và downstream. Tăng giới hạn đơn thuần có thể làm nghẽn service và không giải quyết nguồn tạo futures quá nhanh.

### Tình huống E — SDK client gọi AWS thành công rồi lỗi sau một giờ

Ứng dụng dùng static AWS access key/secret key hết hạn hoặc bị rotate, credentials provider là StaticCredentialsProvider.

**Câu hỏi:** tại sao client reuse không tự refresh?

**Gợi ý:** client reuse không thay thế credentials lifecycle. Static provider giữ credentials cố định; dùng IAM role và DefaultCredentialsProvider hoặc STS assume-role provider có refresh. Xác minh caller identity và trust policy.

### Tình huống F — Pool tăng nhưng vẫn gặp throttling

DynamoDB trả ThrottlingException. Developer tăng Apache maxConnections từ 50 lên 500; lỗi tăng nhiều hơn.

**Câu hỏi:** điều gì bị hiểu sai?

**Gợi ý:** HTTP pool chỉ kiểm soát client concurrency, không tăng DynamoDB table/partition quotas. Giảm burst, retry với backoff/jitter, phân tích hot partition, capacity/On-Demand mode và request patterns.

### Tình huống G — API timeout dù service trả response nhanh

Application ghi nhận p99 5 giây, nhưng CloudWatch service latency thấp. SDK pool pending acquires tăng và S3 streams được xử lý bởi một worker chậm.

**Câu hỏi:** tìm bottleneck ở đâu?

**Gợi ý:** đo connection acquisition, active/pending pool, stream lifetime và shared pool contention. Tách pool hoặc điều chỉnh streaming/concurrency; không tăng timeout để che pool starvation.

### Tình huống H — Lambda client đóng sau mỗi invocation

Handler tạo client trong method và đóng ở finally. Warm invocations liên tiếp phải khởi tạo transport lại.

**Câu hỏi:** lifecycle đúng cho Lambda là gì?

**Gợi ý:** tạo client ngoài handler/static field để reuse giữa invocations. Không lưu request-specific data trong static; hoàn tất async work trước khi handler return; không dựa shutdown hook cho critical work.

### Tình huống I — Nhầm AWS HTTP pool với RDS connection pool

Một ứng dụng gọi S3 và Aurora. Team tăng Apache maxConnections để xử lý lỗi HikariCP **Connection is not available**.

**Câu hỏi:** tại sao không hiệu quả?

**Gợi ý:** Apache pool phục vụ AWS service HTTPS requests; HikariCP quản lý JDBC database sessions. Điều tra DB max connections, transaction leaks, pool size và RDS Proxy riêng.

### Tình huống J — Shutdown làm mất các request đang chạy

Container nhận SIGTERM, ngay lập tức đóng S3Client và Netty transport trong khi futures upload còn pending.

**Câu hỏi:** thứ tự shutdown nào an toàn hơn?

**Gợi ý:** readiness not ready, stop producers/consumers, drain in-flight requests/futures/transfers trong grace period, đóng higher-level components và service clients, sau cùng mới đóng shared HTTP transport/provider do ứng dụng sở hữu.

## 22. Checklist production

- [ ] Đã chọn **AWS SDK for Java 2.x** và quản lý các modules bằng BOM/version thống nhất.
- [ ] Service clients được tạo theo application lifecycle, không tạo trong mỗi request.
- [ ] Đã xác định client config theo Region, credentials provider, endpoint và role.
- [ ] Service clients được dùng lại an toàn giữa threads; request-specific state không đặt trong shared mutable fields.
- [ ] Đã chọn sync Apache/URLConnection hay async Netty theo workload và compatibility.
- [ ] Đã quyết định HTTP transport do SDK sở hữu qua builder hay application sở hữu qua instance.
- [ ] Shared HTTP transport chỉ được đóng một lần sau các service clients.
- [ ] Đã sizing maxConnections/maxConcurrency, pending acquires và pool acquisition timeout.
- [ ] Đã cấu hình connection/read/socket/write timeouts, idle time và connection TTL theo transport.
- [ ] API call timeout/attempt timeout phù hợp deadline; retry có giới hạn, backoff và idempotency.
- [ ] Dùng IAM roles/credentials provider chain; không hard-code access keys.
- [ ] Credentials provider/STS client có lifecycle và refresh phù hợp.
- [ ] Region/endpoint được cấu hình theo môi trường; endpoint override chỉ bật trong test có chủ đích.
- [ ] S3 response streams, async futures và transfer managers được consume/close/cancel đúng.
- [ ] AWS SDK HTTP pool và JDBC/HikariCP/RDS Proxy được sizing/monitor riêng.
- [ ] Graceful shutdown ngừng nhận việc mới, drain in-flight work rồi close theo dependency ownership.
- [ ] Có metrics p95/p99, retry/throttle, pool acquisition, pending requests và credential errors.
- [ ] Logs có AWS request IDs/correlation IDs nhưng không lộ tokens, signatures, credentials hoặc payload nhạy cảm.
- [ ] Đã load test burst, long streams, throttling, failover, credential refresh và shutdown.
- [ ] Đã kiểm thử integration trong LocalStack/AWS test account và tránh endpoint/test credentials trong production.
- [ ] Đã đánh giá compute/network/logging/API request costs và tác động của retries.

## 23. Ghi nhớ

**AWS SDK for Java 2.x service clients thread-safe và nên được tái sử dụng theo application lifecycle**: build khi startup/runtime initialization, dùng chung qua nhiều requests, đóng khi owner kết thúc. **Client per request** làm tăng connection churn và resource overhead; **client per application/configuration** giúp tận dụng HTTP connection pooling, credential refresh và quản lý shutdown rõ ràng.

HTTP transport cần ownership cụ thể: dùng **httpClientBuilder(...)** khi SDK service client quản lý transport nội bộ; dùng **httpClient(existingInstance)** khi application chia sẻ transport và phải tự đóng nó sau các service clients. Sizing **maxConnections/maxConcurrency, pending acquires, connection/read timeouts, API call timeout và retry** theo workload, deadline và quota. Luôn đóng **S3 response streams**, quản lý async futures/backpressure và drain trước shutdown.

Cuối cùng, phân biệt **AWS SDK HTTP connection pool** với **JDBC pool tới RDS/Aurora**; dùng IAM roles/credentials providers thay static keys, giữ TLS verification, đo pool metrics và không log secrets. Client reuse là một phần của thiết kế reliability/performance; nó không tự tăng service quotas hoặc thay thế idempotency, IAM least privilege và database connection management.

### Tài liệu AWS chính thức để đối chiếu

- [AWS SDK for Java 2.x best practices](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/best-practices.html) — reuse clients, connection pools và resource management.
- [HTTP configuration](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/http-configuration.html) — chọn HTTP implementation.
- [Apache HTTP client configuration](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/http-configuration-apache.html) — sync connection pool và timeouts.
- [Netty NIO async HTTP client configuration](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/http-configuration-netty.html) — concurrency, pending acquires và async transport.
- [AWS credentials provider chain](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/credentials-chain.html) — credentials resolution.
- [AWS Region selection](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/region-selection.html) — Region provider chain và explicit Region.
- [Configure service client settings](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/client-configuration.html) — retry, API call timeouts và overrides.
- [Retry strategies](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/retry-strategy.html) — retry modes và strategy configuration.
- [Asynchronous programming](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/asynchronous.html) — CompletableFuture và Netty.
- [SDK metrics](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/metrics.html) — metrics publishing SPI.
- [Using the SDK with AWS Lambda](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/lambda.html) — client initialization và runtime reuse.
- [AWS SDK for Java 2.x GitHub](https://github.com/aws/aws-sdk-java-v2) — releases, source và compatibility.



