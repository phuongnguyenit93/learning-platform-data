# Trigger fixed rate, fixed delay và cron

Trong **SPRING_INTEGRATION_RUNTIME**, poller là thành phần giúp một consumer lấy message từ nguồn theo lịch. Lịch này được điều khiển bởi trigger và thực thi thông qua **TaskScheduler**. Spring Integration cung cấp ba kiểu lịch phổ biến: **fixed rate**, **fixed delay** và **cron**. Chọn đúng kiểu trigger ảnh hưởng trực tiếp đến độ trễ, throughput, khả năng dự đoán thời điểm xử lý và cách ứng dụng phản ứng khi một lượt poll kéo dài.

Ba trigger có thể được dùng trong Java DSL thông qua `Pollers.fixedRate(...)`, `Pollers.fixedDelay(...)` và `Pollers.cron(...)`. Chúng quyết định **khi nào polling endpoint được gọi**. Số message được lấy trong một lần poll, thời gian xử lý handler và mức song song lại phụ thuộc vào cấu hình poller, channel, executor và handler. Hiểu riêng từng lớp giúp tránh nhầm lẫn giữa chu kỳ poll với tốc độ xử lý message.

## 1. Poller, trigger và TaskScheduler

### 1.1 Polling endpoint hoạt động như thế nào?

Với một `PollableChannel` hoặc một `MessageSource`, consumer không được channel gọi trực tiếp khi message xuất hiện. Polling endpoint cần chủ động lấy message theo lịch.

Một lượt poll tổng quát có thể hình dung:

~~~mermaid
flowchart TD
    A["TaskScheduler"] --> B["Trigger đến hạn"]
    B --> C["Polling endpoint chạy"]
    C --> D["receive() từ MessageSource / PollableChannel"]
    D --> E{"Có message?"}
    E -->|Có| F["Gọi MessageHandler"]
    F --> G{"Còn quota trong lượt poll?"}
    G -->|Có| D
    G -->|Không| H["Kết thúc lượt poll"]
    E -->|Không| H
    H --> A
~~~

Các thành phần có trách nhiệm khác nhau:

- **Trigger** xác định thời điểm một tác vụ đến hạn.
- **TaskScheduler** lên lịch và gọi tác vụ tại thời điểm phù hợp.
- **Polling endpoint** thực hiện thao tác nhận message và chuyển message tới handler.
- **TaskExecutor** có thể được dùng để thực thi tác vụ poll hoặc công việc bất đồng bộ theo cấu hình.
- **MessageHandler** xử lý payload hoặc message sau khi nhận.

Trong flow event-driven dùng `SubscribableChannel`, channel dispatch message tới subscriber khi producer gửi. Với polling consumer, endpoint chủ động gọi `receive()`; do đó lịch trigger mới quyết định khi nào consumer kiểm tra nguồn.

### 1.2 TaskScheduler khác TaskExecutor

`TaskScheduler` quản lý thời điểm chạy tác vụ. `TaskExecutor` quản lý việc thực thi task trên thread.

| Thành phần | Trả lời câu hỏi | Ví dụ |
|---|---|---|
| Trigger | Khi nào tác vụ đến hạn? | Mỗi 5 giây, sau khi lượt trước hoàn tất 2 giây, hoặc 8 giờ sáng ngày làm việc |
| TaskScheduler | Ai lên lịch và gọi tác vụ? | `ThreadPoolTaskScheduler` |
| TaskExecutor | Task chạy trên thread nào? | `ThreadPoolTaskExecutor` |
| Poller | Khi được gọi thì lấy message như thế nào? | `maxMessagesPerPoll`, `receiveTimeout` |
| Handler | Message được xử lý ra sao? | Service activator, transformer, filter |

Không nên tăng pool của TaskExecutor để giải quyết một poller có lịch chạy sai. Cũng không nên tăng tần suất trigger khi handler đang nghẽn database hoặc API bên ngoài. Trước hết cần xác định độ trễ nằm ở lịch poll, thời gian nhận message, executor hay logic xử lý.

## 2. Fixed rate: lên lịch theo nhịp cố định

### 2.1 Ý nghĩa

Fixed rate đặt mục tiêu thời điểm bắt đầu các lượt thực thi cách nhau một khoảng thời gian cố định. Ví dụ fixed rate 5 giây có các mốc dự kiến:

