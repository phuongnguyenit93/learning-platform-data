# Dừng nhận việc mới và chờ tác vụ đang chạy khi đóng ứng dụng

## Mục tiêu học tập

Khi một ứng dụng Spring Boot dừng để deploy phiên bản mới, scale down, bảo trì hoặc khởi động lại, tiến trình **không nên tiếp tục nhận công việc mới rồi bỏ dở những tác vụ đã nhận**. Cách dừng an toàn thường gồm hai việc có liên quan nhưng không giống nhau:

1. **Đóng cổng tiếp nhận công việc mới** (*stop admission*): yêu cầu HTTP mới, bản tin queue mới hoặc tác vụ nộp vào executor không còn được chấp nhận theo chính sách ứng dụng.
2. **Chờ công việc đã nhận kết thúc có kiểm soát** (*drain in-flight work*): những tác vụ đang chạy hoặc đã vào hàng đợi được xử lý đến trạng thái hoàn tất, hoặc được đưa sang nhánh timeout/cancellation/retry tường minh.

Hai bước này thuộc **Spring Boot Application Runtime → Luồng và tác vụ**. Chúng liên hệ đến `ApplicationContext.close()`, `ContextClosedEvent`, `SmartLifecycle`, `ExecutorService`, `ThreadPoolTaskExecutor`, graceful HTTP shutdown và các deadline của nền tảng triển khai.

Sau bài học, bạn có thể:

- Phân biệt request đang chạy (*in-flight*), tác vụ đã chấp nhận nhưng còn trong queue (*queued*), công việc mới (*new submission*) và tác vụ hoàn tất.
- Giải thích chính xác `ExecutorService.shutdown()`, `shutdownNow()`, `awaitTermination(...)` và hành vi khi có `RejectedExecutionException`.
- Viết một **admission gate** bảo đảm không có khoảng hở giữa kiểm tra “còn nhận việc” và đưa tác vụ vào executor.
- Dùng `SmartLifecycle.stop(Runnable callback)` để ngừng nhận việc và chỉ thông báo hoàn tất khi worker thực sự ngừng theo hợp đồng.
- Thiết lập Spring Boot **3.3.13** xử lý HTTP request đang chạy với `server.shutdown=graceful` và hiểu `spring.lifecycle.timeout-per-shutdown-phase`.
- Cấu hình `ThreadPoolTaskExecutor` để chờ queued/running jobs khi hủy bean; biết giới hạn của lựa chọn đó với các task mới được submit trong lúc close.
- Chạy một ví dụ Java 17+ / Spring Boot 3.3 có task đang bị chặn, một thread chủ động đóng context, yêu cầu mới bị từ chối và công việc cũ kết thúc trước khi context đóng.
- Thiết kế timeout, retry/idempotency, SIGTERM, readiness và thời gian grace period để giảm nguy cơ mất việc trong production.

**Phiên bản tham chiếu:** Spring Boot 3.3.x (ví dụ dùng **3.3.13**), Spring Framework 6.1.x, Java 17+. Các phiên bản Spring Boot mới hơn có thể thay đổi **mặc định** của graceful shutdown hoặc chi tiết executor; không lấy mặc định của bản mới áp cho Boot 3.3.

## 1. Bài toán: “dừng ứng dụng” không đồng nghĩa “không còn việc”

Giả sử một ứng dụng:

- Phục vụ một HTTP endpoint `POST /jobs` để nhận yêu cầu xử lý báo cáo.
- Đưa công việc vào thread pool hoặc queue.
- Có một job đang chạy mất 12 giây.
- Nhận tín hiệu dừng khi container orchestration muốn thay pod.

Nếu tiến trình đóng database connection hoặc thoát JVM ngay, job có thể bị bỏ dở. Nếu chỉ đợi job chạy mà **không chặn submit mới**, một luồng khác vẫn có thể thêm việc và khiến thời gian chờ kéo dài vô hạn.

Cần thiết kế hai ranh giới:

~~~text
                        TRƯỚC KHI DỪNG
request / message -----> [ACCEPT] -----> queue -----> workers
                             |                           |
                             +---------------------------+
                                 hoàn thành / ghi kết quả

                            KHI CÓ LỆNH DỪNG
                                    |
                                    v
                         đóng admission gate
                                    |
                 +------------------+------------------+
                 |                                     |
         công việc mới                           việc đã chấp nhận
          [REJECT]                                [DRAIN]
                 |                                     |
      trả lỗi / retry-after                    chạy hoặc queued
      / không ack message                      cho đến hoàn tất
                                                       |
                                      timeout? -------+------> xử lý lỗi
                                                       |
                                                       v
                                            đóng executor/resources
                                                       |
                                                       v
                                            hoàn tất context close
~~~

Một ứng dụng vận hành tốt phải định nghĩa **thế nào được tính là “đã chấp nhận”**. Ví dụ: trả HTTP `202 Accepted` trước khi lưu job vào DB/queue bền vững là nguy hiểm, vì client nghĩ server đã nhận trách nhiệm nhưng tiến trình có thể biến mất trước khi công việc được lưu.

**Nguyên tắc:** Ngừng nhận việc trước, rồi mới chờ việc đã nhận; không coi việc dừng nhận request HTTP là đủ để dừng tất cả job nền.

## 2. Bốn loại trạng thái cần phân biệt

| Trạng thái | Ý nghĩa | Xử lý khi shutdown |
| --- | --- | --- |
| `NEW` | Yêu cầu chưa được chấp nhận hoặc đang kiểm tra admission | Từ chối rõ ràng, trả response phù hợp hoặc để nguồn phát retry |
| `QUEUED` | Task đã được nhận và đặt vào executor/queue nhưng chưa bắt đầu | Cho phép chạy nốt trong chính sách drain, hoặc chuyển sang hệ thống bền vững |
| `RUNNING` | Worker đã bắt đầu task, có thể đang giữ kết nối/transaction | Đợi hoàn thành trong deadline; chỉ interrupt nếu có chính sách cancellation |
| `COMPLETED` | Task đã hoàn tất theo tiêu chí nghiệp vụ, kết quả/ack bền vững khi cần | Không cần chạy lại; có thể đóng các resource sau nó |

Không nên dùng chỉ số **active threads = 0** làm tiêu chí duy nhất: nếu queue vẫn còn tác vụ, không có thread đang chạy trong một khoảnh khắc không đồng nghĩa tất cả công việc đã được xử lý.

Tương tự, **queue size = 0** không nói rằng mọi task đã hoàn tất: worker có thể lấy hết task khỏi queue và đang xử lý chúng.

Để theo dõi drain, dùng các thước đo phù hợp như **accepted**, **running**, **queued**, **completed**, **failed**, **rejected**, **in-flight**, **await timeout**, và số job cần retry.

### “Không nhận việc mới” có nhiều nguồn

Một Spring Boot app có thể có nhiều đường ingress:

1. **HTTP:** Spring MVC/Tomcat, WebFlux/Reactor Netty hoặc một reverse proxy.
2. **Message queue:** Kafka/RabbitMQ/JMS listener có thể tiếp tục pull/consume nếu không được tạm dừng.
3. **Scheduler:** `@Scheduled` hoặc một scheduler riêng có thể tiếp tục kích hoạt task.
4. **Task executor:** Những bean khác có thể gọi `execute`/`submit`.
5. **Luồng tự tạo:** `new Thread(...)` hoặc `Executors.new...` ngoài quản lý của Spring.

Mỗi loại cần có **cách chặn đầu vào tương ứng**. `server.shutdown=graceful` không tự gửi “stop polling” đến Kafka consumer hoặc dừng một executor tự tạo mà Spring không biết đến.

## 3. Quy trình đóng an toàn: quiesce → drain → dispose

Có thể chia shutdown thành ba giai đoạn:

### 3.1. Quiesce: ngừng đưa việc mới vào hệ thống

Quiesce nghĩa là instance chuyển sang trạng thái không nhận thêm công việc. Các ví dụ:

- Ngừng đăng ký nhận traffic mới ở load balancer, kết hợp graceful server shutdown.
- Chặn endpoint nộp job ở lớp admission.
- Pause/stop message listener theo contract của thư viện, không tiếp tục poll nếu không còn khả năng xử lý.
- Dừng lịch tạo job mới hoặc từ chối yêu cầu đưa việc vào executor.

**Đừng chỉ set một biến boolean rồi gọi `executor.execute(...)` ngoài khóa**. Hai thread có thể cạnh tranh: thread A kiểm tra `accepting == true`, thread B đóng gate và shutdown executor, thread A vẫn cố submit. Cần một cơ chế đồng bộ hóa tuyến tính (*linearization point*) hoặc xử lý `RejectedExecutionException` một cách chính xác.

### 3.2. Drain: hoàn tất việc đã chấp nhận

Sau khi không còn job mới vào, cho phép:

- Running tasks hoàn tất.
- Queued tasks được worker xử lý nếu chính sách muốn **drain toàn bộ backlog**.
- Các operation commit/flush/ack diễn ra đúng thứ tự, không đóng resource cần thiết quá sớm.

**Deadline là bắt buộc trong production:** Một task bị treo vô hạn hoặc không phản hồi interrupt không được giữ cả tiến trình vô thời hạn. Khi hết thời gian, phải có chính sách rõ: đánh dấu incomplete, retry/redelivery, lưu checkpoint, chuyển dead-letter, yêu cầu forced stop hoặc để orchestrator xử lý.

### 3.3. Dispose: đóng tài nguyên sau khi task không còn cần chúng

Chỉ sau khi các công việc liên quan hoàn tất mới đóng những tài nguyên mà chúng sử dụng: database connection pool, HTTP clients, producer/consumer, file handles và executor.

Nếu đóng database pool **trước khi** một worker commit kết quả, drain trên lý thuyết có thể vẫn kết thúc nhưng dữ liệu bị lỗi. Vì vậy thứ tự lifecycle/dependency giữa **consumer**, **worker executor** và **resource providers** rất quan trọng.

## 4. ExecutorService.shutdown() và shutdownNow() khác nhau

Java SE cung cấp `java.util.concurrent.ExecutorService` với hai phương thức có ý nghĩa rất khác.

### shutdown(): ngừng nhận task mới, cho task cũ tiếp tục

~~~java
executor.shutdown();
~~~

`shutdown()` yêu cầu **orderly shutdown**:

- Những task được nộp **trước khi shutdown** vẫn đủ điều kiện thực thi, bao gồm task đang chạy và task còn trong queue.
- Các task nộp **sau khi shutdown** bị từ chối.
- Phương thức `shutdown()` **không chờ** mọi task kết thúc; nó trả về sau khi phát tín hiệu dừng.

Muốn chờ, gọi `awaitTermination(...)`:

~~~java
executor.shutdown();

boolean terminated =
        executor.awaitTermination(15, TimeUnit.SECONDS);

if (!terminated) {
    System.err.println("Executor did not finish within deadline");
}
~~~

Đây là **đoạn minh họa một phần**, cần một `ExecutorService executor`, import `TimeUnit` và xử lý `InterruptedException`. Khi `awaitTermination(...)` trả về `true`, executor đã chấm dứt theo định nghĩa của Java. Nếu `false`, deadline hết nhưng chưa hoàn tất.

### shutdownNow(): cố gắng dừng, không bảo đảm đã dừng

~~~java
List<Runnable> neverStarted = executor.shutdownNow();
~~~

`shutdownNow()` thường:

- Cố gắng ngắt các task đang chạy (thông qua `Thread.interrupt()`).
- Trả về những task đã nằm trong queue nhưng chưa bắt đầu.
- Không bảo đảm task đang chạy sẽ thực sự dừng. Task bỏ qua interrupt hoặc đang chặn I/O không interruptible có thể tiếp tục.

**Không dùng `shutdownNow()` như thay thế mặc định cho graceful drain.** Nếu có công việc không idempotent hoặc yêu cầu hoàn tất, có thể tạo trạng thái nửa vời, mất dữ liệu hoặc duplicate khi job retry.

### awaitTermination() không tự ngăn task mới

~~~java
boolean done = executor.awaitTermination(10, TimeUnit.SECONDS);
~~~

Gọi riêng `awaitTermination` **trước** khi có shutdown signal không làm executor tự đóng. Phương thức này chỉ chờ executor đi đến trạng thái terminated, hoặc đến deadline/interrupt. Luồng điển hình là:

~~~text
1. stop application admission
2. executor.shutdown()
3. executor.awaitTermination(timeout)
4. nếu chưa xong → escalation có chính sách
~~~

Không nên đảo 1 và 2 nếu các publisher có thể submit việc tới executor giữa hai bước.

### Bảng API

| API | Chặn tác vụ mới? | Chờ đồng bộ? | Xử lý queued tasks? |
| --- | --- | --- | --- |
| `execute(task)`/`submit(task)` | Không; đây là submit | Không chờ kết quả task | Thêm job nếu còn chỗ và executor còn nhận |
| `shutdown()` | Có, tại executor | Không | Giữ các job đã submit để chạy nốt |
| `awaitTermination(t,u)` | Không tự đóng; phụ thuộc trạng thái executor | Có, tới deadline hoặc terminated | Không tự thay đổi queue |
| `shutdownNow()` | Có, và cố interrupt worker | Không đợi đến terminated | Trả về queued tasks chưa chạy |
| `isShutdown()` | Kiểm tra đã yêu cầu shutdown | Không | Không xác nhận tasks đã xong |
| `isTerminated()` | Kiểm tra executor đã terminated | Không | Chỉ true sau khi các task đã kết thúc |

## 5. Admission gate phải chống race condition

Một cách sai dễ gặp:

~~~java
if (accepting.get()) {
    executor.execute(task);
}
~~~

Nếu thread đang đóng ứng dụng đặt `accepting=false` ngay sau khi thread submitter đã đọc `true`, executor có thể vừa shutdown và `execute` ném `RejectedExecutionException`. `AtomicBoolean` làm phép đọc/ghi boolean có visibility tốt, nhưng **không hợp nhất** “kiểm tra rồi submit” thành một thao tác nguyên tử.

Cách đơn giản cho bài học là dùng một monitor duy nhất cho **việc kiểm tra, submit và đóng gate**:

~~~java
private final Object admissionLock = new Object();
private boolean accepting = true;

public boolean submit(Runnable task) {
    synchronized (admissionLock) {
        if (!accepting) {
            return false;
        }

        try {
            executor.execute(task);
            return true;
        }
        catch (RejectedExecutionException rejected) {
            return false;
        }
    }
}

public void closeAdmission() {
    synchronized (admissionLock) {
        accepting = false;
    }
}
~~~

Đây là **đoạn minh họa** cần field `executor` kiểu `Executor`/`ExecutorService` và import `RejectedExecutionException`. Trong code thực tế còn cần báo lý do từ chối và metrics.

Với khóa dùng chung:

- Một submit thành công trước khi đóng gate được ghi nhận là **đã chấp nhận**.
- Một submit đến sau khi gate đóng bị từ chối.
- Không có khoảng hở logic giữa kiểm tra gate và `executor.execute(...)` đối với code tuân thủ cùng monitor.
- `RejectedExecutionException` vẫn phải được xử lý: pool có thể đầy hoặc đã bị đóng bởi cơ chế khác.

Không giữ khóa admission trong **suốt thời gian chạy task**. Khóa chỉ bảo vệ thao tác nộp và chuyển trạng thái, nếu không việc stop có thể bị chặn bởi chính công việc đang chạy.

### Từ chối có nghĩa gì với người gọi?

Một phương thức trả `false` nên khiến caller biết rõ rằng job **chưa được chấp nhận**. Với HTTP có thể trả mã phản hồi phù hợp (thường là 503 hoặc lỗi ứng dụng có Retry-After nếu có chính sách); với message consumer, cần xử lý ack/nack/redelivery chính xác; với producer nội bộ, cần ghi lại để retry hoặc trả lỗi cho tầng gọi.

