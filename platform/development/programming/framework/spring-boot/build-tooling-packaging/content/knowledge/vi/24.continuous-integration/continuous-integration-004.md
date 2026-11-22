# Phân biệt cache dùng tăng tốc với artifact dùng chuyển giao sản phẩm trong CI

## 1. Vấn đề: cùng là file được lưu, nhưng không cùng mục đích

Một pipeline Java/Spring Boot thường cần giữ lại hai nhóm dữ liệu:

- **Cache** lưu dữ liệu có thể tái tạo để lần build sau không phải tải dependency hoặc tính lại task output từ đầu.
- **Artifact** lưu một đầu ra cụ thể đã được tạo trong một lần build, để job khác, workflow khác hoặc người vận hành nhận đúng file đó.

Ví dụ: Maven tải các dependency JAR về `~/.m2/repository`. Đây là dữ liệu cache giúp build nhanh hơn. Sau khi build, project tạo `target/ci-artifact-demo-1.0.0.jar`. Đây là sản phẩm cần được kiểm thử, chuyển sang job đóng Docker image hoặc upload lên Maven repository.

Nếu coi cache như artifact, job triển khai có thể nhận một file cũ theo cache key, file không phải kết quả build vừa qua hoặc file không còn đúng với commit đang kiểm thử. Nếu coi artifact như cache, ta có thể vô tình bỏ mất file cần phát hành khi cache hết hạn, bị evict hoặc cache miss.

Bài thuộc mục **Tự động hóa CI** trong chủ đề **Spring Boot Build Tooling Packaging**. Sau bài này, bạn có thể:

1. Phân biệt dependency cache, build cache, workspace output, CI workflow artifact và release repository.
2. Hiểu vai trò của `~/.m2/repository`, `~/.gradle/caches`, `target/` và `build/`.
3. Chọn cache key phù hợp với OS, architecture, JDK, Maven/Gradle Wrapper và dependency files.
4. Biết khi nào dùng Maven local repository cache, Gradle dependency cache và Gradle task-output build cache.
5. Chuyển executable JAR giữa các GitHub Actions jobs bằng `upload-artifact`/`download-artifact`.
6. Kiểm tra checksum sau khi tải artifact để đảm bảo file chuyển giao không bị thay đổi ngoài ý muốn.
7. Tránh cache poisoning, lưu secrets trong cache hoặc dùng cache làm nguồn phát hành.
8. Thiết kế pipeline **build → test → upload artifact → download → verify → deploy/publish đúng bytes**.
9. Phân biệt workflow artifact có retention với Maven repository/OCI registry dùng phân phối sản phẩm lâu dài.

**Ví dụ thực hành:** Java `17`, Spring Boot `3.5.16`, Maven Wrapper, GitHub Actions, `actions/setup-java@v6`, `actions/upload-artifact@v7` và `actions/download-artifact@v8`. Workflow minh họa nhắm tới GitHub.com hosted runners; GitHub Enterprise Server cần kiểm tra phiên bản action tương thích với server.

## 2. Mô hình tổng quát: cache và artifact giải quyết hai câu hỏi khác nhau

| Câu hỏi | Cơ chế phù hợp | Ví dụ |
| --- | --- | --- |
| Làm sao tránh tải dependency lại? | Dependency cache | `~/.m2/repository`, `~/.gradle/caches/modules-2` |
| Làm sao tránh chạy lại một task tốn thời gian? | Build/task-output cache | Gradle build cache |
| Làm sao job test nhận đúng JAR job build vừa tạo? | CI workflow artifact | Upload/download `application.jar` |
| Làm sao lưu bản release để consumer resolve theo version? | Artifact repository | Maven repository, package registry |
| Làm sao deploy đúng container image đã được QA? | OCI registry + digest | Image digest trong registry |
| Làm sao xem lỗi của một job sau khi job kết thúc? | CI artifact/log retention | Test report, coverage, build log |

Một pipeline có thể sử dụng cả cache lẫn artifact:

~~~text
Source code + pom.xml + Maven Wrapper
                 |
                 v
       RESTORE DEPENDENCY CACHE
       ~/.m2/repository
                 |
                 v
           mvn clean verify
                 |
                 v
       target/application.jar
                 |
             TEST PASS
                 |
                 v
       CREATE CHECKSUM (SHA-256)
                 |
                 v
         UPLOAD CI ARTIFACT
          application.jar
             SHA256SUMS
                 |
          job A completes
                 |
                 v
        DOWNLOAD IN JOB B
                 |
                 v
       VERIFY CHECKSUM + RUN
                 |
                 v
       DEPLOY/PUBLISH EXACT FILE
~~~

**Cache miss chỉ nên làm build chậm hơn.** Nếu xóa toàn bộ cache mà build không thể chạy, pipeline đang phụ thuộc vào trạng thái cache như một nguồn dữ liệu bắt buộc. Một pipeline đúng phải có khả năng tải lại dependencies hoặc tái tạo task outputs khi cache trống.

**Artifact handoff phải có danh tính cụ thể.** Job nhận cần biết artifact đến từ workflow run/build nào, tên file nào, checksum nào và đã vượt qua những kiểm thử nào.

## 3. Năm loại dữ liệu cần phân biệt

### 3.1. Dependency cache

Lưu các dependency/plugin đã tải về hoặc metadata phục vụ dependency resolution. Mục tiêu là giảm network traffic và thời gian chờ.

- Maven: thường là `~/.m2/repository`.
- Gradle: thường là `~/.gradle/caches`, trong đó có module artifacts và resolution metadata.
- Maven/Gradle Wrapper: có cache distribution riêng, tránh tải lại build tool.

Dependency cache không phải thư mục chứa sản phẩm đã được nghiệm thu. Nội dung có thể bị xóa và tải lại từ repository theo coordinates, metadata và integrity policy.

### 3.2. Build cache / task-output cache

Lưu kết quả một số task đã chạy, để build khác có thể tái sử dụng nếu các đầu vào tương ứng không thay đổi.

Ví dụ Gradle có thể cache output của task compile, resource processing hoặc artifact transforms. Build cache dựa trên input/output declarations và task cacheability; task tự viết phải khai báo đầu vào/đầu ra đúng để kết quả tái sử dụng an toàn.

