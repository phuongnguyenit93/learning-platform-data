# Dependency type USES_COMPONENT

Trong **module graph** của Spring Modulith, một mũi tên giữa hai application module không chỉ nói rằng chúng “có liên quan”. Loại dependency giải thích **chúng liên quan bằng cơ chế nào**. `USES_COMPONENT` là loại quan hệ đặc biệt đáng chú ý vì nó thể hiện một module **cần sử dụng Spring component (bean) của module khác** để hoạt động.

Bài học này thuộc chương **Module graph**, trong mô-đun **SPRING_MODULITH_DOCUMENTATION_OBSERVABILITY**. Trong phạm vi học Spring Modulith để sinh tài liệu ranh giới application module và quan sát tương tác trong Spring Boot, ta sẽ học cách nhận diện `USES_COMPONENT` trong code, đọc đúng chiều mũi tên, lọc quan hệ trên sơ đồ, đối chiếu qua Actuator, và kết hợp với tracing/metrics khi cần kiểm chứng hành vi lúc chạy.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Nêu được định nghĩa `DependencyType.USES_COMPONENT` theo mô hình dependency của Spring Modulith.
2. Nhận ra tình huống một bean thuộc module A phụ thuộc vào bean của module B.
3. Phân biệt `USES_COMPONENT` với `DEFAULT`, `EVENT_LISTENER` và các phân loại khác trong phiên bản đang dùng.
4. Đọc đúng một cạnh `orders → payments`: module **orders phụ thuộc payments**, không phải ngược lại.
5. Sinh diagram chỉ hiển thị các quan hệ `USES_COMPONENT` bằng `Documenter.DiagramOptions`.
6. Đọc và lọc `USES_COMPONENT` trong JSON từ `/actuator/modulith`.
7. Giải thích vì sao dependency graph không đồng nghĩa với runtime call graph hay distributed trace.

## 2. `USES_COMPONENT` có nghĩa chính xác là gì?

Spring Modulith biểu diễn quan hệ giữa các module bằng `ApplicationModuleDependency`, được phân loại theo `DependencyType`. Theo JavaDoc chính thức, `USES_COMPONENT` có nghĩa là module nguồn phụ thuộc module đích qua một **component dependency**; về mặt mô hình, **module đích cần được bootstrap để module nguồn chạy được**.

Diễn đạt bằng hai module:

~~~text
orders                         payments
  │                               ▲
  └────── USES_COMPONENT ─────────┘

Nguồn (source)                  Đích (target)
orders phụ thuộc payments vì cần một Spring bean do payments cung cấp.
~~~

Ở dạng ký hiệu:

**`A --USES_COMPONENT--> B`** nghĩa là **A sử dụng component của B**, từ đó A có phụ thuộc kiểu component vào B. Quan hệ này thuộc **kiến trúc được nhận diện từ mã ứng dụng**; nó không đếm số lần A gọi B, cũng không mô tả một request cụ thể.

### 2.1. “Component” được hiểu như thế nào?

Trong ngữ cảnh Spring, component là một đối tượng thuộc Spring container; ví dụ các Spring bean được nhận diện từ `@Component`, `@Service`, `@Repository`, `@Controller` hoặc được đăng ký theo cơ chế cấu hình bean. Trường hợp điển hình là **constructor injection**: một service thuộc module `orders` yêu cầu một service thuộc module `payments`.

Đừng hiểu `USES_COMPONENT` theo nghĩa “một module có tạo đối tượng `new` từ class của module khác” hoặc “đã có HTTP call thành công”. Spring Modulith phân loại một **quan hệ phụ thuộc mã nguồn/component** được nhận diện theo khả năng của phiên bản thư viện; không phải mọi cách lấy bean động hay cơ chế runtime phức tạp đều nhất thiết thể hiện đầy đủ trên module graph.

### 2.2. Tại sao “cần bootstrap” lại quan trọng?

Nếu bean ở `orders` được inject bean ở `payments`, ứng dụng thường phải cung cấp được bean thanh toán trong Spring context để tạo và sử dụng bean đơn hàng. Đây là dấu hiệu của **coupling ở tầng khởi tạo/chạy ứng dụng**: `orders` chưa hoàn toàn độc lập với `payments`.

