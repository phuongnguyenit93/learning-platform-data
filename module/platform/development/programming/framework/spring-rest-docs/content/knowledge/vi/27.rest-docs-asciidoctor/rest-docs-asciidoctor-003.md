# Include snippet bằng đường dẫn tương đối

## 1. Vì sao cần hiểu cách phân giải đường dẫn include?

Spring REST Docs tạo các snippet `.adoc` từ HTTP tests bằng MockMvc, WebTestClient hoặc REST Assured. Asciidoctor ghép các snippet đó vào tài liệu chính bằng macro `include::`. Khi dự án có nhiều thư mục nguồn, build chạy từ các working directory khác nhau hoặc include được lồng nhiều cấp, đường dẫn tương đối rất dễ bị trỏ sai.

Ví dụ:

```asciidoc
include::{snippets}/books-get/http-request.adoc[]
```

Đoạn include chỉ chạy được nếu `{snippets}` đã được gán đúng thư mục chứa `books-get/http-request.adoc`. Nếu viết trực tiếp đường dẫn tương đối như `include::../../build/generated-snippets/...[]`, phải tính đường dẫn từ đúng tài liệu nguồn đang chứa macro đó.

Nguyên tắc quan trọng là: **đường dẫn include tương đối được phân giải theo vị trí của tài liệu hiện tại (document đang xử lý include), trong ngữ cảnh base directory của Asciidoctor; không nên mặc định nó luôn tương đối với terminal working directory**. Với tài liệu được include lồng nhau, đường dẫn của include tiếp theo phải được tính từ file hiện đang chứa macro đó. Kiểm tra vị trí file và cấu hình `base_dir`/`docdir` khi cần chẩn đoán.

## 2. Phân biệt thư mục dự án, thư mục nguồn và thư mục snippets

Một cấu trúc Gradle thường gặp:

```text
spring-rest-docs/
├── build.gradle
├── src/
│   ├── main/java/...
│   ├── test/java/...
│   └── docs/
│       └── asciidoc/
│           ├── index.adoc
│           └── operations/
│               └── books.adoc
└── build/
    ├── generated-snippets/
    │   └── books-get/
    │       ├── http-request.adoc
    │       └── http-response.adoc
    └── docs/asciidoc/html5/index.html
```

Ở đây có ba vị trí khác nhau:

| Vị trí | Ví dụ | Mục đích |
| --- | --- | --- |
| Project directory | `spring-rest-docs/` | Nơi chứa `build.gradle` và `src/`. |
| AsciiDoc source directory | `src/docs/asciidoc/` | Nơi chứa `index.adoc`, file operation và các tài liệu do nhóm viết. |
| Generated snippets directory | `build/generated-snippets/` | Nơi HTTP tests ghi snippet. |

File `index.adoc` nằm trong `src/docs/asciidoc/`. Để đi tới `build/generated-snippets/`, đường dẫn tương đối theo vị trí của `index.adoc` là:

```text
../../build/generated-snippets/
```

Vì cần đi lên hai cấp từ `src/docs/asciidoc/` đến project root, rồi đi vào `build/generated-snippets/`.

## 3. Viết include trực tiếp bằng đường dẫn tương đối

Với cấu trúc ở mục 2, file `src/docs/asciidoc/index.adoc` có thể viết:

```asciidoc
= Books API

== Lấy sách

=== HTTP request
include::../../build/generated-snippets/books-get/http-request.adoc[]

=== HTTP response
include::../../build/generated-snippets/books-get/http-response.adoc[]
```

Đường dẫn `../../build/...` được tính từ thư mục chứa `index.adoc`, không phải từ vị trí mà người dùng vô tình chạy lệnh `gradle` trong terminal. Nếu di chuyển `index.adoc` sang một thư mục khác, phải tính lại số cấp `../`.

Đây là cách trực tiếp và dễ hiểu với tài liệu nhỏ. Tuy nhiên, nếu có hàng chục operation, lặp lại đường dẫn dài sẽ làm tài liệu khó bảo trì. Attribute `{snippets}` giúp tách cấu hình đường dẫn khỏi nội dung include.

## 4. Dùng attribute `snippets` để rút gọn đường dẫn

Trong `index.adoc`, có thể khai báo:

```asciidoc
= Books API
:snippets: ../../build/generated-snippets

== Lấy sách

=== HTTP request
include::{snippets}/books-get/http-request.adoc[]

=== HTTP response
include::{snippets}/books-get/http-response.adoc[]
```

