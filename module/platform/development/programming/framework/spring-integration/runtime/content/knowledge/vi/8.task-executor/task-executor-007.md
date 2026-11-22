# RejectedExecutionHandler khi executor đầy

Trong Spring Integration, một `TaskExecutor` thường tạo ranh giới bất đồng bộ cho message flow. Ví dụ, `ExecutorChannel` nhận message từ luồng gửi rồi giao việc xử lý cho thread pool. Khi các worker đều bận và hàng đợi đã đạt giới hạn, thread pool không thể nhận thêm task. `RejectedExecutionHandler` quyết định điều gì xảy ra tại thời điểm đó.

Đây là một phần của cơ chế điều tiết tải. Chọn sai policy có thể làm mất message âm thầm, khiến thread gửi bị chặn lâu, hoặc đẩy lỗi ngược về producer. Vì vậy, cần hiểu rõ thời điểm executor từ chối, tác động của từng policy và cách đưa tín hiệu quá tải về đúng nơi trong hệ thống.

## 1. Khi nào executor từ chối task?

Với `ThreadPoolExecutor`, việc nhận một task thường diễn ra theo thứ tự sau:

1. Nếu số worker hiện tại nhỏ hơn `corePoolSize`, executor tạo worker để chạy task.
2. Nếu đã có đủ worker lõi, executor thử đưa task vào work queue.
3. Nếu queue không nhận được task và số worker vẫn nhỏ hơn `maxPoolSize`, executor tạo thêm worker.
4. Nếu không thể đưa task vào queue hoặc tạo worker mới, executor gọi `RejectedExecutionHandler`.

Executor cũng từ chối task khi đã shutdown, kể cả khi queue chưa đầy. Vì vậy, rejection có thể báo hiệu quá tải hoặc việc ứng dụng đang dừng.

Ba tham số ảnh hưởng trực tiếp đến ngưỡng quá tải:

| Tham số | Ý nghĩa | Hệ quả khi tăng |
|---|---|---|
| `corePoolSize` | Số worker lõi được duy trì theo cấu hình | Có thêm worker xử lý đồng thời ngay từ mức tải thông thường |
| `maxPoolSize` | Số worker tối đa | Có thể tăng số worker khi queue đã đầy |
| `queueCapacity` | Số task chờ được nhận vào queue | Hấp thụ được nhiều đợt tải tăng đột biến, đổi lại thời gian chờ có thể dài hơn |

Với `ThreadPoolTaskExecutor`, `queueCapacity` dương thường tạo queue có giới hạn; giá trị không dương tạo cơ chế chuyển giao trực tiếp (`SynchronousQueue`). Nếu dùng queue không giới hạn, queue gần như luôn nhận task nên `maxPoolSize` thường không phát huy tác dụng mở rộng worker. Khi tải kéo dài, queue không giới hạn có thể tăng bộ nhớ và thời gian chờ cho đến khi hệ thống suy giảm.

Không nên tăng cả queue lẫn số worker chỉ để làm biến mất cảnh báo rejection. Hãy xác định trước tốc độ message đi vào, thời gian xử lý trung bình, khả năng xử lý của hệ thống phụ thuộc và mức trễ mà nghiệp vụ chấp nhận được.

## 2. Rejection xuất hiện ở đâu trong Spring Integration?

### ExecutorChannel

`DirectChannel` gọi handler ngay trên thread gửi message. Nó không tạo task trong thread pool nên không có rejection từ executor của channel.

`ExecutorChannel` dùng `TaskExecutor` để chuyển việc xử lý sang worker thread. Khi hoạt động bình thường, lời gọi gửi message có thể kết thúc trước khi handler xử lý xong. Nếu executor từ chối ngay lúc submit task, lỗi phát sinh tại ranh giới gửi message và có thể được trả về cho bên gọi `send()`.

Với `ThreadPoolTaskExecutor` và policy mặc định `AbortPolicy`, Spring chuyển `RejectedExecutionException` của JDK thành `TaskRejectedException` khi gọi `execute()`. Lớp channel hoặc thành phần gửi có thể bọc lỗi trong ngoại lệ giao message của Spring Integration; vì vậy, khi xử lý lỗi ở tầng ứng dụng, hãy kiểm tra cả nguyên nhân gốc thay vì chỉ phụ thuộc vào một kiểu ngoại lệ bên ngoài.

