# Request-reply flow

Trong chương **Mô hình message flow** của module **SPRING_INTEGRATION_CORE**, request-reply là mô hình trong đó bên gọi gửi một thông điệp yêu cầu và nhận lại kết quả tương ứng. Một lời gọi Java như `quoteGateway.quote(request)` có thể đi qua nhiều channel và endpoint trước khi trả về một đối tượng báo giá.

Bài học này kết nối `Message`, `MessageChannel`, endpoint, messaging gateway và Java DSL để giải thích đường đi đó. Các ví dụ dùng một dịch vụ tính báo giá trong bộ nhớ, sau đó mở rộng sang xử lý khác luồng, lỗi và kiểm thử. Mục tiêu là đọc được một flow và trả lời bốn câu hỏi: **ai gửi request, ai tạo reply, reply đi về đâu và caller kết thúc việc chờ bằng cách nào?**

## 1. Hợp đồng của một request-reply flow

Giả sử màn hình đặt hàng cần tính giá cho ba cuốn sách. Bên gọi gửi SKU và số lượng, còn flow trả về SKU đã chuẩn hóa cùng tổng tiền:

~~~text
QuoteRequest(" java-book ", 3)
              |
              v
     Chuẩn hóa -> Tính giá
              |
              v
QuoteReply("JAVA-BOOK", 360000)
~~~

Về nghiệp vụ, lời gọi này cần một kết quả cho mỗi yêu cầu hợp lệ. Về kỹ thuật, có ba kiểu kết thúc cần thiết kế rõ:

| Kiểu kết thúc | Ý nghĩa đối với caller | Ví dụ |
| --- | --- | --- |
| Có reply hợp lệ | Nhận được kết quả đúng hợp đồng | Một `QuoteReply` chứa tổng tiền |
| Có lỗi được truyền về | Không hoàn thành thao tác theo cách bình thường | SKU không tồn tại, dịch vụ tính giá bị lỗi |
| Hết thời gian chờ | Không nhận được kết quả trong khoảng chờ đã cấu hình | Worker bị chậm hoặc một nhánh không phát reply |

Hết thời gian chờ không chứng minh rằng request chưa được xử lý. Một thao tác có thể hoàn tất ở worker sau khi caller đã ngừng chờ. Với thao tác có tác dụng phụ như trừ tiền hoặc đặt chỗ, điều này ảnh hưởng trực tiếp đến quyết định thử lại.

Request-reply mô tả quan hệ giữa yêu cầu và phản hồi. Nó không bắt buộc phải dùng HTTP, broker, queue hay một thread riêng. Trong bài này, toàn bộ ví dụ cơ bản chạy trong cùng JVM.

### Phân biệt với gửi một chiều

Với thao tác gửi một chiều, caller không yêu cầu một kết quả nghiệp vụ từ flow. Một method gateway trả `void` có thể thể hiện hợp đồng đó. Tuy nhiên, `void` không tự tạo ra xử lý bất đồng bộ: nếu channel gọi handler trực tiếp, caller vẫn thực thi handler trên thread hiện tại.

Ngược lại, một gateway trả `QuoteReply` thể hiện rằng caller cần kết quả. Đừng nối một gateway như vậy đến một flow chỉ ghi log rồi kết thúc mà không có chính sách phản hồi.

## 2. Request đi vào và reply quay về như thế nào?

~~~mermaid
sequenceDiagram
    participant C as Caller
    participant G as Messaging gateway
    participant I as Request channel
    participant T as Transformer
    participant S as Service activator
    participant R as Reply channel tạm

    C->>G: quote(request)
    G->>I: Message<QuoteRequest> + replyChannel
    I->>T: Chuyển request
    T->>S: Request đã chuẩn hóa
    S->>R: Message<QuoteReply>
    R-->>G: Reply của lần gọi này
    G-->>C: QuoteReply
~~~

