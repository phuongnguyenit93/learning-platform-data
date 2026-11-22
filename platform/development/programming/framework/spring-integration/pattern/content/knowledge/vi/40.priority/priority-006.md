# Không để priority starvation trong Spring Integration

## 1. Bài toán: ưu tiên cao liên tục khiến yêu cầu thường không bao giờ được xử lý

Một dịch vụ xử lý đơn hàng có ba loại sự kiện:

- **HIGH**: hủy giao dịch rủi ro, chặn đơn hàng gian lận, xử lý cảnh báo quan trọng.
- **NORMAL**: cập nhật trạng thái đơn hàng, xác nhận thanh toán.
- **LOW**: đồng bộ báo cáo, cập nhật chỉ số thống kê và tác vụ bảo trì.

Hệ thống dùng một `PriorityChannel` để lấy thông điệp có độ ưu tiên cao trước. Trong ngày cao điểm, sự kiện HIGH xuất hiện nhanh đến mức khi consumer hoàn tất một tác vụ thì lại có HIGH mới chờ sẵn. Những message LOW vẫn nằm trong channel, không báo lỗi, nhưng **không bao giờ đến lượt**.

Đây là **priority starvation** (*đói tài nguyên do ưu tiên*): một nhóm công việc hợp lệ bị trì hoãn vô hạn hoặc quá lâu vì scheduler liên tục phục vụ nhóm khác có ưu tiên cao hơn. Nó khác với việc message bị lỗi hoặc bị mất; message có thể tồn tại bền vững nhưng **không tiến triển**.

Trong module `SPRING_INTEGRATION_PATTERN`, mục tiêu của Enterprise Integration Patterns là tổ chức Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel và correlation thành các luồng message ít phụ thuộc, dễ mở rộng. Để luồng ưu tiên hoạt động đáng tin cậy, cần kết hợp **ưu tiên nghiệp vụ** với **công bằng, giới hạn chờ và quan sát được**.

### Mục tiêu bài học

Sau bài này, bạn có thể:

1. Giải thích vì sao `PriorityChannel` mặc định có thể gây starvation dù hoạt động đúng thiết kế.
2. Phân biệt **priority ordering**, **FIFO**, **fairness**, **aging**, **backpressure** và **guarantee về độ trễ**.
3. Thiết kế luồng sử dụng nhiều `QueueChannel` và weighted round-robin để bảo đảm LOW có cơ hội xử lý.
4. Hiểu giới hạn của custom `Comparator<Message<?>>` và việc không thể chỉ dựa vào đồng hồ để aging một priority heap đã chứa phần tử.
5. Thiết kế retry, error channel, poison-message handling, idempotency và durable handoff mà không tái tạo starvation.
6. Viết kiểm thử tải liên tục và theo dõi age/lag theo từng mức ưu tiên trong production.

## 2. PriorityChannel thực sự làm gì?

`PriorityChannel` là một `PollableChannel` của Spring Integration. Thay vì lấy message chỉ theo thứ tự vào queue như một hàng đợi FIFO thông thường, channel này ưu tiên message theo **header `priority`** hoặc một comparator được cấu hình.

Ví dụ:

~~~java
@Configuration
@EnableIntegration
class PriorityChannelConfiguration {
    @Bean("priorityInput")
    PollableChannel priorityInput() {
        return new PriorityChannel(200);
    }
}
~~~

Gửi message với độ ưu tiên khác nhau:

~~~java
Message<String> urgent = MessageBuilder.withPayload("CANCEL_RISKY_ORDER")
        .setHeader("priority", 9)
        .setHeader("businessEventId", "E-HIGH-01")
        .build();

Message<String> regular = MessageBuilder.withPayload("UPDATE_REPORT")
        .setHeader("priority", 1)
        .setHeader("businessEventId", "E-LOW-01")
        .build();

priorityInput.send(regular);
priorityInput.send(urgent);

// Trong cấu hình mặc định, urgent có thể được lấy trước regular,
// dù regular đã đến trước.
Message<?> first = priorityInput.receive(0);
~~~

Trong các phiên bản Spring Integration thông dụng, độ ưu tiên được lấy từ header `priority`; **giá trị lớn hơn được ưu tiên hơn**. Có thể truyền `Comparator<Message<?>>` để thay đổi cách xếp thứ tự:

~~~java
@Bean("customPriorityInput")
PollableChannel customPriorityInput() {
    Comparator<Message<?>> comparator = (left, right) -> {
        int p1 = ((Number) left.getHeaders()
                .getOrDefault("priority", 0)).intValue();
        int p2 = ((Number) right.getHeaders()
                .getOrDefault("priority", 0)).intValue();
        return Integer.compare(p2, p1); // Priority cao lên trước.
    };
    return new PriorityChannel(200, comparator);
}
~~~

**Cần phân biệt:** cấu hình `PriorityChannel` quyết định cách chọn *message tiếp theo*, không định nghĩa một cơ chế tránh starvation. Nếu HIGH liên tục được đưa vào trước mỗi lần consumer poll, LOW có thể chờ mãi.

> Không giả định hai message có cùng priority luôn được xử lý theo FIFO chỉ vì cùng header. Với queue sắp xếp theo comparator, thứ tự khi comparator trả về `0` có thể không ổn định; nếu cần FIFO trong cùng mức, phải có cơ chế thứ tự phụ hoặc dùng hàng đợi FIFO riêng cho từng lớp.

### Priority không phải một SLA

Nếu business định nghĩa “HIGH được xử lý sớm hơn LOW”, đó là **thứ tự tương đối**. Nếu business định nghĩa “LOW được xử lý trong tối đa 60 giây”, đó là **cam kết thời gian chờ**. Một strict priority queue có thể làm tốt điều thứ nhất nhưng không đủ để bảo đảm điều thứ hai.

## 3. Chứng minh starvation bằng một ví dụ hữu hạn

Giả sử mỗi lần consumer chuẩn bị nhận một message, producer lại đưa vào một HIGH:

~~~text
T0: enqueue LOW-1
T1: enqueue HIGH-1  -> receive HIGH-1
T2: enqueue HIGH-2  -> receive HIGH-2
T3: enqueue HIGH-3  -> receive HIGH-3
...
Tn: enqueue HIGH-n  -> receive HIGH-n

LOW-1: vẫn nằm trong hàng đợi ở mọi thời điểm.
~~~

Đây không phải lỗi mất message. Scheduler liên tục lựa chọn công việc ưu tiên cao theo quy tắc đã đặt ra.

### Kiểm thử nhỏ để tái hiện

