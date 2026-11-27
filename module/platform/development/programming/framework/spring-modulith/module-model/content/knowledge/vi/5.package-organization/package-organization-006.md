# internal, spi và các package có ý nghĩa khác nhau

Tên package là một phần của thiết kế kiến trúc. Khi đọc một module Spring Modulith, tên như **internal**, **spi**, **events**, **persistence** hay **web** giúp người đọc hiểu vai trò của các class và hướng phụ thuộc dự kiến. Tuy nhiên, tên package chỉ là quy ước tổ chức mã nguồn. Spring Modulith xác định API công khai dựa trên cấu trúc module và khai báo Named Interface, không tự động biến một package thành API chỉ vì tên của nó.

Bài học này trình bày cách tổ chức package bên trong Application Module, ý nghĩa thường dùng của các tên package, cách công bố có chủ đích bằng **@NamedInterface** và cách kiểm chứng ranh giới bằng **ApplicationModules.verify()**.

## 1. Bắt đầu từ ranh giới module

Giả sử ứng dụng có package gốc **com.acme.shop**. Các package con trực tiếp của package gốc biểu diễn những Application Module theo quy ước mặc định:

~~~text
com.acme.shop
├── ShopApplication.java
├── orders
├── inventory
└── customers
~~~

Trong đó **orders**, **inventory** và **customers** là các vùng nghiệp vụ độc lập. Bên trong mỗi module, ta tiếp tục tổ chức các package theo trách nhiệm:

~~~text
com.acme.shop
├── ShopApplication.java
├── orders
│   ├── OrderManagement.java
│   ├── internal
│   │   ├── DefaultOrderManagement.java
│   │   ├── Order.java
│   │   └── OrderRepository.java
│   ├── spi
│   │   ├── package-info.java
│   │   └── OrderPricingPolicy.java
│   ├── events
│   │   ├── package-info.java
│   │   └── OrderPlaced.java
│   └── web
│       └── OrderController.java
├── inventory
│   ├── InventoryReservation.java
│   └── internal
│       └── StockRepository.java
└── customers
    ├── CustomerDirectory.java
    └── internal
        └── CustomerRepository.java
~~~

Các điểm cần nhớ:

- **orders**, **inventory** và **customers** là các module nghiệp vụ.
- **orders.internal**, **orders.spi**, **orders.events** và **orders.web** là các package bên trong module **orders**.
- Theo mặc định, package gốc của module là API package không tên (unnamed interface); các subpackage là nội bộ cho đến khi được công bố rõ ràng.
- Việc đặt tên **internal** hay **spi** không tự thay đổi quyền truy cập kiến trúc.

Vì Spring Modulith nhận diện các package con trực tiếp của package ứng dụng làm module, không nên tạo các package tầng dùng chung ở ngay cấp đó như **com.acme.shop.controllers**, **com.acme.shop.services** và **com.acme.shop.repositories**. Cách tổ chức này dễ khiến các tầng kỹ thuật bị nhận diện như các module riêng. Hãy đặt package theo năng lực nghiệp vụ ở cấp module, rồi tổ chức vai trò kỹ thuật bên trong từng module.

## 2. Package internal: nơi giữ chi tiết triển khai

**internal** là tên quy ước phổ biến để gom các type chỉ phục vụ triển khai của module. Các thành phần thường đặt ở đây gồm:

- Service triển khai hợp đồng công khai.
- Repository, DAO và adapter truy cập cơ sở dữ liệu.
- Aggregate, entity và quy tắc nghiệp vụ chỉ dùng bên trong module.
- Mapper, helper và class điều phối nội bộ.
- Cấu hình kỹ thuật chỉ phục vụ module.

Ví dụ, module **orders** công bố một hợp đồng ở package gốc:

~~~java
package com.acme.shop.orders;

public interface OrderManagement {

    void placeOrder(String customerId);
}
~~~

Lớp triển khai nằm trong package **internal**:

~~~java
package com.acme.shop.orders.internal;

import com.acme.shop.orders.OrderManagement;
import org.springframework.stereotype.Service;

