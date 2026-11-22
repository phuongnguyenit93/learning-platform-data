# Kiểm tra khả năng tái lập của các plugin tham gia build trong Maven

## 1. Cùng source, cùng lệnh nhưng artifact khác byte: vấn đề nằm ở đâu?

Một project Java có thể chạy `mvn clean package` hai lần, cả hai lần báo `BUILD SUCCESS`, tests xanh và cùng tạo file `target/demo-1.0.0.jar`. Tuy nhiên SHA-256 của hai JAR có thể khác nhau: ZIP entry có timestamp mới, manifest chứa thời gian build, resources chứa username hoặc một plugin sinh source với thứ tự không ổn định.

**Reproducible build** là việc có thể tạo **cùng byte output** từ cùng nguồn, hướng dẫn build và môi trường đầu vào đã xác định. Đây là một yêu cầu về **artifact identity**, không phải chỉ về behavior của chương trình.

Một vài mức độ cần phân biệt:

| Phép kiểm | Kết luận có thể rút ra | Chưa thể kết luận |
| --- | --- | --- |
| `mvn test` xanh | Assertions đều đạt | JAR bytes không nhất thiết giống |
| `mvn package` xanh | Packaging thành công | Output có thể còn timestamp động |
| `artifact:check-buildplan` xanh | Không thấy known plugin issues trong plan đã xét | Không chứng minh mọi plugin và input đều deterministic |
| Hai lần clean build, SHA-256 trùng | Những artifacts được so trùng bytes trên cùng môi trường | Có thể còn leak username/path/JDK khác |
| Hai môi trường độc lập, cùng output | Bằng chứng mạnh hơn về reproducibility | Cần đánh giá phạm vi artifacts và reference |

**Trọng tâm bài:** không chỉ thiết lập property `project.build.outputTimestamp`, mà cần kiểm tra **tất cả plugin goals thực sự tham gia build**, kiểm thử artifact output và điều tra khi bytes khác.

## 2. Những thành phần Maven nào có thể tạo bytes không ổn định?

| Thành phần/plugin | Output liên quan | Rủi ro |
| --- | --- | --- |
| Maven Compiler Plugin | Bytecode `.class` | JDK/compiler/annotation processor khác nhau |
| Maven Resources Plugin | Copied/filtered resources | Time, env, hostname, absolute path hoặc encoding |
| Maven JAR Plugin | Binary JAR và manifest | ZIP entry timestamps, metadata, archive ordering |
| Maven Source Plugin | `-sources.jar` | Source line endings, timestamp ZIP, file order |
| Maven WAR Plugin | WAR | Archive metadata, web resources |
| Maven Shade Plugin | Uber/fat JAR | Merge services, transformers, dependency order |
| Maven Assembly Plugin | Distribution ZIP/TAR | Timestamps, file modes, ordering |
| Maven Javadoc Plugin | API docs/Javadoc JAR | Doclet/JDK, comments, timestamp, generated HTML |
| Source generator / annotation processor | Generated `.java`/resources | `Instant.now()`, random IDs, filesystem path |
| Buildnumber / git metadata plugin | Properties, manifest | CI job ID hoặc giá trị Git không ổn định |
| Signing, obfuscation, container plugins | Signed artifact/image | Signature metadata, randomness, base image state |

**Không được mặc định plugin mới luôn tạo output tái lập.** Plugin có thể hỗ trợ reproducible archives nhưng vẫn sinh một resource chứa `System.currentTimeMillis()` qua code generation hoặc filtering.

Các artifact release có thể gồm binary JAR, sources JAR, Javadoc JAR, assembly ZIP, shaded JAR và signatures. Cần nói rõ **bộ nào đang được so sánh**.

## 3. Plugin execution plan: nguồn nào được đưa vào danh sách kiểm tra?

Một số plugins được bind bởi **default Maven lifecycle** theo packaging. Với `packaging=jar`, Maven gọi các goals như Resources, Compiler, Surefire và JAR ngay cả khi POM không khai báo mọi plugin bằng tay. Ngoài ra còn có:
- `<build><plugins><executions>` gắn goals vào phase;
- parent POM và `pluginManagement` quản lý versions/config;
- các profiles đang bật như `release`, `ci`, `distribution`;
- goals gọi trực tiếp bằng CLI;
- plugins được dùng như build extensions hoặc gọi công cụ ngoài Maven.

### 3.1. Effective POM có ích nhưng không thay execution plan

```bash
mvn -B -ntp help:effective-pom -Doutput=effective-pom.xml
```

