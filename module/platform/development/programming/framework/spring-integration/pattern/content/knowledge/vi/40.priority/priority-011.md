# Phân biệt priority với deadline trong Spring Integration

## 1. Vì sao thông điệp HIGH chưa chắc phải chạy trước LOW?

Một dịch vụ xử lý đơn hàng nhận hai yêu cầu tại 09:59:40:

| Yêu cầu | Priority | Hạn hoàn tất | Thời gian xử lý dự kiến |
| --- | ---: | --- | ---: |
| A: soát xét rủi ro | HIGH = 9 | 10:30:00 | 30 giây |
| B: khóa chỗ giữ đơn | LOW = 1 | 10:00:00 | 5 giây |

Nếu dùng **strict priority**, consumer có thể chọn A trước B. B bắt đầu khoảng 10:00:10 và chắc chắn trễ hạn trong kịch bản một worker nói trên. Nếu chọn B trước, B có thể hoàn tất 09:59:45; A vẫn còn nhiều thời gian. Tuy nhiên, nếu luôn chọn deadline sớm nhất, nhiều tác vụ LOW có hạn gấp có thể chiếm hết suất của một công việc HIGH đặc biệt quan trọng.

Hai khái niệm giải quyết hai câu hỏi khác nhau:

- **Priority**: *Công việc nào quan trọng hơn theo chính sách phân bổ tài nguyên?* Đây thường là mức **tương đối** giữa các tác vụ đang chờ.
- **Deadline**: *Kết quả phải đạt trước thời điểm nào?* Đây là ràng buộc **thời gian** gắn với yêu cầu nghiệp vụ.

Không có quy tắc phổ quát rằng HIGH đồng nghĩa deadline gần hay LOW đồng nghĩa được phép hoàn tất trễ. Cần thiết kế **scheduling policy** diễn giải cả hai.

Bài học thuộc chương **Priority** của module `SPRING_INTEGRATION_PATTERN`. Khi triển khai Enterprise Integration Patterns bằng Spring Integration — Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel và correlation — ta phải bảo toàn ý nghĩa priority/deadline qua các channel và nhánh xử lý, đồng thời kiểm thử, quan sát kết quả thực tế.

### Kết quả cần đạt

Sau bài này, bạn có thể:

1. Phân biệt priority, deadline, TTL/expiration, timeout, delay, SLA và SLO.
2. Giải thích rõ `PriorityChannel` bảo đảm điều gì và không bảo đảm điều gì.
3. Đọc và đánh giá strict priority, earliest-deadline-first (EDF), least-slack-time (LST), quota và deadline override.
4. Thiết kế metadata/contract để giữ deadline qua EIP và adapter.
5. Xử lý expired message theo nghiệp vụ, không tự âm thầm drop hoặc retry vô hạn.
6. Viết Java + JUnit dùng `Clock` giả để kiểm thử deadline selection và retry budget.
7. Phân biệt đúng hạn **bắt đầu** với đúng hạn **hoàn tất/commit**; đo được deadline miss dưới tải.

## 2. Bảng phân biệt các khái niệm liên quan

| Khái niệm | Ý nghĩa | Ví dụ | Không nên suy ra |
| --- | --- | --- | --- |
| **Priority** | Mức độ quan trọng tương đối khi cấp lượt. | 9 cao hơn 5 và 1. | Message 9 chắc chắn hoàn tất trong 2 giây. |
| **Deadline** | Mốc muộn nhất kết quả được yêu cầu. | Hoàn tất trước 10:00 UTC. | Scheduler tự đáp ứng mốc ấy. |
| **Time-to-live (TTL)** | Khoảng thời gian message còn sống trong resource theo policy. | TTL broker 30 giây. | Handler đã commit trước khi TTL hết. |
| **Expiration** | Thời điểm/cơ chế một message bị coi là hết hạn ở resource. | Broker dead-letter message hết TTL. | Nghiệp vụ đã ghi nhận trạng thái EXPIRED. |
| **Timeout** | Giới hạn thời gian một thao tác chờ/chạy. | Gateway chờ reply 2 giây. | Server chắc chắn dừng side effect sau 2 giây. |
| **Delay / scheduled time** | Không được bắt đầu trước mốc nhất định. | Chạy sau 09:00. | Phải hoàn tất trước một deadline. |
| **Processing budget** | Ước lượng thời gian dành cho một đoạn flow. | Handler cần khoảng 500 ms. | Thời gian chạy thật luôn đúng 500 ms. |
| **SLO** | Mục tiêu đo được về chất lượng dịch vụ. | p99 queue wait HIGH dưới 1 giây. | Tất cả message đều đạt deadline nghiệp vụ. |
| **SLA** | Cam kết với khách hàng/đối tác và điều kiện áp dụng. | 99,9% giao dịch hoàn tất trong 5 giây. | Một annotation có thể tự tạo bảo đảm. |

### Các mốc cần giữ riêng

~~~text
createdAt      : lúc yêu cầu hình thành trong nghiệp vụ
enqueuedAt     : lúc được ghi vào hàng đợi
startedAt      : lúc handler thực sự bắt đầu
completedAt    : lúc kết quả được coi là hoàn tất theo contract
deadlineAt     : thời điểm muộn nhất được phép hoàn tất
~~~

Ví dụ:

~~~text
createdAt   09:59:30
enqueuedAt  09:59:35
startedAt   09:59:50
completedAt 10:00:05
deadlineAt  10:00:00

Queue wait = 15 giây
End-to-end latency = 35 giây
Trễ hạn hoàn tất = 5 giây
~~~

**Bắt đầu trước deadline không đồng nghĩa hoàn tất đúng hạn.** Nếu domain quy định deadline của *việc bắt đầu* thay vì *kết quả*, cần nêu tường minh và kiểm thử theo quy tắc đó; không tự chuyển đổi ý nghĩa.

## 3. Priority là ordering, deadline là ràng buộc thời gian

Ví dụ business classification:

~~~java
enum WorkClass {
    HIGH(9), NORMAL(5), LOW(1);

    private final int value;

    WorkClass(int value) {
        this.value = value;
    }

    int priority() {
        return value;
    }
}
~~~

Các giá trị 9–5–1 chỉ là **quy ước nội bộ**, không phải ba mức cố định của Spring Integration. Với `PriorityChannel` mặc định, giá trị priority cao hơn thường được chọn trước trong số **message còn nằm trong hàng đợi**.

Deadline được lưu như mốc tuyệt đối:

~~~java
Instant deadlineAt =
        Instant.parse("2026-11-21T10:00:00Z");
~~~

Không dùng `LocalDateTime` thiếu timezone để truyền giữa service ở nhiều vùng. Nên lưu **`Instant` hoặc timestamp ISO-8601 có offset rõ**, kiểm tra clock skew giữa các node. Dùng đồng hồ monotonic như `System.nanoTime()` để đo duration bên trong process; dùng wall-clock/UTC khi so với một absolute deadline được chia sẻ.

### Bốn tình huống cần phân biệt

