# Cấu hình IDE và đối chiếu với cách chạy trên dòng lệnh

## 1. Mục tiêu của việc đối chiếu

Trong dự án Spring Boot, có ít nhất hai cách thông dụng để khởi chạy kiểm thử:

1. **Chạy từ IDE:** nhấn biểu tượng Run/Debug cạnh phương thức hoặc lớp test trong IntelliJ IDEA, Eclipse hay Visual Studio Code; tùy IDE và cấu hình, việc chạy có thể do **JUnit runner của IDE** hoặc **Gradle/Maven** thực hiện.
2. **Chạy từ dòng lệnh:** sử dụng **Gradle Wrapper** (`gradlew`) hoặc **Maven Wrapper** (`mvnw`) để build tool khám phá và thực thi test theo cấu hình dự án; đây thường là cách CI thực hiện.

Điều cần đạt không phải là hai nơi có giao diện hay thời gian chạy giống nhau. Điều cần đạt là **cùng mã nguồn, cùng phiên bản/phụ thuộc, cùng cấu hình có ý nghĩa và cùng phạm vi kiểm thử phải cho cùng kết quả**. Nếu IDE báo xanh nhưng lệnh test trong terminal hoặc CI báo đỏ, phải tìm khác biệt thực tế giữa hai môi trường chứ không mặc định tin một phía.

Sau bài này, bạn có thể:

- Cấu hình JDK, test framework và build tool để IDE nhận diện được JUnit Jupiter test.
- Phân biệt runner của IDE với Gradle/Maven test task hoặc plugin.
- Chạy cùng lớp/phương thức test ở IDE, terminal và CI; xác nhận test **thực sự đã chạy**.
- So sánh Java version, classpath, profile, biến môi trường, working directory, JVM arguments và hạ tầng test.
- Tìm nguyên nhân khi test chỉ đạt ở một nơi và thiết lập quy trình kiểm chứng tái hiện được.

**Phạm vi:** dự án Spring Boot dùng Java 17+ và JUnit Jupiter, có thể dùng Gradle hoặc Maven. Các lệnh minh họa dành cho dự án đã có build wrapper và cấu hình dependency tương ứng; không phải mọi dự án đều sử dụng đồng thời cả hai build tool.

## 2. Những lớp cấu hình quyết định kết quả kiểm thử

Việc “IDE đã nhận ra test” chưa có nghĩa IDE đang chạy đúng pipeline kiểm thử của dự án. Hãy phân biệt các lớp sau:

| Lớp | Chức năng | Điều cần đối chiếu |
|---|---|---|
| **JDK** | Biên dịch và chạy Java | Project SDK, Gradle JVM/Maven JVM, Java toolchain, JVM của test |
| **Build tool** | Tạo classpath, compile test, xử lý source set, tài nguyên, plugin | Gradle Wrapper/Maven Wrapper, phiên bản plugin, task/goal |
| **Test framework** | Khám phá test, vòng đời, assertion, extension | JUnit Jupiter và JUnit Platform/Surefire provider |
| **Runner** | Khởi chạy test theo lựa chọn | IDE JUnit runner hay Gradle/Maven runner |
| **Spring TestContext** | Tạo/nạp/cached ApplicationContext cho các test dùng Spring | `@SpringBootTest`, test slice, `@ActiveProfiles`, override property |
| **Môi trường** | Cung cấp biến, file, DB, Docker, locale, timezone | OS, current directory, environment variables, cổng, container |
| **Bộ lọc test** | Quyết định test nào được chọn | Class/method/package, test tags, task, source set, include/exclude |

Một số hiện tượng dễ nhầm:

- IDE chạy test Java trực tiếp có thể bỏ qua `systemProperty`, JVM args hoặc việc generate source mà bạn chỉ khai báo trong Gradle task.
- Gradle có thể đánh dấu `test` là `UP-TO-DATE`, nên dòng lệnh kết thúc thành công **không chứng minh test vừa được thực thi lại**.
- Một dự án nhiều module có thể có nhiều task `test`; lệnh ở root và thao tác Run ở một module có thể chọn **khác phạm vi**.
- Test tích hợp cần Docker/database có thể xanh trên máy có hạ tầng đó và đỏ khi runner hoặc CI không truy cập được.

## 3. Thiết lập dự án chuẩn trước khi chỉnh IDE

### 3.1. Giữ cấu trúc test nhất quán

Cấu trúc thường gặp cho Java + Spring Boot:

```text
project/
├── build.gradle                 # Gradle (hoặc pom.xml với Maven)
├── settings.gradle              # nếu dùng Gradle
├── gradlew / gradlew.bat         # nếu dùng Gradle Wrapper
├── mvnw / mvnw.cmd               # nếu dùng Maven Wrapper
├── src/
│   ├── main/java/com/example/testing/...
│   ├── main/resources/application.yml
│   ├── test/java/com/example/testing/...
│   └── test/resources/application-test.yml
└── ...
```

