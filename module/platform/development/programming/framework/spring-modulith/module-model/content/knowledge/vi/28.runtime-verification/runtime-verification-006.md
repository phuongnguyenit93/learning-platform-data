# Verification test khác verification runtime

Spring Modulith có thể kiểm tra ranh giới module trong test suite hoặc khi ứng dụng khởi động. Hai cách dùng cùng mô hình module và các quy tắc kiến trúc cốt lõi, nhưng chạy ở hai thời điểm khác nhau và bảo vệ hai giai đoạn khác nhau của vòng đời phần mềm.

`ApplicationModules.verify()` thường được gọi trong một JUnit test để phát hiện vi phạm trước khi thay đổi được tích hợp. Runtime verification sử dụng artifact `spring-modulith-runtime` và cấu hình `spring.modulith.runtime.verification-enabled=true` để xác minh cấu trúc module khi Spring Boot khởi động. Nếu phát hiện vi phạm, ứng dụng không khởi động thành công.

Điều cần hiểu rõ là runtime verification kiểm tra mô hình kiến trúc lúc startup. Nó không theo dõi mọi lời gọi phương thức khi ứng dụng đang chạy, cũng không thay thế tracing, metrics hay kiểm thử hành vi nghiệp vụ.

## 1. Verification trong test suite

Architecture test là cách phổ biến để kiểm tra cấu trúc module. Tạo một test JUnit trong source set test:

```java
package com.example;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void verifiesApplicationModuleStructure() {
        ApplicationModules.of(Application.class).verify();
    }
}
```

`ApplicationModules.of(Application.class)` tạo mô hình các application module từ package gốc của ứng dụng. `verify()` kiểm tra các quy tắc như:

- Không có phụ thuộc vòng giữa các application module.
- Module chỉ truy cập API công khai của module khác, không tham chiếu kiểu thuộc package nội bộ.
- Nếu module khai báo `allowedDependencies`, các phụ thuộc phải tuân theo danh sách được cho phép.
- Các kiểm tra bổ sung được cấu hình qua `VerificationOptions`, nếu có.

Nếu có vi phạm, `verify()` ném lỗi và JUnit đánh dấu test thất bại. Build tool và CI có thể dùng kết quả đó để chặn một thay đổi kiến trúc không hợp lệ trước khi triển khai.

Test này không cần khởi tạo toàn bộ `ApplicationContext`. Nó phân tích cấu trúc mã nguồn và các quan hệ kiểu để xác minh kiến trúc. Vì vậy, nó thường nhẹ hơn một bài `@SpringBootTest` và có thể chạy trong test task thông thường.

## 2. Runtime verification khi ứng dụng khởi động

Spring Modulith cung cấp runtime support thông qua artifact `spring-modulith-runtime`. Khi artifact này có trên runtime classpath, Spring Boot auto-configuration đăng ký các thành phần hỗ trợ truy cập mô hình module. Runtime verifier sẽ xác minh cấu trúc module lúc startup nếu property bật tính năng được đặt thành `true`.

Với Maven, khai báo dependency trong `pom.xml`:

```xml
<dependency>
    <groupId>org.springframework.modulith</groupId>
    <artifactId>spring-modulith-runtime</artifactId>
    <scope>runtime</scope>
</dependency>
```

Với Gradle:

```groovy
dependencies {
    runtimeOnly 'org.springframework.modulith:spring-modulith-runtime'
}
```

Sau đó bật runtime verification trong `application.yml`:

```yaml
spring:
  modulith:
    runtime:
      verification-enabled: true
```

Hoặc trong `application.properties`:

```properties
spring.modulith.runtime.verification-enabled=true
```

Khi property được bật và `spring-modulith-runtime` có trên classpath, `RuntimeApplicationModuleVerifier` kiểm tra mô hình module trong quá trình khởi động. Nếu phát hiện vi phạm, Spring Boot dừng quá trình khởi tạo và ứng dụng không đi vào trạng thái sẵn sàng phục vụ.

Runtime verification được tắt mặc định. Chỉ thêm property mà không có artifact runtime sẽ không đăng ký runtime verifier. Tương tự, thêm artifact nhưng không bật property sẽ không tự động kích hoạt việc xác minh cấu trúc lúc startup.

Runtime support chính thức có từ Spring Modulith 2.0. Hãy kiểm tra phiên bản thư viện và ma trận tương thích Spring Boot của dự án trước khi thêm dependency này.

