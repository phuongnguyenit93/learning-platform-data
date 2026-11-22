# Phân biệt Maven repository, nơi lưu artifact CI và OCI registry khi xuất bản Spring Boot

## 1. Vì sao ba nơi lưu trữ thường bị nhầm lẫn?

Sau khi build Spring Boot, một pipeline có thể tạo `target/release-demo-0.1.0.jar`, báo `BUILD SUCCESS` và cần giao sản phẩm cho người tiêu thụ. Nhưng câu “đã upload artifact rồi” **chưa đủ**: artifact đang nằm ở đâu, ai lấy bằng công cụ gì, trong bao lâu, với metadata/định danh nào và có phải chính binary đã được test hay không?

Ba loại đích phổ biến:

1. **Maven repository**: phân phối Java/Maven components theo **coordinates** `groupId:artifactId:version`, kèm POM, metadata và các file JAR/WAR/classifier tương ứng. Maven/Gradle tiêu thụ bằng dependency resolution.
2. **Nơi lưu artifact của CI** (*workflow/job artifacts*): lưu **kết quả của một lần chạy pipeline**, ví dụ executable JAR, test reports, coverage, logs, checksum, SBOM, nhằm truyền giữa jobs hoặc tra cứu/debug sau build. Định danh thường gắn với workflow run/build number và retention policy, **không mặc định có giao thức Maven repository**.
3. **OCI registry**: phân phối container image và các loại OCI artifacts theo **repository:tag** hoặc **repository@digest**. Docker/Podman/containerd/Kubernetes kéo image manifests và layers, không lấy executable JAR bằng Maven GAV thông thường.

```text
Git commit cố định
       |
       v
  Maven / Gradle build + tests
       |
       +--> target/release-demo-0.1.0.jar
       |            |
       |            +--> [CI artifact store]
       |            |      build #308 / artifact "app-jar"
       |            |      -> job khác tải, QA, điều tra
       |            |
       |            +--> [Maven repository]
       |                   com.example:release-demo:0.1.0
       |                   -> Maven/Gradle consumer tải bằng GAV
       |
       +--> Dockerfile / Spring Boot build-image
                    |
                    v
              OCI image + manifest + layers
                    |
                    v
             [OCI registry]
             registry.example.invalid/team/release-demo:0.1.0
             -> node/container runtime pull theo tag/digest
```

**Ba nơi không loại trừ nhau.** Một pipeline tốt có thể lưu test evidence trong CI, publish Java library lên Maven repository, đồng thời phát hành Spring Boot executable container image lên OCI registry. Nhưng không nên **đẩy mọi thứ đi khắp nơi** chỉ vì cùng gọi là “artifact”: phải xác định người tiêu thụ, retention, security và release policy.

Bài học minh họa bằng **Java 17 và Spring Boot 3.5.0**, Maven 3.9.x và các công cụ CI/Docker phổ biến. Các phiên bản cố định để ví dụ nhất quán, không có nghĩa là mới nhất. Các domain `example.invalid` trong phần cấu hình là **địa chỉ minh họa không hoạt động**; phải thay bằng repository/registry thực sự được tổ chức cấp quyền trước khi publish.

## 2. Bảng so sánh nhanh

| Tiêu chí | Maven repository | CI artifact store | OCI registry |
| --- | --- | --- | --- |
| Đối tượng chính | POM, JAR, WAR, sources, javadoc, classifiers, Maven metadata | File và folder sinh từ workflow: JAR, test reports, logs, SBOM, checksum | Container image, image index/manifest, layers, OCI artifact types |
| Định danh tiêu biểu | `com.example:shared-api:1.2.0` | Workflow run `#308` + artifact name `app-jar` | `registry/team/app:1.2.0` hoặc `@sha256:...` |
| Upload điển hình | `mvn deploy` hoặc Gradle `maven-publish` | CI upload-artifact hoặc job artifact feature | `docker push`, `buildx --push`, `bootBuildImage --publish` |
| Download điển hình | Maven dependency resolution, `mvn dependency:get` | CI download-artifact / web API của CI provider | `docker pull`, `podman pull`, Kubernetes pull |
| Metadata quan trọng | POM, GAV, dependency graph, maven-metadata.xml, checksums | Run ID, job, branch/commit, uploader, retention, artifact checksum | OCI manifest/index, config, layer digests, platform, tag, media types |
| Thời gian lưu | Release/snapshot policy theo repository manager | Thường có hạn lưu theo run/plan, có thể tự hết hạn | Registry retention, garbage collection, tag immutability policy |
| Dependency resolution | **Có, theo Maven** | Thường **không** | **Không theo Maven GAV** đối với image thông thường |
| Deployment chạy JVM | Consumer lấy JAR rồi chạy nếu artifact executable | Job tải JAR rồi dùng như file | Runtime kéo image, tạo container |
| Truy vết | Version tọa độ + checksum và repository provenance | Run/job/commit + hash + logs | Image digest/index digest + SBOM/provenance |
| Secrets/permission | Deploy token, read token, repo roles | CI identities/artifact read permissions | Registry credentials, pull/push permissions |

**Chú ý:** một dịch vụ như Nexus, Artifactory hoặc GitHub Packages có thể cung cấp **nhiều loại repository dưới cùng một giao diện/hostname**. Điều đó **không làm chúng thành một định dạng**. Maven endpoint, generic artifact storage, workflow artifacts và OCI Registry endpoint vẫn có API, metadata và quyền truy cập riêng. OCI registry còn có thể lưu artifact không phải image (ví dụ Helm chart/SBOM qua OCI artifact media types), nhưng **không mặc nhiên là Maven repository cho Java dependency**.

## 3. Maven repository là gì?

Maven repository là một kho có **layout và metadata mà Maven clients hiểu**. Định danh quan trọng là:

```text
groupId    : artifactId   : version        [:packaging] [:classifier]
com.example: shared-api   : 1.2.0          : jar
com.example: release-demo : 0.1.0          : jar
com.example: release-demo : 0.1.0          : jar        : exec
```

Maven dùng coordinates để quyết định dependency nào cần tải, ở version nào, với transitive dependencies nào được mô tả trong POM. Tên file có thể giống file ở CI, nhưng **GAV và POM mới là hợp đồng phân phối Java**.

### 3.1. Layout maven2: ví dụ path thực tế

Đối với `com.example:shared-api:1.2.0`, đường dẫn relative trong repository layout thường là:

```text
com/example/shared-api/1.2.0/
├── shared-api-1.2.0.pom
├── shared-api-1.2.0.jar
└── [checksums / signatures tùy hệ thống]

com/example/shared-api/maven-metadata.xml
```

`groupId` có các dấu chấm được chuyển thành thư mục; filename chứa artifactId và version. Repository manager có thể thêm metadata/index/checksum khác. **Không tự chép một JAR lên object storage path có vẻ giống Maven rồi mặc định nó thành một Maven repository hợp lệ**: còn phải xử lý POM, metadata, policy release/snapshot, checksum và cách Maven resolver truy cập.

### 3.2. Ba loại kho Maven cần phân biệt

- **Local repository:** thường nằm ở `~/.m2/repository`, là nơi Maven cache các dependencies/plugins đã tải và các artifacts cài bằng `mvn install`. Đây **không** phải nơi đồng nghiệp/CI runner khác tự nhìn thấy.
- **Remote repository:** repository HTTP(S) hoặc hệ thống được Maven resolver truy cập để tải dependencies/plugins, ví dụ Maven Central hoặc internal Nexus/Artifactory.
- **Hosted deploy repository:** endpoint có quyền **ghi** để publish artifacts của tổ chức, thường tách **releases** và **snapshots**. Có thể nằm trên cùng một repository manager với remote mirrors.

`mvn install` đưa artifact vào local Maven repository. `mvn deploy` thực thi lifecycle tới phase deploy và chuyển artifacts/metadata lên remote deployment repository được cấu hình. **`mvn package` chỉ tạo file ở `target`; `mvn deploy` không đồng nghĩa Docker push.**

