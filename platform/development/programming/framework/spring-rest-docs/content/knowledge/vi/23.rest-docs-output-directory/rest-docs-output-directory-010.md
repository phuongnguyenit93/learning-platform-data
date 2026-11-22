# Quản lý output không thuộc source code

## 1. Phân biệt mã nguồn và output được sinh

Spring REST Docs tạo **snippet** khi test HTTP chạy. Các tệp như `http-request.adoc`, `http-response.adoc`, `request-fields.adoc` và `curl-request.adoc` là kết quả được sinh tự động, không phải mã nguồn cần chỉnh sửa thủ công.

Trong dự án Gradle, output thường nằm dưới `build/generated-snippets/`; với Maven, thường là `target/generated-snippets/`. Cả hai đều nằm trong build directory do build tool quản lý. Tài liệu AsciiDoc do nhóm viết, test và cấu hình build mới là những đầu vào cần duy trì.

| Nội dung | Vị trí thường dùng | Cách quản lý |
| --- | --- | --- |
| Java/Kotlin test | `src/test/...` | Version control |
| AsciiDoc nguồn | `src/docs/asciidoc/` | Version control |
| Cấu hình Gradle/Maven | `build.gradle`, `pom.xml` | Version control |
| Snippet sinh từ test | `build/generated-snippets/` hoặc `target/generated-snippets/` | Build output |
| HTML/PDF đã render | `build/docs/...` hoặc `target/generated-docs/` | Build/release artifact |
| Log và file tạm | `build/`, `target/` | Build output |

Trong module **SPRING_REST_DOCS**, test HTTP bằng MockMvc, WebTestClient hoặc REST Assured tạo snippet; Asciidoctor/Markdown kết hợp snippet thành tài liệu; CI có thể đóng gói tài liệu theo version API. Quản lý đúng ranh giới source/output giúp repository gọn, build tái lập và tránh đưa nhầm kết quả của máy developer vào pull request.

## 2. Vì sao không nên chỉnh sửa snippet trực tiếp?

Giả sử một test tạo:

~~~text
build/generated-snippets/
└── orders/
    └── get-one/
        ├── http-request.adoc
        ├── http-response.adoc
        └── response-fields.adoc
~~~

Nếu mở `http-request.adoc` và sửa nội dung bằng tay, lần chạy test tiếp theo có thể ghi đè thay đổi. Khi request thực tế thay đổi, bản sửa thủ công cũng có thể che giấu việc test và tài liệu không còn khớp nhau.

Quy tắc thực hành:

- Muốn sửa ví dụ request/response, hãy sửa test fixture hoặc request được gửi trong test.
- Muốn sửa mô tả field, hãy sửa descriptor trong `requestFields(...)`, `responseFields(...)`, `requestParameters(...)` hoặc operation tương ứng.
- Muốn đổi định dạng snippet, hãy cấu hình snippet template/operation của Spring REST Docs.
- Muốn sửa cách trình bày, hãy chỉnh AsciiDoc nguồn và cấu hình Asciidoctor.
- Không sửa trực tiếp tệp generated snippet để tạo ra một kết quả chỉ tồn tại trên máy cá nhân.

Snippet là bằng chứng được test sinh ra. Khi thay đổi nguồn dữ liệu, hãy chạy lại test để kết quả mới được tạo.

## 3. Đưa build output vào .gitignore

Với Gradle, `build/` thường đã được ignore trong `.gitignore` của dự án. Với Maven, `target/` cũng thường được ignore. Nếu repository chưa có quy tắc tương ứng, bổ sung:

~~~gitignore
# Gradle build output
/build/

# Maven build output
/target/
~~~

Nếu dự án có nhiều module và mỗi module có build directory riêng, quy tắc ignore cần phù hợp với vị trí `.gitignore`. Một file `.gitignore` ở repository root có thể áp dụng cho thư mục con; các quy tắc có dấu `/` đầu/cuối cần được hiểu theo vị trí file `.gitignore` chứa chúng.

Có thể ignore riêng snippet nếu dự án cố ý lưu một phần khác trong build directory:

~~~gitignore
/build/generated-snippets/
/target/generated-snippets/
~~~

