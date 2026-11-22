# fixedDelay, fixedRate và cron trigger

Trong Spring Integration, một polling endpoint không liên tục hỏi channel một cách ngẫu nhiên. Nó được kích hoạt theo lịch bởi **poller**. Trigger của poller quyết định khi nào một chu kỳ poll bắt đầu: sau một khoảng nghỉ kể từ lần chạy trước (`fixedDelay`), theo nhịp thời gian cố định (`fixedRate`), hoặc tại những thời điểm khớp biểu thức lịch (`cron`).

Chọn trigger ảnh hưởng đến độ trễ nhận message, tải lên hệ thống, cách xử lý khi một chu kỳ kéo dài và khả năng khớp lịch nghiệp vụ. Tuy nhiên, trigger chỉ quyết định thời điểm poll; số message được lấy trong mỗi chu kỳ, thời gian xử lý handler, thread scheduler, executor và transaction vẫn là các phần cấu hình riêng.

Sau bài này, bạn có thể:

- Phân biệt thời điểm chạy của `fixedDelay`, `fixedRate` và `cron`.
- Cấu hình trigger trong Java DSL và hiểu `initialDelay`, `maxMessagesPerPoll`.
- Phân tích ảnh hưởng của thời gian xử lý đến nhịp polling.
- Phân biệt scheduler thread với thread xử lý message.
- Chọn trigger phù hợp và chẩn đoán polling bị trễ, quá tải hoặc chạy sai lịch.

## 1. Poller và polling cycle

Poller là cơ chế lập lịch cho endpoint cần chủ động lấy message. Nó thường được dùng với `PollableChannel` như `QueueChannel` hoặc với inbound channel adapter có nguồn dữ liệu được truy vấn theo lịch.

```text
TaskScheduler
     |
     | trigger fires
     v
Polling endpoint
     |
     | receive / read source
     v
Message (if available)
     |
     v
MessageHandler / downstream flow
```

Một lần trigger kích hoạt một **polling task**. Trong task đó, endpoint có thể lấy một hoặc nhiều message tùy `maxMessagesPerPoll` và cơ chế của source/channel. Khi không còn message, vòng lấy thường kết thúc sớm thay vì chờ đến khi đạt giới hạn. Sau đó trigger quyết định thời điểm task tiếp theo được gọi.

Không nên nhầm ba mốc sau:

- **Trigger time:** thời điểm scheduler kích hoạt polling task.
- **Receive time:** thời điểm endpoint thực sự lấy được message từ channel/source.
- **Processing time:** khoảng thời gian handler và các bước downstream xử lý message.

Nếu queue rỗng, một lần poll vẫn có thể chạy nhưng không tạo ra message. Nếu handler chậm, polling task có thể kéo dài và ảnh hưởng đến nhịp poll tiếp theo, tùy trigger và scheduler.

## 2. fixedDelay: chờ một khoảng sau khi lần chạy trước kết thúc

`fixedDelay` xác định khoảng thời gian giữa **kết thúc một lần thực thi** và **bắt đầu lần tiếp theo**. Ví dụ delay 2 giây nghĩa là sau khi polling task kết thúc, scheduler chờ khoảng 2 giây rồi mới kích hoạt task kế tiếp.

```text
Task 1: [---- xử lý 3 giây ----]  nghỉ 2 giây  Task 2: [---- ...
        ^ bắt đầu                ^             ^ bắt đầu
```

Nếu một polling task mất 3 giây và fixed delay là 2 giây, khoảng cách giữa hai thời điểm bắt đầu xấp xỉ 5 giây (chưa tính độ trễ lập lịch). Vì khoảng nghỉ được tính sau khi task kết thúc, `fixedDelay` tự điều chỉnh nhịp theo thời gian xử lý thực tế.

Ví dụ Java DSL:

```java
@Bean
IntegrationFlow pollOrders(OrderHandler handler) {
    return IntegrationFlow.from(
            "ordersQueue",
            endpoint -> endpoint.poller(
                    Pollers.fixedDelay(2_000)
                            .maxMessagesPerPoll(10)))
            .handle(handler, "handle")
            .get();
}
```

Ở ví dụ này, endpoint poll `ordersQueue` theo fixed delay 2.000 milliseconds và xử lý tối đa 10 message trong một polling cycle. Nếu queue hết message trước khi đạt 10, task có thể kết thúc sớm; khoảng delay tiếp theo được tính từ lúc task kết thúc.

`fixedDelay` phù hợp khi:

- Muốn có một khoảng nghỉ ổn định giữa các lần poll.
- Thời gian truy vấn hoặc xử lý có thể thay đổi đáng kể.
- Muốn tránh lịch chạy dồn ngay sau một lần poll kéo dài.
- Tải hệ thống nên giảm tự nhiên khi mỗi chu kỳ xử lý lâu hơn.

Đổi lại, nhịp polling không phải một tần suất tuyệt đối. Khi handler mất nhiều thời gian, thời điểm poll kế tiếp sẽ lùi tương ứng.

## 3. fixedRate: giữ nhịp theo thời điểm bắt đầu dự kiến

`fixedRate` xác định khoảng thời gian giữa **các thời điểm bắt đầu dự kiến**. Ví dụ fixed rate 2 giây đặt lịch bắt đầu ở các mốc 0s, 2s, 4s, 6s... theo đồng hồ lập lịch.

```text
Lịch dự kiến: 0s       2s       4s       6s
              |--------|--------|--------|

Task ngắn:    [--]     [--]     [--]     [--]
Task dài:     [------ task 3s ------][------ task 3s ------]
              0s                    ~3s
```

Nếu một task kéo dài hơn chu kỳ, lần chạy kế tiếp có thể bắt đầu muộn so với mốc dự kiến. Với cơ chế scheduler chuẩn, cùng một tác vụ định kỳ không chạy chồng lấn lên chính nó; các lần chạy trễ có thể được thực hiện sát nhau để tiếp tục bám lịch, tùy scheduler. `fixedRate` không tự tạo nhiều consumer hoặc nhiều thread song song cho cùng endpoint.

Ví dụ:

```java
@Bean
IntegrationFlow pollInventory(InventoryHandler handler) {
    return IntegrationFlow.from(
            "inventoryQueue",
            endpoint -> endpoint.poller(
                    Pollers.fixedRate(5_000)
                            .initialDelay(1_000)
                            .maxMessagesPerPoll(5)))
            .handle(handler, "refresh")
            .get();
}
```

`initialDelay(1_000)` yêu cầu chờ khoảng 1 giây trước lần poll đầu tiên; sau đó fixed rate 5 giây điều khiển nhịp các lần chạy tiếp theo. Đơn vị số nguyên trong các ví dụ `Pollers.fixedRate(long)` và `fixedDelay(long)` là milliseconds. Các overload nhận `Duration` có thể có tùy phiên bản Spring Integration.

`fixedRate` phù hợp khi:

- Muốn poll theo nhịp mục tiêu, chẳng hạn kiểm tra trạng thái mỗi 5 giây.
- Công việc mỗi lần poll thường ngắn và tương đối ổn định.
- Muốn lập lịch đều theo thời gian bắt đầu dự kiến.

Nếu mỗi lần poll thường xuyên kéo dài hơn chu kỳ, fixed rate có thể khiến task gần như chạy liên tục, không còn khoảng nghỉ như mong muốn. Khi đó cần xem lại chu kỳ, số message mỗi lần poll, thời gian handler hoặc năng lực xử lý.

## 4. cron: chạy theo lịch thời gian thực

`cron` kích hoạt polling task tại các thời điểm khớp biểu thức lịch. Nó phù hợp với công việc gắn với giờ/ngày cụ thể, ví dụ lấy báo cáo lúc 01:00 mỗi ngày hoặc đồng bộ dữ liệu vào các ngày làm việc.

