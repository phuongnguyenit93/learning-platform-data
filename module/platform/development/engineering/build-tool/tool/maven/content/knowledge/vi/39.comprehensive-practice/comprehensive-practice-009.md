# Chẩn đoán lỗi do settings, profile, JDK hoặc metadata kho

> **Thực hành tổng hợp — Build Tool Maven.** Một dự án Java có thể chạy thành công trên máy A nhưng thất bại trên CI dù mã nguồn không thay đổi. Bốn nhóm nguyên nhân thường bị nhầm lẫn là **settings.xml/mirror và quyền truy cập kho**, **profile được kích hoạt khác nhau**, **JDK chạy Maven hoặc JDK biên dịch không khớp**, và **repository metadata/cache khiến Maven resolve artifact khác hoặc không tìm thấy**. Bài này dạy cách tách bốn nhóm bằng bằng chứng, tái hiện trong sandbox, sửa đúng lớp cấu hình và xác minh bằng một build Java 17 hoàn chỉnh.

## 1. Sơ đồ chẩn đoán: kiểm lớp nào trước?

~~~text
Maven build FAIL / local PASS - CI FAIL
                    |
                    v
  Ghi commit, cwd, câu lệnh Maven, exit code
                    |
                    v
  mvn -version / JAVA_HOME / Java runtime?
                    |
         +----------+-------------+
         |                        |
         v                        v
    Java/toolchain             Đúng JDK
    không phù hợp                 |
                                 v
                 Maven đang dùng settings nào?
                 effective-settings, -s, mirrors
                                 |
                 +---------------+--------------+
                 |                              |
                 v                              v
           401/403/timeout               Settings không lạ
           mirror/ACL/network                    |
                                                v
                         Active profiles và effective POM?
                                                |
                                 +--------------+-------------+
                                 |                            |
                                 v                            v
                           Sai profile                  Profile đúng
                           properties/plugin                  |
                                                             v
                                      Có lỗi resolve artifact/plugin?
                                                             |
                                               +-------------+-----------+
                                               |                         |
                                               v                         v
                                     Repository/cache/             Compiler/test/
                                     metadata/policy               application code
                                               |
                                               v
                                      Sửa đúng nguyên nhân,
                                      targeted verify rồi full verify
~~~

Đây là **thứ tự điều tra gợi ý**, không phải một quy tắc tuyệt đối. Ví dụ JDK không phù hợp có thể làm một profile được kích hoạt theo JDK; settings lại chọn một mirror mà snapshot metadata không tồn tại. Nguyên nhân có thể là **kết hợp nhiều lớp**, vì vậy phải giữ bản chụp lệnh và cấu hình thực tế.

### Nhìn triệu chứng để đi đúng hướng

| Triệu chứng trong log | Nghi ngờ đầu tiên | Chứng cứ cần thu |
| --- | --- | --- |
| `401 Unauthorized`, `403 Forbidden` | Settings server ID, credentials, quyền repo | Effective settings, repository/mirror ID, status HTTP |
| `Could not transfer artifact ...`, TLS/timeout | Mirror/proxy/network | Mirror URL, `-X` đã redact, CI network |
| `No plugin found for prefix` | Plugin group metadata/`pluginGroups` | Fully-qualified plugin GAV và effective settings |
| Property đổi, test/resource khác nhau | POM/settings profiles hoặc `-D` override | `help:active-profiles`, `help:evaluate` |
| `invalid target release: 17` | Maven đang dùng JDK không hỗ trợ Java 17 | `mvn -version`, `JAVA_HOME` |
| `UnsupportedClassVersionError` | JVM runtime chạy class quá cũ | Java class file version, `java -version` |
| Enforcer `RequireJavaVersion` fail | JDK chạy Maven không thỏa policy | Enforcer execution, Maven JDK |
| `Could not find artifact ...-SNAPSHOT` | GAV, snapshot policy, local cache/metadata, mirror | `maven-metadata.xml`, repo URL và effective POM |
| `Failure to find ... was cached` | Resolver đã cache một lần không tìm thấy | `*.lastUpdated` trong local repo và update policy |
| `Non-resolvable parent POM` | Parent GAV, relativePath, repositories/settings | Parent coordinates, mirror, cache |
| Local PASS nhưng CI FAIL | Khác source/mvn args/JDK/settings/profile/cache | So snapshot hai môi trường |
| `BUILD SUCCESS` nhưng không test đúng môi trường | Profile chưa active hoặc tests bị skip | Active profiles, Surefire reports, effective POM |

**Một câu log không đủ:** “Could not resolve dependencies” chưa phân biệt được sai version, sai remote repository, proxy lỗi, snapshot chưa được deploy hay metadata cũ.

## 2. Bốn lớp cấu hình không nên đánh đồng

| Lớp | Nơi khai báo | Phạm vi ảnh hưởng | Lệnh để chẩn đoán |
| --- | --- | --- | --- |
| `settings.xml` | `~/.m2/settings.xml`, Maven global settings, hoặc `-s` | Mirrors, servers, proxies, repositories trong settings profiles, local repo | `help:effective-settings` |
| Maven profile | `pom.xml` hoặc `settings.xml` | Properties, repositories, plugins/build logic (tùy nguồn profile) | `help:active-profiles`, `help:effective-pom` |
| JDK | `JAVA_HOME`, PATH, Maven process, toolchains | Runtime Maven/plugin, compiler, tests, bytecode | `mvn -version`, toolchains config |
| Repository metadata | Remote Maven repo và local resolver cache | Versions/snapshots, plugin prefix mapping, negative resolution cache | `maven-metadata.xml`, `-U`, repository URL/log |

**Chú ý:** `settings.xml` không nên chứa project business code hoặc build plugin executions. Profiles trong settings chủ yếu chứa properties, repositories và pluginRepositories; một **POM profile** mới có thể cấu hình đầy đủ build/plugins. Không kỳ vọng hai loại profile hỗ trợ những phần XML giống hệt nhau.

## 3. Checklist lấy bằng chứng trước khi sửa

Trên môi trường gặp lỗi, ghi lại:

~~~bash
pwd
mvn -version
java -version
javac -version
mvn -B -ntp -e clean verify
~~~

Nếu ở Git checkout:

~~~bash
git rev-parse HEAD
git status --porcelain
~~~

Với Windows PowerShell:

~~~powershell
Get-Location
mvn -version
java -version
javac -version
$env:JAVA_HOME
Get-Command java
Get-Command javac
~~~

**Không vội thay POM.** Nếu máy A chạy Maven với JDK 17 nhưng CI dùng JDK 11, một lỗi compile target 17 không phải lỗi dependency. Nếu CI tự bật `-Pci` trong khi local đang bật `dev`, hai build chưa tương đương.

### Một bản ghi chẩn đoán tối thiểu

~~~text
Source SHA/tag: ...
Working directory: ...
Exact mvn command: ...
Maven version / Java runtime: ...
User and global settings paths: ...
Local repository path: ...
Active Maven profiles: ...
Effective property/repository: ...
Plugin:version:goal (execution) @ project: ...
First meaningful error / Caused by: ...
Remote repository or mirror ID: ...
Artifact coordinate: groupId:artifactId:version:type
Files/reports inspected: ...
Hypothesis / experiment / outcome: ...
Validation after fix: ...
~~~

Không đưa user password/token, proxy secret, internal endpoints chưa được phép hoặc toàn bộ debug log chưa redact vào ticket công khai.

## 4. Dự án Java 17 có profile dev/ci để thực hành

