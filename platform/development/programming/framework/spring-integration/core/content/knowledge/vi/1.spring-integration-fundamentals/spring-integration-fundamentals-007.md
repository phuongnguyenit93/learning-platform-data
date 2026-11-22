# Loose coupling giữa các component

## 1. Mục tiêu và bối cảnh

Trong Spring Integration Core, một luồng tích hợp thường gồm nhiều component: tiếp nhận yêu cầu, chuyển đổi dữ liệu, kiểm tra điều kiện, định tuyến và gọi hệ thống đích. Nếu mỗi component trực tiếp biết cách khởi tạo, gọi và xử lý lỗi của component tiếp theo, một thay đổi nhỏ có thể lan ra cả luồng.

**Loose coupling**, hay liên kết lỏng, là thiết kế để mỗi component chỉ phụ thuộc vào những hợp đồng cần thiết và ổn định. Component không cần biết quá nhiều về cách các component khác được triển khai hoặc được kết nối.

Sau bài học này, bạn có thể:

- Nhận diện các dạng phụ thuộc giữa những bước xử lý.
- Giải thích vai trò của `Message`, `MessageChannel`, endpoint và gateway trong việc giảm liên kết.
- Dùng Java DSL để tách logic nghiệp vụ khỏi việc lắp ghép luồng.
- Phân biệt liên kết về mã nguồn, dữ liệu, thời gian và vận hành.
- Chọn ranh giới kiểm thử phù hợp khi thay đổi một component.

Ví dụ xuyên suốt là tiếp nhận đơn hàng: nhận yêu cầu, chuẩn hóa mã sản phẩm và trả về xác nhận tiếp nhận. Đây là ví dụ trong cùng một ứng dụng Java; gửi thông điệp ra broker hoặc sang dịch vụ khác là một quyết định kiến trúc bổ sung.

## 2. Liên kết chặt xuất hiện như thế nào?

Xét cách viết sau:

```java
public class OrderController {
    private final OrderService orderService;
    private final EmailClient emailClient;
    private final AuditRepository auditRepository;

    public OrderController(OrderService orderService,
                           EmailClient emailClient,
                           AuditRepository auditRepository) {
        this.orderService = orderService;
        this.emailClient = emailClient;
        this.auditRepository = auditRepository;
    }

    public OrderReceipt submit(OrderRequest request) {
        OrderReceipt receipt = orderService.place(request);
        emailClient.sendConfirmation(receipt);
        auditRepository.save(receipt);
        return receipt;
    }
}
```

Dependency injection giúp thay implementation của các dependency, nhưng `OrderController` vẫn biết toàn bộ chuỗi hành động. Khi cần gửi thông báo có điều kiện, thêm retry hoặc đổi thứ tự ghi audit, controller phải thay đổi.

Đây không có nghĩa gọi phương thức trực tiếp luôn sai. Với một thao tác cục bộ đơn giản, nó có thể là lựa chọn dễ hiểu nhất. Vấn đề xuất hiện khi một lớp vừa xử lý nghiệp vụ, vừa chịu trách nhiệm điều phối nhiều tác vụ tích hợp có vòng đời thay đổi riêng.

Một số dấu hiệu cần xem xét lại ranh giới component:

- Thay nơi lưu dữ liệu làm thay đổi lớp tiếp nhận yêu cầu.
- Đổi định dạng thông báo làm thay đổi logic tính giá.
- Muốn kiểm thử một phép chuyển đổi nhưng phải khởi tạo cả client HTTP và repository.
- Mỗi bước phải biết tên lớp, thứ tự gọi và chính sách lỗi của các bước còn lại.

## 3. Liên kết lỏng không có nghĩa là không còn phụ thuộc

Hai component chỉ hợp tác được khi có một hợp đồng chung. Spring Integration chuyển nhiều phụ thuộc trực tiếp thành hợp đồng thông điệp và cấu hình kết nối; nó không xóa bỏ mọi ràng buộc.