| Tình huống | Cách hiểu |
| --- | --- |
| HIGH hạn xa, LOW hạn gần | Priority-first và deadline-first có thể chọn khác nhau. |
| HIGH và LOW cùng deadline | Cần tie-breaker theo business criticality hoặc FIFO. |
| LOW đã được worker nhận, HIGH đến sau | HIGH không tự ngắt task LOW đang xử lý. |
| HIGH và LOW đều đã hết hạn | Cần expired policy, không tự xử lý như message bình thường. |

## 4. PriorityChannel có dùng deadline không?

`PriorityChannel` thuộc loại `PollableChannel`. Nó chọn message theo header priority hoặc một `Comparator<Message<?>>` được cấu hình. Nó **không tự đọc** header custom `deadlineAt` như một business deadline.

~~~java
@Bean("priorityPending")
PollableChannel priorityPending() {
    return new PriorityChannel(100);
}
~~~

~~~java
Message<String> high = MessageBuilder.withPayload("HIGH-FAR")
        .setHeader("priority", 9)
        .setHeader("deadlineAt",
                Instant.parse("2026-11-21T10:30:00Z"))
        .build();

Message<String> low = MessageBuilder.withPayload("LOW-SOON")
        .setHeader("priority", 1)
        .setHeader("deadlineAt",
                Instant.parse("2026-11-21T10:00:00Z"))
        .build();

priorityPending.send(low);
priorityPending.send(high);
Message<?> selected = priorityPending.receive(0);
// Với strict priority mặc định, selected thường là HIGH-FAR.
~~~

| Thành phần | Hành vi cốt lõi | Có tự bảo đảm deadline không? |
| --- | --- | --- |
| `DirectChannel` | Dispatch handler đồng bộ trên thread gọi. | Không. |
| `ExecutorChannel` | Bàn giao theo scheduling của executor/thread. | Không. |
| `QueueChannel` FIFO | Lấy message theo quy tắc hàng đợi. | Không. |
| `PriorityChannel` | Chọn theo priority/comparator. | Không, trừ khi scheduler/comparator được thiết kế riêng và vẫn không bảo đảm completion. |
| `Delayer`/delayed endpoint | Trì hoãn xử lý tới thời điểm cho phép. | Không, delay khác deadline. |
| `Service Activator` | Thực thi business handler. | Chỉ nếu code/architecture kiểm tra và bảo vệ contract. |

Việc một channel **truyền header đúng** không có nghĩa nó **sử dụng** header đó để xếp lịch. Một `DirectChannel` có `priority=9` vẫn chạy đồng bộ, không reorder.

## 5. Deadline, slack và tính khả thi

~~~text
remainingTime = deadlineAt - now
estimatedDuration = thời gian xử lý ước tính
slack = deadlineAt - now - estimatedDuration
lateness = completedAt - deadlineAt
~~~

`slack > 0` nghĩa là theo estimate còn dư thời gian; `slack = 0` sát hạn; `slack < 0` theo estimate đã quá muộn ngay cả khi bắt đầu bây giờ.

| Task | Priority | Hạn còn lại | Ước lượng xử lý | Slack |
| --- | ---: | ---: | ---: | ---: |
| A | 9 | 15 giây | 1 giây | +14 giây |
| B | 1 | 18 giây | 17 giây | +1 giây |

B có deadline muộn hơn A nhưng ít slack hơn. Chọn earliest deadline và least slack có thể cho kết quả khác nhau.

**Ước lượng không phải bảo đảm.** CPU, database lock, GC, network, retry và prefetch có thể khiến thời gian thực vượt estimate. Hệ thống cần timeout, admission control, backpressure và metric completion thực tế.

## 6. So sánh thuật toán scheduling

| Chính sách | Quy tắc chọn | Lợi ích | Giới hạn |
| --- | --- | --- | --- |
| **Strict priority** | Ưu tiên số cao nhất. | Giúp nhóm quan trọng nhận lượt trước. | LOW starvation, có thể bỏ lỡ deadline gần. |
| **EDF (earliest deadline first)** | Chọn deadline sớm nhất. | Hợp lý khi deadline là ràng buộc chính. | Có thể giảm suất của HIGH hoặc task không deadline. |
| **LST (least slack time)** | Chọn `deadline - now - estimate` nhỏ nhất. | Tính thêm công sức cần làm. | Phụ thuộc estimate; khó bảo đảm khi độ dài task biến động. |
| **Weighted round-robin** | Phân bổ số lượt 4:2:1 giữa ba lớp. | Tạo cơ hội tiến triển cho LOW. | Chưa tự bảo đảm deadline tính bằng giây. |
| **Deadline override** | Bình thường theo priority/quota, ưu tiên task gần hạn. | Kết hợp criticality và time pressure. | Cần bảo vệ trước deadline gaming. |
| **Reserved capacity** | Dành worker hoặc quota cho từng lớp/tenant. | Hạn chế starvation vì chia sẻ pool. | Resource chung vẫn có thể bị nghẽn. |

### Quy tắc kết hợp minh họa

~~~text
Mỗi lần chọn công việc:
  1. Đánh dấu/xử lý riêng các task đã quá deadline.
  2. Tính remainingTime và slack cho phần còn hợp lệ.
  3. Nếu có task slack <= 10 giây, chọn deadline sớm nhất trong nhóm đó.
  4. Nếu không, chọn theo priority hoặc quota của các lớp.
  5. Ghi lý do lựa chọn và các mốc thời gian.
~~~

Đây là **policy của ứng dụng**, không phải mặc định của Spring Integration. Nếu tất cả client tự khai deadline chỉ còn một giây, nhóm cận hạn sẽ chiếm mọi worker; phải validate deadline theo quyền và business type.

## 7. Comparator EDF: dùng deadline bất biến để sắp thứ tự

Một `Comparator<Message<?>>` ổn định có thể chọn deadline sớm nhất:

~~~java
static Instant requiredDeadline(Message<?> message) {
    Object value = message.getHeaders().get("deadlineAt");
    if (!(value instanceof Instant deadline)) {
        throw new IllegalArgumentException("Missing deadlineAt");
    }
    return deadline;
}

Comparator<Message<?>> byDeadlineThenPriority = (a, b) -> {
    int deadlineOrder =
            requiredDeadline(a).compareTo(requiredDeadline(b));
    if (deadlineOrder != 0) {
        return deadlineOrder; // Hạn sớm lên trước.
    }
    int pa = ((Number) a.getHeaders().get("priority")).intValue();
    int pb = ((Number) b.getHeaders().get("priority")).intValue();
    return Integer.compare(pb, pa); // Khi cùng hạn, HIGH trước.
};

PriorityChannel edfQueue =
        new PriorityChannel(100, byDeadlineThenPriority);
~~~

Trước khi enqueue, ứng dụng phải validate `deadlineAt` và `priority` để comparator không nhận giá trị rỗng/sai kiểu. Khi dùng persistent store, **không** mặc định comparator RAM áp dụng cho store hay broker khác.

Comparator này chỉ sắp xếp message còn chờ; nó không:

