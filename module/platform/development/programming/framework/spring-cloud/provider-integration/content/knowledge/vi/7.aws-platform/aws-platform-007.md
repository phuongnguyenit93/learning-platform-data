# Tùy chỉnh client theo dịch vụ, HTTP transport và endpoint

## 1. Bối cảnh: cùng một ứng dụng nhưng mỗi dịch vụ AWS cần cấu hình riêng

Một ứng dụng Spring Boot có thể đồng thời **upload tài liệu vào Amazon S3**, **gửi sự kiện tới Amazon SQS**, **đọc dữ liệu từ DynamoDB** và **lấy secret từ AWS Secrets Manager**. Tất cả đều sử dụng AWS SDK for Java, nhưng mỗi client có nhu cầu khác nhau:

- S3 có thể cần truyền file lớn, xử lý streaming, connection pool và chế độ địa chỉ bucket riêng.
- SQS thường có nhiều request nhỏ, long polling và consumer chạy liên tục.
- DynamoDB nhạy cảm với độ trễ, retry, throttling và lưu lượng đồng thời.
- Secrets Manager có tần suất truy cập thấp nhưng yêu cầu giới hạn timeout, quyền IAM và không để lộ dữ liệu.
- Kiểm thử tích hợp có thể phải chuyển endpoint từ AWS thật sang LocalStack hoặc service emulator; production cần đảm bảo trở lại endpoint đúng.

Bài học **“Tùy chỉnh client theo dịch vụ, HTTP transport và endpoint”** thuộc chương **Nền tảng AWS** của module **SPRING_CLOUD_PROVIDER_INTEGRATION**. Phạm vi của module là thực hành tích hợp Spring Boot với các dịch vụ managed của AWS, Azure và Google Cloud qua các thư viện Spring Cloud tương ứng; từ danh tính, quyền truy cập storage/messaging/dữ liệu, bảo vệ secret đến kiểm thử và đánh giá khác biệt giữa cloud provider.

Bài này đi sâu vào **AWS SDK for Java 2.x** và cách sử dụng SDK cùng **Spring Cloud AWS của AWSpring**. Mục tiêu là biết **nên cấu hình chung điều gì**, **nên tùy chỉnh riêng điều gì** cho từng service, và **nên kiểm chứng điều gì** trước khi đưa ứng dụng vào vận hành.

**Sau bài học, bạn có thể:**

1. Chọn client synchronous hoặc asynchronous phù hợp với luồng thực thi Spring Boot.
2. Phân biệt API service client, HTTP transport, endpoint, region, credential và signing.
3. Cấu hình timeout, connection pool, retry và lifecycle của client mà không tạo client mới cho từng request.
4. Thiết lập endpoint override an toàn cho kiểm thử và hiểu những khác biệt của S3, SQS.
5. Tạo bean/client riêng theo dịch vụ, chủ động xử lý tương tác với auto-configuration của AWSpring.
6. Chẩn đoán lỗi network, endpoint, region, IAM và runtime dependency theo đúng tầng.

> **Phạm vi phiên bản:** Ví dụ sử dụng **AWS SDK for Java 2.x**, với các starter AWSpring trong bộ phiên bản **được đối chiếu tương thích** với Spring Boot và Java của dự án. Tên property và điểm mở rộng của AWSpring có thể khác theo release; hãy kiểm tra tài liệu của chính phiên bản đang triển khai. Các host, bucket, queue và region trong ví dụ chỉ nhằm minh họa.

## 2. Mô hình cấu hình client theo từng lớp

Để hiểu một lời gọi `S3Client.putObject(...)` diễn ra như thế nào, cần phân biệt các lớp dưới đây:

~~~mermaid
flowchart TD
    A["Service / Adapter trong Spring Boot"] --> B["AWSpring template hoặc SDK client"]
    B --> C["S3Client / SqsAsyncClient / DynamoDbClient"]
    C --> D["Client configuration: timeout, retry, interceptors"]
    D --> E["Endpoint resolution + region + signing"]
    E --> F["HTTP transport: Apache / URLConnection / Netty / CRT"]
    F --> G["DNS, proxy, TLS, VPC/network"]
    G --> H["AWS service hoặc emulator trong test"]
    I["Credentials provider / IAM role"] -. "Cấp credentials để ký request" .-> E
~~~

Khi thêm dependency AWSpring starter, Spring Boot có thể tự tạo client/abstraction theo điều kiện auto-configuration. Dù vậy, **lời gọi thật vẫn đi qua client của AWS SDK** và HTTP transport phía dưới.

| Lớp | Quyết định chính | Ví dụ |
| --- | --- | --- |
| API nghiệp vụ | Gọi dịch vụ nào, operation nào? | `PutObject`, `SendMessage`, `GetItem` |
| AWSpring | Có cần `S3Template`, `SqsTemplate` hoặc `@SqsListener` không? | Starter S3/SQS |
| AWS SDK client | Sync hay async? Region? Client service nào? | `S3Client`, `SqsAsyncClient` |
| Request execution | Timeout, retry, interceptor và client-level override | `ClientOverrideConfiguration` |
| Endpoint | URL nào nhận request, giải quyết hostname theo region/bucket thế nào? | Endpoint AWS thông thường hoặc LocalStack |
| HTTP transport | Thư viện thực hiện network I/O, TLS, pool và proxy | Apache, URLConnection, Netty |
| Identity | Request được ký bằng principal/role nào? | `DefaultCredentialsProvider` hoặc provider được chỉ định |
| AWS service | IAM/resource policy và nghiệp vụ của service | S3 bucket policy, SQS queue policy |

**Một endpoint đúng không tạo IAM permission**, và một role đúng cũng không bảo đảm URL, network hay HTTP client được cấu hình đúng. Những lỗi này cần được điều tra riêng.

## 3. Chọn đúng SDK client cho từng dịch vụ

AWS SDK v2 tổ chức thư viện theo **module dịch vụ**. Trong cùng ứng dụng, bạn có thể dùng các client riêng:

| Dịch vụ | Client blocking | Client asynchronous | Tác vụ thường gặp |
| --- | --- | --- | --- |
| Amazon S3 | `S3Client` | `S3AsyncClient` | `PutObject`, `GetObject`, `HeadObject` |
| Amazon SQS | `SqsClient` | `SqsAsyncClient` | `SendMessage`, `ReceiveMessage`, `DeleteMessage` |
| Amazon DynamoDB | `DynamoDbClient` | `DynamoDbAsyncClient` | `GetItem`, `PutItem`, `Query` |
| AWS Secrets Manager | `SecretsManagerClient` | `SecretsManagerAsyncClient` | `GetSecretValue` |
| AWS STS | `StsClient` | `StsAsyncClient` | `AssumeRole`, `GetCallerIdentity` |

Ví dụ package SDK v2:

~~~java
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.S3AsyncClient;
import software.amazon.awssdk.services.sqs.SqsAsyncClient;
import software.amazon.awssdk.services.dynamodb.DynamoDbClient;
~~~

