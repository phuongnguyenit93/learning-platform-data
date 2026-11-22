# Handler endpoint

## Mục tiêu bài học

Trong Spring Integration Core, handler là thành phần thực hiện công việc khi một message đi đến điểm xử lý: gọi nghiệp vụ, chuyển đổi dữ liệu, ghi ra hệ thống đích hoặc tạo reply. Hiểu handler giúp bạn thiết kế đúng sự kết hợp giữa `Message`, `MessageChannel`, endpoint và gateway, thay vì dồn mọi hành vi vào một callback nhận message.

Sau bài học này, bạn có thể:

- Phân biệt `MessageHandler`, consumer endpoint và service activator.
- Chọn cách xử lý một chiều hoặc có phản hồi.
- Khai báo handler bằng annotation và Java DSL.
- Giải thích luồng reply, thread thực thi và lỗi tại handler.
- Kiểm thử hành vi nghiệp vụ cùng cách handler tham gia một integration flow.

## 1. Handler nằm ở đâu trong một endpoint?

Xét luồng tiếp nhận yêu cầu lập hóa đơn:

```text
Ứng dụng gọi gateway
        |
        v
invoiceRequests (MessageChannel)
        |
        v
Consumer endpoint
        |
        v
Handler gọi InvoiceProcessor.process(...)
        |
        v
Message phản hồi -> replyChannel -> gateway -> ứng dụng
```

Một **consumer endpoint** kết nối kênh đầu vào với logic xử lý. **Handler** là đối tượng được endpoint gọi khi nhận được message. Một endpoint có thể sử dụng handler do bạn viết trực tiếp hoặc handler do Spring Integration tạo ra để gọi một phương thức POJO.

Ba lớp trách nhiệm cần tách biệt:

| Thành phần | Trách nhiệm chính | Ví dụ |
| --- | --- | --- |
| Message channel | Chuyển hoặc lưu giữ message theo đặc tính của kênh | `DirectChannel`, `QueueChannel` |
| Consumer endpoint | Gắn handler với đầu vào và quản lý hoạt động tiêu thụ | `EventDrivenConsumer`, `PollingConsumer` |
| Message handler | Thực hiện hành vi xử lý đối với message | `ServiceActivatingHandler`, một implementation của `MessageHandler` |

Với một `SubscribableChannel` như `DirectChannel`, endpoint thường đăng ký handler để nhận message khi có lệnh gửi. Với một `PollableChannel` như `QueueChannel`, endpoint cần poller để lấy message rồi chuyển cho handler.

Vì vậy, “handler endpoint” trong bài này là điểm xử lý message được cấu thành từ consumer endpoint và handler của nó. Không nên hiểu rằng mọi đối tượng `MessageHandler` tự có khả năng đăng ký kênh, lập lịch polling hoặc quản lý vòng đời đầy đủ.

## 2. Hợp đồng `MessageHandler`

Interface nền tảng có một phương thức không trả về giá trị:

```java
package org.springframework.messaging;

public interface MessageHandler {
    void handleMessage(Message<?> message) throws MessagingException;
}
```

Handler nhận toàn bộ message, bao gồm payload và headers. Một implementation đơn giản có thể ghi log:

```java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHandler;

public class AuditHandler implements MessageHandler {

    @Override
    public void handleMessage(Message<?> message) {
        System.out.println("Payload: " + message.getPayload());
        System.out.println("Message id: " + message.getHeaders().getId());
    }
}
```

Đây là handler kết thúc một nhánh xử lý: nó thực hiện tác dụng phụ và không tạo reply thông qua giá trị trả về.

Điểm dễ nhầm là Spring Integration vẫn hỗ trợ request–reply dù `handleMessage(...)` có kiểu trả về `void`. Các handler hỗ trợ reply thực hiện việc gửi message phản hồi bên trong quá trình xử lý. Chẳng hạn, `ServiceActivatingHandler` gọi phương thức nghiệp vụ, lấy kết quả rồi chuyển kết quả đó thành đầu ra của flow.

```text
MessageHandler.handleMessage(message): void
        |
        +-- gọi nghiệp vụ -> kết quả
        |
        +-- gửi message chứa kết quả tới kênh đầu ra/replyChannel
```

