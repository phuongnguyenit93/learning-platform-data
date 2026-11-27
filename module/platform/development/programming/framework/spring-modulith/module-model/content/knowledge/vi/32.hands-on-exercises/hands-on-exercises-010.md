# Bật runtime verification trong ứng dụng mẫu

Trong các bài trước, ta đã dùng `ApplicationModules.verify()` trong một bài kiểm thử kiến trúc. Bài thực hành này đưa cùng việc kiểm tra module vào **quá trình khởi động ứng dụng Spring Boot**. Khi runtime verification được bật, Spring Modulith kiểm tra application module arrangement lúc ứng dụng khởi động và dừng startup nếu phát hiện vi phạm kiến trúc.

Ta sẽ thực hành với hai module `orders` và `catalog`: trước tiên cố ý tạo một dependency vào package nội bộ để quan sát startup thất bại; sau đó chuyển consumer sang API công khai và khởi động lại.

## 1. Mục tiêu và điều kiện đầu vào

Sau bài thực hành, bạn có thể:

- Thêm `spring-modulith-runtime` vào runtime classpath.
- Bật thuộc tính `spring.modulith.runtime.verification-enabled`.
- Nhận biết thời điểm và hậu quả khi runtime verifier phát hiện vi phạm.
- Sửa dependency sai bằng cách dùng API công khai của module sở hữu.
- Phân biệt runtime verification với kiểm thử kiến trúc chạy trong test.

Giả sử ứng dụng có lớp khởi động tại `com.example.shop.ShopApplication` và package tree:

```text
com.example.shop
├── ShopApplication.java
├── catalog
│   ├── ProductCatalog.java
│   └── internal
│       └── ProductVisibilityPolicy.java
└── orders
    └── internal
        └── OrderService.java
```

Các package con trực tiếp `catalog` và `orders` được Spring Modulith nhận diện là application module theo chiến lược mặc định `direct-subpackages`.

## 2. Thêm runtime support

Runtime verification cần artifact `org.springframework.modulith:spring-modulith-runtime` trên runtime classpath. Nếu dự án đã dùng `spring-modulith-starter-core`, artifact runtime này đã được kéo vào theo dependency của starter; hãy kiểm tra cấu hình hiện tại trước khi thêm dependency trùng.

Với Gradle khi chưa có runtime artifact:

```kotlin
dependencies {
    runtimeOnly("org.springframework.modulith:spring-modulith-runtime")
}
```

Với Maven:

```xml
<dependency>
    <groupId>org.springframework.modulith</groupId>
    <artifactId>spring-modulith-runtime</artifactId>
    <scope>runtime</scope>
</dependency>
```

Hãy để Spring Modulith BOM hoặc dependency management của dự án quản lý phiên bản tương thích. Không tự chọn một phiên bản khác với các artifact Spring Modulith đang sử dụng.

Khi có `spring-modulith-runtime`, Spring Boot auto-configuration đăng ký các thành phần runtime như `ApplicationModulesRuntime`, `SpringBootApplicationRuntime` và `RuntimeApplicationModuleVerifier`. Runtime verifier chỉ thực hiện kiểm tra module khi thuộc tính `spring.modulith.runtime.verification-enabled` được bật thành `true`.

## 3. Bật runtime verification

Trong `src/main/resources/application.properties`, thêm:

```properties
spring.modulith.runtime.verification-enabled=true
```

Hoặc dùng YAML:

```yaml
spring:
  modulith:
    runtime:
      verification-enabled: true
```

Thuộc tính này mặc định là `false`. Vì vậy, chỉ thêm `spring-modulith-runtime` mà không bật property sẽ không tự động bật kiểm tra module khi startup.

Nếu muốn bật theo môi trường, có thể đặt property trong file profile, ví dụ `application-architecture-check.properties`, rồi kích hoạt profile đó khi chạy ứng dụng. Trong bài thực hành, ta bật trực tiếp để dễ quan sát kết quả.

