# Thay đổi API cấu hình hoặc package

## Mục tiêu bài học

Khi nâng cấp Spring REST Docs, một số lỗi xuất hiện ngay lúc biên dịch vì class, method, constructor hoặc package đã thay đổi. Những lỗi khác chỉ xuất hiện khi chạy test hoặc sinh tài liệu: filter không được gắn đúng chỗ, configurer dùng sai integration, snippet không được tạo hoặc preprocessing không còn hiệu lực.

Bài học thuộc chương **Nâng cấp** của module **SPRING_REST_DOCS**: tạo tài liệu REST API có thể kiểm chứng bằng các bài kiểm thử HTTP với **MockMvc**, **WebTestClient** hoặc **REST Assured**; sinh snippet cho request, response, payload, tham số và header; biên soạn tài liệu Asciidoctor/Markdown rồi tích hợp vào build và CI.

Sau bài học, bạn có thể:

- Phân loại lỗi do package, API signature, dependency hoặc hành vi runtime.
- Xác minh API mới bằng Javadoc và source của đúng phiên bản.
- Chuyển cấu hình documentation, filter và preprocessor có kiểm soát.
- Cập nhật import và dependency mà không trộn version các integration modules.
- Giữ nguyên assertion, document identifier, descriptors và output contract.
- Kiểm tra snippet và tài liệu sau migration.
- Tổ chức thay đổi nhỏ để dễ review và rollback.

## 1. Vì sao API cấu hình thay đổi gây lỗi?

Một nâng cấp có thể thay đổi:

- Package của class hoặc vị trí class giữa các artifact.
- Tên method, overload, generic type hoặc kiểu trả về.
- Constructor được thay bằng factory/configurer.
- Visibility của constructor hoặc method.
- Cách gắn documentation filter vào MockMvc, WebTestClient hoặc REST Assured.
- Kiểu preprocessor được nhận ở request và response.
- Default behavior hoặc thời điểm snippet được tạo.

Không phải mọi thay đổi đều là breaking change. Một method có thể chỉ bị deprecated trước khi bị loại bỏ ở major release kế tiếp. Vì vậy, cần xác định lỗi đang gặp thuộc nhóm nào trước khi sửa.

## 2. Phân loại lỗi trước khi migration

| Triệu chứng | Nhóm nguyên nhân có thể gặp | Nơi kiểm tra đầu tiên |
| --- | --- | --- |
| package does not exist | Class chuyển package hoặc thiếu artifact | Javadoc/package index và dependency tree |
| cannot find symbol | Method/class bị đổi tên, xóa hoặc chưa import đúng | Javadoc đúng version, compiler output |
| method cannot be applied | Signature/overload/generic type thay đổi | Method declaration và type inference |
| NoSuchMethodError | Version runtime lệch với compile time | Dependency resolution và classpath |
| ClassNotFoundException | Artifact không có trong runtime/test classpath | Dependency tree và module dependencies |
| Test chạy nhưng không có snippet | Filter/configurer không được gắn hoặc operation không consume result | Test setup và output directory |
| Snippet sai nội dung | Preprocessor/template/default behavior thay đổi | Operation data và generated output |
| Asciidoctor không tìm thấy file | Snippet ID, tên file hoặc task dependency thay đổi | Generated snippets và include path |

Không sửa mọi lỗi bằng cách thêm import hoặc pin một dependency ngẫu nhiên. Với NoSuchMethodError, compile có thể đã thành công nhưng runtime đang nạp một class version khác; cần tìm dependency nào chọn version đó.

## 3. Xác minh package và API theo đúng version

Trước khi thay code, xác định version đã resolve trong project. Tài liệu current có thể mô tả API mới hơn version đang dùng.

Quy trình kiểm tra:

1. Xác định artifact chứa class đang lỗi.
2. Xác nhận version compile/test runtime đã resolve.
3. Mở Javadoc hoặc source JAR đúng version.
4. Tìm class cũ và class/method thay thế (nếu có).
5. Đọc Deprecated, Since và ghi chú migration.
6. Kiểm tra thay đổi ở integration module liên quan.
7. Thực hiện sửa tối thiểu và compile lại module test.

Ví dụ, khi import không còn được tìm thấy:

~~~java
import org.springframework.restdocs.mockmvc.MockMvcRestDocumentation;
~~~

