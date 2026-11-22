# Đường dẫn tương đối tới generated snippets

## 1. Mục tiêu và bối cảnh

Spring REST Docs sinh snippet từ HTTP tests vào thư mục output, thường là `build/generated-snippets` với Gradle hoặc `target/generated-snippets` với Maven. Trang Asciidoctor include snippet bằng directive:

~~~asciidoc
include::{snippets}/orders-get/http-request.adoc[]
~~~

Attribute `snippets` phải trỏ đúng thư mục chứa generated snippets. Nếu không khai báo attribute, trỏ nhầm module hoặc task render chạy trước task test, Asciidoctor sẽ không tìm thấy file.

Bài học thuộc chương **Markdown** của module **SPRING_REST_DOCS**: tạo tài liệu REST API có thể kiểm chứng từ HTTP tests bằng MockMvc, WebTestClient hoặc REST Assured; sinh snippet cho request, response, payload, tham số và header; biên soạn Asciidoctor/Markdown rồi tích hợp build/CI.

Sau bài học, bạn có thể phân biệt source document, generated snippets và rendered output; cấu hình đường dẫn tương đối với Asciidoctor; truyền snippet root qua Gradle/Maven; tổ chức include trong multi-module; chẩn đoán lỗi include.

> Đường dẫn trong include là đường dẫn file được build tool/Asciidoctor giải quyết. Nó không phải endpoint URL mà client API gọi.

## 2. Ba vị trí đường dẫn cần phân biệt

| Vị trí | Ví dụ | Vai trò |
| --- | --- | --- |
| Source documentation | `src/docs/asciidoc/index.adoc` | File Asciidoc chứa giải thích và include directives. |
| Generated snippets | `build/generated-snippets/orders-get/http-request.adoc` | File REST Docs sinh sau khi test ghi operation. |
| Rendered documentation | `build/docs/asciidoc/html5/index.html` | File HTML do Asciidoctor tạo. |

~~~mermaid
flowchart LR
    A["HTTP tests"] --> B["build/generated-snippets"]
    C["src/docs/asciidoc/index.adoc"] --> D["Asciidoctor include"]
    B --> D
    D --> E["build/docs/.../index.html"]
~~~

Tests tạo snippets ở B; file Asciidoc nguồn ở C; Asciidoctor đọc cả source lẫn snippet rồi tạo HTML ở E. Output HTML không phải nguồn include.

### 2.1. Relative path được tính từ đâu?

- Đường dẫn source trong Gradle thường được tính từ project directory.
- Attribute `snippets` thường chứa filesystem path tới thư mục generated snippets.
- Include path được Asciidoctor giải quyết theo document base directory/include path và cấu hình build.
- Output HTML directory chỉ là nơi ghi kết quả render.

Không giả định mọi relative path đều tính từ terminal working directory. Khi chạy Gradle từ root, subproject hoặc CI, working directory có thể khác. Ưu tiên tạo path từ Gradle project layout rồi truyền rõ cho Asciidoctor.

## 3. Include snippet bằng Asciidoctor attribute

Trang Asciidoc:

~~~asciidoc
= Orders API

== Lấy đơn hàng

=== HTTP request
include::{snippets}/orders-get/http-request.adoc[]

=== HTTP response
include::{snippets}/orders-get/http-response.adoc[]

=== Response fields
include::{snippets}/orders-get/response-fields.adoc[]
~~~

`{snippets}` là document attribute. Asciidoctor thay attribute bằng giá trị được cấu hình rồi tìm file tương ứng.

Ví dụ output:

~~~text
build/
└── generated-snippets/
    └── orders-get/
        ├── http-request.adoc
        ├── http-response.adoc
        └── response-fields.adoc
~~~

Nếu attribute trỏ tới `build/generated-snippets`, file include được tạo từ snippet root, identifier `orders-get` và filename `http-request.adoc`. Identifier đến từ `document("orders-get")`. Tên snippet và extension phải khớp chính xác.

### 3.1. Đặt attribute trong source document

