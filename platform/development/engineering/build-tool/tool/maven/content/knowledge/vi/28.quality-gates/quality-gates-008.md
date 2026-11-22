# Gắn các cổng chất lượng vào vòng đời trước install hoặc deploy trong Maven

Trong một dự án Java dùng Maven, **quality gate (cổng chất lượng)** là điều kiện mà bản build phải thỏa trước khi được coi là đủ tốt để đưa vào repository hoặc môi trường sử dụng. Ví dụ: toolchain phù hợp, mã biên dịch được, unit tests và integration tests đạt, độ phủ test tối thiểu và quy tắc style không bị vi phạm.

Điều quan trọng không chỉ là **có công cụ kiểm tra**, mà còn phải **gắn đúng goal của công cụ vào một phase của Maven lifecycle**, cấu hình công cụ **thực sự làm build thất bại** khi không đạt, rồi gọi **lifecycle phase** thích hợp.

Với default lifecycle của Maven 3:

```text
validate
   |
initialize
   |
compile -> test-compile -> test             (unit tests)
   |
package                                  (tạo JAR)
   |
pre-integration-test -> integration-test (integration tests)
   |
post-integration-test                    (dọn môi trường)
   |
verify                                   (kiểm tra kết quả/gates)
   |
install                                  (ghi local Maven repository)
   |
deploy                                   (đẩy lên remote Maven repository)
```

Sơ đồ lược bỏ một số phase trung gian để làm rõ các mốc chính. Nếu goal được bind ở `validate`, `test` hoặc `verify` **trả lỗi và Maven không bị cấu hình bỏ qua lỗi**, thì invocation `mvn install` / `mvn deploy` sẽ không đi đến bước xuất bản artifact tương ứng của module đó.

**Đừng nhầm** `mvn deploy` (yêu cầu **lifecycle phase** `deploy`) với `mvn deploy:deploy` (gọi **một plugin goal trực tiếp**). Một plugin goal trực tiếp **không tự bảo đảm** chạy tất cả gates trong những phases trước; quy trình xuất bản phải dùng đúng entrypoint và kiểm soát quyền publication.

Bài này hướng dẫn thiết kế cổng chất lượng theo nhiều tầng, thực hành **Java 17 + Maven 3.9** với Enforcer, Surefire, Failsafe, JaCoCo và Checkstyle, cố ý tạo lỗi ở từng gate để quan sát vì sao install/deploy bị chặn, sau đó áp dụng vào reactor đa mô-đun và CI/CD.

## 1. Quality gate là gì, khác báo cáo như thế nào?

**Quality check** là phép đo/kiểm tra; **quality gate** là chính sách ra quyết định **PASS/FAIL** dựa trên kết quả đó. Ví dụ:

| Tầng | Công cụ/goal | Kiểm tra điều gì? | Vị trí thường dùng |
| --- | --- | --- | --- |
| Toolchain và build policy | Enforcer `enforcer:enforce` | Phiên bản Maven/JDK, các ràng buộc artifact/config | `validate` |
| Biên dịch mã | Compiler `compiler:compile`, `testCompile` | Java source/test source biên dịch hợp lệ | `compile`, `test-compile` |
| Unit tests | Surefire `surefire:test` | Test methods/assertions của đơn vị mã | `test` |
| Kiểm thử tích hợp | Failsafe `failsafe:integration-test` | Integration test scenarios | `integration-test` |
| Ra quyết định kết quả IT | Failsafe `failsafe:verify` | Summary của integration tests | `verify` |
| Coverage | JaCoCo `jacoco:report` + **`jacoco:check`** | Đo và áp threshold coverage | `verify` |
| Style | Checkstyle **`checkstyle:check`** | Vi phạm quy tắc style mà project chọn | `verify` |
| Phân tích tĩnh nâng cao | PMD/SpotBugs goals phù hợp | Quy tắc static analysis | `verify` hoặc phase phù hợp |
| Cổng bên ngoài | SonarQube/CI approval/scan | Quality profile, bảo mật, policy phát hành | Maven goal kết hợp CI gate |

Phân biệt những goal dễ bị nhầm:

- `jacoco:prepare-agent` chỉ chuẩn bị Java agent để đo coverage; **không quyết định PASS/FAIL coverage**.
- `jacoco:report` sinh báo cáo; **không tự đặt minimum**.
- `jacoco:check` mới đánh giá rules; mặc định `haltOnFailure=true` trong cấu hình JaCoCo.
- `checkstyle:checkstyle` chủ yếu sinh report; `checkstyle:check` là goal đánh giá violations và có thể làm build fail.
- `failsafe:integration-test` chạy tests và ghi summary; `failsafe:verify` mới xử lý thông tin test failure theo thiết kế deferred failure.
- Một dashboard hiển thị “coverage 42%” **không phải gate** nếu không có rule/fail behavior.
- Một CI job chỉ upload report XML mà trả exit code 0 dù test fail cũng **không phải quality gate đáng tin**.

Vì thế, với mỗi kiểm tra, phải có đủ ba yếu tố **được thực thi**, **có tiêu chí đánh giá**, **được phép chặn luồng xuất bản**.

## 2. Maven lifecycle đảm bảo thứ tự ra sao?

Maven có ba lifecycles chính: `clean`, `default`, `site`. `install` và `deploy` là phases của **default lifecycle**, nằm **sau** `verify`.

Với dự án Java JAR thông thường:

```bash
mvn -B -ntp clean verify
```

chạy `clean` rồi default lifecycle đến `verify`. Không tự install hoặc deploy.

```bash
mvn -B -ntp clean install
```

chạy đến `install`, nghĩa là nó **bao gồm `verify` trước đó**.

```bash
mvn -B -ntp clean deploy
```

chạy đến `deploy`, nghĩa là theo luồng mặc định nó bao gồm `verify` và `install` trước khi đến bước deploy.

**Một invocation gọi lifecycle phase muộn đã bao gồm các phases trước**; bạn không cần chạy `mvn verify` rồi `mvn install` chỉ để Maven “nhớ” đã verify trong một build đơn giản. Tuy nhiên trong CI, việc tách job kiểm thử và job xuất bản có thể cần thiết để bảo đảm tất cả module/approval đều đạt và credentials phát hành chỉ có trong job được phép.

### 2.1. Một caveat quan trọng về clean

`mvn clean verify` gồm **hai lifecycles**: mục tiêu `clean` của clean lifecycle và phase `verify` của default lifecycle. `clean` không phải phase nằm giữa `validate` và `compile`.

Chạy `mvn verify` không tự xóa `target` cũ; nếu muốn chống test reports/coverage data cũ ảnh hưởng việc đánh giá, dùng môi trường sạch hoặc `mvn clean verify` theo chính sách. Cẩn trọng không xóa file theo đường dẫn ngoài workspace khi tạo clean scripts riêng.

### 2.2. Các plugin goals không tự chạy vì bạn khai báo version

Khai báo:

```xml
<plugin>
    <groupId>org.jacoco</groupId>
    <artifactId>jacoco-maven-plugin</artifactId>
    <version>0.8.14</version>
</plugin>
```

chỉ xác định plugin artifact/version. Để JaCoCo tham gia lifecycle và **chặn build theo threshold**, cần bind những goals tương ứng qua `<executions>`.

Tương tự, chỉ đưa Checkstyle/SpotBugs vào `<reporting>` không tự bảo đảm `mvn install` sẽ fail khi style/bug checks không đạt. Muốn gate trong **default lifecycle**, cấu hình executions thuộc `<build><plugins>` hoặc cơ chế CI có contract tương đương.

### 2.3. Vì sao không kết thúc ở phase integration-test?

Với Maven 3, `mvn integration-test` dừng **trước `post-integration-test` và `verify`**. Integration environment có thể chưa được dọn, còn Failsafe chưa đánh giá summary cuối cùng. Dùng `mvn verify` như endpoint thông thường của kiểm thử tích hợp, đặc biệt khi có setup/teardown database, container hoặc HTTP service. Đây là một điểm khác biệt cần kiểm tra khi chuyển sang Maven 4 vì lifecycle behavior có cập nhật.

## 3. Đặt gate sớm hay muộn?

Không phải rule nào cũng nên chạy ở phase `validate`. Một cách chọn:

| Phase | Gate thích hợp | Tại sao? |
| --- | --- | --- |
| `validate` | Enforcer: Maven/JDK, policy đơn giản | Không cần compile; fail sớm, rẻ |
| `test` | Surefire unit tests | Test classes đã biên dịch |
| `integration-test` | Failsafe chạy IT | Artifact đã package, môi trường IT được chuẩn bị |
| `post-integration-test` | Teardown | Có cơ hội dọn môi trường dù assertion fail |
| `verify` | Failsafe verify, coverage check, style/static analysis gate | Dữ liệu test và artifact đã sẵn sàng |
| `install` | Không đặt gate muộn hơn trước khi có artifact local | Artifact có thể đã được ghi vào local repository |
| `deploy` | Tránh để gate *chỉ* ở đây nếu có thể chặn sớm | Remote artifact có thể đã được công bố ở module trước |

Gắn check vào `verify` làm nó chạy trước `install` và `deploy` khi dùng **lifecycle phases**. Nhưng `mvn test` hoặc `mvn package` **chưa tới `verify`**, vì vậy không thể lấy một build `BUILD SUCCESS` ở phase test/package làm bằng chứng rằng toàn bộ release gate đã pass.

## 4. Lab Java 17: các cổng Enforcer, tests, coverage và Checkstyle

Lab xây một service Java nhỏ:
- `GreetingService` tạo lời chào và đọc tên từ UTF-8 file.
- `App` có Java `main()` in kết quả xác định.
- `GreetingServiceTest` có ba unit tests, chọn bởi Surefire ở `test`.
- `GreetingServiceIT` có một integration test dùng filesystem và `@TempDir`, chọn bởi Failsafe ở `integration-test`.
- **Enforcer** chặn JDK/Maven không phù hợp tại `validate`.
- **JaCoCo** đo coverage trong test forks và chặn khi thấp hơn `60% instruction coverage` ở `verify`.
- **Checkstyle** chặn tab characters hoặc wildcard imports theo quy tắc đơn giản, cũng ở `verify`.

**Phiên bản minh họa đã được công bố**: Maven 3.9+, JDK 17+, Maven Enforcer Plugin 3.6.2, Maven Compiler Plugin 3.14.1, Maven Surefire/Failsafe 3.6.1, JaCoCo 0.8.14, Maven Checkstyle Plugin 3.6.0, JUnit Jupiter 5.11.4. Không tuyên bố các version này mới nhất tại mọi thời điểm; project production phải xem release notes và Java/Maven compatibility.

### 4.1. Điều kiện và thư mục

Cần:
- `java`/`javac` của JDK 17+; Maven **3.9.x** theo rule Enforcer trong lab.
- Network/Maven mirror để tải plugins và JUnit nếu local Maven repository chưa có.
- Quyền ghi trong project `target` và local Maven repository.
- Không cần Docker, database, cloud credentials hay remote Maven repository để chạy bài.
- **Không chạy `mvn deploy` trong lab** nếu chưa có authorized release target và `distributionManagement`; mục đích là học cách chặn bước publish.

Cây file:

```text
quality-gates-lab/
├── pom.xml
├── checkstyle.xml
└── src/
    ├── main/java/dev/training/quality/
    │   ├── GreetingService.java
    │   └── App.java
    └── test/java/dev/training/quality/
        ├── GreetingServiceTest.java
        └── GreetingServiceIT.java
```

Linux/macOS:

```bash
mkdir -p quality-gates-lab/src/main/java/dev/training/quality
mkdir -p quality-gates-lab/src/test/java/dev/training/quality
cd quality-gates-lab
```

Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force -Path "quality-gates-lab/src/main/java/dev/training/quality" | Out-Null
New-Item -ItemType Directory -Force -Path "quality-gates-lab/src/test/java/dev/training/quality" | Out-Null
Set-Location quality-gates-lab
```

Các lệnh tiếp theo giả định bạn đang đứng ở root `quality-gates-lab`. Ghi **toàn bộ nội dung từng file** dưới đây vào đúng đường dẫn trước khi build.

## 5. POM hoàn chỉnh với các quality gates

Tệp **`pom.xml`**:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.training.quality</groupId>
    <artifactId>quality-gates-lab</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
        <junit.version>5.11.4</junit.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>${junit.version}</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <!-- Gate 1: toolchain policy at validate -->
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-enforcer-plugin</artifactId>
                <version>3.6.2</version>
                <executions>
                    <execution>
                        <id>require-supported-toolchain</id>
                        <phase>validate</phase>
                        <goals>
                            <goal>enforce</goal>
                        </goals>
                        <configuration>
                            <rules>
                                <requireMavenVersion>
                                    <version>[3.9.0,4.0.0)</version>
                                </requireMavenVersion>
                                <requireJavaVersion>
                                    <version>[17,)</version>
                                </requireJavaVersion>
                            </rules>
                            <fail>true</fail>
                        </configuration>
                    </execution>
                </executions>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
            </plugin>

            <!-- Surefire uses the jar lifecycle binding at test -->
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.6.1</version>
                <configuration>
                    <failIfNoTests>true</failIfNoTests>
                </configuration>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
            </plugin>

            <!-- Gate 2: run IT and evaluate the result at verify -->
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-failsafe-plugin</artifactId>
                <version>3.6.1</version>
                <configuration>
                    <failIfNoTests>true</failIfNoTests>
                </configuration>
                <executions>
                    <execution>
                        <id>run-and-verify-integration-tests</id>
                        <goals>
                            <goal>integration-test</goal>
                            <goal>verify</goal>
                        </goals>
                    </execution>
                </executions>
            </plugin>

            <!-- Gate 3: collect coverage, then verify threshold -->
            <plugin>
                <groupId>org.jacoco</groupId>
                <artifactId>jacoco-maven-plugin</artifactId>
                <version>0.8.14</version>
                <executions>
                    <execution>
                        <id>attach-agent</id>
                        <goals>
                            <goal>prepare-agent</goal>
                        </goals>
                    </execution>
                    <execution>
                        <id>enforce-coverage</id>
                        <phase>verify</phase>
                        <goals>
                            <goal>report</goal>
                            <goal>check</goal>
                        </goals>
                        <configuration>
                            <rules>
                                <rule>
                                    <element>BUNDLE</element>
                                    <limits>
                                        <limit>
                                            <counter>INSTRUCTION</counter>
                                            <value>COVEREDRATIO</value>
                                            <minimum>0.60</minimum>
                                        </limit>
                                    </limits>
                                </rule>
                            </rules>
                            <haltOnFailure>true</haltOnFailure>
                        </configuration>
                    </execution>
                </executions>
            </plugin>

            <!-- Gate 4: style validation at verify -->
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-checkstyle-plugin</artifactId>
                <version>3.6.0</version>
                <configuration>
                    <configLocation>checkstyle.xml</configLocation>
                    <includeTestSourceDirectory>true</includeTestSourceDirectory>
                    <consoleOutput>true</consoleOutput>
                    <failOnViolation>true</failOnViolation>
                </configuration>
                <executions>
                    <execution>
                        <id>enforce-style</id>
                        <phase>verify</phase>
                        <goals>
                            <goal>check</goal>
                        </goals>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
```

**Cách đọc cấu hình này:**

1. Enforcer `enforce` ở `validate`: Maven process phải dùng **Maven 3.9.x** (range `[3.9.0,4.0.0)`) và **JDK 17+**. Maven 4 bị loại **có chủ đích** vì bài đang kiểm chứng lifecycle Maven 3.
2. Compiler ghim version để biên dịch đúng Java 17.
3. Surefire ở `test` thông qua default binding của packaging `jar`; `failIfNoTests=true` vì lab **biết chắc** có unit tests.
4. Failsafe có **cả hai goals**; goal `integration-test` và `verify` có default phases phù hợp. `failIfNoTests=true` vì lab **biết chắc** có IT.
5. JaCoCo `prepare-agent` mặc định chạy ở `initialize` và đặt thuộc tính `argLine` cho JVM test runner; `report` và `check` chạy ở `verify`, với threshold `60%` cho **instruction coverage** toàn bundle.
6. Checkstyle `check` được bind ở `verify`, dùng file rules `checkstyle.xml` của project; `failOnViolation=true` để biến vi phạm thành lỗi build.
7. Không có goal `install`/`deploy` tùy biến. Khi gọi lifecycle phase `install` hay `deploy`, Maven đi qua gates trước.

**Các rule này là ví dụ học tập, không phải quality policy bắt buộc cho mọi dự án.** Với dự án production, chọn threshold theo baseline/kiến trúc, mở rộng kiểm tra bảo mật và đánh giá tính phù hợp của từng Maven plugin/JDK version.

### 5.1. JaCoCo agent và argLine

Khi plugin JaCoCo chạy `prepare-agent`, nó thường thiết lập property `argLine` cho Surefire/Failsafe. Lab **không tự override `<argLine>`** ở test plugins, vì override bằng giá trị không chứa JaCoCo agent có thể khiến coverage file không xuất hiện.

Nếu dự án cần thêm JVM arguments, tài liệu JaCoCo khuyến nghị đánh giá property muộn:

```xml
<configuration>
    <argLine>@{argLine} -Dfile.encoding=UTF-8</argLine>
</configuration>
```

Đây là **snippet tùy chọn** đặt trong Surefire/Failsafe khi cần, **không phải thay đổi bắt buộc cho lab**. Với late property evaluation, nên chuẩn bị property trống khi JaCoCo có thể bị bỏ qua để tránh lỗi JVM diễn giải nguyên văn `@{argLine}`. Không thêm cùng một agent hai lần bằng cả cấu hình JaCoCo và JVM args thủ công.

### 5.2. Vì sao Checkstyle ở verify thay vì validate?

Checkstyle có thể được bind ở validate, nhưng nếu source chưa biên dịch hợp lệ, parser/style errors có thể gây nhiễu so với lỗi compiler. Trong lab, checkstyle chạy ở verify để người học phân biệt các loại gate sau compile/test. Trong CI thực, có thể đưa style sớm hơn để fail nhanh, miễn phù hợp plugin dependencies và chất lượng thông báo lỗi.

### 5.3. Vì sao failIfNoTests chỉ đặt ở lab?

Trong reactor có modules `pom` hoặc modules không chứa unit/IT tests hợp lệ. Nếu áp `failIfNoTests=true` vô điều kiện cho mọi module, một aggregator hoặc library không có test có thể fail không cần thiết. Đặt policies theo module/profile và yêu cầu kiểm thử thực tế, không sao chép cờ này vào parent mà không phân loại.

## 6. Checkstyle rules tối thiểu: checkstyle.xml

Tệp **`checkstyle.xml`** ở root project:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE module PUBLIC
    "-//Checkstyle//DTD Checkstyle Configuration 1.3//EN"
    "https://checkstyle.org/dtds/configuration_1_3.dtd">
<module name="Checker">
    <property name="charset" value="UTF-8"/>
    <module name="FileTabCharacter"/>
    <module name="TreeWalker">
        <module name="AvoidStarImport"/>
    </module>
</module>
```

Đây là một cấu hình **chạy được** cho các rules cơ bản:
- `FileTabCharacter` cấm tab trong Java source.
- `AvoidStarImport` cấm kiểu import wildcard như `import java.util.*;`.
- `includeTestSourceDirectory=true` trong plugin khiến rules áp dụng cả test sources, phù hợp kỳ vọng của lab.
- Nếu không có vi phạm, `checkstyle:check` không làm build fail.

**Hạn chế của demo:** hai quy tắc này **không tạo ra bộ style guide toàn diện**. Production có thể dùng rule set tùy chỉnh, Google/Sun checks hoặc profile kiểm tra riêng, nhưng phải kiểm thử các rules và thống nhất IDE/formatter để tránh developer bị chặn bởi yêu cầu không rõ ràng.

## 7. Java source và stdout của lab

### 7.1. GreetingService.java

Tệp **`src/main/java/dev/training/quality/GreetingService.java`**:

```java
package dev.training.quality;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public final class GreetingService {

    public String greet(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("name must not be blank");
        }
        return "Hello, " + name.strip() + "!";
    }

    public String greetFromFile(Path path) throws IOException {
        return greet(Files.readString(path, StandardCharsets.UTF_8));
    }
}
```

`GreetingService` có hai trách nhiệm nhỏ, giúp minh họa gate:
- `greet` xử lý logic thuần và kiểm soát invalid input.
- `greetFromFile` kết hợp filesystem với logic format, giúp kiểm thử tích hợp một behavior thật bằng Java I/O.

### 7.2. App.java

Tệp **`src/main/java/dev/training/quality/App.java`**:

```java
package dev.training.quality;

public final class App {

    private App() {
    }

