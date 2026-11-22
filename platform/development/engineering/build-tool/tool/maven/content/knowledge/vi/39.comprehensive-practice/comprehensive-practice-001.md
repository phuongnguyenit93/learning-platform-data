# Tạo thư viện Java với POM, Maven Wrapper và kiểm thử tự động — bài thực hành tổng hợp

## 1. Kết quả cuối cùng cần đạt

Trong bài thực hành này, bạn xây dựng một **thư viện Java 17** tên `discount-core`, không phải một ứng dụng có `main()` riêng. Thư viện cung cấp API tính **giá sau chiết khấu** với `BigDecimal`. Người học sẽ tạo Maven POM đầy đủ, sử dụng **Maven Wrapper** để thống nhất Maven version, tự động chạy **JUnit Jupiter 5 tests** bằng **Maven Surefire Plugin**, đóng gói JAR, cài JAR vào Maven local repository và cho một dự án Java khác gọi API.

Đề bài thuộc nhóm **Thực hành tổng hợp**: cần liên kết Java source → POM → Wrapper → test → package → verify → install → consumer → CI, chứ không chỉ chạy một vài lệnh Maven rời rạc.

**Điều kiện hoàn thành:**

1. Có thư mục `src/main/java` chứa class thư viện public, API và validation rõ.
2. Có `pom.xml` `packaging=jar`, groupId/artifactId/version đúng và compiler target Java 17.
3. Có Maven Wrapper scripts `mvnw`, `mvnw.cmd` và `.mvn/wrapper/maven-wrapper.properties`.
4. Có JUnit 5 tests ở `src/test/java`, được Surefire thực thi tự động.
5. Lệnh `./mvnw -B -ntp clean verify` thành công **và có test thật được thực thi**.
6. JAR có thư viện class, không vô tình đóng test classes vào runtime artifact.
7. `./mvnw -B -ntp install` cài artifact với GAV cố định vào local Maven repository.
8. Consumer project độc lập khai dependency đó và chạy code demo với output xác định.
9. Có workflow CI chạy lại cùng bộ kiểm thử khi push/pull request.
10. Hiểu cách chẩn đoán những lỗi Wrapper, dependency, compiler, test discovery, packaging và local install thường gặp.

Mọi mã nguồn, POM, test, workflow trong bài là **mẫu dự án độc lập để tự thực hành**. Không yêu cầu chỉnh sửa các dự án người dùng đang triển khai; đường dẫn chỉ mang tính hướng dẫn.

## 2. Phần mềm và phiên bản chọn cho bài

| Thành phần | Phiên bản bài dùng | Vai trò |
| --- | --- | --- |
| JDK | 17 trở lên | Biên dịch/chạy Java 17 |
| Apache Maven | 3.9.9 | Maven build runtime, pin qua Wrapper |
| Apache Maven Wrapper Plugin | 3.3.4 | Sinh Maven Wrapper scripts |
| Maven Compiler Plugin | 3.13.0 | Biên dịch source `--release 17` |
| Maven Surefire Plugin | 3.2.5 | Chạy unit tests JUnit 5 |
| JUnit Jupiter | 5.11.4 | Test API, parameterized tests và engine |
| Maven Clean Plugin | 3.3.2 | Xóa build output có kiểm soát |
| Maven Resources Plugin | 3.3.1 | Xử lý `src/main/resources` khi có |
| Maven JAR Plugin | 3.4.2 | Đóng gói JAR |
| Maven Source Plugin | 3.3.1 | Gắn thêm `-sources.jar` |
| Maven Install Plugin | 3.1.2 | Cài artifact vào local repository |

Đây là **bộ versions cụ thể để lab tái lập được**, không phải tuyên bố các bản mới nhất ở thời điểm đọc. Khi nâng phiên bản, đọc release notes và test lại trước khi đổi POM.

Kiểm tra môi trường:

~~~bash
java -version
javac -version
mvn -version
~~~

Để sinh Wrapper lần đầu, máy cần có Maven cài sẵn hoặc một môi trường có thể gọi Maven Wrapper Plugin. Sau khi commit Wrapper scripts, thành viên khác **không cần cài Maven thủ công**, nhưng vẫn cần JDK hợp lệ và khả năng tải Maven distribution lần đầu.

**Wrapper khóa Maven version, không tự cài JDK 17.** CI phải cấu hình JDK riêng.

## 3. Cấu trúc dự án thư viện

Tạo directory mới:

~~~text
discount-core/
├── pom.xml
├── README.md                  (tùy chọn, tài liệu sử dụng)
├── .gitignore
├── mvnw                       (Wrapper sẽ tạo)
├── mvnw.cmd                   (Wrapper sẽ tạo)
├── .mvn/
│   └── wrapper/
│       └── maven-wrapper.properties
├── src/
│   ├── main/
│   │   └── java/
│   │       └── dev/learning/money/
│   │           └── Discounts.java
│   └── test/
│       └── java/
│           └── dev/learning/money/
│               └── DiscountsTest.java
└── target/                    (Maven tự tạo, không commit)
~~~

Tại thời điểm bắt đầu, chỉ cần tạo `pom.xml` và hai file Java; Wrapper và `target/` xuất hiện theo các bước sau. Package name `dev.learning.money` phải khớp cấu trúc source path tương ứng. `src/main/java` chứa **production code**; `src/test/java` chứa tests, không đưa thẳng tests vào main JAR.

Đừng đặt Java source của thư viện trong `src/test/java`, bởi consumers sẽ không tìm thấy API trong JAR chính.

## 4. Thiết kế API trước khi viết POM

Ta xây dựng một utility class:

~~~java
public final class Discounts {
    public static BigDecimal finalPrice(BigDecimal original, int percent)
}
~~~

Đây là **chữ ký minh họa**, class hoàn chỉnh ở phần 8. Quy tắc nghiệp vụ:

- `original` là số tiền gốc **không âm**, dùng `BigDecimal`; không nhận null.
- `percent` là số nguyên từ **0 đến 100**, bao gồm hai đầu.
- Trả về giá sau giảm theo công thức `original × (100 − percent) / 100`.
- Kết quả **luôn có hai chữ số thập phân**, làm tròn `RoundingMode.HALF_UP`.
- `null` gây `NullPointerException` với thông báo `original`.
- Giá âm hoặc phần trăm ngoài khoảng gây `IllegalArgumentException`.
- Không dùng `double` để biểu diễn số tiền vì có thể gặp sai số nhị phân khi làm việc với decimal fractions.

Ví dụ đã tính theo quy tắc:

| Giá gốc | Giảm | Giá cuối |
| --- | ---: | ---: |
| 199.99 | 15% | 169.99 |
| 100 | 0% | 100.00 |
| 100 | 100% | 0.00 |
| 0.015 | 0% | 0.02 |
| 0.01 | 1% | 0.01 |

Cụ thể `199.99 × 0.85 = 169.9915` → hai chữ số thập phân theo HALF_UP là `169.99`. `0.015` làm tròn thành `0.02`. Hãy coi **quy tắc rounding là hợp đồng API**; một hệ thống thanh toán thực tế có thể đòi quy tắc tiền tệ khác.

## 5. Maven coordinates xác định thư viện

Thư viện dùng Maven coordinates:

~~~text
groupId    = dev.learning.money
artifactId = discount-core
version    = 1.0.0
packaging  = jar
~~~

GAV `dev.learning.money:discount-core:1.0.0` được consumers dùng trong `<dependency>`. `groupId` thường tương ứng tổ chức/package namespace; `artifactId` là tên module; `version` xác định phát hành. Có thể dùng `1.0.0-SNAPSHOT` trong giai đoạn phát triển, nhưng bài dùng bản `1.0.0` cố định để minh họa consumer installation.

Không để version là một từ không kiểm soát như `LATEST` hoặc `RELEASE` trong một release build yêu cầu tái lập.

## 6. POM hoàn chỉnh của thư viện

