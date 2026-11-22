# Quản lý vòng đời clients, channels và thread pools

Một ứng dụng Java/Spring chạy trên Google Cloud thường gọi nhiều dịch vụ: đọc secret từ Secret Manager, tải tệp Cloud Storage, truy vấn BigQuery, gửi thông điệp Pub/Sub và gọi các dịch vụ gRPC nội bộ. Nếu mỗi HTTP request lại tạo một Google Cloud client hoặc một gRPC channel mới, ứng dụng sẽ tốn thời gian khởi tạo, mở thêm kết nối và sinh các thread nền không cần thiết. Ngược lại, nếu client dùng chung bị đóng quá sớm hoặc thread pool không có giới hạn, request đang chạy có thể thất bại, bộ nhớ tăng và shutdown có thể làm mất công việc chưa hoàn tất.

Quản lý vòng đời nghĩa là xác định **khi nào tài nguyên được tạo, ai sở hữu, có thể dùng chung ra sao và khi nào phải dừng**. Trong hệ thống Spring trên GCP, những quyết định này ảnh hưởng trực tiếp đến latency, concurrency, chi phí, độ tin cậy và khả năng khôi phục khi Cloud Run, GKE hoặc Compute Engine khởi động và kết thúc instance.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt Google Cloud client, gRPC channel, stub, executor và kết nối mạng.
- Chọn phạm vi sống phù hợp: mỗi request, mỗi bean singleton hoặc mỗi tiến trình.
- Tạo client dùng chung bằng Spring Dependency Injection và đóng đúng lúc ứng dụng dừng.
- Quản lý gRPC ManagedChannel, deadline và thứ tự shutdown giữa stub, client và executor.
- Cấu hình thread pool có giới hạn, hàng đợi và chính sách từ chối công việc.
- Tổ chức lifecycle cho Pub/Sub Publisher và Subscriber, bao gồm flush và dừng nhận message.
- Thiết kế graceful shutdown phù hợp với Cloud Run và GKE.
- Theo dõi thread, queue, connection, latency và dấu hiệu resource leak.
- Xử lý tình huống quá tải bằng backpressure, timeout và giới hạn concurrency.

## 1. Những tài nguyên Java nào có vòng đời?

Một lời gọi API tưởng như đơn giản có thể đi qua nhiều lớp:

~~~text
Spring Controller / Service
          |
          v
Google Cloud client hoặc gRPC stub
          |
          v
Transport / ManagedChannel
          |
          +--> TLS, HTTP/2, connection, keepalive
          |
          +--> callback executor, retry executor
          |
          +--> background threads
          |
          v
Google Cloud API hoặc service nội bộ
~~~

Không phải mọi thư viện đều có cùng cấu trúc. Một số client dùng gRPC và Google API Client Libraries (GAPIC/GAX), một số dùng HTTP/REST và transport riêng. Vì vậy, phải kiểm tra hợp đồng vòng đời của đúng thư viện và phiên bản đang sử dụng.

| Tài nguyên | Vai trò | Vòng đời thường dùng |
|---|---|---|
| Google Cloud API client | Đóng gói API và transport | Dùng chung trong ứng dụng hoặc theo cấu hình rõ ràng |
| ManagedChannel | Quản lý kết nối gRPC | Dùng chung giữa nhiều RPC và stub |
| gRPC stub | Giao diện gọi RPC, mang tùy chọn như deadline | Thường tạo rẻ và có thể dẫn xuất từ channel dùng chung |
| ExecutorService | Chạy tác vụ Java và callback | Dùng chung, có giới hạn, do owner đóng |
| ScheduledExecutorService | Retry, timeout, lịch tác vụ | Dùng chung theo nhu cầu và đóng khi kết thúc |
| Pub/Sub Publisher | Batch, retry và phát thông điệp | Dùng chung theo topic/cấu hình |
| Pub/Sub Subscriber | Streaming pull, dispatch và ack message | Một worker có vòng đời start/stop rõ ràng |
| HTTP connection pool | Tái sử dụng kết nối HTTP | Do HTTP client hoặc framework quản lý |
| ThreadLocal / MDC | Giữ ngữ cảnh theo thread | Cần dọn sau tác vụ để tránh rò rỉ ngữ cảnh |

Sự khác nhau quan trọng nhất là **ownership**: đối tượng nào tạo ra tài nguyên hoặc được giao quản lý vòng đời thì đối tượng đó chịu trách nhiệm đóng. Code sử dụng client đã được Spring inject không được tự ý đóng client sau mỗi request.

## 2. Phân biệt client, channel và stub

### Client

Client là đối tượng cấp cao cung cấp phương thức gọi API. Ví dụ, SecretManagerServiceClient có các thao tác như truy cập phiên bản secret. Client có thể tự tạo transport channel và executor khi khởi tạo.

Nhiều GAPIC client được thiết kế để dùng lại và có phương thức close để giải phóng background resource. Ví dụ tài liệu của SecretManagerServiceClient yêu cầu gọi close vì client có thể giữ thread nền. Không nên tạo client trong từng phương thức nghiệp vụ rồi quên đóng.

### gRPC ManagedChannel

ManagedChannel đại diện cho hạ tầng giao tiếp gRPC. Nó quản lý các kết nối bên dưới và trạng thái shutdown. ManagedChannel là thread-safe và có thể phục vụ nhiều lời gọi RPC đồng thời.

Một channel không nhất thiết tương ứng đúng một TCP connection: resolver, load balancing, transport và cấu hình của thư viện có thể quyết định số kết nối thực tế. Không nên suy ra số connection chỉ từ số channel.

### Stub

Stub là lớp giao diện gọi một dịch vụ gRPC cụ thể. Stub thường được sinh từ protobuf, chẳng hạn kiểu blocking, async hoặc future stub.

Một stub có thể được cấu hình bằng các phương thức dẫn xuất như withDeadlineAfter hoặc withCallCredentials. Những phương thức này tạo stub với cấu hình lời gọi phù hợp; chúng không tạo một ManagedChannel mới cho mỗi RPC.