    public static void main(String[] args) {
        GreetingService service = new GreetingService();
        System.out.println(service.greet("Maven"));
    }
}
```

Sau khi compile, gọi:

```bash
java -cp target/classes dev.training.quality.App
```

**Stdout Java chính xác:**

```text
Hello, Maven!
```

Đây là stdout của Java application. Output từ `mvn clean verify` có thêm logs plugins và reports, không đồng nhất với đúng một dòng trên.

### 7.3. GreetingServiceTest.java — unit tests

Tệp **`src/test/java/dev/training/quality/GreetingServiceTest.java`**:

```java
package dev.training.quality;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class GreetingServiceTest {

    private final GreetingService service = new GreetingService();

    @Test
    void normalizesName() {
        assertEquals("Hello, Maven!", service.greet("  Maven  "));
    }

    @Test
    void rejectsBlankInput() {
        assertThrows(IllegalArgumentException.class,
            () -> service.greet("   "));
    }

    @Test
    void rejectsNullInput() {
        assertThrows(IllegalArgumentException.class,
            () -> service.greet(null));
    }
}
```

Surefire mặc định chọn class tên `*Test`. Lab có **3 JUnit Jupiter unit tests** ở phase `test`. Kết quả pass kỳ vọng:
- Input có khoảng trắng → chuẩn hóa và trả lời chào.
- Input chỉ có khoảng trắng → ném exception.
- Input null → ném exception.

### 7.4. GreetingServiceIT.java — integration test

Tệp **`src/test/java/dev/training/quality/GreetingServiceIT.java`**:

```java
package dev.training.quality;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class GreetingServiceIT {

    @TempDir
    Path temporaryDirectory;

    @Test
    void readsTemporaryFileAndGreets() throws IOException {
        Path input = temporaryDirectory.resolve("name.txt");
        Files.writeString(input, "Maven", StandardCharsets.UTF_8);

        assertTrue(Files.isRegularFile(input));
        GreetingService service = new GreetingService();
        assertEquals("Hello, Maven!", service.greetFromFile(input));
    }
}
```

Failsafe mặc định nhận tên `*IT`, vì thế class này chạy ở `integration-test` khi goal đã được bind. `@TempDir` do JUnit Jupiter cung cấp, không yêu cầu Maven plugin chuẩn bị service bên ngoài. File system thật được sử dụng, nên đây là phép kiểm tra tích hợp tối giản giữa lớp ứng dụng và I/O.

Lab có **1 integration test**. Trong hệ thống thực, có thể thay bằng DB/HTTP/container scenarios và bind setup/teardown phù hợp ở `pre-integration-test`/`post-integration-test`. Với external resources, cần cleanup dự phòng ở cấp CI vì lỗi infrastructure/CI abort không được Failsafe bảo đảm xử lý như assertion failure bình thường.

## 8. Chạy baseline và kiểm tra các gates

Trong root lab:

```bash
mvn -version
mvn -B -ntp clean verify
```

Khi JDK/Maven và dependencies hợp lệ, luồng dự kiến:

1. Maven Clean xóa `target` cũ.
2. Enforcer kiểm tra `requireMavenVersion` và `requireJavaVersion` ở `validate`.
3. JaCoCo `prepare-agent` tại `initialize` chuẩn bị agent property cho forked test JVM.
4. Compiler biên dịch `GreetingService`/`App` và các test sources.
5. Surefire chạy **3 unit tests**, không thực thi `GreetingServiceIT` vì tên class thuộc mẫu Failsafe.
6. JAR Plugin tạo `target/quality-gates-lab-1.0.0.jar` ở `package`.
7. Failsafe chạy **1 integration test**, ghi `target/failsafe-reports` và summary.
8. Failsafe verify đánh giá kết quả integration test.
9. JaCoCo tạo coverage report và check threshold **INSTRUCTION COVEREDRATIO >= 0.60**.
10. Checkstyle kiểm tra tab/wildcard imports, báo violation nếu có.
11. Nếu mọi goal thành công, Maven kết thúc `BUILD SUCCESS` ở phase verify, **chưa install/deploy**.

**Test counts dự kiến:**

```text
Surefire:  Tests run: 3, Failures: 0, Errors: 0, Skipped: 0
Failsafe:  Tests run: 1, Failures: 0, Errors: 0, Skipped: 0
```

Đây là **tóm tắt thống kê mong đợi**, không phải nguyên văn Maven stdout. Maven logs có `[INFO]`, thời gian, số lượng files và version details khác nhau.

**Bằng chứng gates:**
- `target/surefire-reports/` cho 3 unit tests.
- `target/failsafe-reports/` và `failsafe-summary.xml` cho integration test.
- `target/jacoco.exec` và `target/site/jacoco/index.html` cho dữ liệu/báo cáo coverage.
- `target/checkstyle-result.xml` theo Checkstyle plugin output configuration mặc định.
- Các goal `enforcer:enforce`, `failsafe:verify`, `jacoco:check`, `checkstyle:check` trong Maven logs.
- Exit code của `mvn clean verify` là **0** khi thành công, **khác 0** khi một gate fail.

### 8.1. Không cố định % coverage của một build không thực thi

Lab cố ý kiểm tra ngưỡng **60%**, không tuyên bố một tỉ lệ JaCoCo chính xác đến chữ số thập phân khi chưa chạy trên máy. JaCoCo đo executed bytecode instructions, không đơn giản là “số test pass chia tổng số tests”. Ví dụ `App.main` chưa được unit test gọi, nên coverage 100% của mọi class không phải kỳ vọng hợp lệ.

**Nếu JaCoCo không sinh được `jacoco.exec`**, `jacoco:report` có thể bỏ qua vì thiếu execution data. Không xem một HTML report không tồn tại là PASS coverage; kiểm tra JaCoCo goal logs và policy đối với missing data. Khi thực hiện release gate, nên dùng clean workspace và kiểm tra reports/coverage artifacts thật.

### 8.2. Kiểm tra compile và stdout mà không cần remote repository

Sau `mvn clean verify` thành công:

```bash
java -cp target/classes dev.training.quality.App
```

Kết quả:

```text
Hello, Maven!
```

Dự án chỉ phụ thuộc JDK ở runtime, JUnit ở `test` scope; không cần đặt test JAR/JUnit vào Java main classpath. Dùng `java -cp` vì JAR lab chưa cấu hình `Main-Class` manifest; `java -jar target/quality-gates-lab-1.0.0.jar` không mặc định chạy được.

## 9. Chứng minh quality gates chặn install

Điểm học tập lớn nhất: một gate chỉ có ý nghĩa khi fail trước khi Maven đi đến `install`/`deploy`. Hãy thử **một lỗi tại một thời điểm trên bản lab có thể khôi phục**, rồi chạy `mvn clean install` để quan sát.

### 9.1. Tạo lỗi unit test

Trong `GreetingServiceTest.java`, thay dòng:

```java
assertEquals("Hello, Maven!", service.greet("  Maven  "));
```

bằng:

```java
assertEquals("Hello, Java!", service.greet("  Maven  "));
```

Đây chỉ là **dòng thay thế trong method**, không phải Java file độc lập. Khi chạy:

```bash
mvn -B -ntp clean install
```

Surefire sẽ phát hiện expected/actual không khớp ở phase `test`. Maven dừng trước `package`/`verify`/`install`, nên artifact của lượt build này **không được install bởi invocation đó**.

**Lưu ý:** local repository có thể vẫn còn JAR version `1.0.0` từ lần `install` cũ; việc còn nhìn thấy file đó **không chứng minh lần build vừa fail đã install thành công**. Dùng Maven logs/exit code/timestamps trong môi trường thử nghiệm tách biệt để xác định sự kiện của đúng lượt build.

Khôi phục assertion gốc sau thử nghiệm.

### 9.2. Tạo lỗi integration test

Trong `GreetingServiceIT.java`, đổi expected value:

```java
assertEquals("Hello, Java!", service.greetFromFile(input));
```

Chạy:

```bash
mvn -B -ntp clean install
```

Unit tests vẫn pass; Failsafe chạy `*IT` và ghi **1 assertion failure**. Trong luồng bình thường, Failsafe không fail build ngay ở `integration-test` mà để Maven có cơ hội chạy `post-integration-test`; sau đó `failsafe:verify` đánh dấu build failure. Vì `verify` chưa thành công, phase `install` **không được đến** trong invocation đó.

Không được diễn đạt quá mức rằng post-integration-test sẽ **luôn** chạy nếu test fork process crash, Maven bị kill hoặc setup/plugin resolution lỗi. Deferred failure là behavior cho test results thông thường, không phải try/finally cho mọi loại sự cố.

Khôi phục assertion gốc.

### 9.3. Tạo lỗi coverage

Đổi threshold trong `pom.xml`:

```xml
<minimum>1.00</minimum>
```

Phần này thay **một element** trong JaCoCo `rules`; đây không phải cấu hình plugin đầy đủ. Vì lab không gọi `App.main` trong tests, 100% instruction coverage của **mọi production class** không phải kỳ vọng, nên JaCoCo `check` sẽ có lý do báo rule chưa đạt ở `verify`.

Chạy:

```bash
mvn -B -ntp clean install
```

Expected effect: unit + IT pass, JaCoCo report được tạo nếu test forks thu thập dữ liệu, nhưng `jacoco:check` làm build fail vì ngưỡng quá cao. Phase `install` không được chạy cho module đó.

Khôi phục `<minimum>0.60</minimum>` và chạy lại baseline.

### 9.4. Tạo lỗi Checkstyle

Thêm một dòng import wildcard vào `GreetingService.java`:

```java
import java.util.*;
```

Đây là một import duy nhất đặt cùng các imports khác trong file, **không phải Java file độc lập**. Java compiler thường không coi unused wildcard import này là lỗi, nhưng Checkstyle rule `AvoidStarImport` sẽ phát hiện nó. Với `failOnViolation=true` và execution ở `verify`, build sẽ fail trước `install`.

Chạy:

```bash
mvn -B -ntp clean install
```

Xóa import minh họa và build lại. Không cần cố tạo lỗi bằng một code file không compile được: như vậy gate compiler sẽ chặn trước khi Checkstyle có dịp kiểm tra.

### 9.5. Tạo lỗi toolchain policy

Nếu Maven process chạy bằng Maven version ngoài range `[3.9.0,4.0.0)` hoặc JDK dưới 17, Enforcer sẽ từ chối ở `validate` khi plugin có thể được tải/chạy. Không cố hạ JDK của máy làm việc chỉ để minh họa; xem rule và logs. Nếu toolchain quá cũ để nạp plugin, **lỗi plugin compatibility** có thể xảy ra trước khi Enforcer rule chạy — cũng là một failure, nhưng nguyên nhân khác.

### 9.6. Bảng tổng hợp experiments

| Thí nghiệm | Gate dự kiến | Phase fail | Hệ quả khi gọi `mvn clean install` |
| --- | --- | --- | --- |
| Unit test assert sai | Surefire | `test` | Không tới install |
| Integration test assert sai | Failsafe verify | `verify` | Không tới install |
| Coverage tối thiểu 100% | JaCoCo check | `verify` | Không tới install |
| Wildcard import | Checkstyle check | `verify` | Không tới install |
| Maven/JDK version ngoài policy | Enforcer | `validate` | Không tới install |
| Baseline tất cả pass | Không gate nào fail | Kết thúc `install` | Cài vào local repo |

**Nhớ rằng `mvn install` cài artifact vào local Maven repository, chưa đưa lên remote.** Trong bài thực hành, không cần và không nên thử `mvn deploy` lên bất kỳ repository thật nào chỉ để quan sát gate.

## 10. Một quy tắc quan trọng: lệnh gọi phase và goal khác nhau

Các lệnh sau **không tương đương**:

| Lệnh | Cơ chế | Có đi qua phases/gates trước không? |
| --- | --- | --- |
| `mvn clean verify` | Clean + default lifecycle đến verify | **Có**, qua validate/test/package/verify |
| `mvn clean install` | Clean + default lifecycle đến install | **Có**, bao gồm verify trước install |
| `mvn clean deploy` | Clean + default lifecycle đến deploy | **Có**, bao gồm verify và install |
| `mvn install:install` | Gọi **install plugin goal trực tiếp** | **Không tự bảo đảm** chạy phases trước |
| `mvn deploy:deploy` | Gọi **deploy plugin goal trực tiếp** | **Không tự bảo đảm** chạy phases trước |
| `mvn test` | Default lifecycle đến test | **Chưa** chạy verify gates |
| `mvn package` | Default lifecycle đến package | **Chưa** chạy verify gates |
| `mvn integration-test` (Maven 3) | Default lifecycle đến integration-test | **Chưa** tới post-IT/verify |

Điều này quan trọng khi review shell scripts hoặc CI pipeline: một pipeline có dòng `mvn deploy:deploy` không thể được coi là đã trải qua quality gates chỉ nhờ tên goal có từ “deploy”.

**Policy đề xuất:** CI release job dùng approved Maven lifecycle entrypoints và tách quyền deploy từ quyền chỉ build/test. Nếu dùng custom plugin goal hoặc script upload artifacts, quality gate ở cấp pipeline cần được kiểm tra rõ trước action upload, không chỉ dựa vào POM.

## 11. Vì sao cần Failsafe verify, không chỉ integration-test?

Một dự án có server/database container:
- `pre-integration-test`: start service/container.
- `integration-test`: Failsafe chạy tests.
- `post-integration-test`: stop service/container, dọn resource.
- `verify`: Failsafe đọc summary XML và báo build failure nếu IT test result không đạt.

Cấu hình Failsafe trong lab:

```xml
<executions>
    <execution>
        <id>run-and-verify-integration-tests</id>
        <goals>
            <goal>integration-test</goal>
            <goal>verify</goal>
        </goals>
    </execution>
