# Kiểm thử externalization

*Xác nhận application event được chuyển thành message bên ngoài đúng hợp đồng và có thể phục hồi khi lỗi*

Externalization đưa application event từ ranh giới module Spring Modulith sang một tiến trình hoặc hệ thống khác, thường thông qua broker như RabbitMQ hoặc Kafka. Khi event được đánh dấu bằng `@Externalized`, phần tích hợp chịu trách nhiệm chuyển publication thành message, chọn destination và gửi theo cấu hình vận chuyển. Kiểm thử externalization cần xác nhận toàn bộ hợp đồng đó: event chỉ được gửi khi transaction nghiệp vụ commit, payload có thể được consumer giải mã, message đến đúng nơi và lỗi giao nhận có thể được quan sát, retry hoặc phục hồi.

Một unit test xác nhận service gọi `publishEvent` chưa chứng minh message đã đến broker. Một test chỉ kiểm tra broker có message cũng chưa chứng minh event contract đúng hoặc transaction rollback không phát message. Vì vậy, nên chia kiểm thử thành nhiều lớp và dùng broker thật trong integration test cho các semantics phụ thuộc broker.

## 1. Xác định phạm vi cần kiểm thử

Một luồng externalization thường gồm các thành phần:

1. Module nguồn thay đổi aggregate và phát application event.
2. Event được đánh dấu externalize và có target identifier.
3. Event publication registry ghi nhận publication cần giao.
4. Adapter chuyển event thành message, serialize payload và chọn destination.
5. Broker nhận message và áp dụng routing, durability, acknowledgement hoặc partition theo cấu hình.
6. Consumer nhận message, giải mã và thực hiện side effect.
7. Metric, log và trace giúp quan sát kết quả; retry hoặc resubmission phục hồi publication chưa hoàn tất.

Kiểm thử nên trả lời các câu hỏi sau:

- Event đúng loại có được externalize đến target mong muốn không?
- Event không được đánh dấu có bị gửi ra ngoài ngoài ý muốn không?
- Transaction rollback có ngăn message được gửi không?
- Payload có giữ event ID, type, schema version và dữ liệu cần thiết không?
- Message có được route đến đúng queue/topic và consumer không?
- Broker unavailable hoặc timeout có làm publication được giữ để phục hồi không?
- Consumer có xử lý an toàn khi message được giao lại không?
- Thông tin lỗi có đủ để điều tra mà không làm lộ payload nhạy cảm không?

## 2. Phân chia các lớp kiểm thử

Không cần dùng broker thật cho mọi test. Mỗi lớp nên kiểm tra một hợp đồng cụ thể:

| Lớp kiểm thử | Thành phần chính | Điều cần xác nhận |
|---|---|---|
| Unit test | Event factory, mapping và serializer | Dữ liệu event, discriminator, target logic và payload |
| Application integration test | Spring context, publisher, transaction và publication registry | Event được ghi nhận đúng; rollback không tạo publication đã commit |
| Adapter integration test | Spring Modulith integration và adapter AMQP/Kafka | Target được ánh xạ và message được gửi theo cấu hình |
| Broker integration test | RabbitMQ/Kafka thực tế hoặc Testcontainers | Routing, queue/topic, serialization, confirm, offset, acknowledgement và redelivery |
| Consumer integration test | Consumer cùng database | Giải mã, idempotency, retry và side effect |
| Contract test | Producer và consumer độc lập | Hai phía hiểu cùng schema và version |
| Operational test | Metric, log, alert và runbook | Lỗi được phát hiện và thông tin vận hành có thể hành động |

Mock giúp kiểm tra logic cục bộ nhanh, nhưng không mô phỏng đầy đủ broker topology, persistence, routing hoặc acknowledgement. Dùng test tích hợp ở những điểm mà hành vi phụ thuộc nền tảng messaging.

## 3. Định nghĩa event contract ổn định

Trước khi kiểm thử transport, xác định payload là hợp đồng giữa producer và consumer. Ví dụ:

```java
import java.time.Instant;
import java.util.UUID;
import org.springframework.modulith.events.Externalized;

@Externalized("orders.completed")
public record OrderCompleted(
    UUID eventId,
    UUID orderId,
    Instant completedAt,
    int schemaVersion
) {}
```

`eventId` định danh một lần phát event và phải giữ nguyên qua retry hoặc resubmission. `orderId` là định danh nghiệp vụ ổn định. `completedAt` biểu diễn thời điểm sự kiện xảy ra; `schemaVersion` giúp consumer nhận biết cấu trúc payload. Target `orders.completed` là định danh logic; adapter và cấu hình integration quyết định nó được ánh xạ sang topic, exchange/routing key hay destination nào.

