# Tránh component scan phá vỡ ý định đóng gói

Trong Spring Boot, component scan tìm các lớp được đánh dấu bằng `@Component`, `@Service`, `@Repository`, `@Controller` và các stereotype liên quan để đăng ký chúng thành Spring bean. Trong Spring Modulith, package lại thể hiện ranh giới của application module: package gốc chứa API được công bố, còn các package con thường chứa phần triển khai nội bộ.

Hai cơ chế này phục vụ hai mục đích khác nhau. Component scan quyết định bean nào được đăng ký trong `ApplicationContext`; mô hình module của Spring Modulith xác định phần mã nào được phép tham chiếu từ module khác. Nếu cấu hình scan quá rộng hoặc dùng tra cứu bean để gọi trực tiếp thành phần nội bộ, ứng dụng có thể chạy được nhưng tạo ra các quan hệ runtime đi ngược ý định đóng gói.

Trong `SPRING_MODULITH_MODULE_MODEL`, tổ chức package theo nghiệp vụ chỉ có giá trị khi cách cấu hình Spring cũng tôn trọng ranh giới đó. Bài học này hướng dẫn đặt component scan đúng vị trí, phân biệt bean discovery với module encapsulation và giữ giao tiếp liên module qua API được công bố.

## 1. Component scan và application module giải quyết hai việc khác nhau

`@SpringBootApplication` bao gồm ba khả năng chính: cấu hình Spring Boot, bật auto-configuration và kích hoạt component scan. Mặc định, component scan bắt đầu từ package chứa lớp ứng dụng và đi xuống các package con.

Spring Modulith cũng dùng package của lớp ứng dụng làm điểm xuất phát để xây dựng mô hình module. Theo quy ước mặc định, mỗi package con trực tiếp của package gốc là một application module. Package gốc của module là bề mặt API mặc định; các package con như `internal` được xem là phần nội bộ.

Ví dụ:

```text
com.example.shop
├── ShopApplication.java
├── inventory
│   ├── InventoryAvailability.java
│   └── internal
│       ├── DefaultInventoryAvailability.java
│       └── InventoryRepository.java
└── order
    └── internal
        └── PlaceOrderService.java
```

Trong cấu trúc này:

- Component scan bắt đầu ở `com.example.shop` có thể tìm các bean thuộc cả `inventory` và `order`, bao gồm cả các bean nằm trong package `internal`.
- Spring Modulith nhận diện `inventory` và `order` là hai module riêng.
- Module `order` chỉ được tham chiếu API được công bố của `inventory`; các kiểu trong `inventory.internal` vẫn là nội bộ theo mô hình module.

Việc một lớp nội bộ được đăng ký làm Spring bean không tự động biến lớp đó thành API công khai của module. Tuy nhiên, nếu module khác truy cập bean nội bộ qua tên bean, `ApplicationContext` hoặc một kiểu triển khai nội bộ, ranh giới kiến trúc có thể bị phá vỡ ở thời điểm chạy.

## 2. Đặt lớp ứng dụng ở package gốc

Một cách tổ chức đơn giản và dễ kiểm soát là đặt lớp khởi chạy ở package gốc chung của ứng dụng:

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

Với vị trí này, component scan mặc định bao phủ các module con trong `com.example.shop`. Các module có thể đặt bean của mình ở package gốc hoặc các package con phù hợp mà không cần khai báo một `@ComponentScan` riêng cho từng module.

Tránh đặt lớp ứng dụng quá sâu, ví dụ `com.example.shop.bootstrap`, trong khi `inventory` và `order` lại là các package ngang hàng bên ngoài `bootstrap`. Component scan mặc định từ `bootstrap` sẽ không đi ngược lên để tìm các package anh em. Một cách sửa vội thường gặp là mở rộng scan lên `com.example`; điều đó có thể kéo theo các package không thuộc ứng dụng hoặc các thành phần không nên được đăng ký trong context.

