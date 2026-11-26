# Executor cho listener trong Spring Modulith

## 1. Executor quyết định cách listener bất đồng bộ được thực thi

Trong kiến trúc module, event giúp module phát không cần gọi trực tiếp mọi module nhận. Ví dụ, Orders xác nhận thanh toán rồi phát sự kiện `OrderPaid`. Notifications nghe event để tạo yêu cầu gửi email; Loyalty nghe cùng event để tính điểm. Cả hai công việc có thể thực hiện **sau khi transaction thanh toán đã commit**, và không nhất thiết phải chặn request thanh toán.

Spring Modulith cung cấp `@ApplicationModuleListener` để biểu diễn cách giao tiếp đó. Annotation này kết hợp **`@Async`**, **`@TransactionalEventListener`** và **`@Transactional(propagation = REQUIRES_NEW)`**. Nhưng để thực sự xử lý bất đồng bộ an toàn, ứng dụng vẫn cần quan tâm đến **executor**: thành phần nhận tác vụ, xếp hàng, cấp thread và xử lý khi tải vượt khả năng.

Executor không quyết định ý nghĩa event. `OrderPaid` vẫn là sự thật “đơn đã thanh toán” theo quy tắc của Orders. Executor chỉ quyết định **khi nào và trên tài nguyên nào** logic của listener được chạy. Vì vậy, lựa chọn executor tác động đến throughput, latency, tài nguyên database, lỗi khi quá tải và khả năng khôi phục sau sự cố.

Bài này thuộc phần **Đồng bộ và bất đồng bộ** của `SPRING_MODULITH_APPLICATION_EVENTS`, tập trung vào cấu hình executor dành cho event listener, lựa chọn giữa đồng bộ/bất đồng bộ, ranh giới transaction, xử lý lỗi và cách kiểm thử.

### Kết quả học tập

Sau bài này, bạn có thể:

- Giải thích sự khác nhau giữa synchronous listener, after-commit listener và asynchronous listener.
- Xác định executor mà `@Async` sử dụng và bật asynchronous method execution bằng `@EnableAsync`.
- Cấu hình `ThreadPoolTaskExecutor` riêng với số thread, hàng đợi và chính sách từ chối.
- Dùng executor được đặt tên cho một listener mà vẫn bảo toàn semantics sau commit và transaction mới.
- Chọn kích thước pool phù hợp đặc tính CPU, I/O, giới hạn DB và tải sự kiện.
- Thiết kế backpressure, shutdown, retry, idempotency và theo dõi publication chưa hoàn thành.
- Kiểm thử rằng listener chạy sau commit và hoàn tất độc lập mà không dựa trên `Thread.sleep` cố định.

## 2. Tách ba quyết định: thời điểm, thread và transaction

Ba câu hỏi phải trả lời **riêng** khi cấu hình listener:

| Câu hỏi | Quyết định | Cơ chế thường gặp |
| --- | --- | --- |
| **Khi nào xử lý?** | Ngay lúc publish hay sau khi transaction nguồn commit? | `@EventListener`, `@TransactionalEventListener` |
| **Chạy ở đâu?** | Trên thread gọi publisher hay executor thread? | `@Async`, `@EnableAsync`, `TaskExecutor` |
| **Ghi dữ liệu trong transaction nào?** | Có dùng transaction mới dành cho consumer không? | `@Transactional(propagation = REQUIRES_NEW)` |

Không nên suy luận “`@TransactionalEventListener` chắc chắn async”: annotation này mặc định lắng nghe ở phase `AFTER_COMMIT` nhưng **không tự chuyển sang thread khác**. Ngược lại, `@Async` không tự chờ commit. Nếu đặt `@Async` lên một `@EventListener` thông thường, tác vụ có thể được gửi sang executor **trước khi transaction publisher commit**, dẫn tới đọc trạng thái chưa được xác nhận hoặc thậm chí thực hiện side effect cho một transaction sau đó rollback.

~~~mermaid
flowchart LR
    A["Publisher cập nhật Order"] --> B["publish OrderPaid"]
    B --> C["TX Orders COMMIT"]
    C --> D["AFTER_COMMIT callback"]
    D --> E["Executor nhận task"]
    E --> F["Listener xử lý trong TX mới"]
~~~

Sơ đồ trên thể hiện cấu hình được khuyến nghị cho các side effect liên module có thể xử lý độc lập. Với `@EventListener` đồng bộ, listener thường chạy ngay lúc publish; với `@TransactionalEventListener` không async, callback chạy sau commit nhưng vẫn trên thread xử lý transaction nguồn.

## 3. So sánh ba mẫu listener

### 3.1. Listener đồng bộ thông thường

~~~java
@Component
public class AuditListener {

    @EventListener
    public void on(OrderPaid event) {
        auditService.record(event);
    }
}
~~~

Với Spring `SimpleApplicationEventMulticaster` mặc định không có executor riêng, listener thông thường chạy đồng bộ trong luồng phát event. Caller phải chờ nó kết thúc; exception có thể truyền ngược tới publisher. Nếu phương thức publisher đang trong transaction, listener có thể được gọi trước commit.

Mẫu này có thể hợp lý cho logic ngắn, chủ động cần chạy trong ngữ cảnh hiện tại. Nó không nên là lựa chọn mặc định cho email, HTTP API hay công việc dài mà chỉ có ý nghĩa sau commit.

### 3.2. Listener sau commit nhưng đồng bộ

