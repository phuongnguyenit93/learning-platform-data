# Cache dependency nhưng không dùng snippet cũ

## 1. Phân biệt dependency cache và generated output

CI có thể cache dependency để giảm thời gian tải thư viện Gradle/Maven ở các lần build tiếp theo. Tuy nhiên, snippet do Spring REST Docs sinh ra là **output của test tại commit hiện tại**. Nếu cache và restore snippet từ build trước, tài liệu có thể chứa request/response không còn khớp với mã nguồn hiện tại.

| Dữ liệu | Ví dụ | Có nên cache giữa các build? |
| --- | --- | --- |
| Dependency cache | Gradle module cache, Maven local repository | Có, với cache key phù hợp |
| Build tool wrapper | Gradle Wrapper distribution, Maven Wrapper | Có thể cache/tái sử dụng |
| Generated snippets | build/generated-snippets, target/generated-snippets | Không nên restore như cache |
| Rendered docs | build/docs, target/generated-docs | Không dùng làm input cache cho build mới |
| Test reports | JUnit XML, HTML report | Lưu thành CI artifact; không dùng thay kết quả test mới |

Trong module **SPRING_REST_DOCS**, MockMvc, WebTestClient hoặc REST Assured sinh snippet từ request/response test. Asciidoctor/Markdown dùng snippet để tạo tài liệu và CI đưa tài liệu vào artifact phát hành. Mỗi build cần tạo snippet từ test của chính commit đang build; dependency cache chỉ giúp tải thư viện nhanh hơn.

## 2. Vì sao cache snippet gây tài liệu lỗi thời?

Giả sử commit A có test:

~~~java
mockMvc.perform(get("/orders/42"))
    .andDo(document("orders/get"));
~~~

Snippet được tạo:

~~~text
build/generated-snippets/orders/get/
├── http-request.adoc
└── http-response.adoc
~~~

Ở commit B, endpoint đổi thành /v2/orders/42, header hoặc response schema cũng thay đổi. Nếu CI restore build/generated-snippets của commit A và test B bị skip, lỗi hoặc không ghi đè đầy đủ, Asciidoctor có thể include snippet cũ.

Build tài liệu vẫn có thể thành công nhưng không mô tả API của commit B. Dependency JAR là đầu vào có version/checksum; snippet là kết quả kiểm thử phụ thuộc source, fixture, cấu hình và môi trường chạy.

Nguyên tắc:

- Cache dữ liệu tải về có thể tái sử dụng, như dependency.
- Sinh lại dữ liệu phụ thuộc source trong mỗi build, như REST Docs snippets.
- Chỉ render tài liệu sau khi test tạo snippet thành công.
- Không dùng cache restore để thay thế documentation test.

## 3. Gradle: cache dependency, không cache build output

Gradle dependency cache thường nằm trong Gradle User Home:

~~~text
~/.gradle/caches/modules-2/
~~~

Build output của project thường nằm tại:

~~~text
project/build/
├── classes/
├── reports/
├── generated-snippets/
└── docs/
~~~

Cache Gradle giữ artifact dependency và metadata đã tải; build/ chứa kết quả của build hiện tại.

Trong GitHub Actions, có thể dùng action setup Gradle để cache wrapper và dependency:

~~~yaml
name: Verify API documentation

on:
  pull_request:
  push:
    branches: [main]

jobs:
  docs:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '21'
      - uses: gradle/actions/setup-gradle@v4
      - name: Build and verify documentation
        run: ./gradlew clean test asciidoctor
~~~

setup-gradle quản lý cache Gradle User Home. Lệnh clean xóa build output của workspace trước khi test và render. Không thêm build/generated-snippets vào danh sách path cache riêng.

### 3.1. Nếu tự cấu hình actions/cache

Chỉ chọn dependency cache và wrapper, không chọn toàn bộ project build directory:

~~~yaml
- name: Cache Gradle dependencies
  uses: actions/cache@v4
  with:
    path: |
      ~/.gradle/caches/modules-2
      ~/.gradle/wrapper
    key: gradle-linux-dependencies
~~~

Ví dụ key trên chỉ minh họa; trong dự án thật, key nên bao gồm hệ điều hành và hash các file quản lý dependency như build.gradle, settings.gradle, gradle-wrapper.properties và version catalog. Ưu tiên action setup Gradle chính thức nếu không có yêu cầu cache đặc biệt.

Không cache:

~~~yaml
path: |
  ~/.gradle/caches
  build/
~~~

vì build/ chứa snippets, HTML, class và output khác của build trước. Nếu cache một thư mục output chung, rất dễ restore nhầm dữ liệu đã sinh.

## 4. Maven: cache local repository, không cache target

Maven tải dependency và plugin vào local repository, thường là:

~~~text
~/.m2/repository/
~~~

