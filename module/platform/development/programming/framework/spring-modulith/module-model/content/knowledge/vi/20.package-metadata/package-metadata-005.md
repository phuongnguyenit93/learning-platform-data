# Package metadata khác Java module system thế nào?

Spring Modulith và Java Platform Module System (JPMS) đều giúp tổ chức code thành các phần có ranh giới, nhưng chúng mô tả hai loại ranh giới khác nhau. Spring Modulith dùng metadata ở cấp package, thường khai báo trong `package-info.java`, để mô hình hóa application module bên trong một ứng dụng Spring Boot. JPMS dùng descriptor `module-info.java` để định nghĩa một Java module, các module mà nó yêu cầu và những package được export hoặc mở cho reflection.

Một dự án có thể dùng cả hai cơ chế. JPMS quản lý khả năng đọc và truy cập package giữa các Java module; Spring Modulith mô tả và kiểm chứng ranh giới nghiệp vụ giữa các application module, thường nằm trong cùng một ứng dụng và cùng một Java module. Không nên xem `@ApplicationModule` là một cách viết khác của `module-info.java`, hoặc xem `@NamedInterface` tương đương hoàn toàn với `exports`.

Trong phạm vi **SPRING_MODULITH_MODULE_MODEL**, việc phân biệt hai cơ chế giúp nhóm chọn đúng công cụ để xác định API công khai, kiểm soát dependency và kiểm chứng kiến trúc modular monolith.

## 1. Hai cơ chế giải quyết hai bài toán khác nhau

Spring Modulith tập trung vào cấu trúc module nghiệp vụ trong một ứng dụng Spring. JPMS tập trung vào cấu trúc module của nền tảng Java và khả năng truy cập ở cấp JVM.

| Tiêu chí | Spring Modulith package metadata | Java Platform Module System (JPMS) |
|---|---|---|
| Đơn vị được mô tả | Application module trong một ứng dụng Spring Boot | Java module có tên |
| File metadata chính | `package-info.java` | `module-info.java` |
| Annotation/cú pháp | `@ApplicationModule`, `@NamedInterface` | `requires`, `exports`, `opens`, `uses`, `provides` |
| Phạm vi | Package gốc và các package con của module nghiệp vụ | Toàn bộ package thuộc Java module |
| Mục tiêu | Ranh giới nghiệp vụ, API module và dependency giữa các application module | Readability, package accessibility và reflective access giữa các Java module |
| Cách kiểm tra | `ApplicationModules.verify()` và các test kiến trúc | Java compiler, module resolution và quy tắc truy cập của JVM |
| Có tự tạo JAR/module riêng không? | Không | Java module có thể được đóng gói thành modular JAR hoặc chạy trong module path |

Spring Modulith có thể chia một ứng dụng thành `orders`, `inventory` và `customers` mà không cần tạo ba JAR hoặc ba tiến trình. JPMS có thể định nghĩa một Java module chứa toàn bộ ứng dụng đó, rồi quản lý package nào được các Java module khác đọc.

## 2. package-info.java lưu metadata ở cấp package

Trong Java, `package-info.java` là file dành cho Javadoc và package annotation. Khi biên dịch, compiler tạo `package-info.class` để lưu metadata package. Spring Modulith sử dụng package annotation để biết package nào là application module và package nào là API được công khai.

Ví dụ, `orders/package-info.java`:

```java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "inventory::api"
)
package com.acme.shop.orders;
```

File trên gắn metadata cho package `com.acme.shop.orders`. Nó khai báo rằng module `orders` chỉ được phụ thuộc vào named interface `api` của module `inventory` theo quy tắc được nêu.

Một package con có thể được công khai bằng named interface trong `inventory/api/package-info.java`:

```java
@org.springframework.modulith.NamedInterface("api")
package com.acme.shop.inventory.api;
```

Spring Modulith đọc metadata này khi xây dựng mô hình `ApplicationModules`. Nó không làm thay đổi Java package name, không tạo Java module mới và không tự đóng gói code thành một artifact riêng.

## 3. module-info.java là descriptor của JPMS

JPMS được giới thiệu trong Java 9. Một Java module được mô tả bằng `module-info.java` ở gốc source/module. Descriptor khai báo tên module, các module mà nó cần đọc và những package được export hoặc mở.

Ví dụ:

```java
module com.acme.shop {
    requires java.sql;

    exports com.acme.shop.orders.api;
    exports com.acme.shop.inventory.api;

    opens com.acme.shop.orders.persistence;
}
```

Ý nghĩa của các directive trong ví dụ:

- `requires java.sql` khai báo Java module này cần đọc module `java.sql`.
- `exports com.acme.shop.orders.api` cho phép các Java module đọc module này truy cập các public type trong package được export.
- `opens com.acme.shop.orders.persistence` cho phép truy cập reflective sâu vào package đó theo quy tắc JPMS; nó không phải lời khai báo API compile-time tương đương với `exports`.

JPMS còn có `uses` và `provides ... with ...` để mô tả việc sử dụng và cung cấp service theo Java Service Loader. Đây là cơ chế ở cấp Java module, không phải cách khai báo Spring Modulith application event hoặc module dependency.

## 4. @NamedInterface không giống exports

Hai cơ chế có vẻ tương tự vì đều chỉ định package API, nhưng ngữ nghĩa khác nhau.

`@NamedInterface("api")` nói với Spring Modulith rằng package được đánh dấu là một named interface của application module. Consumer có thể tham chiếu nó bằng qualified dependency, ví dụ `inventory::api`.

`exports` nói với JPMS rằng package được export từ một Java module để các Java module khác có quyền đọc module đó có thể truy cập các public type trong package.

| Câu hỏi | `@NamedInterface("api")` | `exports ...` |
|---|---|---|
| Thuộc hệ thống nào? | Spring Modulith | JPMS |
| Đơn vị sở hữu | Application module | Java module |
| Cách tham chiếu | `inventory::api` | Tên package được export, cùng Java module readability |
| Mục đích | Xác định bề mặt API của application module | Cho phép Java module khác truy cập public type trong package |
| Có kiểm tra dependency nghiệp vụ không? | Có thể tham gia `ApplicationModules.verify()` | Không hiểu khái niệm nghiệp vụ của Spring Modulith |

Nếu dự án dùng cả hai cơ chế, một package có thể cần cả `@NamedInterface("api")` trong `package-info.java` và `exports com.acme.shop.inventory.api` trong `module-info.java`, tùy vào consumer và cách triển khai. Annotation Spring Modulith không tự export package cho JPMS; directive `exports` cũng không tự tạo named interface trong mô hình Spring Modulith.

## 5. OPEN của Spring Modulith không giống opens của JPMS

Đây là cặp thuật ngữ rất dễ nhầm:

| Khái niệm | Ý nghĩa |
|---|---|
| `@ApplicationModule(type = OPEN)` | Nới lỏng ranh giới kiến trúc của application module; các kiểu trong module được đưa vào unnamed interface, trừ kiểu đã được gán vào named interface riêng; module khác có thể truy cập internal types theo mô hình Spring Modulith |
| `opens package.name` trong `module-info.java` | Cho phép truy cập reflective sâu vào package của Java module theo quy tắc JPMS |

`OPEN` không tự cấp quyền reflection cho framework trên module path. `opens` không làm package trở thành API công khai của Spring Modulith và không làm `ApplicationModules.verify()` chấp nhận dependency nội bộ.

Ví dụ, nếu module `inventory` là `CLOSED` nhưng JPMS mở package persistence cho reflection:

```java
// module-info.java
module com.acme.shop {
    opens com.acme.shop.inventory.persistence;
}
```

Spring Modulith vẫn có thể xem `inventory.persistence` là nội bộ và từ chối một module khác tham chiếu trực tiếp vào type ở đó. Directive `opens` chỉ giải quyết nhu cầu reflective access của framework hoặc thư viện trong bối cảnh JPMS.

Ngược lại, nếu application module được đánh dấu `OPEN`, điều đó không tự làm cho package internal được export sang một Java module khác. JPMS vẫn yêu cầu directive phù hợp và các quy tắc Java visibility vẫn có hiệu lực.

## 6. Hai cơ chế có thể cùng tồn tại

Một ứng dụng modular monolith có thể dùng một Java module duy nhất nhưng chia thành nhiều Spring Modulith application module:

```text
Java module: com.acme.shop
│
├── Spring Modulith module: orders
│   ├── com.acme.shop.orders
│   └── com.acme.shop.orders.internal
│
├── Spring Modulith module: inventory
│   ├── com.acme.shop.inventory
│   ├── com.acme.shop.inventory.api
│   └── com.acme.shop.inventory.internal
│
└── Spring Modulith module: customers
    ├── com.acme.shop.customers
    └── com.acme.shop.customers.internal
```

