# Chính sách retry, trì hoãn và hàng đợi lỗi của nhà cung cấp

> Mục tiêu: hiểu cách JMS provider xử lý message bị rollback hoặc giao thất bại; phân biệt retry trong ứng dụng với broker redelivery; cấu hình số lần thử, delay/backoff và Dead Letter Queue (DLQ); phối hợp chính sách broker với Spring listener transaction, error handling và idempotency.

## 1. Vì sao cần chính sách redelivery?

Một consumer có thể không xử lý được message vì lỗi tạm thời như database timeout, downstream service ngừng hoạt động hoặc mất kết nối. Với session transacted, listener có thể ném exception để rollback message. Broker sau đó có thể giao lại message cho consumer.

Nếu broker giao lại ngay lập tức và listener tiếp tục thất bại, message có thể tạo vòng lặp rollback liên tục. Vòng lặp này tiêu thụ CPU, network và listener thread, đồng thời làm các message khác bị chậm. Nếu không giới hạn số lần giao lại, một message lỗi vĩnh viễn có thể chiếm queue vô thời hạn.

Chính sách retry/redelivery thường cần trả lời bốn câu hỏi:

1. Có thử lại hay không khi listener rollback?
2. Chờ bao lâu trước lần giao lại tiếp theo?
3. Tối đa bao nhiêu lần giao thất bại?
4. Sau khi hết lượt, message được chuyển đến đâu và ai chịu trách nhiệm xử lý?

JMS định nghĩa cơ chế acknowledgement, transaction và metadata nhận biết redelivery. Tuy nhiên, cấu hình delay, giới hạn delivery attempts và đích DLQ là tính năng do từng provider triển khai; không có một API cấu hình portable áp dụng giống nhau cho mọi broker.

## 2. Phân biệt ba tầng retry

Cần tách rõ retry ở code ứng dụng, redelivery của broker và việc chuyển message vào DLQ:

| Tầng | Ai thực hiện? | Phạm vi |
|---|---|---|
| Application retry | Code listener/service hoặc thư viện retry | Gọi lại một thao tác bên trong cùng lần giao message, ví dụ gọi API hoặc truy vấn database |
| JMS redelivery | JMS provider/broker | Giao lại message sau khi transaction rollback, session recover hoặc lần giao không được xác nhận |
| Dead Letter Queue | Broker/provider | Chuyển message sang địa chỉ/queue lỗi sau khi vượt ngưỡng giao thất bại hoặc theo chính sách provider |

Ví dụ: listener gọi payment API. Có thể retry API hai lần trong cùng lần giao JMS để xử lý timeout ngắn. Nếu vẫn lỗi, listener ném exception; JMS transaction rollback và broker có thể giao lại message sau một khoảng delay. Sau số lần giao thất bại tối đa, broker chuyển message vào DLQ.

Không nhầm `errorChannel` của Spring Integration với DLQ. `errorChannel` là luồng xử lý lỗi trong application context; DLQ là destination do broker quản lý. Một error flow xử lý exception rồi trả về bình thường có thể khiến listener invocation kết thúc thành công và transaction commit. Nếu muốn rollback, error flow phải ném lại exception hoặc một exception khác theo cấu hình transaction.

## 3. Điều kiện để broker redeliver message

Broker thường redeliver khi lần giao trước không được commit/acknowledge. Những tình huống phổ biến gồm:

- Listener ném exception trong một transacted JMS session và container rollback.
- Ứng dụng gọi `Session.rollback()` trong transaction cục bộ.
- Session/connection đóng trước khi transaction được commit.
- Client dùng `CLIENT_ACKNOWLEDGE` và gọi cơ chế phục hồi như `Session.recover()` theo JMS API.
- Consumer mất kết nối hoặc hết thời gian lease/timeout trước khi acknowledgement được ghi nhận, tùy provider.