- Preempt handler đã bắt đầu.
- Biết thời gian xử lý thực tế.
- Tự hủy message expired.
- Tự bảo đảm mọi deadline dưới overload.
- Tự tổ chức transaction, ACK/redelivery và idempotency.

### Cạm bẫy của comparator theo đồng hồ

Đừng viết comparator phụ thuộc `Instant.now()` rồi chờ heap tự reorder theo tuổi. Priority queue không tự đánh giá lại mọi phần tử mỗi giây. Nếu cần aging hay deadline override dựa trên `now`, hãy dùng scheduler xét lại khi chọn, promotion/reinsert hoặc query store theo policy; có kiểm thử với clock giả.

## 8. Tạo hợp đồng priority + deadline tại ingress

Đặt cả hai giá trị trong domain contract thay vì dùng một để suy giá trị kia:

~~~java
record WorkRequest(
        String eventId,
        String type,
        Instant requestedDeadline) {}

record WorkCommand(
        String eventId,
        String type,
        int priority,
        Instant deadlineAt) {}

final class WorkPolicy {
    static int priorityFor(String type) {
        return switch (type) {
            case "FRAUD_REVIEW", "RISK_CANCEL" -> 9;
            case "PAYMENT_CONFIRM" -> 5;
            case "REPORT_REFRESH" -> 1;
            default -> throw new IllegalArgumentException(
                    "Unknown type: " + type);
        };
    }

    static WorkCommand normalize(WorkRequest request, Clock clock) {
        if (request.eventId() == null
                || request.eventId().isBlank()
                || request.requestedDeadline() == null) {
            throw new IllegalArgumentException("Missing required fields");
        }
        Instant now = clock.instant();
        Instant deadline = request.requestedDeadline();
        if (deadline.isAfter(now.plus(Duration.ofDays(7)))) {
            throw new IllegalArgumentException("Deadline too far away");
        }
        return new WorkCommand(
                request.eventId(),
                request.type(),
                priorityFor(request.type()),
                deadline);
    }
}
~~~

Mức 7 ngày chỉ là **ví dụ policy**. Với deadline quá khứ, domain có thể trả về expired result thay vì từ chối input; không có quy tắc chung cho mọi API.

### Không tin deadline do caller tự ý đặt

Nếu một client ngoài hệ thống được đặt `deadlineAt=now+1s`, họ có thể chiếm mọi suất urgent dù nghiệp vụ thật chỉ là báo cáo LOW. Vì vậy:

1. Xác thực quyền của caller và loại tác vụ.
2. Giới hạn thời hạn tối thiểu/tối đa theo SLA của tenant.
3. Cho phép server tính hoặc clamp deadline.
4. Áp quota/rate limit riêng cho các loại công việc.
5. Ghi `deadlineSource` và `policyVersion` để truy vết quyết định.

## 9. Hợp đồng message và metadata

~~~java
WorkCommand command = WorkPolicy.normalize(request, clock);

Message<WorkCommand> message =
        MessageBuilder.withPayload(command)
                .setHeader("priority", command.priority())
                .setHeader("deadlineAt", command.deadlineAt())
                .setHeader("businessEventId", command.eventId())
                .setHeader("deadlinePolicyVersion", "v1")
                .build();
~~~

| Trường | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| `priority` | Mức quan trọng dùng ở scheduler/channel. | Validate kiểu/miền; mapper broker có property riêng. |
| `deadlineAt` | Mốc deadline tuyệt đối. | Header custom, không tự kích hoạt broker expiration. |
| `businessEventId` | ID nghiệp vụ giữ nguyên qua retry. | Không thay bằng `MessageHeaders.ID`. |
| `originalEnqueuedAt` | Tính tuổi chờ xuyên nhiều lần enqueue. | Không reset khi retry/promote. |
| `correlationId` | Ghép các nhánh Splitter/Aggregator. | Khác event ID của message con. |
| `deadlinePolicyVersion` | Phiên bản rule/nguồn deadline. | Hữu ích khi audit và thay chính sách. |

Ở external boundary, chỉ export **allowlist** header có kiểu wire-compatible. Header như `replyChannel`, `errorChannel` có thể là object nội bộ, không nên đẩy tùy tiện qua HTTP/JMS/Kafka.

## 10. Java: bộ chọn kết hợp priority và deadline

Để kiểm tra được policy **không lệ thuộc Spring context**, viết một selector trên danh sách pending đã có trong test. Đây không phải một durable/concurrent queue production.

~~~java
record PendingTask(
        String eventId,
        int priority,
        Instant deadlineAt,
        Instant acceptedAt,
        Duration estimatedDuration) {}

final class DeadlineAwareSelector {
    private final Clock clock;
    private final Duration urgentWindow;

    DeadlineAwareSelector(Clock clock, Duration urgentWindow) {
        this.clock = clock;
        this.urgentWindow = urgentWindow;
    }

    PendingTask select(List<PendingTask> pending) {
        Instant now = clock.instant();

        // Chỉ chọn task còn hợp lệ; expired phải có outcome riêng.
        List<PendingTask> eligible = pending.stream()
                .filter(t -> !now.isAfter(t.deadlineAt()))
                .toList();
        if (eligible.isEmpty()) {
            throw new NoSuchElementException("No eligible tasks");
        }

        List<PendingTask> urgent = eligible.stream()
                .filter(t -> slack(t, now).compareTo(urgentWindow) <= 0)
                .toList();

        if (!urgent.isEmpty()) {
            return urgent.stream()
                    .min(Comparator
                            .comparing(PendingTask::deadlineAt)
                            .thenComparing(
                                    Comparator.comparingInt(
                                            PendingTask::priority).reversed())
                            .thenComparing(PendingTask::acceptedAt)
                            .thenComparing(PendingTask::eventId))
                    .orElseThrow();
        }

        return eligible.stream()
                .min(Comparator
                        .comparingInt(PendingTask::priority).reversed()
                        .thenComparing(PendingTask::acceptedAt)
                        .thenComparing(PendingTask::eventId))
                .orElseThrow();
    }

    private static Duration slack(PendingTask task, Instant now) {
        return Duration.between(now, task.deadlineAt())
                .minus(task.estimatedDuration());
    }
}
~~~

Ý nghĩa:

- Nếu còn task với slack không lớn hơn `urgentWindow`, chọn task cận hạn có **deadline sớm nhất**.
- Nếu không có task cận hạn, chọn priority cao nhất rồi đến thời gian nhận.
- Task đã expired không được chọn như công việc bình thường nhưng **không được âm thầm xóa khỏi nguồn**.
- Hàm sử dụng `Clock` được inject; khi test có thể khóa thời gian.

**Giới hạn:** mỗi lần chọn quét `O(n)`. Với hàng triệu message, dùng index, database claim/lease hoặc queue scheduler chuyên dụng. Nhiều worker phải có thao tác claim/ACK nguyên tử để tránh cùng chọn một task. Nếu mọi task đều cận hạn, quy tắc trên vẫn có thể trì hoãn HIGH, nên có quota/admission control riêng khi domain đòi hỏi.

## 11. Unit test với Clock cố định

