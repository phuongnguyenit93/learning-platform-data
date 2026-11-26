# Kiểm thử dead-letter

Dead-letter là cơ chế RabbitMQ chuyển một message không thể tiếp tục xử lý trong queue hiện tại sang một dead-letter exchange (DLX). Exchange này định tuyến message tới một hoặc nhiều queue khác, thường là dead-letter queue (DLQ) để lưu giữ, điều tra hoặc xử lý lại sau này.

Kiểm thử dead-letter xác minh toàn bộ hành vi đó: điều kiện nào làm message bị dead-letter, message được định tuyến tới đâu, metadata nào được giữ hoặc bổ sung, queue nguồn còn message hay không và hệ thống có thể phục hồi message an toàn không. Chỉ kiểm tra rằng consumer ném exception chưa đủ để chứng minh topology DLX hoạt động đúng.

Trong Spring Modulith, application events giúp các module công bố sự kiện nghiệp vụ qua ranh giới rõ ràng. Khi event được externalize qua RabbitMQ, producer adapter gửi message và consumer xử lý message ở phía nhận. Kiểm thử dead-letter thuộc ranh giới broker/consumer: nó xác minh cách RabbitMQ xử lý message bị từ chối, hết hạn hoặc vượt giới hạn queue. Event Publication Registry ở phía producer không thay thế DLX, DLQ hoặc cơ chế quản lý message lỗi ở broker.

## 1. Phân biệt DLX và DLQ

DLX và DLQ là hai thành phần khác nhau:

- **Dead-letter exchange (DLX):** exchange nhận message được dead-letter và định tuyến chúng theo exchange type, routing key và binding.
- **Dead-letter queue (DLQ):** queue nhận message sau khi DLX định tuyến. Queue này lưu message để kiểm tra, cách ly hoặc redrive.

Một queue nguồn có thể cấu hình DLX và dead-letter routing key. Khi một message bị dead-letter, RabbitMQ publish message đó tới DLX. Exchange định tuyến message đến queue được bind phù hợp. DLX không phải là queue và việc cấu hình DLX không tự tạo queue đích.

Ví dụ topology:

~~~mermaid
flowchart LR
    P["Producer"] --> X["orders.exchange"]
    X --> Q["orders.main"]
    Q -->|"reject / nack"| D["orders.dlx"]
    D --> R["orders.dead"]
    R --> O["Operator / inspection"]
~~~

Trong ví dụ, orders.main là queue xử lý chính; orders.dlx là direct exchange; orders.dead là queue lưu message lỗi. Ứng dụng có thể dùng DLQ riêng theo domain, loại event hoặc mức độ nhạy cảm.

Một DLQ có thể nhận message từ nhiều queue nguồn. Khi đó, cần giữ metadata nguồn và routing key ban đầu để người vận hành biết message xuất phát từ đâu. Không nên gom tất cả message lỗi vào một queue chung nếu không thể phân biệt ownership, chính sách retention hoặc cách redrive.

## 2. Những điều kiện làm message bị dead-letter

RabbitMQ AMQP 0-9-1 có một số điều kiện dead-letter phổ biến:

| Điều kiện | Hành vi | Trường hợp kiểm thử |
|---|---|---|
| Consumer reject với requeue=false | Message bị từ chối; được chuyển qua DLX nếu queue có cấu hình | Payload không hợp lệ hoặc lỗi không retry |
| Consumer nack với requeue=false | Một hoặc nhiều delivery bị từ chối; được chuyển qua DLX nếu có | Listener thất bại theo chính sách |
| Message hết TTL trong queue | Message hết hạn có thể bị dead-letter nếu queue cấu hình DLX | Retry queue dùng TTL |
| Queue vượt max length hoặc max length bytes | Message bị loại theo overflow policy; một số policy có thể dead-letter message bị loại | Giới hạn backlog |
| Quorum queue vượt delivery limit | Message bị dead-letter nếu cấu hình DLX phù hợp; nếu không, xử lý theo chính sách queue | Poison message được giao lại quá nhiều lần |

