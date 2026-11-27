# Named interface là vùng API bổ sung của module

Trong một ứng dụng Spring Boot được tổ chức theo modular monolith, mỗi module cần có ranh giới rõ ràng: module khác được phép sử dụng những thành phần nào, và phần nào phải được giữ lại để triển khai nội bộ. Spring Modulith xem package gốc của module là API mặc định. Tuy nhiên, một module đôi khi cần đặt các hợp đồng công khai trong những package con để cấu trúc mã nguồn dễ hiểu hơn. **Named interface** cho phép khai báo những package con đó là các vùng API bổ sung của module.

Khái niệm này giúp mô hình module phản ánh đúng kiến trúc nghiệp vụ: module sở hữu dữ liệu và quy trình của mình, còn module khác chỉ phụ thuộc vào những hợp đồng mà chủ sở hữu chủ động công bố. Khi kết hợp named interface với quy tắc phụ thuộc, ta có thể kiểm tra ranh giới đó bằng Spring Modulith thay vì chỉ dựa vào quy ước của nhóm phát triển.

## Vì sao module cần named interface?

Giả sử ứng dụng có module `inventory` quản lý sản phẩm và tồn kho. Module `orders` cần tra cứu thông tin sản phẩm khi tạo đơn hàng. Một cách tổ chức có thể là đặt mọi kiểu dữ liệu công khai ngay trong package gốc `com.acme.inventory`. Cách này đơn giản lúc đầu, nhưng package gốc dễ trở thành nơi chứa quá nhiều lớp và giao diện.

Ta có thể tách hợp đồng tra cứu sản phẩm vào package `com.acme.inventory.catalog`. Theo quy ước package của Spring Modulith, package con thông thường thuộc phần triển khai nội bộ của module. Vì vậy, chỉ chuyển một interface `public` vào package con chưa đủ để tuyên bố rằng đó là API mà module khác được phép dùng. Ta cần đánh dấu package đó bằng `@NamedInterface`.

Ví dụ cấu trúc mã nguồn:

```text
com.acme
├── Application.java
├── inventory
│   ├── InventoryService.java
│   ├── catalog
│   │   ├── package-info.java
│   │   ├── ProductCatalog.java
│   │   └── ProductView.java
│   └── internal
│       └── StockRepository.java
└── orders
    ├── package-info.java
    └── OrderService.java
```

Trong ví dụ này, `com.acme.inventory` là package gốc của module `inventory`. Package `com.acme.inventory.catalog` chứa hợp đồng tra cứu sản phẩm và sẽ được công bố thành một named interface. Package `com.acme.inventory.internal` vẫn là chi tiết triển khai nội bộ. Module `orders` có thể sử dụng hợp đồng trong `catalog` khi quy tắc phụ thuộc của nó cho phép.

## Named interface mở rộng API của module như thế nào?

Có thể hình dung API của một module gồm hai phần:

- API mặc định nằm trong package gốc của module.
- Các API bổ sung nằm trong những package con được đánh dấu bằng `@NamedInterface`.

Những package con không được công bố tiếp tục là vùng nội bộ. Việc một lớp có từ khóa `public` chỉ quyết định khả năng truy cập theo ngôn ngữ Java; nó không tự biến package chứa lớp đó thành API công khai theo mô hình module của Spring Modulith.

Named interface có tên riêng để module tiêu thụ có thể khai báo chính xác vùng API mà nó cần. Tên này cũng giúp người đọc hiểu mục đích của hợp đồng, chẳng hạn `catalog`, `reporting` hoặc `spi`. Tên nên thể hiện nhóm trách nhiệm ổn định, không nên chỉ mô tả tên một lớp cụ thể.

Named interface là một khái niệm kiến trúc của Spring Modulith. Nó không phải Java Platform Module System (`module-info.java`), cũng không tự tạo REST endpoint hay cơ chế bảo mật ở runtime. Nó mô tả API giữa các application module để Spring Modulith có thể phân tích và kiểm chứng cấu trúc phụ thuộc.

## Khai báo named interface bằng `@NamedInterface`

Để công bố package `catalog`, tạo hoặc cập nhật file `package-info.java` trong package đó:

```java
@org.springframework.modulith.NamedInterface("catalog")
package com.acme.inventory.catalog;
```

Annotation đặt ở cấp package cho Spring Modulith biết rằng các kiểu nằm trong `com.acme.inventory.catalog` thuộc một named interface có tên `catalog` của module `inventory`.

