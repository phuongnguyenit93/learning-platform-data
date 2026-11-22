# Shutdown executor cùng server

## 1. Vì sao thứ tự shutdown quan trọng?

Trong **Spring gRPC**, server nhận RPC, dispatch callback lên executor và có thể giao công việc cho business worker, database client hoặc downstream gRPC channel. Khi ứng dụng dừng, các thành phần này có quan hệ phụ thuộc. Nếu executor bị đóng trước server, một RPC đang hoạt động có thể không còn thread để chạy callback hoặc hoàn tất response. Nếu server dừng quá muộn, ứng dụng tiếp tục nhận request trong lúc dependency và worker đã bắt đầu đóng.

Graceful shutdown cần bảo đảm:

- Ngừng nhận RPC mới.
- Cho các RPC đang chạy một khoảng thời gian hữu hạn để hoàn tất.
- Giữ callback executor và dependency sống trong lúc drain.
- Hủy các call còn treo khi hết grace period.
- Đóng outbound channel và worker executor sau khi không còn RPC cần chúng.
- Không để thread, queue hoặc task nền tiếp tục chạy ngoài lifecycle ứng dụng.

Nguyên tắc quan trọng là đóng thành phần ở phía ngoài trước, rồi mới đóng tài nguyên mà các request đang chạy phụ thuộc vào.

## 2. Trình tự shutdown đề xuất

Với một Spring gRPC service có server, outbound channel và executor, trình tự thường là:

1. **Rút khỏi traffic:** đánh dấu instance không còn ready và chờ load balancer/service discovery ngừng gửi request mới.
2. **Dừng nhận RPC:** gọi gRPC Server.shutdown() để bắt đầu graceful shutdown.
3. **Drain RPC đang chạy:** chờ trong grace period đã cấu hình; các call hiện hữu được phép hoàn tất.
4. **Force nếu quá hạn:** gọi Server.shutdownNow() để hủy các call còn hoạt động, rồi chờ thêm một khoảng ngắn.
5. **Đóng outbound channel:** chỉ sau khi handler không còn cần gọi downstream; chờ channel kết thúc trước khi đóng callback executor mà channel dùng.
6. **Đóng business executor:** ngừng nhận task mới, chờ task đã nhận hoàn tất; nếu hết thời gian thì shutdownNow và ghi nhận task còn trong queue.
7. **Xác minh kết thúc:** ghi log/metric nếu server, channel hoặc executor chưa terminate đúng hạn.

~~~mermaid
flowchart TD
    A[Mark instance not ready] --> B[Wait for traffic drain]
    B --> C[Server.shutdown]
    C --> D{In-flight RPCs drained?}
    D -->|Yes| E[Shutdown outbound channels]
    D -->|No, grace period expired| F[Server.shutdownNow]
    F --> G[Wait short forced-stop period]
    G --> E
    E --> H[Shutdown callback and worker executors]
    H --> I[Await termination / report leftovers]
~~~

Thời gian trong mỗi bước phải nằm trong tổng ngân sách shutdown của nền tảng. Nếu Kubernetes hoặc process supervisor chỉ cho ứng dụng một khoảng thời gian ngắn trước khi gửi SIGKILL, tổng grace period nội bộ phải nhỏ hơn khoảng thời gian đó và dành lại thời gian cho cleanup cuối.

## 3. Server.shutdown và Server.shutdownNow

Hai phương thức có semantics khác nhau:

| API | Hành vi | Khi dùng |
| --- | --- | --- |
| Server.shutdown() | Bắt đầu dừng server một cách có trật tự; không nhận call mới và cho call đang chạy cơ hội kết thúc | Bước đầu của graceful shutdown |
| Server.awaitTermination(timeout, unit) | Chờ server terminate tối đa thời gian chỉ định | Drain có giới hạn |
| Server.shutdownNow() | Yêu cầu dừng ngay và hủy các call đang hoạt động | Fallback khi drain quá hạn |
| Server.isTerminated() | Cho biết server đã kết thúc chưa | Xác minh lifecycle |

