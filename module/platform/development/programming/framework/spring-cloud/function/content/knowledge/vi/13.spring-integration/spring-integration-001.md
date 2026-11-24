# Quan hệ giữa mô hình hàm và Enterprise Integration Patterns

## 1. Bối cảnh và mục tiêu

**Spring Cloud Function (SCF)** cho phép biểu diễn logic nghiệp vụ bằng ba giao diện Java quen thuộc:

- **`Supplier<T>`**: tạo dữ liệu, không nhận tham số đầu vào; thường là nguồn phát.
- **`Function<T, R>`**: nhận `T` và trả về `R`; phù hợp cho biến đổi, chuẩn hóa, tính toán, phân loại.
- **`Consumer<T>`**: nhận `T` và thực hiện tác động, không trả về kết quả; thường là điểm cuối xử lý.

SCF quản lý các hàm qua **`FunctionCatalog`**, hỗ trợ **composition** (ghép hàm) và cho phép dùng cùng một logic phía sau những adapter khác nhau như HTTP, message broker hoặc nền tảng serverless. Mục tiêu là giữ logic nghiệp vụ không phụ thuộc giao thức gọi.

**Enterprise Integration Patterns (EIP)** là tập mẫu thiết kế để kết nối các hệ thống bằng thông điệp: *Message Channel*, *Message Translator*, *Content-Based Router*, *Message Filter*, *Splitter*, *Aggregator*, *Publish-Subscribe Channel*, *Service Activator*, *Error Channel*... **Spring Integration** hiện thực nhiều EIP trong hệ sinh thái Spring.

Hai cách tiếp cận bổ sung cho nhau:

> **Hàm** trả lời câu hỏi “Xử lý dữ liệu này như thế nào?”; **EIP** trả lời câu hỏi “Thông điệp đến từ đâu, đi theo đường nào, chia/gộp ra sao và được xử lý lỗi như thế nào?”.

Đến cuối bài, bạn có thể phân định vai trò của SCF và Spring Integration, ánh xạ các kiểu hàm sang những mẫu EIP liên quan, thiết kế một luồng có định tuyến và nhận ra nơi cần thêm hạ tầng điều phối.

## 2. Hai lớp trách nhiệm trong cùng một hệ thống

Một hệ thống xử lý đơn hàng có thể nhận sự kiện từ HTTP, Kafka hoặc hệ thống nội bộ. Dù nguồn nào, quy tắc “đơn trên một triệu đồng là ưu tiên” vẫn nên nằm trong một hàm độc lập.

~~~mermaid
flowchart LR
    A["HTTP / broker / scheduler"] --> B["Inbound adapter"]
    B --> C["Message Channel"]
    C --> D["FunctionCatalog<br/>validateOrder | classifyOrder"]
    D --> E{"Content-Based Router"}
    E -->|PRIORITY| F["Kênh ưu tiên"]
    E -->|STANDARD| G["Kênh thường"]
    F --> H["Consumer / outbound adapter"]
    G --> I["Consumer / outbound adapter"]
    C -. lỗi ở endpoint .-> J["Error flow / retry / DLQ"]
    D -. lỗi khi gọi hàm .-> J
~~~

Có ba tầng cần phân biệt:

1. **Hàm nghiệp vụ:** `validateOrder`, `classifyOrder`, `calculatePrice`... được định nghĩa bằng `Function`; logic nên kiểm thử được chỉ bằng giá trị đầu vào và đầu ra.
2. **Điều phối thông điệp:** channel, filter, router, splitter, aggregator, error flow... được triển khai bằng Spring Integration hoặc thành phần tích hợp tương đương.
3. **Kết nối môi trường:** inbound/outbound adapter, HTTP endpoint, binder của Spring Cloud Stream hoặc serverless adapter đưa dữ liệu vào/ra. SCF cung cấp mô hình hàm chung, nhưng không tự tạo đầy đủ các thành phần EIP chỉ vì có bean kiểu `Function`.

**Lưu ý:** Spring Cloud Function có thể chạy độc lập, không bắt buộc dùng Spring Integration. Khi chỉ cần chuỗi biến đổi đồng bộ, composition có thể là đủ. Khi cần kênh, nhiều nhánh, fan-out, tương quan thông điệp hoặc xử lý lỗi theo hạ tầng, EIP trở nên cần thiết.