Ta dùng project độc lập `triage-app` có hai profiles: **dev** activeByDefault, **ci** bật bằng `-Pci`. POM lọc một resource `lab.properties` thành giá trị `DEV` hoặc `CI`. Java main đọc resource và in mode. Một JUnit test kiểm resource đúng giá trị được Maven truyền vào Surefire. CI profile còn bật một Enforcer rule yêu cầu **JDK chạy Maven** ở major version 17.

### Cấu trúc

~~~text
maven-triage-lab/
├── triage-app/
│   ├── pom.xml
│   └── src/
│       ├── main/
│       │   ├── java/dev/lesson/triage/DiagnosticApp.java
│       │   └── resources/lab.properties
│       └── test/java/dev/lesson/triage/DiagnosticAppTest.java
├── catalog-lib/             # thêm ở phần metadata SNAPSHOT
│   ├── pom.xml
│   └── src/main/java/dev/lesson/catalog/CatalogValue.java
├── remote-repo/             # tạo bằng Maven file:// demo
├── .m2-producer/            # local Maven cache thử nghiệm
├── .m2-snapshot-consumer/   # local Maven cache thứ hai
└── settings-bad.xml         # tùy chọn tạo riêng để thử lỗi mirror
~~~

Những thư mục local Maven cache và repository được tạo khi thực hành; không lưu vào Git và không động chạm `~/.m2` toàn máy.

### 4.1. Tệp `triage-app/pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.lesson</groupId>
    <artifactId>triage-app</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
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
            </resource>
        </resources>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-resources-plugin</artifactId>
                <version>3.3.1</version>
                <configuration>
                    <encoding>${project.build.sourceEncoding}</encoding>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.2</version>
                <configuration>
                    <failIfNoTests>true</failIfNoTests>
                    <systemPropertyVariables>
                        <lab.expectedMode>${lab.mode}</lab.expectedMode>
                    </systemPropertyVariables>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
                <configuration>
                    <archive>
                        <manifest>
                            <mainClass>dev.lesson.triage.DiagnosticApp</mainClass>
                        </manifest>
                    </archive>
                </configuration>
            </plugin>
        </plugins>
    </build>

    <profiles>
        <profile>
            <id>dev</id>
            <activation>
                <activeByDefault>true</activeByDefault>
            </activation>
            <properties>
                <lab.mode>DEV</lab.mode>
            </properties>
        </profile>

        <profile>
            <id>ci</id>
            <properties>
                <lab.mode>CI</lab.mode>
            </properties>
            <build>
                <plugins>
                    <plugin>
                        <groupId>org.apache.maven.plugins</groupId>
                        <artifactId>maven-enforcer-plugin</artifactId>
                        <version>3.5.0</version>
                        <executions>
                            <execution>
                                <id>require-maven-jdk17</id>
                                <phase>validate</phase>
                                <goals>
                                    <goal>enforce</goal>
                                </goals>
                                <configuration>
                                    <rules>
                                        <requireJavaVersion>
                                            <version>[17,18)</version>
                                        </requireJavaVersion>
                                    </rules>
                                </configuration>
                            </execution>
                        </executions>
                    </plugin>
                </plugins>
            </build>
        </profile>
    </profiles>
</project>
~~~

**Đúng mục đích của POM:**

- `activeByDefault=true` làm profile **dev** hoạt động khi không có profile khác trong cùng POM được kích hoạt.
- `-Pci` kích hoạt profile **ci** và làm profile activeByDefault dev trong cùng POM bị tắt theo quy tắc activation.
- `lab.mode` là Maven property ảnh hưởng cả Maven Resources Plugin filtering và Surefire system properties.
- `generate-resources/process-resources` sẽ sinh tệp `target/classes/lab.properties` với đúng giá trị profile.
- Enforcer execution `require-maven-jdk17` chỉ nằm trong **ci** profile và chạy ở `validate` khi CI profile active.
- Enforcer `requireJavaVersion [17,18)` kiểm Java **runtime chạy Maven**, không chỉ Java bytecode target.
- Compiler `maven.compiler.release=17` cấu hình Java language/API target; một JDK mới hơn (ví dụ JDK21) thường vẫn có thể compile `--release 17`, nên rule Enforcer là một policy **riêng**.
- Surefire `failIfNoTests=true` ngăn build xanh khi Maven không tìm thấy bài test.
- JAR có Main-Class, chạy được bằng `java -jar`.

**Không dùng `-DskipTests` khi thực hành chẩn đoán**, vì bỏ test có thể che vấn đề giữa resource filtering và cấu hình môi trường.

### 4.2. Tệp `triage-app/src/main/resources/lab.properties`

~~~properties
lab.mode=${lab.mode}
~~~

Đây là resource template. Với `<filtering>true</filtering>`, Maven tạo giá trị cuối cùng như `lab.mode=DEV` hoặc `lab.mode=CI` trong `target/classes`. File nguồn trong `src/main/resources` vẫn giữ biểu thức Maven.

### 4.3. Tệp `triage-app/src/main/java/dev/lesson/triage/DiagnosticApp.java`

~~~java
package dev.lesson.triage;

import java.io.IOException;
import java.io.InputStream;
import java.io.UncheckedIOException;
import java.util.Properties;

public final class DiagnosticApp {

    private DiagnosticApp() {
    }

    public static int add(int a, int b) {
        return Math.addExact(a, b);
    }

    public static String mode() {
        Properties properties = new Properties();

        try (InputStream input =
                DiagnosticApp.class.getResourceAsStream("/lab.properties")) {
            if (input == null) {
                throw new IllegalStateException(
                    "lab.properties missing from runtime classpath");
            }
            properties.load(input);
        } catch (IOException e) {
            throw new UncheckedIOException(
                "Cannot read lab.properties", e);
        }

        String value = properties.getProperty("lab.mode");
        if (value == null || value.isBlank()) {
            throw new IllegalStateException(
                "lab.mode was not populated by Maven resource filtering");
        }
        return value.trim();
    }

    public static void main(String[] args) {
        System.out.println("MODE=" + mode());
        System.out.println("SUM=" + add(2, 3));
    }
}
~~~

`Properties.load(InputStream)` sử dụng quy tắc encoding của Java properties; trong ví dụ **DEV/CI là ASCII**, nên không mơ hồ. Nếu resource có tiếng Việt, cần chọn cách đọc UTF-8 phù hợp thay vì mặc định nhận InputStream.

### 4.4. Tệp `triage-app/src/test/java/dev/lesson/triage/DiagnosticAppTest.java`

~~~java
package dev.lesson.triage;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;

class DiagnosticAppTest {

    @Test
    void sumsCorrectly() {
        assertEquals(5, DiagnosticApp.add(2, 3));
    }

    @Test
    void filteredResourceMatchesMavenProfileProperty() {
        String expected = System.getProperty("lab.expectedMode");
        assertNotNull(expected, "Surefire property missing");
        assertTrue(expected.equals("DEV") || expected.equals("CI"));
        assertEquals(expected, DiagnosticApp.mode());
    }
}
~~~

**Quan trọng:** hai đầu vào của test profile được Maven cấp từ cùng property, nên test xác minh **resource filtering nhất quán với Surefire injection**; để chứng minh profile thực sự là dev hay ci, còn phải đọc **active-profiles** và kiểm stdout/effective POM. Đây là giới hạn có chủ đích, không được phóng đại JUnit test thành kiểm toán toàn môi trường.

## 5. Chạy baseline trong sandbox và ghi kết quả

Bash/Linux/macOS, đứng trong `maven-triage-lab`:

~~~bash
LAB="$(pwd)"
REPO="$LAB/.m2-producer"

mvn -B -ntp "-Dmaven.repo.local=$REPO" \
  -f triage-app/pom.xml clean verify

