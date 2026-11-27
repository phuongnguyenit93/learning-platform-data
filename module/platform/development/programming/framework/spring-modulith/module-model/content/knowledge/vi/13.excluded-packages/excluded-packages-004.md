# Match package chính và match các package con

Khi Spring Modulith kiểm tra cấu trúc mô-đun, đôi khi có một số lớp hoặc package kỹ thuật không thuộc phạm vi kiến trúc mà nhóm muốn kiểm tra. Ví dụ, ứng dụng có thể chứa mã truy cập cơ sở dữ liệu dùng chung, mã được sinh tự động hoặc một package tích hợp nằm ngoài các mô-đun nghiệp vụ. Spring Modulith cho phép truyền một predicate để loại các lớp hoặc package đó khỏi quá trình kiểm tra.

Điểm cần chú ý là cú pháp package pattern quyết định phạm vi loại trừ. Pattern `com.acme.shop.db` nhắm tới package chính xác; pattern `com.acme.shop.db..` bao gồm package đó cùng toàn bộ package con. Hai cách viết này tạo ra phạm vi khác nhau và cần được chọn theo cấu trúc thực tế.

## 1. Loại trừ bằng predicate khi tạo ApplicationModules

API `ApplicationModules.of(…)` nhận một predicate của ArchUnit để xác định những lớp cần loại khỏi quá trình kiểm tra mô-đun. Có thể dùng `JavaClass.Predicates.resideInAPackage(…)` để chọn lớp theo package:

```java
package com.acme.shop;

import com.tngtech.archunit.core.domain.JavaClass;
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void verifiesApplicationModules() {
        ApplicationModules.of(
                ShopApplication.class,
                JavaClass.Predicates.resideInAPackage("com.acme.shop.db")
        ).verify();
    }
}
```

Trong ví dụ, predicate chọn các lớp Java thuộc package `com.acme.shop.db`. Spring Modulith bỏ các lớp khớp predicate khỏi phạm vi inspection khi xây dựng và xác minh mô hình mô-đun. Các lớp còn lại vẫn được kiểm tra theo những quy tắc boundary của ứng dụng. Vì predicate nhận `JavaClass`, nó không loại các tài nguyên không phải mã Java như tệp SQL, XML hoặc YAML khỏi JAR hay khỏi quy trình đóng gói.

Predicate này không thay đổi vị trí package, không chuyển lớp sang mô-đun khác và cũng không định nghĩa một mô-đun mới. Nó chỉ xác định phần mã nguồn không tham gia lần kiểm tra `ApplicationModules` đang được tạo.

## 2. Match package chính xác

Pattern không có `..` ở cuối sẽ match package được nêu. Ví dụ:

```java
JavaClass.Predicates.resideInAPackage("com.acme.shop.db")
```

Với cấu trúc sau:

```text
com.acme.shop
└── db
    ├── DatabaseHealthCheck.java
    ├── MigrationRunner.java
    └── migration
        └── MigrationSupport.java
```

Pattern `com.acme.shop.db` match các lớp nằm trực tiếp trong package `com.acme.shop.db`, chẳng hạn `DatabaseHealthCheck` và `MigrationRunner`. Nó không tự động mở rộng sang package con `com.acme.shop.db.migration`.

Hãy dùng match chính xác khi chỉ muốn bỏ qua các lớp nằm trong một package cụ thể, còn các package con vẫn cần được đưa vào kiểm tra. Đây là lựa chọn phù hợp nếu package cha chứa một số adapter kỹ thuật nhưng package con có các lớp thuộc boundary nghiệp vụ cần kiểm tra.

## 3. Match package chính và toàn bộ package con

Thêm `..` vào cuối pattern để bao gồm package được chỉ định và mọi package con:

```java
JavaClass.Predicates.resideInAPackage("com.acme.shop.db..")
```

Với cùng cấu trúc ở trên, pattern này match:

- Các lớp trực tiếp trong `com.acme.shop.db`.
- Các lớp trong `com.acme.shop.db.migration`.
- Các lớp trong những package lồng sâu hơn, ví dụ `com.acme.shop.db.migration.internal`.

Minh họa phạm vi:

```text
com.acme.shop
└── db                         <- được match
    ├── DatabaseHealthCheck    <- được loại trừ
    ├── MigrationRunner        <- được loại trừ
    └── migration              <- được match
        └── internal           <- được match
            └── SqlSupport     <- được loại trừ
```

Khác biệt nằm ở hai dấu chấm cuối. `com.acme.shop.db` chỉ nhắm package chính; `com.acme.shop.db..` nhắm package chính cùng các package con. Nếu mục tiêu là loại trừ toàn bộ vùng mã kỹ thuật nằm dưới `db`, pattern thứ hai diễn đạt đúng phạm vi hơn.

## 4. Match một tên package ở nhiều vị trí

Package pattern của ArchUnit còn hỗ trợ `..` ở đầu và giữa pattern. Cách này hữu ích khi cấu trúc có nhiều nhánh nhưng cùng chứa một package mang tên quy ước, chẳng hạn `generated`.

```java
JavaClass.Predicates.resideInAPackage("..generated..")
```

Pattern trên match các package có một segment tên `generated` ở bất kỳ vị trí nào trong đường dẫn package, cùng các package nằm bên dưới segment đó. Ví dụ:

| Package | Có khớp `..generated..`? | Giải thích |
|---|---|---|
| `com.acme.generated` | Có | Có segment `generated` |
| `com.acme.generated.client` | Có | `generated` nằm trước package con `client` |
| `com.acme.shop.generated.dto` | Có | `generated` nằm giữa các segment |
| `com.acme.shop.generator.dto` | Không | `generator` không phải `generated` |
| `com.acme.shop.dto` | Không | Không có segment `generated` |

