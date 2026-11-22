# Release message sau khi hết thời gian với Spring Integration Delayer

## 1. “Release message” có nghĩa là gì?

Trong một luồng Enterprise Integration Patterns (EIP), **Delayer** nhận message, xác định thời điểm được phép xử lý tiếp và **phát (release)** message sang endpoint kế tiếp khi hết khoảng chờ. Đây là hành vi khác với việc cho thread đang xử lý ngủ bằng `Thread.sleep(...)`: với độ trễ dương, Delayer có thể giữ message và đặt lịch phát sau, còn thread ban đầu được giải phóng.

Ví dụ hệ thống bán hàng nhận sự kiện `order-2026-101-created`. Chính sách yêu cầu sau 15 phút mới gửi lời nhắc thanh toán. Trong thời gian chờ, khách có thể đã thanh toán; vì thế luồng phát message nên kiểm tra lại trạng thái đơn hàng **sau khi Delayer release**:

~~~mermaid
flowchart LR
    A[Nhận sự kiện tạo đơn] --> B[Kiểm tra dữ liệu]
    B --> C["Delayer: chờ 15 phút"]
    C --> D{Đơn còn chưa thanh toán?}
    D -->|Có| E[Gửi nhắc thanh toán]
    D -->|Không| F[Kết thúc]
    E --> G[Log và metric]
    F --> G
~~~

Trong module **SPRING_INTEGRATION_PATTERN**, hành vi này giúp ghép các endpoint như Filter, Transformer, Router, Gateway, retry, error channel và correlation thành luồng message ít phụ thuộc, dễ kiểm thử và quan sát. Delayer quyết định **khi nào chuyển message đi tiếp**; Filter, consumer và các thành phần phía sau quyết định **có nên thực hiện tác động nghiệp vụ hay không**.

**Phân biệt ba thời điểm:**

| Thời điểm | Ý nghĩa |
| --- | --- |
| `receivedAt` | Delayer nhận message |
| `dueAt` | Thời điểm message đủ điều kiện release theo chính sách delay |
| `releasedAt` | Message thực tế được gửi sang channel phía sau |

`dueAt` là **mốc sớm nhất mong muốn**. `releasedAt` có thể muộn hơn vì scheduler bận, quá trình khôi phục sau restart, kho lưu trữ chậm hoặc hệ thống chịu tải. Kể cả khi Delayer gửi thành công, thao tác như gửi email hoặc cập nhật database vẫn có thể chưa hoàn thành.

## 2. Vòng đời của một message từ khi nhận đến khi release

Delayer trong Spring Integration sử dụng `DelayHandler`, `TaskScheduler` và một `MessageGroupStore` để phối hợp việc giữ message và phát đúng hạn:

~~~mermaid
flowchart TD
    R["Nhận Message"] --> E["Tính delay: defaultDelay, expression hoặc Date"]
    E --> Q{"Delay còn dương?"}
    Q -->|Không| I["Chuyển tiếp ngay"]
    Q -->|Có| S["Đưa message vào nhóm lưu trữ"]
    S --> T["Lên lịch qua TaskScheduler"]
    T --> W["Chờ đến hạn"]
    W --> X["Tác vụ release được thực thi"]
    X --> C["Gửi tới output channel"]
    C --> U{"Downstream nhận thành công?"}
    U -->|Có| V["Tiếp tục flow"]
    U -->|Lỗi| F["Xử lý lỗi hoặc retry đã cấu hình"]
~~~

Diễn giải:

1. **Nhận:** producer đưa `Message` vào input channel dẫn đến Delayer.
2. **Tính thời gian:** Delayer lấy thời gian chờ mặc định, giá trị biểu thức từ message, hoặc mốc tuyệt đối dạng `java.util.Date`.
3. **Giữ message:** với delay dương, Delayer dùng message store để giữ message trong nhóm có khóa `messageGroupId` và giao scheduler công việc phát lại.
4. **Đến hạn:** khi scheduler thực thi tác vụ, Delayer chuyển message đến output channel.
5. **Tiếp tục:** endpoint sau Delayer, ví dụ Filter hoặc Router, nhận message theo ngữ nghĩa của channel đã dùng.
6. **Xử lý lỗi:** nếu thao tác phát xuống downstream thất bại, cần chính sách retry và error channel dành cho lỗi phát lại.