Với Spring listener container, cấu hình `sessionTransacted=true` để listener invocation chạy trong local JMS transaction. Nếu listener kết thúc bình thường, container commit; nếu exception thoát khỏi listener, container rollback và provider có thể redeliver.

Ví dụ DMLC factory:

```java
import jakarta.jms.ConnectionFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;

@Configuration
class JmsListenerConfiguration {

    @Bean
    DefaultJmsListenerContainerFactory ordersListenerFactory(
            ConnectionFactory connectionFactory) {
        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setSessionTransacted(true);
        factory.setConcurrency("2-8");
        return factory;
    }
}
```

Ví dụ dùng `jakarta.jms` cho Spring Framework 6/7; Spring Framework 5 dùng `javax.jms`. Cần để exception truyền ra khỏi listener nếu muốn transaction rollback. Bắt exception, chỉ ghi log rồi trả về bình thường thường khiến container xem lần xử lý là thành công và commit message.

Spring cảnh báo `AUTO_ACKNOWLEDGE` mặc định không bảo đảm reliability cho listener container. Nếu cần redelivery đáng tin cậy, hãy dùng transacted session hoặc transaction manager phù hợp thay vì dựa vào việc listener ném exception trong chế độ acknowledgement mặc định.

## 4. Metadata nhận biết message được giao lại

JMS cung cấp hai metadata hữu ích:

- `JMSRedelivered`: header boolean cho biết provider có khả năng đã giao message trước đó nhưng chưa được xác nhận. Giá trị `true` là tín hiệu cần phòng tránh xử lý trùng; nó không cho biết nghiệp vụ đã chạy đến bước nào.
- `JMSXDeliveryCount`: property chuẩn cho biết số lần message đã được giao. Lần nhận đầu có giá trị 1; giá trị từ 2 trở lên cho biết message đã được giao lại.

Theo Jakarta Messaging specification, provider không bảo đảm `JMSXDeliveryCount` luôn chính xác tuyệt đối trong mọi tình huống lỗi vì không bắt buộc phải persist bộ đếm này trước mọi lần giao. Vì vậy, dùng nó để quan sát và hỗ trợ policy, không dùng làm khóa idempotency hoặc bằng chứng chính xác về số lần side effect đã xảy ra.

Ví dụ đọc metadata trong listener:

```java
import jakarta.jms.JMSException;
import jakarta.jms.Message;
import org.springframework.jms.annotation.JmsListener;

@JmsListener(
        destination = "orders.incoming",
        containerFactory = "ordersListenerFactory"
)
public void receive(Message message) throws JMSException {
    boolean redelivered = message.getJMSRedelivered();
    Object count = message.getObjectProperty("JMSXDeliveryCount");

    log.info("redelivered={}, deliveryCount={}", redelivered, count);
    process(message);
}
```

Đây là đoạn mã minh họa đọc metadata; `log` và `process` là thành phần do ứng dụng cung cấp. Với method listener nhận DTO trực tiếp, có thể dùng tham số `jakarta.jms.Message` hoặc `@Header` phù hợp để đọc metadata tùy cấu hình adapter/converter.

## 5. Delay và exponential backoff

Redelivery delay là khoảng chờ sau một lần giao thất bại trước khi broker thử giao lại. Delay giúp dependency có thời gian phục hồi và tránh retry dồn dập.

Một lịch exponential backoff thường có dạng:

\[d_n = \min(d_{max}, d_0 \times m^{n-1})\]

Trong đó:

- `d0`: thời gian chờ ban đầu.
- `m`: hệ số nhân, thường lớn hơn 1.
- `n`: số lần redelivery tiếp theo.
- `dmax`: giới hạn delay tối đa.

Ví dụ `d0=1s`, `m=2`, `dmax=30s`: các khoảng chờ lần lượt là 1s, 2s, 4s, 8s, 16s, rồi tối đa 30s. Provider có thể hỗ trợ thêm jitter/collision avoidance để nhiều consumer không cùng retry vào một thời điểm.