## 4. Tạo một vi phạm có chủ đích

Để quan sát runtime verifier hoạt động, hãy tạo một tham chiếu từ `orders` đến package nội bộ của `catalog`.

Tạo `ProductVisibilityPolicy.java` trong `catalog/internal`:

```java
package com.example.shop.catalog.internal;

public final class ProductVisibilityPolicy {

    private ProductVisibilityPolicy() {
    }

    public static boolean isVisible(String sku) {
        return sku != null && !sku.isBlank();
    }
}
```

Sau đó tham chiếu trực tiếp type nội bộ từ `OrderService`:

```java
package com.example.shop.orders.internal;

import com.example.shop.catalog.internal.ProductVisibilityPolicy;
import org.springframework.stereotype.Service;

@Service
public class OrderService {

    public boolean canPlaceOrder(String sku) {
        return ProductVisibilityPolicy.isVisible(sku);
    }
}
```

`ProductVisibilityPolicy` được khai báo `public`, nên Java compiler có thể chấp nhận import. Tuy nhiên, class nằm trong `catalog.internal`, là package nội bộ của closed module `catalog`. Việc `orders` tham chiếu type này vi phạm quy tắc module của Spring Modulith.

## 5. Khởi động ứng dụng và quan sát kết quả

Chạy ứng dụng với runtime verification đã bật:

```powershell
./gradlew bootRun
```

Trên Windows có thể dùng:

```powershell
.\gradlew.bat bootRun
```

Với Maven:

```powershell
mvn spring-boot:run
```

Khi Spring Boot khởi tạo các singleton bean và runtime verifier thực hiện kiểm tra application module arrangement, Spring Modulith phát hiện dependency từ `orders` đến `catalog.internal`. Ứng dụng không hoàn tất startup; thông báo lỗi chứa thông tin violation để xác định module nguồn và type nội bộ đang bị tham chiếu.

Kết quả mong đợi:

| Thành phần | Kết quả |
|---|---|
| Runtime artifact có trên classpath | Có |
| `spring.modulith.runtime.verification-enabled` | `true` |
| `orders` tham chiếu `catalog.internal.ProductVisibilityPolicy` | Vi phạm |
| Ứng dụng hoàn tất startup | Không |

Thông báo cụ thể có thể khác theo phiên bản và cách Spring Boot trình bày lỗi khởi tạo bean. Hãy đọc phần violation do Spring Modulith báo cáo, thay vì chỉ dựa vào dòng lỗi cuối cùng của stack trace.

## 6. Sửa dependency bằng API công khai

Module `catalog` cần quyết định chức năng nào thực sự được phép sử dụng từ bên ngoài. Thay vì công khai policy nội bộ, hãy tạo hợp đồng ở base package.

Tạo `ProductCatalog.java` trong `com.example.shop.catalog`:

```java
package com.example.shop.catalog;

public interface ProductCatalog {

    boolean isAvailableForSale(String sku);
}
```

Tạo implementation trong `catalog/internal`:

```java
package com.example.shop.catalog.internal;

import com.example.shop.catalog.ProductCatalog;
import org.springframework.stereotype.Service;

@Service
class DefaultProductCatalog implements ProductCatalog {

    @Override
    public boolean isAvailableForSale(String sku) {
        return ProductVisibilityPolicy.isVisible(sku);
    }
}
```

`ProductVisibilityPolicy` vẫn là chi tiết nội bộ. Chỉ `DefaultProductCatalog` sử dụng nó bên trong module sở hữu.

Cập nhật `OrderService` để inject hợp đồng công khai:

```java
package com.example.shop.orders.internal;

import com.example.shop.catalog.ProductCatalog;
import org.springframework.stereotype.Service;

@Service
public class OrderService {

    private final ProductCatalog productCatalog;

    public OrderService(ProductCatalog productCatalog) {
        this.productCatalog = productCatalog;
    }

    public boolean canPlaceOrder(String sku) {
        return productCatalog.isAvailableForSale(sku);
    }
}
```

