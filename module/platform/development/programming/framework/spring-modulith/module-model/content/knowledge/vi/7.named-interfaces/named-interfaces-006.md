# Module root package và named interface khác nhau thế nào?

Trong Spring Modulith, module root package (còn gọi là module base package) xác định package gốc của một application module và cung cấp API công khai mặc định. Named interface là một package con được công bố rõ ràng như một nhóm API có tên. Cả hai đều có thể chứa hợp đồng mà module khác sử dụng, nhưng chúng có vai trò khác nhau trong mô hình module.

Module root package xác định module và là điểm đặt API mặc định. Named interface mở rộng bề mặt API bằng cách công bố có chủ đích một package con, thường để chia hợp đồng thành các nhóm như `spi`, `events` hoặc `reporting`. Named interface vẫn thuộc module gốc, không tạo thành application module mới.

## 1. Module root package là gì?

Spring Modulith nhận diện application module theo cấu trúc package. Giả sử lớp Spring Boot chính nằm trong `com.acme.shop`. Các package con trực tiếp như `order` và `inventory` được nhận diện là module mặc định:

```text
com.acme.shop                         # application base package
├── ShopApplication.java
├── order                             # module root package: order
└── inventory                         # module root package: inventory
```

Với module `inventory`, package `com.acme.shop.inventory` là module root package. Nó xác định ranh giới module, tên module mặc định và là nơi đặt API công khai mặc định.

Bạn có thể đặt các type API ngay trong root package:

```java
package com.acme.shop.inventory;

public interface StockAvailability {

    boolean isAvailable(String sku, int quantity);
}
```

Module khác có thể phụ thuộc vào `StockAvailability` qua API mặc định của `inventory`. Những implementation, repository và helper chỉ phục vụ nội bộ nên được đặt trong package con như `inventory.internal`.

Metadata của module có thể được khai báo trong `package-info.java` của root package:

```java
@org.springframework.modulith.ApplicationModule(
        displayName = "Quản lý kho"
)
package com.acme.shop.inventory;
```

`@ApplicationModule` mô tả module đã được nhận diện ở package này, chẳng hạn tên hiển thị và các quy tắc phụ thuộc. Annotation không phải điều kiện duy nhất để package trở thành module theo quy ước mặc định.

## 2. Named interface là gì?

Một module có thể cần công bố nhiều nhóm hợp đồng khác nhau. Thay vì đặt tất cả type trong root package, bạn có thể tạo các package con và đánh dấu từng package bằng `@NamedInterface`.

Ví dụ, module `inventory` công bố thêm nhóm SPI:

```text
com.acme.shop.inventory                 # module root package
├── StockAvailability.java              # API mặc định
├── spi                                 # named interface: spi
│   ├── package-info.java
│   └── StockReservation.java
└── internal                            # implementation nội bộ
    └── StockReservationService.java
```

Đánh dấu package `spi` trong file `package-info.java`:

```java
@org.springframework.modulith.NamedInterface("spi")
package com.acme.shop.inventory.spi;
```

Đặt hợp đồng được công bố trong package đó:

```java
package com.acme.shop.inventory.spi;

public interface StockReservation {

    void reserve(String sku, int quantity);
}
```

Package `com.acme.shop.inventory.spi` vẫn nằm bên trong module `inventory`. `@NamedInterface("spi")` cho Spring Modulith biết đây là một phần API có tên để module khác tham chiếu.

## 3. So sánh trực tiếp

| Tiêu chí | Module root package | Named interface |
|---|---|---|
| Vị trí | Package gốc của module, ví dụ `inventory` | Package con, ví dụ `inventory.spi` |
| Vai trò | Xác định module và cung cấp API mặc định | Công bố thêm một nhóm API có tên |
| Khai báo | Được nhận diện theo quy ước package; có thể mô tả bằng `@ApplicationModule` | Đánh dấu rõ bằng `@NamedInterface` trong `package-info.java` |
| Tên | Tên module thường được suy ra từ package root | Tên giao diện do annotation cung cấp, ví dụ `spi` |
| Phạm vi sở hữu | Là gốc của module | Vẫn thuộc module sở hữu package cha |
| Phụ thuộc từ module khác | Tham chiếu module, ví dụ `inventory` | Có thể tham chiếu cụ thể `inventory :: spi` |

