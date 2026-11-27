# Chiến lược phát hiện module mặc định

Bài này thuộc chương **Module detection** của module **SPRING_MODULITH_MODULE_MODEL**. Spring Modulith mô hình hóa một ứng dụng Spring Boot thành các application module để làm rõ ranh giới nghiệp vụ, API công khai và phụ thuộc giữa các package. Trước khi kiểm tra những ranh giới đó, framework cần xác định package nào tạo thành module.

Theo chiến lược mặc định, Spring Modulith xem **các package con trực tiếp của application base package là các application module**. Quy tắc này khiến cấu trúc package cấp cao trở thành một phần của thiết kế kiến trúc: mỗi package capability nằm ngay dưới package gốc ứng dụng có thể trở thành một module; các package lồng sâu hơn thường là phần bên trong module đó.

## 1. Application base package là mốc phát hiện

Application base package thường là package chứa lớp chính được đánh dấu bằng `@SpringBootApplication`.

Ví dụ:

~~~java
package com.acme.shop;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ShopApplication {

    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
~~~

Trong ví dụ này, application base package là `com.acme.shop`. Khi xây dựng mô hình:

~~~java
import org.springframework.modulith.core.ApplicationModules;

ApplicationModules modules = ApplicationModules.of(ShopApplication.class);
~~~

Spring Modulith sử dụng lớp ứng dụng làm điểm bắt đầu để xác định package gốc và khám phá các module theo chiến lược phát hiện mặc định.

Điều quan trọng là chọn đúng lớp ứng dụng. Nếu package gốc quá hẹp, một số capability có thể nằm ngoài phạm vi khám phá. Nếu package gốc đặt quá sâu, cấu trúc module được nhận diện có thể không phản ánh toàn bộ ứng dụng như nhóm mong muốn.

## 2. Quy tắc mặc định: package con trực tiếp là module

Giả sử ứng dụng bán hàng có cấu trúc:

~~~text
com.acme.shop
├── ShopApplication.java
├── order
│   ├── OrderManagement.java
│   └── internal
│       ├── application
│       │   └── PlaceOrderHandler.java
│       ├── domain
│       │   └── Order.java
│       └── persistence
│           └── JpaOrderRepository.java
├── inventory
│   ├── StockAvailability.java
│   └── internal
│       ├── domain
│       └── persistence
├── customer
│   └── CustomerProfile.java
└── payment
    └── PaymentUseCases.java
~~~

Với application base package là `com.acme.shop`, các package con trực tiếp là:

- `com.acme.shop.order`
- `com.acme.shop.inventory`
- `com.acme.shop.customer`
- `com.acme.shop.payment`

Theo chiến lược mặc định, đây là bốn application module được phát hiện. Package `com.acme.shop.order.internal` và các package sâu hơn thuộc cấu trúc bên trong module order; chúng không tự trở thành module cấp cao ngang hàng với order.

Có thể biểu diễn quy tắc như sau:

~~~text
Application base package: com.acme.shop
│
├── order       -> application module
│   └── internal
│       ├── domain
│       └── persistence
│
├── inventory   -> application module
│   └── internal
│       └── persistence
│
├── customer    -> application module
│
└── payment     -> application module
~~~

Cấp độ package trong cây là yếu tố quyết định vai trò mặc định. Một package có tên `internal`, `domain` hay `persistence` không tự tạo ra module mới nếu nó nằm sâu bên trong một module đã được nhận diện.

## 3. Vì sao chiến lược mặc định dùng package con trực tiếp?

Chiến lược này tạo ra một quy ước đơn giản và dễ dự đoán:

- **Ranh giới cấp cao rõ ràng:** mỗi package capability trực tiếp dưới package gốc là một module.
- **Cấu trúc bên trong linh hoạt:** nhóm có thể chia module thành web, application, domain, persistence hoặc integration mà không biến mỗi tầng thành module cấp cao.
- **Dễ khám phá:** người đọc có thể nhìn cây package để nhận biết những phần chính của ứng dụng.
- **Hỗ trợ modular monolith:** các capability có thể cùng chạy trong một ứng dụng nhưng vẫn có ranh giới và phụ thuộc được kiểm tra.
- **Ít cấu hình ban đầu:** nhóm có thể bắt đầu bằng quy ước package mà chưa cần khai báo riêng từng module.

Đổi lại, nhóm cần tổ chức package cấp cao có chủ đích. Nếu package con trực tiếp được đặt theo technical layer, mô hình phát hiện có thể phản ánh các tầng kỹ thuật thay vì capability nghiệp vụ.

## 4. Cách tổ chức package làm thay đổi kết quả phát hiện

So sánh hai cấu trúc sau.

Cấu trúc theo technical layer:

~~~text
com.acme.shop
├── ShopApplication.java
├── controller
│   ├── OrderController.java
│   └── InventoryController.java
├── service
│   ├── OrderService.java
│   └── InventoryService.java
└── repository
    ├── OrderRepository.java
    └── InventoryRepository.java
~~~

Theo quy tắc mặc định, các package con trực tiếp là `controller`, `service` và `repository`. Đây sẽ là những ranh giới module được nhận diện theo cấu trúc, dù chúng không nhất thiết đại diện cho capability nghiệp vụ mà nhóm muốn bảo vệ.

Cấu trúc theo capability:

~~~text
com.acme.shop
├── ShopApplication.java
├── order
│   ├── OrderManagement.java
│   └── internal
│       ├── web
│       ├── application
│       └── persistence
└── inventory
    ├── StockAvailability.java
    └── internal
        ├── web
        ├── application
        └── persistence
~~~

Ở đây, `order` và `inventory` là package con trực tiếp, nên chúng trở thành module. Các technical layer nằm bên trong từng capability. Cấu trúc này thường phù hợp hơn khi mục tiêu là mô hình hóa modular monolith theo nghiệp vụ.

Vì vậy, trước khi áp dụng kiểm tra kiến trúc, hãy xem lại cây package cấp cao. Công cụ phát hiện module dựa trên quy ước; chất lượng của ranh giới phụ thuộc vào cách nhóm tổ chức package.

## 5. Phân biệt module được phát hiện và package nội bộ

Khi một package được phát hiện là module, package gốc của module đó cũng đóng vai trò API mặc định. Các package con của module thuộc phần nội bộ theo quy ước, trừ khi được công khai rõ ràng bằng named interface.

Ví dụ:

~~~text
com.acme.shop.order
├── OrderManagement.java
├── OrderSummary.java
├── internal
│   ├── application
│   ├── domain
│   └── persistence
└── shipping
    ├── package-info.java
    └── OrderShippingDetails.java
~~~

Trong ví dụ này:

- `com.acme.shop.order` là module base package và cung cấp API mặc định.
- `com.acme.shop.order.internal` là package nội bộ.
- `com.acme.shop.order.shipping` vẫn nằm trong module order; nếu được đánh dấu bằng `@NamedInterface`, package này có thể trở thành một phần API được công khai có tên.

Không nên nhầm việc phát hiện module với việc công khai tất cả package con. Phát hiện xác định ranh giới module; API công khai xác định phần nào module khác được phép sử dụng.

## 6. Chọn application base package đúng cách

Một số nguyên tắc thực tế giúp tránh kết quả phát hiện ngoài ý muốn:

**Đặt lớp ứng dụng ở package gốc bao trùm các capability.** Nếu các module chính là order, inventory và payment, một package như `com.acme.shop` thường phù hợp để chứa lớp `ShopApplication`.

**Đặt capability thành package con trực tiếp.** Tránh đặt controller, service hoặc repository làm package con cấp cao nếu mục tiêu là phát hiện module theo nghiệp vụ.

**Giữ các package dùng chung có chủ sở hữu rõ ràng.** Nếu có một package như `sharedkernel` hoặc `catalog` được thiết kế như module riêng, hãy đặt nó ở đúng cấp package để chiến lược mặc định nhận diện.

**Không di chuyển lớp ứng dụng tùy tiện.** Trong Spring Boot, vị trí của `@SpringBootApplication` cũng ảnh hưởng đến phạm vi component scanning mặc định. Thay đổi package gốc có thể ảnh hưởng cả việc phát hiện module lẫn việc tìm bean; hãy kiểm tra cả hai khía cạnh khi tái cấu trúc.

**Không coi thư mục là bằng chứng duy nhất.** Spring Modulith làm việc với cấu trúc package và các kiểu Java được khám phá. Tên thư mục trong file system không tự tạo ra application module nếu không tương ứng với package trong mã nguồn.

## 7. Khi nào cần chiến lược phát hiện khác?

Quy tắc package con trực tiếp phù hợp với nhiều ứng dụng được tổ chức theo capability. Tuy nhiên, một số codebase legacy có cấu trúc package khác, hoặc nhóm muốn dùng một quy ước phát hiện riêng.

Spring Modulith có cơ chế chiến lược phát hiện module để tùy chỉnh cách xác định module. Khi cần thay đổi quy tắc mặc định, hãy kiểm tra API và cấu hình phù hợp với phiên bản Spring Modulith mà ứng dụng đang dùng, đồng thời ghi lại quy ước để cả nhóm hiểu được.

Trước khi tùy chỉnh, hãy tự hỏi:

- Cấu trúc package hiện tại có thể điều chỉnh để phù hợp với quy tắc mặc định không?
- Quy tắc riêng có thực sự phản ánh một cách tổ chức module nhất quán không?
- Người mới vào dự án có thể dự đoán module nào được phát hiện chỉ từ cấu trúc package không?
- Các bài kiểm tra kiến trúc có đang dùng cùng chiến lược với ứng dụng không?

Nếu có thể làm rõ cây package theo capability, quy ước mặc định thường giúp kiến trúc dễ đọc và ít bất ngờ hơn. Nếu cần chiến lược riêng, hãy coi nó là một quyết định kiến trúc cần được cấu hình và kiểm chứng nhất quán.

## 8. Kiểm chứng các module được phát hiện

Có thể tạo một bài kiểm tra kiến trúc để yêu cầu Spring Modulith xây dựng và xác minh mô hình:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void verifiesApplicationModuleStructure() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

Kiểm tra này giúp phát hiện các vi phạm trong mô hình module, chẳng hạn phụ thuộc vào package nội bộ hoặc quan hệ phụ thuộc không phù hợp với quy tắc đã khai báo.

Khi kiểm tra thất bại, hãy xem xét:

1. Lớp `ShopApplication` có nằm ở package gốc dự kiến không?
2. Các capability có được đặt thành package con trực tiếp không?
3. Có package technical layer nào vô tình trở thành module cấp cao không?
4. Các package con bên trong module có đang bị consumer truy cập trực tiếp không?
5. Các API và named interface đã phản ánh đúng hợp đồng mà module cần công khai chưa?

`verify()` kiểm tra các quy tắc kiến trúc mà mô hình biểu diễn. Nó không tự đánh giá rằng cách chia capability là đúng nghiệp vụ; nhóm vẫn cần review trách nhiệm và quyền sở hữu của từng module.

## 9. Quy trình áp dụng chiến lược mặc định

Có thể thực hiện theo trình tự sau:

1. **Xác định lớp ứng dụng.** Tìm lớp có `@SpringBootApplication` và xác nhận package của lớp đó.
2. **Xác định application base package.** Dùng package chứa lớp ứng dụng làm điểm bắt đầu.
3. **Liệt kê package con trực tiếp.** Đây là các ứng viên module theo chiến lược mặc định.
4. **Đối chiếu với capability.** Đảm bảo các package cấp cao đại diện cho trách nhiệm nghiệp vụ mong muốn.
5. **Tổ chức phần nội bộ.** Đặt technical layer và chi tiết triển khai bên trong package module.
6. **Xác định API công khai.** Dùng package gốc hoặc named interface cho những hợp đồng cần chia sẻ.
7. **Kiểm tra phụ thuộc.** Chạy `ApplicationModules.verify()` và xử lý những truy cập vượt ranh giới.

Khi ứng dụng phát triển, hãy xem lại cấu trúc package mỗi khi thêm capability hoặc di chuyển package. Một thay đổi vị trí có thể làm thay đổi module mà một kiểu thuộc về, từ đó ảnh hưởng đến API và dependency.

## Ghi nhớ

Chiến lược phát hiện module mặc định của Spring Modulith dựa trên **các package con trực tiếp của application base package**. Nếu package gốc ứng dụng là `com.acme.shop`, các package `order`, `inventory`, `customer` và `payment` là những module cấp cao; các package lồng sâu bên trong thuộc cấu trúc của module tương ứng.

Hãy đặt application base package ở vị trí bao trùm ứng dụng và tổ chức package con trực tiếp theo capability nghiệp vụ. Cách làm này giúp mô hình module dễ dự đoán, API dễ xác định và các quy tắc phụ thuộc dễ kiểm chứng bằng Spring Modulith.
