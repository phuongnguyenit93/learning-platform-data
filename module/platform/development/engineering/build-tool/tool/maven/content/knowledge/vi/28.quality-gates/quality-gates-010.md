# Phân biệt kiểm tra build với việc thiết kế nội dung kiểm thử

## 1. Cổng chất lượng của Maven kiểm tra điều gì — và không kiểm tra điều gì?

Một dự án Java có thể nhận kết quả `BUILD SUCCESS` sau lệnh `mvn verify`, trong khi vẫn tính sai phí, bỏ sót tình huống biên hoặc làm mất dữ liệu ở môi trường thực tế. Nghịch lý này xuất hiện khi chúng ta đánh đồng hai hoạt động:

- **Kiểm tra build (build verification/quality gate):** xác nhận một tập quy tắc **đã được thiết lập** được thực thi và không vi phạm. Các quy tắc có thể là biên dịch thành công, unit/integration tests pass, không có test nào bị bỏ qua ngoài chủ đích, coverage đạt ngưỡng, cấu hình JDK đúng, dependency policy không vi phạm hoặc kiểm tra bảo mật đã chạy.
- **Thiết kế nội dung kiểm thử (test design):** quyết định **điều gì phải được kiểm chứng**, kết quả nào đúng, dữ liệu đầu vào nào đại diện cho yêu cầu, tình huống biên/lỗi/rủi ro nào phải có, và bằng chứng nào chứng minh hành vi ứng dụng đáp ứng hợp đồng nghiệp vụ.

**Build gate là bộ máy thực thi và ra quyết định theo tiêu chí; test design là quá trình lựa chọn tiêu chí và các tình huống có ý nghĩa.** Không bên nào thay thế bên nào.

```text
Yêu cầu và rủi ro nghiệp vụ
            |
            v
Thiết kế kịch bản, dữ liệu, expected result
            |
            v
Viết test code (JUnit, contract/IT/E2E, ...)
            |
            v
Maven lifecycle + plugins + quality rules
            |
            v
Report tests/coverage/static analysis/security
            |
            v
Cổng chất lượng: PASS / FAIL theo tiêu chí
            |
            v
Đánh giá rủi ro còn lại và quyết định release
```

Một hệ thống có thể rơi vào bốn tình trạng:

| Nội dung test | Build gate | Ý nghĩa |
| --- | --- | --- |
| Tốt, phản ánh yêu cầu và rủi ro | Được cấu hình đúng, thực thi đủ | Bằng chứng chất lượng đáng tin hơn; vẫn không chứng minh không có lỗi |
| Yếu, chỉ thử happy path | Xanh | **Xanh giả về mặt kỳ vọng chất lượng:** plugin làm đúng việc, nhưng thiếu những kiểm tra cần thiết |
| Tốt | Không chạy hoặc bị skip/ignore | Test có giá trị nhưng **không được dùng làm cổng chặn lỗi** |
| Yếu | Cấu hình quá nghiêm hoặc không ổn định | Build đỏ liên tục nhưng chưa chắc đang chặn đúng loại rủi ro |

Không nên ghi “đã kiểm thử đầy đủ” chỉ vì `mvn test` hoặc `mvn verify` trả exit code `0`. Cần biết **đã chạy những tests nào, chúng xác minh yêu cầu gì, đã phát hiện được những lỗi giả định nào và còn thiếu gì**.

## 2. Đặt đúng tên từng loại bằng chứng

| Thành phần | Câu hỏi nó trả lời tốt | Câu hỏi nó không thể tự trả lời |
| --- | --- | --- |
| Java Compiler Plugin | Source có biên dịch được theo release/target JDK không? | Thuật toán có đúng với yêu cầu không? |
| Maven Surefire Plugin | Những unit tests được phát hiện/chạy ở phase `test` có pass không? | Có đủ test case nghiệp vụ cần thiết chưa? |
| Maven Failsafe Plugin | Những integration tests được cấu hình ở `integration-test`/`verify` có pass không? | Mọi môi trường production/hệ thống ngoài có tương thích không? |
| Maven Enforcer Plugin | Maven/JDK/dependency/version constraints có thỏa rule không? | Logic nghiệp vụ có chính xác không? |
| JaCoCo | Những instructions/branches đã thực sự được thực thi trong JVM có agent không? | Assertion có đúng, oracle độc lập và các yêu cầu có được kiểm thử không? |
| Checkstyle/PMD/SpotBugs | Có vi phạm những quy tắc style/static analysis đã cấu hình không? | Runtime behavior trong mọi kịch bản có đúng không? |
| Dependency/security scanning | Có vấn đề dependency/vulnerability được công cụ nhận diện không? | Không có lỗi zero-day hoặc lỗi nghiệp vụ? |
| JUnit assertions và IT contracts | Actual output có khớp expected result do test mô tả không? | Expected result có được chọn đúng từ requirement không? |
| Review/test design | Bộ kịch bản có bám rủi ro/requirements/boundaries không? | Nó không tự chạy/ghi report nếu thiếu automation |
| CI pipeline | Những jobs bắt buộc có chạy đúng phiên bản/commit và pass không? | Nó không bảo đảm những tests chưa từng viết sẽ được phát hiện |

**Nguyên tắc:** hãy tách “công cụ chạy đúng” khỏi “chúng ta đã hỏi đúng câu hỏi”.

## 3. Maven lifecycle: `test`, `package` và `verify` không giống nhau

Với Maven project `packaging=jar`:

```text
validate
  |
compile               -> compiler:compile
  |
test-compile           -> compiler:testCompile
  |
test                   -> surefire:test
  |
package                -> jar:jar
  |
pre-integration-test
  |
integration-test        -> failsafe:integration-test, nếu đã bind
  |
post-integration-test  -> dọn test environment, nếu có executions
  |
verify                 -> failsafe:verify và các checks, nếu đã bind
```

Các điểm quan trọng:

1. `mvn test` chạy các phases đến `test`: compile main/test sources và **Surefire unit tests** trong cấu hình phổ biến.
2. `mvn package` đi qua `test` trước khi tạo JAR: có thể chạy unit tests, **không tự bao gồm full Failsafe verification**.
3. `mvn verify` đi qua `package`, rồi các phases cho integration tests và các quality checks được bind phù hợp.
4. Failsafe không chạy chỉ vì file tên `*IT.java` có trong `src/test/java`: phải có plugin/execution tương ứng.
5. Failsafe được thiết kế để báo lỗi test ở `verify`, cho phép `post-integration-test` cleanup chạy sau integration tests. **Đừng lấy riêng `mvn integration-test` làm quality gate cuối**.
6. `verify` không tự quét chất lượng ngoài nội dung/plugin executions đã cấu hình. Một project không có tests hay rules vẫn có thể `BUILD SUCCESS`.

### “Maven build đỏ” cũng không cho biết ngay lỗi ở đâu

