# Từ goal thất bại đến execution, mô-đun và nguyên nhân gốc

> Thuộc nhóm **Chẩn đoán lỗi** của **Build Tool Maven**. Bài hướng dẫn truy lỗi từ thông báo Maven “Failed to execute goal” tới **plugin goal**, **execution ID**, **module trong reactor** và **nguyên nhân gốc**. Dự án ví dụ Java 17 có bốn mô-đun và một JUnit assertion sai có chủ đích, giúp quan sát failure rồi sửa và kiểm chứng.

## 1. Đừng xem BUILD FAILURE là lời giải thích

Một Maven build có thể kết thúc bằng:

```text
[ERROR] Failed to execute goal
org.apache.maven.plugins:maven-surefire-plugin:3.5.2:test
(default-test) on project diagnostic-app:
There are test failures.
[INFO] BUILD FAILURE
```

Dòng trên là **địa chỉ của nơi lỗi được báo**, chưa phải nguyên nhân gốc. Nó cho biết:

| Trường | Giá trị | Cách đọc |
| --- | --- | --- |
| Plugin | `org.apache.maven.plugins:maven-surefire-plugin` | Component Maven chạy unit tests |
| Plugin version | `3.5.2` | Implementation thực sự được invoke |
| Goal | `test` | Tác vụ cụ thể của plugin |
| Execution ID | `default-test` | Một lần thực thi trong build plan |
| Project | `diagnostic-app` | MavenProject/module thực thi goal |
| Triệu chứng | `There are test failures` | Một hoặc nhiều tests không pass |
| Root cause | Chưa biết từ dòng này | Phải đọc Surefire report/assertion/stack trace |

**Phân biệt:** “Goal thất bại” là mô tả một **bước build**. “Nguyên nhân gốc” có thể là assertion sai, Java compiler không thấy symbol, dependency chưa resolve, JDK không hợp lệ, plugin configuration sai, hoặc một service bên ngoài không sẵn sàng.

Một plugin không nhất thiết có bug khi báo build fail. Surefire đúng khi từ chối một test có assertion sai.

## 2. Goal, phase và execution ID

Trong log thường có:

```text
[INFO] --- maven-compiler-plugin:3.13.0:compile (default-compile) @ diagnostic-app ---
[INFO] --- maven-surefire-plugin:3.5.2:test (default-test) @ diagnostic-app ---
```

Cấu trúc:

```text
plugin-artifactId : version : goal  (execution-id)  @ module-artifactId
```

- **Goal** là thao tác của plugin: `compiler:compile`, `surefire:test`, `jar:jar`.
- **Phase** là mốc lifecycle: `validate`, `compile`, `test`, `package`, `verify`.
- **Execution ID** nhận diện một cấu hình/lần chạy goal; cùng goal có thể được bind nhiều lần.

Ví dụ `mvn test` gọi **phase `test` của default lifecycle**, Maven thực hiện các goals được bind từ các phase trước đến phase này. `mvn surefire:test` lại là gọi **plugin goal trực tiếp**, không tự đảm bảo đã compile source/test classes trước. Vì thế không được coi hai lệnh là tương đương.

Execution ID `default-test` thường được lifecycle mapping của `jar` packaging tạo ra; **không bắt buộc** phải xuất hiện trong `pom.xml` của module. Một execution ID khác có thể do parent POM hoặc profile khai.

### Một custom execution

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-antrun-plugin</artifactId>
    <version>3.2.0</version>
    <executions>
        <execution>
            <id>create-build-note</id>
            <phase>generate-resources</phase>
            <goals>
                <goal>run</goal>
            </goals>
            <configuration>
                <target>
                    <mkdir dir="${project.build.directory}/notes"/>
                    <echo file="${project.build.directory}/notes/build.txt"
                          message="generated"/>
                </target>
            </configuration>
        </execution>
    </executions>
