# Kiểm tra JAR chứa đủ HTML, Markdown và asset

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Xác định những file HTML, Markdown và tài nguyên tĩnh cần có trong artifact tài liệu.
- Hiểu vị trí classpath resource tương ứng với entry bên trong executable Spring Boot JAR.
- Dùng công cụ JDK để liệt kê, tìm kiếm và giải nén nội dung JAR.
- Kiểm tra file tồn tại, kích thước hợp lý, nội dung không rỗng và cấu trúc thư mục được giữ nguyên.
- Phân biệt Markdown source với HTML được browser phục vụ và hiểu cách consumer truy cập từng loại.
- Phát hiện asset bị thiếu, sai đường dẫn tương đối, file bị lọc hoặc task copy bỏ sót.
- Tự động hóa kiểm tra tính đầy đủ của artifact trong Gradle, Maven và CI.

## 1. Vì sao cần kiểm tra nội dung JAR?

Build thành công không đồng nghĩa executable JAR đã chứa đầy đủ tài liệu. Một JAR có thể khởi động bình thường nhưng trang docs thiếu file CSS, ảnh, trang operation hoặc Markdown source.

Các nguyên nhân thường gặp:

- Asciidoctor chỉ tạo index.html nhưng task copy không đưa các trang con vào resource directory.
- Copy task chỉ lấy file HTML ở thư mục gốc, bỏ qua thư mục con.
- Include/exclude pattern trong Gradle hoặc Maven loại nhầm CSS, JS, ảnh hoặc Markdown.
- Tài liệu được tạo sau khi resource processing hoặc package đã chạy.
- Resource filtering làm thay đổi nội dung file tĩnh.
- Link tương đối trong HTML trỏ đến asset không có trong JAR.
- File Markdown nằm ngoài output directory mà task package đọc.

Vì vậy, cần kiểm tra artifact sau khi package. Việc kiểm tra thư mục build trước package chỉ xác nhận output trung gian, chưa chứng minh JAR cuối cùng có đủ file.

## 2. Xác định nội dung cần đóng gói

Trước khi kiểm tra, lập danh sách file mong đợi. Một bộ tài liệu có thể gồm:

| Nhóm | Ví dụ | Mục đích |
| --- | --- | --- |
| Trang HTML chính | index.html | Trang bắt đầu và điều hướng |
| Trang operation | orders.html, authentication.html | Nội dung API theo resource |
| Markdown source | index.md, orders.md | Nguồn dễ đọc, tải về hoặc xử lý lại |
| CSS | css/site.css, css/theme.css | Kiểu trình bày |
| JavaScript | js/navigation.js, js/search.js | Navigation, tìm kiếm hoặc tương tác |
| Hình ảnh | images/logo.svg, images/flow.png | Logo, sơ đồ và hình minh họa |
| Font | fonts/*.woff2 | Font tùy chỉnh |
| Metadata | manifest.json, version.json | Version, revision hoặc thông tin phát hành |
| Tài liệu tải về | openapi.yaml, api-guide.pdf | Artifact bổ sung nếu dự án công bố |

Không phải dự án nào cũng cần đủ các nhóm trên. Manifest phải phản ánh đúng output của dự án, không kiểm tra một file không được thiết kế để phát hành.

### 2.1. Ví dụ cấu trúc mong đợi

Giả sử ứng dụng đặt tài liệu dưới static/docs:

```text
BOOT-INF/classes/static/docs/
├── index.html
├── index.md
├── manifest.json
├── orders/
│   ├── index.html
│   └── orders.md
├── css/
│   └── site.css
├── js/
│   └── navigation.js
└── images/
    ├── logo.svg
    └── request-flow.png
```

JAR không nhất thiết có cấu trúc giống thư mục source. Ví dụ source có thể nằm trong build/docs/asciidoc, sau đó được copy vào classpath resource. Điều cần kiểm tra là entry cuối cùng trong JAR có đúng prefix và giữ nguyên quan hệ thư mục.

### 2.2. HTML và Markdown có vai trò khác nhau

HTML thường là định dạng browser hiển thị trực tiếp. Markdown là source text có thể:

- Cho consumer tải về hoặc đọc dưới dạng text.
- Dùng làm nguồn cho một renderer khác.
- Được lưu để review, diff hoặc tái sử dụng.
- Được phục vụ với Content-Type phù hợp, thường là text/markdown nếu resource handler và cấu hình MIME hỗ trợ.

Browser không mặc định biến một file .md thành website có navigation và style như HTML. Nếu người đọc cần trang web, hãy đóng gói HTML đã render. Nếu cần source Markdown, đóng gói thêm file .md và công bố cách truy cập rõ ràng.

## 3. Từ classpath resource đến entry trong JAR

Với Spring Boot, file đặt dưới src/main/resources/static/docs thường được copy vào classpath với đường dẫn:

```text
static/docs/index.html
static/docs/index.md
static/docs/css/site.css
```

Trong executable JAR, các entry này thường xuất hiện dưới:

```text
BOOT-INF/classes/static/docs/index.html
BOOT-INF/classes/static/docs/index.md
BOOT-INF/classes/static/docs/css/site.css
```

Spring Boot loader dùng nội dung dưới BOOT-INF/classes làm classpath của ứng dụng. Vì vậy, đường dẫn entry trong JAR cần được đối chiếu với resource path mà ứng dụng dự kiến phục vụ.

Ví dụ mapping mặc định thường gặp:

| JAR entry | URL khi ứng dụng chạy |
| --- | --- |
| BOOT-INF/classes/static/docs/index.html | /docs/ hoặc /docs/index.html |
| BOOT-INF/classes/static/docs/index.md | /docs/index.md |
| BOOT-INF/classes/static/docs/css/site.css | /docs/css/site.css |
| BOOT-INF/classes/static/docs/images/logo.svg | /docs/images/logo.svg |

URL thực tế có thể thay đổi theo context path, resource handler, security và reverse proxy. Entry tồn tại trong JAR chưa đủ chứng minh URL hoạt động; cần thêm runtime smoke test.

## 4. Liệt kê nội dung JAR bằng jar tf

JDK cung cấp lệnh jar để xem danh sách entry:

```bash
jar tf build/libs/orders-service.jar
```

Trên Maven:

```bash
jar tf target/orders-service.jar
```

Tìm các entry quan trọng:

```bash
jar tf build/libs/orders-service.jar | grep 'BOOT-INF/classes/static/docs/'
```

Trên Windows PowerShell, có thể lọc kết quả:

```powershell
jar tf build/libs/orders-service.jar | Select-String 'BOOT-INF/classes/static/docs/'
```

Kiểm tra ít nhất:

- Có trang HTML chính.
- Có những trang operation mà index liên kết đến.
- Có Markdown source nếu release contract yêu cầu.
- Có tất cả CSS, JavaScript, hình ảnh và font được tham chiếu.
- Có metadata/version file nếu pipeline công bố.

Không chỉ đếm số entry. Một JAR có hàng trăm file vẫn có thể thiếu đúng file mà trang chính cần.

## 5. Kiểm tra từng file bắt buộc

Có thể dùng danh sách expected paths để xác minh:

```text
BOOT-INF/classes/static/docs/index.html
BOOT-INF/classes/static/docs/index.md
BOOT-INF/classes/static/docs/orders/index.html
BOOT-INF/classes/static/docs/orders/orders.md
BOOT-INF/classes/static/docs/css/site.css
BOOT-INF/classes/static/docs/js/navigation.js
BOOT-INF/classes/static/docs/images/logo.svg
```

Danh sách này là ví dụ. Thay bằng manifest thực tế của dự án. File không bắt buộc có thể được kiểm tra theo điều kiện, nhưng file cốt lõi như index.html nên khiến build thất bại nếu bị thiếu.

### 5.1. Kiểm tra bằng PowerShell

Có thể lấy danh sách entry và kiểm tra các path bắt buộc:

```powershell
$jarPath = "build/libs/orders-service.jar"
$entries = jar tf $jarPath

$required = @(
    "BOOT-INF/classes/static/docs/index.html",
    "BOOT-INF/classes/static/docs/index.md",
    "BOOT-INF/classes/static/docs/css/site.css",
    "BOOT-INF/classes/static/docs/images/logo.svg"
)

$missing = $required | Where-Object { $_ -notin $entries }
if ($missing.Count -gt 0) {
    $missing | ForEach-Object { Write-Error "Missing JAR entry: $_" }
    exit 1
}

Write-Host "Documentation entries are present."
```

Script này minh họa kiểm tra tồn tại. Với dự án thật, lưu manifest trong build script hoặc CI configuration và điều chỉnh các file bắt buộc theo tài liệu được phát hành.

### 5.2. Kiểm tra theo pattern

Có thể kiểm tra ít nhất một file trong từng nhóm:

- Ít nhất một file .html.
- Có file .md nếu source Markdown được phát hành.
- Có CSS nếu HTML tham chiếu stylesheet.
- Có JS nếu trang dùng script.
- Có file ảnh/font nếu HTML hoặc CSS tham chiếu chúng.

Kiểm tra theo pattern hữu ích khi số trang thay đổi theo số operation. Tuy nhiên, pattern không thay thế danh sách file cốt lõi cần có.

## 6. Giải nén JAR để xác minh nội dung

Danh sách entry chỉ xác nhận tên file. Để kiểm tra file có nội dung, giải nén JAR vào thư mục tạm:

```bash
mkdir -p build/jar-inspection
cd build/jar-inspection
jar xf ../libs/orders-service.jar BOOT-INF/classes/static/docs
```

Sau đó kiểm tra:

```bash
find BOOT-INF/classes/static/docs -type f
```

Với PowerShell:

```powershell
$inspectionDir = "build/jar-inspection"
New-Item -ItemType Directory -Force -Path $inspectionDir | Out-Null
Push-Location $inspectionDir
jar xf ../libs/orders-service.jar BOOT-INF/classes/static/docs
Get-ChildItem -Recurse BOOT-INF/classes/static/docs
Pop-Location
```

Giải nén giúp kiểm tra:

- File có kích thước lớn hơn 0.
- HTML chứa title và nội dung dự kiến.
- Markdown chứa heading và source text.
- CSS/JS không bị rỗng hoặc bị resource filtering làm thay đổi.
- Ảnh/SVG/font có thể đọc được.
- Relative asset path có file đích tương ứng.

Không chỉnh sửa file đã giải nén để sửa artifact. Nếu phát hiện lỗi, quay lại nguồn AsciiDoc, asset hoặc build task rồi tạo lại JAR.

## 7. Kiểm tra HTML tham chiếu asset

Một trang HTML có thể trả 200 nhưng CSS hoặc ảnh bị thiếu. Ví dụ:

```html
<link rel="stylesheet" href="css/site.css">
<script src="js/navigation.js"></script>
<img src="images/logo.svg" alt="Orders API">
```

Các đường dẫn tương đối được giải quyết dựa trên URL trang HTML. Với trang ở /docs/index.html, browser tìm:

```text
/docs/css/site.css
/docs/js/navigation.js
/docs/images/logo.svg
```

Nếu trang con ở /docs/orders/index.html dùng ../css/site.css, URL đích sẽ khác. Hãy kiểm tra từng trang con và tài nguyên mà nó tham chiếu.

### 7.1. Những lỗi đường dẫn phổ biến

| Biểu hiện | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| HTML 200, CSS 404 | CSS không được copy hoặc href sai | Kiểm tra JAR entry và URL asset |
| Trang chính hoạt động, trang con mất logo | Relative path tính từ thư mục trang con | Sửa relative URL hoặc cấu hình base path |
| CSS tải được nhưng font 404 | CSS tham chiếu font ở path không được đóng gói | Kiểm tra url(...) trong CSS và entry font |
| JS 404 | Script path sai hoặc include/exclude bỏ file | Kiểm tra script src và resource task |
| SVG không hiển thị | File thiếu, MIME type hoặc SVG bị xử lý sai | Kiểm tra entry, nội dung và response Content-Type |

Không thay mọi URL bằng đường dẫn bắt đầu từ /docs/ nếu website có thể được deploy dưới context path khác. Dùng relative path hoặc base path được cấu hình nhất quán.

## 8. Kiểm tra Markdown source

Nếu yêu cầu phát hành cả HTML và Markdown, cần xác minh file .md được copy vào JAR:

```text
BOOT-INF/classes/static/docs/index.md
BOOT-INF/classes/static/docs/orders/orders.md
```

Kiểm tra file Markdown:

- Không rỗng.
- Có heading chính.
- Có code fence mở/đóng cân bằng.
- Link đến hình ảnh hoặc file tải về trỏ đến tài nguyên có trong artifact.
- Không chứa secret, token, cookie hoặc dữ liệu production.
- Có version/source revision nếu release policy yêu cầu.

Nếu Markdown dùng relative image path:

```markdown
![Request flow](images/request-flow.png)
```

thì file images/request-flow.png cần nằm đúng vị trí tương đối với file Markdown hoặc link phải được điều chỉnh theo layout phát hành.

### 8.1. URL truy cập Markdown

Nếu resource được đặt dưới static/docs, có thể request:

```text
GET /docs/index.md
```

Server có thể trả Markdown như text/plain hoặc text/markdown tùy MIME mapping. Không giả định browser sẽ render Markdown. Nếu cần hiển thị đẹp, cung cấp HTML tương ứng hoặc một Markdown viewer riêng.

## 9. Kiểm tra kích thước và file rỗng

Entry tồn tại nhưng có kích thước 0 byte thường là dấu hiệu task copy hoặc render lỗi. Nên kiểm tra size tối thiểu cho các file chính:

| Loại file | Kiểm tra |
| --- | --- |
| index.html | Lớn hơn 0 và có nội dung trang |
| Markdown | Lớn hơn 0 và có heading |
| CSS/JS | Lớn hơn 0 nếu trang cần dùng |
| SVG/ảnh | Kích thước hợp lý, file đọc được |
| manifest/version | JSON hợp lệ và chứa metadata cần thiết |

Không đặt ngưỡng byte tùy tiện quá cao. Một CSS nhỏ có thể hợp lệ; một ảnh lớn bất thường có thể cần tối ưu. Tập trung vào file không rỗng, định dạng đúng và có mặt khi được tham chiếu.

## 10. Kiểm tra Gradle đưa đủ tài nguyên vào JAR

Nếu dùng generated resource directory, hãy đảm bảo copy task lấy toàn bộ cây Asciidoctor output:

```groovy
tasks.register('copyApiDocs', Copy) {
    dependsOn tasks.named('asciidoctor')
    from(layout.buildDirectory.dir('docs/asciidoc'))
    into(layout.buildDirectory.dir('generated-resources/api-docs/static/docs'))
}

sourceSets {
    main {
        resources {
            srcDir(layout.buildDirectory.dir('generated-resources/api-docs'))
        }
    }
}

tasks.named('processResources') {
    dependsOn tasks.named('copyApiDocs')
}
```

Không giới hạn include chỉ còn index.html nếu trang cần CSS, JS, images hoặc Markdown. Nếu cần loại bỏ file tạm, dùng exclude cụ thể và kiểm tra manifest sau package.

### 10.1. Kiểm tra task output

Gradle có thể chạy task incremental hoặc cache. Khi thay đổi file input, cần khai báo inputs/outputs phù hợp để task copy và Asciidoctor được chạy lại khi cần. Khi điều tra artifact thiếu file:

```bash
./gradlew clean test asciidoctor copyApiDocs bootJar
```

Sau đó kiểm tra JAR mới tạo bằng jar tf. Clean build giúp loại trừ file stale còn sót từ lần chạy trước.

## 11. Kiểm tra Maven đưa đủ tài nguyên vào JAR

Với Maven, output HTML/Markdown cần được copy vào target/classes trước package:

```xml
<configuration>
  <outputDirectory>target/classes/static/docs</outputDirectory>
  <resources>
    <resource>
      <directory>target/generated-docs</directory>
      <filtering>false</filtering>
    </resource>
  </resources>
</configuration>
```

Thư mục generated-docs cần chứa toàn bộ cây tài liệu, không chỉ index.html. Nếu dùng includes/excludes, rà soát chúng với manifest mong đợi.

Tắt filtering cho HTML, Markdown, CSS, JS, SVG và các asset nhị phân. Filtering không phù hợp có thể thay placeholder hoặc chuỗi đặc biệt trong source, làm nội dung không còn nguyên vẹn.

Sau package:

```bash
mvn clean verify
jar tf target/orders-service.jar
```

Xác minh entries dưới BOOT-INF/classes/static/docs. Không dừng ở việc target/classes có file; JAR cuối cùng mới là artifact sẽ được deploy.

## 12. Tự động kiểm tra completeness trong CI

Một bước CI có thể kiểm tra manifest:

1. Build sạch và chạy documentation tests.
2. Render Asciidoctor.
3. Package executable JAR.
4. Liệt kê entries trong JAR.
5. So sánh với danh sách file bắt buộc.
6. Giải nén tài liệu vào thư mục tạm.
7. Kiểm tra file rỗng, HTML/Markdown thiếu nội dung và asset bị thiếu.
8. Chạy runtime smoke test cho URL docs.

Ví dụ shell kiểm tra entry:

```bash
set -eu

JAR_FILE="build/libs/orders-service.jar"
ENTRIES_FILE="build/jar-entries.txt"

jar tf "$JAR_FILE" > "$ENTRIES_FILE"

grep -Fxq "BOOT-INF/classes/static/docs/index.html" "$ENTRIES_FILE"
grep -Fxq "BOOT-INF/classes/static/docs/index.md" "$ENTRIES_FILE"
grep -Fxq "BOOT-INF/classes/static/docs/css/site.css" "$ENTRIES_FILE"
```

Nếu một file không tồn tại, grep trả mã khác 0 và set -e làm bước CI thất bại. Thêm các entry bắt buộc theo manifest của dự án.

### 12.1. Kiểm tra runtime

Sau khi JAR được chạy trong smoke-test environment, kiểm tra các URL:

```bash
curl --fail --silent --show-error http://localhost:8080/docs/
curl --fail --silent --show-error http://localhost:8080/docs/index.md
curl --fail --silent --show-error http://localhost:8080/docs/css/site.css
curl --fail --silent --show-error http://localhost:8080/docs/images/logo.svg
```

Các URL trên là ví dụ. Thay host, context path và file theo cấu hình runtime. Kiểm tra response body hoặc Content-Type nếu cần; chỉ kiểm tra status có thể bỏ sót nội dung rỗng hoặc sai loại.

## 13. Bảo vệ tính toàn vẹn của artifact

Sau khi xác nhận file tồn tại, có thể kiểm tra tính toàn vẹn:

- Tính SHA-256 của JAR trước khi publish.
- So sánh checksum sau khi tải artifact từ repository.
- Lưu manifest entry và build metadata cạnh artifact.
- Kiểm tra file Markdown/HTML không chứa secret.
- Đảm bảo artifact được tạo từ source revision đã phê duyệt.

Ví dụ:

```bash
sha256sum build/libs/orders-service.jar
```

Checksum xác nhận byte artifact không đổi giữa hai lần kiểm tra. Nó không chứng minh nội dung đúng về mặt học thuật hoặc không chứa secret; cần kết hợp kiểm tra nội dung và review.

## 14. Lỗi thường gặp

| Biểu hiện | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| JAR có HTML nhưng thiếu Markdown | Markdown nằm ngoài copy source hoặc bị exclude | Thêm file .md vào output/manifest và copy tree |
| JAR chỉ có trang index | Copy task chỉ chọn một file | Copy đệ quy toàn bộ docs output |
| CSS/ảnh không có trong JAR | Include pattern thiếu asset extension hoặc folder | Rà soát include/exclude và kiểm tra entry |
| File có entry nhưng 0 byte | Render/copy task tạo file rỗng | Kiểm tra task output trước package |
| JAR có asset nhưng browser 404 | URL relative/base path không khớp | Kiểm tra link trong HTML/CSS và runtime mapping |
| Markdown tải được nhưng không hiển thị như trang | Browser nhận source Markdown | Cung cấp HTML hoặc viewer riêng |
| JAR có file cũ không còn trong source | Output directory không được clean | Clean build hoặc xóa destination trước copy |
| HTML/CSS chứa placeholder lạ | Resource filtering đã sửa nội dung | Tắt filtering cho tài liệu static |
| CI xanh dù thiếu trang operation | Chỉ kiểm tra index hoặc chỉ kiểm tra build success | So sánh manifest bắt buộc và kiểm tra các link đích |

## 15. Checklist kiểm tra JAR

- [ ] Có manifest các file HTML, Markdown và asset mong đợi.
- [ ] JAR chứa index.html dưới đúng classpath path.
- [ ] Các trang operation được liên kết đều có trong JAR.
- [ ] Markdown source có trong JAR nếu release yêu cầu.
- [ ] CSS, JavaScript, images và fonts được đóng gói đầy đủ.
- [ ] Relative path giữa HTML và asset được giữ nguyên.
- [ ] Không có file bắt buộc rỗng hoặc bị cắt cụt.
- [ ] Không có resource filtering làm thay đổi nội dung.
- [ ] Đã giải nén và kiểm tra file quan trọng.
- [ ] Runtime URL cho HTML, Markdown và asset trả nội dung đúng.
- [ ] CI so sánh JAR entries với manifest.
- [ ] Checksum và source revision được lưu theo release policy.

## 16. Bài tập thực hành

Một dịch vụ Orders đóng gói tài liệu dưới static/docs. Bộ tài liệu yêu cầu:

- index.html và index.md.
- orders/index.html và orders/orders.md.
- css/site.css.
- js/navigation.js.
- images/logo.svg.

Hãy thực hiện:

1. Viết manifest gồm các entry classpath bắt buộc.
2. Build executable JAR từ clean state.
3. Dùng jar tf liệt kê và kiểm tra từng entry trong manifest.
4. Giải nén static/docs ra thư mục tạm và xác minh file không rỗng.
5. Kiểm tra HTML tham chiếu CSS, JS và logo đúng relative path.
6. Kiểm tra Markdown có heading, code fence cân bằng và link ảnh hợp lệ.
7. Chạy JAR và gọi URL /docs/, /docs/index.md, /docs/css/site.css và /docs/images/logo.svg.
8. Cố ý loại bỏ một asset trong copy task để xác nhận CI phát hiện lỗi.
9. Khôi phục copy rule, chạy lại build và lưu checksum của JAR.

**Câu hỏi tự kiểm tra:** Nếu jar tf cho thấy index.html, có thể kết luận toàn bộ tài liệu đã được đóng gói đầy đủ không? Không. Cần xác minh các trang con, Markdown nếu được yêu cầu, CSS/JS/images/fonts mà HTML tham chiếu, nội dung file sau giải nén và URL runtime. Một entry duy nhất không đại diện cho toàn bộ website.

## Kết luận

Kiểm tra JAR cần xác minh cả tên entry, nội dung file và khả năng truy cập runtime. Hãy lập manifest HTML, Markdown và asset cần phát hành; dùng jar tf để so sánh entry, giải nén để kiểm tra file không rỗng và xác minh relative path giữa trang với tài nguyên. Markdown là source có thể tải hoặc xử lý tiếp, còn HTML mới là định dạng browser thường hiển thị trực tiếp. Gradle/Maven phải copy toàn bộ cây output và tránh filtering làm thay đổi nội dung. Cuối cùng, CI cần kiểm tra manifest, nội dung quan trọng, URL runtime và checksum để phát hiện sớm artifact thiếu trang hoặc asset trước khi phát hành.