Điều đó **không đồng nghĩa** với khẳng định Spring khởi tạo mọi bean của `payments` trước mọi bean của `orders` trong mọi cấu hình, bởi lazy initialization, proxy, provider hoặc cơ chế đăng ký bean có thể thay đổi chi tiết thời điểm khởi tạo. Mục đích của loại dependency là thể hiện **nhu cầu đối với component của module đích**.

## 3. Ví dụ Java: constructor injection tạo quan hệ `USES_COMPONENT`

Giả sử ứng dụng Spring Boot có base package `com.example.shop`, với ba module theo package: `orders`, `payments`, `inventory`.

~~~text
com.example.shop
├── ShopApplication.java
├── orders/
│   ├── OrderService.java
│   └── OrderPlaced.java
├── payments/
│   └── PaymentService.java
└── inventory/
    └── InventoryListener.java
~~~

### 3.1. Module `payments` công khai một Spring bean

~~~java
// com/example/shop/payments/PaymentService.java
package com.example.shop.payments;

import java.math.BigDecimal;
import java.util.UUID;
import org.springframework.stereotype.Service;

@Service
public class PaymentService {

    public void charge(UUID orderId, BigDecimal amount) {
        // Mã minh họa: thực hiện thanh toán qua cổng bên ngoài.
    }
}
~~~

`PaymentService` đặt ở package gốc `payments`, tức API package theo cách tổ chức module mặc định. Đây là một ví dụ rõ ràng về component có thể được module khác sử dụng.

### 3.2. Module `orders` yêu cầu bean từ `payments`

~~~java
// com/example/shop/orders/OrderService.java
package com.example.shop.orders;

import com.example.shop.payments.PaymentService;
import java.math.BigDecimal;
import java.util.UUID;
import org.springframework.stereotype.Service;

@Service
public class OrderService {

    private final PaymentService paymentService;

    public OrderService(PaymentService paymentService) {
        this.paymentService = paymentService;
    }

    public UUID placeOrder(BigDecimal total) {
        UUID id = UUID.randomUUID();
        paymentService.charge(id, total);
        return id;
    }
}
~~~

Nhìn vào code:

1. `OrderService` là bean thuộc module **`orders`**.
2. Constructor của nó yêu cầu `PaymentService` là bean thuộc module **`payments`**.
3. Spring container cung cấp bean `PaymentService` khi tạo `OrderService` theo cấu hình thông thường.
4. Module graph có thể ghi nhận **`orders → payments`** với loại `USES_COMPONENT`.

~~~mermaid
flowchart LR
    subgraph ORD["Application module: orders"]
        OS["OrderService<br/>@Service"]
    end
    subgraph PAY["Application module: payments"]
        PS["PaymentService<br/>@Service"]
    end
    OS -->|"constructor injection<br/>USES_COMPONENT"| PS
~~~

**Mũi tên thể hiện ai phụ thuộc ai.** Mặc dù `payments` có thể trả kết quả về `orders` khi chạy, quan hệ dependency vẫn được mô tả theo chiều **`orders → payments`**.

### 3.3. Cần phân biệt lúc khởi tạo và lúc thực thi

Code trên có **hai sự kiện khác nhau**:

- Lúc Spring khởi tạo `OrderService`, container cần giải quyết dependency vào `PaymentService`.
- Lúc `placeOrder(...)` chạy, code gọi `paymentService.charge(...)`.

**`USES_COMPONENT` phản ánh loại quan hệ component**; nó không xác nhận `charge(...)` đã chạy, đã thành công, gọi bao nhiêu lần hay mất bao lâu. Muốn biết lần chạy cụ thể, cần test nghiệp vụ, metrics, logs hoặc tracing.

## 4. `USES_COMPONENT` khác gì những dependency type khác?

Spring Modulith có nhiều kiểu phụ thuộc. Trong tài liệu **Application Module Actuator**, các kiểu phổ biến được mô tả gồm `DEFAULT`, `USES_COMPONENT` và `EVENT_LISTENER`. JavaDoc `DependencyType` của những phiên bản mới còn có `ENTITY`, dùng khi module tham chiếu entity của module khác. Luôn đối chiếu API và tài liệu với phiên bản dự án thực tế.

