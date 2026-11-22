# Kiểm thử message đến lệch thứ tự hoặc thiếu trong Spring Integration Runtime

## Mục tiêu bài học

Trong **SPRING_INTEGRATION_RUNTIME**, message flow thường nhận dữ liệu từ nhiều consumer, poller, queue, HTTP client hoặc worker thread. Các message thuộc cùng một nghiệp vụ có thể **đến không theo thứ tự phát**, bị **trễ**, **thiếu**, **giao lại** hoặc cùng lúc được xử lý bởi nhiều instance. Nếu chỉ kiểm thử happy path với ba message đến đúng thứ tự, một lỗi correlation hoặc release rất dễ lọt sang production.

Bài thuộc chương **Correlation runtime**, tập trung vào việc **kiểm thử message đến lệch thứ tự hoặc thiếu**. Các ví dụ sử dụng aggregator để chờ ba thông tin của một đơn hàng, đồng thời liên hệ message store, endpoint, channel, executor, transaction, retry, error flow và lifecycle.

Sau bài này, bạn có thể:

- Thiết kế bộ test cho message **out-of-order, missing, late, duplicated** và **concurrent**.
- Phân biệt **correlation key**, **sequenceNumber/sequenceSize**, **eventId**, **requestId** và **Spring MessageHeaders.ID**.
- Kiểm chứng **ReleaseStrategy** chỉ phát output khi dữ liệu nghiệp vụ thực sự đủ.
- Kiểm tra **group timeout**, partial result, discard channel và state trong **MessageGroupStore**.
- Viết integration test với Spring Integration channel, gửi message theo hoán vị và xác nhận **không có output quá sớm**.
- Đọc nguyên nhân các lỗi thường gặp khi chạy đa luồng, restart, retry hoặc nhiều application instance.

> **Tiêu chí đúng:** Với mỗi nhóm nghiệp vụ, hệ thống không phát kết quả đầy đủ khi còn thiếu điều kiện; khi nhận đủ message hợp lệ, kết quả không phụ thuộc thứ tự đến; message trùng và message đến sau khi hoàn tất không được tạo side effect nghiệp vụ lặp.

## 1. Vì sao message có thể đến lệch thứ tự hoặc thiếu?

Giả sử quy trình xác nhận đơn O-42 đòi hỏi ba bước độc lập:

| Bước | Dữ liệu nhận | Nguồn |
| --- | --- | --- |
| PAYMENT | Thanh toán đã được chấp nhận | Payment service |
| INVENTORY | Hàng đã được giữ | Inventory service |
| ADDRESS | Địa chỉ giao hàng đã được xác thực | Address service |

Một luồng lý tưởng có thể phát theo thứ tự PAYMENT → INVENTORY → ADDRESS. Runtime thực tế có thể quan sát ADDRESS → PAYMENT → INVENTORY do worker, network và latency khác nhau.

~~~mermaid
sequenceDiagram
    participant P as Payment service
    participant I as Inventory service
    participant A as Address service
    participant G as Aggregator
    participant O as Order consumer
    Note over P,A: Các tác vụ chạy độc lập
    A->>G: ADDRESS, group=O-42
    P->>G: PAYMENT, group=O-42
    Note right of G: Chưa đủ 3 bước: chờ
    I->>G: INVENTORY, group=O-42
    G->>O: OrderReady
~~~

Các nguồn gây mất thứ tự/thiếu message:

- **ExecutorChannel / TaskExecutor:** các worker có thời gian hoàn tất khác nhau.
- **QueueChannel và polling consumer:** nhiều poller hoặc nhiều consumer xử lý song song; lần lấy và lần hoàn thành không nhất thiết giữ cùng thứ tự.
- **Broker/adapter:** partition, rebalance, redelivery và retry thay đổi thời điểm message được nhìn thấy. Bảo đảm ordering, nếu có, thường chỉ theo một phạm vi cụ thể như partition/key.
- **Transformer/filter/router:** một nhánh lỗi, filter hoặc đổi correlation header có thể khiến aggregator không nhìn thấy một phần.
- **Service ngoài:** timeout có thể xảy ra dù side effect đã thành công; sự kiện kết quả có thể được phát lại với message ID mới.
- **Restart/scale-out:** message được giữ trong persistent store, nhưng deadline và các tác vụ scheduler có thể cần phục hồi hoặc đối soát.

Không nên kỳ vọng một **DirectChannel** tự bảo đảm thứ tự toàn cục: nó chạy đồng bộ trong từng lời gọi send, nhưng **hai thread khác nhau vẫn có thể send đồng thời** tới cùng handler.

## 2. Xác định chính xác “đúng” trước khi viết test

Không có bộ test correlation hữu ích nếu nghiệp vụ chưa định nghĩa khi nào được coi là đủ. Với đơn hàng O-42, giả sử các điều kiện là:

1. Ba **loại bước** PAYMENT, INVENTORY, ADDRESS đều có mặt.
2. Tất cả bước thuộc cùng **orderId + runId**.
3. Mỗi sự kiện có **eventId** ổn định để nhận diện redelivery.
4. Không có kết quả thất bại hoặc phiên bản mâu thuẫn; nếu có, cần một nhánh failure riêng.
5. Output **OrderReady** chỉ được phát **một lần về mặt nghiệp vụ** cho cùng orderId + runId, kể cả sau restart hoặc redelivery.

Một nhóm test cơ bản có thể mô tả bằng bảng:

| Tình huống | Input | Kỳ vọng |
| --- | --- | --- |
| Đúng thứ tự | PAYMENT → INVENTORY → ADDRESS | Một kết quả sau phần thứ ba |
| Lệch thứ tự | ADDRESS → PAYMENT → INVENTORY | Một kết quả tương đương |
| Thiếu phần | PAYMENT + ADDRESS, không có INVENTORY | Không có OrderReady đầy đủ |
| Duplicated | PAYMENT(E1) hai lần + ADDRESS | Không được hiểu là đủ ba loại bước |
| Đến muộn | Sau khi nhóm complete, INVENTORY được giao lại | Discard/quarantine hoặc xử lý theo chính sách late message |
| Nhiều nhóm xen kẽ | O-42 và O-43 có đủ ba phần riêng | Hai kết quả, không lẫn nhóm |
| Gửi đồng thời | Ba producer cùng send cho O-42 | Một kết quả, không lost update |
| Timeout | Group thiếu INVENTORY đến quá SLA | Có trạng thái timeout, không tạo OrderReady đầy đủ |
| Restart | Lưu 2/3 phần rồi khởi động lại | Không mất phần đã lưu nếu store bền vững |

**Điểm quan trọng:** “Không có output” chỉ chứng minh **trạng thái tạm thời**. Test missing message còn phải kiểm chứng chuyện gì xảy ra khi hết thời gian chờ: quarantine, phát kết quả partial có đánh dấu, giữ nhóm để phục hồi hay xóa state.

## 3. Identity của message: phân biệt các khóa

Một message mẫu:

~~~text
payload:
  orderId=O-42, runId=R-7
  step=PAYMENT, eventId=payment-event-19, accepted=true

headers:
  groupKey=order-ready:v1:O-42:R-7
  correlationId=checkout-O-42
  requestId=checkout-request-91
  id=<Spring Message UUID>
~~~

| Trường | Vai trò | Dùng trong test |
| --- | --- | --- |
| **groupKey** | Khóa duy nhất để aggregator phân nhóm | Kiểm tra message cùng run vào cùng nhóm, khác run không lẫn |
| **correlationId** | Liên kết message trong hành trình nghiệp vụ; có thể được EIP điều chỉnh | Kiểm tra header được propagate đúng qua transform/gateway |
| **orderId + runId** | Định danh lần tổng hợp nghiệp vụ | Kiểm tra không gom hai lần xác nhận khác nhau của cùng đơn |
| **eventId** | Định danh sự kiện nguồn qua retry/redelivery | Kiểm tra deduplication trước hoặc trong quy trình tổng hợp |
| **MessageHeaders.ID** | ID kỹ thuật của một Spring Message | Không dùng làm idempotency key xuyên replay hoặc rebuild message |
| **sequenceNumber/sequenceSize** | Thông tin thứ tự và tổng số phần do splitter/producer thiết lập | Dùng khi chọn release theo sequence; không đồng nghĩa sự kiện nghiệp vụ duy nhất |

**Không nhầm hai kiểu correlation:** Header **correlationId** là quy ước thường dùng của Spring Integration và mặc định trong nhiều correlating endpoint, còn **groupKey** ở bài này là header **tự định nghĩa**. Khi cấu hình aggregator, phải nói rõ nó dùng **headers['groupKey']**. Nếu không, test sẽ không đo đúng quy tắc phân nhóm mong muốn.

Đối với splitter chuẩn, sequence headers có thể là đủ để gom các mảnh của **một message gốc**. Nhưng khi gom **ba kết quả nghiệp vụ từ ba dịch vụ**, dùng số lượng message hoặc sequence size đơn thuần thường không đủ để chống duplicate.

## 4. ReleaseStrategy cần bất biến trước thứ tự đến

ReleaseStrategy trả lời: **nhóm đã đủ điều kiện phát chưa?** Nó nên là phép kiểm tra không có side effect, để các lần đánh giá lại do retry, timeout hoặc concurrency không tạo thêm thanh toán, HTTP call hay event.

Ví dụ model đơn giản:

~~~java
package example;

public enum Step {
    PAYMENT, INVENTORY, ADDRESS
}

// Đặt record trong file OrderPart.java, cùng package example.
public record OrderPart(
        String orderId,
        String runId,
        String eventId,
        Step step,
        boolean accepted) {
}
~~~

Một strategy chỉ phát khi **cả ba loại bước** đều có trạng thái hợp lệ:

~~~java
package example;

import java.util.EnumSet;
import org.springframework.integration.aggregator.ReleaseStrategy;
import org.springframework.integration.store.MessageGroup;
import org.springframework.messaging.Message;

public final class RequiredStepsReleaseStrategy implements ReleaseStrategy {

    private static final EnumSet<Step> REQUIRED =
            EnumSet.allOf(Step.class);

    @Override
    public boolean canRelease(MessageGroup group) {
        EnumSet<Step> accepted = EnumSet.noneOf(Step.class);

        for (Message<?> message : group.getMessages()) {
            if (!(message.getPayload() instanceof OrderPart part)) {
                return false;
            }
            if (!part.accepted()) {
                return false;
            }
            accepted.add(part.step());
        }

        return accepted.containsAll(REQUIRED);
    }
}
~~~

Vì strategy dùng tập **Step**, thứ tự **ADDRESS → PAYMENT → INVENTORY** và **INVENTORY → ADDRESS → PAYMENT** đều cho kết quả như nhau. Một duplicate PAYMENT không thể thay thế INVENTORY.

Tuy nhiên đây chỉ là **release guard**, **chưa phải bộ chống duplicate hoàn chỉnh**:

- Hai sự kiện PAYMENT có eventId trùng vẫn nằm trong group nếu ingress không lọc; khi nhóm được release, processor có thể nhận nhiều phần PAYMENT.
- Nếu hai PAYMENT có trạng thái mâu thuẫn, ví dụ một accepted=true và một accepted=false, chiến lược trên trả false, nhưng cần chính sách rõ để gửi conflict sang error flow/quarantine.
- Nếu một message vô tình mang **groupKey** khác với **orderId/runId trong payload**, strategy không tự phát hiện sai tương quan. Nên validate invariant này trước khi lưu nhóm.
- Với persistent store, **group.getMessages()** có thể phải nạp nhiều payload; nhóm rất lớn cần release logic dựa trên metadata/condition hoặc cơ chế tính tiến độ thích hợp.

Vì vậy, test phải kiểm tra cả **release đúng lúc** lẫn **payload sau release đúng nội dung**. Nếu output là một collection có hai PAYMENT, test không được xem là hoàn toàn đạt yêu cầu chỉ vì nó xuất hiện đúng thời điểm.

## 5. Dựng flow kiểm thử với channel và MessageGroupStore

Để kiểm thử một aggregator thực, nên gửi message qua channel/endpoint của Spring Integration thay vì chỉ gọi **canRelease()** trực tiếp. Đoạn XML sau là một cấu hình kiểm thử minh họa; bean/channel được khai báo trong cùng application context. Đặt trong **order-aggregation-test.xml** của test resources khi áp dụng vào một dự án.

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:int="http://www.springframework.org/schema/integration"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd
           http://www.springframework.org/schema/integration
           https://www.springframework.org/schema/integration/spring-integration.xsd">

    <int:channel id="orderParts"/>
    <int:channel id="orderReady">
        <int:queue/>
    </int:channel>
    <int:channel id="discardedParts">
        <int:queue/>
    </int:channel>

    <bean id="groupStore"
          class="org.springframework.integration.store.SimpleMessageStore"/>
    <bean id="requiredSteps"
          class="example.RequiredStepsReleaseStrategy"/>

    <int:aggregator
            id="orderAggregator"
            input-channel="orderParts"
            output-channel="orderReady"
            message-store="groupStore"
            correlation-strategy-expression="headers['groupKey']"
            release-strategy="requiredSteps"
            discard-channel="discardedParts"
            expire-groups-upon-completion="false"/>
</beans>
~~~

Thiết kế test này có các đặc điểm chủ ý:

- **orderParts** là channel vào đồng bộ; việc send từ một thread và chờ lời gọi hoàn tất giúp test dễ xác định khi aggregator đã xử lý phần đó.
- **orderReady** và **discardedParts** là **QueueChannel**, nên test có thể gọi **receive(timeout)** để quan sát có/không có output.
- **SimpleMessageStore** chỉ giữ state trong RAM và trong một context; đủ để kiểm tra logic, **chưa chứng minh restart hoặc multi-instance**.
- **RequiredStepsReleaseStrategy** kiểm tra đủ ba loại bước; aggregator cần một **MessageGroupProcessor/output processor** nghiệp vụ để tạo đối tượng OrderReady thực trong production. Với processor mặc định, output có thể là collection các payload; không nên suy luận nó đã là DTO nghiệp vụ.
- **expire-groups-upon-completion=false** giữ metadata đã hoàn tất để message đến muộn có thể được nhận diện thay vì tạo một nhóm mới ngay.
- Ví dụ cố ý **chưa cấu hình timeout**: trước tiên kiểm thử hành vi nhận đủ/thiếu khi chưa có expiry. Sẽ có test riêng về timeout ở phần sau.

## 6. Integration test: ba message đến sai thứ tự

Ví dụ JUnit 5 dưới đây dùng cùng cấu hình XML ở phần trước. Tên package là **example**, các kiểu **Step** và **OrderPart** được định nghĩa ở phần 4. Mỗi test sử dụng một **groupKey riêng** để các nhóm không ảnh hưởng lẫn nhau.

~~~java
package example;

import static org.junit.jupiter.api.Assertions.*;
import static example.Step.*;

import java.util.Collection;
import java.util.Set;
import java.util.UUID;
import java.util.stream.Collectors;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(locations = "classpath:order-aggregation-test.xml")
class OutOfOrderAggregationTest {

    @Autowired
    @Qualifier("orderParts")
    MessageChannel input;

    @Autowired
    @Qualifier("orderReady")
    PollableChannel output;

    private Message<OrderPart> part(
            String groupKey, String eventId, Step step) {
        return MessageBuilder.withPayload(
                    new OrderPart("O-42", "run-1", eventId, step, true))
                .setHeader("groupKey", groupKey)
                .setHeader("correlationId", "checkout-O-42")
                .setHeader("requestId", "request-O-42")
                .build();
    }

    @Test
    void releasesOnceWhenMessagesArriveOutOfOrder() {
        String group = "order-ready:v1:" + UUID.randomUUID();

        assertTrue(input.send(part(group, "address-1", ADDRESS)));
        assertNull(output.receive(0), "Chưa đủ 3 loại bước");

        assertTrue(input.send(part(group, "payment-1", PAYMENT)));
        assertNull(output.receive(0), "Vẫn thiếu INVENTORY");

        assertTrue(input.send(part(group, "inventory-1", INVENTORY)));
        Message<?> released = output.receive(1000);
        assertNotNull(released, "Đủ 3 bước phải phát kết quả");
        assertNull(output.receive(0), "Không phát thêm lần thứ hai");

        // Với output processor mặc định: kiểm tra các payload được gom.
        assertInstanceOf(Collection.class, released.getPayload());
        Collection<?> payloads =
                (Collection<?>) released.getPayload();
        Set<Step> actualSteps = payloads.stream()
                .map(value -> ((OrderPart) value).step())
                .collect(Collectors.toSet());
        assertEquals(Set.of(PAYMENT, INVENTORY, ADDRESS), actualSteps);
        assertEquals(3, payloads.size());
    }
}
~~~