- `compile` fail: lỗi cú pháp/types/import/runtime API level.
- `test` fail: Surefire gặp assertion/exception/fork error.
- `package` fail: JAR/WAR/manifest/shading plugin lỗi.
- `integration-test`/`verify` fail: Failsafe tests, cleanup hoặc quality checker lỗi.
- `enforcer:enforce` fail: rule môi trường/dependency không thỏa.
- `jacoco:check` fail: coverage metric dưới threshold.
- Build infrastructure fail: repo timeout, Docker unavailable, credentials, cache/quota.

Tất cả có thể tạo non-zero exit, nhưng **cách khắc phục khác nhau**. Không nên sửa test assertion khi lỗi thực ra do Maven repository không truy cập được.

## 4. Thiết kế test bắt đầu từ yêu cầu, không bắt đầu từ plugin

Quy trình đúng thường là:

1. Thu thập **requirements/acceptance criteria**: ứng dụng cần làm gì và điều gì bị cấm?
2. Chia **lớp kiểm thử**: unit, integration, API/contract, end-to-end, security/performance khi phù hợp.
3. Xác định **test oracle**: giá trị đúng là gì, lấy từ đặc tả/luật độc lập nào?
4. Chọn **test data theo risk**: happy path, invalid input, equivalence classes, giá trị biên, trạng thái, sequence, concurrency và failure recovery.
5. Viết tests cô lập, deterministic, có assertions cụ thể, phản hồi hữu ích.
6. Đưa tests vào Maven lifecycle đúng plugin/phase để build gate có thể thực thi và chặn regression.
7. Kiểm tra báo cáo và coverage/mutation khi thích hợp, rồi duy trì khi yêu cầu thay đổi.

**Oracle là điểm phân biệt rất lớn**: `assertEquals(actual, actual)` luôn pass nhưng hầu như vô nghĩa. Một test chỉ kiểm tra kết quả “khác null” không xác minh con số phí hay quy tắc giảm giá đúng.

### Ví dụ test yếu nhưng luôn xanh

```java
// Đoạn minh họa phản ví dụ, KHÔNG thay cho bộ test nên có.
@Test
void canCallMethod() {
    long actual = PriceRule.payableCents(10_000, true);
    assertTrue(actual >= 0);
}
```

Nếu quy tắc đúng phải trả `9_000`, nhưng implementation lỗi trả `10_000`, test trên **vẫn pass**. Maven Surefire không thể suy ra expected value mà bạn chưa mô tả.

Một test mạnh hơn:

```java
@Test
void memberGetsTenPercentDiscountAtThreshold() {
    assertEquals(9_000, PriceRule.payableCents(10_000, true));
}
```

Ở đây giá trị `9_000` đến từ **yêu cầu nghiệp vụ**, không phải copy công thức từ implementation.

## 5. Bài toán ví dụ: quy tắc giá cuối cùng theo số xu

Ta thiết kế một yêu cầu nhỏ để quan sát sự khác biệt giữa build và test design.

**Hợp đồng nghiệp vụ:**

- Dữ liệu `subtotalCents` là số nguyên `long`, đơn vị **cent** (hoặc đơn vị tiền nhỏ nhất), không âm.
- Nếu **không phải thành viên**: không giảm giá.
- Nếu **là thành viên** và `subtotalCents < 10_000`: không giảm giá.
- Nếu **là thành viên** và `subtotalCents >= 10_000`: giảm **10% giá trị trước giảm**.
- Số tiền giảm được **làm tròn xuống đến cent nguyên**: discount `= subtotalCents / 10` với phép chia nguyên.
- Giá cuối `payableCents = subtotalCents - discount`.
- Với input âm: ném `IllegalArgumentException`, không tự quy đổi thành 0.

**Đây là một quy tắc giả định cho bài học**, không đại diện cho thuế/giảm giá ngoài đời thực. Trong sản phẩm tài chính thực, việc làm tròn, thuế, hoàn tiền, tiền tệ và hạn mức phải có yêu cầu riêng.

### Phân lớp tương đương và giá trị biên

| Tình huống | Input `(subtotal, member)` | Expected |
| --- | --- | --- |
| Số tiền bằng 0 | `(0, false)` | `0` |
| Dưới ngưỡng một cent, thành viên | `(9_999, true)` | `9_999` |
| Đúng ngưỡng, thành viên | `(10_000, true)` | `9_000` |
| Trên ngưỡng một cent, thành viên | `(10_001, true)` | `9_001` |
| Không thành viên ngay ngưỡng | `(10_000, false)` | `10_000` |
| Thành viên trên ngưỡng | `(20_000, true)` | `18_000` |
| Kiểm tra phép chia nguyên | `(17_777, true)` | `16_000` |
| Input âm | `(-1, true)` | Ném `IllegalArgumentException` |

**Vì sao `17_777 -> 16_000`?** `17_777 / 10` (chia nguyên) là `1_777`; `17_777 - 1_777 = 16_000`. Nếu dùng `double` và làm tròn khác quy ước, có thể cho kết quả khác.

Điều quan trọng là kịch bản được chọn từ **hợp đồng**, không chọn chỉ để tăng dòng coverage. `9_999`, `10_000` và `10_001` phân biệt các lỗi `>` so với `>=`.

### Một yêu cầu thường bị quên

Ví dụ nếu requirement nói “không nhận số âm”, thì `payableCents(-1, true)` phải có expected result là **exception**, không phải một con số. Plugin không tự biết cần test exception; người thiết kế test phải bổ sung.

## 6. Cấu trúc project Java 17 và POM hoàn chỉnh

Ví dụ là một module Maven với:

- Unit tests của `PriceRule` do **Surefire** chạy ở phase `test`.
- Integration-style test chạy **JAR đã package** qua một Java subprocess, do **Failsafe** chạy sau `package` và đánh giá tại `verify`.
- **Maven Enforcer** kiểm tra Maven/JDK build constraints.
- **JaCoCo** tạo báo cáo coverage; không giả định coverage cao đồng nghĩa assertions tốt.
- Cấu hình `failIfNoTests=true` để CI không xanh khi vô tình không có test nào phù hợp.
- **Java 17**, JUnit Jupiter 5.11.4, plugin versions pin.

### Cấu trúc tệp

```text
quality-gates-demo/
├── pom.xml
└── src/
    ├── main/java/dev/lesson/quality/
    │   ├── PriceRule.java
    │   └── QuoteCli.java
    └── test/java/dev/lesson/quality/
        ├── PriceRuleTest.java
        └── QuoteCliIT.java
```

Không cần internet lúc **chạy ứng dụng**, nhưng lần build đầu Maven cần dependencies/plugins trong local cache hoặc repository có thể truy cập.

