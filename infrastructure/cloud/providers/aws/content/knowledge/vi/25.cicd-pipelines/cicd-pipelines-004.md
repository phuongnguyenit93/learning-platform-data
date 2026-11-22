# Cache dependency và đóng gói ứng dụng Java trong CodeBuild

Một nhóm phát triển Spring Boot có pipeline chạy trên AWS CodeBuild. Mỗi lần build, Maven hoặc Gradle phải tải hàng trăm dependency, biên dịch source, chạy test và đóng gói executable JAR. Khi build chạy trên build host mới, dependency có thể phải tải lại từ đầu. Nếu pipeline không xác định rõ file đầu ra, artifact được upload có thể thiếu JAR, chứa nhầm file trung gian hoặc không có báo cáo kiểm thử để truy vết.

AWS CodeBuild hỗ trợ cache để tái sử dụng dependency và dữ liệu build giữa các lần chạy. Buildspec định nghĩa các thư mục được cache, các phase thực thi và những file được đóng gói thành artifact. Cấu hình tốt giúp giảm thời gian build, giữ tính tái lập và tạo đầu ra rõ ràng cho các stage tiếp theo.

Bài học thuộc chương **CI/CD trên AWS** của module **CLOUD_PROVIDERS_AWS**. Chúng ta sẽ thực hành với Maven và Gradle, phân biệt S3 cache với local cache, tạo cache key theo dependency descriptors, xuất JAR/WAR, công bố test reports và kiểm soát quyền truy cập cache/artifacts.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Mô tả vai trò của AWS CodeBuild và buildspec trong pipeline Java.
2. Phân biệt dependency cache, task/build cache và build output artifact.
3. Giải thích hai loại cache của CodeBuild: Amazon S3 và local.
4. Chọn local cache mode phù hợp: source, Docker layer hoặc custom.
5. Xác định thư mục dependency cache mặc định của Maven và Gradle.
6. Tạo cache key theo POM, Gradle build files, version catalog và lockfiles.
7. Sử dụng fallback keys và hiểu cách CodeBuild khôi phục cache.
8. Viết buildspec version 0.2 cho Maven và Gradle.
9. Chọn Java runtime và build image ổn định.
10. Đóng gói executable JAR/WAR và chỉ định artifacts chính xác.
11. Xuất JUnit XML test reports và coverage reports.
12. Quản lý multi-module project và monorepo.
13. Kết hợp CodeArtifact với dependency cache.
14. Bảo vệ cache khỏi secret leakage và cache poisoning.
15. Đo hiệu quả cache, xử lý cache miss và debug build chậm.

## 2. CodeBuild trong luồng build Java

Một build CodeBuild thường nhận source từ CodeCommit, GitHub, Bitbucket, S3 hoặc CodePipeline. CodeBuild chuẩn bị build environment, đọc buildspec, chạy lệnh Maven/Gradle và upload artifact hoặc gửi image tới Amazon ECR.

    Source repository / CodePipeline
                |
                v
          AWS CodeBuild
                |
       +--------+---------+
       |                  |
       v                  v
   Restore cache       Build image
       |               JDK + Maven/
       |               Gradle tools
       +--------+---------+
                |
                v
       Compile + unit tests
                |
                v
       Package JAR / WAR
                |
        +-------+-------+
        |               |
        v               v
    Test reports     Build artifact
    JUnit / coverage  S3 / Pipeline
        |               |
        +-------+-------+
                |
                v
       Deploy / integration test

Cache và artifact có mục đích khác nhau:

- **Dependency cache** chứa những dependency đã tải về, ví dụ Maven local repository hoặc Gradle module cache.
- **Build cache** có thể chứa output của task đã tính trước để tránh thực thi lại khi input không đổi.
- **Build artifact** là đầu ra cần chuyển sang stage sau, ví dụ executable JAR, WAR, ZIP hoặc manifest.
- **Test report** là kết quả kiểm thử để pipeline hiển thị và lưu lịch sử chất lượng.

Không dùng cache làm nơi phát hành artifact. Cache là tối ưu hiệu năng và có thể bị thay thế hoặc hết hạn; artifact cần được lưu, định danh và quản lý theo chính sách release.

## 3. Buildspec version 0.2 và các phase

Buildspec là file YAML mô tả cách CodeBuild chạy build. Theo mặc định, CodeBuild tìm file `buildspec.yml` ở thư mục gốc source. Có thể cấu hình tên hoặc vị trí khác trong build project.

Buildspec version 0.2 được khuyến nghị. Khác với version 0.1, các lệnh trong cùng phase dùng chung shell context, nên có thể giữ trạng thái như thư mục hiện tại và biến shell giữa các command trong phase.

Các phase thường dùng:

| Phase | Nhiệm vụ trong Java build |
|---|---|
| install | Chọn runtime Java, cài công cụ cần thiết |
| pre_build | Kiểm tra phiên bản, chuẩn bị registry/repository, xác minh source |
| build | Compile, chạy unit/integration tests, package |
| post_build | Kiểm tra đầu ra, tạo checksum/manifest, chuẩn bị metadata |

Không bắt buộc phải khai báo đủ bốn phase. Nếu một phase không cần lệnh, có thể bỏ nó.

Ví dụ tối giản:

    version: 0.2

    phases:
      install:
        runtime-versions:
          java: corretto17
      pre_build:
        commands:
          - java -version
          - mvn -version
      build:
        commands:
          - mvn -B -ntp clean verify
      post_build:
        commands:
          - echo "Build completed"

`corretto17` chỉ là ví dụ. Runtime version phải được hỗ trợ bởi CodeBuild image đang chọn. Runtime selection trong buildspec được hỗ trợ trên các standard images tương ứng; hãy kiểm tra image version và runtime list trước khi triển khai.

Nguồn: AWS CodeBuild Buildspec reference — https://docs.aws.amazon.com/codebuild/latest/userguide/build-spec-ref.html

## 4. Chọn build image và Java runtime ổn định

