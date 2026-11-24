# Giới hạn thread, kết nối và bộ đệm trong luồng bất đồng bộ

Một ứng dụng Spring Boot có thể nhận request nhanh hơn tốc độ database, Redis, object storage hoặc message consumer xử lý. Trong mô hình bất đồng bộ, thread không phải chờ I/O theo cách blocking, nhưng công việc vẫn chiếm connection, buffer, memory, CPU và quota của dịch vụ. Nếu không đặt giới hạn, request sẽ tích tụ trong hàng đợi, bộ đệm phình ra, connection pool cạn và latency tăng cho tới khi ứng dụng hoặc downstream mất ổn định.

Thiết kế an toàn cần giới hạn độc lập bốn tài nguyên: **thread thực thi**, **số thao tác đang in-flight**, **connection/channel tới dịch vụ**, và **dữ liệu đang chờ trong buffer/queue**. Các giới hạn phải phối hợp với nhau. Tăng thread không giải quyết pool connection quá nhỏ; tăng pool không giải quyết message buffer không giới hạn; bật reactive backpressure cũng không tự bảo vệ một API async trả về `CompletableFuture` nếu ứng dụng submit vô hạn.

Bài thuộc chương **Hiệu năng và chi phí** của mô-đun **SPRING_CLOUD_PROVIDER_INTEGRATION**. Mô-đun thực hành tích hợp Spring Boot với các dịch vụ managed của AWS, Azure và Google Cloud qua thư viện Spring Cloud tương ứng, bao gồm cấu hình danh tính/quyền, storage, messaging, dữ liệu, bảo vệ secret, kiểm thử tích hợp và đánh giá khác biệt giữa cloud provider. Bài này tập trung vào giới hạn tài nguyên và flow control trong các pipeline async/reactive khi gọi dịch vụ cloud.

## 1. Kết quả học tập

Sau bài học, bạn có thể:

- Phân biệt event-loop thread, worker/executor thread, connection, in-flight request và buffer.
- Giải thích vì sao async I/O vẫn cần giới hạn concurrency và memory.
- Thiết kế Reactor pipeline với `flatMap`, `limitRate`, prefetch và bounded buffer.
- Cấu hình AWS SDK async Netty concurrency và future-completion executor.
- Giới hạn connection và pending acquire của Azure Netty HTTP transport.
- Cấu hình Google Cloud Pub/Sub subscriber flow control theo số message và số byte.
- Cấu hình R2DBC pool và tính tổng connection theo số pod.
- Ước lượng buffer memory theo payload size, concurrency và số tầng queue.
- Thiết lập timeout, cancellation, retry, graceful shutdown và metrics.
- Kiểm thử overload để chứng minh hệ thống có điểm dừng hữu hạn khi downstream chậm.

## 2. Async không có nghĩa là tài nguyên vô hạn

Một request có thể đi qua nhiều tầng:

~~~mermaid
flowchart LR
    A[HTTP request] --> B[WebFlux event loop]
    B --> C[Reactor pipeline]
    C --> D[Application worker / callback executor]
    C --> E[SDK client]
    E --> F[Connection pool / HTTP concurrency]
    F --> G[Cloud service]
    C --> H[Operator buffers / queues]
~~~

Mỗi tầng giữ một loại tài nguyên khác nhau:

| Tài nguyên | Đang giới hạn điều gì? | Khi quá tải |
| --- | --- | --- |
| Event-loop threads | Số thread điều phối I/O và callback | Một đoạn blocking có thể làm chậm nhiều request |
| Worker/executor threads | Số tác vụ CPU hoặc blocking callback chạy đồng thời | Queue tăng, task trễ hoặc bị reject |
| In-flight concurrency | Số request/operation đang được thực hiện | Request mới chờ hoặc bị từ chối |
| HTTP connection/channel | Số kết nối mạng hoặc stream đang hoạt động | Pool acquisition chậm hoặc timeout |
| Buffer/queue | Số item/byte đã nhận nhưng chưa xử lý | Heap/direct memory tăng, GC và OOM |
| Downstream quota | Khả năng xử lý thực tế của cloud service | Throttling, 429, retry và latency tăng |

Không dùng một con số để đại diện cho tất cả. Ví dụ `maxConnections=50` không có nghĩa ứng dụng chỉ xử lý được 50 request nếu HTTP/2 multiplex nhiều stream; `flatMap(concurrency=100)` cũng không có nghĩa có 100 TCP connections vì client có thể xếp các request trong pending queue.

## 3. Phân biệt thread, concurrency, connection và buffer

### 3.1. Thread

Thread là đơn vị thực thi code. Trong một pipeline async, thread có thể khởi tạo request, sau đó trả về event loop; callback hoàn tất có thể chạy trên một thread khác. Vì vậy, số request đang chờ I/O có thể lớn hơn số thread rất nhiều.

### 3.2. In-flight concurrency

Concurrency là số operation đã được khởi động nhưng chưa hoàn tất. Ví dụ `flatMap(..., 16)` cho phép tối đa 16 inner publisher đang hoạt động cùng lúc. Đây là giới hạn ở application pipeline; nó độc lập với giới hạn connection của SDK.

### 3.3. Connection hoặc HTTP/2 stream

Connection là kênh TCP/TLS tới endpoint. Với HTTP/1.1, một connection thường chỉ xử lý một request tại một thời điểm; với HTTP/2, nhiều stream có thể dùng chung một connection. gRPC cũng dùng HTTP/2 channel/stream. Phải đọc đúng ý nghĩa `maxConnections`, `maxConcurrency` hoặc channel pool của client đang dùng.

### 3.4. Buffer và queue

