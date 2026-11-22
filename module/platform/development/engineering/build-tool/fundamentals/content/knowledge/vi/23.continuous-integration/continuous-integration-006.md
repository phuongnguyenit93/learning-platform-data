# Phân biệt cache tăng tốc với artifact đầu ra cần bàn giao

Trong CI, cache và artifact đều có thể chứa file được tạo ra trong quá trình build. Vì vậy, hai khái niệm này thường bị dùng lẫn nhau. Tuy nhiên, mục đích của chúng khác nhau:

- **Cache** giúp giảm công việc lặp lại. Build có thể tái sử dụng dependency đã tải hoặc output task đã tạo nếu điều kiện phù hợp.
- **Artifact bàn giao** là đầu ra mà một job, stage, pipeline hoặc người dùng cần nhận được để thực hiện bước tiếp theo, kiểm thử, triển khai, phát hành hoặc lưu trữ.

Ví dụ, Gradle có thể cache output của task biên dịch để build sau không phải biên dịch lại. Nhưng file JAR cần được chuyển từ job build sang job integration test hoặc release phải được đóng gói và upload như artifact của pipeline. Việc file từng xuất hiện trong cache không bảo đảm job sau có thể tải đúng file đó.

Trong một pipeline đáng tin cậy, cache là cơ chế tối ưu hiệu năng; artifact là cơ chế trao đổi và bàn giao kết quả.

## 1. Phân biệt qua mục đích sử dụng

Hãy bắt đầu bằng câu hỏi: file này được lưu để làm gì?

Nếu mục tiêu là tránh tính toán hoặc tải dependency lặp lại, đó là cache. Nếu mục tiêu là chuyển một kết quả cụ thể đến job khác, giữ kết quả của lần chạy để tải xuống, hoặc phát hành cho người dùng, đó là artifact.

| Tiêu chí | Cache tăng tốc | Artifact bàn giao |
|---|---|---|
| Mục tiêu | Tiết kiệm thời gian và tài nguyên | Chuyển giao hoặc lưu giữ đầu ra cụ thể |
| Dữ liệu thường gặp | Dependency, task output có thể tái tạo, dữ liệu trung gian | JAR, WAR, ZIP, installer, report, package, file triển khai |
| Cách định danh | Cache key/fingerprint từ input và cấu hình | Tên artifact, build/run ID, version, commit hoặc release |
| Khi không có dữ liệu | Tính toán/tải lại từ nguồn | Pipeline phải tạo hoặc lấy artifact từ nơi lưu trữ |
| Vòng đời | Có thể bị eviction, expire hoặc thay thế | Theo retention và chính sách lưu trữ của pipeline/repository |
| Mục đích downstream | Tăng tốc bước tạo output | Là đầu vào được bàn giao cho bước tiếp theo |
| Tính chất | Có thể tái tạo khi cần | Cần xác định rõ phiên bản và nguồn gốc |
| Ví dụ | Gradle build cache, dependency cache, CI cache | File JAR được upload từ build job để deploy job tải xuống |

Một file có thể là output của task và đồng thời được đưa vào cache. Nhưng điều đó không làm cho cache trở thành kênh bàn giao artifact. Muốn job khác sử dụng file một cách có chủ đích, pipeline cần có bước upload, publish hoặc trao đổi artifact tương ứng.

## 2. Các lớp lưu trữ dễ bị gọi chung là cache

Trong CI dùng Gradle, có ít nhất ba cơ chế lưu trữ thường gặp:

1. **Gradle dependency cache** lưu metadata và dependency artifact đã resolve/tải về.
2. **Gradle build cache** lưu output của task cacheable theo cache key.
3. **CI cache** là tính năng của nền tảng CI để lưu thư mục hoặc dữ liệu giữa các lần chạy job, thường dùng cho Gradle User Home hoặc package manager cache.

Ngoài ba cơ chế đó còn có **CI artifact storage**, nơi lưu file đầu ra của một pipeline run để job khác hoặc người dùng tải về.

| Cơ chế | Ai quản lý? | Ví dụ dữ liệu |
|---|---|---|
| Dependency cache | Gradle | JAR từ Maven repository, module metadata |
| Build cache | Gradle | Output task compile, generated files, archive nếu task cacheable |
| CI cache | Nền tảng CI và cấu hình workflow | Gradle User Home, thư mục cache của công cụ |
| CI artifact | Nền tảng CI và pipeline | JAR/WAR/ZIP, test report, installer, file cấu hình phát hành |

### Dependency cache không phải artifact phát hành

Giả sử Gradle tải thư viện:

~~~groovy
dependencies {
    implementation 'org.example:logging-client:3.1'
}
~~~

JAR của logging-client là dependency mà build tiêu thụ. Nó được lưu trong dependency cache để lần resolve sau có thể tái sử dụng. Nó không phải JAR ứng dụng do project tạo ra và cũng không phải artifact phát hành của ứng dụng.

