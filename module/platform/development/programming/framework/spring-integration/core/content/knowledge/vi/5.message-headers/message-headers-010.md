# routingSlip

## Mục tiêu và phạm vi

Trong chương **Message headers** của module **SPRING_INTEGRATION_CORE**, bài này giải thích cách dùng header `routingSlip` để đưa một thông điệp qua nhiều bước xử lý. Người học sẽ cấu hình tuyến bằng Java DSL, theo dõi tiến độ, bổ sung bước xử lý có điều kiện và xác định nguyên nhân khi thông điệp không đến đích.

Ví dụ xuyên suốt là một đơn hàng đi qua kiểm tra dữ liệu, bổ sung thông tin và ghi nhận kiểm toán. Các thành phần nghiệp vụ trao đổi bằng `Message` và `MessageChannel`; một gateway có thể cung cấp giao diện gọi từ ứng dụng. Nội dung tập trung vào routing slip; transformer, filter, aggregator và xử lý lỗi được đề cập ở những điểm ảnh hưởng trực tiếp đến việc tiếp tục tuyến.

Ví dụ Java dùng cú pháp Java 17 và API Spring Integration 6.5.x, với thư viện được quản lý đồng bộ qua BOM hoặc cấu hình dependency của dự án. Cần có `spring-integration-core`; ví dụ kiểm thử dùng JUnit Jupiter. Đây là cấu hình độc lập để đọc và thực hành, không giả định dự án hiện tại đã khai báo các bean tương ứng.

## 1. Routing slip giải quyết vấn đề gì?

Giả sử ứng dụng nhận hai loại yêu cầu:

- Đơn thông thường: kiểm tra → bổ sung thông tin → kiểm toán.
- Đơn cần thẩm định: kiểm tra → bổ sung thông tin → thẩm định → kiểm toán.

Có thể nối các endpoint bằng kênh cố định và thêm router tại vị trí phân nhánh. Khi nhiều quy trình dùng lại cùng các bước theo thứ tự khác nhau, việc lặp cấu hình nối kênh làm cấu trúc khó theo dõi.

