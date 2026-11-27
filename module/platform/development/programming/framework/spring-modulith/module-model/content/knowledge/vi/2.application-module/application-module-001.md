# Cấu trúc cơ bản của một application module

Spring Modulith giúp tổ chức một ứng dụng Spring Boot thành các mô-đun nghiệp vụ có ranh giới rõ ràng. Mỗi mô-đun sở hữu một phần trách nhiệm của ứng dụng, công bố một API mà mô-đun khác được phép sử dụng và giữ phần triển khai bên trong. Mô hình này giúp ứng dụng vẫn có thể được triển khai như một khối thống nhất (modular monolith), đồng thời giữ cấu trúc mã nguồn dễ hiểu và dễ kiểm soát khi hệ thống phát triển.

Trong `SPRING_MODULITH_MODULE_MODEL`, việc đọc cấu trúc package là bước đầu để nhận diện ranh giới nghiệp vụ, API công khai và phụ thuộc giữa các package. Bài học này tập trung vào cách một application module được hình thành từ package, phần nào được xem là API, phần nào là nội bộ và cách thể hiện cấu trúc đó trong mã nguồn.

## 1. Application module là gì?

Application module là một đơn vị chức năng bên trong ứng dụng. Đơn vị đó thường tương ứng với một khả năng nghiệp vụ như quản lý đơn hàng, tồn kho, thanh toán hoặc khách hàng. Một module có thể chứa controller, service, repository, entity, cấu hình và các thành phần khác cần thiết để thực hiện trách nhiệm của nó.

Điểm quan trọng là ranh giới module được xác định theo trách nhiệm nghiệp vụ, không phải theo loại kỹ thuật. Ví dụ, `order` và `inventory` là hai module có ý nghĩa nghiệp vụ. `controller`, `service` và `repository` thường là các package kỹ thuật nằm bên trong từng module.

Spring Modulith mặc định nhận diện module dựa trên cấu trúc package của ứng dụng:

- Package gốc của ứng dụng thường là package chứa lớp khởi chạy có `@SpringBootApplication`.
- Mỗi package con trực tiếp của package gốc được xem là một application module.
- Các package con nằm bên trong một module tiếp tục thuộc về module đó.

Ví dụ, nếu lớp khởi chạy nằm trong `com.example.shop`, các package `com.example.shop.order` và `com.example.shop.inventory` là hai module riêng biệt. Các package sâu hơn như `com.example.shop.order.internal` vẫn thuộc module `order`, không tự trở thành module cấp cao nhất.

Spring Modulith tổ chức ranh giới này ở cấp package. Bạn không cần tách mỗi module thành một Maven module, Gradle module hay tiến trình riêng. Các module vẫn có thể chạy trong cùng một ứng dụng Spring Boot và cùng được đóng gói, triển khai.

## 2. Nhìn cấu trúc module qua cây package

Giả sử ứng dụng bán hàng có hai khả năng nghiệp vụ là quản lý tồn kho và quản lý đơn hàng. Cấu trúc package có thể được tổ chức như sau:

```text
com.example.shop
├── ShopApplication.java
├── inventory
│   ├── InventoryManagement.java
│   ├── StockItem.java
│   └── internal
│       ├── InventoryManagementImpl.java
│       └── InventoryRepository.java
└── order
    ├── OrderManagement.java
    └── internal
        ├── OrderManagementImpl.java
        └── OrderRepository.java
```

Trong cấu trúc trên:

| Package hoặc lớp | Vai trò |
|---|---|
| `com.example.shop` | Package gốc của ứng dụng, nơi đặt lớp khởi chạy |
| `com.example.shop.inventory` | Package gốc của module `inventory` |
| `com.example.shop.inventory.internal` | Package chứa phần triển khai nội bộ của `inventory` |
| `com.example.shop.order` | Package gốc của module `order` |
| `com.example.shop.order.internal` | Package chứa phần triển khai nội bộ của `order` |

