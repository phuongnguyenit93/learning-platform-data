# Phân biệt cache tải thư viện với artifact cần bàn giao trong Maven, IDE và CI

> **Build Tool Maven · IDE và CI**  
> Phạm vi thực hành: Maven 3.9.x, Java 17, Maven Compiler Plugin 3.14.1, Surefire Plugin 3.6.1, JAR Plugin 3.5.1 và JUnit Jupiter 5.11.4. Bài giải thích vì sao **Maven local repository cache**, **thư mục `target/`**, **CI cache**, **CI build artifact** và **Maven artifact repository** không phải cùng một khái niệm; hướng dẫn cách tạo, kiểm tra, lưu và bàn giao đúng file để job khác có thể tiếp tục mà không phụ thuộc bộ cache riêng của developer hoặc runner.

## 1. Bài toán thực tế: “Máy tôi chạy được, nhưng job sau không thấy JAR”

Giả sử developer chạy:

```bash
mvn -B clean verify
```

và nhận:

```text
BUILD SUCCESS
```

IDE đang dùng JUnit, Maven đã tải nhiều thư viện, file JAR nằm dưới `target/`. Sau đó một job triển khai ở runner khác báo:

```text
File not found: handoff-demo-1.0.0.jar
```

Có thể build không sai. Vấn đề là **đã nhầm dữ liệu hỗ trợ build với sản phẩm cần bàn giao**:

- Máy developer đã có dependency trong `~/.m2/repository`.
- Job build có JAR trong `target/`.
- Job triển khai chạy ở **workspace khác**.
- CI cache có thể chứa dependencies nhưng **không hứa chứa JAR đã QA**.
- Nếu không upload/download artifact hoặc publish vào repository được kiểm soát, **file cần bàn giao không tự đến job kế tiếp**.

**Quy tắc nền tảng:**

> **Cache là tối ưu hiệu năng, có thể mất và có thể tái tạo. Artifact bàn giao là kết quả cụ thể của một lần build, phải được đặt tên, lưu giữ, chuyển giao và kiểm tra tính toàn vẹn theo hợp đồng.**

Một cache hit có thể giảm thời gian download; nó **không thay thế** việc tạo JAR, chạy tests và bảo đảm job sau nhận đúng JAR đã được kiểm thử.

## 2. Năm loại “nơi chứa file” cần phân biệt

| Loại | Nơi thường gặp | Chứa gì? | Mục đích | Có được coi là bản bàn giao? |
| --- | --- | --- | --- | --- |
| Maven local repository | `~/.m2/repository` hoặc `-Dmaven.repo.local=...` | Dependency JAR/POM, plugins, metadata, artifacts `mvn install` cục bộ | Tái sử dụng input cho Maven Resolver | **Không mặc định** |
| Project build output | `target/` | `.class`, test XML, JAR/WAR, resources, generated files | Sản phẩm và trung gian của lần build trong workspace | **Chỉ sau khi chọn đúng output và lưu riêng** |
| CI dependency cache | Cache store của GitHub/GitLab/runner | Các thư viện/plugins tải về và file đắt để tái tạo | Tăng tốc nhiều lần CI | **Không** |
| CI workflow/job artifact | Artifact store gắn CI run/job | JAR đã build, test reports, checksum, logs được chọn | Chuyển giữa jobs, tải để kiểm tra, giữ evidence | **Có, theo retention và quyền truy cập** |
| Maven artifact repository | Maven Central/Nexus/Artifactory/GitLab registry hoặc repo nội bộ | GAV-versioned JAR/POM, classifiers, metadata | Publish/distribute release cho consumers | **Có, theo chính sách version/immutability** |

**Đặc biệt:** `target/` không phải **CI artifact store**. Nó chỉ là một thư mục trên filesystem của job hiện tại. CI chỉ biết cần giữ file nào khi workflow có lệnh upload artifact phù hợp.

### 2.1. Sơ đồ luồng dữ liệu

```text
             Project source + pom.xml
                       |
                 Maven Resolver
                       |
      Remote repositories (Central/mirror/private)
                       |
                       v
         Local Maven repository cache
               ~/.m2/repository
                       |
                 compile + test
                       |
                       v
                 target/ folder
        +--------------+-------------------+
        |                                  |
  build intermediates                 final output
  .class, generated, temp            handoff-demo-1.0.0.jar
        |                                  |
        |                             chọn + kiểm tra
        |                                  |
        |                                  v
        |                      handoff/JAR + POM + reports
        |                          + SHA-256 record
        |                                  |
        |                         CI upload-artifact
        |                                  |
        |                       CI artifact store
        |                                  |
        |                   next job: download + verify
        |                                  |
        |                         deployment/promotion
        |                                  |
        |                    Maven repository/registry
        |
        +--> không coi toàn bộ target là release package
```

**Không nhất thiết phải dùng cả CI artifacts lẫn Maven repository cho mọi dự án.** Pipeline PR có thể chỉ cần CI artifact để review; thư viện dùng chung nên publish Maven GAV vào registry; ứng dụng triển khai có thể chuyển JAR qua kho artifact immutable rồi đưa vào image. Quan trọng là **điểm bàn giao và cách xác nhận bytes**.

## 3. Maven local repository: cache cho thư viện, plugins và metadata

Theo Maven Settings Reference, local repository mặc định thường là:

```text
Linux/macOS:
  ~/.m2/repository

Windows:
  %USERPROFILE%\.m2\repository
```

Có thể thay bằng `settings.xml` hoặc CLI:

```bash
mvn -Dmaven.repo.local=/tmp/maven-cache-lab clean verify
```

Ví dụ đường dẫn `/tmp/...` dành cho hệ Unix; trên Windows cần đường dẫn hợp lệ tương ứng.

### 3.1. Cấu trúc thường thấy

Sau khi resolve JUnit Jupiter hoặc Maven plugins, cache có thể chứa:

```text
~/.m2/repository/
├── org/junit/jupiter/junit-jupiter/5.11.4/
│   ├── junit-jupiter-5.11.4.pom
│   └── junit-jupiter-5.11.4.jar
├── org/apache/maven/plugins/maven-compiler-plugin/3.14.1/
│   └── maven-compiler-plugin-3.14.1.jar
├── org/apache/maven/plugins/maven-surefire-plugin/3.6.1/
│   └── maven-surefire-plugin-3.6.1.jar
└── ... metadata, checksums và dependencies liên quan
```

Đây là **cây minh họa**, không phải danh sách đảm bảo đầy đủ; Maven có thể lưu thêm `.lastUpdated`, `_remote.repositories`, `maven-metadata-...xml`, POMs của dependencies bắc cầu, plugin dependencies và dữ liệu bookkeeping khác. Khi một artifact chưa được tải, những file tương ứng có thể chưa tồn tại.

Một **local repository** còn có thể chứa artifacts **do chính dự án cài vào bằng `mvn install`**. Vì vậy tên “local repository” chính xác hơn “folder chỉ chứa thư viện tải về”.

### 3.2. Vai trò của local cache trong vòng đời Maven

Khi Maven cần:

```xml
<dependency>
    <groupId>org.junit.jupiter</groupId>
    <artifactId>junit-jupiter</artifactId>
    <version>5.11.4</version>
    <scope>test</scope>
</dependency>
```

nó sẽ tra local repository và các repository remote/mirror theo rules resolution. Nếu đã có artifact hợp lệ trong local repository, Maven có thể **tránh tải lại**. Khi metadata cần cập nhật, SNAPSHOT hoặc policy khác có thể khiến nó liên hệ remote.

Trong ví dụ của bài, JUnit là **test input**; nó không tự được đóng vào main JAR chỉ vì có mặt trong Maven cache. Một project có `junit-jupiter` không phải ứng dụng runtime luôn cần JUnit.

### 3.3. Cache không có bảo đảm về “mới nhất” hay “đúng release”

Có những tình huống:

- Máy A đã tải SNAPSHOT ngày hôm trước, máy B tải snapshot mới.
- Hai runners có metadata range khác nhau.
- Mirror/repository manager thay artifact hoặc upstream.
- Local repository có artifact tự `install` từ project riêng.
- Cache bị xóa do disk cleanup/retention/quota.
- Plugin chưa cache khiến offline build fail.
- Cache bị chiếm dụng hoặc bị poison trong workflow trust boundary yếu.

Từ đó, **cache hit không phải một bước QA**. CI vẫn cần xây code, chạy tests, kiểm tra dependencies và tạo release output đúng version.

### 3.4. `mvn -o` và `mvn -U`

```bash
mvn -o clean verify
mvn -U clean verify
```

- `-o` bật offline mode: Maven không truy cập remote, chỉ dùng local repository đã có. Build có thể fail nếu thiếu dependency/plugin/metadata.
- `-U` yêu cầu Maven kiểm tra lại cập nhật cho một số loại metadata/SNAPSHOT; nó không “khóa” versions hay bảo đảm reproducibility.