Một task có input bị khai báo thiếu có thể trả lại output cũ dù dữ liệu thực tế đã thay đổi. Do đó task-output cache cần được kiểm chứng như một cơ chế tối ưu build, không phải kho phát hành.

### 3.3. Workspace output

Là file được tạo trong workspace của một job:

- Maven: `target/classes`, `target/test-classes`, `target/*.jar`, `target/surefire-reports`.
- Gradle: `build/classes`, `build/resources`, `build/libs`, `build/reports`.

Workspace của một CI job thường bị hủy sau khi job kết thúc. Job khác có runner/workspace riêng; không thể mặc nhiên đọc `target/application.jar` từ job trước. Muốn chuyển file qua job, hãy dùng workflow artifact hoặc kho lưu trữ có chủ đích.

### 3.4. CI workflow artifact

Là file hoặc tập file do workflow tạo ra, được upload để:

- Chuyển build output giữa jobs.
- Lưu binary/test report/log để xem sau khi job kết thúc.
- Cung cấp file cho bước kiểm thử, đóng image hoặc deploy.
- Giữ lại bằng chứng của một lần chạy CI theo retention policy.

Artifact được gắn với workflow run và tên/ID của nó. Đây là **cơ chế chuyển giao đầu ra**, không tự thay thế Maven repository hoặc registry sản phẩm lâu dài.

### 3.5. Release artifact trong repository

Là sản phẩm được publish theo identity ổn định và policy của tổ chức:

- Maven: GAV + extension + classifier trong Maven repository.
- OCI: image manifest/index digest trong container registry.
- Generic binary: artifact repository hoặc release storage.

Release artifact cần versioning, checksum, quyền publish, retention, immutability và quy trình promotion/rollback. Một file workflow artifact có thể là bước trung gian trước release, nhưng không tự trở thành một Maven release chỉ vì được upload thành công.

## 4. Maven: local repository là cache và nơi lưu artifact cài local

Maven local repository mặc định thường nằm ở:

~~~text
Linux/macOS: ~/.m2/repository
Windows:     %USERPROFILE%\.m2\repository
~~~

Nó có hai vai trò:

1. Lưu dependency/plugin artifacts tải từ remote repositories.
2. Lưu artifacts project đã được `mvn install` cài vào local repository.

Vì vậy `~/.m2/repository` là một vùng **hỗn hợp**, không đơn giản chỉ là cache tải xuống. Maven có thể dùng lại các JAR/POM có sẵn tại đây thay vì tải từ remote. Local repository path có thể thay đổi trong `settings.xml` qua `<localRepository>`.

### 4.1. Các lệnh Maven không có cùng mục tiêu

| Lệnh | Kết quả | Có phải artifact handoff giữa CI jobs? |
| --- | --- | --- |
| `mvn dependency:go-offline` | Tải trước nhiều dependencies/plugins cần thiết | Không |
| `mvn -o verify` | Chạy offline, chỉ dùng dữ liệu có sẵn trong local repo | Không |
| `mvn clean verify` | Build sạch và chạy lifecycle đến verify | Chưa; output ở workspace job hiện tại |
| `mvn install` | Cài main/attached artifacts vào local Maven repository | Không; chỉ local repository của môi trường đó |
| `mvn deploy` | Publish project artifacts lên remote repository theo cấu hình | Là publish, không phải CI cache |

`mvn install` ở job A không làm job B tự có JAR nếu job B chạy trên runner khác và không chia sẻ local repository. Cách đúng để chuyển sản phẩm đã build là upload file JAR thành CI artifact hoặc publish lên repository dùng chung.

### 4.2. Cache Maven trong GitHub Actions

`actions/setup-java` hỗ trợ cache cho Maven:

~~~yaml
- uses: actions/setup-java@v6
  with:
    distribution: temurin
    java-version: '17'
    cache: maven
~~~

Với cấu hình này, action quản lý cache dependency Maven, thường là `~/.m2/repository`. Action còn hỗ trợ cache Maven Wrapper distribution riêng và cache JDK khi bật dependency caching, tùy cấu hình action.

Trong project nhiều module, có thể chỉ rõ các file dùng tạo cache key:

~~~yaml
- uses: actions/setup-java@v6
  with:
    distribution: temurin
    java-version: '17'
    cache: maven
    cache-dependency-path: |
      **/pom.xml
      .mvn/wrapper/maven-wrapper.properties
      .mvn/extensions.xml
~~~

Cache key của `setup-java` được xây từ OS, architecture, package manager và hash của các dependency/build input files theo action. Khi POM, Maven Wrapper properties hoặc extension files đổi, key có thể đổi và tạo cache mới.

**Không đưa `target/` vào cache dependency path.** File JAR trong target là output của lần build; nó phải được kiểm tra và chuyển giao bằng artifact workflow.

### 4.3. Maven cache không thay repository nguồn

Maven local repository không phải nguồn phát hành chính thức:

- Cache có thể bị xóa hoặc hết hạn.
- Remote SNAPSHOT có thể được cập nhật và metadata thay đổi.
- Repository origin, mirrors, checksum policy và dependency coordinates vẫn ảnh hưởng resolution.
- Một artifact cài local bằng `mvn install` có thể không tồn tại trong remote repository.
- Cùng coordinates nhưng repository có thể trả binary khác nếu repository cho phép republish.

Không dùng cache để thay Maven Central/internal repository manager, và không copy thủ công file trong local repository như một quy trình publish. Dùng Maven repository APIs/goals và remote repository được quản lý.

### 4.4. Cẩn thận với settings.xml và credentials

Maven `settings.xml` thường chứa server credentials, proxy credentials, mirror configuration hoặc local repository path. File user settings nằm ngoài project ở `~/.m2/settings.xml` theo mặc định.

Chỉ cache đúng thư mục dependency repository; **không cache hoặc upload toàn bộ user home**. Không đưa `settings.xml` có password/token vào cache path, CI artifact hoặc build logs. Credentials phải được cung cấp qua secret store và settings được tạo an toàn cho job.

## 5. Gradle: dependency cache khác build cache

Gradle có nhiều loại cache; không nên gọi tất cả là “Gradle cache” rồi mặc nhiên cho rằng chúng cùng mục đích.

### 5.1. Dependency cache

Gradle lưu module artifacts, POM/Ivy metadata và kết quả dependency resolution trong Gradle User Home, thường dưới:

~~~text
~/.gradle/caches
~/.gradle/wrapper
~~~

Dependency cache giảm việc tải lại dependencies và metadata. Gradle phân biệt repository origins và lưu artifact theo checksum; metadata cache cũng ghi nhận repository đã cung cấp module. Điều này giúp resolver không tùy tiện coi artifact cùng coordinates từ mọi repository là một nguồn giống nhau.

Một số lệnh hữu ích:

~~~bash
./gradlew dependencies
./gradlew --offline build
./gradlew --refresh-dependencies build
~~~

- `dependencies` hiển thị dependency graph cho configuration phù hợp.
- `--offline` yêu cầu Gradle chỉ dùng dữ liệu cache có sẵn; thiếu artifact cần thiết thì build fail.
- `--refresh-dependencies` yêu cầu Gradle kiểm tra lại dependency resolution với repositories; không có nghĩa tải lại mọi file một cách mù quáng.

Cache không biến dynamic versions hoặc changing/SNAPSHOT dependencies thành versions bất biến. Nếu dependency được đánh dấu changing, Gradle có chính sách refresh/cache TTL riêng. Release nên pin versions và quản lý dependency verification/locking theo policy.

### 5.2. Gradle build cache

Gradle build cache lưu **task outputs** và artifact-transform outputs để có thể tái sử dụng nếu các input tương ứng khớp. Nó khác dependency cache:

| Cache | Dữ liệu | Ví dụ |
| --- | --- | --- |
| Dependency cache | Thư viện/plugin tải từ repository và metadata resolve | `spring-core.jar`, plugin modules |
| Build cache | Output do task tạo ra | Compile classes, processed resources, task output |
| Wrapper cache | Gradle distribution đã tải | Gradle version được khai báo trong Wrapper |

Có thể bật build cache cho một lần chạy:

~~~bash
./gradlew clean build --build-cache
~~~

Hoặc bật trong `gradle.properties`:

~~~properties
org.gradle.caching=true
~~~

Gradle có local build cache và có thể cấu hình remote build cache. Khi dùng remote cache, quyền đọc/ghi cần được kiểm soát; không để workflow không đáng tin cậy đẩy outputs vào cache mà release build sẽ tin cậy.

**Build cache không phải kho lưu release JAR.** Sau khi Gradle tạo `build/libs/app.jar`, hãy upload đúng file đó thành CI artifact hoặc publish lên Maven/OCI repository. Một task output cache hit chỉ nói Gradle có thể tái sử dụng kết quả task theo cache key, không chứng minh một artifact đã được lưu lâu dài hoặc phê duyệt phát hành.

### 5.3. Gradle task phải khai báo inputs/outputs đúng

Task cacheable cần khai báo các inputs và outputs ảnh hưởng tới kết quả. Nếu task đọc file môi trường, biến môi trường, tool version hoặc file ngoài nhưng không khai báo input, Gradle có thể tái sử dụng output không còn đúng.

Khi viết custom task:

- Khai báo source files, configuration và tool versions là inputs phù hợp.
- Khai báo output files/directories chính xác.
- Không phụ thuộc ngầm vào current time, random values, hostnames hoặc file ngoài không được khai báo.
- Tránh ghi nhiều output không được quản lý vào một thư mục cacheable.
- Chỉ bật cache cho task có behavior xác định và có thể tái sử dụng an toàn.

Cache là một tối ưu hóa cần correctness; nó không thể sửa một task có input/output contract sai.

### 5.4. Cache Gradle trong GitHub Actions

Dùng `setup-java`:

~~~yaml
- uses: actions/setup-java@v6
  with:
    distribution: temurin
    java-version: '17'
    cache: gradle
    cache-dependency-path: |
      **/*.gradle*
      **/gradle.properties
      **/gradle-wrapper.properties
      gradle/libs.versions.toml
~~~

Hoặc dùng `gradle/actions/setup-gradle` nếu cần quản lý cache Gradle nâng cao hơn. Đọc tài liệu action và Gradle version tương ứng; không cache toàn bộ `build/` như thể đó là dependency repository.

## 6. Cache key: chọn đầu vào nào để nhận cache phù hợp?

Cache key là nhãn dùng để tìm một cache entry. Key quá rộng có thể khôi phục dữ liệu không phù hợp; key quá hẹp tạo quá nhiều cache miss và tốn storage.

Một key cho dependency cache thường cần cân nhắc:

- Hệ điều hành runner.
- CPU architecture.
- Package manager và version/Wrapper.
- JDK/toolchain khi dữ liệu cache phụ thuộc toolchain.
- POMs hoặc Gradle build files.
- Lockfiles, version catalogs và dependency declarations.
- Maven/Gradle extensions hoặc properties ảnh hưởng resolution.
- Các profile/module thực sự được build.

Ví dụ khái niệm:

~~~text
maven-Linux-X64-JDK17-wrapperHash-pomHash
gradle-Linux-X64-JDK17-wrapperHash-lockfileHash
~~~

Không nhất thiết phải tự viết key khi `setup-java` đã quản lý key; đây là mô hình để hiểu những gì làm cache cần được thay mới.

### 6.1. Exact key và restore-keys

GitHub Actions cache có thể:

1. Tìm exact key.
2. Tìm prefix/partial match.
3. Thử các `restore-keys` theo thứ tự.
4. Nếu không có cache phù hợp thì cache miss; job chạy và cache mới có thể được lưu khi hoàn thành thành công.

Ví dụ với `actions/cache`:

~~~yaml
- uses: actions/cache@v4
  with:
    path: ~/.m2/repository
    key: maven-${{ runner.os }}-${{ hashFiles('**/pom.xml') }}
    restore-keys: |
      maven-${{ runner.os }}-
~~~

Đây là ví dụ thủ công để minh họa key matching; khi đã dùng `setup-java cache: maven`, thường không cần thêm cache action thứ hai cho cùng thư mục. Tránh hai action cùng quản lý một path vì có thể gây xung đột hoặc lưu nội dung không như dự kiến.

`restore-keys` có thể lấy cache gần đúng mới nhất. Với dependency cache, Maven/Gradle vẫn thực hiện resolution theo coordinates, metadata và repository policy. Nhưng đừng dùng restore prefix rộng để khôi phục `target/`/`build/` rồi coi file output là bản build hiện tại.

