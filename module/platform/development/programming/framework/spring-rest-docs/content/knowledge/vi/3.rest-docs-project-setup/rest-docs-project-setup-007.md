# Cấu hình asciidoctor-maven-plugin cho Maven

Với dự án dùng Maven, **asciidoctor-maven-plugin** đảm nhiệm bước biên soạn file AsciiDoc thành tài liệu đầu ra như HTML. Trong quy trình Spring REST Docs, plugin này cần đọc đúng thư mục snippet đã được tạo từ các bài kiểm thử HTTP. Vì vậy cấu hình quan trọng nhất là xác định rõ **test tạo snippet ở đâu**, **Asciidoctor đọc snippet từ đâu**, **file AsciiDoc nguồn nằm ở đâu** và **kết quả render được ghi vào đâu**.

Bài học thuộc chương **Thiết lập dự án** của module `SPRING_REST_DOCS`. Module thực hành tạo tài liệu REST API có thể kiểm chứng bằng Spring REST Docs từ test với MockMvc, WebTestClient hoặc REST Assured, sinh snippet cho request, response, payload, tham số và header, sau đó biên soạn Asciidoctor/Markdown và đưa vào build, CI. Bài này tập trung cấu hình Maven để nối đúng các bước đó, hiểu lifecycle, khai báo plugin dependency và xử lý các lỗi thường gặp.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vai trò của `asciidoctor-maven-plugin` trong pipeline Spring REST Docs.
2. Khai báo plugin và execution trong `pom.xml`.
3. Cấu hình thư mục nguồn AsciiDoc, thư mục output và attribute `snippets`.
4. Bảo đảm test tạo snippet chạy trước khi plugin biên soạn tài liệu.
5. Phân biệt dependency của ứng dụng/test với dependency của chính Maven plugin.
6. Chạy Maven để tạo HTML và chẩn đoán lỗi thiếu snippet, sai đường dẫn hoặc build order.
7. Tích hợp bước biên soạn tài liệu vào CI và kiểm soát output cũ.

## 2. Vai trò của asciidoctor-maven-plugin

Spring REST Docs và Asciidoctor giải quyết hai công việc khác nhau:

- **Spring REST Docs** được gọi từ test HTTP; nó ghi nhận request/response, kiểm tra descriptor và tạo các snippet.
- **Asciidoctor** đọc file nguồn `.adoc`, chèn các snippet qua directive `include::` rồi render tài liệu đầu ra.
- **asciidoctor-maven-plugin** kết nối Asciidoctor vào Maven lifecycle, quản lý source directory, output directory, backend và attributes.

Luồng dữ liệu:

```text
src/test/java/
  └── HTTP documentation tests
           │
           ▼
      mvn test
           │
           ▼
target/generated-snippets/
  ├── products-get-success/
  │     ├── http-request.adoc
  │     └── response-fields.adoc
  └── products-get-not-found/
        └── http-response.adoc
           │
           │  attribute: snippets
           ▼
src/docs/asciidoc/
  ├── index.adoc
  ├── products.adoc
  └── orders.adoc
           │
           ▼
asciidoctor-maven-plugin
           │
           ▼
target/generated-docs/
  └── index.html
```

Plugin **không tự chạy các test tạo snippet** nếu không có quan hệ lifecycle phù hợp. Việc chạy test và việc render tài liệu phải được nối trong cùng lệnh Maven hoặc CI job có thứ tự rõ ràng.

## 3. Cấu trúc thư mục đề xuất

Một cấu trúc đơn giản trong Maven project:

```text
my-api/
├── pom.xml
├── src/
│   ├── main/
│   │   └── java/
│   ├── test/
│   │   └── java/
│   │       └── ...DocumentationTest.java
│   └── docs/
│       └── asciidoc/
│           ├── index.adoc
│           ├── introduction.adoc
│           ├── products.adoc
│           └── orders.adoc
└── target/
    ├── generated-snippets/
    │   ├── products-get-success/
    │   └── orders-get-success/
    └── generated-docs/
        └── index.html
```

| Đường dẫn | Nội dung | Chủ thể tạo/quản lý |
| --- | --- | --- |
| `src/test/java` | Kiểm thử HTTP có gọi `document(...)` | Nhóm phát triển |
| `src/docs/asciidoc` | Tài liệu nguồn `.adoc` và lời giải thích | Nhóm phát triển/tác giả tài liệu |
| `target/generated-snippets` | Snippet sinh từ test | Spring REST Docs |
| `target/generated-docs` | Tài liệu đã render | Asciidoctor Maven plugin |