### 3.3. Releases và SNAPSHOTs

| Maven version | Ý nghĩa | Quy tắc publish thông thường |
| --- | --- | --- |
| `1.2.0` | Release version | Nên bất biến, không ghi đè bản đã phát hành |
| `1.2.1-SNAPSHOT` | Development snapshot | Có thể được publish nhiều lần với timestamp/build number và metadata tương ứng |
| `1.2.0-RC1` | Bản ứng viên phát hành, xét Maven version như một version không có đuôi SNAPSHOT | Tùy chính sách hosted release repository |

Một Maven snapshot `1.2.1-SNAPSHOT` có thể được lưu server-side dưới tên timestamped snapshot và metadata `maven-metadata.xml`. Nó không phải Git branch và cũng không phải một OCI image tag. Khi consumer tải SNAPSHOT, chính sách `updatePolicy` và local Maven cache ảnh hưởng thời điểm Maven kiểm tra phiên bản mới.

**Không dùng cùng release version để ghi nhiều JAR khác nhau:** điều đó làm mất khả năng tái tạo dependency graph, dù repository nào đó cho overwrite. Khi cần cập nhật security fix, phát hành version mới và ghi lại checksums.

## 4. Phân biệt repositories dùng để tải với distributionManagement dùng để publish

Trong Maven POM, cấu hình:

```xml
<repositories>
    <repository>
        <id>company-proxy</id>
        <url>https://repo.example.invalid/repository/maven-public/</url>
    </repository>
</repositories>
```

thường phục vụ **dependency resolution**. Nó **không tự chỉ Maven Deploy Plugin publish tới endpoint đó**.

Để publish artifacts của chính project:

```xml
<distributionManagement>
    <repository>
        <id>internal-releases</id>
        <url>https://repo.example.invalid/repository/maven-releases/</url>
    </repository>
    <snapshotRepository>
        <id>internal-snapshots</id>
        <url>https://repo.example.invalid/repository/maven-snapshots/</url>
    </snapshotRepository>
</distributionManagement>
```

`<repository>` ở trên là **đích release**; `<snapshotRepository>` là **đích snapshot**. Đây là đoạn POM, không phải XML hoàn chỉnh. `repo.example.invalid` là placeholder không có dịch vụ; phải thay bằng đúng URL từ repository manager được phê duyệt.

**Điểm rất quan trọng:** `<repositories>` (download), `<pluginRepositories>` (plugin download), `<mirrors>` trong settings (điều hướng download) và `<distributionManagement>` (upload deploy) có vai trò khác nhau. Một `mirrorOf="*"` không nên được suy diễn là tự thay đổi URL deploy. Hãy kiểm tra effective settings/POM khi debug.

### 4.1. Credentials không đặt vào POM

Maven so khớp `distributionManagement.repository.id` với `settings.xml -> servers -> server.id`. Ví dụ **`settings.xml` dùng trên CI** (tệp đầy đủ cho phần này):

```xml
<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0">
    <servers>
        <server>
            <id>internal-releases</id>
            <username>${env.MAVEN_REPO_USER}</username>
            <password>${env.MAVEN_REPO_TOKEN}</password>
        </server>
        <server>
            <id>internal-snapshots</id>
            <username>${env.MAVEN_REPO_USER}</username>
            <password>${env.MAVEN_REPO_TOKEN}</password>
        </server>
    </servers>
</settings>
```

Maven hỗ trợ interpolation của biến môi trường trong settings với cú pháp `${env.NAME}` theo cơ chế settings interpolation. Các biến `MAVEN_REPO_USER` và `MAVEN_REPO_TOKEN` phải được cấp từ **CI secret store** khi job thực sự cần publish. Không đưa credential thật vào Git, `pom.xml`, command-line arguments hoặc logs.

**Cảnh báo:** `settings.xml` mẫu đủ để minh họa server credentials, nhưng tổ chức có thể cần proxy, mirror, TLS truststore, certificates hoặc username khác theo repo. Một số CI provider dùng token/OIDC hoặc maven settings generator thay vì file thủ công. Tên `id` **phải khớp chính xác**, còn token phải có quyền deploy vào đúng hosted repository.

### 4.2. Lệnh build, install, deploy được phân biệt

```bash
# Chỉ build và kiểm thử:
mvn -B -ntp clean verify

# Build và cài artifact vào local ~/.m2/repository:
mvn -B -ntp clean install

# Build + test + publish artifacts tới distributionManagement:
mvn -B -ntp -s ci/settings.xml clean deploy
```

Lệnh `deploy` cuối chỉ chạy được khi `ci/settings.xml` thực sự tồn tại, URL deploy đã thay bằng endpoint được cấp và environment secrets đã cấu hình. **Không chạy lệnh publish với URL ví dụ**, vì nó không phải repository hoạt động.

Nếu project chỉ có một JAR đã được build ở pipeline khác và cần publish như một Maven artifact, Maven Deploy Plugin có goal `deploy-file`, nhưng cần **đủ coordinates, POM/pomFile, classifier và policy**. Không đơn giản đổi tên file trong CI thành `my-app.jar` rồi upload qua HTTP tới Maven repo.

## 5. CI artifact store: không phải Maven dependency registry

CI artifacts lưu **những file do job tạo ra** để người khác hoặc job khác dùng. Ví dụ:
- `target/release-demo-0.1.0.jar` để triển khai/smoke test;
- `target/surefire-reports/*.xml` để theo dõi test failures;
- `target/site/jacoco/index.html` hoặc coverage report;
- `dist/app.jar.sha256` để đối chiếu bytes;
- SBOM, provenance/attestations, generated docs và support bundle.

Một CI provider thường định danh artifact bằng **run ID + artifact name** và giới hạn retention theo repository/organization/plan. GitHub Actions có `actions/upload-artifact` / `actions/download-artifact`. Các CI khác (GitLab CI, Jenkins, Azure Pipelines...) có chức năng tương ứng, nhưng API và quyền khác nhau.

### 5.1. Đặc trưng của workflow artifacts

1. **Gắn với một run/job:** dễ trả lời “build #308 tạo file gì?”.
2. **Gửi giữa jobs:** job build tạo JAR; job kiểm thử container có thể tải lại **đúng JAR đó**.
3. **Có retention:** ví dụ `retention-days: 7` trên GitHub Actions, không vượt policy tối đa của organization/repository.
4. **Không phải giải pháp giữ release mãi mãi theo mặc định:** artifact có thể hết hạn hoặc bị xóa cùng workflow history.
5. **Không tự cung cấp POM/transitive dependency metadata:** Maven không hiểu `run-id/app-jar.zip` là `com.example:release-demo:0.1.0`.
6. **Không phải dependency cache:** CI caching lưu dependencies/tool cache để tăng tốc, còn artifacts lưu **đầu ra đáng bàn giao hoặc kiểm chứng**.
7. **Artifact name không phải nội dung:** `app-jar` có thể chứa một hoặc nhiều file; phải kiểm tra checksum, không chỉ kiểm tra tên.
8. **Artifact upload có thể đóng gói file khi lưu:** nếu cần so sánh byte-for-byte, lấy hash của **JAR gốc** và xác minh sau download/extract thay vì so checksum của ZIP bao ngoài.

### 5.2. GitHub Actions workflow artifact: ví dụ gọn

Ví dụ một workflow **không publish** lên Maven/OCI. Nó build JAR, đóng vào thư mục `dist`, tạo checksum, upload CI artifact ở job đầu và download/verify ở job thứ hai.

**`.github/workflows/build-and-check.yml`:**

