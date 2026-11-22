# Phân biệt build riêng của IDE với build thực sự bằng Maven

## 1. “Build thành công” là thành công theo tiêu chuẩn nào?

Trong dự án Java có `pom.xml`, người phát triển thường mở mã bằng IntelliJ IDEA, Eclipse hoặc VS Code, nhấn **Build Project**, **Run** hoặc **Debug** rồi kết luận: “Dự án build được”. Nhưng IDE có thể đang dùng compiler và project model riêng, **không phải** đang chạy Maven lifecycle theo đúng POM.

Một Maven project có thể xuất hiện dưới nhiều hình thức:

- **IDE native build:** compile sources theo classpath/caches của IDE, thường là incremental compilation.
- **IDE Run/Debug:** chạy trực tiếp `main()` hoặc JUnit method bằng IDE run configuration.
- **IDE Maven invocation:** Maven tool window/extension gọi phase hoặc plugin goal được chọn.
- **Maven CLI:** `mvn` hoặc `mvnw` chạy các phases/goals cụ thể.
- **CI Maven build:** Maven chạy từ Git checkout, với toolchain, profile, settings và quality gates được pipeline kiểm soát.

**IDE native builder hữu ích và không mặc nhiên sai.** Nó có lợi thế phản hồi nhanh, code navigation, hot reload và debugger. Nhưng “compile hợp lệ” khác với “package đúng”, “unit tests pass”, “integration tests pass” hoặc “artifact có thể chạy ở runtime đích”.

Đây là bài học thuộc nhóm **IDE và CI**. Mục tiêu là biết **cách xác định Build nào đã thực thi**, chứ không phải chỉ tìm nút bấm để biến build đỏ thành xanh.

### Các câu hỏi cần trả lời trước khi kết luận

1. Command thực tế là gì: `Build Project`, `Run main`, `mvn compile`, `mvn package` hay `mvn clean verify`?
2. Runtime có dùng Maven thật không? Nếu có, Maven version, JDK Runner và goals nào?
3. Dependencies đến từ POM/effective POM hay libraries được thêm riêng trong IDE?
4. Resource filtering, generated sources, plugin executions và profiles có được áp dụng không?
5. Tests nào đã chạy; có Surefire/Failsafe report và số tests thực tế không?
6. Có packaged JAR/WAR đúng, manifest/resources đúng, đã smoke-test artifact cuối chưa?
7. CI có dùng cùng Git SHA, Maven/JDK/profiles và settings với local không?

## 2. Bảng phân biệt sáu thao tác thường bị gọi chung là “build”

| Thao tác | Cơ chế thường gặp | Bằng chứng đạt được | Chưa chứng minh |
| --- | --- | --- | --- |
| **IDE Build Project** | IntelliJ native builder / Eclipse JDT / Java language server | Source compile theo IDE model | Đầy đủ Maven plugins/lifecycle |
| **IDE Run Main** | IDE builds cần thiết rồi launch JVM | Một main class chạy trên IDE classpath | Packaged JAR chạy độc lập |
| **IDE Run JUnit** | JUnit runner theo IDE classpath | Method/class/suite được chọn pass | Mọi Maven integration/quality gate |
| **Maven goal trong IDE** | IDE gọi Maven runtime cho goal đã chọn | Goal/phase ấy đã chạy | Chưa chắc cùng JDK/settings/flags với CI |
| **`mvn clean verify`** | Maven CLI chạy clean và default lifecycle đến verify | Các goals được bind theo POM chạy | Không tự deploy hoặc chạy check chưa bind |
| **CI `./mvnw clean verify`** | Maven Wrapper trong pipeline | Build theo job định nghĩa | Không tương đương local nếu môi trường khác |

**Chỉ tên thư mục `target/`, biểu tượng Maven hoặc màn hình báo “Build Successful” không cho biết công cụ nào thật sự tạo ra file.**

Có project dùng IDE để import Maven dependencies nhưng vẫn compile bằng Java compiler riêng. Một dự án Maven được import thành công **không buộc mọi hành động IDE tự chạy Maven**.

## 3. Maven lifecycle có nhiều phase, IDE compiler thường chỉ bao phủ một phần

Default lifecycle rút gọn:

~~~text
validate
  |
generate-sources / process-resources
  |
compile / test-compile
  |
test                        Surefire nếu được bind
  |
package                     JAR / WAR / ...
  |
pre-integration-test
  |
integration-test             Failsafe nếu được bind
  |
post-integration-test
  |
verify                      Failsafe verify / quality checks
  |
install                     local Maven repository
  |
deploy                      remote deployment repository
~~~

Các phase khác còn tồn tại; sơ đồ nhằm thể hiện thứ tự chính. `clean` là **lifecycle riêng**, không tự chạy khi gọi `verify`; `site` cũng là lifecycle riêng.

| Maven command | Chạy tới đâu? | Điều chưa có |
| --- | --- | --- |
| `mvn compile` | `compile` | Chưa thực hiện test/package |
| `mvn test` | `test` | Chưa tạo JAR và thường chưa chạy Failsafe |
| `mvn package` | `package` | Chưa kết luận integration tests ở `verify` |
| `mvn verify` | `verify` | Không tự install/deploy |
| `mvn clean verify` | Clean rồi default lifecycle tới verify | Không upload remote, không tạo site tự động |
| `mvn install` | Tới install | Ghi local `.m2`; không đồng nghĩa publish remote |
| `mvn deploy` | Tới deploy | Có thể ghi remote, chỉ dùng theo quyền release |

