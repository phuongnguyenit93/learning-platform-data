# Quản lý lịch đọc, luồng thực thi và dừng vòng lặp an toàn

Với consumer chủ động của Spring Cloud Stream, ứng dụng gọi `PollableMessageSource` để lấy message khi sẵn sàng xử lý. Cách tiếp cận này cho phép kiểm soát lịch đọc, thời gian chờ, thread thực thi và thời điểm dừng. Đổi lại, ứng dụng phải quản lý vòng đời polling một cách có chủ đích.

Một vòng lặp đọc message cần trả lời bốn câu hỏi: khi nào poll, poll trên thread nào, xử lý message trong bao lâu và điều gì xảy ra khi ứng dụng shutdown. Nếu gọi poll liên tục không có thời gian chờ, vòng lặp có thể tiêu thụ CPU khi queue rỗng. Nếu chạy vòng lặp vô hạn trong thread khởi động Spring, ứng dụng có thể không hoàn tất startup. Nếu dừng process mà không chờ handler đang chạy, message có thể được giao lại hoặc trạng thái xử lý không rõ ràng tùy binder.

## 1. PollableMessageSource và quyền chủ động của consumer

Spring Cloud Stream cung cấp `PollableMessageSource` cho mô hình consumer chủ động. Thay vì framework đẩy message vào một function liên tục, ứng dụng gọi `poll()` để yêu cầu nhận một message và cung cấp `MessageHandler` xử lý message đó.

Ví dụ tối giản:

```java
@Component
public class OrderPoller {

    private final PollableMessageSource source;
    private final OrderService orderService;

    public OrderPoller(
            PollableMessageSource source,
            OrderService orderService) {
        this.source = source;
        this.orderService = orderService;
    }

    public boolean pollOnce() {
        return source.poll(message -> {
            OrderPlaced event =
                (OrderPlaced) message.getPayload();

            orderService.handle(event);
        }, 500L);
    }
}
```

Trong ví dụ, ứng dụng yêu cầu poll với timeout 500 mili giây. Nếu nhận được message, handler được gọi. Nếu không có message trong thời gian chờ, `poll()` trả về `false`. Nếu handler xử lý thành công, lời gọi hoàn tất và `poll()` trả về `true`.

`PollableMessageSource` là API đồng bộ: lời gọi `poll()` thực hiện việc nhận và gọi handler trong luồng thực thi của poller. Vì vậy, thời gian xử lý của handler ảnh hưởng trực tiếp tới thời gian một lần poll hoàn tất. Đây là cơ sở để thiết kế lịch đọc và giới hạn concurrency.

## 2. Phân biệt timeout, không có message và xử lý lỗi

Kết quả của poll cần được hiểu đúng:

| Tình huống | Kết quả thường thấy | Hành động của ứng dụng |
|---|---|---|
| Có message và handler hoàn tất | `poll()` trả về `true` | Tiếp tục vòng đọc theo lịch |
| Không có message trong timeout | `poll()` trả về `false` | Chờ một khoảng rồi poll lại |
| Handler ném exception | Lỗi được truyền ra khỏi lần poll sau cơ chế retry được cấu hình | Ghi nhận lỗi và để binder/error policy xử lý |
| Broker hoặc kết nối gặp lỗi | Có thể phát sinh exception | Áp dụng backoff, quan sát trạng thái và phục hồi kết nối |

Không nên dùng `false` để biểu diễn lỗi xử lý nghiệp vụ. Giá trị này chỉ cho biết không nhận được message trong lần poll theo timeout. Lỗi từ handler hoặc broker cần được xử lý qua exception và cơ chế error handling.

Có thể dùng overload `poll(handler, timeout)` để tránh vòng lặp hỏi liên tục khi không có message. Nếu phiên bản binder cung cấp timeout riêng hoặc semantics khác, cần xác minh theo API của phiên bản đó. Không giả định mọi binder có cùng hành vi khi timeout hoặc lỗi kết nối.

## 3. Lập lịch polling và tránh busy loop

Vòng lặp sau có vấn đề:

```java
while (running) {
    source.poll(this::handle);
}
```

