# Shutdown executor cùng server

## 1. Shutdown là một quy trình phối hợp

Trong **Spring gRPC**, server nhận RPC và dispatch listener callback lên executor. Handler có thể tiếp tục dùng business worker, database pool và outbound ManagedChannel để hoàn tất request. Khi Spring ApplicationContext đóng, các thành phần này không thể dừng tùy ý theo thứ tự độc lập.

Nếu executor dừng trước server, callback của RPC đang chạy có thể không còn thread để hoàn tất. Nếu outbound channel đóng trước khi handler drain xong, một request hợp lệ có thể mất khả năng gọi dependency. Nếu server vẫn nhận traffic trong lúc worker đã đóng, caller sẽ gặp lỗi không nhất quán.

Một quy trình shutdown có kiểm soát cần:

- Ngừng đưa instance vào traffic mới.
- Dừng nhận RPC mới tại gRPC server.
- Giữ callback executor và dependency cần thiết trong lúc RPC hiện tại drain.
- Hủy call còn treo khi grace period kết thúc.
- Đóng outbound channel sau khi handler không còn cần chúng.
- Đóng executor theo đúng dependency và chờ terminate trong thời gian hữu hạn.
- Ghi nhận task còn trong queue hoặc worker không dừng được.

Nguyên tắc là **dừng nguồn tạo công việc trước, rồi mới dừng tài nguyên thực thi công việc đó**.

## 2. Xác định quyền sở hữu lifecycle

Trước khi viết shutdown hook, xác định ai sở hữu từng tài nguyên:

| Thành phần | Chủ sở hữu lifecycle | Điều cần phối hợp |
| --- | --- | --- |
| Spring gRPC server | Spring gRPC auto-configuration hoặc ứng dụng tự tạo | Chỉ một nơi gọi shutdown |
| Server callback executor | Spring bean hoặc server factory | Sống cho tới khi server drain xong |
| Business worker executor | Application configuration | Sống trong lúc handler còn cần worker |
| Outbound ManagedChannel | Client configuration/component | Sống cho tới khi inbound handler đã hoàn tất downstream call |
| Client callback executor | Client channel configuration | Sống cho tới khi channel terminate |
| Background job executor | Job subsystem riêng | Có lifecycle và durability riêng nếu job vượt vòng đời RPC |

Không tạo thêm một Netty server nếu Spring gRPC đã tự tạo và quản lý server. Khi dùng auto-configuration, hãy tích hợp vào lifecycle extension/customizer mà phiên bản dự án hỗ trợ. Nếu ứng dụng tự tạo server, cần tắt destroy callback tự động của bean server và giao việc shutdown cho một coordinator duy nhất.

Tránh để cả Spring bean destroy method, gRPC server factory và một custom @PreDestroy cùng gọi shutdown mà không có quy ước. Nhiều owner có thể làm timeout bị cộng dồn, log trùng hoặc executor bị đóng trước khi server drain.

## 3. Trình tự shutdown và quan hệ phụ thuộc

Với một instance có gRPC server, outbound channel và hai executor, trình tự tổng quát:

1. **Readiness false:** báo cho service discovery/load balancer rằng instance không nhận traffic mới.
2. **Traffic drain:** chờ endpoint propagation và request đang trên đường tới instance kết thúc trong một khoảng ngắn.
3. **Server shutdown:** gọi Server.shutdown() để ngừng nhận call mới và cho call hiện hữu hoàn tất.
4. **Server drain:** chờ server terminate trong grace period.
5. **Force stop:** nếu hết thời gian, gọi Server.shutdownNow() và chờ thêm một khoảng ngắn.
6. **Outbound channels:** sau khi inbound handlers đã drain, shutdown các ManagedChannel mà chúng sử dụng.
7. **Executors:** đóng client callback executor sau client channel; đóng business worker và server callback executor khi các thành phần phụ thuộc đã dừng.
8. **Verify:** ghi nhận thành phần chưa terminate, task còn queue và tổng thời gian shutdown.