~~~java
ManagedChannel channel =
    ManagedChannelBuilder.forTarget("api.example.internal:443")
        .useTransportSecurity()
        .build();

// MyServiceGrpc là lớp được sinh từ protobuf của ứng dụng.
MyServiceGrpc.MyServiceBlockingStub stub =
    MyServiceGrpc.newBlockingStub(channel);

// Deadline áp dụng cho lời gọi qua stub dẫn xuất.
MyServiceGrpc.MyServiceBlockingStub timedStub =
    stub.withDeadlineAfter(2, TimeUnit.SECONDS);
~~~

Ví dụ này minh họa cách chia sẻ channel cho nhiều stub và đặt deadline. Cần import các lớp gRPC, kiểu message được sinh từ protobuf và cấu hình TLS/xác thực phù hợp với service thật. Nếu channel đã được thư viện cấp cao sở hữu, không tự tạo thêm một channel trùng mục đích.

### Quy tắc chọn phạm vi sống

- Khởi tạo channel/client dùng chung khi ứng dụng bắt đầu hoặc khi tính năng được sử dụng lần đầu.
- Dùng lại trong các request đồng thời nếu hợp đồng thread-safety của client cho phép.
- Giữ thông tin theo request ở request object, context hoặc stub dẫn xuất; không sửa mutable state dùng chung tùy tiện.
- Đóng client/channel khi Spring context kết thúc hoặc owner bị hủy.
- Tách client theo endpoint, credentials, tenant hoặc quota project khi các cấu hình đó thực sự khác nhau.

## 3. Vì sao không tạo client mới trong mỗi HTTP request?

Giả sử một API trên Cloud Run nhận 300 request/giây, và mỗi request tạo một Secret Manager client, gọi API rồi bỏ đối tượng mà không close.

Hậu quả có thể gồm:

- Khởi tạo transport và TLS thường xuyên, làm tăng latency.
- Nhiều executor và background thread tồn tại ngoài thời gian xử lý request.
- File descriptor và bộ nhớ tăng theo thời gian.
- Connection churn gây áp lực lên client, server và network.
- Kết quả benchmark không ổn định khi instance scale out.
- Shutdown kéo dài vì còn tài nguyên nền chưa được giải phóng.

Giải pháp thông dụng là tạo một client cho vòng đời ứng dụng, inject nó vào service cần sử dụng và để container đóng khi kết thúc. Tuy nhiên, dùng singleton không có nghĩa là không giới hạn concurrency; phải quản lý số request đến dependency theo quota và năng lực thực tế.

## 4. Tạo và đóng Google Cloud client trong Spring

Spring có cơ chế quản lý lifecycle cho singleton bean. Với phương thức @Bean, Spring có thể tự nhận diện public close/shutdown, nhưng khai báo destroyMethod rõ ràng giúp người đọc biết chính xác ý định.

### Ví dụ: Secret Manager client singleton

~~~java
import com.google.cloud.secretmanager.v1.SecretManagerServiceClient;
import java.io.IOException;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class GcpClientConfig {

    @Bean(destroyMethod = "close")
    SecretManagerServiceClient secretManagerClient() throws IOException {
        return SecretManagerServiceClient.create();
    }
}
~~~

Bean trên được tạo một lần cho mỗi Spring application context theo singleton scope mặc định. Các service inject cùng một instance. Khi Spring context đóng bình thường, Spring gọi close trên bean.

Service sử dụng client:

~~~java
import com.google.cloud.secretmanager.v1.SecretManagerServiceClient;
import com.google.cloud.secretmanager.v1.SecretVersionName;
import org.springframework.stereotype.Service;

@Service
public class SecretReader {
    private final SecretManagerServiceClient client;

    public SecretReader(SecretManagerServiceClient client) {
        this.client = client;
    }

    public String readUtf8(String project, String secret, String version) {
        String name = SecretVersionName.of(project, secret, version).toString();
        return client.accessSecretVersion(name)
                     .getPayload()
                     .getData()
                     .toStringUtf8();
    }
}
~~~

Đây là ví dụ minh họa về vòng đời. Ứng dụng cần kiểm soát IAM, lựa chọn version và xử lý lỗi API. Không ghi secret vào log hoặc trả plaintext secret trực tiếp cho người gọi không có quyền. Nếu nội dung secret là dữ liệu nhị phân, dùng byte[] thay vì ép về UTF-8.

**Điểm cần tránh:** không bọc client được inject bằng try-with-resources trong mỗi method. Làm như vậy sẽ đóng singleton sau request đầu tiên, gây lỗi cho các request tiếp theo.

### Client dùng một lần trong tiện ích dòng lệnh

Với chương trình chạy ngắn và tự sở hữu client, try-with-resources lại là lựa chọn phù hợp:

~~~java
try (SecretManagerServiceClient client =
         SecretManagerServiceClient.create()) {
    // Thực hiện một hoặc vài lời gọi API.
}
// close() được gọi khi rời khối.
~~~

Sự khác biệt nằm ở owner: chương trình ngắn tự sở hữu client; trong ứng dụng Spring, container sở hữu singleton bean.

### Một số thư viện có cách đóng khác nhau

Không áp dụng một quy tắc close cho mọi object. Một số client cung cấp AutoCloseable, một số có shutdown và awaitTermination, một số dùng transport do builder hoặc framework khác sở hữu. Tham khảo JavaDoc của đúng client và kiểm tra khi dùng custom channel/transport.

Ví dụ, BigQuery client hiện có phương thức close với hợp đồng giải phóng background resources khi implementation có sở hữu chúng; implementation không có resources có thể thực hiện no-op. Không vì thế mà kết luận mọi Google Cloud client đều có cùng hành vi.

## 5. Quản lý ManagedChannel và quyền sở hữu transport

Khi tự tạo channel cho gRPC service, cần quản lý cả khởi tạo và shutdown. Không tạo channel mới cho mỗi request và không đóng channel khi vẫn còn RPC đang thực hiện.