Ví dụ hợp đồng mà module `orders` cần sử dụng:

```java
package com.acme.inventory.catalog;

public interface ProductCatalog {

    ProductView findBySku(String sku);
}
```

```java
package com.acme.inventory.catalog;

public record ProductView(String sku, String name) {}
```

`ProductCatalog` là điểm vào mà module khác cần biết. `ProductView` là kiểu dữ liệu đi kèm hợp đồng. Các kiểu được công bố trong named interface nên được thiết kế như API ổn định: chỉ chứa những thao tác và dữ liệu mà module tiêu thụ thực sự cần. Không nên đưa repository, entity nội bộ hoặc lớp điều phối quy trình vào API chỉ vì chúng đang tiện để tái sử dụng.

## Giới hạn phụ thuộc tới named interface

Khi module tiêu thụ muốn giới hạn phụ thuộc vào một named interface cụ thể, khai báo `allowedDependencies` trên package gốc của module tiêu thụ. Ví dụ, `orders` chỉ cần vùng `catalog` của `inventory`:

```java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "inventory::catalog"
)
package com.acme.orders;
```

Cú pháp `inventory::catalog` có hai phần: `inventory` là tên module được phụ thuộc, còn `catalog` là tên named interface được sử dụng. Tên module trong ví dụ là tên mặc định suy ra từ package module `com.acme.inventory`.

Sau khai báo này, mã nguồn trong module `orders` có thể sử dụng kiểu được công bố:

```java
package com.acme.orders;

import com.acme.inventory.catalog.ProductCatalog;
import org.springframework.stereotype.Service;

@Service
class OrderService {

    private final ProductCatalog productCatalog;

    OrderService(ProductCatalog productCatalog) {
        this.productCatalog = productCatalog;
    }

    void checkProduct(String sku) {
        var product = productCatalog.findBySku(sku);
        // Tiếp tục xử lý đơn hàng bằng dữ liệu từ hợp đồng công khai.
    }
}
```

Ví dụ trên minh họa hướng phụ thuộc: `orders` gọi hợp đồng do `inventory` sở hữu. Cách triển khai cụ thể của `ProductCatalog` vẫn thuộc trách nhiệm module `inventory`; module `orders` không cần biết repository hay quy trình lưu kho bên trong.

Nếu module tiêu thụ cần nhiều vùng API của cùng một module, có thể khai báo các named interface tương ứng trong danh sách `allowedDependencies`. Hãy chỉ mở quyền truy cập theo nhu cầu thực tế. Khai báo cả module mà không giới hạn interface sẽ làm hợp đồng phụ thuộc rộng hơn mức cần thiết khi mục tiêu của thiết kế là kiểm soát từng vùng API.

## Kiểm chứng ranh giới bằng Spring Modulith

Khai báo annotation mới chỉ mô tả ý định kiến trúc. Cần chạy kiểm tra để phát hiện mã nguồn đang phụ thuộc sai ranh giới. Spring Modulith cung cấp `ApplicationModules` để phân tích cấu trúc module và `verify()` để kiểm tra các quy tắc kiến trúc.

Ví dụ một kiểm thử kiến trúc:

```java
package com.acme;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void verifiesModuleStructure() {
        ApplicationModules.of(Application.class).verify();
    }
}
```

`Application.class` là lớp ứng dụng nằm trong package gốc dùng để khám phá các module. Khi kiểm thử chạy, Spring Modulith phân tích các module được tìm thấy và kiểm tra những ràng buộc như phụ thuộc không được cho phép, truy cập vào thành phần nội bộ và chu trình phụ thuộc giữa các module. Nếu `orders` truy cập trực tiếp `com.acme.inventory.internal.StockRepository`, kiểm thử kiến trúc có thể chỉ ra rằng module đang sử dụng một kiểu nội bộ thay vì API được công bố.

Nên chạy kiểm thử này thường xuyên trong quy trình build, đặc biệt sau khi di chuyển package, thêm module hoặc thay đổi hợp đồng. Nhờ đó, một thay đổi vô tình làm lộ chi tiết triển khai sẽ được phát hiện ngay trong quá trình phát triển.

## Phân biệt named interface với các thành phần liên quan