### LOW cận hạn được ưu tiên trước HIGH hạn xa

~~~java
@Test
void lowNearDeadlineCanOvertakeHighWithDistantDeadline() {
    Instant now = Instant.parse("2026-01-01T10:00:00Z");
    DeadlineAwareSelector selector = new DeadlineAwareSelector(
            Clock.fixed(now, ZoneOffset.UTC),
            Duration.ofSeconds(10));

    PendingTask high = new PendingTask(
            "HIGH-1", 9, now.plusSeconds(1800),
            now.minusSeconds(20), Duration.ofSeconds(2));
    PendingTask low = new PendingTask(
            "LOW-1", 1, now.plusSeconds(12),
            now.minusSeconds(40), Duration.ofSeconds(5));

    assertEquals("LOW-1",
            selector.select(List.of(high, low)).eventId());
}
~~~

LOW có slack **7 giây** và nằm trong cửa sổ khẩn 10 giây. HIGH có nhiều thời gian. Đây là unit test chính sách deadline override, **không** phải test `PriorityChannel` mặc định.

### Khi không có task urgent, HIGH được chọn

~~~java
@Test
void highWinsWhenBothDeadlinesAreComfortable() {
    Instant now = Instant.parse("2026-01-01T10:00:00Z");
    DeadlineAwareSelector selector = new DeadlineAwareSelector(
            Clock.fixed(now, ZoneOffset.UTC),
            Duration.ofSeconds(10));

    PendingTask high = new PendingTask(
            "HIGH-2", 9, now.plusSeconds(100),
            now, Duration.ofSeconds(5));
    PendingTask low = new PendingTask(
            "LOW-2", 1, now.plusSeconds(70),
            now, Duration.ofSeconds(5));

    assertEquals("HIGH-2",
            selector.select(List.of(low, high)).eventId());
}
~~~

EDF thuần có thể chọn LOW trong cùng trường hợp, vì deadline LOW sớm hơn. Điều đó chứng minh phải **nói rõ policy** trước khi khẳng định thứ tự đúng.

### Không chọn expired như task bình thường

~~~java
@Test
void expiredWorkIsExcludedFromNormalSelection() {
    Instant now = Instant.parse("2026-01-01T10:00:00Z");
    DeadlineAwareSelector selector = new DeadlineAwareSelector(
            Clock.fixed(now, ZoneOffset.UTC),
            Duration.ofSeconds(10));

    PendingTask expired = new PendingTask(
            "EXPIRED", 9, now.minusSeconds(1),
            now.minusSeconds(20), Duration.ofSeconds(1));
    PendingTask valid = new PendingTask(
            "VALID", 1, now.plusSeconds(40),
            now, Duration.ofSeconds(2));

    assertEquals("VALID",
            selector.select(List.of(expired, valid)).eventId());
}
~~~

**Quan trọng:** production phải có một **expired transition** riêng: ghi trạng thái EXPIRED, quarantine/reconcile hoặc chuyển xử lý muộn theo domain. Filter expired ra khỏi một danh sách nhưng không ghi trạng thái là lỗi bỏ quên công việc.

## 12. Quy tắc xử lý message hết hạn tùy nghiệp vụ

| Loại tác vụ | Khi quá deadline | Vì sao |
| --- | --- | --- |
| Khóa chỗ chỉ hợp lệ đến 10:00 | Không xác nhận muộn; ghi `EXPIRED_NOT_EXECUTED`. | Xác nhận sau thời gian hiệu lực có thể sai nghiệp vụ. |
| Gửi báo cáo định kỳ | Có thể tiếp tục, ghi `COMPLETED_LATE`. | Dữ liệu vẫn có giá trị dù SLA trễ. |
| Cảnh báo an ninh | Có thể vẫn phải xử lý và escalate. | Bỏ qua alert nguy hiểm hơn hoàn tất trễ. |
| Gọi đối tác đã timeout | Xác minh trạng thái thực tế trước khi retry. | Đối tác có thể đã commit dù caller timeout. |
| Thanh toán/giữ hàng đa bước | Kiểm tra lại trạng thái, có thể cancel/compensate. | Có thể đã có side effect ở nhánh khác. |

Thời hạn xử lý còn phụ thuộc trạng thái transaction và công việc có được phép **bắt đầu** trước deadline nhưng **hoàn tất** sau đó hay không. Đây là quyết định nghiệp vụ cần tài liệu hóa, không chỉ một điều kiện `if (now > deadline)`.

## 13. IntegrationFlow: priority queue và deadline guard là hai trách nhiệm riêng

Một flow nhỏ giúp phân biệt việc **chọn lượt theo priority** với việc **kiểm tra tính hợp lệ theo deadline**:

~~~mermaid
flowchart LR
    A["Gateway / inbound adapter"] --> B["Normalize priority và deadline"]
    B --> C["PriorityChannel"]
    C --> D["Polling endpoint"]
    D --> E{"DeadlineGate"}
    E -->|"Được xử lý"| F["Service Activator"]
    E -->|"Expired"| G["Expired outcome / reconcile"]
    F --> H[("Business database")]
~~~

Ví dụ Java DSL:

~~~java
@Configuration
@EnableIntegration
class PriorityDeadlineFlowConfig {
    @Bean("priorityIngress")
    MessageChannel priorityIngress() {
        return new DirectChannel();
    }

    @Bean("priorityPending")
    PollableChannel priorityPending() {
        return new PriorityChannel(200);
    }

    @Bean
    IntegrationFlow enqueueFlow() {
        return IntegrationFlow.from("priorityIngress")
                .channel("priorityPending")
                .get();
    }

    @Bean
    IntegrationFlow consumeFlow(DeadlineGate gate) {
        return IntegrationFlow.from(
                        "priorityPending",
                        endpoint -> endpoint.poller(
                                Pollers.fixedDelay(200)
                                        .maxMessagesPerPoll(1)))
                .handle(gate, "consume")
                .get();
    }

    @Bean
    Clock clock() {
        return Clock.systemUTC();
    }
}
~~~

Gate đọc deadline/priority trước khi gọi service nghiệp vụ:

~~~java
@Component
class DeadlineGate {
    private final Clock clock;
    private final WorkProcessor processor;

    DeadlineGate(Clock clock, WorkProcessor processor) {
        this.clock = clock;
        this.processor = processor;
    }

    public void consume(Message<WorkCommand> message) {
        WorkCommand work = message.getPayload();
        Object headerPriority = message.getHeaders().get("priority");
        Object headerDeadline = message.getHeaders().get("deadlineAt");

        if (!(headerPriority instanceof Integer priority)
                || !(headerDeadline instanceof Instant deadline)
                || priority.intValue() != work.priority()
                || !deadline.equals(work.deadlineAt())) {
            throw new IllegalArgumentException(
                    "Priority/deadline header mismatch");
        }

        if (clock.instant().isAfter(deadline)) {
            throw new DeadlineExceededException(
                    work.eventId(), deadline);
        }

        processor.process(work);
    }
}