Tên package cấp cao nhất nên diễn đạt khả năng nghiệp vụ. Khi đó, chỉ cần nhìn cây package, người đọc đã có thể nhận ra ứng dụng được chia thành những phần chức năng nào.

### Package gốc của ứng dụng

Package gốc là điểm xuất phát để Spring Modulith tìm các module. Lớp khởi chạy thường được đặt ở đây:

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

Đặt lớp khởi chạy ở package gốc giúp Spring Boot quét các thành phần trong những package con. Đồng thời, Spring Modulith có thể dùng lớp ứng dụng này làm điểm tham chiếu khi xây dựng mô hình module, chẳng hạn qua `ApplicationModules.of(ShopApplication.class)`.

### Package gốc của module

Package gốc của module chứa những kiểu dữ liệu và thành phần tạo nên giao diện mà module muốn công bố. Trong ví dụ, `InventoryManagement` là API để module khác yêu cầu kiểm tra tồn kho:

```java
package com.example.shop.inventory;

public interface InventoryManagement {

    boolean hasAvailableStock(String sku, int quantity);
}
```

Một module có thể công bố nhiều lớp hoặc interface ở package gốc. Các kiểu này tạo thành bề mặt API của module. Nên giữ API nhỏ, thể hiện đúng nhu cầu mà module khác cần, để phần triển khai bên trong có thể thay đổi mà ít ảnh hưởng đến các bên sử dụng.

### Package con chứa phần triển khai

Phần triển khai có thể được đặt trong package con, ví dụ `internal`:

```java
package com.example.shop.inventory.internal;

import com.example.shop.inventory.InventoryManagement;
import org.springframework.stereotype.Service;

@Service
class InventoryManagementImpl implements InventoryManagement {

    private final InventoryRepository repository;

    InventoryManagementImpl(InventoryRepository repository) {
        this.repository = repository;
    }

    @Override
    public boolean hasAvailableStock(String sku, int quantity) {
        return repository.availableQuantity(sku) >= quantity;
    }
}
```

`InventoryManagementImpl` và `InventoryRepository` phục vụ việc thực hiện nghiệp vụ tồn kho. Module `order` không cần biết module `inventory` dùng repository nào, truy vấn dữ liệu ra sao hay triển khai kiểm tra tồn kho bằng cách nào. Module `order` chỉ cần gọi API `InventoryManagement`.

## 3. API công khai và phần nội bộ

Một application module cần có ranh giới truy cập rõ ràng. Theo quy ước mặc định của Spring Modulith, các kiểu nằm trực tiếp trong package gốc của module được xem là thành phần được công bố. Các package con được xem là nội bộ, trừ khi chúng được công bố rõ ràng bằng named interface hoặc module được cấu hình theo kiểu mở.

Với module `inventory` trong ví dụ:

- `com.example.shop.inventory.InventoryManagement` thuộc API công khai.
- `com.example.shop.inventory.StockItem` cũng nằm trong package gốc và có thể là một kiểu công khai nếu API cần dùng nó.
- `com.example.shop.inventory.internal.InventoryManagementImpl` thuộc phần nội bộ.
- `com.example.shop.inventory.internal.InventoryRepository` thuộc phần nội bộ.

Sự phân biệt này có ý nghĩa ở cấp kiến trúc. Java có thể cho phép một lớp `public` được import từ package khác, nhưng điều đó không có nghĩa lớp đó nên được module khác sử dụng. Spring Modulith kiểm tra việc truy cập theo mô hình module để phát hiện những phụ thuộc đi vào package nội bộ.

Ví dụ, module `order` có thể phụ thuộc vào API công khai của `inventory`:

```java
package com.example.shop.order.internal;

import com.example.shop.inventory.InventoryManagement;
import org.springframework.stereotype.Service;

@Service
class OrderService {

    private final InventoryManagement inventory;

    OrderService(InventoryManagement inventory) {
        this.inventory = inventory;
    }

    void checkStockBeforePlacingOrder(String sku, int quantity) {
        if (!inventory.hasAvailableStock(sku, quantity)) {
            throw new IllegalStateException("Insufficient stock");
        }
    }
}
```