Sơ đồ thể hiện các tên file **theo từng loại dự án**; một dự án thực tế không bắt buộc có cả hai wrapper. Thông thường Gradle/Maven nhận `src/test/java` và `src/test/resources` theo quy ước. Thư mục `src/integrationTest/java` chỉ chạy khi dự án đã định nghĩa source set/task hoặc plugin phù hợp; tạo thư mục này **không tự động** làm test được khám phá.

Trong IDE, mở **thư mục gốc chứa cấu hình build**; import hoặc reload từ `build.gradle(.kts)` hay `pom.xml`. Không dựa vào việc tự thêm thư viện JAR thủ công vào IDE nếu build project đã có hệ thống quản lý dependency.

### 3.2. Cấu hình Gradle/JUnit Jupiter

Với một dự án Spring Boot **đã khai báo Spring Boot plugin và các repository/dependency management cần thiết**, phần test liên quan trong `build.gradle` (Groovy DSL) có thể là:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
```

- `spring-boot-starter-test` đưa các công cụ kiểm thử phổ biến, bao gồm JUnit Jupiter, vào test classpath theo phiên bản Spring Boot được quản lý.
- `useJUnitPlatform()` bảo đảm Gradle `Test` task chạy qua JUnit Platform.
- Cần giữ dependency và version theo **build file của dự án**, không gắn một version JUnit ngẫu nhiên chỉ trong IDE.
- Với Gradle Kotlin DSL, cấu hình tương đương thường là `tasks.test { useJUnitPlatform() }`.

Nếu cần thống nhất bản Java cho compile/test, Gradle Java Toolchains có thể được cấu hình ví dụ như sau trong dự án dùng Java 21:

```groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}
```

**Phân biệt:** JDK dùng để **chạy Gradle** và JDK của **toolchain dùng cho compile/test** có thể khác nhau. Lệnh `./gradlew --version` giúp kiểm tra Gradle runtime, nhưng không đủ để khẳng định mọi test JVM dùng đúng toolchain; cần đọc cấu hình task/toolchain và kiểm tra test execution khi nghi ngờ.

### 3.3. Cấu hình Maven/JUnit Jupiter

Trong dự án Maven Spring Boot đã có cấu hình quản lý version phù hợp, khai báo starter test trong `pom.xml`:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
```

JUnit Jupiter phải được Maven Surefire phiên bản phù hợp hỗ trợ để chạy ở phase `test`. Với dự án theo Spring Boot parent/plugin management hiện hành, thường đã có cấu hình hợp lý; khi tự quản lý Maven plugins, hãy xác minh phiên bản `maven-surefire-plugin` và JUnit Platform provider thay vì chỉ dựa vào IDE.

Nếu ứng dụng có **integration tests** được nối với Maven Failsafe, các test đó thường được thực thi ở những phase/goal cấu hình cho integration-test/verify, **không mặc nhiên** thuộc `mvn test`. Điều tương tự đúng với Gradle source set/task bổ sung. Khi đối chiếu, phải so cùng tập test.

### 3.4. Đồng bộ JDK và dependencies

Kiểm tra ba thứ riêng biệt:

1. **JDK IDE dùng để biên dịch/chạy test** có thỏa yêu cầu của mã nguồn không?
2. **JDK build tool chạy** và **toolchain compile/test** có phù hợp không?
3. **Danh sách dependency** mà IDE import có khớp build file và lockfile/BOM không?

Một dự án Spring Boot 3.x yêu cầu tối thiểu Java 17; nếu dự án đặt Java 21, cả IDE và pipeline cần cung cấp JDK/toolchain phù hợp. Sau khi đổi JDK, `build.gradle(.kts)` hoặc `pom.xml`, hãy reload project và kiểm tra xem IDE đã đánh dấu `src/test/java` là nguồn test hay chưa.

## 4. Ví dụ đối chiếu có thể chạy được bằng JUnit Jupiter

Ví dụ này không khởi động Spring context; mục đích là tách bài toán **IDE/CLI đã chọn đúng Java, dependency và runner** khỏi lỗi liên quan Spring/DB. Hai file dưới đây độc lập với ứng dụng và chạy được trong dự án Java 17+ đã cấu hình JUnit Jupiter.

**File `src/main/java/com/example/testing/FeeCalculator.java`:**

```java
package com.example.testing;

public final class FeeCalculator {

    public int total(int subtotal, int fee) {
        if (subtotal < 0 || fee < 0) {
            throw new IllegalArgumentException("Amounts must be non-negative");
        }
        return Math.addExact(subtotal, fee);
    }
}
```

**File `src/test/java/com/example/testing/FeeCalculatorTest.java`:**

```java
package com.example.testing;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class FeeCalculatorTest {
    private final FeeCalculator calculator = new FeeCalculator();

    @Test
    void addsFee() {
        assertEquals(120, calculator.total(100, 20));
    }

    @Test
    void rejectsNegativeAmounts() {
        assertThrows(
                IllegalArgumentException.class,
                () -> calculator.total(-1, 0)
        );
    }

    @Test
    void rejectsOverflow() {
        assertThrows(
                ArithmeticException.class,
                () -> calculator.total(Integer.MAX_VALUE, 1)
        );
    }
}
```