File này mô tả effective project model sau inheritance/profiles, hỗ trợ tìm versions, dependencies và plugin configuration. Nhưng **không phải tất cả plugin có tên trong model đều thật sự chạy**.

Một cấu hình:

```xml
<pluginManagement>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-jar-plugin</artifactId>
            <version>3.4.2</version>
        </plugin>
    </plugins>
</pluginManagement>
```

là **fragment** chốt plugin version, không phải execution mới. Tuy nhiên version đó có thể được dùng bởi JAR Plugin khi lifecycle `jar` packaging đã bind `jar:jar`.

### 3.2. Đọc build log cùng profile thực tế

Ví dụ log minh họa:

```text
--- maven-resources-plugin:3.3.1:resources (...) @ repro-check-demo ---
--- maven-compiler-plugin:3.14.1:compile (...) @ repro-check-demo ---
--- maven-surefire-plugin:3.5.4:test (...) @ repro-check-demo ---
--- maven-jar-plugin:3.4.2:jar (...) @ repro-check-demo ---
--- maven-source-plugin:3.3.1:jar-no-fork (...) @ repro-check-demo ---
```

Tùy Maven version, log thật có định dạng và execution ids khác. Điều phải ghi lại là **plugin GAV, goal, phase, profile và artifact output**. Nếu release có `javadoc:jar`, `shade:shade` hoặc `assembly:single`, cần kiểm **cả các goals đó**, không chỉ nhóm plugin build local.

## 4. Property outputTimestamp và cơ chế archive tái lập

Apache Maven hướng dẫn đặt một giá trị ổn định:

```xml
<properties>
    <project.build.outputTimestamp>2024-01-01T00:00:00Z</project.build.outputTimestamp>
</properties>
```

Đây chỉ là **POM fragment**, timestamp là giá trị minh họa cố định. Các archive-aware plugins có hỗ trợ có thể dùng nó để chuẩn hóa timestamps trong JAR/ZIP entries.

Maven JAR Plugin từ 3.2.0 có tham số `outputTimestamp`, mặc định đọc `${project.build.outputTimestamp}`. Maven Source Plugin cũng hỗ trợ tham số `outputTimestamp`. Các giá trị được hỗ trợ có dạng ISO 8601 có offset hoặc epoch seconds (tương tự `SOURCE_DATE_EPOCH`) theo tài liệu từng goal.

Không dùng một giá trị thay đổi theo mỗi build như:

```xml
<project.build.outputTimestamp>${maven.build.timestamp}</project.build.outputTimestamp>
```

vì mỗi lượt chạy sẽ có timestamp khác nhau, làm mất mục tiêu ổn định của archive metadata.

### Cảnh báo về phiên bản Maven

Tài liệu Apache Maven hiện cho biết **Maven 3.10.0** và **Maven 4.0.0-beta-5** trở lên bật Reproducible Builds mode theo mặc định. Trong các dự án cần tái lập trên nhiều môi trường/version Maven, việc chỉ rõ một giá trị tĩnh ở POM vẫn rất hữu ích.

**Nhưng outputTimestamp không sửa nội dung động đã được plugin ghi vào resource.** Ví dụ:

```properties
build.timestamp=2026-11-10T10:00:00Z
build.user=alice
checkout.path=/home/alice/project
```

Các bytes trên sẽ khác giữa các máy/giờ dù ZIP timestamps giống nhau. Nên tránh đưa thông tin như current time, hostname, username, working directory vào release artifact, hoặc chuẩn hóa bằng một giá trị ổn định theo source commit/release.

## 5. Kiểm tra plugin bằng artifact:check-buildplan

**Apache Maven Artifact Plugin 3.7.0** có goal:

```bash
mvn -B -ntp org.apache.maven.plugins:maven-artifact-plugin:3.7.0:check-buildplan
```

Goal này tính **execution plan** cho những tasks đã chọn và tìm plugin goals có **known Reproducible Builds issues**. Nó không tự tạo hai JAR để so.

Theo tài liệu goal 3.7.0:

| Tham số | Nghĩa |
| --- | --- |
| `failOnNonReproducible` | Có fail khi plan chứa plugin có vấn đề reproducibility đã biết; mặc định `true` |
| `tasks` | Danh sách phases/goals để xét build plan; mặc định `deploy` |
| `outputTimestamp` | Giá trị timestamp plugin sử dụng khi chẩn đoán |
| `diagnose` | Hỗ trợ xác định `outputTimestamp` hiệu dụng |
| `pluginIssues` | File thay thế danh sách plugin issues mặc định |