### Poller và các điểm thực thi bất đồng bộ

Task executor cũng có thể được dùng để chạy poller hoặc các subscriber của một kênh publish-subscribe. Policy tác động tại nơi thành phần đó submit task vào executor. Vị trí quan sát được lỗi phụ thuộc vào thành phần gửi task và cách nó được cấu hình.

Hãy phân biệt hai tình huống:

- **Không submit được task:** executor từ chối trước khi worker bắt đầu xử lý. Đây là tình huống của `RejectedExecutionHandler`.
- **Task đã chạy nhưng xử lý message thất bại:** lỗi phát sinh trong handler hoặc downstream flow. Hãy dùng cơ chế xử lý lỗi của message flow, chẳng hạn error flow phù hợp, retry hoặc dead-letter theo thiết kế. Rejection handler không thay thế cơ chế này.

Đặc biệt, không nên mặc định rằng mọi rejection sẽ tự động đi vào `errorChannel`. Rejection xảy ra ở bước submit task, thường trên thread gọi executor; hãy bắt và xử lý lỗi tại ranh giới gửi hoặc tại upstream có khả năng retry/backpressure.

## 3. Bốn policy có sẵn của JDK

`RejectedExecutionHandler` là interface có phương thức:

```java
void rejectedExecution(Runnable task, ThreadPoolExecutor executor);
```

JDK cung cấp bốn policy phổ biến:

| Policy | Hành vi khi bị từ chối | Tác động lên message flow |
|---|---|---|
| `AbortPolicy` | Ném `RejectedExecutionException` | Producer nhận tín hiệu lỗi rõ ràng; phù hợp khi cần biết task chưa được nhận |
| `CallerRunsPolicy` | Chạy task ngay trên thread gọi `execute()` nếu executor chưa shutdown | Tạo backpressure tự nhiên vì thread gửi phải làm việc; có thể làm tăng latency của producer |
| `DiscardPolicy` | Bỏ task mới mà không báo lỗi | Có nguy cơ mất message âm thầm |
| `DiscardOldestPolicy` | Bỏ task ở đầu queue rồi thử submit task mới | Có nguy cơ làm mất message cũ đang chờ; thứ tự và độ công bằng có thể bị ảnh hưởng |

Một số chi tiết cần nhớ:

- `CallerRunsPolicy` không chạy task nếu executor đã shutdown. Trong trường hợp đó, task có thể bị bỏ mà không có ngoại lệ.
- `DiscardOldestPolicy` thường phù hợp hơn với tác vụ có thể thay thế, chẳng hạn cập nhật trạng thái mới nhất. Nó nguy hiểm với command hoặc event mà mỗi message đều phải được xử lý.
- `DiscardPolicy` không tạo ra tín hiệu để producer retry. Nếu dùng cho message nghiệp vụ, hệ thống phải chấp nhận rõ ràng khả năng mất dữ liệu hoặc có cơ chế quan sát và phục hồi khác.
- `AbortPolicy` là lựa chọn mặc định của `ThreadPoolExecutor` và `ThreadPoolTaskExecutor` nếu không cấu hình policy khác.

### Chọn policy theo yêu cầu xử lý

| Yêu cầu | Hướng lựa chọn | Lý do |
|---|---|---|
| Mỗi message phải được xử lý hoặc phải có lỗi để upstream phản ứng | `AbortPolicy` | Không che giấu việc executor không nhận task |
| Có thể làm chậm producer trong thời gian ngắn | `CallerRunsPolicy` | Khi bão hòa, producer tự tham gia xử lý và giảm tốc độ gửi |
| Chỉ quan tâm giá trị mới nhất, tác vụ cũ có thể bỏ | Cân nhắc `DiscardOldestPolicy` | Task cũ trong queue có thể không còn giá trị |
| Tác vụ phụ, mất task được chấp nhận và có giám sát riêng | Cân nhắc `DiscardPolicy` | Bỏ task có chủ đích, không làm gián đoạn producer |

