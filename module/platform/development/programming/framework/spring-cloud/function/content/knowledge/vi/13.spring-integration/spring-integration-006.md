# Kết hợp hàm với channel, poller, transformer và gateway

## 1. Bài toán: logic nghiệp vụ độc lập, luồng thông điệp có điều phối

**Spring Cloud Function (SCF)** cho phép viết nghiệp vụ bằng `Supplier<T>`, `Function<T,R>` và `Consumer<T>`, quản lý qua `FunctionCatalog` và ghép bằng composition. Một hàm chuẩn hóa hoặc phân loại đơn hàng không cần biết nó được gọi qua HTTP, sự kiện hay serverless.

**Spring Integration** đảm nhiệm phần kết nối và điều phối: message channel, polling endpoint, transformer, gateway, router, filter, error flow và các Enterprise Integration Patterns (EIP). Khi phối hợp, chúng ta có thể dùng **cùng một function** theo nhiều cách mà không sao chép quy tắc nghiệp vụ.

Giả sử có hai nguồn yêu cầu phân loại đơn:

- Người dùng gọi phương thức Java `orderGateway.classify(order)` và mong **nhận lại kết quả ngay** theo cơ chế request/reply.
- Một tác vụ lấy đơn còn chờ trong queue theo lịch và **đẩy kết quả đến consumer**, không có caller đợi reply.

Cả hai phải dùng chung `normalizeOrder|classifyOrder` trong `FunctionCatalog`.

~~~mermaid
flowchart LR
    subgraph G["Đường 1: Request / Reply"]
      A["Lời gọi OrderGateway.classify(...)"] --> B["orders.gatewayInput<br/>DirectChannel"]
      B --> C["Transformer:<br/>FunctionCatalog.lookup(...)"]
      C --> D["replyChannel<br/>của gateway"]
      D --> E["OrderDecision trả về caller"]
    end
    subgraph P["Đường 2: Polling"]
      Q["pendingOrders queue"] --> S["Supplier: pendingOrderSource"]
      T["Poller 250 ms"] --> S
      S --> F["apply:<br/>normalizeOrder|classifyOrder"]
      F --> H["orders.completed<br/>DirectChannel"]
      H --> I["Consumer: captureDecision"]
    end
~~~

**Mục tiêu học tập:** hiểu trách nhiệm của từng thành phần; cài hai đường đi dùng lại function; phân biệt `from("channel")`, `fromSupplier("supplier")`, `transform(...)` và gateway; biết kiểm thử và xử lý lỗi trong mô hình đồng bộ cũng như polling.

## 2. Bốn khái niệm cần phân biệt

| Thành phần | Vai trò trong Spring Integration | Ví dụ | Điều không tự bảo đảm |
| --- | --- | --- | --- |
| **Message Channel** | Kết nối các endpoint, quyết định đặc tính truyền message như đồng bộ, hàng đợi hoặc giao cho executor. | `DirectChannel`, `QueueChannel`, `ExecutorChannel`. | Không tự biến message thành JSON, lưu bền hay retry theo broker. |
| **Poller** | Chủ động gọi message source hoặc đọc pollable channel theo lịch. | `Pollers.fixedDelay(250).maxMessagesPerPoll(1)`. | Không tự bảo đảm acknowledgement, transaction hoặc khôi phục item đã lấy. |
| **Transformer** | Biến đổi payload/message để bước sau nhận dữ liệu có dạng phù hợp. | `.transform(OrderRequest.class, pipeline::apply)`. | Không tự quyết định nhánh đích như router. |
| **Messaging Gateway** | Tạo proxy của interface Java, ánh xạ lời gọi phương thức thành message, nhận reply và chuyển thành kiểu trả về. | `@MessagingGateway` và `OrderDecision classify(OrderRequest)`. | Không đồng nghĩa HTTP gateway, reverse proxy hoặc Spring Cloud Gateway. |

Một **IntegrationFlow** mô tả cách ghép những endpoint này. Các endpoint thực tế sẽ được Spring Integration tạo và quản lý trong application context.

### 2.1. Phân biệt channel với function

`Function<OrderRequest,OrderDecision>` trả một giá trị nhưng không tự gửi giá trị đó đến bất kỳ hệ thống nào. Sau khi `FunctionCatalog` trả function, Spring Integration có thể dùng nó như transformer, rồi gửi output qua `MessageChannel`.

Ngược lại, `MessageChannel` chủ yếu chuyển **`Message<T>`** giữa các endpoint; business rule như ngưỡng đơn ưu tiên nên nằm trong function để có thể tái sử dụng.

### 2.2. Hai kiểu kích hoạt rất khác nhau

~~~text
Push:
caller.send(message) hoặc gateway.method(arg)
    → channel → endpoint → reply/consumer

Pull:
scheduler trigger
    → poller → Supplier.get() / MessageSource.receive()
    → message → endpoint → consumer
~~~

Việc một đối tượng có kiểu `Supplier` chưa khiến nó tự chạy theo lịch. Ngữ nghĩa polling đến từ endpoint và poller do Spring Integration quản lý.

## 3. Dependency và điều kiện phiên bản

Ví dụ sử dụng Java 17+ và Spring Boot cùng Spring Cloud/Spring Integration phiên bản tương thích. Với Maven, giả định ứng dụng đã khai báo Spring Boot parent và Spring Cloud BOM phù hợp:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-function-integration</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-integration</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Gradle tương ứng:

~~~groovy
dependencies {
    implementation 'org.springframework.cloud:spring-cloud-function-integration'
    implementation 'org.springframework.boot:spring-boot-starter-integration'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Module `spring-cloud-function-integration` được giới thiệu từ **Spring Cloud Function 4.0.3**; nó cung cấp `FunctionFlowBuilder` và cách gọi function theo tên catalog ngay trong Integration DSL. Kiểm tra release train thực tế trước khi sao chép ví dụ; không ghép tùy tiện SCF, Spring Boot và Spring Integration thuộc các major version không tương thích.

Trong bài có hai kiểu DSL:

1. **Java DSL gốc**: `IntegrationFlow.from(...).transform(...)` với function được `catalog.lookup(...)`.
2. **Function DSL**: `FunctionFlowBuilder.fromSupplier(...).apply(...).accept(...)` dùng tên function được tra cứu tự động.

Cả hai đều có thể tồn tại trong một ứng dụng. Phần ví dụ sẽ đặt chúng trên **hai nguồn khác nhau** để tránh tạo hai subscriber cùng cạnh tranh hoặc xử lý trùng một message.

## 4. Thiết kế ví dụ: phân loại đơn hàng

Chúng ta định nghĩa:

~~~text
OrderRequest(id, totalVnd)
      │
      ├─ normalizeOrder: Function<OrderRequest, OrderRequest>
      │      kiểm tra và chuẩn hóa mã đơn
      ▼
OrderRequest sạch
      │
      ├─ classifyOrder: Function<OrderRequest, OrderDecision>
      │      đơn từ 1.000.000 VND trở lên → PRIORITY
      ▼
OrderDecision(id, totalVnd, lane)
~~~

Hai cách tiêu thụ cùng pipeline:

- **Gateway:** Java method `classify(...)` trả `OrderDecision` về caller.
- **Poller:** `Supplier<OrderRequest>` lấy đơn từ queue; flow gọi pipeline rồi gửi quyết định tới `Consumer<OrderDecision>` để ghi nhận.

Bộ dữ liệu minh họa:

| Input | Kết quả | Nhánh |
| --- | --- | --- |
| `("  dh-101 ", 1_500_000)` | `("DH-101", 1_500_000, "PRIORITY")` | Ưu tiên |
| `("dh-102", 500_000)` | `("DH-102", 500_000, "STANDARD")` | Thường |
| `(" ", 100_000)` | Từ chối bằng `IllegalArgumentException` | Không phát quyết định |
| `("dh-103", 0)` | Từ chối bằng `IllegalArgumentException` | Không phát quyết định |

Các giá trị dùng `long` để minh họa tiền VND dạng số nguyên; hệ thống thật cần lựa chọn mô hình tiền tệ và quy tắc làm tròn phù hợp.

## 5. Các function được tái sử dụng qua FunctionCatalog

Tạo file `src/main/java/example/orders/OrderFunctions.java`:

~~~java
package example.orders;

import java.util.Locale;
import java.util.function.Function;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

record OrderRequest(String id, long totalVnd) {}
record OrderDecision(String id, long totalVnd, String lane) {}

@Configuration
class OrderFunctions {

    @Bean
    Function<OrderRequest, OrderRequest> normalizeOrder() {
        return order -> {
            if (order == null
                    || order.id() == null
                    || order.id().isBlank()
                    || order.totalVnd() <= 0) {
                throw new IllegalArgumentException("Đơn hàng không hợp lệ");
            }

            return new OrderRequest(
                    order.id().strip().toUpperCase(Locale.ROOT),
                    order.totalVnd());
        };
    }

    @Bean
    Function<OrderRequest, OrderDecision> classifyOrder() {
        return order -> new OrderDecision(
                order.id(),
                order.totalVnd(),
                order.totalVnd() >= 1_000_000 ? "PRIORITY" : "STANDARD");
    }
}
~~~

Hai function là phần nghiệp vụ:

- `normalizeOrder` kiểm tra dữ liệu và chuẩn hóa mã đơn, tạo bản ghi mới thay vì sửa giá trị đầu vào.
- `classifyOrder` phân loại bằng tổng tiền, không biết channel, poller, gateway hay broker.
- Cả hai có thể được tra cứu riêng hoặc dưới composition `normalizeOrder|classifyOrder`.

Cách gọi catalog trực tiếp:

~~~java
Function<OrderRequest, OrderDecision> pipeline =
        catalog.lookup("normalizeOrder|classifyOrder");

OrderDecision result =
        pipeline.apply(new OrderRequest(" dh-101 ", 1_500_000));
// OrderDecision[id=DH-101, totalVnd=1500000, lane=PRIORITY]
~~~

Composition yêu cầu đầu ra `OrderRequest` của hàm thứ nhất tương thích với đầu vào của hàm thứ hai. Nếu dùng converter hoặc wrapper để thay đổi kiểu, phải kiểm thử chuyển đổi thực tế.

## 6. Các channel, Supplier và Consumer

Tạo file `src/main/java/example/orders/OrderFlows.java` để đặt cấu hình. Phần đầu của file:

~~~java
package example.orders;

import java.util.Objects;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.function.Consumer;
import java.util.function.Function;
import java.util.function.Supplier;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.cloud.function.context.FunctionCatalog;
import org.springframework.cloud.function.integration.FunctionFlowBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.messaging.MessageChannel;

@Configuration
class OrderFlows {

    @Bean("orders.gatewayInput")
    MessageChannel gatewayInput() {
        return new DirectChannel();
    }

    @Bean("orders.completed")
    MessageChannel completedChannel() {
        return new DirectChannel();
    }

    @Bean("pendingOrders")
    BlockingQueue<OrderRequest> pendingOrders() {
        return new LinkedBlockingQueue<>();
    }

    @Bean("completedOrders")
    BlockingQueue<OrderDecision> completedOrders() {
        return new LinkedBlockingQueue<>();
    }

    @Bean
    Supplier<OrderRequest> pendingOrderSource(
            @Qualifier("pendingOrders")
            BlockingQueue<OrderRequest> pendingOrders) {
        return pendingOrders::poll;
    }

    @Bean
    Consumer<OrderDecision> captureDecision(
            @Qualifier("completedOrders")
            BlockingQueue<OrderDecision> completedOrders) {
        return completedOrders::add;
    }

    // Hai bean IntegrationFlow được thêm trong mục 7 và 8.
}
~~~

Đây là **khung lớp**; thêm hai phương thức `@Bean IntegrationFlow` ở mục 7 và 8 vào **bên trong lớp `OrderFlows`**, trước dấu ngoặc nhọn đóng của lớp. Không tạo thêm một lớp `OrderFlows` khác.

`pendingOrderSource` lấy một item từ hàng đợi mà không chặn: `Queue.poll()` trả `null` khi queue rỗng. `captureDecision` là consumer cuối và ghi vào một hàng đợi khác. Cách này giúp kiểm thử mà không cần dựng broker/DB.

### 6.1. Tại sao hai channel là DirectChannel?

- `orders.gatewayInput` truyền request cho luồng gateway. Vì `DirectChannel` gọi subscriber trên cùng thread (khi không có boundary async), caller dễ nhận kết quả request/reply ngay.
- `orders.completed` nối transformer trong đường polling với consumer cuối. Nó chỉ là ranh giới thông điệp nội bộ; không phải Kafka topic và không lưu dữ liệu bền vững.

Hai queue `pendingOrders`/`completedOrders` trong demo là **Java `BlockingQueue` dùng làm dữ liệu đầu vào/quan sát**, không phải Spring Integration `QueueChannel`. Phân biệt chúng giúp tránh nhầm đặc tính của một collection với message channel của framework.

## 7. Đường Gateway: channel → transformer → reply

### 7.1. Định nghĩa Messaging Gateway

Tạo file `src/main/java/example/orders/OrderGateway.java`:

~~~java
package example.orders;

import org.springframework.integration.annotation.MessagingGateway;

@MessagingGateway(
        defaultRequestChannel = "orders.gatewayInput",
        defaultReplyTimeout = "5000")
public interface OrderGateway {
    OrderDecision classify(OrderRequest request);
}
~~~

`@MessagingGateway` yêu cầu Spring Integration tạo một proxy cho interface. Caller chỉ thấy phương thức Java và kiểu trả về, không cần tự tạo `Message<?>`. Trong ví dụ, `defaultReplyTimeout` là 5.000 mili giây nếu reply chưa về.

Phải bật quét gateway interface. Tạo `src/main/java/example/orders/OrderApplication.java`:

~~~java
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
~~~

Do các file cùng package `example.orders`, component scanning có thể phát hiện các lớp `@Configuration` và interface gateway. Nếu đặt gateway ở package khác, điều chỉnh phạm vi `@IntegrationComponentScan` phù hợp.

### 7.2. Transformer gọi composition từ FunctionCatalog

Thêm phương thức bean này vào lớp `OrderFlows` ở mục 6:

~~~java
@Bean
IntegrationFlow gatewayReplyFlow(FunctionCatalog catalog) {
    Function<OrderRequest, OrderDecision> pipeline =
            Objects.requireNonNull(
                    catalog.lookup("normalizeOrder|classifyOrder"),
                    "Không tìm thấy composition xử lý đơn");

    return IntegrationFlow.from("orders.gatewayInput")
            .transform(OrderRequest.class, pipeline::apply)
            .get();
}
~~~

`catalog.lookup(...)` chạy khi Spring dựng bean flow; lấy function một lần và tái sử dụng cho những message tiếp theo. `Objects.requireNonNull(...)` giúp lỗi sai tên được phát hiện sớm.

`transform(OrderRequest.class, pipeline::apply)` là một **Spring Integration transformer**. Nó nhận **payload `OrderRequest`** từ message và chuyển thành payload `OrderDecision`, trong khi framework quản lý message envelope và chuyển tiếp.

Cách gọi:

~~~java
OrderDecision result = gateway.classify(
        new OrderRequest(" dh-101 ", 1_500_000));

System.out.println(result);
// OrderDecision[id=DH-101, totalVnd=1500000, lane=PRIORITY]
~~~

### 7.3. Gateway nhận reply bằng cách nào?

~~~mermaid
sequenceDiagram
    participant Caller
    participant Gateway
    participant Channel as orders.gatewayInput
    participant Transformer
    participant Catalog as FunctionCatalog
    Caller->>Gateway: classify(OrderRequest)
    Gateway->>Channel: Message<OrderRequest> + replyChannel header
    Channel->>Transformer: dispatch đồng bộ
    Transformer->>Catalog: pipeline.apply(request)
    Catalog-->>Transformer: OrderDecision
    Transformer-->>Gateway: Message<OrderDecision> trên replyChannel
    Gateway-->>Caller: OrderDecision
~~~

Gateway tạo cơ chế **reply channel tạm thời**, gắn chỉ dẫn trả lời vào header `replyChannel`. Ở cuối flow request/reply, transformer có kết quả nên hạ tầng Spring Integration có thể trả message về reply channel ấy.

**Điều kiện quan trọng:** không đưa một `Consumer` chỉ có tác động phụ và không có reply làm điểm cuối nếu gateway cần `OrderDecision`. Nếu một flow kết thúc bằng `handle(...)` trả `null` hoặc `accept(...)`, caller có thể không nhận được kết quả và phải chờ đến timeout.

`Gateway` trong bài là **Messaging Gateway của Spring Integration**. Nó khác với **Spring Cloud Gateway** (định tuyến HTTP) và cũng khác một HTTP controller. Muốn cung cấp REST API, hãy thêm HTTP adapter/controller gọi gateway hoặc cùng function; không phải chỉ thêm `@MessagingGateway` là có HTTP endpoint.

## 8. Đường Poller: Supplier → function → channel → Consumer

Thêm phương thức thứ hai vào lớp `OrderFlows`:

~~~java
@Bean
IntegrationFlow pollingOrderFlow(FunctionFlowBuilder builder) {
    return builder
            .fromSupplier(
                    "pendingOrderSource",
                    endpoint -> endpoint.poller(
                            Pollers.fixedDelay(250)
                                    .maxMessagesPerPoll(1)))
            .apply("normalizeOrder|classifyOrder")
            .channel("orders.completed")
            .accept("captureDecision");
}
~~~

Ở đây:

1. `fromSupplier("pendingOrderSource", ...)` dùng `FunctionCatalog` tìm bean `Supplier<OrderRequest>` và đưa nó vào một nguồn polling của Spring Integration.
2. `Pollers.fixedDelay(250)` định nhịp kích hoạt source theo fixed delay 250 ms.
3. `maxMessagesPerPoll(1)` giới hạn tối đa một message lấy từ source trong mỗi lần kích hoạt.
4. `apply("normalizeOrder|classifyOrder")` biến `OrderRequest` thành `OrderDecision` theo tên composition trong catalog.
5. `channel("orders.completed")` phát message tới `DirectChannel` nội bộ đã định nghĩa.
6. `accept("captureDecision")` kết thúc flow bằng `Consumer<OrderDecision>`, ghi vào `completedOrders`.

Cách chạy thử (ví dụ trong bean/test có hai queue):

~~~java
pendingOrders.add(new OrderRequest(" dh-102 ", 500_000));

// Sau khi poller kích hoạt, completedOrders sẽ có:
// OrderDecision[id=DH-102, totalVnd=500000, lane=STANDARD]
~~~

**Chú ý thời gian:** `add(...)` chỉ đưa item vào queue; nó không lập tức gọi function. Poller sẽ lấy item ở một lần kích hoạt kế tiếp, sau đó qua các endpoint.

### 8.1. Tại sao không cần gateway ở đường polling?

Không có caller cụ thể đợi một `OrderDecision`. Nguồn tự phát thông điệp và consumer là điểm cuối. Nếu muốn cung cấp kết quả cho người dùng, hệ thống có thể ghi DB, publish event hoặc cho một API tra cứu trạng thái. Đây là mô hình **asynchronous process** theo thời điểm phát dữ liệu, dù các bước xử lý bên trong một lượt poll có thể vẫn đồng bộ trên thread của poller.

### 8.2. Từ apply sang transformer

Hai đoạn dưới đây tương đồng về mục đích, nhưng cách tra cứu khác nhau:

~~~java
// FunctionFlowBuilder (tra cứu composition theo tên)
.apply("normalizeOrder|classifyOrder")
~~~

~~~java
// IntegrationFlow DSL thông thường (tra cứu tường minh trước)
Function<OrderRequest, OrderDecision> f =
        catalog.lookup("normalizeOrder|classifyOrder");

// Trong pipeline:
.transform(OrderRequest.class, f::apply)
~~~

`apply` của FunctionFlowBuilder là cú pháp tiện ích tích hợp với catalog, trong khi `transform` là EIP Transformer phổ biến của Spring Integration. `apply` vẫn mang ý nghĩa biến đổi bằng một function; cả hai cần có kiểu đầu vào/đầu ra đúng hợp đồng.

## 9. Poller: nhịp chạy, giới hạn lấy và điều kiện dừng

### 9.1. Fixed delay và maxMessagesPerPoll

| Cấu hình | Ý nghĩa |
| --- | --- |
| `Pollers.fixedDelay(250)` | Poll theo khoảng trễ cố định giữa các lần kích hoạt; thời điểm thực tế chịu ảnh hưởng của scheduler và thời gian xử lý. |
| `Pollers.fixedRate(250)` | Lên lịch theo nhịp fixed rate; không tự bảo đảm xử lý xong đúng 250 ms hay có thể chạy song song. |
| `maxMessagesPerPoll(1)` | Tối đa một message được lấy từ source trong mỗi lần trigger. |
| `maxMessagesPerPoll(5)` | Có thể lấy tối đa năm message trong một lần trigger nếu source có đủ dữ liệu và các bước cho phép. |

Trong Spring Integration, `SourcePollingChannelAdapter` thường có mặc định `maxMessagesPerPoll = 1`; còn `PollingConsumer` có mặc định khác vì nó đọc từ pollable channel. Đặt giá trị tường minh giúp chính sách chạy dễ kiểm soát và không phụ thuộc giả định ngầm.

### 9.2. Supplier trả null

Với `pendingOrders::poll`, queue rỗng sẽ trả `null`. Trong một polling message source, kết quả này thường nghĩa là **không có message mới** trong lượt poll. Nó không có nghĩa framework gửi một `Message` có payload bằng `null`, vì Spring Messaging không chấp nhận null payload như một dữ liệu thông thường.

Poller vẫn có thể được kích hoạt lại vào kỳ sau và thử tiếp.

### 9.3. Nguồn bị lấy rồi nhưng xử lý lỗi

~~~text
pendingOrders.poll()
     ↓ lấy item ra khỏi queue
normalizeOrder / classifyOrder
     ↓
captureDecision
     ↓
nếu lỗi: item KHÔNG tự quay lại pendingOrders
~~~

Điều này rất quan trọng: demo dùng queue trong RAM nên **không có transactional acknowledgement hoặc giao nhận bền vững**. Khi downstream thất bại, cần cơ chế khôi phục thích hợp, ví dụ:

- Lưu trạng thái pending/processing trong database với transaction.
- Dùng broker và adapter có ack, redelivery hoặc dead-letter.
- Có error store/idempotency key cho trường hợp fail hoặc xử lý trùng.
- Thiết kế retry có giới hạn cho lỗi tạm thời; dữ liệu nghiệp vụ sai thường không thể sửa bằng việc retry vô hạn.

Poller không tự biến `Supplier` thành hệ thống exactly-once.

## 10. Channel: DirectChannel, QueueChannel và ExecutorChannel

Bài dùng `DirectChannel` cho cả hai channel trong demo để minh họa dễ hiểu. Trong hệ thống thực tế, lựa chọn channel thay đổi đặc tính xử lý.

| Loại channel | Đặc tính | Tác động khi nối function |
| --- | --- | --- |
| `DirectChannel` | Dispatch trực tiếp đến subscriber, thông thường cùng thread. | Lỗi downstream có thể lan ngược về caller/poller; phù hợp request/reply đồng bộ. |
| `QueueChannel` | Giữ message trong hàng đợi của channel, consumer khác cần chủ động poll. | Tạo buffering và ranh giới thời gian; thường cần poller cho endpoint đọc nó. |
| `ExecutorChannel` | Giao message đến executor để xử lý bất đồng bộ. | Caller có thể không chờ nghiệp vụ hoàn tất; cần quản lý executor, lỗi, ordering và timeout. |
| `PublishSubscribeChannel` | Phát message tới nhiều subscriber theo chính sách. | Phù hợp fan-out, nhưng không tự bảo đảm mọi nhánh cùng thành công hoặc trả một reply duy nhất. |

### 10.1. Chuyển sang QueueChannel cần thay đổi gì?

Chỉ đổi:

~~~java
@Bean("orders.completed")
MessageChannel completedChannel() {
    return new QueueChannel(100);
}
~~~

chưa đủ trong mọi cấu hình: `QueueChannel` là **PollableChannel**; endpoint downstream đọc từ nó thường cần **poller** để lấy dữ liệu. Có thể cần cấu hình default poller hoặc poller trên endpoint nhận, tùy DSL đang sử dụng. Thay đổi channel có thể làm khác ranh giới transaction và thời điểm xử lý lỗi.

Ví dụ này minh họa một thay đổi về kiến trúc, không phải phần thay thế trực tiếp chạy được nếu chưa bổ sung poller. Thêm import `org.springframework.integration.channel.QueueChannel` khi sử dụng.

### 10.2. Vì sao không đổi gatewayInput sang ExecutorChannel tùy tiện?

Gateway đang mong nhận reply trong khoảng thời gian nhất định. Nếu đổi sang `ExecutorChannel`, việc dispatch sang thread khác có thể hợp lệ, nhưng cần quản lý thời gian chờ, propagation exception, context, cancellation và tương quan reply. Với demo request/reply đơn giản, `DirectChannel` là lựa chọn rõ ràng.

### 10.3. Bảng chọn channel theo nhu cầu

- **Đồng bộ, xử lý nhanh, cần kết quả tức thì:** bắt đầu với `DirectChannel`.
- **Cần đệm lượng message tăng đột biến:** xem xét `QueueChannel` kèm poller, giới hạn capacity và chính sách backpressure.
- **Cần chuyển tải sang executor:** dùng `ExecutorChannel` khi đã thiết kế rõ concurrency, ordering và error handling.
- **Cần gửi cho nhiều nhánh:** dùng `PublishSubscribeChannel` hoặc EIP Recipient List/Router theo contract.

## 11. Transformer khác router, filter và gateway ra sao?

Đây đều là những endpoint có thể xuất hiện trong cùng `IntegrationFlow`, nhưng trách nhiệm khác nhau.

~~~text
Gateway method
    ↓ request message
Message Channel
    ↓
Transformer: OrderRequest → OrderDecision
    ↓
Filter: giữ hoặc bỏ
    ↓
Router: chuyển theo lane
    ↓
Handler/Consumer: thực hiện side effect
~~~

- **Transformer** tính một giá trị đầu ra mới. Trong demo, `normalizeOrder|classifyOrder` trả `OrderDecision`.
- **Filter** giữ hoặc loại message dựa trên điều kiện. Ném `IllegalArgumentException` khi validation thất bại không tự tương đương EIP Filter.
- **Router** dùng giá trị như `lane` để chọn channel đích, ví dụ `orders.priority` hoặc `orders.standard`.
- **Gateway** chuyển lời gọi phương thức thành trao đổi message và có thể trả kết quả về caller.

Một biến thể định tuyến bằng EIP:

~~~java
// Minh họa thay thế flow gateway hoặc poller hiện có;
// cần định nghĩa channel và handler cho cả hai nhánh.
return IntegrationFlow.from("orders.routeInput")
        .transform(OrderRequest.class, pipeline::apply)
        .route(OrderDecision.class, OrderDecision::lane,
                spec -> spec
                        .channelMapping("PRIORITY", "orders.priority")
                        .channelMapping("STANDARD", "orders.standard"))
        .get();
~~~

Đoạn này chỉ giải thích *Router*, không tự tạo `orders.routeInput` hay các kênh đích. Không đặt nó cùng nguồn với gateway đang chờ reply nếu chưa xác định nhánh nào trả response.

## 12. Message header, replyChannel và chuyển đổi kiểu

### 12.1. Message có cả payload và header

~~~text
Message<OrderRequest>
  payload: OrderRequest("DH-101", 1500000)
  headers:
    id: ...
    timestamp: ...
    replyChannel: ...   (nếu được gateway thiết lập)
    traceId: ...        (nếu ứng dụng cung cấp)
~~~

Function `Function<OrderRequest,OrderDecision>` chỉ cần payload, nên dễ tái sử dụng. Spring Integration lo đóng gói/truyền message. Gateway dùng header `replyChannel` để biết nơi gửi kết quả.

Nếu function thật sự cần metadata, khai báo:

~~~java
@Bean
Function<Message<OrderRequest>, Message<OrderRequest>> tagOrder() {
    return incoming -> MessageBuilder.fromMessage(incoming)
            .setHeader("processingStage", "NORMALIZED")
            .build();
}
~~~

Cần import `org.springframework.messaging.Message` và `org.springframework.messaging.support.MessageBuilder`. Khi chuyển qua wrapper/call site, dùng overload phù hợp để chuyển **toàn bộ message**, và kiểm thử header quan trọng thay vì giả định mọi API xử lý giống nhau.

### 12.2. Chuyển đổi payload từ HTTP hoặc broker

Gateway demo nhận đối tượng `OrderRequest` nên không cần parse JSON. Nếu nguồn là HTTP hay broker, payload có thể là JSON string hoặc byte array. Khi đó:

~~~text
JSON bytes
   → converter/deserializer
   → OrderRequest
   → normalizeOrder|classifyOrder
   → OrderDecision
   → serializer/adapter hoặc gateway reply
~~~

`FunctionCatalog` có hỗ trợ wrapper/conversion, nhưng **không có nghĩa mọi byte array tự biến thành bất kỳ POJO nào**. Content type, generic signature, converter và cấu hình adapter phải tương thích. Test unit dùng POJO chưa chứng minh cấu hình binding HTTP/broker đúng.

### 12.3. Header có thể thay đổi qua ranh giới

Truyền qua transformer thường bảo toàn các header thích hợp trong Spring Integration, nhưng header liên quan acknowledgement, partition, message ID hoặc correlation có thể bị adapter/wrapper xử lý riêng. Với request/reply cần chú ý `replyChannel`; với trace cần kiểm thử propagation qua từng bước.

## 13. Gateway không đồng nghĩa HTTP API

Có ba cách nhìn:

| Cách gọi | Interface đối với caller | Thành phần kết nối | Có thể dùng chung function? |
| --- | --- | --- | --- |
| **Messaging Gateway** | `OrderDecision classify(OrderRequest)` | Spring Integration proxy + request channel + reply channel. | Có |
| **HTTP REST** | `POST /orders/classify` | Spring MVC/WebFlux controller hoặc SCF Web adapter. | Có |
| **Event / message broker** | Message đến từ destination/topic/queue. | Spring Cloud Stream binder hoặc Spring Integration inbound adapter. | Có |
| **Serverless** | Hàm được nền tảng gọi bằng event. | Adapter thích hợp với runtime. | Có |

Để phơi bày gateway demo qua HTTP, có thể thêm một controller:

~~~java
@RestController
@RequestMapping("/orders")
class OrderController {

    private final OrderGateway gateway;

    OrderController(OrderGateway gateway) {
        this.gateway = gateway;
    }

    @PostMapping("/classify")
    OrderDecision classify(@RequestBody OrderRequest request) {
        return gateway.classify(request);
    }
}
~~~

Đây là ví dụ **tùy chọn**; cần thêm `spring-boot-starter-web`, import Spring MVC và thiết kế mapping exception sang HTTP status, timeout, validation, authentication phù hợp. Controller không làm thay đổi hai hàm `normalizeOrder`/`classifyOrder`.

Cũng có thể không đi qua gateway, mà cho HTTP adapter gọi function trong catalog trực tiếp. Tùy nhu cầu vận hành, một lớp gateway hữu ích khi muốn ứng dụng gọi một flow có nhiều EIP như request/reply, channel, transform và routing.

## 14. Kiểm thử theo từng ranh giới

### 14.1. Unit test function

Gọi function trực tiếp, không cần Spring:

~~~java
OrderFunctions functions = new OrderFunctions();

OrderRequest normalized = functions.normalizeOrder()
        .apply(new OrderRequest(" dh-101 ", 1_500_000));

OrderDecision decision = functions.classifyOrder()
        .apply(normalized);

assertEquals("DH-101", decision.id());
assertEquals("PRIORITY", decision.lane());
~~~

Kiểm thêm tổng tiền bằng `1_000_000` (vẫn `PRIORITY`), nhỏ hơn ngưỡng (thành `STANDARD`), mã rỗng hoặc tổng tiền không hợp lệ (bị từ chối).

### 14.2. Kiểm thử catalog và composition

Trong Spring test context:

~~~java
@Autowired
FunctionCatalog catalog;

@Test
void compositionShouldBeRegistered() {
    Function<OrderRequest, OrderDecision> pipeline =
            catalog.lookup("normalizeOrder|classifyOrder");

    assertNotNull(pipeline);
    OrderDecision result = pipeline.apply(
            new OrderRequest(" dh-102 ", 500_000));
    assertEquals("STANDARD", result.lane());
}
~~~

Mục này xác nhận **tên function**, loại chữ ký và composition; chưa xác nhận channel/poller/gateway.

### 14.3. Integration test cho Gateway

~~~java
package example.orders;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(classes = OrderApplication.class)
class OrderGatewayTest {

    @Autowired
    OrderGateway gateway;

    @Test
    void gatewayShouldReturnClassifiedOrder() {
        OrderDecision decision = gateway.classify(
                new OrderRequest(" dh-101 ", 1_500_000));

        assertEquals("DH-101", decision.id());
        assertEquals("PRIORITY", decision.lane());
    }
}
~~~

Với `DirectChannel` và transformer đồng bộ, kết quả được trả về từ gateway ngay trong lời gọi phương thức. Nếu flow không tạo reply, test cần có timeout hữu hạn để phát hiện tình huống gateway chờ đến timeout.

### 14.4. Integration test cho polling

~~~java
package example.orders;

import java.util.concurrent.BlockingQueue;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(classes = OrderApplication.class)
class OrderPollingTest {

    @Autowired
    @Qualifier("pendingOrders")
    BlockingQueue<OrderRequest> pendingOrders;

    @Autowired
    @Qualifier("completedOrders")
    BlockingQueue<OrderDecision> completedOrders;

    @Test
    void pollerShouldProcessPendingOrder() throws InterruptedException {
        pendingOrders.clear();
        completedOrders.clear();

        pendingOrders.add(new OrderRequest(" dh-102 ", 500_000));

        OrderDecision result = completedOrders.poll(
                3, TimeUnit.SECONDS);

        assertNotNull(result, "Poller chưa phát kết quả trước timeout");
        assertEquals("DH-102", result.id());
        assertEquals("STANDARD", result.lane());
    }
}
~~~

**Tại sao cần `poll(timeout)`?** Vì poller kích hoạt theo lịch, không đồng bộ với lời gọi `pendingOrders.add(...)` của test. Nếu dùng `completedOrders.poll()` không có timeout ngay sau `add(...)`, kết quả có thể chưa có dù flow đúng.

Các queue trong demo là shared beans; khi chạy nhiều test cùng context song song, cần cách ly trạng thái, tránh dữ liệu test này đi vào test khác. Khi thay queue bằng DB/broker cần test idempotency, retry, redelivery và khả năng khôi phục theo cơ chế thực tế.

## 15. Xử lý lỗi và những quyết định vận hành

| Tình huống | Đường Gateway | Đường Poller |
| --- | --- | --- |
| Mã đơn rỗng / tổng tiền không hợp lệ | Transformer ném lỗi; với flow đồng bộ không có error channel riêng, lỗi thường truyền ngược caller. | Poller/handler xử lý exception theo error handler; cần quyết định bỏ, lưu lỗi hay retry. |
| Không tìm thấy `normalizeOrder|classifyOrder` | Có thể lỗi khi dựng `IntegrationFlow` vì lookup tường minh. | DSL lookup tên function khi dựng/khởi tạo flow; cần kiểm tra bean trong catalog. |
| Function xử lý chậm | Caller chờ, có nguy cơ timeout. | Lượt polling bị chậm hoặc backlog tăng. |
| Consumer ghi DB thất bại | Nếu endpoint nằm trong request/reply, cần quyết định có gửi reply trước/sau commit. | Item đã lấy khỏi source có nguy cơ mất; cần ack/recovery và idempotency. |
| Message trùng lặp | Lệnh caller gọi lại có thể tạo side effect lặp. | Retry/redelivery hoặc nguồn trả cùng item có thể làm xử lý lặp. |
| Adapter broker bị ngắt kết nối | Không áp dụng cho channel nội bộ nếu chưa kết nối broker. | Cần binder/inbound adapter xử lý delivery/ack/reconnection. |

### 15.1. ErrorChannel và retry ở đâu?

Spring Integration có error channel, retry advice, transaction support và khả năng cấu hình error handling cho poller/adapter. Cơ chế nào được kích hoạt còn phụ thuộc endpoint **đồng bộ hay bất đồng bộ**:

- Với `DirectChannel`, exception từ transformer có thể lan ngược tới sender.
- Với polling endpoint, exception có thể đi qua error handler của scheduler/poller.
- Với executor hoặc broker, lỗi có thể xuất hiện ở thread khác, cần error channel hoặc chính sách riêng của adapter.
- Chỉ thêm một bean tên `errorChannel` không đồng nghĩa mọi lỗi đi đến đó theo cùng cơ chế.

Thực tế cần phân loại **lỗi dữ liệu nghiệp vụ** và **lỗi hạ tầng tạm thời**. Dữ liệu sai thường nên báo lỗi hoặc đưa sang nhánh xử lý có chủ đích; lỗi mạng có thể retry/backoff có giới hạn.

### 15.2. Tính nhất quán và idempotency

`FunctionCatalog` chỉ giúp đóng gói và tra cứu logic; `IntegrationFlow` không tự đem lại transaction phân tán. Đặc biệt ở đường polling, thao tác `pendingOrders.poll()` đã lấy item khỏi queue trước khi consumer hoàn tất. Muốn đảm bảo không mất dữ liệu khi process crash, dùng nguồn bền vững và chiến lược ack/transaction/compensation tương ứng.

Nếu consumer tạo side effect như gửi email hoặc ghi dữ liệu, nên dùng business key để chống xử lý trùng, nhất là khi có retry/redelivery.

## 16. Một số lỗi thường gặp

| Triệu chứng | Nguyên nhân cần xem xét |
| --- | --- |
| `NoSuchBeanDefinitionException` đối với `OrderGateway` | Thiếu `@IntegrationComponentScan`, gateway nằm ngoài package quét, hoặc Spring Integration chưa cấu hình. |
| `FunctionFlowBuilder` không inject được | Thiếu `spring-cloud-function-integration` hoặc phiên bản/auto-configuration không tương thích. |
| `FunctionCatalog.lookup(...)` không có function | Sai tên bean, không quét được cấu hình, composition hoặc type không hợp lệ. |
| Gateway gọi nhưng không có reply | Flow kết thúc bằng consumer không trả kết quả, reply channel bị mất hoặc kết quả không đến trước timeout. |
| Gateway timeout sau khi đổi channel | Có boundary async, endpoint downstream không phản hồi hoặc bị nghẽn. |
| Poller không thấy item | Supplier trả `null`, queue khác với queue mà test ghi vào, endpoint chưa start hoặc poller sai lịch. |
| Poller luôn xử lý cùng giá trị | Supplier luôn trả cùng một giá trị/hàm nguồn không cập nhật cursor; cần xem lại hợp đồng source. |
| `ClassCastException` khi transform | Payload không đúng `OrderRequest` hoặc converter/input binding không tương thích. |
| `QueueChannel` có dữ liệu nhưng downstream không chạy | Chưa cấu hình poller cho consumer nhận từ pollable channel. |
| Kết quả bị ghi hai lần | Nguồn event lặp, retry/redelivery hoặc nhiều flow/binding cùng xử lý. |
| Mất dữ liệu khi consumer lỗi | Queue nguồn đã xóa item nhưng không có cơ chế ack/recovery. |

### Câu hỏi tự đánh giá

1. Vì sao `Gateway.classify(...)` có thể trả dữ liệu đồng bộ, còn `fromSupplier(...)` thường không có caller đang đợi?
2. Mối liên hệ giữa `transform(OrderRequest.class, pipeline::apply)` và `apply("normalizeOrder|classifyOrder")` là gì?
3. Tại sao `DirectChannel` có thể phù hợp gateway hơn `QueueChannel` trong một ví dụ request/reply đơn giản?
4. Vì sao đổi `DirectChannel` thành `QueueChannel` thường phải bổ sung poller ở endpoint nhận?
5. Làm sao kiểm chứng một message đã được xử lý xong thay vì chỉ được chấp nhận bởi channel?
6. Nếu `pendingOrders.poll()` lấy item rồi consumer lỗi, nên thay đổi kiến trúc nào để có khả năng khôi phục?
7. Vì sao thêm `@MessagingGateway` chưa tạo một HTTP endpoint?
8. Khi thêm broker adapter, cần kiểm thử thêm những gì về serialization, acknowledgement và idempotency?

## 17. Bài tập mở rộng

1. **Thêm Message Filter:** Tạo điều kiện bỏ đơn có mã bắt đầu `TEST-` sau chuẩn hóa. So sánh việc filter loại message với việc function ném exception.
2. **Thêm Content-Based Router:** Dùng `lane` để đưa kết quả tới `orders.priority` hoặc `orders.standard`, mỗi nhánh có consumer riêng.
3. **Đổi sang QueueChannel:** Chuyển `orders.completed` sang `QueueChannel(100)`, cấu hình polling consumer và chứng minh message vẫn đến consumer.
4. **Bổ sung gateway header:** Thêm tham số `@Header("traceId")` vào phương thức gateway, dùng wire tap kiểm tra header trên message sau transformer.
5. **Giả lập lỗi:** Để consumer thỉnh thoảng ném exception, thử các chiến lược retry/backoff có giới hạn và ghi nhận item cần redrive.
6. **Expose qua HTTP:** Viết `@RestController` gọi `OrderGateway` hoặc gọi function trực tiếp, mô tả rõ phản hồi thành công, validation error và timeout.

## 18. Tài liệu tham khảo chính thức

- [Spring Cloud Function – Spring Integration Interaction](https://docs.spring.io/spring-cloud-function/reference/spring-integration.html): `spring-cloud-function-integration`, `FunctionFlowBuilder`, `fromSupplier`, `apply` và `accept`.
- [Spring Cloud Function – Programming Model](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html): `Supplier`, `Function`, `Consumer`, `FunctionCatalog` và composition.
- [Spring Integration – DSL Basics](https://docs.spring.io/spring-integration/reference/dsl/java-basics.html): các endpoint `transform`, `filter`, `handle`, `route` và luồng message.
- [Spring Integration – Messaging Gateways](https://docs.spring.io/spring-integration/reference/gateway.html): proxy của gateway, request/reply, temporary reply channel, annotation và timeout.
- [Spring Integration – Message Channels](https://docs.spring.io/spring-integration/reference/channel.html): các loại channel và đặc tính đồng bộ/bất đồng bộ.
- [Spring Integration – Channel Adapter](https://docs.spring.io/spring-integration/reference/channel-adapter.html): polling inbound adapter, `maxMessagesPerPoll` và đặc tính vận hành.
- [Spring Integration – Message Endpoints](https://docs.spring.io/spring-integration/reference/endpoint.html): cách cấu hình poller, default poller và transaction.

**Kết luận:** `FunctionCatalog` cung cấp các phép biến đổi nghiệp vụ có thể dùng lại; Spring Integration đặt chúng vào những đường đi thông điệp thông qua **channel**, **poller**, **transformer** và **gateway**. Với cùng composition `normalizeOrder|classifyOrder`, một gateway cung cấp request/reply cho caller, còn một supplier được poll định kỳ để đẩy kết quả tới consumer. Thiết kế ranh giới rõ ràng giúp cùng hàm có thể phục vụ HTTP, sự kiện hoặc serverless, đồng thời để việc chuyển phát, lập lịch và xử lý lỗi thuộc đúng lớp tích hợp.
