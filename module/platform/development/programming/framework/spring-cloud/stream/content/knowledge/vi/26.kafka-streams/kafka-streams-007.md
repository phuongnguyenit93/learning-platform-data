# Ghép hàm được hỗ trợ và tên binding của topology ghép

Kafka Streams binder cho phép xây dựng một topology từ nhiều function bean Java mà không cần viết thêm một function trung gian chỉ để nối kết quả của hàm trước vào hàm sau. Cơ chế này dùng biểu thức **function composition** trong thuộc tính `spring.cloud.function.definition`. Dấu `|` nối các function theo thứ tự thực thi; binder tạo một processor topology và sinh tên binding dựa trên tên các bean được ghép.

Ví dụ, hai function `normalize` và `enrich` có thể được khai báo riêng, sau đó kích hoạt bằng định nghĩa `normalize|enrich`. Binder nối output kiểu `KStream` của `normalize` vào input của `enrich`. Binding đầu vào và đầu ra được đặt tên theo function ghép là `normalizeenrich-in-0` và `normalizeenrich-out-0`.

Nắm đúng các kiểu function được hỗ trợ, giới hạn ghép hàm và quy tắc đặt tên binding giúp cấu hình destination, Serde và các thuộc tính Kafka Streams vào đúng cổng của topology.

## 1. Composition trong Kafka Streams binder

Kafka Streams binder dùng functional programming model với các kiểu Java như `Function`, `Consumer`, `BiFunction` và các function dạng curried để biểu diễn `KStream`, `KTable` hoặc `GlobalKTable` đầu vào/đầu ra.

Một function bean thường thực hiện một bước xử lý có thể đọc hiểu độc lập:

- Chuẩn hóa dữ liệu hoặc kiểm tra điều kiện.
- Làm giàu sự kiện bằng cách join với bảng tham chiếu.
- Tính toán, tổng hợp hoặc chuyển đổi cấu trúc dữ liệu.
- Ghi kết quả ra topic hoặc kết thúc topology bằng một Consumer.

Composition nối các bước này thành một đường xử lý tuyến tính. Mỗi function vẫn là một bean Spring riêng, nhưng binder coi biểu thức ghép là một processor function để tạo topology.

~~~mermaid
flowchart LR
    A[(Topic orders)] --> B[Binding normalizeenrich-in-0]
    B --> C[normalize: KStream]
    C --> D[enrich: KStream]
    D --> E[Binding normalizeenrich-out-0]
    E --> F[(Topic enriched-orders)]
~~~

Trong sơ đồ, hai bước `normalize` và `enrich` được ghép thành một topology. Output trung gian giữa hai function không tự tạo topic hoặc output binding riêng. Chỉ input của toàn chuỗi và output cuối cùng trở thành binding, trừ khi function cuối là Consumer hoặc trả về nhiều KStream theo mô hình branching.

## 2. Khai báo các function bean riêng

Giả sử hệ thống nhận sự kiện đơn hàng, kiểm tra giá trị rồi tạo bản tóm tắt để phát cho downstream:

~~~java
import java.math.BigDecimal;
import java.util.function.Function;

import org.apache.kafka.streams.kstream.KStream;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrderFunctions {

    @Bean
    public Function<KStream<String, Order>, KStream<String, Order>>
            normalize() {
        return orders -> orders
                .filter((key, order) -> order.total().signum() >= 0);
    }

    @Bean
    public Function<KStream<String, Order>, KStream<String, OrderSummary>>
            summarize() {
        return orders -> orders.mapValues(order ->
                new OrderSummary(order.id(), order.total()));
    }

    public record Order(String id, BigDecimal total) {
    }

    public record OrderSummary(String orderId, BigDecimal total) {
    }
}
~~~

Mỗi method `@Bean` có tên bean là tên method. Vì vậy, hai function trong ví dụ có tên `normalize` và `summarize`. Binder sử dụng chính các tên này trong function definition và tên binding được sinh ra.

Function `normalize` nhận và trả về `KStream<String, Order>`. Function `summarize` nhận `KStream<String, Order>` và trả về `KStream<String, OrderSummary>`. Kiểu output của bước đầu tương thích với kiểu input của bước sau, nên có thể ghép hai function.

Kích hoạt composition:

~~~yaml
spring:
  cloud:
    function:
      definition: "normalize|summarize"
    stream:
      bindings:
        normalizesummarize-in-0:
          destination: orders
        normalizesummarize-out-0:
          destination: order-summaries
~~~

Binder tạo topology từ `normalize` rồi tới `summarize`. Tên binding mặc định:

- `normalizesummarize-in-0`: input của function ghép.
- `normalizesummarize-out-0`: output cuối cùng của function ghép.

