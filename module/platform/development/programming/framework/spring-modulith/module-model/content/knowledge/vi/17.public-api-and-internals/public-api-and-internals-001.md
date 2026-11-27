# API package là cổng truy cập mặc định

Trong Spring Modulith, package gốc của một application module là nơi công bố API mặc định. Module khác có thể phụ thuộc vào các kiểu được công khai trong package này. Những package con như `internal`, `persistence` hoặc `web` được xem là phần triển khai nội bộ theo quy ước mặc định, dù các class trong đó có thể khai báo `public` theo quy tắc của Java.

Quy ước này tạo ra một cổng truy cập dễ nhận biết: muốn sử dụng năng lực của module, hãy tìm API ở package gốc trước. Nếu một package con cần được công bố riêng, hãy đánh dấu nó bằng named interface. Nhờ vậy, nhóm có thể phân biệt hợp đồng mà module cam kết cung cấp với những chi tiết có thể thay đổi bên trong.

## 1. Package gốc là API mặc định của module

Giả sử ứng dụng có package gốc `com.acme.shop`. Theo quy ước phát hiện module mặc định, mỗi package con trực tiếp như `inventory`, `order` hoặc `payment` là một application module.

Package gốc của module `inventory` là:

~~~text
com.acme.shop.inventory
~~~

Đây là **base package** của module. Spring Modulith xem các kiểu nằm trực tiếp trong package này là phần API mặc định của module, miễn là chúng có khả năng truy cập phù hợp theo Java, thường là kiểu `public`.

Ví dụ cấu trúc:

~~~text
com.acme.shop
├── ShopApplication.java
├── inventory
│   ├── InventoryManagement.java
│   ├── ReserveStockCommand.java
│   ├── ReservationResult.java
│   ├── internal
│   │   ├── InventoryManagementImpl.java
│   │   └── StockRepository.java
│   ├── persistence
│   │   └── JpaStockRepository.java
│   └── web
│       └── InventoryController.java
└── order
    └── internal
        └── PlaceOrderService.java
~~~

Trong cấu trúc này:

- `inventory` là module nghiệp vụ.
- `InventoryManagement`, `ReserveStockCommand` và `ReservationResult` nằm trong base package, nên tạo nên API mặc định.
- `inventory.internal`, `inventory.persistence` và `inventory.web` là các package con nội bộ theo mặc định.
- `order` sử dụng API của `inventory` thông qua package gốc.

Không cần tạo thêm một thư mục `api` bên trong module chỉ để Spring Modulith nhận diện API mặc định. Chính base package đã đóng vai trò đó.

## 2. API kiến trúc và khả năng truy cập của Java

Java và Spring Modulith giải quyết hai lớp quy tắc khác nhau.

**Java visibility** quyết định mã nguồn có thể tham chiếu một kiểu hoặc thành viên hay không. Một class `public` trong package con có thể được import từ package khác nếu class và các thành viên cần dùng có visibility phù hợp.

**Module API visibility** quyết định kiểu đó có được xem là hợp đồng công khai giữa các application module hay không. Theo quy ước đóng gói mặc định, package gốc là API; package con vẫn là nội bộ, kể cả khi class bên trong được khai báo `public`.

Ví dụ:

~~~java
package com.acme.shop.inventory.internal;

public class StockRepository {
    // Chi tiết truy cập dữ liệu của module inventory.
}
~~~

Một class khác về mặt Java có thể import `StockRepository`. Tuy nhiên, nếu class đó thuộc module `order`, dependency này đi vào package nội bộ của `inventory` và vi phạm ranh giới kiến trúc mặc định.

Spring Modulith phát hiện loại dependency này khi kiểm tra cấu trúc module. Nó không thay đổi compiler của Java và không ngăn câu lệnh import được biên dịch ngay từ đầu. Vì vậy, cần chạy kiểm tra kiến trúc trong bộ kiểm thử để phát hiện những tham chiếu xuyên qua ranh giới.