**Maven `verify` chỉ thực hiện những checks đã được cấu hình/bind**. Ví dụ project có `*IT.java` nhưng không bind Maven Failsafe Plugin thì `mvn verify` vẫn có thể PASS dù integration test đó không chạy.

### Phase khác plugin goal

`mvn verify` gọi toàn bộ phase chain tới `verify`. Ngược lại:
- `mvn compiler:compile` gọi Compiler Plugin goal trực tiếp, không tự chạy full test/package lifecycle.
- `mvn surefire:test` có thể dùng `target/test-classes` từ lượt build trước nếu bạn chưa compile lại.
- `mvn clean` chỉ gọi clean lifecycle.
- `mvn clean verify` yêu cầu cả clean và default lifecycle đến verify.

**Một Maven goal thật chạy trong IDE vẫn chưa chứng minh full build**, nếu người dùng chỉ chọn `compiler:compile` thay vì `clean verify`.

## 4. IntelliJ IDEA: import POM khác với delegate Build cho Maven

IntelliJ IDEA cung cấp Maven Tool Window để import/reload POM, quản lý modules, xem dependencies và chạy Maven goals. Nhưng **Build → Build Project** mặc định có thể dùng **native IntelliJ builder**, giúp incremental Java compilation nhanh hơn.

Những thao tác không đồng nghĩa:

- **Build Project:** compile project bằng IDE builder khi chưa bật delegation.
- **Run/Debug Main:** dùng IDE Run Configuration, có thể có Before Launch build.
- **Maven Tool Window → Lifecycle → verify:** gọi Maven lifecycle đến phase `verify`.
- **Maven Tool Window → Plugins → plugin goal:** gọi goal cụ thể, không phải toàn bộ lifecycle.
- **Sync/Reload Maven Project:** đồng bộ classpath/source roots từ POM, không tự chạy full tests.
- **Delegate IDE build/run actions to Maven:** dùng Maven cho các actions tương ứng; phải xem goals chính xác được IDE gọi.

Đường dẫn cấu hình thường là:

~~~text
Settings / Preferences
  -> Build, Execution, Deployment
  -> Build Tools
  -> Maven -> Runner
  -> Delegate IDE build/run actions to Maven
~~~

Sau delegation, **đừng mặc định Build Project = `mvn clean verify`**. Mỗi IDE action có những goals tương ứng; khi cần cổng kiểm thử chính thức, tạo Maven Run Configuration rõ **`clean verify`**.

Theo tài liệu IntelliJ IDEA, **Rebuild Project trong cấu hình delegated không luôn tự thêm goal `clean`**. Nếu mục tiêu là xóa stale Maven outputs, chạy lệnh `clean verify` chủ đích.

### Sync POM không phải Maven build

Khi sửa dependency/plugin/parent trong `pom.xml`, Sync Maven Changes để IDE cập nhật project model. Dependency được thêm thủ công trong IntelliJ Project Structure **không tự xuất hiện trong POM** và có thể bị loại khi sync lại.

Nếu IntelliJ editor thấy một package nhưng CLI Maven báo thiếu symbol, kiểm tra libraries chỉ có trong IDE model trước khi cho rằng Maven/compiler bị lỗi.

## 5. IntelliJ Project SDK, Maven Runner JDK và terminal Java khác nhau

Các cấu hình có thể chọn những JDK khác nhau:

1. Project SDK và Module SDK của IDE.
2. Maven Importer JDK khi sync POM.
3. Maven Runner JRE/JDK khi IDE chạy Maven goals.
4. Terminal `JAVA_HOME` và `PATH`.
5. Maven Toolchains JDK khi project sử dụng.
6. CI JDK trong build container/runner.

Ví dụ **giả định**:

~~~text
IntelliJ Project SDK        JDK 21
IntelliJ Maven Runner JDK   JDK 17
Terminal JAVA_HOME          JDK 21
CI JVM                      JDK 17
POM maven.compiler.release  17
~~~

Nếu IDE compiler thực tế dùng Java 21 API, source có thể được IDE chấp nhận nhưng Maven compile với `--release 17` sẽ từ chối. **`maven.compiler.release=17` là target Java language/API, không tự xác nhận Maven đang chạy bằng chính JDK 17.**

Kiểm tra:

~~~bash
mvn --version
java -version
javac -version
mvn -B -ntp help:effective-pom -Doutput=target/effective-pom.xml
~~~

Đừng suy ra Maven Runner JDK chỉ bằng cách nhìn Project SDK trên giao diện.

## 6. Eclipse và m2e: workspace build không giống CLI reactor

Eclipse JDT có incremental builder. **M2Eclipse (m2e)** tích hợp Maven để import POM, resolve dependencies, chạy Maven goals và xử lý một số plugin lifecycle mappings.

Các điểm quan trọng:

- **Build Automatically** chủ yếu là IDE workspace build, không tự nghĩa là Maven `clean verify`.
- m2e có Maven-aware resource builder và có thể thực hiện một số plugin executions. Vì vậy nói “Eclipse luôn bỏ qua Maven plugin” là **không đúng**.
- m2e có thể resolve dependency từ **workspace projects** chưa được install vào local Maven repository.
- Runtime Maven được embed khi import có thể khác external Maven được cấu hình cho **Run As → Maven build**.
- **Update Maven Project** đồng bộ Eclipse project model, không thay `clean verify`.

Ví dụ `service` dùng `api` trong cùng Eclipse workspace nên IDE build PASS; nhưng khi chạy `mvn verify` **riêng** trong `service` mà `api` artifact chưa có trong local repo, Maven resolution có thể FAIL. Dùng root reactor hoặc `-pl/-am` thay vì mượn một JAR cũ.