**Kết quả mong đợi:** IDE/JUnit Platform hoặc Gradle/Maven runner khám phá đúng **ba** phương thức test; cả ba thành công. Phương thức `total` không in gì ra stdout. Tùy IDE/build tool, console có thể hiện số test, số pass và thời gian theo định dạng khác nhau; không nên bắt một dòng log cố định làm bằng chứng.

**Cách chạy trong IDE:** import/reload dự án, mở `FeeCalculatorTest.java`, nhấn Run cạnh lớp để chạy cả ba hoặc cạnh `addsFee` để chạy riêng. Xác nhận báo cáo thực thi hiển thị đúng số phương thức được chọn.

**Cách chạy qua Gradle Wrapper trên Linux/macOS:**

```bash
./gradlew --version
./gradlew test --tests "com.example.testing.FeeCalculatorTest"
./gradlew test --tests "com.example.testing.FeeCalculatorTest.addsFee"
```

**Cách chạy qua Maven Wrapper trên Linux/macOS:**

```bash
./mvnw --version
./mvnw -Dtest=FeeCalculatorTest test
./mvnw "-Dtest=FeeCalculatorTest#addsFee" test
```

Chọn **một** nhóm lệnh tương ứng với build tool thực tế. Với `--tests`, Gradle cho phép lọc theo fully qualified class/method. Với Maven Surefire, `-Dtest=...` chọn lớp hoặc phương thức; khả năng lọc của plugin phụ thuộc phiên bản/cấu hình.

**Lưu ý về thông số:** ví dụ `-Dtest=...` là một *Maven Surefire test selector*. Không suy diễn rằng mọi `-D...` truyền cho Gradle đều tự động trở thành system property của JVM đang chạy test; Gradle có thể thực thi test ở một JVM fork khác.

## 5. Cấu hình trong các IDE phổ biến

### 5.1. IntelliJ IDEA: chọn đúng test runner

1. Mở dự án từ Gradle hoặc Maven build file; chờ IDE hoàn tất index và sync.
2. Kiểm tra **Project SDK**, Java language level và, với Gradle, **Gradle JVM** trong phần cấu hình build tool. Với Java Toolchains, kiểm tra JDK phù hợp có sẵn.
3. Trong Gradle project, mở **Settings / Build, Execution, Deployment / Build Tools / Gradle** và kiểm tra lựa chọn **Run tests using** (tên/vị trí menu có thể thay đổi theo phiên bản):
   - **Gradle:** sử dụng Gradle thực thi test, gần với đường chạy CLI/CI hơn và tôn trọng cấu hình test task.
   - **IntelliJ IDEA:** dùng JUnit runner của IDE, thường khởi chạy nhanh và thuận lợi để debug một test nhưng có thể không áp dụng mọi tùy biến task Gradle.
   - **Choose per test** nếu phiên bản IDE hỗ trợ: chọn runner theo từng cấu hình chạy.
4. Nhấn biểu tượng tam giác cạnh lớp/phương thức test, xem **Run** tool window: runner nào đã thực thi, class/method nào được chọn, có thực sự chạy ba phương thức hay không.
5. Chạy lại test đó bằng **Gradle tool window → Tasks → verification → test** hoặc một Gradle run configuration; so sánh với terminal.
6. Khi cần debug, dùng **Debug** trên cùng test; breakpoint phải nằm trên mã thực thi chứ không phải trên mã đã bị IDE hoặc build chưa biên dịch lại.

**Điểm dễ gây lệch:** người học chọn “Run using IntelliJ IDEA”, nhưng dự án khai báo `systemProperty`, `jvmArgs`, `environment`, `maxParallelForks` hoặc tác vụ generate code/resources chỉ trong Gradle `Test` task. Test được IDE chạy có thể nhận classpath/properties khác. Khi kết quả lệch, chuyển runner sang Gradle trước để kiểm tra tính đồng nhất với CLI, rồi xử lý nguyên nhân gốc.

### 5.2. Visual Studio Code: Java Test Runner và terminal là hai đường chạy

1. Cài bộ extension Java phù hợp, bao gồm **Language Support for Java** và **Test Runner for Java** (thường có trong **Extension Pack for Java**).
2. Mở đúng project root/workspace; để Java language server nhận diện Gradle hoặc Maven project, test source và dependencies.
3. Kiểm tra cấu hình **Java runtime/JDK** cho workspace, nhất là khi máy cài nhiều JDK.
4. Trong **Testing** view hoặc biểu tượng Run cạnh test, chọn Run/Debug lớp hoặc phương thức.
5. Với các test cần cấu hình riêng cho extension, VS Code cho phép thiết lập test configuration như `java.test.config`. Đối chiếu JVM args, environment và working directory của cấu hình đó với build tool.
6. Mở terminal ngay tại project root và chạy `./gradlew test` hoặc `./mvnw test` để có đường chạy quy chiếu. Chạy qua một VS Code task gọi wrapper vẫn là chạy build tool, khác với extension gọi Java test runner trực tiếp.

