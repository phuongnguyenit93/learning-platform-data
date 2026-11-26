# Ranh giới và quy tắc phân tầng

## Thiết lập quy tắc phụ thuộc giữa các module và tự động phát hiện vi phạm

Trong module `SOFTWARE_DESIGN_ARCHITECTURE_ARCHITECTURAL_PATTERN_LAYERED` — **Học tổ chức phần mềm theo kiến trúc phân tầng** — việc chia mã nguồn thành các tầng hoặc module chỉ có giá trị khi những ranh giới đó được duy trì. Nếu mọi module đều có thể import lẫn nhau, cấu trúc ban đầu sẽ dần mất ý nghĩa: tầng miền biết chi tiết cơ sở dữ liệu, giao diện gọi thẳng adapter, hoặc hai module tạo thành vòng phụ thuộc.

Bài học này trình bày cách xác định hướng phụ thuộc được phép giữa các module và cách biến quy tắc đó thành kiểm tra tự động. Ví dụ sử dụng một ứng dụng bán hàng Java với các phần trình bày, ứng dụng, miền nghiệp vụ, hạ tầng và khởi tạo hệ thống. Tên và số module có thể thay đổi theo dự án; ma trận phụ thuộc phải phản ánh ranh giới thực tế của hệ thống.

## 1. Vì sao phải quy định hướng phụ thuộc?

Một module có thể sử dụng module khác thông qua kiểu dữ liệu, interface, lời gọi phương thức, annotation hoặc cấu hình. Mỗi quan hệ như vậy tạo ra một **phụ thuộc**. Ta biểu diễn `A -> B` khi mã nguồn của A cần biết một kiểu hoặc hợp đồng thuộc B để biên dịch hay hoạt động theo cách đã thiết kế.

Khi số module tăng, các phụ thuộc tạo thành một đồ thị có hướng. Đồ thị này cần có cấu trúc có chủ đích:

- Module nghiệp vụ cốt lõi không nên phụ thuộc vào giao diện HTTP hoặc thư viện lưu trữ cụ thể.
- Module trình bày nên gửi yêu cầu qua hợp đồng ứng dụng thay vì tự truy cập cơ sở dữ liệu.
- Adapter hạ tầng nên triển khai hợp đồng mà phần bên trong định nghĩa, thay vì buộc phần nghiệp vụ biết adapter cụ thể.
- Các module không nên tạo thành chu trình phụ thuộc khiến việc thay đổi hoặc biên dịch một phần trở nên khó kiểm soát.

Một chương trình vẫn có thể biên dịch và chạy dù kiến trúc đã bị vi phạm. Ví dụ, `OrderController` có thể gọi trực tiếp `JpaOrderRepository`, nhưng cách làm đó khiến luồng HTTP biết chi tiết lưu trữ và bỏ qua ca sử dụng ứng dụng. Vì vậy, kiểm tra biên dịch thông thường chưa đủ để bảo vệ mọi quy tắc kiến trúc.

### Phân biệt các nghĩa của từ module

Trong dự án Java, “module” có thể chỉ những ranh giới khác nhau:

| Loại ranh giới | Ý nghĩa | Cách thường dùng để kiểm soát |
| --- | --- | --- |
| Module logic | Nhóm mã có trách nhiệm và API nội bộ rõ ràng; có thể được thể hiện bằng package | Quy ước package, ArchUnit |
| Module build | Project con trong Maven hoặc Gradle, có dependency được khai báo trong build | Maven POM, Gradle project dependencies |
| Module Java (JPMS) | Đơn vị module của Java Platform Module System, khai báo trong `module-info.java` | `requires`, `exports`, `opens` |

Ba loại ranh giới có thể trùng nhau nhưng không mặc nhiên đồng nhất. Một dự án có thể chỉ có một Gradle project nhưng vẫn chia thành nhiều module logic bằng package. Một dự án khác có thể tách từng module logic thành Gradle subproject và JPMS module riêng. Cần xác định ranh giới nào đang được bảo vệ trước khi viết quy tắc.