Delay không đồng nghĩa với `Thread.sleep()` trong listener. Ngủ trong listener giữ thread và có thể giữ transaction/session mở trong suốt thời gian chờ. Broker-side delayed redelivery thường giải phóng consumer để xử lý message khác, nhưng cách sắp xếp message trong queue phụ thuộc provider.

Cần phân biệt redelivery delay với scheduled/initial delivery delay. JMS 2.0 có API delivery delay cho message mới được gửi; đó là thời gian trì hoãn lần giao đầu tiên, không phải policy retry sau rollback. Redelivery delay thường là cấu hình riêng của broker.

## 6. Giới hạn số lần giao và poison message

Poison message là message liên tục gây thất bại và không thể xử lý thành công theo cấu hình hiện tại. Nguyên nhân thường gặp:

- JSON/XML sai cú pháp hoặc payload không đúng schema.
- Type ID không được consumer hỗ trợ hoặc dữ liệu bắt buộc bị thiếu.
- Business rule không thể thỏa mãn với dữ liệu hiện tại.
- Consumer và producer không tương thích phiên bản.
- Code bug khiến cùng một nhánh luôn ném exception.

Broker policy thường có ngưỡng tối đa delivery attempts. Khi message vượt ngưỡng, broker có thể chuyển message sang DLQ, discard hoặc áp dụng hành động provider-specific. Không nên giả định mọi provider có cùng cách đếm: có cấu hình đếm số lần redelivery sau lần đầu, có cấu hình mô tả tổng delivery attempts. Hãy đọc đúng tài liệu của provider và kiểm thử biên ngưỡng.

Không đặt ngưỡng vô hạn cho mọi queue. Với lỗi tạm thời, retry có giới hạn và delay là hợp lý. Với lỗi vĩnh viễn như payload sai, retry liên tục không thể sửa dữ liệu và chỉ làm nghẽn queue. Cần chuyển poison message sang DLQ/quarantine hoặc xử lý lỗi nghiệp vụ theo hợp đồng.

## 7. Dead Letter Queue là gì?

Dead Letter Queue (DLQ) là destination dùng để giữ message broker không thể giao thành công sau số lần thử hoặc theo một điều kiện lỗi đã cấu hình. DLQ cho phép hệ thống tiếp tục xử lý message hợp lệ trong queue chính, đồng thời giữ lại message lỗi để điều tra.

DLQ thường là queue bền vững được vận hành như một khu vực quarantine. Đội vận hành có thể xem payload/metadata, xác định nguyên nhân, sửa dữ liệu hoặc code rồi replay có kiểm soát.

DLQ không tự sửa message và không đồng nghĩa message đã bị xóa vĩnh viễn. Tùy provider, message có thể được chuyển đến dead-letter address, dead-letter queue mặc định hoặc bị discard nếu không cấu hình đích phù hợp. Phải xác minh cấu hình thực tế trước khi production.

### DLQ khác Expiry Queue

| Destination | Lý do message được chuyển đến |
|---|---|
| DLQ / Dead Letter Address | Giao thất bại, vượt số lần redelivery hoặc bị reject theo policy |
| Expiry Queue / Expiry Address | Message hết hạn theo TTL/expiration trước khi được tiêu thụ |

Một message hết hạn không nhất thiết là poison message. Ngược lại, message bị giao thất bại nhiều lần có thể chưa hết TTL. Nên quản lý DLQ và expiry destination riêng để phân biệt nguyên nhân.

## 8. Cấu hình ví dụ với Apache ActiveMQ Artemis

ActiveMQ Artemis cấu hình redelivery và dead-letter ở broker thông qua `address-setting` trong `broker.xml`. Ví dụ minh họa:

```xml
<address-settings>
  <address-setting match="orders.incoming">
    <dead-letter-address>DLQ</dead-letter-address>
    <max-delivery-attempts>5</max-delivery-attempts>
    <redelivery-delay>1000</redelivery-delay>
    <redelivery-delay-multiplier>2.0</redelivery-delay-multiplier>
    <max-redelivery-delay>30000</max-redelivery-delay>
    <redelivery-collision-avoidance-factor>0.1</redelivery-collision-avoidance-factor>
  </address-setting>
</address-settings>
```