**Lưu ý:** chỉ thấy test xanh trong Testing view chưa xác nhận CI test task đã chạy; VS Code extension và Gradle/Maven có thể chọn cách khởi chạy khác.

### 5.3. Eclipse: JUnit Run As, Buildship và m2e

1. Đảm bảo Eclipse biết **Installed JRE/JDK** phù hợp và project compiler compliance khớp dự án.
2. Import theo loại dự án: **Gradle/Buildship** hoặc **Maven/m2e**; đồng bộ lại khi build file đổi.
3. Kiểm tra `src/test/java` là test source folder trên classpath, và dependencies JUnit Jupiter đã được resolve.
4. Chạy `Run As → JUnit Test` (hoặc lệnh tương ứng của phiên bản Eclipse) để kiểm tra runner của IDE.
5. Khi cần so sát cấu hình build, gọi task `test` bằng Gradle tooling/terminal hoặc goal `test` bằng Maven tooling/terminal.
6. Dùng Debug As JUnit Test để đặt breakpoint; kiểm tra VM arguments, environment và working directory trong Run Configuration.

Nếu lỗi chỉ xuất hiện khi chạy qua build tool, điều tra plugin, task, source set và test execution config; đừng mặc định sửa JUnit test cho hợp riêng JUnit runner của Eclipse.

### 5.4. Quy tắc chung cho cả ba IDE

**Run một phương thức** không thay thế **run cả lớp/module/suite**. Người học nên giữ hai loại cấu hình:

- Cấu hình **phản hồi nhanh**: chạy test đang sửa để debug/đọc assertion gần lỗi.
- Cấu hình **kiểm chứng tương đương CI**: chạy đúng wrapper task/goal và test scope được CI dùng.

Có thể dùng runner IDE để học/điều tra, nhưng quyết định “test suite đã đạt” nên dựa vào build tool, cấu hình và phạm vi được hệ thống build/CI công nhận.

## 6. Các lệnh dòng lệnh cần biết và ý nghĩa thực sự

### 6.1. Gradle Wrapper

Linux/macOS, chạy tại project root:

```bash
./gradlew --version
./gradlew test
./gradlew test --tests "com.example.testing.FeeCalculatorTest"
./gradlew test --tests "com.example.testing.FeeCalculatorTest.addsFee"
./gradlew test --rerun-tasks
./gradlew clean test
```

Windows PowerShell:

```powershell
.\gradlew.bat --version
.\gradlew.bat test --tests "com.example.testing.FeeCalculatorTest"
.\gradlew.bat test --rerun-tasks
```

Diễn giải:

- `./gradlew` dùng phiên bản Gradle được Wrapper quản lý, giảm khác biệt do Gradle global trên máy.
- `test` chạy task có tên `test` theo cấu hình và phạm vi dự án. Với multi-project, cần chọn đúng task path, ví dụ `./gradlew :service:test`, nếu muốn một module cụ thể.
- `--tests` thu hẹp lớp/phương thức theo bộ lọc của Gradle. Nếu không match, Gradle có thể báo không tìm thấy test phù hợp thay vì thực thi toàn suite.
- `--rerun-tasks` ép thực thi lại các task thay vì tin vào trạng thái up-to-date; hữu ích khi muốn chứng minh test **đã chạy lại**, nhưng có thể làm cả các dependency task chạy lại.
- `clean test` xóa output build rồi build/test mới, tốn thời gian hơn và có thể chạm thêm các task, không phải việc bắt buộc mỗi lần debug.

Gradle thường tạo:

- Kết quả có cấu trúc: `build/test-results/test/`.
- Báo cáo HTML: `build/reports/tests/test/index.html`.

Trong multi-project hoặc task riêng, đường dẫn report có thể nằm dưới module và theo tên task. Khi thấy `UP-TO-DATE`, `FROM-CACHE` hoặc `SKIPPED`, cần phân biệt với **test được thực thi và pass**.

### 6.2. Maven Wrapper

Linux/macOS, tại thư mục chứa `pom.xml`:

```bash
./mvnw --version
./mvnw test
./mvnw -Dtest=FeeCalculatorTest test
./mvnw "-Dtest=FeeCalculatorTest#addsFee" test
./mvnw clean test
```

Windows PowerShell:

```powershell
.\mvnw.cmd --version
.\mvnw.cmd "-Dtest=FeeCalculatorTest" test
.\mvnw.cmd "-Dtest=FeeCalculatorTest#addsFee" test
```

Diễn giải:

- `test` chạy Maven lifecycle đến phase test, thường nhờ **Surefire** tìm unit tests theo naming pattern/cấu hình.
- `-Dtest=...` thu hẹp test theo cú pháp mà Surefire hỗ trợ; khi phương thức không được chọn, kiểm tra phiên bản Surefire, tên test thực tế và JUnit engine.
- Báo cáo Surefire thường nằm ở `target/surefire-reports/`.
- Với module Maven nhiều cấp, gọi ở đúng module hoặc chọn `-pl`/`-am` phù hợp; phạm vi này không tự động giống bấm Run test trong IDE.
- Với **Failsafe integration tests** cấu hình riêng, thường cần các phase/goal tương ứng, chẳng hạn `verify`, để thực thi và xác nhận kết quả của chúng.