**Cách đọc kết quả:**

1. Mọi lời gọi send trước lần gửi cuối đã kết thúc, nhưng QueueChannel **vẫn rỗng**. Điều này chứng minh aggregator chưa release quá sớm trong đường xử lý đồng bộ đang test.
2. Sau khi nhận INVENTORY, xuất hiện đúng **một** output chứa cả ba bước, bất kể thứ tự chúng đến.
3. Assertion **payloads.size() == 3** bảo đảm output không vô tình có phần trùng trong happy path.
4. Vì context có thể được chia sẻ giữa các test, nên dùng group key duy nhất, tiêu thụ hết message ở các output channel, hoặc cô lập application context khi chạy test song song.

### Kiểm tra tất cả hoán vị

Với ba loại bước, có **6 hoán vị**. Thay vì chỉ test ADDRESS → PAYMENT → INVENTORY, có thể dùng parameterized test với các chuỗi:

~~~text
PAYMENT, INVENTORY, ADDRESS
PAYMENT, ADDRESS, INVENTORY
INVENTORY, PAYMENT, ADDRESS
INVENTORY, ADDRESS, PAYMENT
ADDRESS, PAYMENT, INVENTORY
ADDRESS, INVENTORY, PAYMENT
~~~

Với mỗi hoán vị, dùng **groupKey mới**, gửi từng phần, kiểm tra **không có output sau phần 1 và 2**, sau phần 3 có đúng một kết quả. Sau đó kiểm tra **tập nội dung**, **eventId** và business key, không so sánh vị trí cố định trong collection nếu nghiệp vụ không yêu cầu thứ tự.

Một collection giữ thứ tự chèn vào store **không đồng nghĩa** thứ tự nghiệp vụ được bảo đảm. Nếu downstream cần output theo thứ tự cố định, **MessageGroupProcessor** cần sắp xếp theo Step/sequence hoặc tạo DTO có các trường định danh rõ ràng.

## 7. Kiểm thử missing message: xác nhận không release sớm

Trường hợp chỉ có PAYMENT và ADDRESS, thiếu INVENTORY. Một test đơn giản:

~~~java
@Test
void doesNotReleaseWhenInventoryIsMissing() {
    String group = "order-ready:v1:" + UUID.randomUUID();

    assertTrue(input.send(part(group, "payment-2", PAYMENT)));
    assertTrue(input.send(part(group, "address-2", ADDRESS)));

    assertNull(output.receive(0));

    // Nếu test cần chứng minh đã lưu 2 phần, có thể inject
    // MessageGroupStore và kiểm tra group theo khóa.
}
~~~

Kiểm tra ngữ cảnh group khi cần:

~~~java
@Autowired
@Qualifier("groupStore")
org.springframework.integration.store.MessageGroupStore groupStore;

// Trong test sau hai lần input.send(...):
var groupState = groupStore.getMessageGroup(group);
assertEquals(2, groupState.size());
assertFalse(groupState.isComplete());
~~~

Không dùng một **Thread.sleep(30_000)** để “chứng minh thiếu message”. Khi chưa cấu hình timeout, chỉ có thể khẳng định **chưa release tại thời điểm quan sát**. Để kiểm tra deadline, cần một test riêng có group timeout và tín hiệu quan sát được.

### Phân biệt thiếu message với thiếu điều kiện release

Các nguyên nhân thường bị gộp:

| Triệu chứng | Nguyên nhân thực tế có thể có | Kiểm tra |
| --- | --- | --- |
| Group O-42 chỉ có hai phần | Service thứ ba chưa gửi hoặc gửi thất bại | Theo dõi outbound của nguồn thứ ba, error flow |
| Có đủ ba message nhưng vẫn chờ | Một payload **accepted=false** hoặc sai loại Step | Xem từng payload, kết quả ReleaseStrategy |
| Message thứ ba đi đâu không rõ | Header groupKey bị xóa hoặc đổi sau transformer | Trace channel trước/sau transform, kiểm tra header |
| Group chờ dù đã phát message | Message đi vào **group khác** do runId/key sai | So sánh danh sách group trong store |
| Group bị “mất” sau restart | SimpleMessageStore trong RAM | Dùng persistent store và test restart |
| Group timeout nhưng không có kết quả | Partial release bị tắt hoặc discard/expiry chưa được quan sát | Kiểm tra timeout, discard channel, message store |

Một luồng test tốt cần phân biệt lỗi **data absent**, **data invalid**, **correlation mismatch** và **scheduler/expiry**. Chúng có cách sửa khác nhau.

## 8. Kiểm thử duplicate và redelivery

Giả sử broker giao lại PAYMENT do consumer ack bị mất:

~~~text
1. PAYMENT, eventId=pay-19, Spring messageId=M1
2. PAYMENT, eventId=pay-19, Spring messageId=M2  ← redelivery
3. ADDRESS, eventId=addr-5
4. INVENTORY, eventId=stock-8
~~~

Nếu release strategy chỉ kiểm tra **size() >= 3**, nó có thể release ngay ở bước 3 dù thiếu INVENTORY. **RequiredStepsReleaseStrategy** ở phần 4 không gặp lỗi phát sớm này, nhưng khi bước 4 tới, group vẫn có thể chứa **hai bản PAYMENT**.

Nên tách hai assertion:

- **Release correctness:** không phát OrderReady khi thiếu một Step.
- **Deduplication correctness:** output không chứa hai sự kiện nghiệp vụ có cùng eventId và không gọi side effect hai lần.

