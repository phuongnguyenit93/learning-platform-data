# Tích hợp kiểm tra tài liệu vào CI

## Mục tiêu bài học

Tài liệu REST API chỉ đáng tin cậy khi có thể tái tạo từ các bài kiểm thử HTTP và được kiểm tra trong mỗi lần thay đổi code. Nếu CI chỉ chạy unit test mà không sinh snippet, render tài liệu và xác minh đầu ra, trang API có thể lỗi thời dù build vẫn xanh.

Bài học thuộc chương **Thực hành tổng hợp** của module **SPRING_REST_DOCS**: tạo tài liệu REST API có thể kiểm chứng bằng Spring REST Docs từ các bài kiểm thử HTTP với **MockMvc**, **WebTestClient** hoặc **REST Assured**; sinh snippet cho request, response, payload, tham số và header; biên soạn tài liệu Asciidoctor/Markdown rồi đưa vào quy trình build, CI.

Sau bài học, bạn có thể:

- Thiết kế pipeline CI hoàn chỉnh cho Spring REST Docs.
- Nối đúng thứ tự test, sinh snippet, render và kiểm tra tài liệu.
- Thiết lập quality gate để build thất bại khi thiếu snippet hoặc tài liệu lỗi.
- Kiểm tra link, include, JSON, field descriptors và dữ liệu nhạy cảm.
- Lưu artifact tài liệu để review hoặc publish.
- Giữ kết quả build nhất quán giữa local và CI.
- Tách kiểm tra tài liệu khỏi bước deploy ứng dụng khi cần.

## 1. Vì sao phải kiểm tra tài liệu trong CI?

Spring REST Docs lấy nội dung tài liệu từ HTTP operation được test thực thi. Khi API thay đổi, test và descriptor có thể phát hiện field mới, field bị xóa hoặc response khác contract. Tuy nhiên, để người đọc nhận được tài liệu hoàn chỉnh, pipeline còn phải ghép snippet và render tài liệu.

CI nên phát hiện các lỗi:

- Test không chạy hoặc không tạo snippet.
- Document identifier thay đổi nhưng file AsciiDoc/Markdown vẫn include tên cũ.
- Request/response field descriptor không còn khớp payload.
- Asciidoctor không tìm thấy include hoặc extension.
- Markdown assembly bỏ sót fragment.
- Link nội bộ hoặc asset bị hỏng.
- Snippet chứa token, cookie hoặc dữ liệu cá nhân.
- Artifact cuối không được tạo hoặc upload sai thư mục.

Một pipeline hoàn chỉnh biến tài liệu thành sản phẩm có thể kiểm tra, không phải một tác vụ thủ công sau khi release.

## 2. Kiến trúc pipeline

Luồng cơ bản:

~~~mermaid
flowchart TD
    A["Checkout source"] --> B["Resolve pinned toolchain"]
    B --> C["Run HTTP documentation tests"]
    C --> D["Generate REST Docs snippets"]
    D --> E["Validate required snippets"]
    E --> F["Assemble / render documentation"]
    F --> G["Check links, includes and content"]
    G --> H["Scan for secrets"]
    H --> I["Upload documentation artifact"]
    I --> J["Optional publish / deploy"]
~~~

Mỗi bước cần có điều kiện thành công rõ ràng:

| Bước | Điều kiện pass |
| --- | --- |
| Toolchain | Dùng đúng JDK và build wrapper đã pin |
| HTTP tests | Tất cả test documentation pass |
| Snippet generation | Các operation cần tài liệu có output |
| Snippet validation | File bắt buộc tồn tại và không rỗng |
| Render | Asciidoctor/Markdown renderer kết thúc thành công |
| Content checks | Link, include, JSON và cấu trúc tài liệu hợp lệ |
| Secret checks | Không phát hiện dữ liệu nhạy cảm cần chặn |
| Artifact | Thư mục output được tạo và lưu thành công |

Không gộp mọi bước thành một lệnh khó chẩn đoán. Có thể chạy trong cùng job nhưng log cần chỉ ra bước nào thất bại.

## 3. Chuẩn bị project để CI tái tạo được

Trước khi viết workflow, xác định:

| Thành phần | Cần chốt |
| --- | --- |
| JDK | Version và distribution được CI sử dụng |
| Build tool | Gradle Wrapper hoặc Maven Wrapper |
| Test integration | MockMvc, WebTestClient hoặc REST Assured |
| Snippet output | Một output directory cố định dưới build/target |
| Document identifiers | Danh sách ID được tài liệu include |
| Renderer | Asciidoctor task hoặc Markdown generator/assembly |
| Artifact directory | Thư mục HTML/PDF/Markdown cuối cùng |
| Validation | Script kiểm tra snippet, link và nội dung |

