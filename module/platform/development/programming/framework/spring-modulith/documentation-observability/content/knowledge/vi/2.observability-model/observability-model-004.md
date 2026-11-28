# Module entry span như điểm bắt đầu của tương tác

Trong một ứng dụng **Spring Boot** được tổ chức bằng **Spring Modulith**, mỗi application module đại diện cho một phần nghiệp vụ có API và ranh giới phụ thuộc rõ ràng. Sơ đồ mô-đun mô tả cấu trúc dự kiến; còn **module entry span** cho biết một lệnh gọi đã thực sự đi vào mô-đun nào, ở phương thức nào và tại thời điểm nào khi ứng dụng đang chạy. Đây là một điểm quan sát hữu ích để đối chiếu kiến trúc với hành vi thực tế.

Bài học thuộc chương **Mô hình quan sát**, tập trung vào cách đọc module entry span, cách nó xuất hiện qua các tương tác đồng bộ và sự kiện, cùng những giới hạn cần nhớ khi phân tích trace.

## 1. Kết quả học tập

Sau bài này, bạn có thể:

1. Giải thích module entry span và phân biệt nó với HTTP server span, root span và span bên trong mô-đun.
2. Xác định những lời gọi nào có khả năng tạo module entry span và những lời gọi nào không.
3. Đọc các thuộc tính `module.identifier`, `module.name`, `module.invocation-type` và `module.method`.
4. Theo dõi đường đi từ một module sang module khác, kể cả khi giao tiếp bằng application event.
5. Thiết lập môi trường quan sát và sử dụng trace để kiểm chứng luồng tương tác ở mức ranh giới mô-đun.

## 2. Module entry span là gì?

Trong distributed tracing, **span** biểu diễn một đơn vị công việc có thời điểm bắt đầu, kết thúc, thời lượng, thuộc tính và mối quan hệ với span khác. Nhiều span có thể cùng thuộc một **trace**, được liên kết bằng trace ID và quan hệ parent–child khi ngữ cảnh tracing được truyền đúng.

**Module entry span** là span được tạo khi cơ chế observability của Spring Modulith nhận diện một lần đi vào **điểm truy cập (entry point)** của application module. Nó đánh dấu việc hệ thống bắt đầu xử lý tại ranh giới được quan sát của mô-đun, chẳng hạn:

- Một Spring bean thuộc API của module `orders` được module `checkout` gọi.
- Một Spring bean thuộc API của module `payment` được module `orders` gọi.
- Một application event listener thuộc module `inventory` được kích hoạt để xử lý sự kiện từ module khác.

Spring Modulith dùng cơ chế quan sát trên các Spring component được nhận diện ở API/entry point của module; các lời gọi được chặn qua interceptor để tạo observation và, khi có tracing phù hợp, tạo span. Điều này cho phép theo dõi **tương tác tại ranh giới mô-đun** mà không cần tự gắn span vào mọi phương thức nghiệp vụ.

**Phân biệt điểm dễ nhầm:** Từ “entry” chỉ **đầu vào của một module**, không khẳng định đây là span đầu tiên của toàn bộ request. Một HTTP request có thể có HTTP server span trước khi vào module; một module có thể gọi module khác khiến các module entry span lồng nhau; một listener bất đồng bộ có thể bắt đầu một trace độc lập nếu không có ngữ cảnh tracing liên kết.

### 2.1. So sánh các loại điểm quan sát

| Khái niệm | Điều nó biểu diễn | Ví dụ |
| --- | --- | --- |
| **Root span** | Điểm bắt đầu của một trace theo quan hệ parent–child | Span đầu tiên của một yêu cầu khi không nhận trace context từ bên ngoài |
| **HTTP server span** | Xử lý một HTTP request ở tầng web | `POST /orders` |
| **Module entry span** | Bắt đầu xử lý tại một entry point của application module | `orders: OrderService.placeOrder(...)` |
| **Span bên trong module** | Một thao tác kỹ thuật hay nghiệp vụ bên dưới | Truy vấn SQL, gọi HTTP tới hệ thống thanh toán |
| **Event publication metric** | Số lần ứng dụng công bố một loại sự kiện | `module.events.published` |

Một module entry span có thể là con của HTTP server span, con của module entry span khác, hoặc là điểm đầu tiên của một trace mới tùy cách luồng xử lý được kích hoạt và ngữ cảnh có được truyền hay không.

