# Đọc hướng phụ thuộc từ module graph

> **Chương:** Module graph  
> **Phạm vi:** Đọc đúng chiều phụ thuộc giữa các application module do Spring Modulith nhận diện; kết hợp module diagram, Actuator và các tín hiệu quan sát của ứng dụng Spring Boot.

## 1. Kết quả học tập

Sau bài này, bạn có thể:

1. Đọc chính xác một cạnh có hướng `A → B` trong **module dependency graph**: module `A` phụ thuộc vào module `B`.
2. Phân biệt **module nguồn (dependent/consumer)** với **module đích (dependency/provider)**; tránh nhầm hướng phụ thuộc với hướng di chuyển dữ liệu, hướng sự kiện hoặc thứ tự hiển thị trên hình.
3. Đọc các quan hệ trong sơ đồ Spring Modulith C4/UML do `Documenter` tạo và ánh xạ sang trường `dependencies[].target` của Actuator.
4. Phân biệt phụ thuộc trực tiếp, phụ thuộc bắc cầu, fan-in, fan-out và vòng phụ thuộc; suy luận tác động thay đổi một cách có điều kiện.
5. Hiểu vì sao listener trong module `notifications` nhận event của `orders` thường tạo dependency `notifications → orders`, dù luồng phát sự kiện có thể được vẽ `orders → notifications`.
6. Kết hợp việc đọc graph với `ApplicationModules.verify()`, module API, metrics và traces để kiểm chứng kiến trúc.

## 2. Trước hết, thống nhất ý nghĩa mũi tên

Trong module dependency graph, dùng quy ước:

~~~text
A ────────► B
│           │
│           └── Module được A sử dụng / phụ thuộc
└── Module chứa tham chiếu / nơi phát sinh phụ thuộc

Đọc: "A phụ thuộc vào B", hoặc "A sử dụng API / kiểu của B".
~~~

Đây là đồ thị **có hướng**. Một cạnh là một cặp có thứ tự `(source, target)`:

- `source`: application module **đang cần** thứ gì đó từ module khác, chẳng hạn kiểu Java, Spring bean hoặc event type.
- `target`: application module **cung cấp** yếu tố đang được tham chiếu.
- `A → B` **khác** `B → A`. Chỉ thấy một chiều không cho phép suy ra chiều ngược.

Nếu code của `orders` sử dụng một public API do `catalog` công bố:

~~~mermaid
flowchart LR
    Orders["orders"] -->|"USES_COMPONENT"| Catalog["catalog"]
~~~

Hãy đọc: “`orders` phụ thuộc vào `catalog`”. Không đọc “`catalog` phải gọi `orders`” hoặc “dữ liệu chỉ được phép chảy từ `orders` sang `catalog`”.

**Quy tắc kiểm tra nhanh:** đặt đầu ngón tay tại **đầu mũi tên**. Module ở đó là **dependency**, tức thứ mà module phía đuôi đang cần. Trong sơ đồ PlantUML/UML, một đường nối có thể sử dụng kiểu nét và ký hiệu khác nhau; luôn kiểm tra **đầu mũi tên và chú giải** thay vì đoán theo vị trí trái/phải.

## 3. Ví dụ xuyên suốt: bốn module của một cửa hàng

Giả sử ứng dụng Spring Boot có các application module:

| Module | Trách nhiệm | API hoặc thông điệp liên quan |
| --- | --- | --- |
| `orders` | Đặt hàng và phát domain event khi đặt hàng hoàn tất | `OrderService`, `OrderPlaced` |
| `catalog` | Cung cấp thông tin mặt hàng | `ProductCatalogApi` |
| `payments` | Thanh toán | `PaymentApi` |
| `notifications` | Gửi thông báo khi đơn hàng được tạo | Listener của `OrderPlaced` |

Cho rằng `OrderService` dùng `ProductCatalogApi` và `PaymentApi`; `notifications` chứa listener có tham số kiểu `OrderPlaced` do `orders` công bố.

