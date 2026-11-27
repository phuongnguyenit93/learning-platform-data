# Package của lớp ứng dụng chính làm root package

Vị trí package của lớp ứng dụng chính trong Spring Boot quyết định phạm vi mặc định mà framework dùng để tìm thành phần của ứng dụng. Spring Modulith cũng dựa vào lớp ứng dụng được cung cấp để xác định package gốc khi khám phá các application module. Vì vậy, đặt lớp có `@SpringBootApplication` ở đúng package gốc là bước nền tảng để component scanning và mô hình mô-đun cùng nhìn thấy một cấu trúc nhất quán.

Trong phạm vi **SPRING_MODULITH_MODULE_MODEL**, ta tổ chức các package theo năng lực nghiệp vụ, xác định API công khai và quản lý phụ thuộc giữa các mô-đun trong một modular monolith. Package của lớp ứng dụng chính là điểm bắt đầu để Spring Boot quét bean và để Spring Modulith khám phá các mô-đun nằm bên dưới.

## 1. Root package là gì?

Trong một ứng dụng Spring Boot, lớp chính thường được đánh dấu bằng `@SpringBootApplication` và chứa phương thức `main` để khởi chạy ứng dụng:

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

Package `com.acme.shop` là package gốc (root package) của lớp ứng dụng. Theo cấu hình mặc định, `@SpringBootApplication` kích hoạt component scanning từ package chứa lớp này và đi xuống các package con. Các bean như `@Component`, `@Service`, `@Repository` và `@Controller` nằm bên dưới phạm vi đó có thể được phát hiện và đăng ký trong application context.

Spring Boot cũng dùng package ứng dụng làm cơ sở cho một số cơ chế tự động cấu hình, chẳng hạn suy ra vùng package mặc định cho việc tìm entity và repository trong các cấu hình tương ứng. Vì vậy, package của lớp chính ảnh hưởng đến việc ứng dụng có tìm thấy các thành phần cần thiết khi khởi động hay không.

Spring Modulith sử dụng lớp ứng dụng làm điểm tham chiếu để khám phá cấu trúc mô-đun. Khi gọi:

```java
ApplicationModules modules = ApplicationModules.of(ShopApplication.class);
```

Spring Modulith xác định package ứng dụng từ `ShopApplication` rồi nhận diện các application module theo cấu trúc package bên dưới. Vì vậy, package gốc cần bao phủ các mô-đun thuộc cùng ứng dụng.

## 2. Đặt lớp ứng dụng ở package cha chung của các mô-đun

Giả sử hệ thống bán hàng có ba năng lực nghiệp vụ: quản lý đơn hàng, tồn kho và khách hàng. Cấu trúc phù hợp có thể là:

```text
com.acme.shop                         // root package
├── ShopApplication.java              // @SpringBootApplication
├── orders                             // application module
│   ├── OrderManagement.java
│   ├── web
│   └── internal
├── inventory                          // application module
│   ├── InventoryManagement.java
│   ├── api
│   └── internal
└── customers                          // application module
    ├── CustomerManagement.java
    └── internal
```

Lớp `ShopApplication` nằm ở `com.acme.shop`, là package cha chung của `orders`, `inventory` và `customers`. Các mô-đun được đặt bên dưới package gốc nên component scanning có thể tìm thấy các bean của chúng, đồng thời Spring Modulith có thể khám phá chúng từ cùng một điểm bắt đầu.

Theo quy ước khám phá mặc định, các package con trực tiếp của package ứng dụng là các application module. Do đó:

- `com.acme.shop.orders` là một mô-đun.
- `com.acme.shop.inventory` là một mô-đun.
- `com.acme.shop.customers` là một mô-đun.
- `com.acme.shop.orders.internal` là package con thuộc mô-đun `orders`, không tự trở thành một mô-đun ngang hàng.

Điều này cho phép một mô-đun tổ chức sâu hơn theo trách nhiệm triển khai mà vẫn giữ nguyên ranh giới nghiệp vụ cấp cao.

## 3. Tại sao không nên đặt lớp ứng dụng quá sâu?

Giả sử lớp chính được đặt trong package `com.acme.shop.bootstrap`:

```text
com.acme.shop
├── bootstrap
│   └── ShopApplication.java
├── orders
├── inventory
└── customers
```

Khi đó package chứa `ShopApplication` là `com.acme.shop.bootstrap`. Component scanning mặc định đi xuống `bootstrap` và các package con của nó; các package anh em như `orders`, `inventory` và `customers` nằm ngoài phạm vi mặc định. Hệ quả có thể là bean không được phát hiện, dẫn đến lỗi thiếu bean khi khởi động.

Tương tự, khi dùng `ApplicationModules.of(ShopApplication.class)`, Spring Modulith lấy package của lớp ứng dụng làm cơ sở khám phá. Các mô-đun nằm bên ngoài `com.acme.shop.bootstrap` không thuộc cây package gốc đó, nên mô hình mô-đun có thể thiếu các mô-đun dự kiến.

Giải pháp rõ ràng nhất là đặt lớp ứng dụng ở package cha chung:

```text
com.acme.shop
├── ShopApplication.java
├── bootstrap
├── orders
├── inventory
└── customers
```

Có thể tùy chỉnh phạm vi component scanning của Spring Boot bằng cấu hình riêng, nhưng việc mở rộng scan package không tự động thay đổi package gốc mà Spring Modulith suy ra từ lớp được truyền vào `ApplicationModules.of(...)`. Nếu tùy chỉnh hai cơ chế riêng rẽ, cần kiểm tra cả hai phạm vi để tránh tình trạng Spring Boot nhìn thấy bean nhưng mô hình Modulith không nhìn thấy mô-đun.

## 4. Tránh đặt lớp ứng dụng quá cao

Đặt lớp chính ở package quá cao cũng có thể gây ra phạm vi quét rộng hơn dự kiến. Ví dụ, nếu lớp chính nằm trong `com.acme`, những package con khác như `com.acme.reporting`, `com.acme.billing` hoặc `com.acme.identity` có thể bị đưa vào phạm vi quét và khám phá.

Điều đó có thể dẫn đến:

- Các bean của ứng dụng khác được quét vào application context hiện tại.
- Các package không thuộc hệ thống bán hàng bị hiểu nhầm là mô-đun của hệ thống.
- Ranh giới giữa các ứng dụng hoặc bounded context trở nên khó xác định.
- Kiểm chứng kiến trúc phát hiện thêm các phụ thuộc ngoài phạm vi mong muốn.

Hãy chọn package cha chung nhỏ nhất bao phủ tất cả mô-đun thuộc ứng dụng. Với ví dụ trên, `com.acme.shop` là lựa chọn hợp lý hơn `com.acme` hoặc `com.acme.shop.bootstrap`.

## 5. Root package và cách tổ chức package theo nghiệp vụ

Khi dùng Spring Modulith, nên tổ chức package theo tính năng hoặc năng lực nghiệp vụ (package by feature), thay vì gom tất cả lớp theo tầng kỹ thuật ở cấp cao nhất.

Ví dụ cấu trúc theo tầng kỹ thuật:

```text
com.acme.shop
├── ShopApplication.java
├── controller
├── service
├── repository
└── entity
```

Theo quy ước khám phá mô-đun, `controller`, `service`, `repository` và `entity` có thể bị nhận diện như các mô-đun riêng. Cách chia này làm cho một năng lực nghiệp vụ như `orders` bị phân tán qua nhiều package cấp cao và khiến ranh giới mô-đun không phản ánh cách nghiệp vụ vận hành.

Thay vào đó, tổ chức theo nghiệp vụ trước, rồi mới chia tầng bên trong từng mô-đun:

```text
com.acme.shop
├── ShopApplication.java
├── orders
│   ├── web
│   ├── application
│   ├── domain
│   └── internal
├── inventory
│   ├── web
│   ├── application
│   ├── domain
│   └── internal
└── customers
    ├── web
    ├── application
    ├── domain
    └── internal
```

Trong cách tổ chức này, `orders`, `inventory` và `customers` là các mô-đun. Các package `web`, `application`, `domain` và `internal` là cấu trúc nội bộ của từng mô-đun. Nhờ vậy, các lớp có cùng trách nhiệm nghiệp vụ nằm gần nhau và có thể được kiểm soát qua một API mô-đun rõ ràng.