~~~java
@Component
public class AccountingListener {

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void on(OrderPaid event) {
        accountingService.onPaid(event);
    }
}
~~~

Phần xử lý được trì hoãn tới sau commit của transaction đã publish event. Nếu không dùng `@Async`, nó không có nghĩa tách sang executor thread. Ngoài ra, **AFTER_COMMIT không tự mở transaction ghi mới**: muốn consumer ghi state độc lập nên chủ động dùng transaction mới phù hợp.

### 3.3. Listener sau commit, async và transaction riêng

~~~java
@Component
public class LoyaltyListener {

    @ApplicationModuleListener
    public void on(OrderPaid event) {
        loyaltyService.creditIfAbsent(event.eventId(), event.orderId());
    }
}
~~~

`@ApplicationModuleListener` trong Spring Modulith là shortcut cho kiểu listener nhận event sau commit, xử lý async trong transaction mới. Khi Spring async infrastructure được bật, task được giao cho executor theo cấu hình `@Async`.

**Chú ý:** bản thân event vẫn được phát từ ứng dụng Spring; annotation không tạo message broker, queue bền vững hay bảo đảm exactly-once end-to-end.

## 4. Bật xử lý @Async bằng @EnableAsync

Một cấu hình cơ bản có thể khai báo:

~~~java
package com.acme.shop.config;

import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;

@Configuration
@EnableAsync
public class AsyncConfiguration {
}
~~~

`@EnableAsync` bật cơ chế Spring xử lý method được đánh dấu `@Async`. Trong ứng dụng dùng proxy-based AOP (mặc định thông thường), lời gọi qua Spring proxy mới được interceptor chuyển sang executor. Việc tự gọi phương thức async qua `this.on(...)` trong cùng bean hoặc tạo instance bằng `new` sẽ không đi qua proxy và có thể chạy đồng bộ.

Đừng giả định chỉ vì class có `@Async` hoặc `@ApplicationModuleListener` mà executor đã chạy đúng như mong muốn. Cần kiểm tra:

1. Bean listener được Spring quản lý và được phát hiện trong `ApplicationContext`.
2. Asynchronous method execution đã được bật trong cấu hình phù hợp.
3. Method listener có thể được AOP proxy/interceptor áp dụng theo phiên bản Spring và cách dùng.
4. Executor mục tiêu tồn tại và có tài nguyên xử lý.
5. Transactional event được phát khi có transaction phù hợp và transaction thực sự commit.

Nếu không có transaction lúc publish, `@TransactionalEventListener` mặc định không xử lý event, trừ khi bật `fallbackExecution` một cách chủ đích. Đó là vấn đề **transaction phase**, không phải vấn đề executor.

## 5. Spring chọn executor nào cho @Async?

Khi method `@Async` không chỉ rõ tên executor, Spring dùng cơ chế lựa chọn executor mặc định của asynchronous method execution. Một số nguồn cấu hình có thể ảnh hưởng:

- `AsyncConfigurer#getAsyncExecutor()` khi ứng dụng định nghĩa AsyncConfigurer.
- Bean `TaskExecutor` phù hợp hoặc bean executor theo tên/quy tắc mà Spring áp dụng.
- Spring Boot có thể auto-configure `AsyncTaskExecutor` cho ứng dụng nếu điều kiện auto-configuration được thỏa.
- Nếu không có executor phù hợp, cơ chế fallback tùy cấu hình và phiên bản Spring có thể dùng executor đơn giản, không phải pool bị giới hạn theo kỳ vọng.

**Không nên dựa vào tên bean mặc định bằng phỏng đoán.** Spring Boot có thể cung cấp bean `applicationTaskExecutor` và lựa chọn executor có thể thay đổi khi ứng dụng tự khai báo `Executor`, `TaskExecutor` hoặc `AsyncConfigurer`. Nếu có nhiều executor, nên xác định rõ executor nào chạy event listener để tránh tranh chấp với task web, scheduled jobs hoặc tác vụ async khác.

Spring cho phép chỉ định executor theo tên qua `@Async("moduleEventsExecutor")`. Đây là cách dễ đọc và kiểm chứng nhất khi cần **pool riêng** cho một loại listener.

### Kiểm tra cấu hình hiện tại

Với Spring Boot, có thể xem các bean `Executor`/`TaskExecutor` đang tồn tại trong context và kiểm tra cấu hình `@EnableAsync`. Để khẳng định method chạy trên executor mong muốn, có thể đặt `threadNamePrefix` đặc trưng, sau đó quan sát thread name trong log/test và metric của executor.

Không nên thiết kế toàn bộ chương trình dựa vào `Thread.currentThread().getName()`; tên thread chỉ là tín hiệu quan sát, không phải hợp đồng bảo đảm thứ tự hay transaction.

## 6. Cấu hình một ThreadPoolTaskExecutor chuyên cho listener

Một cấu hình mẫu:

~~~java
package com.acme.shop.config;

import java.util.concurrent.ThreadPoolExecutor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableAsync
public class EventExecutorConfiguration {

    @Bean(name = "moduleEventsExecutor")
    public ThreadPoolTaskExecutor moduleEventsExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();

        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(200);
        executor.setKeepAliveSeconds(60);
        executor.setThreadNamePrefix("module-events-");
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy()
        );
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(30);

        return executor; // Spring quản lý khởi tạo và shutdown bean.
    }
}
~~~

Các giá trị `4`, `8`, `200` và `30` **chỉ là ví dụ để thảo luận**, không phải cấu hình chuẩn cho mọi ứng dụng.