Sơ đồ là mô hình hành vi logic để học. Chi tiết transaction, thời điểm cập nhật store và retry phụ thuộc cấu hình Spring Integration và các endpoint cụ thể; **không** nên suy ra bảo đảm giao dịch hoặc exactly-once chỉ từ sơ đồ.

### Message được phát nguyên vẹn hay được tạo mới?

Mục tiêu của Delayer là **trì hoãn và chuyển message** chứ không sửa nội dung nghiệp vụ của payload. Thông thường, payload và các header nghiệp vụ như `eventId`, `correlationId` vẫn có thể được endpoint sau Delayer sử dụng. Tuy nhiên, message có thể đi qua các lớp wrapper/khôi phục hoặc được xây dựng lại trong một luồng phức tạp. Vì vậy:

- Dùng `eventId` ổn định để định danh sự kiện nghiệp vụ.
- Dùng `correlationId` để nối các bước thuộc cùng đơn hàng hoặc quy trình.
- Không dùng `MessageHeaders.ID` như khóa chống trùng vĩnh viễn: khi message mới được xây dựng, ID có thể thay đổi.
- Không xem `messageGroupId` là khóa của một đơn hàng; nó nhận diện nhóm message đang chờ **của Delayer**, đặc biệt khi dùng persistent store.

## 3. Release theo delay số và thời điểm tuyệt đối

### Khoảng chờ tương đối

Nếu Delayer nhận message tại `10:00:00.000` với `delayMs = 3_000L`, mốc dự kiến là `10:00:03.000`:

~~~text
10:00:00.000  -- Delayer nhận message
               |     Message nằm trong nhóm chờ
10:00:03.000  -- Message bắt đầu đủ điều kiện release
10:00:03.xxx  -- Scheduler có thể thực hiện tác vụ phát
               |     Filter / Router / Consumer nhận message
~~~

Nếu message khác đến lúc `10:00:00.500` với cùng delay 3 giây, mốc của message thứ hai là khoảng `10:00:03.500`. Delayer lập lịch riêng theo từng message, không nhất thiết phát tất cả message cùng group trong một lần.

### Mốc tuyệt đối

Khi nghiệp vụ cần phát tại một thời điểm cụ thể, biểu thức delay có thể trả về `java.util.Date`:

~~~java
MessageBuilder.withPayload("REMINDER-123")
        .setHeader("deliverAt",
                java.util.Date.from(java.time.Instant.now().plusSeconds(30)))
        .build();
~~~

Với `delayExpression("headers['deliverAt']")`, Delayer dựa trên thời điểm `Date` để xác định khi nào phát. Nếu mốc đã ở quá khứ, message đã đến hạn và không cần chờ. Cần phân biệt:

- `Long` như `30_000L` là **khoảng thời gian 30.000 ms**.
- `Date` là **thời điểm tuyệt đối**.

Không truyền epoch milliseconds dạng số rồi mặc định đó là một `Date`; hãy chuyển kiểu rõ ràng trước khi vào Delayer.

### Release ngay lập tức

Độ trễ bằng `0` hoặc âm khiến message được chuyển tiếp ngay, thay vì đưa vào lịch chờ dương. Đối với đường đi dùng channel đồng bộ như `DirectChannel`, downstream có thể được gọi ngay trong thread của producer. Điều này ảnh hưởng đến thời gian trả về của `send()` và nơi xuất hiện exception.

## 4. Ví dụ Java DSL: release sau khoảng thời gian của mỗi message

Ví dụ sau xây dựng một flow có đầu vào `release.in` và đầu ra `release.ready`. Một header `delayMs` cho phép từng message chọn thời gian chờ riêng, còn `defaultDelay` xử lý trường hợp không có header.

Các phụ thuộc cần thiết khi dùng Spring Boot gồm `spring-boot-starter-integration`. Ví dụ kiểm thử ở mục 5 cần thêm `spring-boot-starter-test`.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;

@Configuration
@EnableIntegration
public class ReleaseDelayConfig {

    @Bean("release.in")
    public MessageChannel releaseInput() {
        return new DirectChannel();
    }

