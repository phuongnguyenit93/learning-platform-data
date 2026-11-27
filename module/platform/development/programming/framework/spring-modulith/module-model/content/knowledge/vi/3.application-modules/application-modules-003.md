# Khởi tạo theo tên package gốc

Để Spring Modulith phân tích cấu trúc một ứng dụng, trước hết ta cần cho nó biết **package gốc** (base package) của ứng dụng nằm ở đâu. Từ package gốc này, Spring Modulith tìm các application module và xây dựng mô hình về những module cùng các quan hệ phụ thuộc giữa chúng.

Lớp khởi động Spring Boot thường là điểm neo thuận tiện nhất. Nếu lớp `ShopApplication` nằm trong package `com.example.shop`, ta có thể khởi tạo mô hình bằng `ApplicationModules.of(ShopApplication.class)`. Spring Modulith lấy package của lớp được truyền vào làm package gốc để khám phá các module bên dưới.

## 1. Package gốc xác định phạm vi khám phá

Giả sử ứng dụng bán hàng có cấu trúc như sau:

```text
com.example.shop
├── ShopApplication.java
├── catalog
│   ├── ProductCatalog.java
│   └── internal
│       ├── ProductEntity.java
│       └── ProductRepository.java
├── orders
│   ├── OrderManagement.java
│   └── internal
│       └── OrderService.java
└── inventory
    ├── StockAvailability.java
    └── internal
        └── StockRepository.java
```

Trong ví dụ này:

- `com.example.shop` là package gốc của ứng dụng.
- `com.example.shop.catalog`, `com.example.shop.orders` và `com.example.shop.inventory` là các package con trực tiếp, tương ứng với ba application module theo chiến lược phát hiện mặc định.
- Các package sâu hơn như `catalog.internal` và `orders.internal` thuộc phạm vi của module cha; chúng thường chứa phần triển khai nội bộ.

Package gốc đóng vai trò mốc để Spring Modulith bắt đầu phân tích. Nó không phải là một application module nghiệp vụ bổ sung. Vì vậy, chọn đúng package gốc sẽ quyết định những package nào được đưa vào mô hình kiến trúc.

## 2. Khởi tạo bằng lớp nằm trong package gốc

Trong ứng dụng Spring Boot, lớp có `@SpringBootApplication` thường được đặt ở package cao nhất chứa các package nghiệp vụ:

```java
package com.example.shop;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ShopApplication {

    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
```

Ta truyền lớp này cho `ApplicationModules.of`:

```java
import org.springframework.modulith.core.ApplicationModules;

ApplicationModules modules = ApplicationModules.of(ShopApplication.class);
```

`ApplicationModules.of(ShopApplication.class)` sử dụng package của `ShopApplication` — tức `com.example.shop` — làm package gốc. Từ đó, Spring Modulith khám phá các application module bên dưới package này theo chiến lược phát hiện đang được áp dụng.

Cách khởi tạo bằng `Class` thường được ưu tiên vì IDE và trình biên dịch có thể theo dõi lớp được tham chiếu. Khi đổi tên package hoặc di chuyển lớp khởi động, ta có thể dùng các công cụ refactor của IDE để cập nhật tham chiếu.

## 3. Khởi tạo trực tiếp bằng tên package

Khi không muốn truyền một lớp làm điểm neo, ta có thể chỉ định package gốc bằng chuỗi tên package:

```java
ApplicationModules modules = ApplicationModules.of("com.example.shop");
```

Hai cách khởi tạo trên thể hiện cùng một ý định nếu lớp `ShopApplication` thực sự nằm trong `com.example.shop`:

```java
ApplicationModules fromApplicationClass =
        ApplicationModules.of(ShopApplication.class);

ApplicationModules fromPackageName =
        ApplicationModules.of("com.example.shop");
```

Với cách dùng chuỗi, tên package phải chính xác và phải là package chung chứa các module cần phân tích. Nếu đổi cấu trúc package mà quên cập nhật chuỗi, mô hình có thể phân tích sai phạm vi hoặc không tìm thấy những module mong muốn. Vì vậy, trong mã kiểm thử của ứng dụng, cách truyền lớp gốc thường dễ bảo trì hơn.

