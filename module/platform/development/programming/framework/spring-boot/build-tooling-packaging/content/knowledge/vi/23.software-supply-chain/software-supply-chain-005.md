# Phân biệt SBOM của ứng dụng Java với SBOM của image container trong Spring Boot

## 1. Hai SBOM trả lời hai câu hỏi khác nhau

**SBOM (Software Bill of Materials)** là bản kiểm kê có cấu trúc về các thành phần phần mềm tạo nên một sản phẩm. SBOM có thể ghi package name, version, supplier, license, hash, quan hệ dependency, công cụ tạo và metadata của subject.

Với dịch vụ Spring Boot, cần phân biệt:

- **Application SBOM:** ứng dụng Java và các thư viện Java mà build đã resolve/đóng gói, chẳng hạn Spring Framework, Jackson, Tomcat và logging libraries.
- **Container image SBOM:** filesystem cuối cùng được triển khai, gồm JRE, OS packages, native libraries, CA certificates và ứng dụng Java được copy vào image.

```text
Maven dependency graph
        |
        v
 Application SBOM
 ├── release-demo (root component)
 ├── Spring Boot dependencies
 ├── Spring MVC / Jackson / Tomcat
 └── Java dependencies trực tiếp + bắc cầu
        |
        v
 executable Spring Boot JAR
        |
        +----------------------------+
                                     |
Base image (Linux + JRE + native libs)
        |                            |
        +-------------+--------------+
                      |
                      v
             final OCI image
                      |
                      v
           Container image SBOM
           ├── OS packages
           ├── JRE/runtime packages
           ├── native libraries
           ├── Java application JAR
           └── Java dependencies nếu scanner nhận diện được
```

**Application SBOM không tự động liệt kê OS packages/JRE của base image. Container image SBOM có thể phát hiện thư viện Java trong executable JAR, nhưng mức độ phát hiện phụ thuộc catalogers và khả năng đọc nested archives của công cụ.** Hai bản kiểm kê bổ sung cho nhau.

SBOM là inventory, **không phải kết quả vulnerability scan** và không phải lời chứng nhận “không có lỗ hổng”. Scanner lấy package identities/versions từ SBOM hoặc image rồi đối chiếu advisory database; kết quả còn phụ thuộc chất lượng nhận diện, dữ liệu vulnerability và ngữ cảnh sử dụng.

## 2. So sánh phạm vi

| Tiêu chí | Application SBOM | Container image SBOM |
| --- | --- | --- |
| Subject | Ứng dụng Java hoặc executable JAR | Một image OCI/Docker cụ thể |
| Đầu vào | Maven/Gradle dependency graph, source manifests, JAR/WAR | Image filesystem, manifest/layers, OS package database, archive scanners |
| Thành phần Java | Dependencies trực tiếp và transitive | Java packages scanner tìm thấy trong JAR/nested JAR |
| JRE | Thường không có nếu chỉ sinh từ Maven project model | Có thể được phát hiện trong final image |
| OS packages | Không có trong dependency graph Java thông thường | Có thể có: Debian/Ubuntu, Alpine, RPM packages |
| Native libraries | Chỉ khi được khai báo/nhận diện ở nguồn ứng dụng | Có thể có: libc, OpenSSL, zlib, JNI libraries |
| Build tools | Maven plugins/compiler cần inventory riêng | Không có nếu builder stage bị loại khỏi final stage |
| Dependency graph | Thường rõ theo Maven/Gradle model | Tùy scanner; nhiều image SBOM tập trung package inventory đã cài |
| Subject identity | GAV, JAR filename/version/hash, source commit | Image repository + manifest/index digest + platform |
| Câu hỏi bảo mật | Dependency Java nào có CVE/license issue? | JRE, OS, native packages và app components nào có trong image? |

### 2.1. Ví dụ component identities

Application SBOM có thể chứa các PURL:

```text
pkg:maven/com.example/release-demo@0.1.0
pkg:maven/org.springframework.boot/spring-boot@3.5.0
pkg:maven/org.springframework/spring-webmvc@...
pkg:maven/com.fasterxml.jackson.core/jackson-databind@...
pkg:maven/org.apache.tomcat.embed/tomcat-embed-core@...
```

Đây là **package URL minh họa**, không phải kết quả của một lần build cụ thể. Version thực tế phải lấy từ dependency resolution và output plugin.

Container image SBOM có thể bổ sung package hệ điều hành/runtime:

```text
pkg:deb/<distro>/libc6@<version>
pkg:deb/<distro>/ca-certificates@<version>
pkg:deb/<distro>/openssl@<version>
pkg:maven/org.springframework.boot/spring-boot@3.5.0
```

Các giá trị `<distro>` và `<version>` là ký hiệu minh họa. Không suy luận package/version thật chỉ từ tag base image; hãy đọc SBOM của image đã build.

## 3. Ba góc nhìn khi tạo Application SBOM

### 3.1. Project/dependency SBOM

Sinh từ Maven hoặc Gradle dependency model:
- Biết dependency trực tiếp và bắc cầu.
- Có thể thể hiện quan hệ component-to-component.
- Ghi version mà build tool thực sự resolve sau conflict resolution, constraints, dependency management và exclusions.
- Có thể phân loại compile/runtime/test/provided.
- Không tự biết JRE hay OS package của container.

CycloneDX Maven Plugin đọc Maven project/dependency graph và tạo SBOM chứa dependencies trực tiếp cùng transitive dependencies. Goal `makeBom` tạo BOM cho từng project; `makeAggregateBom` tổng hợp reactor nhiều module.

### 3.2. Binary/archive SBOM

Quét **file JAR/WAR thực tế** sau khi package:
- Xác nhận thư viện thực sự được đóng trong archive.
- Có thể tìm Maven metadata (`pom.properties`, `pom.xml`, manifest) trong JAR.
- Có thể phát hiện shaded/embedded packages tùy scanner.
- Giúp phát hiện khác biệt giữa dependency graph khai báo và nội dung archive cuối cùng.

