# Đổi package làm thay đổi module model thế nào?

Trong Spring Modulith, package Java là đầu vào quan trọng để nhận diện application module. Vì vậy, đổi tên hoặc di chuyển package có thể làm thay đổi module nào sở hữu một type, type đó thuộc API hay phần triển khai nội bộ, và những dependency nào xuất hiện trong mô hình kiến trúc.

Không phải mọi lần đổi package đều tạo ra một module mới. Kết quả phụ thuộc vào vị trí package mới so với package gốc của ứng dụng và root package của từng module. Di chuyển một package con bên trong cùng module thường chỉ thay đổi tên đầy đủ của type; đưa nó lên cấp con trực tiếp của application root có thể biến nó thành module riêng; chuyển một type từ package nội bộ sang package gốc có thể làm type đó trở thành một phần API mặc định.

## 1. Spring Modulith phát hiện module từ cây Java package

Giả sử lớp khởi chạy Spring Boot nằm trong `com.acme.shop`:

```java
package com.acme.shop;

import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ShopApplication {
}
```

Với chiến lược phát hiện mặc định, mỗi package con trực tiếp của package chứa lớp ứng dụng được xem là một application module. Các package sâu hơn thuộc về module tương ứng, trừ khi ứng dụng khai báo cấu trúc lồng nhau hoặc một chiến lược phát hiện khác.

```text
com.acme.shop                         // application root
├── ShopApplication.java
├── order                             // module root: order
│   ├── OrderManagement.java
│   └── internal
│       └── OrderRepository.java
├── inventory                         // module root: inventory
│   └── InventoryManagement.java
└── customer                          // module root: customer
    └── CustomerManagement.java
```

Ở đây `order`, `inventory` và `customer` là ba module. `order.internal` vẫn thuộc module `order`. Spring Modulith không dựa đơn thuần vào tên thư mục trên ổ đĩa; nó phân tích tên Java package và vị trí của package trong cây package. Trong dự án Java thông thường, đường dẫn thư mục phản ánh tên package, nhưng câu lệnh `package` trong source mới quyết định fully qualified name của type.

Do đó, một lần refactor package có thể làm thay đổi cấu trúc mà Spring Modulith nhìn thấy, ngay cả khi nội dung phương thức và logic nghiệp vụ không đổi.

## 2. Di chuyển package bên trong cùng module

Xét package `com.acme.shop.order.internal.payment`:

```text
com.acme.shop
└── order
    ├── OrderManagement.java
    └── internal
        └── payment
            ├── PaymentAuthorizer.java
            └── PaymentGatewayAdapter.java
```

Nếu chuyển nó sang `com.acme.shop.order.payment`, package mới vẫn nằm bên dưới root package `com.acme.shop.order`:

```text
com.acme.shop
└── order
    ├── OrderManagement.java
    ├── internal
    └── payment
        ├── PaymentAuthorizer.java
        └── PaymentGatewayAdapter.java
```

Theo cách phát hiện mặc định, `payment` vẫn là package con thuộc module `order`; nó không tự trở thành application module mới. Vì thế, ở cấp module graph, ownership vẫn là `order` và việc di chuyển này thường không tạo thêm dependency giữa các module.

Tuy vậy, fully qualified name của các lớp đã thay đổi, ví dụ:

```java
// Trước khi di chuyển
package com.acme.shop.order.internal.payment;

// Sau khi di chuyển
package com.acme.shop.order.payment;
```

Các import, test, cấu hình reflection và nơi tham chiếu tên lớp dưới dạng chuỗi vẫn cần được cập nhật. Nếu package mới nằm trong một Named Interface hoặc được annotation ở `package-info.java`, hãy chuyển và kiểm tra metadata tương ứng.

## 3. Đưa package con lên cấp application root có thể tạo module mới

Giả sử `payment` ban đầu là package con của `order`:

```text
com.acme.shop
└── order
    ├── OrderManagement.java
    └── payment
        ├── PaymentService.java
        └── PaymentRepository.java
```

Nếu chuyển package thành `com.acme.shop.payment`, nó trở thành package con trực tiếp của application root:

```text
com.acme.shop
├── order
│   └── OrderManagement.java
├── payment
│   ├── PaymentService.java
│   └── PaymentRepository.java
└── inventory
    └── InventoryManagement.java
```

Với discovery mặc định, Spring Modulith có thể nhận diện `payment` là một application module mới. Đây không chỉ là thay đổi vị trí code. Những type trước đó thuộc module `order` nay thuộc module `payment`; dependency giữa chúng được tính lại theo quan hệ tham chiếu sau khi di chuyển.