Có thể chạy:

```bash
mvn -B -ntp org.apache.maven.plugins:maven-artifact-plugin:3.7.0:check-buildplan -Ddiagnose=true
```

Nếu báo plugin version lỗi, ghi chính xác version/goal và nghiên cứu phiên bản hỗ trợ reproducible output. Sau khi nâng plugin, **vẫn phải so artifact bytes**, vì một plugin không bị flag có thể còn chịu ảnh hưởng từ input động.

### Giới hạn quan trọng

- Danh sách known issues **không phải catalogue đầy đủ tất cả bug**.
- Kết quả chỉ áp dụng cho **execution plan đã kiểm**, không bao gồm mọi profile chưa kích hoạt hoặc third-party command ngoài Maven.
- Một goal được khai báo trong `pluginManagement` nhưng không được bind/instantiate không tự là bước build.
- Không dùng `-Dcheck.failOnNonReproducible=false` để lờ cảnh báo rồi tuyên bố build tái lập.

Đối với release, kiểm plan có **đúng release profiles/goal chains**. Một build chỉ thực hiện `package` có thể bỏ sót plugin dùng riêng cho release ZIP, Javadoc hay signing.

## 6. Kiểm tra output bằng artifact:compare

Apache Maven đề xuất hai lượt:

```bash
mvn -B -ntp clean install
mvn -B -ntp clean verify org.apache.maven.plugins:maven-artifact-plugin:3.7.0:compare
```

**Giải thích:**
1. Lượt đầu build và install artifact reference vào **local Maven repository** theo đúng GAV.
2. Lượt thứ hai tạo lại artifact từ cùng checkout, rồi `artifact:compare` so current output với reference.
3. Kết quả được ghi vào file `.buildcompare`, và compare có thể fail nếu bytes khác.
4. `compare.fail` ở bản 3.7.0 mặc định `true`.

Lệnh `install` **không** publish remote repository, nhưng vẫn có thể thay đổi artifact cùng GAV trong local Maven repo. Trong CI hoặc thí nghiệm cần tránh reference cũ, dùng local repo riêng cho task.

Một số tham số cần lưu ý:
- `reference.repo`: reference repository khi so với artifact đã publish.
- `buildinfo.ignoreJavadoc`: mặc định **`true`**, nên Javadoc JAR có thể bị bỏ qua.
- `buildinfo.ignore`, `buildinfo.skipModules`: loại artifact/module; khi dùng phải mô tả phạm vi ngoại lệ.
- `compare.aggregate.only`: mode compare khi multi-module.
- Goal `compare` không được đánh dấu thread-safe, nên không mặc định chạy `-T` khi cần chẩn đoán dễ hiểu.

**Hai lần trên cùng máy match mới chỉ là local reproducibility**. Có thể cả hai artifact cùng nhúng đường dẫn `/home/alice/...` nên match tại máy Alice, nhưng khác máy Bob.

Một remote reference ví dụ:

```bash
mvn -B -ntp clean verify org.apache.maven.plugins:maven-artifact-plugin:3.7.0:compare -Dreference.repo=https://repo.example.org/releases/
```

Đây là **URL mẫu**, không phải repository thật. Reference phải có GAV đúng, đáng tin và cùng release profile; không dùng một SNAPSHOT vừa được cập nhật để kết luận project không reproducible.

## 7. Ví dụ Java 17 hoàn chỉnh: hai artifacts cần kiểm

Ta xây một Maven project:
- Binary JAR chứa class Java và resource filtered ổn định;
- Sources JAR được Maven Source Plugin attach;
- JUnit 5 tests để kiểm logic;
- Artifact Plugin để check buildplan/compare.

### 7.1. Cây thư mục

```text
repro-check-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/repro/BuildInfo.java
    │   └── resources/build-info.properties
    └── test/
        └── java/com/example/repro/BuildInfoTest.java
```

