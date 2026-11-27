# Đọc nguồn gốc dependency qua API model

Khi Spring Modulith phát hiện một quan hệ phụ thuộc giữa hai application module, ta thường cần biết thêm ba điều: **type nào ở module nguồn tạo ra dependency, type nào ở module đích được tham chiếu và dependency thuộc loại nào**. Chỉ nhìn sơ đồ `orders → inventory` cho biết hướng phụ thuộc ở cấp module, nhưng chưa đủ để tìm lớp cần xem lại.

Spring Modulith cung cấp `ApplicationModule`, `ApplicationModuleDependencies` và `ApplicationModuleDependency` để truy vấn mô hình này. Trong đó, `ApplicationModuleDependency` là đối tượng quan trọng nhất khi cần đọc nguồn gốc của từng dependency: nó cung cấp source type, target type, target module và dependency type.

## 1. Bắt đầu từ ApplicationModules

Giả sử ứng dụng bán hàng có hai module:

```text
com.example.shop
├── ShopApplication.java
├── inventory
│   ├── StockAvailability.java
│   └── internal
│       └── StockService.java
└── orders
    └── internal
        └── OrderService.java
```

Module `orders` sử dụng chức năng kiểm tra tồn kho được công khai bởi `inventory`:

```java
package com.example.shop.inventory;

public interface StockAvailability {

    boolean isAvailable(String sku, int quantity);
}
```

```java
package com.example.shop.orders.internal;

import com.example.shop.inventory.StockAvailability;
import org.springframework.stereotype.Service;

@Service
public class OrderService {

    private final StockAvailability stockAvailability;

    public OrderService(StockAvailability stockAvailability) {
        this.stockAvailability = stockAvailability;
    }

    public void validate(String sku, int quantity) {
        if (!stockAvailability.isAvailable(sku, quantity)) {
            throw new IllegalStateException("Không đủ hàng trong kho");
        }
    }
}
```

Trước tiên, tạo mô hình module từ lớp Spring Boot application:

```java
ApplicationModules modules = ApplicationModules.of(ShopApplication.class);
```

Sau đó tìm module sở hữu type nguồn. `getModuleByType(Class<?>)` trả về `Optional<ApplicationModule>`:

```java
ApplicationModule orders = modules.getModuleByType(OrderService.class)
        .orElseThrow(() -> new IllegalStateException(
                "Không tìm thấy module chứa OrderService"));
```

Ta đã xác định được module nguồn `orders`. Bước tiếp theo là lấy các dependency mà module này thực sự có.

## 2. Phân biệt dependency được khai báo và dependency thực tế

Spring Modulith mô hình hóa hai góc nhìn khác nhau:

- **Allowed dependencies:** những module mà module nguồn được phép phụ thuộc theo cấu hình, chẳng hạn `allowedDependencies` trong `@ApplicationModule` hoặc các module được khai báo là shared.
- **Materialized dependencies:** những quan hệ phụ thuộc thực tế được phát hiện từ các type trong mã nguồn.

Có thể đọc allow-list bằng `getAllowedDependencies(modules)` và đọc dependency thực tế bằng `getDirectDependencies(modules)`:

```java
var allowed = orders.getAllowedDependencies(modules);
var actual = orders.getDirectDependencies(modules);

System.out.println("Allowed dependencies:");
allowed.forEach(System.out::println);

System.out.println("Actual direct dependencies:");
actual.uniqueModules().forEach(module ->
        System.out.println(module.getDisplayName()));
```

Hai danh sách trả lời hai câu hỏi khác nhau. Một module có thể được cho phép sử dụng nhưng hiện chưa có code nào tham chiếu đến nó. Ngược lại, dependency thực tế đến một module chưa được cho phép có thể là nguyên nhân khiến `verify()` báo vi phạm.

Nếu module không khai báo allow-list tường minh, đừng diễn giải một danh sách khai báo rỗng thành kết luận rằng module không được phép phụ thuộc vào bất kỳ module nào. Hãy phân biệt trường hợp không có giới hạn được khai báo với trường hợp có allow-list nhưng không chứa module đích.

Vì vậy, khi điều tra dependency, hãy xem cả chính sách được khai báo lẫn quan hệ được phát hiện. Không nên kết luận một dependency đang tồn tại chỉ vì nó xuất hiện trong allow-list.

