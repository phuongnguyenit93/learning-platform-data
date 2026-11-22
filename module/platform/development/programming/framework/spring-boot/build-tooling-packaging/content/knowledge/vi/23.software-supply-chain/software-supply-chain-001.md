# Kiểm soát nguồn tải plugin, dependency và bản phân phối Wrapper

Một ứng dụng Spring Boot có thể build thành công nhưng vẫn không đáng tin nếu **Maven/Gradle, plugin, dependency hoặc chính chương trình Wrapper** được tải từ nguồn không kiểm soát. Maven plugin và Gradle plugin là code có thể thực thi trong build process; dependency đi vào classpath ứng dụng; Wrapper là chương trình bootstrap tải và chạy build tool trước khi các kiểm tra trong project bắt đầu.

Bài học thuộc nhóm **Chuỗi cung ứng** và tập trung vào năm câu hỏi:

- Build được phép tải artifact từ **repository nào**?
- Plugin repositories và project dependency repositories có **được kiểm soát riêng** không?
- Maven/Gradle Wrapper tải đúng **bản phân phối đã pin và kiểm tra checksum** không?
- Dependency graph có **version ổn định**, checksum/signature đã xác minh không?
- CI có chạy cùng cấu hình đã review, không dùng cache/credentials ngoài trust boundary không?

Ví dụ dùng **Java 17, Spring Boot 3.3.13, Maven 3.9.9 và Gradle 8.10.2** để minh họa. Đây là bộ phiên bản cố định trong bài, không phải đề xuất version mới nhất. Các hostname `repo.corp.example` chỉ là ví dụ, không phải registry/repository đang hoạt động.

## 1. Bản đồ nguồn cung cấp code cho build

Không chỉ có dependency khai báo trong `pom.xml`/`build.gradle` mới có thể ảnh hưởng sản phẩm. Một build điển hình sử dụng:

```text
Git checkout
    |
    v
Wrapper scripts + Wrapper JAR
    |
    v
Maven / Gradle distribution
    |
    v
Settings / extensions / init scripts
    |
    +------------------------+
    |                        |
    v                        v
Build plugins           Project dependencies
    |                        |
    v                        v
Plugin transitive        Direct + transitive
dependencies             libraries / metadata
    |                        |
    +-----------+------------+
                |
                v
        Compile / test / package
                |
                v
       Spring Boot executable JAR
                |
                v
          Release artifact
```

| Thành phần | Ví dụ | Lý do cần kiểm soát |
| --- | --- | --- |
| Wrapper script | `mvnw`, `gradlew` | Chạy trước build và có thể tải/chạy tool khác |
| Wrapper binary | `maven-wrapper.jar`, `gradle-wrapper.jar` | Là executable code được commit vào repository |
| Build distribution | Maven ZIP, Gradle ZIP | Cung cấp chính chương trình build |
| Repository settings | `settings.xml`, `settings.gradle` | Chọn nguồn tải, credentials, content routing |
| Build extensions | `.mvn/extensions.xml`, settings plugins | Có thể thay đổi build trước khi task thông thường chạy |
| Build plugins | Spring Boot plugin, compiler/test plugins | Chạy code trong build process |
| Plugin dependencies | Các thư viện mà plugin cần | Có thể thực thi cùng quyền với build |
| Project dependencies | Spring Web, JUnit | Đi vào compile/test/runtime classpath |
| Transitive dependencies | Các thư viện được dependency kéo theo | Vẫn tham gia sản phẩm dù không khai báo trực tiếp |
| Metadata | POM, Gradle Module Metadata, Ivy descriptor | Quyết định dependency graph và version bắc cầu |

**Wrapper cũng là một mắt xích supply chain.** Nếu Wrapper JAR hoặc script bị thay, kiểm tra dependency trong Maven/Gradle chưa kịp chạy đã có thể bị vượt qua.

## 2. Ba lớp bảo vệ cần phối hợp

| Lớp | Câu hỏi | Cơ chế |
| --- | --- | --- |
| Source control | Artifact được phép tải từ đâu? | Repository manager, mirror, allowlist, content filters |
| Version control | Build chọn phiên bản nào? | Pin plugin/dependency versions, BOM, dependency lock |
| Artifact verification | Bytes tải về có đúng artifact đã tin? | SHA-256, chữ ký, provenance, Wrapper checksum |

Một repository manager giúp định tuyến và kiểm soát artifact, nhưng không tự chứng minh mọi file proxy về đều chính hãng. Pin version cố định coordinates, nhưng không tự ngăn một repository thay nội dung của cùng version. Checksum kiểm tra integrity, nhưng expected checksum lấy từ chính repository đã bị compromise có thể không đáng tin. Chữ ký hỗ trợ xác minh publisher, nhưng vẫn phải xác minh public key thuộc maintainer đáng tin.

Vì vậy, **repository allowlist + pin versions + checksum/signature verification + CI trust boundary** mới tạo thành chính sách tương đối đầy đủ.

## 3. Thiết kế repository manager cho doanh nghiệp

Một repository manager như Nexus/Artifactory hoặc dịch vụ tương đương có thể cung cấp một endpoint tập trung:

```text
                 Maven / Gradle builds
                          |
                          v
                Corporate repository manager
                          |
              +-----------+------------+
              |                        |
              v                        v
       Hosted internal             Proxy external
       com.acme:*                  Maven Central
       com.company:*               Gradle Plugin Portal
              |                    approved vendor repos
              +-----------+------------+
                          |
                          v
                 Virtual / group endpoint
                          |
                          v
                Developer and CI runners
```

