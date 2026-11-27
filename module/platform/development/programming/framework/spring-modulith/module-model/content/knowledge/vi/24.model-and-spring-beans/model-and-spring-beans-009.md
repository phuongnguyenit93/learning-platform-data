# Kiểm tra bean dependency bằng ví dụ thực tế

Trong một modular monolith, Spring bean thường là cách một module cung cấp chức năng cho module khác. Ví dụ, `orders` cần tra cứu sản phẩm từ `catalog`; `OrderService` có thể inject một bean triển khai hợp đồng `ProductCatalog`. Khi số lượng bean dependency tăng lên, ta cần biết bean nào tạo ra quan hệ, module đích là module nào và quan hệ đó có đang kéo quá nhiều implementation vào module sử dụng hay không.

Spring Modulith cung cấp hai góc nhìn để điều tra:

- `ApplicationModule.getSpringBeans()` cho biết các Spring bean type thuộc một module và metadata như bean có được xem là API bean hay không.
- `ApplicationModule.getDirectDependencies(...)` cùng `ApplicationModuleDependency` cho biết các quan hệ dependency thực tế giữa module, bao gồm source type, target type và dependency type.

Hai góc nhìn này bổ sung cho nhau. Danh sách bean cho biết module có những component nào; dependency model cho biết component nào đang tham chiếu sang module khác.

## 1. Ví dụ: orders sử dụng bean của catalog

Giả sử ứng dụng bán hàng có package tree:

```text
com.example.shop
├── ShopApplication.java
├── catalog
│   ├── ProductCatalog.java
│   ├── ProductView.java
│   └── internal
│       ├── DefaultProductCatalog.java
│       └── ProductRepository.java
└── orders
    └── internal
        └── OrderService.java
```

Module `catalog` công khai hợp đồng tra cứu sản phẩm:

```java
package com.example.shop.catalog;

import java.util.Optional;

public interface ProductCatalog {

    Optional<ProductView> findBySku(String sku);
}
```

Kiểu dữ liệu trả về cũng nằm trong API package:

```java
package com.example.shop.catalog;

import java.math.BigDecimal;

public record ProductView(String sku, String name, BigDecimal price) {
}
```

Implementation được giữ trong package nội bộ:

```java
package com.example.shop.catalog.internal;

import com.example.shop.catalog.ProductCatalog;
import com.example.shop.catalog.ProductView;
import org.springframework.stereotype.Service;

import java.util.Optional;

@Service
class DefaultProductCatalog implements ProductCatalog {

    private final ProductRepository repository;

    DefaultProductCatalog(ProductRepository repository) {
        this.repository = repository;
    }

    @Override
    public Optional<ProductView> findBySku(String sku) {
        return repository.findBySku(sku)
                .map(product -> new ProductView(
                        product.getSku(), product.getName(), product.getPrice()));
    }
}
```

Module `orders` inject hợp đồng `ProductCatalog`:

```java
package com.example.shop.orders.internal;

import com.example.shop.catalog.ProductCatalog;
import org.springframework.stereotype.Service;

@Service
public class OrderService {

    private final ProductCatalog productCatalog;

    OrderService(ProductCatalog productCatalog) {
        this.productCatalog = productCatalog;
    }

    void validateProduct(String sku) {
        var product = productCatalog.findBySku(sku)
                .orElseThrow(() -> new IllegalArgumentException("Không tìm thấy sản phẩm"));

        // Tiếp tục xử lý đơn hàng bằng dữ liệu công khai.
    }
}
```

Ở đây, `OrderService` là bean nguồn trong module `orders`; `DefaultProductCatalog` là bean triển khai trong module `catalog`; `ProductCatalog` là type hợp đồng mà `orders` tham chiếu.

## 2. Tạo mô hình application module

Đầu tiên, tạo mô hình từ lớp Spring Boot application:

```java
package com.example.shop;

import com.example.shop.catalog.ProductCatalog;
import com.example.shop.orders.internal.OrderService;
import org.springframework.modulith.core.ApplicationModules;

ApplicationModules modules = ApplicationModules.of(ShopApplication.class);
```

Tìm module sở hữu các type cần kiểm tra:

```java
var orders = modules.getModuleByType(OrderService.class)
        .orElseThrow(() -> new IllegalStateException("Không tìm thấy module orders"));

var catalog = modules.getModuleByType(ProductCatalog.class)
        .orElseThrow(() -> new IllegalStateException("Không tìm thấy module catalog"));
```

`getModuleByType(Class<?>)` trả về module chứa type được truyền vào. Ta dùng nó để xác định module nguồn và module đích trước khi xem bean hoặc dependency.

## 3. Liệt kê Spring bean trong từng module

`ApplicationModule.getSpringBeans()` trả về danh sách `SpringBean` thuộc module. `SpringBean` là mô hình về **kiểu bean**, không phải một instance đang chạy trong `ApplicationContext`.

```java
import org.springframework.modulith.core.SpringBean;

System.out.println("Beans in orders:");
for (SpringBean bean : orders.getSpringBeans()) {
    System.out.printf("%s, apiBean=%s%n",
            bean.getFullyQualifiedTypeName(),
            bean.isApiBean());
}

System.out.println("Beans in catalog:");
for (SpringBean bean : catalog.getSpringBeans()) {
    System.out.printf("%s, apiBean=%s%n",
            bean.getFullyQualifiedTypeName(),
            bean.isApiBean());
}
```

Các phương thức đáng chú ý của `SpringBean`:

| Phương thức | Ý nghĩa |
|---|---|
| `getFullyQualifiedTypeName()` | Tên đầy đủ của kiểu bean |
| `getType()` | `JavaClass` đại diện cho kiểu bean trong mô hình ArchUnit |
| `isApiBean()` | Bean được xem là API bean nếu type công khai thuộc API package hoặc implementation thực thi một API interface được công khai |
| `isAssignableTo(Class<?>)` | Kiểm tra bean có thể gán cho kiểu được truyền vào không |
| `getInterfacesWithinModule()` | Các interface mà bean triển khai và nằm trong cùng application module |

Trong ví dụ, `DefaultProductCatalog` nằm trong `catalog.internal`, nhưng nó triển khai `ProductCatalog` là interface công khai. Vì vậy, `SpringBean.isApiBean()` có thể xem implementation này là API bean thông qua interface mà nó triển khai. Điều đó không có nghĩa consumer nên import trực tiếp implementation class.

## 4. Tìm bean triển khai một API cụ thể

Overload `getSpringBeans(Class<?>)` trả về các bean có kiểu assignable với kiểu được truyền vào. Đây là cách hữu ích để tìm implementation của một interface:

```java
var productCatalogBeans = catalog.getSpringBeans(ProductCatalog.class);

for (SpringBean bean : productCatalogBeans) {
    System.out.printf("Provider: %s, apiBean=%s%n",
            bean.getFullyQualifiedTypeName(),
            bean.isApiBean());
}
```

Với ví dụ trên, danh sách có thể chứa `DefaultProductCatalog`, vì class này triển khai `ProductCatalog`.

Phương thức này giúp trả lời câu hỏi: module `catalog` có những bean type nào có thể cung cấp hợp đồng `ProductCatalog`? Nó không trả về tên bean trong Spring, qualifier, profile đang hoạt động hoặc instance thực tế được chọn khi ứng dụng chạy.

## 5. Truy vấn bean dependency giữa các module

Danh sách bean không cho biết quan hệ inject. Để tìm dependency giữa module, dùng `getDirectDependencies(...)` và lọc theo `DependencyType.USES_COMPONENT`:

```java
import org.springframework.modulith.core.ApplicationModuleDependency;
import org.springframework.modulith.core.DependencyType;

var beanDependencies = orders.getDirectDependencies(
        modules, DependencyType.USES_COMPONENT);

for (ApplicationModuleDependency dependency : beanDependencies.stream().toList()) {
    System.out.printf(
            "%s --[%s]--> %s (module: %s)%n",
            dependency.getSourceType().getName(),
            dependency.getDependencyType(),
            dependency.getTargetType().getName(),
            dependency.getTargetModule().getDisplayName());
}
```

Với ví dụ `OrderService` inject `ProductCatalog`, kết quả minh họa có dạng:

```text
com.example.shop.orders.internal.OrderService
  --[USES_COMPONENT]-->
com.example.shop.catalog.ProductCatalog
  (module: Catalog)
```

`ApplicationModuleDependency` cung cấp các thông tin:

- `getSourceType()`: type tạo ra dependency, trong ví dụ là `OrderService`.
- `getTargetType()`: type được tham chiếu, trong ví dụ là `ProductCatalog`.
- `getTargetModule()`: module sở hữu type đích, trong ví dụ là `catalog`.
- `getDependencyType()`: loại dependency, trong ví dụ là `USES_COMPONENT`.

Một module có thể có nhiều bean dependency tới cùng module đích. Vì vậy, hãy duyệt từng dependency nếu cần tìm bean nguồn và type đích cụ thể; `uniqueModules()` chỉ phù hợp khi muốn lấy danh sách module đích không trùng lặp.

## 6. Phân biệt USES_COMPONENT với các dependency khác

Spring Modulith phân loại các quan hệ module bằng `DependencyType`:

| Loại | Ý nghĩa | Có phải bean dependency không? |
|---|---|---|
| `USES_COMPONENT` | Module nguồn phụ thuộc vào component của module đích; module đích cần được bootstrap để chạy module nguồn | Có |
| `EVENT_LISTENER` | Module nguồn khai báo listener cho event do module đích công bố | Không phải component injection |
| `ENTITY` | Module nguồn tham chiếu entity của module đích | Không nhất thiết |
| `DEFAULT` | Dependency type thông thường không thuộc các nhóm chuyên biệt ở trên | Không nên mặc định xem là bean injection |

Khi mục tiêu là kiểm tra bean dependency, lọc `USES_COMPONENT` giúp tập trung vào các quan hệ component. Nếu muốn xem mọi loại dependency trực tiếp của module, gọi `getDirectDependencies(modules)` mà không truyền bộ lọc.

Điểm khác biệt quan trọng là `EVENT_LISTENER` không yêu cầu module phát hành event phải được bootstrap chỉ để chạy module listener. Ngược lại, `USES_COMPONENT` biểu thị dependency component khiến module đích cần có mặt trong bootstrap của module nguồn.

## 7. Kết hợp bean inventory và dependency để tìm coupling

Ta có thể kết hợp hai API để đọc quan hệ đầy đủ hơn:

```java
var dependencies = orders.getDirectDependencies(
        modules, DependencyType.USES_COMPONENT);

for (var dependency : dependencies.stream().toList()) {
    String sourceName = dependency.getSourceType().getName();
    String targetName = dependency.getTargetType().getName();

    var targetModule = dependency.getTargetModule();
    var targetBeans = targetModule.getSpringBeans();

    System.out.printf("Source bean type: %s%n", sourceName);
    System.out.printf("Target contract/type: %s%n", targetName);
    System.out.printf("Target module: %s%n", targetModule.getDisplayName());

    targetBeans.stream()
            .filter(bean -> bean.getFullyQualifiedTypeName().equals(targetName))
            .forEach(bean -> System.out.printf(
                    "Matching bean type: %s, apiBean=%s%n",
                    bean.getFullyQualifiedTypeName(),
                    bean.isApiBean()));
}
```

