# Giữ test kiến trúc độc lập và dễ chẩn đoán

Architecture test có nhiệm vụ bảo vệ một quy tắc kiến trúc cụ thể, chẳng hạn dependency graph không có chu trình, module chỉ truy cập API được công khai hoặc domain layer không phụ thuộc vào web layer. Khi mỗi test kiểm tra một nhóm quy tắc rõ ràng, có tên dễ hiểu và phạm vi package chính xác, nhóm phát triển có thể xác định nguyên nhân thất bại nhanh hơn.

Với Spring Modulith, nên tách kiểm tra module boundary bằng `ApplicationModules.verify()` khỏi các quy tắc layering riêng của ứng dụng khi chúng có thể được kiểm tra độc lập bằng ArchUnit. Các bài kiểm tra này thường không cần khởi tạo Spring `ApplicationContext`, database hoặc message broker. Chúng chỉ cần phân tích cấu trúc code đã biên dịch, nên có thể chạy nhanh và ổn định trong CI.

Sau bài học, bạn có thể:

- Tổ chức architecture test độc lập với integration test và Spring context test.
- Tách kiểm tra module boundary khỏi các quy tắc layering riêng.
- Đặt tên `ArchRule` để thông báo lỗi nêu rõ quy tắc bị vi phạm.
- Thu hẹp package pattern để tránh bắt nhầm lớp ngoài phạm vi.
- Chọn giữa `ArchRule.check()` độc lập và `VerificationOptions` tích hợp với Spring Modulith.
- Tránh chia sẻ trạng thái kiểm tra khiến kết quả phụ thuộc thứ tự chạy test.

## 1. Mỗi architecture test nên bảo vệ một ý định rõ ràng

Một architecture test tốt trả lời một câu hỏi cụ thể:

- Module graph có không có chu trình không?
- Module có truy cập package nội bộ của module khác không?
- Domain layer có phụ thuộc vào web adapter không?
- Application layer có phụ thuộc vào bootstrap configuration không?
- Adapter có gọi trực tiếp adapter của module khác không?

Nếu gộp tất cả quy tắc vào một test lớn, một lần chạy thất bại có thể tạo ra nhiều thông báo khó phân loại. Tách các nhóm kiểm tra theo ý định giúp tên test chỉ ra khu vực cần xem trước.

Ví dụ, dùng một test riêng cho quy tắc module của Spring Modulith:

```java
package com.acme.shop.architecture;

import com.acme.shop.ShopApplication;
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleStructureTests {

    @Test
    void applicationModulesRespectTheirBoundaries() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
```

Test này tập trung vào module arrangement: chu trình, quyền truy cập package và `allowedDependencies` đã khai báo. Tên test cho biết rõ đây là kiểm tra ranh giới giữa application module.

## 2. Giữ architecture test độc lập với Spring context

`ApplicationModules.of(ShopApplication.class)` phân tích codebase để tạo module model. Lời gọi này không cần khởi động Spring Boot application context. Vì vậy, một architecture test cơ bản thường chỉ cần JUnit và Spring Modulith core.

Không cần thêm `@SpringBootTest` cho test chỉ xác minh package và dependency graph:

```java
@SpringBootTest
class ModuleStructureTests {

    @Test
    void applicationModulesRespectTheirBoundaries() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
```

Annotation `@SpringBootTest` làm test khởi tạo context, có thể kéo theo auto-configuration, bean wiring, cấu hình môi trường và kết nối hạ tầng. Những thành phần đó không cần thiết cho kiểm tra cấu trúc tĩnh và có thể khiến test chậm hoặc thất bại vì một dịch vụ ngoài không liên quan đến quy tắc đang kiểm tra.

Một test kiến trúc tĩnh nên có đặc điểm:

- Không khởi tạo `ApplicationContext` nếu chỉ kiểm tra cấu trúc package và type dependency.
- Không cần database, broker, filesystem bên ngoài hoặc HTTP service.
- Không phụ thuộc profile hay biến môi trường để quyết định kết quả của quy tắc tĩnh.
- Không cần chạy trước một test khác để tạo dữ liệu hoặc thiết lập trạng thái.
- Có thể chạy lặp lại với cùng codebase và cho cùng kết quả.

`@ApplicationModuleTest` có mục đích khác: nó tạo test context cho một module và các dependency được chọn để kiểm tra hành vi của bean, event hoặc tích hợp trong module. Hãy dùng nó cho module integration test; dùng `ApplicationModules.verify()` cho architecture test tĩnh.

## 3. Tách module boundary test khỏi layering rule

Spring Modulith kiểm tra ranh giới application module. ArchUnit cho phép nhóm định nghĩa các quy tắc riêng bên trong module hoặc giữa các layer.