    @Bean("release.ready")
    public PollableChannel releaseReady() {
        return new QueueChannel();
    }

    @Bean
    public IntegrationFlow releaseDelayFlow() {
        return IntegrationFlow.from("release.in")
                .delay(delayer -> delayer
                        .messageGroupId("notifications.release.delay.v1")
                        .defaultDelay(2_000L)
                        .delayExpression("headers['delayMs']"))
                .channel("release.ready")
                .get();
    }
}
~~~

Giải thích cấu hình:

| Thành phần | Vai trò |
| --- | --- |
| `DirectChannel` tại `release.in` | Nơi producer gửi message |
| `messageGroupId(...)` | Khóa nhóm message chờ của Delayer trong message store |
| `defaultDelay(2_000L)` | Nếu không có giá trị delay riêng, chờ khoảng 2 giây |
| `delayExpression("headers['delayMs']")` | Đọc thời gian chờ bằng mili giây từ header |
| `QueueChannel` tại `release.ready` | Giữ message đã được release để phía kiểm thử gọi `receive(timeout)` |

`QueueChannel` chỉ giúp quan sát message đầu ra trong ví dụ. Trong ứng dụng thực, có thể thay bằng `.handle(...)`, `.filter(...)`, `.route(...)` hoặc adapter tùy mục đích nghiệp vụ.

### Producer gửi message

~~~java
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

public void publishNotifications(MessageChannel releaseInput) {
    releaseInput.send(MessageBuilder.withPayload("ORDER-101")
            .setHeader("eventId", "event-order-101")
            .setHeader("correlationId", "order-101")
            .setHeader("delayMs", 3_000L)
            .build());

    releaseInput.send(MessageBuilder.withPayload("ORDER-102")
            .setHeader("eventId", "event-order-102")
            .setHeader("correlationId", "order-102")
            .setHeader("delayMs", 500L)
            .build());

    releaseInput.send(MessageBuilder.withPayload("ORDER-103")
            .setHeader("eventId", "event-order-103")
            .setHeader("correlationId", "order-103")
            .build()); // Dùng delay mặc định 2 giây
}
~~~

Khi sử dụng, truyền bean channel `release.in` của Spring vào tham số `releaseInput`. Nếu cả ba message đến gần như đồng thời, `ORDER-102` có thể được release trước `ORDER-103`, sau đó mới đến `ORDER-101`.

**Delayer không bảo đảm FIFO theo thứ tự producer gửi.** Thời hạn được tính theo từng message, còn lịch thực thi phụ thuộc scheduler và tải hệ thống. Khi cần thứ tự nghiêm ngặt theo `orderId` hoặc theo chuỗi sự kiện, hãy thiết kế thêm routing/partitioning hoặc một bước sắp thứ tự phù hợp.

## 5. Kiểm thử release đúng hành vi

Một bài kiểm thử nên xác minh cả hai thuộc tính:

1. **Không release quá sớm** khi delay dương.
2. **Cuối cùng release** trong một timeout đủ rộng trên môi trường kiểm thử bình thường.

Không kiểm tra “phải ra đúng tại 750,000 ms”: hệ điều hành, scheduler và CI không cung cấp cam kết chính xác như vậy.

~~~java
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.*;

@SpringJUnitConfig(ReleaseDelayConfig.class)
class ReleaseDelayTest {

    @Autowired
    @Qualifier("release.in")
    MessageChannel input;

    @Autowired
    @Qualifier("release.ready")
    PollableChannel output;

    @Test
    void releasesMessageOnlyAfterRequestedDelay() {
        long start = System.nanoTime();

        assertTrue(input.send(MessageBuilder.withPayload("ORDER-101")
                .setHeader("eventId", "event-order-101")
                .setHeader("delayMs", 750L)
                .build()));

        assertNull(output.receive(100), "Message chưa được release trước hạn");

        Message<?> released = output.receive(3_000);
        assertNotNull(released, "Message phải xuất hiện sau hạn trong timeout");
        assertEquals("ORDER-101", released.getPayload());
        assertEquals("event-order-101",
                released.getHeaders().get("eventId"));

        long elapsedMs = TimeUnit.NANOSECONDS
                .toMillis(System.nanoTime() - start);
        assertTrue(elapsedMs >= 750L,
                "Release không được xảy ra trước delay yêu cầu");
    }