Buffer giữ dữ liệu đã được nhận nhưng chưa được xử lý hoặc chuyển tiếp. Buffer có thể nằm trong Reactor operator, Netty, SDK executor, R2DBC pool, message client hoặc chính ứng dụng. Một pipeline có nhiều tầng buffer; giới hạn ở một tầng không tự động giới hạn các tầng còn lại.

### 3.5. Backpressure

Backpressure là cơ chế để downstream báo upstream tốc độ mà nó có thể tiếp nhận. Reactive Streams biểu diễn demand qua `request(n)`. Nếu producer không thể giảm tốc, hệ thống phải chọn rõ một trong ba cách: **buffer**, **drop** hoặc **fail**. Không có chiến lược nào miễn phí.

Spring WebFlux sử dụng số event-loop thread nhỏ và giả định code không block. Reactive Streams cho phép subscriber điều khiển tốc độ publisher, nhưng chỉ hoạt động khi các publisher/operator trong pipeline hỗ trợ demand.

## 4. Tìm điểm không có giới hạn trong pipeline

Một pipeline có thể trông như reactive nhưng vẫn tích lũy công việc:

~~~java
ids.flatMap(id -> remoteClient.fetch(id));
~~~

Nếu nguồn phát nhanh, `flatMap` mặc định có thể cho phép nhiều inner publisher hoạt động đồng thời theo cấu hình mặc định của phiên bản Reactor. Khi downstream chậm, nhiều request đã được submit vẫn có thể chờ ở SDK/HTTP client. Nếu code chuyển mỗi item thành một `CompletableFuture` ngay lập tức rồi giữ trong list, application đã tạo một queue không có giới hạn trước khi Reactor kiểm soát được demand.

Hãy kiểm tra các điểm sau:

1. Nguồn dữ liệu có thể phát nhanh hơn consumer không?
2. Operator có `concurrency`, `prefetch` hoặc buffer hữu hạn không?
3. SDK client có giới hạn in-flight request và pending acquire không?
4. Executor có bounded queue không?
5. Message consumer có giới hạn outstanding message/byte không?
6. Connection pool có acquisition timeout không?
7. Khi caller timeout hoặc hủy, công việc downstream có được cancel/release không?

## 5. Reactor: giới hạn demand, concurrency và prefetch

### 5.1. Giới hạn số inner operation bằng flatMap

Ví dụ đọc nhiều item từ một repository reactive:

~~~java
import reactor.core.publisher.Flux;

public Flux<Product> loadProducts(Flux<String> productIds) {
    return productIds.flatMap(
        id -> productRepository.findById(id),
        16,
        8
    );
}
~~~

- `concurrency=16`: tối đa 16 inner publisher đang được subscribe.
- `prefetch=8`: số item được yêu cầu trước từ mỗi inner publisher trong operator này.

Prefetch không phải số connection và cũng không phải giới hạn byte. Nếu mỗi item lớn, prefetch 8 có thể tiêu tốn memory đáng kể. Với `Mono` chỉ trả một kết quả nhỏ, prefetch thường ít quan trọng hơn; với `Flux` nhiều item, hãy đo rõ.

### 5.2. Điều chỉnh request theo batch bằng limitRate

~~~java
Flux<Order> orders = orderRepository.findAll()
    .limitRate(64);
~~~

`limitRate` chia demand upstream thành các đợt nhỏ thay vì yêu cầu toàn bộ dữ liệu cùng lúc. Nó giúp điều tiết demand, nhưng không thay thế giới hạn connection pool, SDK concurrency hoặc bộ đệm của driver.

### 5.3. Bounded buffer và overflow policy

Nếu upstream không thể chậm lại, có thể dùng buffer hữu hạn và định nghĩa hành vi khi đầy:

~~~java
import reactor.core.publisher.BufferOverflowStrategy;

Flux<Event> safeEvents = eventSource
    .onBackpressureBuffer(
        256,
        dropped -> metrics.incrementBufferOverflow(),
        BufferOverflowStrategy.ERROR
    );
~~~

Khi buffer đầy, pipeline phát lỗi thay vì giữ dữ liệu vô hạn. Với telemetry có thể chấp nhận mất mẫu, chọn drop policy phù hợp; với lệnh nghiệp vụ hoặc message cần bảo đảm, không âm thầm drop. Dùng durable broker/queue và acknowledgment khi cần lưu trữ, replay hoặc retry.

Các lựa chọn:

| Chiến lược | Khi buffer đầy | Phù hợp |
| --- | --- | --- |
| Bounded buffer + ERROR | Kết thúc pipeline bằng lỗi | Cần phát hiện overload, không chấp nhận âm thầm mất dữ liệu |
| DROP_OLDEST | Bỏ item cũ nhất để nhận item mới | Telemetry/state snapshot mà dữ liệu mới quan trọng hơn |
| DROP_LATEST | Bỏ item vừa đến | Giữ thứ tự/độ mới của backlog hiện có |
| LATEST | Chỉ giữ giá trị mới nhất | UI state hoặc metric snapshot |
| Unbounded buffer | Tiếp tục nhận cho tới khi cạn memory | Tránh dùng trong production flow không có giới hạn đầu vào |

### 5.4. Buffer theo batch

~~~java
import java.time.Duration;
import java.util.List;
import reactor.core.publisher.Flux;

Flux<List<Event>> batches = eventSource.bufferTimeout(
    100,
    Duration.ofMillis(200)
);
~~~

Batch tối đa 100 event hoặc phát sau 200 ms. Batch giảm overhead request nhưng giữ item trong memory lâu hơn. Nếu payload có kích thước khác nhau, thêm giới hạn theo byte ở producer/consumer hoặc kiểm tra tổng kích thước batch trước khi gửi.

## 6. Scheduler và giới hạn thread trong Reactor

### 6.1. Chọn scheduler đúng loại công việc

