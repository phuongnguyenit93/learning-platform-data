# Đọc dependency source thay vì chỉ nhìn mũi tên

Một dependency graph cho biết module nào phụ thuộc module nào, nhưng mũi tên không giải thích đầy đủ vì sao quan hệ đó tồn tại. Hai module có thể nối với nhau vì một Spring component sử dụng component khác, vì một module tham chiếu entity của module khác hoặc vì nó đăng ký listener cho event được công khai. Những quan hệ này có ý nghĩa kiến trúc khác nhau dù sơ đồ có thể biểu diễn chúng bằng cùng một mũi tên.

Spring Modulith cung cấp `ApplicationModuleDependency` để đọc chi tiết từng quan hệ. Khi phân tích một cạnh, hãy xem module nguồn, kiểu Java tạo ra quan hệ, kiểu Java được tham chiếu, module đích và `DependencyType`. Các thông tin đó giúp truy ngược từ sơ đồ về code và đánh giá đúng tác động của phụ thuộc.

## 1. Mũi tên chỉ là phần tóm tắt

Giả sử ứng dụng bán hàng có các module `orders`, `inventory` và `customers`. Một sơ đồ có thể hiển thị:

```text
orders ─────> inventory
orders ─────> customers
inventory ─> orders
```

Sơ đồ cho biết có các quan hệ phụ thuộc giữa những module đó. Nhưng chỉ nhìn mũi tên chưa trả lời được:

- `orders` gọi một Spring bean của `inventory`, hay chỉ tham chiếu một kiểu dữ liệu?
- `orders` phụ thuộc vào entity nào của `customers`?
- Vì sao `inventory` lại phụ thuộc ngược vào `orders`? Có thể đây là một event listener.
- Lớp Java nào tạo ra mỗi quan hệ và kiểu đích cụ thể là gì?
- Một module phụ thuộc module khác trực tiếp hay chỉ thông qua một module trung gian?

Hướng của dependency graph là hướng phụ thuộc: module nguồn sử dụng hoặc tham chiếu module đích. Ví dụ, nếu `orders` gọi một component của `inventory`, `orders` là module nguồn và `inventory` là module đích. Với event, hướng phụ thuộc có thể ngược với hướng phát và nhận event ở runtime.

## 2. Đọc cấu trúc ApplicationModuleDependency

`ApplicationModuleDependency` đại diện cho một quan hệ giữa hai `ApplicationModule`. API công khai cung cấp các thông tin sau:

| API | Ý nghĩa khi phân tích |
|---|---|
| `getSourceType()` | Kiểu Java ở phía nguồn tạo ra quan hệ phụ thuộc |
| `getTargetType()` | Kiểu Java ở phía đích được tham chiếu |
| `getTargetModule()` | Module chứa kiểu đích |
| `getDependencyType()` | Phân loại quan hệ phụ thuộc |

Đối tượng không có phương thức `getSourceModule()`. Module nguồn được xác định từ `ApplicationModule` mà ta đang truy vấn, ví dụ `orders.getDirectDependencies(modules)`. `getSourceType()` là lớp Java cụ thể trong module nguồn, không phải tên module.

Ví dụ, nếu `OrderManagement` trong `orders` sử dụng `InventoryReservation` trong `inventory`, một dependency record có thể được hiểu như sau:

```text
Module nguồn : orders
Source type  : com.acme.shop.orders.OrderManagement
Target type  : com.acme.shop.inventory.InventoryReservation
Target module: inventory
Dependency   : USES_COMPONENT
```

`getSourceType()` và `getTargetType()` trả về `JavaClass` của ArchUnit. Có thể dùng `getName()` để lấy tên đầy đủ của kiểu. Các trường này chỉ ra cặp kiểu Java thiết lập quan hệ; chúng không phải vị trí dòng code hoặc tên chính xác của phương thức gọi. Muốn tìm call site, tiếp tục mở lớp nguồn và kiểm tra constructor, field, method hoặc chữ ký đang tham chiếu kiểu đích.

## 3. Phân biệt các DependencyType

API `DependencyType` hiện hành định nghĩa bốn loại chính. Mỗi loại mô tả một cách module nguồn phụ thuộc module đích.

| Loại | Ý nghĩa | Câu hỏi cần đặt ra |
|---|---|---|
| `USES_COMPONENT` | Phụ thuộc component; module đích cần được bootstrap để module nguồn chạy được | Component nào của module đích được module nguồn sử dụng? |
| `EVENT_LISTENER` | Module nguồn khai báo listener cho event được module đích công khai; module đích không cần bootstrap để module nguồn chạy | Listener nào đang nhận event và event thuộc hợp đồng của module nào? |
| `ENTITY` | Module nguồn tham chiếu entity thuộc module đích | Vì sao module nguồn cần biết entity đó? Có đang chia sẻ mô hình dữ liệu quá sâu không? |
| `DEFAULT` | Loại mặc định khi quan hệ không được phân loại thành một loại chuyên biệt hơn | Cặp kiểu nguồn và đích cho biết quan hệ tổng quát nào? |

