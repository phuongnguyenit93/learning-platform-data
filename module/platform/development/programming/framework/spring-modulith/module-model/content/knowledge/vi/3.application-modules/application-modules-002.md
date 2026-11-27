# Khởi tạo bằng ApplicationModules.of(Application.class)

Trong Spring Modulith, `ApplicationModules` là đối tượng đại diện cho mô hình module của một ứng dụng Spring Boot. Ta khởi tạo mô hình bằng cách truyền vào lớp ứng dụng làm điểm neo:

```java
ApplicationModules modules = ApplicationModules.of(Application.class);
```

Lời gọi này cho Spring Modulith biết cần phân tích cấu trúc package bắt đầu từ đâu để nhận diện các module nghiệp vụ và quan hệ phụ thuộc giữa chúng. `Application.class` là cú pháp lấy đối tượng `Class` của lớp ứng dụng; trong dự án thực tế, tên lớp có thể là `ShopApplication.class`, `OrderServiceApplication.class` hoặc tên khác do nhóm đặt.

Đối với module `SPRING_MODULITH_MODULE_MODEL`, hiểu đúng điểm khởi tạo này là bước đầu để sử dụng `ApplicationModules` cho các công việc tiếp theo như kiểm chứng ranh giới module, xem mô hình phụ thuộc và sinh tài liệu kiến trúc.

## 1. ApplicationModules là gì?

`ApplicationModules` thuộc package `org.springframework.modulith.core`. Nó mô tả các application module được Spring Modulith phát hiện trong ứng dụng, cùng những thông tin kiến trúc liên quan như package thuộc module, các kiểu được module khác sử dụng và quan hệ phụ thuộc giữa các module.

Ví dụ, một ứng dụng thương mại điện tử có thể được tổ chức như sau:

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
└── customer
    ├── CustomerManagement.java
    └── internal
        └── CustomerRepository.java
