# Observation context và metadata module

Trong ứng dụng **Spring Boot** được tổ chức bằng **Spring Modulith**, một request đặt hàng có thể đi vào module `orders`, gọi module `payments` và kích hoạt listener của `inventory`. Khi xem trace, ta muốn biết **span thuộc module nào, vào qua phương thức nào, bằng lời gọi bean hay event listener**. Khi tổng hợp metrics, ta muốn gom dữ liệu theo module và loại event mà không tạo hàng triệu chuỗi dữ liệu mới. Những thông tin mô tả đó được gọi là **metadata quan sát**.

**Micrometer Observation API** dùng `Observation.Context` để giữ dữ liệu của một operation trong suốt vòng đời quan sát. Spring Modulith xây dựng trên cơ chế này với **`ModulithContext`** và **`ModulithObservationConvention`** nhằm bổ sung metadata về application module vào các lần tương tác được instrument.

Bài học thuộc chương **Observation API** của mô-đun **SPRING_MODULITH_DOCUMENTATION_OBSERVABILITY**, gắn với mục tiêu sinh tài liệu ranh giới module, dùng module graph/Actuator, event metrics, tracing và context propagation để kiểm chứng kiến trúc mô-đun khi hệ thống vận hành.

## 1. Kết quả học tập

Sau bài này, bạn có thể:

1. Giải thích `Observation`, `ObservationRegistry`, `Observation.Context`, `ObservationHandler` và `ObservationConvention` làm việc với nhau như thế nào.
2. Phân biệt **dữ liệu ngữ cảnh nội bộ**, **low-cardinality key-values**, **high-cardinality key-values** và **trace context**.
3. Xác định metadata module qua `ModulithContext`, các thuộc tính `module.identifier`, `module.name`, `module.invocation-type` và `module.method`.
4. Đọc JavaDoc của `ModulithContext` và giải thích vai trò của `ModulithObservationConvention`.
5. Tạo một observation nghiệp vụ có metadata bằng Java, thu thập lỗi và sự kiện đúng vòng đời.
6. Bổ sung metadata ổn định cho observation của Spring Modulith mà vẫn giữ các thuộc tính mặc định.
7. Kiểm tra metadata trên trace/metric và nhận ra các giới hạn do sampling, context propagation, instrumentation và backend.

## 2. Observation context là gì?

**`Observation`** là một đơn vị công việc được instrument, có các thao tác vòng đời như **create**, **start**, **openScope**, **event**, **error**, **stop**. Khi tạo một observation, Micrometer gắn với nó một **`Observation.Context` có thể thay đổi**.

Một `Observation.Context` là vùng chứa dữ liệu giống map, dùng để trao đổi trạng thái giữa code instrumentation và các `ObservationHandler`. Handler nhận cùng context trong các callback như `onStart(...)`, `onError(...)`, `onEvent(...)` và `onStop(...)`.

~~~mermaid
flowchart TB
    A["Code nghiệp vụ / Spring Modulith<br/>tạo Observation"] --> B["Observation + mutable Context"]
    R["ObservationRegistry<br/>cấu hình handler/filter/convention"] --> B
    B -->|"start / event / error / stop"| H["ObservationHandler"]
    H --> M["Micrometer Metrics<br/>MeterRegistry"]
    H --> T["Micrometer Tracing<br/>tracer / spans"]
    C["ObservationConvention<br/>tên và key-values"] --> B
    F["ObservationFilter<br/>điều chỉnh Context khi stop"] --> B
~~~

Sơ đồ mô tả cách các thành phần phối hợp; không có nghĩa mỗi observation mặc định đều tạo cả metric lẫn span. Điều đó còn phụ thuộc **handler đã đăng ký**, tracer, meter registry, exporter và cấu hình ứng dụng.

### 2.1. Vai trò của từng thành phần

| Thành phần | Chức năng chính | Có phải dữ liệu của một request cụ thể? |
| --- | --- | --- |
| `Observation` | Đại diện một operation được instrument; điều phối start/scope/event/error/stop | Có |
| `Observation.Context` | Chứa key-values, tên, lỗi và thông tin phục vụ handlers | Có |
| `ObservationRegistry` | Đăng ký cấu hình, predicates, filters, conventions, handlers | Không, là hạ tầng dùng chung |
| `ObservationHandler` | Phản ứng trước lifecycle để ghi metric, span hoặc xử lý khác | Handler thường dùng chung, nhận context của từng observation |
| `ObservationConvention` | Quy định tên và key-values của một loại observation | Quy tắc chung, tính giá trị theo từng context |
| `ObservationFilter` | Cho phép điều chỉnh context trước khi các handler `onStop` được gọi | Quy tắc dùng chung, áp dụng vào context cụ thể |

**Điểm quan trọng:** `Observation.Context` **không phải** `org.springframework.context.ApplicationContext`. ApplicationContext quản lý Spring beans; Observation.Context là dữ liệu riêng của hoạt động được quan sát.

### 2.2. Context có thể chứa những gì?

Theo API Micrometer, context hỗ trợ:

- `put(Object key, T value)` và `get(Object key)`: lưu/đọc trạng thái nội bộ; không phải mọi mục được lưu đều tự biến thành metric tag hay span attribute.
- `addLowCardinalityKeyValue(KeyValue)`: thêm key-value có tập giá trị hữu hạn để handler metrics có thể dùng làm nhãn.
- `addHighCardinalityKeyValue(KeyValue)`: thêm key-value có tập giá trị rất lớn, thường phù hợp hơn với dữ liệu span khi tracing cho phép.
- `getError()`: lỗi đã được ghi nhận trong observation, nếu có.
- `getName()` và `getContextualName()`: tên kỹ thuật và tên có ngữ cảnh phục vụ cách hiển thị.
- `getParentObservation()`: quan hệ observation cha nếu có.

