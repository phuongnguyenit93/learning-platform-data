# Thực hành tổng hợp: Nâng cấp Maven hoặc plugin và kiểm chứng tương thích

## 1. Bài toán thực tế và kết quả phải bàn giao

Một dự án Java chạy ổn định với Maven 3.9.x và Maven Surefire/Failsafe 3.5.4. Nhóm muốn nâng Maven hoặc plugin nhưng phải **chứng minh không làm thay đổi hành vi sản phẩm, không bỏ sót kiểm thử và không phá build ở CI**.

Chỉ đổi `<version>` rồi thấy dòng `BUILD SUCCESS` chưa đủ: có thể unit tests bị skip, integration tests không chạy, plugin version mới chưa được Maven sử dụng, CI chạy một bản Maven khác hoặc JAR chạy thất bại sau packaging. Một nâng cấp có chất lượng cần có **baseline trước thay đổi**, **một biến thay đổi có kiểm soát**, **test evidence**, **so sánh kết quả**, và **kế hoạch quay lui**.

Trong lab, bạn thực hiện hai kịch bản **độc lập**:

- **Kịch bản A (bài thực hành chính):** nâng **cặp plugin kiểm thử Surefire và Failsafe 3.5.4 → 3.5.5** thông qua một Maven property dùng chung. Đây là một thay đổi nhất quán trong cùng test-runner family; không đồng thời nâng JUnit, Java hay Maven core. 3.5.5 là bản có thật và yêu cầu Maven ≥3.6.3, Java ≥8 theo Apache Maven Surefire Plugin.
- **Kịch bản B (mở rộng):** nâng **Maven Wrapper 3.9.12 → 3.9.16**, giữ nguyên versions của project/plugins, rồi so sánh lại. Đây là hai bản Maven 3.9 đã phát hành; không được coi là “phiên bản mới nhất ở mọi thời điểm”.

Một lựa chọn **sandbox riêng** là thử Maven 4.0.0-rc-7 theo hướng dẫn migration chính thức. Tại thời điểm tham khảo tháng 11/2026, Maven 4 vẫn là nhánh release candidate, yêu cầu JDK 17 để chạy; đừng biến thí nghiệm này thành bước release chính khi chưa có phê duyệt.

### Kết quả học tập

Hoàn thành bài, bạn có thể:

1. Phân biệt tương thích **Maven core ↔ plugin**, **Maven JVM/JDK ↔ plugin**, **project bytecode ↔ runtime** và **plugin dependencies ↔ application dependencies**.
2. Thu baseline bằng `mvn -version`/`./mvnw -version`, `help:effective-pom`, active profiles, plugin execution logs và test reports.
3. Pin Maven Wrapper, plugins và Java release target để lệnh chạy trên developer machine lẫn CI có thể tái lập.
4. Tạo được Java 17 project có **unit tests, integration test và executable JAR**.
5. Chạy `clean verify` và nhận biết Surefire chạy unit tests, Failsafe chạy integration tests ở các phases phù hợp.
6. Thử plugin version mới bằng user property mà chưa sửa POM và chứng minh effective/executed version đúng như mong đợi.
7. Thay một property trong POM sau khi thử nghiệm pass, kiểm tra `git diff` và tái chạy toàn bộ quality gate.
8. Tạo compatibility matrix giữa JDK 17/21 và test-runner versions, không nhầm “matrix pass” với “production approved”.
9. Chẩn đoán lỗi `UnsupportedClassVersionError`, `NoSuchMethodError`, JUnit provider mismatch, forked JVM failures, test discovery và plugin resolution.
10. Kiểm các Maven core/build extensions và custom plugins trước khi thử Maven 4.
11. Ghi báo cáo trước–sau có con số test thực, stdout cố định, dependencies, hash/artifact metadata và link CI job.
12. Rollback bằng Git/Wrapper đúng scope, không xóa cache hoặc disable tests để “lấy màu xanh”.

### Điều kiện pass của bài thực hành

Bản nâng cấp được chấp nhận khi **cùng source code và cùng môi trường trong phạm vi so sánh**:

- Lệnh Maven xác nhận version đích thật được dùng.
- `mvn clean verify` exit code **0** mà **không** dùng `-DskipTests` hoặc `-Dmaven.test.skip=true`.
- Đúng **7 unit tests** và **1 integration test** được phát hiện/chạy, failures = 0, errors = 0, skipped = 0.
- Executable JAR chạy đúng stdout: `TOTAL=33.75`.
- Surefire/Failsafe reports tồn tại và được đọc, không dựa duy nhất vào dòng `BUILD SUCCESS`.
- Project `pom.xml` chỉ có thay đổi được duyệt; POM effective/CLI logs cho thấy plugin versions đích.
- CI chạy đủ job bắt buộc; không có cảnh báo regression hay release artifact khác thường chưa giải thích.
- Đã ghi rollback path và quyết định **GO / NO-GO**.

**Quan trọng:** các kết quả ghi trong README là **kỳ vọng từ mã mẫu**, không phải tuyên bố tác giả đã thực thi `mvn` trên máy của bạn. Hãy tạo và chạy project để thu actual evidence.

---

## 2. Bốn tầng tương thích phải phân biệt

~~~text
CLI / Wrapper
      |
      v
Maven core 3.9.x (JVM chạy Maven)
      |
      +--> Maven plugins / build extensions / core extensions
      |       |
      |       +--> Compiler Plugin (compile bytecode)
      |       +--> Surefire Plugin (unit tests)
      |       +--> Failsafe Plugin (integration tests)
      |       +--> Jar Plugin (package application)
      |
      +--> Project compile/test/runtime classpaths
                 |
                 +--> JUnit Jupiter 5.11.4 (test scope)
                 +--> Java 17 application classes
                 +--> Runtime artifact
~~~

### 2.1. Maven core ↔ Maven plugin

Maven plugin là phần mềm có versions và minimum Maven requirements riêng. Một bản Compiler/Surefire Plugin mới không nhất thiết chạy được trên Maven cũ; plugin có thể dựa vào Maven API mà bản cũ thiếu. Kiểm **plugin-info/System Requirements** của **chính version định nâng**.

Với kịch bản A:

- Surefire Plugin 3.5.4 và 3.5.5 đều nằm trong dòng plugin 3.5.x.
- Trang Plugin Details của Surefire 3.5.5 ghi minimum Maven **3.6.3** và JDK **8**. Do đó Maven 3.9.x/JDK17 đáp ứng các mức tối thiểu ấy; **không** có nghĩa toàn bộ cấu hình của bạn chắc chắn tương thích.
- Failsafe cùng họ plugin test execution; khi dùng cùng property, kiểm version và goal log **riêng** cho Failsafe.

### 2.2. JVM chạy Maven ↔ plugin bytecode

`mvn -version` cho Java runtime thực Maven đang dùng. Nếu một plugin được compile cho Java version cao hơn JVM ấy, bạn có thể gặp `UnsupportedClassVersionError` dù project khai `maven.compiler.release=17`.

Maven 4.0.x yêu cầu chạy trên **JDK 17+**, nhưng project vẫn có thể target Java thấp hơn nếu plugin/toolchain hỗ trợ. JDK của Maven runtime và `--release` không phải một biến duy nhất.

### 2.3. Compiler target ↔ runtime ứng dụng

`maven.compiler.release=17` yêu cầu Compiler Plugin dùng `--release 17` phù hợp (với JDK ≥17) để giới hạn API/bytecode. Khi deploy trên Java17, cần bảo đảm classfile major version và mọi runtime dependency tương thích Java17.

Để xem class-file version:

~~~bash
javap -verbose -classpath target/classes vn.example.upgrade.App
~~~

Tìm `major version: 61` cho Java17 class. Đây là một kiểm tra **bytecode**, không phải bằng chứng JUnit tests đã chạy.

### 2.4. Plugin dependencies ↔ application dependencies

Plugin có class realm riêng với plugin dependencies. `mvn dependency:tree` mô tả project dependency graph, không phải mọi JAR trong plugin realm.

