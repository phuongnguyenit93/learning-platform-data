# Quản lý vòng đời executor, scheduler, client và tài nguyên kết nối

## Mục tiêu

Sau bài này, bạn có thể:

- Xác định thành phần nào tạo, sở hữu và chịu trách nhiệm đóng từng tài nguyên.
- Phân biệt vòng đời của application singleton, task, subscription, worker và connection.
- Cấu hình executor và scheduler có giới hạn, có chính sách shutdown rõ ràng.
- Dùng lifecycle hook của Spring để dừng nhận công việc, chờ tác vụ đang chạy và giải phóng tài nguyên đúng thứ tự.
- Đóng client RSocket và transport do ứng dụng sở hữu, đồng thời giữ nguyên tài nguyên dùng chung do framework quản lý.
- Kiểm thử graceful shutdown, timeout, task bị từ chối và rò rỉ thread/connection.

## 1. Vì sao phải quản lý vòng đời tài nguyên?

Ứng dụng Spring Messaging thường giữ nhiều tài nguyên sống lâu hơn một request:

- Executor và thread pool xử lý message bất đồng bộ.
- Reactor Scheduler điều phối tác vụ trên thread.
- Subscription và Scheduler.Worker của từng luồng xử lý.
- RSocketRequester, WebSocket session hoặc client kết nối đến broker.
- Connection pool, timer, buffer và các listener nhận message.
- Consumer, adapter hoặc container duy trì kết nối đến hệ thống bên ngoài.

Mỗi tài nguyên có thời điểm tạo, phạm vi sử dụng và cách kết thúc riêng. Nếu không đóng đúng lúc, ứng dụng có thể gặp:

- Thread còn chạy sau khi Spring context đã đóng, khiến JVM không thoát.
- Message mới vẫn được nhận trong khi dependency đã bắt đầu shutdown.
- Queue tiếp tục nhận công việc nhưng không còn worker xử lý.
- Socket hoặc connection pool bị giữ lại sau khi không còn dùng.
- Subscription vẫn phát dữ liệu và giữ tham chiếu đến object đã ngừng hoạt động.
- Task bị mất giữa chừng hoặc bị hủy mà không có trạng thái nghiệp vụ rõ ràng.
- Context test đóng nhưng thread của test trước vẫn làm ảnh hưởng test sau.

Quản lý vòng đời không chỉ là gọi một hàm close. Nó là hợp đồng về **ai sở hữu tài nguyên, khi nào ngừng nhận công việc, xử lý phần đang chạy ra sao và lúc nào được giải phóng**.

## 2. Phân biệt ownership và scope

Nguyên tắc đầu tiên: thành phần tạo hoặc được giao quyền sở hữu tài nguyên phải chịu trách nhiệm kết thúc tài nguyên đó. Thành phần chỉ mượn tài nguyên không được tự ý đóng nó.

| Scope | Ví dụ | Ai thường quản lý | Khi nào giải phóng |
| --- | --- | --- | --- |
| Application | ThreadPoolTaskExecutor, client singleton | Spring ApplicationContext hoặc component owner | Khi context shutdown |
| Connection | RSocket connection, WebSocket session | Component mở/nhận ownership connection | Khi peer đóng, session kết thúc hoặc component shutdown |
| Worker | Reactor Scheduler.Worker | Thành phần tạo worker | Khi công việc dùng worker kết thúc |
| Subscription | Disposable/subscribe handle | Thành phần gọi subscribe | Khi stream hoàn tất, lỗi hoặc không còn cần |
| Task | Future, scheduled task | Thành phần submit task | Khi task xong hoặc bị cancel theo policy |

Ví dụ:

- Một bean tạo RSocketRequester để gọi service từ xa có trách nhiệm dispose requester khi bean/context kết thúc.
- Một handler nhận RSocketRequester của connection thông qua callback server không mặc nhiên sở hữu connection đó. Framework/server quản lý vòng đời; handler chỉ đóng connection nếu nghiệp vụ thực sự yêu cầu ngắt peer.
- Một service dùng Scheduler singleton được inject từ Spring không được tự dispose Scheduler trong mỗi lần xử lý message.
- Một component tạo Scheduler.Worker riêng phải dispose worker khi không còn dùng.

Trước khi thêm cleanup, hãy trả lời ba câu hỏi:

1. Tài nguyên được tạo ở đâu?
2. Ai có quyền dùng và ai sở hữu?
3. Có thành phần nào khác còn phụ thuộc vào nó khi shutdown không?

Đừng đóng một tài nguyên chỉ vì đang giữ reference đến nó.

## 3. Vòng đời của Spring ApplicationContext

Spring quản lý các singleton bean theo vòng đời của ApplicationContext. Khi khởi động, container tạo bean, inject dependency và gọi các callback khởi tạo. Khi shutdown, container gọi các callback hủy theo lifecycle contract.

Các cơ chế thường gặp:

- **@Bean(destroyMethod = "..."):** khai báo phương thức hủy cho bean do configuration tạo.
- **@PreDestroy:** callback trước khi bean bị hủy.
- **DisposableBean:** bean tự triển khai callback destroy.
- **Lifecycle / SmartLifecycle:** component cần start/stop có điều phối, đặc biệt listener và adapter chạy nền.
- **AutoCloseable / close():** tài nguyên có hợp đồng đóng chuẩn; Spring có thể suy luận destroy method trong nhiều trường hợp.

Chọn một cơ chế phù hợp với loại tài nguyên. Không cần đồng thời gọi shutdown trong @PreDestroy, DisposableBean và destroyMethod cho cùng một executor. Cleanup nên có một owner và một đường đi rõ ràng, có thể gọi lặp an toàn nếu framework yêu cầu.

### @Bean với destroyMethod

Với tài nguyên có phương thức đóng rõ ràng, có thể khai báo:

~~~java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class MessagingResourceConfiguration {

    @Bean(destroyMethod = "shutdown")
    ExecutorService messageExecutor() {
        return Executors.newFixedThreadPool(8);
    }
}
~~~

Spring sẽ gọi shutdown khi bean bị hủy. Tuy nhiên, shutdown chỉ ngăn nhận task mới và cho phép task đã submit chạy tiếp; nó không tự đặt thời hạn chờ vô hạn định. Nếu cần một khoảng drain cụ thể và fallback sang shutdownNow, hãy dùng component quản lý lifecycle có logic awaitTermination.

### @PreDestroy

Với một component sở hữu nhiều tài nguyên, @PreDestroy có thể gom cleanup vào một nơi:

~~~java
import jakarta.annotation.PreDestroy;
import org.springframework.stereotype.Component;

@Component
class MessagingResourceOwner {

    private final SomeClient client;

    MessagingResourceOwner(SomeClient client) {
        this.client = client;
    }

    @PreDestroy
    void close() {
        client.close();
    }
}
~~~

Đây là ví dụ cấu trúc; SomeClient phải có phương thức close phù hợp. Nếu client đã được Spring quản lý như một bean riêng với destroy method, không đóng nó thêm từ component khác. Tránh gọi network operation kéo dài trong @PreDestroy nếu có thể điều phối shutdown bất đồng bộ bằng SmartLifecycle.

## 4. Shutdown theo thứ tự: dừng ingress trước, drain sau

Một hệ thống messaging không nên dừng mọi tài nguyên cùng lúc. Hãy đóng theo dependency graph.

Trình tự thường phù hợp:

1. **Dừng ingress:** ngừng nhận message mới từ broker, WebSocket hoặc RSocket listener.
2. **Ngừng phát sinh công việc mới:** tắt scheduler định kỳ, timer và producer nội bộ.
3. **Drain công việc đang chạy:** cho consumer/handler hoàn thành trong deadline; các task vượt deadline được xử lý theo policy.
4. **Đóng outbound client và connection:** sau khi task không còn gọi dependency.
5. **Shutdown executor và scheduler:** từ chối task mới, chờ phần còn lại và giải phóng thread.
6. **Đóng telemetry và logging sau cùng:** bảo đảm log/metric cho quá trình shutdown vẫn được ghi.

Thứ tự chính xác phụ thuộc quan hệ phụ thuộc. Ví dụ executor xử lý message cần một outbound client; vì vậy client phải sống lâu hơn các task đang dùng nó. Nếu đóng client trước khi drain executor, các task còn lại sẽ thất bại hàng loạt.

### SmartLifecycle và phase

SmartLifecycle phù hợp cho component có start/stop và cần phối hợp với component khác. Spring start các component theo phase tăng dần và stop theo phase giảm dần. Do đó, listener/ingress có phase cao hơn worker mà nó sử dụng thường sẽ được stop trước worker.

Ví dụ minh họa:

~~~java
import org.springframework.context.SmartLifecycle;
import org.springframework.stereotype.Component;

@Component
class MessageIngressLifecycle implements SmartLifecycle {

    private volatile boolean running;

    @Override
    public void start() {
        // Khởi động listener hoặc adapter nhận message.
        running = true;
    }

    @Override
    public void stop() {
        // Ngừng nhận message mới.
        running = false;
    }

    @Override
    public void stop(Runnable callback) {
        try {
            stop();
        } finally {
            callback.run();
        }
    }

    @Override
    public boolean isRunning() {
        return running;
    }

    @Override
    public int getPhase() {
        return 100;
    }

    @Override
    public boolean isAutoStartup() {
        return true;
    }
}
~~~

Đây là skeleton minh họa: phần start/stop phải gọi API thật của listener/container. Với stop bất đồng bộ, chỉ gọi callback khi thao tác stop đã hoàn thành. Nếu callback được gọi quá sớm, Spring có thể tiếp tục hủy dependency trong khi listener vẫn còn hoạt động.

Một worker/executor phụ thuộc có thể dùng phase thấp hơn, ví dụ 0, để listener phase 100 dừng trước. Không chọn phase tùy ý mà không vẽ dependency giữa các component.

## 5. Quản lý ExecutorService

ExecutorService có hai bước shutdown quan trọng:

- **shutdown():** từ chối task mới, nhưng cho các task đã submit chạy tiếp.
- **shutdownNow():** yêu cầu dừng ngay bằng interrupt các task đang chạy và trả về danh sách task chưa bắt đầu; task phải hợp tác với interrupt mới có thể kết thúc.

Không nên gọi shutdownNow ngay khi ứng dụng bắt đầu dừng nếu muốn xử lý hết message đang nhận. Hãy cho một khoảng drain hữu hạn, sau đó mới fallback.

Ví dụ Java 17:

~~~java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class ExecutorShutdownDemo {

    public static void main(String[] args) {
        ExecutorService executor = Executors.newSingleThreadExecutor();

        executor.submit(() -> System.out.println("task-finished"));
        executor.shutdown();

        try {
            boolean terminated =
                    executor.awaitTermination(2, TimeUnit.SECONDS);

            if (!terminated) {
                executor.shutdownNow();
                terminated = executor.awaitTermination(1, TimeUnit.SECONDS);
            }

            System.out.println("terminated=" + terminated);
        } catch (InterruptedException ex) {
            executor.shutdownNow();
            Thread.currentThread().interrupt();
        }
    }
}
~~~

Chạy bằng Java 17:

~~~bash
javac ExecutorShutdownDemo.java
java ExecutorShutdownDemo
~~~

Stdout chính xác:

~~~text
task-finished
terminated=true
~~~

Khi awaitTermination bị interrupt, cần gọi shutdownNow nếu policy yêu cầu dừng và khôi phục interrupt flag bằng Thread.currentThread().interrupt(). Không nuốt InterruptedException rồi tiếp tục chạy như không có gì xảy ra.

Task dài cần kiểm tra interrupt hoặc dùng API có timeout. Một task không hợp tác với interrupt có thể khiến shutdownNow không kết thúc được. Không chạy công việc blocking không giới hạn trên thread xử lý event loop.

## 6. Cấu hình ThreadPoolTaskExecutor trong Spring

ThreadPoolTaskExecutor tích hợp với Spring lifecycle. Khi khai báo thành bean, container quản lý khởi tạo và shutdown. Cần đặt giới hạn thread, queue và thời gian chờ phù hợp với tải của ứng dụng.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
class MessagingExecutorConfiguration {

    @Bean
    ThreadPoolTaskExecutor messageExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();

        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(16);
        executor.setQueueCapacity(200);
        executor.setThreadNamePrefix("message-worker-");

        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(20);

        return executor;
    }
}
~~~

Ý nghĩa:

- corePoolSize là số thread nền duy trì khi tải thấp.
- maxPoolSize giới hạn số thread tối đa.
- queueCapacity giới hạn số task chờ trước khi executor mở rộng thread hoặc từ chối theo cấu hình.
- waitForTasksToCompleteOnShutdown yêu cầu chờ task đã nhận hoàn thành trong quá trình shutdown.
- awaitTerminationSeconds đặt giới hạn chờ.

