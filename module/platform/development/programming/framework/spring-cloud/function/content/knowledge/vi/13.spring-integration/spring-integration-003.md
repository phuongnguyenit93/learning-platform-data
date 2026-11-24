# Gọi FunctionCatalog từ IntegrationFlow

## 1. Bài toán và mục tiêu

**Spring Cloud Function (SCF)** biểu diễn logic nghiệp vụ bằng `Supplier<T>`, `Function<T, R>` và `Consumer<T>`. Các hàm được đăng ký và tra cứu thông qua `FunctionCatalog`; bạn có thể **composition** nhiều hàm thành một pipeline, đồng thời giữ logic không phụ thuộc cách gọi qua HTTP, sự kiện hoặc nền tảng serverless.

**Spring Integration** tổ chức đường đi của message bằng `IntegrationFlow`: nhận message từ channel/adapter, biến đổi payload, lọc, định tuyến, chia/gộp, gọi dịch vụ và xử lý lỗi theo các **Enterprise Integration Patterns (EIP)**.

Trong một ứng dụng dùng cả hai framework, câu hỏi là: **Làm thế nào để một `IntegrationFlow` gọi lại hàm đã đăng ký trong `FunctionCatalog`, thay vì sao chép logic hoặc phụ thuộc chặt vào bean triển khai?**

Có hai hướng chính:

1. **Tra cứu tường minh:** inject `FunctionCatalog`, gọi `catalog.lookup("functionName")` hoặc `catalog.lookup("f1|f2")`, sau đó đưa hàm trả về vào các endpoint của `IntegrationFlow`.
2. **DSL chuyên biệt:** thêm module `spring-cloud-function-integration` và dùng `FunctionFlowBuilder` với `apply("functionDefinition")`, `accept("consumerDefinition")` hoặc `fromSupplier("supplierDefinition")`.

Bài này tập trung vào luồng **từ FunctionCatalog sang IntegrationFlow**, cơ chế thực thi và cách kiểm thử; ví dụ xuyên suốt minh họa cách 1 rồi đối chiếu với cách 2.

Sau bài học, bạn cần giải thích được ý nghĩa của `lookup`, vị trí dùng `transform`, `handle`, `route`, cách dùng composition, tác động của payload/header, trường hợp lookup thất bại và ngữ nghĩa lỗi khi luồng chạy.

## 2. Vai trò của từng thành phần trong đường đi thông điệp

~~~mermaid
flowchart LR
    A["HTTP / broker / internal sender"] --> B["Inbound adapter / MessageChannel"]
    B --> C["IntegrationFlow"]
    D["Các bean Supplier / Function / Consumer"] --> E["FunctionCatalog"]
    E -. lookup hoặc composition .-> F["Function đã được bọc"]
    F --> C
    C --> G["Transformer / Filter / Router"]
    G --> H["Handler hoặc outbound adapter"]
~~~

| Thành phần | Làm gì? | Không tự làm gì? |
| --- | --- | --- |
| `FunctionCatalog` | Tra cứu và ghép hàm dựa trên tên; trả về function được SCF bọc để hỗ trợ các tính năng như conversion/composition. | Không chuyển message đến broker hoặc tạo message channel. |
| `IntegrationFlow` | Xây dựng một chuỗi endpoint xử lý message theo Spring Integration DSL. | Không tự biết function nào cần gọi nếu chưa cấu hình. |
| `transform(...)` | Dùng một transformer để tạo payload/message đầu ra mới. | Không tự quyết định channel nhận message ở nhiều nhánh. |
| `filter(...)` | Giữ hoặc loại message theo điều kiện. | Không đồng nghĩa validation nghiệp vụ chỉ vì cùng dùng một predicate. |
| `route(...)` | Chọn channel đích dựa trên payload, header hoặc khóa định tuyến. | Không tự tạo quy tắc tính toán nghiệp vụ bên trong catalog. |
| `handle(...)` | Kích hoạt xử lý cuối luồng hoặc request/reply handler. | Không tự cung cấp retry, transaction hay idempotency. |
| Adapter/binder | Kết nối HTTP, broker, file, scheduler, serverless... với luồng. | Không làm cho mọi function mặc nhiên có đầy đủ mọi giao thức. |

**Điểm mấu chốt:** `FunctionCatalog` trả về **khả năng xử lý dữ liệu**, còn Spring Integration quyết định **thông điệp đi qua đâu và khi nào**. Cùng một hàm có thể được gọi trực tiếp trong chương trình, sau HTTP adapter hoặc trong một `IntegrationFlow`.

## 3. Điều kiện tối thiểu để gọi FunctionCatalog

### 3.1. Dependency

Một ứng dụng Spring Boot thường cần các thành phần cùng phiên bản tương thích:

- Spring Cloud Function context để có `FunctionCatalog`, ví dụ dependency `org.springframework.cloud:spring-cloud-function-context`.
- Spring Integration DSL, thường nhận được qua `org.springframework.boot:spring-boot-starter-integration`.
- Spring Boot/Spring Cloud dependency management hoặc BOM phù hợp để tránh trộn phiên bản không tương thích.

Ví dụ Maven (phần `dependencies` của `pom.xml`):

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-function-context</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-integration</artifactId>
    </dependency>