| Thuộc tính | Ý nghĩa | Đánh đổi |
| --- | --- | --- |
| `corePoolSize` | Số worker core được duy trì theo quy tắc của pool | Quá thấp làm tăng thời gian chờ; quá cao tốn thread và tài nguyên |
| `maxPoolSize` | Giới hạn worker khi pool cần mở rộng | Quá cao có thể gây áp lực CPU/DB và hệ thống ngoài |
| `queueCapacity` | Số task có thể chờ trong hàng đợi | Quá lớn làm che giấu backlog và giữ nhiều object trong RAM |
| `keepAliveSeconds` | Thời gian giữ worker dư thừa | Ảnh hưởng khả năng thu hẹp pool sau đợt tải |
| `threadNamePrefix` | Nhận diện thread trong log/trace | Chỉ hỗ trợ quan sát, không quyết định tính đúng nghiệp vụ |
| `RejectedExecutionHandler` | Quy định khi pool/queue đầy | Có thể từ chối, chạy tại caller hoặc loại task; chọn sai dễ làm mất tin |
| `waitForTasksToCompleteOnShutdown` | Quyết định cách xử lý task đã nhận khi bean shutdown | Chờ quá lâu làm kéo dài shutdown; dừng sớm cần cơ chế khôi phục |
| `awaitTerminationSeconds` | Giới hạn thời gian shutdown chờ executor kết thúc | Phải cân bằng graceful shutdown với deadline của hạ tầng deploy |

Ở `ThreadPoolTaskExecutor`, một chi tiết quan trọng là **pool thường ưu tiên xếp task vào queue sau khi đã dùng core threads; chỉ tăng số worker vượt core khi queue đạt ngưỡng**. Do đó, thiết lập `maxPoolSize=64` cùng queue rất lớn không có nghĩa lúc nhiều event pool sẽ ngay lập tức chạy 64 task. Muốn thiết kế đúng phải hiểu cả **core + queue + max**.

## 7. Gắn listener với executor riêng mà vẫn giữ after-commit

Khi cần sử dụng **executor được đặt tên**, có thể khai báo tường minh bộ ba annotation thay cho shortcut:

~~~java
package com.acme.shop.notifications.internal;

import com.acme.shop.orders.OrderPaid;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
public class OrderPaidNotificationListener {

    private final NotificationService notifications;

    public OrderPaidNotificationListener(NotificationService notifications) {
        this.notifications = notifications;
    }

    @Async("moduleEventsExecutor")
    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void on(OrderPaid event) {
        notifications.scheduleIfAbsent(
                event.eventId(),
                event.orderId()
        );
    }
}
~~~

Đoạn code giả định `OrderPaid` là event contract công khai và `NotificationService.scheduleIfAbsent` được triển khai idempotent. Class/method public giúp cấu hình proxy/AOP minh bạch khi dùng `@Async` và `@Transactional`.

Để so sánh:

~~~java
// Sử dụng executor mặc định được chọn cho @Async:
@ApplicationModuleListener
public void on(OrderPaid event) {
    notifications.scheduleIfAbsent(event.eventId(), event.orderId());
}
~~~

`@ApplicationModuleListener` là shortcut có `@Async` không khai báo qualifier executor trong API của annotation. Nếu cần executor khác riêng cho method, lựa chọn rõ ràng là **khai báo tường minh `@Async("moduleEventsExecutor")` cùng transactional listener/transaction mới** như ví dụ trước, thay vì giả định shortcut tự có tham số tên executor.

Một lựa chọn khác là cấu hình `AsyncConfigurer#getAsyncExecutor()` để thay executor mặc định cho những phương thức `@Async` không ghi rõ tên. Tuy nhiên, đó là quyết định **toàn ứng dụng**: các tác vụ `@Async` khác cũng có thể bị ảnh hưởng.

### Không tùy tiện đặt @Async lên event publisher

~~~java
// Tránh biến đổi ngữ nghĩa chỉ để "trông có vẻ async".
@Async("moduleEventsExecutor")
@Transactional
public void confirmOrder(UUID orderId) {
    // Giao dịch Orders chạy tại một luồng khác.
}
~~~

Khi chuyển cả **publisher use case** sang executor, thời điểm trả kết quả và transaction của nghiệp vụ gốc thay đổi. Nếu mục tiêu chỉ là đưa công việc Notifications sang background sau khi đơn đã được commit, hãy áp dụng async ở **listener** đúng phase, không dời cả nghiệp vụ chính một cách vô thức.

## 8. Sizing executor theo workload, không theo số event tùy ý

Không có một cỡ thread pool cố định phù hợp mọi event listener. Cần xác định loại công việc.

| Workload của listener | Đặc điểm | Hướng sizing |
| --- | --- | --- |
| CPU-bound, ví dụ tính toán báo cáo nặng | Worker liên tục dùng CPU | Số thread gần năng lực CPU; đo CPU saturation |
| DB-bound, ví dụ ghi notification job | Chờ database, tiêu thụ connection | Giới hạn cạnh tranh theo pool connection và khả năng DB |
| HTTP/I/O-bound, ví dụ gọi API ngoài | Chờ network nhiều | Có thể cần đồng thời cao hơn, nhưng tôn trọng rate limit |
| Nhiều việc ngắn | Tần suất cao, latency thấp | Đo chi phí scheduling và queue wait |
| Công việc vài phút | Giữ worker lâu, tăng backlog | Cân nhắc durable job/queue hoặc chia việc thành bước nhỏ |