Mẫu **Routing Slip** gắn hành trình xử lý vào chính thông điệp. Mỗi bước hoàn thành công việc rồi sử dụng hành trình đó để tìm nơi chuyển tiếp. Tuyến có thể được chọn khi tiếp nhận yêu cầu, còn các bước nghiệp vụ được tái sử dụng. Đây là ý tưởng cốt lõi của mẫu [Routing Slip trong Enterprise Integration Patterns](https://www.enterpriseintegrationpatterns.com/patterns/messaging/RoutingTable.html).

Có thể hình dung một đơn hàng mang theo phiếu hành trình:

```text
payload:
  id = ORD-41

headers:
  businessKey = ORD-41
  routingSlip = hành trình cùng vị trí đang xét
  replyChannel = nơi nhận kết quả cuối
```

Trong ví dụ, payload mô tả đơn hàng, còn header điều khiển cách thông điệp đi qua hệ thống. Tách hai vai trò giúp bước kiểm tra đơn hàng không phải biết bước kế tiếp là kiểm toán hay thẩm định.

Một routing slip hữu ích khi thứ tự xử lý cần đi cùng từng yêu cầu. Nếu mọi yêu cầu luôn đi qua một chuỗi cố định, một `IntegrationFlow` nối trực tiếp thường dễ hiểu hơn.

## 2. Header `routingSlip` được dùng khi nào?

Tên header là `routingSlip`; trong Java nên tham chiếu bằng:

```java
IntegrationMessageHeaderAccessor.ROUTING_SLIP
```

Spring Integration sử dụng header này trong cơ chế chọn kênh ra của các handler tạo thông điệp phản hồi thuộc họ `AbstractMessageProducingHandler`. Khi endpoint đã có `outputChannel`, kênh đó được ưu tiên. Khi chưa có kênh ra, framework xét routing slip; khi tuyến hết mục, nó trở về cơ chế `replyChannel`. Xem [Routing Slip của Spring Integration](https://docs.spring.io/spring-integration/reference/6.5/router/routing-slip.html).

Với một endpoint xử lý đơn hàng, ta cần trả lời ba câu hỏi:

1. Endpoint có tạo kết quả để gửi tiếp không?
2. Endpoint có được nối sẵn với một kênh ra không?
3. Nếu cần dùng routing slip, thông điệp có còn giữ trạng thái tuyến không?

Ví dụ một service activator chỉ ghi log rồi trả về `void` không tạo kết quả tiếp theo. Header tuyến không biến phương thức đó thành bước request-reply. Tương tự, một filter loại thông điệp có thể kết thúc nhánh xử lý ngay tại đó.

Phân biệt các thành phần điều khiển:

| Thành phần | Vai trò trong ví dụ đơn hàng |
| --- | --- |
| `outputChannel` | Kênh ra đã gắn vào endpoint |
| `routingSlip` | Hành trình và vị trí chọn bước tiếp theo |
| `replyChannel` | Đích nhận kết quả sau khi hành trình hoàn tất |
| `errorChannel` | Đích cho thông điệp lỗi khi cơ chế xử lý lỗi tương ứng sử dụng nó |
| Router | Endpoint thực hiện quyết định định tuyến riêng |
| `correlationId` hoặc khóa nghiệp vụ | Liên kết các thông điệp cùng một yêu cầu |

Các header trên không thay thế cho nhau. Ví dụ, đặt khóa liên kết đơn hàng không giúp framework tự tìm được bước kiểm toán.

## 3. Giá trị header chứa cả đường đi và vị trí

Không nên coi giá trị runtime của `routingSlip` là một chuỗi như `"validateOrders;enrichOrders"`.

`RoutingSlipHeaderValueMessageProcessor` tạo giá trị dạng `Map<List<Object>, Integer>` với một phần tử: khóa là danh sách đường đi, giá trị là chỉ số ban đầu `0`. Đây là chi tiết cấu trúc được thể hiện trong [mã nguồn processor của Spring Integration](https://github.com/spring-projects/spring-integration/blob/6.5.x/spring-integration-core/src/main/java/org/springframework/integration/transformer/support/RoutingSlipHeaderValueMessageProcessor.java).

Biểu diễn minh họa:

```text
{
  ["validateOrders", "enrichOrders", "auditOrders"] -> 0
}
```

Sau khi chọn kênh kiểm tra:

```text
{
  ["validateOrders", "enrichOrders", "auditOrders"] -> 1
}
```

Chỉ số mô tả **mục kế tiếp cần xét khi chọn kênh**, không phải bằng chứng bước nghiệp vụ trước đã commit thành công. Trong luồng bất đồng bộ, một thông điệp đã mang chỉ số mới có thể còn nằm trong hàng đợi chờ xử lý.

Nếu một mục là tên kênh, chọn kênh đó sẽ tăng chỉ số. Nếu mục là strategy, framework giữ vị trí để strategy có thể tiếp tục quyết định ở lần sau; strategy trả về `null` hoặc chuỗi rỗng thì mới chuyển sang mục kế tiếp. Xem phần chọn tuyến trong [mã nguồn `AbstractMessageProducingHandler`](https://github.com/spring-projects/spring-integration/blob/6.5.x/spring-integration-core/src/main/java/org/springframework/integration/handler/AbstractMessageProducingHandler.java).

Với các mục đều là tên kênh, diễn tiến của ví dụ là:

| Vị trí chọn kênh | Chỉ số trước khi chọn | Đích được chọn | Chỉ số gửi kèm |
| --- | ---: | --- | ---: |
| Sau khi gắn header | 0 | `validateOrders` | 1 |
| Sau kiểm tra | 1 | `enrichOrders` | 2 |
| Sau bổ sung thông tin | 2 | `auditOrders` | 3 |
| Sau kiểm toán | 3 | Đích theo `replyChannel` | Tuyến đã hết mục |

Không sửa trực tiếp map hoặc danh sách lấy từ header. Hãy để framework quản lý tiến độ; nếu muốn bắt đầu một quy trình mới, cấu hình lại header tại một ranh giới rõ ràng.

## 4. Khai báo đường đi đúng bằng Java DSL

Java DSL cung cấp `HeaderEnricherSpec.routingSlip(...)`. Các đối số riêng biệt là các mục trong hành trình:

```java
.enrichHeaders(headers -> headers.routingSlip(
        "validateOrders",
        "enrichOrders",
        "auditOrders"))
```

API có cả overload nhận tham số `overwrite`. Khi không yêu cầu ghi đè và chưa thay đổi mặc định, header có sẵn được giữ lại. Chi tiết được mô tả trong [API `HeaderEnricherSpec`](https://docs.spring.io/spring-integration/api/org/springframework/integration/dsl/HeaderEnricherSpec.html) và [triển khai của nhánh 6.5.x](https://github.com/spring-projects/spring-integration/blob/6.5.x/spring-integration-core/src/main/java/org/springframework/integration/dsl/HeaderEnricherSpec.java).

Ba cách sau có ý nghĩa khác nhau:

```java
// Đúng: ba mục trong đường đi.
headers.routingSlip("validateOrders", "enrichOrders", "auditOrders");

// Tránh: chỉ truyền một chuỗi cho Java DSL,
// không biểu đạt ba mục riêng theo cách trên.
headers.routingSlip("validateOrders;enrichOrders;auditOrders");

// Sai về giá trị runtime mà cơ chế routing slip cần đọc:
// chỉ tạo header chuỗi thông thường.
headers.header("routingSlip", "validateOrders;enrichOrders;auditOrders");
```

Dấu chấm phẩy xuất hiện trong cú pháp cấu hình XML của routing slip. Không áp dụng nguyên chuỗi XML đó cho tham số varargs của Java DSL.

Trong các ví dụ bên dưới, mọi mục tuyến đều dùng tên bean kênh hoặc tên bean strategy do ứng dụng định nghĩa. Cách đặt tên có chủ ý như `validateOrders` giúp phân biệt kênh xử lý với tên flow `validationFlow`.

### Chọn có giữ tuyến cũ hay không

Nếu một thông điệp đã đi nửa hành trình quay về điểm gắn header, cần quyết định rõ:

- Tiếp tục hành trình đang có: giữ header cũ.
- Khởi tạo hành trình mới tại điểm vào do ứng dụng quản lý: ghi đè có chủ ý.
- Phát hiện yêu cầu không hợp lệ: từ chối và ghi nhận nguyên nhân.

Ví dụ khởi tạo lại tuyến:

```java
.enrichHeaders(headers -> headers.routingSlip(
        true,
        "validateOrders",
        "enrichOrders",
        "auditOrders"))
```

Trong ví dụ này, `true` là tham số ghi đè. Không đặt thao tác khởi tạo lại ở mọi bước: một thông điệp quay vòng có thể bị đưa về đầu tuyến liên tục.

## 5. Ví dụ đầy đủ: đơn hàng đi qua ba bước

Cấu hình sau khai báo các kênh và từng flow xử lý độc lập. Các flow nghiệp vụ kết thúc ngay sau endpoint tạo kết quả để việc chọn kênh kế tiếp dựa vào routing slip.

Lưu thành `OrderRoutingConfiguration.java` khi thực hành trong một dự án có các dependency nêu ở đầu bài:

```java
package com.example.routingslip;

import java.util.ArrayList;
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
public class OrderRoutingConfiguration {

    public record Order(
            String id,
            boolean reviewRequired,
            boolean reviewed,
            List<String> steps) {

        public Order {
            steps = List.copyOf(steps);
        }

        public Order recordStep(String step) {
            List<String> nextSteps = new ArrayList<>(steps);
            nextSteps.add(step);
            return new Order(id, reviewRequired, reviewed, nextSteps);
        }

        public Order markReviewed() {
            return new Order(id, reviewRequired, true, steps)
                    .recordStep("review");
        }
    }

    @Bean
    public MessageChannel ordersInput() {
        return new DirectChannel();
    }

    @Bean
    public MessageChannel validateOrders() {
        return new DirectChannel();
    }

    @Bean
    public MessageChannel enrichOrders() {
        return new DirectChannel();
    }

    @Bean
    public MessageChannel auditOrders() {
        return new DirectChannel();
    }

    @Bean
    public IntegrationFlow orderEntryFlow() {
        return IntegrationFlow.from("ordersInput")
                .enrichHeaders(headers -> headers.routingSlip(
                        "validateOrders",
                        "enrichOrders",
                        "auditOrders"))
                .get();
    }

    @Bean
    public IntegrationFlow validationFlow() {
        return IntegrationFlow.from("validateOrders")
                .<Order, Order>transform(order -> {
                    if (order.id() == null || order.id().isBlank()) {
                        throw new IllegalArgumentException(
                                "Mã đơn hàng không được rỗng");
                    }
                    return order.recordStep("validate");
                })
                .get();
    }

    @Bean
    public IntegrationFlow enrichmentFlow() {
        return IntegrationFlow.from("enrichOrders")
                .handle(Order.class, (order, headers) ->
                        order.recordStep("enrich"))
                .get();
    }

    @Bean
    public IntegrationFlow auditFlow() {
        return IntegrationFlow.from("auditOrders")
                .handle(Order.class, (order, headers) ->
                        order.recordStep("audit"))
                .get();
    }
}
```

Danh sách `steps` giúp quan sát thứ tự thực thi trong bài học. Trong ứng dụng thực, hai handler sau có thể tra cứu thông tin khách hàng và ghi nhận kiểm toán; các tác vụ có tác dụng phụ cần thiết kế riêng về giao dịch và chống xử lý trùng.

Các điểm cần theo dõi trong cấu hình:

- Header enricher là endpoint cuối của flow đầu vào. Sau khi tạo thông điệp đã có tuyến, nó có thể chọn `validateOrders`.
- Transformer kiểm tra trả về một `Order` mới.
- Hai service activator đều trả về `Order` để tạo phản hồi.
- Không có kênh cố định nằm sau các endpoint này.
- Các tên trong tuyến trùng với tên bean kênh, không phải tên các bean `IntegrationFlow`.

`DirectChannel` thực thi consumer trên luồng gửi trong cách sử dụng thông thường của ví dụ. Nếu thay bằng `QueueChannel`, cần cấu hình poller cho endpoint tiêu thụ hàng đợi. Đặc tính thực thi do loại kênh quyết định; xem [các triển khai MessageChannel](https://docs.spring.io/spring-integration/reference/6.5/channel/implementations.html).

### Vì sao không nối tất cả thành một flow dài?

Xét đoạn cấu hình khác:

```java
return IntegrationFlow.from("ordersInput")
        .enrichHeaders(headers -> headers.routingSlip(
                "validateOrders",
                "auditOrders"))
        .handle(Order.class, (order, headers) ->
                order.recordStep("fixed-stage"))
        .channel("fixedOutput")
        .get();
```

Ở đây DSL đã nối header enricher sang handler kế tiếp và nối handler đó tới `fixedOutput`. Các kết nối này tạo kênh ra cho endpoint tương ứng. Chỉ gắn routing slip không làm chúng tự chuyển sang kênh kiểm tra.

Có thể phối hợp một đoạn xử lý cố định với một đoạn dùng routing slip, nhưng cần xác định endpoint nào thực sự giao quyền chọn bước tiếp theo cho header. Tách các flow ngắn trong ví dụ chính giúp nhìn rõ điểm đó.

## 6. Gửi yêu cầu và nhận phản hồi cuối

Khi gửi trực tiếp vào `ordersInput`, phía gửi cần cung cấp nơi nhận kết quả. Đoạn sau chạy bên trong mã đã có `ApplicationContext`:

```java
import java.util.List;

import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.support.MessageBuilder;

import com.example.routingslip.OrderRoutingConfiguration.Order;

// context là ApplicationContext đã nạp OrderRoutingConfiguration.
MessageChannel input =
        context.getBean("ordersInput", MessageChannel.class);

QueueChannel replies = new QueueChannel(1);

Message<Order> request = MessageBuilder
        .withPayload(new Order("ORD-41", false, false, List.of()))
        .setHeader("businessKey", "ORD-41")
        .setHeader(MessageHeaders.REPLY_CHANNEL, replies)
        .build();

if (!input.send(request, 1_000)) {
    throw new IllegalStateException("Không gửi được yêu cầu");
}

Message<?> response = replies.receive(1_000);
if (response == null) {
    throw new IllegalStateException("Chưa nhận được kết quả");
}

Order result = (Order) response.getPayload();
// result.steps() = ["validate", "enrich", "audit"]
```

Khi bước kiểm toán hoàn thành, danh sách không còn mục kênh nào để chọn nên kết quả đi theo `replyChannel`.

Hàng đợi nhận kết quả có dung lượng một vì mỗi lần gọi trong ví dụ dùng một hàng đợi riêng. Khi dùng chung kênh trả lời cho nhiều yêu cầu đồng thời, phải có cơ chế đối chiếu phản hồi với yêu cầu.

### Nếu ứng dụng gọi qua gateway

Có thể để gateway quản lý cơ chế request-reply thay cho mã tự tạo hàng đợi:

```java
package com.example.routingslip;

import org.springframework.integration.annotation.MessagingGateway;

import com.example.routingslip.OrderRoutingConfiguration.Order;

@MessagingGateway(
        defaultRequestChannel = "ordersInput",
        defaultReplyTimeout = "2000")
public interface OrderGateway {

    Order process(Order order);
}
```

Cần đăng ký interface bằng cơ chế quét gateway thích hợp, chẳng hạn `@IntegrationComponentScan` trên cấu hình nằm trong package tương ứng. Gateway tạo kênh trả lời tạm cho lời gọi request-reply; xem [Messaging Gateways](https://docs.spring.io/spring-integration/reference/6.5/gateway.html).

Không thêm một `replyChannel` chung tại điểm vào chỉ để routing slip hoạt động nếu gateway đã quản lý phản hồi cho từng lời gọi. Việc thay địa chỉ phản hồi cần xuất phát từ thiết kế luồng.

Thời gian chờ nhận phản hồi không đồng nghĩa với khả năng hủy công việc đang chạy. Đặc biệt trong ví dụ đồng bộ, xử lý nghiệp vụ có thể diễn ra ngay trong lời gọi gửi; timeout nhận kết quả không phải giới hạn thời gian thực thi cho từng service.

## 7. Thêm bước thẩm định bằng `RoutingSlipRouteStrategy`

Một mục trong đường đi có thể là tên bean triển khai `RoutingSlipRouteStrategy`. Phương thức quan trọng là:

```java
Object getNextPath(Message<?> requestMessage, Object reply);
```

Strategy được hỏi lại cho đến khi trả về `null` hoặc chuỗi rỗng. `requestMessage` là thông điệp đầu vào của endpoint đang tạo phản hồi. `reply` có thể là đối tượng nghiệp vụ, `Message<?>` hoặc `AbstractIntegrationMessageBuilder<?>`; không nên luôn ép nó thành `Message`. Xem [hợp đồng `RoutingSlipRouteStrategy`](https://docs.spring.io/spring-integration/api/org/springframework/integration/routingslip/RoutingSlipRouteStrategy.html).

Trong bài này, strategy chỉ trả về tên một kênh hoặc `null`. Quy tắc nghiệp vụ là:

```text
Đơn cần thẩm định và chưa được thẩm định:
    gửi tới reviewOrders

Các trường hợp khác:
    kết thúc mục strategy, chuyển sang bước kiểm toán
```

Tạo cấu hình bổ sung:

```java
package com.example.routingslip;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.routingslip.RoutingSlipRouteStrategy;
import org.springframework.integration.support.AbstractIntegrationMessageBuilder;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;

import com.example.routingslip.OrderRoutingConfiguration.Order;

@Configuration
public class ReviewRoutingConfiguration {

    @Bean
    public MessageChannel reviewOrders() {
        return new DirectChannel();
    }

    @Bean
    public RoutingSlipRouteStrategy optionalReviewRoute() {
        return (requestMessage, reply) -> {
            Object candidate = reply;

            if (candidate instanceof Message<?> message) {
                candidate = message.getPayload();
            }
            else if (candidate
                    instanceof AbstractIntegrationMessageBuilder<?> builder) {
                candidate = builder.getPayload();
            }

            if (!(candidate instanceof Order order)) {
                throw new IllegalArgumentException(
                        "Strategy cần kết quả kiểu Order");
            }

            return order.reviewRequired() && !order.reviewed()
                    ? "reviewOrders"
                    : null;
        };
    }

    @Bean
    public IntegrationFlow reviewFlow() {
        return IntegrationFlow.from("reviewOrders")
                .<Order, Order>transform(Order::markReviewed)
                .get();
    }
}
```

Sau đó **thay danh sách tuyến trong `orderEntryFlow()`**, không thêm một flow đầu vào thứ hai:

```java
.enrichHeaders(headers -> headers.routingSlip(
        "validateOrders",
        "enrichOrders",
        "optionalReviewRoute",
        "auditOrders"))
```

Nạp cả hai lớp cấu hình. Khi đơn có `reviewRequired = true`, diễn tiến quanh strategy là:

| Thời điểm | Vị trí đang xét | Kết quả strategy | Diễn tiến |
| --- | ---: | --- | --- |
| Sau bổ sung thông tin | 2 | `"reviewOrders"` | Gửi tới bước thẩm định, giữ vị trí 2 |
| Sau thẩm định | 2 | `null` | Tiến sang mục kiểm toán |
| Sau kiểm toán | Tuyến đã hết | Không gọi strategy nữa | Trả kết quả cho caller |

Với đơn không cần thẩm định, strategy trả về `null` ngay lần đầu và bước kiểm toán nhận đơn trực tiếp.

### Điều kiện kết thúc phải đi cùng trạng thái nghiệp vụ

Nếu strategy luôn trả về `"reviewOrders"`, mỗi lần bước thẩm định tạo phản hồi, strategy lại chọn chính kênh đó. Trong cấu hình đồng bộ, chu trình như vậy có thể tiếp tục cho đến khi lỗi do gọi lồng nhau quá sâu.

`markReviewed()` trong ví dụ đổi `reviewed` thành `true` trước khi trả kết quả. Điều kiện này làm strategy kết thúc cho riêng đơn hàng đó.

Không dùng một biến như `private int nextStep` trong bean strategy singleton để ghi tiến độ chung. Hai đơn hàng chạy xen kẽ sẽ tác động vào cùng biến. Ưu tiên quyết định từ thông điệp hiện tại và kết quả xử lý; nếu cần lưu trạng thái dài hạn, khóa trạng thái theo định danh quy trình và xử lý đồng thời có chủ ý.

Cũng cần phân biệt hai tình huống:

- Đọc `requestMessage`: quan sát dữ liệu trước endpoint hiện tại.
- Đọc `reply`: quan sát kết quả endpoint vừa tạo.

Nếu bước thẩm định đã đổi trạng thái nhưng strategy vẫn kiểm tra payload cũ trong request, nó có thể quyết định thẩm định lại. Strategy mẫu kiểm tra kết quả mới vì đó là dữ liệu chứa `reviewed = true`.

## 8. Dùng SpEL và hiểu ngữ cảnh biểu thức

Có thể biểu diễn quy tắc ngắn bằng `ExpressionEvaluatingRoutingSlipRouteStrategy`. Root của biểu thức cung cấp hai thuộc tính `request` và `reply`; chi tiết có trong [triển khai strategy biểu thức](https://github.com/spring-projects/spring-integration/blob/6.5.x/spring-integration-core/src/main/java/org/springframework/integration/routingslip/ExpressionEvaluatingRoutingSlipRouteStrategy.java).

Vì các endpoint trong ví dụ trả về trực tiếp `Order`, có thể thay bean strategy Java ở phần trước bằng bean sau, giữ nguyên tên:

```java
@Bean
public ExpressionEvaluatingRoutingSlipRouteStrategy optionalReviewRoute() {
    return new ExpressionEvaluatingRoutingSlipRouteStrategy(
            "reply.reviewRequired() && !reply.reviewed() "
                    + "? 'reviewOrders' : null");
}
```

Import cho kiểu trên là:

```java
import org.springframework.integration.routingslip
        .ExpressionEvaluatingRoutingSlipRouteStrategy;
```

Đây là phương án thay thế bean `optionalReviewRoute`, không khai báo cả hai bean cùng tên.

Nếu sau này endpoint trả về một `Message<Order>`, biểu thức cần đọc payload của message, chẳng hạn `reply.payload.reviewRequired()`. Khi kiểu phản hồi đa dạng hoặc quy tắc dài, strategy Java có kiểm tra kiểu như phần trước dễ bảo trì hơn.

Không nhầm ngữ cảnh này với một biểu thức đánh giá trực tiếp trên message ở header enricher. Trong strategy biểu thức, `request.headers['businessKey']` truy cập header của yêu cầu; `reply` là kết quả đang được dùng để chọn bước tiếp theo.

### Tránh để biểu thức trở thành dữ liệu điều khiển từ bên ngoài

Nếu hệ thống nhận HTTP, sự kiện từ broker hoặc dữ liệu đối tác, hãy nhận một giá trị nghiệp vụ hữu hạn như `STANDARD` hay `REQUIRES_REVIEW`, rồi ánh xạ sang tuyến do ứng dụng quản lý.

Không đưa nguyên văn chuỗi do bên gửi cung cấp vào cấu hình SpEL hoặc xem đó là tên bean tùy ý. Trong ví dụ này, tên kênh và tên strategy là cấu hình nội bộ; dữ liệu khách hàng chỉ ảnh hưởng điều kiện `reviewRequired`.

## 9. Header qua các endpoint và ranh giới lưu trữ

### 9.1. Bảo toàn thông tin cần để tiếp tục

Header enricher bổ sung metadata mà không cần viết transformer riêng chỉ để đặt header; xem [Header Enricher](https://docs.spring.io/spring-integration/reference/6.5/content-enrichment.html).

Trong chuỗi xử lý, cần theo dõi ít nhất tuyến hiện tại, địa chỉ phản hồi và khóa liên kết nghiệp vụ. Một phép biến đổi payload có thể hoàn toàn đúng về nghiệp vụ nhưng cấu hình loại header sau đó vẫn khiến kết quả không tìm được nơi gửi tiếp.

Đặc biệt kiểm tra:

- Header filter có đang loại `routingSlip` hoặc `replyChannel` không.
- Handler có cấu hình chặn truyền header không.
- Adapter có ánh xạ các header cần thiết qua giao thức hay không.
- Một đoạn mã tự tạo thông điệp mới có bảo toàn metadata theo hợp đồng luồng không.

Cơ chế sao chép header phụ thuộc loại handler và cấu hình; API cho phép chỉ định các mẫu header không truyền tiếp. Xem [API `AbstractMessageProducingHandler`](https://docs.spring.io/spring-integration/docs/6.5.x/api/org/springframework/integration/handler/AbstractMessageProducingHandler.html).

Không kết luận rằng mọi `MessageBuilder.withPayload(...)` đều làm mất header: handler có thể bổ sung header từ request. Hãy kiểm tra thông điệp thực tế tại ranh giới đang gặp vấn đề.

### 9.2. Đi qua broker hoặc `MessageStore`

Biểu thức nội tuyến có thể được chuyển thành đối tượng strategy nằm trong header. Strategy biểu thức phụ thuộc hạ tầng Spring và không phù hợp để mang trực tiếp qua cơ chế Java serialization. Đăng ký strategy thành bean rồi đưa **tên bean** vào tuyến là cách được tài liệu [Routing Slip](https://docs.spring.io/spring-integration/reference/6.5/router/routing-slip.html) khuyến nghị cho tình huống này.

Chọn tên bean mới chỉ giải quyết một phần thiết kế. Với một luồng đi qua broker, cần xác định:

| Vấn đề | Quyết định cần có |
| --- | --- |
| Dạng dữ liệu truyền đi | Serializer có hỗ trợ cấu trúc tuyến đã chọn không |
| Ánh xạ header | Adapter có chuyển header đó theo cấu hình không |
| Tên đích | Consumer có kênh và strategy tương ứng không |
| Nâng cấp cấu hình | Thông điệp cũ được xử lý bằng phiên bản quy trình nào |
| Địa chỉ phản hồi | Có thể sử dụng hợp lệ sau ranh giới tiến trình không |
| Thực thi lại | Bước nào có thể chạy lại mà không tạo tác dụng phụ trùng |

Kênh trả lời tạm bên trong một JVM không tự trở thành một địa chỉ có ý nghĩa ở JVM khác. Một tuyến xử lý đơn hàng lưu lâu ngày thường cần định danh quy trình, phiên bản và trạng thái nghiệp vụ rõ ràng, thay vì chỉ dựa vào tên bean runtime.

Routing slip giúp xác định bước tiếp theo; chính sách phân phối, lưu trữ, giao dịch và chống trùng vẫn phải được thiết kế cho các hệ thống tham gia.

## 10. Xử lý lỗi và các điểm dừng của tuyến

### 10.1. Lỗi trong cấu hình đồng bộ

Ví dụ chính sử dụng `DirectChannel`. Nếu bước kiểm tra ném lỗi, caller gửi yêu cầu có thể nhận exception trên cùng chuỗi gọi. Chỉ đặt header `errorChannel` không tự chuyển mọi exception đồng bộ thành thông điệp lỗi.

Trong xử lý bất đồng bộ, poller và các thành phần có cơ chế xuất bản lỗi có thể tạo `ErrorMessage`, chọn kênh theo header `errorChannel` hoặc kênh lỗi mặc định. Gateway cũng có cấu hình xử lý lỗi riêng. Xem [Error Handling](https://docs.spring.io/spring-integration/reference/6.5/error-handling.html).

Với đơn có mã rỗng, kỳ vọng nghiệp vụ của bài là:

1. Kiểm tra dữ liệu thất bại.
2. Không bổ sung thông tin và không kiểm toán như một đơn thành công.
3. Caller hoặc nhánh xử lý lỗi nhận được nguyên nhân phù hợp với cấu hình.

### 10.2. Chỉ số tuyến không thay thế nhật ký hoàn tất

Một thông điệp gửi vào bước kiểm toán có thể đã mang vị trí sau mục kiểm toán, trong khi thao tác ghi kiểm toán còn chưa thành công.

Vì vậy, khi thiết kế retry, phải xác định retry diễn ra ở đâu: gọi lại tác vụ của endpoint hiện tại, gửi lại thông điệp vào kênh hiện tại, hay bắt đầu lại yêu cầu từ đầu. Mỗi lựa chọn có khả năng lặp tác dụng phụ khác nhau.

Ví dụ đơn hàng đã được ghi vào hệ thống thanh toán rồi lỗi khi ghi kiểm toán: bắt đầu lại từ đầu có thể thanh toán hai lần nếu bước thanh toán không chống trùng. Dùng khóa nghiệp vụ như `orderId` và chính sách idempotency phù hợp với từng hệ thống.

### 10.3. Endpoint không tạo phản hồi

Một số điểm dừng cần phân biệt:

| Tình huống | Hệ quả cần xem xét |
| --- | --- |
| Service activator trả `void` hoặc không có kết quả | Không có phản hồi để tiếp tục; có thể phát sinh lỗi nếu bật yêu cầu phải có reply |
| Filter từ chối thông điệp | Tuyến chính dừng; cần thiết kế discard hoặc lỗi theo nghiệp vụ |
| Aggregator chưa đủ điều kiện release | Chưa tạo kết quả tổng hợp để đi tiếp |
| Routing slip hết mục nhưng thiếu địa chỉ phản hồi | Endpoint tạo kết quả có thể không tìm được kênh gửi |
| Kênh đích không có consumer thích hợp | Gửi có thể thất bại hoặc thông điệp chờ trong hàng đợi, tùy loại kênh |

Nếu dùng splitter/aggregator, thiết kế rõ header nào nằm trên kết quả sau tổng hợp. Một kết quả tổng hợp có thể đại diện nhiều thông điệp con; hành trình của một thông điệp con không tự trở thành hành trình nghiệp vụ đúng cho toàn bộ nhóm.

## 11. Kiểm thử thứ tự, phản hồi và điều kiện kết thúc

Một kiểm thử hữu ích cần xác nhận đầu ra quan sát được. Với tuyến tĩnh, kiểm tra thứ tự bước, khóa nghiệp vụ và việc nhận đúng một kết quả.

Ví dụ dưới dùng trực tiếp Spring context và JUnit Jupiter, nạp cấu hình ba bước ở phần 5:

```java
package com.example.routingslip;

import java.util.List;

import org.junit.jupiter.api.Test;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.support.MessageBuilder;

import com.example.routingslip.OrderRoutingConfiguration.Order;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class OrderRoutingTest {

    @Test
    void shouldFollowTheSlipAndReturnOneReply() {
        try (var context = new AnnotationConfigApplicationContext(
                OrderRoutingConfiguration.class)) {

            MessageChannel input = context.getBean(
                    "ordersInput", MessageChannel.class);
            QueueChannel replies = new QueueChannel(2);

            Message<Order> request = MessageBuilder
                    .withPayload(new Order(
                            "ORD-41", false, false, List.of()))
                    .setHeader("businessKey", "ORD-41")
                    .setHeader(MessageHeaders.REPLY_CHANNEL, replies)
                    .build();

            assertTrue(input.send(request, 1_000));

            Message<?> reply = replies.receive(1_000);
            assertNotNull(reply);

            Order result = (Order) reply.getPayload();
            assertEquals("ORD-41", result.id());
            assertEquals(
                    List.of("validate", "enrich", "audit"),
                    result.steps());
            assertEquals("ORD-41",
                    reply.getHeaders().get("businessKey"));
            assertNull(replies.receive(0));
        }
    }
}
```

Không cần mock khi các handler mẫu chỉ biến đổi dữ liệu trong bộ nhớ. Với tác vụ gọi hệ thống ngoài, có thể thay hoặc mock các thành phần liên quan bằng công cụ của [Spring Integration Test](https://docs.spring.io/spring-integration/reference/6.5/testing.html).

Sau khi chuyển sang tuyến có strategy, bổ sung các tình huống sau trong dự án thực hành:

| Tình huống | Kỳ vọng quan sát được |
| --- | --- |
| Đơn không cần thẩm định | `validate`, `enrich`, `audit` |
| Đơn cần thẩm định và chưa được thẩm định | `validate`, `enrich`, `review`, `audit`; kết quả có `reviewed = true` |
| Đơn đã được thẩm định | Không gọi lại bước `review` |
| Mã đơn rỗng | Phát sinh lỗi; không có kết quả thành công |
| Hai đơn có nhu cầu thẩm định khác nhau chạy đồng thời | Mỗi đơn đi đúng tuyến, không dùng chung tiến độ |
| Header tuyến có sẵn tại đầu vào | Hành vi giữ hoặc ghi đè đúng với lựa chọn thiết kế |
| Endpoint bị nối thêm kênh cố định | Kết quả kiểm thử thể hiện đúng tác động của kết nối mới |

Với strategy, kiểm thử trực tiếp các dạng `reply` mà hệ thống thực sự có thể tạo: domain object, `Message` và builder nếu sử dụng. Điều quan trọng là trạng thái sau xử lý làm strategy dừng đúng lúc.

Đặt timeout hữu hạn cho thao tác nhận trong kiểm thử để không treo tiến trình. Tuy nhiên, timeout nhận không ngắt một vòng lặp đồng bộ đang xảy ra trong `send()`; nên kiểm tra điều kiện kết thúc của strategy bằng kiểm thử đơn vị trước khi chạy cả tuyến.

## 12. Chẩn đoán nhanh khi tuyến không như dự kiến

| Triệu chứng | Điểm kiểm tra đầu tiên | Hướng xử lý |
| --- | --- | --- |
| Header có tuyến nhưng thông điệp vẫn vào một kênh cố định | Kênh ra do DSL hoặc annotation đã cấu hình | Xác định endpoint phải chọn đích theo routing slip |
| Lỗi kiểu dữ liệu header | Giá trị `routingSlip` có phải chuỗi hoặc danh sách tự gắn không | Dùng API chuyên dụng để tạo header |
| Lỗi biểu thức ngay khi khởi tạo tuyến | Tên bean trong tuyến có bị viết sai không | Kiểm tra tên kênh/strategy; chuỗi không khớp bean có thể bị xử lý như SpEL |
| Một bước chạy lặp lại | Strategy có điều kiện kết thúc và đọc đúng kết quả mới không | Sửa trạng thái nghiệp vụ và nhánh trả `null` |
| Caller không nhận được kết quả | Endpoint cuối có reply và địa chỉ phản hồi còn hợp lệ không | Theo dõi bước cuối, header và cơ chế gateway |
| Thông điệp nằm yên sau khi đổi loại kênh | Có consumer và poller cho kênh hàng đợi không | Cấu hình cơ chế tiêu thụ tương ứng |
| Lỗi khi lưu message hoặc gửi qua broker | Header có chứa đối tượng strategy/kênh runtime không | Dùng tên bean phù hợp và xác định hợp đồng serialization |
| Các đơn ảnh hưởng hành trình của nhau | Strategy có biến trạng thái dùng chung không | Tách trạng thái theo yêu cầu/quy trình |

Khi ghi log, nên kèm mã đơn hoặc khóa liên kết, tên bước đang chạy và kết quả quyết định tuyến. Chỉ số routing slip giúp xem luồng điều khiển; nhật ký nghiệp vụ giúp biết tác vụ nào thực sự hoàn tất.

## 13. Tiêu chí chọn routing slip cho một thiết kế

Dùng routing slip khi cần mang theo hành trình cho từng thông điệp và có thể xác định rõ cách mỗi bước trả kết quả. Chuỗi đơn hàng trong bài cho phép tái sử dụng cùng bước kiểm tra và kiểm toán, đồng thời chèn bước thẩm định có điều kiện.

Khi đánh giá một thiết kế cụ thể, cần chốt:

- Điểm nào tạo tuyến và điểm nào được phép thay tuyến.
- Endpoint nào có kênh ra cố định, endpoint nào chọn kênh theo header.
- Cách từng bước tạo phản hồi và duy trì metadata.
- Điều kiện nào bảo đảm strategy kết thúc cho từng thông điệp.
- Nơi nhận kết quả, nơi xử lý lỗi và ý nghĩa của việc thực thi lại.

Một quy trình cần chờ nhiều ngày, tương tác người dùng, bù trừ nhiều giao dịch và khôi phục sau nhiều lần triển khai cần thêm cơ chế quản lý trạng thái quy trình. Routing slip có thể tham gia làm cơ chế chọn bước, còn các yêu cầu vận hành đó phải được đáp ứng bằng thiết kế riêng.

Sau khi thực hành, người học cần giải thích được đường đi của một đơn hàng từ `ordersInput` đến caller, chỉ ra endpoint nào đọc routing slip, và dự đoán ảnh hưởng của việc thêm kênh cố định, bỏ phản hồi hoặc dùng strategy không có điều kiện dừng.
