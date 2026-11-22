# Hoàn thiện CI tạo artifact có checksum, metadata và SBOM để truy vết

Một pipeline CI chỉ chạy test xanh và tạo được file JAR chưa đủ để trả lời các câu hỏi quan trọng khi phát hành: **file này được build từ commit nào, bằng JDK và dependency versions nào, những component bên thứ ba nào nằm trong nó, file có bị thay đổi trên đường chuyển giao không, và ai có thể chứng minh quá trình build?** Khi có sự cố bảo mật hoặc cần rollback, thiếu những dữ liệu này khiến nhóm phải lần ngược log và đoán artifact nào đã được triển khai.

Bài này xây dựng quy trình phát hành cho ứng dụng Spring Boot gồm các bằng chứng liên kết với nhau: **artifact**, **checksum SHA-256**, **build metadata**, **Software Bill of Materials (SBOM)** và **provenance attestation**. Ví dụ dùng **Java 17, Spring Boot 3.3.13**, Maven hoặc Gradle, định dạng SBOM CycloneDX và workflow CI minh họa. Kết quả là một gói bằng chứng có thể kiểm tra độc lập, gắn với source commit và artifact digest, rồi lưu cùng release.

**Phân biệt từ đầu:** checksum giúp phát hiện bytes không khớp digest đáng tin; metadata mô tả build; SBOM liệt kê components và quan hệ dependency; provenance/attestation cung cấp claim có thể xác minh về nơi và cách artifact được tạo. Mỗi loại giải quyết một câu hỏi khác nhau, không thay thế cho nhau.

## 1. Mô hình truy vết từ source tới artifact được triển khai

Một release có thể được biểu diễn như chuỗi:

```text
Git commit + tag
       |
       v
CI workflow + trusted builder
       |
       +--> JDK / Maven or Gradle / plugin versions
       +--> resolved dependency graph
       |
       v
Spring Boot executable JAR/WAR
       |
       +--> SHA-256 checksum
       +--> build-metadata.json
       +--> SBOM (CycloneDX or SPDX)
       +--> signed provenance / attestation
       |
       v
Immutable artifact storage / release
       |
       v
Verify checksum + attestation + policy
       |
       v
Deploy the same artifact bytes
```

Mục tiêu là có thể đi ngược từ artifact đang chạy: xác định digest, tra attestation, kiểm tra commit/build invocation, đọc SBOM để biết dependencies và đối chiếu metadata để biết toolchain.

**Build once, promote many:** build artifact một lần ở pipeline release, kiểm tra nó, rồi chuyển cùng bytes qua staging/production. Nếu mỗi môi trường build lại từ source, dù cùng version string, artifact có thể khác do dependency resolution, JDK, plugin, timestamp hoặc build parameters. Checksum khi đó chỉ chứng minh bytes của từng lần build, không chứng minh hai môi trường dùng cùng artifact.

## 2. Năm loại bằng chứng và câu hỏi mỗi loại trả lời

| Thành phần | Nó mô tả hoặc chứng minh điều gì? | Giới hạn |
| --- | --- | --- |
| **Artifact** | File thực tế sẽ được phân phối, ví dụ traceable-app-1.0.0.jar | Tên/version không chứng minh nguồn gốc |
| **Checksum SHA-256** | Bytes của file có khớp digest được công bố hay không | Nếu attacker thay cả file và checksum thì phép so sánh vẫn có thể pass |
| **Build metadata** | Commit, version, JDK, build tool, workflow, thời điểm, file đầu ra | JSON tự tạo không tự chứng minh thông tin là đáng tin |
| **SBOM** | Components, versions, licenses, hashes và dependency relationships | Không tự chứng minh artifact được build ở đâu hoặc đã an toàn |
| **Provenance/attestation** | Artifact digest gắn với source, builder identity và quy trình build có thể xác minh | Cần trust build platform, identity và verification policy |

Checksum không phải chữ ký số. SBOM không phải báo cáo “không có lỗ hổng”. Metadata không phải provenance được ký. Attestation cũng không thay thế việc review SBOM hoặc chạy security scanning.

## 3. Chọn định dạng SBOM: CycloneDX hay SPDX?

**SBOM** là bản kê khai máy đọc được về những thành phần phần mềm tạo nên sản phẩm. Với Java/Spring Boot, nó thường mô tả component chính, dependency trực tiếp/gián tiếp đã resolve, Package URL (PURL), version, hashes, license, external references và quan hệ giữa các components.

Hai chuẩn được sử dụng rộng rãi:

| Chuẩn | Điểm mạnh thường gặp | Dùng khi |
| --- | --- | --- |
| **CycloneDX** | Tập trung vào inventory, dependency graph và use case bảo mật; hỗ trợ JSON/XML/Protocol Buffers | Component analysis, vulnerability management và VEX |
| **SPDX** | Mô hình hóa package, file, license, copyright và quan hệ; là chuẩn ISO/IEC 5962:2021 | License compliance và trao đổi inventory theo SPDX |

CycloneDX 1.7 là phiên bản chuẩn được Ecma International công bố trong ECMA-424 ấn bản thứ hai tháng 12/2025. Ví dụ dưới đây ghim CycloneDX 1.6 để Maven/Gradle tạo đầu ra đồng nhất và tương thích rộng; có thể nâng schema sau khi xác nhận các consumer hỗ trợ.

**Không tự viết JSON giống SBOM rồi gọi đó là CycloneDX/SPDX.** Dùng plugin/tool tạo đúng schema, sau đó validate file bằng parser/validator tương ứng. JSON hợp lệ về cú pháp chưa chắc hợp lệ theo schema SBOM.

## 4. SBOM của Java dependencies khác SBOM của container image

Với ứng dụng Spring Boot chạy trong executable JAR, SBOM từ Maven/Gradle phản ánh dependency graph mà build tool đã resolve: Spring Framework, Jackson, logging, database drivers và các thư viện runtime khác. Scope test thường không thuộc inventory runtime; provided có thể cần đưa vào SBOM nếu thành phần đó do deployment platform cung cấp.