Ví dụ minh họa về **ba tầng thông tin khác nhau**:

~~~text
Observation.Context
├── Dữ liệu nội bộ: stockReservationStartedAt = <timestamp>
├── Low-cardinality key-values: app.module = "inventory"
│                              operation = "reserve-stock"
└── High-cardinality key-values: operation.run.id = "<ID giả lập>"
~~~

Một giá trị được lưu bằng `context.put("operation.run.id", value)` không tự trở thành span tag. Muốn được handler xuất thành tag, phải sử dụng API key-value thích hợp hoặc convention/filter cung cấp các key-values đó.

## 3. Metadata: low cardinality và high cardinality

**Cardinality** là số lượng giá trị khác nhau có thể xuất hiện cho một khóa. Đây là điểm quyết định chi phí và khả năng truy vấn.

| Ví dụ | Phân loại đề xuất | Lý do |
| --- | --- | --- |
| `module.identifier = orders` hoặc `payments` | Low cardinality | Danh sách module thường hữu hạn |
| `module.invocation-type = bean` hoặc `event listener` | Low cardinality | Số giá trị có giới hạn |
| `operation = reserve-stock` | Low cardinality | Danh mục operation được định nghĩa trước |
| `outcome = success` / `error` | Low cardinality | Số trạng thái nhỏ |
| `order.id = 9e...` | High cardinality | Có thể có một giá trị mới cho mỗi đơn |
| `user.email` | High cardinality và nhạy cảm | Không thích hợp làm metric tag; không nên thu thập nếu không cần |
| `http.route = /orders/{id}` | Low cardinality nếu route template ổn định | Tránh URL thực tế chứa ID |
| `http.url = /orders/123456` | Có thể high cardinality | Mỗi request có thể mang giá trị khác nhau |

Trong Micrometer, **metrics handlers dùng low-cardinality key-values làm tags**. High-cardinality key-values **không được đưa vào metric tags** bởi metrics handler mặc định để tránh bùng nổ số lượng time series. Tracing handler có thể sử dụng cả hai nhóm làm span attributes tùy bridge và convention.

**Không có nghĩa high cardinality là vùng an toàn để ghi dữ liệu nhạy cảm.** Trace cũng có chi phí lưu trữ, quyền truy cập và chính sách bảo mật. Tránh ghi mật khẩu, token, email, số thẻ, mã khách hàng hoặc payload riêng tư vào observation context chỉ để phục vụ dashboard.

### 3.1. Một sai lầm gây chi phí lớn

Nếu gắn `orderId` làm **low-cardinality key-value**, ứng dụng có 100.000 đơn có thể tạo ra hàng trăm nghìn bộ metric tags khác nhau chỉ cho một operation. Mỗi tổ hợp nhãn có thể thành một time series trong Prometheus.

Cách sửa là **đo tổng hợp** bằng các nhãn cố định:

~~~text
Tốt cho metrics:
  module=orders
  operation=create-order
  outcome=success|failure

Không phù hợp cho metrics:
  module=orders
  orderId=<mỗi đơn một UUID>
~~~

Nếu cần truy vấn một đơn cụ thể, hãy dùng **trace ID kết hợp log correlation**, hoặc cơ chế tra cứu nghiệp vụ có phân quyền. Không biến mã định danh giao dịch thành metric tag.

## 4. Spring Modulith đưa thông tin module vào Observation như thế nào?

Spring Modulith nhận diện **application modules** từ mã ứng dụng. Khi bật observability, nó instrument những Spring component thuộc API/entry point của module được hỗ trợ. Lần đi vào một entry point có thể sinh một **module entry observation**, sau đó tracing handler có thể biểu diễn thành **module entry span**.

Cốt lõi của metadata này là **`org.springframework.modulith.observability.ModulithContext`**, một lớp **kế thừa `io.micrometer.observation.Observation.Context`**. JavaDoc chính thức của Spring Modulith 2.2 mô tả constructor:

~~~java
ModulithContext(
    ObservedModule module,
    org.aopalliance.intercept.MethodInvocation invocation,
    org.springframework.core.env.Environment environment
)
~~~

Đây là **API mô tả cách framework tạo context cho observation module**. Trong ứng dụng thông thường, Spring Modulith tạo context khi chặn lời gọi qua ranh giới; bạn **không cần tự gọi constructor** này để bật module instrumentation.

### 4.1. Những metadata mà `ModulithContext` cung cấp

| Method / dữ liệu | Ý nghĩa | Ứng dụng |
| --- | --- | --- |
| `getModule()` | `ObservedModule` đang được quan sát | Lấy technical ID và tên hiển thị |
| `getInvocation()` | `MethodInvocation` được chặn ở entry point | Phân tích phương thức gọi |
| `getApplicationName()` | Tên application nếu được cấu hình | Bổ sung ngữ cảnh vận hành |
| `getContextualName()` | Tên có ngữ cảnh của operation | Giúp đọc trace có ý nghĩa |
| `getLowCardinalityValues()` | Các key-values ít biến thể mà Modulith tính ra | Quy ước tags phù hợp cho metrics |
| `getHighCardinalityValues()` | Các key-values nhiều biến thể mà Modulith tính ra | Metadata chi tiết cho tracing tùy handler |