Không dùng entity JPA hoặc object persistence làm message contract. Event nên bất biến, có kích thước phù hợp và chỉ chứa dữ liệu consumer được phép nhận. Không đưa secret hoặc dữ liệu cá nhân không cần thiết vào payload.

## 4. Kiểm thử serialization và schema

Serialization test kiểm tra payload được tạo ra đúng hợp đồng trước khi gửi qua mạng. Với JSON, nên xác nhận:

- Tên field, kiểu dữ liệu và nullability đúng quy ước.
- UUID, timestamp, enum và số tiền có định dạng nhất quán.
- Event type/discriminator và schema version được giữ lại.
- Consumer có thể giải mã payload thành kiểu event mong đợi.
- Field mới hoặc subtype mới tuân theo chính sách tương thích.
- Payload không chứa field nội bộ hoặc dữ liệu nhạy cảm ngoài hợp đồng.

Ví dụ kiểm tra round-trip bằng `ObjectMapper` đã cấu hình cho ứng dụng:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.Instant;
import java.util.UUID;
import org.junit.jupiter.api.Test;

class OrderCompletedSerializationTest {

    private final ObjectMapper objectMapper = applicationObjectMapper();

    @Test
    void serializesAndRestoresTheEventContract() throws Exception {
        var event = new OrderCompleted(
            UUID.fromString("6d947d20-5b1c-45c6-a6d6-87c7c96d9f12"),
            UUID.fromString("7b0e0d16-37b1-4b77-9a4d-bc7c7a8d8a01"),
            Instant.parse("2026-11-25T10:15:30Z"),
            1
        );

        String json = objectMapper.writeValueAsString(event);
        OrderCompleted restored = objectMapper.readValue(json, OrderCompleted.class);

        assertEquals(event, restored);
    }
}
```

`applicationObjectMapper()` đại diện cho mapper đã được cấu hình trong test context; không tạo một mapper mặc định khác với mapper của adapter. Nên giữ JSON fixture cho các schema version đang được hỗ trợ để phát hiện thay đổi không tương thích khi nâng cấp producer hoặc consumer.

Nếu dùng polymorphic event, kiểm tra discriminator ổn định và chỉ cho phép subtype nằm trong allow-list. Payload có event type không được hỗ trợ phải thất bại theo chính sách rõ ràng, không âm thầm chuyển thành một subtype mặc định.

## 5. Kiểm thử transaction commit và rollback

Một trong những bảo đảm quan trọng là message chỉ được externalize sau khi transaction nghiệp vụ commit. Test cần xác nhận cả hai nhánh:

- **Commit:** thay đổi aggregate được commit, publication được ghi nhận và message được gửi đến broker.
- **Rollback:** transaction thất bại, thay đổi nghiệp vụ rollback và không có message đại diện cho thay đổi chưa commit.

Có thể viết application integration test với Spring context và adapter thật nhưng broker được thay bằng broker test. Gọi use case qua Spring bean để transaction proxy thực sự hoạt động; không tự tạo service bằng `new` trong test vì khi đó `@Transactional` và listener infrastructure có thể không được áp dụng.

Ví dụ về kịch bản rollback:

```java
@SpringBootTest
class OrderExternalizationTransactionTest {

    @Autowired CompleteOrder completeOrder;
    @Autowired OrderRepository orders;
    @Autowired RabbitTemplate rabbitTemplate;

