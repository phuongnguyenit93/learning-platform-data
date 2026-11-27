# Kiểm tra type thuộc named interface nào

Khi một application module công khai nhiều nhóm API, chỉ nhìn tên package đôi khi chưa đủ để xác định một type thuộc hợp đồng nào. Spring Modulith mô hình hóa các nhóm đó bằng `NamedInterface`. Ta có thể dùng mô hình `ApplicationModules` để tìm module sở hữu type, sau đó kiểm tra từng named interface xem nó có chứa type đó hay không.

Điều cần nhớ là **named interface là một nhóm type trong hợp đồng kiến trúc của application module**. Nó không nhất thiết là một Java `interface`. Một nhóm có thể được tạo từ package được đánh dấu bằng `@NamedInterface`, hoặc từ các type được đánh dấu cùng tên.

## 1. Mỗi module có default interface và named interface tường minh

Giả sử ứng dụng có module `inventory`:

```text
com.example.shop.inventory
├── StockAvailability.java
├── api
│   ├── package-info.java
│   └── StockReservation.java
├── spi
│   └── ReservationPolicy.java
└── internal
    └── StockRepository.java
```

Theo quy ước mặc định:

- Các type nằm trực tiếp trong base package `com.example.shop.inventory` thuộc **unnamed interface** (default interface) của module.
- Package `api` có thể được công khai thành named interface tên `api`.
- Type `ReservationPolicy` có thể được đưa vào named interface tên `spi` bằng annotation đặt trực tiếp trên type.
- Package `internal` không được công khai nếu không có khai báo named interface tương ứng.

Ví dụ, `inventory/api/package-info.java` khai báo:

```java
@org.springframework.modulith.NamedInterface("api")
package com.example.shop.inventory.api;
```

Và type có thể được gắn vào một named interface theo cách khác:

```java
package com.example.shop.inventory.spi;

@org.springframework.modulith.NamedInterface("spi")
public interface ReservationPolicy {

    boolean canReserve(String sku, int quantity);
}
```

Trong trường hợp đầu, annotation trên package đưa các type thuộc package `api` vào named interface `api`. Trong trường hợp thứ hai, annotation trên type đưa `ReservationPolicy` vào named interface `spi`. Các type được đánh dấu cùng tên sẽ được nhóm vào cùng named interface của module.

## 2. Tìm module sở hữu type trước

Muốn biết một type thuộc named interface nào, trước hết cần xác định application module chứa type đó. `ApplicationModules.getModuleByType(Class<?>)` trả về `Optional<ApplicationModule>` tương ứng với module sở hữu type.

```java
import com.example.shop.ShopApplication;
import com.example.shop.inventory.api.StockReservation;
import java.util.Optional;

import org.springframework.modulith.core.ApplicationModule;
import org.springframework.modulith.core.ApplicationModules;

ApplicationModules modules = ApplicationModules.of(ShopApplication.class);

Optional<ApplicationModule> owner =
        modules.getModuleByType(StockReservation.class);
```

Nếu `owner` rỗng, Spring Modulith không tìm thấy application module chứa type trong mô hình hiện tại. Hãy kiểm tra package của type, application root package và chiến lược phát hiện module. Một type ở ngoài phạm vi module không thể được kết luận là thuộc named interface của một module.

Nếu tìm thấy module, ta có thể đọc các named interface mà module công khai bằng `ApplicationModule.getNamedInterfaces()`.

## 3. Dùng NamedInterface.contains(Class<?>) để xác định chính xác

API `NamedInterface` cung cấp `contains(Class<?>)`. Cách đáng tin cậy là duyệt các interface của module sở hữu và lọc những interface chứa chính type cần kiểm tra:

```java
import com.example.shop.ShopApplication;
import com.example.shop.inventory.api.StockReservation;
import java.util.List;

import org.springframework.modulith.core.ApplicationModule;
import org.springframework.modulith.core.ApplicationModules;
import org.springframework.modulith.core.NamedInterface;

ApplicationModules modules = ApplicationModules.of(ShopApplication.class);
Class<?> candidateType = StockReservation.class;

ApplicationModule owner = modules.getModuleByType(candidateType)
        .orElseThrow(() -> new IllegalArgumentException(
                "Type không thuộc application module nào"));

List<NamedInterface> matches = owner.getNamedInterfaces().stream()
        .filter(namedInterface -> namedInterface.contains(candidateType))
        .toList();

System.out.println("Module: " + owner.getName());

if (matches.isEmpty()) {
    System.out.println("Type không thuộc named interface được công khai nào.");
} else {
    for (NamedInterface namedInterface : matches) {
        String name = namedInterface.isUnnamed()
                ? "unnamed (default interface)"
                : namedInterface.getName();

        System.out.println("Named interface: " + name);
    }
}
```

Đoạn mã thực hiện ba bước:

1. `getModuleByType(candidateType)` tìm module sở hữu type.
2. `getNamedInterfaces().stream()` lấy các named interface của module đó.
3. `contains(candidateType)` kiểm tra type có nằm trong từng interface hay không.