~~~java
@Test
void continuousHighPriorityTrafficCanDelayLowForever() {
    PriorityChannel channel = new PriorityChannel(100);

    channel.send(MessageBuilder.withPayload("LOW")
            .setHeader("priority", 1).build());

    for (int i = 0; i < 50; i++) {
        channel.send(MessageBuilder.withPayload("HIGH-" + i)
                .setHeader("priority", 9).build());

        Message<?> received = channel.receive(0);
        assertNotNull(received);
        assertTrue(received.getPayload().toString().startsWith("HIGH-"));
    }

    Message<?> remaining = channel.receive(0);
    assertNotNull(remaining);
    assertEquals("LOW", remaining.getPayload());
}
~~~

Vòng lặp hữu hạn cho thấy mỗi lần HIGH mới xuất hiện trước khi poll, LOW vẫn bị bỏ lại. Trong production, nếu HIGH tiếp tục đến không có điểm dừng, thời gian chờ của LOW có thể không có giới hạn.

### Góc nhìn năng lực xử lý

Gọi:

- `λ_H`: tốc độ đến của HIGH (message/giây).
- `λ_L`: tốc độ đến của LOW.
- `μ`: năng lực xử lý tổng, khi chi phí xử lý mỗi message gần tương đương.

Nếu `λ_H ≥ μ` và consumer luôn chọn HIGH trước, LOW có thể **không nhận được suất phục vụ** dù hệ thống vẫn xử lý được nhiều message mỗi giây. Ngay cả khi `λ_H < μ`, các đợt HIGH lớn hoặc thời gian xử lý biến động vẫn có thể làm LOW vượt thời gian chờ cho phép.

Nếu `λ_H + λ_L > μ` kéo dài, **không thuật toán chia lượt nào khiến toàn bộ backlog ổn định** khi năng lực không đổi. Fairness chỉ phân bổ tài nguyên khan hiếm; vẫn cần scale, giới hạn tốc độ nhận hoặc loại bỏ tác vụ không thiết yếu theo chính sách.

## 4. Phân biệt starvation với các vấn đề khác

| Hiện tượng | Dấu hiệu | Không nên nhầm với |
| --- | --- | --- |
| **Priority starvation** | Queue LOW còn message nhưng gần như không có lần dequeue; tuổi của message cũ nhất tăng. | Mất message do crash. |
| **Head-of-line blocking** | Một message chậm/lỗi giữ điểm xử lý khiến message sau chờ dù scheduler đã chọn. | Bản thân so sánh priority sai. |
| **Priority inversion** | Tác vụ HIGH phải chờ tài nguyên/lock do tác vụ LOW giữ. | Starvation của LOW do HIGH chiếm scheduler. |
| **Capacity starvation** | Queue/broker đầy vì HIGH; LOW bị reject ngay khi enqueue. | LOW đã được nhận nhưng không đến lượt xử lý. |
| **Retry starvation** | Một message lỗi được retry liên tục ở priority cao, chiếm các suất xử lý. | Lượng sự kiện HIGH hợp lệ tự nhiên tăng. |
| **Tenant starvation** | Một khách hàng/tenant sinh rất nhiều công việc, tenant khác chờ mãi. | Chỉ có hai nhóm HIGH/LOW. |

Một hệ thống có thể gặp nhiều hiện tượng đồng thời. Ví dụ, retry HIGH không giới hạn làm queue HIGH luôn có message, khiến LOW bị starvation và đồng thời tăng error rate.

## 5. Các chiến lược chống starvation

| Giải pháp | Nguyên lý | Ưu điểm | Giới hạn |
| --- | --- | --- | --- |
| **Weighted round-robin (WRR)** | Luân phiên lấy message từ nhiều queue theo tỷ lệ đã chọn. | Dễ giải thích, bảo đảm suất phục vụ theo **số message** nếu scheduler tiến triển. | Chưa cân bằng thời gian CPU nếu thời gian xử lý mỗi lớp khác nhau. |
| **Aging** | Tăng độ ưu tiên hiệu dụng khi message chờ lâu. | Message cũ dần được đẩy lên trước. | Cần cấu trúc dữ liệu/scheduler thực sự đánh giá lại thứ tự; giới hạn bonus có thể không đủ. |
| **Oldest-first override / deadline** | Khi message vượt ngưỡng tuổi, dành lượt cho nó bất kể priority thông thường. | Gắn trực tiếp với mục tiêu tuổi chờ. | Không thể cam kết thời gian tuyệt đối khi worker bị treo hoặc nguồn quá tải. |
| **Reserved capacity** | Dành worker hoặc quota tối thiểu cho LOW/NORMAL. | Cô lập khả năng tiến triển của lớp ít ưu tiên. | Có thể để capacity nhàn rỗi nếu không có work stealing. |
| **Admission control / backpressure** | Hạn chế luồng HIGH và gửi trả tín hiệu quá tải. | Ngăn backlog tăng vô hạn; có thể bảo vệ tài nguyên chung. | Cần quy tắc nghiệp vụ cho retry, reject hoặc degrade. |
| **Rate limiting theo nguồn/tenant** | Giới hạn producer chiếm dụng queue hoặc downstream. | Ngăn một nguồn gây đói cho toàn hệ thống. | Phải có khóa nhận diện nguồn và cơ chế chống né giới hạn. |
| **Deficit round-robin / weighted fair queuing** | Cấp credit theo trọng số và chi phí xử lý ước lượng. | Công bằng hơn khi message có kích thước/chi phí khác nhau. | Phức tạp hơn WRR; cần biết hoặc đo chi phí. |

Trong nhiều hệ thống nghiệp vụ, **nhiều queue FIFO + scheduler theo trọng số + giới hạn tuổi chờ + backpressure** là điểm khởi đầu dễ kiểm thử hơn một comparator động duy nhất.

## 6. Cách 1 — Chia message thành HIGH, NORMAL, LOW

Thay vì đẩy mọi loại message vào một `PriorityChannel` strict priority, sử dụng một `Router` để phân loại và gửi tới ba `QueueChannel`. Mỗi queue xử lý **FIFO trong chính lớp của nó**.

~~~mermaid
flowchart LR
    A["Gateway / Inbound adapter"] --> B["Validate + Transformer"]
    B --> R{"Priority Router"}
    R --> H["highQueue: FIFO"]
    R --> N["normalQueue: FIFO"]
    R --> L["lowQueue: FIFO"]
    H --> W["Weighted Fair Dispatcher"]
    N --> W
    L --> W
    W --> D["DirectChannel"]
    D --> S["Service Activator / DB"]
    S --> E["Completion / metrics"]
~~~

Một ví dụ cấu hình channel:

~~~java
@Configuration
@EnableIntegration
@EnableScheduling
class FairChannelConfiguration {