@Service
class WorkProcessor {
    @Transactional
    public void process(WorkCommand work) {
        // Xử lý business DB và idempotency theo work.eventId().
        // Hành động thực tế do bài thực hành bổ sung.
    }
}

class DeadlineExceededException extends RuntimeException {
    DeadlineExceededException(String id, Instant deadline) {
        super("Work " + id + " expired at " + deadline);
    }
}
~~~

### Đọc đúng phạm vi của ví dụ

1. `PriorityChannel` ở đây dùng **RAM** và strict priority: không thực thi EDF/deadline override.
2. `DeadlineGate` chỉ phát hiện **quá hạn trước khi xử lý**. Nếu processor chạy lâu, task vẫn có thể hoàn tất muộn.
3. Ném exception không mặc định tạo một expired state hoặc tự đưa message vào DLQ. Cần error flow/nguồn message phù hợp.
4. Một queue RAM đã dequeue message không tự nhận lại message do JDBC rollback; ví dụ không phải thiết kế durable production.
5. `@Transactional` chỉ điều phối tài nguyên database/transaction manager tham gia; không tự hủy side effect ở HTTP/broker.

Khi cần chọn LOW cận deadline trước HIGH hạn xa, phải thay **cơ chế chọn message** bằng selector ở phần 10, EDF comparator thích hợp hoặc một scheduler/store được thiết kế riêng. Chỉ thêm `DeadlineGate` sau strict priority queue là **không đủ** để tránh deadline miss do starvation.

## 14. Gateway, Transformer và Router: giữ deadline xuyên các hop

~~~mermaid
flowchart LR
    A["Gateway request"] --> B["Header Enricher"]
    B --> C["Transformer"]
    C --> D{"Router"}
    D --> E["DirectChannel branch"]
    D --> F["Async executor / broker branch"]
    E --> G["Deadline validation"]
    F --> G
~~~

### Gateway: request timeout khác deadline

~~~java
@MessagingGateway(defaultRequestChannel = "priorityIngress")
interface WorkGateway {
    void submit(Message<WorkCommand> command);
}
~~~

Request có thể mang `priority` và `deadlineAt` được policy gắn sẵn. Nếu Gateway chỉ nhận payload, cần gắn metadata ở một bước ingress. Timeout khi Gateway chờ reply, ví dụ 2 giây, **không có nghĩa worker bất đồng bộ đã bị hủy sau 2 giây**.

### Transformer: không tự gia hạn deadline

Khi thay payload:

~~~java
Message<NormalizedWork> output =
        MessageBuilder.withPayload(
                    normalize(input.getPayload()))
                .copyHeaders(input.getHeaders())
                .setHeader("priority", validatedPriority)
                .setHeader("deadlineAt", validatedDeadline)
                .build();
~~~

Hàm `normalize(...)` và các biến validate là phần của application service. Spring Integration có các quy tắc merge/copy request headers tùy endpoint, nên **test output thực tế**; khi custom code tự tạo Message, vẫn phải chủ động xác định header policy.

### Router: deadline ở mỗi nhánh có thể khác

Nếu Router chuyển sang service ở vùng địa lý khác, deadline tuyệt đối vẫn là một mốc chung, nhưng **remaining budget giảm** vì serialization, queue và network. Không dùng duration được tính một lần ở producer như thể nó không đổi khi truyền giữa các service.

Khi chuyển qua `ExecutorChannel`, transaction thread-bound từ caller không tự đi theo worker. Một handler đã commit phía sender cũng không chứng minh worker còn đủ thời gian để xử lý.

## 15. Splitter và Aggregator: một deadline end-to-end có nhiều ngân sách

Với workflow thanh toán:

~~~mermaid
flowchart LR
    A["Checkout: deadline T"] --> B["Splitter"]
    B --> C["Reserve stock"]
    B --> D["Verify payment"]
    B --> E["Fraud check"]
    C --> F["Aggregator"]
    D --> F
    E --> F
    F --> G["Commit checkout trước T"]
~~~

Parent deadline có thể là 10:00:00, nhưng kết quả các child phải sẵn sàng **trước** mốc đó để còn thời gian aggregate và commit:

~~~text
Parent completion deadline : 10:00:00
Inventory child deadline   : 09:59:45
Payment child deadline     : 09:59:45
Fraud check deadline       : 09:59:50
Aggregation/commit budget  : 10 giây
~~~

Đây là budget ví dụ, không phải chính sách cố định. Quan trọng là:

- Message con giữ `parentDeadlineAt` và `correlationId`.
- Mỗi child có `deadlineAt` riêng phù hợp chi phí nhánh.
- Không tự “gia hạn thêm 30 giây” cho mỗi message con khiến toàn workflow vượt parent deadline.
- Mỗi child có `childEventId` ổn định để chống xử lý lặp.
- Khi Aggregator timeout/partial release, phải định nghĩa kết quả hợp lệ, retry, cancel hoặc compensation.

**Group timeout không nhất thiết bằng business deadline.** `Aggregator` có release strategy, timeout và message store riêng; trường hợp child đến trễ cần xử lý theo domain, không dựa vào correlation để mong side effect các nhánh tự rollback.

### Một nhánh đã commit, nhánh khác trễ

Nếu Reserve Stock đã commit DB nhưng Payment Verify quá hạn, Aggregator không thể tự rollback một transaction đã kết thúc ở worker khác. Có thể cần command mới `ReleaseReservation`, ghi state workflow và retry hành động bù trừ. Đó là **Saga/compensation**, không phải JDBC rollback kéo dài qua broker.

## 16. Deadline và TTL của JMS, RabbitMQ, Kafka

| Resource | Priority | TTL/expiration hoặc retention | Business deadline |
| --- | --- | --- | --- |
| **JMS** | `JMSPriority` của message; broker/provider quyết định semantics. | Producer TTL/JMS expiration theo provider. | Cần lưu mốc nghiệp vụ riêng nếu yêu cầu completion. |
| **RabbitMQ/AMQP** | Message priority property trên queue hỗ trợ. | Message/queue TTL và dead-letter theo policy. | Custom timestamp và gate/handler dùng mốc đó. |
| **Kafka** | Header custom không reorder record theo priority trong partition. | Retention của topic/log. | Truyền trong record header/payload, xác thực lại ở consumer. |
| **JDBC-backed MessageStore** | Có thể sắp theo priority nếu loại store hỗ trợ. | Cleanup hoặc expiry tùy cấu hình. | Cần chính sách ứng dụng, không tự có deadline scheduler. |
| **HTTP** | Header ứng dụng không tạo broker priority. | Request timeout và connection timeout. | API contract tách biệt và có status cuối cùng. |

### JMS: TTL không bảo đảm business commit

Message gửi lúc 09:59:00 với TTL 60 giây có thể được giao lúc 09:59:59; consumer xử lý đến 10:00:30. **Message được deliver khi còn TTL nhưng nghiệp vụ vẫn hoàn tất muộn.** Nếu consumer đã nhận message thì expiration không tự kéo ngược kết quả DB đã commit.

### RabbitMQ: TTL và priority cùng tồn tại nhưng độc lập

