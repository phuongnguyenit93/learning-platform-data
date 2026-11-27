# Kiểm tra thay đổi package khi nâng version

## Vì sao phải kiểm tra package trước khi nâng version?

Khi nâng Spring Modulith, mã nguồn có thể không biên dịch vì một class, annotation hoặc package đã được đổi tên hoặc loại bỏ. Một số thay đổi khác không làm import lỗi nhưng lại ảnh hưởng đến tài liệu sinh tự động, cấu hình dependency hoặc hành vi lúc chạy.

Cần phân biệt ba loại thay đổi:

- **Package và API Java:** tên package, class, annotation hoặc method mà mã nguồn import và gọi.
- **Artifact và dependency:** tên thư viện Maven/Gradle, phạm vi compile/runtime/test và các module được tách hoặc gộp.
- **Hành vi mặc định:** cách sinh sơ đồ, nội dung canvas, vòng đời event publication hoặc yêu cầu của Spring Boot và Spring Framework.

Một lần nâng version an toàn phải kiểm tra cả ba loại. Chỉ sửa import cho đến khi compiler hết lỗi chưa đủ để xác nhận ứng dụng vẫn giữ đúng hành vi kiến trúc.

## Xác định chính xác phiên bản nguồn và phiên bản đích

Trước khi sửa mã, ghi lại:

- Phiên bản Spring Modulith hiện tại và phiên bản muốn nâng lên.
- Phiên bản Spring Boot và Spring Framework mà hai dòng Modulith hỗ trợ.
- Các starter và artifact Spring Modulith đang được khai báo trực tiếp.
- Những API được dùng trong production code, test và quy trình tạo tài liệu.

Spring Modulith có nhiều dòng phát hành tương ứng với các thế hệ Spring Boot khác nhau. Ví dụ, Spring Modulith 2.0 nâng baseline lên Spring Boot 4 và Spring Framework 7; vì vậy việc nâng từ 1.x lên 2.x có thể cần nâng cả nền tảng Spring. Hãy đối chiếu bảng tương thích và release notes của đúng phiên bản đích trước khi thay đổi dependency.

Không lấy một bảng tương thích cũ làm căn cứ cho phiên bản mới nhất. Các bản vá và bản phát hành mới có thể bổ sung hỗ trợ nền tảng hoặc thay đổi dependency đi kèm.

## Nhận diện thay đổi tên package từ Moduliths sang Spring Modulith

Một thay đổi quan trọng trong lịch sử dự án là việc chuyển từ thư viện Moduliths sang Spring Modulith. Tên package và một số API đã được đổi để phản ánh namespace Spring Modulith.

Bảng dưới đây tóm tắt các ánh xạ được tài liệu migration chính thức công bố:

| API cũ của Moduliths | API mới của Spring Modulith |
|---|---|
| org.moduliths.model.Modules | org.springframework.modulith.core.ApplicationModules |
| org.moduliths.model.ModuleDetectionStrategy | org.springframework.modulith.core.ApplicationModuleDetectionStrategy |
| org.moduliths.test.ModuleTest | org.springframework.modulith.test.ApplicationModuleTest |
| org.moduliths.docs.Documenter.Options | org.springframework.modulith.docs.Documenter.DiagramOptions |

Ví dụ, code cũ có thể khởi tạo mô hình module như sau:

~~~java
import org.moduliths.model.Modules;

class ModularityTests {

    void verifyModules() {
        Modules.of(Application.class).verify();
    }
}
~~~

Sau khi chuyển sang Spring Modulith, sử dụng API mới:

~~~java
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    void verifyModules() {
        ApplicationModules.of(Application.class).verify();
    }
}
~~~

Tên class thay đổi cùng package. Vì vậy, không thể chỉ thay prefix org.moduliths thành org.springframework.modulith rồi giữ nguyên tên class cũ.

Tương tự, chiến lược phát hiện module cũ:

~~~java
import org.moduliths.model.ModuleDetectionStrategy;
~~~

được chuyển sang API mới:

~~~java
import org.springframework.modulith.core.ApplicationModuleDetectionStrategy;
~~~

Với test module, annotation cũ ModuleTest được thay bằng ApplicationModuleTest trong package org.springframework.modulith.test. Hãy kiểm tra lại các thuộc tính annotation và bootstrap mode theo Javadoc của phiên bản đích, thay vì giả định mọi cách cấu hình cũ đều có tên hoặc semantics giống hệt.

## Cập nhật API Documenter và kết quả tài liệu

Documenter cũng có thay đổi tên API. Kiểu tùy chọn sơ đồ cũ:

~~~java
org.moduliths.docs.Documenter.Options
~~~

được đổi thành:

~~~java
org.springframework.modulith.docs.Documenter.DiagramOptions
~~~

Ví dụ minh họa cấu hình kiểu sơ đồ UML trong API mới:

~~~java
import org.springframework.modulith.core.ApplicationModules;
import org.springframework.modulith.docs.Documenter;
import org.springframework.modulith.docs.Documenter.DiagramOptions;
import org.springframework.modulith.docs.Documenter.DiagramOptions.DiagramStyle;

var modules = ApplicationModules.of(Application.class);

var options = DiagramOptions.defaults()
    .withStyle(DiagramStyle.UML);

new Documenter(modules).writeDocumentation(
    options,
    Documenter.CanvasOptions.defaults()
);
~~~

Hãy đối chiếu constructor và factory method với Javadoc của phiên bản đang dùng, vì các chi tiết tạo options có thể khác theo dòng phát hành. Trong API hiện hành, Documenter.Options vẫn tồn tại cho cấu hình thư mục đầu ra; kiểu options sơ đồ được truyền vào writeDocumentation() là Documenter.DiagramOptions. Vì vậy, không nhầm kiểu Options mới này với kiểu cùng tên trong API Moduliths cũ.

Ngoài import, tài liệu được sinh cũng có thay đổi mặc định:

- Tài liệu migration ghi nhận component diagram chuyển mặc định sang C4. Hãy kiểm tra mặc định của đúng phiên bản đích; nếu cần giữ sơ đồ UML, cấu hình DiagramOptions.withStyle(DiagramStyle.UML).
- Application Module Canvas ẩn các kiểu không được expose theo mặc định. Nếu tài liệu nội bộ cần hiển thị các kiểu bên trong module, cấu hình CanvasOptions để gọi revealInternals().
- Thư mục đầu ra đổi từ moduliths-docs sang spring-modulith-docs trong thư mục build, ví dụ target với Maven.

Các thay đổi này có thể khiến pipeline tài liệu hoặc liên kết trong trang onboarding không còn tìm thấy file ở đường dẫn cũ. Sau khi nâng version, hãy kiểm tra lại đường dẫn và nội dung thực tế của sơ đồ được sinh.

## Kiểm tra các thay đổi giữa các dòng Spring Modulith

Sau khi mã nguồn đã dùng namespace org.springframework.modulith, không nên mặc định rằng mọi lần nâng từ 1.x lên 2.x đều cần đổi toàn bộ package. Hãy phân biệt migration từ Moduliths cũ với migration giữa các phiên bản Spring Modulith.

Một số thay đổi đáng chú ý theo dòng phát hành:

| Dòng phát hành | Thay đổi cần rà soát |
|---|---|
| Spring Modulith 2.0 | Baseline chuyển sang Spring Boot 4 và Spring Framework 7; annotation @ApplicationEventListener đã deprecated trước đó bị loại bỏ |
| Spring Modulith 2.1 | Hạ tầng observability được tách rõ API và Core; các dependency trực tiếp và customizer cần được rà soát |
| Spring Modulith 2.2 | Bổ sung khả năng khai báo allowed dependencies trên toàn bộ phần module expose bằng cú pháp module :: **; hỗ trợ đăng ký NamedInterface cho type theo chương trình |

Các thay đổi trên không cùng một loại. Baseline nền tảng và annotation ảnh hưởng đến compile/runtime; việc tách observability ảnh hưởng đến artifact và classpath; thay đổi allowed dependencies bổ sung khả năng của API.

### Từ Spring Modulith 1.x lên 2.0

Spring Modulith 2.0 yêu cầu nền tảng Spring Boot 4 và Spring Framework 7. Ngoài việc kiểm tra tương thích dependency, hãy rà soát các API đã deprecated trong dòng 1.x.

Một ví dụ là @ApplicationEventListener đã bị loại bỏ trong 2.0. Tìm mọi nơi sử dụng annotation này và chuyển sang cơ chế listener được hỗ trợ phù hợp với semantics cần có. Với tích hợp module thông thường, @ApplicationModuleListener thường là lựa chọn cần xem xét; nếu yêu cầu xử lý event khác, hãy chọn annotation Spring phù hợp và xác nhận lại thời điểm xử lý, transaction và tính bất đồng bộ.

Dòng 2.0 cũng thay đổi vòng đời Event Publication Registry. Nếu ứng dụng dùng JDBC, JPA, MongoDB hoặc Neo4j để lưu publication, hãy đọc migration notes cho store tương ứng và kiểm tra schema hiện tại. Không giả định nâng thư viện là đủ để mọi schema hoặc trạng thái publication cũ tự chuyển đổi.