### USES_COMPONENT: phụ thuộc component

Đây là loại cần chú ý khi một component trong module nguồn sử dụng component của module đích. Ví dụ:

```java
package com.acme.shop.orders;

import com.acme.shop.inventory.InventoryReservation;
import org.springframework.stereotype.Service;

@Service
class OrderManagement {

    private final InventoryReservation inventory;

    OrderManagement(InventoryReservation inventory) {
        this.inventory = inventory;
    }

    void complete(Order order) {
        inventory.reserve(order.getProductId(), order.getQuantity());
    }
}
```

Quan hệ này có ý nghĩa vận hành: module `orders` sử dụng component do `inventory` cung cấp. Theo định nghĩa của `USES_COMPONENT`, module đích cần được bootstrap để module nguồn có thể chạy. Khi đọc source type, hãy bắt đầu từ `OrderManagement`, sau đó tìm constructor hoặc thành phần đang nhận `InventoryReservation`.

Nếu nhiều lớp nguồn trong `orders` cùng tham chiếu component của `inventory`, đừng kết luận rằng chúng đều là một call site. Hãy đọc từng dependency record và kiểm tra lớp nguồn tương ứng.

### EVENT_LISTENER: phụ thuộc vào hợp đồng event

Giả sử `orders` công khai event `OrderCompleted`:

```java
package com.acme.shop.orders;

import java.util.UUID;

public record OrderCompleted(UUID orderId) {
}
```

Module `inventory` đăng ký listener:

```java
package com.acme.shop.inventory;

import com.acme.shop.orders.OrderCompleted;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class InventoryOnOrderCompleted {

    @ApplicationModuleListener
    void on(OrderCompleted event) {
        // Cập nhật tồn kho sau khi đơn hàng hoàn tất.
    }
}
```

Ở góc nhìn dependency:

```text
inventory.InventoryOnOrderCompleted
        │ khai báo listener cho
        ▼
orders.OrderCompleted

inventory ── EVENT_LISTENER ──> orders
```

Module nguồn là `inventory`, vì lớp listener nằm trong module này. Kiểu đích là `OrderCompleted`, thuộc module `orders`. Do đó, `inventory` phụ thuộc vào hợp đồng event của `orders`.

Ở runtime, hướng truyền event là `orders` phát `OrderCompleted` rồi listener trong `inventory` nhận event. Hai hướng này khác nhau: dependency graph chỉ hướng module phụ thuộc vào hợp đồng nào, còn luồng event mô tả nơi phát và nơi nhận. Đọc `EVENT_LISTENER` giúp nhận ra quan hệ này không giống một lời gọi component trực tiếp.

### ENTITY: tham chiếu entity của module khác

Ví dụ, module `reporting` tham chiếu entity `Customer` thuộc `customers` để tạo báo cáo:

```java
package com.acme.shop.reporting;

import com.acme.shop.customers.Customer;

class CustomerReport {

    String describe(Customer customer) {
        return customer.getId() + " - " + customer.getStatus();
    }
}
```

Nếu `Customer` được nhận diện là entity của module `customers`, quan hệ có thể được phân loại `ENTITY`. Source type giúp tìm lớp đang phụ thuộc vào entity đó; target type chỉ ra entity được tham chiếu.

`ENTITY` mô tả loại tham chiếu trong mô hình module. Chỉ từ nhãn này, không thể kết luận có truy vấn database, có giao dịch hay có thao tác ghi dữ liệu tại runtime. Hãy xem tiếp source code để xác định cách entity được nạp, truyền vào hoặc sử dụng.

### DEFAULT: quan hệ chưa được phân loại chuyên biệt

`DEFAULT` là giá trị mặc định trong `DependencyType`. Tài liệu API không gán cho hằng số này một ngữ nghĩa nghiệp vụ cụ thể tương tự `ENTITY`, `EVENT_LISTENER` hoặc `USES_COMPONENT`. Vì vậy, không nên diễn giải `DEFAULT` thành “không quan trọng”, “không có rủi ro” hoặc “không cần kiểm tra”.

Khi gặp `DEFAULT`, hãy đọc `sourceType` và `targetType`, xác định kiểu đích thuộc module nào, rồi kiểm tra cách source type tham chiếu kiểu đó. Phân loại mặc định vẫn là một quan hệ phụ thuộc cần được xem xét theo ranh giới module.

## 4. Liệt kê dependency record bằng API