Reject/nack với requeue=true yêu cầu broker giao lại message, không đưa message vào DLQ chỉ vì consumer từ chối. Nếu queue không có DLX, reject/nack với requeue=false có thể khiến message bị loại bỏ. Vì vậy, test cần xác minh cả topology lẫn kết quả, tránh chỉ dựa trên việc listener không ném exception.

Các điều kiện và bảo đảm dead-letter có thể khác theo loại queue, policy và phiên bản RabbitMQ. Đặc biệt, hành vi overflow và dead-lettering của quorum queue cần được cấu hình và kiểm tra theo phiên bản broker đang triển khai.

## 3. Thiết kế topology cho kiểm thử

Một test dead-letter cần có tối thiểu:

1. Queue nguồn để nhận message.
2. DLX có exchange type phù hợp.
3. Routing key được dùng khi dead-letter.
4. DLQ được bind tới DLX.
5. Consumer hoặc thao tác test tạo ra điều kiện dead-letter.
6. Cơ chế đọc DLQ và xác minh kết quả.

Ví dụ direct exchange:

~~~text
Main exchange: orders.exchange
Main queue:    orders.main
Main binding:  routing key orders.created

Dead-letter exchange: orders.dlx
Dead-letter queue:    orders.dead
Dead-letter binding:  routing key orders.dead
~~~

Khi queue orders.main cấu hình dead-letter exchange là orders.dlx và dead-letter routing key là orders.dead, message bị dead-letter sẽ được định tuyến tới orders.dead nếu binding phù hợp.

Không giả định routing key ban đầu luôn được dùng cho DLQ. Nếu cấu hình dead-letter routing key riêng, hãy assert routing key sau khi định tuyến theo cấu hình đó. Nếu không cấu hình khóa định tuyến riêng, broker có thể dùng routing key hiện tại của message theo quy tắc dead-letter.

Trong test, topology nên được khai báo tường minh để dễ đọc và tránh phụ thuộc vào cấu hình của môi trường developer. Với môi trường production, có thể quản lý DLX bằng RabbitMQ policy để thay đổi mà không phải xóa và tạo lại queue. Test cần sử dụng cùng loại cấu hình mà ứng dụng thực sự triển khai.

## 4. Khai báo queue và DLX bằng Spring AMQP

Spring AMQP cho phép khai báo exchange, queue và binding qua bean. Ví dụ:

~~~java
@Configuration
class DeadLetterTopology {

    static final String MAIN_QUEUE = "orders.main";
    static final String DLX = "orders.dlx";
    static final String DLQ = "orders.dead";
    static final String DEAD_ROUTING_KEY = "orders.dead";

    @Bean
    DirectExchange ordersDeadLetterExchange() {
        return new DirectExchange(DLX, true, false);
    }

    @Bean
    Queue ordersMainQueue() {
        return QueueBuilder.durable(MAIN_QUEUE)
            .deadLetterExchange(DLX)
            .deadLetterRoutingKey(DEAD_ROUTING_KEY)
            .build();
    }

    @Bean
    Queue ordersDeadQueue() {
        return QueueBuilder.durable(DLQ).build();
    }

    @Bean
    Binding ordersDeadBinding(
            Queue ordersDeadQueue,
            DirectExchange ordersDeadLetterExchange) {
        return BindingBuilder
            .bind(ordersDeadQueue)
            .to(ordersDeadLetterExchange)
            .with(DEAD_ROUTING_KEY);
    }
}
~~~

Đây là topology minh họa cho test. Ứng dụng thực tế cần bảo đảm queue nguồn được khai báo đúng một lần, exchange và binding tồn tại, và quyền của producer/consumer phù hợp.

