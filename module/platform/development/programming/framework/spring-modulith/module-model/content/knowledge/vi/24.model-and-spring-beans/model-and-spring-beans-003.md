# Bean interface ở API package

Một application module có thể công khai Spring bean thông qua một interface nằm trong API package, trong khi class triển khai bean được đặt ở package `internal`. Module khác chỉ cần biết interface để inject bean qua constructor; nó không cần import hoặc phụ thuộc vào class triển khai. Đây là cách giữ hợp đồng công khai ổn định và cho phép module sở hữu thay đổi implementation bên trong.

Spring Modulith nhận diện trường hợp này trong mô hình `SpringBean`. Một bean được xem là API bean nếu type của bean là public và nằm trong API package, hoặc bean triển khai một interface được expose trong API package. Vì vậy, implementation class có thể nằm trong package nội bộ mà bean vẫn được xem là cung cấp API thông qua interface công khai.

Trong phạm vi **SPRING_MODULITH_MODULE_MODEL**, cách tổ chức này kết hợp ba cơ chế: `@NamedInterface` xác định package chứa hợp đồng, Spring tạo bean từ implementation nội bộ, và `ApplicationModules.verify()` kiểm tra consumer chỉ tham chiếu API được phép.

## 1. Phân biệt API interface và Spring bean implementation

Giả sử module `inventory` cung cấp chức năng kiểm tra tồn kho. Ta muốn `orders` gọi chức năng đó mà không biết `inventory` đang dùng JPA, JDBC hay một dịch vụ bên ngoài.

Tổ chức package:

```text
com.acme.shop.inventory
├── api
│   ├── package-info.java
│   └── InventoryOperations.java
└── internal
    ├── InventoryOperationsImpl.java
    └── InventoryRepository.java
```

Hai phần có trách nhiệm khác nhau:

- `inventory.api` chứa hợp đồng công khai mà module khác được phép tham chiếu.
- `inventory.internal` chứa class triển khai, repository và các chi tiết chỉ module `inventory` sở hữu.

Interface không tự trở thành Spring bean chỉ vì nó nằm trong API package. Spring cần một implementation được đăng ký thành bean, ví dụ bằng `@Service`, `@Component` hoặc một phương thức `@Bean`. Consumer inject interface; Spring tìm bean có type triển khai interface đó.

## 2. Đánh dấu API package bằng NamedInterface

Vì `api` là package con của module `inventory`, cần công khai nó bằng `@NamedInterface` trong `inventory/api/package-info.java`:

```java
@org.springframework.modulith.NamedInterface("api")
package com.acme.shop.inventory.api;
```

Nếu interface được đặt trực tiếp trong package gốc `com.acme.shop.inventory`, package gốc đã là API mặc định và không cần tạo named interface riêng. Khi đặt hợp đồng trong package con như `api`, annotation này cho Spring Modulith biết package đó được expose.

Khai báo interface công khai trong `InventoryOperations.java`:

```java
package com.acme.shop.inventory.api;

public interface InventoryOperations {

    boolean isAvailable(String sku);
}
```

Interface chỉ mô tả hành vi mà consumer cần. Nó không nên để lộ JPA entity, repository, `EntityManager`, JDBC template hoặc kiểu dữ liệu chỉ có ý nghĩa với implementation.

## 3. Đặt implementation bean trong internal package

Class triển khai nằm trong `inventory.internal` và được đăng ký thành Spring bean:

```java
package com.acme.shop.inventory.internal;

import com.acme.shop.inventory.api.InventoryOperations;
import org.springframework.stereotype.Service;

@Service
public class InventoryOperationsImpl implements InventoryOperations {

    private final InventoryRepository repository;

    public InventoryOperationsImpl(InventoryRepository repository) {
        this.repository = repository;
    }

    @Override
    public boolean isAvailable(String sku) {
        return repository.hasAvailableStock(sku);
    }
}
```

`InventoryRepository` cũng thuộc package nội bộ:

```java
package com.acme.shop.inventory.internal;

import org.springframework.stereotype.Repository;

@Repository
class InventoryRepository {

    boolean hasAvailableStock(String sku) {
        // Truy vấn kho dữ liệu của module inventory.
        return true;
    }
}
```