| Khía cạnh | Biểu hiện của liên kết chặt | Cách giảm liên kết | Phần vẫn phải thống nhất |
|---|---|---|---|
| Triển khai | Producer gọi trực tiếp một lớp cụ thể | Gửi qua channel, đưa xử lý vào endpoint | Hành vi mong đợi của bước xử lý |
| Cấu trúc dữ liệu | Mọi bước đọc tùy ý trạng thái nội bộ của nhau | Dùng payload và header có hợp đồng rõ ràng | Kiểu, ý nghĩa và quy tắc tương thích dữ liệu |
| Topology | Mỗi bước biết bước kế tiếp | Đặt kết nối trong cấu hình Java DSL | Người cấu hình vẫn phải biết cấu trúc luồng |
| Thời gian | Caller phải chờ toàn bộ chuỗi hoàn tất | Cân nhắc queue hoặc executor | Timeout, sức chứa và cách nhận kết quả |
| Lỗi | Lỗi ở bước sau luôn chi phối caller | Xác định ranh giới xử lý lỗi | Retry, giao dịch và chống xử lý trùng |
| Triển khai vận hành | Các bước phải chạy cùng nhau | Chỉ tách tiến trình khi có nhu cầu rõ ràng | Hạ tầng truyền tin và tương thích phiên bản |

Một luồng dùng `DirectChannel` có thể liên kết lỏng về implementation nhưng vẫn liên kết về thời gian: bên gửi chạy cùng thread với handler và chờ handler hoàn tất.

Ngược lại, thêm queue giúp tách thời điểm gửi khỏi thời điểm xử lý, nhưng payload vẫn có thể quá phụ thuộc vào cấu trúc dữ liệu nội bộ của producer.

## 4. Các thành phần cốt lõi giúp giảm liên kết

### 4.1. Message: hợp đồng trao đổi

`Message<T>` gồm payload và headers. Payload biểu diễn dữ liệu cần xử lý; headers mang thông tin bổ sung như mã tương quan hoặc thông tin định tuyến phản hồi.

```java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

Message<OrderRequest> message = MessageBuilder
    .withPayload(new OrderRequest("REQ-001", " book-01 ", 2))
    .setHeader("sourceSystem", "web")
    .build();
```

Hai bên không cần biết cấu trúc lớp nội bộ của nhau, nhưng phải hiểu `OrderRequest` và ý nghĩa của `sourceSystem` nếu cùng sử dụng header đó.

Cấu trúc `Message` là bất biến về mặt API; điều này không tự làm đối tượng payload trở thành bất biến sâu. Nếu payload chứa `List` có thể sửa, nhiều consumer vẫn có thể quan sát dữ liệu bị thay đổi. Với thông điệp dùng chung, nên ưu tiên giá trị bất biến hoặc sao chép dữ liệu tại ranh giới phù hợp.

### 4.2. MessageChannel: điểm kết nối

Producer gửi vào channel thay vì gọi tên consumer cụ thể. Cấu hình của ứng dụng quyết định endpoint nào nhận thông điệp.

```text
Producer -> Channel -> Consumer endpoint -> Business handler
```

Channel là một abstraction trong Spring Messaging/Spring Integration. Một channel có thể chỉ hoạt động trong bộ nhớ của cùng JVM; sự hiện diện của channel không có nghĩa đã dùng Kafka, RabbitMQ hay một message broker khác.

### 4.3. Endpoint: nối handler với luồng thông điệp

Endpoint liên kết một bước xử lý với cơ chế nhận thông điệp. Tùy endpoint, bước xử lý có thể biến đổi payload, lọc, định tuyến hoặc gọi nghiệp vụ.

Ví dụ, service activator có thể gọi một phương thức Java nhận `PreparedOrder` và trả `OrderReceipt`. Phương thức đó không nhất thiết phải thao tác với `MessageChannel` hoặc tự tìm consumer tiếp theo.