### `pom.xml` đầy đủ

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.lesson</groupId>
    <artifactId>quality-gates-demo</artifactId>
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
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-enforcer-plugin</artifactId>
                <version>3.5.0</version>
                <executions>
                    <execution>
                        <id>require-build-environment</id>
                        <goals>
                            <goal>enforce</goal>
                        </goals>
                        <configuration>
                            <rules>
                                <requireMavenVersion>
                                    <version>[3.8,4)</version>
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
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
                <configuration>
                    <archive>
                        <manifest>
                            <mainClass>dev.lesson.quality.QuoteCli</mainClass>
                        </manifest>
                    </archive>
                </configuration>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.2</version>
                <configuration>
                    <failIfNoTests>true</failIfNoTests>
                </configuration>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-failsafe-plugin</artifactId>
                <version>3.5.2</version>
                <configuration>
                    <failIfNoTests>true</failIfNoTests>
                    <systemPropertyVariables>
                        <demo.jar>${project.build.directory}/${project.build.finalName}.jar</demo.jar>
                    </systemPropertyVariables>
                </configuration>
                <executions>
                    <execution>
                        <id>verify-executable-artifact</id>
                        <goals>
                            <goal>integration-test</goal>
                            <goal>verify</goal>
                        </goals>
                    </execution>
                </executions>
            </plugin>

            <plugin>
                <groupId>org.jacoco</groupId>
                <artifactId>jacoco-maven-plugin</artifactId>
                <version>0.8.13</version>
                <executions>
                    <execution>
                        <id>prepare-coverage-agent</id>
                        <goals>
                            <goal>prepare-agent</goal>
                        </goals>
                    </execution>
                    <execution>
                        <id>generate-coverage-report</id>
                        <phase>verify</phase>
                        <goals>
                            <goal>report</goal>
                        </goals>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
```

**Tại sao POM này là ví dụ của hai hoạt động?**

- `enforcer:enforce` kiểm tra build environment, **không** kiểm tra quy tắc giảm giá.
- Compiler kiểm tra Java 17 source, **không** biết kết quả `payableCents` đúng hay sai.
- `surefire:test` chạy tests đã viết cho `PriceRule`.
- `failsafe:integration-test` chạy tests có hậu tố `IT` nhằm xác nhận **JAR thực tế** được đóng gói và có thể chạy đúng contract.
- `failsafe:verify` đánh giá kết quả IT sau integration-test lifecycle.
- `failIfNoTests=true` giúp phát hiện không tìm thấy test suite ở bước tương ứng. Khi thêm module không có test trong reactor, cần điều chỉnh policy thay vì copy một cách mù quáng.
- `jacoco:prepare-agent` đưa Java agent vào test JVM qua `argLine` của plugins theo mặc định; `jacoco:report` tạo coverage report ở `verify`.
- POM hiện **chưa đặt ngưỡng `jacoco:check`**, vì cần xem coverage data/scope đã thu được trước khi áp threshold phù hợp; phần sau có ví dụ thiết kế gate.

**Giới hạn phạm vi:** các Maven plugins được pin để demo tương thích. Cùng một version plugin có thể có behavior đặc thù theo JDK, local repository và test provider; luôn đối chiếu logs/reports thực tế.

## 7. Production code: `PriceRule.java`

Tạo `src/main/java/dev/lesson/quality/PriceRule.java`:

```java
package dev.lesson.quality;

public final class PriceRule {

    private PriceRule() {
    }

    public static long payableCents(long subtotalCents, boolean member) {
        if (subtotalCents < 0) {
            throw new IllegalArgumentException("subtotalCents must be non-negative");
        }

        if (!member || subtotalCents < 10_000) {
            return subtotalCents;
        }

        long discount = subtotalCents / 10;
        return subtotalCents - discount;
    }
}
```

Đây là implementation đúng với contract của mục 5:

- Không có floating-point currency arithmetic.
- Thành viên chỉ được giảm 10% từ ngưỡng `10_000` trở lên.
- Chiết khấu là phép chia nguyên, làm tròn xuống phần cent lẻ.
- Input âm bị từ chối tường minh.
- Hàm **pure**: không đọc database, thời gian, random hay network, rất phù hợp cho unit tests.

### Tại sao dùng `long` thay `double`?

Tiền tệ nên biểu diễn theo đơn vị nhỏ nhất hoặc kiểu decimal được quy định; `double` có thể có lỗi biểu diễn số thập phân. Với ví dụ đơn giản, `long` cents cho expected values chính xác, dễ test biên. Trong hệ thống thực vẫn cần xét overflow, currency precision và tax policy; nếu thêm các phép nhân/tổng không an toàn, có thể cân nhắc `Math.addExact`/`Math.multiplyExact` hoặc `BigDecimal`.

## 8. Entry point để kiểm tra JAR runtime: `QuoteCli.java`

Tạo `src/main/java/dev/lesson/quality/QuoteCli.java`:

```java
package dev.lesson.quality;

public final class QuoteCli {

    private QuoteCli() {
    }

    public static void main(String[] args) {
        if (args.length != 2
                || (!"true".equals(args[1]) && !"false".equals(args[1]))) {
            System.err.println("Usage: QuoteCli <subtotalCents> <true|false>");
            System.exit(2);
            return;
        }

        long subtotalCents = Long.parseLong(args[0]);
        boolean member = Boolean.parseBoolean(args[1]);

        System.out.println(
                "PAYABLE_CENTS=" + PriceRule.payableCents(subtotalCents, member)
        );
    }
}
```

`QuoteCli` là một **thin CLI wrapper** gọi nghiệp vụ `PriceRule` và in kết quả. `maven-jar-plugin` trong POM đã ghi `Main-Class: dev.lesson.quality.QuoteCli`, nên JAR có thể chạy bằng `java -jar` mà không cần runtime libraries ngoài JDK.

**Giới hạn đã công bố của demo:** đối số `subtotalCents` không phải số sẽ gây `NumberFormatException`, input âm gây `IllegalArgumentException`; code tập trung minh họa build/test contract chứ không phải một CLI production với mọi mã lỗi được chuẩn hóa. Test design cho sản phẩm thật cần bổ sung expected behavior cho input sai kiểu, số vượt miền, usage message và chính sách error code.

Đầu ra khi chạy đúng:

```bash
java -jar target/quality-gates-demo-1.0.0.jar 10000 true
```

**Một dòng stdout do chương trình in khi thành công:**

```text
PAYABLE_CENTS=9000
```

Java `println` thêm ký tự xuống dòng theo hệ điều hành. Giá trị nội dung của dòng là chính xác; output/stacktrace phụ khác sẽ chỉ có khi runtime gặp vấn đề.

## 9. Unit tests: thiết kế đúng giá trị biên và negative cases

Tạo `src/test/java/dev/lesson/quality/PriceRuleTest.java`:

```java
package dev.lesson.quality;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

class PriceRuleTest {

    @ParameterizedTest
    @CsvSource({
        "0, false, 0",
        "9999, true, 9999",
        "10000, true, 9000",
        "10001, true, 9001",
        "10000, false, 10000",
        "20000, true, 18000",
        "17777, true, 16000"
    })
    void computesFinalAmount(long subtotalCents, boolean member, long expected) {
        assertEquals(expected, PriceRule.payableCents(subtotalCents, member));
    }