## 2. Xác định module và hợp đồng công khai

Trước khi viết kiểm tra, hãy liệt kê các module, trách nhiệm và hợp đồng mà module khác được phép sử dụng. Ví dụ, mã nguồn có thể được tổ chức như sau:

```text
com.acme.shop
├── bootstrap       # Khởi tạo ứng dụng và lắp ghép các adapter
├── presentation    # REST controller và chuyển đổi HTTP
├── application     # Điều phối ca sử dụng và định nghĩa port cần thiết
├── domain          # Mô hình và quy tắc nghiệp vụ
└── infrastructure  # Adapter JPA, messaging và tích hợp kỹ thuật
```

Package chỉ là cách biểu diễn ranh giới trong ví dụ. Nếu một module được tách thành project riêng, package có thể nằm trong project đó; nếu dùng JPMS, mỗi module còn có thể khai báo tập package được export.

Một module nên công khai đúng những gì bên sử dụng cần. Ví dụ, `application` có thể công khai `PlaceOrder` hoặc `OrderStore` như hợp đồng; lớp triển khai chi tiết và helper nội bộ không nên trở thành API mặc định. Việc giới hạn API giúp thay đổi bên trong ít ảnh hưởng đến module khác.

Khi xác định ranh giới, hãy trả lời ba câu hỏi:

1. Module chịu trách nhiệm về quyết định hoặc công việc nào?
2. Module khác cần dùng hợp đồng nào của nó?
3. Những package, class hoặc thư viện nào phải được giữ bên trong?

Không nên tạo module chỉ để tăng số lượng package. Ranh giới có ích khi nó tách trách nhiệm, kiểm soát thay đổi hoặc cho phép kiểm thử và triển khai độc lập.

## 3. Lập ma trận phụ thuộc được phép

Hãy thống nhất trước quy ước đọc mũi tên. Trong bài này, `A -> B` nghĩa là **A được phép phụ thuộc vào B**. Với một cách tổ chức dùng application port, ma trận ví dụ có thể là:

| Module sử dụng | Được phép phụ thuộc vào | Không được phụ thuộc trực tiếp vào |
| --- | --- | --- |
| `presentation` | `application` | `domain`, `infrastructure` |
| `application` | `domain` và các thư viện nền tảng cần thiết | `presentation`, `infrastructure` |
| `domain` | Thư viện Java hoặc thư viện miền được chấp nhận rõ ràng | `presentation`, `application`, `infrastructure` |
| `infrastructure` | Hợp đồng `application` và mô hình `domain` mà adapter cần | `presentation` |
| `bootstrap` | `presentation`, `application`, `infrastructure` để lắp ghép ứng dụng | Không nên chứa quy tắc nghiệp vụ thay cho `domain` hoặc `application` |

Một số quan hệ hợp lệ tương ứng:

```text
presentation    -> application
application     -> domain
infrastructure  -> application
infrastructure  -> domain
bootstrap       -> presentation, application, infrastructure
```

Trong ví dụ này, `application` định nghĩa port `OrderStore`; `infrastructure` cung cấp `JpaOrderStore implements OrderStore`. Vì thế mã nguồn của adapter phụ thuộc vào hợp đồng ứng dụng, còn dịch vụ ứng dụng chỉ biết interface. Lúc chạy, lời gọi qua interface được chuyển tới bean adapter do Spring cung cấp.

Ma trận là một chính sách thiết kế, không phải quy tắc phổ quát. Có kiến trúc đặt repository port trong `domain`, có kiến trúc dùng module `contracts` riêng, và có ứng dụng nhỏ gộp một số trách nhiệm. Nếu vị trí hợp đồng thay đổi, hãy cập nhật ma trận và kiểm tra tương ứng. Điều cần giữ là hướng phụ thuộc phải rõ ràng và không để phần cốt lõi bị khóa vào chi tiết bên ngoài.

### Tránh chu trình phụ thuộc

