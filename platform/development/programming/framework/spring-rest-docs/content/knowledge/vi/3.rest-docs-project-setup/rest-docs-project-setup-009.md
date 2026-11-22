# Đảm bảo tác vụ tạo tài liệu phụ thuộc tác vụ test

Spring REST Docs chỉ sinh snippet khi một bài kiểm thử HTTP thực sự chạy qua phần ghi nhận tài liệu. Asciidoctor có thể render file nguồn, nhưng nếu bước render chạy trước test hoặc không được nối với test, các lệnh include sẽ thiếu file hoặc đọc nhầm snippet còn sót từ lần build trước. Trong Maven, cần thiết kế thứ tự rõ ràng: **chạy đúng test tạo snippet, sau đó mới biên soạn tài liệu**.

Bài học thuộc chương **Thiết lập dự án** của module `SPRING_REST_DOCS`. Module thực hành tạo tài liệu REST API có thể kiểm chứng bằng Spring REST Docs từ test với MockMvc, WebTestClient hoặc REST Assured, sinh snippet cho request, response, payload, tham số và header, rồi biên soạn Asciidoctor/Markdown trong build và CI. Bài này tập trung vào dependency giữa các bước trong Maven lifecycle, phân biệt Surefire và Failsafe, kiểm soát goal trực tiếp, profile và output cũ.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vì sao task Asciidoctor phải chạy sau test đã sinh snippet.
2. Đọc Maven lifecycle và chọn phase thích hợp cho execution của plugin.
3. Cấu hình asciidoctor-maven-plugin để chạy trong lifecycle có test trước.
4. Phân biệt Surefire với Failsafe và chọn đúng suite tạo tài liệu.
5. Nhận biết vì sao gọi trực tiếp plugin goal hoặc bỏ qua test có thể tạo tài liệu thiếu/cũ.
6. Thiết kế profile, multi-module và CI để giữ thứ tự test → snippet → render.
7. Chẩn đoán lỗi include và xác minh build từ trạng thái sạch.

## 2. Vì sao cần dependency giữa test và render?

Spring REST Docs không tạo snippet bằng cách quét source code. Test thực thi request, nhận response, kiểm tra kết quả và gọi document(...). Khi đó các snippet mới được ghi. Asciidoctor đọc các file này trong lúc xử lý directive include.

```text
Source code + HTTP documentation tests
                 │
                 ▼
          Maven test lifecycle
                 │
                 ▼
       Surefire chạy documentation tests
                 │
                 ▼
       Spring REST Docs ghi operation
                 │
                 ▼
       target/generated-snippets/
                 │
                 ▼
       asciidoctor-maven-plugin
                 │
                 ▼
       Resolve include:: và render
                 │
                 ▼
       target/generated-docs/
```

Nếu Asciidoctor chạy trước khi thư mục snippet được tạo, include như:

```asciidoc
include::{snippets}/orders-get-success/http-response.adoc[]
```

không thể tìm thấy file. Nếu thư mục vẫn chứa snippet từ build trước, trang có thể render thành công nhưng minh họa không thuộc lần chạy hiện tại. Đây là lỗi khó phát hiện vì đầu ra trông có vẻ hợp lệ.

Dependency phải bảo đảm **đúng test suite tạo dữ liệu mà task render sử dụng**, không chỉ bảo đảm hai task cùng xuất hiện đâu đó trong POM.

## 3. Maven lifecycle và thứ tự phase

Maven default lifecycle có các phase chính sau:

| Phase | Vai trò |
| --- | --- |
| validate | Xác nhận project hợp lệ |
| compile | Biên dịch source chính |
| test-compile | Biên dịch source test |
| test | Chạy unit test qua Surefire theo cấu hình |
| prepare-package | Chuẩn bị trước khi đóng gói |
| package | Tạo artifact JAR/WAR |
| integration-test | Chạy bước kiểm thử tích hợp được cấu hình |
| verify | Kiểm tra bổ sung để xác nhận package đạt yêu cầu |
| install | Cài artifact vào local repository |
| deploy | Đẩy artifact tới remote repository |

Khi gọi một phase, Maven thực thi các phase trước nó trong cùng lifecycle. Ví dụ, lệnh mvn package đi qua test, prepare-package rồi package. Do đó, nếu Asciidoctor được bind vào prepare-package, các test Surefire ở phase test sẽ chạy trước trong cùng invocation.