</plugin>
```

Đây là **fragment minh họa**, không thuộc POM runnable bên dưới. Nếu bind vào một project, log có thể là:

```text
maven-antrun-plugin:3.2.0:run (create-build-note) @ some-module
```

Nếu chỉ nói “antrun lỗi”, bạn chưa biết execution `create-build-note` hay một execution khác. Phải tìm đúng `<id>`, `<phase>`, `<goals>` và `<configuration>`.

## 3. Reactor Summary: FAILURE khác SKIPPED

Maven reactor sắp xếp các modules theo quan hệ dependency/parent, plugin relationships và thứ tự khai báo khi không có ràng buộc khác.

Ví dụ:

```text
[INFO] Reactor Summary for reactor-diagnostics 1.0.0-SNAPSHOT:
[INFO] reactor-diagnostics .............. SUCCESS
[INFO] diagnostic-core .................. SUCCESS
[INFO] diagnostic-app ................... FAILURE
[INFO] diagnostic-runner ................ SKIPPED
[INFO] diagnostic-extra ................. SKIPPED
[INFO] BUILD FAILURE
```

- `diagnostic-app FAILURE`: module có goal báo lỗi.
- `diagnostic-runner SKIPPED`: module phụ thuộc app; chưa có điều kiện để build tiếp.
- `diagnostic-extra SKIPPED`: có thể chỉ vì Maven **fail-fast**, dù module độc lập.
- `SKIPPED` **không phải** bằng chứng code trong module đó có bug.

Các flag quan trọng:

| Flag | Hành vi | Lưu ý |
| --- | --- | --- |
| `-ff` | Fail-fast (mặc định): dừng tại failure | Các module độc lập phía sau có thể bị skip |
| `-fae` | Fail-at-end: tiếp tục các modules không bị ảnh hưởng rồi báo fail | Hữu ích để thu nhiều kết quả mà vẫn giữ failure |
| `-fn` | Fail-never: không làm command báo exit failure theo cách thông thường | **Không dùng cho CI gate** vì có thể tạo tín hiệu xanh giả |
| `-T 1` | Build tuần tự | Dễ đọc log khi parallel modules làm output xen kẽ |

## 4. Quy trình chẩn đoán có thứ tự

1. **Ghi lại command và môi trường**: working directory, `mvn -version`, source commit, active profiles, `-D`, `-pl`, `-rf` và toolchain.
2. **Đọc Reactor Summary**: module nào `FAILURE`? Modules nào bị `SKIPPED` vì dependency hoặc fail-fast?
3. **Tìm “Failed to execute goal”**: plugin/version/goal/execution và `on project`.
4. **Quay lên phía trên**, tìm lỗi cụ thể xuất hiện trong phần goal: `cannot find symbol`, `expected/actual`, `Could not find artifact`, HTTP 401/403, exception/cause, process exit.
5. **Mở report tại đúng module**: Surefire/Failsafe, compiler, Enforcer hay report của plugin tương ứng.
6. **Đối chiếu effective POM** và active profiles để hiểu tại sao goal/execution được gọi.
7. **Tái hiện phạm vi nhỏ nhất có đủ prerequisites**, không cắt mất upstream dependencies.
8. **Sửa nguyên nhân**, chạy targeted test rồi full reactor.

Không chỉ trích dòng `[ERROR] -> [Help 1]`. Đó là gợi ý tham khảo chung, không phải Java file gây lỗi.

## 5. Dự án Java 17 đa mô-đun thực hành

Ta tạo project:

```text
reactor-diagnostics/
├── pom.xml
├── core/
│   ├── pom.xml
│   ├── src/main/java/dev/lesson/core/Calculator.java
│   └── src/test/java/dev/lesson/core/CalculatorTest.java
├── app/
│   ├── pom.xml
│   ├── src/main/java/dev/lesson/app/DiagnosticApp.java
│   └── src/test/java/dev/lesson/app/DiagnosticAppTest.java
├── runner/
│   ├── pom.xml
│   └── src/main/java/dev/lesson/runner/Runner.java
└── extra/
    ├── pom.xml
    └── src/main/java/dev/lesson/extra/Extra.java
```

Quan hệ:

```text
reactor-diagnostics (parent/aggregator)
        |
   core -> app -> runner
        |
      extra (độc lập với app)