| Scheduler | Mục đích | Không nên dùng cho |
| --- | --- | --- |
| `Schedulers.parallel()` | Công việc CPU-bound ngắn, không blocking | JDBC hoặc file/network blocking |
| `Schedulers.single()` | Tác vụ tuần tự/low-latency có chủ đích | Công việc blocking dài hoặc tải cao |
| `Schedulers.boundedElastic()` | Cầu nối cho API blocking | Thay thế driver non-blocking trong toàn bộ ứng dụng |
| Event loop | Điều phối I/O và callback | `Thread.sleep`, JDBC hoặc xử lý CPU dài |

Ví dụ cô lập một lời gọi JDBC legacy:

~~~java
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

Mono<Customer> customer = Mono.fromCallable(
        () -> jdbcRepository.findById(id)
            .orElseThrow(CustomerNotFoundException::new))
    .subscribeOn(Schedulers.boundedElastic());
~~~

Đây là bridge tạm thời; JDBC vẫn block một worker thread. Giới hạn boundedElastic không thay thế connection pool và không tăng khả năng xử lý của database.

### 6.2. boundedElastic cũng có queue

Reactor 3.8 mặc định giới hạn số thread của global `boundedElastic()` khoảng 10 lần số CPU khả dụng và queue tối đa mặc định 100.000 task cho mỗi backing thread. Đây là giá trị mặc định có thể thay đổi theo phiên bản/system property, không phải mục tiêu cấu hình production. Khi queue quá lớn, task có thể chờ lâu trước khi chạy; khi vượt giới hạn, scheduler reject task.

Với workload blocking riêng, có thể tạo scheduler có giới hạn cụ thể:

~~~java
import org.springframework.context.annotation.Bean;
import reactor.core.scheduler.Scheduler;
import reactor.core.scheduler.Schedulers;

@Bean(destroyMethod = "dispose")
Scheduler legacyIoScheduler() {
    return Schedulers.newBoundedElastic(
        24,
        200,
        "legacy-io"
    );
}
~~~

Ở đây có tối đa 24 backing thread và queue tối đa 200 task cho mỗi backing thread. Chọn giá trị theo thời gian blocking, số connection database và SLA. Không tăng queue lên hàng chục nghìn để che giấu việc downstream đang chậm.

### 6.3. Không dùng parallel scheduler cho blocking call

`parallel()` được tối ưu cho công việc CPU-bound ngắn. Nếu một task JDBC chiếm thread parallel, các tác vụ CPU khác trên cùng scheduler có thể bị đói. Chuyển blocking sang boundedElastic hoặc dùng driver non-blocking.

## 7. AWS SDK for Java 2.x: Netty concurrency và future executor

### 7.1. Hai nhóm thread khác nhau

AWS async client sử dụng Netty cho I/O và có `ExecutorService` để hoàn tất các `CompletableFuture`. Đây là hai vai trò khác nhau:

- Netty I/O threads xử lý socket/event.
- Future-completion executor chạy completion callback và các tác vụ hoàn tất future.

AWS SDK mặc định tạo thread pool cho mỗi async client dựa trên số processor và quản lý task trong queue. Async client dùng non-blocking I/O nhưng không bảo đảm toàn bộ đường gọi đều non-blocking: credential retrieval, SigV4 signing hoặc endpoint discovery có thể thực hiện blocking call.

### 7.2. Giới hạn concurrency và pending connection acquire

~~~java
import java.time.Duration;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.http.nio.netty.NettyNioAsyncHttpClient;
import software.amazon.awssdk.services.s3.S3AsyncClient;

S3AsyncClient s3 = S3AsyncClient.builder()
    .region(Region.US_EAST_1)
    .httpClientBuilder(NettyNioAsyncHttpClient.builder()
        .maxConcurrency(128)
        .maxPendingConnectionAcquires(256)
        .connectionAcquisitionTimeout(Duration.ofSeconds(2)))
    .build();
~~~

- `maxConcurrency` giới hạn số request đồng thời mà HTTP client hỗ trợ.
- `maxPendingConnectionAcquires` giới hạn request đang chờ connection/concurrency slot.
- `connectionAcquisitionTimeout` giới hạn thời gian chờ lấy slot.

Ý nghĩa của `maxConcurrency` phụ thuộc transport và protocol. AWS SDK metrics ghi rõ phạm vi theo HTTP client instance; Apache áp dụng cho toàn HTTP client, Netty/CRT áp dụng theo endpoint. Với HTTP/2, concurrency biểu diễn số stream chứ không nhất thiết số TCP connection.

### 7.3. Giới hạn future-completion executor

Khi callback thực hiện mapping nặng hoặc serialize response, có thể cấu hình executor riêng với queue hữu hạn:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.ThreadFactory;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import software.amazon.awssdk.core.client.config.SdkAdvancedAsyncClientOption;
import software.amazon.awssdk.http.nio.netty.NettyNioAsyncHttpClient;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3AsyncClient;

@Configuration(proxyBeanMethods = false)
class AwsAsyncConfiguration {
    @Bean(destroyMethod = "shutdown")
    ExecutorService awsCompletionExecutor() {
        AtomicInteger sequence = new AtomicInteger();
        ThreadFactory threadFactory = task -> {
            Thread thread = new Thread(
                task, "aws-future-" + sequence.incrementAndGet());
            thread.setDaemon(true);
            return thread;
        };
        return new ThreadPoolExecutor(
            16, 16, 30, TimeUnit.SECONDS,
            new ArrayBlockingQueue<>(400),
            threadFactory,
            new ThreadPoolExecutor.AbortPolicy());
    }

