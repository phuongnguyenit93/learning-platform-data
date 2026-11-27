# Kiểm tra model trước và sau exclusion

Khi Spring Modulith phân tích một ứng dụng, `ApplicationModules` tạo ra mô hình trong bộ nhớ từ các package và type mà nó đọc được. Trong một số dự án, có những lớp hoặc package kỹ thuật không nên tham gia vào lần kiểm tra kiến trúc đó, chẳng hạn mã sinh tự động, adapter legacy hoặc phần tích hợp nằm ngoài phạm vi module đang muốn kiểm tra.

Spring Modulith cho phép truyền một predicate vào `ApplicationModules.of(...)` để loại các type hoặc package phù hợp khỏi quá trình kiểm tra. Để hiểu tác động của exclusion, hãy tạo hai mô hình từ cùng một application root: mô hình đầy đủ trước exclusion và mô hình đã áp dụng predicate. Sau đó so sánh module, type và kết quả verification.

## 1. Mô hình ban đầu khi chưa exclusion

Giả sử ứng dụng có cấu trúc:

```text
com.example.shop
├── ShopApplication.java
├── catalog
│   ├── ProductCatalog.java
│   └── internal
│       └── ProductRepository.java
└── orders
    ├── OrderManagement.java
    ├── internal
    │   └── OrderService.java
    └── generated
        ├── GeneratedOrderMapper.java
        └── GeneratedOrderMapperImpl.java
```

Trong ví dụ này, `catalog` và `orders` là application module. Package `orders.generated` chứa mã được sinh tự động. Các lớp này có thể được tạo bởi công cụ mapping hoặc một quy trình build, nên nhóm có thể không muốn chúng tham gia vào kiểm tra dependency của kiến trúc nghiệp vụ.

Tạo mô hình thông thường:

```java
package com.example.shop;

import org.springframework.modulith.core.ApplicationModules;

ApplicationModules completeModel =
        ApplicationModules.of(ShopApplication.class);

completeModel.forEach(System.out::println);
```

`ApplicationModules.of(ShopApplication.class)` dùng package của `ShopApplication` làm điểm bắt đầu phân tích. Mô hình được tạo phản ánh package arrangement và các type được đưa vào phân tích trên classpath.

Lệnh `forEach(System.out::println)` in từng application module cùng thông tin như logical name, base package và các Spring bean được nhận diện. Đây là ảnh chụp hữu ích để hiểu trạng thái ban đầu trước khi thêm bất kỳ quy tắc loại trừ nào.

## 2. Truyền predicate để loại package

Overload của `ApplicationModules.of(...)` nhận hai tham số:

```java
ApplicationModules.of(
        Class<?> modulithType,
        DescribedPredicate<? super JavaClass> ignored)
```

Tham số thứ hai là predicate mô tả những `JavaClass` cần bỏ qua trong quá trình application module inspection. ArchUnit cung cấp các predicate dựng sẵn trong `JavaClass.Predicates`.

Ví dụ, loại package `com.example.shop.orders.generated` cùng toàn bộ package con của nó:

```java
package com.example.shop;

import com.tngtech.archunit.core.domain.JavaClass;
import org.springframework.modulith.core.ApplicationModules;

ApplicationModules filteredModel = ApplicationModules.of(
        ShopApplication.class,
        JavaClass.Predicates.resideInAPackage(
                "com.example.shop.orders.generated.."));

filteredModel.forEach(System.out::println);
```

Predicate `resideInAPackage(...)` chọn các lớp nằm trong package khớp với mẫu đã cung cấp. Hậu tố `..` giúp bao gồm cả package được nêu và các sub-package của nó.

## 3. So sánh model trước và sau exclusion

Ta nên giữ cả hai mô hình để quan sát tác động của predicate. Ví dụ:

```java
package com.example.shop;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.example.shop.orders.OrderManagement;
import com.example.shop.orders.generated.GeneratedOrderMapper;
import com.tngtech.archunit.core.domain.JavaClass;
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ExcludedPackagesTests {

    @Test
    void comparesModelsBeforeAndAfterExclusion() {
        ApplicationModules before =
                ApplicationModules.of(ShopApplication.class);

        ApplicationModules after = ApplicationModules.of(
                ShopApplication.class,
                JavaClass.Predicates.resideInAPackage(
                        "com.example.shop.orders.generated.."));

        System.out.println("=== Model before exclusion ===");
        before.forEach(System.out::println);

        System.out.println("=== Model after exclusion ===");
        after.forEach(System.out::println);

        assertTrue(before.contains(GeneratedOrderMapper.class));
        assertFalse(after.contains(GeneratedOrderMapper.class));
        assertTrue(after.contains(OrderManagement.class));

        after.verify();
    }
}
```