```

Lưu ý sơ đồ biểu diễn parent và dependency relationships ở mức khái niệm; `extra` cũng kế thừa parent nhưng không phụ thuộc core/app.

- `core`: library cộng số, tests pass.
- `app`: phụ thuộc core, **một assertion sai có chủ đích**.
- `runner`: phụ thuộc app nên bị skip khi app fail.
- `extra`: độc lập, giúp quan sát `-fae`.

### 5.1. Parent `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>dev.lesson</groupId>
    <artifactId>reactor-diagnostics</artifactId>
    <version>1.0.0-SNAPSHOT</version>
    <packaging>pom</packaging>

    <modules>
        <module>core</module>
        <module>app</module>
        <module>runner</module>
        <module>extra</module>
    </modules>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.junit.jupiter</groupId>
                <artifactId>junit-jupiter</artifactId>
                <version>5.11.4</version>
            </dependency>
        </dependencies>
    </dependencyManagement>

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
                    <version>3.5.2</version>
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
        </pluginManagement>
    </build>
</project>
```

**Giải thích:** `<modules>` tạo reactor membership; `<parent>` trong POM con để kế thừa configuration. `dependencyManagement` quản lý **version**, không tự tạo dependency. `pluginManagement` quản lý version/config cho plugins được lifecycle sử dụng, không tự bind mọi arbitrary goal. `packaging=pom` của parent không tạo Java JAR. Compiler release 17 cần JDK có thể biên dịch target đó.

### 5.2. `core/pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>dev.lesson</groupId>
        <artifactId>reactor-diagnostics</artifactId>
        <version>1.0.0-SNAPSHOT</version>
    </parent>
    <artifactId>diagnostic-core</artifactId>
    <packaging>jar</packaging>
    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

### 5.3. `core/src/main/java/dev/lesson/core/Calculator.java`

```java
package dev.lesson.core;

public final class Calculator {
    private Calculator() {
    }

    public static int add(int left, int right) {
        return Math.addExact(left, right);
    }
}
```

### 5.4. `core/src/test/java/dev/lesson/core/CalculatorTest.java`

```java
package dev.lesson.core;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import org.junit.jupiter.api.Test;

class CalculatorTest {
    @Test
    void sumsTwoNumbers() {
        assertEquals(5, Calculator.add(2, 3));
    }

    @Test
    void detectsOverflow() {
        assertThrows(
                ArithmeticException.class,
                () -> Calculator.add(Integer.MAX_VALUE, 1)
        );
    }
}
```

Hai tests `core` dự kiến pass.

### 5.5. `app/pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>dev.lesson</groupId>
        <artifactId>reactor-diagnostics</artifactId>
        <version>1.0.0-SNAPSHOT</version>
    </parent>
    <artifactId>diagnostic-app</artifactId>
    <packaging>jar</packaging>
    <dependencies>
        <dependency>
            <groupId>dev.lesson</groupId>
            <artifactId>diagnostic-core</artifactId>
            <version>${project.version}</version>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

### 5.6. `app/src/main/java/dev/lesson/app/DiagnosticApp.java`

```java
package dev.lesson.app;

import dev.lesson.core.Calculator;

public final class DiagnosticApp {
    private DiagnosticApp() {
    }

    public static String summary() {
        return "SUM=" + Calculator.add(2, 3);
    }

    public static void main(String[] args) {
        System.out.println("APP_" + summary());
    }
}
```

### 5.7. `app/src/test/java/dev/lesson/app/DiagnosticAppTest.java`

```java
package dev.lesson.app;

import static org.junit.jupiter.api.Assertions.assertEquals;
import dev.lesson.core.Calculator;
import org.junit.jupiter.api.Test;

class DiagnosticAppTest {
    @Test
    void reportsCorrectSum() {
        // Chủ ý viết expected sai để tạo failure rõ ràng.
        assertEquals(6, Calculator.add(2, 3));
    }
}
```

Trong Java, `Calculator.add(2,3)` trả về 5. Test này đòi 6 nên bị **JUnit assertion failure**. Đây là failure giả lập để học; không được lấy nó làm bằng chứng plugin Surefire lỗi.

### 5.8. `runner/pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>dev.lesson</groupId>
        <artifactId>reactor-diagnostics</artifactId>
        <version>1.0.0-SNAPSHOT</version>
    </parent>
    <artifactId>diagnostic-runner</artifactId>
    <packaging>jar</packaging>
    <dependencies>
        <dependency>
            <groupId>dev.lesson</groupId>
            <artifactId>diagnostic-app</artifactId>
            <version>${project.version}</version>
        </dependency>
    </dependencies>
</project>
```

### 5.9. `runner/src/main/java/dev/lesson/runner/Runner.java`

```java
package dev.lesson.runner;

import dev.lesson.app.DiagnosticApp;

