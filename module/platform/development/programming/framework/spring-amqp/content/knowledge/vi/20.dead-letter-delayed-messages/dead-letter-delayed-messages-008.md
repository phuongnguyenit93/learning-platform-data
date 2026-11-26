# Phân biệt republish từ ứng dụng với dead-letter do broker thực hiện

Trong hệ thống xử lý bất đồng bộ bằng **RabbitMQ và Spring AMQP**, một thông điệp không xử lý được thường cần chuyển sang nơi khác để kiểm tra, xử lý lại hoặc lưu bằng chứng lỗi. Có hai cách dễ bị nhầm lẫn:

- **Application republish:** ứng dụng chủ động gửi một thông điệp bằng `RabbitTemplate` (hoặc thông qua `RepublishMessageRecoverer`) đến exchange đích, rồi kết thúc lần tiêu thụ thông điệp gốc.
- **Broker dead-letter:** ứng dụng hoặc cơ chế của RabbitMQ khiến một thông điệp trở thành *dead letter*; RabbitMQ tự chuyển nó từ queue nguồn qua **dead-letter exchange (DLX)** đến queue đích đã định tuyến.

Cả hai đều có thể đưa thông điệp lỗi đến một queue lưu trữ, nhưng khác nhau về **ai quyết định gửi, điều kiện kích hoạt, ACK/NACK, metadata, retry và mức độ đảm bảo giao nhận**. Phân biệt đúng hai cơ chế là nền tảng để thiết kế retry có giới hạn, hàng đợi lỗi và quy trình xử lý lại an toàn.

## 1. Sự khác nhau cốt lõi

Giả sử dịch vụ nhận sự kiện tạo đơn hàng từ `orders.work` và cần đưa các đơn không xử lý được vào nơi kiểm tra.

### Application republish

```text
orders.work --giao message--> @RabbitListener
                                  |
                                  | xử lý lỗi / hết số lần retry
                                  v
                      RabbitTemplate.publish(...)
                                  |
                                  v
                      orders.errors (exchange)
                                  |
                                  v
                        orders.parking (queue)

Consumer hoàn tất/ACK delivery gốc sau khi republish thành công.
```

Ứng dụng quyết định **có gửi tiếp hay không**, gửi đi đâu và đóng gói nội dung, headers như thế nào. Đích được chọn trong mã ứng dụng hoặc cấu hình ứng dụng. Phát sinh một thao tác publish mới từ phía client; application republish **không tự động sinh header `x-death`**.

### Broker dead-letter

```text
orders.work (có cấu hình DLX)
          |
          | basic.reject / basic.nack với requeue=false
          | hoặc TTL hết hạn, vượt giới hạn queue, ...
          v
  RabbitMQ chuyển message qua orders.dlx
          |
          v
      orders.dead

Không có RabbitTemplate.publish(...) từ consumer cho bước chuyển này.
```

Consumer có thể thông báo với broker rằng delivery **bị từ chối và không requeue**. RabbitMQ xác định DLX của **queue nguồn**, publish lại nội bộ và cập nhật thông tin dead-letter như `x-death`. Những lý do dead-letter khác, chẳng hạn hết TTL, có thể xảy ra ngay cả khi consumer không hoạt động.

> **Điểm cần nhớ:** Dead-letter về mặt nội bộ cũng có bước publish đến exchange, nhưng thao tác đó do **broker** thực hiện theo chính sách của queue. Từ “republish” trong bài này chỉ thao tác **ứng dụng chủ động publish** bằng API gửi message.

## 2. Bảng đối chiếu

