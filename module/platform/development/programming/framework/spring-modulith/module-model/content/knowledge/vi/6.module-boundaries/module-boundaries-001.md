# Ranh giới logic được suy ra từ package base

Bài này thuộc chương **Module boundary** của module **SPRING_MODULITH_MODULE_MODEL**. Spring Modulith mô hình hóa một ứng dụng Spring Boot thành các application module, mỗi module có trách nhiệm nghiệp vụ, API công khai và các quan hệ phụ thuộc riêng. Một điểm nền tảng của mô hình là **ranh giới module mặc định được suy ra từ cấu trúc package bắt đầu tại package của ứng dụng**.

Vì vậy, package không chỉ là cách nhóm file cho dễ tìm. Vị trí của một lớp trong cây package góp phần xác định nó thuộc module nào, phần nào của module được công khai và những phụ thuộc nào cần được kiểm soát.

## 1. Application base package là điểm bắt đầu khám phá

Spring Modulith cần một package gốc để xác định phạm vi ứng dụng. Thông thường, đó là package chứa lớp chính được đánh dấu bằng \`@SpringBootApplication\`.

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

Trong ví dụ này, **com.acme.shop** là application base package. Khi tạo mô hình bằng lớp ứng dụng:

~~~java
import org.springframework.modulith.core.ApplicationModules;

ApplicationModules modules = ApplicationModules.of(ShopApplication.class);
~~~

Spring Modulith dùng package của \`ShopApplication\` làm điểm bắt đầu để khám phá các application module theo quy ước package mặc định.

Cây package bên dưới package gốc có ý nghĩa kiến trúc. Các package con trực tiếp của application base package là những ranh giới module cấp cao được khám phá theo quy ước mặc định. Những package lồng sâu hơn thuộc cấu trúc bên trong module tương ứng, trừ khi được công khai như một named interface.

## 2. Package con trực tiếp xác định module cấp cao

Giả sử ứng dụng bán hàng được tổ chức như sau:

~~~text
com.acme.shop
├── ShopApplication.java
├── order
│   ├── OrderManagement.java
│   ├── OrderSummary.java
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

Với application base package là **com.acme.shop**, các package **order**, **inventory**, **customer** và **payment** là các package con trực tiếp. Theo quy ước mặc định, chúng tạo thành các application module:

| Package module | Trách nhiệm ví dụ |
|---|---|
| \`com.acme.shop.order\` | Tiếp nhận và quản lý vòng đời đơn hàng. |
| \`com.acme.shop.inventory\` | Kiểm tra và quản lý khả năng cung ứng hàng. |
| \`com.acme.shop.customer\` | Quản lý hồ sơ khách hàng. |
| \`com.acme.shop.payment\` | Điều phối nghiệp vụ thanh toán. |

Package \`com.acme.shop.order.internal\` nằm bên dưới package module \`com.acme.shop.order\`. Nó thuộc cấu trúc nội bộ của module order, không trở thành application module cấp cao ngang hàng với order chỉ vì nó là một package riêng.

Đây là khác biệt quan trọng giữa **package con trực tiếp của application base package** và **package lồng bên trong một module**. Cấp độ trong cây package quyết định vai trò mặc định của package trong mô hình.

## 3. Phân biệt application base package và module base package

Hai khái niệm này liên quan nhưng có phạm vi khác nhau:

- **Application base package** là package gốc của ứng dụng, thường chứa lớp \`@SpringBootApplication\`. Nó xác định phạm vi bắt đầu khám phá module.
- **Module base package** là package gốc của một application module, thường là package con trực tiếp của application base package. Nó xác định package thuộc module đó và là nơi đặt API mặc định của module.

Ví dụ:

~~~text
com.acme.shop                 <- application base package
├── ShopApplication.java
├── order                      <- module base package của order
│   ├── OrderManagement.java
│   └── internal
│       └── PlaceOrderHandler.java
└── inventory                  <- module base package của inventory
    ├── StockAvailability.java
    └── internal
        └── StockRepository.java
~~~

Có thể hình dung ranh giới logic mặc định như sau:

~~~text
Application: com.acme.shop
│
├── Module: order
│   ├── API mặc định: com.acme.shop.order
│   └── Internal:     com.acme.shop.order.*
│
└── Module: inventory
    ├── API mặc định: com.acme.shop.inventory
    └── Internal:     com.acme.shop.inventory.*
~~~

Package gốc của module là mốc để phân loại các package bên dưới nó. Vì thế, khi đọc một lớp có tên đầy đủ là \`com.acme.shop.order.internal.persistence.JpaOrderRepository\`, ta có thể xác định nó thuộc module order và nằm trong package con nội bộ persistence.

## 4. Package base cũng ảnh hưởng đến API mặc định

Nhận diện module và xác định API công khai là hai khía cạnh liên quan nhưng không giống nhau.

Theo quy ước mặc định của Spring Modulith, package gốc của module là giao diện không tên (unnamed interface) mà module khác có thể phụ thuộc vào. Các package con của module được xem là nội bộ, trừ khi được công khai rõ ràng bằng named interface.

Ví dụ, module order công khai hợp đồng ở package gốc:

~~~java
package com.acme.shop.order;

import java.util.UUID;

public interface OrderManagement {

    OrderSummary findById(UUID orderId);
}
~~~

Kiểu kết quả cũng thuộc API của module:

~~~java
package com.acme.shop.order;

import java.util.UUID;

public record OrderSummary(UUID id, String status) {
}
~~~

Trong khi đó, lớp triển khai có thể nằm ở package con:

~~~java
package com.acme.shop.order.internal.application;

import com.acme.shop.order.OrderManagement;
import com.acme.shop.order.OrderSummary;
import org.springframework.stereotype.Component;

import java.util.UUID;

@Component
class DefaultOrderManagement implements OrderManagement {

    @Override
    public OrderSummary findById(UUID orderId) {
        // Tải và chuyển đổi dữ liệu nội bộ của module order.
        return null;
    }
}
~~~

Module inventory hoặc shipping nên sử dụng \`OrderManagement\` nếu cần tra cứu đơn hàng. Chúng không nên phụ thuộc trực tiếp vào \`DefaultOrderManagement\` hay các repository nội bộ.

Nếu module cần công khai một nhóm hợp đồng ở package con, có thể khai báo named interface bằng \`@NamedInterface\` trong \`package-info.java\` của package đó:

~~~java
@org.springframework.modulith.NamedInterface("integration")
package com.acme.shop.order.integration;
~~~

Named interface tạo ra một bề mặt API có tên. Nó cho phép module công khai có chủ đích một package con mà không cần mở toàn bộ cấu trúc nội bộ.

## 5. Cấu trúc package có thể tạo ra ranh giới sai nếu chọn sai gốc

Vì module được suy ra từ package con trực tiếp của application base package, chọn package gốc không phù hợp có thể làm mô hình module khác với ý định nghiệp vụ.

Ví dụ, cấu trúc sau đặt technical layer ngay dưới package gốc:

~~~text
com.acme.shop
├── ShopApplication.java
├── controller
│   ├── order
│   │   └── OrderController.java
│   └── inventory
│       └── InventoryController.java
├── service
│   ├── order
│   │   └── OrderService.java
│   └── inventory
│       └── InventoryService.java
└── repository
    ├── order
    │   └── OrderRepository.java
    └── inventory
        └── InventoryRepository.java
~~~

Theo quy ước package mặc định, các package con trực tiếp là **controller**, **service** và **repository**. Những package như \`controller.order\` hoặc \`service.order\` nằm sâu bên trong các package đó. Do vậy, mô hình được suy ra không phản ánh trực tiếp module nghiệp vụ order và inventory như mong muốn.

Để ranh giới module phản ánh capability, hãy tổ chức package theo nghiệp vụ ngay dưới application base package:

~~~text
com.acme.shop
├── ShopApplication.java
├── order
│   ├── OrderManagement.java
│   └── internal
│       ├── web
│       ├── application
│       ├── domain
│       └── persistence
└── inventory
    ├── StockAvailability.java
    └── internal
        ├── web
        ├── application
        ├── domain
        └── persistence
~~~

Khi đó, package con trực tiếp là order và inventory; các technical layer nằm bên trong module sở hữu chúng. Cây package thể hiện rõ năng lực nghiệp vụ nào đang sở hữu một lớp.

## 6. Package lồng nhau không tự tạo thêm module cấp cao

Một hiểu nhầm phổ biến là cho rằng mỗi package đều là một module. Trong mô hình mặc định, không phải vậy.

Ví dụ:

~~~text
com.acme.shop
└── order
    ├── internal
    │   ├── web
    │   ├── application
    │   ├── domain
    │   └── persistence
    └── integration
~~~

Ở đây, \`order\` là package module cấp cao. Các package \`internal.web\`, \`internal.application\`, \`internal.domain\` và \`internal.persistence\` là các phần bên trong module order. Package \`integration\` cũng thuộc module order; nếu được đánh dấu bằng \`@NamedInterface\`, nó có thể trở thành một phần API được công khai có chủ đích.

Điều này giúp tránh phân mảnh mô hình thành hàng chục module nhỏ chỉ vì ứng dụng có nhiều package con. Module phản ánh ranh giới logic và quyền sở hữu; package con thường chỉ thể hiện cách module tổ chức nội bộ.

Cũng cần phân biệt package Java với thư mục vật lý. Một thư mục có tên giống package không tự nó tạo ra module nếu không có cấu trúc package Java tương ứng được Spring Modulith khám phá.

## 7. Java package visibility và ranh giới kiến trúc là hai chuyện khác nhau

Ranh giới suy ra từ package là quy tắc kiến trúc của ứng dụng. Nó không đồng nhất với cơ chế truy cập của ngôn ngữ Java.

Trong Java:

- Một lớp có modifier \`public\` có thể được truy cập từ package khác nếu các điều kiện biên dịch khác được đáp ứng.
- Thành phần package-private chỉ được truy cập từ chính package đó.
- Package con như \`com.acme.shop.order.internal\` là một package Java khác với \`com.acme.shop.order\`; package-private không tự động được chia sẻ giữa package cha và package con.

Spring Modulith bổ sung góc nhìn kiến trúc: package con của module là phần nội bộ theo quy ước, nên module khác không nên phụ thuộc vào nó. Vì vậy, một kiểu \`public\` trong \`order.internal\` có thể hợp lệ với trình biên dịch Java nhưng vẫn vi phạm ranh giới module khi được module khác sử dụng.

Muốn kiểm soát phụ thuộc, nhóm cần cả cấu trúc package rõ ràng và bước kiểm chứng kiến trúc.

## 8. Kiểm chứng ranh giới được suy ra từ package

Có thể yêu cầu Spring Modulith xây dựng mô hình từ lớp ứng dụng và xác minh các quy tắc kiến trúc:

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

Kiểm tra này giúp phát hiện những vấn đề như module tham chiếu đến package nội bộ của module khác hoặc tạo ra phụ thuộc không phù hợp với quy tắc được khai báo.

Có thể thêm annotation \`@ApplicationModule\` trong \`package-info.java\` của package module khi cần mô tả metadata hoặc giới hạn phụ thuộc được phép. Ví dụ:

~~~java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = {"inventory", "customer"}
)
package com.acme.shop.order;
~~~

Danh sách trên minh họa module order được phép phụ thuộc vào API mặc định của inventory và customer. Tên module phải khớp với module được khám phá từ cấu trúc package.

Nên chạy kiểm tra kiến trúc trong bộ test thường xuyên và CI. Khi package được di chuyển hoặc thêm mới, kiểm tra giúp phát hiện liệu thay đổi có làm biến dạng ranh giới module đã định hay không.

## 9. Quy trình thiết kế package base để có ranh giới logic rõ ràng

Khi bắt đầu một ứng dụng hoặc tổ chức lại package hiện có, có thể đi theo các bước sau:

1. **Chọn application base package.** Đặt lớp \`@SpringBootApplication\` trong package gốc bao trùm mã nguồn của ứng dụng.
2. **Nhận diện capability nghiệp vụ.** Xác định các khu vực trách nhiệm như order, inventory, customer và payment.
3. **Đặt capability thành package con trực tiếp.** Dùng các package đó làm module base package để Spring Modulith khám phá.
4. **Tổ chức phần bên trong module.** Đặt web, application, domain, persistence hoặc integration thành package con khi cần.
5. **Xác định API công khai.** Giữ hợp đồng mặc định ở package gốc module; dùng named interface cho nhóm hợp đồng con cần công khai.
6. **Kiểm soát phụ thuộc.** Đảm bảo module khác chỉ sử dụng API được công khai và tuân thủ các quy tắc phụ thuộc.
7. **Kiểm chứng tự động.** Dùng \`ApplicationModules.verify()\` trong test để phát hiện vi phạm khi cấu trúc thay đổi.

Nếu phát hiện package cấp cao đang là controller, service hoặc repository, hãy xem lại package gốc và vị trí các capability. Di chuyển package nên đi kèm kiểm tra import, component scanning, cấu hình và các bài test liên quan để ứng dụng vẫn hoạt động đúng.

## Ghi nhớ

Spring Modulith suy ra ranh giới application module mặc định từ **package con trực tiếp của application base package**. Package con trực tiếp trở thành module cấp cao; các package lồng bên trong thuộc cấu trúc của module đó. Package gốc của module cũng là API mặc định, trong khi package con được giữ nội bộ trừ khi công khai bằng named interface.

Vì vậy, hãy đặt các capability nghiệp vụ như order, inventory, customer và payment ngay dưới package gốc ứng dụng. Cấu trúc package khi ấy vừa thể hiện ranh giới logic, vừa tạo nền tảng để Spring Modulith khám phá module, kiểm soát API và kiểm chứng phụ thuộc trong một modular monolith.