public final class Runner {
    private Runner() {
    }

    public static void main(String[] args) {
        System.out.println("RUNNER_" + DiagnosticApp.summary());
    }
}
```

### 5.10. `extra/pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>dev.lesson</groupId>
        <artifactId>reactor-diagnostics</artifactId>
        <version>1.0.0-SNAPSHOT</version>
    </parent>
    <artifactId>diagnostic-extra</artifactId>
    <packaging>jar</packaging>
</project>
```

### 5.11. `extra/src/main/java/dev/lesson/extra/Extra.java`

```java
package dev.lesson.extra;

public final class Extra {
    private Extra() {
    }

    public static void main(String[] args) {
        System.out.println("EXTRA_OK");
    }
}
```

## 6. Gây lỗi một lần và đọc đúng nơi cần đọc

Từ root `reactor-diagnostics`:

```bash
mvn -version
java -version
mvn -B -ntp clean verify
```

Build **dự kiến fail tại app**, vì JUnit assertion sai. Một phần log minh họa:

```text
[INFO] --- maven-surefire-plugin:3.5.2:test (default-test) @ diagnostic-app ---
[ERROR] Tests run: 1, Failures: 1, Errors: 0, Skipped: 0
[ERROR] dev.lesson.app.DiagnosticAppTest.reportsCorrectSum
[ERROR] expected: <6> but was: <5>
[ERROR] Failed to execute goal
org.apache.maven.plugins:maven-surefire-plugin:3.5.2:test
(default-test) on project diagnostic-app: There are test failures.
[INFO] Reactor Summary:
[INFO] reactor-diagnostics ... SUCCESS
[INFO] diagnostic-core ...... SUCCESS
[INFO] diagnostic-app ....... FAILURE
[INFO] diagnostic-runner .... SKIPPED
[INFO] diagnostic-extra ..... SKIPPED
[INFO] BUILD FAILURE
```

**Các dòng log là dạng minh họa**, format có thể khác ở Maven/JUnit/Surefire versions khác nhau.

Phân tích chính xác: goal `surefire:test` thuộc execution `default-test` đang chạy ở module `diagnostic-app`. Test method `reportsCorrectSum` đòi **6**, actual **5**. Bởi 2+3=5 theo đặc tả demo, lỗi là **test expectation**.

### Đọc report Surefire

Maven Surefire mặc định ghi reports dưới `target/surefire-reports` **của từng module**:

```text
app/target/surefire-reports/
    dev.lesson.app.DiagnosticAppTest.txt
    TEST-dev.lesson.app.DiagnosticAppTest.xml