Để đạt cả hai, thường cần **idempotent receiver/filter** trước aggregator, unique constraint theo eventId hoặc cơ chế dedup bền vững tương đương:

~~~text
Inbound message
    ↓ validate orderId/runId/eventId
    ↓ kiểm tra / ghi nhận eventId idempotently
    ├─ đã xử lý → discard với lý do DUPLICATE
    └─ mới        → Aggregator
~~~

Lưu ý **đồng bộ hóa**: hai consumer đồng thời cùng eventId không được cùng vượt qua “check then put” nếu store không hỗ trợ thao tác atomic. Nếu duplicate đến trong nhiều JVM, bộ nhớ in-process không đủ; ưu tiên kho lưu trữ có unique constraint hoặc atomic claim.

### Bộ test duplicate cần có

1. Gửi hai bản message cùng **eventId** nhưng **khác MessageHeaders.ID**; kiểm tra không tính là hai bước khác nhau.
2. Gửi hai bản cùng **Step** nhưng eventId khác và payload mâu thuẫn; xác minh conflict policy, không tự chọn ngẫu nhiên.
3. Gửi lại cả ba phần **sau khi đã release**; kiểm tra group complete/retained state và downstream idempotency.
4. Gửi duplicate đồng thời từ hai producer; kiểm tra một lần claim trong store.
5. Restart sau khi nhận một phần rồi redeliver; kiểm tra key dedup còn hiệu lực qua restart.

Một bài test chỉ trông vào **Message ID** trùng khi mock cùng một Message object chưa đủ. Thực tế broker adapter thường tạo Spring Message mới cho lần nhận lại.

## 9. Timeout, partial release và message đến muộn

Thiếu message mãi mãi sẽ gây tích tụ incomplete group nếu không có vòng đời rõ ràng. Spring Integration hỗ trợ các cơ chế như **groupTimeout**, **sendPartialResultOnExpiry** và dọn state qua message store/reaper tùy cấu hình.

~~~mermaid
stateDiagram-v2
    [*] --> Waiting: Nhận phần đầu tiên
    Waiting --> Waiting: Chưa đủ điều kiện
    Waiting --> Released: Đủ ba loại bước
    Waiting --> TimedOut: Hết SLA
    TimedOut --> Quarantined: Không phát partial
    TimedOut --> Partial: Cho phép partial theo hợp đồng
    Released --> Completed: Đánh dấu group complete
    Completed --> Retained: Giữ metadata
    Retained --> Discard: Nhận message đến muộn
~~~

**Thiết kế timeout phải là quyết định nghiệp vụ:**

- Nếu một đơn chỉ được xác nhận khi đủ cả ba phần, cấu hình **sendPartialResultOnExpiry=false**; timeout đi vào nhánh thất bại/quarantine theo quy tắc.
- Nếu nghiệp vụ chấp nhận partial (ví dụ dashboard hiển thị số liệu tạm), output **phải gắn rõ trạng thái partial** để downstream không hiểu nhầm là complete.
- Nếu group được **xóa ngay khi hoàn tất** hoặc timeout, một late message có thể mở **group mới** cùng khóa. Giữ metadata complete có thể giúp nhận diện late arrivals, nhưng cần kế hoạch cleanup.
- Nếu timeout và deadline tính theo message cuối cùng, việc redelivery một phần có thể kéo dài “tuổi chờ” ngoài dự kiến; cần quyết định tính từ **lần đầu nhận** hay **lần cập nhật gần nhất**.

### Cách kiểm thử timeout mà không tạo test thất thường

Nên tạo **hai cấu hình test riêng**:

1. **No-timeout fixture** cho các test permutation, missing trước expiry và duplicate, tránh scheduler can thiệp giữa assertions.
2. **Timeout fixture** với timeout ngắn nhưng có giới hạn thời gian kiểm thử đủ rộng, channel nhận event timeout/discard rõ ràng, và chính sách partial được khai báo tường minh.

Với fixture timeout, test gửi 2/3 phần rồi chờ **tín hiệu kết thúc** qua pollable channel/spy hoặc trạng thái group, dùng primitive đồng bộ/await cho điều kiện thay vì sleep cứng. Assertion cần kiểm tra **không có OrderReady đầy đủ**, có event timeout/quarantine nếu đó là hợp đồng, và group được retain/expire đúng chính sách. Khi test chạy trong CI bận, timeout kết quả cần đủ rộng so với SLA test.

**Đừng nhầm receive timeout với group timeout:**

~~~java
assertNull(orderReady.receive(100));
~~~

Lệnh này chỉ nói **trong 100 ms không có message ở QueueChannel output**. Nó **không cấu hình** thời hạn group và cũng **không chứng minh** event timeout của aggregator đã chạy. Để xác minh group timeout, phải quan sát **callback/status sau expiry** hoặc inspect store theo hợp đồng.

### Test late arrival sau khi group complete

Với **expire-groups-upon-completion=false**, có thể thiết kế test:

~~~java
String groupKey = "order-ready:v1:" + UUID.randomUUID();
input.send(part(groupKey, "pay-1", PAYMENT));
input.send(part(groupKey, "stock-1", INVENTORY));
input.send(part(groupKey, "address-1", ADDRESS));
assertNotNull(output.receive(1000));

// Message đến sau: cùng groupKey, có thể là redelivery.
input.send(part(groupKey, "pay-redelivered", PAYMENT));
assertNull(output.receive(0), "Không phát OrderReady lần nữa");

// Kiểm tra discardedParts hoặc trạng thái store theo chính sách cấu hình.
~~~