Các client trên **không phải** `AmazonS3` hay `AmazonSQS` của AWS SDK Java 1.x (thuộc `com.amazonaws.*`). Nếu dự án dùng Spring Cloud AWS đời mới, không sao chép ví dụ SDK v1 mà bỏ qua sự khác biệt API và dependency.

### 3.1. Khi nào dùng client synchronous?

`S3Client` và `SqsClient` là client đồng bộ: lời gọi hoàn tất hoặc ném exception trước khi thread tiếp tục. Phù hợp với:

- Ứng dụng Spring MVC dùng mô hình request xử lý blocking, số lượng I/O đồng thời được quản lý rõ.
- Tác vụ batch quy mô vừa, code tuyến tính dễ đọc và dễ xử lý lỗi.
- Adapter có ít thao tác AWS, nơi độ đơn giản quan trọng hơn throughput rất lớn.

Ví dụ:

~~~java
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.HeadObjectRequest;

public class FileMetadataGateway {
    private final S3Client s3Client;

    public FileMetadataGateway(S3Client s3Client) {
        this.s3Client = s3Client;
    }

    public long contentLength(String bucket, String key) {
        return s3Client.headObject(
                HeadObjectRequest.builder()
                        .bucket(bucket)
                        .key(key)
                        .build())
                .contentLength();
    }
}
~~~

**Blocking** ở đây là đặc tính của lời gọi SDK. Nếu gọi `S3Client` ngay trong reactive event loop, có thể làm nghẽn event loop; cần di chuyển thao tác blocking sang scheduler phù hợp hoặc chọn async client/adapter thích hợp.

### 3.2. Khi nào dùng client asynchronous?

`SqsAsyncClient` hoặc `S3AsyncClient` trả `CompletableFuture` hoặc abstraction bất đồng bộ tương ứng, giúp không giữ thread của caller trong lúc chờ network I/O.

~~~java
import java.util.concurrent.CompletableFuture;
import software.amazon.awssdk.services.sqs.SqsAsyncClient;
import software.amazon.awssdk.services.sqs.model.SendMessageResponse;

public class OrderEventGateway {
    private final SqsAsyncClient sqs;
    private final String queueUrl;

    public OrderEventGateway(SqsAsyncClient sqs, String queueUrl) {
        this.sqs = sqs;
        this.queueUrl = queueUrl;
    }

    public CompletableFuture<SendMessageResponse> publish(String json) {
        return sqs.sendMessage(request -> request
                .queueUrl(queueUrl)
                .messageBody(json));
    }
}
~~~

Async client phù hợp khi application có nhiều I/O đồng thời, xử lý queue dài hạn hoặc tích hợp với reactive pipeline đã được thiết kế theo cách không blocking.

Tuy nhiên, **async không tự động tốt hơn** trong mọi hoàn cảnh. Bạn phải quản lý số request đồng thời, hàng đợi nội bộ, exception trong future, timeout, áp lực bộ nhớ và vòng đời client. Trong các đoạn xử lý thuộc Spring MVC, `future.join()` ngay lập tức vẫn có thể khiến thread chờ, làm giảm lợi ích async.

**Riêng AWSpring SQS:** phiên bản Spring Cloud AWS 3.x thường sử dụng `SqsAsyncClient` phía dưới cho listener/container và các abstraction SQS. Nếu tùy chỉnh HTTP transport, hãy kiểm tra SDK client **thật sự được container dùng**, không chỉ tùy chỉnh một `SqsClient` sync không được gọi.

## 4. HTTP transport trong AWS SDK for Java v2

AWS SDK phân tách **service client** khỏi **HTTP client**. Service client tạo request mang semantics AWS; HTTP transport chịu trách nhiệm kết nối, TLS, pooling, timeout mức network và các đặc tính I/O khác.

### 4.1. Các transport phổ biến

| HTTP transport | Module Maven | Dùng với | Đặc điểm và lựa chọn |
| --- | --- | --- | --- |
| Apache HTTP client | `software.amazon.awssdk:apache-client` | SDK client synchronous | Pool connection, proxy và nhiều tùy chọn HTTP |
| JDK URLConnection | `software.amazon.awssdk:url-connection-client` | SDK client synchronous | Gọn, ít dependency; khả năng pooling/tùy chỉnh khác Apache |
| Netty NIO HTTP client | `software.amazon.awssdk:netty-nio-client` | SDK client asynchronous | Event-loop, connection pool và concurrency bất đồng bộ |
| AWS CRT HTTP client | `software.amazon.awssdk:aws-crt-client` | Các SDK client tương ứng, tùy release | Transport dựa trên AWS Common Runtime, cần xét hỗ trợ và native runtime |
| S3 CRT client / transfer-specific option | Tùy module/hỗ trợ của SDK | S3 async/transfer workload cụ thể | Hữu ích khi cần cơ chế truyền dữ liệu S3 tối ưu; cần đánh giá tải và môi trường |

AWS SDK v2 thường có transport mặc định theo classpath và kiểu client. **Không nên dựa vào giả định “mặc định luôn là X” khi tối ưu hoặc debug production**: ghi rõ HTTP client builder và khai báo module tương ứng để kiểm soát kết quả.

### 4.2. Khai báo dependency Maven có chủ đích

Giả sử dự án đã quản lý version bằng AWSpring BOM và/hoặc AWS SDK BOM phù hợp:

~~~xml
<dependencies>
    <!-- Chỉ thêm service SDK được source của app sử dụng trực tiếp. -->
    <dependency>
        <groupId>software.amazon.awssdk</groupId>
        <artifactId>s3</artifactId>
    </dependency>
    <dependency>
        <groupId>software.amazon.awssdk</groupId>
        <artifactId>sqs</artifactId>
    </dependency>

    <!-- Apache cho client đồng bộ. -->
    <dependency>
        <groupId>software.amazon.awssdk</groupId>
        <artifactId>apache-client</artifactId>
    </dependency>

    <!-- Netty cho client bất đồng bộ. -->
    <dependency>
        <groupId>software.amazon.awssdk</groupId>
        <artifactId>netty-nio-client</artifactId>
    </dependency>
</dependencies>
~~~

Mỗi project chỉ cần những dependency thực tế sử dụng. Một starter AWSpring có thể kéo một số dependency SDK **transitively**, nhưng nếu source của ứng dụng import trực tiếp HTTP builder/service client thì nên khai báo module tương ứng ở mức trực tiếp theo chính sách dependency của dự án.

**Không tự gắn nhiều version SDK v2 khác nhau** cho `s3`, `sqs`, `apache-client` và `netty-nio-client`. Cần kiểm tra resolved dependency graph để chắc các module cùng tương thích. Nếu hiện diện cả `com.amazonaws` (SDK 1.x) và `software.amazon.awssdk` (SDK 2.x), kiểm tra thư viện legacy nào kéo SDK 1.x, thay vì giả định hai thế hệ dùng chung client.

