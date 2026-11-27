# Access trực tiếp vào internal package bị xem là vi phạm

Trong Spring Modulith, một application module có bề mặt API được xác định rõ. Các mô-đun khác được phép sử dụng API đó, còn những package triển khai nội bộ phải được giữ kín. Vì vậy, khi code của mô-đun `orders` tham chiếu trực tiếp đến một class nằm trong package nội bộ của `inventory`, Spring Modulith xem đó là vi phạm ranh giới mô-đun, kể cả khi class đó được khai báo `public` và Java compiler vẫn biên dịch thành công.

Trong phạm vi **SPRING_MODULITH_MODULE_MODEL**, quy tắc này giúp bảo vệ API công khai và giảm phụ thuộc vào chi tiết triển khai giữa các package trong một ứng dụng Spring Boot. `ApplicationModules.verify()` có thể kiểm tra những phụ thuộc như vậy để nhóm phát hiện vi phạm ngay trong bộ kiểm thử kiến trúc.

## 1. Package nào là API, package nào là internal?

Theo quy ước mặc định của Spring Modulith, một application module có package gốc và các package con. Package gốc tạo thành API mặc định của mô-đun. Những package con khác được xem là nội bộ, trừ khi được công khai rõ ràng bằng named interface.

Ví dụ:

```text
com.acme.shop
├── ShopApplication.java
├── orders
│   ├── OrderManagement.java
│   └── internal
│       └── OrderPolicy.java
└── inventory
    ├── InventoryOperations.java       // API mặc định
    └── internal
        ├── InventoryRepository.java
        └── ReservationPolicy.java
```

Trong cấu trúc này:

- `com.acme.shop.orders` là package gốc và API mặc định của mô-đun `orders`.
- `com.acme.shop.inventory` là package gốc và API mặc định của mô-đun `inventory`.
- `com.acme.shop.inventory.internal` là package triển khai nội bộ của `inventory`.
- `orders` có thể sử dụng các kiểu công khai trong API của `inventory`, nhưng không được phụ thuộc trực tiếp vào các kiểu trong `inventory.internal`.

Tên package `internal` là quy ước đặt tên dễ hiểu cho con người. Quy tắc của Spring Modulith không chỉ dựa vào chữ `internal`: mọi package con không được công khai qua named interface đều là phần nội bộ theo mô hình mặc định. Do đó, một package tên `repository`, `persistence` hay `implementation` cũng là nội bộ nếu không được khai báo công khai.

## 2. Vì sao truy cập trực tiếp bị xem là vi phạm?

Giả sử `InventoryRepository` được khai báo `public`:

```java
package com.acme.shop.inventory.internal;

public class InventoryRepository {

    public boolean hasAvailableStock(String sku) {
        // Truy vấn dữ liệu tồn kho
        return true;
    }
}
```

Một lớp trong `orders` có thể import trực tiếp class này:

```java
package com.acme.shop.orders;

import com.acme.shop.inventory.internal.InventoryRepository;

public class OrderManagement {

    private final InventoryRepository inventoryRepository;

    public OrderManagement(InventoryRepository inventoryRepository) {
        this.inventoryRepository = inventoryRepository;
    }

    public void placeOrder(String sku) {
        if (!inventoryRepository.hasAvailableStock(sku)) {
            throw new IllegalStateException("Insufficient stock");
        }
    }
}
```

Java có thể cho phép đoạn code này biên dịch nếu class và constructor đủ quyền truy cập. Tuy nhiên, ở góc nhìn kiến trúc, `orders` đã phụ thuộc vào cách `inventory` lưu trữ và truy vấn dữ liệu. Khi nhóm thay `InventoryRepository`, đổi persistence framework hoặc thay cách tính tồn kho, mô-đun `orders` có thể phải sửa theo.

Điều quan trọng là phân biệt hai loại kiểm soát:

| Cơ chế | Câu hỏi được trả lời |
|---|---|
| Java access modifier (`public`, `protected`, package-private, `private`) | Mã nguồn có được phép tham chiếu kiểu hoặc thành viên theo luật truy cập của Java không? |
| Ranh giới application module của Spring Modulith | Mô-đun hiện tại có được phép phụ thuộc vào package và kiểu của mô-đun kia không? |

`public` chỉ nói về khả năng truy cập ở cấp ngôn ngữ Java. Nó không tự biến một class trong package nội bộ thành API công khai của application module.

## 3. Spring Modulith phát hiện vi phạm như thế nào?