### 6.2. Cache miss là trạng thái bình thường

Cache có thể miss khi:

- POM/lockfile thay đổi.
- JDK/OS/architecture đổi.
- Cache bị eviction hoặc hết retention.
- Branch chưa có cache riêng.
- Key hoặc cache version khác.
- Runner dùng một cache scope khác.

Khi miss, pipeline nên tải dependencies và chạy build bình thường. Đừng biến cache hit thành điều kiện bắt buộc để deploy. Đừng bỏ qua test vì “đã dùng cache của lần build trước”.

## 7. GitHub Actions cache security và cache poisoning

Cache không phải kho tin cậy mặc định. GitHub docs cảnh báo cache contents không được ký/xác minh; workflow đọc được cache có thể trích xuất nội dung, và file cache sau khi restore có thể ảnh hưởng đến files được thực thi.

### 7.1. Không lưu secrets

Không cache:

- `settings.xml` chứa Maven credentials.
- Access tokens, passwords, private keys, signing keys.
- `.env` chứa secrets.
- Credential files hoặc private repository configuration.
- Workspace có file nhạy cảm mà workflow khác có thể đọc.

Cache path nên chỉ gồm dependency/build cache cần thiết. Cung cấp secrets qua CI secret store và chỉ inject vào job cần dùng.

### 7.2. Hạn chế ai được ghi cache

Cache poisoning xảy ra khi một workflow không đáng tin cậy ghi nội dung cache mà workflow có quyền cao hơn sau đó khôi phục và sử dụng. Ví dụ, một PR workflow ghi cache chứa file thực thi giả; một trusted release workflow khôi phục cache và chạy file đó.

Các biện pháp:

- Chỉ trusted branch/trigger được ghi cache dùng cho release.
- Workflow PR/fork nên dùng cache read-only nếu có thể.
- Không đưa secrets vào cache dù cache key có vẻ khó đoán.
- Không chạy file thực thi được lấy từ cache mà không kiểm soát nguồn và integrity.
- Giữ cache key tách biệt theo OS/architecture/toolchain và dependency inputs.
- Nếu cache miss, chạy lại resolution/build thay vì lấy file output không rõ nguồn.
- Với build quan trọng, xác minh dependency integrity bằng checksum/signature và dùng repository đáng tin.

`actions/setup-java` hỗ trợ `cache-read-only`; ví dụ chỉ main branch được ghi cache:

~~~yaml
- uses: actions/setup-java@v6
  with:
    distribution: temurin
    java-version: '17'
    cache: maven
    cache-read-only: ${{ github.ref != 'refs/heads/main' }}
~~~

Biểu thức trên làm các refs khác main chỉ đọc cache; phải điều chỉnh theo branch policy của tổ chức. GitHub có các giới hạn cache access theo branch/trigger, nhưng policy riêng và workflow triggers vẫn cần được review.

## 8. CI workflow artifact: chuyển đúng file giữa các jobs

Mỗi GitHub Actions job thường chạy trên runner/workspace riêng. Nếu job `build` tạo:

~~~text
target/ci-artifact-demo-1.0.0.jar
~~~

thì job `package` không tự có file này. Cách chuyển giao:

1. Build và test JAR trong job A.
2. Tạo checksum cho chính JAR đó.
3. Upload JAR và checksum thành một workflow artifact.
4. Job B download artifact theo đúng tên/ID.
5. Kiểm tra checksum.
6. Dùng đúng file đã download để smoke test/đóng image/deploy.

### 8.1. upload-artifact và download-artifact

GitHub cung cấp:

- `actions/upload-artifact`: upload file hoặc thư mục được tạo trong workflow.
- `actions/download-artifact`: download workflow artifact trong cùng workflow run hoặc run/repository khác nếu có quyền/token phù hợp.

Artifacts được dùng để lưu build binaries, test results, logs, coverage và chia sẻ output giữa jobs. Từ phiên bản v4, workflow artifacts có tính bất biến sau khi tạo; mỗi lần upload nên có tên duy nhất. Không thiết kế nhiều jobs cùng sửa một artifact name như một thư mục dùng chung.

Ví dụ dưới dùng major versions theo tài liệu hiện hành: upload `@v7` và download `@v8`. Trước khi áp dụng, kiểm tra tương thích GitHub Enterprise Server và runner; tài liệu download action hiện có giới hạn hỗ trợ v4+ trên GHES. Với pipeline bảo mật cao, pin actions bằng full commit SHA đã được review thay vì chỉ dùng major tag.

### 8.2. Artifact retention

GitHub workflow artifacts có retention policy:

- Mặc định phổ biến là `90 ngày`, tùy repository/organization settings.
- Có thể đặt `retention-days` ngắn hơn cho file handoff/diagnostic.
- Artifact hết hạn sẽ không còn dùng để download.
- Workflow artifact phù hợp với handoff và điều tra trong thời hạn retention; release lâu dài cần repository/registry có policy lưu trữ riêng.

Ví dụ đặt `retention-days: 14` cho file trung gian. Đừng dùng workflow artifact như kho lưu release không thời hạn.

### 8.3. Tên artifact phải xác định đúng run

Tên artifact nên bao gồm thông tin giúp phân biệt run và matrix job, ví dụ:

~~~text
executable-jar-<git-sha>-<run-id>-<run-attempt>
test-report-linux-jdk17
test-report-windows-jdk17
~~~

Khi matrix chạy nhiều OS/JDK, không để tất cả jobs upload cùng tên rồi kỳ vọng chúng tự merge. Đặt tên riêng hoặc dùng cơ chế merge artifact có chủ đích. Rerun workflow cũng nên tạo artifact identity riêng để tránh đụng artifact đã tồn tại.

## 9. Ví dụ hoàn chỉnh: Maven build cache + chuyển executable JAR giữa hai jobs

Ta tạo một Spring Boot CLI application đơn giản. Job build dùng cache Maven để giảm tải dependency; sau khi JAR qua build/smoke test, nó được upload thành workflow artifact. Job thứ hai download và chạy lại **đúng file đã nhận**, không build lại source.

### 9.1. Cấu trúc project

~~~text
ci-artifact-demo/
  pom.xml
  .mvn/
    wrapper/
      maven-wrapper.properties
  mvnw
  src/
    main/
      java/
        demo/
          CiArtifactDemoApplication.java