shutdownNow không bảo đảm mọi đoạn code ứng dụng lập tức dừng. Server gửi tín hiệu cancellation tới call; handler, database operation và task nền phải hợp tác kiểm tra cancellation hoặc có timeout riêng. Một JDBC call đang block hoặc một thư viện bỏ qua interrupt có thể tiếp tục chạy sau khi RPC bị hủy.

Không gọi shutdownNow ngay khi nhận SIGTERM nếu muốn cho request đang chạy hoàn tất. Cũng không chờ vô hạn: một RPC bị treo có thể giữ process không shutdown được.

## 4. Vì sao phải giữ executor sống trong lúc drain?

Server cần executor để dispatch listener callbacks và tiếp tục xử lý các RPC đang hoạt động. Handler cũng có thể cần business worker để hoàn tất truy vấn hoặc tác vụ đã nhận. Nếu executor bị shutdown trước khi server drain:

- Callback completion có thể bị từ chối vì executor không nhận task mới.
- Response cuối có thể không được gửi.
- Cancellation handler có thể không chạy đúng lúc.
- Task đã nằm trong queue có thể không được thực hiện.
- Log và metric cuối cùng có thể không được flush.

Vì vậy, gọi Server.shutdown trước, chờ server kết thúc, rồi mới shutdown executor phục vụ server. Nếu executor được dùng chung cho nhiều thành phần, chỉ đóng nó khi tất cả thành phần phụ thuộc đã dừng.

Không nhầm executor callback của gRPC với business worker executor. Chúng có thể là hai pool riêng và cần lifecycle riêng. Giữ callback executor hoạt động cho tới khi server/channel đã hoàn tất; business executor phải tiếp tục phục vụ những tác vụ mà RPC đang drain còn cần.

## 5. Cấu hình executor có giới hạn

Ví dụ Spring tạo callback executor và worker executor riêng:

~~~java
import java.util.concurrent.ThreadPoolExecutor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
public class GrpcExecutorConfiguration {

    @Bean
    ThreadPoolTaskExecutor grpcServerExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(8);
        executor.setMaxPoolSize(16);
        executor.setQueueCapacity(128);
        executor.setThreadNamePrefix("grpc-server-");
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        return executor;
    }

    @Bean
    ThreadPoolTaskExecutor grpcBusinessExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(12);
        executor.setMaxPoolSize(24);
        executor.setQueueCapacity(96);
        executor.setThreadNamePrefix("grpc-business-");
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        return executor;
    }
}
~~~

Các giá trị trên chỉ minh họa. Pool thực tế phải được sizing theo CPU, số connection database, downstream capacity, latency và số replica. Queue cần hữu hạn để backlog không tăng vô hạn; khi quá tải, service trả status phù hợp thay vì âm thầm bỏ task.

Không dùng CallerRunsPolicy tùy tiện cho callback executor. Khi queue đầy, policy này có thể chạy business task trên thread submit là thread callback gRPC, khiến việc xử lý RPC khác bị chặn.

## 6. Tạo server với executor do Spring quản lý

Nếu ứng dụng tự quản lý Netty gRPC server, có thể gắn executor vào builder:

~~~java
import io.grpc.Server;
import io.grpc.netty.NettyServerBuilder;
import java.io.IOException;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
public class GrpcServerConfiguration {

    @Bean(destroyMethod = "")
    Server catalogGrpcServer(
            @Qualifier("grpcServerExecutor")
            ThreadPoolTaskExecutor grpcServerExecutor,
            CatalogServiceImpl catalogService) throws IOException {
        return NettyServerBuilder.forPort(9090)
                .executor(grpcServerExecutor)
                .addService(catalogService)
                .build()
                .start();
    }
}
~~~

Ở đây destroyMethod được để rỗng vì một lifecycle coordinator sẽ sở hữu trình tự shutdown của server. Tránh để nhiều bean tự shutdown cùng một tài nguyên theo thứ tự không rõ ràng.

Nếu Spring gRPC phiên bản dự án tự tạo và quản lý server, không tạo thêm Netty server riêng. Hãy gắn executor và graceful shutdown vào server builder/customizer hoặc lifecycle extension được phiên bản đó hỗ trợ. Tên property và API tích hợp có thể thay đổi giữa các phiên bản.