Với tài liệu nhỏ, có thể khai báo ở đầu file:

~~~asciidoc
= Orders API
:snippets: ../../build/generated-snippets

== Lấy đơn hàng

include::{snippets}/orders-get/http-request.adoc[]
~~~

Giá trị relative path được giải quyết theo ngữ cảnh document/include của Asciidoctor và cấu trúc project. Di chuyển source file sang folder khác có thể làm path sai. Với build nhiều môi trường/module, nên truyền attribute từ Gradle/Maven để source không phụ thuộc cấu trúc build.

### 3.2. Attribute chưa được khai báo

Nếu source dùng `{snippets}` nhưng build không truyền attribute, include có thể không resolve. Kiểm tra tên attribute, directory tồn tại, identifier, filename và task dependency. Không khắc phục bằng cách copy snippet thủ công vào source docs vì sẽ tạo hai bản dữ liệu có thể lệch nhau.

## 4. Gradle: dùng chung một snippets directory

Ví dụ Groovy DSL:

~~~groovy
plugins {
    id 'java'
    id 'org.asciidoctor.jvm.convert' version '4.0.2'
}

ext {
    snippetsDir = file("$buildDir/generated-snippets")
}

dependencies {
    testImplementation 'org.springframework.restdocs:spring-restdocs-mockmvc'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

test {
    outputs.dir snippetsDir
}

asciidoctor {
    inputs.dir snippetsDir
    dependsOn test
    attributes 'snippets': snippetsDir
}
~~~

Đây là cấu hình minh họa; version plugin/dependencies cần phù hợp project. Ý chính:

1. `snippetsDir` xác định thư mục snippet trong build directory.
2. Test khai báo thư mục output.
3. Asciidoctor phụ thuộc test để snippet sinh trước.
4. `inputs.dir` khai báo task input cho Gradle.
5. `attributes` truyền path vào Asciidoctor với tên `snippets`.

REST Docs test phải ghi vào đúng directory này. Nếu test ghi directory A nhưng Asciidoctor đọc directory B, include sẽ thiếu dù cả hai task đều chạy.

### 4.1. Dùng Gradle layout API

~~~groovy
def snippetsDir = layout.buildDirectory.dir('generated-snippets')

tasks.named('test') {
    outputs.dir snippetsDir
}

tasks.named('asciidoctor') {
    inputs.dir snippetsDir
    dependsOn tasks.named('test')
    attributes 'snippets': snippetsDir.get().asFile
}
~~~

Task `asciidoctor` phải được tạo bởi plugin trước khi cấu hình. Nếu plugin được áp dụng trong convention plugin hoặc subproject khác, điều chỉnh vị trí cấu hình theo lifecycle đó.

### 4.2. Không hard-code đường dẫn máy cá nhân

Tránh path tuyệt đối như `C:/Users/dev/project/build/generated-snippets`. Nó chỉ tồn tại trên máy cụ thể. Dùng Gradle file/layout API để path được tạo từ project directory và build directory hiện tại.

### 4.3. Task dependency không phụ thuộc thứ tự khai báo

Viết block Asciidoctor sau block test không bảo đảm test chạy trước. Gradle thực thi task graph theo dependency. Dùng `dependsOn test` hoặc dependency tới đúng integration test task nếu task đó sinh snippets.

~~~groovy
asciidoctor {
    dependsOn integrationTest
    inputs.dir snippetsDir
}
~~~

Đảm bảo integration test ghi đúng directory Asciidoctor đọc. Dependency vào task test không sinh REST Docs không giải quyết lỗi include.

## 5. Maven: truyền snippets path bằng property

Maven thường dùng `target/generated-snippets`. Asciidoctor Maven Plugin nhận attribute `snippets` trỏ tới directory này.

~~~xml
<properties>
    <snippetsDirectory>target/generated-snippets</snippetsDirectory>
</properties>

<build>
    <plugins>
        <plugin>
            <groupId>org.asciidoctor</groupId>
            <artifactId>asciidoctor-maven-plugin</artifactId>
            <configuration>
                <attributes>
                    <snippets>target/generated-snippets</snippets>
                </attributes>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

Đây là minh họa cách truyền property/attribute; project còn cần execution/phase và test configurer để sinh snippets. Trong Maven multi-module, phân biệt base directory và build directory của module với root project. Không sao chép cấu hình Gradle nguyên xi sang Maven vì lifecycle, goals, phases và property handling khác nhau.

Điều cần giữ nhất quán: test ghi đúng thư mục mà Asciidoctor đọc.

## 6. Multi-module: source docs và snippets thuộc hai project

Cấu trúc ví dụ:

~~~text
spring-rest-docs/
├── build.gradle
├── settings.gradle
├── api-service/
│   ├── build.gradle
│   └── src/test/java/...
└── docs/
    ├── build.gradle
    └── src/docs/asciidoc/index.adoc
~~~

Tests nằm trong `api-service`, Asciidoctor chạy trong `docs`. Đường dẫn có thể là:

- Snippets: `api-service/build/generated-snippets`.
- Source docs: `docs/src/docs/asciidoc/index.adoc`.
- HTML output: `docs/build/docs/asciidoc/html5`.

Cấu hình ý tưởng trong docs project:

~~~groovy
def apiSnippets = project(':api-service')
    .layout.buildDirectory
    .dir('generated-snippets')

tasks.named('asciidoctor') {
    inputs.dir apiSnippets
    attributes 'snippets': apiSnippets.get().asFile
    dependsOn ':api-service:test'
}
~~~

Cấu hình thực tế phải khớp Gradle version, plugin và dependency giữa projects. Tham chiếu rõ project tạo snippets, tránh relative path dựa vào working directory ngầm định.

### 6.1. Shared output hay output riêng?

| Phương án | Ưu điểm | Rủi ro |
| --- | --- | --- |
| Mỗi module có output riêng | Rõ quyền sở hữu và lifecycle | Tài liệu tổng hợp phải đọc nhiều folder. |
| Một output directory chung | Include tập trung | Identifier dễ collision, khó tách producer. |

Nếu dùng directory chung, identifier nên có namespace như `billing-orders-get` và `identity-users-get`. Mỗi operation directory chỉ nên có một producer ghi.

## 7. Include path khác URL

Include đọc file từ filesystem lúc build:

~~~asciidoc
include::{snippets}/orders-get/http-request.adoc[]
~~~

Nó không được gửi tới browser và không phải public URL. Ngược lại, website link:

~~~markdown
[Xem authentication](authentication.html)
~~~

được browser/site renderer xử lý khi người đọc mở trang.

| Loại path | Ví dụ | Được giải quyết bởi |
| --- | --- | --- |
| Snippet include | `{snippets}/orders-get/http-request.adoc` | Asciidoctor/build. |
| Source file | `src/docs/asciidoc/index.adoc` | Gradle/Maven project layout. |
| HTML output | `build/docs/asciidoc/html5` | Asciidoctor output configuration. |
| Website link | `/api/authentication/` | Browser/web server/site generator. |

Không dùng filesystem path nội bộ làm link công khai.

## 8. Markdown và generated snippets

Spring REST Docs hỗ trợ Markdown template format, nhưng Markdown thuần không có directive include file chuẩn. Do đó `include::{snippets}/...[]` chỉ dùng trực tiếp trong Asciidoctor.

Với Markdown snippets:

~~~text
build/generated-snippets/
└── orders-get/
    ├── http-request.md
    ├── http-response.md
    └── response-fields.md
~~~

Cần static site generator hỗ trợ partials, plugin include, build task ghép file hoặc preprocessor. Snippets path phải được cấu hình trong công cụ ghép; Asciidoctor attribute `snippets` không tự áp dụng cho Markdown renderer.

## 9. Identifier, filename và extension

~~~text
<snippets-root>/<operation-identifier>/<snippet-name>.<extension>
~~~

Ví dụ:

~~~text
build/generated-snippets/orders-get/http-response.adoc
~~~

| Thành phần | Nguồn |
| --- | --- |
| `snippets-root` | Gradle/Maven và Asciidoctor attribute. |
| `orders-get` | Identifier trong `document("orders-get")`. |
| `http-response` | Tên snippet chuẩn hoặc snippet tùy chỉnh. |
| `.adoc` | Template format đang sử dụng. |

Khi chuyển sang Markdown, extension đổi thành `.md` và cách ghép snippet cũng có thể đổi. Không chỉ sửa extension nếu toolchain include còn xử lý định dạng cũ.

Tách identifier success/error để không include nhầm response:

~~~asciidoc
include::{snippets}/orders-get-success/http-response.adoc[]
include::{snippets}/orders-get-not-found/http-response.adoc[]
~~~

## 10. Chẩn đoán lỗi path

Khi Asciidoctor báo thiếu snippet, kiểm tra theo thứ tự:

1. Test có chạy và hoàn tất thành công không?
2. Identifier có đúng với lời gọi `document(...)` không?
3. REST Docs có ghi file vào output directory đó không?
4. Template format có đúng extension không?
5. Attribute `snippets` có được truyền tới Asciidoctor task không?
6. Include path ghép đúng root/identifier/filename chưa?
7. Task render có phụ thuộc task test sinh snippets không?
8. Multi-module có trỏ sang project tạo snippets không?

Thông báo lỗi minh họa:

~~~text
include file not found:
build/generated-snippets/orders-get/http-response.adoc
~~~

Thông báo cho biết Asciidoctor đang tìm file ở path đã resolve. Test có thể vẫn chạy nhưng ghi sang directory khác, dùng identifier khác hoặc sinh extension khác.

### 10.1. Kiểm tra output directory

~~~text
build/generated-snippets/orders-get/
├── http-request.adoc
├── http-response.adoc
└── response-fields.adoc
~~~

Nếu không có folder operation, kiểm tra test có gọi `document(...)` và operation đã ghi snippets chưa. Nếu thiếu một file, xem test có khai báo loại snippet đó không. Không phải operation nào cũng sinh toàn bộ snippets.

### 10.2. Case sensitivity và separator

Windows thường không phân biệt hoa/thường trong filesystem mặc định; Linux CI thường phân biệt. Identifier và filename phải khớp chính xác. Ưu tiên Gradle/Maven xử lý path separator bằng File/Directory/Provider API, tránh tự nối slash/backslash theo máy.

## 11. Ví dụ Gradle tổng hợp

~~~groovy
plugins {
    id 'java'
    id 'org.asciidoctor.jvm.convert' version '4.0.2'
}

def snippetsDir = layout.buildDirectory.dir('generated-snippets')

dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.restdocs:spring-restdocs-mockmvc'
}