    @Bean(destroyMethod = "close")
    S3AsyncClient s3AsyncClient(ExecutorService awsCompletionExecutor) {
        return S3AsyncClient.builder()
            .region(Region.US_EAST_1)
            .httpClientBuilder(NettyNioAsyncHttpClient.builder()
                .maxConcurrency(128)
                .maxPendingConnectionAcquires(256))
            .asyncConfiguration(config -> config.advancedOption(
                SdkAdvancedAsyncClientOption.FUTURE_COMPLETION_EXECUTOR,
                awsCompletionExecutor))
            .build();
    }
}
~~~

Ví dụ đăng ký executor và S3 client thành Spring bean. Khi shutdown, Spring đóng service client phụ thuộc trước executor. Queue hữu hạn giúp overload được biểu hiện bằng rejection; vì đây là executor nội bộ của SDK, chỉ tùy chỉnh khi đã kiểm thử cách SDK báo lỗi khi queue đầy và có metrics cho rejection. Không dùng `CallerRunsPolicy` một cách tùy tiện vì callback có thể chạy trên thread I/O và chặn Netty.

Executor do ứng dụng tạo phải được shutdown trong lifecycle của Spring, sau khi SDK client đã ngừng gửi completion task. Nếu dùng `Executors.newFixedThreadPool` với queue không giới hạn, giới hạn thread nhưng vẫn có thể tích lũy task và memory không giới hạn.

### 7.4. CompletableFuture không có Reactive Streams backpressure

AWS async API trả `CompletableFuture`. Future cho biết một operation hoàn tất, nhưng không có demand protocol như `Flux.request(n)`. Nếu vòng lặp gọi SDK một triệu lần và lưu một triệu future, pipeline đã tạo một triệu operation/đối tượng trước khi có kết quả. Phải giới hạn số future đang hoạt động ở application layer bằng semaphore, bounded executor hoặc Reactor `flatMap` concurrency.

Khi tích hợp vào Reactor, tạo future bên trong mapper để concurrency được áp dụng trước khi gửi request:

~~~java
import software.amazon.awssdk.services.s3.model.GetObjectRequest;
import software.amazon.awssdk.core.ResponseBytes;
import software.amazon.awssdk.core.async.AsyncResponseTransformer;
import software.amazon.awssdk.services.s3.model.GetObjectResponse;
import software.amazon.awssdk.services.s3.S3AsyncClient;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

Mono<ResponseBytes<GetObjectResponse>> download(String bucket, String key) {
    return Mono.defer(() -> Mono.fromFuture(s3.getObject(
            GetObjectRequest.builder().bucket(bucket).key(key).build(),
            AsyncResponseTransformer.toBytes())));
}

Flux<ResponseBytes<GetObjectResponse>> downloads =
    Flux.fromIterable(keys).flatMap(
        key -> download(bucket, key),
        32);
~~~

Concurrency 32 giới hạn số future được tạo đồng thời trong pipeline này. Không gọi `download(...).subscribe()` trong vòng lặp.

## 8. Azure SDK for Java: Netty connection provider

Azure SDK for Java dùng `HttpClient` abstraction; Netty là HTTP client mặc định trong các Azure SDK libraries khi dependency tương ứng có mặt. Netty transport có thể được cấu hình qua `ConnectionProvider`.

### 8.1. Giới hạn connection và pending acquire

~~~java
import java.time.Duration;
import com.azure.core.http.HttpClient;
import com.azure.core.http.netty.NettyAsyncHttpClientBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import reactor.netty.resources.ConnectionProvider;