### 7.2. File pom.xml đầy đủ

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example.repro</groupId>
    <artifactId>repro-check-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.outputTimestamp>2024-01-01T00:00:00Z</project.build.outputTimestamp>
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
        <resources>
            <resource>
                <directory>src/main/resources</directory>
                <filtering>true</filtering>
                <includes>
                    <include>build-info.properties</include>
                </includes>
            </resource>
        </resources>

        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-resources-plugin</artifactId>
                <version>3.3.1</version>
                <configuration>
                    <encoding>UTF-8</encoding>
                    <useDefaultDelimiters>false</useDefaultDelimiters>
                    <delimiters>
                        <delimiter>@</delimiter>
                    </delimiters>
                </configuration>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.4</version>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
                <configuration>
                    <outputTimestamp>${project.build.outputTimestamp}</outputTimestamp>
                </configuration>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-source-plugin</artifactId>
                <version>3.3.1</version>
                <executions>
                    <execution>
                        <id>attach-sources</id>
                        <phase>package</phase>
                        <goals>
                            <goal>jar-no-fork</goal>
                        </goals>
                    </execution>
                </executions>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-artifact-plugin</artifactId>
                <version>3.7.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Đây là **POM độc lập** của bài thực hành. Không cần ghép thêm các fragments minh họa khác.

Điểm quan trọng:
- `outputTimestamp` được chốt tại POM; JAR Plugin 3.4.2 hỗ trợ và lấy đúng property.
- Source Plugin 3.3.1 tạo sources JAR qua `jar-no-fork` ở phase `package`, có hỗ trợ outputTimestamp.
- Resources Plugin chỉ filter file `build-info.properties`, không biến mã nhị phân.
- Filter uses delimiter `@...@` và `useDefaultDelimiters=false`; không vô tình thay các `${...}` khác trong tài nguyên.
- `maven.compiler.release=17`, encoding UTF-8 và plugin versions được khai báo tường minh.
- JUnit Jupiter dependency ở test scope. Artifact Plugin có thể được gọi qua tọa độ đầy đủ khi cần, không tự so mỗi lần `package`.

### 7.3. File src/main/resources/build-info.properties

```properties
artifact=@project.artifactId@
version=@project.version@
```

Sau Resources Plugin filtering:

```properties
artifact=repro-check-demo
version=1.0.0
```

Hai giá trị đến từ POM đã chốt, nên nội dung resource ổn định. Tránh thêm `build.timestamp=@maven.build.timestamp@` hay `build.user=@env.USER@` nếu chúng phải nằm trong artifact reproducible.

### 7.4. File src/main/java/com/example/repro/BuildInfo.java

```java
package com.example.repro;

import java.io.IOException;
import java.io.InputStream;
import java.io.UncheckedIOException;
import java.util.Objects;
import java.util.Properties;

public final class BuildInfo {

    private BuildInfo() {
    }

    public static String identity() {
        Properties values = new Properties();

        try (InputStream input =
                     BuildInfo.class.getResourceAsStream("/build-info.properties")) {
            if (input == null) {
                throw new IllegalStateException("Missing build-info.properties");
            }
            values.load(input);
        } catch (IOException exception) {
            throw new UncheckedIOException(exception);
        }

        String artifact =
                Objects.requireNonNull(values.getProperty("artifact"), "artifact");
        String version =
                Objects.requireNonNull(values.getProperty("version"), "version");

        return artifact + ":" + version;
    }

    public static String greet(String name) {
        if (name == null || name.isBlank()) {
            return "Hello, friend!";
        }
        return "Hello, " + name.strip() + "!";
    }

    public static void main(String[] args) {
        System.out.println(identity());
        System.out.println(greet(" Maven "));
    }
}
```

Đây là **Java 17 compilable**. `identity()` đọc resource classpath, không dùng clock, user, path hay random ID. Các giá trị trong file properties minh họa chỉ chứa ASCII.

Stdout chính xác của chương trình:

```text
repro-check-demo:1.0.0
Hello, Maven!
```

### 7.5. File src/test/java/com/example/repro/BuildInfoTest.java

```java
package com.example.repro;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class BuildInfoTest {

    @Test
    void loadsStableIdentity() {
        assertEquals("repro-check-demo:1.0.0", BuildInfo.identity());
    }

    @Test
    void trimsInput() {
        assertEquals("Hello, Maven!", BuildInfo.greet(" Maven "));
    }

    @Test
    void handlesBlankName() {
        assertEquals("Hello, friend!", BuildInfo.greet(" "));
    }
}
```

Ba JUnit Jupiter tests, không có nguồn ngẫu nhiên. Khi build đúng, kỳ vọng 3 tests, 0 failures, 0 errors.

### 7.6. Lệnh build và chạy

Từ thư mục `repro-check-demo`:

```bash
mvn -version
mvn -B -ntp clean verify
java -cp target/classes com.example.repro.BuildInfo
```

Kỳ vọng output Java:

```text
repro-check-demo:1.0.0
Hello, Maven!
```

Artifacts ở phase package:

```text
target/repro-check-demo-1.0.0.jar
target/repro-check-demo-1.0.0-sources.jar
```

Kiểm tra JAR có `com/example/repro/BuildInfo.class` và `build-info.properties` bằng:

```bash
jar tf target/repro-check-demo-1.0.0.jar
```

**`jar tf` chỉ liệt kê entries**, không chứng minh bytes của hai JAR giống nhau.

## 8. Thực hành kiểm soát plugin và artifact

### 8.1. Rà plugin issues

```bash
mvn -B -ntp org.apache.maven.plugins:maven-artifact-plugin:3.7.0:check-buildplan
```

Goal kiểm theo catalog và tasks/plan. Nếu không báo known issues, tiếp tục bước đo actual artifacts.

### 8.2. Đo qua Maven Artifact Plugin

```bash
mvn -B -ntp clean install
mvn -B -ntp clean verify org.apache.maven.plugins:maven-artifact-plugin:3.7.0:compare
```

Đọc file `.buildcompare` mà plugin báo. Nếu mismatch, giữ log và các file reference/current để phân tích.

### 8.3. Tự so hai JAR bằng SHA-256 trên Linux/macOS

```bash
mvn -B -ntp clean package

cp target/repro-check-demo-1.0.0.jar /tmp/repro-first.jar
cp target/repro-check-demo-1.0.0-sources.jar /tmp/repro-first-sources.jar

mvn -B -ntp clean package

sha256sum /tmp/repro-first.jar target/repro-check-demo-1.0.0.jar
sha256sum /tmp/repro-first-sources.jar target/repro-check-demo-1.0.0-sources.jar

cmp -s /tmp/repro-first.jar target/repro-check-demo-1.0.0.jar \
  && echo MATCH_JAR || echo DIFFERENT_JAR

cmp -s /tmp/repro-first-sources.jar target/repro-check-demo-1.0.0-sources.jar \
  && echo MATCH_SOURCES || echo DIFFERENT_SOURCES
```

Trên macOS không cài `sha256sum` có thể dùng `shasum -a 256`.

Nếu hai artifacts thật sự trùng byte, các dòng kiểm có thể là:

```text
MATCH_JAR
MATCH_SOURCES
```

Đây là **output kỳ vọng có điều kiện**, không phải một SHA-256 được đo sẵn. Hai hash thực phụ thuộc source và toolchain.

**Phải copy artifact trước lần `clean` thứ hai**; nếu không, bản đầu đã bị xóa khỏi `target`.

### 8.4. Windows PowerShell

```powershell
mvn -B -ntp clean package

$refJar = Join-Path $env:TEMP "repro-first.jar"
$refSources = Join-Path $env:TEMP "repro-first-sources.jar"

Copy-Item "target/repro-check-demo-1.0.0.jar" $refJar
Copy-Item "target/repro-check-demo-1.0.0-sources.jar" $refSources

mvn -B -ntp clean package

(Get-FileHash $refJar -Algorithm SHA256).Hash
(Get-FileHash "target/repro-check-demo-1.0.0.jar" -Algorithm SHA256).Hash
(Get-FileHash $refSources -Algorithm SHA256).Hash
(Get-FileHash "target/repro-check-demo-1.0.0-sources.jar" -Algorithm SHA256).Hash
```

So hash theo từng cặp. Nếu chỉ binary JAR trùng mà sources JAR khác, **không** nói tất cả release artifacts đều reproducible.

## 9. Khi byte khác, dùng diffoscope và xác định goal gây ra

Nếu hai JAR khác bytes, đừng nâng tất cả plugins một cách mù quáng. Có thể dùng **diffoscope** (công cụ ngoài Maven, cần cài riêng) để phân tích nội dung archive:

```bash
diffoscope /tmp/repro-first.jar target/repro-check-demo-1.0.0.jar
```

Bước tiếp theo:

1. Đọc `.buildcompare` để biết artifact nào khác.
2. Kiểm archive entries, ZIP timestamps và `META-INF/MANIFEST.MF`.
3. Nếu `build-info.properties` khác, xem **Maven Resources Plugin** và filtered inputs.
4. Nếu `.class` khác, xem **JDK, Maven Compiler Plugin, annotation processors** và generated sources.
5. Nếu binary JAR trùng nhưng sources JAR khác, xem **Maven Source Plugin**, EOL và filesystem order.
6. Nếu plain JAR trùng nhưng shaded JAR khác, xem **Maven Shade Plugin** và resource transformers.
7. Nếu distribution ZIP khác, xem **Assembly Plugin**, manifest, permissions, file order và extra resources.
8. Nếu Javadoc JAR khác, xem **Javadoc Plugin/JDK doclet** và phạm vi mặc định của `artifact:compare`.
9. Sau khi sửa plugin hoặc input, build lại từ `clean` và compare.