Với subscribable channel như `DirectChannel`, consumer được đăng ký để nhận thông điệp. Với pollable channel như `QueueChannel`, consumer cần poller để lấy thông điệp ra xử lý. Cơ chế tiếp nhận là một phần của việc lắp ghép luồng.

### 4.4. Gateway: che giấu API messaging ở biên gọi

Messaging gateway cho phép caller làm việc qua một interface nghiệp vụ:

```java
OrderReceipt receipt = orderGateway.submit(request);
```

Caller không phải tự dựng `Message`, gửi vào channel rồi tìm cách nhận phản hồi. Gateway chuyển lời gọi phương thức thành tương tác messaging theo cấu hình.

Gateway giảm phụ thuộc vào API messaging, nhưng chữ ký phương thức vẫn là một hợp đồng. Nếu đổi kiểu trả về hoặc ý nghĩa của kết quả, caller vẫn bị ảnh hưởng.

### 4.5. Java DSL: tập trung cấu hình kết nối

Java DSL biểu diễn cấu trúc luồng ở một nơi thay vì phân tán việc gọi bước tiếp theo trong từng handler:

```text
Gateway -> orderRequests -> Transformer -> Service activator -> Reply
```

Cấu hình luồng biết các bước được kết nối ra sao. Business handler tập trung vào nghiệp vụ của mình. Vì vậy, thay đổi topology thường được giới hạn ở cấu hình luồng và các kiểm thử liên quan.

## 5. Ví dụ: tách chuẩn hóa đơn hàng khỏi nghiệp vụ tiếp nhận

### 5.1. Điều kiện chạy và hợp đồng dữ liệu

Ví dụ dùng Spring Boot, dependency `spring-boot-starter-integration` và Java 17 trở lên để sử dụng `record`. Để Spring Boot quản lý phiên bản các thư viện Spring tương thích thay vì tự ghép các phiên bản khác nhau.

Đặt các kiểu public dưới đây trong những tệp Java riêng cùng package, ví dụ `example.orders`. Đặt lớp ứng dụng ở package gốc bao phủ các lớp cấu hình. Các đoạn mã chỉ tập trung vào luồng tích hợp; không triển khai HTTP controller hay cơ sở dữ liệu.

```java
package example.orders;

public record OrderRequest(
    String requestId,
    String productCode,
    int quantity
) {}
```

```java
package example.orders;

public record PreparedOrder(
    String requestId,
    String productCode,
    int quantity
) {}
```

```java
package example.orders;

public record OrderReceipt(
    String requestId,
    String productCode,
    String status
) {}
```

`requestId` nhận diện yêu cầu nghiệp vụ. `PreparedOrder` thể hiện dữ liệu đã qua bước chuẩn hóa để nghiệp vụ tiếp nhận không phải lặp lại thao tác đó.

Các record này chỉ chứa chuỗi và số nguyên, phù hợp cho ví dụ trao đổi dữ liệu bất biến. Khi mở rộng payload bằng collection hoặc đối tượng mutable, cần xem xét lại tính bất biến.

### 5.2. Khai báo gateway

```java
package example.orders;

import org.springframework.integration.annotation.MessagingGateway;

@MessagingGateway(
    defaultRequestChannel = "orderRequests",
    defaultRequestTimeout = "1000",
    defaultReplyTimeout = "3000"
)
public interface OrderGateway {
    OrderReceipt submit(OrderRequest request);
}
```

Các giá trị timeout được biểu diễn bằng mili giây. Chúng giới hạn những giai đoạn chờ tương ứng của gateway; không nên hiểu `defaultReplyTimeout` là cơ chế tự ngắt một handler đồng bộ đang thực thi trên thread của caller.

Trong ví dụ dùng `DirectChannel`, nếu nghiệp vụ bị treo bên trong handler, đặt reply timeout không tự biến lời gọi đó thành một tác vụ có thể bị hủy sau ba giây. Timeout của HTTP client, JDBC hoặc tác vụ nền phải được thiết kế tại đúng nơi thực hiện công việc.