Có thể ước lượng sơ bộ số tác vụ đồng thời bằng công thức:

\[
\text{Concurrent tasks} \approx \text{arrival rate (events/s)} \times \text{average processing time (s)}
\]

Ví dụ, nếu 50 event/giây và mỗi event mất trung bình 0,2 giây, mức đồng thời trung bình cần khoảng 10 task, **trước khi tính peak, retry và độ biến thiên latency**. Đây là một ước lượng tải, không phải công thức trực tiếp để đặt `maxPoolSize`.

Bên cạnh đó phải giới hạn theo tài nguyên phụ thuộc: executor 50 threads không giúp ích nếu database chỉ có 10 connections khả dụng và mỗi task cần giữ một connection. Quá nhiều concurrency có thể làm độ trễ và số timeout tăng, dẫn đến retry và tạo vòng lặp quá tải.

### 8.1. Shared executor hay dedicated executor?

Một pool dùng chung rất tiện khi số tác vụ nhỏ và tải ổn định. Tuy nhiên, nếu Notifications có một loạt request chậm, chúng có thể chiếm hết pool khiến listener của Inventory hoặc Loyalty không được xử lý kịp.

Cân nhắc tách executor khi:

- Các nhóm listener có SLA hoặc mức ưu tiên khác nhau.
- Một consumer thường gọi API ngoài chậm, trong khi consumer khác chủ yếu ghi DB.
- Muốn áp dụng giới hạn concurrency/backpressure theo từng nghiệp vụ.
- Cần cô lập lỗi quá tải và quan sát metrics riêng.

Đổi lại, nhiều pool làm tăng số thread tổng và chi phí vận hành. Nên tính **tổng concurrency trên tất cả pool**, không chỉ xem từng pool một cách độc lập.

## 9. Queue và backpressure khi sự kiện đến nhanh hơn khả năng xử lý

Giả sử publisher tạo 1.000 `OrderPaid` trong vài giây, trong khi Notifications xử lý được 100 event/giây. Executor sẽ hình thành backlog.

~~~mermaid
flowchart LR
    P["Publisher / commit"] --> Q["Bounded executor queue"]
    Q --> W1["Worker 1"]
    Q --> W2["Worker 2"]
    Q --> W3["Worker N"]
    W1 --> DB[("Notifications DB")]
    W2 --> DB
    W3 --> DB
~~~

Queue lớn giúp hấp thụ burst ngắn, nhưng có thể trì hoãn sự kiện rất lâu. Queue vô hạn giữ nhiều event object trong RAM và che giấu vấn đề đến lúc tràn bộ nhớ. Queue nhỏ buộc hệ thống xử lý tình huống **rejection** sớm hơn.

### 9.1. Chính sách khi pool đầy

| Chính sách | Hành vi | Rủi ro với event listener |
| --- | --- | --- |
| `AbortPolicy` | Từ chối task bằng exception | Cần quan sát và cơ chế khôi phục publication; không được coi listener đã thành công |
| `CallerRunsPolicy` | Nếu không shutdown, chạy task trên thread gọi submit | “Bất đồng bộ” có thể biến thành chạy tại thread publisher/after-commit và làm tăng latency |
| `DiscardPolicy` | Bỏ task bị từ chối mà không ném exception | Rất nguy hiểm cho nghiệp vụ vì dễ gây mất tác vụ âm thầm |
| `DiscardOldestPolicy` | Bỏ task cũ nhất rồi thử submit task mới | Có thể làm mất công việc đã được lên lịch mà thiếu tín hiệu rõ |
| Handler tùy chỉnh | Có thể ghi metrics, throttle, từ chối có kiểm soát | Phải thiết kế kỹ cách retry/khôi phục và không block vô hạn |

Với luồng event có yêu cầu tin cậy, nên ưu tiên **phát hiện được quá tải**, có cơ chế ghi publication bền vững và khôi phục/retry rõ ràng, thay vì im lặng bỏ task. `AbortPolicy` là một lựa chọn để lỗi được nhìn thấy, nhưng **bản thân rejection exception không bảo đảm event tự được gửi lại**; cần kiểm tra cơ chế publication registry và resubmission được cấu hình.

### 9.2. Backpressure cần một điểm lưu bền

Một executor queue trong RAM **không phải durable queue**: khi JVM dừng, các task còn chờ trong RAM có thể mất. Nếu hệ thống cần bảo đảm không bỏ sự kiện sau commit, phải cấu hình publication registry/outbox/queue bền vững phù hợp rồi xác định cách tái giao các publication chưa hoàn thành.

Trong cấu hình Spring Modulith, **Event Publication Registry** có thể lưu publication cho transactional listeners và hỗ trợ theo dõi, khôi phục khi listener không hoàn thành. Việc registry được bật không tự thiết lập lịch retry vô hạn, retry backoff hay quyền xử lý đúng một lần ở consumer.

## 10. Transaction thực sự nằm ở đâu?

Một workflow được khuyến nghị:

~~~mermaid
sequenceDiagram
    autonumber
    actor Client
    participant O as Orders
    participant DB as Orders DB
    participant R as Registry
    participant E as Async Executor
    participant N as Notifications
    Client->>O: confirmPayment(orderId)
    O->>DB: Update Order = PAID trong TX Orders
    O->>R: publish OrderPaid / ghi publication nếu được cấu hình
    O->>DB: COMMIT
    R-->>E: AFTER_COMMIT - submit task
    E-->>N: on(OrderPaid) trên worker thread
    N->>N: Transaction REQUIRES_NEW
    N->>N: Commit notification job
    N-->>R: Publication completed theo cơ chế registry
