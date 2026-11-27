# Kiểm tra model lúc startup

Trong một modular monolith, module model mô tả các application module, API được công bố và quan hệ dependency giữa chúng. Nhóm thường kiểm tra model bằng `ApplicationModules.verify()` trong architecture test để phát hiện dependency cycle, truy cập package nội bộ hoặc dependency vượt khỏi allowlist. Tuy nhiên, một bài test chỉ chạy trong CI không tự bảo đảm rằng mọi lần triển khai đều khởi động với cấu hình và classpath đúng như môi trường đã kiểm tra.

Spring Modulith cung cấp runtime verification để kiểm tra application module arrangement ngay trong quá trình khởi động ứng dụng. Khi được bật, framework tự xây dựng module model và xác minh các quy tắc kiến trúc; nếu phát hiện vi phạm, quá trình khởi động bị dừng. Đây là một lớp bảo vệ bổ sung ở runtime, giúp ứng dụng không tiếp tục chạy với module arrangement không hợp lệ.

## 1. Runtime verification giải quyết vấn đề gì?

Giả sử ứng dụng bán hàng có các module:

```text
com.acme.shop
├── ShopApplication.java
├── order
│   ├── OrderManagement.java
│   └── internal
│       └── OrderRepository.java
├── inventory
│   └── InventoryManagement.java
└── shipping
    └── ShippingService.java
```

Trong quá trình phát triển, nhóm có thể đã chạy architecture test và xác nhận:

- Không có chu trình dependency giữa các module.
- Module chỉ truy cập package API hoặc Named Interface đã công bố.
- Dependency tuân thủ `allowedDependencies` nếu module có khai báo allowlist.

Sau đó, một thay đổi có thể vô tình đưa reference tới `order.internal.OrderRepository` vào `shipping`. Nếu architecture test không được chạy trong một pipeline nào đó, hoặc môi trường triển khai có classpath/configuration khác, vi phạm có thể đi tới bước khởi động ứng dụng.

Runtime verification thêm một lần kiểm tra tại chính ứng dụng đang khởi động. Khi module model vi phạm quy tắc, ứng dụng không hoàn tất startup thành công. Nhờ vậy, một artifact chứa module arrangement sai có thể bị phát hiện ngay khi được triển khai.

## 2. Thêm `spring-modulith-runtime` vào runtime classpath

Runtime support được cung cấp bởi artifact `spring-modulith-runtime`. Với Gradle, có thể khai báo:

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

Nếu dự án quản lý phiên bản bằng Spring Modulith BOM, không cần ghi version riêng cho artifact. Một số starter đã đưa runtime support vào dependency graph; ví dụ `spring-modulith-starter-core` bao gồm `spring-modulith-runtime` ở runtime scope. Hãy kiểm tra starter đang sử dụng để tránh khai báo trùng không cần thiết.

Điểm quan trọng là runtime artifact phải có mặt trong runtime classpath của ứng dụng được triển khai. Chỉ thêm dependency vào `testImplementation` hoặc test scope không bật được runtime verification trong production application.

## 3. Bật kiểm tra module model khi startup

Sau khi có runtime support, bật thuộc tính `spring.modulith.runtime.verification-enabled`:

```yaml
spring:
  modulith:
    runtime:
      verification-enabled: true
```

Hoặc dùng `application.properties`:

```properties
spring.modulith.runtime.verification-enabled=true
```

Theo cấu hình mặc định của Spring Modulith 2.2, thuộc tính này có giá trị `false`. Vì vậy, chỉ thêm `spring-modulith-runtime` vào classpath chưa có nghĩa runtime verification đã tự động được bật. Cần bật property rõ ràng trong cấu hình của môi trường muốn kiểm tra.

Khi property là `true`, Spring Boot auto-configuration đăng ký `RuntimeApplicationModuleVerifier`. Thành phần này xác minh application module arrangement trong quá trình startup và làm startup thất bại nếu phát hiện violation.

## 4. Luồng hoạt động khi ứng dụng khởi động

Có thể hình dung luồng tổng quát như sau:

```text
Spring Boot bắt đầu khởi động
        |
        v
Nạp runtime auto-configuration
        |
        v
Tạo ApplicationModulesRuntime
        |
        v
Phát hiện application module arrangement
        |
        v
RuntimeApplicationModuleVerifier
        |
        v
Kiểm tra dependency và package boundary
        |
        +---- Có violation ----> Startup thất bại
        |
        +---- Không có lỗi ----> Ứng dụng tiếp tục startup
```