## 3. Lấy các dependency trực tiếp của module

`ApplicationModule.getDirectDependencies(ApplicationModules, DependencyType...)` trả về các dependency trực tiếp của module hiện tại. Kết quả có kiểu `ApplicationModuleDependencies`.

```java
import org.springframework.modulith.core.ApplicationModuleDependencies;

ApplicationModuleDependencies dependencies = orders.getDirectDependencies(modules);

dependencies.stream().forEach(System.out::println);
```

`ApplicationModuleDependencies` là tập hợp các dependency đã được Spring Modulith phát hiện. Một số phương thức thường dùng:

| API | Công dụng |
|---|---|
| `stream()` | Duyệt từng `ApplicationModuleDependency` để xem nguồn và đích cụ thể |
| `uniqueModules()` | Lấy các module đích duy nhất, bỏ trùng module |
| `contains(ApplicationModule)` | Kiểm tra có dependency đến module được truyền vào không |
| `containsModuleNamed(String)` | Kiểm tra có dependency đến module mang tên tương ứng không |
| `contains(String)` | Kiểm tra có dependency đến type theo tên đầy đủ không |
| `withType(DependencyType)` | Tạo tập dependency chỉ gồm một loại đã chọn |
| `isEmpty()` | Kiểm tra tập dependency có rỗng không |

Nếu chỉ cần biết `orders` phụ thuộc vào những module nào, `uniqueModules()` là đủ. Nếu cần biết lớp nào tạo ra từng quan hệ, hãy dùng `stream()` để đọc từng dependency object.

## 4. Đọc source type, target type và target module

`ApplicationModuleDependency` cung cấp bốn thông tin cốt lõi:

- `getSourceType()` trả về Java type tạo ra dependency.
- `getTargetType()` trả về Java type mà source type phụ thuộc vào.
- `getTargetModule()` trả về application module sở hữu target type.
- `getDependencyType()` trả về loại dependency mà Spring Modulith phân loại.

Ví dụ, in các quan hệ trực tiếp của `orders` theo dạng dễ đọc:

```java
import org.springframework.modulith.core.ApplicationModuleDependency;

dependencies.stream().forEach(dependency -> {
    String source = dependency.getSourceType().getName();
    String target = dependency.getTargetType().getName();
    String targetModule = dependency.getTargetModule().getDisplayName();
    String kind = dependency.getDependencyType().name();

    System.out.printf("%s --[%s]--> %s (module: %s)%n",
            source, kind, target, targetModule);
});
```

Một kết quả minh họa có thể có dạng:

```text
com.example.shop.orders.internal.OrderService
  --[USES_COMPONENT]-->
com.example.shop.inventory.StockAvailability
  (module: Tồn kho)
```

Đọc theo chiều source → target giúp xác định đúng module nào đang tạo dependency. Nếu thấy `OrderService` là source type, ta biết cần bắt đầu điều tra từ lớp xử lý đơn hàng; `StockAvailability` là target type cho biết hợp đồng mà lớp đó đang sử dụng.

## 5. Phân biệt các loại dependency

`DependencyType` phân loại quan hệ giữa các application module. Những giá trị chính gồm:

| Loại | Ý nghĩa |
|---|---|
| `DEFAULT` | Nhóm dependency mặc định, không thuộc các loại chuyên biệt như entity, event listener hoặc component |
| `USES_COMPONENT` | Dependency qua component; module đích cần được bootstrap để module nguồn hoạt động |
| `ENTITY` | Module nguồn tham chiếu entity thuộc module đích |
| `EVENT_LISTENER` | Module nguồn khai báo listener cho event do module đích công bố; module đích không cần được bootstrap chỉ để chạy module nguồn theo quan hệ listener này |

Ví dụ, `OrderService` inject một component do `inventory` cung cấp có thể được biểu diễn bằng `USES_COMPONENT`. Nếu code tham chiếu entity của module khác, mô hình có thể phân loại thành `ENTITY`. Một listener nhận event của module khác tạo quan hệ `EVENT_LISTENER`.

