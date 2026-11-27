# Spring bean được module cung cấp

Trong một ứng dụng Spring Boot theo kiến trúc modular monolith, mỗi application module có thể cung cấp các Spring bean để module khác sử dụng. Spring quản lý vòng đời và dependency injection của các bean trong application context, còn Spring Modulith giúp xác định module nào đang sử dụng kiểu nào và kiểm tra việc sử dụng đó có đi qua API được công bố hay không.

Điểm quan trọng là một bean có thể được Spring tạo và inject thành công về mặt kỹ thuật nhưng vẫn tạo ra phụ thuộc kiến trúc không hợp lệ. Vì vậy, khi cung cấp bean cho module khác, hãy công bố một kiểu API ổn định ở module base package hoặc named interface, rồi giữ lớp triển khai ở package nội bộ.

## 1. Spring bean và application module

Spring bean là đối tượng được Spring IoC container quản lý. Bean thường được đăng ký bằng các annotation như `@Component`, `@Service`, `@Repository`, hoặc bằng phương thức `@Bean` trong một lớp `@Configuration`. Các bean có thể nhận dependency qua constructor, setter hoặc field injection.

Spring Modulith nhóm các package của ứng dụng thành application module. Theo quy ước mặc định:

- Package gốc chứa lớp ứng dụng là application base package.
- Mỗi package con trực tiếp của package gốc tạo thành một application module.
- Module base package là phần API công khai mặc định của module.
- Các package con của module thuộc cùng module nhưng được xem là phần triển khai nội bộ, trừ khi được công bố bằng named interface.

Ví dụ, ứng dụng có cấu trúc:

```text
com.acme.shop
├── ShopApplication.java
├── order
│   └── internal
│       └── OrderPlacementService.java
└── inventory
    ├── StockAvailability.java
    └── internal
        └── StockAvailabilityService.java
```

Ở đây, `order` và `inventory` là hai module. `com.acme.shop.inventory.StockAvailability` nằm trong module base package nên có thể đóng vai trò hợp đồng công khai. `StockAvailabilityService` nằm trong package `internal`, do đó là chi tiết triển khai của module `inventory`.

## 2. Cung cấp bean qua một kiểu API công khai

Giả sử module `inventory` cung cấp khả năng kiểm tra số lượng hàng tồn để module `order` kiểm tra trước khi xác nhận đơn hàng. Hãy định nghĩa hợp đồng trong module base package:

```java
package com.acme.shop.inventory;

public interface StockAvailability {

    boolean isAvailable(String sku, int quantity);
}
```

Module `inventory` triển khai hợp đồng bằng một Spring bean trong package nội bộ:

```java
package com.acme.shop.inventory.internal;

import com.acme.shop.inventory.StockAvailability;
import org.springframework.stereotype.Service;

@Service
public class StockAvailabilityService implements StockAvailability {

    @Override
    public boolean isAvailable(String sku, int quantity) {
        // Truy vấn kho và kiểm tra số lượng thực tế.
        return true;
    }
}
```

Module `order` chỉ phụ thuộc vào interface công khai:

```java
package com.acme.shop.order.internal;

import com.acme.shop.inventory.StockAvailability;
import org.springframework.stereotype.Service;

@Service
public class OrderPlacementService {

    private final StockAvailability stockAvailability;

    public OrderPlacementService(StockAvailability stockAvailability) {
        this.stockAvailability = stockAvailability;
    }

    public void placeOrder(String sku, int quantity) {
        if (!stockAvailability.isAvailable(sku, quantity)) {
            throw new IllegalStateException("Không đủ hàng trong kho");
        }

        // Tiếp tục xử lý đơn hàng.
    }
}
```

Spring tìm bean có kiểu phù hợp để inject vào constructor. Bean thực tế là `StockAvailabilityService`, nhưng module `order` chỉ biết đến `StockAvailability`. Nhờ vậy, module `inventory` có thể thay đổi cách truy vấn kho hoặc thay thế lớp triển khai mà không buộc module `order` phụ thuộc vào chi tiết nội bộ.

Đây là cách tổ chức nên ưu tiên khi module muốn cung cấp một dịch vụ đồng bộ cho module khác: hợp đồng thể hiện khả năng nghiệp vụ, còn implementation chịu trách nhiệm thực thi khả năng đó.

