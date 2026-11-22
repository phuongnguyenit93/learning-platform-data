# MessagingTemplate và DirectChannel

Trong module **SPRING_INTEGRATION_CORE**, MessagingTemplate là điểm nối khi mã Java chủ động gọi một luồng thông điệp. Bài này thuộc chương **MessagingTemplate**, tập trung vào việc gửi thông điệp qua DirectChannel, nhận phản hồi, hiểu luồng thực thi và thiết kế cách xử lý lỗi.

Tình huống xuyên suốt là chuẩn hóa mã đơn hàng: ứng dụng gửi chuỗi `"  ord-009  "`, luồng tích hợp trả về `"ORD-009"`. Ví dụ nhỏ này giúp quan sát rõ vai trò của Message, MessageChannel, endpoint và Java DSL trước khi áp dụng cho luồng nghiệp vụ lớn hơn.

## 1. Mục tiêu và điều kiện thực hành

Sau bài học, bạn có thể:

- Chọn thao tác gửi một chiều hoặc yêu cầu–phản hồi.
- Giải thích handler chạy trên thread nào khi đầu vào là DirectChannel.
- Tạo luồng Java DSL và gọi luồng bằng MessagingTemplate.
- Phân biệt thời gian chờ nhận phản hồi với thời gian xử lý nghiệp vụ.
- Nhận diện lỗi thiếu subscriber, thiếu đường trả lời và dùng sai thao tác nhận.
- Viết kiểm thử cho phản hồi, header và đặc tính đồng bộ.

Các ví dụ dùng Java, Spring Integration Core và Spring Context; phần kiểm thử dùng JUnit Jupiter. Dự án cần khai báo `org.springframework.integration:spring-integration-core` và `org.junit.jupiter:junit-jupiter` cho test, với các phiên bản tương thích do cấu hình dependency của dự án quản lý. Không cần broker, máy chủ HTTP hay poller để chạy những luồng DirectChannel trong bài.

Hai chương trình minh họa là các ví dụ độc lập. Có thể đặt mỗi chương trình trong tệp Java mang tên public class tương ứng trong dự án thực hành. Ví dụ Java DSL dùng `AnnotationConfigApplicationContext` để hiển thị rõ quá trình đăng ký và khởi động endpoint.

## 2. Hai thành phần có trách nhiệm khác nhau