### 5.3. Viết business handler độc lập với messaging

```java
package example.orders;

public class OrderService {
    public OrderReceipt place(PreparedOrder order) {
        if (order.quantity() <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }

        return new OrderReceipt(
            order.requestId(),
            order.productCode(),
            "ACCEPTED"
        );
    }
}
```

`OrderService` không biết channel, gateway hoặc consumer tiếp theo. Có thể kiểm thử lớp này bằng Java thông thường, hoặc tái sử dụng nó từ một adapter khác.

Kết quả `ACCEPTED` trong ví dụ chỉ có nghĩa handler đã chấp nhận dữ liệu theo logic được viết. Nó chưa chứng minh đơn hàng được lưu bền vững, thanh toán hay giao hàng.

### 5.4. Lắp ghép luồng bằng Java DSL

```java
package example.orders;

import java.util.Locale;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;

@Configuration
public class OrderIntegrationConfiguration {

    @Bean
    public MessageChannel orderRequests() {
        return new DirectChannel();
    }

    @Bean
    public OrderService orderService() {
        return new OrderService();
    }

    @Bean
    public IntegrationFlow orderFlow(OrderService orderService) {
        return IntegrationFlow.from("orderRequests")
            .transform(OrderRequest.class, request -> new PreparedOrder(
                request.requestId(),
                request.productCode().trim().toUpperCase(Locale.ROOT),
                request.quantity()
            ))
            .handle(orderService, "place")
            .get();
    }
}
```

```java
package example.orders;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.integration.annotation.IntegrationComponentScan;

@SpringBootApplication
@IntegrationComponentScan
public class OrderApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrderApplication.class, args);
    }
}
```

`@IntegrationComponentScan` cho phép phát hiện interface được đánh dấu `@MessagingGateway` trong phạm vi scan. Trong ví dụ Spring Boot, starter và auto-configuration cung cấp hạ tầng Integration cần thiết.

Giả sử caller gửi:

```java
OrderRequest request = new OrderRequest("REQ-001", " book-01 ", 2);
OrderReceipt receipt = orderGateway.submit(request);
```

Kết quả mong đợi có `productCode` bằng `BOOK-01`, `requestId` bằng `REQ-001` và `status` bằng `ACCEPTED`.

Luồng phản hồi sử dụng ngữ cảnh request/reply do gateway thiết lập. Ví dụ không cần một channel phản hồi mang tên riêng; cũng không cần để `OrderService` tự gửi kết quả ngược về gateway.

Để giữ ví dụ gọn, dữ liệu đầu vào được giả định có `requestId` và `productCode` hợp lệ, khác `null`. Trong ứng dụng thực tế, cần một hợp đồng validation rõ ràng tại biên tiếp nhận; lỗi dữ liệu không nên vô tình trở thành `NullPointerException` trong transformer.

### 5.5. Những phụ thuộc đã thay đổi

| Component | Cần biết | Không cần biết |
|---|---|---|
| Caller | `OrderGateway`, dữ liệu yêu cầu và phản hồi | Tên transformer, phương thức handler, cách lắp ghép luồng |
| Gateway | Channel đầu vào và hợp đồng request/reply | Các bước nội bộ của nghiệp vụ |
| Transformer | `OrderRequest`, `PreparedOrder`, quy tắc chuẩn hóa | Cách caller tiếp nhận kết quả |
| `OrderService` | `PreparedOrder`, `OrderReceipt`, quy tắc nghiệp vụ | API channel và cách nhận thông điệp |
| Cấu hình Java DSL | Topology và các component được kết nối | Chi tiết xử lý nội bộ của từng bước |

Nếu đổi quy tắc chuẩn hóa mã sản phẩm, phần thay đổi chủ yếu nằm ở transformer và kiểm thử của bước đó. Nếu đổi hợp đồng `OrderReceipt`, cần đánh giá cả caller vì đó là hợp đồng công khai của gateway.

## 6. Chọn channel là chọn cả ràng buộc thời gian