Ví dụ, dự án muốn domain model không phụ thuộc web adapter. Quy tắc này không đồng nghĩa với module boundary, vì cả hai package `domain` và `web` có thể nằm trong cùng một application module.

```java
package com.acme.shop.architecture;

import com.tngtech.archunit.core.domain.JavaClasses;
import com.tngtech.archunit.core.importer.ClassFileImporter;
import com.tngtech.archunit.lang.ArchRule;
import org.junit.jupiter.api.Test;

import static com.tngtech.archunit.lang.syntax.ArchRuleDefinition.noClasses;

class DomainLayerArchitectureTests {

    private static final ArchRule DOMAIN_MUST_NOT_DEPEND_ON_WEB = noClasses()
            .that().resideInAPackage("com.acme.shop..domain..")
            .should().dependOnClassesThat()
            .resideInAPackage("com.acme.shop..web..")
            .as("domain code must not depend on web adapters");

    @Test
    void domainDoesNotDependOnWeb() {
        JavaClasses classes = new ClassFileImporter()
                .importPackages("com.acme.shop");

        DOMAIN_MUST_NOT_DEPEND_ON_WEB.check(classes);
    }
}
```

`ClassFileImporter` nạp các Java type trong package ứng dụng để ArchUnit phân tích. `ArchRule.check(classes)` thực thi duy nhất quy tắc đã khai báo. Khi vi phạm, thông báo của ArchUnit nêu tên rule và các quan hệ phụ thuộc không hợp lệ.

Với cách tổ chức này, có thể phân biệt kết quả:

| Test | Phạm vi |
|---|---|
| `ModuleStructureTests` | Ranh giới giữa application module theo Spring Modulith |
| `DomainLayerArchitectureTests` | Domain layer không phụ thuộc web layer |
| `ApplicationLayerArchitectureTests` | Application layer không phụ thuộc bootstrap hoặc adapter cụ thể |
| `AdapterArchitectureTests` | Quy tắc riêng giữa các adapter |

Nếu một quy tắc layering thất bại, test của nó cho biết chính xác invariant nào bị phá vỡ mà không cần đọc toàn bộ báo cáo module verification.

## 4. Đặt tên rule và phạm vi package để lỗi dễ hiểu

Tên biến hoặc tên rule nên mô tả điều kiện kiến trúc bằng ngôn ngữ của nhóm. ArchUnit hỗ trợ `.as(...)` để đặt mô tả cho rule:

```java
private static final ArchRule APPLICATION_MUST_NOT_DEPEND_ON_BOOTSTRAP = noClasses()
        .that().resideInAPackage("com.acme.shop..application..")
        .should().dependOnClassesThat()
        .resideInAPackage("com.acme.shop..bootstrap..")
        .as("application code must not depend on bootstrap configuration");
```

Tên `APPLICATION_MUST_NOT_DEPEND_ON_BOOTSTRAP` cho biết invariant trong code; mô tả `.as(...)` xuất hiện trong báo cáo lỗi để người đọc biết rule đang bảo vệ điều gì.

Phạm vi package cũng cần chính xác. Pattern `..domain..` có thể khớp mọi package có segment `domain` trong namespace được import. Nếu dự án chứa nhiều ứng dụng hoặc thư viện trong cùng classpath, hãy giới hạn root, ví dụ `com.acme.shop..domain..`.

Không nên tạo một rule như:

```java
noClasses().should().dependOnClassesThat().resideInAnyPackage("..internal..", "..impl..");
```

cho toàn bộ codebase nếu có những package `internal` hợp lệ trong cùng module hoặc thư viện ngoài. Rule quá rộng dễ tạo nhiều false positive và khiến nhóm mất niềm tin vào architecture test. Hãy xác định rõ lớp nguồn, lớp đích và ranh giới mà nhóm muốn bảo vệ.

## 5. Một test cho một quy tắc độc lập

Nếu có nhiều quy tắc layering, hãy đặt mỗi quy tắc trong một test riêng hoặc một test class theo nhóm layer. Ví dụ:

```java
import com.tngtech.archunit.core.domain.JavaClasses;
import com.tngtech.archunit.core.importer.ClassFileImporter;
import com.tngtech.archunit.lang.ArchRule;
import org.junit.jupiter.api.Test;

import static com.tngtech.archunit.lang.syntax.ArchRuleDefinition.noClasses;

class ApplicationLayerArchitectureTests {

    private static final ArchRule APPLICATION_MUST_NOT_DEPEND_ON_WEB = noClasses()
            .that().resideInAPackage("com.acme.shop..application..")
            .should().dependOnClassesThat()
            .resideInAPackage("com.acme.shop..web..");

    private static final ArchRule APPLICATION_MUST_NOT_DEPEND_ON_BOOTSTRAP = noClasses()
            .that().resideInAPackage("com.acme.shop..application..")
            .should().dependOnClassesThat()
            .resideInAPackage("com.acme.shop..bootstrap..");

    @Test
    void applicationDoesNotDependOnWeb() {
        APPLICATION_MUST_NOT_DEPEND_ON_WEB.check(importedClasses());
    }

    @Test
    void applicationDoesNotDependOnBootstrap() {
        APPLICATION_MUST_NOT_DEPEND_ON_BOOTSTRAP.check(importedClasses());
    }

    private JavaClasses importedClasses() {
        return new ClassFileImporter().importPackages("com.acme.shop");
    }
}
```

Mỗi test có tên riêng và chỉ thực thi một rule. Khi một test thất bại, tên test và tên rule giúp xác định invariant bị vi phạm. Có thể tách mỗi nhóm rule thành class riêng nếu muốn kết quả báo cáo CI ngắn và dễ điều hướng hơn.

## 6. Khi nào nên tích hợp rule với `VerificationOptions`?

Nếu muốn custom ArchUnit rule chạy trong cùng lần xác minh module model của Spring Modulith, hãy đăng ký bằng `VerificationOptions`:

```java
import com.acme.shop.ShopApplication;
import com.tngtech.archunit.lang.ArchRule;
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;
import org.springframework.modulith.core.VerificationOptions;

import static com.tngtech.archunit.lang.syntax.ArchRuleDefinition.noClasses;

class ModuleAndLayerVerificationTests {

    @Test
    void verifiesModuleBoundariesAndDomainLayer() {
        ArchRule domainMustNotDependOnWeb = noClasses()
                .that().resideInAPackage("com.acme.shop..domain..")
                .should().dependOnClassesThat()
                .resideInAPackage("com.acme.shop..web..")
                .as("domain code must not depend on web adapters");

        VerificationOptions options = VerificationOptions.defaults()
                .andAdditionalVerifications(domainMustNotDependOnWeb);

        ApplicationModules.of(ShopApplication.class).verify(options);
    }
}
```

`andAdditionalVerifications()` giữ các additional verification mặc định và bổ sung rule riêng. Cách này phù hợp khi muốn một architecture gate duy nhất xác minh cả module boundary lẫn layering.

Tuy nhiên, khi nhiều custom rule được truyền trong cùng một lần verify, báo cáo có thể chứa nhiều nhóm vi phạm cùng lúc. Nếu mục tiêu là chẩn đoán từng invariant độc lập, có thể kiểm tra từng `ArchRule` bằng `check()` như phần trước. Nếu mục tiêu là một cổng kiến trúc tổng hợp, `VerificationOptions` giúp quản lý rule ở cùng nơi với module model.

`withAdditionalVerifications()` thay thế nhóm additional verification mặc định; chỉ dùng khi chủ đích là thay tập rule bổ sung. Các kiểm tra cốt lõi của Spring Modulith vẫn được thực hiện.

## 7. Tránh phụ thuộc vào thứ tự và trạng thái giữa các test

Mỗi test nên tự tạo đối tượng cần thiết và có thể chạy riêng. Không chia sẻ một instance `ApplicationModules` đã được xác minh giữa các test cần chạy những tập options khác nhau.

Ví dụ, test sau có thể gây nhầm lẫn khi tái sử dụng cùng instance:

```java
class SharedModuleModelTests {

    private static final ApplicationModules MODULES =
            ApplicationModules.of(ShopApplication.class);

    @Test
    void verifiesDefaultRules() {
        MODULES.verify();
    }

    @Test
    void verifiesCustomRules() {
        MODULES.verify(customOptions());
    }
}
```

`verify()` có thể không thực hiện lại việc xác minh nếu instance đó đã được xác minh. Vì vậy, test thứ hai có nguy cơ không chạy tập options mà nó muốn kiểm tra. Thứ tự chạy test cũng có thể ảnh hưởng kết quả.

Hãy tạo module model mới trong mỗi test:

```java
@Test
void verifiesDefaultRules() {
    ApplicationModules.of(ShopApplication.class).verify();
}

@Test
void verifiesCustomRules() {
    ApplicationModules.of(ShopApplication.class).verify(customOptions());
}
```

Hoặc dùng `detectViolations(options)` khi cần thực thi verification với options cụ thể và nhận đối tượng `Violations` để xử lý. API này thực hiện kiểm tra mỗi lần gọi. Đừng dùng static mutable state để lưu kết quả của một lần kiểm tra cho test khác.

## 8. Làm cho báo cáo lỗi có ích

