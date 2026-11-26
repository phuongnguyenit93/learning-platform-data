# Kiểm thử confirm, mandatory return và exchange không tồn tại

Khi ứng dụng dùng **Spring AMQP** gọi `RabbitTemplate.convertAndSend(...)`, việc phương thức trả về bình thường **không đồng nghĩa** message đã đến queue mong muốn. Đường publish qua RabbitMQ (AMQP 0-9-1) có ít nhất ba kết quả khác nhau cần kiểm thử riêng:

1. Broker **nhận và định tuyến được** message tới queue: publisher thường nhận **confirm ACK**.
2. Broker **nhận publish vào exchange tồn tại nhưng không tìm được queue phù hợp**: nếu bật `mandatory`, broker trả **`basic.return` / `NO_ROUTE`**, sau đó vẫn có thể gửi **confirm ACK**.
3. Publish tới **exchange không tồn tại**: broker gửi **channel exception `404 NOT_FOUND`** và **đóng channel**; đây **không phải** `basic.return`.

Bài thuộc chương **Kiểm thử** của module **SPRING_AMQP**. Ta sẽ kiểm tra ba trường hợp bằng **RabbitMQ thật**, `RabbitTemplate`, `CorrelationData`, publisher confirms/returns, topology exchange–queue–binding, quan sát lỗi channel, và cách viết assertions bất đồng bộ để không tạo test chập chờn (*flaky test*). Những kiến thức này liên quan trực tiếp tới xử lý retry, dead-letter, độ tin cậy đầu cuối và quan sát hệ thống.

> Phạm vi ví dụ: Java 17+, Spring Boot 3.x, Spring AMQP 3.x, JUnit Jupiter, AssertJ và Testcontainers 1.x. Khi dùng Spring Boot 4/Spring AMQP 4 hoặc Testcontainers 2, cần đối chiếu thay đổi package và dependency của bản đang dùng. Các ví dụ là tài liệu học tập; không chạy build/test trong bước viết bài này.

## 1. Ba tín hiệu thường bị nhầm lẫn

### 1.1. Publisher confirm là xác nhận của broker đối với publisher

**Publisher confirms** là cơ chế broker trả lại kết quả đối với một lần publish trên channel đã bật confirm mode. Trong Spring AMQP, một `CorrelationData` có ID riêng gắn publish với `CompletableFuture<CorrelationData.Confirm>`:

```java
CorrelationData correlation = new CorrelationData("evt-100");

rabbitTemplate.convertAndSend(
        "orders.events", "orders.created", "payload", correlation);

CorrelationData.Confirm confirm =
        correlation.getFuture().get(10, TimeUnit.SECONDS);

boolean brokerAck = confirm.isAck();
String failureReason = confirm.getReason();
```

- `ack=true`: broker xác nhận publish theo ranh giới của publisher confirms.
- `ack=false`: NACK hoặc thất bại được framework phản ánh dưới dạng negative confirm; reason **có thể rỗng** với broker-generated NACK.
- `get(10, SECONDS)` có thể **timeout**: kết quả **chưa biết**, không phải bằng chứng publish đã thất bại.
- Confirm ACK **không xác nhận** consumer đã nhận, ACK hay commit database.

Với durable queue và persistent message, confirm có ý nghĩa liên quan tới việc các queue liên quan đã chấp nhận message theo semantics lưu trữ của RabbitMQ. Nhưng đó vẫn là **phía broker**, không phải kết quả nghiệp vụ cuối cùng.

### 1.2. Mandatory return cho biết message không được định tuyến

Khi publish vào exchange **tồn tại**, broker có thể không tìm thấy queue nào khớp routing key. Nếu publisher đặt cờ `mandatory=true`, message sẽ được trả về theo `basic.return`.

```text
RabbitTemplate ---- basic.publish(mandatory=true) ----> RabbitMQ
                        exchange tồn tại
                                 |
                                 v
                          không có binding khớp
                                 |
                       basic.return NO_ROUTE
                                 |
                        publisher confirm ACK
                                 |
                                 v
                      Cần xem cả hai kết quả!
```

Mã trả về điển hình của RabbitMQ AMQP 0-9-1 cho unroutable publish là **312 `NO_ROUTE`**. Spring AMQP cung cấp `ReturnedMessage`/`CorrelationData.getReturn()` với `replyCode`, `replyText`, `exchange`, `routingKey` và message gốc.

**Trường hợp quan trọng:** `confirm.isAck() == true` **và** `correlation.getReturn() != null` có thể đồng thời đúng. Nếu ứng dụng chỉ test ACK, message không đến queue nào vẫn bị đánh dấu là “gửi thành công”.

### 1.3. Exchange không tồn tại là protocol/channel error

Nếu publisher gửi tới `exchange="orders.unknown"` nhưng exchange này **không được khai báo**, RabbitMQ trả channel exception `404 NOT_FOUND` và đóng channel đó. Message không được định tuyến; RabbitMQ **không phát `basic.return` cho tình huống này**.

```text
RabbitTemplate ------------ basic.publish ------------> RabbitMQ
                                  |
                            exchange KHÔNG tồn tại
                                  |
                           channel.close 404
                                  |
                    channel không còn dùng để publish
                                  |
                    framework/client xử lý shutdown
                                  |
                  send exception hoặc negative confirm
```

Vì publish không đồng bộ, cách lỗi xuất hiện trong ứng dụng có thể thay đổi theo version, tình trạng channel cache và thời điểm server đóng channel:

- `convertAndSend` có thể ném `AmqpException`.
- Lời gọi có thể **trả về trước** khi server đóng channel; lỗi sau đó được ghi log, báo qua connection/channel shutdown listener hoặc phản ánh bằng negative confirm có reason.
- Nếu connection/channel bị đóng trong khi publish đang outstanding, trạng thái kết quả có thể trở nên **không chắc chắn**, đòi hỏi timeout policy và retry.
- Không được viết test khẳng định exchange không tồn tại **phải** kích hoạt `ReturnsCallback` hoặc **phải** tạo đúng một exception đồng bộ trên thread gửi.