    @Bean("highQueue")
    PollableChannel highQueue() {
        return new QueueChannel(500);
    }

    @Bean("normalQueue")
    PollableChannel normalQueue() {
        return new QueueChannel(500);
    }

    @Bean("lowQueue")
    PollableChannel lowQueue() {
        return new QueueChannel(500);
    }

    @Bean("processingInput")
    DirectChannel processingInput() {
        return new DirectChannel();
    }
}
~~~

Đây là **bài thực hành trên RAM**, không phải kiến trúc đảm bảo không mất dữ liệu khi ứng dụng crash. `QueueChannel` mặc định không có lưu trữ bền vững, và việc dequeue khỏi RAM không được rollback cùng JDBC.

### Định nghĩa priority ở ranh giới nhận

Không nên tin mọi giá trị `priority` do client bên ngoài tự gửi. Ví dụ, một client không có quyền gán HIGH cho hàng nghìn message báo cáo sẽ phá vỡ quota. Hãy chuẩn hóa và phân loại trong service:

~~~java
enum WorkClass {
    HIGH, NORMAL, LOW
}

record WorkItem(
        String eventId,
        String tenantId,
        String type,
        Instant submittedAt) {}

static WorkClass classify(WorkItem item) {
    return switch (item.type()) {
        case "FRAUD_ALERT", "RISK_CANCELLATION" -> WorkClass.HIGH;
        case "ORDER_CONFIRMED", "PAYMENT_RECEIVED" -> WorkClass.NORMAL;
        default -> WorkClass.LOW;
    };
}
~~~

Việc phân loại **theo quy tắc nghiệp vụ tin cậy** còn giúp ngăn tình huống tất cả producer tự gắn HIGH và khiến mô hình priority mất ý nghĩa.

## 7. Cách 2 — Weighted round-robin với suất dành riêng cho LOW

Thay vì “lúc nào cũng HIGH trước”, đặt chu kỳ phục vụ như sau:

~~~text
HIGH, HIGH, HIGH, HIGH, NORMAL, NORMAL, LOW
  1     2     3     4       5       6      7
  |_________________ một chu kỳ ______________|
~~~

Nếu **cả ba queue đều liên tục có việc**, cứ mỗi bảy lần chọn message, LOW được một lượt, NORMAL được hai lượt và HIGH được bốn lượt. Tỷ lệ theo **số tác vụ** là 4:2:1, không phải cam kết phân bổ thời gian CPU tuyệt đối.

Khi một queue trống, scheduler có thể **work-conserving**: lấy message từ queue khác thay vì để worker nhàn rỗi. Khi LOW trở lại có việc, lượt LOW tiếp theo vẫn xuất hiện vì vị trí trong lịch được duy trì.

### Java: bộ điều phối một worker, dễ kiểm thử

~~~java
@Component
class WeightedFairDispatcher {
    // 4 suất HIGH, 2 suất NORMAL, 1 suất LOW.
    private static final int[] SCHEDULE = {0, 0, 0, 0, 1, 1, 2};

    private final PollableChannel[] input;
    private final MessageChannel processingInput;
    private int nextSlot;

    WeightedFairDispatcher(
            @Qualifier("highQueue") PollableChannel high,
            @Qualifier("normalQueue") PollableChannel normal,
            @Qualifier("lowQueue") PollableChannel low,
            @Qualifier("processingInput") MessageChannel processingInput) {
        this.input = new PollableChannel[]{high, normal, low};
        this.processingInput = processingInput;
    }

    // Được @Scheduled gọi định kỳ; public để test gọi trực tiếp.
    @Scheduled(fixedDelay = 50)
    public synchronized void scheduledTick() {
        dispatchOnce();
    }

    public synchronized boolean dispatchOnce() {
        // Nếu queue ứng với slot hiện tại trống, thử các slot kế tiếp.
        for (int offset = 0; offset < SCHEDULE.length; offset++) {
            int slot = (nextSlot + offset) % SCHEDULE.length;
            PollableChannel candidate = input[SCHEDULE[slot]];
            Message<?> message = candidate.receive(0); // Non-blocking.

            if (message == null) {
                continue;
            }

            nextSlot = (slot + 1) % SCHEDULE.length;

            // DirectChannel -> handler đồng bộ trong thread scheduler.
            boolean accepted = processingInput.send(message);
            if (!accepted) {
                throw new IllegalStateException(
                        "Processing channel rejected message");
            }
            return true;
        }

        // Không có queue nào có việc; tránh cố định con trỏ.
        nextSlot = (nextSlot + 1) % SCHEDULE.length;
        return false;
    }
}
~~~

Giải thích một vòng lặp:

1. `nextSlot` xác định suất dự kiến theo dãy trọng số.
2. `receive(0)` thử lấy message mà **không chờ** ở một queue rỗng.
3. Nếu queue trống, tìm suất tiếp theo để tận dụng capacity hiện có.
4. Khi lấy được message, cập nhật con trỏ **trước khi xử lý** để lần sau tiếp tục chu kỳ.
5. `processingInput` là `DirectChannel` nên handler được gọi đồng bộ. Thời gian handler xử lý quyết định tốc độ scheduler có thể tiến.

**Guarantee có điều kiện:** Nếu scheduler tiếp tục được chạy, mỗi lần dispatch hoàn tất trong thời gian hữu hạn, và LOW liên tục có việc, thì khi các queue khác cũng luôn có việc, LOW có **ít nhất một cơ hội trong mỗi vòng bảy lần chọn**. Điều này không tự tạo giới hạn 60 giây nếu một handler mất hàng phút hoặc worker bị treo.

**Phân biệt tiến triển với backlog ổn định:** Nếu cả ba queue luôn có việc, một phần bảy suất chọn dành cho LOW. Khi tốc độ đến của LOW cao hơn năng lực xử lý dành cho một phần bảy suất đó trong thời gian dài, backlog và thời gian chờ LOW vẫn tăng, dù LOW không còn bị bỏ đói tuyệt đối. Muốn ổn định, cần tăng trọng số/capacity cho LOW, giảm tải nhận vào hoặc áp dụng quota và backpressure; nếu thời gian xử lý mỗi loại khác nhau, phải tính theo **thời gian phục vụ** thay vì chỉ đếm message.

### Tại sao không gắn @Scheduled lên từng queue độc lập?

Ba poller độc lập chạy chung pool có thể tạo fairness **ngẫu nhiên**, đặc biệt khi pool nhỏ và handler HIGH luôn chiếm thread. Nếu muốn quota 4:2:1, phải có **bộ điều phối chung**, worker pool được phân vùng, hoặc một scheduling mechanism hỗ trợ quota thực sự. Chỉ tạo ba queue mà không quy định cách cấp lượt **chưa giải quyết starvation**.