Spring cron expression thông dụng có sáu trường:

```text
second minute hour day-of-month month day-of-week
```

Ví dụ:

| Biểu thức | Ý nghĩa |
|---|---|
| `0 */5 * * * *` | Mỗi 5 phút, tại giây 0. |
| `0 0 2 * * *` | Mỗi ngày lúc 02:00. |
| `0 30 8 * * MON-FRI` | 08:30 từ thứ Hai đến thứ Sáu. |
| `0 0 0 1 * *` | 00:00 ngày đầu mỗi tháng. |

Ví dụ Java DSL:

```java
@Bean
IntegrationFlow nightlyReconciliation(ReconciliationHandler handler) {
    return IntegrationFlow.from(
            "reconciliationQueue",
            endpoint -> endpoint.poller(
                    Pollers.cron("0 0 2 * * *")
                            .maxMessagesPerPoll(100)))
            .handle(handler, "reconcile")
            .get();
}
```

Flow trên được lập lịch vào 02:00 theo timezone của trigger/scheduler đang áp dụng. Khi nghiệp vụ yêu cầu múi giờ cụ thể, cần cấu hình timezone rõ ràng bằng API trigger/builder phù hợp với phiên bản Spring Integration đang dùng. Không nên giả định timezone của máy chủ luôn trùng timezone nghiệp vụ.

Cron là lịch theo đồng hồ lịch, không phải khoảng thời gian trôi qua. Thay đổi giờ mùa hè (DST), timezone hoặc thời gian hệ thống có thể làm thời điểm thực tế thay đổi. Một mốc giờ bị bỏ qua hoặc lặp lại khi chuyển DST cần được tính đến nếu tác vụ có yêu cầu chạy đúng một lần theo ngày nghiệp vụ. Ngoài ra, cú pháp cron của Spring có thể khác cron của Quartz hoặc hệ thống Unix; hãy dùng đúng định dạng sáu trường của Spring thay vì sao chép biểu thức bảy trường của Quartz.

## 5. So sánh ba trigger

| Tiêu chí | `fixedDelay` | `fixedRate` | `cron` |
|---|---|---|---|
| Mốc tính lịch | Sau khi lần chạy trước kết thúc. | Theo thời điểm bắt đầu dự kiến. | Theo biểu thức lịch. |
| Có phụ thuộc thời gian xử lý không? | Có; task càng lâu thì lần kế tiếp càng lùi. | Có thể bị trễ nếu task vượt chu kỳ; không mặc nhiên chạy song song. | Task dài có thể khiến lần kích hoạt kế tiếp bị trễ hoặc chờ theo scheduler. |
| Khoảng nghỉ sau task | Được giữ theo delay đã cấu hình. | Không được bảo đảm; task trễ có thể chạy sát lần tiếp theo. | Phụ thuộc khoảng cách giữa các mốc cron. |
| Dùng cho | Polling có khoảng nghỉ sau xử lý. | Công việc định kỳ theo nhịp đều. | Lịch theo giờ/ngày/tuần/tháng. |
| Ví dụ | Nghỉ 2 giây sau mỗi lần kiểm tra queue. | Kiểm tra mỗi 5 giây. | Đồng bộ lúc 02:00 mỗi ngày. |

Không có trigger nào tự quyết định throughput. Throughput còn phụ thuộc số message mỗi poll, thời gian xử lý, channel, executor, số endpoint, tốc độ nguồn dữ liệu và giới hạn của downstream.

## 6. maxMessagesPerPoll: số message trong một chu kỳ

Trigger trả lời câu hỏi “khi nào poll?”, còn `maxMessagesPerPoll` trả lời câu hỏi “mỗi polling task có thể lấy tối đa bao nhiêu message?”. Hai thuộc tính này cần được xem cùng nhau.