~~~mermaid
flowchart LR
    Orders["orders"] -->|"USES_COMPONENT"| Catalog["catalog"]
    Orders -->|"USES_COMPONENT"| Payments["payments"]
    Notifications["notifications"] -->|"EVENT_LISTENER"| Orders
~~~

Bảng cạnh tương ứng:

| Source | Target | Đọc thành lời |
| --- | --- | --- |
| `orders` | `catalog` | `orders` sử dụng một Spring component của `catalog` |
| `orders` | `payments` | `orders` sử dụng một Spring component của `payments` |
| `notifications` | `orders` | `notifications` lắng nghe một event thuộc API của `orders` |

Đây là đồ thị **phụ thuộc ở cấp mã nguồn/module** được giả định để luyện cách đọc. Số lượng cạnh trên graph thực tế phụ thuộc vào mã ứng dụng, cách phát hiện module và quy tắc phân loại dependency của phiên bản Spring Modulith đang dùng.

### 3.1. Đối chiếu với Java code

Ở module `orders`, service sử dụng public API của hai module khác:

~~~java
package com.example.shop.orders;

import com.example.shop.catalog.ProductCatalogApi;
import com.example.shop.payments.PaymentApi;
import org.springframework.stereotype.Service;

@Service
public class OrderService {
    private final ProductCatalogApi catalog;
    private final PaymentApi payments;

    public OrderService(ProductCatalogApi catalog, PaymentApi payments) {
        this.catalog = catalog;
        this.payments = payments;
    }

    public void placeOrder(String orderId, String productId) {
        catalog.requireAvailable(productId);
        payments.charge(orderId); // minh họa quan hệ sử dụng API
    }
}
~~~

Đoạn code minh họa **phụ thuộc ở phía `orders`** vì `orders` tham chiếu hai type nằm trong module khác. API `requireAvailable` và `charge` là giả định cho ví dụ, không phải các method sẵn có của Spring Modulith.

Mũi tên trên dependency graph **không đảm bảo** các method trên đã được thực thi ở một request cụ thể; nó mô tả quan hệ có thể nhận diện từ code.

### 3.2. Phụ thuộc do lắng nghe event

Module `orders` công bố một kiểu event trong public API:

~~~java
package com.example.shop.orders;

public record OrderPlaced(String orderId) {}
~~~

Trong module `notifications`, một Spring component nhận event kiểu đó:

~~~java
package com.example.shop.notifications;

import com.example.shop.orders.OrderPlaced;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
class OrderNotificationListener {

    @EventListener
    void on(OrderPlaced event) {
        // Gửi thông báo cho đơn hàng được tạo.
    }
}
~~~

**Chiều phụ thuộc kiến trúc** là `notifications → orders` vì code listener phải biết kiểu `OrderPlaced` được `orders` công bố. Trong khi đó, khi `orders` phát event bằng `ApplicationEventPublisher`, **hướng truyền sự kiện ở runtime** có thể được mô tả là `orders → notifications`.

~~~mermaid
flowchart TB
    subgraph Static["Dependency graph - liên hệ kiểu mã nguồn"]
        Listener["notifications"] -->|"dùng OrderPlaced của"| Publisher["orders"]
    end
    subgraph Runtime["Luồng sự kiện - hoạt động khi chạy"]
        OrderRuntime["orders"] -->|"publish OrderPlaced"| NotificationRuntime["notifications"]
    end
~~~

Hai mũi tên ngược chiều **không mâu thuẫn** vì chúng trả lời hai câu hỏi khác nhau. Đây là một trong những cách hiểu nhầm phổ biến nhất khi đọc module graph của hệ thống dùng event-driven interaction.

## 4. Cách đọc sơ đồ Spring Modulith từ `Documenter`

Spring Modulith xây dựng mô hình module bằng `ApplicationModules`; `Documenter` có thể sinh sơ đồ thành phần dạng C4 hoặc UML/PlantUML mô tả quan hệ giữa các application module.

Ví dụ một test tạo tài liệu:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;
import org.springframework.modulith.docs.Documenter;

class ModuleDocumentationTests {