Ví dụ, trước khi tách, `OrderManagement` gọi trực tiếp `PaymentService` trong cùng module. Sau khi `PaymentService` trở thành một module riêng, quan hệ đó trở thành dependency `order -> payment`. Nếu `order` có `allowedDependencies`, cần kiểm tra xem `payment` đã nằm trong danh sách cho phép chưa.

Một lần di chuyển package như vậy có thể làm thay đổi:

- Danh sách application module được phát hiện.
- Module sở hữu các type được di chuyển.
- Dependency trực tiếp giữa module cũ và module mới.
- API mặc định và package nội bộ của mỗi module.
- Tên module được dùng trong `allowedDependencies` hoặc các công cụ tài liệu hóa.

Trước khi di chuyển, hãy quyết định `payment` có thực sự là một capability độc lập hay chỉ là một phần triển khai của `order`. Cấu trúc package nên phản ánh quyết định ownership đó.

## 4. Đổi tên root package có thể đổi danh tính module

Trong mô hình mặc định, tên module thường được suy ra từ tên package root của module. Ví dụ, `com.acme.shop.order` đại diện module `order`. Nếu đổi root package thành `com.acme.shop.purchase`, module được phát hiện sẽ mang tên `purchase`.

```text
Trước: com.acme.shop.order
Sau:   com.acme.shop.purchase
```

Việc đổi tên root package làm thay đổi fully qualified name của các type bên trong và có thể thay đổi tên module mà các cấu hình kiến trúc đang tham chiếu. Hãy rà soát:

- `@ApplicationModule` trong `package-info.java` của module.
- `allowedDependencies` của các module tiêu thụ, nếu tên module được liệt kê trực tiếp.
- Các chuỗi `module :: named-interface` trong allowlist.
- Test, tài liệu và sơ đồ kiến trúc có nhắc đến tên module.
- Cấu hình hoặc mã nguồn dùng tên lớp/package dưới dạng chuỗi.

Nếu module sử dụng cấu hình phát hiện tùy chỉnh hoặc metadata bổ sung, đừng chỉ suy tên module từ segment cuối của package. Hãy tạo lại mô hình `ApplicationModules` và quan sát tên module thực tế sau refactor.

## 5. Đổi package có thể làm type chuyển từ internal sang API

Với một closed module, package gốc là API package mặc định; các package con không được công bố là nội bộ. Vì vậy, vị trí của type trong cây package ảnh hưởng đến cách module khác được phép sử dụng nó.

Ban đầu, `OrderRepository` nằm trong package nội bộ:

```java
package com.acme.shop.order.internal;

public class OrderRepository {
}
```

Nếu chuyển nó lên package gốc:

```java
package com.acme.shop.order;

public class OrderRepository {
}
```

Type này nay nằm trong package API mặc định của module `order`. Các module khác có thể tham chiếu nó mà không vi phạm quy tắc truy cập package nội bộ. Tuy nhiên, việc một repository trở thành API công khai thường là dấu hiệu cần xem xét lại thiết kế: module khác có thực sự cần biết cách lưu trữ đơn hàng không, hay chỉ cần một thao tác nghiệp vụ được cung cấp qua `OrderManagement`?

Chiều ngược lại cũng quan trọng. Di chuyển một type từ package gốc xuống package con có thể biến một type API trước đây thành nội bộ. Nếu consumer đang sử dụng type đó, `ApplicationModules.verify()` sẽ phát hiện truy cập package không còn được công bố.

Vì thế, một refactor package có thể thay đổi API boundary ngay cả khi không sửa modifier `public` của lớp.

## 6. Named Interface phụ thuộc vào package và metadata của nó

Một module có thể công bố package con bằng `@NamedInterface`. Ví dụ, `order.events` là hợp đồng event:

```java
@org.springframework.modulith.NamedInterface("events")
package com.acme.shop.order.events;
```

Consumer có thể khai báo phụ thuộc cụ thể:

```java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "order :: events"
)
package com.acme.shop.shipping;
```

Nếu di chuyển package `order.events` sang `order.integration.events`, cần bảo đảm `package-info.java` và annotation `@NamedInterface("events")` được đặt tại package mới. Nếu vẫn giữ tên interface `events`, tham chiếu `order :: events` có thể giữ nguyên vì tên Named Interface là hợp đồng được đặt rõ ràng; nhưng fully qualified name của các event type thay đổi nên import ở consumer phải được cập nhật.