Runtime support cũng đăng ký `SpringBootApplicationRuntime` để xác định lớp ứng dụng chính và cung cấp `ApplicationModulesRuntime` để truy cập module model trong runtime. `RuntimeApplicationModuleVerifier` là thành phần chịu trách nhiệm kiểm tra cấu trúc khi property được bật.

Runtime verification chạy trong quá trình khởi động ứng dụng. Nó không phải một monitor liên tục quét code sau mỗi request, cũng không phải cơ chế kiểm tra dữ liệu nghiệp vụ trong database. Module model được suy ra từ code, package, metadata và cấu hình detection của ứng dụng.

## 5. Những quy tắc kiến trúc được kiểm tra

Runtime verifier sử dụng module arrangement của Spring Modulith để kiểm tra các ràng buộc kiến trúc mà module model hỗ trợ. Các nhóm quy tắc quan trọng gồm:

| Quy tắc | Điều kiện |
| --- | --- |
| Không có module dependency cycle | Đồ thị dependency giữa application module phải là directed acyclic graph |
| Chỉ truy cập API package đã công bố | Module tiêu thụ không được tham chiếu type trong package nội bộ của closed module |
| Chỉ dùng dependency được cho phép | Nếu module khai báo `allowedDependencies`, dependency tới module hoặc Named Interface khác phải nằm trong allowlist |
| Verification bổ sung | Các verification được tích hợp hoặc đăng ký qua `VerificationOptions` có thể được thực thi tùy classpath và cấu hình |

Ví dụ, nếu `shipping` tham chiếu `order.internal.OrderRepository`, runtime verification có thể phát hiện việc truy cập package nội bộ. Nếu `shipping` gọi API của `order` nhưng module chưa cho phép dependency đó trong `allowedDependencies`, verification cũng có thể báo lỗi.

Runtime verification kiểm tra cấu trúc module đã được phát hiện. Nó không tự suy ra danh sách module nghiệp vụ mà nhóm mong đợi nếu package bị bỏ sót khỏi detection strategy. Nếu ứng dụng dùng explicit detection hoặc custom detection, cần có completeness test riêng để xác nhận mọi module dự kiến đều xuất hiện trong model.

## 6. Điều gì xảy ra khi có violation?

Khi verifier phát hiện violation, startup bị abort. Ứng dụng không được xem là khởi động thành công, do đó nền tảng triển khai không nên đưa instance đó vào phục vụ traffic.

Thông tin lỗi được trình bày qua exception và failure analysis của Spring Boot. Diagnostic thường giúp xác định module nguồn, module đích, type hoặc package tạo ra dependency không hợp lệ. Hãy đọc toàn bộ nguyên nhân trước khi sửa; một thay đổi có thể đồng thời vi phạm package boundary và `allowedDependencies`.

Ví dụ, nếu log cho biết `shipping` tham chiếu `order.internal.OrderRepository`, cách xử lý thường là:

1. Xác định nhu cầu thật sự của `shipping`: truy vấn thông tin đơn hàng hay phản ứng với một sự kiện?
2. Nếu cần truy vấn, công bố một API nghiệp vụ hoặc Named Interface từ `order`.
3. Nếu chỉ cần phản ứng, công bố event contract và đăng ký listener.
4. Khai báo `allowedDependencies` ở phía consumer nếu module có dùng allowlist.
5. Chạy architecture test và khởi động lại ứng dụng để xác nhận module model hợp lệ.

Không nên khắc phục bằng cách đánh dấu module `OPEN` hoặc đưa toàn bộ package `internal` thành API chỉ để startup vượt qua. Hãy sửa boundary theo nhu cầu nghiệp vụ và chỉ mở module khi đó là quyết định kiến trúc có chủ đích.

## 7. Runtime verification và architecture test khác nhau thế nào?

Hai cơ chế sử dụng cùng module model nhưng phục vụ các thời điểm khác nhau:

| Tiêu chí | Architecture test | Runtime verification |
| --- | --- | --- |
| Thời điểm | Khi chạy test trong local hoặc CI | Khi ứng dụng khởi động |
| Cách kích hoạt | Gọi `ApplicationModules.verify()` trong test | Có `spring-modulith-runtime` và bật `spring.modulith.runtime.verification-enabled=true` |
| Mục tiêu | Phát hiện lỗi sớm trước khi đóng gói hoặc triển khai | Chặn ứng dụng khởi động với module arrangement vi phạm |
| Phạm vi sử dụng | Có thể tạo nhiều test, options và assertion riêng | Chạy theo runtime module model và cấu hình của ứng dụng |
| Diagnostic | Test report và exception trong test runner | Startup exception và Spring Boot failure analysis |