### Ví dụ đóng channel có thời hạn

~~~java
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;
import java.util.concurrent.TimeUnit;

public final class ChannelExample {
    public static void main(String[] args) {
        ManagedChannel channel = ManagedChannelBuilder
            .forTarget("api.example.internal:443")
            .useTransportSecurity()
            .build();

        try {
            // Tạo và sử dụng stub từ channel.
        } finally {
            channel.shutdown();
            try {
                if (!channel.awaitTermination(5, TimeUnit.SECONDS)) {
                    channel.shutdownNow();
                }
            } catch (InterruptedException interrupted) {
                channel.shutdownNow();
                Thread.currentThread().interrupt();
            }
        }
    }
}
~~~

shutdown ngừng nhận RPC mới; các call đã có thể tiếp tục trong quá trình dừng tùy trạng thái. shutdownNow cưỡng bức hủy call còn lại; nó cũng không bảo đảm tài nguyên biến mất ngay tức thì. Với server thật, phải dừng phát sinh request mới và chờ các request đang xử lý trước khi đóng channel.

### Gói channel thành bean có owner rõ ràng

Khi cần tùy biến channel và timeout shutdown, có thể dùng một wrapper AutoCloseable:

~~~java
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;
import java.util.concurrent.TimeUnit;

public final class GrpcChannelOwner implements AutoCloseable {
    private final ManagedChannel channel;

    public GrpcChannelOwner(String target) {
        this.channel = ManagedChannelBuilder
            .forTarget(target)
            .useTransportSecurity()
            .build();
    }

    public ManagedChannel channel() {
        return channel;
    }

    @Override
    public void close() {
        channel.shutdown();
        try {
            if (!channel.awaitTermination(5, TimeUnit.SECONDS)) {
                channel.shutdownNow();
            }
        } catch (InterruptedException interrupted) {
            channel.shutdownNow();
            Thread.currentThread().interrupt();
        }
    }
}
~~~

Cấu hình Spring:

~~~java
@Configuration(proxyBeanMethods = false)
class GrpcConfig {
    @Bean(destroyMethod = "close")
    GrpcChannelOwner grpcChannelOwner() {
        return new GrpcChannelOwner("api.example.internal:443");
    }
}
~~~

Các service có thể inject GrpcChannelOwner để tạo stub, nhưng không được gọi close trong quá trình phục vụ request. Với ứng dụng dùng nhiều endpoint, nên có một owner độc lập cho mỗi endpoint/cấu hình thực sự cần thiết.

### Khi client thư viện nhận custom transport

GAX cung cấp các transport channel provider và builder để cấu hình endpoint, credentials hoặc transport. Một provider có thể tạo channel mới hoặc trả channel cố định; có API biểu thị liệu client chứa provider có tự đóng channel hay không.

Khi cung cấp channel thủ công:

1. Xác định ai tạo channel và ai có quyền đóng.
2. Đọc hợp đồng shouldAutoClose và hành vi provider của phiên bản thư viện.
3. Tránh để cả client và wrapper cùng giả định mình là owner.
4. Không đóng shared channel khi một trong nhiều client còn sử dụng.
5. Giữ thứ tự dừng: ngừng request mới, đợi in-flight work, đóng client rồi đóng channel khi owner thực sự sở hữu nó.

## 6. Thread pool: tài nguyên có giới hạn

Thread pool chạy công việc đồng thời: tác vụ @Async, callback, xử lý message và một số thao tác blocking. Không nên tạo một executor mới cho từng request vì số thread sẽ tăng không kiểm soát.

Cấu hình executor gồm:

| Thuộc tính | Ý nghĩa | Rủi ro nếu cấu hình sai |
|---|---|---|
| Core pool size | Số worker cơ bản | Quá cao gây chuyển ngữ cảnh |
| Max pool size | Trần số worker | Quá cao gây tốn RAM và áp lực dependency |
| Queue capacity | Số task chờ | Queue vô hạn che giấu quá tải, tăng latency |
| Keep-alive | Thời gian giữ worker thừa | Quá lâu gây lãng phí, quá ngắn gây churn |
| Rejection policy | Hành vi khi đầy | Im lặng bỏ task hoặc gây nghẽn request |
| Thread naming | Giúp debug thread dump | Không xác định được task thuộc pool nào |
| Shutdown wait | Chờ task đang chạy | Dừng quá sớm gây mất task, chờ quá lâu bị kill |

Một executor lớn không làm API bên ngoài nhanh hơn nếu API đó có quota hoặc latency cố định. Với I/O blocking, số worker có thể lớn hơn CPU cores, nhưng phải giới hạn theo bộ nhớ, downstream capacity và deadline.

### Spring ThreadPoolTaskExecutor

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableAsync
public class AsyncConfig {

    @Bean(name = "gcpIoExecutor")
    ThreadPoolTaskExecutor gcpIoExecutor() {
        ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
        pool.setCorePoolSize(4);
        pool.setMaxPoolSize(12);
        pool.setQueueCapacity(100);
        pool.setThreadNamePrefix("gcp-io-");
        pool.setWaitForTasksToCompleteOnShutdown(true);
        pool.setAwaitTerminationSeconds(8);
        return pool;
    }
}
~~~

Spring quản lý khởi tạo và hủy ThreadPoolTaskExecutor khi nó là bean. Không cần gọi pool.initialize thủ công trong phương thức @Bean. Tham số 4, 12, 100 và 8 giây chỉ là ví dụ; cần đo với workload thật và giới hạn shutdown của nền tảng.

Với ThreadPoolExecutor có hàng đợi, khi đủ core threads, task thường được đưa vào queue trước khi pool tăng lên max threads. Vì vậy queue capacity và max pool size phải được chọn cùng nhau; một queue quá lớn có thể làm max threads gần như không được sử dụng.

### Dùng @Async đúng cách