**Không trộn lệnh:** Gradle `--tests` không phải Maven `-Dtest`; Gradle `test` task không đồng nghĩa Maven `test` lifecycle, dù cả hai có thể chạy các JUnit Jupiter test tương tự.

### 6.3. Đọc lỗi thay vì chỉ đọc dòng BUILD SUCCESS

Một lần so sánh hợp lệ cần kiểm tra đồng thời:

1. Build/compile có thành công?
2. Runner đã khám phá **đúng số lượng và tên test**?
3. Có test bị skip, disabled, filtered out hoặc không chạy?
4. Test thất bại ở assertion, context startup, dependency discovery hay hạ tầng ngoài?
5. File report có đúng module/task và đúng lần chạy không?

Khi Gradle báo lỗi chưa rõ, dùng `./gradlew test --stacktrace`; khi cần thêm thông tin về task/config, có thể dùng `--info`. Maven có `./mvnw -e test` để xem stacktrace chi tiết. Dùng log chi tiết có chọn lọc vì lượng thông tin lớn có thể làm chìm lỗi chính.

## 7. Profile, properties và môi trường: nguồn lệch IDE/CLI phổ biến

### 7.1. Nên đặt cấu hình test ở đâu?

Test độc lập nên để các tiền điều kiện cần thiết ngay trong test hoặc cấu hình dành cho test, càng ít phụ thuộc cách bấm Run càng tốt. Với Spring integration test, có thể đặt cấu hình test tại `src/test/resources/application-test.yml` rồi kích hoạt profile bằng annotation:

**Đoạn minh họa trong dự án có `@SpringBootApplication` được phát hiện đúng package:**

```java
package com.example.testing;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.context.ActiveProfiles;

import static org.junit.jupiter.api.Assertions.assertNotNull;

@SpringBootTest
@ActiveProfiles("test")
class BootContextTest {
    @Autowired
    private ApplicationContext context;

    @Test
    void startsWithTestProfile() {
        assertNotNull(context);
    }
}
```

**Ví dụ file `src/test/resources/application-test.yml`:**

```yaml
logging:
  level:
    root: WARN
```

`@ActiveProfiles("test")` được Spring TestContext xử lý khi tạo context; nó không ảnh hưởng đến unit test thuần JUnit không dùng Spring TestContext. Ví dụ `BootContextTest` là **test Spring context**, chỉ chạy khi dự án thực sự có Spring Boot application config và những dependency/hạ tầng mà context yêu cầu. `FeeCalculatorTest` ở phần 4 là ví dụ độc lập, không cần ứng dụng.

Có thể dùng `@TestPropertySource`, test-specific properties hoặc `@DynamicPropertySource` (khi có port động từ Testcontainers). Chọn một cách rõ ràng và kiểm tra thứ tự ưu tiên property thực tế. Tránh để hai runner cần thao tác thủ công khác nhau chỉ để test nhận ra cùng cấu hình.

### 7.2. Vì sao thêm `-Dspring.profiles.active=test` vẫn có thể lệch?

**Phân biệt tiến trình:**

- `./gradlew -Dsome.key=value test` có thể đặt system property cho **Gradle JVM**, trong khi Gradle test thường chạy ở **forked JVM**. Đừng mặc định giá trị sẽ được chuyển sang test nếu build task không cấu hình truyền nó.
- IDE JUnit runner có trường **VM options** riêng. Một giá trị đặt trong Gradle task `systemProperty(...)` không mặc nhiên có trong IDE runner.
- Maven Surefire cũng quản lý test execution và system properties theo cấu hình plugin. Cần kiểm tra cách plugin truyền property sang test JVM.

**Cấu hình Gradle minh họa** khi có lý do thực sự cần truyền một property vào test JVM:

```groovy
tasks.named('test', Test) {
    useJUnitPlatform()
    systemProperty 'app.test.flag', 'enabled'
}
```

Test nào phụ thuộc property đó sẽ nhận giá trị khi chạy qua **Gradle task**. Khi chạy trực tiếp bằng IDE JUnit runner, hãy cấu hình VM option tương đương hoặc chuyển tiền điều kiện đó về test source/config phù hợp. Với Spring integration tests, `@ActiveProfiles("test")` thường giúp thống nhất lựa chọn profile mà không phụ thuộc lệnh khởi chạy.

Không đưa password/token thực vào `application-test.yml` đã commit. Dùng tài khoản test giả lập, secret CI và thiết lập cục bộ có kiểm soát khi thật sự phải kết nối ngoài.

### 7.3. Những thứ cần ghi lại khi hai môi trường cho kết quả khác nhau

