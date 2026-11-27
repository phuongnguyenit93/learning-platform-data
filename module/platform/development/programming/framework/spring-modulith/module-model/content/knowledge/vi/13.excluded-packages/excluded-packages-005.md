# Loại trừ package database khỏi model

Trong một ứng dụng Spring Boot, không phải package nào cũng đại diện cho một năng lực nghiệp vụ cần được Spring Modulith quản lý như application module. Một số package chỉ chứa hạ tầng dùng chung, chẳng hạn cấu hình kết nối database, migration, công cụ khởi tạo schema hoặc adapter phục vụ vận hành. Nếu đưa toàn bộ các lớp này vào module model, chúng có thể làm nhiễu dependency graph và khiến nhóm khó tập trung vào ranh giới nghiệp vụ.

Spring Modulith cho phép loại trừ một số Java type hoặc toàn bộ package khỏi quá trình kiểm tra module bằng overload `ApplicationModules.of(…)` nhận thêm một predicate của ArchUnit. Với package database, ta có thể dùng `JavaClass.Predicates.resideInAPackage(…)` để xác định chính xác những lớp cần bỏ qua.

Điều quan trọng là hiểu đúng phạm vi: exclusion chỉ áp dụng cho module inspection của Spring Modulith. Nó không xóa lớp khỏi ứng dụng, không tắt Spring component scanning và cũng không loại entity hoặc repository khỏi cơ chế khởi tạo của Spring Data.

## 1. Vì sao cần loại trừ package database?

Giả sử ứng dụng bán hàng có package gốc `com.acme.shop`:

```text
com.acme.shop
├── ShopApplication.java
├── order
│   ├── OrderManagement.java
│   └── internal
│       └── OrderRepository.java
├── inventory
│   ├── InventoryManagement.java
│   └── internal
│       └── StockRepository.java
├── customer
│   └── CustomerManagement.java
└── database
    ├── DatabaseConfiguration.java
    ├── MigrationRunner.java
    ├── SchemaInspector.java
    └── internal
        └── ConnectionDiagnostics.java
```

Theo cách phát hiện module mặc định, các package con trực tiếp của `com.acme.shop` có thể được nhận diện là application module. Khi đó, `database` có thể xuất hiện như một module bên cạnh `order`, `inventory` và `customer`, dù nó chỉ chứa hạ tầng dùng chung.

Nhóm có thể muốn module model tập trung vào các capability nghiệp vụ và bỏ qua `database` trong kiểm tra kiến trúc. Ví dụ, `DatabaseConfiguration` tạo `DataSource`, `MigrationRunner` quản lý schema và `SchemaInspector` phục vụ vận hành. Các lớp này không nhất thiết tạo thành một application module có API nghiệp vụ riêng.

Một lý do khác là package database có thể chứa code legacy với các dependency kỹ thuật mà nhóm chưa muốn đưa vào phạm vi kiểm tra module. Exclusion giúp áp dụng Spring Modulith từng bước, nhưng cần được xem là một giới hạn có chủ đích của phạm vi kiểm tra.

## 2. Dùng overload `ApplicationModules.of(…)` với predicate

Spring Modulith cung cấp overload nhận lớp ứng dụng và một `DescribedPredicate` của ArchUnit để xác định các type cần bỏ qua:

```java
ApplicationModules.of(ShopApplication.class, ignoredPredicate);
```

Với package database, dùng `JavaClass.Predicates.resideInAPackage(…)`:

```java
package com.acme.shop;

import com.tngtech.archunit.core.domain.JavaClass;
import org.springframework.modulith.core.ApplicationModules;

class ModuleInspection {

    ApplicationModules modules = ApplicationModules.of(
            ShopApplication.class,
            JavaClass.Predicates.resideInAPackage("com.acme.shop.database..")
    );
}
```

Predicate được truyền vào tham số thứ hai là điều kiện nhận diện các lớp/package cần bỏ qua. Trong ví dụ, mọi lớp thuộc `com.acme.shop.database` và các package con của nó sẽ không tham gia quá trình application module inspection.

Có thể gọi `verify()` ngay trên mô hình đã lọc:

```java
ApplicationModules.of(
        ShopApplication.class,
        JavaClass.Predicates.resideInAPackage("com.acme.shop.database..")
).verify();
```