## 2. Ma trận hành vi cần kiểm thử

| Kịch bản | Exchange tồn tại? | Binding tới queue? | `mandatory` | Confirm mong đợi | Return mong đợi | Kết quả chính |
|---|---|---|---|---|---|---|
| A. Gửi hợp lệ | Có | Có | `true` | ACK | Không | Message xuất hiện trong queue |
| B. Routing key không khớp | Có | Không khớp | `true` | **ACK** | **312 NO_ROUTE** | Không vào queue đích |
| C. Exchange không tồn tại | **Không** | Không áp dụng | `true` | Gửi lỗi hoặc negative confirm/channel failure | **Không** | Broker đóng channel với `404 NOT_FOUND` |
| D. Unroutable nhưng không mandatory | Có | Không khớp | `false` | ACK | Không | Bị drop nếu không có alternate exchange |
| E. Publish không chắc chắn vì mất kết nối | Có thể | Có thể | Tùy | Có thể timeout/exception | Không chắc | Cần retry + idempotency |

Bảng giả định **exchange direct bình thường, không cấu hình alternate exchange**. Nếu exchange có **alternate exchange** và fallback route được tới queue khác, hành vi `mandatory return` có thể khác: message không nhất thiết bị trả về dù routing key không khớp binding chính. Vì vậy test phải tự tạo topology tối giản và cô lập.

**Exchange mặc định `""` là một exchange có sẵn** trong RabbitMQ, không phải “exchange không tồn tại”. Với default exchange, routing key là tên queue; test exchange không tồn tại phải dùng một **tên khác, duy nhất** chưa được khai báo.

## 3. Chuẩn bị môi trường test đáng tin cậy

### 3.1. Vì sao cần broker thật?

Kiểm thử service bằng Mockito phù hợp để xác minh application đã gọi `RabbitTemplate` với exchange/routing key đúng. Nhưng mock **không thể tái hiện** chính xác:

- `basic.return` được broker gửi **trước** confirm.
- Confirm ACK cho publish unroutable.
- `channel.close 404 NOT_FOUND` khi exchange không tồn tại.
- Tính bất đồng bộ của channel shutdown, connection recovery.
- Khác biệt giữa publisher confirm và consumer acknowledgment.

`TestRabbitTemplate` trong `spring-rabbit-test` có ích để test logic listener trực tiếp **không qua broker**, nhưng không thay thế bài kiểm thử protocol trong chủ đề này. Dùng **Testcontainers với RabbitMQ thật** hoặc một RabbitMQ integration-test broker có vòng đời được kiểm soát.

### 3.2. Thư viện cần có

Với Maven/Gradle, nhóm dependency kiểm thử thường gồm:

| Dependency | Vai trò |
|---|---|
| `spring-boot-starter-amqp` | Spring Rabbit, `RabbitTemplate`, `RabbitAdmin` |
| `spring-boot-starter-test` | JUnit Jupiter, AssertJ, Spring Boot Test |
| `org.testcontainers:junit-jupiter` | Tích hợp lifecycle Testcontainers với JUnit 5 |
| `org.testcontainers:rabbitmq` | Container RabbitMQ; package class có thể khác ở Testcontainers 2.x |
| `org.awaitility:awaitility` (tùy chọn) | Chờ điều kiện bất đồng bộ khi thực sự cần; không dùng `Thread.sleep` để “đồng bộ” test |

Không cần đưa RabbitMQ test broker vào production. Các ví dụ sử dụng image minh họa `rabbitmq:4.1-management`; pin image/version phù hợp CI của tổ chức. Testcontainers cần Docker hoặc container runtime tương thích và một image có thể được tải ở môi trường kiểm thử.

### 3.3. Bật correlated publisher confirms và returns

Với Spring Boot, cấu hình kiểm thử:

```yaml
spring:
  rabbitmq:
    publisher-confirm-type: correlated
    publisher-returns: true
    template:
      mandatory: true
```

Ba thuộc tính có vai trò riêng:

1. `publisher-confirm-type: correlated`: bật confirm mode và hạ tầng gắn kết quả với `CorrelationData`.
2. `publisher-returns: true`: bật khả năng nhận returned messages ở `CachingConnectionFactory`.
3. `template.mandatory: true`: yêu cầu broker trả message unroutable. Chỉ bật returns trên factory mà không bật mandatory thì **không** làm broker gửi `basic.return`.

Cấu hình Java tương đương:

```java
CachingConnectionFactory factory =
        new CachingConnectionFactory("localhost", 5672);
factory.setPublisherConfirmType(
        CachingConnectionFactory.ConfirmType.CORRELATED);
factory.setPublisherReturns(true);

RabbitTemplate template = new RabbitTemplate(factory);
template.setMandatory(true);
```

Đây là minh họa **manual configuration**; nếu dùng Spring Boot auto-configuration, nên dùng các thuộc tính YAML phía trên hoặc cấu hình customizer nhất quán, **không** tạo thêm một template không được bean test sử dụng.

**Không bật `channelTransacted=true` trên cùng publisher channel dùng confirms** để “chắc chắn hơn”: AMQP transaction mode và publisher confirm mode là hai cơ chế khác nhau, không dùng cùng channel. Test hiện tại tập trung vào confirms/returns.

### 3.4. Thực hành khai báo topology chính xác

Test sẽ tạo:

```text
RabbitMQ test broker
        |
        +-- direct exchange it.confirm.<random>
               |
               | binding key: "ok"
               v
            durable queue it.confirm.q.<random>

Publish:
  exchange=it.confirm.<random>, routingKey="ok"      -> ROUTED
  exchange=it.confirm.<random>, routingKey="absent"  -> NO_ROUTE
  exchange=it.missing.<random>, routingKey="ok"      -> 404 NOT_FOUND
```

Sử dụng một hậu tố ngẫu nhiên cho mỗi test để không đụng kết quả từ lần chạy khác. Không tạo queue có tên `absent` hoặc bất kỳ binding ngầm nào cho routing key `absent`. Không cấu hình alternate exchange trên exchange này.

## 4. Integration test có thể dùng làm khung tham khảo

Phần dưới trình bày một file kiểm thử Java với Spring Boot 3.x và Testcontainers 1.x. Các import trong code chỉ đưa những kiểu chính; IDE có thể tự thêm import `org.junit.jupiter.api.*`, `org.springframework.*`, `org.testcontainers.*` và `org.assertj.core.api.Assertions.assertThat`.

### 4.1. Bootstrap ứng dụng test và RabbitMQContainer

```java
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.amqp.AmqpException;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.amqp.rabbit.connection.CorrelationData;
import org.springframework.amqp.rabbit.core.RabbitAdmin;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.RabbitMQContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

import java.util.UUID;
import java.util.concurrent.TimeUnit;

import static org.assertj.core.api.Assertions.assertThat;

@Testcontainers
@SpringBootTest(
    classes = PublisherSignalsIT.Bootstrap.class,
    properties = {
        "spring.rabbitmq.publisher-confirm-type=correlated",
        "spring.rabbitmq.publisher-returns=true",
        "spring.rabbitmq.template.mandatory=true"
    })
class PublisherSignalsIT {

    @Container
    static final RabbitMQContainer BROKER = new RabbitMQContainer(
            DockerImageName.parse("rabbitmq:4.1-management"));

    @DynamicPropertySource
    static void rabbitProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.rabbitmq.host", BROKER::getHost);
        registry.add("spring.rabbitmq.port", BROKER::getAmqpPort);
        registry.add("spring.rabbitmq.username", BROKER::getAdminUsername);
        registry.add("spring.rabbitmq.password", BROKER::getAdminPassword);
    }

    @SpringBootConfiguration
    @EnableAutoConfiguration
    static class Bootstrap {
        // Spring Boot tạo ConnectionFactory, RabbitTemplate,
        // RabbitAdmin theo auto-configuration.
    }

    @Autowired RabbitTemplate template;
    @Autowired RabbitAdmin admin;
    @Autowired ConnectionFactory connectionFactory;

    String exchange;
    String queue;

    @BeforeEach
    void prepare() {
        String suffix = UUID.randomUUID().toString();
        exchange = "it.confirm." + suffix;
        queue = "it.confirm.q." + suffix;

        DirectExchange x = new DirectExchange(exchange, true, false);
        Queue q = QueueBuilder.durable(queue).build();

        admin.declareExchange(x);
        admin.declareQueue(q);
        admin.declareBinding(
                BindingBuilder.bind(q).to(x).with("ok"));
    }

    @AfterEach
    void cleanup() {
        admin.deleteQueue(queue);
        admin.deleteExchange(exchange);
    }

    private CorrelationData publish(
            RabbitTemplate sendingTemplate,
            String targetExchange,
            String key,
            String body) {

        CorrelationData cd =
                new CorrelationData(UUID.randomUUID().toString());
        sendingTemplate.convertAndSend(targetExchange, key, body, cd);
        return cd;
    }

    private CorrelationData.Confirm awaitConfirm(CorrelationData cd)
            throws Exception {
        return cd.getFuture().get(10, TimeUnit.SECONDS);
    }

    // Test methods ở các mục tiếp theo nằm trong class này.
}
```

Điểm đáng chú ý:

- `@DynamicPropertySource` lấy **host và mapped AMQP port** thực tế do Testcontainers cấp; không hard-code cổng localhost của container.
- `RabbitAdmin.declareExchange/declarQueue/declareBinding` chạy trước publish. Không dùng auto-declared `@Bean DirectExchange` cho exchange đang muốn kiểm tra là “không tồn tại”.
- `@AfterEach` chỉ dọn **queue/exchange do test sở hữu**. Với hệ thống CI chạy song song, suffix riêng giảm va chạm.
- Chỉ tạo **một** `RabbitTemplate` được Boot cấu hình correlated confirms/returns. Không thay đổi global callback hay `mandatory` của template trong từng test vì các test có thể chạy song song.
- `RabbitAdmin` tồn tại khi Rabbit auto-configuration và auto-declaration được bật. Nếu dự án tắt `spring.rabbitmq.dynamic` hoặc thay auto-configuration, hãy tạo/inject admin tường minh trong test.

**Lưu ý Testcontainers phiên bản:** Import `org.testcontainers.containers.RabbitMQContainer` thuộc Testcontainers 1.x; ở Testcontainers 2.x container module/class đã có thay đổi package. Chọn một thế hệ Testcontainers nhất quán với phần dependency của dự án trước khi biên dịch.

### 4.2. Test A — exchange và routing key hợp lệ

Thêm vào `PublisherSignalsIT`:

```java
@Test
void routablePublishGetsAckAndNoReturn() throws Exception {
    CorrelationData cd = publish(template, exchange, "ok", "event-A");

    CorrelationData.Confirm confirm = awaitConfirm(cd);

    assertThat(confirm.isAck()).isTrue();
    assertThat(cd.getReturn()).isNull();

    Object body = template.receiveAndConvert(queue, 3_000);
    assertThat(body).isEqualTo("event-A");
}
```

Ba assertion độc lập:

1. **ACK confirm**: broker đã xác nhận publish.
2. **Không có return**: không bị broker trả lại do unroutable.
3. **Nhận được message từ queue đích**: topology thực sự đưa message tới queue dự kiến.