~~~

Các trường hợp cần phân biệt:

- **Publisher rollback:** listener `AFTER_COMMIT` không xử lý như một thay đổi đã commit.
- **Publisher commit rồi listener lỗi:** transaction Orders vẫn thành công; transaction của listener có thể rollback riêng.
- **Publisher commit, executor chưa chạy:** Orders đã có state mới nhưng Notifications có thể chưa tạo state, tức eventual consistency.
- **Listener hoàn tất rồi hệ thống lỗi trước khi ghi completion:** cùng event có thể được giao lại; consumer phải idempotent.
- **Executor từ chối ngay lúc submit:** xử lý lỗi và publication recovery là cần thiết; không được suy đoán rằng task đã được queue.

`REQUIRES_NEW` nghĩa là một transaction mới của consumer khi method được chặn qua transactional infrastructure; nó không có nghĩa listener được bảo đảm ghi vào một database khác hay có transaction phân tán với publisher.

### Không giữ transaction của publisher trên worker

Thread-local transaction context của Spring không tự được truyền sang một worker `@Async`. Đó là lý do consumer phải có transaction của chính nó khi thực hiện thao tác ghi. Không nên truyền `EntityManager`, entity JPA lazy proxy hoặc JDBC connection của publisher vào event để dùng trên thread khác.

Event nên mang các giá trị bất biến như `eventId`, `orderId`, `occurredAt` và snapshot nghiệp vụ cần thiết.

## 11. Xử lý lỗi của listener và Event Publication Registry

Khi một method `@Async` trả về `void` và ném exception, caller ban đầu thường không nhận exception đó như một kết quả đồng bộ. Spring có cơ chế `AsyncUncaughtExceptionHandler` để ghi nhận hoặc xử lý ngoại lệ từ các method async kiểu void. Nhưng **log exception không đủ** để bảo đảm publication được thử lại.

Trong Spring Modulith, kết hợp các transactional event listener với **Event Publication Registry** thích hợp giúp theo dõi publication chưa hoàn thành. Cần triển khai backend lưu publication, lựa chọn cơ chế resubmission/republication và chính sách vận hành theo **phiên bản thư viện thực tế**.

Một ví dụ idempotent ở module Notifications:

~~~java
@Service
public class NotificationService {

    private final NotificationJobRepository jobs;

    public NotificationService(NotificationJobRepository jobs) {
        this.jobs = jobs;
    }

    public void scheduleIfAbsent(UUID eventId, UUID orderId) {
        // Pseudocode nghiệp vụ: dựa vào unique constraint ở DB.
        if (jobs.existsBySourceEventId(eventId)) {
            return;
        }

        jobs.save(NotificationJob.forOrderPaid(eventId, orderId));
    }
}
~~~

Đây là ví dụ mô tả API; cần triển khai `NotificationJob` và `NotificationJobRepository`. **Chỉ kiểm tra exists-then-insert trong Java không đủ chống race**: hãy tạo unique constraint cho `source_event_id` hoặc business key thích hợp, và xử lý unique violation theo quy tắc. Ghi dấu event đã xử lý và thay đổi state phải thuộc transaction consumer.

### Tại sao cần idempotency dù pool chỉ có một thread?

Đặt `corePoolSize=1` không ngăn event bị giao lại sau khi ứng dụng restart, và cũng không ngăn hai JVM cùng xử lý một business key qua tuyến khác. Điều kiện “đã xử lý” phải bền vững ngoài RAM; giữ `Set<UUID>` trong singleton listener chỉ là bộ nhớ cục bộ và mất khi restart.

Với side effect như gửi email hoặc gọi API giao hàng, database transaction cũng không thể hoàn tác tác vụ đã xảy ra ở bên ngoài. Cần durable job/outbox, idempotency key được phía đối tác hỗ trợ hoặc quy trình đối soát và bù trừ phù hợp.

## 12. TaskDecorator, logging và truyền context

Khi chuyển sang executor thread, một số giá trị thường nằm ở `ThreadLocal` của request thread **không tự được truyền**. Ví dụ:

- Log MDC, correlation ID.
- Micrometer observation/tracing context.
- Security context hoặc tenant context được giữ trong thread local.
- Request attributes liên quan HTTP.

Việc mất context thường làm log khó truy vết hoặc tạo lỗi khi listener dựa vào dữ liệu của request hiện tại.

Spring hỗ trợ `TaskDecorator` trên `ThreadPoolTaskExecutor` để bọc task và chuyển **một tập context được lựa chọn** sang thread xử lý. Nếu ứng dụng dùng Micrometer Context Propagation, có thể xem xét `ContextPropagatingTaskDecorator` theo dependency và phiên bản Spring phù hợp.

**Phân biệt hai loại dữ liệu:**

| Dữ liệu | Cách xử lý phù hợp |
| --- | --- |
| `eventId`, `orderId`, metadata nghiệp vụ cần bền vững | Đưa vào event contract hoặc lưu theo publication |
| Trace/correlation cần quan sát | Context propagation/decorator phù hợp |
| HTTP request object, JPA session, database transaction | Không chuyển để sử dụng trong listener async |
| Access token/session secret | Không đưa vào event; xác định quyền và danh tính theo chính sách bảo mật |
| Tenant/business identity cần cho xử lý lâu dài | Biểu diễn rõ bằng dữ liệu được phép lưu, không chỉ dựa vào ThreadLocal |

