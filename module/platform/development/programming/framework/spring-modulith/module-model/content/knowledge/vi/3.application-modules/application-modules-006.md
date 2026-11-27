# Đọc system name và metadata toàn ứng dụng

Trong Spring Modulith, `ApplicationModules` tạo ra mô hình kiến trúc của toàn ứng dụng từ lớp Spring Boot chính. Mô hình này cho phép đọc tên hệ thống, liệt kê các application module và xem những thông tin mô tả cũng như quy tắc phụ thuộc đã khai báo cho từng module.

Khả năng đọc metadata hữu ích khi bạn muốn kiểm tra cấu trúc ứng dụng bằng code, tạo báo cáo kiến trúc hoặc hỗ trợ công cụ nội bộ. Thay vì tự suy luận tên module từ đường dẫn thư mục, hãy để Spring Modulith xây dựng mô hình từ package và metadata khai báo trong mã nguồn.

## 1. ApplicationModules là mô hình của toàn ứng dụng

`ApplicationModules` là điểm truy cập chính để khám phá các application module. Bạn tạo mô hình từ lớp ứng dụng:

```java
package com.acme.shop;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.modulith.Modulithic;

@Modulithic(systemName = "shop")
@SpringBootApplication
public class ShopApplication {

    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
```

Trong ví dụ này, `@Modulithic` khai báo metadata ở cấp ứng dụng. Thuộc tính `systemName` đặt tên định danh cho hệ thống là `shop`. Tên này mô tả toàn bộ ứng dụng modular monolith, không phải tên của một application module riêng lẻ.

Khởi tạo mô hình bằng `ApplicationModules.of(ShopApplication.class)`:

```java
import org.springframework.modulith.core.ApplicationModules;

class ModuleModelExample {

    void inspect() {
        ApplicationModules modules = ApplicationModules.of(ShopApplication.class);

        System.out.println("System name: " + modules.getSystemName());
        modules.forEach(System.out::println);
    }
}
```

`ApplicationModules.of(...)` sử dụng lớp ứng dụng làm điểm bắt đầu để khám phá package và xây dựng mô hình. `getSystemName()` đọc tên hệ thống của mô hình; `forEach` cho phép duyệt qua các module đã được phát hiện. Có thể dùng `stream()` khi muốn lọc, ánh xạ hoặc tổng hợp danh sách module bằng Java Stream API.

## 2. Phân biệt metadata cấp ứng dụng và cấp module

Metadata có thể được khai báo ở nhiều cấp, mỗi cấp trả lời một nhóm câu hỏi khác nhau:

| Cấp | Nơi khai báo | Thông tin mô tả |
|---|---|---|
| Toàn ứng dụng | `@Modulithic` trên lớp ứng dụng | Tên định danh của hệ thống và cấu hình khám phá module liên quan |
| Application module | `@ApplicationModule` trong `package-info.java` của module | Tên hiển thị, loại module và các module được phép phụ thuộc |
| Named interface | `@NamedInterface` trong `package-info.java` của package được công bố | Tên giao diện công khai bổ sung của module |

Ví dụ, hệ thống `shop` có các module `order`, `inventory` và `customer`. Tên hệ thống định danh toàn bộ mô hình; metadata của `order` mô tả riêng trách nhiệm và quy tắc phụ thuộc của module đơn hàng.

Không nên đồng nhất tên hệ thống với tên hiển thị của module. Một hệ thống có thể chứa nhiều module và mỗi module có metadata riêng.

## 3. Khai báo metadata cho application module

`@ApplicationModule` được đặt trong `package-info.java` tại module base package. Ví dụ, module `order` có thể khai báo:

```java
@org.springframework.modulith.ApplicationModule(
        displayName = "Quản lý đơn hàng",
        allowedDependencies = "inventory"
)
package com.acme.shop.order;
```

Trong đó:

- `displayName` cung cấp tên dễ đọc cho module trong các báo cáo và công cụ hiển thị.
- `allowedDependencies` giới hạn các module mà `order` được phép phụ thuộc theo mô hình kiến trúc.
- Package chứa `package-info.java` chính là module base package, vì vậy metadata được gắn với module `order`.

