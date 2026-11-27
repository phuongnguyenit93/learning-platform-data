# SPI package và API package trong cùng module

Một Application Module có thể công bố API cho các module khác gọi và đồng thời cung cấp một SPI để module khác bổ sung cách triển khai. Hai loại hợp đồng này có thể cùng tồn tại trong một module vì chúng phục vụ hai hướng mở rộng khác nhau:

- **API package** chứa các hợp đồng mà module cung cấp để consumer sử dụng.
- **SPI package** chứa các hợp đồng mở rộng mà module sở hữu định nghĩa, còn module khác có thể triển khai.

Trong Spring Modulith, API package mặc định là package gốc của module. SPI thường được đặt trong một subpackage và công bố bằng **@NamedInterface**. Bài học này dùng một ví dụ module **orders** để cho thấy cách tổ chức hai hợp đồng, cách các module tiêu thụ khai báo phụ thuộc và cách Spring đưa implementation vào module sở hữu SPI.

## 1. API và SPI giải quyết hai nhu cầu khác nhau

Giả sử ứng dụng bán hàng có module **orders**. Module này cần công bố chức năng đặt hàng để **checkout** sử dụng. Đồng thời, **orders** muốn cho phép module **promotions** cung cấp chính sách điều chỉnh giá.

Hai hợp đồng có vai trò khác nhau:

| Hợp đồng | Ai định nghĩa? | Ai sử dụng? | Ai triển khai? |
|---|---|---|---|
| API **OrderManagement** | Module **orders** | Module **checkout** | Module **orders** |
| SPI **OrderPricingPolicy** | Module **orders** | Module **orders** | Module **promotions** |

API trả lời câu hỏi: “Module này cung cấp chức năng gì cho consumer?”

SPI trả lời câu hỏi: “Module này cho phép thành phần bên ngoài cung cấp hoặc thay thế hành vi nào?”

SPI vẫn là hợp đồng thuộc quyền sở hữu của module **orders**. Module **promotions** triển khai hợp đồng đó, nhưng không sở hữu định nghĩa của nó.

## 2. Tổ chức API package và SPI package trong cùng module

Một cấu trúc package có thể như sau:

~~~text
com.acme.shop
├── ShopApplication.java
├── orders
│   ├── OrderManagement.java
│   ├── spi
│   │   ├── package-info.java
│   │   └── OrderPricingPolicy.java
│   └── internal
│       └── DefaultOrderManagement.java
├── checkout
│   └── CheckoutFacade.java
└── promotions
    └── PromotionalPricingPolicy.java
~~~

Trong ví dụ:

- **com.acme.shop.orders** là base package của Application Module **orders**. Các type public ở đây thuộc API package mặc định (unnamed interface).
- **com.acme.shop.orders.spi** là subpackage của cùng module **orders**. Khi được khai báo Named Interface, type trong package này trở thành một phần API được công bố có tên **spi**.
- **com.acme.shop.orders.internal** chứa implementation nội bộ.
- **checkout** và **promotions** là các module tiêu thụ những hợp đồng khác nhau của **orders**.

**spi** không phải Application Module riêng. Nó là một Named Interface nằm bên trong module **orders**. Việc công bố SPI không làm thay đổi quyền sở hữu nghiệp vụ của module.

## 3. Khai báo API ở package gốc

Module **orders** công bố chức năng đặt hàng qua một interface trong base package:

~~~java
package com.acme.shop.orders;

import java.math.BigDecimal;

public interface OrderManagement {

    String placeOrder(String customerId, BigDecimal subtotal);
}
~~~

Đây là API mà module khác có thể sử dụng. Theo quy tắc mặc định, Spring Modulith xem package gốc của module là unnamed interface. Vì vậy, không cần tạo **@NamedInterface** cho package gốc.

Module **checkout** sử dụng API:

~~~java
package com.acme.shop.checkout;

import com.acme.shop.orders.OrderManagement;
import java.math.BigDecimal;
import org.springframework.stereotype.Service;

@Service
class CheckoutFacade {

    private final OrderManagement orderManagement;

    CheckoutFacade(OrderManagement orderManagement) {
        this.orderManagement = orderManagement;
    }

    String confirmCheckout(String customerId, BigDecimal subtotal) {
        return orderManagement.placeOrder(customerId, subtotal);
    }
}
~~~

**checkout** chỉ cần biết hợp đồng **OrderManagement**. Module này không cần biết class triển khai, repository hoặc cấu trúc dữ liệu nội bộ của **orders**.

## 4. Khai báo SPI trong Named Interface

Module **orders** định nghĩa điểm mở rộng để module khác cung cấp chính sách giá:

~~~java
package com.acme.shop.orders.spi;

import java.math.BigDecimal;

public interface OrderPricingPolicy {