`ObservedModule` cung cấp các thao tác như `getIdentifier()`, `getDisplayName()`, `getInvokedMethod(invocation)` và `isEventListenerInvocation(invocation)`. Điều này giải thích **framework lấy dữ liệu module/method và phân biệt bean call với event listener bằng cách nào**.

Cần phân biệt tên method trong API Modulith:

- `ModulithContext.getLowCardinalityValues()` là dữ liệu do lớp Modulith tạo ra.
- `Observation.Context.getLowCardinalityKeyValues()` là API Micrometer đọc các key-values đang gắn trực tiếp trên observation context.
- `ModulithObservationConvention.getLowCardinalityKeyValues(context)` quyết định nhóm key-values theo **quy ước** cho observation đó.

Ba nguồn này có thể liên quan nhưng **không phải ba tên gọi đồng nghĩa**. Đừng mặc định `context.put(...)` hoặc một key-value trên context sẽ tự xuất hiện ở mọi backend.

### 4.2. Bốn thuộc tính quan trọng của module entry span

Tài liệu **Spring Modulith Production-ready Features** công bố các thuộc tính sau cho **Module Entry Span**:

| Attribute | Ý nghĩa | Ví dụ minh họa |
| --- | --- | --- |
| `module.identifier` | Technical ID của module | `orders` |
| `module.name` | Tên module | `Orders` |
| `module.invocation-type` | Hình thức truy cập module | `bean` hoặc `event listener` |
| `module.method` | Phương thức thực thi tại entry point | `placeOrder` hoặc `on` |

Khi thấy một span có:

~~~text
module.identifier = "inventory"
module.name = "Inventory"
module.invocation-type = "event listener"
module.method = "on"
~~~

ta có thể suy ra span mô tả một **entry point của module inventory được gọi như event listener**, chứ chưa thể kết luận publication đã được xử lý thành công, transaction đã commit hay caller đã nhận kết quả.

**Lưu ý về cardinality:** Tài liệu liệt kê bốn **span tags**, nhưng không nên suy ngược rằng tất cả bốn thuộc tính luôn nằm trong **low-cardinality metric tags**. Hãy kiểm tra `ModulithObservationConvention` và dữ liệu thực tế được xuất của phiên bản đang dùng.

## 5. Phân biệt metadata module trên ba kênh

Cùng một từ “module” có thể xuất hiện trong nhiều đầu ra nhưng ý nghĩa đo đạc khác nhau.

| Kênh | Dữ liệu module nhận được | Câu hỏi trả lời |
| --- | --- | --- |
| `GET /actuator/modulith` | Technical name, display name, base package, dependencies | “Ứng dụng có những module nào và phụ thuộc thế nào?” |
| **Module entry span** | `module.identifier`, `module.name`, `module.invocation-type`, `module.method` | “Một lần chạy đi vào module nào, theo cách nào, khi nào?” |
| **Event publication metric** | `module.events.published` với các tags như `module.event.type` và `module.identifier` | “Ứng dụng công bố event nào, bao nhiêu lần?” |
| **Observation.Context** | Metadata trung gian và thông tin nội bộ của operation | “Handler/convention cần dữ liệu gì để tạo các tín hiệu?” |

Ví dụ sự kiện `OrderPlaced` được module `orders` công bố, rồi `inventory` nhận:

~~~mermaid
sequenceDiagram
    participant W as Web
    participant O as Orders
    participant E as Event publisher
    participant I as Inventory listener
    W->>O: placeOrder()
    Note over O: module.identifier=orders<br/>invocation-type=bean
    O->>E: publish OrderPlaced
    Note over E: module.events.published<br/>counter publication
    E-->>I: on(OrderPlaced) (có thể async)
    Note over I: module.identifier=inventory<br/>invocation-type=event listener
~~~

`/actuator/modulith` có thể cho thấy quan hệ module từ code, nhưng **không trả về history của spans hay event counter**. Module entry span cho thấy lần thực thi được instrument, còn metric công bố không chứng minh listener đã xử lý thành công.

### 5.1. Metadata không tự động đồng nghĩa context propagation

Đây là ba khái niệm riêng:

1. **`Observation.Context`**: vùng chứa metadata và trạng thái của **một observation**.
2. **`Observation.Scope`**: cơ chế đánh dấu observation nào **đang active** trong đoạn code hiện tại để có quan hệ context và handler thích hợp.
3. **Distributed trace context**: trace ID/span ID và thông tin liên kết parent/sampling được truyền qua threads, HTTP hoặc messaging nếu có instrumentation.

Một `ModulithContext` chứa `module.identifier=inventory` không tự chứng minh listener đã nhận được **trace context của publisher**. Khi listener chạy bất đồng bộ, cần cơ chế truyền hoặc khôi phục context phù hợp, và phải kiểm tra parent/span ID trên backend.

## 6. Vòng đời observation và thời điểm metadata được sử dụng

Một operation thường đi qua chuỗi:

~~~mermaid
flowchart LR
    C["createNotStarted()"] --> S["start()"]
    S --> O["openScope()"]
    O --> X["chạy công việc"]
    X --> V["event() / error()<br/>khi phát sinh"]
    V --> Q["Scope.close()"]
    Q --> E["stop()"]
    E --> F["ObservationFilter"]
    F --> H["Handler.onStop()"]
~~~

Lưu ý: `event()` và `error()` chỉ được gọi khi có sự kiện/lỗi; chúng không bắt buộc với mọi observation. `Observation#observe(...)` có thể gói các thao tác start, scope, bắt lỗi và stop cho bạn.