**Offline không phải lockfile.** Cache hai máy có thể khác, nên hai máy offline có thể cho kết quả khác nhau. **Refresh cũng không phải verification:** nó có thể khiến snapshot/range resolution thay đổi.

### 3.5. `dependency:go-offline` có ích nhưng không thay artifact bàn giao

Maven Dependency Plugin 3.11.0 có goal:

```bash
mvn -B org.apache.maven.plugins:maven-dependency-plugin:3.11.0:go-offline
```

Mục đích là pre-resolve project dependencies, plugins và report dependencies để chuẩn bị cho offline builds. Nó **không** đóng gói ứng dụng thành JAR và **không** upload JAR sang job khác.

Trong các project có plugin/generator/profile riêng, vẫn nên kiểm tra thực tế `mvn -o clean verify` trong môi trường thử nghiệm vì có thể còn input chỉ được yêu cầu ở một execution không được prefetch như mong đợi.

**Không đưa toàn bộ `~/.m2` vào artifact phát hành** chỉ vì `go-offline` đã tải xong. Cache có thể rất lớn, chứa các phiên bản không liên quan và metadata không có ý nghĩa với người tiêu thụ JAR.

## 4. `target/`: đầu ra cục bộ của build, không phải một package bàn giao hoàn chỉnh

Với project Maven chuẩn, output folder thường có:

```text
target/
├── classes/
├── test-classes/
├── generated-sources/
├── maven-status/
├── surefire-reports/
├── maven-archiver/
└── handoff-demo-1.0.0.jar
```

Cây có thể khác theo packaging, plugins, active profiles và phases được chạy. Không có `surefire-reports` nếu chưa chạy tests; không có JAR nếu chưa đi tới phase package trong một project đóng gói JAR.

### 4.1. Phân biệt build intermediates và sản phẩm cuối

| Đường dẫn | Bản chất | Có nên bàn giao? |
| --- | --- | --- |
| `target/classes/` | Classes/resources sau biên dịch | Thường **không** nếu phát hành JAR |
| `target/test-classes/` | Compiled test classes | Không đưa vào production package mặc định |
| `target/surefire-reports/` | XML/text unit-test results | Có thể **đính kèm evidence**, không phải runtime artifact |
| `target/generated-sources/` | Generated source code | Chỉ bàn giao khi contract yêu cầu |
| `target/maven-status/` | Compiler/build bookkeeping | Không |
| `target/handoff-demo-1.0.0.jar` | Packaged application JAR | Có, sau tests/QA và kiểm tra |
| `target/*-sources.jar` | Classified source artifact nếu plugin tạo | Có nếu library release policy yêu cầu |
| `target/*-javadoc.jar` | API docs artifact nếu plugin tạo | Có nếu release policy yêu cầu |
| `target/*.war` | WAR deployment package nếu packaging WAR | Có, theo ứng dụng |
| `target/site/` | Website/report HTML nếu Site lifecycle chạy | Có nếu cần publish site, không phải JAR runtime |

**Không kết luận `target` luôn có đúng một JAR.** Project có classifier, shade/assembly hoặc multi-module có thể tạo nhiều file. Cần biết file nào là **final artifact** và file nào chỉ là intermediate/original.

### 4.2. `mvn clean` xóa gì?

Maven Clean Plugin theo default xóa project build output directory, thường là:

```text
target/
```

Nó **không tự xóa** local repository `~/.m2/repository` và **không xóa** CI artifact đã được upload lên storage riêng.

Nhờ vậy người học có thể chạy `mvn clean verify` để tạo output sạch mà vẫn reuse dependency/plugin downloads trong local repository.

Một ví dụ về ba kết quả khác nhau:

```text
mvn clean:
  target/ bị xóa và sẽ được build lại

~/.m2/repository:
  vẫn còn dependency/plugin caches đã có

CI artifact archive:
  vẫn ở storage CI nếu chưa hết retention/chưa bị xóa
```

### 4.3. Vì sao `target/` không tự đi qua jobs?

GitHub-hosted runners và nhiều GitLab runners có workspace riêng cho từng job. Khi job build kết thúc, **đừng giả định filesystem còn được giữ cho job sau**.

Ngay cả với self-hosted runner dùng lại ổ đĩa, không nên lấy workspace persistence tình cờ làm contract, vì gây stale outputs, race conditions và khó audit. Hãy **upload artifact** hoặc publish package theo cơ chế được hỗ trợ.

## 5. CI cache và CI artifact: cùng lưu file, khác hợp đồng

Theo GitHub Actions và GitLab CI chính thức:

- **Cache:** dùng để tái sử dụng files tốn thời gian để tải/tính lại, cải thiện tốc độ. Cache có thể bị miss, bị evict, không có, hoặc nằm ở namespace khác.
- **Artifact:** dùng để lưu **output của một job** để tải sau khi job kết thúc, chia sẻ giữa jobs/stages hoặc dùng làm evidence.

### 5.1. So sánh tập trung

| Tiêu chí | Cache | CI Artifact |
| --- | --- | --- |
| Nguồn chính | Downloaded dependencies/plugins hoặc intermediate có thể tái sinh | Build output/report/evidence |
| Mục đích | Performance | Handoff, review, retention |
| Tồn tại | Best effort theo key, quota, policy | Theo job/run và retention cấu hình |
| Định danh | Cache key và cache namespace | Workflow/job/run, artifact name/ID |
| Khi mất | Thường tải/tạo lại, build vẫn phải chạy | Job sau có thể **không đủ input**, nên fail |
| Khi quá cũ | Dùng sai dependency hoặc incremental state | Có nguy cơ triển khai nhầm bản nếu không check run/digest |
| Bảo mật | Có nguy cơ cache poisoning/secret leakage | Phải giới hạn download, retention, nội dung nhạy cảm |
| Job sau dùng để deploy | **Không dùng làm nguồn chứng cứ release** | Có thể dùng nếu hash/approval được verify |
| Nên đưa `~/.m2` vào? | Thường có, theo policy | Không |
| Nên đưa final JAR vào? | Không mặc định | **Có** |
| Có phải Maven repository GAV? | Không | Không, trừ khi publish riêng |

**Lưu ý:** một số CI caching features cho phép cache intermediate build outputs. Về mặt tính năng vẫn hợp lệ để tăng tốc, nhưng **không biến cache thành bản bàn giao release**. Một cache entry được restore không thay yêu cầu QA lại code hiện tại.

### 5.2. Cache miss là bình thường; artifact miss là lỗi bàn giao

Kịch bản:

```text
Job build, lần #101:
  Cache miss -> tải JUnit/plugin -> compile/test -> tạo JAR -> upload artifact

Job build, lần #102:
  Cache hit  -> bớt tải JUnit/plugin -> compile/test -> tạo JAR -> upload artifact

Job handoff, lần #102:
  Download artifact của chính lần #102 -> verify SHA-256 -> chạy JAR
```

Khi cache miss, pipeline phải vẫn làm việc nếu remote repository và policy cho phép. Nếu job handoff không tải được **artifact của lần #102**, pipeline nên fail thay vì lục cache để tìm một file có tên tương tự.

### 5.3. Đừng cache cùng path với artifact output

Ví dụ nguy hiểm:

```text
Cache path: target/
Artifact path: target/
```

Một cache từ run trước có thể restore stale JAR; một artifact mới có thể overwrite, và quá trình restore khác nhau theo nền tảng. GitLab docs cảnh báo cache và artifacts cùng path có thể chồng lấn vì cache thường được restore trước artifacts.

**Chính sách dễ kiểm soát hơn:**

```text
Cache:      Maven local repo (.m2/repository)
Build:      mvn clean verify
Artifact:   chỉ JAR + POM + test report/checksum cần bàn giao
```

Nếu muốn cache compiler intermediates để tăng tốc, cần cache key/staleness policy riêng và vẫn bắt buộc QA final output; không trộn chúng với release artifacts.

## 6. Hợp đồng bàn giao tối thiểu: “file nào, từ run nào, đúng bytes nào?”

Một **handoff manifest** cho Java JAR nên trả lời:

1. **Tên artifact:** ví dụ `handoff-demo-1.0.0.jar`.
2. **Maven coordinates:** `org.example:handoff-demo:jar:1.0.0`.
3. **Nguồn:** repository, commit SHA/tag đã checkout.
4. **CI run:** workflow/job/build ID, URL và builder identity.
5. **Quality:** lệnh test, test count, failures/errors/skipped và policy gates.
6. **SHA-256:** digest tính trên **final JAR bytes** sau packaging.
7. **POM:** bản POM được dùng/published; version và dependencies.
8. **Retention:** lưu bao lâu, ai được download, artifact có thể hết hạn không.
9. **Đích:** job tiếp theo, staging repository hoặc registry nào nhận file.
10. **Approval/provenance:** chữ ký, attestation hoặc release approval khi cần.