Spring Modulith khám phá các application module từ package ứng dụng và xây dựng mô hình về API cùng các phụ thuộc giữa chúng. Khi một mô-đun tham chiếu đến kiểu thuộc package nội bộ của mô-đun khác, dependency đó đi qua ranh giới API được phép và trở thành vi phạm.

Phụ thuộc có thể xuất hiện dưới nhiều hình thức, chẳng hạn:

- Import và dùng một class nội bộ làm field hoặc constructor parameter.
- Gọi phương thức hoặc truy cập thành viên của kiểu nội bộ.
- Dùng kiểu nội bộ trong kiểu trả về, tham số, generic hoặc quan hệ kế thừa.
- Đưa kiểu nội bộ vào annotation hoặc một khai báo khác tạo ra dependency tĩnh.

Ta có thể đưa kiểm tra vào bộ test:

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

Nếu `orders` phụ thuộc trực tiếp vào `inventory.internal`, `verify()` sẽ báo vi phạm cấu trúc mô-đun. Nhờ vậy, quy tắc kiến trúc được thực thi tự động mỗi khi chạy test thay vì chỉ nằm trong tài liệu hoặc phụ thuộc vào việc lập trình viên nhớ quy ước.

Kiểm tra này là kiểm tra kiến trúc tĩnh trên mô hình và dependency được phát hiện. Nó không có nghĩa Java compiler tự động từ chối mọi import nội bộ. Nếu không chạy kiểm tra kiến trúc trong quy trình phát triển hoặc CI, code có thể vẫn được biên dịch và đóng gói dù đã phá vỡ ranh giới mong muốn.

## 4. Cách sửa: phụ thuộc vào API công khai của module

Thay vì dùng repository nội bộ, `inventory` nên cung cấp một hợp đồng nghiệp vụ ở package gốc:

```java
package com.acme.shop.inventory;

public interface InventoryOperations {

    boolean hasAvailableStock(String sku);
}
```

Phần triển khai giữ bên trong mô-đun:

```java
package com.acme.shop.inventory.internal;

import org.springframework.stereotype.Service;

@Service
class InventoryOperationsImpl implements InventoryOperations {

    private final InventoryRepository repository;

    InventoryOperationsImpl(InventoryRepository repository) {
        this.repository = repository;
    }

    @Override
    public boolean hasAvailableStock(String sku) {
        return repository.hasAvailableStock(sku);
    }
}
```

`orders` chỉ phụ thuộc vào hợp đồng công khai:

```java
package com.acme.shop.orders;

import com.acme.shop.inventory.InventoryOperations;

public class OrderManagement {

    private final InventoryOperations inventory;

    public OrderManagement(InventoryOperations inventory) {
        this.inventory = inventory;
    }

    public void placeOrder(String sku) {
        if (!inventory.hasAvailableStock(sku)) {
            throw new IllegalStateException("Insufficient stock");
        }
    }
}
```

Giờ đây `orders` biết nghiệp vụ cần hỏi tồn kho, nhưng không biết `inventory` dùng repository, SQL hay cơ chế lưu trữ nào. Mô-đun `inventory` có thể thay đổi triển khai nội bộ miễn là giữ hợp đồng công khai tương thích.

## 5. Công khai package qua Named Interface khi cần

Không phải mọi API đều cần đặt ở package gốc. Nếu muốn gom một nhóm kiểu công khai vào package con, có thể khai báo named interface.

Ví dụ, cấu trúc `inventory`:

```text
inventory
├── internal
│   └── InventoryRepository.java
└── api
    ├── package-info.java
    └── InventoryOperations.java
```

Đánh dấu package `api` trong `inventory/api/package-info.java`:

```java
@org.springframework.modulith.NamedInterface("api")
package com.acme.shop.inventory.api;
```

Mô-đun `orders` khai báo phụ thuộc được phép trong `orders/package-info.java`:

```java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "inventory::api"
)
package com.acme.shop.orders;
```

Sau đó, `orders` dùng kiểu công khai từ package `inventory.api`:

```java
import com.acme.shop.inventory.api.InventoryOperations;
```

Named interface đưa package `api` vào bề mặt công khai của `inventory`. Quy tắc `allowedDependencies` giới hạn `orders` sử dụng named interface đó. Package `inventory.internal` vẫn được giữ kín và việc truy cập trực tiếp vào đó vẫn là vi phạm.

Hãy công khai những kiểu mà mô-đun khác thực sự cần. Không nên đánh dấu tất cả package con thành named interface, vì như vậy ranh giới giữa API và chi tiết triển khai sẽ mất ý nghĩa.