| Kiểu | Ý nghĩa chính | Ví dụ | Có chứng minh lời gọi runtime đã xảy ra? |
| --- | --- | --- | --- |
| `DEFAULT` | Phụ thuộc mã nguồn/type thông thường | `orders` tham chiếu một record, interface hoặc type công khai từ module khác mà không tạo quan hệ bean tương ứng | Không |
| **`USES_COMPONENT`** | Module nguồn phụ thuộc Spring component của module đích | `orders.OrderService` inject `payments.PaymentService` | Không |
| `EVENT_LISTENER` | Module nguồn khai báo listener cho event từ module đích | `inventory` nhận `orders.OrderPlaced` | Không |
| `ENTITY` (nếu có trong phiên bản API) | Module nguồn tham chiếu entity thuộc module khác | `reporting` trực tiếp tham chiếu entity `orders` | Không |

Bảng trên phân loại **bản chất mối quan hệ**, không phải mức độ quan trọng hay thứ tự ưu tiên. Cùng một cặp module có thể có **nhiều loại dependency**.

### 4.1. Một ví dụ `EVENT_LISTENER` để tránh nhầm

Giả sử `orders` công bố một event:

~~~java
// com/example/shop/orders/OrderPlaced.java
package com.example.shop.orders;

import java.util.UUID;

public record OrderPlaced(UUID orderId) {}
~~~

Và `inventory` nhận event:

~~~java
// com/example/shop/inventory/InventoryListener.java
package com.example.shop.inventory;

import com.example.shop.orders.OrderPlaced;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
class InventoryListener {

    @EventListener
    void on(OrderPlaced event) {
        // Cập nhật hoặc giữ hàng trong kho.
    }
}
~~~

Về **phụ thuộc code**, module `inventory` tham chiếu type `OrderPlaced` do `orders` công khai. Quan hệ có thể được nhận diện là:

~~~text
inventory --EVENT_LISTENER--> orders
~~~

Trong khi đó, **luồng event** khi chạy được diễn đạt theo hướng:

~~~text
orders --publish OrderPlaced--> inventory listener
~~~

Hai chiều này không mâu thuẫn: đồ thị dependency mô tả **ai cần biết API/type của ai**, còn sơ đồ sự kiện mô tả **ai phát tín hiệu và ai tiếp nhận**. `EVENT_LISTENER` tự thân không có ý nghĩa “module đích phải bootstrap để module nguồn xử lý như với component dependency”.

Nếu `InventoryListener` đồng thời inject một service của `orders`, cùng cặp module **có thể** xuất hiện thêm `USES_COMPONENT`. Khi đó không được gộp mọi quan hệ thành “event only”.

### 4.2. `DEFAULT` không có nghĩa “không quan trọng”

Một module có thể chỉ tham chiếu type công khai của module khác mà không yêu cầu một Spring bean từ module đích. Quan hệ loại `DEFAULT` vẫn quan trọng cho phân tích coupling và boundary, nhưng **không tự thể hiện nhu cầu bootstrap Spring component** như `USES_COMPONENT`.

## 5. Module graph biểu diễn `USES_COMPONENT` như thế nào?

Xét mô hình minh họa:

~~~mermaid
flowchart LR
    O["orders"]
    P["payments"]
    I["inventory"]
    C["catalog"]
    O -->|"USES_COMPONENT"| P
    I -->|"EVENT_LISTENER"| O
    O -.->|"DEFAULT"| C
~~~

Ở đây:

- `orders → payments`: **component dependency** từ service đơn hàng đến bean thanh toán.
- `inventory → orders`: listener phụ thuộc event API của orders.
- `orders → catalog`: giả định một quan hệ type thông thường.

Nếu cần đánh giá **mức độ phụ thuộc Spring bean trực tiếp** giữa các module, chỉ xét cạnh `USES_COMPONENT`. Nếu cần đánh giá **tất cả phụ thuộc cấu trúc**, phải xét cả các loại còn lại.