`{snippets}` là một Asciidoctor document attribute. Giá trị `../../build/generated-snippets` vẫn được phân giải theo vị trí của tài liệu nơi attribute được khai báo/được dùng trong ngữ cảnh tài liệu. Nếu dự án đã dùng `spring-restdocs-asciidoctor`, extension có thể tự cấu hình attribute này tới thư mục generated snippets theo build tool; khi đó không cần khai báo lại trừ khi muốn override.

Với convention mặc định:

| Build tool | Snippets directory thường dùng |
| --- | --- |
| Gradle | `build/generated-snippets` |
| Maven | `target/generated-snippets` |

Nếu dùng attribute do plugin cung cấp, cách include vẫn giống nhau:

```asciidoc
include::{snippets}/orders-create/http-request.adoc[]
```

Khác biệt nằm ở nơi gán giá trị `snippets`: file nguồn, cấu hình build hoặc extension Spring REST Docs.

## 5. Đường dẫn khi include file operation lồng nhau

Tài liệu lớn thường chia thành file chính và file operation:

```text
src/docs/asciidoc/
├── index.adoc
├── common/
│   └── authentication.adoc
└── operations/
    ├── books-list.adoc
    └── books-get.adoc
```

File `index.adoc` có thể include:

```asciidoc
include::common/authentication.adoc[]
include::operations/books-get.adoc[]
```

Sau đó `operations/books-get.adoc` chứa include snippet:

```asciidoc
== Lấy sách theo ID

include::../../../../build/generated-snippets/books-get/http-request.adoc[]
include::../../../../build/generated-snippets/books-get/http-response.adoc[]
```

Ở đây `books-get.adoc` nằm trong `src/docs/asciidoc/operations/`; cần đi lên bốn cấp để về project root rồi vào `build/generated-snippets`. Đường dẫn này khác đường dẫn dùng trong `index.adoc` vì hai file nằm ở hai thư mục khác nhau.

Nếu dùng attribute `snippets`, include trong file operation có thể ngắn hơn:

```asciidoc
include::{snippets}/books-get/http-request.adoc[]
include::{snippets}/books-get/http-response.adoc[]
```

Khi một file được include vào tài liệu khác, các include nằm bên trong file được include cần được kiểm tra theo vị trí của chính file đang chứa macro đó. Đừng chỉ kiểm tra đường dẫn từ `index.adoc` rồi giả định mọi include lồng nhau đều hợp lệ.

## 6. So sánh đường dẫn tương đối và đường dẫn tuyệt đối

| Cách khai báo | Ví dụ | Ưu điểm | Rủi ro |
| --- | --- | --- | --- |
| Tương đối trực tiếp | `../../build/generated-snippets/books-get/http-request.adoc` | Không cần attribute; thấy rõ vị trí tương đối. | Dễ sai khi di chuyển file hoặc thay cấu trúc folder. |
| Tương đối qua attribute | `{snippets}/books-get/http-request.adoc` với `:snippets: ../../build/generated-snippets` | Include ngắn, dễ đổi một nơi. | Cần hiểu nơi khai báo và ngữ cảnh phân giải attribute. |
| Tuyệt đối | `/workspace/project/build/generated-snippets/...` | Có thể hoạt động ổn định trên một máy cụ thể. | Không portable giữa developer, CI agent và hệ điều hành. |
| Attribute do build cung cấp | `{snippets}/books-get/http-request.adoc` | Build quyết định output directory; phù hợp CI. | Phải cấu hình plugin/extension chính xác. |

Thông thường, nên dùng attribute `snippets` do Spring REST Docs/Asciidoctor integration cung cấp hoặc gán từ build. Đường dẫn tương đối trực tiếp phù hợp khi tài liệu nhỏ và cấu trúc ổn định. Tránh commit đường dẫn tuyệt đối của máy cá nhân.

## 7. Cấu hình đường dẫn bằng Gradle thay vì hard-code trong file nguồn

Ví dụ Gradle:

```groovy
plugins {
    id 'java'
    id 'org.asciidoctor.jvm.convert' version '3.3.2'
}

configurations {
    asciidoctorExt
}

def snippetsDir = layout.buildDirectory.dir('generated-snippets')

dependencies {
    testImplementation 'org.springframework.restdocs:spring-restdocs-mockmvc'
    asciidoctorExt 'org.springframework.restdocs:spring-restdocs-asciidoctor'
}

tasks.named('test') {
    outputs.dir snippetsDir
    useJUnitPlatform()
}

tasks.named('asciidoctor') {
    dependsOn tasks.named('test')
    inputs.dir snippetsDir
    configurations 'asciidoctorExt'
    attributes 'snippets': snippetsDir.get().asFile
}
```

Với cấu hình này, file nguồn chỉ cần:

```asciidoc
include::{snippets}/books-get/http-request.adoc[]
```

Build cung cấp đường dẫn được tính từ Gradle layout thay vì buộc file `.adoc` biết project root nằm ở đâu. Cần đồng bộ output directory mà Spring REST Docs test thực sự ghi vào với `snippetsDir` này. Nếu extension Spring REST Docs tự gán attribute `snippets`, hãy kiểm tra cấu hình/version plugin và tránh đặt hai giá trị xung đột.

## 8. Cấu hình Maven và `target/generated-snippets`

Với Maven, output mặc định thường là `target/generated-snippets`. Nếu tài liệu nguồn ở `src/docs/asciidoc/index.adoc`, đường dẫn tương đối trực tiếp tới snippets là:

```asciidoc
:snippets: ../../target/generated-snippets

include::{snippets}/books-get/http-request.adoc[]
```

Khi cấu hình `spring-restdocs-asciidoctor` trong Asciidoctor Maven Plugin, extension có thể cung cấp attribute `snippets` theo convention Maven. Nếu plugin không nhận được extension hoặc dùng custom output path, gán attribute qua cấu hình plugin, ví dụ:

```xml
<attributes>
    <snippets>${project.build.directory}/generated-snippets</snippets>
</attributes>
```

Đảm bảo test chạy trước pha biên soạn tài liệu và ghi đúng `target/generated-snippets`. Với multi-module Maven, chú ý module nào tạo snippet và module nào chạy Asciidoctor; đường dẫn có thể cần trỏ sang output của module test thay vì `target` của module docs.

## 9. Các lưu ý khi dùng path trên Windows và Linux

AsciiDoc include path nên dùng dấu `/` để giữ cú pháp portable:

```asciidoc
include::{snippets}/books-get/http-request.adoc[]
```

Tránh viết backslash kiểu Windows:

```asciidoc
// Không khuyến nghị
include::..\..\build\generated-snippets\books-get\http-request.adoc[]
```

Các vấn đề cần kiểm tra:

- **Chữ hoa/chữ thường:** Linux thường phân biệt `Books-Get` và `books-get`; Windows có thể không. Identifier và tên file include phải khớp chính xác.
- **Khoảng trắng trong path:** có thể khiến macro hoặc thuộc tính bị parse ngoài dự kiến; ưu tiên tên folder không có khoảng trắng. Nếu phải dùng, làm theo cú pháp quoting/escaping mà Asciidoctor hỗ trợ và xác minh bằng build thật.
- **Ký tự Unicode:** tên file có dấu có thể hoạt động, nhưng tên snippet do identifier sinh ra nên dùng ASCII ổn định để tránh khác biệt hệ thống file.
- **Đường dẫn tuyệt đối:** không nên gắn `C:\Users\...` hoặc `/home/...` vào file nguồn.
- **Separator:** dùng `/` ngay cả khi build trên Windows.

## 10. Include an toàn và giới hạn đường dẫn

Asciidoctor có các chế độ an toàn (safe modes) kiểm soát include và truy cập file. Khi build tài liệu, chế độ `safe`/`secure` hoặc cấu hình của plugin có thể giới hạn đường dẫn include chỉ trong `base_dir` hoặc vùng được cho phép. Vì vậy, một include hợp lệ khi chạy cục bộ có thể bị từ chối trong môi trường CI nếu snippets nằm ngoài vùng cho phép.

Khi gặp lỗi liên quan safe mode:

1. Xem log Asciidoctor để biết include path bị chặn hay file thật sự không tồn tại.
2. Xác nhận `base_dir` và thư mục gốc tài liệu mà plugin sử dụng.
3. Đặt generated snippets trong vùng build được cho phép hoặc cấu hình plugin/base directory theo cách an toàn.
4. Chỉ nâng safe mode khi hiểu tác động và kiểm soát được nguồn tài liệu; không tắt giới hạn một cách tùy tiện.

Không dùng include path lấy trực tiếp từ dữ liệu bên ngoài hoặc do người dùng cung cấp. Tài liệu và snippet nên là artifact do repository/build kiểm soát.

## 11. Cách chẩn đoán một include không tìm thấy

Khi Asciidoctor báo `include file not found`, thực hiện lần lượt:

1. Mở thư mục snippets để xác nhận file có thật sau khi test chạy.
2. Kiểm tra identifier trong `document("books-get", ...)` có khớp thư mục `books-get` không.
3. Kiểm tra tên snippet, chẳng hạn `http-request.adoc`, có đúng file đã được sinh không.
4. Xác định file `.adoc` đang chứa `include::` nằm ở thư mục nào.
5. Tính đường dẫn tương đối từ đúng vị trí đó; không tính từ project root theo thói quen.
6. Kiểm tra giá trị cuối của `{snippets}` và plugin/extension đã nạp hay chưa.
7. Kiểm tra `base_dir` và safe mode nếu đường dẫn tồn tại nhưng vẫn bị từ chối.
8. Chạy build sạch để loại trừ snippet cũ hoặc output chưa được tạo.