Spring Boot executable JAR có cấu trúc nested:

```text
release-demo-0.1.0.jar
├── META-INF/MANIFEST.MF
├── org/springframework/boot/loader/...
└── BOOT-INF/
    ├── classes/
    │   └── com/example/release/ReleaseDemoApplication.class
    └── lib/
        ├── spring-boot-3.5.0.jar
        ├── spring-web-....jar
        ├── jackson-databind-....jar
        └── tomcat-embed-core-....jar
```

Scanner không đọc nested JAR có thể chỉ nhận ra executable JAR và bỏ sót package Java bên trong. Hãy chọn công cụ có Java archive cataloger hỗ trợ nested archives và kiểm tra kết quả thực tế.

### 3.3. Application SBOM cho sản phẩm phát hành

Một bản SBOM gắn với executable JAR nên ghi:
- Tên/phiên bản ứng dụng.
- GAV hoặc release version.
- Git commit/build reference.
- Dependency graph và component identities.
- Hash của JAR đã được kiểm thử.
- Tool/version tạo SBOM và schema version.
- Metadata supplier, license, timestamp và external references khi có.

**Mục tiêu là liên kết SBOM với đúng binary được phát hành**, không chỉ với một file POM có thể thay đổi sau này.

## 4. Container image SBOM bao gồm những gì?

Container image là filesystem được đóng gói thành layers, cộng metadata/config và manifest. SBOM nên phản ánh **final image thực sự được triển khai**.

### 4.1. OS packages và runtime

Tùy base image, scanner có thể nhận diện:
- Debian/Ubuntu packages từ `dpkg` database.
- Alpine packages từ `apk` database.
- RPM packages từ `rpm` database.
- Java runtime distribution/version.
- Native shared libraries, CA certificates, timezone data và packages TLS nếu có.

OS packages có advisory theo **distro**. Một bản vá có thể được backport vào package Debian mà upstream version string không tăng theo cách thông thường. Dùng scanner hiểu metadata distro thay vì chỉ so sánh version upstream.

### 4.2. Java application và dependencies

Nếu scanner đọc được Spring Boot executable JAR, nó có thể nhận diện artifact app, nested `BOOT-INF/lib/*.jar` và Maven coordinates/version của dependencies. Mức độ dựng dependency relationships phụ thuộc scanner.

Syft có Java archive cataloger tìm Maven evidence đệ quy trong Java archives, kể cả khi JAR chứa JAR khác. Với công cụ khác, kiểm tra cataloger/version/config và đối chiếu với Application SBOM.

### 4.3. Multi-stage build: builder không nằm trong final image

Ví dụ:

```dockerfile
FROM maven:3.9-eclipse-temurin-17 AS build
WORKDIR /workspace
COPY pom.xml .
COPY src ./src
RUN mvn -B -ntp clean package

FROM eclipse-temurin:17-jre AS runtime
WORKDIR /app
COPY --from=build /workspace/target/release-demo-0.1.0.jar /app/app.jar
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
```

SBOM của **final runtime image** thường không chứa Maven/JDK và các package chỉ tồn tại ở builder stage, vì stage đó không được copy vào final filesystem. Vì vậy:
- Application SBOM mô tả Java dependencies của app.
- Final image SBOM mô tả JRE/OS và app components trong runtime image.
- Builder image/build toolchain là một subject riêng nếu cần inventory.
- Build provenance ghi nhận builder/toolchain và quy trình tạo binary.

Không dùng final image SBOM để tuyên bố đã kiểm kê đầy đủ cả build environment.

## 5. Khi nào cần một SBOM, khi nào cần cả hai?

| Tình huống | SBOM nên dùng |
| --- | --- |
| Java library được publish lên Maven repository | Application/project SBOM của library |
| Spring Boot JAR được phân phối để chạy java -jar | Application SBOM + binary/archive verification |
| Spring Boot service chạy trong Docker/Kubernetes | Application SBOM + final container image SBOM |
| Muốn kiểm tra CVE trong JRE hoặc OS base image | Container image SBOM |
| Muốn phân tích dependency bắc cầu Spring/Jackson/Tomcat | Application SBOM từ Maven/Gradle, đối chiếu archive SBOM |
| Muốn đánh giá native libraries hoặc distro packages | Container image SBOM |
| Muốn kiểm kê Maven plugins/compiler/build image | Build-environment SBOM/provenance riêng |
| Một service có nhiều image AMD64/ARM64 | SBOM theo từng platform/manifest hoặc mô hình tổng hợp giữ platform relationships |
| Multi-module Maven repo có nhiều app | BOM riêng cho từng deployable app; aggregate BOM cho toàn reactor khi cần |

**Khuyến nghị cho Spring Boot chạy container:** tạo Application SBOM từ dependency graph; quét JAR đã đóng gói để xác nhận package thực tế; sau đó quét final OCI image để kiểm kê JRE/OS/native libraries và Java archives trong image.

## 6. Chuẩn định dạng: CycloneDX và SPDX không quyết định phạm vi

SBOM là khái niệm về inventory và relationships; CycloneDX và SPDX là các chuẩn định dạng để biểu diễn dữ liệu đó.

### 6.1. CycloneDX

CycloneDX có thể biểu diễn:
- BOM metadata và component được mô tả.
- Component identities, versions, suppliers, licenses, hashes.
- Dependency graph và direct/transitive relationships.
- Services, external references và composition/completeness.
- Vulnerability information, VEX và provenance-related information theo schema/version phù hợp.

CycloneDX có JSON và XML; JSON thường tiện cho automation, XML vẫn được nhiều hệ thống enterprise hỗ trợ.

**Lưu ý version:** CycloneDX specification hiện có version 1.7, nhưng tài liệu CycloneDX Maven Plugin 2.9.x liệt kê schema 1.6. Không tự đặt `schemaVersion=1.7` chỉ vì đó là phiên bản spec mới; hãy chọn version mà **plugin đã pin và consumer SBOM hỗ trợ**.

### 6.2. SPDX