| Tiêu chí | Ứng dụng republish | Broker dead-letter |
|---|---|---|
| Ai chủ động gửi? | Mã ứng dụng: `RabbitTemplate`, recoverer, hoặc service | RabbitMQ, dựa trên kết quả xử lý delivery hay trạng thái queue |
| Điều kiện kích hoạt | Quy tắc nghiệp vụ, exception, retry đã hết, nút xử lý thủ công... | Reject/NACK với `requeue=false`, message hết TTL, queue vượt độ dài cho phép, quorum queue vượt `delivery-limit` |
| Exchange đích | Ứng dụng chỉ định khi publish | `x-dead-letter-exchange` hoặc policy DLX của queue nguồn |
| Routing key đích | Ứng dụng chỉ định | Dùng `x-dead-letter-routing-key` nếu có; nếu không, RabbitMQ dùng routing key ban đầu theo quy tắc dead-letter |
| Delivery gốc | Ứng dụng cần kết thúc bằng ACK phù hợp; với listener `AUTO`, trả về thành công thường dẫn đến ACK | Reject/NACK `requeue=false` là thao tác kết thúc delivery; broker xử lý dead-letter |
| Dấu vết mặc định | Có thể thêm thông tin exception, exchange gốc, routing key gốc; tùy implementation | Broker thêm/cập nhật `x-death` và các header dead-letter liên quan |
| Chuyển đổi payload | Dễ tạo payload mới, chuẩn hóa thông tin lỗi, ẩn dữ liệu nhạy cảm | Giữ nguyên body; chủ yếu cập nhật metadata khi dead-letter |
| Điều khiển retry | Retry trong listener, retry interceptor, hoặc ứng dụng publish sang queue retry | DLX kết hợp TTL/queue retry; cần giới hạn số vòng và tránh vòng lặp |
| Rủi ro chính | Publish lỗi hoặc chưa được xác nhận nhưng đã ACK; ACK lỗi sau publish có thể tạo bản sao | DLX/binding lỗi hoặc đích không nhận; dead-letter mặc định không đồng nghĩa giao nhận chắc chắn |
| Phù hợp | Cần quyết định theo nghiệp vụ hoặc bổ sung thông tin lỗi chuyên biệt | Cần cơ chế thống nhất ở cấp queue cho các trường hợp bị từ chối, hết hạn, quá giới hạn |

**ACK, NACK, reject và republish là những hành động khác nhau.** Gửi một message mới không tự ACK delivery cũ. Ngược lại, ACK delivery gốc không tự tạo message mới ở queue lỗi.

## 3. Broker dead-letter: cấu hình và luồng hoạt động

### 3.1. Những lý do RabbitMQ dead-letter

Một message trong queue có thể trở thành dead letter khi:

1. Consumer gửi `basic.reject(deliveryTag, false)` hoặc `basic.nack(deliveryTag, false, false)`. Tham số `false` cuối nghĩa là **không requeue**.
2. Message hết thời gian sống (TTL) trong queue.
3. Queue vượt giới hạn độ dài và message bị loại theo cấu hình giới hạn.
4. Đối với **quorum queue**, message vượt giới hạn số lần giao lại (`delivery-limit`).

Lưu ý: `basic.nack(deliveryTag, false, true)` yêu cầu **requeue**, nên không phải một lệnh chuyển trực tiếp sang DLX. Gọi `basicAck` khi xử lý thất bại cũng không kích hoạt DLX.

### 3.2. Định nghĩa topology Spring AMQP

Ví dụ sau sử dụng hai direct exchange và hai queue. `orders.work` được khai báo với DLX. Các binding xác định message mang routing key `orders.created` đi vào queue làm việc, còn message dead-letter với routing key `orders.failed` đi vào queue lỗi.

```java
@Configuration
public class OrderDlxTopology {
    @Bean
    Declarables orderTopology() {
        DirectExchange main = new DirectExchange("orders.main");
        DirectExchange dlx = new DirectExchange("orders.dlx");

        Queue work = QueueBuilder.durable("orders.work")
                .deadLetterExchange("orders.dlx")
                .deadLetterRoutingKey("orders.failed")
                .build();
        Queue dead = QueueBuilder.durable("orders.dead").build();

        return new Declarables(
                main, dlx, work, dead,
                BindingBuilder.bind(work).to(main).with("orders.created"),
                BindingBuilder.bind(dead).to(dlx).with("orders.failed")
        );
    }
}
```

Các class được sử dụng thuộc Spring AMQP, tiêu biểu như `Declarables`, `QueueBuilder`, `DirectExchange` và `BindingBuilder`. Cần bật khai báo RabbitMQ của ứng dụng và có quyền tạo exchange, queue, binding tương ứng.

Đây là ví dụ minh họa bằng **queue arguments**. Trong môi trường vận hành, có thể cấu hình DLX bằng **RabbitMQ policy** để thay đổi quy tắc mà không phải khai báo lại queue hoặc triển khai lại ứng dụng. Nếu một queue đã tồn tại với arguments không tương thích, việc khai báo lại có thể bị broker từ chối; cần quản lý thay đổi topology có kế hoạch.

### 3.3. Consumer báo reject để broker dead-letter