    @Test
    void writeModuleDiagrams() {
        ApplicationModules modules =
            ApplicationModules.of(ShopApplication.class);

        new Documenter(modules)
            .writeModulesAsPlantUml()
            .writeIndividualModulesAsPlantUml();
    }
}
~~~

Ở đây `ShopApplication` là lớp `@SpringBootApplication` giả định nằm tại root package của ứng dụng. Ví dụ cần các dependency Spring Modulith Core/Docs và JUnit phù hợp trong test classpath; output thường nằm trong thư mục tài liệu do `Documenter` cấu hình trong build/target, không cần đưa vào thư mục source code.

- `writeModulesAsPlantUml()`: sơ đồ toàn bộ các module được nhận diện trong phạm vi documenter.
- `writeIndividualModulesAsPlantUml()`: sơ đồ tập trung vào từng module và các module có quan hệ được đưa vào view.
- `Documenter.DiagramOptions.defaults().withStyle(DiagramStyle.UML)`: chọn kiểu UML thay vì C4 mặc định ở các phiên bản hỗ trợ.

Ví dụ biểu diễn **khái niệm** bằng PlantUML dependency:

~~~plantuml
@startuml
component "orders" as Orders
component "catalog" as Catalog
component "payments" as Payments
component "notifications" as Notifications

Orders ..> Catalog : uses component
Orders ..> Payments : uses component
Notifications ..> Orders : listens to event
@enduml
~~~

Đây là minh họa tự viết để đọc mũi tên, **không phải trích nguyên văn file PlantUML mà `Documenter` phát ra**. Với sơ đồ C4, các đường nối và nhãn quan hệ có thể được trình bày khác UML. Điều cần giữ là **ngữ nghĩa module nào phụ thuộc module nào**.

### 4.1. Quy trình 5 bước đọc bất kỳ module graph nào

1. **Đọc nhãn node:** mỗi node là một application module, không tự mặc định node là class, bean, service riêng hay microservice.
2. **Tìm đầu mũi tên:** lấy node phía đuôi làm `source` và node phía đầu làm `target`. Nếu sơ đồ không vẽ đầu mũi tên rõ, tra chú giải hoặc mã PlantUML/metadata gốc.
3. **Đọc nhãn quan hệ:** `USES_COMPONENT`, `EVENT_LISTENER`, `DEFAULT`, hoặc lời mô tả tùy generator. Đừng suy ra một cuộc gọi HTTP khi nhãn chỉ nói đến dependency.
4. **Ghi thành câu “A phụ thuộc B”:** có thể lập edge list `(source, target, type)` để loại bỏ nhầm lẫn do cách xếp node.
5. **Xác định phạm vi của view:** full graph, sơ đồ một module, diagram đã filter hay chỉ phần module được phép hiển thị? Không thấy cạnh trên ảnh đã lọc chưa chứng minh trong toàn bộ hệ thống không có quan hệ ấy.

### 4.2. Đừng suy ra hướng theo vị trí hình vẽ

Các engine layout có thể đảo thứ tự node hoặc bẻ cong đường nối để bố cục dễ đọc. Hai hình sau có cùng ý nghĩa kiến trúc:

~~~text
orders ─────► payments

payments ◄───── orders
~~~

Vị trí trái/phải, trên/dưới hoặc số lần đường nối bẻ góc **không** làm thay đổi hướng phụ thuộc. Trong sơ đồ không có đầu mũi tên hoặc dùng line không hướng, cần quay về dữ liệu source–target; đoán theo bố cục là không đáng tin.

## 5. Đọc cùng một graph từ Actuator JSON

Khi có `spring-modulith-actuator` và Spring Boot Actuator được cấu hình, endpoint thường là:

~~~http
GET /actuator/modulith
~~~

Endpoint trả metadata module, trong đó `dependencies[]` là các **phụ thuộc đi ra từ chính module đang được mô tả**. Theo hợp đồng JSON của Spring Modulith, `dependencies[].target` là module **được phụ thuộc**.

Ví dụ response lược bớt metadata không cần cho bài này:

~~~json
{
  "orders": {
    "basePackage": "com.example.shop.orders",
    "displayName": "Orders",
    "dependencies": [
      { "target": "catalog", "types": ["USES_COMPONENT"] },
      { "target": "payments", "types": ["USES_COMPONENT"] }
    ]
  },
  "catalog": {
    "basePackage": "com.example.shop.catalog",
    "displayName": "Catalog",
    "dependencies": []
  },
  "payments": {
    "basePackage": "com.example.shop.payments",
    "displayName": "Payments",
    "dependencies": []
  },
  "notifications": {
    "basePackage": "com.example.shop.notifications",
    "displayName": "Notifications",
    "dependencies": [
      { "target": "orders", "types": ["EVENT_LISTENER"] }
    ]
  }
}
~~~

Đây là JSON **minh họa**, không phải response thật của dự án. Với JSON này:

- Đang duyệt object `"orders"` thì **source là `orders`**.
- Gặp `{"target":"catalog"}` thì tạo cạnh **`orders → catalog`**.
- Gặp `{"target":"payments"}` thì tạo cạnh **`orders → payments`**.
- Đang duyệt object `"notifications"` gặp `{"target":"orders"}` thì tạo cạnh **`notifications → orders`**.
- `"dependencies": []` chỉ cho biết trong metadata trả về không có dependency **đi ra** từ module đó; không có nghĩa module khác không phụ thuộc vào nó.

Nếu phiên bản hay cơ chế hiển thị gộp nhiều loại quan hệ đến cùng đích:

~~~json
{
  "target": "orders",
  "types": ["EVENT_LISTENER", "USES_COMPONENT"]
}
~~~

Hãy đọc là **một cặp module source–target có nhiều loại phụ thuộc**, không suy thành hai chiều. Các loại trong JSON thường gặp là `DEFAULT` (type dependency), `USES_COMPONENT` (Spring bean dependency) và `EVENT_LISTENER`; API nội bộ ở các phiên bản mới có thể phân loại thêm một số trường hợp, nên đối chiếu phiên bản đang dùng nếu gặp tên lạ.

**Ghi nhớ khi chuyển từ JSON sang graph:** key của object cấp cao nhất là **source**; `dependencies[].target` là **target**. Đây là nguồn kiểm tra hướng tốt khi sơ đồ C4 hoặc UML quá nhiều cạnh giao nhau.

## 6. Phụ thuộc trực tiếp và phụ thuộc bắc cầu

Giả sử có graph:

~~~mermaid
flowchart LR
    Checkout["checkout"] --> Orders["orders"]
    Orders --> Catalog["catalog"]
    Orders --> Payments["payments"]
~~~

- Phụ thuộc **trực tiếp**: `checkout → orders`, `orders → catalog`, `orders → payments`.
- Đường đi **bắc cầu**: `checkout → orders → catalog`. Nói theo khả năng ảnh hưởng, `checkout` có thể chịu tác động của thay đổi trong `catalog` thông qua `orders`.
- Không tự vẽ thêm cạnh **trực tiếp** `checkout → catalog` nếu code không chứa quan hệ đó. Một đường đi nhiều bước **không** tương đương cạnh trực tiếp.

Về thiết kế, nếu `checkout` chỉ dùng API ổn định của `orders`, việc `catalog` thay đổi bên trong có thể được `orders` che giấu. Do đó suy luận “thay đổi `catalog` **chắc chắn** làm `checkout` hỏng” là quá mức; graph chỉ cung cấp **khả năng lan truyền tác động**, không phải kết luận chắc chắn.

### 6.1. Đường phụ thuộc và thứ tự gọi

Một đường `checkout → orders → payments` **không chứng minh** mỗi request checkout đều gọi payments. Dependency graph cho biết code có khả năng sử dụng module theo các cạnh ấy; luồng thực thi thực tế phụ thuộc điều kiện, dữ liệu và orchestration.

Tương tự, `A → B` không có nghĩa `A` phải được khởi tạo trước `B`. Nếu có cơ chế khởi tạo module phụ thuộc vào thứ tự, thường module cung cấp dependency phải sẵn sàng trước module sử dụng. Thứ tự khởi tạo có quy tắc riêng, không thể rút ra trực tiếp từ vị trí node trên hình.