</dependencies>
~~~

Đoạn trên giả định `dependencyManagement` của dự án đã chọn đúng phiên bản Spring Boot và Spring Cloud. Nếu dự án đã có một starter/adapter kéo các dependency này vào, tránh khai báo trùng một cách không cần thiết.

**Cách tra cứu tường minh bằng `catalog.lookup(...)` không đòi hỏi phải thêm `spring-cloud-function-integration`.** Module này dành cho cú pháp `FunctionFlowBuilder` được trình bày ở phần sau.

### 3.2. Các function được đăng ký như thế nào?

Khai báo một bean có kiểu `Supplier`, `Function` hoặc `Consumer` trong Spring context:

~~~java
@Bean
Function<String, String> normalizeCode() {
    return code -> code.strip().toUpperCase(Locale.ROOT);
}
~~~

SCF cho phép truy xuất bằng tên bean thông qua `FunctionCatalog`:

~~~java
Function<String, String> normalizer =
        catalog.lookup("normalizeCode");

String result = normalizer.apply("  order-007  ");
// ORDER-007
~~~

Trong ví dụ có thêm import `java.util.Locale` và `java.util.function.Function`. Cần bảo đảm ứng dụng thực sự bật auto-configuration cho SCF và bean nằm trong Spring context được quét.

**Khác biệt với lấy bean trực tiếp:**

~~~java
Function<String, String> rawBean =
        applicationContext.getBean("normalizeCode", Function.class);

Function<String, String> catalogFunction =
        catalog.lookup("normalizeCode");
~~~

`rawBean` là chính bean mà ứng dụng đăng ký; `catalogFunction` là hàm được catalog trả về và có thể được SCF **bọc** để hỗ trợ conversion, composition và các tính năng khi chạy qua adapter. Hai đối tượng có thể có hành vi sử dụng khác nhau ở ranh giới message. Khi tích hợp với SCF, nên tra cứu qua catalog theo đúng hợp đồng hàm mà bạn muốn sử dụng.

## 4. Mô hình gọi function trong Spring Integration DSL

Với `Function<T,R>`, cách ánh xạ tự nhiên nhất là dùng một **transformer**:

~~~java
@Bean
IntegrationFlow processingFlow(FunctionCatalog catalog) {
    Function<String, String> normalize =
            Objects.requireNonNull(
                    catalog.lookup("normalizeCode"),
                    "Không tìm thấy function normalizeCode");

    return IntegrationFlow.from("input")
            .transform(String.class, normalize::apply)
            .channel("output")
            .get();
}
~~~

Các import chính: `java.util.Objects`, `java.util.function.Function`, `org.springframework.cloud.function.context.FunctionCatalog`, `org.springframework.integration.dsl.IntegrationFlow`, `org.springframework.context.annotation.Bean`.

Trong flow này:

1. `from("input")` nhận message từ channel `input`, được cấu hình ở nơi khác.
2. `transform(String.class, normalize::apply)` lấy **payload kiểu String** rồi gọi hàm trong catalog. Kết quả trở thành payload ở bước sau.
3. `channel("output")` gửi message mới đến channel `output`, được cấu hình hoặc phân giải bởi Spring Integration.

Chữ ký của `transform(...)` ở đây là transformer trên **payload**. Bạn không cần tự bóc `message.getPayload()` trong hàm nghiệp vụ. `String.class` giúp DSL và bước invocation xác định kiểu payload cần xử lý; không có nghĩa mọi kiểu input khác đều tự chuyển được thành String.

### 4.1. Vì sao chọn transformer thay vì handle?

`transform(...)` phù hợp cho `Function<T,R>` có kết quả gửi tiếp trong flow. `handle(...)` thường dùng cho **Service Activator** hoặc handler có tác động phụ; với `Consumer<T>` có thể gọi `accept(...)` tại bước cuối:

~~~java
@Bean
IntegrationFlow consumerFlow(FunctionCatalog catalog) {
    Consumer<String> audit =
            Objects.requireNonNull(
                    catalog.lookup("auditCode"),
                    "Không tìm thấy consumer auditCode");

    return IntegrationFlow.from("audit.input")
            .handle(String.class, (payload, headers) -> {
                audit.accept(payload);
                return null;  // Không gửi reply
            })
            .get();
}
~~~

Ví dụ giả định đã có function `auditCode` kiểu `Consumer<String>` và channel `audit.input`. Trả về `null` từ handler ở điểm cuối nghĩa là handler không phát reply; nếu muốn tiếp tục chuỗi, dùng một endpoint có output được xác định rõ ràng.

### 4.2. Khi nào nên tra cứu catalog?

Với function name cố định trong cấu hình, nên tra cứu **một lần khi tạo bean `IntegrationFlow`**, rồi tái sử dụng reference cho các message sau:

~~~java
Function<String, String> f = catalog.lookup("normalizeCode");

return IntegrationFlow.from("input")
        .transform(String.class, f::apply)
        .get();
~~~

Điều này giúp phát hiện cấu hình sai sớm và tránh lặp lại `lookup(...)` trên mọi message. Dùng `Objects.requireNonNull(...)` hoặc một kiểm tra tương đương nếu tên function là bắt buộc.