- **`onStart`**: handler nhận context ở thời điểm start; thuộc tính được thêm muộn chưa chắc có ở giai đoạn này.
- **`onEvent`**: handler nhận event và context tại thời điểm event.
- **`onError`**: handler nhận lỗi đã ghi bằng `observation.error(...)`.
- **`onStop`**: handler đọc context sau khi các `ObservationFilter` được áp dụng.

Theo tài liệu Micrometer, một `DefaultMeterObservationHandler` có thể tạo **timer** khi observation stop; các low-cardinality key-values và error status ảnh hưởng metric đó. Nếu bật **long-task timer**, nó có thể được khởi tạo từ `onStart`, nên **nhãn thêm bằng filter ở onStop không nhất thiết có trên long-task timer**.

**Không dùng `ObservationFilter` như lời bảo đảm rằng mọi handler sẽ thấy key-value mới ngay từ đầu.** Vị trí thêm metadata trong lifecycle có thể ảnh hưởng tín hiệu được tạo.

## 7. Ví dụ Java: tạo observation nghiệp vụ có context

Mục tiêu: đo một operation **`inventory.reserve-stock`** trong module `inventory`, thêm nhãn module/operation ổn định, một khóa nội bộ phục vụ handler và ghi lỗi đúng cách.

Ví dụ này **tự tạo một business observation**. Nó không thay thế module entry observation do Spring Modulith tự instrument; nếu chạy trong scope của module entry span và có tracing, observation có thể xuất hiện như một span chi tiết bên trong.

~~~java
// com/example/shop/inventory/StockReservationService.java
package com.example.shop.inventory;

import io.micrometer.common.KeyValue;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import java.util.UUID;
import org.springframework.stereotype.Service;

@Service
public class StockReservationService {

    private final ObservationRegistry registry;

    public StockReservationService(ObservationRegistry registry) {
        this.registry = registry;
    }

    public void reserve(UUID orderId) {
        // Context là vùng chứa dữ liệu riêng của một observation.
        Observation.Context context = new Observation.Context()
                .put("stock.operation.stage", "reservation");

        context.addLowCardinalityKeyValue(
                KeyValue.of("app.module", "inventory"));
        context.addLowCardinalityKeyValue(
                KeyValue.of("business.operation", "reserve-stock"));

        Observation observation = Observation.createNotStarted(
                "shop.inventory.reserve-stock", () -> context, registry);

        // observe(...) quản lý start/scope/stop và ghi lỗi khi lambda ném exception.
        observation.observe(() -> {
            reserveInDatabase(orderId);
            observation.event(Observation.Event.of("stock.reserved"));
        });
    }

    private void reserveInDatabase(UUID orderId) {
        // Giả lập logic dự trữ tồn kho.
        // Một ứng dụng thật sẽ dùng repository và quy tắc idempotency.
    }
}
~~~

**Phân tích ví dụ:**

- `shop.inventory.reserve-stock` là **tên observation có tính ổn định**.
- `app.module=inventory` và `business.operation=reserve-stock` có tập giá trị nhỏ, phù hợp làm metric labels nếu handler metrics được bật.
- `stock.operation.stage` được lưu bằng `Context.put` để custom handler đọc; không tự trở thành metric label.
- `observation.event(...)` phát một sự kiện trong vòng đời observation. Nó **khác** `ApplicationEventPublisher.publishEvent(...)` của Spring và **không phải domain event của Spring Modulith**.
- `observe(...)` giúp tránh quên stop/scope khi code ném exception.

### 7.1. Tạo high-cardinality key-value trong lab

Nếu cần minh họa một giá trị riêng từng lượt chạy, có thể thêm:

~~~java
observation.highCardinalityKeyValue(
        "operation.run.id", UUID.randomUUID().toString());
~~~

Đây là một ID **giả lập cho mục đích học tập**. Nó không trở thành metric tag theo cách xử lý mặc định của Micrometer, nhưng có thể được ghi trên trace nếu tracer handler và exporter chấp nhận. Trong production, ưu tiên **trace ID** cho correlation thay vì tự tạo thêm ID trùng mục đích; tránh dùng định danh người dùng hay mã khách hàng.

### 7.2. Viết handler đọc context nội bộ

Nếu thực sự cần một hành động kỹ thuật khi observation kết thúc, có thể viết handler:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationHandler;

final class ReservationObservationHandler
        implements ObservationHandler<Observation.Context> {

    @Override
    public boolean supportsContext(Observation.Context context) {
        return "shop.inventory.reserve-stock".equals(context.getName());
    }

    @Override
    public void onStop(Observation.Context context) {
        String stage = context.get("stock.operation.stage");
        // Có thể dùng stage cho logic ghi nhận kỹ thuật có kiểm soát.
        // Tránh xuất dữ liệu bí mật hoặc tạo I/O nặng ở callback này.
    }
}
~~~

Handler cần được **đăng ký với `ObservationRegistry`** để nhận callback; chỉ khai báo class chưa khiến nó chạy. Trong một Spring Boot application, bạn có thể tích hợp handler qua cấu hình observation của ứng dụng; nếu tạo registry thủ công, dùng:

~~~java
ObservationRegistry registry = ObservationRegistry.create();
registry.observationConfig()
        .observationHandler(new ReservationObservationHandler());
~~~

Đây là ví dụ registry độc lập. Trong ứng dụng Spring Boot thực tế, nên dùng **registry đã được auto-configure** để các handlers/tracer/metrics của Boot vẫn hoạt động, thay vì tự tạo một registry thứ hai không có cấu hình hiện hành.