Nếu queue đã tồn tại với arguments khác, RabbitMQ có thể từ chối khai báo lại queue do inequivalent arg. Test không nên âm thầm bỏ qua lỗi này. Hãy dùng queue name riêng theo test hoặc xóa topology test sau khi hoàn tất.

Trong production, DLX có thể được cấu hình bằng policy. Khi test, nếu topology được khai báo bằng policy, hãy tạo policy tương đương thay vì chỉ kiểm tra bean khai báo arguments. Điều quan trọng là test tái hiện chính sách đang chạy, bao gồm exchange, routing key và loại queue.

## 5. Kiểm thử consumer reject hoặc nack

Một trong các test quan trọng nhất là xác minh consumer từ chối message không thể xử lý và broker chuyển message sang DLQ.

Với Spring AMQP, listener ở MANUAL ack mode có thể chủ động reject:

~~~java
@Component
class OrdersListener {

    @RabbitListener(
        queues = "orders.main",
        ackMode = "MANUAL"
    )
    void handle(Message message, Channel channel)
            throws IOException {

        long tag = message.getMessageProperties()
            .getDeliveryTag();

        try {
            orderHandler.handle(message);
            channel.basicAck(tag, false);
        } catch (InvalidOrderPayloadException ex) {
            channel.basicReject(tag, false);
        }
    }
}
~~~

Ví dụ này coi payload không hợp lệ là lỗi không thể retry và reject với requeue=false. Với lỗi tạm thời, ứng dụng có thể nack/requeue hoặc chuyển qua retry queue theo chính sách. Không nên dùng một nhánh reject chung cho mọi exception.

Test cần xác minh message được đưa vào DLQ và không còn trong queue nguồn. Nếu listener đang chạy async, hãy chờ điều kiện DLQ nhận message bằng Awaitility hoặc cơ chế đồng bộ tương đương; không dùng sleep cố định.

Cần kiểm tra listener thực sự dùng MANUAL ack mode. Nếu container chạy AUTO, exception và ack/reject được xử lý theo container configuration; gọi basicReject trong listener không phải cách duy nhất hoặc phù hợp cho mọi chế độ.

## 6. Dùng Testcontainers để kiểm thử với RabbitMQ thật

Mock RabbitTemplate có thể kiểm tra rằng ứng dụng gọi phương thức publish, nhưng không chứng minh RabbitMQ áp dụng DLX, TTL, routing hoặc x-death header đúng. Integration test nên dùng broker thật, thường qua Testcontainers.

Ví dụ khung test:

~~~java
@Testcontainers
@SpringBootTest
class DeadLetterIntegrationTests {

    @Container
    static final RabbitMQContainer rabbit =
        new RabbitMQContainer("rabbitmq:3.13-management");

    @DynamicPropertySource
    static void rabbitProperties(
            DynamicPropertyRegistry registry) {
        registry.add("spring.rabbitmq.host", rabbit::getHost);
        registry.add(
            "spring.rabbitmq.port",
            rabbit::getAmqpPort
        );
        registry.add(
            "spring.rabbitmq.username",
            rabbit::getAdminUsername
        );
        registry.add(
            "spring.rabbitmq.password",
            rabbit::getAdminPassword
        );
    }

    @Autowired
    RabbitTemplate rabbitTemplate;

    @Test
    void deadLettersRejectedMessage() {
        // Publish payload không hợp lệ vào queue nguồn.
        // Chờ listener reject.
        // Đọc DLQ và kiểm tra body cùng metadata.
    }
}
~~~

Đây là skeleton để minh họa cách kết nối Spring Boot với container; test thực tế cần khai báo topology và listener bean phù hợp. Phiên bản image RabbitMQ nên khớp với phiên bản broker production. Nếu production dùng quorum queue, plugin hoặc policy đặc biệt, test image cũng cần hỗ trợ cấu hình đó.

Testcontainers giúp mỗi test suite có broker cô lập, giảm phụ thuộc vào RabbitMQ cài trên máy developer. Không dùng queue production hoặc vhost dùng chung cho test. Đặt tên queue/exchange riêng hoặc tạo vhost riêng để test không tiêu thụ message của môi trường khác.