Lưu ý: một event có thể được xử lý lại **sau khi ứng dụng restart**. Khi đó thread context của request gốc không còn tồn tại, dù lúc đầu đã có TaskDecorator. Thông tin quan trọng để xử lý lại phải được lưu bền trong event/record tương ứng.

## 13. Virtual threads có thay thế ThreadPoolTaskExecutor không?

Với Java 21+ và cấu hình Spring Boot phù hợp, ứng dụng có thể dùng virtual threads cho một số tác vụ bất đồng bộ; Spring Boot có cấu hình `spring.threads.virtual.enabled=true` khi môi trường hỗ trợ.

Virtual threads giúp giảm chi phí của nhiều luồng chờ I/O trong những trường hợp phù hợp. Tuy nhiên:

- Chúng **không tăng số database connection** và không vượt qua rate limit của API ngoài.
- Hàng nghìn tác vụ đồng thời vẫn có thể quá tải service phụ thuộc.
- Không tự bảo đảm publication bền vững, ordering, transaction hay retry.
- Các thư viện blocking, sử dụng `synchronized` hoặc tài nguyên native có thể ảnh hưởng hiệu năng; cần đo bằng workload thật.
- Cần có cơ chế giới hạn concurrency và backpressure ở lớp hợp lý, kể cả khi task chạy trên virtual thread.

Vì vậy, chọn platform-thread pool hay virtual-thread executor là **quyết định thực thi**, tách khỏi contract event và tính đúng nghiệp vụ. Không dùng virtual threads làm lý do bỏ queue metrics, timeouts hoặc idempotency.

## 14. Shutdown và restart: task đang chờ sẽ ra sao?

Khi rolling deploy hoặc server shutdown, executor có thể vẫn có task đang chờ hoặc đang chạy.

### 14.1. Graceful shutdown

`ThreadPoolTaskExecutor` có các tùy chọn để chờ task đang có hoàn tất khi đóng ứng dụng. Cần chọn thời gian chờ trong giới hạn shutdown của Kubernetes/systemd hoặc hạ tầng triển khai; nếu deadline của platform ngắn hơn thời gian listener cần, task vẫn có thể bị ngắt.

Không nên kéo shutdown vô hạn vì một HTTP call không có timeout. Mỗi listener cần timeout rõ cho kết nối DB/API, có thể kết hợp circuit breaker/rate limit tùy nhu cầu.

### 14.2. Khôi phục publication

Nếu process dừng bất ngờ, queue trong RAM sẽ mất. Khi dùng Event Publication Registry có backend lưu trữ phù hợp, những publication chưa hoàn thành có thể được phục hồi bằng cơ chế resubmission được cấu hình.

Để đánh giá đúng độ tin cậy, cần thử các điểm crash:

1. Sau commit Orders nhưng trước khi executor chạy.
2. Khi task còn nằm trong queue.
3. Khi listener đã bắt đầu transaction nhưng chưa commit.
4. Sau commit state của consumer nhưng trước khi publication được đánh dấu complete.

Trong mọi trường hợp, mục tiêu là state cuối cùng đúng, publication còn quan sát được và không nhân đôi side effect.

## 15. Kiểm thử executor và listener

Một bài test tốt cần chứng minh cả **wiring đúng** lẫn **semantics nghiệp vụ đúng**. Chỉ kiểm tra class có `@Async` là chưa đủ.

### 15.1. Kiểm thử wiring

Xác minh:

- Bean `moduleEventsExecutor` tồn tại đúng tên và kiểu.
- `@EnableAsync` được bật.
- Listener được Spring đăng ký một lần theo ý định.
- Phương thức listener dùng `@Async("moduleEventsExecutor")` nếu cần pool riêng.
- Thread name trong log/tracing đúng `module-events-` (chỉ hỗ trợ kiểm chứng wiring).

Nếu có hai bean có cùng chức năng listener được đăng ký tình cờ, cùng event có thể tạo hai tác vụ. Executor đúng không ngăn duplicate listener definitions.

### 15.2. Kiểm thử transaction sau commit

Ví dụ dạng integration test với `TransactionTemplate`, `ApplicationEventPublisher` và repository kết quả:

~~~java
@SpringBootTest
class OrderPaidListenerIntegrationTest {

    @Autowired TransactionTemplate transactions;
    @Autowired ApplicationEventPublisher publisher;
    @Autowired NotificationJobRepository jobs;

    @Test
    void listenerCreatesJobAfterCommit() {
        UUID eventId = UUID.randomUUID();
        UUID orderId = UUID.randomUUID();

        transactions.executeWithoutResult(tx -> {
            publisher.publishEvent(
                    new OrderPaid(eventId, orderId, Instant.now())
            );
        }); // Transaction đã commit sau khi callback kết thúc.

        await().atMost(Duration.ofSeconds(5)).untilAsserted(() ->
                assertThat(jobs.existsBySourceEventId(eventId)).isTrue()
        );
    }
}
~~~

Ví dụ giả định event `OrderPaid` đã được định nghĩa với constructor tương ứng, các import Spring/JUnit/Awaitility/AssertJ đã có và hạ tầng test tạo được transaction. Đây là **phác thảo test**; có thể cần điều chỉnh DTO, wiring và database theo project.

Dùng `await()` với timeout để chờ kết quả cuối. Đừng dùng `Thread.sleep(1000)` và mặc định listener luôn xử lý xong trong một giây. Tránh bọc toàn bộ test trong một transaction được rollback mặc định, vì listener `AFTER_COMMIT` có thể không chạy.

