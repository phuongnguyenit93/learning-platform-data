# API package, named interface và internal trong tài liệu

Tài liệu của một modular monolith cần cho người đọc biết module nào cung cấp chức năng gì, module khác được phép sử dụng phần nào và chi tiết nào thuộc nội bộ. Spring Modulith lấy thông tin này từ cấu trúc package cùng các annotation kiến trúc, sau đó có thể tạo sơ đồ và module canvas để mô tả hệ thống.

Để tài liệu phản ánh đúng ranh giới module, cần phân biệt ba khái niệm: package gốc được công khai mặc định, named interface được công khai có chủ đích và package nội bộ không dành cho module khác. Các khái niệm này cũng quyết định cách khai báo `allowedDependencies` và cách đọc sơ đồ do Spring Modulith tạo ra.

## 1. Ba vùng trong cấu trúc một module

Giả sử ứng dụng có module `orders` với cấu trúc sau:

```text
com.example.orders
├── package-info.java
├── OrderManagement.java
├── api
│   ├── package-info.java
│   └── OrderCompleted.java
└── internal
    ├── OrderService.java
    └── OrderRepository.java
```

Spring Modulith xác định `com.example.orders` là package gốc của module. Theo quy ước mặc định, các kiểu đặt trực tiếp trong package gốc tạo thành API không đặt tên riêng của module. Package con được xem là nội bộ, trừ khi package đó được công khai bằng `@NamedInterface`.

| Vùng | Cách xác định | Ý nghĩa với module khác |
|---|---|---|
| Package gốc | Package gốc của application module | API mặc định của module |
| Named interface | Package con được đánh dấu `@NamedInterface` | API bổ sung có tên, có thể được cho phép riêng |
| Package nội bộ | Package con không được công khai | Chi tiết triển khai, module khác không nên phụ thuộc |

Tên `internal` trong ví dụ là quy ước đặt tên giúp người đọc dễ nhận biết. Ranh giới được Spring Modulith xác định dựa trên vị trí package và việc package đó có được khai báo là named interface hay không; chỉ đổi tên package không làm nó trở thành API công khai.

## 2. Package gốc là API mặc định

Một module nhỏ có thể công khai các kiểu cần thiết ngay trong package gốc. Ví dụ, `OrderManagement` là hợp đồng mà module `orders` cung cấp:

```java
package com.example.orders;

import java.util.UUID;

public interface OrderManagement {

    void complete(UUID orderId);
}
```

Module khác có thể tham chiếu `com.example.orders.OrderManagement`. Nếu muốn giới hạn danh sách module được phép sử dụng module `orders`, khai báo `allowedDependencies` trong `package-info.java` của module tiêu thụ:

```java
@org.springframework.modulith.ApplicationModule(
        allowedDependencies = "orders"
)
package com.example.billing;
```

Trong tài liệu, hãy thể hiện package gốc là phần API mà module sở hữu công khai. Không nên đưa repository, JPA entity hoặc service triển khai vào package gốc chỉ để các module khác có thể import chúng. Những kiểu đó sẽ trở thành một phần bề mặt công khai và làm hợp đồng khó thay đổi.

## 3. Dùng named interface để công khai API theo nhóm

Khi module có nhiều nhóm API, đặt chúng trong các package riêng và đánh dấu từng package bằng `@NamedInterface`. Ví dụ, package `api` công khai event và kiểu dữ liệu mà module khác cần dùng:

```java
@org.springframework.modulith.NamedInterface("api")
package com.example.orders.api;
```

```java
package com.example.orders.api;

import java.time.Instant;
import java.util.UUID;

public record OrderCompleted(UUID orderId, Instant completedAt) {}
```

Module tiêu thụ có thể giới hạn phụ thuộc vào named interface này:

```java
@org.springframework.modulith.ApplicationModule(
        allowedDependencies = "orders::api"
)
package com.example.notifications;
```