~~~

Ví dụ giả định Maven Wrapper đã được tạo và commit cùng project. Nếu repo chưa có Wrapper, hãy thêm theo quy trình Maven Wrapper hoặc dùng Maven version đã được CI quản lý.

### 9.2. pom.xml đầy đủ

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example.ci</groupId>
    <artifactId>ci-artifact-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Với Spring Boot parent, plugin được quản lý version và goal `repackage` được gắn vào package lifecycle. File executable JAR kỳ vọng:

~~~text
target/ci-artifact-demo-1.0.0.jar
~~~

Nếu project không dùng Boot parent, phải cấu hình plugin version/execution phù hợp; không mặc định một POM Maven bất kỳ sẽ tạo executable Spring Boot JAR.

### 9.3. CiArtifactDemoApplication.java

Tạo `src/main/java/demo/CiArtifactDemoApplication.java`:

~~~java
package demo;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class CiArtifactDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                CiArtifactDemoApplication.class, args);
    }

    @Bean
    CommandLineRunner report() {
        return args ->
                System.out.println("ci-artifact-demo:ok");
    }
}
~~~

Ứng dụng không có web server; sau khi Spring context khởi tạo và `CommandLineRunner` chạy, tiến trình kết thúc khi main hoàn tất. Điều này giúp workflow kiểm tra executable JAR mà không phải giữ một HTTP server chạy nền.

Build local:

~~~bash
./mvnw -B -ntp clean verify
~~~

Chạy JAR:

~~~bash
java -jar target/ci-artifact-demo-1.0.0.jar \
  --spring.main.banner-mode=off \
  --logging.level.root=OFF
~~~

Dòng do application code in chính xác:

~~~text
ci-artifact-demo:ok
~~~

Trong workflow, ta so stdout với đúng chuỗi này để kiểm tra archive sau package.

## 10. Tạo SHA-256 trước khi upload

Sau khi `mvnw clean verify` và packaged JAR smoke test PASS, tạo thư mục handoff:

~~~bash
set -eu

mkdir -p handoff
cp target/ci-artifact-demo-1.0.0.jar handoff/application.jar

(
  cd handoff
  sha256sum application.jar > SHA256SUMS
)
~~~

Trong `handoff/` có:

~~~text
application.jar
SHA256SUMS
~~~

Nội dung `SHA256SUMS` có dạng:

~~~text
<sha256-hex>  application.jar
~~~

`<sha256-hex>` là ký hiệu minh họa; giá trị thực do `sha256sum` tính từ bytes của file. Không ghi digest giả vào release record.

Tại job nhận artifact, chạy:

~~~bash
cd handoff
sha256sum --check SHA256SUMS
~~~

Nếu file khớp, stdout có dạng:

~~~text
application.jar: OK
~~~

Nếu bytes thay đổi hoặc file bị thiếu, lệnh trả nonzero exit code. Job phải dừng trước khi sử dụng file.

**Checksum sidecar bảo vệ điều gì?** Nó phát hiện lỗi truyền tải, file bị thay hoặc chọn nhầm file khi checksum được giữ độc lập và so sánh đúng. Nếu kẻ tấn công có thể thay cả JAR lẫn SHA256SUMS, sidecar tự nó không chứng minh nguồn build đáng tin; cần bảo vệ workflow, quyền artifact và provenance/attestation/signature theo mức bảo đảm yêu cầu.

## 11. GitHub Actions workflow hai jobs hoàn chỉnh

Tạo `.github/workflows/build-transfer.yml`:

~~~yaml
name: Build and transfer executable JAR

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

permissions:
  contents: read

jobs:
  build:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v7

      - name: Set up Java and restore Maven dependency cache
        uses: actions/setup-java@v6
        with:
          distribution: temurin
          java-version: '17'
          cache: maven
          cache-dependency-path: |
            **/pom.xml
            .mvn/wrapper/maven-wrapper.properties
            .mvn/extensions.xml
          cache-read-only: ${{ github.ref != 'refs/heads/main' }}

      - name: Build project and run Maven verification
        run: ./mvnw -B -ntp clean verify

      - name: Smoke-test the packaged JAR and prepare handoff
        shell: bash
        run: |
          set -eu

          jar=target/ci-artifact-demo-1.0.0.jar
          test -f "$jar"

          output="$(java -jar "$jar" \
            --spring.main.banner-mode=off \
            --logging.level.root=OFF)"

          test "$output" = "ci-artifact-demo:ok"

          mkdir -p handoff
          cp "$jar" handoff/application.jar
          (
            cd handoff
            sha256sum application.jar > SHA256SUMS
          )

      - name: Upload the verified executable JAR
        uses: actions/upload-artifact@v7
        with:
          name: executable-jar-${{ github.sha }}-${{ github.run_id }}-${{ github.run_attempt }}
          path: handoff/
          if-no-files-found: error
          retention-days: 14

  consume:
    needs: build
    runs-on: ubuntu-latest

    steps:
      - name: Set up Java runtime for the downloaded JAR
        uses: actions/setup-java@v6
        with:
          distribution: temurin
          java-version: '17'

      - name: Download the artifact from the build job
        uses: actions/download-artifact@v8
        with:
          name: executable-jar-${{ github.sha }}-${{ github.run_id }}-${{ github.run_attempt }}
          path: handoff
          digest-mismatch: error

      - name: Verify checksum and execute the transferred JAR
        shell: bash
        run: |
          set -eu
          cd handoff

          sha256sum --check SHA256SUMS

          output="$(java -jar application.jar \
            --spring.main.banner-mode=off \
            --logging.level.root=OFF)"

          test "$output" = "ci-artifact-demo:ok"

          printf '%s\n' 'artifact.transfer=PASS'
          printf '%s\n' 'artifact.run=PASS'
~~~

### 11.1. Điều gì xảy ra trong job build?

- `actions/setup-java@v6` cài Java 17 và khôi phục dependency cache Maven.
- `cache: maven` tối ưu việc tải dependencies; cache không chứa `handoff/application.jar`.
- `./mvnw clean verify` build source và tạo executable JAR.
- Workflow chạy **chính JAR đã package**, kiểm tra stdout.
- `sha256sum` ghi checksum của file đã qua smoke test.
- `upload-artifact@v7` upload file JAR và sidecar thành một artifact có tên gắn với commit/run/attempt.