### Ví dụ handler phía sau DirectChannel

~~~java
@Service
class WorkHandler {
    public void process(WorkItem work) {
        // Kiểm tra idempotency, chạy nghiệp vụ,
        // và ghi nhận latency/queue wait theo work.type().
    }
}

@Bean
IntegrationFlow processingFlow(WorkHandler handler) {
    return IntegrationFlow.from("processingInput")
            .handle(handler, "process")
            .get();
}
~~~

**Cảnh báo độ tin cậy:** Khi `receive(0)` đã lấy message khỏi `QueueChannel` trong bộ nhớ, nếu handler ném exception, `dispatchOnce()` không tự trả message về queue. Đừng dùng code minh họa này làm mẫu production có yêu cầu **at-least-once**. Với dữ liệu quan trọng, dùng nguồn bền vững và thiết kế dequeue/ACK + transaction/error handling, hoặc lưu công việc vào một durable inbox trước khi xác nhận.

## 8. Kiểm thử fairness dưới luồng HIGH liên tục

Không nên chỉ test “LOW được xử lý khi queue HIGH trống”, vì đó không phải tình huống gây starvation. Phải cho HIGH luôn có sẵn và chứng minh scheduler **vẫn dành suất cho LOW**.

### Unit test thuần channel

~~~java
@Test
void lowPriorityMakesProgressWhileHighHasBacklog() {
    QueueChannel high = new QueueChannel(100);
    QueueChannel normal = new QueueChannel(100);
    QueueChannel low = new QueueChannel(100);
    DirectChannel processing = new DirectChannel();

    List<String> processed = new ArrayList<>();
    processing.subscribe(message ->
            processed.add((String) message.getPayload()));

    for (int i = 0; i < 35; i++) {
        high.send(MessageBuilder.withPayload("H-" + i).build());
    }
    for (int i = 0; i < 14; i++) {
        normal.send(MessageBuilder.withPayload("N-" + i).build());
    }
    for (int i = 0; i < 7; i++) {
        low.send(MessageBuilder.withPayload("L-" + i).build());
    }

    WeightedFairDispatcher dispatcher =
            new WeightedFairDispatcher(high, normal, low, processing);

    for (int i = 0; i < 14; i++) {
        assertTrue(dispatcher.dispatchOnce());
    }

    // Khi ba queue đều không rỗng, hai chu kỳ có hai suất LOW.
    long lowProcessed = processed.stream()
            .filter(value -> value.startsWith("L-"))
            .count();
    assertEquals(2L, lowProcessed);
    assertTrue(processed.subList(0, 7).contains("L-0"));
}
~~~

Test tạo lượng HIGH/NORMAL đủ lớn để các queue còn backlog trong toàn bộ 14 lần xử lý. Với lịch 4:2:1, LOW được chọn ở cuối chu kỳ thứ nhất và thứ hai. Nếu vô tình đổi scheduler thành strict priority, test này sẽ thất bại.

### Property-based/stress test

Với các tải biến động, kiểm thử thêm những thuộc tính:

- LOW pending liên tục và handler luôn kết thúc → số lần dequeue LOW **không đứng yên** qua nhiều chu kỳ.
- Không có LOW → scheduler vẫn dùng được phần lớn capacity cho HIGH/NORMAL.
- Khi LOW trở lại → không phải chờ HIGH rỗng mới được xử lý.
- Khi HIGH tạm ngừng → NORMAL/LOW tận dụng worker mà không bị bỏ đói vô lý.
- Retry HIGH liên tục → vẫn có ngân sách dành cho message LOW hợp lệ.
- Nhiều producer/tenant cùng vào queue → một tenant không chiếm mọi slot của lớp priority.

Unit test theo số lần chọn giúp xác minh thuật toán; integration test với broker, database và worker thực giúp xác minh **latency, ACK, durability và concurrency**.

## 9. Cách 3 — Aging: tăng ưu tiên theo thời gian chờ

Aging làm message ít ưu tiên trở nên “đáng được xử lý sớm hơn” khi nó đã nằm trong queue quá lâu.

Một công thức minh họa:

~~~text
effectivePriority(t)
    = basePriority
      + floor((t - originalEnqueueTime) / agingStep)

Ví dụ:
  basePriority LOW = 1
  agingStep = 10 giây
  LOW chờ 40 giây -> effectivePriority = 5
~~~

Để LOW sau một khoảng chờ có thể vượt một HIGH mới đến, **mức tăng phải đủ** hoặc phải có quy tắc ưu tiên deadline/tuổi chờ. Nếu tăng tối đa 2 điểm trong khi HIGH luôn đạt 100, LOW vẫn có thể starve.

### Cạm bẫy: comparator dựa trên đồng hồ không tự làm heap đảo thứ tự

Một ý tưởng có vẻ hợp lý nhưng **không nên áp dụng trực tiếp**:

~~~java
Comparator<Message<?>> dynamicComparator = (a, b) -> {
    long now = System.currentTimeMillis();
    int aScore = basePriority(a) + ageBonus(a, now);
    int bScore = basePriority(b) + ageBonus(b, now);
    return Integer.compare(bScore, aScore);
};
~~~

Đối với priority heap/queue, comparator thường được gọi khi **chèn, lấy hoặc tái sắp xếp phần tử**; queue không có nghĩa vụ tự đánh giá lại mọi message mỗi khi đồng hồ chạy. Một message tăng điểm theo thời gian **không chắc tự nổi lên đầu heap**. Comparator có thứ tự thay đổi theo thời gian còn làm việc suy luận thứ tự queue khó ổn định.

**Cách đáng tin cậy hơn** là:

1. Lưu `originalEnqueueTime` bền vững.
2. Có tác vụ định kỳ **promote** các message quá tuổi sang lớp priority cao hơn, hoặc scheduler duyệt/claim các message theo effective priority tại thời điểm chọn.
3. Chuyển lớp theo thao tác an toàn, có transaction hoặc cơ chế ACK/retry nếu nguồn bền vững.
4. Giữ `eventId`, `originalEnqueueTime` và số lần attempt khi chuyển; không biến message cũ thành message nghiệp vụ mới.
5. Kiểm thử cùng lượng HIGH liên tục để xác nhận message được promote **thực sự đến lượt**.

Ví dụ chính sách:

| Tuổi chờ kể từ lần enqueue ban đầu | Hành động |
| --- | --- |
| Dưới 15 giây | Giữ lớp priority gốc. |
| 15–45 giây | Tăng class một bậc hoặc cấp lượt riêng cho tác vụ cũ. |
| Trên 45 giây | Đưa vào diện phải ưu tiên xử lý theo deadline nếu nguồn và tài nguyên cho phép. |
| Trên 60 giây | Cảnh báo vi phạm SLO, tăng capacity/escalate; không hứa tự động được xử lý nếu tài nguyên đã tê liệt. |