CodeBuild build environment là Docker image chứa operating system, runtime và công cụ. Có thể chọn image do AWS quản lý hoặc custom image trong Amazon ECR.

Để build tái lập:

- Chọn image family và image version có chủ đích.
- Khai báo Java runtime rõ ràng thay vì phụ thuộc runtime mặc định.
- Pin Maven/Gradle wrapper version trong repository.
- Pin plugin và dependency version.
- Ghi phiên bản Java, Maven/Gradle và commit SHA vào build logs hoặc build manifest.
- Cập nhật image theo lịch có kiểm thử, tránh để runtime tự đổi phiên bản ngoài dự kiến.

Nếu runtime không được khai báo, CodeBuild dùng runtime mặc định có trong image. Runtime mặc định có thể thay đổi khi phiên bản cũ hết vòng đời hỗ trợ.

Với Maven, nên commit Maven Wrapper (`mvnw`, `.mvn/wrapper/`) để project xác định Maven version. Với Gradle, commit Gradle Wrapper (`gradlew`, `gradle/wrapper/gradle-wrapper.properties`) để build agent dùng đúng Gradle distribution.

## 5. Dependency cache hoạt động như thế nào?

Maven và Gradle đều lưu dependency đã tải về trên filesystem của build user. Nếu CodeBuild có thể khôi phục thư mục đó trước khi chạy build, build tool có thể dùng dependency cục bộ và chỉ tải phần còn thiếu.

Luồng cache:

    Build N
      |
      +-- Resolve dependency
      +-- Download missing artifacts
      +-- Compile / test / package
      +-- Save selected cache paths
                |
                v
          Cache storage
                |
                v
    Build N+1
      |
      +-- Restore cache paths
      +-- Resolve dependency
      +-- Download only missing/expired data
      +-- Compile / test / package

Cache không đảm bảo build chạy offline. Maven/Gradle vẫn có thể cần truy cập repository để kiểm tra metadata, lấy plugin chưa có, tải version mới hoặc xác thực artifact. Cache miss chỉ làm build tải lại dependency; nó không nên làm thay đổi kết quả logic của build.

Không nên dùng cache để che lỗi repository hoặc bỏ qua việc pin dependency. Build phải thành công từ cache rỗng trong một lần chạy độc lập.

## 6. Hai loại cache của CodeBuild

CodeBuild hỗ trợ hai loại cache cấp project:

| Loại | Lưu ở đâu | Ưu điểm | Hạn chế |
|---|---|---|---|
| Amazon S3 | S3 bucket/prefix cấu hình trong project | Dùng được giữa nhiều build host | Có thời gian upload/download cache; cần quyền S3 |
| Local | Build host của CodeBuild | Có thể khôi phục nhanh, không truyền cache qua S3 | Chỉ dùng được khi build chạy lại trên host có cache; không đảm bảo host được tái sử dụng |

### 6.1. Khi nên chọn S3 cache

S3 cache phù hợp khi build thường chạy trên host khác nhau hoặc dependency cache có kích thước nhỏ/trung bình và chi phí tải lại lớn hơn chi phí lưu/truyền cache.

S3 cache có thể dùng cache key, fallback keys, versioning và chia sẻ giữa các project. Khi cache key thay đổi theo dependency descriptor, CodeBuild có thể lưu cache riêng cho bộ dependency mới.

### 6.2. Khi nên chọn local cache

Local cache hữu ích với project build thường xuyên, cache lớn và build host có khả năng được tái sử dụng. Nó không phù hợp nếu build chạy thưa vì host có thể không còn cache khi build tiếp theo bắt đầu.

Local cache không phải một ổ đĩa bền vững. Không dựa vào nó để lưu artifact release hoặc dữ liệu bắt buộc phải tồn tại.

Nguồn: AWS CodeBuild — Cache builds to improve performance — https://docs.aws.amazon.com/codebuild/latest/userguide/build-caching.html

## 7. Ba local cache modes

Khi chọn cache type LOCAL, CodeBuild yêu cầu chọn một hoặc nhiều mode:

| Mode | Nội dung được cache | Khi phù hợp |
|---|---|---|
| LOCAL_SOURCE_CACHE | Git metadata của primary/secondary sources | Repository lớn, source checkout là phần tốn thời gian |
| LOCAL_DOCKER_LAYER_CACHE | Docker layers hiện có | Build hoặc pull Docker image lớn |
| LOCAL_CUSTOM_CACHE | Thư mục do buildspec chỉ định | Maven/Gradle dependency directories hoặc thư mục trung gian phù hợp |

Các lưu ý quan trọng:

- Docker layer cache chỉ hỗ trợ Linux và cần privileged mode.
- Privileged mode mở rộng quyền của build container tới thiết bị; cần đánh giá rủi ro bảo mật.
- Windows không hỗ trợ privileged mode.
- Custom cache chỉ nhận directory, không cache một file riêng lẻ.
- Custom cache dùng symlink để tham chiếu thư mục cache.
- Thư mục cache được liên kết vào build trước khi CodeBuild tải source. Nội dung cache có thể ghi đè nội dung source nếu trùng tên.
- AWS hiện ghi nhận local caching không hỗ trợ khi CodeBuild project được cấu hình chạy trong VPC; cũng có một số compute/environment types không hỗ trợ.

Với Java dependency cache, LOCAL_CUSTOM_CACHE thường là mode phù hợp. LOCAL_SOURCE_CACHE chỉ cache Git metadata, không thay thế Maven/Gradle cache. LOCAL_DOCKER_LAYER_CACHE chủ yếu dành cho Docker build.

Nguồn: AWS CodeBuild — Local caching — https://docs.aws.amazon.com/codebuild/latest/userguide/caching-local.html

## 8. Maven local repository

Maven lưu dependency, plugin và metadata tải về trong local repository. Đường dẫn mặc định là:

    ~/.m2/repository

Trong CodeBuild Linux image thông dụng chạy dưới root, đường dẫn thường là:

    /root/.m2/repository