Architecture test nên tiếp tục là lớp kiểm tra chính trong CI vì nó cho developer phản hồi sớm. Runtime verification bổ sung một hàng rào tại môi trường khởi động, đặc biệt hữu ích khi artifact được triển khai qua nhiều môi trường hoặc có cấu hình module detection riêng.

Runtime verification không thay thế test. Nếu chỉ bật runtime verification, lỗi kiến trúc có thể chỉ được phát hiện khi instance bắt đầu khởi động ở môi trường triển khai. Điều đó làm vòng phản hồi chậm hơn so với việc phát hiện trong CI.

## 8. Đồng bộ module detection giữa test và runtime

Module model phụ thuộc vào detection strategy và các tùy chỉnh liên quan. Nếu test dùng custom `ApplicationModuleDetectionStrategy` nhưng runtime không có strategy đó, hai môi trường có thể phát hiện tập module khác nhau.

Spring Modulith lưu ý rằng các tùy chỉnh module detection dùng cho runtime features cần được đặt trong production sources. Ví dụ, nếu cấu hình:

```properties
spring.modulith.detection-strategy=com.acme.shop.architecture.BusinessModuleDetectionStrategy
```

thì class `BusinessModuleDetectionStrategy` phải nằm trên runtime classpath, không chỉ nằm trong `src/test/java`. Marker annotation mà strategy sử dụng cũng phải có mặt trong production code và được biên dịch cùng ứng dụng.

Hãy duy trì các điều kiện sau:

- Test và runtime dùng cùng detection strategy.
- Các package annotation và metadata module được đóng gói trong artifact.
- Các cấu hình `allowedDependencies`, `sharedModules` và Named Interface được giữ nhất quán.
- Test có assertion về danh sách module mong đợi nếu ứng dụng dùng explicit/custom detection.

Việc đồng bộ này giúp tránh tình huống architecture test kiểm tra một module model, còn runtime verifier lại kiểm tra một module model khác.

## 9. Kết hợp runtime verification với `ApplicationModuleInitializer`

Artifact `spring-modulith-runtime` còn cung cấp cơ chế gọi các bean triển khai `ApplicationModuleInitializer` khi có `ApplicationStartedEvent`. Cơ chế này có mục tiêu khác với runtime verifier:

- Runtime verifier kiểm tra module arrangement và có thể làm startup thất bại khi có violation.
- `ApplicationModuleInitializer` chạy logic khởi tạo riêng của module theo thứ tự phù hợp với dependency graph.

Ví dụ:

```java
package com.acme.shop.order;

import org.springframework.modulith.ApplicationModuleInitializer;
import org.springframework.stereotype.Component;

@Component
class OrderModuleInitializer implements ApplicationModuleInitializer {

    @Override
    public void initialize() {
        // Khởi tạo dữ liệu hoặc trạng thái riêng của module order.
    }
}
```

Nếu module `shipping` phụ thuộc vào `order`, initializer của `order` được sắp xếp chạy trước initializer của `shipping`, theo module dependency structure. Các initializer chỉ được gọi khi `spring-modulith-runtime` có mặt trên classpath.

Không cần triển khai `ApplicationModuleInitializer` chỉ để bật runtime verification. Đây là hai tính năng riêng được cung cấp bởi cùng runtime support artifact.

## 10. Bật theo môi trường và quản lý vận hành

Vì runtime verification làm startup thất bại khi có violation, nhóm nên quyết định rõ môi trường nào bật property. Ví dụ, có thể bật trong cấu hình chung của ứng dụng:

```yaml
spring:
  modulith:
    runtime:
      verification-enabled: true
```

Hoặc ghi rõ trong profile triển khai:

```yaml
# application-production.yml
spring:
  modulith:
    runtime:
      verification-enabled: true
```

Nếu dùng profile, hãy chắc chắn profile đó thực sự được kích hoạt trong deployment. Tránh để property bị ghi đè thành `false` bởi biến môi trường hoặc cấu hình ngoài mà không được quan sát.

Trong hệ thống nhiều instance, mỗi instance khởi động đều thực hiện kiểm tra theo cấu hình của chính nó. Nếu artifact có violation, các instance mới có thể không khởi động thành công. Điều này giúp chặn phiên bản sai, nhưng cũng có nghĩa pipeline cần chạy architecture test trước khi triển khai để tránh phát hiện lỗi muộn ở startup.