Không đặt queueCapacity quá lớn chỉ để tránh rejection. Queue dài làm tăng latency và giữ payload/object trong memory. Khi executor từ chối task, ứng dụng cần có phản hồi rõ ràng: retry có giới hạn, trả overload hoặc đưa message về broker theo acknowledgement policy.

Khi executor đã là Spring bean, không gọi shutdown sau mỗi batch hoặc request. Chỉ để container quản lý vòng đời. Nếu cần điều phối listener dừng trước executor, đặt phase hoặc dùng lifecycle coordinator rõ ràng.

## 7. Quản lý Reactor Scheduler và subscription

Reactor Scheduler là tài nguyên có vòng đời riêng. Có hai nhóm cần phân biệt:

- Scheduler dùng chung của Reactor như Schedulers.parallel(), Schedulers.boundedElastic() và Schedulers.single().
- Scheduler do ứng dụng tự tạo như Schedulers.newParallel(...) hoặc Schedulers.newBoundedElastic(...).

Scheduler dùng chung được cache và chia sẻ bởi nhiều thành phần. Không dispose một common Scheduler chỉ vì một service ngừng sử dụng nó; việc đó có thể làm hỏng các pipeline khác. Scheduler do ứng dụng tạo và sở hữu thì phải được dispose.

Ví dụ khai báo Scheduler riêng làm Spring bean:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import reactor.core.scheduler.Scheduler;
import reactor.core.scheduler.Schedulers;

@Configuration
class ReactorSchedulerConfiguration {

    @Bean(destroyMethod = "dispose")
    Scheduler messagingScheduler() {
        return Schedulers.newBoundedElastic(
                8,
                500,
                "messaging-io");
    }
}
~~~

Giới hạn thread và số task chờ giúp Scheduler từ chối tải vượt ngưỡng thay vì giữ queue không giới hạn. Giá trị thực tế phải được chọn theo workload và tài nguyên máy.

Scheduler có disposeGracefully() để yêu cầu giải phóng tài nguyên theo cách graceful. Đây là Mono lazy; cần subscribe hoặc block có timeout trong một lifecycle coordinator phù hợp. Nếu graceful disposal vượt deadline, có thể fallback dispose() theo policy. Không gọi disposeGracefully() rồi bỏ publisher mà cho rằng cleanup đã bắt đầu.

Mỗi Scheduler.Worker được tạo riêng cũng cần dispose khi hết scope. Tương tự, subscription được tạo bằng subscribe() trả về Disposable; nếu stream phải dừng theo vòng đời component, giữ handle và dispose khi component stop.

~~~java
import jakarta.annotation.PreDestroy;
import org.springframework.stereotype.Component;

import reactor.core.Disposable;
import reactor.core.publisher.Flux;

@Component
class MessageSubscriptionOwner {

    private final Disposable subscription;

    MessageSubscriptionOwner(MessageSource source) {
        this.subscription = source.messages()
                .subscribe(this::handle, this::handleError);
    }

    private void handle(MessageEvent event) {
        // Xử lý message.
    }

    private void handleError(Throwable error) {
        // Ghi nhận lỗi và áp dụng policy.
    }

    @PreDestroy
    void stop() {
        subscription.dispose();
    }
}
~~~

MessageSource và MessageEvent đại diện cho abstraction của ứng dụng. Với publisher có lifecycle do framework quản lý, hãy dùng lifecycle contract của framework thay vì subscribe thủ công lần thứ hai.

## 8. Đóng RSocketRequester và các client kết nối

RSocketRequester là API client để gửi request qua RSocket. Khi ứng dụng tạo client requester và sở hữu nó, requester cần được dispose khi không còn dùng hoặc khi application context shutdown. RSocketRequester triển khai Disposable; dispose() đóng connection transport nền và thông báo cho subscriber.

Ví dụ:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.rsocket.RSocketRequester;

@Configuration
class RSocketClientConfiguration {

    @Bean(destroyMethod = "dispose")
    RSocketRequester remoteRequester() {
        return RSocketRequester.builder()
                .tcp("localhost", 7000);
    }
}
~~~

Đây là client requester do ứng dụng tạo và sở hữu. Nếu requester được nhận như một connection-specific argument trong handler phía server, không dispose nó chỉ vì handler hoàn tất một request; connection đó thuộc lifecycle của server/framework.