## 8. Tùy biến metadata của Spring Modulith bằng convention

Đây là điểm kết nối trực tiếp giữa **Observation API** và **Spring Modulith**.

Spring Modulith cho phép ứng dụng đăng ký một bean **`ModulithObservationConvention`** để tùy biến convention của các observation thuộc module. Interface này kế thừa `ObservationConvention<ModulithContext>` và cung cấp default methods:

- `supportsContext(Observation.Context)`: nhận diện observation có `ModulithContext`.
- `getName()`: tên observation dùng bởi instrumentation.
- `getContextualName(ModulithContext)`: tên có ngữ cảnh để hiển thị.
- `getLowCardinalityKeyValues(ModulithContext)`: tập key-values ít biến thể.
- `getHighCardinalityKeyValues(ModulithContext)`: tập key-values nhiều biến thể.

**Quy ước mặc định** ủy quyền đọc tên và các nhóm giá trị từ `ModulithContext`. Khi tùy biến, mục tiêu thường là **bổ sung** metadata mà không làm mất `module.identifier` hoặc những thuộc tính mặc định hữu ích cho truy vấn.

### 8.1. Ví dụ bổ sung nhãn ổn định

Giả sử mọi module của hệ thống đều thuộc miền sản phẩm `commerce` và bạn muốn thêm nhãn `app.domain=commerce` cho những **module observations**.

~~~java
// com/example/shop/config/ModulithObservationConfiguration.java
package com.example.shop.config;

import io.micrometer.common.KeyValue;
import io.micrometer.common.KeyValues;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.modulith.observability.ModulithContext;
import org.springframework.modulith.observability.ModulithObservationConvention;

@Configuration
class ModulithObservationConfiguration {

    @Bean
    ModulithObservationConvention modulithObservationConvention() {
        return new CommerceModulithConvention();
    }

    static final class CommerceModulithConvention
            implements ModulithObservationConvention {

        @Override
        public KeyValues getLowCardinalityKeyValues(ModulithContext context) {
            // Giữ key-values mặc định của Spring Modulith.
            return ModulithObservationConvention.super
                    .getLowCardinalityKeyValues(context)
                    .and(KeyValue.of("app.domain", "commerce"));
        }
    }
}
~~~

Nếu version Java/IDE của bạn không hỗ trợ lời gọi default interface ở định dạng xuống dòng như ví dụ, có thể viết liền `ModulithObservationConvention.super.getLowCardinalityKeyValues(context)`. Đây là phương thức Java hợp lệ, không phải phương thức static trên interface.

Điểm cần kiểm tra sau khi cấu hình:

1. Ứng dụng có đúng **một bean convention Modulith** được instrumentation lựa chọn.
2. Metadata `module.identifier`/`module.name` vẫn hiện diện như kỳ vọng trên các spans.
3. `app.domain` chỉ có tập giá trị hữu hạn (ở đây là một giá trị).
4. Không vô tình thay đổi tên observation mặc định, làm mất dashboard hoặc truy vấn đang dùng.

Đừng tùy tiện đổi `getName()` khi không có yêu cầu thiết kế. Tên observation ảnh hưởng tên metric/timer hoặc cách backend nhóm dữ liệu; thay đổi nó có thể làm đứt dashboard và cảnh báo hiện hành.

### 8.2. Dependency để compile custom convention

Tài liệu **Spring Modulith 2.2** chỉ rõ: nếu viết customizers/conventions sử dụng API observability của Modulith trong **source code**, cần khai báo **`spring-modulith-observability-api` ở compile scope**.

Ví dụ Gradle:

~~~gradle
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'

    // Runtime module actuator + observability instrumentation.
    runtimeOnly 'org.springframework.modulith:spring-modulith-starter-insight'

    // Có mã Java import ModulithContext/ModulithObservationConvention.
    implementation 'org.springframework.modulith:spring-modulith-observability-api'
}
~~~

Giả định dependency versions được quản lý bằng Spring Boot + Spring Modulith BOM tương thích. Nếu chưa có quản lý phiên bản, cần khai báo version phù hợp. Chỉ thêm `runtimeOnly starter-insight` mà không đưa API vào **compile classpath** có thể khiến source import `ModulithContext` không biên dịch được.

**Cẩn thận với phiên bản:** package/API nêu ở đây được xác minh ở Spring Modulith **2.2.0**. Tránh sao chép nguyên ví dụ từ nhánh khác mà không đối chiếu JavaDoc của phiên bản dự án.

## 9. Khi nào nên dùng `ObservationFilter`?

Nếu muốn bổ sung một nhãn **ngang qua nhiều loại observation**, `ObservationFilter` có thể được dùng. Ví dụ chỉ thêm nhãn cho những context thuộc Spring Modulith:

~~~java
package com.example.shop.config;

import io.micrometer.common.KeyValue;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationFilter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.modulith.observability.ModulithContext;

@Configuration
class ModuleObservationFilters {

    @Bean
    ObservationFilter moduleEnvironmentFilter() {
        return context -> {
            if (context instanceof ModulithContext) {
                context.addLowCardinalityKeyValue(
                        KeyValue.of("app.environment.class", "training"));
            }
            return context;
        };
    }
}
~~~

Ví dụ được giới hạn cho lab và dùng nhãn có tập giá trị nhỏ. Không nên hard-code giá trị `training` trong production nếu deployment không phải môi trường đào tạo.

**Chọn đúng công cụ:**