```yaml
name: Build and check artifact

on:
  workflow_dispatch:
  push:
    branches: [main]

permissions:
  contents: read

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'
          cache: maven

      - name: Package
        run: mvn -B -ntp clean verify

      - name: Stage JAR and checksum
        shell: bash
        run: |
          mkdir -p dist
          cp target/release-demo-0.1.0.jar dist/app.jar
          (cd dist && sha256sum app.jar > app.jar.sha256)

      - name: Upload CI artifact
        uses: actions/upload-artifact@v4
        with:
          name: release-demo-jar
          path: dist/
          if-no-files-found: error
          retention-days: 7

  verify-download:
    needs: build
    runs-on: ubuntu-latest
    steps:
      - name: Download CI artifact
        uses: actions/download-artifact@v4
        with:
          name: release-demo-jar
          path: dist

      - name: Verify checksum
        shell: bash
        run: |
          cd dist
          sha256sum -c app.jar.sha256
          jar tf app.jar | grep 'BOOT-INF/classes/'
```

**Điều kiện:** workflow này giả định có `pom.xml`/Java application tạo file `target/release-demo-0.1.0.jar` như phần thực hành bên dưới. `actions/upload-artifact@v4` và `actions/download-artifact@v4` chỉ là tên action minh họa; với CI production, pin actions theo commit SHA đã duyệt, cập nhật versions theo policy. `ubuntu-latest` và hosted runner image có thể thay đổi tool versions, nên gate tái lập nghiêm ngặt cần runner/container toolchain pin chính xác hơn.

`sha256sum -c app.jar.sha256` in dòng tương đương `app.jar: OK` nếu bytes file khớp. Đây là **bằng chứng file được truyền giữa jobs không bị thay đổi** theo checksum ở đầu vào; không chứng minh artifact an toàn, không bảo đảm repository/cache không bị compromise. Check `jar tf` xác nhận JAR có Spring Boot layout; nếu mọi artifact test reports cũng cần lưu, thêm **artifact khác** hoặc upload path phù hợp.

**Nếu workflow download artifact từ workflow run khác**, phải chọn run-id/token/permissions đúng; không mặc định `download-artifact` của current run tự tìm được artifact của mọi workflow trước đó.

### 5.3. GitHub artifact khác GitHub Packages

**GitHub Actions workflow artifact** là output thuộc một workflow run. **GitHub Packages** có thể cung cấp Maven package registry và container registry (GHCR). Cùng thương hiệu GitHub, nhưng **API, retention, permissions và publish commands khác**.

Ví dụ:
- `actions/upload-artifact`: đưa `dist/app.jar` thành CI workflow artifact.
- `mvn deploy` tới endpoint Maven của package registry: publish `GAV + POM/JAR`.
- `docker push ghcr.io/org/app:1.2.0`: publish OCI image manifest và layers.

Một file JAR upload bằng `actions/upload-artifact` **không tự xuất hiện** để dependency consumers resolve bằng Maven GAV. Và OCI image push **không tự tạo** một Maven release.

## 6. OCI registry: nơi chứa manifests, configs và layers

OCI image có một cấu trúc nội dung khác Maven artifact:

```text
registry.example.invalid/team/release-demo:0.1.0
                  |
                  v
tag -> OCI image manifest / image index
                  |
                  +--> image config digest
                  +--> filesystem layer digest #1
                  +--> filesystem layer digest #2
                  +--> ...
```

**Image reference**:
- `registry.example.invalid/team/release-demo:0.1.0`: repository + tag.
- `registry.example.invalid/team/release-demo@sha256:<digest-thực-tế>`: repository + manifest/index digest.

`<digest-thực-tế>` là ký pháp mô tả, **không phải SHA-256 hợp lệ** để copy chạy. Digest phải được lấy từ registry sau build/push. Tag có thể được gán lại nếu registry cho phép; digest định danh nội dung manifest/index cụ thể.

### 6.1. Một image có thể có nhiều kiến trúc CPU

Một image tag có thể trỏ tới OCI index (Docker manifest list):

```text
tag: 0.1.0
   |
   v
OCI index sha256:INDEX...
   |
   +--> linux/amd64 manifest -> config/layers AMD64
   +--> linux/arm64 manifest -> config/layers ARM64
```

`INDEX...` chỉ là sơ đồ. Khi Kubernetes/node pull image từ **index**, container runtime chọn variant phù hợp kiến trúc CPU/OS. JAR Java bytecode có thể portable giữa các kiến trúc, nhưng **JRE và native OS libraries trong image** không portable theo cách đó. Nếu cần hỗ trợ nhiều kiến trúc, phải build/publish đúng platform manifests và test runtime.

### 6.2. Docker push/pull không dùng Maven GAV

```bash
# Sau khi đã build image local có tên và tag:
docker push registry.example.invalid/team/release-demo:0.1.0

# Ở máy triển khai, khi đã có quyền:
docker pull registry.example.invalid/team/release-demo:0.1.0
```

Các lệnh này **chỉ là mẫu sau khi thay hostname thật, đã docker login và build/tag image**. Docker Registry API không đọc Maven `pom.xml` để resolve `groupId:artifactId:version` hay transitive dependencies. Nó trao đổi manifests/layers bằng OCI/Docker distribution semantics.

Một OCI registry có thể lưu **non-image OCI artifacts** (ví dụ SBOM/Helm charts với công cụ hỗ trợ như ORAS), nhưng điều đó **không làm Maven Deploy Plugin tự hiểu endpoint đó**. Nếu muốn phân phối Java library bằng Maven, dùng Maven repository endpoint phù hợp.

### 6.3. Image digest khác SHA của JAR

| Hash | Đối tượng được hash |
| --- | --- |
| `sha256sum target/release-demo-0.1.0.jar` | Bytes của file JAR |
| `docker image inspect .Id` | Thường là image config digest của local image |
| `docker buildx imagetools inspect...` dòng `Digest:` | Manifest hoặc multi-platform index digest trên registry |
| Layer digest trong manifest | Compressed filesystem layer |
| Digest file CI artifact tải về | Có thể là JAR bytes, ZIP container artifact hoặc metadata riêng tùy cách tính |

Không lấy một JAR checksum rồi dùng làm `docker pull repository@sha256:...`; đó là hai địa chỉ cho **hai loại đối tượng khác nhau**.

## 7. Ví dụ thực hành đầy đủ: một Spring Boot JAR, ba kênh bàn giao

Ta sẽ tạo ứng dụng web đơn giản, build JAR bằng Maven và thấy:
1. File JAR trên disk sau `mvn package`.
2. File JAR được upload/download qua CI artifact và kiểm tra bytes.
3. Một Docker image chứa JAR được push tới OCI registry.
4. Cách publish Maven tọa độ của JAR khi có repository được cấp quyền.

**Môi trường:** Java 17+, Maven 3.9.x tương thích Spring Boot 3.5.0, Docker Engine/Buildx khi chạy phần OCI, Linux/macOS Bash hoặc Windows tương đương. Một số bước publish cần private endpoint/credentials do tổ chức cung cấp và **không thể chạy với placeholder**.

### 7.1. Cấu trúc project

```text
release-demo/
├── pom.xml
├── Dockerfile
├── .dockerignore
├── src/main/java/com/example/release/ReleaseDemoApplication.java
├── dist/                                      # tạo sau build, không commit
└── target/                                    # Maven tạo
```

### 7.2. File pom.xml Maven/Spring Boot hoàn chỉnh

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>release-demo</artifactId>
    <version>0.1.0</version>
    <name>release-demo</name>
    <packaging>jar</packaging>

    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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

    <!-- Chỉ bật sau khi tổ chức cấp repository URL và deploy credentials.
    <distributionManagement>
        <repository>
            <id>internal-releases</id>
            <url>https://repo.example.invalid/repository/maven-releases/</url>
        </repository>
        <snapshotRepository>
            <id>internal-snapshots</id>
            <url>https://repo.example.invalid/repository/maven-snapshots/</url>
        </snapshotRepository>
    </distributionManagement>
    -->