java -jar triage-app/target/triage-app-1.0.0.jar
~~~

Với JDK17 hợp lệ, Maven Central/mirror hoạt động, và không có profile khác can thiệp, **stdout từ ứng dụng** là chính xác:

~~~text
MODE=DEV
SUM=5
~~~

**Maven output** còn bao gồm reports và BUILD SUCCESS; ví dụ trên chỉ ghi stdout của Java main.

Chạy profile ci:

~~~bash
mvn -B -ntp "-Dmaven.repo.local=$REPO" \
  -f triage-app/pom.xml -Pci clean verify

java -jar triage-app/target/triage-app-1.0.0.jar
~~~

Với Maven chạy trên JDK17, Enforcer pass. Stdout chính xác:

~~~text
MODE=CI
SUM=5
~~~

Hai lệnh tạo JAR ở **cùng đường dẫn**, nhưng resource được filter theo profile nên **nội dung JAR có thể khác**; đừng coi hai build là cùng binary chỉ vì chung version/name.

### Baseline trên PowerShell

~~~powershell
$lab = (Get-Location).Path
$repo = Join-Path $lab ".m2-producer"
mvn -B -ntp "-Dmaven.repo.local=$repo" -f triage-app/pom.xml clean verify
java -jar triage-app/target/triage-app-1.0.0.jar
mvn -B -ntp "-Dmaven.repo.local=$repo" -f triage-app/pom.xml -Pci clean verify
java -jar triage-app/target/triage-app-1.0.0.jar
~~~

PowerShell dùng các lệnh trên một dòng để tránh nhầm ký tự nối dòng Bash.

## 6. Nhánh lỗi PROFILE: cùng POM nhưng giá trị bị đổi

Giả sử máy cá nhân in `MODE=DEV`, CI in `MODE=CI`. Đó không nhất thiết là bug Java; profile thay đổi **resource trong JAR**.

### Kiểm profile nào được kích hoạt

~~~bash
mvn -B -ntp "-Dmaven.repo.local=$REPO" -f triage-app/pom.xml \
  org.apache.maven.plugins:maven-help-plugin:3.5.2:active-profiles

mvn -B -ntp "-Dmaven.repo.local=$REPO" -f triage-app/pom.xml \
  -Pci org.apache.maven.plugins:maven-help-plugin:3.5.2:active-profiles
~~~

Dự kiến trường hợp đầu có profile dev trong project; trường hợp hai có ci.

### Kiểm giá trị property thực sự

~~~bash
mvn -B -ntp "-Dmaven.repo.local=$REPO" -f triage-app/pom.xml \
  org.apache.maven.plugins:maven-help-plugin:3.5.2:evaluate \
  -Dexpression=lab.mode -q -DforceStdout

mvn -B -ntp "-Dmaven.repo.local=$REPO" -f triage-app/pom.xml -Pci \
  org.apache.maven.plugins:maven-help-plugin:3.5.2:evaluate \
  -Dexpression=lab.mode -q -DforceStdout
~~~

Giá trị kỳ vọng tương ứng: **DEV** và **CI**. `-q -DforceStdout` được dùng khi muốn nhận trực tiếp giá trị; các logs không liên quan có thể đã bị suppress.

### Xem effective POM

~~~bash
mvn -B -ntp "-Dmaven.repo.local=$REPO" -f triage-app/pom.xml -Pci \
  org.apache.maven.plugins:maven-help-plugin:3.5.2:effective-pom \
  -Dverbose
~~~

Đọc phần properties, Enforcer execution và active profile effects. `-Dverbose` thêm chú thích nguồn cấu hình trong effective POM giúp biết một giá trị đến từ parent/profile/POM nào.

### Trường hợp profile active nhưng output vẫn bất ngờ

~~~bash
mvn -B -ntp "-Dmaven.repo.local=$REPO" -f triage-app/pom.xml \
  -Pci -Dlab.mode=DEV clean verify
~~~

CI profile **vẫn active**, Enforcer vẫn được bind, nhưng CLI user property `-Dlab.mode=DEV` có thể ghi đè property cùng tên trong POM. Kết quả resource sẽ là **DEV**, không phải CI. Vì vậy **active profile** và **effective value** đều phải được kiểm.

### Những bẫy profile thường gặp

- `activeByDefault` của một POM có thể tự tắt khi một profile khác trong chính POM được kích hoạt; không chỉ cộng thêm mọi profile.
- Profiles trong POM và settings có phạm vi khai báo XML khác nhau.
- Profiles được resolved sớm, bản thân profile definition không được inherit nguyên vẹn; **effects của active profiles** có thể được inherit.
- JDK, OS, properties hoặc file existence có thể tự kích hoạt profile.
- Các files khác nhau giữa CI và local có thể làm file-activated profile khác nhau.
- Nếu CI dùng `-Pci` nhưng local không, bạn chưa kiểm cùng build plan.
- Nếu Maven 4 được dùng thay vì Maven 3, cách xử lý profile ID không tồn tại nghiêm ngặt hơn; cần kiểm version và command.

**Kết luận nhánh PROFILE:** đừng sửa Java trước khi chứng minh **profile nào active, property cuối cùng là gì và resource/plugin nào bị ảnh hưởng**.

## 7. Nhánh lỗi JDK: Maven runtime và compiler target là hai thứ

Khi log có:

~~~text
release version 17 not supported
~~~

hoặc:

~~~text
invalid target release: 17
~~~

hãy hỏi **JDK nào đang chạy Maven**. Lệnh kiểm:

~~~bash
mvn -version
java -version
javac -version
echo "$JAVA_HOME"
command -v java
command -v javac
~~~

Trong PowerShell:

~~~powershell
mvn -version
java -version
javac -version
$env:JAVA_HOME
Get-Command java
Get-Command javac
~~~

**`mvn -version` là dấu vết quan trọng**, vì nó hiển thị Java runtime Maven đã khởi động. `java -version` và `javac -version` từ shell có thể trỏ đến installation khác, tùy JAVA_HOME/PATH.

### Ba khái niệm cần phân biệt

| Khái niệm | Ví dụ | Ảnh hưởng |
| --- | --- | --- |
| Java chạy Maven | `mvn -version` → Java 11/17/21 | Plugin runtime, Enforcer RequireJavaVersion |
| Java compiler/toolchain | JDK được Maven Compiler Plugin chọn | Phiên bản javac và khả năng compile |
| Java release target | `maven.compiler.release=17` | Language/API/classfile Java 17 |

JDK21 có thể compile với `--release 17`, nhưng trong demo **-Pci** Enforcer yêu cầu Maven runtime Java17, nên CI vẫn **fail** ở `validate` trên JDK21. Đó là policy của ví dụ, không phải Java21 không thể biên dịch Java17.

Với JDK11, Compiler Plugin không thể dùng compiler đó để tạo `--release 17` (nếu không có toolchain khác), nên build có thể fail trước khi test.

### Dùng Enforcer để chẩn đoán rõ ràng

Trong POM demo, CI profile có execution:

~~~xml
<execution>
    <id>require-maven-jdk17</id>
    <phase>validate</phase>
    <goals>
        <goal>enforce</goal>
    </goals>
    <configuration>
        <rules>
            <requireJavaVersion>
                <version>[17,18)</version>
            </requireJavaVersion>
        </rules>
    </configuration>
</execution>
~~~

Đây là **fragment lấy từ POM đầy đủ**, không phải plugin độc lập. Nếu Java runtime Maven là 21, lỗi có thể có dạng:

~~~text
maven-enforcer-plugin:3.5.0:enforce
(require-maven-jdk17) @ triage-app
RequireJavaVersion failed
~~~

Đừng xóa rule để che lỗi. Kiểm runner của CI có thiết lập Java17 trước bước Maven và chạy lại.

### Khi cần JDK compiler khác JDK chạy Maven

Maven Toolchains cho phép plugin biết một JDK cụ thể dùng để biên dịch/test, tách khỏi JDK chạy Maven. Ví dụ **fragment tùy chọn** trong `build/plugins`:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-toolchains-plugin</artifactId>
    <version>3.3.0</version>
    <executions>
        <execution>
            <goals>
                <goal>toolchain</goal>
            </goals>
        </execution>
    </executions>
    <configuration>
        <toolchains>
            <jdk>
                <version>[17,18)</version>
            </jdk>
        </toolchains>
    </configuration>
</plugin>
~~~

Trong môi trường developer/CI cần có `~/.m2/toolchains.xml` hoặc file được chỉ định bằng `-t`, ví dụ **mẫu không độc lập với path thực tế**:

~~~xml
<toolchains>
    <toolchain>
        <type>jdk</type>
        <provides>
            <version>17</version>
        </provides>
        <configuration>
            <jdkHome>/path/to/installed/jdk-17</jdkHome>
        </configuration>
    </toolchain>
</toolchains>
~~~

**Không tự điền path giả rồi kỳ vọng toolchain hoạt động.** Dùng đường dẫn JDK17 thật. Toolchains chỉ ảnh hưởng các plugins biết dùng toolchain; nếu Enforcer vẫn kiểm `RequireJavaVersion` của **Maven runtime** thì chọn JDK17 compiler bằng toolchain không tự làm Enforcer pass khi Maven chạy Java21.

## 8. Nhánh lỗi SETTINGS: nhìn đúng file settings đã có hiệu lực

Maven settings thường nằm tại:

- User settings: `~/.m2/settings.xml`.
- Global settings: `MAVEN_HOME/conf/settings.xml` (tùy cài đặt).
- Một file khác được chỉ định qua `mvn -s path/to/settings.xml`.
- Local repository mặc định: `~/.m2/repository`, trừ khi settings hoặc `-Dmaven.repo.local` đổi.

Settings có các mục như `mirrors`, `servers`, `proxies`, `profiles`, `activeProfiles`, `pluginGroups`. Nó không phải chỗ để đặt Java source, dependencyManagement hay plugin executions của project.

### Xem effective settings mà không tự in password

~~~bash
mvn -B -ntp "-Dmaven.repo.local=$REPO" -f triage-app/pom.xml \
  org.apache.maven.plugins:maven-help-plugin:3.5.2:effective-settings
~~~

Goal này kết hợp global/user settings và hiển thị XML đã tính. Mặc định nó **ẩn password**. Không dùng tham số `-DshowPasswords=true` chỉ để debug, và vẫn redact usernames, URLs, server IDs nội bộ trước khi chia sẻ.

### Mirrors: chỉ một mirror được chọn

Một fragment settings ví dụ:

~~~xml
<mirrors>
    <mirror>
        <id>company-mirror</id>
        <url>https://repo.example.invalid/maven-public</url>
        <mirrorOf>central</mirrorOf>
    </mirror>
</mirrors>
~~~

**Đây là địa chỉ ví dụ không có thật.** Nó diễn tả Maven có thể đổi truy cập repository ID `central` sang mirror `company-mirror`. Nếu URL sai hoặc mirror không proxy đủ artifacts, build fail dù POM dependency hợp lệ.

- `mirrorOf=central` thay Central.
- `mirrorOf=*` ánh xạ mọi repositories, kể cả repositories nội bộ/file-based trừ khi cấu hình ngoại lệ.
- `external:*` chọn repositories bên ngoài localhost/file repositories.
- `*,!repo-local` loại trừ repository ID cụ thể (không thêm khoảng trắng thừa).
- Maven không kết hợp nhiều mirrors phù hợp thành một nhóm; nó chọn mapping tương ứng theo thứ tự ưu tiên, match ID chính xác trước wildcard.
- Nếu mirror ID đã được chọn, credentials trong settings thường cần `server id` khớp **ID của mirror**.

### Servers và credentials

Fragment minh họa **không chứa token thật**:

~~~xml
<servers>
    <server>
        <id>company-mirror</id>
        <username>provided-by-secure-ci</username>
        <password>PLACEHOLDER_ONLY_NOT_A_SECRET</password>
    </server>
</servers>
~~~

**Không sử dụng plaintext placeholder trên vào triển khai thật.** CI nên inject credentials bằng secret manager và settings được tạo an toàn; không commit password, token hoặc privateKey vào Git. Khi kiểm HTTP401/403, đối chiếu **server ID**, auth method, tài khoản có quyền repo và trạng thái của repository; không giả sử mọi 403 đều do sai password.

Đối với Maven3.10+ và Maven4, credential origin-binding còn phụ thuộc scheme/host/port của repository/mirror; khi migrate giữa phiên bản cần kiểm tài liệu settings tương ứng. Đây không phải thay thế cho cấu hình secret đúng.

### Proxy và certificate

Nếu corporate proxy/TLS gây lỗi, cần xác định Maven chạy trong network nào, system trust store/JDK nào, proxy trong settings có active hay không, và URL thật đã được mirror chọn. Không tắt TLS validation hoặc bật HTTP không mã hóa chỉ để build pass.

## 9. Thực hành an toàn: một settings mirror cố tình sai

**Chỉ dùng trong sandbox học tập.** Tạo một file mới `settings-bad.xml` trong `maven-triage-lab`:

~~~xml
<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0"
          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
          xsi:schemaLocation="http://maven.apache.org/SETTINGS/1.2.0 https://maven.apache.org/xsd/settings-1.2.0.xsd">
    <mirrors>
        <mirror>
            <id>broken-mirror</id>
            <mirrorOf>*</mirrorOf>
            <url>https://repo.example.invalid/not-a-real-repository</url>
        </mirror>
    </mirrors>
</settings>
~~~

Domain `example.invalid` không phải repository Maven thật. Nếu cần tạo một **negative test** với local repo chưa cache plugins, chạy một lệnh ở workspace test riêng:

~~~bash
LAB="$(pwd)"
mvn -B -ntp -s "$LAB/settings-bad.xml" \
  "-Dmaven.repo.local=$LAB/.m2-broken" \
  -f triage-app/pom.xml clean verify
~~~

**Kỳ vọng:** Maven có thể fail khi tải plugins/dependencies qua broken mirror. Đó là failure **do settings**, không phải Java code. Không hứa một dòng HTTP cụ thể vì lỗi thực tế tùy DNS/network/cache. Nếu Maven đã có đủ artifacts trong cache riêng đó, một lệnh có thể chưa chạm remote; muốn tái hiện thì dùng local repo mới và mạng được kiểm soát.

**Phục hồi:** dùng lại settings hợp lệ và local repo được phép. Không xóa hay sửa `~/.m2/settings.xml` toàn máy hoặc corporate mirror để phục vụ bài tập.

### Chẩn đoán từ logs

Tìm lines kiểu:

~~~text
Using mirror broken-mirror for central
Could not transfer artifact ... from/to broken-mirror
Unknown host / timeout / handshake / authentication error
~~~

Đây là những **mẫu triệu chứng**, không phải output chính xác của một run thật. Maven `-X` cho thấy repository/mirror được chọn nhưng có thể tiết lộ dữ liệu nhạy cảm. Redact trước khi lưu ticket.

