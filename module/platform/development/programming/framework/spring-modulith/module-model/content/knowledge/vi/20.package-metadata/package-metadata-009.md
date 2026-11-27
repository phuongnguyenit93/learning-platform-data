# Tránh tách metadata khỏi cấu trúc package

Spring Modulith xây dựng mô hình application module từ cấu trúc package của ứng dụng và metadata gắn với chính các package đó. Vì vậy, vị trí của package, annotation khai báo module và tài liệu mô tả package cần được tổ chức thống nhất. Khi metadata bị tách sang một file cấu hình trung tâm, một bảng tính hoặc một tài liệu không gắn với mã nguồn, nhóm dễ gặp tình trạng cấu trúc thực tế đã đổi nhưng mô tả kiến trúc vẫn giữ thông tin cũ.

Trong Java, `package-info.java` là nơi phù hợp để khai báo package annotation và viết Javadoc cho package. Spring Modulith dùng các annotation như `@ApplicationModule` và `@NamedInterface` để hiểu ranh giới module và các API được công khai. Đặt metadata cạnh package mà nó mô tả giúp người phát triển nhìn thấy ý nghĩa kiến trúc ngay tại vị trí tổ chức mã nguồn.

## 1. Metadata thuộc về package nào?

Giả sử một ứng dụng bán hàng có các module `orders`, `inventory` và `shipping`:

~~~text
com.acme.shop
├── ShopApplication.java
├── orders
│   ├── package-info.java
│   ├── OrderManagement.java
│   └── internal
│       └── OrderRepository.java
├── inventory
│   ├── package-info.java
│   ├── InventoryManagement.java
│   ├── api
│   │   ├── package-info.java
│   │   └── StockAvailability.java
│   └── internal
│       ├── StockRepository.java
│       └── StockPolicy.java
└── shipping
    ├── package-info.java
    └── ShippingService.java
~~~

Trong cấu trúc này, metadata cần trả lời những câu hỏi gắn với vị trí cụ thể:

- Package `com.acme.shop.inventory` có đại diện cho một application module không?
- Module có tên hiển thị hoặc loại module nào?
- Module được phép phụ thuộc vào những module nào?
- Package `com.acme.shop.inventory.api` có phải một named interface được công khai không?
- Package `internal` có phải chi tiết triển khai của module sở hữu không?

Các thông tin này nên nằm ở package mà chúng mô tả. Metadata của module inventory được đặt trong `inventory/package-info.java`; metadata của named interface api được đặt trong `inventory/api/package-info.java`; metadata dependency của shipping được đặt trong `shipping/package-info.java`.

## 2. Dùng package-info.java cho package annotation và tài liệu

Java cho phép khai báo annotation ở cấp package. File `package-info.java` phải nằm trong đúng thư mục tương ứng với package. Ví dụ:

~~~java
/**
 * Quản lý tồn kho, kiểm tra khả năng cung ứng và giữ số lượng hàng.
 *
 * <p>Module công khai các hợp đồng nghiệp vụ cần thiết cho những module
 * khác. Repository và chính sách lưu trữ nằm trong package nội bộ.
 */
@org.springframework.modulith.ApplicationModule(
        displayName = "Quản lý tồn kho"
)
package com.acme.shop.inventory;
~~~

File này làm hai việc liên quan trực tiếp đến package:

1. Javadoc mô tả trách nhiệm và phạm vi của package.
2. `@ApplicationModule` cung cấp metadata để Spring Modulith mô hình hóa module.

Đặt file tại:

~~~text
src/main/java/com/acme/shop/inventory/package-info.java
~~~

Đừng đặt file này trong package cha `com.acme.shop` rồi kỳ vọng annotation tự áp dụng cho tất cả package con. Package annotation áp dụng cho package được khai báo ngay sau annotation trong file.

Nếu module đã có package-info.java, hãy bổ sung hoặc chỉnh sửa nội dung tại file đó. Một package chỉ có một khai báo package; không tạo nhiều file package-info.java cho cùng package hoặc nhiều khai báo package annotation tách rời.