</project>
```

**Vì sao comment distributionManagement?** Demo **build và chạy local ngay** mà không cần tài khoản publish; các URL trong `distributionManagement` là example.invalid, không có thật. Khi cần `mvn deploy`, bỏ comment và thay endpoints + server IDs/CI secrets theo hệ thống thật. Với Spring Boot starter parent, `spring-boot-maven-plugin` được khai báo nên `repackage` hoạt động ở phase `package`; không cần thêm execution trùng.

### 7.3. File Java 17 chạy được

**`src/main/java/com/example/release/ReleaseDemoApplication.java`:**

```java
package com.example.release;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class ReleaseDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReleaseDemoApplication.class, args);
    }

    @GetMapping("/ready")
    public String ready() {
        return "ready";
    }

    @GetMapping("/version")
    public String version() {
        return "release-demo:0.1.0";
    }
}
```

Hai endpoints chỉ dùng literals để output không phụ thuộc environment. Trong ứng dụng thật, version nên đến từ release metadata có kiểm soát (project version hoặc Git commit) thay vì hardcode ở source, nhưng ví dụ này giúp người học kiểm tra một cách chính xác.

### 7.4. Build, chạy và xem archive

```bash
mvn -B -ntp clean package
jar tf target/release-demo-0.1.0.jar
java -jar target/release-demo-0.1.0.jar
```

Sau khi web server chạy (mặc định port 8080), terminal khác:

```bash
curl -fsS http://localhost:8080/ready
curl -fsS http://localhost:8080/version
```

**Response body chính xác theo từng request:**

```text
GET /ready   -> ready
GET /version -> release-demo:0.1.0
```

Các dòng trên là **bảng mô tả endpoint và body**, không phải stdout nguyên văn của một lệnh curl. Khi thực thi curl, nó chỉ in body `ready` hoặc `release-demo:0.1.0`, thường không có newline. Dừng JVM bằng Ctrl+C trước khi chạy các bước dùng cùng port.

`jar tf` sẽ có các entries đại diện:

```text
META-INF/MANIFEST.MF
BOOT-INF/classes/com/example/release/ReleaseDemoApplication.class
BOOT-INF/lib/...
org/springframework/boot/loader/...
```

Dấu `...` là sơ đồ, không phải tên literal của file JAR. Đó là **executable Spring Boot archive** do `repackage` tạo; không phải OCI image và chưa được upload tới bất cứ remote repository nào.

## 8. Chuẩn bị một bản JAR duy nhất cho CI và Docker

Sau `mvn package`, tạo thư mục staging:

```bash
mkdir -p dist
cp target/release-demo-0.1.0.jar dist/app.jar
(
  cd dist
  sha256sum app.jar > app.jar.sha256
  sha256sum -c app.jar.sha256
)
```

Trên Linux với `sha256sum`, lệnh kiểm tra in:

```text
app.jar: OK
```

Điểm này rất quan trọng: file `dist/app.jar` là **bản copy của executable JAR đã build**. Trong CI, nên dùng **chính file này** để upload workflow artifact và để build OCI image; không tự build lại source ở một job sau rồi gán cùng version nếu mục tiêu là publish đúng binary đã kiểm thử.

Trên Windows PowerShell, có thể dùng `Get-FileHash -Algorithm SHA256` và công cụ copy tương ứng; file `app.jar.sha256` của ví dụ sử dụng định dạng `sha256sum` cho Linux CI.

**Đặt `dist/` và `target/` ngoài Git.** CI artifact có thể chứa cả `app.jar` và file checksum, nhưng kho Git source không nên lưu JAR của mỗi build không cần thiết.

## 9. Đưa JAR vào OCI image: Dockerfile không dùng Maven repo

**`Dockerfile`:**

```dockerfile
FROM eclipse-temurin:17-jre
WORKDIR /app
COPY dist/app.jar /app/app.jar

USER 10001
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
```

**`.dockerignore`:**

```dockerignore
.git
target/
.gradle/
.idea/
.vscode/
.env
*.pem
*.p12
*.key
```

Không exclude `dist/` vì Dockerfile cần copy `dist/app.jar`. Nếu pipeline dùng một Docker build context khác project root, phải bảo đảm file `dist/app.jar` nằm trong context trước `docker build`.

Chạy local:

```bash
docker build -t release-demo:local .
docker run --rm -p 127.0.0.1:8080:8080 release-demo:local
```

Sau khi container khởi động, `curl -fsS http://localhost:8080/ready` trả `ready`. `EXPOSE 8080` chỉ mô tả intended port, còn `-p 127.0.0.1:8080:8080` công bố cổng trên loopback host. Nếu cùng lúc còn Java process local ở port 8080, Docker run có thể bị lỗi binding; dừng process cũ.

**Thứ đã thay đổi:** đã tạo một **OCI container image** chứa Linux/JRE layers và Java archive. Chỉ sau khi `docker push` hoặc buildx `--push` tới remote registry, image mới thực sự được publish. Một local `docker build` thành công không đồng nghĩa image đã hiện diện trong registry.

### 9.1. Publish OCI image khi có registry thật

Khi có quyền registry và đã xác nhận repository name:

```bash
# IMAGE_REF do CI/release environment cung cấp, ví dụ hostname/repo:version.
: "${IMAGE_REF:?Set an authorized OCI registry image reference}"

docker tag release-demo:local "$IMAGE_REF"
docker push "$IMAGE_REF"

docker buildx imagetools inspect "$IMAGE_REF"
```

Lệnh dùng Bash và **đòi IMAGE_REF là image reference hợp lệ**, ví dụ một registry tổ chức đã cấu hình; không thể chạy với tên chưa cấp. CI phải login bằng secret/token theo chính sách; không ghi password vào Dockerfile hoặc shell history. `imagetools inspect` kiểm tra manifest/digest đã publish ở remote registry.

Nếu registry trả về **index digest** (multi-platform), nó đại diện tập các platform manifests; nếu image chỉ build một platform, reference có thể là một manifest đơn. Đừng giả định digest của `app.jar` chính là image digest.

### 9.2. Không lạm dụng Docker push cho Maven library

Khi một Java library khác cần dùng `GreetingService.class` hoặc API classes qua Maven dependency, đẩy executable OCI image lên registry **không giúp Maven tự resolve classes đó**. Registry cung cấp image filesystem/runtime, còn Maven consumer cần đúng **JAR + POM + GAV** từ Maven repository.

OCI registry có thể có tính năng lưu generic/OCI artifacts, nhưng quy trình tiêu thụ **không tương đương** `<dependency>com.example:shared-lib:1.0.0</dependency>` nếu không có tooling/adapter Maven chuyên biệt.

## 10. Publish Maven artifacts: đúng khi ai là người tiêu thụ?

Nếu Spring Boot app chỉ chạy như **service/container**, OCI image thường là sản phẩm triển khai trực tiếp. Nhưng Maven repository có thể vẫn hữu ích để lưu Java packages, hoặc để phát hành artifact cho một môi trường chạy `java -jar` mà không dùng containers.

Trước khi publish:
- Quyết định đây là **application executable JAR** hay **library JAR** cho consumers.
- Chọn GAV/version/release policy.
- Thiết lập `distributionManagement` với URL releases/snapshots đúng.
- Cấp `settings.xml` credentials cho server ID khớp.
- Chạy test và chỉ deploy khi pass.

Lệnh từ source tree:

```bash
mvn -B -ntp -s ci/settings.xml clean deploy
```

**Ý nghĩa:** build, test, package/repackage, install nội bộ theo lifecycle và deploy artifact/POM đến Maven hosted repository. Với example `distributionManagement` đang comment, lệnh này **không có remote deploy destination**. Đừng bỏ qua điều kiện này.

### 10.1. Vì sao executable Boot JAR không phải library JAR lý tưởng?

Một Boot executable JAR có classes dưới `BOOT-INF/classes` và dependencies lồng trong `BOOT-INF/lib`. Khi module khác dùng nó như Maven dependency thông thường, classpath Java **không** tự coi `BOOT-INF/classes` là root của library JAR. Vì thế, nếu có code muốn tái sử dụng giữa services, hãy phát hành một **plain library JAR** riêng.