Trong cách tổ chức này:

- `module-info.java` quản lý khả năng đọc/truy cập của `com.acme.shop` đối với các Java module khác.
- Các `package-info.java` quản lý metadata của `orders`, `inventory`, `customers` và named interfaces.
- `ApplicationModules.verify()` kiểm tra dependency giữa các application module trong ứng dụng.
- Java compiler và JVM vẫn áp dụng JPMS nếu ứng dụng được biên dịch/chạy như named module trên module path.

Hai cơ chế bổ sung cho nhau. JPMS không thay thế việc mô hình hóa ranh giới nghiệp vụ ở cấp package. Spring Modulith cũng không thay thế Java module descriptor khi dự án cần kiểm soát readability, exports hoặc reflection ở cấp nền tảng.

## 7. JPMS không tự tạo ranh giới nghiệp vụ bên trong cùng một Java module

Giả sử `orders` và `inventory` đều nằm trong Java module `com.acme.shop`. Trong cùng một Java module, code có thể tham chiếu public type của package khác dù package đó không được `exports` ra ngoài Java module. `exports` chủ yếu kiểm soát truy cập từ Java module khác, không chia nhỏ quyền truy cập giữa các package bên trong cùng một Java module.

Do đó, nếu `orders` import `com.acme.shop.inventory.internal.InventoryRepository`, JPMS có thể không ngăn việc này khi cả hai package thuộc cùng `com.acme.shop`. Spring Modulith có thể phát hiện dependency đó và từ chối nếu `inventory` là `CLOSED`.

Đây là lý do Spring Modulith hữu ích trong modular monolith: nó kiểm tra các ranh giới logic nhỏ hơn ranh giới của một Java module hoặc một JAR.

## 8. So sánh enforcement và thời điểm phát hiện vi phạm

Hai cơ chế khác nhau cả về nơi và thời điểm kiểm tra:

| Tình huống | JPMS | Spring Modulith |
|---|---|---|
| Consumer không `requires` Java module cần dùng | Compiler/module resolution báo lỗi readability | Không áp dụng quy tắc `requires` của JPMS |
| Consumer truy cập package không được export từ Java module khác | Compiler/runtime từ chối theo JPMS | Có thể không liên quan nếu package vẫn là API hợp lệ ở cấp application module |
| Consumer trong cùng Java module truy cập package internal của application module khác | JPMS thường không chặn chỉ vì package không export | `verify()` có thể phát hiện vi phạm nếu module đích là `CLOSED` |
| Consumer phụ thuộc vào named interface không được phép | JPMS không biết `allowedDependencies` của Modulith | `verify()` kiểm tra quy tắc application module |
| Framework cần reflection sâu vào package trên module path | Cần `opens` phù hợp | `@ApplicationModule(type = OPEN)` không giải quyết việc này |

Spring Modulith thường được dùng như kiểm tra kiến trúc trong test hoặc build verification. Nó không thay thế compiler enforcement của JPMS. Ngược lại, JPMS không hiểu `ApplicationModule`, `NamedInterface`, `allowedDependencies` hoặc dependency event giữa các application module.

## 9. Ví dụ một module dùng đồng thời hai loại metadata

Một package gốc application module có thể khai báo metadata Spring Modulith trong `package-info.java`:

```java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "customers::api"
)
package com.acme.shop.orders;
```

Package API của `customers`:

```java
@org.springframework.modulith.NamedInterface("api")
package com.acme.shop.customers.api;
```

Java module descriptor có thể export package API mà Java module khác cần truy cập:

```java
module com.acme.shop {
    exports com.acme.shop.customers.api;
    exports com.acme.shop.orders.api;
}
```

Trong ví dụ này, `allowedDependencies` kiểm soát dependency giữa application module `orders` và named interface `customers::api`. `exports` kiểm soát package nào được Java module khác truy cập. Hai khai báo có thể cùng cần thiết nếu có consumer ở cả hai cấp, nhưng chúng không tự đồng bộ với nhau.

Nếu tất cả application module nằm trong cùng Java module và không có Java module consumer bên ngoài, việc export package chỉ để các package nội bộ gọi nhau thường không cần thiết. Spring Modulith vẫn có thể kiểm tra ranh giới giữa các application module bên trong.