**Maven `project.build.outputTimestamp` không thể sửa một file Java generated đã nhúng ngày giờ thật vào comment/resource.** Cần sửa plugin/code generator hoặc điều chỉnh stable input.

### Một bảng chẩn đoán nhanh

| Sự khác biệt | Plugin/input thường cần xem |
| --- | --- |
| JAR timestamps khác | JAR/Source/Assembly/WAR/Shade archiver |
| Manifest có `Build-Time` | Plugin sinh manifest hoặc custom metadata |
| Resources khác | Filtering, environment, encoding |
| Bytecode khác | JDK/compiler/annotation processor |
| `.class` có đường dẫn absolute | Generator/compiler debug metadata |
| `-sources.jar` khác | Source Plugin/source bytes/newlines |
| `-javadoc.jar` khác | Javadoc tool/version/options |
| Service files merge order khác | Shade transformers |
| CI Linux khác máy Windows | EOL, filesystem case, platform tools |
| SNAPSHOT dependency thay đổi | Dependency input không immutable |
| Signature artifacts khác | Signing stage/time/nonce, phân biệt payload |

## 10. Multi-module và release profiles: đừng bỏ qua module cuối

Ví dụ reactor:

```text
platform/
├── pom.xml                 (aggregator)
├── api/pom.xml
├── service/pom.xml
└── distribution/pom.xml
```

`api` tạo library JAR, `service` có thể tạo shaded JAR, `distribution` tạo ZIP. Hash của API JAR trùng **không đủ** để kết luận distribution ZIP tái lập.

**Checklist multi-module:**
- Chạy buildplan check ở root với đúng profile.
- Dùng cùng release goals mà CI deploy.
- Kiểm đủ các module và attached artifacts.
- Không nhầm `pluginManagement` với một goal đã chạy.
- Chú ý `artifact:compare` có thể sinh báo cáo từng module và aggregate.
- Nếu dùng `-T` trong CI, kiểm tính thread-safe của các plugins và đo hiện tượng race.
- Không dùng `-pl` chỉ chọn một module để tuyên bố toàn reactor đã đạt.

Ngoài Maven plugins, còn có các scripts/container tools bên ngoài, chúng cũng là input của build pipeline và cần được kiểm soát.

## 11. Vì sao cần xây từ thư mục hoặc máy khác?

Cùng path, user và timezone tạo ra cùng metadata trong cả hai lượt build có thể làm bài test local **trùng hash nhưng vẫn bị environment leak**.

Để có bằng chứng mạnh hơn:

1. Chốt **source commit** và version toolchain.
2. Build từ thư mục A, giữ artifacts + checksums.
3. Rebuild từ thư mục B có **đường dẫn khác**, hoặc runner/container/máy độc lập.
4. Giữ source, dependencies, timestamp, Maven/JDK version, profiles và flags nhất quán.
5. So mọi artifact được phát hành, bao gồm source/Javadoc/distribution theo phạm vi.
6. Nếu khác, dùng diffoscope tìm đường dẫn/hostname/locale/JDK version bị nhúng.
7. Ghi rõ những artifact được phép exclude, lý do và scope.

Hai lần chạy trong một Docker image giống nhau trên cùng host cũng chỉ kiểm một phần; **independent reproducibility** đòi hỏi builder thứ hai và reference có thể xác minh độc lập.

## 12. CI pipeline đơn giản

Một GitHub Actions workflow minh họa cho demo Java 17:

```yaml
name: Maven reproducibility
on:
  pull_request:
  push:

jobs:
  reproducibility:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'
          cache: maven
      - name: Inspect plugin build plan
        run: mvn -B -ntp org.apache.maven.plugins:maven-artifact-plugin:3.7.0:check-buildplan
      - name: Create reference artifact
        run: mvn -B -ntp clean install
      - name: Rebuild and compare artifacts
        run: mvn -B -ntp clean verify org.apache.maven.plugins:maven-artifact-plugin:3.7.0:compare
```

