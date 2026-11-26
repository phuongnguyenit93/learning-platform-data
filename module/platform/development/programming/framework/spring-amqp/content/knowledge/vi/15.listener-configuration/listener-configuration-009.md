# @SendTo, giá trị trả về và thông điệp phản hồi

Trong chương **Listener khai báo** của **SPRING_AMQP**, phương thức **@RabbitListener** không chỉ nhận và xử lý message. Khi phương thức **trả về một giá trị**, Spring AMQP có thể chuyển giá trị đó thành một **reply message** và publish đến địa chỉ phản hồi phù hợp. Annotation **@SendTo** giúp khai báo **địa chỉ phản hồi dự phòng** cho trường hợp request không có thuộc tính **replyTo**.

Chủ đề này kết nối ba phần của Spring AMQP: **RabbitTemplate** ở phía gửi, **exchange/queue/binding** ở tầng định tuyến, và **@RabbitListener** ở phía xử lý. Ví dụ xuyên suốt là một dịch vụ tính toán báo giá: caller gửi yêu cầu, listener tính kết quả và trả lại phản hồi. Bài học cũng làm rõ khi nào nên dùng request/reply, cách xử lý kết quả rỗng, timeout, exception, converter, correlation và những giới hạn độ tin cậy cần tính đến.

> **Điểm quan trọng:** **@SendTo không phải lệnh gửi một message mới độc lập.** Nó xác định nơi listener gửi **giá trị trả về** khi phù hợp. Nếu request đã mang thuộc tính AMQP **replyTo**, Spring AMQP ưu tiên địa chỉ đó; **@SendTo chỉ là phương án dự phòng**.

## 1. Một request và một reply được tạo như thế nào?

~~~mermaid
sequenceDiagram
    participant C as Caller / RabbitTemplate
    participant E as Request exchange
    participant Q as Request queue
    participant L as @RabbitListener
    participant R as Reply destination
    C->>E: Publish request (replyTo + correlation)
    E->>Q: Route theo binding
    Q->>L: Delivery
    L->>L: Chạy nghiệp vụ
    L->>R: Publish giá trị trả về
    R-->>C: Reply tới địa chỉ do caller chỉ định
    Note over C: Ghép reply với request tương ứng
~~~

Ở phía caller:

1. **RabbitTemplate** publish request đến một **exchange + routing key**.
2. Khi gọi **convertSendAndReceive(...)**, template quản lý việc thiết lập địa chỉ reply và cơ chế correlation cần thiết.
3. Caller chờ một reply hoặc kết thúc theo **replyTimeout**.

Ở phía listener:

1. **@RabbitListener** nhận message từ **request queue**.
2. Spring chuyển body đến tham số phương thức thông qua message converter.
3. Listener trả về một giá trị khác **void/null**.
4. Spring chuyển giá trị đó thành reply message và gửi đến địa chỉ **replyTo** trên request; nếu không có thì xét **@SendTo**.
5. Consumer của reply nhận phản hồi; **RabbitTemplate** có thể ghép phản hồi với request đang chờ.

**Request queue** và **reply destination** là hai vai trò khác nhau. Chúng có thể dùng các exchange/queue khác nhau; không phải cứ listener trả về một String là String đó tự xuất hiện trong cùng queue nhận request.

## 2. Ba cách viết listener: void, trả về giá trị và trả về Message

| Kiểu listener | Hành vi mong đợi | Trường hợp dùng |
|---|---|---|
| **void handle(Request)** | Không có giá trị kết quả để gửi làm reply | Event consumer, fire-and-forget |
| **String handle(Request)** | Spring có thể tạo reply từ String | RPC đơn giản, phản hồi văn bản |
| **ReplyDto handle(Request)** | Converter tuần tự hóa DTO thành reply | API bất đồng bộ có contract rõ |
| **org.springframework.messaging.Message<ReplyDto>** | Trả payload và header bổ sung | Reply cần metadata |
| **org.springframework.amqp.core.Message** | Trả body byte và AMQP properties đã tạo | Kiểm soát thấp tầng về reply |
| **CompletableFuture<ReplyDto>** | Reply sau khi tác vụ bất đồng bộ hoàn tất nếu dùng phiên bản/config hỗ trợ | Tránh giữ thread listener trong lúc đợi I/O |

**Đừng nhầm kiểu trả về với địa chỉ trả về.** Kiểu trả về quyết định **body và metadata**; **replyTo/@SendTo** quyết định **route**. Một phương thức trả về DTO không có nghĩa message converter luôn biết cách serialize DTO đó thành JSON nếu chưa được cấu hình.

### 2.1. Listener trả về null hoặc không trả gì

Nếu phương thức trả về **void** hoặc giá trị **null**, thông thường sẽ **không có reply message** được gửi. Với caller dùng **convertSendAndReceive(...)**, điều này có thể dẫn đến **reply timeout**.

Không nên dùng giá trị null như một thông báo nghiệp vụ “không tìm thấy” nếu caller cần kết luận chắc chắn. Hãy trả về một **reply DTO có trạng thái rõ ràng** như **NOT_FOUND** hoặc **VALIDATION_ERROR**.

### 2.2. Exception không mặc nhiên trở thành reply lỗi

