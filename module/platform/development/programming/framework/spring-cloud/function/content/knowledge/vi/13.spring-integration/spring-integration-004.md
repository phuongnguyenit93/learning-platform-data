# FunctionFlowBuilder và fromSupplier

## 1. Vì sao cần FunctionFlowBuilder?

Trong mô hình **Spring Cloud Function (SCF)**, logic nghiệp vụ được đóng gói thành ba loại hàm Java:

- `Supplier<T>`: cung cấp một giá trị mà không cần đối số đầu vào.
- `Function<T, R>`: biến đổi dữ liệu từ `T` thành `R`.
- `Consumer<T>`: tiếp nhận `T` và thực hiện thao tác cuối, không trả về kết quả nghiệp vụ.

Các hàm được đăng ký và tra cứu bằng `FunctionCatalog`. Nhờ vậy, cùng một hàm có thể được tái sử dụng qua HTTP, sự kiện từ message broker hoặc môi trường serverless, với điều kiện adapter tương ứng được cấu hình. SCF còn hỗ trợ *composition*: ghép các hàm theo tên, ví dụ `normalize|classify`.

**Spring Integration** giải quyết một nhu cầu khác: kết nối các nguồn và đích thông điệp qua channel, transformer, filter, router, splitter, aggregator, polling adapter và error flow. Những thành phần đó thể hiện các **Enterprise Integration Patterns (EIP)** trong một `IntegrationFlow`.

Từ Spring Cloud Function **4.0.3**, module `spring-cloud-function-integration` bổ sung **`FunctionFlowBuilder`**: một điểm bắt đầu cho Java DSL của Spring Integration đã được nối với `FunctionCatalog`. Thay vì viết mã tra cứu từng hàm rồi tự kết nối vào endpoint, flow có thể tham chiếu hàm **bằng tên**.

Đặc biệt, `fromSupplier(...)` cho phép một `Supplier` trong catalog trở thành **nguồn phát** của `IntegrationFlow`.

~~~mermaid
flowchart LR
    A["FunctionCatalog"] -. "lookup theo tên" .-> B["FunctionFlowBuilder"]
    S["Supplier&lt;T&gt;"] --> A
    F["Function&lt;T,R&gt;"] --> A
    C["Consumer&lt;R&gt;"] --> A
    P["Poller"] --> E["SourcePollingChannelAdapter"]
    B --> E
    E --> I["Message trong IntegrationFlow"]
    I --> X["apply(...): Function"]
    X --> Y["EIP: filter / router / wireTap"]
    Y --> Z["accept(...): Consumer"]
~~~

Bài này tập trung vào **`FunctionFlowBuilder` và `fromSupplier`**: cách cấu hình, nhịp polling, dòng dữ liệu, composition, kiểm thử và những tình huống dễ sai. Đây là một bài của chương **Spring Integration** trong phạm vi Spring Cloud Function; không đòi hỏi người học đã có broker hoặc serverless runtime.

### Sau bài học, bạn có thể

1. Giải thích sự khác nhau giữa `fromSupplier("name")` và `from("channel")`.
2. Phân biệt `FunctionFlowBuilder` với `FunctionFlowDefinition` và vai trò của `FunctionCatalog`.
3. Tạo một flow có nguồn `Supplier`, các bước `Function`, EIP Filter và `Consumer`.
4. Cấu hình `Pollers.fixedDelay(...)`, hiểu `maxMessagesPerPoll` và ý nghĩa của kết quả `null` từ nguồn.
5. Kiểm thử flow bất đồng bộ theo nhịp poller, xác định điểm mất dữ liệu và chiến lược xử lý lỗi.

## 2. Các lớp trách nhiệm

Để hiểu `fromSupplier`, trước tiên cần tách **một hàm tạo dữ liệu** khỏi **cơ chế quyết định thời điểm gọi hàm đó**.

~~~text
Nguồn dữ liệu hoặc hàng đợi nội bộ
            │
            ▼
Supplier<T> đã đăng ký trong FunctionCatalog
            ▲
            │ get() được gọi theo lịch
            │
SourcePollingChannelAdapter + Poller
            │
            ▼
    Spring Integration Message
            │
            ▼
     apply("transformName")
            │
            ▼
  filter / route / channel / ...
            │
            ▼
     accept("consumerName")
~~~

| Thành phần | Trách nhiệm | Điều không nên suy diễn |
| --- | --- | --- |
| `Supplier<T>` | Trả về phần tử tiếp theo, ví dụ một đơn hàng cần xử lý. | Không tự định nghĩa lịch chạy, retry, transaction hoặc ack. |
| `FunctionCatalog` | Quản lý function, supplier, consumer; hỗ trợ tra cứu và composition theo tên. | Không phải message broker hay message store. |
| `FunctionFlowBuilder` | Tạo flow theo DSL có tham chiếu hàm trong catalog, bao gồm `fromSupplier`. | Không tự kích hoạt các adapter HTTP/Kafka/serverless. |
| `FunctionFlowDefinition` | Phần DSL tiếp tục sau khi khai báo nguồn; bổ sung `apply` và `accept` bên cạnh operator Integration DSL. | Không thay thế filter, router, aggregator của Spring Integration. |
| `SourcePollingChannelAdapter` và `Poller` | Định kỳ gọi nguồn, phát message vào pipeline theo cấu hình. | Không mặc nhiên đảm bảo exactly-once hoặc phục hồi dữ liệu nguồn. |
| `Consumer<T>` | Điểm xử lý cuối, có thể lưu dữ liệu hoặc gửi đi. | Không trả về payload để tiếp tục chuỗi như `Function<T,R>`. |