### 5.1. Tập các câu hỏi mà cạnh này trả lời

Từ `orders --USES_COMPONENT--> payments`, ta có thể hỏi:

- Khi tách `payments` thành module/dịch vụ độc lập, API bean nào đang được `orders` inject?
- Khi viết application-module test chỉ khởi tạo `orders`, có phải cung cấp bean/stub từ `payments` hay không?
- Một thay đổi đối với API component của `payments` có thể ảnh hưởng module nào?
- Có tình trạng quá nhiều module khác nhau đều inject trực tiếp bean của `payments` không?
- Những dependency nào nên được thay bằng event hoặc một API trừu tượng hơn, **nếu yêu cầu nghiệp vụ cho phép**?

`USES_COMPONENT` giúp *đặt câu hỏi về coupling*. Nó không tự quyết định một quan hệ là tốt hay xấu: gọi đồng bộ qua module là hợp lệ trong nhiều modular monolith.

## 6. Sinh sơ đồ chỉ hiển thị `USES_COMPONENT` với `Documenter`

Spring Modulith có `Documenter` để sinh module graph ở dạng component diagram, phục vụ tài liệu kiến trúc. API `Documenter.DiagramOptions.withDependencyTypes(DependencyType... types)` cho phép chọn những loại dependency sẽ xuất hiện trong sơ đồ.

Ví dụ một **JUnit test** sinh riêng module graph của các component dependency:

~~~java
package com.example.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;
import org.springframework.modulith.core.DependencyType;
import org.springframework.modulith.docs.Documenter;
import org.springframework.modulith.docs.Documenter.DiagramOptions;

class ModuleGraphDocumentationTests {

    @Test
    void documentsComponentDependencies() {
        ApplicationModules modules =
                ApplicationModules.of(ShopApplication.class);

        DiagramOptions onlyComponentDependencies = DiagramOptions.defaults()
                .withDependencyTypes(DependencyType.USES_COMPONENT);

        new Documenter(modules)
                .writeModulesAsPlantUml(onlyComponentDependencies);
    }
}
~~~

Đây là API cho **sinh tài liệu trong test/build**, không phải API trả về runtime trace. Với Gradle, cần các dependency test tương thích, ví dụ:

~~~gradle
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.modulith:spring-modulith-starter-test'
}
~~~

Giả định ứng dụng đã quản lý version Spring Boot và Spring Modulith bằng BOM hoặc dependency management tương thích. `spring-modulith-starter-test` bao gồm hỗ trợ documentation trong dòng phiên bản được mô tả ở Spring Modulith Appendix; nếu dự án dùng cấu trúc dependency riêng, có thể phụ thuộc trực tiếp vào `spring-modulith-docs` ở test scope.

### 6.1. Cách đọc kết quả

Nếu graph tổng thể có ba cạnh:

~~~text
orders    --USES_COMPONENT--> payments
inventory --EVENT_LISTENER--> orders
orders    --DEFAULT-------> catalog
~~~

thì graph được tạo với `withDependencyTypes(USES_COMPONENT)` chỉ thể hiện cạnh:

~~~text
orders --USES_COMPONENT--> payments
~~~

Các module không còn quan hệ được hiển thị **có thể bị lược khỏi sơ đồ** theo tùy chọn `ElementsWithoutRelationships` mặc định. Vì vậy “không còn node/cạnh trong diagram đã lọc” chỉ có nghĩa là **không nằm trong kết quả lọc**, không chứng minh module không tồn tại hay hệ thống không có các loại phụ thuộc khác.

### 6.2. Hai cách sinh diagram giải quyết hai mục đích

~~~java
new Documenter(ApplicationModules.of(ShopApplication.class))
        .writeModulesAsPlantUml(); // Diagram toàn hệ thống, mặc định gồm các loại quan hệ.

new Documenter(ApplicationModules.of(ShopApplication.class))
        .writeModulesAsPlantUml(
                DiagramOptions.defaults()
                        .withDependencyTypes(DependencyType.USES_COMPONENT)
        ); // Diagram được lọc theo component dependency.
~~~