Để đọc dependency source, trước tiên tạo mô hình module và lấy module nguồn. Ví dụ dưới đây liệt kê các phụ thuộc trực tiếp của `orders`:

```java
import org.springframework.modulith.core.ApplicationModule;
import org.springframework.modulith.core.ApplicationModules;
import org.springframework.modulith.core.ApplicationModuleDependency;

ApplicationModules modules = ApplicationModules.of(ShopApplication.class);

ApplicationModule orders = modules.getModuleByName("orders")
        .orElseThrow();

orders.getDirectDependencies(modules).stream()
        .forEach((ApplicationModuleDependency dependency) -> {
            System.out.printf(
                    "%s -> %s | %s | %s -> %s%n",
                    orders.getDisplayName(),
                    dependency.getTargetModule().getDisplayName(),
                    dependency.getDependencyType(),
                    dependency.getSourceType().getName(),
                    dependency.getTargetType().getName());
        });
```

Đầu ra có dạng minh họa:

```text
orders -> inventory | USES_COMPONENT | com.acme.shop.orders.OrderManagement -> com.acme.shop.inventory.InventoryReservation
orders -> customers | ENTITY | com.acme.shop.orders.OrderQuery -> com.acme.shop.customers.Customer
```

Tên module nguồn được lấy từ biến `orders`, còn module đích được lấy từ `dependency.getTargetModule()`. Hai kiểu Java ở cuối dòng cho biết lớp nguồn nào tạo quan hệ và kiểu đích nào được tham chiếu. Kết quả thực tế phụ thuộc vào cấu trúc code và metadata của ứng dụng.

### Lọc theo loại phụ thuộc

`getDirectDependencies()` nhận các `DependencyType` để chỉ lấy một số nhóm quan hệ:

```java
var componentDependencies = orders.getDirectDependencies(
        modules,
        DependencyType.USES_COMPONENT);

var entityDependencies = orders.getDirectDependencies(
        modules,
        DependencyType.ENTITY);
```

Hoặc lấy toàn bộ quan hệ trực tiếp rồi lọc bằng `withType()`:

```java
import org.springframework.modulith.core.DependencyType;

ApplicationModule inventory = modules.getModuleByName("inventory")
        .orElseThrow();

var eventDependencies = inventory.getDirectDependencies(modules)
        .withType(DependencyType.EVENT_LISTENER);

eventDependencies.stream().forEach(dependency ->
        System.out.println(
                dependency.getSourceType().getName()
                        + " listens to "
                        + dependency.getTargetType().getName()));
```

Các phương thức trên trả về `ApplicationModuleDependencies`, một tập hợp các dependency record. `stream()` duyệt từng record; `uniqueModules()` trả về các module đích duy nhất. Hai thao tác phục vụ mục đích khác nhau:

- Dùng `stream()` khi cần biết từng cặp `sourceType` và `targetType`, cũng như loại phụ thuộc.
- Dùng `uniqueModules()` khi chỉ cần biết module nguồn đang phụ thuộc vào những module đích nào.

Nếu nhiều lớp của `orders` phụ thuộc vào `inventory`, danh sách module duy nhất chỉ hiển thị `inventory` một lần. Điều này phù hợp khi thống kê module, nhưng không đủ khi truy tìm source code tạo ra từng quan hệ.

### Phân biệt phụ thuộc trực tiếp và bắc cầu

`getDirectDependencies(modules)` chỉ trả về các phụ thuộc trực tiếp của module đang xét. `getAllDependencies(modules)` bao gồm cả phụ thuộc bắc cầu.

Ví dụ:

```text
orders ─────> inventory ─────> products
```

Với `orders`, `inventory` là phụ thuộc trực tiếp; `products` là phụ thuộc bắc cầu nếu `orders` không tham chiếu trực tiếp module đó. Khi tìm lớp nguồn tạo ra một cạnh, bắt đầu bằng `getDirectDependencies()` để tránh gán nhầm quan hệ của module trung gian cho module đang xét.

## 5. Đọc dependency record theo một quy trình nhất quán

Khi phát hiện một cạnh đáng chú ý trong sơ đồ hoặc kết quả kiểm tra, hãy thực hiện lần lượt:

1. **Xác định module nguồn:** module nào đang được truy vấn hoặc đứng ở phía đầu mũi tên?
2. **Đọc `getDependencyType()`:** quan hệ được phân loại là component, entity, event listener hay mặc định?
3. **Đọc `getSourceType()`:** lớp nào trong module nguồn thiết lập quan hệ?
4. **Đọc `getTargetType()`:** lớp hoặc kiểu nào ở module đích được tham chiếu?
5. **Đọc `getTargetModule()`:** kiểu đích thuộc module nào và module đó có công khai API cần thiết không?
6. **Mở source type:** kiểm tra constructor, field, tham số phương thức, annotation listener hoặc chữ ký liên quan để hiểu vì sao phụ thuộc tồn tại.
7. **Đánh giá tác động:** xác định quan hệ có phù hợp với hợp đồng module, có tạo phụ thuộc không mong muốn hay cần chuyển sang event/API khác không.