## 7. Xác minh message trong DLQ

Khi DLQ nhận message, đừng chỉ kiểm tra queue có ít nhất một message. Hãy đọc message và xác minh nội dung cùng metadata.

Những điều nên kiểm tra:

- Body giữ đúng event payload hoặc nội dung ban đầu theo contract.
- Message ID hoặc event ID được giữ ổn định.
- Content type và encoding phù hợp.
- Correlation ID và các header nghiệp vụ cần thiết được giữ.
- Routing key và exchange phản ánh đường định tuyến mong đợi.
- x-death có queue nguồn và reason phù hợp.
- Message không bị tiêu thụ hoặc mất khỏi DLQ trước khi test xác minh.

Ví dụ đọc DLQ:

~~~java
Message deadLetter = rabbitTemplate.receive(
    "orders.dead",
    5_000
);

assertThat(deadLetter).isNotNull();
assertThat(deadLetter.getBody())
    .isEqualTo(expectedBody);

assertThat(deadLetter.getMessageProperties().getHeaders())
    .containsKey("x-death");
~~~

Đoạn code minh họa đọc message với timeout theo API Spring AMQP. Khi nhận message bằng phương thức receive auto-ack, message có thể bị loại khỏi DLQ sau khi lấy; điều này phù hợp với queue cô lập trong test nhưng cần lưu ý nếu muốn kiểm tra lại nhiều lần. Có thể dùng basicGet với manual ack hoặc chỉ đọc một lần rồi xác minh toàn bộ thuộc tính trong cùng test.

Nếu message được chuyển qua nhiều DLX hoặc retry queue, routing metadata có thể thay đổi theo từng chặng. Test nên xác minh các trường có ý nghĩa với contract, không khóa vào mọi header nội bộ nếu phiên bản broker có thể bổ sung metadata khác.

## 8. Kiểm tra x-death metadata

RabbitMQ bổ sung header x-death khi message bị dead-letter. Đây là một danh sách các bảng metadata mô tả lịch sử dead-letter, thường bao gồm:

| Trường | Ý nghĩa |
|---|---|
| queue | Queue nơi message bị dead-letter |
| reason | Lý do, ví dụ rejected, expired, maxlen hoặc delivery_limit |
| count | Số lần dead-letter theo queue và reason |
| exchange | Exchange liên quan tới lần dead-letter |
| routing-keys | Các routing key tại thời điểm dead-letter |
| time | Thời điểm dead-letter |
| original-expiration | TTL ban đầu nếu phù hợp |

RabbitMQ có thể nén các lần dead-letter cùng queue và reason thành một entry với count tăng dần. Vì vậy, không nên giả định mỗi lần dead-letter luôn tạo một phần tử mới trong x-death.

Ví dụ kiểm tra metadata theo cách không phụ thuộc thứ tự:

~~~java
@SuppressWarnings("unchecked")
List<Map<String, Object>> deaths =
    (List<Map<String, Object>>) deadLetter
        .getMessageProperties()
        .getHeaders()
        .get("x-death");

assertThat(deaths).isNotEmpty();

assertThat(deaths)
    .anySatisfy(death -> {
        assertThat(death.get("queue"))
            .isEqualTo("orders.main");
        assertThat(death.get("reason"))
            .isEqualTo("rejected");
    });
~~~

Đoạn test cần chuyển kiểu dữ liệu theo representation thực tế mà Rabbit client trả về; các field của AMQP table có thể là kiểu Java khác nhau tùy client và serializer. Hãy assert giá trị sau khi chuẩn hóa nếu cần, thay vì ép kiểu cứng vào một implementation cụ thể.

Không dùng x-death làm event ID hoặc idempotency key. Nó là metadata lịch sử dead-letter, không phải định danh nghiệp vụ ổn định.