File `discount-core/pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.learning.money</groupId>
    <artifactId>discount-core</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>
    <name>Discount Core</name>
    <description>Java 17 utility library for discount calculations</description>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <project.build.outputTimestamp>2024-01-01T00:00:00Z</project.build.outputTimestamp>
        <junit.jupiter.version>5.11.4</junit.jupiter.version>
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
                <artifactId>maven-install-plugin</artifactId>
                <version>3.1.2</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Đây là một **POM đầy đủ**; người học chỉ cần tạo chính xác file này. Không cần parent POM, BOM hay private repository trong lab.

### Vì sao JUnit nằm ở test scope?

`junit-jupiter` cung cấp API để biên dịch test và engine cần thiết để thực thi tests. `<scope>test</scope>` khiến nó nằm trong test classpath, không phải runtime dependency mà một consumer của `discount-core` phải tải chỉ để dùng `Discounts.finalPrice`.

Còn production class `Discounts` chỉ dùng Java standard library (`BigDecimal`, `Objects`, `RoundingMode`), nên **không cần external runtime dependency**. Điều này làm JAR đơn giản, ít rủi ro classpath và dễ tái sử dụng.

### Vai trò của từng plugin

| Plugin | Mục đích trong lab |
| --- | --- |
| Clean | Xóa build outputs cũ trước khi đo/kiểm tra build sạch |
| Resources | Copy/filter resources nếu có |
| Compiler | Dùng JDK17+ với `--release 17` |
| Surefire | Phát hiện và chạy JUnit Jupiter tests ở test phase |
| JAR | Tạo `discount-core-1.0.0.jar` |
| Source | Tạo `discount-core-1.0.0-sources.jar` khi package |
| Install | Cài artifacts vào local Maven repository |

`project.build.outputTimestamp` giúp các archiver plugins tương thích đặt thời gian file entry có thể tái lập. Nó **không bảo đảm** mọi byte và dependency của build tự động deterministic; cần kiểm tra plugin versions, môi trường, input files và timestamps khác khi yêu cầu reproducible builds nghiêm ngặt.

## 7. Vì sao maven.compiler.release không thay thế JAVA_HOME?

`<maven.compiler.release>17</maven.compiler.release>` yêu cầu Compiler Plugin sử dụng target API/classfile tương ứng Java 17 thông qua `--release` trên JDK hỗ trợ. Nhưng nếu Maven đang chạy bằng JDK 11 và không có toolchain phù hợp, Maven vẫn có thể không biên dịch được source Java 17.

Kiểm tra Maven thực dùng Java nào:

~~~bash
./mvnw -version
~~~

Thông tin output thường chứa Maven version, Java version, Java home và OS. Wrapper pin **Maven**, không tự ép `JAVA_HOME` thành JDK 17. Trên CI ta sẽ dùng `actions/setup-java` để cài JDK phù hợp.

Nếu Java compiler báo `release version 17 not supported`, hãy kiểm tra JDK của Maven, không chỉ sửa dòng POM rồi thử lại vô hạn.

## 8. File Discounts.java hoàn chỉnh

File `src/main/java/dev/learning/money/Discounts.java`:

~~~java
package dev.learning.money;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Objects;

/**
 * Pure Java 17 discount calculations with two-decimal HALF_UP output.
 */
public final class Discounts {

    private static final BigDecimal HUNDRED = BigDecimal.valueOf(100);

    private Discounts() {
        throw new AssertionError("Utility class must not be instantiated");
    }

    /**
     * Returns original * (100 - percent) / 100, rounded to 2 decimals.
     *
     * @param original non-negative monetary amount, must not be null
     * @param percent integer discount percentage from 0 through 100
     * @return final amount with scale 2
     * @throws NullPointerException if original is null
     * @throws IllegalArgumentException if original is negative or
     *         percent is outside the [0, 100] range
     */
    public static BigDecimal finalPrice(
            BigDecimal original,
            int percent) {

        Objects.requireNonNull(original, "original");

        if (original.signum() < 0) {
            throw new IllegalArgumentException(
                    "original must not be negative");
        }

        if (percent < 0 || percent > 100) {
            throw new IllegalArgumentException(
                    "percent must be between 0 and 100");
        }

        BigDecimal multiplier = BigDecimal.valueOf(100L - percent);

        return original.multiply(multiplier)
                .divide(HUNDRED, 2, RoundingMode.HALF_UP);
    }
}
~~~

### Phân tích hợp đồng của API

- `final class`: không cho subclass mở rộng utility class sai mục đích.
- Constructor `private`: không cần tạo instance; method thuần.
- `HUNDRED` là constant `BigDecimal` bất biến.
- `Objects.requireNonNull` cho thông báo rõ nếu truyền null.
- `signum() < 0` từ chối mọi giá âm.
- `percent` được kiểm tra 0..100, kể cả hai đầu.
- `100L - percent` an toàn vì giá trị đã được kiểm tra.
- `multiply` và `divide(HUNDRED, 2, HALF_UP)` dùng decimal arithmetic, không dùng floating-point double.
- Kết quả có **scale 2** ngay cả khi original là `BigDecimal("100")`.

**Không dùng `new BigDecimal(0.1)`** trong money code. Nếu cần nhập decimal literal, dùng `new BigDecimal("0.1")` hoặc `BigDecimal.valueOf(0.1)` trong trường hợp đã hiểu nguồn double.

## 9. Tại sao không trả double?

Ví dụ kiểu nên tránh khi cần decimal money exactness:

~~~java
double result = 199.99 * (1.0 - 0.15);
~~~

Đoạn này là **minh họa**, không thuộc thư viện cuối cùng. Double là binary floating-point, không biểu diễn chính xác mọi số thập phân như `0.1`. Việc `System.out.println` đôi khi in ra một chuỗi trông hợp lý không chứng minh phép toán an toàn cho tiền tệ.

Với `BigDecimal`, nên quy định thêm scale/rounding, input validation và currency conventions. Lab cố ý lấy hai chữ số thập phân để minh họa, **không tự tuyên bố mọi currency đều dùng hai decimal places**.

## 10. Thiết kế tests trước khi chạy

Các test cases tối thiểu:

| Case | Input | Expected | Điều cần chứng minh |
| --- | --- | --- | --- |
| Giảm 15% | 199.99, 15 | 169.99 | Công thức đúng |
| Không giảm | 100, 0 | 100.00 | Biên 0% và scale |
| Giảm hết | 100, 100 | 0.00 | Biên 100% |
| Rounding nhỏ | 0.01, 1 | 0.01 | HALF_UP rounding |
| Giá bằng zero | 0, 25 | 0.00 | Biên số tiền |
| Half-cent | 0.015, 0 | 0.02 | HALF_UP tại mốc .005 |
| Null | null, 10 | NullPointerException | Defensive API |
| Số tiền âm | -0.01, 10 | IllegalArgumentException | Validation |
| Discount âm | 1.00, -1 | IllegalArgumentException | Biên dưới |
| Discount quá 100 | 1.00, 101 | IllegalArgumentException | Biên trên |

Có thể thực hiện những cases đó bằng 5 bộ dữ liệu parameterized + một test rounding + một test null + một test negative + hai bộ dữ liệu percent invalid, tổng cộng **10 lượt test** nếu tất cả được JUnit 5 phát hiện.

**Lưu ý**: Một method `@ParameterizedTest` có thể tạo nhiều test invocations, vì vậy số lượt báo trong Surefire có thể lớn hơn số method trong source.

## 11. JUnit 5: DiscountsTest.java hoàn chỉnh

File `src/test/java/dev/learning/money/DiscountsTest.java`:

~~~java
package dev.learning.money;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;
import org.junit.jupiter.params.provider.ValueSource;

class DiscountsTest {

    @ParameterizedTest
    @CsvSource({
        "199.99, 15, 169.99",
        "100, 0, 100.00",
        "100, 100, 0.00",
        "0.01, 1, 0.01",
        "0, 25, 0.00"
    })
    void calculatesDiscount(
            String original,
            int percent,
            String expected) {

        BigDecimal actual = Discounts.finalPrice(
                new BigDecimal(original),
                percent);

        assertEquals(new BigDecimal(expected), actual);
    }

    @Test
    void roundsHalfCentUp() {
        assertEquals(
                new BigDecimal("0.02"),
                Discounts.finalPrice(new BigDecimal("0.015"), 0));
    }

    @Test
    void rejectsNull() {
        assertThrows(
                NullPointerException.class,
                () -> Discounts.finalPrice(null, 10));
    }

    @Test
    void rejectsNegativeAmount() {
        assertThrows(
                IllegalArgumentException.class,
                () -> Discounts.finalPrice(new BigDecimal("-0.01"), 10));
    }

    @ParameterizedTest
    @ValueSource(ints = {-1, 101})
    void rejectsInvalidPercentage(int percent) {
        assertThrows(
                IllegalArgumentException.class,
                () -> Discounts.finalPrice(new BigDecimal("1.00"), percent));
    }
}
~~~

Đây là **file test đầy đủ**; class package/path khớp Java main. JUnit Jupiter 5.11.4 bao gồm API và parameterized test support được Maven resolve qua dependency `junit-jupiter`. Không cần cài JUnit ngoài Maven thủ công.

### Đếm số test invocations

- `calculatesDiscount`: 5 dòng `@CsvSource` ⇒ 5 lần.
- `roundsHalfCentUp`: 1 lần.
- `rejectsNull`: 1 lần.
- `rejectsNegativeAmount`: 1 lần.
- `rejectsInvalidPercentage`: 2 values ⇒ 2 lần.

**Tổng: 10 test invocations**. Khi chạy baseline đúng, expect 10 tests thành công, 0 failures, 0 errors, 0 skipped theo convention Surefire. Không khẳng định logs chữ nào cũng y hệt giữa các Maven/JDK versions, nhưng bộ dữ liệu cho 10 invocations là xác định.

## 12. Vì sao assertEquals BigDecimal ở đây có ý nghĩa?

`BigDecimal.equals` so cả numeric value **lẫn scale**:

~~~java
new BigDecimal("100.0").equals(new BigDecimal("100.00"))
~~~

Biểu thức trên trả `false` do scale khác nhau, dù `compareTo` có thể coi hai số bằng nhau về giá trị.

Trong lab, hợp đồng API yêu cầu **scale 2**, nên dùng:

~~~java
assertEquals(new BigDecimal("100.00"), actual);
~~~

là chủ ý đúng. Nếu API không quy định scale, bạn có thể xét `compareTo`/decimal comparison khác; **không sửa assertion để che bug rounding**.

## 13. Tên file test và quy tắc Surefire discovery

Surefire có conventions phát hiện tests như:

~~~text
TestSomething.java
SomethingTest.java
SomethingTests.java
SomethingTestCase.java
~~~

File `DiscountsTest.java` của lab khớp pattern. Chỉ tạo `DiscountsChecks.java` rồi thêm `@Test` chưa chắc được Surefire khám phá theo mặc định.

POM lab bật:

~~~xml
<failIfNoTests>true</failIfNoTests>
~~~

Nghĩa là build sẽ fail nếu Surefire không tìm thấy test cần chạy. Đây là **guardrail phù hợp với project lab có test bắt buộc**, nhưng trong multi-module reactor, modules chỉ chứa BOM hoặc parent POM sẽ cần cấu hình khác khi không có tests.

**Không biến `failIfNoTests=false` thành cách chữa cơ bản** khi đã hứa có automated tests; hãy sửa tên file, package, JUnit dependency, test engine hoặc Surefire config.

## 14. Lần build đầu tiên bằng Maven cài sẵn

Trước khi Wrapper được tạo:

~~~bash
mvn -B -ntp clean verify
~~~

Nếu dùng JDK17+, Maven tương thích và mạng/repository hoạt động:

1. Clean Plugin xóa `target/`.
2. Resources Plugin xử lý resources nếu có.
3. Compiler Plugin biên dịch `Discounts.java`.
4. Test compile biên dịch `DiscountsTest.java`.
5. Surefire Plugin chạy JUnit Jupiter test invocations.
6. JAR Plugin tạo runtime JAR.
7. Source Plugin gắn source JAR trong phase package.
8. Maven hoàn thành verify, báo `BUILD SUCCESS`.

**Đây là luồng dự kiến theo POM, không phải log của một lần chạy đã thực hiện trên máy người đọc.** Nếu xảy ra `BUILD FAILURE`, đọc lỗi thật và khắc phục, không tự ghi thành công.

### Các file sinh ra

~~~text
target/
├── classes/dev/learning/money/Discounts.class
├── test-classes/dev/learning/money/DiscountsTest.class
├── surefire-reports/
│   ├── TEST-dev.learning.money.DiscountsTest.xml
│   └── dev.learning.money.DiscountsTest.txt
├── discount-core-1.0.0.jar
└── discount-core-1.0.0-sources.jar
~~~

Danh sách là các outputs **chủ yếu**; Maven có thể tạo thêm metadata/temp directories. File reports có thể khác ở đường dẫn/naming nếu Surefire configuration bị thay đổi.

## 15. Tạo Maven Wrapper đúng phiên bản

Khi Maven cài sẵn đã chạy được POM, đứng tại root `discount-core` và chạy **một lần**:

~~~bash
mvn -N org.apache.maven.plugins:maven-wrapper-plugin:3.3.4:wrapper -Dmaven=3.9.9 -Dtype=only-script
~~~

Giải thích từng phần:

- `-N`: non-recursive, phù hợp project root.
- `org.apache.maven.plugins:maven-wrapper-plugin:3.3.4:wrapper`: fully-qualified Maven Wrapper Plugin goal.
- `-Dmaven=3.9.9`: yêu cầu Wrapper sử dụng Apache Maven 3.9.9.
- `-Dtype=only-script`: lựa chọn script-only implementation, **không yêu cầu commit maven-wrapper.jar**.

Cú pháp `-Dmaven` và `-Dtype` là user properties của Maven Wrapper Plugin 3.3.4. Trong môi trường mới, goal này vẫn cần mạng để resolve Maven Wrapper Plugin dependencies; không nhầm nó với việc Wrapper sẽ hoạt động offline tự động từ đầu.

### Wrapper tạo những gì?

Thông thường:

~~~text
mvnw
mvnw.cmd
.mvn/wrapper/maven-wrapper.properties
~~~

Với `only-script`, script dùng tiện ích phù hợp để tải Maven distribution khi chưa cached, sau đó chạy Maven đã tải. Trên Unix-like cần shell POSIX và công cụ tải thích hợp như `curl`/`wget`; trên Windows cần PowerShell theo implementation.

**Không tự bịa file JAR của wrapper trong chế độ only-script.** Những wrapper types khác như `bin`/`source` có tập file khác.

## 16. Kiểm tra Maven Wrapper đã ghim đúng

Linux/macOS:

~~~bash
./mvnw -version
./mvnw -B -ntp clean verify
~~~

Windows PowerShell:

~~~powershell
.\mvnw.cmd -version
.\mvnw.cmd -B -ntp clean verify
~~~

Kiểm tra:

- Maven runtime được in là bản 3.9.9 đã chọn.
- Java runtime thực sự dùng JDK 17+.
- Build vẫn phát hiện và chạy JUnit tests.
- `BUILD SUCCESS` sau verify, không phải chỉ sau `validate`.
- Wrapper đang đọc `.mvn/wrapper/maven-wrapper.properties` của project, không bị gọi nhầm system `mvn`.

Nếu `./mvnw` báo `Permission denied` trên Unix:

~~~bash
chmod +x mvnw
~~~

Commit executable bit khi dùng Git/Unix để các thành viên và CI không phải sửa tay mỗi lần. Windows dùng `mvnw.cmd`, không chạy Bash script bằng PowerShell trực tiếp.

## 17. Maven Wrapper properties và bảo mật distribution

Sau khi generate, mở file `.mvn/wrapper/maven-wrapper.properties` và kiểm tra `distributionUrl` trỏ tới **đúng Maven distribution version** được chọn. Ví dụ mẫu:

~~~properties
distributionUrl=https://repo.maven.apache.org/maven2/org/apache/maven/apache-maven/3.9.9/apache-maven-3.9.9-bin.zip
~~~

Đây là **một URL minh họa đường dẫn Maven distribution chính thức**; sử dụng nội dung file Wrapper sinh ra hoặc endpoint mirror được tổ chức phê duyệt cho project thật.

Maven Wrapper Plugin hỗ trợ `distributionSha256Sum` để pin expected SHA-256 của Maven distribution. Nếu tổ chức yêu cầu supply-chain verification, lấy digest **từ nguồn chính thức/được tin cậy**, đối chiếu với đúng file/version rồi cấu hình. **Không điền một chuỗi hash tự bịa** chỉ để file trông đủ.

Thực hành an toàn:

1. Dùng HTTPS và nguồn Maven distribution được tin cậy.
2. Kiểm tra version và `distributionUrl` đã pin.
3. Nếu có checksum, xác minh đúng digest.
4. Không nhúng credentials vào URL trong Git.
5. Không tải script Wrapper từ nguồn không đáng tin rồi chạy trực tiếp.
6. Review thay đổi `mvnw`/`mvnw.cmd`/Wrapper properties trong pull request.
7. Cache Maven distribution ở CI theo policy; cache không thay kiểm tra integrity.

**Wrapper chỉ giải quyết Maven distribution/runtime; Maven plugins và project dependencies vẫn được Maven Resolver tải theo POM/settings.**

## 18. Những file nên commit và bỏ qua

Ví dụ `.gitignore` ở project root:

~~~gitignore
target/
*.class
.idea/
.vscode/
*.iml
.DS_Store
~~~

Nên commit:

- `pom.xml`.
- `src/main/java/...` và `src/test/java/...`.
- `mvnw` và `mvnw.cmd`.
- `.mvn/wrapper/maven-wrapper.properties`.
- `.github/workflows/...` khi thêm CI.
- `README.md`, license/project metadata nếu project cần.

Không commit:

- `target/` output compiled JAR/classes/reports.
- Local Maven cache `~/.m2/repository`.
- Secrets, `settings.xml` chứa credentials.
- Temporary test files, IDE-generated machine settings.

Trong chế độ only-script, không cần tùy tiện copy một `maven-wrapper.jar` từ nơi khác vào repository. Với loại wrapper khác, tuân theo file set tương ứng.

## 19. Maven lifecycle: từ clean tới verify

Lệnh:

~~~bash
./mvnw -B -ntp clean verify
~~~

kết hợp một phase của **clean lifecycle** với phase `verify` của default lifecycle. Các phases/goals chính theo đường đi của JAR project gồm:

~~~text
clean
  |
  v
validate
  |
  v
process-resources -> compile -> process-test-resources
  |
  v
test-compile -> test (Surefire)
  |
  v
package (JAR + source JAR)
  |
  v
verify
~~~

Đây là sơ đồ khái quát, không phải danh sách mọi phase. Maven sẽ chạy các goals thực sự được bound trong lifecycle và plugin executions. Trong lab, test suite chạy trong phase `test` trước khi package hoàn thành.

### Vì sao verify tốt hơn chỉ compile?

- `compile`: tập trung source compilation, chưa tự chạy unit tests.
- `test`: compile/test-compile rồi chạy Surefire.
- `package`: tạo JAR sau tests.
- `verify`: chạy đến verify và các checks bound tới đó nếu có.
- `install`: thêm bước cài artifacts vào local Maven repository.
- `deploy`: publish lên remote repository được cấu hình (không thuộc baseline).

**Không lẫn `mvn verify` với `mvn deploy`.** Bài không tự cấu hình quyền publish hoặc đưa artifacts lên public repository.

## 20. Verify test thực sự chạy

Sau:

~~~bash
./mvnw -B -ntp clean verify
~~~

xem log có Surefire goal, JUnit test class và test summary. Với đúng `DiscountsTest.java` như phần 11, có 10 invocations và kỳ vọng 0 failures/errors/skipped.

Các file report thường ở:

~~~text
target/surefire-reports/TEST-dev.learning.money.DiscountsTest.xml
target/surefire-reports/dev.learning.money.DiscountsTest.txt
~~~

Một report JUnit/Surefire có thể liệt kê `tests="10"` và `failures="0"` tương ứng baseline; đừng chỉ đọc `BUILD SUCCESS` nếu tests bị skip bởi cấu hình khác.

**Lưu ý:** Không có cờ `-DskipTests` trong lệnh quality gate của bài. Một build được phép skip tests để chẩn đoán tốc độ không được quảng cáo là “đã kiểm thử tự động”.

## 21. Kiểm tra artifact sau package

Lệnh:

~~~bash
./mvnw -B -ntp package
~~~

Những artifacts cơ bản:

~~~text
target/discount-core-1.0.0.jar
target/discount-core-1.0.0-sources.jar
~~~

Kiểm tra nội dung JAR:

~~~bash
jar tf target/discount-core-1.0.0.jar
~~~

Tìm entry:

~~~text
dev/learning/money/Discounts.class
~~~

Đối với source JAR:

~~~bash
jar tf target/discount-core-1.0.0-sources.jar
~~~

Tìm entry:

~~~text
dev/learning/money/Discounts.java
~~~

**Không mong có `DiscountsTest.class` trong main JAR**. Tests được compile vào `target/test-classes` và thực thi bằng Surefire; JUnit dependency test scope không được bundle vào JAR production.

Bạn có thể dùng `javap` để xem public API đã compile:

~~~bash
javap -classpath target/discount-core-1.0.0.jar dev.learning.money.Discounts
~~~

Kết quả quan trọng là public method `finalPrice(java.math.BigDecimal, int)` và class public tồn tại. Những chi tiết output của `javap` phụ thuộc JDK/flags.

## 22. Tại sao library JAR không cần Main-Class?

`discount-core` là thư viện: consumers **import class** hoặc declare Maven dependency, không chạy nó như một ứng dụng độc lập.

Do POM không cấu hình executable manifest `Main-Class`, lệnh:

~~~bash
java -jar target/discount-core-1.0.0.jar
~~~

không phải cách kiểm tra thư viện; có thể báo thiếu main manifest attribute. Đây không phải build lỗi. Kiểm tra đúng là **tests, JAR content, public API, và consumer project**.

Nếu muốn có CLI demo, tạo một **ứng dụng consumer riêng**. Đừng lẫn library API với entrypoint của một runnable app trong cùng JAR khi mục tiêu là phát hành thư viện tái sử dụng.

## 23. Phân biệt main JAR và source JAR

| Artifact | Nội dung | Dùng để làm gì? |
| --- | --- | --- |
| `discount-core-1.0.0.jar` | Compiled classes + metadata/resources | Consumer compile/runtime |
| `discount-core-1.0.0-sources.jar` | Java source files | IDE source navigation, review |
| `target/test-classes` | Test bytecode | Surefire trên project library |
| `target/surefire-reports` | XML/TXT reports | CI/test diagnostics |
| `pom.xml` | Maven metadata/dependencies/version | Consumer resolution |

Source JAR được gắn với classifier `sources`; nó **không thay** main JAR. Trong project chuyên nghiệp, có thể xuất bản thêm Javadoc JAR, legal documents, checksums/signatures theo repository policy, nhưng không cần thêm những plugin đó chỉ để bài cơ sở chạy được.

## 24. Cài thư viện vào local Maven repository

Đứng tại `discount-core`:

~~~bash
./mvnw -B -ntp clean install
~~~

Maven sẽ chạy các phases trước `install`, bao gồm tests và package, sau đó ghi main JAR, POM và các attached artifacts vào Maven local repository.

Với cấu hình mặc định, GAV mapping là:

~~~text
~/.m2/repository/dev/learning/money/discount-core/1.0.0/
├── discount-core-1.0.0.pom
├── discount-core-1.0.0.jar
└── discount-core-1.0.0-sources.jar
~~~

Các metadata files khác có thể đi kèm; path local repo cũng có thể được thay bằng `settings.xml` hoặc `-Dmaven.repo.local`.

**Install không phải publish remote.** Máy khác sẽ không tự nhìn thấy JAR ở local repository của máy bạn. Khi chia sẻ cho team, cần private artifact repository, GitHub Packages hoặc Maven Central theo điều kiện và quy trình phù hợp.

## 25. Consumer project: chứng minh JAR tái sử dụng được

Tạo một project **khác**, ví dụ `discount-client/`:

~~~text
discount-client/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── dev/learning/demo/
                └── ConsumerMain.java
~~~

Consumer POM khai dependency vào `discount-core:1.0.0` mà bạn vừa install. Nếu chưa chạy `install` ở thư viện, consumer có thể báo `Could not resolve dependency`, vì artifact chưa có trong local/remote repositories.

**Không đặt consumer project vào cùng root thư viện một cách mơ hồ** rồi kỳ vọng Maven tự hiểu reactor. Đây là một project độc lập để chứng minh local artifact resolution.

## 26. Consumer pom.xml hoàn chỉnh

File `discount-client/pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.learning.demo</groupId>
    <artifactId>discount-client</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>dev.learning.money</groupId>
            <artifactId>discount-core</artifactId>
            <version>1.0.0</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
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