~~~text
Thời điểm dự kiến:  00s    05s    10s    15s    20s
                   |------|------|------|------|
Lượt poll:          P1     P2     P3     P4     P5
~~~

Khoảng thời gian được tính theo lịch bắt đầu của các lượt, không phải đợi một khoảng delay sau khi lượt trước kết thúc mới tính lượt tiếp theo.

Fixed rate phù hợp khi muốn kiểm tra nguồn theo nhịp đều, chẳng hạn đồng bộ trạng thái định kỳ, đọc dữ liệu theo chu kỳ hoặc kiểm tra một nguồn có message mới.

### 2.2 Cấu hình trong Spring Integration

~~~java
@Bean
IntegrationFlow fixedRateFlow(
        MessageSource<Order> orderSource,
        OrderService orderService) {

    return IntegrationFlow.from(
            orderSource,
            endpoint -> endpoint.poller(
                Pollers.fixedRate(5_000)
                    .maxMessagesPerPoll(10)))
        .handle(orderService, "process")
        .get();
}
~~~

Ví dụ này yêu cầu polling endpoint được lên lịch theo fixed rate 5 giây. Mỗi lần được gọi, poller có thể lấy tối đa 10 message theo cấu hình `maxMessagesPerPoll`, nếu nguồn còn message.

Fixed rate không có nghĩa mỗi message được xử lý cách nhau 5 giây. Trigger lên lịch **một lượt poll**; một lượt poll có thể nhận nhiều message. Nếu handler xử lý từng message mất 200 ms và poller lấy 10 message, thời gian xử lý của một lượt có thể lớn hơn đáng kể so với thời gian nhận một message.

### 2.3 Khi lượt poll kéo dài hơn chu kỳ

Giả sử chu kỳ là 5 giây nhưng một lượt poll mất 8 giây. Với scheduler dựa trên `ScheduledExecutorService`, cùng một periodic task không thực thi chồng lấn với chính nó; lần chạy tiếp theo có thể bị trễ so với mốc dự kiến. Scheduler không tự tạo thêm một bản sao task đang chạy để chạy song song.

Tuy nhiên, cần phân biệt callback được scheduler gọi với công việc mà callback giao cho executor hoặc thành phần bất đồng bộ. Nếu poller hoặc downstream dùng executor/channel bất đồng bộ, công việc của lượt trước có thể vẫn đang xử lý trong khi lượt poll kế tiếp bắt đầu. Khi đó mức concurrency phụ thuộc cấu hình executor và endpoint, không chỉ phụ thuộc fixed rate.

Dùng fixed rate khi mốc bắt đầu đều đặn có ý nghĩa. Nếu mỗi lượt cần cách nhau một khoảng nghỉ sau khi xử lý xong, fixed delay thường dễ dự đoán hơn.

## 3. Fixed delay: đợi sau khi lượt trước hoàn tất

### 3.1 Ý nghĩa

Fixed delay tính khoảng chờ từ khi một lần thực thi kết thúc đến khi lần kế tiếp bắt đầu.

~~~text
Lượt poll 1:       [---- xử lý 3 giây ----]
                                              <--- delay 5 giây --->
Lượt poll 2:                                                  [---- ... ----]
                                                                  <--- delay --->
Lượt poll 3:                                                                      [...]
~~~

Nếu xử lý mất 3 giây và fixed delay là 5 giây, khoảng cách giữa hai thời điểm bắt đầu sẽ xấp xỉ 8 giây. Nếu xử lý mất 7 giây, khoảng cách giữa hai lần bắt đầu sẽ xấp xỉ 12 giây.

Fixed delay phù hợp khi cần nghỉ một khoảng thời gian sau khi xử lý xong, ví dụ:

- Gọi API bên ngoài có giới hạn tần suất.
- Poll một nguồn chậm và muốn tránh tạo tải liên tục.
- Chạy tác vụ mà thời gian xử lý thay đổi đáng kể.
- Muốn giữ một khoảng nghỉ ổn định giữa hai lượt đồng bộ.

### 3.2 Cấu hình trong Spring Integration

~~~java
@Bean
IntegrationFlow fixedDelayFlow(
        MessageSource<Order> orderSource,
        OrderService orderService) {

    return IntegrationFlow.from(
            orderSource,
            endpoint -> endpoint.poller(
                Pollers.fixedDelay(5_000)
                    .maxMessagesPerPoll(20)))
        .handle(orderService, "process")
        .get();
}
~~~