    @Test
    void rejectsNegativeSubtotal() {
        IllegalArgumentException error = assertThrows(
                IllegalArgumentException.class,
                () -> PriceRule.payableCents(-1, true)
        );
        assertEquals("subtotalCents must be non-negative", error.getMessage());
    }
}
```

JUnit Jupiter `@ParameterizedTest` chạy mỗi dòng `@CsvSource` như một invocation độc lập. Ở đây có **7 parameterized invocations và 1 @Test**, tức **8 trường hợp unit test**.

**Vì sao đây là test design có chất lượng hơn “assert non-null”?**

- Test đúng ngưỡng `10_000` và **hai phía** `9_999`/`10_001`.
- Kiểm tra hai nhánh thành viên/không thành viên.
- Kiểm tra quy tắc chia nguyên với số không chia hết cho 10.
- Kiểm tra lỗi input âm và thông điệp exception.
- Expected values được viết **từ hợp đồng nghiệp vụ** ở mục 5, không sao chép hàm đang kiểm thử để tính expected.

Một cách làm kém hơn:

```java
// Phản ví dụ: expected được tính bằng chính công thức implementation.
long subtotal = 17_777;
long expected = subtotal - subtotal / 10;
assertEquals(expected, PriceRule.payableCents(subtotal, true));
```

Kết quả có thể đúng, nhưng oracle độc lập kém: nếu implementation và test copy cùng một lỗi diễn giải requirement, cả hai sẽ cùng sai mà test vẫn xanh. Tốt hơn là lưu **giá trị expected đã được business/BA/QA xác nhận** hoặc tính bằng một mô hình độc lập.

## 10. Integration test: kiểm tra artifact sau `package`

Unit test ở mục 9 chứng minh `PriceRule` trả kết quả đúng trong test JVM. Nó chưa chứng minh JAR đã package có `Main-Class`, đường chạy `java -jar` và CLI arguments đúng. Đó là lý do tạo một integration-style test.

Tạo `src/test/java/dev/lesson/quality/QuoteCliIT.java`:

```java
package dev.lesson.quality;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;

class QuoteCliIT {

    private record RunResult(int exitCode, String output) {
    }

    private RunResult executeJar(String... arguments) throws Exception {
        String executable = System.getProperty("os.name")
                .toLowerCase(Locale.ROOT).contains("win") ? "java.exe" : "java";
        Path java = Path.of(System.getProperty("java.home"), "bin", executable);

        String jarFile = System.getProperty("demo.jar");
        assertNotNull(jarFile, "Failsafe must provide demo.jar");

        List<String> command = new ArrayList<>(
                List.of(java.toString(), "-jar", jarFile)
        );
        command.addAll(Arrays.asList(arguments));

        Process process = new ProcessBuilder(command)
                .redirectErrorStream(true)
                .start();

        boolean completed = process.waitFor(15, TimeUnit.SECONDS);
        if (!completed) {
            process.destroyForcibly();
        }
        assertTrue(completed, "The CLI process timed out");

        String output = new String(
                process.getInputStream().readAllBytes(),
                StandardCharsets.UTF_8
        ).trim();

        return new RunResult(process.exitValue(), output);
    }

    @Test
    void executableJarUsesTheBusinessRule() throws Exception {
        RunResult result = executeJar("10000", "true");
        assertEquals(0, result.exitCode());
        assertEquals("PAYABLE_CENTS=9000", result.output());
    }