## 3. Ánh xạ mô hình hàm với các Enterprise Integration Patterns

| Enterprise Integration Pattern | Liên hệ với mô hình hàm | Điều cần bổ sung khi triển khai thực tế |
| --- | --- | --- |
| **Message Endpoint / Service Activator** | `Consumer<T>` có thể là nơi nhận và xử lý một payload; `Function<T,R>` có thể xử lý và sinh phản hồi. | Adapter/endpoint quyết định cách nhận, xác nhận và trả lời thông điệp. |
| **Message Translator / Content Enricher** | `Function<T,R>` biểu diễn tự nhiên phép đổi cấu trúc hoặc bổ sung dữ liệu. | Chuyển đổi payload khác với xử lý metadata/header và chuyển đổi định dạng ở biên truyền thông. |
| **Pipes and Filters** | Ghép `f | g` để đầu ra của `f` trở thành đầu vào của `g`. | Composition là chuỗi gọi hàm; các “pipe” ở đây chưa mặc nhiên là message channel độc lập hay bất đồng bộ. |
| **Message Filter** | Một `Predicate<T>` hoặc logic kiểm tra trong hàm mô tả điều kiện giữ/bỏ. | Cần endpoint filter thực sự để quyết định loại bỏ, chuyển sang discard channel hoặc báo lỗi. Ném exception khi dữ liệu không hợp lệ không đồng nghĩa với EIP Filter. |
| **Content-Based Router** | `Function<T, RouteDecision>` tính khóa định tuyến dựa trên nội dung. | Router đọc khóa và chọn kênh đích; hàm tự tính khóa không tự phát thông điệp sang các kênh. |
| **Splitter** | Hàm có thể biến một đối tượng thành `List<R>` hay `Flux<R>`. | Splitter EIP biến thành các message riêng, thường phải quản lý sequence/correlation header và downstream flow. |
| **Aggregator** | Hàm có thể tổng hợp một danh sách đã có sẵn. | Aggregator EIP phải giữ trạng thái, xác định nhóm tương quan, điều kiện hoàn tất và timeout cho các message đến không cùng lúc. |
| **Publish-Subscribe Channel / Recipient List** | Nhiều `Consumer<T>` có thể cùng dùng một kiểu dữ liệu. | Channel/broker cần đảm nhiệm fan-out và chính sách giao nhận; chỉ đăng ký nhiều consumer không tạo publish-subscribe. |
| **Wire Tap** | Có thể thêm logic ghi vết tại biên. | Dùng wire tap/audit flow để quan sát thông điệp mà không làm lẫn tác động phụ vào hàm tính toán. |
| **Error Channel / Dead Letter Channel** | Hàm có thể ném exception hoặc trả về một kết quả lỗi theo hợp đồng nghiệp vụ. | Retry, backoff, DLQ, bù trừ và xử lý lỗi theo channel/binder thuộc về tầng tích hợp. |

Ánh xạ này là **tương quan về trách nhiệm**, không phải quan hệ một-một giữa một kiểu Java và một mẫu EIP. Ví dụ, `Function<Order, Boolean>` chỉ trả về giá trị true/false; muốn thực hiện *Message Filter* cần một thành phần dùng kết quả đó để giữ hoặc loại thông điệp.

## 4. Composition và FunctionCatalog: phần nào giống Pipes and Filters?

Giả sử ta có:

~~~java
Function<A, B> first = ...;
Function<B, C> second = ...;
Function<A, C> pipeline = first.andThen(second);
~~~

Composition của SCF đưa ý tưởng tương tự lên tên các bean, ví dụ `validateOrder|classifyOrder`. `FunctionCatalog` hỗ trợ tra cứu hàm đã đăng ký và chuỗi hàm theo tên.

Về mặt khái niệm, các thứ tự thường gặp là:

- `Supplier<A> → Function<A,B>`: nguồn tạo dữ liệu, sau đó biến đổi.
- `Function<A,B> → Function<B,C>`: chuỗi biến đổi.
- `Function<A,B> → Consumer<B>`: biến đổi rồi thực hiện hành động ở cuối.

Kiểu đầu ra của bước trước phải tương thích kiểu đầu vào bước sau. Với chuỗi đồng bộ thông thường, một lời gọi đi qua các hàm trong cùng lượt xử lý; giữa chúng **không tự xuất hiện broker, hàng đợi bền vững, cơ chế retry hoặc transaction**. Các tổ hợp imperative/reactive còn phải tuân theo cách SCF xử lý những kiểu hàm đó.