Nếu đổi tên Named Interface từ `events` thành `integration`, các allowlist đang dùng `order :: events` phải được rà soát và cập nhật thành `order :: integration`. Nếu đổi luôn root package của module từ `order` thành `purchase`, tên module trong allowlist cũng cần thay đổi tương ứng.

Nếu chuyển type từ Named Interface về package gốc, hoặc từ package gốc vào package con, loại API mà consumer sử dụng cũng thay đổi. Hãy xem đây là thay đổi hợp đồng, không chỉ là thao tác sắp xếp file.

## 7. Dependency graph được xây dựng lại theo package và type sau refactor

Spring Modulith phân tích các quan hệ giữa module từ code đã biên dịch và cấu trúc package. Các tham chiếu type, Spring component dependency và event listener có thể tạo ra dependency edge. Khi package hoặc ownership của type thay đổi, dependency graph cũng có thể thay đổi.

Ví dụ trước khi tách `payment`:

```text
order
└── internal.payment.PaymentService
```

`PaymentService` là một phần triển khai bên trong `order`. Sau khi chuyển thành module riêng:

```text
order ----------------> payment
  OrderManagement       PaymentService
```

Nếu `OrderService` tiếp tục inject `PaymentService`, quan hệ gọi trước đây nằm trong cùng module nay là dependency giữa hai module. Module `order` phải sử dụng API được công bố của `payment` và cho phép dependency đó nếu đang khai báo `allowedDependencies`.

Ngược lại, nếu di chuyển một type dùng chung vào trong module `order`, các module khác có thể mất một API mà trước đây chúng phụ thuộc. Dependency graph có thể giảm cạnh hoặc chuyển thành truy cập package nội bộ không hợp lệ.

Vì vậy, sau mỗi lần đổi package có ảnh hưởng đến module root hoặc API boundary, hãy tạo lại `ApplicationModules` và chạy `verify()` để xem mô hình mới.

## 8. Package root của ứng dụng ảnh hưởng đến discovery và component scanning

Package chứa lớp `@SpringBootApplication` thường là điểm xuất phát cho component scanning mặc định của Spring Boot và cũng là package gốc được dùng khi tạo mô hình `ApplicationModules.of(ShopApplication.class)`.

Nếu di chuyển lớp ứng dụng từ `com.acme.shop` sang `com.acme`, phạm vi package được quét mặc định có thể mở rộng. Nếu chuyển lớp ứng dụng xuống `com.acme.shop.bootstrap`, các module đang nằm ở `com.acme.shop.order` có thể không còn là package con của package mới và không được discovery theo cấu hình mặc định.

Ví dụ:

```text
Trước:
com.acme.shop
├── ShopApplication.java
├── order
└── inventory

Sau khi chuyển lớp ứng dụng xuống:
com.acme.shop.bootstrap
└── ShopApplication.java

com.acme.shop
├── order
└── inventory
```

Trong cấu trúc sau, `order` và `inventory` không nằm dưới `com.acme.shop.bootstrap`. Mô hình module mặc định được tạo từ `ShopApplication.class` có thể không nhận diện chúng như trước. Component scanning mặc định của Spring Boot cũng thay đổi theo package của lớp ứng dụng.

Khi đổi application root, hãy kiểm tra thêm `@ComponentScan`, `@EntityScan`, `@EnableJpaRepositories`, `@ConfigurationPropertiesScan` và các cấu hình khác đang dựa vào package. Có thể cần khai báo base package rõ ràng hoặc dùng cấu hình discovery phù hợp. Không nên giả định việc đổi package lớp khởi chạy chỉ ảnh hưởng đến tên import.

## 9. Cách quan sát module model sau khi đổi package

Có thể in mô hình module để xem framework nhận diện cấu trúc mới như thế nào:

```java
package com.acme.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleDetectionTests {

    @Test
    void printsDetectedModules() {
        ApplicationModules modules = ApplicationModules.of(ShopApplication.class);
        modules.forEach(System.out::println);
    }

    @Test
    void verifiesDetectedModuleStructure() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
```

Sau khi đổi package, kiểm tra kết quả theo các câu hỏi:

1. Module nào được phát hiện và module nào biến mất hoặc xuất hiện mới?
2. Root package của từng module có đúng với capability dự kiến không?
3. Type được di chuyển còn thuộc module cũ hay đã sang module mới?
4. Type nào đã chuyển từ API package sang internal package hoặc ngược lại?
5. Named Interface và `allowedDependencies` còn trỏ đúng module/interface không?
6. Dependency graph có cạnh mới, cạnh bị mất hoặc chu trình mới không?