### 11.2. Điều gì xảy ra trong job consume?

- `needs: build` bảo đảm job chỉ chạy sau khi job build thành công.
- Runner thứ hai cài JRE/JDK 17 để chạy file được tải về.
- `download-artifact@v8` tải artifact theo đúng tên đã tạo.
- `digest-mismatch: error` yêu cầu action báo lỗi nếu digest artifact tải về không khớp giá trị server cung cấp.
- `sha256sum --check` xác minh bytes của JAR sau khi giải nén artifact.
- `java -jar` thực thi **file vừa download**, không build lại source.
- Hai dòng cuối chỉ được in khi checksum và runtime smoke đều PASS.

Với workflow ví dụ, output cuối do step verify in chính xác:

~~~text
application.jar: OK
artifact.transfer=PASS
artifact.run=PASS
~~~

Các bước Maven build và upload có log riêng. Nếu checksum hoặc application output không khớp, `set -eu`/`test` làm step fail và workflow không thể coi job `consume` là thành công.

### 11.3. Vì sao tên artifact chứa run ID và run attempt?

Một commit có thể được chạy lại nhiều lần. Nếu dùng duy nhất tên theo commit, artifact name có thể đụng với artifact đã tạo trong cùng workflow run. Ghép `github.run_id` và `github.run_attempt` giúp phân biệt các lần chạy và tránh việc nhiều jobs vô tình upload cùng artifact name.

Với matrix builds, thêm cả `matrix.os`, `matrix.java` hoặc classifier vào tên để phân biệt output theo nền tảng/JDK. Không gộp các file cùng tên từ nhiều jobs nếu chưa định nghĩa quy tắc chọn/merge.

## 12. Workflow artifact không phải Maven release repository

Workflow artifact phù hợp để giữ và chuyển file theo một workflow run. Nhưng một ứng dụng cần được consumer resolve theo Maven coordinates thì cần publish vào Maven repository.

| Tiêu chí | GitHub workflow artifact | Maven repository |
| --- | --- | --- |
| Định danh | Workflow run + artifact name/ID | GAV + extension + classifier |
| Mục tiêu | Job handoff, test output, build output, logs | Resolve dependency và phân phối Maven artifact |
| Retention | Theo GitHub Actions retention policy | Theo retention/immutability policy của repository manager |
| Consumer | Workflow/job hoặc người có quyền repo | Maven/Gradle consumers và tools hiểu repository |
| SNAPSHOT/release metadata | Không phải Maven metadata | Có repository metadata và snapshot/release policy |
| Publish command | `upload-artifact` | `mvn deploy` hoặc publisher tương ứng |
| Checksum | Artifact digest và/hoặc sidecar | Repository checksums/signatures theo policy |

`mvn install` chỉ đưa artifact vào local Maven repository; `mvn deploy` publish artifact lên remote repository đã cấu hình. Không upload toàn bộ `~/.m2/repository` thành workflow artifact rồi coi đó là Maven repository công khai.

Với sản phẩm Maven, remote repository cần release immutability, authentication, access control, snapshot policy và retention. Workflow artifact thường hết hạn sau một thời gian, vì vậy không dùng nó làm nơi lưu trữ release lâu dài trừ khi tổ chức có chính sách lưu trữ riêng đáp ứng yêu cầu.

## 13. OCI image cũng cần artifact identity riêng

Nếu job tiếp theo dùng JAR để build Docker image, có thể chuyển đúng file JAR qua workflow artifact rồi:

1. Download JAR và `SHA256SUMS`.
2. Chạy `sha256sum --check`.
3. Build Docker image với Dockerfile chỉ COPY file JAR đã verify.
4. Trích file JAR từ image và so checksum với file đã download.
5. Smoke-test container.
6. Push image và lưu registry digest.

Ba định danh không được nhầm:

~~~text
Git commit SHA     = source revision
JAR SHA-256       = executable JAR bytes
OCI image digest  = image manifest/index
~~~

Cùng Git commit không đảm bảo JAR bytes giống nhau; cùng JAR bytes không đảm bảo OCI image digest giống nhau vì base image, OS layers, image config, compression và platform có thể khác.

Không cache Docker release image rồi dùng tag cache làm deployment artifact. Cache build layers có thể tăng tốc Docker build, nhưng image được publish phải được xác định bằng tag/digest và vượt qua các image gates.

## 14. Cache build output và cache dependency: khi nào nên dùng?

### 14.1. Maven

Nên cache:

- `~/.m2/repository` cho dependencies/plugins.
- Maven Wrapper distribution nếu workflow không tải lại mỗi lần.
- Các cache hỗ trợ bởi CI action, có key gắn với POM/Wrapper/OS/architecture phù hợp.

Không nên mặc định cache:

- `target/` chứa output compile/package cũ.
- File JAR đã qua QA nhưng không có artifact identity.
- `~/.m2/settings.xml` hoặc toàn bộ user home.
- Log/report có thể chứa secrets.

Nếu project dùng Maven build-cache extension hoặc plugin cache output, hãy đọc tài liệu và kiểm tra cache correctness riêng; đó không phải behavior mặc định của local repository.

### 14.2. Gradle

Nên tách:

- Dependency cache: tải module artifacts/metadata.
- Wrapper cache: Gradle distribution.
- Build cache: task outputs có inputs/outputs khai báo đúng.
- Workflow artifact: `build/libs/*.jar` đã được kiểm chứng và chuyển giao.

Có thể bật Gradle build cache nhưng vẫn cần upload executable JAR riêng. Không dùng cache hit như bằng chứng rằng JAR đã được phát hành hoặc được chuyển qua job khác.

### 14.3. Workspace incremental outputs

Một số CI runner được tái sử dụng có workspace còn file cũ. `mvn clean` hoặc `./gradlew clean` giúp xóa output cũ trước build. Nhưng clean không thay artifact transfer, và việc restore cache vào `target/`/`build/` có thể gây stale outputs nếu plugin/task không xử lý incremental state đúng.

Để chuyển sản phẩm đã build, dùng một file artifact rõ ràng. Để tăng tốc task, dùng cache mechanism được build tool hỗ trợ. Hai workflow có thể cùng tồn tại nhưng cần phân biệt.

## 15. GitHub Actions cache và artifact: những giới hạn thực tế