Class implementation được đặt trong `internal` dù nó có thể là `public`. Từ `public` của Java không có nghĩa type đã trở thành API của Spring Modulith. Quyền truy cập ở cấp module được quyết định bởi package API, named interface và loại module `CLOSED`/`OPEN`.

Trong ví dụ này, `InventoryOperationsImpl` là bean do `@Service` đăng ký. Bean triển khai interface `InventoryOperations`, và interface đó thuộc named interface `inventory::api`. Spring Modulith có thể nhận diện bean là API bean thông qua interface được expose.

## 4. Consumer chỉ inject interface công khai

Module `orders` dùng interface mà không import implementation:

```java
package com.acme.shop.orders.internal;

import com.acme.shop.inventory.api.InventoryOperations;
import org.springframework.stereotype.Service;

@Service
public class OrderPlacement {

    private final InventoryOperations inventory;

    public OrderPlacement(InventoryOperations inventory) {
        this.inventory = inventory;
    }

    public void place(String sku) {
        if (!inventory.isAvailable(sku)) {
            throw new IllegalStateException("Insufficient stock");
        }

        // Tiếp tục xử lý use case đặt hàng.
    }
}
```

`orders` chỉ biết `InventoryOperations`. Spring dependency injection tìm bean `InventoryOperationsImpl` phù hợp khi tạo application context. Consumer không cần biết tên class, repository hoặc công nghệ lưu trữ của `inventory`.

Nếu `orders` import trực tiếp `com.acme.shop.inventory.internal.InventoryOperationsImpl`, consumer đã phụ thuộc vào implementation. Khi `inventory` là module `CLOSED`, dependency đó vi phạm ranh giới ngay cả khi class implementation có modifier `public`.

## 5. Giới hạn dependency bằng allowedDependencies

Để thể hiện rõ `orders` chỉ được dùng named interface `api` của `inventory`, khai báo trong `orders/package-info.java`:

```java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "inventory::api"
)
package com.acme.shop.orders;
```

Biểu thức `inventory::api` gồm logical identifier của module đích và tên named interface. Nó cho phép code trong `orders` tham chiếu các type thuộc `inventory.api`.

Hai khai báo có vai trò riêng:

- `@NamedInterface("api")` công khai package API của module `inventory`.
- `allowedDependencies = "inventory::api"` giới hạn dependency đi ra của module `orders` vào đúng interface đó.

Nếu `orders` cần thêm một API khác của `inventory`, nhóm cần công khai interface phù hợp và cập nhật allowlist có chủ đích. Không nên thêm toàn bộ module hoặc mở module chỉ để giữ một import implementation cũ.

## 6. Vì sao bean implementation trong internal vẫn là API bean?

Spring Modulith cung cấp mô hình `SpringBean` để biểu diễn bean mà nó phát hiện trong application module. Phương thức `SpringBean.isApiBean()` trả về `true` trong hai trường hợp:

1. Type của bean là một public type được expose trong API package của module.
2. Bean triển khai một interface được expose trong API package của module.

Trường hợp thứ hai chính là pattern interface công khai và implementation nội bộ. `InventoryOperationsImpl` nằm trong `inventory.internal`, nhưng nó triển khai `InventoryOperations` thuộc `inventory.api`; do đó bean có thể được nhận diện là API bean.

Điều này không có nghĩa implementation class được đưa vào API package hoặc consumer được phép import class đó. Hợp đồng mà consumer sử dụng vẫn là `InventoryOperations`; `isApiBean()` mô tả bean cung cấp API thông qua type công khai.

Một interface nằm trong API package nhưng không có implementation bean được đăng ký thì vẫn là một type được expose, nhưng Spring không thể inject một bean không tồn tại. Cần kiểm tra cả metadata kiến trúc và wiring của application context.

## 7. Component scanning và bean registration

Với cấu trúc package nằm dưới root package của ứng dụng, `@SpringBootApplication` thường kích hoạt component scanning cho cả API và internal package:

```java
package com.acme.shop;

import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ShopApplication {
}
```