**Tránh trường hợp xấu nhất:** Phía nhận trả thành công nhưng trong thực tế executor từ chối việc và hệ thống không có log/queue bền vững để phục hồi.

## 6. Spring Boot HTTP graceful shutdown: phạm vi bảo vệ

Spring Boot 3.3 hỗ trợ graceful shutdown cho embedded Tomcat, Jetty, Reactor Netty và Undertow, trong Servlet và Reactive web application. Để bật trong bản 3.3, cấu hình:

~~~properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
~~~

Hoặc YAML:

~~~yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 20s
~~~

Chỉ chọn một cách cấu hình phù hợp dự án; các dòng trên là cấu hình ví dụ, không tạo file riêng trong demo CLI mục 9.

### Điều thực sự xảy ra

- Spring Boot thực hiện graceful web-server shutdown như một phần của `ApplicationContext.close()`.
- Server **không nhận request mới theo cách phù hợp implementation** nhưng cho phép các request đã nhận trước đó hoàn tất trong khoảng grace period.
- `spring.lifecycle.timeout-per-shutdown-phase` giới hạn thời gian chờ trên **mỗi nhóm phase** của lifecycle processor, không phải một timeout bao trùm tất cả hoạt động shutdown.
- Tomcat/Jetty/Reactor Netty có thể từ chối kết nối mới ở network layer; Undertow trong tài liệu Boot 3.3 có thể trả HTTP **503** cho connection/request mới. Không viết code dựa vào một kiểu từ chối duy nhất cho mọi server.

**Giới hạn:** Graceful web shutdown chủ yếu bảo vệ **các HTTP requests đang xử lý**. Nếu request đã gửi một job lên executor rồi trả 202 ngay, request hoàn thành **không chứng minh job nền đã xong**. Khi ấy cần **drain executor riêng** hoặc chuyển job sang broker/storage bền vững.

### Đừng lấy mặc định của bản Spring Boot mới áp vào 3.3

Một số bản Spring Boot mới hơn bật graceful shutdown mặc định. Bài này dùng **Spring Boot 3.3** nên đặt rõ `server.shutdown=graceful` khi muốn chính sách graceful. Không suy diễn từ tài liệu phiên bản hiện tại của framework sang một project vẫn dùng Boot 3.3.

### Cổng mở không phải readiness

Web server có thể bind port trước khi ứng dụng phát `ApplicationReadyEvent`, và quá trình drain có thể bắt đầu trong lúc socket đang chuyển trạng thái. Một load balancer hoặc orchestrator nên dựa trên readiness/termination signals thích hợp, thay vì chỉ thử kết nối TCP.

Trong môi trường Kubernetes, quy trình thường có các bước: đánh dấu pod không nên nhận traffic mới, cho routing có thời gian cập nhật, gửi SIGTERM, thực hiện drain và chờ cho đến `terminationGracePeriodSeconds`. **PreStop hook và propagation delay** cũng có thể tiêu tốn cùng ngân sách thời gian đó; cần tính tổng thời gian, không chỉ đặt một timeout trong ứng dụng.

## 7. Spring lifecycle và thứ tự dừng các thành phần

### ContextClosedEvent

Spring Framework phát `ContextClosedEvent` khi `ApplicationContext` đang đóng. Một listener có thể dùng để **phát tín hiệu ngừng nhận việc** tại thời điểm bắt đầu đóng context:

~~~java
@EventListener(ContextClosedEvent.class)
public void rejectNewJobs() {
    accepting.set(false);
}
~~~

Đây là **đoạn minh họa**, cần bean chứa method, imports `EventListener` và `ContextClosedEvent`, và một cơ chế admission gate thread-safe. Lưu ý chỉ `AtomicBoolean` không giải quyết toàn bộ race “check-then-submit” như mục 5; cần thiết kế gate và xử lý reject đúng.

Không nên nhồi một công việc chờ hàng chục giây vào listener `ContextClosedEvent` rồi cho rằng các lifecycle components đã dừng. Đây là sự kiện thông báo context đang đóng; việc dừng có thứ tự nên đặt vào lifecycle/destroy hook được thiết kế cho nó.

### SmartLifecycle.stop(Runnable callback)

`org.springframework.context.SmartLifecycle` hỗ trợ:

~~~java
@Override
public void stop(Runnable callback) {
    // 1) Ngừng admission
    // 2) Yêu cầu các worker ngừng nhận việc
    // 3) Đợi công việc đã chấp nhận hoàn tất / được xử lý lỗi
    // 4) Sau khi thật sự dừng, callback.run()
}
~~~

Đây là **đoạn hướng dẫn**, không phải implementation độc lập. Ý nghĩa của `callback` là thông báo cho `DefaultLifecycleProcessor` rằng bước stop của component đã hoàn tất. Nếu component dừng bất đồng bộ, callback phải chạy **khi công việc dừng thật sự hoàn tất**, không phải ngay sau khi submit một task “stop”.

`SmartLifecycle` còn có:

- `start()` để bắt đầu dịch vụ.
- `isRunning()` để phản ánh trạng thái.
- `isAutoStartup()` để tự start khi context refresh.
- `getPhase()` để điều phối thứ tự nhóm lifecycle.
- `stop()` từ `Lifecycle` cho đường dừng tường minh.

**Phase nhỏ start trước; phase lớn stop trước.** Dùng phase/`@DependsOn` để stop producer/ingress trước consumer, consumer trước các tài nguyên dưới nó khi phù hợp. **Các bean độc lập cùng phase không có thứ tự tuyệt đối được bảo đảm**; đừng dựa vào thứ tự bean definitions hay `@Order` để xác định thứ tự dừng.

### Phân biệt stop callback và “việc đã được lưu bền vững”

Một worker có thể đã thoát, nhưng một job chưa ack/commit đúng cách. Ngược lại, job đã lưu durable thì có thể được xử lý lại sau restart dù chưa chạy hoàn tất trong tiến trình cũ. Vì vậy lifecycle “dừng thành công” và nghiệp vụ “không mất việc” cần những tiêu chí khác nhau, gồm transaction và retry policy.

## 8. ThreadPoolTaskExecutor và cấu hình chờ task khi Spring đóng

Trong ứng dụng Spring, `ThreadPoolTaskExecutor` thuộc `org.springframework.scheduling.concurrent` là wrapper tiện lợi cho thread pool có quản lý Spring lifecycle.

Một cấu hình điển hình:

~~~java
@Configuration
public class ExecutorConfiguration {

    @Bean("backgroundExecutor")
    ThreadPoolTaskExecutor backgroundExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();

        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("background-");

        // Cho running tasks và queued tasks hoàn tất khi shutdown.
        executor.setWaitForTasksToCompleteOnShutdown(true);

        // Chờ tối đa 20 giây trong bước hủy executor.
        executor.setAwaitTerminationSeconds(20);

        return executor;
    }
}
~~~

Đoạn trên là **một file cấu hình minh họa**, không thêm nó vào project mục 9. Khi dùng thật, cần import `@Configuration`, `@Bean` và `ThreadPoolTaskExecutor`. Spring khởi tạo bean executor và quản lý destruction/lifecycle khi context đóng.

### Ý nghĩa chính xác của hai flag

**`setWaitForTasksToCompleteOnShutdown(true)`** yêu cầu executor thực hiện soft/orderly shutdown, không chủ động interrupt running tasks và tiếp tục thực thi những task đã nằm trong queue theo hợp đồng. Nó có thể **bỏ qua coordinated lifecycle stop phase** và chuyển việc chờ sang bước destroy riêng của executor.

**`setAwaitTerminationSeconds(20)`** làm bước shutdown của executor **chặn tối đa khoảng 20 giây** để đợi termination trước khi phần destruction còn lại của context tiếp tục. Đây là timeout chờ, **không phải cơ chế bảo đảm job chắc chắn xong trong 20 giây**.