Một điểm dễ nhầm khác: package con không phải package con theo nghĩa visibility của Java. `com.acme.shop.inventory` và `com.acme.shop.inventory.internal` là hai Java package khác nhau. Thành viên package-private trong package gốc không tự động truy cập được từ package `internal`, và ngược lại.

## 3. Thiết kế API nhỏ trong base package

Hãy đưa vào base package những kiểu mà module khác thực sự cần để yêu cầu một hành vi hoặc hiểu kết quả của hành vi đó. Ví dụ, module `inventory` công bố thao tác giữ hàng:

~~~java
package com.acme.shop.inventory;

public interface InventoryManagement {

    ReservationResult reserve(ReserveStockCommand command);
}
~~~

Lệnh và kết quả cũng thuộc hợp đồng công khai:

~~~java
package com.acme.shop.inventory;

public record ReserveStockCommand(String sku, int quantity) {
}
~~~

~~~java
package com.acme.shop.inventory;

public record ReservationResult(String reservationId, boolean accepted) {
}
~~~

API mô tả ý định nghiệp vụ: module khác yêu cầu giữ một số lượng sản phẩm và nhận kết quả. Nó không tiết lộ module dùng JPA, JDBC, cache hay một cơ chế lưu trữ cụ thể.

Phần triển khai có thể nằm trong package `internal`:

~~~java
package com.acme.shop.inventory.internal;

import com.acme.shop.inventory.InventoryManagement;
import com.acme.shop.inventory.ReservationResult;
import com.acme.shop.inventory.ReserveStockCommand;
import org.springframework.stereotype.Service;

@Service
class InventoryManagementImpl implements InventoryManagement {

    private final StockRepository repository;

    InventoryManagementImpl(StockRepository repository) {
        this.repository = repository;
    }

    @Override
    public ReservationResult reserve(ReserveStockCommand command) {
        // Kiểm tra tồn kho và lưu thông tin giữ hàng.
        return new ReservationResult("reservation-123", true);
    }
}
~~~

`InventoryManagementImpl` và `StockRepository` có thể thay đổi bên trong module mà không buộc module sử dụng phải biết chi tiết đó. API chỉ cần giữ ổn định hành vi và kiểu dữ liệu mà bên gọi dựa vào.

## 4. Module khác đi qua API package như thế nào?

Module `order` cần giữ hàng khi khách tạo đơn. Nó phụ thuộc vào `InventoryManagement` và các kiểu hợp đồng trong base package:

~~~java
package com.acme.shop.order.internal;

import com.acme.shop.inventory.InventoryManagement;
import com.acme.shop.inventory.ReservationResult;
import com.acme.shop.inventory.ReserveStockCommand;
import org.springframework.stereotype.Service;

@Service
class PlaceOrderService {

    private final InventoryManagement inventory;

    PlaceOrderService(InventoryManagement inventory) {
        this.inventory = inventory;
    }

    void place(String sku, int quantity) {
        ReservationResult result = inventory.reserve(
                new ReserveStockCommand(sku, quantity)
        );

        if (!result.accepted()) {
            throw new IllegalStateException("Không đủ hàng để tạo đơn");
        }
    }
}
~~~

Dependency có hướng rõ ràng:

~~~text
order.internal.PlaceOrderService
              |
              | gọi API công khai
              v
inventory.InventoryManagement
              |
              | được triển khai bởi
              v
inventory.internal.InventoryManagementImpl
              |
              v
inventory.internal.StockRepository
~~~

Module `order` biết hợp đồng `InventoryManagement`. Spring container có thể inject implementation tương ứng khi khởi tạo ứng dụng, nhưng mã của `order` không cần import implementation hoặc repository nội bộ của `inventory`.

Việc sử dụng interface là một lựa chọn thiết kế phù hợp khi muốn tách hợp đồng khỏi triển khai. API mặc định không bắt buộc mọi kiểu phải là Java interface; một class hoặc record `public` trong base package cũng có thể là một phần API. Điều cần quản lý là hợp đồng công khai và mức độ ổn định của nó.

## 5. Điều gì nên và không nên đặt trong API package?