Dependency `discount-core` ở scope compile (mặc định), nên consumer có thể import class `dev.learning.money.Discounts`. Consumer không cần JUnit Jupiter để chạy production method vì JUnit là test-only của project thư viện.

## 27. ConsumerMain.java hoàn chỉnh

File `discount-client/src/main/java/dev/learning/demo/ConsumerMain.java`:

~~~java
package dev.learning.demo;

import java.math.BigDecimal;
import dev.learning.money.Discounts;

public final class ConsumerMain {

    private ConsumerMain() {
    }

    public static void main(String[] args) {
        BigDecimal original = new BigDecimal("199.99");
        BigDecimal finalPrice = Discounts.finalPrice(original, 15);
        System.out.println("Gia sau giam: " + finalPrice.toPlainString());
    }
}
~~~

**Stdout chính xác:**

~~~text
Gia sau giam: 169.99
~~~

Thông báo cố ý dùng ASCII để tránh khác biệt charset của terminal trong một số môi trường. Phép tính dựa trên contract `199.99` và giảm `15%`; `toPlainString()` giữ định dạng thập phân chuẩn từ BigDecimal scale 2.

## 28. Build và chạy consumer trên Linux/macOS

Sau khi đã `install` thư viện, vào `discount-client`:

~~~bash
mvn -B -ntp clean package
java -cp "target/classes:$HOME/.m2/repository/dev/learning/money/discount-core/1.0.0/discount-core-1.0.0.jar" dev.learning.demo.ConsumerMain
~~~