## 9. Kiểm thử retry queue dùng TTL và DLX

Một mẫu retry phổ biến dùng retry queue có TTL. Khi consumer gặp lỗi tạm thời, message được dead-letter sang retry exchange/queue. Sau khi TTL hết hạn, retry queue dead-letter message trở lại queue chính.

~~~mermaid
flowchart TD
    A["orders.main"] --> B["Consumer"]
    B -->|Thành công| C["ACK"]
    B -->|Lỗi tạm thời| D["NACK requeue=false"]
    D --> E["orders.retry.dlx"]
    E --> F["orders.retry.30s"]
    F -->|TTL hết hạn| G["orders.retry.return"]
    G --> A
    B -->|Lỗi vĩnh viễn| H["orders.dead"]
~~~

Test retry cần phân biệt queue retry trung gian với DLQ cuối cùng. Message nằm trong retry queue không có nghĩa đã bị cách ly vĩnh viễn. DLQ cuối cùng thường dành cho message hết lượt thử hoặc lỗi không thể phục hồi.

Các trường hợp nên kiểm tra:

- Lỗi tạm thời làm message đi vào retry queue.
- Message ở retry queue trong thời gian TTL đã định.
- Hết TTL, message được route về queue chính.
- Sau số lần thử tối đa, message được chuyển tới parking/dead-letter queue.
- Retry count không bị reset hoặc tăng sai khi message đi qua nhiều queue.
- Message ID, event ID và correlation ID giữ ổn định qua các lần retry.

TTL là thời gian tối đa message chờ trong queue, không phải bộ hẹn giờ chính xác tới mili giây. Message hết hạn có thể được xử lý sau một khoảng trễ tùy tải broker và hoạt động queue. Test nên dùng timeout đủ rộng và xác minh điều kiện cuối, không assert thời điểm chính xác tuyệt đối.

## 10. Kiểm thử dead-letter do message expiration

Message có thể hết hạn theo per-message TTL hoặc queue-level TTL. Khi queue có DLX, message hết hạn có thể được dead-letter thay vì chỉ bị loại bỏ.

Test nên xác minh:

1. Message được publish vào queue có TTL hoặc expiration phù hợp.
2. Message không được consumer nhận trước khi hết hạn, hoặc consumer được tạm dừng có chủ đích.
3. Sau khi hết hạn, message xuất hiện ở DLQ hoặc queue đích đã cấu hình.
4. x-death reason thể hiện expired.
5. Metadata original-expiration có mặt nếu broker cung cấp cho trường hợp đó.

Không dùng consumer đang chạy bình thường rồi giả định message chắc chắn hết hạn trước khi được nhận. Với test expiration, nên để queue không có consumer hoặc kiểm soát consumer start time để loại bỏ race giữa delivery và TTL.

Nếu queue có nhiều message với TTL khác nhau, RabbitMQ có thể xử lý expiration khi message tới đầu queue hoặc theo cách broker quản lý queue. Hãy thiết kế test đơn giản với một message hoặc một queue riêng để kết quả dễ xác định.

## 11. Kiểm thử max length và delivery limit

Queue có thể giới hạn số message hoặc tổng dung lượng. Khi vượt giới hạn, overflow policy quyết định message mới hoặc message cũ bị xử lý thế nào. Nếu dùng dead-letter policy, test cần xác minh chính xác message nào bị chuyển đi.

Với quorum queue, delivery limit có thể giới hạn số lần message được giao lại trước khi dead-letter hoặc loại bỏ theo cấu hình. Đây là cách hữu ích để ngăn poison message bị redeliver vô hạn.

Một test cho max length hoặc delivery limit nên:

- Tạo queue với loại và policy tương đương production.
- Gửi message có ID riêng để phân biệt.
- Kích hoạt overflow hoặc redelivery limit.
- Đọc queue nguồn và DLQ.
- Xác minh message bị dead-letter đúng theo overflow/delivery policy.
- Xác minh message khác không bị chuyển nhầm hoặc mất ngoài dự kiến.