### 3.1. Chọn phase cho Asciidoctor

Cấu hình execution phổ biến:

```xml
<execution>
    <id>generate-api-docs</id>
    <phase>prepare-package</phase>
    <goals>
        <goal>process-asciidoc</goal>
    </goals>
</execution>
```

Điều này phù hợp khi documentation tests chạy bằng Surefire ở phase test. Khi build đi tới prepare-package, test đã chạy và snippet đã sẵn sàng.

Phase không tự bảo đảm test đã tạo snippet. Các trường hợp sau vẫn có thể làm thiếu dữ liệu:

- Có tham số -DskipTests hoặc cấu hình Surefire bỏ qua test.
- Test class không khớp naming/include configuration.
- Documentation test chỉ chạy trong profile không được bật.
- Test tạo snippet ở Failsafe integration-test, vốn chạy sau prepare-package.
- Test chưa cấu hình Spring REST Docs hoặc không gọi document(...).

Vì vậy, trước khi chọn phase, phải xác định test suite nào là nguồn snippet.

## 4. Cấu hình Surefire và asciidoctor-maven-plugin

Ví dụ sau dùng JUnit 5, MockMvc và documentation tests chạy trong phase test. Các version chỉ là bộ phiên bản minh họa; dự án cần chọn phiên bản tương thích với Spring Boot/Spring Framework, Java và plugin đang sử dụng.

```xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
    <spring-restdocs.version>3.0.3</spring-restdocs.version>
    <asciidoctor.maven.plugin.version>2.2.6</asciidoctor.maven.plugin.version>
</properties>

<dependencies>
    <dependency>
        <groupId>org.springframework.restdocs</groupId>
        <artifactId>spring-restdocs-mockmvc</artifactId>
        <version>${spring-restdocs.version}</version>
        <scope>test</scope>
    </dependency>
</dependencies>

<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-surefire-plugin</artifactId>
            <version>3.2.5</version>
        </plugin>

        <plugin>
            <groupId>org.asciidoctor</groupId>
            <artifactId>asciidoctor-maven-plugin</artifactId>
            <version>${asciidoctor.maven.plugin.version}</version>
            <dependencies>
                <dependency>
                    <groupId>org.springframework.restdocs</groupId>
                    <artifactId>spring-restdocs-asciidoctor</artifactId>
                    <version>${spring-restdocs.version}</version>
                </dependency>
            </dependencies>
            <executions>
                <execution>
                    <id>render-api-docs</id>
                    <phase>prepare-package</phase>
                    <goals>
                        <goal>process-asciidoc</goal>
                    </goals>
                </execution>
            </executions>
            <configuration>
                <sourceDirectory>
                    ${project.basedir}/src/docs/asciidoc
                </sourceDirectory>
                <outputDirectory>
                    ${project.build.directory}/generated-docs
                </outputDirectory>
                <backend>html</backend>
                <attributes>
                    <snippets>
                        ${project.build.directory}/generated-snippets
                    </snippets>
                </attributes>
            </configuration>
        </plugin>
    </plugins>
</build>
```

Dependency spring-restdocs-mockmvc nằm trong project dependencies và có scope test. Dependency spring-restdocs-asciidoctor nằm bên trong cấu hình plugin vì nó hỗ trợ tích hợp Asciidoctor. Hai dependency không thay thế nhau.

### 4.1. Test phải thật sự tạo snippet

Ví dụ MockMvc tối giản:

```java
@ExtendWith(RestDocumentationExtension.class)
class ProductDocumentationTest {

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider provider) {
        mockMvc = MockMvcBuilders
            .standaloneSetup(new ProductController())
            .apply(documentationConfiguration(provider))
            .build();
    }

    @Test
    void getProduct() throws Exception {
        mockMvc.perform(
                RestDocumentationRequestBuilders
                    .get("/api/products/{id}", 7L)
                    .accept(MediaType.APPLICATION_JSON)
            )
            .andExpect(status().isOk())
            .andDo(document("products-get-success"));
    }
}
```

Ví dụ lược bớt import và descriptor để tập trung vào task dependency. Với dự án thực, cần assertion và descriptor cho path/query parameter, header và payload thuộc hợp đồng. Khi test chạy, output có thể gồm:

```text
target/generated-snippets/products-get-success/
    http-request.adoc
    http-response.adoc
    curl-request.adoc
```