| Thành phần | Ví dụ khác biệt | Cách thu hẹp |
|---|---|---|
| Java runtime | IDE dùng JDK 21, terminal dùng JDK 17 | So Project SDK, Gradle JVM, `java -version`, `./gradlew --version` và toolchain |
| Profile | IDE bật `test`, CLI dùng profile mặc định | Gắn `@ActiveProfiles` vào Spring test hoặc đồng bộ cấu hình runner |
| JVM properties | Gradle test task thêm `-Dapp.test.flag`, IDE không có | Đọc VM options và cấu hình `Test` task |
| Environment | IDE có biến môi trường cục bộ, CI thiếu | So tên/giá trị cần thiết, dùng cấu hình test an toàn |
| Working directory | Code đọc file bằng đường dẫn tương đối | Ưu tiên resource trên classpath; kiểm tra `user.dir` khi cần |
| Classpath | IDE chưa reload dependency hoặc tự thêm JAR | Sync build, dùng dependencies từ Gradle/Maven |
| Encoding/timezone | Default charset hoặc zone khác | Dùng UTF-8/zone rõ và clock kiểm soát được |
| Spring resources | `application-test.yml` không có trên test classpath | Đặt đúng `src/test/resources` và kiểm tra resource processing |
| Testcontainers | Docker chạy được ở IDE nhưng terminal/CI không kết nối | Kiểm tra Docker engine/socket/permissions và hạ tầng test |
| Parallel/fork | CLI chạy nhiều fork; IDE chạy một test đơn lẻ | So cấu hình concurrency, loại bỏ state chia sẻ |

**Đường dẫn resource:** khi đọc file thuộc `src/test/resources`, ưu tiên `getResourceAsStream(...)` hoặc Spring resource abstraction thay vì dùng `new File("src/test/resources/...")`. Đường dẫn tương đối phụ thuộc working directory, nên rất dễ khác giữa IDE, Gradle, Maven, và container.

## 8. Thử lại cùng một phạm vi để tìm chênh lệch có thật

Một quy trình thực hành cho lớp `FeeCalculatorTest`:

1. **Đóng băng đầu vào:** save tất cả file, ghi rõ commit/branch, JDK đã chọn, phiên bản wrapper; reload dependency trong IDE.
2. **Chạy qua IDE:** chọn **cả lớp**; xác nhận chính xác 3 test được chạy và pass. Ghi lại runner: IntelliJ JUnit/Gradle, Eclipse JUnit hoặc VS Code Java Test Runner.
3. **Chạy qua wrapper:** dùng lệnh lọc đúng lớp và module. Với Gradle, nếu muốn kiểm chứng thực thi mới, thêm `--rerun-tasks`; với Maven, xem Surefire summary/report.
4. **Đối chiếu kết quả:** cùng danh sách test, cùng assertion, cùng trạng thái pass/fail/skip. Thời gian có thể khác vì JVM startup, incremental compile hoặc context cache.
5. **Nếu có lệch:** so theo thứ tự *scope/runner → JDK/toolchain → classpath/dependency → profile/properties → resource/data/DB/Docker → parallel/timing*. Mỗi lần chỉ thay một nguyên nhân để biết thay đổi nào có tác dụng.
6. **Xác nhận cuối:** chạy toàn bộ test task hoặc pipeline đã được dự án/CI công nhận, không dừng ở kết quả của một phương thức đã lọc.

Với test Spring context, tiến hành tương tự nhưng cần xác minh thêm `@SpringBootTest` tìm đúng cấu hình ứng dụng, những bean cần thiết được tạo và test resources/profile được nạp. Chỉ thêm test tích hợp vào bài thực hành sau khi test thuần JUnit chạy đồng nhất, vì như vậy tránh trộn lỗi IDE/CLI với lỗi database hoặc application startup.

### 8.1. Cách chọn runner theo mục tiêu

| Mục tiêu | Lựa chọn phù hợp | Cần xác minh |
|---|---|---|
| Debug nhanh một assertion | IDE JUnit runner | Classpath/VM args đủ cho test; không bỏ qua setup từ build |
| Tái hiện lỗi xảy ra trong CI Gradle | Gradle runner hoặc `./gradlew ...` | Đúng task path, test filter, JVM, properties |
| Tái hiện lỗi xảy ra trong CI Maven | Maven goal qua wrapper | Surefire/Failsafe, profile, test selection |
| Kiểm tra kết hợp Spring + DB | Task/goal integration test của dự án | Profile, container, schema/migration, cleanup |
| Kiểm tra toàn suite trước khi giao | Wrapper với đúng task/goal CI | Test report, skipped tests, pipeline status |

**Không dùng nhanh/chậm làm bằng chứng đúng/sai:** IDE có thể nhanh hơn nhờ incremental compilation; Gradle có thể nhanh hơn nhờ cache; Maven có thể chạy với fork khác. Sự khác biệt thời gian chỉ là tín hiệu cần đo và lý giải, không phải kết luận về hành vi.

## 9. Chẩn đoán các tình huống thường gặp

### 9.1. IDE tìm thấy test, terminal báo “No tests found” hoặc chạy 0 test

Kiểm tra lần lượt:

- Import `org.junit.jupiter.api.Test` có đúng không? Có vô tình dùng `org.junit.Test` của JUnit 4 mà không có engine tương thích không?
- `spring-boot-starter-test` hoặc JUnit Jupiter dependencies có thuộc **test runtime classpath** của build tool không?
- Gradle đã bật `useJUnitPlatform()` cho đúng test task chưa? Maven Surefire có phiên bản/provider tương thích không?
- File đang ở `src/test/java` hay source set thực sự được task/goal chọn?
- Test class/method filter `--tests` hoặc `-Dtest` có match đúng tên và module?
- Test có `@Disabled`, tag filter hoặc điều kiện thực thi khiến nó bị bỏ qua không?

**Đừng sửa bằng cách đổi tên test tùy tiện** trước khi đọc thông báo discovery và report; xác định cơ chế bị thiếu để các test còn lại cũng được chạy đúng.

### 9.2. IDE xanh, Gradle/Maven đỏ

Những nguyên nhân thường gặp:

- IDE JUnit runner bỏ qua cấu hình trong task/plugin (JVM args, system properties, generated resources, test filters).
- Build tool dùng JDK/toolchain khác, hoặc dependency/version khác với classpath IDE đã cache.
- Chạy full suite trên dòng lệnh làm lộ test phụ thuộc thứ tự/chia sẻ trạng thái; chạy đơn lẻ từ IDE che giấu lỗi.
- Dòng lệnh chạy integration tests, container hoặc môi trường mà IDE chưa chạy.
- CI/Linux có phân biệt chữ hoa–thường trong đường dẫn mà máy phát triển không bộc lộ.

**Cách xử lý:** tái hiện đúng lớp bằng wrapper, so runner/context/parameters, rồi sửa build configuration hoặc thiết kế test. Nếu suite chạy lẻ xanh nhưng chạy cùng nhau đỏ, kiểm tra state/database/cache chia sẻ; đừng mặc định tăng timeout.

### 9.3. Terminal xanh, IDE đỏ hoặc IDE không thấy test

Kiểm tra IDE đã import project từ build file và reload đúng chưa; test source root đã nhận diện chưa; JDK và dependencies có hợp không; workspace có chọn nhầm submodule không; Java language server/index có hoàn tất không. Nếu Gradle chạy xanh còn IDE built-in runner lỗi classpath, chuyển IntelliJ sang Gradle runner hoặc chạy Gradle task để xác minh rồi mới sửa cấu hình IDE.

### 9.4. `Failed to load ApplicationContext`

Thông báo này cho biết **Spring context startup không thành công**, không phải tự động là lỗi JUnit/IDE. Đọc **root cause đầu tiên có ý nghĩa** trong stacktrace:

- Có đúng `@SpringBootApplication`/`@SpringBootConfiguration` được phát hiện từ package của test?
- Profile test có nạp đúng cấu hình và các placeholder bắt buộc không?
- Database URL, migration, bean injection, port hoặc dependency bên ngoài có hợp lệ?
- Nếu dùng Testcontainers, Docker có chạy và dữ liệu kết nối động được truyền qua `@DynamicPropertySource` hay cơ chế Spring Boot hỗ trợ tương ứng không?
- IDE và CLI có chạy cùng test class, cùng active profiles và cùng source resources không?

Với `@WebMvcTest` hoặc `@DataJpaTest`, context khác với `@SpringBootTest`; đừng thay một annotation chỉ để làm test xanh nếu phạm vi kiểm thử yêu cầu loại context ban đầu.

### 9.5. Test chỉ thất bại trong full suite hoặc khi chạy song song

Xem có test nào dùng static mutable state, singleton cache, DB dùng chung, đường dẫn file trùng, cổng cố định, thay đổi timezone/global properties hoặc thao tác bất đồng bộ không chờ điều kiện. Một lần Run IDE thường chọn một class/method, còn CLI có thể chạy toàn suite hoặc nhiều fork; sự khác biệt phơi bày lỗi độc lập của test. Sửa fixture/cô lập tài nguyên; chỉ bật parallel khi đã đủ điều kiện, không cố định thứ tự để che lỗi.

### 9.6. Build success nhưng không có bằng chứng test mới chạy

Với Gradle, nếu `test` là `UP-TO-DATE` hoặc `FROM-CACHE` thì không nên báo “vừa chạy lại mọi test”; dùng `--rerun-tasks` khi mục tiêu là xác thực thực thi mới. Với Maven hoặc Gradle, luôn đọc test count và report; một build không lỗi cũng có thể có test bị exclude, skip hoặc nằm trong task/goal khác. Với Maven, kiểm tra có tham số skip tests hay không.

### 9.7. Debugger chạy nhưng breakpoint không dừng

Xác định JVM thật đang chạy test. Nếu IDE debug JUnit runner, debugger thường được gắn sẵn; nếu chạy Gradle/Maven từ terminal, debugger của IDE không tự động gắn vào test worker JVM. Với Gradle `Test` task, tùy phiên bản có thể dùng lựa chọn `--debug-jvm` để đợi IDE attach debugger đến test process; cần đọc thông báo port và kết nối đúng JVM. Cũng kiểm tra class đã được build lại và breakpoint có nằm trên đường code được test gọi không.