Với listener mặc định sử dụng chế độ xác nhận `AUTO`, ứng dụng có thể ném `AmqpRejectAndDontRequeueException` cho lỗi không nên xử lý lại:

```java
@Component
public class OrderConsumer {
    private final OrderService orderService;

    public OrderConsumer(OrderService orderService) {
        this.orderService = orderService;
    }

    @RabbitListener(queues = "orders.work")
    public void receive(Message message) {
        try {
            orderService.process(message.getBody());
        } catch (InvalidOrderException ex) {
            throw new AmqpRejectAndDontRequeueException(
                    "Đơn hàng không hợp lệ", ex);
        }
    }
}
```

`OrderService` và `InvalidOrderException` là các thành phần nghiệp vụ giả định. Khi listener ném exception trên, container từ chối delivery với `requeue=false`; RabbitMQ chuyển message từ `orders.work` sang `orders.dlx`, sau đó đi vào `orders.dead` qua binding đã khai báo. Ví dụ không gọi `RabbitTemplate.convertAndSend`.

Nếu ứng dụng chọn chế độ `ackMode = MANUAL`, thao tác tương ứng là:

```java
// deliveryTag lấy từ message.getMessageProperties().getDeliveryTag()
channel.basicReject(deliveryTag, false); // không requeue -> có thể dead-letter
```

**Chỉ reject không đủ:** Queue nguồn phải có DLX phù hợp, exchange đích phải tồn tại và có đường định tuyến tới queue đích. Nếu không có DLX, message bị reject không requeue sẽ bị loại khỏi queue nguồn mà không xuất hiện ở queue lỗi.

### 3.4. Metadata broker bổ sung

Với message đi qua DLX, RabbitMQ quản lý header `x-death`. Đây là lịch sử dead-letter theo các thông tin như queue, lý do (`rejected`, `expired`, `maxlen`, `delivery_limit`), số lần, exchange và routing key liên quan. Broker có thể gộp các sự kiện giống nhau thành bộ đếm thay vì thêm một mục mới mỗi lần.

Ví dụ cấu trúc khái niệm:

```yaml
x-death:
  - queue: orders.work
    reason: rejected
    count: 1
    exchange: orders.main
x-first-death-queue: orders.work
x-first-death-reason: rejected
```

Cấu trúc trên chỉ để diễn giải; kiểu dữ liệu AMQP, tập header bổ sung và cách trình bày thực tế có thể khác nhau giữa phiên bản broker/client. `x-death` phản ánh các **lần dead-letter tại broker**, không phải tổng số lần thử xử lý nghiệp vụ trong ứng dụng.

## 4. Application republish: gửi lại chủ động từ Spring AMQP

Application republish thường được dùng khi ứng dụng cần đưa một bản sao message lỗi tới exchange chuyên dụng sau khi thử xử lý một số lần. Nó cũng phù hợp khi muốn tạo một *failure event* mới mang dữ liệu nghiệp vụ, nguyên nhân lỗi hoặc thông tin truy vết do ứng dụng quyết định.

### 4.1. Dùng `RepublishMessageRecoverer` sau retry

Spring AMQP có `RepublishMessageRecoverer`. Recoverer nhận message gốc và exception khi retry đã hết, rồi dùng `RabbitTemplate` publish tới exchange/routing key đã chỉ định.

```java
@Configuration
public class AppRepublishConfig {
    @Bean
    Declarables errorTopology() {
        DirectExchange errors = new DirectExchange("orders.errors");
        Queue parking = QueueBuilder.durable("orders.parking").build();

        return new Declarables(
                errors, parking,
                BindingBuilder.bind(parking)
                        .to(errors).with("orders.failed")
        );
    }

    @Bean
    RetryOperationsInterceptor republishRecovery(RabbitTemplate template) {
        return RetryInterceptorBuilder.stateless()
                .maxAttempts(3)
                .backOffOptions(500L, 2.0, 2000L)
                .recoverer(new RepublishMessageRecoverer(
                        template, "orders.errors", "orders.failed"))
                .build();
    }

    @Bean
    SimpleRabbitListenerContainerFactory republishFactory(
            ConnectionFactory connectionFactory,
            RetryOperationsInterceptor republishRecovery) {
        SimpleRabbitListenerContainerFactory factory =
                new SimpleRabbitListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setAdviceChain(republishRecovery);
        return factory;
    }
}
```