Nếu `poll()` trả về ngay khi không có message, vòng lặp sẽ gọi lại liên tục và tiêu thụ CPU. Đây là busy loop. Có thể khắc phục bằng timeout khi poll, khoảng nghỉ khi không có message hoặc một scheduler điều khiển tần suất đọc.

Một consumer chủ động thường cần ba khoảng thời gian riêng:

- **Poll timeout**: thời gian tối đa một lần poll chờ message.
- **Idle delay**: khoảng chờ trước lần poll tiếp theo khi không có message.
- **Error backoff**: khoảng chờ khi broker hoặc handler phát sinh lỗi liên tục.

Không nên gộp ba giá trị thành một cấu hình duy nhất. Khi queue rỗng, idle delay giúp giảm tải. Khi broker lỗi, error backoff cần tăng dần để tránh tạo thêm áp lực lên broker. Khi có message, consumer có thể poll tiếp ngay hoặc theo tốc độ đã giới hạn.

Ví dụ cấu hình:

```yaml
app:
  orders:
    polling:
      poll-timeout-ms: 500
      idle-delay-ms: 100
      initial-error-backoff-ms: 500
      max-error-backoff-ms: 30000
      shutdown-wait-seconds: 30
```

Đây là cấu hình riêng của ứng dụng, không phải thuộc tính chuẩn của Spring Cloud Stream. Các giá trị cần được hiệu chỉnh theo độ trễ chấp nhận được, throughput, timeout của service nghiệp vụ và khả năng của broker.

## 4. Chọn thread thực thi cho vòng polling

Vì `poll()` và handler có tính đồng bộ, không nên chạy vòng lặp vô hạn trên thread khởi động hoặc thread HTTP request. Có thể dùng một thread riêng để thực hiện polling:

```java
ExecutorService executor =
    Executors.newSingleThreadExecutor();

executor.submit(() -> {
    while (running) {
        boolean received = source.poll(this::handle, 500L);

        if (!received) {
            Thread.sleep(100L);
        }
    }
});
```

Đây chỉ là minh họa việc tách vòng lặp khỏi thread gọi. Một triển khai production cần quản lý executor, xử lý interruption, lỗi, backoff và shutdown. Không tạo executor mới cho mỗi lần poll hoặc mỗi message.

Một thread đơn giúp các lần poll không chồng lấn và giữ thứ tự gọi handler theo luồng poller. Nếu handler thực hiện JDBC hoặc HTTP blocking, thời gian xử lý của nó sẽ giữ thread polling. Đây là lựa chọn đơn giản, dễ dự đoán khi cần xử lý tuần tự.

Nếu cần tăng throughput, có thể thiết kế bước chuyển tiếp sang worker pool có giới hạn. Tuy nhiên, không nên gửi công việc sang executor rồi trả về handler ngay nếu binder ghi nhận message đã xử lý trước khi worker hoàn tất. Khi đó message có thể được acknowledge quá sớm. Cần xác định rõ ranh giới hoàn tất, acknowledgement và retry trước khi tách xử lý bất đồng bộ.

## 5. Quản lý vòng đời bằng SmartLifecycle

Một vòng lặp polling cần bắt đầu và dừng cùng vòng đời Spring ApplicationContext. `SmartLifecycle` phù hợp khi một component phải khởi chạy tác vụ nền sau khi context sẵn sàng và dừng có kiểm soát khi context đóng.

Ví dụ sau dùng một scheduled executor đơn luồng. Mỗi lần poll chỉ có một tác vụ đang chạy; nếu nhận được message thì poll tiếp sớm, nếu queue rỗng thì chờ idle delay, nếu gặp lỗi thì tăng backoff:

