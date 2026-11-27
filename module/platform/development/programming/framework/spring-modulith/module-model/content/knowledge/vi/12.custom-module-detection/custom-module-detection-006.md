# Đồng bộ strategy giữa verification và documentation

Khi dùng custom `ApplicationModuleDetectionStrategy`, Spring Modulith phải nhận diện cùng một tập module ở mọi nơi sử dụng mô hình kiến trúc. Nếu verification dùng một strategy nhưng tài liệu được sinh từ một cấu hình khác, kết quả kiểm tra có thể không khớp với sơ đồ C4/UML hoặc Module Canvas mà nhóm công bố. Cách an toàn là đăng ký strategy thống nhất cho môi trường kiểm thử và tài liệu, tạo một `ApplicationModules` làm nguồn mô hình duy nhất, rồi dùng chính instance đó cho cả `verify()` và `Documenter`.

Trong phạm vi **SPRING_MODULITH_MODULE_MODEL**, `ApplicationModules` là mô hình biểu diễn các ranh giới nghiệp vụ, API công khai và dependency giữa package trong ứng dụng Spring Boot. `ApplicationModules.verify()` kiểm tra các quy tắc kiến trúc trên mô hình; `Documenter` tạo sơ đồ và tài liệu từ mô hình đó. Vì vậy, chất lượng của cả hai kết quả phụ thuộc vào việc chúng được xây dựng từ cùng package gốc, cùng detection strategy và cùng các tùy chỉnh liên quan.

## 1. Vì sao verification và documentation phải đồng bộ?

Giả sử ứng dụng có các package:

```text
com.acme.shop
├── ShopApplication.java
├── orders
├── inventory
├── customers
├── config
└── shared
```

Nhóm định nghĩa custom strategy để chỉ xem `orders`, `inventory`, `customers` và `shared` là application module; package `config` là hạ tầng chung và không phải module độc lập.

Nếu verification dùng custom strategy nhưng documentation lại tạo mô hình bằng default detection, hai kết quả có thể khác nhau:

| Verification | Documentation | Hệ quả |
|---|---|---|
| Dùng custom strategy | Dùng default strategy | Test có thể bỏ qua `config`, nhưng sơ đồ lại hiển thị `config` như một module |
| Dùng default strategy | Dùng custom strategy | Test có thể báo dependency tới `config`, trong khi tài liệu không có module này |
| Dùng hai phiên bản strategy khác nhau | Mỗi bên tạo một module list | Ranh giới và dependency trong tài liệu không còn là mô hình đã được kiểm chứng |
| Dùng cùng strategy và cùng tùy chỉnh | Dùng cùng `ApplicationModules` | Verification và documentation phản ánh cùng một cấu trúc |

Sự lệch nhau không chỉ ảnh hưởng số lượng module. Nó có thể làm thay đổi module ownership của package, named interfaces, dependency graph và kết quả phát hiện chu trình. Một sơ đồ đẹp nhưng được sinh từ mô hình khác không phải bằng chứng rằng cấu trúc trong sơ đồ đã vượt qua verification.

## 2. Custom strategy là nguồn quy tắc phát hiện module

`ApplicationModuleDetectionStrategy` cho phép chọn package nào trở thành module base package. Strategy nhận package gốc của ứng dụng và trả về stream các package mô-đun:

```java
package com.acme.shop.architecture;

import java.util.Set;
import java.util.stream.Stream;

import com.tngtech.archunit.core.domain.JavaPackage;
import org.springframework.modulith.core.ApplicationModuleDetectionStrategy;

public final class BusinessModuleDetectionStrategy
        implements ApplicationModuleDetectionStrategy {

    private static final Set<String> TECHNICAL_PACKAGES =
        Set.of("config", "mapper", "persistence");

    @Override
    public Stream<JavaPackage> getModuleBasePackages(JavaPackage basePackage) {
        return ApplicationModuleDetectionStrategy.directSubPackage()
            .getModuleBasePackages(basePackage)
            .filter(candidate -> !TECHNICAL_PACKAGES.contains(
                candidate.getRelativeName()
            ));
    }
}
```