## 4. Đưa việc khởi tạo vào kiểm thử kiến trúc

Sau khi tạo mô hình, ta có thể yêu cầu Spring Modulith kiểm tra các quy tắc kiến trúc bằng `verify()`:

```java
package com.example.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void verifiesApplicationModules() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
```

Kiểm thử này không cần khởi động toàn bộ Spring Application Context. `ApplicationModules` phân tích cấu trúc các lớp trên classpath dựa vào package gốc, sau đó `verify()` kiểm tra những quy tắc module mà Spring Modulith áp dụng, chẳng hạn chu trình phụ thuộc và việc truy cập package nội bộ trái quy ước.

Khi kiểm thử thành công, ta có thêm một bước bảo vệ ranh giới module trong quy trình build. Nếu một thay đổi làm `orders` phụ thuộc trực tiếp vào package nội bộ của `catalog`, hoặc tạo ra chu trình phụ thuộc giữa các module, kiểm thử có thể phát hiện vi phạm và trả về lỗi để nhóm xử lý.

## 5. Chọn package gốc đúng cách

Khi đặt lớp khởi động hoặc chọn tên package, hãy bảo đảm package gốc là tổ tiên chung của các application module cần phân tích.

Ví dụ, nếu lớp được truyền vào nằm trong `com.example.shop.orders`, Spring Modulith sẽ lấy package đó làm điểm bắt đầu. Khi ấy, `catalog` và `inventory` nằm bên ngoài phạm vi package này, nên chúng không được khám phá như những module ngang hàng của ứng dụng. Đây là lý do không nên đặt lớp neo trong một package nghiệp vụ con nếu mục tiêu là phân tích toàn bộ ứng dụng.

Một số lỗi thường gặp:

| Cấu hình | Hệ quả có thể gặp | Cách xử lý |
|---|---|---|
| Truyền lớp nằm trong package con như `com.example.shop.orders` | Phạm vi khám phá bị thu hẹp vào package đó | Truyền lớp khởi động hoặc lớp neo nằm trong `com.example.shop` |
| Dùng chuỗi package cũ sau khi đổi cấu trúc mã nguồn | Không tìm thấy hoặc bỏ sót module | Cập nhật tên package; cân nhắc dùng tham chiếu `Class` |
| Đặt module ở các package không cùng nằm dưới package gốc đã chọn | Một số module không thuộc phạm vi phân tích | Tổ chức các module dưới một package chung hoặc chọn package gốc bao quát chúng |
| Hiểu package lồng sâu là module ngang hàng | Phân chia module sai với cấu trúc dự kiến | Xác định module ở package con trực tiếp; giữ package triển khai sâu bên trong module cha |

Nếu ứng dụng có nhiều package gốc độc lập, hãy xem lại cách tổ chức package để có một package chung phù hợp với ranh giới ứng dụng. Đồng thời, cần bảo đảm cấu hình component scan của Spring Boot bao quát các thành phần cần chạy; phạm vi khám phá của Spring Modulith và phạm vi component scan có liên quan đến cách tổ chức package nhưng phục vụ hai mục đích khác nhau.

## 6. Tách biệt khởi tạo mô hình và kiểm tra quy tắc

`ApplicationModules.of(...)` tạo mô hình module từ package gốc. Bản thân lời gọi này chưa thay thế bước kiểm tra kiến trúc. Để kiểm chứng các quy tắc, hãy gọi `verify()` như trong ví dụ kiểm thử.

Ta có thể ghi nhớ trình tự sau:

```text
Chọn package gốc
        |
        v
ApplicationModules.of(...)
        |
        v
Khám phá application module
        |
        v
ApplicationModules.verify()
        |
        v
Kiểm tra quy tắc phụ thuộc và ranh giới module
```

Trong thực tế, hãy bắt đầu bằng cách đặt lớp `@SpringBootApplication` ở package gốc của ứng dụng, sau đó dùng `ApplicationModules.of(ShopApplication.class).verify()` trong một bài kiểm thử kiến trúc. Khi cấu trúc package thay đổi, kiểm thử này giúp phát hiện sớm việc chọn sai package gốc hoặc những thay đổi làm vi phạm ranh giới module.