Không có binding `normalize-out-0` hoặc `summarize-in-0` cho đoạn nối nội bộ. Nếu muốn ghi một kết quả trung gian ra topic, hãy biểu diễn thao tác ghi trong Kafka Streams DSL hoặc thiết kế một topology/processor riêng phù hợp.

## 3. Phân biệt dấu | và dấu ;

Hai ký tự này có ý nghĩa khác nhau trong `spring.cloud.function.definition`:

| Cú pháp | Ý nghĩa | Kết quả |
|---|---|---|
| `normalize|summarize` | Ghép các function thành một chuỗi. | Một topology tuyến tính, binding đầu vào/đầu ra của function ghép. |
| `normalize;summarize` | Kích hoạt hai function độc lập. | Hai processor/topology riêng, mỗi function có binding riêng. |
| `normalize|summarize;archive` | Ghép hai function đầu và kích hoạt `archive` riêng. | Một topology ghép và một topology độc lập. |

Ví dụ:

~~~yaml
spring:
  cloud:
    function:
      definition: "normalize|summarize;archive"
~~~

Trong cấu hình này, `normalize` và `summarize` tạo một topology ghép; `archive` là một processor khác. Dấu chấm phẩy không nối output của `summarize` sang `archive`.

Khi một ứng dụng có nhiều Kafka Streams processor độc lập, mỗi processor có application ID riêng. Cần cấu hình application ID theo từng function nếu ứng dụng chạy nhiều processor và muốn kiểm soát rõ consumer group, state store và khả năng mở rộng. Không dùng tên binding thay cho application ID.

## 4. Những kiểu function có thể ghép

Kafka Streams binder hỗ trợ composition có giới hạn để tạo topology tuyến tính:

| Thành phần đầu tiên | Thành phần tiếp theo | Hỗ trợ | Ghi chú |
|---|---|---|---|
| `Function` | Một hoặc nhiều `Function` | Có | Output của bước trước phải khớp input bước sau. |
| `Function` | `Consumer` | Có | Consumer phải là bước cuối, topology không có output binding. |
| `BiFunction` | Một hoặc nhiều `Function` | Có | `BiFunction` phải đứng đầu chuỗi. |
| `BiFunction` | `Consumer` | Có | Consumer kết thúc chuỗi. |
| `BiFunction` | `BiFunction` | Không | Không ghép một BiFunction tiếp theo trong cùng definition. |
| `Consumer` | Bất kỳ function nào | Không | Consumer không thể là bước đầu vì nó không tạo output cho bước kế tiếp. |
| `BiConsumer` | Bất kỳ function nào | Không | BiConsumer không được hỗ trợ trong composition. |
| Function trả `KStream[]` | Function tiếp theo | Không | Function tạo branching array chỉ có thể là bước cuối. |

Các dạng composition trên là phạm vi hỗ trợ của Kafka Streams binder. Không suy rộng từ quy tắc composition chung của Spring Cloud Function sang mọi kiểu `Supplier`, `BiConsumer` hoặc function tùy ý trong Kafka Streams binder.

### Function nối Function

Đây là trường hợp đơn giản nhất. Function sau nhận đúng kiểu mà function trước trả về:

~~~java
@Bean
public Function<KStream<String, Order>, KStream<String, Order>>
        validateOrder() {
    return stream -> stream.filter(
            (key, order) -> order.total().signum() > 0);
}

@Bean
public Function<KStream<String, Order>, KStream<String, EnrichedOrder>>
        enrichOrder() {
    return stream -> stream.mapValues(order ->
            new EnrichedOrder(order.id(), order.total(), "STANDARD"));
}
~~~

Định nghĩa:

~~~yaml
spring:
  cloud:
    function:
      definition: "validateOrder|enrichOrder"
~~~

Output `KStream<String, Order>` của `validateOrder` trở thành input của `enrichOrder`. Nếu kiểu dữ liệu không tương thích, composition không thể được xây dựng đúng.

### Function kết thúc bằng Consumer

Một topology có thể biến đổi dữ liệu rồi ghi vào hệ thống đích ngay trong Consumer:

~~~java
import java.util.function.Consumer;

@Bean
public Function<KStream<String, Order>, KStream<String, OrderSummary>>
        summarizeOrder() {
    return stream -> stream.mapValues(order ->
            new OrderSummary(order.id(), order.total()));
}

@Bean
public Consumer<KStream<String, OrderSummary>> storeSummary(
        SummaryRepository repository) {
    return stream -> stream.foreach((key, summary) ->
            repository.save(summary));
}
~~~

Định nghĩa:

~~~yaml
spring:
  cloud:
    function:
      definition: "summarizeOrder|storeSummary"
~~~

`storeSummary` là thành phần cuối cùng. Function ghép có input binding mặc định `summarizeOrderstoreSummary-in-0` và không có output binding vì Consumer không trả về KStream. Việc ghi dữ liệu trong `foreach` là side effect của ứng dụng; cần cân nhắc tính idempotent và tác động của retry/reprocessing.