Output Maven project thường ở:

~~~text
project/target/
├── classes/
├── surefire-reports/
├── generated-snippets/
└── generated-docs/
~~~

Trong CI, cache ~/.m2/repository giúp giảm thời gian tải dependency/plugin. Không cache target/ vì thư mục này chứa kết quả test và snippet của build trước.

Ví dụ GitHub Actions:

~~~yaml
- uses: actions/setup-java@v4
  with:
    distribution: temurin
    java-version: '21'
    cache: maven

- name: Verify API documentation
  run: mvn -B clean verify
~~~

cache: maven dùng cache dependency Maven theo cơ chế của setup-java. mvn -B clean verify làm mới target rồi chạy test, sinh snippet và render tài liệu theo lifecycle đã cấu hình.

Không cấu hình cache path:

~~~yaml
path: |
  ~/.m2/repository
  target/
~~~

vì target/ không phải dependency cache. Đặc biệt, không restore target/generated-snippets từ một build khác.

## 5. Cache key và restore key

Cache key nên phản ánh những đầu vào quyết định dependency:

- Hệ điều hành/runner nếu cache có thành phần phụ thuộc nền tảng.
- Wrapper version.
- File build như build.gradle, settings.gradle, gradle/libs.versions.toml.
- pom.xml, parent POM hoặc file quản lý version Maven.
- JDK nếu cache/toolchain phụ thuộc phiên bản Java.

Restore key dạng prefix có thể giúp tái sử dụng cache gần nhất khi file build thay đổi. Build tool vẫn kiểm tra dependency và tải phần còn thiếu theo metadata/version. Restore key chỉ dành cho dependency cache, không dùng để khôi phục snippets.

Không đưa hash của test hoặc document identifier vào dependency cache key với mục đích cache snippets. Test vẫn phải chạy để kiểm chứng hành vi hiện tại.

## 6. Bảo đảm snippet được sinh mới trong mỗi build

Pipeline đúng thứ tự:

~~~text
Checkout commit
      |
      v
Restore dependency cache
      |
      v
Clean project output
      |
      v
Run documentation tests
      |
      v
Generate snippets
      |
      v
Render Asciidoctor
      |
      v
Verify rendered docs
      |
      v
Upload release artifact
~~~

Gradle:

~~~bash
./gradlew clean test asciidoctor
~~~

Maven:

~~~bash
mvn -B clean verify
~~~

Nếu build tách test thường và documentation test thành các task/profile riêng, hãy bảo đảm task/profile tạo snippet luôn được gọi trước Asciidoctor. Không dùng -x test, -DskipTests hoặc maven.test.skip=true trong job tạo tài liệu nếu các test bị bỏ qua chính là nguồn snippet.

Nếu chỉ muốn bỏ qua test không liên quan, cấu hình test selection rõ ràng nhưng vẫn chạy đầy đủ documentation tests cần thiết. Asciidoctor nên thất bại khi snippet bắt buộc không tồn tại, thay vì lặng lẽ dùng file cũ.

## 7. Xử lý workspace được tái sử dụng

Một số self-hosted runner hoặc CI workspace được giữ lại giữa các job. Dù không cache build/ hoặc target/, file cũ vẫn có thể tồn tại nếu workspace không sạch.

Các biện pháp:

1. Dùng clean trước bước test tạo snippet.
2. Nếu không thể clean toàn bộ, xóa đúng thư mục generated-snippets trước test.
3. Không chạy nhiều job đồng thời trong cùng workspace và cùng output directory.
4. Dùng workspace/job riêng cho mỗi build.
5. Upload artifact sau khi xác minh; không lấy artifact từ workspace cũ.

Gradle có thể tạo task làm sạch riêng:

~~~groovy
def snippetsDir = layout.buildDirectory.dir('generated-snippets')

tasks.register('cleanSnippets', Delete) {
    delete snippetsDir
}
~~~

Sau đó:

~~~bash
./gradlew cleanSnippets test asciidoctor
~~~

Với Maven, dùng mvn clean verify hoặc cấu hình Maven Clean Plugin để xóa riêng thư mục snippet nếu không thể xóa toàn bộ target.

## 8. Không để Asciidoctor âm thầm dùng snippet cũ

Asciidoctor include một đường dẫn tĩnh:

~~~adoc
include::{snippets}/orders/get/http-request.adoc[]
~~~

Nếu file từ build trước còn tồn tại, include vẫn có thể thành công dù test hiện tại không tạo snippet đó. Vì thế chỉ kiểm tra Asciidoctor thành công là chưa đủ.

Các cách tăng độ tin cậy:

- Clean output trước khi chạy documentation tests.
- Đảm bảo test có document(...) và task test là dependency của Asciidoctor.
- Dùng descriptor/field documentation để test thất bại khi request/response thay đổi ngoài hợp đồng.
- Kiểm tra các snippet bắt buộc được tạo trong build hiện tại.
- Không cho phép CI skip documentation tests nhưng vẫn publish docs.

