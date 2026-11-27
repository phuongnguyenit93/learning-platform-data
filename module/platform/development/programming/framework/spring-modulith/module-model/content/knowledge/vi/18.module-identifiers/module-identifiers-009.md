# Đặt quy tắc tên module cho toàn ứng dụng

Spring Modulith mặc định đặt logical identifier của application module bằng tên package tương đối với root package đang được quét. Ví dụ, module nằm ở `com.acme.shop.catalog` dưới root `com.acme.shop` có identifier là `catalog`. Khi một ứng dụng có nhiều root package, các root khác nhau có thể cùng chứa package con `catalog`, dẫn đến trùng identifier.

Bạn có thể đặt quy tắc định danh dùng chung cho toàn ứng dụng bằng thuộc tính `useFullyQualifiedModuleNames` trên `@Modulithic`. Khi bật thuộc tính này, Spring Modulith dùng tên package đầy đủ làm identifier, ví dụ `com.acme.shop.catalog` và `com.acme.shared.catalog`. Đây là lựa chọn hữu ích khi dùng `additionalPackages` hoặc khi cần tên module không trùng nhau giữa nhiều namespace.

Sau bài học, bạn có thể:

- Phân biệt tên module cục bộ và fully qualified module name.
- Bật quy tắc tên đầy đủ bằng `@Modulithic(useFullyQualifiedModuleNames = true)`.
- Hiểu mối liên hệ giữa root package, `additionalPackages` và module identifier.
- Cập nhật `allowedDependencies` và `sharedModules` theo identifier đang sử dụng.
- Kiểm tra identifier thực tế bằng `ApplicationModules` và `ApplicationModule.getIdentifier()`.

## 1. Logical module identifier được tạo như thế nào?

Spring Modulith phát hiện application module từ các package được chọn bên dưới root package. Mỗi module có một logical identifier để phân biệt nó trong module model. Theo mặc định, identifier là phần tên package nằm bên dưới root package.

Ví dụ, lớp ứng dụng nằm trong `com.acme.shop`:

```text
com.acme.shop                         <- root package
├── ShopApplication.java
├── catalog                           <- module identifier: catalog
├── checkout                          <- module identifier: checkout
└── inventory                         <- module identifier: inventory
```

Với cấu trúc này, identifier cục bộ lần lượt là `catalog`, `checkout` và `inventory`. Tên package đầy đủ của module `catalog` vẫn là `com.acme.shop.catalog`, nhưng identifier mặc định chỉ là `catalog`.

Tên module trong mô hình không phải tên hiển thị của ứng dụng. Thuộc tính `systemName` của `@Modulithic` đặt tên logic của toàn hệ thống để dùng trong tài liệu được tạo; nó không thay đổi module identifier. Tương tự, `ApplicationModuleIdentifier` là value object đại diện cho identifier, không phải cấu hình để tự đặt một bí danh tùy ý cho package.

## 2. Vì sao nhiều root package có thể gây trùng tên?

Một ứng dụng có thể cần phân tích thêm namespace ngoài package của lớp Spring Boot chính. `@Modulithic(additionalPackages = ...)` cho phép khai báo các root package bổ sung. Spring Modulith sẽ chạy module detection cho từng root đó.

Giả sử ứng dụng có cấu trúc:

```text
com.acme.shop                         <- root từ ShopApplication
├── ShopApplication.java
├── catalog                           <- module catalog của shop
└── checkout                          <- module checkout

com.acme.shared                       <- root bổ sung
├── catalog                           <- module catalog dùng chung
└── configuration                     <- module cấu hình dùng chung
```

Khai báo root bổ sung:

```java
package com.acme.shop;

import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.modulith.Modulithic;

@Modulithic(additionalPackages = "com.acme.shared")
@SpringBootApplication
public class ShopApplication {
}
```

Nếu dùng tên cục bộ, hai module `com.acme.shop.catalog` và `com.acme.shared.catalog` đều có identifier `catalog`. Tình huống này gây nhập nhằng khi khai báo phụ thuộc, chọn module trong test hoặc đọc module model.

## 3. Bật fully qualified module names cho toàn ứng dụng

Thêm `useFullyQualifiedModuleNames = true` vào annotation `@Modulithic` trên lớp ứng dụng chính:

```java
package com.acme.shop;

import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.modulith.Modulithic;

@Modulithic(
        additionalPackages = "com.acme.shared",
        useFullyQualifiedModuleNames = true
)
@SpringBootApplication
public class ShopApplication {
}
```

Với cấu hình này, identifier được tạo từ tên package đầy đủ:

| Package module | Identifier mặc định | Identifier khi bật fully qualified |
|---|---|---|
| `com.acme.shop.catalog` | `catalog` | `com.acme.shop.catalog` |
| `com.acme.shop.checkout` | `checkout` | `com.acme.shop.checkout` |
| `com.acme.shared.catalog` | `catalog` | `com.acme.shared.catalog` |
| `com.acme.shared.configuration` | `configuration` | `com.acme.shared.configuration` |

Hai module cùng có tên cục bộ `catalog` giờ có identifier khác nhau. Quy tắc này được áp dụng làm mặc định cho module được tạo trong application module arrangement, bao gồm các root package bổ sung.

Giá trị mặc định của `useFullyQualifiedModuleNames` là `false`. Nếu không có xung đột tên giữa các root package và nhóm muốn identifier ngắn gọn, có thể giữ nguyên mặc định.

## 4. Có thể dùng `@Modulith` thay cho `@Modulithic`

Spring Modulith cũng cung cấp annotation `@Modulith`, kết hợp quy ước Modulith với `@SpringBootApplication` và cung cấp các thuộc tính tương ứng dưới dạng alias. Nếu dự án dùng annotation này cho lớp ứng dụng, có thể bật cùng tùy chọn:

```java
package com.acme.shop;

import org.springframework.modulith.Modulith;

@Modulith(
        additionalPackages = "com.acme.shared",
        useFullyQualifiedModuleNames = true
)
public class ShopApplication {
}
```

Chọn annotation phù hợp với cách dự án đang khai báo lớp ứng dụng. Không cần khai báo cả `@Modulith` và `@Modulithic` trên cùng lớp chỉ để bật quy tắc tên đầy đủ.

## 5. Cập nhật các nơi tham chiếu module identifier

Khi bật fully qualified names, những cấu hình và đoạn code dùng tên module phải dùng identifier mới. Nếu giữ lại tên cục bộ cũ, Spring Modulith sẽ không tìm thấy module theo tên đó hoặc allowlist sẽ không trỏ đến module mong muốn.

### `allowedDependencies`

Giả sử `checkout` cần phụ thuộc vào named interface `api` của module `com.acme.shared.catalog`. Khai báo ở package của `checkout`:

```java
@org.springframework.modulith.ApplicationModule(
        allowedDependencies = "com.acme.shared.catalog::api"
)
package com.acme.shop.checkout;
```

Phần trước `::` là fully qualified module identifier; phần sau là tên named interface. Nếu module tiêu thụ được phép dùng toàn bộ API của module đích, có thể dùng identifier đầy đủ với wildcard phù hợp, chẳng hạn `com.acme.shared.catalog::**`.

### `sharedModules`

Thuộc tính `sharedModules` trên `@Modulithic` khai báo các module luôn được đưa vào bootstrap của module integration test. Khi bật fully qualified naming, hãy dùng identifier đầy đủ ở đây:

```java
@Modulithic(
        additionalPackages = "com.acme.shared",
        useFullyQualifiedModuleNames = true,
        sharedModules = "com.acme.shared.configuration"
)
@SpringBootApplication
public class ShopApplication {
}
```

Nếu một module được đánh dấu shared bằng identifier cục bộ cũ `configuration`, hãy cập nhật thành `com.acme.shared.configuration` sau khi bật tùy chọn.

### Truy vấn module bằng `ApplicationModules`

Khi cần lấy module theo tên, dùng identifier đầy đủ:

```java
import org.springframework.modulith.core.ApplicationModule;
import org.springframework.modulith.core.ApplicationModules;

var modules = ApplicationModules.of(ShopApplication.class);

ApplicationModule catalog = modules
        .getModuleByName("com.acme.shared.catalog")
        .orElseThrow();

System.out.println(catalog.getIdentifier());
System.out.println(catalog.getBasePackage());
```

`getIdentifier()` trả về `ApplicationModuleIdentifier` của module. Bạn cũng có thể tạo value object từ chuỗi bằng `ApplicationModuleIdentifier.of("com.acme.shared.catalog")` khi API cần một identifier. Phương thức này chỉ tạo đối tượng biểu diễn tên đã chọn; nó không bật quy tắc fully qualified và không thay đổi module model.

## 6. Xác minh tên module thực tế

Sau khi thay đổi cấu hình, hãy tạo lại module model từ lớp ứng dụng chính và in các module:

```java
import org.springframework.modulith.core.ApplicationModules;

class ModuleIdentifierInspection {

    void inspect() {
        var modules = ApplicationModules.of(ShopApplication.class);
        modules.forEach(System.out::println);
        modules.verify();
    }
}
```