```java
Pollers.fixedDelay(1_000)
        .maxMessagesPerPoll(20)
```

Với cấu hình trên, mỗi chu kỳ có thể lấy tối đa 20 message. Nếu queue chỉ có 3 message, endpoint chỉ xử lý được 3 rồi kết thúc vòng lấy; nó không chờ cho đủ 20. Nếu queue luôn đầy, một chu kỳ có thể xử lý đủ 20 và chiếm scheduler thread trong thời gian handler chạy.

Giới hạn thấp giúp mỗi lần poll ngắn hơn và cho scheduler cơ hội phục vụ các tác vụ khác, nhưng có thể giảm throughput do overhead mỗi chu kỳ. Giới hạn cao giúp xử lý batch lớn hơn, nhưng có thể làm một task chiếm thread lâu và tăng độ trễ cho các công việc khác. Giá trị tối ưu phụ thuộc thời gian xử lý trung bình, kích thước message và tải hệ thống.

Một số API hỗ trợ giá trị `-1` để biểu thị không giới hạn số message trong một lần poll. Chỉ dùng khi nguồn có thể kết thúc vòng nhận đúng lúc và muốn drain đến khi hết message. Với nguồn luôn có dữ liệu hoặc nguồn không bao giờ trả về rỗng, một poll không giới hạn có thể chiếm thread quá lâu. Hãy xác minh semantics và giá trị mặc định theo loại endpoint/phiên bản đang dùng; khi cần kiểm soát tải, đặt giới hạn tường minh.

## 7. initialDelay và thời điểm poll đầu tiên

`initialDelay` trì hoãn lần thực thi đầu tiên của trigger theo khoảng thời gian được cấu hình. Nó thường hữu ích khi ứng dụng cần thời gian hoàn tất khởi động, kết nối datasource, nạp cấu hình hoặc chờ một thành phần phụ thuộc sẵn sàng.

```java
Pollers.fixedDelay(10_000)
        .initialDelay(30_000)
        .maxMessagesPerPoll(10)
```

Ví dụ trên chờ khoảng 30 giây trước lần poll đầu tiên, sau đó áp dụng fixed delay 10 giây giữa các polling task. `initialDelay` không phải thời gian chờ trước mỗi message và cũng không phải timeout của thao tác receive.

Không dùng initial delay để che giấu một dependency chưa sẵn sàng nếu ứng dụng có thể kiểm tra readiness rõ ràng. Với yêu cầu phụ thuộc trạng thái, hãy quản lý lifecycle/health condition để endpoint chỉ start khi điều kiện thực sự thỏa mãn.

## 8. Scheduler, executor và thread xử lý

Poller được kích hoạt bởi `TaskScheduler`. Khi trigger đến hạn, scheduler chạy polling task. Trong cấu hình đơn giản, phần receive và xử lý message có thể diễn ra trên thread thực thi polling task. Có thể cấu hình executor cho poller hoặc dùng channel bất đồng bộ để tách công việc sang thread khác.

Phân biệt ba loại thread:

- **Scheduler thread:** kích hoạt polling task theo trigger.
- **Poller task execution thread:** chạy logic nhận message; thường là scheduler thread nếu không cấu hình executor riêng.
- **Downstream handler thread:** chạy handler; có thể cùng thread poller hoặc chuyển sang executor qua channel như `ExecutorChannel`.

Ví dụ dùng executor cho poller (API builder cần đối chiếu phiên bản đang sử dụng):

```java
Pollers.fixedDelay(1_000)
        .taskExecutor(pollerExecutor)
        .maxMessagesPerPoll(10)
```

Việc tách executor có thể tăng khả năng chạy nhiều polling task, nhưng cũng làm thay đổi thứ tự, transaction context và cách lỗi được quan sát. Thread pool quá nhỏ có thể khiến task chờ; queue task quá lớn làm độ trễ tích tụ; queue quá nhỏ có thể gây rejected execution. Đừng tăng số thread trước khi đo thời gian poll, thời gian handler và độ sâu queue.

