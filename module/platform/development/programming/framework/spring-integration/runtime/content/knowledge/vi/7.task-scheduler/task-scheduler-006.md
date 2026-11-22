# Pool size và giới hạn scheduler

Spring Integration dùng `TaskScheduler` để kích hoạt các polling endpoint và những tác vụ có lịch khác. Scheduler quyết định khi nào một polling task được chạy và thread nào thực thi task đó. Kích thước pool của scheduler vì vậy ảnh hưởng đến số tác vụ có thể chạy đồng thời, độ trễ khi bắt đầu poll, và khả năng một poller làm chậm những poller khác.

`poolSize` thường bị hiểu nhầm là số consumer, số message xử lý đồng thời hoặc capacity của queue. Thực tế, nó điều khiển số thread mà scheduler có thể dùng để thực thi các scheduled task. Muốn điều chỉnh throughput của một flow, cần xem đồng thời scheduler, poller, executor, handler và hệ thống downstream.

## 1. TaskScheduler trong Spring Integration

`TaskScheduler` là abstraction của Spring để lên lịch tác vụ theo thời điểm, khoảng delay, fixed rate hoặc cron trigger. Spring Integration dùng scheduler để kích hoạt polling endpoint. Khi đến thời điểm, polling endpoint thực hiện một lượt nhận message từ `PollableChannel` hoặc gọi một `MessageSource`, tùy loại endpoint.

Một số thành phần thường liên quan:

| Thành phần | Trách nhiệm |
|---|---|
| `TaskScheduler` | Lên lịch và kích hoạt tác vụ theo trigger |
| `ThreadPoolTaskScheduler` | Implementation dùng thread pool để chạy scheduled task |
| Polling endpoint | Thực hiện một lượt nhận message và gọi handler hoặc đưa message vào flow |
| `PollerMetadata` | Mô tả trigger, giới hạn message, executor, advice và các thuộc tính của poller |
| `TaskExecutor` | Thực thi công việc trên worker thread khi poller được cấu hình tách việc khỏi scheduler thread |

Một poller thường được kích hoạt lặp lại bởi scheduler. Nếu không tách execution bằng executor riêng, công việc polling có thể chạy ngay trên scheduler thread. Nếu lần poll bao gồm nhận message có timeout dài hoặc handler thực hiện I/O chậm, thread đó bị chiếm trong thời gian tương ứng.

## 2. ThreadPoolTaskScheduler và poolSize

`ThreadPoolTaskScheduler` là implementation phổ biến của `TaskScheduler`. Nó sử dụng `ScheduledThreadPoolExecutor` bên dưới. `poolSize` quyết định số scheduler thread có thể thực thi scheduled task đồng thời.

Ví dụ cấu hình scheduler riêng cho các polling task của Spring Integration:

```java
@Configuration
class IntegrationSchedulerConfiguration {

    @Bean(name = "taskScheduler")
    ThreadPoolTaskScheduler taskScheduler() {
        ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
        scheduler.setPoolSize(8);
        scheduler.setThreadNamePrefix("si-scheduler-");
        scheduler.setWaitForTasksToCompleteOnShutdown(true);
        scheduler.setAwaitTerminationSeconds(30);
        scheduler.setRemoveOnCancelPolicy(true);
        return scheduler;
    }
}
```

Trong ví dụ, scheduler có tối đa 8 thread thực thi scheduled task cùng lúc. Prefix giúp nhận diện thread trong log và thread dump. Cấu hình shutdown yêu cầu scheduler chờ task đang chạy trong thời gian giới hạn; `removeOnCancelPolicy` giúp loại task đã bị hủy khỏi hàng đợi delay của executor.

Nếu tự tạo `ThreadPoolTaskScheduler`, giá trị mặc định của Spring Framework là một thread. Hạ tầng Spring Integration hoặc Spring Boot có thể cung cấp scheduler mặc định tùy cấu hình và phiên bản. Trong ứng dụng thực tế, hãy xác định bean scheduler mà poller đang sử dụng và cấu hình rõ ràng khi tải yêu cầu nhiều hơn một tác vụ chạy đồng thời.

`poolSize` là số thread của scheduler, không phải capacity của queue. Scheduled executor lưu các tác vụ đã lên lịch trong hàng đợi delay; tăng pool size không đặt giới hạn số tác vụ đã được đăng ký hoặc số message đang chờ trong `QueueChannel`.

