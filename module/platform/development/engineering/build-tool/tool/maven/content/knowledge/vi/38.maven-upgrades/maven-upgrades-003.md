# Nâng plugin, chạy kiểm chứng và so sánh artifact trước sau trong Maven

## 1. Bản chất của một lần nâng Maven plugin

Một Maven plugin là mã thực thi trong quá trình build. Nó có thể biên dịch Java, chạy test, sinh resource, tạo JAR/WAR, kiểm chất lượng, ký hoặc phát hành artifact. Vì vậy, **nâng một plugin không chỉ thay version trong POM; nó có thể thay sản phẩm được đóng gói** dù Java source không đổi.

Ví dụ bài học nâng Apache Maven JAR Plugin từ `3.3.0` lên `3.4.2`:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-jar-plugin</artifactId>
    <version>3.4.2</version>
</plugin>
~~~

Hai phiên bản trên đều có trong tài liệu Apache Maven và hỗ trợ `outputTimestamp` để giảm nhiễu của ZIP-entry timestamps. Dù vậy **không được dự đoán checksum của hai JAR sẽ giống hoặc khác** nếu chưa xây và đo thực tế.

Nhiệm vụ của kỹ sư không chỉ là nhìn `BUILD SUCCESS`, mà phải trả lời: đúng goal/version đã chạy chưa; cùng tests/quality gates có đạt không; main/attached artifacts có đủ không; binary/resources/manifest/Maven metadata thay ở đâu; consumers có tương thích không; và có thể rollback an toàn không?

Bài thuộc nhóm **Nâng cấp Maven**. Sau khi hoàn thành, bạn sẽ:

1. Lập kế hoạch nâng đúng một plugin, đúng goal và POM scope.
2. Kiểm plugin compatibility với Maven/JDK, parameters, parent inheritance, active profiles.
3. Lưu source commit, toolchain, commands, test reports và artifacts **trước** khi chạy `clean` lần nữa.
4. Tạo project Java 17 hoàn chỉnh với Maven Compiler/Surefire/JAR, 4 JUnit tests và một resource được đóng gói.
5. Chạy phép thử A/B khi chỉ thay JAR Plugin `3.3.0 → 3.4.2`.
6. So SHA-256, ZIP entries, MANIFEST, embedded POM, class/resource bytes, public API và stdout.
7. Phân biệt **reproducible build** với **so sánh artifacts qua hai plugin versions**.
8. Hoàn tất nâng cấp trong POM được commit, chạy verify không CLI override.
9. Thiết kế CI, multi-module inventory, consumer tests, review/rollback và release checks.
10. Viết báo cáo trước/sau dựa trên kết quả đo thật, không tự tạo checksum hay tuyên bố PASS khi chưa chạy.

**Môi trường mẫu:** Maven 3.8+, JDK 17+, JUnit Jupiter 5.11.4, Maven Compiler Plugin 3.13.0, Surefire 3.5.4, Clean 3.4.1, Resources 3.3.1, JAR Plugin 3.3.0/3.4.2. Các versions được ghim để dễ tái hiện, không được hiểu là mặc định mới nhất cho mọi dự án.

## 2. Rủi ro nằm ở plugin goal và output contract

Mỗi plugin có full coordinate `groupId:artifactId:version`, thường cung cấp nhiều goals. Ví dụ `jar:jar` tạo main JAR; `jar:test-jar` tạo attached test JAR nếu được cấu hình. `mvn verify` đi qua lifecycle bindings, không tự chạy mọi goal của mọi plugin.

Một thay đổi plugin có thể ảnh hưởng:

| Thứ thay đổi | Rủi ro cần kiểm |
| --- | --- |
| Compiler Plugin | Java bytecode/API, annotation processing, `--release`, output directories. |
| Surefire Plugin | JUnit provider, test discovery, JVM forks, XML reports, skip behavior. |
| Failsafe Plugin | Integration-test và verify semantics, teardown, CI status. |
| JAR Plugin | Archive entries, manifest, timestamps, metadata Maven. |
| WAR Plugin | `WEB-INF/lib`, overlays, web.xml, resources. |
| Shade Plugin | Relocation, duplicate classes, `META-INF/services`, fat JAR. |
| Resources Plugin | Filtering, character encoding, binary resource preservation. |
| Source/Javadoc Plugin | Attached `-sources.jar`, `-javadoc.jar`, publication metadata. |
| GPG/Deploy/Release Plugin | Signatures, staging, remote repository side effects. |
| JaCoCo/Enforcer/Analysis Plugin | Quality gates, rules, report format và test coverage. |

**Không coi việc nâng phiên bản dependency của ứng dụng giống việc nâng build plugin.** Plugin có riêng dependencies/classloader và có quyền đọc/ghi filesystem, network theo quyền của build runner.

### PluginManagement và parent POM

- `build/plugins` trực tiếp khai báo plugin và configuration.
- `build/pluginManagement` quản lý versions/default configurations cho plugins được dùng.
- Parent POM có thể làm tất cả modules thừa hưởng plugin executions.
- Active profiles có thể bật plugin, đổi phase, đổi repository hoặc parameter.
- `reporting/plugins` dùng cho các reports/site, cần đánh giá riêng khi liên quan.
- Direct CLI goals có thể chạy ngoài execution bind ở POM.

Vì vậy phải biết **effective configuration** và log thực thi, không chỉ nhìn POM con. Với Maven Help Plugin được phép chạy:

~~~bash
mvn org.apache.maven.plugins:maven-help-plugin:3.5.2:effective-pom -Dverbose -Doutput=effective-pom.xml
~~~

Lệnh chỉ nên chạy **sau khi static-review** project và trên môi trường phù hợp: Maven Help Plugin và core extensions vẫn là code thực thi. Effective POM cũng phụ thuộc active profiles/properties của chính invocation.

## 3. Kiểm trước khi chạm version

Trước khi nâng, đối chiếu:

1. Lý do nâng: security fix, bug fix, JDK support, reproducible output, feature, performance.
2. Release notes của **plugin và version đích**, không chỉ latest docs.
3. Minimum Maven/JDK; deprecated/removed parameters và thay defaults.
4. Có thay `goal` hoặc phase binding hay không.
5. Plugin dependencies và nguồn binary có thuộc repository allowlist không.
6. Test frameworks/annotation processors và downstream consumers.
7. POM parent/pluginManagement và CI profiles.
8. Attached artifacts, signature/staging/release requirements.
9. Kế hoạch rollback, owner review và điều kiện chấp thuận.

Ví dụ Apache Maven JAR Plugin 3.4.2 có trang `plugin-info.html` ghi minimum Maven 3.6.3/JDK 8; môi trường Java 17/Maven 3.8+ của lab đáp ứng. **Các plugin khác có minimum cao hơn**; không copy compatibility này sang Compiler/Surefire bản mới mà chưa kiểm.