Module `order` gọi qua `InventoryManagement`. Nó không import `InventoryManagementImpl` hoặc `InventoryRepository`. Nhờ vậy, module tồn kho có thể thay đổi cách lưu trữ hoặc cách tính số lượng khả dụng mà không buộc module đơn hàng thay đổi theo.

### Công bố một package con bằng named interface

Đôi khi API của module cần được chia thành nhiều nhóm. Ví dụ, module `inventory` có API thông thường và một nhóm kiểu dành cho tích hợp hoặc mở rộng. Bạn có thể công bố một package con có chủ đích bằng `@NamedInterface`.

Đặt `package-info.java` trong package cần công bố:

```java
@org.springframework.modulith.NamedInterface("spi")
package com.example.shop.inventory.spi;
```

Các kiểu trong `com.example.shop.inventory.spi` khi đó thuộc named interface có tên `spi`. Module khác có thể phụ thuộc vào giao diện được công bố này theo tên, thay vì truy cập tùy ý vào mọi package nội bộ của `inventory`.

Named interface hữu ích khi một module có nhiều nhóm người dùng hoặc nhiều loại hợp đồng khác nhau. Tên giao diện nên thể hiện mục đích sử dụng, chẳng hạn `spi`, `api` hoặc một tên gắn với nghiệp vụ. Không nên công bố package nội bộ chỉ để giải quyết nhanh một lỗi truy cập; trước tiên hãy xem xét liệu kiểu đó có thực sự là hợp đồng cần chia sẻ hay không.

### Mở toàn bộ module

Spring Modulith cũng hỗ trợ cấu hình module theo kiểu mở bằng `@ApplicationModule(type = ApplicationModule.Type.OPEN)`. Khi module được mở, các package bên trong có thể được truy cập rộng hơn theo quy tắc của kiểu module. Cách này phù hợp với một số trường hợp đặc biệt, nhưng làm giảm khả năng kiểm soát API. Với module nghiệp vụ thông thường, nên bắt đầu từ cấu trúc đóng mặc định và chỉ công bố những phần thực sự cần thiết.

## 4. Khai báo thông tin và quy tắc của module

Bạn có thể đặt `@ApplicationModule` trong `package-info.java` của package gốc module để khai báo thông tin hoặc giới hạn phụ thuộc. Ví dụ, module `order` chỉ định module `inventory` là một phụ thuộc được cho phép:

```java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "inventory"
)
package com.example.shop.order;
```

`allowedDependencies` giúp diễn đạt những module mà module hiện tại được phép phụ thuộc. Khi khai báo quy tắc này, tên module phải khớp với tên package module mà Spring Modulith nhận diện. Nếu module cần sử dụng một named interface, hãy khai báo phụ thuộc theo cú pháp mà phiên bản Spring Modulith của dự án hỗ trợ cho named interface đó.

Không phải module nào cũng cần `package-info.java`. Nếu cấu trúc package đã đủ rõ và chưa cần metadata bổ sung, quy ước package mặc định vẫn có thể mô tả mô hình module. Khi cần chính sách truy cập, tên hiển thị hoặc cấu hình module, `@ApplicationModule` là nơi thích hợp để khai báo.

## 5. Phụ thuộc giữa các module

Khi một module sử dụng API của module khác, một quan hệ phụ thuộc được hình thành. Ví dụ:

```mermaid
flowchart LR
    Order["order module"] -->|InventoryManagement| Inventory["inventory module"]
```

Hướng mũi tên thể hiện module `order` phụ thuộc vào module `inventory`. Trong mã nguồn, quan hệ này xuất hiện khi lớp của `order` import và sử dụng kiểu được công bố bởi `inventory`.

Một cấu trúc tốt thường có các đặc điểm sau:

1. **Phụ thuộc đi qua API công khai.** Module sử dụng hợp đồng đã công bố, không truy cập lớp triển khai hoặc repository nội bộ của module khác.
2. **Trách nhiệm nghiệp vụ được giữ đúng nơi.** Logic quản lý tồn kho thuộc `inventory`; logic xử lý đơn hàng thuộc `order`. Module gọi nhau qua hợp đồng khi cần phối hợp.
3. **Tránh phụ thuộc vòng.** Nếu `order` phụ thuộc `inventory` và `inventory` lại phụ thuộc `order`, hai module đã bị ràng buộc chặt. Hãy xem lại quyền sở hữu nghiệp vụ, đưa hợp đồng dùng chung về vị trí phù hợp hoặc cân nhắc giao tiếp qua sự kiện.
4. **Giữ số lượng phụ thuộc ở mức cần thiết.** Mỗi quan hệ phụ thuộc bổ sung thêm một ràng buộc mà nhóm phát triển phải hiểu và duy trì.

Trong một số luồng nghiệp vụ, module phát sự kiện và module khác lắng nghe sự kiện có thể giảm phụ thuộc trực tiếp. Chẳng hạn, sau khi đơn hàng được tạo, `order` phát sự kiện `OrderPlaced`; module khác có thể phản ứng với sự kiện đó. Cách giao tiếp bằng sự kiện là một lựa chọn thiết kế bổ sung. Dù dùng API hay sự kiện, mỗi module vẫn cần có trách nhiệm và ranh giới package rõ ràng.

## 6. Cách chọn cấu trúc package cho một ứng dụng

Khi bắt đầu chia module, hãy đi từ các khả năng nghiệp vụ mà ứng dụng cung cấp. Với một hệ thống bán hàng, cấu trúc cấp cao có thể là:

```text
com.example.shop
├── ShopApplication.java
├── customer
├── inventory
├── order
├── payment
└── shipping
```

Sau đó, mỗi module có thể tự tổ chức các package con theo nhu cầu:

```text
com.example.shop.order
├── OrderManagement.java
├── OrderPlaced.java
├── web
│   └── OrderController.java
├── application
│   └── PlaceOrderService.java
├── domain
│   ├── Order.java
│   └── OrderLine.java
└── internal
    └── OrderRepository.java
```

Đây là một cách tổ chức minh họa. Bạn có thể chọn tên và cách chia package con khác, miễn là cấu trúc thể hiện được trách nhiệm và giữ được ranh giới truy cập. Những package như `web`, `application`, `domain` hoặc `internal` ở đây đều nằm dưới `order`, nên chúng vẫn thuộc module `order`.

Tránh tổ chức toàn bộ ứng dụng theo các package kỹ thuật ở cấp trực tiếp dưới package gốc, ví dụ:

```text
com.example.shop
├── controller
├── service
├── repository
└── entity
```

Theo quy ước phát hiện module mặc định, các package cấp trực tiếp như `controller`, `service`, `repository` và `entity` có thể bị nhận diện thành các module riêng. Cách chia này còn làm một nghiệp vụ bị phân tán qua nhiều module kỹ thuật, khiến ranh giới nghiệp vụ khó nhận biết. Thay vào đó, hãy đặt các thành phần kỹ thuật bên trong module nghiệp vụ tương ứng.

Một package tên `common` ở cấp gốc cũng cần được cân nhắc kỹ. Nếu mọi module đều đưa các kiểu tiện ích hoặc nghiệp vụ dùng chung vào đó, package này dễ trở thành nơi tập trung phụ thuộc và khó xác định quyền sở hữu. Chỉ tạo module dùng chung khi có một trách nhiệm rõ ràng và hợp đồng ổn định; nếu một kiểu chỉ phục vụ một nghiệp vụ, hãy giữ nó trong module sở hữu nghiệp vụ đó.

## 7. Kiểm tra mô hình module

Sau khi tổ chức package, bạn có thể dùng `ApplicationModules` để yêu cầu Spring Modulith xây dựng mô hình và kiểm tra các quy tắc kiến trúc. Một kiểm thử đơn giản có thể viết như sau:

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