Trong ví dụ, Artemis áp dụng policy cho address khớp `orders.incoming`, chờ 1 giây trước redelivery, tăng delay theo hệ số 2, giới hạn delay 30 giây và chuyển message vượt ngưỡng sang address `DLQ`. Cần tạo/bind queue nhận DLQ và xác nhận tên address thực tế mà JMS destination ánh xạ tới trong broker của bạn.

Các thuộc tính `max-delivery-attempts`, `redelivery-delay`, `redelivery-delay-multiplier`, `max-redelivery-delay` và `dead-letter-address` là cấu hình riêng của Artemis, không phải thuộc tính JMS portable. Nếu không cấu hình dead-letter address, hành vi sau khi vượt ngưỡng phụ thuộc phiên bản/cấu hình Artemis; tài liệu broker mô tả message có thể bị loại bỏ.

## 9. Cấu hình ví dụ với ActiveMQ Classic

ActiveMQ Classic dùng `RedeliveryPolicy` phía client để thiết lập delay và số lần redelivery. Ví dụ:

```java
import org.apache.activemq.ActiveMQConnectionFactory;
import org.apache.activemq.RedeliveryPolicy;

ActiveMQConnectionFactory connectionFactory =
        new ActiveMQConnectionFactory("tcp://localhost:61616");

RedeliveryPolicy policy = connectionFactory.getRedeliveryPolicy();
policy.setInitialRedeliveryDelay(1_000L);
policy.setUseExponentialBackOff(true);
policy.setBackOffMultiplier(2.0);
policy.setMaximumRedeliveries(5);
```

Đây là API riêng của ActiveMQ Classic client, không dùng được với Artemis hoặc JMS provider khác. `maximumRedeliveries` mô tả số lần redelivery được phép sau lần giao đầu; cần đọc đúng semantics của phiên bản client. Chính sách DLQ được cấu hình riêng ở broker, thường qua destination policy/dead-letter strategy; ActiveMQ Classic có DLQ mặc định `ActiveMQ.DLQ` và hỗ trợ cấu hình DLQ riêng theo destination.

Không sao chép tên class hoặc property của ActiveMQ Classic sang Artemis. Dù hai sản phẩm cùng thuộc Apache ActiveMQ, mô hình cấu hình redelivery/DLQ của chúng khác nhau.

## 10. Phối hợp retry của ứng dụng với redelivery của broker

Application retry phù hợp với một số lỗi tạm thời ngắn, ví dụ gọi HTTP service bị timeout trong vài trăm mili giây. Broker redelivery phù hợp khi cần chờ lâu hơn để dependency phục hồi và không muốn giữ listener thread/transaction trong lúc chờ.

Một chiến lược có thể dùng:

1. Thử lại thao tác downstream một số lần nhỏ trong thời gian ngắn.
2. Nếu vẫn thất bại, ném exception ra khỏi listener.
3. Listener container rollback JMS transaction.
4. Broker đợi theo redelivery delay rồi giao lại message.
5. Sau ngưỡng delivery attempts, broker chuyển message sang DLQ.

Nếu dùng Spring Retry `RetryTemplate` trong service, hãy quyết định rõ điều gì xảy ra khi hết lượt. Nếu recovery callback nuốt exception và trả về bình thường, listener có thể commit message dù nghiệp vụ chưa hoàn tất. Nếu muốn broker redeliver, phải để lỗi thoát khỏi listener hoặc chủ động rollback theo transaction contract.

Tránh nhân số lần thử một cách vô ý. Ví dụ 3 lần thử trong ứng dụng cho mỗi lần giao × 5 lần giao broker có thể tạo đến 15 lần gọi downstream. Hãy đặt một ngân sách retry tổng thể và tính cả thời gian chờ, timeout mỗi lần, transaction duration và deadline nghiệp vụ.