Dependencies bị shade/relocate, thư viện copy thủ công, generated binary hoặc thành phần không khai báo trong build graph có thể không được mô tả đầy đủ.

Nếu đóng gói bằng Cloud Native Buildpacks hoặc Docker:
- Image còn chứa **OS packages, base/run image layers, JVM runtime và các thành phần buildpack cung cấp**.
- SBOM Java dependency graph không tự bao gồm tất cả thành phần hệ điều hành của final OCI image.
- Cần thêm **SBOM của container image** từ công cụ có khả năng inspect image cuối cùng, rồi gắn kết quả với image digest.

Hãy xác định rõ SBOM mô tả một module JAR, toàn bộ multi-module distribution, executable WAR hay OCI image. Nếu release gồm nhiều module, chỉ dùng aggregate SBOM khi nó phản ánh đúng tập module được đóng gói.

## 5. Checksum SHA-256: kiểm tra bytes của artifact

SHA-256 tạo digest 256 bit từ nội dung file. Cùng một file và cùng thuật toán sẽ cho cùng digest; chỉ cần một byte thay đổi thì digest gần như chắc chắn thay đổi.

Trên Linux/macOS:

```bash
sha256sum target/traceable-app-1.0.0.jar
```

Output có một chuỗi 64 ký tự hex theo sau là tên file. Digest thật phải được tính từ artifact vừa tạo; không copy giá trị mẫu vào release.

Trên Windows PowerShell:

```powershell
Get-FileHash .\target\traceable-app-1.0.0.jar -Algorithm SHA256
```

Kết quả có trường Hash và Algorithm. Với file tải về, tính hash **sau khi download** rồi so sánh với checksum lấy từ nguồn đáng tin cậy.

### 5.1. Manifest cho nhiều file

Một release có thể có SHA256SUMS liệt kê artifact, SBOM và metadata:

```bash
cd dist
sha256sum traceable-app-1.0.0.jar bom.json build-metadata.json > SHA256SUMS
sha256sum --check SHA256SUMS
```

Khi mọi file khớp, output có dạng:

```text
traceable-app-1.0.0.jar: OK
bom.json: OK
build-metadata.json: OK
```

Chạy lệnh verify từ thư mục dist như ví dụ vì manifest lưu filename tương đối. Nếu file bị sửa, thiếu hoặc khác bytes, sha256sum --check trả lỗi và exit code khác 0.

### 5.2. Checksum không đủ chống giả mạo

Nếu artifact và SHA256SUMS được tải từ cùng một website không đáng tin, attacker có thể thay cả hai. Phép so sánh vẫn thành công nhưng người nhận đã lấy artifact giả.

Do đó:
- Dùng checksum để phát hiện corruption và xác minh file khớp digest tham chiếu.
- Lấy digest từ kênh đã xác thực hoặc kiểm tra chữ ký/attestation có identity đáng tin.
- Không dùng MD5 hoặc SHA-1 làm cơ chế integrity/security cho release mới.
- Nếu artifact có provenance attestation, xác minh signer identity và subject digest theo policy.

**Checksum trả lời “bytes có khớp không?”; chữ ký/attestation trả lời thêm “ai đã xác nhận digest này và trong quy trình nào?”.**

## 6. Build metadata: ghi lại cách artifact được tạo

Metadata là tài liệu sidecar, ví dụ build-metadata.json, mô tả một lần build. Những trường hữu ích:

| Nhóm | Trường nên lưu |
| --- | --- |
| Artifact | Tên file, version, packaging type, media type, SHA-256 |
| Source | Repository URI, full commit SHA, tag/release, trạng thái working tree |
| Build invocation | Workflow/job, run ID, attempt, URL, start/end time |
| Toolchain | JDK vendor/version, Maven/Gradle Wrapper, Spring Boot/plugin versions, OS/architecture |
| Dependencies | SBOM path/digest, lockfile/verification metadata digest, dependency graph reference |
| Builder | CI platform identity, build container/builder image digest nếu có |
| Publication | Repository/package coordinate, registry, release ID và digest sau publish |

Dùng **full Git commit SHA**, không chỉ branch name hoặc short SHA. Branch có thể di chuyển; commit SHA xác định nội dung source cụ thể.

Metadata không nên ghi password, access token, signing key, secret environment variables, credentials từ Maven settings.xml/Gradle properties hoặc toàn bộ environment dump. Chỉ lưu allowlist fields cần cho audit.

Nếu metadata chứa checksum của JAR và SBOM, tạo nó **sau** khi hai file đã hoàn tất. Không nhúng checksum của chính build-metadata.json vào trong nó vì sẽ tạo quan hệ tự tham chiếu; đưa metadata vào SHA256SUMS được tạo sau cùng.

## 7. Provenance và SLSA: nối artifact với source và builder

**Provenance** là thông tin có thể xác minh về nơi, thời điểm và cách một artifact được tạo. SLSA mô tả build provenance trong hệ thống attestation in-toto.

Một build provenance tốt thường liên kết:
- **Subject:** artifact và digest của artifact.
- **Source dependency:** repository và commit cụ thể.
- **Build definition:** loại build, workflow, external parameters và build instructions.
- **Builder identity:** build platform được tin cậy đã thực thi quy trình.
- **Resolved dependencies:** những input đã được lấy trong quá trình build, nếu nền tảng ghi nhận.
- **Run details:** invocation ID và thời gian bắt đầu/kết thúc.

Đối với SLSA/in-toto, provenance là attestation có cấu trúc; subject digest ràng buộc lời khai với bytes của artifact. **Chỉ viết một JSON có tên provenance.json không tự tạo được trust**. Phải dùng build platform hoặc signer có identity được xác minh, bảo vệ identity và kiểm tra attestation khi tiêu thụ artifact.

SLSA v1.2 là phiên bản hiện hành trong tài liệu tham khảo tại thời điểm bài viết. Các cấp SLSA mô tả yêu cầu đối với **build provenance và build platform**, không phải nhãn chất lượng tự động cho SBOM. Có SBOM không có nghĩa build đạt một SLSA level.