Thư mục `target` là output build của Maven, có thể tái tạo. Không đặt file nguồn `.adoc` duy nhất trong `target`, vì lệnh `mvn clean` sẽ xóa thư mục này.

## 4. Chuẩn bị dependency của Spring REST Docs

Ví dụ dưới đây dùng test với MockMvc. Trong `pom.xml`, dependency của Spring REST Docs MockMvc được khai báo trong project dependency với scope `test`:

```xml
<properties>
    <java.version>17</java.version>
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
```

Đây là ví dụ pin phiên bản để minh họa một cấu hình Maven; phiên bản Spring REST Docs cần tương thích với Spring Framework/Spring Boot của dự án. Nếu dự án đã quản lý phiên bản qua BOM hoặc parent POM, hãy dùng cơ chế dependency management hiện có và tránh khai báo phiên bản mâu thuẫn.

Tùy test client, dependency có thể khác:

| Test client | Dependency Spring REST Docs thường dùng |
| --- | --- |
| MockMvc | `spring-restdocs-mockmvc` |
| WebTestClient | `spring-restdocs-webtestclient` |
| REST Assured | `spring-restdocs-restassured` |

Chỉ thêm dependency cho client thực sự sử dụng. Các dependency này phục vụ test; chúng không thay thế plugin biên soạn AsciiDoc.

## 5. Cấu hình output directory cho snippet

Trước khi khai báo Asciidoctor, cần biết Spring REST Docs đang ghi snippet vào đâu. Với Maven, quy ước thường dùng là:

```text
${project.build.directory}/generated-snippets
```

Maven property `project.build.directory` thường trỏ tới `target`. Vì vậy đường dẫn thực tế thường là `target/generated-snippets`.

### 5.1. Cấu hình qua JUnit 5 và MockMvc

Spring REST Docs cung cấp extension để gắn context tạo snippet với test. Ví dụ:

```java
@ExtendWith(RestDocumentationExtension.class)
class ProductDocumentationTest {

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(
            WebApplicationContext context,
            RestDocumentationContextProvider restDocumentation) {

        mockMvc = MockMvcBuilders.webAppContextSetup(context)
            .apply(documentationConfiguration(restDocumentation))
            .build();
    }

    @Test
    void getProduct() throws Exception {
        mockMvc.perform(
                get("/api/products/{id}", 7L)
                    .accept(MediaType.APPLICATION_JSON)
            )
            .andExpect(status().isOk())
            .andDo(document("products-get-success"));
    }
}
```

Ví dụ rút gọn phần import và assertion payload để tập trung vào chỗ cấu hình. Trong dự án thực tế, test cần dùng đúng request builder, fixture và descriptor cho hợp đồng. Với MockMvc path parameters, dùng `RestDocumentationRequestBuilders.get(...)` để giữ URI template khi mô tả biến đường dẫn.

Một cách khác là cấu hình rõ output directory thông qua API `JUnitRestDocumentation` hoặc cấu hình test phù hợp với phiên bản và test framework đang dùng. Điều cần bảo đảm là thư mục test ghi ra **trùng chính xác** với attribute `snippets` mà plugin Asciidoctor sử dụng.

### 5.2. Xác nhận đường dẫn trước khi cấu hình plugin

Sau khi chạy test, kiểm tra output:

```text
target/generated-snippets/products-get-success/
    http-request.adoc
    http-response.adoc
    path-parameters.adoc
    response-fields.adoc
```

Tên và số lượng file phụ thuộc vào descriptor đã khai báo. Ví dụ GET không có request body sẽ không cần request-fields snippet; nếu test không gọi `responseFields(...)`, không giả định có file `response-fields.adoc`.

## 6. Khai báo asciidoctor-maven-plugin trong pom.xml

Một cấu hình cơ bản có thể đặt trong phần `build/plugins`:

```xml
<build>
    <plugins>
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
                    <id>generate-api-docs</id>
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
                    <toc>left</toc>
                    <toclevels>3</toclevels>
                    <sectnums>true</sectnums>
                </attributes>
            </configuration>
        </plugin>
    </plugins>
</build>
```

Các cấu hình chính:

| Thành phần | Chức năng |
| --- | --- |
| `groupId`, `artifactId` | Xác định Maven plugin |
| `version` | Pin phiên bản plugin |
| Plugin dependency `spring-restdocs-asciidoctor` | Cung cấp thành phần tích hợp/extension của Spring REST Docs cho Asciidoctor |
| `execution` | Đặt tên một lần chạy plugin |
| `phase` | Nối bước render vào Maven lifecycle |
| `goal` | Chạy mục tiêu `process-asciidoc` |
| `sourceDirectory` | Thư mục nguồn AsciiDoc |
| `outputDirectory` | Nơi ghi HTML |
| `backend` | Định dạng đầu ra, ở đây là HTML |
| `attributes.snippets` | Đường dẫn mà directive include dùng để tìm snippet |