**Hạn chế minh bạch:**
- Job kiểm lặp trên cùng runner, không phải independent rebuild.
- `mvn install` ghi vào local repository của job, không deploy remote.
- Nếu release dùng `-Prelease`, signing hoặc plugin tạo ZIP/Javadoc, cần kiểm đúng release execution.
- Branch protection/required checks phải bật trong hệ thống Git hosting nếu muốn bắt buộc job xanh.
- Với private repository cần quản lý credentials bằng secrets, không ghi vào POM hoặc log public.

Không nên làm CI tự thay đổi source để che mismatch. CI nên trả nonzero exit status và giữ báo cáo cho developer sửa.

## 13. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Check-buildplan fail | Plugin version có issue đã biết | Upgrade và so output |
| Check-buildplan pass, hash fail | Catalog không bao phủ input/plugin custom | So file, dùng diffoscope |
| Hai JAR khác entry time | Archiver chưa dùng stable timestamp | Cấu hình outputTimestamp đúng |
| OutputTimestamp dùng current time | Giá trị đổi giữa các build | Dùng stable release/commit value |
| Resource chứa build.user/hostname | Filtering dynamic | Loại hoặc chuẩn hóa metadata |
| Bytecode khác ở JDK khác | Toolchain không pin | Cố định JDK/vendor/update |
| Binary JAR match, sources JAR fail | Source Plugin/line endings | Kiểm source artifact riêng |
| Javadoc JAR bỏ qua | `buildinfo.ignoreJavadoc=true` mặc định | Điều chỉnh scope |
| Plain JAR match, shaded JAR fail | Shade transformers/order | Kiểm shaded output |
| Compare không tìm reference | Chưa install đúng GAV hoặc repo sai | Tạo reference đáng tin |
| Compare dùng artifact stale | Local repository có GAV cũ | Dùng isolated local repo |
| Build khác khi checkout path đổi | Absolute path bị nhúng | Sửa generator/metadata |
| Cùng máy trùng, cross-OS khác | Encoding/EOL/file mode | Chuẩn hóa theo chính sách |
| Release ZIP khác nhưng module JAR trùng | Assembly/extra resources | So distribution artifact |
| Maven `-T` làm output biến động | Thread-safety/race | Điều tra parallel plugin |
| Plugin chỉ ở management | Goal chưa instantiated | Xem lifecycle/actual executions |
| SNAPSHOT đổi qua đêm | Dependency không immutable | Dùng release/lock inputs |
| `install` bị nhầm là deploy | Lẫn local và remote repo | Dùng đúng lifecycle |
| Fail flag bị tắt | Cổng kiểm tra không chặn | Tắt exceptions sau khi xử lý |

### Trình tự debug

1. Lưu source commit, plugin/JDK/Maven versions, profiles.
2. Ghi SHA-256 từng artifact reference và current.
3. Tách lỗi archive time, manifest, resource, class hoặc source JAR.
4. Xác định goal sinh file đang khác.
5. Xem version plugin và `outputTimestamp`.
6. Tìm input động: clock, environment, random, filesystem path.
7. Sửa đúng nguyên nhân, không chỉ đổi thứ tự XML.
8. Build sạch hai lần và chạy artifact compare.
9. Nếu cần, kiểm khác thư mục/máy.
10. Ghi scope so sánh và những ngoại lệ chưa xử lý.

## 14. Bài tập

1. Vì sao Maven `BUILD SUCCESS` không chứng minh JAR giống nhau từng byte?
2. Hai bước `artifact:check-buildplan` và `artifact:compare` kiểm điều gì khác nhau?
3. Tại sao check-buildplan xanh vẫn có thể chứa plugin generator phi tái lập?
4. `project.build.outputTimestamp` ảnh hưởng ZIP metadata như thế nào?
5. Vì sao không dùng `${maven.build.timestamp}` cho reproducible archive property?
6. Compiler `release=17` đã bảo đảm bytecode trùng trên mọi JDK 17 chưa?
7. Tại sao phải kiểm `-sources.jar` riêng?
8. `artifact:compare` có thể bỏ qua Javadoc artifacts theo mặc định không?
9. Vì sao phải copy JAR ra ngoài `target` trước build thứ hai?
10. `Get-FileHash` và SHA-256 chỉ xác minh điều gì?
11. Tại sao build ở hai working directory khác nhau là phép kiểm mạnh hơn?
12. Nếu `build-info.properties` khác nhưng class giống, tìm ở plugin nào?
13. Nếu plain JAR trùng nhưng shaded JAR khác, cần kiểm gì?
14. `mvn install` có publish remote artifact không?
15. Java `BuildInfo.main` ở ví dụ in những dòng nào?

### Đáp án tóm tắt