Nếu scheduler WRR đã bảo đảm LOW tiến triển theo tỷ lệ nhưng vẫn chưa đáp ứng **độ trễ lớn nhất**, hãy kết hợp aging hoặc oldest-first override thay vì chỉ tăng trọng số vô hạn.

## 10. Cách 4 — Bảo vệ deadline và độ tuổi message

Một hệ thống có thể định nghĩa:

~~~text
HIGH: ưu tiên độ trễ thấp, p99 queue wait <= 2 giây
NORMAL: p99 queue wait <= 10 giây
LOW: p99 queue wait <= 60 giây
~~~

Các số trên chỉ là **ví dụ SLO**, không phải đặc tính mặc định của Spring Integration. Để vận hành, cần theo dõi:

- **Queue wait**: từ lúc message được nhận bền vững đến khi bắt đầu xử lý.
- **End-to-end latency**: từ lúc business event được tạo đến khi side effect nghiệp vụ commit.
- **Oldest pending age**: tuổi của message đang chờ lâu nhất trong từng class.
- **Deadline miss rate**: tỷ lệ message vượt deadline.
- **Time since last completed LOW**: thời gian kể từ lần gần nhất LOW tiến triển.

Một thuật toán override có thể là:

~~~text
each scheduling decision:
  if oldest LOW waiting >= threshold:
      choose LOW, provided processing resources available
  else if oldest NORMAL waiting >= threshold:
      choose NORMAL
  else:
      follow weighted schedule 4:2:1
~~~

Khi nhiều lớp cùng quá hạn, phải định nghĩa thứ tự rõ (ví dụ deadline sớm nhất trước, hoặc ràng buộc nghiệp vụ không được trì hoãn HIGH rủi ro). **Không** dùng một ngưỡng duy nhất như `LOW > 30s` mà không xét khối lượng xử lý; một tác vụ LOW mất 10 phút vẫn có thể làm hệ thống không đạt SLO của HIGH nếu chỉ có một worker.

### Giới hạn toán học

WRR bảo đảm **lượt chọn** dưới giả định scheduler và handler tiến triển, không bảo đảm xử lý hoàn thành trước một mốc thời gian tuyệt đối khi:

- Handler treo hoặc giữ lock vô thời hạn.
- Tổng tốc độ đến liên tục cao hơn năng lực xử lý.
- Một lớp có message xử lý dài bất thường.
- Nguồn lỗi, broker/DB không sẵn sàng, retry kéo dài.
- Bị giới hạn bởi một resource dùng chung (connection pool, CPU, khóa DB, downstream rate limit).

Muốn một SLO chắc chắn hơn, cần **timeout, bulkhead, admission control, worker capacity và theo dõi trực tiếp tuổi chờ**, không chỉ thay comparator.

## 11. Cách 5 — Reserved capacity và bulkhead

Đối với công việc HIGH rất đắt đỏ hoặc nhiều tenant, một scheduler chung vẫn có nguy cơ bị khóa bởi handler dài. Có thể cấp **worker pool riêng** cho nhóm:

~~~mermaid
flowchart LR
    R["Router"] --> H["HIGH Queue"]
    R --> N["NORMAL Queue"]
    R --> L["LOW Queue"]
    H --> HP["HIGH workers: 4"]
    N --> NP["NORMAL workers: 2"]
    L --> LP["LOW worker: 1"]
    HP --> DB[("DB / downstream")]
    NP --> DB
    LP --> DB
~~~

Ví dụ, với bảy worker, dành 4/2/1 worker cho HIGH/NORMAL/LOW. Khi HIGH tràn ngập, một worker LOW vẫn có thể xử lý độc lập, **nếu** downstream chung còn tài nguyên.

Đổi lại:

- Worker LOW có thể nhàn rỗi khi chỉ có HIGH.
- Bảy worker cùng tranh một connection pool nhỏ vẫn có thể làm LOW không tiến triển.
- Nếu downstream có rate limit chung, cần quota/reservation ở **chính downstream**.
- Nếu muốn tận dụng worker trống, cân nhắc work stealing nhưng không được lấy mất **suất tối thiểu** đã hứa cho LOW.

Bulkhead phù hợp khi cần bảo vệ tiến triển của một lớp hoặc tenant bất chấp tải cao của lớp khác. Nó không thay thế backpressure khi tổng tải vượt mức tài nguyên có thể đáp ứng.

## 12. Backpressure và capacity: đừng để LOW bị từ chối ngay từ cửa

Starvation có thể bắt đầu **trước khi scheduler chạy**: queue HIGH chiếm hết capacity bộ nhớ/broker, khiến LOW không enqueue được.

Ví dụ với `QueueChannel` dung lượng hữu hạn:

~~~java
@Bean("lowQueue")
PollableChannel lowQueue() {
    return new QueueChannel(200);
}

boolean accepted = lowQueue.send(message, 250);
if (!accepted) {
    // Queue đầy / quá thời gian chờ.
    // Áp dụng chính sách retry, durable fallback hoặc báo quá tải.
}
~~~

Tùy channel và cấu hình, `send(message, timeout)` có thể chờ capacity tối đa theo timeout rồi trả về thất bại. **Không** đánh đồng send thất bại với message đã được lưu bền vững ở đâu đó.

Các cách bảo vệ capacity:

1. **Giới hạn đầu vào HIGH** theo producer/tenant và loại sự kiện.
2. **Reserve dung lượng hoặc quota** cho LOW/NORMAL thay vì một queue chung bị HIGH chiếm hết.
3. **Chống trùng trước khi enqueue** nếu producer hay retry đang phát nhiều message giống nhau.
4. **Coalesce** message báo cáo có thể gộp được, nhưng chỉ khi domain cho phép bỏ qua các trạng thái trung gian.
5. **Durable fallback/retry** cho công việc quan trọng; không âm thầm drop message khi queue đầy.
6. **Scale worker** hoặc giảm chi phí handler khi arrival rate dài hạn vượt capacity.

Capacity nên được tính theo cả số message, kích thước payload, tuổi backlog và resource tiêu thụ (RAM, DB, connection, broker quotas), không chỉ một số `capacity`.

## 13. Retry và error channel có thể tạo starvation trở lại

Một message HIGH sai schema bị ném lỗi rồi retry ngay lập tức với priority vẫn bằng 9 có thể chiếm hầu hết slot HIGH. Nếu retry vô hạn hoặc broker liên tục redeliver, các message HIGH hợp lệ và LOW đều bị chậm.