Giả sử `catalog -> pricing`, `pricing -> inventory` và `inventory -> catalog`. Đây là một chu trình. Khi đó, thay đổi API của `catalog` có thể buộc cả hai module còn lại thay đổi; việc kiểm thử hoặc tái sử dụng riêng một module cũng khó hơn.

Một đồ thị phụ thuộc không có chu trình (DAG) giúp ta sắp xếp thứ tự xây dựng và hiểu rõ module nào là nền tảng. Nếu hai module cần dùng dữ liệu của nhau, hãy xem xét một trong các cách sau:

- Đưa hợp đồng ổn định mà cả hai thực sự cần vào một module nhỏ hơn, có trách nhiệm rõ ràng.
- Đảo chiều phụ thuộc bằng interface/port do bên cần khả năng đó định nghĩa.
- Gộp hai phần nếu chúng luôn thay đổi cùng nhau và chưa có lý do thực tế để tách.
- Thay lời gọi trực tiếp bằng sự kiện hoặc thông điệp khi nghiệp vụ cho phép xử lý bất đồng bộ; cách này vẫn cần hợp đồng và quy tắc vận hành rõ ràng.

Không nên giải quyết chu trình bằng cách chuyển mọi class dùng chung vào một package `common` không có giới hạn. Module dùng chung quá rộng thường trở thành nơi chứa phụ thuộc của toàn hệ thống và làm mờ ranh giới ban đầu.

## 4. Kiểm soát ở mức module build và JPMS

Khi dự án dùng nhiều Maven/Gradle project, khai báo dependency giữa các project giúp quản lý đồ thị build và giới hạn classpath biên dịch. Nếu class của `infrastructure` không xuất hiện trên compile classpath của `application`, mã ứng dụng không thể import class đó. Tuy nhiên, dependency bắc cầu có thể làm một thư viện xuất hiện trên classpath dù project không khai báo trực tiếp; vì vậy cần kiểm tra cấu hình `api`/`implementation` hoặc phạm vi dependency cùng với quy tắc kiến trúc.

Với Java Platform Module System, `module-info.java` có thể giới hạn module nào đọc được module nào và package nào được công khai. Ví dụ rút gọn:

```java
// domain/src/main/java/module-info.java
module com.acme.shop.domain {
    exports com.acme.shop.domain.model;
}
```

```java
// application/src/main/java/module-info.java
module com.acme.shop.application {
    requires com.acme.shop.domain;
    exports com.acme.shop.application.api;
    exports com.acme.shop.application.port;
}
```

```java
// infrastructure/src/main/java/module-info.java
module com.acme.shop.infrastructure {
    requires com.acme.shop.application;
    requires com.acme.shop.domain;
}
```

Trong cấu trúc này, `domain` không khai báo `requires` tới `application` hoặc `infrastructure`; `application` cũng không đọc module hạ tầng. Module hạ tầng đọc các hợp đồng ứng dụng và mô hình miền để triển khai adapter. Module khởi tạo có thể `requires` các module cần lắp ghép. Các tên package trong `exports` phải khớp package thật của dự án.

`requires` xác định khả năng đọc giữa các JPMS module; `exports` xác định package công khai cho module khác. `opens` phục vụ truy cập phản chiếu sâu trong những tình huống cần thiết, chẳng hạn một số framework. Không nên dùng `opens` hoặc `exports` rộng hơn nhu cầu vì chúng làm tăng bề mặt truy cập.

Kiểm soát ở build và JPMS có ích, nhưng không thay thế hoàn toàn quy tắc kiến trúc ở mức class/package. Một project đơn có thể chứa nhiều module logic; một JPMS module cũng có thể chứa nhiều package với chính sách phụ thuộc khác nhau. Vì vậy, ta có thể bổ sung kiểm tra bằng ArchUnit.

## 5. Tự động kiểm tra bằng ArchUnit

**ArchUnit** là thư viện kiểm thử kiến trúc cho Java. Nó đọc bytecode đã biên dịch và cho phép diễn đạt quy tắc về package, class, annotation, phụ thuộc và các nhóm thành phần dưới dạng kiểm thử. Khi một quy tắc bị vi phạm, kiểm thử thất bại và báo những quan hệ phụ thuộc không phù hợp để nhóm phát hiện sớm trong quá trình build hoặc CI.