Gateway chuyển lời gọi method thành message. Trong cách dùng thông thường, gateway tạo một reply channel tạm cho lần trao đổi và đưa địa chỉ đó vào header `replyChannel`. Vì vậy, flow cơ bản không cần khai báo một bean reply channel riêng. Đây là cách triển khai mẫu **Return Address**: request mang theo địa chỉ để gửi kết quả về. [Messaging Gateways](https://docs.spring.io/spring-integration/reference/gateway.html)

Sơ đồ mô tả đường đi logic, không khẳng định có nhiều thread. Nếu các channel trong flow đều là `DirectChannel`, các lời gọi endpoint diễn ra trên thread của caller.

Một điểm cần phân biệt: `requestChannel.send(message)` chỉ là thao tác gửi. Giá trị boolean của `send` không phải payload của reply. Việc gửi rồi nhận kết quả cần gateway, `MessagingTemplate` hoặc một cơ chế nhận reply do ứng dụng tự quản lý.

## 3. Payload, return address và correlation

Một request trong ví dụ có thể được hình dung như sau:

~~~text
Message<QuoteRequest>
  payload:
    sku: " java-book "
    quantity: 3
  headers:
    id: UUID của message
    replyChannel: địa chỉ nhận kết quả
    requestId: "REQ-2026-001"       # header nghiệp vụ tự định nghĩa
~~~

Các header có vai trò khác nhau:

| Header | Câu hỏi mà nó trả lời | Cách dùng trong bài |
| --- | --- | --- |
| `id` | Đây là message instance nào? | Nhận diện message khi chẩn đoán |
| `replyChannel` | Gửi kết quả về đâu? | Đường quay về caller |
| `errorChannel` | Gửi thông điệp lỗi đến đâu khi cơ chế xử lý lỗi áp dụng? | Đường xử lý thất bại |
| `correlationId` | Message này thuộc nhóm/trao đổi nào theo quy ước đang dùng? | Hữu ích khi ghép nhóm hoặc trao đổi qua transport |
| `requestId` | Đây là yêu cầu nghiệp vụ nào? | Mã do ứng dụng định nghĩa để theo dõi |

`replyChannel` có thể chứa một đối tượng channel hoặc tên channel mà framework có thể phân giải. Không nên coi nó là một chuỗi luôn sẵn sàng đưa qua mạng. Payload và các header giá trị tùy biến cũng không mặc nhiên là bất biến sâu, dù cấu trúc `MessageHeaders` không cho sửa trực tiếp. [Message](https://docs.spring.io/spring-integration/reference/message.html)

Trong ví dụ, `requestId` là quy ước của ứng dụng, không phải một header đặc biệt tự kích hoạt việc đối chiếu reply. Tương tự, chỉ thêm `correlationId` vào hai message không làm một `QueueChannel` tự tìm đúng phản hồi cho từng caller.

## 4. Endpoint chọn nơi gửi reply như thế nào?

Với service activator thông thường trong bài, không cấu hình routing slip, có thể đọc đường trả lời theo thứ tự:

1. Nếu endpoint có output channel được cấu hình, kết quả đi đến output channel đó.
2. Nếu không có output channel, endpoint dùng `replyChannel` trên request.
3. Nếu request không có địa chỉ đó và kết quả trả về là một `Message`, framework có thể dùng `replyChannel` trên message kết quả.
4. Nếu endpoint đã tạo kết quả nhưng không phân giải được đích gửi, flow thất bại khi xác định nơi gửi reply.

Quy tắc này giải thích vì sao handler cuối flow chỉ cần trả về một POJO: framework tạo message kết quả và chuyển đến địa chỉ phù hợp. Khi handler trả `null` hoặc `void`, không có payload reply để chuyển tiếp; `requiresReply(true)` giúp biến tình huống thiếu kết quả thành lỗi tại endpoint yêu cầu reply. [Service Activator](https://docs.spring.io/spring-integration/reference/service-activator.html)

Ví dụ cấu hình dễ gây hiểu nhầm:

~~~text
Gateway -> Tính giá -> auditQueue
                         |
                         v
                    Chỉ lưu nhật ký
~~~

Endpoint tính giá đã gửi output vào `auditQueue`. Nếu consumer của queue chỉ ghi nhật ký rồi kết thúc, caller không nhận được báo giá. Khi cần quan sát message, hãy thiết kế nhánh quan sát riêng và giữ đường tạo reply tiếp tục về gateway. Nhánh quan sát cũng không nên vô tình phát thêm một reply nghiệp vụ.

## 5. Ví dụ đầy đủ: gateway và Java DSL tính báo giá

### 5.1. Điều kiện dùng ví dụ

Các lớp dưới đây dùng Java 17 và API Java DSL của Spring Integration 6.x. Mỗi khối có tên file tương ứng; đặt các file trong cùng package `example.requestreply` của một dự án học thử.

Classpath cần:

| Mục đích | Dependency |
| --- | --- |
| Message channel, endpoint, gateway và Java DSL | `org.springframework.integration:spring-integration-core` |
| Khởi tạo context Java | `org.springframework:spring-context` |
| Các ví dụ kiểm thử ở phần sau | `org.springframework:spring-test` và `org.junit.jupiter:junit-jupiter` |

Dùng bộ phiên bản Spring tương thích do BOM hoặc dependency management của dự án quản lý. Trong dự án Spring Boot, có thể dùng `spring-boot-starter-integration` và `spring-boot-starter-test` để cung cấp các thành phần tương ứng. Phần mã chính dưới đây khởi tạo context trực tiếp để thấy rõ cấu hình tối thiểu.

### 5.2. Đối tượng request và reply

**QuoteRequest.java**

~~~java
package example.requestreply;

public record QuoteRequest(String sku, int quantity) {
}
~~~

**QuoteReply.java**

~~~java
package example.requestreply;

import java.math.BigDecimal;

public record QuoteReply(String sku, BigDecimal total) {
}
~~~

Request và reply là hai kiểu dữ liệu riêng. Việc phân biệt này giúp caller biết chính xác đầu vào cần cung cấp và kết quả có thể nhận, thay vì dùng một `Map` chứa nhiều khóa không rõ hợp đồng.

### 5.3. Logic nghiệp vụ

**QuoteService.java**

~~~java
package example.requestreply;

import java.math.BigDecimal;

public class QuoteService {

    public QuoteReply quote(QuoteRequest request) {
        if (request.quantity() <= 0) {
            throw new IllegalArgumentException("Quantity must be positive");
        }

        BigDecimal unitPrice = switch (request.sku()) {
            case "JAVA-BOOK" -> new BigDecimal("120000");
            case "SI-BOOK" -> new BigDecimal("180000");
            default -> throw new IllegalArgumentException(
                    "Unknown SKU: " + request.sku());
        };

        BigDecimal total = unitPrice.multiply(
                BigDecimal.valueOf(request.quantity()));

        return new QuoteReply(request.sku(), total);
    }
}
~~~

Service là một POJO nhận request và trả reply. Nó không cần biết request đi qua channel nào. Trong ví dụ này, SKU không tồn tại là lỗi được truyền về caller; nếu sản phẩm cần trả một trạng thái nghiệp vụ như `NOT_FOUND`, hãy mở rộng kiểu reply và quy định rõ trường nào có giá trị cho từng trạng thái.

### 5.4. Interface gateway

**QuoteGateway.java**

~~~java
package example.requestreply;

import org.springframework.integration.annotation.Gateway;
import org.springframework.integration.annotation.MessagingGateway;

@MessagingGateway(defaultRequestChannel = "quoteRequests")
public interface QuoteGateway {

    @Gateway(requestTimeout = 500, replyTimeout = 1500)
    QuoteReply quote(QuoteRequest request);
}
~~~

Đơn vị của hai giá trị timeout là millisecond. Chúng được đặt tường minh để ví dụ không phụ thuộc vào mặc định. `@Gateway` cho phép cấu hình ở mức method; `requestTimeout` áp dụng cho việc gửi có thể bị chặn, còn `replyTimeout` áp dụng cho việc chờ phản hồi. [Gateway API](https://docs.spring.io/spring-integration/docs/current/api/org/springframework/integration/annotation/Gateway.html)

### 5.5. Cấu hình flow

**QuoteFlowConfig.java**

~~~java
package example.requestreply;

import java.util.Locale;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.config.IntegrationComponentScan;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
@IntegrationComponentScan(basePackageClasses = QuoteGateway.class)
public class QuoteFlowConfig {

    @Bean
    public MessageChannel quoteRequests() {
        return new DirectChannel();
    }

    @Bean
    public QuoteService quoteService() {
        return new QuoteService();
    }

    @Bean
    public IntegrationFlow quoteFlow(QuoteService quoteService) {
        return IntegrationFlow.from("quoteRequests")
                .<QuoteRequest, QuoteRequest>transform(request ->
                        new QuoteRequest(
                                request.sku() == null
                                        ? ""
                                        : request.sku().trim()
                                                .toUpperCase(Locale.ROOT),
                                request.quantity()))
                .handle(quoteService, "quote",
                        endpoint -> endpoint.requiresReply(true))
                .get();
    }
}
~~~

`@IntegrationComponentScan` tìm interface có `@MessagingGateway` và đăng ký proxy tương ứng. Chỉ dùng component scan thông thường không đủ để phát hiện các interface gateway theo cơ chế này. [MessagingGateway API](https://docs.spring.io/spring-integration/docs/current/api/org/springframework/integration/annotation/MessagingGateway.html)

Trong flow, transformer nhận `QuoteRequest`, tạo request mới với SKU được chuẩn hóa, rồi service activator gọi `QuoteService.quote`. Java DSL dùng `.handle(...)` để nối việc xử lý bằng POJO hoặc handler vào flow. [Service Activators and the .handle() method](https://docs.spring.io/spring-integration/reference/dsl/java-handle.html)

Cấu hình `requiresReply(true)` được đặt trên endpoint tính giá. Nó thể hiện yêu cầu: nếu method đã được gọi bình thường thì phải tạo kết quả. Nó không phải cơ chế theo dõi mọi nhánh trong toàn bộ flow. [GenericEndpointSpec API](https://docs.spring.io/spring-integration/docs/current/api/org/springframework/integration/dsl/GenericEndpointSpec.html)

Không có `.channel("someReplies")` ở cuối flow. Kết quả tính giá dùng return address của request để quay về gateway.

### 5.6. Gọi thử

**RequestReplyDemo.java**

~~~java
package example.requestreply;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class RequestReplyDemo {

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(QuoteFlowConfig.class)) {

            QuoteGateway gateway = context.getBean(QuoteGateway.class);

            QuoteReply reply = gateway.quote(
                    new QuoteRequest(" java-book ", 3));

            if (reply == null) {
                throw new IllegalStateException("No quote reply received");
            }

            System.out.println(reply.sku());
            System.out.println(reply.total());
        }
    }
}
~~~

Kết quả kỳ vọng:

~~~text
JAVA-BOOK
360000
~~~

Với đầu vào trên, thứ tự thực thi là:

1. Caller gọi proxy `QuoteGateway`.
2. Gateway tạo request message và return address.
3. `quoteRequests` chuyển request đến transformer.
4. Transformer đổi `" java-book "` thành `"JAVA-BOOK"`.
5. Service activator gọi POJO, tính `120000 × 3`.
6. Message chứa `QuoteReply` đi đến reply channel.
7. Proxy lấy payload và trả `QuoteReply` cho caller.

Nếu gọi với `quantity = 0`, service ném lỗi thay vì tạo báo giá. Nếu một lỗi lập trình khiến service trả `null`, endpoint đã cấu hình bắt buộc reply sẽ báo thiếu kết quả.

## 6. Dùng MessagingTemplate khi cần thao tác trực tiếp với Message

Gateway phù hợp khi lớp gọi muốn làm việc bằng interface nghiệp vụ. Khi cần quan sát headers hoặc gửi một `Message` tự xây dựng, có thể dùng `MessagingTemplate.sendAndReceive`. API này trả về reply message, vì vậy caller có thể đọc cả payload lẫn headers. [MessagingTemplate API](https://docs.spring.io/spring-integration/docs/current/api/org/springframework/integration/core/MessagingTemplate.html)

Ví dụ sau là một method có thể thêm vào lớp chạy thử; context được truyền vào là context đã khởi tạo ở phần trước:

~~~java
public static void callWithMessage(
        org.springframework.context.ApplicationContext context) {

    var requests = context.getBean(
            "quoteRequests", org.springframework.messaging.MessageChannel.class);

    var template =
            new org.springframework.integration.core.MessagingTemplate();
    template.setSendTimeout(500);
    template.setReceiveTimeout(1500);

    org.springframework.messaging.Message<QuoteRequest> request =
            org.springframework.messaging.support.MessageBuilder
                    .withPayload(new QuoteRequest(" si-book ", 2))
                    .setHeader("requestId", "REQ-2026-001")
                    .build();

    org.springframework.messaging.Message<?> reply =
            template.sendAndReceive(requests, request);

    if (reply == null) {
        throw new IllegalStateException("No reply for REQ-2026-001");
    }

    QuoteReply payload = (QuoteReply) reply.getPayload();
    System.out.println(payload.total()); // 360000
    System.out.println(reply.getHeaders().get("requestId"));
}
~~~

Ví dụ dùng chính đối tượng request channel lấy từ context, không phân giải channel bằng tên qua template. Template quản lý việc gửi và chờ reply cho lần trao đổi này.

Không thay `sendAndReceive` bằng `send` rồi mong nhận lại `QuoteReply`. Cũng không lấy giá trị trả về của `send` làm bằng chứng rằng dịch vụ đã xử lý thành công.

## 7. Thread và timeout: hai điều cần đọc riêng

### 7.1. DirectChannel giữ việc xử lý trên thread caller

Ở cấu hình cơ bản, `DirectChannel` gọi một subscriber trong thread gửi message. Việc chọn channel này phù hợp cho ví dụ nhỏ vì đường đi dễ theo dõi. Nó cũng có nghĩa là một lời gọi I/O chậm bên trong service có thể giữ thread caller trong thời gian dài. [Message Channel Implementations](https://docs.spring.io/spring-integration/reference/channel/implementations.html)

Giả sử một phiên bản khác của `QuoteService` gọi nhà cung cấp và lời gọi đó mất 5 giây:

~~~text
Thread caller:
  gateway.quote(...)
    -> DirectChannel.send(...)
      -> service.quote(...)       mất 5 giây
    <- send kết thúc
    -> gateway nhận reply
  <- method trả về
~~~

Không nên suy ra rằng `replyTimeout = 1500` sẽ ngắt `service.quote(...)` tại giây thứ 1,5. Đồng hồ chờ reply của gateway bắt đầu khi thread quay về gateway sau phần gửi, không phải một đồng hồ ngắt toàn bộ call stack kể từ lúc gửi request. [Gateway API](https://docs.spring.io/spring-integration/docs/current/api/org/springframework/integration/annotation/Gateway.html)

Vì vậy, timeout của HTTP client, JDBC hoặc tài nguyên downstream cần được cấu hình ở chính lớp truy cập tài nguyên. Giá trị timeout trên gateway không thay thế cho các giới hạn đó.

### 7.2. Request timeout và reply timeout giải quyết hai giai đoạn

| Thiết lập | Giai đoạn cần giới hạn | Không nên hiểu là |
| --- | --- | --- |
| `requestTimeout` | Chờ gửi request vào channel có thao tác gửi bị chặn | Ngân sách chạy tối đa của service |
| `replyTimeout` | Chờ reply sau giai đoạn gửi | Cơ chế tự hủy worker hoặc rollback nghiệp vụ |
| Timeout của client downstream | Chờ kết nối, đọc hoặc thực hiện thao tác theo API của client đó | Bằng chứng chắc chắn thao tác từ xa chưa xảy ra |

Một trường hợp dễ hình dung cho request timeout là `QueueChannel` có sức chứa hữu hạn và đã đầy. Với send có timeout, sender chờ đến khi có chỗ hoặc hết khoảng chờ. Queue chưa đầy chỉ xác nhận đã nhận message vào bộ đệm, không xác nhận kết quả tính giá đã tồn tại. [Message Channel Implementations](https://docs.spring.io/spring-integration/reference/channel/implementations.html)

Trong ví dụ đã cấu hình `500` và `1500` millisecond, không nên viết yêu cầu vận hành rằng “mọi lời gọi chắc chắn kết thúc trong 2 giây”. Các giai đoạn chạy đồng bộ trước khi chờ reply và các cơ chế downstream khác vẫn cần được tính vào ngân sách toàn bộ lời gọi.

### 7.3. Sau timeout, quyết định nghiệp vụ vẫn còn

Với một API tính giá chỉ đọc dữ liệu, caller có thể chọn thử lại theo chính sách tải. Với API tạo đơn hàng, thử lại cần đi kèm một mã yêu cầu có thể phát hiện xử lý trùng.

Một chính sách hoàn chỉnh nên quy định:

- Caller làm gì khi chưa biết kết quả.
- Có thể tra cứu trạng thái bằng mã nghiệp vụ nào.
- Kết quả đến muộn được quan sát hoặc xử lý ra sao.
- Điều kiện nào cho phép thử lại thao tác có tác dụng phụ.

Đây là quyết định của ứng dụng; chỉ đặt `replyTimeout` không tạo ra các quy tắc trên.

## 8. Chuyển xử lý sang worker mà vẫn giữ request-reply

Có thể thay bean `quoteRequests` hiện có bằng `ExecutorChannel` dùng một executor do Spring quản lý. Phần transformer và service activator không cần thay đổi.

**Các bean thay thế/bổ sung trong QuoteFlowConfig:**

~~~java
@Bean
public org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor
        quoteExecutor() {

    var executor =
            new org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor();
    executor.setCorePoolSize(2);
    executor.setMaxPoolSize(4);
    executor.setQueueCapacity(20);
    executor.setThreadNamePrefix("quote-worker-");
    return executor;
}

@Bean
public MessageChannel quoteRequests(
        org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor
                quoteExecutor) {

    return new org.springframework.integration.channel.ExecutorChannel(
            quoteExecutor);
}
~~~

Thay bean channel cũ, không giữ đồng thời hai bean cùng tên `quoteRequests`. Vì executor là Spring bean, container quản lý việc khởi tạo và vòng đời của nó.

Đường thực thi thông thường lúc này là:

~~~text
Caller thread: tạo request -> giao cho executor -> chờ reply
Worker thread:                         chuẩn hóa -> tính giá -> gửi reply
Caller thread:                                               nhận kết quả
~~~

Caller vẫn dùng method trả `QuoteReply` nên vẫn chờ kết quả. Việc có worker thread không biến hợp đồng đó thành gửi một chiều.

`ExecutorChannel` phân phối công việc qua executor; các chính sách executor có thể ảnh hưởng đến thread thực thi. Cũng không nên giả định transaction trên thread caller tự bao phủ phần xử lý ở worker. [Message Channel Implementations](https://docs.spring.io/spring-integration/reference/channel/implementations.html)

Nếu thay bằng `QueueChannel`, cần thiết kế consumer cho pollable channel, thường là endpoint có poller. Đổi channel thành queue mà không có consumer hoạt động chỉ làm request nằm chờ. Ngoài ra, queue trong bộ nhớ không tự cung cấp độ bền qua lần khởi động lại.

Khi nhu cầu của caller là nhận một handle để đợi kết quả sau, có thể nghiên cứu gateway với `Future` hoặc `CompletableFuture`. Cần phân biệt hai quyết định: **flow dùng worker để xử lý** và **API của caller trả kết quả theo kiểu bất đồng bộ**.

## 9. Hai request đồng thời có cần chung một reply queue?

Giả sử có hai yêu cầu:

~~~text
Request A: JAVA-BOOK, quantity = 1
Request B: SI-BOOK,   quantity = 2
~~~

Nếu B hoàn tất trước A, thứ tự hoàn tất khác thứ tự gửi. Với một reply queue tự dựng dùng chung và hai caller cùng gọi `receive()`, caller đang chờ A có thể lấy nhầm kết quả của B nếu không có cơ chế đối chiếu.

Thiết kế cần giải quyết cả ba việc:

1. Đặt một mã tương quan vào request.
2. Đưa mã đó vào reply theo hợp đồng.
3. Có dispatcher hoặc registry chuyển reply đến đúng lần gọi đang chờ.

Trong flow nội bộ cơ bản ở trên, nên để gateway quản lý return address cho từng lần trao đổi thay vì tự tạo một queue chung. Tên bean `defaultReplyChannel` là cấu hình của gateway, không nên suy diễn nó hoạt động giống một queue mà mọi caller tự lấy phần tử đầu tiên.

Khi request đi qua HTTP, JMS hoặc một broker khác, transport adapter/gateway cần chuyển đổi địa chỉ và metadata theo giao thức tương ứng. Không gửi trực tiếp một channel object nội bộ qua mạng rồi kỳ vọng JVM khác sử dụng được nó. Khi đó cần đọc thêm hợp đồng request-reply của chính transport đang dùng.

## 10. Transformer, filter, router và aggregator ảnh hưởng thế nào đến reply?

Mục tiêu của request-reply không chỉ là “có một endpoint cuối trả dữ liệu”. Mỗi nhánh có thể kết thúc xử lý đều phải có ý nghĩa đối với caller.

| Thành phần trong flow | Tình huống cần chú ý | Quyết định thiết kế cho flow báo giá |
| --- | --- | --- |
| Transformer | Tạo message tùy biến nhưng làm mất metadata cần cho đường về | Giữ các header cần thiết; dùng phép biến đổi payload thông thường khi phù hợp |
| Filter | Loại request và không tạo kết quả | Chọn ném lỗi từ chối hoặc có nhánh tạo một reply nghiệp vụ |
| Router | Một loại request không đi đến nhánh tạo reply | Quy định rõ nhánh xử lý và kết quả cho từng loại |
| Splitter + aggregator | Một request sinh nhiều message nhưng nhóm chưa đủ điều kiện release | Xác định correlation, release và xử lý nhóm thiếu phần tử |
| Handler cuối | Chỉ ghi dữ liệu/log rồi trả `void` | Dùng gửi một chiều hoặc bổ sung một kết quả đúng hợp đồng |

### Filter không đồng nghĩa với một reply “bị từ chối”

Một filter có thể bỏ message. Muốn việc loại bỏ trở thành lỗi đối với caller, có thể cấu hình `throwExceptionOnRejection(true)`. Muốn trả kết quả nghiệp vụ “không đủ điều kiện”, nhánh loại bỏ phải có endpoint tạo kết quả đó. Chỉ cấu hình discard channel chưa đảm bảo sẽ có reply. [Filter](https://docs.spring.io/spring-integration/reference/filter.html)

Ví dụ quyết định ở mức thiết kế:

~~~text
Yêu cầu báo giá
  -> Kiểm tra quyền
       -> Cho phép: tính giá -> QuoteReply
       -> Từ chối: tạo QuoteDecision(REJECTED, lý do)
~~~

Nếu chọn thiết kế này, gateway phải trả kiểu dữ liệu chứa được cả hai kết quả, chẳng hạn `QuoteDecision`. Không thể giữ chữ ký `QuoteReply quote(...)` rồi tùy ý trả một kiểu lỗi không tương thích.

### Router cần được đọc theo từng đường đi

Với router phân loại khách hàng thường và khách hàng ưu tiên, hãy lần theo cả hai nhánh đến nơi tạo reply. Các cấu hình mapping, resolution và default output phụ thuộc loại router; cần xem tài liệu đúng router thay vì giả định mọi trường hợp không match đều có cùng hành vi. [Router Implementations](https://docs.spring.io/spring-integration/reference/router/implementations.html)

### Aggregator có thời gian chờ của nhóm

Aggregator giữ các message có liên quan và phát kết quả khi điều kiện release được đáp ứng. Nó có correlation strategy và release strategy; vì vậy “đã xử lý xong một nhánh” chưa có nghĩa là “đã có reply cho request gốc”. [Aggregator](https://docs.spring.io/spring-integration/reference/aggregator.html)

Nếu một báo giá tổng hợp cần kết quả từ ba nguồn nhưng chỉ có hai nguồn phản hồi, phải quyết định trả kết quả một phần, trả lỗi hay tiếp tục chờ theo thời hạn của nhóm. Ngân sách đó cần phù hợp với thời gian caller sẵn sàng chờ.

## 11. Lỗi là một đường kết thúc cần thiết kế

Phân biệt rõ:

- **Lỗi xử lý:** endpoint ném exception.
- **Thiếu kết quả:** không có reply được tạo hoặc không tới nơi đang chờ.
- **Hết khoảng chờ:** caller dừng chờ theo cấu hình.
- **Kết quả nghiệp vụ âm:** có một reply hợp lệ, chẳng hạn `REJECTED`.

Trong flow chạy cùng thread, exception có thể lan theo call stack. Với xử lý khác thread, không thể dùng call stack của worker để ném trực tiếp vào caller; framework dùng cơ chế message lỗi khi thích hợp. Khi cơ chế phát lỗi bất đồng bộ hoạt động, header `errorChannel` của request được ưu tiên, sau đó mới đến kênh lỗi toàn cục. Không nên suy ra rằng mọi exception trong một flow đồng bộ đều tự được gửi đến bean `errorChannel`. [Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html)

Trong ví dụ hiện tại, không cấu hình error flow chuyển đổi lỗi thành kết quả. Caller cần xử lý lỗi nghiệp vụ như `IllegalArgumentException` từ dịch vụ; khi chẩn đoán cũng cần biết framework có thể bọc lỗi và gắn message thất bại.

Nếu muốn gateway gửi lỗi vào một flow chuyên biệt, thuộc tính annotation là `errorChannel`, ví dụ `@MessagingGateway(defaultRequestChannel = "quoteRequests", errorChannel = "quoteErrors")`. Flow đó cần quyết định trả một kết quả tương thích hoặc để lỗi tiếp tục được báo cho caller. [MessagingGateway API](https://docs.spring.io/spring-integration/docs/current/api/org/springframework/integration/annotation/MessagingGateway.html)

Một error handler chỉ ghi log rồi trả `null` không tự trở thành phản hồi nghiệp vụ. Đặc biệt, không dùng một báo giá bằng 0 để che mọi lỗi kỹ thuật: caller có thể diễn giải nhầm đó là giá thật.

Khi API cần bắt buộc báo lỗi nếu hết thời gian chờ reply, Spring Integration từ 6.2 hỗ trợ `errorOnTimeout` trên `@MessagingGateway`. Cần kiểm tra phiên bản đang dùng và vẫn nhớ rằng tùy chọn này không phải cơ chế ngắt downstream đang chạy đồng bộ.

## 12. Gọi một request-reply subflow bằng .gateway()

Ngoài gateway interface ở biên ứng dụng, Java DSL có operator `.gateway(...)` để một flow gọi flow khác qua input channel và nhận reply. Kết quả từ flow được gọi trở thành đầu vào cho bước tiếp theo của flow gọi. [Operator gateway()](https://docs.spring.io/spring-integration/reference/dsl/java-gateway.html)

Ví dụ dưới đây thêm một flow trả riêng tổng tiền. Nó tái sử dụng `quoteRequests` và dịch vụ báo giá đã có:

~~~java
@Bean
public IntegrationFlow quoteTotalFlow() {
    return IntegrationFlow.from("quoteTotalRequests")
            .gateway("quoteRequests",
                    gateway -> gateway
                            .requestTimeout(500L)
                            .replyTimeout(1500L))
            .<QuoteReply, java.math.BigDecimal>transform(QuoteReply::total)
            .get();
}
~~~

Đầu vào `quoteTotalRequests` vẫn là `QuoteRequest`, đầu ra nghiệp vụ của flow này là `BigDecimal`. Caller có thể gọi flow mới bằng một gateway có kiểu trả về `BigDecimal` hoặc bằng `MessagingTemplate`.

So sánh mục đích:

| Cách nối | Ý nghĩa trong thiết kế |
| --- | --- |
| `.channel("quoteRequests")` | Chuyển message sang channel tiếp theo |
| `.gateway("quoteRequests")` | Thực hiện trao đổi với flow đích rồi xử lý reply tại bước tiếp theo |

Return address của trao đổi bên trong và đường về caller bên ngoài là hai tầng cần giữ đúng. Dùng operator gateway khi cần quan hệ “gọi flow con rồi tiếp tục”; không tự thay header reply của flow ngoài bằng một channel cố định.

## 13. Minh họa kiểm thử hợp đồng request-reply

Các đoạn kiểm thử sau dành cho người học đưa vào dự án thực hành. Chúng dùng JUnit Jupiter và Spring Test; không cần HTTP server hay broker.

**QuoteFlowTest.java**

~~~java
package example.requestreply;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.integration.core.MessagingTemplate;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.ContextConfiguration;
import org.springframework.test.context.junit.jupiter.SpringExtension;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;

@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = QuoteFlowConfig.class)
class QuoteFlowTest {

    @Autowired
    QuoteGateway gateway;

    @Autowired
    org.springframework.context.ApplicationContext context;

    @Test
    void normalizesSkuAndReturnsQuoteToCaller() {
        QuoteReply reply = gateway.quote(
                new QuoteRequest(" java-book ", 3));

        assertNotNull(reply);
        assertEquals("JAVA-BOOK", reply.sku());
        assertEquals(0,
                new BigDecimal("360000").compareTo(reply.total()));
    }

    @Test
    void reportsInvalidQuantityToCaller() {
        assertThrows(IllegalArgumentException.class,
                () -> gateway.quote(
                        new QuoteRequest("JAVA-BOOK", 0)));
    }

    @Test
    void returnsPayloadAndPreservesBusinessRequestId() {
        MessageChannel requests = context.getBean(
                "quoteRequests", MessageChannel.class);

        MessagingTemplate template = new MessagingTemplate();
        template.setSendTimeout(500);
        template.setReceiveTimeout(1500);

        Message<QuoteRequest> request = MessageBuilder
                .withPayload(new QuoteRequest(" si-book ", 2))
                .setHeader("requestId", "REQ-001")
                .build();

        Message<?> reply = template.sendAndReceive(requests, request);

        assertNotNull(reply);
        QuoteReply payload =
                assertInstanceOf(QuoteReply.class, reply.getPayload());

        assertEquals("SI-BOOK", payload.sku());
        assertEquals(0,
                new BigDecimal("360000").compareTo(payload.total()));
        assertEquals("REQ-001",
                reply.getHeaders().get("requestId"));
    }
}
~~~

Ba ví dụ kiểm tra các kết quả mà caller quan sát được: dữ liệu chuẩn hóa đúng, lỗi được báo về và metadata nghiệp vụ cần thiết còn tồn tại. Đây là những điều quan trọng hơn việc chỉ kiểm tra một endpoint đã được gọi.

Khi flow phát triển, bổ sung các tình huống theo thay đổi thực tế:

| Tình huống | Điều cần xác minh |
| --- | --- |
| Filter từ chối | Caller nhận đúng lỗi hoặc reply từ chối đã quy định |
| Router có nhiều nhánh | Mỗi nhánh hợp lệ đều kết thúc theo hợp đồng |
| Service có thể trả `null` | Endpoint bắt buộc reply báo lỗi |
| Hai request xử lý đồng thời | Kết quả thuộc đúng request |
| Worker không phát reply | Caller kết thúc chờ theo chính sách timeout |
| Worker hoàn tất muộn | Ứng dụng xử lý được trạng thái chưa rõ kết quả |
| Aggregator thiếu phần tử | Có chính sách hết hạn nhóm và kết quả cho caller |

Với kiểm thử timeout hoặc thứ tự hoàn tất, nên điều khiển worker bằng latch hoặc tín hiệu đồng bộ để tạo tình huống xác định, thay vì chỉ dựa vào `Thread.sleep`. Spring Integration còn có bộ công cụ riêng để mock endpoint và kiểm thử từng đoạn hoặc cả flow. [Testing support](https://docs.spring.io/spring-integration/reference/testing.html)

## 14. Chẩn đoán một lời gọi chờ quá lâu

Bắt đầu từ triệu chứng quan sát được ở caller, rồi lần theo request:

| Triệu chứng | Điểm cần kiểm tra trước |
| --- | --- |
| Method gateway không được inject | Scan interface gateway và phạm vi package |
| Gửi vào direct channel báo không có subscriber | Flow có được đăng ký và endpoint có hoạt động không |
| Service chạy nhưng caller không nhận reply | Output channel cuối và đường về qua `replyChannel` |
| Chỉ một số đầu vào hết thời gian chờ | Nhánh router, filter hoặc điều kiện release của aggregator |
| Có request trong queue nhưng không thấy service chạy | Consumer, poller và trạng thái endpoint |
| `replyTimeout` nhỏ nhưng method vẫn chạy lâu | Có đoạn downstream đang giữ thread caller không |
| Chỉ thấy log lỗi, caller vẫn chờ | Error flow có tạo kết quả hoặc báo lỗi về caller không |
| Sai kết quả giữa các lời gọi | Reply queue dùng chung, correlation và dispatcher tự viết |
| Thử lại tạo dữ liệu trùng | Hợp đồng idempotency và trạng thái xử lý sau timeout |

Có thể ghi lại `requestId`, tên endpoint và thread tại những điểm quan trọng. Trong ví dụ báo giá, ba điểm có ích là trước gateway, khi bắt đầu tính giá và khi caller nhận kết quả. Các điểm đó giúp phân biệt thời gian xếp hàng, thời gian xử lý và thời gian chờ.

Đừng bắt đầu bằng cách tăng mọi timeout. Nếu một filter đã loại message mà không có reply, tăng thời gian chờ chỉ làm lỗi thiết kế xuất hiện chậm hơn.

## 15. Thực hành mở rộng

1. Thêm SKU `"SPRING-BOOK"` với giá `150000` và xác nhận request mua hai cuốn trả tổng `300000`.
2. Định nghĩa một reply nghiệp vụ chứa trạng thái `QUOTED` hoặc `REJECTED`; cập nhật đồng bộ service, gateway và assertion của caller.
3. Thay request channel bằng `ExecutorChannel` và ghi tên thread để quan sát ranh giới caller/worker.
4. Thiết kế một filter giới hạn số lượng đặt mua; chọn rõ cách caller nhận kết quả khi request bị từ chối.
5. Tạo hai request có thời gian xử lý khác nhau và xác nhận mỗi caller nhận đúng SKU của mình.
6. Vẽ một flow lấy giá từ nhiều nguồn, nêu correlation key, điều kiện release và cách trả lời khi một nguồn không phản hồi.

Sau các bài thực hành, hãy tự lần theo một request bất kỳ từ gateway đến endpoint cuối. Tại mỗi bước, xác định payload hiện tại, metadata cần giữ, thread thực thi và đường kết thúc cho cả thành công lẫn thất bại. Đó là nền tảng để ghép các mẫu tích hợp lớn hơn mà vẫn duy trì hợp đồng rõ ràng với caller.