## 8. Project Spring Boot Java 17 để tạo artifact thực hành

Cấu trúc tối giản:

```text
traceable-app/
├── pom.xml                         # Maven
├── settings.gradle                 # Gradle thay thế Maven
├── build.gradle                    # Gradle thay thế Maven
├── scripts/
│   └── create-evidence.sh
└── src/
    └── main/
        └── java/com/example/traceable/
            └── TraceabilityApplication.java
```

Maven và Gradle là hai phương án build riêng, dùng chung mã Java.

File src/main/java/com/example/traceable/TraceabilityApplication.java:

```java
package com.example.traceable;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class TraceabilityApplication {

    public static void main(String[] args) {
        SpringApplication.run(TraceabilityApplication.class, args);
    }
}

@RestController
class TraceabilityController {

    @GetMapping("/health")
    String health() {
        return "traceable-app-ok";
    }
}
```

Controller package-private vẫn được Spring component scan phát hiện vì nằm trong package gốc. Khi ứng dụng chạy trên port 8080, HTTP GET /health trả body:

```text
traceable-app-ok
```

Endpoint này là smoke test sau khi tạo JAR/image; nó không phải metadata về commit. Commit và digest cần được lưu trong sidecar/attestation để tránh nhầm lẫn giữa thông tin runtime và bằng chứng build.

## 9. Maven: POM với CycloneDX SBOM

Ví dụ POM dùng Spring Boot 3.3.13 và CycloneDX Maven Plugin 2.9.3. Plugin 2.9.x tạo CycloneDX schema 1.6; đây là lựa chọn thống nhất với ví dụ Gradle bên dưới.

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
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>traceable-app</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>

            <plugin>
                <groupId>org.cyclonedx</groupId>
                <artifactId>cyclonedx-maven-plugin</artifactId>
                <version>2.9.3</version>
                <configuration>
                    <projectType>application</projectType>
                    <schemaVersion>1.6</schemaVersion>
                    <outputFormat>json</outputFormat>
                    <outputName>bom</outputName>
                    <outputDirectory>${project.build.directory}</outputDirectory>
                    <includeCompileScope>true</includeCompileScope>
                    <includeProvidedScope>true</includeProvidedScope>
                    <includeRuntimeScope>true</includeRuntimeScope>
                    <includeTestScope>false</includeTestScope>
                </configuration>
                <executions>
                    <execution>
                        <id>generate-sbom</id>
                        <phase>package</phase>
                        <goals>
                            <goal>makeBom</goal>
                        </goals>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
```

Plugin makeBom tạo SBOM cho module Maven. Với cấu hình trên, file JSON nằm ở target/bom.json. includeProvidedScope=true giữ lại dependencies thuộc provided scope trong inventory; điều này hữu ích khi ứng dụng WAR dựa vào Servlet container bên ngoài. Test scope bị loại để BOM tập trung vào dependencies của ứng dụng.

Đối với Maven multi-module:
- makeBom tạo BOM theo module.
- makeAggregateBom tạo BOM tổng hợp ở root reactor.
- makePackageBom dành cho module có packaging war hoặc ear.

Chọn goal theo **đối tượng phát hành**. Nếu artifact release là một module JAR, BOM của module đó thường phù hợp. Nếu artifact là một distribution kết hợp nhiều module, cần một aggregate BOM mô tả đúng tập module được đóng gói.

## 10. Maven: build artifact và SBOM

Từ thư mục gốc:

```bash
java -version
./mvnw -B -ntp clean verify
```

Nếu không có Maven Wrapper, dùng Maven cài sẵn đã được kiểm soát. Với POM ở mục 9, verify đi qua phase package, nên CycloneDX plugin được gọi theo execution đã khai báo.

Kiểm tra output:

```bash
test -s target/traceable-app-1.0.0.jar
test -s target/bom.json
jar tf target/traceable-app-1.0.0.jar
```

Kiểm tra nhanh component trong SBOM:

```bash
grep -n '"bomFormat"' target/bom.json
grep -n '"components"' target/bom.json
```

JSON output phải ghi nhận format CycloneDX và có component data. grep chỉ là kiểm tra sơ bộ; CI nghiêm túc nên dùng CycloneDX validator hoặc parser hiểu schema đã chọn.

Xem dependency graph Maven riêng:

```bash
./mvnw -B dependency:tree -Dverbose \
    -DoutputFile=target/dependency-tree.txt
```

Dependency tree là bằng chứng bổ trợ giúp điều tra cách Maven resolve version; **SBOM là inventory chuẩn hóa để trao đổi giữa các hệ thống**. Hai file không cùng mục đích và có thể được lưu cùng release nếu cần điều tra sâu.

## 11. Gradle: plugin CycloneDX và SBOM Direct

Gradle ví dụ dùng Spring Boot 3.3.13, Java 17 và CycloneDX Gradle plugin 3.5.1. Plugin dòng 3.x yêu cầu **Gradle 8.4 trở lên**. Nếu wrapper dự án cũ hơn, phải chọn phiên bản plugin tương thích hoặc nâng Gradle Wrapper có kiểm thử.

File settings.gradle:

```groovy
rootProject.name = 'traceable-app'
```

File build.gradle:

```groovy
import org.cyclonedx.Version
import org.cyclonedx.model.Component

plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'org.cyclonedx.bom' version '3.5.1'
}

group = 'com.example'
version = '1.0.0'

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

springBoot {
    mainClass = 'com.example.traceable.TraceabilityApplication'
}

tasks.named('test') {
    useJUnitPlatform()
}