```

Linux/macOS:

```bash
cat app/target/surefire-reports/dev.lesson.app.DiagnosticAppTest.txt
grep -n "expected" app/target/surefire-reports/*.txt
```

PowerShell:

```powershell
Get-ChildItem app\target\surefire-reports
Get-Content app\target\surefire-reports\dev.lesson.app.DiagnosticAppTest.txt
```

Đừng chỉ tìm root `target` rồi nghĩ không có test reports. Phần lỗi Maven có thể nằm trong `app/target` khi project root chỉ `packaging=pom`.

## 7. `-fae` tách module lỗi và module độc lập

Thử:

```bash
mvn -B -ntp -fae clean verify
```

Một kết quả reactor hợp lý:

```text
reactor-diagnostics ........ SUCCESS
diagnostic-core ............ SUCCESS
diagnostic-app ............. FAILURE
diagnostic-runner .......... SKIPPED
diagnostic-extra ........... SUCCESS
BUILD FAILURE
```

`diagnostic-extra` không bị ảnh hưởng bởi app, nên có thể được build. `runner` vẫn phụ thuộc app nên không chạy thành công. Tổng thể Maven **vẫn fail**. Đây là lý do `-fae` hữu ích hơn `-fn` khi muốn nhìn toàn bộ các module độc lập mà không che lỗi khỏi CI.

## 8. `-pl` và `-am`: chọn đúng module, giữ đủ dependencies

Từ root:

```bash
mvn -B -ntp -pl :diagnostic-app -am test
```

- `-pl :diagnostic-app` chọn Maven project theo artifactId `diagnostic-app`; dấu `:` giúp phân biệt selector với path.
- `-am` xây cùng các reactor projects mà app cần, ở đây có `diagnostic-core`.
- Phase `test` chạy đủ quá trình compile/test cho các modules đã chọn.

Nếu chỉ chạy:

```bash
mvn -B -ntp -pl :diagnostic-app test
```

core có thể không được build trong invocation. Nếu `diagnostic-core:1.0.0-SNAPSHOT` chưa có trong Maven local repository, bạn sẽ nhận thêm lỗi `Could not find artifact`. Đó là **lỗi giả do phạm vi tái hiện sai**, không phải lỗi JUnit ban đầu.

### Chỉ chạy một test method

```bash
mvn -B -ntp -pl :diagnostic-app -am test \
  "-Dtest=DiagnosticAppTest#reportsCorrectSum" \
  -Dsurefire.failIfNoSpecifiedTests=false
```

Vì `-Dtest` áp dụng cho cả reactor selection, core không có `DiagnosticAppTest`. `surefire.failIfNoSpecifiedTests=false` cho phép các modules không chứa test được chỉ định không tạo thêm lỗi “no matching tests”.

Đây **chỉ là phép kiểm có chọn lọc**; sau khi sửa vẫn cần chạy tất cả tests và full reactor.

## 9. Sửa đúng nguyên nhân, xác minh đến cuối

Trong `app/src/test/java/dev/lesson/app/DiagnosticAppTest.java`, thay:

```java
assertEquals(6, Calculator.add(2, 3));
```

bằng:

```java
assertEquals(5, Calculator.add(2, 3));
```

Trong demo này, code chính xác đã trả 5. **Không sửa implementation đúng để phù hợp test sai**.

Chạy:

```bash
mvn -B -ntp -pl :diagnostic-app -am test
mvn -B -ntp clean verify
```

Khi build thành công, bạn có thể chạy mains với classes đã compile:

Linux/macOS:

```bash
java -cp "app/target/classes:core/target/classes" dev.lesson.app.DiagnosticApp
java -cp "runner/target/classes:app/target/classes:core/target/classes" dev.lesson.runner.Runner
java -cp "extra/target/classes" dev.lesson.extra.Extra
```

**Stdout theo thứ tự:**

```text
APP_SUM=5
RUNNER_SUM=5
EXTRA_OK
```

PowerShell (dấu `;` làm classpath separator):

```powershell
java -cp "app\target\classes;core\target\classes" dev.lesson.app.DiagnosticApp
java -cp "runner\target\classes;app\target\classes;core\target\classes" dev.lesson.runner.Runner
java -cp "extra\target\classes" dev.lesson.extra.Extra
```

Demo chỉ dùng Java SE runtime; nếu dự án thật có external runtime dependencies, phải dựng classpath đủ các JAR tương ứng.

## 10. `-rf`: resume có thể gây lỗi dependency mới

Maven thường gợi ý:

```bash
mvn -B -ntp verify -rf :diagnostic-app
```

`-rf` / `--resume-from` **bắt đầu từ một module trong reactor order**, không tự đảm bảo upstream modules đã được rebuild. Nếu core chưa được `install` vào local Maven repository, app có thể không resolve được dependency core:

```text
Could not resolve dependencies for project dev.lesson:diagnostic-app:
Could not find artifact dev.lesson:diagnostic-core:jar:1.0.0-SNAPSHOT
```

Đây là khả năng tùy workspace/local repository state, không phải `-rf` luôn fail. Lệnh an toàn hơn trong demo:

```bash
mvn -B -ntp -pl :diagnostic-app -am verify
```

Sau đó kiểm toàn bộ:

```bash
mvn -B -ntp clean verify
```

`-amd` / `--also-make-dependents` làm việc theo chiều ngược lại với `-am`: khi core thay đổi, muốn kiểm các modules phụ thuộc nó:

```bash
mvn -B -ntp -pl :diagnostic-core -amd verify
```

Điều này chọn nhánh downstream core→app→runner, không bắt buộc bao gồm `extra` độc lập.

## 11. Truy nguồn execution qua effective POM

Khi một execution xuất hiện dù bạn không nhìn thấy trong `app/pom.xml`, cần kiểm:

- Lifecycle bindings theo `packaging=jar`.
- Parent/super POM và pluginManagement.
- `build/plugins` và `<executions><execution>`.
- Active profiles trong POM/settings, `-P`/`-D` trên command line.
- Plugin executions có cùng ID được merge/override qua inheritance.
- Custom packaging, build extensions hoặc CLI-invoked plugin goals.

### Xem effective POM của app

```bash
mvn -B -ntp -f app/pom.xml \
  org.apache.maven.plugins:maven-help-plugin:3.5.2:effective-pom \
  -Dverbose
```

`help:effective-pom` cho thấy parent inheritance/interpolation/active profiles; verbose thêm nhận xét nguồn XML. Nếu muốn lưu ra file, dùng `-Doutput=path/to/effective-pom.xml` tại path có quyền ghi và kiểm đường dẫn thực tế.

### Xem active profiles

```bash
mvn -B -ntp -f app/pom.xml \
  org.apache.maven.plugins:maven-help-plugin:3.5.2:active-profiles
```

### Tra tham số và goal

```bash
mvn -B -ntp \
  org.apache.maven.plugins:maven-help-plugin:3.5.2:describe \
  -Dplugin=org.apache.maven.plugins:maven-surefire-plugin \
  -Dgoal=test -Ddetail=true
```

Goal `help:describe` giải thích các plugin parameters/user properties. Không tự đoán tên `-Dproperty` chỉ từ XML field.

### Ví dụ execution lỗi riêng

Fragment **không thuộc demo POM**:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-enforcer-plugin</artifactId>
    <version>3.5.0</version>
    <executions>
        <execution>
            <id>require-java-17-runtime</id>
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
```

Nếu thêm ở `build/plugins` và chạy Maven bằng JDK 21, execution `require-java-17-runtime` có thể fail ở phase `validate`. Root cause là **Java runtime chạy Maven không thỏa rule**, chứ không phải assertion trong app. Kiểm `mvn -version`: Java runtime Maven dùng có thể khác Java của terminal.

## 12. `-e`, `-X` và `Caused by`

Một build error có thể có chuỗi:

```text
Failed to execute goal ...: MojoExecutionException ...
Caused by: java.lang.IllegalStateException: ...
Caused by: java.nio.file.NoSuchFileException: ...
```

`MojoExecutionException` là wrapper thông báo plugin goal không hoàn thành; `Caused by` sâu hơn giúp xác định file/exception. Nhưng không máy móc chọn sâu nhất: nguyên nhân nghiệp vụ/config có thể ở lớp trên.

```bash
mvn -B -ntp -e clean verify
```

`-e` giúp xem exception details.

```bash
mvn -B -ntp -X clean verify
```

`-X` rất chi tiết, hữu ích cho resolver/config nhưng có thể chứa nội bộ URLs, settings/system properties và dữ liệu nhạy cảm. **Redact secrets trước khi chia sẻ log**. Không chạy mã từ repository chưa tin cậy trên môi trường có production credentials chỉ để xem `-X`.

## 13. Các kiểu failure thường gặp khác

| Thông báo / goal | Gốc vấn đề có thể | Cách kiểm tra |
| --- | --- | --- |
| `compiler:compile` + `cannot find symbol` | Source/import/classpath hoặc generator chưa chạy | Java file/line, dependencies, generated sources |
| `invalid target release: 17` | JDK/Compiler không hỗ trợ target | `mvn -version`, `JAVA_HOME` |
| `surefire:test` + expected/actual | Test assertion | `target/surefire-reports` của module |
| `failsafe:verify` | Integration test fail | `target/failsafe-reports`, services/test data |
| `Could not resolve dependencies` | GAV, parent, reactor selection, repo/cache | `-pl`/`-am`, `settings.xml`, artifact coordinates |
| `Plugin ... could not be resolved` | Plugin GAV/pluginRepository/mirror/network | POM/pluginManagement/settings |
| `resources:resources` | File path/encoding/filtering | Resource directories, effective config |
| `enforcer:enforce` | Build policy rule vi phạm | Execution ID, rule, Maven/JDK/dependencies |
| `jar:jar` | Packaging/archive | target/classes, permissions, manifest |
| `deploy:deploy` + `401/403` | Repository auth/ACL | `distributionManagement`, server ID/settings |
| `site:site` | Site rendering/reporting | Doxia content, site descriptor |
| Plugin external process exit code | CLI/process/OS | Args, cwd, env, permissions |

Phải phân biệt **test failure** (assertion sai), **test error** (exception), **skipped test** và **0 tests**. Trường hợp 0 tests có thể do cấu hình discovery/provider sai; không tự xem là full QA pass.

`cannot find symbol` có thể do generated sources chưa được tạo, không chỉ lỗi Java trực tiếp. Một `Could not resolve dependencies` ở downstream có thể do upstream module fail hoặc chọn reactor thiếu prerequisites.

## 14. Nếu CI fail nhưng local pass

Thu thập cùng một bộ bằng chứng:

```text
Git commit/tag + dirty state
Exact mvn invocation + working directory
Maven/JDK version, OS/architecture
Profiles, properties, settings/mirrors (không lộ secrets)
Reactor Summary + module order
Plugin/version/goal (execution-id) @ module
First actionable error + relevant Caused by chain
Surefire/Failsafe/compiler/repository logs
Targeted reproduction + full reactor validation
```

Những khác biệt hay gặp: profiles `-Pci`, container JDK, dependency SNAPSHOT/ranges, cache, env variables, network/proxy/TLS, filesystem case sensitivity, parallel tests, shared ports, clock/locale và CI checkout location.

Bash lưu log mà vẫn giữ Maven exit status:

```bash
set -o pipefail
mvn -B -ntp clean verify 2>&1 | tee build.log
grep -nE 'Failed to execute goal|Reactor Summary|Caused by:|Tests run:|cannot find symbol|Could not resolve' build.log
```

`grep` chỉ chỉ ra vị trí cần đọc; không tự xác định nguyên nhân. Không đăng log chứa secrets lên issue công khai.

## 15. Tránh “fix” bằng cách che lỗi

Những lệnh sau **không sửa assertion**:

```bash
mvn -DskipTests clean verify
mvn -Dmaven.test.skip=true package
mvn -fn verify
```

- `skipTests` bỏ chạy test, không sửa code/test sai.
- `maven.test.skip` còn có thể bỏ test compilation.
- `-fn` có thể che exit failure khỏi CI.
- Xóa test, tắt Enforcer, đổi expected mà không xem spec có thể gây lỗi nghiêm trọng.
- Xóa `~/.m2/repository` hoặc thêm `-U` không sửa sai artifact GAV/JDK; còn có thể thay dependency resolution và che dấu nguyên nhân.

Một sửa lỗi đúng cần chứng minh **giả thuyết → thay đổi tối thiểu → targeted test pass → full reactor pass**.

## 16. Ticket chẩn đoán mẫu

**Tiêu đề:** `diagnostic-app — surefire:test (default-test) assertion sai`.

**Build:** `mvn -B -ntp clean verify` từ root, JDK17, Maven3.9.

**Goal/module:** `maven-surefire-plugin:3.5.2:test (default-test) @ diagnostic-app`.

**Bằng chứng:** `DiagnosticAppTest.reportsCorrectSum` expected 6, actual 5. Reactor: core SUCCESS, app FAILURE, runner/extra SKIPPED.

**Root cause:** Test expected value sai theo định nghĩa phép cộng; không phải Surefire/plugin hoặc Calculator implementation.

**Fix:** `assertEquals(5, Calculator.add(2,3))`.

**Validation:** `mvn -pl :diagnostic-app -am test` và `mvn clean verify` đều pass, `APP_SUM=5` khi chạy Java.

Không đưa token/password vào ticket và không dùng log demo làm bằng chứng cho một run chưa thực thi.

## 17. Câu hỏi tự kiểm tra

**1.** Dòng `maven-surefire-plugin:3.5.2:test (default-test) @ diagnostic-app` cho biết gì?

**Đáp án:** Plugin/version, goal, execution ID và module. Phải đọc report mới biết test nào lỗi.

**2.** `default-test` có nhất thiết được khai trong app POM?

**Đáp án:** Không. Nó có thể đến từ lifecycle mapping của `jar` packaging.

**3.** `runner SKIPPED` có nghĩa Runner.java sai?

**Đáp án:** Không. App upstream fail có thể khiến runner không được build.

**4.** Vì sao dùng `-fae` thay vì `-fn`?

**Đáp án:** `-fae` tiếp tục modules không bị ảnh hưởng và vẫn giữ build failure; `-fn` có thể che exit status lỗi.

**5.** `-pl :diagnostic-app -am` có tác dụng gì?

**Đáp án:** Chọn app và build các reactor dependencies như core; tránh missing artifact do chọn thiếu upstream.

**6.** `-rf :diagnostic-app` có tự build core không?

**Đáp án:** Không bảo đảm; nếu core chưa được install, lỗi dependency mới có thể xuất hiện.

**7.** Trong demo nên sửa test hay Calculator?

**Đáp án:** Test; 2+3=5, implementation đúng.

**8.** Surefire report nằm đâu?

**Đáp án:** Ở `target/surefire-reports` của từng module, ví dụ `app/target/surefire-reports`.

**9.** Khi nào cần `help:effective-pom`?

**Đáp án:** Khi cần xem cấu hình sau parent inheritance/profiles/pluginManagement và tìm nguồn execution.

**10.** Vì sao phải chạy full reactor sau targeted fix?

**Đáp án:** Để bảo đảm downstream modules và các quality gates khác vẫn pass.

## 18. Checklist khi gặp lỗi Maven trong dự án thật

- [ ] Biết commit, command, cwd, Maven/JDK và active profiles.
- [ ] Xác định `FAILURE`/`SKIPPED` trong Reactor Summary.
- [ ] Ghi plugin/version/goal, execution ID và project artifactId.
- [ ] Đọc error message cụ thể, report đúng module và stack trace.
- [ ] Phân biệt module báo failure với nơi root cause xuất hiện.
- [ ] Kiểm parent/effective POM, `pluginManagement`, profiles và executions.
- [ ] Kiểm dependency GAV, settings/mirror và upstream modules.
- [ ] Dùng `-pl -am` khi cô lập branch có dependencies.
- [ ] Cẩn thận với `-rf` nếu upstream chưa có artifact trong local repo.
- [ ] Dùng `-fae` nếu muốn quan sát modules không bị ảnh hưởng.
- [ ] Không dùng `-fn` hoặc `skipTests` để che failure.
- [ ] Kiểm JDK/toolchain, locale, network và CI environment.
- [ ] Không chia sẻ debug logs chứa secrets.
- [ ] Sửa theo business spec, không chỉ để có `BUILD SUCCESS`.
- [ ] Xác minh targeted test, full reactor và CI exit code.

**Kết luận:** Maven hiển thị **goal và execution ID** để chỉ ra điểm build thất bại, nhưng **root cause** phải xác nhận qua test reports, compiler diagnostics, dependency resolution hoặc stack trace của đúng module. Biết dùng `-pl`, `-am`, `-rf`, `-fae` và effective POM giúp điều tra nhanh mà không tạo lỗi giả; chẩn đoán chỉ hoàn thành khi nguyên nhân đã sửa và **full reactor được kiểm chứng lại**.

## Tài liệu tham khảo

- [Apache Maven — Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Apache Maven — Working with Multiple Modules](https://maven.apache.org/guides/mini/guide-multiple-modules.html)
- [Apache Maven — Configuring Plugins](https://maven.apache.org/guides/mini/guide-configuring-plugins.html)
- [Apache Maven — Default Mojo Execution IDs](https://maven.apache.org/guides/mini/guide-default-execution-ids.html)
- [Maven Help Plugin — effective-pom](https://maven.apache.org/plugins/maven-help-plugin/effective-pom-mojo.html)
- [Maven Help Plugin — describe](https://maven.apache.org/plugins/maven-help-plugin/describe-mojo.html)
- [Maven Surefire — surefire:test](https://maven.apache.org/surefire/maven-surefire-plugin/test-mojo.html)
- [Maven Surefire — Running a Single Test](https://maven.apache.org/surefire/maven-surefire-plugin/examples/single-test.html)
- [Maven Failsafe Plugin](https://maven.apache.org/surefire/maven-failsafe-plugin/)
- [Maven Enforcer Rule — Require Java Version](https://maven.apache.org/enforcer/enforcer-rules/requireJavaVersion.html)

*Dự án demo dùng Java17, Maven3.9.x, JUnit Jupiter5.11.4, Compiler Plugin3.13.0, Surefire3.5.2, Resources3.3.1 và JAR3.4.2. Test `DiagnosticAppTest` được cố ý viết sai để người học tự tái hiện; các đoạn log và stdout là kết quả dự kiến từ cấu hình, chưa được chạy build độc lập khi biên soạn bài.*