~~~java
import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class AsyncLookupService {
    private final SecretReader secretReader;

    public AsyncLookupService(SecretReader secretReader) {
        this.secretReader = secretReader;
    }

    @Async("gcpIoExecutor")
    public CompletableFuture<String> loadValue(
            String project, String secret, String version) {
        String result = secretReader.readUtf8(project, secret, version);
        return CompletableFuture.completedFuture(result);
    }
}
~~~

@Async chỉ chuyển nơi thực hiện sang executor; nó không biến một RPC blocking thành non-blocking. Cần xử lý timeout, thất bại và tình huống pool từ chối task. Trong Spring proxy mode, tự gọi một phương thức @Async từ phương thức khác trong cùng object thường không đi qua proxy, nên không kích hoạt xử lý bất đồng bộ như mong đợi.

Nếu dùng dữ liệu nhạy cảm, tránh chuyển plaintext secret qua nhiều tầng async không cần thiết. Ví dụ chỉ nhằm minh họa cơ chế thread pool và DI.

## 7. Backpressure và khi thread pool quá tải

Khi tốc độ request vào lớn hơn tốc độ xử lý, các task sẽ tích tụ. Nếu queue không có giới hạn, latency tăng và ứng dụng có thể hết bộ nhớ trước khi xuất hiện cảnh báo CPU.

Một mô hình đơn giản:

~~~text
HTTP requests / Pub/Sub messages
             |
             v
     Bounded work queue
             |
        +----+----+
        |         |
        v         v
     Worker 1   Worker N
        |         |
        +----+----+
             |
             v
      Google Cloud API
      (quota / latency)
~~~

Khi queue đầy, cần phản ứng có chủ đích:

- Từ chối sớm một phần công việc với mã lỗi và retry guidance phù hợp.
- Giảm số message in-flight qua Pub/Sub flow control.
- Giảm request concurrency hoặc áp dụng semaphore/bulkhead cho dependency.
- Dùng Cloud Tasks hoặc Pub/Sub cho công việc bất đồng bộ cần độ bền và retry.
- Đặt timeout tổng để request không chờ vô hạn.

### Không dùng CallerRunsPolicy thiếu cân nhắc

CallerRunsPolicy chạy task trên thread của bên gửi khi pool đầy. Nó có thể tạo backpressure tự nhiên, nhưng nếu caller là HTTP request thread hoặc gRPC event loop, thao tác blocking có thể giữ thread quan trọng và gây hiệu ứng dây chuyền.

AbortPolicy hoặc cơ chế từ chối rõ ràng thường dễ vận hành hơn khi ứng dụng có thể trả lỗi và retry có giới hạn. Chọn rejection policy theo semantics của công việc; không có một policy phù hợp mọi hệ thống.

### Tránh deadlock do nested futures

Nếu task trong pool nhỏ gửi task khác vào cùng pool rồi blocking chờ kết quả, các worker có thể bị chiếm hết và không còn thread để chạy task con. Hãy tránh nested blocking, tách pool có trách nhiệm khác nhau hoặc dùng composition không chặn worker.

## 8. Pub/Sub Publisher: batching và flush khi dừng

Publisher có thể batch message, retry và duy trì các background resource. Nên tạo Publisher dùng chung cho mỗi topic/cấu hình thay vì tạo một instance cho từng message.

Ví dụ Java:

~~~java
import com.google.api.core.ApiFuture;
import com.google.cloud.pubsub.v1.Publisher;
import com.google.pubsub.v1.PubsubMessage;
import com.google.pubsub.v1.TopicName;
import com.google.protobuf.ByteString;
import java.util.concurrent.TimeUnit;

public final class PublishExample {
    public static void send(String project, String topic) throws Exception {
        Publisher publisher = Publisher
            .newBuilder(TopicName.of(project, topic))
            .build();

        try {
            PubsubMessage message = PubsubMessage.newBuilder()
                .setData(ByteString.copyFromUtf8("order-created"))
                .build();

            ApiFuture<String> messageId = publisher.publish(message);
            System.out.println("Published: " + messageId.get(10, TimeUnit.SECONDS));
        } finally {
            publisher.shutdown();
            try {
                publisher.awaitTermination(10, TimeUnit.SECONDS);
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
            }
        }
    }
}
~~~

Đây là ví dụ chương trình ngắn tự sở hữu Publisher. Trong ứng dụng Spring, Publisher nên là singleton hoặc được quản lý qua một wrapper có phương thức close: dừng nhận task mới, flush message đang batch, gọi shutdown và chờ termination có giới hạn.

Một số lưu ý:

- Kết quả publish có thể hoàn thành bất đồng bộ; kiểm tra future để biết message có được chấp nhận hay không.
- Không bỏ qua lỗi publish; cần quyết định retry, lưu bền hoặc báo thất bại theo nghiệp vụ.
- Đặt batching, flow control và retry theo throughput và memory budget.
- Khi đóng, đợi message đang chờ đủ thời gian; nếu bị kill giữa chừng vẫn có thể mất công việc chỉ tồn tại trong RAM.
- Đối với nghiệp vụ cần gửi thông điệp chắc chắn sau khi ghi database, cân nhắc transactional outbox hoặc cơ chế bền vững phù hợp thay vì chỉ trông chờ flush khi shutdown.

## 9. Pub/Sub Subscriber: vòng đời start/stop và concurrency

Subscriber dùng StreamingPull để nhận message và giao cho callback. Nó có lifecycle khác với client chỉ phục vụ RPC đồng bộ:

~~~text
CREATED
   |
   v
STARTING -> RUNNING -> STOPPING -> TERMINATED
                 |
                 +--> FAILED
~~~

Ứng dụng cần gọi startAsync và quan sát awaitRunning hoặc listener; khi dừng, gọi stopAsync rồi chờ awaitTerminated theo giới hạn thời gian phù hợp.

### Cấu hình số luồng và flow control

~~~java
import com.google.api.gax.batching.FlowControlSettings;
import com.google.api.gax.core.ExecutorProvider;
import com.google.api.gax.core.InstantiatingExecutorProvider;
import com.google.cloud.pubsub.v1.Subscriber;