Một scheduler dùng chung cho nhiều poller cũng có thể trở thành điểm nghẽn nếu polling task chạy lâu. Cần kiểm tra scheduler pool size, thời gian chạy mỗi task và các poller khác cùng chia sẻ scheduler. Nếu dùng executor riêng cho poller, theo dõi cả executor đó và executor của channel downstream.

## 9. Transaction và retry quanh polling task

Poller có thể được kết hợp với advice chain để áp dụng transaction, retry hoặc các hành vi cross-cutting quanh một lần poll. Transaction boundary có thể được cấu hình qua transaction advice/transaction manager phù hợp; retry advice có thể thử lại khi việc nhận hoặc xử lý message gặp lỗi thuộc nhóm được phép retry.

```java
@Bean
IntegrationFlow pollPayments(PaymentHandler handler,
                             Advice transactionAdvice) {
    return IntegrationFlow.from(
            "paymentsQueue",
            endpoint -> endpoint.poller(
                    Pollers.fixedDelay(2_000)
                            .advice(transactionAdvice)
                            .maxMessagesPerPoll(1)))
            .handle(handler, "process")
            .get();
}
```

Đây là ví dụ minh họa gắn advice vào poller; `transactionAdvice` cần được tạo với transaction manager và phạm vi phù hợp. Nếu xử lý nhiều message trong một polling task, cần hiểu transaction advice bao quanh toàn task hay từng lần nhận/xử lý theo cấu hình endpoint và advice chain. Với yêu cầu mỗi message là một transaction riêng, hãy cấu hình và kiểm chứng boundary tương ứng thay vì suy ra từ `maxMessagesPerPoll`.

Retry cũng cần được phân biệt với trigger. Trigger quyết định thời điểm polling task tiếp theo được schedule; retry advice có thể thực hiện nhiều lần thử trong phạm vi một lần xử lý. Không dùng fixedRate ngắn để thay cho retry policy, vì cách đó không phân loại lỗi, không quản lý backoff theo nguyên nhân và có thể làm hệ thống tiếp tục nhận thêm công việc khi message cũ vẫn thất bại.

## 10. Chọn trigger theo tình huống

| Nhu cầu | Lựa chọn gợi ý | Lý do |
|---|---|---|
| Kiểm tra queue và nghỉ một khoảng sau mỗi batch | `fixedDelay` | Khoảng nghỉ bắt đầu sau khi polling task hoàn tất. |
| Kiểm tra trạng thái dịch vụ theo nhịp mục tiêu | `fixedRate` | Dễ biểu đạt chu kỳ dự kiến giữa các lần bắt đầu. |
| Chạy đối soát lúc 02:00 mỗi ngày | `cron` | Lịch gắn với giờ/ngày trên đồng hồ. |
| Tác vụ mất thời gian biến động và không muốn poll dồn | `fixedDelay` | Nhịp tự giãn theo thời gian thực thi. |
| Báo cáo vào ngày làm việc cuối tuần | `cron` | Có thể mô tả lịch theo ngày trong tuần và giờ cụ thể. |

Khi chọn, hãy trả lời ba câu hỏi: công việc được kích hoạt theo khoảng thời gian hay theo lịch thực; một lần poll có thể mất bao lâu; và nếu poll trễ thì hệ thống nên nghỉ, chạy bù hay bỏ qua mốc đã lỡ? Câu trả lời giúp chọn trigger và thiết kế xử lý trễ đúng với nghiệp vụ.