| Mục đích | API phù hợp |
| --- | --- |
| Đổi tên và key-values theo convention của riêng module observation | `ModulithObservationConvention` |
| Gắn nhãn với scope rộng hoặc điều kiện khác nhau trên toàn registry | `ObservationFilter` |
| Quyết định tạo observation thật hay no-op | `ObservationPredicate` |
| Thực hiện công việc khi start/stop/error/event | `ObservationHandler` |
| Giữ dữ liệu riêng của operation để handler dùng | `Observation.Context.put/get` |
| Thêm một operation nghiệp vụ con có duration riêng | `Observation.createNotStarted(...).observe(...)` |

**Giới hạn của filter:** Tài liệu Micrometer mô tả `ObservationFilter` chạy trước handler `onStop`. Nó không phải cách chắc chắn để gắn nhãn cho các thao tác xử lý ngay ở `onStart`. Nếu mục tiêu cần metadata có mặt từ lúc observation bắt đầu, hãy đưa thông tin vào context/convention ngay lúc tạo observation hoặc theo con đường được instrumentation hỗ trợ.

## 10. Bật observability và kiểm chứng metadata

Có hai phần tương đối độc lập:

- **Instrumentation Spring Modulith** để tạo observations ở module entry points và event publication metrics.
- **Micrometer Tracing / MeterRegistry / exporter** để chuyển metadata thành traces hoặc metrics có thể quan sát.

Ví dụ lab Spring Boot **4.x** và Spring Modulith **2.2** tương thích, có BOM:

~~~gradle
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.modulith:spring-modulith-observability-api'

    runtimeOnly 'org.springframework.modulith:spring-modulith-starter-insight'
    runtimeOnly 'org.springframework.boot:spring-boot-starter-opentelemetry'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
}
~~~

`application.yml` minh họa:

~~~yaml
spring:
  application:
    name: shop-modulith

management:
  endpoints:
    web:
      exposure:
        include: health,info,modulith,metrics,prometheus
  tracing:
    sampling:
      probability: 1.0
  opentelemetry:
    tracing:
      export:
        otlp:
          endpoint: http://localhost:4318/v1/traces
~~~

Giả định **OTLP/HTTP Collector** đang lắng nghe ở `localhost:4318` và forward traces tới backend. `sampling.probability: 1.0` chỉ nên dùng khi thực hành, để giảm khả năng request bị bỏ do sampling; production cần cấu hình theo lưu lượng và chi phí.

### 10.1. Quy trình đọc metadata đúng

1. Gọi một endpoint đi qua module `orders` và `payments`.
2. Trong trace backend, tìm module entry spans bằng `module.identifier` hoặc tên service.
3. Kiểm tra `module.name`, `module.method`, `module.invocation-type` và key-value mới `app.domain` nếu đã thêm convention.
4. Dùng `GET /actuator/modulith` để đối chiếu module names và dependencies ở **mức cấu trúc**.
5. Kích hoạt domain event và xem `GET /actuator/metrics/module.events.published` nếu muốn kiểm tra **publication counter**.
6. Đọc output `/actuator/prometheus` để xem tên metric và tags được export thực tế; đừng kỳ vọng mọi span attribute tự trở thành metric tag.
7. Với async listener, kiểm tra trace context và parent span trước khi kết luận event branch thuộc trace nào.

Ví dụ gọi Actuator:

~~~bash
curl -fsS http://localhost:8080/actuator/modulith
curl -fsS http://localhost:8080/actuator/metrics
curl -fsS http://localhost:8080/actuator/metrics/module.events.published
curl -fsS http://localhost:8080/actuator/prometheus
~~~

**Điểm kiểm chứng:** `/actuator/modulith` trả **module graph JSON**, không phải danh sách spans; `/actuator/metrics` trả **metrics**, không phải toàn bộ trace; muốn tìm module entry span và metadata của nó, cần **tracing backend**.

### 10.2. Ví dụ cách đọc một trace minh họa

~~~text
Trace abc... (minh họa)
└── HTTP POST /orders
    └── module entry span:
        module.identifier = orders
        module.invocation-type = bean
        module.method = placeOrder
        app.domain = commerce                  (custom)
        └── module entry span:
            module.identifier = payments
            module.invocation-type = bean
            module.method = charge
            app.domain = commerce              (custom)
~~~

Nếu `app.domain` không có, hãy kiểm tra convention bean đã thực sự được Spring Modulith lựa chọn chưa, bridge có xuất key-value này không, trace đã được sampling chưa và backend có hiển thị tất cả attributes không.

Không nên suy rằng module metadata vắng mặt trong một trace thì module chắc chắn chưa được gọi: còn phụ thuộc cách gọi Spring bean, instrumentation, sampling, exporter và đường thực thi.

## 11. Context propagation trong các tương tác bất đồng bộ

Giả sử `orders` phát `OrderPlaced` để `inventory` xử lý bằng `@ApplicationModuleListener` chạy trên executor khác. `orders` và `inventory` vẫn là hai module, mỗi entry span có **module metadata riêng**. Nhưng việc hai span có **cùng trace ID và quan hệ parent** hay không lại là vấn đề **context propagation**.

### 11.1. Không nhầm hai đối tượng mang tên context

| Ngữ cảnh | Mục đích | Hệ quả khi không truyền đúng |
| --- | --- | --- |
| `Observation.Context` của một operation | Giữ metadata/trạng thái cho observation đó | Handler có thể không thấy dữ liệu của operation nếu sử dụng sai context |
| Active `Observation.Scope` / tracing context | Xác định operation đang hoạt động và quan hệ trace/span | Span phía async có thể bị tách sang trace khác hoặc mất parent |
| `SecurityContext`, transaction context, MDC | Thông tin bảo mật, giao dịch và logging ở runtime | Có thể mất principal/log correlation hoặc thay đổi semantics; không được tự động giả định sẽ truyền cùng tracing |