Ghi một upgrade card:

~~~text
Component: org.apache.maven.plugins:maven-jar-plugin
From: 3.3.0
To: 3.4.2
Goals: jar:jar (default JAR packaging)
Maven/JDK: record exact local/CI versions
Scope: one Java 17 module for lab
Expected unchanged: public API, resource, stdout, test counts
Allowed differences: only differences explicitly reviewed
Gates: verify, XML reports, artifact diff, consumer smoke
Rollback: restore previously approved plugin version
~~~

Giá trị "expected unchanged" là **mục tiêu kiểm**, không phải kết quả đã đo.

## 4. Lưu baseline: một lần clean có thể xóa bằng chứng cũ

Đừng nâng plugin và chạy `mvn clean verify` khi chưa lưu `target/*.jar`, Surefire/Failsafe XML, generated files hoặc manifest gốc. `clean` có thể xóa toàn bộ `target`.

Một bộ baseline đáng tin:

| Bằng chứng | Để làm gì |
| --- | --- |
| Git SHA và trạng thái working tree | Xác định source thực; SHA không bao gồm uncommitted changes. |
| `java -version`, `mvn --version` | Biết JVM Maven dùng, JDK vendor và Maven version. |
| Full Maven command | Giữ `-P`, `-D`, `-T`, `-pl`, `-am`, `-o` nếu được dùng. |
| Effective POM (khi cần) | Chứng minh phiên bản/goals/configuration thực. |
| Build log và exit code | Tìm goal/version đã chạy và lỗi đầu tiên. |
| Test XML và test count | Không cho build xanh vì test bị skip. |
| Main JAR và attached artifacts | Dữ liệu thật để so trước/sau. |
| File list/manifest/checksums | So archive structure và metadata. |
| JDK/OS/CI runner information | Giảm nhiễu do môi trường. |

Đặt báo cáo ngoài `target`:

~~~text
plugin-upgrade-lab/
├── pom.xml
├── src/...
└── evidence/
    ├── before/
    │   ├── verify.log
    │   ├── exit-code.txt
    │   ├── app.jar
    │   ├── app.sha256
    │   ├── entries.sorted.txt
    │   ├── manifest.txt
    │   └── TEST-demo.upgrade.BuildGreetingTest.xml
    └── after/
        ├── verify.log
        ├── exit-code.txt
        ├── app.jar
        ├── app.sha256
        ├── entries.sorted.txt
        ├── manifest.txt
        └── TEST-demo.upgrade.BuildGreetingTest.xml
~~~

Không tự cho rằng các file này tồn tại trước khi chạy thí nghiệm: chúng được tạo từ commands ở các mục sau.

## 5. A/B design: chỉ thay một biến

Có hai cách nâng plugin trong phép kiểm:

**Cách A — CLI override một property.** Giữ nguyên bytes source `pom.xml` giữa hai lần và truyền:

~~~bash
mvn -B -ntp -Djar.plugin.version=3.3.0 clean verify
mvn -B -ntp -Djar.plugin.version=3.4.2 clean verify
~~~

POM khai báo version dưới dạng `${jar.plugin.version}`. Đây là cách dùng trong lab để cô lập khác biệt của **plugin implementation** mà không cần edit/revert POM liên tục.

**Cách B — hai worktrees/branches có diff POM một dòng.** Mỗi bản chứa version tường minh tương ứng; build trên cùng JDK/Maven/inputs. Đây gần release pipeline thực nhưng JAR có thể nhúng POM khác nhau, khiến artifact SHA thay do **metadata POM**, không phải do Java bytecode.

**Quan trọng:** CLI A/B chỉ là thí nghiệm. Với plugin version truyền bằng user property, file POM lưu trong JAR có thể vẫn phản ánh **giá trị mặc định của POM gốc**, không phản ánh CLI override. Khi quyết định nâng chính thức, phải commit plugin version mới vào POM và build **không override** để kiểm release candidate cuối.

### Điều gì phải giữ cố định?

- Source/test/resource files và Git revision.
- JDK/Maven major/minor theo chính sách.
- Compiler/Surefire/Resources/Clean plugin versions.
- Dependency versions, scopes và Maven repositories.
- Maven command/lifecycle, ngoại trừ plugin version property.
- Test profiles, environment, locale/timezone nếu có ảnh hưởng.
- Workspace state: `clean verify` để không lẫn JAR cũ.
- Concurrency level, cache state và network policy khi đo hiệu năng.

Nếu đồng thời nâng Compiler Plugin, chuyển JDK 17→21 và thay JAR Plugin thì khác biệt bytecode/archive không thể quy cho một biến.

## 6. Project Java 17 runnable

Cấu trúc dự án một module:

~~~text
plugin-upgrade-lab/
├── pom.xml
├── src/
│   ├── main/
│   │   ├── java/demo/upgrade/BuildGreeting.java
│   │   └── resources/demo/upgrade/build.properties
│   └── test/java/demo/upgrade/BuildGreetingTest.java
└── evidence/                      # Chỉ tạo khi chạy lab
~~~

Bài lab có một Java class, một resource và **bốn JUnit Jupiter tests**, không dùng Docker/DB/credentials, phù hợp kiểm plugin đóng gói JAR.

### 6.1. `pom.xml` hoàn chỉnh

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo.upgrade</groupId>
    <artifactId>plugin-upgrade-lab</artifactId>
    <version>1.0.0-SNAPSHOT</version>
    <packaging>jar</packaging>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.outputTimestamp>2024-01-01T00:00:00Z</project.build.outputTimestamp>
        <jar.plugin.version>3.3.0</jar.plugin.version>
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
                <version>3.4.1</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-resources-plugin</artifactId>
                <version>3.3.1</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.4</version>
                <configuration>
                    <failIfNoTests>true</failIfNoTests>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>${jar.plugin.version}</version>
                <configuration>
                    <outputTimestamp>${project.build.outputTimestamp}</outputTimestamp>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**Lý do cấu hình:**

- Maven `jar` packaging bind goal `jar:jar` ở phase `package`.
- Maven Compiler `release=17` tạo classes cho Java 17 APIs/bytecode; runner vẫn cần JDK đủ mới.
- Resources Plugin copy resources theo default lifecycle.
- JUnit Jupiter chỉ có `test` scope, không đóng gói vào main JAR.
- Surefire 3.5.4 chạy `*Test` và `failIfNoTests=true` để bắt phát hiện thiếu tests.
- Chỉ Maven JAR Plugin version là biến A/B; plugin khác ghim cố định.
- `project.build.outputTimestamp` là input reproducible archiving tường minh, không chứng minh toàn bộ build bit-identical.
- POM không khai báo `Main-Class`, nên dùng `java -cp` để chạy; không dùng `java -jar`.

### 6.2. `src/main/java/demo/upgrade/BuildGreeting.java`

~~~java
package demo.upgrade;