Expected stdout:

~~~text
Gia sau giam: 169.99
~~~

Điều kiện: Maven dùng local repository mặc định `$HOME/.m2/repository`. Nếu bạn cấu hình `-Dmaven.repo.local` hoặc settings `localRepository` khác, thay JAR path.

**Không dùng** `java -jar target/discount-client-1.0.0.jar` ở đây: consumer POM chưa thiết lập `Main-Class` và không tạo fat JAR. `java -cp` là cách đơn giản, minh bạch về classpath.

## 29. Build và chạy consumer trên Windows PowerShell

Sau `.\mvnw.cmd ... install` ở library (hoặc dùng Maven đã cài nếu consumer chưa có Wrapper), tại `discount-client`:

~~~powershell
mvn -B -ntp clean package
java -cp "target\classes;$HOME\.m2\repository\dev\learning\money\discount-core\1.0.0\discount-core-1.0.0.jar" dev.learning.demo.ConsumerMain
~~~

Stdout cũng là:

~~~text
Gia sau giam: 169.99
~~~

Windows Java classpath separator là dấu `;`, còn Unix-like là dấu `:`. Lưu ý `$HOME` trong PowerShell đại diện user home, nhưng nếu local Maven repository đã được cấu hình ở vị trí khác thì phải dùng vị trí thực.