## 5. Cấu hình HTTP client đồng bộ bằng Apache

Ví dụ một service cần đọc metadata hoặc upload object S3 với kết nối đồng bộ. Có thể cấu hình một `S3Client` dùng Apache HTTP transport:

~~~java
import java.time.Duration;
import software.amazon.awssdk.core.client.config.ClientOverrideConfiguration;
import software.amazon.awssdk.http.apache.ApacheHttpClient;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;

public final class S3ClientFactory {
    public static S3Client create() {
        return S3Client.builder()
                .region(Region.AP_SOUTHEAST_1)
                .httpClientBuilder(ApacheHttpClient.builder()
                        .maxConnections(80)
                        .connectionTimeout(Duration.ofSeconds(3))
                        .socketTimeout(Duration.ofSeconds(15)))
                .overrideConfiguration(ClientOverrideConfiguration.builder()
                        .apiCallAttemptTimeout(Duration.ofSeconds(20))
                        .apiCallTimeout(Duration.ofSeconds(45))
                        .build())
                .build();
    }
}
~~~

Trong ví dụ trên:

- `maxConnections(80)` là giới hạn pool cho HTTP transport của client, cần cân bằng với concurrency thực tế.
- `connectionTimeout` giới hạn thời gian thiết lập kết nối ở mức HTTP; không phải tổng thời gian upload.
- `socketTimeout` liên quan thời gian chờ I/O socket ở transport này; không đồng nghĩa thời hạn toàn bộ API call.
- `apiCallAttemptTimeout` giới hạn **một lần thử** request.
- `apiCallTimeout` giới hạn **toàn bộ lời gọi SDK**, bao gồm các attempt/retry theo cơ chế client.

Các con số chỉ **minh họa để học**, không phải khuyến nghị cố định. Trên workload upload file lớn, timeout socket/API thấp có thể cắt ngang truyền dữ liệu hợp lệ. Với thao tác metadata nhỏ, timeout quá dài làm người dùng chờ không cần thiết.

### 5.1. Không tạo HTTP client mới cho mỗi request nghiệp vụ

Ví dụ **không nên**:

~~~java
// Phản ví dụ: tạo client cho từng lần gọi API.
// void getMetadata(...) {
//     S3Client s3 = S3Client.builder().build();
//     s3.headObject(...);
//     // Không tái sử dụng connection; dễ làm rò tài nguyên nếu không close.
// }
~~~

Service client SDK v2 được thiết kế để **tái sử dụng** khi cấu hình không đổi. Trong ứng dụng Spring Boot, thông thường tạo bean singleton hoặc factory/cache có vòng đời phù hợp; đóng client khi ApplicationContext dừng. Điều đó cho phép tận dụng connection pooling, giảm overhead TLS/DNS và kiểm soát tài nguyên.

**Chú ý quyền sở hữu transport:** nếu truyền một HTTP client **được xây dựng sẵn** bằng `.httpClient(existingClient)` vào nhiều service client, phải quản lý và đóng transport đó riêng theo lifecycle thích hợp; các service client không nhất thiết sở hữu việc đóng HTTP transport được chia sẻ. Với `.httpClientBuilder(...)`, SDK có thể xây/manage transport cho client theo hợp đồng của SDK. Không tạo hàng trăm client/transport bất đồng bộ với event loop riêng nếu có thể chia sẻ cấu hình.

### 5.2. Timeout theo nhiều tầng

~~~mermaid
flowchart TD
    CALL["Một lời gọi SDK"] --> TOTAL["apiCallTimeout: toàn bộ lời gọi"]
    TOTAL --> TRY["apiCallAttemptTimeout: từng attempt"]
    TRY --> CONN["connectionTimeout: thiết lập kết nối"]
    TRY --> IO["socket/read/write timeout: I/O transport"]
    TRY --> RETRY["Retry/backoff nếu retry strategy cho phép"]
    RETRY --> TRY
~~~

Timeout thực tế còn chịu ảnh hưởng của network, DNS, TLS, cơ chế retry, streaming, queueing trong connection pool và client/library cụ thể. Không hiểu `socketTimeout(15s)` là “toàn bộ upload luôn phải xong trong 15 giây” hoặc `apiCallTimeout(45s)` là SLA end-to-end của nghiệp vụ nếu service còn xử lý dữ liệu, gọi DB, ký file, gửi event.

## 6. Cấu hình HTTP client bất đồng bộ bằng Netty

Với một service publish nhiều sự kiện lên SQS, một `SqsAsyncClient` có thể sử dụng Netty NIO:

~~~java
import java.time.Duration;
import software.amazon.awssdk.core.client.config.ClientOverrideConfiguration;
import software.amazon.awssdk.http.nio.netty.NettyNioAsyncHttpClient;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.sqs.SqsAsyncClient;

public final class SqsAsyncClientFactory {
    public static SqsAsyncClient create() {
        return SqsAsyncClient.builder()
                .region(Region.AP_SOUTHEAST_1)
                .httpClientBuilder(NettyNioAsyncHttpClient.builder()
                        .maxConcurrency(64)
                        .connectionTimeout(Duration.ofSeconds(3))
                        .connectionAcquisitionTimeout(Duration.ofSeconds(5))
                        .readTimeout(Duration.ofSeconds(30))
                        .writeTimeout(Duration.ofSeconds(15)))
                .overrideConfiguration(ClientOverrideConfiguration.builder()
                        .apiCallTimeout(Duration.ofSeconds(45))
                        .build())
                .build();
    }
}
~~~

Ý nghĩa một số tham số:

| Tham số | Cần hiểu |
| --- | --- |
| `maxConcurrency` | Giới hạn số request đồng thời mà transport xử lý, không phải số message SQS được xử lý bởi nghiệp vụ |
| `connectionAcquisitionTimeout` | Thời gian chờ lấy connection từ pool; có thể tăng lỗi khi pool quá tải |
| `readTimeout` / `writeTimeout` | Giới hạn I/O ở Netty transport; không tự áp dụng cho toàn bộ retry |
| `apiCallTimeout` | Giới hạn thời gian tổng thể của lời gọi SDK, xét cơ chế retry |
| Số thread/event loop | Liên quan môi trường runtime và transport; cần đo lường khi có tải |

**Ví dụ SQS long polling:** nếu consumer dùng `ReceiveMessage` với `WaitTimeSeconds` lớn, thiết lập HTTP read timeout/API timeout phải đủ cho thời gian chờ của long poll **cộng thêm network overhead**. Một read timeout ngắn hơn `WaitTimeSeconds` có thể gây lỗi lặp lại dù queue hoạt động bình thường.

Với `@SqsListener` của AWSpring, số listener container, concurrency, tốc độ xử lý handler, visibility timeout và acknowledgement cũng ảnh hưởng throughput. Chỉ tăng `maxConcurrency` của Netty **không** tự giải quyết được backlog nếu business handler quá chậm.