tasks.named('test') {
    outputs.dir snippetsDir
}

tasks.named('asciidoctor') {
    dependsOn tasks.named('test')
    inputs.dir snippetsDir
    sourceDir file('src/docs/asciidoc')
    outputDir layout.buildDirectory.dir('docs/asciidoc').get().asFile
    attributes 'snippets': snippetsDir.get().asFile
}
~~~

REST Docs test cũng phải ghi vào đúng `snippetsDir`. Output directory cụ thể phụ thuộc cách cấu hình qua annotation, JUnit extension hay REST Docs configurer. Chọn một nơi làm nguồn path duy nhất.

Asciidoc source:

~~~asciidoc
= Orders API

== Lấy đơn hàng

=== Request
include::{snippets}/orders-get/http-request.adoc[]

=== Response
include::{snippets}/orders-get/http-response.adoc[]

=== Fields
include::{snippets}/orders-get/response-fields.adoc[]
~~~

Nếu source document cũng khai báo `snippets`, thống nhất giá trị để tránh attribute trong file nguồn khác với giá trị build.

## 12. CI và build sạch

~~~mermaid
flowchart TD
    A["Checkout source"] --> B["Clean build outputs"]
    B --> C["Run REST Docs tests"]
    C --> D{"Tests pass?"}
    D -->|No| X["Fail CI"]
    D -->|Yes| E["Verify generated-snippets"]
    E --> F["Run Asciidoctor"]
    F --> G{"Includes resolve and render pass?"}
    G -->|No| X
    G -->|Yes| H["Review artifact"]
    H --> I["Publish"]