M2Eclipse FAQ còn giải thích vì sao resource folder có thể bị JDT đánh dấu excluded: Maven Builder cần thực hiện resource filtering; JDT copy trực tiếp có thể **ghi đè filtered resources**.

## 7. VS Code: Java Run/Debug khác Maven Explorer

Visual Studio Code với các Java extensions có Language Server và Debugger. Maven for Java extension bổ sung **Maven Explorer**, cho phép chạy Maven Lifecycle/Plugin goals.

- **Run Java/Debug Java:** có thể launch bằng Java debugger và classpath IDE đã resolve.
- **Maven Explorer → verify:** yêu cầu Maven goal/phase phù hợp.
- **Terminal → `./mvnw clean verify`:** Maven Wrapper shell command khi wrapper đã có.
- **Java workspace compilation:** không mặc nhiên chạy Maven `verify`.

Xem **terminal/output panel** của extension để biết goal, POM, module và Maven runtime thực sự. Không dựa vào tên nút Run/Build vì extensions và phiên bản IDE có thể khác nhau.

Các Maven plugins trong project có thể thực thi code khi build; chỉ chạy Maven extension tasks với workspace đáng tin và quyền phù hợp.

## 8. Demo Java 17: vì sao compile PASS nhưng test/build FAIL?

Project đơn module gồm:
- `pom.xml` pin Maven Clean, Enforcer, Resources, Compiler, Surefire, Jar và Failsafe Plugins.
- `app.properties` chứa `@project.version@` để Maven filter.
- `GreetingApp` đọc metadata từ resource và in message.
- **Hai JUnit 5 unit tests** xác minh behavior và version.
- **Một Failsafe integration test** mở packaged JAR, kiểm tra Main-Class/resource và chạy `java -jar`.
- Tình huống đổi một string Java hoàn toàn hợp lệ nhưng làm assertions FAIL.

Cấu trúc:

~~~text
ide-vs-maven-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/vn/example/build/GreetingApp.java
    │   └── resources/app.properties
    └── test/
        └── java/vn/example/build/
            ├── GreetingAppTest.java
            └── GreetingJarIT.java
~~~

**Yêu cầu thực hành:** Maven 3.9+, JDK 17+, Maven repositories truy cập được dependencies/plugins. Không cần database, Docker, Git remote hay deploy server.

### 8.1. `pom.xml` đầy đủ

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>vn.example.build</groupId>
    <artifactId>ide-vs-maven-demo</artifactId>
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
            <version>5.10.2</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <resources>
            <resource>
                <directory>src/main/resources</directory>
                <filtering>true</filtering>
                <includes>
                    <include>app.properties</include>
                </includes>
            </resource>
        </resources>

        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-clean-plugin</artifactId>
                <version>3.3.2</version>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-enforcer-plugin</artifactId>
                <version>3.5.0</version>
                <executions>
                    <execution>
                        <id>require-platform</id>
                        <phase>validate</phase>
                        <goals><goal>enforce</goal></goals>
                        <configuration>
                            <rules>
                                <requireMavenVersion>
                                    <version>[3.9,)</version>
                                </requireMavenVersion>
                                <requireJavaVersion>
                                    <version>[17,)</version>
                                </requireJavaVersion>
                            </rules>
                        </configuration>
                    </execution>
                </executions>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-resources-plugin</artifactId>
                <version>3.3.1</version>
                <configuration>
                    <delimiters>
                        <delimiter>@</delimiter>
                    </delimiters>
                    <useDefaultDelimiters>false</useDefaultDelimiters>
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
                <version>3.2.5</version>
                <configuration>
                    <failIfNoTests>true</failIfNoTests>
                </configuration>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
                <configuration>
                    <archive>
                        <manifest>
                            <mainClass>vn.example.build.GreetingApp</mainClass>
                        </manifest>
                    </archive>
                </configuration>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-failsafe-plugin</artifactId>
                <version>3.2.5</version>
                <executions>
                    <execution>
                        <id>check-actual-jar</id>
                        <goals>
                            <goal>integration-test</goal>
                            <goal>verify</goal>
                        </goals>
                    </execution>
                </executions>
                <configuration>
                    <failIfNoTests>true</failIfNoTests>
                    <systemPropertyVariables>
                        <demo.jar>${project.build.directory}/${project.build.finalName}.jar</demo.jar>
                    </systemPropertyVariables>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### Chú ý về POM

1. Enforcer ở **`validate`** kiểm tra Maven/JDK, không chạy khi chỉ native IDE compile.
2. Resources Plugin filter version khi Maven xử lý resources.
3. Compiler Plugin dùng Java 17 target; Surefire chạy tests `*Test`.
4. Jar Plugin cấu hình **Main-Class**, tạo JAR chạy bằng `java -jar`.
5. Failsafe cần explicit `integration-test` và `verify` executions cho `*IT`.
6. JUnit Jupiter scope `test`; main JAR không mang dependency này trong runtime.
7. POM **không có `distributionManagement`**, vì demo không publish remote.
8. Versions pin phục vụ bài tập, **không khẳng định là versions mới nhất**.

Một dự án thực có thể kế thừa các plugin versions từ parent/`pluginManagement`; khi chẩn đoán phải đọc **effective POM**, không chỉ source POM.

## 9. `src/main/resources/app.properties` và resource filtering

~~~properties
app.name=@project.artifactId@
app.version=@project.version@
~~~

Maven Resources Plugin tạo bản filtered, dự kiến tại `target/classes/app.properties`:

~~~properties
app.name=ide-vs-maven-demo
app.version=1.0.0
~~~