Khi shutdown, cần dừng producer/consumer sử dụng requester trước, drain các request đang chạy trong giới hạn, rồi dispose requester. Các request mới sau khi dispose phải bị từ chối hoặc đi qua một client/connection mới theo policy; không tái sử dụng requester đã disposed.

Với WebSocket/STOMP hoặc broker client, áp dụng cùng nguyên tắc:

- Dừng adapter/listener nhận message trước.
- Ngừng publish message mới.
- Chờ acknowledgement và tác vụ đang xử lý trong deadline.
- Đóng session/connection/client mà component sở hữu.
- Hủy timer, heartbeat task và subscription đi kèm.

Nếu framework hoặc connection factory đã quản lý lifecycle, hãy gọi stop/close ở đúng abstraction của framework. Không đóng socket bên dưới trong khi broker container vẫn nghĩ connection đang hoạt động.

## 9. Graceful shutdown và deadline

Graceful shutdown không có nghĩa là chờ mọi task vô thời hạn. Mỗi giai đoạn cần deadline rõ ràng:

| Giai đoạn | Hành động | Điều gì xảy ra khi hết deadline |
| --- | --- | --- |
| Stop ingress | Không nhận thêm message mới | Đóng listener/session theo policy |
| Drain in-flight | Chờ handler và acknowledgement | Cancel hoặc đánh dấu retry/redelivery |
| Close outbound clients | Đóng kết nối sau khi task kết thúc | Hủy request còn treo và ghi nhận lỗi |
| Shutdown workers | Từ chối task mới, chờ worker kết thúc | Interrupt/fallback dispose |
| Finalize telemetry | Flush log/trace/metric | Kết thúc theo timeout để JVM thoát |

Deadline tổng thể phải nhỏ hơn termination grace period của container/orchestrator. Nếu Kubernetes chỉ cho process một khoảng grace period ngắn mà ứng dụng chờ executor quá lâu, process sẽ bị kill trước khi hoàn thành cleanup.

Cần phân biệt:
- **Task hoàn thành:** nghiệp vụ và acknowledgement đã kết thúc.
- **Task bị cancel:** computation dừng, nhưng side effect có thể đã xảy ra.
- **Message được redeliver:** broker giao lại theo acknowledgement/retry policy.
- **Request bị timeout:** caller ngừng chờ; server có thể vẫn đang xử lý.

Không xác nhận ACK trước khi side effect cần thiết đã commit. Không xem cancel là rollback. Với nghiệp vụ có side effect, cần idempotency và reconciliation để xử lý trường hợp shutdown xảy ra giữa chừng.

## 10. Tránh các lỗi vòng đời thường gặp

- **Đóng tài nguyên dùng chung:** một service dispose Scheduler hoặc connection pool được nhiều service dùng, làm các thành phần khác hỏng theo.
- **Không đóng tài nguyên tự tạo:** custom executor, scheduler, worker hoặc requester giữ thread/socket sau shutdown.
- **Đóng client trước worker:** task đang chạy tiếp tục gọi client đã đóng và phát sinh lỗi hàng loạt.
- **Chờ vô hạn:** awaitTermination không có timeout làm shutdown bị treo.
- **Dùng queue vô hạn:** tải tăng làm latency và memory tăng đến khi OOM.
- **Bỏ qua rejection:** task bị từ chối nhưng message đã được ACK hoặc không có retry path.
- **Subscribe nhưng không giữ Disposable:** không thể chủ động dừng subscription theo lifecycle.
- **Đóng subscription quá sớm:** message đang xử lý bị cancel nhưng không có chính sách retry/ack rõ ràng.
- **Gọi cleanup nhiều nơi:** @PreDestroy, destroyMethod và callback khác cùng đóng một tài nguyên, gây thứ tự khó đoán.
- **Tạo thread trong mỗi request:** thread không được tái sử dụng và rất khó kiểm soát số lượng.
- **Block event loop:** shutdown hoặc network wait trên event loop làm nhiều connection khác ngừng phản hồi.

## 11. Kiểm thử vòng đời và resource leak

Không chỉ test rằng method close đã được gọi. Cần xác nhận hệ thống thực sự dừng nhận việc, drain đúng, đóng kết nối và không còn thread/tác vụ bị giữ lại.

Các test quan trọng:

1. **Context shutdown:** tạo ApplicationContext, lấy bean executor/scheduler/client, đóng context và xác nhận tài nguyên owned đã disposed.
2. **Task đang chạy:** submit task có latch, bắt đầu shutdown, xác nhận task được phép hoàn tất trong deadline.
3. **Task vượt deadline:** giữ task lâu hơn timeout, xác nhận fallback interrupt/dispose được gọi và shutdown kết thúc.
4. **Task mới sau shutdown:** xác nhận executor từ chối task mới.
5. **Listener ordering:** khi stop ingress, worker vẫn hoạt động cho đến khi in-flight message drain xong.
6. **RSocket close:** dispose requester và xác nhận onClose hoàn tất; request mới không được gửi trên requester đã đóng.
7. **Subscription cleanup:** dispose subscription và xác nhận publisher không phát thêm item.
8. **Context restart:** đóng và tạo lại ApplicationContext, xác nhận không có thread cũ hoặc port cũ còn bị chiếm.
9. **Repeated close:** gọi shutdown/dispose theo hợp đồng và xác nhận cleanup không tạo lỗi hoặc side effect lặp.
10. **Leak check:** kiểm tra thread name prefix, connection count, active task count và file/socket handle trước/sau test.

Không dùng Thread.sleep để chờ shutdown. Dùng CountDownLatch, Awaitility hoặc StepVerifier với timeout. Test phải có deadline hữu hạn để failure không treo CI.

Ví dụ kiểm tra một executor kết thúc:

~~~java
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;

class ExecutorLifecycleTest {

    @Test
    void executorTerminatesAfterShutdown() throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();

        executor.submit(() -> {
            // Task hữu hạn.
        });

        executor.shutdown();

        assertTrue(executor.awaitTermination(2, TimeUnit.SECONDS));
    }
}
~~~

Trong integration test Spring, ưu tiên kiểm tra bean lifecycle thực tế thay vì tự gọi shutdown trước rồi chỉ test object JDK. Với client thật, xác nhận peer quan sát được close signal và server không còn giữ connection/session cũ.

## 12. Quan sát tài nguyên trong production

Để phát hiện leak và shutdown bị kẹt, theo dõi:

- Số thread theo prefix và trạng thái thread.
- Active thread, pool size, queue size và số task bị reject.
- Số message đang xử lý, số acknowledgement chờ và thời gian drain.
- Số connection/session mở, số connection bị đóng và nguyên nhân đóng.
- Số subscription/worker đang hoạt động nếu ứng dụng có thể đo được.
- Số lần timeout khi shutdown và số task bị interrupt.
- Thời gian từ lúc nhận tín hiệu shutdown đến khi process dừng.

Metric tag nên có cardinality thấp: tên executor, tên client, loại operation. Không dùng message ID, user ID hoặc connection ID làm metric tag. Chi tiết định danh nên ở log có kiểm soát.

Khi có sự cố, thread dump giúp tìm worker đang block hoặc task không phản hồi interrupt. Connection metrics và log lifecycle giúp phân biệt connection bị leak với connection vẫn đang được giữ có chủ đích.

## 13. Checklist triển khai

- [ ] Mỗi executor, scheduler, client và connection có owner rõ ràng.
- [ ] Tài nguyên dùng chung không bị dispose bởi consumer chỉ mượn nó.
- [ ] Executor có giới hạn thread, queue và rejection policy.
- [ ] Scheduler tự tạo được dispose; common Scheduler không bị đóng tùy tiện.
- [ ] Subscription và Worker có handle để hủy theo đúng scope.
- [ ] RSocketRequester do ứng dụng sở hữu được dispose khi shutdown.
- [ ] Ingress dừng trước worker và outbound dependency.
- [ ] In-flight task có deadline drain và fallback rõ ràng.
- [ ] Interrupt được xử lý đúng, không nuốt InterruptedException.
- [ ] Không ACK message trước khi side effect cần thiết được commit.
- [ ] Có test context shutdown, task đang chạy, timeout và resource leak.
- [ ] Production có metric cho thread, queue, connection và shutdown duration.

## Tài liệu tham khảo

- [Spring Framework Reference — Bean Lifecycle](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html)
- [Spring Framework API — SmartLifecycle](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/SmartLifecycle.html)
- [Spring Framework API — ThreadPoolTaskExecutor](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html)
- [Spring Framework API — RSocketRequester](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/rsocket/RSocketRequester.html)
- [Project Reactor API — Scheduler](https://projectreactor.io/docs/core/release/api/reactor/core/scheduler/Scheduler.html)
- [Java API — ExecutorService](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ExecutorService.html)