Ví dụ này bắt đầu từ chiến lược mặc định, sau đó loại các package kỹ thuật có tên nằm trong tập `TECHNICAL_PACKAGES`. Với dự án thực tế, có thể dùng allowlist các năng lực nghiệp vụ, quy ước package hoặc metadata. Hãy chọn quy tắc có thể giải thích và kiểm thử; blacklist cần được cập nhật khi xuất hiện package kỹ thuật mới.

Nếu strategy còn tùy chỉnh named interface, hãy thực hiện việc đó trong cùng implementation. Ví dụ, mọi package con tên `api` được công khai như named interface:

```java
import org.springframework.modulith.core.ApplicationModuleInformation;
import org.springframework.modulith.core.NamedInterfaces;

@Override
public NamedInterfaces detectNamedInterfaces(
        JavaPackage basePackage,
        ApplicationModuleInformation information) {

    return NamedInterfaces.builder()
        .recursive()
        .matching("api")
        .build();
}
```

Như vậy, cả việc chọn module base package lẫn việc phát hiện named interface đều nằm trong cùng strategy. Verification và documentation sẽ dùng cùng kết quả khám phá khi chúng dùng cùng mô hình `ApplicationModules`.

## 3. Đăng ký strategy cho môi trường kiểm thử và tài liệu

Spring Modulith nhận strategy qua thuộc tính `spring.modulith.detection-strategy`. Giá trị có thể là một trong các strategy dựng sẵn như `direct-sub-packages`, `explicitly-annotated`, hoặc tên đầy đủ của custom strategy.

Ví dụ khi custom strategy chỉ phục vụ verification và documentation trong test, đặt class và cấu hình trong test sources:

```text
src
├── main
│   └── java
│       └── com/acme/shop/ShopApplication.java
└── test
    ├── java
    │   └── com/acme/shop/architecture/
    │       └── BusinessModuleDetectionStrategy.java
    └── resources
        └── application.properties
```

Trong `src/test/resources/application.properties`:

```properties
spring.modulith.detection-strategy=com.acme.shop.architecture.BusinessModuleDetectionStrategy
```

Spring Modulith yêu cầu custom strategy và phần đăng ký của nó có mặt trong test sources nếu strategy được dùng để kiểm chứng và tạo tài liệu. Nhờ đó, test tạo mô hình có thể nạp đúng implementation thay vì âm thầm quay về default detection.

Nếu custom strategy cũng được dùng bởi runtime components như `ApplicationModuleInitializer`, actuator hoặc observability, strategy cần có mặt ở runtime classpath. Trong trường hợp đó, đặt implementation và cấu hình ở main sources, đồng thời khai báo `spring-modulith-core` như compile-time dependency theo yêu cầu của tài liệu Spring Modulith. Đừng chỉ đặt strategy trong test sources nếu runtime cũng cần dùng nó.

Với các dự án đang dùng cơ chế đăng ký cũ qua `META-INF/spring.properties`, cần kiểm tra hướng dẫn của phiên bản Spring Modulith đang sử dụng; cơ chế này đã được đánh dấu deprecated trong API hiện hành. Ưu tiên thuộc tính `spring.modulith.detection-strategy` được tài liệu phiên bản dự án hỗ trợ.

## 4. Tạo một ApplicationModules dùng chung

Sau khi strategy đã được đăng ký, tạo mô hình một lần từ lớp ứng dụng:

```java
import org.springframework.modulith.core.ApplicationModules;

ApplicationModules modules = ApplicationModules.of(ShopApplication.class);
```

`ApplicationModules.of(ShopApplication.class)` đọc package gốc và các tùy chỉnh Modulith liên quan để xây dựng mô hình trong bộ nhớ. Tập module được nhận diện phụ thuộc vào package arrangement và detection strategy đang có hiệu lực.

Hãy dùng chính instance `modules` đó cho verification và documentation. Tránh tạo hai instance ở hai test class riêng với cấu hình hoặc classpath khác nhau rồi giả định chúng giống nhau.

## 5. Verification và Documenter dùng cùng mô hình

Một test có thể kiểm chứng cấu trúc và sinh tài liệu từ cùng instance:

```java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;
import org.springframework.modulith.docs.Documenter;

class ModuleArchitectureDocumentationTests {

    private final ApplicationModules modules =
        ApplicationModules.of(ShopApplication.class);

    @Test
    void verifiesApplicationModuleStructure() {
        modules.verify();
    }

    @Test
    void writesModuleDocumentation() {
        new Documenter(modules)
            .writeDocumentation();
    }
}
```

`modules.verify()` kiểm tra các ràng buộc kiến trúc như chu trình dependency, truy cập vào package nội bộ và các dependency bị giới hạn bởi `allowedDependencies`. `new Documenter(modules)` nhận đúng mô hình đã tạo, rồi `writeDocumentation()` sinh tài liệu cho toàn bộ module arrangement.

Tài liệu được sinh gồm:

- Sơ đồ component tổng quan của tất cả module.
- Sơ đồ component riêng cho từng module cùng các module liên quan theo dependency.
- Application Module Canvas cho từng module, mô tả package nền, Spring beans được expose, aggregate roots, event được publish/listen và configuration properties có metadata phù hợp.
- Tài liệu Asciidoc tổng hợp khi gọi phương thức tạo aggregating document.

Theo cấu hình mặc định, đầu ra nằm trong thư mục `spring-modulith-docs` bên dưới build directory. Hãy xem tài liệu được sinh là một artifact của chính mô hình `ApplicationModules`, không phải một phép quét package độc lập khác.

## 6. Vì sao nên truyền ApplicationModules vào Documenter?

Spring Modulith cung cấp các cách khởi tạo `Documenter`:

```java
new Documenter(ShopApplication.class);
```

hoặc:

```java
new Documenter(modules);
```

Constructor nhận class ứng dụng là cách tiện lợi vì `Documenter` tự tạo `ApplicationModules` cho class đó. Tuy nhiên, khi cần bảo đảm documentation dùng đúng mô hình vừa được verify, truyền trực tiếp instance `modules` là lựa chọn rõ ràng hơn.

Điều này đặc biệt quan trọng khi verification có thêm tùy chỉnh như:

- Custom `ApplicationModuleDetectionStrategy`.
- Predicate loại trừ một số class hoặc package.
- Cấu hình root package hoặc additional packages.
- Các metadata và quy tắc mô-đun được áp dụng trong một context kiểm thử cụ thể.

Nếu tạo `Documenter` từ class ứng dụng ở một nơi khác, cần bảo đảm nó được khởi tạo với cùng cấu hình, strategy, classpath và các tùy chỉnh. Dùng chung một instance tránh phải dựa vào giả định đó.

## 7. Kiểm tra model trước khi sinh tài liệu