**MessagingTemplate** cung cấp API để mã ứng dụng gửi Message, gửi payload thông qua cơ chế chuyển đổi, hoặc gửi yêu cầu và lấy phản hồi. Nó không thay thế endpoint nghiệp vụ. [Tài liệu MessagingTemplate](https://docs.spring.io/spring-integration/reference/channel/template.html).

**DirectChannel** chuyển thông điệp tới subscriber ngay trên thread đang gọi gửi. Nó là một SubscribableChannel, không phải hàng đợi để bên nhận gọi `receive()`. Trong lần phân phối thành công, một handler được chọn xử lý thông điệp; channel không phát bản sao tới mọi subscriber. [Javadoc DirectChannel](https://docs.spring.io/spring-integration/api/org/springframework/integration/channel/DirectChannel.html).

| Thành phần | Trách nhiệm trong ví dụ chuẩn hóa |
|---|---|
| `Message<String>` | Mang chuỗi đầu vào và header theo dõi yêu cầu |
| `MessagingTemplate` | Gửi yêu cầu, quản lý thao tác chờ phản hồi |
| `DirectChannel` | Nối bên gửi tới endpoint trên cùng thread |
| Transformer endpoint | Bỏ khoảng trắng ở hai đầu, chuyển thành chữ hoa |
| Kênh trả lời | Đưa kết quả về lời gọi đang chờ |

Sơ đồ khái niệm của luồng:

~~~mermaid
flowchart LR
    A["Mã ứng dụng"] --> B["MessagingTemplate"]
    B --> C["DirectChannel: normalizeInput"]
    C --> D["Transformer endpoint"]
    D --> E["Kênh trả lời tạm"]
    E --> B
    B --> F["Message phản hồi"]
~~~

DirectChannel xác định cách chuyển tiếp tại điểm đó. Muốn biết toàn bộ luồng có đồng bộ hay không, phải xem cả các channel và endpoint phía sau.

### 2.1. Một subscriber không có nghĩa là chỉ một thread được phép gửi

Nếu hai thread ứng dụng cùng gọi `send()`, handler có thể được thực thi đồng thời bởi hai thread ấy. “Chạy trên thread người gửi” không đồng nghĩa với việc mọi yêu cầu được tuần tự hóa.

Với bài toán chuẩn hóa, lambda chỉ dùng dữ liệu cục bộ nên không có trạng thái dùng chung. Nếu thay lambda bằng service có một `ArrayList` thay đổi được dùng chung, thiết kế đó cần được xem xét lại về khả năng truy cập đồng thời.

### 2.2. Nhiều subscriber không tạo thành một pipeline

Giả sử đăng ký cả bước kiểm tra dữ liệu và bước lưu đơn hàng vào cùng một DirectChannel. Đây không phải cách biểu diễn “kiểm tra rồi lưu”.

Trong cấu hình mặc định, DirectChannel dùng round-robin để chọn handler; failover có thể thử handler khác nếu handler được chọn ném lỗi. Vì vậy một thông điệp có thể đi qua nhiều lần thử khi có lỗi, nhưng đây không phải broadcast hay chuỗi bước nghiệp vụ. [Triển khai message channel](https://docs.spring.io/spring-integration/reference/channel/implementations.html).

Để biểu diễn các bước bắt buộc, nối chúng theo thứ tự trong một IntegrationFlow. Nếu dùng failover cho các handler có side effect, cần cân nhắc trường hợp handler đầu đã thực hiện một phần công việc rồi mới thất bại.

## 3. Chọn đúng thao tác của MessagingTemplate

Import dùng trong bài là:

~~~java
import org.springframework.integration.core.MessagingTemplate;
~~~

Đây là template của Spring Integration, kế thừa GenericMessagingTemplate trong Spring Messaging. Có thể truyền channel mặc định qua constructor hoặc cấu hình default destination. [Javadoc MessagingTemplate](https://docs.spring.io/spring-integration/api/org/springframework/integration/core/MessagingTemplate.html).

| Thao tác | Đầu vào chính | Kết quả ở phía gọi |
|---|---|---|
| `send(channel, message)` | Message đã được tạo | Không trả Message phản hồi |
| `send(message)` | Message và channel mặc định | Như trên |
| `convertAndSend(channel, payload)` | Payload | Chuyển thành Message rồi gửi |
| `sendAndReceive(channel, request)` | Message yêu cầu | Message phản hồi hoặc `null` |
| `convertSendAndReceive(channel, payload, String.class)` | Payload và kiểu đích | Payload phản hồi kiểu String hoặc `null` |
| `receive(channel)` | Channel nhận được bằng cơ chế polling | Message hoặc `null` |

Với API template đang dùng, `send(...)` trả về `void`. Giá trị `boolean` thuộc về API `MessageChannel.send(...)`. Nếu việc gửi trả về `false`, template báo lỗi giao nhận; không có biến `boolean success = template.send(...)`. Đối chiếu chữ ký phương thức theo Javadoc của dependency khi gặp ví dụ tài liệu cũ. [API gửi của template](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/core/AbstractMessageSendingTemplate.html).

Các phương thức `convert...` sử dụng MessageConverter. Không nên suy ra rằng gọi `convertAndSend` luôn tuần tự hóa thành JSON; khả năng chuyển đổi phụ thuộc converter được cấu hình. Trong ví dụ String dưới đây, không cần thiết lập JSON converter.

### 3.1. Truyền channel trực tiếp hoặc dùng channel mặc định

Hai cách sau diễn đạt cùng đích gửi:

~~~java
DirectChannel input = new DirectChannel();
input.subscribe(message ->
        System.out.println(message.getPayload()));

MessagingTemplate explicit = new MessagingTemplate();
explicit.convertAndSend(input, "ord-009");

MessagingTemplate withDefault = new MessagingTemplate(input);
withDefault.convertAndSend("ord-010");
~~~

Đoạn mã giả định đã import DirectChannel và MessagingTemplate.

Một template được Spring quản lý cũng có thể phân giải tên channel thông qua cơ chế destination resolver. Khi dùng đối tượng tạo thủ công, truyền chính đối tượng channel là cách minh bạch để tránh phụ thuộc vào việc phân giải tên bean. [Mã nguồn MessagingTemplate](https://raw.githubusercontent.com/spring-projects/spring-integration/6.5.x/spring-integration-core/src/main/java/org/springframework/integration/core/MessagingTemplate.java).

Không thay đổi default channel của một template dùng chung cho từng yêu cầu. Nếu hai yêu cầu cần hai đích khác nhau, truyền channel trong lời gọi tương ứng.

## 4. Ví dụ gửi một chiều: quan sát cùng thread

Chương trình sau đăng ký MessageHandler trực tiếp. Handler chỉ in thông tin, không tạo phản hồi.

~~~java
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.core.MessagingTemplate;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

public class DirectSendDemo {

    public static void main(String[] args) {
        DirectChannel input = new DirectChannel();

        input.subscribe(message -> {
            System.out.println("handler thread = "
                    + Thread.currentThread().getName());
            System.out.println("payload = " + message.getPayload());
            System.out.println("requestId = "
                    + message.getHeaders().get("requestId"));
        });

        MessagingTemplate template = new MessagingTemplate(input);

        Message<String> request = MessageBuilder
                .withPayload("ord-009")
                .setHeader("requestId", "req-009")
                .build();

        System.out.println("before send, thread = "
                + Thread.currentThread().getName());

        template.send(request);

        System.out.println("after send");
    }
}
~~~

Khi chạy từ `main` thông thường, thứ tự đầu ra dự kiến là:

~~~text
before send, thread = main
handler thread = main
payload = ord-009
requestId = req-009
after send
~~~

Bạn có thể đặt breakpoint trong handler và quan sát call stack từ `main` tới `template.send(...)`, tới channel, rồi tới handler.

Từ ví dụ có thể rút ra ba điều:

1. Handler đã chạy xong trước khi dòng `after send` được thực hiện.
2. Gửi một chiều chỉ có nghĩa là bên gọi không yêu cầu nhận Message phản hồi.
3. Nếu handler làm việc chậm, bên gọi cũng phải đợi ở lời gọi gửi.

Không áp dụng kết luận “mọi công việc đã xong” cho luồng có bước chuyển sang executor hoặc hàng đợi ở phía sau. Khi đó call stack của người gửi có thể kết thúc trước công việc bất đồng bộ.

## 5. Ví dụ yêu cầu–phản hồi với Java DSL

Trong ví dụ này, ứng dụng cần lấy mã đã chuẩn hóa. Ta dùng transformer endpoint có đầu ra, thay cho MessageHandler chỉ ghi log ở mục trước.

Java DSL mô tả các thành phần của luồng và đăng ký chúng vào Spring context thông qua IntegrationFlow bean. Việc chỉ tạo một builder trong biến cục bộ không thay thế quá trình đăng ký endpoint. [Java DSL](https://docs.spring.io/spring-integration/reference/dsl.html).

~~~java
import java.util.Locale;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.core.MessagingTemplate;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

public class NormalizeFlowDemo {

    @Configuration
    @EnableIntegration
    public static class FlowConfig {

        @Bean
        public DirectChannel normalizeInput() {
            return new DirectChannel();
        }

        @Bean
        public IntegrationFlow normalizeFlow(
                @Qualifier("normalizeInput") DirectChannel input) {

            return IntegrationFlow.from(input)
                    .transform(String.class,
                            value -> value.trim()
                                    .toUpperCase(Locale.ROOT))
                    .get();
        }

        @Bean
        public MessagingTemplate normalizeTemplate(
                @Qualifier("normalizeInput") DirectChannel input) {

            MessagingTemplate template = new MessagingTemplate(input);
            template.setSendTimeout(1_000);
            template.setReceiveTimeout(1_000);
            return template;
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(FlowConfig.class)) {

            MessagingTemplate template = context.getBean(
                    "normalizeTemplate", MessagingTemplate.class);

            Message<String> request = MessageBuilder
                    .withPayload("  ord-009  ")
                    .setHeader("requestId", "req-009")
                    .build();

            Message<?> reply = template.sendAndReceive(request);

            if (reply == null) {
                throw new IllegalStateException(
                        "Không nhận được kết quả chuẩn hóa");
            }

            System.out.println("normalized = " + reply.getPayload());
            System.out.println("requestId = "
                    + reply.getHeaders().get("requestId"));

            String second = template.convertSendAndReceive(
                    "  si-core  ", String.class);

            if (second == null) {
                throw new IllegalStateException(
                        "Không nhận được phản hồi thứ hai");
            }

            System.out.println("second = " + second);
        }
    }
}
~~~

Bỏ qua log khởi động Spring, phần đầu ra nghiệp vụ dự kiến:

~~~text
normalized = ORD-009
requestId = req-009
second = SI-CORE
~~~

Overload `transform(String.class, ...)` cho biết kiểu dữ liệu mà lambda nhận. Lambda chỉ thực hiện phép biến đổi; endpoint transformer đảm nhiệm việc tạo và chuyển Message đầu ra. [API transformer trong Java DSL](https://docs.spring.io/spring-integration/api/org/springframework/integration/dsl/BaseIntegrationFlowDefinition.html).

Ví dụ sử dụng `Locale.ROOT` để quy tắc chuyển chữ hoa không phụ thuộc locale mặc định của máy chạy. Quy tắc nghiệp vụ ở đây chỉ là bỏ khoảng trắng hai đầu và chuyển chữ hoa; chưa bao gồm kiểm tra định dạng mã đơn hàng.

### 5.1. Vì sao không cần khai báo reply QueueChannel?

Template tạo một kênh trả lời tạm cho từng lần trao đổi và đưa địa chỉ trả lời vào Message yêu cầu. Endpoint cuối luồng có thể gửi kết quả về địa chỉ đó.

Với endpoint sinh đầu ra, output channel được cấu hình rõ có độ ưu tiên trước địa chỉ `replyChannel` trong header. Khi không có output channel, endpoint có thể sử dụng `replyChannel` để trả kết quả. [Quy tắc gửi phản hồi của endpoint](https://docs.spring.io/spring-integration/reference/service-activator.html).

Trong ví dụ, transformer là điểm cuối và không có output channel riêng nên kết quả quay về template. Không thêm một QueueChannel chứa kết quả rồi chờ template tự tìm đến đó.

Nếu quyết định gửi đầu ra sang một channel khác, thiết kế phải bảo đảm có đường chuyển tiếp kết quả về người gọi. Chỉ đưa kết quả vào một hàng đợi chưa hoàn tất hợp đồng yêu cầu–phản hồi.

### 5.2. Diễn biến của một lời gọi đồng bộ

~~~mermaid
sequenceDiagram
    participant App as Mã ứng dụng
    participant T as MessagingTemplate
    participant C as DirectChannel
    participant E as Transformer endpoint
    participant R as Kênh trả lời tạm

    App->>T: sendAndReceive(request)
    T->>T: Chuẩn bị địa chỉ trả lời
    T->>C: send(request có replyChannel)
    C->>E: handleMessage(request), cùng thread
    E->>E: trim và uppercase
    E->>R: Gửi Message kết quả
    E-->>C: Hoàn tất handler
    C-->>T: Hoàn tất gửi
    T->>R: Nhận phản hồi
    R-->>T: Message kết quả
    T-->>App: reply
~~~

Các participant biểu diễn thành phần, không biểu diễn các thread riêng. Trong luồng này, phản hồi đã được gửi vào kênh tạm trước khi template bắt đầu bước nhận.

Một `requestId` do ứng dụng đặt giúp đối chiếu yêu cầu với log và phản hồi. Nó không thay thế việc giữ đúng địa chỉ `replyChannel` của trao đổi. Khi tự xây Message mới ở giữa luồng, cần xem xét các header phải được truyền tiếp.

### 5.3. MessageHandler thông thường không tự tạo phản hồi

Hợp đồng của MessageHandler là `handleMessage(Message<?> message)` trả về `void`. Việc handler tính một chuỗi trong biến cục bộ không làm chuỗi ấy trở thành phản hồi.

Nếu cần biến đổi dữ liệu, dùng transformer như ví dụ. Nếu cần gọi một service nghiệp vụ có giá trị trả về, dùng endpoint service activator, chẳng hạn `.handle(service, "methodName")`. Endpoint đó chịu trách nhiệm chuyển kết quả phương thức thành đầu ra; nó khác việc chỉ `subscribe` một lambda ghi log.

## 6. Timeout giới hạn điều gì?

Cấu hình `setSendTimeout(...)` và `setReceiveTimeout(...)` dùng đơn vị mili giây. API cũng hỗ trợ timeout theo từng Message thông qua header tương ứng. [Javadoc cấu hình timeout](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/core/GenericMessagingTemplate.html).

| Cấu hình | Câu hỏi cần đặt khi đọc luồng |
|---|---|
| `sendTimeout` | Channel đích có thao tác chờ khi tiếp nhận thông điệp không? |
| `receiveTimeout` | Sau bước gửi, còn phải đợi bao lâu để lấy phản hồi? |

### 6.1. DirectChannel không cung cấp deadline cho handler

Trong triển khai GenericMessagingTemplate, bước gửi được thực hiện trước bước nhận phản hồi. Do đó `receiveTimeout` không ngắt handler đồng bộ đang chạy trong bước gửi. [Mã nguồn quá trình trao đổi](https://raw.githubusercontent.com/spring-projects/spring-framework/6.2.x/spring-messaging/src/main/java/org/springframework/messaging/core/GenericMessagingTemplate.java).

Ví dụ suy luận: thay transformer bằng lời gọi một hệ thống bên ngoài mất ba giây, đặt `receiveTimeout = 100` ms, và hệ thống đó trả kết quả thành công. Nếu toàn bộ đường đi vẫn đồng bộ, người gọi có thể chờ khoảng ba giây rồi nhận kết quả; không thể kỳ vọng template kết thúc sau 100 ms.

Tương tự, `sendTimeout` không biến lời gọi handler trên DirectChannel thành một tác vụ có cơ chế hủy sau deadline. Nếu service gọi HTTP hoặc cơ sở dữ liệu, cấu hình giới hạn thời gian phù hợp tại client hoặc tài nguyên đó.

Trong tình huống chuẩn hóa mã, thời gian tính toán rất ngắn. Khi thay bằng xử lý I/O, cần đánh giá lại mức chiếm dụng thread và giới hạn tài nguyên của phía gọi.

### 6.2. Handler kết thúc nhưng không có phản hồi

Nếu thay transformer bằng handler `void`, lời gọi gửi có thể hoàn tất nhưng bước nhận không có Message để trả về. Với timeout nhận hữu hạn, `sendAndReceive` có thể trả `null`. Bên gọi phải xử lý nhánh này trước khi truy cập payload.

Ví dụ tối giản, với channel đã có subscriber nhưng subscriber không gửi phản hồi:

~~~java
DirectChannel input = new DirectChannel();
input.subscribe(message -> {
    // Chỉ tiêu thụ thông điệp, không tạo phản hồi.
});

MessagingTemplate template = new MessagingTemplate(input);
template.setReceiveTimeout(0);

Message<?> reply = template.sendAndReceive(
        MessageBuilder.withPayload("ord-009").build());

// reply là null: handler đã chạy nhưng không có phản hồi.
~~~

Các import giống những ví dụ trước. Giá trị `0` yêu cầu bước nhận kiểm tra ngay, hữu ích để minh họa việc thiếu phản hồi mà không thêm thời gian chờ.

Khi thiết kế nghiệp vụ, quyết định rõ `null` biểu diễn trường hợp nào. Nếu “không có đơn hàng” là kết quả hợp lệ, nên trả một cấu trúc kết quả rõ ràng để phân biệt với “không có phản hồi của luồng”.

### 6.3. Chuyển sang bất đồng bộ không tự hủy công việc khi hết thời gian

Giả sử phía sau channel đầu vào có một bước đưa yêu cầu sang executor. Template có thể đợi phản hồi trong khi worker xử lý. Nếu bên gọi hết thời gian chờ, worker vẫn có thể tiếp tục và tạo side effect.

Đối với một lệnh thanh toán, việc tự động gửi lại chỉ vì không nhận phản hồi có thể tạo lệnh trùng. Khi mở rộng ví dụ sang nghiệp vụ có side effect, thiết kế requestId ổn định, kiểm tra trùng và chính sách thử lại phải đi cùng hợp đồng phản hồi.

## 7. Vì sao receive(DirectChannel) không đúng?

`receive(...)` lấy thông điệp từ đích hỗ trợ polling; nó không đăng ký một subscriber mới. DirectChannel chỉ chuyển tiếp đến subscriber đang có. Vì vậy có thể dùng nó làm channel yêu cầu của `sendAndReceive`, nhưng không dùng nó như một hàng đợi trả lời.

`receive` có thể trả `null` khi không nhận được thông điệp, và các biến thể `receiveAndConvert` lấy payload theo kiểu đích. [Hợp đồng nhận Message](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/core/MessageReceivingOperations.html).

Phân biệt hai câu hỏi:

- `sendAndReceive(input, request)`: gửi đến input, rồi lấy phản hồi qua cơ chế trao đổi của template.
- `receive(input)`: yêu cầu lấy một thông điệp đang chờ trên chính input.

Việc tham số có kiểu chung MessageChannel không bảo đảm mọi triển khai channel đều phù hợp với mọi thao tác. Khi cần bên nhận chủ động lấy thông điệp đang lưu, hãy cân nhắc QueueChannel và cơ chế tiêu thụ tương ứng.

## 8. Lỗi đồng bộ quay về người gọi như thế nào?

Với một luồng chạy trên thread người gọi qua DirectChannel, lỗi chưa được xử lý của endpoint truyền ngược qua call stack. Không thể chỉ thêm header `errorChannel` rồi mặc định rằng template sẽ nuốt lỗi và phát ErrorMessage. Cơ chế lỗi cho luồng bất đồng bộ phải được xem xét tại ranh giới thực thi tương ứng. [Xử lý lỗi trong Spring Integration](https://docs.spring.io/spring-integration/reference/error-handling.html).

Tại điểm gọi, có thể xử lý nhóm lỗi messaging:

~~~java
try {
    Message<?> reply = template.sendAndReceive(request);

    if (reply == null) {
        throw new IllegalStateException(
                "Luồng không trả kết quả cho req-009");
    }

    // Chỉ dùng reply.getPayload() sau khi kiểm tra null.
}
catch (org.springframework.messaging.MessagingException ex) {
    // Ghi nhận requestId và chuỗi nguyên nhân theo chính sách ứng dụng.
    // Để tầng gọi quyết định cách trả lỗi, không biến lỗi thành thành công.
    throw ex;
}
~~~

Đây là đoạn minh họa đặt trong phương thức đã có `template` và `request`. Lỗi nghiệp vụ có thể được bọc trong ngoại lệ messaging khi đi qua endpoint; cần xem chuỗi nguyên nhân thay vì chỉ tìm một loại exception nghiệp vụ ở lớp ngoài cùng.

| Hiện tượng | Điểm cần kiểm tra trước |
|---|---|
| Báo lỗi không có subscriber ngay khi gửi | Context đã khởi động chưa, endpoint có đăng ký đúng channel không? |
| Handler chạy nhưng người gọi nhận `null` | Handler có sinh đầu ra và có đường phản hồi không? |
| Kết quả nằm ở queue khác, người gọi vẫn đợi | Có chuyển tiếp từ queue đó về địa chỉ trả lời không? |
| Gọi `receive(input)` bị lỗi | Input có phải PollableChannel không? |
| Thời gian gọi lớn hơn receiveTimeout | Có công việc đồng bộ chậm trong bước gửi không? |
| Hai bước nghiệp vụ không cùng chạy | Có đăng ký cả hai làm subscriber cạnh tranh trên cùng DirectChannel không? |

Bảng là trình tự khoanh vùng cho các ví dụ trong bài, không thay thế việc đọc stack trace và cấu hình thực tế.

## 9. Transaction và thread cần được đọc cùng nhau

DirectChannel giữ việc gọi handler trên thread người gửi, tạo điều kiện để các thao tác dùng tài nguyên phù hợp tham gia transaction đang có. Channel không tự khởi tạo transaction chỉ vì tên của nó là DirectChannel.

Transaction của luồng do ứng dụng khởi tạo vẫn chịu cấu hình transaction thông thường của Spring. Ranh giới chuyển thread cần được xem xét lại vì transaction gắn với thread không tự lan sang worker mới. [Transaction trong message flow](https://docs.spring.io/spring-integration/reference/transactions.html).

Ví dụ thiết kế: một service có transaction hợp lệ gọi template để kiểm tra và ghi dữ liệu qua các bước đồng bộ. Nếu một bước lỗi, kết quả rollback còn phụ thuộc transaction manager, propagation, tài nguyên tham gia và quy tắc rollback.

Nếu bước cuối gọi dịch vụ vận chuyển bên ngoài, không nên suy ra rollback cơ sở dữ liệu cũng hoàn tác được yêu cầu đã gửi cho dịch vụ đó. Cần phân định side effect và cơ chế bù của nghiệp vụ.

## 10. Kiểm thử các hợp đồng quan trọng

Các kiểm thử dưới đây dùng JUnit Jupiter. Đặt chúng cùng package với `NormalizeFlowDemo` ở mục 5. Không cần Spring Boot hay broker cho các ca này.

~~~java
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.core.MessagingTemplate;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessagingException;
import org.springframework.messaging.support.MessageBuilder;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertThrows;

class MessagingTemplateDirectChannelTest {

    @Test
    void handlerRunsOnCallingThread() {
        DirectChannel input = new DirectChannel();
        AtomicReference<Thread> observed = new AtomicReference<>();
        input.subscribe(message ->
                observed.set(Thread.currentThread()));

        MessagingTemplate template = new MessagingTemplate(input);
        Thread caller = Thread.currentThread();

        template.send(MessageBuilder.withPayload("ord-009").build());

        assertSame(caller, observed.get());
    }

    @Test
    void dslFlowReturnsNormalizedPayloadAndRequestId() {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(
                             NormalizeFlowDemo.FlowConfig.class)) {

            MessagingTemplate template = context.getBean(
                    "normalizeTemplate", MessagingTemplate.class);

            Message<?> reply = template.sendAndReceive(
                    MessageBuilder.withPayload("  ord-009  ")
                            .setHeader("requestId", "req-009")
                            .build());

            assertNotNull(reply);
            assertEquals("ORD-009", reply.getPayload());
            assertEquals("req-009",
                    reply.getHeaders().get("requestId"));
        }
    }

    @Test
    void oneWayHandlerDoesNotProduceReply() {
        DirectChannel input = new DirectChannel();
        input.subscribe(message -> {
            // Không có đầu ra.
        });

        MessagingTemplate template = new MessagingTemplate(input);
        template.setReceiveTimeout(0);

        Message<?> reply = template.sendAndReceive(
                MessageBuilder.withPayload("ord-009").build());

        assertNull(reply);
    }

    @Test
    void channelWithoutSubscriberFailsToDeliver() {
        DirectChannel input = new DirectChannel();
        MessagingTemplate template = new MessagingTemplate(input);

        assertThrows(MessagingException.class,
                () -> template.send(
                        MessageBuilder.withPayload("ord-009").build()));
    }
}
~~~

Bốn ca kiểm thử tách biệt bốn hợp đồng: thread thực thi, giá trị phản hồi cùng header, trường hợp không có phản hồi, và thất bại giao nhận khi không có subscriber. Dùng lớp lỗi messaging chung ở ca cuối giúp kiểm tra hợp đồng thất bại mà không buộc nội dung log phải giống hệt giữa các phiên bản.

Không dùng `Thread.sleep(...)` để chờ endpoint trong những ca đồng bộ này. Nếu sau này thêm ranh giới bất đồng bộ, thay cách đồng bộ kiểm thử bằng cơ chế có điều kiện hoàn tất và giới hạn chờ phù hợp.

Các đoạn mã là ví dụ thực hành để chạy trong dự án của người học; bài viết không khẳng định chúng đã được biên dịch hoặc chạy trong một môi trường cụ thể.

## 11. Chọn MessagingTemplate hay gateway?

Nếu một lớp hạ tầng cần tự xây Message, thêm header và chọn channel, MessagingTemplate cho phép thể hiện các quyết định đó trực tiếp.

Nếu service nghiệp vụ chỉ cần một hợp đồng như `String normalize(String rawCode)`, messaging gateway có thể che API Message và channel sau một interface. [Messaging gateways](https://docs.spring.io/spring-integration/reference/gateway.html).

| Nhu cầu tại điểm gọi | Hướng thiết kế |
|---|---|
| Tạo Message và kiểm soát header trao đổi | MessagingTemplate |
| API nghiệp vụ theo phương thức có kiểu dữ liệu rõ | Messaging gateway |
| Các bước ngắn cần thực thi nối tiếp trên caller thread | DirectChannel trong luồng |
| Cần tiếp nhận dồn để xử lý sau | Xem xét QueueChannel và consumer tương ứng |
| Cần tách công việc khỏi caller thread | Xem xét ranh giới executor và hợp đồng lỗi/phản hồi |

Chọn template hoặc gateway không tự quyết định luồng đồng bộ hay bất đồng bộ. Quyết định đó còn nằm trong các channel và thành phần của luồng.

## 12. Thực hành mở rộng

Dùng luồng chuẩn hóa làm điểm xuất phát và thực hiện lần lượt:

1. Thêm một transformer kiểm tra mã rỗng sau khi `trim()`. Quy định rõ đầu vào không hợp lệ phải trả kết quả từ chối hay ném lỗi; không để người gọi hiểu nhầm là phản hồi bị mất.
2. Ghi `requestId` tại điểm vào và điểm kết thúc. Gửi hai yêu cầu có ID khác nhau rồi đối chiếu mỗi kết quả với đúng yêu cầu.
3. Thay endpoint cuối bằng một handler chỉ ghi log. Quan sát trường hợp `null` với timeout nhận hữu hạn và sửa điểm gọi cho phù hợp hợp đồng một chiều.
4. Đăng ký hai handler ghi tên khác nhau trên một DirectChannel độc lập và gửi nhiều thông điệp. Quan sát cách phân phối, sau đó viết lại thành IntegrationFlow nếu yêu cầu là cả hai bước phải chạy nối tiếp.
5. Thiết kế trên giấy việc thay một bước chuẩn hóa bằng gọi HTTP. Chỉ ra nơi đặt timeout I/O, nơi có thể đổi thread, và cách tránh side effect trùng khi bên gọi thử lại.

Tiêu chí hoàn thành: với mỗi lời gọi, bạn xác định được Message đi vào channel nào, endpoint nào xử lý, thread nào thực thi, kết quả quay về bằng đường nào và điều gì xảy ra nếu không có phản hồi.