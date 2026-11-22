# Quy tắc phát hiện tên lớp kiểm thử và nguy cơ không chạy bài nào trong Maven

## 1. Vì sao “BUILD SUCCESS” chưa chắc đã có test chạy?

Maven có thể **biên dịch mã kiểm thử thành công** rồi **kết thúc phase `test` mà không thực thi một test method nào**. Đó là một rủi ro đáng chú ý khi nhóm dùng Maven Surefire Plugin để chạy unit test: mặc định, Surefire chỉ quét **các lớp kiểm thử có tên khớp quy ước**. Một lớp có phương thức `@Test` nhưng đặt tên không khớp có thể **bị bỏ qua** mà không xuất hiện lỗi Java compile.

Ví dụ:

~~~java
package org.example.math;

import org.junit.jupiter.api.Test;

class CalculatorSpec {
    @Test
    void shouldAdd() {
        // Một phương thức test hợp lệ với JUnit Jupiter.
    }
}
~~~

Đoạn trên **chỉ là mảnh ví dụ**, chưa có toàn bộ class/phép kiểm tra. Dù có `@Test`, tên lớp `CalculatorSpec` **không** thuộc bốn mẫu tên lớp mà Surefire thường tìm theo mặc định. Nếu không cấu hình khác, nó **không được Surefire tự chọn** trong lượt quét tên lớp mặc định.

Trong khi đó, cùng ý tưởng đặt trong `CalculatorTest` thường được chọn, vì tên lớp kết thúc bằng `Test`.

**Phân biệt ba kết quả:**

- **Test source compiled:** Java compiler biên dịch tệp trong `src/test/java` thành `target/test-classes`. Chưa chứng minh test đã chạy.
- **Test class selected:** Surefire chọn class theo pattern hoặc option `-Dtest`, sau đó giao cho provider/test engine xử lý.
- **Test methods executed:** JUnit/TestNG thực sự tìm và chạy các test cases hợp lệ; có thể không có method nào, hoặc tất cả bị disable/filtered.

Do đó, **Maven build success ≠ có test thực chạy ≠ test coverage đạt yêu cầu**.

Bài học này giải thích các quy tắc naming của Surefire, nguyên nhân test bị bỏ qua, cách sửa naming hoặc `includes/excludes`, khác biệt với Failsafe, và cách chống “0 tests” trên CI.

## 2. Surefire tham gia Maven lifecycle ở đâu?

Với project Maven sử dụng packaging `jar` và các lifecycle bindings thông thường:

~~~text
src/main/java                         src/test/java
      |                                     |
      v                                     v
compile phase                        test-compile phase
      |                                     |
      v                                     v
target/classes                       target/test-classes
                                            |
                                            v
                                    test phase / Surefire
                                            |
                                scan class names + excludes
                                            |
                                            v
                                   test provider / engine
                                            |
                                            v
                                   execute test cases
                                            |
                                            v
                               target/surefire-reports/
~~~

Trong lệnh:

~~~bash
mvn -B -ntp clean test
~~~

Maven chạy các phase cần thiết để compile main, compile tests rồi dùng Surefire thực thi kiểm thử. `clean` xóa output cũ để giảm khả năng test class từ lần build trước còn sót lại.

Ở một project đơn giản, các đường dẫn mặc định là:

~~~text
src/test/java/                  # source test
target/test-classes/            # .class sau test-compile
target/surefire-reports/        # báo cáo của những test mà Surefire chạy
~~~

**Không được hiểu nhầm:** Surefire không chỉ đơn giản mở mọi file `.java` chứa chữ `@Test`. Nó quét classes theo patterns được cấu hình và để provider/engine (ví dụ JUnit Platform) xác định những phương thức/test descriptors nào thực sự có thể chạy.

Nếu lệnh `mvn test` thành công nhưng không thấy kết quả test, câu hỏi đầu tiên nên là **Surefire có chọn đúng test classes hay không**, trước khi sửa logic test.

## 3. Bốn mẫu tên lớp mặc định của Maven Surefire

Theo tài liệu chính thức của Maven Surefire Plugin, khi **không cấu hình `includes` khác và không dùng `-Dtest` để chọn riêng**, Surefire tự tìm những tên lớp khớp các mẫu sau:

| Pattern mặc định | Kiểu tên được chọn | Ví dụ phù hợp |
| --- | --- | --- |
| `**/Test*.java` | Tên bắt đầu bằng `Test` | `TestCalculator.java`, `TestOrderService.java` |
| `**/*Test.java` | Tên kết thúc bằng `Test` | `CalculatorTest.java`, `OrderServiceTest.java` |
| `**/*Tests.java` | Tên kết thúc bằng `Tests` | `CalculatorTests.java`, `ValidationTests.java` |
| `**/*TestCase.java` | Tên kết thúc bằng `TestCase` | `CalculatorTestCase.java`, `PaymentTestCase.java` |

Cú pháp `**/` nghĩa là ở bất kỳ package/subdirectory nào trong cây test output, không chỉ package root. `*` là ký tự đại diện theo cú pháp pattern, không phải Java regex viết trực tiếp.

**Ví dụ không khớp mặc định:**

| Tên lớp/source | Surefire tự chọn theo bốn pattern? | Vì sao? |
| --- | --- | --- |
| `CalculatorSpec.java` | Không | Không có prefix `Test` hoặc suffix `Test`, `Tests`, `TestCase`. |
| `CalculatorCheck.java` | Không | Tên “Check” không nằm trong quy ước. |
| `CalculatorShould.java` | Không | Tên mô tả hành vi không đồng nghĩa pattern Surefire. |
| `CalculatorIT.java` | Không theo mặc định Surefire | Đuôi `IT` thường dành cho Maven Failsafe integration tests. |
| `SpecCalculator.java` | Không | Prefix `Spec` không phải `Test`. |
| `Calculatortest.java` | Không | Khác chữ hoa/thường so với `*Test`; cách đặt tên cần đúng mẫu. |
| `TestCalculator.java` | Có | Bắt đầu bằng `Test`. |
| `CalculatorTest.java` | Có | Kết thúc bằng `Test`. |
| `CalculatorTests.java` | Có | Kết thúc bằng `Tests`. |
| `CalculatorTestCase.java` | Có | Kết thúc bằng `TestCase`. |

Những pattern `*.java` trên là **cú pháp quy ước của Surefire để chọn test classes**; khi thực thi, Surefire làm việc với các **file `.class` đã biên dịch** trong `target/test-classes`. Nó không cần compile lại mọi tệp `.java` theo pattern; test compilation là phase khác. Với regex custom patterns, Surefire xét đường dẫn `.class` (xem phần sau).