```java
@Component
public class ManagedOrderPoller implements SmartLifecycle {

    private static final Logger log =
        LoggerFactory.getLogger(ManagedOrderPoller.class);

    private static final long POLL_TIMEOUT_MS = 500;
    private static final long IDLE_DELAY_MS = 100;
    private static final long MAX_BACKOFF_MS = 30_000;

    private final PollableMessageSource source;
    private final OrderService orderService;

    private final AtomicBoolean running = new AtomicBoolean(false);

    private volatile ScheduledExecutorService executor;
    private volatile ScheduledFuture<?> scheduledTask;
    private int consecutiveFailures;

    public ManagedOrderPoller(
            PollableMessageSource source,
            OrderService orderService) {
        this.source = source;
        this.orderService = orderService;
    }

    @Override
    public synchronized void start() {
        if (!running.compareAndSet(false, true)) {
            return;
        }

        consecutiveFailures = 0;
        executor = Executors.newSingleThreadScheduledExecutor(r -> {
            Thread thread = new Thread(r, "orders-poller");
            thread.setDaemon(true);
            return thread;
        });

        scheduleNext(0);
        log.info("Order poller started");
    }

    private void scheduleNext(long delayMs) {
        if (!running.get()) {
            return;
        }

        ScheduledExecutorService current = executor;
        if (current == null) {
            return;
        }

        try {
            ScheduledFuture<?> next = current.schedule(
                this::pollOnce,
                delayMs,
                TimeUnit.MILLISECONDS
            );
            scheduledTask = next;

            // stop() có thể chạy đồng thời với lúc lên lịch.
            if (!running.get()) {
                next.cancel(false);
            }
        } catch (RejectedExecutionException ex) {
            // Executor có thể đã shutdown trong lúc ứng dụng đang dừng.
            if (running.get()) {
                log.warn("Polling task was rejected while the poller is running", ex);
            }
        }
    }

    private void pollOnce() {
        if (!running.get()) {
            return;
        }

        long nextDelay = IDLE_DELAY_MS;

        try {
            boolean received = source.poll(message -> {
                OrderPlaced event =
                    (OrderPlaced) message.getPayload();

                orderService.handle(event);
            }, POLL_TIMEOUT_MS);

            consecutiveFailures = 0;
            if (received) {
                nextDelay = 0;
            }
        } catch (Exception ex) {
            consecutiveFailures =
                Math.min(consecutiveFailures + 1, 10);

            long multiplier =
                1L << Math.min(consecutiveFailures - 1, 10);

            nextDelay = Math.min(
                MAX_BACKOFF_MS,
                500L * multiplier
            );

            log.warn(
                "Polling failed; retrying after {} ms",
                nextDelay,
                ex
            );
        }

        scheduleNext(nextDelay);
    }

    @Override
    public synchronized void stop() {
        running.set(false);

        ScheduledFuture<?> task = scheduledTask;
        if (task != null) {
            task.cancel(false);
        }

        ScheduledExecutorService current = executor;
        if (current != null) {
            current.shutdown();

            try {
                if (!current.awaitTermination(30, TimeUnit.SECONDS)) {
                    current.shutdownNow();
                }
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                current.shutdownNow();
            }
        }

        log.info("Order poller stopped");
    }

    @Override
    public void stop(Runnable callback) {
        stop();
        callback.run();
    }

    @Override
    public boolean isRunning() {
        return running.get();
    }
}
```

Đây là khung triển khai minh họa. Trong dự án thật, nên đưa poll timeout, idle delay, backoff và shutdown timeout vào cấu hình ứng dụng; bổ sung kiểm tra null/type của payload và metric. Cần bảo đảm bean chỉ có một instance poller cho binding tương ứng, tránh hai component cùng đọc một nguồn ngoài ý muốn.

Điểm quan trọng trong ví dụ:

- `start()` tạo executor một lần và bắt đầu lịch đọc.
- Executor đơn luồng bảo đảm không có hai lần poll chạy đồng thời.
- `scheduleNext()` chỉ lên lịch tác vụ tiếp theo khi poll hiện tại đã kết thúc.
- Khi không có message, poller chờ idle delay thay vì quay vòng liên tục.
- Khi có lỗi, backoff tăng dần và có giới hạn.
- `stop()` đặt cờ dừng, hủy tác vụ tiếp theo và chờ tác vụ đang chạy hoàn tất trong thời gian cho phép.
- `shutdownNow()` chỉ được dùng khi hết thời gian chờ hoặc thread bị interrupt.