Các lệnh trên là **hai phương án sử dụng riêng**; khi dùng chung một output folder và cùng tên file, lần sinh sau có thể ghi đè sơ đồ trước. Nếu muốn lưu đồng thời, cần cấu hình tên tệp đầu ra khác nhau bằng tùy chọn `withTargetFileName(...)` hoặc tổ chức các lần sinh riêng.

## 7. Đọc `USES_COMPONENT` từ Spring Modulith Actuator

Ngoài tài liệu sinh trong test, Spring Modulith có **Application Module Actuator** để công bố mô hình cấu trúc module khi ứng dụng đang chạy.

- Endpoint thông thường: `GET /actuator/modulith`.
- Mỗi module có `dependencies[]` là các phụ thuộc **đi ra** từ module đó.
- `dependencies[].target` chỉ **tên kỹ thuật** của module đích.
- `dependencies[].types[]` liệt kê các loại dependency của quan hệ đến đích, ví dụ `USES_COMPONENT`.

Ví dụ JSON minh họa:

~~~json
{
  "orders": {
    "displayName": "Orders",
    "basePackage": "com.example.shop.orders",
    "dependencies": [
      {
        "target": "payments",
        "types": ["USES_COMPONENT"]
      }
    ]
  },
  "payments": {
    "displayName": "Payments",
    "basePackage": "com.example.shop.payments",
    "dependencies": []
  },
  "inventory": {
    "displayName": "Inventory",
    "basePackage": "com.example.shop.inventory",
    "dependencies": [
      {
        "target": "orders",
        "types": ["EVENT_LISTENER"]
      }
    ]
  }
}
~~~

**Quan sát trọng tâm:** `orders.dependencies[0].target = payments` và `types = ["USES_COMPONENT"]` có nghĩa **orders phụ thuộc payments qua Spring component**. `payments.dependencies = []` chỉ nói **payments không có outgoing module dependency được ghi nhận trong ví dụ**, không nói payments không có incoming dependency.

### 7.1. Lọc những dependency có `USES_COMPONENT`

Nếu bạn đã bật Modulith Actuator và expose endpoint phù hợp, có thể dùng `curl` và `jq`:

~~~bash
# Xem mọi dependency USES_COMPONENT trong application module graph.
curl -fsS http://localhost:8080/actuator/modulith \
  | jq -r '
    to_entries[]
    | .key as $source
    | .value.dependencies[]?
    | select(.types | index("USES_COMPONENT"))
    | "\($source) -> \(.target)"
  '
~~~

Với JSON ví dụ, kết quả:

~~~text
orders -> payments
~~~

Biểu thức `.value.dependencies[]?` cho phép xử lý module không có dependency; `index("USES_COMPONENT")` kiểm tra một phần tử tồn tại trong mảng `types`. Do `types` là **mảng**, một quan hệ có thể đồng thời mang `USES_COMPONENT` và `EVENT_LISTENER`; lọc theo `index` vẫn tìm đúng.

Nếu chỉ cần xem outgoing dependency của `orders`:

~~~bash
curl -fsS http://localhost:8080/actuator/modulith \
  | jq '.orders.dependencies[]? | select(.types | index("USES_COMPONENT"))'
~~~

### 7.2. Vì sao JSON không thay thế diagram?

- Actuator tiện cho truy vấn và đối chiếu một **bản build đang chạy**.
- Documenter thích hợp để sinh tài liệu và sơ đồ **trong quy trình build/test**.
- Cả hai cùng dựa trên **application module model**, nhưng đường đi tạo dữ liệu và cấu hình module detection giữa build/test với runtime phải được giữ nhất quán.

Nếu bạn tùy biến cách phát hiện module chỉ trong nguồn test, kết quả diagram ở test có thể khác mô hình dùng bởi Actuator khi chạy production. Cần đặt những tùy biến muốn áp dụng ở runtime vào production source theo hướng dẫn Spring Modulith.

## 8. `USES_COMPONENT` liên hệ gì đến ranh giới kiến trúc?

### 8.1. Public API và private implementation