### Từ Spring Modulith 2.0 lên 2.1

Hạ tầng observability được tinh chỉnh và tách thành API và Core. Với cấu hình dependency trực tiếp, cần kiểm tra artifact:

- spring-modulith-observability-api cung cấp API tùy chỉnh và thường nằm trong compile classpath khi mã ứng dụng triển khai customizer.
- spring-modulith-observability-core cung cấp phần triển khai runtime và thường nằm trong runtime classpath.

Nếu ứng dụng dùng starter Insight, các dependency cần thiết thường được kéo vào theo starter. Nếu khai báo artifact riêng, hãy đối chiếu dependency tree và hướng dẫn của phiên bản đích. Không giữ một dependency cũ chỉ vì tên artifact vẫn còn trong file build; cần xác nhận artifact đó còn cung cấp class mà ứng dụng đang import.

## Quy trình tìm package và API đã thay đổi

Trước khi sửa, tìm tất cả vị trí tham chiếu đến namespace cũ, class cũ và annotation deprecated trong mã nguồn production, test và cấu hình tài liệu.

Ví dụ với ripgrep:

~~~bash
rg -n "org\.moduliths|ModuleDetectionStrategy|ModuleTest|Documenter\.Options|ApplicationEventListener" src
~~~

Nếu dự án dùng nhiều source set hoặc module con, mở rộng phạm vi tìm kiếm đến các thư mục chứa mã nguồn và test tương ứng. Không chỉ tìm file Java; kiểm tra Kotlin, cấu hình build, script tạo tài liệu và các ví dụ onboarding nếu chúng được duy trì trong cùng repository.

Lập bảng migration trước khi chỉnh sửa:

| Vị trí | API cũ | API mới | Việc cần làm |
|---|---|---|---|
| Test kiến trúc | Modules | ApplicationModules | Cập nhật import và lời gọi |
| Module detection | ModuleDetectionStrategy | ApplicationModuleDetectionStrategy | Cập nhật implements và method signature |
| Test module | ModuleTest | ApplicationModuleTest | Cập nhật annotation và kiểm tra bootstrap mode |
| Sinh tài liệu | Documenter.Options | Documenter.DiagramOptions | Cập nhật kiểu options và style |
| Event listener | ApplicationEventListener | API listener được hỗ trợ | Xem lại transaction và timing |
| Observability | Artifact cũ | observability-api / observability-core | Điều chỉnh compile/runtime dependency |

Không thực hiện thay thế chuỗi trên toàn repository mà chưa xem ngữ cảnh. Một class cùng tên có thể thuộc package khác hoặc là kiểu của ứng dụng, không phải API Spring Modulith.

## Nâng dependency theo một bộ phiên bản thống nhất

Spring Modulith cung cấp BOM để quản lý phiên bản các artifact trong cùng dòng phát hành. Khi nâng, cập nhật BOM hoặc dependency management một lần, rồi kiểm tra các starter và artifact Spring Modulith có cùng phiên bản tương thích.

