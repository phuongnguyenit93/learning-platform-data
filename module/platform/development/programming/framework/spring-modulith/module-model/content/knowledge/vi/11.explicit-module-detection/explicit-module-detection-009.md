# Kiểm tra thiếu annotation sau khi đổi chiến lược

Khi chuyển Spring Modulith từ chiến lược phát hiện mặc định `direct-sub-packages` sang `explicitly-annotated`, cách framework nhận diện application module thay đổi. Trước đó, mọi package con trực tiếp của package chứa lớp Spring Boot application có thể được xem là module. Sau khi chuyển, chỉ những package được đánh dấu bằng Spring Modulith `@ApplicationModule` hoặc jMolecules `@Module` mới được chọn làm module root.

Điều này tạo ra một rủi ro dễ bỏ sót: một package nghiệp vụ quên annotation có thể biến mất khỏi danh sách application module. Các lớp Java trong package đó vẫn có thể tồn tại và được compiler biên dịch; nhưng boundary, dependency và các quy tắc kiến trúc gắn với module có thể không còn được áp dụng như nhóm mong đợi.

Đặc biệt, `ApplicationModules.verify()` kiểm tra module model đã được phát hiện. Nó không biết danh sách module mà nhóm dự định có. Vì vậy, để phát hiện thiếu annotation, cần kiểm tra cả **danh sách module mong đợi** và **các quy tắc kiến trúc của module đã phát hiện**.

## 1. Điều gì thay đổi khi bật `explicitly-annotated`?

Giả sử lớp ứng dụng nằm trong `com.acme.shop` và cấu trúc code như sau:

```text
com.acme.shop
├── ShopApplication.java
├── business
│   ├── order
│   ├── inventory
│   └── customer
├── integration
│   ├── shipping
│   └── payment
└── support
    └── monitoring
```

Với chiến lược mặc định `direct-sub-packages`, các package con trực tiếp `business`, `integration` và `support` là module root. Những package `business.order`, `business.inventory` hoặc `integration.shipping` nằm sâu hơn và thuộc về module cấp trên theo mô hình mặc định.

Khi chuyển sang `explicitly-annotated`, framework chỉ chọn các package được đánh dấu. Nếu nhóm đánh dấu `business.order`, `business.inventory`, `integration.shipping` và `integration.payment`, nhưng quên `business.customer`, module model sẽ chỉ có bốn module được đánh dấu đó. `business.customer` không tự động được tạo thành module chỉ vì nó nằm trong cây package.

```text
Package được đánh dấu                 Kết quả
business.order                       -> module được phát hiện
business.inventory                   -> module được phát hiện
business.customer                    -> thiếu marker, không là module riêng
integration.shipping                 -> module được phát hiện
integration.payment                  -> module được phát hiện
```

Package không có marker vẫn là package Java hợp lệ. Nếu nó nằm dưới một module cha đã được phát hiện, các type của nó có thể thuộc phạm vi module cha. Nếu không có module cha phù hợp, các type đó có thể nằm ngoài các application module mà nhóm định quản lý. Vì vậy, không nên đồng nhất “package vẫn biên dịch” với “module vẫn được phát hiện”.

## 2. Vì sao `verify()` không tự phát hiện mọi annotation bị thiếu?

`ApplicationModules.of(ShopApplication.class)` xây dựng một mô hình từ package root và detection strategy đang cấu hình. `verify()` sau đó kiểm tra những module có trong mô hình: truy cập package nội bộ, dependency được phép, dependency cycle và các quy tắc liên quan.

Nếu package `business.customer` không được đánh dấu, explicit strategy không đưa nó vào danh sách module root. Khi module không tồn tại trong mô hình, `verify()` không có thông tin rằng nhóm dự định package đó phải là một module riêng. Nó không thể tự suy ra ý định nghiệp vụ chỉ từ tên package.

Ví dụ, nếu module `order` vô tình tham chiếu một type trong package `business.customer` chưa được đánh dấu và type đó không thuộc module được phát hiện nào, dependency có thể không được kiểm tra như một dependency giữa hai application module. Một bài test chỉ gọi `verify()` có thể vẫn thành công dù module `customer` bị bỏ sót.

Do đó, cần tách hai câu hỏi:

- **Detection completeness:** tất cả module mà kiến trúc dự kiến có được phát hiện hay không?
- **Architecture verification:** các module đã phát hiện có tuân thủ quy tắc dependency và encapsulation hay không?