Hai setting không tự tạo một admission gate cấp nghiệp vụ. Đặc biệt, `waitForTasksToCompleteOnShutdown(true)` có semantics cho phép một số submission muộn trước khi executor thực sự đi vào destroy/shutdown; vì thế nếu ứng dụng cần nói “ngay từ lúc bắt đầu close sẽ không nhận thêm việc”, hãy **đóng gate của publisher/consumer trước**.

### Một lưu ý riêng cho Spring Framework 6.1

`ThreadPoolTaskExecutor` tham gia lifecycle stop và xử lý tín hiệu context close. Các thuộc tính như `acceptTasksAfterContextClose`, `strictEarlyShutdown` (từ 6.1.4) và `waitForTasksToCompleteOnShutdown` có tương tác với nhau. Cụ thể, các lựa chọn cho late shutdown có thể bỏ qua coordinated stop và chuyển sang destroy phase.

Do vậy:

- **Không** chọn ngẫu nhiên cả ba flag rồi mong “càng nhiều true càng graceful”.
- Nếu bắt buộc chặn job mới ngay khi context bắt đầu close, hãy có **admission control độc lập** và test `RejectedExecutionException`.
- Nếu task cần database/client bean trong quá trình drain, đảm bảo chúng **chưa bị destroy** trước khi executor đợi xong; một `awaitTerminationSeconds` hữu hạn có thể hữu ích, nhưng thứ tự các bean vẫn phải được thiết kế.
- Nếu cần kiểm soát chặt một chuỗi producer → worker → dependent resources, cân nhắc dùng `SmartLifecycle` điều phối rõ ràng thay vì chỉ sửa cấu hình executor.

**Không nên tự thay `ThreadPoolTaskExecutor` bằng `Executors.newFixedThreadPool(...)` trong một `@Bean` rồi quên lifecycle:** nếu executor do ứng dụng tự tạo, hãy chắc chắn có destroy hook hoặc component sở hữu nó như ví dụ mục 9.

## 9. Ví dụ hoàn chỉnh: chặn task mới, drain task cũ khi close context

Ví dụ Java 17+ / Spring Boot 3.3.13 dưới đây dùng **một executor tự quản lý** bên trong bean `SmartLifecycle`. Nó không có HTTP server hay database nên tập trung vào **giao thức admission và drain**.

Trong demo:

1. Spring Boot refresh context, `WorkCoordinator.start()` được gọi.
2. Main nộp một task cũ và cho task chạy đến một barrier.
3. Main tạo một thread khác để gọi `context.close()`.
4. `stop(Runnable)` đóng gate, báo main rằng từ thời điểm này không nhận thêm task.
5. Main thử nộp task mới và nhận `false`.
6. Main cho task cũ kết thúc.
7. Lifecycle processor chờ executor terminated, nhận callback và hoàn tất close.
8. Main đợi close thread kết thúc, rồi in kết quả.

**Tại sao có các CountDownLatch?** Chúng chỉ dùng để khiến thứ tự log ví dụ **xác định và kiểm thử được**, không phụ thuộc `Thread.sleep(...)` hoặc tốc độ CPU.

### 9.1. Cấu trúc project

~~~text
graceful-drain-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/com/example/drain/
    ├── GracefulDrainApplication.java
    └── WorkCoordinator.java
~~~

**`settings.gradle`:**

~~~groovy
rootProject.name = 'graceful-drain-demo'
~~~

**`build.gradle`:**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation platform(
        'org.springframework.boot:spring-boot-dependencies:3.3.13'
    )
    implementation 'org.springframework.boot:spring-boot-starter'
}

springBoot {
    mainClass = 'com.example.drain.GracefulDrainApplication'
}
~~~

Dự án không dùng web starter. Nếu Gradle chưa cài, có thể thêm Gradle Wrapper tương thích Spring Boot 3.3; cấu trúc trên không chứa wrapper sẵn. Cần JDK 17+.

### 9.2. WorkCoordinator: SmartLifecycle sở hữu executor

**`src/main/java/com/example/drain/WorkCoordinator.java`:**

~~~java
package com.example.drain;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.TimeUnit;

import org.springframework.context.SmartLifecycle;

public final class WorkCoordinator implements SmartLifecycle {

    private final Object admissionLock = new Object();

    private final ExecutorService executor =
            Executors.newSingleThreadExecutor(r ->
                    new Thread(r, "demo-worker"));

    private final CountDownLatch taskStartPermit =
            new CountDownLatch(1);

    private final CountDownLatch taskStarted =
            new CountDownLatch(1);

    private final CountDownLatch taskFinishPermit =
            new CountDownLatch(1);

    private final CountDownLatch admissionClosed =
            new CountDownLatch(1);

    private volatile boolean running;
    private boolean accepting;

    @Override
    public void start() {
        synchronized (admissionLock) {
            accepting = true;
            running = true;
        }
        System.out.println("LIFECYCLE: started");
    }

    public boolean submitFirstTask() {
        synchronized (admissionLock) {
            if (!accepting) {
                return false;
            }
            try {
                executor.execute(() -> {
                    try {
                        taskStartPermit.await();
                        System.out.println("TASK: running");
                        taskStarted.countDown();

                        taskFinishPermit.await();
                        System.out.println("TASK: completed");
                    }
                    catch (InterruptedException interrupted) {
                        Thread.currentThread().interrupt();
                        System.out.println("TASK: interrupted");
                    }
                });
                return true;
            }
            catch (RejectedExecutionException rejected) {
                return false;
            }
        }
    }

    public boolean submitLateTask() {
        synchronized (admissionLock) {
            if (!accepting) {
                return false;
            }
            try {
                executor.execute(() ->
                        System.out.println("TASK: unexpected late work"));
                return true;
            }
            catch (RejectedExecutionException rejected) {
                return false;
            }
        }
    }

    public void allowTaskToStart() {
        taskStartPermit.countDown();
    }

    public void awaitTaskStarted() throws InterruptedException {
        if (!taskStarted.await(5, TimeUnit.SECONDS)) {
            throw new IllegalStateException(
                    "Demo task did not start in time");
        }
    }

    public void awaitAdmissionClosed() throws InterruptedException {
        if (!admissionClosed.await(5, TimeUnit.SECONDS)) {
            throw new IllegalStateException(
                    "Demo shutdown did not start in time");
        }
    }

    public void allowTaskToFinish() {
        taskFinishPermit.countDown();
    }

    @Override
    public void stop(Runnable callback) {

        // Gate đóng trước khi executor ngừng nhận task.
        synchronized (admissionLock) {
            accepting = false;
        }
        System.out.println("SHUTDOWN: admission closed");
        admissionClosed.countDown();

        executor.shutdown();

        try {
            boolean terminated =
                    executor.awaitTermination(15, TimeUnit.SECONDS);

            if (!terminated) {
                System.err.println(
                        "SHUTDOWN: deadline exceeded; interrupt requested");
                executor.shutdownNow();
                terminated =
                        executor.awaitTermination(2, TimeUnit.SECONDS);
            }

            if (terminated) {
                running = false;
                System.out.println("SHUTDOWN: drained");
                callback.run();
            }
            else {
                // Không được báo “đã dừng” khi worker còn sống.
                System.err.println(
                        "SHUTDOWN: incomplete; worker may still run");
            }
        }
        catch (InterruptedException interrupted) {
            Thread.currentThread().interrupt();
            executor.shutdownNow();
            System.err.println(
                    "SHUTDOWN: waiting thread interrupted");
        }
    }

    @Override
    public void stop() {
        stop(() -> { });
    }

    @Override
    public boolean isRunning() {
        return running;
    }

    @Override
    public boolean isAutoStartup() {
        return true;
    }

    @Override
    public int getPhase() {
        return 0;
    }
}
~~~

**Các điểm quan trọng trong mã:**