## 10. Cách kiểm tra Spring Modulith và JPMS

Với Spring Modulith, tạo mô hình từ lớp ứng dụng và xác minh dependency:

```java
import org.springframework.modulith.core.ApplicationModules;

ApplicationModules.of(ShopApplication.class).verify();
```

Với JPMS, kiểm tra `module-info.java` và biên dịch/chạy ứng dụng trong module path. Có thể dùng công cụ Java như `jdeps` để phân tích dependency ở cấp module/package và kiểm tra descriptor được đóng gói trong modular JAR.

Một quy trình kiểm tra dự án dùng cả hai cơ chế có thể gồm:

1. Chạy compile hoặc test trên module path để xác nhận `requires`, `exports` và `opens` phù hợp.
2. Chạy `ApplicationModules.verify()` để xác nhận ranh giới application module và `allowedDependencies`.
3. Kiểm tra các package API được công khai đúng ở cả hai lớp nếu consumer cần chúng.
4. Kiểm thử Spring reflection, configuration binding và bean creation nếu ứng dụng chạy trên JPMS module path.
5. Rà soát các thay đổi `package-info.java` và `module-info.java` cùng nhau khi di chuyển package hoặc đổi API.

Không nên xem một lần compile thành công là bằng chứng rằng ranh giới Spring Modulith đúng. Cũng không nên xem `ApplicationModules.verify()` thành công là bằng chứng rằng JPMS readability hoặc reflective access đã được cấu hình đúng.

## 11. Những nhầm lẫn thường gặp

- **“`package-info.java` là Java module descriptor.”** Không đúng. Đây là file metadata/Javadoc ở cấp package; JPMS descriptor là `module-info.java`.
- **“`@ApplicationModule` tạo một Java module.”** Nó đánh dấu application module trong mô hình Spring Modulith, không tạo module-info hoặc modular JAR.
- **“`@NamedInterface` tương đương `exports`.”** Một bên định danh API của application module, bên kia export package từ Java module.
- **“`type = OPEN` tương đương `opens`.”** OPEN nới lỏng ranh giới kiến trúc Spring Modulith; opens cho phép reflective access theo JPMS.
- **“JPMS đã chia module thì không cần Spring Modulith.”** Nếu nhiều application module cùng nằm trong một Java module, JPMS không kiểm soát dependency nội bộ giữa chúng theo cách Spring Modulith làm.
- **“Spring Modulith thay thế `requires`.”** Spring Modulith không quản lý readability giữa các Java module.
- **“Export package là đủ để dependency được phép.”** Package được export ở JPMS vẫn có thể vi phạm `allowedDependencies` hoặc module boundary của Spring Modulith.
- **“Một ứng dụng chỉ được chọn một trong hai.”** Hai cơ chế có thể cùng tồn tại, miễn là build/runtime và metadata được cấu hình đúng cho từng lớp.

## Kết luận

Package metadata của Spring Modulith và Java module descriptor của JPMS phục vụ hai cấp ranh giới khác nhau. `package-info.java` cùng `@ApplicationModule` và `@NamedInterface` mô tả application module, API và dependency trong một ứng dụng Spring Boot. `module-info.java` cùng `requires`, `exports` và `opens` mô tả readability, package access và reflective access giữa các Java module. Hai cơ chế có thể cùng tồn tại: JPMS bảo vệ ranh giới ở cấp Java module, còn Spring Modulith kiểm tra các ranh giới nghiệp vụ nhỏ hơn bên trong ứng dụng. Hãy dùng đúng cơ chế cho từng mục tiêu và kiểm chứng cả hai nếu dự án sử dụng đồng thời.

## Tài liệu tham khảo

- [Spring Modulith — Fundamentals](https://docs.spring.io/spring-modulith/reference/fundamentals.html)
- [Spring Modulith — ApplicationModule annotation API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/ApplicationModule.html)
- [Spring Modulith — NamedInterface annotation API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/NamedInterface.html)
- [Oracle Java — The Java Module System](https://docs.oracle.com/javase/9/docs/api/java/lang/module/package-summary.html)
- [Oracle Java — Module Declaration](https://docs.oracle.com/javase/specs/jls/se21/html/jls-7.html#jls-7.7)
- [Oracle Java — Module System](https://dev.java/learn/modules/)