public final class BuildGreeting {
    private BuildGreeting() {
    }

    public static String welcome(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("name must not be blank");
        }
        return "Hello, " + name + "!";
    }

    public static void main(String[] args) {
        System.out.println(welcome("Maven"));
    }
}
~~~

Java 17 code này không cần third-party runtime dependency. Hàm xử lý `null`/blank rõ ràng.

### 6.3. `src/main/resources/demo/upgrade/build.properties`

~~~properties
role=training
~~~

Sau resources phase, file nằm dưới `target/classes/demo/upgrade/build.properties`; JAR Plugin sẽ đưa nó vào main JAR nếu không có excludes/transformations khác. Đây là một entry dùng để kiểm đóng gói không bị mất resource.

### 6.4. `src/test/java/demo/upgrade/BuildGreetingTest.java`

~~~java
package demo.upgrade;

import java.io.InputStream;
import java.util.Properties;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;

class BuildGreetingTest {
    @Test
    void greetsByName() {
        assertEquals("Hello, Maven!", BuildGreeting.welcome("Maven"));
    }

    @Test
    void rejectsNullName() {
        assertThrows(
                IllegalArgumentException.class,
                () -> BuildGreeting.welcome(null));
    }

    @Test
    void rejectsBlankName() {
        assertThrows(
                IllegalArgumentException.class,
                () -> BuildGreeting.welcome("  "));
    }

    @Test
    void includesResourceOnTestClasspath() throws Exception {
        try (InputStream in = getClass()
                .getResourceAsStream("/demo/upgrade/build.properties")) {
            assertNotNull(in);
            Properties properties = new Properties();
            properties.load(in);
            assertEquals("training", properties.getProperty("role"));
        }
    }
}
~~~

Bốn tests kiểm method response, input validation và resource trong test classpath. **Bài test resource không thay kiểm entry có mặt trong JAR**, vì Surefire chạy trước `package`. Phải kiểm file JAR thật bằng `jar tf` ở mục 9.

### 6.5. Chạy Java và stdout xác định

Khi `mvn clean verify` hoàn tất:

~~~bash
java -cp target/classes demo.upgrade.BuildGreeting
~~~

**Stdout chính xác:**

~~~text
Hello, Maven!
~~~

Nếu chạy từ JAR được tạo:

~~~bash
java -cp target/plugin-upgrade-lab-1.0.0-SNAPSHOT.jar demo.upgrade.BuildGreeting
~~~

**Stdout vẫn là:**

~~~text
Hello, Maven!
~~~

JAR không có manifest `Main-Class` nên `java -jar ...` không phải cách chạy hợp lệ trong bài này.

## 7. Build baseline và bảo toàn artifact

Dùng Bash Linux/macOS từ root project. Các lệnh giả định Maven/JDK có sẵn, repositories resolve được; **không thực thi demo trên một repository không tin cậy hoặc runner có production secrets**.

~~~bash
mkdir -p evidence/before evidence/after
java -version > evidence/before/java-version.txt 2>&1
mvn --version > evidence/before/maven-version.txt 2>&1
mvn -B -ntp -Djar.plugin.version=3.3.0 clean verify > evidence/before/verify.log 2>&1
printf '%s\n' "$?" > evidence/before/exit-code.txt
~~~

**Phải đặt `printf` ngay sau Maven** để lấy đúng exit code; script có `set -e` cần kiểm soát trường hợp failure dự kiến. Chỉ copy JAR và test report khi verify đã PASS và files tồn tại. Nếu fail, giữ log/exit status và điều tra **không cố lấy một artifact cũ**.

Với baseline thành công:

~~~bash
cp target/plugin-upgrade-lab-1.0.0-SNAPSHOT.jar evidence/before/app.jar
cp target/surefire-reports/TEST-demo.upgrade.BuildGreetingTest.xml evidence/before/TEST-demo.upgrade.BuildGreetingTest.xml
jar tf evidence/before/app.jar | LC_ALL=C sort > evidence/before/entries.sorted.txt
unzip -p evidence/before/app.jar META-INF/MANIFEST.MF > evidence/before/manifest.txt
sha256sum evidence/before/app.jar > evidence/before/app.sha256
~~~

`unzip`, `sha256sum` và `sort` là OS tools; Windows có phương án khác ở mục 10.

**Kỳ vọng (cần kiểm bằng log thật):**

- Maven log có `maven-jar-plugin:3.3.0:jar`.
- Surefire chạy 4 tests, 0 failures, 0 errors, 0 skipped.
- Main JAR tồn tại đúng tọa độ `demo.upgrade:plugin-upgrade-lab:1.0.0-SNAPSHOT`.
- JAR có class `demo/upgrade/BuildGreeting.class` và resource `demo/upgrade/build.properties`.
- Chạy `java -cp evidence/before/app.jar demo.upgrade.BuildGreeting` in `Hello, Maven!`.
- File `app.sha256` có một giá trị SHA-256 **được tính từ bytes thật**; không có digest cố định để chép trước.

## 8. Build candidate sau khi đổi đúng một biến

Giữ POM/source/resources/test files và toolchain như trước, chỉ thay plugin override:

~~~bash
mvn -B -ntp -Djar.plugin.version=3.4.2 clean verify > evidence/after/verify.log 2>&1
printf '%s\n' "$?" > evidence/after/exit-code.txt
~~~

Khi candidate PASS:

~~~bash
cp target/plugin-upgrade-lab-1.0.0-SNAPSHOT.jar evidence/after/app.jar
cp target/surefire-reports/TEST-demo.upgrade.BuildGreetingTest.xml evidence/after/TEST-demo.upgrade.BuildGreetingTest.xml
jar tf evidence/after/app.jar | LC_ALL=C sort > evidence/after/entries.sorted.txt
unzip -p evidence/after/app.jar META-INF/MANIFEST.MF > evidence/after/manifest.txt
sha256sum evidence/after/app.jar > evidence/after/app.sha256
~~~

Kiểm trực tiếp plugin đã được dùng:

~~~bash
grep "maven-jar-plugin:3.3.0:jar" evidence/before/verify.log
grep "maven-jar-plugin:3.4.2:jar" evidence/after/verify.log
~~~

Maven có thể in prefix khác tùy log formatter/version. Nếu không thấy dòng, mở build log và effective POM; **không tuyên bố nâng thành công** chỉ do property đầu vào đã ghi.

Chạy đúng JAR đã lưu:

~~~bash
java -cp evidence/before/app.jar demo.upgrade.BuildGreeting
java -cp evidence/after/app.jar demo.upgrade.BuildGreeting
~~~

**Stdout dự kiến của mỗi lần:**

~~~text
Hello, Maven!
~~~

Hai JAR có thể có SHA-256 khác nhau, và điều đó **chưa tự là regression**. Phần tiếp theo giải thích phép so có ý nghĩa.