tasks.named('cyclonedxDirectBom') {
    projectType = Component.Type.APPLICATION
    schemaVersion = Version.VERSION_16
    includeConfigs = ['compileClasspath', 'runtimeClasspath']
    skipConfigs = ['(?i).*test.*']
}
```

cyclonedxDirectBom tạo SBOM cho project hiện tại. Mặc định JSON output nằm ở build/reports/cyclonedx-direct/bom.json. Plugin 3.x cũng đăng ký Direct SBOM task cho subprojects khi được áp dụng ở root. cyclonedxBom tạo **aggregate SBOM** từ Direct SBOM của các project được bật; chỉ dùng aggregate khi artifact/distribution thật sự bao gồm tập project đó.

Build:

```bash
./gradlew clean test bootJar cyclonedxDirectBom
```

Kiểm tra:

```bash
test -s build/libs/traceable-app-1.0.0.jar
test -s build/reports/cyclonedx-direct/bom.json
```

Dependency graph hỗ trợ điều tra:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

Với multi-module, có thể tạo SBOM riêng cho app module bằng task project path hoặc tạo aggregate ở root. Đừng attach aggregate SBOM vào một JAR module đơn lẻ nếu aggregate còn mô tả các module không nằm trong artifact đó; consumer sẽ hiểu sai boundary.

## 12. Chọn đúng phạm vi dependencies trong SBOM

Để SBOM hữu ích cho security và compliance, cần hiểu configuration/scope mà tool đưa vào:

| Nguồn | Có nên đưa vào SBOM của runtime artifact? | Ghi chú |
| --- | --- | --- |
| Compile/runtime dependencies | Có | Đây thường là components trực tiếp hoặc gián tiếp của ứng dụng |
| Maven provided / Gradle providedRuntime | Thường có khi mô tả WAR triển khai lên container | Server cung cấp ở runtime nhưng vẫn là dependency của deployment contract |
| Test-only dependencies | Thường không trong runtime SBOM | Có thể tạo SBOM riêng cho test/build environment nếu policy yêu cầu |
| Build plugins/build tools | Có thể cần SBOM riêng cho build environment | Không tự trộn chúng vào runtime SBOM |
| OS packages/base image | Cần image SBOM riêng nếu phát hành container | Java dependency plugin không mô tả đầy đủ các layer hệ điều hành |
| Dependencies được copy/shade thủ công | Cần kiểm tra bổ sung | Build graph có thể không biết chúng tồn tại |

Trong Maven, includeCompileScope, includeProvidedScope, includeRuntimeScope, includeTestScope quyết định scope được tính. Trong Gradle plugin 3.x, includeConfigs và skipConfigs dùng regex khớp tên configuration; ví dụ chọn compileClasspath và runtimeClasspath, loại các config test.

**Đừng chỉ nhìn số lượng components.** Kiểm tra một số dependency quan trọng có đúng version, PURL và license hay không; xác nhận các module expected có mặt; xác nhận test dependencies không vô tình trộn vào runtime SBOM nếu policy không muốn.

## 13. Tạo một gói evidence thống nhất

Sau build, thư mục release có thể chứa:

```text
dist/
├── traceable-app-1.0.0.jar
├── bom.json
├── build-metadata.json
└── SHA256SUMS
```

Vai trò:
- traceable-app-1.0.0.jar: artifact được phát hành.
- bom.json: SBOM CycloneDX mô tả dependencies của artifact.
- build-metadata.json: commit, toolchain, workflow, thời gian và digest.
- SHA256SUMS: checksum cho artifact, SBOM và metadata.

Provenance attestation có thể được lưu ngoài thư mục này trong hệ thống attestations của CI/registry, nhưng phải tham chiếu **đúng digest của file trong dist**. Nếu lưu attestation thành file rời, cũng cần lưu/verify nó theo cơ chế signature và identity riêng.

## 14. Script Bash tạo metadata và SHA256SUMS

Tạo scripts/create-evidence.sh:

```bash
#!/usr/bin/env bash
set -euo pipefail

ARTIFACT_PATH="target/traceable-app-1.0.0.jar"
SBOM_PATH="target/bom.json"
BUILD_TOOL_NAME="Maven Wrapper"
SPRING_BOOT_VERSION="3.3.13"
SBOM_SPEC_VERSION="1.6"
DIST_DIR="dist"

test -s "$ARTIFACT_PATH"
test -s "$SBOM_PATH"

git diff --quiet
git diff --cached --quiet

mkdir -p "$DIST_DIR"

ARTIFACT_NAME="$(basename "$ARTIFACT_PATH")"
cp "$ARTIFACT_PATH" "$DIST_DIR/$ARTIFACT_NAME"
cp "$SBOM_PATH" "$DIST_DIR/bom.json"

ARTIFACT_SHA256="$(sha256sum "$DIST_DIR/$ARTIFACT_NAME" | awk '{print $1}')"
SBOM_SHA256="$(sha256sum "$DIST_DIR/bom.json" | awk '{print $1}')"

SOURCE_COMMIT="${GITHUB_SHA:-$(git rev-parse HEAD)}"
SOURCE_TAG="${GITHUB_REF_NAME:-$(git describe --tags --exact-match 2>/dev/null || true)}"
BUILD_ID="${GITHUB_RUN_ID:-local}"
BUILD_ATTEMPT="${GITHUB_RUN_ATTEMPT:-1}"
WORKFLOW_NAME="${GITHUB_WORKFLOW:-local}"
BUILD_TIMESTAMP="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
JAVA_VERSION="$(java -version 2>&1 | head -n 1)"
MAVEN_VERSION="$(./mvnw -version | head -n 1)"

BUILD_URL=""
if [[ -n "${GITHUB_SERVER_URL:-}" &&
      -n "${GITHUB_REPOSITORY:-}" &&
      -n "${GITHUB_RUN_ID:-}" ]]; then
    BUILD_URL="${GITHUB_SERVER_URL}/${GITHUB_REPOSITORY}/actions/runs/${GITHUB_RUN_ID}"
fi

