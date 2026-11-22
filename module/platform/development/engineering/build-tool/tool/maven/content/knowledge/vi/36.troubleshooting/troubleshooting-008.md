# Build thành công nhưng không có kiểm thử nào được chạy trong Maven

Một Java/Maven build báo `BUILD SUCCESS` **không có nghĩa là Surefire hoặc Failsafe đã chạy bất kỳ phép kiểm thử nào**. Java source có thể compile, file JAR vẫn được tạo và Maven trả exit code 0 trong khi test source ở sai thư mục, tên test không khớp quy ước, plugin chưa được bind, JUnit Platform thiếu engine, toàn bộ tests bị lọc/skipped hoặc CI vô tình truyền flag bỏ chạy tests.

Bài học thuộc nhóm **Chẩn đoán lỗi**, hướng dẫn xác định chính xác nguyên nhân *“Build thành công nhưng không có kiểm thử nào được chạy”* và biến tình trạng đó thành lỗi CI có thể kiểm soát. Mục tiêu không chỉ là tìm một dòng log, mà phân biệt:

- **Test source:** file `.java` trong test source root.
- **Test compilation:** có `.class` trong `target/test-classes`.
- **Discovery:** Surefire/Failsafe/JUnit Platform có nhận class/test case không.
- **Execution:** có bao nhiêu test invocations thật sự chạy.
- **Skip:** có bao nhiêu test bị `@Disabled`, conditions hoặc skip flags.
- **Result:** failures/errors, XML reports, Maven exit code và module coverage.

Bài thực hành dùng **Java 17, Maven 3.9.x, JUnit Jupiter 5.11.0, Maven Surefire Plugin 3.6.1 và Maven Failsafe Plugin 3.6.1**. Plugin versions được cố định để ví dụ dễ tái lập; không giả định luôn là mới nhất. Một POM hoàn chỉnh có **5 unit tests + 1 integration test**, Java app chạy được và một Python 3 CI gate đọc XML reports để phát hiện zero executed tests. Trong các phần minh họa ngắn, fragment XML/Java được ghi rõ khi không phải file chạy độc lập.

> **Quy tắc:** Không lấy `BUILD SUCCESS` làm bằng chứng kiểm thử. Phải có *test report của lần build hiện tại* cho đúng module/loại test, với ngưỡng tối thiểu `executed = tests - skipped` và số failures/errors bằng 0.

## 1. Vì sao Maven có thể thành công khi không có tests?

Default Maven lifecycle cho `packaging=jar`:

```text
validate
   ↓
compile           biên dịch src/main/java
   ↓
test-compile      biên dịch src/test/java
   ↓
test              Surefire chạy unit tests
   ↓
package           đóng gói main JAR
   ↓
integration-test  Failsafe nếu có execution phù hợp
   ↓
verify            Failsafe verify và các quality gates nếu bind
   ↓
install           local Maven repository
   ↓
deploy            remote Maven repository
```

Một trong các nhầm lẫn thường gặp là thấy Maven đã chạy `test-compile` và tạo `target/test-classes` rồi tưởng assertions đã được thực thi. **Biên dịch test source không phải chạy test.** Cần phase `test` gọi Surefire, hoặc `integration-test` + `verify` gọi Failsafe.

Theo tài liệu Surefire 3.6.1, **`failIfNoTests` có default `false`**. Vì vậy nếu không tìm thấy test nào, Maven có thể ghi dạng log:

```text
[INFO] No tests to run.
[INFO] BUILD SUCCESS
```

Hai dòng trên minh họa ý nghĩa, **không phải literal log được thu từ một Maven invocation cụ thể**. Lời nhắc `No tests to run` có thể thay đổi theo plugin version/verbosity. Default `failIfNoTests=false` cũng có ở Failsafe. Đây là lý do CI cần kiểm test counts thay vì chỉ kiểm exit status.

### 1.1. Ma trận các triệu chứng

| Quan sát | Có thể hiểu là | Kiểm tra tiếp |
| --- | --- | --- |
| `BUILD SUCCESS` nhưng không có Surefire log | Chưa đến phase `test`, packaging khác hoặc plugin skip | Command, packaging, Maven lifecycle |
| `No sources to compile` ở `testCompile` | Test source không được Maven nhận | `src/test/java`, testSourceDirectory, profiles |
| Có `.class` nhưng `No tests to run` | Class name không match, engine/filters lỗi | Surefire patterns, annotation, provider |
| `Tests run: 0` | Chưa có test invocation được ghi nhận | Tên class, includes/excludes, skip |
| `Tests run: 5, Skipped: 5` | Có tests được phát hiện nhưng **không executed** | `@Disabled`, environment conditions, tags |
| `Tests run: 5, Failures: 0, Errors: 0, Skipped: 0` | 5 test invocations thành công | Đối chiếu số lượng mong đợi |
| Unit tests pass nhưng `*IT` không chạy | Failsafe chưa bind hoặc chưa tới `verify` | Failsafe plugin/goals/naming |
| Root multi-module xanh nhưng thiếu report module X | Có thể chỉ build parent/subset hoặc test skip | Reactor Summary, `-pl/-N`, per-module reports |

**Đếm executed, không đếm file source.** Một test class có thể chứa 20 methods; một `@ParameterizedTest` có thể tạo nhiều invocations; một `@TestFactory` trả rỗng có thể không chạy assertion nào.

## 2. Trước tiên xác nhận command đã tới phase chạy tests

Thử từ root có `pom.xml`:

```bash
java -version
mvn --version
mvn -B clean test
```

Lệnh `test` chạy các phases trước đó, biên dịch production/test code rồi Surefire chạy unit tests cho project có lifecycle binding phù hợp.

So với:

```bash
mvn -B clean compile
mvn -B clean test-compile
mvn -B clean package
mvn -B clean verify
```

- `compile` chỉ biên dịch production code.
- `test-compile` có thể biên dịch test classes nhưng **chưa chạy methods**.
- `package` chạy qua `test` cho default `jar` lifecycle, nhưng có thể bị skip test execution theo configuration.
- `verify` đi qua `test`/`integration-test`; integration tests chỉ được chạy khi **Failsafe goals đã bind**.
- `mvn surefire:test` gọi goal riêng lẻ, **không tự chạy sạch toàn bộ lifecycle `test-compile`**; trên checkout sạch có thể thiếu test classes.