## 5. Ghép function bắt đầu bằng BiFunction

Khi topology có hai nguồn đầu vào, function đầu tiên có thể là `BiFunction`. Ví dụ, join luồng đơn hàng với bảng khách hàng:

~~~java
import java.util.function.BiFunction;

import org.apache.kafka.streams.kstream.KStream;
import org.apache.kafka.streams.kstream.KTable;

@Bean
public BiFunction<KStream<String, Order>,
        KTable<String, Customer>,
        KStream<String, EnrichedOrder>> enrichFromCustomer() {
    return (orders, customers) -> orders.leftJoin(
            customers,
            (order, customer) -> new EnrichedOrder(
                    order.id(),
                    order.total(),
                    customer == null ? "UNKNOWN" : customer.segment()
            )
    );
}

@Bean
public Function<KStream<String, EnrichedOrder>,
        KStream<String, OrderView>> toOrderView() {
    return enriched -> enriched.mapValues(order ->
            new OrderView(order.id(), order.segment()));
}
~~~

Khai báo:

~~~yaml
spring:
  cloud:
    function:
      definition: "enrichFromCustomer|toOrderView"
~~~

`BiFunction` phải là function đầu tiên trong chuỗi. Các thành phần sau nó phải là `Function` hoặc `Consumer`, không phải một `BiFunction` khác.

Hai input được đánh số theo thứ tự tham số:

- Tham số thứ nhất `KStream<String, Order>` tạo input binding `enrichFromCustomertoOrderView-in-0`.
- Tham số thứ hai `KTable<String, Customer>` tạo input binding `enrichFromCustomertoOrderView-in-1`.
- Output cuối cùng tạo binding `enrichFromCustomertoOrderView-out-0`.

Trong Kafka Streams binder, kiểu tham số `KStream`, `KTable` hoặc `GlobalKTable` xác định loại binding. Thứ tự tham số là một phần của hợp đồng topology; đổi thứ tự có thể khiến cấu hình destination hoặc Serde bị gắn vào sai nguồn.

## 6. Dùng curried function để có nhiều input

Khi topology cần hơn hai input, binder hỗ trợ các function dạng **currying**. Thay vì một function có ba hoặc nhiều tham số, method trả về các function lồng nhau. Mỗi lần áp dụng một phần tạo ra một input binding.

Ví dụ join đơn hàng với bảng khách hàng và bảng sản phẩm:

~~~java
import java.util.function.Function;

import org.apache.kafka.streams.kstream.GlobalKTable;
import org.apache.kafka.streams.kstream.KStream;

@Bean
public Function<KStream<String, Order>,
        Function<GlobalKTable<String, Customer>,
                Function<GlobalKTable<String, Product>,
                        KStream<String, EnrichedOrder>>>> enrichOrder() {

    return orders -> customers -> products ->
            orders.join(
                    customers,
                    (orderKey, order) -> order.customerId(),
                    (order, customer) -> new OrderWithCustomer(order, customer)
            ).join(
                    products,
                    (key, value) -> value.order().productId(),
                    (value, product) -> new EnrichedOrder(
                            value.order(), value.customer(), product)
            );
}
~~~

Định nghĩa function đơn lẻ này:

~~~yaml
spring:
  cloud:
    function:
      definition: enrichOrder
~~~

Binder tạo ba input binding theo thứ tự:

| Binding | Kiểu đầu vào | Ví dụ destination |
|---|---|---|
| `enrichOrder-in-0` | `KStream<String, Order>` | `orders` |
| `enrichOrder-in-1` | `GlobalKTable<String, Customer>` | `customers` |
| `enrichOrder-in-2` | `GlobalKTable<String, Product>` | `products` |
| `enrichOrder-out-0` | `KStream<String, EnrichedOrder>` | `enriched-orders` |

Có thể ghép function curried đầu tiên với một Function tiếp theo:

~~~java
@Bean
public Function<KStream<String, EnrichedOrder>,
        KStream<String, OrderView>> toOrderView() {
    return stream -> stream.mapValues(EnrichedOrder::toView);
}
~~~

Định nghĩa:

~~~yaml
spring:
  cloud:
    function:
      definition: "enrichOrder|toOrderView"
~~~

Trong trường hợp này, tên binding mặc định của function ghép là:

- `enrichOrdertoOrderView-in-0`
- `enrichOrdertoOrderView-in-1`
- `enrichOrdertoOrderView-in-2`
- `enrichOrdertoOrderView-out-0`

Curried function cho phép có nhiều input binding mà không cần một `BiFunction` cho mọi trường hợp. Tuy nhiên, quá nhiều input làm chữ ký Java khó đọc và topology khó vận hành. Nếu một processor cần nhiều nguồn độc lập, hãy xem xét tách topology hoặc đưa dữ liệu tham chiếu vào state store phù hợp.