`verify()` trả lời câu hỏi thứ hai. Một bài test đối chiếu danh sách module mong đợi với module thực tế sẽ trả lời câu hỏi thứ nhất.

## 3. Đánh dấu từng package bằng `package-info.java`

Với explicit detection, đặt `@ApplicationModule` trong `package-info.java` của từng package được chọn làm module root.

Ví dụ cho `business.order`:

```java
@org.springframework.modulith.ApplicationModule
package com.acme.shop.business.order;
```

Và cho `business.customer`:

```java
@org.springframework.modulith.ApplicationModule
package com.acme.shop.business.customer;
```

Nếu muốn công bố metadata như `displayName` hoặc `allowedDependencies`, có thể khai báo cùng annotation:

```java
@org.springframework.modulith.ApplicationModule(
    displayName = "Customer management",
    allowedDependencies = "shared :: identifiers"
)
package com.acme.shop.business.customer;
```

Marker phải nằm đúng package dự định làm module. Đặt annotation ở `com.acme.shop.business` không tự đánh dấu tất cả package con `order`, `inventory` và `customer` thành các module độc lập.

Chiến lược explicit được bật trong cấu hình ứng dụng:

```yaml
spring:
  modulith:
    detection-strategy: explicitly-annotated
```

Hoặc:

```properties
spring.modulith.detection-strategy=explicitly-annotated
```

Đảm bảo cấu hình này được nạp trong môi trường dùng để tạo module model, bao gồm cả test kiến trúc. Nếu test và runtime sử dụng detection strategy khác nhau, kết quả kiểm tra có thể không phản ánh cấu trúc thực tế của ứng dụng.

## 4. Duy trì danh sách module mong đợi trong test

Một cách trực tiếp để phát hiện package bị quên annotation là khai báo danh sách root package dự kiến trong test và so sánh với danh sách mà `ApplicationModules` phát hiện.

```java
package com.acme.shop;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.Set;
import java.util.stream.Collectors;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleDetectionTests {

    private static final Set<String> EXPECTED_MODULE_ROOTS = Set.of(
            "com.acme.shop.business.order",
            "com.acme.shop.business.inventory",
            "com.acme.shop.business.customer",
            "com.acme.shop.integration.shipping",
            "com.acme.shop.integration.payment"
    );

    @Test
    void detectsEveryExpectedModule() {
        ApplicationModules modules = ApplicationModules.of(ShopApplication.class);

        Set<String> detectedModuleRoots = modules.stream()
                .map(module -> module.getBasePackage().getName())
                .collect(Collectors.toSet());

        assertEquals(EXPECTED_MODULE_ROOTS, detectedModuleRoots,
                "Detected application module roots must match the expected set");
    }
}
```

Nếu quên `@ApplicationModule` ở `business.customer`, tập `detectedModuleRoots` sẽ thiếu `com.acme.shop.business.customer` và bài test thất bại. Nếu vô tình đánh dấu thêm một package không nên là module, phép so sánh tập hợp cũng phát hiện phần tử thừa.

Ví dụ này giả định ứng dụng dùng một tập module root phẳng như danh sách đã khai báo. Nếu dự án có nested module, shared module hoặc module được đóng góp từ package khác, hãy đưa các root hợp lệ đó vào danh sách kỳ vọng hoặc chia kỳ vọng theo từng nhóm để test phản ánh đúng mô hình thực tế.

## 5. Kiểm tra một module cụ thể bằng type hoặc package

Khi không cần so sánh toàn bộ danh sách, có thể kiểm tra module chứa một type đại diện. Ví dụ, `CustomerManagement` là một type nằm trực tiếp trong package root của module `customer`:

```java
package com.acme.shop;

import static org.junit.jupiter.api.Assertions.assertTrue;

import com.acme.shop.business.customer.CustomerManagement;
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class CustomerModuleDetectionTests {

    @Test
    void customerPackageIsDetectedAsItsOwnModule() {
        ApplicationModules modules = ApplicationModules.of(ShopApplication.class);

        boolean detectedAsOwnModule = modules.getModuleByType(CustomerManagement.class)
                .map(module -> module.getBasePackage().getName()
                        .equals("com.acme.shop.business.customer"))
                .orElse(false);

        assertTrue(detectedAsOwnModule,
                "Customer package must be detected as an application module root");
    }
}
```