`isUnnamed()` giúp phân biệt default interface với named interface được khai báo tường minh. Với default interface, không nên suy ra tên kỹ thuật từ display name của module; hãy kiểm tra bằng `isUnnamed()`.

## 4. Diễn giải kết quả

Giả sử module `inventory` có ba nhóm API:

| Type cần kiểm tra | Vị trí khai báo | Kết quả mong đợi |
|---|---|---|
| `StockAvailability` | Trực tiếp trong `com.example.shop.inventory` | Unnamed interface (default) |
| `StockReservation` | Trong package được đánh dấu `@NamedInterface("api")` | Named interface `api` |
| `ReservationPolicy` | Được đánh dấu `@NamedInterface("spi")` trên type | Named interface `spi` |
| `StockRepository` | Trong `inventory.internal`, không có annotation công khai | Không thuộc named interface công khai nào |

Hai trường hợp cuối cần được phân biệt cẩn thận: một type có thể thuộc module nhưng vẫn là internal. Nếu `getModuleByType()` tìm thấy module mà danh sách `matches` rỗng, điều đó thường cho biết type chưa nằm trong bất kỳ named interface nào được module công khai. Nó không có nghĩa type không tồn tại hoặc không thuộc module.

Nếu `getModuleByType()` không tìm thấy module, hãy kiểm tra xem type có nằm ngoài application root package, ở package không được phát hiện, hoặc bị loại khỏi mô hình bởi cấu hình discovery hay không.

Thông thường một type được mong đợi nằm trong một named interface. Nếu danh sách `matches` có nhiều phần tử, hãy kiểm tra cách các package và type được đánh dấu, cũng như chiến lược phát hiện named interface tùy chỉnh; đừng tự chọn phần tử đầu tiên rồi bỏ qua các kết quả còn lại.

## 5. Dùng kết quả để khai báo allowedDependencies

Khi một module khác cần sử dụng type thuộc named interface, tên dependency phải trỏ tới đúng module và named interface. Ví dụ, nếu `orders` cần dùng `StockReservation` thuộc `inventory::api`, có thể khai báo trong `package-info.java` của `orders`:

```java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "inventory::api"
)
package com.example.shop.orders;
```

Cú pháp `moduleName::namedInterfaceName` xác định chính xác hợp đồng mà module gọi được phép sử dụng. Nếu type nằm trong unnamed interface của `inventory`, dependency có thể được khai báo bằng tên module `inventory`.

Việc kiểm tra type trước giúp tránh khai báo nhầm `inventory::api` trong khi type thực tế nằm trong default interface, hoặc cho phép cả module khi bên gọi chỉ cần một nhóm API cụ thể.

## 6. Kiểm tra named interface trong bài test kiến trúc

Ta có thể biến kỳ vọng về vị trí API thành kiểm thử để phát hiện khi ai đó di chuyển type hoặc thay đổi annotation:

```java
package com.example.shop;

import static org.junit.jupiter.api.Assertions.assertTrue;

import com.example.shop.inventory.api.StockReservation;
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModule;
import org.springframework.modulith.core.ApplicationModules;

class NamedInterfaceTests {

    @Test
    void stockReservationBelongsToInventoryApi() {
        ApplicationModules modules = ApplicationModules.of(ShopApplication.class);

        ApplicationModule inventory = modules.getModuleByType(StockReservation.class)
                .orElseThrow();

        boolean exposedThroughApi = inventory.getNamedInterfaces().stream()
                .anyMatch(namedInterface ->
                        namedInterface.isNamed()
                                && namedInterface.getName().equals("api")
                                && namedInterface.contains(StockReservation.class));

        assertTrue(exposedThroughApi);
    }
}
```

Kiểm thử này xác nhận đồng thời type thuộc module `inventory`, interface có tên `api` và interface đó thực sự chứa type. Nếu chỉ kiểm tra `getName()` mà không gọi `contains()`, ta mới biết module có một interface tên `api`, chứ chưa biết type đang xét có thuộc interface ấy hay không.

## 7. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu chính xác |
|---|---|
| Named interface luôn là một Java `interface` | Đây là nhóm type công khai của module; có thể được tạo từ package hoặc các type được đánh dấu |
| Mọi sub-package đều tự động là named interface | Sub-package mặc định là nội bộ cho đến khi được công khai bằng cơ chế phù hợp |
| Type ở package gốc thuộc named interface có tên `api` | Type ở base package thuộc unnamed interface theo mặc định |
| Chỉ cần xem tên package để kết luận type thuộc interface nào | Dùng `NamedInterface.contains(Class<?>)` để kiểm tra membership của chính type |
| Không tìm thấy named interface nghĩa là type không thuộc module | Type có thể thuộc module nhưng vẫn là internal |

Hãy bắt đầu bằng `getModuleByType()`, sau đó kiểm tra `getNamedInterfaces()` và `contains()`. Cách làm này cho biết rõ type thuộc module nào, được công khai qua named interface nào, hay vẫn là chi tiết nội bộ cần được giữ kín.

Tài liệu API tham khảo: [ApplicationModules](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModules.html), [NamedInterfaces](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/NamedInterfaces.html) và [NamedInterface](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/NamedInterface.html).