**Điểm quan trọng:** khi settings mirrorOf=* trỏ sai, thay version của JUnit hay Maven Compiler Plugin thường **không giải quyết root cause**.

## 10. Dependency repositories và plugin repositories không giống nhau

Trong Maven có ít nhất hai kiểu artifact được resolver tìm:

- **Project dependency**: JAR/POM ở `<dependencies>`.
- **Build plugin**: Maven Compiler, Surefire, custom plugins ở `build/plugins`.

POM/settings có thể khai **repositories** cho dependencies và **pluginRepositories** cho plugins. Một mirror có thể chuyển hướng các repositories theo cấu hình. Vì vậy:

- `Could not resolve plugin org.apache.maven.plugins:maven-compiler-plugin` không nhất thiết chứng minh dependency JUnit sai.
- `Could not find artifact dev.lesson:triage-catalog:jar:1.0.0-SNAPSHOT` không nhất thiết chứng minh plugin repository sai.
- Plugin prefix lookup (ví dụ `mvn demo:goal`) còn phụ thuộc `pluginGroups` và group-level plugin metadata.

Khi debug, ghi **GAV**, repo ID và lỗi HTTP chính xác. Đừng chỉ viết “repo Maven lỗi”.

### Thứ tự repository và mirrors

Maven tổng hợp repositories từ effective settings, effective POM và dependency context; profiles active có thể thêm repositories. Sau đó Maven áp mirror mapping **trước khi tải**. Đọc:

~~~bash
mvn -B -ntp "-Dmaven.repo.local=$REPO" -f triage-app/pom.xml \
  org.apache.maven.plugins:maven-help-plugin:3.5.2:effective-settings

mvn -B -ntp "-Dmaven.repo.local=$REPO" -f triage-app/pom.xml \
  org.apache.maven.plugins:maven-help-plugin:3.5.2:effective-pom \
  -Dverbose
~~~

Không suy thứ tự chỉ từ danh sách repositories viết trong một POM; settings profiles và mirrors có thể thay đổi route cuối cùng.

## 11. Repository metadata là gì và nó khác artifact file thế nào?

Maven repositories có các file `maven-metadata.xml` để giúp khám phá versions, snapshots và plugin prefix mapping.

| Cấp metadata | Vị trí logic | Dùng để |
| --- | --- | --- |
| G-level, theo groupId | `dev/lesson/maven-metadata.xml` | Plugin prefix → plugin artifactId |
| A-level, theo groupId/artifactId | `dev/lesson/triage-catalog/maven-metadata.xml` | List versions, latest/release/lastUpdated |
| V-level, theo SNAPSHOT baseVersion | `dev/lesson/triage-catalog/1.0.0-SNAPSHOT/maven-metadata.xml` | Map base SNAPSHOT sang timestamped snapshot files |

Trong một Maven remote snapshot repository, các tệp thực có thể đặt tên:

~~~text
triage-catalog-1.0.0-20261110.120001-1.jar
triage-catalog-1.0.0-20261110.120001-1.pom
~~~

Timestamp/build number ở trên **chỉ minh họa**, không phải output của một lần publish thực tế. Resolver có thể đọc V-level metadata để biết version timestamp nào cần tải.

### Metadata khác POM/JAR

- **JAR** chứa mã đã biên dịch.
- **POM** chứa tọa độ và dependency model.
- **maven-metadata.xml** giúp Maven biết version nào có thể được chọn hoặc file snapshot nào tương ứng.
- **.lastUpdated** trong local repo có thể ghi nhận kết quả/negative cache của các lần thử fetch.
- **maven-metadata-[repoId].xml** trong local repo có thể gắn metadata được lưu theo repository ID.
- **_remote.repositories** ghi thông tin nguồn artifact trong local resolver, không phải metadata để người dùng tự sửa nhằm “khôi phục” GAV.

Một POM/JAR **đúng tên và tồn tại ở remote** chưa đảm bảo client có thể tìm thấy nếu snapshot metadata bị thiếu, repository policy chặn snapshots, hoặc mirror trỏ sai.

## 12. Lab file://: tự tạo SNAPSHOT repository không cần server thật

Để nhìn tận mắt V-level metadata, tạo project Maven `catalog-lib` độc lập cạnh `triage-app`.

### 12.1. Tệp `catalog-lib/pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.lesson</groupId>
    <artifactId>triage-catalog</artifactId>
    <version>1.0.0-SNAPSHOT</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-resources-plugin</artifactId>
                <version>3.3.1</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 12.2. Tệp `catalog-lib/src/main/java/dev/lesson/catalog/CatalogValue.java`

~~~java
package dev.lesson.catalog;

public final class CatalogValue {
    private CatalogValue() {
    }

    public static String label() {
        return "CATALOG_1";
    }

    public static void main(String[] args) {
        System.out.println(label());
    }
}
~~~

Nếu Java classes đã được compile, chạy:

~~~bash
java -cp catalog-lib/target/classes dev.lesson.catalog.CatalogValue
~~~

Stdout chính xác:

~~~text
CATALOG_1
~~~

### 12.3. Build trong sandbox

Từ root `maven-triage-lab`, Bash:

~~~bash
LAB="$(pwd)"
PRODUCER_CACHE="$LAB/.m2-producer"
REMOTE_REPO="$LAB/remote-repo"
mkdir -p "$REMOTE_REPO"

(
  cd catalog-lib

  mvn -B -ntp "-Dmaven.repo.local=$PRODUCER_CACHE" \
    clean package

  mvn -B -ntp "-Dmaven.repo.local=$PRODUCER_CACHE" \
    org.apache.maven.plugins:maven-deploy-plugin:3.2.0:deploy-file \
    "-Dfile=$PWD/target/triage-catalog-1.0.0-SNAPSHOT.jar" \
    "-DpomFile=$PWD/pom.xml" \
    -DrepositoryId=lab-file \
    "-Durl=file://$REMOTE_REPO"
)
~~~

**Ý nghĩa:**

- `clean package` tạo snapshot JAR và POM trong project sandbox.
- Goal **deploy:deploy-file** chuyển JAR/POM đã có vào Maven repository ở path `file://`, **không phải remote Internet**.
- `repositoryId=lab-file` đặt ID của target local file repository; demo này không cần username/password.
- Maven Deploy Plugin cập nhật metadata cần thiết trong `remote-repo`. Với SNAPSHOT, mục tiêu là quan sát cả đường dẫn baseVersion lẫn timestamped files/metadata.
- Repo đích chỉ nằm trong `maven-triage-lab/remote-repo` do người học mới tạo. **Không dùng URL của repository thật hoặc GAV/version đang được đội khác sử dụng.**

### 12.4. Kiểm metadata ở remote

~~~bash
find remote-repo/dev/lesson/triage-catalog \
  -name "maven-metadata.xml" -print

cat remote-repo/dev/lesson/triage-catalog/1.0.0-SNAPSHOT/maven-metadata.xml
~~~

Bạn sẽ thấy thông tin liên quan `snapshot`/`snapshotVersions`, gồm timestamp/build number do tool tạo. Không bịa timestamp cố định để assert. Cần xác minh:

- File JAR/POM timestamped thực tồn tại dưới `1.0.0-SNAPSHOT`.
- Metadata trỏ tới version có file thật.
- Artifact group/artifact/baseVersion đúng.
- Repository được Maven consumer sử dụng là **chính file URL này**, không phải một mirror khác.

Nếu metadata không có hoặc cấu trúc khác, mở log deploy để kiểm plugin thật đã chạy, repo được ghi, và có thể package trên filesystem nào.

### 12.5. Resolve SNAPSHOT từ một local cache khác