Nếu listener ném exception trong lúc xử lý, Spring AMQP **không mặc định biến exception đó thành một response DTO thành công** cho caller. Tùy error handler, requeue, retry và DLX, request có thể bị gửi lại hoặc đưa vào dead-letter; caller có thể hết thời gian chờ reply.

Muốn trả lỗi nghiệp vụ có cấu trúc, hãy thiết kế **ReplyDto** có status/errorCode và bắt những lỗi **được dự kiến thuộc hợp đồng**. Không biến lỗi hạ tầng tạm thời thành một response thành công giả.

## 3. @SendTo chọn nơi gửi reply như thế nào?

Trong Spring AMQP, một phương thức **@RabbitListener** có thể khai báo:

~~~java
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.messaging.handler.annotation.SendTo;
import org.springframework.stereotype.Component;

@Component
public class GreetingListener {
    @RabbitListener(queues = "greetings.requests.q")
    @SendTo("greetings.replies.q")
    public String greet(String name) {
        return "Xin chao, " + name;
    }
}
~~~

Khi listener trả về String, Spring AMQP sẽ gửi reply:

- **Nếu request có replyTo:** dùng **replyTo** của request.
- **Nếu request không có replyTo:** dùng **greetings.replies.q** từ **@SendTo**.
- **Nếu không có cả hai:** không có địa chỉ phản hồi hợp lệ được xác định; việc trả về dữ liệu mà không chỉ định reply route không tạo ra một phản hồi có thể giao đến caller một cách đáng tin cậy.

Ví dụ queue **greetings.replies.q** phải tồn tại hoặc được khai báo bởi ứng dụng/đội vận hành. Một chuỗi tên queue trong **@SendTo** không tự đảm bảo queue có sẵn.

### 3.1. Cú pháp exchange/routingKey

Giá trị của **@SendTo** không phải URL HTTP. Spring AMQP hiểu nó như địa chỉ reply với dạng **exchange/routingKey**:

| Giá trị @SendTo | Exchange reply | Routing key |
|---|---|---|
| **greetings.replies.q** | Default exchange (tên rỗng) | greetings.replies.q |
| **/greetings.replies.q** | Default exchange | greetings.replies.q |
| **greetings.replies/rpc.result** | greetings.replies | rpc.result |
| **greetings.replies/** | greetings.replies | Chuỗi rỗng |
| **/** hoặc chuỗi rỗng | Default exchange | Chuỗi rỗng |

Trường hợp thứ nhất tiện khi reply sẽ được gửi trực tiếp tới **queue có tên cố định**: default exchange định tuyến theo queue name. Trường hợp có **exchange/routingKey** phù hợp khi cần binding và quản lý đường đi phản hồi rõ ràng.