```

Với cấu trúc mặc định, `order`, `inventory` và `customer` là các application module vì chúng là package con trực tiếp của package gốc ứng dụng. Các package lồng bên trong mỗi module, chẳng hạn `order.internal`, thuộc phạm vi module `order`; chúng không tự động trở thành module cấp cao riêng.

Mô hình giúp trả lời các câu hỏi như:

- Ứng dụng có những module nghiệp vụ nào?
- Mỗi module sở hữu những package nào?
- Module nào đang phụ thuộc vào module nào?
- Module tiêu thụ đang sử dụng API công khai hay truy cập vào phần triển khai nội bộ của module khác?

## 2. Chọn lớp ứng dụng làm điểm neo

Tham số của `ApplicationModules.of(...)` là một đối tượng `Class<?>`. Trong đa số ứng dụng Spring Boot, ta truyền lớp có annotation `@SpringBootApplication`, vì lớp này thường nằm ở package gốc bao quanh các module nghiệp vụ.

Ví dụ:

```java
package com.acme.shop;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ShopApplication {

    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
```

Lớp `ShopApplication` nằm tại `com.acme.shop`. Các module `order`, `inventory` và `customer` nằm bên dưới package này. Khi tạo mô hình, ta truyền chính lớp đó:

```java
import org.springframework.modulith.core.ApplicationModules;

ApplicationModules modules = ApplicationModules.of(ShopApplication.class);
```

Tên `Application.class` trong biểu thức tổng quát chỉ là tên lớp ví dụ. Nếu lớp khởi động của dự án là `ShopApplication`, hãy dùng `ShopApplication.class`. Java truyền tham chiếu lớp ở thời điểm biên dịch; đây không phải chuỗi tên lớp và cũng không phải một instance của application.

### Vì sao vị trí package của lớp ứng dụng quan trọng?

Spring Modulith dùng package của lớp được truyền vào làm package gốc để phát hiện cấu trúc module. Do đó, nên đặt lớp ứng dụng ở package gốc chung của các module.

Ví dụ phù hợp:

```text
com.acme.shop
├── ShopApplication.java
├── order
├── inventory
└── customer
```

Nếu đặt lớp ứng dụng quá sâu:

```text
com.acme.shop
├── order
├── inventory
└── bootstrap
    └── ShopApplication.java
```

thì package gốc lấy từ lớp `ShopApplication` sẽ là `com.acme.shop.bootstrap`. Các package `order` và `inventory` nằm ngoài nhánh đó, nên mô hình có thể không phát hiện được các module mà nhóm mong đợi. Khi gặp tình huống này, hãy kiểm tra package khai báo của lớp ứng dụng và cấu trúc package thực tế.

## 3. Khởi tạo mô hình trong code

Để tạo mô hình, import `ApplicationModules` và gọi phương thức factory tĩnh `of` với lớp ứng dụng:

```java
import org.springframework.modulith.core.ApplicationModules;

public class ModuleModelExample {

    public ApplicationModules createModel() {
        return ApplicationModules.of(ShopApplication.class);
    }
}
```

Phương thức `of` trả về một đối tượng `ApplicationModules`. Ta có thể giữ đối tượng này trong biến để sử dụng cho nhiều thao tác tiếp theo. Chẳng hạn, cùng một mô hình có thể được đưa vào bước kiểm chứng kiến trúc hoặc công cụ sinh tài liệu.

Lưu ý rằng `ApplicationModules.of(...)` tạo mô hình cấu trúc từ lớp và package có trên classpath. Nó không tương đương với `SpringApplication.run(...)`: lời gọi này không khởi chạy ứng dụng, không mở web server và không tạo toàn bộ Spring `ApplicationContext` chỉ để nhận diện module.

## 4. Tạo mô hình và kiểm chứng là hai thao tác riêng

Việc tạo đối tượng `ApplicationModules` cho ta mô hình để làm việc. Để yêu cầu Spring Modulith kiểm tra các quy tắc kiến trúc, cần gọi `verify()`:

```java
ApplicationModules modules = ApplicationModules.of(ShopApplication.class);

modules.verify();
```

`verify()` kiểm tra cấu trúc phụ thuộc theo các quy tắc module mà Spring Modulith nhận diện, bao gồm những vấn đề như phụ thuộc vòng hoặc truy cập vào phần nội bộ của module khác. Nếu có vi phạm, thao tác kiểm chứng báo lỗi để nhóm phát triển xử lý.

Có thể đưa kiểm tra này vào JUnit để tự động chạy cùng test suite:

```java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ApplicationModuleVerificationTests {

    @Test
    void verifiesApplicationModuleStructure() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
```

Đặt bài kiểm tra trong source set test giúp CI phát hiện thay đổi làm phá vỡ ranh giới module ngay trong quá trình tích hợp. Nếu chỉ gọi `of(...)` mà không gọi `verify()` hoặc một thao tác sử dụng mô hình khác, ta mới chỉ tạo mô hình; chưa yêu cầu kiểm chứng kiến trúc.

## 5. Các điều kiện để khởi tạo đúng

Khi `ApplicationModules.of(...)` không tạo ra mô hình như mong đợi, hãy kiểm tra lần lượt các điều kiện sau:

| Điều kiện | Cần kiểm tra | Hệ quả nếu cấu hình sai |
|---|---|---|
| Đúng lớp ứng dụng | Truyền lớp ứng dụng thực tế, thường là lớp có `@SpringBootApplication` | Phân tích bắt đầu từ sai package gốc |
| Đúng package gốc | Lớp ứng dụng nằm ở package cha chung của các module | Một số module có thể nằm ngoài phạm vi phát hiện |
| Cấu trúc package rõ ràng | Các module mặc định nằm trong những package con trực tiếp của package gốc | Các package có thể bị gom hoặc nhận diện khác dự kiến |
| Có dependency phù hợp | Module `spring-modulith-core` có trên compile/test classpath và phiên bản được quản lý nhất quán với Spring Modulith đang dùng | Không biên dịch được import hoặc không gọi được API |
| Có lớp trong classpath | Các lớp của ứng dụng đã được biên dịch và hiện diện trong runtime classpath của thao tác phân tích | Mô hình không thể phản ánh đầy đủ cấu trúc mã nguồn |

Trong Maven, dependency lõi thường được khai báo như sau khi dự án đã quản lý phiên bản Spring Modulith bằng BOM:

```xml
<dependency>
    <groupId>org.springframework.modulith</groupId>
    <artifactId>spring-modulith-core</artifactId>
</dependency>
```

Nếu dự án đã dùng starter Spring Modulith phù hợp, dependency lõi có thể đã được kéo vào gián tiếp. Hãy kiểm tra dependency tree của chính dự án trước khi thêm một khai báo trùng lặp. Không nên trộn các phiên bản Spring Modulith khác nhau giữa những module thư viện.

## 6. Ví dụ hoàn chỉnh: tạo mô hình cho ứng dụng Shop

Giả sử cấu trúc ứng dụng là:

```text
com.acme.shop
├── ShopApplication.java
├── order
│   ├── OrderManagement.java
│   └── internal
│       └── OrderRepository.java
└── inventory
    ├── InventoryManagement.java
    └── internal
        └── StockRepository.java
```

Ta có thể tạo mô hình và kiểm chứng nó trong một bài test:

```java
package com.acme.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ShopModuleTests {

    @Test
    void createsAndVerifiesModuleModel() {
        ApplicationModules modules = ApplicationModules.of(ShopApplication.class);

        modules.verify();
    }
}
```

Khi test chạy, Spring Modulith sử dụng `ShopApplication.class` làm điểm neo, phân tích các package bên dưới `com.acme.shop`, xây dựng mô hình module và thực thi kiểm chứng. Nếu quan hệ phụ thuộc tuân thủ các quy tắc, test hoàn tất thành công. Nếu một module truy cập trái phép vào phần nội bộ hoặc tạo quan hệ phụ thuộc không hợp lệ, test thất bại và cung cấp thông tin để điều tra.

Từ đây, cùng đối tượng `modules` cũng có thể được dùng trong các bước tiếp theo của quy trình kiến trúc, ví dụ truyền cho `Documenter` để sinh sơ đồ. Việc tái sử dụng cùng một mô hình giúp các thao tác sau cùng dựa trên một điểm bắt đầu và cùng cách nhận diện module.

## 7. Những nhầm lẫn thường gặp

**Nhầm `Application.class` với tên cố định bắt buộc.** `Application` chỉ là tên minh họa. Hãy truyền class literal của lớp ứng dụng thực tế, ví dụ `ShopApplication.class`.

**Truyền lớp cấu hình nằm sâu trong một module.** Lớp được truyền xác định package gốc phân tích. Nếu lớp nằm sâu dưới package của module, các module ngang hàng có thể bị bỏ ngoài phạm vi. Hãy chọn lớp ứng dụng ở package gốc chung.

**Cho rằng gọi `of()` đồng nghĩa ứng dụng đã được khởi động.** `of()` tạo mô hình module. Việc khởi chạy Spring Boot và tạo application context là một quy trình khác.

**Cho rằng tạo mô hình tự động làm CI thất bại khi có mọi vi phạm.** Hãy gọi `verify()` trong test hoặc trong bước kiểm tra kiến trúc để yêu cầu xác minh các quy tắc.

**Cho rằng mọi package con đều là module cấp cao.** Theo chiến lược phát hiện mặc định, package con trực tiếp của package gốc là module; các package sâu hơn thường thuộc về module cha.

## Kết luận

`ApplicationModules.of(Application.class)` là điểm khởi đầu để Spring Modulith xây dựng mô hình module từ cấu trúc package của ứng dụng. Đối số cần là lớp ứng dụng thực tế, thường nằm ở package gốc chung của các module. Sau khi có đối tượng `ApplicationModules`, ta có thể dùng nó để kiểm chứng kiến trúc bằng `verify()` và làm đầu vào cho các công cụ khác. Đặt đúng lớp ứng dụng và hiểu rõ ranh giới giữa tạo mô hình với kiểm chứng giúp nhóm sử dụng Spring Modulith nhất quán trong test suite và CI.