Ở đây poller chờ 5 giây sau khi một lượt thực thi kết thúc trước khi lên lịch lượt kế tiếp. Mỗi lượt có thể nhận tối đa 20 message theo quota đã đặt.

Fixed delay thường phù hợp với polling source cần giới hạn áp lực lên hệ thống ngoài. Đổi lại, nếu xử lý kéo dài, tần suất poll thực tế giảm theo thời gian xử lý. Điều này có thể làm tăng độ trễ phát hiện message mới.

## 4. Cron: lên lịch theo thời gian lịch

### 4.1 Ý nghĩa

Cron trigger xác định thời điểm chạy theo biểu thức lịch, thay vì theo một khoảng thời gian đều nhau. Ví dụ:

- Mỗi 5 phút.
- Mỗi ngày lúc 02:00.
- Từ thứ Hai đến thứ Sáu lúc 09:00.
- Mỗi đầu giờ.

Spring cron expression sử dụng 6 trường theo thứ tự:

~~~text
second minute hour day-of-month month day-of-week
   |      |    |       |          |       |
   |      |    |       |          |       +-- Thứ trong tuần
   |      |    |       |          +---------- Tháng
   |      |    |       +--------------------- Ngày trong tháng
   |      |    +----------------------------- Giờ
   |      +---------------------------------- Phút
   +----------------------------------------- Giây
~~~

Ví dụ biểu thức:

| Cron expression | Lịch chạy |
|---|---|
| `0 */5 * * * *` | Mỗi 5 phút, tại giây 0 |
| `0 0 * * * *` | Đầu mỗi giờ |
| `0 0 2 * * *` | Mỗi ngày lúc 02:00 |
| `0 0 9 * * MON-FRI` | 09:00 từ thứ Hai đến thứ Sáu |
| `0 30 8 1 * *` | 08:30 ngày đầu mỗi tháng |

Spring cron expression có trường giây ở đầu, khác với một số cron scheduler chỉ dùng 5 trường. Không sao chép biểu thức từ Linux crontab hoặc dịch vụ cloud mà chưa kiểm tra định dạng.

### 4.2 Cấu hình poller dùng cron

~~~java
@Bean
IntegrationFlow cronFlow(
        MessageSource<ReportRequest> reportSource,
        ReportService reportService) {

    return IntegrationFlow.from(
            reportSource,
            endpoint -> endpoint.poller(
                Pollers.cron("0 0 2 * * *")
                    .maxMessagesPerPoll(50)))
        .handle(reportService, "generate")
        .get();
}
~~~

Ví dụ yêu cầu poller chạy lúc 02:00 mỗi ngày và xử lý tối đa 50 message trong một lượt. Nếu nguồn có nhiều hơn 50 message, phần còn lại sẽ được xử lý ở những lượt sau theo lịch tiếp theo hoặc theo cách poller được cấu hình.

Cron phù hợp với công việc gắn với lịch nghiệp vụ như tạo báo cáo cuối ngày, đối soát, đồng bộ đầu ngày hoặc kiểm tra theo khung giờ. Nó không phù hợp nếu mục tiêu thực tế chỉ là chạy đều mỗi 5 giây; fixed rate hoặc fixed delay dễ hiểu và dễ kiểm soát hơn.

### 4.3 Time zone và daylight saving time

Cron thường được diễn giải theo múi giờ của trigger hoặc scheduler. Nếu lịch nghiệp vụ gắn với một múi giờ cụ thể, hãy cấu hình múi giờ một cách tường minh thay vì phụ thuộc timezone mặc định của máy chạy.

Ví dụ lịch báo cáo lúc 02:00 tại Việt Nam nên được xác định theo `Asia/Ho_Chi_Minh`. Nếu ứng dụng chạy ở nhiều khu vực hoặc container dùng UTC, thời điểm thực thi có thể khác với giờ địa phương mà người vận hành mong đợi.

Các khu vực có daylight saving time có thể có ngày mà một giờ địa phương bị bỏ qua hoặc xuất hiện hai lần. Cần quyết định lịch nghiệp vụ nên bám giờ địa phương hay thời gian UTC. Với tác vụ tài chính hoặc đối soát, phải xác định rõ cách xử lý những ngày chuyển đổi giờ.