### 2.1. Parent POM không đại diện tests của child modules

Trong reactor:

```text
root/pom.xml             packaging=pom
module-a/pom.xml         packaging=jar
module-b/pom.xml         packaging=jar
```

Parent `packaging=pom` thường không có Java test classes. Lệnh `mvn -N verify` chỉ build root **non-recursive**, nên có thể `BUILD SUCCESS` mà tests ở module-a/module-b không chạy. Từ root chạy không có `-N` và xem Reactor Summary + reports từng module.

Không tự kỳ vọng một dòng “Tests run: 0” ở parent có nghĩa mọi child zero. Cũng không tự kỳ vọng build root pass có nghĩa tất cả modules đều chứa tests.

## 3. Surefire nhận những test class names nào?

Apache Maven Surefire mặc định include:

```text
**/Test*.java
**/*Test.java
**/*Tests.java
**/*TestCase.java
```

Các patterns được đối chiếu với tên các test classes đã biên dịch, với ý nghĩa tương ứng tên file Java. Ví dụ:

| Class name | Mặc định Surefire? | Lý do |
| --- | --- | --- |
| `TestPrice` | Có | `Test*.java` |
| `PriceTest` | Có | `*Test.java` |
| `PriceTests` | Có | `*Tests.java` |
| `PriceTestCase` | Có | `*TestCase.java` |
| `PriceSpec` | Không | Không khớp default patterns |
| `PriceIT` | Không | Thường dùng Failsafe |
| `ITPrice` | Không | Thường dùng Failsafe |
| `PriceIntegrationTest` | Có | Kết thúc bằng `Test` |
| `PriceTestHelper` | Không | Không khớp bốn patterns |
| `PriceTest$Nested` | Có thể bị loại | Default excludes của Surefire loại inner class files `**/*$*` |

Nếu IDE chạy được `PriceSpec` khi nhấn Run cạnh `@Test` nhưng `mvn test` không thấy class đó, đây thường là **khác biệt discovery giữa IDE runner và Surefire**, không phải Java compiler bị hỏng.

### 3.1. Cách sửa ưu tiên: đặt lại tên test

Sai convention:

```text
src/test/java/vn/example/tests/PriceSpec.java
```

Đổi thành:

```text
src/test/java/vn/example/tests/PriceTest.java
```

và đổi Java class name tương ứng. Sau đó:

```bash
mvn -B clean test
```

Dùng `clean` để xóa `.class` cũ trong `target/test-classes`; test count của build cũ không nên làm bạn tưởng mới có tests được phát hiện.

### 3.2. Hoặc khai includes nếu team dùng hậu tố khác

Một fragment Surefire nếu team dùng `*Spec`:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-surefire-plugin</artifactId>
    <version>3.6.1</version>
    <configuration>
        <includes>
            <include>**/Test*.java</include>
            <include>**/*Test.java</include>
            <include>**/*Tests.java</include>
            <include>**/*TestCase.java</include>
            <include>**/*Spec.java</include>
        </includes>
    </configuration>
</plugin>
```

Đây là **plugin fragment**, không phải POM runnable hoàn chỉnh. Khi ghi đè `includes`, đừng vô tình xóa các patterns mặc định cần giữ. `excludes`, `excludesFile` và `-Dtest=...` có thể ghi đè/thay đổi selection; hãy đọc effective POM thay vì đoán theo source filenames.

### 3.3. File nằm sai source root

Maven Java test source root mặc định:

```text
src/test/java
```

Nếu code nằm trong `tests/java`, `test` hoặc `src/main/tests` nhưng POM không cấu hình source roots, Maven có thể báo `No sources to compile`. IDE có thể đánh dấu các thư mục đó là test source riêng, gây lệch với CI.

**Sửa:** dùng thư mục chuẩn hoặc khai generated/test source roots bằng plugin/POM phù hợp. Không chữa bằng cách chỉ “Mark Directory as Test Sources Root” trong IDE mà CI Maven không biết.

## 4. Những flags bỏ qua tests dễ bị ẩn

| Flag/config | Hành vi chủ yếu |
| --- | --- |
| `-DskipTests` | Surefire bỏ **chạy** unit tests, test compile thường vẫn diễn ra |
| `-Dmaven.test.skip=true` | Bỏ cả test compilation và test execution qua Compiler/Surefire/Failsafe |
| `-DskipITs=true` | Failsafe bỏ integration tests, unit Surefire không mặc định bị tắt |
| Surefire `<skipTests>true</skipTests>` | Bỏ test execution ở plugin |
| Plugin `<skip>true</skip>` | Bỏ goal tương ứng |
| `-Dtest=SomeTest` | Chỉ chọn test cụ thể, không phải toàn suite |
| `-Dit.test=SomeIT` | Chỉ chọn integration test cụ thể trong Failsafe |
| `-Dmaven.test.failure.ignore=true` | Có thể cho phép build tiếp tục dù test failures; không chứng minh đủ tests |
| JUnit `@Disabled` | Test được discovery nhưng bị skipped |

**Version nuance:** theo Surefire/Failsafe **3.6.1**, `-DskipTests` là property Surefire; Failsafe hiện không còn bind chính tham số `skipTests` của mình với property `skipTests` như các bản cũ. Dùng `-DskipITs` để điều khiển IT; `-Dmaven.test.skip` có thể tắt cả compile/unit/IT. Khi chẩn đoán một repo dùng Failsafe cũ, xem đúng plugin version và docs phiên bản đó.

### 4.1. Những nơi cần tìm flags

1. CI job template, build script và Maven command thực chạy.
2. `.mvn/maven.config` trong repository.
3. Parent POM và các `<properties>`.
4. `<build><plugins>`, `pluginManagement` kế thừa.
5. Maven profiles chọn bởi `-P`, settings.xml hoặc activation.
6. Environment/JVM/system properties và runner options.
7. IDE Maven Run Configuration hoặc wrapper script.

Ví dụ CI đang gọi:

```bash
mvn -B -Dmaven.test.skip=true clean verify
```

Java code compile và JAR có thể được tạo dù **không có tests executed**. Không sửa bug bằng cách thêm assertion giả; phải xóa skip configuration ở nguồn tạo ra nó và kiểm reports.

### 4.2. Khi skipTests=false không có tác dụng

Nếu effective POM chứa:

```xml
<configuration>
    <skipTests>true</skipTests>