### 15.3. Kiểm thử quá tải và xử lý lỗi

| Kịch bản | Điều cần kiểm chứng |
| --- | --- |
| 10 event được phát trong transaction đã commit | Đủ công việc được xử lý, không mất job |
| Queue lấp đầy | Rejection được phát hiện, đo đạc và publication có cách khôi phục |
| Listener lỗi tạm thời | Transaction listener rollback, publication chưa hoàn thành có thể được xử lý lại |
| Hai event cùng business key | Unique constraint/idempotency bảo vệ state |
| Event bị giao lại sau restart | Không nhân đôi side effect |
| Executor shutdown khi task còn chờ | Không mất việc không thể khôi phục; chính sách shutdown đúng |
| Event đến sau một event có phiên bản mới hơn | Consumer không áp dụng trạng thái cũ sai thứ tự |
| Mất MDC/trace trên executor thread | Có propagation và log/correlation theo thiết kế |

Không phải lúc nào cũng cần viết test mô phỏng hàng nghìn event trong unit test; những kiểm tra throughput/backpressure nên chạy ở mức integration/load test với pool và database gần thực tế.

### 15.4. Spring Modulith test support

Spring Modulith có `@ApplicationModuleTest` và hỗ trợ kịch bản `Scenario` để kiểm tra publication và điều kiện bất đồng bộ. Với test chỉ dùng module slice, phải bảo đảm listener và bean executor dự kiến được bootstrap; nếu test cắt bỏ cấu hình cần thiết thì kết quả không phản ánh production.