Không phải mọi PR build cần đầy đủ chữ ký và SBOM; nhưng **final filename + build run identity + test status + digest** là nền tảng mạnh để tránh nhầm bản.

### 6.1. Bộ file bàn giao gợi ý

```text
handoff/
├── handoff-demo-1.0.0.jar
├── pom.xml
├── TEST-org.example.ci.ArtifactAppTest.xml
└── handoff-demo-1.0.0.jar.sha256
```

Đây là **bộ file mẫu**, không phải thứ Maven tự tạo toàn bộ. `pom.xml` được copy vào thư mục bàn giao; checksum được tạo bằng CLI; test XML do Surefire sinh.

Nếu bàn giao **Maven library** với sources/Javadoc classifiers hoặc một WAR/container image, hợp đồng phải thay theo loại artifact. Không hardcode `*.jar` nếu sản phẩm thực là `*.war`, `.zip`, Docker image digest hay POM-only module.

### 6.2. Tính SHA-256 trên JAR chứ không phải ZIP wrapper của CI

GitHub/GitLab có thể nén artifact bundle thành một archive để lưu/tải. Archive bytes, metadata, nén và entry ordering **không nhất thiết giống bytes file JAR bên trong**.

Cách kiểm chứng tốt:

```text
SHA-256(final JAR được tạo ở build job)
                 ==
SHA-256(JAR sau khi download artifact ở job sau)
```

Nếu cần verify chữ ký, kiểm chứng **đúng file JAR/POM** sau khi tải và trusted key/provenance policy, không chỉ tin archive tên đẹp.

## 7. Dự án Java 17 chạy được: cache JUnit nhưng bàn giao application JAR

Lab đơn giản cố ý có **test dependency JUnit** để Maven phải tải thư viện/plug-in, nhưng main application **không cần JUnit ở runtime**. Vì vậy có thể `java -jar` trực tiếp và quan sát rõ cache là input, JAR là output.

### 7.1. Cấu trúc project

```text
handoff-demo/
├── pom.xml
└── src/
    ├── main/java/org/example/ci/ArtifactApp.java
    └── test/java/org/example/ci/ArtifactAppTest.java
```

Yêu cầu: **JDK 17+**, Maven **3.9.x**, Maven Central hoặc approved mirror có thể resolve plugins/dependencies.

### 7.2. `pom.xml` hoàn chỉnh

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>org.example</groupId>
    <artifactId>handoff-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>
    <name>Handoff Demo</name>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <project.build.outputTimestamp>2026-01-01T00:00:00Z</project.build.outputTimestamp>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.4</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-clean-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-resources-plugin</artifactId>
                <version>3.3.1</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.6.1</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.5.1</version>
                <configuration>
                    <archive>
                        <manifest>
                            <mainClass>org.example.ci.ArtifactApp</mainClass>
                        </manifest>
                    </archive>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

**Điểm quan trọng trong POM:**

- `junit-jupiter` có **`test` scope**, dùng để compile/run tests; không cần đóng vào JAR production.
- Compiler Plugin ghim version **3.14.1** và `maven.compiler.release=17`.
- Surefire Plugin **3.6.1** chạy JUnit tests ở phase `test`.
- JAR Plugin **3.5.1** tạo JAR và đặt `Main-Class` để chạy bằng `java -jar`.
- Clean Plugin **3.5.0** xóa `target` khi gọi `clean`; không xóa Maven local repo.
- `project.build.outputTimestamp` giúp ổn định archive timestamps với plugin hỗ trợ, **không tự chứng minh toàn bộ build reproducible**.
- Không có `<distributionManagement>` hay credentials trong POM; demo chỉ **build và handoff**, không upload remote release repository.

### 7.3. `src/main/java/org/example/ci/ArtifactApp.java`

```java
package org.example.ci;

public final class ArtifactApp {
    private ArtifactApp() {
    }

    public static int add(int left, int right) {
        return Math.addExact(left, right);
    }

    public static String message() {
        return "handoff-demo: 2 + 3 = " + add(2, 3);
    }

    public static void main(String[] args) {
        System.out.println(message());
    }
}
```

Main code chỉ dùng `java.base` của JDK 17. `Math.addExact` trả `5` cho `2+3` và báo `ArithmeticException` nếu phép cộng `int` bị overflow; ta kiểm thử cả hai trường hợp.

### 7.4. `src/test/java/org/example/ci/ArtifactAppTest.java`

```java
package org.example.ci;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class ArtifactAppTest {
    @Test
    void addsTwoNumbers() {
        assertEquals(5, ArtifactApp.add(2, 3));
    }

    @Test
    void rejectsOverflow() {
        assertThrows(ArithmeticException.class,
                () -> ArtifactApp.add(Integer.MAX_VALUE, 1));
    }

    @Test
    void producesStableLabel() {
        assertEquals("handoff-demo: 2 + 3 = 5",
                ArtifactApp.message());
    }
}
```

Ba tests cho thấy **test dependency là input của build**. Tests được đặt trong `src/test/java`; các `.class` của chúng ở `target/test-classes` và test XML ở `target/surefire-reports`. Chúng không phải entry point của JAR production.

### 7.5. Chạy project

Trong thư mục chứa POM:

```bash
java -version
mvn -version
mvn -B -ntp clean verify
```

Nếu environment resolve được dependencies và tests PASS, Maven sinh:

```text
target/classes/org/example/ci/ArtifactApp.class
target/test-classes/org/example/ci/ArtifactAppTest.class
target/surefire-reports/TEST-org.example.ci.ArtifactAppTest.xml
target/handoff-demo-1.0.0.jar
```

Phần tổng kết kiểm thử **dự kiến**:

```text
Tests run: 3, Failures: 0, Errors: 0, Skipped: 0
```

Không coi dòng trên là log thật cho đến khi đã chạy Maven; nó là **kết quả kỳ vọng từ ba JUnit tests đã viết**. Job CI phải kiểm tra test runner status và số tests thực thi.

### 7.6. Chạy đúng JAR đã tạo

```bash
java -jar target/handoff-demo-1.0.0.jar
```

**Stdout chính xác từ `ArtifactApp.main`:**

```text
handoff-demo: 2 + 3 = 5
```

Không cần JUnit JAR ở runtime, bởi application không tham chiếu JUnit. Nếu bạn đổi app sang dùng thư viện bên ngoài ở runtime, một **thin JAR** sẽ cần classpath/dependency packaging phù hợp; cache `~/.m2` trên máy build **không** khiến một JAR bất kỳ chạy độc lập trên máy khác.

### 7.7. Soi JAR và test output

```bash
jar tf target/handoff-demo-1.0.0.jar
```

Kỳ vọng có:

```text
META-INF/MANIFEST.MF
org/example/ci/ArtifactApp.class
```

Với một JDK 17 đầy đủ, `jar` command có sẵn. Danh sách `jar tf` có thể có thêm Maven metadata; không đòi đầu ra chỉ đúng hai dòng.

### 7.8. Tạo bộ bàn giao

Trên Linux/macOS có `cp` và GNU/coreutils `sha256sum`:

```bash
mkdir -p handoff
cp target/handoff-demo-1.0.0.jar handoff/
cp pom.xml handoff/pom.xml
cp target/surefire-reports/TEST-org.example.ci.ArtifactAppTest.xml handoff/
(
  cd handoff
  sha256sum handoff-demo-1.0.0.jar > handoff-demo-1.0.0.jar.sha256
)
```

**Đây là phép copy cụ thể** và tạo checksum sau build, không copy toàn bộ `target` hoặc `.m2`. Với macOS mặc định không có `sha256sum`, có thể dùng:

```bash
shasum -a 256 handoff/handoff-demo-1.0.0.jar
```

Nếu muốn tạo file checksum theo format GNU `sha256sum -c`, hãy dùng công cụ phù hợp hoặc script có format kiểm chứng tương ứng; đừng giả định `shasum`/`sha256sum` cùng được cài trên mọi OS.

### 7.9. Windows PowerShell tạo handoff

Từ root project:

```powershell
New-Item -ItemType Directory -Force -Path .\handoff | Out-Null
Copy-Item .\target\handoff-demo-1.0.0.jar .\handoff\
Copy-Item .\pom.xml .\handoff\pom.xml
Copy-Item .\target\surefire-reports\TEST-org.example.ci.ArtifactAppTest.xml .\handoff\

$hash = (Get-FileHash -Algorithm SHA256 `
    .\handoff\handoff-demo-1.0.0.jar).Hash.ToLowerInvariant()