`spring-restdocs-asciidoctor` ở đây là **dependency của Maven plugin**, được khai báo bên trong `<plugin>`. Nó không giống dependency `spring-restdocs-mockmvc` trong `<project><dependencies>`, vốn được test compile/runtime sử dụng. Nếu thiếu plugin dependency, các macro hoặc extension Asciidoctor dành cho Spring REST Docs có thể không được nạp đúng theo cách tài liệu dự án mong muốn.

### 6.1. Vì sao chọn phase prepare-package?

Trong Maven lifecycle thông dụng, phase `test` diễn ra trước `prepare-package`. Vì vậy, khi chạy `mvn package` hoặc `mvn verify`, các test đã được chạy trước bước biên soạn tài liệu gắn ở `prepare-package`.

Luồng đơn giản:

```text
validate
   │
compile
   │
test-compile
   │
test  ───────────────► Spring REST Docs tạo snippets
   │
prepare-package ─────► asciidoctor-maven-plugin render
   │
package
   │
verify
```

Nếu gắn plugin vào một phase chạy quá sớm, snippet chưa tồn tại khi Asciidoctor xử lý include. Chọn phase muộn hơn test giúp giữ đúng thứ tự trong cùng lifecycle. Dự án có integration-test riêng cần kiểm tra phase/task thực tế của suite đó và đặt render sau bước tạo snippet tương ứng.

### 6.2. Chạy riêng goal và chạy qua lifecycle

Có thể gọi trực tiếp plugin:

```bash
mvn asciidoctor:process-asciidoc
```

Lệnh này chạy goal Asciidoctor, nhưng không tự bảo đảm các test tạo snippet vừa được chạy trong cùng invocation. Nếu output snippets chưa tồn tại hoặc còn từ lần chạy trước, kết quả render có thể lỗi hoặc dùng dữ liệu cũ.

Trong quy trình đầy đủ, ưu tiên:

```bash
mvn clean verify
```

Lệnh này làm sạch output Maven, chạy các phase từ đầu đến `verify`, bao gồm test và bước biên soạn tài liệu đã nối ở `prepare-package`.

## 7. Viết AsciiDoc dùng attribute snippets

Tạo file `src/docs/asciidoc/index.adoc`:

```asciidoc
= Product API
:toc: left
:toclevels: 3

== Giới thiệu

Tài liệu mô tả API sản phẩm.

=== Lấy thông tin sản phẩm

Sử dụng endpoint để đọc sản phẩm theo mã.

==== Request

include::{snippets}/products-get-success/http-request.adoc[]

==== Path parameters

include::{snippets}/products-get-success/path-parameters.adoc[]

==== Response

include::{snippets}/products-get-success/http-response.adoc[]

==== Response fields

include::{snippets}/products-get-success/response-fields.adoc[]
```

Attribute `snippets` được lấy từ cấu hình plugin và trỏ tới `target/generated-snippets`. Đường dẫn include cuối cùng tương ứng:

```text
target/generated-snippets/
    products-get-success/
        http-request.adoc
```

Một số lỗi phổ biến:

- Tên `products-get-success` không khớp identifier trong `document(...)`.
- Test không tạo `path-parameters.adoc` vì thiếu descriptor hoặc request builder không giữ URI template.
- Test không tạo `response-fields.adoc` vì không gọi `responseFields(...)`.
- Attribute `snippets` trỏ nhầm sang thư mục output của module/test suite khác.
- File nguồn AsciiDoc nằm ngoài `sourceDirectory` đã cấu hình.

Đừng thêm include của một file chỉ vì nghĩ rằng mọi operation đều tạo đủ các snippet. Chỉ include file mà test thực sự sinh ra.

## 8. Đưa tài liệu HTML vào build artifact

Với cấu hình trên, output dự kiến tại:

```text
target/generated-docs/index.html
```

Có thể đóng gói tài liệu cùng artifact ứng dụng, copy vào nơi phục vụ static site hoặc publish bằng một job riêng. Cách phát hành phụ thuộc hệ thống triển khai; plugin chỉ tạo tài liệu theo cấu hình, không tự xuất bản lên website.