</configuration>
```

thì `-DskipTests=false` có thể không override **literal plugin configuration**. Cần sửa POM, ví dụ buộc plugin config đọc property được phép override hoặc bỏ skip mặc định. Đừng giả định một property CLI luôn thắng mọi cấu hình XML.

## 5. JUnit Jupiter: API compile được nhưng runtime engine chưa có

Với JUnit Jupiter cần phân biệt:

- `junit-jupiter-api` cung cấp `org.junit.jupiter.api.Test` và Assertions để **compile**.
- `junit-jupiter-engine` là engine **thực thi** Jupiter test invocations.
- Surefire JUnit Platform provider làm cầu nối Maven ↔ JUnit Platform.
- `junit-vintage-engine` cần thiết để vận hành JUnit 4 tests theo các cấu hình JUnit Platform phù hợp.
- `@Test` của JUnit4 (`org.junit.Test`) **khác** `@Test` của Jupiter (`org.junit.jupiter.api.Test`).

Một dependency đơn giản có đủ API và Engine cho ví dụ là:

```xml
<dependency>
    <groupId>org.junit.jupiter</groupId>
    <artifactId>junit-jupiter</artifactId>
    <version>5.11.0</version>
    <scope>test</scope>
</dependency>
```

`junit-jupiter` aggregator kéo các Jupiter components phù hợp. Chỉ có API và thiếu engine có thể khiến Maven không chạy test như mong muốn dù source compilation thành công. Xem `mvn dependency:tree -Dscope=test` để xác định chính xác resolved engines/versions.

Theo tài liệu Apache, **Surefire từ 3.6.0** dùng JUnit Platform làm cơ chế chung cho nhiều test frameworks; provider/engine selection phụ thuộc dependencies. Không áp dụng lời khuyên cho phiên bản 2.x một cách máy móc khi đang dùng Surefire 3.6.x.

### 5.1. Jupiter test class không bắt buộc public

JUnit Jupiter chấp nhận test class/method **package-private**. Ví dụ hợp lệ:

```java
package vn.example.tests;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class PriceTest {
    @Test
    void calculates() {
        assertEquals(4, 2 + 2);
    }
}
```

Đừng biến mọi test class thành public chỉ vì convention cũ. Nhưng những điều sau vẫn cần kiểm:

- `@Test` được import đúng framework.
- Không phải helper method không có `@Test`.
- Test method không bị `private`/sai signature.
- Test class không bị class-level `@Disabled`, conditions hay engine filters.
- Dynamic tests/parameterized tests có invocations thật.
- Unit tests nằm trong `src/test/java` và compiler có tạo `target/test-classes`.

### 5.2. Trộn JUnit 4 với JUnit 5

Một class dùng:

```java
import org.junit.Test;
```

không trở thành Jupiter test chỉ vì project thêm Jupiter API. Với JUnit Platform cần xác định JUnit 4 dependency và Vintage Engine phù hợp, hoặc migrate annotation sang Jupiter. Surefire 3.6.x có logic engine/provider selection riêng; kiểm documentation/version và dependencies thực tế, không kết luận theo tên `@Test` đơn thuần.

### 5.3. All skipped vẫn có thể BUILD SUCCESS

Nếu toàn bộ tests mang `@Disabled` hoặc conditional skips:

```text
tests=5
skipped=5
failures=0
errors=0
executed=0
```

thì không có assertion nào thực thi. Dù bật `failIfNoTests=true`, plugin có thể đã **discovery** năm tests nên không coi đó là “no tests”. Vì vậy **gate đọc reports** phải kiểm `executed = tests - skipped`.

## 6. Surefire khác Maven Failsafe như thế nào?

**Surefire** chạy unit tests ở phase `test`. **Failsafe** chạy integration tests với hai goals:

- `failsafe:integration-test` ở phase `integration-test`.
- `failsafe:verify` ở phase `verify`.

Failsafe tách chạy tests và verify result để các công việc dọn môi trường ở `post-integration-test` còn có cơ hội hoàn thành. Tài liệu Apache khuyến nghị **`mvn verify`**, thay vì kết thúc ở `mvn integration-test` trước verify.

Default Failsafe names:

```text
**/IT*.java
**/*IT.java
**/*ITCase.java
```

Ví dụ:

| Class | Plugin mặc định |
| --- | --- |
| `CalculatorTest` | Surefire |
| `AppIT` | Failsafe nếu goals đã bind |
| `ITApp` | Failsafe nếu goals đã bind |
| `AppITCase` | Failsafe nếu goals đã bind |
| `AppIntegrationTest` | Surefire vì tên kết thúc `Test` |
| `AppSpec` | Không plugin nào theo default patterns |

`mvn verify` **không tự kích hoạt** Failsafe trong mọi JAR project. Phải khai plugin goals trong `build/plugins` hoặc kế thừa execution phù hợp. Nếu plugin chỉ có version trong `pluginManagement` mà không có active execution, tests `*IT` vẫn không chạy.

## 7. Project Java 17 runnable: 5 unit tests + 1 integration test

Project lab được thiết kế sao cho `clean verify` chạy 6 tests và CI có thể kiểm chúng. Tên các files và Java classes khớp chính xác.

### 7.1. Cây thư mục

```text
test-discovery-lab/
├── pom.xml
└── src/
    ├── main/java/vn/example/tests/
    │   ├── Calculator.java
    │   └── App.java
    └── test/java/vn/example/tests/
        ├── CalculatorTest.java
        └── AppIT.java