Message HIGH có thể hết TTL trước khi được consumer xử lý nếu queue quá tải. Message LOW đã được **prefetch** trước khi HIGH đến cũng không tự được thu hồi về queue để HIGH chạy trước. Kiểm tra broker property priority, `x-max-priority` của queue hỗ trợ, prefetch và TTL/expiration **tách riêng**.

### Kafka: retention không phải deadline

Kafka giữ record theo partition/offset; `deadlineAt` trong record header không khiến broker đảo thứ tự offset. Muốn xử lý HIGH gần deadline trước, cần phân nhóm/consumer pool hoặc scheduler ở tầng ứng dụng mà vẫn tôn trọng ordering của aggregate.

### Truyền absolute deadline, không chỉ remainingMillis

~~~text
Producer lúc 09:59:55: remainingMillis = 5000
Record chờ broker 4 giây
Consumer nhận lúc 09:59:59

Nếu consumer đọc remainingMillis=5000 cũ -> sai!
Phải đọc deadlineAt=10:00:00 và tính lại còn 1 giây.
~~~

Đồng bộ clock giữa các node là điều kiện vận hành quan trọng. Với hệ thống phân tán, cần đo và cảnh báo clock skew, đồng thời chọn một nguồn thời gian nhất quán cho các quyết định có hậu quả tài chính.

## 17. Retry và redelivery tiêu thụ thời gian còn lại

Một message có deadline 9 giây kể từ lúc bắt đầu:

~~~text
Attempt 1: 3 giây -> lỗi tạm thời
Backoff:   2 giây
Attempt 2: 3 giây -> lỗi
Backoff:   4 giây

Nếu retry tiếp thì đã vượt deadline.
~~~

Nên có:

- Giới hạn số attempt.
- Backoff, jitter và retry budget theo deadline.
- `businessEventId` ổn định qua retry/redelivery.
- Phân loại lỗi tạm thời/vĩnh viễn/không rõ kết quả.
- Expired outcome khi không còn đủ ngân sách xử lý.
- DLQ/quarantine có thể quan sát và replay có kiểm soát.

Hàm kiểm tra *ước lượng còn kịp*:

~~~java
static boolean canRetry(
        Instant deadline,
        Instant now,
        Duration backoff,
        Duration estimatedDuration) {
    return !now.plus(backoff)
            .plus(estimatedDuration)
            .isAfter(deadline);
}
~~~

Unit test:

~~~java
@Test
void retryRespectsRemainingDeadlineBudget() {
    Instant now = Instant.parse("2026-01-01T10:00:00Z");
    Instant deadline = now.plusSeconds(5);

    assertTrue(canRetry(
            deadline, now,
            Duration.ofSeconds(1),
            Duration.ofSeconds(2)));

    assertFalse(canRetry(
            deadline, now,
            Duration.ofSeconds(4),
            Duration.ofSeconds(2)));
}
~~~

`canRetry` chỉ dùng estimate; thực tế vẫn có thể chạy quá hạn. Nếu một attempt đã commit ở DB nhưng ACK từ broker bị mất, source có thể redeliver sau deadline. Consumer phải kiểm tra **idempotency và kết quả commit trước đó**, không chỉ thấy expired là coi business operation chưa từng chạy.

### Error channel và expired không phải một loại lỗi duy nhất

Khi một handler ném lỗi, Spring Integration có thể tạo `ErrorMessage` chuyển tới `errorChannel` theo adapter/configuration. Payload lỗi thường là exception; nếu cần metadata của message gốc, phải truy xuất failed message hoặc giữ snapshot riêng. Các trạng thái nên phân biệt:

| Trạng thái | Ngữ nghĩa |
| --- | --- |
| `EXPIRED_NOT_EXECUTED` | Không bắt đầu vì đã mất hiệu lực trước xử lý. |
| `COMPLETED_LATE` | Nghiệp vụ hoàn tất nhưng sau deadline. |
| `FAILED_RETRY_EXHAUSTED` | Retry hết ngân sách/số lần. |
| `CANCELLED` | Chủ thể có quyền đã hủy. |
| `NEEDS_RECONCILIATION` | Không biết side effect từ timeout/network đã xảy ra hay chưa. |

Không đưa mọi message hết hạn vào retry queue HIGH vô hạn. Đó là cách làm tăng starvation, backlog và số deadline miss cho những message còn giá trị.

## 18. Gateway timeout không tự cancel worker

~~~mermaid
sequenceDiagram
    participant Client
    participant Gateway
    participant Worker
    participant DB
    Client->>Gateway: Request(eventId, deadline=T)
    Gateway->>Worker: Dispatch async
    Note over Gateway: Reply timeout
    Gateway-->>Client: Timeout
    Worker->>DB: Business COMMIT after T
    Note over Client,DB: Timeout không tự rollback commit
~~~

Trường hợp này có thể tạo double effect nếu client retry với event ID mới. Để thiết kế an toàn:

1. Dùng **idempotency key** ổn định cho cùng business request.
2. Có API tra cứu trạng thái cuối khi client timeout.
3. Nếu cho phép cancel, ghi intent hủy và worker kiểm tra trước điểm side effect quan trọng.
4. Nếu đã gửi email, gọi API hoặc commit payment, có thể cần compensation.
5. Xác định deadline áp cho bắt đầu, commit hay việc gửi reply.

Một thread bị interrupt hoặc Gateway bị timeout không thể thu hồi một side effect đã commit ở tài nguyên khác.

## 19. Cửa sổ giữa kiểm tra deadline và commit

~~~text
09:59:59.900 -> DeadlineGate: còn 100 ms
09:59:59.950 -> bắt đầu transaction
10:00:00.100 -> cập nhật database
10:00:00.300 -> COMMIT

Deadline = 10:00:00
~~~

Gate cho qua trước deadline nhưng kết quả **hoàn tất sau hạn**. Nếu nghiệp vụ không cho phép xác nhận sau mốc:

- Kiểm tra domain state và deadline càng gần điểm side effect quan trọng càng tốt.
- Dùng điều kiện cập nhật **nguyên tử** tại storage để giảm race.
- Kiểm tra số row ảnh hưởng và phân biệt expired/already processed/not found.
- Không tự coi một SQL statement chạy đúng hạn là cam kết **transaction commit** trước deadline nếu commit có thể đến sau.
- Ghi nhận `completedAt` thực tế theo định nghĩa đã công bố.

Ví dụ PostgreSQL/JDBC:

~~~sql
UPDATE reservations
   SET state = 'CONFIRMED'
 WHERE reservation_id = ?
   AND state = 'PENDING'
   AND expires_at > CURRENT_TIMESTAMP;
~~~

Nếu update 0 row, cần xác minh trạng thái thay vì retry mù quáng. Clock tại database và tại ứng dụng có thể khác; nếu yêu cầu giao dịch tài chính chặt, phải xác định hệ thống **nào làm nguồn thời gian quyết định**.

## 20. Priority starvation, fairness và capacity