Khi cần chỉ định timezone trực tiếp, Spring Framework cung cấp `CronTrigger` nhận biểu thức cron cùng timezone. Với poller DSL, kiểm tra overload và cấu hình trigger mà phiên bản Spring Integration đang dùng hỗ trợ; không giả định mọi phiên bản có cùng API cấu hình timezone.

## 5. So sánh ba trigger

| Tiêu chí | Fixed rate | Fixed delay | Cron |
|---|---|---|---|
| Cách tính | Theo nhịp thời gian cố định giữa các mốc dự kiến | Delay tính từ khi lượt trước hoàn tất | Theo biểu thức ngày/giờ |
| Phù hợp | Kiểm tra đều đặn | Nghỉ sau khi xử lý xong | Lịch nghiệp vụ |
| Ảnh hưởng khi xử lý lâu | Tick có thể trễ; công việc async được giao có thể chồng lấn | Lượt sau bắt đầu muộn hơn theo thời gian xử lý | Lượt chạy phụ thuộc trigger và cách xử lý missed tick |
| Dự đoán thời điểm | Tốt khi tác vụ ngắn và scheduler ổn định | Phụ thuộc thời gian xử lý | Tốt theo giờ lịch và timezone |
| Ví dụ | Mỗi 10 giây | Nghỉ 5 giây sau mỗi lượt | 02:00 mỗi ngày |

Một cách chọn nhanh:

- Dùng **fixed rate** nếu muốn các lần poll theo nhịp cố định và tác vụ thường hoàn thành nhanh.
- Dùng **fixed delay** nếu muốn luôn có một khoảng nghỉ sau khi mỗi lượt hoàn tất.
- Dùng **cron** nếu thời điểm chạy gắn với ngày, giờ hoặc ngày làm việc.

Không chọn trigger chỉ dựa vào con số chu kỳ. Cần xét thời gian xử lý, mức tải của nguồn, độ trễ chấp nhận được, cách xử lý khi ứng dụng dừng và yêu cầu về múi giờ.

## 6. Một lượt poll xử lý bao nhiêu message?

Trigger chỉ quyết định thời điểm gọi polling endpoint. Trong mỗi lượt, poller có thể gọi `receive()` nhiều lần tùy `maxMessagesPerPoll`.

Ví dụ:

~~~java
Pollers.fixedDelay(1_000)
    .maxMessagesPerPoll(25)
~~~

Nghĩa là poller được lên lịch với fixed delay 1 giây và có quota tối đa 25 message trong một lượt. Đây không phải cam kết mỗi giây xử lý đúng 25 message. Nếu nguồn rỗng, lượt poll có thể không tạo ra message nào; nếu handler chậm, một lượt có thể mất nhiều thời gian hơn dự kiến.

Cần cân nhắc các trường hợp:

- **Quota nhỏ**: giảm thời gian một lượt poll chiếm scheduler, nhưng có thể làm backlog tăng nếu tốc độ nhận thấp hơn tốc độ message đến.
- **Quota lớn**: tăng số message xử lý mỗi lượt, giảm overhead lên lịch, nhưng một lượt có thể chạy lâu và làm các tác vụ khác phải chờ nếu scheduler pool nhỏ.
- **Nguồn rỗng**: poller vẫn có thể được gọi theo trigger nhưng không tạo công việc nghiệp vụ.
- **Nguồn liên tục có message**: quota lớn hoặc không giới hạn có thể khiến một lượt xử lý kéo dài; cần giữ fairness với các endpoint khác.

`maxMessagesPerPoll` là giới hạn số message mà polling consumer nhận trong một lần thực thi. Nó không thay thế giới hạn concurrency của executor, cũng không đảm bảo message được xử lý song song.

## 7. Cấu hình TaskScheduler cho polling endpoint

### 7.1 ThreadPoolTaskScheduler

TaskScheduler thực thi callback được lên lịch. Có thể khai báo một `ThreadPoolTaskScheduler` để điều khiển số thread dành cho tác vụ scheduler:

~~~java
@Bean
ThreadPoolTaskScheduler taskScheduler() {
    ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
    scheduler.setPoolSize(4);
    scheduler.setThreadNamePrefix("si-scheduler-");
    scheduler.setWaitForTasksToCompleteOnShutdown(true);
    scheduler.setAwaitTerminationSeconds(30);
    return scheduler;
}
~~~