Có thể đọc trực tiếp tài liệu chính thức: [Surefire — Inclusions and Exclusions of Tests](https://maven.apache.org/surefire/maven-surefire-plugin/examples/inclusion-exclusion.html).

## 4. Đặt tên theo pattern vẫn chưa bảo đảm có test method

Giả sử tệp `src/test/java/org/example/math/CalculatorTest.java`:

~~~java
package org.example.math;

public class CalculatorTest {
    public void ordinaryMethod() {
        System.out.println("This is not a JUnit Jupiter test.");
    }
}
~~~

Tên `CalculatorTest` **khớp** `**/*Test.java`; compiler có thể tạo `CalculatorTest.class`. Nhưng method trên **không có `@org.junit.jupiter.api.Test`**, cũng không đăng ký một test descriptor phù hợp theo provider/engine khác.

Vì vậy:

- **Surefire có thể chọn class** do tên.
- **JUnit Jupiter có thể không tìm thấy test method nào** trong class.
- Class này **không được tính là một unit test được chạy** chỉ vì tên chứa `Test`.

Ngược lại, một class có `@Test` hợp lệ nhưng mang tên `CalculatorSpec` vẫn có thể bị **Surefire loại ngay trước bước JUnit discovery** nếu không được chọn qua pattern hoặc option CLI.

**Hai điều kiện khác nhau phải cùng đúng** (với kiểu dự án minh họa JUnit Jupiter):

1. Class nằm ở **đúng test output** và được Surefire chọn theo tên, hoặc được chỉ định theo cách được Surefire hỗ trợ.
2. Có **test engine/provider** phù hợp và những test methods/descriptors hợp lệ, không bị toàn bộ lọc hoặc disable.

Không thể dùng riêng quy tắc đặt tên để thay thế test engine, cũng không thể dùng riêng annotation để thay thế Surefire class selection.

## 5. JUnit Jupiter, JUnit Platform và các annotation

Với JUnit 5, Surefire phải phối hợp với **JUnit Platform** và một **TestEngine** thực thi test tương ứng (thường là Jupiter engine). Các yếu tố thường cần:

- Có dependency JUnit Jupiter trong project `scope=test` để compiler nhìn thấy `@Test`, `Assertions` và engine cần thiết.
- Maven Surefire Plugin phiên bản hỗ trợ JUnit Platform (ví dụ `3.5.2` trong POM hoàn chỉnh ở phần 7).
- Class test khớp quy tắc scan hoặc được chọn tường minh.
- Test method được Jupiter nhận diện, chẳng hạn có `@Test`, `@ParameterizedTest`, `@RepeatedTest`, `@TestFactory` theo API tương ứng.
- Không bị filter tags/engines/custom includes/excludes hoặc disabled configuration loại bỏ.

Ví dụ dependency Maven:

~~~xml
<dependency>
    <groupId>org.junit.jupiter</groupId>
    <artifactId>junit-jupiter</artifactId>
    <version>5.11.4</version>
    <scope>test</scope>
</dependency>
~~~

Đây là **mảnh `project/dependencies`**, không phải POM độc lập. Artifact `junit-jupiter` tập hợp JUnit Jupiter API/engine phục vụ ví dụ. **Không** đặt JUnit test API chỉ trong `plugin/dependencies` của Surefire và mong `src/test/java` tự import được.

**Cảnh báo khác:** class có tên phù hợp nhưng mọi test bị `@Disabled`, bị lọc bởi tags (`groups`/`excludedGroups`) hoặc điều kiện môi trường đều không tạo ra một lượt thực thi hữu ích. Khi ấy log/reports có thể có chỉ số `skipped`, nhưng coverage vẫn không tăng. `failIfNoTests` không thay thế việc kiểm tra test counts và test effectiveness.

## 6. Điều gì khiến một bài test bị bỏ qua mà không có lỗi?

Các tình huống nên chủ động kiểm tra:

1. **Tên lớp không khớp:** `CalculatorSpec` có `@Test` nhưng không thuộc mặc định `Test*`/`*Test`/`*Tests`/`*TestCase`.
2. **Sai thư mục:** tệp ở `src/main/java` thay vì `src/test/java`; Maven không coi đó là test source theo layout mặc định.
3. **Chưa biên dịch test:** dùng `-Dmaven.test.skip=true` hoặc thiếu test compiler/source root.
4. **Test engine không đúng:** JUnit API có thể compile nhưng JUnit Jupiter engine không được cung cấp phù hợp.
5. **Custom includes quá hẹp:** POM chỉ include `**/*FastTest.java` khiến `CalculatorTest` bị loại.
6. **Custom excludes quá rộng:** `**/*Test.java` trong `excludes` loại toàn bộ những test tên kết thúc `Test`.
7. **Chỉ chạy một test khác:** `-Dtest=SomeOtherTest` override bộ class được chọn; test còn lại không được chạy.
8. **Lọc tags/groups:** chẳng hạn chỉ chạy `fast` nhưng tất cả test hiện có gắn tag `slow`.
9. **`@Disabled`/điều kiện execution:** engine phát hiện nhưng đánh dấu skip.
10. **Class lồng nhau:** Surefire mặc định exclude `**/*$*` khi scan class files; xem mục 12 về JUnit `@Nested` để tránh kết luận sai.
11. **Nhầm Surefire với Failsafe:** tên `OrderIT` thuộc quy ước integration test, không mặc nhiên thuộc Surefire unit tests.
12. **Đang ở nhầm module:** lệnh Maven từ root reactor và `-pl` chọn một module khác với module chứa test.
13. **Lifecycle/test goal không chạy:** `skipTests`, profile, plugin executions, packaging khác hoặc CI gọi `compile` thay vì `test`.
14. **Bài test hiện có trong source nhưng bị stale output:** chưa chạy `clean` sau khi rename và compiler output còn tệp `.class` cũ.
15. **Provider/JDK/module path bất tương thích:** với Java 9+ JPMS, test runtime có thể gặp vấn đề module visibility/engine; lỗi này khác thuần naming.

Nhiều nguyên nhân không làm compiler báo sai, vì **tệp test là Java source hợp lệ**. Đó là lý do CI phải kiểm **số test thật chạy**, chứ không chỉ nhìn trạng thái Maven.

## 7. Ví dụ Maven và Java 17 hoàn chỉnh: 2 test được chọn, 1 test bị bỏ qua theo tên

Tạo một Maven project đơn module có hai lớp test JUnit Jupiter:

- `CalculatorTest`: có **2 test methods**; được Surefire chọn theo mặc định.
- `CalculatorSpec`: có **1 test method**; hợp lệ với JUnit Jupiter nhưng tên **không khớp quy tắc Surefire mặc định**.

Nhờ thiết kế này, cùng một lần `mvn clean test` sẽ giúp phân biệt **test được biên dịch** và **test được chạy**.

Cấu trúc:

~~~text
surefire-naming-demo/
├── pom.xml
└── src/
    ├── main/java/org/example/math/Calculator.java
    └── test/java/org/example/math/
        ├── CalculatorTest.java
        └── CalculatorSpec.java
~~~

Môi trường: JDK 17+, Maven 3.9.x hoặc phiên bản tương thích, và repository có thể cung cấp Maven plugins/JUnit artifacts nếu chưa cache. Dự án không yêu cầu một server/database bên ngoài.

### 7.1. pom.xml đầy đủ

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>org.example.training</groupId>
    <artifactId>surefire-naming-demo</artifactId>
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
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.2</version>
                <configuration>
                    <!-- Guard against a successful build with no tests. -->
                    <failIfNoTests>true</failIfNoTests>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**Quan trọng về guard:** Trong POM mẫu đã bật `<failIfNoTests>true</failIfNoTests>`. Đây là một sự lựa chọn **chủ động** cho module bắt buộc có unit tests, **không phải default của Surefire**. Mặc định, tham số `failIfNoTests` là `false` (xem mục 10). Việc bật guard giúp thí nghiệm “không có test nào được chọn” thất bại có chủ đích thay vì âm thầm báo BUILD SUCCESS.

`junit-jupiter` nằm ở **project test scope**; `maven-surefire-plugin` nằm ở `build/plugins`. Đây là hai vai trò khác nhau.

### 7.2. src/main/java/org/example/math/Calculator.java

~~~java
package org.example.math;

public final class Calculator {
    private Calculator() {
    }

    public static int add(int a, int b) {
        return a + b;
    }
}
~~~

Đây là class Java độc lập, không dùng thư viện ngoài JDK. Tên package, tên class và đường dẫn file đúng theo quy ước Java.

### 7.3. src/test/java/org/example/math/CalculatorTest.java

~~~java
package org.example.math;

import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class CalculatorTest {
    @Test
    void addsPositiveNumbers() {
        assertEquals(5, Calculator.add(2, 3));
    }

    @Test
    void supportsNegativeNumbers() {
        assertEquals(-2, Calculator.add(-5, 3));
    }
}
~~~

`CalculatorTest` là một **package-private class**, vẫn hợp lệ với JUnit Jupiter; JUnit 5 không yêu cầu mọi test class/method đều phải `public`. Nó có đúng **2 methods gắn `@Test`**. Tên class kết thúc bằng `Test`, khớp `**/*Test.java` của Surefire.

### 7.4. src/test/java/org/example/math/CalculatorSpec.java

~~~java
package org.example.math;

import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class CalculatorSpec {
    @Test
    void additionIsReversibleWithOppositeNumber() {
        assertEquals(0, Calculator.add(9, -9));
    }
}
~~~

Mã ở đây cũng là **JUnit Jupiter test hợp lệ** và được test compiler biên dịch. Tuy nhiên, `CalculatorSpec` **không** khớp pattern tên mặc định của Surefire. Khi chạy thông thường, lớp đó **không tự được chọn**; đây là lỗi naming mà bài muốn minh họa.

### 7.5. Chạy bài và đọc kết quả

Từ thư mục chứa `pom.xml`:

~~~bash
mvn -B -ntp clean test
~~~

Theo thiết kế của ba tệp Java và cấu hình POM trên, nếu không có thêm test khác/filter khác:

- `Calculator.java` biên dịch vào `target/classes`.
- **Cả hai** lớp `CalculatorTest` và `CalculatorSpec` được test compiler biên dịch vào `target/test-classes`.
- Surefire mặc định chọn `CalculatorTest`.
- JUnit Jupiter chạy **2 test methods** của `CalculatorTest`.
- Method trong `CalculatorSpec` **không chạy** khi không có custom include/`-Dtest`.

Một **đoạn tóm tắt kết quả minh họa** trong log Surefire:

~~~text
Running org.example.math.CalculatorTest
Tests run: 2, Failures: 0, Errors: 0, Skipped: 0
~~~

Đây là ví dụ rút gọn **nội dung thống kê**, không khẳng định log Maven có đúng hai dòng không tiền tố; Surefire có thể chèn `[INFO]`, thời gian và dòng báo cáo khác. Kết quả **số test theo source mẫu = 2** khi không có thay đổi nào khác.

Đường dẫn báo cáo thông thường:

~~~text
target/
├── classes/org/example/math/Calculator.class
├── test-classes/org/example/math/CalculatorTest.class
├── test-classes/org/example/math/CalculatorSpec.class
└── surefire-reports/
    ├── TEST-org.example.math.CalculatorTest.xml
    └── org.example.math.CalculatorTest.txt
~~~

Cây được rút gọn, có thể có file Maven metadata hoặc report khác. Điểm khác biệt cần quan sát: có `CalculatorSpec.class` trong `test-classes` **không có nghĩa** nó có một report/test case được chạy. Báo cáo XML theo test class đã chạy/engine cung cấp mới là bằng chứng tốt hơn.

## 8. Chạy tường minh lớp không khớp tên bằng -Dtest

Surefire cho phép chọn một test class bằng user property `test`, không cần sửa ngay quy tắc mặc định trong POM:

~~~bash
mvn -B -ntp -Dtest=CalculatorSpec test
~~~

Trong ví dụ, vì lớp `CalculatorSpec` đã được biên dịch và có `@Test` hợp lệ, lệnh chọn riêng này chạy **1 test method**:

~~~text
Running org.example.math.CalculatorSpec
Tests run: 1, Failures: 0, Errors: 0, Skipped: 0
~~~

Đây vẫn là **đoạn báo cáo rút gọn**, không phải stdout nguyên văn chắc chắn của Maven. Lệnh `-Dtest=CalculatorSpec` chứng minh rằng **JUnit test không bị lỗi**, chỉ đơn giản **không được Surefire quét tự động theo pattern mặc định**.

Chạy riêng method theo syntax được Surefire/JUnit Platform hỗ trợ:

~~~bash
mvn -B -ntp "-Dtest=CalculatorTest#addsPositiveNumbers" test
~~~

Với một method trên, chỉ **1 test method** được chọn trong tình huống mẫu. Dấu `#` có thể cần quote ở một số shell; dạng có quote giúp giảm rủi ro shell xử lý ký tự đặc biệt.

**Cẩn trọng:** Chạy `-Dtest` trong local IDE/terminal **không sửa được CI đang chạy `mvn test` không có `-Dtest`**. Đây là một công cụ chẩn đoán/chạy có chủ đích; lâu dài nên đặt tên đúng chuẩn hoặc cấu hình includes chung.

## 9. Sửa lâu dài: đổi tên lớp hoặc cấu hình includes

Có hai cách phổ biến để Surefire tự chạy lớp `CalculatorSpec` trong `mvn test`.

### 9.1. Cách ưu tiên: đổi tên lớp đúng quy ước

Đổi:

~~~text
src/test/java/org/example/math/CalculatorSpec.java
~~~

thành:

~~~text
src/test/java/org/example/math/CalculatorSpecTest.java
~~~

và đổi declaration:

~~~java
class CalculatorSpecTest {
    @Test
    void additionIsReversibleWithOppositeNumber() {
        org.junit.jupiter.api.Assertions.assertEquals(0, Calculator.add(9, -9));
    }
}
~~~

Đoạn Java vừa rồi chỉ thay thế **nội dung class test sau khi đổi tên**, không phải file mới thêm song song với `CalculatorSpec.java`. Hãy xóa/rename file cũ đúng cách; tránh để **hai class cùng thực hiện một test** nếu mục đích chỉ là đổi tên.

Sau đó chạy:

~~~bash
mvn -B -ntp clean test
~~~

Nếu project chỉ có các source trong bài, kết quả dự kiến:

~~~text
CalculatorTest:      2 test methods
CalculatorSpecTest:  1 test method
TOTAL:               3 tests
~~~

Đây là tóm tắt **số test tính từ mã mẫu**, không phải log nguyên văn. Lớp đổi tên khớp `**/*Test.java`. Dùng `clean` để loại `CalculatorSpec.class` cũ và tránh nhiễu khi thử nghiệm.

**Ưu điểm:** không cần cấu hình Surefire đặc biệt, code review dễ đọc, đúng convention của nhiều dự án Java.

### 9.2. Khi tổ chức dùng tên *Spec: thêm includes

Nếu tên `CalculatorSpec` được quy định vì phong cách kiểm thử của nhóm, có thể cấu hình Surefire:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-surefire-plugin</artifactId>
    <version>3.5.2</version>
    <configuration>
        <failIfNoTests>true</failIfNoTests>
        <includes>
            <include>**/Test*.java</include>
            <include>**/*Test.java</include>
            <include>**/*Tests.java</include>
            <include>**/*TestCase.java</include>
            <include>**/*Spec.java</include>
        </includes>
    </configuration>
</plugin>
~~~

Đây là **mảnh cấu hình plugin**, dùng để **thay thế/cập nhật phần Surefire plugin** trong POM hiện có. **Không** đặt thêm một plugin Surefire thứ hai cùng loại nếu chỉ muốn đổi includes.

Khi `<includes>` được cấu hình, các rule được cấu hình sẽ điều khiển bộ lớp Surefire chọn. Vì vậy mẫu trên **giữ nguyên bốn pattern mặc định và thêm `**/*Spec.java`**. Nếu chỉ đặt `**/*Spec.java`, những lớp `CalculatorTest` hoặc `TestCalculator` có thể không còn nằm trong danh sách được chọn như trước.

Với POM mẫu ban đầu chưa rename class, sau khi thay plugin configuration bằng đoạn trên, `mvn clean test` có thể chọn cả `CalculatorTest` và `CalculatorSpec`, chạy tổng cộng **3 tests**.

**Cảnh báo:** Đừng bật pattern quá rộng `**/*.java` hoặc `**/*.*` chỉ để “chạy hết”. Điều đó có thể khiến Surefire đưa các helper/abstract classes/utility classes vào vòng scan, làm log khó đọc hoặc gây hành vi provider không mong muốn. Một quy ước rõ ràng dễ kiểm toán hơn.

## 10. Guard quan trọng: failIfNoTests và failIfNoSpecifiedTests

Một trong những nguồn gây “bảo đảm giả” lớn nhất là **default của `failIfNoTests`**.

Trong Surefire:

| Tham số | Mặc định theo tài liệu Surefire | Ý nghĩa |
| --- | --- | --- |
| `failIfNoTests` | `false` | Khi **không có test nào để chạy** trong lượt Surefire, build thường **không thất bại chỉ vì 0 tests**. |
| `failIfNoSpecifiedTests` | `true` | Khi người dùng **chỉ định test bằng `-Dtest=...`** mà không có test phù hợp được chạy, build **thất bại** theo mặc định. |

Nguồn: [Maven Surefire Plugin — surefire:test parameters](https://maven.apache.org/surefire/maven-surefire-plugin/test-mojo.html).

**Ví dụ mặc định dễ gây bất ngờ:**

~~~text
Project có test source: CalculatorSpec.java
Surefire không có custom includes và không có -Dtest
  --> Không tìm được test class theo tên mặc định
  --> 0 tests
  --> failIfNoTests mặc định false
  --> Maven có thể BUILD SUCCESS
~~~

Ngược lại:

~~~bash
mvn -B -ntp -Dtest=MissingCalculatorTest test
~~~

Nếu không có lớp phù hợp, Surefire mặc định `failIfNoSpecifiedTests=true` nên đây thường là **lỗi build có chủ đích**. Nó không chứng minh rằng mọi lượt `mvn test` không chỉ định `-Dtest` cũng sẽ fail nếu 0 tests.

### Bật bảo vệ tại module bắt buộc có test

Trong `maven-surefire-plugin`:

~~~xml
<configuration>
    <failIfNoTests>true</failIfNoTests>
</configuration>
~~~

Khi project không chọn được test nào cho một lượt Surefire, build sẽ thất bại thay vì âm thầm vượt qua. Có thể truyền user property được plugin hỗ trợ:

~~~bash
mvn -B -ntp -DfailIfNoTests=true clean test
~~~

Lưu ý: nếu POM có `<configuration>` tường minh, khả năng CLI override một tham số phụ thuộc Maven parameter binding/configuration merge. Để chính sách CI dễ đọc, **đặt rõ `<failIfNoTests>true</failIfNoTests>` trong plugin config của module cần guard** và kiểm tra effective POM.

**Giới hạn của guard:** Nó kiểm tình huống **không có tests chạy được** theo semantics của Surefire, nhưng không bảo đảm mỗi file test dự kiến đều được chọn, hoặc test suite có đủ coverage. Trong ví dụ, `CalculatorTest` đã chạy 2 methods, nên `failIfNoTests=true` **không phát hiện việc `CalculatorSpec` bị bỏ sót**. CI có thể cần kiểm tra tối thiểu số test/report hoặc kiểm kê naming ở source.

### Thí nghiệm 0 tests an toàn

Trong **một bản sao** của dự án ví dụ ở mục 7, đổi **cả tên file và tên class**:

~~~text
CalculatorTest.java --> CalculatorCheck.java
class CalculatorTest --> class CalculatorCheck
~~~

Giữ `CalculatorSpec.java`. Sau đó chạy:

~~~bash
mvn -B -ntp clean test
~~~

Bây giờ **cả hai** test classes (`CalculatorCheck` và `CalculatorSpec`) không khớp bốn pattern mặc định. Với `failIfNoTests=true` đã cấu hình, lệnh phải được Surefire **đánh dấu thất bại do không có tests để chạy** trong điều kiện không bị skip/profile override.

Không chỉ đổi **tên file** mà quên tên class: với Java package-private class, compiler có thể vẫn tạo `CalculatorTest.class` và Surefire vẫn nhận tên cũ. Phải đổi tên class, rồi dùng `clean` để không còn `.class` cũ. Sau thí nghiệm, khôi phục file/class gốc để giữ ví dụ runnable.

## 11. Chọn tests bằng CLI -Dtest: khác chọn mặc định

Tùy chọn `-Dtest` hữu ích cho chạy test có mục tiêu:

~~~bash
mvn -B -ntp -Dtest=CalculatorTest test
mvn -B -ntp -Dtest=CalculatorSpec test
mvn -B -ntp "-Dtest=CalculatorTest#addsPositiveNumbers" test
~~~

Ý nghĩa:

- `CalculatorTest`: chạy class có tên đó.
- `CalculatorSpec`: chọn tường minh một class không thuộc default naming.
- `CalculatorTest#addsPositiveNumbers`: chọn một method cụ thể (với Surefire/JUnit Platform hỗ trợ).

Có thể dùng wildcard hoặc pattern theo cú pháp plugin:

~~~bash
mvn -B -ntp "-Dtest=*Test" test
~~~

**Khác biệt:** `-Dtest` là **bộ lọc chọn test cho lượt chạy hiện tại**; nó có thể override các includes mặc định. Khi không có class/method phù hợp, `failIfNoSpecifiedTests` thường làm fail.

Không nên dùng `-Dtest=CalculatorTest` cố định trong CI tổng thể vì nó **chỉ chạy lớp đã chỉ định** và có thể bỏ qua những test class mới. Nếu chỉ cần smoke tests, cấu hình một job khác rồi giữ một job chạy suite đầy đủ.

Trên một Maven reactor nhiều module, `-Dtest=ClassName` có thể khiến **một module không có lớp tương ứng** thất bại vì `failIfNoSpecifiedTests` áp dụng khi Surefire thực thi ở module đó. Phải cân nhắc `-pl` hoặc cách cấu hình `failIfNoSpecifiedTests` theo mục tiêu; không vô hiệu hóa cờ một cách toàn cục khi chưa hiểu hệ quả.

## 12. Excludes và nested classes: các sắc thái quan trọng

Surefire mặc định còn có một pattern loại trừ cho inner classes:

~~~text
**/*$*
~~~

Dạng `$` thường xuất hiện trong tên file `.class` của **nested/member classes**, ví dụ:

~~~text
CalculatorTest.class
CalculatorTest$NestedCases.class
~~~

Theo tài liệu Surefire, lớp lồng nhau **không được quét như một test class độc lập** theo default excludes. Điều này có ích để tránh quét các helper/inner classes trùng lặp.

**Nhưng với JUnit Jupiter `@Nested` cần phân biệt rõ:** một `@Nested` class có thể được **JUnit Platform khám phá như test container bên trong enclosing test class đã được Surefire chọn**. Exclude `*$*` trong Surefire không có nghĩa tất cả Jupiter `@Nested` tests chắc chắn bị bỏ qua; chúng có thể chạy thông qua lớp bao ngoài.

Ví dụ minh họa:

~~~java
package org.example.math;

import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class OuterTest {
    @Nested
    class InnerCases {
        @Test
        void nestedTestIsDiscoveredThroughOuter() {
            assertEquals(2, 1 + 1);
        }
    }
}
~~~

Đây là một **test class riêng** `OuterTest.java`, không phải phần bổ sung vào project Calculator ở mục 7 nếu muốn giữ số test dự kiến = 2. `OuterTest` khớp `*Test` và JUnit Jupiter có thể phát hiện `InnerCases` qua enclosing test class.

**Custom excludes cũng có thể ẩn test hợp lệ:**

~~~xml
<configuration>
    <excludes>
        <exclude>**/*SlowTest.java</exclude>
        <exclude>**/experimental/**</exclude>
    </excludes>
</configuration>
~~~

Đây là **mảnh Surefire configuration**. Với cách này, `CustomerSlowTest` có thể bị loại dù tên khớp default include. Nếu tổ chức dùng các excludes cố định, nên review định kỳ để tránh “tạm bỏ test khó” thành bỏ vĩnh viễn.

Đừng xóa default nested exclusion chỉ để sửa một `CalculatorSpec` không chạy; đó là hai vấn đề khác nhau.

## 13. Includes/excludes theo đường dẫn và regex: tránh đọc sai pattern

Những pattern như:

~~~text
**/Test*.java
**/*Test.java
**/*Tests.java
**/*TestCase.java
**/*Spec.java
~~~

là **Ant-style patterns** mà Surefire diễn giải trên lớp đã biên dịch (dù pattern viết đuôi `.java`). Chúng phù hợp với việc biểu diễn package/subdirectory bằng dấu `/`.

Surefire còn hỗ trợ regex theo cú pháp:

~~~text
%regex[.*Spec.*]
~~~

**Cẩn trọng với regex:** Surefire regex matching là trên **đường dẫn `.class`**, dùng dấu slash `/` và thường cần hiểu đúng biểu thức so khớp đầy đủ, không đơn giản là pattern source filename như trên. Một biểu thức `.*Spec.*` có thể vô tình chọn nhiều class có `Spec` ở giữa tên hoặc đường dẫn, nên khi chỉ muốn đuôi `Spec`, dùng **Ant-style `**/*Spec.java`** trong ví dụ đào tạo sẽ rõ hơn.

Có thể khai báo full package/class name patterns theo cú pháp Surefire version hỗ trợ, nhưng không nên trộn regex và Ant-glob một cách máy móc. Hãy đọc mục [Inclusions and Exclusions](https://maven.apache.org/surefire/maven-surefire-plugin/examples/inclusion-exclusion.html) và kiểm tra actual test count sau thay đổi.

Các trường hợp nên đặc biệt thận trọng:

- **Chữ hoa/thường:** `CalculatorTest` khác `Calculatortest`.
- **Package path:** `org/example/math/` khác tên dotted `org.example.math` trong regex path matching.
- **Extension:** Surefire cú pháp `.java` trong Ant-style include được plugin xử lý để khớp output class; regex dùng `.class`.
- **Inner class `$`:** có default exclusion.
- **Test class compiled nhưng tên custom:** class vẫn có trong `target/test-classes` nhưng không được chọn.
- **Custom includes thay default:** muốn giữ bốn mặc định, liệt kê chúng cùng custom rule.

## 14. Surefire và Failsafe có quy ước tên khác nhau

Maven Surefire Plugin thường phục vụ **unit tests** ở phase `test`. Maven Failsafe Plugin thường phục vụ **integration tests** với các goals như `integration-test` và `verify` khi plugin/executions được cấu hình đúng.

Theo tài liệu Maven Failsafe, các pattern mặc định thường là:

| Plugin | Pattern mặc định |
| --- | --- |
| **Surefire** | `**/Test*.java`, `**/*Test.java`, `**/*Tests.java`, `**/*TestCase.java` |
| **Failsafe** | `**/IT*.java`, `**/*IT.java`, `**/*ITCase.java` |

Tình huống thường gặp:

~~~text
src/test/java/org/example/OrderServiceTest.java  --> Surefire
src/test/java/org/example/OrderServiceIT.java    --> Failsafe (nếu được bind)
src/test/java/org/example/OrderServiceSpec.java  --> Không mặc định theo hai nhóm trên
~~~

**Lưu ý:** Chỉ đặt tên `OrderServiceIT` **không tự làm Failsafe chạy**. Nếu project không cấu hình plugin/executions, gọi `mvn verify` thường không chạy integration tests qua Failsafe. Tương tự, Failsafe có config include/exclude riêng; sửa Surefire includes không tự điều chỉnh Failsafe.

Đoạn POM **minh họa riêng** để bind Failsafe vào lifecycle:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-failsafe-plugin</artifactId>
    <version>3.5.2</version>
    <executions>
        <execution>
            <goals>
                <goal>integration-test</goal>
                <goal>verify</goal>
            </goals>
        </execution>
    </executions>
</plugin>
~~~

Đây là **mảnh `build/plugins`**, không phải yêu cầu thêm vào POM ví dụ Calculator. Với hệ thống tích hợp thật, cần chuẩn bị môi trường integration test và kiểm soát dữ liệu/cleanup, không chỉ đổi suffix.

Nếu `OrderServiceIT` bị Surefire bỏ qua nhưng Failsafe chưa được bind, **không có plugin nào chạy test đó**. Đây là lỗ hổng cấu hình rất thường gặp khi nhóm chuyển unit test sang integration test.

## 15. Cách xem Surefire Reports để biết điều gì đã thực sự chạy

Sau khi chạy:

~~~bash
mvn -B -ntp clean test
~~~

hãy xem thư mục:

~~~text
target/surefire-reports/
    TEST-org.example.math.CalculatorTest.xml
    org.example.math.CalculatorTest.txt
~~~

Tên file phụ thuộc test class/engine và configuration. Có thể có thêm report files hoặc output với định dạng khác nếu plugin được tùy chỉnh.

Tệp XML thông thường có cấu trúc tương tự:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<testsuite name="org.example.math.CalculatorTest"
           tests="2" errors="0" skipped="0" failures="0"
           time="0.001">
    <!-- Nội dung testcase và properties được lược bỏ trong minh họa -->
</testsuite>
~~~

Đây là **mảnh XML minh họa**, không phải report nguyên văn của run thật (thời gian và metadata thay đổi). Khi review reports, nên đọc:

- **`tests`**: số test cases theo report.
- **`failures`** và **`errors`**: các ca fail.
- **`skipped`**: các ca không chạy vì skip/disabled.
- Những test class nào **có report**, và class nào có `.class` nhưng **không có report**.
- Lỗi provider, forked JVM và test engine nếu suite không chạy.

Không nên suy rằng “file report mới được tạo” tức là mọi test dự kiến đều chạy; chỉ các lớp được chọn/được engine xử lý mới thường có report. Với parallel/test retries, số lượng/report layout có thể thay đổi theo phiên bản.

**CI kiểm chứng được:** sau full test, tổng số tests thực chạy (`tests - skipped` theo semantics report phù hợp) nên vượt một mức hợp lý, và các suite quan trọng phải có report. `failIfNoTests=true` là lớp bảo vệ đầu tiên, **không phải** bằng chứng về đầy đủ test coverage.

## 16. Cấu hình CI để không âm thầm chấp nhận 0 tests

Một pipeline chất lượng cần làm rõ: **module này có bắt buộc có unit tests không?**

Nếu **có**, đặt:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-surefire-plugin</artifactId>
    <version>3.5.2</version>
    <configuration>
        <failIfNoTests>true</failIfNoTests>
    </configuration>
</plugin>
~~~

và chạy:

~~~bash
mvn -B -ntp clean verify
~~~

Lệnh `verify` theo lifecycle JAR thông thường đi qua `test` và cho Surefire cơ hội chạy. Tuy nhiên, nếu có `skipTests`, `maven.test.skip`, profile override hoặc plugin execution đặc biệt, cần kiểm tra log/effective POM thay vì tin chỉ vào tên goal.

**Một ví dụ GitHub Actions sử dụng Maven Wrapper nếu repository đã có `mvnw`:**

~~~yaml
name: Java unit tests
on:
  push:
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'
      - name: Test with Surefire
        run: ./mvnw -B -ntp clean verify
~~~

Đây là **mảnh cấu hình CI** dùng khi repository thực sự có Maven Wrapper; **project mẫu ở mục 7 không tự cung cấp `mvnw`**. Với repository không có Wrapper, CI nên cài Maven version được nhóm quản lý rồi dùng `mvn`. Một build không có tests được chọn sẽ fail do POM mẫu đã bật `failIfNoTests`.

Để tăng độ tin cậy, CI có thể:

1. Xuất bản `target/surefire-reports` làm artifact sau job.
2. Kiểm tra số test thật chạy theo module, không chỉ status code của `mvn`.
3. Đặt minimum test count cho các module bắt buộc có tests nếu pipeline/tooling hỗ trợ.
4. Chạy thêm coverage check (ví dụ JaCoCo) phù hợp mục tiêu; 2 test chạy không có nghĩa đạt coverage.
5. Chạy Failsafe riêng nếu có integration tests, thay vì trông chờ Surefire bắt tên `*IT`.
6. Đảm bảo không có flags skip được bật ngoài ý muốn.
7. Review naming convention trong pull request.
8. Lưu full test report của các module chính, không chỉ một report từ root aggregator.

Không đặt quá nhiều lớp guard vào ví dụ học tập rồi cho rằng mọi dự án phải giống hệt: một module chỉ chứa model/codegen/BOM **có thể hợp lệ khi không có unit test**, và cần cấu hình chính sách theo mục đích module.

## 17. Multi-module reactor: nơi “0 tests” còn khó phát hiện hơn

Với Maven reactor:

~~~text
root/pom.xml
├── domain/pom.xml
│   └── src/test/java/.../DomainTest.java
├── api/pom.xml
│   └── src/test/java/.../ApiSpec.java
└── cli/pom.xml
    └── src/test/java/.../CliTest.java
~~~

Giả sử mỗi child packaging JAR, parent packaging POM:

- `domain` có `DomainTest` → Surefire chạy khi được bind.
- `api` có `ApiSpec` → có thể **0 tests** theo naming default.
- `cli` có `CliTest` → Surefire chạy.
- Root parent packaging POM không có test source theo design; **không nên coi root không có test là lỗi khi nó không thực thi Surefire**.

Nếu chỉ nhìn build tổng thể, bạn có thể thấy một số suite chạy và `BUILD SUCCESS` nhưng **module API không chạy gì**. Cần xem **reports theo module**:

~~~text
domain/target/surefire-reports/
api/target/surefire-reports/
cli/target/surefire-reports/
~~~

Đặt `failIfNoTests=true` cho module `api` nếu mọi PR bắt buộc có unit tests; nhưng nếu một module khác không có tests theo kiến trúc, nên giới hạn guard trong module cần thay vì áp đặt bừa bãi khiến parent/utility module fail.

Các lệnh chọn Maven module:

~~~bash
mvn -pl :api -am test
mvn -pl :api test
~~~

Chúng cần reactor thật có artifactId `api` và có thể đòi các module upstream được build/cài. `-pl` chọn **Maven projects**, không phải chọn test classes. `-Dtest=ApiSpec` chọn **lớp test** trong Surefire; hai option phục vụ hai lớp lựa chọn khác nhau.

Khi chạy `-Dtest=SomeClass` trên toàn reactor, module không chứa class đó có thể bị fail do `failIfNoSpecifiedTests=true`, dù build bình thường không có vấn đề naming. Hãy phân biệt **cấu hình scan mặc định**, **chọn một test có mục tiêu** và **lựa chọn Maven modules**.

## 18. Skip flags: test không chạy vì naming hay vì bị bỏ qua có chủ đích?

Các cờ Maven thông dụng liên quan test:

| Cờ/config | Hành vi thường gặp | Rủi ro khi đọc kết quả |
| --- | --- | --- |
| `-DskipTests` hoặc Surefire `skipTests=true` | Bỏ bước **chạy test**, nhưng test source có thể vẫn được compile. | BUILD SUCCESS mà không test; không phải lỗi naming. |
| `-Dmaven.test.skip=true` | Bỏ cả **test compilation và test execution** đối với plugins tôn trọng property. | Không có output mới, không suy từ test classes cũ. |
| `-Dtest=CalculatorTest` | Chọn riêng một test class. | Các lớp khác không chạy vì **filter explicit**, không vì lỗi naming. |
| `-DfailIfNoTests=true` | Yêu cầu Surefire fail khi không có test để chạy, nếu plugin thực sự được thực thi. | Không bảo đảm tất cả test source đều được chọn. |
| `-Dsurefire.failIfNoSpecifiedTests=false` | Cho phép không tìm thấy test theo bộ lọc `-Dtest`. | Có thể che lỗi đánh sai tên class/typo; tránh bật tùy tiện. |

Các thuộc tính và hành vi phải được đối chiếu với phiên bản Surefire/Failsafe cụ thể; trong dự án có profile/plugin inheritance, effective configuration mới là thứ plugin nhận.

Nếu log có `Tests are skipped.`, đừng quy tất cả lỗi về `*Test` pattern. Kiểm tra CLI flags, POM properties, profile, CI environment và Maven Help Plugin `effective-pom`.

**Đối với CI:** không sử dụng `-DskipTests` ở job bắt buộc xác minh test. Có thể có job packaging nhanh cố tình skip tests, nhưng cần một job khác đã chứng minh tests được thực thi.

## 19. Bảng chẩn đoán nhanh

| Hiện tượng | Khả năng cao | Cách kiểm tra |
| --- | --- | --- |
| Class `CalculatorSpec` có `@Test`, không có trong Surefire reports. | Không khớp mặc định. | Chạy `-Dtest=CalculatorSpec`; đổi thành `CalculatorSpecTest` hoặc thêm include. |
| `mvn test` BUILD SUCCESS nhưng không thấy test report. | `failIfNoTests` mặc định false hoặc plugin bị skip/không chạy. | Xem Surefire log, test source layout, naming, flags và effective POM. |
| `-Dtest=MissingTest` làm fail nhưng `mvn test` bình thường không fail. | `failIfNoSpecifiedTests` default true, `failIfNoTests` default false. | Kiểm tra hai tham số đúng trong Surefire docs. |
| Class tên `CalculatorTest` được chọn nhưng Tests run 0. | Không có test descriptor hợp lệ, engine mismatch/filter. | Kiểm `@Test`, JUnit Jupiter engine, tags, disabled, provider. |
| Java compiler biên dịch `CalculatorSpec.java` nhưng Surefire không chạy. | Test compile và test execution là hai phase khác nhau. | So `target/test-classes` với `surefire-reports`. |
| Rename class test xong Surefire vẫn chạy lớp cũ. | `target/test-classes` còn stale `.class`. | Chạy `mvn clean test`. |
| `OrderIT` không chạy bởi `mvn test`. | Surefire naming không bao gồm `*IT`. | Cấu hình Failsafe hoặc custom Surefire include theo chủ đích. |
| `mvn verify` không chạy `OrderIT`. | Failsafe chưa được bind hoặc profile inactive. | Xem `build/plugins/executions` và Failsafe reports. |
| Test JUnit 5 compile được nhưng không chạy. | TestEngine không có/không chọn đúng hoặc plugin cũ. | Dùng `junit-jupiter` + Surefire phiên bản hỗ trợ, xem logs. |
| Một test có `@Disabled`, suite báo skipped. | JUnit engine chủ động skip. | Xem report `skipped`, điều kiện tag/annotation. |
| Bật custom includes thì test cũ biến mất. | Rule mới thay danh sách mặc định. | Giữ 4 defaults nếu muốn thêm `*Spec`. |
| Lớp nested được JUnit `@Nested` chạy dù Surefire exclude `$`. | JUnit phát hiện nested container qua outer class. | Xem outer class name và JUnit report; không đồng nhất hai tầng discovery. |
| Chỉ module `api` có zero tests trong reactor. | Tên test của module đó sai hoặc module-specific config. | Kiểm reports từng module và `-pl :api`. |
| Build chạy test nhưng coverage quá thấp. | Test selection chỉ là một điều kiện cần. | Bổ sung coverage thresholds/review, không chỉ `failIfNoTests`. |
| `-Dtest=CalculatorTest` trên root làm fail module khác. | Explicit test filter không có class khớp ở mọi module. | Dùng `-pl` hoặc điều chỉnh cấu hình theo mục đích. |
| Test method tên `testSomething` nhưng không có `@Test` trong JUnit Jupiter. | JUnit Jupiter không suy mọi method chỉ từ tiền tố. | Thêm annotation tương ứng; đừng nhầm quy ước JUnit 3/4. |

**Đường chẩn đoán:** bắt đầu từ **phase nào chạy** → **test source có biên dịch không** → **test class có khớp pattern không** → **engine có nhận test methods không** → **có filter/skip không** → **report có thực sự có test cases không**. Đọc log và report **của đúng module** để tránh kết luận từ output của một module khác.

## 20. Checklist code review và CI

- [ ] Unit test source nằm trong `src/test/java` (hoặc source root test được cấu hình rõ).
- [ ] Tên các lớp unit test khớp `Test*`, `*Test`, `*Tests` hoặc `*TestCase`; nếu tổ chức dùng `*Spec` thì Surefire includes được khai báo rõ.
- [ ] Class test có **test methods hợp lệ** với đúng framework và engine, không chỉ có tên kết thúc `Test`.
- [ ] JUnit Jupiter API/engine được khai báo ở project scope test, dùng Surefire version hỗ trợ.
- [ ] Surefire plugin version được pin trong POM/parent, không phụ thuộc Maven default không kiểm soát.
- [ ] Custom includes **không vô tình bỏ mất** bốn quy tắc mặc định mà project vẫn dùng.
- [ ] Custom excludes, tags và disabled conditions được xem xét; không che test quan trọng.
- [ ] `failIfNoTests=true` ở module bắt buộc có tests, có ngoại lệ có chủ đích cho module không cần test.
- [ ] CI không bật `skipTests`/`maven.test.skip` trong job xác minh.
- [ ] Đã chạy `mvn clean test` hoặc `clean verify` sau rename để loại stale class files.
- [ ] Test report có số test thực sự được chạy; kiểm tra `tests`, `skipped`, `errors`, `failures`.
- [ ] Không dùng `-Dtest` cố định trong job full suite và tưởng mọi test đều chạy.
- [ ] Integration tests theo `IT*`/`*IT`/`*ITCase` có Failsafe execution phù hợp nếu sử dụng.
- [ ] Mỗi module trong reactor có report/guard phù hợp với vai trò của nó.
- [ ] Có coverage hoặc quy tắc kiểm kê test suite bổ sung nếu rủi ro bỏ sót một file là cao.
- [ ] Build log/checksum/report được lưu theo chính sách CI để có thể truy vết kết quả thực.

## 21. Câu hỏi tự kiểm tra

1. **Một class tên `PaymentSpec` có `@Test` và biên dịch thành công, Maven Surefire mặc định có chạy không?**  
   Không phải chỉ vì `@Test`. `PaymentSpec` không khớp bốn include patterns mặc định. Cần đổi tên, cấu hình includes hoặc chọn tường minh.

2. **Bốn tên lớp nào là ví dụ hợp lệ theo default?**  
   `TestPayment`, `PaymentTest`, `PaymentTests`, `PaymentTestCase`.

3. **Tại sao `PaymentTest` có thể được quét nhưng không có test method nào chạy?**  
   Vì JUnit/TestEngine còn phải nhận test descriptor, annotation, provider và filter hợp lệ.

4. **`failIfNoTests` mặc định là gì?**  
   `false`. Nếu Surefire không có tests để chạy, build có thể thành công.

5. **`failIfNoSpecifiedTests` mặc định là gì?**  
   `true` khi đã chỉ định `-Dtest=...` mà không có test phù hợp chạy.

6. **Bật `failIfNoTests=true` có phát hiện riêng `CalculatorSpec` không chạy trong khi `CalculatorTest` vẫn chạy 2 tests không?**  
   Không. Nó không bảo đảm tất cả lớp test dự kiến đều chạy, chỉ giúp ngăn tình huống zero tests theo semantics plugin.

7. **Vì sao sau khi rename test cần chạy `mvn clean test`?**  
   Để bỏ compiled `.class` của lớp tên cũ khỏi `target/test-classes`, tránh chạy test “ma”.

8. **`CalculatorIT` mặc định được plugin nào tìm?**  
   Thường là Failsafe khi được cấu hình chạy integration tests; Surefire mặc định không có `*IT`.

9. **`@Nested` trong JUnit 5 có nhất định bị bỏ hết vì Surefire exclude `**/*$*` không?**  
   Không. JUnit có thể phát hiện nested tests thông qua enclosing test class đã được Surefire chọn.

10. **Dùng `-Dtest=CalculatorSpec` thành công có nghĩa `mvn test` không có filter sẽ tự chạy class đó không?**  
    Không. `-Dtest` chọn class cho lượt chạy hiện tại, không đổi default naming.

11. **Có nên đặt pattern `**/*.java` để “chắc chắn không sót test” không?**  
    Không nên. Nó quét quá rộng, không bảo đảm các class đó có test method và có thể làm provider chọn helper classes.

12. **Tại sao CI cần kiểm số test thực sự chạy thay vì chỉ BUILD SUCCESS?**  
    Vì naming, excludes, filters, skip flags hoặc engine có thể khiến build thành công dù suite rỗng hoặc thiếu nhiều test mong đợi.

## 22. Tài liệu tham khảo chính thức

- [Apache Maven Surefire Plugin — Inclusions and Exclusions of Tests](https://maven.apache.org/surefire/maven-surefire-plugin/examples/inclusion-exclusion.html) — bốn default includes, custom includes/excludes, Ant-style và regex.
- [Apache Maven Surefire Plugin — Using JUnit 5 Platform](https://maven.apache.org/surefire/maven-surefire-plugin/examples/junit-platform.html) — JUnit Jupiter/TestEngine, cách chọn class, nested classes và JUnit tags.
- [Apache Maven Surefire Plugin — surefire:test Parameters](https://maven.apache.org/surefire/maven-surefire-plugin/test-mojo.html) — `failIfNoTests`, `failIfNoSpecifiedTests`, `includes`, `excludes` và `test` property.
- [Apache Maven Surefire Plugin — Running a Single Test](https://maven.apache.org/surefire/maven-surefire-plugin/examples/single-test.html) — `-Dtest`, wildcard và chọn method.
- [Apache Maven Failsafe Plugin — Inclusions and Exclusions of Tests](https://maven.apache.org/surefire/maven-failsafe-plugin/examples/inclusion-exclusion.html) — `IT*`, `*IT`, `*ITCase`.
- [Apache Maven Failsafe Plugin — Usage](https://maven.apache.org/surefire/maven-failsafe-plugin/usage.html) — cách bind `integration-test` và `verify`.
- [Apache Maven Surefire Plugin — Examples](https://maven.apache.org/surefire/maven-surefire-plugin/examples/) — báo cáo, classpath, provider, JUnit Platform và filtering.
- [JUnit 5 User Guide — Writing Tests](https://docs.junit.org/5.11.4/user-guide/) — `@Test`, `@Disabled`, `@Nested`, test classes và test discovery.
- [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html) — `test-compile`, `test` và `verify` trong lifecycle.

**Kết luận:** Surefire mặc định quét các lớp có tên **`Test*`, `*Test`, `*Tests` hoặc `*TestCase`**. **Test code biên dịch được và có `@Test` không có nghĩa Surefire sẽ tự chạy nó.** Hãy đặt tên đúng convention hoặc khai báo includes rõ ràng, xác nhận JUnit engine nhận test methods, đọc `target/surefire-reports` và bật `failIfNoTests` ở module bắt buộc có tests. Trên CI, kiểm tra **số test thực chạy** để tránh một bản build “xanh” nhưng bộ kiểm thử không thực hiện nhiệm vụ.