## 11. Chẩn đoán poller chạy sai nhịp hoặc quá tải

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Poll chậm hơn khoảng delay mong đợi | Task xử lý lâu; fixedDelay tính delay sau khi task kết thúc. | Đo thời gian polling task và handler. |
| fixedRate chạy gần như liên tục | Thời gian task thường xuyên vượt chu kỳ. | So sánh thời gian task với period; giảm batch hoặc tăng chu kỳ. |
| Cron không chạy đúng giờ nghiệp vụ | Timezone scheduler khác timezone nghiệp vụ hoặc biểu thức sai. | Kiểm tra sáu trường cron, timezone và log lần kích hoạt. |
| Queue tăng liên tục | Tốc độ producer lớn hơn tốc độ consumer; maxMessagesPerPoll thấp hoặc handler chậm. | Đo ingress/throughput, queue depth, thời gian xử lý và số poll. |
| Các poller khác cũng bị trễ | Scheduler thread pool dùng chung bị chiếm bởi task dài. | Kiểm tra scheduler pool, task duration và executor tách riêng. |
| Task bị từ chối | Executor queue đầy hoặc pool đạt giới hạn. | Kiểm tra rejection metric/log, queue capacity và worker utilization. |
| Message xử lý lặp hoặc transaction không như mong muốn | Transaction boundary, retry hoặc ack/receive semantics chưa đúng. | Kiểm tra advice chain, transaction manager và cơ chế nguồn. |

Quy trình kiểm tra:

1. Xác định loại endpoint và trigger thực tế được áp dụng.
2. Ghi lại thời điểm bắt đầu/kết thúc của polling task; so sánh với chu kỳ cấu hình.
3. Kiểm tra `maxMessagesPerPoll`, queue depth và thời gian xử lý từng message.
4. Kiểm tra scheduler và executor: pool size, active threads, queue task và rejected task.
5. Với cron, xác nhận timezone, biểu thức và thay đổi giờ hệ thống/DST.
6. Kiểm tra transaction, retry và error flow nếu message bị nhận lại hoặc không được hoàn tất.

## 12. Tự kiểm tra

**Tình huống:** Một poller dùng `fixedRate(2_000)` nhưng mỗi polling task mất khoảng 5 giây. Log cho thấy task kế tiếp bắt đầu gần như ngay sau khi task trước kết thúc.

1. Vì sao không có khoảng nghỉ 2 giây sau mỗi task?
2. Nếu muốn luôn nghỉ 2 giây sau khi task kết thúc, nên dùng trigger nào?
3. Nếu muốn chạy lúc 02:00 mỗi ngày theo giờ Việt Nam, cần quan tâm thêm điều gì ngoài biểu thức cron?
4. Nếu một lần poll lấy tối đa 50 message, thuộc tính nào điều khiển giới hạn này?

**Gợi ý trả lời:** (1) Fixed rate bám các mốc bắt đầu dự kiến; task dài hơn period khiến lần chạy trễ và có thể được thực hiện sát lần trước, nhưng không mặc nhiên chạy chồng lấn. (2) Dùng `fixedDelay(2_000)`. (3) Cấu hình timezone của trigger/scheduler theo `Asia/Ho_Chi_Minh` bằng API phù hợp phiên bản. (4) `maxMessagesPerPoll(50)`.

**Bài tập thực hành:** Tạo một polling flow với `QueueChannel`, handler cố ý mất khoảng 3 giây mỗi message và `maxMessagesPerPoll(2)`. Chạy lần lượt với `fixedDelay(1_000)` và `fixedRate(1_000)`, ghi lại thời điểm bắt đầu/kết thúc từng poll. Sau đó cấu hình cron chạy mỗi phút và xác nhận timezone. So sánh queue depth, khoảng nghỉ, scheduler thread và throughput.

## Tài liệu tham khảo

- [Spring Integration Reference — Pollers](https://docs.spring.io/spring-integration/reference/endpoint.html#polling-consumer)
- [Spring Integration Reference — Configuring the Task Scheduler](https://docs.spring.io/spring-integration/reference/configuration/namespace-taskscheduler.html)
- [Spring Integration Java DSL — Pollers](https://docs.spring.io/spring-integration/reference/dsl.html)
- [Spring Framework Reference — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