`verify()` kiểm tra các quy tắc kiến trúc mà mô hình hỗ trợ, chẳng hạn truy cập package nội bộ, dependency ngoài allowlist và chu trình module. Nó không thay thế việc kiểm tra cấu hình component scanning, entity scanning hoặc các tên package được lưu dưới dạng chuỗi trong ứng dụng.

## 10. Quy trình refactor package an toàn

Trước khi đổi package, hãy xác định đây là thay đổi ở cấp nào:

| Phạm vi thay đổi | Ảnh hưởng cần kiểm tra |
| --- | --- |
| Package con bên trong cùng module | Fully qualified name, import, test và Named Interface metadata nếu có |
| Package được đưa lên cấp con trực tiếp của application root | Có thể tạo module mới và chuyển ownership của type |
| Root package của module được đổi tên | Tên module, package API, `allowedDependencies`, Named Interface và tài liệu kiến trúc |
| Type chuyển giữa root package và package con | API boundary mặc định thay đổi |
| Package chứa lớp `@SpringBootApplication` thay đổi | Application root, module discovery, component scan và các scan base package khác |

Sau đó thực hiện theo trình tự:

1. Ghi lại module model và dependency graph hiện tại bằng `ApplicationModules`.
2. Xác định ownership mong muốn của package và type sau refactor.
3. Di chuyển source cùng `package-info.java`, cập nhật fully qualified name và các import.
4. Rà soát `@ApplicationModule`, `@NamedInterface`, `allowedDependencies` và cấu hình scan liên quan.
5. Tạo lại mô hình `ApplicationModules` để xác nhận module discovery.
6. Chạy `ApplicationModules.verify()` và xử lý các vi phạm theo đúng nguyên nhân.
7. Chạy các test ứng dụng phù hợp để xác nhận component, repository và configuration properties vẫn được phát hiện.

Đừng chỉ dựa vào việc IDE đã cập nhật import hoặc project biên dịch thành công. Compiler không biết module nào nên sở hữu type hoặc package nào cần là API. Kiểm tra kiến trúc mới xác nhận được những quyết định đó.

## 11. Những nhầm lẫn thường gặp

| Nhận định | Cách hiểu chính xác |
| --- | --- |
| Đổi tên thư mục luôn tạo module mới. | Spring Modulith phân tích Java package và vị trí trong cây package, không chỉ tên thư mục trên ổ đĩa. |
| Mọi package con đều là application module. | Theo mặc định, package con trực tiếp của application root mới là module; package sâu hơn thường thuộc module cha. |
| Di chuyển package con trong cùng module luôn làm dependency graph thay đổi. | Ownership module thường giữ nguyên, nhưng fully qualified name và API boundary có thể thay đổi. |
| Đưa package con lên cấp application root chỉ là di chuyển code. | Nó có thể tạo module mới và chuyển ownership, làm xuất hiện dependency edge giữa module. |
| Giữ modifier `public` nghĩa là API không thay đổi khi đổi package. | Vị trí package quyết định type thuộc API package hay internal package của closed module. |
| Đổi root package không ảnh hưởng cấu hình. | Tên module, allowlist, Named Interface, component scan và các cấu hình dựa vào package có thể cần cập nhật. |
| Project biên dịch được là module model vẫn đúng. | Cần tạo lại `ApplicationModules` và chạy `verify()` để kiểm tra các boundary và dependency mới. |

## 12. Ghi nhớ

Đổi package có thể làm thay đổi module model vì Spring Modulith nhận diện application module từ cây Java package. Di chuyển package con bên trong cùng module thường giữ nguyên ownership; đưa package lên cấp con trực tiếp của application root có thể tạo module mới; đổi root package có thể đổi tên module; chuyển type giữa root package và package con có thể làm thay đổi API boundary.

Khi refactor, hãy kiểm tra cả package root của ứng dụng, root package của module, `package-info.java`, Named Interface, `allowedDependencies` và các cấu hình scanning. Sau khi di chuyển, tạo lại `ApplicationModules`, quan sát module được phát hiện và chạy `verify()` để xác nhận dependency graph và boundary. Một thay đổi package chỉ hoàn tất khi cấu trúc mới vẫn phản ánh đúng ownership, API và quan hệ phụ thuộc mà nhóm mong muốn.

## Tài liệu tham khảo

- [Spring Modulith Reference — Fundamentals](https://docs.spring.io/spring-modulith/reference/fundamentals.html)
- [Spring Modulith Reference — Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html)
- [Spring Boot Reference — Structuring Your Code](https://docs.spring.io/spring-boot/reference/using/structuring-your-code.html)