Dùng wrapper của repository thay vì cài một version Gradle/Maven bất kỳ trên runner. Pin version plugin và dependency; tránh dùng latest trong build vì kết quả có thể thay đổi giữa hai lần chạy CI.

Đặt output sinh ra trong thư mục build (build/ với Gradle hoặc target/ với Maven). Không commit snippet được sinh như nguồn chân lý nếu quy trình của dự án quy định test tạo lại chúng.

## 4. Chạy test sinh snippet

Với Gradle, test REST Docs thường chạy trong test hoặc một task riêng. Ví dụ:

~~~powershell
./gradlew clean test
~~~

Nếu dự án tách test documentation:

~~~groovy
tasks.register('documentationTest', Test) {
    useJUnitPlatform()
    include '**/*DocumentationTest.class'
}
~~~

Chỉ tạo task riêng khi project có naming convention và test suite phù hợp. Nếu task test đã chạy tất cả REST Docs tests, không cần chạy trùng lần nữa.

Với Maven:

~~~bash
./mvnw clean test
~~~

Nếu test được chia theo profile hoặc Maven Failsafe, kích hoạt đúng profile/phase để chắc chắn integration tests tạo snippet cũng được chạy. Kiểm tra test report để xác nhận số test thực sự được thực thi.

### 4.1. Giữ output sạch

CI thường dùng workspace mới, nhưng trong job có cache hoặc nhiều task, file snippet cũ vẫn có thể tồn tại. Dùng clean build hoặc làm sạch đúng output directory trước khi test sinh snippet.

Không xóa toàn bộ workspace hoặc cache dependency một cách tùy tiện. Chỉ làm sạch thư mục output thuộc quyền sở hữu của task tài liệu.

## 5. Xác thực snippet bắt buộc

Một test suite có thể pass nhưng một operation không còn được gọi hoặc không còn ghi documentation. Vì vậy, thêm bước xác nhận các snippet cần thiết tồn tại.

Ví dụ PowerShell:

~~~powershell
$required = @(
    'build/generated-snippets/orders-get/http-request.adoc',
    'build/generated-snippets/orders-get/http-response.adoc',
    'build/generated-snippets/orders-create/request-fields.adoc',
    'build/generated-snippets/orders-create/response-fields.adoc'
)

$missing = $required | Where-Object {
    -not (Test-Path -LiteralPath $_ -PathType Leaf)
}

if ($missing.Count -gt 0) {
    throw "Missing REST Docs snippets: $($missing -join ', ')"
}

$empty = $required | Where-Object {
    (Test-Path -LiteralPath $_ -PathType Leaf) -and
    ((Get-Item -LiteralPath $_).Length -eq 0)
}

if ($empty.Count -gt 0) {
    throw "Empty REST Docs snippets: $($empty -join ', ')"
}
~~~

Đường dẫn và phần mở rộng ở trên chỉ là ví dụ. Thay bằng output directory, document identifier và template format thật của project. Nếu project dùng Markdown template, tên file có thể là .md.

Không yêu cầu tất cả loại snippet cho mọi operation. Ví dụ GET không có request body thì không cần request-fields.adoc. Manifest nên mô tả đúng những fragment mà trang tài liệu thực sự include.

## 6. Render tài liệu Asciidoctor

Với Gradle Asciidoctor plugin, task render phải phụ thuộc vào task sinh snippet:

~~~groovy
tasks.named('asciidoctor') {
    dependsOn tasks.named('test')
    inputs.dir layout.buildDirectory.dir('generated-snippets')
    attributes 'snippets': layout.buildDirectory
        .dir('generated-snippets')
        .get()
        .asFile
}
~~~

Chạy:

~~~powershell
./gradlew clean test asciidoctor
~~~

Xác nhận output directory của task. Ví dụ:

~~~powershell
Get-ChildItem -Path build/docs/asciidoc -Recurse -File
~~~

Không mặc định mọi cấu hình plugin đều ghi vào build/docs/asciidoc; kiểm tra outputDir trong build script.

Với Maven, plugin Asciidoctor phải được gắn vào lifecycle phù hợp. Chạy phase đã cấu hình, ví dụ verify, rồi xác nhận HTML được tạo. mvn test không tự đảm bảo tài liệu đã được render nếu execution nằm ở phase khác.

### 6.1. Kiểm tra include

Asciidoctor include có thể trỏ tới file không tồn tại nếu:

- snippets attribute trỏ sai output directory.
- document(...) đổi identifier.
- Tên snippet hoặc extension khác template hiện tại.
- Task render chạy trước test.

Asciidoctor thường báo lỗi khi include bắt buộc không tìm thấy file. Không tắt lỗi include để pipeline pass; sửa đúng path hoặc cập nhật nguồn tài liệu.

## 7. Render tài liệu Markdown

Markdown thuần không có include file chuẩn. Pipeline Markdown cần một trong các cơ chế đã được project chọn:

1. Plugin include của static site generator.
2. Template Markdown của REST Docs kết hợp với build-time assembly.
3. Chuyển đổi snippet AsciiDoc sang Markdown bằng công cụ được kiểm tra.

Luồng ví dụ:

~~~text
HTTP tests
   |
   v
build/generated-snippets/
   |
   v
Markdown assembly
   |
   v
build/docs-markdown/
   |
   v
Markdown site generator
   |
   v
build/site/
~~~

Nối task assembly sau test và renderer sau assembly. Thêm kiểm tra fragment bắt buộc trước khi render. Nếu generator có chế độ strict link checking, bật chế độ đó trong CI.

Không đặt directive Asciidoctor include trong file Markdown rồi kỳ vọng mọi renderer xử lý. Cần kiểm tra đúng plugin/generator và version đang dùng.

## 8. Quality gates cho tài liệu

Một pipeline tốt kiểm tra nhiều lớp, không chỉ kiểm tra exit code của renderer:

### 8.1. Test và descriptor

- HTTP tests pass.
- Field descriptors bao phủ payload theo contract.
- Path/query parameter và header được mô tả.
- Response status và error cases có test phù hợp.

### 8.2. Snippet

- Mọi file được include đều tồn tại.
- Snippet không rỗng.
- Operation identifier không bị đổi ngoài chủ đích.
- Preprocessor đã che token/cookie/session.
- Nội dung request/response thuộc đúng test operation.

### 8.3. Rendered output

- Asciidoctor hoặc Markdown generator kết thúc thành công.
- Không có include directive chưa xử lý.
- Link nội bộ và asset tồn tại.
- Code fence và table hiển thị đúng.
- JSON snippet hợp lệ nếu fragment là JSON thuần.
- Navigation/TOC được tạo theo cấu hình.

### 8.4. Artifact

- Output directory tồn tại.
- Có ít nhất một file tài liệu dự kiến (ví dụ index.html).
- Artifact được lưu với tên/version dễ nhận diện.
- Publish chỉ chạy sau khi các quality gate pass.

## 9. Kiểm tra dữ liệu nhạy cảm

Snippet có thể chứa giá trị lấy từ request/response test. Trước khi publish, kiểm tra:

- Authorization và bearer token.
- Cookie/session ID.
- API key hoặc secret header.
- Email, số điện thoại, địa chỉ và dữ liệu cá nhân thật.
- Host nội bộ, IP hoặc identifier không nên công bố.

Dùng fixture giả ngay trong test và preprocessor để loại bỏ/thay thế giá trị nhạy cảm. Không dựa vào secret scanner như biện pháp duy nhất; dữ liệu test phải an toàn từ nguồn.

Nếu CI phát hiện token mẫu như test-token, có thể fail để nhắc rằng preprocessing chưa hoạt động. Điều chỉnh pattern theo chính sách của dự án để tránh false positive với chuỗi minh họa công khai.

## 10. Ví dụ GitHub Actions

Workflow Gradle minh họa:

~~~yaml
name: REST Docs

on:
  pull_request:
  push:
    branches: [ main ]

jobs:
  documentation:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '21'

      - name: Generate snippets and render docs
        run: ./gradlew --no-daemon clean test asciidoctor

      - name: Validate required snippets
        shell: bash
        run: |
          required=(
            build/generated-snippets/orders-get/http-request.adoc
            build/generated-snippets/orders-get/http-response.adoc
          )
          for file in "${required[@]}"; do
            test -s "$file" || {
              echo "Missing or empty snippet: $file"
              exit 1
            }
          done

      - name: Verify rendered documentation
        run: test -s build/docs/asciidoc/index.html

      - name: Upload documentation artifact
        uses: actions/upload-artifact@v4
        with:
          name: rest-api-docs
          path: build/docs/asciidoc/
          if-no-files-found: error
~~~

Ví dụ giả định JDK 21, branch main, tên task asciidoctor, snippet path và output HTML như đã khai báo. Điều chỉnh theo wrapper, JDK support matrix, test IDs và outputDir thực tế của repository. Với Markdown, thay task Asciidoctor bằng assembly và generator tương ứng.

Trong repository thực tế, pin action theo chính sách bảo mật của tổ chức (ví dụ commit SHA đã được phê duyệt) và dùng permission tối thiểu cần thiết.

## 11. Artifact và publish

Nên tách hai quyết định:

- **Build artifact:** lưu HTML/Markdown đã render để reviewer tải và kiểm tra trong pull request.
- **Publish:** đưa tài liệu lên website hoặc nơi lưu trữ chính thức sau khi merge/release.

Không cần publish website ở mọi pull request. Có thể chỉ upload artifact để review, rồi publish từ branch chính hoặc tag release.