Đây là API của `ApplicationModules`, không phải thuộc tính cấu hình như `spring.modulith.excluded-packages` và cũng không phải một annotation `@ExcludedPackage`. Predicate được truyền vào lúc tạo từng module model. Vì vậy, các bài test hoặc tác vụ tài liệu hóa muốn dùng cùng phạm vi inspection cần tạo `ApplicationModules` bằng cùng predicate.

## 3. Phân biệt package chính xác và toàn bộ package con

`resideInAPackage(…)` sử dụng cú pháp package matcher của ArchUnit. Hai mẫu thường gặp có phạm vi khác nhau:

| Package identifier | Phạm vi được khớp |
| --- | --- |
| `com.acme.shop.database` | Chỉ các lớp nằm trực tiếp trong package `com.acme.shop.database` |
| `com.acme.shop.database..` | Các lớp trong `com.acme.shop.database` và mọi package con như `database.config`, `database.migration` hoặc `database.internal.jdbc` |

Ví dụ, nếu cấu trúc có:

```text
com.acme.shop.database
├── DatabaseConfiguration.java
├── config
│   └── DataSourceConfiguration.java
├── migration
│   └── MigrationRunner.java
└── internal
    └── ConnectionDiagnostics.java
```

Predicate `resideInAPackage("com.acme.shop.database")` chỉ khớp `DatabaseConfiguration`. Các lớp trong `config`, `migration` và `internal` vẫn nằm ngoài phạm vi khớp.

Predicate `resideInAPackage("com.acme.shop.database..")` khớp cả package `database` và tất cả package con. Đây thường là lựa chọn phù hợp nếu mục tiêu là bỏ qua toàn bộ khu vực hạ tầng database.

ArchUnit cũng hỗ trợ mẫu `..database..` để khớp package có segment `database` ở nhiều vị trí khác nhau trong tên package. Tuy nhiên, mẫu rộng như vậy có thể bỏ qua những package không liên quan. Hãy ưu tiên tên package đầy đủ bắt đầu từ application root nếu chỉ muốn loại trừ một khu vực cụ thể.

## 4. Loại trừ nhiều package cùng lúc

Nếu ứng dụng có nhiều nhóm hạ tầng nằm ngoài phạm vi module model, có thể dùng `resideInAnyPackage(…)`:

```java
ApplicationModules modules = ApplicationModules.of(
        ShopApplication.class,
        JavaClass.Predicates.resideInAnyPackage(
                "com.acme.shop.database..",
                "com.acme.shop.migration..",
                "com.acme.shop.operations.."
        )
);

modules.verify();
```

Predicate này bỏ qua các lớp thuộc một trong những package identifier được liệt kê. Hãy giữ danh sách ngắn và giải thích lý do của từng vùng bị loại trừ. Nếu một package không còn cần được bỏ qua sau khi refactor, hãy gỡ nó khỏi predicate để đưa code trở lại phạm vi kiểm tra.

Đừng dùng mẫu chung như `com.acme.shop..` vì nó sẽ khớp gần như toàn bộ ứng dụng và làm mất ý nghĩa của module inspection. Exclusion cần hẹp đến mức chỉ bao phủ những lớp thật sự nằm ngoài ranh giới mà nhóm muốn kiểm tra.

## 5. Đưa exclusion vào bài test kiến trúc

Một bài test JUnit có thể tạo module model với predicate rồi chạy verification:

```java
package com.acme.shop;

import com.tngtech.archunit.core.domain.JavaClass;
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void verifiesBusinessModulesIgnoringDatabaseInfrastructure() {
        ApplicationModules.of(
                ShopApplication.class,
                JavaClass.Predicates.resideInAPackage(
                        "com.acme.shop.database.."
                )
        ).verify();
    }
}
```

Khi chạy test, Spring Modulith kiểm tra các module còn lại trong module model đã tạo. Các lớp được predicate khớp sẽ không được đưa vào phạm vi application module inspection.

Nếu có nhiều test hoặc công cụ cần dùng chung cấu hình, có thể tạo một phương thức factory trong test support để tránh mỗi nơi khai báo một predicate khác nhau:

```java
package com.acme.shop;

import com.tngtech.archunit.core.domain.JavaClass;
import org.springframework.modulith.core.ApplicationModules;

final class ModuleModels {

    private ModuleModels() {}

    static ApplicationModules businessModules() {
        return ApplicationModules.of(
                ShopApplication.class,
                JavaClass.Predicates.resideInAPackage(
                        "com.acme.shop.database.."
                )
        );
    }
}
```