Nếu cần cùng một Maven module xuất bản **plain JAR cho dependency** và **executable JAR cho vận hành**, Spring Boot Maven Plugin có thể attach executable JAR với classifier, ví dụ `exec`, trong khi giữ main artifact plain JAR:

```xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <configuration>
        <classifier>exec</classifier>
    </configuration>
</plugin>
```

Đây là **đoạn thay thế cấu hình plugin trong `pom.xml`**, không dán hai khai báo plugin cùng group/artifact. Với setup phù hợp, Maven output có thể gồm:
- `release-demo-0.1.0.jar`: plain JAR main artifact;
- `release-demo-0.1.0-exec.jar`: executable Spring Boot archive, attached classifier `exec`.

**Cảnh báo:** khi dùng classifier `exec`, Dockerfile phải COPY **`release-demo-0.1.0-exec.jar`**, không phải plain `release-demo-0.1.0.jar`. Nếu chỉ phân phối service, giữ cấu hình mặc định đơn giản của ví dụ chính và không cần classifier. Trong kiến trúc multi-module, thường rõ ràng hơn khi tách module library và module Spring Boot app.

### 10.2. Maven repository consumer: ví dụ dependency POM

Một module consumer thêm:

```xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>shared-api</artifactId>
    <version>1.2.0</version>
</dependency>
```

và cấu hình `<repositories>`/`settings.xml` đủ để Maven lấy đúng hosted artifact. Maven tải POM và các transitive dependencies theo dependency graph. **Không** thêm `workflow artifact URL` hoặc `docker.io/repo:tag` vào `<dependency>` vì đó không phải Maven coordinates.

**Tải Maven artifact để xác minh** (giả sử remote repository được khai báo/credentials phù hợp):

```bash
mvn -B -ntp dependency:get \
  -Dartifact=com.example:shared-api:1.2.0
```

Lệnh này dùng Maven Dependency Plugin, cần plugin resolution và remote repository sẵn sàng. Nó đưa artifact vào local Maven cache; không chạy service hay tải OCI image.

## 11. Gradle tương đương: maven-publish và bootBuildImage khác nhau

Nếu project dùng Gradle, vẫn phải giữ ba đích phân biệt:
- `maven-publish` plugin cho **Maven repository**;
- CI provider upload-artifact cho **workflow artifacts**;
- `bootBuildImage` hoặc Docker/Buildx cho **OCI image**.

### 11.1. Gradle Kotlin DSL: Maven publication

Ví dụ **đoạn thêm vào một `build.gradle.kts` của Java library** đã có plugin Java:

```kotlin
plugins {
    `java-library`
    `maven-publish`
}

group = "com.example"
version = "1.2.0"

publishing {
    publications {
        create<MavenPublication>("mavenJava") {
            from(components["java"])
        }
    }
    repositories {
        maven {
            name = "internal"
            url = uri("https://repo.example.invalid/repository/maven-releases/")
            credentials {
                username = providers.environmentVariable("MAVEN_REPO_USER").orNull
                password = providers.environmentVariable("MAVEN_REPO_TOKEN").orNull
            }
        }
    }
}
```

**Điểm cần điều chỉnh để có file Kotlin DSL thật:** hai dòng ``java-library`` và ``maven-publish`` trong `plugins` được bao bằng ký hiệu backtick chỉ để hiển thị; **Kotlin DSL plugin syntax chuẩn** là:

```kotlin
plugins {
    `java-library`
    `maven-publish`
}
```

Phần này là **minh họa publish Java library**, không áp dụng trực tiếp lên executable Boot app mà chưa chọn component/artifact đúng. URL `example.invalid` chưa hoạt động. Với Gradle plugin DSL, có thể viết `id("java-library")` và `id("maven-publish")` (hợp lệ) để tránh nhầm lẫn về cú pháp.

Lệnh publish khi endpoint/credentials đã có:

```bash
./gradlew publish
```

Gradle tạo publication Maven gồm POM/JAR theo component, và thực thi upload đến repository được khai báo. **`publish` không phải Docker push**. Với Spring Boot executable JAR, cần cấu hình publication của `bootJar` artifact có chủ đích nếu muốn publish riêng; plain `components["java"]` có thể không phải binary executable mà bạn dự định bàn giao.

### 11.2. Spring Boot Gradle bootBuildImage

Với plugin Spring Boot và Java, task `bootBuildImage` có thể tạo OCI image dùng Cloud Native Buildpacks. Một đoạn Kotlin DSL minh họa:

```kotlin
import org.springframework.boot.gradle.tasks.bundling.BootBuildImage

tasks.named<BootBuildImage>("bootBuildImage") {
    imageName.set("registry.example.invalid/team/release-demo:0.1.0")
    publish.set(false)
}
```

`publish=false` nghĩa là xây image ở local daemon/builder, chưa gửi đến OCI registry. Nếu muốn publish, cần `publish=true` và cấu hình registry authentication/permissions thích hợp. **Task này không ghi Maven GAV/POM lên Maven repository và không tạo CI workflow artifact upload**.

## 12. Spring Boot Cloud Native Buildpacks cũng xuất bản OCI image

Ngoài Dockerfile, Spring Boot Maven Plugin có goal:

```bash
mvn -B -ntp spring-boot:build-image \
  -Dspring-boot.build-image.imageName=release-demo:local
```

Lệnh trên có thể tạo OCI image bằng Buildpacks khi Docker daemon/builder được hỗ trợ và các buildpack images có thể tải. Tạo image local **khác** publish registry.

Sau khi cấu hình image name là reference tới registry có quyền và CI credentials đúng, có thể bật publish:

```bash
mvn -B -ntp spring-boot:build-image \
  -Dspring-boot.build-image.imageName=registry.example.invalid/team/release-demo:0.1.0 \
  -Dspring-boot.build-image.publish=true
```

**Dòng lệnh publish là minh họa**, chưa runnable với `example.invalid`. Nếu repository dùng registry riêng, có thể cần `docker.publishRegistry` credentials hoặc Docker/credential helper theo phiên bản plugin và môi trường; kiểm tra docs đúng Spring Boot version. Không nhét mật khẩu trực tiếp lên CLI (có thể lộ trong process list/log), không dùng Docker Hub credentials mặc định cho registry công ty.

**Quan hệ các goal:** `spring-boot:repackage` tạo executable Java archive; `spring-boot:build-image` dùng Buildpacks để tạo OCI image. Cả hai không tương đương `mvn deploy` (Maven distribution).

## 13. Phác thảo pipeline release có kiểm soát

Một luồng phát hành tốt tách trách nhiệm:

```text
(1) Build & test
    mvn clean verify
    |
    +-- app.jar, app.jar.sha256, test reports, SBOM
    |
    v
(2) Lưu CI artifacts theo run/commit, retention ngắn-vừa
    |
    +-- job QA tải lại JAR, verify checksum, smoke test
    |
    v
(3) Approve release / security scanning / provenance
    |
    +-- Maven repository (nếu có Java consumers)
    |      Maven GAV + POM + checksum, immutable release version
    |
    +-- OCI registry (nếu deploy containers)
           image digest + manifests/layers, arch coverage
    |
    v
(4) Deploy
    - Java consumer: GAV/version đã lock
    - Kubernetes/container: repository@sha256:index-or-manifest-digest
    - VM java -jar: tải đúng JAR release + kiểm checksum
```

**Tránh “được QA ở A nhưng publish B”:** nếu job QA test file JAR từ một run, job publish lại build source khác version/dependency/JDK mà không kiểm tra bytes, sản phẩm phát hành có thể không giống artifact đã kiểm thử. Phương pháp đáng tin là **promote chính bytes đã kiểm**, hoặc build lại reproducibly và **chứng minh checksum bằng nhau** trước publish.

