# Phân biệt module logic trong một ứng dụng với module Gradle

Khi thiết kế một ứng dụng Spring Boot theo hướng modular monolith, ta thường chia ứng dụng thành các phần như `catalog`, `orders` và `inventory`. Spring Modulith xem những phần này là **application module** (module logic của ứng dụng). Trong khi đó, Gradle cũng có khái niệm **project module** (module Gradle) để chia một bản build thành nhiều project.

Hai khái niệm cùng được gọi là “module”, nhưng trả lời hai câu hỏi khác nhau:

- **Module logic của Spring Modulith:** chức năng nghiệp vụ nào thuộc về phần nào của ứng dụng, phần nào được phép phụ thuộc vào phần nào và API nào được công khai?
- **Module Gradle:** mã nguồn nào được biên dịch trong project nào, project nào phụ thuộc vào project nào và bản build tạo ra những artifact nào?

Hiểu rõ khác biệt này giúp ta thiết kế ranh giới nghiệp vụ trước, sau đó mới quyết định có cần tách cấu trúc build hay không.

## 1. Module logic trong Spring Modulith là gì?

Module logic là một đơn vị tổ chức mã nguồn theo năng lực nghiệp vụ hoặc trách nhiệm của ứng dụng. Ví dụ, một hệ thống bán hàng có thể có các module `catalog` quản lý sản phẩm, `orders` xử lý đơn hàng và `inventory` quản lý tồn kho.

Các module này vẫn thuộc **một ứng dụng Spring Boot**. Chúng thường chạy trong cùng tiến trình, cùng JVM và được triển khai cùng ứng dụng. Việc chia module tạo ra ranh giới kiến trúc bên trong ứng dụng; nó không tự tạo ra service hay tiến trình độc lập.

Spring Modulith mặc định suy ra module từ cấu trúc package. Nếu package gốc của ứng dụng là `com.example.shop`, các package con trực tiếp như `catalog`, `orders` và `inventory` được nhận diện là những application module.

```text
com.example.shop
├── ShopApplication.java
├── catalog
│   ├── ProductCatalog.java
│   └── internal
│       ├── ProductEntity.java
│       └── ProductCatalogImpl.java
├── orders
│   ├── OrderManagement.java
│   └── internal
│       └── OrderService.java
└── inventory
    ├── StockAvailability.java
    └── internal
        └── StockRepository.java
```

Trong ví dụ này, `catalog`, `orders` và `inventory` là ba module logic. Các package con như `catalog.internal` và `orders.internal` chứa chi tiết triển khai của module tương ứng.

### API công khai và phần triển khai nội bộ

Theo quy ước mặc định của Spring Modulith, các kiểu dữ liệu nằm trực tiếp trong package gốc của module tạo nên API mà module khác có thể sử dụng. Các package con được xem là phần nội bộ. Vì vậy, module `orders` có thể gọi `ProductCatalog` trong package `catalog`, nhưng không nên truy cập trực tiếp `ProductEntity` hoặc repository nội bộ của `catalog`.

Ví dụ, module `orders` sử dụng API của `catalog`:

```java
package com.example.shop.orders.internal;

import com.example.shop.catalog.ProductCatalog;

class OrderService {

    private final ProductCatalog productCatalog;

    OrderService(ProductCatalog productCatalog) {
        this.productCatalog = productCatalog;
    }
}
```

Thiết kế này giữ quyền sở hữu dữ liệu và cách triển khai bên trong module `catalog`. Module `orders` chỉ biết hợp đồng mà `catalog` công khai, nhờ đó `catalog` có thể thay đổi cách lưu trữ hoặc xử lý mà ít ảnh hưởng đến bên gọi.

Nếu cần công khai một API nằm trong package con, ta có thể đánh dấu package đó bằng `@NamedInterface`:

```java
@org.springframework.modulith.NamedInterface("api")
package com.example.shop.catalog.api;
```

Khi đó, `catalog::api` là một named interface mà module khác có thể phụ thuộc vào. Việc mở một named interface nên là quyết định có chủ đích: package được mở trở thành một phần hợp đồng mà module sở hữu cần duy trì.

Ta cũng có thể khai báo các module được phép phụ thuộc trong `@ApplicationModule`, đặt ở `package-info.java` của module cần giới hạn:

```java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = {"catalog", "inventory::api"}
)
package com.example.shop.orders;
```

Khai báo này thể hiện `orders` được phép dùng API mặc định của `catalog` và named interface `api` của `inventory`. Tên module và tên named interface phải khớp với cấu trúc ứng dụng thực tế.

## 2. Module Gradle là gì?