## 7. Quy tắc tương thích giữa kiểu output và input

Composition là nối các function theo kiểu dữ liệu. Output của function trước phải là kiểu input mà function tiếp theo chấp nhận. Binder không tự động chuyển đổi mọi cấu trúc Kafka Streams để làm cho hai function tương thích.

| Output của bước trước | Input của bước sau | Kết quả |
|---|---|---|
| `KStream<K, V>` | `KStream<K, V>` | Ghép trực tiếp nếu generic types tương thích. |
| `KTable<K, V>` | `KTable<K, V>` | Ghép trực tiếp. |
| `KStream<K, V>` | `KTable<K, V>` | Không tương thích trực tiếp. |
| `KTable<K, V>` | `KStream<K, V>` | Không tương thích trực tiếp nếu function sau khai báo KStream. |
| `KTable<K, V>` | `KTable<K, V>` | Ghép được; function sau phải nhận KTable. |

### Trường hợp KTable làm output

Kafka Streams binder cho phép `KTable` là output binding cuối cùng. Nhưng khi `KTable` là output trung gian trong composition, function tiếp theo phải nhận `KTable`.

Ví dụ hợp lệ:

~~~java
@Bean
public Function<KStream<String, String>, KTable<String, String>>
        toTable() {
    return KStream::toTable;
}

@Bean
public Function<KTable<String, String>, KStream<String, String>>
        toStream() {
    return KTable::toStream;
}
~~~

Định nghĩa:

~~~yaml
spring:
  cloud:
    function:
      definition: "toTable|toStream"
~~~

Function `toStream` nhận `KTable` vì output của `toTable` là `KTable`. Nếu thay chữ ký của `toStream` thành `Function<KStream<...>, ...>`, chuỗi không còn tương thích. Việc chuyển giữa table và stream phải được thể hiện rõ bằng API Kafka Streams như `toStream()` hoặc `toTable()`.

## 8. Giới hạn khi ghép function

Kafka Streams binder hỗ trợ composition tối giản cho linear topology. Các giới hạn quan trọng:

1. `Function` có thể ghép với một hoặc nhiều `Function`.
2. `Function` có thể kết thúc bằng một `Consumer`.
3. `BiFunction` chỉ được đứng đầu; các phần tiếp theo là `Function` hoặc `Consumer`.
4. Không ghép `BiFunction` tiếp theo vào sau `BiFunction` đầu tiên.
5. Không ghép `BiConsumer`.
6. Không bắt đầu chuỗi bằng `Consumer`.
7. Function trả về `KStream[]` để branching chỉ được nằm cuối chuỗi.
8. Kiểu KStream/KTable giữa hai bước phải tương thích.
9. Không ghép một function dùng regular Kafka message-channel binder với một function dùng Kafka Streams binder trong cùng một chuỗi. Một ứng dụng có thể chạy cả hai loại processor độc lập, nhưng composition phải nằm trong cùng mô hình binder.

### Branching và KStream[]

Kafka Streams hỗ trợ chia một stream thành nhiều nhánh. Function có thể trả về mảng `KStream[]`; binder tạo một output binding cho mỗi phần tử của mảng.

Ví dụ function branching:

~~~java
@Bean
public Function<KStream<String, Order>, KStream<String, Order>[]>
        branchOrders() {
    return input -> {
        KStream<String, Order> highValue =
                input.filter((key, order) -> order.total().intValue() >= 1000);
        KStream<String, Order> regular =
                input.filter((key, order) -> order.total().intValue() < 1000);

        @SuppressWarnings("unchecked")
        KStream<String, Order>[] branches = new KStream[] {
                highValue, regular
        };
        return branches;
    };
}
~~~

Output binding mặc định:

- `branchOrders-out-0`
- `branchOrders-out-1`

Nếu function branching là function cuối của một chuỗi composition, tên binding được sinh theo tên function ghép cộng hậu tố output. Không thể nối một function khác sau bước trả về `KStream[]` trong cùng composition; hãy thực hiện các bước tiếp theo riêng trong từng nhánh hoặc thiết kế topology khác.

## 9. Tên binding mặc định của function đơn lẻ

Trước khi hiểu tên binding của composition, cần nắm quy tắc của một function độc lập:

| Kiểu function | Binding đầu vào mặc định | Binding đầu ra mặc định |
|---|---|---|
| `Consumer<KStream<...>>` | `<bean>-in-0` | Không có |
| `Function<KStream<...>, KStream<...>>` | `<bean>-in-0` | `<bean>-out-0` |
| `BiFunction<KStream<...>, KTable<...>, KStream<...>>` | `<bean>-in-0`, `<bean>-in-1` | `<bean>-out-0` |
| Curried Function có ba input | `<bean>-in-0`, `-in-1`, `-in-2` | `<bean>-out-0` |
| Function trả `KStream[]` | `<bean>-in-0` | `<bean>-out-0`, `-out-1`, ... |