Nên tách rõ:

- **Hosted repository:** chỉ pipeline có quyền mới được publish artifacts nội bộ.
- **Proxy repository:** cache nguồn bên ngoài đã được phê duyệt.
- **Virtual/group repository:** hợp nhất hosted và proxy thành endpoint cho developer/CI.
- **Content policy:** giới hạn group/module/plugin được phép; chặn version, license hoặc artifact không đạt policy.
- **Quarantine/scanning:** scan malware, CVE, license và metadata trước khi promote artifact mới.
- **Immutability:** release coordinates không bị ghi đè; snapshot/dev repository có policy riêng.
- **Audit:** ghi nhận identity nào tải/publish artifact, từ source nào và thời điểm nào.

Ví dụ endpoint minh họa:

- `https://repo.corp.example/repository/maven-all/` cho Maven dependencies/plugins.
- `https://repo.corp.example/repository/gradle-plugins/` cho Gradle plugin marker và plugin artifacts.
- `https://repo.corp.example/repository/maven-internal/` cho group nội bộ.

Các URL chỉ mô tả cách phân vùng; repository manager phải thật sự proxy/host đúng metadata, POM, Gradle module metadata và plugin marker cần thiết.

### 3.1. Chặn dependency confusion

Giả sử ứng dụng dùng `com.acme:billing-client:1.0.0`. Nếu artifact nội bộ không tồn tại ở repository nội bộ nhưng build tiếp tục hỏi public repository, kẻ khác có thể publish cùng coordinates lên public repo và khiến build nhận nhầm package.

Biện pháp:

- Namespace nội bộ phải có ownership rõ ràng.
- Group `com.acme` chỉ được resolve từ internal hosted repository.
- Không để public repository trở thành fallback cho group nội bộ.
- Repository manager áp dụng routing/allowlist; Gradle có thể dùng `exclusiveContent`.
- Release pipeline fail nếu artifact nội bộ thiếu thay vì tự tìm cùng GAV trên Internet.

**Không dùng thứ tự repository như hàng rào duy nhất.** Cần cấu hình routing/content policy có thể review và audit.

## 4. Maven: phân biệt project repositories và plugin repositories

Maven có hai loại repository trong POM:

- `<repositories>`: nơi tìm project dependencies.
- `<pluginRepositories>`: nơi tìm Maven plugins.

Plugin còn có dependency riêng trong plugin classpath. Parent POM, build extensions và artifacts phục vụ build cũng phải resolve từ nguồn đã kiểm soát.

Ví dụ fragment POM:

```xml
<repositories>
    <repository>
        <id>corp-public</id>
        <url>https://repo.corp.example/repository/maven-public/</url>
        <releases>
            <enabled>true</enabled>
            <checksumPolicy>fail</checksumPolicy>
        </releases>
        <snapshots>
            <enabled>false</enabled>
        </snapshots>
    </repository>
</repositories>

<pluginRepositories>
    <pluginRepository>
        <id>corp-plugins</id>
        <url>https://repo.corp.example/repository/maven-plugins/</url>
        <releases>
            <enabled>true</enabled>
            <checksumPolicy>fail</checksumPolicy>
        </releases>
        <snapshots>
            <enabled>false</enabled>
        </snapshots>
    </pluginRepository>
</pluginRepositories>
```

Đây là fragment giải thích cấu trúc. `checksumPolicy=fail` làm Maven fail khi checksum verification của repository không đạt. Nó **không phải chữ ký publisher**; nếu artifact và checksum cùng bị thay trong repository đã compromise, checksum đó không đủ chứng minh authenticity. Với môi trường doanh nghiệp, repository manager và verification/signature policy cần bổ sung.

## 5. Maven mirror trong settings.xml

Maven có thể dùng global settings hoặc user settings. User settings thường ở `~/.m2/settings.xml`; đây là nơi phù hợp để đặt mirror, server credentials, proxy và cấu hình môi trường. Không commit password cá nhân vào POM.

Ví dụ `settings.xml`:

```xml
<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0"
          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
          xsi:schemaLocation="http://maven.apache.org/SETTINGS/1.2.0 https://maven.apache.org/xsd/settings-1.2.0.xsd">

    <servers>
        <server>
            <id>corp-maven</id>
            <username>${env.REPO_USER}</username>
            <password>${env.REPO_PASSWORD}</password>
        </server>
    </servers>

    <mirrors>
        <mirror>
            <id>corp-maven</id>
            <name>Corporate Maven virtual repository</name>
            <url>https://repo.corp.example/repository/maven-all/</url>
            <mirrorOf>*</mirrorOf>
        </mirror>
    </mirrors>
</settings>
```

Giải thích:

1. `mirrorOf=*` yêu cầu Maven route remote repository requests qua endpoint nội bộ, bao gồm dependency và plugin repositories.
2. `id` của mirror là `corp-maven`; Maven lấy credentials từ `<server>` có **cùng id**.
3. `REPO_USER` và `REPO_PASSWORD` được CI secret store inject. Không in giá trị ra logs.
4. `maven-all` phải là virtual/group endpoint có thể phục vụ artifacts được phép, bao gồm plugins và dependencies.
5. Nếu policy yêu cầu tách endpoint plugin/dependency, hãy cấu hình mirror phù hợp; không giả định một repository chỉ proxy Maven Central sẽ chứa mọi Gradle/Maven plugin.
6. Dùng HTTPS và CA chain được trust. Không nhúng credentials trong URL.

