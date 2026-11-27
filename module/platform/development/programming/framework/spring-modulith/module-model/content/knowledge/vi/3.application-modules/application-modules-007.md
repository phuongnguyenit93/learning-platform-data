# withinRootPackages và nhận diện type thuộc root package

Khi kiểm tra một Java type trong ứng dụng Spring Modulith, ta thường cần trả lời hai câu hỏi khác nhau: type đó có nằm trực tiếp trong package gốc của một application module hay không, và application module nào đang sở hữu type đó? Hai câu hỏi này có vẻ giống nhau nhưng không có cùng ý nghĩa.

`ApplicationModules` cung cấp các API để truy vấn mô hình module đã được phát hiện. Trong đó, `withinRootPackages(String className)` kiểm tra type có nằm trực tiếp trong root package của một module hay không; còn `getModuleByType(…)` tìm module chứa type đó. Hiểu rõ sự khác biệt giúp tránh nhầm lẫn giữa vị trí của type, quyền truy cập API và quyền sở hữu module.

## 1. Tạo mô hình ApplicationModules

`ApplicationModules` là mô hình trong bộ nhớ mô tả các application module mà Spring Modulith phát hiện từ cấu trúc package và cấu hình của ứng dụng. Ta thường khởi tạo mô hình bằng lớp Spring Boot application:

```java
package com.acme.shop;

import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ShopApplication {
}
```

Trong test hoặc công cụ kiểm tra kiến trúc, tạo mô hình như sau:

```java
import org.springframework.modulith.core.ApplicationModules;

ApplicationModules modules = ApplicationModules.of(ShopApplication.class);
```

Theo chiến lược phát hiện mặc định, mỗi package con trực tiếp của package chứa `ShopApplication` được xem là một application module. Ví dụ:

```text
com.acme.shop                         // package của ShopApplication
├── ShopApplication.java
├── order                             // application module: order
│   ├── OrderManagement.java
│   ├── OrderId.java
│   └── internal
│       └── OrderRepository.java
├── inventory                         // application module: inventory
│   ├── InventoryManagement.java
│   └── internal
│       └── StockRepository.java
└── customer                          // application module: customer
    └── CustomerManagement.java
```

Trong ví dụ này, `com.acme.shop` là package gốc của ứng dụng. Các package `com.acme.shop.order`, `com.acme.shop.inventory` và `com.acme.shop.customer` là root package (hay base package) của từng module. `com.acme.shop.order.internal` là package con thuộc module `order`, không tự động trở thành một application module riêng.

Có thể in mô hình để quan sát các module đã được phát hiện:

```java
modules.forEach(System.out::println);
```

Mô hình được tạo ra phụ thuộc vào package của lớp ứng dụng, chiến lược phát hiện module và các tùy chỉnh như `@Modulithic`. Vì vậy, các truy vấn tiếp theo phản ánh đúng mô hình mà ta đã tạo, không phải một phép quét mọi package bất kỳ trong classpath.

## 2. Phân biệt application root package và module root package

Từ “root package” thường gây nhầm lẫn vì có hai cấp khác nhau:

| Khái niệm | Ví dụ | Vai trò |
| --- | --- | --- |
| Package gốc của ứng dụng | `com.acme.shop` | Package chứa lớp `@SpringBootApplication`, làm điểm xuất phát cho phát hiện module mặc định |
| Root package của module | `com.acme.shop.order` | Package nền của module `order`; các type công khai trong package này tạo thành API mặc định của module đóng |
| Package con của module | `com.acme.shop.order.internal` | Chứa triển khai nội bộ theo mặc định |

Vì vậy, khi nói một type nằm trong root package của module, ta đang nói đến package nền của module đó, chẳng hạn `com.acme.shop.order`. Ta không nói rằng type nằm trong package gốc của toàn bộ ứng dụng `com.acme.shop`.

Với một module đóng, Spring Modulith xem các type công khai trong package nền của module là API mặc định. Các package con được xem là nội bộ, trừ khi được công bố rõ ràng qua Named Interface hoặc cấu hình module phù hợp. Java vẫn có thể cho phép import một lớp `public` từ package con, nhưng điều đó không làm cho việc truy cập ấy hợp lệ về mặt kiến trúc.

## 3. `withinRootPackages(String className)` kiểm tra điều gì?

`withinRootPackages` là một phương thức instance của `ApplicationModules` với chữ ký:

```java
boolean withinRootPackages(String className)
```

Phương thức nhận tên của một Java type và trả về `true` nếu type đó nằm trực tiếp trong một trong các root package của những module thuộc mô hình. Các package con không được tính.

Giả sử có hai lớp:

```java
package com.acme.shop.order;

public class OrderManagement {
}
```

```java
package com.acme.shop.order.internal;

public class OrderRepository {
}
```

Ta có thể kiểm tra bằng tên đầy đủ của type:

```java
boolean managementAtRoot = modules.withinRootPackages(
        OrderManagement.class.getName()
);

boolean repositoryAtRoot = modules.withinRootPackages(
        OrderRepository.class.getName()
);
```

Kết quả tương ứng:

| Type | Package của type | Kết quả | Lý do |
| --- | --- | --- | --- |
| `OrderManagement` | `com.acme.shop.order` | `true` | Nằm trực tiếp trong root package của `order` |
| `OrderRepository` | `com.acme.shop.order.internal` | `false` | Nằm trong package con `internal`, không nằm trực tiếp trong root package |
| `InventoryManagement` | `com.acme.shop.inventory` | `true` | Nằm trực tiếp trong root package của `inventory` |

Phương thức này là một phép kiểm tra vị trí package. Nó không nhận `Class<?>` mà nhận `String className`; dùng `SomeType.class.getName()` giúp tránh gõ sai tên đầy đủ. Đối số cần là tên type, không phải chỉ tên package như `com.acme.shop.order`.

Điểm quan trọng là `false` không có nghĩa type không thuộc ứng dụng hoặc không thuộc module nào. Nó chỉ có nghĩa type không nằm trực tiếp trong root package của module.

## 4. `getModuleByType(…)` nhận diện module sở hữu type

Nếu câu hỏi là “Type này thuộc module nào?”, hãy dùng `getModuleByType(…)`. Phương thức có các dạng nhận `Class<?>`, ArchUnit `JavaClass` hoặc tên type:

```java
import java.util.Optional;
import org.springframework.modulith.core.ApplicationModule;

Optional<ApplicationModule> owner = modules.getModuleByType(
        OrderRepository.class
);
```

Trong ví dụ, `OrderRepository` nằm trong `com.acme.shop.order.internal`, nhưng module sở hữu nó vẫn là `order`. Vì thế, `getModuleByType(OrderRepository.class)` có thể trả về module `order` trong khi `withinRootPackages(OrderRepository.class.getName())` trả về `false`.

Có thể so sánh hai API như sau:

| API | Câu hỏi được trả lời | Type trong `order.internal` |
| --- | --- | --- |
| `withinRootPackages(className)` | Type có nằm trực tiếp trong root package của module không? | `false` |
| `getModuleByType(type)` | Module nào chứa type này? | Module `order` |
| `contains(type)` | Type có nằm trong mô hình `ApplicationModules` này không? | `true` nếu type được mô hình bao gồm |

`getModuleByType` trả về `Optional<ApplicationModule>` vì có thể không tìm thấy module chứa type được hỏi. Hãy xử lý trường hợp không có kết quả thay vì giả định mọi type trong classpath đều thuộc một application module:

```java
modules.getModuleByType(OrderManagement.class)
        .ifPresent(module -> System.out.println(module));
```

Khi chỉ có tên type, có thể dùng overload nhận `String`. Tên đầy đủ thường rõ ràng hơn tên đơn giản, đặc biệt khi ứng dụng có nhiều lớp trùng tên:

```java
Optional<ApplicationModule> owner = modules.getModuleByType(
        "com.acme.shop.order.OrderManagement"
);
```

Nếu muốn tìm module từ package thay vì type, dùng `getModuleForPackage(String name)`:

```java
Optional<ApplicationModule> owner = modules.getModuleForPackage(
        "com.acme.shop.order.internal"
);
```

## 5. Root package không đồng nghĩa với toàn bộ API công khai

Trong mô hình module đóng mặc định, package nền của module là API package. Tuy nhiên, một module có thể công bố thêm các package con bằng Named Interface.

Ví dụ, `order` muốn công bố event để module khác sử dụng:

```java
@org.springframework.modulith.NamedInterface("events")
package com.acme.shop.order.events;
```

Type `OrderPlaced` trong `com.acme.shop.order.events` có thể là một phần API được công bố của module `order`. Nhưng nó vẫn nằm trong package con `events`, không nằm trực tiếp trong root package `com.acme.shop.order`.

Do đó:

```java
modules.withinRootPackages(OrderManagement.class.getName());
// true: OrderManagement nằm trong com.acme.shop.order

modules.withinRootPackages(OrderPlaced.class.getName());
// false: OrderPlaced nằm trong com.acme.shop.order.events
```

Đây là điểm cần nhớ khi dùng phương thức này để phân loại type: **`withinRootPackages` không phải phép kiểm tra đầy đủ xem một type có thuộc API công khai hay không.** Nó chỉ kiểm tra type có nằm trực tiếp trong root package hay không. Một type thuộc Named Interface vẫn có thể là API công khai dù kết quả là `false`.

Tương tự, kết quả `true` không kiểm tra modifier `public` của lớp. Một lớp package-private cũng có thể được đặt trực tiếp trong root package; Java visibility và vị trí package là hai thuộc tính riêng. Muốn xác định khả năng truy cập thực tế, cần xem xét cả visibility của type và quy tắc kiến trúc mà Spring Modulith áp dụng.

## 6. Kết hợp các truy vấn để kiểm tra cấu trúc

Trong một bài test kiến trúc, ta có thể kết hợp `withinRootPackages`, `getModuleByType` và `contains` để diễn đạt các giả định rõ ràng:

```java
package com.acme.shop;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.acme.shop.order.OrderManagement;
import com.acme.shop.order.internal.OrderRepository;
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ApplicationModuleLookupTests {

    private final ApplicationModules modules =
            ApplicationModules.of(ShopApplication.class);

    @Test
    void distinguishesModuleRootTypesFromInternalTypes() {
        assertTrue(modules.withinRootPackages(
                OrderManagement.class.getName()
        ));

        assertFalse(modules.withinRootPackages(
                OrderRepository.class.getName()
        ));

        assertTrue(modules.contains(OrderRepository.class));
        assertTrue(modules.getModuleByType(OrderRepository.class).isPresent());
    }
}
```

Bài test trên thể hiện một điểm quan trọng: `OrderRepository` không nằm trực tiếp trong root package, nhưng vẫn thuộc module `order`. Nếu chỉ dùng `withinRootPackages` để kết luận một type có nằm trong module hay không, ta sẽ phân loại sai các lớp triển khai trong package con.

Khi cần quan sát tất cả root package mà mô hình đã nhận diện, API hiện tại còn cung cấp `getRootPackages()`:

```java
modules.getRootPackages().forEach(System.out::println);
```

Kết quả giúp đối chiếu các package nền thực tế với cấu trúc dự kiến. Trong ứng dụng có cấu hình module nâng cao hoặc nhiều package gốc, đây là cách hữu ích để hiểu phạm vi mà mô hình đang kiểm tra.

## 7. Khi nào nên dùng từng API?

Chọn API theo đúng câu hỏi kiến trúc cần trả lời:

| Mục tiêu | API phù hợp |
| --- | --- |
| Xác định type có nằm trực tiếp trong root package của một module | `withinRootPackages(type.getName())` |
| Xác định module chứa một type | `getModuleByType(type)` |
| Kiểm tra type có nằm trong mô hình module đã tạo | `contains(type)` |
| Xác định module chứa một package | `getModuleForPackage(packageName)` |
| Liệt kê các root package của mô hình | `getRootPackages()` |
| Kiểm tra các quy tắc kiến trúc của toàn bộ mô hình | `verify()` |

`withinRootPackages` phù hợp khi ta cần phân biệt type khai báo ngay trong package API mặc định với type nằm trong package con. `getModuleByType` phù hợp khi cần tra cứu module sở hữu type, kể cả type nằm trong package triển khai nội bộ. `verify()` phù hợp khi muốn Spring Modulith thực thi các quy tắc phụ thuộc và đóng gói đã cấu hình.

Đừng dùng `withinRootPackages` như một bộ lọc để chọn module khi khởi tạo `ApplicationModules`. Phương thức này không thay đổi chiến lược phát hiện module và không giới hạn việc quét package; nó chỉ trả lời câu hỏi về vị trí của một type trong mô hình đã được tạo. Việc chọn package gốc ứng dụng, bổ sung package phát hiện hoặc thay đổi detection strategy là một phần cấu hình khác.

## 8. Các nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu chính xác |
| --- | --- |
| Root package của module là package chứa `@SpringBootApplication`. | Package chứa lớp ứng dụng là application root; mỗi module có root/base package riêng, thường là package con trực tiếp của application root. |
| `withinRootPackages` nhận tên package. | Tham số là tên type (`className`); nên truyền `SomeType.class.getName()`. |
| Kết quả `false` nghĩa type không thuộc module nào. | Type trong package con có thể vẫn thuộc module; dùng `getModuleByType` để tra cứu module sở hữu. |
| Kết quả `false` nghĩa type không phải API. | Named Interface có thể công bố type trong package con, dù `withinRootPackages` trả về `false`. |
| Kết quả `true` bảo đảm type là `public`. | Phương thức kiểm tra vị trí package, không kiểm tra Java visibility. |
| `withinRootPackages` thay đổi phạm vi phát hiện module. | Đây là truy vấn boolean trên mô hình đã tạo; cấu hình phát hiện module nằm ở API và cấu hình khác. |

## 9. Ghi nhớ

`ApplicationModules` cho phép nhìn ứng dụng như một mô hình các module thay vì chỉ là một tập hợp package. Trong mô hình đó, root package của mỗi module là package nền, nơi đặt API mặc định; các package con chứa phần triển khai nội bộ hoặc Named Interface được công bố riêng.

`withinRootPackages(String className)` chỉ xác định type có nằm trực tiếp trong một root package hay không. `getModuleByType(…)` trả lời câu hỏi type thuộc module nào, kể cả khi type nằm trong package con. Hai phương thức bổ sung cho nhau và không nên được dùng thay thế nhau.

Khi đọc một type, hãy tách bạch ba điều: type nằm ở package nào, module nào sở hữu nó và type có được công bố như một API hay không. Phân biệt được ba câu hỏi này giúp thiết kế test kiến trúc chính xác và giữ ranh giới của modular monolith rõ ràng.

## Tài liệu tham khảo

- [Spring Modulith API — `ApplicationModules`](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModules.html)
- [Spring Modulith Reference — Fundamentals](https://docs.spring.io/spring-modulith/reference/fundamentals.html)
- [Spring Modulith Reference — Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html)
