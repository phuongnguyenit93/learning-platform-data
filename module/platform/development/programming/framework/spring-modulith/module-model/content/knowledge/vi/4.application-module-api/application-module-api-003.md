# Đọc named interfaces của module

Trong một modular monolith, một mô-đun có thể chứa nhiều package nhưng chỉ một phần trong số đó được phép trở thành API cho mô-đun khác. Spring Modulith biểu diễn những bề mặt công khai này bằng `NamedInterface`. Khi cần kiểm tra một mô-đun đang công khai những gì, ta có thể đọc `NamedInterfaces` từ `ApplicationModule`, xem tên từng interface, liệt kê các kiểu nằm trong đó và tra cứu một interface theo tên.

Trong phạm vi **SPRING_MODULITH_MODULE_MODEL**, việc đọc named interfaces giúp hiểu ranh giới nghiệp vụ và hợp đồng giữa các package trong ứng dụng Spring Boot. Đây là bước hữu ích khi rà soát phụ thuộc, thiết kế `allowedDependencies`, viết kiểm thử kiến trúc hoặc tạo tài liệu mô-đun. Ta đang truy vấn mô hình mà Spring Modulith khám phá từ cấu trúc package và metadata của ứng dụng.

## 1. Named interface là gì?

Một application module thường có package gốc và một số package con. Theo quy ước, package gốc của mô-đun tạo thành API mặc định (unnamed interface). Các package con được xem là phần triển khai nội bộ. Nếu muốn công khai thêm một package cụ thể, ta đánh dấu package đó bằng annotation `@NamedInterface`.

Ví dụ, mô-đun `inventory` có cấu trúc:

```text
com.acme.shop.inventory
├── InventoryManagement.java       // API mặc định của module
├── api
│   ├── package-info.java           // Named Interface "api"
│   └── InventoryOperations.java
└── internal
    └── InventoryRepository.java   // chi tiết nội bộ
```

Trong `api/package-info.java`:

```java
@org.springframework.modulith.NamedInterface("api")
package com.acme.shop.inventory.api;
```

Khai báo này đưa các kiểu thuộc package `com.acme.shop.inventory.api` vào named interface có tên `api`. Mô-đun khác có thể được cho phép phụ thuộc vào bề mặt đó. Các kiểu trong `internal` vẫn là chi tiết triển khai và không được công khai chỉ vì chúng có modifier `public`.

Một named interface không nhất thiết phải là một Java `interface`. Nó là một nhóm kiểu (types) được công khai cùng nhau, có thể bao gồm class, interface, enum hoặc các kiểu khác được Spring Modulith phát hiện trong package được đánh dấu.

## 2. Phân biệt ba kiểu API có tên gần nhau

Spring Modulith có ba kiểu thường gặp khi làm việc với khái niệm này:

| Kiểu | Package | Vai trò |
|---|---|---|
| `@NamedInterface` | `org.springframework.modulith` | Annotation dùng để đánh dấu package hoặc metadata cho package được công khai |
| `NamedInterface` | `org.springframework.modulith.core` | Đại diện cho một interface cụ thể trong mô hình, gồm tên và các kiểu thành viên |
| `NamedInterfaces` | `org.springframework.modulith.core` | Tập hợp các `NamedInterface` của một application module |

Điểm cần nhớ: annotation dùng lúc khai báo cấu trúc mã nguồn; hai lớp trong package `core` dùng lúc đọc mô hình đã được khám phá. `ApplicationModule.getNamedInterfaces()` trả về một `NamedInterfaces`, không trả về annotation.

## 3. Lấy ApplicationModule cần đọc

Trước hết, tạo mô hình ứng dụng bằng `ApplicationModules.of(...)`, sau đó tìm mô-đun theo tên:

```java
import org.springframework.modulith.core.ApplicationModule;
import org.springframework.modulith.core.ApplicationModules;

ApplicationModules modules = ApplicationModules.of(ShopApplication.class);

ApplicationModule inventory = modules.getModuleByName("inventory")
    .orElseThrow(() -> new IllegalStateException("Module inventory not found"));
```

`getModuleByName()` trả về `Optional<ApplicationModule>` vì mô-đun có thể không tồn tại trong mô hình. Xử lý trường hợp không tìm thấy ngay tại điểm tra cứu giúp tránh lỗi null và làm rõ giả định của đoạn code. Thay `ShopApplication.class` bằng lớp Spring Boot application gốc của dự án và dùng đúng logical name của mô-đun.

Nếu chưa biết tên mô-đun, có thể duyệt mô hình trước:

```java
modules.stream()
    .map(ApplicationModule::getName)
    .sorted()
    .forEach(System.out::println);
```

## 4. Đọc tất cả named interfaces của một module

Sau khi lấy được `ApplicationModule`, gọi `getNamedInterfaces()` để nhận tập hợp interface mà mô-đun công khai:

```java
import java.util.Comparator;

import org.springframework.modulith.core.NamedInterface;
import org.springframework.modulith.core.NamedInterfaces;

NamedInterfaces interfaces = inventory.getNamedInterfaces();

interfaces.stream()
    .sorted(Comparator.comparing(NamedInterface::getName))
    .forEach(namedInterface -> {
        String kind = namedInterface.isUnnamed() ? "unnamed" : "named";

        System.out.println(namedInterface.getName() + " (" + kind + ")");

        namedInterface.forEach(type ->
            System.out.println("  - " + type.getName())
        );
    });
```

`NamedInterfaces` là một tập hợp có thể duyệt và cũng cung cấp `stream()`. Mỗi phần tử là một `NamedInterface`. Ta đọc tên bằng `getName()`, dùng `isUnnamed()` để nhận diện API mặc định, rồi duyệt các kiểu thành viên của interface. Mỗi phần tử kiểu ở đây là `JavaClass` của ArchUnit; `getName()` trả về tên đầy đủ của kiểu.

Sắp xếp theo tên giúp đầu ra ổn định và dễ so sánh giữa các lần chạy. Điều này hữu ích khi tạo báo cáo, snapshot hoặc kiểm tra kết quả trong test. Nếu chỉ cần in nhanh, có thể dùng `interfaces.forEach(...)` mà không cần tạo stream.

## 5. Đọc riêng API mặc định và các interface được đặt tên

`NamedInterfaces` bao gồm unnamed interface đại diện cho API mặc định của package gốc. Có thể truy cập nó trực tiếp:

```java
NamedInterface defaultApi = inventory.getNamedInterfaces().getUnnamedInterface();

System.out.println("Default API:");
defaultApi.forEach(type -> System.out.println(type.getName()));
```

Để biết mô-đun có khai báo ít nhất một named interface tường minh hay không, dùng `hasExplicitInterfaces()`:

```java
boolean hasAdditionalApi = inventory.getNamedInterfaces().hasExplicitInterfaces();
```

Phương thức này nói về các interface được khai báo tường minh. Giá trị `false` không có nghĩa mô-đun không có API; package gốc vẫn là API mặc định theo quy ước.

Có thể lọc các interface tường minh khi duyệt:

```java
inventory.getNamedInterfaces().stream()
    .filter(NamedInterface::isNamed)
    .forEach(namedInterface ->
        System.out.println(namedInterface.getName())
    );
```

`isNamed()` và `isUnnamed()` là hai cách diễn đạt rõ ràng khi báo cáo loại interface. Không nên suy luận rằng một interface là nội bộ chỉ vì tên của nó không phải `api`; trạng thái công khai được quyết định bởi mô hình và cách khai báo, không phải bởi tên gọi tự do.

## 6. Tra cứu một named interface theo tên

Khi biết trước tên, dùng `getByName()` thay vì duyệt toàn bộ tập hợp:

```java
NamedInterface api = inventory.getNamedInterfaces()
    .getByName("api")
    .orElseThrow(() -> new IllegalStateException(
        "Named interface 'api' not found in inventory"
    ));

api.forEach(type -> System.out.println(type.getName()));
```

`getByName()` trả về `Optional<NamedInterface>`. Điều này cho phép chương trình phân biệt rõ hai trường hợp: mô-đun có công khai interface cần tìm, hoặc tên đó không có trong mô hình. Nếu việc thiếu interface là lỗi cấu hình kiến trúc, `orElseThrow()` là lựa chọn phù hợp. Nếu interface là tùy chọn, có thể dùng `ifPresent()` hoặc `orElse(...)` theo nghiệp vụ.

Ví dụ kiểm tra một kiểu cụ thể có thuộc interface `api` hay không:

```java
boolean isExposed = api.contains(InventoryOperations.class);
```

Phương thức `contains(Class<?>)` kiểm tra kiểu đã cho có nằm trong named interface hay không. Ta cũng có thể tìm interface chứa kiểu đó bằng cách duyệt:

```java
inventory.getNamedInterfaces().stream()
    .filter(namedInterface -> namedInterface.contains(InventoryOperations.class))
    .map(NamedInterface::getName)
    .forEach(System.out::println);
```

Một kiểu có thể được kiểm tra trong tập interface để hiểu nó được công khai ở bề mặt nào. Khi thiết kế, nên tránh đưa cùng một kiểu vào nhiều interface trừ khi có chủ đích rõ ràng, vì điều đó có thể khiến hợp đồng giữa các mô-đun khó diễn giải.

## 7. Liên hệ named interface với quy tắc phụ thuộc

Đọc named interface có ích nhất khi kết quả được đối chiếu với quy tắc phụ thuộc. Giả sử `orders` chỉ được phép dùng API `api` của `inventory`, có thể khai báo trong `orders/package-info.java`:

```java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "inventory :: api"
)
package com.acme.shop.orders;
```