## 3. Pool size giới hạn điều gì?

Giả sử ứng dụng có 12 polling endpoint độc lập, mỗi endpoint được kích hoạt định kỳ và mỗi lượt poll mất 2 giây. Nếu tất cả dùng chung scheduler có pool size 4, tối đa 4 scheduled task có thể chạy cùng lúc. Các task còn lại chờ thread trống, vì vậy thời điểm thực thi thực tế có thể trễ so với trigger.

| Cấu hình | Ý nghĩa |
|---|---|
| `poolSize = 1` | Chỉ một scheduled task có thể thực thi tại một thời điểm trên scheduler đó |
| `poolSize = 4` | Tối đa bốn scheduled task có thể thực thi đồng thời |
| `poolSize = 8` | Tối đa tám scheduled task có thể thực thi đồng thời |

Pool size không bảo đảm mọi task bắt đầu đúng giờ. Nếu tất cả thread đều đang bận, task đã đến hạn phải đợi. Pool size lớn hơn có thể giảm chờ do scheduler contention, nhưng cũng làm tăng số công việc có thể chạy đồng thời và gây áp lực lên database, HTTP client, broker hoặc hệ thống đích.

Một polling endpoint thường có một tác vụ định kỳ của riêng nó. Việc tăng pool size chủ yếu cho phép nhiều endpoint độc lập chạy song song; nó không tự động làm một endpoint xử lý nhiều message hơn trong một lượt. Muốn thay đổi số message mỗi lượt, điều chỉnh `maxMessagesPerPoll`; muốn tăng worker song song, xem cấu hình consumer/executor tương ứng.

## 4. Phân biệt scheduler pool, task executor và queue capacity

Ba loại giới hạn này nằm ở những ranh giới khác nhau:

| Cơ chế | Giới hạn hoặc điều khiển | Ví dụ |
|---|---|---|
| Scheduler `poolSize` | Số scheduled task có thể thực thi đồng thời | Tối đa 8 poller task chạy trên scheduler |
| `TaskExecutor` | Số worker thực thi công việc được giao và chính sách hàng đợi của executor | Poller giao việc cho worker pool có giới hạn |
| Channel capacity | Số message có thể chờ trong một channel có giới hạn | `QueueChannel(500)` giữ tối đa 500 message |

`maxMessagesPerPoll` là một giới hạn thứ tư: số message tối đa mà một polling task nhận trong một lượt. Nó không làm scheduler có thêm thread và cũng không tăng capacity của channel.

Ví dụ, scheduler có pool size 4, executor có 10 worker, queue channel có capacity 500 và `maxMessagesPerPoll = 20`. Những con số này không có nghĩa hệ thống luôn xử lý 40 message cùng lúc. Số tác vụ thực sự chạy phụ thuộc vào số poller, cách poller dispatch sang executor, trạng thái thread pool, thời gian handler và giới hạn downstream.

## 5. Khi nào scheduler thread bị chiếm lâu?

Scheduler thread có thể bị giữ trong suốt thời gian scheduled task chạy. Với polling endpoint, thời gian đó có thể bao gồm:

- Chờ message qua `receiveTimeout` khi channel rỗng.
- Nhận và xử lý tối đa `maxMessagesPerPoll` message.
- Chạy transformer hoặc handler có thao tác I/O đồng bộ.
- Chờ transaction, retry hoặc backoff trong advice chain.
- Chờ hệ thống bên ngoài phản hồi.

Nếu poller xử lý lâu trên scheduler thread, những tác vụ khác dùng chung scheduler có thể bắt đầu trễ. Đây là một dạng scheduler starvation hoặc contention. Tăng pool size có thể giúp trong ngắn hạn, nhưng nếu nguyên nhân là handler bị block lâu, nên xem xét tách công việc xử lý sang một `TaskExecutor` có giới hạn và giữ scheduler thread cho việc kích hoạt lịch.

Không nên cấu hình một executor không giới hạn chỉ để tránh scheduler bị block. Khi worker pool và queue của executor không có giới hạn hợp lý, backlog có thể chuyển từ scheduler sang executor và tiếp tục tăng cho đến khi cạn tài nguyên.

## 6. Tách lịch kích hoạt và xử lý bằng TaskExecutor

Scheduler có thể chịu trách nhiệm kích hoạt poller, trong khi `TaskExecutor` thực thi phần công việc polling trên worker thread theo cấu hình poller. Việc tách này hữu ích khi handler có thể block hoặc cần xử lý song song có kiểm soát.