Trong cách tổ chức module mặc định, package gốc của module đóng vai trò API, còn subpackage thường dành cho phần nội bộ. Một thiết kế phù hợp là để bean dịch vụ cần chia sẻ nằm ở API của module hoặc expose giao diện công khai qua **named interface**.

Ví dụ:

~~~text
com.example.shop
├── orders/
│   └── OrderService.java               (inject PaymentOperations)
└── payments/
    ├── PaymentOperations.java           (API công khai)
    └── internal/
        └── DefaultPaymentOperations.java (@Service)
~~~

Tổ chức này làm giảm việc module `orders` phải biết class triển khai nội bộ. **Tuy nhiên**, đừng mặc định chính cách inject interface này luôn hiển thị một cạnh `USES_COMPONENT` giống cách inject trực tiếp một `@Service` cụ thể: việc phân loại dependency phụ thuộc type được tham chiếu và cơ chế nhận diện Spring component của phiên bản Modulith. Hãy **xem model thực tế** để xác nhận.

### 8.2. Phát hiện mối phụ thuộc đáng xem xét

Một component dependency là dấu hiệu hợp lệ nhưng cần lưu tâm nếu:

- Một module domain cấp thấp inject trực tiếp bean thuộc module tầng trên, khiến chiều phụ thuộc đi ngược thiết kế.
- Hai module inject bean của nhau, gây nguy cơ phụ thuộc vòng và khó kiểm soát khởi tạo.
- Nhiều module tham chiếu implementation nội bộ thay vì API công khai của module đích.
- Module chỉ cần nhận thông tin nghiệp vụ nhưng lại buộc chặt vào API gọi đồng bộ của module khác.

Các lựa chọn cải thiện có thể gồm đặt API ở đúng ranh giới, dùng giao diện ổn định, tách phần nhiệm vụ hoặc phát domain event. **Không nên thay mọi bean call bằng event một cách máy móc**: luồng cần phản hồi đồng bộ, xác thực trạng thái hoặc giao dịch có thể phù hợp với lời gọi trực tiếp.

### 8.3. Kiểm chứng bằng `ApplicationModules.verify()`

Một graph có `USES_COMPONENT` không mặc nhiên là lỗi. Cần so với các ràng buộc module và kiểm thử kiến trúc:

~~~java
package com.example.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ArchitectureTests {

    @Test
    void verifiesModuleBoundaries() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

Kiểm thử này phục vụ việc phát hiện các vi phạm ranh giới, chẳng hạn truy cập package nội bộ không được expose hay dependency không được phép. Nó không chứng minh từng bean call có hiệu năng tốt hoặc mọi luồng nghiệp vụ đã chạy đúng; những vấn đề đó cần test và observability riêng.

## 9. Từ module graph đến observability lúc chạy

Mô-đun học này còn đề cập **Actuator, event metrics, tracing và context propagation**. Vai trò của chúng khác nhau:

| Nguồn dữ liệu | Câu hỏi có thể trả lời | Điều không thể suy ra |
| --- | --- | --- |
| `USES_COMPONENT` trong module graph | Module nào phụ thuộc bean của module khác? | Tần suất gọi, latency, lỗi cụ thể |
| `/actuator/modulith` | Ứng dụng đang chạy nhận diện module và outgoing dependencies thế nào? | Lịch sử lời gọi runtime |
| Module entry span / distributed tracing | Một request được quan sát đã đi qua module nào, thời gian từng bước ra sao? | Tất cả dependency code chưa từng được thực thi |
| Event publication metrics | Những loại event được publish bao nhiêu lần theo instrumentation? | Mọi listener đã xử lý thành công |
| Context propagation | Trace/observation context được nối qua thread và luồng async thế nào? | Tự động bảo đảm module boundary đúng |
| `ApplicationModules.verify()` | Một số quy tắc cấu trúc của module có bị vi phạm không? | Kết quả và hiệu năng của mọi lần gọi runtime |

Ví dụ: graph cho biết `orders --USES_COMPONENT--> payments`, nhưng một trace của request có thể **không có** span `payments` nếu đường code trong request không gọi bean đó, sampling bỏ span, hoặc instrumentation chưa bật. Ngược lại, nhiều lần gọi vào `payments` trong một request cũng **không tạo nhiều cạnh** trên module graph.

Để xác nhận một tương tác có thật:

1. Dùng graph hoặc `/actuator/modulith` để xác định dependency **dự kiến theo code**.
2. Thực thi request đi qua nhánh code cần kiểm tra.
3. Dùng module entry spans, logs và metrics để xác định **lần thực thi**.
4. Nếu có listener chạy async, kiểm tra context propagation thay vì mặc định tất cả spans phải nằm chung một trace.

## 10. Tình huống thường gặp và cách kiểm tra

| Tình huống | Ý nghĩa có thể có | Hướng kiểm tra |
| --- | --- | --- |
| `orders → payments` xuất hiện ở `USES_COMPONENT` | Orders đang phụ thuộc Spring component của Payments | Tìm constructor/field/method injection hoặc cách bean được tham chiếu |
| Sơ đồ đã lọc không còn một module | Module không có cạnh `USES_COMPONENT` hiển thị theo điều kiện lọc | Xem graph tổng thể, `DEFAULT`/`EVENT_LISTENER` và tùy chọn ẩn node không có quan hệ |
| Module consumer có `EVENT_LISTENER` nhưng không có `USES_COMPONENT` | Có dependency event/type, chưa thấy component dependency | Kiểm tra code listener và việc có inject bean module khác hay không |
| Đã inject bean nhưng không thấy `USES_COMPONENT` | Có thể khác cách nhận diện component/module, hoặc dùng type trừu tượng, bean động | Kiểm tra version, module detection, API type và model thực tế |
| Actuator và diagram có dependency khác nhau | Có thể là khác phiên bản build hoặc customization chỉ có ở test | So bản build, package detection và cấu hình production |
| Có `USES_COMPONENT` nhưng không có trace span | Graph mô tả cấu trúc; không khẳng định lời gọi runtime | Kiểm tra request path, instrumentation, sampling và exporter |
| Có phụ thuộc vòng ở module graph | Thiết kế có thể đang coupling hai chiều | Xem tất cả type dependency, kiểm thử `verify()` và cơ chế bean wiring |

### 10.1. Không nhầm với dependency của Gradle/Maven

`USES_COMPONENT` mô tả **hai application module trong cùng ứng dụng Spring Modulith**, thường được phát hiện từ package/code. Nó **không** phải `implementation "group:artifact"` của Gradle/Maven và không trực tiếp nói rằng dự án đã kéo thêm một external JAR. Một codebase có thể dùng một Maven module duy nhất nhưng có nhiều application module của Spring Modulith.

### 10.2. Không nhầm với số lần Spring bean được gọi

Một cạnh `orders → payments` được nhận diện ở cấp mô hình, dù `placeOrder()` chạy 1 lần hay 1 triệu lần. Để có tần suất, lỗi và độ trễ, cần metrics/tracing với instrumentation phù hợp. Không dùng số cạnh `USES_COMPONENT` như KPI throughput.

## 11. Bài thực hành

### Bài 1 — Xác định chiều quan hệ

Cho đoạn code:

~~~java
@Service
class CheckoutService {
    CheckoutService(PricingService pricingService) {
        this.pricingService = pricingService;
    }

    private final PricingService pricingService;
}
~~~

Giả sử `CheckoutService` thuộc module `checkout`, `PricingService` là Spring bean thuộc module `pricing`, được nhận diện qua ranh giới module. Hãy cho biết:

1. Module nào là **source**, module nào là **target**?
2. Cạnh graph có nhãn gì?
3. Nếu `pricing` không gọi `checkout`, có thể kết luận `pricing → checkout` tồn tại không?
4. Nếu chưa có request checkout nào chạy, cạnh này có thể được phát hiện không?

**Gợi ý:** `checkout --USES_COMPONENT--> pricing`; đây là phụ thuộc code/component, không phụ thuộc request đã chạy hay chưa.

### Bài 2 — Phân loại các cạnh

Giả sử graph có:

~~~text
checkout  --USES_COMPONENT--> pricing
inventory --EVENT_LISTENER--> checkout
checkout  --DEFAULT--------> catalog
~~~

Hãy dựng hai sơ đồ: một sơ đồ đầy đủ và một sơ đồ chỉ giữ `USES_COMPONENT`. Giải thích vì sao sơ đồ đã lọc không còn cạnh đến `inventory` hoặc `catalog`.

### Bài 3 — Dùng `Documenter`

Trong một ứng dụng Spring Boot dùng Spring Modulith:

1. Tạo test với `ApplicationModules.of(ShopApplication.class)`.
2. Gọi `new Documenter(modules).writeModulesAsPlantUml(...)`.
3. Thêm `DiagramOptions.defaults().withDependencyTypes(DependencyType.USES_COMPONENT)`.
4. So sánh các cạnh trước và sau lọc; ghi chú module nào bị ẩn do không còn quan hệ hiển thị.
5. Đối chiếu một cạnh với constructor injection hoặc một bean dependency thực tế trong code.

### Bài 4 — Kiểm tra qua Actuator và trace

Khi endpoint `/actuator/modulith` đã được expose:

1. Dùng `jq` tìm các module pair có `USES_COMPONENT`.
2. Gọi một nghiệp vụ thực sự đi qua một cặp trong kết quả.
3. Nếu tracing đã cấu hình, kiểm tra module entry span liên quan.
4. Giải thích vì sao **cạnh graph có thể tồn tại nhưng span không xuất hiện**, và vì sao **một span không thay thế được model dependency**.

## 12. Câu hỏi ôn tập

1. `DependencyType.USES_COMPONENT` biểu thị nhu cầu gì giữa source module và target module?
2. Trong `orders --USES_COMPONENT--> payments`, module nào là bên sử dụng bean?
3. `USES_COMPONENT` có chắc chắn là một method call đã được thực thi không?
4. Vì sao lọc `withDependencyTypes(USES_COMPONENT)` có thể làm biến mất các module trên sơ đồ?
5. `DEFAULT` và `EVENT_LISTENER` khác `USES_COMPONENT` về bản chất quan hệ như thế nào?
6. Khi JSON Actuator có `"types": ["USES_COMPONENT", "EVENT_LISTENER"]`, cần diễn giải ra sao?
7. Thông tin nào phải lấy từ tracing/metrics thay vì module graph?
8. Nếu một bean ở module A phụ thuộc bean ở module B, kiến trúc có chắc chắn sai không? Vì sao?

## 13. Ghi nhớ

**`USES_COMPONENT` = module nguồn phụ thuộc vào Spring component của module đích.** Đây là tín hiệu cho biết module nguồn cần API/component của module đích ở cấp kiến trúc, thường thấy qua dependency injection. Trong graph, luôn đọc mũi tên theo chiều **source → target**; đừng nhầm nó với chiều event phát ra, số lần gọi hoặc một trace cụ thể.

Khi muốn phân tích coupling do Spring bean, hãy lọc graph bằng `DiagramOptions.withDependencyTypes(DependencyType.USES_COMPONENT)` hoặc đọc `dependencies[].types[]` ở `/actuator/modulith`. Kết hợp thêm kiểm thử ranh giới module và tracing/event metrics khi mục tiêu chuyển từ **cấu trúc được nhận diện** sang **hành vi vận hành**.

### Tài liệu tham khảo chính thức

- [Spring Modulith JavaDoc — `DependencyType`: định nghĩa `USES_COMPONENT`](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/DependencyType.html).
- [Spring Modulith — Production-ready Features: Application Module Actuator, dependency types và JSON](https://docs.spring.io/spring-modulith/reference/production-ready.html).
- [Spring Modulith JavaDoc — `Documenter.DiagramOptions`: `withDependencyTypes(...)`](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/docs/Documenter.DiagramOptions.html).
- [Spring Modulith — Documenting Application Modules: component diagrams và canvases](https://docs.spring.io/spring-modulith/reference/documentation.html).
- [Spring Modulith — Fundamentals: module API, named interfaces, allowed dependencies](https://docs.spring.io/spring-modulith/reference/fundamentals.html).
- [Spring Modulith — Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html).