    @Test
    void zeroDelayIsReleasedWithoutWaitingForScheduler() {
        assertTrue(input.send(MessageBuilder.withPayload("IMMEDIATE")
                .setHeader("delayMs", 0L)
                .build()));

        Message<?> released = output.receive(1_000);
        assertNotNull(released);
        assertEquals("IMMEDIATE", released.getPayload());
    }

    @Test
    void missingHeaderUsesDefaultDelay() {
        long start = System.nanoTime();
        assertTrue(input.send(MessageBuilder.withPayload("DEFAULT").build()));

        assertNull(output.receive(100));
        Message<?> released = output.receive(4_000);

        assertNotNull(released);
        assertEquals("DEFAULT", released.getPayload());
        long elapsedMs = TimeUnit.NANOSECONDS
                .toMillis(System.nanoTime() - start);
        assertTrue(elapsedMs >= 2_000L);
    }
}
~~~

Các test trên được thiết kế chạy độc lập với một application context cấu hình cho bài học. Nếu triển khai chạy test song song và dùng chung channel, cần cô lập context/channel hoặc bảo đảm message của test này không làm nhiễu test kia. Với kiểm thử trên CI rất bận, tăng timeout của `receive(...)` và chủ động kiểm soát nguồn message để giảm sai lệch.

Một số trường hợp mở rộng đáng kiểm thử:

- Hai message có cùng `delayMs` nhưng đến lệch nhau 500 ms.
- Message được đặt lịch theo `Date`, kể cả mốc trong quá khứ.
- Scheduler chịu tải cao: release trễ hơn deadline nhưng không phát quá sớm.
- Filter sau Delayer loại bỏ message vì trạng thái nghiệp vụ đã thay đổi.
- Consumer thất bại trong lúc xử lý message vừa release.
- Ứng dụng restart khi message chưa đến hạn, với persistent store.

## 6. Release và ngữ nghĩa của downstream channel

Release có nghĩa là Delayer **chuyển message qua output channel**. Không phải mọi loại channel đều thể hiện việc hoàn thành nghiệp vụ theo cùng cách:

| Output channel / bước sau | Điều xảy ra khi message được release |
| --- | --- |
| `DirectChannel` và `ServiceActivator` | Consumer có thể được gọi đồng bộ trong thread đang thực hiện release |
| `QueueChannel` | Message được đưa vào hàng đợi; consumer cần chủ động poll |
| `ExecutorChannel` | Handoff sang executor; việc xử lý thực tế có thể diễn ra sau đó |
| Filter | Có thể chấp nhận hoặc loại bỏ message dựa trên điều kiện hiện tại |
| Router | Chọn nhánh đích; lỗi cấu hình định tuyến có thể xuất hiện ở giai đoạn này |
| Message broker outbound adapter | Chuyển cho broker theo ngữ nghĩa xác nhận của adapter/broker |

Đừng đánh đồng các câu sau:

- “Scheduler đã chạy tác vụ release.”
- “Đầu ra của Delayer đã nhận message.”
- “Consumer đã xử lý nghiệp vụ thành công.”
- “Tác động ngoài hệ thống (email, API, database) đã được xác nhận.”

Đó là các mốc khác nhau. Một message được release thành công vào `QueueChannel` vẫn có thể tiếp tục nằm trong hàng đợi. Một message gửi qua adapter có thể được broker nhận nhưng consumer phía broker chưa xử lý. Vì vậy, metric và log phải nêu rõ **đang đo mốc nào**.

### Tình huống thời gian chờ nhưng trạng thái nghiệp vụ đã thay đổi

Nếu `ORDER-101` đã thanh toán sau 10 phút, nhưng reminder được lên lịch release sau 15 phút, Delayer vẫn có thể phát sự kiện reminder đúng hạn. Hãy kiểm tra tình trạng thanh toán ở bước sau:

~~~java
// Pseudocode của phần sau Delayer:
if (!orderRepository.isPaid(orderId)) {
    reminderService.sendReminder(orderId);
}
~~~