Nếu consumer ứng dụng khác cũng đang đọc cùng queue test, assertion số 3 có thể thất bại vì **consumer đã lấy message**. Do đó dùng queue riêng, không gắn `@RabbitListener` cạnh tranh, và không kiểm tra một production queue đang có consumer thật.

`receiveAndConvert(queue, 3_000)` là test-only pull để quan sát message. Nó không đại diện cho một consumer nghiệp vụ commit DB, và việc lấy message có thể ACK/loại message khỏi queue tùy API/configuration.

### 4.3. Test B — mandatory return khi không có binding khớp

```java
@Test
void unroutableMandatoryGetsAckAndReturn() throws Exception {
    CorrelationData cd = publish(
            template, exchange, "absent", "event-B");

    CorrelationData.Confirm confirm = awaitConfirm(cd);

    // Broker đã xử lý publish, nên có thể ACK.
    assertThat(confirm.isAck()).isTrue();

    // Nhưng không queue nào nhận message.
    var returned = cd.getReturn();
    assertThat(returned).isNotNull();
    assertThat(returned.getReplyCode()).isEqualTo(312);
    assertThat(returned.getReplyText()).contains("NO_ROUTE");
    assertThat(returned.getExchange()).isEqualTo(exchange);
    assertThat(returned.getRoutingKey()).isEqualTo("absent");

    // Queue chỉ có binding key "ok".
    assertThat(template.receive(queue, 200)).isNull();
}
```

**Vì sao test chờ confirm trước rồi mới đọc return?** Với **correlated confirms + returns** được cấu hình đúng, Spring AMQP bảo đảm `CorrelationData.getReturn()` được gắn **trước khi** confirm future hoàn thành với ACK cho message returned (miễn điều kiện callback được tuân thủ). Vì vậy `awaitConfirm(cd)` là một rào chờ hợp lệ; test không cần `Thread.sleep(1000)` để “cho return chạy kịp”.

RabbitMQ quy định `basic.return` của message unroutable có `mandatory=true` được gửi **trước** publisher confirm. Một **confirm ACK vẫn hợp lệ** sau NO_ROUTE vì broker đã xác định publish không thể định tuyến.

### 4.4. Test C — gửi tới exchange không tồn tại

```java
@Test
void missingExchangeCausesFailureNotMandatoryReturn() throws Exception {
    String missingExchange = "it.missing."
            + UUID.randomUUID();

    CorrelationData cd =
            new CorrelationData(UUID.randomUUID().toString());

    boolean synchronousFailure = false;

    try {
        template.convertAndSend(
                missingExchange, "ok", "event-C", cd);
    } catch (AmqpException ex) {
        synchronousFailure = true;
    }

    if (!synchronousFailure) {
        // Kết quả lỗi có thể đến bất đồng bộ khi broker đóng channel.
        CorrelationData.Confirm confirm =
                cd.getFuture().get(10, TimeUnit.SECONDS);
        assertThat(confirm.isAck()).isFalse();
        // getReason() có thể chứa thông tin channel closure
        // nhưng không bắt buộc cùng một chuỗi ở mọi version.
    }

    // Thiếu exchange không phải trường hợp basic.return(NO_ROUTE).
    assertThat(cd.getReturn()).isNull();
}
```

Tại RabbitMQ, exchange không tồn tại dẫn tới `404 NOT_FOUND` và đóng **channel** đang publish. Với Spring AMQP, negative confirm do framework tạo có thể mang `reason` mô tả channel close. Một số hoàn cảnh lỗi có thể ném exception đồng bộ; test trên cho phép cả hai hình thức trong môi trường đã định nghĩa.

**Quan trọng:** Không nên catch mọi `Exception` rồi coi là “test đã pass”, vì như vậy cả lỗi kết nối, timeout do test sai cấu hình và lỗi code khác cũng bị che đi. Test cần phân biệt:

- Đường lỗi đồng bộ thuộc kiểu AMQP client failure.
- Hoặc đường lỗi bất đồng bộ có negative confirm trong deadline hữu hạn.
- **Không** có mandatory return.
- Nếu test cần kiểm tra chính xác `404 NOT_FOUND`, quan sát shutdown signal hoặc server logs và kiểm tra `replyCode` của channel exception trong một integration test riêng.

Một số phiên bản client có thể làm kết quả của `CompletableFuture` hoàn tất theo cách riêng hoặc báo exception khi connection bị lỗi cùng lúc; hãy phân biệt tình huống đó với một exchange thực sự chưa khai báo thay vì nới lỏng assertion đến mức mọi lỗi đều được chấp nhận.

### 4.5. Test D — không bật mandatory: ACK có thể đi cùng message bị drop

Vì `template` của test đang dùng `mandatory=true`, tạo **template thứ hai chỉ dùng trong test** để không thay đổi trạng thái toàn cục:

```java
@Test
void unroutableWithoutMandatoryCanAckWithoutReturn() throws Exception {
    RabbitTemplate nonMandatory =
            new RabbitTemplate(connectionFactory);
    nonMandatory.setMandatory(false);

    CorrelationData cd = publish(
            nonMandatory, exchange, "absent", "event-D");

    CorrelationData.Confirm confirm = awaitConfirm(cd);

    assertThat(confirm.isAck()).isTrue();
    assertThat(cd.getReturn()).isNull();
    assertThat(template.receive(queue, 200)).isNull();
}
```

Khi exchange tồn tại và không có binding phù hợp, RabbitMQ có thể **discard message** nếu `mandatory=false` và không có alternate exchange. Publisher confirm ACK vẫn không biểu thị đã vào một queue. Đây là một negative control giúp phát hiện cấu hình mandatory/returns bị thiếu trong ứng dụng.