Có thể kiểm tra sự tồn tại của snippet sau test:

~~~bash
test -f build/generated-snippets/orders/get/http-request.adoc
test -f build/generated-snippets/orders/get/http-response.adoc
~~~

Với Maven, thay build/ bằng target/. Những kiểm tra này bổ sung cho test; chúng không thay thế việc kiểm chứng nội dung và status của request/response.

## 9. Cache test result có thể ảnh hưởng việc sinh snippet

Gradle có thể đánh dấu task test up-to-date hoặc dùng build cache nếu input/output cho phép. Nếu output snippets bị xóa bên ngoài nhưng Gradle vẫn xem test up-to-date, test có thể không chạy và snippet không được tạo lại.

Quản lý output đúng:

~~~groovy
def snippetsDir = layout.buildDirectory.dir('generated-snippets')

tasks.named('test') {
    outputs.dir snippetsDir
}
~~~

Khai báo output giúp Gradle theo dõi thư mục snippet cùng task test. Nếu một bước ngoài Gradle xóa output, hãy chạy clean hoặc buộc task test chạy lại theo cơ chế phù hợp. Không dựa vào thư mục snippets còn sót để chứng minh task test đã chạy.

Nếu dùng remote build cache, cân nhắc liệu test task có được cache hay không và output có hoàn toàn tái lập, an toàn để chia sẻ không. Với documentation tests, nhiều nhóm chọn chạy test thật trong CI release để bảo đảm snippet đến từ lần thực thi của commit hiện tại.

## 10. Sự cố thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Docs hiển thị endpoint cũ | Restore snippets từ cache hoặc workspace cũ | Bỏ cache build output, clean trước test |
| Asciidoctor thành công dù documentation test bị skip | Snippet cũ còn tồn tại | Clean output và bắt buộc chạy documentation tests |
| Gradle test báo UP-TO-DATE nhưng snippet thiếu | Output bị xóa ngoài Gradle hoặc khai báo output chưa đúng | Khai báo outputs.dir, clean hoặc rerun test |
| Maven dùng snippet từ lần build trước | Cache/restore target/ hoặc không chạy clean | Chỉ cache .m2/repository, chạy mvn clean verify |
| CI cache miss liên tục | Key thay đổi quá thường xuyên hoặc hash file chưa phù hợp | Hash file quản lý dependency và dùng restore prefix |
| Cache quá lớn | Cache cả build output hoặc cache không giới hạn | Chỉ cache dependency/wrapper; xem lại retention |
| Job song song ghi chung snippets | Dùng chung workspace/output root | Cô lập workspace và output directory |
| Artifact phát hành chứa snippet lỗi thời | Package lấy output trước khi test/render hoàn tất | Nối dependency đúng và kiểm tra snippet hiện tại |

## 11. Bài tập thực hành

Thiết lập CI cho một Spring REST Docs project với Gradle hoặc Maven:

1. Cấu hình cache dependency: Gradle User Home hoặc Maven local repository.
2. Không đưa build/, target/, generated-snippets/ hoặc rendered docs vào dependency cache.
3. Chạy clean build và documentation tests.
4. Xác nhận snippet được sinh lại ở output directory của build hiện tại.
5. Chạy Asciidoctor và kiểm tra HTML.
6. Thử thay đổi request/response fixture, chạy lại CI và xác nhận snippet phản ánh thay đổi.
7. Thử bỏ qua documentation test trong một build kiểm soát; xác nhận pipeline tạo tài liệu không thể dùng snippet cũ để báo thành công.
8. Upload artifact chỉ sau khi test, render và kiểm tra nội dung thành công.

**Tiêu chí hoàn thành:** Dependency cache giúp build nhanh hơn; snippet luôn được sinh từ test hiện tại; Asciidoctor không sử dụng output cũ; artifact được upload chỉ sau khi toàn bộ bước kiểm chứng thành công.

## Tài liệu tham khảo

- [Gradle User Manual — Dependency Caching](https://docs.gradle.org/current/userguide/dependency_caching.html)
- [Gradle User Manual — Build Cache](https://docs.gradle.org/current/userguide/build_cache.html)
- [Gradle User Manual — Testing in Java & JVM Projects](https://docs.gradle.org/current/userguide/java_testing.html)
- [Apache Maven — Local Repository](https://maven.apache.org/guides/mini/guide-configuring-maven.html)
- [Apache Maven Clean Plugin](https://maven.apache.org/plugins/maven-clean-plugin/)
- [GitHub Actions — Dependency Caching](https://docs.github.com/en/actions/using-workflows/caching-dependencies-to-speed-up-workflows)