Không tự suy luận package mới từ tên class. Hãy tìm class trong Javadoc/source artifact của version đích. Nếu class đã chuyển sang artifact khác, cập nhật dependency tương ứng; nếu class bị thay thế, đọc tài liệu migration để dùng API được hỗ trợ.

Các package cần tra cứu tùy integration:

- org.springframework.restdocs.mockmvc
- org.springframework.restdocs.webtestclient
- org.springframework.restdocs.restassured
- org.springframework.restdocs.operation.preprocess
- org.springframework.restdocs.payload

Đây là các khu vực API cần tra cứu, không phải khẳng định rằng mọi class ở đó đã đổi package giữa các phiên bản.

## 4. Kiểm tra dependency và artifact

Spring REST Docs tách integration theo test harness:

| Artifact | Mục đích |
| --- | --- |
| spring-restdocs-core | API nền tảng và operation/snippet model |
| spring-restdocs-mockmvc | Tích hợp MockMvc |
| spring-restdocs-webtestclient | Tích hợp WebTestClient |
| spring-restdocs-restassured | Tích hợp REST Assured |
| spring-restdocs-asciidoctor | Extension hỗ trợ Asciidoctor |

Giữ các artifact cùng dòng release đồng bộ theo hướng dẫn chính thức. Không thêm integration artifact mới nếu test không dùng nó, và không trộn core với integration module ở version khác nhau nếu không có chỉ dẫn rõ ràng.

### 4.1. Kiểm tra với Gradle

~~~powershell
./gradlew dependencyInsight --dependency spring-restdocs --configuration testCompileClasspath
./gradlew dependencyInsight --dependency spring-restdocs --configuration testRuntimeClasspath
~~~

Kiểm tra cả compile và runtime vì hai classpath có thể resolve khác nhau. Nếu dự án dùng version catalog, platform hoặc constraint, tìm nơi quản lý version thay vì sửa trực tiếp dependency đã được sinh ra.

### 4.2. Kiểm tra với Maven

~~~bash
mvn dependency:tree -Dincludes=org.springframework.restdocs
mvn help:effective-pom
~~~

dependency:tree cho thấy artifact thực tế; effective-pom giúp xác định version được quản lý từ parent, BOM hoặc dependencyManagement. Khi gặp lỗi linkage, đọc cả dependency tree của Spring Framework, Spring Test và REST Assured liên quan.

## 5. Migration cấu hình MockMvc

MockMvc thường gắn REST Docs qua MockMvcRestDocumentation.documentationConfiguration(...) trong lúc xây dựng MockMvc. Ví dụ:

~~~java
MockMvc mockMvc = MockMvcBuilders
    .webAppContextSetup(context)
    .apply(documentationConfiguration(restDocumentation))
    .build();
~~~

Operation test ghi snippet:

~~~java
mockMvc.perform(get("/api/orders/{id}", 42))
    .andExpect(status().isOk())
    .andDo(document("orders-get"));
~~~

Khi nâng cấp, xác nhận:

- documentationConfiguration(...) còn nhận đúng context provider hay không.
- Configurer có thay đổi fluent API hoặc kiểu trả về không.
- Custom MockMvcBuilder có đang ghi đè configurer dùng chung không.
- Test slice và full application context đều gắn REST Docs đúng cách.
- document(...) được gọi sau assertions cần thiết.

Nếu dự án có base test hoặc factory tạo MockMvc, cập nhật tại một nơi rồi chạy một test đại diện trước khi mở rộng.

## 6. Migration cấu hình WebTestClient

WebTestClient có integration configurer riêng:

~~~java
WebTestClient client = WebTestClient
    .bindToApplicationContext(applicationContext)
    .configureClient()
    .filter(
        WebTestClientRestDocumentation.documentationConfiguration(
            restDocumentation
        )
    )
    .build();
~~~

Operation:

~~~java
client.get()
    .uri("/api/orders/{id}", 42)
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .jsonPath("$.id").isEqualTo(42)
    .consumeWith(
        WebTestClientRestDocumentation.document("orders-get")
    );
~~~

Khi API cấu hình đổi, kiểm tra cả bind mode:

- bindToApplicationContext dùng application context.
- bindToController phù hợp test một hoặc một số controller cụ thể.
- bindToRouterFunction dùng functional endpoint.
- bindToServer gọi server đã chạy.

Chuyển bind mode có thể làm thay đổi phạm vi middleware, filter, codec và network behavior được kiểm thử. Không coi đây là thay đổi thuần cú pháp.