## 3. Đặt metadata dependency tại module tiêu thụ

`allowedDependencies` mô tả module mà module hiện tại được phép phụ thuộc vào. Vì vậy, metadata này thuộc package gốc của consumer.

Ví dụ, module shipping sử dụng named interface api của inventory:

~~~java
/**
 * Điều phối việc chuẩn bị và thực hiện giao hàng.
 */
@org.springframework.modulith.ApplicationModule(
        displayName = "Giao hàng",
        allowedDependencies = "inventory::api"
)
package com.acme.shop.shipping;
~~~

Cấu hình này nằm trong:

~~~text
src/main/java/com/acme/shop/shipping/package-info.java
~~~

Đọc quan hệ theo hướng:

~~~text
shipping  ─────depends on─────>  inventory::api
consumer                           provider
khai báo allowlist                 công khai named interface
~~~

Không đặt `allowedDependencies = "inventory::api"` trong package-info.java của inventory với ý định cấp quyền cho shipping. Nếu đặt ở inventory, thuộc tính sẽ mô tả các module mà inventory được phép phụ thuộc vào.

Khi review metadata, hãy xác định đúng chủ sở hữu của quan hệ: consumer khai báo dependency; provider công khai API.

## 4. Công khai named interface ngay tại package API

Một module có thể công khai một nhóm kiểu trong package con bằng `@NamedInterface`. Ví dụ:

~~~java
/**
 * Hợp đồng tích hợp tồn kho dành cho các module khác.
 */
@org.springframework.modulith.NamedInterface("api")
package com.acme.shop.inventory.api;
~~~

File này nằm tại:

~~~text
src/main/java/com/acme/shop/inventory/api/package-info.java
~~~

Các kiểu trong package này có thể được consumer sử dụng qua named interface `inventory::api`. Ví dụ:

~~~java
package com.acme.shop.inventory.api;

public interface StockAvailability {

    boolean isAvailable(String sku, int quantity);
}
~~~

Đặt tên package là `api` tự nó không công khai package đó. Metadata `@NamedInterface("api")` mới khai báo nhóm API có tên api cho mô hình Spring Modulith.

Tương tự, nếu muốn công khai một nhóm hợp đồng khác, chẳng hạn `spi`, hãy đặt annotation tương ứng tại package đó:

~~~java
@org.springframework.modulith.NamedInterface("spi")
package com.acme.shop.inventory.spi;
~~~

Chỉ công khai những nhóm hợp đồng có mục đích rõ ràng. Không đánh dấu package `internal`, `persistence` hoặc `repository` thành named interface chỉ để giải quyết lỗi phụ thuộc; hãy xác định API nghiệp vụ mà consumer thực sự cần.

## 5. Giữ cấu trúc package và metadata đồng bộ

Metadata chỉ chính xác khi package được khai báo tồn tại và chứa đúng trách nhiệm. Ví dụ, nếu package-info.java công khai named interface api nhưng package đã bị đổi tên hoặc chuyển đi, metadata và cấu trúc mã nguồn không còn khớp.

Khi đổi cấu trúc, kiểm tra đồng thời các thành phần:

| Thay đổi | Metadata cần rà soát |
|---|---|
| Đổi tên package gốc của module | Package declaration trong package-info.java, vị trí file và mọi tham chiếu đến module |
| Đổi tên hoặc di chuyển named interface | Package declaration, annotation @NamedInterface và allowedDependencies của consumer |
| Tách một module thành hai module | Annotation @ApplicationModule ở các package gốc mới và dependency giữa các module |
| Gộp hai module | Xóa hoặc hợp nhất metadata module, rà soát consumer và các named interface còn dùng |
| Đổi tên identifier hoặc display name | Các giá trị id/displayName và nơi tham chiếu identifier trong dependency |
| Chuyển package nội bộ thành API | Thiết kế hợp đồng, annotation named interface và tài liệu package |