Tên `inventory` là logical name của mô-đun đích; `api` là tên named interface trong mô-đun đó. Cú pháp `module :: interface` giới hạn phụ thuộc vào phần API đã công khai. Khi không khai báo phụ thuộc tường minh, mô-đun khác vẫn có thể dùng API mặc định ở package gốc theo quy tắc mặc định của Spring Modulith.

Khi đọc kết quả, hãy kiểm tra ba điều:

1. Mô-đun đích có tồn tại trong `ApplicationModules` hay không.
2. `getNamedInterfaces()` có trả về interface mang đúng tên được khai báo hay không.
3. Kiểu mà mô-đun gọi đang nằm trong interface được phép hay thuộc package nội bộ.

Việc nhìn thấy một kiểu trong danh sách named interface chỉ cho biết kiểu đó thuộc bề mặt được công khai của mô-đun. Nó không tự chứng minh rằng mọi phụ thuộc hiện tại đều hợp lệ; việc xác minh quy tắc phải được thực hiện riêng.

## 8. Ví dụ kiểm thử đọc named interface

Ta có thể viết kiểm thử để bảo vệ hợp đồng công khai quan trọng. Ví dụ sau giả định mô-đun `inventory` khai báo interface `api` và đặt `InventoryOperations` trong đó:

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModule;
import org.springframework.modulith.core.ApplicationModules;
import org.springframework.modulith.core.NamedInterface;

class NamedInterfaceTests {

    @Test
    void exposesInventoryOperationsThroughApi() {
        ApplicationModules modules = ApplicationModules.of(ShopApplication.class);

        ApplicationModule inventory = modules.getModuleByName("inventory")
            .orElseThrow();

        NamedInterface api = inventory.getNamedInterfaces()
            .getByName("api")
            .orElseThrow();

        assertThat(api.contains(InventoryOperations.class)).isTrue();
    }
}
```

Kiểm thử này sẽ báo lỗi khi mô-đun không còn công khai interface `api` hoặc kiểu `InventoryOperations` bị chuyển ra khỏi bề mặt đó. Đây là kiểm thử hợp đồng ở mức mô hình, giúp thay đổi package hoặc annotation có chủ đích hơn.

Để kiểm tra toàn bộ cấu trúc và các phụ thuộc, bổ sung kiểm thử kiến trúc riêng:

```java
ApplicationModules.of(ShopApplication.class).verify();
```

Kiểm thử đọc named interface xác nhận một API cụ thể tồn tại. `verify()` kiểm tra các quy tắc kiến trúc mà Spring Modulith áp dụng, bao gồm những vi phạm phụ thuộc giữa mô-đun. Hai kiểm tra bổ trợ nhau và phục vụ các mục tiêu khác nhau.

## 9. Những nhầm lẫn thường gặp

- **Nhầm annotation với lớp mô hình.** `org.springframework.modulith.NamedInterface` là annotation khai báo; `org.springframework.modulith.core.NamedInterface` là đối tượng mô hình được trả về khi đọc cấu trúc.
- **Cho rằng mọi package con đều là API.** Package con thường là nội bộ cho đến khi được công khai bằng named interface hoặc cấu hình mô-đun phù hợp.
- **Cho rằng unnamed interface nghĩa là không có API.** Unnamed interface chính là API mặc định ở package gốc của mô-đun.
- **Cho rằng named interface chỉ chứa Java interface.** Nó có thể chứa nhiều loại Java type; tên gọi mô tả bề mặt công khai theo nhóm.
- **Dùng tên package thay cho tên interface.** Trong `allowedDependencies`, phần sau `::` phải khớp với tên named interface được mô hình nhận diện.
- **Coi việc liệt kê interface là kiểm chứng kiến trúc.** Đọc mô hình giúp quan sát API; hãy chạy `ApplicationModules.verify()` để kiểm tra quy tắc phụ thuộc.

## Kết luận

Để đọc API công khai của một mô-đun, hãy lấy `ApplicationModule` từ `ApplicationModules`, gọi `getNamedInterfaces()` và duyệt hoặc tra cứu các `NamedInterface` cần thiết. `getUnnamedInterface()` cho biết API mặc định, `getByName()` tìm interface tường minh, còn `contains()` giúp xác nhận một kiểu có thuộc bề mặt đó hay không. Kết hợp việc đọc mô hình với `allowedDependencies` và `verify()`, nhóm có thể hiểu rõ mô-đun đang công khai những hợp đồng nào và bảo vệ ranh giới đó trong quá trình phát triển.

## Tài liệu tham khảo

- [Spring Modulith — Fundamentals: Named Interfaces](https://docs.spring.io/spring-modulith/reference/fundamentals.html)
- [Javadoc: ApplicationModule](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModule.html)
- [Javadoc: NamedInterfaces](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/NamedInterfaces.html)
- [Javadoc: NamedInterface](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/NamedInterface.html)