Listener sử dụng factory này:

```java
@RabbitListener(
        queues = "orders.work",
        containerFactory = "republishFactory")
public void receiveOrder(byte[] body) {
    orderService.process(body); // Có thể ném exception
}
```

Luồng trong cấu hình này:

1. Container nhận delivery từ `orders.work` và gọi listener.
2. Listener lỗi, retry interceptor thử lại tối đa ba lần theo cấu hình ví dụ. Các lần gọi lại tại đây là **retry phía ứng dụng**, không tự tạo `x-death`.
3. Nếu hết retry, `RepublishMessageRecoverer` publish message đến exchange `orders.errors` với routing key `orders.failed`.
4. Nếu recoverer kết thúc bình thường, lần xử lý được coi là đã phục hồi; trong `AUTO` ack mode, container hoàn tất/ACK delivery gốc.
5. Broker định tuyến message vừa publish tới `orders.parking` bằng binding của exchange lỗi.

`RepublishMessageRecoverer` thường bổ sung header cung cấp thông tin exception và nguồn gốc, chẳng hạn `x-exception-message`, `x-exception-stacktrace`, `x-original-exchange` và `x-original-routingKey`. Đây là metadata do **ứng dụng/recoverer** thêm; nó không có nghĩa message đã đi qua DLX.

> Hai đoạn cấu hình broker DLX và application republish là **hai phương án minh họa để đối chiếu**. Khi áp dụng vào cùng `orders.work`, cần chọn rõ đường xử lý lỗi. Một recoverer publish thành công và ACK delivery gốc sẽ không kích hoạt DLX cho delivery đó; DLX vẫn có thể được sử dụng cho các lần reject khác hoặc khi TTL hết hạn.

### 4.2. Republish thủ công bằng `RabbitTemplate`

Nếu nghiệp vụ phải biến đổi nội dung message, có thể chủ động gọi:

```java
rabbitTemplate.convertAndSend(
        "orders.errors",
        "orders.failed",
        failedOrderEvent,
        outbound -> {
            outbound.getMessageProperties()
                    .setHeader("failure-code", "ORDER_VALIDATION");
            return outbound;
        }
);
```

`failedOrderEvent` là dữ liệu lỗi do ứng dụng tạo. Với listener ở chế độ `MANUAL`, sau khi xác nhận publish đến đích theo yêu cầu độ tin cậy của hệ thống, ứng dụng mới gửi `basicAck` cho delivery nguồn. Với `AUTO`, việc listener kết thúc thành công thường dẫn đến ACK. Nếu gọi `convertAndSend` rồi ACK ngay mà không kiểm tra publisher confirm và routing result, có nguy cơ mất message khi publish thất bại.

## 5. Độ tin cậy: publish, ACK và dead-letter không phải một giao dịch mặc định

### 5.1. Application republish có khoảng hở giữa hai thao tác

Phương án thường gặp là **publish message lỗi → ACK message nguồn**. Hai thao tác này không tự động trở thành một giao dịch nguyên tử:

| Thời điểm lỗi | Hệ quả có thể xảy ra | Cách giảm rủi ro |
|---|---|---|
| Publish thất bại nhưng delivery gốc đã ACK | Message lỗi có thể mất | Chỉ ACK sau khi xác nhận publish phù hợp |
| Publish đến broker thành công nhưng ACK nguồn thất bại | Message nguồn có thể được giao lại, gây tạo thêm bản sao | Consumer và xử lý ở đích phải **idempotent** theo message/business ID |
| Exchange nhận publish nhưng không có binding phù hợp | Publish confirm có thể là ACK ở cấp broker nhưng message vẫn không đến queue đích | Bật và xử lý **publisher returns** với thuộc tính `mandatory` khi cần phát hiện unroutable |
| Recoverer/consumer bị crash giữa hai bước | Trạng thái hai bản message có thể không đồng bộ | Retry an toàn, deduplicate; dùng outbox khi cần liên kết với trạng thái DB |

Ví dụ cấu hình Spring Boot để hỗ trợ kiểm tra việc gửi:

```yaml
spring:
  rabbitmq:
    publisher-confirm-type: correlated
    publisher-returns: true
    template:
      mandatory: true
```