~~~

CI cần bảo đảm:

- Test sinh snippets chạy trước Asciidoctor.
- REST Docs output directory và Asciidoctor attribute dùng cùng path.
- Không phụ thuộc generated file còn sót từ build trước.
- Include bắt buộc phải resolve.
- Build fail nếu thiếu snippet, không bỏ qua file im lặng.
- Multi-module task dependency rõ ràng.
- Website link được kiểm tra sau render, tách biệt filesystem include.

Không cần commit generated snippets nếu build tạo lại đáng tin cậy. Nếu commit snippets để review, cần quy ước cập nhật diff và tránh include output cũ.

## 13. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Include không tìm thấy file | `snippets` chưa khai báo hoặc sai directory | Xác minh attribute từ build. |
| Test có snippet nhưng Asciidoctor không thấy | Test ghi directory A, Asciidoctor đọc B | Dùng chung path definition. |
| Local pass, CI fail | Path phụ thuộc working directory hoặc file cũ | Dùng layout API và build sạch. |
| Identifier folder không tồn tại | `document(...)` dùng identifier khác | Khớp identifier test/include. |
| File .md nhưng include đòi .adoc | Template format không đồng nhất | Dùng extension/toolchain đúng. |
| Response snippet không có | Test không khai báo descriptor hoặc body không tồn tại | Xác minh snippet có được sinh không. |
| Multi-module include sai | Relative path tính từ nhầm project | Tham chiếu project tạo snippets. |
| Windows pass, Linux fail | Khác hoa/thường hoặc separator | Dùng tên chính xác và path API. |
| Asciidoctor chạy trước tests | Thiếu task dependency | dependsOn task sinh snippets. |
| HTML link hỏng dù include pass | Nhầm filesystem path với URL | Kiểm tra link sau render. |