</executions>
```

Hai goals có default phases phù hợp. **Không được chỉ bind `integration-test` rồi kỳ vọng mọi assertion failure tự làm `mvn install` fail** nếu thiếu verify goal, vì Failsafe thiết kế để trì hoãn build failure.

Với ngoại lệ hạ tầng:
- Setup goal có thể fail trước test.
- JVM fork có thể crash.
- CI timeout/cancel có thể dừng process.
- Post-IT teardown có thể fail.
- Verify có thể chưa nhận summary hợp lệ.

Vì vậy, khi có external resources như Docker/test DB, tạo **cleanup dự phòng ở cấp CI** với điều kiện chạy ngay cả khi job fail/cancel theo khả năng nền tảng, đồng thời dùng môi trường cách ly và TTL cho tài nguyên cloud.

## 12. Test coverage: số đo khác chính sách

Một số counter JaCoCo:
- `INSTRUCTION`: số bytecode instructions đã/không chạy.
- `LINE`: line coverage khi có debug line information.
- `BRANCH`: nhánh điều kiện.
- `METHOD`, `CLASS`, `COMPLEXITY`: những góc nhìn khác theo JaCoCo.

Một số value:
- `COVEREDRATIO`: tỉ lệ phần được cover.
- `MISSEDRATIO`: tỉ lệ bỏ sót.
- `MISSEDCOUNT`/`COVEREDCOUNT`: số phần tử.

Rule lab:

```xml
<rules>
    <rule>
        <element>BUNDLE</element>
        <limits>
            <limit>
                <counter>INSTRUCTION</counter>
                <value>COVEREDRATIO</value>
                <minimum>0.60</minimum>
            </limit>
        </limits>
    </rule>
</rules>
```

Đây là **đoạn trong JaCoCo check configuration**, không phải POM hoàn chỉnh. `element=BUNDLE` áp rule cho tổng bundle của module. Không áp 60% tự động cho từng class: muốn kiểm tra từng class, dùng `element=CLASS` và các excludes/rules phù hợp.

### 12.1. Vì sao report không đủ?

`jacoco:report` có thể sinh HTML/XML khi có dữ liệu, nhưng nếu không có `jacoco:check` gắn với threshold và halt-on-failure, Maven build có thể thành công dù coverage rất thấp. Do đó:
- **Report** phục vụ quan sát.
- **Check** phục vụ quality gate.
- **CI** quyết định có cho publish khi check thành công không.

### 12.2. Missing execution data

JaCoCo `prepare-agent` không phải phép màu nếu test runner:
- Không fork JVM phù hợp.
- Bị override `argLine` và mất Java agent.
- Tests bị skip.
- JVM bị kill trước khi ghi `jacoco.exec`.
- Test sources hoặc production classes không được chạy như kỳ vọng.

Khi không có execution data, một số report/check goals có thể bỏ qua hoặc báo không có file. **Không dùng “BUILD SUCCESS” kèm “Skipping JaCoCo execution due to missing execution data file” làm bằng chứng coverage policy đã được thực thi.** Nếu coverage là release requirement, CI phải xác minh report/exec data hợp lệ và chính sách xử lý missing data — ngoài rule check.

### 12.3. Coverage của unit tests và integration tests

Trong lab, JaCoCo agent dùng chung property `argLine`; cả Surefire và Failsafe có thể ghi vào data file phù hợp. Trong project thật, nếu chạy forked JVM/service containers độc lập, JaCoCo agent của test fork **không tự đo** mọi JVM của server/client ngoài process. Có thể cần `prepare-agent-integration`, separate data files, `merge`, `report-integration` hoặc agent cho service JVM theo thiết kế.

Đừng kết luận “integration test chạy” đồng nghĩa “coverage của service container đã được đo”. Kiểm tra JaCoCo reports thực tế và class loader/process boundaries.

## 13. Static analysis gate và công cụ ngoài Maven

### 13.1. Checkstyle

Goal `checkstyle:check` có thể fail build khi vi phạm. Khi cấu hình trong `<build><plugins>` ở `verify`, nó có thể chặn install/deploy. **Chỉ cấu hình `checkstyle:checkstyle` để tạo HTML report không tự mang cùng contract fail.**

### 13.2. PMD và SpotBugs

Các công cụ static analysis có goals dùng để **generate report** và goals dùng để **check/fail**. Ví dụ tiêu biểu:
- Maven PMD Plugin: `pmd:check` sau khi `pmd:pmd` phân tích (plugin có thể gọi phân tích theo semantics của goal).
- SpotBugs Maven Plugin: `spotbugs:check` để đánh giá kết quả analysis, cần cấu hình xử lý findings theo tool docs/version.

Đây là **hướng mở rộng**, không phải dependencies trong lab runnable. Trước khi bind, xác minh:
- Goal yêu cầu compiled classes hay sources?
- Bản plugin tương thích Maven/JDK hiện tại?
- Ngưỡng severity và baseline exclusion?
- Có bỏ qua build khi report thiếu?
- Có false positives trong generated sources/tests?

### 13.3. SonarQube hoặc external quality gate

Một Maven goal gửi analysis tới SonarQube **không tự bảo đảm** external server đã đánh giá xong và trả **quality gate FAILED** trước khi bước deploy bắt đầu. Nếu cần dùng external gate để chặn publish, CI phải **chờ và kiểm tra trạng thái từ hệ thống phân tích**, sử dụng integration/parameters của đúng tool, và fail pipeline khi không đạt.

Không coi “analysis upload thành công” là “quality gate PASS”. Điều tương tự áp dụng cho security scanners có asynchronous jobs, approval workflows và kiểm tra license.

## 14. Các tùy chọn skip/ignore có thể làm quality gate mất tác dụng

Những flags sau là **công cụ điều khiển build**, không phải bằng chứng quality được thỏa:

| Flag/option | Tác động thường gặp | Rủi ro |
| --- | --- | --- |
| `-DskipTests` | Surefire 3.6.1 bỏ chạy unit tests | Build success dù không có unit test result |
| `-DskipITs` | Failsafe 3.6.1 bỏ chạy integration tests | Build success dù IT chưa chạy |
| `-Dmaven.test.skip=true` | Compiler/Surefire/Failsafe có thể bỏ test compilation/execution | Có thể làm mất gần như toàn bộ test gate |
| `-Denforcer.skip` | Bỏ Enforcer rules | Toolchain/policy không còn được chặn |
| `-Dcheckstyle.skip` | Bỏ Checkstyle analysis/check | Style gate không còn hiệu lực |
| `-Djacoco.skip` | Bỏ JaCoCo agent/report/check | Coverage không được đo/kiểm |
| `-Djacoco.haltOnFailure=false` | Cho JaCoCo báo warning thay vì fail | Coverage threshold không chặn build |
| `-Dmaven.test.failure.ignore=true` | Cho phép bỏ qua failure của test runner theo cấu hình | Unit tests fail nhưng build có thể tiếp tục |
| `<testFailureIgnore>true</testFailureIgnore>` | Bỏ fail do kết quả tests ở plugin tương ứng | Release gate có thể xanh giả |
| `-fn` | Maven fail-never behavior | Exit status có thể che module failures |

**Một nuance của Failsafe 3.6.x:** `-DskipTests` **không tự động tương đương `-DskipITs`**. Trong phiên bản 3.6.1, Failsafe không còn bind user property `skipTests` như các hướng dẫn cũ thường mô tả; muốn skip integration tests, dùng `-DskipITs` khi thực sự được phép.

**Không dùng bất kỳ skip flag nào trong release job mà vẫn báo “quality gate đầy đủ đã qua”.** Nếu skip được chấp thuận (chẳng hạn build docs module), phải thể hiện rõ profile/policy nào miễn kiểm tra và lý do.

### 14.1. Gate skip như một property trong POM

Các goals có thể hỗ trợ `<skip>`, `<fail>`, `<failOnViolation>`, `<haltOnFailure>`. Khi đưa chúng vào một property hoặc Maven profile, tính an toàn phụ thuộc vào:
- Profile được activate ở CI hay không?
- Người gọi có thể override từ command line không?
- Quality policy có cho phép exception không?
- Có job chạy full gates trên commit/artifact định phát hành không?
- Release credentials có bị cấp cho job bỏ qua gates không?

Vì vậy POM gate chỉ là một lớp phòng thủ. **CI branch protection, review và publish authorization** vẫn cần thiết nếu muốn chặn mọi đường phát hành bị bypass.

### 14.2. Tests = 0 không đồng nghĩa pass

Khi Surefire/Failsafe không thấy tests, mặc định behavior có thể cho phép build thành công tùy goal/configuration. Lab dùng `failIfNoTests=true` ở các modules có tests bắt buộc, nhưng với parent aggregator hoặc module không có IT, phải điều chỉnh theo module.

Nhìn **test counts và XML reports**, không chỉ dòng `BUILD SUCCESS`.

## 15. Install: kiểm tra xong mới ghi local repository

`mvn install` xây artifact và đưa vào **local Maven repository** sau khi các phases trước đã hoàn thành cho project tương ứng:

```bash
mvn -B -ntp clean install
```

Trong lab, nếu tất cả gates pass, local repository thường có:

```text
~/.m2/repository/dev/training/quality/quality-gates-lab/1.0.0/
    quality-gates-lab-1.0.0.pom
    quality-gates-lab-1.0.0.jar