Ví dụ khai báo một executor có số worker và queue hữu hạn:

```java
@Bean
ThreadPoolTaskExecutor pollerExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(4);
    executor.setMaxPoolSize(8);
    executor.setQueueCapacity(100);
    executor.setThreadNamePrefix("si-poller-worker-");
    executor.setWaitForTasksToCompleteOnShutdown(true);
    executor.setAwaitTerminationSeconds(30);
    return executor;
}
```

Đây là executor cho công việc được dispatch; nó không thay thế `TaskScheduler`. Khi cấu hình poller dùng executor, cần kiểm tra API của phiên bản Spring Integration đang dùng và gắn đúng executor vào `PollerMetadata` hoặc endpoint DSL. Cũng cần xác định chính sách khi executor hết worker hoặc queue đầy: task bị từ chối, caller chạy task, hay một cơ chế backpressure khác.

Khi tách executor, thread xử lý có thể khác scheduler thread. Vì vậy, không nên dựa vào thread-local state của scheduler để truyền security context, transaction context hoặc dữ liệu request. Hãy dùng cơ chế truyền context phù hợp và xác định transaction boundary trên worker thread.

## 7. Chọn pool size cho tải thực tế

Không có công thức cố định cho mọi ứng dụng. Cách chọn phụ thuộc loại task và số polling endpoint có thể hoạt động cùng lúc.

Với polling task ngắn, không block và kết thúc nhanh, pool size nhỏ có thể phục vụ nhiều endpoint. Với task có `receiveTimeout` dài hoặc handler chạy I/O đồng bộ, mỗi task có thể giữ một thread lâu hơn; cần tăng pool hoặc tách xử lý sang executor. Với task CPU-bound, tăng thread vượt số CPU khả dụng thường làm tăng context switching thay vì tăng throughput.

Một quy trình sizing thực tế:

1. Liệt kê các polling endpoint và tần suất kích hoạt của từng endpoint.
2. Đo thời gian từ lúc task được kích hoạt đến khi kết thúc, gồm cả thời gian chờ nhận message.
3. Xác định những task nào có thể đến hạn cùng lúc và có thể chạy song song.
4. Đặt pool size ban đầu đủ cho mức đồng thời dự kiến, cộng một khoảng dự phòng hợp lý.
5. Tải thử với backlog và downstream gần với production.
6. Điều chỉnh theo độ trễ bắt đầu poll, thời gian xử lý, thread bận và tải của downstream.

Một cách ước lượng sơ bộ là so sánh tổng thời gian thread bị chiếm bởi các task đến hạn trong một khoảng thời gian với số thread sẵn có. Nếu nhiều task thường xuyên chờ vì toàn bộ scheduler thread đang bận, cần tìm task giữ thread lâu hoặc tăng năng lực scheduler có kiểm soát.

Không nên lấy số lượng polling endpoint làm pool size một cách máy móc. Nhiều poller có lịch khác nhau và chỉ chạy trong thời gian ngắn có thể chia sẻ một pool nhỏ. Ngược lại, một vài poller có thời gian xử lý dài cũng có thể làm pool nhỏ bị bão hòa.

## 8. Fixed delay, fixed rate và scheduler contention

Trigger quyết định thời điểm một tác vụ được lên lịch; scheduler pool quyết định khi nào có thread để thực thi nó.

| Trigger | Cách tính lịch | Khi scheduler bận |
|---|---|---|
| `fixedDelay` | Chờ delay sau khi lần thực thi trước hoàn tất | Lần tiếp theo được tính sau khi task hoàn tất, nhưng vẫn cần thread để chạy |
| `fixedRate` | Duy trì nhịp thời gian giữa các lần kích hoạt | Task có thể bắt đầu trễ nếu thread không sẵn sàng; cùng một periodic task không chạy chồng lấn chính nó |
| `cron` | Kích hoạt tại các mốc lịch | Nếu scheduler bận ở mốc đó, việc thực thi thực tế có thể trễ |

Tăng pool size không thay đổi semantics của trigger. Nó chỉ tăng số task độc lập có thể được thực thi đồng thời. Nếu một poller có fixed delay 1 giây nhưng mỗi lượt mất 5 giây, việc tăng scheduler pool không làm chính poller đó chạy chồng lấn nhiều lượt; nó chỉ giúp các poller khác không phải chờ thread của nó.