## 9. So artifacts theo thứ tự từ ngoài vào trong

### 9.1. Inventory và GAV

Kiểm cả hai runs có đúng main JAR, không nhầm `-tests.jar`, `-sources.jar`, fat JAR hay module khác. Với multi-module, ghi GAV/classifier/extension cho **tất cả artifacts**. Demo chỉ cấu hình main JAR; nếu không có source/Javadoc/signature thì không đánh dấu chúng “mất”.

### 9.2. SHA-256 và size

~~~bash
sha256sum evidence/before/app.jar evidence/after/app.jar
ls -l evidence/before/app.jar evidence/after/app.jar
~~~

- **Hash giống:** JAR bytes giống nhau dưới giả định hash collision không đáng kể; vẫn phải kiểm test/consumer contract.
- **Hash khác:** một hoặc nhiều byte khác, có thể do ZIP metadata, MANIFEST, embedded POM, class/resource, compression hoặc entry ordering. Cần đào sâu.
- **File size giống** không chứng minh bytes giống.
- **File size khác** là dấu hiệu cần giải thích, không tự cho biết có breaking change.

Đừng tự gán checksum giả vào tài liệu hoặc báo cáo CI khi chưa chạy.

### 9.3. ZIP/JAR entry names

~~~bash
diff -u evidence/before/entries.sorted.txt evidence/after/entries.sorted.txt
~~~

Danh sách sorted tập trung vào **tên entries**, không phải bytes/timestamps. So các mục:

~~~text
META-INF/MANIFEST.MF
META-INF/maven/demo.upgrade/plugin-upgrade-lab/pom.xml
META-INF/maven/demo.upgrade/plugin-upgrade-lab/pom.properties
demo/upgrade/BuildGreeting.class
demo/upgrade/build.properties
~~~

Sự hiện diện chính xác của Maven descriptor tùy Maven Archiver configuration và defaults. Nếu tên entry trùng nhưng content khác thì sorted list vẫn giống: cần giải nén.

### 9.4. MANIFEST.MF

~~~bash
diff -u evidence/before/manifest.txt evidence/after/manifest.txt
~~~

Kiểm các trường nếu có:

- `Manifest-Version`, `Created-By`, `Build-Jdk-Spec`.
- `Main-Class` hoặc `Class-Path` với executable JAR.
- `Automatic-Module-Name` với Java modules.
- `Multi-Release` cho multi-release JAR.
- Implementation/Specification version/vendor.
- Custom manifest entries do dự án yêu cầu.

Không mặc định mọi trường đều có. Một thay đổi metadata có thể không ảnh hưởng class behavior nhưng vẫn ảnh hưởng người dùng đọc manifest hoặc công cụ release.

### 9.5. Giải nén và so bytes nội dung

Trên Linux/macOS có `unzip`/`diff`:

~~~bash
mkdir -p evidence/before/unpacked evidence/after/unpacked
unzip -q evidence/before/app.jar -d evidence/before/unpacked
unzip -q evidence/after/app.jar -d evidence/after/unpacked
diff -r evidence/before/unpacked evidence/after/unpacked
~~~

Từ kết quả diff, xem cụ thể:

~~~bash
unzip -p evidence/before/app.jar demo/upgrade/build.properties
unzip -p evidence/after/app.jar demo/upgrade/build.properties
~~~

**Resource mong đợi trong cả hai artifact:**

~~~properties
role=training
~~~

Khi có file khác, phân loại thành **thay đổi intentional**, **nondeterministic metadata** hoặc **nghi vấn regression**. Đừng xóa file khác biệt để biến hash thành khớp mà không hiểu tác động.

### 9.6. Public API và bytecode

Dùng `javap` có trong JDK:

~~~bash
javap -public -classpath evidence/before/app.jar demo.upgrade.BuildGreeting > evidence/before/api.txt
javap -public -classpath evidence/after/app.jar demo.upgrade.BuildGreeting > evidence/after/api.txt
diff -u evidence/before/api.txt evidence/after/api.txt
~~~

Kiểm disassembly khi cần:

~~~bash
javap -c -p -classpath evidence/before/app.jar demo.upgrade.BuildGreeting > evidence/before/bytecode.txt
javap -c -p -classpath evidence/after/app.jar demo.upgrade.BuildGreeting > evidence/after/bytecode.txt
diff -u evidence/before/bytecode.txt evidence/after/bytecode.txt
~~~

`javap -public` chỉ so lớp được chọn, **không là full binary compatibility checker**. Dự án thư viện nên dùng công cụ được duyệt như Revapi/japicmp và consumer regression tests. Nếu compiler/JDK thay trong cùng PR, differences trong bytecode có thể do công cụ khác chứ không riêng JAR Plugin.

### 9.7. Embedded POM và Maven descriptor

Maven Archiver có thể thêm:

~~~text
META-INF/maven/demo.upgrade/plugin-upgrade-lab/pom.xml
META-INF/maven/demo.upgrade/plugin-upgrade-lab/pom.properties
~~~

Khi commit đổi `<jar.plugin.version>3.3.0</jar.plugin.version>` thành `3.4.2`, **POM bytes nằm trong JAR có thể đổi**, dù source Java không đổi. Nếu CLI override version trong A/B, POM nguồn vẫn ghi default cũ trong trường hợp mẫu, nên embedded POM có thể chưa mô tả đúng override thực tế. **Bởi vậy candidate cuối phải được xây từ POM đã commit, không phải chỉ từ CLI override.**

Không nên tắt `addMavenDescriptor` chỉ để có hash giống: đó là một thay đổi artifact contract khác cần review riêng.

## 10. Cách kiểm trên Windows PowerShell

Windows không nhất thiết có Bash `diff`, `sha256sum` hoặc `unzip`. Dùng:

~~~powershell
Get-FileHash -Algorithm SHA256 evidence\before\app.jar
Get-FileHash -Algorithm SHA256 evidence\after\app.jar
~~~

Dùng JDK `jar` để liệt kê entries:

~~~powershell
jar tf evidence\before\app.jar | Sort-Object | Set-Content evidence\before\entries.sorted.txt
jar tf evidence\after\app.jar | Sort-Object | Set-Content evidence\after\entries.sorted.txt
Compare-Object (Get-Content evidence\before\entries.sorted.txt) (Get-Content evidence\after\entries.sorted.txt)
~~~

Giải nén bằng JDK:

~~~powershell
New-Item -ItemType Directory -Force evidence\before\unpacked | Out-Null
New-Item -ItemType Directory -Force evidence\after\unpacked | Out-Null

Push-Location evidence\before\unpacked
jar xf ..\app.jar
Pop-Location

Push-Location evidence\after\unpacked
jar xf ..\app.jar
Pop-Location
~~~

Sau đó xem manifest:

~~~powershell
Compare-Object (Get-Content evidence\before\unpacked\META-INF\MANIFEST.MF) (Get-Content evidence\after\unpacked\META-INF\MANIFEST.MF)
~~~

**Đừng dùng text `Get-Content` để so binary `.class`**: dùng `Get-FileHash` cho từng file, binary diff hoặc `javap`. Khi PowerShell so strings, encoding/newline có thể khác, phải dựa vào bytes khi kết luận bitwise equality.

Chạy runtime JAR:

~~~powershell
java -cp evidence\before\app.jar demo.upgrade.BuildGreeting
java -cp evidence\after\app.jar demo.upgrade.BuildGreeting
~~~

Cả hai dự kiến in `Hello, Maven!`.

## 11. Reproducible builds khác so hai plugin versions

**Reproducible build** yêu cầu cùng source, environment và build instructions tạo các artifacts xác định giống từng byte. Trong bài đang xét, A và B **cố ý có build instruction khác** (plugin version), nên không bắt buộc hai JAR bit-identical để gọi mỗi version là reproducible.

Hai câu hỏi:

- **A1 vs A2**, cùng JAR Plugin 3.3.0 và cùng input: mỗi run có sinh bytes giống nhau không?
- **B1 vs B2**, cùng JAR Plugin 3.4.2 và cùng input: candidate có reproducible không?
- **A vs B**, hai plugin versions khác nhau: có thay đổi artifact contract nào không?

Nếu A1/A2 đã khác nhau do timestamp, không nên tự quy mọi khác biệt A/B cho plugin upgrade.

### `project.build.outputTimestamp`

POM lab có:

~~~xml
<project.build.outputTimestamp>2024-01-01T00:00:00Z</project.build.outputTimestamp>
~~~

JAR Plugin hỗ trợ `outputTimestamp` để ổn định timestamps của archive entries; nó là **một phần** của reproducibility, chưa đủ cho mọi plugin, JDK, OS hoặc file được sinh động. Ở các Maven phiên bản mới, default reproducibility behavior có thể thay; việc đặt tường minh giúp lab nhất quán trên Maven 3.8+.

### Maven Artifact Plugin

Apache Maven cung cấp `maven-artifact-plugin` với `check-buildplan` và `compare`. Ví dụ:

~~~bash
mvn org.apache.maven.plugins:maven-artifact-plugin:3.7.0:check-buildplan
~~~

Goal này giúp nhận biết những plugin/goal có vấn đề reproducible build đã biết. Nó **không thay test API hoặc kiểm artifact semantic**.

Tài liệu cũng mô tả workflow kiểm **same-version rebuild** bằng reference local repository:

~~~bash
mvn clean install
mvn clean verify org.apache.maven.plugins:maven-artifact-plugin:3.7.0:compare
~~~

Đây là **thí nghiệm cùng build instruction**; `install` sẽ ghi artifact vào local repository và có thể ghi đè reference GAV ở local. Tránh chạy trên một repository có trạng thái cần bảo toàn. Không dùng `artifact:compare` như phép thay thế duy nhất cho before/after snapshots khi nâng plugin giữa hai versions khác nhau.

Nếu có `diffoscope` được cài/duyệt:

~~~bash
diffoscope evidence/before/app.jar evidence/after/app.jar
~~~

nó có thể giúp thấy ZIP/manifest/class differences sâu hơn. Tool có thể tạo output rất lớn; cần đánh giá dữ liệu nhạy cảm nếu share.

## 12. Test coverage và test counts quan trọng hơn một dòng xanh

Maven `clean verify` có thể kết thúc `BUILD SUCCESS` nhưng không chạy những tests mà nhóm tưởng đã chạy nếu skip flags, profiles hoặc test naming sai.

Trong demo:

~~~text
target/surefire-reports/TEST-demo.upgrade.BuildGreetingTest.xml
~~~

nên biểu diễn **4 tests, 0 failures, 0 errors, 0 skipped** khi environment bình thường. Đây là mục tiêu kiểm, không phải kết quả đã chạy thực tế trong tài liệu.

Một báo cáo nâng plugin nên so:

| Chỉ số | Before | After |
| --- | --- | --- |
| Unit test count | Giá trị đo | Giá trị đo |
| Failures/errors/skipped | Giá trị đo | Giá trị đo |
| Integration tests (nếu có) | Failsafe XML | Failsafe XML |
| Coverage (nếu policy yêu cầu) | JaCoCo XML + metric | JaCoCo XML + metric |
| Enforcer/static analysis | Rules/goal results | Rules/goal results |
| Maven exit status | Mã thoát thật | Mã thoát thật |
| Goal/plugin version | Từ Maven log | Từ Maven log |

Không sửa bằng cách tắt tests, thêm `-DskipTests`, `-Dmaven.test.skip=true` hoặc `-fn` để CI báo xanh. Nếu upgrade làm test discovery giảm từ 4 về 0, phải chặn hoặc điều tra.

**`mvn verify` không tự chạy Failsafe/JaCoCo nếu chưa bind goals tương ứng.** Đừng báo “integration tests/coverage đã được xác minh” chỉ vì `verify` thành công.

## 13. Nâng chính thức: commit thay đổi vào POM

A/B ở mục 7–9 dùng CLI override. Khi quyết định ứng dụng plugin mới, đổi giá trị trong POM:

**Trước:**

~~~xml
<jar.plugin.version>3.3.0</jar.plugin.version>
~~~

**Sau:**

~~~xml
<jar.plugin.version>3.4.2</jar.plugin.version>
~~~

Chạy từ source đã có diff mong muốn:

~~~bash
mvn -B -ntp clean verify
~~~

**Không truyền `-Djar.plugin.version` ở bước này.** Xác nhận Maven log có `maven-jar-plugin:3.4.2:jar`, tests đủ 4, JAR đúng GAV, resource/class có mặt và Java runtime stdout đúng.

Điểm khác của candidate sau commit: embedded Maven POM có thể chứa giá trị `3.4.2`, nên hash JAR cuối có thể khác thí nghiệm B bằng CLI override. Đây có thể là metadata khác biệt hợp lý; phải ghi nó trong before/after report.

### Phân biệt kết quả của ba build

~~~text
A: cùng POM nguồn, CLI ép 3.3.0
B: cùng POM nguồn, CLI ép 3.4.2
C: POM đã commit 3.4.2, KHÔNG CLI override
~~~

- **A/B** cô lập plugin implementation version.
- **C** phản ánh candidate chính thức mà developer/CI sẽ build trong tương lai.
- Không dùng artifact B để tuyên bố artifact C đã được kiểm nếu build instructions khác.
- Với release workflow, chỉ publish sau approval và full quality gates; không tự dùng `deploy` trong PR A/B.

## 14. Multi-module: không chỉ so một JAR

Một project lớn:

~~~text
root/
├── pom.xml
├── api/pom.xml
├── service/pom.xml
├── web/pom.xml
└── distribution/pom.xml
~~~