Base package là cổng mặc định, vì vậy mỗi kiểu được đặt ở đây cần có lý do để trở thành một phần hợp đồng liên module.

| Nên cân nhắc công bố | Nên giữ nội bộ |
| --- | --- |
| Interface mô tả thao tác nghiệp vụ | Service triển khai use case |
| Command và result dùng trong API | Repository và adapter persistence |
| Kiểu sự kiện module công bố | Entity ORM và mapping nội bộ |
| Value object cần trao đổi qua ranh giới | Helper, mapper hoặc validator chỉ phục vụ triển khai |
| Kiểu truy vấn mà module cam kết hỗ trợ | Controller hoặc lớp điều phối HTTP nếu không phải API module |

Không phải mọi DTO đều cần công khai. Nếu một kiểu chỉ được dùng trong một quy trình nội bộ, hãy đặt nó trong package con phù hợp. Nếu đưa kiểu vào API, cần xem xét khả năng tương thích khi thêm, bỏ hoặc đổi trường và khi thay đổi kiểu trả về.

Đặc biệt, tránh để chữ ký API tham chiếu trực tiếp các kiểu triển khai nội bộ. Ví dụ, `InventoryManagement` không nên trả về `JpaStockEntity` hoặc nhận `StockRepository`. Khi đó, hợp đồng công khai sẽ phụ thuộc vào chi tiết mà module cần quyền tự thay đổi.

## 6. Package con là internal theo mặc định

Spring Modulith xem các package con của base package là nội bộ nếu chúng chưa được công bố tường minh hoặc chưa được mô hình hóa theo một cách khác.

Ví dụ:

~~~text
com.acme.shop.inventory
├── InventoryManagement.java       // API mặc định
├── ReservationResult.java         // API mặc định
├── internal
│   ├── InventoryManagementImpl.java
│   └── StockRepository.java        // internal
├── persistence
│   └── JpaStockRepository.java     // internal
└── web
    └── InventoryController.java   // internal theo ranh giới module
~~~

Một controller nằm trong `inventory.web` có thể được Spring MVC đăng ký và phục vụ HTTP bình thường. Việc controller được framework sử dụng không tự biến package `web` thành API cho application module khác. API HTTP của ứng dụng và API package của module là hai hợp đồng khác nhau.

Tương tự, class `public` trong `inventory.persistence` không tự trở thành API. Module khác vẫn nên đi qua base package hoặc giao diện được công bố rõ ràng.

## 7. Khi nào cần công bố package con bằng Named Interface?

Có trường hợp một module cần công bố một nhóm kiểu nằm ngoài base package. Ví dụ, `inventory` có một SPI dành cho adapter hoặc module tích hợp. Khi đó, hãy dùng `@NamedInterface` trên `package-info.java` của package con:

~~~java
@org.springframework.modulith.NamedInterface("spi")
package com.acme.shop.inventory.spi;
~~~

Cấu trúc lúc này:

~~~text
com.acme.shop.inventory
├── InventoryManagement.java
├── internal
│   └── StockRepository.java
└── spi
    ├── package-info.java           // @NamedInterface("spi")
    └── StockReservationProvider.java
~~~

Module `inventory` có hai vùng API được công bố:

- Base package `inventory`, là API mặc định không có tên riêng.
- Named interface `inventory::spi`, là giao diện bổ sung có tên `spi`.

Module sử dụng có thể khai báo dependency đến named interface cụ thể. Ví dụ, tại package gốc của module `order`:

~~~java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "inventory::spi"
)
package com.acme.shop.order;
~~~

Khai báo này phù hợp nếu `order` chỉ cần named interface `spi`. Nếu `order` cần cả API mặc định ở base package và SPI, hãy cho phép cả hai:

~~~java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = { "inventory", "inventory::spi" }
)
package com.acme.shop.order;
~~~

Hãy chọn allowlist dựa trên các kiểu mà module thực sự sử dụng.

Named interface chỉ công bố package con được đánh dấu. Những package con khác như `internal` hoặc `persistence` vẫn nội bộ theo mặc định.

## 8. Named Interface khác nested module