~~~mermaid
flowchart TD
    A[Mark instance not ready] --> B[Wait for routing drain]
    B --> C[Server.shutdown]
    C --> D{Server terminated?}
    D -->|No, grace period expired| E[Server.shutdownNow]
    E --> F[Wait forced-stop interval]
    D -->|Yes| G[Shutdown outbound channels]
    F --> G
    G --> H[Await channel termination]
    H --> I[Shutdown client callback executor]
    I --> J[Shutdown business and server executors]
    J --> K[Verify termination and leftovers]
~~~

Sơ đồ giả định background job không dùng chung outbound channel hoặc business executor sau khi server drain. Nếu có job độc lập, phải drain job subsystem trước khi đóng các tài nguyên mà job đó cần.

## 4. Server.shutdown và shutdownNow

| API | Hành vi | Vị trí trong quy trình |
| --- | --- | --- |
| Server.shutdown() | Bắt đầu graceful shutdown, không nhận call mới và cho call hiện tại hoàn tất | Bước đầu dừng server |
| Server.awaitTermination(timeout, unit) | Chờ server kết thúc tối đa thời gian chỉ định | Drain có giới hạn |
| Server.shutdownNow() | Yêu cầu hủy các call đang hoạt động và dừng server ngay | Fallback khi hết grace period |
| Server.isTerminated() | Kiểm tra server đã terminate chưa | Xác minh kết quả |

shutdownNow không cưỡng bức dừng mọi đoạn code Java. Nó yêu cầu gRPC hủy call; service phải quan sát cancellation và dừng công việc có thể dừng. JDBC driver, HTTP client hoặc thư viện blocking có thể tiếp tục chạy nếu không có timeout/interruption phù hợp.

Không chờ server vô hạn. Một stream không bao giờ hoàn tất hoặc dependency bị treo có thể giữ process không thoát. Mọi bước await cần timeout nhỏ hơn ngân sách shutdown của nền tảng.

## 5. Giữ executor sống trong lúc drain

Server callback executor phải còn hoạt động cho tới khi server đã terminate. Business worker cũng cần tiếp tục chạy nếu handler đang chờ kết quả từ worker trước khi gửi response cuối.

Nếu shutdown executor quá sớm:

- Callback có thể bị từ chối vì executor không nhận task mới.
- Response cuối hoặc terminal callback có thể không được gửi.
- Cancellation handler và cleanup callback có thể bị trì hoãn.
- Task đã nhận nhưng đang ở queue có thể không được xử lý.

Không nhầm server callback executor với business worker executor. Chúng có thể là hai pool riêng. Client callback executor của outbound channel lại là một lifecycle khác; chỉ đóng nó sau khi channel đã terminate.

## 6. Cấu hình executor riêng trong Spring

Ví dụ khai báo callback executor và business worker executor với queue hữu hạn:

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

Các con số chỉ minh họa. Sizing cần dựa trên CPU, số connection database, downstream capacity, latency và số replica. Queue hữu hạn giúp backlog không tăng vô hạn; khi quá tải, service phải trả status rõ ràng thay vì âm thầm bỏ request.

## 7. Tạo server và giao shutdown cho một coordinator

Nếu ứng dụng tự quản lý Netty gRPC server, có thể gắn callback executor vào builder:

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

destroyMethod được để rỗng vì coordinator sẽ sở hữu trình tự shutdown. Nếu Spring gRPC tự tạo server, không dùng cấu hình tự tạo server này; tích hợp executor và shutdown vào lifecycle của server do Spring quản lý.

## 8. Coordinator shutdown trong Spring