Thêm artifact `archunit-junit5` vào cấu hình test của Maven hoặc Gradle, chọn phiên bản tương thích với JUnit và quy trình build của dự án. Ví dụ Gradle Kotlin DSL:

```kotlin
dependencies {
    testImplementation("com.tngtech.archunit:archunit-junit5:<archunit-version>")
}
```

Ví dụ dưới đây mô tả chính sách ở phần ma trận bằng `layeredArchitecture`. Dù các nhóm được gọi là layer trong API, ta có thể dùng chúng để biểu diễn những module logic được tổ chức theo package:

```java
package com.acme.shop.archtests;

import com.tngtech.archunit.junit.AnalyzeClasses;
import com.tngtech.archunit.junit.ArchTest;
import com.tngtech.archunit.lang.ArchRule;

import static com.tngtech.archunit.library.Architectures.layeredArchitecture;
import static com.tngtech.archunit.library.dependencies.SlicesRuleDefinition.slices;

@AnalyzeClasses(packages = "com.acme.shop")
class ModuleArchitectureTest {

    @ArchTest
    static final ArchRule module_dependencies_follow_policy =
        layeredArchitecture()
            .consideringAllDependencies()
            .layer("Bootstrap").definedBy("com.acme.shop.bootstrap..")
            .layer("Presentation").definedBy("com.acme.shop.presentation..")
            .layer("Application").definedBy("com.acme.shop.application..")
            .layer("Domain").definedBy("com.acme.shop.domain..")
            .layer("Infrastructure").definedBy("com.acme.shop.infrastructure..")
            .whereLayer("Bootstrap").mayNotBeAccessedByAnyLayer()
            .whereLayer("Presentation").mayOnlyBeAccessedByLayers("Bootstrap")
            .whereLayer("Application").mayOnlyBeAccessedByLayers(
                "Presentation", "Infrastructure", "Bootstrap")
            .whereLayer("Domain").mayOnlyBeAccessedByLayers(
                "Application", "Infrastructure")
            .whereLayer("Infrastructure").mayOnlyBeAccessedByLayers("Bootstrap");

    @ArchTest
    static final ArchRule module_packages_must_be_acyclic =
        slices().matching("com.acme.shop.(*)..")
            .should().beFreeOfCycles();
}
```

Trong quy tắc `mayOnlyBeAccessedByLayers`, hãy đọc theo hướng **module nào được phép phụ thuộc vào layer đang xét**. Ví dụ, `Application` chỉ được `Presentation`, `Infrastructure` và `Bootstrap` sử dụng; `Domain` chỉ được `Application` và `Infrastructure` sử dụng. `Infrastructure` chỉ được `Bootstrap` truy cập để lắp ghép. Vì vậy, controller không thể gọi trực tiếp adapter JPA mà không làm kiểm thử thất bại.

Quy tắc `slices()` chia package thành các lát theo mẫu `com.acme.shop.(*)..` rồi yêu cầu các lát không tạo chu trình. Mẫu này giả định segment đầu tiên sau `com.acme.shop` là tên module logic. Nếu package của dự án có cấu trúc khác, cần sửa mẫu để mỗi lát tương ứng với ranh giới muốn kiểm tra.

Đoạn mã là khung minh họa cho cấu trúc package đã nêu. Khi áp dụng, hãy điều chỉnh tên package, các layer được phép truy cập và cách quét class cho đúng mã nguồn thực tế. Nếu dự án có package ngoài kiến trúc như mã sinh tự động, mã migration hoặc phần tích hợp đặc biệt, hãy quyết định rõ có đưa chúng vào phạm vi kiểm tra hay không. Tránh thêm ngoại lệ rộng chỉ để làm kiểm thử xanh.

### Chạy kiểm tra trong quy trình build