Test có thể gọi `ModuleModels.businessModules().verify()`. Factory này giúp test architecture, module documentation và các kiểm tra liên quan cùng sử dụng một phạm vi inspection. Nếu ứng dụng cần mô hình đầy đủ bao gồm database module cho một mục đích khác, hãy tạo một factory riêng với predicate phù hợp thay vì dùng nhầm mô hình đã loại trừ.

## 6. Exclusion không thay thế Spring component scanning

Đây là điểm rất dễ nhầm. Predicate của `ApplicationModules.of(…)` chỉ ảnh hưởng đến việc Spring Modulith phân tích code để xây dựng module model. Nó không điều chỉnh cách Spring Boot tìm và đăng ký bean.

Ví dụ, lớp sau vẫn có thể được Spring tạo bean nếu nó nằm trong phạm vi component scan và thỏa mãn cấu hình ứng dụng:

```java
package com.acme.shop.database;

import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class DatabaseConfiguration {
    // Khai báo DataSource, transaction manager hoặc JDBC infrastructure.
}
```

Việc loại trừ `com.acme.shop.database..` khỏi `ApplicationModules` không làm `DatabaseConfiguration` biến mất khỏi Spring ApplicationContext. Spring Boot vẫn thực hiện component scanning theo cấu hình của nó.

Tương tự, exclusion không:

- Xóa các class khỏi source code hoặc bytecode.
- Loại class khỏi runtime classpath.
- Tắt `@EntityScan`, JPA repository scanning hoặc Spring Data repository registration.
- Ngăn Flyway hoặc Liquibase chạy migration.
- Tắt cấu hình `DataSource`, transaction manager hoặc JDBC.

Nếu mục tiêu là ngăn Spring tạo bean hoặc ngăn JPA phát hiện entity, cần dùng cơ chế cấu hình scanning/registration tương ứng. Không dùng predicate của Spring Modulith để giải quyết vấn đề runtime đó.

## 7. Exclusion làm giảm phạm vi kiến trúc được kiểm tra

Loại trừ package database có nghĩa là nhóm chấp nhận không kiểm tra các type nằm trong phạm vi đó như một phần của module model. Điều này có thể phù hợp với migration runner hoặc công cụ vận hành độc lập, nhưng cũng có thể che khuất một dependency cần được quản lý.

Ví dụ, nếu `order` trực tiếp phụ thuộc vào `DatabaseConfiguration` hoặc một lớp truy cập JDBC dùng chung trong package bị loại trừ, module verification có thể không còn mô hình hóa đầy đủ quan hệ với phần hạ tầng đó. Khi ấy, nhóm sẽ mất một tín hiệu kiến trúc về việc module nghiệp vụ đang phụ thuộc vào chi tiết database.

Vì vậy, trước khi loại trừ, hãy phân biệt hai trường hợp:

| Trường hợp | Hướng xử lý |
| --- | --- |
| Package chỉ chứa hạ tầng dùng chung, không phải capability và không cần kiểm tra như application module | Có thể loại trừ bằng predicate hẹp |
| Package chứa repository/adapter thuộc một capability như `order` hoặc `inventory` | Nên giữ trong module sở hữu, thường ở package con `internal` của module đó |
| Package database cung cấp một API nghiệp vụ có consumer rõ ràng | Cân nhắc mô hình hóa thành module hoặc Named Interface phù hợp thay vì loại trừ |
| Chỉ muốn bỏ qua một lớp legacy cụ thể | Dùng predicate chỉ khớp lớp đó thay vì bỏ qua cả package |

Trong modular monolith, repository thường thuộc về module sở hữu dữ liệu hoặc capability. Ví dụ, `OrderRepository` nên nằm trong `order.internal` nếu nó phục vụ riêng nghiệp vụ đơn hàng. Đưa tất cả repository vào một package database toàn cục rồi loại trừ package đó có thể làm mất dấu ownership và che khuất dependency giữa nghiệp vụ với persistence.

## 8. Chọn predicate đủ hẹp và có thể giải thích

Một predicate exclusion nên trả lời được ba câu hỏi:

1. Package hoặc type nào bị bỏ qua?
2. Vì sao chúng nằm ngoài phạm vi kiểm tra module?
3. Khi nào nhóm sẽ xem xét đưa chúng trở lại module model?