Không thể biến một raw `MessageHandler` thành handler trả lời chỉ bằng cách cấu hình `outputChannel` ở một nơi khác. Handler hoặc cơ chế bao quanh nó phải thực sự có khả năng tạo và gửi reply.

## 3. Service activator: đưa phương thức nghiệp vụ vào flow

Service activator là lựa chọn thông dụng khi muốn gọi một phương thức Java từ luồng message. Spring Integration tạo adapter để nối mô hình messaging với phương thức nghiệp vụ.

Ví dụ phương thức nghiệp vụ:

```java
public InvoiceResult process(InvoiceRequest request) {
    // Kiểm tra yêu cầu và thực hiện nghiệp vụ.
    return new InvoiceResult(request.orderId(), "ACCEPTED");
}
```

Khi được gắn vào service activator:

1. Handler nhận `Message<?>` từ endpoint.
2. Framework xác định phương thức cần gọi và ánh xạ đối số.
3. Phương thức được thực thi với payload hoặc thông tin message cần thiết.
4. Kết quả khác `null` được dùng để tạo reply.
5. Reply được gửi theo cấu hình đầu ra.

Handler không chỉ dùng để gọi HTTP hoặc ghi cơ sở dữ liệu. Nó cũng có thể điều phối một bước nghiệp vụ trong bộ nhớ. Tuy nhiên, nếu ý định là chuyển đổi, định tuyến, lọc hoặc gom nhóm message, nên dùng endpoint thể hiện đúng mẫu tích hợp tương ứng.

| Ý định của bước xử lý | Cấu trúc thường phù hợp |
| --- | --- |
| Gọi dịch vụ nghiệp vụ và lấy kết quả | Service activator, `.handle(...)` |
| Chuyển payload từ dạng này sang dạng khác | Transformer, `.transform(...)` |
| Chọn kênh tiếp theo theo nội dung | Router, `.route(...)` |
| Chấp nhận hoặc loại bỏ message theo điều kiện | Filter, `.filter(...)` |
| Gom nhiều message thành một kết quả | Aggregator, `.aggregate(...)` |
| Ghi nhận hoặc gửi ra hệ thống đích, không cần reply | Handler một chiều hoặc outbound channel adapter |

Một phương thức Java có thể làm nhiều việc trong bảng, nhưng việc sử dụng đúng endpoint giúp người đọc hiểu ngữ nghĩa, cấu hình và kỳ vọng kiểm thử của flow.

## 4. Ánh xạ payload và headers vào phương thức

Phương thức xử lý không bắt buộc phải nhận `Message<?>`. Có thể chỉ khai báo dữ liệu mà nghiệp vụ thực sự cần.

### 4.1. Chỉ nhận payload

```java
public InvoiceResult process(InvoiceRequest request) {
    return new InvoiceResult(request.orderId(), "ACCEPTED");
}
```

Cách này giữ lớp nghiệp vụ ít phụ thuộc vào messaging. Nếu payload đã đúng kiểu, việc đọc và kiểm thử phương thức khá trực tiếp. Không nên kỳ vọng mọi payload bất kỳ đều tự chuyển thành kiểu đích; chuyển đổi phụ thuộc bộ chuyển đổi, cấu hình và dữ liệu đầu vào.

### 4.2. Nhận payload cùng một header

```java
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.messaging.handler.annotation.Payload;

public InvoiceResult process(
        @Payload InvoiceRequest request,
        @Header(name = "tenantId", required = false) String tenantId) {

    String effectiveTenant = tenantId == null ? "default" : tenantId;
    return new InvoiceResult(
            request.orderId(),
            "ACCEPTED_FOR_" + effectiveTenant);
}
```

Nếu một header bắt buộc bị thiếu, việc giải quyết đối số có thể thất bại trước khi thân phương thức chạy. Với header tùy chọn, dùng kiểu đối số có thể nhận `null`, tránh primitive khi không có giá trị mặc định phù hợp.

### 4.3. Nhận toàn bộ message

```java
import org.springframework.messaging.Message;

public InvoiceResult process(Message<InvoiceRequest> message) {
    InvoiceRequest request = message.getPayload();
    Object correlationId = message.getHeaders().get("correlationId");

    // correlationId có thể dùng để ghi log/truy vết nếu ứng dụng cung cấp.
    return new InvoiceResult(request.orderId(), "ACCEPTED");
}
```

