# Kiểm tra đường dẫn và encoding trên runner

Documentation tests của Spring REST Docs ghi snippet vào filesystem; Asciidoctor/Markdown renderer đọc các file đó để tạo tài liệu. Một pipeline chạy được trên máy developer chưa chắc chạy được trên CI runner, vì runner có thể dùng hệ điều hành khác, working directory khác, filesystem phân biệt chữ hoa/chữ thường, separator khác và locale/encoding khác. Các lỗi thường xuất hiện dưới dạng include không tìm thấy, đường dẫn artifact sai, ký tự tiếng Việt bị lỗi hoặc nội dung thay đổi giữa môi trường.

Để pipeline ổn định, cần quản lý đường dẫn theo build tool và workspace, dùng một nguồn cấu hình cho snippet output và renderer, xử lý file bằng UTF-8 nhất quán, đồng thời kiểm tra artifact ngay trên runner. Bài học này tập trung vào tính portable của path và encoding trong CI, không phụ thuộc một CI provider cụ thể.

Bài học thuộc chương **CI và phát hành** của module `SPRING_REST_DOCS`. Module tạo tài liệu REST API có thể kiểm chứng từ test HTTP bằng MockMvc, WebTestClient hoặc REST Assured, sinh snippet cho request, response, payload, tham số và header, rồi biên soạn Asciidoctor/Markdown và tích hợp build, CI.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Nhận diện khác biệt path giữa Windows, Linux và macOS runner.
2. Cấu hình snippets directory nhất quán giữa test recorder và Asciidoctor.
3. Tránh phụ thuộc vào working directory hoặc đường dẫn tuyệt đối trên máy developer.
4. Xử lý filesystem phân biệt hoa/thường và tên file chính xác.
5. Bảo đảm Markdown, AsciiDoc và snippet được đọc/ghi bằng UTF-8.
6. Kiểm tra newline, locale và encoding trên runner.
7. Xác minh artifact paths trước khi upload hoặc publish.

## 2. Vì sao path và encoding dễ lỗi trên CI?

Một dự án có thể phát triển trên Windows nhưng CI chạy Linux. Những khác biệt thường gây lỗi:

- Windows dùng dấu gạch chéo ngược trong path native; Linux/macOS thường dùng dấu gạch chéo xuôi.
- Filesystem Linux thường phân biệt Orders-Get và orders-get; môi trường local có thể không phân biệt.
- Working directory của CI step có thể khác thư mục chạy local.
- Đường dẫn tuyệt đối trên máy developer không tồn tại trên runner.
- File lưu bằng encoding mặc định của máy có thể bị đọc sai trên runner.
- Locale/timezone khác nhau có thể làm output chứa ký tự hoặc định dạng không ổn định.

### 2.1. Dấu hiệu nhận biết

| Triệu chứng | Nguyên nhân có thể |
| --- | --- |
| Asciidoctor báo include file không tồn tại | Sai base directory, identifier hoặc separator |
| Local chạy, Linux CI thất bại | Khác biệt chữ hoa/thường |
| Snippet có nhưng renderer không thấy | Test và renderer dùng hai output directory |
| Tiếng Việt thành ký tự lỗi | File không phải UTF-8 hoặc reader dùng encoding khác |
| Diff có nhiều thay đổi không rõ | Newline, locale hoặc timezone không thống nhất |
| Upload artifact báo không tìm thấy | Glob/path tính từ working directory khác |
| Test ghi ra thư mục bất ngờ | Relative path được resolve từ user.dir khác dự kiến |

## 3. Dùng path tương đối từ build directory

Tránh hard-code đường dẫn tuyệt đối như C:\Users\developer\project hoặc /home/runner/work. Những path này chỉ đúng trên một máy hoặc runner cụ thể.

Với Gradle, ưu tiên API build directory:

```groovy
def snippetsDir = layout.buildDirectory.dir("generated-snippets")

tasks.named("asciidoctor") {
    inputs.dir(snippetsDir)
}
```

Với Maven, dùng property build directory:

```xml
<snippets>${project.build.directory}/generated-snippets</snippets>
```

Cả hai ví dụ thể hiện cách xây path từ build system. Test recorder và Asciidoctor phải nhận cùng một giá trị. Nếu test ghi vào build/generated-snippets còn renderer tìm ở target/generated-snippets, include sẽ hỏng dù mỗi đường dẫn đều hợp lệ riêng lẻ.