Cú pháp `orders::api` gồm tên module và tên named interface. Nó diễn đạt rõ rằng `notifications` được sử dụng phần API `api` do `orders` công khai. Nếu module `orders` có thêm named interface khác, chẳng hạn `spi`, consumer chỉ được dùng phần đó khi quy tắc phụ thuộc cho phép.

Named interface có thể được dùng để phân nhóm hợp đồng theo mục đích, ví dụ:

```text
com.example.orders
├── api             -> API nghiệp vụ và event công khai
├── spi             -> Hợp đồng mở rộng dành cho tích hợp
└── internal        -> Cài đặt nội bộ
```

Trong tài liệu, cần ghi rõ ý nghĩa của từng named interface. Tên `api` hoặc `spi` chỉ là nhãn; hợp đồng thực tế được quyết định bởi các kiểu nằm trong package và các quy tắc phụ thuộc của module.

## 4. Package internal chứa chi tiết triển khai

Các lớp chỉ phục vụ nội bộ module nên nằm trong package con không được đánh dấu `@NamedInterface`. Ví dụ:

```java
package com.example.orders.internal;

import org.springframework.stereotype.Service;

@Service
class OrderService {

    // Điều phối quy tắc nghiệp vụ và truy cập dữ liệu của orders.
}
```

Module khác không nên import `OrderService` hoặc `OrderRepository`. Thay vào đó, module sở hữu cung cấp thao tác cần thiết qua package gốc hoặc named interface. Spring vẫn có thể tạo bean trong package nội bộ nếu component scanning bao phủ package đó; việc bean tồn tại trong ApplicationContext không khiến kiểu của nó trở thành API module.

Khi viết tài liệu, phân biệt rõ:

- **Public API:** hợp đồng mà module cam kết cho consumer sử dụng.
- **Named interface:** một nhóm API được công khai và có tên cụ thể.
- **Internal implementation:** lớp, repository và mô hình dữ liệu chỉ phục vụ việc triển khai bên trong module.

Không nên mô tả package nội bộ như một điểm tích hợp. Nếu consumer cần một khả năng hiện chỉ có trong `internal`, hãy bổ sung hợp đồng công khai ở module sở hữu thay vì hướng dẫn consumer gọi trực tiếp lớp triển khai.

## 5. Tạo tài liệu module bằng Documenter

Spring Modulith cung cấp `Documenter` để tạo tài liệu từ mô hình `ApplicationModules`. Trong source set test, thêm dependency `spring-modulith-docs` tương ứng với phiên bản Spring Modulith đang dùng, sau đó tạo một test sinh tài liệu:

```java
package com.example;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;
import org.springframework.modulith.docs.Documenter;

class ModuleDocumentationTests {

    @Test
    void createModuleDocumentation() {
        var modules = ApplicationModules.of(Application.class);

        new Documenter(modules)
                .writeModulesAsPlantUml()
                .writeIndividualModulesAsPlantUml()
                .writeModuleCanvases();
    }
}
```

Ba thao tác tạo ba góc nhìn bổ trợ nhau:

| Phương thức | Nội dung tài liệu |
|---|---|
| `writeModulesAsPlantUml()` | Sơ đồ PlantUML tổng quan các module và quan hệ phụ thuộc |
| `writeIndividualModulesAsPlantUml()` | Sơ đồ chi tiết riêng cho từng module |
| `writeModuleCanvases()` | Module canvas tổng hợp thông tin và cấu trúc của từng module |

Documenter sử dụng mô hình module đã được phân tích từ ứng dụng. Vì vậy, package gốc, named interface, package nội bộ và quan hệ phụ thuộc trong mã nguồn là đầu vào để tạo tài liệu. Khi cấu trúc package hoặc annotation thay đổi, hãy sinh lại tài liệu để sơ đồ và canvas phản ánh trạng thái mới.

Theo cấu hình mặc định, tài liệu được ghi vào thư mục output của Spring Modulith dưới `target/spring-modulith-docs`. Có thể tích hợp các file PlantUML và module canvas này vào tài liệu kỹ thuật của dự án, ví dụ trang kiến trúc hoặc tài liệu onboarding. Hãy kiểm tra output của phiên bản thư viện đang dùng nếu dự án đã tùy chỉnh thư mục đích.