Nhận toàn bộ message phù hợp khi logic xử lý cần quan sát nhiều headers hoặc điều khiển thông tin phản hồi. Đổi lại, lớp xử lý phụ thuộc trực tiếp vào Spring Messaging.

Nếu lớp có nhiều phương thức hoặc nhiều overload, chỉ định rõ tên phương thức trong DSL và giữ chữ ký dễ phân giải. Việc gọi đúng phương thức còn phụ thuộc kiểu payload và cách ánh xạ đối số; không nên dùng overload phức tạp như một cơ chế định tuyến ngầm.

## 5. Ví dụ request–reply với annotation và gateway

Ví dụ dưới đây nhận yêu cầu lập hóa đơn và trả lại một kết quả chấp nhận. Nó chưa thực hiện lưu hóa đơn, gọi dịch vụ ngoài hoặc bảo đảm chống trùng nghiệp vụ. Các phần như Spring Integration Core và cơ chế khởi tạo Spring context được giả định đã có trong ứng dụng.

Các kiểu `record` yêu cầu Java 16 trở lên; các dự án Java cũ hơn có thể dùng POJO tương đương. Mỗi kiểu `public` dưới đây nằm trong tệp Java riêng thuộc package `example.invoice`.

### 5.1. Mô hình dữ liệu

```java
package example.invoice;

import java.math.BigDecimal;

public record InvoiceRequest(String orderId, BigDecimal amount) {
}
```

```java
package example.invoice;

public record InvoiceResult(String orderId, String status) {
}
```

### 5.2. Lớp nghiệp vụ được gọi bởi handler

```java
package example.invoice;

import org.springframework.integration.annotation.ServiceActivator;

public class InvoiceProcessor {

    @ServiceActivator(
            inputChannel = "invoiceRequests",
            requiresReply = "true")
    public InvoiceResult process(InvoiceRequest request) {
        if (request.orderId() == null || request.orderId().isBlank()) {
            throw new IllegalArgumentException("orderId must not be blank");
        }
        if (request.amount() == null || request.amount().signum() <= 0) {
            throw new IllegalArgumentException("amount must be positive");
        }

        return new InvoiceResult(request.orderId(), "ACCEPTED");
    }
}
```

`requiresReply = "true"` thể hiện hợp đồng: bước này phải tạo kết quả. Nếu phương thức không trả kết quả, framework báo lỗi thay vì âm thầm kết thúc nhánh.

### 5.3. Gateway làm điểm vào của ứng dụng

```java
package example.invoice;

import org.springframework.integration.annotation.MessagingGateway;

@MessagingGateway(defaultRequestChannel = "invoiceRequests")
public interface InvoiceGateway {

    InvoiceResult submit(InvoiceRequest request);
}
```

Gateway che giấu thao tác tạo message và chờ phản hồi khỏi mã gọi nghiệp vụ. Với lời gọi request–reply này, cơ chế gateway cung cấp thông tin kênh trả lời để handler gửi kết quả về.

### 5.4. Cấu hình hạ tầng

```java
package example.invoice;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.IntegrationComponentScan;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
@IntegrationComponentScan(basePackageClasses = InvoiceGateway.class)
public class InvoiceIntegrationConfig {

    @Bean
    public MessageChannel invoiceRequests() {
        return new DirectChannel();
    }

    @Bean
    public InvoiceProcessor invoiceProcessor() {
        return new InvoiceProcessor();
    }
}
```

`@EnableIntegration` bật hạ tầng integration cần thiết. Bean `InvoiceProcessor` được xử lý để tạo endpoint từ `@ServiceActivator`. `@IntegrationComponentScan` tìm interface gateway; việc có một interface gắn annotation không tự tạo ra implementation Java thông thường.

Ví dụ gọi từ một bean đã được inject gateway:

```java
InvoiceResult result = invoiceGateway.submit(
        new InvoiceRequest("ORD-1001", new BigDecimal("125000")));
```

Với cấu hình `DirectChannel` trên, endpoint gọi processor trên thread đang gửi request. Handler trả `InvoiceResult`, framework tạo reply rồi gateway nhận và trả kết quả cho caller.

## 6. Cấu hình tương đương bằng Java DSL

Java DSL biểu diễn các bước xử lý bằng chuỗi cấu hình. Với cùng payload và gateway, có thể khai báo endpoint bằng `.handle(...)`.