Tên binding được tạo từ tên function bean và vị trí input/output. Đây là tên logic trong Spring Cloud Stream để cấu hình destination, group, Serde và các thuộc tính binding.

Nếu không cấu hình `destination`, binder có thể dùng tên binding làm tên topic mặc định hoặc yêu cầu topic tương ứng đã tồn tại tùy quyền và cấu hình provisioning. Trong production, nên đặt destination rõ ràng để tránh vô tình tạo topic theo tên binding.

## 10. Quy tắc tên binding của topology ghép

Với function composition, binder ghép tên các function bean theo đúng thứ tự trong definition để tạo tên function ghép. Sau đó, binder thêm hậu tố input/output và chỉ số.

Ví dụ:

~~~text
spring.cloud.function.definition=foo|bar

Tên function ghép: foobar
Input binding:      foobar-in-0
Output binding:     foobar-out-0
~~~

Ví dụ có ba bước:

~~~text
spring.cloud.function.definition=decode|validate|enrich

Tên function ghép: decodevalidateenrich
Input binding:      decodevalidateenrich-in-0
Output binding:     decodevalidateenrich-out-0
~~~

Nếu function đầu là curried và có hai input:

~~~text
spring.cloud.function.definition=curriedFoo|bar

Tên function ghép: curriedFoobar
Input binding 0:   curriedFoobar-in-0
Input binding 1:   curriedFoobar-in-1
Output binding:    curriedFoobar-out-0
~~~

Nếu function cuối là Consumer:

~~~text
spring.cloud.function.definition=normalize|persist

Input binding: normalizepersist-in-0
Output binding: không có
~~~

Binding name không phải topic name, consumer group hay application ID. Nó là tên cổng của topology để Spring Cloud Stream áp dụng cấu hình. Destination mới là tên Kafka topic mà binding kết nối.

## 11. Đặt destination cho các binding của composition

Ví dụ hai function `normalize|enrich` được ghép thành một topology:

~~~yaml
spring:
  cloud:
    function:
      definition: "normalize|enrich"
    stream:
      bindings:
        normalizeenrich-in-0:
          destination: orders
        normalizeenrich-out-0:
          destination: enriched-orders
~~~

`normalizeenrich-in-0` đọc từ topic `orders`; `normalizeenrich-out-0` ghi kết quả cuối cùng tới topic `enriched-orders`.

Không cấu hình destination cho một binding trung gian như `normalize-out-0`, vì binding đó không được tạo trong topology ghép. Nếu dùng nhầm tên, thuộc tính có thể không áp dụng vào topology mà bạn mong muốn.

### Cấu hình nhiều input

Với `curriedFoo|bar`, mỗi input phải có destination riêng:

~~~yaml
spring:
  cloud:
    function:
      definition: "curriedFoo|bar"
    stream:
      bindings:
        curriedFoobar-in-0:
          destination: orders
        curriedFoobar-in-1:
          destination: customers
        curriedFoobar-out-0:
          destination: enriched-orders
~~~

Input thứ nhất và thứ hai được gắn theo thứ tự tham số của curried function. Hãy kiểm tra chữ ký bean trước khi gán destination, đặc biệt khi một nguồn là KTable hoặc GlobalKTable.

## 12. Đổi tên binding mặc định bằng alias

Tên binding ghép dài có thể khó đọc khi topology có nhiều function. Spring Cloud Stream cho phép ánh xạ tên mặc định sang một alias dễ hiểu qua:

~~~text
spring.cloud.stream.function.bindings.<default-binding-name>
~~~

Ví dụ đổi tên binding của `normalize|enrich`:

~~~yaml
spring:
  cloud:
    function:
      definition: "normalize|enrich"
    stream:
      function:
        bindings:
          normalizeenrich-in-0: orders-input
          normalizeenrich-out-0: orders-output
      bindings:
        orders-input:
          destination: orders
        orders-output:
          destination: enriched-orders
~~~

Sau ánh xạ:

- `normalizeenrich-in-0` được gọi qua alias `orders-input`.
- `normalizeenrich-out-0` được gọi qua alias `orders-output`.
- Thuộc tính binding-level như destination phải được đặt dưới alias mới.

Nếu cấu hình thêm group, consumer properties hoặc extended Kafka Streams properties, cũng phải dùng alias tương ứng sau khi đã đổi tên. Không tiếp tục đặt các thuộc tính dưới tên mặc định cũ rồi mong chúng tự áp dụng vào alias.

### Alias cho topology nhiều input

~~~yaml
spring:
  cloud:
    function:
      definition: "enrichOrder|toOrderView"
    stream:
      function:
        bindings:
          enrichOrdertoOrderView-in-0: orders-source
          enrichOrdertoOrderView-in-1: customers-table
          enrichOrdertoOrderView-in-2: products-table
          enrichOrdertoOrderView-out-0: order-views
      bindings:
        orders-source:
          destination: orders
        customers-table:
          destination: customers
        products-table:
          destination: products
        order-views:
          destination: order-views