Không duy trì một danh sách package API độc lập ở nhiều nơi nếu có thể biểu diễn trực tiếp bằng package annotation. Nếu dự án cần tài liệu tổng quan, tài liệu đó nên được sinh từ mô hình hoặc được cập nhật như một bản diễn giải của metadata trong mã nguồn.

## 6. Không nhầm package metadata với cấu hình Spring runtime

Package annotation mô tả cấu trúc và quy tắc kiến trúc. Nó không thay thế cấu hình runtime và không tự tạo bean.

| Thông tin | Nơi phù hợp | Vai trò |
|---|---|---|
| Module là gì, display name, loại module | Package gốc trong package-info.java | Metadata của application module |
| Named interface nào được công khai | Package API trong package-info.java | Metadata của nhóm API |
| Consumer được phép phụ thuộc vào đâu | Package gốc của consumer | Ràng buộc dependency |
| Database URL, credential, cổng server | application.yml, profile hoặc môi trường | Cấu hình runtime |
| Bean implementation, constructor injection | Java class và Spring configuration | Hành vi ứng dụng |
| Sơ đồ module và mô tả tổng quan | Tài liệu được sinh hoặc tài liệu kiến trúc | Cách trình bày mô hình cho người đọc |

Ví dụ, không đặt tên named interface trong `application.yml` rồi kỳ vọng Spring Modulith tự nhận diện nó. Named interface là metadata package và cần được khai báo bằng annotation tại package tương ứng.

Tương tự, `@ApplicationModule` không thay thế `@Service`, `@Component` hoặc cơ chế component scanning. Một package có thể là application module nhưng các bean vẫn phải được khai báo và phát hiện theo cấu hình Spring thông thường.

## 7. Chọn detection strategy phù hợp với metadata

Cấu trúc package và package annotation phối hợp với detection strategy để tạo mô hình module.

Với chiến lược mặc định `direct-subpackages`, Spring Modulith nhận diện các package con trực tiếp của package chứa lớp ứng dụng. Annotation `@ApplicationModule` cung cấp thêm metadata cho module đã được nhận diện.

Nếu ứng dụng chọn chiến lược `explicitly-annotated`, chỉ package được đánh dấu bằng `@ApplicationModule` hoặc jMolecules `@Module` mới được chọn làm application module. Khi đó, package-info.java trở thành phần quan trọng của quy ước phát hiện module.

Ví dụ cấu hình:

~~~properties
spring.modulith.detection-strategy=explicitly-annotated
~~~

Khi sử dụng chiến lược này, nếu tạo package nghiệp vụ mới mà quên package-info.java với annotation module, package có thể không xuất hiện trong mô hình. Vì vậy, quy trình tạo module cần bao gồm bước tạo package metadata cùng lúc với package và mã nguồn đầu tiên.

Không nên thêm annotation một cách máy móc cho mọi package con. Package `internal`, `persistence`, `adapter` thường là các phần bên trong module, không phải application module độc lập.

## 8. Ví dụ hoàn chỉnh với inventory và shipping

Một cấu trúc tối thiểu có thể được tổ chức như sau:

~~~text
src/main/java/com/acme/shop
├── ShopApplication.java
├── inventory
│   ├── package-info.java
│   ├── InventoryManagement.java
│   ├── api
│   │   ├── package-info.java
│   │   └── StockAvailability.java
│   └── internal
│       └── StockAvailabilityService.java
└── shipping
    ├── package-info.java
    └── ShippingService.java
~~~

Metadata của provider:

~~~java
@org.springframework.modulith.ApplicationModule(
        displayName = "Quản lý tồn kho"
)
package com.acme.shop.inventory;
~~~

Metadata của API package:

~~~java
@org.springframework.modulith.NamedInterface("api")
package com.acme.shop.inventory.api;
~~~

Metadata của consumer:

~~~java
@org.springframework.modulith.ApplicationModule(
        displayName = "Giao hàng",
        allowedDependencies = "inventory::api"
)
package com.acme.shop.shipping;
~~~

Hợp đồng công khai:

~~~java
package com.acme.shop.inventory.api;

public interface StockAvailability {

    boolean isAvailable(String sku, int quantity);
}
~~~

Consumer chỉ tham chiếu hợp đồng đó:

~~~java
package com.acme.shop.shipping;

import com.acme.shop.inventory.api.StockAvailability;
import org.springframework.stereotype.Service;

@Service
public class ShippingService {

    private final StockAvailability stockAvailability;

    public ShippingService(StockAvailability stockAvailability) {
        this.stockAvailability = stockAvailability;
    }

    public void prepare(String sku, int quantity) {
        if (!stockAvailability.isAvailable(sku, quantity)) {
            throw new IllegalStateException("Không đủ hàng để giao");
        }

        // Tiếp tục quy trình giao hàng.
    }
}
~~~

Trong ví dụ này, metadata được đặt tại đúng package mà nó mô tả: inventory sở hữu metadata module; inventory.api sở hữu metadata named interface; shipping sở hữu allowlist dependency của nó.

## 9. Kiểm chứng metadata bằng ApplicationModules

Sau khi tổ chức package-info.java, tạo architecture test để kiểm tra mô hình:

~~~java
package com.acme.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void verifiesPackageMetadataAndModuleBoundaries() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

`verify()` kiểm tra các quy tắc module dựa trên mô hình được phát hiện, bao gồm phụ thuộc vòng, truy cập package nội bộ và các giới hạn dependency được khai báo.

Khi test thất bại, hãy kiểm tra theo thứ tự:

1. Package gốc của lớp ứng dụng có đúng không?
2. File package-info.java có nằm đúng thư mục package không?
3. Package declaration trong file có trùng với đường dẫn không?
4. @ApplicationModule có được đặt ở package gốc của module không?
5. @NamedInterface có được đặt tại package mà nó công khai không?
6. allowedDependencies có nằm trên package gốc của consumer không?
7. Identifier module và tên named interface có khớp với metadata provider không?

Có thể in mô hình để hỗ trợ review:

~~~java
var modules = ApplicationModules.of(ShopApplication.class);
System.out.println(modules);
~~~

Nếu metadata không được đọc như dự kiến, trước hết xác nhận file package-info.java thuộc đúng source set và được biên dịch cùng mã nguồn ứng dụng. Không vội tạo một file cấu hình trung tâm để bù cho annotation đặt sai package.

## 10. Những cách tổ chức dễ gây lệch metadata

Một số cách làm khiến metadata dần tách khỏi cấu trúc:

- **Gom toàn bộ dependency vào một tài liệu riêng:** tài liệu có thể lỗi thời khi package hoặc module thay đổi.
- **Đặt tất cả annotation trong package gốc của ứng dụng:** annotation package không tự áp dụng cho các package con.
- **Dùng tên folder thay cho named interface:** package tên api chưa chắc đã được công khai nếu thiếu @NamedInterface.
- **Đặt allowlist ở provider:** allowedDependencies cần nằm ở module tiêu thụ đang tạo ra dependency.
- **Tạo package-info.java ở sai source set:** metadata chỉ phục vụ test có thể không xuất hiện trong artifact production; metadata kiến trúc của ứng dụng nên nằm trong main sources.
- **Tạo nhiều quy ước đặt tên:** một nơi dùng inventory, nơi khác dùng inventories hoặc display name, khiến identifier khó theo dõi.
- **Không cập nhật metadata khi refactor package:** cấu trúc mới và annotation cũ không còn mô tả cùng một thiết kế.

Nếu cần một danh mục tổng quan cho nhóm, hãy tạo tài liệu hoặc sơ đồ từ mô hình Spring Modulith. Giữ annotation và cấu trúc package là nguồn dữ liệu kiến trúc chính, sau đó dùng tài liệu tổng quan để giải thích và trình bày.