### 13.1. Build một lần, publish nhiều dạng

CI có thể chạy `mvn clean deploy` trong **một invocation** khi publish Maven repository và điều kiện QA gate đã được đảm bảo trước deploy. Cùng phiên đó, lấy executable JAR và dùng Dockerfile để tạo OCI image.

Nếu phải tách jobs:
- upload JAR + checksum;
- job tiếp theo download và đối chiếu;
- publish image từ đúng downloaded JAR;
- Maven publish dùng một cơ chế hỗ trợ publish **file đã kiểm** với POM/coordinates đầy đủ, hoặc dùng build/release job thống nhất; không mặc định gọi `mvn deploy` từ một folder chỉ có JAR mà không có Maven POM.
- giữ provenance liên kết Git commit, artifact SHA-256, image digest, build run ID.

Không có một cú pháp CI chung dùng được mọi provider; GitHub Actions YAML phía trên là ví dụ về handoff, còn publish commands phụ thuộc kho thật.

### 13.2. Đặt metadata release ở đâu?

Một bản ghi release hữu ích:

| Trường | Ví dụ định dạng | Mục đích |
| --- | --- | --- |
| Git revision | commit SHA đã duyệt | Nguồn build |
| Maven coordinates | `com.example:release-demo:0.1.0` | Java package identity |
| Executable JAR checksum | `sha256:...` của file JAR thực | Kiểm chứng bytes |
| CI build | run ID + workflow + job | Tìm logs/evidence |
| OCI image ref | `registry/team/release-demo:0.1.0` | Tên phát hành dễ đọc |
| OCI digest | `sha256:...` của manifest/index thực | Pin image trên runtime |
| SBOM/provenance | Tệp hoặc OCI artifact reference có kiểm chứng | Supply-chain trace |
| Test/security status | Gate name, timestamp, tool version | Quyết định promotion |

Không tự suy ra một digest từ version string. Mỗi digest phải được tính/đọc từ đúng binary/registry.

## 14. Retention và immutability: không thể dùng chung một chính sách

### Maven releases

Maven hosted release repository nên **ngăn overwrite/deletion tùy tiện**, lưu POM/JAR và metadata đủ lâu cho các consumers tái lập. Maven SNAPSHOTs có retention/cleanup riêng để giới hạn lưu trữ nhưng cần rõ policy để CI không bất ngờ mất dependency.

### CI artifacts

Artifacts gắn với từng run thường có retention giới hạn, ví dụ 7 hoặc 30 ngày theo policy tổ chức. Đặt retention có chủ đích: test reports của PR có thể giữ ngắn, còn release approvals/provenance cần được **archival sang kho dài hạn** nếu pháp lý/audit yêu cầu. Không dùng tên artifact giống nhau giữa runs làm bằng chứng content immutable lâu dài.

### OCI images

Container registry có lifecycle cho **tags, manifests, layers và garbage collection**. Một tag có thể mutable, digest content-addressed. Nhưng digest có thể không còn pull được nếu registry xóa manifest/layers theo retention và garbage collection; lưu giữ release images theo policy, đặc biệt cho rollback.

**Một bản release đầy đủ cần cân đối ba chính sách**: xóa CI artifacts cũ không nên làm mất bản release dùng bởi production; xóa image layers đang được digest reference không được làm rollback thất bại; Maven release artifacts phải có retention và quyền phù hợp.

## 15. Authentication và phân quyền: ba giao thức khác nhau

| Đích | Credential thường gặp | Quyền nên tách |
| --- | --- | --- |
| Maven repository | `settings.xml` server credentials/token, repository manager roles | Read dependencies; deploy releases/snapshots |
| CI artifact store | CI job identity/token, run access, repository permissions | Upload artifact của job; download trong workflow; admin delete |
| OCI registry | Docker login/credential helper, OCI registry token/OIDC | Pull image; push image; delete/retag theo policy |

**Không dùng chung một admin token** cho cả Maven, CI và OCI nếu có thể. Thiết kế nguyên tắc **least privilege**: build job chỉ cần đọc dependencies; publish job được cấp quyền write đúng repository; deploy runtime chỉ cần pull. Tách credentials release và snapshot, giới hạn OIDC subject/audience khi áp dụng federation.

### 15.1. Tránh lộ secret khi build

- Không đưa Maven password/token vào `pom.xml` hoặc `settings.xml` commit trong Git.
- Không thêm `ARG SECRET=...` trong Dockerfile rồi ghi secret vào layer/history.
- Không upload `~/.m2/settings.xml`, `.docker/config.json`, `.env` hoặc token file vào CI artifact.
- Tránh bật Maven `-X` hoặc echo tất cả environment variables trong public CI logs khi có secrets.
- Không dùng untrusted PR runner với credentials publish có quyền production.
- Dùng secret store của CI, permissions nhỏ và review provenance trước promotion.

OCI image và Maven JAR có thể được tải/giải nén/inspect; “đóng trong archive” **không phải mã hóa**. Nếu Maven artifact là nội bộ, thiết lập repository access rõ; nếu image chứa config runtime secret thì phải di chuyển secret ra runtime secret store.

## 16. Checksum, provenance và signature: giá trị của từng nơi

**Checksum** dùng để đối chiếu rằng bytes file đang có khớp với hash dự kiến. Nhưng có nhiều đối tượng cần hash:

```text
Git tree/commit hash
         |
         v
JAR file bytes ----> sha256(JAR)
         |
         v
Docker build -----> OCI manifest/index digest
         |
         +----------> layer digests (nhiều layers)
```

`sha256(JAR)` không phải OCI image digest. Maven repository có thể lưu checksums của JAR/POM; CI artifact có checksum của raw file; OCI registry có content-addressed manifests/layers. Chúng liên quan cùng một release nhưng **không trùng giá trị**.

### 16.1. Checksum không tự chứng minh nguồn đáng tin

Một attacker có thể thay artifact và thay checksum nếu kiểm soát cả hai. Vì vậy supply-chain assurance còn cần:
- trusted build identity;
- repository/registry access controls;
- signed artifacts/attestations/provenance khi policy yêu cầu;
- SBOM, vulnerability/license scans;
- immutable version/digest/registry policies;
- reproducible builds hoặc binary promotion.

Đừng quảng bá `sha256sum -c` như một chữ ký số. Nó chỉ so sánh content hash với dữ liệu bạn tin là đã lấy từ nguồn hợp lệ.

### 16.2. Maven GAV không phải toàn bộ provenance

`com.example:release-demo:0.1.0` giúp consumers tìm artifact, nhưng không chứng minh ai build bằng toolchain nào. Cần lưu lại Git commit, CI run, JAR SHA, repository write identity và security evidence trong hệ thống phát hành. Tương tự, OCI tag `:0.1.0` chỉ là alias; deploy production nên pin/ghi lại **digest thực tế**.

## 17. Bài toán nhiều kiến trúc và OCI index

Khi publish OCI image cho `linux/amd64` và `linux/arm64`, Buildx có thể tạo **multi-platform image index**. Trong khi đó file JAR Java 17 có thể vẫn là cùng một artifact Java portable (nếu không có native dependencies).

```text
app.jar (Java bytecode)
       |
       +--> JRE/base linux/amd64 -> image manifest AMD64
       |
       +--> JRE/base linux/arm64 -> image manifest ARM64
                     |
                     v
            OCI multi-platform index
```

Vì vậy:
- Maven repository có thể phân phối **một Java JAR**;
- CI artifact store có thể giữ **một JAR** và logs;
- OCI registry có thể lưu **nhiều manifests/layers** cho từng CPU architecture dưới **một tag/index**.

Kiểm tra bằng:

```bash
docker buildx imagetools inspect "$IMAGE_REF"
```

Khi image được push và `IMAGE_REF` có thật. Không dùng `uname -m` trên developer laptop làm bằng chứng image đa nền tảng; cần kiểm tra index manifests và smoke test trên target CPU. Nếu executable Spring Boot có JNI/native dependencies hoặc native-image (GraalVM), artifact chạy có thể cần build riêng theo kiến trúc.