Nâng Surefire có thể thay test provider/fork/classloader behavior mà **không** đổi JUnit Jupiter version trong `<dependencies>`. Ngược lại nâng JUnit có thể ảnh hưởng tests dù Surefire giữ nguyên. Vì thế lab giữ JUnit version cố định khi so 3.5.4 → 3.5.5.

---

## 3. Quy trình an toàn gồm sáu cổng kiểm tra

| Gate | Hành động | Minh chứng phải lưu | Được đi tiếp khi |
| --- | --- | --- | --- |
| G0 — Scope | Chọn một trục nâng cấp, lập risk list | Ticket/PR, version current/target | Goal rõ, rollback rõ |
| G1 — Baseline | Build sạch với version cũ | Maven/JDK, plugin versions, XML reports, JAR stdout | Baseline PASS |
| G2 — Candidate | Thử version mới qua CLI hoặc branch | Effective POM, plugin execution log | Đúng artifact đích |
| G3 — Verification | Run full `clean verify` + JAR smoke test | Unit/IT counts, exit codes, artifacts | Không regression |
| G4 — Matrix | Test JDK/OS/profile/modules cần hỗ trợ | CI run IDs và failed logs | Required jobs PASS |
| G5 — Promote | Pin version trong source, review, merge | Git diff, review, rollback tag/commit | GO được duyệt |

Nếu G1 đã fail, nâng plugin có thể **che** hoặc **làm khác** lỗi cũ; không gọi candidate PASS khi không có baseline có thể so sánh.

### 3.1. Chọn một thay đổi tại một thời điểm

Không gộp Maven core 3.9.12→3.9.16, Surefire 3.5.4→3.5.5, JUnit 5→6 và JDK17→21 trong cùng một PR khi mục tiêu là xác định compatibility của một bước nâng cấp.

Trường hợp nâng đồng thời Surefire và Failsafe **cùng version property** được xem là **một thay đổi của test-runner family** trong bài này. Nếu ứng dụng chỉ dùng Surefire, bạn có thể thử nâng riêng Surefire; nếu dùng Failsafe và có providers/plugins chung, việc giữ chúng cùng release line giúp giản lược phạm vi đối chiếu nhưng không bỏ kiểm chứng.

---

## 4. Môi trường và cấu trúc project

Yêu cầu: Apache Maven **3.9.x**, JDK **17+**, truy cập Maven artifact repository được tổ chức tin cậy, Git (nếu dùng version control). Java source không yêu cầu external application dependencies ngoài test-only JUnit.

Tạo project:

~~~text
maven-upgrade-lab/
├── pom.xml
└── src/
    ├── main/java/vn/example/upgrade/
    │   ├── Checkout.java
    │   └── App.java
    └── test/java/vn/example/upgrade/
        ├── CheckoutTest.java
        └── AppIT.java
~~~

**Năm file bắt buộc**: một POM, hai classes chính, một unit-test class, một integration-test class.

Wrapper files, CI workflow và báo cáo chỉ được bổ sung **ở các bước sau**. Bạn không cần Maven Wrapper được cài sẵn để build năm file này.

---

## 5. pom.xml baseline đầy đủ