- **1:** Build/test không đối chiếu timestamps và bytes.
- **2:** Một bên rà known issues trong buildplan, một bên so actual artifact output.
- **3:** Catalog chỉ chứa vấn đề đã biết, không đánh giá mọi input động.
- **4:** Chuẩn hóa timestamp entries của supported archive plugins.
- **5:** Giá trị đổi theo giờ invocation.
- **6:** Chưa; JDK/compiler/processors cũng là inputs.
- **7:** Sources JAR là release artifact độc lập.
- **8:** Có, default `buildinfo.ignoreJavadoc=true`.
- **9:** `clean` xóa artifacts lượt trước.
- **10:** So bytes của các file được đo, không tự xác minh provenance.
- **11:** Giúp phát hiện dữ liệu nhúng đường dẫn và môi trường.
- **12:** Maven Resources Plugin và filtered values.
- **13:** Shade transformers, merge order, inputs và timestamp.
- **14:** Không, chỉ local repository.
- **15:** `repro-check-demo:1.0.0` và `Hello, Maven!`.

## 15. Checklist chất lượng trước release

- [ ] Source commit và release profiles được xác định.
- [ ] Maven/JDK/compiler/plugin versions được chốt.
- [ ] Dependencies dùng version immutable.
- [ ] Có stable `project.build.outputTimestamp` khi cần.
- [ ] Đã kiểm kê plugin executions thực sự từ lifecycle/profiles.
- [ ] Đã chạy `artifact:check-buildplan` với đúng execution scope.
- [ ] Known non-reproducible plugin issues đã được xử lý.
- [ ] JAR/Source/WAR/Shade/Assembly/Javadoc output được đánh giá theo phạm vi release.
- [ ] Resources và codegen không ghi clock/user/path ngẫu nhiên vào artifacts.
- [ ] Đã so hai lần clean build bằng SHA-256 hoặc `artifact:compare`.
- [ ] Đã đọc `.buildcompare` và nêu rõ những exclusions/ignore flags.
- [ ] Các binary/source/Javadoc JAR cần phát hành được so riêng.
- [ ] Signing, Docker/image và các công cụ ngoài Maven được xem xét.
- [ ] Nếu muốn chứng minh độc lập, đã rebuild ở path/máy khác.
- [ ] CI dùng đúng profile và lifecycle/goal chain của release.
- [ ] Không đặt fail/skip flags để che kết quả không tái lập.
- [ ] Báo cáo chỉ tuyên bố mức reproducibility đúng với bằng chứng.

**Kết luận:** Kiểm tra khả năng tái lập của các plugin Maven cần phối hợp **kiểm execution plan** và **đo artifact bytes**. `artifact:check-buildplan` chỉ ra known issues trong plugin plan, còn `artifact:compare` hoặc SHA-256 cho biết output hiện tại có trùng reference hay không. `project.build.outputTimestamp` hữu ích để ổn định archive metadata, nhưng không tự sửa input từ clock, username, filesystem hay plugin custom. Một release chỉ nên được gọi là reproducible trong phạm vi những artifacts và môi trường đã được kiểm chứng rõ ràng.

## Tài liệu tham khảo chính thức

- [Apache Maven — Configuring for Reproducible Builds](https://maven.apache.org/guides/mini/guide-reproducible-builds.html)
- [Apache Maven Artifact Plugin 3.7.0 — Goals](https://maven.apache.org/plugins/maven-artifact-plugin/plugin-info.html)
- [Apache Maven Artifact Plugin — check-buildplan](https://maven.apache.org/plugins/maven-artifact-plugin/check-buildplan-mojo.html)
- [Apache Maven Artifact Plugin — compare](https://maven.apache.org/plugins/maven-artifact-plugin/compare-mojo.html)
- [Apache Maven Artifact Plugin — Usage](https://maven.apache.org/plugins/maven-artifact-plugin/usage.html)
- [Apache Maven Artifact Plugin — Diagnosing Reproducible Builds](https://maven.apache.org/plugins/maven-artifact-plugin/reproducible.html)
- [Apache Maven JAR Plugin — jar:jar outputTimestamp](https://maven.apache.org/plugins/maven-jar-plugin/jar-mojo.html)
- [Apache Maven Source Plugin — source:jar](https://maven.apache.org/plugins/maven-source-plugin/jar-mojo.html)
- [Apache Maven — Guide to Filtering Resources](https://maven.apache.org/guides/mini/guide-filtering-resources.html)
- [Reproducible Builds — JVM](https://reproducible-builds.org/docs/jvm/)