@Service
class DefaultOrderManagement implements OrderManagement {

    @Override
    public void placeOrder(String customerId) {
        // Kiểm tra đơn hàng, lưu dữ liệu và thực hiện nghiệp vụ.
    }
}
~~~

Module khác chỉ phụ thuộc vào **OrderManagement**. Nó không cần import **DefaultOrderManagement**, repository hoặc entity nội bộ. Nhờ constructor injection, Spring vẫn có thể tạo bean triển khai và cung cấp nó cho nơi tiêu thụ hợp đồng.

### internal có tự động được bảo vệ không?

Không. Tên **internal** tự nó không phải annotation và cũng không phải từ khóa của Java. Spring Modulith coi subpackage là nội bộ theo quy tắc mặc định của module đóng. Nếu một class trong package này được khai báo **public**, Java vẫn có thể cho phép mã nguồn khác import nó và biên dịch.

Ranh giới kiến trúc được kiểm tra bởi Spring Modulith. Nếu module khác tham chiếu type nội bộ, bài kiểm tra kiến trúc có thể phát hiện vi phạm khi chạy **ApplicationModules.verify()**. Vì vậy, hãy dùng tên **internal** nhất quán để truyền đạt ý định cho người đọc, đồng thời dùng kiểm chứng kiến trúc để bảo vệ ý định đó.

Không nên công bố package **internal** bằng Named Interface chỉ để giải quyết một import đang bị chặn. Nếu module khác cần một chức năng, hãy thiết kế một hợp đồng nghiệp vụ ổn định ở API package hoặc một Named Interface có mục đích rõ ràng.

## 3. Package spi: hợp đồng cho điểm mở rộng

**SPI** thường là viết tắt của *Service Provider Interface*. Tên này thường dùng cho các interface mà module cung cấp để một thành phần khác có thể triển khai, thay thế hoặc mở rộng hành vi.

Ví dụ, module **orders** cho phép một module khác cung cấp chính sách tính giá:

~~~java
package com.acme.shop.orders.spi;

public interface OrderPricingPolicy {

    java.math.BigDecimal calculate(
        String orderId,
        java.math.BigDecimal subtotal
    );
}
~~~

Để package **spi** trở thành Named Interface có tên **spi**, khai báo trong file **package-info.java**:

~~~java
@org.springframework.modulith.NamedInterface("spi")
package com.acme.shop.orders.spi;
~~~

Sau khai báo, module khác có thể tham chiếu các type được công bố trong Named Interface này nếu quy tắc phụ thuộc cho phép. Ví dụ, module **promotions** khai báo quyền phụ thuộc ở package gốc của nó:

~~~java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "orders :: spi"
)
package com.acme.shop.promotions;
~~~

Sau đó, một bean trong **promotions** có thể triển khai hợp đồng:

~~~java
package com.acme.shop.promotions;

import com.acme.shop.orders.spi.OrderPricingPolicy;
import java.math.BigDecimal;
import org.springframework.stereotype.Component;

@Component
class PromotionalPricingPolicy implements OrderPricingPolicy {

    @Override
    public BigDecimal calculate(String orderId, BigDecimal subtotal) {
        // Áp dụng chính sách giá của chương trình khuyến mại.
        return subtotal.multiply(new BigDecimal("0.90"));
    }
}
~~~

Ví dụ này thể hiện hướng phụ thuộc có chủ đích: **orders** định nghĩa hợp đồng mở rộng; **promotions** cung cấp một triển khai. Module **orders** có thể nhận các bean triển khai bằng Spring injection và áp dụng chúng trong quy trình tính giá. Module sở hữu hợp đồng không cần phụ thuộc vào module triển khai.

### SPI không đồng nghĩa với cơ chế tự nạp plugin

Trong Spring Modulith, **@NamedInterface("spi")** công bố package dưới tên giao diện **spi**. Annotation này không tự động tìm implementation, không đăng ký bean và cũng không kích hoạt cơ chế Java **ServiceLoader**. Việc tạo bean, chọn implementation và điều phối vòng đời vẫn do Spring hoặc cơ chế plugin mà ứng dụng thiết kế đảm nhiệm.