### 6.1. DirectChannel: ít trung gian nhưng vẫn đồng bộ

`DirectChannel` gọi một subscriber để xử lý thông điệp trên thread gửi. Nó không phát cùng một thông điệp tới tất cả subscriber như cơ chế publish-subscribe.

Ưu điểm là luồng thực thi dễ theo dõi, ít chi phí chuyển thread và có thể tham gia ngữ cảnh giao dịch trên thread hiện tại nếu hạ tầng giao dịch được cấu hình phù hợp.

Giới hạn là caller còn phụ thuộc vào thời gian và kết quả của handler. Lỗi downstream có thể quay về lời gọi gửi hoặc gateway, thường dưới dạng ngoại lệ messaging bao bọc nguyên nhân.

Đừng nối thêm một subscriber vào `DirectChannel` với kỳ vọng cả hai đều nhận mọi đơn hàng. Muốn phát cho nhiều nhánh, phải thiết kế publish-subscribe và chính sách xử lý lỗi tương ứng.

### 6.2. QueueChannel: tách gửi và xử lý bằng hàng đợi

Có thể thay khai báo channel đầu vào bằng:

```java
@Bean
public MessageChannel orderRequests() {
    return new QueueChannel(100);
}
```

Đoạn này cần import `org.springframework.integration.channel.QueueChannel`. Khi luồng bắt đầu từ một pollable channel, endpoint tiêu thụ phải được cấu hình poller. Ví dụ, phần đầu của flow có thể đổi thành:

```java
IntegrationFlow.from(
        "orderRequests",
        endpoint -> endpoint.poller(
            Pollers.fixedDelay(100).maxMessagesPerPoll(10)
        )
    )
    // Các bước transform và handle tiếp theo.
```

Đoạn trên là phần thay thế trong cấu hình, cần import `org.springframework.integration.dsl.Pollers` và giữ các bước còn lại của flow. Nó minh họa consumer thăm dò hàng đợi theo chu kỳ với số thông điệp tối đa mỗi lần poll.

Producer có thể gửi xong trước khi nghiệp vụ xử lý. Tuy nhiên, với gateway trả về `OrderReceipt`, caller vẫn đợi phản hồi. Queue chỉ thay đổi cơ chế thực thi; nó không tự biến API request/reply thành API chỉ xác nhận tiếp nhận.

Một số hệ quả phải thiết kế rõ:

- Hàng đợi có sức chứa 100; khi đầy, gửi có thể phải chờ hoặc không thành công theo timeout và cách gọi.
- `QueueChannel` mặc định trong bộ nhớ không tự bảo đảm thông điệp sống sót khi tiến trình dừng.
- Thông điệp có thể đã vào queue rồi caller hết thời gian chờ phản hồi; việc xử lý vẫn có thể tiếp tục.
- Nếu caller gửi lại, nghiệp vụ có thể nhận cùng một yêu cầu nhiều lần.

Vì vậy, `requestId` và chính sách idempotency trở nên quan trọng khi thao tác tạo tác dụng phụ. Chỉ thêm trường `requestId` chưa tạo ra idempotency; cần cơ chế kiểm tra và ghi nhận xử lý phù hợp với giao dịch nghiệp vụ.

### 6.3. ExecutorChannel: chuyển thực thi sang executor

`ExecutorChannel` dùng executor để điều phối việc gọi handler. Với executor thông thường chuyển tác vụ sang thread khác, nó giúp tách thread gửi khỏi thread xử lý nhưng không phải hàng đợi lưu bền vững.

Hành vi thực tế còn phụ thuộc executor và chính sách từ chối tác vụ; chẳng hạn chính sách chạy tác vụ trên thread gọi khi quá tải có thể làm thay đổi kỳ vọng về sự bất đồng bộ.

Không giả định giao dịch hoặc dữ liệu trong `ThreadLocal` tự đi qua ranh giới executor. Bất kỳ thông tin nghiệp vụ nào cần truyền phải có cách truyền rõ ràng; thông tin quan sát như trace cũng cần cơ chế propagation được cấu hình phù hợp.

