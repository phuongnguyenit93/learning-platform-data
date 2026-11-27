# Vì sao package phẳng làm boundary khó nhìn?

Một ứng dụng Spring Boot có thể biên dịch và chạy tốt dù hàng trăm lớp nằm trong một package hoặc được chia theo các tầng kỹ thuật như `controller`, `service`, `repository`. Cách sắp xếp này giúp tìm một loại lớp quen thuộc, nhưng thường không cho biết năng lực nghiệp vụ nào sở hữu lớp đó, API nào được phép dùng từ bên ngoài và phần triển khai nào cần được giữ kín.

Đây là vấn đề của ranh giới kiến trúc. Spring Modulith nhận diện application module từ cấu trúc package và kiểm tra quan hệ phụ thuộc giữa chúng. Vì vậy, cách tổ chức package ảnh hưởng trực tiếp đến việc mô hình mô-đun có phản ánh đúng nghiệp vụ hay không. Với modular monolith, tổ chức theo năng lực nghiệp vụ thường giúp nhìn thấy boundary rõ hơn tổ chức toàn bộ ứng dụng theo tầng kỹ thuật.

## 1. Package phẳng che khuất quyền sở hữu nghiệp vụ

Hãy hình dung ứng dụng bán hàng có các năng lực `order`, `inventory` và `customer`. Khi tất cả lớp nằm trong cùng một package, cấu trúc có thể trông như sau:

```text
com.acme.shop
├── ShopApplication.java
├── OrderController.java
├── OrderService.java
├── OrderRepository.java
├── InventoryController.java
├── InventoryService.java
├── StockRepository.java
├── CustomerController.java
├── CustomerService.java
└── CustomerRepository.java
```

Nhìn tên lớp, người đọc có thể đoán một phần trách nhiệm, nhưng package không thể hiện rõ ba nhóm nghiệp vụ. Khi cần thay đổi quy tắc tạo đơn hàng, nhà phát triển phải lần theo tên lớp và các lời gọi để tìm tất cả thành phần liên quan. Khi cần đánh giá một phụ thuộc, cấu trúc cũng không cho biết `OrderService` đang sử dụng một API được công bố của `inventory` hay đang truy cập thẳng vào chi tiết lưu trữ của nó.

Package phẳng thường dẫn đến một số hệ quả:

- **Khó xác định chủ sở hữu:** một lớp thuộc nghiệp vụ nào phải được suy ra từ tên, nội dung hoặc lịch sử dự án.
- **API dễ bị mở rộng vô tình:** các lớp nghiệp vụ và lớp triển khai nằm cạnh nhau, nên ranh giới giữa hợp đồng và chi tiết nội bộ không rõ.
- **Phụ thuộc khó kiểm soát:** code của một năng lực có thể gọi bất kỳ lớp nào khác mà không có cấu trúc package giúp cảnh báo.
- **Thay đổi khó khoanh vùng:** một thay đổi nghiệp vụ thường kéo theo chỉnh sửa ở nhiều vị trí phân tán.

Vấn đề không nằm ở số lượng package ít hay nhiều. Vấn đề là cấu trúc không cho thấy mỗi năng lực nghiệp vụ sở hữu những gì và cho phép phần còn lại của ứng dụng sử dụng những gì.

## 2. Chia package theo tầng kỹ thuật vẫn có thể làm boundary khó nhìn

Một bước tổ chức phổ biến là chuyển các lớp vào package theo vai trò kỹ thuật:

```text
com.acme.shop
├── ShopApplication.java
├── controller
│   ├── OrderController.java
│   ├── InventoryController.java
│   └── CustomerController.java
├── service
│   ├── OrderService.java
│   ├── InventoryService.java
│   └── CustomerService.java
└── repository
    ├── OrderRepository.java
    ├── StockRepository.java
    └── CustomerRepository.java
```

Cấu trúc này dễ tìm controller, service hoặc repository. Tuy nhiên, code của từng năng lực nghiệp vụ lại bị chia ra nhiều package. Muốn hiểu trọn vẹn `order`, người đọc phải ghép `OrderController` từ `controller`, `OrderService` từ `service` và `OrderRepository` từ `repository`.

Điều này còn có ý nghĩa cụ thể với cách Spring Modulith phát hiện module mặc định. Mỗi package con trực tiếp của package chứa lớp ứng dụng là một ứng viên application module. Với cấu trúc trên, các package `controller`, `service` và `repository` có thể được nhận diện như những module riêng. Chúng là các nhóm kỹ thuật, không phải các năng lực nghiệp vụ mà ứng dụng cần mô hình hóa.