Ví dụ so sánh:

```text
File include:
  src/docs/asciidoc/index.adoc

Snippet:
  build/generated-snippets/books-get/http-request.adoc

Relative path:
  ../../build/generated-snippets/books-get/http-request.adoc
```

Nếu file include được chuyển tới `src/docs/asciidoc/operations/books-get.adoc`, đường dẫn trực tiếp sẽ thay đổi thành `../../../../build/...`; còn nếu dùng attribute `snippets` đã cấu hình đúng, nội dung macro không cần thay đổi.

## 12. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách khắc phục |
| --- | --- | --- |
| `include file not found` | Đường dẫn tương đối tính sai hoặc file snippet chưa được sinh. | Xác định vị trí file chứa macro và kiểm tra output hiện tại. |
| Include chạy từ máy developer nhưng lỗi ở CI | Dùng absolute path hoặc working directory khác. | Dùng attribute từ build và đường dẫn portable. |
| File ở `build/generated-snippets` nhưng Asciidoctor tìm trong `src/docs/...` | Attribute không được cấu hình hoặc khai báo path sai. | Kiểm tra extension `spring-restdocs-asciidoctor` và giá trị `{snippets}`. |
| Include trong file operation bị lỗi | Dùng đường dẫn tính từ index thay vì file operation đang chứa macro. | Tính lại theo vị trí file hiện tại hoặc dùng attribute gốc. |
| Chạy trên Windows được nhưng Linux lỗi | Khác biệt chữ hoa/chữ thường hoặc separator. | Khớp chính xác filename và dùng `/`. |
| Include path bị safe mode chặn | Snippet nằm ngoài vùng base directory cho phép. | Sắp xếp output/base directory hoặc cấu hình safe mode có kiểm soát. |
| Include file rỗng hoặc cũ | Test không chạy, chạy thất bại hoặc output chưa được clean. | Chạy test thành công từ build sạch trước khi render. |
| Dùng `operation::` nhưng không hoạt động | Thiếu extension Asciidoctor của Spring REST Docs. | Thêm `spring-restdocs-asciidoctor` đúng plugin/configuration. |

## 13. Checklist thực hành

- [ ] Đã xác định file `.adoc` nào đang chứa `include::`.
- [ ] Đã xác định chính xác nơi test ghi snippet.
- [ ] Nếu dùng đường dẫn trực tiếp, đã tính tương đối từ thư mục của file đang include.
- [ ] Nếu dùng `{snippets}`, attribute đã được cấu hình đúng trong file hoặc build.
- [ ] Operation identifier và tên snippet khớp với file thực tế.
- [ ] Include lồng nhau đã được kiểm tra ở từng file nguồn.
- [ ] Dùng dấu `/`, khớp chữ hoa/chữ thường và tránh absolute path máy cá nhân.
- [ ] Đã kiểm tra `base_dir`/safe mode nếu include bị từ chối.
- [ ] Build chạy HTTP tests trước Asciidoctor và dùng snippets của build hiện tại.
- [ ] HTML/PDF cuối được render thành công với đủ request, response và descriptor snippets.

Đường dẫn tương đối giúp tài liệu Spring REST Docs hoạt động trên nhiều máy mà không phụ thuộc workspace cá nhân. Hãy xác định nơi file AsciiDoc đang nằm, nơi snippet được sinh và ngữ cảnh Asciidoctor dùng để phân giải include. Với dự án có nhiều operation hoặc nhiều cấp file nguồn, sử dụng attribute `{snippets}` do build cấu hình thường dễ bảo trì hơn việc lặp lại nhiều cấp `../` trong từng include.

## Tài liệu tham khảo

- [Asciidoctor – Include Directive](https://docs.asciidoctor.org/asciidoc/latest/directives/include/)
- [Asciidoctor – Document Attributes](https://docs.asciidoctor.org/asciidoc/latest/attributes/document-attributes/)
- [Asciidoctor – Safe Modes](https://docs.asciidoctor.org/asciidoctor/latest/safe-modes/)
- [Spring REST Docs – Getting Started](https://docs.spring.io/spring-restdocs/reference/getting-started.html)
- [Spring REST Docs – Reference Documentation](https://docs.spring.io/spring-restdocs/docs/current/reference/htmlsingle/)