## 3. So sánh hai cơ chế

| Tiêu chí | Verification trong test | Runtime verification |
|---|---|---|
| Thời điểm chạy | Khi test task thực thi | Khi ứng dụng khởi động |
| Cách kích hoạt | Gọi `ApplicationModules.verify()` trong JUnit | Thêm `spring-modulith-runtime` và bật property |
| Mục tiêu chính | Phát hiện vi phạm trong quá trình phát triển và CI | Ngăn ứng dụng có cấu trúc module vi phạm khởi động |
| Kết quả khi có vi phạm | Test thất bại, build/CI có thể thất bại | Quá trình khởi động ứng dụng bị hủy |
| Có cần chạy ứng dụng Spring Boot đầy đủ? | Không | Có, vì verifier được đăng ký trong runtime auto-configuration |
| Mặc định | Chỉ chạy khi test được gọi | Tắt nếu property không được bật |

Hai cơ chế không loại trừ nhau. Architecture test cung cấp phản hồi sớm cho lập trình viên và pull request. Runtime verification tạo thêm một lớp bảo vệ ở môi trường chạy ứng dụng, ví dụ khi một artifact được đóng gói hoặc triển khai bằng một pipeline khác với pipeline đã chạy test.

## 4. Cả hai kiểm tra điều gì?

Hai cơ chế xác minh dựa trên mô hình module của Spring Modulith. Ví dụ, module `shipping` phụ thuộc trực tiếp vào implementation nội bộ của `inventory`:

```java
package com.example.shipping;

import com.example.inventory.internal.InventoryService;
import org.springframework.stereotype.Service;

@Service
class ShippingService {

    private final InventoryService inventory;

    ShippingService(InventoryService inventory) {
        this.inventory = inventory;
    }
}
```

Giả sử `InventoryService` nằm trong package nội bộ không được công khai. `ApplicationModules.verify()` có thể phát hiện tham chiếu này trong architecture test. Khi runtime verification được bật, verifier cũng xác minh mô hình module lúc ứng dụng khởi động và phát hiện vi phạm tương tự.

Cách sửa là để `inventory` công khai một hợp đồng phù hợp, ví dụ `InventoryOperations` trong package gốc hoặc trong named interface `inventory::api`, rồi để `shipping` phụ thuộc vào hợp đồng đó. Sau khi sửa, test và lần khởi động có runtime verification đều phải vượt qua.

## 5. Runtime verification không phải giám sát mọi tương tác

Từ “runtime” dễ khiến người đọc nghĩ rằng Spring Modulith liên tục quan sát từng lần module gọi nhau. Runtime verification không hoạt động theo cách đó. Nó xác minh cấu trúc module trong giai đoạn khởi động dựa trên mô hình được xây dựng từ ứng dụng.

Nếu mục tiêu là quan sát tương tác giữa các module sau khi ứng dụng đã chạy, hãy xem xét Spring Modulith observability. Tính năng observability có thể tạo Micrometer spans cho các lời gọi đến Spring bean thuộc API module, ghi nhận loại tương tác và module liên quan. Các spans này có thể được gửi đến hệ thống tracing tương thích.

| Nhu cầu | Cơ chế phù hợp |
|---|---|
| Kiểm tra ranh giới module trong pull request | Architecture test với `ApplicationModules.verify()` |
| Chặn ứng dụng khởi động khi cấu trúc module vi phạm | Runtime verification |
| Quan sát lời gọi bean và tương tác module trong production | Spring Modulith observability và tracing |
| Kiểm tra một luồng nghiệp vụ có kết quả đúng | Unit test, module integration test hoặc end-to-end test |

Không nên xem runtime verification là một cơ chế bảo mật hoặc sandbox. Nó bảo vệ quy ước kiến trúc module đã được mô hình hóa; nó không thay thế phân quyền, kiểm soát truy cập dữ liệu, kiểm thử nghiệp vụ hay giám sát vận hành.

## 6. Chọn nơi bật runtime verification

Vì runtime verification có thể khiến ứng dụng từ chối khởi động, hãy xác định môi trường và quy trình triển khai trước khi bật.

Một cấu hình thường gặp là bật ở môi trường phát triển, staging và production sau khi architecture test đã ổn định. Nếu production cần đảm bảo artifact luôn tuân thủ ranh giới module, runtime verification có thể là lớp kiểm tra bổ sung ngay khi tiến trình bắt đầu. Trong môi trường mà một lỗi cấu trúc có thể khiến nhiều replica cùng không khởi động, nhóm vận hành cần hiểu rõ thông báo lỗi và có cách rollback artifact hoặc cấu hình.