```

`CalculatorTest` có 5 unit test methods. `AppIT` là một test integration *in-process* kiểm luồng App ↔ Calculator; không có database hoặc network. Tên `*IT` thể hiện **Failsafe lifecycle discovery**, không giả vờ kiểm HTTP/DB nếu project không có các integration boundaries đó.

### 7.2. POM đầy đủ

File `test-discovery-lab/pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>vn.example</groupId>
    <artifactId>test-discovery-lab</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <junit.jupiter.version>5.11.0</junit.jupiter.version>
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
                <version>3.3.2</version>
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
                <configuration>
                    <release>${maven.compiler.release}</release>
                </configuration>
            </plugin>
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
                <artifactId>maven-failsafe-plugin</artifactId>
                <version>3.6.1</version>
                <configuration>
                    <failIfNoTests>true</failIfNoTests>
                </configuration>
                <executions>
                    <execution>
                        <id>run-integration-tests</id>
                        <phase>integration-test</phase>
                        <goals>
                            <goal>integration-test</goal>
                        </goals>
                    </execution>
                    <execution>
                        <id>verify-integration-tests</id>
                        <phase>verify</phase>
                        <goals>
                            <goal>verify</goal>
                        </goals>
                    </execution>
                </executions>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
            </plugin>
        </plugins>
    </build>
</project>
```

**Quan trọng:**

1. `jar` packaging bind Surefire `test` theo default lifecycle.
2. `junit-jupiter` trong test scope cung cấp Jupiter API/Engine tương thích.
3. `failIfNoTests=true` làm Surefire fail nếu unit tests không được tìm thấy; Failsafe cũng yêu cầu IT có trong module này.
4. Failsafe bind `integration-test` và `verify` rõ ràng, không chỉ khai tên plugin.
5. Không có `skipTests`/`skipITs` trong POM. Nếu truyền skip flags trên CLI, plugin có thể bỏ execution theo chủ đích, vì thế cần thêm XML report gate.
6. Cấu hình strict ở đây dành cho module **có cả unit và IT**; không sao chép máy móc vào module POM-only hoặc module không có IT.

### 7.3. Calculator.java

File `src/main/java/vn/example/tests/Calculator.java`:

```java
package vn.example.tests;

/**
 * Calculates an integer amount after a percentage discount.
 */
public final class Calculator {
    private Calculator() {
    }

    /**
     * @param price nonnegative amount in cents
     * @param discountPercent 0 through 100
     * @return discounted cents, rounded down
     * @throws IllegalArgumentException if input is invalid
     */
    public static int net(int price, int discountPercent) {
        if (price < 0 || discountPercent < 0 || discountPercent > 100) {
            throw new IllegalArgumentException("invalid price or discount");
        }
        return (int) ((long) price * (100 - discountPercent) / 100);
    }
}
```

Phép nhân chuyển sang `long` để tránh `int` overflow. Kết quả cuối luôn trong `[0, price]` (khi inputs hợp lệ), nên ép về int là an toàn.

### 7.4. App.java và stdout

File `src/main/java/vn/example/tests/App.java`:

```java
package vn.example.tests;

public final class App {
    private App() {
    }

    public static String message() {
        return "netCents=" + Calculator.net(1000, 10);
    }