Loại dependency giúp hiểu bản chất quan hệ, nhưng không thay thế việc đọc source và target type. Hai dependency cùng loại vẫn có thể được tạo bởi những lớp khác nhau và tham chiếu những type khác nhau.

## 6. Lọc dependency theo loại

Các phương thức `getDirectDependencies(...)` và `getAllDependencies(...)` nhận danh sách `DependencyType` tùy chọn. Ta có thể lọc để điều tra một nhóm quan hệ cụ thể:

```java
import org.springframework.modulith.core.DependencyType;

var componentDependencies = orders.getDirectDependencies(
        modules, DependencyType.USES_COMPONENT);

componentDependencies.stream().forEach(dependency ->
        System.out.printf("%s -> %s%n",
                dependency.getSourceType().getName(),
                dependency.getTargetType().getName()));
```

Hoặc chỉ xem dependency do event listener tạo ra:

```java
var eventDependencies = orders.getDirectDependencies(
        modules, DependencyType.EVENT_LISTENER);
```

Ở cấp `ApplicationModuleDependencies`, `withType(DependencyType)` cũng có thể lọc một tập dependency đã lấy được:

```java
var eventOnly = orders.getDirectDependencies(modules)
        .withType(DependencyType.EVENT_LISTENER);
```

Lọc theo loại hữu ích khi một module có nhiều kiểu tích hợp. Ví dụ, nhóm có thể muốn xem các dependency component để tìm coupling giữa service, rồi xem riêng event listener để đánh giá các quan hệ giao tiếp bất đồng bộ.

## 7. Phân biệt dependency trực tiếp và dependency bắc cầu

Giả sử mô hình có các quan hệ:

```text
orders ───────> inventory
   │
   └──────────> shipping ───────> inventory
```

`orders` phụ thuộc trực tiếp vào `inventory` và `shipping`. `shipping` cũng phụ thuộc vào `inventory`. Khi xem toàn bộ dependency bắc cầu của `orders`, ta có thể thấy những module mà `orders` phụ thuộc thông qua các module trung gian.

Spring Modulith cung cấp:

- `getDirectDependencies(modules)`: chỉ lấy dependency trực tiếp.
- `getAllDependencies(modules)`: lấy dependency của module, bao gồm cả dependency bắc cầu.
- `getDependencies(modules, DependencyDepth, DependencyType...)`: chọn độ sâu và loại dependency cần truy vấn.

Ví dụ:

```java
import org.springframework.modulith.core.DependencyDepth;

var direct = orders.getDirectDependencies(modules);
var transitive = orders.getAllDependencies(modules);

var immediateOnly = orders.getDependencies(
        modules, DependencyDepth.IMMEDIATE);

var allLevels = orders.getDependencies(
        modules, DependencyDepth.ALL);
```

`DependencyDepth.IMMEDIATE` giới hạn ở cấp trực tiếp; `DependencyDepth.ALL` bao gồm các cấp bắc cầu. Hãy dùng dependency trực tiếp khi tìm lớp đang tạo ra một cạnh cụ thể. Dùng toàn bộ dependency khi muốn hiểu phạm vi module mà một module phụ thuộc gián tiếp.

Không nên nhầm danh sách module duy nhất với danh sách dependency chi tiết. Một module đích có thể được tham chiếu bởi nhiều source type hoặc qua nhiều target type. `uniqueModules()` gom các module đích thành một danh sách, trong khi `stream()` giữ lại từng `ApplicationModuleDependency` để điều tra nguồn gốc.

## 8. Tìm module và type tạo ra dependency cụ thể

Nếu biết module đích cần điều tra, có thể lọc các dependency theo target module hoặc target type:

```java
var inventory = modules.getModuleByName("inventory").orElseThrow();

var dependenciesToInventory = orders.getDirectDependencies(modules).stream()
        .filter(dependency -> dependency.getTargetModule().equals(inventory));

dependenciesToInventory.forEach(dependency ->
        System.out.printf("Source: %s, target: %s%n",
                dependency.getSourceType().getName(),
                dependency.getTargetType().getName()));
```

Nếu đã biết target type, có thể lọc theo tên đầy đủ:

```java
import com.example.shop.inventory.StockAvailability;

var dependenciesToStockAvailability = orders.getDirectDependencies(modules).stream()
        .filter(dependency -> dependency.getTargetType().getName()
                .equals(StockAvailability.class.getName()));
```