Không retry lỗi vĩnh viễn như validation, authentication/authorization sai hoặc schema không hỗ trợ. Có thể route thẳng sang quarantine/DLQ theo policy của ứng dụng/provider thay vì tiêu tốn toàn bộ số lần thử.

## 11. Spring Integration error flow và broker DLQ

Nếu JMS message được nhận qua Spring Integration inbound adapter, lỗi có thể được gửi vào `errorChannel` tùy cấu hình. Đây là error flow trong ứng dụng; nó không tự động là DLQ của broker.

Từ Spring Integration 4.2, lỗi conversion của inbound adapter/gateway cũng có thể được gửi đến `errorChannel`. Nếu error flow xử lý message lỗi rồi kết thúc bình thường, transaction có thể commit và message bị loại khỏi queue. Nếu muốn rollback để broker redeliver, error flow phải ném lại exception hoặc exception khác. Hãy kiểm tra chính xác version và flow cấu hình.

Với lỗi vĩnh viễn, error flow có thể ghi message vào một quarantine destination hoặc lưu payload/metadata bền vững rồi mới hoàn tất transaction. Nếu việc publish quarantine và acknowledge message gốc phải nguyên tử, cần cùng JMS transaction/session hoặc cơ chế transactional phù hợp; không giả định hai thao tác độc lập là atomic.

## 12. Thiết kế quy trình vận hành DLQ

DLQ cần được vận hành như một quy trình có chủ sở hữu, không chỉ là một queue được tạo ra:

1. **Phân loại:** tách lỗi tạm thời, lỗi dữ liệu, lỗi cấu hình và lỗi code.
2. **Quan sát:** ghi destination gốc, message ID, event ID, correlation ID, delivery count, thời điểm và nguyên nhân lỗi.
3. **Bảo vệ dữ liệu:** giới hạn quyền đọc DLQ, tránh log payload nhạy cảm và đặt retention phù hợp.
4. **Điều tra:** xác định message lỗi do producer, consumer, broker hay dependency downstream.
5. **Sửa nguyên nhân:** triển khai fix code, cấu hình hoặc data mapping trước khi replay.
6. **Replay có kiểm soát:** chọn batch nhỏ, theo dõi kết quả và giữ nguyên event ID để deduplication hoạt động.
7. **Đóng sự cố:** lưu lại nguyên nhân, số lượng message, thời gian ảnh hưởng và cách khôi phục.

Không tự động chuyển tất cả message trong DLQ trở lại queue chính theo lịch. Nếu nguyên nhân chưa được sửa, message sẽ tiếp tục thất bại và quay lại DLQ, tạo vòng lặp vận hành.

Khi replay, cần cân nhắc giữ nguyên business event ID để consumer nhận ra đây là cùng một sự kiện. Nếu tạo event ID mới, hệ thống có thể xem replay là nghiệp vụ mới và áp dụng side effect lần nữa. Việc giữ hay tạo ID mới phải theo hợp đồng replay của ứng dụng.

## 13. Idempotency và duplicate delivery

Retry/redelivery thường mang semantics at-least-once: message có thể được giao nhiều lần nếu lần xử lý trước không được xác nhận hoặc kết quả commit không rõ ràng. Broker không thể biết một HTTP call hoặc database transaction bên ngoài đã tạo side effect hay chưa.

Consumer cần idempotent:

- Dùng `eventId`/`commandId` ổn định do ứng dụng tạo.
- Ghi event ID đã xử lý vào inbox table có unique constraint.
- Cập nhật dữ liệu nghiệp vụ và inbox trong cùng database transaction.
- Dùng idempotency key khi gọi API thanh toán hoặc downstream service nếu có.
- Nếu duplicate đã hoàn tất, kết thúc listener thành công để transaction commit và broker ngừng giao lại.