    @Test
    void doesNotSendAnEventWhenTheBusinessTransactionRollsBack() {
        assertThrows(
            IllegalStateException.class,
            () -> completeOrder.completeAndFailAfterPublishing(testOrderId())
        );

        assertFalse(orders.findById(testOrderId()).orElseThrow().isCompleted());
        assertNull(rabbitTemplate.receive("billing.order-completed", 1_000));
    }
}
```

`completeAndFailAfterPublishing` và queue trong ví dụ là fixture của ứng dụng cần xây dựng. Test phải dùng cùng cấu hình externalization và transaction như ứng dụng; nếu adapter bất đồng bộ, cần đợi trong giới hạn thời gian hoặc đồng bộ test theo trạng thái publication thay vì giả định message xuất hiện tức thì.

Tránh bọc toàn bộ test bằng một transaction test tự rollback nếu mục tiêu là kiểm tra transaction nghiệp vụ và after-commit behavior. Transaction của test có thể làm thay đổi thời điểm commit và khiến kết quả không phản ánh luồng thực tế.

## 6. Kiểm thử target mapping và broker routing

Test adapter phải xác nhận target logic được ánh xạ đến đúng destination theo cấu hình ứng dụng. Với RabbitMQ, kiểm tra exchange, routing key, binding và queue. Với Kafka, kiểm tra topic, message key, header và partition behavior cần thiết.

Các trường hợp nên có:

1. Event `OrderCompleted` đến đúng destination đã cấu hình.
2. Event khác không bị route nhầm vào destination của `OrderCompleted`.
3. Queue hoặc subscription nhận đúng message theo binding/routing rule.
4. Message key hoặc partition key giữ đúng thứ tự trong phạm vi nghiệp vụ cần thiết.
5. Message không khớp binding được phát hiện qua publisher return/alternate exchange nếu cấu hình sử dụng.
6. Target không tồn tại hoặc broker từ chối publish tạo ra lỗi có thể quan sát.

Không suy luận target identifier luôn là tên exchange, routing key hay topic. Quy tắc mapping phụ thuộc integration module và phiên bản Spring Modulith. Test nên xác nhận destination thực tế của adapter thay vì chỉ kiểm tra annotation có chuỗi mong muốn.

## 7. Dùng Testcontainers cho broker integration test

Testcontainers giúp chạy broker thật trong phạm vi test, giảm khác biệt giữa mock và môi trường vận hành. Ví dụ với RabbitMQ:

```java
import org.junit.jupiter.api.Test;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.RabbitMQContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers
@SpringBootTest
class OrderExternalizationRabbitMqTest {

    @Container
    static final RabbitMQContainer rabbit =
        new RabbitMQContainer("rabbitmq:3.13-management-alpine");

    @DynamicPropertySource
    static void rabbitProperties(DynamicPropertyRegistry properties) {
        properties.add("spring.rabbitmq.host", rabbit::getHost);
        properties.add("spring.rabbitmq.port", rabbit::getAmqpPort);
        properties.add("spring.rabbitmq.username", rabbit::getAdminUsername);
        properties.add("spring.rabbitmq.password", rabbit::getAdminPassword);
    }

    @Autowired CompleteOrder completeOrder;
    @Autowired RabbitTemplate rabbitTemplate;