Dùng cache **consumer mới**, không dùng cache producer đã có artifact:

~~~bash
CONSUMER_CACHE="$LAB/.m2-snapshot-consumer"

mvn -B -ntp "-Dmaven.repo.local=$CONSUMER_CACHE" \
  -f triage-app/pom.xml \
  org.apache.maven.plugins:maven-dependency-plugin:3.9.0:get \
  -Dartifact=dev.lesson:triage-catalog:1.0.0-SNAPSHOT \
  "-DremoteRepositories=lab-file::default::file://$REMOTE_REPO" \
  -Dtransitive=false
~~~

Lệnh dùng Maven Dependency Plugin goal **get** để resolve **một artifact** từ remote file repo. `-Dtransitive=false` giữ scope bài tập đơn giản, không resolve dependencies đi kèm của artifact demo. Plugins của Maven vẫn có thể được tải từ Central/mirror; `remoteRepositories` chỉ bổ sung repository để tìm artifact được yêu cầu, không tự thay thế mọi plugin repository.

**Kỳ vọng:** Maven có thể tìm SNAPSHOT đúng trong file repo và lưu vào `.m2-snapshot-consumer`. Xem:

~~~bash
find .m2-snapshot-consumer/dev/lesson/triage-catalog \
  -maxdepth 2 -type f -print
~~~

Các file/tên local có thể khác layout timestamped của remote, tùy resolver; **đừng giả định local JAR nhất thiết có cùng tên timestamped với remote**.

## 13. Thử lỗi metadata/negative cache theo cách không phá dữ liệu

### Case 1: Yêu cầu version không có

Trong khi remote file repo mới chỉ có `1.0.0-SNAPSHOT`, chạy:

~~~bash
mvn -B -ntp "-Dmaven.repo.local=$CONSUMER_CACHE" \
  -f triage-app/pom.xml \
  org.apache.maven.plugins:maven-dependency-plugin:3.9.0:get \
  -Dartifact=dev.lesson:triage-catalog:1.0.1-SNAPSHOT \
  "-DremoteRepositories=lab-file::default::file://$REMOTE_REPO" \
  -Dtransitive=false
~~~

**Dự kiến failure** do `1.0.1-SNAPSHOT` chưa được publish. Đây là lỗi **version/remote content** không phải JDK hay compiler plugin.

### Case 2: Maven báo failure bị cache

Nếu lần get thất bại, Maven có thể ghi negative-cache records ở local repo và báo tương tự:

~~~text
Failure to find ... was cached in the local repository,
resolution will not be reattempted until the update interval ...
~~~

Thông báo tùy Maven/Resolver version và repository policy. Các file `*.lastUpdated` có thể cho biết failed attempt. Đừng mặc định cache bị hỏng; nó có thể **đang ghi lại đúng sự thật rằng artifact chưa tồn tại ở lần tìm trước**.

### Case 3: Bắt Maven kiểm lại theo update policy

~~~bash
mvn -B -ntp -U "-Dmaven.repo.local=$CONSUMER_CACHE" \
  -f triage-app/pom.xml \
  org.apache.maven.plugins:maven-dependency-plugin:3.9.0:get \
  -Dartifact=dev.lesson:triage-catalog:1.0.1-SNAPSHOT \
  "-DremoteRepositories=lab-file::default::file://$REMOTE_REPO" \
  -Dtransitive=false
~~~

`-U` yêu cầu kiểm lại missing releases và updated snapshots theo Maven CLI; **nó không thể tạo artifact chưa được publish**. Khi repo vẫn không có `1.0.1-SNAPSHOT`, lệnh vẫn phải fail.

Để thực sự sửa case này, xuất bản **1.0.1-SNAPSHOT** (sau khi sửa version trong catalog-lib POM, build và publish đúng artifact) hoặc yêu cầu đúng `1.0.0-SNAPSHOT`; không xóa metadata để “ép” Maven thấy version không tồn tại.

### Case 4: `-o` và `-nsu`

| Cờ | Ý nghĩa | Tác dụng chẩn đoán |
| --- | --- | --- |
| `-U` | Force re-check missing releases/updated snapshots | Hữu ích sau khi remote artifact đã được publish/sửa metadata |
| `-nsu` | Không cập nhật snapshots theo policy | Có thể giữ snapshot đã cache, tránh refresh ngoài ý muốn |
| `-o` | Offline | Chỉ dùng những artifacts/plugins đã có trong cache |
| `-Dmaven.repo.local=path` | Chọn local Maven repository | Tách môi trường, tránh lấy nhầm artifact cũ |
| `-X` | Maven debug | Xem repo/mirror/cache trace; cần redact secrets |
| `-s path` | Dùng file user settings khác | So sánh settings có/không có mirror |
| `-Pci` | Bật profile ci | Kiểm build plan/config riêng của CI |

Nếu dùng `-o` với một local repo trống, Maven có thể fail ngay tại **plugin resolution**, trước khi tới artifact SNAPSHOT mà bạn muốn debug. Vì vậy không suy “metadata snapshot sai” từ một offline failure chung chung.

### Case 5: metadata và artifact không khớp

Trong một repository thật, có thể gặp metadata version level trỏ tới timestamped JAR đã bị xóa, publish chưa đồng bộ POM/JAR, hoặc mirror/cache có bản cũ. Cần:

1. Xác nhận **đúng repository URL sau mirror mapping**.
2. Đọc remote `maven-metadata.xml` tại đúng GAV/baseVersion.
3. Xác nhận file timestamped JAR/POM thực tồn tại, không chỉ version list.
4. Kiểm repository snapshots/release policy và quyền.
5. Kiểm local metadata cache/update interval, rồi thử `-U` sau khi remote đã đúng.
6. Dùng local repo thử nghiệm mới để phân biệt **cache cũ** với **remote server**.
7. Nếu vẫn fail, báo repository maintainer sửa metadata/asset consistency; không sửa tay metadata trên remote sản xuất nếu không có quy trình quản trị.

### Case 6: khác repository ID

Local cache metadata theo repository ID có thể khiến cùng một artifact được resolver xử lý khác khi bạn đổi mirror/repository ID. Không chỉ so URL bằng mắt; xem `maven-metadata-[repoId].xml`, `_remote.repositories` và effective settings để biết artifact đến từ repository nào.

## 14. Thứ tự thực hiện thử nghiệm để phân biệt bốn root causes

Một trình tự ít tạo lỗi giả:

**A. Reproduce baseline**

~~~bash
mvn -B -ntp "-Dmaven.repo.local=$REPO" \
  -f triage-app/pom.xml clean verify
~~~

Kỳ vọng JDK17 và dev profile tạo stdout `MODE=DEV`. Nếu không, điều tra settings/JDK trước.

**B. Bật CI profile mà không đổi JDK/settings**

~~~bash
mvn -B -ntp "-Dmaven.repo.local=$REPO" \
  -f triage-app/pom.xml -Pci clean verify
~~~

Nếu JDK17, kỳ vọng `MODE=CI`. Nếu JDK khác, Enforcer policy có thể chặn.

**C. So settings**

Đọc effective-settings với settings mặc định, sau đó nếu có file riêng, truyền `-s` cùng cache đã kiểm soát. Không chép secrets vào logs.

**D. So Maven metadata**

Với file:// repo riêng, đọc `maven-metadata.xml` từ remote, rồi dùng Dependency Plugin get với cache riêng. Thử một GAV thiếu để quan sát cached not found; giải thích vì sao `-U` không sửa được GAV sai.

**E. Xác nhận full build**