Nếu tài liệu được version hóa theo API release, dùng version/commit metadata trong đường dẫn artifact. Tránh ghi đè tài liệu của phiên bản đang phát hành bằng output từ nhánh chưa release.

## 12. Chạy pipeline hiệu quả và tái lập

Để local và CI cho kết quả tương đương:

- Dùng Gradle Wrapper/Maven Wrapper.
- Pin JDK và plugin versions.
- Quản lý REST Docs artifacts đồng bộ.
- Dùng fixture ổn định cho timestamp, UUID và dữ liệu động.
- Đặt output directory rõ ràng và làm sạch trước khi sinh snippet.
- Không phụ thuộc file sinh từ lần build trước.
- Không để test chạy song song ghi cùng document identifier nếu output bị xung đột.
- Lưu log và artifact khi pipeline thất bại để điều tra.

Cache dependency có thể tăng tốc build, nhưng không cache generated snippets như nguồn đầu vào đáng tin cậy. Snippet cần được tạo từ source và test của commit hiện tại.

## 13. Lỗi thường gặp

| Dấu hiệu | Nguyên nhân | Cách khắc phục |
| --- | --- | --- |
| Test pass nhưng không có tài liệu | Task render không chạy hoặc thiếu dependency | Nối test → renderer trong task graph |
| Snippet thiếu trong CI | Operation không được thực thi hoặc ID đổi | Kiểm tra test report, document ID và manifest |
| Local pass, CI fail | Output cũ còn trên máy local | Chạy clean build và xác minh path |
| Asciidoctor báo include missing | Attribute hoặc tên file sai | Đối chiếu generated snippets với include |
| Markdown còn directive include | Plugin/assembly không chạy | Kiểm tra generator và task dependency |
| Artifact rỗng | Upload sai output directory | Kiểm tra outputDir và file tồn tại |
| Pipeline không phát hiện token | Secret scan không bao phủ format snippet | Dùng fixture giả, preprocessor và content check |
| Build lâu do chạy test nhiều lần | Test task bị gọi lặp trong workflow | Thiết kế một task graph và tái sử dụng output cùng job |
| Hai test ghi đè snippet | Trùng document identifier | Đặt ID duy nhất hoặc tuần tự hóa operation |
| Tài liệu lỗi thời sau merge | Publish không gắn với commit/release mới | Nối publish với artifact của đúng revision |

## 14. Bài thực hành tổng hợp

Tích hợp CI cho API quản lý đơn hàng:

~~~text
GET  /api/orders/{id}
POST /api/orders
~~~

Yêu cầu:

1. Viết HTTP tests bằng MockMvc, WebTestClient hoặc REST Assured.
2. Sinh request, response, path parameters và request/response fields snippets.
3. Dùng preprocessor để format JSON và che header nhạy cảm.
4. Biên soạn trang AsciiDoc hoặc Markdown để include/assemble snippet.
5. Cấu hình task test chạy trước bước render.
6. Tạo manifest snippet bắt buộc và làm CI fail khi file thiếu/rỗng.
7. Kiểm tra include, link, JSON, code fence, field table và dữ liệu nhạy cảm.
8. Upload HTML/Markdown artifact cho pull request.
9. Chỉ publish tài liệu chính thức sau khi quality gates pass.
10. Thử cố ý đổi một document identifier hoặc xóa một snippet bắt buộc để xác nhận CI phát hiện lỗi.

**Tiêu chí hoàn thành:** một commit mới có thể tự sinh snippet và tài liệu từ workspace sạch; lỗi test, snippet thiếu, render lỗi hoặc dữ liệu nhạy cảm đều làm pipeline thất bại; artifact cuối có thể tải về và đối chiếu với commit.

## Ghi nhớ

CI cần kiểm tra toàn bộ chuỗi **HTTP tests → REST Docs snippets → Asciidoctor/Markdown → content validation → artifact**. Chạy test thôi chưa đủ. Hãy xác nhận snippet bắt buộc tồn tại, include/assembly hoạt động, renderer tạo output, link và JSON hợp lệ, dữ liệu nhạy cảm đã được xử lý và artifact được lưu đúng thư mục. Pin toolchain, dùng workspace sạch và chỉ publish sau khi quality gates pass để tài liệu API luôn tái tạo được từ commit hiện tại.

**Tài liệu tham khảo:** [Spring REST Docs Reference](https://docs.spring.io/spring-restdocs/reference/), [Spring REST Docs Getting Started](https://docs.spring.io/spring-restdocs/reference/getting-started/documentation.html), [Asciidoctor Gradle Plugin](https://docs.asciidoctor.org/gradle-plugin/latest/), [Asciidoctor Maven Plugin](https://docs.asciidoctor.org/maven-tools/latest/), [GitHub Actions Documentation](https://docs.github.com/actions) và [GitHub Actions upload-artifact](https://github.com/actions/upload-artifact).