// subscriptionName và messageReceiver được tạo ở nơi khác.
ExecutorProvider executorProvider =
    InstantiatingExecutorProvider.newBuilder()
        .setExecutorThreadCount(4)
        .build();

FlowControlSettings flowControl =
    FlowControlSettings.newBuilder()
        .setMaxOutstandingElementCount(200L)
        .setMaxOutstandingRequestBytes(20L * 1024 * 1024)
        .build();

Subscriber subscriber =
    Subscriber.newBuilder(subscriptionName, messageReceiver)
        .setParallelPullCount(2)
        .setExecutorProvider(executorProvider)
        .setFlowControlSettings(flowControl)
        .build();

subscriber.startAsync().awaitRunning();
~~~

Ví dụ trên minh họa giới hạn số message và byte in-flight. Trong phiên bản client có cách cấu hình cụ thể, hãy đối chiếu JavaDoc tương ứng. Với Pub/Sub Java, parallelPullCount điều chỉnh số stream; executorProvider quyết định worker phục vụ callback. Không chỉ tăng thread count mà bỏ qua flow control, vì số message đang xử lý và độ lớn payload cũng làm tăng memory.

### Dừng Subscriber

~~~java
subscriber.stopAsync();
try {
    subscriber.awaitTerminated(8, TimeUnit.SECONDS);
} catch (java.util.concurrent.TimeoutException timeout) {
    // Ghi nhận và để hệ thống điều phối shutdown tiếp tục.
} catch (InterruptedException interrupted) {
    Thread.currentThread().interrupt();
}
~~~

Nên dừng nhận message mới trước, sau đó chờ callback đang chạy hoàn tất theo giới hạn shutdown. Ack chỉ khi xử lý đủ bền theo nghiệp vụ; với công việc chưa hoàn tất, không ack sớm chỉ để shutdown nhanh. Message chưa ack có thể được gửi lại, nên consumer cần idempotency.

Trên Cloud Run services, Google khuyến nghị Pub/Sub push subscription cho workload nhận thông điệp qua HTTP vì push kích hoạt autoscaling. Một streaming pull subscriber chạy nền cần chiến lược CPU, min instances và lifecycle rõ ràng; với workload chạy liên tục có thể cân nhắc GKE, Compute Engine hoặc hình thức chạy phù hợp.

## 10. Thứ tự shutdown đúng trong ứng dụng Spring

Shutdown không chỉ là gọi close cho từng object theo thứ tự ngẫu nhiên. Nếu đóng channel trong khi callback vẫn đang gửi RPC, những lời gọi đó có thể thất bại.

Một trình tự tham khảo:

1. Nhận tín hiệu shutdown và ngừng chấp nhận request hoặc công việc mới.
2. Dừng scheduler và subscriber nhận message mới.
3. Chờ HTTP request, async task và message handler đang chạy theo deadline.
4. Flush Publisher hoặc các batch output còn lại.
5. Đóng Google Cloud API clients và HTTP/gRPC resources chúng sở hữu.
6. Đóng ManagedChannel do ứng dụng tự quản lý.
7. Shutdown executor do ứng dụng sở hữu, chờ tối đa theo budget còn lại.
8. Ghi nhận số task chưa hoàn thành và kết thúc tiến trình.

Thứ tự cụ thể phụ thuộc dependency graph: một executor dùng để hoàn tất publish callback không được đóng trước Publisher. Một shared channel dùng bởi nhiều client phải đóng sau khi tất cả client ngừng gửi RPC.

### Spring lifecycle hooks

| Hook | Khi dùng | Lưu ý |
|---|---|---|
| @Bean(destroyMethod = "close") | Client AutoCloseable có vòng đời singleton | Đơn giản, được quản lý bởi context |
| @PreDestroy | Dọn tài nguyên trong component cụ thể | Tránh blocking quá lâu hoặc gọi API không cần thiết |
| DisposableBean | Tích hợp dọn tài nguyên với Spring | Gắn code trực tiếp với Spring |
| SmartLifecycle | Cần start/stop theo phase, ví dụ Subscriber | Có thể điều phối shutdown có thứ tự |
| ThreadPoolTaskExecutor bean | Pool @Async do Spring quản lý | Cấu hình wait và thời hạn shutdown |
| Shutdown hook JVM | Công cụ Java ngoài container DI | Không thay thế lifecycle của Spring |

Khi nhiều bean phụ thuộc nhau, Spring có thể dùng quan hệ dependency để quyết định thứ tự hủy. Với tài nguyên phức tạp, dùng SmartLifecycle và thiết kế phase có chủ ý, kiểm tra trong integration test. Không dựa vào thứ tự tên class hoặc thứ tự khai báo ngẫu nhiên.

### Spring Boot graceful shutdown

Ví dụ application.yml:

~~~yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 8s
~~~

Spring Boot sẽ cố hoàn tất request đang xử lý trong thời gian dành cho shutdown phase. Con số 8 giây chỉ là ví dụ; cần chia sẻ tổng shutdown budget cho web server, subscriber, publisher, client và executor. Việc cấu hình 8 giây cho nhiều thành phần không bảo đảm tất cả hoàn thành trong tổng 8 giây.

## 11. Đặc thù Cloud Run, GKE và Compute Engine

### Cloud Run

Cloud Run service có thể scale in, thay revision hoặc chấm dứt instance. Khi shutdown, instance nhận SIGTERM để dọn dẹp trong khoảng grace period ngắn, thường khoảng 10 giây trước khi bị dừng. Không nên thiết kế shutdown phụ thuộc vào việc chờ hàng phút để drain task.

Với request-based billing, CPU ngoài thời gian xử lý request có thể bị giới hạn hoặc không sẵn sàng như kỳ vọng. Vì vậy, không phù hợp để khởi chạy background thread rồi trả HTTP response và hy vọng công việc sẽ luôn chạy xong.

Đối với công việc cần hoàn thành sau HTTP response:

- Dùng Pub/Sub push hoặc Cloud Tasks cho công việc có thể retry.
- Dùng Cloud Run jobs cho xử lý batch hữu hạn theo thời gian và cấu hình task.
- Nếu thật sự cần xử lý nền trên instance còn sống, đánh giá instance-based billing và minimum instances, nhưng vẫn phải xử lý trường hợp instance bị chấm dứt.
- Ghi state hoặc checkpoint bền vững, tránh chỉ giữ dữ liệu quan trọng trong RAM.

Cloud Run autoscaling dựa vào concurrency và CPU. Số Cloud Run instances nhân với số client/channel/connection mỗi instance có thể tạo tải lớn lên dependency. Đừng chỉ tính tài nguyên cho một instance.

### GKE

Pod có terminationGracePeriodSeconds, readiness probe và container lifecycle. Khi pod chuẩn bị dừng, phải ngừng nhận traffic mới và cho request đang chạy thời gian hoàn tất trước khi container bị kill.

Thời gian drain của ingress/load balancer, graceful shutdown của web server và thời gian đóng client phải nằm trong khoảng grace period đã cấu hình. Nếu terminationGracePeriodSeconds quá thấp, Publisher có thể chưa flush xong. Nếu quá cao, rollout có thể chậm.

Quan sát pod restarts, memory, CPU, open file descriptors, thread count và connection count. Thread pool quá lớn kết hợp với memory limit thấp có thể gây OOMKilled ngay cả khi heap Java chưa đầy vì native stacks và buffers cũng tiêu thụ bộ nhớ.

### Compute Engine

Tiến trình JVM chạy trên VM có thể nhận tín hiệu shutdown khi VM dừng hoặc instance group thay đổi. Dùng systemd hoặc process supervisor để truyền tín hiệu, cấu hình timeout và ghi log shutdown.

Không dựa vào shutdown hook để hoàn tất công việc dài hoặc chuyển trạng thái quan trọng. Cần có persistence, checkpoint và retry ở tầng nghiệp vụ.

## 12. Tính toán concurrency và downstream capacity

Giả sử một Cloud Run service có:

- Tối đa 20 instances ở thời điểm tải cao.
- Mỗi instance có một pool tối đa 12 worker gọi API.
- Mỗi worker có thể mở hoặc giữ một database connection trong lúc thực hiện công việc.

Nếu không có giới hạn riêng, nhu cầu đồng thời tối đa về database có thể lên đến khoảng 20 × 12 = 240 connection, chưa tính connection từ background components và các service khác. Nếu Cloud SQL chỉ đủ năng lực cho mức thấp hơn, tăng thread pool có thể làm lỗi tăng mạnh.

Một nguyên tắc thiết kế là xác định **concurrency budget** cho từng dependency:

~~~text
Tổng nhu cầu đồng thời
  ≈ số instance có thể hoạt động
    × request/concurrency được phép mỗi instance
    × số thao tác đồng thời tới dependency
~~~

Công thức là ước tính sơ bộ. Request có thể fan-out, retry hoặc batch; vì vậy cần tính cả peak, hiệu ứng retry và workload nền.

### Giới hạn theo dependency

Có thể sử dụng semaphore, bulkhead hoặc bounded executor riêng cho lời gọi tốn tài nguyên. Không cần tạo một thread pool riêng cho từng API nhỏ, nhưng các dependency có giới hạn rất khác nhau có thể cần ranh giới concurrency độc lập.

Ví dụ:

- Secret Manager: cache kết quả ngắn hạn có kiểm soát khi phù hợp, giới hạn request theo quota.
- Cloud SQL: cấu hình connection pool size và max instances phối hợp.
- Pub/Sub: dùng flow control và batching.
- gRPC nội bộ: đặt deadline, giới hạn in-flight RPC và xử lý retry có backoff.
- Cloud Storage: giới hạn số tác vụ upload/download đồng thời theo bandwidth và memory.

## 13. Deadlines, retries và cancellation

Một thread bị kẹt trong RPC quá lâu sẽ tiếp tục chiếm worker và queue. Vì vậy, lifecycle cần kết hợp timeout và deadline.

### Deadline cho gRPC

~~~java
MyServiceGrpc.MyServiceBlockingStub timed =
    stub.withDeadlineAfter(1500, TimeUnit.MILLISECONDS);

// RPC qua timed sẽ có giới hạn thời gian.
~~~

Deadline là hạn xử lý của RPC; nếu hết hạn, RPC thường bị hủy và trả trạng thái DEADLINE_EXCEEDED. Trong pipeline nhiều hop, cần truyền deadline hoặc tính budget còn lại để các hop không cộng dồn thời gian chờ vô hạn.

### Retry có giới hạn

Retry chỉ áp dụng cho lỗi tạm thời và thao tác phù hợp với idempotency. Dùng exponential backoff, jitter, deadline tổng và retry budget. Nếu executor đã bão hòa, retry không kiểm soát có thể khiến hệ thống quá tải hơn.

### Cancellation

Khi client HTTP ngắt kết nối, task có thể vẫn đang chạy nếu application không lan truyền cancellation. Với CompletableFuture và API bất đồng bộ, cần kiểm tra hỗ trợ cancel của client và cách dùng interruption. Không giả định gọi Future.cancel tự động hủy network RPC nếu thư viện không hỗ trợ.

## 14. Virtual threads trong Java 21 và Spring Boot

Virtual threads giảm chi phí mỗi thread Java đối với nhiều tác vụ blocking I/O. Với Spring Boot có hỗ trợ, có thể bật bằng:

~~~properties
spring.threads.virtual.enabled=true
~~~

Khi bật và dùng Java 21+, một số executor/scheduler tự cấu hình của Spring Boot có thể chuyển sang dùng virtual threads thay cho thread pool nền tảng truyền thống.

Virtual threads **không làm tăng quota API, database connection hay network bandwidth**. Nếu 10.000 virtual threads cùng gọi dependency có giới hạn 100 request đồng thời, dependency vẫn quá tải. Cần semaphore, rate limit hoặc giới hạn in-flight work.