~~~

Các alias làm rõ vai trò của từng nguồn. Kiểu binding vẫn do chữ ký `KStream`, `KTable` hoặc `GlobalKTable` trong function quyết định; alias chỉ đổi tên cổng cấu hình.

## 13. Binding name và Kafka Streams extended properties

Kafka Streams binder có thuộc tính mở rộng theo binding name, ví dụ Serde, state store materialization, timestamp extractor hoặc event type. Khi đã đổi tên binding, hãy sử dụng alias cho cả thuộc tính mở rộng.

Ví dụ:

~~~yaml
spring:
  cloud:
    function:
      definition: "normalize|enrich"
    stream:
      function:
        bindings:
          normalizeenrich-in-0: orders-input
          normalizeenrich-out-0: orders-output
      bindings:
        orders-input:
          destination: orders
        orders-output:
          destination: enriched-orders
      kafka:
        streams:
          bindings:
            orders-input:
              consumer:
                value-serde: org.apache.kafka.common.serialization.Serdes$StringSerde
~~~

Đây là ví dụ minh họa vị trí cấu hình Serde theo alias. Serde thực tế phải phù hợp với key/value của topic và kiểu dữ liệu mà topology xử lý. Nếu không đổi tên binding, dùng binding name mặc định `normalizeenrich-in-0` trong namespace Kafka Streams.

Không nhầm:

- `spring.cloud.stream.bindings.<name>` là cấu hình chung của binding như destination.
- `spring.cloud.stream.kafka.streams.bindings.<name>` là cấu hình mở rộng riêng của Kafka Streams binder.
- `spring.cloud.stream.function.bindings.<default-binding-name>` là ánh xạ tên binding mặc định sang alias.

## 14. Phân biệt binding name và application ID

Kafka Streams dùng `application.id` để định danh processor application, consumer group và trạng thái liên quan. Binding name chỉ định danh input/output port trong Spring Cloud Stream.

| Thành phần | Ví dụ | Mục đích |
|---|---|---|
| Function bean name | `normalize` | Định danh function bean trong Spring. |
| Function definition | `normalize|enrich` | Khai báo composition và thứ tự thực thi. |
| Composed function name | `normalizeenrich` | Tên function ghép được binder suy ra. |
| Binding name | `normalizeenrich-in-0` | Cổng input để cấu hình destination và consumer properties. |
| Destination | `orders` | Kafka topic nguồn hoặc đích. |
| Application ID | `order-enrichment-v1` | Định danh Kafka Streams application và consumer group. |

Với nhiều Kafka Streams processor độc lập trong cùng ứng dụng, cần đặt application ID riêng cho từng processor theo cấu hình binder:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        streams:
          binder:
            functions:
              archive:
                application-id: order-archive-v1
              audit:
                application-id: order-audit-v1
~~~

Tên function trong thuộc tính `functions.<function-name>.applicationId` là function bean/processor được kích hoạt. Hãy kiểm tra đúng function name khi cấu hình nhiều processor. Không đặt application ID bằng binding name như `normalizeenrich-in-0`; hai khái niệm có vòng đời và ý nghĩa khác nhau.

## 15. Composition và nhiều processor độc lập trong một ứng dụng

Một ứng dụng có thể khai báo nhiều function bean và chỉ định các processor cần kích hoạt trong definition. Ví dụ:

~~~java
@Bean
public Function<KStream<String, Order>, KStream<String, Order>>
        normalize() {
    return stream -> stream.filter(
            (key, order) -> order.total().signum() >= 0);
}

@Bean
public Function<KStream<String, Order>, KStream<String, OrderSummary>>
        summarize() {
    return stream -> stream.mapValues(
            order -> new OrderSummary(order.id(), order.total()));
}

@Bean
public Consumer<KStream<String, AuditEvent>> audit(
        AuditRepository auditRepository) {
    return stream -> stream.foreach((key, event) ->
            auditRepository.store(event));
}
~~~

Cấu hình:

~~~yaml
spring:
  cloud:
    function:
      definition: "normalize|summarize;audit"
    stream:
      bindings:
        normalizesummarize-in-0:
          destination: orders
        normalizesummarize-out-0:
          destination: order-summaries
        audit-in-0:
          destination: audit-events
~~~

Trong ví dụ:

- `normalize|summarize` là một topology ghép có input và output.
- `audit` là một topology riêng chỉ có input.
- `audit` không nhận output trung gian từ `summarize`.

Nếu cần audit chính xác những sự kiện đã qua bước summarize, hãy nối audit vào composition hoặc publish một luồng riêng từ Kafka Streams DSL. Không dùng dấu `;` để mong binder tạo đường nối giữa hai processor.