Nếu cấu trúc hiện tại buộc phải đặt lớp ứng dụng ở package khác, hãy xác định rõ các package cần scan và kiểm tra chúng có thực sự thuộc phạm vi ứng dụng hay không.

## 3. Cấu hình scan quá rộng có thể tạo ra điều gì?

Giả sử package gốc của ứng dụng là `com.example.shop`, nhưng lớp ứng dụng khai báo:

```java
@SpringBootApplication(scanBasePackages = "com.example")
public class ShopApplication {
}
```

Thiết lập này mở rộng component scan lên `com.example`, bao gồm mọi package con bên dưới, không chỉ các module của cửa hàng. Những component ở package hỗ trợ, ứng dụng khác hoặc thư viện nội bộ cùng namespace cũng có thể được đăng ký ngoài dự kiến.

Một cấu hình scan đặt trong module cũng có thể vô tình kéo component của module khác vào phạm vi cấu hình riêng:

```java
package com.example.shop.order;

import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;

@Configuration
@ComponentScan("com.example.shop.inventory.internal")
class OrderConfiguration {
}
```

`order` lúc này chủ động quét package triển khai nội bộ của `inventory`. Cấu hình này khiến `order` phụ thuộc vào cách `inventory` tổ chức component bên trong, và có thể tạo ra các bean trùng hoặc nhiều bean cùng thỏa mãn một điểm injection. Khi `inventory` đổi cấu trúc hoặc thay cách triển khai, cấu hình của `order` cũng có thể phải thay đổi.

Không nên dùng component scan để kéo implementation của module khác vào module hiện tại. Nếu cần một khả năng từ module khác, hãy phụ thuộc vào API của module đó và để module sở hữu tự đăng ký bean triển khai.

## 4. Giữ implementation nội bộ, công bố interface nghiệp vụ

Một mẫu tổ chức phổ biến là đặt interface được công bố trong package gốc module và đặt lớp triển khai trong package con `internal`.

Interface công khai của module `inventory`:

```java
package com.example.shop.inventory;

public interface InventoryAvailability {

    boolean hasAvailableStock(String sku, int quantity);
}
```

Lớp triển khai thuộc nội bộ module:

```java
package com.example.shop.inventory.internal;

import com.example.shop.inventory.InventoryAvailability;
import org.springframework.stereotype.Service;

@Service
class DefaultInventoryAvailability implements InventoryAvailability {

    private final InventoryRepository repository;

    DefaultInventoryAvailability(InventoryRepository repository) {
        this.repository = repository;
    }

    @Override
    public boolean hasAvailableStock(String sku, int quantity) {
        return repository.availableQuantity(sku) >= quantity;
    }
}
```

`DefaultInventoryAvailability` được Spring phát hiện và đăng ký bean nhờ component scan từ package gốc. Module `order` chỉ cần tham chiếu interface công khai:

```java
package com.example.shop.order.internal;

import com.example.shop.inventory.InventoryAvailability;
import org.springframework.stereotype.Service;

@Service
class PlaceOrderService {

    private final InventoryAvailability inventory;

    PlaceOrderService(InventoryAvailability inventory) {
        this.inventory = inventory;
    }

    void place(String sku, int quantity) {
        if (!inventory.hasAvailableStock(sku, quantity)) {
            throw new IllegalStateException("Insufficient stock");
        }

        // Tiếp tục xử lý đơn hàng.
    }
}
```

Spring inject implementation phù hợp cho interface `InventoryAvailability`. Về mặt mã nguồn, `order` chỉ phụ thuộc vào API công khai. Nó không cần import `DefaultInventoryAvailability` hoặc `InventoryRepository`.

Trong ví dụ, `InventoryRepository` được giả định là một bean nội bộ do module `inventory` đăng ký, chẳng hạn một Spring Data repository hoặc một repository triển khai riêng.

Trong cấu trúc có nhiều package con, một số kiểu nội bộ có thể cần modifier `public` để các lớp khác bên trong cùng module sử dụng. Spring Modulith kiểm tra quy tắc truy cập giữa các module, nên `public` ở cấp Java không đồng nghĩa với việc kiểu đó được phép dùng từ module khác.