Ví dụ, có thể đặt tên predicate để thể hiện ý định:

```java
import com.tngtech.archunit.base.DescribedPredicate;
import com.tngtech.archunit.core.domain.JavaClass;

private static final DescribedPredicate<JavaClass> IGNORED_DATABASE_INFRASTRUCTURE =
        JavaClass.Predicates.resideInAPackage("com.acme.shop.database..");
```

Sau đó dùng:

```java
ApplicationModules modules = ApplicationModules.of(
        ShopApplication.class,
        IGNORED_DATABASE_INFRASTRUCTURE
);
```

Đặt tên predicate giúp reviewer hiểu đây là vùng hạ tầng được chủ động loại khỏi inspection. Có thể ghi lý do ngay cạnh khai báo hoặc trong tài liệu kiến trúc của test. Tránh thêm nhiều pattern chồng lấn mà không rõ chúng đang bỏ qua những lớp nào.

Nếu cần xác minh phạm vi matcher, hãy đối chiếu các ví dụ của ArchUnit `PackageMatcher`: `*` khớp một segment package, còn `..` khớp không hoặc nhiều segment. Việc hiểu đúng pattern rất quan trọng vì một dấu chấm hoặc wildcard sai có thể khiến exclusion quá hẹp hoặc quá rộng.

## 9. Những nhầm lẫn thường gặp

| Nhận định | Cách hiểu chính xác |
| --- | --- |
| Có thể cấu hình `spring.modulith.excluded-packages` để bỏ qua database | API được tài liệu hóa là overload `ApplicationModules.of(…, ignoredPredicate)`; không phải một property exclusion package chung |
| `resideInAPackage("com.acme.shop.database")` bao gồm mọi package con | Mẫu này chỉ khớp package đã nêu; thêm `..` để bao gồm các package con |
| Loại trừ package khỏi module model sẽ tắt Spring bean trong package đó | Predicate chỉ ảnh hưởng module inspection; component scanning của Spring Boot vẫn hoạt động theo cấu hình riêng |
| Exclusion xóa code khỏi ứng dụng | Class vẫn tồn tại trong source, bytecode và runtime classpath |
| Loại trừ database luôn làm kiến trúc tốt hơn | Có thể che khuất dependency từ module nghiệp vụ tới hạ tầng; chỉ loại trừ phần thật sự nằm ngoài phạm vi module cần kiểm tra |
| Mọi repository nên chuyển vào package database chung | Repository thường thuộc module sở hữu dữ liệu; package chung có thể làm mờ ownership |
| Bỏ qua package đồng nghĩa không cần test phần đó nữa | Các test persistence, migration và integration vẫn cần thiết theo yêu cầu ứng dụng; chỉ module inspection không phân tích package đó |

## 10. Ghi nhớ

Để loại trừ package database khỏi Spring Modulith module model, tạo `ApplicationModules` bằng overload nhận predicate:

```java
ApplicationModules.of(
        ShopApplication.class,
        JavaClass.Predicates.resideInAPackage("com.acme.shop.database..")
).verify();
```

Mẫu `com.acme.shop.database` chỉ khớp package chính; `com.acme.shop.database..` khớp package đó và mọi package con. Dùng `resideInAnyPackage(…)` khi cần loại trừ nhiều vùng có chủ đích.

Exclusion chỉ thu hẹp phạm vi phân tích kiến trúc của Spring Modulith. Nó không tắt component scanning, JPA repository scanning, migration hoặc bean runtime. Hãy dùng predicate hẹp, ghi rõ lý do và cân nhắc kỹ những dependency có thể bị che khuất. Nếu repository hoặc adapter thuộc một capability nghiệp vụ, giữ nó trong module sở hữu thường giúp boundary rõ hơn việc đưa tất cả vào một package database toàn cục.

## Tài liệu tham khảo

- [Spring Modulith Reference 2.2 — Fundamentals: Excluding Packages](https://docs.spring.io/spring-modulith/reference/fundamentals.html)
- [Spring Modulith API — `ApplicationModules`](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModules.html)
- [ArchUnit API — `JavaClass.Predicates`](https://javadoc.io/doc/com.tngtech.archunit/archunit/latest/com/tngtech/archunit/core/domain/JavaClass.Predicates.html)
- [ArchUnit User Guide — Package Identifiers](https://www.archunit.org/userguide/html/000_Index.html)