## 7. Coordinator quản lý graceful shutdown

Một component có thể điều phối server và executor trong một nơi. Ví dụ dùng Spring lifecycle callback:

~~~java
import jakarta.annotation.PreDestroy;
import io.grpc.Server;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Component;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Component
public final class GrpcShutdownCoordinator {

    private static final Logger log =
            LoggerFactory.getLogger(GrpcShutdownCoordinator.class);

    private final Server server;
    private final ThreadPoolTaskExecutor grpcServerExecutor;
    private final ThreadPoolTaskExecutor grpcBusinessExecutor;

    public GrpcShutdownCoordinator(
            Server server,
            @Qualifier("grpcServerExecutor")
            ThreadPoolTaskExecutor grpcServerExecutor,
            @Qualifier("grpcBusinessExecutor")
            ThreadPoolTaskExecutor grpcBusinessExecutor) {
        this.server = server;
        this.grpcServerExecutor = grpcServerExecutor;
        this.grpcBusinessExecutor = grpcBusinessExecutor;
    }

    @PreDestroy
    public void shutdown() {
        log.info("Starting graceful gRPC shutdown");
        server.shutdown();

        boolean terminated = awaitServer(25, TimeUnit.SECONDS);
        if (!terminated) {
            log.warn("gRPC server drain timed out; forcing shutdown");
            server.shutdownNow();
            terminated = awaitServer(5, TimeUnit.SECONDS);
        }

        if (!terminated) {
            log.error("gRPC server did not terminate within shutdown budget");
        }

        // Không đóng callback executor trước khi server đã được drain.
        shutdownExecutor("grpc-server", grpcServerExecutor, 10);
        shutdownExecutor("grpc-business", grpcBusinessExecutor, 15);
    }

    private boolean awaitServer(long timeout, TimeUnit unit) {
        try {
            return server.awaitTermination(timeout, unit);
        } catch (InterruptedException error) {
            Thread.currentThread().interrupt();
            return false;
        }
    }

    private void shutdownExecutor(
            String name,
            ThreadPoolTaskExecutor executor,
            long timeoutSeconds) {
        executor.shutdown();
        ThreadPoolExecutor pool = executor.getThreadPoolExecutor();
        try {
            if (!pool.awaitTermination(timeoutSeconds, TimeUnit.SECONDS)) {
                int queued = pool.shutdownNow().size();
                log.warn("{} executor forced to stop; {} queued tasks returned",
                        name, queued);
                if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                    log.error("{} executor still has active workers", name);
                }
            }
        } catch (InterruptedException error) {
            int queued = pool.shutdownNow().size();
            log.warn("{} executor interrupted during shutdown; {} queued tasks returned",
                    name, queued);
            Thread.currentThread().interrupt();
        }
    }
}
~~~

Đây là ví dụ coordinator tối giản cho một server và hai executor. Trong hệ thống thực, cần bổ sung readiness/traffic drain và outbound channel lifecycle; các timeout 25/5/10/15 giây phải được điều chỉnh theo shutdown budget của nền tảng.

Ví dụ dùng jakarta.annotation.PreDestroy theo Spring Boot 3/Jakarta. Với ứng dụng Spring cũ còn dùng Java EE namespace, import annotation tương ứng theo phiên bản. Nếu dự án quản lý server bằng SmartLifecycle hoặc lifecycle extension của Spring gRPC, hãy đặt cùng trình tự drain vào lifecycle đó thay vì thêm một hook thứ hai.

Spring hủy bean phụ thuộc trước bean mà nó phụ thuộc vào. Coordinator inject server và executor nên được hủy trước các dependency đó. Việc tắt destroyMethod tự động của Server trong ví dụ giúp tránh hai nơi cùng sở hữu shutdown. Executor vẫn có thể được Spring đóng lần nữa khi bean bị destroy; shutdown lần hai trên executor đã dừng là an toàn, nhưng nên có một lifecycle owner rõ ràng để log và timeout không bị phân tán.