CodeBuild và AWS CodeArtifact đưa ra ví dụ cache Maven path:

    cache:
      paths:
        - '/root/.m2/**/*'

Có thể thu hẹp path để chỉ cache repository:

    cache:
      paths:
        - '/root/.m2/repository/**/*'

Cách thứ hai tránh cache các file cấu hình user khác nằm trong `.m2`, ví dụ `settings.xml` nếu build environment lưu file đó ở đây.

Không cache file chứa credential của repository. Dùng CodeArtifact authorization hoặc secret provider để lấy credential lúc build, giữ file cấu hình có secret ngoài cache và không in token ra log.

Nguồn:
- AWS CodeArtifact dependency caching — https://docs.aws.amazon.com/codeartifact/latest/ug/dependency-caching.html
- Maven settings — https://maven.apache.org/settings.html

## 9. Gradle dependency cache

Gradle User Home mặc định là:

    ~/.gradle

Các dependency module thường nằm ở:

    ~/.gradle/caches/modules-2

CodeBuild/AWS CodeArtifact thường dùng path:

    /root/.gradle/caches/**/*

Có thể cache riêng dependency caches:

    cache:
      paths:
        - '/root/.gradle/caches/**/*'
        - '/root/.gradle/wrapper/dists/**/*'

`caches` chứa dependency metadata, downloaded modules và nhiều cache khác của Gradle. `wrapper/dists` lưu Gradle distribution được tải bởi Wrapper. Nếu build project đặt `GRADLE_USER_HOME` khác, phải đổi cache path theo biến đó.

Không nên cache tùy tiện toàn bộ home directory. `.gradle/gradle.properties` có thể chứa credentials; `init.d` có thể chứa script tùy biến. Cần giữ cache paths ở đúng thư mục dependency cần thiết.

### 9.1. Dependency cache khác Gradle build cache

Gradle có ít nhất hai khái niệm cần phân biệt:

- **Dependency cache:** lưu POM/module metadata và artifact dependency để tránh tải lại.
- **Build cache:** lưu output của task dựa trên input hash, giúp tránh thực thi lại task khi input tương đương.

Build cache có thể bật cho một lần chạy:

    ./gradlew --build-cache build

Hoặc bật trong `gradle.properties`:

    org.gradle.caching=true

Nếu chỉ cache dependency directories, Gradle có thể vẫn phải compile/test ở mỗi build. Muốn tái sử dụng task outputs cần bật và cấu hình Gradle build cache phù hợp. CodeBuild S3 cache có thể lưu thư mục `build-cache-1` trong Gradle User Home, nhưng đây vẫn là cơ chế cache cục bộ được truyền qua S3, không tự tạo remote Gradle Build Cache chuyên dụng.

Nguồn:
- Gradle dependency caching — https://docs.gradle.org/current/userguide/dependency_caching.html
- Gradle build cache — https://docs.gradle.org/current/userguide/build_cache.html
- Gradle directory layout — https://docs.gradle.org/current/userguide/directory_layout.html

## 10. Cache key và dependency descriptors

Cache key xác định cache snapshot mà CodeBuild tìm để restore. Nếu chỉ dùng một key cố định, những thay đổi dependency có thể dùng lại cache cũ. Tốt hơn là tạo key từ file mô tả dependency.

Ví dụ Maven:

    cache:
      key: "maven-java17-$(codebuild-hash-files '**/pom.xml')"
      fallback-keys:
        - maven-java17-
        - maven-
      paths:
        - '/root/.m2/repository/**/*'

Ví dụ Gradle:

    cache:
      key: "gradle-java17-$(codebuild-hash-files '**/build.gradle*' '**/settings.gradle*' 'gradle/libs.versions.toml' 'gradle.lockfile' 'gradle/wrapper/gradle-wrapper.properties')"
      fallback-keys:
        - gradle-java17-
        - gradle-
      paths:
        - '/root/.gradle/caches/**/*'
        - '/root/.gradle/wrapper/dists/**/*'

`codebuild-hash-files` là tiện ích CodeBuild tính SHA-256 trên các file khớp glob. Khi dependency descriptor đổi, key đổi và CodeBuild tìm cache mới theo key đó.

Với Maven multi-module, hash toàn bộ `pom.xml` giúp nhận biết thay đổi ở module con. Nếu dùng Maven Wrapper, có thể đưa `.mvn/wrapper/maven-wrapper.properties` vào danh sách hash. Với Gradle, đưa version catalog, lockfiles, settings/build scripts và wrapper properties vào key.

### 10.1. Fallback keys

CodeBuild tìm primary key trước. Nếu không có exact match, CodeBuild thử lần lượt fallback keys theo prefix search. Build có thể khôi phục cache cũ gần nhất rồi tạo cache cho primary key mới.

Tối đa năm fallback keys được hỗ trợ. `fallback-keys` bị bỏ qua nếu không có `key`.

Không dùng fallback key quá rộng giữa các runtime không tương thích hoặc project không cùng trust boundary. Ví dụ không chia sẻ cache Maven giữa Java 8 và Java 21 nếu plugin/dependency hoặc native artifact có thể khác.

### 10.2. Cache key không thay dependency locking

Cache key là cơ chế tìm cache, không phải bằng chứng dependency được pin hoặc xác minh integrity.

- Maven: khai báo version cụ thể, quản lý plugin version và tránh SNAPSHOT không kiểm soát.
- Gradle: dùng dependency locking/version catalog và dependency verification khi phù hợp.
- Thay dependency graph phải thay cache key.
- Khi nghi cache lỗi, chạy một build không cache hoặc xóa cache theo quy trình để so sánh.

Nguồn: AWS CodeBuild — S3 caching and cache keys — https://docs.aws.amazon.com/codebuild/latest/userguide/caching-s3.html

## 11. S3 cache trong buildspec

Project phải được cấu hình cache type S3 và trỏ tới cache bucket/prefix. Buildspec định nghĩa key và paths.