## 10. Thiết lập quy trình nhất quán cho nhóm và CI

Một dự án Spring Boot nên công bố ít nhất:

1. **Wrapper chuẩn:** commit các file Gradle/Maven Wrapper hợp lệ; dùng wrapper trong tài liệu, IDE import và CI.
2. **Phiên bản Java:** khai báo release/toolchain hoặc compiler configuration; CI cấp JDK đúng, IDE chọn tương thích.
3. **Test dependencies và runner:** khai báo trong build file; JUnit Platform và Surefire/Failsafe được cấu hình nhất quán.
4. **Các task/goal chính thức:** nói rõ lệnh chạy unit tests, integration tests, và khi nào chạy full suite; multi-module phải ghi rõ task path/module selection.
5. **Config test độc lập:** ưu tiên `@ActiveProfiles`, test resources và fixture rõ; không phụ thuộc những VM args bí mật chỉ có trên máy một cá nhân.
6. **Report và fail policy:** CI đọc test reports, fail khi test lỗi, phân biệt skip/disabled/không có test; không coi “0 tests” là chiến thắng.
7. **Hạ tầng test:** quy định Docker/DB/test services, seed/cleanup và timeout cho integration tests.
8. **Hướng dẫn IDE:** ghi rõ chọn runner nào để tái hiện CI; runner IDE có thể dùng cho debug nhanh nhưng không thay thế kiểm chứng cuối.

**Ví dụ chính sách thực hành:** với dự án Gradle, lập trình viên có thể bấm Run trên `FeeCalculatorTest` để nhận phản hồi nhanh; trước khi tạo pull request, chạy `./gradlew test` (hoặc task được dự án quy định). CI cũng dùng wrapper cùng cấu hình và lưu report. Nếu cần kiểm tra lỗi ngẫu nhiên, ép chạy lại bằng `--rerun-tasks` thay vì tin vào cache.

## 11. Bảng kiểm tự đánh giá

Trước khi xác nhận “cấu hình IDE và dòng lệnh đã khớp”, hãy kiểm tra:

- [ ] Dự án được import từ Gradle/Maven build file, và IDE đã sync dependencies/test source.
- [ ] JDK/Java toolchain phù hợp; hiểu sự khác biệt giữa Gradle JVM và test JVM.
- [ ] `spring-boot-starter-test`/JUnit Jupiter và build test runner được khai báo trong dự án.
- [ ] Biết IDE đang chạy JUnit trực tiếp hay delegate sang Gradle/Maven.
- [ ] Chạy được cùng một lớp và phương thức test ở IDE và wrapper.
- [ ] Hai đường chạy khám phá đúng test count; không nhầm skip/cache với lần thực thi mới.
- [ ] Đối chiếu đúng module, task/goal, test filter, package và source set.
- [ ] Spring integration test dùng đúng active profile, test resources và context configuration.
- [ ] Không có khác biệt không kiểm soát về environment, JVM properties, working directory, timezone hoặc Docker/DB.
- [ ] Có thể tìm test report và lỗi gốc khi fail ở từng đường chạy.
- [ ] CI thực thi pipeline kiểm thử đã thống nhất và lưu kết quả để truy vết.

**Kết luận kỹ thuật:** IDE là công cụ tuyệt vời để viết, chạy chọn lọc và debug test; **build tool với wrapper và cấu hình dự án là điểm đối chiếu có thể tái lập**. Chỉ khi cùng đầu vào và cùng phạm vi test cho cùng kết quả qua cả hai đường chạy, ta mới có cơ sở tin rằng môi trường phát triển không che giấu lỗi của bộ kiểm thử.

## Tài liệu tham khảo

- [Spring Boot Reference — Testing](https://docs.spring.io/spring-boot/reference/testing/) — test starter, JUnit và khả năng hỗ trợ test của Spring Boot.
- [Spring Boot Reference — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html) — `@SpringBootTest`, cấu hình và test slices.
- [Gradle User Manual — Testing in Java & JVM Projects](https://docs.gradle.org/current/userguide/java_testing.html) — Test tasks, JUnit Platform và filtering.
- [Gradle User Manual — Command-Line Interface](https://docs.gradle.org/current/userguide/command_line_interface.html) — Wrapper task execution, `--rerun-tasks` và báo cáo.
- [Apache Maven Surefire — Running a Single Test](https://maven.apache.org/surefire/maven-surefire-plugin/examples/single-test.html) — `-Dtest` và lọc phương thức.
- [IntelliJ IDEA — Testing in Gradle](https://www.jetbrains.com/help/idea/work-with-tests-in-gradle.html) — lựa chọn Gradle runner/IntelliJ IDEA runner.
- [Visual Studio Code — Testing Java](https://code.visualstudio.com/docs/java/java-testing) — Java Test Runner, Test Explorer và test configuration.
- [JUnit User Guide](https://docs.junit.org/current/user-guide/) — JUnit Jupiter, cấu hình khám phá và vòng đời test.