"$hash  handoff-demo-1.0.0.jar" |
    Set-Content -Encoding Ascii .\handoff\handoff-demo-1.0.0.jar.sha256
```

Dòng checksum tạo ở đây tương thích về nội dung với dạng `sha256sum` phổ biến: 64 ký tự hex, hai dấu cách và tên file. Trên Windows có thể kiểm tra lại bằng `Get-FileHash` và so giá trị, không cần cài GNU tools.

**Không copy `~/.m2/repository` vào `handoff/`.** Thư mục ấy là cache thư viện và plugins, không phải một phần contract triển khai JAR này.

## 8. GitHub Actions: `setup-java cache: maven` khác `upload-artifact`

Ví dụ workflow dưới đây **cố ý tách thành hai jobs** để thấy rõ ranh giới. Nó chỉ chạy trên push vào `main` hoặc khi kích hoạt thủ công; không cần publisher secret.

File `.github/workflows/java-handoff.yml`:

```yaml
name: Maven cache versus build artifact

on:
  push:
    branches: [main]
  workflow_dispatch:

permissions:
  contents: read

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Set up JDK 17 and Maven cache
        uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'
          cache: maven

      - name: Build and run tests
        run: mvn -B -ntp clean verify

      - name: Prepare exact handoff files
        run: |
          mkdir -p handoff
          cp target/handoff-demo-1.0.0.jar handoff/
          cp pom.xml handoff/
          cp target/surefire-reports/TEST-org.example.ci.ArtifactAppTest.xml handoff/
          (cd handoff && sha256sum handoff-demo-1.0.0.jar > handoff-demo-1.0.0.jar.sha256)

      - name: Upload tested build output
        uses: actions/upload-artifact@v4
        with:
          name: java17-package-${{ github.run_id }}
          path: handoff/
          if-no-files-found: error
          retention-days: 14

  inspect-handoff:
    needs: build
    runs-on: ubuntu-latest
    steps:
      - name: Set up JDK for the consumer job
        uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'

      - name: Download handoff from this run
        uses: actions/download-artifact@v4
        with:
          name: java17-package-${{ github.run_id }}
          path: handoff/

      - name: Verify bytes and execute
        run: |
          cd handoff
          sha256sum -c handoff-demo-1.0.0.jar.sha256
          java -jar handoff-demo-1.0.0.jar
```

### 8.1. Từng phần làm gì?

- `actions/setup-java@v4` với `cache: maven` dùng tính năng Maven dependency caching của GitHub; về cơ bản giúp reuse local Maven repository downloads.
- `mvn -B -ntp clean verify` **vẫn chạy build và tests** dù cache hit.
- `handoff/` chỉ chứa file được chọn làm output và evidence.
- `actions/upload-artifact@v4` lưu các file ấy dưới một **artifact name gắn run ID**.
- `if-no-files-found: error` tránh trường hợp glob/path sai nhưng step upload vẫn “xanh”.
- Job `inspect-handoff` chạy trong **runner/job riêng**, không thấy `target/` của job `build`.
- `actions/download-artifact@v4` tải output được đặt tên từ **chính workflow run hiện tại**.
- `sha256sum -c` kiểm tra **JAR sau khi download** khớp checksum đã ghi lúc build.
- `java -jar` chạy file đã bàn giao, không chạy lại Maven compile.

### 8.2. Ranh giới chứng minh của ví dụ

Đoạn workflow dùng `actions/checkout@v4`, `setup-java@v4` và `upload/download-artifact@v4` vì dễ học. Với production có yêu cầu chống action substitution, nên pin GitHub Actions theo **verified commit SHAs**, kiểm soát branch protections và action allowlist.

**Checksum đi kèm JAR trong cùng artifact bundle kiểm tra được sự thay đổi do truyền/giải nén hoặc nhầm file**, nhưng nếu một attacker sửa được **cả JAR lẫn checksum** ở nguồn thì hai file có thể vẫn khớp. Release cần digest kỳ vọng/attestation từ nguồn đáng tin cậy và approval/provenance policy.

`retention-days: 14` là lựa chọn **minh họa**; giới hạn retention thực tế phụ thuộc repository/org/enterprise settings. CI artifact có thể hết hạn, nên package dùng lâu dài cần publish vào kho có retention phù hợp.

### 8.3. Nếu workflow chỉ cache Maven mà không upload artifact?

Ví dụ:

```yaml
- uses: actions/setup-java@v4
  with:
    distribution: temurin
    java-version: '17'
    cache: maven
- run: mvn clean verify
```

có thể giảm download, nhưng **không cung cấp file bàn giao cho job mới**. Nếu người kiểm thử tải artifacts qua GitHub UI, phần upload vẫn phải được cấu hình. GitHub docs phân biệt rõ *dependency caching* với *workflow artifacts*.

### 8.4. Nếu artifact thiếu khi tải?

Kiểm tra:

1. `build` job có PASS không.
2. Step `Prepare exact handoff files` có tạo đủ files không.
3. `upload-artifact` có `if-no-files-found: error` không.
4. Artifact name có đúng run ID không.
5. Job download dùng `needs: build` không.
6. Artifact còn trong retention/quyền truy cập không.
7. File được download vào `handoff/` hay thư mục khác.
8. SHA-256 sau tải có khớp không.

**Không tự chuyển sang cache hoặc một JAR ở runner cũ** khi artifact bàn giao thiếu.

## 9. GitLab CI/CD: `cache:` và `artifacts:` là hai cấu hình riêng

Ví dụ `.gitlab-ci.yml` cho pipeline từ **default branch đã được review**. Cache Maven đặt ở path **bên trong workspace** vì GitLab cache paths phải nằm trong project directory:

```yaml
stages:
  - build
  - inspect

build:
  image: maven:3.9-eclipse-temurin-17
  stage: build
  rules:
    - if: '$CI_COMMIT_BRANCH == $CI_DEFAULT_BRANCH'
  cache:
    key:
      files:
        - pom.xml
    paths:
      - .m2/repository/
    policy: pull-push
  script:
    - mvn -B -ntp "-Dmaven.repo.local=$CI_PROJECT_DIR/.m2/repository" clean verify
    - mkdir -p handoff
    - cp target/handoff-demo-1.0.0.jar handoff/
    - cp pom.xml handoff/
    - cp target/surefire-reports/TEST-org.example.ci.ArtifactAppTest.xml handoff/
    - cd handoff && sha256sum handoff-demo-1.0.0.jar > handoff-demo-1.0.0.jar.sha256
  artifacts:
    when: on_success
    paths:
      - handoff/
    expire_in: 14 days

inspect:
  image: eclipse-temurin:17-jdk
  stage: inspect
  needs:
    - job: build
      artifacts: true
  rules:
    - if: '$CI_COMMIT_BRANCH == $CI_DEFAULT_BRANCH'
  script:
    - cd handoff
    - sha256sum -c handoff-demo-1.0.0.jar.sha256
    - java -jar handoff-demo-1.0.0.jar