### 4.6. Test E — template tiếp tục publish sau channel error

Sau lỗi `404`, **channel cũ không thể tiếp tục sử dụng**. `CachingConnectionFactory` thường quản lý channel mới khi publish tiếp; ta có thể kiểm chứng rằng ứng dụng không bị “hỏng vĩnh viễn” chỉ vì một publish sai tên exchange.

```java
@Test
void validPublishWorksAfterMissingExchangeFailure() throws Exception {
    String missing = "it.missing." + UUID.randomUUID();
    CorrelationData bad =
            new CorrelationData(UUID.randomUUID().toString());

    try {
        template.convertAndSend(missing, "ok", "bad", bad);
        assertThat(awaitConfirm(bad).isAck()).isFalse();
    } catch (AmqpException expected) {
        // Channel đã gặp lỗi giao thức.
    }

    CorrelationData good =
            publish(template, exchange, "ok", "event-after-failure");

    assertThat(awaitConfirm(good).isAck()).isTrue();
    assertThat(good.getReturn()).isNull();
    assertThat(template.receiveAndConvert(queue, 3_000))
            .isEqualTo("event-after-failure");
}
```

Không kiểm tra “cùng một physical channel vẫn hoạt động”, vì channel đã đóng theo protocol. Mục tiêu là **connection factory/template có thể phục hồi bằng channel phù hợp** và những lần gửi hợp lệ sau không bị lỗi dây chuyền.

## 5. Quan sát lỗi 404 qua channel/connection shutdown

`CorrelationData.Confirm.getReason()` có thể mô tả một NACK do Spring framework phát sinh sau channel shutdown, nhưng test không nên phụ thuộc vào một substring cố định như `"404 NOT_FOUND"` ở tất cả Spring/RabbitMQ versions.

Khi cần xác nhận **đúng mã lỗi protocol**, thêm observer chỉ dành cho test/diagnostics hoặc dùng log phía broker:

```java
CachingConnectionFactory cf = /* Bean của application */;
cf.addConnectionListener(new ConnectionListener() {
    @Override
    public void onCreate(Connection connection) {
        // Không thay đổi connection ở đây.
    }

    @Override
    public void onShutDown(ShutdownSignalException signal) {
        // Ghi nhận structured signal: reply code, classId, methodId...
        // Không block callback thread.
    }
});
```

Import minh họa: `org.springframework.amqp.rabbit.connection.CachingConnectionFactory`, `org.springframework.amqp.rabbit.connection.ConnectionListener`, `org.springframework.amqp.rabbit.connection.Connection` và `com.rabbitmq.client.ShutdownSignalException`.

**Phân biệt:** `ShutdownSignalException` là tín hiệu channel/connection đóng, không phải `ReturnedMessage`. Broker logs thường hiển thị **`NOT_FOUND - no exchange '...' in vhost '...'`** với channel error. Nếu ứng dụng cần assertion chặt về `404`, có thể dùng chính signal của RabbitMQ client và đối chiếu `AMQP.Channel.Close.replyCode` thay vì so sánh toàn bộ text thay đổi theo version.

Không biến test lỗi exchange thành bài test service restart: một channel bị đóng theo protocol **không nhất thiết đóng toàn bộ connection**. Các channel hợp lệ khác có thể tiếp tục hoạt động.

## 6. Thiết kế test không flaky: đồng bộ hóa bằng tín hiệu thật

### 6.1. Đừng dùng Thread.sleep để chờ return

Ví dụ sai:

```java
rabbitTemplate.convertAndSend(exchange, "absent", payload, cd);
Thread.sleep(500); // Hy vọng broker đã trả result
assertThat(cd.getReturn()).isNotNull();
```

Máy CI chậm, mạng lag hoặc broker đang bận có thể khiến 500 ms không đủ; test thất bại không ổn định. Ngược lại, ngủ 5 giây cho mọi test làm suite rất chậm mà vẫn không có bảo đảm.

Dùng `cd.getFuture().get(timeout, unit)` để chờ publisher confirm, rồi kiểm tra return vì **có thứ tự return-before-confirm** trong cấu hình tương ứng. Với điều kiện khác không có correlation, dùng `CompletableFuture`/`CountDownLatch` cho callback hoặc `Awaitility` chờ điều kiện quan sát được.

### 6.2. CorrelationData ID phải độc lập cho mỗi publish

`CorrelationData` nên có ID riêng để phân biệt các publish cùng lúc:

```java
String publishId = UUID.randomUUID().toString();
CorrelationData cd = new CorrelationData(publishId);

template.convertAndSend(exchange, key, body, cd);
CorrelationData.Confirm result = cd.getFuture()
        .get(10, TimeUnit.SECONDS);
```

Không tạo lại cùng một `CorrelationData` object cho nhiều message đang outstanding. Với business retry của **cùng một sự kiện**, có thể giữ **business event ID** cố định nhưng tạo **publish attempt correlation ID** mới cho từng lần thử:

```text
eventId:         order-123-event-7       (giữ nguyên qua retry)
attemptId:       order-123-event-7/a1    (mỗi lần publish khác nhau)
attemptId:       order-123-event-7/a2
RabbitMQ messageId/header eventId:       giữ eventId ổn định
CorrelationData.id:                      attemptId
```

Nhờ vậy logs và metrics có thể kết nối các lần publish mà không nhầm kết quả ACK/NACK của attempt cũ với attempt mới.

### 6.3. Không sửa shared RabbitTemplate giữa các test

`RabbitTemplate.setMandatory(...)` và `setReturnsCallback(...)` thay đổi cấu hình của bean. Nếu hai test chạy song song và cùng thay đổi template, một test đang chờ returned message có thể bị test khác tắt mandatory giữa chừng.

Khuyến nghị:

- Dùng template **bất biến về cấu hình trong suốt bài test**.
- Nếu cần negative control, tạo template riêng với cùng `ConnectionFactory` như test D.
- Mỗi test tự sở hữu exchange, queue, binding và ID.
- Không dùng một queue chung có listener khác tiêu thụ message để chứng minh routing.
- Không chạy `@DirtiesContext` vô cớ sau mỗi test; chỉ reset context khi test thực sự sửa hạ tầng Spring khó hoàn nguyên.

### 6.4. Giới hạn timeout, tránh treo test

Một test có thể timeout vì broker down hoặc pipeline confirm chưa được cấu hình. Hãy dùng thời hạn hữu hạn (ví dụ 10 giây trong lab) và giữ diagnostic context: tên exchange, routing key, correlation ID, broker endpoint/vhost, connection/channel error và pending confirms.

**Timeout không bằng negative confirm.** Không được viết:

```java
try {
    cd.getFuture().get(10, TimeUnit.SECONDS);
} catch (TimeoutException ignored) {
    // Sai: coi timeout là broker NACK.
}
```

Thay vào đó, test phải **fail có diagnostic**; ứng dụng production thì chuyển publish sang trạng thái **UNKNOWN/RETRYABLE**, giữ event ID và xử lý bằng retry/idempotency.

## 7. ReturnsCallback và ConfirmCallback trong ứng dụng thật

Bên cạnh `CorrelationData.getFuture()` và `getReturn()`, `RabbitTemplate` còn có callbacks để ghi metrics và quan sát tập trung:

```java
@Configuration
public class PublisherSignalLogging {

    @Bean
    RabbitTemplate observedTemplate(ConnectionFactory cf) {
        RabbitTemplate template = new RabbitTemplate(cf);
        template.setMandatory(true);

        template.setReturnsCallback(returned -> {
            // Không block; ghi metric + log metadata an toàn.
            log.warn("unroutable exchange={} routingKey={} code={} reason={}",
                    returned.getExchange(),
                    returned.getRoutingKey(),
                    returned.getReplyCode(),
                    returned.getReplyText());
        });

        template.setConfirmCallback((correlation, ack, cause) -> {
            String id = correlation == null
                    ? "unknown" : correlation.getId();
            log.info("publish attempt={} ack={} cause={}",
                    id, ack, cause);
        });
        return template;
    }
}
```

Trong ví dụ, `log` là SLF4J logger đã được khai báo trong class. Để dùng callbacks, vẫn phải bật `publisher-confirm-type=correlated`, `publisher-returns=true` trên connection factory và `mandatory=true` trên template. Mỗi template chỉ hỗ trợ **một** `ReturnsCallback` và **một** `ConfirmCallback`; nếu nhiều thành phần muốn quan sát, nên fan-out trong callback điều phối thay vì để từng service ghi đè callback.

Callbacks **không nên thực hiện tác vụ chậm** như DB write blocking, network request hay chờ một publish confirm khác. Hành vi của returned-message sequencing còn phụ thuộc callback không bị block quá lâu; Spring AMQP có quy tắc xử lý callback (bao gồm giới hạn khoảng 60 giây trong tài liệu) để tránh confirm bị giữ vô hạn.

**Nguồn sự thật cho một publish attempt** nên được kết hợp:

```text
send exception?
    | yes  -> FAILED / UNKNOWN, phân loại loại lỗi
    | no
    v
publisher confirm đến?
    | no   -> UNKNOWN, retry có idempotency
    | nack -> FAILED / retry theo reason
    | ack
    v
CorrelationData.getReturn() có message?
    | yes  -> UNROUTABLE, không đánh dấu delivered
    | no   -> ACCEPTED_BY_BROKER theo routing policy
```

Không gọi trạng thái cuối `DELIVERED_TO_CONSUMER` nếu chỉ có publisher confirm. Broker đã nhận chưa có nghĩa `@RabbitListener` đã xử lý.

## 8. Những tình huống bổ sung cần kiểm tra

### 8.1. Alternate exchange thay đổi kết quả mandatory

Một direct exchange có thể được cấu hình alternate exchange (AE). Khi routing key không khớp binding chính nhưng AE route được, message có thể vào **queue fallback**; lúc đó test “missing binding = NO_ROUTE” không còn đúng như topology tối giản.

Trong integration tests, hãy xác định AE có tồn tại hay không. Đừng gọi `NO_ROUTE` một cách máy móc chỉ vì không nhìn thấy binding ở exchange chính. Có thể viết test riêng cho fallback queue: confirm ACK, không return, message nằm ở fallback queue.

### 8.2. Không có consumer vẫn có thể publish thành công

Một durable queue tồn tại và binding đúng dù **không có consumer online** vẫn có thể nhận message. Publisher confirm ACK không chờ `@RabbitListener` ACK message.

```text
exchange -> queue (ready=1, consumer=0)  vẫn có thể confirm ACK
```

Test không nên dùng “không có listener” làm điều kiện để giả lập unroutable. **Unroutable** là không có **queue đích phù hợp**, không phải queue có consumer bị tắt.

### 8.3. Không tìm thấy queue khác với không tìm thấy exchange

Khi publish tới **default exchange `""`**, routing key là tên queue. Nếu queue này không tồn tại, default exchange vẫn **tồn tại**, và với `mandatory=true` publish thường trở thành trường hợp **NO_ROUTE**.

Ngược lại, publish tới **tên exchange không tồn tại** gây channel exception. Phải dùng đúng đích để phân biệt hai trường hợp khi test.

### 8.4. Producer network outage có thể tạo unknown outcome

Nếu kết nối bị cắt sau khi broker đã nhận message nhưng trước khi publisher nhận confirm, message có thể đã đến queue mặc dù `getFuture()` timeout hoặc framework báo channel/connection failure. Khi retry, message có thể bị gửi **lần thứ hai**.