Không suy ra rằng mọi queue type đều có cùng semantics. Classic queue và quorum queue có khác biệt về delivery limit, dead-letter guarantees và một số policy. Hãy chọn broker version và queue type đúng với môi trường triển khai.

## 12. Kiểm thử poison message và phân loại lỗi

Poison message là message luôn làm consumer thất bại, ví dụ payload sai schema, trường bắt buộc không hợp lệ hoặc dữ liệu gây lỗi không thể phục hồi. Nếu consumer requeue ngay mỗi lần, message có thể tạo vòng lặp nóng và chặn tiến trình xử lý.

Một chính sách thường có ba nhóm:

| Nhóm | Ví dụ | Hành vi |
|---|---|---|
| Lỗi tạm thời | Timeout dịch vụ, broker quá tải | Retry có backoff |
| Lỗi không thể phục hồi | JSON malformed, schema không hỗ trợ | Reject không requeue, chuyển DLQ |
| Lỗi cần can thiệp | Dữ liệu mâu thuẫn, nghiệp vụ cần phê duyệt | Cách ly và tạo cảnh báo/ticket |

Test nên chứng minh payload malformed không làm listener retry vô hạn. Sau khi chuyển DLQ, consumer chính phải tiếp tục xử lý message hợp lệ tiếp theo. Điều này giúp phát hiện poison message làm nghẽn queue.

Không nên coi mọi exception là poison message. Timeout có thể là lỗi tạm thời; một kết quả từ chối nghiệp vụ có thể là trạng thái hợp lệ. Listener và retry policy cần phân loại lỗi có chủ đích.

## 13. Kiểm thử redrive từ DLQ

Redrive là thao tác đưa message đã cách ly trở lại luồng xử lý sau khi nguyên nhân lỗi được khắc phục. Có thể redrive thủ công qua công cụ vận hành hoặc tự động bằng một worker chuyên trách.

Test redrive cần xác minh:

- Chỉ message được chọn mới được gửi lại.
- Payload và event ID được giữ nguyên, trừ khi có quy trình migration contract rõ ràng.
- Routing key mới đúng queue đích.
- Header dead-letter history được giữ hoặc chuyển sang audit record theo chính sách.
- Message không bị xử lý trùng nếu lần xử lý trước đã tạo side effect.
- Message lỗi lại được chuyển về DLQ theo chính sách, không tạo vòng lặp redrive vô hạn.

Không redrive toàn bộ DLQ ngay khi một dependency vừa phục hồi. Có thể tạo burst tải lớn hoặc lặp lại lỗi. Hệ thống vận hành nên hỗ trợ giới hạn tốc độ, chọn batch, dry run và audit người thực hiện.

Nếu payload cần sửa trước khi redrive, hãy lưu bản gốc và ghi nhận transformation. Không thay đổi event ID tùy tiện vì consumer có thể dựa vào ID đó để idempotency.

## 14. Cô lập test và quản lý topology

Test dead-letter thường tạo exchange, queue, binding, policy và message tồn đọng. Nếu dùng chung tên với môi trường khác, test có thể đọc nhầm hoặc xóa dữ liệu không thuộc mình.

Các nguyên tắc cô lập:

- Dùng broker container hoặc vhost riêng cho test suite.
- Dùng queue/exchange name có namespace theo suite hoặc test.
- Khai báo topology tường minh trước khi publish.
- Dọn queue và binding sau test nếu broker dùng chung.
- Không xóa queue có thể đang được test khác sử dụng.
- Không chạy test song song trên cùng queue nếu không có routing isolation.
- Đặt timeout và cleanup trong finally hoặc lifecycle hook.

Queue durable có thể tồn tại sau khi test kết thúc nếu broker container được tái sử dụng. Test cần dọn topology hoặc tạo tên duy nhất. Không dựa vào việc container luôn bị hủy sau từng method nếu test framework tái sử dụng container ở cấp class hoặc suite.