## 18. CI/CD chống phát hành nhầm sản phẩm

### 18.1. Không phát hành trước khi kiểm thử

Một chuỗi gate an toàn:
1. Build Maven/Gradle, chạy unit/integration tests.
2. Lưu JAR/checksum/report ở CI artifact store.
3. Job khác download và verify checksum, chạy smoke test trên đúng bytes.
4. Security scan/SBOM/provenance và release approval khi cần.
5. Publish Maven components nếu có Java consumers.
6. Build/push OCI image từ JAR đã kiểm, scan final image và inspect index.
7. Deploy bằng Maven version có checksum hoặc OCI digest đã phát hành.
8. Record rollback references, monitor health.

**Đánh đổi:** `mvn deploy` là lifecycle bao gồm compile/test/package/install/deploy trong một invocation. Nếu bạn dùng nó trực tiếp sau khi tất cả gate đã đủ, Maven tự chạy các phases. Nếu muốn tách approval **sau QA** nhưng **trước publish**, pipeline phải tổ chức jobs/cơ chế promotion cẩn thận để không rebuild thành file khác.

### 18.2. Khác nhau giữa “upload thành công” và “phát hành thành công”

Một HTTP 200 từ workflow artifact upload chứng minh file đã vào CI storage **theo API của CI**. Nó không chứng minh:
- Maven consumers resolve được `GAV`;
- OCI runtime pull được image digest;
- image đã được scan;
- JAR đúng version/manifest;
- release production đã deploy;
- artifact được giữ đủ lâu.

Một `mvn deploy` SUCCESS chứng minh Maven deployment step hoàn thành theo response repository, nhưng không tự chứng minh image OCI được publish hoặc chạy được trên Kubernetes.

Một `docker push` SUCCESS chứng minh registry nhận image layers/manifests, nhưng không tự chứng minh Maven repository đã có POM/JAR hoặc artifact đúng checksum trong CI.

## 19. Các lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| `mvn package` thành công nhưng đồng nghiệp không lấy được artifact | JAR chỉ nằm ở `target` hoặc local Maven repository | Publish `mvn deploy` tới hosted Maven repo có policy |
| `mvn install` rồi máy CI khác fail | Local `~/.m2/repository` không chia sẻ | Dùng remote Maven repository hoặc cùng reactor build |
| CI upload artifact nhưng consumer Maven `Could not find artifact` | Workflow artifact không có GAV/POM/metadata | Publish Maven repository đúng format |
| `mvn deploy` báo repository chưa chỉ định | Thiếu `distributionManagement` hoặc alt repo | Cấu hình deploy target chính xác |
| Maven deploy báo 401/403 | Server ID/token/quyền sai | So `distributionManagement.id` và `settings.xml server.id` |
| Maven deploy báo 404 | URL trỏ sai repository endpoint hoặc không hỗ trợ upload | Kiểm tra hosted repo URL/type |
| Maven release bị chặn overwrite | Version đã được publish và immutability policy | Tăng version, không ghi đè release |
| Maven snapshot cũ | Repository metadata/cache `updatePolicy` | Kiểm tra metadata/policy/version và CI cache |
| `docker pull` thất bại dù JAR có trong Maven repo | Container image chưa được publish OCI | Build/tag/push image tới registry |
| `docker push` 401/403 | OCI registry auth/push permission sai | Login bằng token phù hợp, check image reference |
| Docker push xong Kubernetes `ImagePullBackOff` | Sai registry/image tag, thiếu pull secret hoặc platform | Inspect image reference/index, node architecture, credentials |
| `no match for platform in manifest` | OCI index thiếu requested CPU architecture | Build/push target platform tương ứng |
| Docker image có sai Java app | Dockerfile COPY JAR khác version hoặc rebuild sau QA | Dùng JAR đã checksum, kiểm tra contents và image provenance |
| `java -jar` chạy fail từ JAR trong Maven repo | Published plain JAR không phải executable Boot JAR | Chọn đúng classifier/JAR và manifest |
| Library consumer không load class từ Boot JAR | Dùng executable `BOOT-INF/classes` làm dependency | Publish plain library JAR hoặc module library riêng |
| CI artifact đã biến mất | Retention hết hạn hoặc workflow run bị xóa | Lưu release binary vào kho dài hạn, không dựa run artifacts |
| Checksum của downloaded artifact archive khác | So sánh ZIP wrapper thay vì raw JAR | Hash và verify raw JAR bên trong |
| OCI tag trỏ bản mới, rollback sai | Tag mutable, thiếu digest pin | Record/deploy bằng `repository@sha256:...` |
| Maven dependency được tải nhưng transitive thiếu | POM metadata chưa đúng, exclusions/scope sai | Kiểm tra published POM/dependency graph |
| Các job build cùng version nhưng checksum khác | Toolchain, timestamp, dependency, generated resources khác | Promote đúng bytes hoặc reproducible build comparison |
| Scan JAR PASS nhưng image có CVE JRE | Scan chưa xét base OS/JRE layers | Scan **final OCI image** và base digest |
| CI job tải artifact khác run | Chọn sai name/run-id/permissions | Pin run ID, verify SHA-256 và provenance |

### 19.1. Quy trình kiểm tra nhanh từ triệu chứng

1. **Hỏi người tiêu thụ dùng công cụ nào**: Maven/Gradle, CI download hay Kubernetes/docker pull?
2. **Xác định identity**: GAV (Java package), run-id+artifact-name (CI), repo:tag/digest (OCI).
3. **Kiểm tra nơi file đã thực sự tới**: `target`/`~/.m2` không phải remote Maven deploy; local Docker image không phải remote OCI registry.
4. **Xác minh quyền truy cập và endpoint type**: Maven hosted endpoint, CI artifact API, OCI Registry API có khác nhau.
5. **Đối chiếu checksum** raw JAR trước/sau handoff, hoặc digest OCI đã push.
6. **Xem metadata**: POM/transitive Maven, CI retention/run ID, OCI manifest/platform list.
7. **Chạy consumer thật**: `mvn dependency:get`, CI download/checksum hoặc `docker pull`/runtime smoke test.
8. **Kiểm tra release policy**: immutable releases, OCI tag overwrite, CI artifact expiry.
9. **Kiểm tra security/trust**: nguồn publish, signed attestations, SBOM và quyền.
10. **Record kết quả**: GAV/JAR SHA/CI run ID/OCI digest và timestamps vào release record.

## 20. Những hiểu lầm nên loại bỏ