| Loại channel | Cách tiêu thụ chính | Caller còn phải quan tâm |
|---|---|---|
| `DirectChannel` | Gọi subscriber trên thread gửi | Thời gian xử lý, lỗi đồng bộ |
| `QueueChannel` | Consumer poll thông điệp đã xếp hàng | Dung lượng, timeout gửi, độ trễ, mất dữ liệu nếu không lưu bền |
| `ExecutorChannel` | Dispatch qua executor | Năng lực executor, quá tải, lỗi và ngữ cảnh qua thread |

## 7. Transformer, router, filter và aggregator ảnh hưởng đến hợp đồng ra sao?

Những endpoint này giúp tách trách nhiệm, nhưng mỗi loại thêm một điều kiện mà người thiết kế luồng phải hiểu.

- **Transformer** tách chuyển đổi dữ liệu khỏi nghiệp vụ. Cần công bố kiểu đầu vào và đầu ra; downstream không nên dựa vào những trường nội bộ không thuộc hợp đồng.
- **Router** tách quyết định đường đi khỏi handler. Cần xác định dữ liệu dùng để định tuyến và điều gì xảy ra khi không có tuyến phù hợp.
- **Filter** tách quy tắc chấp nhận thông điệp. Trong luồng request/reply, loại bỏ thông điệp mà không tạo phản hồi hoặc báo lỗi thích hợp có thể khiến caller đợi đến timeout.
- **Aggregator** gom nhiều thông điệp thành một kết quả. Hợp đồng phải có quy tắc tương quan, điều kiện giải phóng nhóm và xử lý nhóm không bao giờ nhận đủ phần tử.

Ví dụ, nếu thêm filter loại đơn có số lượng bằng 0 trước `OrderService`, không nên chỉ kiểm tra rằng handler không chạy. Cần kiểm tra cả hành vi mà caller quan sát: nhận lỗi nghiệp vụ, nhận kết quả từ chối, hay chờ hết thời gian theo thiết kế.

Tách component chỉ hữu ích khi hành vi giữa các bước vẫn có thể giải thích và kiểm thử được.

## 8. Hợp đồng dữ liệu quyết định mức liên kết thực tế

### 8.1. Dùng dữ liệu theo mục đích của luồng

Không nên gửi nguyên một JPA entity với lazy association vào mọi bước chỉ vì entity đã có sẵn. Consumer có thể vô tình phụ thuộc vào persistence context, trạng thái mutable hoặc cấu trúc bảng dữ liệu.

Một DTO hoặc record chứa đúng dữ liệu cần cho tác vụ thường tạo ranh giới dễ hiểu hơn. Tuy nhiên, việc thêm một DTO không tự đem lại tương thích: đổi ý nghĩa trường hoặc biến trường tùy chọn thành bắt buộc vẫn có thể phá vỡ consumer.

### 8.2. Dùng header có chủ đích

Header phù hợp với thông tin điều phối và metadata, chẳng hạn hệ thống nguồn hoặc mã tương quan. Dữ liệu nghiệp vụ cốt lõi như danh sách sản phẩm, số lượng và tiền tệ nên có vị trí rõ ràng trong hợp đồng payload.

Tránh để handler phụ thuộc ngầm vào một header chỉ được tạo bởi endpoint rất xa phía trước. Nếu header là bắt buộc, hãy ghi rõ nơi tạo, nơi kiểm tra, kiểu dữ liệu và cách xử lý khi thiếu.

Các đối tượng kỹ thuật như channel phản hồi trong luồng nội bộ JVM không phải là hợp đồng có thể tùy ý serialize qua mạng. Nếu chuyển sang broker, phải thiết kế lại ranh giới truyền tải và tương quan phản hồi phù hợp.

### 8.3. Phân biệt chấp nhận và hoàn thành