## 3. Từ kiến trúc tĩnh đến đường đi thực tế

Giả sử hệ thống bán hàng có các module:

- `web` nhận request và chuyển yêu cầu nghiệp vụ.
- `orders` tạo đơn hàng và phát sự kiện `OrderPlaced`.
- `payments` cung cấp thao tác thanh toán cho `orders`.
- `inventory` xử lý sự kiện đặt hàng để giữ tồn kho.

Quan hệ phụ thuộc ở mức thiết kế có thể mô tả là `web → orders → payments` và `orders → (OrderPlaced) → inventory`. Nhưng mô hình tĩnh chưa cho biết khi một request thực sự chạy thì phương thức nào được gọi, thời gian nằm ở bước nào, hoặc listener có thực sự thực thi không.

~~~mermaid
sequenceDiagram
    autonumber
    participant C as HTTP client
    participant W as Web
    participant O as Orders
    participant P as Payments
    participant E as Event publisher
    participant I as Inventory listener
    C->>W: POST /orders
    W->>O: placeOrder()
    Note over O: Module entry span: orders
    O->>P: charge()
    Note over P: Module entry span: payments
    P-->>O: Kết quả thanh toán
    O->>E: publishEvent(OrderPlaced)
    O-->>W: orderId
    E-->>I: on(OrderPlaced) (có thể async)
    Note over I: Module entry span: inventory
    W-->>C: HTTP response
~~~

Sơ đồ là **luồng xử lý logic**, không phải lời khẳng định rằng các span luôn có cùng trace ID. Nhánh `inventory` chạy bất đồng bộ cần được kiểm tra ngữ cảnh thực tế trước khi kết luận nó là span con của `orders`.

Trong trường hợp lệnh gọi bean đồng bộ trên cùng luồng, một trace thường có dạng khái niệm:

~~~text
Trace 8f... (minh họa)
└── HTTP POST /orders                    [HTTP server span]
    └── orders: placeOrder(...)          [module entry span]
        ├── payments: charge(...)        [module entry span]
        │   └── HTTP/DB thao tác ngoài    [span do thư viện khác tạo, nếu được instrument]
        └── publish OrderPlaced          [thao tác phát event]
~~~

Với `@ApplicationModuleListener` chạy bất đồng bộ, module `inventory` có thể xuất hiện dưới trace khác hoặc trong một nhánh trace có ngữ cảnh được khôi phục. Tên span trong ví dụ là cách diễn đạt để dễ đọc; **không dùng những tên minh họa này làm ràng buộc kiểm thử**. Khi kiểm chứng, hãy dựa vào tag `module.*` được ghi nhận thật.

## 4. Khi nào Spring Modulith tạo module entry span?

Spring Modulith nhận diện module từ cấu trúc application và các API/entry point của module. Khi bật hỗ trợ observability, nó dùng cơ chế dựa trên Spring bean để quan sát các lần truy cập vào những điểm đã được nhận diện.

### 4.1. Những trường hợp điển hình

| Tình huống | Cách diễn giải |
| --- | --- |
| Module A gọi một bean được module B công khai | Lần đi vào API của B có thể tạo entry span của B với kiểu `bean` |
| Application event được một listener của module B nhận | Khi listener được nhận diện và thực thi, có thể tạo entry span với kiểu `event listener` |
| Controller/handler là entry point được framework kích hoạt | Có thể là điểm quan sát đầu vào module tùy cấu trúc module và cơ chế nhận diện ở phiên bản đang dùng |
| Bean nội bộ của B gọi một bean nội bộ khác trong B | Không mặc nhiên tạo một entry span mới chỉ vì có thêm phương thức được gọi |
| Gọi phương thức nội bộ qua `this.method()` | Không nên kỳ vọng proxy/interceptor của Spring tạo một module entry span mới |
| Gọi trực tiếp một đối tượng tạo bằng `new` ngoài Spring container | Không được Spring bean instrumentation quan sát tự động |

**Điều kiện quan trọng:** Span chỉ hiện trong backend khi các thành phần phù hợp được instrument, cấu hình tracer/exporter đã hoạt động, trace được sampling và lời gọi thực sự chạy. “Không thấy span” chưa đủ để kết luận “không có tương tác”.

### 4.2. Bốn thuộc tính cần đọc