Nếu module cần sử dụng một named interface cụ thể, có thể khai báo phụ thuộc theo tên giao diện đó, chẳng hạn `inventory :: spi`, sau khi module `inventory` công bố named interface `spi`.

Một named interface có thể được khai báo trong package con:

```java
@org.springframework.modulith.NamedInterface("spi")
package com.acme.shop.inventory.spi;
```

Package `inventory.spi` vẫn thuộc module `inventory`. Annotation chỉ đánh dấu package đó là một phần API được công bố có tên. Các package triển khai khác của `inventory` vẫn giữ vai trò nội bộ theo quy ước mặc định.

## 4. Đọc danh sách module và thông tin cơ bản

Sau khi tạo mô hình, bạn có thể truy cập module theo tên hoặc duyệt qua toàn bộ danh sách. Ví dụ:

```java
import org.springframework.modulith.core.ApplicationModule;
import org.springframework.modulith.core.ApplicationModules;

class ModuleInventory {

    void printModules() {
        ApplicationModules modules = ApplicationModules.of(ShopApplication.class);

        modules.forEach(module -> {
            System.out.println("Module: " + module.getName());
            System.out.println("Base package: " + module.getBasePackage());
            System.out.println("Display name: " + module.getDisplayName());
        });

        ApplicationModule order = modules.getModuleByName("order");
        System.out.println("Order module: " + order);
    }
}
```

Thông tin tên module và base package giúp xác định module nào được khám phá và package nào làm gốc cho module đó. Tên hiển thị hỗ trợ báo cáo hướng đến người đọc. `getModuleByName("order")` giúp truy cập một module cụ thể khi bạn đã biết tên định danh của nó.

Khi cần tra cứu theo một kiểu Java thuộc module, có thể dùng API tra cứu module theo type của `ApplicationModules`. Cách này hữu ích khi viết công cụ gắn thông tin kiến trúc với một class cụ thể, thay vì tự phân tích tên package.

## 5. Metadata được dùng để kiểm tra kiến trúc

Metadata không chỉ phục vụ hiển thị. Những khai báo như `allowedDependencies` và named interface cung cấp thông tin để Spring Modulith xác định phụ thuộc nào hợp lệ.

Ví dụ, nếu `order` chỉ được phép phụ thuộc vào `inventory`, khai báo ở `order` sẽ làm rõ ý định kiến trúc. Khi code trong `order` tham chiếu module khác không nằm trong danh sách được phép, kiểm tra kiến trúc có thể phát hiện vi phạm.

Bạn có thể kiểm tra toàn bộ mô hình bằng:

```java
import org.springframework.modulith.core.ApplicationModules;
import org.junit.jupiter.api.Test;

class ModularityTests {

    @Test
    void verifiesApplicationModules() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
```

`verify()` kiểm tra các quy tắc phụ thuộc và những ràng buộc kiến trúc mà mô hình module cung cấp. Vì vậy, metadata khai báo cần phản ánh đúng chính sách phụ thuộc mà nhóm phát triển mong muốn duy trì.

Khi kiểm tra thất bại, hãy xem module gọi, module đích và loại phụ thuộc được báo cáo. Sau đó đối chiếu với `allowedDependencies` và các named interface đã công bố. Nếu phụ thuộc là hợp lệ về nghiệp vụ, hãy điều chỉnh metadata hoặc API theo quyết định kiến trúc có chủ đích rồi chạy lại kiểm tra.

## 6. Dùng metadata để tạo báo cáo kiến trúc

Một công cụ nội bộ có thể dùng mô hình để in danh sách module và tên hệ thống. Ví dụ đơn giản:

```java
import org.springframework.modulith.core.ApplicationModules;

class ArchitectureReport {

    void print() {
        ApplicationModules modules = ApplicationModules.of(ShopApplication.class);

        System.out.println("Application: " + modules.getSystemName());
        System.out.println("Modules:");

        modules.stream()
                .sorted((left, right) -> left.getName().compareTo(right.getName()))
                .forEach(module -> System.out.printf(
                        "- %s (%s)%n",
                        module.getName(),
                        module.getBasePackage()
                ));
    }
}
```

