# Ưu tiên cao làm message khác chờ lâu: Starvation trong Spring Integration

## 1. Vấn đề: message ưu tiên thấp có thể đợi rất lâu

Trong hệ thống tích hợp thông điệp, việc đưa yêu cầu khẩn cấp lên trước là hợp lý: một sự cố sản xuất cần được xử lý nhanh hơn tác vụ tổng hợp báo cáo. Tuy nhiên, nếu các message ưu tiên cao đến liên tục, message ưu tiên thấp có thể **không bao giờ được lấy khỏi hàng đợi**, dù nó đã đợi trước đó từ lâu. Hiện tượng này gọi là **starvation** (thiếu cơ hội được phục vụ).

Đây là bài học thuộc chương **Priority** của module **SPRING_INTEGRATION_PATTERN**. Module hướng đến việc triển khai Enterprise Integration Patterns với Spring Integration để xây dựng luồng thông điệp ít phụ thuộc, dễ mở rộng, kết hợp Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel và correlation, đồng thời kiểm thử và theo dõi các nhánh xử lý. Khi thêm **Priority Channel** vào một luồng như vậy, ta cần quan tâm không chỉ *message khẩn có đi trước không* mà còn *message bình thường có được xử lý trong thời gian chấp nhận được không*.

Ví dụ hàng đợi \`PriorityChannel\` của Spring Integration sử dụng header \`priority\` để ưu tiên lấy message có giá trị lớn hơn:

~~~text
Thời điểm    Message được enqueue                 Message được lấy tiếp
---------    ----------------------------------   ----------------------
t0           L: priority=1                        (chưa poll)
t1           H1: priority=9                       H1
t2           H2: priority=9                       H2
t3           H3: priority=9                       H3
t4           H4: priority=9                       H4
...          ...                                  ...

Message L vẫn nằm trong queue, dù đến trước tất cả H1, H2, ...
~~~

**Ý chính:** \`PriorityChannel\` quyết định **thứ tự lấy các message còn đang chờ**. Nó không đảm bảo công bằng (fairness), không tự nâng ưu tiên cho message chờ lâu và không thu hồi công việc mà consumer đã lấy trước đó.

Sau bài này, bạn có thể:

1. Giải thích vì sao priority nghiêm ngặt có thể gây starvation.
2. Phân biệt thời gian chờ trong queue với thời gian xử lý của handler và thứ tự hoàn tất.
3. Tạo test tái hiện message thấp bị vượt qua nhiều lần bằng \`PriorityChannel\`.
4. Chọn chính sách hạn mức, chia queue, aging hoặc SLA phù hợp.
5. Viết và kiểm thử một lịch lấy message đơn giản bảo đảm nhóm thấp vẫn có lượt xử lý.
6. Thiết kế metric, cảnh báo và kịch bản kiểm thử tải để phát hiện starvation trước khi vận hành thực tế.

## 2. Phân biệt Priority, Fairness và Starvation

Ba khái niệm này liên quan nhưng không đồng nghĩa:

| Khái niệm | Câu hỏi chính | Ví dụ |
| --- | --- | --- |
| **Priority** | Khi có nhiều message đang đợi, lấy message nào trước? | Ưu tiên \`9\` hơn \`1\` |
| **Fairness** | Các nhóm công việc có nhận được cơ hội xử lý hợp lý không? | Sau tối đa ba lượt khẩn, dành một lượt cho nhóm thường nếu nhóm này có việc |
| **Starvation** | Một nhóm có thể đợi không giới hạn khi nhóm khác luôn có việc không? | Message \`1\` bị đẩy lùi bởi chuỗi \`9\` liên tục |

Một thuật toán ưu tiên tuyệt đối có thể **đúng về thứ tự** mà vẫn **không đáp ứng SLA** của nghiệp vụ. Vì vậy, yêu cầu “message khẩn đi trước” cần được bổ sung bằng yêu cầu như “message thông thường không được chờ quá 30 giây ở tải thiết kế”.

### Không nhầm với các vấn đề khác

- **Backpressure:** Producer gửi nhanh hơn hệ thống tiêu thụ khiến queue tăng hoặc đầy; starvation có thể xuất hiện ngay cả khi tổng queue chưa đầy.
- **Priority inversion:** Công việc ưu tiên cao bị chặn bởi tài nguyên đang bị công việc ưu tiên thấp nắm giữ. Đây là vấn đề về phụ thuộc và khóa tài nguyên, khác starvation do lịch lấy từ queue.
- **Deadlock:** Các tác vụ chờ nhau theo vòng và không tiến triển. Starvation có thể xảy ra khi **vẫn có nhiều tác vụ khác hoàn tất bình thường**.
- **Slow handler:** Message đã được lấy nhưng xử lý quá lâu. Metric thời gian chờ queue và thời gian xử lý handler phải được tách riêng để chẩn đoán đúng.

## 3. Cơ chế gây starvation trong PriorityChannel

Spring Integration cung cấp \`PriorityChannel\`, một \`PollableChannel\`. Với cơ chế so sánh mặc định, header \`IntegrationMessageHeaderAccessor.PRIORITY\` có giá trị \`Integer\` càng cao thì message càng có cơ hội được **lấy trước**.

~~~mermaid
flowchart TD
    P["Producer"] -->|"priority=1"| Q["PriorityChannel"]
    P -->|"priority=9 liên tục"| Q
    Q -->|"Poll chọn message ưu tiên cao"| H["Service Activator"]
    H --> OUT["Output"]
    Q -.->|"Message mức 1 tiếp tục chờ"| L["Thời gian chờ tăng"]
    L --> ALERT["Có thể vi phạm SLA"]
~~~

Tại mỗi lần poll, nếu queue đang có cả message mức \`9\` và \`1\`, message \`9\` được chọn. Khi tải ưu tiên cao đủ lớn để luôn còn message \`9\` trong queue, message \`1\` có thể không được phục vụ.

### Điều kiện quan trọng

Starvation không có nghĩa **mọi message ưu tiên thấp đều sẽ chờ mãi**. Nếu backlog ưu tiên cao được xử lý hết, nhóm thấp có cơ hội tiếp tục. Nguy cơ xảy ra khi **nguồn ưu tiên cao luôn duy trì backlog**, hoặc tiêu thụ tài nguyên đến mức không còn năng lực dành cho nhóm khác.

Giả sử một consumer xử lý được trung bình 20 message/giây:

| Tình huống | Message ưu tiên cao đến | Năng lực còn lại theo phép tính đơn giản | Hàm ý |
| --- | --- | --- | --- |
| A | 5 message/giây | Khoảng 15 message/giây | Nhóm thấp thường còn cơ hội |
| B | 18 message/giây | Khoảng 2 message/giây | Nhóm thấp có thể chờ dài khi có backlog |
| C | 22 message/giây | Không còn năng lực dư | Backlog ưu tiên cao có xu hướng tăng; nhóm thấp có nguy cơ không được lấy |

Đây chỉ là mô hình minh họa với giả định thời gian xử lý trung bình đồng nhất và năng lực cố định. Trong thực tế, handler có thể khác độ phức tạp, retry, I/O và số worker; cần đo **tốc độ vào, tốc độ ra và độ trễ** theo từng nhóm thay vì dựa hoàn toàn vào trung bình.

### Thứ tự lấy khác thứ tự hoàn tất

Ngay cả khi message mức \`9\` được lấy khỏi queue trước, một \`ExecutorChannel\` hoặc handler bất đồng bộ vẫn có thể khiến message khác hoàn tất sớm hơn. Priority Channel không tự cung cấp:

- Hủy một tác vụ ưu tiên thấp đang chạy.
- Bảo đảm thứ tự hoàn tất của nhiều worker.
- Bảo đảm exactly-once, idempotency hoặc xử lý lỗi.
- Bảo đảm mọi nhóm ưu tiên đều có một lượt xử lý trong thời hạn nhất định.

## 4. Ví dụ kiểm thử tái hiện starvation có kiểm soát

Kiểm thử starvation thực sự là kiểm thử **liveness** (khả năng tiếp tục được phục vụ). Không nên tạo test vô hạn. Thay vào đó, mô phỏng một số vòng ưu tiên cao liên tục và kiểm tra rằng message mức thấp tiếp tục bị giữ lại.

Ví dụ dùng Java 17, JUnit 5, AssertJ và Spring Integration 6.x, không cần broker, database hoặc poller. Với dự án Spring Boot, bạn có thể dùng các dependency tương thích:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-integration</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Tạo lớp \`src/test/java/example/PriorityStarvationTest.java\`:

~~~java
package example;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.integration.IntegrationMessageHeaderAccessor;
import org.springframework.integration.channel.PriorityChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

class PriorityStarvationTest {

    static Message<String> work(String id, int priority) {
        return MessageBuilder.withPayload(id)
                .setHeader(IntegrationMessageHeaderAccessor.PRIORITY, priority)
                .setHeader("requestId", id)
                .build();
    }

    static String next(PriorityChannel channel) {
        Message<?> message = channel.receive(1_000);
        assertThat(message).isNotNull();
        return (String) message.getPayload();
    }

    @Test
    void priority_high_is_polled_before_low_when_both_are_waiting() {
        PriorityChannel channel = new PriorityChannel(10);

        channel.send(work("low", 1));
        channel.send(work("high", 9));

        assertThat(next(channel)).isEqualTo("high");
        assertThat(next(channel)).isEqualTo("low");
        assertThat(channel.receive(0)).isNull();
    }

    @Test
    void repeated_high_arrivals_can_keep_low_waiting() {
        PriorityChannel channel = new PriorityChannel(20);

        channel.send(work("low-original", 1));
        for (int round = 1; round <= 8; round++) {
            String highId = "high-" + round;
            channel.send(work(highId, 9));

            // Ở mỗi lượt poll đều có high và low đang chờ.
            assertThat(next(channel)).isEqualTo(highId);
        }

        // Mức thấp vẫn nguyên vẹn sau tám lượt bị vượt qua.
        Message<?> low = channel.receive(1_000);
        assertThat(low).isNotNull();
        assertThat(low.getPayload()).isEqualTo("low-original");
        assertThat(low.getHeaders().get("requestId"))
                .isEqualTo("low-original");
        assertThat(channel.receive(0)).isNull();
    }

    @Test
    void high_priority_does_not_preempt_a_message_already_taken() {
        PriorityChannel channel = new PriorityChannel(10);
        channel.send(work("low-already-taken", 1));

        Message<?> started = channel.receive(1_000);
        assertThat(started.getPayload()).isEqualTo("low-already-taken");

        // Consumer đã lấy low; high không thể quay ngược thời gian.
        channel.send(work("urgent-new", 9));
        assertThat(next(channel)).isEqualTo("urgent-new");
    }
}
~~~

Test \`repeated_high_arrivals_can_keep_low_waiting\` cho thấy **tám lần trì hoãn liên tiếp**, đủ để chứng minh rủi ro. Nó **không** chứng minh chờ vô hạn bằng quan sát hữu hạn. Khẳng định đúng về mặt thiết kế là: nếu tại mỗi lần poll luôn tồn tại message có priority cao hơn, thuật toán ưu tiên nghiêm ngặt có thể tiếp tục chọn message cao và không tạo lượt cho message thấp.

**Vì sao test này ổn định?** Mỗi test tạo một channel riêng, dùng một thread để gửi và nhận, không có poller chạy song song. Vì vậy kết quả không phụ thuộc lịch thread. Nếu chuyển sang flow với poller đang hoạt động, cần kiểm soát thời điểm tạo backlog trước khi khẳng định thứ tự.

## 5. Thiết kế chính sách phục vụ công bằng

Không có một chiến lược chung cho mọi nghiệp vụ. Chọn chính sách dựa trên mức khẩn, SLA, số lượng message, thời gian xử lý và hậu quả nếu message thông thường chờ lâu.

| Chiến lược | Cách hoạt động | Phù hợp khi | Giới hạn |
| --- | --- | --- | --- |
| **Ưu tiên tuyệt đối** | Luôn lấy mức cao nhất | Công việc cấp cứu, mục tiêu cao nhất là độ trễ nhóm khẩn | Nguy cơ starvation mức thấp |
| **Weighted scheduling** | Phân chia lượt, ví dụ ba high rồi một low | Cần ưu tiên nhưng có tiến độ cho mọi nhóm | High không luôn đi trước mọi low |
| **Queue riêng + worker quota** | Dành một phần worker cho từng nhóm | Có tải đủ lớn và SLA riêng | Tốn tài nguyên, phải điều chỉnh quota |
| **Aging** | Chờ lâu thì tăng quyền ưu tiên theo quy tắc | Muốn ưu tiên khẩn nhưng không bỏ đói nhóm thấp | Phải thiết kế cách cập nhật và sắp xếp lại |
| **Deadline-aware scheduling** | Xem xét deadline hoặc thời gian còn lại đến SLA | Có hạn xử lý rõ ràng | Cần timestamp, deadline đáng tin cậy |
| **Giới hạn nguồn high** | Rate limit hoặc admission control | Một nguồn khẩn có thể chiếm toàn bộ queue | Cần quyết định message vượt giới hạn sẽ đi đâu |

Các giải pháp có thể kết hợp. Ví dụ: Router tách \`urgent\` và \`normal\` vào hai queue, scheduler cho urgent ba lượt rồi normal một lượt, sau đó áp dụng rate limit tại nguồn nếu urgent quá tải.

### Bảo đảm nào là thực tế?

Với mô hình **một consumer tuần tự** và quy tắc “tối đa ba lần lấy high liên tiếp nếu queue low có việc”, một message low đã nằm đầu queue sẽ được chọn **muộn nhất sau ba lượt high tiếp theo**, với điều kiện scheduler tiếp tục được gọi và không dừng vì lỗi. Đây là bảo đảm theo **số lượt điều phối**, không phải cam kết cố định theo mili giây.

Nếu mỗi tác vụ high đôi khi chạy hàng phút, ba lượt high có thể vẫn khiến low chờ rất lâu. Để có giới hạn thời gian chờ, cần thêm timeout, giới hạn thời gian xử lý, năng lực dự phòng hoặc ưu tiên theo deadline.

## 6. Ví dụ scheduler có hạn mức ba high, một low

Một cách đơn giản để giảm starvation là dùng **hai QueueChannel FIFO riêng**, rồi chọn từ queue nào sẽ được lấy tiếp. Đây là cơ chế điều phối ở **bên ngoài \`PriorityChannel\`**, không phải tính năng fairness tự động của Spring Integration.

~~~mermaid
flowchart LR
    IN["Input / Router"] -->|"URGENT"| HQ["urgent.queue"]
    IN -->|"NORMAL"| LQ["normal.queue"]
    HQ --> S{"Quota Scheduler\nmax 3 urgent"}
    LQ --> S
    S --> H["Handler"]
    H --> OUT["Output"]
~~~

Dưới đây là lớp Java có thể chạy độc lập. Nó phục vụ queue normal sau tối đa ba lần lấy urgent liên tiếp **nếu normal đang có message**, còn khi một queue rỗng thì tận dụng queue kia.

~~~java
package example;

import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;

final class QuotaScheduler {

    private final QueueChannel urgent;
    private final QueueChannel normal;
    private final int maxUrgentStreak;
    private int urgentStreak;

    QuotaScheduler(
            QueueChannel urgent,
            QueueChannel normal,
            int maxUrgentStreak) {
        if (maxUrgentStreak < 1) {
            throw new IllegalArgumentException(
                    "maxUrgentStreak must be positive");
        }
        this.urgent = urgent;
        this.normal = normal;
        this.maxUrgentStreak = maxUrgentStreak;
    }

    // Giả định một thread duy nhất gọi pollNext().
    Message<?> pollNext() {
        if (urgentStreak >= maxUrgentStreak) {
            Message<?> fromNormal = normal.receive(0);
            if (fromNormal != null) {
                urgentStreak = 0;
                return fromNormal;
            }
            urgentStreak = 0;
        }

        Message<?> fromUrgent = urgent.receive(0);
        if (fromUrgent != null) {
            urgentStreak++;
            return fromUrgent;
        }

        Message<?> fromNormal = normal.receive(0);
        if (fromNormal != null) {
            urgentStreak = 0;
        }
        return fromNormal;
    }
}
~~~

Đây là một bộ điều phối **single-thread** để minh họa thuật toán. Khi nhiều thread cùng gọi \`pollNext()\`, biến \`urgentStreak\` cần được bảo vệ bằng cơ chế đồng bộ phù hợp; với nhiều instance ứng dụng, phải phối hợp quota ở cấp phân tán hoặc áp dụng chính sách theo từng instance một cách có chủ đích.

### Kiểm thử được bảo đảm theo lượt

Tạo lớp test:

~~~java
package example;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

class QuotaSchedulerTest {

    private static void enqueue(QueueChannel channel, String value) {
        assertThat(channel.send(
                MessageBuilder.withPayload(value).build())).isTrue();
    }

    private static String next(QuotaScheduler scheduler) {
        Message<?> message = scheduler.pollNext();
        assertThat(message).isNotNull();
        return (String) message.getPayload();
    }

    @Test
    void normal_gets_a_turn_after_three_urgent_dispatches() {
        QueueChannel urgent = new QueueChannel();
        QueueChannel normal = new QueueChannel();
        QuotaScheduler scheduler = new QuotaScheduler(urgent, normal, 3);

        enqueue(normal, "normal-1");
        for (int n = 1; n <= 6; n++) {
            enqueue(urgent, "urgent-" + n);
        }

        assertThat(next(scheduler)).isEqualTo("urgent-1");
        assertThat(next(scheduler)).isEqualTo("urgent-2");
        assertThat(next(scheduler)).isEqualTo("urgent-3");
        assertThat(next(scheduler)).isEqualTo("normal-1");
        assertThat(next(scheduler)).isEqualTo("urgent-4");
        assertThat(next(scheduler)).isEqualTo("urgent-5");
        assertThat(next(scheduler)).isEqualTo("urgent-6");
        assertThat(scheduler.pollNext()).isNull();
    }

    @Test
    void unused_normal_quota_does_not_block_urgent() {
        QueueChannel urgent = new QueueChannel();
        QueueChannel normal = new QueueChannel();
        QuotaScheduler scheduler = new QuotaScheduler(urgent, normal, 3);

        for (int n = 1; n <= 5; n++) {
            enqueue(urgent, "urgent-" + n);
        }

        for (int n = 1; n <= 5; n++) {
            assertThat(next(scheduler)).isEqualTo("urgent-" + n);
        }
        assertThat(scheduler.pollNext()).isNull();
    }

    @Test
    void normal_is_served_when_urgent_queue_is_empty() {
        QueueChannel urgent = new QueueChannel();
        QueueChannel normal = new QueueChannel();
        QuotaScheduler scheduler = new QuotaScheduler(urgent, normal, 3);

        enqueue(normal, "normal-only");
        assertThat(next(scheduler)).isEqualTo("normal-only");
        assertThat(scheduler.pollNext()).isNull();
    }
}
~~~

**Quan sát:** Dù urgent còn ba message khác, \`normal-1\` vẫn được chọn ở lượt thứ tư. Bài test không cần \`Thread.sleep()\`, không có thread race, và đo **quy tắc dispatch** thay vì đo trễ tường minh.

### Đưa chính sách vào Spring Integration

Trong một flow thật, Router có thể gửi vào hai channel \`urgent.queue\` và \`normal.queue\`. Một thành phần điều phối riêng lần lượt gọi \`receive\` trên hai channel, chuyển message được chọn tới channel đầu vào của Service Activator. Thiết kế production cần quyết định thêm:

1. Ai sở hữu lịch poll và cách dừng/khởi động scheduler?
2. Khi handler ném lỗi, quota có tính lần lấy thất bại hay không?
3. Khi một queue đầy, producer phải chờ, bị từ chối hay đi đường dự phòng?
4. Khi triển khai nhiều replica, quota được hiểu theo mỗi replica hay toàn hệ thống?
5. Làm sao quan sát backlog, độ trễ và chứng minh SLA khi tải cao?

Việc sử dụng hai queue với hai poller độc lập **chưa tự động** áp dụng quy tắc ba high rồi một low. Muốn cam kết quota như ví dụ, cần có một scheduler điều phối hoặc cơ chế chia tài nguyên có kiểm soát.

## 7. Aging: tăng cơ hội cho message chờ lâu

**Aging** là chính sách tăng quyền ưu tiên của message dựa trên thời gian chờ. Một mô hình khái niệm:

\[
P_{\mathrm{effective}} = P_{\mathrm{base}} + \alpha \times T_{\mathrm{waiting}}
\]

Trong đó:

- \(P_{\mathrm{base}}\): priority ban đầu theo nghiệp vụ.
- \(T_{\mathrm{waiting}}\): thời gian đã chờ, dùng cùng một đơn vị (ví dụ giây).
- \(\alpha\): hệ số tăng ưu tiên theo thời gian.

Ví dụ nếu \(\alpha = 1\) điểm/phút, message có priority ban đầu 1 sau 10 phút sẽ có priority hiệu dụng là 11; trong một cơ chế **thực sự sắp xếp lại**, nó có thể vượt message mới có priority 9.

**Cảnh báo kỹ thuật:** Không được mặc định chỉ thay comparator của \`PriorityChannel\` thành một phép tính đọc \`System.currentTimeMillis()\` là đủ để thực hiện aging. Priority queue dựa trên cấu trúc sắp xếp tại thời điểm insert/remove; khi thời gian trôi qua, queue **không tự cập nhật lại vị trí** của mọi phần tử chỉ vì khóa so sánh thay đổi. Comparator phụ thuộc đồng hồ còn dễ làm mất tính nhất quán khi các phần tử đang nằm trong cấu trúc dữ liệu.

Những cách triển khai aging rõ ràng hơn:

- Định kỳ chọn message đã quá tuổi, tính priority hiệu dụng rồi **tái đưa vào** một cấu trúc queue được sắp xếp lại có kiểm soát.
- Sắp xếp lại backlog dưới cơ chế đồng bộ hoặc dùng scheduler ngoài queue để chọn theo \`priority\` và \`waitingTime\`.
- Áp dụng **deadline-aware scheduling** nếu điều quan trọng là hạn hoàn tất thay vì điểm ưu tiên trừu tượng.

Khi chọn aging, cần quyết định có giới hạn mức tăng không, xử lý message đến đúng deadline thế nào và đảm bảo không có việc tái đưa vào queue gây mất hoặc phát trùng message. Test cần dùng đồng hồ điều khiển được hoặc logic thời gian tách riêng để có kết quả xác định.

## 8. Tách queue và dành năng lực riêng

Một phương án dễ vận hành là dành tài nguyên cho từng lớp công việc:

~~~mermaid
flowchart LR
    IN["Input"] --> R{"Router"}
    R -->|"critical"| HQ["Critical Queue"]
    R -->|"normal"| NQ["Normal Queue"]
    HQ --> HC["Critical Workers"]
    NQ --> NC["Normal Workers"]
    HC --> OUT["Kết quả"]
    NC --> OUT
~~~

Ví dụ khi có bốn worker, bạn có thể **dành trước** ba worker cho critical và một worker cho normal. Ngay cả khi critical luôn có backlog, normal vẫn có worker riêng để tiếp tục xử lý. Đổi lại, khi queue normal rỗng, worker dành riêng có thể không được sử dụng nếu không có cơ chế mượn năng lực.

So sánh nhanh:

| Thiết kế | Điều được đảm bảo khi một nhóm luôn quá tải | Chi phí |
| --- | --- | --- |
| Một \`PriorityChannel\`, một consumer | Chỉ đảm bảo chọn message ưu tiên cao nhất còn đợi | Nhóm thấp dễ bị trì hoãn |
| Hai queue + scheduler quota | Có lượt dispatch cho nhóm thấp khi scheduler còn chạy | Phải quản lý chính sách điều phối |
| Hai queue + worker riêng | Nhóm thấp có năng lực xử lý riêng | Dùng tài nguyên nhiều hơn |
| Một queue + aging có tái sắp xếp | Message chờ lâu được nâng vị thế | Phức tạp về thời gian và tính nhất quán |

Việc chọn chính sách không nên chỉ dựa vào số lượng message. Tác vụ critical tốn 10 giây trong khi tác vụ normal tốn 5 ms sẽ tạo áp lực rất khác tác vụ có chi phí ngang nhau.

## 9. Quan hệ với các pattern khác

Ưu tiên và công bằng là vấn đề xuyên suốt một hệ thống tích hợp:

### Router và Filter

Router có thể phân loại \`CRITICAL\`/\`NORMAL\` và gửi vào hai queue. Filter có thể loại request không hợp lệ trước khi chúng chiếm chỗ trong queue. Việc gắn priority sai ở Header Enricher có thể đẩy tất cả message thành critical, khiến chính sách ưu tiên không còn ý nghĩa.

### Transformer và payload

Transformer thay đổi payload không nhất thiết thay đổi priority. Nếu priority được tính từ severity của payload, hãy tính và **kiểm tra header trước khi enqueue**. Message đã nằm trong \`PriorityChannel\` không tự được sắp lại chỉ vì một object payload có thể bị thay đổi sau đó.

### Splitter, Aggregator và correlation

Một message ưu tiên cao có thể bị Splitter tách thành nhiều fragment. Nếu fragment được đưa hết vào queue priority cao, chúng có thể chiếm nhiều lượt xử lý. Khi Aggregator chờ đủ fragment, một phần tử mức thấp bị chờ lâu có thể làm **toàn bộ group** phát kết quả muộn. Test cần kiểm tra cả ordering và **độ trễ hoàn tất của correlation group**.

### Gateway

Gateway đồng bộ đang đợi reply có thể timeout dù message của nó vẫn còn trong queue. Nếu Gateway phục vụ người dùng tương tác, không nên để request thông thường bị trì hoãn vô hạn chỉ vì công việc nền nhận priority cao liên tục.

### Retry và error channel

Một message critical bị lỗi liên tục và retry quá thường xuyên có thể chiếm worker, kéo dài backlog của mọi mức ưu tiên. Giới hạn \`maxAttempts\`, backoff, circuit breaker, dead-letter/recovery và rate limit giúp tránh biến một message lỗi thành nguồn chiếm tài nguyên không dứt.

Khi một message được retry hoặc phát lại vào queue, cần kiểm tra \`requestId\`, \`correlationId\`, khóa idempotency, mức ưu tiên và thứ tự phát lại. Priority Channel không tự bảo đảm retry an toàn, exactly-once hoặc bỏ trùng.

## 10. Metrics cần theo dõi để nhận biết starvation

Không nên chỉ quan sát **độ dài queue tổng**. Một queue có 1.000 message priority cao được xử lý nhanh có thể không gây thiệt hại bằng 20 message priority thấp đã chờ hàng giờ.

| Metric | Nhóm theo | Giá trị phát hiện |
| --- | --- | --- |
| \`queue_depth\` | Priority, tenant hoặc class | Nhóm nào đang tích backlog |
| \`oldest_message_age_seconds\` | Priority/class | Message lâu nhất đã chờ bao lâu |
| \`queue_wait_seconds\` | Priority/class; p50/p95/p99 | SLA thời gian chờ có bị vượt |
| \`dispatch_count\` | Priority/class | Có nhóm nào không được lấy message |
| \`arrival_rate\`, \`service_rate\` | Priority/class | Tải đến có vượt năng lực xử lý |
| \`processing_duration_seconds\` | Handler/class | Chậm do handler hay do chờ queue |
| \`retry_count\`, \`error_count\` | Priority/class | Có nhóm lỗi chiếm tài nguyên |
| \`gateway_timeout_count\` | Route/class | Người gọi bị ảnh hưởng bởi thời gian chờ |

Để đo **thời gian chờ**, có thể gắn header nghiệp vụ như \`enqueuedAt\` tại đúng điểm enqueue và đo khi message được lấy. Đồng hồ giữa các máy có thể lệch; nếu cần SLA chính xác, phải xác định nguồn thời gian thống nhất, độ trễ truyền tải và ranh giới phép đo.

### Cảnh báo theo tác động thay vì chỉ theo kích thước

Ví dụ giả định:

~~~text
Normal SLA:
  99% message được lấy khỏi queue trong 30 giây.

Alert:
  oldest_normal_age > 30 giây trong nhiều chu kỳ liên tiếp,
  hoặc p99 queue_wait_seconds của normal vượt 30 giây.
~~~

Giá trị \`30 giây\` là **minh họa**, không phải giới hạn của Spring Integration. Với sự kiện khẩn, ngưỡng riêng có thể nghiêm ngặt hơn. Mỗi cảnh báo nên kèm queue depth, rate vào/ra, số worker, tỉ lệ retry và correlation/request ID mẫu để xác định nguyên nhân.

## 11. Kiểm thử tải và kiểm thử liveness

Unit test trong mục 4 chứng minh **cơ chế ưu tiên tuyệt đối có thể trì hoãn nhóm thấp**. Để xác nhận chính sách chống starvation đáp ứng yêu cầu thật, cần test có thời gian, concurrency và lưu lượng gần với hệ thống vận hành.

Một ma trận hữu ích:

| Kịch bản | Điều kiện | Kỳ vọng |
| --- | --- | --- |
| Không có critical | Chỉ normal vào queue | Normal sử dụng được năng lực rảnh |
| Critical ít | Critical thỉnh thoảng xuất hiện | Critical đi trước khi đang chờ, normal vẫn hoàn tất |
| Critical ổn định | Critical vào gần bằng khả năng xử lý | Normal vẫn có lượt theo quota hoặc worker reserve |
| Critical bùng nổ | Một đợt critical lớn | Normal không vượt giới hạn chờ đã quy định |
| Critical quá tải kéo dài | Critical đến nhanh hơn xử lý | Backpressure hoạt động, normal vẫn có tiến độ nếu chính sách cam kết |
| Critical retry liên tục | Một số handler luôn lỗi | Retry giới hạn, không chiếm mọi worker |
| Normal chờ gần SLA | Một message normal gần deadline | Aging/deadline policy kích hoạt nếu được cấu hình |
| Hai tenant cùng priority | Tenant A áp đảo lưu lượng | Tenant B không bị bỏ đói nếu có tenant fairness |

### Thiết kế phép đo

1. Đặt rõ **arrival rate**, phân phối priority, thời gian xử lý và tổng thời gian test.
2. Tạo ít nhất một message normal có ID có thể theo dõi từ lúc enqueue đến khi dispatch.
3. Duy trì nguồn critical đủ lâu để thử tình huống backlog liên tục.
4. Kiểm tra **tỉ lệ message normal được phục vụ**, thời gian chờ lớn nhất hoặc p99 theo SLA và số message còn tồn.
5. Chạy lại với retry, handler chậm, consumer khởi động lại hoặc nhiều replica nếu đây là rủi ro thực tế.

Không nên viết test dùng \`Thread.sleep\` rồi khẳng định message chắc chắn đã được xử lý. Dùng tín hiệu hoàn tất, latch, polling có timeout hữu hạn hoặc đồng hồ có thể điều khiển khi kiểm tra logic thời gian. Tách unit test về quyết định scheduler khỏi integration test với poller và adapter để lỗi dễ được xác định.

## 12. Các lỗi triển khai thường gặp

| Sai lầm | Hậu quả | Khắc phục |
| --- | --- | --- |
| Luôn chọn message priority lớn nhất mà không định nghĩa SLA nhóm thấp | Starvation | Xác định chính sách fairness hoặc quota |
| Tưởng \`PriorityChannel\` tự tăng priority theo tuổi | Low đợi lâu vẫn low | Aging cần tái đánh giá và sắp xếp lại thực sự |
| Dùng comparator đọc đồng hồ liên tục nhưng không tái heap | Thứ tự không phản ánh aging như mong đợi | Thiết kế aging ở scheduler hoặc cấu trúc phù hợp |
| Đo queue depth tổng thay vì theo class | Che khuất nhóm low bị tồn đọng | Theo dõi oldest age và p99 theo priority |
| Dùng hai poller độc lập rồi coi là quota 3:1 | Không có cam kết theo số lượt | Dùng scheduler điều phối hoặc worker quota rõ ràng |
| Kiểm thử thứ tự khi producer/consumer chạy song song | Test không ổn định | Đóng backlog trước khi poll, kiểm thử concurrency riêng |
| Nhầm polling order với completion order | Kết luận sai về SLA | Đo thời gian chờ và xử lý riêng |
| Retry lỗi khẩn không giới hạn | Worker bị chiếm, nhóm khác chờ | Max attempts, backoff, circuit breaker, recovery |
| Dùng priority để xử lý bảo mật hoặc phân quyền | Request không hợp lệ vẫn được xử lý | Xác thực và phân quyền độc lập với priority |
| Cấp quota toàn hệ thống nhưng mỗi replica tự đếm | Kết quả lệch kỳ vọng khi scale | Xác định rõ quota per-instance hay global |

## 13. Bài thực hành

### Bài A — Tái hiện trì hoãn

Tạo \`PriorityChannel\` và enqueue một message \`LOW\` có priority 1. Trong tám vòng tiếp theo, gửi một message \`HIGH\` priority 9, rồi thực hiện một lần poll. Xác nhận cả tám lần đều lấy HIGH; sau đó ngừng gửi HIGH và chứng minh LOW cuối cùng được lấy. Giải thích vì sao đây là biểu hiện của rủi ro starvation chứ chưa phải test chờ vô hạn.

### Bài B — Giảm thời gian chờ bằng quota

Từ \`QuotaScheduler\`, đổi \`maxUrgentStreak\` từ 3 thành 2. Gửi năm urgent và hai normal. Kiểm tra lịch dispatch khi cả hai queue liên tục có message và rút ra giới hạn số lượt urgent trước mỗi lượt normal. Thêm test cho trường hợp normal queue trống để bảo đảm scheduler không bỏ phí capacity.

### Bài C — Đánh giá aging

Đề xuất hàm tính priority hiệu dụng theo \`basePriority\`, thời gian enqueue và hệ số aging. Kiểm tra với message normal chờ 10 phút và message critical vừa đến. Nêu cơ chế tái sắp xếp hoặc scheduler dùng giá trị hiệu dụng; không chỉ thay comparator của queue rồi kỳ vọng thứ tự tự thay đổi.

### Bài D — Ưu tiên và retry

Tạo handler critical luôn lỗi tạm thời, có retry giới hạn. Trong lúc đó, gửi message normal. Đo số lần retry, thời gian chiếm worker và thời gian chờ normal. Chọn một phương án như backoff, worker reserve hoặc circuit breaker để giữ tiến độ của normal rồi viết test xác nhận.

### Bài E — Quan sát độ trễ theo lớp công việc

Gắn \`enqueuedAt\` và \`requestId\` vào message, đo lúc lấy khỏi queue và xuất metric \`queue_wait_seconds\` theo \`critical\`/\`normal\`. Tạo một kịch bản nhiều critical khiến normal chờ quá ngưỡng giả định; xác nhận cảnh báo phát đúng và có đủ thông tin để tìm queue/handler gây trễ.

## 14. Tiêu chí tự đánh giá

Bài học đạt mục tiêu khi bạn có thể trả lời rõ:

1. Vì sao một message priority thấp có thể chờ vô hạn dù consumer liên tục xử lý công việc?
2. Trạng thái nào của \`PriorityChannel\` khiến message mới priority cao vượt message cũ?
3. Vì sao test hữu hạn chỉ chứng minh **khả năng bị trì hoãn nhiều lần**?
4. Chính sách nào bảo đảm tiến độ cho nhóm thấp: quota, worker reserve, aging hay deadline?
5. Giới hạn chính sách được phát biểu bằng số lượt dispatch hay thời gian thực?
6. Làm sao xác minh chính sách khi có nhiều worker, retry, broker hoặc nhiều replica?
7. Những metric nào cho biết một nhóm đang bị thiếu cơ hội thay vì chỉ xử lý chậm?

**Kết quả cần nhớ:** Priority giúp hệ thống ưu tiên công việc quan trọng, nhưng một hệ thống vận hành tốt còn phải xác định **mức độ công bằng tối thiểu** cho các nhóm khác. Khi thiết kế quota hoặc aging có thể kiểm thử, đo thời gian chờ theo từng priority và kiểm soát retry/capacity, bạn có thể dùng Spring Integration để phục vụ công việc khẩn mà vẫn duy trì tiến độ cho phần còn lại của luồng thông điệp.