Chỉ nên dùng tên **spi** khi package thực sự chứa các hợp đồng dành cho điểm mở rộng hoặc nhà cung cấp triển khai. Nếu package chỉ chứa các API nghiệp vụ thông thường để module khác gọi, API package mặc định hoặc một Named Interface mang tên phù hợp hơn có thể rõ nghĩa hơn.

## 4. Package api, events và integration

Các package này thường diễn đạt những loại hợp đồng khác nhau. Chúng không tự động được Spring Modulith expose; muốn công bố subpackage, hãy khai báo Named Interface.

| Tên package | Vai trò thường dùng | Khi nào nên công bố? |
|---|---|---|
| **api** | Hợp đồng công khai được nhóm riêng | Khi muốn tách API khỏi package gốc và cần một Named Interface rõ tên |
| **events** | Các sự kiện nghiệp vụ được module phát ra | Khi module khác cần lắng nghe các event này |
| **integration** | Hợp đồng phục vụ tích hợp với module hoặc hệ thống khác | Khi bên ngoài module cần dùng các kiểu tích hợp ổn định |
| **spi** | Điểm mở rộng hoặc hợp đồng do thành phần khác triển khai | Khi module thực sự cho phép thay thế hoặc bổ sung hành vi |
| **internal** | Chi tiết triển khai | Thông thường không công bố |

Ví dụ công bố event:

~~~java
@org.springframework.modulith.NamedInterface("events")
package com.acme.shop.orders.events;
~~~

~~~java
package com.acme.shop.orders.events;

import java.time.Instant;

public record OrderPlaced(String orderId, Instant occurredAt) {}
~~~

Module **orders** có thể phát sự kiện **OrderPlaced** sau khi đơn hàng được tạo. Module khác đăng ký listener theo type event đã công bố. Bên nhận chỉ phụ thuộc vào hợp đồng sự kiện; nó không cần truy cập aggregate hoặc repository của **orders**.

Không phải mọi event nội bộ đều cần công bố. Nếu event chỉ dùng để phối hợp các thành phần bên trong cùng module, hãy giữ nó trong package nội bộ. Khi công bố event liên module, cần coi tên, trường dữ liệu và ý nghĩa nghiệp vụ của event là một phần hợp đồng mà module phát sự kiện phải duy trì.

Tương tự, **integration** nên chứa DTO, interface hoặc event cần thiết cho tích hợp. Tránh đưa entity persistence hoặc class triển khai cụ thể vào đây vì điều đó khiến hợp đồng tích hợp phụ thuộc vào cấu trúc nội bộ.

## 5. Package domain, application và persistence

Các tên này thường mô tả trách nhiệm kỹ thuật hoặc lớp trong mô hình nghiệp vụ. Chúng hữu ích để tổ chức mã nguồn, nhưng không nhất thiết là API liên module.

**domain** có thể chứa aggregate, entity, value object và domain service. Nếu những type này chỉ phục vụ nghiệp vụ của một module, hãy giữ chúng nội bộ. Chia sẻ entity giữa nhiều module thường tạo liên kết chặt vào vòng đời, quy tắc bất biến và cách lưu trữ của module sở hữu. Thường nên công bố một hợp đồng hoặc dữ liệu đọc phù hợp với nhu cầu của consumer.

**application** có thể chứa use case, command handler và application service điều phối nghiệp vụ. Những class này thường là chi tiết triển khai của module. Module khác nên gọi facade hoặc interface công khai mà module chủ động thiết kế thay vì import trực tiếp mọi application service.

**persistence** thường chứa Spring Data repository, mapping JPA, cấu hình truy cập dữ liệu và truy vấn riêng của module. Repository không nên trở thành API dùng chung chỉ vì có phương thức public. Hãy để module sở hữu dữ liệu quyết định cách đọc và ghi.

Ví dụ một cách chia package nội bộ:

~~~text
orders
├── OrderManagement.java
├── internal
│   ├── application
│   │   └── PlaceOrderService.java
│   ├── domain
│   │   ├── Order.java
│   │   └── OrderLine.java
│   └── persistence
│       ├── OrderEntity.java
│       └── JpaOrderRepository.java
~~~

Cách chia trên giữ các tầng kỹ thuật bên trong module. Nếu số lượng class còn ít, có thể đặt chúng trực tiếp trong **internal** thay vì tạo nhiều package con rỗng. Hãy thêm tầng khi nó giúp nhóm trách nhiệm rõ hơn, không chỉ để tạo cấu trúc sâu.

## 6. Package web, messaging, config và adapter

Các package sau thường là adapter hoặc cấu hình phục vụ một cách giao tiếp cụ thể:

- **web** hoặc **rest**: controller, request/response DTO và xử lý HTTP.
- **messaging**: listener, message mapper và publisher cho broker.
- **config**: cấu hình Spring bean, client và tích hợp kỹ thuật.
- **adapter**: thành phần chuyển đổi giữa mô hình nội bộ và hệ thống bên ngoài.
- **client**: HTTP client hoặc SDK wrapper để gọi dịch vụ khác.

Những package này thường thuộc phần triển khai của module. Một REST controller không tự động trở thành API Java cho module khác; HTTP API và API package của Spring Modulith là hai ranh giới khác nhau. Tương tự, message listener là chi tiết nhận thông điệp; event hoặc message contract chỉ nên được công bố khi có consumer bên ngoài module cần tham chiếu type đó.

Ví dụ:

~~~text
inventory
├── InventoryReservation.java
└── internal
    ├── web
    │   └── InventoryController.java
    ├── messaging
    │   └── StockUpdatedListener.java
    ├── persistence
    │   └── JpaStockRepository.java
    └── config
        └── InventoryClientConfiguration.java
~~~

Đặt adapter dưới **internal** nhấn mạnh rằng đây là phương tiện thực hiện nghiệp vụ của module. Nếu ứng dụng cần công bố một HTTP contract hoặc message contract cho module khác, hãy tạo type hợp đồng riêng và công bố nó một cách tường minh.

## 7. Đặt tên package không thay thế quy tắc expose

Các quy ước tên giúp đội ngũ hiểu kiến trúc nhanh hơn, nhưng cần phân biệt ba lớp:

1. **Tên package** truyền đạt ý nghĩa và trách nhiệm cho người đọc.
2. **Cấu trúc Application Module** xác định package nào thuộc module nào.
3. **API package và Named Interface** xác định type nào được module công bố; **allowedDependencies** giới hạn module tiêu thụ được phép dùng giao diện nào.

Ví dụ, chỉ đổi tên **orders.private** thành **orders.spi** không làm package trở thành API. Tương tự, tạo package **orders.api** mà không khai báo Named Interface thì package đó vẫn là subpackage nội bộ theo mặc định.

Để công bố **orders.api**, thêm:

~~~java
@org.springframework.modulith.NamedInterface("api")
package com.acme.shop.orders.api;
~~~

Consumer có thể cho phép đúng giao diện:

~~~java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "orders :: api"
)
package com.acme.shop.inventory;
~~~

Nếu consumer cần cả API package mặc định và Named Interface **api**, hãy khai báo cả hai trong **allowedDependencies**:

~~~java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = { "orders", "orders :: api" }
)
package com.acme.shop.inventory;
~~~

Việc công bố một package là cam kết kiến trúc. Trước khi thêm Named Interface, hãy xác định ai sẽ sử dụng nó, hợp đồng nào cần ổn định và module sở hữu có sẵn sàng duy trì hợp đồng đó hay không.

## 8. Những cách tổ chức nên tránh

**Đưa tất cả class vào một package dùng chung toàn ứng dụng.** Ví dụ, **com.acme.shop.services** chứa service của orders, inventory và customers làm mờ quyền sở hữu nghiệp vụ. Đặt class trong module tương ứng để phụ thuộc đi qua hợp đồng có chủ sở hữu rõ ràng.