    public static void main(String[] args) {
        System.out.println(message());
    }
}
```

Sau build:

```bash
java -cp target/test-discovery-lab-1.0.0.jar vn.example.tests.App
```

**Stdout chính xác:**

```text
netCents=900
```

Đây là plain library JAR; POM không tạo manifest `Main-Class`. Vì vậy `java -cp ... fully.qualified.Main` là lệnh đúng, không giả định `java -jar` chạy.

### 7.5. CalculatorTest.java — 5 unit tests

File `src/test/java/vn/example/tests/CalculatorTest.java`:

```java
package vn.example.tests;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class CalculatorTest {

    @Test
    void tenPercentDiscount() {
        assertEquals(900, Calculator.net(1000, 10));
    }

    @Test
    void noDiscount() {
        assertEquals(1000, Calculator.net(1000, 0));
    }

    @Test
    void fullDiscount() {
        assertEquals(0, Calculator.net(1000, 100));
    }

    @Test
    void roundsDown() {
        assertEquals(133, Calculator.net(199, 33));
    }

    @Test
    void rejectsInvalidDiscount() {
        assertThrows(
            IllegalArgumentException.class,
            () -> Calculator.net(500, 101)
        );
    }
}
```

Có **năm methods `@Test`**, package-private hợp lệ với JUnit Jupiter. `CalculatorTest` khớp default `*Test.java` của Surefire.

### 7.6. AppIT.java — 1 integration test

File `src/test/java/vn/example/tests/AppIT.java`:

```java
package vn.example.tests;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class AppIT {
    @Test
    void composesReceiptMessage() {
        assertEquals("netCents=900", App.message());
    }
}
```

`AppIT` khớp Failsafe `*IT.java`, không nằm trong Surefire defaults. Test kiểm hai lớp Java phối hợp, không có external service. Đừng hiểu mỗi class đặt tên IT đều tự động thành end-to-end test thật.

## 8. Lệnh chạy và kết quả mong đợi

Tại root project:

```bash
java -version
mvn --version
mvn -B clean test
```

Maven cần JDK 17+ và truy cập Maven repository để tải dependencies/plugins lần đầu. Surefire dự kiến ghi tóm tắt:

```text
Tests run: 5, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
```

Đây là các dòng **tóm tắt nội dung mong đợi**, không phải toàn bộ log cố định.

Chạy đủ Failsafe:

```bash
mvn -B clean verify
```

Dự kiến:

```text
Surefire: Tests run: 5, Failures: 0, Errors: 0, Skipped: 0
Failsafe: Tests run: 1, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
```

Trong log thật, các nhãn “Surefire:” và “Failsafe:” ở trên là nhãn giải thích, không nhất thiết nằm ngay trước dòng tests run. Các XML reports mới là bằng chứng có thể kiểm tự động.

### 8.1. Reports ở đâu?

```text
target/
├── classes/vn/example/tests/
│   ├── Calculator.class
│   └── App.class
├── test-classes/vn/example/tests/
│   ├── CalculatorTest.class
│   └── AppIT.class
├── surefire-reports/
│   └── TEST-vn.example.tests.CalculatorTest.xml
├── failsafe-reports/
│   ├── TEST-vn.example.tests.AppIT.xml
│   └── failsafe-summary.xml
└── test-discovery-lab-1.0.0.jar
```

Có thể có `*.txt`, runtime/log files khác. Đường dẫn reports thay đổi nếu plugin cấu hình `reportsDirectory` custom. Với cấu hình mặc định ở ví dụ, script ở mục 11 đọc đúng các file `TEST-*.xml`.

### 8.2. Chạy một unit test cụ thể

```bash
mvn -B -Dtest=CalculatorTest test
mvn -B -Dtest=CalculatorTest#tenPercentDiscount test
```

Với test selector `-Dtest=MissingTest`, Surefire mặc định `failIfNoSpecifiedTests=true`, nên yêu cầu chọn test không tồn tại thường làm Maven fail. **`failIfNoSpecifiedTests` khác `failIfNoTests`**: cái đầu chỉ áp khi user chỉ định selector, cái sau áp cho trường hợp suite rỗng theo cấu hình.

### 8.3. Chọn một integration test

```bash
mvn -B -Dit.test=AppIT verify
```

`-Dit.test` dành cho Failsafe, không phải Surefire. Surefire vẫn chạy các unit tests trong phase `test` (trừ khi skip theo cấu hình). Nếu chỉ gọi `mvn test`, Failsafe chưa tới phase integration-test/verify.

## 9. Tạo tình huống lỗi có chủ đích để kiểm giải pháp

Thực hiện trên **bản sao hoặc nhánh thí nghiệm**, sau đó hoàn nguyên.

### 9.1. Đổi CalculatorTest thành CalculatorSpec

Đổi file:

```text
CalculatorTest.java -> CalculatorSpec.java
```

Đổi class trong file thành `CalculatorSpec`. Không đổi `AppIT`. Khi chạy:

```bash
mvn -B clean test
```

Surefire không tìm thấy unit test phù hợp; POM mẫu bật `failIfNoTests=true` nên **build fail**. Nếu xóa `failIfNoTests=true` để trở về default false, Maven có thể `BUILD SUCCESS` nhưng không unit test nào được chạy — chính là lỗi cần ngăn.

**Khôi phục:** đổi lại class và file `CalculatorTest`, rồi chạy `mvn -B clean verify`. Không commit bản test tên sai.

### 9.2. Gọi Maven với skip flag

```bash
mvn -B -Dmaven.test.skip=true clean verify
```

Flag này skip test compilation/execution ở các plugins hỗ trợ. Do các goals bị skip có chủ đích, `failIfNoTests=true` không thay thế được CI gate kiểm executed tests. Build vẫn có thể thành công.

**Khôi phục:** chạy `mvn -B clean verify` không có skip flag. Để không nhầm reports cũ, phải dùng `clean` hoặc clean workspace trước bước đếm.

### 9.3. Chỉ giữ AppIT nhưng không cấu hình Failsafe

Nếu project chỉ có `AppIT.java` nhưng Failsafe executions bị bỏ, `mvn verify` không mặc nhiên chạy nó. Surefire cũng không match `*IT`. Với default `failIfNoTests=false`, build có thể thành công dù không test nào chạy. **Sửa Failsafe POM + phase + reports**, không ép đổi tên tất cả IT thành `*Test` để Surefire chạy nhầm lifecycle.

## 10. failIfNoTests và những giới hạn của nó

Surefire strict cho module **bắt buộc** có unit tests:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-surefire-plugin</artifactId>
    <version>3.6.1</version>
    <configuration>
        <failIfNoTests>true</failIfNoTests>
    </configuration>
</plugin>
```

Failsafe strict cho module **bắt buộc** có IT:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-failsafe-plugin</artifactId>
    <version>3.6.1</version>
    <configuration>
        <failIfNoTests>true</failIfNoTests>
    </configuration>
    <!-- Cần execution integration-test và verify như POM mẫu -->
</plugin>
```

Hai đoạn là fragments; POM chạy được nằm ở mục 7. Có thể dùng:

```bash
mvn -B -DfailIfNoTests=true clean test
```

Nhưng user property `failIfNoTests` có thể áp dụng cho cả Surefire/Failsafe khi goals chạy. Trong reactor có POM-only modules hoặc modules không có IT, **không bật blanket rule này** mà chưa xác định module nào bắt buộc có test gì.

### 10.1. All skipped không luôn bị failIfNoTests bắt

```java
package vn.example.tests;

import org.junit.jupiter.api.Disabled;
import org.junit.jupiter.api.Test;

class DisabledExampleTest {
    @Disabled("excluded during migration")
    @Test
    void neverRuns() {
        throw new AssertionError("should never be executed");
    }
}
```

Ví dụ này match naming và có JUnit test case nhưng bị marked skipped. Có thể report `tests=1, skipped=1, executed=0`. `failIfNoTests` không phải đảm bảo “ít nhất một assertion đã chạy”. Vì vậy cần XML gate kiểm `tests-skipped > 0` và threshold.

### 10.2. Filters có thể làm zero executed

- `<includes>` không khớp bất kỳ compiled class.
- `<excludes>` loại hết tests.
- `-Dtest=...` hoặc `-Dit.test=...` chọn sai.
- JUnit `@Tag`, `groups`/`excludedGroups` và engine filters chọn một nhóm không tồn tại.
- `@DisabledOnOs`/`@EnabledIfEnvironmentVariable` loại hết invocations trên CI.
- `@TestFactory` trả empty stream hoặc parameterized test không có input hợp lệ (hành vi cụ thể tùy framework/version).
- `@Nested` test setup/engine discovery khác với provider/test class filters.

Vì vậy kiểm Maven logs, selected provider và XML report counts thay vì đoán chỉ từ file names.

## 11. CI gate kiểm số unit/IT executed từ XML

Một CI script **Python 3 runnable** đọc `target/surefire-reports` và `target/failsafe-reports` sau `mvn -B clean verify`. Lưu đoạn sau thành `check_test_reports.py` ở root project:

```python
#!/usr/bin/env python3
from pathlib import Path
from xml.etree import ElementTree as ET