## 16. Khi nào nên ghép hàm và khi nào nên tách topology?

Composition phù hợp với các bước xử lý tuyến tính có cùng vòng đời và cần chia sẻ một topology. Tách thành nhiều processor phù hợp khi các nhánh có yêu cầu triển khai, application ID, trạng thái, scaling hoặc quyền truy cập khác nhau.

| Tiêu chí | Ghép hàm bằng `|` | Processor độc lập bằng `;` |
|---|---|---|
| Topology | Một chuỗi tuyến tính | Nhiều topology riêng |
| Binding | Một bộ input/output của function ghép | Mỗi function có binding riêng |
| Output trung gian | Không tự tạo binding riêng | Có thể nối qua topic nếu cấu hình |
| Vòng đời | Các bước cùng processor | Mỗi processor có thể quản lý riêng |
| Application ID | Một processor identity cho topology ghép | Cần định danh theo từng processor |
| Phù hợp | Normalize → enrich → transform | Audit, projection và archive độc lập |

Không nên tạo composition quá dài chỉ để giảm số bean hoặc số dòng cấu hình. Một chuỗi tuyến tính có nhiều bước vẫn có thể khó kiểm thử, khó thay đổi và khó quan sát. Đặt ranh giới theo nghiệp vụ và yêu cầu vận hành.

## 17. Kiểm thử function composition và binding names

Kiểm thử nên xác nhận cả logic dữ liệu lẫn cấu hình topology:

1. Kiểm thử từng function bean độc lập để xác nhận logic transform.
2. Kiểm thử composition theo đúng thứ tự function.
3. Kiểm tra kiểu output/input tại mỗi điểm nối.
4. Kiểm tra số lượng và tên binding được binder tạo.
5. Xác nhận mỗi binding trỏ tới đúng destination.
6. Kiểm tra alias và các extended Kafka Streams properties được gắn đúng binding.
7. Với nhiều processor, xác nhận mỗi processor có application ID dự kiến.

### Ví dụ kiểm tra luồng xử lý

Với composition `normalize|summarize`, tạo các record đầu vào:

| Key | Order | Kết quả mong đợi |
|---|---|---|
| `o-1` | total = 120 | Giữ lại và tạo OrderSummary. |
| `o-2` | total = -5 | Bị lọc ở bước normalize. |
| `o-3` | total = 0 | Giữ lại nếu điều kiện `signum() >= 0`. |

Test topology nên xác nhận:

- Output chỉ chứa record qua được bước normalize.
- Giá trị output là OrderSummary được tạo bởi summarize.
- Key được giữ hoặc thay đổi đúng theo logic từng bước.
- Không có output binding trung gian cho function đầu tiên.

### Kiểm tra tên binding

Có thể quan sát binding được tạo qua Actuator bindings endpoint khi endpoint đã được bật. Với function ghép `normalize|summarize`, cần thấy input và output binding của topology ghép; không kỳ vọng binding riêng của từng function thành phần.

Với composition curried, kiểm tra đủ các input binding theo số phần tham số. Với function cuối là Consumer, không kỳ vọng output binding. Với function cuối trả `KStream[]`, kiểm tra số output binding bằng số stream trả về.

### Ma trận kiểm thử

| Tình huống | Thiết lập | Kết quả cần xác nhận |
|---|---|---|
| Function + Function | `normalize|summarize` | Một topology ghép, một input và một output. |
| Function + Consumer | `summarize|persist` | Một input, không có output binding. |
| BiFunction đầu tiên | `joinOrders|toView` | Hai input binding theo thứ tự tham số và một output. |
| Curried function | Ba input trong function đầu | Ba input binding được đánh số 0, 1, 2. |
| KTable trung gian | `toTable|toStream` | Function sau nhận KTable. |
| Sai kiểu nối | Output KStream nhưng function sau yêu cầu KTable | Phát hiện lỗi tương thích kiểu khi xây dựng composition. |
| Consumer đầu tiên | `consume|transform` | Definition không được hỗ trợ. |
| BiConsumer trong chuỗi | `joinAndConsume|transform` | Composition không được hỗ trợ. |
| BiFunction thứ hai | `joinA|joinB` | Composition không được hỗ trợ. |
| Branching ở giữa | Function trả KStream[] rồi nối function khác | Không được hỗ trợ. |
| Branching cuối | Function cuối trả KStream[] | Số output binding khớp số stream. |
| Alias binding | Đổi `normalizeenrich-in-0` thành `orders-input` | Destination và extended properties dùng alias mới. |
| Nhiều processor | `normalize|summarize;audit` | Một topology ghép và một topology audit độc lập. |
| Application ID | Hai processor có cấu hình ID riêng | Không dùng chung application ID ngoài dự kiến. |