Mẫu này thích hợp khi nhiều module hoặc package gốc khác nhau cùng chứa mã được sinh tự động. Tuy nhiên, hãy kiểm tra danh sách package thực tế trước khi dùng pattern rộng, vì một segment tên `generated` có thể xuất hiện trong vùng mã mà nhóm vẫn muốn kiểm tra.

## 5. Kết hợp lựa chọn pattern với cấu trúc package

Giả sử ứng dụng có cấu trúc:

```text
com.acme.shop
├── order
│   ├── OrderService.java
│   └── generated
│       └── OrderMapperImpl.java
├── inventory
│   └── InventoryService.java
├── db
│   ├── DatabaseHealthCheck.java
│   └── migration
│       └── MigrationRunner.java
└── reporting
    └── generated
        └── ReportMapperImpl.java
```

Có thể chọn pattern theo mục tiêu:

| Mục tiêu | Pattern | Phạm vi được chọn |
|---|---|---|
| Chỉ bỏ qua lớp nằm trực tiếp trong package `db` | `com.acme.shop.db` | Package `com.acme.shop.db` |
| Bỏ qua toàn bộ mã dưới `db` | `com.acme.shop.db..` | `db` và tất cả package con |
| Bỏ qua mã sinh tự động trong nhiều mô-đun | `..generated..` | Các package có segment `generated` và package con |

Ví dụ kiểm tra ứng dụng với toàn bộ mã trong `db` được loại khỏi inspection:

```java
import com.tngtech.archunit.core.domain.JavaClass;
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void verifiesModulesIgnoringDatabaseInfrastructure() {
        ApplicationModules.of(
                ShopApplication.class,
                JavaClass.Predicates.resideInAPackage("com.acme.shop.db..")
        ).verify();
    }
}
```

Nếu cần loại trừ các package `generated` ở nhiều mô-đun, thay pattern bằng `..generated..`. Không nên ghép nhiều package thành một chuỗi tùy ý; predicate cần mô tả đúng điều kiện match của ArchUnit.

## 6. Tránh loại trừ quá rộng

Loại trừ giúp tập trung kiểm tra vào phần mã nguồn thuộc mô hình mô-đun, nhưng cũng làm các lớp được match nằm ngoài phạm vi inspection. Nếu loại trừ nhầm một lớp nghiệp vụ, vi phạm phụ thuộc hoặc boundary phát sinh từ lớp đó có thể không xuất hiện trong kết quả kiểm tra.

Trước khi thêm exclusion, hãy xác định:

1. Package hoặc lớp đó có thực sự nằm ngoài phạm vi kiến trúc cần kiểm tra không?
2. Chỉ package chính cần loại trừ hay cả các package con?
3. Pattern có thể match thêm package nghiệp vụ ở một nhánh khác không?
4. Khi cấu trúc package thay đổi, exclusion có còn chọn đúng phạm vi dự kiến không?

Không dùng exclusion để che một phụ thuộc sai giữa hai mô-đun. Nếu một lớp nghiệp vụ truy cập package nội bộ của mô-đun khác, cần sửa API hoặc quan hệ phụ thuộc. Loại lớp gây ra vi phạm khỏi inspection chỉ khiến kiểm tra mất khả năng phát hiện vấn đề đó.

## 7. Kiểm tra lại phạm vi match

Khi thay đổi package pattern, hãy kiểm chứng cả trường hợp được match và không được match. Một cách thực tế là ghi lại các lớp đại diện cho từng package trong cấu trúc, sau đó chạy bài kiểm tra kiến trúc và xem vi phạm nào còn được báo.

Ví dụ, nếu chọn `com.acme.shop.db`, hãy chắc chắn rằng lớp trong `com.acme.shop.db.migration` vẫn tham gia inspection. Nếu chọn `com.acme.shop.db..`, hãy chắc chắn rằng cả package `db` và các package con đều nằm ngoài inspection. Với `..generated..`, hãy xác nhận các package `generated` ở nhiều vị trí được chọn và những package có tên gần giống như `generator` vẫn được kiểm tra.

Có thể kiểm tra cú pháp matcher độc lập bằng `PackageMatcher` của ArchUnit khi cần xác minh một quy tắc phức tạp. Dù kiểm tra matcher riêng, kết quả cuối cùng vẫn cần được xác nhận qua bài test `ApplicationModules` của ứng dụng vì đó là nơi predicate exclusion thực sự được áp dụng.

## 8. Bài tập tự kiểm tra

Cho các package sau:

```text
com.acme.shop.db
com.acme.shop.db.migration
com.acme.shop.order.generated
com.acme.shop.reporting.generated.dto
com.acme.shop.order.generator
```

Hãy xác định package nào được match bởi từng pattern:

1. `com.acme.shop.db`
2. `com.acme.shop.db..`
3. `..generated..`

Sau đó chọn pattern phù hợp nếu yêu cầu là loại trừ toàn bộ mã dưới `db` và tất cả package tên `generated` trong các mô-đun, đồng thời giữ `generator` trong phạm vi kiểm tra.

Khi hoàn thành, bạn cần giải thích được sự khác nhau giữa match một package chính xác, match package chính cùng các package con và match một segment tên package ở nhiều vị trí. Việc hiểu đúng phạm vi pattern giúp exclusion có chủ đích và giữ cho kiểm tra kiến trúc Spring Modulith đáng tin cậy.