Đó là file resource thực được package vào JAR nếu Maven `process-resources` và `package` chạy đúng. **IDE builder có thể xử lý hoặc không xử lý filtering theo cách khác**, tùy IDE/extension/config; không nên khẳng định mọi IDE đều copy raw resource.

Nếu IDE Run gặp token `@project.version@`, hãy kiểm tra **classloader/resource output path** của IDE và cấu hình Maven delegation trước khi sửa code hoặc đặt version cứng trong source resource.

## 10. `src/main/java/vn/example/build/GreetingApp.java`

~~~java
package vn.example.build;

import java.io.IOException;
import java.io.InputStream;
import java.util.Properties;

public final class GreetingApp {
    private GreetingApp() {
    }

    public static String greeting() {
        return "HELLO FROM MAVEN";
    }

    public static String version() throws IOException {
        Properties properties = new Properties();
        try (InputStream input =
                GreetingApp.class.getResourceAsStream("/app.properties")) {
            if (input == null) {
                throw new IOException("Missing app.properties");
            }
            properties.load(input);
        }

        String value = properties.getProperty("app.version");
        if (value == null || value.isBlank()
                || value.contains("@")) {
            throw new IllegalStateException("Unfiltered app.version");
        }
        return value;
    }

    public static String message() throws IOException {
        return greeting() + " | version=" + version();
    }

    public static void main(String[] args) throws IOException {
        System.out.println(message());
    }
}
~~~

Ứng dụng dùng **Java standard library** để đọc resource; runtime không cần JUnit JAR. `project.version` của Maven là build-time property, Java process không tự có nó làm system property — cần resource filtering hoặc metadata được đóng gói có chủ đích.

## 11. `src/test/java/vn/example/build/GreetingAppTest.java`

~~~java
package vn.example.build;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class GreetingAppTest {
    @Test
    void greetingMeetsContract() {
        assertEquals("HELLO FROM MAVEN", GreetingApp.greeting());
    }

    @Test
    void versionWasFiltered() throws Exception {
        String version = GreetingApp.version();
        assertFalse(version.contains("@"));
        assertTrue(version.matches(
                "\\d+\\.\\d+\\.\\d+(?:-SNAPSHOT)?"));
        assertEquals("HELLO FROM MAVEN | version=" + version,
                GreetingApp.message());
    }
}
~~~

Test kiểm tra **hành vi** và **metadata resource thực tế**, không chỉ Java syntax. Test không hardcode project version `1.0.0` để cho phép đổi version theo policy.

Tên `*Test` phù hợp Surefire. `mvn test` chạy tests này (nếu plugin/dependencies được resolve và không skip); `mvn verify` bao gồm test phase.

## 12. `src/test/java/vn/example/build/GreetingJarIT.java`

~~~java
package vn.example.build;

import org.junit.jupiter.api.Test;

import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Locale;
import java.util.Properties;
import java.util.concurrent.TimeUnit;
import java.util.jar.Attributes;
import java.util.jar.JarEntry;
import java.util.jar.JarFile;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.junit.jupiter.api.Assertions.fail;

class GreetingJarIT {
    @Test
    void packagedJarRuns() throws Exception {
        String configured = System.getProperty("demo.jar");
        assertNotNull(configured, "Missing demo.jar property");
        Path jarPath = Path.of(configured).toAbsolutePath();
        assertTrue(Files.isRegularFile(jarPath));

        String version;
        try (JarFile jar = new JarFile(jarPath.toFile())) {
            assertNotNull(jar.getManifest());
            assertEquals("vn.example.build.GreetingApp",
                    jar.getManifest().getMainAttributes()
                            .getValue(Attributes.Name.MAIN_CLASS));
            assertNotNull(jar.getEntry(
                    "vn/example/build/GreetingApp.class"));
            JarEntry metadata = jar.getJarEntry("app.properties");
            assertNotNull(metadata);

            Properties properties = new Properties();
            try (InputStream input = jar.getInputStream(metadata)) {
                properties.load(input);
            }
            version = properties.getProperty("app.version");
            assertNotNull(version);
            assertTrue(version.matches(
                    "\\d+\\.\\d+\\.\\d+(?:-SNAPSHOT)?"));
        }

        String executable = System.getProperty("os.name")
                .toLowerCase(Locale.ROOT).contains("win")
                ? "java.exe" : "java";
        Path java = Path.of(System.getProperty("java.home"),
                "bin", executable);

        Process process = new ProcessBuilder(
                java.toString(), "-jar", jarPath.toString())
                .redirectErrorStream(true)
                .start();

        if (!process.waitFor(15, TimeUnit.SECONDS)) {
            process.destroyForcibly();
            process.waitFor(5, TimeUnit.SECONDS);
            fail("Packaged JVM timed out");
        }

        String output = new String(
                process.getInputStream().readAllBytes(),
                StandardCharsets.UTF_8).strip();

        assertEquals(0, process.exitValue(),
                "Child output: " + output);
        assertEquals("HELLO FROM MAVEN | version=" + version,
                output);
    }
}
~~~

**Tại sao integration test cần thiết?** IDE Run có thể chạy main từ `target/classes` hoặc IDE output cùng một classpath rất khác packaged JAR. `GreetingJarIT` mở JAR thật, kiểm tra manifest, resource và main class, rồi chạy chính `java -jar` trong một JVM mới.

Test chỉ in một dòng nhỏ nên đọc process output sau `waitFor` là phù hợp. Ứng dụng thực có nhiều logs cần tiêu thụ stdout/stderr song song hoặc redirect để tránh deadlock. Test trên chưa kiểm tra database/network vì demo không có các thành phần đó.

## 13. Baseline: Maven build thực sự và stdout

Từ thư mục chứa `pom.xml`:

~~~bash
mvn --version
mvn -B -ntp clean verify
java -jar target/ide-vs-maven-demo-1.0.0.jar
~~~

Trong trường hợp project được tạo đúng, Maven sẽ:
1. Clean output cũ.
2. Enforcer kiểm tra Maven 3.9+/JDK 17+.
3. Filter resource `app.properties`.
4. Compile Java và tests.
5. Surefire chạy **hai unit test methods**.
6. Package `ide-vs-maven-demo-1.0.0.jar`.
7. Failsafe chạy **một integration test** trên JAR cuối.
8. Failsafe `verify` xác nhận kết quả.
9. Dừng ở `verify`, **không install/deploy**.

**Stdout chính xác của riêng lệnh `java -jar` cuối**:

~~~text
HELLO FROM MAVEN | version=1.0.0
~~~

Không dùng một transcript Maven console cố định: plugin logs/timestamps/cache khác nhau theo môi trường.

Kiểm tra outputs:

~~~text
target/classes/vn/example/build/GreetingApp.class
target/classes/app.properties
target/test-classes/vn/example/build/GreetingAppTest.class
target/test-classes/vn/example/build/GreetingJarIT.class
target/surefire-reports/...
target/failsafe-reports/...
target/ide-vs-maven-demo-1.0.0.jar
~~~

Dấu `...` là nhóm báo cáo, không phải literal file name. **Có `target/` chưa đủ chứng minh Maven vừa chạy** — output có thể còn từ lần trước hoặc do IDE dùng chung directory.

## 14. Thí nghiệm: compiler PASS nhưng Maven test FAIL

Chỉ trong **bản sao bài tập**, sửa method:

~~~java
public static String greeting() {
    return "HELLO FROM IDE";
}
~~~

Đây là **đoạn sửa có chủ đích làm vi phạm hợp đồng**, không phải code chuẩn để giữ lại.

- Java vẫn **hợp lệ cú pháp và kiểu**, nên IDE native **Build Project có thể PASS**.
- IDE Run có thể in `HELLO FROM IDE | version=1.0.0` nếu resource đã được filter đúng; nếu IDE resource chưa filter, nó có thể báo lỗi khác.
- Chạy **`mvn -B -ntp clean verify`**: Surefire unit test `greetingMeetsContract` FAIL, vì expected `"HELLO FROM MAVEN"` nhưng actual `"HELLO FROM IDE"`.

Điều này chứng minh **compile thành công không phải behavior pass**. Đọc `target/surefire-reports/` để xác nhận failure, thay vì kết luận chung chung Maven khác IDE vì plugin bị lỗi.

Sau thí nghiệm, **sửa lại đúng dòng đó** thành `return "HELLO FROM MAVEN";` trong bản sao, chạy lại `mvn clean verify` để xác nhận baseline PASS. Không dùng `git reset --hard`/`git clean -fdx` trên workspace dùng chung để xóa thay đổi khác.

## 15. IDE Run PASS nhưng JAR cuối fail: lỗi packaging

IDE có thể chạy main với compiled classes và dependencies đã load sẵn. Nhưng packaged JAR có thể:
- Thiếu `Main-Class` trong manifest.
- Thiếu resource đã filter hoặc resource nằm sai đường dẫn.
- Không kèm runtime dependencies cần thiết (thin JAR vs shaded/assembly).
- Có class files biên dịch cho Java cao hơn runtime đích.
- Thiếu generated files hoặc binary asset được Maven plugins đóng gói.

Do đó chạy:

~~~bash
jar tf target/ide-vs-maven-demo-1.0.0.jar
java -jar target/ide-vs-maven-demo-1.0.0.jar
~~~

Các entries đáng tìm:

~~~text
META-INF/MANIFEST.MF
vn/example/build/GreetingApp.class
app.properties
~~~

Demo dùng JAR executable vì đây là ứng dụng không cần external runtime library. Với library JAR, không nhất thiết có Main-Class; test phù hợp là **consumer compile/runtime hoặc API/ABI test**, không phải luôn `java -jar`.

## 16. Khi IDE classpath và Maven classpath khác nhau

Một IDE có thể có JAR được thêm thủ công qua Project Structure/Build Path nhưng POM không khai báo. Khi đó:

~~~text
IDE model:
  project classes
  + manually-added-library.jar

Maven effective POM:
  project dependencies
  - không có manually-added-library
~~~

IDE compile PASS, Maven compile từ checkout sạch có thể báo:

~~~text
package example.external does not exist
cannot find symbol
~~~

Đây là **lỗi minh họa**, không thuộc demo runnable. Sửa bằng dependency GAV/version/scope hợp lệ trong POM, không dùng `systemPath` trỏ tới thư mục cá nhân.

Chiều ngược lại: POM có dependency nhưng IDE chưa Sync, nên IDE đỏ trong khi `mvn verify` PASS. Xác minh:

~~~bash
mvn -B -ntp help:effective-pom -Doutput=target/effective-pom.xml
mvn -B -ntp org.apache.maven.plugins:maven-dependency-plugin:3.11.0:tree
~~~

Goal đầy đủ ở trên chính là một invocation **Maven Dependency Plugin `dependency:tree`** với version pin. `dependencyManagement` chỉ quản lý version/metadata khi dependency được sử dụng, **không tự thêm dependency vào classpath**.

## 17. Generated sources và annotation processing

Một POM có thể gọi Protobuf/OpenAPI/ANTLR/JAXB/jOOQ/annotation processors tại `generate-sources` hoặc `compile`. Những khác biệt phổ biến:

- IDE giữ generated code cũ trong project model, compile PASS; `mvn clean verify` từ checkout mới không sinh lại vì thiếu input/plugin config.
- Maven có annotation processor được cấu hình, IDE chưa bật annotation processing → Maven PASS, IDE editor báo thiếu generated methods.
- IDE extension/plugin dùng generator version khác POM → codegen behavior khác.
- IDE đánh dấu nhầm source roots hoặc import cache stale.
- CI thiếu schema file, license config hoặc environment variable chỉ có trên máy developer.

Sửa **generator goals/source inputs/processor paths ở POM hoặc thiết lập IDE sync** theo chính sách. Không copy generated files tùy ý vào source tree chỉ để Build Project xanh.

## 18. Profiles, settings và flags tạo ra hai Maven builds khác nhau

Ngay cả khi cả IDE và terminal cùng gọi Maven, kết quả có thể khác bởi:

| Yếu tố | Ví dụ |
| --- | --- |
| Maven version | bundled vs external vs Maven Wrapper |
| Maven JDK | IntelliJ Runner JRE vs CLI `JAVA_HOME` vs CI JDK |
| Maven profiles | `-Pdev`, `-Pci`, profile auto activation |
| Settings | `~/.m2/settings.xml`, `-s`, proxies, mirrors |
| Local repository | `.m2` cache khác hoặc `-Dmaven.repo.local` |
| Dependency policy | SNAPSHOT update, offline `-o`, forced updates `-U` |
| Test skip | `-DskipTests`, `-Dmaven.test.skip=true`, `-DskipITs` |
| Modules | root reactor vs one child, `-pl`, `-am` |
| OS/variables | timezone, locale, JDK vendor, resource paths |
| Workspace | dirty files, untracked resources, stale `target` |

Hai lệnh không tương đương:

~~~bash
mvn -Pdev -DskipTests package
mvn -Pci clean verify
~~~

Lệnh đầu đang **skip tests**, dừng ở package và bật dev profile. Lệnh sau dọn output, chạy tới verify với CI profile. **Không thể dùng kết quả xanh của lệnh đầu làm bằng chứng đầy đủ cho lệnh sau.**

Để xem active profiles:

~~~bash
mvn -B -ntp help:active-profiles
~~~

Để xem effective POM:

~~~bash
mvn -B -ntp help:effective-pom -Doutput=target/effective-pom.xml
~~~

File effective POM dùng để phân tích, **không sửa thay cho source POM**.

## 19. Maven Wrapper: hữu ích, nhưng không tự cố định JDK

Một project dùng Maven Wrapper thường có:

~~~text
mvnw
mvnw.cmd
.mvn/wrapper/maven-wrapper.properties
~~~

Sau khi setup wrapper trong project và review/commit đầy đủ, dùng:

**Linux/macOS:**

~~~bash
./mvnw --version
./mvnw -B -ntp clean verify
~~~

**Windows PowerShell:**

~~~powershell
.\mvnw.cmd --version
.\mvnw.cmd -B -ntp clean verify
~~~

Wrapper giúp mọi người dùng Maven distribution version theo project policy và có thể tự tải Maven khi cần. Tuy nhiên **không tự pin JDK, parent/BOM, plugins, dependencies, settings hoặc environment variables**. Maven Enforcer/JDK Toolchains và CI setup vẫn cần.

Không tự tạo Maven Wrapper files trong repository người khác chỉ để thử. Việc thêm Wrapper scripts và properties là một thay đổi được version control và phải review.

## 20. Multi-module Reactor: IDE workspace có thể che lỗi resolution

Project minh họa khác:

~~~text
platform/
├── pom.xml            packaging=pom, modules=api,service
├── api/pom.xml        jar
└── service/pom.xml    jar, depends on api
~~~

Trong IDE, module `service` có thể compile bằng classes của `api` đang mở trong workspace. Nhưng Maven build **riêng thư mục service** có thể không resolve được `api` nếu nó chưa được publish/install local.

Từ root:

~~~bash
mvn -B -ntp clean verify
~~~

Hoặc để kiểm tra module service và reactor dependencies:

~~~bash
mvn -B -ntp -pl :service -am verify
~~~

`-pl` chọn module, `-am` build modules liên quan từ reactor. Dẫu vậy đây **không thay full root build** nếu modules khác có checks bắt buộc.

**`<modules>` chỉ khai báo aggregation, không tự làm `service` phụ thuộc `api`.** Cần actual `<dependency>` đúng để Maven hiểu reactor graph; `dependencyManagement` entry đơn thuần không tạo dependency.

## 21. Clean, cache và stale outputs

IDE thường giữ:
- Incremental compiler cache.
- Workspace-resolved module libraries.
- Generated sources từ build trước.
- Filtered resources còn trong `target/classes`.
- IDE-specific output directories, có thể chia sẻ với Maven.

Khi muốn biết một checkout có tự build được không, **Maven clean build trong workspace an toàn** tốt hơn nhấn IDE Rebuild rồi suy tương đương.

Nhưng Maven Clean Plugin có thể được cấu hình dọn ngoài `target` bằng filesets. Đừng chạy destructive `clean` trên workspace chưa kiểm tra hoặc `git reset --hard`/`git clean -fdx` trên thư mục nhiều người cùng dùng. Tốt hơn tạo checkout/CI runner riêng.

**Một `target/` tồn tại không chứng minh output thuộc về Git commit hoặc lượt build hiện tại.** Kiểm tra command, run logs, test reports, file digest và nguồn.

## 22. Checklist bằng chứng “đã chạy Maven thật”

Đừng chỉ dựa vào dòng `BUILD SUCCESS`. Thu thập:

1. **Command đầy đủ** `mvn -B -ntp clean verify` hoặc Wrapper tương ứng.
2. **Maven/JDK version** từ Maven invocation ấy.
3. **Working directory và Git SHA** của source được build.
4. **Active profiles/flags/settings** và project GAV.
5. **Plugin goals thực sự chạy**: Enforcer, Resources, Compiler, Surefire, Jar, Failsafe.
6. **Số tests discovered và executed**, không có skip ngoài policy.
7. **`target/surefire-reports` và `target/failsafe-reports`** của build hiện tại.
8. **Packaged artifact** đúng GAV/classifier/type, có manifest/resource đúng.
9. **Artifact smoke test** chạy độc lập khỏi IDE classpath.
10. **Checksum/evidence** nếu CI hoặc phát hành yêu cầu.

Log Maven thường có goal lines dạng:

~~~text
--- maven-resources-plugin:...:resources ...
--- maven-compiler-plugin:...:compile ...
--- maven-surefire-plugin:...:test ...
--- maven-jar-plugin:...:jar ...
--- maven-failsafe-plugin:...:integration-test ...
--- maven-failsafe-plugin:...:verify ...
~~~

Đây là **mẫu loại goal**, không phải transcript thật hoặc kết quả chắc chắn của mọi project. `BUILD SUCCESS` chỉ nói **những goals đã chọn** thành công, không nói có bao nhiêu check chưa được cấu hình.

## 23. Tạo parity giữa IDE, CLI và CI

Một pipeline trung tính:

~~~text
Checkout approved source SHA
          |
          v
Setup JDK 17+ / selected Maven or Maven Wrapper
          |
          v
Resolve dependencies from approved repositories
          |
          v
mvn -B -ntp clean verify
          |
          +-- Surefire unit reports
          +-- Failsafe integration reports
          +-- packaged JAR
          |
          v
Run java -jar on final JAR
          |
          v
Record commit, Maven/JDK, profiles, artifact digest
          |
          v
Store CI reports/artifacts, no remote deploy in PR job
~~~

Khi đã có Maven Wrapper trong Git và Linux CI runner:

~~~bash
./mvnw --version
./mvnw -B -ntp clean verify
java -jar target/ide-vs-maven-demo-1.0.0.jar
sha256sum target/ide-vs-maven-demo-1.0.0.jar
~~~

Nếu chưa có Wrapper, dùng Maven version được pipeline pin. **CI phải dừng khi `verify` trả exit code khác 0**, không tiếp tục tạo checksum rồi kết luận job xanh. Source từ PR chưa được trust không nên nhận deploy credentials vì Maven plugins có thể thực thi code trong build.

## 24. Khi IDE PASS nhưng Maven FAIL: chẩn đoán theo phase

| Triệu chứng | Nguyên nhân có thể | Hướng điều tra |
| --- | --- | --- |
| IDE Build PASS, Maven compile FAIL | IDE-only library, source/API level hoặc dependency khác | IDE Build Path, effective POM, Maven dependency tree |
| IDE Build PASS, Maven Surefire FAIL | Behavior không đáp ứng assertion | `target/surefire-reports` |
| IDE Run PASS, `java -jar` FAIL | Thiếu Main-Class, resource, runtime dependency | Jar entries và Failsafe artifact test |
| IDE PASS, Maven Enforcer FAIL | Maven/JDK Runner khác policy | `mvn --version`, Maven Runner JRE |
| IDE PASS, Maven codegen FAIL | Stale generated sources/cache | Clean checkout và generator input/plugin |
| Maven PASS, IDE editor đỏ | POM chưa sync hoặc IDE SDK/cache khác | Reload Maven Project, source roots |
| Maven CLI PASS, Maven IDE FAIL | Maven version/JDK/settings/profiles khác | Runner config và effective POM |
| CI PASS nhưng IT không chạy | Failsafe chưa bind hoặc `-DskipITs` | `target/failsafe-reports` |
| `mvn package` PASS, `verify` FAIL | Check ở integration-test/verify | Plugin executions, reports |
| IDE Rebuild PASS, Maven clean FAIL | Rebuild action không chạy Maven clean | Log và actual command |

**Quy trình debug hiệu quả:** (1) tái hiện bằng `mvn clean verify`; (2) đọc phase fail; (3) so Maven/JDK/settings/profiles; (4) xem effective POM/dependency tree; (5) đọc test reports/JAR; (6) sửa đúng nơi; (7) chạy lại clean verify và CI.

Dùng `mvn -e -B -ntp clean verify` để thấy stack traces khi cần. `mvn -X` có thể lộ nhiều URL/settings và thông tin môi trường; phải redaction trước khi chia sẻ logs ra ngoài.

## 25. Những hiểu lầm cần tránh

1. **POM có Maven icon → mọi nút IDE Build đều chạy Maven.** Sai.
2. **Maven Sync/Reload → đã chạy Surefire và Failsafe.** Sai.
3. **`mvn compile` PASS → `mvn verify` cũng PASS.** Không chắc.
4. **IDE Run PASS → packaged JAR có thể chạy.** Không chắc.
5. **Thêm JAR vào IDE libraries → dependency đã có trong Maven.** Sai.
6. **Build Project được delegate → chắc chắn chạy `mvn clean verify`.** Không mặc nhiên.
7. **Project SDK → chắc chắn là Maven runner JDK.** Sai.
8. **Maven Wrapper → tự khóa luôn JDK và transitive dependencies.** Sai.
9. **Có `target/` → Maven vừa chạy.** Không có đủ bằng chứng.
10. **Chỉ chạy một test trong IDE → full test suite đã pass.** Sai.
11. **`-DskipTests` vẫn chứng minh test PASS.** Sai.
12. **Xóa toàn bộ workspace chung để xử lý cache.** Có nguy cơ mất dữ liệu.
13. **`mvn deploy` chỉ để thử build.** Deploy có thể ghi remote; không dùng khi chưa được phép.