Lệnh `verify()` kiểm tra mô hình module, bao gồm những vi phạm ranh giới và phụ thuộc không hợp lệ mà Spring Modulith có thể phát hiện. Khi kiểm thử thất bại, hãy đọc thông báo để xác định module nào đang truy cập package nội bộ, phụ thuộc chưa được cho phép hoặc tạo thành chu trình phụ thuộc. Sau đó, sửa hợp đồng hoặc cấu trúc package tại đúng module sở hữu trách nhiệm.

Bạn cũng có thể duyệt mô hình để quan sát những module được phát hiện:

```java
ApplicationModules modules = ApplicationModules.of(ShopApplication.class);
modules.forEach(System.out::println);
```

Việc kiểm tra bằng mã giúp quy tắc kiến trúc được thực thi lặp lại trong quá trình phát triển và trong CI. Nhờ đó, một thay đổi package hoặc một import mới có thể được phát hiện sớm nếu nó làm sai lệch ranh giới đã thiết kế.

## 8. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| Một module phải là một Maven hoặc Gradle module | Application module của Spring Modulith có thể chỉ là một nhóm package trong cùng ứng dụng. |
| Package `service` luôn là module | Chỉ package con trực tiếp của package gốc mới được nhận diện thành module theo quy ước mặc định; package kỹ thuật nên nằm dưới module nghiệp vụ. |
| Cứ khai báo lớp `public` là đã tạo API module | Khả năng truy cập của Java và quy tắc công bố API của Spring Modulith là hai khái niệm khác nhau. |
| Module khác có thể import bất kỳ lớp nào nếu ứng dụng vẫn biên dịch | Mã có thể biên dịch nhưng vẫn vi phạm ranh giới kiến trúc mà Spring Modulith kiểm tra. |
| Đưa mọi kiểu dùng chung vào `common` luôn làm thiết kế tốt hơn | Cần xác định rõ quyền sở hữu và trách nhiệm của phần dùng chung để tránh tạo một module tập trung phụ thuộc. |
| Named interface đồng nghĩa với việc mở toàn bộ module | Named interface chỉ công bố một nhóm package có tên; module vẫn có thể giữ các package khác ở trạng thái nội bộ. |

## 9. Checklist thiết kế một application module

Trước khi xem một package là module hoàn chỉnh, hãy kiểm tra các điểm sau:

- [ ] Package gốc ứng dụng được xác định rõ và lớp khởi chạy nằm ở vị trí phù hợp.
- [ ] Mỗi package con trực tiếp của package gốc đại diện cho một khả năng hoặc trách nhiệm nghiệp vụ.
- [ ] Các package con của module được tổ chức bên trong đúng module sở hữu chúng.
- [ ] API công khai nằm ở package gốc hoặc trong named interface được công bố có chủ đích.
- [ ] Lớp triển khai, repository và chi tiết nội bộ được giữ trong package nội bộ.
- [ ] Module khác chỉ phụ thuộc vào hợp đồng đã công bố.
- [ ] Các quan hệ phụ thuộc có hướng rõ ràng và không tạo chu trình.
- [ ] Kiểm thử `ApplicationModules.of(...).verify()` được dùng để kiểm tra quy tắc kiến trúc.

## 10. Kết luận

Cấu trúc cơ bản của một application module bắt đầu từ package gốc ứng dụng và các package con trực tiếp đại diện cho module nghiệp vụ. Bên trong mỗi module, package gốc tạo nên API được công bố theo mặc định, còn các package con giữ phần triển khai nội bộ trừ khi được mở rõ ràng bằng named interface hoặc cấu hình module phù hợp.

Khi tổ chức package theo trách nhiệm nghiệp vụ, giữ API nhỏ và kiểm soát phụ thuộc qua Spring Modulith, ứng dụng Spring Boot có thể duy trì sự thống nhất trong triển khai mà vẫn có các ranh giới kiến trúc đủ rõ để phát triển và kiểm chứng lâu dài.