Ví dụ cấu hình project bằng CloudFormation:

    Cache:
      Type: S3
      Location: company-codebuild-cache
      CacheNamespace: java-builds

Phần buildspec:

    version: 0.2

    phases:
      build:
        commands:
          - mvn -B -ntp verify

    cache:
      key: "maven-java17-$(codebuild-hash-files '**/pom.xml')"
      fallback-keys:
        - maven-java17-
      paths:
        - '/root/.m2/repository/**/*'

Nếu không khai báo `cache.paths`, CodeBuild có thể best-effort cache một số dependency phổ biến, nhưng khai báo tường minh giúp dễ review và dự đoán hơn.

Các trường cache có thể dùng:

| Field | Ý nghĩa |
|---|---|
| key | Primary key được so khớp chính xác |
| fallback-keys | Prefix keys được tìm lần lượt khi primary miss |
| action: restore | Chỉ restore, không lưu thay đổi |
| action: save | Chỉ lưu, không restore |
| paths | File/directory được đưa vào cache |

Nếu không đặt action, CodeBuild mặc định restore và save.

S3 cache có thể được chia sẻ giữa các project khi chúng dùng cùng cacheNamespace, cùng key, cùng cache paths và cùng S3 bucket/prefix. Chỉ chia sẻ giữa các project có dependency/toolchain và quyền tin cậy tương đương.

## 12. Local custom cache cho Maven

Nếu project dùng local cache, chọn `LOCAL_CUSTOM_CACHE` ở phần cache của CodeBuild project. Ví dụ CloudFormation:

    Cache:
      Type: LOCAL
      Modes:
        - LOCAL_CUSTOM_CACHE

Buildspec khai báo path:

    version: 0.2

    phases:
      install:
        runtime-versions:
          java: corretto17
      build:
        commands:
          - mvn -B -ntp clean verify

    cache:
      paths:
        - '/root/.m2/repository/**/*'

Local custom cache chỉ hoạt động khi project bật đúng mode. Thêm `cache.paths` trong buildspec nhưng project dùng `NO_CACHE` sẽ không tự tạo cache.

## 13. Buildspec Maven hoàn chỉnh

Ví dụ project Spring Boot có Maven `finalName` là `orders-api`, Surefire/Failsafe xuất JUnit XML và executable JAR tại `target/orders-api.jar`.

    version: 0.2

    phases:
      install:
        runtime-versions:
          java: corretto17

      pre_build:
        commands:
          - java -version
          - mvn -version
          - echo "Starting Maven verification"

      build:
        commands:
          - mvn -B -ntp clean verify

      post_build:
        commands:
          - test -f target/orders-api.jar
          - sha256sum target/orders-api.jar > target/orders-api.jar.sha256
          - echo "Maven build completed"

    reports:
      junit:
        files:
          - 'target/surefire-reports/TEST-*.xml'
          - 'target/failsafe-reports/TEST-*.xml'
        file-format: JUNITXML

    artifacts:
      files:
        - 'target/orders-api.jar'
        - 'target/orders-api.jar.sha256'
      discard-paths: yes
      name: orders-api-$CODEBUILD_BUILD_NUMBER

    cache:
      key: "maven-java17-$(codebuild-hash-files '**/pom.xml')"
      fallback-keys:
        - maven-java17-
      paths:
        - '/root/.m2/repository/**/*'

Điểm cần điều chỉnh:

- `orders-api.jar` phải khớp tên file thực tế do Maven tạo. Nếu không dùng `finalName`, thay bằng đúng artifactId-version.
- Nếu có nhiều module, chỉ đưa executable module vào artifact chính hoặc khai báo secondary artifacts.
- `clean verify` chạy lifecycle tới verify, bao gồm compile, test và package theo cấu hình Maven project.
- `-B` bật batch mode; `-ntp` tắt transfer progress để log gọn.
- `sha256sum` là ví dụ cho Linux build image.
- `reports` dùng đường dẫn XML thật do Surefire/Failsafe plugin tạo.

## 14. Buildspec Gradle hoàn chỉnh

Ví dụ Spring Boot Gradle project có task `bootJar` tạo file `build/libs/orders-api.jar`:

    version: 0.2

    phases:
      install:
        runtime-versions:
          java: corretto17

      pre_build:
        commands:
          - java -version
          - ./gradlew --version
          - echo "Starting Gradle verification"

      build:
        commands:
          - ./gradlew --no-daemon clean test bootJar

      post_build:
        commands:
          - test -f build/libs/orders-api.jar
          - sha256sum build/libs/orders-api.jar > build/libs/orders-api.jar.sha256
          - echo "Gradle build completed"

    reports:
      junit:
        files:
          - '**/build/test-results/test/*.xml'
        file-format: JUNITXML

    artifacts:
      files:
        - 'build/libs/orders-api.jar'
        - 'build/libs/orders-api.jar.sha256'
      discard-paths: yes
      name: orders-api-$CODEBUILD_BUILD_NUMBER

    cache:
      key: "gradle-java17-$(codebuild-hash-files '**/build.gradle*' '**/settings.gradle*' 'gradle/libs.versions.toml' 'gradle.lockfile' 'gradle/wrapper/gradle-wrapper.properties')"
      fallback-keys:
        - gradle-java17-
      paths:
        - '/root/.gradle/caches/**/*'
        - '/root/.gradle/wrapper/dists/**/*'

`bootJar` yêu cầu Spring Boot Gradle plugin. Với ứng dụng Java không dùng Spring Boot, task đóng gói có thể là `jar`. Nếu build nhiều module, điều chỉnh glob reports và artifact path theo project layout.

`--no-daemon` tránh phụ thuộc vào daemon tồn tại giữa các build container. Gradle vẫn có thể dùng dependency cache và build cache trong Gradle User Home.

## 15. Đóng gói JAR/WAR đúng cách

Build command thành công chưa đủ; cần xác định file nào là sản phẩm được phát hành.