groups = {
    "surefire": (
        Path("target/surefire-reports"),
        5,
    ),
    "failsafe": (
        Path("target/failsafe-reports"),
        1,
    ),
}

for name, (folder, min_executed) in groups.items():
    files = sorted(folder.glob("TEST-*.xml"))
    if not files:
        raise SystemExit(f"ERROR: no {name} test XML reports")

    tests = skipped = failures = errors = 0
    for file in files:
        suite = ET.parse(file).getroot()
        if suite.tag != "testsuite":
            raise SystemExit(f"ERROR: unexpected XML root in {file}")
        tests += int(suite.attrib.get("tests", "0"))
        skipped += int(suite.attrib.get("skipped", "0"))
        failures += int(suite.attrib.get("failures", "0"))
        errors += int(suite.attrib.get("errors", "0"))

    executed = tests - skipped
    print(
        f"{name}: tests={tests} skipped={skipped} "
        f"executed={executed} failures={failures} errors={errors}"
    )
    if failures or errors:
        raise SystemExit(f"ERROR: {name} had test failures/errors")
    if executed < min_executed:
        raise SystemExit(
            f"ERROR: {name} executed={executed}; "
            f"minimum required={min_executed}"
        )

print("Test execution gate: PASS")
```

Khi build lab đúng, stdout dự kiến của riêng script:

```text
surefire: tests=5 skipped=0 executed=5 failures=0 errors=0
failsafe: tests=1 skipped=0 executed=1 failures=0 errors=0
Test execution gate: PASS
```

**Điều kiện:** CI có Python 3, các XML reports dạng Surefire/Failsafe chuẩn với root `testsuite` và report directories mặc định. Nếu project dùng `reportsDirectory` khác, điều chỉnh paths. Script kiểm *cả* tổng tests và số executed, và fail nếu thiếu reports.

### 11.1. Tại sao cần clean trước parser?

```bash
mvn -B clean verify
python3 check_test_reports.py
```

Không có `clean`, XML từ build cũ có thể vẫn ở `target`. Nếu lần hiện tại skip tests, script có thể đọc report cũ và pass giả. Dùng clean checkout/clean phase và thu reports **cùng CI job**. Maven command phải pass và script cũng phải pass, không dùng `mvn -fn` để che Maven failure.

CI shell driver:

```bash
#!/usr/bin/env sh
set -eu

java -version
mvn --version
mvn -B --no-transfer-progress clean verify
python3 check_test_reports.py
```

Script trên không tự cài JDK/Maven/Python3; CI runner phải cung cấp toolchain và checkout. Lệnh `set -eu` giúp dừng job khi Maven hoặc report gate lỗi.

### 11.2. Gate multi-module phải kiểm đúng từng module

Với reactor:

```text
parent/pom.xml
service-a/target/surefire-reports/TEST-*.xml
service-b/target/surefire-reports/TEST-*.xml
app/target/failsafe-reports/TEST-*.xml
```

Script một module cần được **mở rộng** để duyệt paths đúng cho từng module. Đừng chỉ kiểm tổng tests toàn repo >0; module A có 200 tests có thể che module B zero tests.

Ví dụ test policy (đây là YAML **mô tả**, không phải cấu hình Maven tự đọc):

```yaml
modules:
  service-a:
    minimumUnitExecuted: 5
    minimumIntegrationExecuted: 0
  service-b:
    minimumUnitExecuted: 3
    minimumIntegrationExecuted: 0
  app:
    minimumUnitExecuted: 4
    minimumIntegrationExecuted: 2
  parent:
    minimumUnitExecuted: 0
    minimumIntegrationExecuted: 0