**Phân biệt:**

- Composition giải quyết **thứ tự thực thi các phép biến đổi**.
- EIP *Pipes and Filters* có thể kết hợp các bộ xử lý thành flow, nhưng **Message Channel** giữa các bước còn có thể đảm nhiệm truyền thông, chuyển luồng, bất đồng bộ hoặc ranh giới lỗi.
- `FunctionCatalog` quản lý và tra cứu định nghĩa hàm, không đóng vai trò router hoặc message store.

## 5. Ví dụ: dùng lại hàm nghiệp vụ trong một luồng EIP

### 5.1. Bài toán

Một cửa hàng nhận đơn hàng với hai trường `id` và `total` (đơn vị VND):

~~~json
{"id":"DH-101","total":1250000}
~~~

Yêu cầu:

1. Kiểm tra đơn có mã hợp lệ và tổng tiền lớn hơn 0.
2. Phân loại `PRIORITY` nếu `total >= 1000000`, ngược lại là `STANDARD`.
3. Gửi quyết định tới kênh xử lý tương ứng.

Ta đặt bước 1–2 vào các hàm độc lập, bước 3 vào EIP Content-Based Router.

### 5.2. Định nghĩa các hàm không phụ thuộc kênh truyền

Ví dụ dùng Java 17+, Spring Boot 3+ và Spring Cloud Function. Các record cùng package với lớp cấu hình.

~~~java
package example.orders;

import java.math.BigDecimal;
import java.util.function.Function;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

record Order(String id, BigDecimal total) {}
record CheckedOrder(String id, BigDecimal total) {}
record ShippingDecision(String id, String tier) {}

@Configuration
class OrderFunctions {

    @Bean
    Function<Order, CheckedOrder> validateOrder() {
        return order -> {
            if (order == null
                    || order.id() == null
                    || order.id().isBlank()
                    || order.total() == null
                    || order.total().signum() <= 0) {
                throw new IllegalArgumentException("Đơn hàng không hợp lệ");
            }
            return new CheckedOrder(order.id(), order.total());
        };
    }

    @Bean
    Function<CheckedOrder, ShippingDecision> classifyOrder() {
        return order -> {
            String tier = order.total()
                    .compareTo(new BigDecimal("1000000")) >= 0
                    ? "PRIORITY" : "STANDARD";
            return new ShippingDecision(order.id(), tier);
        };
    }
}
~~~

Đây là những **phép biến đổi nghiệp vụ**: không biết đơn đến từ HTTP hay queue; cũng không biết kênh đích nằm ở đâu. `validateOrder` đang áp dụng quy tắc *validation* bằng exception, chưa phải một EIP Message Filter.

Khi có `FunctionCatalog` trong Spring context, có thể lấy cùng một pipeline:

~~~java
Function<Order, ShippingDecision> pipeline =
        catalog.lookup("validateOrder|classifyOrder");

ShippingDecision result =
        pipeline.apply(new Order("DH-101", new BigDecimal("1250000")));
// result: ShippingDecision[id=DH-101, tier=PRIORITY]
~~~

Nếu muốn một HTTP adapter hoặc binder của SCF chọn pipeline làm function definition, có thể cấu hình:

~~~properties
spring.cloud.function.definition=validateOrder|classifyOrder
~~~

Thuộc tính đó chọn định nghĩa hàm mà adapter hỗ trợ sẽ sử dụng; **nó không tự xây dựng các kênh `orders.priority` hay `orders.standard`**.

### 5.3. Dùng Spring Integration để định tuyến theo kết quả hàm

Đây là một cấu hình flow minh họa với Spring Integration Java DSL. Nó dùng lại chính pipeline trong `FunctionCatalog`; các channel và hai handler được định nghĩa riêng trong tầng tích hợp.

~~~java
package example.orders;

import java.util.function.Function;

import org.springframework.cloud.function.context.FunctionCatalog;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;

@Configuration
class OrderFlow {

    @Bean("orders.input")
    MessageChannel orderInput() {
        return new DirectChannel();
    }

    @Bean("orders.priority")
    MessageChannel priorityChannel() {
        return new DirectChannel();
    }

    @Bean("orders.standard")
    MessageChannel standardChannel() {
        return new DirectChannel();
    }