Dependency của `orders` giờ hướng đến `ProductCatalog` trong base package của `catalog`. Implementation nội bộ được Spring inject thông qua interface; consumer không cần import hoặc biết `ProductVisibilityPolicy`.

## 7. Khởi động lại và xác nhận thành công

Giữ nguyên dependency runtime và property `verification-enabled=true`, sau đó khởi động lại ứng dụng:

```powershell
./gradlew bootRun
```

Khi dependency nội bộ đã được thay bằng API công khai, runtime verifier không còn phát hiện vi phạm package boundary này. Nếu không có vi phạm kiến trúc khác, ứng dụng có thể hoàn tất startup.

Kết quả mong đợi:

| Thành phần | Kết quả |
|---|---|
| Runtime artifact có trên classpath | Có |
| Runtime verification được bật | Có |
| `orders` tham chiếu `catalog.ProductCatalog` | Hợp lệ |
| `orders` tham chiếu `catalog.internal` | Không còn |
| Ứng dụng hoàn tất startup | Có, nếu không còn violation khác |

Nếu ứng dụng vẫn dừng, hãy đọc violation tiếp theo. Có thể còn chu trình module, dependency không nằm trong `allowedDependencies` hoặc một tham chiếu tới internal package khác.

## 8. Runtime verification kiểm tra những gì?

Runtime verifier sử dụng application module model và các quy tắc verification của Spring Modulith. Các quy tắc cốt lõi bao gồm:

- **Không có chu trình ở cấp module:** dependency giữa các module phải tạo thành directed acyclic graph.
- **Truy cập qua API:** module không được tham chiếu type trong internal package của closed module khác.
- **Allowed dependencies:** nếu module khai báo `allowedDependencies`, dependency thực tế phải nằm trong allow-list.

Nếu dự án có các kiểm tra bổ sung được cấu hình qua `VerificationOptions`, các options đó có thể được cung cấp cho runtime verifier thông qua cấu hình bean phù hợp. Phạm vi bài thực hành này tập trung vào việc bật runtime verification và xử lý quy tắc module cốt lõi.

Runtime verification không thay thế kiểm thử nghiệp vụ, kiểm thử tích hợp, kiểm tra database schema hoặc xác nhận hệ thống bên ngoài đang hoạt động. Nó xác nhận application module arrangement tại thời điểm khởi động.

## 9. Runtime verification khác gì ApplicationModules.verify() trong test?

Hai cách kiểm tra dùng chung mô hình và quy tắc kiến trúc, nhưng khác nhau ở thời điểm và mục đích:

| Tiêu chí | `ApplicationModules.verify()` trong test | Runtime verification |
|---|---|---|
| Thời điểm | Khi test được thực thi | Khi ứng dụng Spring Boot khởi động |
| Cách kích hoạt | Gọi trực tiếp trong test | Thêm `spring-modulith-runtime` và bật property |
| Kết quả khi có violation | Bài test thất bại | Ứng dụng không hoàn tất startup |
| Mục đích | Phát hiện lỗi sớm trong quá trình phát triển/CI | Bảo vệ ứng dụng ở môi trường chạy thực tế |
| Phạm vi | Mô hình được tạo trong test classpath | Mô hình được tạo từ production runtime classpath và cấu hình production |

Nên giữ test kiến trúc trong CI để nhận phản hồi sớm. Runtime verification bổ sung một lớp bảo vệ khi ứng dụng được khởi động trong môi trường triển khai.

## 10. Lưu ý với custom module detection

Nếu ứng dụng sử dụng `ApplicationModuleDetectionStrategy` tùy chỉnh hoặc metadata phát hiện module chỉ được khai báo trong test sources, runtime verifier sẽ không tự nhìn thấy cấu hình test-only đó.

Các customization cần thiết cho runtime phải nằm trong production sources và production configuration. Ví dụ:

- Implementation `ApplicationModuleDetectionStrategy` nằm trong `src/main/java`.
- Property `spring.modulith.detection-strategy` nằm trong `src/main/resources/application.properties` hoặc cấu hình môi trường production tương ứng.
- Package metadata như `@ApplicationModule` được biên dịch cùng ứng dụng.

Nếu test và runtime phát hiện module theo hai chiến lược khác nhau, hai môi trường có thể tạo ra model khác nhau. Hãy giữ cấu hình module detection nhất quán giữa test và production.

## 11. Xử lý tình huống runtime verification không chạy

| Hiện tượng | Nguyên nhân cần kiểm tra | Cách xử lý |
|---|---|---|
| Ứng dụng khởi động dù có dependency vi phạm | Property chưa được bật hoặc không được nạp | Kiểm tra `spring.modulith.runtime.verification-enabled=true` trong effective configuration |
| Không có runtime verifier | `spring-modulith-runtime` không có trên runtime classpath | Thêm `runtimeOnly`/Maven runtime dependency hoặc kiểm tra starter đã kéo dependency này chưa |
| Test phát hiện module khác với runtime | Custom detection strategy chỉ tồn tại trong test sources | Chuyển customization cần thiết sang production sources |
| Startup dừng với module cycle | Dependency graph có chu trình | Truy vết cạnh và thay đổi hướng phụ thuộc hoặc event contract |
| Startup dừng vì internal package access | Module tham chiếu type trong sub-package nội bộ | Dùng base package API hoặc named interface |
| Startup dừng vì dependency không được phép | `allowedDependencies` không bao gồm module/interface đích | Thiết kế lại hướng dependency hoặc cập nhật allow-list có chủ đích |

Để tạm thời tắt kiểm tra trong một môi trường cụ thể, có thể đặt property thành `false`; tuy nhiên, hãy duy trì một môi trường hoặc pipeline có bật kiểm tra để vi phạm không bị bỏ sót lâu dài.

## 12. Bài tập tự kiểm tra

Thực hiện các thay đổi sau trên ứng dụng mẫu:

1. Thêm `spring-modulith-runtime` vào runtime classpath nếu chưa có.
2. Bật `spring.modulith.runtime.verification-enabled=true`.
3. Tạo tham chiếu từ `orders` tới một class `public` nằm trong `catalog.internal`.
4. Khởi động ứng dụng và ghi lại module nguồn, module đích cùng lý do vi phạm.
5. Tạo API công khai trong base package hoặc named interface của `catalog`.
6. Chuyển `orders` sang sử dụng API đó.
7. Khởi động lại và xác nhận ứng dụng hoàn tất startup.
8. Tạo thêm một dependency cycle hoặc vi phạm `allowedDependencies`, quan sát runtime verifier phát hiện rồi sửa lại.
9. Giữ một bài test `ApplicationModules.verify()` để kiểm tra cùng quy tắc trong CI.

Checklist hoàn thành:

- [ ] Runtime artifact có trên runtime classpath.
- [ ] Property verification được bật trong cấu hình ứng dụng.
- [ ] Ứng dụng dừng startup khi có violation được tái hiện.
- [ ] Dependency sai được thay bằng API công khai.
- [ ] Ứng dụng khởi động thành công sau khi sửa.
- [ ] Test kiến trúc vẫn được duy trì trong CI.

Runtime verification giúp application module arrangement trở thành một điều kiện của quá trình khởi động. Khi cấu trúc package hoặc dependency bị thay đổi làm boundary không còn hợp lệ, ứng dụng phát hiện vấn đề ngay khi khởi động thay vì tiếp tục chạy với một modular monolith có ranh giới sai.

Tài liệu tham khảo: [Spring Modulith 2.2.0 – Runtime Support](https://docs.spring.io/spring-modulith/reference/runtime.html), [Spring Modulith 2.2.0 – Configuration Properties](https://docs.spring.io/spring-modulith/reference/appendix.html#configuration-properties), [Spring Modulith – Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html).