### 6.1. Async không có nghĩa là vô hạn đồng thời

Nếu producer nhận 50.000 message/giây nhưng application phát ra hàng nghìn `CompletableFuture` mà không có cơ chế backpressure/batching/giới hạn concurrent requests, bộ nhớ và pool có thể quá tải. Cần phối hợp:

- Backpressure hoặc rate limiting tại tầng nghiệp vụ.
- Batch SQS khi phù hợp semantics và size limit của API.
- Retry có giới hạn và jitter, tránh đẩy tải trở lại đồng loạt.
- Metric connection acquisition timeout, latency và SQS throttling.
- Idempotency cho side effect vì request có thể thành công ở AWS dù client không nhận được response.

## 7. Retry, timeout và lỗi mạng: thiết kế theo loại operation

AWS SDK v2 hỗ trợ retry strategy và cấu hình timeout ở client. Mặc định retry có thể khác theo phiên bản/mode; không nên ghi cứng giả định số lần retry khi chưa xem cấu hình thực tế.

### 7.1. Những nguyên nhân khiến SDK retry

Trong phạm vi retry strategy và service semantics, SDK có thể thử lại request khi gặp các lỗi tạm thời như throttling hoặc một số lỗi network/server phù hợp. Nhưng:

- **Không phải lỗi nào cũng retry được.** `AccessDenied` do IAM thiếu quyền thường không được giải quyết bằng retry.
- **Không phải payload nào cũng replay an toàn.** Với streaming upload, cần bảo đảm request body/stream có thể được thử lại theo SDK và transport đang dùng.
- **Không phải operation nào cũng idempotent.** Nếu request tạo side effect và response bị mất, thử lại có thể tạo tác động trùng; phải xem API và khóa idempotency theo dịch vụ.
- **Retry làm tăng latency và tải.** Timeout quá dài cộng retry nhiều lần có thể vượt SLA nghiệp vụ.

### 7.2. Không nhầm các mức timeout

| Mức | Đặt ở đâu? | Ví dụ lỗi |
| --- | --- | --- |
| Kết nối TCP/TLS | HTTP transport | Endpoint không reachable, proxy/firewall, handshake lỗi |
| Chờ pool | HTTP transport, nhất là async | `connectionAcquisitionTimeout` |
| Read/write | HTTP transport | Server chậm, long polling, streaming |
| Một request attempt | SDK client override | Một lần gửi API vượt giới hạn |
| Toàn bộ SDK API call | SDK client override | Hết thời gian kể cả retry |
| Toàn bộ HTTP request của người dùng | Spring MVC/WebFlux hoặc gateway | Controller/gateway timeout dù AWS SDK vẫn chạy |
| Xử lý message | SQS listener/queue | Visibility timeout, redelivery, DLQ |

Hãy xác định SLA nghiệp vụ trước, sau đó phân bổ timeout ở những tầng phù hợp. Thời hạn tổng có thể phải tính cả truy cập database, chuyển đổi payload, lưu file, gọi S3/SQS và thời gian xử lý hậu kỳ.

### 7.3. Không dùng retry để che lỗi cấu hình

Nếu `S3Client` gọi sai endpoint, chứng chỉ TLS không hợp lệ hoặc resource nằm sai region, tăng số retry chỉ làm chậm quá trình xác nhận lỗi. Đối với 403 IAM hoặc SQS `QueueDoesNotExist`, trước tiên kiểm tra identity, region, ARN, queue URL và resource policy.

## 8. Region, endpoint và AWS request signing là ba khái niệm riêng

### 8.1. Region

`Region` là vùng AWS mà client hướng tới, ví dụ `ap-southeast-1`. Khi không chỉ định trên builder, SDK có thể dùng region provider chain (Java system property `aws.region`, environment `AWS_REGION`, shared profile, một số metadata môi trường theo thứ tự của SDK v2).

### 8.2. Endpoint

Endpoint là địa chỉ mạng mà request được gửi đến. Với cấu hình mặc định, SDK giải quyết endpoint của service theo region và các yếu tố khác. Chẳng hạn endpoint của SQS, STS, DynamoDB và S3 có thể được xây dựng theo quy tắc khác nhau.

`endpointOverride(URI)` yêu cầu SDK hướng tới một URL cụ thể, thường dùng trong test hoặc khi cần endpoint đã được kiểm soát. **Endpoint override không tự đặt region, không tạo credential và không bỏ qua việc ký request.**

### 8.3. Signing

AWS SDK thường ký request theo AWS Signature Version 4 hoặc cơ chế ký phù hợp với dịch vụ. Region/endpoint có thể tham gia vào phạm vi ký và định tuyến request. Nếu endpoint override trỏ sai vùng nhưng client ký theo region khác, request AWS thật có thể gặp signature mismatch, redirect hoặc lỗi service-specific.

**Ví dụ:** set `region(Region.US_EAST_1)` cho `S3Client` nhưng bucket thực ở Singapore. Dù credential đúng và endpoint có thể phân giải, request có nguy cơ lỗi/redirect do vùng bucket. Cần xác định region của tài nguyên, không chọn theo vị trí máy developer.

~~~mermaid
flowchart LR
    I["Credentials provider: role"] --> S["Request signing"]
    R["Region của client"] --> E["Endpoint resolver"]
    R --> S
    E --> H["URL / Host"]
    H --> S
    S --> T["HTTP transport"]
    T --> A["AWS service / test endpoint"]
~~~

## 9. Endpoint mặc định, endpoint override và DNS riêng

### 9.1. Ưu tiên cơ chế chuẩn của AWS trên production

Trong production, thông thường hãy đặt **region đúng** và để SDK dùng endpoint chuẩn của AWS:

~~~java
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.sqs.SqsAsyncClient;

SqsAsyncClient sqs = SqsAsyncClient.builder()
        .region(Region.AP_SOUTHEAST_1)
        .build();
~~~

Nếu hạ tầng dùng **VPC endpoint/private DNS**, nhiều trường hợp SDK vẫn dùng hostname tiêu chuẩn và DNS/route của VPC đưa traffic qua endpoint riêng. Vì thế **không mặc định phải dùng `endpointOverride(...)` chỉ vì có VPC endpoint**. Hãy kiểm tra loại endpoint, private DNS, route, security group và VPC endpoint policy của dịch vụ tương ứng.

### 9.2. Endpoint override cho local test

Một client test dùng giả lập S3:

~~~java
import java.net.URI;
import software.amazon.awssdk.auth.credentials.AwsBasicCredentials;
import software.amazon.awssdk.auth.credentials.StaticCredentialsProvider;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.S3Configuration;

S3Client localS3 = S3Client.builder()
        .region(Region.US_EAST_1)
        .endpointOverride(URI.create("http://localhost:4566"))
        .credentialsProvider(StaticCredentialsProvider.create(
                AwsBasicCredentials.create("test", "test")))
        .serviceConfiguration(S3Configuration.builder()
                .pathStyleAccessEnabled(true)
                .build())
        .build();
