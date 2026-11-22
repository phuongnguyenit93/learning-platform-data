# Build một lần và chuyển đúng artifact đã kiểm chứng qua các môi trường

Một pipeline CI/CD đáng tin cậy tạo **một bản build đã được kiểm thử**, lưu nó thành artifact bất biến, rồi promote chính artifact đó qua Development, Staging và Production. Mỗi môi trường nhận cùng một JAR/WAR hoặc cùng một OCI image digest; chỉ cấu hình runtime, secrets, endpoint, tài nguyên và quyền triển khai thay đổi theo môi trường.

Đó là nguyên tắc **Build once, promote many**.

Ví dụ, CI build Spring Boot service từ Git commit `a83f1c2` thành:

~~~text
Artifact: orders-api-1.8.0.jar
SHA-256:  <digest thực tế do CI tính>
Source:   a83f1c2
Build:    run-4821
~~~

Sau khi kiểm thử và kiểm tra bảo mật đạt yêu cầu, artifact được đưa vào repository. Development, Staging và Production đều tải đúng artifact này, xác minh checksum/chữ ký rồi triển khai. Pipeline **không chạy lại Gradle/Maven để tạo một JAR khác cho từng môi trường**.

Nếu dùng container, ý tưởng tương tự: build image một lần, push vào registry, ghi lại digest và triển khai cùng reference dạng `registry/team/orders-api@sha256:...` qua từng môi trường.

## 1. Vì sao cần build một lần?

Một quy trình dễ gây sai lệch là build riêng cho từng environment:

~~~text
Source commit
   |
   +--> Build for Development --> orders-api.jar (A)
   |
   +--> Build for Staging -----> orders-api.jar (B)
   |
   +--> Build for Production --> orders-api.jar (C)
~~~

Dù cùng branch hoặc cùng version string, ba lần build có thể nhận dependency khác, plugin khác, JDK khác, generated timestamp khác hoặc environment variables khác. Kết quả là A, B và C không nhất thiết chứa cùng bytes. Nếu Staging đã kiểm thử A nhưng Production chạy C, bạn chưa thực sự triển khai binary đã được kiểm thử.

Quy trình build-once:

~~~text
                Git commit
                    |
                    v
             Build + test once
                    |
                    v
             Package artifact
                    |
                    v
        Verify + checksum + signature
                    |
                    v
        Immutable artifact repository
                    |
          +---------+----------+
          |         |          |
          v         v          v
       Dev deploy  Stage     Production
          |         |          |
          +---------+----------+
          Same artifact bytes / image digest
~~~

Lợi ích:

- **Tính nhất quán:** binary đã test ở Staging là binary được đưa lên Production.
- **Khả năng truy xuất:** biết artifact đến từ commit, workflow run và toolchain nào.
- **Rollback chính xác:** triển khai lại một version/digest đã biết.
- **Kiểm soát thay đổi:** chỉ cấu hình và trạng thái môi trường khác nhau.
- **Giảm sai lệch:** không để việc build trong mỗi môi trường vô tình tạo artifact khác.
- **Audit rõ ràng:** mỗi lần promotion có người duyệt, thời điểm, môi trường và digest.

### Artifact là gì?

Artifact là **đầu ra đã đóng gói của build**, chẳng hạn:

- Executable Spring Boot JAR hoặc WAR.
- OCI container image.
- Archive/distribution ZIP chứa ứng dụng và các file cần thiết.
- Metadata liên quan như checksum, signature, SBOM và provenance.

Source code, Gradle cache, Maven local repository và container build cache **không phải** artifact release mà môi trường triển khai cần nhận. Một release record có thể tham chiếu nhiều file, nhưng phải xác định rõ file nào là deployable artifact.

## 2. Phân biệt build, verify, publish, promote và deploy

| Giai đoạn | Việc thực hiện | Đầu ra / điều kiện hoàn thành |
| --- | --- | --- |
| Build | Checkout đúng commit, resolve dependencies, compile, package | JAR/WAR hoặc OCI image mới |
| Verify | Unit/integration tests, kiểm tra dependency, checksum, signature, scan | Kết quả QA và bằng chứng xác minh |
| Publish | Đưa artifact đã xác minh vào repository/registry | Một version hoặc digest có thể truy xuất |
| Promote | Cho phép cùng artifact đi tới môi trường tiếp theo | Trạng thái promotion và approval |
| Deploy | Cài/chạy artifact trong môi trường đích | Instance/container đang chạy đúng digest |
| Validate | Smoke test, health check, contract/monitoring | Kết quả sau triển khai |

**Publish và deploy không phải cùng một hành động.** Publish lưu artifact vào repository để có thể lấy lại; deploy đưa artifact vào một môi trường chạy. Maven phase `deploy` có nghĩa là publish artifact lên remote repository, không phải mặc định triển khai ứng dụng lên Production.

**Promote cũng không phải build lại.** Với repository manager, promotion có thể là chuyển staging repository sang trạng thái release, đổi visibility hoặc gắn metadata. Với OCI image, có thể thêm một tag mới cho cùng image digest. Trong cả hai trường hợp, nội dung artifact phải giữ nguyên.

## 3. Điều gì giữ nguyên và điều gì thay đổi theo môi trường?