```

### 9.1. Vì sao dùng `.m2/repository` thay cho `~/.m2/repository`?

GitLab CI cache paths được khai báo **relative với project directory**. Vì thế Maven được gọi với:

```bash
"-Dmaven.repo.local=$CI_PROJECT_DIR/.m2/repository"
```

để các files Maven tải đi vào `.m2/repository` dưới checkout, nơi `cache.paths` có thể lưu lại. Nếu Maven vẫn tải vào HOME trong khi GitLab cache `.m2/` của project, cache sẽ **không chứa đúng dữ liệu cần thiết**.

Ví dụ **không dùng credential file** hay `settings.xml` chứa secrets làm cache. `.m2/repository` chỉ chứa Maven artifacts/metadata cho build trong bài này.

### 9.2. Vì sao `cache:key:files` dựa vào `pom.xml`?

Khi POM đổi, cache key có thể đổi. Điều này tránh dùng chung một cache key cho mọi cấu hình mã nguồn, nhưng **không bảo đảm mọi dependency input khác cũng đã được khóa**:

- Parent/BOM POMs có thể đổi nếu repository cho overwrite.
- Multi-module project còn nhiều `pom.xml`.
- SNAPSHOT/range dependencies phụ thuộc metadata.
- Maven `settings.xml`, mirror, JDK hoặc plugin configs có thể khác.

Với mono-repo hoặc multi-module, nên thiết kế cache keys từ **đúng các build descriptor files liên quan**, Maven/JDK/runner context và trust boundary, hoặc dùng chiến lược tách cache theo branch/project.

### 9.3. Vì sao artifact là hợp đồng giữa hai jobs?

`needs: [job: build, artifacts: true]` yêu cầu job `inspect` tải artifacts do job `build` tạo, dựa trên đúng pipeline dependency. CI artifact được giải nén vào workspace của `inspect`, nên có `handoff/` để verify và chạy.

`cache:` không được dùng làm lối thay thế để truyền JAR qua stages; GitLab docs khuyến nghị dùng **artifacts** cho kết quả trung gian giữa jobs.

### 9.4. Vì sao ví dụ chỉ cho trusted default branch?

Một cache `pull-push` có thể nhận dữ liệu từ job chạy code không tin cậy; nếu runner/cache sharing policy yếu, cache poisoning có thể khiến trusted builds dùng bytes bị thay. Ví dụ giới hạn bằng `rules` để tránh tự đưa untrusted merge request vào job có quyền cập nhật cache cùng namespace.

Trong CI thực, còn cần xem **protected vs unprotected branches**, runner isolation, artifact sharing settings và quyền publish. Default branch restriction **không tự đủ** nếu users vẫn có khả năng thay workflow/cache key không được review.

### 9.5. `artifacts: when: on_success` có tác dụng gì?

Nó chỉ upload handoff khi **build job thành công**. Đừng publish một JAR từ build thất bại chỉ vì `artifacts: when: always` mang toàn bộ `target/` từ workspace chưa sạch.

Nếu cần lưu logs/test reports khi build fail, tạo **artifact báo lỗi riêng**, giới hạn đúng paths và không cho deploy job tiêu thụ package chưa PASS. Một pipeline có thể lưu test report để debug nhưng vẫn chặn release.

## 10. Khi nào dùng Maven `install` hoặc `deploy` thay vì CI workflow artifact?

Ba lệnh này có ý nghĩa khác nhau:

```bash
mvn package
mvn install
mvn deploy
```

- `package` tạo artifact trong project output, thường `target/...jar`.
- `install` đi qua build lifecycle và cài **artifact/POM vào Maven local repository** để các project local khác resolve như một dependency.
- `deploy` đi qua lifecycle và publish tới **remote Maven repository** theo `distributionManagement`/publisher plugin phù hợp.

### 10.1. `mvn install` không phải bàn giao cho máy khác

Sau:

```bash
mvn -B clean install
```

bạn có thể thấy file do chính dự án tạo trong local repository:

```text
~/.m2/repository/org/example/handoff-demo/1.0.0/
    handoff-demo-1.0.0.jar
    handoff-demo-1.0.0.pom
```

**Đây vẫn là local repository của máy hiện tại.** Job ở runner khác không tự có bản này. Một developer `mvn install` rồi consumer ở máy đó build thành công không chứng minh version đã có trong remote repository.

### 10.2. `mvn deploy` là xuất bản theo GAV

Một **fragment minh họa** cho POM release:

```xml
<distributionManagement>
    <repository>
        <id>approved-releases</id>
        <url>https://repo.example.invalid/maven/releases</url>
    </repository>
</distributionManagement>
```

`.invalid` là URL cố ý không hoạt động; không chạy deploy thật bằng fragment này. Remote repository dùng credentials ở `settings.xml` hoặc provider-specific flow, không đưa tokens trong POM.

**Khi nào nên dùng?**

- **CI artifact:** cần JAR cho bước test/download/deploy trong workflow hoặc lưu logs/report ngắn hạn.
- **Maven repository:** cần library/versioned artifacts cho các teams/projects khác resolve qua GAV lâu dài.
- **Container registry:** ứng dụng được đóng OCI image, deployment lấy **image digest** làm artifact thực; có thể vẫn lưu JAR evidence riêng.

Nếu release pipeline dùng CI artifact trước khi deploy, nên **promote chính bytes đã test** hoặc verify SHA-256 giữa build job và deploy job, không build lại rồi suy hai JAR giống nhau.

### 10.3. Maven artifact classifier không phải CI archive name

Trong Maven:

```text
org.example:handoff-demo:jar:1.0.0
org.example:handoff-demo:jar:sources:1.0.0
```

có thể phân biệt main artifact và source classifier (nếu nguồn thực được attach). Tên `java17-package-123456` trong GitHub Actions chỉ là **CI artifact name**, không phải Maven groupId/artifactId/version.

Một CI archive có thể chứa nhiều Maven artifacts, nhưng không thay thế published POM, metadata, classifier và repository layout dùng cho dependency resolution.

## 11. Điều gì phải được giữ lại khi bàn giao?

Không phải cứ nén `target/` là đủ. Tùy loại sản phẩm:

| Artifact bàn giao | Nên có | Không tự ý thêm |
| --- | --- | --- |
| Executable JAR | Final JAR + SHA-256 + commit/build ID + test result | Local `.m2` |
| Library JAR | Main JAR, published POM, sources/Javadoc nếu policy, signature/checksum | Test classes/metadata private |
| WAR | Final WAR + test evidence + deployment config **không có secrets** | IDE caches hoặc workspace state |
| Multi-module release | Mỗi module GAV + artifact digest + parent POM/BOM refs | Một JAR duy nhất đại diện mọi module |
| CI debug bundle | Relevant logs, Surefire XML, diagnostics đã redact | Passwords, tokens, personal settings |
| Static site | `target/site` assets/HTML theo website policy | Maven caches và files không dùng |
| Docker/OCI image | Image digest + SBOM/provenance + deployment refs | Chỉ image tag không kèm digest |

### 11.1. Không upload toàn bộ `target/` nếu không biết nó chứa gì

`target/` có thể chứa:

- Debug symbols, build logs, generated code và temporary files.
- Test data có credentials hoặc thông tin nhạy cảm.
- Dependency copies hoặc original unshaded JAR.
- Classifiers, samples hoặc artifacts không được phê duyệt.
- Files cũ nếu không có `clean`.

Chỉ upload đúng những paths đã được review; dùng `mvn clean verify` và kiểm tra file tồn tại/size/digest. Đừng vô tình public test fixtures/secrets.

### 11.2. Kiểm tra file cuối trước upload

Trên Linux:

```bash
test -s target/handoff-demo-1.0.0.jar
jar tf target/handoff-demo-1.0.0.jar
sha256sum target/handoff-demo-1.0.0.jar
```

- `test -s` fail khi file không tồn tại hoặc rỗng.
- `jar tf` đọc archive structure.
- `sha256sum` cho digest để đối chiếu sau bàn giao.

**Lưu ý:** `jar tf` và SHA-256 không tự chứng minh chất lượng code. Tests và release policy cần là các gates riêng.

### 11.3. Đối chiếu SHA-256 sau download

Trong job consumer có GNU coreutils:

```bash
cd handoff
sha256sum -c handoff-demo-1.0.0.jar.sha256
```

Kết quả thành công thường có dạng:

```text
handoff-demo-1.0.0.jar: OK
```

Đây là output **dự kiến** của `sha256sum -c` khi checksum khớp; đường dẫn/locale/tool version có thể làm cách hiển thị khác. Nếu file/hash không khớp, **chặn deploy**.

### 11.4. POM và test report không phải bằng chứng tuyệt đối

Một POM/CI test XML trong cùng artifact archive có thể bị sửa nếu người có quyền upload archive bị chiếm tài khoản. Trong release quan trọng, cần kết nối:

```text
Source Git commit
    -> trusted CI run
    -> test results
    -> final artifact digest
    -> signature/provenance attestation
    -> approved deploy target