Kết quả cho biết những source type nào trong `orders` tham chiếu `StockAvailability`. Nếu có nhiều kết quả, hãy điều tra từng source type vì chúng có thể đại diện cho các use case khác nhau.

## 9. API model cho biết đến đâu?

`ApplicationModuleDependency` cung cấp nguồn gốc ở cấp type. Nó cho biết lớp nguồn và lớp đích, nhưng không cung cấp trực tiếp tên method, field, constructor parameter hoặc số dòng đã tạo ra dependency.

Ví dụ, nếu kết quả chỉ ra:

```text
OrderService -> StockAvailability
```

ta biết lớp `OrderService` phụ thuộc vào `StockAvailability`. Để tìm chính xác constructor, field hoặc method nào tham chiếu type này, hãy dùng Find Usages của IDE hoặc tìm kiếm trong source code với tên type. API model đóng vai trò chỉ đường để thu hẹp phạm vi điều tra.

Ngoài ra, API model chỉ phản ánh các dependency mà Spring Modulith phát hiện trong phạm vi module và classpath được phân tích. Một dependency tới type ngoài application module, type bị loại trừ hoặc code không nằm trong phạm vi import có thể không xuất hiện như một cạnh giữa hai application module.

## 10. Kết hợp truy vết với verification

Đọc dependency model giúp tìm nguồn gốc và hiểu cấu trúc; `verify()` kiểm tra các quy tắc kiến trúc. Hai thao tác bổ trợ nhau:

```java
package com.example.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

import com.example.shop.orders.internal.OrderService;

class ModuleDependencyTests {

    @Test
    void inspectsAndVerifiesOrdersDependencies() {
        ApplicationModules modules = ApplicationModules.of(ShopApplication.class);

        ApplicationModule orders = modules.getModuleByType(OrderService.class)
                .orElseThrow();

        orders.getDirectDependencies(modules).stream().forEach(dependency ->
                System.out.printf("%s -> %s [%s]%n",
                        dependency.getSourceType().getName(),
                        dependency.getTargetType().getName(),
                        dependency.getDependencyType()));

        modules.verify();
    }
}
```

Khi test chạy, phần truy vết in ra các dependency trực tiếp của `orders`; `verify()` sau đó kiểm tra những quy tắc module đã cấu hình, như dependency được phép và truy cập API nội bộ. Việc đọc được một dependency trong model không tự chứng minh dependency đó hợp lệ.

## 11. Quy trình điều tra dependency

Khi phát hiện một cạnh đáng ngờ trong sơ đồ module, hãy làm theo trình tự:

1. Tạo `ApplicationModules` từ lớp gốc của ứng dụng.
2. Tìm module nguồn bằng `getModuleByType()` hoặc `getModuleByName()`.
3. Lấy `getDirectDependencies(modules)` để tập trung vào các cạnh trực tiếp.
4. Duyệt `ApplicationModuleDependencies.stream()` để đọc `getSourceType()`, `getTargetType()`, `getTargetModule()` và `getDependencyType()`.
5. Nếu cần, lọc theo target module, target type hoặc `DependencyType`.
6. Dùng IDE Find Usages để tìm method, field hoặc constructor cụ thể trong source type.
7. Kiểm tra dependency bắc cầu bằng `getAllDependencies()` hoặc `getDependencies(..., DependencyDepth.ALL)` khi cần hiểu phạm vi rộng hơn.
8. Gọi `ApplicationModules.verify()` để xác nhận các quy tắc kiến trúc.

Khi kết hợp module-level graph với source type và target type, ta có thể đi từ một cạnh tổng quát như `orders → inventory` đến đúng lớp tạo ra quan hệ. Điều đó giúp nhóm đánh giá dependency có phản ánh hợp đồng nghiệp vụ hay đang ràng buộc module vào implementation không cần thiết.

Tài liệu tham khảo: [ApplicationModule Javadoc](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModule.html), [ApplicationModuleDependencies Javadoc](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModuleDependencies.html), [ApplicationModuleDependency Javadoc](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModuleDependency.html), [DependencyType Javadoc](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/DependencyType.html).