Với đơn hàng, thanh toán, cập nhật dữ liệu hoặc event cần bảo toàn, thường nên bắt đầu bằng `AbortPolicy`, sau đó thiết kế retry có giới hạn hoặc đưa tải trở lại broker. Không dùng policy bỏ task chỉ để giữ cho luồng gửi luôn trả về thành công.

## 4. Cấu hình ThreadPoolTaskExecutor cho một flow

Ví dụ sau tạo một executor có queue giới hạn và dùng `AbortPolicy`. `ExecutorChannel` tạo ranh giới bất đồng bộ cho flow xử lý đơn hàng.

```java
import java.util.concurrent.ThreadPoolExecutor;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.TaskExecutor;
import org.springframework.integration.channel.ExecutorChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
public class OrderIntegrationConfiguration {

    @Bean("integrationTaskExecutor")
    public ThreadPoolTaskExecutor integrationTaskExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(100);
        executor.setKeepAliveSeconds(60);
        executor.setThreadNamePrefix("si-order-");
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(30);
        return executor;
    }

    @Bean("asyncOrdersChannel")
    public MessageChannel asyncOrdersChannel(
            @Qualifier("integrationTaskExecutor") TaskExecutor executor) {
        return new ExecutorChannel(executor);
    }

    @Bean
    public IntegrationFlow orderFlow() {
        return IntegrationFlow.from("ordersIn")
                .channel("asyncOrdersChannel")
                .handle((payload, headers) -> {
                    // Xử lý đơn hàng ở worker thread.
                    processOrder(payload);
                    return null;
                })
                .get();
    }

    private void processOrder(Object payload) {
        // Gọi nghiệp vụ xử lý đơn hàng.
    }
}
```

Spring quản lý vòng đời bean `ThreadPoolTaskExecutor` và khởi tạo nó trong quá trình tạo application context. Khi context dừng, `waitForTasksToCompleteOnShutdown` yêu cầu chờ các task đã nhận hoàn tất; `awaitTerminationSeconds` đặt giới hạn chờ. Các thiết lập shutdown không biến executor thành hàng đợi bền vững: task còn lại vẫn có thể không hoàn tất nếu tiến trình bị dừng cưỡng bức hoặc vượt quá thời gian chờ.

Với cấu hình trên, queue chứa tối đa 100 task đang chờ. Khi 8 worker đều bận và queue đầy, task tiếp theo bị từ chối. Nếu executor đang shutdown, task mới cũng bị từ chối. `AbortPolicy` làm cho bên submit nhận được lỗi để quyết định retry, báo lỗi hoặc chuyển sang cơ chế dự phòng.

## 5. CallerRunsPolicy tạo backpressure như thế nào?

Giả sử một `ExecutorChannel` đang dùng `CallerRunsPolicy`. Khi pool và queue đều đầy, thread gọi `send()` có thể chạy handler trực tiếp. Nếu handler mất 300 ms, lời gọi gửi message đó cũng có thể mất xấp xỉ thời gian xử lý còn lại của handler.

Hành vi này có thể làm chậm producer và giảm số task mới được đưa vào pool. Tuy nhiên, nó cũng làm thay đổi đặc tính của flow trong thời gian quá tải:

- Thread gửi có thể bị chặn bởi công việc downstream.
- Latency của HTTP request, listener hoặc poller gửi message có thể tăng mạnh.
- Handler có thể chạy trên thread có context khác với worker thông thường.
- Nếu producer đang giữ transaction hoặc lock, việc chạy handler ngay trên thread đó có thể kéo dài thời gian giữ tài nguyên.
- Với `ExecutorChannel`, flow vốn bất đồng bộ có thể tạm thời xử lý đồng bộ khi pool bão hòa.

Vì vậy, chỉ chọn `CallerRunsPolicy` khi producer có thể chịu được việc xử lý đồng bộ dự phòng. Hãy kiểm tra cả thread gửi thực tế: một request thread bị giữ lâu có thể làm cạn thread pool của web server, khiến quá tải lan sang những request không liên quan.

## 6. Viết rejection handler có đếm số lần từ chối

Nếu cần số liệu rõ ràng, có thể tạo policy tùy chỉnh. Ví dụ sau vẫn giữ hành vi fail-fast của `AbortPolicy`, đồng thời đếm số lần executor từ chối task:

```java
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.RejectedExecutionHandler;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.atomic.LongAdder;

public final class CountingAbortPolicy implements RejectedExecutionHandler {

    private final LongAdder rejectedCount = new LongAdder();

    @Override
    public void rejectedExecution(
            Runnable task, ThreadPoolExecutor executor) {
        rejectedCount.increment();
        throw new RejectedExecutionException(
                executor.isShutdown()
                        ? "Integration executor is shutting down"
                        : "Integration executor is saturated");
    }

    public long getRejectedCount() {
        return rejectedCount.sum();
    }
}
```

Đăng ký policy này cho `ThreadPoolTaskExecutor` bằng `setRejectedExecutionHandler(new CountingAbortPolicy())`. Trong ứng dụng thực tế, nên đưa bộ đếm vào Micrometer hoặc hệ thống metrics đang dùng để theo dõi tỷ lệ rejection theo thời gian. Bộ đếm trong ví dụ chỉ minh họa hành vi; nếu cần nhiều executor hoặc nhiều instance ứng dụng, hãy xuất metric có tag nhận diện executor và instance.

Không nên ghi log stack trace cho từng rejection ở mức cao khi hệ thống đang quá tải. Một đợt log lớn có thể làm tình trạng nặng hơn. Hãy dùng counter, rate, log có giới hạn và cảnh báo theo ngưỡng.

Một custom handler nhận `Runnable`, không nhận trực tiếp `Message<?>`. Vì thế, không nên cố phân tích message bằng cách ép kiểu task nội bộ của Spring Integration. Nếu cần xử lý theo message ID, correlation ID hoặc nghiệp vụ, hãy xử lý ở tầng message flow hoặc producer, nơi message còn được biểu diễn bằng kiểu dữ liệu rõ ràng.

## 7. Xử lý rejection ở ranh giới gửi message

Với policy ném lỗi, producer có thể bắt lỗi submit và quyết định hành động tiếp theo. Ví dụ minh họa:

```java
try {
    messagingTemplate.send("ordersIn", message);
} catch (RuntimeException ex) {
    if (hasRejectedExecutionCause(ex)) {
        // Ghi nhận quá tải và thực hiện retry có giới hạn,
        // hoặc để upstream broker gửi lại theo acknowledgement.
    } else {
        throw ex;
    }
}
```

`hasRejectedExecutionCause` ở đây là hàm ứng dụng kiểm tra chuỗi `cause` để tìm `TaskRejectedException` hoặc `RejectedExecutionException`; tên và cách triển khai phụ thuộc phiên bản Spring cùng lớp ngoại lệ bao quanh lời gọi gửi. Không nên retry vô hạn ngay trên cùng thread. Retry cần có giới hạn, backoff, jitter khi phù hợp và bảo đảm xử lý idempotent để một message được gửi lại không tạo tác dụng phụ trùng lặp.

Nếu message đến từ broker, hãy cân nhắc để broker giữ message cho đến khi consumer có thể nhận lại, tùy theo semantics acknowledgement của connector. Nếu message chỉ nằm trong bộ nhớ của producer hoặc executor, việc process dừng có thể làm mất phần backlog đó.

Khi cần buffer giữa producer và consumer, có thể dùng `QueueChannel` với poller để tách nơi nhận message khỏi nơi xử lý. Cần cấu hình giới hạn queue và cách xử lý khi queue đầy. Nếu cần backlog tồn tại qua lần restart, hãy dùng message store hoặc broker có khả năng lưu bền phù hợp với yêu cầu. Queue nội bộ của thread pool chỉ là nơi chờ thực thi task, không phải message store bền vững.

## 8. Theo dõi dấu hiệu bão hòa

Một executor có thể chưa phát sinh rejection nhưng đã gây trễ lớn vì queue tăng liên tục. Nên theo dõi đồng thời:

- Số worker đang hoạt động và tổng số worker.
- Độ dài queue và dung lượng còn lại.
- Tốc độ task được submit, hoàn tất và bị từ chối.
- Thời gian chờ trong queue và thời gian xử lý của handler.
- Tỷ lệ lỗi downstream, timeout và retry.
- Latency của producer khi dùng `CallerRunsPolicy`.