Ví dụ dùng pool 4 thread để scheduler có thể chạy nhiều scheduled task khác nhau. Tên bean và cách Spring Integration chọn scheduler cần thống nhất với cấu hình hạ tầng của ứng dụng; không tạo nhiều scheduler bean trùng vai trò mà không có chủ đích.

Một scheduler pool quá nhỏ có thể khiến tác vụ định kỳ khác phải chờ khi một callback chiếm thread lâu. Một pool quá lớn lại tạo thêm thread và context switching không cần thiết. Đo thời gian thực thi, độ trễ lịch và số scheduled task trước khi thay đổi pool size.

### 7.2 Scheduler không phải worker pool nghiệp vụ

Nếu polling endpoint xử lý handler đồng bộ, thời gian xử lý có thể chiếm thread scheduler. Nếu cần tách việc poll và xử lý, có thể cấu hình executor ở poller hoặc đặt một channel bất đồng bộ trong flow.

Ví dụ về ranh giới:

~~~mermaid
flowchart LR
    A["TaskScheduler"] --> B["Polling endpoint"]
    B --> C["MessageSource"]
    C --> D["Message"]
    D --> E["ExecutorChannel"]
    E --> F["Worker thread"]
    F --> G["Message handler"]
~~~

Trong mô hình này, scheduler lên lịch poll; poller lấy message; ExecutorChannel chuyển việc xử lý downstream sang executor. Scheduler và worker pool có thể được điều chỉnh độc lập theo tải và yêu cầu concurrency.

Khi thêm executor, handler có thể tiếp tục chạy sau khi thao tác gửi message qua channel trả về. Vì vậy, transaction, exception, thứ tự hoàn thành và shutdown cần được xem xét tại ranh giới bất đồng bộ.

## 8. Phân biệt Poller với @Scheduled

Spring Framework có annotation `@Scheduled` để lên lịch gọi một method. Spring Integration poller là cấu hình gắn với một polling endpoint, nơi một lần trigger dẫn đến thao tác nhận message từ MessageSource hoặc PollableChannel.

| Cách dùng | Mục đích |
|---|---|
| `@Scheduled` | Lên lịch gọi method ứng dụng |
| `Pollers.fixedRate(...)` | Lên lịch một polling endpoint theo fixed rate |
| `Pollers.fixedDelay(...)` | Lên lịch polling endpoint theo fixed delay |
| `Pollers.cron(...)` | Lên lịch polling endpoint theo cron |

Ví dụ `@Scheduled`:

~~~java
@Component
class CacheRefreshJob {

    @Scheduled(fixedDelay = 30_000)
    void refresh() {
        // Gọi logic refresh cache.
    }
}
~~~

Ví dụ poller:

~~~java
@Bean
IntegrationFlow refreshRequestFlow(
        MessageSource<RefreshRequest> source,
        CacheRefreshService service) {

    return IntegrationFlow.from(source,
            endpoint -> endpoint.poller(Pollers.fixedDelay(30_000)))
        .handle(service, "refresh")
        .get();
}
~~~

Cả hai đều dùng cơ chế scheduling của Spring, nhưng poller tích hợp trực tiếp với message flow. Không cần dùng `@Scheduled` để tự gọi `receive()` nếu một polling endpoint đã đáp ứng yêu cầu. Ngược lại, một tác vụ chỉ gọi method nội bộ và không cần message abstraction có thể phù hợp với `@Scheduled`.

## 9. Poller, transaction và retry

Một poller có thể được cấu hình advice để bao quanh hoạt động polling hoặc xử lý message. Đây là nơi thường đặt transaction advice, retry advice hoặc các cross-cutting concern khác.

Một số điểm cần xác định:

- Transaction bao quanh thao tác đọc nguồn, xử lý handler hay cả hai?
- Message được lấy khỏi queue trước hay sau khi transaction bắt đầu?
- Nếu handler thất bại, nguồn có thể rollback để message được nhận lại không?
- Nếu nguồn ngoài không hỗ trợ transaction, cần acknowledgement hoặc idempotency như thế nào?
- Retry chạy trên cùng thread hay qua executor khác?

Với nguồn database có transaction phù hợp, poller có thể phối hợp transaction để đọc và xử lý dữ liệu theo ranh giới đã chọn. Với broker hoặc API ngoài, cơ chế xác nhận và redelivery phụ thuộc connector. Không giả định mọi MessageSource đều rollback message giống nhau.