Ngoài `verify()`, nên kiểm tra danh sách module và package nền mà strategy thực sự trả về. Ví dụ:

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.Set;
import java.util.stream.Collectors;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleDetectionConsistencyTests {

    private final ApplicationModules modules =
        ApplicationModules.of(ShopApplication.class);

    @Test
    void detectsExpectedBusinessModules() {
        Set<String> identifiers = modules.stream()
            .map(module -> module.getIdentifier().toString())
            .collect(Collectors.toSet());

        assertThat(identifiers)
            .containsExactlyInAnyOrder("orders", "inventory", "customers", "shared");
    }

    @Test
    void verifiesTheSameModelUsedForDocumentation() {
        modules.verify();
    }
}
```

Test đầu bảo vệ danh sách module mà custom strategy dự kiến tạo ra. Test thứ hai xác minh chính mô hình đó. Test sinh tài liệu cũng phải dùng field `modules` trong cùng fixture hoặc cùng cách khởi tạo để giữ nguồn dữ liệu thống nhất.

Nếu strategy có quy tắc named interface riêng, hãy kiểm tra cả named interface của các module quan trọng. Một module xuất hiện đúng tên nhưng expose sai package vẫn có thể tạo ra tài liệu không phản ánh hợp đồng mà consumer được phép dùng.

## 8. Đồng bộ khi documentation được sinh ở một task riêng

Không phải dự án nào cũng sinh tài liệu trong cùng test class với verification. Có thể có một test task riêng, một build task hoặc pipeline CI chuyên tạo sơ đồ. Trong trường hợp đó, cần giữ các điều kiện sau giống nhau:

| Thành phần | Verification | Documentation |
|---|---|---|
| Root application class/package | Cùng lớp hoặc package gốc | Cùng lớp hoặc package gốc |
| Detection strategy | Cùng class và cùng phiên bản | Cùng class và cùng phiên bản |
| Strategy registration | Có trên test/runtime classpath tương ứng | Có trên classpath sinh tài liệu |
| Ignore predicate | Cùng phạm vi class/package bị loại | Cùng phạm vi class/package bị loại |
| Modulith metadata | Cùng `@Modulithic`, additional packages và module metadata | Cùng `@Modulithic`, additional packages và module metadata |
| Dependency configuration | Cùng `allowedDependencies` và named interfaces | Cùng `allowedDependencies` và named interfaces |

Nếu documentation task chạy trong một JVM khác, hãy cấu hình cùng property và bảo đảm custom strategy có mặt trong classpath của task đó. Không nên chỉ truyền tên class trong property nhưng quên thêm artifact chứa class strategy vào task runtime.

Nếu có thể, hãy gom việc tạo mô hình vào một helper hoặc fixture dùng chung trong test sources. Các test verification và documentation gọi helper đó để tránh hai nơi tự khai báo strategy hoặc package root theo cách khác nhau.

## 9. Đồng bộ tài liệu viết tay với mô hình được kiểm chứng

`Documenter` sinh sơ đồ và Module Canvas từ `ApplicationModules`, nhưng nhóm vẫn có thể viết tài liệu kiến trúc bằng Markdown hoặc Asciidoc. Tài liệu viết tay nên lấy danh sách module, identifier, base package, API và dependency từ cùng mô hình đã verify.

Có thể in thông tin mô hình để đối chiếu với tài liệu:

```java
modules.forEach(System.out::println);
```

Khi cập nhật tài liệu viết tay, hãy đối chiếu các tên module, package và mũi tên dependency với output hiện tại. Nếu nhóm quyết định tài liệu có thêm góc nhìn nghiệp vụ không được thể hiện trong model, hãy ghi rõ đó là mô tả nghiệp vụ bổ sung, tránh trình bày nó như dependency đã được Spring Modulith xác minh.

Không nên duy trì một danh sách module thủ công ở nhiều nơi mà không có kiểm tra đối chiếu. Danh sách cũ dễ tồn tại sau khi module được đổi tên, gộp, tách hoặc chuyển sang named interface khác.

## 10. Những lỗi đồng bộ thường gặp

### Strategy chỉ có trong main sources

Ứng dụng runtime biết custom strategy, nhưng test không có class hoặc registration tương ứng. Verification có thể dùng default strategy và báo kết quả khác với runtime.

### Strategy chỉ có trong test sources dù runtime cũng cần dùng

Verification và documentation chạy đúng, nhưng các runtime components như actuator hoặc observability không thể sử dụng strategy vì class không có trên runtime classpath. Đưa implementation vào main sources và khai báo dependency cần thiết nếu runtime thực sự dùng nó.

### Documenter tạo mô hình riêng với cấu hình khác

Verification dùng `ApplicationModules` đã tùy chỉnh, còn `Documenter(ShopApplication.class)` tạo mô hình từ một cấu hình khác. Truyền instance `ApplicationModules` đã verify vào `Documenter` để loại bỏ nguồn lệch này.

### Hai strategy có cùng tên nhưng logic khác nhau

Nếu strategy được copy giữa main và test sources, hai bản có thể dần khác logic. Hãy dùng chung một implementation hoặc đảm bảo cùng artifact/version được dùng ở cả hai classpath.

### Documentation không được sinh lại sau khi đổi ranh giới

Test verification có thể đã pass sau khi module được thêm, đổi tên hoặc thay dependency, nhưng sơ đồ trong tài liệu vẫn là artifact cũ. Gắn bước sinh tài liệu vào pipeline kiểm tra phù hợp và cập nhật artifact được công bố khi mô hình thay đổi.

### Nhầm verification với chất lượng tài liệu

`verify()` kiểm tra các quy tắc cấu trúc và dependency mà Spring Modulith hỗ trợ. Nó không xác nhận mô tả nghiệp vụ, tên hiển thị, nội dung giải thích hoặc sơ đồ viết tay đã đầy đủ và dễ hiểu. Tài liệu cần được rà soát nội dung riêng sau khi sinh từ mô hình đúng.

## 11. Quy trình triển khai đồng bộ

Khi đưa custom detection vào dự án, có thể làm theo thứ tự:

1. **Chốt quy tắc phát hiện.** Xác định rõ package nào là module base package, package nào là phần nội bộ và named interface nào được expose.
2. **Viết một custom strategy.** Đặt logic phát hiện và named interface (nếu tùy chỉnh) trong một implementation có thể tái sử dụng.
3. **Đăng ký strategy.** Cấu hình `spring.modulith.detection-strategy` và bảo đảm implementation cùng registration có mặt trong test sources; thêm vào runtime sources nếu runtime components cần sử dụng.
4. **Tạo model dùng chung.** Khởi tạo `ApplicationModules.of(ShopApplication.class)` trong fixture hoặc helper chung.
5. **Kiểm tra module list.** Assertion các module identifier, base package và named interface quan trọng.
6. **Verify model.** Gọi `modules.verify()` trên chính instance đó.
7. **Sinh documentation.** Truyền cùng `modules` vào `new Documenter(modules)` và gọi `writeDocumentation()` hoặc các phương thức sinh sơ đồ/canvas cần thiết.
8. **Đối chiếu tài liệu viết tay.** Cập nhật danh sách module và dependency theo model đã kiểm chứng.
9. **Tích hợp CI.** Chạy verification và documentation generation với cùng classpath, property và version strategy; kiểm tra artifact sinh ra khi cấu trúc thay đổi.

## 12. Checklist trước khi phát hành sơ đồ kiến trúc

- [ ] Verification và documentation dùng cùng root application class/package.
- [ ] Custom `ApplicationModuleDetectionStrategy` có cùng implementation và phiên bản.
- [ ] Strategy registration có mặt trong test sources và classpath sinh tài liệu.
- [ ] Runtime components có strategy trên runtime classpath nếu chúng cần dùng.
- [ ] Cùng ignore predicate, additional packages và Modulith metadata được áp dụng.
- [ ] Danh sách module và named interface được assertion trong test.
- [ ] `ApplicationModules.verify()` chạy trên model được dùng để sinh tài liệu.
- [ ] `Documenter` nhận trực tiếp instance `ApplicationModules` đó.
- [ ] Sơ đồ và Module Canvas được sinh lại sau thay đổi package hoặc dependency.
- [ ] Tài liệu viết tay được đối chiếu với module list và dependency hiện tại.

## Kết luận

Verification và documentation cần phản ánh cùng một module arrangement. Với custom detection, hãy đăng ký strategy trong môi trường test dùng để kiểm chứng và sinh tài liệu, tạo một `ApplicationModules` làm nguồn mô hình duy nhất, gọi `verify()` trên instance đó và truyền chính instance đó vào `Documenter`. Khi documentation được sinh ở task riêng, giữ đồng nhất root package, strategy, classpath, ignore rules và metadata. Cách làm này giúp sơ đồ C4/UML, Module Canvas và tài liệu kiến trúc mô tả đúng cấu trúc mà Spring Modulith đã kiểm tra.

## Tài liệu tham khảo

- [Spring Modulith — Fundamentals: Customizing Module Detection](https://docs.spring.io/spring-modulith/reference/fundamentals.html#modules.customizing-detection)
- [Spring Modulith — Documenting Application Modules](https://docs.spring.io/spring-modulith/reference/documentation.html)
- [Javadoc: ApplicationModuleDetectionStrategy](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModuleDetectionStrategy.html)
- [Javadoc: ApplicationModules](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModules.html)
- [Javadoc: Documenter](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/docs/Documenter.html)