jq -n \
    --arg artifact "$ARTIFACT_NAME" \
    --arg artifactSha256 "$ARTIFACT_SHA256" \
    --arg commit "$SOURCE_COMMIT" \
    --arg tag "$SOURCE_TAG" \
    --arg buildId "$BUILD_ID" \
    --arg buildAttempt "$BUILD_ATTEMPT" \
    --arg workflow "$WORKFLOW_NAME" \
    --arg buildUrl "$BUILD_URL" \
    --arg createdAt "$BUILD_TIMESTAMP" \
    --arg javaVersion "$JAVA_VERSION" \
    --arg mavenVersion "$MAVEN_VERSION" \
    --arg springBootVersion "$SPRING_BOOT_VERSION" \
    --arg buildTool "$BUILD_TOOL_NAME" \
    --arg sbomSha256 "$SBOM_SHA256" \
    --arg sbomSpecVersion "$SBOM_SPEC_VERSION" \
    '{
      schemaVersion: "1.0",
      artifact: {
        file: $artifact,
        mediaType: "application/java-archive",
        digest: {
          algorithm: "SHA-256",
          value: $artifactSha256
        }
      },
      source: {
        commit: $commit,
        tag: $tag
      },
      build: {
        id: $buildId,
        attempt: $buildAttempt,
        workflow: $workflow,
        url: $buildUrl,
        createdAt: $createdAt,
        tool: $buildTool,
        java: $javaVersion,
        maven: $mavenVersion,
        springBoot: $springBootVersion
      },
      sbom: {
        file: "bom.json",
        format: "CycloneDX JSON",
        specVersion: $sbomSpecVersion,
        digest: {
          algorithm: "SHA-256",
          value: $sbomSha256
        }
      }
    }' > "$DIST_DIR/build-metadata.json"

(
    cd "$DIST_DIR"
    sha256sum "$ARTIFACT_NAME" bom.json build-metadata.json > SHA256SUMS
    sha256sum --check SHA256SUMS
)
```

Script cần Bash, jq, sha256sum, Git và Maven Wrapper. Nó dừng nếu artifact/SBOM thiếu hoặc tracked working tree có thay đổi. Các giá trị CI như GITHUB_SHA, GITHUB_RUN_ID được dùng khi chạy trong GitHub Actions; khi chạy local, script lấy commit từ Git và đặt build ID là local.

SHA256SUMS được tạo **sau** metadata, vì vậy manifest bao phủ cả ba file. Metadata lưu digest của artifact và SBOM; manifest lưu thêm digest của metadata. Không đưa chính SHA256SUMS vào danh sách nó tự kiểm tra.

Nếu project dùng Gradle, thay ARTIFACT_PATH, SBOM_PATH, BUILD_TOOL_NAME, MAVEN_VERSION trong script bằng artifact và SBOM Gradle tương ứng. Không giữ trường Maven version cho build Gradle; ghi Gradle Wrapper version thực tế.

## 15. Kiểm tra checksum trên Windows PowerShell

Trên Windows, có thể dùng Get-FileHash để tính lại digest:

```powershell
$artifact = ".\dist\traceable-app-1.0.0.jar"
$manifest = Get-Content ".\dist\SHA256SUMS"

$line = $manifest | Where-Object {
    $_ -match "traceable-app-1.0.0.jar$"
}

$expected = ($line -split "\s+")[0].ToLowerInvariant()
$actual = (Get-FileHash $artifact -Algorithm SHA256).Hash.ToLowerInvariant()

if ($actual -ne $expected) {
    throw "SHA-256 mismatch: artifact bytes do not match the manifest"
}

"SHA-256 verification: PASS"
```

Output khi file khớp:

```text
SHA-256 verification: PASS
```

Đây là kiểm tra cho artifact JAR. Có thể lặp lại cùng cách với bom.json và build-metadata.json. Nếu manifest được lấy từ cùng một nguồn không đáng tin với artifact, phép kiểm tra chỉ phát hiện lỗi truyền tải, không chứng minh nguồn gốc; cần xác minh signature/attestation độc lập.

## 16. Reproducible builds: tạo lại cùng bytes từ cùng inputs

**Reproducible build** nghĩa là cùng source code, build environment và build instructions có thể tạo ra artifact giống nhau từng byte. Đây là nền tảng giúp người khác kiểm chứng artifact, nhưng checksum của một lần build không tự chứng minh reproducibility.

Các nguồn làm build không tái lập:
- Plugin tạo archive ghi timestamp hoặc thứ tự file không ổn định.
- Dependency dùng SNAPSHOT, dynamic version hoặc repository cho phép thay bytes.
- Maven/Gradle Wrapper hoặc JDK khác version.
- Build script đọc thời gian hiện tại, hostname, username hoặc đường dẫn workspace.
- Generated files chứa timestamp hoặc dữ liệu môi trường.
- Buildpack/base image tag mutable.
- Dependency tải về không có checksum/verification metadata.

### 16.1. Maven: output timestamp cố định theo source revision

Maven hỗ trợ project.build.outputTimestamp để các plugin archive có thể tạo output reproducible. Trong CI, lấy timestamp commit:

```bash
SOURCE_DATE_EPOCH="$(git log -1 --format=%ct)"

./mvnw -B -ntp \
    -Dproject.build.outputTimestamp="$SOURCE_DATE_EPOCH" \
    clean verify
```

Dùng cùng source commit sẽ cho cùng giá trị epoch. Cần dùng phiên bản plugin hỗ trợ reproducible archives; một property timestamp không tự sửa các plugin hoặc generated files không deterministic.

Maven có thể kiểm tra hai lần build bằng maven-artifact-plugin goal compare:

```bash
./mvnw clean install
./mvnw clean verify artifact:compare
```

Đây là kiểm tra cục bộ hữu ích, nhưng chưa chứng minh bên thứ ba build lại từ một môi trường hoàn toàn độc lập cũng nhận cùng bytes. Kiểm chứng mạnh hơn cần build trong workspace/container độc lập và so sánh SHA-256.

### 16.2. Gradle: archive order và file timestamps

Trong build.gradle Groovy:

```groovy
import org.gradle.api.tasks.bundling.AbstractArchiveTask

tasks.withType(AbstractArchiveTask).configureEach {
    preserveFileTimestamps = false
    reproducibleFileOrder = true
}
```

Trong build.gradle.kts:

```kotlin
import org.gradle.api.tasks.bundling.AbstractArchiveTask