## 15. Xác minh không mất message và không xác nhận sai

Một test dead-letter cần xác minh message không biến mất do cấu hình sai. Khi DLX không tồn tại hoặc binding không khớp, message có thể không đến DLQ như mong đợi. Nếu test chỉ kiểm tra queue nguồn đã rỗng, nó có thể kết luận sai rằng dead-letter thành công.

Một số assertion quan trọng:

- Message xuất hiện trong đúng DLQ.
- Message không còn trong queue nguồn sau khi dead-letter hoàn tất.
- Body và định danh vẫn đúng.
- x-death ghi nhận queue và reason đúng.
- Queue khác không nhận nhầm message.
- Message hợp lệ tiếp theo vẫn được consumer xử lý.
- Khi DLQ hoặc DLX không khả dụng, hành vi phù hợp với queue type và dead-letter strategy đang dùng.

Bảo đảm chuyển message tới DLX phụ thuộc cấu hình và loại queue. Với yêu cầu độ bền cao, cần hiểu rõ dead-letter strategy của quorum queue và at-least-once dead-lettering nếu dùng. Test phải chạy trên cấu hình tương đương production để kiểm tra đúng mức bảo đảm.

Không tuyên bố exactly-once chỉ vì test thấy một message trong DLQ. Duplicate có thể xuất hiện khi retry hoặc phục hồi; consumer và redrive flow vẫn cần idempotency.

## 16. Kiểm thử tích hợp Spring AMQP

Một bộ integration test có thể bao gồm:

1. Khởi động RabbitMQ bằng Testcontainers.
2. Khai báo queue nguồn, DLX, DLQ và binding.
3. Khởi động listener với ack mode và retry policy giống production.
4. Publish payload hợp lệ hoặc không hợp lệ.
5. Chờ message vào DLQ hoặc queue retry.
6. Đọc body, headers và x-death.
7. Xác minh queue nguồn, retry queue và DLQ theo trạng thái mong đợi.
8. Dọn topology và message sau test.

Có thể dùng RabbitTemplate để publish message và đọc DLQ trong test. Khi test consumer acknowledgement, nên để listener container thực thi đúng cấu hình thay vì chỉ gọi service method trực tiếp. Nếu cần kiểm tra basic.reject/basic.nack ở mức giao thức, có thể dùng Channel trực tiếp trong một test tập trung.

Không dùng mock cho phần cần chứng minh broker routing. Mock có thể xác nhận code gọi reject hoặc publish, nhưng chỉ broker thật mới xác nhận DLX, binding, TTL, x-death và queue semantics.

## 17. Ma trận test dead-letter tối thiểu

Một bộ test nên bao phủ các điều kiện quan trọng của topology:

| Scenario | Given | When | Then |
|---|---|---|---|
| Reject vĩnh viễn | Queue có DLX và DLQ | Reject requeue=false | Message vào DLQ |
| Nack không requeue | Queue có DLX | Nack requeue=false | Message vào DLQ |
| Requeue | Queue có DLX | Reject requeue=true | Message được giao lại, chưa vào DLQ |
| Không có DLX | Queue không cấu hình DLX | Reject requeue=false | Message bị loại theo semantics broker |
| TTL retry | Retry queue có TTL và DLX | Message hết hạn | Message quay lại queue chính |
| TTL cuối cùng | Queue TTL có DLX terminal | Message hết hạn | Message vào DLQ cuối |
| Poison message | Payload sai schema | Consumer từ chối | Không retry vô hạn |
| Max length | Queue có giới hạn | Vượt giới hạn | Message bị xử lý theo overflow policy |
| Delivery limit | Quorum queue có giới hạn | Giao lại quá số lần | Dead-letter theo policy |
| Redrive | Message đang ở DLQ | Gửi lại có kiểm soát | Message về đúng queue và xử lý idempotent |