Hãy theo dõi startup logs và trạng thái readiness của instance. Không nên đánh đồng một tiến trình đã được tạo với một ứng dụng đã khởi động thành công và sẵn sàng nhận traffic.

## 11. Chẩn đoán khi runtime verification không chạy

Nếu ứng dụng vẫn khởi động dù nhóm mong đợi module violation phải làm startup thất bại, kiểm tra lần lượt:

| Dấu hiệu | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Không có thông báo runtime verification | Property vẫn là `false` hoặc không được nạp | Kiểm tra effective configuration và profile đang hoạt động |
| Runtime verifier không được đăng ký | `spring-modulith-runtime` không có trong runtime classpath | Kiểm tra dependency graph của artifact được đóng gói |
| Test và runtime phát hiện module khác nhau | Custom detection strategy chỉ có trong test source set | Chuyển strategy và marker cần thiết sang production sources |
| Ứng dụng thất bại startup sau khi bật property | Có architectural violation thực tế | Đọc failure analysis, module nguồn/đích và target package |
| Test pass nhưng runtime fail | Test dùng options hoặc module model khác runtime | Đồng bộ detection strategy, metadata và cấu hình verification |
| Runtime verification chạy nhưng bỏ sót một module dự kiến | Package không được discovery theo strategy hiện tại | Bổ sung completeness test cho expected module roots |

## 12. Những nhầm lẫn thường gặp

| Nhận định | Cách hiểu chính xác |
| --- | --- |
| Chỉ thêm `spring-modulith-runtime` là tự bật verification | `spring.modulith.runtime.verification-enabled` mặc định là `false`; cần bật rõ ràng |
| Runtime verification chạy liên tục khi ứng dụng phục vụ request | Nó kiểm tra module arrangement trong quá trình startup |
| Runtime verifier thay thế architecture test | Test vẫn cần thiết để phát hiện lỗi sớm trong CI |
| `ApplicationModuleInitializer` là verifier | Initializer chạy logic khởi tạo module; verifier kiểm tra module arrangement |
| Runtime verification kiểm tra dữ liệu database và nghiệp vụ | Nó kiểm tra cấu trúc module và dependency từ code/model |
| Custom detection strategy chỉ cần có trong test | Runtime features cần tùy chỉnh detection có trong production sources |
| Vi phạm chỉ tạo warning nhưng ứng dụng vẫn chạy | Runtime verifier được cấu hình để abort startup khi phát hiện violation |
| `spring-modulith-runtime` luôn phải khai báo trực tiếp | Nếu starter như `spring-modulith-starter-core` đã kéo runtime artifact vào, không cần thêm dependency trùng |

## 13. Ghi nhớ

Để kiểm tra module model lúc startup, thêm `spring-modulith-runtime` vào runtime classpath và bật `spring.modulith.runtime.verification-enabled=true`. Property mặc định là `false`. Khi được bật, Spring Boot auto-configuration đăng ký `RuntimeApplicationModuleVerifier` để xác minh application module arrangement và abort startup nếu có violation.

Runtime verification kiểm tra các ràng buộc như module dependency cycle, truy cập package nội bộ và `allowedDependencies`. Nó bổ sung cho architecture test chạy trong CI, không thay thế test và không phải monitor liên tục sau khi ứng dụng đã chạy. Nếu dùng custom module detection, hãy đặt strategy và marker trong production sources để test và runtime xây dựng cùng module model.

`spring-modulith-runtime` còn hỗ trợ `ApplicationModulesRuntime`, `SpringBootApplicationRuntime` và gọi `ApplicationModuleInitializer` theo thứ tự dependency khi ứng dụng phát `ApplicationStartedEvent`. Đây là các tính năng liên quan của runtime support nhưng có mục tiêu riêng. Hãy bật runtime verification có chủ đích, quan sát startup/readiness và tiếp tục giữ architecture test trong pipeline để phát hiện vi phạm sớm.

## Tài liệu tham khảo

- [Spring Modulith 2.2 — Runtime Support](https://docs.spring.io/spring-modulith/reference/runtime.html)
- [Spring Modulith 2.2 — Configuration Properties](https://docs.spring.io/spring-modulith/reference/appendix.html)
- [Spring Modulith API — `RuntimeApplicationModuleVerifier`](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/runtime/autoconfigure/SpringModulithRuntimeAutoConfiguration.RuntimeApplicationModuleVerifier.html)
- [Spring Modulith API — `ApplicationModuleInitializer`](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/ApplicationModuleInitializer.html)
- [Spring Modulith — Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html)