### 3.1. Một nguồn cấu hình

Đặt snippets directory tại một property hoặc biến build dùng chung thay vì lặp string ở nhiều nơi. Ví dụ khái niệm trong Gradle:

```groovy
def restDocsSnippets = layout.buildDirectory.dir("generated-snippets")

tasks.named("test") {
    systemProperty(
        "org.springframework.restdocs.outputDir",
        restDocsSnippets.get().asFile.absolutePath
    )
}

tasks.named("asciidoctor") {
    inputs.dir(restDocsSnippets)
}
```

Cách truyền output directory vào test recorder tùy setup Spring REST Docs của dự án; cần kiểm tra cấu hình MockMvc/WebTestClient/REST Assured hiện tại. Không giả định system property ví dụ này tự cấu hình mọi test harness nếu dự án chưa đọc property đó. Nguyên tắc là chỉ có một nguồn giá trị cho cả hai phía.

## 4. Separator và API xử lý path

Trong file cấu hình AsciiDoc, include path thường viết bằng dấu /, kể cả khi build chạy trên Windows:

```asciidoc
include::{snippets}/orders-get/http-request.adoc[]
```

Trong code Java, dùng Path/Paths thay vì tự nối separator:

```java
Path snippets = Paths.get(
    buildDirectory,
    "generated-snippets",
    "orders-get"
);

Path requestSnippet = snippets.resolve("http-request.adoc");
```

Path.resolve(...) chọn separator phù hợp với filesystem hiện tại. Khi truyền path cho plugin hoặc công cụ ngoài JVM, dùng API build tool để cung cấp absolute path đã resolve từ project/build directory.

### 4.1. Không nối path bằng chuỗi

Tránh ghép chuỗi theo separator Windows như generated-snippets\orders-get. Cách này gắn chặt code với một OS và dễ tạo path sai trên Linux. Dùng Path.resolve, File hoặc API Gradle/Maven tương ứng.

### 4.2. Relative path phụ thuộc working directory

Một relative path như build/generated-snippets được resolve từ working directory của process. CI provider có thể chạy step từ repository root hoặc subdirectory được chỉ định. Hãy xác định working directory rõ trong job và dùng project/build directory làm base.

Không giả định shell đang đứng cùng folder với file build script hoặc file AsciiDoc. Renderer có thể resolve include theo base directory của document hoặc theo thuộc tính plugin truyền vào; kiểm tra hành vi của plugin đang dùng.

## 5. Filesystem phân biệt chữ hoa/thường

Linux runner thường phân biệt tên file theo case. Ví dụ:

```text
orders-get/http-request.adoc
Orders-Get/http-request.adoc
```

Hai đường dẫn có thể trỏ tới hai file khác nhau trên Linux. Nếu test dùng identifier orders-get nhưng AsciiDoc include Orders-Get, local có thể vẫn chạy trong một số filesystem, còn CI Linux báo thiếu file.

Quy tắc:

- Dùng identifier nhất quán, tốt nhất là lowercase kebab-case.
- Tên snippet phải khớp chính xác chữ hoa/thường.
- Kiểm tra tên file được tạo thực tế sau test.
- Không dựa vào filesystem local để xác nhận case sensitivity.

### 5.1. Kiểm tra include paths

Với mỗi include, kiểm tra cả directory và filename:

```asciidoc
include::{snippets}/orders-get/http-request.adoc[]
include::{snippets}/orders-get/http-response.adoc[]
include::{snippets}/orders-get/response-fields.adoc[]
```

Nếu descriptor không sinh response-fields.adoc, không thêm include chỉ dựa vào suy đoán. Hãy kiểm tra file thực tế và descriptor test.

## 6. Encoding UTF-8 cho nội dung tiếng Việt

Markdown, AsciiDoc và generated snippet có thể chứa tiếng Việt trong heading, description và payload ví dụ. Để tránh lỗi encoding:

- Lưu source .md, .adoc, .java, .yml bằng UTF-8.
- Cấu hình editor/repository để không chuyển sang encoding legacy.
- Khi script đọc/ghi file, chỉ định UTF-8 rõ ràng.
- Tránh dựa vào encoding mặc định của OS hoặc shell.
- Xác minh HTML/PDF cuối hiển thị dấu tiếng Việt chính xác.

Ví dụ Java đọc file UTF-8:

```java
String content = Files.readString(
    Path.of("src/docs/asciidoc/index.adoc"),
    StandardCharsets.UTF_8
);
```

Ví dụ PowerShell đọc/ghi UTF-8 trong script kiểm tra:

```powershell
$content = Get-Content -Raw -Encoding UTF8 -LiteralPath $path
Set-Content -LiteralPath $output -Value $content -Encoding UTF8
```

PowerShell 5.1 và các phiên bản mới có khác biệt về encoding mặc định và BOM. Chỉ định encoding rõ ràng trong script để tránh phụ thuộc phiên bản runner.

### 6.1. Encoding source và encoding output

Đừng chỉ kiểm tra source Markdown. Snippet có thể được tạo từ Java test, template hoặc fixture; renderer sau đó tạo HTML/PDF. Kiểm tra toàn chuỗi:

```text
Java test / fixture
       │
       ▼
Generated snippets
       │
       ▼
AsciiDoc / Markdown
       │
       ▼
HTML / PDF
```

Nếu một bước đọc sai encoding, lỗi có thể xuất hiện ở bước sau dù source ban đầu đúng UTF-8.

## 7. Newline, locale và timezone

Windows thường dùng CRLF; Linux thường dùng LF. Git có thể chuẩn hóa newline theo cấu hình repository. Nên khai báo quy tắc rõ qua .gitattributes, ví dụ:

```gitattributes
*.md   text eol=lf
*.adoc text eol=lf
*.yml  text eol=lf
*.java text eol=lf
```

Không ép file binary về text. PDF, hình ảnh và artifact nhị phân cần giữ nguyên bytes.

Locale và timezone cũng có thể ảnh hưởng timestamp hoặc định dạng ngày/giờ trong snippet. Nếu giá trị thời gian là fixture, dùng giá trị cố định. Nếu test cần thời gian, cố định Clock hoặc timezone theo contract. Tránh dựa vào locale mặc định của runner.

## 8. Xác minh output trên runner

Sau khi documentation tests chạy, kiểm tra:

1. Snippets directory tồn tại tại path dự kiến.
2. Các identifier có folder tương ứng.
3. File được include tồn tại với đúng case.
4. File không rỗng.
5. File text đọc được bằng UTF-8.
6. Asciidoctor chạy từ working directory/path đã cấu hình.
7. HTML/PDF output nằm đúng artifact directory.
8. Upload step trỏ tới artifact path thực tế.

Có thể viết validation task để fail sớm khi file include thiếu. Thông báo nên ghi rõ path đang tìm và working directory/base directory được dùng.

### 8.1. Không chỉ kiểm tra directory tồn tại

Snippets directory tồn tại không chứng minh tất cả operation được tạo. Kiểm tra từng identifier và file include bắt buộc. Đồng thời xác nhận test report cho thấy documentation tests đã thực sự chạy.

## 9. Ví dụ validation script portable

Ví dụ Java kiểm tra file snippet bằng Path:

```java
Path root = Paths.get(snippetsDirectory);

List<String> requiredFiles = List.of(
    "orders-get/http-request.adoc",
    "orders-get/http-response.adoc"
);

for (String relative : requiredFiles) {
    Path file = root.resolve(relative).normalize();

    if (!file.startsWith(root.normalize())) {
        throw new IllegalArgumentException("Invalid snippet path: " + relative);
    }

    if (!Files.isRegularFile(file) || Files.size(file) == 0) {
        throw new IllegalStateException(
            "Missing or empty REST Docs snippet: " + file
        );
    }

    String text = Files.readString(file, StandardCharsets.UTF_8);
}
```

Ví dụ minh họa việc kiểm tra file và encoding. Nếu dùng Java version cũ chưa có Files.readString hoặc List.of, thay bằng API tương thích. Khi operation lớn, có thể sinh danh sách required files từ manifest/include declarations để tránh duy trì hai danh sách rời rạc.

## 10. Artifact path trên CI

Artifact upload thường nhận path tương đối từ workspace hoặc glob. Đường dẫn cần khớp output thật:

```text
Gradle:
build/docs/**

Maven:
target/generated-docs/**

Snippets:
build/generated-snippets/**
hoặc
target/generated-snippets/**
```

Không upload build/docs nếu plugin thực tế ghi vào build/asciidoc/html5, hoặc upload snippets từ thư mục module khác. Kiểm tra cấu hình output plugin và log task trước khi khai báo artifact path.