### 15.1. Cache không được sửa tại chỗ theo key cũ

GitHub Actions cache tạo entry theo key. Khi exact key đã tồn tại, nội dung entry đó không được sửa như một thư mục dùng chung; cần key mới để tạo entry khác. Nếu job dùng `restore-keys`, nó có thể nhận partial match gần nhất.

Do đó, không sử dụng cache key cố định như `production-latest` để thay thế một JAR release mỗi lần. Đó là cách sử dụng cache sai mục đích.

### 15.2. Workflow artifact immutable

Từ `upload-artifact@v4`, artifacts được tạo là immutable. Các lần upload không thể tùy ý append vào cùng artifact như cơ chế cũ. Nếu cần artifact mới, tạo artifact mới với tên/ID khác; thao tác overwrite (nếu được bật) tạo ID mới và thay artifact trước, không phải sửa bytes tại chỗ.

Trong workflow ví dụ, một job build upload một artifact duy nhất; job consume chỉ download. Đây là cách đơn giản để tránh collision.

### 15.3. File permissions trong artifact archive

Upload artifact dạng ZIP có thể không giữ mọi POSIX permissions như ban đầu; file thường được khôi phục với permission chuẩn của action. Với JAR, đây không phải vấn đề vì file được gọi qua `java -jar`, không cần executable bit. Nếu chuyển shell scripts hoặc binary cần executable mode, có thể đóng gói thành `tar` trước khi upload rồi unpack sau download, hoặc chọn cách upload phù hợp theo action version.

### 15.4. Retention và quota

Artifact có thể hết hạn và storage có quota. Retention ngắn phù hợp file handoff/diagnostics; release binaries cần chuyển vào repository/registry được quản lý lâu dài. Không thiết kế rollback production dựa trên một workflow artifact có thể tự hết hạn sau retention period.

## 16. Chọn chiến lược theo tình huống

| Tình huống | Cơ chế đề xuất | Lý do |
| --- | --- | --- |
| Nhiều build dùng chung dependency Maven | Cache `~/.m2/repository` | Tránh tải dependency/plugin nhiều lần |
| Gradle build có task compile/resource đắt | Dependency cache + Gradle build cache | Tái dùng downloads và task outputs theo hai cơ chế riêng |
| Job integration test cần JAR từ job build | Workflow artifact | Chuyển đúng file output giữa runner riêng |
| Job Docker cần JAR đã được smoke-test | Workflow artifact + SHA-256 | Bảo đảm Docker build nhận đúng bytes |
| Nhiều developer cần dùng library nội bộ | Maven remote repository | Resolve theo GAV/version/classifier |
| Production cần container image bất biến | OCI registry digest | Deploy đúng manifest/index đã publish |
| Debug test fail sau khi runner kết thúc | Workflow artifact logs/reports | Giữ bằng chứng theo retention |
| Release cần rollback nhiều tháng sau | Release repository/registry có retention | Workflow artifact ngắn hạn không đủ |
| Build chạy offline trên máy mới | Seed dependency cache/repository đã xác minh | Cache thiếu dependency sẽ khiến offline build fail |
| Untrusted PR cần dùng cache của main | Restore-only/read-only cache | Giảm nguy cơ cache poisoning |

## 17. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| Job B báo không tìm thấy `target/app.jar` | Mỗi job có workspace riêng | Upload artifact ở job A và download ở job B |
| `mvn install` xong nhưng runner khác không thấy artifact | Install chỉ vào local repository của runner A | Dùng workflow artifact hoặc remote Maven repository |
| Cache miss làm build fail | Pipeline phụ thuộc vào cache như nguồn bắt buộc | Cho phép download/rebuild từ remote repositories |
| Build nhận JAR cũ từ cache | Cache output path/key quá rộng hoặc restore fallback sai | Không cache release JAR; upload artifact theo run identity |
| POM đổi nhưng cache vẫn không đúng | Cache key không hash đủ dependency inputs | Bổ sung pom/lockfile/Wrapper/extension paths |
| Gradle dependency cache hit nhưng task vẫn chạy | Dependency cache không phải task-output build cache | Cấu hình build cache nếu task cacheable |
| Gradle build cache trả output không đúng | Task khai báo thiếu inputs/outputs hoặc task không deterministic | Sửa task contract, kiểm tra cacheability |
| `--offline` Maven/Gradle fail | Cache thiếu dependency/plugin/metadata | Bỏ offline hoặc seed đủ cache/repository |
| Workflow artifact download không tìm thấy | Tên artifact/run không khớp, upload step fail hoặc retention hết hạn | Kiểm tra upload summary, exact name/ID và run |
| Artifact upload trùng tên | Nhiều jobs/matrix/reruns cùng tên | Thêm run ID/attempt/OS/JDK vào tên |
| SHA-256 mismatch sau download | File bị thay, sai file hoặc sai manifest | Dừng deploy, kiểm tra nguồn và checksum |
| JAR checksum pass nhưng app chạy fail | Checksum chỉ kiểm tra bytes, không kiểm tra runtime correctness | Chạy packaged-JAR smoke test và container smoke |
| Cache chứa credentials | Cache path quá rộng hoặc lưu user home | Xóa cache bị lộ, xoay credentials, giới hạn path |
| PR ghi cache mà release build tin cache | Cache poisoning hoặc quyền write quá rộng | Read-only cache cho untrusted workflows; trusted cache writer |
| Workflow artifact hết hạn | Retention không đủ cho release/rollback | Publish vào Maven repository/OCI registry lâu dài |
| CI build pass nhưng release artifact khác | Rebuild ở job publish thay vì dùng artifact đã test | Download đúng artifact, verify checksum, không build lại |
| Upload shell script xong mất executable bit | ZIP artifact không bảo toàn POSIX permissions | Tar file trước upload hoặc chmod sau download |
| Multi-module dùng cache key không đầy đủ | Hash chỉ root pom/thiếu child module inputs | Dùng cache-dependency-path bao gồm các module |
| SNAPSHOT dependency đổi nhưng cache cũ còn | Snapshot/update policy và metadata cache | Dùng release versions cho release; refresh có chủ đích |

## 18. Checklist thiết kế pipeline

### Cache