`JMSRedelivered` và `JMSXDeliveryCount` giúp nhận biết delivery history; chúng không thay thế idempotency key. Không giả định DLQ loại bỏ duplicate hoặc đảm bảo exactly-once business effect.

## 14. Chọn policy theo loại lỗi

| Loại lỗi | Hành động gợi ý |
|---|---|
| Database timeout ngắn | Application retry ít lần; nếu hết lượt, rollback để broker redeliver sau delay |
| Downstream service đang outage | Broker-side delay/backoff, giới hạn số lần giao và cảnh báo outage |
| Payload sai schema hoặc JSON hỏng | Quarantine/DLQ sớm; không retry vô hạn |
| Thiếu quyền hoặc credential sai | Dừng/giảm retry, cảnh báo cấu hình; tránh gây bão xác thực |
| Business rule từ chối hợp lệ | Ghi kết quả nghiệp vụ từ chối và commit theo hợp đồng; không xem mọi rejection là lỗi kỹ thuật |
| Code bug gây exception lặp lại | Giới hạn redelivery, DLQ và cảnh báo để tránh poison message chặn queue |
| Broker restart hoặc network interruption | Dùng recovery của listener container/provider; xử lý duplicate và kết quả gửi không rõ ràng |

Một queue có thể cần policy khác queue khác. Ví dụ queue thanh toán có thể cần retry delay dài và DLQ có giám sát chặt; queue telemetry có thể chấp nhận discard một số message hết hạn. Đặt policy theo giá trị nghiệp vụ và SLA, không dùng một cấu hình chung thiếu phân biệt.

## 15. Kiểm thử retry, delay và DLQ

Cần kiểm thử với đúng broker/provider và version được triển khai:

1. Listener thành công: message được commit và không bị redeliver.
2. Listener ném exception trong transacted session: broker giao lại message.
3. Kiểm tra `JMSRedelivered` và `JMSXDeliveryCount` ở lần nhận tiếp theo.
4. Xác nhận delay thực tế gần với policy cấu hình; đo cả jitter và giới hạn delay.
5. Gây lỗi liên tục để xác nhận ngưỡng delivery attempts và hành vi khi vượt ngưỡng.
6. Xác nhận message đến đúng DLQ address/queue và vẫn giữ metadata cần thiết.
7. Xác nhận message hết TTL đi theo expiry policy, không bị nhầm với poison-message DLQ.
8. Replay message sau khi sửa lỗi và xác nhận idempotency ngăn side effect lặp.
9. Restart broker trong lúc consumer xử lý để kiểm tra redelivery và kết quả commit không rõ ràng.
10. Kiểm tra queue chính vẫn tiếp tục xử lý message hợp lệ khi một poison message bị đưa sang DLQ.

Không chỉ kiểm tra cấu hình XML/Java đã được load. Phải xác nhận hành vi thực tế bằng delivery count, timestamp, queue depth, DLQ contents và log broker.

## 16. Metrics và cảnh báo

Nên theo dõi:

- Số lần redelivery theo destination.
- Số message vào DLQ theo thời gian và theo loại lỗi.
- Queue depth, tuổi message cũ nhất và tốc độ tiêu thụ.
- Tỷ lệ listener exception, rollback và retry exhaustion.
- Delay thực tế giữa các lần giao lại.
- Số message được replay và tỷ lệ replay thành công.
- Consumer count, processing latency và downstream error rate.

Cảnh báo khi DLQ tăng bất thường, oldest-message-age vượt SLA, delivery count tăng nhanh hoặc queue depth liên tục tăng. Gắn correlation ID và event ID vào log để truy vết một message xuyên qua nhiều lần giao.

## 17. Lỗi thường gặp