**Cẩn thận với dấu gạch chéo:** **exchange/routingKey** là quy ước parse của Spring AMQP cho địa chỉ phản hồi; không phải cú pháp routing key của topic exchange. Trong các ví dụ nên đặt tên exchange/queue rõ ràng, không nhúng dấu **/** vào tên để tránh nhập nhằng.

### 3.2. Thứ tự ưu tiên của replyTo và @SendTo

~~~mermaid
flowchart TD
    A["@RabbitListener xử lý xong"] --> B{"Có giá trị trả về khác null?"}
    B -->|"Không"| X["Không tự gửi reply"]
    B -->|"Có"| C{"Request có replyTo?"}
    C -->|"Có"| D["Gửi đến replyTo của request"]
    C -->|"Không"| E{"Có @SendTo hợp lệ?"}
    E -->|"Có"| F["Gửi theo @SendTo"]
    E -->|"Không"| G["Thiếu reply destination<br/>cần cấu hình hoặc xử lý lỗi"]
~~~

Điều này giải thích tình huống thường gặp: bạn thêm **@SendTo("my.fixed.reply.queue")** nhưng khi caller dùng **RabbitTemplate.convertSendAndReceive(...)**, phản hồi **không đi vào queue cố định**. Đó là hành vi đúng, vì template đã đặt **replyTo** riêng cho lời gọi request/reply.

## 4. Thực hành hoàn chỉnh: replyTo từ RabbitTemplate và @SendTo dự phòng

Ví dụ dùng **Spring Boot + Spring AMQP** với một dịch vụ nhân đôi số nguyên. Để dễ quan sát, body request và reply đều là **String**, không phụ thuộc vào JSON converter.

### 4.1. Dependency và kết nối

Trong Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-amqp</artifactId>
</dependency>
~~~

Ví dụ **application.yml**, với RabbitMQ local đã có tài khoản và vhost:

~~~yaml
spring:
  rabbitmq:
    host: localhost
    port: 5672
    virtual-host: app_dev
    username: learn_amqp
    password: ${RABBITMQ_PASSWORD}
    template:
      reply-timeout: 5s
~~~

**reply-timeout** là giới hạn chờ phản hồi nghiệp vụ của **RabbitTemplate**; không phải **publisher confirm timeout**. Cấp mật khẩu thật qua biến môi trường/secret. Trong production cần xem SLO và thời gian xử lý thực tế trước khi chọn timeout.

### 4.2. Khai báo request/reply topology

Dùng request exchange và một reply exchange riêng để minh họa định tuyến. Reply queue cố định đóng vai trò **fallback** khi caller không đặt replyTo.

~~~java
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.Declarables;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class RpcTopology {
    public static final String REQUEST_EXCHANGE = "calc.rpc.requests";
    public static final String REQUEST_KEY = "calc.double";
    public static final String REQUEST_QUEUE = "calc.rpc.requests.q";

    public static final String REPLY_EXCHANGE = "calc.rpc.replies";
    public static final String REPLY_KEY = "calc.result";
    public static final String FALLBACK_REPLY_QUEUE =
            "calc.rpc.fallback.replies.q";

    @Bean
    public Declarables rpcResources() {
        DirectExchange requests =
                new DirectExchange(REQUEST_EXCHANGE, true, false);
        DirectExchange replies =
                new DirectExchange(REPLY_EXCHANGE, true, false);

        Queue requestQueue =
                QueueBuilder.durable(REQUEST_QUEUE).build();
        Queue fallbackQueue =
                QueueBuilder.durable(FALLBACK_REPLY_QUEUE).build();

        return new Declarables(
                requests,
                replies,
                requestQueue,
                fallbackQueue,
                BindingBuilder.bind(requestQueue)
                        .to(requests)
                        .with(REQUEST_KEY),
                BindingBuilder.bind(fallbackQueue)
                        .to(replies)
                        .with(REPLY_KEY)
        );
    }
}
~~~

**RabbitAdmin** có thể tự khai báo các bean trên khi Spring Boot đã cấu hình kết nối và cơ chế khai báo tự động được bật. Request và reply ở cùng vhost **app_dev**.

### 4.3. Viết @RabbitListener có @SendTo

~~~java
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.messaging.handler.annotation.SendTo;
import org.springframework.stereotype.Component;

@Component
public class DoubleNumberListener {

    @RabbitListener(queues = RpcTopology.REQUEST_QUEUE)
    @SendTo("calc.rpc.replies/calc.result")
    public String doubleNumber(String input) {
        int value = Integer.parseInt(input);
        return "result=" + (value * 2);
    }
}
~~~

Khi nhận **"21"**, phương thức trả về **"result=42"**. Spring AMQP sử dụng message converter để tạo reply body từ String. Với **SimpleMessageConverter**, String thường được chuyển sang dữ liệu văn bản.

Nếu request có replyTo, reply đi theo replyTo. Nếu request không có replyTo, Spring dùng địa chỉ **calc.rpc.replies/calc.result**, qua binding đến queue **calc.rpc.fallback.replies.q**.

Đoạn code này đơn giản hóa validation. Trong hệ thống thật cần kiểm tra input, giới hạn giá trị, tránh overflow khi nhân và có reply status rõ ràng cho lỗi nghiệp vụ.

### 4.4. Gọi request/reply bằng convertSendAndReceive

~~~java
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.stereotype.Service;

@Service
public class DoubleNumberClient {
    private final RabbitTemplate rabbitTemplate;

    public DoubleNumberClient(RabbitTemplate rabbitTemplate) {
        this.rabbitTemplate = rabbitTemplate;
    }

    public String calculate(int value) {
        Object result = rabbitTemplate.convertSendAndReceive(
                RpcTopology.REQUEST_EXCHANGE,
                RpcTopology.REQUEST_KEY,
                Integer.toString(value)
        );

        if (result == null) {
            throw new IllegalStateException(
                    "Khong nhan duoc reply trong thoi gian cho"
            );
        }
        if (!(result instanceof String)) {
            throw new IllegalStateException(
                    "Reply khong dung kieu: " + result.getClass()
            );
        }
        return (String) result;
    }
}
~~~

Ví dụ gọi **calculate(21)** có kết quả **result=42** nếu listener phản hồi trước reply timeout và không có lỗi định tuyến hoặc chuyển đổi.

**Chú ý:** **RabbitTemplate.convertSendAndReceive(...)** thường dùng cơ chế **direct reply-to** khi RabbitMQ hỗ trợ và template không cấu hình reply queue riêng. Spring AMQP quản lý **replyTo/correlation** cho lời gọi này. Vì vậy, reply **không đi qua fallback reply exchange** của ví dụ.

Nếu không có reply trước timeout, phiên bản Spring AMQP thông dụng trả về **null**; ứng dụng phải quyết định cách xử lý thay vì giả định null là kết quả nghiệp vụ hợp lệ.

### 4.5. Thử @SendTo khi không có replyTo

Dùng một lệnh gửi **không chờ reply**:

~~~java
rabbitTemplate.convertAndSend(
        RpcTopology.REQUEST_EXCHANGE,
        RpcTopology.REQUEST_KEY,
        "21"
);
~~~

Trong tình huống publisher không tự đặt **replyTo**, listener vẫn trả về **result=42**; Spring sử dụng **@SendTo** để publish vào exchange **calc.rpc.replies** với key **calc.result**. Message sẽ được route tới **calc.rpc.fallback.replies.q**.

Để quan sát, đừng chạy consumer riêng trên fallback queue; mở RabbitMQ Management UI, chọn đúng vhost, kiểm tra message **Ready** ở queue này.

**Khác biệt quan trọng:** Lệnh **convertAndSend(...)** chỉ publish request và không tự lấy reply về. Nếu bạn cần nhận giá trị trả về trực tiếp trong caller, dùng request/reply hoặc tạo một consumer của reply queue cùng cơ chế correlation riêng.

## 5. Request/reply với direct reply-to

RabbitMQ cung cấp cơ chế **direct reply-to** phục vụ RPC nhẹ, để caller có thể nhận reply mà không cần tạo một reply queue độc lập cho mỗi request.

~~~mermaid
flowchart LR
    C["RabbitTemplate<br/>convertSendAndReceive"] --> E["Request exchange"]
    E --> Q[("Request queue")]
    Q --> L["@RabbitListener<br/>return value"]
    L --> R["Direct reply-to<br/>amq.rabbitmq.reply-to"]
    R --> C
~~~

### 5.1. Direct reply-to và reply queue cố định

| Tiêu chí | Direct reply-to | Reply queue cố định |
|---|---|---|
| Cách dùng | RabbitTemplate có thể tự chọn khi hỗ trợ | Ứng dụng quản lý queue/listener reply |
| Cần khai báo queue reply riêng | Thường không | Có |
| Chi phí quản lý topology reply | Thấp | Cao hơn |
| Persistence của reply | **Không phải queue durable thông thường** | Phụ thuộc cấu hình queue/message |
| Trường hợp dùng | RPC ngắn, chấp nhận timeout và retry | Muốn kiểm soát reply consumer, concurrency hoặc topology riêng |
| Correlation | Template hỗ trợ tự ghép request/reply | Phải cấu hình đúng, nhất là khi có nhiều request in-flight |

**Direct reply-to có ngữ nghĩa at-most-once đối với reply**: nếu caller ngắt kết nối hoặc không còn nhận reply, phản hồi có thể bị mất. Nó **không** là giải pháp thay thế durable queue hay quy trình công việc kéo dài.

Với reply queue cố định, việc làm queue durable cũng không tự bảo đảm caller đang chờ còn tồn tại, biết ID tương ứng hay xử lý được reply muộn; vẫn cần xử lý lifecycle và correlation rõ ràng.

### 5.2. Timeout không hủy công việc

~~~mermaid
sequenceDiagram
    participant C as Caller
    participant Q as Request queue
    participant L as Listener
    C->>Q: Request A
    Q->>L: Delivery A
    Note over L: Tác vụ chạy lâu
    Note over C: replyTimeout hết
    C-->>C: convertSendAndReceive trả null
    L->>C: Reply A đến muộn
    Note over C: Request đã hết thời gian chờ<br/>Reply muộn có thể bị bỏ
~~~

**Reply timeout chỉ là giới hạn chờ của caller.** Nó không mặc nhiên gửi lệnh cancel tới listener. Nếu caller retry request A, listener có thể xử lý **hai lần**; request/reply không tự bảo đảm exactly-once.

Vì vậy, với nghiệp vụ có side effect (thanh toán, đặt chỗ, gửi hóa đơn), phải dùng **requestId/idempotency key** và chiến lược trạng thái phù hợp. Các thao tác cần thời gian dài thường phù hợp hơn với **command + event kết quả** thay vì giữ thread HTTP chờ RPC qua RabbitMQ.

## 6. Return value và MessageConverter

Giá trị Java trả về từ **@RabbitListener** được xử lý qua lớp chuyển đổi message. Nếu dùng sai converter, reply có thể đến nhưng caller không deserialize được.

| Giá trị listener trả về | Converter thông dụng | Reply body/properties |
|---|---|---|
| **String** | SimpleMessageConverter | Text bytes, thường contentType text/plain |
| **byte[]** | SimpleMessageConverter | Binary bytes |
| **DTO Java** | JSON MessageConverter | JSON, contentType application/json |
| **Spring Messaging Message<T>** | Converter + header mapping | Payload và headers do phương thức cung cấp |
| **Spring AMQP Message** | Không cần convert body lần nữa | Body bytes/properties do phương thức tạo |

Nếu client và listener không cùng codebase hoặc khác ngôn ngữ, nên thống nhất **contentType, charset, schemaVersion và reply DTO**, không dựa vào tên class Java có trong type headers nội bộ.

### 6.1. Trả về DTO bằng JSON converter

Đối với Spring AMQP 3.x với Jackson 2, một cấu hình thường gặp:

~~~java
import org.springframework.amqp.support.converter.Jackson2JsonMessageConverter;
import org.springframework.amqp.support.converter.MessageConverter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class JsonReplyConverterConfig {

    @Bean
    public MessageConverter jsonMessageConverter() {
        return new Jackson2JsonMessageConverter();
    }
}
~~~

Để dùng kiểu converter này, dự án cần Jackson phù hợp và phải đảm bảo **RabbitTemplate** và **listener factory** đang dùng converter đó. Với Spring AMQP 4.x/Jackson 3, dùng converter và import tương ứng phiên bản.

DTO có thể là record:

~~~java
public record CalculationReply(
        String requestId,
        String status,
        Integer result,
        String errorCode
) {}
~~~

Ví dụ listener **thay thế**, không chạy đồng thời với **DoubleNumberListener** trên cùng request queue nếu muốn thử một đường xử lý duy nhất:

~~~java
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.messaging.handler.annotation.SendTo;
import org.springframework.stereotype.Component;

@Component
public class JsonCalculationListener {

    @RabbitListener(queues = RpcTopology.REQUEST_QUEUE)
    @SendTo("calc.rpc.replies/calc.result")
    public CalculationReply process(String requestId) {
        return new CalculationReply(
                requestId,
                "OK",
                42,
                null
        );
    }
}
~~~

Giá trị trả về **CalculationReply** sẽ được JSON converter phù hợp tuần tự hóa thành JSON. Đoạn ví dụ chỉ minh họa cấu trúc reply; trong ứng dụng thật, cần khai báo request DTO và tính kết quả thực sự.

**Không mặc định** SimpleMessageConverter sẽ tạo JSON cho mọi DTO. Nếu chỉ nhận **byte[]** hoặc gặp lỗi parse ở phía caller, hãy kiểm tra converter được dùng thực tế và contentType của reply.

### 6.2. Trả thêm headers bằng Spring Messaging Message

Khi cần metadata trong reply, có thể trả về **org.springframework.messaging.Message<T>**:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.messaging.handler.annotation.SendTo;
import org.springframework.amqp.rabbit.annotation.RabbitListener;

@RabbitListener(queues = RpcTopology.REQUEST_QUEUE)
@SendTo("calc.rpc.replies/calc.result")
public Message<String> handleWithHeader(String input) {
    return MessageBuilder.withPayload("received:" + input)
            .setHeader("reply-schema-version", 1)
            .setHeader("service-name", "calculator")
            .build();
}
~~~

Đây là **phương thức minh họa đặt trong một bean được Spring quản lý**, không phải đoạn class hoàn chỉnh. Dùng như phương án thay thế listener khác trên cùng queue.

Chú ý có **hai kiểu Message khác nhau**:

- **org.springframework.messaging.Message<T>**: trừu tượng Spring Messaging, gồm payload và headers.
- **org.springframework.amqp.core.Message**: AMQP message thấp tầng có body byte[] và MessageProperties.

Khi cần đặt **contentType** cụ thể cho một reply đã được tuần tự hóa, Spring AMQP cung cấp thuộc tính như **replyContentType** và **converterWinsContentType** trên @RabbitListener, hoặc có thể trả về AMQP Message với properties được kiểm soát. Chọn cách phù hợp converter và phiên bản đang sử dụng.

### 6.3. Dùng ReplyPostProcessor để thêm metadata

Spring AMQP hỗ trợ xử lý reply trước khi gửi, chẳng hạn thêm header truy vết hoặc version. **ReplyPostProcessor** có thể nhận cả request và reply, hữu ích khi muốn chuyển một số metadata vào response.

Ví dụ tính chất nghiệp vụ:

~~~text
Request:
  headers.request-id = req-101
  body = "21"

Reply:
  headers.request-id = req-101
  headers.reply-version = 1
  body = "result=42"
~~~

Không sao chép tùy ý header nhạy cảm từ request sang reply. Đặc biệt, **correlationId/replyTo** là thông tin phục vụ ghép request/reply; không nên ghi đè nếu không hiểu cách RabbitTemplate quản lý.

## 7. @SendTo có thể dùng placeholder và SpEL

Ngoài đích reply cố định, **@SendTo** có thể dùng giá trị cấu hình hoặc biểu thức.

### 7.1. Placeholder từ cấu hình

~~~yaml
app:
  rpc:
    fallback-reply-address: calc.rpc.replies/calc.result
~~~

Ví dụ trên listener:

~~~java
@RabbitListener(queues = RpcTopology.REQUEST_QUEUE)
@SendTo("${app.rpc.fallback-reply-address}")
public String process(String input) {
    return "received:" + input;
}
~~~

Giá trị placeholder được Spring phân giải khi khởi tạo listener. Nó phù hợp việc đổi địa chỉ fallback theo môi trường, không phải định tuyến động theo nội dung từng message.

### 7.2. Biểu thức khởi tạo và biểu thức runtime khác nhau

| Cú pháp | Thời điểm đánh giá | Trường hợp dùng |
|---|---|---|
| **#{...}** | Một lần khi khởi tạo listener | Lấy reply address từ bean/config |
| **!{...}** | Với từng request/reply | Chọn đích dựa trên request và kết quả xử lý |
| **${...}** | Placeholder cấu hình | Địa chỉ fallback theo application properties |

Ví dụ **runtime SpEL**:

~~~java
@RabbitListener(queues = "calc.rpc.request.dynamic.q")
@SendTo("!{'calc.rpc.replies/' + result.routeKey()}")
public RoutedReply processDynamic(String input) {
    return new RoutedReply("calc.result", "received:" + input);
}
~~~

Ở đây **RoutedReply** là DTO của ứng dụng có phương thức **routeKey()**; queue request và binding đích cần được khai báo riêng. Đoạn trên là minh họa cú pháp, không thay thế topology hoàn chỉnh mục 4.

Biểu thức runtime có ngữ cảnh chứa **request**, **source** và **result**. Đích được tạo phải là **địa chỉ hợp lệ được phép gửi**; không nên lấy nguyên một giá trị do caller kiểm soát rồi ghép trực tiếp thành tên exchange/routing key để tránh lỗi định tuyến hoặc gửi dữ liệu sai nơi.

**Lưu ý thứ tự ưu tiên:** Những biểu thức **@SendTo** vẫn đóng vai trò fallback. Nếu request có **replyTo**, listener ưu tiên replyTo thay vì biểu thức fallback đã khai báo.

## 8. Multi-method listener và @RabbitHandler

Một bean có thể khai báo **@RabbitListener ở cấp class** kết hợp các phương thức **@RabbitHandler** để xử lý các payload khác nhau. **@SendTo** cũng có thể được dùng ở cấp class như default reply address.

~~~java
import org.springframework.amqp.rabbit.annotation.RabbitHandler;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.messaging.handler.annotation.SendTo;
import org.springframework.stereotype.Component;

@Component
@RabbitListener(queues = "commands.requests.q")
@SendTo("commands.replies.q")
public class CommandHandler {

    @RabbitHandler
    public String handleText(String text) {
        return "text:" + text;
    }

    @RabbitHandler
    public String handleNumber(Integer value) {
        return "number:" + value;
    }
}
~~~

Đây là mô hình minh họa; phải khai báo queue **commands.requests.q** và **commands.replies.q**, đồng thời có MessageConverter phân biệt/convert được payload String và Integer. Nếu converter chỉ trả String cho mọi request, nhánh Integer có thể không được chọn.

**@RabbitHandler** lựa chọn phương thức dựa trên kiểu payload sau conversion. **@SendTo cấp class** định nghĩa reply address dự phòng, còn thuộc tính **replyTo của request** vẫn được ưu tiên khi có.

## 9. Trả về CompletableFuture và ACK bất đồng bộ

Một listener có thể cần gọi service không đồng bộ và trả reply khi kết quả sẵn sàng.

~~~java
import java.util.concurrent.CompletableFuture;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.messaging.handler.annotation.SendTo;

@RabbitListener(queues = "calc.rpc.async.requests.q")
@SendTo("calc.rpc.replies/calc.result")
public CompletableFuture<String> processAsync(String input) {
    return CompletableFuture.supplyAsync(
            () -> "result=" + (Integer.parseInt(input) * 2)
    );
}
~~~

Đây là **phương thức minh họa**, cần đặt trong Spring bean, khai báo queue và dùng executor phù hợp nếu triển khai thật. Không sử dụng common thread pool không kiểm soát cho công việc blocking dài hoặc có SLA rõ ràng.

Với các kiểu trả về bất đồng bộ được hỗ trợ như **CompletableFuture** (và **Mono** khi có Reactor), Spring AMQP cần cơ chế **manual acknowledgment** để không ACK request trước khi tương lai hoàn tất. Các phiên bản Spring AMQP hiện đại có thể tự chuyển sang MANUAL khi phát hiện async return type; vẫn nên xác nhận hành vi với phiên bản thư viện và listener factory đang dùng.

Nếu future kết thúc bằng exception, message có thể bị requeue hoặc reject theo loại exception, container configuration và error handler. Nếu exception xảy ra **trước khi tạo được future**, cần bảo đảm lỗi đó được phản ánh đúng, tránh ACK sớm hoặc mất message.

**Không xem async return là bảo đảm xử lý exactly once.** Request có thể được giao lại khi kết nối mất trước ACK; hàm nghiệp vụ vẫn phải idempotent nếu tạo tác dụng phụ.

## 10. Thiết kế reply có trạng thái thay vì để caller đoán

Ví dụ bài toán báo giá: một request không hợp lệ vì mã sản phẩm không tồn tại không nên được biểu diễn bằng null reply rồi để caller chờ timeout.

Một hợp đồng reply rõ ràng:

~~~json
{
  "requestId": "req-1001",
  "status": "NOT_FOUND",
  "result": null,
  "errorCode": "PRODUCT_NOT_FOUND",
  "message": "Không tìm thấy sản phẩm"
}
~~~

Các trạng thái có thể được định nghĩa:

| Trạng thái | Ý nghĩa | Caller làm gì? |
|---|---|---|
| **OK** | Đã có kết quả | Sử dụng kết quả |
| **VALIDATION_ERROR** | Request sai hợp đồng | Sửa request, không retry nguyên request |
| **NOT_FOUND** | Không tồn tại thực thể | Xử lý nghiệp vụ phù hợp |
| **CONFLICT** | Trạng thái không cho phép | Điều chỉnh quy trình hoặc dữ liệu |
| **TEMPORARILY_UNAVAILABLE** | Không thể đáp ứng tạm thời | Retry có kiểm soát nếu operation idempotent |

Các trạng thái trên là **hợp đồng ứng dụng**, không phải mã lỗi AMQP. RabbitMQ không tự thêm chúng vào response.

Đối với exception bất ngờ, nên để cơ chế listener error handling/retry/DLQ xử lý và giúp người vận hành nhận biết. Nếu ứng dụng quyết định chuyển exception thành một reply lỗi, phải xác định rõ việc **ACK/requeue request gốc**, logging và cách caller retry để tránh vừa gửi response lỗi vừa âm thầm xử lý request lần nữa.

## 11. Chẩn đoán khi listener đã return nhưng caller không thấy reply

| Triệu chứng | Nguyên nhân có thể | Bước kiểm tra |
|---|---|---|
| **convertSendAndReceive trả null** | Reply timeout, listener không return, listener lỗi, reply không đến | Kiểm tra log listener và replyTimeout |
| **@SendTo queue không có message** | Request có replyTo nên bỏ qua @SendTo | Quan sát property replyTo của request |
| **Listener trả về null** | Không có response được gửi | Trả trạng thái reply rõ ràng |
| **Listener trả DTO, caller đọc byte[]** | MessageConverter không thống nhất | Kiểm tra contentType và converter cả hai phía |
| **Không có request delivery** | Exchange, binding, routing key hoặc vhost sai | Kiểm tra request queue/consumer count |
| **Fallback queue có message nhưng caller chờ timeout** | Caller dùng convertSendAndReceive nhưng reply bị route sai do cấu hình thủ công | Kiểm tra replyTo/correlation |
| **Reply đến sau khi timeout** | Xử lý chậm, network delay, timeout thấp | Theo dõi latency và late replies |
| **Listener xử lý lại cùng request** | Request redelivery hoặc caller retry | Dùng requestId/idempotency key |
| **Reply queue cố định không có binding** | @SendTo dùng exchange/routingKey không route được | Kiểm tra reply exchange và binding |
| **Chỉ một vài phiên bản consumer lỗi** | Khác converter/schema giữa instance | Kiểm tra rollout và compatibility |

### 11.1. Cần theo dõi metadata gì?

Khi debug, log những trường có ý nghĩa:

~~~text
requestId=req-1001
requestExchange=calc.rpc.requests
requestRoutingKey=calc.double
requestQueue=calc.rpc.requests.q
replyTo=amq.rabbitmq.reply-to...
replyOutcome=OK
processingLatencyMs=28
replyRoundTripMs=41
~~~

Các giá trị chỉ minh họa, không giả định một replyTo cụ thể được tạo theo một hậu tố cố định. Tùy chế độ Spring AMQP, replyTo có thể là địa chỉ direct reply-to hoặc queue phản hồi được cấu hình.

Đừng log payload có thông tin nhạy cảm; lưu **requestId, correlationId, contentType, errorCode, latency** thường đã đủ để điều tra vấn đề routing/serialization.

## 12. Khi nào nên dùng request/reply qua RabbitMQ?

Request/reply tạo trải nghiệm gần giống RPC, nhưng caller vẫn phụ thuộc vào tốc độ xử lý của service bên kia.

| Nhu cầu | Request/reply bằng RabbitTemplate | Command + event kết quả |
|---|---|---|
| Kết quả nhanh, vài chục đến vài trăm ms | Phù hợp nếu độ trễ và timeout được quản lý | Có thể phức tạp không cần thiết |
| Công việc vài phút/giờ | Không phù hợp khi giữ lời gọi chờ lâu | Thường phù hợp hơn |
| Cần caller luôn có mặt để nhận kết quả | Có thể dùng direct reply-to | Event lưu vào durable queue để đọc sau |
| Nhiều bước, retry, redelivery | Phải thiết kế thêm correlation và idempotency | Dễ mô hình hóa workflow bất đồng bộ hơn |
| Cần chịu mất kết nối caller | Direct reply-to không bảo đảm reply durable | Durable result event và lưu trạng thái phù hợp |

Ví dụ thay vì chờ kết quả dựng báo cáo trong **convertSendAndReceive(...)**, có thể:

1. Publish command **report.generate** với requestId.
2. Worker nhận và ACK theo chính sách sau xử lý.
3. Publish event **report.generated** hoặc **report.failed**.
4. Caller kiểm tra trạng thái qua database/API hoặc nhận notification riêng.

**@SendTo rất hữu ích cho reply ngắn và đơn giản**, nhưng không nên áp dụng nó như cơ chế job completion bảo đảm bền vững cho mọi loại công việc.

## 13. Độ tin cậy: reply không thay thế publisher confirm hoặc consumer ACK

Một luồng request/reply đáng tin cậy có ít nhất bốn điều cần phân biệt:

1. **Request publish:** Caller có thể bật publisher confirms/returns để biết broker xử lý publish và message có route được không.
2. **Request delivery:** Listener nhận message từ queue theo cơ chế consumer.
3. **Reply publish:** Listener trả về dữ liệu, Spring gửi reply; nếu reply path hỏng, caller có thể timeout.
4. **Request ACK:** Listener container xác nhận delivery của request theo chế độ AUTO/MANUAL và chiến lược xử lý lỗi.

**Không nên coi bốn bước này là một giao dịch nguyên tử.** Nếu listener đã ghi database nhưng lỗi khi gửi reply, request có thể bị xử lý lại hoặc caller retry, dẫn tới tác dụng phụ lặp. Cần idempotency, transaction, retry và DLQ tùy nghiệp vụ.

Trong listener **AUTO** thông dụng, container chịu trách nhiệm ACK khi xử lý thành công. Khi sử dụng **MANUAL**, ứng dụng phải ACK/NACK đúng delivery tag và channel; đối với async return, cần tuân thủ cơ chế acknowledgment của phiên bản Spring AMQP đang dùng.

**Reply timeout không phải bằng chứng nghiệp vụ đã thất bại.** Một tác vụ có thể đã hoàn tất nhưng reply bị mất hoặc đến muộn. Với yêu cầu quan trọng, dùng requestId và API tra cứu trạng thái để giải quyết tình huống chưa xác định.

## 14. Bài thực hành tự kiểm chứng

### Bài A — Không có replyTo, @SendTo được sử dụng

1. Khai báo topology mục 4.
2. Chạy **DoubleNumberListener** và bảo đảm fallback queue rỗng.
3. Gọi **RabbitTemplate.convertAndSend(...)** với input **"21"**, không đặt replyTo.
4. Kiểm tra fallback queue nhận **"result=42"**.
5. Giải thích tại sao caller của convertAndSend không tự nhận chuỗi kết quả.

### Bài B — Có replyTo, @SendTo bị bỏ qua

1. Gọi **DoubleNumberClient.calculate(21)**.
2. Kiểm tra trả về **"result=42"**.
3. Theo dõi property replyTo trên request nếu có công cụ quan sát phù hợp.
4. Xác nhận reply không cần đi qua **calc.rpc.fallback.replies.q**.
5. Giải thích cơ chế direct reply-to và cách RabbitTemplate ghép reply với request.

### Bài C — Listener trả về null

Đổi phương thức listener trong môi trường thử nghiệm để trả null. Dùng **convertSendAndReceive** và ghi lại hành vi khi hết replyTimeout. Sau đó thay null bằng reply DTO có trạng thái **NOT_FOUND**, so sánh khả năng xử lý của caller.

### Bài D — Sai routing của fallback reply

Thay **@SendTo** thành địa chỉ **calc.rpc.replies/missing.key** nhưng không tạo binding tương ứng. Gửi request không có replyTo. Quan sát message có thể không vào fallback queue và thảo luận cách bật publisher return/giám sát của phía listener để phát hiện reply không route.

### Bài E — Trả về DTO và headers

Thay String reply bằng **CalculationReply**, cấu hình JSON converter cho caller và listener, rồi thử:

- Chuyển DTO đúng sang JSON có contentType application/json.
- Trả thêm header **reply-schema-version**.
- Thay đổi schema version không tương thích để quan sát lỗi deserialize.
- Đảm bảo không có hai listener cùng nghe một queue khi đang cần kiểm chứng cùng một reply.

### Bài F — Timeout và idempotency

Tạo một request có **requestId=req-1001**, listener xử lý chậm hơn replyTimeout, sau đó caller retry cùng requestId. Giả lập một tác dụng phụ trong database và thiết kế để nó chỉ xảy ra **một lần** dù listener nhận nhiều delivery.

## 15. Những điều cần nhớ

- **@RabbitListener** có thể **trả về giá trị**; Spring AMQP chuyển giá trị thành một reply message khi có reply destination hợp lệ.
- **@SendTo là địa chỉ reply fallback**: chỉ được dùng khi request không mang **replyTo**.
- **@SendTo("exchange/routingKey")** chọn exchange và routing key; **@SendTo("queueName")** gửi qua default exchange tới queue cùng tên.
- **RabbitTemplate.convertSendAndReceive(...)** quản lý request/reply, correlation và thường dùng direct reply-to; **convertAndSend(...)** không chờ reply.
- **Void/null** thường không tạo reply; exception không tự trở thành business error DTO.
- **MessageConverter** quyết định cách serialize/deserialize giá trị trả về; JSON DTO cần converter/schema thống nhất.
- **Reply timeout không hủy tác vụ**; request có thể đã xử lý nhưng reply bị mất hoặc đến muộn.
- **Publisher confirm, return, consumer ACK, retry, dead-letter và idempotency** vẫn cần thiết để hệ thống dùng Spring AMQP xử lý bất đồng bộ đáng tin cậy.

### Tài liệu tham khảo chính thức

- [Spring AMQP — Reply Management](https://docs.spring.io/spring-amqp/reference/amqp/receiving-messages/async-annotation-driven/reply.html): giá trị trả về, @SendTo, replyTo, SpEL và ReplyPostProcessor.
- [Spring AMQP — Request/Reply Messaging](https://docs.spring.io/spring-amqp/reference/amqp/request-reply.html): RabbitTemplate, direct reply-to và replyTimeout.
- [Spring AMQP — Reply ContentType](https://docs.spring.io/spring-amqp/reference/amqp/receiving-messages/async-annotation-driven/reply-content-type.html): converter và content type của reply.
- [Spring AMQP — Asynchronous @RabbitListener Return Types](https://docs.spring.io/spring-amqp/reference/amqp/receiving-messages/async-returns.html): CompletableFuture, Mono và acknowledgment.
- [RabbitMQ — Direct Reply-to](https://www.rabbitmq.com/docs/direct-reply-to): cơ chế gửi reply và giới hạn at-most-once.