Nếu shutdown bị interrupt, ví dụ chuyển sang force stop và khôi phục interrupt flag. Trong production, có thể dùng helper await-uninterruptibly có giới hạn thời gian để vẫn dành một phần ngân sách cho cleanup các thành phần còn lại, sau đó khôi phục interrupt flag.

## 8. Đóng outbound ManagedChannel đúng thời điểm

Một server handler có thể đang gọi downstream qua ManagedChannel. Nếu đóng channel trước khi inbound RPC drain xong, request đang chạy có thể không gọi được dependency để hoàn tất.

Thứ tự cho outbound channel:

1. Ngừng nhận inbound RPC mới.
2. Drain inbound server để handler hiện tại hoàn tất các downstream call.
3. Gọi ManagedChannel.shutdown() cho từng channel.
4. Chờ channel terminate trong thời gian giới hạn.
5. Nếu quá hạn, gọi shutdownNow() và chờ thêm một khoảng ngắn.
6. Sau khi channel kết thúc, mới đóng executor chuyên dùng cho callback của channel.

Ví dụ:

~~~java
private boolean shutdownChannel(
        String name,
        ManagedChannel channel,
        long graceSeconds) {
    channel.shutdown();
    try {
        if (channel.awaitTermination(graceSeconds, TimeUnit.SECONDS)) {
            return true;
        }
        log.warn("{} channel drain timed out", name);
        channel.shutdownNow();
        return channel.awaitTermination(5, TimeUnit.SECONDS);
    } catch (InterruptedException error) {
        channel.shutdownNow();
        Thread.currentThread().interrupt();
        return false;
    }
}
~~~

Nếu channel dùng executor chung với server, chỉ shutdown executor sau khi cả server lẫn channel đã terminate. Không shutdown callback executor trong lúc channel vẫn có thể phát callback.

## 9. Readiness, load balancer và grace period

Server.shutdown() ngăn server nhận call mới ở tầng gRPC, nhưng hạ tầng phía trước vẫn cần biết instance đang rời traffic. Trong môi trường có service discovery hoặc Kubernetes:

- Đánh dấu readiness false trước khi bắt đầu drain.
- Chờ endpoint controller/load balancer cập nhật và ngừng gửi traffic mới.
- Dành một khoảng thời gian nhỏ cho connection đang mở và request đang trên đường tới instance.
- Sau đó mới gọi Server.shutdown().

Readiness drain và gRPC graceful shutdown giải quyết hai phạm vi khác nhau: readiness ngăn routing mới ở hạ tầng; Server.shutdown ngăn call mới tại server. Dùng cả hai giúp giảm lỗi UNAVAILABLE trong lúc rollout.

Tổng thời gian cần nằm trong termination grace period của nền tảng:

| Giai đoạn | Ví dụ ngân sách |
| --- | ---: |
| Readiness propagation / load balancer drain | 5 giây |
| Graceful RPC drain | 25 giây |
| Force-stop và chờ server | 5 giây |
| Channel/executor cleanup | 15 giây |
| Tổng | 50 giây |

Đây chỉ là ví dụ. Cần chừa thời gian dự phòng trước khi nền tảng gửi SIGKILL. Nếu platform chỉ cho 30 giây, không thể cấu hình các bước nội bộ tổng cộng 50 giây.

## 10. Tác vụ nền và công việc tách khỏi RPC

Server termination không tự chứng minh mọi task mà RPC từng khởi tạo đã kết thúc. Một handler có thể submit công việc fire-and-forget rồi trả response ngay; task đó không còn nằm trong vòng đời RPC.

Với công việc cần bảo đảm hoàn tất:

- Theo dõi task bằng registry hoặc job system có lifecycle riêng.
- Không giữ task quan trọng chỉ trong in-memory queue nếu process có thể dừng bất kỳ lúc nào.
- Dùng durable queue/outbox khi công việc phải tiếp tục sau restart.
- Khi shutdown, ngừng nhận task mới và drain task đang chạy trong ngân sách riêng.
- Task phải có deadline, cancellation token hoặc timeout dependency.
- Không chờ vô hạn một task không có cơ chế dừng.