Không nhầm `mvnw.cmd` ở thư viện và `mvn` ở consumer: consumer là dự án phụ tách biệt, không tự có wrapper scripts. Nếu muốn pin Maven cho consumer, thêm Maven Wrapper vào project đó hoặc dùng Maven 3.9.9 đã cài.

## 30. Bài kiểm thử thất bại có chủ đích

Bạn có thể thực hành “quality gate chặn lỗi” trên **bản sao** project hoặc nhánh thử nghiệm:

Trong test `roundsHalfCentUp()`, tạm thay expected từ `"0.02"` thành `"0.01"`, trong khi code source không đổi. Chạy:

~~~bash
./mvnw -B -ntp clean verify
~~~

Lúc này JUnit assertion phải **FAIL** vì kết quả thật `0.02` khác expected `0.01`, và Surefire sẽ làm Maven build không thành công theo cấu hình mặc định.

Sau đó **khôi phục expected `0.02`** và chạy lại. Đây là một thí nghiệm để thấy automated tests thực sự được kích hoạt; không phải phần cuối cùng của source file.

**Không commit test cố ý lỗi**. Nếu build vẫn PASS sau khi cố ý sửa assertion, cần kiểm tra Surefire test discovery và logs, không mặc định hệ thống đã kiểm thử đúng.

## 31. Chỉ chạy một test class hoặc method

Chạy tất cả tests:

~~~bash
./mvnw -B -ntp test
~~~

Chạy một class:

~~~bash
./mvnw -B -ntp -Dtest=DiscountsTest test
~~~

Chạy một method cụ thể:

~~~bash
./mvnw -B -ntp -Dtest=DiscountsTest#roundsHalfCentUp test
~~~

Phương thức `roundsHalfCentUp` là một `@Test` không parameterized, phù hợp làm ví dụ test selection. Những cú pháp filter phức tạp phụ thuộc Surefire provider/version; xem tài liệu Surefire 3.2.5 nếu chọn phương thức parameterized.

**Test selection không phải release quality gate.** Dùng `clean verify` đầy đủ trong CI.

## 32. skipTests và maven.test.skip khác nhau

Hai cờ hay nhầm:

~~~bash
./mvnw -B -ntp clean package -DskipTests
~~~

Trong Surefire 3.2.5, `skipTests` bỏ **thực thi unit tests**, nhưng thông thường test sources vẫn được biên dịch.

~~~bash
./mvnw -B -ntp clean package -Dmaven.test.skip=true
~~~

Cờ `maven.test.skip` được Compiler/Surefire và các plugins hỗ trợ dùng để bỏ cả test compilation và test execution.

**Không dùng hai lệnh này để chứng minh đã kiểm thử tự động.** Chúng phục vụ tình huống chẩn đoán/thử build nhanh có chủ đích, còn baseline release/CI phải có tests.

Với POM lab đang bật `failIfNoTests=true`, cần phân biệt “không có test được discover” với “cố tình skip tests” và đọc log đúng; đừng chỉ nhìn `BUILD SUCCESS`.

## 33. Tự động hóa CI bằng GitHub Actions

Tạo file `.github/workflows/verify.yml` ở **project thư viện**:

~~~yaml
name: Verify Java library

on:
  push:
  pull_request:

permissions:
  contents: read

jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - name: Check out sources
        uses: actions/checkout@v4

      - name: Set up Java 17
        uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'
          cache: maven

      - name: Verify with project Maven Wrapper
        run: |
          chmod +x ./mvnw
          ./mvnw -B -ntp clean verify
~~~

Workflow này:

- Chạy trên push và pull_request events theo GitHub Actions semantics.
- Checkout source project đã commit.
- Chọn JDK17; Wrapper chọn Maven 3.9.9 theo properties.
- Dùng Maven cache để tăng tốc nhưng vẫn thực thi clean build/tests.
- Chạy `clean verify` nên Surefire unit tests thực thi trước khi đóng gói.
- Có quyền `contents: read` tối thiểu cho workflow, không cần secrets/publish permissions.

Đây là workflow ví dụ cho **public/trusted dependencies**. Một dự án dùng private artifact repository sẽ cần CI settings/secrets được bảo vệ, và không được đưa credentials vào workflow YAML công khai.

### Vì sao CI vẫn chạy tests dù có cache?

`cache: maven` thường cache artifacts ở local Maven repository, **không phải** bằng chứng tests đã chạy. `clean verify` thực thi lifecycle và Surefire vẫn chạy tests của source hiện tại.

Nếu CI log chỉ có `BUILD SUCCESS` mà không có test reports, kiểm tra lại package/test path, Surefire, skip flags và test discovery.

## 34. CI nào cần dùng Maven Wrapper?

Trong GitHub Actions ví dụ, dùng `./mvnw` thay vì `mvn` để chọn Maven version theo repository. Điều này giúp dev/CI thống nhất build tool version.

Cần kiểm tra:

- Workflow sử dụng JDK17 như đã hứa.
- Wrapper file `mvnw` và properties nằm trong repo.
- Script có execute permission hoặc workflow cấp quyền chạy phù hợp.
- Network/mirror/Proxy của runner cho phép tải Maven distribution lần đầu.
- Source of truth cho distribution URL là wrapper properties đã được review.
- Nếu organization yêu cầu checksum/signature, bổ sung kiểm tra dựa trên hash đáng tin.
- Không lén đổi Maven version trên CI runner và vẫn tuyên bố dùng Wrapper.
- Nếu có internal repository, cache không bypass security/provenance checks.

**CI là nơi lặp lại cùng build, không thay thế code review**.

## 35. Kiểm tra dependency graph và phạm vi JUnit

Từ `discount-core`, có thể xem dependency tree:

~~~bash
./mvnw -B -ntp org.apache.maven.plugins:maven-dependency-plugin:3.8.1:tree
~~~

Đây là full-coordinate goal để tránh plugin prefix/version resolution ngoài dự định.

Kết quả cần quan sát:

- `org.junit.jupiter:junit-jupiter:5.11.4:test`.
- Các thành phần JUnit Platform/Engine/API có thể xuất hiện ở transitive test graph.
- Không có external `compile` dependency vì production class chỉ dùng JDK standard library.
- Maven plugins của build **không được tính như project compile/runtime dependencies** trong cùng tree.

Consumer sẽ nhìn dependency `dev.learning.money:discount-core:1.0.0:compile`, nhưng không tự nhận JUnit test dependencies của thư viện làm runtime dependency.

## 36. Unit tests, integration tests và deploy khác nhau

Lab dùng **unit tests** tên `DiscountsTest`, Surefire chạy trong phase `test`.

Nếu thư viện sau này cần integration tests (ví dụ phải kết nối database hoặc HTTP service), nên:

1. Thiết kế fixtures và môi trường test rõ.
2. Dùng Maven Failsafe Plugin với các goals/phases thích hợp như `integration-test` và `verify`.
3. Không ép integration tests vào Surefire mặc định nếu có yêu cầu lifecycle riêng.
4. CI phải bảo đảm `verify` thật sự chạy integration-test gate.
5. Có cleanup môi trường khi tests fail.
6. Không dùng `-DskipTests` vô điều kiện để bỏ mọi tests.

**Deploy không thuộc lab cơ sở.** `mvn deploy` cần repository, credentials, signing/metadata policy của tổ chức. `mvn install` chỉ đủ để consumer trên **cùng máy** resolve artifact đã build.

## 37. Chọn version như thế nào?

Maven coordinates `1.0.0` của lab chỉ là bản phát hành học tập. Trong sản phẩm thật, một quy tắc semantic versioning phổ biến:

- **Major** khi thay đổi API không tương thích.
- **Minor** khi thêm tính năng tương thích.
- **Patch** khi sửa lỗi tương thích.

Ví dụ nếu thay đổi cách làm tròn từ HALF_UP sang HALF_EVEN cho cùng method, đây là **thay đổi hành vi có thể ảnh hưởng consumers** dù chữ ký Java không đổi; cần xem versioning/compatibility policy.

Không overwrite một release artifact `1.0.0` trong repository immutable chỉ vì source đã đổi. Đổi version/release coordinates theo quy trình.

## 38. Thư viện production cần thêm gì ngoài bài?

Một thư viện có thể cần:

- API JavaDoc đầy đủ và example usage.
- License và NOTICE phù hợp (đặc biệt khi open source/public).
- Chữ ký, checksum, provenance và repository metadata.
- Source JAR/Javadoc JAR khi publish lên Maven Central hoặc repository yêu cầu.
- Test coverage, static analysis và security scanner theo policy.
- Changelog/release notes.
- Tests về binary/source compatibility qua các versions.
- Maven Enforcer Plugin để kiểm soát Maven/JDK yêu cầu.
- Reproducible build checks.
- Build/test trong các JDK versions dự định hỗ trợ.
- README diễn giải cách kết hợp với framework khác.

Những điều này hữu ích nhưng **không phải điều kiện bắt buộc để lab Java 17 cơ sở build**. Không thêm tùy tiện plugin phức tạp vào POM chỉ để “cho đầy đủ” nếu chưa có yêu cầu từ release process.

## 39. Kiểm tra JAR có nằm trong local repository

Sau:

~~~bash
./mvnw -B -ntp install
~~~

Linux/macOS với local repository mặc định:

~~~bash
ls "$HOME/.m2/repository/dev/learning/money/discount-core/1.0.0"
~~~

Windows PowerShell:

~~~powershell
Get-ChildItem "$HOME\.m2\repository\dev\learning\money\discount-core\1.0.0"
~~~

Tìm main JAR, POM và attached source JAR. Nếu không có:

- Lệnh đã thật sự tới phase install chưa?
- Project GAV đúng hay đang build một POM khác?
- Có dùng `-Dmaven.repo.local` hoặc settings `localRepository` khác không?
- Maven install plugin có báo lỗi/quyền truy cập không?
- Có bị đổi version hoặc dùng SNAPSHOT không?
- Consumer đang dùng **cùng local repository** hay một isolated repo khác?

Không giải quyết bằng cách copy JAR ngẫu nhiên vào folder local repo mà không có POM/metadata phù hợp.

## 40. Một release local không tự trở thành dependency của mọi máy

Nếu người học chạy trên laptop A:

~~~bash
./mvnw -B -ntp install
~~~

thì dependency chỉ hiện diện trong Maven local repo của laptop A. Laptop B/CI không tự có artifact đó, trừ khi:

- Build thư viện trong cùng reactor đúng module dependency ordering; hoặc
- Install thư viện riêng trong cùng CI job; hoặc
- Publish lên private/public Maven repository đã cấu hình.

Do đó consumer demo trong bài chạy **trên cùng máy** hoặc môi trường đã install artifact. Nếu chuyển sang nhiều module, cần học Maven reactor và `-pl/-am` thay vì chia sẻ local cache thiếu kiểm soát.

## 41. Maven Wrapper cũng có cache

Wrapper tải Maven distribution vào thư mục cache thích hợp lần đầu; những lần sau có thể dùng bản đã tải. Còn Maven project/plugin dependencies nằm trong **Maven local artifact repository**.

Hai loại cache khác nhau:

| Cache | Nội dung |
| --- | --- |
| Maven Wrapper distribution cache | Apache Maven binary distribution |
| Maven local repository | POM, plugin JAR, project dependencies, local installed artifacts |
| `target/` | Compiled classes, test outputs, JARs và reports |
| CI cache | Bản sao chọn lọc các paths để tăng tốc CI |

Vì thế một build lần đầu chậm có thể do Wrapper distribution download **và** project dependencies/plugin resolution. Không xóa `~/.m2` toàn bộ mỗi khi build chậm; điều đó còn khiến những caches ấy lạnh trở lại.

## 42. Có thể chạy offline không?

Sau khi Wrapper Maven distribution và các artifacts cần thiết đã cached:

~~~bash
./mvnw -B -ntp -o clean verify
~~~

có thể thành công nếu project/plugins/dependencies đã đủ ở Maven local repository.

Nhưng `-o` không tự tạo artifacts chưa cached, không làm tests không chạy và không nhất thiết chặn mọi network call do plugin/custom test code tự tạo. Một lần offline fail vì Maven Source Plugin thiếu trong cache cho biết cache chưa đủ, không chứng minh `Discounts.java` sai.

Để prefetch có chủ đích, Maven Dependency Plugin có:

~~~bash
./mvnw -B -ntp org.apache.maven.plugins:maven-dependency-plugin:3.8.1:go-offline
~~~

Goal giúp resolve project/plugin/report dependencies, nhưng không cam kết mọi custom external resource của mọi goal đã cached. **Offline verification vẫn phải chạy thật** với cùng profiles/modules/goals khi cần CI không có network.