Có thể kết hợp architecture verification:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleArchitectureTest {

    @Test
    void verifiesModuleBoundaries() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

Architecture test kiểm tra dependency được Spring Modulith hỗ trợ; nó **không thay thế** kiểm thử thread pool, transaction và retry.

## 16. Quan sát executor và publication

Để hiểu liệu async listener có đang đáp ứng nhu cầu, cần đo từ lúc event được phát tới khi consumer hoàn thành.

| Nhóm chỉ số | Giá trị nên quan sát | Ý nghĩa |
| --- | --- | --- |
| Executor | `activeThreads`, `poolSize`, `queueDepth` | Đang quá tải hay còn headroom |
| Thời gian | Queue wait, processing duration, end-to-end latency | Trễ xuất phát từ queue, DB hay API |
| Kết quả | Completed, failed, rejected task count | Phát hiện lỗi và quá tải |
| Publication registry | Pending/incomplete publications, oldest age, retries | Sự kiện nào chưa được consumer xử lý xong |
| Database / API | Connection wait, timeout, rate-limit errors | Executor có vượt khả năng dependency không |
| Truy vết | `eventId`, `eventType`, `orderId`, `listenerName` | Liên kết các lần xử lý và retry |

Micrometer/Actuator có thể cung cấp metrics cho executor và công việc async tùy cách instrument và phiên bản Spring Boot. Không nên giả định mọi metric đều có sẵn ở mọi cấu hình; cần xác minh endpoint metrics thực tế.

Ví dụ log có cấu trúc:

~~~text
event=OrderPaid eventId=E1 listener=NotificationListener thread=module-events-3 phase=STARTED
event=OrderPaid eventId=E1 listener=NotificationListener thread=module-events-3 phase=COMPLETED
event=OrderPaid eventId=E2 listener=LoyaltyListener thread=module-events-5 phase=FAILED reason=DB_TIMEOUT
~~~

Không log toàn bộ event chứa thông tin nhạy cảm. ID cần đủ để trace nhưng tránh lộ secret, token hoặc chi tiết thanh toán.

**Tín hiệu đáng báo động:** queueDepth liên tục tăng, oldest pending publication ngày càng già, tỷ lệ rejection tăng hoặc end-to-end latency vượt SLA. Tăng `maxPoolSize` chỉ là một biện pháp; nếu DB đã bão hòa, tăng số thread có thể làm lỗi nặng hơn.

## 17. Sai lầm phổ biến

| Sai lầm | Tác động | Cách sửa |
| --- | --- | --- |
| Nghĩ `@TransactionalEventListener` tự async | Callback vẫn có thể chiếm thread publisher sau commit | Bật async và chọn executor khi cần |
| Thêm `@Async` cho `@EventListener` mà không xét commit | Consumer chạy trước khi state nguồn commit | Dùng transactional listener `AFTER_COMMIT` |
| Không bật `@EnableAsync` | Async interceptor có thể không được kích hoạt | Kiểm tra configuration và proxy wiring |
| Dùng executor mặc định mà không biết nguồn | Các workload tranh chấp pool | Chọn tên executor và quan sát thực tế |
| Queue không giới hạn | Backlog lớn, tăng RAM, latency khó đo | Dùng bounded queue và backpressure |
| `CallerRunsPolicy` cho rằng luôn async | Task có thể chạy trong thread submit | Chọn rejection policy có chủ đích |
| `DiscardPolicy` với sự kiện nghiệp vụ | Có thể im lặng mất công việc | Dùng fail-visible + durable recovery |
| Tăng threads không xét DB pool | Timeout, deadlock/lock contention, retry storm | Đo dependency capacity rồi sizing |
| Giữ `EntityManager`/HTTP request trong event | Sai thread/lifecycle và context | Chuyển immutable business data |
| Dựa vào in-memory queue để đảm bảo độ bền | Mất task khi JVM crash | Publication registry/outbox phù hợp |
| Catch exception rồi không báo thất bại | Registry có thể đánh dấu complete sai | Để lỗi được ghi nhận hoặc cập nhật failure state đúng |
| Dùng singleton Set ID đã xử lý | Mất dedup sau restart, khác nhau giữa replicas | DB unique constraint/idempotency |
| Test kiểm tra state ngay sau publish | Flaky test do async chưa chạy | Chờ điều kiện cuối với timeout |

## 18. Bài tập thực hành

### Bài 1 — Chọn executor cho từng nhóm listener

Một hệ thống có ba listener:

- Notifications gọi API email, trung bình 150 ms, có rate limit.
- Reporting tính toán CPU khoảng 20 ms/event.
- Inventory ghi DB khoảng 50 ms/event, database có giới hạn connection.

Hãy quyết định dùng chung hay tách pool, chọn giới hạn concurrency ban đầu và những metric phải quan sát trước khi điều chỉnh.

### Bài 2 — Phân tích code sai thời điểm

~~~java
@Async("moduleEventsExecutor")
@EventListener
public void on(OrderPaid event) {
    emailClient.sendPaidEmail(event.orderId());
}
~~~

Giải thích vì sao listener có thể gửi email khi transaction publisher chưa commit và đề xuất tổ hợp annotation phù hợp để chạy **sau commit** trong transaction riêng.

### Bài 3 — Mô phỏng rejection

Cấu hình pool 1 core thread, tối đa 2 threads, queue 2 và `AbortPolicy`. Publish một loạt event mà listener chờ I/O. Quan sát thời điểm queue đầy, task bị reject và cách publication recovery hoạt động trong cấu hình thực tế. Thử thay `CallerRunsPolicy` và so sánh latency của request publisher.

### Bài 4 — Xử lý duplicate

Tạo tình huống listener đã commit job nhưng ứng dụng crash trước khi publication hoàn thành. Sau restart, publication được giao lại. Thiết kế bảng chứa `source_event_id` duy nhất và kiểm thử chỉ có một job.

### Bài 5 — Theo dõi thread và tracing

Gắn `threadNamePrefix="module-events-"` và correlation ID vào log. Dùng `TaskDecorator` hoặc cơ chế context propagation phù hợp để trace xuyên thread. Kiểm chứng rằng một publication retry sau restart vẫn có event ID cần thiết ngay cả khi request thread cũ không còn.

## 19. Checklist đưa executor listener vào production

- [ ] Đã phân biệt rõ listener chạy đồng bộ, sau commit và trên executor thread.
- [ ] `@EnableAsync` và Spring proxy/interceptor đang hoạt động đúng.
- [ ] Đã xác định executor thực tế của từng listener, không phụ thuộc vào phỏng đoán về tên mặc định.
- [ ] Pool và queue được sizing theo throughput, latency, DB connection và API rate limit.
- [ ] Rejection policy được chọn có chủ đích, không im lặng bỏ business task.
- [ ] Có giới hạn queue và backpressure phù hợp, tránh backlog vô hạn trong RAM.
- [ ] Listener cần ghi state được chạy trong transaction riêng sau commit.
- [ ] Có backend publication registry/outbox phù hợp và cơ chế retry/republication sau sự cố.
- [ ] Listener idempotent khi nhận cùng event nhiều lần.
- [ ] Không truyền entity JPA, transaction, request/session object sang async thread.
- [ ] Có chính sách context propagation cho log/trace và metadata nghiệp vụ bền vững.
- [ ] Đã kiểm thử rollback, overload, rejection, restart và duplicate delivery.
- [ ] Có shutdown timeout, metric executor và cảnh báo publication backlog.

## 20. Ghi nhớ

**Executor là tài nguyên thực thi listener, không phải nơi bảo đảm độ bền của event.** Trong Spring Modulith, `@ApplicationModuleListener` giúp module nhận làm việc sau commit, bất đồng bộ và trong transaction mới. Khi cần một executor dành riêng cho loại listener nào đó, có thể dùng `@Async("moduleEventsExecutor")` kết hợp `@TransactionalEventListener(AFTER_COMMIT)` và `@Transactional(REQUIRES_NEW)` để kiểm soát chính xác.

Thread pool và queue ảnh hưởng lớn tới throughput, thời gian chờ và khả năng chịu quá tải. Cấu hình đúng cần xuất phát từ nhu cầu nghiệp vụ, loại workload và giới hạn DB/API, kèm policy từ chối rõ ràng. Khi ứng dụng dừng hoặc listener thất bại, cơ chế publication registry/outbox và retry được cấu hình phù hợp mới giúp theo dõi và khôi phục công việc. Consumer phải idempotent, bởi event có thể được giao lại.

### Tài liệu tham khảo

- [Spring Modulith — Working with Application Events](https://docs.spring.io/spring-modulith/reference/events.html) — `@ApplicationModuleListener`, transaction và Event Publication Registry.
- [Spring Modulith — ApplicationModuleListener API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/events/ApplicationModuleListener.html) — annotation composition.
- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html) — `@EnableAsync`, `@Async`, executor qualification và exception handling.
- [Spring Boot — Task Execution and Scheduling](https://docs.spring.io/spring-boot/reference/features/task-execution-and-scheduling.html) — auto-configuration, thread pool và virtual threads.

> Các con số thread/queue và đoạn mã là ví dụ học tập. Trước khi đưa vào production, đối chiếu API, bean selection và lifecycle với phiên bản Spring Framework, Spring Boot và Spring Modulith đang sử dụng.