- Cùng một `admissionLock` bảo vệ kiểm tra `accepting`, enqueue task và chuyển `accepting=false`; vì vậy code submit thông qua bean này không thể lọt qua gate sau khi gate đóng.
- `CountDownLatch` chỉ là công cụ điều khiển thí nghiệm: task cũ được nộp, chờ main ra lệnh bắt đầu, sau đó chờ main ra lệnh hoàn tất.
- `executor.shutdown()` từ chối job mới tại executor nhưng vẫn cho job trước đó tiếp tục.
- `awaitTermination(15, SECONDS)` chờ có deadline. Demo chính luôn cho task hoàn thành sớm trước khi deadline.
- Nếu quá deadline, code yêu cầu interruption với `shutdownNow()` rồi chờ thêm một khoảng ngắn; nó **không nói rằng interrupt chắc chắn kết thúc task**.
- `callback.run()` chỉ được gọi ở nhánh executor **thực sự terminated**, và `running` chuyển `false` ở nhánh đó. Nếu không thể xác nhận terminated, code báo lỗi và để lifecycle processor xử lý timeout, thay vì ngụy báo stop thành công.
- Với một thành phần production, cần chính sách xử lý khi bị interrupt ngay trong quá trình await (deadline chung, escalation, telemetry, external supervisor). Demo ưu tiên làm rõ **điều kiện được phép báo callback**.

Trong đường lỗi sau khi đã gọi `shutdownNow()`, task có thể bị bỏ dở; **không được gọi tình huống đó là “drained thành công theo nghiệp vụ”** nếu yêu cầu của task là phải hoàn tất. `SHUTDOWN: drained` trong mã có nghĩa **executor terminated**, không chứng nhận từng job đã commit thành công khi có interruption. Đường bình thường của ví dụ không đi qua cancellation.

### 9.3. Main khởi động và đóng context có chủ đích

**`src/main/java/com/example/drain/GracefulDrainApplication.java`:**

~~~java
package com.example.drain;

import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class GracefulDrainApplication {

    public static void main(String[] args)
            throws InterruptedException {

        SpringApplication app =
                new SpringApplication(GracefulDrainApplication.class);

        app.setWebApplicationType(WebApplicationType.NONE);
        app.setBannerMode(Banner.Mode.OFF);
        app.setLogStartupInfo(false);

        ConfigurableApplicationContext context = app.run(args);
        WorkCoordinator work = context.getBean(WorkCoordinator.class);

        boolean accepted = work.submitFirstTask();
        System.out.println("MAIN: first accepted=" + accepted);

        // Bảo đảm main in trước khi worker bắt đầu log.
        work.allowTaskToStart();
        work.awaitTaskStarted();

        // close() sẽ gọi SmartLifecycle.stop(Runnable).
        Thread closer = new Thread(context::close, "context-closer");
        closer.start();

        // Đợi gate đóng thật, không sleep/đoán thời gian.
        work.awaitAdmissionClosed();

        boolean lateAccepted = work.submitLateTask();
        System.out.println("MAIN: late accepted=" + lateAccepted);

        // Cho task đã nhận từ trước hoàn tất.
        work.allowTaskToFinish();

        closer.join();
        System.out.println("MAIN: context closed");
    }

    @Bean
    WorkCoordinator workCoordinator() {
        return new WorkCoordinator();
    }
}
~~~

**Đặc điểm cần hiểu:**

1. `WorkCoordinator` là bean Spring do `@Bean` tạo ra, có phase `0` và `isAutoStartup()==true`, được khởi động trong context refresh.
2. `SpringApplication.run(args)` hoàn tất trước khi main nộp task. Demo là CLI nên không phải ứng dụng server giữ request mãi.
3. Lời gọi `context.close()` ở thread `context-closer` cho phép main tiếp tục quan sát gate trong lúc shutdown đang chờ task.
4. `awaitAdmissionClosed()` giúp test chỉ gửi yêu cầu trễ **sau khi** gate đã chuyển sang đóng. Vì vậy `submitLateTask()` trả `false`.
5. Task cũ vẫn ở trong executor; sau khi main gọi `allowTaskToFinish()`, worker in hoàn tất, executor terminated và lifecycle callback được gọi.
6. `closer.join()` khiến main chỉ in “context closed” khi thread thực hiện `context.close()` kết thúc.

**Chú ý:** Trong một JVM thực tế, framework, signal handler, timeout và thread scheduling có thể thêm những log khác. Ví dụ chỉ tuyên bố thứ tự **các dòng in bởi hai class của demo** trong đường chạy bình thường, không cam kết thứ tự mọi dòng log Spring/Gradle.

### 9.4. Chạy và output kỳ vọng

Từ thư mục `graceful-drain-demo`:

~~~bash
gradle bootRun
~~~

Nếu có Gradle Wrapper thì dùng `./gradlew bootRun` trên Linux/macOS hoặc `.\gradlew.bat bootRun` trên Windows; project mẫu không tự tạo wrapper.

Các dòng do **mã của demo** tự in, trong điều kiện không timeout hoặc interruption bất thường:

~~~text
LIFECYCLE: started
MAIN: first accepted=true
TASK: running
SHUTDOWN: admission closed
MAIN: late accepted=false
TASK: completed
SHUTDOWN: drained
MAIN: context closed
~~~

Lý do thứ tự được kiểm soát:

- `MAIN: first accepted=true` in trước khi main mở `taskStartPermit`.
- `TASK: running` in trước khi `taskStarted` được countdown, và main chỉ tiếp tục sau đó.
- `SHUTDOWN: admission closed` in trước khi `admissionClosed` được countdown.
- `MAIN: late accepted=false` được in sau khi gate đóng, và trước khi main mở `taskFinishPermit`.
- `TASK: completed` xuất hiện trước khi thread worker thoát; `awaitTermination` chỉ trả `true` sau khi executor hoàn toàn terminated.
- `SHUTDOWN: drained` xuất hiện trước callback và trước khi `context.close()` trả về.

Nếu chương trình không ra đúng output vì bị timeout, **đó là đường lỗi cần điều tra**, không phải một thứ tự log hợp lệ khác của đường thành công đã được các latch kiểm soát.

### 9.5. Ba thử nghiệm hữu ích

**Thử nghiệm A — Bỏ bước đóng admission gate.** Nếu chỉ `executor.shutdown()` mà phía nhận không có gate/không xử lý reject, client/producer có thể nghĩ job được chấp nhận dù executor từ chối. Thử nghiệm này chỉ nên làm trong project sandbox, không dùng để tiếp nhận job production.

**Thử nghiệm B — Không mở `taskFinishPermit`.** Thread worker tiếp tục chờ; sau 15 giây `awaitTermination` trả `false`, code yêu cầu interrupt. Trong tình huống này, log không được đánh đồng với hoàn thành nghiệp vụ. Có thể nhận `TASK: interrupted` thay vì `TASK: completed`.

**Thử nghiệm C — Thay `shutdown()` bằng `shutdownNow()` ngay khi đóng gate.** Khi task còn chạy, nó có thể bị interrupt trước khi hoàn tất; khi task nằm trong queue, `shutdownNow()` có thể trả các queued tasks chưa thực hiện. Điều đó cho thấy vì sao forced shutdown chỉ nên là nhánh escalation.

## 10. Tại sao không dùng riêng @PreDestroy để làm tất cả?

`@PreDestroy` thường chạy ở giai đoạn **destroy bean**. Nó hợp lý để đóng một tài nguyên đã không còn được dùng, nhưng với hệ thống nhiều producer/consumer, bạn thường cần **ngừng nhận việc trước** rồi mới phá hủy resources.

Ví dụ nguy hiểm:

~~~java
@PreDestroy
public void close() {
    executor.shutdownNow();
    databaseClient.close();
}
~~~

Đây là **mẫu không khuyến nghị**, không phải code áp dụng vào ví dụ. Nó:

- Ngắt task không có drain.
- Có thể đóng database client khi một task vẫn đang commit.
- Không nêu deadline, queue policy hoặc trạng thái job còn dở.
- Không bảo đảm producer ngừng submit trước lúc executor đóng.

Có thể dùng `@PreDestroy` sau khi các thành phần `SmartLifecycle` đã dừng theo thứ tự, hoặc dùng một bean sở hữu resource có destroy method để chờ đến khi mọi task dùng nó đã xong.