@Configuration(proxyBeanMethods = false)
class AzureAsyncTransportConfiguration {
    @Bean(destroyMethod = "dispose")
    ConnectionProvider azureConnectionProvider() {
        return ConnectionProvider.builder("azure-data")
            .maxConnections(80)
            .pendingAcquireMaxCount(160)
            .pendingAcquireTimeout(Duration.ofSeconds(2))
            .maxIdleTime(Duration.ofSeconds(30))
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

- `maxConnections`: số connection tối đa trong pool theo remote address.
- `pendingAcquireMaxCount`: số yêu cầu đang chờ lấy connection.
- `pendingAcquireTimeout`: thời gian chờ tối đa.
- `maxIdleTime`: thời gian connection có thể nhàn rỗi trước khi đóng.

ConnectionProvider custom là resource do ứng dụng sở hữu; dispose khi ApplicationContext shutdown. Không tạo provider cho từng service request. Các giới hạn transport này không thay thế giới hạn concurrency ở Reactor pipeline.

### 8.2. Đặt giới hạn ở hai tầng

~~~java
import java.nio.ByteBuffer;
import reactor.core.publisher.Flux;

Flux<ByteBuffer> chunks = blobAsyncClient
    .downloadStream()
    .limitRate(32);
~~~

Azure Blob `BlobAsyncClientBase.downloadStream()` trả `Flux<ByteBuffer>`; `download()` ở một số client API cũ đã deprecated hoặc trả response wrapper. `limitRate(32)` điều tiết demand của một download; nếu mở nhiều download đồng thời, còn phải giới hạn số publisher bằng `flatMap(..., concurrency)`. Khi đọc stream lớn, cần giới hạn đồng thời số download và số buffer bytes đang giữ; chỉ đặt max connection chưa đủ nếu ứng dụng mở hàng nghìn publisher cùng lúc.

Azure Netty builder có tùy chọn `disableBufferCopy(true)` để tránh deep-copy response ByteBuffer sang heap, nhưng Microsoft cảnh báo không bật tùy chọn này nếu downstream giữ buffer sau khi callback trả về: Netty có thể thu hồi/reuse bộ nhớ direct buffer và gây hỏng dữ liệu. Chỉ tối ưu copy sau khi đã đo memory và bảo đảm consumer xử lý ByteBuffer ngay trong vòng đời được phép.

## 9. Spring R2DBC: giới hạn database connection

Với R2DBC, mỗi connection đang sử dụng là một tài nguyên database. Reactive code có thể tạo nhiều request đồng thời nhưng database vẫn có giới hạn session, CPU, lock và I/O. Spring Boot cung cấp R2DBC pool properties khi có `r2dbc-pool`; mặc định max-size là 10 và `max-acquire-time` không có timeout nếu không cấu hình.

~~~yaml
spring:
  r2dbc:
    pool:
      enabled: true
      initial-size: 4
      min-idle: 2
      max-size: 24
      max-acquire-time: 2s
      max-create-connection-time: 3s
      max-idle-time: 10m
      max-life-time: 30m
      max-validation-time: 1s
~~~

Các giá trị chỉ là điểm khởi đầu để đo. Nếu có 5 pod với `max-size=24`, tổng số connection ứng dụng có thể mở tới 120, chưa tính migration, admin, monitoring hoặc worker khác. Giới hạn tổng phải thấp hơn connection budget mà database dành cho ứng dụng.

### 9.1. Pool acquisition là một hàng đợi

Khi pool đã đủ 24 connection, request thứ 25 có thể chờ connection được trả lại. Nếu transaction giữ connection lâu, pending acquire tăng. Đặt `max-acquire-time` để request không chờ vô hạn; khi hết hạn, trả lỗi overload có kiểm soát và có thể để caller retry sau backoff.

Không tăng pool size khi query chậm hoặc transaction giữ connection trong lúc gọi HTTP/Blob. Tăng pool có thể làm database có nhiều query cạnh tranh hơn, khiến latency xấu hơn. Trước hết đo connection usage time, query duration và lock wait.

### 9.2. Giữ transaction ngắn

Không giữ connection/transaction trong khi:

- Chờ một API HTTP khác.
- Download/upload object storage.
- Chờ message broker acknowledgment.
- Thực hiện xử lý CPU dài.
- Chờ người dùng hoặc timer.

Thực hiện I/O ngoài database trước/sau transaction nếu semantics cho phép; với side effect cần nhất quán, dùng outbox/saga thay vì giữ database connection trong suốt workflow.

## 10. Google Cloud Pub/Sub: flow control theo message và byte

Pub/Sub subscriber nhận message từ server và gọi handler. Nếu handler xử lý chậm hơn tốc độ message tới, số message chưa ack sẽ tăng. Google Cloud Pub/Sub flow control cho phép đặt giới hạn số outstanding message và tổng byte outstanding; khi một trong hai giới hạn bị vượt, subscriber tạm dừng pull cho tới khi message được ack/nack.

### 10.1. Cấu hình Java subscriber

~~~java
import com.google.api.gax.batching.FlowControlSettings;
import com.google.api.gax.core.ExecutorProvider;
import com.google.api.gax.core.InstantiatingExecutorProvider;
import com.google.cloud.pubsub.v1.MessageReceiver;
import com.google.cloud.pubsub.v1.Subscriber;
import com.google.pubsub.v1.ProjectSubscriptionName;

FlowControlSettings flowControl = FlowControlSettings.newBuilder()
    .setMaxOutstandingElementCount(500L)
    .setMaxOutstandingRequestBytes(32L * 1024L * 1024L)
    .build();

ExecutorProvider executorProvider =
    InstantiatingExecutorProvider.newBuilder()
        .setExecutorThreadCount(4)
        .build();

MessageReceiver receiver = (message, consumer) -> {
    try {
        processMessage(message);
        consumer.ack();
    } catch (RetryableException ex) {
        consumer.nack();
    }
};

Subscriber subscriber = Subscriber.newBuilder(
        ProjectSubscriptionName.of(projectId, subscriptionId),
        receiver)
    .setFlowControlSettings(flowControl)
    .setParallelPullCount(2)
    .setExecutorProvider(executorProvider)
    .build();

subscriber.startAsync().awaitRunning();
// Khi ứng dụng shutdown: subscriber.stopAsync().awaitTerminated();
~~~

500 là giới hạn message outstanding và 32 MiB là giới hạn tổng payload outstanding trong ví dụ. Chọn theo memory budget và thời gian xử lý. Ack sau khi xử lý nghiệp vụ hoàn tất; ack ngay khi nhận message sẽ làm flow control giải phóng slot quá sớm và có thể mất khả năng redelivery khi worker lỗi.

`projectId`, `subscriptionId`, `processMessage` và `RetryableException` là giá trị/kiểu do ứng dụng định nghĩa. Nack có thể khiến message được redeliver; lỗi không retry được nên được xử lý theo chính sách nghiệp vụ, ví dụ chuyển vào dead-letter topic hoặc ghi nhận kết quả thất bại rồi ack, tránh vòng lặp redelivery vô hạn.

### 10.2. Thread và message count là hai giới hạn riêng

Ví dụ mở 2 StreamingPull stream và dùng executor 4 thread cho mỗi stream, tương đương tối đa khoảng 8 thread xử lý callback theo cấu hình này. `setParallelPullCount` quyết định số stream; `setExecutorProvider` điều khiển executor xử lý message. Đây là hai giới hạn riêng với 500 outstanding message và 32 MiB flow control. Tăng stream/thread có thể tăng throughput nhưng cũng tăng CPU, memory và sức ép lên database.

Nếu handler blocking, không chạy nó trên event-loop thread của WebFlux. Nếu handler gọi database, concurrency handler không nên vượt quá connection pool và năng lực database. Nếu message xử lý 200 ms và 20 handler đồng thời, số message hoàn tất lý thuyết khoảng 100/giây trước khi xét network, retry và downstream.

### 10.3. Backlog broker và backlog client khác nhau

Flow control giới hạn message đã được client kéo về nhưng chưa ack. Message còn nằm trên subscription backlog phía Pub/Sub không chiếm heap của ứng dụng. Khi backlog tăng liên tục dù client đã đạt flow control, đó là dấu hiệu consumer capacity thấp hơn publish rate trong thời gian dài; cần scale subscriber hoặc tối ưu handler, không tăng outstanding limit vô hạn.

## 11. Tính buffer memory theo byte

Giới hạn theo số item có thể gây sai lệch khi payload có kích thước khác nhau. 500 message × 1 KB khác hoàn toàn 500 message × 2 MB.

Ước lượng thô:

**M ≈ N × S × K**

Trong đó:

- **N:** số item đang giữ đồng thời.
- **S:** kích thước payload trung bình hoặc p95 (byte).
- **K:** hệ số số bản sao/buffer của các tầng.

Ví dụ 200 payload × 256 KiB × 2 bản sao:

**M ≈ 200 × 256 KiB × 2 = 100 MiB**

Đây chỉ là ước lượng payload; chưa gồm object header, collection, ByteBuf allocator, TLS buffer, decompression, JSON tree và JVM overhead. Dùng p95/p99 payload size khi sizing, không chỉ average.

### 11.1. Heap và direct memory

Netty có thể dùng direct ByteBuf ngoài Java heap. Vì vậy, heap usage ổn định không chứng minh tổng memory an toàn. Theo dõi:

- JVM heap used/committed và GC pause.
- Direct buffer memory và Netty allocator metrics nếu bật.
- Container RSS/cgroup memory.
- Buffer/queue depth và payload bytes.
- Số request đang đọc/ghi stream.

Giới hạn container phải tính cả heap, direct memory, metaspace, thread stack và native library memory.

### 11.2. Đừng nhân buffer không cần thiết

Các thao tác `collectList()`, `buffer()`, `cache()`, `replay()` hoặc serialize toàn bộ payload có thể giữ thêm bản sao trong memory. Nếu response lớn, stream từng chunk hoặc page dữ liệu thay vì gom tất cả vào một list. Đọc body và giải phóng buffer theo contract của SDK.

## 12. Ước lượng concurrency và pool size

### 12.1. Little's Law

Số operation đang in-flight trung bình có thể ước lượng bằng:

**L = λ × W**

Trong đó **λ** là throughput (operation/giây), **W** là thời gian operation giữ tài nguyên (giây), **L** là số operation đang in-flight trung bình.

Ví dụ service xử lý 80 request/giây, mỗi request giữ database connection trung bình 0,15 giây:

**L = 80 × 0,15 = 12 connections**

12 là mức trung bình, không phải pool max. Cần thêm headroom theo burst/p95, nhưng không được vượt connection budget tổng của database.

### 12.2. Xác định bottleneck trước khi tăng thread

| Quan sát | Nút thắt có thể | Hành động |
| --- | --- | --- |
| Event loop bận, CPU cao | CPU work hoặc blocking trên event loop | Profile, chuyển CPU work đúng scheduler, loại bỏ blocking |
| Worker queue tăng, thread đều bận | Blocking dependency chậm | Giới hạn queue, tăng capacity có kiểm soát hoặc thay driver |
| Pool active chạm max, pending tăng | Downstream connection/pool thiếu hoặc operation giữ lâu | Đo thời gian giữ connection, tối ưu query, tính lại pool |
| Pool còn idle nhưng request pending | Concurrency/queue ở tầng khác | Kiểm tra SDK pending acquire, executor và operator buffer |
| Direct memory tăng | ByteBuf/response buffer/stream không được giải phóng | Kiểm tra body lifecycle, cancellation và buffer size |
| 429/throttling tăng | Cloud quota hoặc provisioned throughput | Giảm concurrency, retry backoff, tăng quota khi phù hợp |

Tăng thread khi downstream đã bão hòa thường làm tình hình tệ hơn vì thêm request tranh cùng connection/CPU/IOPS.

## 13. Timeout, cancellation và retry

Mỗi tầng nên có timeout riêng:

| Timeout | Mục tiêu |
| --- | --- |
| Pool acquire timeout | Không chờ vô hạn connection |
| Connect/TLS timeout | Giới hạn mở socket và handshake |
| Request/attempt timeout | Giới hạn một lần gọi dịch vụ |
| Overall API timeout | Giới hạn toàn bộ operation gồm retry |
| Queue wait timeout | Giới hạn thời gian task nằm trong queue |
| Business deadline | Giới hạn tổng thời gian request/message |

Khi caller hủy subscription hoặc timeout, kiểm tra SDK/driver có propagate cancellation xuống request hay không. Một số client có thể ngừng chờ response nhưng request đã gửi vẫn tiếp tục ở server. Giải phóng buffer/connection và không giả định cancellation đã rollback side effect.

Retry:

- Chỉ retry lỗi transient như connection reset, throttling hoặc service unavailable.
- Dùng exponential backoff và jitter.
- Giới hạn retry count và tổng deadline.
- Không retry authentication, authorization, validation hoặc schema error.
- Thao tác ghi cần idempotency key/conditional write hoặc kiểm tra trạng thái trước khi retry.

Không retry ở mọi tầng cùng lúc. SDK, application, gateway và message broker có thể cộng dồn retry, làm số request thực tế cao hơn nhiều so với traffic đầu vào.

## 14. Graceful shutdown và xử lý message đang dở

Khi ứng dụng shutdown:

1. Ngừng nhận request hoặc message mới.
2. Dừng pull/ingress để backlog không tiếp tục vào bộ nhớ.
3. Chờ operation đang in-flight trong một deadline.
4. Ack message chỉ khi xử lý thành công; message chưa xử lý thì nack/để hết ack deadline theo chính sách.
5. Hủy publisher/subscription còn hoạt động.
6. Đóng SDK client, connection pool, executor và scheduler do ứng dụng sở hữu.

Không shutdown executor trước khi SDK hoàn tất callback; không dispose Netty resource khi response body còn đang được đọc. Với Pub/Sub, dừng subscriber theo lifecycle và cho handler hoàn tất trong thời gian cho phép.

## 15. Quan sát overload và flow control

Theo dõi các chỉ số:

| Tầng | Metric |
| --- | --- |
| Reactor | Active subscriptions, requested demand, buffer overflow, scheduler queued tasks/rejected tasks |
| JVM | Live threads, blocked threads, CPU, heap, direct memory, GC pause |
| AWS SDK | MaxConcurrency, PendingConcurrencyAcquires, concurrency acquire duration, API attempt latency |
| Azure Netty | Active/idle connections, pending acquire count, pending acquire latency, connect timeout |
| R2DBC | Acquired/allocated/idle connections, pending acquire, acquire latency, query duration |
| Google Pub/Sub | Outstanding message count/bytes, ack latency, backlog age, redelivery, subscriber throughput |
| Cloud service | 429/throttling, quota, service latency, connection reset |

Đặt alert theo xu hướng và tỷ lệ bão hòa, ví dụ pending queue tăng liên tục, pool active giữ ở max, buffer overflow hoặc direct memory tiến sát container limit. Không chỉ alert khi CPU đạt 100%; async pipeline có thể cạn connection hoặc memory trong khi CPU còn thấp.

## 16. Kiểm thử overload và backpressure

### 16.1. Kiểm thử có kiểm soát

Tạo downstream giả lập với latency cố định, ví dụ 500 ms, rồi tăng tốc độ producer theo từng bước. Ghi:

- Số operation đang in-flight.
- Queue/buffer depth và tổng byte.
- Active/pending connection.
- Thread count, CPU, heap/direct memory.
- p95/p99 latency, timeout và error rate.

Xác minh khi vượt capacity, ứng dụng có chậm lại, từ chối có kiểm soát hoặc đẩy backlog về broker thay vì tăng memory vô hạn.

### 16.2. Kiểm thử Reactor demand

~~~java
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

StepVerifier.create(
        Flux.range(1, 100)
            .limitRate(8),
        0)
    .thenRequest(8)
    .expectNextCount(8)
    .thenCancel()
    .verify();
~~~

Ví dụ kiểm tra publisher chỉ được subscriber yêu cầu từng đợt. Với operator có prefetch, demand upstream có thể lớn hơn số item downstream đã tiêu thụ; kiểm tra hành vi thực tế của pipeline thay vì chỉ nhìn output cuối.

### 16.3. Kiểm thử Pub/Sub

Tạo publisher nhanh hơn subscriber, đặt max outstanding message và byte thấp trong môi trường test. Quan sát subscriber pause pull khi chạm limit, sau đó tiếp tục khi handler ack/nack. Kiểm tra message redelivery nếu handler thất bại.

## 17. Lỗi thường gặp

| Lỗi | Hệ quả | Cách sửa |
| --- | --- | --- |
| Cho rằng async nghĩa là không cần giới hạn | Future/request/queue tích tụ | Đặt concurrency và queue hữu hạn |
| Dùng `subscribe()` trực tiếp trong vòng lặp | Submit không giới hạn, mất backpressure | Compose publisher hoặc dùng semaphore/bounded executor |
| Chỉ giới hạn thread, queue vô hạn | Task chờ tích tụ và memory tăng | Bounded queue + timeout + rejection policy |
| Tăng maxConnections để sửa query chậm | Database bị thêm tải cạnh tranh | Tối ưu query/transaction và tính connection budget |
| Chỉ giới hạn connection, không giới hạn publisher | Nhiều request chờ trong pending queue | Giới hạn `flatMap` concurrency và SDK pending acquire |
| Buffer chỉ theo item count | Payload lớn gây OOM | Giới hạn cả count và byte |
| Dùng unbounded `onBackpressureBuffer` | Heap/direct memory tăng vô hạn | Bounded buffer với overflow policy rõ |
| Chặn event loop bằng JDBC hoặc `block()` | Tất cả request trên loop bị trễ | Driver non-blocking hoặc boundedElastic bridge |
| Ack Pub/Sub trước khi xử lý xong | Message lỗi nhưng không được redeliver | Ack sau khi business processing thành công |
| Retry đồng loạt không jitter | Retry storm, queue và connection cạn | Backoff, jitter, retry budget |
| Không đóng response stream | Connection/buffer không được giải phóng | Đóng/cancel stream trong mọi nhánh |
| Shutdown executor quá sớm | Callback bị mất hoặc request lỗi | Drain in-flight trước khi đóng resource |

## 18. Quy trình thiết kế giới hạn

~~~mermaid
flowchart TD
    A[Đo throughput và payload size] --> B[Đo thời gian giữ tài nguyên]
    B --> C[Ước lượng in-flight concurrency]
    C --> D[Chọn giới hạn connection và worker]
    D --> E[Đặt buffer count + byte + queue timeout]
    E --> F[Đặt deadline, cancellation và retry]
    F --> G[Load test với downstream chậm]
    G --> H{Queue và memory có hữu hạn?}
    H -->|Không| I[Giảm concurrency hoặc thêm flow control]
    I --> G
    H -->|Có| J[Theo dõi metrics và chốt alert]
~~~

Trước khi phát hành, trả lời:

1. Có bao nhiêu event-loop, worker và completion thread?
2. Bao nhiêu request có thể in-flight trên mỗi instance?
3. SDK/HTTP client có giới hạn connection và pending acquire không?
4. Tổng connection trên toàn bộ pod có nằm trong database/API budget không?
5. Mỗi buffer có giới hạn item count và byte không?
6. Queue overflow sẽ block, drop, fail hay chuyển sang durable broker?
7. Có timeout cho pool acquire, queue wait và request deadline không?
8. Cancellation có giải phóng resource downstream không?
9. Retry có idempotent và có budget không?
10. Metrics có thể phân biệt pool saturation, scheduler saturation và cloud throttling không?

## 19. Bài tập thực hành

**Bài tập 1 — Reactor concurrency.** Tạo Flux gồm 10.000 ID, gọi API giả lập có latency 200 ms. Chạy `flatMap` concurrency 4, 16 và 64; đo throughput, in-flight, p95 và memory.

**Bài tập 2 — Bounded buffer.** Tạo producer phát 1.000 event/giây và consumer xử lý 100 event/giây. Thử bounded buffer 200 item với ERROR, DROP_OLDEST và DROP_LATEST; quan sát số event mất và latency.

**Bài tập 3 — AWS async.** Cấu hình S3AsyncClient với `maxConcurrency=32`, pending acquire 64 và completion executor có queue 100. Tăng request đến khi xuất hiện acquire timeout/rejection; giải thích metric tương ứng.

**Bài tập 4 — Azure Netty.** Dùng ConnectionProvider maxConnections 20, pendingAcquireMaxCount 40 và timeout 1 giây. Tạo nhiều download song song; quan sát pending acquire và direct memory.

**Bài tập 5 — R2DBC pool.** Cấu hình max-size 12 trên mỗi pod, chạy 4 pod và tính tổng connection tối đa. Tạo transaction giữ connection 1 giây rồi đo pending acquire khi tải vượt pool.

**Bài tập 6 — Pub/Sub flow control.** Cấu hình subscriber tối đa 200 message và 16 MiB outstanding. Làm handler chậm 500 ms; quan sát pull pause, ack latency và backlog.

**Bài tập 7 — Byte budget.** So sánh 500 message 1 KiB với 500 message 1 MiB. Tính payload memory tối thiểu và thêm hệ số bản sao của serialization/buffer.

**Bài tập 8 — Retry storm.** Làm downstream trả 429 trong 5 giây. So sánh retry ngay lập tức với exponential backoff + jitter; đo pending queue, request amplification và p99.

**Bài tập 9 — Shutdown.** Dừng ứng dụng khi còn 50 message đang xử lý. Xác minh ingress dừng, handler hoàn tất trong deadline, message chưa ack được redeliver và resource được đóng đúng thứ tự.

## 20. Ghi nhớ

- Async giải phóng thread trong lúc chờ I/O nhưng không loại bỏ giới hạn CPU, connection, memory, quota hoặc thời gian xử lý.
- Giới hạn riêng **thread**, **in-flight concurrency**, **connection/channel** và **buffer/queue**; không dùng một con số thay cho tất cả.
- Reactor backpressure truyền demand qua Reactive Streams; nếu producer không giảm tốc, phải chọn buffer hữu hạn, drop hoặc fail.
- `flatMap(concurrency, prefetch)` và `limitRate` giúp điều tiết pipeline; `subscribe()` và `block()` có thể tạo unbounded demand.
- AWS async dùng Netty I/O thread và future-completion executor riêng; cấu hình maxConcurrency, pending acquire và bounded executor.
- Azure Netty ConnectionProvider giới hạn maxConnections, pendingAcquireMaxCount và pendingAcquireTimeout; vẫn cần giới hạn publisher ở application layer.
- Spring R2DBC pool cần max-size và max-acquire-time rõ ràng; tính tổng connection trên mọi pod.
- Google Pub/Sub flow control giới hạn cả outstanding message count và byte; ack sau khi xử lý thành công.
- Buffer memory phụ thuộc số item, payload size và số bản sao ở từng tầng; đo heap lẫn direct memory.
- Timeout, cancellation, retry budget và graceful shutdown là một phần của flow control, không phải việc bổ sung sau cùng.

## 21. Tài liệu tham khảo

- [Spring Framework — WebFlux concurrency model and Reactive Streams backpressure](https://docs.spring.io/spring-framework/reference/web/webflux/new-framework.html)
- [Project Reactor — Backpressure](https://projectreactor.io/docs/core/release/reference/subscribe-backpressure.html)
- [Project Reactor — Mono.fromFuture and lazy CompletableFuture integration](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html)
- [Project Reactor — Schedulers API and boundedElastic limits](https://projectreactor.io/docs/core/release/api/reactor/core/scheduler/Schedulers.html)
- [AWS SDK for Java 2.x — Asynchronous programming and executor options](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/asynchronous.html)
- [AWS SDK for Java 2.x — Metrics reference](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/metrics-list.html)
- [Azure SDK for Java — HTTP clients and pipelines](https://learn.microsoft.com/en-us/azure/developer/java/sdk/http-client-pipeline)
- [Azure SDK for Java — Netty HTTP client and connection pool](https://learn.microsoft.com/en-us/java/api/com.azure.core.http.netty.nettyasynchttpclientbuilder?view=azure-java-stable)
- [Azure Storage Blob Java — BlobAsyncClientBase streaming methods](https://learn.microsoft.com/en-us/java/api/com.azure.storage.blob.specialized.blobasyncclientbase?view=azure-java-stable)
- [Spring Boot 3.5 — R2DBC pool properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/)
- [R2DBC Pool — Configuration and lifecycle](https://github.com/r2dbc/r2dbc-pool)
- [Google Cloud Pub/Sub — Flow control for subscribers](https://docs.cloud.google.com/pubsub/docs/flow-control)
- [Google Cloud Pub/Sub — Concurrency control for subscribers](https://docs.cloud.google.com/pubsub/docs/concurrency-control)
- [Google Cloud Pub/Sub Java — Subscriber API](https://cloud.google.com/java/docs/reference/google-cloud-pubsub/latest/com.google.cloud.pubsub.v1.Subscriber)