Spring có thể phát hiện `@Service` và `@Repository` trong `com.acme.shop.inventory.internal`, rồi đăng ký bean tương ứng. Spring Modulith vẫn xem package đó là nội bộ của module `inventory`; component scanning không biến package thành API.

Có thể đăng ký bean bằng `@Bean` trong một configuration class nội bộ thay cho `@Service`:

```java
package com.acme.shop.inventory.internal;

import com.acme.shop.inventory.api.InventoryOperations;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class InventoryBeanConfiguration {

    @Bean
    InventoryOperations inventoryOperations(InventoryRepository repository) {
        return new InventoryOperationsImpl(repository);
    }
}
```

Trong cả hai cách, điều quan trọng là có bean triển khai interface và bean đó được tạo trong module sở hữu. Annotation `@NamedInterface` chỉ mô tả API package cho Spring Modulith; nó không đăng ký bean với Spring.

## 8. Kiểm tra API bean bằng ApplicationModule và SpringBean

Spring Modulith cho phép liệt kê các bean trong một module và lọc bean có thể gán cho một type:

```java
import org.springframework.modulith.core.ApplicationModule;
import org.springframework.modulith.core.ApplicationModules;
import org.springframework.modulith.core.SpringBean;

ApplicationModules modules = ApplicationModules.of(ShopApplication.class);

ApplicationModule inventory = modules.getModuleByName("inventory")
    .orElseThrow();

var beans = inventory.getSpringBeans(InventoryOperations.class);

beans.forEach(bean -> System.out.println(
    bean.getFullyQualifiedTypeName() + " -> API bean: " + bean.isApiBean()
));
```

`ApplicationModule.getSpringBeans()` trả về các Spring bean mà module chứa. Overload `getSpringBeans(InventoryOperations.class)` lọc các bean assignable với interface được truyền vào; overload này có từ Spring Modulith 1.4. `SpringBean.isApiBean()` cho biết bean có được xem là cung cấp API của module hay không.

Có thể viết test để bảo vệ pattern:

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModule;
import org.springframework.modulith.core.ApplicationModules;

import com.acme.shop.ShopApplication;
import com.acme.shop.inventory.api.InventoryOperations;

class InventoryApiBeanTests {

    @Test
    void exposesInventoryOperationsAsAnApiBean() {
        ApplicationModules modules = ApplicationModules.of(ShopApplication.class);

        ApplicationModule inventory = modules.getModuleByName("inventory")
            .orElseThrow();

        var beans = inventory.getSpringBeans(InventoryOperations.class);

        assertThat(beans).hasSize(1);
        assertThat(beans.get(0).isApiBean()).isTrue();
    }

    @Test
    void verifiesModuleBoundaries() {
        modules().verify();
    }

    private ApplicationModules modules() {
        return ApplicationModules.of(ShopApplication.class);
    }
}
```

Test đầu xác nhận module có bean triển khai interface và bean đó được nhận diện là API bean. Test thứ hai chạy kiểm tra dependency và ranh giới module. Hai kiểm tra bổ sung cho nhau: một kiểm tra cách Spring Modulith phân loại bean, một kiểm tra dependency tổng thể.

## 9. Điều gì xảy ra khi consumer inject implementation trực tiếp?

Giả sử `orders` thay constructor thành:

```java
public OrderPlacement(InventoryOperationsImpl inventory) {
    this.inventory = inventory;
}
```

Consumer phải import class từ `inventory.internal`. Nếu `inventory` là module `CLOSED`, `ApplicationModules.verify()` phát hiện truy cập package nội bộ và báo vi phạm. `allowedDependencies = "inventory::api"` cũng không cấp quyền tham chiếu `inventory.internal`.

Ngoài vi phạm kiến trúc, consumer còn bị ràng buộc vào class triển khai. Khi `inventory` thay `InventoryOperationsImpl` bằng adapter khác, đổi cách lưu trữ hoặc tách implementation, `orders` có thể phải sửa theo.

Nếu interface công khai được giữ ổn định, implementation có thể được thay mà consumer không cần biết:

```text
orders
  └── inject InventoryOperations
          ▲
          │ implements