Kết quả mong đợi:

- Mô hình `before` có `GeneratedOrderMapper` vì chưa áp dụng predicate loại trừ.
- Mô hình `after` không chứa type đó trong phạm vi phân tích.
- `OrderManagement` vẫn nằm trong mô hình sau exclusion vì nó không khớp predicate.
- `after.verify()` kiểm tra các quy tắc kiến trúc trên mô hình đã lọc.

`ApplicationModules.contains(Class<?>)` là cách trực tiếp để xác nhận một type có được đưa vào mô hình hay không. Nó hữu ích hơn việc chỉ nhìn output console khi muốn viết assertion ổn định trong test.

## 4. Exclusion ảnh hưởng đến inspection, không sửa package tree

Predicate được truyền vào `ApplicationModules.of(...)` chỉ áp dụng cho mô hình phân tích được tạo bởi lời gọi đó. Nó không xóa file Java, không di chuyển package, không sửa import trong mã nguồn và không loại bean khỏi Spring `ApplicationContext` khi ứng dụng chạy.

Ví dụ, nếu `GeneratedOrderMapper` vẫn được Spring đăng ký bằng `@Component` hoặc được tạo qua cấu hình `@Bean`, việc loại nó khỏi application module inspection không làm Spring ngừng tạo bean đó. Exclusion cũng không thay thế cấu hình component scan, dependency injection hoặc cơ chế đóng gói của Gradle/Maven.

Do đó, hãy diễn giải kết quả đúng phạm vi:

| Thao tác | Tác động |
|---|---|
| `ApplicationModules.of(ShopApplication.class)` | Phân tích application module model với các type phù hợp trên classpath |
| `ApplicationModules.of(ShopApplication.class, ignored)` | Tạo model với những type khớp predicate bị bỏ qua trong inspection |
| Xóa hoặc di chuyển file Java | Thay đổi mã nguồn và có thể thay đổi package arrangement thực tế |
| Thay đổi component scan hoặc bean configuration | Thay đổi những bean Spring đăng ký lúc runtime |

Đây là lý do exclusion thích hợp cho mã kỹ thuật hoặc legacy nằm ngoài phạm vi kiểm tra cụ thể, nhưng không phải giải pháp thay thế cho việc tổ chức lại module khi ranh giới nghiệp vụ đang sai.

## 5. Chọn đúng phạm vi PackageMatcher

Chuỗi truyền cho `resideInAPackage(...)` sử dụng cú pháp matcher của ArchUnit. Hai mẫu sau có phạm vi khác nhau:

| Mẫu | Phạm vi khớp |
|---|---|
| `com.example.shop.orders.generated` | Các lớp nằm trực tiếp trong package `generated` |
| `com.example.shop.orders.generated..` | Các lớp trong `generated` và mọi sub-package của nó |
| `..generated..` | Các package có segment `generated` ở những vị trí phù hợp trong tên package |

Ví dụ, với cấu trúc:

```text
com.example.shop.orders.generated
com.example.shop.orders.generated.mapper
com.example.shop.orders.internal
com.example.shop.catalog.generated
```

Mẫu `com.example.shop.orders.generated` chỉ khớp package `orders.generated`. Mẫu `com.example.shop.orders.generated..` khớp cả package `orders.generated` và `orders.generated.mapper`; nó không khớp `orders.internal` hay `catalog.generated`.

Nếu mục tiêu là loại toàn bộ mã sinh tự động trong nhiều module, một matcher rộng như `..generated..` có thể phù hợp. Tuy nhiên, hãy kiểm tra kỹ phạm vi để tránh loại nhầm các lớp có ý nghĩa nghiệp vụ nhưng tình cờ nằm trong package cùng tên.

## 6. Loại một package dùng chung hoặc adapter ngoài phạm vi

Một trường hợp khác là ứng dụng có package kỹ thuật dùng chung mà nhóm chưa muốn đưa vào module verification:

```text
com.example.shop
├── ShopApplication.java
├── catalog
├── orders
└── infrastructure
    ├── database
    └── messaging
```

Nếu muốn loại toàn bộ `infrastructure` khỏi lần kiểm tra này, có thể dùng:

```java
ApplicationModules modules = ApplicationModules.of(
        ShopApplication.class,
        JavaClass.Predicates.resideInAPackage(
                "com.example.shop.infrastructure.."));

modules.verify();
```

Hãy cân nhắc kỹ trước khi loại một package có nhiều dependency. Nếu `orders` đang phụ thuộc vào adapter hoặc type thuộc `infrastructure`, việc loại chúng khỏi inspection có thể làm các quan hệ đó không còn xuất hiện trong kết quả verification. Điều này có thể phù hợp khi package nằm ngoài phạm vi kiểm tra được xác định rõ, nhưng sẽ che khuất vấn đề nếu mục tiêu là bảo vệ toàn bộ kiến trúc ứng dụng.