**Dùng internal như một API ngầm.** Nếu nhiều module import trực tiếp **orders.internal**, kiến trúc đang phụ thuộc vào chi tiết triển khai. Hãy tìm hợp đồng nghiệp vụ phù hợp và công bố nó có chủ đích.

**Đặt mọi thứ vào spi.** Package **spi** chỉ nên chứa điểm mở rộng hoặc hợp đồng provider. Controller, repository, DTO nội bộ và helper không phải SPI chỉ vì chúng cần được dùng từ một package khác.

**Công bố toàn bộ domain model.** Expose entity và aggregate làm consumer phụ thuộc vào cấu trúc dữ liệu, quan hệ và vòng đời nội bộ. Hãy chọn API, read model hoặc event thể hiện đúng nhu cầu giao tiếp.

**Tạo quá nhiều Named Interface.** Mỗi giao diện công khai làm tăng số hợp đồng cần quản lý. Chỉ tách **api**, **spi**, **events** hoặc **integration** khi các nhóm đó có người tiêu thụ và mục đích khác nhau.

**Nhầm HTTP API với API package.** Controller có thể là đầu vào công khai của ứng dụng qua HTTP, nhưng type controller không vì thế trở thành hợp đồng Java giữa các Application Module.

## 9. Kiểm chứng cấu trúc package

Spring Modulith có thể kiểm tra các phụ thuộc thực tế giữa module. Tạo bài test kiến trúc:

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

Test này giúp phát hiện các phụ thuộc đi vào package nội bộ của module khác, các chu trình phụ thuộc và những vi phạm liên quan đến **allowedDependencies**. Chạy test trong CI để thay đổi package hoặc import không âm thầm làm suy yếu ranh giới.

Khi test thất bại, hãy xem type bị tham chiếu nằm ở package nào. Nếu đó là **internal**, kiểm tra consumer có thực sự cần hợp đồng này hay không. Nếu đó là **spi**, **events** hoặc **api**, xác nhận package đã khai báo Named Interface và consumer được phép phụ thuộc vào đúng interface. Không sửa lỗi bằng cách công bố toàn bộ module nếu chỉ một hợp đồng nhỏ cần được chia sẻ.

## 10. Quy trình chọn tên và vị trí package

Khi thêm một type mới, hãy tự hỏi:

1. Type này thuộc năng lực nghiệp vụ nào? Đặt nó bên trong Application Module sở hữu nghiệp vụ đó.
2. Type có phải hợp đồng cho module khác không? Nếu không, giữ nó trong phần nội bộ.
3. Nếu là hợp đồng, nó thuộc API nghiệp vụ chính, điểm mở rộng SPI, event hay hợp đồng tích hợp? Chọn tên thể hiện đúng vai trò.
4. Nếu hợp đồng nằm trong subpackage, khai báo Named Interface tương ứng.
5. Cập nhật **allowedDependencies** ở module tiêu thụ nếu dự án giới hạn phụ thuộc.
6. Chạy **ApplicationModules.verify()** để kiểm tra toàn bộ ranh giới.

Tên package tốt giúp người đọc nhận ra ai sở hữu nghiệp vụ, class phục vụ mục đích gì và hợp đồng nào được phép sử dụng từ bên ngoài. Khi quy ước tên được kết hợp với API package, Named Interface và kiểm chứng kiến trúc, cấu trúc package trở thành một phần thực thi của thiết kế modular monolith.

## Tài liệu tham khảo

- [Spring Modulith Reference — Fundamentals](https://docs.spring.io/spring-modulith/reference/fundamentals.html): Application Module, API package, Named Interface và Open Application Module.
- [Spring Modulith Reference — Application Module Structure Verification](https://docs.spring.io/spring-modulith/reference/verification.html): kiểm tra phụ thuộc module và cấu trúc kiến trúc.
- [Spring Modulith Javadoc — NamedInterface](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/NamedInterface.html): khai báo giao diện được công bố của một module.