Nếu nghiệp vụ cần chọn **hàm khác nhau ở runtime** theo từng message, đó là một yêu cầu khác: cần quy tắc chọn tên, danh sách hàm được phép gọi, xử lý lỗi và quản lý type. Trong nhiều trường hợp, hãy dùng EIP **Content-Based Router** tới các flow được cấu hình sẵn thay vì lookup từ chuỗi tùy ý của người gửi.

## 5. Ví dụ đầy đủ: phân loại đơn hàng bằng hàm trong catalog

### 5.1. Yêu cầu

Một hệ thống nhận đơn hàng:

~~~json
{"id":" DH-042 ","totalVnd":1750000}
~~~

Quy tắc:

1. Chuẩn hóa mã đơn bằng cách bỏ khoảng trắng đầu/cuối và chuyển thành chữ hoa.
2. Từ chối mã rỗng hoặc `totalVnd <= 0`.
3. Phân loại đơn từ `1_000_000` VND trở lên thành `PRIORITY`, còn lại `STANDARD`.
4. Spring Integration nhận message, gọi composition của hai function và đưa kết quả tới một trong hai channel.

Ở đây validation/chuẩn hóa/phân loại là **nghiệp vụ**; router và channel là **EIP**.

~~~mermaid
flowchart LR
    A["orders.input"] --> B["transform: catalog.lookup(normalizeOrder|classifyOrder)"]
    B --> C{"route theo tier"}
    C -->|PRIORITY| D["orders.priority"]
    C -->|STANDARD| E["orders.standard"]
    D --> F["priorityHandler"]
    E --> G["standardHandler"]
~~~

### 5.2. Bước 1 — Khai báo hợp đồng dữ liệu và function

Ví dụ Java 17+:

~~~java
package example.orders;

import java.util.Locale;
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

record OrderRequest(String id, long totalVnd) {}
record RoutingDecision(String id, long totalVnd, String tier) {}

@Configuration
class OrderFunctions {

    @Bean
    Function<OrderRequest, OrderRequest> normalizeOrder() {
        return order -> {
            if (order == null || order.id() == null
                    || order.id().isBlank() || order.totalVnd() <= 0) {
                throw new IllegalArgumentException("Đơn hàng không hợp lệ");
            }

            String id = order.id().strip().toUpperCase(Locale.ROOT);
            return new OrderRequest(id, order.totalVnd());
        };
    }

    @Bean
    Function<OrderRequest, RoutingDecision> classifyOrder() {
        return order -> new RoutingDecision(
                order.id(),
                order.totalVnd(),
                order.totalVnd() >= 1_000_000
                        ? "PRIORITY" : "STANDARD");
    }
}
~~~

Hai function không biết HTTP, message broker, tên channel hay flow nào sẽ gọi chúng. Bởi vậy chúng có thể dùng lại trong REST endpoint hoặc adapter serverless cùng với cùng tên function definition.

`normalizeOrder` có validation và ném `IllegalArgumentException` với dữ liệu không hợp lệ; ném exception ở đây là **quy tắc từ chối nghiệp vụ**, chưa phải EIP Message Filter.

### 5.3. Bước 2 — Tạo IntegrationFlow và tra cứu composition

~~~java
package example.orders;

import java.util.Objects;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.function.Function;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.cloud.function.context.FunctionCatalog;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;

@Configuration
class OrderIntegration {