```

CI parser phải biết **scope Reactor thực tế** `-pl/-am/-N` và chỉ so modules được kỳ vọng trong job đó. Root `packaging=pom` không cần các tests như JAR module có logic nghiệp vụ. Nếu parent áp `failIfNoTests=true` lên mọi child không phân biệt, build có thể fail sai policy.

## 12. Chẩn đoán bằng effective POM và dependency tree

### 12.1. Effective POM

```bash
mvn -B help:effective-pom -Doutput=target/effective-pom.xml
mvn -B help:active-profiles
```

Dùng để xác định:

- Surefire/Failsafe plugin version và executions thật sau inheritance.
- `skip`, `skipTests`, `failIfNoTests`, `includes`, `excludes`, `testSourceDirectory`, `testClassesDirectory`.
- Parent/profile có vô tình thay execution phase không.
- `pluginManagement` chỉ quản lý plugin; Failsafe execution đã active ở `build/plugins` module chưa.
- JUnit Jupiter dependencies/versions/properties sau profiles/BOM.
- `packaging` và child module coordinates.
- Maven settings active profiles có thay sources/dependencies/repositories.

**Không sửa generated effective POM**: sửa POM thật/parent/profile tương ứng, rồi chạy clean verify. Khi chia sẻ output này, rà soát nội dung settings/repository/internal URLs và secrets.

### 12.2. Dependency tree

```bash
mvn -B dependency:tree -Dscope=test
```

Kiểm Jupiter API/Engine, JUnit Platform versions, JUnit Vintage Engine nếu có JUnit 4 tests, TestNG dependencies khi dùng TestNG. API present nhưng Engine bị exclude hoặc conflict là nguyên nhân Maven không chạy tests như IDE runner mong đợi.

### 12.3. Maven debug logs

```bash
mvn -B -X clean test
```

`-X` có thể in plugin configuration, provider/test classpath, includes/excludes và active properties. Chỉ dùng khi log thông thường + reports không đủ, và không chia sẻ nguyên debug output chứa đường dẫn/credentials nội bộ. Đừng dùng cache purge toàn bộ `~/.m2/repository` làm bước đầu; nó không sửa naming/flags/engine.

## 13. Khác biệt IDE và Maven CLI

IntelliJ IDEA, Eclipse và VS Code Java extensions có thể chạy tests trực tiếp bằng IDE/JUnit runner. IDE có thể:

- Chạy `CalculatorSpec` khi click Run cạnh `@Test` dù Surefire mặc định không include `*Spec`.
- Dùng dependencies/module path có thêm libraries thủ công không xuất hiện trong POM.
- Bật Maven profile khác CI.
- Chọn khác JDK version hoặc test engine.
- Nhận test folder do user đánh dấu thủ công mà Maven `src/test/java` không biết.
- Chạy selected single method thay vì toàn suite được Maven kiểm.

**Cách kiểm chuẩn:** chạy `mvn -B clean verify` trong terminal với đúng Maven/JDK/settings như CI, đọc XML reports, sửa naming/POM/plugin config rồi reimport/sync Maven project vào IDE. Không thêm test library ở IDE Project Structure như một thay thế cho dependency Maven.

## 14. Multi-module: parent xanh không có nghĩa child tests đã chạy

Các tình huống điển hình:

- Root có `packaging=pom`, không có unit tests; điều đó bình thường.
- Child module `library` có tests nhưng chỉ chạy `mvn -N verify` từ root; child không được build.
- CI gọi `mvn -pl :api verify` và bỏ modules khác; kết quả không đại diện full reactor.
- `-Dtest=CalculatorTest` từ root fail ở các child không có class; cần scope module đúng, không tắt fail gates toàn cục.
- Có `<pluginManagement>` ghi Failsafe version nhưng không có active execution trong child nên IT không chạy.
- Maven Reactor có upstream failure khiến downstream modules `SKIPPED`; missing reports là do reactor không chạy module, không phải JUnit `@Disabled`.
- Chạy `mvn -T 2` cho reactor không tự song song hóa mỗi JUnit method và không tự làm Failsafe chạy khi chưa bind.

Một policy tốt xác định module nào phải có unit/IT tests, khi nào tổng có thể zero hợp lệ, rồi kiểm XML per-module. Không dùng “100 tests ở toàn repo” để bỏ qua một module vừa thay code nhưng mất tests vì profile/naming.

## 15. Bảng lỗi nhanh

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `BUILD SUCCESS`, 0 tests | Default `failIfNoTests=false` | Bật strict theo module và kiểm XML |
| `No sources to compile` | Sai `src/test/java` hoặc custom source root | Sửa source root/POM |
| Có `.class`, không chạy test | Naming, filters, engine sai | Kiểm patterns/provider/classpath |
| `CalculatorSpec` chạy IDE, Maven không | Surefire default không include `*Spec` | Rename hoặc includes |
| `AppIT` không chạy `mvn test` | Failsafe thuộc integration-test/verify | Bind goals và chạy verify |
| `mvn verify` không có failsafe reports | Failsafe chưa active trong plugin executions | Cấu hình `integration-test` + `verify` |
| `-DskipTests` vẫn xanh | Unit test execution bị skip | Bỏ flag ở CI và kiểm reports |
| `-Dmaven.test.skip=true` | Bỏ cả compile và chạy tests | Gỡ flag, clean verify |
| JUnit API compile, 0 tests | Engine/provider thiếu hoặc bị lọc | Khai Jupiter aggregator/engine |
| JUnit4 `@Test` trong Jupiter-only project | Annotation/provider mismatch | Thêm Vintage tương thích hoặc migrate |
| `Tests run: 5, Skipped: 5` | `@Disabled`/conditions | Kiểm executed, không chỉ tests |
| Reports có nhưng test chạy hôm trước | Không `clean` trước check | Clean workspace/target |
| Plugin hard-code `<skipTests>true` | CLI override không tác dụng | Sửa POM/parent config |
| `-Dtest=Unknown` fail | Default `failIfNoSpecifiedTests=true` | Sửa selector, không che lỗi |
| Root Maven pass, child không có report | `-N`/`-pl` chọn sai | Kiểm Reactor Summary/scope |
| Parent không có test | `packaging=pom` hợp lệ | Không áp blanket strict gate |
| CI chỉ kiểm tổng tests >0 | Module khác che zero của module này | Per-module thresholds |
| TestNG/JUnit engine filter lọc sạch | groups/tags/include engines sai | Kiểm effective POM và provider |
| `mvn -fn` dù failure exit 0 | Fail-never che lỗi | Không dùng trong CI gates |
| `-X` log chứa credentials | Chia sẻ debug log không lọc | Rà soát/redact trước khi chia sẻ |

## 16. Quy trình điều tra theo thứ tự

1. Ghi lại exact CI/Maven command, JDK, branch và selected reactor modules.
2. Chạy `java -version` và `mvn --version`.
3. Chạy `mvn -B clean test`, xác nhận Surefire có được gọi.
4. Kiểm `src/test/java` và `target/test-classes`.
5. Kiểm naming patterns mặc định hoặc includes/excludes.
6. Xem `@Test` import, Jupiter Engine/JUnit Platform provider.
7. Xem `skipTests`, `maven.test.skip`, `skipITs`, profiles và POM inheritance.
8. Chạy `mvn -B clean verify`, xác nhận Failsafe `integration-test` + `verify`.
9. Đọc XML reports mới, tính `executed = tests - skipped`.
10. Đối chiếu test counts tối thiểu của đúng module/loại tests.
11. Nếu khó xác định, xem effective POM/dependency tree và debug logs đã rà soát.
12. Chạy lại clean verify và CI gate sau sửa, không chấp nhận success khi executed=0.

## 17. Những cách chữa sai cần tránh

**Không tắt test để bảo đảm build xanh:**

```bash
mvn -DskipTests package
mvn -Dmaven.test.skip=true install
```

Hai lệnh có thể hữu ích khi bạn chủ đích package để debug, nhưng **không thay test verification trước release**.

**Không tạo một test giả:**

```java
@Test
void alwaysPasses() {
    assertTrue(true);
}
```

Đây chỉ là fragment minh họa một anti-pattern; test không assert hành vi nghiệp vụ có thể làm test count dương mà không mang giá trị. Nên viết tests kiểm happy path, boundary, invalid inputs và integration contracts.

**Không giải quyết bằng cách xóa `~/.m2/repository` ngay lập tức.** Bắt đầu từ names/phases/config/providers; xóa cache không thay test naming hay bỏ skip flag.

**Không xem “IDE chạy được” là bằng chứng CI chạy được.** IDE runner và Maven Surefire có khác biệt về discovery, profiles và classpath; phải kiểm Maven CLI + reports.

## 18. Câu hỏi ôn tập có đáp án

**Câu 1.** `BUILD SUCCESS` có chứng minh unit tests đã chạy không?

**Đáp án:** Không; Surefire mặc định `failIfNoTests=false`. Cần kiểm reports/actual executed count.

**Câu 2.** `PriceSpec.java` có được Surefire chạy mặc định không?

**Đáp án:** Không; đổi thành `PriceTest` hoặc khai `includes` có `*Spec`.

**Câu 3.** `mvn test-compile` có chạy `@Test` không?

**Đáp án:** Không; đó là phase compile test source, khác `mvn test`.

**Câu 4.** `-DskipTests` khác `-Dmaven.test.skip` thế nào?

**Đáp án:** SkipTests thường bỏ test execution nhưng vẫn compile test sources; Maven.test.skip bỏ cả test compile và execution.

**Câu 5.** Vì sao `AppIT` không chạy ở `mvn test`?

**Đáp án:** Theo convention, `*IT` thường do Failsafe ở integration-test/verify chạy khi đã bind goals.

**Câu 6.** Sao phải có `failsafe:verify`?

**Đáp án:** Nó kiểm kết quả IT sau phase chạy/dọn môi trường; `mvn verify` là điểm kết thúc phù hợp.

**Câu 7.** JUnit Jupiter API đủ để Surefire thực thi test không?

**Đáp án:** Chưa chắc; cần Jupiter Engine/JUnit Platform provider runtime tương thích.

**Câu 8.** JUnit5 test class package-private có hợp lệ không?

**Đáp án:** Có; không bắt buộc public, nhưng annotation/signature phải đúng.

**Câu 9.** `failIfNoTests=true` có chắc phát hiện mọi test `@Disabled` không?

**Đáp án:** Không; có thể chúng được discovery và marked skipped. Kiểm `executed=tests-skipped`.

**Câu 10.** Vì sao nên dùng `clean verify` trước khi parse XML?

**Đáp án:** Để không đọc report cũ từ build trước khi lần hiện tại bỏ test execution.

**Câu 11.** `-Dtest=MissingTest` thường fail dù default no-tests đôi khi pass vì sao?

**Đáp án:** `failIfNoSpecifiedTests` mặc định true, khác `failIfNoTests` mặc định false.

**Câu 12.** Reactor có 100 tests tổng cộng đủ chứng minh mỗi module đều chạy tests không?

**Đáp án:** Không. Cần threshold theo module để một module không bị module khác che.

**Câu 13.** Vì sao không thêm JUnit JAR thủ công trong IDE để chữa CLI?

**Đáp án:** CLI/CI resolve dependencies theo POM; IDE-only classpath không được tái lập.

**Câu 14.** `-DskipITs` có phải luôn tắt Surefire unit tests không?

**Đáp án:** Không; nó nhắm Failsafe IT. Kiểm plugin version và POM config.

**Câu 15.** Test count=5 mà skipped=5, failures=0 có đủ pass không?

**Đáp án:** Không có test executed; CI gate cần yêu cầu minimum executed > 0 theo policy.

## 19. Checklist trước khi chấp nhận BUILD SUCCESS

- [ ] Maven command đi tới đúng `test`/`integration-test`/`verify` phases.
- [ ] `src/test/java` được biên dịch và có test classes trong `target/test-classes`.
- [ ] Unit test class names khớp Surefire default hoặc includes được khai rõ.
- [ ] IT class names khớp Failsafe, và goals `integration-test`/`verify` đã bind.
- [ ] JUnit Jupiter/engines/providers có mặt trong test runtime dependencies.
- [ ] Surefire/Failsafe versions được pin; không dùng bản cũ thiếu framework support.
- [ ] Không có `skipTests`/`maven.test.skip`/`skipITs` ngoài dự kiến.
- [ ] Parent/profile/CI scripts không vô tình disable tests.
- [ ] `failIfNoTests=true` áp cho modules buộc có tests, không ép POM-only modules.
- [ ] `failIfNoSpecifiedTests` không bị vô hiệu hóa để che test selector sai.
- [ ] Reports trong `target/surefire-reports` và `target/failsafe-reports` là của clean build hiện tại.
- [ ] CI tính `executed=tests-skipped`, yêu cầu threshold theo module và kiểm failures/errors.
- [ ] Cả Maven exit code và XML gate đều PASS.
- [ ] Không có test giả chỉ tăng report count mà không kiểm hành vi.
- [ ] Java 17 demo có 5 unit methods, 1 IT, stdout `netCents=900`.

## 20. Tài liệu chính thức

- [Apache Maven Surefire — test goal parameters](https://maven.apache.org/surefire/maven-surefire-plugin/test-mojo.html)
- [Apache Maven Surefire — test inclusions/exclusions](https://maven.apache.org/surefire/maven-surefire-plugin/examples/inclusion-exclusion.html)
- [Apache Maven Surefire — JUnit Platform](https://maven.apache.org/surefire/maven-surefire-plugin/examples/junit-platform.html)
- [Apache Maven Surefire — skipping tests](https://maven.apache.org/surefire/maven-surefire-plugin/examples/skipping-tests.html)
- [Apache Maven Failsafe — overview and goals](https://maven.apache.org/surefire/maven-failsafe-plugin/)
- [Apache Maven Failsafe — inclusions/exclusions](https://maven.apache.org/surefire/maven-failsafe-plugin/examples/inclusion-exclusion.html)
- [Apache Maven Failsafe — integration-test goal](https://maven.apache.org/surefire/maven-failsafe-plugin/integration-test-mojo.html)
- [Apache Maven Failsafe — verify goal](https://maven.apache.org/surefire/maven-failsafe-plugin/verify-mojo.html)
- [Apache Maven — build lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Apache Maven — working with multiple modules](https://maven.apache.org/guides/mini/guide-multiple-modules.html)
- [JUnit User Guide](https://docs.junit.org/current/user-guide/)