Đặt các quy tắc ArchUnit trong source set test và chạy cùng bộ kiểm thử thông thường, chẳng hạn `./gradlew test` hoặc `mvn test`. Đưa bước này vào CI để pull request có vi phạm phụ thuộc sẽ bị đánh dấu thất bại trước khi hợp nhất. Khi hệ thống có nhiều project, có thể đặt kiểm thử ở từng project hoặc tạo một project kiểm thử kiến trúc có thể đọc bytecode của các module cần kiểm tra.

ArchUnit kiểm tra những phụ thuộc mà nó nhận diện từ bytecode và cấu hình import. Nó không thể tự chứng minh mọi hành vi động, chẳng hạn một class được tìm bằng reflection, tên class được lấy từ file cấu hình hoặc giao tiếp diễn ra qua hệ thống bên ngoài. Với những ranh giới đó, cần kiểm tra cấu hình, hợp đồng tích hợp hoặc kiểm thử phù hợp khác. Build tool và JPMS cũng có vai trò riêng trong việc ngăn dependency ở cấp project/module.

## 6. Xử lý khi phát hiện vi phạm

Khi kiểm thử báo `presentation` phụ thuộc `infrastructure`, đừng chỉ xóa import để làm test qua. Hãy xác định lý do lời gọi xuất hiện và đưa trách nhiệm về đúng ranh giới. Chẳng hạn:

1. Nếu controller đang lưu đơn hàng trực tiếp, chuyển điều phối sang `PlaceOrder` ở application.
2. Nếu application cần khả năng lưu, định nghĩa port `OrderStore` trong module phù hợp.
3. Để `JpaOrderStore` trong infrastructure triển khai port đó.
4. Để bootstrap hoặc cấu hình Spring lắp ghép interface với adapter.
5. Chạy lại kiểm thử kiến trúc và kiểm thử chức năng liên quan.

Với một chu trình giữa hai module, hãy kiểm tra xem hợp đồng nào đang bị đặt sai chỗ hoặc hai phần nào thực tế thuộc cùng một trách nhiệm. Nếu cần ngoại lệ, ghi rõ lý do, phạm vi class/package và thời hạn xem xét; ngoại lệ nên càng hẹp càng tốt. Không nên bỏ qua toàn bộ module hoặc tắt quy tắc chung chỉ vì một trường hợp đặc biệt.

## 7. Duy trì chính sách kiến trúc

Quy tắc tự động chỉ hữu ích nếu chúng phản ánh thiết kế mà nhóm thực sự muốn giữ. Khi thêm module hoặc đổi package, cập nhật ma trận phụ thuộc, module descriptor và ArchUnit cùng lúc. Trong review, hãy xem một dependency mới như một quyết định kiến trúc: module sử dụng có thật sự cần hợp đồng đó không, hợp đồng có nằm ở nơi ổn định không, và quan hệ mới có tạo chu trình hay mở đường cho phụ thuộc không mong muốn không?

Không phải mọi phụ thuộc đều xấu và không có một ma trận đúng cho tất cả hệ thống. Mục tiêu là giới hạn những phụ thuộc gây khóa chặt trách nhiệm, giữ cho module cốt lõi độc lập với chi tiết triển khai, và phát hiện sớm khi mã nguồn đi lệch khỏi quy ước đã thống nhất.

## Tự kiểm tra

1. Trong ma trận của bài, `infrastructure -> application` có thể hợp lệ vì lý do nào? Vì sao chiều ngược lại thường bị cấm?
2. Nếu `catalog -> pricing` và `pricing -> catalog`, vấn đề kiến trúc nào xuất hiện? Nêu một cách xử lý phù hợp.
3. JPMS `requires` và `exports` kiểm soát những khía cạnh nào? Vì sao một dự án vẫn có thể cần ArchUnit?
4. Trong ArchUnit, `mayOnlyBeAccessedByLayers("Presentation")` nói về hướng phụ thuộc nào?
5. Một lời gọi được tìm bằng reflection có thể không xuất hiện như dependency thông thường trong bytecode. Cần bổ sung cách kiểm tra nào cho trường hợp đó?