Nếu business executor chỉ phục vụ RPC và handler chờ task hoàn tất trước khi đóng response, server drain thường sẽ giữ executor cần thiết cho tới khi call kết thúc. Nếu task sống lâu hơn RPC, cần lifecycle và durability riêng; không dựa vào Server.awaitTermination để quản lý nó.

## 11. Xử lý task còn trong queue khi force shutdown

ThreadPoolExecutor.shutdown() ngừng nhận task mới nhưng vẫn cho task đã submit chạy hết. shutdownNow() yêu cầu dừng task đang chạy và trả về danh sách task chưa bắt đầu trong queue.

Các điểm cần lưu ý:

- shutdownNow không bảo đảm thread đang block trong thư viện bên ngoài sẽ dừng ngay.
- Task được trả về từ queue chưa chạy; cần log số lượng và xác định có thể bỏ hay phải lưu lại.
- Không âm thầm discard task nghiệp vụ quan trọng.
- Nếu task có thể retry sau restart, lưu vào durable queue trước khi acknowledge RPC.
- Nếu task chỉ là callback phục vụ RPC đã bị hủy, cancellation/terminal guard phải ngăn callback phát response muộn.

Với task đang chạy, dùng timeout riêng cho database/HTTP client và kiểm tra cancellation giữa các bước. Interrupt chỉ có tác dụng với code và thư viện hỗ trợ interruption.

## 12. Quan sát shutdown

Nên phát log và metric theo từng giai đoạn:

| Signal | Ý nghĩa |
| --- | --- |
| grpc.shutdown.started | Coordinator bắt đầu shutdown |
| grpc.readiness.disabled | Instance đã rút khỏi traffic |
| grpc.server.drain.duration | Thời gian server drain |
| grpc.server.inflight_at_shutdown | Số RPC đang hoạt động khi bắt đầu drain |
| grpc.server.force_shutdown | Số lần phải dùng shutdownNow |
| grpc.channel.shutdown.duration | Thời gian outbound channel terminate |
| executor.active_at_shutdown | Worker đang chạy khi shutdown |
| executor.queue_at_shutdown | Task còn chờ trong queue |
| executor.rejected | Task bị từ chối khi pool đã đầy hoặc đang dừng |
| grpc.shutdown.incomplete | Thành phần không terminate trong ngân sách |

Log nên có component name, thời gian chờ, số task còn queue và trạng thái terminate. Không đưa request ID hoặc tenant ID vào metric label; dùng log/trace khi cần điều tra một request cụ thể.

Một shutdown thành công không chỉ là process đã thoát. Cần biết server có drain bình thường hay bị force, executor có task bị bỏ lại không và dependency channel có kết thúc trước deadline của nền tảng không.

## 13. Kiểm thử graceful và forced shutdown

Integration test nên dùng server/channel thật hoặc in-process transport tùy mục tiêu. Với transport test, có thể dùng latch để giữ một RPC đang chạy rồi bắt đầu shutdown:

~~~java
CountDownLatch handlerStarted = new CountDownLatch(1);
CountDownLatch releaseHandler = new CountDownLatch(1);

// Trong test service:
handlerStarted.countDown();
releaseHandler.await();
responseObserver.onNext(response);
responseObserver.onCompleted();

// Trong test:
assertTrue(handlerStarted.await(2, TimeUnit.SECONDS));
server.shutdown();
assertFalse(server.awaitTermination(100, TimeUnit.MILLISECONDS));
releaseHandler.countDown();
assertTrue(server.awaitTermination(2, TimeUnit.SECONDS));
~~~

Đây là pseudocode cho test phối hợp bằng latch; cần đặt await trong try/finally để luôn release latch nếu assertion thất bại. Không dùng sleep cố định để đoán handler đã bắt đầu.