```

Nếu một gate fail, invocation **không đi đến install phase của module đó**. Tuy nhiên:
- Nếu bản `1.0.0` đã có sẵn từ trước, file trong local repo **không tự biến mất**.
- Nếu dùng reactor nhiều module, những module đã hoàn tất `install` trước khi một module khác fail **có thể đã nằm trong local repository**.
- Một plugin custom gắn với phase sớm vẫn có thể ghi file ở nơi khác; quality gate của Maven không phải sandbox của mọi side effect.
- Maven local repository có thể khác `~/.m2/repository` khi dùng settings hoặc `-Dmaven.repo.local`.

Để thử trong môi trường biệt lập có thể dùng local repository tạm, ví dụ:

```bash
mvn -B -ntp "-Dmaven.repo.local=target/isolated-repo" clean install
```

**Cẩn trọng:** dòng lệnh ví dụ trên dùng local repository **dưới `target`**, trong khi `clean` có thể xóa `target` ở đầu invocation. Maven thường chuẩn bị/cache artifacts lại sau clean, nhưng tốt hơn trong CI nghiêm túc hãy đặt isolated repository **ngoài thư mục output bị clean**, ví dụ thư mục riêng của job, để tránh side effects giữa clean/cache. Đừng xóa repository của người khác hoặc thư mục cache dùng chung để thử failure.

## 16. Deploy: Maven lifecycle và rủi ro phát hành một phần

`mvn deploy` chạy đến phase `deploy` của default lifecycle. Với một module đơn giản, gate fail ở `test` hoặc `verify` thường chặn deploy goal của module đó.

Nhưng một **reactor nhiều module không phải giao dịch nguyên tử toàn hệ thống**. Ví dụ:

```text
reactor: core -> service -> app
mvn deploy (sequential, illustrative)

core:    validate ... verify PASS -> install -> deploy SUCCESS
service: validate ... verify PASS -> install -> deploy SUCCESS
app:     validate ... verify FAIL -> no deploy of app
```

Khi `app` fail, artifact `core` và `service` **có thể đã được publish**. Không được tuyên bố “chỉ cần bind gates vào verify thì Maven bảo đảm cả reactor đều pass trước khi bất kỳ artifact nào được upload”.

### 16.1. Chiến lược CI nhiều giai đoạn an toàn hơn

Một flow phổ biến:

```text
Source commit
   |
   v
Build + tests + quality gates for WHOLE reactor
   |
   +---- FAIL --> stop, collect reports, no publishing credentials
   |
   v
Approval / external security / quality gate (if required)
   |
   +---- FAIL --> stop
   |
   v
Publish stage with controlled credentials and repository policy
   |
   v
Release verification and artifact promotion
```

Trong publish stage, **không tự động thêm `-DskipTests` và giả định đã được bảo vệ**. Nếu build/test và publish tách invocation, cần chứng minh chúng dùng **đúng commit, toolchain, dependencies và artifact content**, và bảo đảm stage sau không âm thầm tạo artifact khác từ source đã đổi. Với artifacts cần immutability/provenance, dùng staging repository, artifact attestation, checksum và promote mechanism theo hệ thống repository.

Maven `mvn deploy` tự chạy các phases trước cho invocation đó, nhưng **điều này không làm toàn bộ reactor publish atomic**. Để thật sự phát hành all-or-nothing, cần release/repository workflow có staging/promotion hoặc chính sách tương đương; Maven lifecycle đơn thuần không cấp bảo đảm đó.

### 16.2. DistributionManagement và credentials

Để deploy từ Maven, project thường có `<distributionManagement>` trỏ đến approved remote repository, còn credentials thuộc `settings.xml`/CI secret manager.

Ví dụ snippet **minh họa**, không phải repository thực để deploy:

```xml
<distributionManagement>
    <repository>
        <id>company-releases</id>
        <url>https://repo.example.invalid/releases</url>
    </repository>
    <snapshotRepository>
        <id>company-snapshots</id>
        <url>https://repo.example.invalid/snapshots</url>
    </snapshotRepository>