**Maven mirror không phải repository aggregation tự động.** Maven chọn một mirror phù hợp cho mỗi request; nếu cần hợp nhất nhiều nguồn, dùng repository manager group/virtual repository. `mirrorOf=*` chỉ định tuyến qua một endpoint, không tự ghép nhiều mirror.

### 5.1. Server ID phải khớp mirror ID

Nếu POM khai báo repository ID `corp-public` nhưng settings chọn mirror ID `corp-maven`, credentials cho request qua mirror phải khớp **ID của mirror thực tế**. Nếu ID sai, Maven có thể truy cập URL nhưng không gửi đúng credentials và nhận 401.

CI nên tạo settings file tạm với quyền đọc hạn chế, inject secrets và truyền qua `-s`. Không commit file settings chứa credentials. Password encryption/secret injection không thay thế việc giới hạn token scope và bảo vệ runner.

## 6. Maven: pin plugin và dependency versions

### 6.1. BOM không quản lý mọi thứ trong build

Spring Boot parent/BOM quản lý dependency versions theo bộ đã kiểm thử cùng nhau. Nó không tự pin mọi Maven plugin version. Plugin versions cần được quản lý bằng parent plugin management hoặc khai báo rõ trong project.

Ví dụ `pluginManagement`:

```xml
<build>
    <pluginManagement>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.2.5</version>
            </plugin>
        </plugins>
    </pluginManagement>
</build>
```

`pluginManagement` cung cấp version/configuration cho plugin khi project thực sự sử dụng; nó không tự chạy plugin. Spring Boot parent có thể quản lý version `spring-boot-maven-plugin`; nếu không dùng parent, pin version rõ ràng.

Phân biệt:

- `dependencyManagement` quản lý version/scope của project dependencies.
- `pluginManagement` quản lý version/configuration của build plugins.

Đưa version vào BOM không tự pin Maven plugin version.

### 6.2. Tránh version thay đổi theo thời gian

Release build nên tránh:

- Maven version range như `[1.0,2.0)`.
- SNAPSHOT dependencies hoặc parent POM có nội dung thay đổi.
- Plugin không khai báo version rõ ràng.
- Build extension có version động.
- Repository cho phép ghi đè release coordinates.

Ưu tiên exact release versions, parent/plugin versions được pin, snapshots ở repository riêng và không cho release job resolve snapshot ngoài policy.

### 6.3. Kiểm tra graph đã resolve

Từ project root:

```bash
./mvnw -B -ntp dependency:tree
./mvnw -B -ntp dependency:resolve-plugins
./mvnw -B -ntp help:effective-pom
```

- `dependency:tree` cho biết dependency bắc cầu thực tế.
- `dependency:resolve-plugins` hỗ trợ kiểm tra Maven plugins đã resolve.
- `help:effective-pom` cho thấy cấu hình sau inheritance/profile/plugin management.

Không chạy verbose/debug config trên log công khai nếu có credentials. Dependency tree giúp hiểu graph, nhưng không tự xác minh bytes artifact.

## 7. Maven Wrapper: kiểm soát distribution và bootstrap binary

### 7.1. Wrapper tải gì?

Maven Wrapper thường gồm:

- `mvnw`/`mvnw.cmd`: entrypoint script cho Linux/macOS/Windows.
- `.mvn/wrapper/maven-wrapper.properties`: cấu hình distribution URL và version.
- `maven-wrapper.jar` nếu dùng binary Wrapper type; hoặc source/script-only variant.
- Maven distribution ZIP/TAR: chương trình Maven được tải và chạy.

Khi developer chạy `./mvnw verify`, Wrapper có thể tải Maven version trong properties file rồi mới thực hiện build. Vì vậy, **Maven dependency mirror không tự kiểm soát mọi chi tiết của bước tải Maven distribution**.

### 7.2. Dùng distribution mirror nội bộ

File `.mvn/wrapper/maven-wrapper.properties` cần trỏ `distributionUrl` tới Maven distribution đã được tổ chức phê duyệt và lưu trong repository manager nội bộ. Ví dụ URL có thể theo cấu trúc:

```text
https://repo.corp.example/repository/maven-distributions/apache-maven-3.9.9-bin.zip
```

Đường dẫn này chỉ là cấu trúc minh họa; repository manager phải chứa đúng file distribution tương ứng.

Maven Wrapper cũng hỗ trợ biến `MVNW_REPOURL` để route tải distribution qua repository manager. Nếu repository cần Basic Authentication, có thể cấp `MVNW_USERNAME` và `MVNW_PASSWORD` từ secret store. Không nhúng credentials vào `distributionUrl` vì properties file được commit vào Git.

### 7.3. Xác minh checksum riêng cho distribution và wrapper JAR

Maven Wrapper có hai thuộc tính:

- `distributionSha256Sum`: SHA-256 của Maven distribution ZIP/TAR.
- `wrapperSha256Sum`: SHA-256 của `maven-wrapper.jar` nếu project dùng binary Wrapper.

Lấy expected SHA-256 từ nguồn phát hành Apache đã xác minh độc lập; nếu tổ chức mirror file, checksum của mirror phải khớp bytes của release chính thức. Không tự tính checksum từ file vừa tải qua đúng nguồn đang bị nghi ngờ rồi chấp nhận nó làm trust anchor.

`wrapperSha256Sum` chỉ liên quan khi wrapper type có `maven-wrapper.jar`. Với source/script-only variant, review script và source downloader thực sự được commit.

### 7.4. Tạo/cập nhật Maven Wrapper