## 9. Scheduler queue và giới hạn số task đã đăng ký

`ThreadPoolTaskScheduler` dựa trên `ScheduledThreadPoolExecutor`. Hàng đợi delay của scheduled executor dùng để giữ các tác vụ đã được lên lịch và không phải queue có capacity giống `QueueChannel`. `poolSize` giới hạn số thread thực thi, không giới hạn số scheduled future được đăng ký.

Điều này quan trọng với flow động. Nếu ứng dụng liên tục tạo polling endpoint hoặc schedule task mới mà không stop/destroy flow cũ, số scheduled task có thể tăng dù pool size không đổi. Tăng pool size không giải quyết rò rỉ registration hoặc task đã lên lịch bị bỏ quên.

Khi hủy flow hoặc endpoint, cần bảo đảm scheduled task được cancel theo lifecycle. `removeOnCancelPolicy` có thể giúp executor loại task đã hủy khỏi hàng đợi delay, tránh giữ lại các task cancel trong queue cho đến thời điểm dự kiến chạy. Theo dõi số endpoint đang hoạt động và số scheduled task khi ứng dụng dùng `IntegrationFlowContext`.

## 10. Shutdown và lifecycle của scheduler

Scheduler thường là bean do application context quản lý. Khi context đóng, bean lifecycle sẽ dừng việc lập lịch mới và giải phóng executor theo cấu hình shutdown.

Một số thuộc tính cần xem xét:

| Thuộc tính | Ý nghĩa |
|---|---|
| `waitForTasksToCompleteOnShutdown` | Yêu cầu executor chờ task đã nhận hoàn tất theo chính sách shutdown |
| `awaitTerminationSeconds` | Giới hạn thời gian chờ executor kết thúc |
| `removeOnCancelPolicy` | Loại scheduled task đã cancel khỏi delay queue khi executor hỗ trợ |
| `threadNamePrefix` | Đặt prefix để nhận diện thread trong log và thread dump |

Chờ task hoàn tất có thể giúp xử lý poll đang chạy, nhưng cũng làm shutdown kéo dài. Cần đặt timeout phù hợp và có chính sách khi task không thể hoàn tất. Nếu handler đang gọi hệ thống ngoài, timeout HTTP/database cũng cần hữu hạn để scheduler không bị giữ vô thời hạn.

Với flow động, `registration.stop()` dừng endpoint và các lần poll mới theo lifecycle của nó; `registration.destroy()` loại bỏ registration. Đừng chỉ xóa handle khỏi registry mà quên dừng endpoint, vì scheduled task và tài nguyên liên quan có thể vẫn tồn tại.

## 11. Nhiều scheduler trong cùng application context

Ứng dụng có thể có nhiều nhóm công việc với yêu cầu khác nhau: polling endpoint của Spring Integration, tác vụ `@Scheduled`, housekeeping, hoặc công việc bảo trì. Nếu tất cả dùng chung một scheduler nhỏ, một nhóm task chạy lâu có thể làm các nhóm còn lại trễ.

Có thể tách scheduler theo mục đích:

- Scheduler cho polling endpoint cần độ trễ ổn định.
- Scheduler cho tác vụ bảo trì hoặc housekeeping ít ưu tiên.
- Scheduler riêng cho một nhóm flow có thời gian xử lý và tải khác biệt rõ rệt.

Việc tách scheduler cần có chủ đích. Mỗi pool là một tập thread và tài nguyên riêng; tạo quá nhiều scheduler làm tăng chi phí quản lý, thread và khó vận hành. Đặt tên bean rõ ràng, chỉ định scheduler đúng nơi poller sử dụng và ghi nhận ai sở hữu vòng đời của bean đó.

Không giả định mọi `@Scheduled` task và Spring Integration poller chắc chắn dùng cùng một scheduler. Cách resolve scheduler phụ thuộc cấu hình Spring, Spring Boot và Spring Integration. Kiểm tra bean thực tế được inject hoặc resolve cho từng cơ chế trước khi chẩn đoán contention.

## 12. Quan sát và chẩn đoán scheduler saturation

Khi poller chạy trễ, cần xác định task chưa được kích hoạt, task đang chờ thread hay handler đang chạy quá lâu. Các số liệu hữu ích gồm:

- Pool size và số thread active.
- Số scheduled task đang chờ và số task đã hoàn tất.
- Thời gian từ mốc trigger tới lúc task thực sự bắt đầu.
- Thời gian thực thi từng polling task.
- Số poller bị trễ, queue depth của channel và số message xử lý mỗi lượt.
- Retry count, error count và thời gian chờ downstream.
- Số worker active, queue depth và rejected task của `TaskExecutor` nếu được dùng.

Với `ThreadPoolTaskScheduler`, có thể quan sát underlying `ScheduledThreadPoolExecutor` qua API truy cập của scheduler để lấy các chỉ số phù hợp. Trong môi trường Spring Boot, kết hợp Actuator/Micrometer nếu các metric cần thiết đã được bật. Thread dump cũng giúp tìm scheduler thread đang block ở `receive()`, database, HTTP client hoặc handler.

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Nhiều poller bắt đầu trễ cùng lúc | Scheduler pool bão hòa | Active thread, task duration, pool size |
| Chỉ một flow chậm | Handler hoặc downstream của flow đó bị block | Thread dump, I/O latency, retry |
| CPU thấp nhưng poller trễ | Thread đang chờ I/O hoặc receive timeout | Stack trace và thời gian chờ |
| Tăng pool nhưng downstream lỗi nhiều hơn | Quá nhiều tác vụ cùng gọi hệ thống đích | Connection pool, rate limit, concurrency |
| Scheduled task tăng dần theo thời gian | Flow/endpoint động chưa được destroy hoặc task chưa cancel | Registration count, endpoint lifecycle, cancelled future |
| Shutdown không kết thúc | Task bị block hoặc executor chờ quá lâu | Await termination, timeout downstream, thread dump |

## 13. Những lỗi cấu hình thường gặp

- **Pool size quá nhỏ:** nhiều poller chia sẻ một thread; một task chậm làm các task khác trễ.
- **Pool size quá lớn:** quá nhiều công việc chạy đồng thời, gây tranh chấp CPU, connection pool hoặc rate limit downstream.
- **Dùng scheduler thay cho worker executor:** handler nặng chạy trực tiếp trên scheduler thread và giữ lịch của các poller khác.
- **Nhầm pool size với queue capacity:** tăng scheduler pool không làm `QueueChannel` chứa được nhiều message hơn.
- **Không giới hạn công việc:** `maxMessagesPerPoll = -1`, receive timeout dài và handler chậm có thể tạo một lượt poll kéo dài.
- **Chia sẻ scheduler không có quan sát:** tác vụ `@Scheduled`, poller và housekeeping tranh chấp cùng pool mà không có metric.
- **Không cleanup flow động:** endpoint đã hết nhu cầu nhưng scheduled task và bean runtime vẫn còn.
- **Shutdown không có timeout:** task block vô hạn làm context đóng chậm hoặc không hoàn tất.

## 14. Nguyên tắc sizing và vận hành

- **Xác định scheduler thực tế:** kiểm tra bean và cấu hình mà poller đang dùng; không dựa vào giả định về default.
- **Đo trước khi tăng pool:** dùng thời gian task, độ trễ kích hoạt và thread dump để xác định contention.
- **Giữ scheduler task ngắn:** chuyển công việc I/O hoặc xử lý dài sang executor có giới hạn khi phù hợp.
- **Tách các nhóm lịch có yêu cầu khác nhau:** chỉ tạo scheduler riêng khi cần cô lập độ trễ hoặc tài nguyên.
- **Phân biệt các loại giới hạn:** pool size, executor capacity, channel capacity và `maxMessagesPerPoll` điều khiển những thứ khác nhau.
- **Bảo vệ downstream:** concurrency của scheduler và executor phải nằm trong năng lực database, broker và API đích.
- **Quản lý lifecycle:** cancel task, stop/destroy endpoint và chờ shutdown trong thời gian hữu hạn.
- **Theo dõi task động:** giới hạn số flow và registration được tạo trong runtime, cleanup khi không còn dùng.

Trước khi thay đổi `poolSize`, hãy xác định poller nào đang dùng scheduler đó, task nào giữ thread lâu, và có bao nhiêu task thực sự cần chạy đồng thời. Scheduler pool đủ lớn giúp các tác vụ được kích hoạt đúng nhịp hơn, nhưng hiệu năng cuối cùng vẫn phụ thuộc vào executor, handler, channel và khả năng của hệ thống downstream.