### @DependsOn và resource ownership

Trong một kiến trúc nhiều bean, nếu component A sử dụng component B, Spring có thể có thông tin dependency qua constructor injection hoặc `@DependsOn`. Điều này hỗ trợ thứ tự khởi tạo/hủy bean. Nhưng **không tự thay thế** việc thiết kế một drain protocol có deadline cho những job đang hoạt động ngoài bean lifecycle.

Nếu một worker thread dùng `DataSource`, bảo đảm DataSource còn sống cho đến khi worker kết thúc; nếu dùng một executor Spring-managed, phải hiểu stop/destruction phase của executor so với database/client beans khác.

## 11. HTTP request đang chạy và job nền: hai deadline khác nhau

Giả sử một request:

~~~text
T=0s   HTTP POST /reports
T=0.1s server đưa report job vào executor
T=0.2s HTTP trả 202 Accepted
T=5s   bắt đầu shutdown
T=12s  job mới ghi kết quả xong
~~~

Khi graceful web server shutdown ở `T=5s`, HTTP request trên đã kết thúc tại `T=0.2s`, vì vậy server không còn một **HTTP request in-flight** tương ứng để chờ. Nhưng task background còn chạy thêm nhiều giây.

Vì vậy cấu hình:

~~~properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
~~~

**không tự bảo đảm** job đã nộp vào `ExecutorService` tùy biến tiếp tục chạy đến cuối. Cần:

- Admission gate cho endpoint/publisher.
- Chính sách executor drain.
- Một nơi lưu trạng thái job bền vững nếu cần.
- Readiness/health/telemetry cho shutdown progress.
- Deadline khớp với ngân sách container/orchestrator.

### Với HTTP request không tách background job

Nếu handler giữ request mở và xử lý đồng bộ trong 8 giây, graceful web shutdown có thể đợi request đó hoàn tất trong phase grace. Nhưng nếu handler dùng streaming, WebFlux hoặc tác vụ async trả response lâu dài, phải hiểu contract completion thực tế của server và ứng dụng. Không dùng `Thread.sleep` trong demo để đại diện mọi loại request.

## 12. Message consumer, ack và redelivery

Với Kafka, RabbitMQ, JMS hoặc một polling source riêng, câu “dừng nhận việc mới” cần dịch sang cơ chế của từng thư viện:

- Ngừng poll/consume hoặc pause listener/container theo API được hỗ trợ.
- Đợi hoặc checkpoint các messages **đã nhận** đang xử lý.
- Chỉ ack/commit offset khi kết quả đạt điều kiện bền vững.
- Nếu hết deadline, để message chưa ack được redeliver hoặc chuyển theo retry/DLQ policy.
- Đảm bảo consumer không xác nhận message quá sớm khiến hệ thống mất khả năng replay.

Không viết một method chung `consumer.stop()` rồi khẳng định nó có cùng semantics với mọi broker. Tùy client, stop có thể dừng poll mới, cancel tasks, đóng connection hoặc chờ xử lý hiện tại — cần đọc đúng API/version.

### At-least-once và tính idempotent

Trong hệ thống queue thông thường, có thể xuất hiện trường hợp:

~~~text
worker hoàn tất side effect
    |
    +-- tiến trình bị kill trước khi ack/commit
    |
broker redeliver message cho instance khác
    |
    +-- side effect có nguy cơ thực hiện lần thứ hai
~~~

Vì vậy “graceful shutdown” có thể **giảm** số tác vụ bị ngắt nhưng **không loại bỏ được** duplicate. Cần idempotency keys, unique constraint, transaction/outbox hoặc cơ chế deduplication phù hợp.

Đừng dùng một biến `static Set<String> completedJobs` trong JVM làm bảo đảm chống duplicate toàn cluster; state này mất khi process restart và không chia sẻ giữa các replica.

## 13. Scheduler và @Async: tránh khởi tạo job mới lúc dừng

Một phương thức `@Scheduled` có thể tiếp tục được kích hoạt khi application context chưa hoàn tất quá trình close. Trong shutdown, cần chắc rằng scheduler không tạo thêm việc đang chờ executor drain.

Các chiến lược:

1. Dừng hoặc pause scheduler theo API được hỗ trợ trước khi drain worker.
2. Dùng admission gate tại chỗ scheduler submit task, để callback trễ bị từ chối.
3. Bảo đảm reject được xử lý (log, retry, checkpoint) thay vì mất task.
4. Nếu scheduling là distributed, cần đảm bảo leader/lock/next-run policy để instance mới không chạy trùng.
5. Với periodic task, phân biệt “dừng tạo lần chạy mới” và “dừng công việc đang chạy”.

Với `@Async`, target method thường được submit vào một `TaskExecutor`. Cấu hình executor có thể làm thay đổi thời điểm nó từ chối hoặc đợi task. Nếu dùng `@Async void`, exception trong background job không tự trả về caller; cần có exception handler, logging và telemetry thích hợp.

**Không chỉ dựa vào proxy @Async:** self-invocation trong cùng class có thể bỏ qua proxy, khiến method chạy đồng bộ ngoài ý muốn. Điều này tác động cách xác định “task nào đang chạy trong executor” khi dừng.

## 14. Dự trù ngân sách shutdown

Nên tính thời gian shutdown ở cấp deployment, không chỉ trong Java:

~~~text
t0: quyết định loại bỏ instance
    |
    +-- cập nhật readiness / drain load balancer
    |       (có propagation delay)
    |
    +-- preStop / SIGTERM
    |       (cơ chế phụ thuộc orchestration)
    |
    +-- Spring context close
    |       +-- stop HTTP ingress
    |       +-- stop job admission
    |       +-- drain worker/broker tasks
    |       +-- close connection / database / clients
    |
    +-- JVM exit trước khi hard deadline
            |
            v
        nếu quá hạn: có thể bị SIGKILL / forced termination
~~~

Các mốc ở trên là **mô hình logic**; thứ tự preStop/SIGTERM và readiness propagation cụ thể thuộc nền tảng triển khai. Không giả định Kubernetes tự bảo đảm pod lập tức biến mất khỏi mọi load balancer trước khi gửi SIGTERM.

### Ba bộ đếm thời gian dễ nhầm

| Timeout | Phạm vi | Ví dụ |
| --- | --- | --- |
| `spring.lifecycle.timeout-per-shutdown-phase` | Mỗi nhóm phase của Spring lifecycle processor | `20s` |
| `ThreadPoolTaskExecutor.setAwaitTerminationSeconds` | Bước executor destruction/await | `20` |
| Container `terminationGracePeriodSeconds` | Ngân sách hard stop cấp pod/container | Phải đủ lớn cho preStop + close + buffer |

Các timeout **không nhất thiết chạy nối tiếp đơn giản** và không đảm bảo tổng đúng bằng một số. Dù vậy, đặt tất cả cùng một giá trị sát giới hạn hard stop có thể không để lại thời gian cho flush logs, đóng resource và shutdown hooks.

**Ví dụ nguyên tắc:** Nếu công việc thường mất 10 giây và cần 5 giây để flush state/ack, tổng grace budget phải tính thêm propagation và buffer. Không cứng nhắc nói một cấu hình cụ thể phù hợp mọi hệ thống.

### SIGTERM và SIGKILL

- **SIGTERM** thường cho ứng dụng/JVM cơ hội thực hiện shutdown hooks, đóng Spring context và dọn resources.
- **SIGKILL** không cho JVM chạy Java shutdown hooks, `@PreDestroy` hoặc `SmartLifecycle.stop`.
- Một lỗi máy, mất điện, OOM hoặc container bị hard kill cũng không thể bảo đảm graceful callback.
- Một số IDE/task runner có cơ chế stop ngay, không gửi tín hiệu chuẩn; không dùng duy nhất nút Stop của IDE để đánh giá shutdown behavior production.

Do đó mọi job quan trọng cần cơ chế khôi phục **ngay cả khi graceful shutdown không diễn ra**.

## 15. Những trường hợp phải quyết định chính sách nghiệp vụ