Nếu cần nhiều file AsciiDoc, plugin có thể xử lý các nguồn trong `sourceDirectory` theo cấu hình. Nên chọn file entry point và cách tổ chức include rõ ràng để tránh tạo nhiều trang trùng nội dung hoặc output ngoài ý muốn.

### 8.1. Đặt output vào artifact

Một lựa chọn là để tài liệu được tạo trong `target/generated-docs` và lưu lại như build artifact trong CI. Nếu muốn đóng gói vào JAR/WAR, cần thêm bước tài nguyên/cấu hình Maven tương ứng để đưa thư mục output vào artifact. Không nên giả định `asciidoctor-maven-plugin` tự động đưa HTML vào JAR chỉ vì nó render thành công.

### 8.2. Tách build tài liệu khỏi build ứng dụng

Một số dự án muốn developer chạy test nhanh mà không render docs mỗi lần. Có thể đặt execution trong Maven profile, ví dụ `api-docs`, để chỉ bật khi cần:

```xml
<profiles>
    <profile>
        <id>api-docs</id>
        <build>
            <plugins>
                <!-- Đưa cấu hình asciidoctor-maven-plugin vào đây -->
            </plugins>
        </build>
    </profile>
</profiles>
```

Khi đó, lệnh CI phải kích hoạt profile:

```bash
mvn clean verify -Papi-docs
```

Nếu plugin nằm trong profile, `mvn verify` không bật profile sẽ không tạo HTML. Hãy để chính sách build rõ ràng: tài liệu là điều kiện bắt buộc của pipeline phát hành hay là artifact tùy chọn.

## 9. Tích hợp Maven với CI

Một job CI điển hình:

```text
Checkout commit
     │
     ▼
mvn clean verify
     │
     ├── Compile failure ─────────► Fail
     ├── Documentation test fail ─► Fail
     ├── Descriptor mismatch ─────► Fail
     ├── Asciidoctor include fail ─► Fail
     │
     ▼
target/generated-snippets/
     │
     ▼
target/generated-docs/
     │
     ▼
Lưu artifact / publish theo pipeline
```

CI nên chạy từ workspace sạch để tránh snippet còn lại của build trước. Nếu sử dụng profile, phải kích hoạt nhất quán trong job. Nếu có nhiều module Maven, cần quyết định module nào tạo snippet, module nào biên soạn và cách truyền output giữa các module.

### 9.1. Lưu artifact thay vì commit output build

Thông thường, không commit `target/generated-snippets` hoặc `target/generated-docs` như source. Chúng là output có thể tái tạo. Có thể lưu HTML làm artifact của pipeline, hoặc publish từ job tài liệu sau khi test và render thành công.

Source cần quản lý trong version control gồm:

- `pom.xml` và cấu hình plugin.
- Test tài liệu hóa.
- File `.adoc` và các phần giải thích viết tay.
- Các template hoặc script cần thiết cho quy trình biên soạn.

## 10. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra/khắc phục |
| --- | --- | --- |
| Include báo không tìm thấy file | Attribute `snippets` hoặc identifier sai | So sánh cấu hình plugin với output và `document(...)` |
| Không có `generated-snippets` | Test không chạy hoặc chưa cấu hình Spring REST Docs | Kiểm tra test discovery, extension/filter và log |
| Asciidoctor chạy trước test | Execution gắn sai phase hoặc gọi goal riêng | Gắn goal vào phase sau `test`, chạy lifecycle như `mvn verify` |
| Có response snippet nhưng thiếu bảng field | Chưa khai báo `responseFields(...)` | Bổ sung descriptor nếu field thuộc hợp đồng |
| Không có path-parameters snippet | Dùng request builder không giữ URI template | Dùng `RestDocumentationRequestBuilders` phù hợp |
| Plugin không nhận attribute snippets | Cấu hình XML sai vị trí hoặc tên attribute | Đặt trong `<configuration><attributes>` và kiểm tra effective POM |
| Extension Spring REST Docs không hoạt động | Thiếu plugin dependency hoặc sai dependency scope | Kiểm tra `spring-restdocs-asciidoctor` ở plugin và test dependency riêng |
| `mvn asciidoctor:process-asciidoc` render file cũ | Goal chạy mà không chạy test trước, output còn tồn dư | Chạy `mvn clean verify` |
| HTML không xuất hiện ở nơi mong đợi | `outputDirectory` hoặc source entry point khác | Kiểm tra `target/generated-docs` và log plugin |
| HTML không nằm trong JAR/WAR | Chưa thêm bước đóng gói resource | Cấu hình tài nguyên Maven hoặc artifact/publish task |
| Chạy local được nhưng CI lỗi | Khác profile, JDK, đường dẫn hoặc working directory | Dùng cùng lệnh Maven và cấu hình CI có thể tái tạo |