Tài liệu Spring Modulith công bố các tag của **Module Entry Span**:

| Tag | Ý nghĩa | Giá trị minh họa |
| --- | --- | --- |
| `module.identifier` | Mã định danh kỹ thuật của module | `orders` |
| `module.name` | Tên module dùng để hiển thị | `Orders` |
| `module.invocation-type` | Hình thức đi vào module | `bean` hoặc `event listener` |
| `module.method` | Phương thức được thực thi ở entry point | `placeOrder` hoặc tên phương thức tương ứng |

Nhờ các thuộc tính này, có thể trả lời: “Yêu cầu đã đi vào module nào?”, “Qua bean call hay event listener?”, “Phương thức entry nào đang tốn thời gian?”.

Không gán các giá trị có số lượng biến thể quá lớn như order ID, email, token hay dữ liệu cá nhân vào tag đo đạc. Khi cần liên hệ một giao dịch cụ thể, ưu tiên sử dụng trace ID và cơ chế log correlation phù hợp; không biến thông tin nhạy cảm thành nhãn metric.

## 5. Ví dụ Java: nhìn thấy một lần đi qua ranh giới module

Ví dụ sau mô tả mã rút gọn của một ứng dụng Spring Boot có base package `com.example.shop`. Các package con `orders`, `payments`, `inventory` và `web` được dùng như các module ở mức khái niệm. Đoạn mã minh họa điểm giao tiếp; phần gọi cổng thanh toán và lưu dữ liệu thực tế được lược bỏ.

**API công khai của module thanh toán:**

~~~java
// com/example/shop/payments/PaymentService.java
package com.example.shop.payments;

import java.math.BigDecimal;
import java.util.UUID;
import org.springframework.stereotype.Service;

@Service
public class PaymentService {

    public void charge(UUID orderId, BigDecimal amount) {
        // Minh họa: gọi cổng thanh toán hoặc cập nhật trạng thái.
    }
}
~~~

**Sự kiện nghiệp vụ do module đơn hàng công bố:**

~~~java
// com/example/shop/orders/OrderPlaced.java
package com.example.shop.orders;

import java.util.UUID;

public record OrderPlaced(UUID orderId) {}
~~~

**API module đơn hàng gọi sang thanh toán và phát sự kiện:**

~~~java
// com/example/shop/orders/OrderService.java
package com.example.shop.orders;

import com.example.shop.payments.PaymentService;
import java.math.BigDecimal;
import java.util.UUID;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {

    private final PaymentService payments;
    private final ApplicationEventPublisher events;

    public OrderService(PaymentService payments,
                        ApplicationEventPublisher events) {
        this.payments = payments;
        this.events = events;
    }

    @Transactional
    public UUID placeOrder(BigDecimal amount) {
        UUID orderId = UUID.randomUUID();
        payments.charge(orderId, amount);
        events.publishEvent(new OrderPlaced(orderId));
        return orderId;
    }
}
~~~

**Module inventory nhận sự kiện:**

~~~java
// com/example/shop/inventory/OrderPlacedHandler.java
package com.example.shop.inventory;

import com.example.shop.orders.OrderPlaced;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class OrderPlacedHandler {

    @ApplicationModuleListener
    void on(OrderPlaced event) {
        // Minh họa: giữ hàng, cập nhật tồn kho.
    }
}
~~~

Một controller trong `web` gọi `OrderService.placeOrder(...)`. Nếu tracing được cấu hình và hai service được nhận diện ở API của module, phần lời gọi đồng bộ có thể tạo các entry span tương ứng với `orders` và `payments`. `@ApplicationModuleListener` là lối viết gọn của listener giao dịch chạy bất đồng bộ và trong giao dịch riêng. Sự kiện được xử lý sau khi giao dịch nguồn commit thành công; khi đó bạn kiểm tra span của `inventory` riêng theo ngữ cảnh tracing thực tế.

> **Phạm vi ví dụ:** Trong hệ thống thật, không nên coi một thao tác thanh toán bên ngoài là có thể rollback chỉ vì phương thức gọi được đánh dấu `@Transactional`. Thiết kế giao dịch và xử lý lỗi nghiệp vụ cần được giải quyết độc lập với instrumentation.

## 6. Bật observability để xuất module entry span

Để quan sát được, cần **hai lớp**:

1. **Spring Modulith observability** nhận biết và instrument tương tác ở ranh giới module.
2. **Micrometer Tracing + tracer/exporter + backend** đưa dữ liệu span tới công cụ như Grafana Tempo, Jaeger hoặc Zipkin qua cấu hình phù hợp.

Ví dụ cấu hình **Gradle cho một ứng dụng Spring Boot 4.2 / Spring Modulith 2.2**, với phiên bản được quản lý qua BOM hoặc dependency management tương thích:

~~~gradle
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-opentelemetry'
    runtimeOnly 'org.springframework.modulith:spring-modulith-starter-insight'
}
~~~

`spring-modulith-starter-insight` tích hợp hỗ trợ **Actuator** và **observability** của Modulith; `spring-boot-starter-opentelemetry` cung cấp đường đi tracing/OTLP trong nhóm phiên bản Spring Boot nêu trên. Nếu dự án dùng phiên bản khác, phải đối chiếu artifact và cấu hình của chính phiên bản đó: chẳng hạn artifact observability được tách thành `spring-modulith-observability-core` ở nhánh mới, trong khi các nhánh cũ dùng tên `spring-modulith-observability`.

Ví dụ `application.yml` dành cho môi trường thực hành với OTLP/HTTP collector ở máy cục bộ:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,modulith,metrics
  tracing:
    sampling:
      probability: 1.0
  opentelemetry:
    tracing:
      export:
        otlp:
          endpoint: http://localhost:4318/v1/traces
~~~

Mức sampling `1.0` chỉ phù hợp để dễ kiểm chứng trong môi trường học/lab; trong production cần chọn tỷ lệ theo tải, chi phí và yêu cầu quan sát. Cấu hình endpoint trên giả định đã có OTLP collector nhận HTTP tại cổng 4318; nếu chưa chạy backend/collector hoặc cấu hình exporter sai thì span có thể được tạo nhưng không xuất hiện ở giao diện tracing.

### 6.1. Các bước kiểm chứng

1. Khởi chạy ứng dụng và backend nhận trace, xác nhận cấu hình xuất span hoạt động.
2. Gọi endpoint nghiệp vụ thực sự đi qua `web → orders → payments`.
3. Mở một trace của request, tìm các span có tag `module.identifier=orders` và `module.identifier=payments`.
4. Kiểm tra `module.invocation-type` tương ứng với lần gọi bean; so sánh thời điểm, độ dài và quan hệ parent–child của chúng.
5. Theo dõi event `OrderPlaced` và tìm listener của `inventory`. Nếu không cùng trace ID, kiểm tra luồng bất đồng bộ và context propagation trước khi kết luận listener không chạy.
6. Nếu cần đối chiếu cấu trúc tĩnh, truy cập `GET /actuator/modulith` (khi actuator đã bật và endpoint được phép truy cập) để xem dependency graph mà Modulith nhận diện.

**Kết quả mong đợi:** Có bằng chứng runtime cho các lần đi vào module ở luồng thực sự đã chạy. Không cần và không nên đòi hỏi mọi lệnh gọi nội bộ phải có module entry span.

## 7. Đồng bộ, bất đồng bộ và context propagation

Quan hệ cha–con giữa các span dựa vào **trace context**, không dựa vào việc hai module nằm cạnh nhau trong module graph.

| Luồng thực thi | Điều thường quan sát được | Cần kiểm tra |
| --- | --- | --- |
| Bean call đồng bộ qua module A → B | Span của B thường nằm dưới context đang hoạt động của A | Bean có được instrument không? Sampling có bật không? |
| `@EventListener` đồng bộ | Listener có thể tiếp tục dùng context của luồng phát event | Listener có thực thi và được nhận diện không? |
| `@ApplicationModuleListener` bất đồng bộ | Listener chạy luồng/giao dịch khác; quan hệ trace phụ thuộc context được truyền | Task executor và context propagation đã cấu hình chưa? |
| Gọi dịch vụ ngoài bằng HTTP/messaging | Cần truyền trace context qua giao thức/headers nếu muốn nối trace | Client và consumer có tracing instrumentation tương thích không? |

Trong Spring Boot 4.2, khi dùng `@Async` với `AsyncTaskExecutor` được tự động cấu hình, có thể bật truyền ngữ cảnh bằng:

~~~yaml
spring:
  task:
    execution:
      propagate-context: true