Ví dụ, nếu sơ đồ cho thấy `inventory -> orders`, đừng vội kết luận `inventory` gọi service của `orders`. Nếu record có `EVENT_LISTENER`, hãy kiểm tra `sourceType` là listener trong `inventory` và `targetType` là event công khai của `orders`. Nếu record có `USES_COMPONENT`, hãy tìm component nguồn và component đích để xác định module nào cần được bootstrap cùng nhau.

## 6. Dependency type không đồng nghĩa với quyền truy cập

`DependencyType` giải thích bản chất của quan hệ được phát hiện. Nó không tự nói rằng quan hệ đó được phép theo quy tắc kiến trúc.

Ví dụ, `orders` có thể phụ thuộc `customers` bằng `USES_COMPONENT`, nhưng kiểu đích lại nằm trong package nội bộ mà `customers` không công khai. Hoặc `orders` có thể sử dụng module `customers` dù `allowedDependencies` của `orders` không cho phép quan hệ đó.

Vì thế, cần tách hai câu hỏi:

- **Quan hệ là gì?** Đọc `ApplicationModuleDependency` và `DependencyType`.
- **Quan hệ có hợp lệ không?** Dùng named interface, `allowedDependencies` và `ApplicationModules.verify()` để kiểm tra quy tắc kiến trúc.

Một dependency record có thể giúp giải thích vi phạm bằng cách chỉ ra lớp nguồn và kiểu đích liên quan. Khi `verify()` báo một module truy cập API không được công khai hoặc phụ thuộc ngoài danh sách cho phép, hãy quay lại record để xác định source type cụ thể trước khi sửa.

## 7. Những lỗi thường gặp khi đọc dependency source

| Cách đọc sai | Cách đọc chính xác |
|---|---|
| Xem mũi tên là thứ tự gọi hàm | Mũi tên thể hiện hướng phụ thuộc module; luồng thực thi cần được xác định từ code hoặc runtime trace |
| Xem `sourceType` là tên module nguồn | Đây là kiểu Java thiết lập quan hệ; module nguồn là module đang được truy vấn |
| Xem `targetType` là toàn bộ module đích | Đây là kiểu Java cụ thể được tham chiếu; `getTargetModule()` cho biết module chứa kiểu đó |
| Gộp mọi dependency record giữa hai module thành một quan hệ | Một cặp module có thể có nhiều lớp nguồn, kiểu đích hoặc loại phụ thuộc |
| Chỉ xem `uniqueModules()` khi điều tra lỗi | Cần `stream()` để giữ lại chi tiết từng dependency record |
| Xem `DEFAULT` là phụ thuộc không quan trọng | Đây vẫn là phụ thuộc; cần đọc source type và target type để hiểu ý nghĩa |
| Cho rằng `EVENT_LISTENER` là lời gọi component trực tiếp | Đây là phụ thuộc vào hợp đồng event; hướng phát event runtime có thể ngược hướng phụ thuộc |
| Cho rằng loại phụ thuộc quyết định quan hệ có được phép | Phải kiểm tra riêng named interface, `allowedDependencies` và kết quả `verify()` |

## 8. Checklist khi điều tra một cạnh

- [ ] Đã xác định đúng module nguồn và module đích.
- [ ] Đã ghi lại `DependencyType` của từng dependency record.
- [ ] Đã xác định `sourceType` và `targetType`.
- [ ] Đã phân biệt phụ thuộc trực tiếp với phụ thuộc bắc cầu.
- [ ] Đã mở lớp nguồn để tìm constructor, field, method hoặc listener tạo ra quan hệ.
- [ ] Đã kiểm tra kiểu đích có thuộc API được công khai của module đích hay không.
- [ ] Đã kiểm tra `allowedDependencies` và kết quả `ApplicationModules.verify()` khi cần đánh giá tính hợp lệ.

Khi có đầy đủ source type, target type và dependency type, một mũi tên tổng quát trở thành một quan hệ có thể giải thích và truy vết. Đó là cơ sở để quyết định nên giữ phụ thuộc, công khai hợp đồng, chuyển sang event hay điều chỉnh ranh giới module.

## Tài liệu tham khảo

- [ApplicationModuleDependency API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModuleDependency.html)
- [DependencyType API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/DependencyType.html)
- [ApplicationModuleDependencies API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModuleDependencies.html)
- [ApplicationModule API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModule.html)
- [ApplicationModules API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModules.html)