Đây là **phương án thay thế** cho cấu hình annotation ở phần trước. Khi dùng phương án này:

- Bỏ `@ServiceActivator` khỏi `InvoiceProcessor.process(...)`, giữ nguyên logic nghiệp vụ.
- Dùng cấu hình DSL dưới đây thay cho `InvoiceIntegrationConfig` ở trên.
- Giữ lại interface `InvoiceGateway` và các kiểu dữ liệu.

```java
package example.invoice;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.IntegrationComponentScan;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
@IntegrationComponentScan(basePackageClasses = InvoiceGateway.class)
public class InvoiceDslConfig {

    @Bean
    public MessageChannel invoiceRequests() {
        return new DirectChannel();
    }

    @Bean
    public InvoiceProcessor invoiceProcessor() {
        return new InvoiceProcessor();
    }

    @Bean
    public IntegrationFlow invoiceFlow(InvoiceProcessor processor) {
        return IntegrationFlow.from("invoiceRequests")
                .handle(processor, "process",
                        endpoint -> endpoint.id("invoiceHandlerEndpoint"))
                .get();
    }
}
```

`.handle(processor, "process", ...)` tạo service activator gọi phương thức đã chỉ định. `invoiceHandlerEndpoint` là ID của consumer endpoint được tạo ra; nó hữu ích khi quan sát và quản lý endpoint, nhưng không phải tên kênh đầu vào.

Ví dụ DSL này yêu cầu phương thức luôn trả kết quả bằng chính logic của `process(...)`. Nó không cấu hình tường minh `requiresReply` như phương án annotation. Nếu hợp đồng cần phát hiện `null` ngay tại handler, hãy cấu hình handler hỗ trợ reply với `requiresReply` hoặc sử dụng phương án annotation đã trình bày.

Không bật đồng thời cả hai phương án trên cùng `invoiceRequests` với ý định “mỗi request chỉ gọi processor một lần theo một endpoint duy nhất”. Khi có nhiều subscriber trên `DirectChannel`, cơ chế phân phối chọn subscriber theo cấu hình; đây không phải chuỗi xử lý tuần tự và cũng không phải broadcast.

### Handler dạng lambda

Một bước nghiệp vụ ngắn cũng có thể viết bằng `GenericHandler` qua DSL:

```java
@Bean
public IntegrationFlow invoiceFlow() {
    return IntegrationFlow.from("invoiceRequests")
            .<InvoiceRequest>handle((request, headers) -> {
                if (request.amount() == null
                        || request.amount().signum() <= 0) {
                    throw new IllegalArgumentException(
                            "amount must be positive");
                }
                return new InvoiceResult(request.orderId(), "ACCEPTED");
            })
            .get();
}
```

Đoạn này cũng là một phương án thay thế cho bean `invoiceFlow`, không khai báo thêm cạnh flow cũ. Lambda có hai đối số nhận payload và headers rồi trả kết quả; nó khác raw `MessageHandler`, vốn nhận một `Message<?>` và có phương thức trả về `void`.

Với nghiệp vụ nhiều nhánh hoặc cần tái sử dụng, tách thành lớp riêng thường giúp kiểm thử và đọc flow dễ hơn.

## 7. Quy tắc phản hồi và kết thúc flow

### 7.1. Reply đi đâu?

Với handler hỗ trợ reply, cần phân biệt hai trường hợp chính:

| Tình huống | Cách xử lý đầu ra |
| --- | --- |
| Có output channel được cấu hình | Reply được gửi tới output channel đó |
| Không có output channel được cấu hình | Handler tìm đích trả lời qua cơ chế `replyChannel` của request |

Ví dụ một chuỗi xử lý tường minh:

```java
return IntegrationFlow.from("invoiceRequests")
        .handle(processor, "process")
        .channel("invoiceResults")
        .get();
```

Kết quả được chuyển đến `invoiceResults`. Nếu request đi vào từ gateway và caller đang chờ reply, phần flow sau `invoiceResults` phải tiếp tục xử lý và đưa kết quả trở về reply channel thích hợp. Chỉ đặt tên một output channel không làm gateway tự nhận được reply từ mọi kênh bất kỳ.