~~~

Nếu tự tạo `AsyncTaskExecutor`, hãy cấu hình `ContextPropagatingTaskDecorator` cho executor đó theo tài liệu Spring Boot. Các cơ chế này giúp truyền observation context qua thread, nhưng cần kiểm tra cả thời điểm publish/commit, cách listener được gọi và backend tracing trước khi nhận định tất cả span của xử lý event chắc chắn chung một trace. Không nên tự suy quan hệ nhân quả chỉ từ thứ tự thời gian trên giao diện.

**Quan trọng:** `module.identifier` là thuộc tính mô tả module của span; `traceId` là định danh chuỗi quan sát. Hai giá trị giải quyết hai câu hỏi khác nhau: “đang ở module nào?” và “những bước nào thuộc cùng một trace?”.

## 8. Đối chiếu với metric và module graph

Module entry span trả lời câu hỏi **một lần tương tác cụ thể diễn ra như thế nào**. Các tín hiệu khác bổ sung góc nhìn:

| Dữ liệu | Câu hỏi phù hợp | Giới hạn |
| --- | --- | --- |
| Module entry spans | Module nào được gọi, bằng đường nào, thời lượng bao lâu? | Chỉ thấy lời gọi đã instrument và được lấy mẫu/xuất thành công |
| `module.events.published` | Có bao nhiêu domain event được công bố? | Số lần công bố không đồng nghĩa số lần listener xử lý thành công |
| `module.events.published.<moduleIdentifier>.<SimpleEventTypeName>` | Một loại event cụ thể được công bố bao nhiêu lần? | Không thay thế trace của từng lần xử lý |
| `/actuator/modulith` | Các module và dependency mà ứng dụng nhận diện là gì? | Cấu trúc được nhận diện, không phải luồng thực thi của từng request |
| Application logs có trace ID | Khi phát sinh lỗi, dòng log nào liên quan đến trace? | Log thiếu correlation hoặc bị lọc có thể khiến thông tin đứt đoạn |

Từ đó có thể kiểm chứng một giả thuyết kiến trúc như: “Tạo đơn hàng phải đi qua `orders` rồi `payments`, sau đó công bố `OrderPlaced`”. Dùng module graph để biết quan hệ được khai báo, trace để thấy phần chạy đồng bộ, event metric để biết sự kiện đã được publish, và quan sát listener để xác nhận bước xử lý cuối.

Tuy vậy, một trace **không chứng minh toàn bộ hệ thống tuân thủ ranh giới module**. Muốn phát hiện dependency bị cấm hoặc tham chiếu sai API, vẫn cần kiểm thử kiến trúc bằng cơ chế verify của Spring Modulith. Tracing cung cấp bằng chứng vận hành bổ sung, không thay thế xác minh cấu trúc.

## 9. Tình huống phân tích trace thực tế

**Tình huống A — Thanh toán chậm:** Một request mất 900 ms; module entry span `orders` dài khoảng 850 ms, bên trong span `payments` dài 720 ms. Điều này gợi ý phần lớn thời gian của `orders` đang nằm ở bước thanh toán. Tiếp tục xem HTTP client/database spans của `payments` để xác định nguyên nhân; không quy toàn bộ 850 ms cho code nội bộ `orders`.

**Tình huống B — Có event nhưng không thấy inventory:** Metric `module.events.published` tăng, nhưng không tìm thấy span listener `inventory` trong trace của request. Các khả năng gồm listener xử lý bất đồng bộ ở trace khác, thiếu propagation, trace bị sampling, exporter lỗi hoặc listener chưa chạy. Kiểm tra event publication registry/logs và truy vấn trace theo thời gian, service, module trước khi kết luận event bị mất.

**Tình huống C — Không thấy span cho một helper method:** `PaymentService.charge()` gọi một helper nội bộ trong cùng module, nhưng giao diện chỉ có entry span `payments`. Đây có thể là hành vi đúng vì helper không phải điểm đi vào module. Nếu cần đo riêng helper, dùng một observation nghiệp vụ có chủ đích; không mở rộng mọi method thành module entry span.

**Tình huống D — Hai entry span cùng module:** Một endpoint gọi hai API riêng của `orders` hoặc nhiều lần gọi qua các entry point được instrument. Có thể có nhiều span cùng `module.identifier=orders`. Hãy đọc phương thức, parent span và timestamp để phân biệt, không mặc định mỗi request chỉ có một span cho mỗi module.