Tuy nhiên, nếu toàn bộ `build/` hoặc `target/` đã được ignore thì không cần thêm quy tắc con. Tránh thêm nhiều dòng trùng lặp khiến chính sách repository khó đọc.

### 3.1. Kiểm tra file đã được Git theo dõi

`.gitignore` chỉ ngăn Git thêm file chưa được theo dõi. Nó không tự ngừng theo dõi file đã commit trước đó.

Kiểm tra:

~~~bash
git status --short
git ls-files build/generated-snippets target/generated-snippets
~~~

Nếu snippet đã được track và nhóm quyết định chuyển chúng thành build output, cần thực hiện thay đổi tracking có chủ đích trong pull request. Ví dụ bỏ file khỏi index nhưng giữ file local:

~~~bash
git rm -r --cached build/generated-snippets
git rm -r --cached target/generated-snippets
~~~

Chỉ chạy lệnh cho đường dẫn thực sự đang được Git theo dõi và sau khi đã xem diff. `--cached` bỏ file khỏi index; nó không xóa file khỏi working tree. Không dùng lệnh này như thao tác dọn dẹp mặc định cho mọi build.

## 4. Làm sạch output bằng build tool

### 4.1. Gradle

Gradle có task `clean` để xóa build directory:

~~~bash
./gradlew clean
~~~

Sau đó chạy test và render tài liệu:

~~~bash
./gradlew test asciidoctor
~~~

Hoặc chạy một build đầy đủ:

~~~bash
./gradlew clean build
~~~

Nếu `asciidoctor` phụ thuộc vào `test`, task graph sẽ bảo đảm test chạy trước bước render. Cấu hình output/input đúng giúp Gradle nhận biết `generated-snippets` là output của test và input của Asciidoctor.

`clean` xóa cả build output khác như class đã compile, report và tài liệu đã render. Vì vậy chỉ dùng khi muốn build lại sạch; không dùng nếu đang cần giữ một artifact chưa được sao lưu ở trong `build/`.

### 4.2. Maven

Maven dùng `clean` để xóa thư mục `target/`:

~~~bash
mvn clean
~~~

Chạy lifecycle tạo test snippet và tài liệu:

~~~bash
mvn clean verify
~~~

Nếu Asciidoctor được gắn ở phase sau `test`, `verify` sẽ đi qua phase đó theo lifecycle chuẩn. Chạy riêng `mvn test` có thể chỉ tạo snippet mà chưa render tài liệu, tùy phase đã cấu hình.

### 4.3. Chỉ xóa một thư mục output

Đôi khi muốn làm mới snippet mà không xóa toàn bộ build output. Có thể tạo task Gradle riêng:

~~~groovy
def snippetsDir = layout.buildDirectory.dir('generated-snippets')

tasks.register('cleanSnippets', Delete) {
    delete snippetsDir
}

tasks.named('test') {
    outputs.dir snippetsDir
}
~~~

Sau đó:

~~~bash
./gradlew cleanSnippets test asciidoctor
~~~

Với Maven, có thể dùng Maven Clean Plugin cấu hình fileset cụ thể hoặc xóa thư mục snippet trong một bước build được quản lý. Tránh tự viết script xóa đường dẫn quá rộng như `build/**` hoặc `target/**` nếu mục tiêu chỉ là làm mới snippet.

## 5. Giữ tài liệu nguồn ngoài build directory

Một cấu trúc dễ duy trì:

~~~text
project/
├── src/
│   ├── main/
│   ├── test/
│   └── docs/
│       └── asciidoc/
│           ├── index.adoc
│           └── resources/
├── build.gradle
├── .gitignore
└── build/
    ├── generated-snippets/
    └── docs/
        └── asciidoc/
~~~

`src/docs/asciidoc/` chứa nội dung do nhóm viết và được version control. `build/generated-snippets/` chứa nội dung test sinh. `build/docs/` chứa HTML/PDF được render.

Không đặt AsciiDoc nguồn duy nhất bên trong `build/` hoặc `target/`, vì lệnh clean sẽ xóa chúng. Nếu nhóm có thư mục docs riêng ngoài `src/`, hãy bảo đảm build cấu hình `sourceDirectory` trỏ đúng nơi và thư mục đó được quản lý trong Git.