## 6. Đọc sơ đồ và module canvas

Sơ đồ tổng quan giúp người đọc nhận ra các module và chiều phụ thuộc giữa chúng. Khi xem sơ đồ, hãy lần theo quan hệ từ module tiêu thụ đến module cung cấp để trả lời ba câu hỏi:

1. Module nào đang sử dụng module nào?
2. Quan hệ đó có phù hợp với `allowedDependencies` không?
3. Kiểu được sử dụng thuộc package gốc hoặc named interface công khai nào?

Sơ đồ chi tiết của một module giúp xem cấu trúc bên trong module đó. Module canvas bổ sung ngữ cảnh để người đọc hiểu trách nhiệm, các thành phần và quan hệ của module. Kết hợp các góc nhìn này sẽ giúp tài liệu diễn đạt cả ranh giới bên ngoài lẫn cấu trúc nội bộ.

Khi trình bày tài liệu thủ công bên cạnh output được sinh tự động, nên giữ cách gọi thống nhất: tên module theo application module, tên API theo package hoặc named interface, và tên package nội bộ theo cấu trúc thực tế. Không gán nhãn một package là public chỉ vì tên nó chứa từ `api`; hãy xác nhận package đó được công khai trong mô hình Spring Modulith.

## 7. Kiểm chứng tài liệu có khớp với kiến trúc

Tài liệu chỉ hữu ích khi mô hình module hợp lệ. Có thể thêm kiểm tra kiến trúc bên cạnh test sinh tài liệu:

```java
package com.example;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void verifyModuleStructure() {
        ApplicationModules.of(Application.class).verify();
    }
}
```

`verify()` kiểm tra các quy tắc module, bao gồm truy cập API và các ràng buộc phụ thuộc đã khai báo. Test này giúp phát hiện trường hợp consumer tham chiếu package nội bộ hoặc vượt quá danh sách phụ thuộc được phép. Sau khi sửa cấu trúc, chạy lại bước sinh tài liệu để tránh giữ sơ đồ cũ.

Một quy trình cập nhật tài liệu phù hợp gồm:

1. Chỉnh package và annotation trong mã nguồn module.
2. Kiểm tra `ApplicationModules.of(Application.class).verify()`.
3. Sinh lại sơ đồ tổng quan, sơ đồ từng module và module canvas bằng `Documenter`.
4. Đưa output mới vào tài liệu kiến trúc của dự án và rà soát các mô tả do con người viết.

## 8. Bài tập thực hành

1. Tạo module `orders` với package gốc, `api` và `internal`.
2. Đặt một hợp đồng nghiệp vụ trong package gốc và một event trong `api`.
3. Đánh dấu `orders.api` bằng `@NamedInterface("api")`.
4. Đặt service và repository trong `internal`; xác nhận module khác không import trực tiếp các kiểu này.
5. Khai báo `allowedDependencies = "orders::api"` ở một module consumer.
6. Tạo test dùng `Documenter` để sinh sơ đồ tổng quan, sơ đồ riêng và module canvas.
7. Đọc tài liệu được sinh ra và chỉ ra phần nào là API mặc định, phần nào là named interface, phần nào là nội bộ.
8. Thử tạo một tham chiếu từ consumer đến `orders.internal`, chạy kiểm tra kiến trúc để quan sát vi phạm, rồi khôi phục hợp đồng công khai.

Sau bài tập, bạn cần giải thích được vì sao tài liệu module phải phản ánh package thực tế và annotation kiến trúc, cách named interface giới hạn bề mặt API, và vì sao package nội bộ không được xem là hợp đồng tích hợp.

## Tài liệu tham khảo

- [Documenting Application Modules – Spring Modulith Reference](https://docs.spring.io/spring-modulith/reference/documentation.html)
- [Application Modules – Spring Modulith Reference](https://docs.spring.io/spring-modulith/reference/fundamentals.html)
- [Documenter API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/docs/Documenter.html)
- [NamedInterface API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/NamedInterface.html)