Khi đó, dependency graph có nguy cơ phản ánh quan hệ giữa tầng kỹ thuật thay vì quan hệ giữa các capability. Ví dụ, `controller` cần gọi `service`, `service` cần dùng `repository`; các module này trở thành những đơn vị phụ thuộc xuyên suốt mọi nghiệp vụ. Ranh giới `order`, `inventory` và `customer` vẫn chưa được thể hiện.

Chia package theo tầng có thể phù hợp với một số ứng dụng nhỏ hoặc quy ước tổ chức code khác. Nhưng nếu mục tiêu là kiểm soát boundary theo application module của Spring Modulith, các package cấp module nên đại diện cho phần chức năng mà nhóm muốn đóng gói.

## 3. Spring Modulith dùng cấu trúc package để nhận diện module

Giả sử lớp khởi chạy nằm trong package `com.acme.shop`:

```java
package com.acme.shop;

import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ShopApplication {
}
```

Theo quy tắc phát hiện mặc định, các package con trực tiếp bên dưới package ứng dụng được xem là application module. Những package sâu hơn thuộc về module cha theo cấu trúc package, trừ khi ứng dụng khai báo một cấu trúc mô-đun lồng nhau.

Ví dụ, nếu có `com.acme.shop.order`, `com.acme.shop.inventory` và `com.acme.shop.customer`, Spring Modulith có thể nhận diện ba module tương ứng. `com.acme.shop.order.internal` là package con của module `order`, không tự động trở thành module ngang hàng với `order`.

Điểm này giải thích tại sao cấu trúc package không chỉ là cách đặt file. Nó là đầu vào để Spring Modulith xây dựng mô hình module, xác định package API mặc định và phân tích phụ thuộc.

Nếu tất cả lớp nằm trực tiếp trong `com.acme.shop`, không có package con theo từng năng lực để tạo ra các boundary module mặc định. Nếu package con là các tầng kỹ thuật, framework sẽ nhìn thấy các package kỹ thuật đó như các đơn vị cấp module. Trong cả hai trường hợp, cấu trúc không diễn đạt được các capability mà nhóm muốn đóng gói.

## 4. Tổ chức theo năng lực nghiệp vụ (package by feature)

Với modular monolith, cách tổ chức thường dễ hiểu hơn là đặt tất cả thành phần của một năng lực vào cùng một module:

```text
com.acme.shop
├── ShopApplication.java
├── order
│   ├── OrderManagement.java
│   ├── OrderId.java
│   ├── PlaceOrder.java
│   └── internal
│       ├── OrderController.java
│       ├── PlaceOrderService.java
│       └── OrderRepository.java
├── inventory
│   ├── InventoryManagement.java
│   └── internal
│       ├── InventoryController.java
│       ├── InventoryService.java
│       └── StockRepository.java
└── customer
    ├── CustomerManagement.java
    └── internal
        ├── CustomerController.java
        ├── CustomerService.java
        └── CustomerRepository.java
```

Giờ đây, mọi thành phần liên quan đến `order` đều nằm trong phạm vi module `order`, dù chúng đảm nhiệm vai trò controller, service hay repository. Người đọc có thể bắt đầu từ package `order` để hiểu năng lực tạo đơn hàng, thay vì tìm kiếm qua các tầng kỹ thuật của toàn ứng dụng.

Trong module đóng mặc định, package gốc như `com.acme.shop.order` là API package. Các type được công bố tại đây là điểm truy cập mà module khác có thể sử dụng. Các package con như `order.internal` chứa phần triển khai nội bộ. Nếu một package con cần được công bố có chủ đích, có thể khai báo Named Interface.

Ví dụ API của `order`:

```java
package com.acme.shop.order;

public interface OrderManagement {

    OrderId placeOrder(PlaceOrder command);
}
```

Phần triển khai ở package nội bộ:

```java
package com.acme.shop.order.internal;

import com.acme.shop.order.OrderId;
import com.acme.shop.order.OrderManagement;
import com.acme.shop.order.PlaceOrder;
import org.springframework.stereotype.Service;

@Service
class PlaceOrderService implements OrderManagement {

    private final OrderRepository orders;

    PlaceOrderService(OrderRepository orders) {
        this.orders = orders;
    }

    @Override
    public OrderId placeOrder(PlaceOrder command) {
        // Thực hiện quy trình tạo và lưu đơn hàng.
        return OrderId.newId();
    }
}
```