Nếu cần restart component sau khi đã gọi `stop()`, ví dụ trên tạo executor mới ở lần `start()` kế tiếp. Trong hệ thống thực tế, cần kiểm tra chính sách restart của lifecycle và tránh gọi `start()` trong khi executor cũ vẫn đang kết thúc.

## 6. Dừng an toàn và xử lý message đang chạy

Dừng an toàn không chỉ là đặt `running = false`. Cần xác định điều gì xảy ra với lần poll đang chờ hoặc handler đang xử lý.

Một quy trình graceful shutdown nên gồm:

1. Ngừng lên lịch poll mới.
2. Để lần poll hiện tại kết thúc hoặc hết timeout.
3. Chờ handler đang chạy hoàn tất trong thời gian shutdown cho phép.
4. Đóng executor và tài nguyên liên quan.
5. Để binder đóng consumer và kết nối theo vòng đời của Spring.

Trong ví dụ, `cancel(false)` hủy tác vụ đã lên lịch nhưng không ngắt ngang tác vụ đang chạy. `executor.shutdown()` ngăn nhận tác vụ mới và cho phép tác vụ hiện tại kết thúc. `awaitTermination()` chờ tối đa 30 giây. Nếu handler vượt quá thời gian đó, `shutdownNow()` gửi yêu cầu interrupt; thư viện blocking có thể không phản ứng ngay nếu không hỗ trợ interruption.

Để shutdown có giới hạn thực tế:

- Đặt connect/read/request timeout cho client nghiệp vụ.
- Không dùng thao tác chờ vô hạn trong handler.
- Đặt shutdown timeout lớn hơn thời gian xử lý thông thường nhưng vẫn phù hợp thời gian orchestrator cho phép.
- Ghi log message ID đang xử lý nếu có thể, để hỗ trợ điều tra sau khi dừng.
- Thiết kế handler idempotent vì message có thể được giao lại nếu xử lý chưa được xác nhận.

Không nên đánh dấu message hoàn tất chỉ vì vòng lặp đã thoát. Việc xác nhận message phụ thuộc binder và broker. Nếu process bị kill đột ngột, broker có thể giao lại message chưa được acknowledge hoặc consumer có thể đọc lại từ offset chưa commit.

## 7. Exception, retry và backoff

Khi handler ném exception, không nên bắt rồi bỏ qua để poller tiếp tục như thể message đã thành công. Exception cần được truyền ra khỏi handler để cơ chế retry/error handling của binder có cơ hội xử lý.

Ví dụ:

```java
private void handle(Message<?> message) {
    OrderPlaced event =
        (OrderPlaced) message.getPayload();

    // Nếu xử lý thất bại, để exception truyền ra.
    orderService.handle(event);
}
```

Cần phân biệt hai loại retry:

- **Retry trong một lần poll**: cơ chế retry được cấu hình cho pollable consumer có thể thử lại handler theo chính sách của Spring Cloud Stream/binder.
- **Retry vòng polling**: sau khi lần poll thất bại hoặc broker lỗi, vòng lặp chờ backoff rồi thực hiện poll tiếp.

Hai cơ chế không thay thế nhau. Retry handler không nhất thiết khắc phục lỗi kết nối broker; vòng polling không nên lặp tức thì một message độc hại gây lỗi vĩnh viễn.

Chính sách retry nên xác định số lần thử, backoff, loại exception được retry và cách đưa message lỗi vào DLQ nếu binder hỗ trợ. Hành vi requeue, acknowledgement và DLQ khác nhau giữa Kafka, RabbitMQ và Pulsar. Không suy luận rằng pollable source có cùng semantics giao nhận trên mọi binder.

## 8. Giới hạn concurrency và luồng thực thi

Một poller đơn luồng là lựa chọn dễ kiểm soát khi thứ tự xử lý hoặc acknowledgement cần rõ ràng. Nếu cần throughput cao hơn, có thể tăng số poller hoặc chuyển xử lý sang worker pool, nhưng cần cân nhắc:

- Nhiều poller cùng đọc một binding có thể tạo cạnh tranh nhận message và thay đổi thứ tự xử lý.
- Với Kafka, partition và consumer group quyết định mức song song; tăng thread tùy ý không vượt qua số partition có thể được gán cho group.
- Với RabbitMQ, số consumer, prefetch và acknowledgement ảnh hưởng tới số message đang xử lý.
- Với Pulsar, subscription type và số partition ảnh hưởng tới cách phân phối message.
- Nếu handler trả về trước khi worker hoàn tất, binder có thể ghi nhận xử lý thành công quá sớm tùy cách handoff.

Nếu cần xử lý song song, hãy sử dụng executor có giới hạn, xác định rõ ai chờ kết quả và cách lỗi được truyền ngược tới poller. Một lựa chọn an toàn là để handler đợi kết quả worker trong thời gian có giới hạn; lựa chọn khác là dùng một kiến trúc handoff có cơ chế lưu trạng thái và acknowledgement riêng. Không gửi message sang thread nền rồi bỏ qua kết quả.

## 9. Trạng thái xử lý, idempotency và acknowledgement

Một message có thể được nhận, xử lý nghiệp vụ, cập nhật database rồi mới được broker ghi nhận là đã tiêu thụ. Nếu ứng dụng lỗi giữa các bước, message có thể được giao lại. Do đó, handler cần xử lý lặp an toàn.

Ví dụ dùng event ID:

```java
@Service
public class OrderService {

    private final ProcessedEventRepository processedEvents;
    private final OrderRepository orders;

    public OrderService(
            ProcessedEventRepository processedEvents,
            OrderRepository orders) {
        this.processedEvents = processedEvents;
        this.orders = orders;
    }

    @Transactional
    public void handle(OrderPlaced event) {
        if (processedEvents.existsById(event.eventId())) {
            return;
        }

        orders.apply(event);
        processedEvents.save(
            new ProcessedEvent(event.eventId())
        );
    }
}
```

Ví dụ giả định cập nhật đơn hàng và ghi event ID đã xử lý nằm trong cùng transaction database, đồng thời event ID có unique constraint. Nếu hai instance có thể xử lý cùng event đồng thời, cần dựa vào ràng buộc duy nhất và xử lý xung đột một cách rõ ràng, không chỉ dựa vào thao tác kiểm tra trước khi ghi.

Không nên tự xác nhận message thủ công nếu binder đang quản lý acknowledgement. Với một số binder, acknowledgement mode và API ack đặc thù có thể được cấu hình, nhưng phải theo tài liệu binder. PollableMessageSource không tạo ra một cơ chế ack chung giống nhau cho mọi broker.

## 10. Giám sát lịch đọc và vòng đời

Một poller production cần có metric để biết nó đang hoạt động, đang chờ hay bị lỗi. Nên theo dõi:

| Metric/log | Mục đích |
|---|---|
| Số lần poll | Xác nhận vòng đọc còn chạy |
| Số lần poll có message | Đo hoạt động nhận dữ liệu |
| Số lần poll rỗng | Hiểu tải và điều chỉnh idle delay |
| Thời gian một lần poll | Phát hiện handler chậm hoặc broker latency |
| Số lỗi và thời gian backoff | Phát hiện broker/service mất ổn định |
| Số message xử lý thành công/thất bại | Theo dõi kết quả nghiệp vụ |
| Số message đang xử lý khi shutdown | Đánh giá drain và timeout |
| Consumer lag/queue depth/backlog | Đánh giá khả năng bắt kịp dữ liệu |

Log nên có event ID, correlation ID và tên binding nếu metadata sẵn có. Tránh ghi payload đầy đủ khi có thông tin nhạy cảm. Metric cần tách lỗi broker, lỗi conversion và lỗi nghiệp vụ nếu có thể để vận hành biết điểm cần xử lý.

## 11. Kiểm thử lịch poll và shutdown

Có thể chia kiểm thử thành nhiều tầng:

1. **Unit test handler**: kiểm tra payload hợp lệ, lỗi nghiệp vụ và idempotency.
2. **Unit test poller**: dùng mock `PollableMessageSource` để xác minh timeout, kết quả `true/false`, backoff và không lên lịch poll mới sau khi stop.
3. **Lifecycle test**: khởi động context, xác minh poller chạy; đóng context và xác minh executor dừng trong giới hạn.
4. **Integration test với broker**: gửi message, tạm dừng consumer, gửi thêm message rồi restart cùng group để kiểm tra backlog và redelivery.
5. **Failure test**: làm handler ném exception, ngắt broker hoặc giữ service chậm để kiểm tra retry, timeout và shutdown.
6. **Load test**: tăng tốc độ phát message để đánh giá queue, concurrency, thời gian xử lý và khả năng bắt kịp.