## 7. Migration cấu hình REST Assured

REST Assured tích hợp Spring REST Docs qua filter:

~~~java
RequestSpecification documentationSpec =
    new RequestSpecBuilder()
        .addFilter(
            RestAssuredRestDocumentation.documentationConfiguration(
                restDocumentation
            )
        )
        .build();
~~~

Test operation:

~~~java
given(documentationSpec)
    .filter(document("orders-get"))
    .when()
    .get("/api/orders/{id}", 42)
    .then()
    .statusCode(200);
~~~

Khi nâng cấp, xác nhận package của RestAssuredRestDocumentation và filter còn đúng; RequestSpecification được dùng trong request thực thi; documentation filter được gắn đúng vị trí; REST Assured version tương thích với Spring REST Docs integration; response assertions vẫn chạy và làm test fail khi contract không đạt.

Nếu test có nhiều filter, kiểm tra thứ tự và side effect của từng filter. Không thay đổi filter order chỉ để làm snippet giống baseline nếu điều đó làm sai behavior của test.

## 8. Migration preprocessors và custom snippets

Preprocessors có thể được cấu hình theo request/response hoặc ở documentation configurer. Khi method signature thay đổi, cần kiểm tra kiểu cụ thể mà integration yêu cầu.

~~~java
mockMvc.perform(get("/api/profile")
        .header("Authorization", "Bearer test-token"))
    .andExpect(status().isOk())
    .andDo(document("profile-get",
        preprocessRequest(removeHeaders("Authorization")),
        preprocessResponse(prettyPrint())
    ));
~~~

Khi nâng cấp:

- Xác minh import của Preprocessors, request/response preprocessor interfaces và helper methods.
- Kiểm tra overload preprocessRequest(...)/preprocessResponse(...).
- Kiểm tra default preprocessors trên configurer có còn cùng hành vi.
- Kiểm tra custom OperationPreprocessor có cần cập nhật interface hoặc method.
- Xác nhận header/token nhạy cảm vẫn được che trong snippet.

Custom snippet template cũng cần được kiểm tra. API template có thể vẫn compile nhưng template output thay đổi do model/attribute mới. Sinh lại snippet đại diện và so sánh nội dung thay vì chỉ xác nhận task thành công.

## 9. Giữ nguyên contract và document identifiers

Khi sửa API cấu hình hoặc package, không thay đổi đồng thời:

- Document identifier như orders-get.
- Path/query parameter names.
- Field descriptors và mô tả contract.
- Preprocessor masking rules.
- Template format và output directory.

Giữ các yếu tố này ổn định giúp cô lập tác động của migration. Nếu bắt buộc đổi một yếu tố, ghi rõ lý do và cập nhật nơi include snippet tương ứng.

Ví dụ tài liệu AsciiDoc:

~~~asciidoc
include::{snippets}/orders-get/http-request.adoc[]
include::{snippets}/orders-get/http-response.adoc[]
include::{snippets}/orders-get/response-fields.adoc[]
~~~

Sau khi nâng cấp, kiểm tra các file trên vẫn được sinh với identifier và tên phù hợp. Nếu tên snippet thay đổi theo version/template, cập nhật include dựa trên output thực tế, không đoán tên file.

## 10. Cách xử lý lỗi compiler hiệu quả

Khi compiler báo cannot find symbol, xử lý theo thứ tự:

1. Đọc toàn bộ lỗi đầu tiên, xác định symbol và source file.
2. Kiểm tra dependency version đã resolve.
3. Tìm class/method trong Javadoc/source JAR của version đích.
4. So sánh signature cũ và mới.
5. Cập nhật import, dependency hoặc call site đúng nguyên nhân.
6. Compile lại test source liên quan.
7. Chạy test operation và kiểm tra snippet.

Không sửa nhiều file cùng lúc trước khi biết API thay đổi cụ thể. Với NoSuchMethodError, đừng chỉ đổi import: cần kiểm tra runtime classpath và loại trừ hai version cùng tồn tại.

## 11. So sánh output sau migration

Chạy test vào thư mục snippet mới, tách biệt với output cũ. So sánh:

| Nội dung | Cần xác nhận |
| --- | --- |
| HTTP request | Method, URI, query, headers và body |
| HTTP response | Status, headers và body |
| Parameter snippets | Tên, mô tả và encoding |
| Field snippets | Field paths, types, descriptions, optional |
| Preprocessing | Pretty-print, masking, normalization |
| Custom snippets | Template, attributes và nội dung render |
| Tài liệu cuối | Include paths, links, TOC và Asciidoctor/Markdown output |