    @Bean
    IntegrationFlow orderRouting(FunctionCatalog catalog) {
        Function<Order, ShippingDecision> pipeline =
                catalog.lookup("validateOrder|classifyOrder");

        return IntegrationFlow.from("orders.input")
                .transform((Order order) -> pipeline.apply(order))
                .route("payload.tier()", r -> r
                        .channelMapping("PRIORITY", "orders.priority")
                        .channelMapping("STANDARD", "orders.standard"))
                .get();
    }

    @Bean
    IntegrationFlow priorityHandler() {
        return IntegrationFlow.from("orders.priority")
                .handle(message ->
                        System.out.println("Ưu tiên: " + message.getPayload()))
                .get();
    }

    @Bean
    IntegrationFlow standardHandler() {
        return IntegrationFlow.from("orders.standard")
                .handle(message ->
                        System.out.println("Thông thường: " + message.getPayload()))
                .get();
    }
}
~~~

Trong ví dụ này:

- `orders.input` là **Message Channel** nhận đơn từ một nguồn đã được nối vào flow.
- `transform(...)` gọi **composition** `validateOrder|classifyOrder` như một *Message Translator*.
- `route(...)` là **Content-Based Router**: đọc `tier` trên payload rồi gửi message đến đúng channel.
- Hai `handle(...)` là các **Service Activator** mẫu; trong ứng dụng thật có thể thay việc in ra màn hình bằng gọi dịch vụ nghiệp vụ hoặc outbound adapter.

`DirectChannel` dùng cùng luồng gọi và không lưu bền thông điệp. Một request gửi vào `orders.input` có thể đi xuyên qua bước biến đổi, router và handler trước khi lệnh gửi hoàn tất. Muốn chuyển xử lý bất đồng bộ hoặc qua broker cần thay/bổ sung channel, adapter và cấu hình tương ứng. Tên channel trong ví dụ là tên bean nội bộ, chưa phải tên Kafka topic hay RabbitMQ queue.

Đường đi của đơn `DH-101`:

~~~text
Order("DH-101", 1250000)
  → validateOrder  → CheckedOrder("DH-101", 1250000)
  → classifyOrder  → ShippingDecision("DH-101", "PRIORITY")
  → Content-Based Router
  → orders.priority
  → priorityHandler
~~~

Không nên đưa lệnh gửi tới `orders.priority` trực tiếp vào `classifyOrder`. Làm vậy khiến hàm phân loại phụ thuộc message channel và khó tái sử dụng khi cùng logic được triển khai qua HTTP hoặc serverless.

### 5.4. Một logic, nhiều cách gọi

| Cách triển khai | Thành phần làm nhiệm vụ kết nối | Phần logic dùng lại |
| --- | --- | --- |
| **HTTP** | Adapter của Spring Cloud Function Web nhận request, chuyển payload và trả response theo khả năng adapter. | `validateOrder|classifyOrder` |
| **Event/message broker** | Spring Cloud Stream binder kết nối destination, thực hiện binding và xử lý theo đặc tính broker. | Cùng function definition hoặc hàm tương ứng |
| **Spring Integration flow** | Channel, transformer, router, service activator, inbound/outbound adapter. | Gọi pipeline qua `FunctionCatalog` |
| **Serverless** | Adapter dành cho môi trường serverless chuyển event của nền tảng thành lời gọi hàm. | Cùng hàm nghiệp vụ |

Mỗi cách kết nối có cấu hình, định dạng payload, lifecycle và ngữ nghĩa lỗi riêng. Không thể suy ra rằng một function đã được công bố qua HTTP thì tự động xuất hiện dưới dạng consumer của broker hoặc ngược lại.

## 6. Payload, Message và header: nơi mô hình hàm gặp EIP

EIP coi một message gồm **payload** và **header** (metadata), ví dụ:

~~~text
Message<Order>
  payload: {id: "DH-101", total: 1250000}
  headers: {traceId: "trace-7", contentType: "application/json", ...}
~~~

Hàm kiểu `Function<Order, ShippingDecision>` chỉ diễn đạt dữ liệu nghiệp vụ. Khi cần quyết định dựa trên metadata, giữ trace ID hoặc gán header định tuyến, có thể dùng `Function<Message<T>, Message<R>>`:

~~~java
@Bean
Function<Message<Order>, Message<Order>> markReceived() {
    return incoming -> MessageBuilder.fromMessage(incoming)
            .setHeader("processingStage", "received")
            .build();
}
~~~

Ở ví dụ này, `MessageBuilder.fromMessage(...)` tạo message mới từ message đầu vào và cập nhật header. Cần thêm import `org.springframework.messaging.Message` và `org.springframework.messaging.support.MessageBuilder`.

Một số nguyên tắc quan trọng:

- Dùng **payload thuần** nếu hàm không cần quan tâm transport; dùng **Message** khi metadata là một phần có chủ đích của hợp đồng.
- Header ứng dụng như `traceId` hoặc `correlationId` phải được truyền và kiểm tra đúng nơi cần dùng. Header hệ thống/broker như acknowledgement, delivery attempt hay routing key có quy tắc riêng; không giả định chúng được giữ y nguyên qua mọi adapter.
- Conversion giữa JSON, Java object và `Message<?>` phụ thuộc chữ ký hàm cùng adapter/converter đang dùng. Đặt contract rõ ràng và kiểm thử ở ranh giới HTTP/broker.
- Header có thể giúp router quyết định đường đi; nhưng **đọc header để tính toán** vẫn khác với **thực hiện routing tới channel**.

## 7. Vì sao Splitter và Aggregator không thể thay chỉ bằng Function?

Giả sử một đơn hàng có mười dòng sản phẩm. Có hai tình huống khác nhau:

**Trường hợp A — dữ liệu đã nằm sẵn trong bộ nhớ.** Một `Function<Order, List<OrderLine>>` trả về danh sách mười phần tử. Đây chỉ là phép chuyển đổi giá trị. Nếu sau đó một hàm khác nhận cả `List<OrderLine>` và tính tổng, pipeline đơn giản có thể đủ.

**Trường hợp B — mười dòng phải xử lý độc lập.** EIP *Splitter* phát mười **message**, mỗi message có thể đi qua worker khác nhau. Kết quả đến lệch thứ tự hoặc sau nhiều giây; *Aggregator* cần biết chúng thuộc đơn hàng nào, khi nào đủ mười kết quả và xử lý ra sao nếu một dòng thất bại.

~~~mermaid
flowchart LR
    A["Order gồm 10 dòng"] --> S["Splitter"]
    S --> P["Xử lý dòng 1"]
    S --> Q["Xử lý dòng 2...9"]
    S --> R["Xử lý dòng 10"]
    P --> G["Aggregator<br/>correlation + release condition"]
    Q --> G
    R --> G
    G --> X["OrderSummary"]
~~~

Ở tình huống B, các thông tin như **correlation key**, **sequence size/number**, **message store**, **timeout**, **release strategy** và xử lý kết quả thiếu là trách nhiệm điều phối của EIP. Việc trả về `List<?>`, `Stream<?>` hay `Flux<?>` trong chữ ký hàm **không tự tạo ra** những bảo đảm đó. Với luồng reactive, còn cần chú ý backpressure, subscription và vị trí kết thúc của stream.

## 8. Lỗi, retry, thứ tự và tính nhất quán

Khi đưa một hàm vào flow tích hợp, cần đặt chính sách lỗi ở **đúng tầng**:

| Tình huống | Nơi xử lý phù hợp | Lý do |
| --- | --- | --- |
| Đơn có `total <= 0` | Hàm validation trả kết quả lỗi nghiệp vụ hoặc ném lỗi có phân loại. | Retry cùng dữ liệu thường không làm đơn hợp lệ hơn. |
| API đối tác tạm thời lỗi mạng | Adapter/handler kết hợp retry và backoff. | Có khả năng phục hồi khi gọi lại. |
| Xử lý thất bại nhiều lần | Error flow, DLQ hoặc kho sự kiện lỗi phù hợp với broker. | Cho phép quan sát, phân loại và xử lý lại có kiểm soát. |
| Event trùng lặp sau redelivery | Consumer/handler idempotent, kiểm soát bằng khóa nghiệp vụ. | Delivery *at-least-once* có thể khiến cùng sự kiện đến nhiều lần. |
| Nhiều kết quả trả về lệch thứ tự | Aggregator/correlation hoặc cơ chế sắp xếp riêng. | Thứ tự trong từng hàm không đảm bảo thứ tự trên hệ phân tán. |
| Cần transaction qua nhiều hệ thống | Thiết kế transaction/bù trừ ở tầng xử lý tích hợp. | Composition không tự cung cấp transaction phân tán. |