tasks.withType<AbstractArchiveTask>().configureEach {
    isPreserveFileTimestamps = false
    isReproducibleFileOrder = true
}
```

Cấu hình này chuẩn hóa timestamp và thứ tự entry cho Gradle archive tasks. Vẫn cần pin toolchain, dependencies và các plugin tạo generated files khác.

### 16.3. Pin dependencies và verify checksums đầu vào

Với Gradle:
- Bật dependency locking cho configurations cần thiết.
- Chạy build với --write-locks để tạo/cập nhật lock state.
- Dùng dependency verification metadata để kiểm tra checksum/signature của dependency đã tải.
- Commit gradle.lockfile và gradle/verification-metadata.xml theo policy.

Ví dụ:

```groovy
dependencyLocking {
    lockAllConfigurations()
}
```

```bash
./gradlew build --write-locks
./gradlew --write-verification-metadata sha256 help
./gradlew --dependency-verification=strict clean build
```

Review file verification metadata trước khi commit. Không tự động tin mọi checksum vừa thu thập nếu nguồn dependency chưa được xác thực; bước khởi tạo metadata phải đi qua một quy trình review.

Với Maven:
- Dùng Spring Boot BOM/dependencyManagement để quản lý version đồng bộ.
- Không dùng SNAPSHOT/dynamic versions trong release.
- Pin plugin versions và Maven Wrapper.
- Có thể dùng Enforcer để phát hiện dependency convergence/version không mong muốn.
- Bảo đảm repository release áp dụng immutability và kiểm soát checksum của artifact.

## 17. Maven Wrapper và Gradle Wrapper cũng là build inputs

Một pipeline có thể pin Java nhưng vẫn không tái lập nếu mỗi máy dùng Maven/Gradle khác.

**Maven Wrapper:**
- Commit mvnw, mvnw.cmd và .mvn/wrapper/.
- Pin Maven distribution version trong maven-wrapper.properties.
- Dùng distributionSha256Sum để kiểm tra archive Maven tải về.
- Ghi ./mvnw -version vào build metadata.

**Gradle Wrapper:**
- Commit gradlew, gradlew.bat, gradle/wrapper/.
- Pin distributionUrl và distributionSha256Sum.
- Không dùng một Gradle cài sẵn tùy ý trên CI.
- Ghi ./gradlew --version vào build metadata.

JDK cũng cần được cố định: version major chưa đủ cho yêu cầu chặt; ghi vendor, patch/build và architecture nếu chúng ảnh hưởng release. Không dump credentials hoặc secret values vào metadata.

## 18. SBOM và artifact phải được liên kết với cùng một release

Một lỗi quy trình thường gặp là build JAR ở commit A, rồi generate SBOM ở một lần build khác hoặc trên dependency graph đã thay đổi. Kết quả là hai file cùng mang version 1.0.0 nhưng không mô tả cùng build.

Cách giảm rủi ro:
1. Checkout một commit SHA cụ thể.
2. Resolve dependencies một lần trong build invocation.
3. Build artifact và SBOM từ cùng workspace, cùng dependency graph.
4. Tính digest của artifact và SBOM sau khi chúng hoàn tất.
5. Ghi hai digest vào build metadata.
6. Tạo attestation gắn artifact digest và SBOM với nhau.
7. Lưu cả ba file trong cùng release bundle.

Nếu có nhiều module, phải quyết định SBOM nào mô tả artifact được phát hành. Direct SBOM cho module app và aggregate SBOM cho cả reactor có phạm vi khác nhau; chọn sai boundary có thể làm consumer tưởng các component trong test tooling hoặc module không được phân phối là runtime dependencies của sản phẩm.

## 19. GitHub Actions: tạo artifact, SBOM, checksum và attestations

Ví dụ workflow Maven cho release tag. File .github/workflows/release-evidence.yml:

```yaml
name: release-evidence

on:
  push:
    tags:
      - "v*"

permissions:
  contents: read
  id-token: write
  attestations: write

jobs:
  build:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout source
        uses: actions/checkout@v4

      - name: Set up Java
        uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: "17"
          cache: maven

      - name: Build JAR and CycloneDX SBOM
        run: |
          SOURCE_DATE_EPOCH="$(git log -1 --format=%ct)"
          ./mvnw -B -ntp \
            -Dproject.build.outputTimestamp="$SOURCE_DATE_EPOCH" \
            clean verify

      - name: Create metadata and checksum manifest
        run: bash scripts/create-evidence.sh

      - name: Attest artifact build provenance
        uses: actions/attest@v4
        with:
          subject-path: dist/traceable-app-1.0.0.jar

      - name: Attest artifact with its SBOM
        uses: actions/attest@v4
        with:
          subject-path: dist/traceable-app-1.0.0.jar
          sbom-path: dist/bom.json

      - name: Upload release evidence bundle
        uses: actions/upload-artifact@v4
        with:
          name: traceable-app-release-evidence
          path: dist/
          if-no-files-found: error
```

Các điểm cần hiểu:
- id-token: write cho phép action lấy identity OIDC dùng tạo attestation.
- attestations: write cấp quyền ghi attestation.
- Bước provenance chạy trên artifact JAR sau khi build.
- Bước SBOM attestation gắn bom.json với **cùng artifact JAR**.
- upload-artifact lưu bundle trong workflow run; bước này chưa tự tạo release trong Maven repository hoặc container registry.

Trong workflow thực tế, cần đồng bộ tên artifact/version giữa POM và workflow. Nếu version thay đổi theo tag, hãy truyền version đã kiểm tra vào build script thay vì giữ cứng tên file ở nhiều nơi. Pin GitHub Actions theo commit SHA theo security policy của tổ chức; ví dụ @v4 minh họa major version, không phải pin bất biến.

GitHub artifact attestations có yêu cầu quyền và điều kiện khả dụng tùy loại repository/plan. Với CI khác, dùng nền tảng tạo in-toto/SLSA provenance tương đương; **không coi GitHub Actions là yêu cầu bắt buộc của mô hình truy vết**.

## 20. Xác minh artifact và attestation trước khi deploy

Người nhận tải artifact cùng evidence bundle rồi thực hiện:

**Bước 1 — kiểm tra checksum:**

```bash
cd dist
sha256sum --check SHA256SUMS
```

**Bước 2 — xác minh provenance attestation:**

```bash
gh attestation verify traceable-app-1.0.0.jar \
    -R "$GITHUB_REPOSITORY"