Cấu hình này **chỉ mở khả năng nhận confirm/return**. Ứng dụng hoặc recoverer được chọn vẫn phải thực sự đợi/kiểm tra kết quả trước khi coi thao tác republish thành công. Publisher confirm xác nhận broker xử lý publish theo cơ chế confirm, không thay thế kiểm tra routing hay cam kết hệ thống xử lý xong nghiệp vụ ở consumer đích.

Khi nghiệp vụ vừa cập nhật database vừa phát message, một **transactional outbox** có thể giúp bảo đảm sự kiện gửi đi phù hợp với trạng thái đã commit; điều này cũng cần consumer chống xử lý trùng.

### 5.2. Broker dead-letter cũng có giới hạn

DLX giảm trách nhiệm publish trong consumer, nhưng **không bảo đảm tuyệt đối rằng mọi dead letter đều nằm trong queue đích**. Exchange đích không tồn tại, binding sai, queue đích không sẵn sàng hoặc broker không thể chuyển message đều là các trường hợp phải xem xét.

Với cấu hình dead-letter thông thường, RabbitMQ có thể chuyển theo ngữ nghĩa **at-most-once** và có nguy cơ mất message nếu đích không nhận được. Một số cấu hình **quorum queue** hỗ trợ cơ chế dead-letter **at-least-once** với các điều kiện và đánh đổi tài nguyên riêng; không nên mặc định mọi queue đều có bảo đảm này.

Do đó, cả hai phương án đều cần quan sát queue lỗi, kiểm tra topology, phát hiện message bị trả về/không định tuyến và thiết kế chống trùng ở phía xử lý cuối.

## 6. Liên hệ với retry và delayed messages

Một message có thể được thử lại mà **không** cần dead-letter: retry interceptor gọi lại handler, hoặc consumer NACK với `requeue=true` để broker giao lại. Tuy nhiên, requeue liên tục mà không có giới hạn/backoff có thể tạo vòng lặp nóng, gây tải CPU và nghẽn queue.

RabbitMQ còn có mô hình **retry queue dùng TTL + DLX**:

```text
orders.work --reject/requeue=false--> orders.retry.exchange
                                         |
                                         v
                                  orders.retry.10s
                                    (TTL 10 giây)
                                         |
                                   hết TTL, DLX
                                         v
                                    orders.main
                                         |
                                         v
                                    orders.work
```

Trong mô hình này, **cả hai lần chuyển qua DLX đều do broker thực hiện**. TTL của queue retry tạo khoảng trì hoãn; message quay về queue làm việc sau khi hết hạn. Cần xác định số lần retry tối đa và đường đi cuối cùng tới parking/dead queue. Nếu cấu hình routing quay vòng không hợp lý, có thể gây retry vô hạn; RabbitMQ cũng có cơ chế phát hiện một số vòng dead-letter để tránh luân chuyển không có lần reject phù hợp.

Nếu ứng dụng muốn chọn thời gian retry tùy loại lỗi hoặc kiểm soát payload, nó có thể **republish sang retry exchange/queue**. Khi đó publish là thao tác của ứng dụng, còn lần hết TTL từ queue retry về queue làm việc vẫn là dead-letter của broker. Một luồng xử lý hoàn toàn có thể **kết hợp cả hai**, miễn là quy ước retry count và ACK được xác định rõ.

Không dùng riêng `x-death.count` làm số lần thử nghiệp vụ trong mọi trường hợp: bộ đếm này theo **dead-letter event** và lý do, không bao gồm các lần retry nội bộ trong Java. Nếu ứng dụng tự republish message đã từng dead-letter, hãy cẩn thận với header lịch sử được giữ lại; dùng bộ đếm retry nghiệp vụ riêng nếu cần.

## 7. Cách chọn cơ chế cho từng tình huống

| Tình huống | Phương án ưu tiên | Vì sao |
|---|---|---|
| Message hết TTL khi đang chờ trong queue | Broker dead-letter | Consumer không cần chạy để phát hiện hết hạn |
| Consumer xác định payload không hợp lệ và chỉ cần đưa nguyên bản sang queue lỗi | Reject/NACK không requeue + DLX | Quy tắc đơn giản, áp dụng thống nhất ở cấp queue |
| Muốn bổ sung stack trace, mã lỗi nghiệp vụ hoặc dựng một failure event riêng | Application republish | Ứng dụng có ngữ cảnh nghiệp vụ để xây nội dung và headers |
| Retry tạm thời ngay trong JVM với backoff ngắn rồi đưa vào parking queue | Retry interceptor + `RepublishMessageRecoverer` | Điều khiển số lần thử và fallback ở Spring AMQP |
| Trì hoãn bằng queue TTL rồi trả message về queue ban đầu | TTL + DLX | Broker đảm nhiệm việc hết hạn và định tuyến lại |
| Cần kiểm soát chặt chẽ việc publish lỗi và ACK nguồn | Cân nhắc cả hai, theo cam kết của queue và nghiệp vụ | Phải đánh giá publisher confirms, returns, quorum dead-lettering, idempotency và khả năng phục hồi |