Với ứng dụng có nhiều tác vụ đồng thời, kiểm tra trạng thái và gửi nhắc vẫn có thể gặp race. Hãy chọn cơ chế transaction, trạng thái/phiên bản đơn hàng và idempotency phù hợp. Đừng trông chờ Delayer tự hủy message khi dữ liệu nghiệp vụ bên ngoài đã thay đổi.

## 7. Lỗi xảy ra đúng thời điểm release

Khi delay dương, phần phát lại thường được thực thi bằng tác vụ scheduler **sau** khi producer đã rời endpoint. Do đó, lỗi của downstream có thể không được phản hồi trực tiếp tới lần gọi `send()` ban đầu. Cần xử lý lỗi và quan sát tại thời điểm release.

Ví dụ hai tình huống:

1. Producer gọi `send()`, Delayer tiếp nhận và lên lịch thành công; 3 giây sau consumer gọi REST API bị lỗi 503.
2. Producer gọi `send()` với delay bằng 0; Delayer chuyển message ngay; nếu downstream đồng bộ ném exception, exception có thể xuất hiện ngay trên đường gọi của producer.

Delayer cung cấp các tùy chọn liên quan đến việc phát lại khi lỗi, gồm `maxAttempts`, `retryDelay` và `delayedMessageErrorChannel`. Đoạn cấu hình sau có thể thay cho `.delay(...)` trong flow chính:

~~~java
.delay(delayer -> delayer
        .messageGroupId("notifications.release.delay.v1")
        .defaultDelay(2_000L)
        .delayExpression("headers['delayMs']")
        .maxAttempts(3)
        .retryDelay(1_000L)
        .delayedMessageErrorChannel("release.errors"))
~~~

Khi sử dụng, phải khai báo channel `release.errors` và một flow xử lý `ErrorMessage` thực tế. Hãy xác định rõ lỗi nào cần retry, trường hợp nào cần đưa vào dead-letter/quarantine, khi nào phát cảnh báo vận hành và cách lưu metadata `eventId`, `correlationId` để xử lý tiếp.

**Lưu ý:** retry trong giai đoạn Delayer phát sang downstream khác với retry sau khi một consumer bên ngoài đã nhận và xử lý một phần nghiệp vụ. Không tự giả định `maxAttempts(3)` đồng nghĩa toàn bộ giao dịch nghiệp vụ sẽ được thử lại chính xác ba lần từ đầu đến cuối.

Với message store và transaction, điều gì xảy ra khi hết lần thử phụ thuộc cấu hình gửi, cơ chế lưu trữ và lỗi. Cần thử trực tiếp các ca consumer ném exception, ứng dụng dừng giữa thao tác, error flow xử lý thành công/thất bại và tình huống reschedule để hiểu bảo đảm của hệ thống.

## 8. Restart ứng dụng khi message chưa được release

Một Delayer dùng store trong bộ nhớ có thể mất message còn chờ khi tiến trình tắt. Với nghiệp vụ cần bảo toàn nhắc nhở, có thể cấu hình `MessageGroupStore` bền vững, ví dụ `JdbcMessageStore`, và giữ `messageGroupId` ổn định:

~~~java
// Minh họa đoạn delay trong một flow đã có JdbcMessageStore.
.delay(delayer -> delayer
        .messageGroupId("billing.reminders.delay.v1")
        .messageStore(jdbcMessageStore)
        .defaultDelay(60_000L))
~~~

Đoạn này chỉ thể hiện phần cấu hình store. Ứng dụng còn cần `DataSource`, schema JDBC message store, channel input/output, transaction và chiến lược xử lý lỗi đúng với môi trường thực tế.

Ví dụ:

| Thời điểm | Sự kiện |
| --- | --- |
| 10:00:00 | Message được nhận, delay 60 giây, lưu vào persistent store |
| 10:00:20 | Ứng dụng dừng |
| 10:01:10 | Ứng dụng chạy lại, đọc message còn chờ và khôi phục lịch |
| Sau 10:01:10 | Message đã quá hạn có thể được release ngay khi quá trình khôi phục sẵn sàng |