### Build cache không phải nơi lưu release

Task của project có thể tạo file:

~~~text
app/build/libs/app-1.0.0.jar
~~~

Nếu task tương ứng cacheable, Gradle có thể lưu output vào build cache. Cache entry được dùng khi một task có cache key tương ứng cần khôi phục output. Để chuyển file JAR sang deploy job hoặc cung cấp cho người dùng, pipeline vẫn cần upload artifact hoặc publish vào repository phù hợp.

### CI cache không phải CI artifact

Một workflow có thể cache thư mục Gradle để giảm thời gian tải dependency. Một workflow khác cần file JAR từ job build. Hai mục tiêu này cần hai bước lưu trữ khác nhau: cache để tăng tốc, artifact để bàn giao.

## 3. Luồng dữ liệu trong một pipeline

Một pipeline có thể được hình dung như sau:

~~~text
                    CI pipeline
                         |
                         v
                   Build job
                         |
            +------------+-------------+
            |                          |
            v                          v
     Restore caches              Checkout source
            |                          |
            +-------------+------------+
                          |
                          v
                    Run Gradle
                          |
             +------------+------------+
             |                         |
             v                         v
       Cache task output          Create deliverables
       for reuse later            JAR / ZIP / reports
                                       |
                                       v
                               Upload CI artifacts
                                       |
                       +---------------+---------------+
                       |                               |
                       v                               v
                 Test job                         Deploy job
                 Download JAR                    Download JAR
                       |                               |
                       v                               v
                Run integration tests             Deploy exact build
                       |                               |
                       v                               v
                 Test reports                     Release record
~~~

Cache có thể được khôi phục ở đầu build job và được cập nhật sau khi build. Artifact được tạo sau khi task tạo ra file bàn giao; job downstream tải đúng artifact của run hoặc release mà nó phụ thuộc.

Nếu test job chỉ cần source code và tự build lại, nó có thể chạy Gradle độc lập và dùng cache. Nếu test job phải kiểm thử đúng JAR đã được build ở job trước, nó cần tải JAR artifact đó. Hai cách có ý nghĩa khác nhau.

## 4. Artifact là gì trong bối cảnh CI?

Trong CI, **artifact** thường là file hoặc thư mục được một job tạo ra và nền tảng CI lưu lại gắn với một pipeline run, workflow run hoặc build number.

Ví dụ:

- JAR/WAR do Gradle tạo.
- ZIP/TAR chứa distribution.
- Native executable hoặc installer.
- Test report HTML/XML.
- Coverage report.
- SBOM hoặc checksum file.
- Package đã được ký.
- File metadata mô tả commit, version và build.

Artifact có thể được:

- Download bởi job khác trong cùng pipeline.
- Tải về bởi developer hoặc QA.
- Đưa vào bước deploy.
- Lưu giữ làm bằng chứng của release.
- Đính kèm vào release record.
- Chuyển sang hệ thống publish hoặc phân phối khác.

Artifact thường được định danh bằng tên và thông tin run/build. Ví dụ:

~~~text
artifact: app-package
run: 1842
commit: 8f31c2a
files:
  - app-1.0.0.jar
  - checksums.txt
  - build-info.json
~~~

Cấu trúc minh họa này cho thấy artifact có nguồn gốc và danh sách file cụ thể. Tên artifact và metadata cần được thiết kế để người nhận biết chính xác họ đang tải kết quả nào.

## 5. Tạo output có thể bàn giao bằng Gradle

Gradle task tạo output trong project thường ghi vào thư mục build của project. Ví dụ Java plugin tạo JAR:

~~~groovy
plugins {
    id 'java'
}

group = 'com.example'
version = '1.0.0'
~~~

Chạy:

~~~shell
./gradlew :app:jar
~~~

Output thường nằm dưới:

~~~text
app/build/libs/
~~~

Nếu dùng Spring Boot plugin, task tạo executable archive thường là bootJar. Với application plugin, có thể có distribution ZIP/TAR. Tên task và output phụ thuộc plugin và cấu hình thực tế.

Các task phổ biến:

| Task | Output thường gặp |
|---|---|
| jar | JAR thư viện/application |
| war | WAR |
| bootJar | Executable Spring Boot JAR |
| distZip | ZIP distribution |
| distTar | TAR distribution |
| test | Test result và report |
| jacocoTestReport | Coverage report nếu JaCoCo được cấu hình |
| assemble | Các artifact cần assemble theo plugin |
| build | Các task kiểm tra và assemble theo lifecycle của plugin |

Không nên giả định mọi project đều tạo cùng tên file hoặc cùng task. Hãy xem task và archive configuration của project.

### Tạo output có tên/version ổn định

Ví dụ cấu hình JAR:

~~~groovy
tasks.named('jar', Jar) {
    archiveBaseName = 'orders-service'
    archiveVersion = project.version.toString()
    archiveClassifier = ''
}
~~~