**Điểm khác biệt quan trọng:** một `Supplier` trong SCF chỉ mô tả *cách tạo hoặc lấy dữ liệu*. Khi đặt nó vào `fromSupplier(...)`, **Spring Integration** cung cấp phần lifecycle của một polling message source.

## 3. Dependency và phạm vi phiên bản

### 3.1. Maven

Trong ứng dụng Spring Boot có quản lý phiên bản qua Spring Cloud BOM tương thích:

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

Phần trên giả định dự án đã có cấu hình Spring Boot parent/BOM và Spring Cloud dependency management. Không khai báo ngẫu nhiên version `spring-cloud-function-integration` tách biệt với release train của SCF. Nếu starter/adapter hiện có đã kéo Spring Integration vào classpath, kiểm tra dependency thực tế trước khi thêm thành phần trùng lặp.

### 3.2. Gradle

~~~groovy
dependencies {
    implementation 'org.springframework.cloud:spring-cloud-function-integration'
    implementation 'org.springframework.boot:spring-boot-starter-integration'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Tương tự Maven, đoạn này yêu cầu version management phù hợp của Spring Boot và Spring Cloud.

### 3.3. Các import quan trọng

~~~java
import java.util.function.Supplier;
import java.util.function.Function;
import java.util.function.Consumer;

import org.springframework.cloud.function.integration.FunctionFlowBuilder;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
~~~

`FunctionFlowBuilder` đến từ module **`spring-cloud-function-integration`**. Nếu ứng dụng chỉ có `spring-cloud-function-context` và Spring Integration cơ bản thì có thể tra cứu `FunctionCatalog` thủ công, nhưng chưa chắc có builder chuyên biệt này.

## 4. FunctionFlowBuilder và FunctionFlowDefinition hoạt động ra sao?

### 4.1. DSL theo tên hàm

Ví dụ tối giản về cấu trúc:

~~~java
@Bean
IntegrationFlow exampleFlow(FunctionFlowBuilder builder) {
    return builder
            .fromSupplier("eventSource",
                    e -> e.poller(Pollers.fixedDelay(1000)))
            .apply("normalizeEvent")
            .accept("saveEvent");
}
~~~

Giả định trong `FunctionCatalog` có các hàm:

~~~text
eventSource   : Supplier<Event>
normalizeEvent: Function<Event, NormalizedEvent>
saveEvent     : Consumer<NormalizedEvent>
~~~

Đoạn DSL mang ý nghĩa:

1. `fromSupplier("eventSource", ...)`: tra cứu supplier theo tên trong catalog và dùng nó làm nguồn polling.
2. `apply("normalizeEvent")`: gọi function với dữ liệu được phát ra từ source.
3. `accept("saveEvent")`: chuyển kết quả sang consumer ở điểm cuối.

Đây là minh họa API; muốn chạy cần khai báo các bean tương ứng. Tên function là **tên định nghĩa mà catalog tra cứu được**, không phải tên topic, queue hay message channel.

### 4.2. Đường đi của đối tượng builder

Theo mô hình DSL:

~~~text
FunctionFlowBuilder
   └─ fromSupplier("eventSource", endpointConfigurer)
        └─ FunctionFlowDefinition
             ├─ apply("normalizeEvent")
             ├─ operator của Spring Integration: filter, route, wireTap...
             └─ accept("saveEvent")  → IntegrationFlow
~~~

`FunctionFlowDefinition` mở rộng khả năng của `IntegrationFlowDefinition`/`IntegrationFlowExtension` để dùng tên hàm. Vì vậy có thể xen những operator của Spring Integration giữa các bước gọi function.

### 4.3. Các API thường dùng

| API | Vai trò | Ví dụ |
| --- | --- | --- |
| `fromSupplier("supplierName")` | Bắt đầu flow bằng supplier trong catalog, sử dụng default poller đã cấu hình. | `.fromSupplier("pendingOrders")` |
| `fromSupplier("supplierName", e -> e.poller(...))` | Bắt đầu từ supplier và khai báo endpoint/poller ngay tại chỗ. | `.fromSupplier("pendingOrders", e -> e.poller(Pollers.fixedDelay(500)))` |
| `from("inputChannel")` | Bắt đầu flow từ một channel có message được gửi đến từ bên ngoài hoặc flow khác. | `.from("orders.in")` |
| `apply("functionName")` | Biến đổi payload/message bằng function lấy từ catalog. | `.apply("normalizeOrder")` |
| `apply("f1|f2")` | Ghép các function tương thích trong catalog. | `.apply("validate|classify")` |
| `accept("consumerName")` | Gọi consumer kết thúc flow. | `.accept("storeOrder")` |
| `accept("f1|consumer")` | Ghép function với consumer ở cuối theo khả năng composition của catalog. | `.accept("normalize|archive")` |

**Lưu ý về `fromSupplier("name")` không có endpoint configurer:** phiên bản Spring Integration hỗ trợ factory này với **default poller của application context**, và default poller phải được cấu hình nếu dùng cách đó. Khi viết bài thực hành hoặc service có yêu cầu rõ ràng về nhịp lấy dữ liệu, nên dùng biến thể có `e -> e.poller(...)` để source có lịch thực thi tường minh.

**Không nhầm `from("channel")` với `fromSupplier("supplier")`:** tên channel là đích tiếp nhận *message được đẩy vào*, còn tên supplier là function *được poller chủ động gọi*. Cùng một giá trị String trong hai method không có cùng ý nghĩa.

## 5. Thực hành: polling phiếu hỗ trợ từ hàng đợi

### 5.1. Bài toán

Một ứng dụng nhận các mã phiếu hỗ trợ qua một queue nội bộ. Thay vì xây dựng luồng nhận trực tiếp từ HTTP hay Kafka, ta mô phỏng nguồn có thể được polling:

~~~text
Queue<String> pendingCodes
  [" vip-101 ", "normal-202", "   "]
          │
          ▼
Supplier<String> pendingTicketSource
          │  được poller gọi định kỳ
          ▼
apply("normalizeTicket") → "VIP-101"
          │
          ▼
filter(code không rỗng)
          │
          ▼
apply("classifyTicket")
          │
          ▼
TicketResult("VIP-101", "EXPRESS")
          │
          ▼
accept("captureTicket")
          │
          ▼
Queue<TicketResult> processedTickets
~~~

Yêu cầu nghiệp vụ:

- Chuẩn hóa mã phiếu bằng cách cắt khoảng trắng và chuyển thành chữ hoa.
- Bỏ những mã rỗng sau chuẩn hóa.
- Mã bắt đầu `VIP-` vào luồng `EXPRESS`, còn lại là `STANDARD`.
- Ghi nhận kết quả trong queue để kiểm thử.
- Poll từng phần tử theo chu kỳ 250 ms, tối đa một message mỗi lần kích hoạt.

### 5.2. Mã ví dụ hoàn chỉnh

Đặt mã sau trong `src/main/java/example/ticket/TicketFlowConfig.java`. Đây là một ví dụ tự chứa ở mức cấu hình; nó chỉ dùng bộ nhớ, không yêu cầu Kafka hay cơ sở dữ liệu.

~~~java
package example.ticket;

import java.util.Locale;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.function.Consumer;
import java.util.function.Function;
import java.util.function.Supplier;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.cloud.function.integration.FunctionFlowBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;

record TicketResult(String code, String lane) {}

@Configuration
public class TicketFlowConfig {

    @Bean("pendingCodes")
    BlockingQueue<String> pendingCodes() {
        return new LinkedBlockingQueue<>();
    }

    @Bean("processedTickets")
    BlockingQueue<TicketResult> processedTickets() {
        return new LinkedBlockingQueue<>();
    }

    @Bean
    Supplier<String> pendingTicketSource(
            @Qualifier("pendingCodes") BlockingQueue<String> pendingCodes) {
        // poll() không chặn; trả null khi chưa có phần tử.
        return pendingCodes::poll;
    }

    @Bean
    Function<String, String> normalizeTicket() {
        return code -> code.strip().toUpperCase(Locale.ROOT);
    }

    @Bean
    Function<String, TicketResult> classifyTicket() {
        return code -> {
            if (code.isBlank()) {
                throw new IllegalArgumentException("Mã phiếu rỗng");
            }
            String lane = code.startsWith("VIP-")
                    ? "EXPRESS" : "STANDARD";
            return new TicketResult(code, lane);
        };
    }

    @Bean
    Consumer<TicketResult> captureTicket(
            @Qualifier("processedTickets")
            BlockingQueue<TicketResult> processedTickets) {
        return processedTickets::add;
    }

    @Bean
    IntegrationFlow ticketPollingFlow(FunctionFlowBuilder builder) {
        return builder
                .fromSupplier(
                        "pendingTicketSource",
                        endpoint -> endpoint.poller(
                                Pollers.fixedDelay(250)
                                        .maxMessagesPerPoll(1)))
                .apply("normalizeTicket")
                .filter(String.class, code -> !code.isBlank())
                .apply("classifyTicket")
                .accept("captureTicket");
    }
}
~~~

Giả sử ứng dụng Spring Boot có entry point cùng package cha hoặc package `example.ticket` để Spring quét được `TicketFlowConfig`:

~~~java
package example.ticket;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TicketApplication {
    public static void main(String[] args) {
        SpringApplication.run(TicketApplication.class, args);
    }
}
~~~

Không cần thêm `@Bean FunctionCatalog` thủ công khi auto-configuration của module tương thích đã hoạt động. `FunctionFlowBuilder` sẽ được Spring inject vào `ticketPollingFlow` và dùng catalog đã cấu hình.

### 5.3. Phân tích từng bước

**Nguồn dữ liệu**

~~~java
@Bean
Supplier<String> pendingTicketSource(
        @Qualifier("pendingCodes") BlockingQueue<String> source) {
    return source::poll;
}
~~~

`Supplier<String>` chỉ nói *làm thế nào để lấy mã phiếu kế tiếp*. Nó không tự tạo một scheduled task. `BlockingQueue.poll()` loại một phần tử khỏi queue và trả nó; khi queue rỗng, trả `null` ngay lập tức, không chặn thread.

**Source polling**

~~~java
.fromSupplier("pendingTicketSource",
        endpoint -> endpoint.poller(
                Pollers.fixedDelay(250).maxMessagesPerPoll(1)))
~~~

- `"pendingTicketSource"` là tên supplier trong `FunctionCatalog`.
- `fixedDelay(250)` biểu diễn khoảng trễ 250 ms giữa các lượt kích hoạt theo kiểu fixed delay.
- `maxMessagesPerPoll(1)` giới hạn mỗi lượt polling xử lý tối đa một message từ source.
- Đối với source polling của Spring Integration trong ví dụ này, khi supplier trả `null` thì lượt poll không có message để chuyển xuống các bước tiếp theo.

**Xử lý nghiệp vụ**

~~~java
.apply("normalizeTicket")
.filter(String.class, code -> !code.isBlank())
.apply("classifyTicket")
~~~

Hai lời gọi `apply` thực hiện function được tra cứu theo tên. `filter` là **EIP Message Filter** của Spring Integration, quyết định bỏ thông điệp rỗng sau chuẩn hóa. Điều kiện lọc không phải một function tự sinh ra broker route; đây là toán tử định tuyến trong flow.

**Đích xử lý**

~~~java
.accept("captureTicket");
~~~

`captureTicket` là `Consumer<TicketResult>`, được gọi sau khi phân loại thành công. Consumer không trả về message phản hồi để tiếp tục pipeline. Nếu sau này cần trả kết quả cho caller HTTP, nên thiết kế luồng request/reply phù hợp hoặc dùng một `Function` trả về dữ liệu thay vì `Consumer` điểm cuối.

### 5.4. Một trace minh họa

~~~text
pendingCodes.add(" vip-101 ")
    ↓
[Tới thời điểm poller kích hoạt]
pendingTicketSource.get()
    → " vip-101 "
    ↓
normalizeTicket.apply(...)
    → "VIP-101"
    ↓
filter: !code.isBlank() = true
    ↓
classifyTicket.apply(...)
    → TicketResult("VIP-101", "EXPRESS")
    ↓
captureTicket.accept(...)
    ↓
processedTickets chứa 1 kết quả
~~~

Với chuỗi chỉ gồm dấu cách, function chuẩn hóa trả chuỗi rỗng và filter loại message. Vì `pendingCodes.poll()` đã lấy phần tử khỏi queue, message bị lọc cũng không còn trong queue nguồn. Đây là hành vi có chủ đích ở bài tập; hệ thống production cần chính sách discard, lưu audit hoặc dead-letter nếu muốn truy vết dữ liệu bị loại.

## 6. Poller quyết định hoạt động của fromSupplier

### 6.1. Fixed delay, fixed rate và giới hạn mỗi lần poll

Các lựa chọn quan trọng:

| Tùy chọn | Ý nghĩa | Khi nào dùng |
| --- | --- | --- |
| `Pollers.fixedDelay(250)` | Nghỉ theo fixed delay giữa các lần kích hoạt; không nhằm bám sát một mốc giờ cố định. | Nguồn có dữ liệu đến đều, muốn điều tiết tải. |
| `Pollers.fixedRate(250)` | Lên lịch theo nhịp fixed rate; thực thi thực tế còn phụ thuộc scheduler và thời gian xử lý. | Cần nhịp lịch tương đối đều; phải xét tải/concurrency. |
| `maxMessagesPerPoll(1)` | Giới hạn số message được lấy/xử lý trong một lượt poll. | Tránh lấy nhiều mục liên tiếp trong một trigger. |
| `Pollers.trigger(customTrigger)` | Dùng `Trigger` tùy biến để quyết định thời điểm poll. | Poll một lần, theo lịch nghiệp vụ hoặc điều kiện phức tạp. |
| `taskExecutor(...)`/scheduler thích hợp | Ảnh hưởng thread thực thi tùy cấu hình endpoint. | Cần xử lý đồng thời có kiểm soát. |

**Không nên suy ra từ `fixedRate` hoặc `fixedDelay` rằng một lần gọi supplier được bảo đảm xử lý xong đúng hạn**. Nếu downstream mất 5 giây, hệ thống phải xét khả năng scheduler bị bận, tác vụ chồng lấn, backlog, timeout và ordering.

### 6.2. Vì sao không nên dùng `get()` trả cùng dữ liệu mãi?

Ví dụ:

~~~java
@Bean
Supplier<String> staticTicket() {
    return () -> "VIP-ALWAYS";
}
~~~

Nếu nguồn bị poll theo chu kỳ, mỗi lần `get()` lại trả `"VIP-ALWAYS"`, nên downstream sẽ thấy **nhiều message giống nhau**. Đó là hành vi hợp lệ cho heartbeat hoặc demo nhưng gây xử lý trùng nếu dữ liệu biểu diễn một giao dịch đơn lẻ.

Nguồn cần ngữ nghĩa rõ ràng, ví dụ:

- Queue: trả phần tử tiếp theo rồi lấy nó khỏi queue.
- Bảng dữ liệu: đọc theo cursor, checkpoint hoặc trạng thái xử lý.
- API ngoài: dùng ETag/offset/cursor hay dấu thời gian, có giới hạn tốc độ.
- Tác vụ phát định kỳ: chủ đích tạo sự kiện mới với mã định danh mới cho mỗi lần gọi.

### 6.3. Khi không có dữ liệu

Một supplier trả `null` ở source polling thông thường biểu thị **lượt này không phát message**. Điều đó khác với việc muốn gửi một thông điệp có payload `null`: Spring Messaging không cho phép sử dụng `null` tùy tiện làm message payload.

Ví dụ với queue:

~~~java
Supplier<String> source = queue::poll;
String item = source.get();

if (item == null) {
    // Queue đang rỗng, không có item mới trong lượt này.
}
~~~

Flow vẫn còn hoạt động và poller sẽ thử lại theo lịch cho đến khi endpoint được dừng. Không nên để supplier chặn vô hạn trong `get()`, vì điều đó có thể giữ thread của poller và làm việc dừng ứng dụng khó kiểm soát. Nếu sử dụng polling có timeout, cần thiết kế timeout và huỷ bỏ đúng cách.

### 6.4. Default poller so với poller riêng

Hai dạng dưới đây khác về khả năng quan sát cấu hình:

~~~java
.fromSupplier("pendingTicketSource")
~~~

~~~java
.fromSupplier("pendingTicketSource",
        e -> e.poller(Pollers.fixedDelay(250).maxMessagesPerPoll(1)))
~~~

Dạng đầu dựa vào **default poller** của Spring Integration trong application context theo phiên bản/API đang dùng. Nếu chưa có default poller phù hợp, việc dựng flow có thể lỗi hoặc chạy không đúng ý định. Dạng thứ hai đặt cấu hình ngay tại endpoint và thường dễ hiểu hơn cho bài học hoặc một source có yêu cầu lịch riêng.

## 7. Composition: áp dụng nhiều Function sau fromSupplier

FunctionCatalog có thể ghép các hàm theo cú pháp `functionA|functionB`. Trong ví dụ:

~~~text
normalizeTicket : Function<String, String>
classifyTicket  : Function<String, TicketResult>
captureTicket   : Consumer<TicketResult>
~~~

Nếu không cần một EIP đứng giữa hai bước, có thể viết:

~~~java
@Bean
IntegrationFlow shortFlow(FunctionFlowBuilder builder) {
    return builder
            .fromSupplier("pendingTicketSource",
                    e -> e.poller(Pollers.fixedDelay(250)))
            .accept("normalizeTicket|classifyTicket|captureTicket");
}
~~~

**Đây là cấu hình thay thế để minh họa**, không nên đăng ký đồng thời với `ticketPollingFlow` trên cùng supplier/queue trong demo vì hai polling endpoint có thể tranh nhau lấy dữ liệu. `Consumer` ở cuối composition khiến toàn bộ chuỗi trở thành một bước tiêu thụ, phù hợp với `accept(...)`.

Tuy nhiên, **hai phiên bản chưa tương đương về nghiệp vụ**: phiên bản gốc có `filter` bỏ mã rỗng; phiên bản rút gọn không có filter, nên `classifyTicket` sẽ ném exception đối với chuỗi rỗng. Nếu cần giữ chính sách lọc, nên giữ EIP Filter riêng hoặc thay đổi hợp đồng function một cách có chủ đích.

### 7.1. Không nhầm composition với EIP

| Thành phần | Thành quả | Không tự cung cấp |
| --- | --- | --- |
| `apply("normalizeTicket|classifyTicket")` | Một chuỗi function có kiểu đầu vào/ra tương thích. | Kênh bền vững, retry từng bước, Splitter/Aggregator. |
| `filter(...)` | Chỉ cho message đạt điều kiện đi tiếp. | Business validation đầy đủ nếu chưa được mô tả. |
| `route(...)` | Gửi tới channel phù hợp theo khóa định tuyến. | Tự động tạo quy tắc nghiệp vụ trong catalog. |
| `wireTap(...)` | Sao chép message sang luồng quan sát/audit. | Bảo đảm lưu trữ audit nếu chưa có handler/stores. |
| `fromSupplier(...)` | Nguồn message được gọi theo poller. | Ack/retry/broker transaction. |

Để thêm quan sát, ví dụ:

~~~java
return builder
        .fromSupplier("pendingTicketSource",
                e -> e.poller(Pollers.fixedDelay(250)))
        .wireTap("tickets.auditChannel")
        .apply("normalizeTicket")
        .accept("captureText");
~~~

Đây là **minh họa một flow khác**: `tickets.auditChannel` phải được cấu hình và có consumer tương ứng; `captureText` phải là `Consumer<String>` đã đăng ký. Không dùng đoạn này thay nguyên vào demo nếu chưa khai báo các thành phần được nhắc đến.

## 8. Phân biệt Supplier thường và Supplier reactive

Spring Cloud Function hỗ trợ cả:

~~~java
Supplier<TicketResult> imperativeSupplier;
Supplier<Flux<TicketResult>> reactiveSupplier;
~~~

Đối với `Supplier<T>` thông thường, mỗi lần `get()` có thể tạo **một phần tử** cho một lượt polling (tuỳ source contract). `Supplier<Flux<T>>` thì cung cấp một **Publisher**, có thể biểu diễn một stream dài hoặc nhiều phần tử.

Điều này ảnh hưởng đến cách tích hợp:

1. Một `Flux<T>` là đối tượng stream, **không tự đồng nghĩa với một message riêng cho mỗi phần tử**.
2. Nếu muốn đưa từng phần tử vào flow, cần một ranh giới reactive hoặc splitter thích hợp, hiểu đúng subscription, backpressure và lifecycle.
3. Một supplier reactive có thể được thiết kế để tạo luồng dài sống lâu, hoặc tạo các luồng hữu hạn theo từng lần gọi. Nhịp polling hợp lý phụ thuộc vào loại nguồn.
4. Spring Cloud Function có annotation `@PollableSupplier` để biểu đạt ý định source reactive hữu hạn có thể được gọi lại; **annotation này tự nó không tạo scheduler**. Trong IntegrationFlow, polling/adapter vẫn cần được cấu hình phù hợp.

Tài liệu Spring Cloud Function đưa ví dụ nâng cao:

~~~java
return builder
        .fromSupplier("httpSupplier",
                e -> e.poller(Pollers.trigger(new OnlyOnceTrigger())))
        .<Flux<?>>handle((fluxPayload, headers) -> fluxPayload,
                e -> e.async(true))
        .channel(c -> c.flux())
        .apply("spelFunction")
        .<String, String>transform(String::toUpperCase)
        .accept("fileConsumer");
~~~

Đây là một **trích đoạn cấu trúc** để đọc hiểu, không phải ví dụ biên dịch độc lập: nó yêu cầu các function `httpSupplier`/`spelFunction`/`fileConsumer`, các import, component reactive và cấu hình riêng theo thư viện Spring Functions Catalog. Điểm đáng học là *source polling một lần*, *async handler*, *flux channel* và *function* phải phối hợp với nhau. Không nên lấy nguyên `Supplier<Flux<T>>` rồi giả định `apply("imperativeFunction")` tự tách từng phần tử và xử lý đúng.

## 9. Message payload, header và chuyển đổi kiểu

Message của Spring Integration gồm **payload** và **headers**:

~~~text
Message<String>
  payload: " vip-101 "
  headers:
    id: ...
    timestamp: ...
    traceId: ... (nếu được cung cấp)
~~~

Trong demo, `Supplier<String>` trả một giá trị chuỗi. Source adapter đóng gói nó thành message cho flow. Bước `apply("normalizeTicket")` xử lý payload theo kiểu khai báo. Nếu thay bằng `Supplier<Message<T>>` để thêm header, cần kiểm thử xem quá trình tra cứu/catalog wrapper, endpoint và adapter bảo toàn metadata nào.

Ví dụ ý tưởng tạo message ở nguồn:

~~~java
@Bean
Supplier<Message<String>> sourceWithTrace() {
    return () -> MessageBuilder.withPayload("VIP-101")
            .setHeader("traceId", "run-042")
            .build();
}
~~~

Import `org.springframework.messaging.Message` và `org.springframework.messaging.support.MessageBuilder`. Cấu hình này chỉ nhằm minh họa contract với header; đừng đăng ký thêm flow dùng nguồn này nếu chưa xác định thời điểm phát và idempotency.

**Các lưu ý quan trọng:**

- `Supplier<String>` → `Function<String, TicketResult>` là chuỗi có kiểu rõ ràng; đổi sang JSON, byte array hoặc POJO khác có thể cần converter.
- `Function<Message<T>, Message<R>>` có quyền đọc và tạo header; một function chỉ nhận `T` không nên tự phụ thuộc thông tin transport.
- Header về acknowledgement, partition key, delivery attempt hoặc correlation ID có thể do adapter/broker quản lý. Không giả định chúng luôn còn nguyên khi đi qua mọi ranh giới.
- `FunctionCatalog` có thể dùng conversion và wrapper; hãy kiểm tra kiểu đầu/ra thực tế ở **ranh giới IntegrationFlow** thay vì dựa vào cast không kiểm soát.
- Payload `null` không phải một message hợp lệ để gửi tiếp; hãy biểu diễn “chưa có dữ liệu” theo hợp đồng của source.

## 10. Kiểm thử flow có nguồn polling

Khác với flow bắt đầu bằng `from("channelName")`, flow `fromSupplier(...)` được **scheduler kích hoạt**, nên test phải chờ sự kiện với thời hạn rõ ràng.

### 10.1. Unit test function

Không cần Spring context để kiểm tra nghiệp vụ:

~~~java
TicketFlowConfig config = new TicketFlowConfig();

String code = config.normalizeTicket().apply(" vip-101 ");
TicketResult result = config.classifyTicket().apply(code);

assertEquals("VIP-101", result.code());
assertEquals("EXPRESS", result.lane());
~~~

Thêm ca `normal-202` → `STANDARD`; chuỗi rỗng bị validation từ chối; chuỗi khoảng trắng được filter bỏ trong flow. Test unit function không xác nhận lịch polling hoặc EIP Filter.

### 10.2. Integration test có thời hạn

Giả sử `TicketApplication` cùng package với `TicketFlowConfig` và test dùng JUnit 5:

~~~java
package example.ticket;

import java.util.concurrent.BlockingQueue;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(classes = TicketApplication.class)
class TicketPollingFlowTest {

    @Autowired
    @Qualifier("pendingCodes")
    BlockingQueue<String> pendingCodes;

    @Autowired
    @Qualifier("processedTickets")
    BlockingQueue<TicketResult> processedTickets;

    @Test
    void shouldPollNormalizeAndClassify() throws InterruptedException {
        pendingCodes.clear();
        processedTickets.clear();

        pendingCodes.add("  vip-101  ");

        TicketResult result = processedTickets.poll(3, TimeUnit.SECONDS);

        assertNotNull(result, "Không nhận được kết quả trước timeout");
        assertEquals("VIP-101", result.code());
        assertEquals("EXPRESS", result.lane());
    }
}
~~~

**Vì sao không dùng `processedTickets.poll()` ngay sau `pendingCodes.add(...)`?** Poller chạy theo lịch và có thể chưa đến lượt gọi supplier. `poll(3, TimeUnit.SECONDS)` cho test chờ có giới hạn, tránh flakiness do timing trong trường hợp bình thường.

Nếu nhiều test chạy song song hoặc dùng chung Spring context/queue, cần cách ly trạng thái từng test hoặc tạm dừng/khởi động endpoint theo test. Các hàng đợi trong ví dụ là shared beans, thích hợp demo nhưng không thay thế một hệ thống kiểm thử độc lập.

### 10.3. Kiểm tra trường hợp không có dữ liệu

Có thể đo số kết quả trước và sau một khoảng ngắn, nhưng không nên viết test với `Thread.sleep(...)` chỉ để suy ra chắc chắn một scheduling policy. Để kiểm tra logic source, gọi trực tiếp `pendingTicketSource(...).get()` khi queue rỗng; để kiểm tra polling adapter, dùng metric/spy hoặc harness test Integration có khả năng điều khiển clock/scheduler theo mức độ tin cậy cần thiết.

### 10.4. Các ca cần kiểm tra thêm

| Ca | Kỳ vọng |
| --- | --- |
| Queue trống | Không có message đi đến consumer trong lượt polling. |
| `" vip-101 "` | Một kết quả `TicketResult("VIP-101", "EXPRESS")`. |
| `"normal-202"` | Một kết quả `STANDARD`. |
| `"   "` | Bị filter loại, không phát `TicketResult`. |
| Nhiều phần tử liên tiếp | Được poll theo giới hạn `maxMessagesPerPoll` và nhịp đã cấu hình, không giả định xử lý đồng thời. |
| `classifyTicket` ném exception | Xác định đường xử lý lỗi của poller; bảo đảm hệ thống không âm thầm bỏ mất dữ liệu quan trọng. |
| Consumer ghi dữ liệu thất bại | Xác định retry, idempotency, dead-letter hoặc bù trừ phù hợp. |

## 11. Lỗi, retry và tính an toàn dữ liệu

Trong demo, `pendingCodes.poll()` **lấy phần tử khỏi queue trước** khi các bước normalize/classify/capture được thực thi. Nếu consumer ném lỗi sau đó, phần tử **không tự được đưa lại vào queue**. Đừng nhầm việc có poller với khả năng giao nhận bền vững.

~~~mermaid
flowchart TD
    A["Supplier lấy item khỏi queue"] --> B["Function xử lý"]
    B --> C{"Thành công?"}
    C -->|Có| D["Consumer nhận kết quả"]
    C -->|Lỗi| E["Error handler / retry policy"]
    E --> F{"Có cơ chế khôi phục item?"}
    F -->|Có| G["Retry / lưu lỗi / bù trừ"]
    F -->|Không| H["Có nguy cơ mất dữ liệu"]
~~~

| Lỗi | Cách xử lý nên cân nhắc |
| --- | --- |
| Sai tên supplier/function/consumer | Fail fast khi dựng flow, kiểm tra tên trong catalog và dependency. |
| Input không hợp lệ | Validate hoặc filter; có thể gửi discard channel/audit, tránh retry vô hạn. |
| API phụ thuộc tạm thời lỗi | Retry với backoff có giới hạn tại handler/adapter; tránh làm nghẽn poller. |
| Source đã lấy item nhưng downstream thất bại | Cần transactional source, acknowledgement hoặc cơ chế khôi phục/redrive thích hợp. |
| Event trùng sau retry/redelivery | Thiết kế consumer idempotent theo khóa nghiệp vụ. |
| Tải đến vượt khả năng xử lý | Tuning poller, batch size, queue capacity, concurrency và giám sát backlog. |
| Shutdown giữa lúc xử lý | Xác định điểm dừng poller, cách drain, checkpoint và xử lý phần tử đang chạy. |

**Không có bảo đảm exactly-once chỉ nhờ `fromSupplier(...)`.** Với queue trong bộ nhớ, ứng dụng còn có thể mất dữ liệu khi process restart. Khi đi production, một hệ thống nguồn bền vững có trạng thái/ack hoặc broker phù hợp sẽ giải quyết vấn đề đó tốt hơn.

### 11.1. Retry nằm ở đâu?

Tùy loại endpoint, có thể cấu hình advice/error handler trên polling adapter hoặc handler phía sau. Spring Integration có error channel và cơ chế xử lý exception, nhưng **không phải exception nào cũng đi theo một đường giống nhau**: nguồn đồng bộ, executor, reactive flow và adapter bên ngoài có ngữ nghĩa khác nhau.

Một nguyên tắc thực tế:

- Lỗi **dữ liệu** (mã phiếu không hợp lệ) thường không nên retry vô hạn.
- Lỗi **tạm thời** (mạng hoặc API phụ thuộc) có thể retry có giới hạn/backoff.
- Lỗi **không hồi phục** cần lưu log có ngữ cảnh, error store hoặc dead-letter theo yêu cầu.
- Với bất kỳ retry/redelivery nào, consumer cần tránh tác dụng phụ lặp bằng khóa idempotency hoặc transaction phù hợp.

## 12. Khi nào fromSupplier phù hợp và khi nào nên dùng adapter khác?

| Tình huống | Lựa chọn phù hợp | Lý do |
| --- | --- | --- |
| Đọc công việc định kỳ từ repository/queue nội bộ | `fromSupplier("source", poller)` | Supplier có thể đóng gói quy tắc lấy item, flow xử lý theo nhịp rõ ràng. |
| Phát sự kiện heartbeat hoặc snapshot theo lịch | `fromSupplier` | Supplier có thể chủ động tạo mỗi lần gọi; cần định nghĩa ý nghĩa của sự kiện trùng. |
| Đã có inbound channel nhận message từ flow khác | `builder.from("channelName")` | Message đã được đẩy vào, không cần polling một supplier. |
| Nhận HTTP request rồi trả response | HTTP adapter hoặc gateway phù hợp | Cần request/reply, status code, serialization và timeout HTTP. |
| Tiêu thụ Kafka/RabbitMQ có ack/redelivery | Spring Cloud Stream binder hoặc Spring Integration inbound adapter tương ứng | Broker adapter xử lý đặc thù protocol, partition, acknowledgement và retry. |
| Dùng `Supplier<Flux<T>>` là stream dài sống lâu | Reactive flow/adapter đã thiết kế rõ subscription | Không nên poll để tạo stream mới liên tục nếu một stream dài mới là ý định. |
| Chỉ cần gọi một function thuần trong code Java | `FunctionCatalog.lookup(...)` rồi `apply(...)` | Không cần tạo `IntegrationFlow` nếu không có bài toán tích hợp message. |

Kết hợp với HTTP, sự kiện và serverless là một lợi ích của **mô hình hàm tách khỏi giao thức**, nhưng mỗi môi trường cần adapter riêng. `fromSupplier` là **một chiến lược tạo nguồn message cho Spring Integration**, không thay thế toàn bộ những adapter đó.

## 13. Troubleshooting theo triệu chứng

| Triệu chứng | Nguyên nhân cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| Không inject được `FunctionFlowBuilder` | Thiếu `spring-cloud-function-integration` hoặc auto-configuration/version không phù hợp. | Kiểm tra dependency tree, release train, bean auto-configuration. |
| Lỗi không tìm thấy `pendingTicketSource` | Tên bean không khớp, bean không được quét/đăng ký catalog. | Kiểm tra `@Configuration`, method `@Bean` và tên function. |
| Flow có bean nhưng không chạy | Poller không có hoặc endpoint chưa được start. | Dùng overload có `e.poller(...)`, kiểm tra lifecycle của integration endpoint. |
| Supplier được gọi mãi, không có item | Queue rỗng và supplier trả `null`. | Kiểm tra writer đưa item vào đúng queue, monitor backlog. |
| Supplier trả mã giống nhau liên tục | Supplier luôn trả constant/cùng record. | Đổi contract nguồn, cursor hoặc điều kiện chỉ phát một lần. |
| Xử lý chậm hơn kỳ vọng | Downstream blocking, scheduler bận, poller không đúng nhịp. | Kiểm tra latency, poll interval, max messages per poll, executor. |
| `ClassCastException` hoặc lỗi chuyển đổi | Kiểu payload khác chữ ký function, thiếu converter/content type. | Dùng kiểu rõ ràng, test conversion ở đầu flow. |
| `apply` tìm thấy function nhưng lỗi runtime | Function ném exception hoặc đầu vào sai. | Unit test function và test catalog riêng. |
| Dữ liệu biến mất sau exception | Source đã xóa item khỏi queue trước khi consumer thành công. | Thiết kế ack/retry/error store hoặc transactional retrieval. |
| Process shutdown làm mất backlog | Queue hoàn toàn trong bộ nhớ. | Chuyển sang nguồn bền vững nếu cần bảo đảm khôi phục. |
| Header trace biến mất | Wrapper/adapter/transformer thay đổi message. | Dùng `Message<T>` khi thật sự cần và kiểm thử bảo toàn header. |

### Bài tập mở rộng

1. Thay `Supplier<String>` bằng `Supplier<OrderRequest>` và hai function phân loại đơn theo tổng tiền, giữ nguyên nguyên lý polling.
2. Thêm một **discard channel** cho mã phiếu rỗng thay vì loại bỏ mà không ghi nhận.
3. Thử `maxMessagesPerPoll(3)` với mười item và đo số lượt gọi supplier khi downstream chạy nhanh/chậm.
4. Thêm một consumer cố tình ném exception cho mã `VIP-FAIL`, quan sát hành vi queue và thiết kế cơ chế khôi phục.
5. Viết một biến thể dùng `from("tickets.input")` để so sánh chủ động polling với message được đẩy vào.

## 14. Checklist tự đánh giá

- [ ] Tôi phân biệt được supplier tạo dữ liệu với poller quyết định thời điểm gọi `get()`.
- [ ] Tôi biết `fromSupplier("name")` tra cứu tên **trong catalog**, còn `from("name")` bắt đầu từ **channel**.
- [ ] Tôi có thể giải thích tại sao `FunctionFlowDefinition` bổ sung `apply`/`accept` cho Integration DSL.
- [ ] Tôi biết khi nào cần poller tường minh và ý nghĩa của `maxMessagesPerPoll`.
- [ ] Tôi không nhầm `null` từ supplier rỗng với message có payload `null`.
- [ ] Tôi biết composition chỉ ghép hàm, không tự thực hiện EIP filter/route/aggregate.
- [ ] Tôi có test chờ theo thời hạn vì poller chạy theo lịch, không phụ thuộc thời điểm gửi.
- [ ] Tôi đã cân nhắc idempotency và khôi phục khi source lấy item trước khi downstream thành công.

## 15. Tài liệu tham khảo chính thức

- [Spring Cloud Function — Spring Integration Interaction](https://docs.spring.io/spring-cloud-function/reference/spring-integration.html): giới thiệu module `spring-cloud-function-integration`, `FunctionFlowBuilder`, `fromSupplier`, `apply`, `accept` và mẫu reactive.
- [Spring Cloud Function — Programming Model](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html): `Supplier`, `Function`, `Consumer`, `FunctionCatalog`, composition và annotation `@PollableSupplier`.
- [Spring Integration — java.util.function Interfaces Support](https://docs.spring.io/spring-integration/reference/functions-support.html): hỗ trợ `Supplier`/`Function` trong IntegrationFlow và các endpoint.
- [Spring Integration — IntegrationFlow Javadoc](https://docs.spring.io/spring-integration/docs/6.4.2/api/org/springframework/integration/dsl/IntegrationFlow.html): factory `fromSupplier` nhận `Supplier` và cấu hình polling.

**Kết luận:** `FunctionFlowBuilder` giúp Spring Integration gọi các hàm nghiệp vụ trong `FunctionCatalog` bằng tên. `fromSupplier(...)` là phần kết nối đặc biệt quan trọng: nó biến một `Supplier<T>` thành nguồn message được kích hoạt theo poller, sau đó có thể ghép `apply`, các toán tử EIP và `accept`. Sự tách biệt này giúp các hàm của Spring Cloud Function tiếp tục có thể tái sử dụng khi kết nối với HTTP, sự kiện hoặc serverless, đồng thời giữ việc điều phối, lập lịch và xử lý lỗi ở tầng tích hợp thích hợp.
