# Chọn lớp hoặc phương thức kiểm thử đơn vị bằng -Dtest trong Maven

## 1. Vì sao cần chọn một test thay vì luôn chạy toàn bộ?

Khi một dự án Java có nhiều lớp test, lệnh `mvn test` thông thường chạy tất cả các kiểm thử thuộc phạm vi Maven Surefire Plugin. Trong quá trình sửa một lỗi nhỏ, người lập trình thường muốn chạy một lớp `CalculatorTest`, hoặc thu hẹp hơn đến đúng phương thức `addsNumbers`, để biết sớm thay đổi của mình có tác dụng hay không.

Với Maven Surefire, cách làm trực tiếp là:

~~~bash
mvn "-Dtest=CalculatorTest" test
mvn "-Dtest=CalculatorTest#addsNumbers" test
~~~

Lệnh đầu chọn lớp; lệnh sau chọn một phương thức theo tên Java. Cả hai vẫn gọi Maven lifecycle phase `test`. Bộ lọc này ảnh hưởng **những test được Surefire thực thi**, không buộc Maven chỉ biên dịch đúng một file Java.

Bài học giải thích toàn bộ vòng đời của một lệnh `-Dtest`: cú pháp lớp và phương thức, cách chọn nhiều mục/pattern, đặc điểm JUnit 5, quoting trong Bash/PowerShell/CMD, đọc Surefire Reports, lỗi không tìm thấy test, sự khác nhau với skip flags, vấn đề multi-module và ranh giới với Failsafe integration tests.

### Bạn sẽ nắm được

1. Cú pháp `-Dtest=ClassName` và `-Dtest=ClassName#methodName`.
2. Vai trò của Surefire Plugin và sự khác biệt giữa `test` phase, `surefire:test` goal, Java class và JUnit method.
3. Cách dùng `*`, `?`, dấu phẩy và dấu `+` trong những tình huống được provider hỗ trợ.
4. Cách chạy đúng một lớp hoặc một method có tên đầy đủ gồm package.
5. Cách kiểm tra số `Tests run`, `Failures`, `Errors` và `Skipped`.
6. Cách xử lý `No tests matching pattern`, test compilation fail và các lệnh lọc bị skip.
7. Cách phối hợp `-Dtest` với reactor `-pl`/`-am` mà không che giấu việc test thực sự chưa chạy.
8. Quy tắc dùng selective testing trong development và full regression trong CI.

Bài chạy với Maven **3.9.x**, JDK **17+**, Maven Surefire Plugin **3.5.4**, JUnit Jupiter **5.11.4**. Các phiên bản được ghim để thực hành dễ tái hiện, không phải khẳng định chúng luôn là bản mới nhất.

## 2. Maven test lifecycle và Surefire làm việc ở giai đoạn nào?

Với packaging `jar` thông thường:

~~~text
src/main/java
     |
     v
compile        -> target/classes
     |
src/test/java
     |
     v
test-compile   -> target/test-classes
     |
     v
test           -> maven-surefire-plugin:test
                    |
                    +-- quét lớp test và chọn test phù hợp
                    +-- áp dụng -Dtest nếu có
                    +-- chạy bằng JUnit Platform/Jupiter
                    +-- ghi target/surefire-reports
~~~

Ba thứ khác nhau:

| Thành phần | Ý nghĩa |
| --- | --- |
| `mvn test` | Gọi Maven lifecycle phase `test`; Maven thực hiện các phase trước nó |
| `mvn surefire:test` | Gọi trực tiếp goal của Surefire; không mặc nhiên biên dịch source/test mới |
| `-Dtest=CalculatorTest` | Maven user property tên `test`, Surefire nhận làm tham số chọn test |

`-Dtest` không đổi tên class Java, không chỉnh sửa source, không thay `<scope>test</scope>` của dependency và cũng không phải Java JVM option để bật JUnit. Maven truyền property này tới goal Surefire.

### 2.1. Mặc định Surefire nhận diện những tên file nào?

Khi không cấu hình `includes`/`excludes` và không có `-Dtest`, Surefire có những pattern mặc định thường gặp:

~~~text
**/Test*.java
**/*Test.java
**/*Tests.java
**/*TestCase.java
~~~

Ví dụ `CalculatorTest.java`, `LabelTest.java`, `TestCalculator.java`, `AllMathTests.java` và `CalculatorTestCase.java` thường khớp. Một lớp tên `CalculatorChecks.java` không thuộc các pattern này chỉ vì có `@Test` bên trong. Bạn có thể đổi tên lớp theo quy ước hoặc cấu hình inclusion phù hợp.

Với `-Dtest`, Surefire dùng pattern mà bạn chỉ định để chọn test và ghi đè tham số `includes/excludes` thông thường cho lần lựa chọn đó. Không nên hiểu điều này là vô hiệu mọi quy tắc của JUnit Platform, ví dụ `@Disabled`, tag filtering hoặc điều kiện chạy.

### 2.2. Surefire không phải JUnit

JUnit Jupiter cung cấp các annotation `@Test` và assertions. Maven Surefire Plugin là công cụ chạy kiểm thử trong lifecycle Maven. Vì thế POM cần:

- JUnit Jupiter ở `<dependencies>`, scope `test`.
- Surefire ở `<build><plugins>` với version được kiểm soát.

Nếu chỉ khai JUnit nhưng dùng Surefire quá cũ/không có provider phù hợp, test có thể không được discovery hoặc thực thi đúng. Nếu chỉ khai Surefire nhưng không đưa JUnit vào test classpath, source test dùng `org.junit.jupiter.api.Test` không biên dịch được.

## 3. Dự án ví dụ Java 17: 2 lớp, 6 phương thức test

Bài thực hành dùng hai lớp test có phương thức tên tường minh và không overload/nested/parameterized. Nhờ vậy ta có thể dự đoán **chính xác số test** theo mỗi lệnh chọn.

Cây thư mục:

~~~text
test-selection-demo/
├── pom.xml
└── src/
    ├── main/java/vn/example/selection/
    │   └── Calculator.java
    └── test/java/vn/example/selection/
        ├── CalculatorTest.java
        └── LabelTest.java
~~~

Cần Maven 3.9.x, JDK 17+ và repository có khả năng tải dependency/plugin trong lần chạy đầu. Tất cả lệnh ở các phần tiếp theo dùng từ thư mục `test-selection-demo` trừ khi nói rõ khác.

### 3.1. pom.xml hoàn chỉnh

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>vn.example</groupId>
    <artifactId>test-selection-demo</artifactId>
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
                <version>3.14.1</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.4</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
                <configuration>
                    <archive>
                        <manifest>
                            <mainClass>vn.example.selection.Calculator</mainClass>
                        </manifest>
                    </archive>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Giải thích:

- `maven.compiler.release=17` yêu cầu mức Java 17; nó không cài JDK, vì vậy `mvn -version` vẫn phải chỉ một JDK phù hợp.
- `junit-jupiter` chứa thành phần để biên dịch và chạy test JUnit Jupiter, nhưng không nằm trong runtime classpath bình thường của ứng dụng.
- Maven Surefire Plugin 3.5.4 chạy test JUnit 5 thông qua JUnit Platform provider tương ứng.
- JAR Plugin ghi manifest `Main-Class`. Ví dụ main không có external runtime dependencies nên `java -jar` có thể chạy mà không cần fat JAR.
- Không cố ý cấu hình `includes`, `excludes` hoặc skip flags. Mục đích là đo riêng tác dụng của `-Dtest`.

### 3.2. Mã sản phẩm: Calculator.java

File `src/main/java/vn/example/selection/Calculator.java`:

~~~java
package vn.example.selection;

import java.util.Locale;
import java.util.Objects;

public final class Calculator {
    private Calculator() {
    }

    public static int add(int a, int b) {
        return Math.addExact(a, b);
    }

    public static int divide(int numerator, int denominator) {
        return numerator / denominator;
    }

    public static String normalize(String text) {
        return Objects.requireNonNull(text, "text")
                .trim()
                .toUpperCase(Locale.ROOT);
    }

    public static void main(String[] args) {
        System.out.println("sum=" + add(2, 3));
        System.out.println("label=" + normalize(" maven "));
    }
}
~~~

Ứng dụng sử dụng API của JDK: `Math.addExact`, phép chia nguyên, `Objects.requireNonNull`, `Locale.ROOT`. Nó không cần JUnit để chạy `main`. Stdout **chính xác** của chương trình:

~~~text
sum=5
label=MAVEN
~~~

Dòng này không phải do Surefire tự in khi chạy test. Ta sẽ dùng `java` riêng để kiểm tra sau.

### 3.3. Lớp test thứ nhất: CalculatorTest.java

File `src/test/java/vn/example/selection/CalculatorTest.java`:

~~~java
package vn.example.selection;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class CalculatorTest {
    @Test
    void addsNumbers() {
        assertEquals(5, Calculator.add(2, 3));
    }

    @Test
    void addsNegativeNumbers() {
        assertEquals(-1, Calculator.add(2, -3));
    }

    @Test
    void dividesNumbers() {
        assertEquals(3, Calculator.divide(9, 3));
    }

    @Test
    void rejectsDivisionByZero() {
        assertThrows(ArithmeticException.class,
                () -> Calculator.divide(1, 0));
    }
}
~~~

Có đúng **4** phương thức `@Test`:

~~~text
CalculatorTest
├── addsNumbers
├── addsNegativeNumbers
├── dividesNumbers
└── rejectsDivisionByZero
~~~

JUnit Jupiter cho phép test class/method package-private; không cần `public` ở đây. Các methods không phụ thuộc thứ tự chạy, không được đánh dấu `@Disabled`, không overload và không parameterized.

### 3.4. Lớp thứ hai: LabelTest.java

File `src/test/java/vn/example/selection/LabelTest.java`:

~~~java
package vn.example.selection;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class LabelTest {
    @Test
    void normalizesInput() {
        assertEquals("MAVEN", Calculator.normalize(" maven "));
    }

    @Test
    void rejectsNullInput() {
        assertThrows(NullPointerException.class,
                () -> Calculator.normalize(null));
    }
}
~~~

Có đúng **2** test ở lớp này. Tổng project: **4 + 2 = 6**.

### 3.5. Chạy tất cả để có baseline

~~~bash
java -version
mvn -version
mvn clean test
~~~

Với ba file Java, POM hợp lệ, JDK 17+ và dependency/plugin tải được, kết quả mong đợi là:

~~~text
Tests run: 6, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
~~~

Đây là số liệu **tóm tắt mong đợi**, không phải log Maven nguyên văn. Console có thể in riêng kết quả cho từng class trước phần tổng.

Các đầu ra cần thấy:

~~~text
target/
├── classes/vn/example/selection/Calculator.class
├── test-classes/vn/example/selection/CalculatorTest.class
├── test-classes/vn/example/selection/LabelTest.class
└── surefire-reports/
    ├── TEST-vn.example.selection.CalculatorTest.xml
    └── TEST-vn.example.selection.LabelTest.xml
~~~

Surefire cũng có thể sinh file `*.txt`. Dùng `mvn clean test` để đảm bảo không còn report cũ trong `target` gây nhầm lẫn.

### 3.6. Chạy Java main, không phải chạy test

~~~bash
java -cp target/classes vn.example.selection.Calculator
~~~

Stdout:

~~~text
sum=5
label=MAVEN
~~~

Nếu muốn kiểm tra JAR:

~~~bash
mvn package
java -jar target/test-selection-demo-1.0.0.jar
~~~

Kết quả vẫn là hai dòng trên. `mvn package` sẽ đi qua phase `test` và chạy các test theo cấu hình hiện có; chính lệnh `java -jar` mới gọi main.

## 4. Chọn một lớp test

Cú pháp phổ biến nhất:

~~~bash
mvn "-Dtest=CalculatorTest" test
~~~

Surefire chọn `CalculatorTest`, chạy bốn methods `@Test` của lớp ấy và không thực thi hai methods thuộc `LabelTest`. Số liệu mong đợi trong lần chạy sạch:

~~~text
Tests run: 4, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
~~~

Không cần đuôi `.java` hoặc `.class`. Tên lớp đủ nếu trong project không có class trùng tên gây mơ hồ. Bạn có thể dùng tên đầy đủ có package:

~~~bash
mvn "-Dtest=vn.example.selection.CalculatorTest" test
~~~

Với ví dụ này nó cũng chọn bốn methods. Dùng fully qualified class name đặc biệt hữu ích trong project có nhiều package cùng chứa tên `CalculatorTest`.

Một lựa chọn khác:

~~~bash
mvn "-Dtest=LabelTest" test
~~~

Kết quả mong đợi:

~~~text
Tests run: 2, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
~~~

**Đừng nhầm class test và main class.** Lệnh `java vn.example.selection.CalculatorTest` không phải cách chạy `@Test` của JUnit, vì lớp này không cung cấp `public static void main`. Hãy chạy bằng Maven Surefire hoặc một JUnit Platform runner được cấu hình.

## 5. Chọn đúng một phương thức bằng dấu #

Cú pháp trọng tâm:

~~~bash
mvn "-Dtest=CalculatorTest#addsNumbers" test
~~~

Đọc câu lệnh:

~~~text
-Dtest=CalculatorTest#addsNumbers
       |              |
       |              +-- Java method tên addsNumbers
       +----------------- test class CalculatorTest
~~~

Với POM và các methods thường của ví dụ, dự kiến **một test** được thực thi:

~~~text
Tests run: 1, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
~~~

Thử chọn method khác:

~~~bash
mvn "-Dtest=CalculatorTest#rejectsDivisionByZero" test
~~~

`rejectsDivisionByZero` test exception của `Calculator.divide(1,0)`; nó cũng có một `@Test` nên dự kiến một test.

### 5.1. Dùng tên Java method, không dùng tên business function

Trong source:

~~~java
@Test
void dividesNumbers() {
    assertEquals(3, Calculator.divide(9, 3));
}
~~~

Tên test method là `dividesNumbers`; tên method production mà nó gọi là `divide`. Vì vậy:

~~~bash
mvn "-Dtest=CalculatorTest#dividesNumbers" test
~~~

là lựa chọn đúng. Lệnh chọn `#divide` **không tự động** chuyển thành `#dividesNumbers`. `-Dtest` lọc theo pattern/tên, không phân tích ý nghĩa tiếng Anh của test.

### 5.2. Dùng cả package và method

~~~bash
mvn "-Dtest=vn.example.selection.CalculatorTest#addsNumbers" test
~~~

Cách viết này xác định một class cụ thể theo tên đầy đủ. Với demo, vẫn chỉ **1 test**. Nếu hệ thống có test class trùng tên nhưng khác package, FQN làm command dễ review hơn.

### 5.3. Lỗi khi gõ nhầm tên method

~~~bash
mvn "-Dtest=CalculatorTest#methodDoesNotExist" test
~~~

Không có Java method nào tên như vậy trong project mẫu. Surefire 3.5.4 có cấu hình mặc định **`failIfNoSpecifiedTests=true`**, nên khi không test nào khớp, build thường báo lỗi “no tests matching pattern were executed” thay vì im lặng thành công.

Không nên thêm `-Dsurefire.failIfNoSpecifiedTests=false` chỉ để chuyển kết quả thành xanh. Hãy sửa đúng tên class/method và kiểm tra lại số test.

## 6. Chọn theo wildcard: * và ?

Surefire hỗ trợ patterns thông dụng:

- `*`: khớp không hoặc nhiều ký tự.
- `?`: khớp đúng một ký tự.

Ví dụ:

~~~bash
mvn "-Dtest=*Test" test
~~~

Trong project demo, `*Test` khớp cả `CalculatorTest` và `LabelTest`, nên có **6 test**.

~~~bash
mvn "-Dtest=Calc*Test" test
~~~

Trong demo, chỉ `CalculatorTest` khớp, nên có **4 test**.

### 6.1. Wildcard theo tên phương thức

~~~bash
mvn "-Dtest=CalculatorTest#adds*" test
~~~

Hai method tên:

~~~text
addsNumbers
addsNegativeNumbers
~~~

đều bắt đầu bằng `adds`. Với Surefire/JUnit Jupiter provider phù hợp và ví dụ methods `@Test` đơn giản, dự kiến **2 test**.

Một pattern khác:

~~~bash
mvn "-Dtest=CalculatorTest#rejects*" test
~~~

Chọn `rejectsDivisionByZero`: **1 test**.

`?` hữu ích khi chỉ khác một ký tự trong class hoặc method name. Nó không phải một dấu hỏi mang ý nghĩa tự do về ngữ nghĩa; pattern phải khớp chuỗi theo luật Surefire.

### 6.2. Luôn quote pattern trong terminal

Không nên dựa vào shell để tự giữ nguyên `*` hay `?`. Hãy đưa cả property thành một argument:

~~~bash
mvn "-Dtest=CalculatorTest#adds*" test
~~~

Trong Bash, PowerShell và CMD, cú pháp quoting có khác biệt (xem mục 13). Dấu nháy giúp Surefire, chứ không phải shell, nhận và giải thích pattern.

## 7. Nhiều lớp và nhiều method trong một value

### 7.1. Chọn hai lớp bằng dấu phẩy

~~~bash
mvn "-Dtest=CalculatorTest,LabelTest" test
~~~

Surefire đọc hai tên lớp trong một property `test`. Với project demo, hai lớp có tổng **6 test**.

Bạn cũng có thể kết hợp tên và wildcard:

~~~bash
mvn "-Dtest=Calc*Test,LabelTest" test
~~~

Với chính hai lớp của demo, kết quả vẫn **6 test**. Trong dự án lớn có nhiều class phù hợp `Calc*Test`, số test có thể cao hơn; hãy kiểm tra Surefire report thay vì dựa bảng đếm mẫu.

### 7.2. Chọn hai method của cùng một class

Cú pháp kết hợp method của Surefire dùng dấu `+`, ví dụ:

~~~bash
mvn "-Dtest=CalculatorTest#addsNumbers+dividesNumbers" test
~~~

Ý định là chọn `addsNumbers` và `dividesNumbers`. Với provider hỗ trợ selector phức hợp, hai methods thường của demo cho kết quả **2 test**.

**Ghi chú tương thích:** tài liệu Surefire mô tả lịch sử hỗ trợ các biểu thức method phức hợp theo từng test provider (JUnit 4/TestNG và JUnit Platform). Khi dùng JUnit Jupiter, test parameterized, nested, dynamic hoặc version plugin khác, **phải xác nhận test thực thi bằng report**. Không nên mặc định mọi dạng selector có cùng behavior trên mọi provider.

### 7.3. Chọn một method ở hai lớp khác nhau

Ví dụ pattern phối hợp:

~~~bash
mvn "-Dtest=CalculatorTest#addsNumbers,LabelTest#normalizesInput" test
~~~

Biểu thức hướng đến hai methods thuộc hai class. Khi cả hai selectors được provider xử lý, kỳ vọng **2 test**. Nếu kết quả khác, kiểm tra plugin/provider và dùng hai lần chạy độc lập để cô lập nguyên nhân.

Đối với debug một lỗi duy nhất, cách đơn giản và ít mơ hồ nhất vẫn là `-Dtest=Class#method`.

### 7.4. Patterns phủ định và regex

Surefire còn có syntax phủ định bằng `!` và regex dạng `%regex[...]`. Đây là tính năng của pattern parser chứ không phải JUnit `@Tag`. Với một danh sách lớn hoặc biểu thức phức tạp, nên đọc tài liệu của **đúng phiên bản Surefire** trước khi sử dụng.

Ví dụ minh họa loại `LabelTest` khỏi các lớp kết thúc `Test`:

~~~bash
mvn '-Dtest=*Test,!LabelTest' test
~~~

Đây là lệnh viết theo cách quote an toàn cho **Bash** và thường dùng được trong **PowerShell**. Với **Windows CMD**, dùng dấu nháy đôi:

~~~bat
mvn "-Dtest=*Test,!LabelTest" test
~~~

Bash tương tác có history expansion với `!` trong một số hoàn cảnh, nên tránh đặt `!` trong double quotes nếu đang bật tính năng ấy.

Dùng lọc phủ định/regex phải đi kèm việc kiểm tra **test count và class nào thật sự chạy**; biểu thức nhìn “đúng” nhưng chọn quá ít test vẫn là một rủi ro.

## 8. Bảng đối chiếu lệnh trong project mẫu

Với POM ở mục 3, không có skipped/disabled tests:

| Command | Phạm vi được chọn | Số test dự kiến |
| --- | --- | ---: |
| `mvn clean test` | Tất cả test | **6** |
| `mvn "-Dtest=CalculatorTest" test` | CalculatorTest | **4** |
| `mvn "-Dtest=LabelTest" test` | LabelTest | **2** |
| `mvn "-Dtest=CalculatorTest#addsNumbers" test` | Một method | **1** |
| `mvn "-Dtest=CalculatorTest#rejectsDivisionByZero" test` | Một method | **1** |
| `mvn "-Dtest=*Test" test` | Hai lớp theo pattern | **6** |
| `mvn "-Dtest=Calc*Test" test` | Một lớp theo pattern | **4** |
| `mvn "-Dtest=CalculatorTest#adds*" test` | Hai methods theo prefix | **2** |
| `mvn "-Dtest=CalculatorTest,LabelTest" test` | Hai lớp | **6** |
| `mvn "-Dtest=CalculatorTest#addsNumbers+dividesNumbers" test` | Hai methods | **2** khi provider hỗ trợ |
| `mvn "-Dtest=CalculatorTest#addsNumbers,LabelTest#normalizesInput" test` | Một method mỗi lớp | **2** khi provider hỗ trợ |

Số trong bảng là **kỳ vọng từ source mẫu**, không phải một cách giả lập kết quả thật của máy người học. Sau khi chạy, con số ở Surefire reports là bằng chứng cuối.

### 8.1. Sơ đồ một class so với một method

~~~text
-Dtest=CalculatorTest
       |
       +-- addsNumbers
       +-- addsNegativeNumbers
       +-- dividesNumbers
       +-- rejectsDivisionByZero

-Dtest=CalculatorTest#addsNumbers
       |
       +-- addsNumbers
~~~

Với selector theo method, Surefire **không cần sửa lớp Java** để tắt ba method còn lại. Nó chỉ quyết định test nào được framework/provider thực thi ở lần chạy đó.

## 9. Đọc Surefire Reports đúng cách

Sau khi Surefire chạy, báo cáo thường nằm trong:

~~~text
target/surefire-reports/
~~~

Hai dạng thông thường:

~~~text
TEST-vn.example.selection.CalculatorTest.xml
vn.example.selection.CalculatorTest.txt
TEST-vn.example.selection.LabelTest.xml
vn.example.selection.LabelTest.txt
~~~

XML có thể chứa attributes đại diện số test/failure/error/skipped. Một đoạn **minh họa cấu trúc**:

~~~xml
<testsuite name="vn.example.selection.CalculatorTest"
           tests="1"
           failures="0"
           errors="0"
           skipped="0">
    <!-- Surefire tạo thêm testcase, properties, thời gian ... -->
</testsuite>
~~~

Đoạn này không phải nguyên văn bắt buộc của mọi bản Surefire. Khi chạy `-Dtest=CalculatorTest#addsNumbers`, bạn muốn tìm **một testcase tương ứng** và xác nhận trạng thái pass.

### 9.1. Vì sao nên dùng clean khi đo số test?

Nếu lần trước chạy tất cả sáu test, rồi chỉ chạy một method không có `clean`, một số files trong `surefire-reports` có thể còn dữ liệu từ lần trước. Đếm số XML files đơn giản có thể gây nhầm.

Trong bài tập xác minh, dùng:

~~~bash
mvn clean "-Dtest=CalculatorTest#addsNumbers" test
~~~

Sau đó đọc report của đúng lần chạy. `clean` dọn output trong `target`, không xóa dependency cache `~/.m2/repository`.

### 9.2. BUILD SUCCESS chưa đủ

`BUILD SUCCESS` không bảo đảm **test mà bạn định chạy đã thực sự chạy** trong mọi cấu hình. Một lệnh có `-DskipTests`, `maven.test.skip=true` hoặc cấu hình tránh fail khi không có test có thể khiến Maven hoàn tất nhưng thiếu kiểm chứng mong muốn.

Checklist xác nhận gồm:

1. Tên test class/method đã được chọn đúng.
2. `Tests run` là con số dự kiến.
3. `Failures=0`, `Errors=0`, và đã xem `Skipped`.
4. Surefire reports thuộc **lần chạy hiện tại**.
5. Không có skip flags trái với mục đích.

## 10. Sai tên lớp hoặc method: failIfNoSpecifiedTests

Thử:

~~~bash
mvn "-Dtest=DoesNotExistTest" test
~~~

Không có class `DoesNotExistTest` trong project mẫu. Surefire thông thường báo lỗi tương tự:

~~~text
No tests matching pattern "DoesNotExistTest" were executed!
~~~

Thông điệp thực có thể khác về dấu nháy, tên pattern hoặc plugin version; đây là **lỗi không tìm thấy specified test**, không phải assertion của Java test thất bại.

Một trường hợp khác:

~~~bash
mvn "-Dtest=CalculatorTest#methodDoesNotExist" test
~~~

Cũng không khớp source. Đừng cố thêm một Java method giả hoặc đổi mã production để làm filter qua; sửa command đúng tên test, hoặc xem class/method thực tế trong source.

### 10.1. Mặc định failIfNoSpecifiedTests=true

Surefire Plugin có user property:

~~~text
surefire.failIfNoSpecifiedTests
~~~

Giá trị mặc định là **true**. Đây là lựa chọn an toàn: gõ nhầm selector sẽ không làm CI im lặng báo xanh.

Bạn có thể tắt khi thực sự có lý do:

~~~bash
mvn "-Dtest=CalculatorTest" "-Dsurefire.failIfNoSpecifiedTests=false" test
~~~

Nhưng việc tắt lỗi **không tạo ra test**, cũng không xác nhận một method được chạy. Cần xem số `Tests run` và report. Trong project demo đơn module, thường **không có lý do** để tắt option này.

### 10.2. Khác biệt với failIfNoTests

| Cấu hình | Mục đích | Default Surefire 3.5.4 |
| --- | --- | --- |
| `surefire.failIfNoSpecifiedTests` | Không có test khớp `-Dtest` | `true` |
| `failIfNoTests` | Trường hợp tổng quát không tìm thấy test để chạy | `false` |

Hai tham số không đồng nghĩa. Khi gặp lỗi “No tests matching”, đầu tiên kiểm tra cách gõ `-Dtest` và module đúng, không tắt cả hai kiểm tra.

## 11. Lọc test thực thi không đồng nghĩa lọc test compilation

Với lệnh:

~~~bash
mvn "-Dtest=CalculatorTest#addsNumbers" test
~~~

Maven lifecycle vẫn thực hiện:

~~~text
compile       -> biên dịch src/main/java
test-compile  -> biên dịch src/test/java
test          -> Surefire thực thi addsNumbers
~~~

Nếu `LabelTest.java` có lỗi cú pháp, `test-compile` có thể fail **trước khi** Surefire được gọi, dù bạn đã chọn một method của `CalculatorTest`.

Ví dụ `LabelTest.java` có lời gọi thiếu dấu đóng ngoặc: compiler sẽ từ chối build. `-Dtest` không bảo Java compiler “bỏ qua lớp không được chọn”. Cần sửa source/test compilation trước.

Tương tự:

- Sai cú pháp ở `Calculator.java` → fail `compile`.
- Không tải được `junit-jupiter` → lỗi dependency resolution/test classpath.
- Method được chọn có assertion sai → fail `surefire:test`.
- Chọn một method không tồn tại → lỗi không tìm thấy specified test ở Surefire.

**Đây là lý do `-Dtest` không phải công cụ chữa mọi lỗi build.**

## 12. Không dùng skip flags cùng lúc với lựa chọn test

Các cờ liên quan:

| Cờ | Ảnh hưởng thông thường |
| --- | --- |
| `-Dtest=CalculatorTest` | Surefire chọn lớp test để thực thi |
| `-DskipTests` | Bỏ việc **thực thi** test, thông thường vẫn biên dịch test |
| `-Dmaven.test.skip=true` | Bỏ cả bước **biên dịch và thực thi** test ở các plugin có hỗ trợ |

Ví dụ lệnh này tự mâu thuẫn mục tiêu:

~~~bash
mvn "-Dtest=CalculatorTest#addsNumbers" -DskipTests test
~~~

Bạn đã chọn một test nhưng đồng thời yêu cầu bỏ chạy test. Nếu Maven in `BUILD SUCCESS`, không được kết luận `addsNumbers` đã pass.

Kiểm tra cả cấu hình CI/Maven profiles và `.mvn/maven.config` nếu script có các default flags được thêm ngầm.

### 12.1. Disabled test vẫn có thể bị skip

Một method có:

~~~java
@Disabled("Temporary")
@Test
void sampleMethod() {
    // ...
}
~~~

Đây là **snippet minh họa**, không thuộc source runnable mục 3 và muốn dùng thì phải import `org.junit.jupiter.api.Disabled`. Khi JUnit quyết định method `@Disabled`, selector `-Dtest` không làm nó tự động chạy. Report có thể ghi skipped.

## 13. Shell quoting: Bash, PowerShell và Windows CMD

Những ký tự như `#`, `*`, `?`, `!`, `,` và `+` có thể bị shell xử lý theo cách riêng. Nên quote toàn bộ `-Dtest=...` như một argument.

### 13.1. Bash hoặc Zsh

~~~bash
mvn '-Dtest=CalculatorTest#addsNumbers' test
mvn '-Dtest=CalculatorTest#adds*' test
mvn '-Dtest=*Test,!LabelTest' test
~~~

Dấu nháy đơn trong Bash giữ nguyên nội dung không cần biến môi trường nội suy. Đây là cách đặc biệt an toàn với `!` trong interactive Bash nếu history expansion đang bật.

### 13.2. Windows PowerShell

~~~powershell
mvn '-Dtest=CalculatorTest#addsNumbers' test
mvn '-Dtest=CalculatorTest#adds*' test
mvn '-Dtest=CalculatorTest,LabelTest' test
~~~

Single-quoted string của PowerShell giữ các ký tự đặc biệt nguyên dạng. Nếu bạn dùng profile chạy qua wrapper script, vẫn phải xem wrapper có truyền lại argument đúng hay không.

### 13.3. Windows CMD

~~~bat
mvn "-Dtest=CalculatorTest#addsNumbers" test
mvn "-Dtest=CalculatorTest#adds*" test
mvn "-Dtest=CalculatorTest,LabelTest" test
~~~

CMD dùng dấu nháy **đôi** để gom argument; không sao chép dấu nháy đơn Bash rồi cho rằng CMD sẽ bỏ chúng như nhau.

### 13.4. Cách viết phổ biến cho lựa chọn đơn giản

~~~bash
mvn "-Dtest=CalculatorTest#addsNumbers" test
~~~

Lệnh này phù hợp với các shell thông dụng cho ví dụ không có `!` hoặc các ký tự phải escape thêm. Với regex hoặc CLI phức tạp, dùng cú pháp quoting đúng **môi trường đang chạy**, không coi một mẫu chung là tuyệt đối.

## 14. JUnit 5 nâng cao: DisplayName, Parameterized và Nested

Các ví dụ chính dùng methods `@Test` thông thường để chọn theo tên Java. Trong test suite thật có thể gặp:

### 14.1. @DisplayName không đổi tên method

~~~java
@DisplayName("Cộng số")
@Test
void addsNumbers() {
    assertEquals(5, Calculator.add(2, 3));
}
~~~

Đây là **đoạn thay thế một method trong CalculatorTest**, không phải file đầy đủ. Phải import `org.junit.jupiter.api.DisplayName` khi dùng. CLI vẫn chọn bằng **tên Java method**:

~~~bash
mvn "-Dtest=CalculatorTest#addsNumbers" test
~~~

Không dùng `"Cộng số"` làm tên method sau `#`.

### 14.2. Một method có thể tạo nhiều test invocations

`@ParameterizedTest` và `@RepeatedTest` có thể sinh nhiều lần chạy từ **một Java method**. Chọn `Class#method` không phải lúc nào cũng tương đương “một testcase” ở report.

`@TestFactory` tạo dynamic tests khi runtime. `@Nested` tổ chức một cây nested test classes, có tên/discovery khác top-level. Những kiểu này phụ thuộc cách JUnit Platform provider thực thi và biểu thức filter; không nên áp dụng các số 1/2/4/6 của project demo lên chúng.

Nếu Java methods bị overload cùng tên, pattern chỉ nêu tên có thể khớp nhiều trường hợp; nên đọc tài liệu Surefire/JUnit provider của version dùng và kiểm tra XML reports để chắc chắn selector đúng.

### 14.3. @Tag và -Dtest là hai lớp lựa chọn

JUnit 5 có `@Tag("fast")`/`@Tag("slow")` để phân loại test về mặt ngữ nghĩa. Surefire có các tùy chọn nhóm/tag riêng, ví dụ `groups` và `excludedGroups` với JUnit Platform. `-Dtest` lại là **bộ lọc theo class/method name**.

Đừng nhầm `-Dtest=fast` thành “chạy mọi JUnit test mang tag fast”. Nếu cần nhóm test ổn định cho CI, nên dùng tag/config theo quy ước project; nếu cần chạy đúng một method lúc debug, dùng `Class#method`.

## 15. Project nhiều module: -pl, -am và rủi ro no specified tests

Giả sử reactor:

~~~text
company-parent/
├── pom.xml
├── domain/
│   └── pom.xml
├── service/
│   └── pom.xml
└── api/
    └── pom.xml
~~~

Chỉ module `service` có `CalculatorTest`. Nếu từ root chạy:

~~~bash
mvn "-Dtest=CalculatorTest" test
~~~

property `test=CalculatorTest` có thể được truyền tới Surefire của **nhiều module**. Các module khác không có `CalculatorTest` có thể fail với `failIfNoSpecifiedTests=true`.

### 15.1. Chọn module với -pl

Khi `artifactId` của module là `service`, dùng:

~~~bash
mvn -pl :service "-Dtest=CalculatorTest" test
~~~

`-pl` chọn module reactor; `-Dtest` chọn test bên trong module đó. Nhưng nếu module có dependency nội bộ chưa được build/install, Maven có thể không resolve được artifact.

### 15.2. -am kéo module phụ vào build

~~~bash
mvn -pl :service -am "-Dtest=CalculatorTest" test
~~~

`-am` (also make) đưa các module mà service phụ thuộc vào reactor. Những module đó có thể nhận cùng `-Dtest` và không chứa class được chỉ định, dẫn tới lỗi không tìm thấy test.

Trường hợp đặc biệt có thể dùng:

~~~bash
mvn -pl :service -am "-Dtest=CalculatorTest" "-Dsurefire.failIfNoSpecifiedTests=false" test
~~~

**Không khuyến nghị coi lệnh này tự đủ QA**: nó có thể che việc `service` cũng không chọn được `CalculatorTest` do gõ sai. Phải kiểm tra **report của service**, bảo đảm ít nhất một test đúng tên đã chạy.

Một lựa chọn khác là build/install các dependency modules theo pipeline, rồi chạy riêng `-pl :service` (không `-am`) để không khiến mọi module nhận cùng test filter. Đảm bảo dùng dependency artifacts của cùng build, không dùng JAR cũ.

### 15.3. Phân biệt ba quyết định

- `-pl`: module nào được chọn.
- `-am`: module phụ thuộc nào cũng được build.
- `-Dtest`: test class/method nào Surefire sẽ chọn **trong mỗi module đang chạy goal**.

Không nên dùng mỗi `-Dtest` để thay quyết định chọn module; chúng hoạt động ở hai tầng khác nhau.

## 16. Maven Surefire và Maven Failsafe không cùng parameter

Hai plugin có chức năng thường được chia như sau:

| Plugin | Mục tiêu | Phase | Tham số chọn |
| --- | --- | --- | --- |
| Maven Surefire Plugin | Unit tests | `test` | `-Dtest=...` |
| Maven Failsafe Plugin | Integration tests | `integration-test` và `verify` nếu được cấu hình | `-Dit.test=...` |

Ví dụ của project runnable:

~~~bash
mvn "-Dtest=CalculatorTest#addsNumbers" test
~~~

Ví dụ **chỉ minh họa cú pháp Failsafe**, không runnable với POM mẫu vì không có lớp `DatabaseIT` và chưa cấu hình Failsafe:

~~~bash
mvn "-Dit.test=DatabaseIT" verify
~~~

Đừng dùng `-Dtest=DatabaseIT` để khẳng định Failsafe sẽ lọc integration tests. Ngược lại, `-Dit.test=CalculatorTest` không phải cách điều khiển Surefire của bài.

### 16.1. Gọi goal trực tiếp có thể dùng output cũ

~~~bash
mvn surefire:test "-Dtest=CalculatorTest"
~~~

Lời gọi goal này **không đảm bảo test-compile đã chạy trong cùng lệnh**. Nếu test source mới sửa mà `target/test-classes` cũ, bạn có thể thấy kết quả không phản ánh mã mới.

Trong lúc học hoặc điều tra lỗi, ưu tiên:

~~~bash
mvn clean "-Dtest=CalculatorTest" test
~~~

Lệnh phase giúp chạy qua các bước biên dịch đến test, có `clean` để dọn stale artifacts.

## 17. Lỗi thường gặp và chẩn đoán

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| `No tests matching pattern` | Sai class/method/package, nhầm module | Kiểm tra source thật, chạy `-Dtest=Class` trước, xem reports |
| Chọn một method nhưng testCompile fail | File test khác có Java syntax error | Sửa source; `-Dtest` lọc **execution**, không lọc compilation |
| Maven báo BUILD SUCCESS, tests run 0 | Skip flags hoặc cấu hình không fail khi không test | Kiểm tra skip flags, Surefire report, failIfNoSpecifiedTests |
| `-Dtest=CalculatorTest#divide` không tìm thấy | Java method thật tên `dividesNumbers` | Dùng `#dividesNumbers` hoặc pattern phù hợp |
| Method chạy nhiều lần | Parameterized/repeated tests hoặc pattern nhiều matches | Xem JUnit annotations và XML report |
| Lớp không xuất hiện trong suite mặc định | Tên file không khớp include patterns | Đặt tên `*Test`/`*Tests` hoặc cấu hình đúng |
| Test mang `@Disabled` | JUnit bỏ qua dù class được chọn | Kiểm tra skipped và điều kiện JUnit |
| Pattern chứa `!` hoặc `*` bị đổi | Shell xử lý history/glob/quoting | Quote toàn argument theo shell |
| CI sử dụng `-DskipTests` | Surefire không thực thi | Loại bỏ cờ skip khi mục đích là chạy test |
| Reactor phụ fail do không có test | `-am` làm nhiều module nhận cùng property | `-pl`/build artifacts phù hợp; chỉ tắt fail flag có điều kiện |
| `mvn surefire:test` không thấy mã mới | Không chạy compile/testCompile | Gọi lifecycle `mvn test` |
| Report vẫn có XML của lớp không được chọn | File cũ trong `target` | Build sạch và kiểm tra timestamps/log |
| JUnit 5 test không chạy | Plugin/provider/engine không hợp lệ | Kiểm tra JUnit Jupiter dependency, Surefire version |
| Maven không tải được Surefire/JUnit | Repository/mirror/proxy/credentials | Chẩn đoán dependency resolution, không sửa filter vô ích |
| Integration test không chạy | Đang dùng Failsafe, không phải Surefire | Dùng `-Dit.test` và phase/goal tương ứng |
| Chỉ chạy một method rồi báo toàn bộ suite pass | Phạm vi kiểm thử quá hẹp | Chạy full `mvn test`/CI regression trước release |

### 17.1. Quy trình xử lý trong sáu bước

1. Đọc đúng lệnh CLI, shell, project directory, options `-pl/-am` và mọi skip flag.
2. Xác định Java package, tên class, tên method, annotations và module đang chứa test.
3. Xác minh plugin/version/test framework của module từ POM/effective POM khi cần.
4. Phân biệt phase lỗi: compile, test-compile, Surefire goal hay assertion test.
5. Chạy một lớp trước bằng `-Dtest=Class`, sau đó thu hẹp bằng `Class#method`.
6. Đọc Surefire Reports của **lần chạy mới**, kiểm tra test count/skips/failures/errors và quay lại chạy full suite sau khi sửa.

Không sửa toàn bộ build bằng cách vô hiệu kiểm tra `failIfNoSpecifiedTests`. Điều này dễ làm một command chọn test sai báo thành công.

## 18. Sử dụng -Dtest trong phát triển và CI

### 18.1. Vòng lặp phát triển hợp lý

Khi sửa một hàm:

1. Chạy method tái hiện bug: `-Dtest=CalculatorTest#addsNumbers`.
2. Khi bug fix pass, chạy cả `CalculatorTest` để mở rộng phạm vi.
3. Chạy `mvn test` không có `-Dtest` để phát hiện ảnh hưởng tới các lớp khác.
4. Chạy integration tests và CI checks theo quy định dự án trước khi merge/phát hành.

Đây là chiến lược **feedback nhanh rồi mở rộng**. `-Dtest` không thay thế regression testing.

### 18.2. Ghi nhận command và test count trong CI

Một job fast-feedback có thể dùng `-Dtest`, nhưng job kiểm tra trước merge cần rõ phạm vi. Lưu:

- Maven/JDK và Surefire versions.
- Command Maven đã chạy và selector thực tế.
- Module selection `-pl/-am`.
- `Tests run, Failures, Errors, Skipped`.
- Surefire reports và thời điểm build.
- Bất kỳ flag nào thay đổi scope kiểm thử.

Chỉ có `BUILD SUCCESS` với một test được lọc không chứng minh tất cả test của hệ thống đã pass.

### 18.3. Khi nên dùng giải pháp khác

Nếu một nhóm test thường xuyên được chạy theo chính sách CI, cân nhắc cấu hình `includes/excludes`, JUnit `@Tag`, Maven profiles hoặc tách module test. `-Dtest` rất phù hợp với **lựa chọn đích danh tạm thời**, nhưng không nên biến một chuỗi patterns dài khó review thành cổng QA chính thức mà không có cách xác nhận số test.

## 19. Bài tập cuối bài

### Bài tập A — Baseline

Dựng project ở mục 3, chạy `mvn clean test`. Kiểm chứng **6 tests PASS** bằng log và XML reports. Ghi lại hai tên class `CalculatorTest` và `LabelTest`.

### Bài tập B — Chọn lớp

~~~bash
mvn clean "-Dtest=CalculatorTest" test
~~~

Dự đoán **4 test**. Giải thích tại sao `LabelTest.java` vẫn được biên dịch nhưng hai methods của nó không được Surefire thực thi.

### Bài tập C — Chọn method

~~~bash
mvn clean "-Dtest=CalculatorTest#addsNumbers" test
~~~

Dự đoán **1 test**. Tìm report và chứng minh `addsNumbers` đã được chạy.

### Bài tập D — Pattern method

~~~bash
mvn clean "-Dtest=CalculatorTest#adds*" test
~~~

Liệt kê hai methods phù hợp. Kiểm tra con số **2** trên demo.

### Bài tập E — Chọn hai lớp

~~~bash
mvn clean "-Dtest=CalculatorTest,LabelTest" test
~~~

Giải thích vì sao dấu phẩy trong property tương đương yêu cầu nhiều patterns. Kết quả ví dụ là **6 test**.

### Bài tập F — Thử failure

Trong **bản sao project thực hành**, đổi expected result trong `CalculatorTest.addsNumbers` thành `6`. Chạy riêng method, xem `Failures: 1`. Khôi phục `5` rồi chạy lại. Phân biệt failure assertion với lỗi không tìm được test.

### Bài tập G — Không có method

~~~bash
mvn "-Dtest=CalculatorTest#methodDoesNotExist" test
~~~

Quan sát lỗi no tests matching. Vì sao không nên dùng `surefire.failIfNoSpecifiedTests=false` chỉ để làm xanh kết quả?

### Bài tập H — Test compilation

Cố tình tạo Java syntax error tạm trong `LabelTest.java` rồi chạy method `CalculatorTest#addsNumbers`. Dự đoán phase fail; giải thích vì sao `-Dtest` không bỏ qua `test-compile`.

### Bài tập I — Shell

Viết lại lệnh chọn `CalculatorTest#addsNumbers` cho Bash, PowerShell, CMD. Thử với `*Test` và giải thích vì sao phải quote argument.

### Bài tập J — Reactor

Giả sử chỉ module `service` chứa `CalculatorTest`. Viết lệnh `-pl :service`, rồi phân tích rủi ro khi thêm `-am`. Nếu bật `surefire.failIfNoSpecifiedTests=false`, bạn cần kiểm chứng thêm điều gì?

### Bài tập K — Phân biệt integration test

Dự án có `DatabaseIT` do Failsafe quản lý. Cú pháp chọn test tương ứng là gì? Tại sao `-Dtest` của Surefire không phải cách thay thế tổng quát cho `-Dit.test`?

### Bài tập L — Quy trình release

Bạn vừa sửa một bug tại `Calculator.add`. Đề xuất thứ tự kiểm tra: một method → một class → full unit suite → integration/CI. Ở bước nào nên bỏ `-Dtest` và tại sao?

## 20. Checklist ghi nhớ

- [ ] Biết test class/method và package thực sự trong Java source.
- [ ] Chạy `mvn "-Dtest=ClassName" test` để chọn **lớp**.
- [ ] Chạy `mvn "-Dtest=ClassName#methodName" test` để chọn **phương thức**.
- [ ] Dùng quote phù hợp shell với `#`, `*`, `?`, `+`, `,` hoặc `!`.
- [ ] Biết `-Dtest` chỉ lọc **test execution**, không chọn riêng file để biên dịch.
- [ ] Phân biệt Surefire với JUnit Jupiter và Failsafe.
- [ ] Không dùng `-DskipTests`/`maven.test.skip=true` khi muốn xác nhận test đã chạy.
- [ ] Không im lặng tắt `failIfNoSpecifiedTests` khi chỉ gõ nhầm tên.
- [ ] Đọc Surefire report của lần chạy hiện tại, không dựa vào file cũ.
- [ ] Với multi-module, kiểm soát `-pl`, `-am` và xác nhận số test đúng module.
- [ ] Chạy full regression suite trước khi merge hoặc phát hành theo yêu cầu dự án.

**Kết luận:** `-Dtest` là một bộ lọc mạnh để rút ngắn vòng lặp phát triển Java/Maven. Cú pháp `Class#method` giúp nhắm chính xác một phương thức, nhưng giá trị kiểm chứng chỉ có khi **đúng test đã thực sự chạy và được ghi trong Surefire Reports**. Sau khi sửa xong, phải mở rộng phạm vi kiểm thử phù hợp, không đánh đồng một test PASS với cả hệ thống PASS.

## 21. Tài liệu chính thức

- [Maven Surefire Plugin 3.5.4 — surefire:test](https://maven.apache.org/surefire-archives/surefire-3.5.4/maven-surefire-plugin/test-mojo.html): tham số `test`, `failIfNoSpecifiedTests`, patterns và các option của goal.
- [Maven Surefire — Running a Single Test](https://maven.apache.org/surefire/maven-surefire-plugin/examples/single-test.html): cách chọn một class, một method, nhiều patterns.
- [Maven Surefire — Using JUnit 5 Platform](https://maven.apache.org/surefire/maven-surefire-plugin/examples/junit-platform.html): hỗ trợ JUnit Jupiter engine và quy tắc class discovery.
- [Maven Surefire 3.5.4 — Inclusions and Exclusions](https://maven.apache.org/surefire-archives/surefire-3.5.4/maven-surefire-plugin/examples/inclusion-exclusion.html): default include patterns và `includes/excludes`.
- [Maven Surefire — Introduction](https://maven.apache.org/surefire/maven-surefire-plugin/): phase test, Surefire Reports và goal `surefire:test`.
- [Apache Maven — Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html): sự khác nhau giữa gọi phase và goal.
- [Maven Failsafe — Running a Single Test](https://maven.apache.org/surefire/maven-failsafe-plugin/examples/single-test.html): `it.test` cho integration tests.