SPDX là chuẩn mở quốc tế, dùng để mô tả package, file, license, copyright, relationships và thông tin supply chain. SPDX 3.0 mở rộng mô hình cho software, services, datasets, AI/ML và nhiều nội dung liên quan.

SPDX và CycloneDX đều có thể mô tả Application SBOM hoặc Container image SBOM. **Đổi JSON từ CycloneDX sang SPDX không tự thêm OS packages bị thiếu**, và đổi scanner cũng không đảm bảo scope đầy đủ nếu đầu vào không đúng.

### 6.3. Component identity

Một SBOM tốt cần định danh component ổn định:
- **PURL (Package URL):** định danh package theo ecosystem, ví dụ `pkg:maven/org.springframework.boot/spring-boot@3.5.0`.
- **CPE:** định danh sản phẩm theo quy ước Common Platform Enumeration khi phù hợp.
- **Hash:** SHA-256 của binary/file package khi scanner có thể tính hoặc lấy được.
- **Version + supplier:** hỗ trợ trường hợp package thiếu PURL/CPE.

Không chỉ so sánh `name` vì nhiều package có tên giống nhau ở các ecosystem khác nhau. Hãy dùng PURL, version, supplier, qualifiers và hash khi có.

## 7. Ví dụ thực hành: tạo Application SBOM cho Spring Boot Java 17

Ta tạo ứng dụng web nhỏ và sinh CycloneDX SBOM bằng Maven. Ví dụ dùng Java 17, Spring Boot 3.5.0, Maven 3.9.x, CycloneDX Maven Plugin 2.9.3 và CycloneDX schema 1.6 tương thích tài liệu plugin 2.9.x. Các version trên là bộ version cố định để ví dụ nhất quán; trong dự án thật, pin và cập nhật theo chính sách tổ chức.

### 7.1. Cấu trúc project

```text
release-demo/
├── pom.xml
├── Dockerfile
├── .dockerignore
└── src/
    └── main/
        └── java/
            └── com/example/release/
                └── ReleaseDemoApplication.java
```

### 7.2. File pom.xml hoàn chỉnh

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

            <plugin>
                <groupId>org.cyclonedx</groupId>
                <artifactId>cyclonedx-maven-plugin</artifactId>
                <version>2.9.3</version>
                <executions>
                    <execution>
                        <id>application-sbom</id>
                        <phase>verify</phase>
                        <goals>
                            <goal>makeBom</goal>
                        </goals>
                    </execution>
                </executions>
                <configuration>
                    <projectType>application</projectType>
                    <schemaVersion>1.6</schemaVersion>
                    <includeCompileScope>true</includeCompileScope>
                    <includeRuntimeScope>true</includeRuntimeScope>
                    <includeProvidedScope>false</includeProvidedScope>
                    <includeTestScope>false</includeTestScope>
                    <outputFormat>all</outputFormat>
                    <outputName>bom</outputName>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

**Vì sao cấu hình như vậy?**
- `makeBom` tạo BOM cho Maven project này.
- `projectType=application` mô tả đúng loại component gốc.
- `compile` và `runtime` scope được đưa vào inventory.
- `provided` được loại trong ví dụ vì đây là executable Spring Boot JAR tự mang runtime dependencies phù hợp. Nếu nền tảng triển khai thực sự cung cấp một dependency `provided`, phải ghi nhận thành phần môi trường đó theo policy thay vì mặc định bỏ qua.
- `test` scope được loại khỏi Application Runtime SBOM; nếu cần kiểm kê build/test dependencies, tạo SBOM riêng cho build environment.
- `outputFormat=all` tạo JSON và XML.
- Plugin 2.9.x tài liệu hóa CycloneDX schema 1.6; kiểm tra release/schema support trước khi nâng plugin.

### 7.3. Java application chạy được

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

### 7.4. Build và sinh Application SBOM

Từ thư mục root `release-demo`:

```bash
java -version
mvn -version
mvn -B -ntp clean verify
```

Maven chạy test/lifecycle đến `verify`, đồng thời CycloneDX plugin tạo:

```text
target/bom.json
target/bom.xml
target/release-demo-0.1.0.jar
```

Tên file theo `outputName=bom`; output directory mặc định là thư mục `target` của Maven project. File JAR là executable Spring Boot archive nhờ `spring-boot-maven-plugin`.

Kiểm tra:

```bash
jar tf target/release-demo-0.1.0.jar
```

Các entries đại diện:

```text
META-INF/MANIFEST.MF
BOOT-INF/classes/com/example/release/ReleaseDemoApplication.class
BOOT-INF/lib/spring-boot-3.5.0.jar
BOOT-INF/lib/spring-web-....jar
BOOT-INF/lib/...
org/springframework/boot/loader/...
```

Dấu `....` là ký hiệu rút gọn, không phải filename thực. Có thể đọc BOM bằng `jq`:

```bash
jq -r '.metadata.component |
       [.type, .name, (.version // "")] | @tsv' target/bom.json

jq -r '.components[]? |
       [.type, .name, (.version // ""), (.purl // "")] | @tsv' \
       target/bom.json
```

Nếu consumer chỉ cần một định dạng, có thể cấu hình `outputFormat` tương ứng thay vì `all`. Đừng chỉnh file JSON thủ công rồi gọi đó là SBOM mới; mọi thay đổi phải được tái tạo từ build inputs hoặc toolchain có thể truy vết.

### 7.5. Kiểm tra dependency graph và scope

```bash
mvn -B -ntp dependency:tree -Dscope=runtime
```

Lệnh giúp đối chiếu dependency graph Maven với components trong BOM. Nếu component không xuất hiện như mong đợi, kiểm tra:
- Maven profile đang active.
- Dependency scope và exclusions.
- Dependency management/version mediation.
- `optional` và dependency transitive.
- Cấu hình include/exclude scope của CycloneDX.
- Plugin version và output schema.
- Dependency được Spring Boot plugin đưa vào hay loại khỏi executable archive.