Module Gradle thường được gọi chính xác hơn là **Gradle subproject** trong một multi-project build. Nó là một đơn vị của hệ thống build, có thể có file cấu hình riêng, source set, dependency và các task biên dịch hoặc đóng gói riêng.

Một build nhiều project có thể khai báo các project trong `settings.gradle`:

```groovy
rootProject.name = 'shop'

include(':catalog', ':orders', ':inventory')
```

Mỗi project có thể có `build.gradle` riêng. Ví dụ, project `orders` khai báo phụ thuộc vào project `catalog`:

```groovy
dependencies {
    implementation(project(':catalog'))
}
```

Gradle dùng khai báo này để xây dựng đồ thị phụ thuộc của bản build. Tùy plugin và cấu hình, mỗi project có thể tạo ra JAR hoặc artifact khác. Gradle quản lý việc biên dịch, classpath, thứ tự task, đóng gói và các cơ chế tối ưu build.

Một Gradle project không mặc nhiên là một ứng dụng độc lập. Ví dụ, ứng dụng Spring Boot ở project `app` có thể phụ thuộc vào các project thư viện `catalog`, `orders` và `inventory`; khi đóng gói, các thư viện này vẫn có thể được đưa vào cùng một Spring Boot executable JAR và chạy trong cùng tiến trình.

Gradle hiểu quan hệ giữa các project trong bản build. Nó không tự biết `orders` là nghiệp vụ đơn hàng, package nào là API công khai của `catalog`, hay `orders` có đang truy cập nhầm phần nội bộ của `catalog` hay không. Những quy tắc kiến trúc ở cấp package cần được mô hình hóa và kiểm tra bằng công cụ phù hợp, chẳng hạn Spring Modulith.

## 3. So sánh hai loại module

| Tiêu chí | Module logic của Spring Modulith | Module Gradle |
|---|---|---|
| Câu hỏi chính | Ứng dụng được chia theo trách nhiệm và ranh giới nghiệp vụ như thế nào? | Mã nguồn được chia thành những project build nào? |
| Được mô tả bằng | Chủ yếu là package; có thể bổ sung `@ApplicationModule` và `@NamedInterface` | Các project được khai báo trong `settings.gradle` và cấu hình bằng build script |
| Phạm vi | Kiến trúc bên trong một ứng dụng | Cấu trúc của bản build |
| Ranh giới quan trọng | API công khai, package nội bộ và hướng phụ thuộc giữa application module | Quan hệ phụ thuộc project, classpath, task và artifact |
| Cách kiểm chứng | `ApplicationModules.verify()` kiểm tra các quy tắc module đã mô hình hóa | Gradle kiểm tra và thực thi đồ thị phụ thuộc cùng các quy tắc build |
| Kết quả triển khai | Không tự tạo artifact hoặc tiến trình riêng | Có thể tạo JAR hoặc artifact riêng tùy plugin và cấu hình |

Điểm cần nhớ là **ranh giới package và ranh giới project không đồng nhất**. Khi nhiều application module cùng nằm trong một Gradle project, trình biên dịch Java vẫn có thể nhìn thấy các lớp `public` giữa chúng. Gradle không tự ngăn một lớp trong `orders` import lớp nội bộ của `catalog`. Spring Modulith giúp phát hiện loại vi phạm kiến trúc đó khi ta chạy kiểm chứng module.

## 4. Một Gradle project có thể chứa nhiều module logic

Đây là cách tổ chức phổ biến khi xây dựng modular monolith. Ta giữ một project Gradle cho ứng dụng Spring Boot, nhưng chia package thành nhiều application module:

```text
shop/                         # Một Gradle project
├── build.gradle
└── src/main/java/com/example/shop/
    ├── ShopApplication.java
    ├── catalog/              # Application module
    ├── orders/               # Application module
    └── inventory/            # Application module
```

Trong cấu trúc này:

- Gradle xem toàn bộ mã nguồn trên là một project để biên dịch và đóng gói ứng dụng.
- Spring Modulith nhận diện ba module logic từ các package `catalog`, `orders` và `inventory`.
- Các module có thể được kiểm tra về chu trình phụ thuộc, truy cập package nội bộ và những giới hạn phụ thuộc đã khai báo.
- Ứng dụng vẫn có thể được triển khai như một modular monolith duy nhất.

Ta có thể thêm một bài kiểm tra kiến trúc để xác minh mô hình module:

```java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void verifiesApplicationModuleStructure() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
```

Khi chạy test, Spring Modulith phân tích cấu trúc ứng dụng và báo lỗi nếu phát hiện vi phạm các quy tắc module mà mô hình đang áp dụng. Nhờ đó, ranh giới kiến trúc được kiểm tra tự động trong quy trình build, dù ta chưa tách các module thành Gradle project riêng.