Các bảng field/parameter chỉ được tạo khi test khai báo descriptor tương ứng. Không giả định mọi operation đều sinh mọi snippet.

### 4.2. Kiểm tra Surefire có phát hiện test

Surefire chỉ chạy test được phát hiện theo provider, naming convention, include/exclude và profile cấu hình. Nếu class documentation test không khớp pattern, Maven có thể đi tiếp tới prepare-package mà không tạo snippet.

Kiểm tra report trong target/surefire-reports và log Maven để xác nhận đúng class và số test đã chạy. Exit code 0 một mình chưa đủ: một build không phát hiện test nào cũng có thể thành công nếu không có kiểm tra bổ sung.

## 5. Phân biệt Surefire và Failsafe

Một dự án có thể tạo snippet từ unit/MVC test hoặc từ integration test khởi động server và gọi qua HTTP. Hai cách này diễn ra ở các phase khác nhau.

| Plugin | Phase phổ biến | Mục đích |
| --- | --- | --- |
| Maven Surefire | test | Chạy unit test và các test thuộc suite này |
| Maven Failsafe | integration-test và verify | Chạy integration test và kiểm tra kết quả suite |

Failsafe thường dùng goal integration-test để thực thi test và goal verify để kiểm tra kết quả. Nếu integration test tạo snippet, Asciidoctor phải chạy sau khi suite đó đã thực thi.

### 5.1. Snippet từ Surefire

Có thể bind render ở prepare-package nếu documentation tests chạy tại phase test và đó là nguồn snippet cần dùng:

```text
test (Surefire)
    │
    ▼
generated-snippets
    │
    ▼
prepare-package (Asciidoctor)
    │
    ▼
package
    │
    ▼
verify
```

Lệnh mvn clean verify đi qua các phase trước đó trong default lifecycle, do vậy Surefire test ở phase test chạy trước prepare-package.

### 5.2. Snippet từ Failsafe

Nếu snippet chỉ được tạo ở integration-test, Asciidoctor bind vào prepare-package chạy quá sớm. Có thể chuyển execution render sang phase verify:

```xml
<execution>
    <id>render-api-docs-after-integration-tests</id>
    <phase>verify</phase>
    <goals>
        <goal>process-asciidoc</goal>
    </goals>
</execution>
```

Cần kiểm tra thứ tự execution ở phase verify trong effective POM và log Maven: test Failsafe phải được thực thi trước khi Asciidoctor đọc snippet, và kết quả Failsafe phải được xác nhận theo lifecycle. Nếu thứ tự cùng phase không đủ rõ, hãy dùng một phase/job muộn hơn hoặc tách biên soạn tài liệu thành bước sau khi integration-test suite đã hoàn tất.

**Không bind Asciidoctor vào prepare-package nếu snippet chỉ xuất hiện ở integration-test.**

## 6. Goal trực tiếp không chạy các phase test

Một lỗi thường gặp là chạy:

```bash
mvn asciidoctor:process-asciidoc
```

Đây là cách gọi trực tiếp plugin goal. Nó không mặc định chạy toàn bộ các phase trước prepare-package. Nếu test chưa chạy, snippet không tồn tại; nếu output cũ còn lại, plugin có thể render từ dữ liệu cũ.

| Lệnh | Hành vi liên quan |
| --- | --- |
| mvn test | Chạy lifecycle đến phase test; không chạy execution ở prepare-package |
| mvn package | Chạy test rồi prepare-package và package |
| mvn verify | Chạy lifecycle đến verify |
| mvn clean verify | Dọn output build rồi chạy lifecycle đến verify |
| mvn asciidoctor:process-asciidoc | Gọi trực tiếp goal; không mặc định chạy Surefire trước |
| mvn -DskipTests package | Bỏ qua thực thi test |
| mvn -Dmaven.test.skip=true package | Bỏ biên dịch và chạy test |

Trong pipeline phát hành, ưu tiên lifecycle command đã cấu hình như mvn clean verify. Chỉ chạy goal trực tiếp trong vòng chỉnh sửa nội dung cục bộ khi snippet đã được tạo và xác nhận thuộc đúng source hiện tại.

### 6.1. Profile có thể làm đứt chuỗi dependency

Nếu documentation tests hoặc plugin Asciidoctor nằm trong Maven profile, CI phải bật đúng profile. Ví dụ:

```bash
mvn clean verify -Papi-docs
```