## 5. Đặt cấu hình bean trong module sở hữu bean

Không phải bean nào cũng cần được đăng ký bằng stereotype. Một module có thể dùng `@Configuration` và `@Bean` để tạo implementation của API do chính module đó sở hữu:

Đây là một cách đăng ký thay thế cho việc gắn `@Service` trực tiếp lên `DefaultInventoryAvailability` ở ví dụ trước. Chọn một cách cho cùng một implementation để tránh đăng ký hai bean cùng cung cấp `InventoryAvailability`.

```java
package com.example.shop.inventory.internal;

import com.example.shop.inventory.InventoryAvailability;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class InventoryConfiguration {

    @Bean
    InventoryAvailability inventoryAvailability(InventoryRepository repository) {
        return new DefaultInventoryAvailability(repository);
    }
}
```

`InventoryConfiguration` nằm trong module `inventory` và chịu trách nhiệm tạo bean cho API của module. Module khác không cần import cấu hình nội bộ này. Component scan từ package ứng dụng sẽ tìm cấu hình và đăng ký bean.

Nếu cần dùng `@Import`, hãy import cấu hình có chủ đích thuộc phạm vi ứng dụng hoặc hợp đồng cấu hình được công bố. Tránh import trực tiếp một lớp cấu hình nội bộ của module khác, vì như vậy module tiêu thụ phải biết chi tiết tổ chức bên trong module cung cấp.

## 6. Tránh service locator và tra cứu bean nội bộ

Một cách khác có thể làm mờ ranh giới là dùng `ApplicationContext` để lấy bean theo tên:

```java
@Service
class PlaceOrderService {

    private final ApplicationContext context;

    PlaceOrderService(ApplicationContext context) {
        this.context = context;
    }

    void place(String sku) {
        Object service = context.getBean("defaultInventoryAvailability");
        // Gọi service lấy được bằng cơ chế tra cứu động.
    }
}
```

Cách này tạo phụ thuộc runtime ẩn trong chuỗi tên bean. Trình biên dịch không thể hiện rõ module `order` đang cần hợp đồng nào, và việc đổi tên bean hoặc thay implementation có thể làm luồng chạy lỗi. Việc tra cứu động cũng khiến việc đọc và kiểm tra quan hệ module khó hơn.

Hãy dùng constructor injection với interface công khai:

```java
PlaceOrderService(InventoryAvailability inventory) {
    this.inventory = inventory;
}
```

Nếu thực sự cần lựa chọn implementation theo runtime, hãy biểu diễn lựa chọn đó qua một abstraction hoặc registry có hợp đồng rõ ràng, đặt trong module sở hữu chức năng tương ứng. Không dùng `ApplicationContext` làm đường tắt để truy cập package nội bộ của module khác.

## 7. Phân biệt component scan với module detection

Component scan và module detection có thể bắt đầu từ cùng package gốc, nhưng chúng không phải một cơ chế:

| Cơ chế | Nhiệm vụ | Cấu hình tiêu biểu |
|---|---|---|
| Component scan | Tìm lớp Spring stereotype và đăng ký bean | `@ComponentScan`, `@SpringBootApplication(scanBasePackages = ...)` |
| Module detection | Xác định package nào tạo thành application module | Quy ước package mặc định, `@ApplicationModule`, `spring.modulith.detection-strategy`, `@Modulithic` |

Ví dụ, `@Modulithic(additionalPackages = "...")` yêu cầu Spring Modulith xem các package bổ sung như root package để phát hiện module. Thuộc tính này không thay thế `@ComponentScan` và không tự đăng ký các component thành Spring bean.

Ngược lại, thêm một package vào `scanBasePackages` chỉ mở rộng nơi Spring tìm component. Việc đó không tự biến package thành application module trong mô hình Spring Modulith.