## 26. Bài tập thực hành

**Bài 1:** Dựng đủ POM và bốn file source/resource theo mục 8–12. Chạy `mvn -B -ntp clean verify`, kiểm tra số unit và integration tests.

**Bài 2:** Chạy `java -jar target/ide-vs-maven-demo-1.0.0.jar`; stdout phải là **HELLO FROM MAVEN | version=1.0.0**.

**Bài 3:** So `app.properties` nguồn với bản filtered dưới `target/classes` và trong JAR.

**Bài 4:** Sửa `greeting()` thành `"HELLO FROM IDE"` trong bản sao. Giải thích vì sao IDE native compile PASS nhưng Maven Surefire FAIL. Khôi phục code và kiểm tra lại.

**Bài 5:** So `mvn compile`, `mvn test`, `mvn package`, `mvn verify`, `mvn clean verify`; tìm thời điểm Surefire/Failsafe chạy.

**Bài 6:** Đọc manifest bằng `jar tf`/archive tool; giải thích vì sao IDE Run không thay thế packaged artifact smoke test.

**Bài 7:** So Project SDK, Maven Runner JDK, terminal `mvn --version` và CI JVM; phân biệt Java SDK với `maven.compiler.release`.

**Bài 8:** Mô tả một IDE-only library và một POM dependency. Vì sao cách giải quyết lâu dài phải dựa vào Maven POM/effective model?

**Bài 9:** Dùng `help:active-profiles`, `help:effective-pom`, `maven-dependency-plugin:tree` để xác định effective environment của một Maven run.

**Bài 10:** Thiết kế CI chạy Wrapper `clean verify`, lưu test reports và artifact digest. Viết điều kiện fail khi Surefire/Failsafe bị skip hoặc JAR smoke test fail.

## 27. Checklist xác nhận Maven build thực sự đã PASS

1. Command goals/phases đã ghi chính xác.
2. POM, module và working directory đúng.
3. Source Git commit và trạng thái workspace có thể xác minh.
4. Maven/JDK/toolchain versions đúng policy.
5. Active profiles, settings và repositories được xác định.
6. Không dùng IDE-only classpath/libraries để kết luận.
7. Generated sources và resources được xử lý theo POM.
8. Compiler Java release/API target đúng.
9. Surefire chạy đủ unit tests.
10. Failsafe chạy đủ integration tests nếu được yêu cầu.
11. Enforcer/static/quality gates thật sự được bind.
12. Không skip tests/quality checks ngoài policy.
13. JAR/WAR artifact được package đúng.
14. Manifest/resource/runtime dependencies được kiểm tra.
15. Runtime smoke test dùng đúng artifact cuối.
16. Test reports thuộc về build và source hiện tại.
17. CI chạy cùng goals và environment được duyệt.
18. Artifact digest/CI logs được giữ khi cần traceability.
19. IDE Build/Run/Sync không bị nhầm với full Maven verification.
20. **`verify` PASS không có nghĩa đã install hoặc deploy.**

### Tổng kết

**IDE Build và Maven Build có thể cùng báo thành công nhưng đang kiểm tra những thứ khác nhau.** IDE ưu tiên incremental compile và trải nghiệm debug. Maven thực thi POM, lifecycle phases và plugin goals, bao gồm resource filtering, tests, package và verification **nếu chúng được cấu hình đúng**.

Để chứng minh dự án có thể build trong CI, hãy dùng **Maven CLI hoặc Maven Wrapper chạy `clean verify`** với JDK, profiles và settings đã chốt. Nếu IDE xanh mà Maven đỏ, hãy kiểm tra **phase fail, classpath, resource filtering, generated sources, test reports, packaging và Maven runner JDK**. Nếu Maven xanh mà IDE đỏ, hãy Sync Maven Project và kiểm tra IDE model. **Bằng chứng build chính thức là lệnh/goal và kết quả thực**, không phải chỉ một biểu tượng màu xanh.

### Tài liệu chính thức

- [Apache Maven — Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Apache Maven — Maven Wrapper](https://maven.apache.org/tools/mavenwrapper.html)
- [Apache Maven — Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
- [Apache Maven Compiler Plugin](https://maven.apache.org/plugins/maven-compiler-plugin/)
- [Apache Maven Resources Plugin](https://maven.apache.org/plugins/maven-resources-plugin/)
- [Apache Maven Surefire Plugin](https://maven.apache.org/surefire/maven-surefire-plugin/)
- [Apache Maven Failsafe Plugin](https://maven.apache.org/surefire/maven-failsafe-plugin/)
- [Apache Maven Enforcer Plugin](https://maven.apache.org/enforcer/maven-enforcer-plugin/)
- [IntelliJ IDEA — Delegate Build and Run Actions to Maven](https://www.jetbrains.com/help/idea/delegate-build-and-run-actions-to-maven.html)
- [IntelliJ IDEA — Compile and Build Applications](https://www.jetbrains.com/help/idea/compiling-applications.html)
- [IntelliJ IDEA — Maven Support](https://www.jetbrains.com/help/idea/maven-support.html)
- [Eclipse m2e — Documentation](https://eclipse.dev/m2e/documentation/m2e-documentation.html)
- [Eclipse m2e — FAQ](https://eclipse.dev/m2e/documentation/m2e-faq.html)
- [VS Code — Java Build Tools](https://code.visualstudio.com/docs/java/java-build)