Một số điểm cần kiểm tra:

- Thư viện có dùng synchronized hoặc native call làm pin carrier thread trong tình huống cụ thể không?
- MDC, trace context và security context có được truyền đúng không?
- Executor tự cấu hình của Spring Boot đã thay đổi như thế nào khi bật virtual threads?
- Blocking I/O có thực sự là bottleneck chính hay hệ thống bị giới hạn CPU?
- Có còn giới hạn concurrent RPC và queue phù hợp không?

Đừng bật virtual threads như một cách thay thế mọi cơ chế backpressure. Benchmark trên workload thực tế và quan sát latency, memory, thread state và throughput.

## 15. Theo dõi và phát hiện resource leak

Metrics, logs và thread dumps giúp xác định client/channel/executor có được quản lý đúng không.

| Tín hiệu | Ý nghĩa có thể có | Kiểm tra tiếp |
|---|---|---|
| Thread count tăng sau mỗi request | Tạo executor/client lặp lại | Kiểm tra vị trí khởi tạo, thread name |
| Open file descriptors tăng | Connection/socket không được giải phóng | Kiểm tra channel và HTTP client ownership |
| Queue depth tăng liên tục | Công việc vào nhanh hơn xử lý | Đo arrival rate, worker utilization, downstream latency |
| Active threads luôn chạm max | Pool bão hòa hoặc task bị blocking | Thread dump, timeout, dependency metrics |
| RPC latency tăng khi CPU thấp | Chờ network/dependency hoặc pool queue | Trace và metrics client |
| Pub/Sub outstanding messages cao | Callback chậm hoặc flow control chưa đúng | Ack latency, subscriber concurrency |
| Shutdown kéo dài hoặc timeout | Chưa dừng producer, drain sai thứ tự | Log lifecycle và task còn in-flight |
| Memory tăng dù heap ổn định | Native thread stack, direct buffers, transport | JVM native memory và connection metrics |

### Thread dump

Khi nghi ngờ thread leak hoặc deadlock, thu thập thread dump an toàn qua công cụ JVM phù hợp và phân tích:

- Số thread theo prefix.
- Trạng thái RUNNABLE, WAITING, TIMED_WAITING, BLOCKED.
- Các stack trace lặp lại ở cùng thao tác blocking.
- Executor worker có đang chờ task hay bị kẹt trong RPC.
- Thread của gRPC/Netty và client library có tăng theo số request không.

Không chỉ dựa vào số thread tuyệt đối. Một số thư viện tạo thread nền hợp lệ; điều đáng lo là số thread tăng không trở về mức ổn định hoặc tăng theo số request thay vì theo số instance/client đã thiết kế.

### Micrometer và Cloud Monitoring

Spring Boot Actuator và Micrometer có thể cung cấp metrics JVM, executor hoặc các metrics tùy biến theo cách ứng dụng instrument. Đưa metrics lên Cloud Monitoring/Managed Service for Prometheus tùy kiến trúc.

Dashboard nên có:

- JVM threads live/daemon và memory.
- Executor active count, queue size, completed/rejected tasks.
- RPC latency, deadline exceeded, retry và error rate theo dependency.
- Pub/Sub publish latency, pending messages, subscriber ack/nack.
- HTTP request latency, 5xx và saturation của Cloud Run/GKE.
- Số instance/pod và downstream connection count.

Metric label không nên chứa user ID, email hoặc request ID vì cardinality và rủi ro bảo mật.

## 16. Tình huống thực tế: Spring Boot API trên Cloud Run

Một dịch vụ checkout trên Cloud Run nhận HTTP request, đọc thông tin cấu hình từ Secret Manager, ghi database và gửi sự kiện Pub/Sub.

### Thiết kế chưa phù hợp

Trong mỗi request, controller tạo Secret Manager client, một Publisher và ExecutorService mới, sau đó trả HTTP response ngay khi đã gửi task vào executor.

Các vấn đề:

- Client và executor mới liên tục tiêu tốn connection/thread.
- Publisher có thể chưa kịp flush khi request trả về và CPU bị giảm.
- Khi Cloud Run scale in, task nằm trong RAM có thể biến mất.
- Không có giới hạn số task hay connection tới Cloud SQL.
- Không rõ ai sở hữu shutdown nên khó drain an toàn.

### Thiết kế cải tiến

~~~text
Spring ApplicationContext (mỗi Cloud Run instance)
           |
           +--> SecretManagerServiceClient singleton
           |
           +--> Pub/Sub Publisher singleton
           |
           +--> Bounded Executor / semaphore
           |
           +--> Database connection pool
           |
           +--> HTTP request handlers
                      |
                      v
              Checkout service
                      |
                      +--> Đọc cấu hình qua client dùng chung
                      +--> Thực hiện giao dịch có deadline
                      +--> Ghi outbox/event bền vững
                      +--> Trả kết quả đã xác nhận
~~~

Trong thiết kế này:

1. Spring tạo một instance cho mỗi client có cấu hình chung.
2. Request handler không tự đóng client.
3. Pool và connection limit được tính theo số Cloud Run instances tối đa.
4. Gửi sự kiện quan trọng theo một cơ chế bền vững (ví dụ outbox + publisher worker hoặc Pub/Sub push/Cloud Tasks tùy nghiệp vụ).
5. Khi shutdown, ứng dụng dừng nhận công việc, drain trong giới hạn rồi đóng Publisher, clients và executors.
6. Telemetry ghi nhận latency, queue depth, active connections, failed publish và thời gian shutdown.

### Cách kiểm chứng

- Load test ở mức concurrency gần production.
- Quan sát thread count trước và sau hàng nghìn request.
- Tạo rollout mới để kích hoạt shutdown/restart và kiểm tra message còn in-flight.
- Kiểm tra Pub/Sub không mất sự kiện nghiệp vụ; consumer xử lý được duplicate.
- Kiểm tra queue được giới hạn và request bị từ chối theo cách có chủ đích khi quá tải.
- Xác minh service vẫn hoạt động khi một dependency chậm hoặc trả lỗi tạm thời.