### Những nhầm lẫn thường gặp

- **“NACK là chắc chắn vào DLQ.”** Sai: `requeue=true` đưa message quay lại luồng tiêu thụ; `requeue=false` chỉ dẫn đến DLQ khi DLX và binding được cấu hình, hoạt động đúng.
- **“`RabbitTemplate.convertAndSend` tạo `x-death`.”** Sai: header dead-letter do broker quản lý khi có dead-letter event; một ứng dụng có thể mang theo header lịch sử nếu sao chép message.
- **“`RepublishMessageRecoverer` trả về nghĩa là queue lỗi đã xử lý xong.”** Sai: recoverer chỉ thực hiện bước publish; consumer ở queue lỗi là một quá trình khác.
- **“Publisher confirm ACK là message đã tới queue mong muốn.”** Chưa đủ: cần quan tâm routing và publisher returns nếu message có thể không có đích.
- **“Có DLX nghĩa là không mất message.”** Sai: cần kiểm tra giới hạn của kiểu queue và chính sách dead-letter cụ thể.
- **“Đã retry ba lần ở Spring thì `x-death.count` phải bằng ba.”** Sai: retry trong listener không nhất thiết đưa message qua DLX.

## 8. Bài thực hành kiểm chứng

Thực hiện hai kịch bản tách biệt trên môi trường RabbitMQ thử nghiệm; mỗi kịch bản dùng một message có ID riêng để dễ theo dõi.

1. **Kiểm chứng broker DLX:** Khai báo `orders.main`, `orders.work`, `orders.dlx`, `orders.dead` và các binding như mục 3. Publish một message không hợp lệ vào `orders.main` với routing key `orders.created`. Cho listener ném `AmqpRejectAndDontRequeueException`. Xác nhận message rời queue nguồn và xuất hiện tại `orders.dead`; kiểm tra `x-death` có lý do `rejected`.
2. **Kiểm chứng app republish:** Cấu hình `orders.errors`, `orders.parking` và factory retry ở mục 4; cho listener ném lỗi để hết ba lần thử. Xác nhận message đến `orders.parking` với thông tin exception do recoverer thêm; delivery gốc được hoàn tất. Không kỳ vọng một `x-death` mới chỉ vì republish.
3. **Thay đổi một yếu tố:** Ở kịch bản broker, thử `requeue=true` và so sánh; ở kịch bản app, thử routing key không có binding với publisher returns được bật. Quan sát message nằm ở đâu, consumer có được gọi lại không và ứng dụng nhận tín hiệu lỗi publish thế nào.
4. **Kiểm tra khả năng xử lý trùng:** Dùng cùng một business ID khi mô phỏng publish thành công nhưng ACK nguồn không hoàn tất; xác nhận consumer đích bỏ qua sự kiện đã xử lý.

Khi quan sát, phân biệt rõ **messages ready**, **messages unacknowledged**, số lần giao lại (`redelivered`), message ở queue lỗi, `x-death` và log/publisher confirm của ứng dụng. Những số liệu này chỉ mô tả các giai đoạn khác nhau, không thay thế lẫn nhau.

## 9. Tổng kết kiến thức

**Application republish** là quyết định gửi message mới của mã Spring AMQP, thuận lợi khi cần retry ở ứng dụng, chọn đích và tạo ngữ cảnh lỗi. **Broker dead-letter** là quyết định chuyển message của RabbitMQ theo trạng thái delivery/queue và cấu hình DLX, thuận lợi cho việc xử lý reject, TTL và giới hạn queue. Với cả hai cơ chế, cần xác nhận đường định tuyến, xác định trách nhiệm ACK/NACK, giới hạn retry, theo dõi message lỗi và thiết kế xử lý trùng để hệ thống bất đồng bộ hoạt động đáng tin cậy.