    @Test
    void rejectsAnInvalidMemberFlag() throws Exception {
        RunResult result = executeJar("10000", "maybe");
        assertEquals(2, result.exitCode());
        assertEquals(
                "Usage: QuoteCli <subtotalCents> <true|false>",
                result.output()
        );
    }
}
```

**Các điều kiện và lời giải thích:**

1. `QuoteCliIT` match pattern mặc định Failsafe `*IT.java`. `PriceRuleTest` match Surefire pattern `*Test.java`. Hai test suites thuộc **cùng `src/test/java`**, nhưng plugin chạy chúng ở các phases khác nhau.
2. Failsafe `<demo.jar>${project.build.directory}/${project.build.finalName}.jar</demo.jar>` cung cấp đường dẫn JAR sau `package` cho test JVM.
3. `ProcessBuilder` chạy Java executable từ `java.home/bin` với `-jar`, vì vậy kiểm tra **artifact đã đóng gói thực**.
4. `redirectErrorStream(true)` trộn stderr vào stdout để assertions về usage message đơn giản. Trong production test runner có log lớn, cần xử lý stream/buffer mạnh hơn, không block vô thời hạn.
5. `waitFor(15, TimeUnit.SECONDS)` tránh treo vô hạn; timeout cần điều chỉnh theo môi trường. Nếu process chưa kết thúc, test fail.
6. Test positive xác nhận exit code `0` và dòng `PAYABLE_CENTS=9000`.
7. Test invalid member flag xác nhận exit code `2` và usage message, kiểm tra một **contract lỗi** mà unit test nghiệp vụ không thể bao phủ.
8. Java subprocess **không tự thừa hưởng JaCoCo javaagent của test JVM**. Vì vậy các lines chạy chỉ trong subprocess có thể không được tính vào JaCoCo report mặc định; đây là giới hạn đo đạc, **không phải test không được thực thi**.

**JUnit tests ở `PriceRuleTest` kiểm tra business logic; `QuoteCliIT` kiểm tra tích hợp giữa JAR manifest, launcher, argument parsing, error code và function output.** Đó là sự phân công có chủ đích, không phải “tên Test và IT cho đẹp”.

## 11. Chạy các phase để thấy cổng chất lượng hoạt động

### 11.1. Kiểm tra toolchain

Từ thư mục `quality-gates-demo/`:

```bash
mvn -version
java -version
```

POM yêu cầu Maven trong khoảng `[3.8,4)` và Java `[17,)`. Nếu Maven/JDK không thỏa rule, Enforcer chặn build ngay ở phase liên quan. Đây là **kiểm tra môi trường**, không phải kiểm thử nghiệp vụ.

### 11.2. Chạy unit tests

```bash
mvn -B -ntp clean test
```

Khi Maven resolve dependencies/plugins thành công:

- Compiler biên dịch classes.
- Surefire chạy **8 unit test invocations** từ `PriceRuleTest`.
- `QuoteCliIT` chưa được Failsafe chạy vì invocation dừng tại `test`.
- Build thành công nếu mọi unit tests và build rules pass.

Kết quả **dạng tóm tắt**, không phải console output Maven nguyên văn:

```text
Surefire: PriceRuleTest — 8 tests, 0 failures, 0 errors
Failsafe: not invoked at phase test
```

Báo cáo XML/text của Surefire thường nằm tại:

```text
target/surefire-reports/
```

### 11.3. Chạy package

```bash
mvn -B -ntp clean package
```

`package` chạy Surefire như `mvn test` rồi Jar Plugin tạo:

```text
target/quality-gates-demo-1.0.0.jar
```

Kiểm tra entry:

```bash
jar tf target/quality-gates-demo-1.0.0.jar
```

Tìm:

```text
META-INF/MANIFEST.MF
dev/lesson/quality/PriceRule.class
dev/lesson/quality/QuoteCli.class
```

Sau đó có thể chạy:

```bash
java -jar target/quality-gates-demo-1.0.0.jar 10000 true
```

**Dòng stdout chương trình:**

```text
PAYABLE_CENTS=9000
```

`mvn package` **không tự chạy `QuoteCliIT`** trong cấu hình này; phải tới `integration-test`/`verify`.

### 11.4. Chạy `verify` đầy đủ

```bash
mvn -B -ntp clean verify
```

Khi thành công, kỳ vọng về mặt logic:

```text
Enforcer: Maven/JDK requirements passed
Surefire: PriceRuleTest, 8 tests passed
Jar Plugin: quality-gates-demo-1.0.0.jar built
Failsafe integration-test: QuoteCliIT, 2 tests passed
Failsafe verify: integration tests verified
JaCoCo report: coverage files generated
BUILD SUCCESS
```

Đây là **bản tóm tắt các kết quả mong đợi**, không phải stdout nguyên văn/cam kết log order. Execution IDs, provider logs, file path và số liệu coverage phụ thuộc plugin/environment.

Như vậy với demo có tổng cộng **10 test invocations**: 8 unit, 2 integration. Đừng nhầm 10 test pass với 10 yêu cầu nghiệp vụ khác nhau: số lần test chạy không phải số yêu cầu đã bao phủ.

Báo cáo cần đối chiếu:

```text
target/surefire-reports/
target/failsafe-reports/
target/site/jacoco/index.html
target/site/jacoco/jacoco.xml
target/jacoco.exec
```

JaCoCo có thể không có file XML nếu cấu hình report formats bị đổi; các đường dẫn trên là defaults phổ biến theo plugin version. Khi test subprocess không có agent, coverage của CLI code có thể thấp hơn thực tế những lệnh IT đã chạy.

## 12. Thử một lỗi cố ý: build không tự biết expected answer

Giả sử một developer vô tình sửa trong `PriceRule.java`:

```java
// Dòng sai — chỉ để minh họa, KHÔNG dùng làm bản phát hành.
if (!member || subtotalCents <= 10_000) {
    return subtotalCents;
}
```

Dấu `<=` thay vì `<` làm thành viên **không được giảm giá khi đúng ngưỡng 10_000**. Với dữ liệu `(10_000, true)`, method trả `10_000` thay vì `9_000`.

**Nếu bộ test chỉ có phản ví dụ `assertTrue(actual >= 0)`**, Maven Surefire vẫn có thể báo xanh. Cùng một code lỗi nhưng có assertion:

```java
assertEquals(9_000, PriceRule.payableCents(10_000, true));
```

thì unit test sẽ fail. Không phải Maven “thông minh hơn” ở trường hợp thứ hai; **thiết kế test đã cung cấp oracle cụ thể hơn**.

### Một lỗi khác: sai quy tắc làm tròn

Nếu developer tính:

```java
// Sai so với quy tắc chia nguyên của bài học:
long discount = Math.round(subtotalCents * 0.10);
```

với input `17_777`, discount có thể thành `1_778` và kết quả `15_999`; test expected `16_000` sẽ phát hiện sự khác biệt. Kết quả này cũng minh họa vì sao dùng floating-point/rounding rules cần được quy định rõ.

**Không cần lưu các phiên bản code sai vào Git.** Đây là thí nghiệm đọc/so sánh. Nếu thực hành, hoàn nguyên production code sau khi xác nhận test fail.

## 13. Tránh “build xanh nhưng không có test”

Surefire có tham số `failIfNoTests`; theo tài liệu, mặc định thường là `false`. Vì thế một project có thể hoàn thành `mvn test` với **0 tests** khi class names không match, dependency test engine thiếu hoặc không có test source.

Trong POM demo, chúng ta khai:

```xml
<configuration>
    <failIfNoTests>true</failIfNoTests>
</configuration>
```

cho cả Surefire và Failsafe. Nếu một plugin không tìm thấy tests phù hợp ở phase của nó, build sẽ fail thay vì báo thành công im lặng.

**Cẩn thận với multi-module:** một module chỉ là parent `packaging=pom` có thể không có tests, module thư viện chỉ có unit tests hoặc module nào đó không có ITs. Đừng copy `failIfNoTests=true` vào mọi module rồi coi build failures là lỗi nghiệp vụ. Chọn scope/rules theo kiến trúc reactor.

### Tên test và plugin discovery

Thông thường:

- Surefire: `Test*.java`, `*Test.java`, `*Tests.java`, `*TestCase.java`.
- Failsafe: `IT*.java`, `*IT.java`, `*ITCase.java`.

Tên file không tự kiểm tra nội dung test. `PriceRuleTest` có thể chứa 0 meaningful assertions mà vẫn được đếm là test nếu method chạy. `QuoteCliIT` chỉ được Failsafe chạy khi plugin executions được bind.

### Cờ skip có thể làm gate bị vô hiệu hóa

```bash
mvn verify -DskipTests=true -DskipITs=true
mvn verify -Dmaven.test.skip=true
mvn verify -Dmaven.test.failure.ignore=true
```

Không dùng các cờ này trong quality gate bắt buộc mà không có chính sách rõ:

- `skipTests` với Surefire thường bỏ chạy unit tests nhưng vẫn compile test code.
- `skipITs` dành cho Failsafe integration tests.
- `maven.test.skip` có thể bỏ cả **test compilation** thông qua Compiler Plugin.
- `maven.test.failure.ignore` **không biến test fail thành test pass**, nhưng có thể cho phép build tiếp tục mặc dù có failures.
- Chú ý **phiên bản Failsafe**: các bản 3.5.x thường nhận `skipTests` theo user property; từ Failsafe 3.6.0, binding đó đã thay đổi. Muốn rõ ý định skip IT nên dùng `skipITs`.

**Một pipeline có thể “BUILD SUCCESS” vì đã skip mọi thứ.** Vì thế báo cáo CI phải nêu test counts/skips và effective flags, không chỉ exit code.

## 14. Coverage: hữu ích nhưng không bằng chất lượng test

JaCoCo có các counters như LINE, BRANCH, INSTRUCTION, METHOD, CLASS và COMPLEXITY. Nó trả lời câu hỏi “đã đi qua phần code nào trong những JVM được instrumented?”, không trả lời “assertions có bắt được lỗi nghiệp vụ không?”.

Ví dụ test:

```java
@Test
void callsMethodWithoutCheckingValue() {
    PriceRule.payableCents(10_000, true);
}
```

có thể tăng line/branch coverage khi code được chạy, nhưng **không xác nhận output**. Code sai cũng có thể được thực thi đầy đủ rồi test vẫn pass.

### Tại sao 100% line coverage không chứng minh không lỗi?

- Không kiểm tra expected values.
- Không bao phủ hết combinations và state sequences.
- Branch coverage khác line coverage.
- Một nhánh có thể được thực thi với dữ liệu không đủ phân biệt logic đúng/sai.
- Mock có thể che đi sự cố integration thật.
- Race conditions, timezone, locale, retries và upstream outages có thể chưa được thử.
- Test oracle có thể chép lại sai lầm của implementation.

**Sử dụng coverage như tín hiệu tìm gaps**, không làm KPI duy nhất.

### Bật coverage gate có chủ đích

POM demo đã có `prepare-agent` và `report`. Sau khi quan sát coverage baseline, có thể **thêm một execution khác** trong cấu hình `jacoco-maven-plugin`:

```xml
<execution>
    <id>enforce-branch-coverage</id>
    <phase>verify</phase>
    <goals>
        <goal>check</goal>
    </goals>
    <configuration>
        <rules>
            <rule>
                <element>BUNDLE</element>
                <limits>
                    <limit>
                        <counter>BRANCH</counter>
                        <value>COVEREDRATIO</value>
                        <minimum>0.60</minimum>
                    </limit>
                </limits>
            </rule>
        </rules>
    </configuration>