Trong một số trường hợp, target type của dependency là interface, còn bean triển khai interface lại có tên class khác. Khi đó, dùng `targetModule.getSpringBeans(ProductCatalog.class)` hoặc `SpringBean.isAssignableTo(ProductCatalog.class)` để tìm implementation assignable với hợp đồng, thay vì so sánh tên type tuyệt đối.

Ví dụ:

```java
catalog.getSpringBeans(ProductCatalog.class).forEach(bean ->
        System.out.printf("Implementation: %s%n",
                bean.getFullyQualifiedTypeName()));
```

Nhờ vậy, ta có thể lần theo đường đi từ bean nguồn, qua hợp đồng mà nó inject, đến bean type trong module đích có khả năng cung cấp hợp đồng đó.

## 8. Dùng dependency model để đánh giá coupling

Một dependency tới API bean công khai thường là cách tích hợp hợp lệ. Tuy nhiên, số lượng và độ rộng của bean dependency có thể cho thấy mức độ gắn kết giữa hai module.

Ví dụ, nếu `orders` inject nhiều component khác nhau của `inventory`:

```text
orders
 ├── StockAvailability
 ├── StockReservation
 ├── WarehouseConfiguration
 ├── InventoryAdminService
 └── StockRepository
```

Hãy đặt các câu hỏi:

1. `orders` có thực sự cần tất cả các capability này không?
2. Có type nào thuộc package nội bộ hoặc là chi tiết persistence không?
3. Có nhiều bean đang thể hiện một use case có thể được gom sau một API nghiệp vụ gắn kết hơn không?
4. Một số tương tác có phù hợp với event nghiệp vụ một chiều thay vì lời gọi component đồng bộ không?
5. Dependency có đang tạo chu kỳ hoặc làm allow-list quá rộng không?

Không nên đánh giá coupling chỉ bằng số lượng bean. Một module có thể cần vài component chuyên biệt vì chúng đại diện cho các use case khác nhau. Điều cần xem là consumer có phụ thuộc vào những hợp đồng ổn định, có ý nghĩa và thuộc quyền sở hữu của module đích hay không.

Spring Modulith cũng lưu ý rằng nếu một module cần quá nhiều bean từ module khác, đây thường là dấu hiệu coupling cao. Nhóm nên xem lại những dependency có thể thay bằng domain event khi nghiệp vụ cho phép.

## 9. Kiểm tra wiring thực tế bằng ApplicationModuleTest

`ApplicationModules` và `SpringBean` mô tả mô hình tĩnh từ code. Chúng không khởi động Spring `ApplicationContext` và không xác nhận bean instance nào được chọn khi áp dụng `@Primary`, `@Qualifier`, profile hoặc conditional configuration.

Để kiểm tra wiring thực tế, dùng `@ApplicationModuleTest`. Ví dụ, test module `orders` trong chế độ mặc định `STANDALONE` chỉ bootstrap module hiện tại. Nếu `OrderService` cần `ProductCatalog` từ `catalog`, test có thể mock hợp đồng bên ngoài:

```java
package com.example.shop.orders.internal;

import com.example.shop.catalog.ProductCatalog;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

@ApplicationModuleTest
class OrderIntegrationTests {

    @MockitoBean
    ProductCatalog productCatalog;

    @Autowired
    OrderService orderService;

    @Test
    void startsOrdersModuleWithCatalogContractMocked() {
        // Kiểm tra use case orders với hợp đồng catalog được thay bằng mock.
    }
}
```

Spring Boot tạo bean mock cho `ProductCatalog` trong application context được bootstrap cho test. Cách này giữ test tập trung vào module `orders`, trong khi hợp đồng bên ngoài được kiểm soát rõ ràng.

## 10. Chọn bootstrap mode phù hợp

Nếu muốn dùng bean thật từ các module phụ thuộc, có thể chọn bootstrap mode khác:

| Mode | Phạm vi bootstrap |
|---|---|
| `STANDALONE` | Chỉ module đang được test; đây là mặc định |
| `DIRECT_DEPENDENCIES` | Module đang test và các module mà nó phụ thuộc trực tiếp |
| `ALL_DEPENDENCIES` | Module đang test và toàn bộ cây dependency bắc cầu |

Ví dụ, nếu muốn test `orders` cùng các module mà nó phụ thuộc trực tiếp:

```java
@ApplicationModuleTest(
    mode = ApplicationModuleTest.BootstrapMode.DIRECT_DEPENDENCIES
)
class OrderIntegrationTests {

    // Các bean thật của orders và direct dependencies được bootstrap.
}
```

Hãy chọn mode theo mục tiêu test. Nếu đang kiểm tra riêng hành vi của `orders`, mock các bean đích bên ngoài thường giúp test độc lập hơn. Nếu mục tiêu là kiểm tra tích hợp thực sự giữa `orders` và `catalog`, có thể bootstrap các dependency cần thiết.

Nếu một module có nhiều bean reference xuyên module mà test chỉ chạy được khi mở rộng bootstrap rất rộng, hãy xem lại thiết kế dependency. Đừng tự động chọn `ALL_DEPENDENCIES` chỉ để che khuất mức coupling.

## 11. Phân biệt các thao tác kiểm tra

| Thao tác | Trả lời câu hỏi nào? | Có khởi động Spring context không? |
|---|---|---|
| `module.getSpringBeans()` | Module chứa những Spring bean type nào? | Không |
| `module.getSpringBeans(SomeType.class)` | Module có bean type nào assignable với hợp đồng này? | Không |
| `module.getDirectDependencies(modules, USES_COMPONENT)` | Module có component dependency trực tiếp nào? | Không |
| `ApplicationModules.verify()` | Dependency có tuân thủ quy tắc kiến trúc module không? | Không |
| `@ApplicationModuleTest` | Các bean trong module có khởi tạo và wiring được trong phạm vi bootstrap đã chọn không? | Có |

Phân biệt các bước này giúp tránh kết luận quá mức. Một dependency được phát hiện trong model không chứng minh rằng bean runtime đã được tạo thành công; ngược lại, application context khởi động thành công cũng không chứng minh toàn bộ dependency đang đi qua API kiến trúc phù hợp.

## 12. Quy trình kiểm tra bean dependency

Khi muốn rà soát bean dependency của một module, hãy làm theo trình tự:

1. Tạo `ApplicationModules` từ lớp Spring Boot application.
2. Tìm module nguồn và module đích bằng `getModuleByType()`.
3. Duyệt `getSpringBeans()` để biết bean type trong từng module.
4. Dùng `isApiBean()` để xem bean nào được nhận diện là API bean.
5. Gọi `getDirectDependencies(modules, DependencyType.USES_COMPONENT)` để lấy component dependency trực tiếp.
6. Đọc source type, target type và target module của từng dependency.
7. Dùng `getSpringBeans(TargetContract.class)` để tìm bean trong module đích có thể triển khai hợp đồng.
8. Chạy `ApplicationModules.verify()` để kiểm tra boundary, allow-list và chu trình module.
9. Dùng `@ApplicationModuleTest` để xác nhận wiring thực tế; mock dependency ngoài module hoặc chọn bootstrap mode phù hợp.
10. Nếu module phụ thuộc quá nhiều bean bên ngoài, xem lại API, quyền sở hữu use case và khả năng giao tiếp bằng domain event.

Tài liệu tham khảo: [Spring Modulith – Fundamentals](https://docs.spring.io/spring-modulith/reference/fundamentals.html), [Spring Modulith – Integration Testing Application Modules](https://docs.spring.io/spring-modulith/reference/testing.html), [ApplicationModule Javadoc](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModule.html), [SpringBean Javadoc](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/SpringBean.html), [ApplicationModuleDependency Javadoc](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModuleDependency.html), [DependencyType Javadoc](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/DependencyType.html).