Một API trả `ACCEPTED` có thể chỉ xác nhận đã đưa việc vào xử lý. Một API trả `COMPLETED` có thể đòi hỏi toàn bộ nghiệp vụ đã xong. Đổi giữa hai ý nghĩa này mà giữ nguyên interface vẫn làm caller hiểu sai.

Nếu luồng trở thành bất đồng bộ dài hạn, có thể cần trả mã yêu cầu rồi cung cấp cách truy vấn trạng thái hoặc phát sự kiện kết quả. Đây là thay đổi hợp đồng sản phẩm, không chỉ là đổi `DirectChannel` thành `QueueChannel`.

## 9. Liên kết lỏng phải đi cùng hợp đồng lỗi

Trong ví dụ ban đầu dùng `DirectChannel`, lỗi kiểm tra số lượng phát sinh khi gateway đang gọi luồng có thể truyền trở lại caller. Không nên giả định một bean tên `errorChannel` sẽ tự tiếp nhận và nuốt mọi lỗi đồng bộ của ứng dụng.

Ở ranh giới poller hoặc tác vụ bất đồng bộ, lỗi không còn có thể đơn giản ném ngược trên thread gửi ban đầu. Spring Integration có các cơ chế biểu diễn lỗi bằng `ErrorMessage` và chuyển tới error channel theo ngữ cảnh, thành phần và cấu hình tương ứng.

Một thiết kế đầy đủ cần trả lời:

1. Caller nhận lỗi trực tiếp, nhận một phản hồi nghiệp vụ hay nhận kết quả sau?
2. Lỗi dữ liệu có được thử lại không, hay phải từ chối ngay?
3. Retry xảy ra quanh đúng bước lỗi hay quanh cả chuỗi có tác dụng phụ?
4. Nếu gateway timeout nhưng handler vẫn hoàn tất, hệ thống nhận biết kết quả muộn thế nào?
5. Nếu ghi cơ sở dữ liệu thành công nhưng gửi thông báo thất bại, có thể retry mà không tạo đơn trùng không?

Retry toàn bộ flow có thể lặp lại những thao tác đã thành công. Một endpoint riêng cho bước gửi thông báo giúp đặt retry đúng ranh giới, nhưng vẫn cần idempotency hoặc cơ chế ghi nhận thích hợp khi tác dụng phụ có thể lặp lại.

Ngoài lỗi, cần quan sát được đường đi thông điệp. Sử dụng mã tương quan nghiệp vụ nhất quán, đặt tên endpoint có ý nghĩa khi cần và theo dõi độ trễ, số lỗi, độ sâu hàng đợi. Nếu không, một luồng có nhiều component độc lập sẽ khó vận hành dù mã nguồn đã được tách tốt.

## 10. Kiểm thử theo ranh giới phụ thuộc

### 10.1. Kiểm thử đơn vị cho business handler

Ví dụ JUnit Jupiter sau không cần khởi động Spring:

```java
package example.orders;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class OrderServiceTest {
    private final OrderService service = new OrderService();

    @Test
    void acceptsPositiveQuantity() {
        OrderReceipt receipt = service.place(
            new PreparedOrder("REQ-001", "BOOK-01", 2)
        );

        assertEquals("REQ-001", receipt.requestId());
        assertEquals("ACCEPTED", receipt.status());
    }

    @Test
    void rejectsNonPositiveQuantity() {
        assertThrows(IllegalArgumentException.class, () -> service.place(
            new PreparedOrder("REQ-002", "BOOK-01", 0)
        ));
    }
}
```

Kiểm thử này xác nhận quy tắc nghiệp vụ, không xác nhận transformer hoặc cấu hình channel hoạt động đúng.

### 10.2. Kiểm thử hợp đồng xuyên qua gateway

Với dependency kiểm thử của Spring Boot, có thể kiểm tra wiring và kết quả quan sát được từ gateway:

```java
package example.orders;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

@SpringBootTest
class OrderFlowTest {
    @Autowired
    private OrderGateway gateway;

    @Test
    void normalizesProductCodeAndReturnsReceipt() {
        OrderReceipt receipt = gateway.submit(
            new OrderRequest("REQ-001", " book-01 ", 2)
        );

        assertNotNull(receipt);
        assertEquals("REQ-001", receipt.requestId());
        assertEquals("BOOK-01", receipt.productCode());
        assertEquals("ACCEPTED", receipt.status());
    }
}
```

Kiểm thử này phát hiện được gateway chưa được scan, channel đặt sai tên, transformer không chạy hoặc luồng không tạo phản hồi mong muốn.

Khi thêm queue, executor, router hoặc filter, bổ sung kiểm thử cho hành vi mới: quá tải, timeout, thông điệp bị từ chối, kết quả muộn và xử lý trùng. Với luồng bất đồng bộ, dùng cơ chế chờ có giới hạn thay vì `Thread.sleep()` tùy ý; tránh khẳng định thứ tự nếu thiết kế không bảo đảm thứ tự đó.

## 11. Những ngộ nhận thường gặp

| Ngộ nhận | Cách hiểu phù hợp |
|---|---|
| Có dependency injection là đã liên kết lỏng toàn diện | DI giảm phụ thuộc khởi tạo; hợp đồng dữ liệu, thời gian và điều phối vẫn cần thiết kế |
| Mọi channel đều là bất đồng bộ | `DirectChannel` thực thi trên thread gửi |
| Gateway luôn là lời gọi từ xa | Gateway có thể chỉ đi vào luồng trong cùng JVM |
| Đổi sang queue là caller không phải chờ | Gateway request/reply vẫn đợi kết quả theo hợp đồng |
| Message bất biến nên payload không thể đổi | Đối tượng payload có thể vẫn mutable |
| Mọi subscriber của `DirectChannel` đều nhận cùng thông điệp | Nó là cơ chế point-to-point, không phải phát tới mọi subscriber |
| Có `errorChannel` là mọi lỗi được xử lý thống nhất | Đường đi lỗi phụ thuộc ranh giới đồng bộ, bất đồng bộ và cấu hình |
| Tách nhiều endpoint luôn làm hệ thống tốt hơn | Mỗi ranh giới phải giúp cô lập thay đổi, kiểm thử hoặc vận hành |

Không cần biến mọi lời gọi hàm thành một thông điệp. Một phép tính cục bộ nhỏ thường dễ hiểu hơn dưới dạng phương thức thông thường. Spring Integration đem lại giá trị khi cần mô hình hóa rõ ràng các ranh giới chuyển đổi, định tuyến, tích hợp và điều phối.

## 12. Bài tập vận dụng

1. Tách phép chuẩn hóa mã sản phẩm thành một lớp riêng và kiểm thử nó không cần Spring. Giữ kiểm thử qua gateway để xác nhận luồng vẫn sử dụng phép chuẩn hóa đó.
2. Thêm bước kiểm tra yêu cầu trước nghiệp vụ. Xác định rõ caller quan sát gì với `quantity = 0`; không để bài tập chỉ kết thúc ở việc thông điệp biến mất.
3. Thay channel đầu vào bằng `QueueChannel` có sức chứa hữu hạn và thêm poller. Giải thích vì sao caller của `submit()` vẫn có thể phải chờ.
4. Giả lập xử lý chậm và mô tả trường hợp caller timeout nhưng nghiệp vụ tiếp tục. Đề xuất cách sử dụng `requestId` để nhận biết yêu cầu lặp lại.
5. Xác định nơi cần sửa khi thêm bước thông báo: caller, business handler hay cấu hình flow. Giải thích thêm hợp đồng lỗi và ý nghĩa kết quả trả về nếu bước thông báo thất bại.

Tiêu chí đánh giá là bạn chỉ ra được từng loại phụ thuộc đã giảm, từng hợp đồng còn tồn tại và hành vi caller có thể quan sát. Số lượng channel hoặc endpoint không phải thước đo trực tiếp của loose coupling.