    @Test
    void externalizesCompletedOrderToTheConfiguredQueue() {
        completeOrder.complete(testOrderId());

        Object message = rabbitTemplate.receiveAndConvert(
            "billing.order-completed", 5_000
        );

        assertNotNull(message);
    }
}
```

Ví dụ minh họa cách khởi chạy RabbitMQ và cấp thông tin kết nối cho Spring Boot. Test cần khai báo topology và cấu hình Spring Modulith AMQP integration giống ứng dụng. Queue `billing.order-completed`, use case và mapping target phải tồn tại trong fixture. Tùy phiên bản Spring Boot/Testcontainers, có thể dùng service connection thay cho `DynamicPropertySource`.

Với Kafka, có thể dùng Kafka Testcontainer hoặc môi trường broker tương thích, cấp bootstrap servers vào test context, tạo topic và consumer test. Đọc message theo timeout có giới hạn; không dùng `Thread.sleep` cố định vì nó làm test chậm và không loại bỏ race condition.

## 8. Kiểm thử Event Publication Registry

Registry theo dõi publication cần giao đến transactional listener hoặc externalization target. Kiểm thử nên xác nhận:

- Publication được ghi nhận khi transaction publisher commit.
- Publication của transaction rollback không tồn tại như một công việc đã commit cần externalize.
- Khi adapter gửi thành công, publication chuyển sang trạng thái hoàn tất theo integration đang dùng.
- Khi broker không sẵn sàng hoặc publish thất bại, publication chưa hoàn tất vẫn có thể được phát hiện.
- Sau khi dependency phục hồi, retry/resubmission có thể hoàn tất publication.
- Một event có nhiều listener có trạng thái publication riêng theo listener/target.

Không gắn test với tên bảng hoặc cột nội bộ của persistence implementation nếu API công khai đã đủ để quan sát. Cách truy vấn publication và thao tác resubmit có thể thay đổi theo phiên bản Spring Modulith; dùng API được hỗ trợ trong dependency của dự án.

Registry theo dõi trạng thái giao, không chứng minh consumer bên ngoài đã hoàn tất nghiệp vụ. Nếu broker xác nhận nhận message, publication phía producer có thể hoàn tất dù consumer còn đang xử lý. Kiểm thử end-to-end cần xác nhận consumer riêng nếu yêu cầu nghiệp vụ đòi hỏi điều đó.

## 9. Kiểm thử lỗi vận chuyển và phục hồi

Externalization cần chịu được broker unavailable, timeout, mất kết nối và lỗi routing. Hãy mô phỏng lỗi có kiểm soát:

- Broker không sẵn sàng khi ứng dụng cố publish.
- Broker nhận message nhưng producer timeout trước khi nhận confirm.
- Exchange/topic hoặc destination không tồn tại.
- Message không khớp binding hoặc không có consumer.
- Serialization thất bại vì payload không hợp lệ.
- Connection bị ngắt trong lúc gửi hoặc consumer đang nhận.
- Broker phục hồi sau một khoảng gián đoạn và backlog được xử lý lại.

Sau lỗi, xác nhận publication hoặc message được giữ theo semantics đã cấu hình, retry có backoff và có giới hạn, lỗi vĩnh viễn được chuyển đến nơi điều tra phù hợp. Không giả định mọi lỗi đều retry được; payload sai schema cần sửa hợp đồng hoặc dữ liệu trước khi gửi lại.

## 10. Kiểm thử duplicate và idempotency ở consumer

Timeout hoặc mất acknowledgement có thể khiến cùng một message được giao lại. Consumer cần dùng `eventId` ổn định để tránh side effect trùng. Test nên gửi cùng payload/event ID nhiều lần và xác nhận read model hoặc dữ liệu nghiệp vụ chỉ thay đổi một lần.

Nếu dùng inbox pattern, kiểm tra unique constraint theo consumer và event ID. Việc ghi inbox và cập nhật read model phải nằm trong cùng transaction. Test cạnh tranh nên dùng database thật hoặc database test tương thích để xác nhận hai worker đồng thời không cùng claim event.

Nếu consumer gọi API bên ngoài, kiểm tra idempotency key được truyền ổn định qua các lần gọi. Mô phỏng timeout sau khi hệ thống đích đã thực hiện side effect để xác nhận lần retry không tạo tác động thứ hai. Mock trả lỗi trước khi side effect xảy ra chưa bao phủ được tình huống khó này.

## 11. Kiểm thử consumer contract và schema evolution

Producer và consumer có thể được triển khai ở các thời điểm khác nhau. Contract test nên xác nhận:

- Consumer đọc được payload do producer hiện tại phát.
- Consumer mới đọc được fixture của schema cũ trong giai đoạn tương thích.
- Producer mới không xóa hoặc đổi nghĩa field mà consumer cũ vẫn cần.
- Event type hoặc discriminator mới được xử lý theo chính sách rõ ràng.
- Unknown subtype hoặc payload sai cấu trúc được đưa vào luồng lỗi có thể điều tra.
- Timestamp, UUID, enum, tiền tệ và giá trị null được diễn giải thống nhất.

Giữ fixture JSON hoặc schema đại diện trong test của producer và consumer. Khi hợp đồng thay đổi không tương thích, phát hành version mới và triển khai consumer có khả năng đọc trước khi producer bắt đầu phát version đó.

## 12. Kiểm thử bảo mật và quyền truy cập

Broker integration test nên xác nhận producer chỉ publish vào destination được cấp quyền và consumer chỉ subscribe các destination cần thiết. Nếu môi trường dùng TLS hoặc cơ chế xác thực, kiểm tra cấu hình kết nối trong test môi trường phù hợp; không ghi credential vào log hoặc fixture.

Payload test nên xác nhận không có secret, token hoặc dữ liệu cá nhân ngoài hợp đồng. Nếu event chứa thông tin nhạy cảm được mã hóa hoặc token hóa, kiểm tra consumer được phép giải mã theo đúng quyền và key version. Không dùng dữ liệu production thật trong fixture test.

## 13. Kiểm thử metric, log và trace

Khi externalization thất bại, người vận hành cần phân biệt lỗi ở producer, adapter, broker hay consumer. Kiểm tra metric và log có các thông tin phù hợp:

- Event type, event ID và target/destination.
- Publication attempt, success/failure và tuổi publication chưa hoàn tất.
- Publisher confirm/return hoặc lỗi kết nối theo broker.
- Consumer lag, queue depth, redelivery và dead-letter count nếu có.
- Correlation ID và trace context được truyền qua header theo cấu hình.
- Không có payload nhạy cảm hoặc secret trong log.

Không dùng event ID làm tag metric vì cardinality cao. Event ID nên nằm trong log hoặc trace có kiểm soát; metric dùng các tag hữu hạn như event type, listener, destination và outcome.

## 14. Tránh test flaky và test phụ thuộc thời gian

Externalization thường bất đồng bộ nên test dễ thất bại ngẫu nhiên nếu giả định message xuất hiện ngay sau lệnh publish. Một số nguyên tắc:

- Dùng polling hoặc Awaitility với timeout hữu hạn để đợi điều kiện cuối cùng.
- Không dùng `Thread.sleep` cố định để phỏng đoán thời điểm consumer hoàn tất.
- Dùng queue/topic và event ID riêng cho mỗi test để tránh message còn sót từ test trước.
- Xóa hoặc drain message test theo cách an toàn trước/sau mỗi test; không purge destination dùng chung với test khác đang chạy song song.
- Dùng transaction boundary thật; tránh test transaction rollback tự động che khuất after-commit behavior.
- Đặt timeout đủ cho broker container khởi động nhưng không quá dài để che giấu lỗi.
- Không phụ thuộc thứ tự test hoặc dữ liệu singleton dùng chung.

Nếu cần kiểm tra thứ tự, phát event có sequence xác định và assert thứ tự theo phạm vi broker thực sự bảo đảm, chẳng hạn trong một Kafka partition. Không yêu cầu thứ tự toàn cục khi topology không cung cấp bảo đảm đó.

## 15. Ma trận kiểm thử đề xuất

Một ma trận ngắn giúp nhóm kiểm tra đủ đường đi và lỗi quan trọng:

| Kịch bản | Thành phần cần quan sát | Kết quả mong đợi |
|---|---|---|
| Event được phát và transaction commit | Aggregate, registry, broker | Một publication được ghi nhận và message đến destination đúng |
| Transaction rollback | Database, registry, broker | Không có message cho thay đổi chưa commit |
| Target mapping sai | Adapter, broker return/routing | Lỗi được phát hiện; message không biến mất âm thầm |
| Broker unavailable | Adapter, registry | Publication chưa hoàn tất được giữ để phục hồi |
| Broker phục hồi | Registry, broker, consumer | Retry/resubmission hoàn tất và backlog giảm |
| Consumer nhận trùng | Inbox, read model | Side effect chỉ áp dụng một lần |
| Schema không tương thích | Serializer, consumer, DLQ | Lỗi được phân loại và có thể điều tra |
| Consumer chậm | Queue depth/lag, metric | Backlog được quan sát và giới hạn theo chính sách |
| Quyền truy cập sai | Broker authentication/ACL | Publish/subscribe bị từ chối rõ ràng |
| Trace và log | Producer, adapter, consumer | Có thể nối một event qua các bước mà không lộ payload nhạy cảm |

Không nhất thiết mọi commit đều chạy toàn bộ ma trận với mọi broker. Có thể chạy unit test nhanh thường xuyên và chạy broker integration/contract test trong pipeline phù hợp. Những kiểm thử transaction, routing và retry cần được giữ trong bộ kiểm thử bảo vệ hợp đồng quan trọng.

## 16. Những điểm cần nhớ

- Kiểm thử externalization phải bao phủ event contract, transaction, adapter, broker routing và consumer.
- Unit test xác nhận logic cục bộ; broker thật hoặc Testcontainers cần thiết để kiểm tra semantics vận chuyển.
- Xác nhận event chỉ được gửi sau commit và không gửi khi transaction rollback.
- Kiểm tra target mapping, serialization, schema compatibility và routing đến đúng destination.
- Event Publication Registry giúp theo dõi publication chưa hoàn tất; test cả lỗi vận chuyển và resubmission.
- Consumer phải idempotent vì broker redelivery hoặc retry có thể giao cùng message nhiều lần.
- Dùng timeout/polling có giới hạn, fixture riêng và transaction boundary thật để tránh test flaky.
- Kiểm thử log, metric, trace và bảo mật để sự cố có thể được điều tra an toàn.

Khi kiểm thử từ hợp đồng event đến broker và consumer, bao gồm cả commit, rollback, lỗi vận chuyển và giao trùng, nhóm phát triển có thể xác nhận externalization hoạt động đúng trong điều kiện bình thường lẫn khi phục hồi. Kết hợp kiểm thử tích hợp với Event Publication Registry, schema contract và consumer idempotency giúp giao tiếp giữa các module Spring Modulith đáng tin cậy hơn.