## 6. Khi nào nên dùng API, khi nào nên dùng sự kiện?

Lời gọi trực tiếp qua API công khai phù hợp khi mô-đun gọi cần kết quả để tiếp tục quyết định. Ví dụ, `orders` hỏi `inventory` xem có thể giữ hàng hay không và cần câu trả lời ngay trong quy trình đặt hàng.

Sự kiện nghiệp vụ phù hợp khi mô-đun phát thông báo một sự kiện đã xảy ra và không cần gọi trực tiếp từng bên nhận. Ví dụ, sau khi đơn hàng được xác nhận, `orders` phát `OrderConfirmed` để mô-đun thông báo hoặc phân tích xử lý độc lập.

Không nên dùng sự kiện chỉ để né một vi phạm package. Nếu nghiệp vụ cần kết quả đồng bộ, hãy thiết kế API công khai có hợp đồng rõ. Nếu nghiệp vụ thực sự phù hợp với xử lý theo sự kiện, hãy xác định thêm yêu cầu về giao dịch, thử lại, xử lý trùng và tính nhất quán.

## 7. Quy trình tìm và sửa dependency vi phạm

Khi `ApplicationModules.verify()` báo truy cập package nội bộ, có thể xử lý theo trình tự:

1. **Xác định mô-đun sở hữu kiểu bị truy cập.** Dựa vào package đầy đủ của class trong thông báo vi phạm.
2. **Xác nhận package đó có phải API không.** Kiểm tra nó thuộc package gốc hay một named interface được công khai.
3. **Tìm nơi tạo dependency.** Kiểm tra import, field, constructor, method signature, generic, annotation và quan hệ kế thừa.
4. **Xác định nhu cầu nghiệp vụ thực sự.** Mô-đun gọi cần một thao tác nghiệp vụ, dữ liệu đọc hay thông báo sự kiện?
5. **Đưa hợp đồng vào API công khai.** Tạo hoặc điều chỉnh facade/service contract trong package gốc hoặc named interface phù hợp.
6. **Giữ chi tiết triển khai bên trong.** Chuyển repository và policy về package nội bộ, chỉ cho lớp trong mô-đun sở hữu chúng sử dụng.
7. **Chạy lại kiểm tra kiến trúc và test nghiệp vụ.** Xác nhận dependency vi phạm đã biến mất và hành vi ứng dụng vẫn đúng.

Một thay đổi tốt thường làm dependency hướng tới hợp đồng nghiệp vụ ổn định. Nếu API mới chỉ bọc nguyên xi mọi phương thức của repository, nhóm có thể đã công khai chi tiết triển khai dưới một tên khác; hãy thiết kế hợp đồng theo nhu cầu của bên sử dụng.

## 8. Những nhầm lẫn thường gặp

- **“Class public thì module nào cũng được dùng.”** Java cho phép truy cập ở cấp ngôn ngữ không đồng nghĩa với việc dependency hợp lệ theo ranh giới Spring Modulith.
- **“Chỉ package tên internal mới là nội bộ.”** Theo quy ước, package con không được công khai đều là nội bộ, bất kể tên package.
- **“Đổi tên package là sửa được vi phạm.”** Vi phạm xuất phát từ dependency vượt qua API module, không chỉ từ chữ `internal` trong tên.
- **“Tắt kiểm tra là giải quyết được vấn đề.”** Bỏ kiểm chứng chỉ che giấu dependency; nó không làm ranh giới trở nên đúng hoặc giảm coupling.
- **“Đưa repository vào Named Interface là đủ.”** Việc đó công khai chi tiết persistence. Thông thường nên công khai hợp đồng nghiệp vụ và giữ repository ở bên trong.
- **“Mọi giao tiếp liên mô-đun nên dùng event.”** Chọn API hay event theo yêu cầu về kết quả, thời điểm xử lý và tính nhất quán của nghiệp vụ.

## Kết luận

Truy cập trực tiếp vào package nội bộ của mô-đun khác là vi phạm vì nó tạo phụ thuộc vào chi tiết triển khai nằm ngoài API được công khai. Modifier `public` của Java không thay đổi quy tắc kiến trúc này. Hãy đưa thao tác cần thiết vào package gốc hoặc một `Named Interface`, khai báo dependency được phép khi cần, rồi dùng `ApplicationModules.verify()` để bảo vệ ranh giới giữa các mô-đun trong modular monolith.