inventory.internal.InventoryOperationsImpl
          │
          └── có thể thay bằng implementation khác
```

## 10. Các lỗi thường gặp

- **Đặt interface trong internal package.** Consumer không thể tham chiếu nó qua API boundary của module đóng. Hãy chuyển hợp đồng ra package gốc hoặc named interface.
- **Đánh dấu API package nhưng không có bean implementation.** Spring có thể không tìm thấy bean để inject. Kiểm tra `@Service`, `@Component`, `@Bean` và phạm vi component scanning.
- **Đặt implementation trong API package chỉ để consumer inject được.** Cách này làm lộ class triển khai và khuyến khích consumer phụ thuộc vào concrete type. Hãy để implementation trong internal và inject interface.
- **Cho rằng public class luôn là API.** Modifier `public` chỉ là quy tắc Java. Spring Modulith còn xét package có được expose hay không.
- **Cho rằng `@NamedInterface` tạo Spring bean.** Annotation này chỉ công khai package trong mô hình module; bean phải được đăng ký riêng.
- **Inject concrete implementation từ consumer.** Điều này tạo dependency vào internal package và có thể bị `verify()` từ chối.
- **Để interface trả về internal entity hoặc repository type.** Dù interface ở API package, chữ ký vẫn làm rò rỉ chi tiết triển khai. Dùng DTO hoặc value type dành riêng cho hợp đồng.
- **Có nhiều bean triển khai cùng interface nhưng không chọn rõ.** Spring có thể báo `NoUniqueBeanDefinitionException`; dùng `@Primary`, `@Qualifier` hoặc chỉ công khai một implementation phù hợp.
- **Quên allowlist.** Nếu consumer khai báo `allowedDependencies`, phải thêm đúng `module::namedInterface` mà nó sử dụng.

## 11. Quy trình thiết kế bean interface ở API package

Khi một module cần cung cấp Spring bean cho module khác, hãy thực hiện:

1. **Xác định hành vi công khai.** Mô tả thao tác nghiệp vụ mà consumer thực sự cần.
2. **Tạo interface API.** Đặt interface trong package gốc hoặc package con được đánh dấu `@NamedInterface`.
3. **Giữ chữ ký ổn định.** Chỉ dùng các kiểu dữ liệu thuộc hợp đồng công khai; không trả entity hoặc repository nội bộ.
4. **Tạo implementation nội bộ.** Đặt class triển khai trong `internal` hoặc package hạ tầng của module sở hữu.
5. **Đăng ký Spring bean.** Dùng `@Service`, `@Component` hoặc `@Bean` để Spring tạo implementation.
6. **Inject interface ở consumer.** Consumer import và nhận API interface qua constructor.
7. **Khai báo dependency.** Nếu dùng allowlist, thêm đúng `module::namedInterface` vào `allowedDependencies` của consumer.
8. **Kiểm tra API bean.** Dùng `getSpringBeans(Interface.class)` và `SpringBean.isApiBean()` để xác nhận bean được nhận diện đúng.
9. **Chạy verification và integration test.** Dùng `ApplicationModules.verify()` để bảo vệ module boundary và test Spring context để xác nhận bean wiring.

## Kết luận

Một Spring bean có thể cung cấp API qua interface nằm trong package được expose, dù class triển khai ở package `internal`. Spring Modulith nhận diện bean là API bean nếu type của bean nằm trong API package hoặc bean triển khai một interface được expose. Hãy công khai hợp đồng bằng package gốc hoặc `@NamedInterface`, đăng ký implementation nội bộ thành Spring bean và để consumer inject interface qua constructor. Dùng `allowedDependencies` để giới hạn consumer vào đúng API, `SpringBean.isApiBean()` để kiểm tra cách bean được phân loại và `ApplicationModules.verify()` để bảo vệ dependency giữa các module.

## Tài liệu tham khảo

- [Spring Modulith — Fundamentals: Application Modules and Named Interfaces](https://docs.spring.io/spring-modulith/reference/fundamentals.html)
- [Spring Modulith — SpringBean API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/SpringBean.html)
- [Spring Modulith — ApplicationModule API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModule.html)
- [Spring Modulith — Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html)