## 7. Fan-in, fan-out và hướng lan truyền thay đổi

Với một module `M`:

- **Fan-out / out-degree:** số module khác mà `M` phụ thuộc trực tiếp (số cạnh **đi ra** từ `M`).
- **Fan-in / in-degree:** số module khác phụ thuộc trực tiếp vào `M` (số cạnh **đi vào** `M`).

Ví dụ:

~~~mermaid
flowchart LR
    Orders["orders"] -->|"outgoing"| Catalog["catalog"]
    Orders -->|"outgoing"| Payments["payments"]
    Checkout["checkout"] -->|"incoming"| Orders
    Notifications["notifications"] -->|"incoming"| Orders
~~~

Trong graph này:

| Module | Cạnh đi ra | Cạnh đi vào | Cách hiểu |
| --- | --- | --- | --- |
| `orders` | 2 | 2 | Dùng `catalog`, `payments`; được `checkout`, `notifications` phụ thuộc |
| `catalog` | 0 | 1 | Không có dependency đi ra được vẽ; `orders` phụ thuộc vào nó |
| `payments` | 0 | 1 | Không có dependency đi ra được vẽ; `orders` phụ thuộc vào nó |
| `checkout` | 1 | 0 | Chỉ phụ thuộc trực tiếp vào `orders` trong view |
| `notifications` | 1 | 0 | Phụ thuộc vào `orders` theo loại quan hệ trong view |

**Đọc tác động của thay đổi:** nếu thay đổi public API của `orders`, các consumer có cạnh **chỉ vào `orders`** như `checkout`, `notifications` là nhóm đầu tiên cần xem xét. Nếu `orders` thay đổi cách gọi `payments`, bản thân `orders` có thể cần sửa theo **cạnh đi ra**.

Chỉ dùng fan-in/fan-out như **tín hiệu để điều tra**. Fan-in cao có thể cho thấy một module API được nhiều phần sử dụng, nhưng không chứng minh nó thiết kế tốt hoặc xấu. Fan-out cao có thể khiến orchestration phức tạp, nhưng cũng có thể phù hợp vai trò module điều phối. Mức độ coupling phụ thuộc tính ổn định của API, nội dung phụ thuộc và quy tắc kiến trúc.

## 8. Vòng phụ thuộc: nhận diện bằng hướng mũi tên

Một vòng phụ thuộc có dạng:

~~~mermaid
flowchart LR
    A["orders"] --> B["payments"]
    B --> C["billing"]
    C --> A
~~~

Ta có chu trình có hướng:

~~~text
orders → payments → billing → orders
~~~

Chỉ cần đi theo các mũi tên và quay lại node xuất phát là đã có **directed cycle**. Một vòng như `A → B → A` cũng là cycle, dù chỉ có hai module.

Vòng phụ thuộc thường làm mờ ranh giới trách nhiệm, khó khởi tạo/thử nghiệm từng module độc lập và dễ gây ảnh hưởng dây chuyền. Spring Modulith có khả năng kiểm tra quy tắc **không cho phép cycle giữa application modules**:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleArchitectureTests {

    @Test
    void moduleDependenciesMustBeValid() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

Theo cơ chế verification mặc định, `verify()` cũng kiểm tra truy cập vào API module thay vì implementation internals và các giới hạn dependency được khai báo bằng `@ApplicationModule(allowedDependencies = …)` (nếu có). Test thất bại khi phát hiện vi phạm kiến trúc. **Graph là công cụ đọc và thảo luận**, còn việc pass/fail nên được quyết định bằng **các quy tắc kiểm chứng đã cấu hình**, không chỉ bằng cảm nhận từ hình vẽ.

### 8.1. Tìm nguyên nhân của cycle từ code

Khi thấy `orders → payments → orders`:

1. Xác định type hoặc bean tạo cạnh `orders → payments` (chẳng hạn `PaymentApi`).
2. Tìm cạnh `payments → orders`: có thể là `OrderRepository` bị tham chiếu vào internals, event listener cho `OrderPlaced` hoặc một service dùng `OrderApi`.
3. Chọn cách sửa dựa trên kiến trúc: di chuyển API về đúng module cung cấp, tránh truy cập implementation, tạo event contract phù hợp, hoặc điều chỉnh trách nhiệm giữa các module.
4. Chạy lại `ApplicationModules.verify()`; tạo lại graph để xem hướng đã thay đổi thế nào.

Không “sửa” cycle bằng cách ẩn cạnh trên sơ đồ. Cấu hình filter chỉ thay hình, trong khi ràng buộc code vẫn còn.

## 9. Allowed dependencies và API module: khi một cạnh đúng kỹ thuật nhưng sai thiết kế

Không phải mọi cạnh mà Spring Modulith phát hiện đều được kiến trúc cho phép. Chẳng hạn đội thiết kế muốn `orders` chỉ phụ thuộc `catalog` và `payments`. Có thể khai báo trong `package-info.java` của module:

~~~java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = {"catalog", "payments"}
)
package com.example.shop.orders;
~~~