</execution>
```

**Đây là đoạn cấu hình minh họa, không nằm trong POM đầy đủ của demo.** Threshold `0.60` chỉ để minh họa cú pháp, **không phải tiêu chuẩn chất lượng mặc định** cho mọi dự án. Nếu thêm, build `verify` sẽ fail khi coverage branch ratio thấp hơn minimum trong JaCoCo execution data.

Vì integration test ở mục 10 chạy một Java subprocess **không mang JaCoCo agent**, coverage report không nhất thiết ghi nhận những branches chỉ được thực thi trong subprocess. Không nên tăng threshold mù quáng rồi kết luận “IT không hề chạy”. Nếu cần đo coverage xuyên process, phải cấu hình agent/exec merge rõ ràng hoặc đo theo chiến lược instrumentation khác.

JaCoCo `check` chỉ biết counters/rules, **không phát hiện việc một requirement quan trọng chưa có trong test plan**. Phải xem coverage và traceability cùng nhau.

## 15. Thước đo nâng cao: mutation testing

Một cách bổ trợ là **mutation testing**: công cụ tạo những thay đổi nhỏ có chủ đích trong code (ví dụ đổi `<` thành `<=`, đổi phép cộng/trừ, điều kiện true/false) rồi chạy bộ test.

- Nếu test suite fail với code đã bị “mutate”, mutation đó được **killed**; có tín hiệu rằng test nhạy với thay đổi.
- Nếu test suite vẫn pass, mutation **survived**; có thể là một lỗ hổng test design.
- Một số mutations **equivalent** về hành vi hoặc không có ý nghĩa ở miền input thực, nên score không phải chân lý tuyệt đối.
- Mutation testing đòi thời gian chạy lớn hơn và cũng không thay thế integration/security/performance testing.

Trong bài toán `PriceRule`, mutation đổi `subtotalCents < 10_000` thành `<= 10_000` đáng lẽ được phát hiện bởi test boundary `10_000`. Mutation bỏ exception với input âm được phát hiện bởi `rejectsNegativeSubtotal`.

Các công cụ như PIT có thể hỗ trợ Maven mutation testing; cần dùng đúng version/plugin configuration và giải thích kết quả theo codebase thay vì ép một mutation score tuyệt đối cho mọi module.

## 16. Phân tầng kiểm thử theo phạm vi rủi ro

| Tầng kiểm thử | Kịch bản phù hợp | Tốc độ/độ cô lập | Cổng build phổ biến |
| --- | --- | --- | --- |
| Unit | Quy tắc thuần, đầu vào biên, exceptions, transformations | Rất nhanh, ít phụ thuộc | Surefire `test` |
| Component | Controller/service với fake/in-memory dependencies | Nhanh-trung bình | Surefire hoặc Failsafe tùy cấu hình |
| Integration | Database transactions, filesystem, message broker, executable artifact | Chậm hơn, cần setup/teardown | Failsafe `integration-test` + `verify` |
| Contract/API | HTTP status/body/schema, compatibility với consumers | Trung bình, cần host/API | Failsafe/contract plugin |
| End-to-end | Luồng người dùng qua nhiều services | Chậm, dễ biến động | CI job riêng hoặc Failsafe khi phù hợp |
| Security | AuthN/AuthZ, data validation, dependency scanning, secrets | Theo công cụ và môi trường | Security scans + targeted tests |
| Performance | Latency, throughput, memory, load behavior | Tốn tài nguyên, cần baseline | Dedicated pipeline/perf environment |
| Resilience | Retry, timeout, circuit breaker, failover, partial outage | Tùy mức độ phức tạp | Targeted IT/chaos tests |

Không phải mọi project cần một test E2E cho từng dòng code. Thiết kế hợp lý thường là nhiều unit tests nhanh, một số integration tests thật sự có giá trị và số lượng E2E vừa đủ để bảo vệ các hành trình quan trọng.

### Test đúng tầng có ý nghĩa gì?

Để kiểm tra `PriceRule.payableCents` với `9_999`, một unit test là đủ; không cần khởi động Docker và HTTP server. Để kiểm tra JAR manifest/CLI args/exit code, test subprocess `QuoteCliIT` có giá trị hơn unit test gọi static method. Để kiểm tra phiên bản migration database, phải dùng DB test environment thật hoặc test container, không chỉ mock mọi query.

**Cổng chất lượng chỉ có ích khi mỗi lớp test chọn đúng ranh giới hệ thống.**

## 17. Test case design: không chỉ dữ liệu mà cả trạng thái và sequence

Bên cạnh partition/boundary ở mục 5, những kỹ thuật phổ biến:

### 17.1. Equivalence partitioning

Chia miền input có cùng expected behavior: subtotal âm, subtotal không âm dưới ngưỡng, subtotal đúng/vượt ngưỡng, member=false. Chọn đại diện cho từng lớp.

### 17.2. Boundary value analysis

Test ngay dưới/đúng/trên điểm chuyển trạng thái. Với ngưỡng `10_000`, chọn `9_999`, `10_000`, `10_001` để bắt lỗi so sánh `<`/`<=`.

### 17.3. Decision tables

Nếu có nhiều điều kiện (member, voucher, country, tax mode), viết bảng tổ hợp điều kiện/expected actions, xác định rules ưu tiên. Không nhất thiết exhaustive mọi tổ hợp nếu quá nhiều; ưu tiên risk và rule interactions.

### 17.4. State-transition testing

Với order lifecycle `CREATED -> PAID -> REFUNDED`, test chuyển trạng thái hợp lệ và bất hợp lệ. Một test gọi riêng `pay()` không chứng minh `refund()` bị chặn khi order chưa paid.

### 17.5. Negative/error-path testing

Kiểm tra invalid input, timeout, permission denied, duplicate messages, bad schema, partial data. Đặt expected error code/exception và trạng thái dữ liệu sau lỗi, không chỉ “có exception là đủ”.

### 17.6. Property-based và metamorphic testing

Một số invariants dùng được khi không có output cố định cho mọi input: chẳng hạn `payableCents(x,false)==x` với mọi `x >=0`; kết quả không âm và không vượt subtotal; với member eligible, payable không tăng khi áp dụng discount. Các properties phải **thực sự đúng theo requirement**, không được viết quá rộng rồi tạo false failures.

Trong bài demo, test cases cụ thể vẫn quan trọng, vì property `payable <= subtotal` không đủ bắt lỗi “không giảm giá tại ngưỡng”.

## 18. Độ tin cậy của kiểm thử: flaky tests và isolation

Một cổng chất lượng nghiêm ngặt nhưng có test flakiness cao sẽ bị mất giá trị. Nguyên nhân thường gặp:

- Dựa vào thời gian thực (`LocalDateTime.now()`), timezone hoặc locale của máy chạy.
- Dùng random không ghi seed, test thứ tự ngầm định hoặc shared mutable state.
- Test phụ thuộc network/public API không ổn định.
- Database/file fixture không reset giữa các tests.
- Port 8080 cố định bị một process khác chiếm.
- Quá trình bất đồng bộ chưa hoàn tất nhưng assertion chạy ngay.
- Resource cleanup thiếu, đặc biệt khi integration test fail.
- Container version/base image biến động.

Các cách giảm:

- Clock/Random có thể inject và cố định trong unit tests.
- Cô lập test data, dùng transactions/fixtures có cleanup.
- Dùng temporary directory qua JUnit `@TempDir` khi test filesystem.
- Dùng dynamic port thay vì hardcode khi có web server.
- Có timeout hợp lý và đợi theo trạng thái (eventual consistency) thay vì sleep tùy tiện.
- Pin dependency/toolchain/image versions.
- Tách tests chậm/phụ thuộc môi trường ra tầng IT/E2E; có đủ setup/teardown.

**Rerun test cho xanh không phải chứng minh lỗi đã hết.** Surefire/Failsafe có tùy chọn rerun failures ở một số phiên bản; nếu dùng, phải ghi nhận flakes/rerun counts và xử lý nguyên nhân. Đừng che test fail bằng `maven.test.failure.ignore`.

## 19. Cổng chất lượng trong CI: từ rule đến evidence

Một pipeline Java Maven hợp lý có thể có các bước:

```text
Commit / Pull Request
    |