## 10. Những lỗi diễn giải thường gặp

| Cách hiểu sai | Cách hiểu đúng |
| --- | --- |
| “Module entry span luôn là root của toàn hệ thống.” | Nó là điểm vào ranh giới **module**; root trace có thể ở HTTP server hoặc nơi khác. |
| “Không có entry span nghĩa là module không hề được gọi.” | Trước tiên kiểm tra instrumentation, exposure, sampling, exporter và cách gọi. |
| “Mọi method của mỗi service đều có entry span.” | Cơ chế tập trung vào điểm truy cập module được nhận diện, không tự động bao phủ toàn bộ method nội bộ. |
| “Event đã publish thì listener chắc chắn thành công.” | Publication và completion là hai giai đoạn khác nhau. |
| “Các span có tag module giống nhau đều chung một request.” | Phải dựa vào trace ID, span ID và quan hệ parent–child. |
| “Span dài đồng nghĩa CPU trong module cao.” | Thời gian span có thể bao gồm chờ I/O hoặc lời gọi module khác. |

## 11. Bài thực hành tự kiểm tra

**Bài 1 — Tìm điểm bắt đầu thực sự.** Vẽ một trace gồm `HTTP POST /orders`, `orders.placeOrder` và `payments.charge`. Chỉ rõ root span của trace và hai module entry span. Giải thích vì sao chúng không phải cùng một khái niệm.

**Bài 2 — Phân loại thuộc tính.** Với span có `module.identifier=inventory`, `module.invocation-type=event listener` và `module.method=on`, trả lời đây là dấu hiệu tương tác theo bean call hay event listener. Liệu chỉ riêng span này có chứng minh event đã xử lý thành công không?

**Bài 3 — Kiểm tra luồng async.** Tắt rồi bật `spring.task.execution.propagate-context` trong một ứng dụng lab đang dùng executor tự động cấu hình, gọi lại cùng luồng nghiệp vụ và so sánh trace ID/parent ID của listener. Ghi lại kết quả thực tế; không mặc định môi trường của bạn nhất thiết tạo quan hệ giống ví dụ.

**Bài 4 — So sánh kiến trúc với vận hành.** Xem `/actuator/modulith` và ít nhất một trace đã xuất. Liệt kê một dependency được nhìn thấy cả ở mô hình module lẫn runtime, cùng một dependency không xuất hiện trong trace vừa xem. Giải thích vì sao một trace đơn lẻ không thể phủ hết module graph.

### Câu hỏi ôn tập

1. Module entry span đánh dấu **điểm vào của cái gì**?
2. Vì sao span `payments` có thể là con của span `orders` trong một lời gọi đồng bộ?
3. Tại sao listener `@ApplicationModuleListener` có thể nằm ở trace khác?
4. Khi không thấy module entry span, bạn cần kiểm tra những điều kiện kỹ thuật nào trước?
5. Vì sao nên kết hợp span, event metrics, actuator và kiểm thử kiến trúc?

## 12. Ghi nhớ

**Module entry span là dấu mốc quan sát tại ranh giới application module.** Nó cho thấy một tương tác đã đi vào module qua entry point nào, theo hình thức nào và mất bao lâu. Trong một modular monolith, các dấu mốc này giúp nối **module graph** (kiến trúc dự kiến) với **traces và metrics** (hành vi runtime). Đọc chúng cùng trace context, đặc biệt khi có event bất đồng bộ, để tránh nhầm “điểm bắt đầu tương tác với module” thành “điểm bắt đầu của toàn bộ trace”.

### Tài liệu tham khảo

- [Spring Modulith — Production-ready Features: Observing Application Modules, Module Entry Span và Observability Metrics](https://docs.spring.io/spring-modulith/reference/production-ready.html).
- [Spring Modulith — Fundamentals: Application Modules](https://docs.spring.io/spring-modulith/reference/fundamentals.html).
- [Spring Modulith — Working with Application Events](https://docs.spring.io/spring-modulith/reference/events.html).
- [Spring Boot — Observability và Context Propagation](https://docs.spring.io/spring-boot/reference/actuator/observability.html).
- [Spring Boot — Tracing, exporter và sampling](https://docs.spring.io/spring-boot/reference/actuator/tracing.html).