Khai báo này mô tả **đích mà source `orders` được phép phụ thuộc**, không phải danh sách module được phép phụ thuộc **vào `orders`**. Nếu `orders` bắt đầu tham chiếu `notifications`, verification có thể phát hiện vi phạm allowed-dependencies.

Ngoài hướng cạnh, còn cần kiểm tra **điểm đi vào module đích**:

- `orders → catalog` thông qua public API của `catalog` có thể hợp lệ.
- `orders → catalog.internal.SomeRepository` cũng có cùng hướng mũi tên trên graph, nhưng đã vượt qua ranh giới nội bộ và có thể bị Spring Modulith verification từ chối.
- Nếu module có **named interfaces**, cấu hình cho phép tham chiếu có thể chi tiết đến interface được xuất bản; cùng cặp source–target không đủ để đánh giá hợp lệ.

Vì vậy khi review, đặt hai câu hỏi độc lập: **“Hướng phụ thuộc có đúng không?”** và **“Có phụ thuộc qua API công khai được phép không?”**

## 10. Những nhầm lẫn thường gặp khi đọc graph

| Quan sát | Kết luận sai | Cách đọc đúng |
| --- | --- | --- |
| `orders → payments` | “payments gọi orders” | `orders` phụ thuộc vào `payments` |
| `notifications → orders` với `EVENT_LISTENER` | “Event chạy từ notifications sang orders” | Listener trong `notifications` phụ thuộc vào event type của `orders`; luồng event runtime có thể ngược lại |
| Có cạnh `A → B` | “Mọi request của A đều gọi B” | Graph mô tả dependency được phát hiện, không phải trace từng request |
| `catalog` có `dependencies: []` | “Không module nào dùng catalog” | Không có **outgoing dependency** được ghi nhận; vẫn có thể có incoming dependency |
| `A → B → C` | “A có dependency trực tiếp sang C” | Đó là **transitive path**; cạnh trực tiếp `A → C` cần được kiểm tra riêng |
| Node `payments` ở góc trái ảnh | “payments chắc là module nguồn” | Bố cục không quyết định hướng; đọc đầu mũi tên |
| Không thấy `notifications` trong diagram của `payments` | “Không tồn tại notifications trong ứng dụng” | Individual/module-filtered view không hiển thị mọi module |
| Có `A → B → A` | “Miễn là hai module chạy được thì ổn” | Cycle là dấu hiệu cần kiểm chứng; `verify()` mặc định kiểm tra cycle |
| Cạnh hợp lệ `A → B` | “Đảm bảo không vi phạm encapsulation” | Còn phải xem tham chiếu qua API/named interface hay internals |
| Thấy `EVENT_LISTENER` trên graph | “Event đã publish và listener xử lý thành công” | Cần event publication/metrics/traces để kiểm tra runtime |

## 11. Phân biệt module graph với graph quan sát lúc chạy

Để kiểm chứng kiến trúc theo mục tiêu của **Spring Modulith Documentation & Observability**, cần tách ba loại bằng chứng:

| Nguồn | Thấy gì? | Không kết luận được gì chỉ từ nguồn này? |
| --- | --- | --- |
| `Documenter` C4/UML module graph | Các module và dependency được phát hiện khi tạo tài liệu | Một lời gọi hay event đã chạy thực tế |
| `GET /actuator/modulith` | Module metadata và outgoing dependencies của **ứng dụng đang chạy** | Mức độ hoạt động, thời gian chạy, trạng thái xử lý event |
| Micrometer observation, metrics, tracing | Các operation/event instrumented đã chạy, latency, span/trace theo cấu hình | Toàn bộ dependency tĩnh chưa từng được gọi |

Ví dụ:

~~~mermaid
flowchart LR
    subgraph Arch["Graph kiến trúc"]
        NotificationStatic["notifications"] -->|"EVENT_LISTENER"| OrdersStatic["orders"]
    end
    subgraph Events["Một tương tác runtime"]
        OrdersRuntime["orders"] -->|"publish OrderPlaced"| NotificationsRuntime["notifications"]
    end
~~~

Muốn tìm hiểu “đơn hàng nào khiến notification nào chạy”, cần công cụ runtime và correlation/trace context. Muốn trả lời “notifications đang phụ thuộc kiến trúc vào ai”, đọc graph hoặc JSON metadata. Khi xử lý event bất đồng bộ qua `Executor`, Reactor hoặc durable publication, tracing context có thể cần cơ chế propagation phù hợp; bản thân module graph không giải quyết chuyện truyền context.

**Lưu ý phạm vi:** ngay cả trace cũng chỉ thể hiện span đã được instrument và được ghi nhận theo sampling/exporter; thiếu span chưa đủ kết luận dependency không tồn tại hoặc code không chạy.

## 12. Quy trình review graph trong một dự án thực tế

Một buổi review module graph có thể đi theo thứ tự:

**Bước 1 — Chốt phiên bản và nguồn graph.** Ghi tên ứng dụng, commit/bản deploy, cách phát hiện module và nguồn graph (`Documenter` hay `/actuator/modulith`). Tránh so ảnh của bản cũ với runtime bản mới rồi kết luận graph mâu thuẫn.

**Bước 2 — Lập bảng cạnh có hướng.** Với từng `source`, liệt kê tất cả `target` và kiểu quan hệ (nếu có). Bảng edge list thường dễ review hơn sơ đồ quá dày đường nối.

**Bước 3 — Xét các cạnh bất ngờ.** Nếu module nghiệp vụ lõi phụ thuộc module hạ tầng giao diện, nếu có một cặp dependency hai chiều hoặc một module dùng quá nhiều internals của module khác, hãy tìm class/bean/event type tạo cạnh.

**Bước 4 — Xét fan-in/fan-out và chu trình.** Chỉ ra module nào dễ lan ảnh hưởng khi API thay đổi và module nào đang phối hợp nhiều phần, nhưng tránh đưa ra kết luận định tính dựa trên số đếm.

**Bước 5 — Chạy quy tắc verification.** Dùng `ApplicationModules.of(ShopApplication.class).verify()` trong test cùng phiên bản/thành phần đúng của ứng dụng. Nếu có allowed dependencies hoặc named interfaces, đảm bảo test thực sự tải được các metadata đó.

**Bước 6 — Đối chiếu runtime khi cần.** Dùng Actuator để xem bản đang chạy công bố model nào; dùng event metrics/tracing để xem tương tác thực tế. Nếu graph có `orders → payments` nhưng trace request không có span payments, kiểm tra điều kiện gọi, instrumentation, sampling và context propagation thay vì suy diễn.

## 13. Bài tập đọc hướng phụ thuộc

Cho graph:

~~~mermaid
flowchart LR
    Checkout["checkout"] --> Orders["orders"]
    Orders --> Catalog["catalog"]
    Orders --> Payments["payments"]
    Reporting["reporting"] -->|"EVENT_LISTENER"| Orders
    Notifications["notifications"] -->|"EVENT_LISTENER"| Orders