Khi nhiều HIGH có deadline xa liên tục chiếm worker, LOW cận hạn có thể trễ. Khi một lượng LOW khổng lồ đều tự nhận deadline sớm, EDF lại có thể làm HIGH không tiến triển. Vì vậy cần kết hợp:

- Priority được phân loại từ policy tin cậy.
- Deadline chỉ được gán trong giới hạn được cấp quyền.
- Fair scheduling/weighted quota khi yêu cầu các lớp đều tiến triển.
- Deadline override có giới hạn.
- Reserved capacity hoặc bulkhead cho nhánh quan trọng.
- Backpressure và admission control khi không đủ công suất.

**Không algorithm nào bảo đảm deadline bất khả thi**. Nếu có 100 task, mỗi task chiếm một worker 10 giây, một worker không thể hoàn tất tất cả trong 60 giây, dù dùng EDF, LST hay strict priority. Hệ thống phải tăng worker, giảm tải hoặc thương lượng deadline.

### Fairness khác backlog ổn định

Scheduler 4:2:1 cho LOW một phần bảy **suất chọn** khi cả ba queue liên tục có backlog. Nếu tốc độ LOW đến lớn hơn năng lực xử lý trong một phần bảy suất đó trong thời gian dài, backlog LOW vẫn tăng và các deadline có thể liên tục bị miss. Cần đo thêm processing cost và capacity, không chỉ đếm số lượt.

## 21. Kiểm thử nhiều tình huống priority/deadline

| Kịch bản | Điều cần assert | Không được mặc định |
| --- | --- | --- |
| HIGH deadline xa, LOW sắp hạn | Policy deadline override chọn LOW nếu đã công bố. | Strict `PriorityChannel` tự làm điều này. |
| Cùng deadline, khác priority | Tie-breaker theo priority. | FIFO khi comparator không có tie-breaker. |
| LOW đã được nhận, HIGH đến sau | Không preempt handler đang chạy. | HIGH hoàn tất trước trong mọi trường hợp. |
| Task expired từ trước | Có expired outcome và audit. | Filter bỏ task là xử lý đầy đủ. |
| Negative slack | Metric/decision thể hiện rủi ro không khả thi. | Estimate luôn chính xác. |
| Gateway reply timeout | Worker có thể chạy tiếp, kết quả phải reconcile. | Client timeout tự rollback DB. |
| Splitter một child trễ | Aggregator timeout/partial/compensation theo policy. | Correlation gom chung transaction các worker. |
| Retry backoff vượt budget | Dừng retry theo policy hết hạn. | Retry tự kéo dài deadline. |
| Broker TTL hết | Broker expiration xử lý theo cấu hình. | TTL là deadline hoàn tất nghiệp vụ. |
| Clock lệch giữa node | Chuẩn hóa timestamp và theo dõi skew. | Chuỗi local time giống nghĩa trên mọi node. |
| HIGH liên tục, LOW gần hạn | Deadline override/fairness được kiểm thử với HIGH luôn backlog. | Test khi HIGH queue rỗng là đủ. |
| Overload kéo dài | Admission control, scale hoặc trạng thái không đạt deadline. | EDF bảo đảm mọi việc đúng hạn. |

### Kiểm thử không dựa vào sleep dài

Sử dụng `Clock.fixed`/`Clock.offset` trong unit test. Với thread concurrency, dùng `CountDownLatch`/bounded await để điều khiển điều kiện xuất hiện task. Unit test selector không chứng minh ACK, redelivery hoặc khôi phục sau crash; cần integration test với broker/JDBC store thật nếu đó là yêu cầu production.

## 22. Quan sát vận hành: đo hai trục độc lập

Một trace có thể gồm:

~~~text
eventId = E-17
correlationId = ORDER-17
priorityAssigned = 1
deadlineAt = 2026-11-21T10:00:00Z
enqueuedAt = 2026-11-21T09:59:45Z
startedAt = 2026-11-21T09:59:55Z
completedAt = 2026-11-21T10:00:03Z
outcome = COMPLETED_LATE
latenessSeconds = 3
~~~

| Metric | Đo gì |
| --- | --- |
| `queue_wait_seconds{class}` | Độ trễ trước khi handler bắt đầu. |
| `end_to_end_latency_seconds{type}` | Từ nghiệp vụ phát sinh đến kết quả cuối. |
| `deadline_miss_total{type,class}` | Tác vụ không đạt deadline theo định nghĩa domain. |
| `remaining_budget_at_start_seconds{type}` | Thời gian còn lại khi bắt đầu. |
| `negative_slack_total{type}` | Task được nhận khi estimate đã không khả thi. |
| `completed_late_total{type}` | Công việc hoàn tất nhưng quá hạn. |
| `expired_without_execution_total{type}` | Công việc được quyết định expired trước khi chạy. |
| `oldest_pending_age_seconds{class}` | Tìm starvation và backlog. |
| `retry_total{type,reason}` | Retry đang tiêu tốn deadline ra sao. |
| `timeout_total{endpoint}` | Timeout kỹ thuật, khác business miss. |

**Cảnh báo minh họa:**

~~~text
IF deadline_miss_rate > agreed_SLO:
    alert("Business deadline SLO missed")

IF LOW_pending > 0 AND LOW_completed_last_60s == 0:
    alert("Possible LOW starvation")

IF remaining_budget_p10 < processing_time_p90:
    alert("Queued work may not meet deadlines")
~~~

Không gắn một `eventId` duy nhất vào nhãn metric cardinality cao; dùng trace/log có kiểm soát để tra ID. Không log payload nhạy cảm nếu không cần.

## 23. Anti-pattern phổ biến

| Anti-pattern | Vì sao sai | Cách đúng hơn |
| --- | --- | --- |
| Gắn `priority=9` rồi coi như có deadline. | Priority chỉ là ordering tương đối. | Lưu deadline riêng và xác định mốc completion. |
| Gắn `deadlineAt` rồi chờ `PriorityChannel` mặc định hiểu. | Channel không đọc custom deadline. | Comparator EDF hoặc scheduler deadline-aware. |
| Dùng TTL broker làm SLA hoàn tất. | Broker expiration khác business commit. | Phân biệt TTL/expiration và deadline nghiệp vụ. |
| Coi Gateway timeout là worker bị hủy. | Async worker có thể vẫn chạy. | Idempotency, cancel contract và status API. |
| Mỗi lần retry tính lại `now+30s`. | Gia hạn deadline vô hạn. | Giữ absolute deadline gốc. |
| Comparator đọc đồng hồ và kỳ vọng heap tự reorder. | Heap không tự cập nhật mọi phần tử. | Promotion/re-selection rõ ràng. |
| Lọc message expired rồi bỏ đi không ghi nhận. | Không có audit hoặc business outcome. | Mark EXPIRED/reconcile/quarantine theo policy. |
| Kiểm tra deadline trước handler rồi khẳng định commit đúng hạn. | Handler có thể vượt deadline. | Check business storage, đo completion thực. |
| Cho client tự đặt deadline cực gấp. | Lạm dụng tài nguyên, deadline gaming. | Authz, quota, giới hạn deadline. |
| Nghĩ EDF luôn đáp ứng mọi deadline. | Overload và duration sai. | Feasibility, scaling, backpressure. |
| Splitter tự kéo dài deadline mỗi child. | Vượt parent deadline end-to-end. | Phân bổ ngân sách từ deadline gốc. |
| Dùng deadline làm khóa dedupe. | Nhiều event có cùng deadline, retry thay mốc. | `eventId` ổn định riêng. |