Sau khi sửa settings/profile/JDK/repository, chạy lại **cùng invocation CI mong muốn** và đọc Surefire reports; không tuyên bố fixed chỉ vì một lệnh `help:evaluate` hiển thị đúng property.

## 15. Một số cặp nguyên nhân dễ bị nhầm

| Quan sát | Có thể là A | Có thể là B | Phép phân biệt |
| --- | --- | --- | --- |
| `Could not find artifact` | GAV sai | Mirror trỏ repo không có artifact | So GAV và actual mirror/repo URL |
| `Cannot access central` | Proxy/TLS | Offline mode trong settings | Effective settings, network, `-o`/`offline` |
| Compile Java17 fail | Maven chạy JDK11 | Maven compiler/toolchain chọn JDK khác | `mvn -version`, compiler config |
| CI JDK21 fail, local JDK17 pass | Enforcer require 17 | Java API incompatibility | Goal/execution và `Caused by` |
| JAR khác trong cùng commit | `-Pci` lọc resource khác | JDK/plugin/dependency resolution khác | Effective POM, sha256, JDK |
| Snapshot mới không xuất hiện | `-nsu`/update policy/cache | Repo metadata chưa đổi hoặc mirror cũ | Local/remote metadata và `-U` |
| Plugin goal không tìm thấy | Plugin prefix metadata | Plugin GAV/version không có | Fully qualified goal và help:describe |
| `401` sau đổi mirror | Credentials id không khớp | Repo account hết quyền | Effective server/mirror IDs, policy |
| Dev profile tự biến mất | Một profile khác trong cùng POM active | Settings/CLI override property | `active-profiles`, `help:evaluate` |
| Tests pass nhưng build fail | Enforcer policy | Artifact resolver fail sau test phase | Đọc đúng Maven goal/execution |
| Local pass, CI fail | CI settings/proxy khác | CI repository cache sạch | Cùng settings/JDK với fresh cache |

**Không sửa bằng trực giác:** nếu log chỉ nói “Failed to execute goal”, cần đọc plugin:version:goal, execution ID, project artifactId và nguyên nhân sâu hơn.

## 16. Lưu log chẩn đoán mà không làm mất exit code

Bash:

~~~bash
set -o pipefail
mvn -B -ntp -Pci -e -f triage-app/pom.xml clean verify 2>&1 | tee build.log
~~~

`set -o pipefail` giúp pipeline giữ exit failure của Maven thay vì chỉ thấy status của `tee`. Sau đó tìm:

~~~bash
grep -nE 'Failed to execute goal|Caused by:|Reactor Summary|Could not resolve|Could not transfer|RequireJavaVersion|Tests run:' build.log
~~~

**Tìm được dòng không có nghĩa tìm được nguyên nhân.** Quay lên xem goal banner, execution ID, module, source line và repository URL (đã redact).

Khi cần thêm chi tiết:

~~~bash
mvn -B -ntp -e -f triage-app/pom.xml clean verify
mvn -B -ntp -X -f triage-app/pom.xml clean verify
~~~

`-e` thêm error stack; `-X` có thể lộ file paths, usernames, internal registry endpoints, system properties và environment data. Dùng để debug cục bộ, không tự upload log nguyên văn lên ticket.

## 17. Chẩn đoán trên CI: giữ cùng một nguồn sự thật

Một CI job tối thiểu nên ghi:

- Source commit/tag đã check out.
- Maven wrapper/Maven version nếu có và output `mvn -version`.
- JDK được setup trước Maven; nếu Maven toolchain riêng, log JDK compiler/test.
- Exact Maven command, `-P`, `-D`, `-s`, working directory.
- File settings được cấp (chỉ pathname và mirror/server IDs đã redact).
- Local Maven cache path và cache strategy.
- Effective profiles/property cần thiết, không dump passwords.
- Artifact GAV và repository IDs mà Maven thực sự resolve.
- Surefire/Failsafe reports và build exit code.
- Bản Maven metadata/HTTP status liên quan khi xảy ra SNAPSHOT lỗi.
- Kết quả targeted reproduction và full `clean verify` sau fix.

### Quy trình CI hợp lý

~~~text
checkout
  -> setup JDK đúng phiên bản
  -> chuẩn bị settings qua secret manager (không commit credentials)
  -> mvn -version
  -> print active profile names and safe properties
  -> mvn -B -ntp -Pci clean verify
  -> archive test reports, triage logs (redacted)
  -> chỉ phát hành artifact sau quality gates
~~~

Nếu dùng Maven Toolchains, bảo đảm toolchains.xml JDK paths tồn tại trong runner. Một POM hợp lệ không tự cài JDK.

**Cache policy:** SNAPSHOT metadata và local negative-cache records có thể khác nhau giữa CI runs; để kiểm root cause, dùng một lần chạy với **local repository riêng** nhưng không tùy tiện xóa global cache của đồng nghiệp.

## 18. Những cách chữa sai thường gặp

| Cách làm sai | Vì sao không giải quyết root cause | Cách đúng |
| --- | --- | --- |
| Xóa `~/.m2` mỗi khi Maven fail | Mất thông tin, chậm và có thể che cache/policy issue | Dùng isolated repo, inspect metadata trước |
| Gọi `-U` cho mọi lỗi | Không tạo artifact thiếu, không sửa ACL/TLS/JDK | Chỉ dùng khi refresh metadata hợp lý |
| Dùng `-o` để “tránh lỗi repo” | Cache thiếu sẽ gây lỗi mới | Kiểm nguồn remote và chuẩn bị offline cache |
| Tắt Enforcer rule | Che JDK policy violation | Dùng runtime/toolchain hợp policy |
| Thay `maven.compiler.release` thành 8 để build pass | Thay hợp đồng Java/API, che yêu cầu Java17 | Setup đúng JDK/target đã thiết kế |
| Thêm password vào POM | Rò rỉ secret, sai nơi chứa config | Settings/CI secret injection |
| Tắt TLS validation | Tăng rủi ro MITM/supply-chain | Sửa trust store/proxy/cert hợp lệ |
| Đổi dependency thành version mới nhất | Build không tái lập, khó debug | Pin GAV đúng và kiểm repo metadata |
| Thêm repository mới vào mọi POM | Có thể phá policy bảo mật/lookup | Dùng repository manager/approved mirrors |
| Bật `-fn` hoặc `skipTests` | Làm CI xanh giả | Giữ quality gate và sửa nguyên nhân |
| Chỉ xem source POM | Bỏ sót parent, settings, active profile | Effective POM/settings và properties |
| Nhìn `java -version` mà không xem `mvn -version` | Maven có thể dùng JVM khác | Kiểm JVM trong Maven process |
| Dùng cùng local repo producer để kiểm remote | Artifact đã install local, có thể không tải remote | Tạo consumer local cache riêng |
| Tự sửa `maven-metadata.xml` trên production | Dễ làm repo không nhất quán | Theo quy trình admin/republish và audit |

## 19. Bài tập tự kiểm chứng

**Bài 1 — Profile:** chạy dev rồi ci; ghi `active-profiles`, `lab.mode` từ Help Plugin và stdout của `java -jar`. Giải thích tại sao cùng source có mode khác.

**Bài 2 — Property override:** bật `-Pci` đồng thời truyền `-Dlab.mode=DEV`. Dự đoán file resource và test trước khi chạy. Giải thích profile vẫn active nhưng output mode bị override.

**Bài 3 — JDK policy:** trên một môi trường có JDK21, so `mvn -version` với `java -version` và chạy `-Pci`. Xác định Enforcer goal/execution fail vì runtime version, không phải JUnit logic.

**Bài 4 — Settings:** trên sandbox, so một settings hợp lệ với `settings-bad.xml`. Ghi mirror ID thực, xác định tại sao plugin/dependency không download.