Việc khôi phục message được Spring Integration hỗ trợ thông qua cơ chế reschedule của Delayer, nhưng **thời điểm release sau restart không còn là mốc chính xác đã hẹn** nếu ứng dụng tắt quá lâu. Luôn đo release trễ và đặt ra chính sách nghiệp vụ cho message hết hạn: tiếp tục gửi, kiểm tra lại điều kiện, hoặc loại bỏ có ghi nhận.

Persistent store không tự tạo ra bảo đảm *exactly-once*. Một tác động bên ngoài có thể đã thành công rồi hệ thống gặp lỗi trước khi lưu trạng thái xác nhận. Khi retry hoặc khôi phục, cùng sự kiện logic có thể được xử lý lại. Hãy sử dụng `eventId` làm khóa idempotency và cân nhắc outbox/inbox nếu cần bảo đảm cao hơn.

**Không đổi `messageGroupId` tùy tiện:** tên group là khóa đọc các message chờ trong store. Đổi tên mà không chuyển dữ liệu có thể khiến phiên bản mới không nhận lại các message đang nằm ở group cũ.

## 9. Quan sát release trong môi trường thực tế

Để phân tích vì sao một message bị phát muộn, log và metric nên có các giá trị:

~~~text
eventId=reminder-101
correlationId=order-101
delayGroup=billing.reminders.delay.v1
receivedAt=2026-11-21T10:00:00Z
dueAt=2026-11-21T10:01:00Z
releasedAt=2026-11-21T10:01:00.280Z
releaseLagMs=280
status=RELEASED
~~~

Các mốc thời gian trên là ví dụ giả định, không phải log mặc định do Spring Integration tự sinh. Ứng dụng cần đo và gắn các trường phù hợp với hệ thống tracing/metrics của mình.

Hai đại lượng hữu ích:

\[
\text{actualWaitMs} = \text{releasedAt} - \text{receivedAt}
\]

\[
\text{releaseLagMs} = \max(0,\ \text{releasedAt} - \text{dueAt})
\]

Với các mốc tuyệt đối, nên lưu thời gian ở UTC (`Instant`) để tránh lỗi múi giờ. Trong hệ thống có nhiều máy, đồng bộ đồng hồ là điều kiện để so sánh timestamp. Đo khoảng thời gian trong cùng tiến trình bằng đồng hồ đơn điệu nếu có thể.

| Triệu chứng | Khả năng cần kiểm tra | Cách tiếp cận |
| --- | --- | --- |
| Message phát ngay dù cấu hình chờ | Delay bằng 0/âm, biểu thức trả về giá trị ngoài dự kiến | Log delay hiệu lực, kiểm tra header và SpEL |
| Message phát muộn nhiều | Scheduler quá tải, ứng dụng restart, message store chậm | Đo `releaseLagMs` và số message chờ |
| Message tới consumer nhưng xử lý vẫn chậm | Queue/broker hoặc consumer phía sau bị nghẽn | Đo thêm thời điểm consumer bắt đầu và hoàn thành |
| Message không còn sau restart | Store trong bộ nhớ, group ID đổi, lỗi khôi phục | Kiểm tra persistent store và lịch reschedule |
| Reminder gửi cho đơn đã thanh toán | Không kiểm tra lại trạng thái sau Delayer | Đưa Filter/kiểm tra nghiệp vụ sau release |
| Reminder được gửi hai lần | Retry, nguồn gửi lại, sự cố giữa side effect và xác nhận | Consumer idempotent theo `eventId` |
| Gateway đồng bộ timeout | Reply đến sau hạn chờ của caller | Thiết kế phản hồi bất đồng bộ hoặc điều chỉnh hợp đồng thời gian |

### Bảo vệ scheduler trước tải lớn

Nếu hàng nghìn message cùng được nhận và cùng delay 5 giây, có thể có **nhiều tác vụ release đến hạn gần như đồng thời**. Delayer không tự giới hạn số request/giây của endpoint phía sau.

Cần cân nhắc dung lượng hàng đợi, cấu hình pool scheduler, giới hạn concurrency, rate limiter, cơ chế backpressure hoặc broker nếu lưu lượng lớn. Với hệ thống phân tán, phải kiểm tra transaction/locking và tránh giả định các instance cùng nhìn vào một store sẽ tự phân chia công việc mà không có nguy cơ tranh chấp.