| Loại ứng dụng | Artifact thường gặp | Lưu ý |
|---|---|---|
| Java library | JAR | Có thể cần sources JAR, javadoc JAR và POM |
| Spring Boot service | Executable JAR | Kiểm tra manifest và boot loader |
| Java web app truyền thống | WAR | Phải khớp application server target |
| Lambda Java | ZIP/JAR hoặc shaded JAR | Theo packaging model của runtime/handler |
| Containerized service | Docker image trong ECR | Image digest thường là định danh deploy tốt hơn tag mutable |

Không nên dùng `artifacts.files: - '**/*'` cho release artifact nếu source tree chứa `.git`, cache, test reports, secret file hoặc file build trung gian. Chỉ chọn đúng file cần chuyển sang stage sau.

Với Spring Boot Maven, plugin thường tạo executable JAR trong `target`. Với Gradle, `bootJar` tạo executable JAR trong `build/libs`. Hãy kiểm tra file thực tế và tên file ổn định trước khi cấu hình artifacts.

### 15.1. Artifact name và versioning

Có thể gắn build number vào artifact name:

    artifacts:
      name: orders-api-$CODEBUILD_BUILD_NUMBER
      files:
        - 'target/orders-api.jar'

Artifact name có thể được tính tại build time bằng shell syntax hoặc CodeBuild environment variable. Kết hợp build number với commit SHA hoặc release version giúp truy vết build.

Không ghi đè artifact release đã được phê duyệt. Dùng versioned S3 bucket, S3 versioning hoặc naming convention immutable theo release policy.

### 15.2. Artifact path và base-directory

`artifacts.files` nhận path tương đối từ source build directory hoặc base-directory. Ví dụ:

    artifacts:
      base-directory: target
      files:
        - orders-api.jar
        - orders-api.jar.sha256

`discard-paths: yes` làm phẳng cấu trúc thư mục. Chỉ bật khi không cần giữ layout module. Nếu có nhiều file trùng tên ở nhiều thư mục, flatten có thể gây xung đột; giữ path mặc định khi cần phân biệt.

## 16. Test reports và coverage reports

CodeBuild có thể thu thập report từ file test/coverage được build tool tạo.

Với Maven Surefire, test report thường nằm trong:

    target/surefire-reports/TEST-*.xml

Với Maven Failsafe:

    target/failsafe-reports/TEST-*.xml

Với Gradle:

    build/test-results/test/*.xml

Ví dụ report JUnit:

    reports:
      junit:
        files:
          - 'target/surefire-reports/TEST-*.xml'
        file-format: JUNITXML

CodeBuild hỗ trợ nhiều định dạng test report như JUnit XML, NUnit, TestNG và Visual Studio TRX. Với coverage, CodeBuild hỗ trợ các định dạng như JaCoCo XML và Cobertura XML.

Reports khác artifacts:

- Reports được CodeBuild thu thập để hiển thị kết quả test/coverage.
- Artifacts được đóng gói và chuyển đến S3/CodePipeline hoặc đích được cấu hình.
- Một file có thể được dùng làm report và cũng có thể được đóng gói nếu cần, nhưng hai cấu hình có mục tiêu khác nhau.

Không dùng `on-failure: CONTINUE` để bỏ qua test failure rồi phát hành artifact như thể build đã pass. Nếu test thất bại, pipeline release nên dừng theo quality gate.

Nguồn: AWS CodeBuild Buildspec reference — https://docs.aws.amazon.com/codebuild/latest/userguide/build-spec-ref.html

## 17. Multi-module Maven và Gradle

Với monorepo hoặc multi-module project, cache key cần phản ánh toàn bộ dependency graph. Chỉ hash root POM hoặc root build file có thể không phát hiện thay đổi trong module con.

Maven:

    cache:
      key: "maven-$(codebuild-hash-files '**/pom.xml' '.mvn/wrapper/maven-wrapper.properties')"
      paths:
        - '/root/.m2/repository/**/*'

Gradle:

    cache:
      key: "gradle-$(codebuild-hash-files '**/build.gradle*' '**/settings.gradle*' '**/gradle.lockfile' 'gradle/libs.versions.toml' 'gradle/wrapper/gradle-wrapper.properties')"
      paths:
        - '/root/.gradle/caches/**/*'
        - '/root/.gradle/wrapper/dists/**/*'

Nếu mỗi service có dependency graph độc lập, cân nhắc cache key riêng theo service path, project name hoặc namespace. Điều này tránh project A làm cache của project B mất hiệu quả hoặc sử dụng nhầm dependency context.

Với Maven multi-module, artifact có thể chứa nhiều JAR. Hãy chọn module cần phát hành, không upload mọi JAR nếu pipeline chỉ deploy một service.

## 18. Dùng CodeArtifact làm nguồn dependency riêng tư

AWS CodeArtifact có thể làm Maven/Gradle package repository cho dependency nội bộ và proxy/upstream cho package công khai. Cache ở CodeBuild giúp giảm tải download lặp lại; CodeArtifact giúp kiểm soát nguồn package, version và quyền truy cập.

Luồng:

    CodeBuild service role
          |
          | Get authorization token
          v
      CodeArtifact
          |
          | Maven / Gradle resolve
          v
      Local dependency cache
          |
          v
      Compile / test / package

Với CodeArtifact, build role thường cần quyền lấy authorization token và đọc package từ repository. Nếu dùng KMS customer managed key, cần quyền liên quan phù hợp. Không hard-code token vào `pom.xml`, `settings.xml`, `build.gradle` hoặc buildspec.

CodeBuild buildspec hỗ trợ lấy environment variables từ Parameter Store và Secrets Manager. Tuy nhiên, secret masking chỉ che đúng giá trị đã lưu; nếu command encode, đổi case hoặc nối secret thành chuỗi khác, log có thể không che được chuỗi biến đổi. Tránh `set -x`, shell tracing và in toàn bộ environment variables.

## 19. Bảo mật cache và chống cache poisoning

Cache có thể chứa artifact do build trước tải về hoặc tạo ra. Nếu nhiều nhánh/project không cùng mức tin cậy dùng chung cache, build không tin cậy có thể ghi dữ liệu ảnh hưởng build sau.