Test Binder hữu ích để kiểm tra wiring và logic message trong bộ nhớ, nhưng không mô phỏng đầy đủ durability, offset, acknowledgement, redelivery hoặc hành vi shutdown của broker thật. Các thuộc tính này cần integration test với Kafka, RabbitMQ hoặc Pulsar tương ứng.

## 12. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Poll trong vòng lặp không có timeout hoặc delay | Busy loop, CPU tăng khi queue rỗng | Dùng poll timeout, idle delay hoặc scheduler |
| Chạy vòng lặp vô hạn trong ApplicationRunner | Cản trở hoàn tất startup và khó quản lý lifecycle | Dùng component nền có lifecycle rõ ràng |
| Tạo executor mới mỗi lần poll | Rò rỉ thread và khó giới hạn tài nguyên | Dùng executor được quản lý theo vòng đời component |
| Cho phép nhiều poll chạy đồng thời ngoài ý muốn | Cạnh tranh nhận, khó kiểm soát thứ tự và ack | Dùng scheduler đơn luồng hoặc khóa điều phối |
| Bắt exception rồi bỏ qua | Message có thể bị xem là xử lý thành công | Để lỗi truyền tới binder/error handling |
| Dừng ngay bằng interrupt | Handler hoặc thư viện blocking có thể bị cắt giữa chừng | Dừng nhận mới, chờ tác vụ hiện tại, đặt timeout |
| Gửi sang worker rồi trả về ngay | Ack có thể xảy ra trước khi nghiệp vụ hoàn tất | Chờ kết quả hoặc thiết kế handoff có trạng thái |
| Không dùng idempotency | Message giao lại có thể gây cập nhật lặp | Dùng event ID và transaction/unique constraint |

## 13. Checklist triển khai

- Dùng `PollableMessageSource` khi ứng dụng cần chủ động quyết định thời điểm nhận message và binder hỗ trợ mô hình này.
- Chọn poll timeout, idle delay và error backoff riêng biệt.
- Chạy poller trên thread/executor được quản lý, không chặn thread khởi động hoặc request.
- Bảo đảm các lần poll không chồng lấn nếu thiết kế yêu cầu xử lý tuần tự.
- Giữ handler đồng bộ tới khi kết quả xử lý được xác định, hoặc thiết kế handoff có kiểm soát ack.
- Để exception đi qua cơ chế retry/error handling đã cấu hình.
- Đặt timeout cho thao tác blocking và giới hạn thời gian shutdown.
- Dừng lịch poll mới trước, sau đó chờ handler đang chạy hoàn tất.
- Thiết kế idempotent để chịu được redelivery.
- Theo dõi poll rate, lỗi, thời gian xử lý, backlog và consumer lag.
- Kiểm thử pause, restart, handler failure và shutdown với broker thật.

## 14. Tài liệu tham khảo

- [Spring Cloud Stream Reference — Pollable Message Source](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/overview-pollable-consumers.html), phần pollable consumers và `PollableMessageSource`.
- [Spring Framework Reference — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html), phần quản lý tác vụ nền và scheduler.
- [Spring Framework API — SmartLifecycle](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/SmartLifecycle.html), vòng đời start/stop và callback khi dừng.

Quản lý consumer chủ động đòi hỏi ứng dụng kiểm soát lịch poll, thread thực thi và quá trình shutdown. Dùng timeout để tránh busy loop, executor đơn luồng để tránh poll chồng lấn, backoff khi lỗi và lifecycle để dừng có kiểm soát. Quan trọng nhất, chỉ xem message hoàn tất khi handler đã xử lý xong theo semantics của binder; thiết kế idempotent và kiểm thử với broker thật giúp hệ thống phục hồi an toàn sau pause, restart hoặc lỗi đột ngột.