Do đó:

- Giữ business `eventId` ổn định.
- Consumer idempotent bằng unique key/DB transaction.
- Sử dụng outbox bền vững nếu ý định publish cần tồn tại qua process crash.
- Không viết test “timeout chắc chắn không có message trong queue”; đó là một giả định không an toàn.

### 8.5. Test publisher NACK không giống test NO_ROUTE

Broker-generated publisher NACK là tình huống khác và thường hiếm hơn; không thể tạo nó một cách tin cậy chỉ bằng routing key không khớp. Với unroutable mandatory message, broker **thường vẫn confirm ACK** sau `basic.return`.

Muốn test business logic khi NACK mà không cần gây hỏng broker thật, có thể **unit test hàm phân loại kết quả** bằng dữ liệu `Confirm(false, reason)` giả lập; song integration test vẫn cần kiểm tra các protocol cases thật.

## 9. Bài tập thực hành theo cấp độ

### Bài 1 — Xác minh broker ACK của publish hợp lệ

Dùng exchange direct, queue và binding như mục 4. Publish với routing key `ok`. Chờ confirm bằng future, xác nhận `ack=true`, `return=null` và queue thực sự chứa payload. Không sử dụng listener cạnh tranh trên queue test.

### Bài 2 — Chứng minh ACK không có nghĩa đã vào queue

Publish tới exchange đang tồn tại với routing key `absent` và `mandatory=true`. Assert **ACK và returned message đồng thời**; reply code `312`, text `NO_ROUTE`, queue đích rỗng.

### Bài 3 — Tắt mandatory

Dùng một `RabbitTemplate` riêng với `setMandatory(false)`, cùng exchange nhưng key không có binding. Chờ confirm, xác nhận ACK, không có return và queue không có message. Giải thích vì sao test này không được dùng để đánh dấu gửi thành công theo yêu cầu nghiệp vụ.

### Bài 4 — Exchange không tồn tại

Publish tới exchange có tên duy nhất chưa được khai báo. Xác minh thất bại đồng bộ hoặc negative confirm, không có returned message, server logs hoặc shutdown signal chỉ ra `404 NOT_FOUND`. Đừng kỳ vọng `NO_ROUTE`.

### Bài 5 — Phục hồi sau channel close

Ngay sau bài 4, dùng cùng RabbitTemplate publish tới exchange hợp lệ. Xác nhận ACK và queue nhận message. Diễn giải rằng **channel mới** có thể được sử dụng; channel cũ đã đóng.

### Bài 6 — Default exchange

Publish vào exchange `""` với routing key là tên queue tồn tại: phải route. Publish vào exchange `""` với routing key là tên queue không tồn tại và mandatory: kiểm tra NO_ROUTE, không phải exchange error.

### Bài 7 — Alternate exchange

Tạo exchange chính có AE và fallback queue. Publish với routing key không khớp binding chính nhưng được AE định tuyến. Quan sát ACK, không return và message ở fallback queue; so sánh với bài 2.

### Bài 8 — Timeout và idempotency

Trong lab cô lập, cắt kết nối hoặc chặn confirm sau publish để mô phỏng **unknown outcome**. Xác nhận ứng dụng không coi timeout là NACK; khi retry cùng event ID, consumer có cơ chế chống xử lý trùng.

### Bài 9 — Song song nhiều publish attempts

Gửi đồng thời 100 message với mỗi lần một `CorrelationData` riêng. Xác nhận kết quả được ghép theo correlation ID; không dùng một biến `lastConfirm` chung. Nếu có một vài routing key không hợp lệ, chỉ những correlation IDs tương ứng có returned message.

### Bài 10 — Báo cáo quan sát hệ thống

Đếm `publisher_ack_total`, `publisher_nack_total`, `publisher_return_total`, `publisher_confirm_timeout_total`, `channel_close_404_total`; log exchange/routing key, correlation ID, broker/vhost và loại lỗi. So sánh metrics với queue ready, message counts và broker logs để chứng minh không trộn unroutable với missing exchange.

**Tiêu chí đạt:** Test có broker thật, từng kịch bản độc lập, không `sleep` cố định, phân biệt confirm với return và channel failure, không xem ACK là consumer success, và có đường retry/idempotency khi kết quả publish không chắc chắn.

## 10. Checklist cho pull request

Trước khi merge thay đổi liên quan publisher RabbitMQ, nên xác minh:

- [ ] Có integration test **routable → ACK + no return + queue receives message**.
- [ ] Có integration test **unroutable mandatory → ACK + NO_ROUTE**.
- [ ] Có integration test **missing exchange → channel failure/404; không có return**.
- [ ] Test dùng queue/exchange riêng và không có consumer cạnh tranh.
- [ ] `publisher-confirm-type=correlated`, `publisher-returns=true`, `mandatory=true` được cấu hình trên bean thực tế.
- [ ] Dùng `CorrelationData` riêng cho mỗi publish attempt.
- [ ] Future/callback được chờ bằng signal và timeout hữu hạn, không `Thread.sleep`.
- [ ] Khi confirm timeout, ứng dụng giữ trạng thái **UNKNOWN** và retry an toàn bằng event ID cố định.
- [ ] Không nhầm publisher confirms với consumer ACK hoặc database commit.
- [ ] Negative control `mandatory=false` và alternate exchange được đánh giá nếu topology dùng chúng.
- [ ] Các callback không block, không ghi đè nhau và có logs/metrics đủ phân loại lỗi.
- [ ] Khả năng phục hồi sau `channel.close` được kiểm tra, không dùng lại chính channel đã đóng.

## 11. Những ngộ nhận phổ biến