Nếu một handler tạo kết quả nhưng không xác định được đích đầu ra, việc gửi reply có thể thất bại. `channel.send(message)` chỉ thực hiện thao tác gửi theo hợp đồng của kênh; nó không tự đóng vai trò gateway request–reply.

### 7.2. `null`, `void` và `requiresReply`

| Kết quả phương thức được gọi | Ý nghĩa thông thường |
| --- | --- |
| Payload khác `null` | Tạo reply mang payload đó |
| Một `Message<?>` | Cung cấp payload và headers cho reply theo cơ chế của handler |
| `null` hoặc phương thức `void` | Không có reply; có thể kết thúc nhánh |
| Không có reply trong khi `requiresReply` bật | Phát sinh lỗi thiếu reply, thường là `ReplyRequiredException` |

Trả `null` có thể phù hợp với một bước một chiều. Trong luồng gateway cần phản hồi, nó có thể khiến caller chờ đến khi hết thời gian chờ hoặc nhận kết quả thiếu như cấu hình cho phép. Khi cần một kết quả nghiệp vụ như “không tìm thấy”, hãy cân nhắc trả một đối tượng thể hiện trạng thái đó thay vì dùng `null` không rõ nghĩa.

### 7.3. Bảo toàn headers

Khi phương thức trả một payload thông thường, handler hỗ trợ reply thường truyền các headers thích hợp từ request sang reply. Việc truyền headers vẫn chịu quy tắc của framework và cấu hình handler; không nên giả định mọi header đều được sao chép nguyên trạng.

Nếu tự tạo message ở tầng khác hoặc gửi thủ công bằng một handler tùy biến, cần chủ động xem xét các headers phục vụ truy vết và phản hồi, chẳng hạn `correlationId`, `replyChannel`, `errorChannel`. Mất `replyChannel` trên đường đi có thể làm một request xử lý nghiệp vụ thành công nhưng không trả được kết quả cho caller.

Không lưu hoặc truyền nguyên `replyChannel` như một trường nghiệp vụ bền vững. Kênh trả lời tạm thời trong bộ nhớ không phải địa chỉ có thể dùng lại tùy ý sau khi khởi động lại ứng dụng hay qua mọi transport.

## 8. Thread thực thi, polling và tải xử lý

Handler không tự quyết định toàn bộ mô hình thực thi. Kênh và consumer endpoint quyết định handler được gọi khi nào, trên thread nào.

| Đầu vào | Thread thường gọi handler | Điều cần lưu ý |
| --- | --- | --- |
| `DirectChannel` | Thread gửi message | Handler chậm giữ thread caller; lỗi thường lan ngược theo call stack |
| `ExecutorChannel` | Thread do executor cung cấp | Có ranh giới bất đồng bộ; không mặc định giữ transaction/thread-local của caller |
| `QueueChannel` cùng poller | Thread của tác vụ polling, hoặc executor được cấu hình cho poller | Cần polling metadata; message trong queue chưa có nghĩa đã xử lý thành công |

Với queue đầu vào, một service activator có thể được khai báo như sau trong một cấu hình riêng:

```java
import org.springframework.integration.annotation.Poller;
import org.springframework.integration.annotation.ServiceActivator;

@ServiceActivator(
        inputChannel = "pendingInvoices",
        poller = @Poller(fixedDelay = "500"))
public void consume(InvoiceRequest request) {
    // Thực hiện một tác vụ một chiều.
}
```

Trong ví dụ này, `pendingInvoices` phải là bean kênh pollable, chẳng hạn `QueueChannel`. Poller được cấu hình fixed delay 500 ms; điều đó không có nghĩa mỗi message chắc chắn được xử lý sau đúng 500 ms. Thời gian thực tế còn phụ thuộc thời lượng xử lý, số message mỗi lần poll, lịch chạy và tải hệ thống.

Khi cho phép nhiều thread gọi handler, hãy kiểm tra trạng thái dùng chung. Một bean handler thường được tái sử dụng; trường instance như `currentRequest` có thể bị các lần xử lý đồng thời ghi đè. Nên giữ dữ liệu theo request trong biến cục bộ và bảo vệ tài nguyên dùng chung khi cần.

## 9. Xử lý lỗi tại handler

### 9.1. Luồng đồng bộ

Nếu `InvoiceProcessor` ném `IllegalArgumentException` khi xử lý message qua `DirectChannel`, lỗi thường quay về caller qua call stack, có thể được bọc bằng một messaging exception. Với gateway, cách lỗi được chuyển tiếp còn chịu cấu hình gateway.