Một architecture test dễ chẩn đoán nên giúp người đọc trả lời nhanh ba câu hỏi:

1. Quy tắc nào bị vi phạm?
2. Lớp hoặc package nào tạo ra vi phạm?
3. Vì sao quy tắc đó tồn tại?

Có thể cải thiện báo cáo bằng các cách:

- Dùng tên test mô tả invariant, ví dụ `domainDoesNotDependOnWeb`.
- Dùng `.as("...")` để đặt mô tả rõ cho `ArchRule`.
- Giới hạn package pattern theo namespace ứng dụng.
- Một test chỉ thực thi một rule khi cần chẩn đoán chi tiết.
- Giữ nguyên thông báo vi phạm của ArchUnit hoặc Spring Modulith; tránh bắt exception rồi chỉ trả về một assertion boolean chung chung.
- Không bỏ qua toàn bộ vi phạm bằng filter rộng chỉ để CI xanh.

Ví dụ không nên làm:

```java
@Test
void architectureIsFine() {
    try {
        ApplicationModules.of(ShopApplication.class).verify();
    } catch (Exception ignored) {
        assertTrue(true);
    }
}
```

Test này nuốt lỗi kiến trúc và luôn thành công, nên không còn bảo vệ invariant nào. Hãy để exception truyền ra để JUnit đánh dấu test thất bại với thông báo gốc.

## 9. Đặt architecture test ở đâu trong dự án?

Một cấu trúc test source set dễ tìm có thể như sau:

```text
src/test/java
└── com/acme/shop
    ├── architecture
    │   ├── ModuleStructureTests.java
    │   ├── DomainLayerArchitectureTests.java
    │   └── ApplicationLayerArchitectureTests.java
    ├── order
    │   └── OrderServiceTests.java
    └── inventory
        └── InventoryModuleTests.java
```

Nhóm `architecture` chứa các test tĩnh áp dụng cho toàn ứng dụng. Test nghiệp vụ hoặc module integration đặt gần module tương ứng để người phát triển dễ tìm. Đây là quy ước tổ chức, không phải cấu trúc bắt buộc của Spring Modulith.

Một pipeline CI có thể chạy các nhóm test theo thứ tự:

1. Architecture tests để phát hiện vi phạm package và dependency sớm.
2. Unit tests cho logic nghiệp vụ.
3. `@ApplicationModuleTest` cho hành vi và tương tác bên trong module.
4. Integration tests cho database, broker và hệ thống ngoài.

Có thể chạy song song nếu cấu hình build cho phép và các test không chia sẻ tài nguyên mutable. Architecture test tĩnh thường không cần chờ database hoặc broker sẵn sàng.

## 10. Checklist cho architecture test dễ bảo trì

- [ ] Mỗi test có tên diễn đạt một invariant kiến trúc.
- [ ] Module boundary test dùng `ApplicationModules.of(...).verify()`.
- [ ] Layering rule độc lập khi cần được kiểm tra bằng `ArchRule.check()`.
- [ ] Custom rule có mô tả `.as(...)` rõ ràng.
- [ ] Package pattern giới hạn đúng namespace của ứng dụng.
- [ ] Test tĩnh không khởi tạo Spring context hoặc phụ thuộc hạ tầng ngoài.
- [ ] Không tái sử dụng `ApplicationModules` instance đã verify với options khác nhau.
- [ ] Không nuốt exception hoặc bỏ qua toàn bộ vi phạm.
- [ ] Architecture tests chạy tự động trong CI.

## 11. Ghi nhớ

Giữ architecture test độc lập bằng cách tách kiểm tra module boundary khỏi các quy tắc layering riêng, không khởi tạo Spring context khi chỉ cần phân tích code và để mỗi test bảo vệ một invariant rõ ràng. Dùng `ApplicationModules.verify()` cho ranh giới module; dùng `ArchRule.check()` cho rule độc lập; dùng `VerificationOptions` khi muốn tích hợp custom rule vào cùng lần xác minh Modulith. Đặt tên rule bằng `.as(...)`, giới hạn package pattern, tạo module model mới cho mỗi lần kiểm tra với options khác nhau và giữ thông báo lỗi gốc. Các test nhỏ, xác định và dễ đọc giúp CI chỉ ra chính xác quy tắc kiến trúc cần được sửa.

## Tài liệu tham khảo

- [Spring Modulith – Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html)
- [Spring Modulith API – `ApplicationModules`](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModules.html)
- [Spring Modulith API – `VerificationOptions`](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/VerificationOptions.html)
- [ArchUnit User Guide – Writing Architecture Rules](https://www.archunit.org/userguide/html/000_Index.html)
- [JUnit 5 User Guide](https://junit.org/junit5/docs/current/user-guide/)