Với cấu hình này, tên archive dựa trên project version và archive properties. Khi release, version nên phản ánh phiên bản được phát hành. Không nên để job deploy đoán tên file từ một pattern mơ hồ nếu build có thể tạo nhiều archive.

### Hai ranh giới bàn giao khác nhau

Nếu một task Gradle cần output của task khác, nối output provider vào input. Nếu một job CI cần file sau khi job build kết thúc, dùng artifact upload/download của nền tảng CI.

- Trong cùng Gradle build: task input/output provider và task graph.
- Giữa CI jobs/runs: CI artifact storage và dependency giữa jobs.

## 6. Upload artifact sau khi build

Sau khi Gradle tạo output, pipeline cần chỉ rõ file nào sẽ được lưu như artifact.

Ví dụ cấu trúc workflow tổng quát:

~~~yaml
jobs:
  build:
    steps:
      - checkout-source
      - restore-gradle-cache
      - run: ./gradlew :app:clean :app:assemble
      - upload-artifact:
          name: app-package
          path: app/build/libs/*.jar
          retention: 14 days
~~~

Đây là pseudocode mô tả luồng, không phải cú pháp dùng chung cho mọi CI provider. Tên action, cách khai báo path, retention và quyền truy cập phụ thuộc nền tảng CI.

Điểm quan trọng là upload phải trỏ đến output thực tế của build. Nếu task tạo file ở vị trí khác, pattern phải thay đổi theo cấu hình. Nếu glob khớp nhiều file, cần xác định có chủ đích những file nào được bàn giao.

### Chỉ upload file cần cho bước tiếp theo

Không nhất thiết upload toàn bộ thư mục build. Thư mục build có thể chứa:

- Class file và generated source.
- Temporary file.
- Intermediate output.
- Cache/local state.
- Test result.
- Nhiều archive hoặc bản output không phải deliverable.

Hãy chọn rõ deliverable và report cần giữ. Artifact nhỏ, rõ tên và có metadata sẽ dễ kiểm soát hơn.

Ví dụ một artifact release:

~~~text
release-package/
  orders-service-1.0.0.jar
  checksums.sha256
  build-info.json
~~~

Một artifact test evidence có thể tách riêng:

~~~text
test-evidence/
  test-results/
  test-report/
  coverage/
~~~

Tách package phát hành và bằng chứng kiểm thử giúp downstream job và người xem hiểu mục đích từng artifact.

## 7. Download và sử dụng artifact ở job downstream

Một job downstream cần khai báo quan hệ phụ thuộc với job tạo artifact và tải artifact tương ứng.

Ví dụ luồng tổng quát:

~~~yaml
jobs:
  build:
    steps:
      - run: ./gradlew :app:assemble
      - upload-artifact:
          name: app-package
          path: app/build/libs/app.jar

  integration-test:
    needs: build
    steps:
      - download-artifact:
          name: app-package
      - run: run-integration-tests-against-downloaded-app

  deploy:
    needs: integration-test
    steps:
      - download-artifact:
          name: app-package
      - run: deploy-downloaded-app
~~~

Đây là pseudocode; cần dùng cú pháp đúng theo CI provider. Job integration test và deploy tải artifact đã được build, nên chúng có thể kiểm thử và triển khai cùng một binary.

### Vì sao nên deploy đúng artifact đã test?

Nếu integration test job tự build lại, có thể tạo ra binary khác với binary được build job tạo ra do:

- Dependency hoặc version động thay đổi.
- Environment hoặc build property khác.
- Toolchain khác.
- Source checkout khác.
- Build script hoặc generated input thay đổi.
- Build chạy ở thời điểm khác và lấy metadata khác.

Khi test và deploy dùng cùng artifact, pipeline có thể chứng minh binary được triển khai chính là binary đã qua các bước kiểm thử trước đó.

Đây là nguyên tắc **artifact promotion**: tạo một lần, xác minh, rồi chuyển cùng một artifact qua các môi trường.

## 8. Cache key và artifact identity giải quyết hai bài toán khác nhau

Cache cần một key để xác định dữ liệu có thể tái sử dụng. Artifact cần identity để người nhận biết chính xác file nào đang được bàn giao.

### Cache key

Cache key thường phản ánh các yếu tố ảnh hưởng đến nội dung cache:

- Hệ điều hành hoặc kiến trúc khi output phụ thuộc môi trường.
- Gradle Wrapper version.
- JDK/toolchain.
- Dependency lockfiles hoặc version catalog.
- Build logic/task implementation.
- Source/input fingerprint theo cơ chế build cache.
- Các option ảnh hưởng output.

Ví dụ key của CI cache dùng để giữ Gradle dependency cache có thể dựa trên OS và lockfile:

~~~text
gradle-dependencies-linux-jdk21-lock-v3
~~~

Ví dụ này chỉ minh họa cách đặt key. Key thực tế phụ thuộc cache action và dữ liệu được cache. Nếu key quá rộng, cache có thể chứa dữ liệu không tương thích; nếu quá hẹp, cache hit giảm.

### Artifact identity

Artifact nên gắn với thông tin có ý nghĩa cho lần build:

~~~text
name: orders-service
version: 1.0.0
commit: 8f31c2a
build-run: 1842
platform: linux-x64
~~~

Không dùng cache key làm version phát hành. Cache key có thể thay đổi vì một yếu tố tối ưu hóa và có thể không duy nhất cho một release. Version và build identity phải được quản lý theo chính sách artifact/release.

| Cache key trả lời | Artifact identity trả lời |
|---|---|
| Có thể tái sử dụng dữ liệu này cho task/input hiện tại không? | Đây là output của build/release nào? |
| Input và cấu hình có tương thích không? | File thuộc commit, version và pipeline run nào? |
| Có cache hit không? | Người nhận có đang dùng đúng binary cần bàn giao không? |

## 9. Cache miss không đồng nghĩa mất artifact

Cache có thể bị xóa, hết hạn hoặc eviction. Nếu cache miss, Gradle hoặc CI phải tính toán/tải lại dữ liệu cần thiết. Điều đó có thể làm build chậm hơn nhưng không nên làm mất deliverable đã được phát hành.

Artifact storage có retention riêng. Nếu artifact bị hết hạn và không được publish vào repository lâu dài, pipeline có thể không còn tải được nó. Vì vậy, release artifact cần được lưu ở nơi có vòng đời phù hợp với chính sách phân phối và audit.

### So sánh vòng đời

| Sự kiện | Cache | Artifact |
|---|---|---|
| Hết hạn/eviction | Có thể bị xóa và tạo lại | Có thể bị xóa theo retention |
| Build lại | Có thể tạo cache entry mới | Có thể tạo artifact mới với run/version mới |
| Dùng lại giữa các job | Chỉ khi key/scope/permission phù hợp | Khi job tải artifact đúng run hoặc release |
| Dùng làm bằng chứng phát hành | Không nên dựa vào cache | Phù hợp nếu lưu giữ và định danh đúng |
| Không tìm thấy | Tính lại hoặc tải dependency lại | Cần build lại hoặc lấy từ repository/archive khác |

Một pipeline tốt không dựa vào việc cache còn tồn tại để giữ file release. Artifact phát hành cần được publish hoặc lưu trong kho có retention phù hợp.

## 10. Cache dependency trong CI

CI cache thường được dùng để giữ Gradle User Home giữa các lần chạy. Ví dụ, workflow có thể cache:

~~~text
GRADLE_USER_HOME/
  caches/
  wrapper/
~~~

Việc này có thể giảm thời gian tải Gradle distribution, dependency metadata và JAR. Tuy nhiên, không phải mọi nội dung trong Gradle User Home đều nên được cache hoặc chia sẻ theo cùng một chính sách. Gradle quản lý cache nội bộ và có thể cần xử lý lock, version hoặc dữ liệu theo người dùng.

### Chọn phần cần cache

Một workflow có thể cache Gradle dependency data và Wrapper distribution dựa trên cache key phù hợp. Tránh đưa output release hoặc toàn bộ workspace vào một cache key chung nếu mục tiêu là bàn giao artifact.

Nếu cache toàn bộ thư mục build, có thể gặp các vấn đề:

- Output cũ bị dùng nhầm.
- File generated phụ thuộc environment bị tái sử dụng không đúng.
- Nhiều job ghi đè hoặc xung đột.
- Cache quá lớn.
- Khó xác định output thuộc commit nào.
- Bỏ qua task graph hoặc task input/output contract của Gradle.

Ưu tiên Gradle build cache cho task output có thể cache; dùng CI cache cho dependency/tool data theo hướng dẫn của nền tảng; dùng CI artifact để bàn giao deliverable.

### Cache key có fallback

Một số CI provider hỗ trợ restore key/prefix. Cách này có thể lấy cache gần nhất nếu key chính xác không tồn tại. Điều đó hữu ích với dependency cache, nhưng cần xem nội dung được restore có an toàn để dùng lại không.

Với artifact release, không dùng fallback cache để tìm “file JAR gần giống”. Release phải lấy đúng artifact gắn với run/version đã được phê duyệt.

## 11. Gradle build cache trong CI

Gradle build cache có thể giúp nhiều CI run dùng lại output task nếu cache key khớp. Bật bằng:

~~~shell
./gradlew build --build-cache
~~~

Hoặc:

~~~properties
org.gradle.caching=true
~~~

Remote build cache có thể được cấu hình trong settings:

~~~groovy
buildCache {
    remote(HttpBuildCache) {
        url = uri('https://cache.example.internal/')
        push = false
    }
}
~~~

Trong ví dụ, build có thể đọc cache từ remote service nhưng không push entry. CI job đáng tin cậy có thể được cấu hình quyền push theo chính sách tổ chức.

### Build cache có thể lưu output của archive task không?

Một task archive có thể cache nếu task type và cấu hình cho phép, output được xác định từ input đã khai báo và cache policy phù hợp. Nhưng ngay cả khi archive output có trong build cache, job release vẫn cần lấy đúng archive và upload/publish nó như deliverable.

Build cache trả lời câu hỏi: “Có thể khôi phục output tương đương cho task này không?” Artifact handoff trả lời: “File nào được giao cho job hoặc người nhận tiếp theo?”

### Không dựa vào cache để tìm đường dẫn release

Nếu deploy job cần file JAR, nó nên nhận file qua artifact download hoặc repository. Nó không nên tìm file trong Gradle cache directory vì đó là implementation detail của cache và không phải contract phát hành.

## 12. Publish artifact vào repository khác với upload CI artifact

Có hai kiểu bàn giao phổ biến:

1. **CI artifact upload**: lưu file gắn với pipeline run để job khác hoặc người dùng tải.
2. **Repository publish**: phát hành package vào Maven/Ivy repository, container registry, package registry hoặc kho phân phối.

Với Gradle Maven Publish plugin:

~~~groovy
plugins {
    id 'maven-publish'
}

publishing {
    publications {
        mavenJava(MavenPublication) {
            from components.java
            groupId = 'com.example'
            artifactId = 'orders-service'
            version = project.version.toString()
        }
    }

    repositories {
        maven {
            url = uri(layout.buildDirectory.dir('repo'))
        }
    }
}
~~~

Ví dụ này publish vào repository cục bộ dưới build directory để minh họa cấu trúc. Trong môi trường thực tế, repository đích và credential phải được cấu hình theo chính sách phát hành.

Publish task thường có side effect lên repository và không nên được xem như task cacheable thông thường. Cache hit không thể thay thế hành động gửi package đến repository đích.

### Chọn nơi lưu theo vòng đời

| Nhu cầu | Nơi phù hợp |
|---|---|
| Job khác trong cùng workflow cần file | CI artifact storage |
| QA cần tải file của một run | CI artifact storage |
| Lưu test report để xem sau | CI artifact storage hoặc report store |
| Phân phối thư viện cho project khác | Maven/Ivy/package repository |
| Phát hành container image | Container registry |
| Lưu binary release lâu dài | Release repository hoặc artifact repository |
| Tăng tốc compile ở nhiều build | Gradle remote build cache |

Không nên dùng CI artifact storage làm kho package lâu dài nếu retention của nền tảng không đáp ứng yêu cầu. Ngược lại, không nên publish mọi file tạm của build vào repository phát hành.

## 13. Bàn giao nhiều loại output

Một build thường tạo nhiều file. Cần phân loại deliverable và evidence:

~~~text
app/build/
  libs/
    app-1.0.0.jar
  reports/
    tests/
      test/
        index.html
  test-results/
    test/
      TEST-*.xml
  distributions/
    app-1.0.0.zip
~~~

Một pipeline có thể tạo hai artifact:

- **app-package**: JAR/ZIP cần cho deploy.
- **test-evidence**: test reports và coverage reports cần cho QA/audit.

Không nên upload toàn bộ build directory một cách mặc định. Hãy xác định file nào downstream thực sự cần, file nào chỉ để chẩn đoán và file nào không cần giữ.

### Đặt tên artifact rõ ràng

Tên artifact nên mô tả nội dung và có thể phân biệt platform/variant khi cần:

~~~text
orders-service-linux-x64
orders-service-windows-x64
test-evidence-unit
test-evidence-integration
release-manifest
~~~

Nếu một pipeline tạo nhiều variant, tên artifact không nên mơ hồ như output hoặc build. Gắn version/commit/run ID trong metadata hoặc artifact name theo khả năng của CI provider.

## 14. Tạo manifest và checksum cho artifact

Artifact cần được nhận diện và xác minh. Có thể tạo file metadata chứa:

- Product/module name.
- Version.
- Commit SHA.
- Pipeline run/build number.
- Build timestamp nếu chính sách cho phép.
- Java/Gradle version.
- Platform/architecture.
- Danh sách file.
- Checksum của từng file.
- Trạng thái test hoặc liên kết report.

Ví dụ build-info JSON:

~~~json
{
  "name": "orders-service",
  "version": "1.0.0",
  "commit": "8f31c2a",
  "buildRun": "1842",
  "gradleVersion": "8.10.2",
  "javaVersion": "21",
  "artifacts": [
    "orders-service-1.0.0.jar"
  ]
}
~~~

Đây là cấu trúc minh họa. Dữ liệu phải được tạo từ nguồn build thực tế; không điền version hoặc commit giả định.

Có thể tạo checksum:

~~~shell
sha256sum orders-service-1.0.0.jar > checksums.sha256
~~~

Trên Windows PowerShell:

~~~powershell
Get-FileHash .\orders-service-1.0.0.jar -Algorithm SHA256
~~~

Checksum giúp xác nhận file tải xuống có cùng nội dung với file đã tạo. Nó không tự chứng minh nguồn gốc đáng tin cậy nếu checksum và artifact cùng bị thay thế; với yêu cầu cao hơn, dùng chữ ký số, attestations hoặc provenance do hệ thống phát hành tạo.

## 15. Artifact promotion: build một lần, kiểm thử rồi triển khai

Một quy trình release đáng tin cậy thường tạo artifact một lần và chuyển artifact đó qua các stage.

~~~text
Source commit
     |
     v
Build once
     |
     v
Create release artifact
     |
     v
Upload artifact + metadata
     |
     v
Unit / integration verification
     |
     v
Approve release
     |
     v
Deploy same artifact to staging
     |
     v
Promote same artifact to production
~~~

Trong mô hình này, môi trường triển khai có thể thay đổi cấu hình runtime, secret hoặc endpoint, nhưng binary được triển khai vẫn là cùng một artifact.

### Vì sao không build lại ở mỗi môi trường?

Nếu build lại cho staging và production, hai môi trường có thể nhận binary khác nhau. Ngay cả cùng commit, build có thể khác do dependency động, toolchain, build property hoặc generated metadata.

Build once rồi promote artifact giúp:

- Kiểm thử đúng binary sẽ triển khai.
- Giữ mối liên hệ giữa commit và release.
- So sánh checksum giữa các môi trường.
- Truy vết khi có sự cố.
- Giảm khả năng build không nhất quán.

Nếu artifact cần cấu hình khác theo môi trường, ưu tiên đưa cấu hình triển khai vào runtime hoặc đóng gói thành cấu hình tách biệt, theo kiến trúc ứng dụng. Tránh rebuild binary chỉ để thay đổi secret hoặc endpoint nếu có thể cấu hình khi chạy.

## 16. Artifact retention và chính sách lưu giữ

CI artifact thường có thời hạn lưu giữ. Thời hạn có thể được đặt theo workflow, project hoặc chính sách tổ chức.

Cần phân biệt:

- Artifact tạm của pull request.
- Artifact phục vụ QA.
- Artifact của nightly build.
- Artifact release candidate.
- Artifact release chính thức.
- Test report/evidence cần lưu để audit.

Ví dụ chính sách:

| Loại | Retention minh họa | Mục đích |
|---|---:|---|
| PR test report | 7 ngày | Debug và review |
| Nightly package | 14 ngày | Kiểm tra định kỳ |
| Release candidate | 30–90 ngày | Kiểm thử và phê duyệt |
| Release chính thức | Theo chính sách sản phẩm | Phân phối và truy vết |
| Cache | Theo cache eviction/retention | Tối ưu hiệu năng |

Các con số chỉ là ví dụ. Cần dùng chính sách thực tế của tổ chức và CI provider. Release artifact có thể cần lưu lâu hơn giới hạn CI artifact; trong trường hợp đó, publish sang artifact repository hoặc release storage.

### Không để cache retention quyết định release retention

Cache có thể bị dọn dẹp bất cứ lúc nào theo chính sách eviction. Artifact release cần được giữ theo cam kết phân phối, audit và khả năng rollback. Hai vòng đời này phải được quản lý độc lập.

## 17. Bảo mật và tin cậy khi dùng cache/artifact

Cache và artifact đều có thể chứa code hoặc dữ liệu được build tiêu thụ ở bước sau. Cần kiểm soát ai có thể ghi và ai có thể tải.

### Remote cache

Nếu job không đáng tin cậy có quyền ghi remote build cache, nó có thể đưa output vào cache mà build đáng tin cậy sau đó khôi phục. Vì vậy:

- Chỉ cho phép nguồn tin cậy push cache dùng chung.
- Giới hạn quyền ghi theo branch/repository.
- Có thể cho pull request chỉ đọc cache.
- Bảo vệ credential và endpoint.
- Phân vùng cache nếu trust boundary khác nhau.
- Không đưa secret vào cacheable task input/output.

### Artifact

Artifact cũng cần kiểm soát:

- Ai được upload.
- Job nào được download.
- Artifact có gắn với run/commit đúng không.
- Có được ký hoặc checksum verify không.
- Artifact có chứa secret, file cấu hình nội bộ hoặc dữ liệu cá nhân không.
- Retention và quyền tải có phù hợp không.
- Artifact có được publish từ branch/tag được phép phát hành không.

Không nên upload toàn bộ workspace vì có thể vô tình chứa file .env, credential, local configuration, debug dump hoặc file tạm.

### Không tin artifact chỉ vì tên của nó

Tên release.zip không chứng minh file thuộc release đúng. Kiểm tra build/run ID, commit, version, checksum và nguồn upload. Với quy trình release có yêu cầu cao, dùng chữ ký và provenance/attestation.

## 18. Cache và artifact trong build nhiều job

Một số pipeline chia build theo matrix hoặc nhiều module:

~~~text
                  Pipeline
                     |
          +----------+----------+
          |                     |
          v                     v
      Build Linux           Build Windows
          |                     |
          v                     v
   linux package          windows package
          |                     |
          +----------+----------+
                     |
                     v
                Aggregate job
                     |
                     v
             Release bundle
~~~

Mỗi matrix job có thể dùng cache chung nếu key và output tương thích. Tuy nhiên, mỗi job tạo artifact riêng theo platform. Aggregate job tải các artifact cụ thể và ghép chúng thành bundle phát hành.

### Không dùng cache để gom kết quả matrix

Cache là kho tái sử dụng theo key, có thể bị ghi đè hoặc có semantics restore khác nhau. Nếu cần gom một file từ mỗi matrix leg, dùng artifact upload/download hoặc cơ chế artifact aggregation của CI provider.

Tên artifact nên bao gồm platform/variant để tránh ghi đè:

~~~text
app-linux-x64
app-windows-x64
app-macos-arm64
~~~

Aggregate job cần biết chính xác artifact nào bắt buộc và xử lý trường hợp một matrix leg thất bại.

## 19. Report cũng là artifact có ích

Test report và coverage report không phải cache tăng tốc. Chúng là bằng chứng của lần chạy test cụ thể.

Ví dụ:

~~~text
app/build/reports/tests/test/index.html
app/build/test-results/test/TEST-*.xml
app/build/reports/jacoco/test/html/index.html
~~~

CI có thể upload các report này ngay cả khi test thất bại, tùy chính sách pipeline. Điều đó giúp reviewer xem kết quả và điều tra lỗi sau khi job kết thúc.

### Giữ report khi job thất bại

Một số nền tảng CI cho phép cấu hình upload artifact ngay cả khi bước trước đó thất bại. Cú pháp khác nhau theo provider. Nên cấu hình có chủ đích để report được lưu khi test fail, nhưng không để trạng thái upload thành công che giấu task test thất bại.

Tách trạng thái:

- Test job status: pass/fail.
- Report artifact upload: success/failure.
- Build package artifact: created/not created.
- Release gate: approved/blocked.

Một report được upload thành công không có nghĩa test đã pass.

## 20. Những lỗi thường gặp khi dùng cache thay cho artifact

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Deploy job không tìm thấy JAR | Chỉ cache Gradle, không upload artifact | Upload JAR và khai báo dependency job |
| Job sau lấy nhầm JAR cũ | Dùng cache key/pattern mơ hồ hoặc file tồn tại từ workspace cũ | Tải artifact theo run/build identity |
| Build nhanh local nhưng CI không có output | Output chỉ có trong workspace local hoặc cache local | Tạo output trong CI và upload artifact |
| Cache hit nhưng release file không xuất hiện | Build cache không phải artifact handoff | Thực hiện archive task rồi upload file |
| Job sau phải build lại | Không có artifact được bàn giao | Upload/download artifact giữa jobs |
| Release không truy vết được commit | Artifact thiếu metadata | Gắn commit, version, run ID và checksum |
| Artifact hết hạn trước khi cần rollback | Retention quá ngắn | Publish release vào kho lưu trữ lâu dài |
| Matrix jobs ghi đè file | Artifact name giống nhau | Đặt tên theo OS/architecture/variant |
| Cache restore làm test dùng dữ liệu cũ | Cache scope/key không phù hợp | Chỉ cache dữ liệu tái tạo được và key theo input |
| File được deploy khác file đã test | Mỗi stage tự build lại | Promote cùng artifact qua các stage |

## 21. Quy trình thiết kế cache và artifact cho một pipeline Gradle

Khi thiết kế pipeline, hãy đi theo các bước:

1. **Liệt kê dữ liệu được tạo**: dependency, intermediate output, JAR/WAR/ZIP, report, checksum và metadata.
2. **Phân loại từng dữ liệu**: cache để tăng tốc, artifact để bàn giao, hay package để publish lâu dài.
3. **Xác định producer**: Gradle task/job nào tạo file.
4. **Xác định consumer**: job, stage, developer hoặc repository nào cần nhận file.
5. **Thiết kế cache key**: phản ánh input và môi trường ảnh hưởng dữ liệu cache.
6. **Thiết kế artifact identity**: tên, version, commit, run ID, platform và checksum.
7. **Cấu hình upload/download**: dùng artifact storage cho file cần chuyển giữa jobs.
8. **Giữ đúng dependency giữa jobs**: job downstream chỉ chạy sau khi artifact producer hoàn tất và đạt điều kiện.
9. **Đặt retention**: cache theo mục tiêu hiệu năng, artifact theo nhu cầu test/release/audit.
10. **Bảo vệ quyền truy cập**: giới hạn quyền push cache và upload artifact.
11. **Promote cùng binary**: test, staging và production nhận cùng artifact nếu quy trình yêu cầu build once.
12. **Kiểm chứng bằng metadata/checksum**: xác nhận file downstream đúng với file đã tạo.

### Ví dụ checklist thiết kế

| Câu hỏi | Quyết định cần có |
|---|---|
| Dependency Gradle được tái sử dụng ở đâu? | Gradle dependency cache/CI cache |
| Task output nào có thể tái sử dụng? | Gradle build cache |
| JAR nào cần deploy? | Artifact name, path, version |
| Job nào tạo JAR? | Build job và Gradle task |
| Job nào nhận JAR? | Test/deploy/release job |
| Làm sao biết đúng build? | Commit SHA, run ID, version |
| Làm sao kiểm tra file không đổi? | SHA-256 hoặc chữ ký |
| Giữ file bao lâu? | CI retention hoặc artifact repository policy |
| Ai được phép ghi cache/artifact? | Branch/job permissions và credential policy |

## 22. Ví dụ pipeline hoàn chỉnh ở mức khái niệm

Một pipeline có thể thực hiện như sau:

~~~text
1. Checkout source
2. Restore dependency/tool cache
3. Run Gradle build
      ./gradlew clean :app:check :app:assemble
4. Create metadata and checksums
5. Upload package artifact
      app/build/libs/app-1.0.0.jar
      build-info.json
      checksums.sha256
6. Upload test evidence
      test reports
      coverage report
7. Integration-test job downloads package artifact
8. Run integration tests against that package
9. Release gate checks test result and approval
10. Publish/promote the same package
11. Record release identity and provenance
~~~

Ở đây:

- Restore cache giúp bước build nhanh hơn.
- Gradle build cache giúp tái sử dụng task output khi cache key khớp.
- JAR được upload để trở thành artifact bàn giao.
- Test report được upload làm evidence.
- Integration test dùng đúng JAR đã tạo.
- Publish/promote đưa artifact vào nơi phân phối lâu dài.

Nếu pipeline chỉ cache Gradle User Home mà không upload JAR, deploy job không có contract rõ ràng để nhận binary. Nếu pipeline chỉ upload JAR nhưng không cache dependency/task output, build vẫn có thể đúng nhưng tốn thời gian hơn. Hai cơ chế có thể cùng tồn tại và phục vụ hai mục tiêu riêng.

## 23. Những nhầm lẫn thường gặp

| Dễ nhầm | Cách hiểu đúng |
|---|---|
| Cache và artifact đều là file nên có thể dùng thay nhau | Cache tối ưu việc tái sử dụng; artifact chuyển giao kết quả cụ thể |
| Gradle dependency cache chứa JAR ứng dụng | Nó chủ yếu chứa dependency mà build tiêu thụ |
| Build cache hit nghĩa artifact đã được upload | Cache hit chỉ khôi phục output task trong build |
| CI cache giữ file chắc chắn cho release | Cache có thể expire/evict và không phải kho release |
| Upload toàn bộ thư mục build là đủ | Cần chọn deliverable, report và metadata cần bàn giao |
| Deploy job có thể tìm JAR trong Gradle cache | Deploy phải nhận artifact qua CI storage hoặc repository |
| Artifact name là đủ để nhận diện release | Cần run/commit/version và checksum hoặc provenance |
| Build lại ở production tương đương promote artifact | Build lại có thể tạo binary khác; promotion giữ cùng binary |
| Test report upload thành công nghĩa test pass | Upload status và test status là hai kết quả riêng |
| Remote build cache là artifact repository | Build cache lưu output theo task key; repository phát hành package theo tọa độ/version |
| Cache miss làm mất release | Cache miss yêu cầu tính lại; release cần artifact storage riêng |
| Matrix jobs có thể dùng chung một cache key để gom package | Dùng artifact riêng theo platform/variant rồi aggregate |

## 24. Nguyên tắc bàn giao đáng tin cậy

Khi build trong CI, hãy xem cache và artifact là hai phần bổ sung:

- Cache giúp giảm thời gian bằng cách tái sử dụng dữ liệu có thể tái tạo.
- Artifact xác định và chuyển giao kết quả cụ thể của một lần build.
- Repository phát hành giữ package theo version và vòng đời phân phối.
- Metadata, checksum, chữ ký và provenance giúp người nhận xác minh nguồn gốc và tính toàn vẹn.

Một pipeline tốt có thể xóa toàn bộ cache mà vẫn tạo lại được sản phẩm từ source và dependency hợp lệ. Đồng thời, sau khi build hoàn tất, các job test/deploy/release phải nhận đúng artifact được tạo ra ở job build, không phụ thuộc vào việc một cache entry tình cờ còn tồn tại.

Hãy dùng cache để tăng tốc công việc có thể lặp lại; dùng artifact để bàn giao thứ cần được kiểm thử, triển khai, phát hành hoặc lưu giữ.