Đọc các chỉ số cùng nhau để tìm nguyên nhân. Queue tăng trong khi số task hoàn tất giảm thường gợi ý downstream chậm hoặc worker bị giữ lâu. Rejection tăng đột ngột có thể do lưu lượng tăng, dependency chậm, cấu hình pool quá nhỏ hoặc executor đang shutdown. Tăng `maxPoolSize` không giúp nhiều nếu database connection pool hoặc API downstream đã là nút thắt.

Khi xử lý sự cố, hãy lần lượt kiểm tra tốc độ message đầu vào, thời gian xử lý handler, trạng thái dependency, queue và worker. Sau đó chọn một hành động có kiểm soát: giảm tốc producer, điều chỉnh concurrency, tăng năng lực downstream, hoặc chuyển backlog sang broker. Đừng chỉ tăng queue vì queue lớn hơn có thể biến rejection thành thời gian chờ dài và tiêu thụ nhiều bộ nhớ.

## 9. Kiểm thử rejection một cách xác định

Có thể kiểm tra `AbortPolicy` bằng pool chỉ có một worker và queue chỉ chứa một task. Task đầu tiên giữ worker, task thứ hai chiếm chỗ trong queue, task thứ ba phải bị từ chối:

```java
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;

class RejectedExecutionHandlerTests {

    @Test
    void abortPolicyRejectsWhenWorkerAndQueueAreFull() throws Exception {
        ThreadPoolExecutor executor = new ThreadPoolExecutor(
                1,
                1,
                0,
                TimeUnit.SECONDS,
                new ArrayBlockingQueue<>(1),
                new ThreadPoolExecutor.AbortPolicy());

        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        try {
            executor.execute(() -> {
                started.countDown();
                try {
                    release.await();
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                }
            });

            if (!started.await(5, TimeUnit.SECONDS)) {
                throw new AssertionError("Worker did not start");
            }

            executor.execute(() -> { }); // Task thứ hai nằm trong queue.

            assertThrows(
                    RejectedExecutionException.class,
                    () -> executor.execute(() -> { })); // Task thứ ba bị từ chối.
        } finally {
            release.countDown();
            executor.shutdown();
            executor.awaitTermination(5, TimeUnit.SECONDS);
        }
    }
}
```

Khi kiểm thử với `ThreadPoolTaskExecutor`, hãy kiểm tra thêm ngoại lệ Spring quan sát được ở lời gọi `execute()` và ở lời gọi gửi message qua channel. Với `CallerRunsPolicy`, xác minh task thực sự chạy trên thread gọi khi pool bão hòa. Với policy bỏ task, xác minh metric hoặc tín hiệu nghiệp vụ có thể phát hiện task bị bỏ; nếu không có tín hiệu đó, bài kiểm thử rất dễ cho kết quả thành công giả.

## 10. Checklist khi đưa vào production

- Dùng queue có giới hạn và chọn `corePoolSize`, `maxPoolSize` dựa trên tải đo được.
- Xác định rõ message nào được phép bỏ và message nào phải được bảo toàn.
- Chọn policy phù hợp; với message nghiệp vụ quan trọng, ưu tiên rejection có thể quan sát và xử lý.
- Xử lý lỗi submit ở producer hoặc upstream; không nhầm rejection với lỗi handler sau khi task đã chạy.
- Retry có giới hạn, backoff và idempotency; tránh vòng retry làm tăng tải khi hệ thống đang nghẽn.
- Theo dõi queue, active worker, thời gian chờ, throughput và rejection rate.
- Kiểm tra hành vi trong shutdown và thời gian drain task.
- Nếu cần lưu backlog bền vững, dùng message store hoặc broker phù hợp thay vì dựa vào queue nội bộ của executor.

`RejectedExecutionHandler` là điểm quyết định cách hệ thống phản ứng khi executor không nhận thêm việc. Cấu hình tốt phải làm rõ ba điều: task bị từ chối có được báo cho upstream hay không, producer có bị chặn hay không, và message được bảo toàn bằng cơ chế nào. Khi ba điều này được thiết kế cùng với giới hạn queue và khả năng downstream, Spring Integration có thể phản ứng có kiểm soát khi tải vượt quá năng lực xử lý.