Một coordinator có thể điều phối server và executor. Ví dụ sau dùng @PreDestroy cho một ứng dụng tự quản lý server:

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
    private final ReadinessController readiness;

    public GrpcShutdownCoordinator(
            Server server,
            @Qualifier("grpcServerExecutor")
            ThreadPoolTaskExecutor grpcServerExecutor,
            @Qualifier("grpcBusinessExecutor")
            ThreadPoolTaskExecutor grpcBusinessExecutor,
            ReadinessController readiness) {
        this.server = server;
        this.grpcServerExecutor = grpcServerExecutor;
        this.grpcBusinessExecutor = grpcBusinessExecutor;
        this.readiness = readiness;
    }

    @PreDestroy
    public void shutdown() {
        log.info("Starting gRPC shutdown");
        readiness.markNotReady();
        readiness.awaitRoutingDrain(5, TimeUnit.SECONDS);

        server.shutdown();
        boolean drained = awaitServer(20, TimeUnit.SECONDS);
        if (!drained) {
            log.warn("gRPC drain timed out; forcing server shutdown");
            server.shutdownNow();
            drained = awaitServer(5, TimeUnit.SECONDS);
        }

        if (!drained) {
            log.error("gRPC server did not terminate in the shutdown budget");
        }

        shutdownExecutor("grpc-business", grpcBusinessExecutor, 10);
        shutdownExecutor("grpc-server", grpcServerExecutor, 5);
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
                log.warn("{} executor forced to stop; {} queued tasks remain",
                        name, queued);
                if (!pool.awaitTermination(3, TimeUnit.SECONDS)) {
                    log.error("{} executor still has active workers", name);
                }
            }
        } catch (InterruptedException error) {
            int queued = pool.shutdownNow().size();
            log.warn("{} executor interrupted; {} queued tasks returned",
                    name, queued);
            Thread.currentThread().interrupt();
        }
    }
}
~~~

ReadinessController là abstraction của ứng dụng để rút instance khỏi traffic và chờ propagation; nó không phải API gRPC. Trong ví dụ này outbound channel chưa được đưa vào coordinator để giữ rõ trách nhiệm; production cần shutdown channel sau server drain và trước executor mà channel sử dụng.

Spring hủy bean phụ thuộc trước bean mà nó phụ thuộc vào. Vì coordinator inject server, executor và readiness controller, nó có thể điều phối chúng trước khi các dependency bị destroy. Với Spring Boot 3, ví dụ dùng jakarta.annotation.PreDestroy; ứng dụng phiên bản cũ có thể cần namespace annotation khác.

Nếu dự án dùng SmartLifecycle hoặc lifecycle extension của Spring gRPC, đặt quy trình vào lifecycle owner phù hợp thay vì thêm hook thứ hai. Không để Spring auto-shutdown server đồng thời với coordinator nếu không có chủ ý và thứ tự rõ ràng.

## 9. Đóng outbound ManagedChannel sau server

Handler có thể cần outbound ManagedChannel để hoàn tất downstream call. Vì vậy, đừng đóng channel trước khi inbound server drain xong.

Sau khi server đã terminate:

1. Gọi ManagedChannel.shutdown() để ngừng call mới.
2. Chờ call đang chạy hoàn tất trong thời gian giới hạn.
3. Nếu quá hạn, gọi shutdownNow().
4. Chờ channel terminate thêm một khoảng ngắn.
5. Đóng client callback executor sau channel nếu executor đó được quản lý riêng.

~~~java
import io.grpc.ManagedChannel;
import java.util.concurrent.TimeUnit;
import org.slf4j.Logger;

static boolean shutdownChannel(
        String name,
        ManagedChannel channel,
        Logger log) {
    channel.shutdown();
    try {
        if (channel.awaitTermination(5, TimeUnit.SECONDS)) {
            return true;
        }
        log.warn("{} channel drain timed out", name);
        channel.shutdownNow();
        return channel.awaitTermination(3, TimeUnit.SECONDS);
    } catch (InterruptedException error) {
        channel.shutdownNow();
        Thread.currentThread().interrupt();
        return false;
    }
}
~~~

Nếu channel dùng chung với background job, server drain không có nghĩa channel đã hết consumer. Hãy drain job subsystem hoặc tách channel có lifecycle riêng. Không đóng executor dùng chung cho channel khác vẫn đang hoạt động.

## 10. Readiness và termination grace period

Server.shutdown() dừng nhận call mới ở gRPC server, nhưng load balancer/service discovery cần thời gian cập nhật endpoint. Vì vậy nên đánh dấu readiness false trước, chờ traffic drain, rồi mới shutdown server.

Tổng ngân sách nội bộ phải nhỏ hơn termination grace period của nền tảng:

| Giai đoạn | Ngân sách minh họa |
| --- | ---: |
| Readiness propagation | 5 giây |
| Server graceful drain | 20 giây |
| Server force-stop wait | 5 giây |
| Channel và executor cleanup | 15 giây |
| Tổng | 45 giây |