| Thành phần | Vai trò | Điều cần nhớ |
|---|---|---|
| Package gốc của module | Chứa API mặc định của module | Không cần đánh dấu bằng `@NamedInterface` để trở thành API mặc định |
| Package con có `@NamedInterface` | Công bố thêm một vùng API có tên | Có thể được tham chiếu bằng cú pháp `module::interface` |
| Package con không được công bố | Chứa chi tiết triển khai nội bộ | Module khác không nên phụ thuộc trực tiếp vào các kiểu ở đây |
| `allowedDependencies` | Khai báo những phụ thuộc module được phép | Có thể chỉ rõ một named interface thay vì cho phép phụ thuộc rộng |
| `ApplicationModules.verify()` | Kiểm tra mô hình module | Biến quy ước kiến trúc thành kiểm thử có thể chạy tự động |

Named interface cũng có thể đại diện cho những nhóm hợp đồng khác nhau. Chẳng hạn, `catalog` có thể là API phục vụ nghiệp vụ tra cứu sản phẩm, còn `spi` có thể là nhóm điểm mở rộng dành cho module tích hợp. Tên gọi không tự áp đặt quy tắc thiết kế; ý nghĩa và trách nhiệm của từng vùng API cần được nhóm phát triển thống nhất và thể hiện qua các kiểu được công bố.

## Những lỗi thiết kế thường gặp

**Chỉ thêm `public` mà quên `@NamedInterface`.** Lớp vẫn có thể được Java biên dịch khi module khác import, nhưng Spring Modulith vẫn xem package con chưa được công bố là nội bộ. Hãy kiểm tra `package-info.java` của đúng package chứa hợp đồng.

**Khai báo sai tên module hoặc tên interface.** Giá trị trong `allowedDependencies` phải khớp với tên module và tên đã gán cho `@NamedInterface`. Ví dụ, `inventory::catalog` sẽ không trỏ tới một interface có tên `product-catalog`. Khi kiểm tra thất bại, hãy đối chiếu package gốc của module và annotation tại package API.

**Đưa quá nhiều kiểu vào API.** Nếu công bố nguyên một package chứa cả hợp đồng lẫn chi tiết triển khai, module tiêu thụ có thể dần phụ thuộc vào những thành phần mà module sở hữu muốn thay đổi tự do. Hãy giữ package API nhỏ, có trách nhiệm rõ ràng và chỉ chứa kiểu cần thiết cho giao tiếp liên module.

**Coi named interface là cách bỏ qua mọi quy tắc phụ thuộc.** Việc công bố API không cho phép tạo chu trình phụ thuộc hoặc sử dụng tùy ý mọi module khác. Các quy tắc phụ thuộc vẫn cần được khai báo và kiểm chứng bằng `ApplicationModules.verify()`.

**Để hợp đồng phụ thuộc vào chi tiết nội bộ.** Một interface công khai nhưng trả về entity persistence hoặc yêu cầu caller truyền repository-specific object vẫn khiến module tiêu thụ bị gắn với cách triển khai. Ưu tiên kiểu dữ liệu và thao tác thể hiện ngôn ngữ nghiệp vụ của module sở hữu.

## Quy trình áp dụng trong một module

Khi cần cho module khác sử dụng một phần chức năng nằm ngoài package gốc, hãy xác định trước hợp đồng nhỏ nhất mà caller cần. Đặt hợp đồng và các kiểu dữ liệu liên quan trong package con có trách nhiệm rõ ràng, sau đó đánh dấu package bằng `@NamedInterface` với tên dễ hiểu. Tiếp theo, khai báo `allowedDependencies` ở module tiêu thụ theo dạng `module::interface`, cập nhật mã gọi để chỉ phụ thuộc vào hợp đồng đó, rồi chạy kiểm thử `ApplicationModules.of(Application.class).verify()`.

Nếu kiểm thử báo truy cập vào package nội bộ, hãy xem lại ranh giới: có thể hợp đồng cần được chuyển vào named interface, hoặc module tiêu thụ đang đảm nhận công việc thuộc về module sở hữu. Nếu kiểm thử báo phụ thuộc không được phép, hãy xác nhận caller có thực sự cần vùng API đó và chỉ khai báo quyền phụ thuộc tương ứng khi kiến trúc cho phép.

Một named interface tốt giúp người đọc trả lời được ba câu hỏi: module nào sở hữu hợp đồng, module khác được phép dùng phần nào, và phần triển khai nào vẫn nằm sau ranh giới. Khi các câu trả lời đó rõ ràng, ứng dụng modular monolith có thể phát triển thêm chức năng mà các module vẫn giữ được quyền tự chủ và khả năng thay đổi nội bộ.