| Nhận định sai | Điều đúng |
|---|---|
| “`convertAndSend` trả về bình thường là đã tới queue.” | Publish bất đồng bộ; cần confirm, return và kiểm tra routing. |
| “Confirm ACK nghĩa là chắc chắn có queue nhận.” | Unroutable message có thể **ACK + return**. |
| “Mandatory return nghĩa là broker NACK.” | Return và confirm là hai tín hiệu khác; unroutable thường ACK. |
| “Exchange không tồn tại sẽ trả `NO_ROUTE`.” | Exchange thiếu gây channel exception `404 NOT_FOUND`, không phải `basic.return`. |
| “Không có consumer thì message sẽ bị return.” | Queue/binding tồn tại vẫn có thể lưu message mà chưa có consumer. |
| “Chỉ bật publisher-returns là đã nhận `basic.return`.” | Cần bật `mandatory` cho publish tương ứng và có hạ tầng nhận returns. |
| “Timeout tức là broker không có message.” | Outcome không xác định; broker có thể đã nhận. |
| “Dùng `Thread.sleep(1s)` là kiểm tra return an toàn.” | Phụ thuộc tốc độ môi trường; chờ confirm future hoặc tín hiệu callback. |
| “Có publisher confirms nên không cần eventId.” | Có thể retry sau timeout và tạo duplicate; idempotency vẫn cần. |
| “Channel close làm toàn bộ RabbitMQ connection hỏng.” | Protocol channel error thường đóng channel; connection có thể vẫn dùng channel khác. |
| “Tăng timeout sẽ sửa được exchange không tồn tại.” | Đây là lỗi topology/cấu hình cần sửa, không phải độ trễ broker. |

## 12. Câu hỏi tự kiểm tra

1. Vì sao `RabbitTemplate.convertAndSend` không ném exception vẫn chưa đủ để khẳng định message đến queue?
2. Khi exchange tồn tại nhưng không có binding khớp, `mandatory=true` dẫn đến tín hiệu nào?
3. Vì sao confirm ACK có thể xuất hiện cùng `NO_ROUTE`?
4. Exchange không tồn tại làm broker trả `basic.return` hay đóng channel?
5. Default exchange `""` có được tính là exchange không tồn tại không?
6. `CorrelationData.getReturn()` nên được đọc vào lúc nào để tránh race trong mô hình correlated confirms/returns?
7. Vì sao không thể tạo test publisher NACK đáng tin cậy chỉ bằng routing key không khớp?
8. Nếu confirm timeout nhưng broker đã lưu message, retry có thể gây gì? Phương án nào giảm hậu quả?
9. Testcontainers giải quyết điều gì mà `TestRabbitTemplate` hoặc Mockito không tái hiện được?
10. Có nên đổi `setMandatory(false)` trên shared RabbitTemplate khi các test đang chạy song song?
11. Khi exchange có alternate exchange, kết quả unroutable khác test direct exchange không AE như thế nào?
12. Publisher confirm có liên hệ nguyên tử với `@RabbitListener` ACK/DB commit không?

**Đáp án gợi ý:** (1) publish bất đồng bộ; (2) `basic.return`, thường `312 NO_ROUTE` và sau đó confirm; (3) ACK xác nhận broker xử lý publish, không bảo đảm route; (4) đóng channel `404 NOT_FOUND`; (5) không; (6) sau future confirm ACK với cấu hình correlated confirms + returns; (7) NO_ROUTE vẫn có thể ACK; (8) duplicate, cần stable event ID/idempotent consumer/outbox; (9) hành vi protocol thật; (10) không, dùng template riêng; (11) fallback có thể route thành công nên không return; (12) không.

## 13. Tổng kết

Kiểm thử publisher trong **Spring AMQP** phải tách **publisher confirm**, **mandatory return** và **lỗi giao thức khi exchange không tồn tại**:

- **Routable:** broker có thể ACK, không return và message đến queue.
- **Unroutable vào exchange tồn tại:** với `mandatory=true`, thường **ACK + `NO_ROUTE` return**; ACK không chứng minh định tuyến thành công.
- **Exchange không tồn tại:** broker **đóng channel với `404 NOT_FOUND`**, không trả `basic.return`; client có thể nhận lỗi đồng bộ hoặc negative confirm bất đồng bộ.

Dùng `CorrelationData.getFuture()` làm tín hiệu chờ, đọc `getReturn()` sau confirm khi cấu hình đúng, triển khai integration tests bằng RabbitMQ thật, cô lập topology và ID từng test. Với ứng dụng production, kết hợp kết quả confirm/return, retry an toàn khi timeout, event ID bền vững, consumer idempotent và observability để đạt độ tin cậy đầu cuối; không xem publish ACK là xử lý nghiệp vụ thành công.

### Tài liệu tham khảo

- [Spring AMQP — RabbitTemplate, Correlated Publisher Confirms and Returns](https://docs.spring.io/spring-amqp/reference/amqp/template.html): `CorrelationData`, future, returned message, lỗi exchange thiếu và callbacks.
- [Spring AMQP — Testing Support](https://docs.spring.io/spring-amqp/reference/testing.html): `spring-rabbit-test`, `TestRabbitTemplate` và lựa chọn integration testing.
- [RabbitMQ — Consumer Acknowledgements and Publisher Confirms](https://www.rabbitmq.com/docs/confirms): thứ tự `basic.return` trước confirm, semantics publisher ACK.
- [RabbitMQ — Publishers](https://www.rabbitmq.com/docs/publishers): unroutable message, mandatory và channel exception khi publish tới exchange không tồn tại.
- [RabbitMQ — Java Client API Guide](https://www.rabbitmq.com/client-libraries/java-api-guide): return listeners, exception và client publishing.
- [Testcontainers — RabbitMQ Module](https://java.testcontainers.org/modules/rabbitmq/): chạy RabbitMQ thật trong integration test.