Kiểm tra cả hai phía: profile có bật test tạo snippet không, và có bật plugin render không? Nếu chỉ một phía hoạt động, task chain bị đứt. Build bình thường không bật profile có thể không tạo HTML hoặc không tạo snippet mới.

### 6.2. Skip test không tương thích với mục tiêu tạo tài liệu

Các tham số skip có thể khiến build tiếp tục mà không thực thi documentation tests. Nếu job có trách nhiệm tạo tài liệu kiểm chứng, không được dùng skip test như cấu hình mặc định. Nếu cần build artifact nhanh không kèm tài liệu, tách profile/job rõ ràng và không coi output đó là tài liệu đã được xác minh trong lần build hiện tại.

## 7. Ngăn output cũ che giấu lỗi

Snippet nằm trong target là generated output. Khi test bị skip hoặc identifier đổi tên, các file từ lần chạy trước có thể vẫn tồn tại. Asciidoctor tìm thấy file và render thành công dù test không tạo ra nó trong build hiện tại.

Cách phòng tránh:

1. Chạy mvn clean verify trong CI để xóa target và tạo lại từ đầu.
2. Không quản lý snippet generated như source trong thư mục src.
3. Bảo đảm task render chạy sau suite tạo snippet.
4. Kiểm tra Surefire/Failsafe report, không chỉ exit code.
5. Kiểm tra các identifier/file bắt buộc trước khi render nếu pipeline có bước verify riêng.
6. Không dùng profile skip test trong job tạo tài liệu.

Maven Clean Plugin có thể dọn thư mục generated riêng nếu dự án cần giữ một số output khác. Tuy vậy, thông thường mvn clean đã xóa toàn bộ target. Không đặt file nguồn AsciiDoc duy nhất trong target vì nó sẽ bị xóa.

## 8. Nhiều suite và multi-module Maven

### 8.1. Nhiều test suite tạo snippet

Nếu MVC tests và integration tests cùng tạo snippet, hãy phân biệt output directory hoặc identifier. Không để hai suite ghi nội dung khác nhau vào cùng thư mục operation.

```text
target/
├── generated-snippets-mvc/
│   ├── products-get-success/
│   └── orders-get-success/
├── generated-snippets-integration/
│   ├── products-get-database/
│   └── orders-get-authorization/
└── generated-docs/
```

Mỗi suite cần cấu hình output directory riêng; Asciidoctor phải chạy sau tất cả suite có snippet được trang tài liệu tham chiếu. Có thể khai báo attributes riêng tương ứng trong tài liệu nguồn. Đây là chiến lược tổ chức của dự án, không phải hành vi tự động của Spring REST Docs.

### 8.2. Multi-module

Trong multi-module Maven, module API có thể tạo snippet còn module docs biên soạn AsciiDoc. Hai module có thư mục target riêng, nên module docs không tự đọc được snippet module API bằng một đường dẫn relative chung.

Các lựa chọn thường gặp:

- Đóng gói snippet vào một artifact trung gian và để module docs phụ thuộc artifact đó.
- Copy output snippet giữa module bằng một bước build rõ ràng.
- Dùng output directory chia sẻ được cấu hình tường minh và kiểm soát build song song.

Ví dụ:

```text
parent
├── api-service
│   └── documentation tests → snippets
└── api-docs
    └── asciidoctor-maven-plugin → HTML
```

Giữ chiều phụ thuộc một hướng: module API tạo output; module docs sử dụng output đã tạo. Tránh vòng dependency trong đó API lại cần tài liệu để build.

## 9. Kiểm tra thứ tự thực thi

Khi nghi ngờ Asciidoctor chạy trước test, dùng lệnh:

```bash
mvn clean verify
```

Tìm log Surefire/Failsafe và log asciidoctor-maven-plugin:process-asciidoc. Xác nhận test suite tạo snippet đã hoàn tất trước khi plugin render.

Dùng effective POM để xem cấu hình sau khi Maven merge parent POM và profile:

```bash
mvn help:effective-pom
```

Kiểm tra execution, phase, profile, skip flags, plugin order và output directory. Khi cần chi tiết, có thể chạy mvn -X clean verify; log debug dài và có thể chứa đường dẫn/thông tin môi trường nên cần rà soát trước khi chia sẻ.