Chỉ kiểm tra output rỗng là **chưa đủ** để chứng minh late message đã được xử lý đúng. Cần quan sát **discard/quarantine** hoặc metadata group, và kiểm tra không có memory leak do giữ metadata quá lâu.

## 10. Kiểm thử message đến đồng thời và nhiều group xen kẽ

Kiểm thử tuần tự xác minh correlation logic; nó chưa chứng minh thread safety. Khi nhiều producer gọi cùng một DirectChannel hoặc ExecutorChannel, group có thể bị cập nhật song song.

Ví dụ cho ba phần vào đồng thời:

~~~java
var pool = java.util.concurrent.Executors.newFixedThreadPool(3);
var start = new java.util.concurrent.CountDownLatch(1);
String groupKey = "order-ready:v1:" + java.util.UUID.randomUUID();

try {
    var futures = java.util.List.of(
        pool.submit(() -> {
            start.await();
            return input.send(part(groupKey, "p", PAYMENT));
        }),
        pool.submit(() -> {
            start.await();
            return input.send(part(groupKey, "i", INVENTORY));
        }),
        pool.submit(() -> {
            start.await();
            return input.send(part(groupKey, "a", ADDRESS));
        })
    );

    start.countDown();
    for (var future : futures) {
        assertTrue(future.get(5, java.util.concurrent.TimeUnit.SECONDS));
    }

    assertNotNull(output.receive(1000));
    assertNull(output.receive(0), "Không có kết quả thứ hai");
} finally {
    pool.shutdownNow();
}
~~~

Đây là **mẫu test thread trong cùng JVM**. Nó kiểm tra ba tác vụ cùng bắt đầu và chờ tất cả send hoàn tất, tránh so thời gian bằng sleep. Cần chạy lặp lại với nhiều group/key, kết hợp trường hợp một thread gửi duplicate và một thread gây lỗi.

**Đừng dùng một groupKey cho tất cả test chạy song song**: các test có thể giẫm vào nhau. Với test có chung context, dùng group key riêng và cơ chế drain hoặc cô lập output queues.

### Xen kẽ nhiều group

Gửi O-42 PAYMENT, O-43 ADDRESS, O-42 INVENTORY, O-43 PAYMENT, O-42 ADDRESS, O-43 INVENTORY. Kỳ vọng:

- Có **hai** output, một cho O-42 và một cho O-43.
- Mỗi output chỉ chứa đúng **ba message của cùng runId**.
- Không có thứ tự bắt buộc **giữa hai output** nếu các group được xử lý bởi executor khác nhau.
- Test kiểm tra content/correlation theo **groupKey**, không giả định output[0] luôn là O-42.

### Scale nhiều JVM

Để kiểm thử multi-instance thực sự, cần **MessageGroupStore chung**, **LockRegistry hoặc cơ chế phối hợp tương đương** và ít nhất hai application instance. Test chỉ dùng SimpleMessageStore và ExecutorService **không chứng minh** an toàn qua nhiều process.

Kịch bản quan trọng: hai instance cùng gửi phần cuối vào group gần đủ điều kiện, hoặc một instance chết giữa cập nhật group và publish. Cần xác minh:

- Không mất message trong store và không release hai lần ngoài hợp đồng.
- Lock/transaction hoạt động giữa instance, không chỉ trong bộ nhớ một JVM.
- Consumer downstream idempotent vì output vẫn có thể redeliver sau lỗi mạng hoặc crash.

## 11. Retry, transaction và error flow trong bộ test

Một phép test correlation chỉ chứng minh trạng thái đúng trong **đường xử lý thành công** nếu không cố tình tạo lỗi. Tại runtime, retry và transaction có thể thay đổi điều gì được lưu vào store.

~~~mermaid
flowchart TD
    IN["Inbound message"] --> T["Transformer / validator"]
    T --> C["CorrelationStrategy"]
    C --> S[("MessageGroupStore")]
    S --> R{"ReleaseStrategy"}
    R -- "Chưa đủ" --> W["Waiting / timeout"]
    R -- "Đủ" --> P["MessageGroupProcessor"]
    P --> OUT["Output channel / consumer"]
    T -. "exception" .-> ER["Error flow"]
    S -. "exception" .-> ER
    P -. "exception" .-> ER
    OUT -. "exception" .-> ER
~~~

### Các ranh giới cần xác định

| Thành phần | Điều cần kiểm chứng |
| --- | --- |
| **DirectChannel** | Exception từ handler đồng bộ có truyền về sender? Transaction có cùng thread không? |
| **ExecutorChannel** | Error phát sinh ở worker thread đi đâu? Transaction của sender không mặc định bao trùm downstream |
| **Poller** | Nếu poll/handler thất bại, nguồn có lấy lại message không? Chính sách ack, transaction và retry được áp dụng ở đâu? |
| **MessageGroupStore** | Add/release/mark-complete có rollback cùng transaction không? Store có bền vững sau crash không? |
| **RetryAdvice/broker redelivery** | Cùng eventId có được xử lý lại như nghiệp vụ mới không? Có retry lồng nhiều tầng không? |
| **ErrorMessage** | Có lấy được failed/original message và groupKey/requestId từ lỗi không? |
| **MessageGroupProcessor** | Nếu tạo output lỗi, group ở trạng thái nào và lần retry tiếp theo sẽ làm gì? |

**Các test không nên bỏ qua:**