Một số khác biệt về thứ tự header hoặc whitespace có thể chỉ là formatting. Khác biệt về status, field, content type, parameter hoặc giá trị đã che là thay đổi cần điều tra.

Với JSON, so sánh cấu trúc nếu thứ tự property không phải contract. Với header, phân biệt header do client test tự thêm với header API thực sự cam kết.

## 12. Lỗi thường gặp

| Dấu hiệu | Nguyên nhân | Cách khắc phục |
| --- | --- | --- |
| Package không còn tồn tại | Class chuyển module/package hoặc thiếu dependency | Tra Javadoc/source đúng version và kiểm tra artifact |
| Method không nhận tham số cũ | Overload hoặc generic signature thay đổi | Dùng signature đúng version, không ép kiểu tùy tiện |
| NoSuchMethodError | Compile/runtime dependency mismatch | Kiểm tra dependencyInsight hoặc dependency tree |
| MockMvc không sinh snippet | Configurer không được apply vào builder đang dùng | Kiểm tra factory/base test và builder thực tế |
| WebTestClient không ghi operation | Filter/consumeWith đặt sai vị trí | Kiểm tra documentation filter và exchange chain |
| REST Assured không ghi snippet | Filter không gắn vào request specification thực thi | Kiểm tra spec được truyền vào given(...) |
| Preprocessor không còn che token | Import hoặc overload/configuration đổi | Kiểm tra output snippet và API mới |
| Asciidoctor báo thiếu include | Document ID/tên snippet/output directory thay đổi | Đối chiếu generated-snippets và cập nhật include |
| Custom snippet render sai | Template model hoặc template format thay đổi | So sánh template và snippet output |
| Một số test dùng API cũ | Cấu hình bị nhân bản ở nhiều base test | Tập trung cấu hình và tìm toàn bộ call site |

## 13. Bài thực hành

Chọn một test REST Docs đang sử dụng MockMvc, WebTestClient hoặc REST Assured.

Yêu cầu:

1. Ghi lại import, configurer/filter, preprocessors và document identifier hiện tại.
2. Chọn một version mục tiêu và xác nhận API bằng Javadoc/source đúng version.
3. Tạo nhánh migration riêng, cập nhật dependency và các artifact liên quan đồng bộ.
4. Sửa package/import/signature theo API mới; không thay đổi contract của operation.
5. Chạy test và xác nhận request/response assertions vẫn đầy đủ.
6. Sinh snippet vào thư mục mới, so sánh với baseline.
7. Render Asciidoctor/Markdown và xác nhận include không bị hỏng.
8. Chạy CI với test và task tạo tài liệu.

**Tiêu chí hoàn thành:** không còn API/package cũ không được hỗ trợ; dependency được resolve đồng bộ; test pass; snippet và tài liệu phản ánh cùng contract; thay đổi output được giải thích và có thể review.

## Ghi nhớ

Khi nâng cấp Spring REST Docs, hãy phân biệt lỗi package/import, thay đổi method signature, dependency mismatch và thay đổi hành vi runtime. Xác minh API mới bằng Javadoc/source đúng version trước khi sửa. Cập nhật configurer/filter theo đúng integration MockMvc, WebTestClient hoặc REST Assured; giữ nguyên assertions, document identifiers, descriptors và preprocessing rules. Cuối cùng, chạy test, sinh snippet vào output sạch, so sánh nội dung và render tài liệu. Migration hoàn tất khi cả test HTTP lẫn pipeline tài liệu đều hoạt động với API mới.

**Tài liệu tham khảo:** [Spring REST Docs Reference](https://docs.spring.io/spring-restdocs/reference/), [Spring REST Docs API Javadoc](https://docs.spring.io/spring-restdocs/docs/current/api/), [Spring REST Docs Releases](https://github.com/spring-projects/spring-restdocs/releases), [MockMvcRestDocumentation API](https://docs.spring.io/spring-restdocs/docs/current/api/org/springframework/restdocs/mockmvc/MockMvcRestDocumentation.html), [WebTestClient integration reference](https://docs.spring.io/spring-restdocs/reference/) và [REST Assured Usage Guide](https://github.com/rest-assured/rest-assured/wiki/Usage).