| Thành phần | Giữ nguyên giữa các môi trường? | Ví dụ |
| --- | --- | --- |
| JAR/WAR bytes | Có | `orders-api-1.8.0.jar` |
| OCI image digest | Có | `sha256:...` |
| Maven GAV/release version | Có | `com.example:orders-api:1.8.0` |
| Git commit/build provenance | Có | `a83f1c2` / run 4821 |
| Spring profile | Có thể khác | `development`, `staging`, `production` |
| Database URL | Có thể khác | DB của từng môi trường |
| Credentials/API tokens | Có thể khác | Secret store theo môi trường |
| Feature flags | Có thể khác | Bật dần tính năng |
| CPU/RAM/replica count | Có thể khác | Resource limits và autoscaling |
| Deployment approval | Có thể khác | Production cần reviewer |

### Cấu hình runtime ở bên ngoài binary

Spring Boot có thể đọc cấu hình từ environment variables, external config files, Config Server, Kubernetes ConfigMaps/Secrets hoặc secret manager.

Ví dụ cùng một JAR được chạy với profile khác nhau:

~~~bash
java -jar orders-api-1.8.0.jar --spring.profiles.active=staging
~~~

~~~bash
java -jar orders-api-1.8.0.jar --spring.profiles.active=production
~~~

Hai lệnh dùng **cùng file JAR**; Spring Environment nhận profile khác nhau. Nếu triển khai container, có thể truyền:

~~~bash
docker run -e SPRING_PROFILES_ACTIVE=staging registry.example.test/team/orders-api@sha256:...
~~~

`registry.example.test` và digest là giá trị minh họa; thay bằng registry/reference thực tế.

Không đóng database password, API key, token hoặc private certificate vào JAR/image. Cấp chúng lúc runtime qua secret store có phân quyền và audit.

### Đừng dùng build profile để tạo binary riêng cho từng environment

Cần phân biệt:

- **Spring profile runtime:** chọn cấu hình khi ứng dụng khởi động.
- **Maven build profile / Gradle project property:** có thể thay dependency, resource filtering, compiler options hoặc nội dung artifact trong lúc build.

Nếu `-Pproduction` làm Maven/Gradle đóng gói một JAR khác `-Pstaging`, pipeline đã tạo các artifact riêng. Dùng runtime configuration cho endpoint, credentials và feature flags; giữ build inputs giống nhau cho release.

Một số giá trị thực sự phải được xác định lúc build (ví dụ compile target, native binary, static frontend bundle) cần có chính sách riêng. Nếu artifact phụ thuộc platform/architecture, tạo một artifact cho từng target rõ ràng và promote đúng artifact tương ứng, không âm thầm rebuild theo môi trường.

## 4. Version, checksum và danh tính của bản build

Một release nên có **một định danh ổn định** và bằng chứng cho biết nó đến từ đâu.

~~~text
Product:             Orders API
Artifact:            orders-api-1.8.0.jar
Coordinates:         com.example:orders-api:1.8.0
Git commit:          <full commit trong CI>
Build run:           4821
JDK:                 <bản thực tế>
Gradle:              <Wrapper version>
SHA-256:             <digest tính từ file>
Signature:           <signature/key identity nếu có>
SBOM:                <file/reference nếu có>
Built at:            <UTC timestamp>
~~~

Các giá trị trong ngoặc là trường cần lấy từ hệ thống build thật, không điền giả.

### Version phải bất biến

Dùng release version duy nhất, ví dụ `1.8.0`. Repository release nên được cấu hình **không cho ghi đè cùng tọa độ** bằng bytes mới. Không build lại rồi publish artifact khác dưới cùng `com.example:orders-api:1.8.0`.

Tránh dùng `SNAPSHOT`, dynamic dependency versions hoặc tag `latest` cho release cần promotion. Nếu build candidate có nhiều lần thử, gắn build ID hoặc release candidate version riêng; chỉ chọn một candidate đã xác minh để promote.

### SHA-256 kiểm tra file tải xuống

Sau khi build:

~~~bash
sha256sum orders-api-1.8.0.jar > SHA256SUMS
~~~

Sau khi tải artifact ở một môi trường khác:

~~~bash
sha256sum --check SHA256SUMS
~~~

Khi checksum khớp, file tải xuống có cùng bytes với file đã được tính hash. Tuy nhiên, nếu attacker thay cả JAR và checksum trong cùng một nguồn không đáng tin, hai file vẫn có thể khớp. Với release quan trọng, lấy manifest/checksum từ nguồn được bảo vệ, xác minh signature hoặc provenance và kiểm soát quyền ghi repository.

### Signature và provenance

- **Checksum:** xác nhận bytes so với digest kỳ vọng.
- **Digital signature:** xác minh dữ liệu được ký bởi khóa/identity được tin cậy.
- **Build provenance/attestation:** ghi lại source, builder/workflow và thông tin tạo artifact.
- **SBOM:** liệt kê các thành phần phần mềm trong artifact/image.

Không có một lớp nào thay thế hoàn toàn các lớp còn lại. Xác minh signature thành công không có nghĩa artifact không có CVE; SBOM có mặt cũng không chứng minh source commit được build đúng. Hãy áp dụng policy phù hợp và lưu kết quả kiểm tra.

## 5. Làm cho lần build đầu tiên có thể kiểm soát và truy xuất

Build-once bảo đảm các môi trường dùng cùng một artifact. Nó **khác với reproducible build**:

- **Build once, promote many:** không tạo lại artifact khi chuyển qua các môi trường.
- **Reproducible build:** một người/máy độc lập có thể build lại từ cùng source, environment và instructions để thu được bytes giống nhau.