Một package con được đánh dấu `@NamedInterface` vẫn thuộc module cha. Nó mở rộng tập hợp API được công bố của module, nhưng không tạo ra một application module độc lập.

Nested module là một khái niệm khác: package con được khai báo như một module riêng và có thể có ranh giới, API cùng dependency riêng. Hãy chọn theo mục đích:

| Nhu cầu | Cách biểu diễn |
| --- | --- |
| Công bố một nhóm kiểu ở package con | `@NamedInterface` |
| Tách một phần nghiệp vụ thành module con có ranh giới riêng | Nested application module |
| Giữ package con làm chi tiết triển khai | Không công bố; để internal theo mặc định |

Không nên tạo nested module chỉ để cho phép module khác import một interface. Nếu chỉ cần công bố một hợp đồng bổ sung, named interface là cơ chế phù hợp hơn.

## 9. Open module là ngoại lệ đối với quy ước đóng gói mặc định

Một module có thể được đánh dấu là open bằng `@ApplicationModule(type = ApplicationModule.Type.OPEN)`. Trong open module, các package con cũng được đưa vào unnamed interface và được mở cho module khác truy cập theo chính sách open module.

Ví dụ:

~~~java
@org.springframework.modulith.ApplicationModule(
    type = org.springframework.modulith.ApplicationModule.Type.OPEN
)
package com.acme.shop.inventory;
~~~

Đây là lựa chọn có thể hữu ích khi đưa codebase cũ vào kiểm soát kiến trúc mà chưa thể đóng gói toàn bộ package con ngay lập tức. Tuy nhiên, open module làm rộng bề mặt truy cập và giảm khả năng phát hiện một số vấn đề dependency, bao gồm việc open module không tham gia vào kiểm tra dependency cycle như module đóng.

Với module mới, hãy bắt đầu bằng quy ước đóng mặc định: base package là API, package con là internal. Chỉ mở module khi có lý do chuyển đổi rõ ràng và có kế hoạch thu hẹp phạm vi đó.

## 10. Kiểm chứng package API bằng ApplicationModules

Có thể dùng `ApplicationModules.verify()` để kiểm tra các dependency thực tế giữa module:

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

Giả sử `order` gọi `inventory.InventoryManagement`, dependency đó đi qua API mặc định và được chấp nhận. Nếu `order` import `inventory.internal.StockRepository`, Spring Modulith sẽ phát hiện truy cập vào package nội bộ và báo lỗi kiểm chứng.

| Dependency từ `order` | Kết quả theo cấu trúc mặc định |
| --- | --- |
| `inventory.InventoryManagement` | Hợp lệ: kiểu nằm trong base package |
| `inventory.ReserveStockCommand` | Hợp lệ: kiểu nằm trong base package |
| `inventory.internal.StockRepository` | Vi phạm: package con nội bộ |
| `inventory.persistence.JpaStockRepository` | Vi phạm: package con nội bộ |
| `inventory.spi.StockReservationProvider` | Chỉ hợp lệ nếu package `spi` được công bố bằng named interface và dependency được cho phép |

Kiểm thử này giúp biến quy ước package thành một điều kiện có thể chạy tự động trong CI. Nó không thay thế review thiết kế API: một dependency có thể hợp lệ về mặt kỹ thuật nhưng vẫn tạo ra hợp đồng quá rộng hoặc không ổn định.

## 11. Cách tổ chức package để API dễ nhận biết

Khi tạo module mới, có thể làm theo trình tự:

1. Chọn một package gốc theo năng lực nghiệp vụ, ví dụ `com.acme.shop.inventory`.
2. Đưa các interface, command, result và kiểu sự kiện cần công bố trực tiếp vào base package.
3. Đặt service triển khai, repository, adapter và helper vào các package con như `internal`, `persistence` hoặc `integration`.
4. Kiểm tra chữ ký API để không làm lộ kiểu dữ liệu nội bộ.
5. Chỉ đánh dấu named interface khi một package con thực sự cần trở thành hợp đồng cho module khác.
6. Chạy `ApplicationModules.verify()` để phát hiện các dependency đi vào package nội bộ.