~~~

Các credential `test/test` là **giả và chỉ dùng trong test**, không thể dùng thay IAM role production. Khi test thực tế, hãy lấy URL từ container/emulator đã khởi động; `localhost:4566` chỉ đúng khi client chạy cùng network namespace/máy và emulator đang lắng nghe cổng đó.

### 9.3. Endpoint override không phải URL tài nguyên nghiệp vụ

`SqsAsyncClient.endpointOverride(...)` xác định endpoint của **dịch vụ SQS**. Còn `SendMessageRequest.queueUrl(...)` xác định **queue đích**. Tương tự, `S3Client.endpointOverride(...)` không thay `bucket(...)` và `key(...)`.

Sai lầm phổ biến:

- Đặt queue URL của một queue cụ thể làm endpoint base của SQS client.
- Dùng endpoint override đến LocalStack trong production.
- Đặt region ngẫu nhiên rồi trông đợi endpoint override khắc phục mọi lỗi chữ ký.
- Bỏ qua TLS certificate/hostname verification để “sửa” lỗi endpoint.
- Tạo endpoint riêng cho mỗi request thay vì dùng client cấu hình theo môi trường.

### 9.4. HTTP và HTTPS

Khi gọi AWS thật, **HTTPS/TLS** là đường mặc định cần bảo vệ. Endpoint `http://...` trong ví dụ LocalStack chỉ phù hợp emulator local hoặc môi trường giả lập được cô lập. Không vô hiệu hóa xác thực TLS hoặc bỏ qua certificate verification để kết nối production.

Với endpoint private hoặc proxy TLS của tổ chức, phải quản lý certificate trust chain, hostname và proxy bằng cấu hình bảo mật được phê duyệt. Không triển khai một `TrustAllCertificates` vào production.

## 10. Đặc thù S3: virtual-hosted và path-style access

S3 hỗ trợ nhiều cách thể hiện bucket trong HTTP request. Hai cách thông dụng:

| Chế độ | Ví dụ URL minh họa | Ý nghĩa |
| --- | --- | --- |
| Virtual-hosted style | `https://example-bucket.s3.ap-southeast-1.amazonaws.com/key` | Tên bucket nằm trong hostname |
| Path-style | `https://s3.ap-southeast-1.amazonaws.com/example-bucket/key` | Tên bucket nằm trong path |

SDK S3 tự áp các quy tắc endpoint và kiểu addressing theo dịch vụ, bucket và cấu hình. **Không bật path-style cho toàn bộ môi trường sản xuất chỉ vì LocalStack yêu cầu**.

### 10.1. Khi nào cần path-style?

Với nhiều S3 emulator hoặc endpoint thử nghiệm như `http://localhost:4566`, virtual-hosted style có thể tạo hostname dạng `bucket.localhost` mà DNS không phân giải phù hợp. Khi đó cấu hình:

~~~java
S3Configuration s3Configuration = S3Configuration.builder()
        .pathStyleAccessEnabled(true)
        .build();
~~~

và truyền vào builder:

~~~java
S3Client client = S3Client.builder()
        .region(Region.US_EAST_1)
        .endpointOverride(URI.create("http://localhost:4566"))
        .serviceConfiguration(s3Configuration)
        .build();
~~~

Đoạn thứ hai giả định client đã có source credentials phù hợp với môi trường test; trong ví dụ test hoàn chỉnh phải đặt static **dummy** credentials tường minh.

### 10.2. Những tính năng S3 cần endpoint rules đặc thù

Khi dùng các tính năng như access points, S3 Transfer Acceleration, dual-stack, Multi-Region Access Points, S3 Express One Zone hoặc ARN dạng đặc biệt, endpoint/signing có thể theo quy tắc riêng và cần loại client/hỗ trợ SDK tương ứng.

Do đó, **endpointOverride toàn cục** có thể làm mất một số hành vi endpoint resolution của S3. Trước khi đặt custom endpoint, đọc hướng dẫn của chính tính năng và SDK release; kiểm thử từng operation mục tiêu thay vì suy ra từ `PutObject` đơn giản.

### 10.3. Region của S3 bucket

Tên bucket có thể tồn tại duy nhất trong phạm vi partition theo quy tắc dịch vụ, nhưng operation S3 vẫn chịu ảnh hưởng từ vùng bucket và endpoint. Nếu một ứng dụng dùng bucket ở nhiều region, nên quản lý client theo **vùng tài nguyên** hoặc cơ chế SDK phù hợp; không thay đổi biến `AWS_REGION` toàn process rồi kỳ vọng client đã tạo sẽ tự đổi region.

## 11. Đặc thù SQS: client endpoint, queue URL và long polling

SQS queue URL thường bao gồm region, account ID và tên queue. Ví dụ minh họa:

~~~text
https://sqs.ap-southeast-1.amazonaws.com/111122223333/order-events-dev
~~~

Khi gọi SQS:

~~~java
import software.amazon.awssdk.services.sqs.SqsAsyncClient;

public class OrderQueueSender {
    private final SqsAsyncClient sqs;
    private final String queueUrl;

    public OrderQueueSender(SqsAsyncClient sqs, String queueUrl) {
        this.sqs = sqs;
        this.queueUrl = queueUrl;
    }

    public void send(String payload) {
        sqs.sendMessage(request -> request
                .queueUrl(queueUrl)
                .messageBody(payload))
            .join();
    }
}
~~~

`join()` chỉ minh họa việc chờ kết quả trong một ví dụ ngắn; trong code async thực tế, nên trả future hoặc xử lý completion không blocking theo kiến trúc của service.

Nếu region của `SqsAsyncClient` không trùng region queue, SDK hoặc service có thể trả lỗi endpoint/queue/authorization tùy request. **Không trỏ client tới một region và queue URL của region khác mà chưa kiểm thử hành vi cụ thể.**

### 11.1. Long polling và timeout HTTP

Khi sử dụng `ReceiveMessage` với `waitTimeSeconds(20)`, server có thể đợi tối đa khoảng 20 giây trước khi trả message hoặc response rỗng theo đặc tính SQS. Cấu hình read timeout và API attempt timeout cần **lớn hơn khoảng đợi này cộng network overhead**. Nếu quá ngắn, consumer liên tục timeout, retry và gây tải không cần thiết.

Trong Spring Cloud AWS SQS listener, cấu hình polling, concurrency, acknowledgement, visibility timeout và DLQ cần được đánh giá cùng HTTP transport. Thay đổi `maxConcurrency` của Netty không tự thay đổi mức độ song song của business handler hoặc giới hạn queue.

### 11.2. LocalStack SQS: queue URL phải tương thích endpoint test

Với emulator, `CreateQueue`/`GetQueueUrl` có thể trả một queue URL phụ thuộc cách emulator tạo hostname và network. Đảm bảo URL được dùng ở client tương thích với endpoint test và môi trường chạy (host vs container); không copy queue URL production vào test hoặc ngược lại.