- [ ] Cache chỉ chứa dependency/tool/build cache có thể tái tạo.
- [ ] Key bao gồm OS/architecture và dependency/build inputs phù hợp.
- [ ] Maven/Gradle Wrapper và toolchain được quản lý.
- [ ] Không cache `target/`/`build/` như sản phẩm phát hành nếu chưa có task-cache strategy đúng.
- [ ] Không cache `settings.xml`, secrets, tokens hoặc private keys.
- [ ] Cache miss vẫn cho phép build tải dependencies và chạy đầy đủ.
- [ ] PR/fork chỉ đọc cache nếu workflow không đáng tin cậy.
- [ ] Cache được coi là optimization; không bỏ test vì cache hit.

### Artifact transfer

- [ ] Job tạo artifact sau khi build/test thành công.
- [ ] Chọn chính xác file JAR/WAR/image hoặc test report cần chuyển.
- [ ] Artifact name gắn với commit/run/attempt/matrix để tránh collision.
- [ ] Upload action fail nếu file không tồn tại.
- [ ] Upload kèm checksum/provenance phù hợp.
- [ ] Job nhận download đúng artifact ID/name.
- [ ] Kiểm tra checksum sau khi download.
- [ ] Smoke-test file đã download; không build lại source thay thế nó.
- [ ] Retention phù hợp với thời gian cần debug/handoff.

### Release

- [ ] Release JAR/WAR được publish vào Maven repository có policy rõ.
- [ ] OCI image được publish vào registry và lưu digest.
- [ ] Không dùng workflow cache làm nguồn phát hành.
- [ ] Không dùng workflow artifact ngắn hạn làm kho release lâu dài.
- [ ] Publish đúng bytes đã vượt qua các gates.
- [ ] Lưu Git commit, artifact checksum, repository coordinates/image digest và CI run ID.

## 19. Câu hỏi tự kiểm tra

**A. Cache Maven hit có chứng minh job hiện tại đã build ra đúng JAR cần phát hành không?**

Không. Cache hit chỉ cho biết cache key khớp và nội dung cache được khôi phục. JAR vẫn phải được tạo/kiểm tra trong job và upload thành artifact riêng.

**B. Vì sao không cache `target/ci-artifact-demo-1.0.0.jar` rồi để job deploy đọc lại?**

Cache có key matching/restore policy và lifecycle riêng; nó không phải giao thức handoff bảo đảm job nhận đúng output của run hiện tại. Dùng workflow artifact, artifact ID và checksum.

**C. `mvn install` có chuyển JAR giữa hai GitHub-hosted runners không?**

Không. Nó cài vào local Maven repository của runner hiện tại. Runner job khác cần artifact upload/download hoặc remote repository.

**D. Gradle dependency cache và Gradle build cache có giống nhau?**

Không. Dependency cache giữ downloaded modules/metadata; build cache giữ task outputs có thể tái sử dụng. Cả hai đều khác workflow artifact dùng chuyển file sản phẩm giữa jobs.

**E. Nếu cache bị xóa, pipeline có nên fail không?**

Không. Build nên có thể tải lại dependencies và tạo lại outputs. Cache miss chỉ nên làm pipeline chậm hơn, trừ khi hệ thống chủ động chạy offline và đã seed đầy đủ dữ liệu.

**F. Artifact upload thành công có chứng minh ứng dụng chạy đúng không?**

Không. Upload chỉ chứng minh file được lưu trong workflow artifact. Cần chạy packaged JAR, checksum verify, integration/smoke test và kiểm tra runtime trước publish/deploy.

**G. SHA256SUMS được upload cùng JAR có đủ chống kẻ tấn công thay cả hai file không?**

Không. Sidecar giúp phát hiện lỗi truyền tải/chọn nhầm file nếu checksum được tin cậy độc lập. Với provenance cần chữ ký/attestation, protected workflow, least privilege và trusted artifact storage.

**H. Có thể dùng GitHub workflow artifact để lưu release 2 năm không?**

Không nên dựa vào retention mặc định/giới hạn workflow artifact cho rollback dài hạn. Publish release vào Maven repository, generic artifact repository hoặc OCI registry có retention/immutability policy phù hợp.

## 20. Tài liệu chính thức

- GitHub Actions — Dependency caching concepts: https://docs.github.com/en/actions/concepts/workflows-and-actions/dependency-caching
- GitHub Actions — Dependency caching reference, key matching and security: https://docs.github.com/en/actions/reference/workflows-and-actions/dependency-caching
- GitHub Actions — Workflow artifacts: https://docs.github.com/en/actions/concepts/workflows-and-actions/workflow-artifacts
- GitHub Actions — Store and share workflow artifacts: https://docs.github.com/en/actions/tutorials/store-and-share-data
- actions/setup-java — Maven/Gradle dependency, Wrapper and JDK caching: https://github.com/actions/setup-java
- actions/upload-artifact — Artifact upload, immutability and retention: https://github.com/actions/upload-artifact
- actions/download-artifact — Download and digest verification: https://github.com/actions/download-artifact
- Apache Maven — Introduction to repositories: https://maven.apache.org/guides/introduction/introduction-to-repositories
- Apache Maven — Local repositories: https://maven.apache.org/repositories/local.html
- Apache Maven — Settings reference and localRepository: https://maven.apache.org/settings.html
- Gradle — Dependency caching: https://docs.gradle.org/current/userguide/dependency_caching.html
- Gradle — Build cache: https://docs.gradle.org/current/userguide/build_cache.html
- Gradle — Build cache use cases: https://docs.gradle.org/current/userguide/build_cache_use_cases.html
- Spring Boot 3.5 — Packaging executable archives: https://docs.spring.io/spring-boot/3.5/maven-plugin/packaging.html
- Maven Wrapper — Usage and configuration: https://maven.apache.org/wrapper/

**Ghi nhớ:** Cache trả lời **“có thể tái sử dụng dữ liệu nào để build nhanh hơn?”**. Artifact trả lời **“file nào được tạo trong run này, đã được kiểm tra ra sao và cần chuyển tới đâu?”**. Cache có thể bị miss hoặc xóa mà build vẫn phải chạy được; artifact phải có identity, checksum và luồng upload/download rõ ràng. Khi phát hành, hãy dùng **đúng bytes đã được kiểm chứng**, rồi lưu lâu dài trong Maven repository hoặc OCI registry theo policy của sản phẩm.