có thể tạo nhiều artifacts:

~~~text
api-version.jar
service-version.jar
web-version.war
distribution-version.zip
*-sources.jar
*-javadoc.jar
*.pom
*.asc                # nếu có signing
~~~

Khi plugin được quản lý trong parent, upgrade có thể ảnh hưởng nhiều modules. Phải lập inventory theo **module + GAV + classifier + extension**, kèm size/checksum/report status. Những attached classifiers chỉ được mong đợi nếu project đã cấu hình Source/Javadoc/Test-JAR/Signing goals.

Chạy full Reactor:

~~~bash
mvn -B -ntp clean verify
~~~

Nếu chỉ chọn service:

~~~bash
mvn -B -ntp -pl :service -am clean verify
~~~

thì upstream dependencies được bao gồm nhưng **không chứng minh mọi module khác đã verify**. Bắt buộc có full scope theo chính sách release.

### Artifacts nào cần soi kỹ theo plugin?

- JAR Plugin: main/test JAR, manifest, class/resource entries.
- Shade: fat JAR dependencies, service files, relocation paths.
- Resources: filtered files, character encodings, placeholders.
- Compiler: class file version, annotation-generated sources, public API.
- WAR: `WEB-INF` tree, deployment descriptor và static assets.
- Assembly: ZIP/TAR file modes, scripts và directory layout.
- GPG/Deploy: signed GAVs, checksums, staging repository, source/Javadoc attachments.

Một version bump plugin có thể không thay Java class nhưng làm thiếu `META-INF/services`; với runtime ServiceLoader, đó là regression nghiêm trọng dù bytecode main không đổi.

## 15. Kiểm consumers, không chỉ binary diff

Đối với thư viện dùng bởi downstream services:

1. Compile một consumer project against candidate artifact.
2. Chạy consumer integration/contract tests.
3. Kiểm public API/binary compatibility bằng công cụ chuyên dụng khi có.
4. So module metadata/`Automatic-Module-Name`, manifest và services.
5. Kiểm Java bytecode target với JDK consumers hỗ trợ.
6. Kiểm serialized data/config/resource loading.
7. Kiểm transitive dependency POM và runtime classpath nếu packaging hoặc publication thay.
8. Theo dõi startup/performance/resource regression khi có rủi ro.

Một smoke test `Hello, Maven!` rất hữu ích cho lab nhưng không thể thay hàng trăm consumer contract tests của dự án thật. **Hash giống** cũng chưa chứng minh một bản release tương đương nếu `.pom` hoặc repository metadata đi kèm đã đổi.

## 16. CI matrix so baseline và candidate

Ví dụ GitHub Actions cho chính demo:

~~~yaml
name: Maven Plugin Upgrade Verification

on:
  pull_request:
  push:
    branches: [main]

permissions:
  contents: read