~~~

**Câu 1.** Module nào phụ thuộc trực tiếp vào `orders`?

**Câu 2.** `orders` phụ thuộc trực tiếp vào module nào?

**Câu 3.** `checkout` có đường phụ thuộc đến `payments` không? Có cạnh trực tiếp `checkout → payments` không?

**Câu 4.** Nếu `orders` phát event và listener trong `notifications` xử lý, hướng truyền event runtime và hướng phụ thuộc kiểu Java có nhất thiết trùng nhau không?

**Câu 5.** Nếu một thay đổi public API trong `orders` làm test compilation của `reporting` thất bại, hướng cạnh nào giải thích được mối liên hệ? Việc có cạnh ấy đã đủ kết luận đây là kiến trúc sai chưa?

**Câu 6.** Sau khi thêm cạnh `catalog → checkout`, có cycle không? Hãy lần theo mũi tên.

<details>
<summary>Gợi ý đáp án</summary>

1. `checkout`, `reporting` và `notifications` có cạnh trực tiếp **chỉ vào `orders`**.
2. `orders` có hai cạnh đi ra đến `catalog` và `payments`.
3. Có đường đi bắc cầu `checkout → orders → payments`; graph không vẽ cạnh trực tiếp `checkout → payments`.
4. Không nhất thiết. Dependency tĩnh có thể là `notifications → orders` do listener biết `OrderPlaced`; event runtime được phát từ `orders` cho `notifications`.
5. Cạnh `reporting → orders` diễn đạt `reporting` phụ thuộc API của `orders`. Đúng/sai phụ thuộc quy tắc kiến trúc và tính công khai của API, không thể kết luận chỉ từ một cạnh.
6. Có chu trình `catalog → checkout → orders → catalog`.

</details>

## 14. Tóm tắt ghi nhớ

Khi đọc Spring Modulith module graph, hãy hỏi theo đúng thứ tự:

1. **Ai là source, ai là target?** `A → B` nghĩa là `A phụ thuộc B`.
2. **Đây là loại dependency nào?** Type reference, bean/component use hay event listener?
3. **View này có đầy đủ không?** Toàn graph, một module hay chỉ một phần được lọc?
4. **Quan hệ có trực tiếp không?** Phân biệt một cạnh với đường đi bắc cầu; kiểm tra cycle theo chiều mũi tên.
5. **Nó có phù hợp kiến trúc không?** Đối chiếu allowed dependencies, API module, named interfaces và kết quả `verify()`.
6. **Nó đã diễn ra khi chạy chưa?** Cần metrics/tracing/event publications nếu câu hỏi là về hành vi runtime.

**Một câu cần nhớ:** trong **dependency graph**, mũi tên chỉ từ **module cần thứ gì đó** đến **module cung cấp thứ đó**; đối với event, hướng phụ thuộc tĩnh có thể ngược hướng phát thông điệp ở runtime.

### Tài liệu tham khảo

- [Spring Modulith — Documenting Application Modules](https://docs.spring.io/spring-modulith/reference/documentation.html) — cách tạo module component diagrams C4/UML bằng `Documenter`.
- [Spring Modulith — Production-ready Features](https://docs.spring.io/spring-modulith/reference/production-ready.html) — endpoint `modulith`, `dependencies[]` và `dependencies[].target`.
- [Spring Modulith — Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html) — kiểm tra vòng phụ thuộc, API module và allowed dependencies.
- [Spring Modulith — Fundamentals](https://docs.spring.io/spring-modulith/reference/fundamentals.html) — module boundaries, named interfaces và cách khai báo dependency được phép.
- [Spring Modulith — Working with Application Events](https://docs.spring.io/spring-modulith/reference/events.html) — mô hình giao tiếp bằng domain event và application-module listener.

> **Lưu ý phiên bản:** tên API, bộ lọc, nhóm loại dependency và định dạng diagram có thể thay đổi giữa các phiên bản Spring Modulith. Khi triển khai, dùng BOM tương thích của Spring Boot/Spring Modulith và đối chiếu tài liệu theo phiên bản dự án.