1. Parser nhận message lỗi trước aggregator: không được tạo group với khóa null/UNKNOWN.
2. Handler/processor ném exception sau khi group đủ điều kiện: lỗi được truyền hoặc đưa đúng error flow; không bị nuốt.
3. Transaction rollback khi store đã nhận phần cuối: sau rollback trạng thái group và output phải khớp cam kết của resource/transaction manager.
4. Broker redeliver sau rollback: cùng eventId không gây thêm side effect.
5. Lỗi xảy ra **sau khi output đã gửi**: downstream cần idempotency vì rollback DB không tự thu hồi HTTP/broker event.

Đừng ngầm giả định **message store + aggregator = exactly once**. Tính nhất quán giữa store và output phụ thuộc transaction manager, adapter và topology; side effect bên ngoài thường cần **outbox/inbox, unique constraint** hoặc cơ chế đối soát.

## 12. Restart và khôi phục group còn thiếu

**SimpleMessageStore** hữu ích cho unit/integration test nhỏ, nhưng state biến mất khi JVM dừng. Để xác minh flow sống qua restart, dùng **JdbcMessageStore, RedisMessageStore hoặc MongoDbMessageStore** phù hợp cấu hình production và test với storage thực.

Kịch bản:

~~~text
T0: Instance A nhận PAYMENT (O-42)
T1: Instance A nhận ADDRESS (O-42)
T2: MessageGroupStore ghi bền vững 2/3 phần
T3: Dừng instance A
T4: Khởi động instance B với cùng store/schema
T5: B gửi INVENTORY (O-42)
T6: Aggregator release một kết quả đúng cho O-42
~~~

Kiểm chứng thêm:

- **groupKey** và payload vẫn deserialize được sau nâng cấp version.
- State group incomplete không bị reset/duplicate do bean mới.
- Group timeout/reaper hoặc cơ chế expiry vẫn được kích hoạt sau restart; timer từng group trong RAM không nên được coi là sẽ tự khôi phục nguyên vẹn.
- Metadata completed/late-arrival được giữ hoặc dọn theo chính sách.
- Một số headers như object channel hoặc transport callback có thể không serialize được; phải quy định header mapping.
- Hai instance cùng truy cập store cần lock phù hợp, không chỉ dựa vào việc dữ liệu nằm trong DB/Redis.

Với test crash thực, phải có cơ chế đóng tiến trình hoặc tắt instance tại checkpoint có kiểm soát. Nếu chỉ gọi **context.close()** sau khi transaction đã hoàn thành, đó là test restart bình thường, **chưa phải** test crash giữa commit và publish.

## 13. Quan sát và chẩn đoán khi một group không bao giờ hoàn tất

Một log tốt phải phân biệt **group ID, business ID, event ID, message ID và attempt**:

~~~text
flow=orderConfirmation
endpoint=orderAggregator
groupKey=order-ready:v1:O-42:R-7
correlationId=checkout-O-42
eventId=stock-8
step=INVENTORY
groupSize=2
presentSteps=PAYMENT,INVENTORY
missingSteps=ADDRESS
decision=WAIT
thread=aggregation-worker-3
~~~

Đây là một **mẫu log tự thiết kế**, không phải trường mặc định được Spring Integration ghi ra.

Các tín hiệu runtime nên theo dõi:

| Chỉ số | Câu hỏi vận hành |
| --- | --- |
| Số **incomplete groups** | Có message thiếu, sai correlation hoặc filter bỏ phần không? |
| **Age** và **lastModified age** của group | Nhóm nào chưa được cập nhật quá SLA? |
| Số message/group và **unique eventId** | Có duplicate khiến size tăng nhưng chưa đủ bước không? |
| Release rate và thời gian chờ release | Có nhóm mất quá lâu vì một upstream chậm? |
| Timeout, partial, discard, late arrival | Chính sách xử lý thiếu phần có hoạt động đúng? |
| FailedMessage/errorChannel count | Có lỗi bị ghi log rồi bỏ qua hoặc mất correlation không? |
| Store latency, serialization errors, lock contention | DB/Redis/instance đang gây nghẽn hay lỗi state? |
| Retry/redelivery và duplicate outputs | Có retry lồng nhiều tầng hoặc idempotency chưa đủ? |

Khi tìm một group không release, điều tra theo thứ tự:

1. **Nguồn:** Ba bước có được phát thực sự không, bằng chứng eventId nào?
2. **Đầu vào aggregator:** Mỗi message mang **groupKey** gì sau transformer/filter/router?
3. **Store:** Group với khóa mong đợi có bao nhiêu phần, complete flag và timestamps ra sao?
4. **ReleaseStrategy:** Điều kiện thiếu là gì, có duplicate/conflict hay payload không hợp lệ?
5. **Timeout:** Deadline đã đến chưa, scheduler/reaper có hoạt động sau restart?
6. **Thread/transaction:** Có task bị reject, rollback, deadlock hoặc lock contention?
7. **Output:** Release thành công nhưng output processor, adapter hoặc downstream đã thất bại ở đâu?

Chỉ nhìn **group.size()** là chưa đủ; cần thêm **tập các bước duy nhất**, trạng thái payload và thông tin phiên xử lý.

## 14. Bài thực hành mở rộng: ma trận lỗi cần kiểm chứng

**Đề bài:** Một flow xác nhận đơn hàng phải nhận ba bước từ broker, có thể chạy trên nhiều instance. SLA **2 phút** kể từ khi bắt đầu nhóm; nếu thiếu phần, phải ghi **OrderAssemblyTimedOut** và không phát **OrderReady**. Broker có at-least-once delivery, có thể tạo duplicate sau restart.

Thiết kế kiểm thử theo ma trận:

| Ca | Tác động giả lập | Kỳ vọng kiểm chứng |
| --- | --- | --- |
| A | Đảo cả sáu hoán vị của 3 phần | Mỗi group phát đúng một OrderReady khi đủ điều kiện |
| B | Thiếu mỗi loại Step một lần | Không release sớm; hết SLA đi timeout flow |
| C | Một Step có 2 lần giao cùng eventId | Không đếm duplicate; không release sớm |
| D | Một Step gửi payload accepted=false | Xử lý conflict/failure, không phát thành công |
| E | Phần thứ ba tới sau timeout | Theo chính sách late arrival, không tự tạo OrderReady sai |
| F | Cùng orderId nhưng khác runId | Hai nhóm độc lập, không trộn payload |
| G | Hai orderId xen kẽ | Không lẫn group, không phụ thuộc thứ tự output giữa group |
| H | Ba producer gửi đồng thời | Không mất state, không phát hai lần |
| I | Restart sau 2/3 phần | Persistent store tiếp tục với 2/3 phần đã ghi |
| J | Hai instance cùng gửi phần cuối | Lock/idempotency giữ đúng nghiệp vụ |
| K | Output processor ném exception | Error flow được kích hoạt, state/retry được xác minh |
| L | Producer timeout rồi gửi lại | eventId/idempotency key giữ nguyên, side effect không lặp |
| M | Group đã complete nhưng metadata được dọn | Late message xử lý theo chính sách đã thiết kế, không phát nghiệp vụ trùng |

### Gợi ý tổ chức test suite

Phân thành các mức độc lập:

- **Unit test ReleaseStrategy:** tất cả tập Step con, duplicate, accepted=false, payload sai kiểu. Test nhanh logic, nhưng **không** chứng minh tính đúng của channel/store.
- **Integration test trong một context:** DirectChannel + QueueChannel + aggregator + SimpleMessageStore. Kiểm tra thời điểm release, headers, message grouping và output.
- **Integration test có scheduler/timeouts:** groupTimeout, expiry/discard, state store sau timeout; dùng điều kiện/tín hiệu đồng bộ để tránh sleep tùy ý.
- **Stress/concurrency test:** nhiều producer, cùng và khác groupKey, bounded timeouts, kiểm tra tổng output và deadlock.
- **End-to-end với broker/persistent store:** redelivery, restart, hai instance, transaction, lock, idempotency và downstream output.

Không cần chạy stress test nặng trong mọi lần commit, nhưng các điều kiện **out-of-order, missing, duplicate** nên là regression test lặp lại khi thay đổi release strategy, correlation mapping hoặc schema payload.

## 15. Checklist trước khi triển khai

- Các bước nghiệp vụ **cần đủ** là gì? Đủ số message hay đủ **loại message duy nhất**?
- Đã tách **groupKey / correlationId / eventId / requestId / MessageHeaders.ID** chưa?
- ReleaseStrategy có kết quả **bất biến với thứ tự đến** và không có side effect?
- Có kiểm thử tất cả hoán vị quan trọng, và kiểm tra **không release sau từng phần chưa đủ**?
- Có test missing message **trước và sau deadline**, với trạng thái timeout có thể quan sát?
- Duplicate có thể đến với **Message ID mới** không; cơ chế dedup có atomic giữa các instance?
- Khi group complete, late arrival đi đâu; giữ/xóa metadata sau bao lâu?
- **Partial release** có được phép không; nếu có, downstream có biết kết quả thiếu?
- Group ID có namespace và **runId** để tránh trộn các phiên xử lý không?
- Store có bền vững qua restart; serialization, transaction và lock đã được kiểm tra?
- Flow có ExecutorChannel/poller/broker redelivery khiến thứ tự và transaction thay đổi không?
- ErrorMessage còn **failedMessage, correlation, business key** để chẩn đoán?
- Test đã kiểm tra cả **output payload**, **số lần phát**, **state store** và **side effect thực** chưa?
- Có metric cho incomplete/expired groups, duplicate, contention và age vượt SLA?

## Kết luận

**Kiểm thử message đến lệch thứ tự hoặc thiếu** là cách chứng minh một correlating flow hoạt động đúng dưới điều kiện runtime thực tế. Với Spring Integration, cần kiểm tra **CorrelationStrategy** nhóm đúng message, **ReleaseStrategy** chỉ phát khi đủ điều kiện, **MessageGroupStore** giữ state theo vòng đời, và **timeout/recovery** có kết cục rõ khi thiếu phần.

Đừng dừng ở test “gửi ba message và nhận một kết quả”. Hãy thử mọi thứ tự quan trọng, cố tình bỏ một phần, gửi duplicate, đưa message đến muộn, chạy đồng thời và restart. Kết hợp business idempotency, transaction, locking và khả năng quan sát để một OrderReady được hiểu đúng **một lần về mặt nghiệp vụ**, dù có thể tồn tại nhiều attempt và delivery kỹ thuật.

## Tài liệu tham khảo

- [Spring Integration Reference — Aggregator](https://docs.spring.io/spring-integration/reference/aggregator.html)
- [Spring Integration Reference — Message Store](https://docs.spring.io/spring-integration/reference/message-store.html)
- [Spring Integration Reference — Message Channel Implementations](https://docs.spring.io/spring-integration/reference/channel/implementations.html)
- [Spring Integration Reference — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html)
- [Spring Integration Reference — Testing](https://docs.spring.io/spring-integration/reference/testing.html)
- [Spring Integration API — ReleaseStrategy](https://docs.spring.io/spring-integration/api/org/springframework/integration/aggregator/ReleaseStrategy.html)
- [Spring Integration API — MessageGroupStore](https://docs.spring.io/spring-integration/api/org/springframework/integration/store/MessageGroupStore.html)