Nếu nền tảng chỉ cấp 30 giây trước SIGKILL, không thể cấu hình các bước nội bộ tổng cộng 45 giây. Phải giảm từng timeout và dành một phần ngân sách cho shutdown hook cuối cùng.

Readiness drain và gRPC server shutdown giải quyết hai lớp khác nhau: readiness ngăn routing mới từ hạ tầng; Server.shutdown ngăn call mới tại server. Dùng cả hai giúp rollout ít tạo lỗi hơn.

## 11. Background task và công việc vượt vòng đời RPC

Server terminate không chứng minh mọi task từng được RPC tạo ra đã kết thúc. Handler có thể submit fire-and-forget task rồi trả response ngay; task đó có lifecycle riêng.

Với công việc cần tiếp tục sau restart:

- Dùng durable queue, job store hoặc transactional outbox.
- Chỉ acknowledge RPC sau khi công việc đã được ghi bền vững theo contract.
- Khi shutdown, ngừng nhận job mới và drain job đang chạy trong ngân sách riêng.
- Giữ dependency và executor cần thiết cho tới khi job subsystem dừng.
- Không dựa vào Server.awaitTermination() để quản lý task không còn gắn với RPC.

Nếu task chỉ phục vụ RPC và handler chờ task hoàn tất trước response, server drain thường giữ executor cần thiết tới khi call kết thúc. Nếu task sống lâu hơn RPC, hãy coi nó là background job độc lập.

## 12. Xử lý task còn trong queue

ThreadPoolExecutor.shutdown() ngừng nhận task mới nhưng cho task đã submit tiếp tục chạy. shutdownNow() yêu cầu interrupt worker đang chạy và trả về danh sách task chưa bắt đầu trong queue.

- Ghi nhận số task được trả về từ shutdownNow().
- Xác định task nào có thể bỏ và task nào cần persist/retry.
- Không âm thầm bỏ công việc nghiệp vụ đã được caller xem là accepted.
- Task đang chạy cần timeout cho database/HTTP và kiểm tra cancellation giữa các bước.
- Interrupt chỉ dừng được code hoặc thư viện hỗ trợ interruption.

Nếu executor đang giữ callback cho RPC đã bị hủy, terminal guard phải ngăn callback gửi response muộn. Nếu task quan trọng cần chạy sau restart, lưu vào durable queue trước khi xác nhận đã nhận công việc.

## 13. Quan sát shutdown

Theo dõi từng giai đoạn bằng log và metric:

| Signal | Ý nghĩa |
| --- | --- |
| grpc.shutdown.started | Coordinator bắt đầu shutdown |
| grpc.readiness.disabled | Instance đã rút khỏi traffic |
| grpc.server.drain.duration | Thời gian server drain |
| grpc.server.inflight_at_shutdown | Số RPC đang hoạt động lúc bắt đầu drain |
| grpc.server.force_shutdown | Số lần phải dùng shutdownNow |
| grpc.channel.shutdown.duration | Thời gian outbound channel terminate |
| executor.active_at_shutdown | Worker đang chạy khi shutdown |
| executor.queue_at_shutdown | Task còn chờ trong queue |
| executor.rejected | Task bị từ chối khi pool đầy hoặc đang dừng |
| grpc.shutdown.incomplete | Thành phần không terminate trong ngân sách |

Log nên có component name, thời gian chờ, số task còn queue và trạng thái terminate. Không dùng request ID hoặc tenant ID làm metric label vì cardinality cao; dùng log/trace khi cần điều tra request cụ thể.

Một shutdown thành công cần cho biết server drain bình thường hay bị force, channel có terminate không và executor còn worker/task nào sau thời hạn.

## 14. Kiểm thử graceful và forced shutdown

Integration test nên giữ một RPC đang chạy bằng latch rồi bắt đầu shutdown:

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

Đây là pseudocode phối hợp bằng latch. Đặt releaseHandler.countDown() trong finally để assertion lỗi không làm test treo. Không dùng sleep cố định để đoán handler đã bắt đầu.