## 6. Khi nào cần lưu artifact bên ngoài source tree?

Một số quy trình cần giữ output sau khi build kết thúc:

- CI upload HTML/PDF làm artifact của job.
- Release pipeline publish ZIP tài liệu cùng version ứng dụng.
- Một module docs khác cần tải snippets của module API.
- Nhóm QA lưu báo cáo hoặc tài liệu để review.

Trong các trường hợp đó, build vẫn nên tạo output ở vị trí có thể tái lập; sau khi kiểm tra thành công, CI hoặc bước packaging copy/attach artifact sang nơi lưu trữ phù hợp.

Ví dụ Gradle tạo ZIP tài liệu:

~~~groovy
def renderedDocs = layout.buildDirectory.dir('docs/asciidoc')

tasks.register('apiDocsZip', Zip) {
    dependsOn tasks.named('asciidoctor')
    from(renderedDocs)
    archiveClassifier = 'api-docs'
    destinationDirectory = layout.buildDirectory.dir('distributions')
}
~~~

Ví dụ Maven Assembly đóng gói thư mục HTML đã render:

~~~xml
<fileSet>
    <directory>${project.build.directory}/generated-docs</directory>
    <outputDirectory>/</outputDirectory>
</fileSet>
~~~

Artifact được upload lên CI artifact store, package registry hoặc release repository theo chính sách dự án. Không cần chuyển snippet hoặc HTML ngược vào `src/` chỉ để chúng tồn tại sau build.

## 7. Quản lý output trong CI

CI thường dùng workspace tạm hoặc workspace được tái sử dụng. Nếu workspace được tái sử dụng, snippet cũ có thể còn lại khi test hoặc document identifier bị xóa. Một clean build giúp loại bỏ dữ liệu cũ trước khi sinh tài liệu mới.

Pipeline tham khảo:

~~~text
Checkout source
      |
      v
Clean build output
      |
      v
Run documentation tests
      |
      v
Generate snippets
      |
      v
Render HTML/PDF
      |
      v
Verify documentation
      |
      v
Upload release artifact
~~~

Gradle:

~~~bash
./gradlew clean test asciidoctor apiDocsZip
~~~

Maven:

~~~bash
mvn clean verify
~~~

Nếu Maven đóng gói docs ở phase `package`, dùng `mvn clean package` hoặc phase muộn hơn. Nếu Gradle ZIP docs là task riêng, thêm task đó vào lệnh CI phát hành.

### 7.1. Kiểm tra trước khi upload

Trước khi upload artifact, xác nhận:

1. Test tài liệu hóa đã chạy thành công.
2. Snippet cần thiết được tạo trong output directory hiện tại.
3. Asciidoctor không dùng snippet cũ từ workspace trước.
4. HTML/PDF có đủ trang và tài nguyên.
5. Artifact mang đúng version/commit.
6. Không có log, secret, file tạm hoặc dữ liệu môi trường không dành cho người nhận.

Giữ output của build và artifact đã publish là hai việc riêng. Workspace có thể bị xóa sau job; artifact cần được lưu trong hệ thống CI/release có version và quyền truy cập phù hợp.

## 8. Multi-module và nhiều output directory

Trong dự án nhiều module, mỗi module thường có build directory riêng:

~~~text
repository/
├── orders-api/
│   └── build/generated-snippets/
├── customers-api/
│   └── build/generated-snippets/
└── docs-site/
    └── src/docs/asciidoc/
~~~

Đây là cách tách output tự nhiên: test của `orders-api` và `customers-api` không ghi đè snippet của nhau. Module `docs-site` có thể lấy artifact snippets đã publish hoặc dùng một bước copy/assemble có dependency rõ ràng.

Không để hai module ghi vào cùng một thư mục chia sẻ nếu chúng có identifier trùng nhau hoặc có thể chạy song song. Nếu cần một root tổng hợp, hãy dùng task riêng để copy output từ từng module vào namespace tương ứng:

~~~text
build/all-snippets/
├── orders/
└── customers/
~~~