Đoạn code trên tạo báo cáo có tên hệ thống và danh sách module được sắp xếp theo tên. Có thể mở rộng báo cáo để hiển thị tên dễ đọc, các named interface và những phụ thuộc đã được khai báo. Khi tích hợp vào CI, báo cáo giúp reviewer hiểu nhanh phạm vi module mà bài kiểm tra kiến trúc đang kiểm soát.

Nên lấy dữ liệu từ mô hình `ApplicationModules` thay vì tự quét thư mục nguồn. Việc tự quét có thể bỏ sót quy tắc khám phá module, package được công bố hoặc metadata annotation mà Spring Modulith đã xử lý.

## 7. Lưu ý khi đọc và quản lý metadata

1. **Đặt annotation đúng vị trí.** `@Modulithic` thuộc lớp ứng dụng; `@ApplicationModule` thuộc `package-info.java` của module; `@NamedInterface` thuộc package con được công bố.
2. **Dùng tên ổn định.** Chọn `systemName` và tên module nhất quán để báo cáo, tài liệu và công cụ nội bộ có thể tham chiếu ổn định.
3. **Phân biệt tên định danh và tên hiển thị.** Tên module dùng trong tra cứu và tham chiếu phụ thuộc cần nhất quán; `displayName` dành cho con người đọc.
4. **Khai báo đúng phụ thuộc.** `allowedDependencies` biểu đạt chính sách kiến trúc. Không thêm mọi module vào danh sách chỉ để làm cho kiểm tra qua được.
5. **Giữ API công khai nhỏ.** Named interface chỉ nên chứa hợp đồng cần chia sẻ. Không công bố package triển khai hoặc repository chỉ vì một module khác đang cần truy cập chúng.
6. **Kiểm tra sau khi thay đổi metadata.** Chạy `ApplicationModules.of(ShopApplication.class).verify()` để xác nhận mô hình và các quy tắc phụ thuộc vẫn hợp lệ.

## 8. Bài tập thực hành

Với ứng dụng bán hàng có các module `order`, `inventory` và `customer`, hãy thực hiện:

1. Khai báo `@Modulithic(systemName = "shop")` trên `ShopApplication`.
2. Đặt `@ApplicationModule(displayName = "Quản lý đơn hàng", allowedDependencies = "inventory")` trong `com.acme.shop.order/package-info.java`.
3. Khai báo named interface `spi` trong `com.acme.shop.inventory.spi`.
4. Tạo `ApplicationModules` từ `ShopApplication.class` và đọc system name.
5. Duyệt danh sách module, in tên, base package và display name.
6. Tra cứu module `order` bằng `getModuleByName("order")`.
7. Chạy `verify()` và thử thêm một phụ thuộc không được phép để quan sát kết quả kiểm tra.
8. Viết một báo cáo ngắn liệt kê tên hệ thống và các module được phát hiện.

Sau bài tập, hãy giải thích metadata cấp ứng dụng khác metadata cấp module ở điểm nào, và vì sao `allowedDependencies` có thể giúp duy trì ranh giới kiến trúc.

## 9. Ghi nhớ

- `ApplicationModules.of(ShopApplication.class)` tạo mô hình application module từ lớp ứng dụng.
- `@Modulithic(systemName = "shop")` khai báo tên định danh ở cấp toàn ứng dụng; có thể đọc tên đó từ mô hình qua `getSystemName()`.
- `@ApplicationModule` mô tả metadata của một module, chẳng hạn tên hiển thị và các phụ thuộc được phép.
- `@NamedInterface` công bố một package con như một phần API có tên.
- Có thể duyệt module, tra cứu theo tên và dùng `verify()` để kiểm tra các quy tắc kiến trúc.
- Nên dùng mô hình Spring Modulith làm nguồn dữ liệu cho báo cáo kiến trúc thay vì tự suy luận module từ cấu trúc thư mục.

Khi nắm được cách đọc system name và metadata, bạn có thể xây dựng công cụ quan sát cấu trúc toàn ứng dụng, kiểm tra quy tắc phụ thuộc và duy trì modular monolith theo những ranh giới được khai báo rõ ràng.