Ví dụ Maven:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.modulith</groupId>
            <artifactId>spring-modulith-bom</artifactId>
            <version>${spring-modulith.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Ví dụ Gradle:

~~~groovy
dependencies {
    implementation platform(
        "org.springframework.modulith:spring-modulith-bom:${springModulithVersion}"
    )

    implementation "org.springframework.modulith:spring-modulith-starter-core"
    testImplementation "org.springframework.modulith:spring-modulith-starter-test"
}
~~~

Đây là mẫu cấu hình; hãy dùng version property và starter đúng với nhu cầu thực tế của dự án. Không ghim một phiên bản riêng cho từng artifact nếu BOM đã quản lý chúng, trừ khi có lý do tương thích rõ ràng.

Sau khi thay đổi dependency, kiểm tra dependency tree để phát hiện đồng thời nhiều dòng phiên bản, artifact cũ không còn dùng và dependency bắc cầu bị loại bỏ. Tên artifact và tên package Java không phải lúc nào cũng có quan hệ một-một; việc đổi artifact không đồng nghĩa package của mọi class trong artifact đó đều đổi.

## Kiểm tra hành vi sau khi cập nhật import

Khi compiler đã nhận diện các API mới, kiểm tra những hành vi có thể thay đổi:

**Mô hình module:** ApplicationModules.of(Application.class) vẫn phát hiện đúng module, named interface và dependency.

**Kiểm chứng kiến trúc:** ApplicationModules.verify() vẫn chạy và không bỏ sót các vi phạm trước đây.

**Test module:** @ApplicationModuleTest vẫn khởi tạo đúng phạm vi module và các dependency được chọn.

**Tài liệu:** Documenter tạo sơ đồ và canvas tại đường dẫn mới; style và phần internals hiển thị đúng yêu cầu.

**Event:** Listener vẫn chạy đúng thời điểm, trong transaction phù hợp; Event Publication Registry lưu và hoàn tất publication theo semantics của phiên bản mới.

**Observability:** Các metric, span và customizer vẫn được nạp khi runtime khởi động.

Một bài test cấu trúc có thể tiếp tục dùng:

~~~java
package com.acme.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void verifiesModuleStructureAfterUpgrade() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

Test này xác nhận mô hình module hiện tại thỏa mãn các quy tắc kiến trúc. Nó không thay thế kiểm tra transaction, event publication, schema hoặc nội dung tài liệu.

## Checklist nâng version

Trước khi hoàn tất một lần nâng Spring Modulith, hãy xác nhận:

1. Đã xác định phiên bản nguồn, phiên bản đích và baseline Spring Boot/Framework tương ứng.
2. Đã đọc migration appendix, release notes và Javadoc của phiên bản đích.
3. Đã tìm mọi import, annotation và lời gọi API cũ trong production và test sources.
4. Đã thay tên class và package theo mapping chính thức, không thay chuỗi máy móc.
5. Đã rà soát API deprecated hoặc bị loại bỏ, đặc biệt listener và test annotation.
6. Đã cập nhật BOM, starter và artifact theo đúng scope compile/runtime/test.
7. Đã kiểm tra thay đổi của Documenter, thư mục output và CanvasOptions.
8. Đã rà soát event publication schema và semantics nếu ứng dụng dùng registry bền vững.
9. Đã kiểm tra dependency tree để tránh trộn các dòng phiên bản.
10. Đã chạy kiểm chứng cấu trúc và các test tích hợp liên quan trong quy trình nâng cấp của dự án.

## Bài tập vận dụng

Một ứng dụng vẫn dùng thư viện Moduliths cũ. Test kiến trúc import org.moduliths.model.Modules, test tích hợp dùng org.moduliths.test.ModuleTest, và test tạo tài liệu dùng Documenter.Options. Nhóm muốn chuyển sang Spring Modulith và giữ sơ đồ UML trong tài liệu onboarding.

Hãy lập kế hoạch:

1. Đối chiếu phiên bản Spring Modulith đích với Spring Boot và Spring Framework hiện tại.
2. Chuyển Modules sang ApplicationModules và ModuleTest sang ApplicationModuleTest.
3. Chuyển ModuleDetectionStrategy sang ApplicationModuleDetectionStrategy nếu ứng dụng có custom detection.
4. Chuyển Documenter.Options sang Documenter.DiagramOptions.
5. Cấu hình DiagramStyle.UML nếu cần giữ kiểu sơ đồ cũ.
6. Kiểm tra CanvasOptions nếu nhóm cần hiển thị các kiểu nội bộ.
7. Cập nhật liên kết đến thư mục spring-modulith-docs.
8. Chạy kiểm chứng cấu trúc module và kiểm tra tài liệu sau khi sinh.

Kết quả mong đợi: source code dùng đúng namespace và class của Spring Modulith; tài liệu sinh ra vẫn có style UML và nội dung canvas phù hợp; pipeline không còn phụ thuộc đường dẫn output hoặc annotation cũ.

## Tiêu chí hoàn tất

Bạn đã nắm được chủ đề khi có thể phân biệt thay đổi package với thay đổi artifact và hành vi mặc định, tra cứu mapping chính thức từ Moduliths sang Spring Modulith, cập nhật import và annotation theo đúng API, kiểm tra baseline Spring Boot/Framework, và xác minh mô hình module cùng tài liệu sau khi nâng version.

Tài liệu tham khảo:

- [Spring Modulith — Appendix: Migrating from Moduliths](https://docs.spring.io/spring-modulith/reference/appendix.html)
- [Spring Modulith 2.0 GA release notes](https://spring.io/blog/2025/11/21/spring-modulith-2-0-ga-1-4-5-and-1-3-11-released/)
- [Spring Modulith 2.1 GA release notes](https://spring.io/blog/2026/06/11/spring-modulith-2-1-ga-2-0-7-and-1-4-12-released/)
- [Spring Modulith — Production-ready Features](https://docs.spring.io/spring-modulith/reference/production-ready.html)
- [Spring Modulith — API documentation](https://docs.spring.io/spring-modulith/docs/current/api/)