### Quy tắc retry hữu hạn

~~~text
Receive event
  -> Validate payload
      -> permanent error: quarantine / DLQ
  -> Process in business transaction
      -> success: commit + acknowledge according to source
      -> transient error: rollback, retry with bounded backoff
      -> retries exhausted: durable error record / DLQ
~~~

Ở đây:

- **Lỗi tạm thời**: DB mất kết nối ngắn, downstream timeout, lock contention; có thể retry với backoff và jitter phù hợp.
- **Lỗi vĩnh viễn**: payload sai schema, event bị cấm, trường bắt buộc thiếu; nên đưa vào vùng lỗi có thể tra cứu.
- **Lỗi không rõ kết quả**: phía nhận có thể đã commit dù caller timeout; dùng `eventId` cố định và idempotency.
- **Retry budget** nên có quota riêng, tránh message retry chiếm toàn bộ suất xử lý của message mới.

### Error channel

Trong Spring Integration, lỗi có thể được chuyển thành `ErrorMessage` và gửi tới một `errorChannel` tùy endpoint. Nhưng việc error flow nhận được lỗi **không chứng minh** transaction đã rollback hoặc broker sẽ redeliver.

| Tình huống | Tác động đối với starvation/delivery |
| --- | --- |
| Handler đồng bộ ném exception về transactional poller. | DB có thể rollback; nguồn có/không redeliver tùy resource và ACK. |
| Handler bắt exception, chỉ log rồi return. | Poller/listener có thể coi message đã xử lý, kể cả khi nghiệp vụ chưa hoàn tất. |
| Error handler retry không giới hạn với priority cao. | Poison message gây retry storm và starvation. |
| Retry được lên lịch vào **delayed queue** riêng. | Giảm việc một message lỗi monopolize scheduler; cần durable retry và hạn chế attempt. |
| Error flow gửi sang DLQ rồi return. | Phải bảo đảm DLQ lưu thành công theo policy trước khi ACK message gốc nếu yêu cầu không mất dữ liệu. |

**Không** dùng `PriorityChannel` RAM + bắt exception rồi `send()` lại một cách vô hạn như một cơ chế redelivery production. Cách này có thể mất message khi process crash, tạo vòng lặp lỗi và làm nhiều lớp khác đói tài nguyên.

## 14. Durable message, transaction và idempotency trong production

Ví dụ WRR ở phần 7 dùng ba queue trong RAM để minh họa thuật toán. Khi sự kiện có giá trị nghiệp vụ, cần một nguồn bền vững:

- **JMS/AMQP**: queue tách theo priority hoặc routing key; mỗi consumer/dispatcher có ACK/redelivery đúng adapter.
- **Kafka**: phân nhóm/topic/partition và tiến độ consumer phù hợp; không thể tùy ý xóa/hợp nhất offset như queue RAM.
- **JDBC-backed MessageStore**: lưu message trong DB với transaction và poller được cấu hình phù hợp.
- **Durable inbox**: nhận message, ghi yêu cầu và metadata vào DB trong transaction trước khi trả success cho inbound.

### Chọn implementation theo bảo đảm

| Cấu hình | Fairness | Khả năng phục hồi | Điều phải thiết kế thêm |
| --- | --- | --- | --- |
| Một `PriorityChannel` RAM strict priority | Không có guarantee cho LOW khi HIGH liên tục. | Mất khi process crash. | Aging/quotas, durable store nếu cần. |
| Ba `QueueChannel` RAM + WRR | Có suất phục vụ theo số lần dispatch nếu scheduler tiến. | Chưa bền vững. | Durable handoff, retry/ACK, idempotency. |
| Nhiều queue bền vững + weighted consumers | Có thể cấp quota/worker riêng. | Tùy store/broker và ACK/transaction. | Rebalance, concurrency, retry, DLQ, monitoring. |
| Một persistent priority store | Có khả năng lưu bền vững và thứ tự theo priority của store. | Tùy store; không đồng nghĩa fairness. | Xử lý starvation tại scheduler hoặc phân lớp. |

Khi dùng message store hỗ trợ priority, phải kiểm tra API và quy tắc sắp xếp **của store**. Theo tài liệu Spring Integration, cấu hình priority channel sử dụng message store yêu cầu implementation `PriorityCapableChannelMessageStore`; tùy cách cấu hình, **không kết hợp comparator/capacity kiểu queue RAM với option message-store**. Không suy rằng custom comparator trên RAM tự áp dụng cho JDBC/Redis/Mongo priority store.

### ACK, transaction và redelivery

Nếu scheduler đã nhận một message từ durable queue nhưng handler chưa commit, sự cố có thể làm message được gửi lại. Ngược lại, nếu scheduler ACK/dequeue commit quá sớm rồi handler lỗi, message có thể bị mất.

Một thiết kế an toàn phải xác định rõ:

1. **Khi nào nhận/claim message?**
2. **Khi nào transaction nghiệp vụ commit?**
3. **Khi nào ACK/offset commit hoặc xóa khỏi durable store?**
4. **Khi crash giữa bước 2 và 3, message có thể lặp không?**
5. **Idempotency** ngăn lặp side effect thế nào?

Ví dụ consumer ghi database:

~~~sql
CREATE TABLE processed_events (
    consumer_name VARCHAR(80) NOT NULL,
    event_id VARCHAR(100) NOT NULL,
    processed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

~~~java
@Transactional
public void handleImportantEvent(WorkItem item) {
    int claimed = jdbc.update("""
            INSERT INTO processed_events(consumer_name, event_id)
            VALUES (?, ?)
            ON CONFLICT (consumer_name, event_id) DO NOTHING
            """, "work-handler", item.eventId());

    if (claimed == 0) {
        return; // Redelivery: đã commit ở lần trước.
    }

    // Ghi nghiệp vụ trong cùng transaction.
    applyBusinessChange(item);
}
~~~

SQL trên minh họa PostgreSQL. Cả marker và side effect JDBC cần cùng transaction. Nếu `applyBusinessChange` lỗi, transaction rollback cả marker. Nếu DB commit nhưng ACK chưa hoàn thành, lần redelivery dùng lại `eventId` nên tránh cập nhật trùng. `correlationId` dùng để theo dõi workflow, không tự thay thế `eventId`.

Nếu xử lý còn phát event mới sang hệ thống khác, cân nhắc **transactional outbox**: ghi event cần gửi cùng business update, relay publish sau commit, consumer downstream idempotent. Outbox giữ ý định gửi bền vững nhưng không bảo đảm broker và DB commit trong một global transaction.

## 15. Công bằng giữa tenant và các lớp priority

Priority starvation không chỉ xảy ra giữa HIGH và LOW. Một tenant A có thể phát 90% HIGH khiến tenant B không đến lượt dù cả hai đều được gắn HIGH.

Mô hình hai cấp:

~~~mermaid
flowchart LR
    A["Messages có tenantId + business priority"] --> P["Router theo class HIGH/NORMAL/LOW"]
    P --> T["Bộ điều phối giữa tenants trong từng class"]
    T --> W["Weighted scheduler giữa các class"]
    W --> H["Workers / business handlers"]
~~~

Đề xuất:

- **Per-tenant quota/token bucket** để một tenant không tạo backlog không giới hạn.
- **Round-robin hoặc deficit round-robin** giữa những tenant có message đang chờ trong cùng priority.
- **Giới hạn đồng thời** theo tenant để một nhóm tác vụ chậm không giữ hết worker.
- **Mức ưu tiên do server xác định**, không cho client tự nâng `priority` vô điều kiện.
- **SLO theo tenant và theo class**; một chỉ số trung bình toàn hệ thống có thể che mất trường hợp tenant nhỏ bị bỏ đói.

Tính công bằng giữa tenant và tính ưu tiên giữa các loại công việc là **hai bài toán độc lập**. Nên mô tả chính sách theo cả hai chiều, thay vì cố nhét mọi quy tắc vào một con số priority.

## 16. Quan sát: đo starvation bằng tín hiệu nào?

Đừng chỉ theo dõi số message được xử lý mỗi giây. Một hệ thống có throughput HIGH rất tốt vẫn có thể bỏ đói LOW.

| Metric | Cách đọc | Hành động khi xấu |
| --- | --- | --- |
| `queue_depth{class}` | Số message còn chờ theo class. | Kiểm tra capacity, tắc consumer hoặc số lượng producer. |
| `oldest_pending_age_seconds{class}` | Tuổi message chờ lâu nhất theo class. | Tìm starvation/poison message, trigger ưu tiên tuổi. |
| `queue_wait_seconds{class}` p95/p99 | Độ trễ từ enqueue đến bắt đầu xử lý. | Điều chỉnh trọng số, worker, admission. |
| `completed_total{class}` | Tiến triển thật sự theo class. | Nếu LOW pending > 0 mà completions không tăng, điều tra ngay. |
| `deadline_miss_total{class}` | Số lần vượt SLO chờ. | Cân nhắc oldest-first override và capacity. |
| `retry_total{class,reason}` | Retry đang tiêu tốn suất phục vụ ra sao. | Điều chỉnh backoff, retry budget, DLQ. |
| `rejected_total{class}` | Message bị từ chối ở cửa vì queue đầy. | Backpressure/fallback; không âm thầm drop. |
| `active_handlers{class}` | Lớp nào đang giữ worker. | Bulkhead, timeout, limit concurrency. |
| `last_progress_timestamp{class}` | Lần gần nhất class có business commit thành công. | Phát hiện queue còn việc nhưng không xử lý. |

**Cảnh báo minh họa:**

~~~text
IF low_pending > 0
AND oldest_low_age > 45s:
    alert("LOW approaching wait-time SLO")

IF low_pending > 0
AND low_completions_last_60s == 0:
    alert("Possible starvation or stalled worker")
~~~

Ngoài ra cần theo dõi:

- **Queue wait tính từ lần enqueue đầu tiên**, không reset khi retry hoặc chuyển từ LOW sang NORMAL.
- **Thời gian xử lý thực** theo class để WRR được hiệu chỉnh nếu HIGH tốn CPU hơn LOW nhiều lần.
- **Consumer lag, broker ACK, transaction rollback, DLQ** đối với nguồn bền vững.
- **Correlation ID và event ID** để tìm message chưa tiến triển và phân biệt duplicate với event mới.
- **Mức ưu tiên gốc và mức ưu tiên hiệu dụng** sau aging để hiểu vì sao một message được chọn.

Không log payload hoặc thông tin nhạy cảm nếu không cần thiết. Một log “receive thành công” không chứng minh business side effect đã commit.

## 17. Kiểm thử nâng cao: lỗi, concurrency và thời gian chờ

| Kịch bản | Kỳ vọng |
| --- | --- |
| HIGH được enqueue liên tục trước mỗi lần poll. | LOW vẫn được dispatch theo ngân sách nếu dùng WRR; strict PriorityChannel có thể trì hoãn vô hạn. |
| Chỉ có HIGH trong hàng đợi. | Scheduler work-conserving không để worker trống vô lý. |
| HIGH/NORMAL trống, LOW có việc. | LOW dùng toàn bộ khả năng xử lý sẵn có, không phải chờ slot đặc biệt. |
| LOW vừa trở lại sau lúc queue trống. | Trong hữu hạn lần chọn, LOW được phục vụ; không bị kẹt do con trỏ. |
| Một handler HIGH bị treo. | Timeout/bulkhead ngăn nó chiếm toàn bộ khả năng phục vụ LOW. |
| Một HIGH poison message bị retry liên tục. | Retry hữu hạn, backoff và DLQ; LOW không mất mọi suất phục vụ. |
| Queue LOW đầy. | Producer nhận tín hiệu quá tải và có phương án retry/fallback rõ; không âm thầm mất message. |
| Worker crash sau DB commit trước ACK. | Redelivery không tạo side effect trùng nhờ event ID và idempotency. |
| Chuyển message sang lớp ưu tiên cao hơn do aging. | Original enqueue time và event ID không bị reset; không tạo thêm xử lý trùng. |
| Nhiều worker / nhiều instance. | Fairness được thiết kế ở cấp dùng chung hoặc dựa trên quota/shard; không phụ thuộc một counter cục bộ tình cờ. |
| Một tenant phát số lượng message HIGH áp đảo. | Quota giữa tenant vẫn bảo đảm tenant khác có tiến triển. |
| Tải vào lớn hơn năng lực xử lý trong thời gian dài. | Hệ thống có backpressure, alert, scaling hoặc degrade thay vì khẳng định mọi SLO đều đạt. |

### Test thời gian chờ phải xét clock

Để kiểm tra aging, nên dùng một **clock giả/có thể điều khiển** thay vì gọi `Thread.sleep(60_000)`. Tạo message với `originalEnqueueTime` cố định, tăng đồng hồ trong test và gọi scheduler hoặc promotion job ở các mốc xác định. Như vậy test nhanh, lặp lại ổn định và không phụ thuộc timing của máy CI.

Đối với retry và redelivery, kiểm thử với broker/MessageStore thật trong môi trường integration test khi ứng dụng yêu cầu delivery bền vững; unit test WRR không chứng minh được ACK, rollback hay khôi phục sau crash.

## 18. Bài tập thực hành

**Bài 1 — tái hiện starvation.** Dùng `PriorityChannel` với header priority 9 và 1. Enqueue LOW trước, sau đó trong mỗi vòng lặp enqueue HIGH và `receive(0)`. Giải thích vì sao LOW bị trì hoãn dù queue còn message.

**Bài 2 — xây dựng lịch 4:2:1.** Tạo ba `QueueChannel` và bộ điều phối WRR. Kiểm thử 70 lần xử lý khi cả ba queue luôn có backlog: dự kiến khoảng 40 HIGH, 20 NORMAL, 10 LOW theo số lần dispatch, nếu chi phí từng handler không làm dừng scheduler.

**Bài 3 — kiểm tra queue trống.** Chỉ enqueue LOW, giữ HIGH/NORMAL trống. Xác minh dispatcher không lãng phí 6/7 lượt mà vẫn dùng capacity cho LOW.

**Bài 4 — thêm aging.** Định nghĩa `originalEnqueueTime` và nâng class khi message chờ trên 30 giây. Dùng fake clock để chứng minh promotion hoạt động và không reset tuổi chờ sau retry.

**Bài 5 — ưu tiên và deadline.** Định nghĩa SLO HIGH p99 ≤ 2 giây, LOW p99 ≤ 60 giây. Giả lập handler HIGH có thời gian xử lý tăng gấp 10 lần. So sánh WRR theo số message với reserved workers và deadline override.

**Bài 6 — retry không làm đói queue.** Tạo một message HIGH luôn ném exception, thêm retry budget tối đa 3 lần và backoff. Kiểm chứng message được chuyển vào DLQ và LOW tiếp tục tiến triển.

**Bài 7 — nhiều tenant.** Tenant A gửi 90% lưu lượng HIGH, tenant B gửi 10%. Thử thêm quota từng tenant rồi đo số message và tuổi chờ của B khi tải cao.

**Bài 8 — production readiness.** Chuyển ví dụ ba queue RAM sang một durable message source phù hợp; định nghĩa chính xác dequeue/ACK, transaction business, retry, idempotency, việc mất worker và cách tiếp tục scheduler sau restart.

### Câu hỏi tự đánh giá

**1. `PriorityChannel` có mặc định tránh starvation không?** Không. Nó chọn message theo priority; HIGH liên tục có thể khiến LOW chờ vô hạn.

**2. Weighted round-robin 4:2:1 bảo đảm điều gì?** Khi các queue luôn có việc và scheduler tiến triển, nó phân bổ số **lượt chọn message** theo tỷ lệ, không tự đảm bảo deadline tính theo giây.

**3. Vì sao không nên dùng comparator `System.currentTimeMillis()` để aging một priority heap?** Vì heap không tự reorder toàn bộ phần tử khi thời gian thay đổi; phải có cơ chế reevaluate/rebuild/promotion thực sự.

**4. Tách thành ba queue có tự đủ để công bằng không?** Không. Phải có chính sách cấp worker/lượt giữa các queue.

**5. Vì sao LOW vẫn có thể bị chậm khi đã có WRR?** Handler khác chạy quá lâu, thiếu worker, downstream bị nghẽn, tổng tải quá cao hoặc worker không hoàn tất.

**6. Nếu message được lấy khỏi QueueChannel RAM rồi handler lỗi thì sao?** Message không tự được đưa lại chỉ vì JDBC rollback; muốn reliability phải thiết kế nguồn bền vững, ACK và redelivery.

**7. Khi nào cần outbox/inbox?** Khi cần tránh mất ý định gửi sau DB commit hoặc chống duplicate khi consumer nhận lại message từ tài nguyên khác.

## 19. Checklist trước khi đưa flow ưu tiên vào production

- [ ] Định nghĩa priority theo nghiệp vụ có tin cậy, không cho producer tự nâng vô hạn.
- [ ] Xác định mỗi lớp có SLO chờ và budget tối thiểu hay không.
- [ ] Không coi strict priority là fairness; có WRR, aging, deadline override hoặc reserved capacity khi cần.
- [ ] Nếu dùng WRR, kiểm tra cả **queue có việc liên tục** và **queue trống**.
- [ ] Nếu dùng aging, có promotion/reheap/selection logic thật sự, không chỉ comparator đọc đồng hồ.
- [ ] Giữ FIFO trong cùng lớp nếu nghiệp vụ yêu cầu, bảo toàn event ID/ordering metadata.
- [ ] Có limit tại producer/tenant, backpressure và chính sách khi queue đầy.
- [ ] Với task dài/treo, có timeout và bulkhead để bảo vệ tiến triển của lớp khác.
- [ ] Retry phải hữu hạn, có backoff, DLQ và quota; không để poison HIGH chiếm mọi worker.
- [ ] Message quan trọng phải dùng nguồn bền vững, ACK/transaction và idempotency phù hợp.
- [ ] Ghi lại original enqueue time, eventId và correlationId qua mọi lần retry/promotion.
- [ ] Theo dõi oldest pending age, p95/p99 wait, low progress, queue depth, retry và deadline misses.
- [ ] Kiểm thử overload, crash, nhiều instance, tenant lớn, duplicate và partial failure.
- [ ] Chấp nhận giới hạn capacity: fairness không thay thế scaling và admission control khi tải dài hạn vượt khả năng xử lý.

**Ghi nhớ:** **Priority giúp chọn việc quan trọng trước; fairness bảo đảm việc ít ưu tiên vẫn tiến triển.** `PriorityChannel` là công cụ ordering, không phải một hệ thống scheduling fairness hoàn chỉnh. Trong Spring Integration, muốn tránh priority starvation phải chủ động thiết kế quota, aging/deadline hoặc reserved workers, rồi kiểm thử cùng tình huống HIGH đến liên tục, có retry và có lỗi — đúng với điều kiện hệ thống gặp khi tải lớn.

### Tài liệu tham khảo

- [Spring Integration — Message Channel Implementations](https://docs.spring.io/spring-integration/reference/channel/implementations.html): `PriorityChannel` và các loại channel.
- [Spring Integration — Configuring Message Channels](https://docs.spring.io/spring-integration/reference/channel/configuration.html): header `priority`, comparator, capacity và priority-capable message stores.
- [Spring Framework — Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html): boundary giao dịch khi xử lý message.

*Ví dụ dùng queue trong bộ nhớ để dễ nhìn thuật toán và kiểm thử fairness. Khi triển khai production, cần đối chiếu API với phiên bản Spring Integration, giới hạn channel, contract của broker/store và cấu hình transaction/ACK; không coi sample scheduler là giải pháp giao tin bền vững sẵn có.*