### 15.1. Job ngắn, idempotent, có deadline

Đây là ứng viên tốt để drain: ngừng nhận job mới, chờ running/queued jobs hoàn tất trong khoảng ngân sách, log kết quả. Nếu job không hoàn tất thì lưu trạng thái và retry.

### 15.2. Job chạy nhiều giờ

Không nên giữ một pod trong trạng thái terminating hàng giờ chỉ để chờ job. Thay vào đó cân nhắc checkpoint, queue bền vững, worker chuyên dụng, lease/heartbeat hoặc cơ chế resume để instance khác tiếp tục.

### 15.3. Task đang giữ transaction

Nếu task đang trong DB transaction, cố interrupt giữa chừng có thể gây rollback, nhưng đó là hành vi phụ thuộc driver, framework và transaction boundary. Không suy đoán `shutdownNow()` tự rollback mọi side effect ngoài DB.

### 15.4. Task thực hiện payment hoặc gửi email

Một job có external side effect phải có idempotency key hoặc dấu vết giao dịch; nếu quá deadline rồi retry mù quáng, có thể thanh toán/gửi email hai lần.

### 15.5. Stream/long polling

Một request streaming có thể kéo dài mãi. Cần quyết định cho phép hoàn tất tự nhiên, cắt stream có giao thức resume, hay graceful reconnect. Đặt deadline và giải thích rõ cho client.

### 15.6. Multi-replica deployment

Khi rolling deployment, instance mới có thể nhận việc trong khi instance cũ đang drain. Không dùng local boolean để bảo đảm toàn hệ thống chỉ có một worker sở hữu job. Cần queue lease/assignment, partition rebalance hoặc distributed lock phù hợp.

## 16. Metrics và logs nên có

Một hệ thống có thể log các mốc:

~~~text
shutdown_requested
admission_closed
inflight_before_drain=<N>
queued_before_drain=<N>
drain_completed=<N>
drain_failed=<N>
drain_timeout=<true|false>
resources_closed
context_closed
~~~

Đây là **mẫu log cấu trúc**, không phải output thực của project mục 9. Không nên in dữ liệu nhạy cảm trong payload vào logs.

Các thước đo có ích:

- `jobs.accepted.total`, `jobs.rejected.total`.
- `jobs.running`, `jobs.queued`, `jobs.inflight`.
- `jobs.completed.total`, `jobs.failed.total`, `jobs.cancelled.total`.
- `shutdown.drain.duration`, `shutdown.timeout.total`.
- `executor.active.count`, `executor.queue.size`, `executor.completed.task.count` khi executor hỗ trợ.
- Thời gian từ SIGTERM đến lúc ngừng nhận traffic mới; thời gian từ intake closed đến last job completed.

Không nhất thiết expose mọi metric cho mọi service; chọn số liệu giúp trả lời: “Có nhận việc sau shutdown không?”, “Còn bao nhiêu job chưa kết thúc?”, “Có job nào bị mất/duplicate không?” và “Có vượt grace period không?”.

## 17. Kiểm thử shutdown không dựa vào Thread.sleep

Một bài test dễ bị flaky:

~~~java
Thread.sleep(1000);
context.close();
assertEquals(0, activeTasks);
~~~

Đây là **mẫu minh họa không khuyến nghị**; thứ tự task phụ thuộc scheduling và tốc độ máy. `sleep` chỉ tạo độ trễ, **không chứng minh** task đã tới mốc mong đợi.

Thay vào đó dùng:

- `CountDownLatch` để đồng bộ “task đã bắt đầu”, “shutdown đã đóng gate” và “cho phép task kết thúc”.
- `Future` hoặc `CompletableFuture` để quan sát kết quả task.
- `awaitTermination` để chứng minh executor đã terminated.
- Bộ đếm in-flight có đồng bộ và test invariant `accepted == completed + failed + cancelled + pending` theo mô hình nghiệp vụ.
- Timeout cho các thao tác chờ trong test để tránh treo pipeline CI vô hạn.
- Kiểm tra cả ngả bình thường và ngả deadline, không chỉ happy path.

### Những invariant cần assert

**Trên đường dừng bình thường:**

1. Task đã chấp nhận trước gate close vẫn có cơ hội chạy nốt.
2. Task đến sau gate close luôn bị từ chối.
3. Context không báo close hoàn tất trước khi drain callback chạy.
4. Executor terminated trước khi tài nguyên dependent bị đóng.
5. Không có job nào “đã accepted” nhưng mất hoàn toàn không có trạng thái/recovery plan.

**Trên đường timeout/interrupt:**

1. Có log/metric và lý do lỗi rõ ràng.
2. Không báo “drained all work” khi task chưa hoàn tất.
3. Có đường retry/redelivery/checkpoint nếu công việc cần bền vững.
4. Timeout của ứng dụng nhỏ hơn ngân sách hard kill sau khi trừ buffer.
5. Task không hợp tác với interrupt được xử lý như một giới hạn an toàn, không giả định `shutdownNow()` thần kỳ dừng được.

## 18. Lỗi thường gặp và cách khắc phục

**1. Chỉ gọi executor.shutdown() rồi coi đã xong.** Sai. `shutdown()` không đợi task kết thúc; dùng `awaitTermination` hoặc một lifecycle coordination phù hợp.

**2. Gọi awaitTermination mà không có shutdown signal.** Không chủ động kết thúc executor; trước hết ngừng nhận việc rồi yêu cầu shutdown.

**3. Dùng shutdownNow() làm cách shutdown chuẩn.** Có thể interrupt running tasks và bỏ queued tasks, gây công việc nửa chừng hoặc mất việc.

**4. Không khóa cặp check-then-submit.** Một boolean không đủ tạo nguyên tử cho việc xét gate và enqueue; cần monitor/lock hoặc cơ chế tuyến tính khác, cộng với xử lý reject.

**5. Đóng executor trước khi dừng producer.** Producer có thể tiếp tục submit và thấy reject không được xử lý. Dừng nguồn tạo việc trước.

**6. Dừng HTTP server nhưng quên queue consumer.** Web graceful shutdown không tự dừng message listeners, scheduler hoặc background executors tự tạo.

**7. Nghĩ HTTP 202 Accepted bảo đảm job nền đã hoàn tất.** 202 chỉ cho biết server chấp nhận yêu cầu theo giao thức/ứng dụng; cần durable handoff và tracking job nếu muốn bảo đảm trách nhiệm.

**8. Chờ running tasks nhưng quên queued tasks.** Queue có thể còn backlog; phải định nghĩa drain toàn queue hay chuyển/retry chưa chạy.

**9. Đóng DataSource trước khi job commit.** Worker vẫn có thể cần DB; thiết kế lifecycle/dependency để tài nguyên còn sống trong lúc drain.

**10. Gọi SmartLifecycle callback ngay sau khi submit shutdown async.** Sai nếu component chưa thực sự dừng; callback biểu thị quá trình stop đã hoàn thành.

**11. Không gọi callback khi stop thành công.** LifecycleProcessor có thể chờ tới timeout vì không biết component đã dừng.

**12. Dùng @PreDestroy để kill thread ngay.** Destroy callback không thay thế một admission/drain protocol có thứ tự.

**13. Tin rằng mọi cùng-phase lifecycle bean có thứ tự rõ.** Không có cam kết đối với các peer độc lập; dùng phase khác hoặc `@DependsOn`.

**14. Cho rằng Spring Boot 3.3 bật graceful HTTP shutdown mặc định vì bản mới làm như vậy.** Không dùng tài liệu phiên bản mới để suy ra behavior của dependency cũ; cấu hình `server.shutdown=graceful` tường minh trong 3.3.

**15. Gộp timeout-per-shutdown-phase và awaitTerminationSeconds thành cùng một timeout.** Hai cơ chế áp dụng ở các bước khác nhau; phải tính cả ngân sách container.

**16. Đặt awaitTerminationSeconds nhưng không đóng admission.** Flag chờ termination không bảo đảm phía publisher ngừng nộp job từ sớm.