## 3. Bean nội bộ không tự động trở thành API

Spring Boot thường component-scan từ package của lớp `@SpringBootApplication` xuống các package con. Do đó, bean được khai báo trong `inventory.internal` vẫn có thể được phát hiện và đăng ký vào application context. Spring Modulith không tạo một Spring application context riêng cho từng module và cũng không tự ngăn mọi lệnh inject bean nội bộ.

Ví dụ, nếu `OrderPlacementService` phụ thuộc trực tiếp vào `StockAvailabilityService`, ứng dụng có thể vẫn khởi động được vì Spring tìm thấy bean:

```java
package com.acme.shop.order.internal;

import com.acme.shop.inventory.internal.StockAvailabilityService;
import org.springframework.stereotype.Service;

@Service
public class OrderPlacementService {

    private final StockAvailabilityService stockAvailabilityService;

    public OrderPlacementService(
            StockAvailabilityService stockAvailabilityService) {
        this.stockAvailabilityService = stockAvailabilityService;
    }
}
```

Tuy nhiên, đây là phụ thuộc trực tiếp từ module `order` vào package nội bộ của module `inventory`. Phụ thuộc như vậy vi phạm ranh giới module theo quy ước mặc định của Spring Modulith. Nó cũng khiến module gọi bị ràng buộc với cách triển khai cụ thể của module được gọi.

Hãy phân biệt hai câu hỏi:

| Câu hỏi | Thành phần trả lời |
|---|---|
| Bean có được tạo và inject trong Spring không? | Spring IoC container, component scanning và cấu hình bean |
| Module có được phép phụ thuộc vào kiểu bean đó không? | Mô hình module và quy tắc kiến trúc của Spring Modulith |

Việc Spring inject thành công không thay thế cho việc kiểm tra kiến trúc. Hãy để module khác tham chiếu kiểu API đã công bố và dùng kiểm thử kiến trúc để phát hiện các phụ thuộc đi vào package nội bộ.

## 4. Công bố bean qua named interface

Đôi khi module cần nhóm API trong một package con thay vì đặt tất cả kiểu công khai tại module base package. Bạn có thể công bố package đó bằng `@NamedInterface`.

Ví dụ, module `inventory` cung cấp một nhóm hợp đồng SPI trong package `inventory.spi`. Khai báo named interface trong `package-info.java`:

```java
@org.springframework.modulith.NamedInterface("stock")
package com.acme.shop.inventory.spi;
```

Đặt kiểu hợp đồng tại package này:

```java
package com.acme.shop.inventory.spi;

public interface StockReservation {

    void reserve(String sku, int quantity);
}
```

Một Spring bean trong module `inventory` có thể triển khai hợp đồng đó, còn module tiêu thụ sẽ inject qua kiểu `StockReservation`. Package `inventory.spi` vẫn thuộc module `inventory`; named interface chỉ công bố một phần API có tên để các module khác sử dụng có chủ đích.

Khi dùng named interface, hãy giữ tên và phạm vi của nó ổn định. Chỉ đưa các kiểu cần chia sẻ vào package được công bố. Những repository, entity hoặc helper chỉ phục vụ nội bộ vẫn nên ở package nội bộ để tránh mở rộng API không cần thiết.

## 5. Kiểm tra phụ thuộc giữa các module

Spring Modulith cung cấp `ApplicationModules` để khám phá cấu trúc module và kiểm tra các quy tắc phụ thuộc. Có thể viết một bài kiểm thử kiến trúc như sau:

```java
package com.acme.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void verifiesModuleStructure() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
```

Với ví dụ trên, module `order` tham chiếu `StockAvailability` trong API của `inventory`, nên phụ thuộc đi qua package được công bố. Nếu đổi injection point sang `StockAvailabilityService` trong `inventory.internal`, mô hình có thể phát hiện truy cập vào kiểu nội bộ và báo vi phạm khi chạy `verify()`.

Khi kiểm tra thất bại, hãy đọc thông báo để xác định module gọi, module được gọi và kiểu đang bị tham chiếu. Sau đó:

1. Xác định kiểu đó có phải hợp đồng mà module đích muốn cung cấp không.
2. Nếu có, chuyển hợp đồng vào module base package hoặc một named interface phù hợp.
3. Cập nhật bean triển khai để implement hợp đồng công khai.
4. Chuyển constructor injection của module gọi sang kiểu công khai.
5. Chạy lại kiểm thử kiến trúc để xác nhận phụ thuộc đã đi qua API.

`ApplicationModules.verify()` tập trung kiểm tra mô hình và các quy tắc kiến trúc. Nó không thay thế các kiểm thử Spring cần thiết để xác nhận bean thực tế được đăng ký, có thể inject và hoạt động đúng trong application context.

## 6. Một số lưu ý khi thiết kế bean API

- **Dùng constructor injection.** Dependency của một service được thể hiện rõ qua constructor, giúp dễ đọc, dễ kiểm thử và dễ nhận diện phụ thuộc giữa module.
- **Công bố hợp đồng nghiệp vụ.** Interface như `StockAvailability` mô tả khả năng mà module cung cấp. Tránh công bố repository hoặc lớp truy cập dữ liệu nếu đó không phải hợp đồng tích hợp dự kiến.
- **Giữ implementation trong package nội bộ.** Các lớp `@Service`, `@Repository` và helper chỉ phục vụ triển khai nên nằm trong package con của module.
- **Chú ý kiểu trả về của `@Bean`.** Nếu đăng ký bean bằng phương thức `@Bean`, hãy thiết kế kiểu được module khác tham chiếu là kiểu API công khai. Lớp cấu hình và chi tiết tạo bean có thể được giữ trong package nội bộ.
- **Phân biệt API với lựa chọn bean.** `@Qualifier` và `@Primary` giúp Spring chọn bean khi có nhiều ứng viên; chúng không công bố package nội bộ thành API và không thay thế quy tắc module.
- **Giới hạn phụ thuộc có chủ đích.** Nếu module chỉ nên sử dụng một số module khác, có thể khai báo quy tắc phụ thuộc bằng cơ chế `allowedDependencies` của Spring Modulith và kiểm tra bằng `verify()`.

## 7. Bài tập thực hành

Hãy xây dựng hai module `order` và `inventory` trong ứng dụng `com.acme.shop`.

1. Tạo interface `StockAvailability` trong `com.acme.shop.inventory`.
2. Tạo `StockAvailabilityService` có annotation `@Service` trong `com.acme.shop.inventory.internal` và triển khai interface trên.
3. Tạo `OrderPlacementService` trong `com.acme.shop.order.internal`; inject `StockAvailability` qua constructor.
4. Chạy `ApplicationModules.of(ShopApplication.class).verify()` và quan sát mô hình phụ thuộc.
5. Thử đổi kiểu dependency trong `OrderPlacementService` thành `StockAvailabilityService`. Chạy lại kiểm thử để quan sát vi phạm do truy cập package nội bộ.
6. Khôi phục dependency về `StockAvailability` và xác nhận kiểm thử kiến trúc thành công.
7. Nếu cần cung cấp một nhóm hợp đồng ở package con, tạo named interface, chuyển interface vào package đó và thử sử dụng từ module gọi.

Sau khi hoàn thành, hãy tự giải thích vì sao Spring có thể inject một bean nội bộ nhưng Spring Modulith vẫn có thể báo phụ thuộc không hợp lệ.

## 8. Ghi nhớ

- Spring quản lý bean và dependency injection trong application context; Spring Modulith mô hình hóa ranh giới và phụ thuộc giữa các application module.
- Một module cung cấp bean cho module khác thông qua kiểu API công khai trong module base package hoặc named interface.
- Lớp triển khai có thể nằm trong package nội bộ và được Spring quản lý, trong khi module tiêu thụ chỉ phụ thuộc vào interface công khai.
- Inject trực tiếp kiểu thuộc package nội bộ có thể chạy được về mặt Spring nhưng vi phạm quy tắc kiến trúc của module.
- Dùng `ApplicationModules.of(ShopApplication.class).verify()` để kiểm tra phụ thuộc, đồng thời dùng kiểm thử Spring phù hợp để xác nhận bean được đăng ký và hoạt động đúng.

Thiết kế bean API rõ ràng giúp các module giao tiếp qua hợp đồng nghiệp vụ ổn định, giữ quyền thay đổi triển khai bên trong và duy trì cấu trúc modular monolith có thể kiểm chứng.
