# Injection trực tiếp vào module khác

Trong một ứng dụng Spring Boot được chia thành nhiều application module, một module có thể cần gọi nghiệp vụ do module khác cung cấp. Cách quen thuộc là inject một Spring bean qua constructor. Spring xử lý việc tạo và kết nối bean; Spring Modulith mô hình hóa quan hệ phụ thuộc giữa các module và kiểm tra xem kiểu được inject có thuộc API mà module cung cấp hay không.

Ví dụ, module `shipping` cần biết một mặt hàng có đủ tồn kho trước khi tạo lệnh giao hàng. Module `inventory` có thể cung cấp một bean thực hiện thao tác đó. Điểm quan trọng là module gọi chỉ phụ thuộc vào hợp đồng công khai của `inventory`, còn cách triển khai vẫn nằm bên trong module sở hữu nó.

## 1. Spring bean và ranh giới module

Spring Modulith xác định module dựa trên cấu trúc package của ứng dụng. Giả sử ứng dụng có package gốc `com.example` và hai module:

```text
com.example
├── Application.java
├── inventory
│   ├── InventoryOperations.java
│   └── internal
│       └── InventoryService.java
└── shipping
    └── ShippingService.java
```

Trong cấu trúc mặc định:

- `com.example.inventory` là package gốc của module `inventory`. Các kiểu được đặt trực tiếp trong package này thuộc API công khai mặc định của module.
- `com.example.inventory.internal` là package con. Package này được xem là nội bộ và không tự động trở thành API cho module khác.
- `com.example.shipping` là package gốc của module `shipping`.

Spring component scan vẫn có thể phát hiện `@Service` trong package `internal` và đăng ký bean trong ApplicationContext. Việc một bean tồn tại trong ApplicationContext không đồng nghĩa mọi module đều được phép phụ thuộc trực tiếp vào kiểu triển khai của bean đó. Ranh giới module được kiểm tra riêng bằng mô hình kiến trúc của Spring Modulith.

## 2. Inject qua kiểu API công khai

Module `inventory` khai báo một hợp đồng công khai tại package gốc:

```java
package com.example.inventory;

public interface InventoryOperations {

    boolean isAvailable(String sku, int quantity);
}
```

Phần triển khai được đặt trong package nội bộ:

```java
package com.example.inventory.internal;

import com.example.inventory.InventoryOperations;
import org.springframework.stereotype.Service;

@Service
public class InventoryService implements InventoryOperations {

    @Override
    public boolean isAvailable(String sku, int quantity) {
        // Tra cứu tồn kho và áp dụng quy tắc của module inventory.
        return true;
    }
}
```

Ví dụ dùng `return true` để tập trung vào cách kết nối bean. Trong ứng dụng thực tế, phương thức này cần đọc dữ liệu tồn kho và áp dụng quy tắc nghiệp vụ của module `inventory`.

Module `shipping` inject interface công khai bằng constructor:

```java
package com.example.shipping;

import com.example.inventory.InventoryOperations;
import org.springframework.stereotype.Service;

@Service
public class ShippingService {

    private final InventoryOperations inventory;

    public ShippingService(InventoryOperations inventory) {
        this.inventory = inventory;
    }

    public void prepareShipment(String sku, int quantity) {
        if (!inventory.isAvailable(sku, quantity)) {
            throw new IllegalStateException("Không đủ hàng trong kho");
        }

        // Tiếp tục quy trình chuẩn bị giao hàng của module shipping.
    }
}
```

Spring tìm bean triển khai `InventoryOperations` và truyền bean đó vào `ShippingService`. Module `shipping` chỉ biết interface công khai; nó không cần import hoặc biết `InventoryService` được triển khai ra sao.

Constructor injection làm rõ phụ thuộc bắt buộc của bean, giúp lớp dễ kiểm thử và tránh phụ thuộc ẩn qua field injection. Interface cũng tạo điểm ổn định để module `inventory` có thể thay đổi cách truy cập dữ liệu mà không buộc module `shipping` sửa theo, miễn là hợp đồng công khai vẫn giữ nguyên.

## 3. Khai báo module được phép phụ thuộc

Nếu muốn giới hạn các module mà `shipping` được phép sử dụng, khai báo `allowedDependencies` trong `package-info.java` của module:

```java
@org.springframework.modulith.ApplicationModule(
        allowedDependencies = "inventory"
)
package com.example.shipping;
```

Giá trị `inventory` là tên module đích. Quy tắc này cho phép `shipping` phụ thuộc vào module `inventory`; nó không mở toàn bộ package nội bộ của `inventory` thành API công khai. Việc truy cập vẫn phải tuân theo ranh giới package và các named interface mà module đích công bố.

Nếu module không khai báo `allowedDependencies`, Spring Modulith vẫn kiểm tra các quy tắc cấu trúc như phụ thuộc vòng tròn và truy cập API nội bộ. `allowedDependencies` bổ sung danh sách giới hạn rõ ràng cho các phụ thuộc giữa module.

## 4. Công khai API qua named interface

Không nhất thiết phải đặt mọi kiểu API trong package gốc của module. Khi muốn tổ chức API trong một package riêng, có thể đánh dấu package đó bằng `@NamedInterface`.

Ví dụ chuyển hợp đồng sang `com.example.inventory.api` và tạo file `package-info.java`:

```java
@org.springframework.modulith.NamedInterface("api")
package com.example.inventory.api;
```

Interface được khai báo trong package này:

```java
package com.example.inventory.api;

public interface InventoryOperations {

    boolean isAvailable(String sku, int quantity);
}
```

Module khác có thể import kiểu từ named interface này. Nếu muốn giới hạn `shipping` chỉ được phụ thuộc vào named interface `api` của `inventory`, khai báo:

```java
@org.springframework.modulith.ApplicationModule(
        allowedDependencies = "inventory::api"
)
package com.example.shipping;
```

Cú pháp `inventory::api` chỉ rõ module và named interface được phép sử dụng. Khi tổ chức API theo cách này, implementation vẫn nên nằm trong package nội bộ, chẳng hạn `com.example.inventory.internal`, và triển khai interface `com.example.inventory.api.InventoryOperations`.

## 5. Điều gì xảy ra nếu inject trực tiếp implementation nội bộ?

Giả sử `ShippingService` import `com.example.inventory.internal.InventoryService` và khai báo constructor nhận kiểu `InventoryService`. Nếu lớp triển khai được khai báo `public`, Java có thể cho phép tham chiếu đó, và Spring có thể tìm thấy bean tương ứng. Tuy nhiên, module `shipping` lúc này phụ thuộc trực tiếp vào một kiểu thuộc package nội bộ của `inventory`.

Spring Modulith xem đây là vi phạm tính đóng gói module. Lời gọi `ApplicationModules.verify()` có thể phát hiện phụ thuộc đến package nội bộ trong quá trình kiểm tra kiến trúc, dù ApplicationContext có thể khởi tạo được các bean. Vì vậy, một ứng dụng chạy được chưa chắc đã tuân thủ ranh giới module.

Hãy chuyển kiểu được inject sang API công khai hoặc named interface. Nếu nghiệp vụ thực sự cần dùng một khả năng mới, module sở hữu khả năng đó nên bổ sung phương thức vào hợp đồng công khai phù hợp. Tránh đưa repository, entity nội bộ hoặc service triển khai vào API chỉ để module khác tiện truy cập.

## 6. Kiểm chứng quan hệ phụ thuộc

Có thể tạo một bài kiểm tra kiến trúc để kiểm tra mô hình module:

```java
package com.example;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void moduleDependenciesRespectTheirBoundaries() {
        ApplicationModules.of(Application.class).verify();
    }
}
```

Khi chạy test, Spring Modulith phân tích các module và báo lỗi nếu phát hiện phụ thuộc không hợp lệ, chẳng hạn module truy cập package nội bộ của module khác hoặc vi phạm danh sách `allowedDependencies`.

Trong ví dụ này, test kiểm tra cả phụ thuộc được tạo bởi tham chiếu kiểu trong constructor của `ShippingService`. Nếu thay `InventoryOperations` bằng `InventoryService`, kiểm tra kiến trúc sẽ phát hiện việc module `shipping` sử dụng implementation nội bộ.

## 7. Khi nào nên dùng injection trực tiếp?

Injection trực tiếp phù hợp khi module cần một kết quả đồng bộ để tiếp tục xử lý, ví dụ `shipping` cần kiểm tra tồn kho ngay trước khi chuẩn bị giao hàng. Hợp đồng công khai giúp lời gọi có ý nghĩa rõ ràng và cho phép Spring quản lý vòng đời bean.

Nếu module chỉ cần thông báo một sự kiện đã xảy ra và không cần gọi đồng bộ để nhận kết quả, có thể cân nhắc Spring application event. Ví dụ, `inventory` phát sự kiện khi mức tồn kho thay đổi và module khác đăng ký xử lý. Cách giao tiếp này giảm sự phụ thuộc trực tiếp giữa bên phát và bên nhận, nhưng có ngữ nghĩa xử lý và nhất quán dữ liệu khác với một lời gọi bean đồng bộ.

| Nhu cầu | Cách giao tiếp phù hợp |
|---|---|
| Cần kết quả ngay để quyết định bước tiếp theo | Inject bean qua API công khai |
| Muốn tổ chức API trong package riêng | Inject kiểu thuộc named interface |
| Chỉ cần thông báo một sự kiện để module khác tự xử lý | Phát application event |
| Muốn gọi trực tiếp service hoặc repository nội bộ của module khác | Thiết kế lại API công khai của module sở hữu |

## 8. Bài tập thực hành

1. Tạo hai module `inventory` và `shipping` dưới package gốc của ứng dụng.
2. Đặt `InventoryOperations` trong package gốc của `inventory`, còn `InventoryService` trong package `inventory.internal`.
3. Inject `InventoryOperations` vào `ShippingService` bằng constructor và gọi nó trong một thao tác nghiệp vụ.
4. Khai báo `allowedDependencies = "inventory"` cho module `shipping`.
5. Chạy bài kiểm tra `ApplicationModules.of(Application.class).verify()` để xác nhận cấu trúc hợp lệ.
6. Thử tham chiếu trực tiếp `InventoryService` từ `shipping`, sau đó quan sát vi phạm kiến trúc và khôi phục phụ thuộc qua interface công khai.
7. Chuyển interface sang package `inventory.api`, đánh dấu package bằng `@NamedInterface("api")` và giới hạn phụ thuộc bằng `inventory::api`.

Sau bài tập, bạn cần giải thích được vì sao Spring có thể inject một bean nhưng Spring Modulith vẫn có thể từ chối quan hệ phụ thuộc đó về mặt kiến trúc. Đây là điểm cốt lõi khi kết hợp Spring dependency injection với ranh giới của modular monolith.

## Tài liệu tham khảo

- [Application Modules – Spring Modulith Reference](https://docs.spring.io/spring-modulith/reference/fundamentals.html)
- [Verification of Application Module Structure – Spring Modulith Reference](https://docs.spring.io/spring-modulith/reference/verification.html)
- [ApplicationModule API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/ApplicationModule.html)
- [NamedInterface API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/NamedInterface.html)