So sánh `getBasePackage().getName()` giúp xác nhận type thuộc đúng module root dự kiến. Điều này quan trọng khi có nested module: chỉ kiểm tra `getModuleByType(...).isPresent()` có thể chưa đủ, vì type vẫn có thể thuộc một module cha trong khi module con mà nhóm mong đợi chưa được phát hiện.

Một cách tương tự là kiểm tra package:

```java
boolean customerPackageDetected = modules.stream()
        .anyMatch(module -> module.getBasePackage().getName()
                .equals("com.acme.shop.business.customer"));
```

`getModuleForPackage()` hữu ích để hỏi package đang thuộc module nào. Tuy nhiên, nếu mục tiêu là xác nhận package đó chính là một module root riêng, hãy so sánh base package của module trả về với package mong đợi, thay vì chỉ kiểm tra `Optional` có giá trị.

## 6. Kiểm tra annotation và module model là hai lớp kiểm tra khác nhau

Có thể kiểm tra trực tiếp package annotation bằng reflection:

```java
Package customerPackage = CustomerManagement.class.getPackage();

boolean hasModuleMarker = customerPackage.isAnnotationPresent(
        org.springframework.modulith.ApplicationModule.class);
```

Tuy nhiên, kiểm tra reflection đơn thuần không chứng minh rằng Spring Modulith đã nhận package đó theo detection strategy hiện hành. Nó chỉ kiểm tra annotation có hiện diện trong runtime package metadata hay không. Ngược lại, kiểm tra `ApplicationModules` xác nhận kết quả mà framework thực sự đưa vào module model.

Vì vậy, bài test danh sách root package thường là tín hiệu có giá trị hơn cho yêu cầu “không được thiếu module”. Nếu nhóm muốn chẩn đoán nguyên nhân cụ thể, có thể bổ sung kiểm tra annotation hoặc kiểm tra vị trí file `package-info.java`, nhưng không nên thay thế kiểm tra module model bằng reflection.

## 7. Kết hợp completeness test với `verify()`

Sau khi xác nhận tất cả module dự kiến đã xuất hiện, chạy `verify()` để kiểm tra dependency và encapsulation:

```java
package com.acme.shop;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.Set;
import java.util.stream.Collectors;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ApplicationArchitectureTests {

    private final ApplicationModules modules =
            ApplicationModules.of(ShopApplication.class);

    @Test
    void detectsExpectedModuleRoots() {
        Set<String> expected = Set.of(
                "com.acme.shop.business.order",
                "com.acme.shop.business.inventory",
                "com.acme.shop.business.customer",
                "com.acme.shop.integration.shipping",
                "com.acme.shop.integration.payment"
        );

        Set<String> detected = modules.stream()
                .map(module -> module.getBasePackage().getName())
                .collect(Collectors.toSet());

        assertEquals(expected, detected);
    }

    @Test
    void verifiesModuleDependenciesAndBoundaries() {
        modules.verify();
    }
}
```

Hai test này bảo vệ hai hợp đồng khác nhau:

- Test đầu đảm bảo danh sách module không bị thiếu hoặc thừa so với kiến trúc dự kiến.
- Test thứ hai kiểm tra các module đã được phát hiện có tuân thủ quy tắc kiến trúc hay không.

Nên chạy cả hai trong CI. Nếu chỉ chạy `verify()`, một module bị quên marker có thể không tạo ra vi phạm nào để báo lỗi. Nếu chỉ so sánh danh sách module, test lại không phát hiện dependency sai giữa những module đã có. Kết hợp cả hai giúp kiểm tra đầy đủ hơn.

## 8. Chẩn đoán khi module không xuất hiện

Khi completeness test báo thiếu một root package, hãy kiểm tra theo thứ tự:

| Dấu hiệu | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Package có code nhưng không có trong module model | Thiếu `@ApplicationModule` hoặc `@Module` | Kiểm tra `package-info.java` của đúng package |
| Annotation có trong source nhưng module vẫn không xuất hiện | File khai báo sai package hoặc chưa được biên dịch vào test classpath | Kiểm tra package declaration và output của source set |
| Một module cha xuất hiện nhưng module con mong đợi không có | Package con chưa được đánh dấu thành nested module | Kiểm tra marker ở package con và expected root set |
| Module xuất hiện trong môi trường này nhưng mất ở môi trường khác | Detection property hoặc custom strategy khác nhau | Kiểm tra cấu hình được nạp trong test/runtime profile |
| Có module ngoài dự kiến trong tập phát hiện | Một package đã được đánh dấu thừa hoặc custom strategy chọn quá rộng | Xem base package của từng module và thu hẹp marker/strategy |
| Module bị phát hiện nhưng `verify()` thất bại | Dependency hoặc package access vi phạm quy tắc | Đọc violation và sửa quan hệ API/dependency tương ứng |