Ví dụ một cấu trúc hoàn chỉnh:

~~~text
com.acme.shop
├── inventory
│   ├── InventoryManagement.java
│   ├── ReserveStockCommand.java
│   ├── ReservationResult.java
│   ├── internal
│   │   ├── InventoryManagementImpl.java
│   │   └── StockRepository.java
│   ├── persistence
│   │   └── JpaStockRepository.java
│   └── spi
│       ├── package-info.java
│       └── StockReservationProvider.java
└── order
    ├── package-info.java
    └── internal
        └── PlaceOrderService.java
~~~

Ở đây, API mặc định của `inventory` nằm tại base package. SPI được công bố riêng bằng named interface. Các package triển khai còn lại giữ nội bộ.

## 12. Những nhầm lẫn thường gặp

**Cho rằng mọi class `public` đều thuộc API module.** Java `public` chỉ nói rằng kiểu có thể được tham chiếu từ package khác. Spring Modulith vẫn xem package con là nội bộ theo quy ước mặc định.

**Cho rằng package `internal` là một từ khóa đặc biệt.** Tên `internal` chỉ là quy ước đặt tên dễ hiểu. Chính vị trí package con và mô hình module quyết định nó là nội bộ, không phải riêng tên folder.

**Cho rằng package `api` là bắt buộc.** Base package đã là API mặc định. Có thể tạo package con `api` và đánh dấu named interface nếu có lý do cụ thể, nhưng không cần tạo nó chỉ để Spring Modulith nhận diện API.

**Cho rằng package con có thể truy cập package-private của package cha.** Java coi package cha và package con là hai package riêng. Package-private không tự mở rộng theo cây thư mục.

**Cho rằng controller public là API module.** Endpoint HTTP là giao diện cho client bên ngoài. Ranh giới API module là quy tắc tổ chức và phụ thuộc trong codebase.

**Cho rằng `ApplicationModules.verify()` ngăn import lúc compile.** Công cụ này kiểm chứng kiến trúc khi test chạy. Java compiler vẫn có thể biên dịch tham chiếu đến class `public` trong package con.

## 13. Checklist thiết kế API package

- [ ] Xác định base package của application module.
- [ ] Đưa các kiểu công khai cần thiết vào base package.
- [ ] Giữ implementation, persistence và helper trong package con.
- [ ] Kiểm tra chữ ký API không tham chiếu kiểu nội bộ.
- [ ] Phân biệt Java visibility với API visibility của Spring Modulith.
- [ ] Dùng `@NamedInterface` khi cần công bố rõ một package con.
- [ ] Dùng nested module khi cần một ranh giới module con độc lập.
- [ ] Hạn chế open module và có kế hoạch thu hẹp khi dùng cho code legacy.
- [ ] Chạy `ApplicationModules.verify()` trong bộ kiểm thử kiến trúc.

## 14. Kết luận

Package gốc của application module là cổng truy cập mặc định trong Spring Modulith. Các kiểu công khai tại đó tạo nên API mà module khác có thể sử dụng. Package con được xem là nội bộ theo mặc định, kể cả khi các class bên trong khai báo `public` theo Java.

Hãy đặt hợp đồng nghiệp vụ nhỏ và ổn định trong base package, giữ implementation trong package con và dùng named interface khi thật sự cần công bố thêm một nhóm kiểu. Kết hợp cấu trúc đó với `ApplicationModules.verify()` để phát hiện dependency xuyên vào phần nội bộ ngay trong quá trình phát triển.

## Tài liệu tham khảo

- [Spring Modulith — Fundamentals: Application Modules](https://docs.spring.io/spring-modulith/reference/fundamentals.html)
- [Spring Modulith — Named Interfaces](https://docs.spring.io/spring-modulith/reference/fundamentals.html)
- [Spring Modulith — Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html)
- [Spring Modulith — `ApplicationModule` API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/ApplicationModule.html)
- [Spring Modulith — `NamedInterface` API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/NamedInterface.html)