Retry cần phân biệt lỗi tạm thời và lỗi không thể khắc phục. Nếu retry không giới hạn với delay ngắn, một endpoint lỗi có thể chiếm scheduler hoặc worker liên tục. Hãy đặt giới hạn số lần thử, backoff, error channel và cơ chế lưu message lỗi theo yêu cầu nghiệp vụ.

## 10. Ứng dụng dừng hoặc bỏ lỡ lịch thì sao?

TaskScheduler chỉ lập lịch trong vòng đời process đang chạy. Nếu ứng dụng dừng lúc 02:00 và khởi động lại lúc 02:20, cron không tự tạo lại một lượt poll bền vững cho mốc 02:00 đã qua. Tương tự, fixed rate hoặc fixed delay không tự lưu lịch sử các tick đã bỏ lỡ khi process không hoạt động.

Nếu yêu cầu là “mỗi ngày phải tạo một báo cáo”, không nên chỉ dựa vào cron trigger. Cần lưu trạng thái công việc hoặc thời điểm kỳ gần nhất đã hoàn thành để khi ứng dụng khởi động lại có thể phát hiện kỳ bị thiếu và chạy bù.

Một số mẫu xử lý:

- Lưu `lastSuccessfulRun` hoặc bảng job execution trong database.
- Tạo job theo ngày nghiệp vụ với unique key để tránh chạy trùng.
- Dùng scheduler phân tán hoặc job store bền vững nếu nhiều node cùng điều phối.
- Thiết kế handler idempotent để chạy lại không tạo dữ liệu trùng.
- Dùng lock/lease nếu chỉ một instance được quyền thực hiện một kỳ công việc.

Cron trigger không phải message broker và không phải durable job store. Nếu cần đảm bảo một lần chạy cho mỗi kỳ, phải xây dựng cơ chế lưu trạng thái, khóa và chạy bù phù hợp.

## 11. Quan sát và chẩn đoán lịch poll

Khi poller không chạy đúng thời điểm hoặc backlog tăng, kiểm tra theo từng lớp:

| Triệu chứng | Điểm cần kiểm tra |
|---|---|
| Không có lượt poll | Endpoint có running không, autoStartup có bật không, trigger có hợp lệ không |
| Poll chạy lệch giờ | Time zone, cron expression, scheduler pool có bị chiếm không |
| Fixed delay lâu hơn mong đợi | Thời gian xử lý lượt trước, thời gian nhận message và thời gian chờ |
| Fixed rate bị trễ | Callback có chạy lâu hơn chu kỳ, scheduler có đủ thread không |
| Cron bỏ lỡ một kỳ | Process có dừng, trigger có lenient behavior, có cơ chế catch-up không |
| Backlog tăng | maxMessagesPerPoll, throughput handler, executor queue và nguồn message |
| CPU thấp nhưng độ trễ cao | I/O, lock, connection pool, transaction hoặc remote service |
| Nhiều lượt xử lý đồng thời | Poller task executor, downstream channel và worker pool |

Các metric hữu ích:

- Số lần poll và thời gian giữa hai lần poll.
- Thời gian chạy một lượt poll.
- Số message nhận được mỗi lượt.
- Thời gian xử lý từng message.
- Queue depth và backlog ở nguồn.
- Số thread scheduler đang active.
- Số worker executor đang active và task đang chờ.
- Số lần lỗi poll, lỗi handler và retry.
- Thời điểm chạy thành công gần nhất của job nghiệp vụ.

Đặt thread name prefix có ý nghĩa như `si-scheduler-` và `si-order-worker-` để đọc log và thread dump. Ghi `messageId`, `correlationId` và tên endpoint để lần theo một message qua flow.

## 12. Kiểm thử trigger và polling endpoint

Kiểm thử lịch không nên phụ thuộc vào những khoảng sleep dài hoặc thời gian thực không ổn định. Có thể:

- Kiểm tra cấu hình poller được tạo với đúng trigger và quota.
- Dùng MessageSource giả để đếm số lần receive và trả message theo kịch bản.
- Dùng CountDownLatch để chờ handler được gọi thay vì sleep cố định.
- Kiểm tra fixed delay bằng cách ghi nhận thời điểm bắt đầu/kết thúc từng lượt.
- Kiểm tra cron expression với các thời điểm lịch đại diện, bao gồm timezone và ngày chuyển đổi giờ nếu nghiệp vụ liên quan.
- Kiểm tra endpoint stop để xác nhận poller không tiếp tục tạo lượt poll mới.
- Kiểm tra lỗi handler, retry và error channel riêng với test lịch bình thường.