Điểm cốt lõi: root package là ranh giới module và API mặc định; named interface là một phần API bổ sung được công bố có tên bên trong ranh giới đó.

## 4. Ví dụ module cung cấp API mặc định và named interface

Module `inventory` cung cấp khả năng kiểm tra hàng tồn trong root package:

```java
package com.acme.shop.inventory;

public interface StockAvailability {

    boolean isAvailable(String sku, int quantity);
}
```

Đồng thời module cung cấp hợp đồng đặt chỗ hàng cho các module tích hợp qua SPI:

```java
package com.acme.shop.inventory.spi;

public interface StockReservation {

    void reserve(String sku, int quantity);
}
```

Package `inventory.spi` được công bố bằng `@NamedInterface("spi")`. Implementation của hai hợp đồng có thể nằm trong `inventory.internal`:

```java
package com.acme.shop.inventory.internal;

import com.acme.shop.inventory.StockAvailability;
import com.acme.shop.inventory.spi.StockReservation;
import org.springframework.stereotype.Service;

@Service
public class InventoryService implements StockAvailability, StockReservation {

    @Override
    public boolean isAvailable(String sku, int quantity) {
        // Kiểm tra tồn kho.
        return true;
    }

    @Override
    public void reserve(String sku, int quantity) {
        // Giữ số lượng hàng.
    }
}
```

Module tiêu thụ chỉ tham chiếu interface cần dùng. Ví dụ, `order` có thể sử dụng `StockAvailability` để kiểm tra hàng và `StockReservation` để yêu cầu giữ hàng. Nó không cần tham chiếu trực tiếp `InventoryService`.

## 5. Khai báo phụ thuộc vào root package hoặc named interface

Nếu module `order` sử dụng API mặc định của `inventory`, có thể khai báo trong `package-info.java` của `order`:

```java
@org.springframework.modulith.ApplicationModule(
        displayName = "Quản lý đơn hàng",
        allowedDependencies = "inventory"
)
package com.acme.shop.order;
```

Nếu module `order` cần phụ thuộc vào named interface `spi`, hãy khai báo cụ thể:

```java
@org.springframework.modulith.ApplicationModule(
        displayName = "Quản lý đơn hàng",
        allowedDependencies = "inventory :: spi"
)
package com.acme.shop.order;
```

Hai khai báo biểu đạt mức độ cụ thể khác nhau:

- `inventory` cho phép phụ thuộc vào API mặc định của module `inventory`.
- `inventory :: spi` xác định named interface `spi` của module `inventory` là hợp đồng mà module tiêu thụ cần dùng.

`allowedDependencies` thể hiện chính sách phụ thuộc giữa các module. Nó không biến package nội bộ thành API công khai và cũng không thay thế việc tham chiếu đúng type được công bố.

## 6. Named interface không phải module con

Đừng nhầm package con được công bố với một module lồng bên trong. Xét cấu trúc:

```text
com.acme.shop
└── inventory                         # module inventory
    ├── StockAvailability.java
    ├── spi                            # named interface spi
    │   ├── package-info.java
    │   └── StockReservation.java
    └── internal                       # package nội bộ
        └── InventoryService.java
```

Trong mô hình mặc định:

- `com.acme.shop.inventory` là module root package và xác định module `inventory`.
- `com.acme.shop.inventory.spi` là package con được công bố như named interface `spi`.
- `com.acme.shop.inventory.internal` là package con triển khai nội bộ.

Hai package `spi` và `internal` đều thuộc module `inventory`. Việc đánh dấu `spi` bằng `@NamedInterface` thay đổi khả năng được module khác sử dụng theo mô hình kiến trúc, không thay đổi module sở hữu package.

Java vẫn xem root package và package con là các package riêng. Quyền truy cập package-private của Java không tự mở rộng từ package cha sang package con. Spring Modulith bổ sung quy tắc kiến trúc ở cấp module; quy tắc này độc lập với access modifier của Java.

## 7. Khi nào nên dùng từng cách?