**SBOM từ Maven model và SBOM quét JAR không nhất thiết giống tuyệt đối.** Một bên mô tả resolved project dependencies theo scope; bên kia mô tả packages mà scanner tìm thấy trong binary thực tế.

### 7.6. Kiểm tra SBOM cho multi-module Maven

Trong một reactor nhiều module:
- `makeBom` tạo BOM theo từng Maven project.
- `makeAggregateBom` tạo aggregate BOM tại root, tập hợp các modules được đưa vào build.
- Nên tạo BOM riêng cho mỗi deployable application để biết đúng dependency set của service.
- Aggregate BOM hữu ích cho inventory toàn repository, nhưng có thể chứa các module/test tools không nằm trong một executable JAR cụ thể.

Có thể gọi goal aggregate từ root:

```bash
mvn -B -ntp org.cyclonedx:cyclonedx-maven-plugin:2.9.3:makeAggregateBom
```

Dùng goal và cấu hình phù hợp với phiên bản plugin đã pin; kiểm tra output của từng module và aggregate thay vì chỉ kiểm tra một file tên `bom.json`.

## 8. Tạo final container image từ đúng JAR đã build

Để tránh job Docker tự build lại source rồi tạo một binary khác với binary đã QA, ví dụ này **build JAR trước**, sau đó Dockerfile chỉ copy JAR đã có.

**`Dockerfile`:**

```dockerfile
FROM eclipse-temurin:17-jre
WORKDIR /app

COPY target/release-demo-0.1.0.jar /app/app.jar

USER 10001
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
```

**`.dockerignore`:**

```dockerignore
.git
.idea
.vscode
.env
*.pem
*.key
*.p12
```

Không ignore `target/` vì Dockerfile cần file JAR trong thư mục đó. Base tag `17-jre` giúp demo dễ đọc; release production nên kiểm soát base image bằng digest/policy đã được tổ chức phê duyệt, cập nhật bản vá có kiểm thử.

Build image:

```bash
docker build -t release-demo:0.1.0 .
```

Chạy:

```bash
docker run --rm -p 127.0.0.1:8080:8080 release-demo:0.1.0
```

Terminal khác:

```bash
curl -fsS http://localhost:8080/ready
curl -fsS http://localhost:8080/version
```

Response body lần lượt:

```text
ready
release-demo:0.1.0
```

Dừng container bằng Ctrl+C. Nếu port 8080 bận, đổi port host, ví dụ `-p 127.0.0.1:9090:8080`.

**Điểm quan trọng:** final image chứa JRE/base filesystem và JAR đã được build; nó không chứa Maven compiler/toolchain. Vì thế container image SBOM phải thêm inventory của runtime base image mà Application SBOM không biết đến.

## 9. Sinh SBOM từ executable JAR và từ final image

### 9.1. Quét archive JAR

Dùng Syft để quét executable archive:

```bash
syft target/release-demo-0.1.0.jar \
  -o cyclonedx-json=target/application-archive.cdx.json
```

Syft Java archive cataloger tìm Maven evidence trong JAR/WAR/EAR và có thể duyệt nested archives đệ quy. Kết quả này là **binary/archive SBOM** để xác minh package thực sự có trong file đã build. Scanner cần được cập nhật và cấu hình phù hợp; vẫn phải kiểm tra component list và completeness.

### 9.2. Quét final container image

Sau khi `docker build` thành công:

```bash
syft release-demo:0.1.0 \
  -o cyclonedx-json=target/container-image.cdx.json
```

Syft image catalogers kiểm kê các packages mà nó phát hiện trong final image. Tùy base image, kết quả có thể có OS packages và runtime packages cùng các Java packages nhận diện được từ nested archive.

Có thể dùng Docker Scout:

```bash
docker scout sbom \
  --format cyclonedx \
  --output target/container-scout.cdx.json \
  local://release-demo:0.1.0
```

`local://` yêu cầu dùng image trong local image store, không tra registry. Docker Scout SBOM hỗ trợ image, OCI layout, archive và local directory/file; output có thể ở dạng JSON, SPDX hoặc CycloneDX.

**Không mặc định output Syft và Docker Scout giống byte-for-byte.** Hai tool có catalogers, metadata, package identification, graph modeling và phiên bản khác nhau. Hãy kiểm tra tool/version, component set và source evidence.

### 9.3. Kiểm tra image inventory

Xem một số PURLs trong SBOM image:

```bash
jq -r '.components[]?.purl // empty' \
  target/container-image.cdx.json | sort -u
```

Để kiểm tra OS packages, tìm PURL ecosystem như `pkg:deb/...`, `pkg:apk/...` hoặc `pkg:rpm/...` tùy distro. Để kiểm tra Java packages, tìm `pkg:maven/...`.

Không có package `pkg:deb` trong SBOM **không tự động chứng minh image không có OS components**: base có thể dùng distro khác, database package manager bị thiếu hoặc scanner không nhận diện được. Xem metadata image và catalogers đã chạy.

### 9.4. So sánh ba bản kiểm kê

| File | Nó chứng minh điều gì? | Điều nó không chứng minh |
| --- | --- | --- |
| `target/bom.json` | Maven project/dependency graph theo scope/config đã chọn | JRE/OS packages trong container |
| `target/application-archive.cdx.json` | Java packages scanner tìm được trong JAR thực tế | OS/JRE của image |
| `target/container-image.cdx.json` | Packages scanner nhận diện trong final image | Mọi build tools đã dùng ở builder stage hoặc mọi dependency chưa được phát hiện |

Nếu Application SBOM có Spring/Tomcat/Jackson nhưng image SBOM thiếu chúng, cần kiểm tra Java archive cataloger và nested JAR support trước khi kết luận image không chứa dependencies. Ngược lại, nếu image SBOM có JRE/OS packages mà Application SBOM không có, đó thường là khác biệt phạm vi hợp lý.

## 10. Đọc quan hệ và completeness, không chỉ đếm số component