1. **“Cả ba đều có tên artifact nên giống nhau.”** Không: mỗi nơi có **định danh/giao thức/metadata** riêng.
2. **“`mvn package` là publish.”** Không: nó chỉ tạo output trong `target`.
3. **“`mvn install` là publish cho toàn team.”** Không: nó thường chỉ cài vào Maven local repository.
4. **“`actions/upload-artifact` đã tạo Maven release.”** Không: đó là workflow artifact, không có GAV/POM theo giao thức Maven.
5. **“`docker push` làm module Java có thể được import bằng Maven.”** Không: push chỉ phát hành OCI image/artifact theo registry semantics.
6. **“Một server Artifactory/Nexus phục vụ cả ba thì API giống nhau.”** Không: cùng hệ thống có thể chứa nhiều repository types/paths.
7. **“OCI tag `:1.0.0` là immutable.”** Không mặc định; cần tag immutability policy hoặc digest pin.
8. **“Maven GAV đủ chứng minh đúng source commit.”** Không: cần provenance/checksum và release process.
9. **“JAR SHA-256 = image digest.”** Không: đối tượng hash khác nhau.
10. **“CI artifacts có thể giữ mãi không mất.”** Không nên mặc định; retention/expiry có thể xóa.
11. **“Executable Spring Boot JAR lý tưởng làm dependency library.”** Thường không; dùng plain JAR cho library.
12. **“Chỉ cần upload JAR qua HTTP vào một URL có chữ maven.”** Không đảm bảo POM/metadata/layout hợp lệ.
13. **“Đã push OCI image nghĩa là image chạy trên mọi CPU.”** Không: cần manifests tương ứng.
14. **“Digest pin chứng minh publisher đáng tin.”** Không: digest chỉ content addressing, còn trust cần provenance/signature/policy.
15. **“Build lại cùng version tự động tạo binary giống hệt.”** Không nếu toolchain/dependencies/timestamp khác.
16. **“Lưu SBOM vào CI artifact tự động gắn nó vào image.”** Không: cần OCI attestation/attachment hoặc release record linkage cụ thể.
17. **“Maven snapshot và Docker tag mutable là cùng một cơ chế.”** Không: Maven có snapshot metadata/version semantics khác OCI tag pointer.
18. **“Muốn release app lên Kubernetes bắt buộc phải publish Maven JAR.”** Không: có thể build/push OCI image từ kiểm chứng JAR và deploy image digest.
19. **“Dùng OCI registry chứa generic artifacts thì Maven tự hiểu.”** Không, trừ khi có tooling/adapter thật sự hỗ trợ Maven protocol.
20. **“CI cache và CI artifact là một.”** Không: cache tối ưu build inputs, artifact lưu build outputs/evidence.

## 21. Bảng quyết định: nên publish đi đâu?

| Tình huống | Đích phù hợp | Lý do |
| --- | --- | --- |
| Team khác khai báo `<dependency>com.example:api:1.2.0</dependency>` | Maven repository | Cần GAV, POM, transitive dependency resolution |
| Spring Boot service deploy bằng Kubernetes | OCI registry | Kubelet/container runtime kéo image bằng digest |
| Job test ở workflow khác cần JAR đã build | CI artifact store hoặc release artifact store | Handoff đúng bytes, gắn run/commit và checksum |
| Lưu test reports của PR trong vài ngày | CI artifact store | Debug/QA gắn workflow run |
| Phát hành plain Java library dùng cho Gradle/Maven | Maven repository | Chuẩn Java ecosystem |
| Phân phối VM service để chạy `java -jar` | Maven repository, release storage hoặc kho artifact dài hạn phù hợp | Phụ thuộc cách installer/updater lấy binary và kiểm checksum |
| Phân phối container image multiarch | OCI registry có image index | Runtime chọn OS/architecture variant |
| Lưu Helm chart theo OCI | OCI registry có hỗ trợ artifact type | Dùng Helm/OCI client tương ứng, không phải Maven GAV |
| Lưu SBOM/provenance dài hạn | OCI attachments, release archive hoặc artifact store có retention thích hợp | Cần gắn digest/version và policy |
| Lưu intermediate build output chỉ trong một run | CI artifact store | Không cần permanent package publishing |

**Quy tắc dễ nhớ:** hỏi “**người nhận sẽ gõ lệnh gì?**” Nếu họ chạy `mvn dependency:get`, đó là Maven repository; nếu job gọi `download-artifact`, đó là CI artifact; nếu node chạy `docker pull`, đó là OCI registry.

## 22. Checklist release Spring Boot

- [ ] Phân biệt Java **library** và Spring Boot **executable application**.
- [ ] Quy định GAV/version/packaging/classifier khi cần Maven package.
- [ ] Maven `distributionManagement` trỏ đúng hosted releases/snapshots repo.
- [ ] Maven `settings.xml server.id` khớp repo ID; token từ secret store, không commit.
- [ ] Chạy tests trước khi publish; nếu dùng `mvn deploy`, hiểu lifecycle thực thi đến deploy.
- [ ] Không dựa `mvn install` như kho dùng chung giữa CI runners.
- [ ] CI artifact có name/run ID/retention/checksum rõ và không chứa secrets.
- [ ] Download CI artifact được verify raw JAR checksum trước khi dùng cho các bước tiếp.
- [ ] Container image được build từ **JAR đã kiểm** chứ không rebuild không kiểm soát.
- [ ] OCI registry image reference có namespace/tag đúng và được push thành công.
- [ ] Ghi **image digest thực** sau push; với multiarch kiểm tra index/platforms.
- [ ] Maven release và OCI image có immutable/retention policy phù hợp với rollback.
- [ ] Release metadata liên kết Git commit ↔ JAR SHA ↔ CI run ↔ OCI digest.
- [ ] Scan Java dependencies, image OS/JRE layers, SBOM và provenance theo policy.
- [ ] Cấp quyền tách read/publish/deploy, không dùng chung admin token.
- [ ] Kiểm thử từ phía **consumer thật**: Maven resolve, CI download, docker pull/smoke.
- [ ] Cập nhật base image/dependencies chủ động dù artifacts đã được pin.
- [ ] Không tuyên bố phát hành hoàn tất chỉ từ một bước upload thành công.

## 23. Tài liệu chính thức

- Apache Maven – [Maven Repositories](https://maven.apache.org/repositories/index.html): local/remote Maven repositories và download.
- Apache Maven – [Introduction to the Repository](https://maven.apache.org/guides/introduction/introduction-to-repositories.html): Maven layout/metadata và repository usage.
- Apache Maven – [POM Reference](https://maven.apache.org/pom.html): `groupId`, `artifactId`, `version`, `distributionManagement`.
- Maven Deploy Plugin – [Usage](https://maven.apache.org/plugins/maven-deploy-plugin-4.x/usage.html): `deploy`, `deploy-file`, release/snapshot destinations và server IDs.
- Apache Maven – [Security and Deployment Settings](https://maven.apache.org/guides/mini/guide-deployment-security-settings.html): `settings.xml` credentials không đặt vào POM.
- GitHub Actions – [Workflow artifacts](https://docs.github.com/en/actions/concepts/workflows-and-actions/workflow-artifacts): đặc điểm, phạm vi và cache/artifact distinction.
- GitHub Actions – [Store and share data with workflow artifacts](https://docs.github.com/en/actions/tutorials/store-and-share-data): `upload-artifact`, `download-artifact`, `retention-days`.
- Docker – [Push images to a repository](https://docs.docker.com/docker-hub/repos/manage/hub-images/push/): `docker tag` và `docker push`.
- Docker – [Image digests and manifests](https://docs.docker.com/dhi/explore/security-concepts/digests/): content addressing, index/manifest.
- Docker – [Multi-platform builds](https://docs.docker.com/build/building/multi-platform/): image index và CPU variants.
- Spring Boot 3.5 – [Maven Plugin: Packaging Executable Archives](https://docs.spring.io/spring-boot/3.5/maven-plugin/packaging.html): `spring-boot:repackage` và classifier.
- Spring Boot 3.5 – [Maven Plugin: Packaging OCI Images](https://docs.spring.io/spring-boot/3.5/maven-plugin/build-image.html): Cloud Native Buildpacks và image publishing.
- Spring Boot 3.5 – [Gradle Plugin: Packaging OCI Images](https://docs.spring.io/spring-boot/3.5/gradle-plugin/packaging-oci-image.html): `bootBuildImage` và registry.
- Gradle – [Maven Publish Plugin](https://docs.gradle.org/current/userguide/publishing_maven.html): `maven-publish`, publications và repositories.

**Kết luận:** cùng là “artifact” nhưng **Maven repository** phục vụ **Java components theo GAV/POM**, **CI artifact store** giữ **đầu ra và bằng chứng của workflow run**, còn **OCI registry** phục vụ **container images theo tag/digest/manifests/layers**. Một bản phát hành Spring Boot có thể cần cả ba, nhưng phải xác định consumer, version identity, retention, quyền và checksum cho từng nơi. Giữ chuỗi **Git commit → JAR SHA-256 → CI run → Maven GAV (nếu có) → OCI image digest (nếu có)** để bảo đảm có thể truy vết, kiểm chứng và rollback.