## 43. Troubleshooting: Java/JDK

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `release version 17 not supported` | Maven chạy JDK quá cũ | Kiểm tra `./mvnw -version` và JDK17+ |
| `javac: command not found` | Chưa cài JDK/PATH sai | Cài JDK 17+, đặt JAVA_HOME/PATH đúng |
| `UnsupportedClassVersionError` ở consumer | JVM runtime thấp hơn classfile target | Chạy Java17+ hoặc đổi support policy |
| `package ... does not exist` | Java file sai package/path | Khớp package, source tree và imports |
| `cannot find symbol Discounts` | Consumer dependency hoặc classpath thiếu | Kiểm tra GAV, install, `-cp` |
| Tests compile fail, main compile PASS | Test dependency/import không đúng | Kiểm tra JUnit Jupiter scope/test source |
| JVM main output khác | Source/inputs khác, hoặc bản JAR stale | Rebuild clean, xác nhận GAV/version |

**Đừng sửa Maven POM target xuống Java 8 chỉ để “cho chạy”** nếu thư viện đã cam kết API Java17.

## 44. Troubleshooting: Maven Wrapper

| Triệu chứng | Kiểm tra |
| --- | --- |
| `./mvnw: Permission denied` | Git executable bit/`chmod +x mvnw` |
| `mvnw.cmd` không tìm thấy | Chưa generate/commit Windows script |
| Wrapper không tải Maven distribution | URL, network/proxy/TLS, cache, checksum |
| Wrapper chạy Maven khác 3.9.9 | Kiểm tra `distributionUrl` và actual `./mvnw -version` |
| Máy không có Maven nhưng Wrapper đã commit | Gọi `./mvnw` thay `mvn`; vẫn cần JDK |
| `.mvn/wrapper/maven-wrapper.properties` bị thiếu | Commit file do Wrapper Plugin tạo |
| Wrapper thiếu curl/wget trên Unix | Cài tool được phép hoặc chọn wrapper type phù hợp |
| Private distribution download cần auth | Dùng CI secrets, không hardcode token vào URL |
| Script thay đổi bất thường trong PR | Review supply-chain/security trước khi chạy |

Wrapper không sửa được POM sai hoặc test failure. Nó chủ yếu thống nhất **Maven version và launcher workflow**.

## 45. Troubleshooting: dependency và plugins

| Error | Hướng kiểm tra |
| --- | --- |
| `Could not resolve org.junit.jupiter...` | Maven repositories, network, settings/mirrors, GAV |
| `Plugin ... could not be resolved` | Plugin version, plugin repo, cache, authentication |
| `No plugin found for prefix` | Dùng full-coordinate goal hoặc kiểm tra prefix mapping |
| `PKIX path building failed` | Java TLS truststore/corporate proxy, không disable TLS |
| `401/403` từ private mirror | Repository ID và read credentials |
| `This failure was cached` | Sửa root cause trước rồi thử `-U` phù hợp |
| `BUILD SUCCESS` nhưng không thấy test | Surefire discovery/config, `-DskipTests`, source naming |
| `There are test failures` | Xem `target/surefire-reports`, sửa code/test |
| Source JAR không xuất hiện | Source Plugin execution/phase/GAV, chạy package |
| Consumer không resolve `discount-core` | Chạy library install cùng repo hoặc publish hợp lệ |

**Không sửa bug Java bằng cách xóa toàn bộ `~/.m2/repository`**. Tách artifact resolution lỗi với compiler/test failures.

## 46. Vì sao test failure phải làm build fail?

Một bài thực hành “kiểm thử tự động” chỉ có ý nghĩa nếu pipeline thực sự ngăn artifact lỗi được coi là PASS.

Với Surefire 3.2.5:

- Test assertion failure gây `There are test failures` và build fail trong cấu hình thông thường.
- Reports XML/TXT lưu details để đọc.
- `failIfNoTests=true` chặn trường hợp không discover test nào.
- Có thể chạy từng test để debug.
- Không đặt `testFailureIgnore=true` trong POM cơ sở, vì sẽ che thất bại của quality gate.
- Không tự bật rerun/flake tolerance khiến test fail đi vào accepted build mà không có policy.

Nếu project có tests không ổn định (flaky), hãy tìm nguyên nhân, isolate environment và có quarantine policy cụ thể; **không dùng skipTests làm giải pháp lâu dài**.

## 47. Hướng dẫn tự rà soát trước khi nộp bài

Mỗi người học nên tự kiểm tra:

1. **Source hợp lệ:** `Discounts.java` nằm đúng package path; logic không dùng floating-point.
2. **POM hợp lệ:** các tags XML đóng đầy đủ; groupId/artifactId/version/package pin đúng.
3. **JDK:** Maven Wrapper chạy trên JDK17+.
4. **Wrapper:** có scripts và properties; version Maven được in đúng.
5. **Test:** có `DiscountsTest.java` với JUnit Jupiter engine; 10 invocations theo baseline.
6. **Build:** `clean verify` PASS không có skip flags.
7. **Report:** Surefire reports tồn tại, 0 failures/errors/skipped trong baseline.
8. **Package:** JAR chính có `Discounts.class`; source JAR có `Discounts.java`.
9. **Isolation:** JUnit test classes không đi vào main JAR.
10. **Install:** artifact hiện trong local Maven repository ở GAV đúng.
11. **Consumer:** dependency GAV khớp library; code biên dịch.
12. **Runtime:** output consumer đúng `Gia sau giam: 169.99`.
13. **CI:** workflow thực sự gọi Wrapper và chạy clean verify trên JDK17.
14. **Security:** không có token, mật khẩu hoặc hash giả trong repo.
15. **Cleanliness:** `target/` và local Maven cache không được commit.

## 48. Bài tập mở rộng từ baseline

1. Thêm phương thức `discountAmount(original, percent)`, dùng lại validation, rồi bổ sung tests cho scale 2.
2. Viết tests với giá gốc rất lớn (ví dụ số tiền có hàng chục chữ số) để thấy lợi ích `BigDecimal`.
3. Cho phép quy tắc rounding được chọn qua enum, nhưng vẫn cung cấp default API tương thích.
4. Thêm test `BigDecimal("0.005")` ở 0% và giải thích HALF_UP.
5. Viết JavaDoc cho public API và tạo Javadoc JAR bằng Maven Javadoc Plugin theo release policy.
6. Thêm Maven Enforcer Plugin kiểm tra tối thiểu JDK/Maven mà CI support.
7. Tạo một module `discount-client` trong multi-module reactor và dùng `-pl/-am` để build đúng thứ tự.
8. Bổ sung Maven Failsafe integration tests cho consumer scenario khi phù hợp.
9. Tạo workflow CI matrix JDK17/21 nếu library dự kiến hỗ trợ hai runtime.
10. Đưa artifact lên private Maven repository theo quyền publish được tổ chức cấp.
11. Thực hiện reproducible-build comparison trên hai môi trường cùng inputs/version.
12. Kiểm tra Maven Wrapper distribution checksum do upstream công bố.
13. Dùng `mvn dependency:tree` so test vs runtime scopes.
14. Viết test để chứng minh API từ chối discount 101%.
15. Kiểm tra việc đổi `groupId`/`artifactId` ảnh hưởng dependency consumer và local repo path.

**Không cần làm hết bài mở rộng để hoàn thành baseline.** Mỗi thay đổi phải được kiểm tra tự động lại bằng `clean verify` và không làm hỏng API đã công bố.

## 49. Câu hỏi ôn tập có đáp án