## 10. Phân biệt Delayer với các cơ chế gần giống

| Cơ chế | Khi nào dùng? | Khác biệt với release của Delayer |
| --- | --- | --- |
| Delayer | Chờ một khoảng thời gian hoặc mốc cụ thể trước khi chuyển message | Phát **từng message** khi đến hạn |
| `QueueChannel` | Cần buffer để consumer chủ động lấy | Không tự gắn deadline release của Delayer |
| Rate limiter | Giới hạn throughput theo thời gian | Kiểm soát **tốc độ**, không chỉ dời thời điểm |
| Retry với backoff | Sau lỗi cần thử lại theo chính sách | Phụ thuộc kết quả thất bại trước đó |
| `@Scheduled`/scheduler nghiệp vụ | Chạy công việc định kỳ theo lịch | Không gắn sẵn một deadline riêng cho mỗi message đến |
| Aggregator | Chờ đủ phần tử rồi gom kết quả | Release dựa vào điều kiện nhóm, không chỉ thời gian của một message |
| Gateway đồng bộ | Caller gửi và chờ reply | Caller có thể timeout trong khi message vẫn đang chờ Delayer |

Ví dụ `Splitter → Delayer → Aggregator` cần **hai định nghĩa release khác nhau**: Delayer phát từng mảnh khi thời gian của nó kết thúc; Aggregator trả kết quả khi nhóm liên quan đạt release strategy. Không dùng `messageGroupId` của Delayer làm mặc định cho khóa tương quan của Aggregator.

## 11. Bài tập thực hành

1. Cấu hình `defaultDelay(1_000L)`, gửi ba message cách nhau 300 ms. Ghi lại `receivedAt`, `dueAt` và `releasedAt` của từng message, giải thích vì sao không có một mốc release chung.
2. Gửi lần lượt các header `delayMs = 0L`, `300L`, `2_000L` và một message không có header. Quan sát message nào đến `QueueChannel` trước.
3. Sau Delayer, thêm Filter truy vấn trạng thái đơn hàng. Mô phỏng đơn được thanh toán khi message vẫn đang chờ; kiểm tra reminder có bị chặn đúng lúc release không.
4. Thêm một consumer cố ý ném exception khi nhận message đã đến hạn. Gắn error channel, retry phù hợp và log `eventId` để tìm message thất bại.
5. Đổi từ store trong bộ nhớ sang store bền vững, restart ứng dụng giữa thời gian chờ rồi xác minh các message còn lại được phát theo chính sách.
6. Đẩy nhiều message cùng deadline, đo `releaseLagMs` và xác định điểm nghẽn scheduler hoặc downstream.
7. Với một flow dùng Gateway đồng bộ, cho delay vượt quá timeout của caller. Thiết kế lại đường trả kết quả để caller không phải chờ hoàn thành nghiệp vụ lâu.

### Câu hỏi tự kiểm tra

- Vì sao `send()` thành công ở producer chưa chứng minh consumer đã hoàn thành?
- Điều gì khác nhau giữa `dueAt` và `releasedAt`?
- Tại sao message có delay 0 có thể phát ngay trong thread gọi?
- Khi message store bền vững khôi phục một message đã quá hạn, downstream cần kiểm tra thêm điều kiện nghiệp vụ nào?
- Vì sao cần `eventId` ổn định khi retry và restart?
- Trong trường hợp nhiều message đồng thời đến hạn, làm sao giảm nguy cơ gây quá tải downstream?

## Tài liệu tham khảo

- [Spring Integration Reference — Delayer](https://docs.spring.io/spring-integration/reference/delayer.html): vòng đời delay, scheduler, message group, cách phát lại và lỗi khi release.
- [Spring Integration Reference — Java DSL](https://docs.spring.io/spring-integration/reference/dsl.html): khai báo `IntegrationFlow` và các endpoint.
- [Spring Integration Reference — Message Store](https://docs.spring.io/spring-integration/reference/message-store.html): lưu trữ trong bộ nhớ và persistent store.
- [Spring Integration Reference — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html): lỗi trong luồng message bất đồng bộ, error channel và các biện pháp xử lý.