## 6. Cách xác nhận package gốc và mô hình mô-đun

Khi kiểm tra một ứng dụng hiện có, hãy xác nhận package khai báo ở đầu file của lớp chính:

```java
package com.acme.shop;
```

Sau đó đối chiếu với package của các mô-đun. Mỗi mô-đun dự kiến phải nằm bên dưới package gốc. Có thể tạo mô hình và liệt kê tên các mô-đun được khám phá:

```java
import org.springframework.modulith.core.ApplicationModules;

ApplicationModules modules = ApplicationModules.of(ShopApplication.class);

modules.stream()
    .map(module -> module.getName())
    .sorted()
    .forEach(System.out::println);
```

Nếu kết quả thiếu `orders`, `inventory` hoặc `customers`, hãy kiểm tra package của lớp chính và package khai báo của các mô-đun. Cũng cần xác nhận tên package trong source code khớp với vị trí và cấu trúc package dự kiến.

Để đưa quy tắc kiến trúc vào kiểm thử, dùng `verify()`:

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

Kiểm thử này xác minh mô hình mô-đun được khám phá từ lớp ứng dụng và kiểm tra các quy tắc kiến trúc mà Spring Modulith áp dụng, chẳng hạn các phụ thuộc không hợp lệ hoặc chu trình phụ thuộc. Nó giúp phát hiện sớm cấu trúc package không phù hợp với ranh giới đã định.

## 7. Checklist khi chọn package cho lớp ứng dụng chính

Khi tạo dự án mới hoặc tái cấu trúc, hãy tự kiểm tra:

1. Lớp `@SpringBootApplication` nằm trong package cha chung của các mô-đun.
2. Các mô-đun nghiệp vụ nằm trong các package con trực tiếp của package gốc.
3. Package con sâu hơn được dùng để tổ chức nội bộ từng mô-đun.
4. Các package cấp cao phản ánh năng lực nghiệp vụ, không phải chỉ là tầng kỹ thuật dùng chung.
5. Không đặt lớp ứng dụng trong default package hoặc package con quá sâu khiến các mô-đun anh em nằm ngoài phạm vi.
6. Package gốc không rộng đến mức vô tình bao gồm các ứng dụng hoặc bounded context khác.
7. `ApplicationModules.of(ShopApplication.class).verify()` chạy thành công trong bộ kiểm thử kiến trúc.

## 8. Những nhầm lẫn thường gặp

- **Cho rằng vị trí file không quan trọng.** Package khai báo của lớp chính là cơ sở cho phạm vi quét mặc định và việc khám phá mô-đun.
- **Chỉ mở rộng `scanBasePackages` là đủ.** Cấu hình component scanning của Spring Boot và package gốc mà Spring Modulith suy ra là hai vấn đề cần được kiểm tra riêng.
- **Đặt lớp chính trong package của một mô-đun.** Điều này có thể khiến các mô-đun ngang hàng nằm ngoài package gốc.
- **Chia package theo controller/service/repository ở cấp gốc.** Cách chia này thường làm cấu trúc mô-đun đi theo tầng kỹ thuật thay vì năng lực nghiệp vụ.
- **Đặt lớp chính ở package cha quá rộng.** Việc quét và khám phá có thể kéo thêm các package không thuộc ứng dụng.
- **Cho rằng package con của mô-đun là mô-đun độc lập.** Các package con sâu hơn thường thuộc mô-đun cha; ranh giới mô-đun mặc định được xác định ở cấp package con trực tiếp của package ứng dụng.

## Kết luận

Hãy đặt lớp có `@SpringBootApplication` trong package cha chung, nhỏ nhất bao phủ các mô-đun nghiệp vụ. Cách bố trí này giúp Spring Boot quét bean trong phạm vi dự kiến và giúp Spring Modulith khám phá đúng cây package của ứng dụng. Từ root package đó, tổ chức các package con trực tiếp theo năng lực nghiệp vụ, giữ các package sâu hơn cho chi tiết nội bộ, rồi dùng `ApplicationModules.of(ShopApplication.class).verify()` để kiểm chứng cấu trúc.