Nguyên tắc:

- Tách cache namespace và S3 prefix giữa production/release branch với pull request không tin cậy.
- Không chia sẻ cache ghi được giữa fork/untrusted PR và release pipeline.
- Giới hạn IAM service role chỉ đọc/ghi cache prefix cần thiết.
- Bật encryption cho cache bucket; dùng SSE-S3 hoặc SSE-KMS theo yêu cầu.
- Không cache `settings.xml`, `gradle.properties`, credential files, private keys hoặc token.
- Không lưu secret trong artifact hoặc test report.
- Pin dependency và plugin version; xác minh checksum/signature khi hệ sinh thái hỗ trợ.
- Dùng lockfiles và dependency verification để phát hiện dependency graph hoặc artifact thay đổi bất thường.
- Không cho build job có quyền ghi cache production nếu job chỉ chạy test từ branch chưa tin cậy.

### 19.1. Maven cache và Gradle User Home

Maven local repository thường chứa JAR/POM và metadata, nhưng file `~/.m2/settings.xml` có thể chứa repository credentials. Chỉ cache `repository/**/*` khi phù hợp.

Gradle User Home có thể chứa `gradle.properties`, `init.d` scripts và cache metadata. Chỉ cache những thư mục dependency cần thiết; không cache cả `/root/.gradle/**/*` một cách không kiểm soát.

### 19.2. Cache và build isolation

Build không nên đọc cache do principal không tin cậy ghi vào. Tách CodeBuild project/service role/cache namespace theo trust boundary, hoặc dùng S3 bucket/prefix riêng. Khi cần tăng độ tin cậy, chạy một build clean không cache trước release quan trọng và so sánh artifact checksum.

## 20. Cache, reproducibility và dependency freshness

Cache tăng tốc nhưng không được làm build mất tính xác định.

Maven và Gradle có quy tắc riêng cho dynamic/changing dependencies. SNAPSHOT, version range và dynamic version có thể được refresh theo policy/TTL. Nếu pipeline dùng những dependency này, cùng một commit có thể resolve ra nội dung khác ở hai thời điểm.

Để build tái lập:

1. Pin dependency version.
2. Pin plugin và build tool version.
3. Dùng Maven Wrapper/Gradle Wrapper.
4. Dùng Gradle dependency locking và verification khi phù hợp.
5. Tránh version range và SNAPSHOT trong release build nếu không có quy trình kiểm soát.
6. Ghi commit SHA, runtime version và artifact checksum.
7. Thỉnh thoảng chạy build với cache rỗng để kiểm tra khả năng tái tạo.

`mvn -o` và `gradle --offline` chỉ nên dùng khi đã chắc cache chứa đủ dependencies/plugins. Không bật offline mode mặc định cho build cần giải quyết dependency mới.

## 21. Đo hiệu quả cache

Đừng chỉ bật cache rồi giả định build nhanh hơn. So sánh trước và sau theo số liệu.

| Chỉ số | Ý nghĩa |
|---|---|
| Build duration | Tổng thời gian build |
| Dependency resolution time | Thời gian Maven/Gradle resolve dependencies |
| Downloaded bytes | Dữ liệu tải từ repository |
| Cache restore/save duration | Chi phí tải và lưu cache |
| Cache hit/miss | Mức độ khớp key và cache availability |
| Test duration | Thời gian chạy test, không nhất thiết giảm nhờ dependency cache |
| Build failure rate | Phát hiện cache gây lỗi hoặc stale data |
| S3 storage/requests | Chi phí vận hành cache |

Cache có ích khi chi phí restore thấp hơn chi phí tải/biên dịch lại. Nếu cache rất lớn nhưng build chạy thưa, S3 transfer hoặc local host miss có thể khiến tổng thời gian không cải thiện.

Đo ít nhất một nhóm build cold-cache và một nhóm warm-cache với source/dependency tương đương. Đừng so sánh build khác nhau về test count, runtime, compute type hoặc dependency graph.

## 22. Troubleshooting các lỗi thường gặp

### 22.1. Cache không được khôi phục

Kiểm tra:

- Project cache type có phải S3/LOCAL đúng ý định không.
- Với local cache, mode LOCAL_CUSTOM_CACHE đã bật chưa.
- Cache path có đúng user home và đúng build image không.
- `GRADLE_USER_HOME` hoặc Maven local repository có bị override không.
- S3 role có quyền truy cập bucket/prefix và KMS key không.
- Cache key có thay đổi vì hash descriptor không.
- Build host có được tái sử dụng với local cache không.

### 22.2. Cache restore nhưng Maven vẫn tải dependency

Maven có thể cần metadata mới, plugin chưa cache, dependency version thay đổi hoặc artifact không có trong local repository. Kiểm tra `mvn -X` trong một lần debug có kiểm soát; tránh bật debug log thường xuyên nếu nó có thể in thông tin nhạy cảm.

### 22.3. Gradle vẫn resolve/download nhiều

Kiểm tra `GRADLE_USER_HOME`, Gradle Wrapper, lockfiles, repository configuration, dynamic versions và cache paths. Gradle có thể cần refresh metadata theo TTL hoặc build đang dùng Gradle version có cache format khác.

### 22.4. Build pass nhưng artifact không tồn tại

Kiểm tra Maven `finalName`, Gradle `bootJar`/`jar`, module đang build, path thực tế và `artifacts.files`. Có thể dùng lệnh `find target -maxdepth 2 -type f` hoặc `find build/libs -maxdepth 1 -type f` để debug trong Linux image, nhưng không đưa toàn bộ output directory vào release artifact nếu chưa lọc.

### 22.5. Test report không hiển thị

Kiểm tra Surefire/Failsafe/Gradle có sinh XML không, path glob có khớp không, file format có đúng JUnit XML không và test có thực sự chạy không. Nếu test bị skip hoặc build dừng trước phase test, report có thể không tồn tại.