Ví dụ lược bỏ chi tiết domain để làm rõ vị trí của hợp đồng và triển khai. `OrderManagement` là API mà module khác có thể phụ thuộc; `PlaceOrderService` và `OrderRepository` thuộc phần nội bộ của `order`.

## 5. Boundary rõ hơn giúp kiểm soát API và dependency

Khi mỗi module đại diện cho một năng lực nghiệp vụ, ta có thể diễn đạt các quy tắc kiến trúc bằng code.

Một module khác có thể gọi API công khai:

```java
import com.acme.shop.order.OrderManagement;
```

Nó không nên import chi tiết nội bộ:

```java
// Vi phạm boundary của module đóng mặc định.
import com.acme.shop.order.internal.OrderRepository;
```

Java có thể vẫn cho phép import một lớp `public` ở package con. Vì vậy, compiler không đủ để thực thi mọi quy tắc boundary. Spring Modulith cung cấp kiểm tra kiến trúc để phát hiện việc module khác truy cập package nội bộ.

Lưu ý rằng package con cũng là một Java package riêng. Quyền truy cập package-private của Java chỉ áp dụng trong đúng package, không tự mở rộng sang package con như `order.internal`. Vì vậy, một lớp nội bộ có thể cần khai báo `public` để các thành phần ở package khác trong cùng module sử dụng. `public` ở đây phục vụ khả năng truy cập của Java; Spring Modulith vẫn có thể kiểm tra và ngăn module bên ngoài phụ thuộc vào package nội bộ đó.

Nếu `shipping` cần dùng một event được `order` công bố trong package `order.events`, hãy khai báo package đó là Named Interface:

```java
@org.springframework.modulith.NamedInterface("events")
package com.acme.shop.order.events;
```

Sau đó, module `shipping` có thể giới hạn phụ thuộc đến giao diện đó:

```java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "order :: events"
)
package com.acme.shop.shipping;
```

Khai báo này làm cho hợp đồng tích hợp được thể hiện rõ. `shipping` có thể sử dụng event được công bố mà không cần truy cập repository hoặc service nội bộ của `order`.

## 6. Cấu trúc package làm dependency graph dễ đọc hơn

Một trong những giá trị của Spring Modulith là khả năng phân tích các phụ thuộc giữa module. Khi package phản ánh capability, dependency graph thường gần với cách nhóm hiểu về nghiệp vụ hơn.

Ví dụ:

```text
order -------> inventory
  |
  +----------> customer

shipping ----> order :: events
```

Sơ đồ minh họa các hợp đồng phụ thuộc ở mức khái niệm. `order` có thể gọi API của `inventory` và `customer` trong luồng tạo đơn. `shipping` nhận event từ Named Interface `order :: events` để chuẩn bị giao hàng. Những module này không cần biết các repository nội bộ của nhau.

Khi package bị chia theo tầng kỹ thuật, đồ thị có thể trông như `controller -> service -> repository`. Cách nhìn đó hữu ích để hiểu luồng gọi kỹ thuật, nhưng không cho biết module nghiệp vụ nào phụ thuộc vào module nào. Nó cũng dễ tạo ra những module cấp cao mà mọi nghiệp vụ đều phải đi qua.

Boundary theo capability giúp nhóm đặt câu hỏi cụ thể hơn:

- `order` có thực sự cần API nào từ `inventory`?
- `shipping` có cần gọi trực tiếp `order` hay chỉ cần nhận `OrderPlaced`?
- Có module nào đang phụ thuộc ngược lại vào `order` khiến đồ thị tạo chu trình không?
- Một thay đổi trong `customer` có làm lộ chi tiết nội bộ sang `order` không?

Những câu hỏi này hỗ trợ kiểm soát coupling và ngăn cấu trúc modular monolith suy giảm theo thời gian.

## 7. Kiểm chứng boundary bằng ApplicationModules

Sau khi tổ chức package theo capability, hãy đưa kiểm tra kiến trúc vào test:

```java
package com.acme.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void verifiesModuleBoundaries() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
```

`verify()` kiểm tra các quy tắc kiến trúc mà mô hình hỗ trợ, bao gồm chu trình phụ thuộc và việc truy cập package nội bộ của module khác. Nếu ứng dụng khai báo `allowedDependencies`, các phụ thuộc cũng được đối chiếu với danh sách cho phép.