Ví dụ cấu hình theo profile:

```yaml
# application-staging.yml
spring:
  modulith:
    runtime:
      verification-enabled: true
```

Hãy bảo đảm artifact `spring-modulith-runtime` có trong runtime classpath của profile triển khai đó. Cấu hình property riêng lẻ không thể thay thế dependency.

## 7. Đồng bộ cấu hình module giữa test và runtime

Runtime support sử dụng mô hình module trong ứng dụng khi khởi động. Nếu dự án tùy chỉnh cách phát hiện module, các tùy chỉnh cần có trong production sources để runtime feature nhận được cùng cấu hình. Không đặt toàn bộ cấu hình module detection trong test source set rồi kỳ vọng runtime verifier tự nhìn thấy.

Khi test và runtime cho kết quả khác nhau, hãy kiểm tra:

1. Cùng phiên bản Spring Modulith được sử dụng cho các dependency liên quan.
2. `Application.class` nằm ở package gốc mà nhóm dự định dùng để phát hiện module.
3. Các annotation `@ApplicationModule`, `@NamedInterface` và `allowedDependencies` có trong artifact production.
4. Tùy chỉnh module detection cần thiết được khai báo trong production sources.
5. Dependency `spring-modulith-runtime` thực sự có mặt trên runtime classpath.
6. Property `spring.modulith.runtime.verification-enabled` có giá trị `true` trong môi trường đang chạy.

Nếu dùng `VerificationOptions` tùy chỉnh, hãy tổ chức cấu hình theo cách mà runtime auto-configuration có thể nhận được. Có thể đăng ký `VerificationOptions` như một bean trong application context để runtime verifier sử dụng; tránh chỉ khai báo options trong một test helper.

## 8. Quy trình áp dụng hai lớp kiểm tra

Một quy trình phù hợp cho modular monolith có thể gồm:

1. Thay đổi mã nguồn module.
2. Chạy architecture test trong CI.
3. Nếu test thất bại, sửa vi phạm trước khi đóng gói.
4. Đóng gói và triển khai artifact.
5. Runtime verification kiểm tra cấu trúc module lúc startup.
6. Nếu startup thất bại, đọc lỗi xác minh, xem lại cấu trúc hoặc rollback artifact/cấu hình.

Architecture test là bước kiểm tra thường xuyên trong CI. Runtime verification bổ sung một lần xác minh khi artifact thực sự khởi động. Khi cả hai cùng được cấu hình, một vi phạm được phát hiện ở CI trước khi triển khai; nếu một thay đổi hoặc cấu hình khác lọt qua quy trình build, runtime verifier vẫn có thể chặn ứng dụng khởi động.

## 9. Bài tập thực hành

1. Tạo `ModularityTests` và gọi `ApplicationModules.of(Application.class).verify()` trong một test JUnit.
2. Chạy test task và xác nhận vi phạm package nội bộ khiến test thất bại.
3. Thêm dependency `spring-modulith-runtime` vào runtime classpath.
4. Bật `spring.modulith.runtime.verification-enabled=true` trong profile staging.
5. Khởi động ứng dụng với cấu trúc hợp lệ và xác nhận ứng dụng khởi động thành công.
6. Tạm tạo một phụ thuộc không hợp lệ, chạy architecture test và quan sát test thất bại.
7. Khởi động ứng dụng với runtime verification bật và quan sát quá trình startup bị hủy do vi phạm.
8. Khôi phục API module hợp lệ, chạy lại test và khởi động ứng dụng để xác nhận cả hai cơ chế đều vượt qua.

Sau bài tập, bạn cần giải thích được khác biệt giữa thời điểm và tác động của verification test với runtime verification, các dependency và property cần thiết để bật runtime verifier, và vì sao runtime verification không phải cơ chế quan sát mọi lời gọi khi ứng dụng đang phục vụ request.

## Tài liệu tham khảo

- [Spring Modulith Runtime Support](https://docs.spring.io/spring-modulith/reference/runtime.html)
- [Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html)
- [SpringModulithRuntimeProperties API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/runtime/autoconfigure/SpringModulithRuntimeProperties.html)
- [Production-ready Features – Observing Application Modules](https://docs.spring.io/spring-modulith/reference/production-ready.html)