Với Spring Boot hỗ trợ Micrometer Context Propagation, các executor và client có thể cần cấu hình để capture/restore context. Ví dụ với Boot 4.x khi ứng dụng dùng `AsyncTaskExecutor` được tự cấu hình:

~~~yaml
spring:
  task:
    execution:
      propagate-context: true
~~~

Với **executor tự tạo**, cần áp dụng `ContextPropagatingTaskDecorator` hoặc cơ chế tương đương theo tài liệu Spring Boot. Ngoài ra, sự kiện được xử lý sau transaction commit có thể được gắn lại ngữ cảnh theo cơ chế riêng. **Đừng coi một property là bảo đảm mọi listener và mọi transport giữ nguyên quan hệ trace**: hãy kiểm chứng trên trace thật.

Một listener ở trace khác có thể vẫn báo `module.identifier=inventory` vì **metadata module được nhận diện tại entry point của listener**, ngay cả khi trace context từ publisher không được nối tiếp.

## 12. Những lỗi thường gặp và cách giải thích

| Triệu chứng hoặc cách hiểu sai | Cách kiểm tra đúng |
| --- | --- |
| “`Observation.Context` giống `ApplicationContext`.” | Một cái giữ dữ liệu operation; cái kia quản lý Spring beans. |
| “`context.put(...)` sẽ tự tạo tag Prometheus.” | Cần low-cardinality key-values/convention và metrics handler; `put` là dữ liệu nội bộ. |
| “High-cardinality key-values cũng phải nằm trên mọi metric.” | Micrometer metrics handler mặc định dùng low-cardinality key-values; high-cardinality dành cho tracing tùy cấu hình. |
| “Có `module.identifier` là listener thành công.” | Metadata chỉ mô tả module; xem registry/logs/outcome để kết luận completion. |
| “Có `ModulithContext` thì chắc chắn có distributed trace.” | Cần tracer, exporter, sampling và operation thực tế được instrument. |
| “Một module có một span duy nhất.” | Một module có thể có nhiều entry invocations và nhiều spans trong một trace. |
| “`ObservationFilter` thêm tag ở onStop thì onStart cũng thấy.” | Metadata thêm muộn không bảo đảm có ở handler xử lý start/long-task timer. |
| “Đổi tên observation không ảnh hưởng dashboard.” | Tên và key-values có thể ảnh hưởng metric series và các truy vấn/alerts. |
| “Bật Actuator là bật trace exporter.” | Actuator chỉ expose endpoint được cấu hình; tracing cần riêng tracer/exporter/backend. |
| “Hai span có cùng module ID thì cùng một trace.” | Phải kiểm tra trace ID/span ID và quan hệ parent. |
| “Module graph mô tả số lần gọi qua module.” | Graph phản ánh dependency code; spans phản ánh những lần chạy được instrument. |
| “Mọi lỗi đều làm span `ERROR`.” | Còn tùy instrumentation, exception có thoát khỏi operation và được ghi bằng `error(...)` hay không. |

### 12.1. Chọn metadata theo mục đích

Một quy tắc thực tế:

- Để **lọc metric theo nhóm module**: dùng `module.identifier` hoặc một key-value ổn định có tập giá trị nhỏ.
- Để **phân tích một request**: dùng tracing với `module.method`, `module.invocation-type`, duration/status/exception và trace ID.
- Để **đối chiếu ranh giới kiến trúc**: dùng `ApplicationModules`, Documenter và `/actuator/modulith`.
- Để **đếm công bố domain events**: dùng `module.events.published` và các counters theo event type.
- Để **đo listener completion**: tham khảo Event Publication Registry và instrumentation theo outcome thực tế.
- Để **truyền trace qua async**: dùng context propagation phù hợp, không thêm một chuỗi tag mang trace ID vào low-cardinality metrics.

### 12.2. An toàn khi bổ sung metadata

Không ghi secret vào `ModulithContext`, exception message hoặc observation context chỉ vì “đây là dữ liệu nội bộ”. Dữ liệu có thể được chuyển sang tracing/logging exporters và đi tới hệ thống bên ngoài.

Hạn chế thay đổi đồng loạt các conventions ở production mà chưa kiểm tra tên metric, span attributes và dashboard hiện tại. Khi chuyển đổi cần đánh giá **backward compatibility** của tags và truy vấn cảnh báo.

## 13. Bài thực hành

### Bài 1 — Phân loại ba loại context

Cho các giá trị:

~~~text
A. Context.put("reservation.started", timestamp)
B. Observation.lowCardinalityKeyValue("app.module", "inventory")
C. Trace ID đang active trong async listener
D. ApplicationContext.getBean(OrderService.class)
~~~

Hãy xác định giá trị nào là dữ liệu nội bộ của observation, metric tag có thể sử dụng, tracing context và Spring container API. Giải thích vì sao chúng không thể thay thế cho nhau.

**Đáp án định hướng:** A là dữ liệu `Observation.Context`; B là low-cardinality key-value; C là trace context; D thuộc Spring ApplicationContext.

### Bài 2 — Xây observation nghiệp vụ

Viết một service `StockReservationService` inject `ObservationRegistry`; tạo observation `shop.inventory.reserve-stock`, thêm `app.module=inventory` và `outcome` với tập giá trị nhỏ. Gọi bằng `observe(...)`, phát một `Observation.Event` khi hoàn tất và thử ném exception.