Một exception ném ra từ `Function` sẽ đi theo cơ chế xử lý lỗi của **caller**. Trong một flow Spring Integration đồng bộ, nó có thể lan về điểm gửi; trong một binder, retry hoặc DLQ có thể phụ thuộc cấu hình destination, loại lỗi và chế độ tiêu thụ. Vì vậy không nên viết trong tài liệu hoặc code giả định rằng “SCF tự retry ba lần” cho mọi môi trường.

Để giữ các hàm dễ tái sử dụng, nên giới hạn tác động phụ trong phần tính toán thuần. Gửi email, ghi cơ sở dữ liệu, publish sự kiện hay gọi API ngoài thường thuộc `Consumer`/handler hoặc lớp dịch vụ được gọi ở điểm cuối flow, kèm chính sách idempotency và lỗi phù hợp.

## 9. Cách kiểm thử đúng ranh giới

Có thể chia kiểm thử thành ba mức:

1. **Unit test hàm nghiệp vụ:** gọi trực tiếp `validateOrder().apply(...)` và `classifyOrder().apply(...)` để xác nhận đơn hợp lệ, đơn lỗi, ngưỡng đúng bằng một triệu và đầu ra `tier`. Không cần broker hoặc Spring Integration.
2. **Test composition/catalog:** khởi tạo Spring context, tra cứu `catalog.lookup("validateOrder|classifyOrder")` và kiểm tra đầu vào/đầu ra, kiểu dữ liệu và chuyển đổi message cần thiết.
3. **Integration test flow/adapter:** gửi `Message<Order>` vào `orders.input`, xác nhận chỉ nhánh phù hợp nhận message, header quan trọng còn đúng, trường hợp lỗi đi vào đường xử lý đã thiết kế. Nếu dùng broker thật, kiểm thêm acknowledgement, retry, redelivery, ordering và DLQ theo hạ tầng thực tế.

Ví dụ unit test không cần context Spring:

~~~java
OrderFunctions functions = new OrderFunctions();

CheckedOrder checked = functions.validateOrder().apply(
        new Order("DH-101", new BigDecimal("1250000")));

ShippingDecision decision =
        functions.classifyOrder().apply(checked);

assertEquals("PRIORITY", decision.tier()); // JUnit 5
~~~

Nên có thêm ca `total = 1000000` (vẫn `PRIORITY`), `total = 999999` (`STANDARD`) và `total <= 0` (bị từ chối). Các ca này xác minh quy tắc nghiệp vụ độc lập với việc điều phối.

## 10. Nguyên tắc thiết kế và những nhầm lẫn thường gặp

- **Đặt quyết định nghiệp vụ trong hàm, đặt việc vận chuyển trong flow.** Hàm trả về `ShippingDecision`; router quyết định gửi tới channel nào.
- **Dùng composition cho chuỗi biến đổi tuyến tính.** Khi có nhiều nhánh, cần lưu trạng thái nhóm hoặc fan-out, hãy xem xét EIP phù hợp.
- **Tách validation và filtering.** Validate có thể bác bỏ một đơn vì lỗi; filter là một hành vi điều phối giữ/bỏ message theo điều kiện.
- **Phân biệt collection với nhiều message.** Một `List<T>` trong bộ nhớ chưa phải một nhóm message có correlation và timeout.
- **Đừng đồng nhất FunctionCatalog với message broker.** Catalog dùng để đăng ký/tra cứu/composition; broker và adapter chịu trách nhiệm chuyển phát.
- **Thiết kế idempotency, retry và quan sát ở ranh giới có tác động phụ.** Có thể thuần hóa phần tính toán, nhưng không nên bỏ qua ngữ nghĩa giao nhận thực tế.

**Kết luận:** Spring Cloud Function giúp đóng gói và tái sử dụng logic bằng `Supplier`, `Function`, `Consumer` cùng `FunctionCatalog`; Spring Integration cung cấp các mẫu EIP để điều phối message qua channel, router, splitter, aggregator và các endpoint. Khi phối hợp đúng, một hàm nghiệp vụ có thể được gọi qua HTTP, sự kiện hoặc serverless, trong khi mỗi môi trường vẫn giữ cơ chế vận chuyển, định tuyến và xử lý lỗi thích hợp của mình.