```

**Bước 3 — xác minh SBOM attestation:**

```bash
gh attestation verify traceable-app-1.0.0.jar \
    -R "$GITHUB_REPOSITORY" \
    --predicate-type https://cyclonedx.org/bom
```

Các lệnh gh attestation verify cần GitHub CLI có hỗ trợ attestations và repository tương ứng. Kiểm tra output về signer/workflow identity, repository, source ref và subject digest theo policy. Chỉ chạy lệnh thành công chưa đủ nếu policy không kiểm tra **identity được phép**, commit/tag được phép và workflow đã được phê duyệt.

**Bước 4 — kiểm tra nội dung metadata/SBOM:**
- Artifact filename/version có khớp release không?
- SHA-256 trong metadata có khớp checksum và subject digest không?
- Commit SHA có đúng tag release không?
- Build workflow, JDK, Spring Boot và dependency versions có nằm trong policy?
- SBOM có đúng format/schema và đúng component chính không?
- Dependency/license/vulnerability findings đã được đánh giá theo tiêu chí tổ chức chưa?

Nếu bất kỳ điều kiện bắt buộc nào fail, dừng promotion/deploy và điều tra. Không chỉ sửa metadata bằng tay để làm cho checksum khớp; phải tạo lại evidence từ build được kiểm soát.

## 21. Artifact của container image cần digest riêng

Nếu pipeline phát hành cả OCI image:
- Tag như registry.example/team/traceable-app:1.0.0 là nhãn mutable.
- Registry manifest digest sha256:... xác định nội dung manifest.
- docker image inspect --format '{{.Id}}' trả local image ID/config identity, không tự động là registry manifest digest.
- Sau khi push, lấy digest từ output của registry/build tool và lưu trong metadata/provenance.
- SBOM Java dependencies và SBOM final container image có thể là hai inventory khác nhau.

Một attestation cho container image phải bind tới **image name + digest**, không chỉ tag. Khi deploy, dùng immutable digest nếu platform hỗ trợ; không build lại một image khác rồi giữ nguyên tag release.

Với Buildpacks, image SBOM nên tính đến base/run image và OS components. Nếu chỉ đính kèm bom.json do Maven tạo, hãy ghi rõ đó là SBOM của Java project dependencies, không khẳng định nó bao gồm mọi packages của final image.

## 22. Lưu trữ và phân phối evidence bundle

Đặt artifact và bằng chứng cạnh nhau:
- Maven repository: JAR/WAR, SBOM classifier hoặc sidecar, checksum/signature theo repository policy.
- GitHub/GitLab release: file artifact, bom.json, build-metadata.json, SHA256SUMS.
- OCI registry: image digest, image SBOM và attestations gắn với digest.
- Artifact repository nội bộ: giữ build logs, dependency lock/verification files và provenance cùng release record.

Nên dùng immutable version coordinates và retention phù hợp. Không overwrite 1.0.0 bằng bytes khác. Nếu cần sửa release, tạo version mới và giữ liên kết tới bản cũ để audit/rollback.

Một cấu trúc thư mục có thể được lưu trữ:

```text
release-1.0.0/
├── traceable-app-1.0.0.jar
├── bom.json
├── build-metadata.json
├── SHA256SUMS
└── attestations/
    ├── build-provenance
    └── sbom-attestation