**Gợi ý:** Dùng `Observation.createNotStarted(...).observe(...)`; quan sát cách handler nhận context và ghi lỗi. Tránh dùng `ApplicationEventPublisher.publishEvent(...)` khi chỉ muốn tạo **Observation Event**.

### Bài 3 — Chỉ ra key-values nào làm tăng cardinality

Danh sách: `module.identifier`, `module.invocation-type`, `operation`, `orderId`, `email`, `http.route`, `http.url`. Phân loại các nhãn nên là low, high, hoặc không nên ghi vì nhạy cảm. Đề xuất cách thay `orderId` bằng cơ chế correlation.

### Bài 4 — Tùy biến metadata Modulith

Tạo bean `ModulithObservationConvention` có `getLowCardinalityKeyValues(...)` bổ sung `app.domain=commerce` bằng `.and(KeyValue.of(...))`, giữ nguyên giá trị của default convention.

Sau đó gọi luồng `orders → payments`, xem module entry spans và xác nhận nhãn `app.domain` có mặt. Nếu nhãn thiếu, hãy tìm nguyên nhân từ: compile dependency API, bean registration, instrumentation, sampler, exporter hoặc backend.

### Bài 5 — Phân biệt tên và tính chất observation

Một nhóm đề xuất đổi `getName()` từ tên ổn định `modulith.module.entry` (minh họa) thành `orders.placeOrder.1234` cho mỗi request. Hãy giải thích tác hại của biến thể tên lớn đến metrics/dashboard và đề xuất thiết kế tốt hơn bằng tên ổn định + metadata riêng.

**Gợi ý:** Không lấy tên minh họa ở đây làm tên thực tế được Spring Modulith cam kết. Đọc tên observation từ instrumentation/backend của phiên bản đang dùng.

### Bài 6 — Context propagation

Gọi một `@ApplicationModuleListener` bất đồng bộ, ghi lại `traceId`/`parentSpanId` của span bên publisher và listener, cùng `module.identifier` ở từng bên. So sánh khi dùng executor có/không có cơ chế truyền context. Kết luận dựa trên dữ liệu thực tế, không mặc định metadata module tự lan truyền qua thread.

## 14. Tự kiểm tra

1. `Observation.Context` là đối tượng có vòng đời theo operation hay Spring container?
2. `ObservationHandler` đọc context ở những callback nào?
3. `ObservationRegistry` có phải trace backend hay không?
4. `context.put(...)` và `addLowCardinalityKeyValue(...)` khác nhau thế nào?
5. Vì sao `orderId` không nên là low-cardinality metric tag?
6. `ModulithContext` kế thừa lớp nào?
7. `getModule()` và `getInvocation()` cung cấp loại thông tin gì?
8. Bốn thuộc tính được tài liệu Spring Modulith liệt kê cho module entry span là gì?
9. `ModulithObservationConvention` có thể tùy chỉnh tên và loại key-values nào?
10. Vì sao `ObservationFilter` không bảo đảm thay đổi có mặt ở `onStart`?
11. Trường hợp nào cần thêm `spring-modulith-observability-api` ở compile scope?
12. Vì sao một module entry span có metadata chính xác nhưng vẫn có thể nằm trong trace khác với publisher?
13. Metrics `module.events.published` đo publication hay listener completion?
14. Vì sao nên kiểm tra cả module graph, event metrics và tracing khi kiểm chứng vận hành?

## 15. Ghi nhớ

**Observation.Context là nơi giữ metadata và trạng thái của một hoạt động được quan sát.** Spring Modulith dùng `ModulithContext` để gắn ngữ cảnh module/invocation, còn `ModulithObservationConvention` để chọn tên và key-values. Những thuộc tính như `module.identifier`, `module.invocation-type` và `module.method` giúp phân tích các **lần đi vào ranh giới module** trên trace.

**Low-cardinality metadata** phù hợp cho metrics; **high-cardinality metadata** có thể hữu ích trong tracing nhưng cần kiểm soát độ nhạy cảm/chi phí. **Context của observation** không thay thế **trace context propagation** khi xử lý bất đồng bộ.

Để kiểm chứng kiến trúc và vận hành, hãy kết hợp đúng nguồn: **module graph/Actuator** cho ranh giới cấu trúc, **event metrics** cho số lần publish, **module entry spans** cho đường chạy cụ thể, và **Event Publication Registry/logs** cho trạng thái xử lý listener khi cần.

### Tài liệu tham khảo

- [Spring Modulith 2.2 — Production-ready Features: observability, module entry span và conventions](https://docs.spring.io/spring-modulith/reference/production-ready.html).
- [Spring Modulith JavaDoc — `ModulithContext`](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/observability/ModulithContext.html).
- [Spring Modulith JavaDoc — `ModulithObservationConvention`](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/observability/ModulithObservationConvention.html).
- [Spring Modulith JavaDoc — `ObservedModule`](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/observability/ObservedModule.html).
- [Micrometer — Observation Components: Context, handlers, conventions, filters](https://docs.micrometer.io/micrometer/reference/observation/components.html).
- [Micrometer — Observation Introduction: lifecycle và cardinality](https://docs.micrometer.io/micrometer/reference/observation/introduction.html).
- [Spring Boot — Observability và context propagation](https://docs.spring.io/spring-boot/reference/actuator/observability.html).
- [Spring Boot — Tracing và exporters](https://docs.spring.io/spring-boot/reference/actuator/tracing.html).