### 22.6. Cache gây lỗi hoặc kết quả không nhất quán

Thử một build không cache. Nếu build clean thành công nhưng warm-cache thất bại, kiểm tra cache path có chứa output cũ, metadata của dependency thay đổi, build tool version mismatch hoặc cache bị ghi bởi build khác. Tạo cache key mới sau khi sửa dependency/toolchain.

## 23. Bài tập tình huống

### Bài A — Maven tải lại toàn bộ dependency mỗi build

CodeBuild project dùng S3 cache nhưng buildspec không có `cache.paths`.

**Đáp án:** khai báo `/root/.m2/repository/**/*` hoặc path local repository thực tế trong `cache.paths`, sau đó kiểm tra project cache type là S3 và IAM role có quyền.

### Bài B — Gradle cache không nằm ở `/root/.gradle`

Project đặt `GRADLE_USER_HOME=/opt/gradle-home`.

**Đáp án:** cache path phải đổi sang `/opt/gradle-home/caches/**/*` và wrapper distributions nếu cần.

### Bài C — Local cache không hoạt động trong VPC project

Build project chạy trong VPC và bật local custom cache.

**Đáp án:** theo giới hạn CodeBuild hiện hành, local caching không hỗ trợ khi project được cấu hình làm việc với VPC. Cân nhắc S3 cache.

### Bài D — CodeBuild chạy Linux Docker layer cache

Project bật LOCAL_DOCKER_LAYER_CACHE nhưng privileged mode tắt.

**Đáp án:** Docker layer cache cần Linux và privileged mode. Đánh giá security trước khi bật privileged mode.

### Bài E — Cache key không đổi dù dependency thay đổi

Cache key chỉ là `maven-java17`.

**Đáp án:** đưa hash các POM/lockfiles/build descriptors vào key để thay đổi dependency graph tạo cache key mới.

### Bài F — Một build từ fork ghi cache dùng chung với release

Build PR không tin cậy dùng cùng S3 cache namespace và quyền ghi như production.

**Đáp án:** tách cache namespace/bucket prefix và IAM role theo trust boundary. Không cho untrusted PR ghi cache mà release build tiêu thụ.

### Bài G — `settings.xml` bị đưa vào cache

Developer cache toàn bộ `/root/.m2/**/*`; file settings có server password.

**Đáp án:** thu hẹp cache path về `/root/.m2/repository/**/*`, lấy credential từ secret provider và rotate credential nếu đã bị lộ.

### Bài H — `artifacts.files` dùng `**/*`

Output ZIP chứa source, test reports và file cấu hình không cần thiết.

**Đáp án:** liệt kê đúng JAR/WAR, checksum và manifest cần phát hành; không gom toàn bộ source directory.

### Bài I — Maven build pass nhưng CodeBuild không upload JAR

Maven tạo `target/payment-service-1.2.0.jar`, buildspec trỏ `target/app.jar`.

**Đáp án:** sửa artifact path cho khớp file thực tế hoặc cấu hình `finalName` ổn định.

### Bài J — Gradle report không xuất hiện

Buildspec trỏ `target/surefire-reports`, nhưng project dùng Gradle.

**Đáp án:** dùng `build/test-results/test/*.xml` và file format JUNITXML.

### Bài K — Dùng offline mode trên cache rỗng

Build fail vì plugin chưa có trong local cache.

**Đáp án:** bỏ offline mode, cho phép resolve/download dependency. Chỉ dùng offline khi đã seed đầy đủ cache và có mục đích rõ.

### Bài L — Artifact thay đổi nhưng cùng version

Hai build tạo file `orders-api-1.0.0.jar` với nội dung khác nhau và upload cùng tên.

**Đáp án:** dùng artifact name/version theo build hoặc commit, giữ checksum, bật versioning/immutable release policy và không ghi đè release đã phê duyệt.

## 24. Câu hỏi ôn tập

1. Buildspec là gì và CodeBuild mặc định tìm file ở đâu?
2. Vì sao nên dùng buildspec version 0.2?
3. Bốn phase chính của buildspec là gì?
4. Dependency cache khác build artifact như thế nào?
5. Hai cache type chính của CodeBuild là gì?
6. S3 cache khác local cache ở điểm nào?
7. LOCAL_SOURCE_CACHE lưu nội dung gì?
8. LOCAL_DOCKER_LAYER_CACHE yêu cầu điều kiện gì?
9. LOCAL_CUSTOM_CACHE có thể cache một file riêng lẻ không?
10. Local cache có hoạt động trong mọi VPC CodeBuild project không?
11. Maven local repository mặc định nằm ở đâu?
12. Gradle dependency cache mặc định nằm ở đâu?
13. Vì sao không nên cache toàn bộ Maven/Gradle user home?
14. Cache key nên dựa vào những file nào?
15. `codebuild-hash-files` làm nhiệm vụ gì?
16. Fallback key được tìm như thế nào?
17. Có tối đa bao nhiêu fallback keys?
18. `cache/action: restore` có lưu cache mới không?
19. Vì sao cache key không thay dependency locking?
20. Maven `verify` có bao gồm package lifecycle không?
21. Gradle `bootJar` dùng trong trường hợp nào?
22. Maven Surefire XML thường nằm ở đâu?
23. Gradle JUnit XML thường nằm ở đâu?
24. `artifacts.files` xác định điều gì?
25. `discard-paths: yes` làm thay đổi cấu trúc artifact thế nào?
26. Vì sao không nên dùng `**/*` cho mọi release artifact?
27. CodeArtifact có vai trò gì trong dependency management?
28. Vì sao không lưu repository token trong buildspec?
29. Cache poisoning có thể ảnh hưởng release pipeline như thế nào?
30. Khi nào nên chạy build không cache?