jobs:
  compare-plugin-versions:
    runs-on: ubuntu-latest
    timeout-minutes: 20

    strategy:
      fail-fast: false
      matrix:
        jar-plugin: ['3.3.0', '3.4.2']

    steps:
      - name: Checkout source
        uses: actions/checkout@v7
        with:
          persist-credentials: false

      - name: Set up Java 17
        uses: actions/setup-java@v6
        with:
          distribution: temurin
          java-version: '17'
          cache: maven
          cache-read-only: ${{ github.event_name == 'pull_request' }}

      - name: Record toolchain
        run: |
          java -version
          mvn --version
          git rev-parse HEAD

      - name: Verify with selected JAR Plugin
        run: mvn -B -ntp -Djar.plugin.version=${{ matrix.jar-plugin }} clean verify

      - name: Inspect produced JAR
        if: ${{ success() }}
        run: |
          jar tf target/plugin-upgrade-lab-1.0.0-SNAPSHOT.jar
          java -cp target/plugin-upgrade-lab-1.0.0-SNAPSHOT.jar demo.upgrade.BuildGreeting
          sha256sum target/plugin-upgrade-lab-1.0.0-SNAPSHOT.jar

      - name: Upload results even on failure
        if: ${{ always() }}
        uses: actions/upload-artifact@v7
        with:
          name: jar-plugin-${{ matrix.jar-plugin }}-${{ github.run_id }}-${{ github.run_attempt }}
          path: |
            **/target/surefire-reports/**
            target/plugin-upgrade-lab-1.0.0-SNAPSHOT.jar
          if-no-files-found: warn
          retention-days: 7
~~~

**Giải thích phạm vi:**

- Hai matrix legs dùng cùng source event ref và các plugin versions được override.
- `fail-fast: false` giữ job còn lại nếu một leg FAIL.
- Build step giữ exit code; không đặt `continue-on-error: true` để che test failures.
- `Inspect produced JAR` chạy khi prior steps success; upload vẫn chạy khi verify fail.
- `always()` **không tạo file JAR/XML chưa tồn tại**, chỉ cố upload các files hiện có.
- Tên artifact unique theo plugin version + run ID + attempt.
- Upload artifact **không tự parse tests và không tự so hai JAR**. Job so sánh tự động cần download cả hai artifacts sau khi build, phân tích và áp policy riêng.
- Major action tags có thể thay đổi; muốn pin immutable SHA cần sử dụng SHA thực do upstream/organization xác minh, không bịa.
- Với GitHub Enterprise/self-hosted runner cũ, kiểm action/runtime compatibility.
- PR job không có publish/signing/cloud production secrets; `contents: read` là baseline quyền tối thiểu.

Đây là matrix **đánh giá**, không phải release. Một candidate cuối sau commit version mới vào POM vẫn cần build không override ở required CI. Không chạy `mvn deploy` trong PR chỉ để đo ảnh hưởng plugin JAR.

## 17. Quy trình phân loại khác biệt

| Dấu hiệu | Ý nghĩa có thể | Quyết định ban đầu |
| --- | --- | --- |
| SHA bằng nhau | JAR bytes bằng nhau. | Kiểm tests, POM ngoài JAR, consumers vẫn cần. |
| SHA khác, entry names bằng | Metadata/entry bytes/ZIP compression khác. | Unpack và so per-entry. |
| Chỉ manifest đổi | Plugin/JDK/Archiver metadata. | Review field có phải consumer contract không. |
| Chỉ embedded POM đổi | Version property/source POM đổi. | Ghi metadata change, kiểm release instructions. |
| Class bytes khác | Compiler/JDK/source/generator có thể khác. | Javap/API + kiểm toolchain. |
| Resource bytes khác | Filtering/encoding/packaging có thể đổi. | Kiểm config, contract và runtime. |
| Class/resource bị thiếu | Packaging regression. | Chặn nếu consumers cần. |
| Source/Javadoc artifact thiếu | Plugin attach/phase/skip changed. | Chặn release contract nếu bắt buộc. |
| Tests giảm từ 4 xuống 0 | Discovery hoặc skip behavior đổi. | Chặn, không gọi PASS. |
| Build CI fail, local PASS | Toolchain/profile/repo/cache khác. | Ghi exact environment và tái hiện. |
| Reproducibility chỉ fail ở one version | Plugin/version/toolchain nondeterminism. | Chẩn đoán same-version rebuild. |
| Release signing khác | Signature timestamps/keys và artifact bytes. | Kiểm signing policy; không so signature vô bối cảnh. |

Khi artifact khác, **không tắt Maven descriptor, manifest entries hoặc tests chỉ để hash khớp**. Những cách đó tự tạo thay đổi contract mới, có thể che regression.

## 18. Phương pháp đo hiệu năng có kiểm soát

Plugin upgrade đôi khi hứa build nhanh hơn, nhưng một lần chạy sau có cache ấm hơn chưa chứng minh gì.

Để benchmark:

- Giữ Git SHA, Maven/JDK, OS/CPU/memory và network gần tương đương.
- Phân biệt warm/cold dependency caches, plugins chưa được download.
- Lặp nhiều trials cho baseline/candidate, loại thông tin outlier có lý do.
- So wall-clock duration, CPU/memory, test forks, download size, module timings.
- Không đánh đổi build correctness/test counts lấy tốc độ.
- Nếu baseline và candidate dùng `-T` khác, đang đo cả concurrency change; không quy hoàn toàn cho plugin.
- Release/reproducibility có thể phụ thuộc nguồn timestamp, file ordering và archive compression; ghi các thông số này.

Trên Linux:

~~~bash
/usr/bin/time -p mvn -B -ntp -Djar.plugin.version=3.3.0 clean verify
/usr/bin/time -p mvn -B -ntp -Djar.plugin.version=3.4.2 clean verify
~~~

`/usr/bin/time` không có ở mọi máy. Đây là phép đo thời gian, vẫn phải kiểm exit status và outputs. Không chạy vòng lặp chứa `deploy` hoặc thao tác ghi repository production.

## 19. Troubleshooting khi nâng plugin

| Lỗi | Nguyên nhân thường gặp | Cách xác minh |
| --- | --- | --- |
| Maven vẫn dùng JAR Plugin cũ. | Property không áp dụng hoặc inherited version. | Build log và effective POM với cùng flags. |
| `UnsupportedClassVersionError` | Plugin hoặc dependency yêu cầu JDK cao hơn. | Release docs/JDK đang chạy Maven. |
| `No plugin found` | Prefix/GAV/pluginRepositories sai. | Dùng full coordinates, kiểm repository và metadata. |
| `Could not resolve plugin` | Offline, proxy, rate limit, missing artifact. | Kiểm repo/settings và status; không chia sẻ credentials. |
| JAR không được tạo. | Packaging khác, goal skip, build fail trước `package`. | Reactor summary/goal log. |
| `ClassNotFoundException` chạy candidate. | Class thiếu hoặc runtime classpath sai. | `jar tf`/manifest/Java command. |
| `java -jar` fail thiếu Main-Class. | Lab cố ý không cấu hình executable JAR. | Dùng `java -cp JAR Class`. |
| `build.properties` mất. | Resources/packaging includes/excludes. | `jar tf` và unpack. |
| Tests = 0. | Surefire naming/provider/skip. | `failIfNoTests` và XML. |
| SHA khác qua A/B. | Byte differences thuộc nhiều loại. | So entries, manifest, unpack, javap. |
| Hash khác trong hai runs cùng version. | Nondeterministic timestamp/env. | `outputTimestamp`, artifact compare, diffoscope. |
| Candidate POM descriptor vẫn ghi old version. | CLI override không sửa POM source. | Commit property đích và rebuild không override. |
| JAR khác dù .class giống. | Manifest/Maven metadata/ZIP bytes khác. | Unpack và archive inspection. |
| Version nâng nhưng Failsafe IT không chạy. | Execution chưa bind hoặc chỉ `mvn test`. | Kiểm `verify`/Failsafe goals. |
| Maven local và CI khác. | JDK/Maven/profile/OS/cache khác. | Ghi tool versions và exact flags. |
| Multi-module artifacts thiếu. | Chỉ chạy `-pl` subset. | Full Reactor verify và inventory. |
| Publishing thất bại sau verify. | Repository/signing/staging config khác. | Kiểm deploy stage trên môi trường được phép. |
| PR reports bị upload chứa secrets. | Tests/plugins in stdout/exception. | Sanitization, giới hạn retention/access. |
| Nhiều plugin cùng được nâng. | Không cô lập root cause. | Chia PR hoặc chạy incremental A/B. |

Nếu lỗi chập chờn, ghi fail frequency và điều kiện thay vì chỉ rerun đến khi build xanh. Nếu plugin là một build-time executable chưa tin cậy, không chạy A/B với quyền ký/publish chỉ để thu thêm logs.

## 20. Quyết định upgrade và rollback

**Chấp thuận** khi: plugin version mới thực sự được dùng; tests/quality gates PASS với số lượng hợp lệ; artifact inventory đúng; differences được giải thích và phê duyệt; API/consumer checks phù hợp; release staging và rollback sẵn sàng.

**Chưa chấp thuận** khi: hash khác nhưng chưa phân tích entry; test counts thiếu; CI toolchain khác chưa hiểu; attached artifacts chưa kiểm; hoặc chỉ có log `BUILD SUCCESS` mà không biết goal/version.

**Chặn** khi: required tests FAIL/bị skip; class/resource/API bắt buộc mất; phiên bản plugin không tương thích JDK/Maven; artifact có lỗi bảo mật/provenance; release thiếu chữ ký; hoặc build script có destructive side effect.

Nếu cần rollback:

1. Giữ revision POM/plugin version cũ và toolchain snapshot.
2. Trước deploy, revert thay đổi và chạy clean verify lại.
3. Nếu đã publish một release GAV bất biến, **không ghi đè artifact đó**: cần theo repository policy phát hành bản sửa mới.
4. Kiểm signing/staging state và consumers đã lấy artifact.
5. Lưu logs/hashes/diff và quyết định rollback.
6. Có owner chịu trách nhiệm nâng phiên bản tiếp theo khi upstream sửa lỗi.

Không tự coi revert một property là đã hoàn nguyên mọi artifact production nếu release trước đã được phát hành.

## 21. Bài tập có đáp án

### Bài A — thực hành A/B đầy đủ

Tạo 4 files trong mục 6, chạy baseline 3.3.0 rồi candidate 3.4.2 theo mục 7–8. Với mỗi run:

- Ghi Maven/JDK versions, exit code, plugin goal log.
- Kiểm 4 JUnit tests được chạy.
- Copy main JAR và Surefire XML ra `evidence`.
- So SHA-256, entries, manifest, extracted class/resource/POM.
- Chạy Java từ JAR đã lưu, xác nhận stdout `Hello, Maven!`.
- Chỉ khi mọi khác biệt có lời giải thích mới commit version đích.
- Build lại không override, kiểm artifact cuối.

**Đáp án định hướng:** báo cáo dựa trên **giá trị đo** từ environment thật; không giả định SHA giống hoặc khác. Nếu JAR khác chỉ vì metadata POM, phân loại metadata, không tuyên bố class regression.

### Bài B — bytewise và semantic comparison

Hai JAR có cùng entries và cùng Java classes nhưng MANIFEST khác `Created-By`. Có phải fail?

**Đáp án:** chưa chắc. Cần biết field đó có là contract/runtime dependency hay không, reproducibility policy và reports/consumers có đạt không. Nếu không ảnh hưởng và khác biệt được chấp thuận, upgrade có thể PASS dù hash khác.

### Bài C — plugin và JDK cùng đổi

Một PR nâng Compiler Plugin và JDK 17→21, đồng thời target `release=21`. Có thể quy bytecode khác cho Compiler Plugin không?

**Đáp án:** không vì ít nhất ba biến. Thử plugin upgrade dưới same JDK/target khi có thể; sau đó kiểm migration JDK riêng. Bytecode target 21 không chạy trên Java 17.

### Bài D — release artifacts

Một reactor tạo 10 JAR, 10 sources.jar và 10 javadoc.jar. Sau plugin upgrade chỉ còn 10 JAR; full verify PASS.

**Đáp án:** không được chấp thuận nếu release contract yêu cầu sources/Javadoc. Phải kiểm release profile và attach plugins; `verify` của config hiện tại có thể không kích hoạt các executions đó.

### Bài E — phân biệt reproducibility

Baseline build hai lần A1/A2 có hashes khác nhau, candidate hai lần B1/B2 có hashes bằng nhau. A/B hashes khác.

**Đáp án:** khả năng candidate đã sửa một nguồn nondeterminism, nhưng cần so từng entry và environments. **Khác biệt A/B không phải phép test định nghĩa reproducibility**; test đó là A1/A2, B1/B2 trong cùng instructions. Dùng outputTimestamp, artifact compare và diffoscope để tìm gốc.

## 22. Checklist trước khi merge PR nâng Maven plugin

**Chuẩn bị**

- [ ] Ghi full plugin GAV/version before/after và goals affected.
- [ ] Kiểm release notes/min Maven/JDK/plugin dependencies.
- [ ] Review parent/pluginManagement, CI active profiles, repositories.
- [ ] Ghi commit SHA, working tree, versions, command và môi trường.
- [ ] Lưu baseline JAR/report/log ở ngoài `target`.
- [ ] Thay đúng một biến trong thí nghiệm A/B.

**Kiểm chứng**

- [ ] Cả hai runs có Maven exit code được ghi thật.
- [ ] Goal/version trong logs đúng như thử nghiệm.
- [ ] Unit/IT/coverage/analysis gates đã chạy đủ theo policy.
- [ ] Test counts và failures/errors/skipped được so.
- [ ] Main và attached artifact inventory đúng GAV/classifier/extension.
- [ ] SHA-256 được tính từ bytes thật.
- [ ] Entries, manifest, embedded POM, classes/resources được so.
- [ ] Public API và consumer smoke/integration tests được chạy khi cần.
- [ ] Những differences có giải thích và reviewer approval.
- [ ] Có same-version reproducibility check nếu release yêu cầu.

**Release**

- [ ] Plugin version đích đã commit vào POM, build không CLI override.
- [ ] Full Reactor/CI/staging profile được chạy theo scope.
- [ ] PR build không được cấp publish/signing secrets.
- [ ] Source/Javadoc/signatures/repository POM được kiểm nếu có.
- [ ] Rollback/release immutability được xác nhận.
- [ ] Không có skip flags hoặc suppressions che lỗi.

## 23. Tổng kết

**Upgrade Maven plugin thành công = kiểm đúng plugin + kiểm đúng build + kiểm đúng artifact + kiểm đúng consumer contract.**

~~~text
Ghi source/toolchain + plugin GAV
              │
              ▼
Build trước nâng, lưu artifacts
              │
              ▼
Đổi đúng một plugin version
              │
              ▼
Build sau nâng, lưu artifacts
              │
              ▼
So tests + hash + ZIP entries
              │
              ▼
So manifest + POM + class/resource + API
              │
              ▼
Kiểm same-version reproducibility
              │
              ▼
Commit version mới, build không override
              │
              ▼
Full CI/staging + approval + rollback
~~~

Ghi nhớ: **SHA khác chỉ cho biết bytes khác**, không tự là regression; **SHA giống không thay consumer tests**. Maven JAR có thể nhúng POM, nên nâng plugin trong source POM có thể tự làm JAR hash khác. `outputTimestamp` giúp giảm nhiễu, không chứng minh mọi plugin/tool tạo output reproducible. Luôn có before/after evidence và kiểm version thật sự trong Maven log trước khi tuyên bố đã nâng an toàn.

## Tài liệu chính thức

- Apache Maven — Guide to Configuring Plug-ins: https://maven.apache.org/guides/mini/guide-configuring-plugins.html
- Maven — Introduction to the Build Lifecycle: https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html
- Maven — POM Reference: https://maven.apache.org/pom.html
- JAR Plugin 3.3.0 — `jar:jar`: https://maven.apache.org/plugins-archives/maven-jar-plugin-3.3.0/jar-mojo.html
- JAR Plugin 3.4.2 — Plugin Info & Requirements: https://maven.apache.org/plugins-archives/maven-jar-plugin-3.4.2/plugin-info.html
- JAR Plugin — `jar:jar` parameters: https://maven.apache.org/plugins/maven-jar-plugin/jar-mojo.html
- Maven Archiver — Embedded Maven Descriptor: https://maven.apache.org/components/shared-archives/maven-archiver-3.3.0/
- Maven — Configuring for Reproducible Builds: https://maven.apache.org/guides/mini/guide-reproducible-builds.html
- Maven Artifact Plugin `artifact:compare`: https://maven.apache.org/plugins/maven-artifact-plugin/compare-mojo.html
- Maven Artifact Plugin — Goals: https://maven.apache.org/plugins/maven-artifact-plugin/plugin-info.html
- Maven Help Plugin — Effective POM: https://maven.apache.org/plugins/maven-help-plugin/effective-pom-mojo.html
- Maven Surefire — Test reports: https://maven.apache.org/surefire/maven-surefire-plugin/
- Maven — Multiple Modules: https://maven.apache.org/guides/mini/guide-multiple-modules.html
- GitHub Actions — Checkout: https://github.com/actions/checkout
- GitHub Actions — Setup Java: https://github.com/actions/setup-java
- GitHub Actions — Upload Artifact: https://github.com/actions/upload-artifact