## 11. Quy trình khi tạo hoặc thay đổi module

Để metadata không bị quên trong quá trình phát triển, đưa nó vào cùng quy trình thay đổi package:

1. Xác định trách nhiệm nghiệp vụ và package gốc của module.
2. Tạo package gốc và package-info.java cùng lúc.
3. Viết Javadoc ngắn mô tả trách nhiệm, phạm vi và những gì module sở hữu.
4. Khai báo @ApplicationModule với các metadata cần thiết.
5. Tạo package API riêng nếu cần và đánh dấu bằng @NamedInterface.
6. Khai báo allowedDependencies tại package gốc của consumer.
7. Đặt service, repository, entity và implementation trong package nội bộ.
8. Chạy architecture test để xác minh mô hình.
9. Khi đổi package hoặc tên interface, cập nhật package-info.java và các consumer trong cùng thay đổi.
10. Sinh lại sơ đồ hoặc tài liệu kiến trúc nếu dự án sử dụng Documenter.

Quy trình này làm cho metadata thay đổi cùng với cấu trúc mà nó mô tả. Người review có thể xem package, package-info.java và các lớp liên quan trong cùng pull request.

## 12. Checklist review package metadata

- [ ] Mỗi application module có package gốc rõ ràng.
- [ ] package-info.java nằm đúng thư mục và có package declaration khớp.
- [ ] Javadoc package mô tả đúng trách nhiệm module.
- [ ] @ApplicationModule chỉ được đặt tại package gốc của module.
- [ ] @NamedInterface được đặt tại package con thực sự cần công khai.
- [ ] allowedDependencies nằm trên package gốc của consumer.
- [ ] Identifier module và tên named interface thống nhất giữa provider và consumer.
- [ ] Package internal không bị công khai chỉ để làm cho test vượt qua.
- [ ] Metadata kiến trúc nằm trong production sources nếu runtime cần sử dụng.
- [ ] Architecture test xác minh thành công sau thay đổi.
- [ ] Tài liệu hoặc sơ đồ tổng quan được cập nhật nếu cấu trúc module thay đổi.

## 13. Bài tập thực hành

1. Tạo package gốc `com.acme.shop.inventory` và file package-info.java cho module inventory.
2. Viết Javadoc mô tả trách nhiệm của inventory và đánh dấu package bằng @ApplicationModule.
3. Tạo package `inventory.api`, đặt StockAvailability trong package đó và công khai bằng @NamedInterface("api").
4. Tạo package `inventory.internal` cho implementation và repository.
5. Tạo module shipping với package-info.java và khai báo allowedDependencies = "inventory::api".
6. Inject StockAvailability vào ShippingService qua constructor.
7. Thử xóa @NamedInterface khỏi inventory.api và chạy architecture test để quan sát vi phạm.
8. Khôi phục annotation, sau đó thử chuyển allowedDependencies sang package-info.java của inventory và giải thích vì sao hướng dependency bị khai báo sai.
9. Đổi tên package inventory.api hoặc tên named interface, cập nhật metadata và consumer trong cùng một thay đổi.
10. Review lại cấu trúc package, package-info.java và kết quả verify() để chứng minh metadata đang mô tả đúng kiến trúc.

Sau bài tập, bạn cần giải thích được vì sao package-info.java là nơi thích hợp cho metadata package, cách @ApplicationModule và @NamedInterface gắn với cấu trúc package, và vì sao metadata kiến trúc nên được duy trì ngay cạnh mã nguồn mà nó mô tả.

## Tài liệu tham khảo

- [Application Modules – Spring Modulith Reference](https://docs.spring.io/spring-modulith/reference/fundamentals.html)
- [ApplicationModule API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/ApplicationModule.html)
- [NamedInterface API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/NamedInterface.html)
- [Verifying Application Module Structure – Spring Modulith Reference](https://docs.spring.io/spring-modulith/reference/verification.html)