1. **Mục tiêu chính của bài?** Tạo thư viện Java17 có POM, Wrapper, JUnit tests, JAR và consumer.
2. **Packaging của thư viện là gì?** `jar`.
3. **GAV thư viện?** `dev.learning.money:discount-core:1.0.0`.
4. **File Java production nằm ở đâu?** `src/main/java/dev/learning/money/Discounts.java`.
5. **File test nằm ở đâu?** `src/test/java/dev/learning/money/DiscountsTest.java`.
6. **Library JAR có cần Main-Class?** Không, nếu chỉ xuất bản library API.
7. **Vì sao dùng BigDecimal?** Tránh sai số decimal do double trong money calculations.
8. **Rounding mode của lab?** `HALF_UP`.
9. **Scale kết quả?** Hai chữ số thập phân.
10. **199.99 giảm 15% trả gì?** `169.99`.
11. **100 giảm 100% trả gì?** `0.00`.
12. **0.015 với giảm 0% trả gì?** `0.02`.
13. **Input null gây gì?** `NullPointerException`.
14. **Giá âm gây gì?** `IllegalArgumentException`.
15. **Discount -1 hoặc 101 gây gì?** `IllegalArgumentException`.
16. **Maven version được Wrapper pin?** `3.9.9`.
17. **Wrapper Plugin version bài dùng?** `3.3.4`.
18. **Option `-Dtype=only-script` có nghĩa?** Tạo script-only Wrapper, không cần wrapper JAR trong repo.
19. **Wrapper có cài JDK17 không?** Không, cần JDK riêng.
20. **Command Unix chạy quality gate?** `./mvnw -B -ntp clean verify`.
21. **Command Windows tương đương?** `.\mvnw.cmd -B -ntp clean verify`.
22. **JUnit dependency scope?** `test`.
23. **Compiler Plugin dùng property nào?** `maven.compiler.release=17`.
24. **Surefire Plugin làm gì?** Chạy unit tests trong test phase và ghi reports.
25. **Số test invocations trong lab?** 10.
26. **Vì sao có nhiều invocations hơn số test methods?** Parameterized tests chạy trên nhiều input cases.
27. **`failIfNoTests=true` giúp gì?** Fail build nếu không discover tests.
28. **`mvn compile` có tự chạy tests không?** Không, chỉ tới compile phase.
29. **`mvn verify` có publish remote không?** Không.
30. **`mvn install` publish Central không?** Không, cài vào local repository.
31. **Source Plugin tạo file gì?** `discount-core-1.0.0-sources.jar`.
32. **Main JAR cần chứa class nào?** `dev/learning/money/Discounts.class`.
33. **Main JAR có chứa DiscountsTest.class không?** Không theo cấu hình baseline.
34. **Consumer có tự cần JUnit không?** Không, JUnit là test-only dependency của library.
35. **Consumer dùng API qua đâu?** Maven dependency `discount-core:1.0.0` và import `Discounts`.
36. **Consumer output chính xác?** `Gia sau giam: 169.99`.
37. **Tại sao consumer dùng java -cp thay vì java -jar?** JAR không cấu hình entrypoint/fat packaging.
38. **Unix classpath separator?** Dấu `:`.
39. **Windows classpath separator?** Dấu `;`.
40. **CI pin Java như thế nào?** `actions/setup-java` với Java 17.
41. **CI gọi Maven bằng gì?** `./mvnw` của repository.
42. **Cache Maven trên CI thay tests được không?** Không.
43. **Nếu test fail, có nên set testFailureIgnore?** Không trong baseline quality gate.
44. **Nếu Wrapper không tải Maven, sửa Java source có tác dụng?** Không; xem URL/network/Proxy/TLS.
45. **Nếu consumer không resolve library, bước đầu?** Xác minh install cùng local repository và đúng GAV.
46. **Nếu build SUCCESS nhưng không có tests?** Kiểm tra Surefire naming/config và skip flags.
47. **Vì sao không commit target/?** Đó là generated build output, không phải source.
48. **Vì sao không điền checksum giả?** Làm mất giá trị integrity validation và có thể chặn build.
49. **Khi nâng version thư viện, cần làm gì?** Rebuild/test, cập nhật GAV, consumer references và release policy.
50. **Đâu là bằng chứng hoàn thành tốt nhất?** Wrapper-driven `clean verify` thực thi tests + JAR hợp lệ + consumer chạy đúng output.

## 50. Checklist nộp bài tổng hợp

- [ ] Có POM hoàn chỉnh đúng GAV/version/package.
- [ ] JDK17+ và Maven/Wrapper version ghi rõ.
- [ ] Có `mvnw`, `mvnw.cmd` và Wrapper properties đúng version.
- [ ] Maven distribution URL và integrity được kiểm tra theo policy.
- [ ] Java main source biên dịch được, package/path chính xác.
- [ ] API public có validation, rounding và JavaDoc rõ.
- [ ] Không sử dụng double để xử lý decimal money.
- [ ] JUnit Jupiter dependency khai scope test.
- [ ] Surefire Plugin version được pin.
- [ ] Surefire discover `DiscountsTest`, có 10 invocations.
- [ ] Không bật skipTests/testFailureIgnore trong quality gate.
- [ ] Tests bao phủ happy path, biên, rounding và errors.
- [ ] `clean verify` PASS trong môi trường hợp lệ.
- [ ] Có Surefire XML/TXT reports và không có test failures.
- [ ] JAR chính có `Discounts.class`, không có test classes.
- [ ] Source JAR được tạo đúng khi package.
- [ ] `install` cài artifact đúng local repository.
- [ ] Consumer POM có GAV chính xác.
- [ ] ConsumerMain biên dịch và in đúng `Gia sau giam: 169.99`.
- [ ] CI chạy với JDK17 và Wrapper, không phụ thuộc system Maven tùy ý.
- [ ] Workflow có quyền tối thiểu và không lộ secrets.
- [ ] `.gitignore` loại target và IDE output; Wrapper được commit.
- [ ] Biết sự khác nhau giữa verify, install và deploy.
- [ ] Có README API usage và release instructions.
- [ ] Nếu version/behavior đổi, tests và consumer được chạy lại.
- [ ] Không publish artifacts nếu chưa có quyền và policy phê duyệt.

## 51. Tài liệu chính thức để đối chiếu

- [Apache Maven — Getting Started Guide](https://maven.apache.org/guides/getting-started/): cấu trúc project, GAV, lifecycle, dependency.
- [Apache Maven — POM Reference](https://maven.apache.org/pom.html): `project`, `dependencies`, `build/plugins`.
- [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html): `compile`, `test`, `package`, `verify`, `install`, `deploy`.
- [Apache Maven — Maven Wrapper](https://maven.apache.org/tools/wrapper/): Wrapper scripts và Maven distribution.
- [Apache Maven Wrapper Plugin — wrapper:wrapper](https://maven.apache.org/tools/wrapper/maven-wrapper-plugin/wrapper-mojo.html): `-Dmaven`, `-Dtype`, `distributionSha256Sum`.
- [Apache Maven Wrapper Plugin — Usage](https://maven.apache.org/tools/wrapper/maven-wrapper-plugin/usage.html): only-script và hệ điều hành hỗ trợ.
- [Maven Compiler Plugin — Setting Compiler Release](https://maven.apache.org/plugins/maven-compiler-plugin/examples/set-compiler-release.html): Java `--release`.
- [Maven Surefire Plugin — Using JUnit Platform](https://maven.apache.org/surefire/maven-surefire-plugin/examples/junit-platform.html): JUnit 5 provider.
- [Maven Surefire Plugin 3.2.5 — surefire:test](https://maven.apache.org/surefire-archives/surefire-3.2.5/maven-surefire-plugin/test-mojo.html): `failIfNoTests`, skip flags, reports.
- [Maven Surefire Plugin — Skipping Tests](https://maven.apache.org/surefire/maven-surefire-plugin/examples/skipping-tests.html): skipTests vs maven.test.skip.
- [Maven JAR Plugin](https://maven.apache.org/plugins/maven-jar-plugin/): JAR build.
- [Maven Source Plugin — jar-no-fork](https://maven.apache.org/plugins/maven-source-plugin/jar-no-fork-mojo.html): attach source artifact.
- [Maven Install Plugin](https://maven.apache.org/plugins/maven-install-plugin/): local repository installation.
- [Maven Dependency Plugin — tree](https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html): project dependencies và scopes.
- [JUnit 5 User Guide](https://docs.junit.org/5.11.4/user-guide/): Jupiter tests và parameterized test.
- [Java 17 — BigDecimal API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html): exact decimal, scale, rounding.
- [GitHub Actions — Building and Testing Java with Maven](https://docs.github.com/en/actions/tutorials/build-and-test-code/java-with-maven): CI setup-java và Maven builds.

**Kết luận:** Một thư viện Java đúng chuẩn không chỉ là `Discounts.java` được compile. Cần có **POM ổn định**, **Maven Wrapper** để mọi máy dùng cùng Maven version, **JUnit/Surefire tests** thực sự chạy ở lifecycle, **JAR đúng nội dung**, và **consumer** chứng minh API tái sử dụng. Kiểm chứng end-to-end bằng Wrapper `clean verify`, `install`, consumer classpath và CI; giữ tests, versioning và artifact provenance làm rào chắn chất lượng lâu dài.