## 17. Các lỗi thường gặp

| Lỗi | Hệ quả | Cách khắc phục |
|---|---|---|
| Tạo GAPIC client mỗi request | Thread/connection churn, tăng latency | Tạo singleton bean và close khi context dừng |
| Đóng singleton client trong service method | Request sau thất bại vì client đã đóng | Để Spring/owner quản lý close |
| Tạo ManagedChannel cho từng RPC | Tăng kết nối và TLS overhead | Tái sử dụng channel, tạo stub theo nhu cầu |
| Không phân định channel ownership | Double close hoặc resource leak | Ghi rõ client/provider/wrapper nào chịu trách nhiệm |
| Executor có queue vô hạn | Latency và memory tăng khi quá tải | Queue hữu hạn, rejection/backpressure |
| Tăng thread pool để chữa API chậm | Downstream overload và retry storm | Giới hạn concurrency, timeout và phân tích dependency |
| Đóng executor trước khi drain Publisher | Callback/flush thất bại | Dừng producer và chờ in-flight trước khi đóng executor |
| Ack Pub/Sub trước khi xử lý bền vững | Có thể mất công việc khi instance bị kill | Ack sau khi công việc đã hoàn tất bền vững |
| Chạy background thread sau HTTP response trên Cloud Run | Task có thể ngừng hoặc mất khi instance dừng | Dùng Pub/Sub/Cloud Tasks/Jobs phù hợp |
| Chỉ dùng @PreDestroy với tác vụ hàng phút | Không kịp grace period của nền tảng | Shutdown có budget, checkpoint và retry |
| Bật virtual threads rồi bỏ mọi giới hạn | Dependency vẫn quá tải | Semaphore, rate limit và quota-aware design |

## 18. Checklist trước khi đưa Java service lên GCP

- [ ] Mỗi client có owner và scope được định nghĩa.
- [ ] Client dùng chung chỉ được tạo một lần cho mỗi cấu hình phù hợp.
- [ ] Google Cloud client có close/shutdown được quản lý bởi Spring hoặc owner rõ ràng.
- [ ] Shared ManagedChannel không bị đóng trong từng RPC.
- [ ] Custom channel/provider có hợp đồng ownership và thứ tự close rõ ràng.
- [ ] ThreadPoolTaskExecutor có core/max/queue hữu hạn và chính sách rejection.
- [ ] Không có blocking task dài trong gRPC event loop hoặc thread quan trọng.
- [ ] Mỗi dependency có deadline, retry budget và concurrency limit phù hợp.
- [ ] Pub/Sub Publisher được flush và awaitTermination khi dừng.
- [ ] Subscriber có start/stop rõ ràng, flow control và ack đúng thời điểm.
- [ ] Spring graceful shutdown và nền tảng có budget thời gian phù hợp.
- [ ] Cloud Run không phụ thuộc vào task RAM sau HTTP response cho công việc bắt buộc.
- [ ] Số connection/pool được tính trên toàn bộ instances/pods.
- [ ] Metrics có thread count, active/queued/rejected task, RPC latency và lỗi shutdown.
- [ ] Có load test, scale-in/restart test và kiểm tra không mất công việc quan trọng.

## Kết luận

Quản lý vòng đời tài nguyên trong Java/Spring trên GCP bắt đầu từ ba câu hỏi: **ai tạo, ai sử dụng và ai đóng**. Google Cloud clients và gRPC channels thường nên được tái sử dụng theo vòng đời ứng dụng; thread pools cần có giới hạn và chính sách backpressure; Publisher và Subscriber cần cơ chế drain và stop rõ ràng. Spring giúp điều phối bean lifecycle, nhưng ứng dụng vẫn phải tính tới deadline, thứ tự shutdown, số instance, quota và thời gian kết thúc của Cloud Run hoặc GKE. Khi thiết kế ownership, concurrency và telemetry ngay từ đầu, hệ thống giảm resource leak, xử lý tải ổn định hơn và khôi phục đáng tin cậy khi instance thay đổi.

## Tài liệu tham khảo

- [SecretManagerServiceClient Java reference](https://docs.cloud.google.com/java/docs/reference/google-cloud-secretmanager/latest/com.google.cloud.secretmanager.v1.SecretManagerServiceClient)
- [Google Cloud Java client configuration](https://docs.cloud.google.com/java/docs/common-configuration-options)
- [GAX TransportChannelProvider reference](https://docs.cloud.google.com/java/docs/reference/gax/latest/com.google.api.gax.rpc.TransportChannelProvider)
- [Pub/Sub Java Publisher reference](https://docs.cloud.google.com/java/docs/reference/google-cloud-pubsub/latest/com.google.cloud.pubsub.v1.Publisher)
- [Pub/Sub Java Subscriber reference](https://docs.cloud.google.com/java/docs/reference/google-cloud-pubsub/latest/com.google.cloud.pubsub.v1.Subscriber)
- [Pub/Sub concurrency control](https://docs.cloud.google.com/pubsub/docs/concurrency-control)
- [gRPC Java ManagedChannel](https://grpc.github.io/grpc-java/javadoc/io/grpc/ManagedChannel.html)
- [Spring Framework: Bean lifecycle](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html)
- [Spring Boot: Task execution and scheduling](https://docs.spring.io/spring-boot/reference/features/task-execution-and-scheduling.html)
- [Spring Boot: Graceful shutdown](https://docs.spring.io/spring-boot/reference/web/graceful-shutdown.html)
- [Cloud Run: Instance autoscaling](https://docs.cloud.google.com/run/docs/about-instance-autoscaling)
- [Cloud Run: Billing settings and background CPU](https://docs.cloud.google.com/run/docs/configuring/billing-settings)
- [Cloud Run: Container shutdown](https://docs.cloud.google.com/run/docs/configuring/execution-environments)