Kiểm tra này hữu ích nhất khi được chạy thường xuyên trong test suite hoặc CI. Khi ai đó thêm một import từ `order.internal` vào `shipping`, bài test có thể phát hiện vi phạm ngay trong quá trình phát triển.

Việc đổi cấu trúc package không tự động làm cho thiết kế tốt. Nếu nhóm gom các lớp không liên quan vào cùng một package `order`, hoặc công bố mọi package con thành Named Interface, boundary vẫn khó duy trì. `verify()` giúp thực thi quy tắc kỹ thuật, còn việc chọn capability và hợp đồng API vẫn cần quyết định kiến trúc có chủ đích.

## 8. Chuyển từ package phẳng sang package theo feature

Không cần di chuyển toàn bộ code trong một lần. Có thể tổ chức lại theo từng năng lực nghiệp vụ:

1. **Chọn một capability:** bắt đầu với phần có trách nhiệm rõ như `order` hoặc `inventory`.
2. **Tập hợp code liên quan:** chuyển controller, service, repository và domain type của capability vào package module tương ứng.
3. **Xác định API:** đưa các hợp đồng mà module khác thực sự cần dùng vào package gốc của module.
4. **Đóng gói triển khai:** chuyển chi tiết nội bộ vào package con như `internal`.
5. **Công bố hợp đồng bổ sung khi cần:** dùng Named Interface cho event hoặc SPI có người tiêu thụ cụ thể.
6. **Sửa các điểm phụ thuộc:** thay import đến lớp nội bộ bằng lời gọi API hoặc giao tiếp qua event phù hợp.
7. **Thêm kiểm tra kiến trúc:** chạy `ApplicationModules.verify()` để giữ boundary sau khi tái cấu trúc.

Sau mỗi capability, hãy kiểm tra lại package tree và dependency graph. Cách làm theo từng bước giúp phát hiện sớm những lớp đang phục vụ nhiều nghiệp vụ hoặc những API chưa được xác định rõ.

## 9. Những nhầm lẫn thường gặp

| Nhận định | Cách hiểu chính xác |
| --- | --- |
| Càng ít package thì code càng đơn giản. | Ít package có thể làm mất dấu ownership và API boundary khi ứng dụng lớn lên. |
| Chia thành `controller`, `service`, `repository` là đã có modular monolith. | Đó là tổ chức theo tầng kỹ thuật; package cấp module nên phản ánh capability nếu muốn mô hình hóa module nghiệp vụ. |
| Mỗi package con luôn là một application module. | Theo mặc định, các package con trực tiếp của application root là module; package sâu hơn thường thuộc module cha. |
| Đặt một lớp vào package `internal` là compiler sẽ cấm module khác truy cập. | Java có thể vẫn cho phép truy cập lớp `public`; cần dùng quy tắc và kiểm tra kiến trúc của Spring Modulith. |
| Mọi package con đều phải là nội bộ. | Có thể công bố một package con bằng Named Interface khi nó là hợp đồng cần thiết. |
| Chỉ cần đổi tên package là boundary đã tốt. | Cần xác định ownership, API công khai và các dependency được phép; cấu trúc chỉ là nền tảng để thể hiện các quyết định đó. |

## 10. Ghi nhớ

Package phẳng làm boundary khó nhìn vì các lớp của nhiều năng lực nghiệp vụ cùng nằm trong một phạm vi hoặc bị chia theo tầng kỹ thuật. Người đọc khó xác định module nào sở hữu một lớp, phần nào là API và phần nào chỉ là triển khai nội bộ. Trong Spring Modulith, vấn đề này còn ảnh hưởng đến cách framework nhận diện application module từ các package con trực tiếp của package ứng dụng.

Tổ chức theo feature đặt các thành phần liên quan của `order`, `inventory` hay `customer` vào từng module. Package gốc thể hiện API mặc định, package con chứa triển khai nội bộ, còn Named Interface công bố những hợp đồng bổ sung có chủ đích. Kết hợp cấu trúc đó với `ApplicationModules.verify()` giúp modular monolith có boundary dễ đọc, dễ kiểm tra và dễ duy trì.

## Tài liệu tham khảo

- [Spring Modulith Reference — Fundamentals](https://docs.spring.io/spring-modulith/reference/fundamentals.html)
- [Spring Modulith Reference — Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html)