Đầu ra của từng module hiển thị logical name và base package. Đối chiếu identifier hiển thị với các giá trị đang dùng trong `allowedDependencies`, `sharedModules` và test. Nếu một module không xuất hiện hoặc một dependency không được nhận diện, hãy kiểm tra root package, `additionalPackages` và identifier trước khi thay đổi package Java.

Bạn có thể thêm kiểm tra JUnit để khóa cấu hình tên:

```java
import com.acme.shop.ShopApplication;
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

import static org.assertj.core.api.Assertions.assertThat;

class ModularityTests {

    @Test
    void verifiesApplicationModuleArrangement() {
        var modules = ApplicationModules.of(ShopApplication.class);

        assertThat(modules.getModuleByName("com.acme.shop.catalog")).isPresent();
        assertThat(modules.getModuleByName("com.acme.shared.catalog")).isPresent();

        modules.verify();
    }
}
```

Ví dụ dùng AssertJ để minh họa kiểm tra sự tồn tại của hai identifier không trùng nhau; hãy bổ sung import AssertJ theo dependency test của dự án.

## 7. Trade-off khi chọn tên đầy đủ

| Tiêu chí | Tên cục bộ | Tên package đầy đủ |
|---|---|---|
| Độ ngắn khi khai báo dependency | Ngắn, ví dụ `catalog` | Dài hơn, ví dụ `com.acme.shared.catalog` |
| Nhiều root package có cùng tên module con | Có thể trùng identifier | Phân biệt được bằng package đầy đủ |
| Đọc module model | Dễ nhìn trong ứng dụng một root | Nhìn rõ namespace sở hữu module |
| Đổi package Java | Identifier cục bộ có thể giữ nguyên nếu vị trí tương đối không đổi | Identifier thay đổi theo package đầy đủ |
| Cấu hình `allowedDependencies` và `sharedModules` | Dùng tên ngắn | Phải dùng identifier đầy đủ |

Không nên bật fully qualified names chỉ vì tên đầy đủ có vẻ rõ ràng hơn. Hãy chọn dựa trên cấu trúc root package và yêu cầu tránh xung đột. Nếu ứng dụng chỉ có một root và không có hai module cùng tên cục bộ, identifier ngắn thường dễ đọc và ít thay đổi hơn khi tái cấu trúc package cha.

## 8. Phân biệt naming với module detection

`useFullyQualifiedModuleNames` chỉ quyết định cách tạo identifier từ package đã được chọn làm module. Nó không quyết định package nào được phát hiện và không thay thế detection strategy.

| Cơ chế | Vai trò |
|---|---|
| `spring.modulith.detection-strategy` | Chọn các package được xem là module base package |
| `ApplicationModuleDetectionStrategy` | Tùy chỉnh quy tắc chọn package module |
| `@Modulithic(additionalPackages = ...)` | Bổ sung root package để chạy module detection |
| `@Modulithic(useFullyQualifiedModuleNames = true)` | Dùng tên package đầy đủ làm module identifier |
| `@ApplicationModule(allowedDependencies = ...)` | Giới hạn module identifier hoặc named interface mà module được phép phụ thuộc |

Ví dụ, nếu custom detection strategy chọn `com.acme.shop.catalog`, tùy chọn fully qualified sẽ làm identifier của module đó là `com.acme.shop.catalog`. Nếu strategy không chọn package này làm module, việc bật tên đầy đủ không tự khiến package trở thành module.

## 9. Ghi nhớ

Theo mặc định, Spring Modulith dùng tên package tương đối với root làm logical module identifier. Khi có nhiều root package, các module con cùng tên có thể xung đột. Đặt `useFullyQualifiedModuleNames = true` trên `@Modulithic` hoặc `@Modulith` để dùng package đầy đủ làm identifier trên toàn application module arrangement. Sau khi bật, cập nhật các tham chiếu module trong `allowedDependencies`, `sharedModules` và code truy vấn module. Tùy chọn này điều chỉnh cách đặt tên module đã được phát hiện; nó không thay đổi detection strategy, package boundary hay tạo bí danh tùy ý.

## Tài liệu tham khảo

- [Spring Modulith 2.2.0 – Fundamentals](https://docs.spring.io/spring-modulith/reference/fundamentals.html)
- [Spring Modulith 2.2.0 API – `@Modulithic`](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/Modulithic.html)
- [Spring Modulith 2.2.0 API – `@Modulith`](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/Modulith.html)
- [Spring Modulith 2.2.0 API – `ApplicationModuleIdentifier`](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModuleIdentifier.html)
- [Spring Modulith 2.2.0 API – `ApplicationModuleSource`](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModuleSource.html)