Các kịch bản nên kiểm tra:

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| Không có RPC đang chạy | Server terminate nhanh sau shutdown |
| Unary RPC đang xử lý | RPC hoàn tất trong grace period |
| Streaming RPC còn mở | Stream được phép drain hoặc bị hủy khi grace period hết |
| RPC bị treo quá grace period | shutdownNow được gọi và cancellation tới handler |
| Executor có task đang chạy | Task được drain hoặc force theo timeout |
| Executor queue đầy | Task mới bị reject rõ ràng, không bị âm thầm mất |
| Outbound call đang chạy | Channel còn sống cho tới khi inbound handler hoàn tất |
| Readiness đã false | Instance không nhận traffic mới từ load balancer |
| Task nền độc lập RPC | Lifecycle riêng drain/persist task đúng contract |
| Shutdown bị interrupt | Force path được kích hoạt và interrupt flag được khôi phục |

Kiểm tra cả thread leak sau test suite. Một server đã terminate nhưng executor còn worker non-daemon có thể làm test process không thoát.

## 14. Sai lầm thường gặp

1. **Shutdown executor trước server.** Callback của RPC đang chạy có thể không còn thread để hoàn tất.
2. **Gọi shutdownNow ngay lập tức.** Các request hợp lệ bị hủy dù còn thời gian drain.
3. **Chờ server vô hạn.** Một call treo có thể giữ process mãi.
4. **Đóng downstream channel trước inbound server.** Handler đang drain mất dependency cần thiết.
5. **Cho rằng server terminate nghĩa là mọi background task đã xong.** Task fire-and-forget có lifecycle riêng.
6. **Bỏ qua readiness/load balancer drain.** Request mới vẫn có thể được định tuyến tới instance đang dừng.
7. **Không kiểm soát tổng grace period.** Platform có thể SIGKILL trước khi cleanup nội bộ hoàn tất.
8. **Không xử lý task trả về từ shutdownNow.** Công việc đã nhận có thể bị mất.
9. **Có nhiều bean cùng sở hữu shutdown.** Thứ tự đóng tài nguyên khó dự đoán và log trùng lặp.
10. **Không test forced shutdown và thread leak.** Lỗi chỉ xuất hiện khi rollout hoặc process bị dừng thật.

## 15. Bài tập vận dụng

Với một Spring gRPC service có server, downstream channel và hai executor:

1. Tạo callback executor và business executor riêng, queue hữu hạn.
2. Xây lifecycle coordinator để đánh dấu readiness false, gọi Server.shutdown và chờ drain.
3. Khi grace period hết, gọi Server.shutdownNow và xác minh cancellation tới handler.
4. Chỉ sau khi server drain, shutdown outbound ManagedChannel và chờ channel terminate.
5. Shutdown executor cuối cùng; nếu hết timeout, dùng shutdownNow và ghi số task còn queue.
6. Tạo một RPC có latch để chứng minh request đang chạy được phép hoàn tất trong graceful period.
7. Tạo một RPC treo để kiểm tra forced shutdown.
8. Kiểm tra tổng thời gian shutdown không vượt termination grace period của môi trường chạy.
9. Thu thập metric cho drain duration, force shutdown, active workers và queue leftovers.

**Tiêu chí hoàn thành:** người học giải thích được thứ tự shutdown giữa server, channel và executor; triển khai drain có giới hạn thời gian; xử lý force-stop và task còn queue; phối hợp readiness với platform termination grace period; và kiểm thử được graceful lẫn forced shutdown.

### Tài liệu tham khảo

- [gRPC Java Server API](https://grpc.github.io/grpc-java/javadoc/io/grpc/Server.html): shutdown, shutdownNow và awaitTermination.
- [gRPC Java ManagedChannel API](https://grpc.github.io/grpc-java/javadoc/io/grpc/ManagedChannel.html): graceful shutdown của client channel.
- [Java ThreadPoolExecutor](https://docs.oracle.com/en/java/javase/): shutdown, shutdownNow và awaitTermination.
- [Spring ThreadPoolTaskExecutor](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html): lifecycle executor trong Spring.
- [Spring Bean Lifecycle](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html): destroy callbacks và bean lifecycle.
- [Spring gRPC Reference](https://docs.spring.io/spring-grpc/reference/): tích hợp server/client gRPC trong Spring.