Vì vậy, khi bean không được tạo, hãy kiểm tra component scan và cấu hình bean. Khi module không được nhận diện, hãy kiểm tra package gốc, module detection strategy và cấu trúc package. Không thay đổi một cơ chế để cố giải quyết vấn đề thuộc cơ chế còn lại.

## 8. Kiểm chứng ranh giới đóng gói

Nên kết hợp kiểm tra cấu trúc module và kiểm thử Spring context.

### Kiểm tra cấu trúc module

Spring Modulith có thể phân tích module và kiểm tra các tham chiếu trái với ranh giới đã khai báo:

```java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void verifiesModuleStructure() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
```

Kiểm tra này hữu ích để phát hiện module tham chiếu kiểu nội bộ của module khác hoặc vi phạm quy tắc dependency. Tuy nhiên, các package trong chuỗi cấu hình scan có thể được khai báo bằng tên dạng `String`; vì vậy không nên giả định rằng kiểm tra dependency tĩnh sẽ phát hiện mọi trường hợp quét bean quá rộng.

### Kiểm tra wiring qua API công khai

Một kiểm thử context có thể xác nhận bean API được tạo và inject thành công:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import com.example.shop.inventory.InventoryAvailability;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class ModuleWiringTests {

    @Autowired
    InventoryAvailability inventoryAvailability;

    @Test
    void exposesInventoryCapabilityThroughItsApi() {
        assertThat(inventoryAvailability).isNotNull();
    }
}
```

Ngoài ra, hãy rà soát mọi khai báo `@ComponentScan`, `scanBasePackages`, `@Import` và các lệnh `ApplicationContext.getBean(...)`. Xác nhận mỗi scan có phạm vi cần thiết và mỗi module tiêu thụ gọi qua hợp đồng được công bố.

## 9. Checklist cấu hình component scan

- [ ] Lớp `@SpringBootApplication` nằm ở package gốc chung của ứng dụng.
- [ ] Component scan mặc định bao phủ các module thuộc ứng dụng.
- [ ] Không mở rộng scan lên namespace cha rộng hơn nếu không có lý do cụ thể.
- [ ] Không đặt component scan trong một module để quét package nội bộ của module khác.
- [ ] Bean triển khai được đăng ký trong module sở hữu nó.
- [ ] Module tiêu thụ inject interface hoặc hợp đồng công khai bằng constructor.
- [ ] Không dùng bean name hoặc `ApplicationContext` để truy cập implementation nội bộ.
- [ ] Phân biệt cấu hình component scan với cấu hình module detection.
- [ ] Chạy `ApplicationModules.verify()` và kiểm thử Spring context.

## 10. Kết luận

Component scan là cơ chế đăng ký Spring bean; nó không thay thế và cũng không tự thay đổi ranh giới module do Spring Modulith xác định. Đặt lớp ứng dụng ở package gốc thường cho phép scan các module trong phạm vi ứng dụng. Các bean nội bộ vẫn có thể được đăng ký để module sở hữu sử dụng hoặc để triển khai API công khai.

Ý định đóng gói được giữ vững khi module khác chỉ tham chiếu hợp đồng công khai, còn implementation và cấu hình bean được quản lý trong module sở hữu. Hãy tránh scan quá rộng, scan package nội bộ từ module tiêu thụ và tra cứu bean bằng tên. Kết hợp `ApplicationModules.verify()` với kiểm thử context để kiểm tra cả cấu trúc kiến trúc lẫn wiring khi chạy.

## Tài liệu tham khảo

- [Spring Boot — Using the `@SpringBootApplication` Annotation](https://docs.spring.io/spring-boot/reference/using/using-the-springbootapplication-annotation.html)
- [Spring Boot — Structuring Your Code](https://docs.spring.io/spring-boot/reference/using/structuring-your-code.html)
- [Spring Framework — Classpath Scanning and Managed Components](https://docs.spring.io/spring-framework/reference/core/beans/classpath-scanning.html)
- [Spring Modulith — Fundamentals](https://docs.spring.io/spring-modulith/reference/fundamentals.html)