Một SBOM hữu ích nên có:
- Root component đại diện sản phẩm được mô tả.
- Component identities rõ (PURL, version, supplier).
- Dependency relationships nếu tool hỗ trợ.
- Metadata về tool, thời gian, serial number hoặc BOM reference.
- Hashes khi có thể tính/nhận diện.
- External references và provenance/source reference.
- Composition/completeness nếu format/tool hỗ trợ.

### 10.1. BOM root và component list

Application BOM thường có root component như `com.example:release-demo:0.1.0`, sau đó liệt kê Maven dependencies. Container image BOM có thể mô tả subject là image hoặc component gốc của image, cùng các package nằm trong filesystem.

Không chỉ kiểm tra số dòng:
- 100 components không tự động tốt hơn 60 components.
- Một SBOM có nhiều duplicate packages hoặc package identities không đầy đủ có thể khó dùng hơn.
- Một BOM thiếu quan hệ dependency sẽ hạn chế phân tích tác động của một library.
- Một BOM không có hash/provenance sẽ khó chứng minh đúng binary nào được mô tả.

### 10.2. Dùng PURL để đối chiếu

Ví dụ một Maven package có PURL:

```text
pkg:maven/com.fasterxml.jackson.core/jackson-databind@2.x.y
```

Image SBOM có thể biểu diễn cùng dependency bằng PURL Maven đó, trong khi base image có các PURL OS:

```text
pkg:deb/<distro>/libc6@<version>
pkg:deb/<distro>/ca-certificates@<version>
```

Khi so sánh:
1. Chuẩn hóa PURL, version, qualifiers và namespace.
2. So sánh hash nếu cả hai công cụ cung cấp hash tương thích.
3. Phân biệt package duplicate do nhiều đường dẫn/archive copies.
4. Kiểm tra version conflict và shaded dependencies.
5. Giữ nguyên quan hệ dependency của từng BOM.
6. Không gộp component bằng tên file JAR đơn thuần.

### 10.3. Không ghép hai JSON bằng cách nối mảng

Nếu muốn tạo **combined/system SBOM** từ Application BOM và Image BOM:
- Xác định image là deployment artifact chứa application component nào.
- Giữ lại provenance/source của từng component.
- Deduplicate theo package identity và version, không chỉ tên.
- Duy trì dependency relationships và BOM reference hợp lệ.
- Đánh dấu rõ completeness của từng nguồn.
- Dùng tool merge/compose hỗ trợ format/schema; validate kết quả bằng schema validator.

Thông thường, lưu **hai SBOM riêng** cùng release record sẽ rõ ràng hơn. Chỉ tạo combined BOM khi consumer có use case thực sự và công cụ có thể giữ relationships đúng.

## 11. Build-time dependencies khác runtime dependencies

Một Java project có nhiều loại dependencies:
- **Compile/runtime libraries:** có thể đi vào executable JAR.
- **Test libraries:** JUnit, Mockito, Testcontainers; thường không được đóng trong production JAR.
- **Build plugins:** Maven Compiler, Surefire, CycloneDX plugin, Spring Boot Maven Plugin.
- **Build runtime:** JDK, Maven distribution, OS packages của builder container.
- **Application runtime:** JRE, base OS, native libraries và app dependencies.

Một Application Runtime SBOM thường không nên trộn tất cả test/build tools vào cùng package set rồi gọi đó là inventory của runtime app. Tuy nhiên, tổ chức có thể yêu cầu **build SBOM** riêng để kiểm kê compiler/plugins/build images.

Ví dụ Maven scopes:

| Scope | Ý nghĩa phổ biến | Đưa vào runtime Application SBOM? |
| --- | --- | --- |
| `compile` | Có trên compile và runtime classpath | Thường có |
| `runtime` | Cần lúc chạy, không cần compile | Có |
| `provided` | Nền tảng/container dự kiến cung cấp | Tùy deployment; mẫu trên loại ra |
| `test` | Chỉ phục vụ test | Thường loại khỏi runtime BOM |
| `system` | Dependency gắn với path local | Cần review thủ công; dễ thiếu portability |

Không dựa scope đơn lẻ để khẳng định file có nằm trong Boot JAR; xác minh với `jar tf` và binary/archive scanner.

## 12. Multi-module Maven: BOM riêng cho app và BOM aggregate cho repository

Một dự án lớn có thể:

```text
reactor-root/
├── pom.xml
├── core-library/
├── service-api/
├── reporting/
├── boot-app/
└── integration-tests/
```

Root aggregate BOM có thể liệt kê nhiều module, bao gồm library và test modules. Nhưng một container image chỉ đóng gói các module mà `boot-app` phụ thuộc và những gì được copy vào final image.

**Hai mục tiêu khác nhau:**
- **Aggregate reactor BOM:** inventory toàn bộ Maven reactor.
- **Deployable application BOM:** inventory dependency set của đúng module/application được release.

Khi publish image của `boot-app`, hãy giữ SBOM module app gắn với image đó. Không dùng root aggregate BOM làm bằng chứng duy nhất cho nội dung final image nếu aggregate còn có những modules không được đóng gói.

Nếu dùng CycloneDX Gradle plugin, plugin 3.x có thể sinh direct SBOM cho từng project và aggregate SBOM qua task `cyclonedxBom`; `cyclonedxDirectBom` tạo BOM riêng cho project. Cấu hình task và schema phải theo đúng release plugin tương thích Gradle Wrapper.

## 13. SBOM và vulnerability scan là hai bước liên quan nhưng khác nhau

SBOM trả lời **“có những components nào?”**. Vulnerability scanner trả lời **“các components đó khớp advisory/vulnerability nào?”**.

Luồng:

```text
Application SBOM / Image SBOM
            |
            v
    Package identification
    (PURL, CPE, version, distro)
            |
            v
   Vulnerability/advisory database
            |
            v
      Matching + policy
            |
            +--> CVE findings
            +--> affected/fixed versions
            +--> severity / exploitability context
            +--> false-positive review / VEX
            |
            v
       CI release gate
```