```

Nếu nền tảng quản lý attestations ngoài filesystem, thư mục có thể chỉ lưu URI/ID tham chiếu. Điều quan trọng là người nhận có thể lấy và verify attestation theo subject digest.

## 23. Những lỗi thường gặp khi tạo checksum, metadata và SBOM

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Checksum thay đổi sau mỗi build dù code không đổi | Archive timestamps, plugin output, environment leak hoặc dependency thay đổi | Bật reproducible archive settings, pin inputs và so sánh hai builds |
| Checksum file tải về không khớp | File corruption, nhầm version hoặc file bị thay | Download lại từ nguồn tin cậy, đối chiếu digest và attestation |
| Artifact và checksum đều được sửa nhưng verify vẫn pass | Cùng lấy từ một nguồn không đáng tin | Verify chữ ký/attestation bằng trusted identity |
| bom.json không tồn tại | Plugin không chạy hoặc output path khác | Kiểm tra Maven phase/Gradle task và build logs |
| SBOM không có runtime dependency | Scope/configuration bị loại | Kiểm tra includeCompile/Runtime/Provided hoặc Gradle includeConfigs |
| SBOM có test libraries | Test scope/configuration được đưa vào | Điều chỉnh phạm vi và ghi rõ SBOM boundary |
| SBOM của WAR thiếu Servlet container | Provided scope bị loại | Đưa provided components vào SBOM theo deployment contract |
| SBOM không có OS packages | Chỉ tạo từ Java dependency graph | Tạo thêm image SBOM từ final OCI image |
| Multi-module SBOM thiếu project | Chỉ tạo Direct SBOM cho một module | Dùng aggregate khi artifact thực sự bao gồm các modules đó |
| SBOM schema không được scanner chấp nhận | Version CycloneDX/SPDX không tương thích | Ghim schema version theo consumer và validate trước phát hành |
| Metadata commit không khớp source tag | Build từ branch di động hoặc checkout sai SHA | Checkout full commit SHA và kiểm tra tag/revision |
| Metadata ghi nhầm JDK | CI dùng JDK khác local hoặc không ghi runtime thực | Lưu java -version, toolchain/vendor và build logs |
| Provenance verify fail | Attestation subject digest khác artifact hoặc signer không được tin | So sánh digest, workflow identity và source claims |
| SBOM attestation verify fail | SBOM không gắn với artifact hoặc predicate type sai | Tạo attestation với đúng artifact + SBOM path và verify predicate |
| Metadata thiếu URL build | CI không truyền run ID/URL | Map biến build platform vào metadata script |
| Artifact được rebuild khi deploy | Promotion pipeline gọi lại build | Promote chính artifact đã kiểm thử |
| Release tag bị overwrite | Registry/repository cho phép mutable version | Dùng immutable release policy và digest |
| Script tạo metadata chứa secret | Dump toàn bộ environment hoặc credentials | Chỉ chọn allowlist fields, review output trước publish |
| Checksum manifest không tìm thấy file | Chạy sha256sum --check từ sai thư mục | Chạy từ dist hoặc dùng manifest có path tương đối đúng |

## 24. Quy trình xử lý sự cố khi traceability không đầy đủ

Khi phát hiện artifact thiếu checksum/SBOM hoặc không verify được provenance:

1. Xác định chính xác artifact đang được hỏi: filename, version, repository coordinate hoặc image digest.
2. Tính lại SHA-256 từ bytes đang có; không suy luận từ tag.
3. Tìm SHA256SUMS và metadata được phát hành cùng artifact.
4. Verify attestation với subject digest và trusted builder identity.
5. Đối chiếu commit, tag, workflow run và toolchain.
6. Kiểm tra SBOM schema, main component, resolved versions và dependency scope.
7. Nếu thiếu evidence hoặc mismatch, giữ artifact ở trạng thái chưa được promotion; không tự tạo checksum mới rồi coi đó là bằng chứng build gốc.
8. Nếu phải build lại, tạo release/evidence mới và ghi rõ artifact digest mới.
9. Nếu đã deploy, xác định workload đang chạy image digest/artifact digest nào trước khi rollback.
10. Lưu log điều tra và cập nhật pipeline để lỗi tương tự bị chặn ở lần phát hành sau.

**Không sửa checksum/metadata thủ công để che một mismatch.** Nếu artifact bytes đã thay đổi, phải xem đó là một artifact khác, có digest và provenance mới.

## 25. Checklist CI trước khi phát hành

- [ ] Checkout source bằng full commit SHA và xác định release tag.
- [ ] Working tree sạch, build inputs và build scripts đã được review.
- [ ] Java, Spring Boot, Maven/Gradle Wrapper và plugin versions được pin.
- [ ] Dependencies có lock/verification hoặc version management phù hợp; release không dùng SNAPSHOT/dynamic versions ngoài policy.
- [ ] Unit/integration tests và security checks đã hoàn thành.
- [ ] Artifact JAR/WAR được tạo một lần từ đúng build invocation.
- [ ] SBOM CycloneDX/SPDX được tạo từ đúng resolved dependency graph và đúng boundary.
- [ ] Provided/runtime/test scopes được chọn có chủ đích.
- [ ] Container image có SBOM riêng nếu cần inventory OS/base image.
- [ ] Artifact SHA-256 được tính sau khi file hoàn tất.
- [ ] build-metadata.json ghi source commit, workflow ID, toolchain, thời điểm và artifact/SBOM digests.
- [ ] SHA256SUMS bao phủ artifact, SBOM và metadata.
- [ ] Manifest được verify trong CI trước khi upload.
- [ ] Provenance/attestation được tạo bởi trusted build platform, gắn đúng artifact digest.
- [ ] SBOM attestation gắn SBOM với cùng artifact subject.
- [ ] Workflow identity, source revision, builder và invocation được verify theo policy.
- [ ] Artifact/evidence được lưu trong immutable release repository.
- [ ] Promotion/deploy dùng chính artifact bytes hoặc OCI digest đã kiểm thử.
- [ ] Có retention và rollback record cho release.
- [ ] Không có secret trong metadata, checksum files hoặc build logs.

**Ghi nhớ:** checksum cho biết bytes có khớp digest hay không; metadata cho biết build khai báo những gì; SBOM liệt kê components; provenance/attestation nối artifact digest với source và builder có thể xác minh. Một pipeline hoàn chỉnh phải tạo các bằng chứng từ **cùng một build invocation**, lưu chúng cạnh release, kiểm tra chúng trước promotion và triển khai đúng bytes đã được phê duyệt.

## Tài liệu tham khảo chính thức

- [Apache Maven — Configuring for Reproducible Builds](https://maven.apache.org/guides/mini/guide-reproducible-builds.html)
- [Apache Maven — Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
- [CycloneDX Maven Plugin — Documentation](https://cyclonedx.github.io/cyclonedx-maven-plugin/)
- [CycloneDX Maven Plugin — Releases](https://github.com/CycloneDX/cyclonedx-maven-plugin/releases)
- [CycloneDX Gradle Plugin — Documentation](https://github.com/CycloneDX/cyclonedx-gradle-plugin)
- [Gradle Plugin Portal — CycloneDX Plugin](https://plugins.gradle.org/plugin/org.cyclonedx.bom)
- [CycloneDX — Specification Overview](https://cyclonedx.org/specification/overview/)
- [Ecma International — ECMA-424 CycloneDX](https://ecma-international.org/publications-and-standards/standards/ecma-424/)
- [SPDX — Specification](https://spdx.github.io/spdx-spec/)
- [SLSA v1.2 — Provenance](https://slsa.dev/spec/v1.2/provenance)
- [SLSA — Build Provenance](https://slsa.dev/spec/v1.2/build-provenance)
- [GitHub Docs — Artifact Attestations](https://docs.github.com/en/actions/concepts/security/artifact-attestations)
- [GitHub Docs — Generate Artifact Attestations](https://docs.github.com/en/actions/how-tos/secure-your-work/use-artifact-attestations/use-artifact-attestations)
- [GitHub Docs — Verify Artifact Attestations](https://docs.github.com/en/actions/how-tos/secure-your-work/use-artifact-attestations)