mvn -B -ntp clean verify
    |
    +-- enforce Maven/JDK/dependency policy
    +-- compile main and test sources
    +-- run Surefire unit tests
    +-- package JAR
    +-- run Failsafe integration tests
    +-- run JaCoCo report/check if configured
    |
Collect reports + code review
    |
Security/static analysis/contract tests (if required)
    |
Decision to merge/release based on risk
```

**Đọc báo cáo, không chỉ xem exit code**:

- Surefire reports: `target/surefire-reports`.
- Failsafe reports: `target/failsafe-reports`.
- JaCoCo HTML/XML coverage: `target/site/jacoco`.
- Enforcer/static analysis reports theo plugin config.
- Pipeline logs: có thực sự tới phase `verify`, có skip flags, có test filter hoặc profile tắt tests không?
- CI commit SHA, JDK/Maven/toolchain versions, dependency lock/policy và environment name.

### Những trạng thái nên báo cáo riêng

| Trạng thái | Điều kiện xác nhận | Không được suy ra |
| --- | --- | --- |
| `COMPILED` | Compile goal pass | Business logic đúng |
| `UNIT_TESTS_PASS` | Unit suite chạy và pass, count hợp lệ | IT/contract suite đã chạy |
| `IT_TESTS_PASS` | Failsafe test suite chạy và `verify` pass | Production integration hoàn hảo |
| `COVERAGE_GATE_PASS` | `jacoco:check` với rules phù hợp pass | Mọi assertions đều chất lượng |
| `ARTIFACT_BUILT` | File JAR/WAR và metadata đúng | App đã khởi động |
| `ARTIFACT_SMOKE_TESTED` | Process/JAR thực chạy với expected result | Security/performance/edge cases đầy đủ |
| `REVIEW_APPROVED` | Người review/QA đã đánh giá test plan và gaps | Không thể tồn tại lỗi chưa phát hiện |

Không có một cờ `BUILD SUCCESS` nào thay cho toàn bộ bảng.

## 20. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng khắc phục |
| --- | --- | --- |
| `mvn verify` success nhưng rule nghiệp vụ sai | Test oracle/edge cases chưa có | Viết kịch bản từ requirement, thêm boundary và negative tests |
| `mvn test` success dù 0 tests | Surefire không phát hiện tests, `failIfNoTests=false` | Xem reports/discovery; chọn failIfNoTests policy |
| `mvn package` pass, IT không chạy | Failsafe phase chưa đến | Dùng `mvn verify` và bind cả integration-test/verify goals |
| `mvn integration-test` xong, IT failures chưa làm build fail | Failsafe verify chưa chạy | Chạy `mvn verify` |
| `No tests were executed` | Tên test không match, engine/provider thiếu hoặc test filter sai | Kiểm tra `*Test`/`*IT`, dependencies và plugin logs |
| Build xanh do `-DskipTests` | Test execution bị bỏ qua | Kiểm tra effective flags và CI policy |
| Build xanh nhưng report có failure | `maven.test.failure.ignore=true` | Không dùng failure-ignore trong required gates |
| JaCoCo báo coverage thấp dù IT đã chạy | Tests chạy trong subprocess không có agent, hoặc classpath khác | Phân biệt measured JVMs, cấu hình agent riêng nếu cần |
| JaCoCo báo coverage cao nhưng thiếu lỗi boundary | Coverage là execution metric | Thêm explicit expected values/mutation tests |
| Enforcer fail trên máy developer | Maven/JDK ngoài allowed range | Dùng toolchain đúng hoặc thay constraint có chủ đích |
| `QuoteCliIT` fail không thấy JAR | Không chạy phase package hoặc `demo.jar` config sai | Dùng `verify`, xem Jar Plugin và Failsafe system properties |
| IT không ổn định khi CI chạy song song | Port/data/file/process shared | Cô lập fixtures, dynamic ports, cleanup |
| Test pass local fail CI | Timezone/locale/JDK/network/dependency khác | Reproduce môi trường, pin versions và log diagnostic context |
| Build fail khi mạng repository lỗi | Infrastructure failure | Xem dependency resolution/proxy/mirror, không sửa assertions |
| Unit test test lại chính công thức source | Oracle không độc lập | Lấy expected từ spec/known cases |
| Coverage target tăng liên tục nhưng bugs không giảm | KPI-driven test design | Đánh giá assertions, mutation/incident escape rate, risk coverage |

## 21. Câu hỏi tự kiểm tra

**Câu 1.** `mvn clean verify` trả `BUILD SUCCESS`. Có chứng minh không còn lỗi nghiệp vụ không?  
**Đáp án:** Không. Nó chỉ xác nhận các goals/rules/tests đã cấu hình pass trong môi trường chạy. Những tình huống chưa thiết kế vẫn có thể sai.

**Câu 2.** Một test chỉ có `assertTrue(payable >= 0)` cho đơn hàng thành viên 10.000 cent. Tại sao yếu?  
**Đáp án:** Nó không xác minh expected `9_000`; implementation trả `10_000` vẫn pass.

**Câu 3.** Với ngưỡng `10_000`, ba giá trị nào bắt lỗi `<` thay bằng `<=`?  
**Đáp án:** `9_999`, `10_000`, `10_001`; đặc biệt case đúng ngưỡng bắt lỗi so sánh.

**Câu 4.** `mvn package` có tự chạy test tên `QuoteCliIT` trong POM demo không?  
**Đáp án:** Không; Failsafe executions chạy ở các phases integration-test/verify, trong khi `package` dừng trước đó.

**Câu 5.** `PriceRuleTest` có 7 dòng `@CsvSource` và một method `@Test`. Tổng bao nhiêu test invocations?  
**Đáp án:** 8, theo behavior JUnit Jupiter parameterized test.

**Câu 6.** Vì sao `QuoteCliIT` chạy `java -jar` thay vì gọi trực tiếp `PriceRule`?  
**Đáp án:** Để xác minh **đường chạy artifact sau packaging**, gồm manifest/launcher/CLI arguments/exit code, một ranh giới unit test thuần không bao phủ.

**Câu 7.** Có thể đạt 100% line coverage nhưng vẫn có lỗi không?  
**Đáp án:** Có; coverage cho biết code đã được thực thi, không bảo đảm expected values/assertions đúng.

**Câu 8.** `failIfNoTests=true` có phù hợp mọi module parent/aggregator không?  
**Đáp án:** Không mặc định; module không có tests hợp lệ có thể fail không cần thiết. Chọn rule theo mục đích module.

**Câu 9.** Với Failsafe, tại sao cần `verify` sau `integration-test`?  
**Đáp án:** Để Failsafe đánh giá test results sau bước teardown, tránh bỏ dở cleanup.

**Câu 10.** Một mutation đổi `subtotalCents < 10_000` thành `<= 10_000`. Test nào phải bắt?  
**Đáp án:** Test `PriceRule.payableCents(10_000, true) == 9_000`.

**Câu 11.** Một IT chạy Java subprocess nhưng JaCoCo report không ghi nhận code từ subprocess. Có thể kết luận IT không chạy?  
**Đáp án:** Không. JaCoCo agent của test JVM không tự instrument một JVM con; cần xem Failsafe test results/process output và cấu hình coverage riêng.

**Câu 12.** Ai quyết định phải có test cho dữ liệu âm và ngưỡng giảm giá?  
**Đáp án:** Người thiết kế test cùng team phát triển/QA/product dựa trên requirements và rủi ro, không phải Maven Compiler/Surefire tự phát hiện.

## 22. Checklist cho một quality gate có giá trị

- [ ] Có requirements/acceptance criteria rõ và test oracle độc lập.
- [ ] Đã liệt kê happy path, edge/boundary, negative/failure cases.
- [ ] Đã xem những requirements quan trọng có test cases tương ứng chưa.
- [ ] Tests có assertion cụ thể và có thể phân biệt implementation đúng/sai.
- [ ] Không copy nguyên business algorithm làm expected result cho mọi case.
- [ ] Đã chọn đúng unit/integration/contract/E2E layer theo rủi ro.
- [ ] Unit tests có thể chạy nhanh, cô lập, deterministic.
- [ ] Tests có tên/discovery patterns phù hợp Surefire/Failsafe.
- [ ] Failsafe bind cả integration-test và verify nếu IT bắt buộc.
- [ ] Không chỉ chạy `integration-test` rồi kết luận suite pass.
- [ ] Đã đọc report counts, failure/error/skipped, không chỉ `BUILD SUCCESS`.
- [ ] `failIfNoTests` policy đúng theo từng loại module.
- [ ] CI không vô tình dùng skip/failure-ignore flags trong required gates.
- [ ] Enforcer versions/rules phù hợp JDK/Maven/build environments được hỗ trợ.
- [ ] JaCoCo coverage report/check được hiểu đúng phạm vi instrumented JVMs.
- [ ] Coverage thresholds được chọn dựa trên baseline/risk, không phải để có số đẹp.
- [ ] Có mutation testing/review khi cần đánh giá sensitivity của suite.
- [ ] Đã test artifact sau package ở ít nhất một integration/smoke path quan trọng.
- [ ] External services, data fixtures, processes/containers có setup/teardown sạch.
- [ ] Các flaky tests được điều tra và sửa, không che bằng rerun/ignore vô hạn.
- [ ] Security/performance/contract risks được đánh giá riêng khi project cần.
- [ ] CI log/report gắn đúng commit, JDK, Maven, dependencies và environment.
- [ ] Release decision xem test evidence và known risks, không chỉ một exit code.

**Kết luận:** Kiểm tra build bằng Maven là **cơ chế thực thi và chặn những vi phạm đã được mô tả**. Thiết kế nội dung kiểm thử là **quyết định thế nào là đúng và những tình huống nào phải chứng minh**. Một cổng chất lượng đáng tin cần cả hai: (1) test cases có expected result rõ, bao phủ boundary/risk thực sự; (2) plugins/lifecycle/CI bắt buộc thực thi chúng, kiểm tra reports và không cho skip ngoài chủ đích. `mvn verify` là công cụ mạnh, nhưng không thể thay tư duy kiểm thử.

## Tài liệu chính thức

- [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Apache Maven Surefire Plugin — Introduction](https://maven.apache.org/surefire/maven-surefire-plugin/)
- [Apache Maven Surefire Plugin — surefire:test Parameters](https://maven.apache.org/surefire/maven-surefire-plugin/test-mojo.html)
- [Apache Maven Failsafe Plugin — Introduction](https://maven.apache.org/surefire/maven-failsafe-plugin/)
- [Apache Maven Failsafe Plugin — failsafe:verify](https://maven.apache.org/surefire/maven-failsafe-plugin/verify-mojo.html)
- [Apache Maven Enforcer Plugin — Usage](https://maven.apache.org/enforcer/maven-enforcer-plugin/usage.html)
- [JaCoCo — Maven Plugin](https://www.jacoco.org/jacoco/trunk/doc/maven.html)
- [JaCoCo — jacoco:check](https://www.jacoco.org/jacoco/trunk/doc/check-mojo.html)
- [JUnit 5 — User Guide](https://docs.junit.org/5.11.4/user-guide/index.html)

*Các ví dụ dùng Java 17, Maven 3.8–3.x, JUnit Jupiter 5.11.4, Surefire/Failsafe 3.5.2 và JaCoCo 0.8.13. Lệnh thử nghiệm được thiết kế để kiểm chứng hai tầng unit/IT; khi chuyển sang dự án thật cần điều chỉnh dữ liệu, ranh giới test và gate rules theo yêu cầu thực tế.*