## 5. Khi nào nên tách thành nhiều Gradle project?

Ta có thể chọn ánh xạ gần một-một giữa application module và Gradle project:

```text
Gradle build: shop
├── :app
├── :catalog
├── :orders
└── :inventory
```

Cách này có thể hữu ích khi các phần cần được biên dịch hoặc tái sử dụng độc lập, có dependency ở cấp project cần quản lý chặt, có quy trình phát hành artifact riêng, hoặc bản build đủ lớn để việc tách project đem lại lợi ích rõ ràng.

Tuy nhiên, tách Gradle project làm tăng số lượng build script, cấu hình dependency và quy ước phối hợp giữa các project. Nó cũng không thay thế việc thiết kế API nghiệp vụ. Nếu một Gradle project `orders` phụ thuộc trực tiếp vào quá nhiều chi tiết nội bộ của `catalog`, việc đặt chúng ở hai project riêng chưa chắc đã tạo ra một ranh giới nghiệp vụ tốt.

Có thể dùng các dấu hiệu sau để quyết định:

| Nhu cầu | Hướng phù hợp |
|---|---|
| Muốn nhóm code theo nghiệp vụ, công khai API rõ ràng và kiểm tra chiều phụ thuộc | Bắt đầu bằng application module của Spring Modulith |
| Muốn giữ một ứng dụng triển khai duy nhất, nhưng có nhiều ranh giới nghiệp vụ | Một Gradle project chứa nhiều application module thường đã đủ |
| Cần biên dịch, tái sử dụng hoặc phát hành một phần mã nguồn như artifact riêng | Cân nhắc tách thành Gradle project |
| Chỉ muốn tạo thêm thư mục hoặc package có tên module | Chưa đủ lý do để tạo Gradle project mới |

Một hướng đi thực tế là bắt đầu với một Gradle project và xác định các application module theo năng lực nghiệp vụ. Khi có nhu cầu build hoặc phân phối độc lập được chứng minh, ta mới cân nhắc chuyển một phần mã nguồn sang Gradle project riêng. Sau khi tách, vẫn cần giữ mô hình API và quy tắc phụ thuộc ở cấp ứng dụng.

## 6. Đừng nhầm với Java Platform Module System

Java còn có **module của JPMS** (Java Platform Module System), thường được khai báo trong `module-info.java` bằng các chỉ thị như `requires` và `exports`. JPMS quy định module Java phụ thuộc và công khai package nào ở cấp nền tảng Java.

Ba khái niệm có mục đích khác nhau:

- Spring Modulith application module mô tả ranh giới kiến trúc và nghiệp vụ trong ứng dụng Spring.
- Gradle project module mô tả cách tổ chức và xây dựng source code trong build.
- JPMS module mô tả module ở cấp hệ thống module của Java.

Một dự án có thể dùng Gradle mà không dùng JPMS; cũng có thể tổ chức nhiều application module của Spring Modulith trong một Gradle project. Không nên suy ra rằng có package module của Spring Modulith thì phải có `module-info.java`, hoặc mỗi Gradle project phải tương ứng với một tiến trình chạy riêng.

## 7. Cách suy nghĩ khi thiết kế

Khi bắt đầu một modular monolith, hãy xác định các năng lực nghiệp vụ và quyền sở hữu dữ liệu trước. Với mỗi application module, làm rõ API mà module công khai, package nào là nội bộ và module nào được phép phụ thuộc vào nó. Sau đó dùng `ApplicationModules.of(ShopApplication.class).verify()` để đưa các quy tắc này vào kiểm tra tự động.

Tiếp theo, xem xét nhu cầu build: liệu một Gradle project duy nhất có đáp ứng được việc biên dịch, kiểm thử và đóng gói không? Nếu có, giữ cấu trúc build đơn giản và dùng Spring Modulith để bảo vệ ranh giới logic. Nếu cần artifact hoặc chu trình build độc lập, hãy tách Gradle project dựa trên nhu cầu đó và tiếp tục kiểm chứng kiến trúc ứng dụng.

Hãy ghi nhớ hai câu hỏi khi đọc một cấu trúc dự án:

1. **Ranh giới nghiệp vụ nằm ở đâu?** Đây là câu hỏi về application module của Spring Modulith.
2. **Ranh giới biên dịch và đóng gói nằm ở đâu?** Đây là câu hỏi về Gradle project.

Trả lời riêng hai câu hỏi này giúp tránh việc đồng nhất tên gọi “module” với cùng một loại ranh giới, đồng thời cho phép kiến trúc nghiệp vụ và cấu trúc build phát triển theo nhu cầu thực tế của ứng dụng.