Với test integration, dùng scheduler được cấu hình cho test và thời gian chờ có giới hạn. Tránh để test phụ thuộc trực tiếp vào một mốc cron trong tương lai xa.

## 13. Những nhầm lẫn cần tránh

- **Fixed rate không phải fixed delay**: fixed rate bám nhịp mốc chạy; fixed delay đợi sau khi lượt trước hoàn tất.
- **Cron không phải khoảng thời gian cố định**: nó bám lịch ngày/giờ và timezone.
- **Trigger không quyết định số message**: `maxMessagesPerPoll` kiểm soát quota của một lượt poll.
- **Một lần poll không đồng nghĩa một message**: một lượt có thể nhận nhiều message tùy cấu hình.
- **TaskScheduler không phải TaskExecutor**: một bên lập lịch, một bên thực thi task.
- **Poller không giống event-driven consumer**: poller chủ động gọi receive; event-driven consumer được channel dispatch.
- **Fixed rate không tự đảm bảo xử lý song song**: scheduler và executor mới quyết định thread và concurrency.
- **Cron không lưu lần chạy khi ứng dụng dừng**: cần job store hoặc cơ chế catch-up nếu không được phép bỏ kỳ.
- **Tăng tần suất poll không tự tăng throughput**: nếu handler hoặc nguồn ngoài đang nghẽn, tăng tần suất có thể làm tải nặng hơn.
- **Dừng poller không tự drain backlog**: cần trình tự shutdown và kiểm tra message đang chờ.

## 14. Tự kiểm tra

1. Nếu một lượt xử lý mất 8 giây và chu kỳ mong muốn là 5 giây, fixed rate và fixed delay tạo ra lịch bắt đầu khác nhau như thế nào?
2. Một polling endpoint dùng cron lúc 02:00 mỗi ngày. Vì sao lịch này có thể chạy sai giờ khi chuyển môi trường từ Việt Nam sang một vùng timezone khác?
3. Nếu muốn mỗi lượt poll xử lý tối đa 20 message, cần cấu hình thuộc tính nào? Trigger có quyết định con số này không?
4. Vì sao TaskScheduler và TaskExecutor cần được quan sát riêng?
5. Một poller fixed rate dùng executor để xử lý bất đồng bộ. Vì sao công việc của lượt trước có thể vẫn đang chạy khi lượt poll tiếp theo bắt đầu?
6. Ứng dụng dừng trong thời điểm cron đến hạn rồi khởi động lại sau đó. Cần cơ chế nào để không bỏ lỡ kỳ công việc?
7. Khi nguồn message rỗng, poller vẫn được lên lịch. Điều này khác gì với một event-driven consumer?
8. Khi một lượt poll xử lý quá nhiều message, nó có thể ảnh hưởng thế nào tới các scheduled task khác dùng chung scheduler?

## Tài liệu tham khảo

- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [Spring Framework — TaskScheduler API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/TaskScheduler.html)
- [Spring Framework — CronTrigger API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/support/CronTrigger.html)
- [Spring Integration — Poller configuration](https://docs.spring.io/spring-integration/reference/endpoint.html#polling-consumer)
- [Spring Integration — Pollers API](https://docs.spring.io/spring-integration/docs/current/api/org/springframework/integration/dsl/Pollers.html)

## Kết luận

Fixed rate, fixed delay và cron đều điều khiển thời điểm polling endpoint được gọi, nhưng chúng biểu diễn ba loại lịch khác nhau: nhịp đều giữa các mốc, khoảng nghỉ sau khi hoàn tất và lịch theo ngày/giờ. TaskScheduler thực thi lịch; poller quyết định cách lấy message và quota mỗi lượt; executor cùng channel quyết định ranh giới thread và concurrency. Khi chọn trigger, cần tính cả thời gian xử lý, timezone, backlog, transaction, retry và tình huống ứng dụng dừng. Với công việc nghiệp vụ không được bỏ kỳ, hãy lưu trạng thái thực thi và thiết kế cơ chế chạy bù thay vì kỳ vọng cron tự lưu các lần chạy đã bỏ lỡ.