- **Cho rằng JMS chuẩn định nghĩa một cấu hình DLQ chung:** redelivery limit, delay và DLQ routing phụ thuộc provider.
- **Nhầm application retry với broker redelivery:** một cái gọi lại thao tác trong listener; cái còn lại giao lại toàn bộ message.
- **Dùng `Thread.sleep()` trong listener để trì hoãn:** giữ thread và có thể giữ transaction/session mở.
- **Dùng `AUTO_ACKNOWLEDGE` nhưng kỳ vọng rollback khi listener lỗi:** cần transacted session hoặc transaction manager phù hợp.
- **Nuốt exception sau khi hết application retry:** listener có thể trả về thành công và message bị commit.
- **Đặt retry vô hạn:** poison message có thể làm nghẽn queue và tiêu tốn tài nguyên.
- **Không cấu hình DLQ address/queue:** provider có thể discard message sau ngưỡng thay vì lưu lại.
- **Nhầm DLQ với expiry queue:** hai destination biểu thị hai nguyên nhân khác nhau.
- **Cho rằng delivery count là bộ đếm tuyệt đối:** `JMSXDeliveryCount` không được bảo đảm chính xác tuyệt đối qua mọi failure.
- **Replay mà không kiểm tra idempotency:** side effect nghiệp vụ có thể bị lặp.
- **Cấu hình policy ActiveMQ Classic cho Artemis:** hai provider có API và broker configuration khác nhau.
- **Cho rằng Spring errorChannel tự động đưa message vào broker DLQ:** error channel là luồng trong ứng dụng, DLQ là destination do broker quản lý.

## 18. Quy trình xây dựng chính sách retry và DLQ

1. Xác định loại lỗi nào có thể phục hồi và lỗi nào là vĩnh viễn.
2. Chọn local JMS transaction hoặc transaction manager phù hợp để listener failure có thể rollback.
3. Chọn số lần thử, delay ban đầu, multiplier, delay tối đa và jitter theo SLA.
4. Xác định semantics đếm attempts chính xác của broker/version.
5. Cấu hình DLQ address/queue và quyền truy cập; cấu hình expiry riêng.
6. Đặt application retry nhỏ và giới hạn tổng số lần gọi downstream.
7. Đảm bảo exception được truyền ra ngoài listener khi cần broker redelivery.
8. Thiết kế idempotency/inbox và quy trình replay.
9. Kiểm thử rollback, delayed redelivery, max attempts, DLQ, expiry và broker restart.
10. Theo dõi queue depth, delivery count, retry exhaustion và DLQ; định kỳ rà soát message tồn đọng.

## 19. Kết luận

JMS transaction và exception propagation quyết định khi nào một message có thể được redeliver; JMS provider quyết định delay, số lần giao lại và destination nhận message lỗi. Spring listener container giúp quản lý transaction và listener lifecycle, còn policy redelivery/DLQ phải được cấu hình theo broker cụ thể.

Thiết kế đáng tin cậy cần retry có giới hạn, exponential backoff/jitter khi phù hợp, DLQ có quy trình điều tra và replay, cùng consumer idempotent. Hãy phân biệt lỗi tạm thời với poison message, kiểm tra semantics của delivery counter theo provider và kiểm thử hành vi thực tế thay vì giả định mọi JMS broker hoạt động giống nhau.

## Tài liệu tham khảo

- [Jakarta Messaging 3.1 — JMSRedelivered and JMSXDeliveryCount](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html)
- [Spring Framework Reference — Using Spring JMS](https://docs.spring.io/spring-framework/reference/integration/jms/using.html)
- [Spring Framework Reference — Receiving a Message](https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html)
- [Spring Integration — JMS Support and Inbound Conversion Errors](https://docs.spring.io/spring-integration/reference/jms.html)
- [Apache ActiveMQ Artemis — Redelivery and Dead Letter Addresses](https://activemq.apache.org/components/artemis/documentation/)
- [Apache ActiveMQ Classic — Message Redelivery and DLQ Handling](https://activemq.apache.org/components/classic/documentation/message-redelivery-and-dlq-handling)
- [Apache ActiveMQ Classic — Redelivery Policy](https://activemq.apache.org/components/classic/documentation/redelivery-policy)