## 14. Bài thực hành

Tạo tài liệu cho GET /api/orders/101 với identifier `orders-get` và POST /api/orders với identifier `orders-create`.

Thực hiện:

1. Cấu hình MockMvc để REST Docs sinh snippets vào `build/generated-snippets`.
2. Chạy tests và xác minh directory theo identifier.
3. Tạo `src/docs/asciidoc/index.adoc`, include request/response qua `snippets`.
4. Cấu hình Gradle truyền đúng snippets directory và để Asciidoctor phụ thuộc task test sinh snippets.
5. Di chuyển source Asciidoc vào folder con; xác minh include vẫn đúng theo attribute.
6. Chạy build từ root và subproject nếu có; bảo đảm không phụ thuộc terminal working directory.
7. Đổi thử identifier hoặc extension để quan sát lỗi include.
8. Nếu dùng Markdown, cấu hình công cụ ghép Markdown riêng và xác định base path.
9. Chạy clean build trong CI; chỉ publish khi tests, include và render thành công.

**Tiêu chí hoàn thành:** phân biệt đúng source path, snippets path và output path; truyền attribute chính xác; hiểu identifier/filename/extension; khai báo task dependency; tái tạo tài liệu từ build sạch local và CI.

## Tài liệu tham khảo

- [Spring REST Docs — Getting Started](https://docs.spring.io/spring-restdocs/tutorial/getting-started/index.html)
- [Asciidoctor — Include Directive](https://docs.asciidoctor.org/asciidoc/latest/directives/include/)
- [Asciidoctor Gradle Plugin — Using Attributes](https://docs.asciidoctor.org/gradle-plugin/latest/)
- [Gradle — Working with Files](https://docs.gradle.org/current/userguide/working_with_files.html)
- [Gradle — Declaring Dependencies between Tasks](https://docs.gradle.org/current/userguide/controlling_task_execution.html)