</distributionManagement>
```

Đây là **ví dụ XML giả định**; `example.invalid` không phải endpoint hoạt động. Trong sản phẩm thật, hãy dùng repository được tổ chức ủy quyền, bảo vệ credentials, phân quyền release và snapshot khác nhau, áp immutable release policy.

**Không đưa username/password/token thẳng vào `pom.xml` hoặc lệnh shell được ghi log**. Maven settings sử dụng `server id` phù hợp với `distributionManagement repository id`; CI nên cấp credentials ngắn hạn hoặc secret masking theo nền tảng.

## 17. Reactor nhiều module: gate theo module và gate toàn hệ thống

Trong Maven reactor:

```text
workspace/
├── pom.xml                    (packaging=pom)
├── library/                   (packaging=jar)
├── service/                   (packaging=jar)
└── integration-checks/        (packaging=jar hoặc pom theo thiết kế)
```

Có ít nhất ba câu hỏi phải làm rõ:
1. **Gate nào phải chạy trên mỗi module?** Ví dụ compiler tests và style checks.
2. **Gate nào chỉ chạy ở một module aggregator?** Ví dụ coverage report tổng thể hoặc cross-module integration tests.
3. **Bằng chứng toàn reactor pass được lưu ở đâu?** Reactor Summary, CI job exit code, reports/artifacts và approvals.

### 17.1. Enforcer ở parent

Nếu parent `pom` được các child kế thừa, cấu hình plugin Enforcer trong `<build><plugins>` có thể được inherit xuống các children. Nhưng parent chỉ chứa `<pluginManagement>` mà không có plugin usage phù hợp thì không tự chạy Enforcer cho mọi module. **Mục tiêu là đảm bảo execution thực sự hiện diện** trong effective POM của module cần được gate.

Kiểm tra:

```bash
mvn -B -ntp -pl :library org.apache.maven.plugins:maven-help-plugin:3.5.1:effective-pom
```

Lệnh này là ví dụ cho reactor có artifactId `library`, **không phải command áp dụng vào lab một module**. Xem effective POM, Maven log và goal thực thi.

### 17.2. Coverage ở multi-module khác một module

JaCoCo `BUNDLE` rule trong lab được áp dụng theo từng Maven module. Nó **không tự tính overall ratio cho toàn reactor**. Muốn coverage toàn hệ thống, xem `jacoco:report-aggregate`, module báo cáo tổng, class/source paths và dữ liệu IT phù hợp.

**Đừng dùng aggregate report như gate nếu chưa có bước check/fail rõ ràng.** JaCoCo `report-aggregate` chủ yếu tạo báo cáo; cần kiểm chứng cách đặt threshold/quality gate tổng trên đúng reports và phiên bản plugin.

### 17.3. Module `pom` không có tests

Nếu root aggregator `pom` không chứa Java classes/tests, `failIfNoTests=true` hay coverage threshold 60% gắn thừa vào root có thể gây lỗi sai hoặc check bị skip vì không có data. Nên thiết kế:
- Enforcer chung ở parent nếu cần.
- Tests/coverage/style ở Java modules.
- Cross-module checks trong một module hoặc CI stage có chủ đích.
- Không sao chép `skipTests` trên toàn reactor để giải quyết một module root không có tests.

### 17.4. Chọn subset bằng -pl

```bash
mvn -B -ntp -pl :service -am clean verify
```

Chọn service và những upstream projects cần theo reactor. Nhưng `-pl` có thể **loại các modules độc lập khác** khỏi build; chất lượng toàn reactor chưa được xác nhận. Không dùng một subset `-pl :service` thành công để công bố **toàn bộ release** nếu policy yêu cầu tất cả modules.

### 17.5. Fail-fast và fail-at-end

```bash
mvn -B -ntp -fae clean verify
```

`-fae` cố hoàn thành các nhánh độc lập và báo failures ở cuối. Nó không khiến downstream module phụ thuộc một failed project chạy thành công, và không thay đổi thứ tự phases nội bộ mỗi module.

Tránh:

```bash
mvn -B -ntp -fn clean verify
```

trong release gate. `-fn` có thể làm Maven bỏ qua exit status failure; CI có nguy cơ xanh giả. Thu thập report từ failed builds bằng CI artifact upload conditions, không ép Maven “fail never”.

## 18. Maven profile cho quality gates: dùng cẩn trọng

Một số nhóm có profiles:
- `fast-dev`: unit tests + compile, bỏ IT nặng.
- `ci`: đầy đủ unit/integration/coverage/style.
- `release`: thêm security/license scans hoặc deploy prerequisites.

Tuy nhiên POM chỉ có profile **không tự bảo đảm nó luôn active**. Ví dụ:

```bash
mvn -Pci clean verify
```

chỉ có giá trị khi project định nghĩa `ci` và quality gates phù hợp. Bài lab đặt gates trong default `build/plugins` thay vì profile để người học dễ thấy cơ chế.

### 18.1. Quy tắc giúp release không bypass

- CI phải ghi rõ active profiles và skip flags.
- Release credential chỉ cấp cho pipeline/job được phép.
- Branch protection không cho merge nếu required checks thiếu.
- Bắt buộc test count/coverage report phù hợp, không chỉ exit code.
- Với quality gate bên ngoài, chờ kết quả và fail khi server trả trạng thái không đạt.
- Có quy trình ngoại lệ có phê duyệt, thay vì ai cũng tự thêm `-DskipTests`.
- Với release artifacts, bảo đảm artifact đã được build/test dưới đúng commit và dependency versions.
- Tách job báo cáo khỏi job có quyền publish.

**Phần Maven POM là cơ chế kỹ thuật, không thay thế các yêu cầu quản trị release.**

## 19. Troubleshooting: build xanh dù gate đáng lẽ fail

| Hiện tượng | Nguyên nhân khả dĩ | Hướng kiểm chứng |
| --- | --- | --- |
| JaCoCo HTML có coverage thấp nhưng `install` vẫn chạy | Chỉ cấu hình `report`, thiếu `check` hoặc haltOnFailure=false | Xem execution goal check và ngưỡng |
| Checkstyle có violations nhưng build success | Chỉ dùng `checkstyle:checkstyle` report hoặc failOnViolation=false | Bind `checkstyle:check` tại phase phù hợp |
| Integration tests fail nhưng `mvn integration-test` success | Chưa chạy Failsafe `verify` | Dùng `mvn verify` và đủ 2 goals |
| `mvn package` success nhưng quality policy chưa qua | `verify` chưa được chạy | Dùng `mvn clean verify` |
| Unit tests không chạy | `-DskipTests`, test naming, engine, Surefire config | Check `target/surefire-reports` và counts |
| IT tests không chạy | Thiếu Failsafe executions, `-DskipITs`, selector không khớp | Check reports + failIfNoTests |
| Coverage không có file `jacoco.exec` | JaCoCo agent bị skip/override argLine, fork không chạy | Xem prepare-agent và test JVM logs |
| Code style gate không chạy | Plugin ở `reporting` chứ không có build execution | Xem effective POM `build/plugins` |
| Enforcer không chạy | Chỉ có `pluginManagement` hoặc `-Denforcer.skip` | Xem execution và log phase validate |
| CI publish artifact dù verify job fail | Publish job không phụ thuộc required checks/uses direct upload | Sửa CI stage dependencies và permissions |
| `mvn deploy:deploy` không chạy tests | Gọi plugin goal trực tiếp thay vì lifecycle | Dùng `mvn deploy` hoặc gate pipeline rõ |
| Một module fail nhưng vài artifacts đã lên repo | Reactor deploy không atomic | Dùng staging/promote và whole-reactor preflight |
| Coverage toàn reactor thấp nhưng module pass | Check theo từng module, chưa có aggregate policy | Dùng aggregate report và CI gate phù hợp |
| Parent aggregator không có IT làm build fail | Copy failIfNoTests=true vào mọi module | Scope policy theo module |
| Plugin yêu cầu Java/Maven mới | Chọn plugin version không khớp runtime | `mvn -version` và plugin requirements |
| Scan external chưa xong nhưng deploy đã bắt đầu | Chỉ upload analysis, không chờ quality-gate result | Cấu hình CI wait/verify server status |
| Local repo còn JAR sau gate fail | Artifact đã install từ invocation trước | So timestamp, build log hoặc isolated repository |

### 19.1. Chẩn đoán goal và phase

Trong Maven log, tìm:
- Tên goal trước dòng `BUILD FAILURE`.
- Phase mà goal bind hoặc đang chạy.
- Các plugin-specific error details.
- Artifact files từ build hiện tại.
- Test failures trong Surefire/Failsafe reports.
- JaCoCo coverage data và rule violation.
- Checkstyle violations cùng filename/line.
- Reactor Summary cho multi-module.

**Không chỉ grep `BUILD FAILURE`**, vì nó cho biết build không thành công nhưng không giải thích gate nào chặn. Và **không chỉ grep `BUILD SUCCESS`** để kết luận quality gates được chạy; có thể build kết thúc sớm ở `test`/`package` hoặc đã skip goals.

### 19.2. Báo cáo tiêu chuẩn cho QA gate

Một bản tóm tắt release evidence có thể gồm:

| Evidence | Trạng thái cần xác nhận |
| --- | --- |
| Maven/JDK/runtime | Phiên bản được phép |
| Unit tests | Số lượng thực thi, 0 failures/errors |
| Integration tests | Số lượng thực thi, 0 failures/errors |
| Coverage | File report hợp lệ, ratio đạt threshold |
| Style/static analysis | Goal check chạy, 0 violations theo policy |
| Security/SBOM | Công cụ/phê duyệt tương ứng đạt |
| Build artifact | Đúng GAV, hash, provenance |
| Publish | Chỉ chạy sau gates/approval, target được phép |

Đây là **mẫu hồ sơ chất lượng**, không phải bằng chứng một build cụ thể đã chạy. Không điền giả PASS khi chưa có logs/reports thật.

## 20. Cách nâng quy tắc từ lab sang sản phẩm thật

**Bước 1: xác định release contract.** Dự án ứng dụng và thư viện khác nhau: library cần binary compatibility, dependency/API policy; service có thể cần security scans, integration tests với database, image/runtime smoke tests.

**Bước 2: chọn minimum gates.** Toolchain và unit tests là nền tảng. Coverage rule nên đặt theo baseline/scope; tránh game metric bằng tests vô nghĩa.

**Bước 3: gắn goals đúng phase.** Enforcer ở `validate`, tests ở `test`/`integration-test`, check/report ở `verify`. Chọn goal **có fail behavior**, không chỉ report.

**Bước 4: tách fail behavior khỏi chỉ số đo.** Thử injection một lỗi có kiểm soát: assertion sai, threshold vượt, style vi phạm. Xác nhận exit code khác 0, build không tới install/deploy.

**Bước 5: kiểm tra skip policy.** Bỏ flags skip trong release pipeline; dùng CI branch protection và code review để chặn thay đổi POM phá gate.

**Bước 6: xác minh coverage/test evidence.** Tests pass nhưng count bằng 0 không đủ; report HTML tồn tại nhưng rỗng không đủ. Xem dữ liệu build hiện tại.

**Bước 7: mở rộng multi-module.** Parent inheritance, aggregator, pluginManagement và module scope cần được kiểm tra qua effective POM và reactor log.

**Bước 8: áp dụng publication discipline.** Chỉ deploy tới repository được ủy quyền, staging/promotion nếu cần whole-reactor safety, không dùng production credentials trong job thử nghiệm.

**Bước 9: theo dõi sau phát hành.** Quality gates tại build-time không thay runtime monitoring, vulnerability patch cadence, incident response và artifact revocation/rollback policy.

## 21. Checklist release quality gate

- [ ] Lệnh release dùng Maven lifecycle phase đúng, không bypass bằng direct plugin goal không được kiểm soát.
- [ ] `mvn -version` thỏa Java/Maven policy.
- [ ] Enforcer execution thực sự bind vào `validate`.
- [ ] Compiler/JAR/plugin versions được quản lý và tương thích.
- [ ] Surefire chạy số unit tests mong đợi, không bị skip.
- [ ] Failsafe bind **cả integration-test và verify**.
- [ ] Setup/teardown integration environment có fallback ngoài Maven khi cần.
- [ ] JaCoCo agent được gắn vào JVM test, có execution data hợp lệ.
- [ ] JaCoCo `check` có threshold và haltOnFailure phù hợp.
- [ ] Checkstyle/PMD/SpotBugs goals có khả năng làm build fail, không chỉ báo cáo.
- [ ] Không dùng `-fn` hoặc failure-ignore flags trong release gate.
- [ ] Không có `-DskipTests`/`-DskipITs`/`-Djacoco.skip`/`-Dcheckstyle.skip`/`-Denforcer.skip` trái policy.
- [ ] Build `clean verify` thành công trên đúng commit và toolchain.
- [ ] Chạy thử lỗi giả lập và xác nhận **không tới install/deploy**.
- [ ] CI yêu cầu external gate đạt trước publication.
- [ ] Mọi module bắt buộc có QA đã được kiểm tra; không nhầm subset với toàn reactor.
- [ ] Với multi-module deploy, có giải pháp trước nguy cơ partial publication.
- [ ] Remote repository, credentials và immutable-release policy được cấu hình an toàn.
- [ ] QA reports được giữ làm bằng chứng và không chứa secrets.
- [ ] Chính sách exceptions được review, không cho skip checks tùy tiện.

## 22. Bài tập tự kiểm tra và đáp án

**Câu 1.** `mvn clean install` có tự chạy phase `verify` không?

**Đáp án:** Có. Khi gọi default lifecycle phase `install`, Maven chạy các phases trước, bao gồm verify; `clean` là lifecycle riêng được gọi trước.

**Câu 2.** `mvn deploy:deploy` có tương đương `mvn deploy` không?

**Đáp án:** Không. Lệnh thứ nhất gọi trực tiếp plugin goal, không tự bảo đảm chạy các lifecycle phases trước; lệnh thứ hai chọn default lifecycle phase deploy.

**Câu 3.** Vì sao không đặt mọi gate ở `validate`?

**Đáp án:** Unit/integration tests, compiled classes và coverage data chưa có ở validate. Nên fail sớm với rules rẻ, rồi kiểm tra kết quả ở phases sau.

**Câu 4.** Goal JaCoCo nào làm build fail khi không đạt ngưỡng?

**Đáp án:** `jacoco:check`, khi cấu hình rule và `haltOnFailure=true`. `jacoco:report` chỉ tạo báo cáo.

**Câu 5.** Checkstyle goal nào dùng để chặn violations?

**Đáp án:** `checkstyle:check` với fail behavior phù hợp, không chỉ `checkstyle:checkstyle`.

**Câu 6.** Vì sao cần cả `failsafe:integration-test` và `failsafe:verify`?

**Đáp án:** Goal đầu chạy IT và ghi kết quả; goal verify đánh giá summary, cho phép teardown ở post-integration-test trước khi báo build failure thông thường.

**Câu 7.** `mvn package` có bảo đảm JaCoCo rule ở verify đã pass không?

**Đáp án:** Không. Package kết thúc trước verify; phải chạy `mvn verify` hoặc phase muộn hơn.

**Câu 8.** Lab có bao nhiêu unit tests và integration tests?

**Đáp án:** **3 unit tests** chạy bởi Surefire và **1 integration test** chạy bởi Failsafe.

**Câu 9.** Java `App.main` trong lab in đúng gì?

**Đáp án:** Một dòng `Hello, Maven!`.

**Câu 10.** Enforcer trong lab kiểm tra điều gì?

**Đáp án:** Maven nằm trong `[3.9.0,4.0.0)` và JDK `[17,)` tại phase validate.

**Câu 11.** JaCoCo `COVEREDRATIO=0.60` có nghĩa 60% test methods đã chạy không?

**Đáp án:** Không. Rule là tỉ lệ **bytecode instructions** được cover, không phải tỉ lệ số tests đã thực thi.

**Câu 12.** Nếu một gate fail ở verify thì `mvn install` có ghi artifact của lượt build đó không?

**Đáp án:** Không đến install phase của module đó trong invocation đang fail. Nhưng local repository vẫn có thể còn artifact từ lần build trước.

**Câu 13.** Có bảo đảm `mvn deploy` trên reactor ba module chỉ upload khi cả ba đã pass không?

**Đáp án:** Không. Những module đi trước có thể đã được deploy trước khi module sau fail; cần staging/promotion hoặc whole-reactor gating riêng khi yêu cầu atomic publication.

**Câu 14.** Vì sao report JaCoCo rỗng mà BUILD SUCCESS không phải coverage PASS?

**Đáp án:** Không có data có thể khiến report/check bị skip; cần xác nhận coverage data và rule thực sự được đánh giá.

**Câu 15.** `-DskipITs` làm gì trong Failsafe 3.6.1?

**Đáp án:** Skip integration tests. `-DskipTests` của Surefire không tự skip Failsafe trong bản 3.6.x.

**Câu 16.** SonarQube upload analysis thành công có đủ làm quality gate không?

**Đáp án:** Chưa. CI còn phải chờ server tính toán và kiểm tra trạng thái quality gate; không chỉ xem upload thành công.

**Câu 17.** `pluginManagement` có tự chạy Enforcer không?

**Đáp án:** Không chỉ nhờ entry quản lý; phải có plugin usage/execution phù hợp trong effective POM.

**Câu 18.** Module `pom` không có IT test có nên áp `failIfNoTests=true` vô điều kiện không?

**Đáp án:** Không. Phải phân loại modules nào được yêu cầu có IT trước khi đặt policy.

**Câu 19.** Nếu code style sai nhưng compiler vẫn pass, gate nào trong lab chặn?

**Đáp án:** `checkstyle:check` ở verify với `failOnViolation=true`.

**Câu 20.** Vì sao không dùng `-fn` trong release pipeline?

**Đáp án:** Nó có thể che lỗi exit status, khiến CI coi build fail là success.

**Câu 21.** Cần kiểm chứng điều gì trước khi giao remote repository credentials?

**Đáp án:** Whole-reactor tests/gates/approval phù hợp đã hoàn tất, artifact/commit provenance đúng, job có quyền publish đã được ủy quyền.

**Câu 22.** Có thể chỉ nhìn `BUILD SUCCESS` để chắc tất cả quality gates đã chạy không?

**Đáp án:** Không. Có thể Maven chỉ chạy tới test/package, hoặc các goals đã bị skip. Phải đối chiếu lifecycle command, active profiles, goal logs, test counts và reports.

## 23. Tài liệu chính thức

- [Apache Maven – Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html): validate/test/package/verify/install/deploy và thứ tự phases.
- [Apache Maven – Running Apache Maven](https://maven.apache.org/run.html): phân biệt goals và phases, ví dụ `mvn verify`/`mvn install`/`mvn deploy`.
- [Apache Maven Enforcer Plugin – Usage](https://maven.apache.org/enforcer/maven-enforcer-plugin/usage.html): `enforcer:enforce`, rules và flag fail/skip.
- [Apache Maven Enforcer Built-In Rules](https://maven.apache.org/enforcer/enforcer-rules/index.html): `requireMavenVersion` và `requireJavaVersion`.
- [Apache Maven Surefire Plugin](https://maven.apache.org/surefire/maven-surefire-plugin/): unit tests ở phase test.
- [Apache Maven Failsafe Plugin – Introduction](https://maven.apache.org/surefire/maven-failsafe-plugin/): goals integration-test/verify và deferred test failure.
- [Apache Maven Failsafe Plugin – Usage](https://maven.apache.org/surefire/maven-failsafe-plugin/usage.html): bind hai goals với lifecycle.
- [JaCoCo Maven – prepare-agent](https://www.jacoco.org/jacoco/trunk/doc/prepare-agent-mojo.html): JVM agent, `argLine` và execution data.
- [JaCoCo Maven – report](https://www.jacoco.org/jacoco/trunk/doc/report-mojo.html): sinh coverage reports.
- [JaCoCo Maven – check](https://www.jacoco.org/jacoco/trunk/doc/check-mojo.html): counter/value/threshold và haltOnFailure.
- [Apache Maven Checkstyle Plugin – Usage](https://maven.apache.org/plugins/maven-checkstyle-plugin/usage.html): bind `checkstyle:check` trong build.
- [Apache Maven Checkstyle Plugin – checkstyle:check](https://maven.apache.org/plugins/maven-checkstyle-plugin/check-mojo.html): violations/check behavior.
- [Apache Maven – Guide to Working with Multiple Modules](https://maven.apache.org/guides/mini/guide-multiple-modules.html): reactor sorting/failure behavior và module subset.
- [Apache Maven – Introduction to Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html): scopes, dependency management, transitivity và version mediation.