Nếu multi-module build, xác định output từng module và vị trí tổng hợp. Không giả định mọi module ghi chung một root directory.

## 11. Lỗi thường gặp và cách khắc phục

| Triệu chứng | Nguyên nhân | Cách khắc phục |
| --- | --- | --- |
| Include local chạy nhưng fail trên Linux | Sai case identifier/file | Chuẩn hóa lowercase và kiểm tra chính xác |
| Snippet không tìm thấy | Sai output directory hoặc working directory | Dùng build directory chung và resolve path rõ |
| Path có separator sai | Nối chuỗi theo Windows | Dùng Path.resolve hoặc build API |
| Tiếng Việt lỗi dấu | Encoding mặc định khác UTF-8 | Lưu/đọc/ghi UTF-8 rõ ràng |
| Diff toàn file sau CI | CRLF/LF không thống nhất | Khai báo .gitattributes |
| Timestamp khác giữa runner | Locale/timezone/clock khác | Dùng fixture/Clock cố định |
| Artifact upload rỗng | Glob sai hoặc output path khác | Xác minh output thực tế trên runner |
| Module A lấy snippet module B | Output path dùng chung không phân biệt module | Đặt output theo module hoặc identifier namespace |
| File tồn tại nhưng render lỗi | File rỗng hoặc encoding sai | Kiểm tra size và đọc UTF-8 trước render |
| Local pass nhưng CI không có snippet | Test task bị filter hoặc skip | Kiểm tra test count và task execution |

## 12. Best practices

1. Dùng build directory và API path của Gradle/Maven thay cho absolute path máy cá nhân.
2. Dùng một nguồn cấu hình cho snippets output và Asciidoctor attribute.
3. Dùng / trong include path AsciiDoc và API Path trong Java.
4. Chuẩn hóa identifier và filename về case nhất quán.
5. Lưu source và text outputs bằng UTF-8; script phải chỉ định encoding.
6. Khai báo newline policy bằng .gitattributes nếu repository hỗ trợ nhiều OS.
7. Cố định locale/timezone hoặc fixture khi chúng ảnh hưởng snippet.
8. Validate từng include file, không chỉ kiểm tra directory tồn tại.
9. Xác minh artifact path từ log/output thật của runner.
10. Chạy CI trên Linux nếu production build dùng Linux, kể cả khi developer làm việc trên Windows.

## 13. Bài thực hành

Dự án Spring REST Docs phát triển trên Windows nhưng CI chạy Linux. Test tạo snippets vào build directory; Asciidoctor include request/response và trang Markdown có tiếng Việt. CI hiện báo thiếu file ở một identifier và một số dấu tiếng Việt bị lỗi.

**Nhiệm vụ:**

1. Xác định working directory và snippets output directory thực tế.
2. Đồng bộ cấu hình output giữa test recorder và Asciidoctor.
3. Kiểm tra case của identifier và filename trên Linux.
4. Thay path nối chuỗi bằng API Path/Gradle/Maven phù hợp.
5. Kiểm tra source .md, .adoc, snippet và script dùng UTF-8.
6. Chuẩn hóa newline policy nếu repository cần hỗ trợ Windows/Linux.
7. Cố định timezone/locale hoặc fixture cho dữ liệu thời gian.
8. Viết validation cho các snippet file được include.
9. Sửa artifact upload path theo output thực tế.
10. Chạy pipeline trên clean runner và kiểm tra HTML/PDF tiếng Việt.

**Tiêu chí hoàn thành:** path portable; include khớp case; recorder và renderer dùng chung output; text hiển thị UTF-8 chính xác; artifact upload đúng directory; pipeline tái lập giữa local và runner.

## 14. Ghi nhớ

- Runner có thể khác máy developer về OS, working directory, filesystem case sensitivity, locale và encoding.
- Dùng Gradle/Maven build directory làm base thay vì hard-code absolute path.
- Recorder và Asciidoctor phải dùng cùng snippets directory.
- Dùng Path.resolve trong Java; tránh tự nối separator theo một OS.
- Include path phải khớp chính xác case của identifier và filename.
- Lưu/đọc/ghi Markdown, AsciiDoc và snippet bằng UTF-8 rõ ràng.
- Chuẩn hóa newline, locale và timezone để giảm diff không cần thiết.
- Validate từng file include và artifact path ngay trên runner trước khi publish.