## 24. Bài tập thực hành

**Bài 1 — strict priority so với EDF.** Tạo một `PriorityChannel` mặc định, cho A(HIGH, deadline sau 30 phút) và B(LOW, deadline sau 20 giây). Kiểm thử thứ tự khi cả hai đã enqueue, rồi thay bằng comparator EDF; giải thích khác biệt.

**Bài 2 — least slack.** Cho A còn 15 giây, xử lý 1 giây; B còn 18 giây, xử lý 17 giây. Tính slack và lựa chọn theo LST. Phân tích nếu estimate sai 50%.

**Bài 3 — deadline override.** Dùng `DeadlineAwareSelector` với ba HIGH hạn xa, một LOW cận hạn, hai NORMAL. Test khi có task urgent và khi không có. Bổ sung nhánh xử lý task expired.

**Bài 4 — metadata propagation.** Gateway → Transformer → Router → PriorityChannel → Service Activator. Kiểm tra `priority`, `deadlineAt` và `businessEventId` ở mỗi điểm. Cố tình tạo Transformer mất deadline rồi viết test phát hiện.

**Bài 5 — Splitter/Aggregator.** Parent hạn 10:00:00, ba nhánh inventory/payment/fraud. Phân bổ budget cho từng nhánh và Aggregator, giả lập một nhánh trễ; quyết định partial result, cancel và compensation.

**Bài 6 — retry.** Deadline còn 5 giây, backoff 4 giây và attempt cần 2 giây. Test `canRetry` trả false. Thêm phân biệt retry sau lỗi tạm thời với expired outcome.

**Bài 7 — broker TTL.** Publish message có business deadline 40 giây và broker TTL 10 giây. Kiểm tra outcome và giải thích vì sao TTL không được dùng như deadline completion.

**Bài 8 — completion và timeout.** Một worker xử lý LOW 30 giây, HIGH tới giữa chừng; Gateway timeout trước khi DB commit. Xác định điều gì đã hoàn tất, điều gì chưa, và cách client retry an toàn.

**Bài 9 — overload.** Một worker, 100 task × 10 giây CPU, deadline 60 giây. Đề xuất admission control, capacity hoặc thương lượng deadline; không giả định thuật toán nào có thể làm điều bất khả thi.

### Câu hỏi tự đánh giá

**1. Priority có tương đương deadline không?** Không. Priority là mức quan trọng tương đối, deadline là mốc ràng buộc thời gian.

**2. `PriorityChannel` có tự đọc `deadlineAt` custom không?** Không trong cấu hình priority mặc định.

**3. EDF bảo đảm mọi deadline khi tải cao không?** Không; còn phụ thuộc feasibility, worker capacity, duration, lỗi và network.

**4. TTL của broker có nghĩa kết quả nghiệp vụ đã hoàn tất trước hạn không?** Không. TTL áp dụng cho message/resource.

**5. Vì sao nên gửi absolute deadline qua nhiều service?** Vì remaining duration được tính một lần không tự giảm theo thời gian message chờ ở broker/network.

**6. Check deadline trước handler có đủ không?** Không, handler và commit vẫn có thể hoàn tất sau deadline.

**7. Aggregator có tự rollback các nhánh đã commit khi một child quá hạn không?** Không, cần policy và compensation nếu phù hợp.

**8. Khi nào một LOW nên được chọn trước HIGH?** Khi business policy cho phép deadline override và LOW sắp hết hạn trong khi HIGH còn dư thời gian.

## 25. Checklist trước production

- [ ] Định nghĩa riêng priority, deadline, TTL/expiration, timeout và scheduled time.
- [ ] Xác định deadline áp cho **bắt đầu**, **commit** hay **end-to-end completion**.
- [ ] Dùng absolute UTC deadline; không reset khi retry/redelivery.
- [ ] Validate quyền đặt priority và deadline tại ingress; có quota theo tenant.
- [ ] Giữ `eventId`, `correlationId`, `deadlineAt` và `originalEnqueuedAt` qua EIP/adapter.
- [ ] Chọn rõ strict priority, EDF, LST, deadline override, WRR hoặc reserved capacity.
- [ ] Nếu dùng comparator heap, tránh phụ thuộc vào clock thay đổi mà không có re-evaluation.
- [ ] Có trạng thái expired outcome theo loại nghiệp vụ; không silent drop.
- [ ] Kiểm tra feasibility bằng remaining budget và estimated duration.
- [ ] Kiểm soát side effect sau deadline tại boundary business/storage quan trọng.
- [ ] Phân bổ budget cho các child của Splitter, Aggregator và Gateway.
- [ ] Test Gateway timeout với worker vẫn đang chạy; có idempotency/cancellation contract.
- [ ] Retry hữu hạn, tính backoff vào deadline, có DLQ/reconcile.
- [ ] Với JMS/RabbitMQ/Kafka, kiểm tra priority property, TTL/retention và business deadline **riêng**.
- [ ] Sử dụng durable source, ACK/redelivery, idempotent consumer nếu message quan trọng.
- [ ] Có unit test dùng `Clock.fixed`, integration test concurrency/crash và overload.
- [ ] Giám sát completion latency, deadline miss, negative slack, backlog và starvation.
- [ ] Có admission control hoặc scale khi tải lớn hơn năng lực đáp ứng.

**Ghi nhớ:** **Priority quyết định ai được chọn trước; deadline quyết định kết quả cần có trước khi nào.** `PriorityChannel` giúp sắp xếp thông điệp còn chờ, nhưng không phải một hệ thống bảo đảm đúng hạn. Trong Spring Integration, cần thêm contract deadline chuẩn, thuật toán scheduling có chủ đích, xử lý expired, transaction/ACK, retry có ngân sách, idempotency và đo mốc **nghiệp vụ thực sự hoàn tất**.

### Tài liệu nên đối chiếu với phiên bản đang dùng

- Spring Integration Reference: Message Channels, `PriorityChannel`, Polling Consumer và Delayer.
- Spring Integration Reference: Gateway, Transformer, Router, Splitter, Aggregator và Error Handling.
- Spring Framework Reference: Transaction Management, Timeouts và Scheduling.
- JMS Specification: Message Priority, TTL/Expiration.
- RabbitMQ Documentation: Priority Queues, TTL, Dead Lettering, Prefetch.
- Apache Kafka Documentation: Record Headers, Partition Ordering, Offset và Retention.

*Các đoạn Java là ví dụ từng phần để minh họa thiết kế và kiểm thử; khi đưa vào dự án cần bổ sung class/import, wire adapter và test theo phiên bản Spring Integration thực tế. Chưa thực hiện Content QA chuyên môn, Gradle hoặc STEP khác theo hướng dẫn Worker.*