```

Không chỉ tin filename `release-latest.jar`, `BUILD SUCCESS` hoặc JAR được tải từ cache.

## 12. Mấu chốt về cache key, retention và xóa dữ liệu

### 12.1. Cache key nên dựa vào cái gì?

Một cache key có thể kết hợp:

```text
OS + JDK major + Maven distribution
+ pom.xml (và các module POMs)
+ dependency lock/approved resolved inputs nếu có
+ repository profile/trust context
```

Đừng đưa **secret value** trực tiếp vào key; keys có thể bị lộ trong logs/metadata. Đừng dùng một cache key toàn cục cho private/protected và untrusted PR workflows mà không kiểm tra isolation.

**Không cần chạm cache để đổi artifact name.** Cache key và CI artifact ID giải quyết hai vấn đề khác nhau.

### 12.2. Cache invalidation không sửa dependency resolution policy

Ví dụ POM có:

```xml
<version>2.0.0-SNAPSHOT</version>
```

Thay cache key hay xóa cache có thể khiến Maven tải **SNAPSHOT mới**, chứ không tái hiện chính xác build cũ. Version ranges cũng có thể resolve khác sau khi repository metadata cập nhật.

Để release tái lập cần pin versions, kiểm soát mirrors/Repositories, tránh mutable releases và lưu artifact input digests. Cache chỉ làm quá trình tải nhanh hay chậm.

### 12.3. Cache retention khác artifact retention

Cache có thể bị evict vì quota/LRU/TTL và không nên là nguồn phục hồi release. CI artifacts cũng có retention, thường có thể cấu hình nhưng không phải kho lưu trữ vĩnh viễn.

Đối với releases cần truy vết dài hạn:

- Publish Maven artifact vào approved immutable repository.
- Lưu release provenance/test evidence đủ thời gian theo SLA.
- Đối chiếu SHA-256 của artifact đã deploy.
- Có backup/retention policy độc lập với ephemeral runner cache.

### 12.4. `mvn clean` không xóa cache; dọn cache không được làm mất release artifact

Nếu muốn điều tra dependency cache, dùng repo tách biệt thay vì xóa bừa:

```bash
mvn -B -Dmaven.repo.local=/tmp/m2-cleanroom clean verify
```

Bài này dùng local path ví dụ trên Unix. Nó giúp quan sát lần tải mới mà không phá HOME Maven cache của developer. Khi cần dọn chọn lọc, có các goals của Maven Dependency Plugin, nhưng phải hiểu scope trước khi purge.

**Không dùng `rm -rf ~/.m2/repository` như phản xạ đầu tiên** và không coi việc cache bị xóa là “mất artifact phát hành” nếu release đã được lưu đúng nơi.

## 13. IDE: vì sao build/run trong IDE khác `mvn package`?

IDE như IntelliJ IDEA, Eclipse/m2e hoặc VS Code Java có thể:

- Import Maven POM và resolve dependencies qua local repository.
- Dùng compiler/incremental build của IDE hoặc delegate build cho Maven.
- Tạo output ở `out/`, `bin/` hoặc `target/classes` tùy IDE/config.
- Chạy application từ classpath của IDE với dependencies đã tải.
- Chạy JUnit qua IDE test runner.
- Không nhất thiết chạy `maven-jar-plugin` để tạo final JAR.

Vì thế **“Run trong IDE thành công”** chưa chứng minh:

```text
target/handoff-demo-1.0.0.jar
```

đã tồn tại hoặc chạy được ở máy sạch.

### 13.1. Ba phép thử nên tách

1. **IDE run:** tiện debug code, classpath được IDE quản lý.
2. **Maven CLI `clean verify`:** chuẩn hóa lifecycle, plugins, tests và packaged output.
3. **Artifact handoff test:** download file thật sang môi trường khác, verify checksum và chạy JAR/WAR/container.

Một số IDE có nút “Build Artifact” riêng tạo JAR với cấu hình khác POM; nếu CI contract dùng Maven thì phải lấy đúng output của Maven, không dùng file mà IDE xuất trong thư mục khác chỉ vì tên giống.

### 13.2. “Invalidate caches” trong IDE khác xóa Maven cache

IDE có indexes/workspace caches cho code analysis, inspections và navigation. Xóa IDE index **không nhất thiết** xóa Maven `~/.m2/repository`; và xóa Maven local repo **không có nghĩa** IDE index sẽ tự đồng bộ ngay.

Khi gặp lỗi dependency:

- Xem IDE đang dùng đúng `settings.xml`, JDK và Maven distribution chưa.
- So `mvn -version` với cấu hình IDE.
- Reimport/sync Maven model đúng cách.
- Kiểm tra repository mirror/auth và versions.
- Nếu cần, thử Maven CLI trong workspace sạch.

**Không chuyển artifact cho CI bằng cách copy IDE cache directory.**

## 14. Multi-module Maven: bàn giao không chỉ một JAR ở root

Ví dụ reactor:

```text
platform-parent/       (packaging=pom)
├── common-lib/        (packaging=jar)
├── service-api/        (packaging=jar)
└── web-app/            (packaging=war)
```

`mvn clean verify` từ root có thể sinh:

```text
common-lib/target/common-lib-1.0.0.jar
service-api/target/service-api-1.0.0.jar
web-app/target/web-app-1.0.0.war
```

Root `pom` module có thể không có `root/target/*.jar`. **Không viết CI upload glob `target/*.jar` ở root và kết luận toàn bộ reactor đã bàn giao.**

### 14.1. Xác định tập artifacts cần thiết

- **Library release:** JAR/POM của từng module được publish với GAV chính xác.
- **Deployable application:** có thể chỉ bàn giao WAR/boot JAR của ứng dụng cuối, nhưng cần provenance và dependency inventory.
- **Integration-test stage:** có thể cần JAR của modules phụ trợ, config files và test reports.
- **Parent/BOM artifacts:** Maven POM cũng là publishable artifact dù không sinh JAR.

Tạo release manifest liệt kê từng file/GAV/digest. Nếu một file thiếu, fail job; không dùng wildcard quá rộng làm upload “có vài JAR là PASS”.

### 14.2. `mvn install` có thể giúp local reactor, không thay distribution contract

Một reactor nhiều modules thường dùng Maven dependency resolution giữa modules, và các team có thể chạy `mvn install` để cache module artifacts local. Nhưng job khác/consumer khác vẫn cần **CI artifacts hoặc remote Maven repository** chứa đúng coordinates và bytes.

Nếu dùng `-pl`/`-am` để build subset, phải xác định đúng modules được bao gồm; đừng kỳ vọng root `target` tự gom mọi sản phẩm.

### 14.3. Shade/Assembly/Spring Boot repackage

Một project có thể có:

```text
target/original-app.jar
target/app.jar
target/app-exec.jar
```

hoặc file đã shaded/repackaged mang tên khác. File nào là **final deliverable** phải được xác định theo plugin config và tests/deployment process, không chỉ bằng `find target -name '*.jar'` rồi chọn file đầu.

**Tính digest và ký file cuối cùng**, sau đó deploy đúng bytes ấy. Một JAR trung gian trong `target/` không nên tự trở thành artifact production vì nó có tên giống.

## 15. Quy trình hai job để chứng minh bàn giao thực sự

Một cách kiểm thử không phụ thuộc CI provider:

```text
Job A (builder):
  1. Checkout đúng Git commit
  2. Setup JDK/Maven
  3. Restore dependency cache nếu có
  4. mvn clean verify, kiểm tra 3 tests PASS
  5. Chọn final JAR, tạo checksum
  6. Upload handoff artifact

Job B (consumer):
  1. Bắt đầu với workspace/runner riêng, không dựa cache builder
  2. Download artifact từ Job A của cùng workflow run
  3. Kiểm tra file name/version/size và SHA-256
  4. Đọc POM/evidence/test summary nếu policy cần
  5. Chạy java -jar hoặc integration test/smoke test
  6. Cho phép promotion/deploy chỉ khi mọi gate PASS
```

Nếu job B vẫn thành công khi builder cache bị xóa, đó là tín hiệu tốt: **đã tách đúng artifact handoff khỏi dependency cache**. Tuy nhiên job B cần network/runner JDK để chạy tests/smoke tests, tùy trường hợp.

### 15.1. Không build lại âm thầm giữa hai jobs

Thiết kế rủi ro:

```text
Job A: mvn clean verify -> JAR A -> test PASS
Job B: mvn clean package -> JAR B -> deploy
```

JAR B có thể khác A nếu timestamp, SNAPSHOT, plugin, JDK hoặc build inputs thay đổi. Nếu bắt buộc rebuild, phải so artifact digests và giải thích differences; nếu không, hãy **promote file A**.

### 15.2. Cache chỉ là input; artifact là output cần gắn commit/run

Một dashboard release đúng nên có:

```text
sourceCommit = full Git object ID
mavenGav = org.example:handoff-demo:jar:1.0.0
buildRun = CI run/job ID
toolchain = JDK/Maven build image
tests = 3 executed, 0 failed, 0 errors, 0 skipped (nếu thực tế đúng)
artifactSha256 = hash thực của JAR
artifactLocation = CI artifact URL hoặc registry coordinates
deployment = environment + verified digest
```

Tất cả values trong ví dụ là **fields để lưu**, không được tự bịa run ID/hash. Build script phải lấy chúng từ CI/Git/file thực.

## 16. An toàn bảo mật khi lưu cache và artifacts

### 16.1. Không đưa secrets vào cache

Maven `settings.xml` có thể chứa credentials cho private repository. Nếu cache path quá rộng:

```text
~/.m2/
```

nó có thể vô tình lưu cả `settings.xml`, `settings-security.xml`, server tokens hoặc files khác trong HOME Maven directory.

**Chỉ cache `.m2/repository` khi phù hợp**; vẫn rà soát có private artifacts/sensitive metadata không. Protected vs untrusted branches có security boundary riêng; không cho fork PR đọc cache chứa private dependencies nếu policy cấm.

### 16.2. Cache poisoning

Cache có thể bị poison khi untrusted workflow được phép ghi bytes để trusted release job restore. Điều này có thể khiến Maven Resolver/plugins dùng dữ liệu không đáng tin dù `pom.xml` không đổi.

Các biện pháp:

- Tách caches theo trust level/branch/project.
- Không cho untrusted PR cập nhật cache được trusted release dùng.
- Pin plugin/dependency versions và approved repositories.
- Validate checksums và provenance theo policy.
- Dùng runners/containers cô lập.
- Xóa cache nghi ngờ và kiểm tra lại từ approved source.
- Không coi cache được restore là “đã QA”.

### 16.3. CI artifacts cũng cần quyền và retention

Một CI artifact có thể chứa test logs, stack traces, internal URLs, config hoặc dữ liệu test. Vì vậy:

- Chỉ upload những file được phê duyệt.
- Không để private token trong compiled resources hoặc logs.
- Cấu hình ai được download.
- Định nghĩa retention theo nhu cầu audit.
- Không dùng một public artifact archive làm nơi lưu `settings.xml` thật.
- Với binary release quan trọng, verify signature/attestation và repository provenance.

### 16.4. Checksums trong cùng bundle chưa đủ để chống tamper có chủ đích

Khi bundle chứa cả `jar` và `.sha256`, consumer so được file đã download có khớp record trong bundle. Nhưng một người sửa được **cả hai** vẫn có thể tạo cặp nhất quán.

Đối với phát hành nghiêm ngặt, xác minh digest kỳ vọng từ **trusted CI attestation/approval** hoặc cryptographic signature đúng identity. `sha256sum -c` là bước integrity hữu ích, không phải toàn bộ supply-chain verification.

## 17. Xử lý lỗi thường gặp

| Triệu chứng | Nguyên nhân khả dĩ | Cách xử lý |
| --- | --- | --- |
| IDE chạy được nhưng thiếu JAR | Chỉ run/build classes trong IDE | `mvn clean package` hoặc `verify` |
| JUnit dependency có trong `.m2`, JAR không thấy | `.m2` chứa input, không phải target output | Kiểm tra `target/` |
| Job B không tìm thấy JAR | Không upload/download artifact | Thêm CI artifact handoff |
| Cache hit nhưng không có file triển khai | Cache không lưu deliverable | Upload đúng final artifact |
| Cache miss nên build chậm | Cache evicted/key mismatch | Tải lại dependencies, đừng skip tests |
| GitHub upload thành công nhưng bundle rỗng | Path sai hoặc không cấu hình fail | `if-no-files-found: error` |
| GitLab cache `.m2/` trống | Maven đang tải vào HOME | Dùng `-Dmaven.repo.local` trỏ project |
| GitLab job sau không thấy `handoff/` | Chưa có `artifacts:` hoặc `needs:artifacts` | Cấu hình truyền artifact |
| Job B lấy nhầm artifact run cũ | Dùng name/URL không gắn run | Handoff theo current run/needs |
| JAR cùng tên nhưng hash khác | Rebuild/nondeterministic inputs | Dừng deploy, so digests |
| `mvn clean` xóa JAR | `target/` là build output | Build lại hoặc download CI artifact |
| `mvn clean` làm mất cache? | Nhầm target với local repo | `~/.m2` vẫn có, kiểm tra location |
| `mvn -o` fail | Thiếu plugin/dependency trong cache | Prefetch, hoặc build online |
| `mvn -U` lấy dependency khác | SNAPSHOT/metadata thay | Pin release inputs, so graph |
| JAR `java -jar` lỗi `no main manifest attribute` | Chưa cấu hình Main-Class | Cấu hình JAR Plugin |
| `java -jar` lỗi `ClassNotFound` | Thin JAR cần runtime deps | Đóng dependency/runtimes đúng cách |
| `jar tf` có `.class` nhưng test XML thiếu | Surefire chưa chạy/bị skip | Kiểm tra test phase/logs |
| Copy cả `target/` làm bundle quá lớn | Upload intermediates | Chọn files cần bàn giao |
| Release artifact hết hạn sau 14 ngày | CI artifact retention | Publish immutable registry/long-term store |
| `mvn install` xong runner B không resolve được | Install chỉ local repo A | Remote registry hoặc artifact handoff |
| Maven deployed artifact khác artifact QA | Rebuild khi deploy | Promote exact tested bytes |
| Multi-module chỉ upload root `target/*.jar` | Outputs nằm ở modules con | Liệt kê đúng module paths |
| Có cả `original-*.jar` và final JAR | Shade/Boot/Assembly thay output | Chọn final deployable |
| Checksum valid với file đã bị đổi | JAR và checksum cùng bị sửa | Trusted digest/signature/attestation |
| Runner cache chứa token private repo | Cache scope quá rộng | Thu hồi token, cache lại paths đúng |
| PR workflow có thể poison cache | Không tách trust boundary | Bảo vệ cache keys/branches/runner |
| Tests failed nhưng CI vẫn upload JAR | `when: always`/step condition sai | Chỉ publish package khi verify PASS |
| `pom.xml` upload không khớp JAR | Rebuild/version drift | Gắn source commit, GAV, hash |
| Artifact gắn tên “latest” | Tên dễ tái sử dụng/nhầm | Gắn run ID/version/digest |
| Report Surefire từ build trước | Không clean hoặc cache `target` | `mvn clean verify`, kiểm tra XML mới |

### 17.1. Runbook điều tra thiếu file bàn giao

1. Xác định job **sinh** file và lifecycle command thực.
2. Kiểm tra `mvn -version`, JDK, POM version và packaging.
3. Đọc logs compile/test/package, xác nhận build PASS.
4. Liệt kê `target/` trong **chính job builder**.
5. Kiểm tra upload path/glob, file size và artifact name.
6. Kiểm tra CI artifact storage, retention và download permission.
7. Kiểm tra consumer job thật sự download artifact của đúng run.
8. So checksum file sau download.
9. Nếu hash mismatch, dừng promotion và điều tra.
10. Nếu cần Maven library cho các dự án khác, kiểm tra remote Maven GAV registry riêng.

## 18. Những quyết định thiết kế nên thống nhất trong đội

| Quyết định | Hướng khuyến nghị |
| --- | --- |
| Build entry point | Maven CLI + POM, không phụ thuộc IDE-specific output |
| Cache | Chỉ dependencies/plugins, đường dẫn rõ, tách trust levels |
| Cache key | Build descriptors + OS/JDK/profile context theo nhu cầu |
| CI package artifact | Final file(s) và checksums; không upload toàn bộ `.m2` |
| Inter-job transfer | `upload/download-artifact`, GitLab `artifacts/needs` |
| Test evidence | Surefire XML mới từ cùng run, test count và status |
| Delivery identity | Maven GAV + CI run + Git SHA + artifact digest |
| Retention | CI short-term; immutable repository cho release dài hạn |
| Publisher | Chỉ job protected; không trao token cho PR builds |
| Rebuild | Tránh khi promote; nếu có phải verify digest equality |
| Multi-module | Liệt kê đúng artifacts từng module, không glob nhầm root |
| Incident response | Giữ logs/evidence, so hashes, isolate corrupted cache |

### 18.1. Khi nào **không** cần cache?

- Build nhỏ với ít dependencies và network tốt.
- Cache overhead/lưu trữ vượt lợi ích.
- Reproducibility/security policy yêu cầu mỗi build lấy fresh inputs từ một approved immutable repository.
- Workflows có source không tin cậy và cache sharing khó cách ly.

**Không cache vẫn có thể bàn giao tốt** nếu artifact upload/verification được thiết kế đúng. Ngược lại, caching rất tốt mà thiếu artifact retention thì vẫn bàn giao kém.

### 18.2. Khi nào không cần CI artifact giữa jobs?

Nếu chỉ có **một job** build/test/deploy và file vẫn ở cùng workspace, có thể dùng `target/` trực tiếp trong job ấy. Tuy vậy release evidence/rollback thường vẫn cần **lưu binary cuối ở kho có kiểm soát**.

Với một **Maven library được publish trực tiếp lên repository** có thể không cần giữ thêm CI artifact ZIP, nếu repository immutability, test provenance và retention đã đáp ứng yêu cầu. Hai đường lưu này bổ sung nhau, không phải luôn bắt buộc đồng thời.

## 19. Câu hỏi tự kiểm tra

**1.** `~/.m2/repository` dùng chủ yếu cho gì?  
**Đáp án:** Local Maven repository cho dependencies, plugins, metadata và artifacts cài bằng `mvn install`.

**2.** `target/` chứa gì?  
**Đáp án:** Outputs/intermediates của lần Maven build trong workspace.

**3.** Cache hit có chứng minh tests PASS không?  
**Đáp án:** Không, cần chạy/kiểm tra test runner.

**4.** `mvn clean` có xóa `~/.m2/repository` không?  
**Đáp án:** Không mặc định.

**5.** `mvn clean` có thể làm mất JAR dưới `target/` không?  
**Đáp án:** Có, vì nó làm sạch build outputs.

**6.** `mvn -o` có đảm bảo build tái lập không?  
**Đáp án:** Không, nó chỉ dùng local repository có sẵn.

**7.** `dependency:go-offline` có tạo application JAR không?  
**Đáp án:** Không; mục đích là pre-resolve build inputs.

**8.** `mvn install` có đẩy artifact tới Maven Central không?  
**Đáp án:** Không, nó cài vào local repository.

**9.** `mvn deploy` có phải GitHub `upload-artifact` không?  
**Đáp án:** Không; Maven deploy publish tới Maven repository, upload-artifact lưu CI workflow output.

**10.** Job mới có tự thấy `target/` của runner trước không?  
**Đáp án:** Không nên giả định; dùng CI artifact transfer.

**11.** Vì sao không cache `target/` làm nguồn deploy?  
**Đáp án:** Dễ stale/intermediate outputs, cache không phải handoff contract.

**12.** Vì sao final JAR cần checksum?  
**Đáp án:** Để so bytes trước/sau khi bàn giao và triển khai.

**13.** Checksum nằm cùng artifact archive có đủ chống tamper không?  
**Đáp án:** Không nếu kẻ tấn công sửa được cả JAR và checksum; cần trusted digest/signature.

**14.** `cache: maven` trong `setup-java` làm gì?  
**Đáp án:** Tăng tốc restore/save local Maven dependencies, không upload JAR đầu ra.

**15.** `actions/upload-artifact` làm gì?  
**Đáp án:** Lưu các files do job tạo làm CI artifacts để download/view hoặc chuyển jobs.

**16.** `if-no-files-found: error` có lợi gì?  
**Đáp án:** Fail sớm khi upload path sai/missing.

**17.** GitLab vì sao cần `-Dmaven.repo.local=$CI_PROJECT_DIR/.m2/repository`?  
**Đáp án:** Đặt cache Maven trong project folder để GitLab `cache.paths` có thể lưu.

**18.** GitLab nên dùng `cache` hay `artifacts` để truyền JAR giữa stages?  
**Đáp án:** `artifacts` và `needs`/`dependencies`.

**19.** Tại sao không đưa `settings.xml` chứa token vào cache?  
**Đáp án:** Vì có thể lộ secrets giữa jobs/branches/runners.

**20.** Một release artifact nằm trong `~/.m2` có đủ để máy khác resolve không?  
**Đáp án:** Không, cần remote Maven repository hoặc handoff bytes.

**21.** Vì sao Maven thin JAR có thể chạy trong IDE nhưng lỗi khi chuyển máy?  
**Đáp án:** IDE cấp runtime classpath; JAR riêng chưa chứa external runtime dependencies.

**22.** Multi-module cần chú ý gì khi upload?  
**Đáp án:** Artifacts ở từng module `target`, không nhất thiết ở root `target`.

**23.** Có thể coi mọi `target/*.jar` là final deployable không?  
**Đáp án:** Không, có thể gồm original/shaded/sources/test classifiers.

**24.** CI artifact hết retention thì nên xử lý release lâu dài thế nào?  
**Đáp án:** Publish vào immutable repository/registry và lưu provenance phù hợp.

**25.** Nếu job deploy rebuild lại JAR, điều gì phải xác nhận?  
**Đáp án:** File mới có cùng digest đã test/approved hoặc dùng chính file đã QA.

**26.** Một cache bị xóa có nên làm mất release đã publish không?  
**Đáp án:** Không; release được giữ riêng ở kho artifacts phù hợp.

**27.** Thế nào là handoff đúng?  
**Đáp án:** Đúng file final, đúng run/commit/GAV, QA PASS, digest verify, quyền và retention rõ.

**28.** IDE “Invalidate Caches” có đồng nghĩa xóa local Maven repo không?  
**Đáp án:** Không nhất thiết; IDE index và Maven dependency cache là hai lớp khác nhau.

## 20. Checklist thực hành cho team

- [ ] Build bằng Maven lifecycle rõ, cùng POM/toolchain với CI.
- [ ] Biết chính xác Maven local repo path; không nhầm `~/.m2` với `target/`.
- [ ] Không dùng CI dependency cache làm nơi bàn giao final JAR.
- [ ] `mvn clean verify` chạy và Surefire tests có số lượng kỳ vọng.
- [ ] Chọn đúng final binary sau packaging/shade/repackage.
- [ ] Tạo checksum trên **final file** và lưu cùng evidence.
- [ ] Ghi Git SHA, Maven GAV, CI run ID/URL vào release record.
- [ ] Chỉ upload file cần thiết, không upload toàn bộ caches.
- [ ] Test reports được lấy từ chính build run.
- [ ] CI upload path có fail khi thiếu file.
- [ ] Job consumer download artifact của đúng run.
- [ ] Job consumer kiểm tra checksum và smoke test trên file đã download.
- [ ] Cache miss không ngăn build nếu repositories khả dụng.
- [ ] Cache keys có strategy theo build descriptors/JDK/branch trust.
- [ ] Không lưu secrets trong cache hoặc public artifacts.
- [ ] CI artifacts có retention phù hợp cho review/handoff.
- [ ] Release dài hạn có immutable artifact repository/registry.
- [ ] `mvn install` không được nhầm với remote publication.
- [ ] Multi-module khai báo đủ artifacts của từng module.
- [ ] Có chính sách QA riêng cho output failure diagnostics.
- [ ] Không tự publish file từ build failed/skipped tests.
- [ ] Nếu cần reproducible release, kiểm tra input digests và toolchain.
- [ ] Nếu có signing/provenance, verify đúng signer/trusted identity.
- [ ] Khi gặp cache corruption, không xóa bừa `~/.m2` của người khác.
- [ ] Khi thiếu artifact bàn giao, điều tra upload/download và run ID trước.

## 21. Tài liệu tham khảo chính thức

1. [Apache Maven — Settings Reference](https://maven.apache.org/settings.html) — `localRepository`, mirrors và server settings.
2. [Apache Maven — Introduction to Repositories](https://maven.apache.org/guides/introduction/introduction-to-repositories.html) — local/remote repositories và Maven Resolver.
3. [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html) — compile/test/package/verify/install/deploy.
4. [Maven Clean Plugin — Usage](https://maven.apache.org/plugins/maven-clean-plugin/usage.html) — dọn project target build outputs.
5. [Maven JAR Plugin](https://maven.apache.org/plugins/maven-jar-plugin/) — đóng gói main application JAR.
6. [Maven Surefire Plugin](https://maven.apache.org/surefire/maven-surefire-plugin/) — JUnit execution và XML reports.
7. [Maven Dependency Plugin 3.11.0 — go-offline](https://maven.apache.org/components/plugins/maven-dependency-plugin/go-offline-mojo.html) — pre-resolve project dependencies/plugins.
8. [Maven Dependency Plugin — dependency:tree](https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html) — inspect resolved dependency graph.
9. [GitHub Actions — Dependency caching](https://docs.github.com/en/actions/concepts/workflows-and-actions/dependency-caching) — cache là tối ưu cho downloaded inputs.
10. [GitHub Actions — Workflow artifacts](https://docs.github.com/en/actions/concepts/workflows-and-actions/workflow-artifacts) — lưu job outputs/chuyển giữa jobs.
11. [GitHub Docs — Building and testing Java with Maven](https://docs.github.com/en/actions/tutorials/build-and-test-code/java-with-maven) — setup-java cache Maven và upload artifacts.
12. [GitHub Actions — Store and share data with workflow artifacts](https://docs.github.com/en/actions/how-tos/writing-workflows/choosing-what-your-workflow-does/storing-and-sharing-data-from-a-workflow) — upload/download và retention.
13. [GitLab Docs — Caching in GitLab CI/CD](https://docs.gitlab.com/ci/caching/) — cache vs artifacts.
14. [GitLab Docs — CI/CD YAML syntax](https://docs.gitlab.com/ci/yaml/) — cache key, artifacts, needs.
15. [GitLab Docs — Maven packages in package registry](https://docs.gitlab.com/user/packages/maven_repository/) — publish Maven GAV vào GitLab registry.
16. [Apache Maven — Configuring for Reproducible Builds](https://maven.apache.org/guides/mini/guide-reproducible-builds.html) — `outputTimestamp` và binary reproducibility.

**Kết luận:** `~/.m2/repository` và CI cache giúp Maven **không phải tải lại thư viện/plugin mỗi lần**; `target/` chứa **kết quả cục bộ sau compile/test/package**; còn CI artifact/Maven repository là **nơi bàn giao chính file cuối đã kiểm thử, định danh và lưu giữ theo chính sách**. Cache có thể mất mà build vẫn có thể chạy lại; **artifact được deploy phải là đúng bytes đã QA và được chuyển giao có thể kiểm chứng**.