    @Bean("orders.input")
    MessageChannel inputChannel() {
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

    @Bean("priorityResults")
    BlockingQueue<RoutingDecision> priorityResults() {
        return new LinkedBlockingQueue<>();
    }

    @Bean("standardResults")
    BlockingQueue<RoutingDecision> standardResults() {
        return new LinkedBlockingQueue<>();
    }

    @Bean
    IntegrationFlow classifyFlow(FunctionCatalog catalog) {
        Function<OrderRequest, RoutingDecision> classify =
                Objects.requireNonNull(
                        catalog.lookup("normalizeOrder|classifyOrder"),
                        "Không tìm thấy composition của đơn hàng");

        return IntegrationFlow.from("orders.input")
                .transform(OrderRequest.class, classify::apply)
                .route(RoutingDecision.class,
                        RoutingDecision::tier,
                        route -> route
                                .channelMapping("PRIORITY", "orders.priority")
                                .channelMapping("STANDARD", "orders.standard"))
                .get();
    }

    @Bean
    IntegrationFlow priorityFlow(
            @Qualifier("priorityResults")
            BlockingQueue<RoutingDecision> results) {
        return IntegrationFlow.from("orders.priority")
                .handle(RoutingDecision.class, (payload, headers) -> {
                    results.add(payload);
                    return null;
                })
                .get();
    }

    @Bean
    IntegrationFlow standardFlow(
            @Qualifier("standardResults")
            BlockingQueue<RoutingDecision> results) {
        return IntegrationFlow.from("orders.standard")
                .handle(RoutingDecision.class, (payload, headers) -> {
                    results.add(payload);
                    return null;
                })
                .get();
    }
}
~~~

Các điểm đáng chú ý:

- `lookup("normalizeOrder|classifyOrder")` yêu cầu catalog ghép đầu ra `OrderRequest` của hàm đầu với đầu vào `OrderRequest` của hàm sau. Kết quả chung có kiểu nghiệp vụ `Function<OrderRequest, RoutingDecision>`.
- `transform(OrderRequest.class, classify::apply)` gọi composition trên **payload**; message header thông thường được Spring Integration mang qua endpoint theo cơ chế truyền message của flow, nhưng hãy kiểm thử header quan trọng.
- `route(RoutingDecision.class, RoutingDecision::tier, ...)` đọc khóa định tuyến từ payload rồi chuyển message đến channel phù hợp. Function chỉ **trả về quyết định**, không tự gửi sang channel.
- `priorityFlow` và `standardFlow` đóng vai trò handler cuối, mỗi handler ghi vào một queue trong bộ nhớ để minh họa. Khi triển khai thật, có thể đổi thành outbound adapter, ghi DB hoặc gọi dịch vụ.
- `DirectChannel` là channel đồng bộ và không lưu bền thông điệp. Ví dụ này không có bảo đảm giao nhận từ broker hay khôi phục sau sự cố.

**Về configuration:** những bean trong ví dụ cần được Spring Boot quét cùng package hoặc được `@Import` vào application configuration. Bản demo sử dụng ba channel có tên cụ thể; nếu dùng một inbound adapter ngoài, adapter phải được nối vào `orders.input`.

### 5.4. Bước 3 — Gửi một message

Trong mã ứng dụng/test có Spring context:

~~~java
MessageChannel input =
        context.getBean("orders.input", MessageChannel.class);

boolean sent = input.send(
        new GenericMessage<>(new OrderRequest(" dh-042 ", 1_750_000)));

System.out.println(sent); // true nếu message được chấp nhận
~~~

Cần import `org.springframework.messaging.MessageChannel` và `org.springframework.messaging.support.GenericMessage`; `context` là một `ApplicationContext` đã được inject hoặc lấy từ ứng dụng.

Kết quả mong đợi: `priorityResults` nhận

~~~text
RoutingDecision[id=DH-042, totalVnd=1750000, tier=PRIORITY]
~~~

và `standardResults` không nhận đơn này.

### 5.5. Vì sao không gọi trực tiếp function bean?

Đoạn này vẫn xử lý nghiệp vụ bình thường:

~~~java
Function<OrderRequest, OrderRequest> normalize =
        applicationContext.getBean("normalizeOrder", Function.class);
~~~

Nhưng nếu flow chủ đích dùng **composition**, chuyển đổi được SCF hỗ trợ và abstraction theo function definition, lấy qua `FunctionCatalog` nhất quán hơn với các adapter của hệ SCF. Tuy nhiên, việc tra cứu qua catalog không thay thế yêu cầu về contract dữ liệu đầu vào/đầu ra và xử lý ngoại lệ.

## 6. Gọi Supplier và Consumer từ IntegrationFlow

`FunctionCatalog` không chỉ có `Function<T,R>`.

### 6.1. Consumer làm điểm kết thúc

Khi catalog có:

~~~java
@Bean
Consumer<RoutingDecision> dispatchOrder() {
    return decision -> System.out.println("Dispatched: " + decision.id());
}
~~~

ta có thể tạo endpoint:

~~~java
@Bean
IntegrationFlow dispatchFlow(FunctionCatalog catalog) {
    Consumer<RoutingDecision> dispatch =
            Objects.requireNonNull(
                    catalog.lookup("dispatchOrder"),
                    "Không tìm thấy dispatchOrder");

    return IntegrationFlow.from("orders.dispatchInput")
            .handle(RoutingDecision.class, (payload, headers) -> {
                dispatch.accept(payload);
                return null;
            })
            .get();
}
~~~

Ví dụ giả định channel `orders.dispatchInput` đã được khai báo riêng. Với `Consumer<T>`, hành động xử lý thường có side effect và không trả về dữ liệu cho bước tiếp theo; nên đặt ở cuối flow hoặc định nghĩa reply rõ nếu cần.

### 6.2. Supplier làm nguồn phát

Khi catalog có:

~~~java
@Bean
Supplier<String> nextCode() {
    return () -> "DH-DEMO";
}
~~~

Spring Integration có thể sử dụng supplier như một nguồn cho polling endpoint:

~~~java
@Bean
IntegrationFlow pollCodes(FunctionCatalog catalog) {
    Supplier<String> supplier =
            Objects.requireNonNull(
                    catalog.lookup("nextCode"),
                    "Không tìm thấy nextCode");

    return IntegrationFlow
            .from(supplier, spec -> spec
                    .poller(Pollers.fixedDelay(1000)))
            .channel("codes.output")
            .get();
}
~~~

Thêm import `java.util.function.Supplier`, `org.springframework.integration.dsl.Pollers` và các import Spring tương ứng; channel `codes.output` được cấu hình ở nơi khác. Đây là **minh họa nguồn polling**, không phải flow liên kết với `orders.input` ở ví dụ trước.

Một số điểm cần hiểu:

- `Supplier<T>` được gọi theo nhịp poller, không phải theo request gửi vào một message channel.
- `Pollers.fixedDelay(1000)` thiết lập delay ở mức 1.000 mili giây theo DSL.
- Trong nhiều polling adapter, một giá trị `null` nghĩa là nguồn không có message ở lượt đó; cần xác nhận ngữ nghĩa của supplier và adapter cụ thể.
- Nếu supplier đọc rồi xóa dữ liệu ở hệ thống bên ngoài, cần thiết kế acknowledgement/recovery vì lỗi ở downstream có thể làm mất dữ liệu đã lấy.
- Không dùng supplier trả cùng một giá trị mãi mãi nếu ứng dụng thực tế cần biết khi nào dừng, trừ khi đã giới hạn nhịp và vòng đời.

## 7. So sánh ba cách đưa Function vào IntegrationFlow

| Cách | Cú pháp minh họa | Phù hợp khi | Đánh đổi |
| --- | --- | --- | --- |
| Lấy bean trực tiếp | `flow.transform(normalizeOrderBean)` | Chỉ cần Java function thuần, không dùng đặc tính SCF. | Không dùng wrapper và lookup/composition của catalog. |
| Lookup thủ công | `catalog.lookup("normalizeOrder|classifyOrder")` rồi `flow.transform(...)` | Muốn kiểm soát rõ transformer, handler, type và EIP trong flow. | Cần code lookup, kiểm tra null và nối hàm vào endpoint. |
| FunctionFlowBuilder | `builder.from("input").apply("normalizeOrder|classifyOrder")` | Dự án đã dùng `spring-cloud-function-integration` và muốn diễn đạt flow theo tên function. | Thêm module/DSL chuyên biệt và ràng buộc vào API của module. |

### 7.1. Cùng ý tưởng bằng FunctionFlowBuilder

Khi có dependency `org.springframework.cloud:spring-cloud-function-integration` (theo release train tương thích), module tự cấu hình `FunctionFlowBuilder` với `FunctionCatalog`:

~~~java
@Bean
IntegrationFlow classifyWithBuilder(FunctionFlowBuilder builder) {
    return builder
            .from("orders.builderInput")
            .apply("normalizeOrder|classifyOrder")
            .route(RoutingDecision.class,
                    RoutingDecision::tier,
                    r -> r
                            .channelMapping("PRIORITY", "orders.priority")
                            .channelMapping("STANDARD", "orders.standard"))
            .get();
}
~~~

Cần import `org.springframework.cloud.function.integration.FunctionFlowBuilder`. Channel `orders.builderInput` là nguồn khác cần khai báo. Đoạn này minh họa **một lựa chọn thay thế** cho `classifyFlow`, không có ý định đăng ký hai flow cùng nghe `orders.input` trong ví dụ chạy thử.

Các toán tử `apply(String functionDefinition)` và `accept(String consumerDefinition)` tra cứu tên hàm từ catalog. `fromSupplier("supplierName")` dùng supplier trong catalog để tạo nguồn. Vẫn có thể kết hợp EIP `filter`, `route`, `wireTap`, `channel`... do Spring Integration cung cấp.

**Lưu ý phiên bản:** module integration được giới thiệu từ Spring Cloud Function 4.0.3; hãy kiểm tra đúng tài liệu của release đang sử dụng. Không giả định dự án Spring Cloud Function đời cũ đã có `FunctionFlowBuilder`.

### 7.2. Khi nào dùng `spring.cloud.function.definition`?

Thuộc tính:

~~~properties
spring.cloud.function.definition=normalizeOrder|classifyOrder
~~~

thường được **adapter hoặc binder** dùng để chọn function/composition mà chúng gọi. Trong `IntegrationFlow` được viết tường minh như trên, lệnh `catalog.lookup("normalizeOrder|classifyOrder")` đã xác định rõ function; nó không cần property đó để quyết định tên function.

Đặt property không tự tạo channel `orders.input`, không tự kết nối Kafka topic vào đó và cũng không thay thế định nghĩa `IntegrationFlow`. Khi một ứng dụng dùng cả Spring Cloud Stream bindings và các flow Spring Integration, phải xác định rõ **điểm nhận message** để tránh xử lý trùng.

## 8. Payload, Message header và chuyển đổi kiểu

### 8.1. Tham số mà function nhận là gì?

Message của Spring Integration gồm:

~~~text
Message<OrderRequest>
  payload = OrderRequest("DH-042", 1750000)
  headers = {traceId: "trace-123", ...}
~~~

Với đoạn:

~~~java
.transform(OrderRequest.class, classify::apply)
~~~

`classify::apply` nhận **`OrderRequest`**, tức payload, không nhận toàn bộ `Message<OrderRequest>`. Điều này giữ hàm nghiệp vụ đơn giản và tách khỏi chi tiết vận chuyển.

Nếu quy tắc thật sự cần header, có thể định nghĩa function có kiểu `Message<T>`:

~~~java
@Bean
Function<Message<OrderRequest>, Message<OrderRequest>> addProcessingStage() {
    return incoming -> MessageBuilder.fromMessage(incoming)
            .setHeader("processingStage", "VALIDATED")
            .build();
}
~~~

Cần import `org.springframework.messaging.Message` và `org.springframework.messaging.support.MessageBuilder`. Khi kết nối một function nhận `Message` vào endpoint, hãy chọn overload/hợp đồng xử lý **whole message** thích hợp, kiểm thử thực tế payload và header sau khi qua catalog wrapper. Không ép kiểu tùy tiện `Message<?>` thành `Message<OrderRequest>` nếu chưa biết input thực tế.

Một số lưu ý:

- `FunctionCatalog` hỗ trợ chuyển đổi dữ liệu dựa trên chữ ký hàm, content type và các converter có sẵn. Không có bảo đảm rằng một object bất kỳ sẽ tự biến thành `OrderRequest` khi thiếu converter/cấu hình tương ứng.
- Message header thường được Spring Integration giữ khi xây dựng message mới qua transformer, nhưng việc chuyển qua SCF wrapper/adapter có thể ảnh hưởng header theo hợp đồng cụ thể. Với header quan trọng như trace ID, correlation ID hoặc thông tin acknowledgement, nên có integration test.
- Phân biệt header nghiệp vụ với metadata của broker. Header dành cho retry/acknowledgement/partition key có thể được adapter quản lý và không nên thay đổi tùy tiện.

### 8.2. Ví dụ sai kiểu đầu vào

~~~java
Function<OrderRequest, RoutingDecision> classify =
        catalog.lookup("normalizeOrder|classifyOrder");

// Sai nếu gửi String mà không có converter String -> OrderRequest:
input.send(new GenericMessage<>("{\"id\":\"DH-042\",\"totalVnd\":1750000}"));
~~~

Flow của phần 5 mong đợi **payload `OrderRequest`**. Nếu inbound HTTP/broker cung cấp JSON, cần một bước deserialization/converter hoặc cấu hình content type rõ ràng trước khi tới transformer. Cần kiểm thử serialization, trường thiếu, enum/date/number format và validation ở ranh giới.

## 9. Composition và ràng buộc kiểu

Khi catalog tra cứu `"f1|f2"`, về mặt logic:

~~~text
input --f1--> intermediate --f2--> output
~~~

Ví dụ:

~~~java
Function<OrderRequest, RoutingDecision> composed =
        catalog.lookup("normalizeOrder|classifyOrder");
~~~

Để composition hợp lệ, kiểu kết quả `f1` phải phù hợp đầu vào `f2`. Một số loại chuyển đổi hợp lệ có thể được SCF thực hiện qua converter, nhưng không nên dựa vào khả năng chuyển đổi không được công bố/kiểm thử.

Dù composition rất hữu ích, nó chỉ giải quyết **chuỗi hàm được gọi cùng nhau**:

- Không tự tạo các message channel giữa hai hàm.
- Không tự retry từng bước theo broker.
- Không tự tạo Splitter/Aggregator hoặc correlation store.
- Không tự biến một danh sách được trả về thành nhiều message có sequence header.
- Không tự biến một `Function<T,R>` thành HTTP endpoint nếu không có adapter tương ứng.

Nếu cần một EIP đứng giữa hai bước, hãy đặt từng hàm vào từng transformer:

~~~java
Function<OrderRequest, OrderRequest> normalize =
        catalog.lookup("normalizeOrder");
Function<OrderRequest, RoutingDecision> classify =
        catalog.lookup("classifyOrder");

return IntegrationFlow.from("orders.filteredInput")
        .transform(OrderRequest.class, normalize::apply)
        .filter(OrderRequest.class, order -> order.totalVnd() >= 10_000)
        .transform(OrderRequest.class, classify::apply)
        .channel("orders.filteredOutput")
        .get();
~~~

Đoạn này giả định các channel `orders.filteredInput` và `orders.filteredOutput` đã được cấu hình; đây là biến thể flow, không chạy đồng thời trên cùng nguồn với flow phần 5. Chú ý **khác biệt về chính sách**: biến thể trên lọc bỏ đơn dưới 10.000 VND; composition của phần 5 không có bước lọc này.

## 10. Lỗi, retry, transaction và luồng bất đồng bộ

Hãy tách bốn loại vấn đề thường bị gộp làm một:

| Trường hợp | Nơi phát sinh | Hướng xử lý |
| --- | --- | --- |
| Không tìm thấy function definition | Khi `catalog.lookup(...)` chạy hoặc lúc khởi tạo flow. | Fail fast, báo rõ tên function; kiểm tra bean và cấu hình catalog. |
| Payload sai kiểu hoặc thiếu converter | Trước/trong lúc transformer gọi hàm. | Sửa message contract, converter, content type và validation đầu vào. |
| Hàm ném exception do dữ liệu nghiệp vụ không hợp lệ | `normalizeOrder.apply(...)` hoặc hàm khác. | Trả lỗi có phân loại, loại message theo chính sách hoặc chuyển tới luồng xử lý dữ liệu lỗi. Không retry vô hạn. |
| Hệ thống bên ngoài tạm thời không khả dụng | Handler hoặc outbound adapter. | Retry/backoff, error flow, DLQ hoặc bù trừ theo adapter và hạ tầng. |

Với `DirectChannel`, xử lý thường **đồng bộ trên thread của người gửi**. Nếu function trong transformer ném exception, nó có thể lan ngược về lời gọi `send(...)`. Việc một application có `errorChannel` không đồng nghĩa mọi exception đồng bộ đều tự động được đưa vào đó; error flow phụ thuộc cách endpoint, poller, executor hoặc adapter xử lý lỗi.

Khi thay `DirectChannel` bằng `ExecutorChannel`, `QueueChannel` hoặc một broker adapter:

- Điểm và thời điểm lỗi xuất hiện có thể thay đổi.
- Bên gửi có thể chỉ biết đã đặt message vào queue, chưa biết nghiệp vụ hoàn thành.
- Có thể cần timeout, retry, quan sát trạng thái, dead-letter channel và idempotency.
- Cần xác định lại thứ tự xử lý, concurrency và giới hạn số message đang chạy.

**Không coi composition là transaction**: `catalog.lookup("f1|f2")` không đảm bảo hai hàm commit/rollback cùng nhau; nếu một bước đã có side effect trước khi bước sau lỗi, cần thiết kế bù trừ hoặc quản lý transaction phù hợp.

## 11. Reactive function trong IntegrationFlow

SCF còn hỗ trợ các kiểu như:

~~~java
Function<Flux<OrderRequest>, Flux<RoutingDecision>> reactiveClassify
~~~

Ở đây đầu vào/đầu ra không còn là một `OrderRequest` đơn lẻ. Không nên đưa trực tiếp function này vào:

~~~java
.transform(OrderRequest.class, reactiveFunction::apply)
~~~

bởi `reactiveFunction.apply(...)` mong đợi một `Flux<OrderRequest>`, còn transformer đang nhận một payload `OrderRequest`. Cần có ranh giới reactive phù hợp (ví dụ reactive channel, nguồn `Flux` hoặc endpoint xử lý stream), đồng thời thiết kế subscription, backpressure, lifecycle và error propagation.

Spring Cloud Function hỗ trợ mô hình reactive, và Spring Integration có DSL/endpoint reactive, nhưng tính tương thích phụ thuộc kiểu chính xác, phiên bản và adapter. Đừng ép `Flux` thành một payload thông thường chỉ để code biên dịch. Hãy kiểm thử cả chuỗi dưới tải và trường hợp stream lỗi/kết thúc.

## 12. Kiểm thử từng lớp của lời gọi catalog

### 12.1. Unit test function

Chỉ gọi logic nghiệp vụ:

~~~java
OrderFunctions functions = new OrderFunctions();

OrderRequest normalized =
        functions.normalizeOrder()
                 .apply(new OrderRequest(" dh-042 ", 1_750_000));

RoutingDecision decision =
        functions.classifyOrder().apply(normalized);

assertEquals("DH-042", decision.id());
assertEquals("PRIORITY", decision.tier());
~~~

Cần JUnit 5 và static import `org.junit.jupiter.api.Assertions.assertEquals`. Các ca cần bổ sung: ngưỡng `1_000_000` đúng bằng mức ưu tiên; `999_999` thuộc standard; mã rỗng hoặc tổng tiền bằng/nhỏ hơn 0 bị từ chối.

### 12.2. Test catalog và composition

Trong test có Spring context:

~~~java
@Autowired
FunctionCatalog catalog;

@Test
void catalogShouldComposeByName() {
    Function<OrderRequest, RoutingDecision> f =
            catalog.lookup("normalizeOrder|classifyOrder");

    assertNotNull(f);
    assertEquals(
            "STANDARD",
            f.apply(new OrderRequest(" a-1 ", 100_000)).tier());
}
~~~

Test này giúp phát hiện việc bean không vào catalog, sai tên function, loại kiểu không tương thích hoặc lỗi composition.

### 12.3. Integration test với channel và flow

~~~java
@SpringBootTest
class OrderFlowTest {