Một SBOM đầy đủ vẫn có thể chứa nhiều CVE. Một scanner không báo CVE có thể do:
- Component không được nhận diện.
- Advisory database chưa cập nhật hoặc không có mapping.
- Version/distro backport được xử lý khác.
- CVE chưa công bố hoặc chưa có dữ liệu.
- Scanner thiếu cataloger cho một package ecosystem.
- Dependency không nằm trong scope mà tool quét.

Vì vậy:
- Sinh SBOM và lưu đúng artifact subject.
- Quét Application SBOM để xem Java dependencies.
- Quét final image để xem JRE/OS/native components.
- Review findings theo policy, không chỉ dựa số lượng CVE.
- Dùng VEX hoặc security exception có lý do khi tổ chức hỗ trợ; không xóa package khỏi SBOM chỉ để làm sạch báo cáo.

## 14. CI/CD: tạo và gắn hai SBOM với đúng release

Một pipeline tham khảo:

```text
Git commit
   |
   v
Maven clean verify
   |
   +--> executable app.jar
   +--> application bom.json / bom.xml
   +--> test reports
   |
   v
Archive scan app.jar
   |
   +--> application-archive.cdx.json
   |
   v
Build OCI image từ đúng app.jar đã kiểm
   |
   +--> image manifest / layers / digest
   |
   v
Scan final image
   |
   +--> container-image.cdx.json
   |
   v
Vulnerability + license policy gates
   |
   v
Publish / sign / attach provenance
   |
   v
Deploy bằng image digest đã được duyệt
```

### 14.1. Bash pipeline mẫu

Sau khi cài Maven, Docker, Syft và có project từ mục 7:

```bash
set -eu

mvn -B -ntp clean verify

syft target/release-demo-0.1.0.jar \
  -o cyclonedx-json=target/application-archive.cdx.json

docker build -t release-demo:0.1.0 .

syft release-demo:0.1.0 \
  -o cyclonedx-json=target/container-image.cdx.json

sha256sum \
  target/release-demo-0.1.0.jar \
  target/bom.json \
  target/application-archive.cdx.json \
  target/container-image.cdx.json
```

Pipeline này minh họa thứ tự công việc, không bao gồm registry credentials, SBOM signing hay security gate của tổ chức. Các SHA-256 thực tế sẽ phụ thuộc binary và tool outputs; không có checksum cố định để copy từ tài liệu.

### 14.2. Build once, promote the same bytes

Để tránh tình huống QA kiểm thử một JAR nhưng image đóng gói một JAR khác:
1. Build executable JAR một lần.
2. Sinh Application SBOM từ resolved dependency graph.
3. Quét archive JAR và tính checksum.
4. Chạy tests/smoke tests trên đúng JAR đó.
5. Build image bằng `COPY` từ đúng file JAR đã kiểm.
6. Sinh Container image SBOM sau khi image được tạo.
7. Ghi image digest và JAR SHA vào release record.
8. Publish/promote cùng binary/image đã kiểm thử.

Nếu job Docker tự chạy lại Maven build, cần chứng minh JAR mới giống JAR đã QA bằng checksum/reproducible build evidence; chỉ dùng chung version string chưa đủ.

### 14.3. Lưu SBOM ở đâu?

Các lựa chọn phổ biến:
- CI artifact store cho reports gắn workflow run, build ID và commit.
- Maven repository attach Application SBOM với classifier phù hợp khi publish Java artifact.
- OCI registry/attestation store để gắn Container image SBOM với image digest.
- Release archive hoặc evidence store dài hạn cho audit/rollback.

Không chỉ lưu SBOM với tên chung `bom.json` mà thiếu thông tin subject. Cần biết BOM mô tả **JAR nào hoặc image digest nào**.

## 15. Gắn metadata và provenance để truy vết

Một release record tốt nên liên kết:

| Metadata | Ý nghĩa |
| --- | --- |
| Git commit | Source revision đã build |
| Maven GAV | Định danh Java component |
| JAR SHA-256 | Bytes của executable JAR |
| Application SBOM serial/version | Bản inventory dependency của ứng dụng |
| Archive SBOM tool/version | Công cụ quét binary JAR |
| OCI repository/tag | Image reference dễ đọc |
| OCI manifest/index digest | Định danh chính xác image đã phát hành |
| Platform | `linux/amd64`, `linux/arm64`... |
| Container SBOM | Inventory của final image cụ thể |
| Base image digest | JRE/OS base thực sự đã dùng |
| Builder/toolchain | Maven/JDK/plugins/build image |
| Test/security evidence | Kết quả kiểm thử, scan, approval và policy |

SBOM không tự chứng minh ai tạo ra binary. Để tăng độ tin cậy:
- Ký SBOM/attestation theo supply-chain policy.
- Gắn provenance với source commit và build identity.
- Lưu JAR hash và image digest.
- Hạn chế quyền publish và chỉnh sửa release artifacts.
- Không tái sử dụng SBOM cũ sau khi thay JAR/base image/dependency.
- Bảo đảm người nhận có thể xác minh chữ ký/attestation từ trust root được duyệt.

## 16. Multi-platform images: SBOM cần xét theo architecture

Một image index có thể trỏ tới nhiều manifests:

```text
release-demo:0.1.0
       |
       v
OCI image index
       |
       +--> linux/amd64 manifest
       |      ├── AMD64 JRE
       |      ├── AMD64 OS layers
       |      └── app JAR
       |
       +--> linux/arm64 manifest
              ├── ARM64 JRE
              ├── ARM64 OS layers
              └── app JAR
```

Application JAR Java thuần có thể giống nhau ở cả hai platform, nhưng OS/JRE/native components và layer digests có thể khác.

Vì vậy:
- Một Application SBOM có thể dùng chung cho binary JAR nếu binary thực sự giống nhau.
- Container image SBOM nên gắn với đúng child manifest/platform hoặc aggregate index có relationships rõ.
- Quét từng platform được phát hành, không chỉ quét local image mặc định của laptop.
- Dùng OCI index digest làm identity chung, đồng thời giữ child manifest digest và platform-specific scan evidence.
- Nếu app chứa JNI/native-image, Application binary/dependencies có thể cũng khác theo architecture.