Không phải ứng dụng nào cũng dùng tất cả điều kiện. Chọn test theo topology, queue type và retry policy đang triển khai, nhưng phải có ít nhất một test chứng minh reject/nack không requeue thực sự đi tới DLQ.

## 18. Quan sát dead-letter trong vận hành

Dead-letter queue là nơi cách ly message, không nên trở thành nơi lưu lỗi vô thời hạn mà không có người chịu trách nhiệm.

Nên theo dõi:

- Số message Ready và Unacknowledged trong DLQ.
- Tuổi message lâu nhất trong DLQ.
- Tốc độ message mới vào DLQ.
- Số message theo queue nguồn và reason.
- Số lần redrive và tỷ lệ redrive thành công.
- Số message retry vượt giới hạn.
- Kích thước payload và dung lượng DLQ.

Log nên chứa message ID, event ID, source queue, dead-letter reason, routing key, x-death count, correlation ID và thời điểm. Tránh log toàn bộ payload nếu có dữ liệu cá nhân hoặc bí mật.

Cảnh báo khi DLQ tăng đột biến, message tồn quá thời hạn vận hành hoặc redrive thất bại liên tục. Cần có runbook xác định ai điều tra, cách phân loại lỗi, cách sửa payload nếu được phép và quy trình redrive có audit.

## 19. Lỗi thường gặp khi kiểm thử dead-letter

**Nhầm DLX với DLQ.** Exchange định tuyến message, queue lưu message. Hãy kiểm tra cả hai thành phần và binding.

**Chỉ kiểm tra listener ném exception.** Điều đó không chứng minh broker đã dead-letter. Hãy đọc message từ DLQ.

**Reject với requeue=true rồi chờ DLQ.** Message được yêu cầu giao lại. Hãy dùng requeue=false cho trường hợp cần dead-letter.

**Queue không có DLX hoặc binding sai.** Message có thể bị loại mà không đến DLQ. Hãy xác minh topology trước khi kiểm tra kết quả.

**Coi retry queue là DLQ cuối.** Retry queue là một chặng chờ; DLQ thường là nơi cách ly cuối cùng. Hãy phân biệt hai mục đích.

**Dùng sleep để chờ TTL.** Test dễ flaky. Hãy chờ điều kiện với timeout đủ rộng và kiểm tra trạng thái cuối.

**Assert cứng cấu trúc toàn bộ x-death.** Broker có thể nén entry hoặc thay đổi representation. Hãy kiểm tra queue, reason và count có ý nghĩa.

**Dùng RabbitMQ mock cho routing test.** Mock không mô phỏng DLX, TTL hoặc broker headers. Hãy dùng RabbitMQ thật trong integration test.

**Không cô lập queue giữa các test.** Message cũ hoặc test song song có thể làm sai kết quả. Hãy dùng container/vhost/queue riêng và cleanup rõ.

**Redrive mà không có idempotency.** Message có thể tạo side effect trùng. Hãy giữ event ID và kiểm tra khóa chống xử lý trùng ở consumer.

## Kết luận

Kiểm thử dead-letter phải xác minh toàn bộ đường đi của message từ queue nguồn qua DLX tới DLQ, bao gồm điều kiện dead-letter, routing key, body, headers và x-death metadata. Với retry bằng TTL, cần kiểm tra riêng queue trung gian và DLQ cuối cùng; với poison message, cần chứng minh message không tạo vòng lặp giao lại vô hạn.

Trong Spring Modulith, producer publication, broker dead-letter và consumer business state là các ranh giới riêng. Dùng RabbitMQ thật qua Testcontainers, cấu hình topology tương đương production, chờ theo điều kiện và xác minh idempotency giúp test phản ánh đúng hành vi broker. DLQ khi đó trở thành cơ chế cách ly có thể quan sát, điều tra và phục hồi thay vì nơi message biến mất khỏi luồng xử lý.