### 10.1. Kiểm tra effective POM

Khi nghi ngờ cấu hình bị parent POM hoặc profile ghi đè, dùng:

```bash
mvn help:effective-pom
```

Kiểm tra cấu hình plugin sau khi Maven hợp nhất các POM. Lệnh này hữu ích để xem phiên bản, execution, phase, source/output directory và attributes cuối cùng.

Có thể xem log chi tiết:

```bash
mvn -X clean verify
```

Chỉ dùng log debug khi cần điều tra vì output dài và có thể chứa đường dẫn/một số thông tin môi trường. Trước khi chia sẻ log ra ngoài, rà soát dữ liệu nhạy cảm.

## 11. Best practices

1. **Dùng property cho phiên bản và đường dẫn:** dễ đồng bộ cấu hình và giảm lặp.
2. **Giữ source ngoài `target`:** `mvn clean` không được xóa nội dung tài liệu do tác giả quản lý.
3. **Nối test trước render:** tránh tài liệu được biên soạn từ snippet cũ.
4. **Tách project dependency và plugin dependency:** dễ hiểu phạm vi sử dụng.
5. **Định nghĩa attribute ở một nơi:** các trang chỉ tham chiếu `snippets` thay vì hard-code đường dẫn.
6. **Chạy `mvn clean verify` trên CI:** kiểm tra toàn bộ lifecycle từ đầu.
7. **Chọn profile có chủ đích:** biết rõ job nào phải tạo docs và job nào có thể bỏ qua.
8. **Kiểm tra output cuối:** include, link, dữ liệu nhạy cảm, tiêu đề và các ví dụ lỗi/thành công.
9. **Không commit generated output như source:** quản lý test và file `.adoc`; tạo HTML trong pipeline.
10. **Pin và cập nhật phiên bản có kiểm soát:** bảo đảm plugin, extension và Spring REST Docs tương thích với toolchain dự án.

## 12. Bài thực hành

Tạo một Maven project có endpoint `GET /api/products/{id}` và test tài liệu hóa bằng MockMvc.

**Yêu cầu:**

1. Thêm dependency `spring-restdocs-mockmvc` với scope `test`.
2. Cấu hình `RestDocumentationExtension` và MockMvc để snippet được tạo trong `target/generated-snippets`.
3. Viết test có assertion status, ID và một field nghiệp vụ; gọi `document("products-get-success", ...)`.
4. Khai báo ít nhất `pathParameters(...)` và `responseFields(...)`.
5. Tạo `src/docs/asciidoc/index.adoc` và include `http-request.adoc`, `path-parameters.adoc`, `http-response.adoc` và `response-fields.adoc`.
6. Cấu hình `asciidoctor-maven-plugin` với phase `prepare-package`, source directory và output directory.
7. Chạy `mvn clean verify`.
8. Xác nhận snippet và HTML được sinh đúng nơi.
9. Thử đổi identifier trong test mà không đổi include; quan sát lỗi, sau đó cập nhật đường dẫn và chạy lại.
10. Thử chạy goal Asciidoctor riêng sau khi clean để nhận biết vì sao thiếu snippet nếu chưa chạy test.

**Tiêu chí hoàn thành:** Maven chạy test trước khi render, output snippet đúng directory, các include được giải quyết, HTML được tạo trong `target/generated-docs` và build thất bại khi test hoặc bước biên soạn gặp lỗi cần xử lý.

## 13. Ghi nhớ

- `spring-restdocs-mockmvc` là dependency test của project; `spring-restdocs-asciidoctor` có thể được khai báo như dependency của plugin để hỗ trợ tích hợp Asciidoctor.
- `asciidoctor-maven-plugin` quản lý source directory, output directory, backend, attributes và execution trong Maven lifecycle.
- Attribute `snippets` phải trỏ đúng nơi Spring REST Docs tạo snippet, thường là `target/generated-snippets` trong ví dụ Maven.
- Gắn `process-asciidoc` vào phase sau test, chẳng hạn `prepare-package`, giúp snippet được tạo trước khi include.
- `mvn clean verify` là cách kiểm tra pipeline đầy đủ từ output sạch; gọi riêng goal Asciidoctor không tự chạy test.
- Source `.adoc` được quản lý trong `src/docs/asciidoc`; snippet và HTML là generated output. Việc đóng gói hoặc publish HTML cần cấu hình bổ sung theo dự án.