Reproducibility là bằng chứng mạnh hơn cho tính tái lập của quy trình. Nhưng kể cả chưa đạt bit-for-bit reproducibility, pipeline vẫn có thể promote chính xác artifact đã build nếu lưu trữ và kiểm soát integrity đúng cách.

### Cố định build inputs với Gradle

- Commit Gradle Wrapper và pin version.
- Khai báo Java toolchain rõ ràng.
- Pin plugin versions.
- Dùng dependency locking cho các configurations cần thiết.
- Dùng dependency verification metadata khi cần kiểm tra checksums/signatures.
- Hạn chế dynamic/changing dependencies trong release.
- Không để build phụ thuộc dữ liệu không kiểm soát từ environment.

Ví dụ bật dependency locking:

~~~groovy
dependencyLocking {
    lockAllConfigurations()
}
~~~

Tạo/cập nhật lock state:

~~~bash
./gradlew dependencies --write-locks
~~~

Commit lockfiles vào version control sau khi review. Locking cố định version đã resolve, nhưng không tự bảo đảm artifact bytes ở mọi repository giống nhau; có thể kết hợp dependency verification.

Tham khảo [Gradle Dependency Locking](https://docs.gradle.org/current/userguide/dependency_locking.html) và [Dependency Verification](https://docs.gradle.org/current/userguide/dependency_verification.html).

### Cố định build inputs với Maven

- Commit Maven Wrapper nếu project dùng wrapper.
- Pin plugin/dependency versions và quản lý parent/BOM rõ ràng.
- Tránh version ranges/changing snapshots trong release.
- Dùng dependency convergence/enforcer rules nếu phù hợp.
- Thiết lập reproducible archive timestamp và dùng plugin versions hỗ trợ reproducible builds.
- Ghi JDK, Maven và OS/platform thực tế trong build record.

Maven có property `project.build.outputTimestamp` để hỗ trợ reproducible builds:

~~~xml
<properties>
    <project.build.outputTimestamp>2026-01-01T00:00:00Z</project.build.outputTimestamp>
</properties>
~~~

Đây là timestamp minh họa cố định; trong project thật chọn giá trị theo release policy. Chỉ cấu hình timestamp chưa đủ: các plugin và build inputs khác cũng phải hỗ trợ reproducibility.

Xem [Maven Reproducible Builds](https://maven.apache.org/guides/mini/guide-reproducible-builds.html).

### Kiểm thử đúng artifact sẽ phát hành

Nên chạy kiểm thử trước khi publish:

1. Compile và unit tests.
2. Integration tests với dependencies cần thiết.
3. Package executable JAR/WAR hoặc image.
4. Smoke test chính artifact đã đóng gói, không chỉ class files trong test task.
5. Dependency/security/license scans theo policy.
6. Checksum, signature và provenance.
7. Lưu artifact cùng metadata vào immutable store.

Một kiểm thử sau package có thể phát hiện lỗi khác với unit tests, ví dụ thiếu resource, manifest sai hoặc dependency runtime không được đóng gói.

## 6. Thực hành Gradle: publish một executable Spring Boot JAR một lần

Ví dụ dùng Java 17 và Spring Boot Gradle plugin. Mục tiêu tạo `orders-api-1.8.0.jar`, kiểm thử và publish đúng file đó vào một Maven-compatible repository.

### 6.1. Cấu hình `build.gradle`

~~~groovy
import org.gradle.api.credentials.PasswordCredentials
import org.gradle.api.publish.maven.MavenPublication

plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'maven-publish'
}

group = 'com.example'
version = providers.gradleProperty('releaseVersion').getOrElse('0.0.0-dev')

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('bootJar') {
    archiveFileName.set('orders-api-' + project.version + '.jar')
}

publishing {
    publications {
        app(MavenPublication) {
            groupId = project.group.toString()
            artifactId = 'orders-api'
            version = project.version.toString()
            artifact(tasks.named('bootJar'))
        }
    }

    repositories {
        maven {
            name = 'releaseRepo'
            url = uri(providers.gradleProperty('releaseRepoUrl').getOrElse(
                layout.buildDirectory.dir('staging-repo').get().asFile.toURI().toString()
            ))
            credentials(PasswordCredentials)
        }
    }
}
~~~

Các phần cần hiểu:

- `releaseVersion` được truyền từ release tag/CI, không lấy từ tên môi trường.
- `bootJar` tạo executable archive; task publish dùng chính output của task đó làm publication artifact.
- Maven publication có tọa độ `com.example:orders-api:1.8.0` khi version là 1.8.0.
- `releaseRepo` là repository đích. Gradle có thể lấy credentials theo repository name từ properties `releaseRepoUsername` và `releaseRepoPassword`.
- Trong CI, truyền credentials qua environment properties như `ORG_GRADLE_PROJECT_releaseRepoUsername` và `ORG_GRADLE_PROJECT_releaseRepoPassword`. Không commit password vào `gradle.properties`.
- Repository URL fallback là local staging folder để tiện thử nghiệm; release job thực tế phải truyền URL của repository được quản trị.

Ví dụ này publish executable Boot JAR như **một file phân phối để triển khai**. Nó không khai báo `from components.java` như một library thông thường; consumer không nên hiểu publication này là API library có dependency graph đầy đủ để dùng làm compile classpath.

### 6.2. Build, test và publish đúng một lần

Từ project root:

~~~bash
./gradlew clean test bootJar -PreleaseVersion=1.8.0
~~~

Kiểm tra file:

~~~text
build/libs/orders-api-1.8.0.jar
~~~

Tính checksum:

~~~bash
cd build/libs
sha256sum orders-api-1.8.0.jar > SHA256SUMS
~~~

Sau khi build và test đạt, publish:

~~~bash
cd ../..
./gradlew publish -PreleaseVersion=1.8.0 -PreleaseRepoUrl=https://repo.example.test/releases
~~~

Trong CI, credentials được cấp qua environment properties nêu trên. URL `repo.example.test` là hostname ví dụ, không phải repository có thật.

Gradle Maven Publish tạo task publish theo publication/repository đã cấu hình. Lệnh `publish` publish các publications tới repositories được khai báo. Để không vô tình tạo một artifact khác, release pipeline nên dùng cùng commit, version và build output đã qua QA; không chạy một build khác để phục vụ từng môi trường.

Tài liệu: [Gradle Maven Publish Plugin](https://docs.gradle.org/current/userguide/publishing_maven.html).

### 6.3. Promotion và deployment

Repository có thể chứa:

~~~text
com/example/orders-api/1.8.0/
    orders-api-1.8.0.jar
    orders-api-1.8.0.pom
    checksums/signatures (nếu được cấu hình)
~~~

Development tải artifact `com.example:orders-api:1.8.0`, xác minh checksum rồi triển khai. Khi kiểm thử đạt, Staging và Production lấy **cùng tọa độ release và cùng bytes** từ repository.

Nếu repository manager có staging/promote workflow, hãy promote release repository/metadata theo cơ chế của sản phẩm đó. Không rebuild rồi upload đè lên version `1.8.0`.

## 7. Maven tương đương: deploy artifact một lần

Trong Maven, phase `deploy` của default lifecycle publish artifact cuối cùng lên remote repository. `mvn clean deploy` chạy các phase trước đó theo thứ tự: validate, compile, test, package, verify, install rồi deploy. Nó không phải lệnh deploy ứng dụng lên Production. [Maven Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html).

### 7.1. Khai báo repository đích trong POM

~~~xml
<distributionManagement>
    <repository>
        <id>internal-releases</id>
        <url>https://repo.example.test/maven/releases</url>
    </repository>
</distributionManagement>
~~~

Đây là phần cấu hình bên trong `pom.xml`. Credentials tương ứng được đặt trong Maven `settings.xml` theo cùng server ID:

~~~xml
<settings>
    <servers>
        <server>
            <id>internal-releases</id>
            <username>USERNAME_FROM_SECRET_STORE</username>
            <password>PASSWORD_FROM_SECRET_STORE</password>
        </server>
    </servers>
</settings>
~~~

Đây là cấu trúc minh họa, không điền credential thật vào source control. CI tạo/cấp settings bảo mật từ secret manager hoặc credentials mechanism của hệ thống.

### 7.2. Build và publish một lần

~~~bash
mvn clean verify deploy
~~~

Sau khi hoàn tất, artifact được lưu trong remote Maven repository theo GAV đã khai báo. Các deployment jobs tiếp theo tải đúng release version từ repository; **không chạy lại `mvn package` hoặc `mvn deploy` cho mỗi environment**.

Maven Deploy Plugin cũng có goal `deploy:deploy-file` để upload file đã được build ở nơi khác. Khi dùng goal này, phải cung cấp đúng file, GAV và repository; không được build lại một artifact mới chỉ để đổi nơi triển khai. Xem [Maven Deploy Plugin](https://maven.apache.org/plugins/maven-deploy-plugin-4.x/usage.html).

### 7.3. Cấu hình Maven không được làm thay artifact theo environment

Không dùng Maven profile `dev`, `staging`, `prod` để thay dependency/resource filtering hoặc đóng credentials vào JAR nếu mục tiêu là promote cùng binary. Dùng Spring runtime profile hoặc external configuration cho phần thay đổi giữa các môi trường.

## 8. Container image: promote bằng digest thay vì chỉ tag

Nếu ứng dụng được đóng gói thành OCI image, image tag có thể dễ đọc:

~~~text
registry.example.test/team/orders-api:1.8.0
~~~

Nhưng tag có thể được gắn lại vào một image khác nếu registry policy cho phép. **Digest là content-addressed identifier** cho nội dung image. Docker cho phép pull image bằng digest để pin chính xác một version của image. [Docker pull by digest](https://docs.docker.com/reference/cli/docker/image/pull/).

Sau khi build và push image một lần:

~~~bash
docker push registry.example.test/team/orders-api:1.8.0
~~~

Registry/CLI trả digest của image đã push. Lưu giá trị thật vào release record, ví dụ dạng:

~~~text
registry.example.test/team/orders-api@sha256:<actual-digest>
~~~

Triển khai cùng reference qua các môi trường:

~~~bash
docker pull registry.example.test/team/orders-api@sha256:<actual-digest>
~~~

Trong Kubernetes, image field của Deployment cũng có thể dùng reference theo digest. Ví dụ:

~~~yaml
spec:
  template:
    spec:
      containers:
        - name: orders-api
          image: registry.example.test/team/orders-api@sha256:<actual-digest>
~~~

`<actual-digest>` là placeholder phải thay bằng digest thực tế. Không commit một digest giả vào manifest production.

### Nếu dùng Spring Boot Cloud Native Buildpacks

Có thể tạo OCI image trực tiếp từ executable archive bằng `bootBuildImage` hoặc Maven `spring-boot:build-image`. Cấu hình image name trỏ tới registry và bật publish theo policy khi muốn push. Sau khi image đã push, lấy digest từ output/registry rồi dùng digest này cho mọi môi trường.

Không chạy lại buildpacks với tag/environment khác cho từng stage nếu yêu cầu là cùng một image. Nếu muốn thêm tag như `staging` hoặc `production`, tag đó phải trỏ tới **cùng digest**.

### Tag không phải digest

~~~text
orders-api:1.8.0       -> tên dễ đọc, có thể bị retag
orders-api@sha256:...  -> tham chiếu nội dung cụ thể
~~~

Dùng tag để tìm artifact và hiển thị release; dùng digest để xác minh/deploy chính xác. Sau mỗi lần push, ghi digest registry thực trả về, không tính digest bằng cách hash một tar export không tương đương với manifest digest của registry.

## 9. GitHub Actions: build một lần, ba môi trường dùng cùng artifact

Ví dụ sau minh họa workflow cho release tag `v1.8.0`:

- Build job chạy tests và tạo JAR **một lần**.
- Upload một workflow artifact có tên gắn với Git commit.
- Development, Staging và Production lần lượt download đúng workflow artifact đó.
- Mỗi job kiểm tra SHA-256 trước khi gọi deploy script.
- GitHub Environments có thể áp dụng required reviewers cho Staging/Production.

Các action versions trong ví dụ là major tags được tài liệu GitHub công bố tại thời điểm soạn bài: checkout v7, setup-java v6, upload-artifact v7 và download-artifact v8. Với hệ thống cần kiểm soát supply chain chặt, pin từng action tới full commit SHA đã review thay vì chỉ dùng major tag.

### 9.1. File workflow

Tạo `.github/workflows/release.yml`:

~~~yaml
name: Build once and promote

on:
  push:
    tags:
      - 'v*'

permissions:
  contents: read

jobs:
  build:
    runs-on: ubuntu-latest
    outputs:
      version: ${{ steps.meta.outputs.version }}

    steps:
      - uses: actions/checkout@v7

      - uses: actions/setup-java@v6
        with:
          distribution: temurin
          java-version: '17'

      - id: meta
        shell: bash
        run: |
          RELEASE_VERSION="$(printf '%s' "$GITHUB_REF_NAME" | sed 's/^v//')"
          echo "version=$RELEASE_VERSION" >> "$GITHUB_OUTPUT"

      - name: Build and test once
        run: |
          ./gradlew --no-daemon clean test bootJar \
            -PreleaseVersion="${{ steps.meta.outputs.version }}"

      - name: Create checksum manifest
        env:
          RELEASE_VERSION: ${{ steps.meta.outputs.version }}
        run: |
          cd build/libs
          sha256sum "orders-api-$RELEASE_VERSION.jar" > SHA256SUMS

      - name: Upload immutable release artifact
        uses: actions/upload-artifact@v7
        with:
          name: orders-api-${{ github.sha }}
          path: |
            build/libs/orders-api-*.jar
            build/libs/SHA256SUMS
          if-no-files-found: error
          retention-days: 30

  deploy-development:
    needs: build
    runs-on: ubuntu-latest
    environment: development

    steps:
      - uses: actions/checkout@v7

      - uses: actions/download-artifact@v8
        with:
          name: orders-api-${{ github.sha }}
          path: release

      - name: Verify downloaded artifact
        working-directory: release
        run: sha256sum --check SHA256SUMS

      - name: Deploy the same JAR
        env:
          RELEASE_VERSION: ${{ needs.build.outputs.version }}
        run: |
          ./ci/deploy.sh \
            --environment development \
            --artifact "release/orders-api-$RELEASE_VERSION.jar"

  deploy-staging:
    needs: deploy-development
    runs-on: ubuntu-latest
    environment: staging

    steps:
      - uses: actions/checkout@v7

      - uses: actions/download-artifact@v8
        with:
          name: orders-api-${{ github.sha }}
          path: release

      - name: Verify downloaded artifact
        working-directory: release
        run: sha256sum --check SHA256SUMS

      - name: Deploy the same JAR
        env:
          RELEASE_VERSION: ${{ needs.build.outputs.version }}
        run: |
          ./ci/deploy.sh \
            --environment staging \
            --artifact "release/orders-api-$RELEASE_VERSION.jar"

  deploy-production:
    needs: deploy-staging
    runs-on: ubuntu-latest
    environment: production

    steps:
      - uses: actions/checkout@v7

      - uses: actions/download-artifact@v8
        with:
          name: orders-api-${{ github.sha }}
          path: release

      - name: Verify downloaded artifact
        working-directory: release
        run: sha256sum --check SHA256SUMS

      - name: Deploy the same JAR
        env:
          RELEASE_VERSION: ${{ needs.build.outputs.version }}
        run: |
          ./ci/deploy.sh \
            --environment production \
            --artifact "release/orders-api-$RELEASE_VERSION.jar"
~~~

### 9.2. Điều workflow này bảo đảm

- Chỉ job `build` chạy Gradle để tạo JAR.
- Các deploy jobs download artifact có tên dựa trên cùng `github.sha` và workflow run.
- Mỗi môi trường tính lại SHA-256 và so với manifest được upload cùng artifact.
- Các jobs chạy tuần tự nhờ `needs`.
- `environment` tách cấu hình/quyền triển khai theo môi trường.
- Deploy script nhận file JAR đã tải về; nó không được gọi lại Gradle/Maven để build artifact.

`./ci/deploy.sh` là **script tích hợp riêng của dự án**, cần triển khai để copy/deploy đúng file đã truyền và đọc runtime configuration từ environment. Workflow mẫu chưa thể deploy vào hệ thống thật nếu script và thông tin kết nối chưa được cấu hình.

### 9.3. Thiết lập approval cho Production

Trong GitHub repository settings, tạo các Environments:

- `development`
- `staging`
- `production`

Cấu hình Required reviewers cho Production và các protection rules phù hợp. GitHub hỗ trợ required reviewers, wait timer và protection rules cho environment deployment jobs. [GitHub deployment environments](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments).

Khi job `deploy-production` cần chạy, protection rule có thể yêu cầu người có quyền phê duyệt trước khi job tiếp tục. Approval chỉ mở đường cho deploy; checksum/provenance vẫn phải được xác minh.

### 9.4. Artifact retention và repository lâu dài

GitHub workflow artifact hữu ích để chuyển file giữa các jobs trong cùng workflow run. Upload-artifact v4 trở lên tạo artifacts bất biến; ví dụ dùng v7. Download-artifact v8 hiện xử lý digest mismatch theo hướng fail mặc định. [actions/upload-artifact releases](https://github.com/actions/upload-artifact/releases) và [actions/download-artifact releases](https://github.com/actions/download-artifact/releases).

Trong ví dụ, retention là 30 ngày. Workflow artifacts không nhất thiết là kho release dài hạn. Với releases cần rollback sau nhiều tháng/năm, publish JAR vào Maven-compatible repository hoặc image vào OCI registry có retention/immutability policy phù hợp. Promotion nên tải theo GAV hoặc digest từ kho bền vững.

### 9.5. Build provenance với GitHub artifact attestations

GitHub Actions có thể tạo artifact attestation để ghi nhận **artifact được build ở đâu và như thế nào**. Với binary, workflow có thể cấp quyền `id-token: write`, `attestations: write` và dùng `actions/attest` sau khi build. Consumer/CI có thể xác minh attestation bằng GitHub CLI theo repository/identity policy. [GitHub artifact attestations](https://docs.github.com/en/actions/how-tos/secure-your-work/use-artifact-attestations/use-artifact-attestations).

Attestation là bằng chứng provenance, không thay thế checksum, signature hoặc vulnerability scan. Chỉ bật quyền tối thiểu và xác minh source repository/workflow identity mà release policy mong đợi.

## 10. Runtime configuration và trạng thái môi trường

Cùng một binary vẫn có thể hành xử khác nhau vì cấu hình runtime và dữ liệu bên ngoài. Điều đó là bình thường nếu được quản lý rõ.

### Spring Boot configuration theo môi trường

Ví dụ cấu hình chung:

~~~properties
spring.application.name=orders-api
server.port=8080
~~~

Các giá trị riêng có thể được truyền khi chạy:

~~~bash
SPRING_PROFILES_ACTIVE=production \
ORDERS_DATABASE_URL='jdbc:postgresql://db-prod.example.test/orders' \
java -jar orders-api-1.8.0.jar
~~~

URL trên chỉ là ví dụ; username/password nên được lấy từ secret store. Trong Kubernetes, cấu hình có thể đến từ ConfigMap/Secret và được mount hoặc truyền thành environment variables.

Không đóng password hoặc database URL Production vào JAR ở build stage. Cấu hình runtime cần có audit, quyền truy cập và khả năng xoay vòng secrets độc lập với release binary.

### Database migration cần tương thích qua quá trình promotion

Build-once không giải quyết tự động việc schema database khác nhau giữa các môi trường. Migration cần có chiến lược tương thích:

1. Thêm cột/bảng mới theo cách không phá vỡ app version đang chạy.
2. Deploy app version mới và kiểm tra.
3. Chuyển traffic/feature flag theo kế hoạch.
4. Chỉ xóa/đổi cấu trúc cũ sau khi mọi consumer đã chuyển đổi và rollback không còn cần schema cũ.

Với rolling deployment, cần nghĩ tới khả năng hai application versions cùng chạy trong thời gian chuyển tiếp. Một migration không backward-compatible có thể khiến rollback binary cũ thất bại dù artifact được giữ nguyên.

### Feature flags

Có thể bật tính năng theo môi trường hoặc nhóm người dùng mà không tạo JAR mới. Feature flag phải được quản lý và version/audit riêng. Không dùng feature flags để che giấu một artifact khác đang chạy trong Production.

## 11. Promotion, rollback và kiểm tra sau deploy

### Promotion có điều kiện

Một môi trường chỉ nên promote khi:

- Artifact đã được xác minh đúng checksum/digest.
- Signature/attestation đạt trust policy nếu release yêu cầu.
- Tests/scan trước release đã pass.
- Deployment ở môi trường hiện tại healthy.
- Smoke test, API/contract checks và các tiêu chí vận hành đạt.
- Người có thẩm quyền đã phê duyệt nếu môi trường cần approval.

Nếu Staging fail, pipeline dừng tại đó. Không tạo artifact mới chỉ để “sửa cho Production”; sửa source, tạo release candidate/version mới và bắt đầu lại từ build stage.

### Rollback

Lưu danh sách release đã triển khai:

~~~text
Production current:
  orders-api@sha256:aaa...

Previous known-good:
  orders-api@sha256:bbb...

Git commit:
  a83f1c2...

Deployment record:
  environment=production
  release=1.8.0
  deployedAt=<UTC time>
~~~

Đây là mẫu minh họa. Khi rollback, trỏ deployment về digest/GAV đã được lưu và kiểm chứng, rồi dùng runtime config phù hợp. Không build lại source cũ để cố tái tạo binary trước đây nếu artifact cũ vẫn còn trong repository.

Rollback cũng cần kiểm tra database migrations, queue/event compatibility và external API changes. Binary cũ có thể không tương thích với trạng thái dữ liệu mới nếu migration không được thiết kế backward-compatible.

### Kiểm tra sau triển khai

Sau mỗi environment:

- Health/readiness endpoints.
- HTTP smoke tests và contract checks.
- Error rate, latency, saturation và log exceptions.
- Kết nối DB/queue/external services.
- Phiên bản/digest instance báo cáo có khớp release record không.
- Tỷ lệ rollout và số replicas thực sự chạy.
- Kết quả sau thời gian quan sát trước khi promote tiếp.

**Build success chỉ chứng minh artifact đã được tạo. Deploy success chỉ chứng minh thao tác triển khai đã hoàn tất.** Cần kiểm tra ứng dụng thật đang chạy đúng version/digest và đáp ứng tiêu chí vận hành.

## 12. Những lỗi phổ biến phá vỡ nguyên tắc build-once

| Hiện tượng | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| JAR ở Production khác Staging | Mỗi môi trường chạy Gradle/Maven build riêng | Build một lần, lưu artifact và download cùng release |
| Cùng version nhưng checksum khác | Ghi đè release coordinates hoặc rebuild khác inputs | Bật immutable releases, tạo version mới khi có thay đổi |
| Dependency tự đổi khi build lại | Dynamic versions/changing snapshots | Pin/lock dependency versions và verification metadata |
| Image tag giống nhưng image khác | Tag bị retag hoặc push lại | Lưu và deploy bằng OCI digest |
| Staging pass nhưng Production fail do config | Secret/URL/profile khác hoặc thiếu | Version hóa external config, kiểm tra config trước promotion |
| Build profile làm JAR khác | Resource filtering hoặc dependencies đổi theo env | Chuyển cấu hình sang runtime |
| Deploy job chạy lại tests/build/package | Pipeline trộn verify với build stage | Deploy job chỉ tải, verify và triển khai artifact |
| Checksum pass nhưng file độc hại | Checksum và artifact cùng nguồn bị compromise | Xác minh signature/provenance và nguồn manifest |
| Artifact không còn để rollback | Repository retention quá ngắn hoặc xóa release | Dùng kho release lâu dài và retention policy |
| Promotion đổi image digest | Build/push image mới ở mỗi stage | Promote tag/metadata nhưng giữ cùng digest |
| Rollback binary cũ làm app lỗi DB | Migration phá vỡ backward compatibility | Expand/contract migration và rollback plan |
| Production deploy không có approval | Environment protection rules chưa cấu hình | Thiết lập reviewers/approval và branch protection |
| CI artifact download lỗi checksum | Artifact bị hỏng hoặc transfer mismatch | Fail job, điều tra run/artifact; không bỏ qua digest mismatch |

### Dấu hiệu pipeline đang rebuild ngầm

- Deploy stage chạy `./gradlew bootJar`, `./gradlew build` hoặc `mvn package`.
- Image build được chạy lại trong mỗi environment job.
- Version thay đổi thành `1.8.0-staging` và `1.8.0-prod` dù source không đổi.
- JAR checksum không được lưu hoặc không được so sánh khi download.
- Script deploy sửa trực tiếp nội dung JAR, thay manifest hoặc repack image.
- Runtime chỉ ghi tag, không lưu image digest/GAV và source commit.

Nếu một bước deploy thực sự cần transform artifact (ví dụ ký, thêm metadata, nén hoặc generate config file), hãy xem nó là một **artifact transformation/build step** có input/output và checksum riêng. Không lặng lẽ sửa binary đã được phê duyệt rồi gọi output đó là cùng artifact.

## 13. Release record tối thiểu

Mỗi lần publish/promote nên lưu một record có thể truy xuất:

~~~text
Application:             orders-api
Release version:         1.8.0
Source repository:       <repository>
Source commit:           <full commit SHA>
Build workflow/run:      <run ID and URL>
Build toolchain:         <JDK, Gradle/Maven, plugin versions>
Dependency lock state:   <lockfile/verification metadata revision>
Artifact coordinate:     com.example:orders-api:1.8.0
Artifact SHA-256:        <actual digest>
OCI image digest:        <actual digest, if containerized>
Signature/attestation:   <verified identity/reference>
SBOM:                    <reference>
Tests/scans:             <report references and results>
Promotion history:       dev -> staging -> production
Approvals:               <reviewer and timestamp>
Deployment result:       <health checks and runtime digest>
~~~

Release record là cầu nối giữa source, artifact và deployment. Khi incident xảy ra, nhóm vận hành có thể biết binary nào chạy ở mỗi environment, nó được build từ commit nào và ai đã phê duyệt promotion.

## 14. Checklist trước khi promote lên môi trường tiếp theo

### Trước khi publish

- [ ] Build từ một commit/tag cụ thể.
- [ ] Gradle/Maven/JDK/plugin/dependency inputs được cố định.
- [ ] Unit/integration/package tests đạt.
- [ ] Security/license/dependency scans đạt theo policy.
- [ ] Artifact được đóng gói một lần và có tên/version rõ.
- [ ] Tính SHA-256 hoặc lấy OCI digest.
- [ ] Signature/provenance được tạo và xác minh nếu policy yêu cầu.
- [ ] Publish vào repository/registry có immutable release policy.
- [ ] Lưu release manifest, SBOM và build reports.

### Trước mỗi lần promotion

- [ ] Tải đúng GAV hoặc image digest đã duyệt.
- [ ] Xác minh checksum/signature/attestation.
- [ ] Xác nhận release version và source commit đúng.
- [ ] Cấu hình environment/secrets từ nguồn runtime đã kiểm soát.
- [ ] Approval đã hoàn tất nếu môi trường yêu cầu.
- [ ] Deploy script nhận đúng artifact và không build lại.
- [ ] Ghi deployment record và artifact digest.
- [ ] Smoke/health/contract checks đạt.
- [ ] Chỉ promote tiếp khi environment hiện tại đạt tiêu chí.

### Khi rollback

- [ ] Chọn previous known-good artifact/digest.
- [ ] Xác minh lại integrity/signature.
- [ ] Kiểm tra schema/data compatibility.
- [ ] Dùng runtime configuration phù hợp.
- [ ] Ghi lại rollback actor, thời điểm và digest.

## 15. Câu hỏi tự kiểm tra

**Câu 1.** “Build once, promote many” có nghĩa gì?

**Trả lời:** Tạo và kiểm thử một artifact, publish nó một lần, rồi dùng đúng bytes/digest đó qua nhiều môi trường.

**Câu 2.** Vì sao cùng source commit nhưng build riêng ở Staging và Production vẫn có thể tạo artifact khác?

**Trả lời:** Dependency resolution, JDK/plugin versions, timestamps, environment-dependent resource filtering hoặc toolchain khác có thể làm bytes thay đổi.

**Câu 3.** Build-once có đồng nghĩa reproducible build không?

**Trả lời:** Không. Build-once tránh rebuild khi promotion; reproducible build là khả năng tái tạo bit-for-bit artifact từ cùng source và build inputs.

**Câu 4.** Có thể đổi Spring profile giữa Staging và Production mà vẫn dùng cùng JAR không?

**Trả lời:** Có. Spring profile là runtime configuration, miễn cấu hình không được bake thành binary riêng cho từng environment.

**Câu 5.** Maven phase `deploy` có phải deploy app lên server Production không?

**Trả lời:** Không. Maven `deploy` publish artifact lên remote repository. Deploy ứng dụng là bước của CD/orchestrator riêng.

**Câu 6.** Vì sao không nên overwrite `com.example:orders-api:1.8.0`?

**Trả lời:** Cùng tọa độ phải tham chiếu cùng release artifact. Overwrite làm checksum, cache, audit và rollback không còn đáng tin.

**Câu 7.** Image tag `1.8.0` có đủ để chứng minh Production chạy đúng image không?

**Trả lời:** Không nếu tag có thể bị retag. Ghi và triển khai theo image digest.

**Câu 8.** Checksum pass có chứng minh publisher đúng không?

**Trả lời:** Không. Expected checksum phải đến từ nguồn tin cậy; signature/attestation và identity trust bổ sung bằng chứng nguồn gốc.

**Câu 9.** Sau khi Staging pass, có nên chạy lại Gradle để tạo JAR Production không?

**Trả lời:** Không. Production phải tải/promote artifact đã được kiểm thử ở Staging; nếu cần sửa source thì tạo release mới và bắt đầu lại.

**Câu 10.** Điều gì có thể làm rollback binary cũ thất bại dù JAR vẫn nguyên vẹn?

**Trả lời:** Database schema hoặc dữ liệu đã thay đổi không backward-compatible, runtime config mới, external API/queue contract hoặc secret đã bị rotate mà app cũ không hỗ trợ.

## 16. Tài liệu chính thức

- Gradle — [Maven Publish Plugin](https://docs.gradle.org/current/userguide/publishing_maven.html): publish một publication lên Maven-compatible repository.
- Gradle — [Dependency Locking](https://docs.gradle.org/current/userguide/dependency_locking.html): cố định các resolved dependency versions.
- Gradle — [Dependency Verification](https://docs.gradle.org/current/userguide/dependency_verification.html): xác minh checksums và PGP signatures của dependencies.
- Maven — [Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html): package, verify, install và deploy phases.
- Maven — [Deploy Plugin Usage](https://maven.apache.org/plugins/maven-deploy-plugin-4.x/usage.html): deploy artifact lên remote repository.
- Maven — [Reproducible Builds](https://maven.apache.org/guides/mini/guide-reproducible-builds.html): tạo artifact có thể tái tạo và so sánh.
- Docker — [Pull an Image by Digest](https://docs.docker.com/reference/cli/docker/image/pull/): pin image vào một digest cụ thể.
- GitHub — [Manage Deployment Environments](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments): required reviewers và environment protection.
- GitHub — [Store and Share Workflow Artifacts](https://docs.github.com/en/actions/tutorials/store-and-share-data): chuyển artifact giữa các workflow jobs.
- GitHub — [Artifact Attestations](https://docs.github.com/en/actions/how-tos/secure-your-work/use-artifact-attestations/use-artifact-attestations): ghi nhận build provenance.

**Ghi nhớ:** Build một lần từ source commit cụ thể; kiểm thử và xác minh artifact; publish vào kho bất biến; promote cùng GAV/checksum hoặc OCI digest; chỉ thay runtime configuration theo môi trường. Mỗi deployment phải lưu artifact identity, approval và kết quả health checks để có thể truy xuất và rollback chính xác.