Với Docker Scout, có option `--platform` để chọn platform khi phân tích image. Xem manifest/index bằng Buildx trước, sau đó scan đúng variants mà production hỗ trợ.

## 17. Lỗi thường gặp và cách khắc phục

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Application SBOM thiếu dependency đang dùng | Scope/config/profile/exclusion chưa đúng | Xem `mvn dependency:tree`, effective POM và CycloneDX scope config |
| Application SBOM có test libraries | `includeTestScope=true` hoặc plugin cấu hình không đúng | Tách build/test BOM; đặt test scope false cho runtime BOM |
| Maven BOM có `provided` nhưng JAR không có | Project model include provided scope, trong khi app archive không đóng dependency đó | Chọn scope policy phù hợp; đối chiếu `jar tf` |
| Maven BOM không có JRE | Project dependency graph không chứa runtime base | Quét final container image |
| Image SBOM thiếu Spring/Tomcat | Scanner không đọc nested Boot JAR hoặc cataloger không chạy | Dùng archive-aware scanner, xác minh Syft Java cataloger và scan JAR riêng |
| Image SBOM chỉ có OS packages | Tool chỉ dùng OS package database hoặc không nhận dạng Java archive | Thêm Java archive cataloger, quét executable JAR và đối chiếu |
| Image SBOM thiếu OS packages | Distro/minimal image không có package database hoặc scanner không hỗ trợ | Xem base image, cataloger support và scan binary/filesystem |
| Image SBOM vẫn có Maven/JDK | Build tools được copy vào final stage hoặc image scan nhầm builder | Inspect final image layers và Dockerfile stage |
| Container SBOM khác sau khi chỉ đổi base image | JRE/OS packages hoặc base digest đã đổi | Sinh lại image SBOM và scan lại |
| Container SBOM cũ gắn với tag mới | Tag mutable nhưng BOM không được regenerate | Gắn BOM với manifest digest, không chỉ tag |
| CVE scan báo khác giữa hai tool | Advisory data, PURL/CPE matching và distro logic khác nhau | Kiểm tra package identity, scanner version, advisory source |
| SBOM không có dependency relationships | Scanner chỉ tạo flat inventory hoặc không có graph evidence | Dùng Maven/Gradle dependency SBOM cho graph |
| Aggregate BOM chứa test module | Root reactor bao gồm test/support modules | Tạo BOM riêng cho deployable application |
| Hai BOM trùng nhiều component | Cùng Java libraries xuất hiện ở app và image | So sánh PURL/version/hash; giữ source và subject riêng |
| SBOM không khớp binary phát hành | Build lại ở job khác hoặc artifact bị thay sau QA | So JAR hash, commit, build ID và provenance |
| Scan JAR không tìm thấy nested dependencies | Scanner/cataloger chưa hỗ trợ archive format hoặc bị tắt | Kiểm tra Java cataloger và scan config, dùng tool có nested archive support |
| Multiarch image chỉ có một SBOM | Chỉ scan platform mặc định | Scan mỗi platform/child manifest được release |
| Plugin báo schema không hỗ trợ | Schema version mới hơn plugin release | Dùng schema version được plugin hỗ trợ hoặc nâng plugin |
| BOM JSON parse được nhưng consumer từ chối | Schema/media type/version hoặc required metadata sai | Validate bằng validator tương thích schema |
| Vulnerability không tìm thấy trong SBOM | Package chưa được catalog, không có PURL/CPE hoặc chưa có advisory | Xem file evidence/cataloger, package metadata và scanner coverage |

### 17.1. Quy trình debug tuần tự

1. Xác nhận đúng subject: Maven project, executable JAR hay final image.
2. Kiểm tra Git commit, GAV, JAR SHA-256 và image digest.
3. Xem `mvn dependency:tree` để xác nhận dependency resolution.
4. Xem `jar tf` để xác nhận các nested libraries thực sự đóng trong Boot JAR.
5. Sinh Application SBOM từ Maven/Gradle.
6. Sinh archive SBOM từ JAR và so sánh component identities.
7. Quét final image, xem OS/JRE/native packages và Java catalogers.
8. Kiểm tra final image là đúng Dockerfile stage/platform.
9. So PURL/version/hash, không chỉ so tên package.
10. Xem SBOM tool version, schema version, scan configuration và metadata.
11. Chạy vulnerability scan riêng; xem advisory source, distro mapping và policy.
12. Gắn kết quả với đúng JAR/image digest, không ghi đè SBOM của release cũ.

## 18. Những hiểu lầm cần tránh

1. **“Application SBOM đã đủ cho container.”** Không: nó thường không chứa OS/JRE base image.
2. **“Container SBOM luôn có toàn bộ Java dependencies.”** Không: cần scanner hỗ trợ nested JAR/catalogers thích hợp.
3. **“Hai SBOM phải giống hệt.”** Không: chúng mô tả các subjects và scopes khác nhau.
4. **“SBOM chính là vulnerability report.”** Không: inventory và advisory matching là hai bước.
5. **“Maven plugin quét mọi thứ trong final image.”** Không: plugin đọc Maven project/dependency model.
6. **“Image scanner hiểu mọi dependency graph như Maven.”** Không: graph completeness phụ thuộc scanner evidence.
7. **“Một image SBOM bao gồm Maven/Gradle builder.”** Không nếu builder stage không nằm trong final image.
8. **“Một JAR checksum là image digest.”** Không: hash của file JAR khác manifest/index digest OCI.
9. **“SPDX hay CycloneDX quyết định SBOM là application hay container.”** Không: đó là format; scope do subject và nguồn dữ liệu quyết định.
10. **“Có SBOM nghĩa là không có CVE.”** Không: SBOM có thể liệt kê components đang có lỗ hổng.
11. **“CVE severity cao nghĩa là ứng dụng chắc chắn exploitable.”** Không: cần xem affected package, configuration, reachability và VEX/context.
12. **“Một SBOM cho tag luôn đúng mãi.”** Không: tag có thể thay image; gắn SBOM với digest.
13. **“Quét image local một kiến trúc đủ cho multiarch.”** Không: cần kiểm tra từng platform manifest.
14. **“Gộp hai file BOM bằng cách nối components là xong.”** Không: cần xử lý duplicate identities, BOM references và dependency relationships.
15. **“Application BOM mặc định chỉ có runtime.”** Không: phải kiểm tra scope config; Maven plugin có thể bao gồm compile/provided/system theo cấu hình.
16. **“Build tool dependencies là runtime application dependencies.”** Không: nên phân biệt build SBOM với runtime SBOM.
17. **“Tên `bom.json` cho biết BOM mô tả gì.”** Không: phải đọc metadata/subject và release linkage.
18. **“Scanner không tìm thấy package nghĩa là package không tồn tại.”** Không: có thể do cataloger, archive format, package database hoặc coverage limitation.