Đường dẫn copy phải ổn định và được khai báo là output của task tổng hợp. Không copy bằng thao tác thủ công sau mỗi lần chạy test.

## 9. Ngoại lệ: khi nào generated output có thể được commit?

Thông thường, không commit `build/generated-snippets/` hoặc `target/generated-snippets/`. Tuy nhiên, một repository có thể chủ động version control artifact đã render nếu có lý do vận hành, chẳng hạn website docs được host trực tiếp từ branch tĩnh hoặc hệ thống phát hành không có bước build tại nơi deploy.

Nếu chọn cách này:

- Chỉ commit loại output cần deploy, không nhất thiết commit toàn bộ snippet trung gian.
- Ghi rõ quy trình tái tạo output từ test và tài liệu nguồn.
- CI phải kiểm tra output đã commit có đồng bộ với build hiện tại.
- Pull request cần thể hiện diff output để reviewer kiểm tra.
- Không chỉnh tay output đã sinh mà không sửa nguồn tương ứng.

Đây là quyết định của quy trình repository, không phải yêu cầu mặc định của Spring REST Docs. Dù commit hay không, nguồn có thể tái tạo vẫn phải là test, descriptor và tài liệu AsciiDoc.

## 10. Sự cố thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Snippet xuất hiện trong git status | Build directory chưa được ignore hoặc file đã được track | Kiểm tra .gitignore và git ls-files |
| Sửa snippet nhưng thay đổi biến mất | Test chạy lại đã ghi đè output | Sửa test/descriptor rồi sinh snippet mới |
| Tài liệu chứa ví dụ cũ | Workspace giữ output từ lần build trước | Chạy clean build và kiểm tra include |
| Clean làm mất tài liệu nguồn | Đặt source dưới build/ hoặc target/ | Chuyển nguồn sang src/docs hoặc thư mục được version control |
| CI không lưu được HTML | Chưa cấu hình upload artifact hoặc sai output path | Kiểm tra task render và artifact path |
| Module docs thiếu snippet | Output nằm trong build directory module khác | Thêm dependency và bước chia sẻ/copy artifact |
| Hai module ghi đè nhau | Dùng chung output root và identifier | Tách output root hoặc namespace theo module |
| Artifact chứa file thừa | Đóng gói cả build directory thay vì thư mục docs | Chỉ chọn thư mục HTML/PDF cần phát hành |

## 11. Bài tập thực hành

Trong một Gradle hoặc Maven project có Spring REST Docs:

1. Cấu hình test sinh snippet vào build/generated-snippets hoặc target/generated-snippets.
2. Kiểm tra .gitignore để bảo đảm output không bị thêm vào source control.
3. Tạo AsciiDoc nguồn trong src/docs/asciidoc/ và include snippet.
4. Chạy clean build, xác nhận snippet được sinh lại và tài liệu render thành công.
5. Tạo ZIP chỉ chứa HTML đã render, không chứa toàn bộ build directory.
6. Upload ZIP như artifact của CI hoặc lưu vào release staging.
7. Thử xóa một test/document identifier rồi clean build; xác nhận snippet cũ không còn trong artifact mới.
8. Kiểm tra git status sau build để bảo đảm source tree không có generated output ngoài dự kiến.

**Tiêu chí hoàn thành:** Source và generated output được tách rõ; snippet không bị chỉnh tay hoặc commit ngoài chủ đích; clean build tái tạo tài liệu; CI lưu đúng artifact đã kiểm chứng.

## Tài liệu tham khảo

- [Spring REST Docs — Getting Started](https://docs.spring.io/spring-restdocs/tutorial/getting-started/index.html)
- [Spring REST Docs — Documenting Your API](https://docs.spring.io/spring-restdocs/reference/documenting-your-api.html)
- [Gradle User Manual — The Build Directory](https://docs.gradle.org/current/userguide/organizing_gradle_projects.html)
- [Gradle User Manual — Clean Task](https://docs.gradle.org/current/userguide/base_plugin.html)
- [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Apache Maven Clean Plugin](https://maven.apache.org/plugins/maven-clean-plugin/)