Trong nhiều trường hợp, giải pháp bền vững hơn là xác định module sở hữu adapter, đưa hợp đồng cần thiết vào API phù hợp hoặc tạo module riêng cho phần hạ tầng. Chỉ dùng exclusion khi nhóm hiểu rõ lý do và chấp nhận phạm vi không được kiểm tra.

## 7. So sánh kết quả verification

Sau khi xem model trước và sau exclusion, hãy chạy verification trên mô hình phù hợp với mục tiêu.

Nếu muốn biết trạng thái đầy đủ của ứng dụng, hãy kiểm tra mô hình không exclusion:

```java
ApplicationModules completeModel =
        ApplicationModules.of(ShopApplication.class);

completeModel.verify();
```

Nếu package đã chọn thực sự nằm ngoài phạm vi kiến trúc cần kiểm tra, có thể kiểm tra mô hình đã loại trừ:

```java
ApplicationModules focusedModel = ApplicationModules.of(
        ShopApplication.class,
        JavaClass.Predicates.resideInAPackage(
                "com.example.shop.orders.generated.."));

focusedModel.verify();
```

Hai lần verification trả lời hai câu hỏi khác nhau. Mô hình đầy đủ cho biết toàn bộ các type được phân tích có tuân thủ quy tắc module hay không. Mô hình đã lọc cho biết phần còn lại sau khi bỏ qua những type được chỉ định có tuân thủ quy tắc hay không.

Nếu verification chỉ thành công sau exclusion, hãy ghi lại package đã loại và lý do. Không nên xem kết quả đó là bằng chứng toàn bộ ứng dụng đã sạch vi phạm, vì các type bị bỏ qua không còn được kiểm tra trong lần chạy đó.

## 8. Những lỗi thường gặp khi exclusion

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Type vẫn xuất hiện sau exclusion | Matcher chỉ khớp package cha hoặc con khác với dự kiến | Kiểm tra tên package đầy đủ và thêm `..` nếu cần bao gồm sub-package |
| Exclusion loại quá nhiều type | Dùng matcher rộng như `..generated..` hoặc `..infra..` | Thu hẹp matcher theo package đầy đủ của module |
| Module vẫn xuất hiện sau khi loại một sub-package | Module còn những type khác không bị loại | Đây có thể là kết quả mong đợi; kiểm tra `contains()` với type cụ thể |
| Verification thành công sau exclusion nhưng ứng dụng vẫn có dependency đáng ngờ | Type bị loại không còn tham gia kiểm tra | Xem lại model đầy đủ và xác định dependency cần refactor |
| Nghĩ rằng bean đã bị loại khỏi Spring context | Nhầm exclusion của ArchUnit/Spring Modulith với cấu hình runtime | Kiểm tra riêng component scan và bean configuration |

## 9. Quy trình thực hành

Khi cần loại một package khỏi application module inspection, hãy làm theo trình tự:

1. Tạo `ApplicationModules` không exclusion và in toàn bộ model để có baseline.
2. Xác định chính xác package hoặc type không nên tham gia lần kiểm tra này.
3. Tạo mô hình thứ hai bằng overload `ApplicationModules.of(Class, ignoredPredicate)`.
4. In mô hình sau exclusion và dùng `contains(Class<?>)` để xác nhận type được chọn đã bị loại.
5. Kiểm tra một type quan trọng khác vẫn nằm trong model để tránh matcher quá rộng.
6. Gọi `verify()` trên mô hình đã lọc và diễn giải kết quả theo đúng phạm vi exclusion.
7. Ghi lại lý do loại trừ; định kỳ xem lại để có thể đưa package trở lại kiểm tra khi phần legacy hoặc mã sinh tự động đã được xử lý.

Exclusion là một công cụ tinh chỉnh phạm vi phân tích, không phải cách thay đổi cấu trúc ứng dụng. Khi luôn so sánh model trước và sau, nhóm có thể thấy rõ những type nào không còn được kiểm tra, xác nhận phần còn lại vẫn đúng ranh giới và tránh nhầm một lần verification có phạm vi hẹp với kết quả kiểm tra toàn bộ modular monolith.

Tài liệu tham khảo: [Spring Modulith – Excluding Packages](https://docs.spring.io/spring-modulith/reference/fundamentals.html#modules.excluding-packages), [ApplicationModules Javadoc](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModules.html), [ArchUnit PackageMatcher](https://www.archunit.org/userguide/html/000_Index.html#_package_matcher).