## 18. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Không tìm thấy function trong definition | Tên trong `spring.cloud.function.definition` không trùng tên bean. | Kiểm tra tên method `@Bean` hoặc tên component. |
| Function được chạy thành topology riêng thay vì ghép | Dùng dấu `;` thay vì `|`. | Dùng `|` để composition; dùng `;` chỉ để kích hoạt processor độc lập. |
| Không tìm thấy binding `foo-in-0` | Function ghép tạo tên mới từ các bean name. | Dùng tên binding của function ghép, ví dụ `foobar-in-0`. |
| Destination không được áp dụng | Cấu hình dưới tên function thành phần hoặc alias cũ. | Đặt properties dưới binding name thực tế sau composition/alias. |
| Hai input bị đảo | Gán destination không theo thứ tự tham số của BiFunction/curried function. | Đối chiếu chữ ký Java và hậu tố `in-0`, `in-1`, ... |
| Composition lỗi kiểu | Output function trước không khớp input function sau. | Điều chỉnh generic types hoặc chuyển đổi KStream/KTable tường minh. |
| BiFunction không ghép được | BiFunction không đứng đầu hoặc có BiFunction tiếp theo. | Đặt một BiFunction đầu chuỗi, sau đó chỉ Function/Consumer. |
| Consumer không tạo output binding | Composition kết thúc bằng Consumer. | Đây là hành vi đúng; Consumer không trả KStream. |
| Không nối được sau branching | Function trung gian trả KStream[]. | Đưa branching thành bước cuối hoặc thiết kế lại topology. |
| Extended Serde không áp dụng | Binding đã đổi alias nhưng property vẫn dùng tên mặc định. | Dùng alias cho Kafka Streams binding properties. |
| Nhiều processor dùng chung application ID | Chưa cấu hình ID riêng cho từng processor. | Cấu hình `functions.<function-name>.applicationId` theo từng function. |
| Kỳ vọng processor độc lập nhận output của processor khác | Dùng dấu `;` như thể nó nối pipeline. | Dùng topic làm ranh giới và cấu hình output/input destination tương ứng. |

Khi điều tra, kiểm tra theo thứ tự: tên bean, function definition, kiểu function, kiểu input/output ở mỗi điểm nối, binding name được sinh, alias, destination và application ID. Cách này phân biệt lỗi composition với lỗi provision topic hoặc lỗi Kafka Streams runtime.

## 19. Checklist trước khi triển khai

- [ ] Tên trong function definition khớp chính xác tên bean.
- [ ] Dùng `|` cho composition và `;` cho các processor độc lập.
- [ ] Function đầu và các function tiếp theo thuộc kiểu được Kafka Streams binder hỗ trợ.
- [ ] Nếu dùng BiFunction, nó đứng đầu chuỗi.
- [ ] Nếu dùng Consumer, Consumer là thành phần cuối.
- [ ] Không ghép BiConsumer hoặc bắt đầu bằng Consumer.
- [ ] Output type của mỗi bước khớp input type của bước sau.
- [ ] Function dùng KTable ở giữa có function kế tiếp nhận KTable.
- [ ] Branching KStream[] chỉ xuất hiện ở bước cuối.
- [ ] Tên binding được tính theo tên function ghép và chỉ số input/output.
- [ ] Destination được đặt dưới binding name thực tế.
- [ ] Nếu dùng alias, tất cả binding-level và extended properties đều dùng alias.
- [ ] Application ID được phân biệt với function name và binding name.
- [ ] Các processor độc lập trong cùng ứng dụng có application ID phù hợp.
- [ ] Integration test xác nhận topology, binding và destination thực tế.

Kafka Streams binder hỗ trợ composition có giới hạn cho topology tuyến tính: `Function` có thể nối với `Function` và kết thúc bằng `Consumer`; `BiFunction` phải đứng đầu; curried function cho phép nhiều input. Dấu `|` ghép các function thành một processor, còn dấu `;` kích hoạt nhiều processor độc lập. Binder tạo tên binding từ tên function ghép, ví dụ `foo|bar` tạo `foobar-in-0` và `foobar-out-0`; nếu đổi tên bằng alias, mọi cấu hình binding phải dùng alias mới. Hiểu đúng kiểu dữ liệu, giới hạn composition và tên binding giúp topology được nối đúng và các thuộc tính Kafka Streams được áp dụng vào đúng input/output.

## Tài liệu tham khảo

- [Spring Cloud Stream 5.0.4 — Kafka Streams Programming Model](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-streams-binder/programming-model.html)
- [Spring Cloud Stream 5.0.4 — Ancillaries to the Programming Model](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-streams-binder/ancillaries-to-the-programming-model.html)
- [Spring Cloud Stream — Kafka Streams Binder Reference Guide](https://docs.spring.io/spring-cloud-stream-binder-kafka/docs/current/reference/html/kafka-streams.html)