## 10. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| Include thiếu file | Render trước test hoặc descriptor không sinh file | Kiểm tra phase, test và descriptor |
| Trang có ví dụ cũ | Snippet từ build trước tồn tại | Clean output, chạy lại test |
| mvn test có snippet nhưng không có HTML | Asciidoctor được bind ở phase sau test | Chạy package/verify hoặc phase render |
| Không có snippet integration | Failsafe chưa chạy hoặc render trước integration-test | Kiểm tra Failsafe execution và chuyển render muộn hơn |
| Goal trực tiếp lỗi sau clean | Goal không chạy test trước | Dùng lifecycle command |
| CI thiếu một số trang | Profile/suite không chạy | Kiểm tra profile và test report |
| Test pass nhưng response fields thiếu | Descriptor chưa khai báo mọi field cần thiết hoặc test dùng relaxed mode | Đối chiếu hợp đồng và descriptor |
| Multi-module không tìm thấy file | Nhầm target của module khác | Copy/publish output rõ ràng |
| Test bị skip nhưng build vẫn xanh | Skip flags hoặc cấu hình Surefire | Không skip test trong job tài liệu |
| Hai suite ghi đè snippet | Identifier trùng trong output chung | Tách identifier hoặc output directory |

### 10.1. Quy trình điều tra thiếu include

1. Xem report để xác nhận test tài liệu hóa có chạy.
2. Kiểm tra target/generated-snippets/<operation-id>/.
3. Xác nhận file được include có được descriptor tương ứng tạo ra không.
4. Đối chiếu attribute snippets với output directory của test.
5. Xem log xác nhận render chạy sau test.
6. Chạy mvn clean verify để loại trừ output cũ.
7. Nếu chỉ lỗi ở CI, kiểm tra profile, JDK, reactor module và skip flags.

## 11. Best practices

- Bind render sau đúng test suite tạo snippet.
- Surefire ở phase test có thể dùng với Asciidoctor ở prepare-package.
- Nếu snippet đến từ Failsafe integration tests, đặt render sau suite tích hợp.
- Dùng lifecycle command trong CI thay vì gọi riêng goal render.
- Không dùng skip test trong job có trách nhiệm tạo tài liệu.
- Kiểm tra số lượng test và report để biết test có thực sự được phát hiện.
- Clean generated output để tránh snippet stale.
- Giữ source AsciiDoc ngoài target.
- Kiểm tra effective POM và log khi thứ tự execution không rõ.
- Tách output directory nếu nhiều suite có vòng đời và nội dung độc lập.

## 12. Bài thực hành

Tạo Maven project dùng MockMvc để sinh snippet cho GET /api/products/{id}. Trang AsciiDoc include http-request.adoc, http-response.adoc và response-fields.adoc.

**Nhiệm vụ:**

1. Thêm spring-restdocs-mockmvc scope test.
2. Cấu hình RestDocumentationExtension và document("products-get-success", ...).
3. Đặt snippet output trong target/generated-snippets.
4. Bind asciidoctor-maven-plugin vào prepare-package.
5. Chạy mvn clean verify và đối chiếu Surefire → snippets → Asciidoctor.
6. Xác nhận HTML tạo tại target/generated-docs.
7. Chạy mvn clean rồi gọi trực tiếp mvn asciidoctor:process-asciidoc; quan sát việc thiếu snippet khi test chưa chạy.
8. Chạy lại mvn clean verify và xác nhận trang render đủ.
9. Thử -DskipTests và giải thích vì sao build không còn bảo đảm snippet mới.
10. Chuyển test sang Failsafe integration test, chọn phase render thích hợp và xác minh thứ tự trong log.

**Tiêu chí hoàn thành:** build sạch chạy test tạo snippet trước render; đường dẫn include đúng; task không dùng output cũ; khi skip hoặc chuyển suite test, vấn đề dependency được phát hiện và xử lý có chủ đích.

## 13. Ghi nhớ

- Spring REST Docs chỉ tạo snippet khi test được thực thi và gọi phần ghi nhận operation.
- Surefire test ở phase test có thể tạo snippet trước Asciidoctor ở prepare-package.
- Nếu snippet đến từ Failsafe integration tests, phải đặt render sau suite đó; prepare-package thường quá sớm.
- Gọi trực tiếp asciidoctor:process-asciidoc không tự chạy các phase test trước đó.
- mvn clean verify, report test, effective POM và log execution giúp xác nhận build order.
- Dependency đúng nghĩa bảo đảm đúng suite tạo đủ snippet trước render, tránh output cũ và giữ CI có thể tái tạo.