Một cách kiểm thử đáng tin cậy là tạo queue trong setup test, lấy queue URL từ chính endpoint test và truyền nó cho handler/publisher trong context test.

## 12. Tích hợp với Spring Boot và Spring Cloud AWS

### 12.1. Khi nào để AWSpring auto-configure?

Nếu ứng dụng chỉ có **một vùng** và sử dụng một bộ credential/endpoint chuẩn cho service, để AWSpring tạo bean thường giúp giảm code:

- Thêm starter AWSpring cần thiết, ví dụ S3/SQS.
- Khai báo region/credential bằng nguồn môi trường phù hợp.
- Inject `S3Template`, `SqsTemplate` hoặc SDK client do auto-configuration cung cấp tùy release.
- Để SDK default credential chain nhận role từ ECS/EKS/EC2 hoặc profile dev.
- Kiểm tra tài liệu auto-configuration của AWSpring để biết property, client bean và customization hook được hỗ trợ.

Ví dụ cấu hình vùng với các release AWSpring 3.x phổ biến:

~~~yaml
spring:
  cloud:
    aws:
      region:
        static: ${AWS_REGION}

app:
  aws:
    s3:
      bucket: ${APP_S3_BUCKET}
    sqs:
      queue-url: ${APP_SQS_QUEUE_URL}
~~~

Đây là **cấu hình minh họa**, không chứa static access key. `AWS_REGION`, bucket và queue URL là cấu hình phải được môi trường deploy cung cấp. Cấu hình Spring Cloud AWS và client code có thể ghi đè một phần default SDK behavior; cần xem bean thực tế trước khi kết luận.

### 12.2. Vì sao không đặt một endpoint cho mọi dịch vụ?

S3, SQS, DynamoDB và STS có endpoint resolution, API operation và đặc điểm network riêng. Nếu test S3 qua emulator nhưng SQS cần dùng AWS staging thật, áp global endpoint override cho tất cả client có thể chuyển nhầm request, dẫn tới lỗi network hoặc side effect sai môi trường.

Tùy release, AWSpring có thể cung cấp **property endpoint theo dịch vụ** hoặc điểm tùy chỉnh client builder riêng. Hãy kiểm tra tên property và ưu tiên cấu hình trong reference guide đúng phiên bản; không tự giả định `spring.cloud.aws.endpoint` hoặc một tên property bất kỳ sẽ phù hợp với mọi starter.

Một cấu hình ứng dụng ở tầng riêng có thể phân tách:

~~~yaml
app:
  aws:
    archive:
      region: ${APP_ARCHIVE_REGION:ap-southeast-1}
      bucket: ${APP_ARCHIVE_BUCKET}
    events:
      region: ${APP_EVENTS_REGION:ap-southeast-1}
      queue-url: ${APP_EVENTS_QUEUE_URL}
~~~

Cách tổ chức này tách vùng/tài nguyên theo use case. Adapter tự chọn client đúng và hạn chế lỗi dùng bucket/queue của môi trường khác.

### 12.3. Tự tạo bean service client được đặt tên

Khi cần client S3 **riêng** cho một bucket lưu trữ/archive, có thể tạo bean được đặt tên:

~~~java
import java.time.Duration;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import software.amazon.awssdk.core.client.config.ClientOverrideConfiguration;
import software.amazon.awssdk.http.apache.ApacheHttpClient;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;

@Configuration(proxyBeanMethods = false)
public class ArchiveS3Configuration {

    @Bean(name = "archiveS3Client", destroyMethod = "close")
    S3Client archiveS3Client(
            @Value("${app.aws.archive.region}") String region) {

        return S3Client.builder()
                .region(Region.of(region))
                .httpClientBuilder(ApacheHttpClient.builder()
                        .maxConnections(40)
                        .connectionTimeout(Duration.ofSeconds(3)))
                .overrideConfiguration(ClientOverrideConfiguration.builder()
                        .apiCallTimeout(Duration.ofSeconds(40))
                        .build())
                .build();
    }
}
~~~

Tại adapter, inject bằng qualifier để biết chính xác client được dùng:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;
import software.amazon.awssdk.services.s3.S3Client;

@Service
public class ArchiveMetadataReader {

    private final S3Client archiveS3;

    public ArchiveMetadataReader(
            @Qualifier("archiveS3Client") S3Client archiveS3) {
        this.archiveS3 = archiveS3;
    }

    public long getSize(String bucket, String key) {
        return archiveS3.headObject(request -> request
                .bucket(bucket)
                .key(key))
            .contentLength();
    }
}
~~~

**Tương tác với auto-configuration rất quan trọng:** một bean `S3Client` do bạn tự khai báo có thể khiến auto-configuration AWSpring **back off** hoặc chọn cách wiring khác tùy version và điều kiện. Nếu app cần cả default client cho `S3Template` và `archiveS3Client` riêng, phải cấu hình rõ client/template sử dụng bean nào và kiểm thử context; không mặc định tên bean khác là đủ để giữ nguyên bean default.

Bài toán có nhiều region, role hoặc endpoint nên dùng adapter/factory có định nghĩa sở hữu rõ ràng, thay vì để một bean global ngầm được sử dụng cho mọi tài nguyên.

### 12.4. Những cấu hình nên tách theo môi trường

| Mục | Local test | Staging/production |
| --- | --- | --- |
| Credentials | Credential giả khi dùng emulator; AWS profile khi gọi sandbox thật | IAM role/workload identity |
| Region | Region test chỉ định rõ | Region tài nguyên thật |
| Endpoint | Emulator/test endpoint được cấp từ test runtime | Endpoint mặc định AWS hoặc endpoint private được cấu hình có chủ đích |
| HTTP transport | Cấu hình đủ tái lập, không yêu cầu throughput quá lớn | Tuning sau khi đo tải/latency |
| Timeout/retry | Thấp hơn và dễ chẩn đoán trong test phù hợp | Theo SLA, long polling, side effect và throughput |
| Resource | Bucket/queue test tách biệt | ARN, tên tài nguyên và account/region theo môi trường |

## 13. HTTP proxy, TLS và VPC endpoints

Trong doanh nghiệp, egress traffic có thể đi qua proxy hoặc VPC endpoint. Cần phân biệt **URL của AWS service** với **đường mạng đi tới URL đó**.

### 13.1. Khi nào cần proxy?

Nếu máy developer hoặc container trong mạng doanh nghiệp phải đi qua HTTP proxy, hãy cấu hình proxy theo transport đang dùng (Apache, Netty hoặc cơ chế HTTP client tương ứng), cùng no-proxy rules khi thích hợp.

Một số transport hỗ trợ `ProxyConfiguration` riêng; các thiết lập host, scheme, user/password và TLS phải theo hướng dẫn của phiên bản SDK. Không đặt username/password proxy trong source hay log.