    BigDecimal apply(String customerId, BigDecimal subtotal);
}
~~~

Để công bố package **com.acme.shop.orders.spi**, thêm annotation trong file **package-info.java**:

~~~java
@org.springframework.modulith.NamedInterface("spi")
package com.acme.shop.orders.spi;
~~~

Sau khai báo, **OrderPricingPolicy** là một type thuộc Named Interface **spi**. Module khác có thể tham chiếu type này nếu dependency rule của consumer cho phép.

Annotation **@NamedInterface("spi")** chỉ đánh dấu package là giao diện được công bố có tên. Nó không tự tìm implementation, không đăng ký Spring bean và không kích hoạt Java **ServiceLoader**. Việc tạo và lựa chọn bean vẫn do Spring hoặc cơ chế mở rộng do ứng dụng thiết kế đảm nhiệm.

## 5. Module sở hữu sử dụng SPI của chính nó

Implementation nội bộ của **orders** có thể inject **OrderPricingPolicy** để thực hiện use case:

~~~java
package com.acme.shop.orders.internal;

import com.acme.shop.orders.OrderManagement;
import com.acme.shop.orders.spi.OrderPricingPolicy;
import java.math.BigDecimal;
import org.springframework.stereotype.Service;

@Service
class DefaultOrderManagement implements OrderManagement {

    private final OrderPricingPolicy pricingPolicy;

    DefaultOrderManagement(OrderPricingPolicy pricingPolicy) {
        this.pricingPolicy = pricingPolicy;
    }

    @Override
    public String placeOrder(String customerId, BigDecimal subtotal) {
        BigDecimal finalPrice = pricingPolicy.apply(customerId, subtotal);
        // Lưu đơn hàng với finalPrice trong phần triển khai thực tế.
        return "order-" + customerId;
    }
}
~~~

Ở đây, **DefaultOrderManagement** thuộc module **orders** và tham chiếu SPI cũng thuộc module **orders**. Đây là quan hệ nội bộ trong cùng module. **orders** không cần import class **PromotionalPricingPolicy** hoặc biết module nào cung cấp implementation.

## 6. Module khác triển khai SPI

Module **promotions** cung cấp implementation cho **OrderPricingPolicy**:

~~~java
package com.acme.shop.promotions;

import com.acme.shop.orders.spi.OrderPricingPolicy;
import java.math.BigDecimal;
import org.springframework.stereotype.Component;

@Component
class PromotionalPricingPolicy implements OrderPricingPolicy {

    @Override
    public BigDecimal apply(String customerId, BigDecimal subtotal) {
        return subtotal.multiply(new BigDecimal("0.90"));
    }
}
~~~

Class này thuộc module **promotions**, nhưng triển khai interface do **orders** sở hữu. Vì mã nguồn **promotions** import **OrderPricingPolicy**, dependency graph có cạnh từ **promotions** đến Named Interface **orders :: spi**.

Khi ứng dụng khởi động, Spring cần phát hiện bean **PromotionalPricingPolicy** trong component scan và inject bean đó vào **DefaultOrderManagement**. Nếu không có bean phù hợp, ứng dụng sẽ không tạo được service cần SPI. Nếu có nhiều implementation, cần thiết kế cách chọn rõ ràng, chẳng hạn dùng **@Primary**, **@Qualifier**, **@Order** hoặc inject danh sách provider và áp dụng quy tắc lựa chọn.

Điểm quan trọng là chiều phụ thuộc mã nguồn vẫn đi từ module triển khai SPI đến module định nghĩa SPI. Việc Spring inject implementation lúc chạy không có nghĩa **orders** phải phụ thuộc mã nguồn vào module **promotions**.

## 7. Khai báo allowedDependencies riêng cho từng consumer

**checkout** sử dụng API package mặc định của **orders**, nên khai báo ở package gốc của **checkout**:

~~~java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "orders"
)
package com.acme.shop.checkout;
~~~

**promotions** triển khai type thuộc Named Interface **spi**, nên khai báo:

~~~java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "orders :: spi"
)
package com.acme.shop.promotions;
~~~

Hai module tiêu thụ có quyền phụ thuộc khác nhau:

| Module tiêu thụ | Hợp đồng cần dùng | Khai báo |
|---|---|---|
| **checkout** | API package mặc định | **"orders"** |
| **promotions** | Named Interface **spi** | **"orders :: spi"** |

Nếu một consumer cần cả API mặc định và SPI, có thể khai báo cả hai:

~~~java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = { "orders", "orders :: spi" }
)
package com.acme.shop.someconsumer;
~~~

**allowedDependencies** được khai báo ở module tiêu thụ vì nó mô tả outgoing dependencies mà module đó được phép có. Khai báo này không làm package nội bộ của **orders** trở thành API.