Không nên mặc định mọi lỗi từ handler đều được gửi vào bean tên `errorChannel`. Trong luồng đồng bộ, việc lan truyền exception trực tiếp là hành vi cần tính đến đầu tiên.

### 9.2. Luồng bất đồng bộ và polling

Với executor hoặc polling, caller không còn nằm trên cùng call stack khi handler xử lý. Hạ tầng của Spring Integration có các cơ chế xử lý lỗi và xuất bản `ErrorMessage`, thường liên quan đến header `errorChannel`, kênh lỗi mặc định và cấu hình error handler của thành phần thực thi.

Cần xác định rõ ở ranh giới bất đồng bộ:

- Lỗi được chuyển đến kênh nào và ai tiêu thụ kênh đó.
- Message gốc hoặc ngữ cảnh xử lý có thể được tìm lại bằng cách nào.
- Caller đang chờ reply sẽ nhận lỗi, hết thời gian chờ hay được trả một kết quả nghiệp vụ.
- Tác vụ thất bại được retry, lưu để xử lý lại hay dừng tại đó.

Việc dùng một executor tùy chỉnh hoặc error handler tùy chỉnh có thể thay đổi hành vi mặc định. Cấu hình kênh lỗi phải đi kèm kiểm thử đường lỗi thực tế.

### 9.3. Retry và tác dụng phụ

Request handler advice có thể bao quanh bước gọi handler, chẳng hạn dùng retry advice để thử lại khi lỗi tạm thời. Tuy nhiên, retry không tự giải quyết trùng lặp nghiệp vụ.

Ví dụ dịch vụ lập hóa đơn đã tạo hóa đơn nhưng lỗi mạng xảy ra trước khi nhận được kết quả. Lần retry tiếp theo có thể tạo hóa đơn thứ hai nếu hệ thống đích không kiểm tra trùng.

Cần chọn khóa idempotency phù hợp, ví dụ một định danh yêu cầu lập hóa đơn ổn định. `orderId` chỉ phù hợp nếu quy tắc nghiệp vụ xác nhận mỗi đơn hàng chỉ có đúng một thao tác lập hóa đơn tương ứng. Không dùng message ID mới phát sinh cho mỗi lần gửi lại như một bảo đảm chống trùng xuyên các lần gửi.

Transaction cũng không tự bao phủ mọi hệ thống đích chỉ vì handler nằm trong integration flow. Phạm vi transaction phụ thuộc thread, transaction manager, tài nguyên tham gia và cấu hình endpoint/advice. Một lệnh HTTP từ handler thường không tự rollback theo transaction cơ sở dữ liệu cục bộ.

## 10. Kiểm thử handler ở hai mức

### 10.1. Kiểm thử logic nghiệp vụ

Vì processor nhận và trả kiểu nghiệp vụ, có thể gọi trực tiếp bằng unit test mà không cần khởi tạo integration flow.

```java
package example.invoice;

import java.math.BigDecimal;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class InvoiceProcessorTest {

    private final InvoiceProcessor processor = new InvoiceProcessor();

    @Test
    void acceptsPositiveAmount() {
        InvoiceResult result = processor.process(
                new InvoiceRequest("ORD-1001", new BigDecimal("125000")));

        assertEquals("ORD-1001", result.orderId());
        assertEquals("ACCEPTED", result.status());
    }

    @Test
    void rejectsNonPositiveAmount() {
        assertThrows(IllegalArgumentException.class,
                () -> processor.process(new InvoiceRequest(
                        "ORD-1001", BigDecimal.ZERO)));
    }
}
```

Test này kiểm tra giá trị và quy tắc nghiệp vụ. Nó chưa chứng minh endpoint đã đăng ký đúng channel hoặc gateway đã nhận được reply.

### 10.2. Kiểm thử tích hợp qua gateway

Với phương án annotation ở phần 5, một test khởi tạo Spring context và gọi gateway sẽ kiểm tra cả đường request–reply:

```java
package example.invoice;

import java.math.BigDecimal;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringJUnitConfig(InvoiceIntegrationConfig.class)
class InvoiceFlowTest {

    @Autowired
    private InvoiceGateway gateway;

    @Test
    void returnsReplyThroughGateway() {
        InvoiceResult result = gateway.submit(
                new InvoiceRequest("ORD-1001", new BigDecimal("125000")));

        assertEquals("ORD-1001", result.orderId());
        assertEquals("ACCEPTED", result.status());
    }
}
```

Test này cần JUnit Jupiter và Spring Test bên cạnh các dependency của ví dụ. Nó kiểm tra đường đi qua gateway, channel, endpoint và reply. Nếu dùng phương án DSL thì thay lớp cấu hình bằng `InvoiceDslConfig` sau khi đã bỏ annotation service activator khỏi processor.

Các trường hợp cần bổ sung khi áp dụng vào ứng dụng:

| Trường hợp | Điều cần kiểm tra |
| --- | --- |
| Payload sai kiểu hoặc header bắt buộc bị thiếu | Lỗi ánh xạ được xử lý tại đúng ranh giới |
| Phương thức trả `null` | Kết thúc một chiều hoặc báo thiếu reply đúng hợp đồng |
| Handler ném lỗi trong luồng đồng bộ | Caller nhận được lỗi và giữ được nguyên nhân cần chẩn đoán |
| Handler ném lỗi sau ranh giới bất đồng bộ | Error flow nhận lỗi; caller có kết quả hoặc timeout đúng cấu hình |
| Retry sau khi đã có tác dụng phụ | Không tạo thêm kết quả nghiệp vụ trùng lặp |
| Nhiều message xử lý đồng thời | Không rò trạng thái giữa các request |

Với test qua queue hoặc kênh lỗi, dùng thao tác nhận có timeout hữu hạn hoặc công cụ chờ điều kiện. Tránh dựa vào `Thread.sleep(...)` cố định vì thời gian thực thi có thể thay đổi theo môi trường.

## 11. Các lỗi thiết kế thường gặp

| Hiện tượng | Nguyên nhân cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| Gateway chờ nhưng không nhận kết quả | Handler `void`/`null`, reply đi sang nhánh khác, mất `replyChannel` | Xác định hợp đồng reply và lần theo toàn bộ đường đầu ra |
| Gửi vào channel nhưng báo không có subscriber | Endpoint chưa được tạo, chưa chạy hoặc chưa đăng ký | Kiểm tra Spring bean, annotation processing, channel name và vòng đời endpoint |
| Queue có message nhưng không được tiêu thụ | Thiếu poller, poller dừng hoặc bước xử lý trước đó bị kẹt | Kiểm tra polling metadata, trạng thái endpoint và log |
| Bước sau handler không chạy | Handler một chiều hoặc kết quả là `null` | Dùng handler tạo reply nếu flow cần tiếp tục |
| Hai handler cùng kênh nhưng không chạy theo thứ tự mong muốn | Nhầm nhiều subscriber với chuỗi pipeline | Nối các bước bằng các channel riêng hoặc chuỗi DSL |
| Lỗi không xuất hiện ở `errorChannel` | Đường chạy đồng bộ lan exception trực tiếp hoặc có error handler khác | Kiểm tra thread, gateway và error handling thực tế |
| Retry làm tạo hai hóa đơn | Tác vụ không idempotent, không có khóa chống trùng phù hợp | Thiết kế chống trùng theo định danh nghiệp vụ |
| Dữ liệu của request này xuất hiện trong request khác | Trạng thái mutable trong handler được dùng đồng thời | Dùng biến cục bộ hoặc cơ chế đồng bộ phù hợp |

## 12. Ghi nhớ khi thiết kế handler endpoint

Một handler endpoint tốt thể hiện rõ đầu vào, hành vi nghiệp vụ và hợp đồng đầu ra. Hãy xác định bước đó có cần reply hay không trước khi viết mã, chọn kênh và endpoint theo mô hình thực thi cần thiết, rồi kiểm tra đường lỗi cùng với đường thành công.

`MessageHandler` là hợp đồng thực thi ở tầng messaging. Service activator nối hợp đồng đó với một phương thức nghiệp vụ. Consumer endpoint đưa message từ channel đến handler. Gateway cung cấp điểm gọi thuận tiện cho ứng dụng và có thể quản lý lời gọi request–reply. Bốn vai trò này phối hợp để tạo thành một luồng tích hợp có thể đọc, quan sát và kiểm thử.