**Đáp án nhanh:** (1) YAML chỉ dẫn build, mặc định root source; (2) các lệnh cùng phase dùng chung shell context; (3) install, pre_build, build, post_build; (4) cache tăng tốc, artifact là đầu ra chuyển stage; (5) S3 và LOCAL; (6) S3 chia sẻ qua host, local gắn build host; (7) Git metadata; (8) Linux và privileged mode; (9) không, chỉ directory; (10) không; (11) `~/.m2/repository`; (12) `~/.gradle/caches`; (13) có thể chứa settings/credentials/scripts; (14) POM, Gradle scripts, version catalog, lockfiles, wrapper properties; (15) tạo SHA-256 từ file khớp glob; (16) prefix search lần lượt sau primary miss; (17) năm; (18) không; (19) key chỉ tìm cache, không pin graph; (20) có; (21) Spring Boot executable JAR; (22) `target/surefire-reports`; (23) `build/test-results/test`; (24) file được upload; (25) làm phẳng đường dẫn; (26) có thể lẫn source/secrets/build output; (27) repository package riêng tư/proxy; (28) tránh lộ credential; (29) build không tin cậy có thể đầu độc cache; (30) kiểm tra reproducibility hoặc điều tra cache issue.

## 25. Checklist production

- [ ] Buildspec dùng version 0.2.
- [ ] CodeBuild image và Java runtime được chọn/pin có chủ đích.
- [ ] Maven Wrapper hoặc Gradle Wrapper được commit và version được pin.
- [ ] Maven/Gradle dependency versions và plugins được quản lý rõ.
- [ ] Cache type S3/LOCAL phù hợp tần suất và môi trường.
- [ ] Cache paths đúng với Maven local repository hoặc Gradle User Home thực tế.
- [ ] Cache key hash dependency descriptors/lockfiles.
- [ ] Fallback keys không vượt qua ranh giới project/runtime/trust.
- [ ] Không cache settings.xml, gradle.properties chứa secret hoặc private key.
- [ ] S3 cache bucket/prefix có encryption và IAM least privilege.
- [ ] Local cache mode đúng và đáp ứng giới hạn VPC/compute/image.
- [ ] Docker layer cache chỉ bật khi thật sự cần và đã đánh giá privileged mode.
- [ ] Build chạy được từ cache rỗng.
- [ ] Release build không phụ thuộc SNAPSHOT/dynamic dependency không kiểm soát.
- [ ] Maven/Gradle build command chạy test và package đúng lifecycle.
- [ ] Test reports trỏ đúng XML output path.
- [ ] Artifacts chỉ gồm JAR/WAR/checksum/manifest cần phát hành.
- [ ] Artifact name có build identity hoặc release version.
- [ ] Artifact output bucket được mã hóa và có retention/versioning phù hợp.
- [ ] Cache không được dùng thay artifact repository/release storage.
- [ ] Build logs không in token, secret hoặc toàn bộ environment.
- [ ] Có số liệu cold-cache/warm-cache và theo dõi cache hit/miss.
- [ ] Có quy trình tạo cache key mới hoặc chạy no-cache khi nghi cache corruption.

## 26. Tổng kết

AWS CodeBuild cache và artifact packaging giải quyết hai nhu cầu riêng trong CI/CD Java:

- Cache Maven/Gradle dependency giúp giảm tải download lặp lại.
- S3 cache dùng được qua nhiều build host; local cache có thể nhanh hơn nhưng phụ thuộc build host và cache mode.
- LOCAL_SOURCE_CACHE lưu Git metadata, LOCAL_DOCKER_LAYER_CACHE lưu Docker layers, LOCAL_CUSTOM_CACHE lưu các thư mục buildspec chỉ định.
- Maven thường dùng `/root/.m2/repository`; Gradle thường dùng `/root/.gradle/caches`.
- Cache key nên thay đổi theo POM, Gradle scripts, version catalog, lockfiles và wrapper version.
- Cache không thay dependency locking, checksum verification hoặc khả năng build từ cache rỗng.
- Buildspec version 0.2 định nghĩa phase, test reports và artifact output.
- Artifacts phải chỉ rõ executable JAR/WAR cần chuyển sang stage tiếp theo; test reports được cấu hình riêng.
- S3 cache cần IAM, encryption và phân vùng theo trust boundary; không để untrusted PR ghi cache mà production release tiêu thụ.
- Đo cold-cache/warm-cache để xác định cache thực sự tiết kiệm thời gian và chi phí.

Một pipeline Java tốt tạo được artifact có thể truy vết, kiểm thử được và tái tạo từ source cùng dependency đã kiểm soát. Cache chỉ giúp pipeline làm việc đó nhanh hơn.

### Tài liệu AWS và nhà cung cấp chính thức

1. AWS CodeBuild buildspec reference: https://docs.aws.amazon.com/codebuild/latest/userguide/build-spec-ref.html
2. AWS CodeBuild cache builds: https://docs.aws.amazon.com/codebuild/latest/userguide/build-caching.html
3. AWS CodeBuild S3 caching: https://docs.aws.amazon.com/codebuild/latest/userguide/caching-s3.html
4. AWS CodeBuild local caching: https://docs.aws.amazon.com/codebuild/latest/userguide/caching-local.html
5. Specify a local cache: https://docs.aws.amazon.com/codebuild/latest/userguide/specify-caching-local.html
6. Create a CodeBuild project: https://docs.aws.amazon.com/codebuild/latest/userguide/create-project.html
7. Getting started with CodeBuild: https://docs.aws.amazon.com/codebuild/latest/userguide/getting-started-overview.html
8. AWS CodeArtifact dependency caching: https://docs.aws.amazon.com/codeartifact/latest/ug/dependency-caching.html
9. Maven settings reference: https://maven.apache.org/settings.html
10. Maven local repository configuration: https://maven.apache.org/guides/mini/guide-configuring-maven.html
11. Gradle dependency caching: https://docs.gradle.org/current/userguide/dependency_caching.html
12. Gradle build cache: https://docs.gradle.org/current/userguide/build_cache.html
13. Gradle directory layout: https://docs.gradle.org/current/userguide/directory_layout.html
14. Gradle security guidance: https://docs.gradle.org/current/userguide/securing_builds.html