**17. Chờ vô thời hạn để “không mất job”.** Một task bị treo có thể khiến deployment không kết thúc; cần deadline, recovery plan và forced-stop policy.

**18. Tưởng Thread.interrupt là lệnh kill chắc chắn.** Interrupt là tín hiệu hợp tác; code có thể bỏ qua hoặc chặn trên I/O không thể ngắt.

**19. Không xử lý InterruptedException.** Nuốt interruption làm shutdown khó kiểm soát; khôi phục interrupt status khi phù hợp và thực hiện cleanup/escalation.

**20. Ack message trước khi side effect được lưu bền vững.** Có thể mất dữ liệu nếu tiến trình chết giữa ack và commit. Thiết kế ack/transaction/retry theo broker.

**21. Không có idempotency khi redelivery.** Job có thể chạy trùng khi tiến trình bị kill sau side effect nhưng trước ack.

**22. Chạy nhiều replicas và dựa vào in-memory flag.** Admission flag chỉ áp dụng cho một instance, không thay cho distributed ownership hoặc queue lease.

**23. Dùng fixed Thread.sleep trong integration test.** Dễ flaky và không chứng minh quan hệ cần test; dùng latch/barrier/future.

**24. Bật mọi flag executor “chờ task” mà không xét phiên bản.** Trong Spring Framework 6.1, các cờ executor có tương tác về early shutdown, coordinated lifecycle stop và destruction phase; cần test đúng dependency versions.

**25. In “graceful shutdown success” dù quá deadline.** Cần phân biệt executor terminated, task completed, business state committed và message acked; không đồng nhất các tín hiệu.

## 19. Bài thực hành

1. Tại sao phải đóng admission **trước** khi chờ các task đang chạy? Điều gì xảy ra nếu các producer còn được phép submit?
2. So sánh `shutdown()` và `shutdownNow()` trên một executor có một running task và hai queued tasks.
3. Vì sao `awaitTermination(10, SECONDS)` có thể trả `false` ngay cả khi bạn đã gọi `shutdown()`?
4. Với một endpoint trả 202 rồi tạo background job, tại sao `server.shutdown=graceful` **không đủ** để bảo đảm job hoàn tất?
5. Chạy project mục 9 và giải thích từng dòng output. Các latch đã loại bỏ race của log như thế nào?
6. Thử nộp task mới **trước** khi `admissionClosed` được signaled. Nó có thể được chấp nhận không? Vì sao đây là kết quả phù hợp?
7. Tại sao code `if (accepting.get()) executor.execute(task)` vẫn có race dù `accepting` là `AtomicBoolean`?
8. Xóa lời gọi `work.allowTaskToFinish()` trong demo. Khi quá deadline, sự kiện nào xuất hiện? Task đã hoàn thành nghiệp vụ chưa?
9. Thay `shutdown()` bằng `shutdownNow()` trong demo và ghi nhận nhánh `InterruptedException` của worker.
10. Viết một counter `inFlight` để theo dõi số task đã accepted nhưng chưa hoàn tất. Bạn phải cập nhật counter khi reject/exception như thế nào?
11. Đổi từ `ExecutorService` tự tạo sang `ThreadPoolTaskExecutor`; bật `setWaitForTasksToCompleteOnShutdown(true)` và `setAwaitTerminationSeconds(20)`. Vì sao vẫn cần admission gate?
12. Trong Spring Framework 6.1, tại sao không nên tự bật cả `strictEarlyShutdown` và `waitForTasksToCompleteOnShutdown` rồi đoán rằng mọi task sẽ được xử lý “strictly graceful”?
13. Tạo một `SmartLifecycle` producer và một `SmartLifecycle` worker. Chọn phase/depends-on để producer dừng trước worker.
14. Một worker cần database connection để commit. Làm thế nào để bảo đảm bean DB client vẫn sống trong drain?
15. Dùng `ContextClosedEvent` để đóng admission ở đầu quá trình close. Vì sao đây chỉ là một phần của toàn bộ shutdown protocol?
16. Một consumer ack message **trước** khi xử lý xong; nếu SIGKILL xảy ra, kết quả có thể ra sao?
17. Nếu side effect thành công nhưng chưa ack, broker redeliver. Bạn sẽ dùng idempotency key/unique constraint/outbox như thế nào?
18. Khi pod có `terminationGracePeriodSeconds=30` và preStop mất 10 giây, vì sao không nên đặt một drain wait 30 giây mà không có buffer?
19. Một tác vụ không phản hồi interrupt vì network I/O bị kẹt. Có nên khẳng định `shutdownNow()` đã stop nó không? Bạn cần timeout phía client và cancellation policy nào?
20. Viết một integration test với `CountDownLatch` để chứng minh task accepted trước close hoàn tất, còn task submit sau gate close bị từ chối.
21. Đặt metric đo `shutdown.drain.duration` và số jobs rejected trong lúc terminating; những dấu hiệu nào cho thấy grace budget không đủ?
22. Với công việc kéo dài nhiều giờ, tại sao checkpoint và resume thường tốt hơn việc đợi toàn bộ job trong một pod?
23. Giải thích khác biệt giữa executor terminated, job callback returned, database commit succeeded và message broker ack succeeded.
24. Trong ứng dụng WebFlux có streaming response, bạn sẽ quyết định thời điểm close stream và cơ chế resume ra sao?
25. Nếu IDE không gửi tín hiệu dừng tương đương SIGTERM, cách nào kiểm tra graceful shutdown gần điều kiện triển khai thật hơn?

## Ghi nhớ

- **Quy tắc cốt lõi:** ngừng nhận việc mới → để task đã nhận hoàn tất trong deadline → dọn tài nguyên sau cùng.
- `ExecutorService.shutdown()` từ chối task mới nhưng **không tự đợi** task cũ hoàn thành; `awaitTermination(...)` là bước chờ với timeout.
- `shutdownNow()` là nhánh ép dừng/cancellation, không bảo đảm interrupt thành công hoặc công việc đã được commit.
- Admission gate cần chống race giữa kiểm tra trạng thái và nộp job, đồng thời xử lý tình huống executor reject.
- `SmartLifecycle.stop(Runnable)` giúp phối hợp vòng đời; chỉ thông báo callback sau khi component thật sự dừng theo hợp đồng.
- Trong Spring Boot **3.3**, cấu hình `server.shutdown=graceful` cho HTTP graceful shutdown và `spring.lifecycle.timeout-per-shutdown-phase` cho thời gian chờ mỗi phase; điều này **không tự drain executor hoặc consumer tùy biến**.
- Với `ThreadPoolTaskExecutor`, `setWaitForTasksToCompleteOnShutdown(true)` và `setAwaitTerminationSeconds(...)` có thể hỗ trợ chờ queued/running jobs trong destruction, nhưng không thay thế việc ngừng producer.
- Graceful shutdown **không thay thế** durable queue, checkpoint, retry, idempotency, transaction và đúng thứ tự ack/commit.
- Không có Java callback nào được bảo đảm chạy khi tiến trình nhận SIGKILL hoặc host chết; phải thiết kế phục hồi cho trường hợp shutdown không graceful.
- Test shutdown bằng latch/future và các invariant bắt buộc, tránh `Thread.sleep` rồi kết luận từ log ngẫu nhiên.

### Tài liệu tham khảo

- Spring Boot 3.3 — Graceful Shutdown: https://docs.spring.io/spring-boot/3.3/reference/web/graceful-shutdown.html
- Spring Boot 3.3 — Application Availability: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Framework 6.1 — `SmartLifecycle`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/SmartLifecycle.html
- Spring Framework 6.1 — `DefaultLifecycleProcessor`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/support/DefaultLifecycleProcessor.html
- Spring Framework 6.1 — `ThreadPoolTaskExecutor`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html
- Spring Framework 6.1 — `ExecutorConfigurationSupport`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/scheduling/concurrent/ExecutorConfigurationSupport.html
- Java SE 17 — `ExecutorService`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html
- Java SE 17 — `CountDownLatch`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html