Dùng API ở module root package khi module có một nhóm hợp đồng chính, tương đối nhỏ và phù hợp cho các module tiêu thụ. Ví dụ, `StockAvailability` là khả năng cốt lõi mà các module khác cần dùng.

Dùng named interface khi module có các nhóm API với mục đích khác nhau hoặc các nhóm người tiêu thụ khác nhau. Ví dụ:

- `inventory.spi`: hợp đồng mở rộng hoặc điểm tích hợp cho module khác.
- `inventory.events`: các kiểu sự kiện nghiệp vụ được công bố.
- `inventory.reporting`: hợp đồng truy vấn phục vụ báo cáo.

Không cần tạo named interface chỉ để chia thư mục cho gọn. Một package con chỉ trở thành named interface khi được công bố rõ bằng annotation. Các package `internal`, `persistence` hoặc `web` vẫn nên là phần triển khai nội bộ nếu module không có chủ đích cung cấp chúng làm API.

## 8. Kiểm chứng ranh giới bằng ApplicationModules

Bạn có thể xác minh mô hình module và phụ thuộc bằng `ApplicationModules.verify()`:

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

Hãy thử các trường hợp sau:

1. Module `order` import `StockAvailability` từ module root package `inventory`.
2. Module `order` import `StockReservation` từ named interface `inventory.spi` và khai báo `allowedDependencies = "inventory :: spi"`.
3. Module `order` import trực tiếp một service trong `inventory.internal`.

`verify()` có thể phát hiện việc truy cập package nội bộ hoặc phụ thuộc không phù hợp với metadata đã khai báo. Nếu kiểm thử thất bại, hãy xác định module nguồn, module đích và type/package bị tham chiếu, rồi điều chỉnh hợp đồng hoặc quy tắc phụ thuộc.

Kiểm thử kiến trúc xác nhận cấu trúc code tuân theo ranh giới đã khai báo. Nó không thay thế kiểm thử Spring để xác nhận bean được tạo và inject đúng, cũng không tự quyết định một hợp đồng có hợp lý về mặt nghiệp vụ hay không.

## 9. Bài tập thực hành

Với ứng dụng `com.acme.shop`, hãy xây dựng module `inventory` có API mặc định và một named interface:

1. Đặt `StockAvailability` trong `com.acme.shop.inventory`.
2. Tạo package `com.acme.shop.inventory.spi` và khai báo `@NamedInterface("spi")` trong `package-info.java`.
3. Đặt interface `StockReservation` trong package `spi`.
4. Đặt implementation của hai interface trong `com.acme.shop.inventory.internal`.
5. Khai báo module `order` chỉ phụ thuộc `inventory` và inject `StockAvailability`.
6. Chuyển một use case sang `StockReservation` và khai báo `allowedDependencies = "inventory :: spi"`.
7. Thử import một implementation từ `inventory.internal`, rồi chạy `ApplicationModules.verify()` để quan sát vi phạm.
8. Viết báo cáo ngắn giải thích package nào xác định module, package nào là API mặc định và package nào là named interface.

Sau bài tập, hãy tự trả lời: nếu xóa annotation `@NamedInterface("spi")`, điều gì thay đổi trong mô hình công khai? Package `spi` có trở thành module mới không? Vì sao module root package vẫn quan trọng ngay cả khi module đã có nhiều named interface?

## 10. Ghi nhớ

- Module root package (module base package) xác định application module và cung cấp API công khai mặc định.
- `@NamedInterface` công bố một package con thành nhóm API có tên.
- Named interface vẫn thuộc module root package sở hữu nó; nó không tạo application module mới.
- `allowedDependencies = "inventory"` tham chiếu API mặc định của module `inventory`.
- `allowedDependencies = "inventory :: spi"` tham chiếu named interface `spi` của module `inventory`.
- Package nội bộ không trở thành API chỉ vì type Java là `public` hoặc được Spring quản lý như bean.
- Dùng `ApplicationModules.verify()` để kiểm tra việc sử dụng API và quy tắc phụ thuộc giữa các module.

Hiểu rõ sự khác nhau giữa module root package và named interface giúp bạn xác định đúng ranh giới sở hữu, công bố các nhóm hợp đồng có chủ đích và duy trì phụ thuộc rõ ràng trong modular monolith.