File `maven-upgrade-lab/pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>vn.example</groupId>
    <artifactId>maven-upgrade-lab</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <junit.jupiter.version>5.11.4</junit.jupiter.version>
        <surefire.version>3.5.4</surefire.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>${junit.jupiter.version}</version>
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
                <version>${surefire.version}</version>
                <configuration>
                    <failIfNoTests>true</failIfNoTests>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-failsafe-plugin</artifactId>
                <version>${surefire.version}</version>
                <executions>
                    <execution>
                        <goals>
                            <goal>integration-test</goal>
                            <goal>verify</goal>
                        </goals>
                    </execution>
                </executions>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
                <configuration>
                    <archive>
                        <manifest>
                            <mainClass>vn.example.upgrade.App</mainClass>
                        </manifest>
                    </archive>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-enforcer-plugin</artifactId>
                <version>3.6.3</version>
                <executions>
                    <execution>
                        <id>check-maven-and-java</id>
                        <goals>
                            <goal>enforce</goal>
                        </goals>
                        <configuration>
                            <rules>
                                <requireMavenVersion>
                                    <version>[3.9,4.0)</version>
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
                <artifactId>maven-help-plugin</artifactId>
                <version>3.5.2</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 5.1. Vì sao dùng property cho hai test plugins?

Cả Surefire và Failsafe đọc `${surefire.version}` (sau khi POM được lưu, nội dung thật phải là cú pháp Maven property với ký tự dollar). Điều này cho phép thử:

~~~bash
mvn "-Dsurefire.version=3.5.5" clean verify
~~~

Nếu CLI user property thắng model interpolation theo Maven invocation, effective POM sẽ dùng 3.5.5 cho cả hai test plugins. **Phải xác minh bằng effective POM và log**, không chỉ tin vào lệnh `-D` đã được gõ.

### 5.2. Vì sao pin các plugin còn lại?

Clean/Resources/Compiler/Jar/Enforcer được cố định để thay đổi test plugin không đồng thời đổi build tools khác. Các plugins có release cycle độc lập, nên version trong POM là **fixture** chứ không phải guarantee chúng đều mới nhất.

### 5.3. Vì sao đặt Maven/Java Enforcer?

`requireMavenVersion=[3.9,4.0)` giữ thử nghiệm chính trong Maven3.9.x; `requireJavaVersion=[17,)` yêu cầu Maven JVM Java17+. Khi thử Maven4, rule cố ý fail: phải chỉnh compatibility policy trên **nhánh riêng được duyệt**, không dùng skip enforcer trên release CI để lách gate.

### 5.4. Vì sao có Failsafe?

Surefire mặc định phát hiện các unit tests tên `*Test.java`. Failsafe mặc định phát hiện integration tests như `*IT.java` và có hai goals quan trọng: `failsafe:integration-test` để chạy và `failsafe:verify` để báo trạng thái cuối. Maven lifecycle `verify` bao gồm chúng khi plugin được bind.

**Không chỉ gọi `mvn integration-test` rồi kết luận thành công**: với Failsafe, goal `verify` mới hoàn tất việc đánh giá test results và fail build phù hợp.

---

## 6. Checkout.java: business logic độc lập, test được

File `src/main/java/vn/example/upgrade/Checkout.java`:

~~~java
package vn.example.upgrade;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Objects;

public final class Checkout {
    private Checkout() {
    }

    public static BigDecimal total(
            BigDecimal unitPrice,
            int quantity,
            BigDecimal discountRate) {

        Objects.requireNonNull(unitPrice, "unitPrice");
        Objects.requireNonNull(discountRate, "discountRate");

        if (unitPrice.signum() < 0) {
            throw new IllegalArgumentException("unitPrice must be nonnegative");
        }
        if (quantity < 0) {
            throw new IllegalArgumentException("quantity must be nonnegative");
        }
        if (discountRate.compareTo(BigDecimal.ZERO) < 0
                || discountRate.compareTo(BigDecimal.ONE) > 0) {
            throw new IllegalArgumentException(
                    "discountRate must be between 0 and 1");
        }

        BigDecimal gross =
                unitPrice.multiply(BigDecimal.valueOf(quantity));
        BigDecimal payable = gross.multiply(
                BigDecimal.ONE.subtract(discountRate));
        return payable.setScale(2, RoundingMode.HALF_UP);
    }
}
~~~

**Quy tắc của demo:**

- Không nhận giá hoặc số lượng âm.
- Discount là tỷ lệ từ 0 đến 1, kể cả biên.
- Tính với `BigDecimal`, không dùng `double` cho tiền.
- Chỉ làm tròn **một lần cuối** với `HALF_UP` về hai chữ số thập phân.
- `total(12.50, 3, 0.10) = 33.75`.
- `total(1.005, 1, 0) = 1.01`.
- `total(4.99, 0, 0) = 0.00`.

Bài không xử lý thuế, tiền tệ nhiều loại hoặc quy tắc làm tròn ngân hàng của sản phẩm thực; đây là fixture test deterministic để **đo compatibility**.

---

## 7. App.java: smoke test đầu ra của JAR

File `src/main/java/vn/example/upgrade/App.java`:

~~~java
package vn.example.upgrade;

import java.math.BigDecimal;

public final class App {
    private App() {
    }

    public static String message() {
        BigDecimal total = Checkout.total(
                new BigDecimal("12.50"),
                3,
                new BigDecimal("0.10"));
        return "TOTAL=" + total.toPlainString();
    }

    public static void main(String[] args) {
        System.out.println(message());
    }
}
~~~

Khi compile/package thành công, chạy JAR:

~~~bash
java -jar target/maven-upgrade-lab-1.0.0.jar
~~~

**Stdout chính xác từ App.main**, một dòng:

~~~text
TOTAL=33.75
~~~

Dòng có newline cuối do `println`. POM dùng Maven JAR Plugin gắn `Main-Class: vn.example.upgrade.App`. App chỉ dùng Java standard library; không cần ứng dụng runtime JAR phụ.

Đây là signal độc lập với test provider: nếu unit tests pass nhưng `java -jar` fail, nâng cấp build chưa đủ.

---

## 8. CheckoutTest.java: bảy unit tests phát hiện bằng Surefire

File `src/test/java/vn/example/upgrade/CheckoutTest.java`:

~~~java
package vn.example.upgrade;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;

class CheckoutTest {
    private static BigDecimal money(String value) {
        return new BigDecimal(value);
    }

    @Test
    void appliesTenPercentDiscount() {
        assertEquals(money("33.75"), Checkout.total(
                money("12.50"), 3, money("0.10")));
    }

    @Test
    void roundsHalfUpAtTwoDecimals() {
        assertEquals(money("1.01"), Checkout.total(
                money("1.005"), 1, money("0")));
    }

    @Test
    void zeroQuantityReturnsZeroWithTwoDecimals() {
        assertEquals(money("0.00"), Checkout.total(
                money("4.99"), 0, money("0")));
    }

    @Test
    void rejectsNegativePrice() {
        assertThrows(IllegalArgumentException.class,
                () -> Checkout.total(
                        money("-0.01"), 1, money("0")));
    }

    @Test
    void rejectsNegativeQuantity() {
        assertThrows(IllegalArgumentException.class,
                () -> Checkout.total(
                        money("5.00"), -1, money("0")));
    }

    @Test
    void rejectsOutOfRangeDiscount() {
        assertThrows(IllegalArgumentException.class,
                () -> Checkout.total(
                        money("5.00"), 1, money("1.01")));
    }

    @Test
    void rejectsNullPrice() {
        assertThrows(NullPointerException.class,
                () -> Checkout.total(null, 1, money("0")));
    }
}
~~~

Có **đúng bảy phương thức `@Test`**. Test naming `CheckoutTest` phù hợp Surefire default include pattern. Chúng không dùng clock, network hoặc global state; tiện để so hai test plugin versions.

**Chú ý:** `BigDecimal.equals` so cả scale; các assertions mong trả về scale 2 vì `setScale(2, HALF_UP)`. Nếu bạn thay logic sang `stripTrailingZeros`, kết quả số học có thể vẫn bằng nhưng tests sẽ fail. Đó là regression có ý nghĩa với contract của demo.

---

## 9. AppIT.java: integration test kiểm packaged JAR thực sự chạy

File `src/test/java/vn/example/upgrade/AppIT.java`:

~~~java
package vn.example.upgrade;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.junit.jupiter.api.Assertions.fail;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Locale;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;

class AppIT {
    @Test
    void packagedJarLaunchesAndPrintsExpectedResult() throws Exception {
        Path jar = Path.of(
                "target", "maven-upgrade-lab-1.0.0.jar")
                .toAbsolutePath().normalize();

        assertTrue(Files.isRegularFile(jar),
                "JAR must exist after package phase");

        boolean windows = System.getProperty("os.name")
                .toLowerCase(Locale.ROOT).contains("win");
        String binary = windows ? "java.exe" : "java";
        Path executable = Path.of(
                System.getProperty("java.home"), "bin", binary);

        Process child = new ProcessBuilder(
                executable.toString(),
                "-jar",
                jar.toString())
                .redirectErrorStream(true)
                .start();

        boolean finished = child.waitFor(15, TimeUnit.SECONDS);
        if (!finished) {
            child.destroyForcibly();
            fail("Java process did not finish within 15 seconds");
        }

        String output = new String(
                child.getInputStream().readAllBytes(),
                StandardCharsets.UTF_8).strip();

        assertEquals(0, child.exitValue(), output);
        assertEquals("TOTAL=33.75", output);
    }
}
~~~

**Tại sao là integration test thay vì unit test?**

Test này không chỉ gọi `App.message()` trong cùng JVM; nó:

1. Kiểm JAR đã tồn tại sau `package`.
2. Dùng Java executable của JVM test hiện tại tạo **process con**.
3. Gọi `java -jar` thật.
4. Kiểm exit code 0 và toàn bộ stdout (sau `strip()`).
5. Fail khi process treo quá 15 giây.

Tên `AppIT` phù hợp default Failsafe include patterns và **không** thuộc default Surefire `*Test` pattern. Với `mvn clean verify`, Maven JAR Plugin đóng gói ở `package` trước khi Failsafe integration-test goal chạy.

Nếu môi trường CI không cho phép spawn subprocess, đừng đổi test thành skip rồi công bố tương thích: ghi rõ restriction, điều chỉnh runner/policy hoặc thiết kế một IT phù hợp mà vẫn xác thực packaging.

**Không nên gọi `mvn test` để xác minh AppIT:** phase `test` chưa tới Failsafe integration-test; yêu cầu `verify` mới bao phủ tất cả.

---

## 10. Chạy baseline trước khi nâng

Từ thư mục root chứa POM, chạy:

~~~bash
mvn -version
java -version
javac -version
mvn -B -ntp clean verify
~~~

Nếu Maven3.9.x, JDK17+, repositories và môi trường cho phép ProcessBuilder, dự kiến:

~~~text
Tests run: 7, Failures: 0, Errors: 0, Skipped: 0
Tests run: 1, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
~~~

Các dòng chỉ là **mẫu kết quả hai test plugins**, không phải nguyên văn toàn bộ build log. Chúng có thể được in cùng nhiều lines khác; kiểm tên test classes và reports để biết **7 unit + 1 integration**.

Tiếp tục:

~~~bash
java -jar target/maven-upgrade-lab-1.0.0.jar
~~~

Stdout kỳ vọng:

~~~text
TOTAL=33.75
~~~

### 10.1. Xem reports thay vì chỉ nhìn console

Surefire:

~~~text
target/surefire-reports/
    TEST-vn.example.upgrade.CheckoutTest.xml
    vn.example.upgrade.CheckoutTest.txt
~~~

Failsafe:

~~~text
target/failsafe-reports/
    TEST-vn.example.upgrade.AppIT.xml
    vn.example.upgrade.AppIT.txt
    failsafe-summary.xml
~~~

Tên artifacts phụ thuộc plugin/report configuration, nhưng các paths trên là **default patterns dự kiến** khi plugin ghi reports. Kiểm XML attributes `tests`, `errors`, `failures`, `skipped`, không chỉ dòng success.

### 10.2. Ghi baseline vào một bảng

| Field | Baseline expected | Evidence |
| --- | --- | --- |
| Maven runtime | 3.9.x thực tế | `mvn -version` |
| Maven JVM | JDK17+ thực tế | Maven version output |
| Surefire | 3.5.4 | POM property, execution log |
| Failsafe | 3.5.4 | POM property, execution log |
| JUnit Jupiter | 5.11.4 | POM/effective test dependencies |
| Compiler | 3.14.1 | POM, log |
| Java target | 17 | `release`, `javap` |
| Unit tests | 7 / 0 fail | Surefire XML |
| Integration tests | 1 / 0 fail | Failsafe XML |
| App stdout | `TOTAL=33.75` | `java -jar` |
| CI JDK/OS | Đo thực tế | CI job |

Các giá trị plugin là của **fixture POM**, không phải kết quả đo môi trường. Khi nộp bài, thay giá trị “thực tế” bằng output từ terminal/CI.

### 10.3. Git baseline

Nếu đây là repository có Git:

~~~bash
git status --short
git switch -c lab/maven-upgrade
git add pom.xml src
git commit -m "Add reproducible Maven upgrade baseline"
~~~

Nếu chỉ là thư mục chưa `git init`, các lệnh Git sẽ fail; bạn có thể chạy `git init` và cấu hình identity theo quy trình của team. Không chạy `git push` tự động, không commit credentials.

---

## 11. Cài và pin Maven Wrapper (tùy chọn nhưng nên dùng cho team)

Dùng Maven CLI đang hoạt động **một lần** để thêm Wrapper:

~~~bash
mvn -N org.apache.maven.plugins:maven-wrapper-plugin:3.3.4:wrapper \
  "-Dmaven=3.9.12" \
  "-Dtype=only-script"
~~~

Maven Wrapper Plugin 3.3.4 có goal `wrapper:wrapper`; `-Dmaven` chọn Maven version và `-Dtype=only-script` chọn bản wrapper scripts không cần `maven-wrapper.jar`. Đây là lệnh **sửa project bằng cách tạo/cập nhật Wrapper files**; chỉ chạy trong repo/branch sandbox được phép.

Sau đó:

~~~bash
./mvnw -version
./mvnw -B -ntp clean verify
~~~

Trên Windows:

~~~powershell
mvn.cmd -N org.apache.maven.plugins:maven-wrapper-plugin:3.3.4:wrapper "-Dmaven=3.9.12" "-Dtype=only-script"
.\mvnw.cmd -version
.\mvnw.cmd -B -ntp clean verify
~~~

**Phải kiểm `./mvnw -version` thực in 3.9.12.** Đọc `.mvn/wrapper/maven-wrapper.properties` và bảo đảm distribution URL từ nguồn tin cậy. Thêm checksum SHA-256 do publisher chính thức xác nhận, không tự bịa `distributionSha256Sum`.

### 11.1. Tại sao phải dùng cùng launcher?

Nếu baseline chạy `mvn` nhưng candidate chạy `./mvnw`, bạn đã thay cả Maven distribution lẫn plugin version mà không để ý. Để so plugin A, **dùng cùng launcher** trước và sau. Để so Maven core B, **giữ nguyên plugin versions**.

### 11.2. Wrapper không tự pin JDK

Wrapper quản lý Maven distribution nhưng JDK chạy Maven vẫn do launcher/`JAVA_HOME`/CI setup cung cấp. Vì vậy lưu cả Maven và Java runtime từ wrapper output.

---

## 12. Kịch bản A: thử plugin 3.5.5 mà chưa sửa POM

Giữ nguyên Maven core/JDK và source. Dùng cùng launcher đã chọn. Nếu bạn không cài Wrapper, thay `./mvnw` bằng `mvn` **ở tất cả các lệnh**.

Chạy baseline lại qua Wrapper:

~~~bash
./mvnw -B -ntp clean verify
~~~

Rồi candidate bằng Maven user property:

~~~bash
./mvnw -B -ntp "-Dsurefire.version=3.5.5" clean verify
~~~

Trong POM, cả Surefire và Failsafe tham chiếu `${surefire.version}`. Maven user properties từ CLI được sử dụng trong model interpolation; **vẫn phải xác minh** plugin versions hiện trong effective POM và actual build logs. Nếu POM thực của bạn khai literal version trực tiếp hoặc parent/child override, cờ này có thể không thay đúng plugin.

### 12.1. Kiểm versions hiệu lực

~~~bash
./mvnw "-Dsurefire.version=3.5.5" \
  org.apache.maven.plugins:maven-help-plugin:3.5.2:effective-pom \
  -Doutput=target/effective-pom-candidate.xml
~~~

Mở file và tìm:

~~~xml
<artifactId>maven-surefire-plugin</artifactId>
<version>3.5.5</version>
~~~

và:

~~~xml
<artifactId>maven-failsafe-plugin</artifactId>
<version>3.5.5</version>
~~~

Đây là **đoạn mong đợi** trong effective POM, có thể có khoảng trắng/other XML fields. Đọc cả hai, không chỉ Compiler/JUnit hoặc `pom.xml` ban đầu.

### 12.2. Kiểm actual execution

Trong build log candidate, tìm:

~~~text
--- surefire:3.5.5:test (...) @ maven-upgrade-lab ---
--- failsafe:3.5.5:integration-test (...) @ maven-upgrade-lab ---
--- failsafe:3.5.5:verify (...) @ maven-upgrade-lab ---
~~~

Đây là **dạng log minh họa**, không phải output literal. Version ở CLI chưa đủ nếu execution log vẫn cho thấy bản cũ.

### 12.3. So test results

Candidate chỉ pass khi:

- Unit tests **7** và integration test **1**.
- Không có skipped tests.
- Không có test failures/errors.
- JAR smoke test in `TOTAL=33.75`.
- Plugin versions thực sự là 3.5.5 cho cả hai.
- Không có cảnh báo/behavior mới chưa giải thích.

### 12.4. Vì sao chọn 3.5.5 chứ không “nâng luôn mới nhất”?

Đây là bài tập nâng cấp **có kiểm soát** từ 3.5.4 → 3.5.5 để so cùng một plugin family và dễ rollback. Bản mới hơn có thể tồn tại vào thời điểm bạn làm lab. Trong dự án thật, chọn **target đáp ứng security/compatibility policy**, đọc release notes và chạy lại cùng gates; không khẳng định 3.5.5 là newest.

---

## 13. Chốt nâng cấp plugin trong source

Sau khi candidate pass và được review, đổi **một dòng** trong POM:

~~~diff
-        <surefire.version>3.5.4</surefire.version>
+        <surefire.version>3.5.5</surefire.version>
~~~

Không đổi `junit.jupiter.version`, Compiler/Jar, Maven core hoặc application code trong PR này.

Kiểm diff:

~~~bash
git diff --check
git diff -- pom.xml
~~~

Chạy **không còn CLI override** để chứng minh source POM mới tự chứa version:

~~~bash
./mvnw -B -ntp clean verify
java -jar target/maven-upgrade-lab-1.0.0.jar
~~~

Kiểm output unit/IT/XML/effective POM như trước. Nếu có Maven Wrapper và repo Git, add/commit đúng files đã review; không commit `target` hoặc local repository/cache.

### 13.1. Baseline/candidate report mẫu

| Tiêu chí | Before | After | Kết luận |
| --- | --- | --- | --- |
| Maven core | 3.9.12 | 3.9.12 | Giữ nguyên |
| Maven JVM JDK | 17, cùng vendor | 17, cùng vendor | Giữ nguyên |
| Compiler Plugin | 3.14.1 | 3.14.1 | Giữ nguyên |
| Surefire Plugin | 3.5.4 | 3.5.5 | Thay có chủ đích |
| Failsafe Plugin | 3.5.4 | 3.5.5 | Thay cùng family |
| JUnit Jupiter | 5.11.4 | 5.11.4 | Giữ nguyên |
| Unit tests | 7/0 fail | 7/0 fail | PASS nếu đã đo |
| Integration tests | 1/0 fail | 1/0 fail | PASS nếu đã đo |
| App stdout | `TOTAL=33.75` | `TOTAL=33.75` | PASS nếu đã đo |

**Đây là bảng kỳ vọng của fixture, không phải kết quả CI đã đo.** Nếu actual data khác, thay bằng số thực và đánh dấu fail/warning phù hợp.

---

## 14. Kịch bản B: nâng Maven Wrapper 3.9.12 → 3.9.16

**Bắt đầu từ baseline riêng hoặc branch khác**, giữ nguyên Surefire/Failsafe versions. Nếu đã hoàn thành A, bạn có thể chọn baseline A đã approve rồi **chỉ** đổi Maven core; báo rõ phạm vi khác, không trộn hai kết quả để tuyên bố một thí nghiệm đơn biến.

Maven 3.9.16 là một release chính thức trong dòng 3.9.x. Maven Wrapper Plugin có thể tạo/update scripts/properties theo Maven version:

~~~bash
mvn -N org.apache.maven.plugins:maven-wrapper-plugin:3.3.4:wrapper \
  "-Dmaven=3.9.16" \
  "-Dtype=only-script"
~~~

Nếu hệ thống có yêu cầu đặc biệt về checksum/Wrapper type, phải theo policy đó. Không ghi đè bản Wrapper của repo production trước khi được approve.

Sau đó:

~~~bash
./mvnw -version
./mvnw -B -ntp clean verify
java -jar target/maven-upgrade-lab-1.0.0.jar
~~~

`./mvnw -version` phải in Maven **3.9.16**. Nếu không, rollback/điều tra launcher thay vì ghi kết quả “Maven core upgraded”.

### 14.1. Điều không được đổi cùng lúc

- JDK major/vendor.
- Test plugin versions.
- Parent POM và dependencies.
- Build extensions / core extensions.
- Java source hoặc Surefire test includes.
- Enforcer policy.

Nếu vì tính tương thích cần thay thêm một thành phần, tách thành **thay đổi thứ hai có lý do riêng**, ghi dependency/risk và chạy lại baseline mới.

### 14.2. Chi phí khởi động/bộ nhớ có thể thay đổi

Maven core release có thể thay Resolver/classloading/plugin validation behavior. Tăng/giảm thời gian build hoặc downloads không tự là regression chức năng; đo warm-cache/cold-cache trong môi trường được kiểm soát. Đừng so một lần chạy với repo trống và một lần chạy có cache rồi kết luận version mới nhanh/chậm.

### 14.3. So output JAR hash một cách cẩn thận

Hai JAR có thể khác byte-level do timestamps/metadata mặc dù class behavior giống nhau. Kiểm:

~~~bash
jar tf target/maven-upgrade-lab-1.0.0.jar
java -jar target/maven-upgrade-lab-1.0.0.jar
~~~

Nếu yêu cầu **byte-identical/reproducible build**, phải pin timestamps và plugin packaging inputs, sau đó kiểm hash bằng `sha256sum` hoặc công cụ tương đương. Lab cơ bản yêu cầu **behavior + tests + manifest/classfile**; không bắt buộc hash toàn JAR trùng nếu chưa thiết lập reproducibility.

---

## 15. Mở rộng: thử Maven 4 release candidate trong nhánh riêng

Apache Maven hướng dẫn migration theo các giai đoạn:

1. **Prepare:** build xanh trên Maven3 hiện hành và nâng plugins đến bản tương thích Maven3.
2. **Test:** thử Maven4 trên JDK17+ song song, sửa tối thiểu vấn đề tương thích.
3. **Migrate:** chỉ sau khi thành công mới cân nhắc features riêng Maven4 như POM model 4.1.0.

Tại thời điểm tham khảo tháng 11/2026, Maven 4.0.0-rc-7 đã được phát hành, **chưa phải GA**; Maven3.9.16 vẫn là ví dụ baseline ổn định trong lab. Luôn đối chiếu trang Apache Maven Releases khi làm bài ở ngày khác.

### 15.1. Vì sao POM mẫu hiện tại sẽ fail trên Maven4?

POM cố ý có:

~~~xml
<requireMavenVersion>
    <version>[3.9,4.0)</version>
</requireMavenVersion>
~~~

Range này chặn Maven4. Nếu muốn đánh giá RC, tạo **branch thử nghiệm** và thay rule có kiểm soát, không dùng `-Denforcer.skip=true` rồi công bố production compatible.

### 15.2. Cần kiểm trước Maven4

- Maven4 chạy trên Java17+.
- Maven4 core/repository/plugin API compatibility.
- Compiler, Surefire/Failsafe, Jar, resources, clean, Enforcer requirements.
- Core extensions trong `.mvn/extensions.xml` và những extension inject từ Maven home.
- Build extensions trong POM hoặc plugin `<extensions>true</extensions>`.
- Parent/child POM inheritance, profiles, dependency management.
- Plugin misconfigurations: duplicate plugin declarations, removed properties/legacy lifecycle phase bindings.
- Install/deploy defaults thay đổi, đặc biệt `installAtEnd`/`deployAtEnd` theo migration guide.
- POM `modelVersion 4.1.0` không bắt buộc ngay để thử Maven4 với project model 4.0.0; chỉ dùng khi cần Maven4-specific features.
- Full reactor, site/reporting, custom plugin goals và deploy staging chứ không chỉ `mvn test`.

**Không cài RC trực tiếp lên release CI** nếu team chưa duyệt; chạy sandbox/matrix riêng. Maven4 có thể đòi plugin versions khác khi plugin 3.x không compatible; xử lý từng plugin với release notes.

---

## 16. Automation: đọc XML test reports để kiểm số lượng thực

Với Maven Surefire/Failsafe, kết quả mặc định nằm trong:

~~~text
target/surefire-reports/TEST-*.xml
target/failsafe-reports/TEST-*.xml
~~~

Nếu có nhiều test classes/modules, đừng chỉ grep một dòng. Python 3 standard library có thể tóm tắt tests/failures/errors/skipped.

File bổ sung tùy chọn `tools/verify_reports.py`:

~~~python
#!/usr/bin/env python3
from pathlib import Path
import sys
import xml.etree.ElementTree as ET


def count_reports(folder):
    paths = sorted(Path(folder).glob("TEST-*.xml"))
    summary = {
        "suites": 0,
        "tests": 0,
        "failures": 0,
        "errors": 0,
        "skipped": 0,
    }

    for path in paths:
        root = ET.parse(path).getroot()
        suites = [root] if root.tag == "testsuite" else list(
            root.findall("testsuite")
        )
        for suite in suites:
            summary["suites"] += 1
            for key in ("tests", "failures", "errors", "skipped"):
                summary[key] += int(suite.get(key, "0"))

    return summary


def main():
    unit = count_reports("target/surefire-reports")
    integration = count_reports("target/failsafe-reports")

    print(
        "UNIT tests={tests} failures={failures} "
        "errors={errors} skipped={skipped}".format(**unit)
    )
    print(
        "IT tests={tests} failures={failures} "
        "errors={errors} skipped={skipped}".format(**integration)
    )

    ok = (
        unit["tests"] == 7
        and integration["tests"] == 1
        and unit["suites"] >= 1
        and integration["suites"] >= 1
        and all(
            values[k] == 0
            for values in (unit, integration)
            for k in ("failures", "errors", "skipped")
        )
    )

    print("REPORT_GATE=" + ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
~~~

### 16.1. Chạy Python report gate

Trước tiên chạy `clean verify`. Sau đó:

~~~bash
python3 tools/verify_reports.py
~~~

Khi fixture chạy đúng, stdout **chính xác của script** (với reports của bảy unit tests và một IT):

~~~text
UNIT tests=7 failures=0 errors=0 skipped=0
IT tests=1 failures=0 errors=0 skipped=0
REPORT_GATE=PASS
~~~

Đây là kết quả **mong đợi có điều kiện**, chỉ khẳng định khi XML thực sự tương ứng mã mẫu. Nếu reports thiếu hoặc fail, script trả exit code 1.

### 16.2. Giới hạn của script

- Script chạy từ **project root** có `target` đúng, chỉ xử lý **một module**.
- Nó không phân biệt retries/flaky tests trong một số Surefire report encodings; dùng provider/report metadata khi cần kiểm retry history.
- Nó không tự chứng minh plugin version mới đã chạy; phải đọc log/effective POM.
- Với fork/test report schema customization, XML root/attributes có thể khác; cần điều chỉnh parser.
- Nó không gọi Maven; hãy chỉ chạy **sau** một `clean verify` thành công hoặc kể cả khi fail để thu evidence.
- Nó không đọc dependency/advisory metadata, cũng không xác minh artifact hash.

Một CI quality gate nên gồm **cả Maven exit code + report gate + smoke test + version evidence**, không dùng một chỉ số thay tất cả.

---

## 17. GitHub Actions compatibility matrix

Đây là workflow **tùy chọn**, yêu cầu repository đã có Maven Wrapper được tạo/committed. Dùng JDK17 và JDK21 với cả baseline/target plugin versions, giữ Maven Wrapper distribution giống nhau trong matrix.

File `.github/workflows/maven-upgrade-compatibility.yml`:

~~~yaml
name: Maven upgrade compatibility

on:
  push:
    branches: [main]
  pull_request:
  workflow_dispatch:

permissions:
  contents: read

jobs:
  compatibility:
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        java: ['17', '21']
        test-plugin: ['3.5.4', '3.5.5']

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Set up Java
        uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: ${{ matrix.java }}
          cache: maven

      - name: Maven and Java runtime
        run: |
          chmod +x mvnw
          ./mvnw -version
          java -version

      - name: Build and test
        run: >
          ./mvnw -B -ntp
          "-Dsurefire.version=${{ matrix.test-plugin }}"
          clean verify

      - name: Verify packaged JAR
        run: |
          java -jar target/maven-upgrade-lab-1.0.0.jar
          jar tf target/maven-upgrade-lab-1.0.0.jar

      - name: Verify test report counts
        run: |
          python3 tools/verify_reports.py

      - name: Upload test evidence
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: reports-jdk${{ matrix.java }}-plugin-${{ matrix.test-plugin }}
          path: |
            target/surefire-reports/
            target/failsafe-reports/
          if-no-files-found: warn
~~~

### 17.1. Lưu ý để workflow thực sự chạy

- Bạn phải thêm `tools/verify_reports.py` (mục 16) và Maven Wrapper scripts vào Git **trước**.
- `mvnw` phải executable trên Linux hoặc workflow `chmod +x` như mẫu.
- Actions versions trong YAML là **ví dụ khóa theo major**, cần kiểm security/update policy của tổ chức và có thể pin commit SHA nếu policy yêu cầu.
- GitHub runner phải có Python3 (GitHub-hosted Ubuntu thường có), nhưng nếu tổ chức dùng runner tùy chỉnh thì cài/kiểm phiên bản.
- Matrix có **4 jobs**. Không suy ra mọi OS đều compatible vì mẫu chỉ chạy Ubuntu. Nếu target hỗ trợ Windows/macOS, bổ sung runners phù hợp.
- `java-version` setup JDK trong job; Maven Wrapper vẫn phải được xác minh bằng `./mvnw -version`.
- `test-plugin` matrix variable là test-runner family version, không phải version của JUnit Jupiter.
- Khi candidate fail chỉ trên JDK21, lưu logs và class origin/JDK details để phân biệt plugin/JDK regression.
- Không auto merge PR chỉ vì matrix màu xanh; so requirements và reviewer approval.

### 17.2. Kiểm đúng JAR stdout trên CI

Workflow mẫu gọi `java -jar` nhưng **không tự assert stdout**. Để gate cứng, bạn có thể thêm một bước Python 3:

~~~yaml
- name: Assert application stdout
  run: |
    python3 -c "import subprocess; p=subprocess.run(['java','-jar','target/maven-upgrade-lab-1.0.0.jar'],capture_output=True,text=True,check=True); assert p.stdout=='TOTAL=33.75\n', repr(p.stdout)"
~~~

Lệnh Python nhận literal newline escape trong string; trên GitHub Ubuntu, shell quoting giữ nguyên. Nếu CI chạy Windows, cần kiểm shell syntax/line endings khác. Bài mẫu đã có `AppIT` cũng xác nhận stdout và exit code, nhưng kiểm ngoài Maven giúp bắt thêm lỗi packaging/launcher.

### 17.3. Không so kết quả từ hai CI jobs với biến khác nhau

Khi matrix thử JDK17 và JDK21, đừng so chỉ duration/timestamp rồi gán khác biệt cho plugin version. So **cùng Java version, cùng OS, cùng Maven Wrapper, cùng source** giữa baseline 3.5.4 và target 3.5.5.

---

## 18. Risk register và compatibility matrix cần bàn giao

Bảng dưới đây là **mẫu lập kế hoạch**, không phải kết quả test đã chạy.

| Thành phần | Current | Target | Rủi ro | Test cần có |
| --- | --- | --- | --- | --- |
| Maven core | 3.9.12 | 3.9.16 (B) | Resolver/classloading/plugin validation | Full verify, plugin goals |
| Surefire | 3.5.4 | 3.5.5 (A) | JUnit provider, forked JVM, test discovery | 7 unit tests |
| Failsafe | 3.5.4 | 3.5.5 (A) | Integration-test/verify phases | 1 packaged-JAR IT |
| Compiler | 3.14.1 | unchanged | JDK release, annotation processors | Compile, javap major 61 |
| JAR | 3.4.2 | unchanged | Manifest/executable layout | java -jar |
| JUnit Jupiter | 5.11.4 | unchanged | Engine compatibility with provider | Test reports |
| Enforcer | 3.6.3 | unchanged | Maven/JDK version policy | Version gate |
| Core extensions | none in demo | unchanged | Bootstrap/API compatibility | Inspect config/startup |
| JDK Maven | 17+ measured | unchanged | Binary/plugin minimum JDK | mvn -version |
| Maven4 RC | not in main lab | sandbox only | Compatibility, POM model, lifecycle | Dedicated matrix |

### 18.1. Thêm dữ liệu thực tế

Trong dự án doanh nghiệp, ghi:

~~~text
repo:
source commit:
module:
baseline job URL:
candidate job URL:
profiles/CI environment:
Maven launcher + version:
Maven JVM JDK vendor/major/patch:
target bytecode release:
plugin coordinates before/after:
resolved plugin artifact:
unit tests count/failures:
integration tests count/failures:
application stdout:
artifact name/size/hash:
exception/warnings:
approval decision:
rollback commit/tag:
~~~

Không dùng placeholder này như bản báo cáo cuối: thay bằng dữ liệu đo hoặc ghi `unverified` đúng nghĩa.

### 18.2. Bằng chứng có thể thiếu

Nếu Maven build failed trước khi Surefire chạy, báo cáo test counts từ bản build cũ còn trong target là **không hợp lệ**. Chạy `clean verify` trước mỗi lần so, hoặc cô lập build output directories, và đọc report timestamps/CI artifacts gắn với run.

Nếu tests có `Skipped: 7`, một số dòng vẫn có thể dẫn tới `BUILD SUCCESS`. Gate yêu cầu skipped = 0 để chứng minh toàn bộ test suite được kiểm, trừ khi product policy có danh sách exclusions đã được duyệt.

---

## 19. Những lỗi thường xảy ra sau nâng cấp

### 19.1. Plugin không tương thích với Maven core

Triệu chứng:

~~~text
PluginContainerException
NoSuchMethodError: org.apache.maven....
A required class was missing while executing ...
~~~

Kiểm plugin GAV/version, Maven core version, JVM version, `mvn -e -X` plugin realm và minimum requirements. Nếu plugin cũ dùng Maven 2 APIs hoặc Maven internals, nâng core có thể yêu cầu nâng plugin. **Không** sửa bằng cách đưa JAR Maven core ngẫu nhiên vào project dependencies.

### 19.2. Maven plugin yêu cầu JDK mới hơn

~~~text
UnsupportedClassVersionError
~~~

Lỗi có thể xuất hiện khi Maven JVM chạy JDK17 nhưng plugin được compile target JDK21; property `maven.compiler.release=17` **không** giúp JVM tải plugin. Sửa JVM Maven hoặc chọn plugin compatible theo policy.

### 19.3. Unit tests “biến mất”

Một plugin version/provider/config change có thể ảnh hưởng test discovery:

- Test class không đúng default patterns.
- Engine Jupiter không có trong test dependencies.
- `-DskipTests`/`-Dmaven.test.skip=true` được truyền qua CI.
- `-Dtest`/`-Dit.test` giới hạn số tests.
- Test include/exclude patterns khác.
- Provider chọn JUnit4/Vintage/TestNG khác dự kiến.
- Fork hoặc module path gây test classloading issue.

Không lấy `BUILD SUCCESS` làm bằng chứng tất cả tests chạy. Kiểm XML reports và exact test counts.

### 19.4. Failsafe integration-test pass nhưng verify fail

Failsafe thiết kế tách `integration-test` và `verify`. Nếu integration test fail, goal có thể để trạng thái cuối cho `verify`. Chạy `mvn verify` để nhận kết luận build, không gọi riêng phase integration-test rồi chấp nhận.

### 19.5. JUnit provider không load

Ví dụ:

~~~text
TestEngine with ID 'junit-jupiter' failed to discover tests
java.lang.NoClassDefFoundError: ...
~~~

Kiểm JUnit Jupiter engine/test graph, Surefire provider version, Java module path/forking flags, plugin realm. `mvn dependency:tree` giúp với test dependencies; `mvn -X` và plugin docs giúp với provider/plugin realm.

### 19.6. Artifact mới thiếu Main-Class

~~~text
no main manifest attribute, in ...jar
~~~

Kiểm Jar Plugin configuration và manifest thực:

~~~bash
jar xf target/maven-upgrade-lab-1.0.0.jar META-INF/MANIFEST.MF
~~~

Sau đó đọc `META-INF/MANIFEST.MF`; lệnh này giải nén file vào working directory, nên chỉ dùng trong thư mục sandbox nếu không muốn làm bẩn Git. Một cách không ghi ra source là dùng `unzip -p` nếu môi trường có tool. Test `AppIT` sẽ bắt lỗi không launch được JAR.

### 19.7. API behavior hoặc classfile khác

Nếu program stdout khác mà tests chưa bắt, bổ sung regression tests cho contract. Nếu bytecode major >61, target release có thể đã bị thay; đối chiếu Compiler Plugin effective configuration và JDK toolchain.

### 19.8. Network/repository/SSL

~~~text
PluginResolutionException
Could not transfer artifact ...
PKIX path building failed
429 Too Many Requests
~~~

Đây có thể là resolver/mirror/network/credentials failure, **không phải** plugin code incompatibility. Không xóa toàn bộ `~/.m2/repository` hay đổi plugin version nhiều lần khi nguyên nhân là rate limit/network. Ghi error chính xác, dùng repository mirror/credentials tin cậy theo policy.

### 19.9. Windows vs Unix

- Wrapper Unix dùng `./mvnw`, Windows dùng `mvnw.cmd`.
- Shell quoting đối với `-Dsurefire.version=...` khác, nên ví dụ đặt toàn bộ property trong dấu ngoặc kép.
- Đường dẫn `java.exe` được `AppIT` tự chọn.
- Maven local repository có path khác, nên không hardcode `~/.m2` vào Java code.
- Dòng newline stdout là system-dependent; AppIT dùng `strip()` để kiểm nội dung logic.

### 19.10. Test flaky/timeout khi nâng plugin

Đừng coi một lần pass sau retry là bằng chứng không regression. Chạy lặp đủ để phân biệt flaky behavior; giữ run IDs, fork settings, thread counts, resource limits và stack traces. Với CI container, CPU/RAM có thể làm test timeouts chứ không phải version incompatibility.

---

## 20. Rollback: chính xác và đủ nhanh

### 20.1. Nếu chỉ thử bằng CLI override

Không có thay đổi source. Bỏ cờ `-Dsurefire.version=3.5.5` và chạy baseline:

~~~bash
./mvnw -B -ntp clean verify
~~~

Nếu dùng Git branch sạch, xác nhận:

~~~bash
git status --short
~~~

### 20.2. Nếu đã đổi POM nhưng chưa merge

Review `git diff -- pom.xml`, rồi sửa property về 3.5.4 **hoặc** revert commit nâng cấp. Trong team project, dùng `git revert <commit>` sau khi đã merge thay vì reset/force push shared history.

Không dùng `git reset --hard` trên workspace có thay đổi chưa được lưu. Backup/uncommitted changes cần được bảo vệ theo quy trình nhóm.

### 20.3. Nếu đã đổi Wrapper

Revert commit chỉ chứa wrapper scripts/properties, kiểm lại `./mvnw -version` thực quay về 3.9.12 và chạy full verify. Không chỉ đổi text trong properties rồi giả định distribution cached đã đúng; launcher output là bằng chứng cuối.

### 20.4. Đừng rollback bằng cách skip tests

Các lệnh sau **không phải rollback thật**:

~~~bash
mvn -DskipTests package
mvn -Dmaven.test.skip=true package
mvn -Denforcer.skip=true verify
~~~

Chúng làm thay đổi quality gate, có thể che regression. Nếu cần mitigation vận hành trong sự cố, ghi rõ scope/approval; không kết luận build compatibility đã được kiểm.

---

## 21. So sánh hai kịch bản mà không lẫn nguyên nhân

| Bài thực hành | Maven core | Surefire/Failsafe | Java/JUnit | Tập trung kiểm |
| --- | --- | --- | --- | --- |
| Baseline | 3.9.12 | 3.5.4 | JDK17+, JUnit5.11.4 | Reference behavior |
| Candidate A | 3.9.12 | 3.5.5 | Giữ nguyên | Test-runner compatibility |
| Candidate B | 3.9.16 | 3.5.4 | Giữ nguyên | Maven core compatibility |
| A+B sau phê duyệt | 3.9.16 | 3.5.5 | Giữ nguyên | Final integrated regression |
| Maven4 RC sandbox | 4.0.0-rc-7 | Compatibility-dependent | JDK17+ | Major migration exploration |

Không đổi Enforcer range trong A/B: cả hai vẫn dùng Maven3.9.x. Với Maven4 RC sandbox, Enforcer rule bắt buộc điều chỉnh trên branch đó. Đừng lấy một build pass của A+B rồi kết luận **riêng** A hoặc **riêng** B đã không ảnh hưởng gì; các phép so đơn biến cần từng baseline rõ.

---

## 22. Bài tập thực hành có tiêu chí chấm

### Bài 1 — Dựng baseline

Tạo đúng năm file ở mục 4–9. Chạy `mvn clean verify` và `java -jar`. Nộp console Maven/JDK version, XML reports, stdout JAR. **Đạt khi 7 unit + 1 IT PASS và stdout `TOTAL=33.75`.**

### Bài 2 — Kết quả có thể kiểm toán

Tạo bảng trước nâng: Maven version, Java vendor/version, plugin GAV/version, JUnit, test counts và JAR artifact. Những gì chỉ là giả định phải ghi `unverified`.

### Bài 3 — Maven Wrapper

Cài Wrapper 3.3.4 với `-Dmaven=3.9.12`, kiểm `./mvnw -version` và so với `mvn -version`. Vì sao phải dùng cùng launcher cho cả hai lần test plugin?

### Bài 4 — Plugin override

Chạy `"-Dsurefire.version=3.5.5" clean verify` mà chưa sửa POM. Trong effective POM và execution log, xác định cả Surefire lẫn Failsafe version mới.

### Bài 5 — Test count

Tạo file `tools/verify_reports.py` và chạy sau candidate build. Vì sao script fail khi Surefire tests bị skip mà Maven vẫn có thể exit 0 trong vài cấu hình?

### Bài 6 — JAR smoke test

Chạy `java -jar`. Kiểm exit code 0 và stdout chính xác. Vì sao `mvn test` xanh không đủ chứng minh package output chạy được?

### Bài 7 — PR nhỏ

Chỉ đổi `surefire.version` từ 3.5.4 lên 3.5.5. Chạy `git diff --check`, xác minh không nâng JUnit/JDK, chạy build không CLI override.

### Bài 8 — Maven core upgrade

Trên branch độc lập, nâng Maven Wrapper 3.9.12→3.9.16 mà vẫn giữ Surefire/Failsafe 3.5.4. Nêu các evidence cần so trước–sau.

### Bài 9 — Bytecode

Dùng `javap -verbose`, tìm classfile major 61. Vì sao Compiler release=17 và Maven JVM JDK version có thể khác nhau?

### Bài 10 — Test discovery

Đổi tên `CheckoutTest` thành một class không khớp Surefire include defaults (trên branch sandbox). Vì sao một build có thể bỏ sót tests? Quality gate nào bắt lỗi này?

### Bài 11 — Integration-test phase

Chạy riêng `mvn test` rồi `mvn verify`. Phase nào phải có `AppIT`? Vì sao Failsafe cần `verify`?

### Bài 12 — Plugin/JDK mismatch

Giả sử plugin mới yêu cầu JDK21 nhưng Maven JVM chạy JDK17. Điều gì có thể xảy ra? Vì sao đổi `maven.compiler.release` không đủ?

### Bài 13 — Network failure

Một candidate run fail `Could not transfer artifact` hoặc HTTP429. Có nên đánh giá “plugin không tương thích” từ lỗi này không? Bạn phải ghi evidence gì?

### Bài 14 — CI matrix

Tạo matrix JDK17/21 × Surefire 3.5.4/3.5.5. Có bao nhiêu jobs và vì sao so đúng JDK/OS mới tách được ảnh hưởng plugin?

### Bài 15 — Failure injection

Trong test sandbox, tạm sửa expected discount 33.75 thành 33.74, chạy `verify` và xác nhận gate fail. Hoàn nguyên test rồi rerun. Không merge thay đổi tạo lỗi này.

### Bài 16 — Extension inventory

Kiểm `.mvn/extensions.xml`, `build/extensions` và plugins `extensions=true` trong dự án thật. Vì sao core extension có thể fail ngay trước Surefire khi nâng Maven major?

### Bài 17 — Maven4 RC

Đọc migration guide, liệt kê prerequisites JDK17, plugin compatibility, Enforcer range và các thay đổi model/lifecycle. Tại sao RC thử nghiệm cần branch/matrix riêng?

### Bài 18 — Artifact comparison

So JAR entries/manifest/classfile/version và stdout. Tại sao SHA-256 hai JAR khác không tự chứng minh behavior regression khi build chưa được thiết kế reproducible?

### Bài 19 — Rollback

Mô tả cách rollback CLI override, POM property và Wrapper commit. Vì sao `-DskipTests` không phải rollback?

### Bài 20 — GO / NO-GO

Viết báo cáo có trước/sau Maven, JDK, Surefire/Failsafe, số test, stdout, CI matrix, rủi ro còn mở, người duyệt và commit rollback. Không được điền PASS cho những job chưa chạy.

---

## 23. Checklist cuối cùng trước khi phê duyệt nâng cấp

- [ ] Đã xác định phiên bản current và target, release notes và yêu cầu Maven/JDK tối thiểu.
- [ ] Đã chốt phạm vi một thay đổi hoặc một plugin family nhất quán.
- [ ] Đã lưu baseline cùng commit, Maven/JDK, profiles, module và CI config.
- [ ] Maven Wrapper/CLI thực hiện đúng version mà báo cáo ghi.
- [ ] Parent/pluginManagement/profiles không override phiên bản ngoài ý định.
- [ ] Effective POM và execution log xác nhận Surefire/Failsafe versions đích.
- [ ] `clean verify` chạy không skip tests và exit code 0.
- [ ] Surefire XML thực có 7 unit tests, 0 fail/error/skipped.
- [ ] Failsafe XML thực có 1 integration test, 0 fail/error/skipped.
- [ ] `AppIT` đã launch packaged JAR, không chỉ mock `main`.
- [ ] `java -jar` stdout đúng `TOTAL=33.75`.
- [ ] `javap` cho đúng target classfile (Java17 nếu đó là contract).
- [ ] Compiler, Jar, JUnit và runtime inputs giữ nguyên khi kiểm A.
- [ ] Test plugin versions giữ nguyên khi kiểm Maven core B.
- [ ] CI jobs bắt buộc đã pass, flaky tests/timeout được điều tra.
- [ ] Build/core extensions và custom plugins đã được rà compatibility.
- [ ] Không tự nâng đến Maven4 preview trên production build.
- [ ] Không dùng `skipTests`, `maven.test.skip` hoặc Enforcer skip để che lỗi.
- [ ] Không xem network/HTTP429 là bằng chứng incompatibility.
- [ ] Không đưa credentials/private settings vào artifacts công khai.
- [ ] Git diff đúng scope, commit/PR có reviewer và rollback plan.
- [ ] Quyết định GO / NO-GO dựa vào **actual evidence**, không dùng outputs minh họa.

**Kết luận:** Nâng cấp Maven hoặc plugin là một thay đổi của **công cụ build**, nhưng chất lượng được đo bằng **đầu ra và hành vi thật của sản phẩm**. Quy trình an toàn là *baseline → chọn một biến thay đổi → thử candidate → xác minh version thật → chạy unit/IT/package/smoke tests → CI compatibility matrix → review/rollback*. Bài lab cho phép bạn chứng minh cặp Surefire/Failsafe 3.5.4→3.5.5 và Maven Wrapper 3.9.12→3.9.16 **một cách độc lập**, trước khi cân nhắc bất kỳ migration lớn hơn nào.

## 24. Tài liệu tham khảo chính thức

- [Apache Maven — Starting with Maven 4](https://maven.apache.org/guides/mini/guide-migration-to-mvn4): prepare/test/migrate, JDK17, plugin versions, lifecycle differences và optional model4.1.0.
- [Apache Maven — Maven Release History](https://maven.apache.org/docs/history): các phiên bản Maven 3.9.12, 3.9.16, Maven4 RC.
- [Apache Maven — Maven Wrapper](https://maven.apache.org/tools/wrapper/): Maven Wrapper distributions, scripts và sử dụng `./mvnw`.
- [Apache Maven Wrapper Plugin — wrapper:wrapper](https://maven.apache.org/tools/wrapper/maven-wrapper-plugin/wrapper-mojo.html): `-Dmaven`, `-Dtype=only-script`, distribution checksum properties.
- [Apache Maven Surefire Plugin 3.5.5 — Plugin Details](https://maven.apache.org/surefire-archives/surefire-3.5.5/maven-surefire-plugin/plugin-info.html): min Maven/JDK, plugin goals.
- [Apache Maven Surefire Plugin — Introduction](https://maven.apache.org/surefire/maven-surefire-plugin/): JUnit unit tests và report locations.
- [Apache Maven Surefire — Using JUnit Platform](https://maven.apache.org/surefire/maven-surefire-plugin/examples/junit-platform.html): provider/engine requirements.
- [Apache Maven Failsafe Plugin](https://maven.apache.org/surefire/maven-failsafe-plugin/): integration-test/verify goals và reports.
- [Apache Maven Compiler Plugin](https://maven.apache.org/plugins/maven-compiler-plugin/): release target/toolchains.
- [Apache Maven JAR Plugin](https://maven.apache.org/plugins/maven-jar-plugin/): manifest/executable JAR.
- [Apache Maven Enforcer — requireMavenVersion](https://maven.apache.org/enforcer/enforcer-rules/requireMavenVersion.html): Maven range checks.
- [Apache Maven Enforcer — requireJavaVersion](https://maven.apache.org/enforcer/enforcer-rules/requireJavaVersion.html): JDK requirement rule.
- [Apache Maven Help Plugin — effective-pom](https://maven.apache.org/plugins/maven-help-plugin/effective-pom-mojo.html): effective plugin versions and inheritance.
- [MojoHaus Versions Maven Plugin — display-plugin-updates](https://www.mojohaus.org/versions/versions-maven-plugin/display-plugin-updates-mojo.html): tìm candidate plugin versions nhưng không tự nâng.
- [Apache Maven — Guide to Maven Classloading](https://maven.apache.org/guides/mini/guide-maven-classloading.html): plugin realms/project classpath/extension impacts.