Khi lỗi qua proxy, kiểm tra:

1. DNS và khả năng kết nối từ chính process/container.
2. Proxy URL và no-proxy domains.
3. TLS root CA/hostname verification của đường đi đang sử dụng.
4. Region/endpoint/signing của client.
5. Quyền IAM chỉ sau khi biết request tới được dịch vụ AWS.

### 13.2. VPC endpoint

**VPC Gateway Endpoint** cho một số dịch vụ (như S3/DynamoDB trong cấu hình hỗ trợ) và **Interface Endpoint/PrivateLink** cho các dịch vụ tương ứng giúp network traffic có đường riêng tới dịch vụ AWS.

Có VPC endpoint không nghĩa là toàn bộ service request tự được cho phép: security group, route table, endpoint policy, DNS/private DNS và IAM vẫn có vai trò. Không sửa `AccessDenied` do endpoint policy bằng cách dùng static credentials khác.

Nếu private DNS đã định tuyến hostname chuẩn của service vào endpoint, client SDK có thể tiếp tục dùng region và endpoint mặc định. Chỉ dùng `endpointOverride(...)` khi yêu cầu network/endpoint đã được xác định rõ.

### 13.3. TLS và kiểm soát chứng chỉ

Không vô hiệu hóa kiểm tra TLS trong production. Khi dùng certificate nội bộ hoặc proxy terminate TLS, cần cấp trust store đúng và xác minh hostname/certificate chain. Dữ liệu nhạy cảm như secret, credentials và payload cá nhân không nên bị ghi vào wire logs.

## 14. Kiểm thử cấu hình client và endpoint

Một bài test hiệu quả nên tách **test logic**, **test wiring HTTP** và **test hành vi AWS thật**.

### 14.1. Unit test: mock/fake ở adapter

Service nghiệp vụ phụ thuộc một interface như `DocumentStore` hoặc `EventPublisher`. Unit test fake adapter để xác nhận logic, xử lý response/exception và idempotency, không cần AWS credential hoặc network.

### 14.2. Integration test: LocalStack và endpoint theo vòng đời test

Với Testcontainers/LocalStack hoặc emulator phù hợp:

1. Tạo endpoint test khi container đã khởi động; dùng mapped host/port đúng của môi trường chạy.
2. Xây client test với endpoint override, region cụ thể và **credential giả** chỉ trong test.
3. Với S3 emulator, dùng path-style nếu hostname của emulator không hỗ trợ virtual-hosted style.
4. Tạo bucket/queue test, thực hiện Put/Get hoặc Send/Receive rồi dọn dữ liệu.
5. Kiểm tra bean/template/listener Spring đang sử dụng **chính client test**.

Một factory test gọn:

~~~java
import java.net.URI;
import software.amazon.awssdk.auth.credentials.AwsBasicCredentials;
import software.amazon.awssdk.auth.credentials.StaticCredentialsProvider;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.S3Configuration;

public final class TestS3ClientFactory {
    public static S3Client create(URI endpoint) {
        return S3Client.builder()
                .endpointOverride(endpoint)
                .region(Region.US_EAST_1)
                .credentialsProvider(StaticCredentialsProvider.create(
                        AwsBasicCredentials.create("test", "test")))
                .serviceConfiguration(S3Configuration.builder()
                        .pathStyleAccessEnabled(true)
                        .build())
                .build();
    }
}
~~~

**Giới hạn:** LocalStack không thể đại diện đầy đủ cho IAM role trust, SCP/KMS, mọi tính năng endpoint, network VPC hoặc quota/throttling thực tế của AWS. Không suy từ test emulator thành “IAM production đúng”.

### 14.3. Integration/smoke test trên tài khoản AWS sandbox

Trên tài khoản AWS test có quyền giới hạn:

- Dùng role của **chính workload** chạy test (ECS task role, EKS Pod Identity/IRSA, EC2 instance profile, CI OIDC).
- Xác nhận account và principal qua STS `GetCallerIdentity` nếu có thể; đối chiếu region/endpoint/resource.
- Thực hiện request S3/SQS nhỏ và kiểm tra response, latency, retry/throttling.
- Quan sát kết nối khi bật proxy, VPC endpoint hoặc custom trust store.
- Với SQS, kiểm tra long polling và visibility timeout; với S3, kiểm tra object size, metadata, mã hóa/KMS và streaming nếu có.
- Chặn các thao tác ghi vào production bằng IAM/resource policy và kiểm tra account/region allowlist.

Một smoke test bằng profile của laptop **không chứng minh** ECS/EKS runtime đang dùng role mong muốn.

## 15. Chẩn đoán sự cố theo triệu chứng

| Triệu chứng | Tầng cần ưu tiên kiểm tra | Bước xác minh |
| --- | --- | --- |
| `NoClassDefFoundError` cho Apache/Netty transport | Dependency/runtime classpath | BOM, SDK module, `runtimeClasspath` |
| Client khởi tạo nhưng không tìm credentials | Identity provider | Role ECS/EKS/EC2, profile local, provider chain |
| `Unable to load region` | Region | `aws.region`, `AWS_REGION`, profile, builder, AWSpring properties |
| DNS không phân giải bucket emulator | S3 endpoint resolution | Path-style, host mapping, endpoint override |
| `UnknownHostException` / connection refused | Network/endpoint | URL, host/port, container network, DNS, proxy |
| TLS handshake/certificate failure | TLS/HTTP transport | Trust store, endpoint hostname, proxy, CA |
| `SignatureDoesNotMatch` | Signing/region/endpoint/clock/credential | Vùng ký, endpoint, thời gian hệ thống, loại credential |
| `AccessDenied` từ S3/SQS | IAM/resource/KMS policy | Principal STS, action, ARN, policy/condition |
| SQS `QueueDoesNotExist` | Queue URL/region/account | Queue thật, region của client, queue URL và IAM |
| SQS long polling liên tục timeout | Read/API timeout | `waitTimeSeconds`, Netty read timeout, API call attempt |
| Connection pool timeout | HTTP transport/concurrency | Pool capacity, `maxConcurrency`, backpressure, connection acquisition |
| Upload S3 lớn bị ngắt | Streaming/timeout/memory | API call timeout, body replay, HTTP transport, multipart strategy |
| LocalStack test pass, production fail | Sự khác biệt emulator/AWS | IAM, KMS, VPC endpoint, real region/service behavior |

Không thay nhiều tham số timeout/proxy/region/credentials cùng lúc khi debug: mỗi thay đổi sẽ làm mất khả năng kết luận nguyên nhân.

### 15.1. Quan sát vận hành

Nên theo dõi:

- Latency theo service operation, status/error code và retry count.
- Thời gian chờ connection pool, số request concurrent, timeout rate.
- SQS backlog, processing duration, visibility timeout và DLQ depth.
- S3 upload/download throughput, kích thước payload, lỗi streaming và lỗi KMS.
- Region/endpoint **loại môi trường** (không log secret, session token hoặc toàn bộ dữ liệu nhạy cảm).
- Tương quan giữa request người dùng, AWS request ID và trace/correlation ID.