    @Autowired
    ApplicationContext context;

    @Autowired
    @Qualifier("priorityResults")
    BlockingQueue<RoutingDecision> priorityResults;

    @Autowired
    @Qualifier("standardResults")
    BlockingQueue<RoutingDecision> standardResults;

    @Test
    void shouldSendPriorityOrderToPriorityChannel() {
        priorityResults.clear();
        standardResults.clear();

        MessageChannel input =
                context.getBean("orders.input", MessageChannel.class);

        assertTrue(input.send(new GenericMessage<>(
                new OrderRequest(" dh-042 ", 1_750_000))));

        RoutingDecision result = priorityResults.poll();

        assertNotNull(result);
        assertEquals("DH-042", result.id());
        assertEquals("PRIORITY", result.tier());
        assertTrue(standardResults.isEmpty());
    }
}
~~~

Các import chính: `org.springframework.boot.test.context.SpringBootTest`, `org.springframework.context.ApplicationContext`, `org.springframework.beans.factory.annotation.Autowired`, `org.springframework.beans.factory.annotation.Qualifier`, `org.junit.jupiter.api.Test`, `org.springframework.messaging.MessageChannel`, `org.springframework.messaging.support.GenericMessage`, `java.util.concurrent.BlockingQueue` và các static assertion của JUnit 5.

Test giả định ứng dụng có Spring Boot test starter và quét hai cấu hình `OrderFunctions`, `OrderIntegration`. Với `DirectChannel`, kết quả đã đi tới handler trước khi `send(...)` trả về; nếu thay bằng bất đồng bộ/broker, dùng kiểm tra có thời hạn thay vì `poll()` ngay lập tức. Với nhiều test chạy song song, nên tách trạng thái queue theo test để tránh giao thoa.

### 12.4. Bảng kiểm lỗi thường gặp

| Triệu chứng | Kiểm tra trước |
| --- | --- |
| `catalog` không inject được | Có SCF context dependency, auto-configuration và phiên bản tương thích chưa? |
| `catalog.lookup("name")` trả `null` hoặc function không mong đợi | Bean có được đăng ký? Tên có đúng? Có single-function fallback đang che lỗi tên sai không? |
| Composition sai kiểu | Kiểm tra `f1` output và `f2` input; converter có đáp ứng hợp đồng không? |
| Transformer ném `ClassCastException` | Payload đến từ channel là kiểu gì? Có đưa JSON string vào flow nhận POJO không? |
| Message không đến đích | Channel input có đúng tên? Router mapping có đủ khóa? Có handler/subscriber ở channel đích? |
| Mất trace/correlation header | Có transformer/adaptor nào tạo message mới và bỏ header không? |
| Test đồng bộ chạy nhưng production lỗi ngẫu nhiên | Cần kiểm tra executor/broker, concurrency, retry, ordering và idempotency. |

## 13. Những quyết định thiết kế nên giữ nhất quán

1. **Đặt logic nghiệp vụ trong function.** Chỉ để function biết `OrderRequest`/`RoutingDecision`, tránh chứa logic gửi thẳng tới channel.
2. **Đặt điều phối trong flow.** Router, filter, splitter, aggregator, retry advice và adapter thuộc EIP/infra layer.
3. **Tra cứu tên function ổn định và fail fast.** Với function cần dùng trong một flow cố định, lookup khi dựng flow thuận tiện hơn lookup trên từng message.
4. **Chọn đúng điểm gọi theo interface.** `Function` thường dùng `transform`; `Consumer` dùng handler cuối; `Supplier` dùng polling source hoặc nguồn được adapter quản lý.
5. **Dùng composition cho các biến đổi liền kề.** Khi cần thêm EIP giữa các bước, tách thành nhiều transformer.
6. **Kiểm soát kiểu dữ liệu ở ranh giới.** JSON, POJO, `Message<T>`, header, reactive stream đều phải có hợp đồng rõ ràng.
7. **Thiết kế lỗi theo môi trường gọi.** HTTP có response/error khác với broker có retry/redelivery/DLQ; function không tự đảm bảo cách truyền lỗi thống nhất qua mọi adapter.
8. **Kiểm thử theo ba lớp.** Function thuần, catalog/composition và `IntegrationFlow` với channel/adapter thực tế.

### Câu hỏi tự kiểm tra

- Tại sao lấy bean `Function` từ `ApplicationContext` không hoàn toàn giống gọi `catalog.lookup(...)`?
- Khi nào nên chọn `transform(...)`, khi nào `handle(...)`?
- Nếu cần routing dựa trên `tier`, phần nào do function thực hiện và phần nào do Spring Integration thực hiện?
- Đặt `spring.cloud.function.definition` có làm `IntegrationFlow` tự nhận message từ broker không?
- Vì sao function reactive nhận `Flux<T>` không thể tùy tiện đưa vào transformer mong đợi `T`?
- Nếu xử lý bị lặp sau broker redelivery, đâu là vị trí cần bảo đảm idempotency?

## 14. Tài liệu chính thức

- [Spring Cloud Function — Programming model](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html): `FunctionCatalog`, lookup, wrapper, conversion, composition và kiểu function.
- [Spring Cloud Function — Spring Integration Interaction](https://docs.spring.io/spring-cloud-function/reference/spring-integration.html): module `spring-cloud-function-integration`, `FunctionFlowBuilder` và các toán tử `apply`/`accept`.
- [Spring Integration — Java DSL](https://docs.spring.io/spring-integration/reference/dsl/java-basics.html): `IntegrationFlow`, `transform` và các endpoint.
- [Spring Integration — Functions Support](https://docs.spring.io/spring-integration/reference/functions-support.html): sử dụng các interface `java.util.function` với Integration Flow.
- [Spring Integration — Router Implementations](https://docs.spring.io/spring-integration/reference/router/implementations.html): ví dụ routing theo payload/channels.

**Tổng kết:** Để gọi các hàm tái sử dụng của Spring Cloud Function bên trong `IntegrationFlow`, hãy dùng `FunctionCatalog.lookup(...)` (có thể kèm composition) và nối kết quả vào `transform`, `handle` hoặc nguồn `Supplier` phù hợp. Khi dùng module `spring-cloud-function-integration`, `FunctionFlowBuilder` cho phép diễn đạt trực tiếp `apply`/`accept` theo tên hàm. Trong cả hai cách, EIP và cấu hình vận chuyển vẫn do Spring Integration cùng adapter tương ứng đảm nhiệm, giúp một hàm nghiệp vụ có thể dùng lại qua HTTP, sự kiện hoặc serverless.