Khi có Maven đã được cài đặt và xác minh:

```bash
mvn wrapper:wrapper -Dmaven=3.9.9 -Dtype=bin
```

Sau khi chạy:

1. Review diff của `mvnw`, `mvnw.cmd`, `.mvn/wrapper/maven-wrapper.properties` và `maven-wrapper.jar`.
2. Xác nhận distribution URL trỏ đúng internal mirror/Apache distribution.
3. Ghi checksum distribution và wrapper binary tương ứng.
4. Kiểm tra version bằng `./mvnw -version`.
5. Commit thay đổi Wrapper cùng review như executable code, không chỉ như đổi version string.

## 8. Bài thực hành Maven với Spring Boot Java 17

Ta tạo ứng dụng nhỏ để minh họa build chạy qua repository settings đã được kiểm soát.

Cấu trúc:

```text
supply-chain-demo/
├── pom.xml
└── src/
    ├── main/java/dev/example/supplychain/
    │   ├── SupplyChainApplication.java
    │   └── OriginController.java
    └── test/java/dev/example/supplychain/
        └── OriginControllerTest.java
```

`pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>dev.example</groupId>
    <artifactId>supply-chain-demo</artifactId>
    <version>1.0.0</version>

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
                <version>3.3.13</version>
            </plugin>
        </plugins>
    </build>
</project>
```

POM không khai báo public repository riêng; CI dùng corporate settings file để route requests. Parent version và Boot plugin version được pin ở 3.3.13; starter versions do parent quản lý.

`src/main/java/dev/example/supplychain/SupplyChainApplication.java`:

```java
package dev.example.supplychain;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SupplyChainApplication {

    public static void main(String[] args) {
        SpringApplication.run(SupplyChainApplication.class, args);
    }
}
```

`src/main/java/dev/example/supplychain/OriginController.java`:

```java
package dev.example.supplychain;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class OriginController {

    @GetMapping("/origin")
    public String origin() {
        return "dependency-policy-ok";
    }
}
```

`src/test/java/dev/example/supplychain/OriginControllerTest.java`:

```java
package dev.example.supplychain;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class OriginControllerTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void endpointReturnsExpectedBody() throws Exception {
        mvc.perform(get("/origin"))
                .andExpect(status().isOk())
                .andExpect(content().string("dependency-policy-ok"));
    }
}
```

Build bằng Wrapper và corporate settings:

```bash
./mvnw -B -ntp -s "$CI_MAVEN_SETTINGS" clean verify
```

`CI_MAVEN_SETTINGS` là đường dẫn tới settings file do CI tạo an toàn, chứa mirror/server ID phù hợp. Không commit file có credentials. Build thành công xác nhận source compile/test/package theo POM; để kiểm chứng repository policy, CI cần chạy bằng runner không có local cache chưa được xác minh và lưu logs/graph evidence theo policy.

## 9. Gradle: plugin repositories và dependency repositories

Gradle tách hai đường:

- `pluginManagement.repositories` trong `settings.gradle`: nơi tìm plugins được khai báo qua `plugins { ... }`.
- `dependencyResolutionManagement.repositories`: nơi tìm thư viện cho project/subprojects.

Đặt `mavenCentral()` trong `repositories` của `build.gradle` **không** tự thêm nơi tìm plugin DSL. Thêm Gradle Plugin Portal vào `pluginManagement` cũng không làm nó thành project dependency repository.

### 9.1. Centralize repository declarations

Ví dụ `settings.gradle`:

```groovy
pluginManagement {
    repositories {
        maven {
            name = 'corpPlugins'
            url = uri('https://repo.corp.example/repository/gradle-plugins/')
            credentials(PasswordCredentials)
        }
    }
}

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)

    repositories {
        exclusiveContent {
            forRepository {
                maven {
                    name = 'corpInternal'
                    url = uri('https://repo.corp.example/repository/maven-internal/')
                    credentials(PasswordCredentials)
                }
            }
            filter {
                includeGroupAndSubgroups('com.acme')
            }
        }

        maven {
            name = 'corpPublic'
            url = uri('https://repo.corp.example/repository/maven-public/')
            credentials(PasswordCredentials)
        }
    }
}

rootProject.name = 'supply-chain-demo'
```

Giải thích:

1. `corpPlugins` cung cấp plugin marker và plugin artifacts. Repository manager phải proxy đúng nguồn plugin được phê duyệt.
2. `corpInternal` chỉ nhận group `com.acme` và các subgroup. `exclusiveContent` bảo đảm group đó chỉ được hỏi internal repository.
3. `corpPublic` là proxy/virtual repository cho dependencies bên ngoài đã duyệt.
4. `FAIL_ON_PROJECT_REPOS` làm build fail nếu subproject tự khai báo repository ngoài settings.
5. Nếu policy chỉ cho phép corporate repository, không thêm public fallback trực tiếp như `gradlePluginPortal()`/`mavenCentral()`; repository manager phải proxy các nguồn được phê duyệt.

### 9.2. Cấp Gradle credentials qua properties

`credentials(PasswordCredentials)` lấy properties theo repository name:

| Repository | Username property | Password property |
| --- | --- | --- |
| `corpPlugins` | `corpPluginsUsername` | `corpPluginsPassword` |
| `corpInternal` | `corpInternalUsername` | `corpInternalPassword` |
| `corpPublic` | `corpPublicUsername` | `corpPublicPassword` |

Trên CI, inject bằng environment properties có prefix `ORG_GRADLE_PROJECT_`. Ví dụ tên biến:

```text
ORG_GRADLE_PROJECT_corpPluginsUsername
ORG_GRADLE_PROJECT_corpPluginsPassword
ORG_GRADLE_PROJECT_corpInternalUsername
ORG_GRADLE_PROJECT_corpInternalPassword
ORG_GRADLE_PROJECT_corpPublicUsername
ORG_GRADLE_PROJECT_corpPublicPassword
```

Đây là **tên biến** để CI secret store cấp giá trị. Với máy local, có thể đặt properties trong `~/.gradle/gradle.properties` và giới hạn quyền đọc file; không commit credentials.

### 9.3. Cấm fallback cho group nội bộ

Nếu `com.acme:billing-client:1.0.0` không có trong internal repository, Gradle phải fail thay vì tìm cùng coordinates ở public repo. Đây là mục tiêu của `exclusiveContent`. Nếu nội bộ phát hành Gradle plugin, phải kiểm tra cả plugin marker coordinates; plugin marker group không nhất thiết trùng implementation module group.

## 10. Gradle: pin plugin, BOM và project dependencies

`build.gradle` (Groovy DSL):

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
}

group = 'dev.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.13')
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}

dependencyLocking {
    lockAllConfigurations()
}
```

- Spring Boot plugin version được pin trong `plugins` block và resolve qua `pluginManagement`.
- Boot BOM quản lý version starter/transitive dependencies.
- `dependencyLocking` lưu version đã resolve cho các configurations được lock.
- Repository declarations nằm trong `settings.gradle` để policy được review tập trung.
- Gradle Wrapper version được pin riêng trong `gradle-wrapper.properties`.

### 10.1. Tạo dependency lock state

Với project mẫu:

```bash
./gradlew build --write-locks
```

Gradle tạo/cập nhật `gradle.lockfile` ghi các module versions đã resolve. Commit lock file và review mọi thay đổi khi nâng dependency.

**Locking không kiểm tra bytes.** Nó cố định coordinates/version; nếu repository thay nội dung của cùng version, cần dependency verification để phát hiện. Locking cũng không giải quyết changing dependencies như `-SNAPSHOT`; release nên dùng versions ổn định.

## 11. Gradle dependency verification

Gradle có thể xác minh dependency/plugin artifacts và metadata bằng file:

`gradle/verification-metadata.xml`

Khi file tồn tại, Gradle áp dụng dependency verification cho các artifacts được dependency management engine resolve, bao gồm JAR/ZIP, POM/module metadata và plugin artifacts.

Bootstrap metadata trong môi trường đã được tin cậy:

```bash
./gradlew --write-verification-metadata sha256,pgp build
```

Sau khi sinh file:

1. Review diff của `gradle/verification-metadata.xml`.
2. Xác minh checksum với release source chính thức khi có thể.
3. Xác minh PGP key fingerprint thuộc maintainer đáng tin; không tự động trust mọi key được tải.
4. Kiểm tra các entries do Gradle tự sinh và ghi origin/trust rationale.
5. Commit metadata và chạy CI ở strict verification mode.

### 11.1. Checksum khác signature

| Cơ chế | Chứng minh | Giới hạn |
| --- | --- | --- |
| SHA-256 | Bytes tải về khớp fingerprint đã tin cậy | Không tự chứng minh ai publish |
| PGP signature | Artifact được ký bởi key tương ứng | Phải xác minh key thuộc maintainer |
| Lockfile | Version nào được resolve | Không kiểm tra bytes |
| Vulnerability scan | Có CVE đã biết hay không | Không chứng minh source/authenticity |

Nếu checksum và artifact cùng lấy từ repository đã bị compromise, chúng có thể bị thay đồng thời. Nên lấy checksum từ nguồn độc lập hoặc xác minh signature khi có.

### 11.2. Bootstrap có rủi ro

`--write-verification-metadata` tạo metadata từ artifacts hiện tại mà build tải về. Nếu repository đã trả artifact độc hại, bootstrap có thể ghi checksum của artifact đó. Vì vậy bootstrap chỉ là bước khởi tạo; cần review và xác minh độc lập trước khi commit.

Gradle có thể verify PGP signatures khi artifact publish `.asc`. Không phải mọi artifact đều có signature; checksum đã tin cậy là fallback. Nếu signature tồn tại nhưng key chưa trusted, build nên fail để người review xác minh fingerprint thay vì tự động chấp nhận.

**Không thêm `trusted-artifacts` cho toàn bộ group chỉ để làm CI xanh.** Cấu hình đó có thể bỏ qua verification cho artifacts khớp rule.

## 12. Gradle Wrapper: pin distribution và kiểm tra Wrapper JAR

### 12.1. Pin distribution URL và SHA-256

File `gradle/wrapper/gradle-wrapper.properties`:

```properties
distributionUrl=https://repo.corp.example/gradle-distributions/gradle-8.10.2-bin.zip
distributionSha256Sum=31c55713e40233a8303827ceb42ca48a47267a0ad4bab9177123121e71524c26
```

Checksum trên là SHA-256 chính thức của `gradle-8.10.2-bin.zip`. Nếu chọn `-all.zip`, version khác hoặc file khác, checksum phải đổi đúng theo artifact đó. Khi mirror nội bộ lưu nguyên bytes, checksum vẫn phải giống nguồn chính thức.

Gradle Wrapper so sánh distribution bytes với `distributionSha256Sum` và fail nếu không khớp. Tài liệu Gradle nêu checksum distribution chỉ được kiểm tra khi distribution chưa được tải/cached; CI cần quản lý cache/Gradle User Home theo trust boundary.

### 12.2. Wrapper JAR được kiểm tra riêng

`gradle-wrapper.jar` nằm ở `gradle/wrapper/gradle-wrapper.jar` và được commit vào source control. Nó chạy trước build script và trước dependency verification. `distributionSha256Sum` **không** xác minh Wrapper JAR.

Với Gradle 8.10.2, checksum Wrapper JAR được Gradle công bố là:

```text
2db75c40782f5e8ba1fc278a5574bab070adccb2d21ca5a6e5ed840888448046
```

Trên Linux/macOS:

```bash
printf '%s  %s\n' '2db75c40782f5e8ba1fc278a5574bab070adccb2d21ca5a6e5ed840888448046' 'gradle/wrapper/gradle-wrapper.jar' | sha256sum --check -
```

Output khi khớp:

```text
gradle/wrapper/gradle-wrapper.jar: OK
```

Có thể dùng Gradle Wrapper Validation action/Gradle Setup Action đã được tổ chức phê duyệt trong GitHub Actions để kiểm tra Wrapper JAR. Review mọi thay đổi JAR như thay đổi executable code, không chỉ như nâng version.

### 12.3. Auth tải Gradle distribution private

Nếu internal distribution server cần Basic Auth/Bearer token, đặt credentials trong Gradle User Home hoặc CI secret properties, không nhúng vào `distributionUrl` đã commit. Gradle hỗ trợ system properties theo hostname, ví dụ:

```properties
systemProp.gradle.repo_corp_example_wrapperUser=build-reader
systemProp.gradle.repo_corp_example_wrapperPassword=secret-from-ci
```

Đây là ví dụ về **cấu trúc properties ngoài repository**; CI phải inject giá trị thật qua secret store. Gradle cũng hỗ trợ `wrapperToken` nếu server dùng Bearer authentication. Giới hạn credential theo hostname để tránh gửi tới máy chủ khác nếu URL bị đổi.

## 13. Maven Wrapper và Gradle Wrapper so sánh

| Nội dung | Maven Wrapper | Gradle Wrapper |
| --- | --- | --- |
| Distribution URL | `distributionUrl` trong `.mvn/wrapper/maven-wrapper.properties` | `distributionUrl` trong `gradle-wrapper.properties` |
| Distribution checksum | `distributionSha256Sum` | `distributionSha256Sum` |
| Wrapper binary checksum | `wrapperSha256Sum` khi có `maven-wrapper.jar` | Xác minh `gradle-wrapper.jar` riêng |
| Internal mirror | `MVNW_REPOURL` hoặc URL trong properties | `distributionUrl` trỏ internal mirror |
| Auth | `MVNW_USERNAME`/`MVNW_PASSWORD` | Host-scoped Wrapper system properties |
| Bootstrap code | Wrapper script và tùy chọn wrapper JAR/source | `gradlew`/`gradlew.bat` và `gradle-wrapper.jar` |

Hai Wrapper đều cần được commit, pin version và verify. Chúng không thay thế repository policy cho plugin/dependency sau khi build tool đã khởi động.

## 14. CI: dùng Wrapper và repository policy đã review

### 14.1. Maven CI

```bash
./mvnw -version
./mvnw -B -ntp -s "$CI_MAVEN_SETTINGS" clean verify
```

`CI_MAVEN_SETTINGS` là settings file CI tạo an toàn, có mirror/server ID phù hợp. Credentials đến từ secret store và file không được commit. CI cần fail khi Wrapper checksum mismatch, repository auth fail hoặc artifact không resolve từ approved endpoint.

### 14.2. Gradle CI

```bash
./gradlew --version
./gradlew --no-daemon --dependency-verification strict clean build
```

`--dependency-verification strict` làm verification failures fail build. Không dùng `lenient`/`off` trong release gate để che checksum/signature mismatch. Khi nâng dependency, cập nhật lockfile/verification metadata trong PR riêng có review.

### 14.3. Cache và runner

- Cache chỉ được chia sẻ trong trust boundary phù hợp; untrusted PR không được ghi cache dùng bởi release jobs.
- Không xem `mvn -o` hoặc Gradle `--offline` là bằng chứng nguồn tải đáng tin; offline chỉ ngăn truy cập network.
- Không chạy release bằng global settings/init scripts không được quản lý.
- Không cấp production secrets cho build scripts chạy từ untrusted fork.
- Tách build/test job khỏi publish/deploy job có quyền mạnh.
- Lưu logs về Wrapper version, repository source, dependency graph, lock/verification changes và artifact provenance theo policy.

## 15. Build extensions và cấu hình ngoài project

Một số thành phần thay đổi build trước khi task/test thông thường chạy.

**Maven:**

- `.mvn/extensions.xml` khai báo core extensions có thể chạy trong Maven core.
- `.mvn/maven.config` và `.mvn/jvm.config` thay đổi command/JVM options.
- Global/user `settings.xml` có thể thêm profiles, mirrors, servers và proxies.
- Wrapper scripts/JAR chạy trước Maven.

**Gradle:**

- `settings.gradle` có thể áp dụng settings plugins và thay đổi plugin resolution.
- `buildSrc`, included builds và convention plugins là build logic thực thi.
- `~/.gradle/init.d` có thể chứa init scripts ảnh hưởng mọi build trên máy/runner.
- `GRADLE_USER_HOME/gradle.properties` và global init scripts có thể tác động credentials/repositories.

CI release nên dùng runner image đã quản lý, inspect global settings/init scripts và giới hạn quyền đọc file/secret của build process. Chỉ review `pom.xml` hoặc `build.gradle` là chưa đủ để hiểu toàn bộ nguồn code build đang chạy.

## 16. Những lỗi phổ biến và cách xử lý

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Maven tải dependency từ Central dù có internal repo | Mirror không match hoặc không có `mirrorOf=*` | Kiểm tra effective settings và mirror selection |
| Maven plugin tải được nhưng dependency fail | `pluginRepositories` và `repositories` là hai đường khác nhau | Kiểm tra cả hai hoặc mirror tập trung |
| Maven báo 401 sau khi cấu hình mirror | `<server><id>` không khớp mirror ID | Dùng đúng ID của mirror được chọn |
| Maven checksum policy chỉ warn | Repository policy không đặt fail hoặc checksum source không đáng tin | Đặt policy phù hợp và xác minh checksum/signature độc lập |
| Maven Wrapper tải từ Internet | `distributionUrl`/`MVNW_REPOURL` chưa trỏ mirror | Cấu hình Wrapper distribution riêng |
| Maven Wrapper checksum mismatch | URL trỏ file khác hoặc artifact bị thay | Fail build, xác minh release source; không tự cập nhật checksum |
| Gradle plugin không resolve | Thiếu plugin marker/plugin repository | Cấu hình `pluginManagement` và proxy plugin portal |
| Gradle subproject tự thêm Maven Central | Repository mode chưa khóa | Dùng `FAIL_ON_PROJECT_REPOS` |
| Internal group resolve từ public | Thiếu exclusive routing | Dùng `exclusiveContent` và manager routing |
| Gradle báo missing checksum | Verification metadata chưa có artifact/POM/plugin bắc cầu | Review và cập nhật metadata |
| Gradle checksum mismatch | Bytes khác expected | Dừng build, kiểm tra cache/repository và nguồn chính thức |
| PGP key không trusted | Chưa xác minh fingerprint | Kiểm tra key với maintainer và cập nhật trust metadata có review |
| Gradle distribution checksum pass nhưng Wrapper JAR đổi | Hai file được kiểm tra riêng | Verify `gradle-wrapper.jar` bằng checksum/action |
| Gradle Wrapper checksum không chạy với cache nóng | Distribution đã có trong cache | Dùng cache tin cậy/isolated GRADLE_USER_HOME, verify Wrapper JAR |
| Lockfile không đổi nhưng bytes thay | Lockfile khóa version, không khóa content | Bật dependency verification |
| BOM đã pin nhưng plugin version trôi | BOM không quản lý mọi plugin version | Pin trong `pluginManagement`/plugin declaration |
| Build laptop pass nhưng CI sạch fail | Cache/global settings che thiếu cấu hình | Dùng Wrapper, settings đồng nhất, runner sạch |
| `--offline` pass | Artifact tồn tại trong local cache | Xác minh provenance/cache; offline không phải trust proof |
| Plugin mới yêu cầu quyền/secret bất thường | Plugin chạy trong build process | Review source, quyền runner và scope secrets |

### Quy trình điều tra khi nghi artifact bị thay

1. Ghi lại group/module/version, plugin ID, repository URL/ID và thời điểm resolve.
2. Giữ logs và checksum mismatch; chưa xóa cache trước khi thu thập bằng chứng.
3. Tính SHA-256 file cache, đối chiếu với repository và release source chính thức.
4. Kiểm tra POM/module metadata và dependency graph có thay đổi không.
5. Kiểm tra Wrapper distribution/JAR nếu thay đổi xảy ra trước build.
6. Xác minh PGP key fingerprint từ nguồn độc lập.
7. Báo repository manager/security owner và quarantine artifact nếu có dấu hiệu tampering.
8. Chỉ cập nhật lock/verification metadata sau khi xác nhận artifact mong đợi.

## 17. Bài tập tự kiểm tra

**Tình huống A.** Maven POM có `<repositories>` nhưng plugin không tải được từ internal repository. Vì sao?

*Đáp án:* Plugin resolution dùng `<pluginRepositories>`; cấu hình cả hai hoặc dùng mirror trong `settings.xml` bao phủ mọi repository requests.

**Tình huống B.** Maven mirror có URL đúng nhưng trả 401. Điều đầu tiên cần kiểm tra?

*Đáp án:* `<server><id>` có khớp `<mirror><id>` được chọn không, và CI đã inject credentials chưa.

**Tình huống C.** Spring Boot BOM quản lý starter versions. Có thể bỏ pin tất cả Maven plugin versions?

*Đáp án:* Không. BOM quản lý dependencies; plugin versions cần pluginManagement/parent plugin management hoặc version riêng.

**Tình huống D.** Gradle có `mavenCentral()` trong `pluginManagement` nhưng `implementation` không resolve được Spring Web. Vì sao?

*Đáp án:* Plugin repositories và project dependency repositories độc lập. Cần khai báo trong `dependencyResolutionManagement`.

**Tình huống E.** Gradle lockfile không đổi nhưng checksum verification fail. Có thể bỏ verification vì version đã lock?

*Đáp án:* Không. Lockfile pin version; verification metadata kiểm tra bytes. Cần cả hai.

**Tình huống F.** Gradle distribution checksum pass nhưng Wrapper JAR bị thay. Có an toàn không?

*Đáp án:* Chưa. `distributionSha256Sum` kiểm tra distribution ZIP; `gradle-wrapper.jar` phải xác minh riêng.

**Tình huống G.** Gradle bootstrap verification metadata từ public repo rồi build pass. Có thể tin mọi checksum?

*Đáp án:* Không. Bootstrap ghi lại bytes hiện tại; review và xác minh độc lập trước khi commit.

**Tình huống H.** Maven checksumPolicy là `fail`. Có chứng minh artifact authenticity không?

*Đáp án:* Không hoàn toàn. Nó kiểm tra checksum repository cung cấp; nếu artifact/checksum cùng bị thay, cần signature/provenance hoặc checksum độc lập.

**Tình huống I.** `MVNW_REPOURL` đã trỏ internal repo nhưng dependency vẫn tải public. Vì sao?

*Đáp án:* `MVNW_REPOURL` điều khiển Maven Wrapper distribution, không phải toàn bộ dependency/plugin repositories sau khi Maven khởi động. Cần Maven settings mirror.

**Tình huống J.** Gradle bật `FAIL_ON_PROJECT_REPOS` nhưng plugin vẫn resolve từ một nguồn khác. Vì sao?

*Đáp án:* Repository mode áp dụng project dependency repositories; plugin repositories vẫn cấu hình riêng trong `pluginManagement`. Kiểm tra cả settings/init scripts.

## 18. Checklist nghiệm thu

**Wrapper và build tool:**

- Wrapper scripts/binaries đã được review và xác minh checksum/signature.
- Maven/Gradle distribution version được pin trong Wrapper properties.
- `distributionSha256Sum` khớp đúng file distribution đã phê duyệt.
- Maven Wrapper JAR có `wrapperSha256Sum` nếu dùng binary type.
- Gradle Wrapper JAR được xác minh riêng, không nhầm với distribution checksum.
- Wrapper distribution tải qua internal mirror/HTTPS theo policy.
- Wrapper credentials nằm ngoài source control và chỉ có quyền read.

**Repositories và plugins:**

- Maven `repositories`/`pluginRepositories` được route qua approved mirror.
- Maven settings server/mirror IDs khớp; secrets inject an toàn.
- Gradle `pluginManagement` và `dependencyResolutionManagement` được cấu hình riêng.
- Gradle `FAIL_ON_PROJECT_REPOS` và content filters chặn repo ngoài allowlist.
- Internal groups chỉ resolve từ hosted repository; không public fallback.
- Plugin versions/transitive plugin dependencies được pin và review.
- Build extensions, settings plugins, init scripts/global config được quản lý.

**Dependencies và verification:**

- Spring Boot BOM/parent và dependency versions được pin.
- Release không dùng dynamic/latest/range/SNAPSHOT.
- Gradle lockfile được commit và cập nhật có review.
- Gradle verification metadata có checksum/signature đã xác minh.
- Maven checksum policy phù hợp và có chữ ký/provenance bổ sung khi cần.
- CVE/license/malware scan là gate riêng, không nhầm với checksum.
- CI build trên runner/cache có trust boundary rõ.

**CI và phát hành:**

- CI chạy Wrapper thay vì Maven/Gradle tùy ý có sẵn trên PATH.
- CI dùng settings/Gradle properties được inject an toàn.
- Untrusted PR không có publisher secrets hoặc quyền ghi cache release.
- Verification failure làm job fail; không dùng lenient/off để che mismatch.
- Lưu repository source, dependency graph, Wrapper/tool versions, lock/verification metadata diff và artifact provenance theo policy.
- Release artifact được tạo từ đúng build đã qua kiểm tra, không rebuild bằng nguồn/toolchain khác ở bước deploy.

**Kết luận:** Chuỗi cung ứng build Spring Boot phải được bảo vệ từ **Wrapper distribution và Wrapper binary**, đến **plugin repositories**, **project dependency repositories**, **version/lock state** và **bytes tải về**. Maven dùng `settings.xml` mirror, `repositories`/`pluginRepositories`, BOM/pluginManagement và Wrapper checksum properties; Gradle dùng `pluginManagement`, `dependencyResolutionManagement`, content filters, dependency locking và `verification-metadata.xml`. Kết hợp repository manager, version pinning, checksum/signature verification và CI runner đáng tin giúp nhóm xác nhận build đã sử dụng **đúng công cụ, đúng nguồn và đúng artifact được phê duyệt**.

### Tài liệu chính thức

- Apache Maven — Using Mirrors for Repositories: https://maven.apache.org/guides/mini/guide-mirror-settings.html
- Apache Maven — Settings Reference: https://maven.apache.org/settings.html
- Apache Maven — POM Reference: https://maven.apache.org/pom.html
- Apache Maven — Maven Wrapper: https://maven.apache.org/tools/wrapper/
- Apache Software Foundation — Verifying Releases: https://apache.org/info/verification.html
- Gradle — Securing Repositories: https://docs.gradle.org/current/userguide/securing_repositories.html
- Gradle — Declaring Repositories: https://docs.gradle.org/current/userguide/declaring_repositories.html
- Gradle — Dependency Locking: https://docs.gradle.org/current/userguide/dependency_locking.html
- Gradle — Dependency Verification: https://docs.gradle.org/current/userguide/dependency_verification.html
- Gradle — Gradle Wrapper: https://docs.gradle.org/current/userguide/gradle_wrapper.html
- Gradle — Securing the Build Tool: https://docs.gradle.org/current/userguide/securing_build_tool.html
- Gradle — Official Distribution and Wrapper Checksums: https://gradle.org/release-checksums/
- Spring Boot 3.3 — Gradle Plugin: https://docs.spring.io/spring-boot/3.3/gradle-plugin/