**Bài 5 — Snapshot metadata:** tạo `triage-catalog:1.0.0-SNAPSHOT` vào file repo. Đọc V-level metadata, đối chiếu timestamped artifact file với metadata. Thử resolve 1.0.1-SNAPSHOT chưa tồn tại; giải thích vì sao `-U` không sửa được.

**Bài 6 — CI replay:** ghi một failure ticket chứa commit, JDK, profiles, settings/mirror IDs, GAV, exception, kết quả sau sửa. Không đưa secrets vào báo cáo.

## 20. Câu hỏi ôn tập

**Câu 1:** `mvn -version` khác `java -version` ở đâu?

**Đáp án:** `mvn -version` cho JVM thực sự đang chạy Maven; shell `java -version` có thể dùng một JDK khác.

**Câu 2:** Vì sao `-Pci` có thể làm dev profile activeByDefault biến mất?

**Đáp án:** Một profile khác active trong cùng POM làm activeByDefault không còn được chọn.

**Câu 3:** Tại sao chỉ xem `help:active-profiles` chưa đủ?

**Đáp án:** CLI property `-D` hoặc settings property có thể đổi effective value; cần thêm `help:evaluate` hoặc effective POM.

**Câu 4:** Maven settings có thể thay Central bằng mirror không?

**Đáp án:** Có, cấu hình mirrorOf. Repo URL cuối phải được xác định từ effective settings và Maven logs.

**Câu 5:** `server id` khớp ID nào sau khi mirror được chọn?

**Đáp án:** ID của repository/mirror đang được dùng để kết nối; thường là mirror ID, không tự động luôn là central.

**Câu 6:** Compiler release 17 có buộc Maven chạy bằng Java17 không?

**Đáp án:** Không. JDK mới hơn có thể compile target 17. Enforcer RequireJavaVersion là policy riêng về JVM chạy Maven.

**Câu 7:** Vì sao một SNAPSHOT dùng metadata ở version level?

**Đáp án:** Để ánh xạ baseVersion `1.0.0-SNAPSHOT` sang timestamped snapshot files thực.

**Câu 8:** `-U` có sửa version GAV không tồn tại không?

**Đáp án:** Không. Nó làm Maven kiểm lại theo update policy, nhưng artifact chưa publish vẫn không thể được resolve.

**Câu 9:** `-o` dùng làm gì?

**Đáp án:** Chạy offline bằng những artifacts/plugins đã có trong local cache; không tải thứ chưa được cache.

**Câu 10:** Vì sao phải dùng local repo riêng khi test file:// repository?

**Đáp án:** Producer đã có artifact local; consumer cache riêng giúp chứng minh Maven thật sự resolve từ remote test repo.

**Câu 11:** `maven-metadata.xml` và `*.lastUpdated` có giống nhau không?

**Đáp án:** Không. Metadata mô tả versions/snapshots/plugin prefixes; `*.lastUpdated` có thể lưu lịch sử attempt hoặc negative cache của resolver.

**Câu 12:** Khi local pass CI fail, nên sửa POM trước hay thu evidence?

**Đáp án:** Thu exact invocation, JDK, settings, profile, repo/cache và error cause trước; sửa lớp đúng khi đã có bằng chứng.

## 21. Checklist trước khi kết luận đã sửa lỗi

- [ ] Đã xác nhận source SHA, cwd và command giống mục tiêu CI.
- [ ] Có `mvn -version`/`JAVA_HOME` và compiler/toolchain JDK evidence.
- [ ] Biết user/global settings hoặc `-s` file nào được dùng.
- [ ] Biết effective mirrors, server IDs, proxy và local repo path.
- [ ] Không tiết lộ credentials/secret logs.
- [ ] Biết active profiles và effective property value.
- [ ] Biết POM profile, settings profile và default activation khác nhau.
- [ ] Nếu lỗi JDK, phân biệt runtime Maven, compiler toolchain và release target.
- [ ] Nếu lỗi repository, ghi chính xác GAV, plugin/dependency, repo ID và HTTP code.
- [ ] Nếu SNAPSHOT, kiểm V-level metadata, file timestamped và update policy.
- [ ] Nếu cached failure, xác minh remote đã sửa trước khi dùng `-U`.
- [ ] Không xóa global cache hoặc sửa remote metadata mù.
- [ ] Chạy targeted reproduction trong sandbox và ghi output.
- [ ] Chạy full `mvn -B -ntp -Pci clean verify` với CI environment chính xác.
- [ ] Xác minh Surefire reports, exit status, profile mode và artifact.
- [ ] Có ticket root cause/biện pháp khắc phục và regression evidence.
- [ ] Không che lỗi bằng `-fn`, `skipTests` hay bỏ policy.

**Kết luận:** Khi Maven thất bại, đừng mặc định nguyên nhân là dependency hoặc Java code. Dùng **effective-settings** để nhìn mirror/credentials routing, **active-profiles/effective-pom/evaluate** để nhìn build configuration, **mvn -version/toolchains** để nhìn JDK thực, và **remote/local repository metadata** để xác định Maven đang tìm phiên bản nào ở đâu. Chỉ khi bốn nhóm đã được tách bằng chứng và **full build được xác minh lại** mới có cơ sở báo lỗi đã được sửa.

## Nguồn tài liệu chính thức

- [Apache Maven — Settings Reference](https://maven.apache.org/settings.html)
- [Apache Maven — Using Mirrors for Repositories](https://maven.apache.org/guides/mini/guide-mirror-settings.html)
- [Apache Maven — Setting up Multiple Repositories](https://maven.apache.org/guides/mini/guide-multiple-repositories.html)
- [Apache Maven — Introduction to Build Profiles](https://maven.apache.org/guides/introduction/introduction-to-profiles.html)
- [Maven Help Plugin — Plugin Details](https://maven.apache.org/plugins/maven-help-plugin/plugin-info.html)
- [Maven Help Plugin — effective-settings](https://maven.apache.org/plugins/maven-help-plugin/effective-settings-mojo.html)
- [Maven Help Plugin — effective-pom](https://maven.apache.org/plugins/maven-help-plugin/effective-pom-mojo.html)
- [Apache Maven — Guide to Using Toolchains](https://maven.apache.org/guides/mini/guide-using-toolchains.html)
- [Maven Compiler Plugin — Setting Java Version](https://maven.apache.org/plugins/maven-compiler-plugin/examples/set-compiler-source-and-target.html)
- [Maven Enforcer Plugin — Require Java Version](https://maven.apache.org/enforcer/enforcer-rules/requireJavaVersion.html)
- [Apache Maven — Repository Metadata](https://maven.apache.org/repositories/metadata.html)
- [Maven Dependency Plugin — dependency:get](https://maven.apache.org/plugins/maven-dependency-plugin/get-mojo.html)
- [Maven Deploy Plugin — deploy:deploy-file](https://maven.apache.org/plugins/maven-deploy-plugin/deploy-file-mojo.html)
- [Apache Maven — CLI Options Reference](https://maven.apache.org/ref/3.9.11/maven-embedder/cli.html)

*Ví dụ đã được thiết kế cho Java 17 và Maven 3.9.x; các đoạn log “dự kiến” không phải log ghi lại từ một build đã chạy trong lượt soạn bài. File URL, repository cache, settings-bad.xml và ứng dụng đều là môi trường học tập độc lập. Mọi thay đổi trong ví dụ là các thao tác người học tự thực hiện tại sandbox; không có lệnh nào yêu cầu sửa cấu hình hay artifact repository sản xuất.*