Khi dùng explicit detection, đừng chỉ tìm annotation bằng tìm kiếm chuỗi toàn repository. Một marker có thể nằm trong package cha hoặc package con không đúng ý định. Điều cần xác nhận là annotation nằm ở đúng package root và module model trả về đúng base package đó.

## 9. Chuyển đổi từ default sang explicit theo từng bước

Một quy trình chuyển đổi có kiểm soát có thể thực hiện như sau:

1. **Ghi nhận module hiện tại:** tạo `ApplicationModules` với chiến lược mặc định và lưu danh sách root package đang được phát hiện.
2. **Chọn module mục tiêu:** xác định package nào thực sự đại diện cho capability cần quản lý.
3. **Đánh dấu đầy đủ:** thêm `@ApplicationModule` vào `package-info.java` của từng module mục tiêu; đánh dấu nested module nếu cần.
4. **Bật explicit strategy:** cấu hình `spring.modulith.detection-strategy=explicitly-annotated` trong môi trường cần áp dụng.
5. **So sánh module roots:** chạy completeness test để phát hiện module bị thiếu hoặc thừa.
6. **Kiểm tra dependency:** chạy `ApplicationModules.verify()` và xử lý các vi phạm.
7. **Đưa test vào CI:** giữ cả kiểm tra danh sách module và kiểm tra kiến trúc trong pipeline.

Nếu chuyển đổi một codebase lớn, có thể chia theo từng nhóm package. Tuy nhiên, mỗi giai đoạn phải có danh sách module kỳ vọng rõ ràng. Tránh bật explicit strategy trước khi nhóm thống kê và đánh dấu các package module, vì những package bị quên có thể rời khỏi module model mà không tạo ra lỗi biên dịch.

## 10. Những nhầm lẫn thường gặp

| Nhận định | Cách hiểu chính xác |
| --- | --- |
| `verify()` sẽ báo mọi package thiếu `@ApplicationModule`. | `verify()` kiểm tra module đã phát hiện; nó không biết danh sách module mà nhóm dự định có. |
| Package không có annotation sẽ bị xóa khỏi ứng dụng. | Code vẫn tồn tại và có thể biên dịch; package chỉ không được chọn làm module root theo explicit strategy. |
| Chỉ cần kiểm tra `getModuleByType(...).isPresent()`. | Type có thể thuộc module cha; cần xác nhận base package đúng với module root dự kiến. |
| Thấy annotation ở một package cha nghĩa là mọi package con đều thành module. | Marker áp dụng cho package được khai báo; nested package cần được đánh dấu riêng nếu muốn thành nested module. |
| Tìm chuỗi `@ApplicationModule` là đủ để kiểm tra. | Cần xác nhận module model thực tế, vì annotation có thể nằm sai package hoặc không được nạp trong test classpath. |
| Test discovery và test verification là một. | Discovery completeness kiểm tra danh sách module; verification kiểm tra dependency và boundary của mô hình đó. |

## 11. Ghi nhớ

Sau khi chuyển sang `explicitly-annotated`, Spring Modulith chỉ nhận package được đánh dấu bằng `@ApplicationModule` hoặc jMolecules `@Module`. Package quên marker có thể không còn là module độc lập, dù code vẫn biên dịch. `ApplicationModules.verify()` không tự biết module nào bị bỏ sót vì nó chỉ kiểm tra mô hình đã phát hiện.

Hãy duy trì một danh sách module root mong đợi và so sánh với `modules.stream()` bằng `getBasePackage().getName()`. Với module cụ thể, có thể dùng `getModuleByType()` rồi xác nhận base package chính xác. Sau đó chạy `verify()` để kiểm tra dependency và encapsulation. Hai lớp test này nên cùng tồn tại trong CI để phát hiện cả module bị thiếu lẫn module có boundary sai.

## Tài liệu tham khảo

- [Spring Modulith Reference — Customizing Module Detection](https://docs.spring.io/spring-modulith/reference/fundamentals.html)
- [Spring Modulith API — `ApplicationModules`](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModules.html)
- [Spring Modulith API — `ApplicationModuleDetectionStrategy`](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModuleDetectionStrategy.html)
- [Spring Modulith Reference — Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html)