AWS SDK và HTTP client có thể cung cấp metric/diagnostic qua cơ chế tùy phiên bản. Tích hợp với Micrometer/observability cần được làm có chủ đích, tránh bật body logging chứa payload nhạy cảm.

## 16. Thực hành: thiết kế client cho một ứng dụng đa dịch vụ

**Tình huống:** Dịch vụ Spring Boot `document-api`:

- Upload tài liệu vào bucket S3 tại `ap-southeast-1`.
- Publish event vào queue SQS tại cùng region.
- Đọc secret từ Secrets Manager khi startup hoặc khi cần.
- Chạy local với LocalStack cho S3/SQS, nhưng staging/production gọi AWS thật bằng IAM role.
- Có hai workload: API đồng bộ số lượng request vừa phải và worker xử lý queue với lưu lượng lớn.

### Nhiệm vụ A — Chọn client/transport

1. Lựa chọn `S3Client` hay `S3AsyncClient` cho upload theo kích thước file, mô hình server và concurrency; giải thích trade-off.
2. Lựa chọn `SqsAsyncClient` cho publisher/worker nếu phù hợp; đề xuất mức `maxConcurrency` ban đầu và **cách đo lại** thay vì tuyên bố một giá trị tối ưu cố định.
3. Chọn Apache hoặc URLConnection cho sync client; Netty cho async client; giải thích tác động dependency và lifecycle.
4. Liệt kê những thông số tối thiểu cần theo dõi: connection timeout, read timeout, API call attempt/total, retry count.

### Nhiệm vụ B — Cấu hình Spring và endpoint

1. Tạo property `app.aws.s3.region`, `app.aws.s3.bucket`, `app.aws.sqs.region`, `app.aws.sqs.queue-url`.
2. Với production, đặt region thật và để SDK dùng endpoint tiêu chuẩn trừ khi VPC endpoint/custom URL có yêu cầu cụ thể.
3. Với LocalStack, override endpoint từng service trong phạm vi test; set fake credentials và S3 path-style.
4. Đảm bảo context Spring inject đúng bean client vào S3 adapter và SQS listener; kiểm tra tác động của custom bean đến auto-configuration AWSpring.

### Nhiệm vụ C — Sự cố thực tế

| Sự cố | Cần phân tích |
| --- | --- |
| S3 test lỗi DNS với bucket hostname | Virtual-hosted style đang trỏ tới host nào? Có cần path-style và host mapping? |
| SQS receive long polling timeout sau 5 giây | `WaitTimeSeconds` và HTTP read/API timeout có mâu thuẫn? |
| Application bị `AccessDenied` dù endpoint reach được | Principal IAM nào đang ký request, action/ARN/resource policy/KMS nào liên quan? |
| Trong ECS, client gọi lại `localhost:4566` | Config endpoint test đã lọt vào production bằng đường nào? |
| Tăng pool từ 50 lên 500 không tăng throughput | Handler/CPU/DB/SQS throttling/backpressure ở đâu? |
| Upload 200 MB fail dù `PutObject` nhỏ hoạt động | Request body, streaming, multipart, timeout và memory footprint ra sao? |

### Nhiệm vụ D — Kiểm thử

- Unit test adapter, mock lỗi AWS SDK.
- Integration test qua LocalStack cho S3/SQS với test-only endpoint và credential.
- Smoke test sandbox với role, region và resource ARN đúng.
- Load test có kiểm soát đo pool, concurrency, timeout, retry và memory.
- Kiểm thử lỗi TLS/proxy/network và đảm bảo logs không chứa key hoặc token.

**Tiêu chí đạt:** Bài làm tách được client service với HTTP transport, chỉ rõ endpoint/region/credential, phân biệt blocking/async, nêu cách triển khai bean trong Spring và có căn cứ đo lường để chọn timeout/pool. Quan trọng nhất: local test không được phép làm thay đổi tài nguyên production.

## 17. So sánh khái niệm với Azure và Google Cloud

Trong module tích hợp đa cloud, cả AWS, Azure và Google Cloud đều có SDK client kết nối tới dịch vụ managed, nhưng cơ chế xác định endpoint và HTTP pipeline khác nhau.

| Nhu cầu | AWS | Azure | Google Cloud |
| --- | --- | --- | --- |
| SDK client | `S3Client`, `SqsAsyncClient`, `DynamoDbClient` | Azure SDK clients như Blob/Queue/Service Bus clients theo dịch vụ | Google Cloud Java clients như Storage, Pub/Sub theo dịch vụ |
| Credentials mặc định | `DefaultCredentialsProvider` và IAM role/STS | Azure credential chain/Managed Identity tùy client | Application Default Credentials và service account/workload identity |
| HTTP transport | Apache, URLConnection, Netty, CRT tùy kiểu SDK client | Pipeline/HTTP client options của Azure SDK | HTTP/gRPC transports tùy thư viện dịch vụ |
| Resource endpoint | Region và service endpoint; S3 có addressing rules | URL resource, service endpoint và region theo dịch vụ | Project/location và service endpoints theo dịch vụ |
| Test emulator | LocalStack hoặc emulator phù hợp | Azurite hoặc emulator của service phù hợp | Emulator của từng dịch vụ (ví dụ Pub/Sub emulator) khi có |

Sự tương đồng là cần quản lý **identity, endpoint, transport, timeout và retry**. Không thể sao chép trực tiếp `endpointOverride(...)` của AWS sang mọi Azure/GCP client; phải tuân thủ API, auth và semantics của SDK tương ứng.

## 18. Ghi nhớ

Khi tích hợp Spring Boot với AWS, hãy cấu hình theo trật tự:

1. Xác định **dịch vụ và loại client** (blocking hay async).
2. Chọn **region**, **credential provider** và cơ chế IAM phù hợp môi trường.
3. Để **endpoint resolver chuẩn của SDK** làm việc trên production, chỉ override khi có yêu cầu kiểm chứng.
4. Chọn **HTTP transport**, timeout, pool và retry theo đặc tính request và kết quả đo.
5. Quản lý **client lifecycle** trong Spring, tránh vô tình thay bean auto-configuration của AWSpring.
6. Kiểm thử riêng **wiring/endpoint**, **IAM/KMS/network thật** và **performance**.

**AWSpring** hỗ trợ mô hình lập trình Spring; **AWS SDK for Java 2.x** cung cấp service clients và HTTP transports; **AWS** thực thi định tuyến, xác thực, IAM, quota và hành vi dịch vụ. Tùy chỉnh client theo đúng dịch vụ, thay vì áp một cấu hình cho mọi request, giúp ứng dụng hoạt động ổn định và dễ chẩn đoán khi mở rộng sang S3, SQS, dữ liệu, secrets và kiến trúc đa cloud.