Các kịch bản nên kiểm tra:

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| Không có RPC đang chạy | Server terminate nhanh sau shutdown |
| Unary RPC đang xử lý | RPC hoàn tất trong grace period |
| Streaming RPC còn mở | Stream drain hoặc bị hủy khi grace period hết |
| RPC bị treo quá grace period | shutdownNow được gọi và cancellation tới handler |
| Executor có task đang chạy | Task được drain hoặc force theo timeout |
| Executor queue đầy | Task mới bị reject rõ ràng |
| Outbound call đang chạy | Channel còn sống tới khi inbound handler hoàn tất |
| Readiness đã false | Instance không nhận traffic mới từ load balancer |
| Background job độc lập RPC | Job subsystem drain/persist theo contract |
| Shutdown bị interrupt | Force path được kích hoạt và interrupt flag được khôi phục |

Kiểm tra thread leak sau test suite. Server đã terminate nhưng executor còn worker non-daemon vẫn có thể giữ process không thoát.

## 15. Sai lầm thường gặp

1. **Shutdown executor trước server.** Callback của RPC đang chạy có thể không còn thread để hoàn tất.
2. **Gọi shutdownNow ngay lập tức.** Request hợp lệ bị hủy dù còn thời gian drain.
3. **Chờ server vô hạn.** Một call treo có thể giữ process mãi.
4. **Đóng downstream channel trước inbound server.** Handler đang drain mất dependency cần thiết.
5. **Cho rằng server terminate nghĩa là background task đã xong.** Task fire-and-forget có lifecycle riêng.
6. **Bỏ qua readiness/load balancer drain.** Request mới vẫn có thể được định tuyến tới instance đang dừng.
7. **Không kiểm soát tổng grace period.** Platform có thể SIGKILL trước khi cleanup hoàn tất.
8. **Không xử lý task trả về từ shutdownNow.** Công việc đã nhận có thể bị mất.
9. **Có nhiều bean cùng sở hữu shutdown.** Thứ tự đóng tài nguyên khó dự đoán.
10. **Không test forced shutdown và thread leak.** Lỗi chỉ xuất hiện khi rollout hoặc process dừng thật.

## 16. Bài tập vận dụng

Với một Spring gRPC service có server, downstream channel và hai executor:

1. Tạo callback executor và business executor riêng, queue hữu hạn.
2. Xây lifecycle coordinator để đánh dấu readiness false, gọi Server.shutdown() và chờ drain.
3. Khi grace period hết, gọi Server.shutdownNow() và xác minh cancellation tới handler.
4. Chỉ sau khi server drain, shutdown outbound ManagedChannel và chờ channel terminate.
5. Shutdown executor cuối cùng; nếu hết timeout, dùng shutdownNow() và ghi số task còn queue.
6. Tạo RPC có latch để chứng minh request đang chạy được phép hoàn tất trong graceful period.
7. Tạo RPC treo để kiểm tra forced shutdown.
8. Kiểm tra tổng thời gian shutdown không vượt termination grace period của môi trường chạy.
9. Thu thập metric cho drain duration, force shutdown, active workers và queue leftovers.

**Tiêu chí hoàn thành:** người học giải thích được thứ tự shutdown giữa server, channel và executor; triển khai drain có giới hạn thời gian; xử lý force-stop và task còn queue; phối hợp readiness với termination grace period; và kiểm thử được graceful lẫn forced shutdown.

### Tài liệu tham khảo

- [gRPC Java Server API](https://grpc.github.io/grpc-java/javadoc/io/grpc/Server.html): shutdown, shutdownNow và awaitTermination.
- [gRPC Java ManagedChannel API](https://grpc.github.io/grpc-java/javadoc/io/grpc/ManagedChannel.html): graceful shutdown của client channel.
- [Java ThreadPoolExecutor](https://docs.oracle.com/en/java/javase/): shutdown, shutdownNow và awaitTermination.
- [Spring ThreadPoolTaskExecutor](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html): lifecycle executor trong Spring.
- [Spring Bean Lifecycle](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html): destroy callbacks và bean lifecycle.
- [Spring gRPC Reference](https://docs.spring.io/spring-grpc/reference/): tích hợp server/client gRPC trong Spring.