## 8. Dependency graph và luồng injection lúc chạy

Với ví dụ trên, dependency graph ở mức mã nguồn có thể biểu diễn như sau:

~~~text
checkout ───────────────> orders (API package)

promotions ─────────────> orders :: spi

orders.internal ────────> orders.spi
       (cùng một module)
~~~

Khi ứng dụng chạy, Spring tạo các bean và kết nối chúng:

~~~text
CheckoutFacade
      |
      v
OrderManagement
      |
      v
DefaultOrderManagement
      |
      v
OrderPricingPolicy <──── PromotionalPricingPolicy
~~~

Sơ đồ thứ nhất mô tả phụ thuộc type giữa các module. Sơ đồ thứ hai mô tả kết nối bean lúc chạy. Hai góc nhìn có liên quan nhưng không đồng nhất: bean implementation có thể được inject vào module sở hữu SPI mà không tạo import từ module sở hữu sang module triển khai.

## 9. Khi nào nên dùng API package và SPI package?

| Nhu cầu | Cách tổ chức phù hợp |
|---|---|
| Module khác gọi chức năng nghiệp vụ ổn định | API package mặc định |
| Module khác cung cấp implementation cho một điểm mở rộng | Named Interface **spi** |
| Nhiều module cần lắng nghe event nghiệp vụ | Named Interface **events** |
| Type chỉ phục vụ implementation của module | Subpackage nội bộ như **internal** |
| Consumer cần cả chức năng và điểm mở rộng | Cho phép cả API package và Named Interface tương ứng |

Không phải module nào cũng cần SPI. Nếu module không có nhu cầu nhận implementation từ bên ngoài, không cần tạo package **spi** chỉ để làm cấu trúc trông đồng đều. Một SPI được công bố là hợp đồng mà module phải duy trì; chỉ nên tạo khi có điểm mở rộng thực sự.

## 10. Những lỗi thiết kế thường gặp

**Đặt SPI trong package gốc cùng API mà không phân biệt mục đích.** Khi API gọi từ consumer và SPI dành cho provider bị trộn lẫn, người đọc khó nhận ra ai gọi và ai triển khai hợp đồng. Có thể tách SPI vào subpackage có Named Interface riêng.

**Tưởng tên spi tự động làm package được expose.** Tên package chỉ là quy ước. Cần khai báo **@NamedInterface("spi")** để công bố subpackage.

**Cho consumer quyền truy cập toàn bộ module dù chỉ cần SPI.** Nếu **promotions** chỉ triển khai **OrderPricingPolicy**, hãy giới hạn bằng **orders :: spi**. Điều này giúp bề mặt phụ thuộc của consumer rõ ràng.

**Để module sở hữu SPI import implementation cụ thể.** Khi **orders** import **PromotionalPricingPolicy**, hướng phụ thuộc bị đảo ngược và module nghiệp vụ bị gắn với provider. Hãy để **orders** phụ thuộc vào interface của chính nó và để Spring inject implementation.

**Nhầm Named Interface với plugin loader.** **@NamedInterface** công bố hợp đồng kiến trúc. Nó không tự đăng ký provider hoặc chọn implementation. Hãy cấu hình Spring bean và chiến lược lựa chọn riêng.

**Công bố SPI không có consumer hoặc provider.** Một interface chưa có nhu cầu mở rộng thực tế làm tăng bề mặt API và chi phí bảo trì. Hãy bắt đầu từ use case và chỉ tạo SPI khi có lý do rõ ràng.

## 11. Kiểm chứng ranh giới module

Có thể kiểm tra dependency rule bằng bài test kiến trúc:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void verifiesModuleBoundaries() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

Kiểm chứng này giúp phát hiện:

1. **checkout** truy cập type nội bộ của **orders** thay vì API package được công bố.
2. **promotions** truy cập package **orders.spi** khi chưa khai báo Named Interface hoặc dependency rule phù hợp.
3. Consumer tạo dependency ngoài danh sách **allowedDependencies**.
4. Các chu trình phụ thuộc giữa Application Module.

Test kiến trúc kiểm tra ranh giới module, còn việc Spring có tạo được bean provider hay không cần được xác nhận bằng context test hoặc integration test phù hợp. Hai loại kiểm tra bảo vệ hai vấn đề khác nhau: quyền phụ thuộc ở mức kiến trúc và khả năng kết nối implementation lúc chạy.

## Tài liệu tham khảo

- [Spring Modulith Reference — Fundamentals](https://docs.spring.io/spring-modulith/reference/fundamentals.html): API package mặc định, Named Interface và Application Module.
- [Spring Modulith Reference — Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html): kiểm tra dependency rule và ranh giới module.
- [Spring Modulith Javadoc — NamedInterface](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/NamedInterface.html): khai báo Named Interface cho package.