## 19. Checklist cho release Spring Boot

### Application SBOM

- [ ] Chọn đúng module/deployable application.
- [ ] Dùng dependency graph đã resolve từ Maven/Gradle.
- [ ] Đặt project/component type là application khi phù hợp.
- [ ] Xác định rõ compile/runtime/provided/test/system scopes.
- [ ] Xác nhận dependency versions và exclusions bằng dependency tree.
- [ ] Chọn CycloneDX/SPDX schema mà producer và consumer cùng hỗ trợ.
- [ ] Sinh SBOM sau khi build đã xác định artifact version.
- [ ] Đối chiếu với executable JAR và archive scanner.
- [ ] Lưu GAV, Git commit, JAR SHA-256 và SBOM tool/version.

### Container image SBOM

- [ ] Quét **final image**, không chỉ source directory hoặc builder stage.
- [ ] Kiểm kê OS/JRE/native packages của base image.
- [ ] Bảo đảm Java archive cataloger đọc nested Boot JAR khi cần.
- [ ] Xác nhận image scanner nhận đúng image digest.
- [ ] Kiểm tra base image digest, runtime version và platform.
- [ ] Quét từng architecture được phát hành.
- [ ] Lưu image SBOM gắn với manifest/index digest.
- [ ] Quét vulnerability/license policy trên final image.
- [ ] Không tái sử dụng SBOM cũ sau khi thay image/JAR/base.

### Supply chain và CI

- [ ] Build/test một JAR, promote đúng bytes sang image.
- [ ] Lưu Application SBOM, archive SBOM và Container SBOM riêng.
- [ ] Ghi liên kết Git commit ↔ JAR SHA ↔ image digest ↔ SBOM.
- [ ] Ký/attest SBOM theo policy khi cần.
- [ ] Lưu provenance/build toolchain riêng khi yêu cầu.
- [ ] Có retention đủ lâu cho release, rollback và audit.
- [ ] Cập nhật plugin/scanner/advisory database có kiểm soát.
- [ ] Validate schema và metadata trước khi publish.
- [ ] Không coi SBOM generation thành security gate duy nhất.

## 20. Tài liệu chính thức

- CycloneDX – [Specification Overview](https://cyclonedx.org/specification/overview/): component model, metadata, dependencies, composition và vulnerability representation.
- CycloneDX Maven Plugin – [Plugin Documentation](https://cyclonedx.github.io/cyclonedx-maven-plugin/): `makeBom`, `makeAggregateBom`, scope configuration, schema và artifact attachment.
- CycloneDX Maven Plugin – [makeBom Goal](https://cyclonedx.github.io/cyclonedx-maven-plugin/makeBom-mojo.html): compile/runtime/provided/test scopes và output configuration.
- CycloneDX Maven Plugin – [makeAggregateBom Goal](https://cyclonedx.github.io/cyclonedx-maven-plugin/makeAggregateBom-mojo.html): aggregate reactor BOM và module outputs.
- CycloneDX – [ECMA-424 Standard](https://ecma-international.org/publications-and-standards/standards/ecma-424/): tiêu chuẩn CycloneDX BOM.
- SPDX – [Specifications](https://spdx.dev/use/specifications/): SPDX 3.0 và các phiên bản trước.
- Anchore Syft – [Java Package Analysis](https://oss.anchore.com/docs/capabilities/java/): Java archive cataloger, nested JAR scanning và package metadata.
- Anchore Syft – [Package Catalogers](https://oss.anchore.com/docs/guides/sbom/catalogers/): khác biệt catalogers cho image và source directory.
- Anchore Syft – [Getting Started](https://oss.anchore.com/docs/guides/sbom/): tạo SBOM từ container images, filesystems và archives.
- Docker – [docker scout sbom](https://docs.docker.com/reference/cli/docker/scout/sbom/): quét image/OCI archive và xuất JSON, SPDX, CycloneDX.
- Docker – [Docker Scout](https://docs.docker.com/scout/): image inventory và vulnerability analysis.
- Spring Boot 3.5 – [Maven Plugin Packaging](https://docs.spring.io/spring-boot/3.5/maven-plugin/packaging.html): executable JAR và `repackage`.
- Spring Boot 3.5 – [Executable Jar Nested Jars](https://docs.spring.io/spring-boot/3.5/specification/executable-jar/nested-jars.html): `BOOT-INF/classes`, `BOOT-INF/lib` và launcher layout.

**Ghi nhớ:** Application SBOM cho biết **những package Java cấu thành ứng dụng theo dependency/build model**; Container image SBOM cho biết **những package có mặt trong filesystem image cuối cùng**, bao gồm runtime và OS packages. Với Spring Boot, hãy tạo BOM từ Maven/Gradle, xác minh executable JAR, rồi quét final image. Liên kết cả hai bằng Git commit, JAR checksum và OCI digest để biết chính xác thành phần nào thuộc ứng dụng, thành phần nào đến từ base image, và bản SBOM đang mô tả đúng sản phẩm nào.