# Reactor nhiều mô-đun: chính sách -ff, -fae, -fn và tác động đến mã thoát Maven

## 1. Vấn đề thực tế

Trong dự án Java có nhiều Maven modules, một module không đạt có thể làm hỏng cả chuỗi build. Tuy nhiên, **phản ứng của Maven sau lỗi đầu tiên** và **mã thoát trả về cho terminal/CI** không phải là một chuyện duy nhất.

Ba lựa chọn Reactor quan trọng:

~~~bash
mvn -ff verify
mvn -fae verify
mvn -fn verify
~~~

- `-ff`, `--fail-fast`: **dừng sớm khi gặp project failure**. Đây là **mặc định** của Maven Reactor nếu không truyền chính sách khác.
- `-fae`, `--fail-at-end`: **tiếp tục các module không bị ảnh hưởng** và cuối cùng vẫn báo thất bại nếu có module fail.
- `-fn`, `--fail-never`: **không dùng reactor project failure để làm Maven process trả mã lỗi**. Các module có thể thất bại nhưng command vẫn trả exit code `0`. Reactor còn cố chạy những module phụ thuộc vào module đã lỗi, dù chúng có thể thất bại tiếp.

**Điểm quan trọng nhất cho CI/CD:** `-fae` vẫn giữ exit code khác `0` khi có lỗi. `-fn` có thể khiến job CI báo xanh dù đã có test/build failure. Không bao giờ đồng nhất **exit code 0** của `-fn` với **toàn bộ modules SUCCESS**.

Bài minh họa dựa trên Maven **3.9.x**, Java **17**, Compiler Plugin **3.14.1**, Surefire **3.5.4**, JAR Plugin **3.4.2** và JUnit Jupiter **5.11.4**. Versions được ghim cho ví dụ, không phải tuyên bố bản mới nhất.

### Mục tiêu

Sau bài học, bạn có thể:

1. Giải thích Reactor, dependency graph và ý nghĩa `SUCCESS`/`FAILURE`/`SKIPPED`.
2. So sánh đúng hành vi `-ff`, `-fae`, `-fn` ở một reactor có module phụ thuộc và module độc lập.
3. Hiểu tại sao `-fae` tiếp tục module độc lập nhưng không nhất thiết thử module phụ thuộc vào module lỗi.
4. Hiểu tại sao `-fn` có thể thử các module phụ thuộc và vẫn trả `0` dù nhiều module fail.
5. Chạy được reactor gồm ba child modules Java 17, cố tình gây JUnit failure mà không phá Java syntax.
6. Thu và đối chiếu mã thoát của Maven trong Bash, PowerShell, Windows CMD và scripts CI.
7. Phân biệt failure policies với `-DskipTests`, `maven.test.failure.ignore`, `-pl`, `-am`, `-amd` và `-rf`.
8. Đưa ra chính sách phù hợp khi muốn phản hồi nhanh, thu thập nhiều lỗi hoặc bảo vệ release gate.

---

## 2. Maven Reactor xử lý nhiều module như thế nào?

Một root POM có thể dùng:

~~~xml
<packaging>pom</packaging>
<modules>
    <module>math-core</module>
    <module>math-cli</module>
    <module>audit-tool</module>
</modules>
~~~

Khi gọi `mvn verify` tại root, Maven Reactor thu thập modules, sắp xếp theo quan hệ, build và báo tổng kết. Cần phân biệt hai cấu trúc:

- **Aggregation:** root `<modules>` tập hợp các modules để chạy cùng reactor.
- **Inheritance:** child `<parent>` kế thừa groupId/version/properties/plugins từ parent. Hai quan hệ không đồng nghĩa; ví dụ có thể có aggregation mà không có parent inheritance.

Trong bài:

~~~text
reactor-failure-demo (root POM)
       |
       +------------ math-core ------------+
       |                                   |
       |                                   v
       |                                math-cli
       |
       +------------ audit-tool (độc lập)
~~~

`math-cli` thực sự khai Maven dependency vào `math-core`. `audit-tool` không phụ thuộc vào hai module kia. Do đó lỗi ở math-core **ảnh hưởng downstream math-cli**, trong khi audit-tool vẫn có thể build độc lập.

### 2.1. Thứ tự build không chỉ là thứ tự các dòng modules

Maven 3 Reactor sorting xét các quan hệ được khai thực tế: project dependencies, plugin dependencies, build extensions và thứ tự `<modules>` khi không có ràng buộc khác. Chỉ đặt version trong `dependencyManagement` hoặc `pluginManagement` **không tạo dependency edge** để quyết định thứ tự.

Nếu project A cần class/artifact của B, thì B phải được xây dựng trước A trong reactor hợp lệ. Với build song song, các nhánh không phụ thuộc nhau có thể chạy đồng thời.

### 2.2. Reactor Summary và exit code là hai lớp thông tin

Ví dụ log rút gọn:

~~~text
Reactor Summary for reactor-failure-demo 1.0.0:

reactor-failure-demo ........ SUCCESS
math-core ................... FAILURE
math-cli .................... SKIPPED
audit-tool .................. SUCCESS
~~~

Đây là **minh họa**, không phải toàn bộ log Maven nguyên văn. Ba trạng thái:

- `SUCCESS`: project đã hoàn thành những goals/phases của nó trong lần chạy.
- `FAILURE`: project có lỗi mà Maven coi là build failure.
- `SKIPPED`: project chưa hoàn tất theo yêu cầu, chẳng hạn do policy hoặc dependency vào project lỗi.

**SKIPPED không có nghĩa PASSED.** Module bị skip chưa cung cấp bằng chứng test thành công.

**Exit code** là con số của **tiến trình Maven tổng thể**: `0` thường biểu thị command thành công; khác `0` biểu thị lỗi. CI thường dựa chủ yếu vào con số này, chứ không tự diễn giải từng dòng Reactor Summary. `-fn` thay đổi đáng kể mối quan hệ đó.

---

## 3. Bảng tổng hợp chính sách xử lý lỗi

| Flag | Tên dài | Sau lỗi đầu tiên | Module độc lập chưa chạy | Module phụ thuộc vào project lỗi | Mã thoát khi có reactor failure |
| --- | --- | --- | --- | --- | --- |
| `-ff` | `--fail-fast` | Dừng reactor sớm | Thường SKIPPED nếu chưa bắt đầu | Thường SKIPPED | **Khác 0** |
| `-fae` | `--fail-at-end` | Tiếp tục các module không bị ảnh hưởng; báo lỗi cuối build | Tiếp tục, có thể SUCCESS hoặc FAILURE | Thường SKIPPED do dependency bị lỗi | **Khác 0** |
| `-fn` | `--fail-never` | Cố tiếp tục cả các dependent modules | Được thử build | Được thử, nhưng có thể thất bại tiếp | **0** cho reactor project failures được policy xử lý |

Với build **không có lỗi**, cả ba chế độ bình thường trả `0`.

Với một JUnit assertion failure thông thường trong reactor, `-ff` hoặc `-fae` trả mã nonzero (thường là `1` ở Maven CLI), còn `-fn` có thể trả `0` dù một số module `FAILURE`.

**Giới hạn:** một lỗi *trước khi Maven kịp chạy reactor*, như không tìm được `mvn`, JVM không thể khởi động, Maven Wrapper không tải được distribution hay shell bị kill, **không nhất thiết được `-fn` che đi**. Không khẳng định `-fn` khiến mọi lỗi hệ điều hành trở thành mã `0`.

### 3.1. Tại sao không nói mọi lỗi đều trả chính xác 1?

Maven và wrapper có thể trả các mã lỗi khác nhau tùy tầng lỗi, môi trường hoặc tín hiệu dừng. Đối với CI gate, điều quan trọng là **zero hay nonzero**. Các đoạn ví dụ ghi “thường 1” chỉ phản ánh lỗi unit test thông thường, không phải quy tắc tất định cho mọi lỗi khởi động/CLI/JVM.

### 3.2. -ff là mặc định

Hai lệnh sau có cùng lựa chọn Reactor failure policy mặc định:

~~~bash
mvn clean verify
mvn -ff clean verify
~~~

Nếu mục tiêu là phản hồi nhanh sau lỗi đầu tiên, bạn không cần thêm flag, nhưng khai `-ff` tường minh trong script có thể giúp người đọc hiểu ý định.

---

## 4. Phân tích -ff (fail-fast)

Khi module đang chạy fail, fail-fast dừng việc tiếp tục build reactor. Với build **nối tiếp**, những module đứng sau chưa bắt đầu thường bị đánh dấu `SKIPPED`.

Ví dụ:

~~~text
root POM       SUCCESS
math-core      FAILURE  <-- gặp test failure
math-cli       SKIPPED
audit-tool     SKIPPED

Process exit: nonzero
~~~

Audit-tool không phụ thuộc math-core nhưng vẫn có thể chưa chạy, vì `-ff` **dừng reactor**, không chỉ dừng riêng nhánh phụ thuộc.

### Lúc nào hợp lý?

- Developer chạy local, muốn thấy lỗi đầu tiên càng nhanh càng tốt.
- Project rất lớn, phần còn lại ít có giá trị khi module hạ tầng đã fail.
- CI job ưu tiên tốc độ fail-first và không cần gom lỗi độc lập vào cùng lần chạy.

### Lúc nào chưa đủ?

Nếu monorepo có nhiều module độc lập và một lỗi sớm che hết kết quả những module khác, bạn phải sửa lỗi rồi chạy lại mới biết còn lỗi khác. Trong trường hợp muốn nhiều diagnostics, `-fae` hữu ích hơn.

---

## 5. Phân tích -fae (fail-at-end)

`-fae` giữ thông tin project failure nhưng tiếp tục các phần reactor **không bị ảnh hưởng bởi module lỗi**.

~~~text
root POM       SUCCESS
math-core      FAILURE
math-cli       SKIPPED (dependency vào core lỗi)
audit-tool     SUCCESS (độc lập)

Process exit: nonzero
~~~

**Fail at end không có nghĩa “build sẽ thành công vào cuối”.** Nghĩa đúng: các module độc lập có thể được thử, và kết quả toàn reactor vẫn thất bại nếu có failure.

### Vì sao math-cli bị skip?

Math-cli có một dependency edge vào math-core. Khi math-core fail, Reactor không coi artifact/source của core là một thành phần đã build thành công để dùng cho downstream. Vì vậy `-fae` có thể skip math-cli. Đây là hành vi đúng và an toàn: không báo rằng math-cli đã qua kiểm thử khi đầu vào bắt buộc bị lỗi.

### Vì sao audit-tool vẫn chạy?

Không có dependency edge tới math-core hoặc math-cli. Nó là một nhánh khả thi, nên `-fae` tiếp tục build và kiểm thử audit-tool.

### Lợi ích cho CI

`mvn -fae clean verify` thường là lựa chọn tốt cho monorepo: **nhiều module độc lập cùng báo cáo lỗi trong một lần**, nhưng job vẫn có exit code nonzero để chặn merge/deploy nếu project quan trọng chưa đạt.

---

## 6. Phân tích -fn (fail-never)

`-fn` được thiết kế để **không để kết quả thất bại của project/module làm Maven process báo lỗi**. Khi có build failures trong reactor, exit code có thể bằng `0`.

~~~text
root POM       SUCCESS
math-core      FAILURE
math-cli       được thử build dù phụ thuộc core
audit-tool     được thử build

Process exit: 0 đối với reactor failures
~~~

**Maven vẫn có thể ghi log và Reactor Summary có FAILURE.** `-fn` không chữa Java syntax, assertion, dependency resolution hoặc artifacts.

Khác biệt tinh tế giữa `-fae` và `-fn`: tài liệu Maven ghi nhận fail-never vẫn **cố chạy dependent projects**, trong khi fail-at-end thường không chạy những projects bị ảnh hưởng. Nếu core fail ở phase test, các compiled classes có thể đã có, nhưng JAR chưa được package trong invocation đó. Kết quả math-cli sau đó có thể thay đổi tùy reactor workspace và dependency resolution; có thể build được, cũng có thể fail.

### Nguy cơ chính

Nếu CI chỉ kiểm tra numeric exit code thì một job sử dụng `-fn` có thể **báo SUCCESS dù Surefire/Failsafe tests FAIL**. Bởi vậy:

- Không dùng `-fn` làm gate chính của PR/release.
- Không xem process `0` là bằng chứng mọi modules SUCCESS khi thấy `-fn`.
- Nếu thật sự cần best-effort diagnostics, phải có một quality gate **độc lập và bắt buộc** xác nhận reports và build state.

### Khi nào có thể chấp nhận?

Lệnh chẩn đoán, thu thập thông tin nhiều module, hoặc job phụ chỉ thu reports và không quyết định chất lượng sản phẩm. Với job cần “thu nhiều lỗi và vẫn fail”, ưu tiên **`-fae`**.

---

## 7. Bài thực hành: ba module và hai công tắc lỗi JUnit

Dựng một project Java 17 có dependency graph rõ:

~~~text
reactor-failure-demo/
├── pom.xml
├── math-core/
│   ├── pom.xml
│   └── src/
│       ├── main/java/vn/example/reactor/math/Calculator.java
│       └── test/java/vn/example/reactor/math/CalculatorTest.java
├── math-cli/
│   ├── pom.xml
│   └── src/main/java/vn/example/reactor/cli/CliApp.java
└── audit-tool/
    ├── pom.xml
    └── src/
        ├── main/java/vn/example/reactor/audit/AuditApp.java
        └── test/java/vn/example/reactor/audit/AuditTest.java
~~~

Tạo đúng **9 files**: 4 POM và 5 Java files. `math-cli` khai dependency trực tiếp vào `math-core`; `audit-tool` hoàn toàn độc lập với hai module này.

Hai properties điều khiển lỗi:

- `demo.fail.core=false`: mặc định math-core test pass; đổi `true` để tạo một JUnit assertion failure ở core.
- `demo.fail.audit=false`: mặc định audit-tool tests pass; đổi `true` để tạo một JUnit assertion failure ở audit.

Đây là cách tái hiện đáng tin hơn việc cố ý phá syntax của một file Java: bạn có thể chọn đúng failure và khôi phục bằng một CLI property. Các bài thực hành **không cần sửa code** sau khi đã tạo project.

Yêu cầu: Maven 3.9.x, JDK 17+, Maven repository có thể tải plugins/JUnit, terminal đặt tại thư mục `reactor-failure-demo`.

---

## 8. Root POM hoàn chỉnh

File `reactor-failure-demo/pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>vn.example.reactor</groupId>
    <artifactId>reactor-failure-demo</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>

    <modules>
        <module>math-core</module>
        <module>math-cli</module>
        <module>audit-tool</module>
    </modules>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <demo.fail.core>false</demo.fail.core>
        <demo.fail.audit>false</demo.fail.audit>
    </properties>

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
                <configuration>
                    <systemPropertyVariables>
                        <demo.fail.core>${demo.fail.core}</demo.fail.core>
                        <demo.fail.audit>${demo.fail.audit}</demo.fail.audit>
                    </systemPropertyVariables>
                </configuration>
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

Đây là POM root **đầy đủ**. Child POMs có `<parent>` chỉ vào root để kế thừa Java 17 và plugin versions. Maven default lifecycle cho `jar` packaging sử dụng compiler/Surefire/JAR goals ở phase tương ứng.

`<systemPropertyVariables>` truyền hai Maven properties sang JVM thực thi JUnit. Vì vậy `Boolean.getBoolean("demo.fail.core")` trong test đọc được giá trị từ command `-Ddemo.fail.core=true`. Maven Surefire 3.5.4 cũng có khả năng promote user properties, nhưng khai tường minh ở đây giúp người học hiểu nguồn dữ liệu.

Các flags `-ff`, `-fae`, `-fn` là **Reactor CLI policy**, không phải properties trong `maven-surefire-plugin`.

---

## 9. math-core: một class Java và hai test

### math-core/pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>vn.example.reactor</groupId>
        <artifactId>reactor-failure-demo</artifactId>
        <version>1.0.0</version>
    </parent>

    <artifactId>math-core</artifactId>
    <packaging>jar</packaging>

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.4</version>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
~~~

### math-core/src/main/java/vn/example/reactor/math/Calculator.java

~~~java
package vn.example.reactor.math;

public final class Calculator {
    private Calculator() {
    }

    public static int add(int a, int b) {
        return Math.addExact(a, b);
    }
}
~~~

### math-core/src/test/java/vn/example/reactor/math/CalculatorTest.java

~~~java
package vn.example.reactor.math;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;

import org.junit.jupiter.api.Test;

class CalculatorTest {
    @Test
    void addsTwoNumbers() {
        assertEquals(5, Calculator.add(2, 3));
    }

    @Test
    void optionalFailureSwitch() {
        assertFalse(
                Boolean.getBoolean("demo.fail.core"),
                "Intentional math-core failure"
        );
    }
}
~~~

Với `demo.fail.core=false`, **cả hai test pass**. Khi truyền `-Ddemo.fail.core=true`, method `optionalFailureSwitch` FAIL với assertion rõ ràng, trong khi `addsTwoNumbers` vẫn pass.

Lỗi này xuất hiện ở goal `surefire:test`, sau compile và test-compile, nhưng trước phase package của module core. Vì vậy đừng mặc định binary `math-core-1.0.0.jar` đã được tạo trong chính lần build bị lỗi.

---

## 10. math-cli: module phụ thuộc core

### math-cli/pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>vn.example.reactor</groupId>
        <artifactId>reactor-failure-demo</artifactId>
        <version>1.0.0</version>
    </parent>

    <artifactId>math-cli</artifactId>
    <packaging>jar</packaging>

    <dependencies>
        <dependency>
            <groupId>vn.example.reactor</groupId>
            <artifactId>math-core</artifactId>
            <version>1.0.0</version>
        </dependency>
    </dependencies>
</project>
~~~

### math-cli/src/main/java/vn/example/reactor/cli/CliApp.java

~~~java
package vn.example.reactor.cli;

import vn.example.reactor.math.Calculator;

public final class CliApp {
    private CliApp() {
    }

    public static void main(String[] args) {
        System.out.println("sum=" + Calculator.add(2, 3));
    }
}
~~~

`math-cli` có compile dependency thực sự vào `math-core`. Nó không có JUnit test riêng, nên trong baseline build thường báo “No tests to run” ở module này.

Sau khi **toàn bộ build thành công**, chạy trên Linux/macOS:

~~~bash
java -cp "math-cli/target/classes:math-core/target/classes" vn.example.reactor.cli.CliApp
~~~

Trên Windows CMD/PowerShell:

~~~bat
java -cp "math-cli\target\classes;math-core\target\classes" vn.example.reactor.cli.CliApp
~~~

Stdout của cả hai (khi classpath đúng):

~~~text
sum=5
~~~

Đây là kết quả của Java main, **không phải log được Maven tự in trong `mvn verify`**.

---

## 11. audit-tool: module độc lập có hai test

### audit-tool/pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>vn.example.reactor</groupId>
        <artifactId>reactor-failure-demo</artifactId>
        <version>1.0.0</version>
    </parent>

    <artifactId>audit-tool</artifactId>
    <packaging>jar</packaging>

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.4</version>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
~~~

### audit-tool/src/main/java/vn/example/reactor/audit/AuditApp.java

~~~java
package vn.example.reactor.audit;

public final class AuditApp {
    private AuditApp() {
    }

    public static String message() {
        return "AUDIT_OK";
    }

    public static void main(String[] args) {
        System.out.println(message());
    }
}
~~~

### audit-tool/src/test/java/vn/example/reactor/audit/AuditTest.java

~~~java
package vn.example.reactor.audit;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;

import org.junit.jupiter.api.Test;

class AuditTest {
    @Test
    void auditMessageIsStable() {
        assertEquals("AUDIT_OK", AuditApp.message());
    }

    @Test
    void optionalAuditFailureSwitch() {
        assertFalse(
                Boolean.getBoolean("demo.fail.audit"),
                "Intentional audit-tool failure"
        );
    }
}
~~~

Hai test PASS khi `demo.fail.audit=false`. Có thể tạo failure độc lập bằng `-Ddemo.fail.audit=true`. Audit-tool **không khai dependency** vào core hoặc CLI, nên `-fae` có lý do để chạy nó khi core fail.

Sau baseline build thành công:

~~~bash
java -cp audit-tool/target/classes vn.example.reactor.audit.AuditApp
~~~

Stdout chính xác:

~~~text
AUDIT_OK
~~~

---

## 12. Baseline: không có lỗi

Tại root reactor:

~~~bash
mvn -version
java -version
mvn clean verify
~~~

Nếu source/POM đúng, JDK phù hợp và Maven đã resolve các artifacts, kết quả mong đợi:

~~~text
reactor-failure-demo ...... SUCCESS
math-core ................. SUCCESS
math-cli .................. SUCCESS
audit-tool ................ SUCCESS

BUILD SUCCESS
~~~

Tổng JUnit tests thực sự của project mẫu:

~~~text
math-core:  2 tests, 0 failures
math-cli:   0 tests
audit-tool: 2 tests, 0 failures
total:      4 tests, 0 failures
~~~

Các dòng trên là **tóm tắt dự kiến**, không phải stdout bắt buộc có đúng dấu chấm/số khoảng trắng. Mã thoát của một baseline Maven thành công thông thường là `0`.

### Tại sao chạy baseline trước?

Nó xác nhận các module/POM/dependency đang hợp lệ trước khi kiểm thử chính sách thất bại. Nếu ngay baseline đã lỗi tải JUnit, sai JDK hoặc typo Java, các kết quả sau không còn chỉ phản ánh ý định `-Ddemo.fail.core=true`.

`clean` giúp giảm nhầm lẫn output cũ trong `target`, nhưng không xóa local repository `~/.m2`.

---

## 13. Thí nghiệm 1: core fail với -ff

~~~bash
mvn -ff "-Ddemo.fail.core=true" clean verify
~~~

Trong math-core, `Boolean.getBoolean("demo.fail.core")` trả true, nên một assertion FAIL. Với Reactor **nối tiếp**, dự kiến:

~~~text
reactor-failure-demo ...... SUCCESS
math-core ................. FAILURE
math-cli .................. SKIPPED
audit-tool ................ SKIPPED

BUILD FAILURE
~~~

Maven process trả **nonzero** (thường `1`).

Giải thích:

- Root parent/aggregator đã được xử lý.
- Math-core fail tại Surefire test phase.
- Fail-fast ngừng reactor; math-cli và audit-tool chưa được build.
- Audit-tool tuy độc lập nhưng vẫn `SKIPPED` vì policy dừng sớm, không phải vì nó có dependency vào core.

Kiểm tra report `math-core/target/surefire-reports/TEST-vn.example.reactor.math.CalculatorTest.xml` để xác nhận 2 tests, 1 failure, 0 errors. Report phải thuộc lần chạy hiện tại.

---

## 14. Thí nghiệm 2: core fail với -fae

~~~bash
mvn -fae "-Ddemo.fail.core=true" clean verify
~~~

Với cùng failure và không có lỗi audit, dự kiến:

~~~text
reactor-failure-demo ...... SUCCESS
math-core ................. FAILURE
math-cli .................. SKIPPED
audit-tool ................ SUCCESS

BUILD FAILURE
~~~

Exit vẫn **nonzero** (thường `1`).

**So với -ff:** audit-tool đã được kiểm thử dù math-core fail. Math-cli bị skip vì có dependency vào core. Như vậy `-fae` thu thêm diagnostics nhưng **không thay đổi đánh giá rằng toàn bộ reactor thất bại**.

Đây là lựa chọn hợp lý khi PR/CI cần nhìn thấy lỗi ở nhiều module độc lập trong cùng một lượt chạy, nhưng vẫn phải chặn merge nếu còn lỗi.

---

## 15. Thí nghiệm 3: core fail với -fn

~~~bash
mvn -fn "-Ddemo.fail.core=true" clean verify
~~~

Phần có thể khẳng định cho lỗi module thông thường:

~~~text
reactor-failure-demo ...... SUCCESS
math-core ................. FAILURE
math-cli .................. Reactor cố thử build
audit-tool ................ Reactor cố thử build

Maven process exit: 0
~~~

**Không hardcode trạng thái math-cli thành SUCCESS.** Khi core fail ở phase test, class output đã compile có thể có nhưng main JAR chưa được tạo trong lần build; reactor workspace/local repository có thể ảnh hưởng việc math-cli resolve dependency. Math-cli có thể fail tiếp, hoặc đi xa hơn nếu đầu vào đã có. Dù thế nào, **math-core đã FAIL**.

Điều cần tự kiểm chứng:

1. Báo cáo Surefire của core ghi 1 test failure.
2. Reactor Summary/log có dòng project failure.
3. Shell nhận numeric exit code `0` do `-fn`.
4. Nếu dùng công cụ CI chỉ nhìn exit status, job có thể xanh giả.

`-fn` không biến assertion false thành true và không bảo đảm toàn bộ JAR/reports đã tồn tại. Không dùng trong release gate.

---

## 16. Ma trận kết quả khi chỉ core có lỗi

Giả sử chạy root reactor nối tiếp, `demo.fail.core=true`, `demo.fail.audit=false`:

| Module | `-ff` | `-fae` | `-fn` |
| --- | --- | --- | --- |
| Root POM | SUCCESS | SUCCESS | SUCCESS |
| Math-core | FAILURE | FAILURE | FAILURE |
| Math-cli phụ thuộc core | SKIPPED | SKIPPED | Được thử; có thể thành công hoặc thất bại |
| Audit-tool độc lập | SKIPPED | SUCCESS | Được thử, thường SUCCESS |
| Process exit | Nonzero | Nonzero | **0** đối với reactor failure |
| Có thể coi là full pass? | Không | Không | **Không** |

Khi tất cả modules PASS, ba flags thường đều trả `0`. Khi thất bại, sự khác biệt trọng tâm là **phạm vi tiếp tục** và **mã thoát**.

### Thí nghiệm 4: hai lỗi độc lập với -fae

~~~bash
mvn -fae "-Ddemo.fail.core=true" "-Ddemo.fail.audit=true" clean verify
~~~

Kỳ vọng:

~~~text
reactor-failure-demo ...... SUCCESS
math-core ................. FAILURE
math-cli .................. SKIPPED
audit-tool ................ FAILURE

BUILD FAILURE
~~~

Trong một lần chạy, bạn thấy failure của cả `CalculatorTest` và `AuditTest`. Exit vẫn nonzero. Với `-ff`, audit thường bị skip trước khi lỗi audit có cơ hội xuất hiện.

---

## 17. Kiểm tra mã thoát bằng Bash

Ngay sau Maven command trong Bash, `$?` là exit code của command vừa kết thúc.

~~~bash
mvn -fae "-Ddemo.fail.core=true" clean verify
status=$?
printf 'exit_code=%s\n' "$status"
~~~

Kết quả `status` thường khác `0`. Với `-fn`:

~~~bash
mvn -fn "-Ddemo.fail.core=true" clean verify
status=$?
printf 'exit_code=%s\n' "$status"
~~~

Trong tình huống reactor failure được `-fn` xử lý, dòng `printf` cho stdout **chính xác**:

~~~text
exit_code=0
~~~

**Lưu ngay `$?`:** nếu chạy `echo` hoặc command khác trước khi lấy status, `$?` đã trở thành mã của command mới.

### 17.1. Bash set -e

Khi script có `set -e`, Maven failure có thể làm script dừng sớm, trước khi bạn kịp thu logs. Cách bắt lỗi mà vẫn trả đúng code:

~~~bash
if mvn -fae "-Ddemo.fail.core=true" clean verify; then
    status=0
else
    status=$?
fi

printf 'Maven returned %s\n' "$status"

# Có thể upload reports vào CI ở đây.
exit "$status"
~~~

Cách này không biến failure thành pass. `exit "$status"` chuyển lại tín hiệu lỗi của Maven cho caller.

### 17.2. Khi dùng tee

~~~bash
mvn -fae "-Ddemo.fail.core=true" clean verify | tee reactor.log
~~~

Ở Bash mặc định, exit của pipeline có thể là exit của `tee`, làm mất lỗi Maven. Có thể dùng:

~~~bash
set -o pipefail
mvn -fae "-Ddemo.fail.core=true" clean verify | tee reactor.log
status=$?
printf 'pipeline_exit=%s\n' "$status"
~~~

`pipefail` làm pipeline báo nonzero khi có thành phần thất bại. Nếu cần exit của **riêng Maven** khi nhiều thành phần trong pipe có thể fail, Bash còn có `PIPESTATUS`; đọc nó ngay sau pipeline, trước bất kỳ command nào khác.

**Lưu ý:** không có cách shell `pipefail` nào làm `-fn` trở thành một gate an toàn nếu chính Maven đã cố tình trả `0` cho reactor failure.

---

## 18. PowerShell và CMD: đọc đúng native exit

### PowerShell

~~~powershell
mvn -fae '-Ddemo.fail.core=true' clean verify
$code = $LASTEXITCODE
Write-Output "exit_code=$code"
~~~

Với `-fn`:

~~~powershell
mvn -fn '-Ddemo.fail.core=true' clean verify
$code = $LASTEXITCODE
Write-Output "exit_code=$code"
~~~

Nếu lỗi module được `-fn` xử lý, stdout của dòng cuối là:

~~~text
exit_code=0
~~~

`$LASTEXITCODE` biểu thị mã thoát của native executable. Đừng dựa vào `$?` sau khi đã chạy thêm PowerShell cmdlets, vì nó phản ánh trạng thái hoạt động PowerShell và dễ bị thay đổi.

Trong PowerShell CI script:

~~~powershell
mvn -fae clean verify
$buildCode = $LASTEXITCODE
Write-Output "Maven exit: $buildCode"
exit $buildCode
~~~

### Windows CMD

~~~bat
mvn -fae "-Ddemo.fail.core=true" clean verify
echo exit_code=%ERRORLEVEL%
~~~

Với `-fn`:

~~~bat
mvn -fn "-Ddemo.fail.core=true" clean verify
echo exit_code=%ERRORLEVEL%
~~~

Nếu Maven bỏ qua reactor failure, kết quả mong đợi `exit_code=0`. Trong các file batch dùng ngoặc/phép mở rộng biến, `%ERRORLEVEL%` có thể được expand trước khi command chạy; ví dụ là cách chạy tuần tự trực tiếp trong CMD terminal. Với batch scripts phức tạp, dùng biến và delayed expansion đúng ngữ cảnh.

### Maven Wrapper

Khi repository có Maven Wrapper, có thể dùng `./mvnw` hoặc `mvnw.cmd`. Wrapper vẫn phải chuyển exit code phù hợp cho terminal. Tuy nhiên lỗi tải Maven distribution/khởi động JVM xảy ra **trước reactor** không thuộc phạm vi mà `-fn` cam kết che.

---

## 19. -pl, -am, -amd: chọn module không đồng nghĩa chọn failure policy

Những lựa chọn sau quyết định **phạm vi reactor**, không trực tiếp thay đổi `-ff/-fae/-fn`:

| Flag | Mục đích |
| --- | --- |
| `-pl` / `--projects` | Chọn một số project/module |
| `-am` / `--also-make` | Thêm những reactor dependencies của modules đã chọn |
| `-amd` / `--also-make-dependents` | Thêm những modules phụ thuộc vào selected modules |
| `-rf` / `--resume-from` | Bắt đầu lại từ một module trong reactor |
| `-N` / `--non-recursive` | Chỉ build project hiện tại, không đệ quy child modules |
| `-T` | Chọn mức song song; không phải failure policy |

### Chọn riêng audit-tool

~~~bash
mvn -pl :audit-tool clean verify
~~~

Câu lệnh chỉ chọn audit-tool. Dù truyền `-Ddemo.fail.core=true`, core test **không được chạy** nếu math-core không nằm trong selected reactor. Build audit PASS **không** chứng minh math-core PASS.

### Chọn CLI cùng core dependency

~~~bash
mvn -pl :math-cli -am clean verify
~~~

`-am` đưa math-core vào phần build cần thiết. Nếu thêm property làm core test fail và dùng `-fae`, math-cli có thể bị skip. `-am` không làm core failure biến mất.

### Chọn core và các dependents

~~~bash
mvn -pl :math-core -amd clean verify
~~~

`-amd` kéo math-cli vào vì phụ thuộc core, không nhất thiết kéo audit-tool. Một lần chạy phạm vi hẹp không thể được tuyên bố là “cả monorepo đã PASS”.

### Build chỉ CLI mà thiếu dependency

~~~bash
mvn -pl :math-cli clean verify
~~~

Nếu math-core chưa install vào local repo và không có trong selected reactor, command có thể fail vì unresolved dependency. Đó là lỗi **selection/dependency resolution**, không tự động là failure từ test core.

---

## 20. -rf / --resume-from và artifacts cũ

Sau một reactor build failed, Maven có thể gợi ý resume từ module bị lỗi. Ví dụ:

~~~bash
mvn -rf :math-core clean verify
~~~

`-rf` không có nghĩa sửa lỗi hay bỏ qua kiểm thử. Nó thay đổi phần reactor được chạy tiếp theo. Với Maven 3, các module đứng trước điểm resume có thể không được build lại, do đó một dependency/parent artifact chưa install vào local repository có thể không resolve khi build lại.

Lời khuyên:

- Sửa nguyên nhân test/build failure trước.
- Với demo nhỏ, chạy lại **full `mvn clean verify`** để tránh lệch trạng thái.
- Với hệ thống lớn, dùng `-pl`/`-am` hoặc `-rf` khi hiểu rõ dependency graph, trạng thái artifact và các module chưa verify.
- Không đánh dấu full reactor pass chỉ vì một run resume chạy thành công trên một phần modules.

Một success sau resume có thể chỉ chứng minh những modules trong phạm vi resume đã đạt.

---

## 21. -T song song và thứ tự log

Với reactor song song:

~~~bash
mvn -T 2 -fae clean verify
~~~

Các modules độc lập có thể chạy đồng thời. Nếu math-core fail, audit-tool có thể đã được scheduler khởi động. Dưới `-ff` song song, “dừng tại lỗi đầu tiên” không có nghĩa mọi module đã chạy bị kill tức thời. Vì thế:

- Không dùng thứ tự in log làm bản đồ dependency duy nhất.
- Đọc Reactor Summary, module graph, báo cáo test và exit status.
- Khi cần minh họa dễ dự đoán, chạy **nối tiếp, không có `-T`**.
- Nếu parallel tests tranh cổng/database/temporary files, đó là rủi ro concurrency/isolation riêng, không phải lý do để bật `-fn`.

Chính sách exit code của `-fn` vẫn nguy hiểm với CI kể cả khi build chạy song song.

---

## 22. Phân biệt Reactor policy với bỏ qua test failure

| Flag/property | Tầng ảnh hưởng | Hệ quả |
| --- | --- | --- |
| `-ff` | Reactor | Dừng sớm khi module failure |
| `-fae` | Reactor | Cố chạy modules không bị ảnh hưởng, vẫn trả lỗi |
| `-fn` | Reactor/process result | Không trả lỗi chỉ vì reactor project failures |
| `-DskipTests` | Surefire/test execution | Thường vẫn compile test nhưng **không chạy** |
| `-Dmaven.test.skip=true` | Test compile/execution | Thường bỏ cả compile và chạy test |
| `-Dmaven.test.failure.ignore=true` | Surefire test goal | Có thể không biến assertion failure thành module failure |
| `-Dtest=SomeTest` | Surefire | Lọc class/method được thực thi |

Ví dụ:

~~~bash
mvn -fae -DskipTests "-Ddemo.fail.core=true" clean verify
~~~

Command này không còn kiểm chứng property failure như các thí nghiệm vì test có thể không được thực thi. Nếu core không fail, nguyên nhân là **test bị skip**, không phải `-fae` đã làm assertion đúng.

Tương tự:

~~~bash
mvn -ff "-Dmaven.test.failure.ignore=true" "-Ddemo.fail.core=true" verify
~~~

có thể ghi JUnit failures nhưng plugin không trả goal failure như cấu hình mặc định. Reactor policy chỉ phản ứng khi Maven coi project/module đã fail.

Không dùng các skip/ignore flags để làm đẹp CI; phải xác nhận **số test đã chạy** và **số failures/errors** trong reports.

---

## 23. Khi nào dùng policy nào trong thực tế?

### Local development: ưu tiên phản hồi nhanh

~~~bash
mvn -ff clean test
~~~

Phù hợp nếu muốn biết lỗi đầu tiên và sửa dần. Tuy nhiên nó không luôn thu được lỗi của các module khác.

### Pull request / merge gate: thu nhiều lỗi nhưng giữ exit nonzero

~~~bash
mvn -fae clean verify
~~~

Giúp chạy những nhánh độc lập, thu reports, và vẫn fail job nếu có project failure. Đây thường là lựa chọn tốt cho reactor nhiều modules. Nhưng nếu một module bị SKIPPED vì upstream fail, PR chưa thể coi đã đủ coverage.

### Diagnostics best-effort không quyết định merge/deploy

~~~bash
mvn -fn clean verify
~~~

Chỉ cân nhắc khi một bước độc lập cần tiếp tục thu thông tin và có cơ chế riêng để báo cáo failures. Đừng để exit `0` của nó được CI dùng làm chứng cứ các modules đã đạt.

### Release pipeline

Không dùng `-fn` để hợp thức hóa artifact chưa được verify. Khi release, cần biết chính xác module nào SUCCESS, module nào SKIPPED, test reports, versions và artifacts thuộc cùng source revision. Một ZIP/JAR đã được tạo ra không chứng minh toàn bộ release đạt quality gates.

---

## 24. Bẫy khi xử lý exit code trong pipeline

### Bẫy 1: lệnh khác ghi đè status

~~~bash
mvn -fae "-Ddemo.fail.core=true" clean verify
echo "finished"
status=$?
~~~

`status` là exit của `echo`, không phải của Maven. Sửa bằng cách đọc `$?` ngay sau Maven.

### Bẫy 2: pipeline tee làm mất lỗi

~~~bash
mvn -fae clean verify | tee reactor.log
~~~

Trên Bash khi không dùng pipefail, status pipeline có thể phản ánh `tee` chứ không phải Maven. Bật `set -o pipefail` khi cần CI nhận failure của Maven.

### Bẫy 3: cố trả exit 0 để upload reports

~~~bash
mvn -fae clean verify
exit 0
~~~

Lệnh này biến cả build thất bại thành script success. Thay vào đó, bắt status, thu report (nếu có) và cuối cùng `exit "$status"`.

### Bẫy 4: grep BUILD FAILURE thay vì xem exit/reports

Text log có thể thay đổi theo Maven/plugin version, chứa nhiều module output hoặc bị cắt. Quality gate nên dùng numeric exit code và các test XML reports có cấu trúc, không dựa duy nhất vào grep.

### Bẫy 5: tin exit 0 của -fn

Kể cả cách thu status đúng hoàn toàn, nếu policy được yêu cầu là `-fn` thì giá trị `0` có thể chỉ có nghĩa Maven đã **bỏ qua reactor failure khi quyết định process status**. Shell không thể đoán ý định khác. Cách đơn giản nhất để có CI gate đúng là **không dùng -fn cho gate**.

---

## 25. Một số lỗi thường gặp khi thực hành

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Không tái hiện core failure | Không truyền đúng `-Ddemo.fail.core=true` hoặc Surefire không chạy test | Xem CLI, Surefire report và POM system properties |
| `-ff` skip audit-tool dù audit độc lập | Fail-fast dừng trước khi audit chạy | Dùng `-fae` nếu cần diagnostics |
| `-fae` skip math-cli | math-cli phụ thuộc core failed | Sửa core, chạy lại; skip là đúng dependency behavior |
| `-fae` exit nonzero dù audit SUCCESS | core vẫn FAILURE | Không đổi thành pass |
| `-fn` exit 0 dù core test FAIL | Chính sách fail-never | Không dùng cho CI gate |
| `-fn` thử CLI nhưng fail tiếp | Core artifact/classes thiếu hoặc lỗi dependency | Xem compile/resolver logs; -fn không chữa lỗi |
| `-fn` thử CLI và success | Đủ input từ reactor/cache | Core test vẫn fail, không coi full reactor pass |
| Không có core test report | Module chưa được chọn hoặc test bị skip | Kiểm tra -pl/-am/-DskipTests |
| Failures từ compiler thay vì test | Java source/POM lỗi | Sửa đúng nguyên nhân, không thay policy mù quáng |
| Full build success dù test assertion fail | Có test failure ignore/skip flag | Loại bỏ bypass trước CI QA |
| `-rf` không resolve modules | Artifact trước điểm resume chưa install | Build lại dependencies/full reactor |
| `-T` thay đổi thứ tự module log | Scheduling song song | Đọc graph và Reactor Summary |
| CI xanh sau Maven fail | Shell script nuốt exit hoặc dùng -fn | Lưu và trả lại mã Maven, dùng -fae |
| PowerShell báo status lạ | Nhầm `$?` với `$LASTEXITCODE` | Đọc numeric native exit ngay sau Maven |
| Local chạy được nhưng CI fail | JDK, profile, repository, cache khác | Ghi môi trường, dùng Maven Wrapper và build sạch |
| Module SKIPPED bị coi là PASSED | Diễn giải báo cáo sai | Kiểm tra module coverage thật |

### Quy trình chẩn đoán sáu bước

1. Ghi nguyên command, Maven/JDK versions, failure policy, selected modules, profiles và skip flags.
2. Xác minh dependency edges của reactor; module nào phụ thuộc module lỗi?
3. Xem plugin goal gây FAILURE: compile, test, package, verify hay resolution.
4. Đọc Reactor Summary để phân biệt SUCCESS, FAILURE, SKIPPED.
5. Xem `target/surefire-reports` và những test XML có liên quan, xác nhận test thật đã chạy.
6. Bắt numeric exit status ngay khi command kết thúc; sau khi sửa lỗi, chạy lại phạm vi đủ để verify các module bị skip.

---

## 26. Bài tập tự kiểm chứng

### Bài A — Default policy

Chạy `mvn clean verify` rồi `mvn -ff clean verify` khi không bật failure properties. Vì sao hai lần có cùng failure policy và thường trả `0`?

### Bài B — Chỉ core thất bại

~~~bash
mvn -ff "-Ddemo.fail.core=true" clean verify
~~~

Dự đoán trạng thái core/CLI/audit. Đọc nonzero exit và báo cáo `CalculatorTest`. Tại sao audit bị SKIPPED dù không phụ thuộc core?

### Bài C — Thu diagnostics độc lập

~~~bash
mvn -fae "-Ddemo.fail.core=true" clean verify
~~~

Kiểm tra audit SUCCESS nhưng CLI SKIPPED. Vì sao process vẫn trả nonzero?

### Bài D — Thử fail-never

~~~bash
mvn -fn "-Ddemo.fail.core=true" clean verify
~~~

Đọc exit `0` rồi mở Surefire XML của core. Giải thích vì sao exit zero không chứng minh core PASS. Quan sát math-cli có được thử và có thành công hay không, không dự đoán cố định trước khi kiểm tra log.

### Bài E — Hai lỗi độc lập

~~~bash
mvn -fae "-Ddemo.fail.core=true" "-Ddemo.fail.audit=true" clean verify
~~~

Dự đoán core FAILURE, audit FAILURE, CLI SKIPPED. Tại sao -fae hữu ích hơn fail-fast khi cần nhiều error reports?

### Bài F — Test phạm vi hẹp

~~~bash
mvn -pl :audit-tool "-Ddemo.fail.core=true" clean verify
~~~

Nếu audit PASS, có được kết luận core PASS không? Phân biệt module selection với failure policy.

### Bài G — Phụ thuộc với -am

~~~bash
mvn -pl :math-cli -am -fae "-Ddemo.fail.core=true" clean verify
~~~

Xác định các modules được chọn và kết quả khi core assertion fail.

### Bài H — Exit code Bash

Thử lưu `$?` ngay sau command, rồi cố tình chèn `echo` trước khi lưu status. Giải thích mã nào bị mất. Lặp lại với `tee` và `pipefail`.

### Bài I — PowerShell và CMD

Dùng `$LASTEXITCODE` trong PowerShell hoặc `%ERRORLEVEL%` trong CMD để nhận mã cuối của Maven. Tại sao không nên chèn nhiều lệnh rồi mới đọc status?

### Bài J — Thử skip tests

~~~bash
mvn -fae -DskipTests "-Ddemo.fail.core=true" clean verify
~~~

Vì sao core test không còn tạo failure như mong đợi? Phân biệt **test không chạy** và **test chạy rồi pass**.

### Bài K — Parallel reactor

Thêm `-T 2` vào thử nghiệm fail-fast. Tại sao audit có thể đã bắt đầu trước khi core failure được phát hiện? Điều gì vẫn không thay đổi về vai trò của exit code?

### Bài L — Policy cho CI

Một monorepo muốn báo tất cả lỗi độc lập nhưng vẫn phải chặn merge nếu module bất kỳ fail. Chọn `-ff`, `-fae` hay `-fn`? Giải thích cả ảnh hưởng tới downstream và numeric exit.

### Bài M — Build lại sạch

Sau khi thí nghiệm, chạy:

~~~bash
mvn "-Ddemo.fail.core=false" "-Ddemo.fail.audit=false" clean verify
~~~

Kỳ vọng mọi modules SUCCESS, **4 JUnit tests PASS** và exit `0`. Đây là trạng thái kết thúc an toàn của bài học.

---

## 27. Checklist trước khi áp dụng trong CI

- [ ] Biết Maven version và reactor modules thực tế.
- [ ] Hiểu dependency graph thay vì chỉ nhìn thứ tự tên module.
- [ ] Biết `-ff` là default và dừng sớm.
- [ ] Biết `-fae` tiếp tục các module không bị ảnh hưởng nhưng vẫn trả failure.
- [ ] Biết `-fn` có thể exit 0 dù modules/tests fail.
- [ ] Không dùng `-fn` làm quality gate duy nhất cho PR/merge/release.
- [ ] Xem `SUCCESS`, `FAILURE` và `SKIPPED` riêng, không coi SKIPPED là pass.
- [ ] Kiểm tra các module downstream bị bỏ qua sau upstream failure.
- [ ] Xác định `-pl/-am/-amd/-rf` có giới hạn phạm vi kiểm chứng không.
- [ ] Nếu chạy song song `-T`, không dựa vào thứ tự log để suy ra dependency.
- [ ] Không vô ý bật `-DskipTests` hoặc `maven.test.failure.ignore`.
- [ ] Đọc Surefire/Failsafe reports và numeric exit code của Maven.
- [ ] Script Bash/PowerShell/CMD không nuốt exit code vì lệnh sau hoặc pipeline.
- [ ] Đã chạy đủ các module cần thiết trước khi phát hành artifacts.
- [ ] Không dùng JAR cũ từ local repo làm bằng chứng một source revision mới đã verify.

**Kết luận:** `-ff` tối ưu cho **phát hiện lỗi sớm**, `-fae` cho **thu nhiều kết quả kiểm thử độc lập nhưng vẫn giữ tín hiệu thất bại**, còn `-fn` cho **best-effort run với nguy cơ che lỗi ở process exit**. Với CI cần bảo vệ chất lượng, `-fae` thường giúp lấy nhiều diagnostics mà không tạo tín hiệu xanh giả. Luôn kiểm chứng Reactor Summary, module test reports và mã thoát — ba thứ này bổ sung nhau, không thay thế nhau.

## 28. Tài liệu chính thức

- [Apache Maven — Working with Multiple Modules (Maven 3)](https://maven.apache.org/guides/mini/guide-multiple-modules.html): Reactor sorting, `-ff` mặc định, `-fae`, `-pl`, `-am`, `-rf`.
- [Apache Maven — Working with Multiple Subprojects (Maven 4)](https://maven.apache.org/guides/mini/guide-multiple-subprojects-4.html): so sánh Maven 4 và diễn giải `-fn`, lưu ý không áp dụng mọi thay đổi Maven 4 cho Maven 3.
- [Apache Maven Invoker — ReactorFailureBehavior](https://maven.apache.org/shared/maven-invoker/xref/org/apache/maven/shared/invoker/InvocationRequest.html): `FailFast`, `FailAtEnd`, `FailNever`.
- [Maven CLI Options Reference](https://svn.apache.org/repos/asf/maven/website/components/ref/3-LATEST/maven-embedder/cli.html): long/short flags và project selection.
- [Apache Maven — Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html): các phase `test`, `package`, `verify`.
- [Apache Maven — Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html): module dependencies và classpath.
- [Maven Surefire 3.5.4 — surefire:test](https://maven.apache.org/surefire-archives/surefire-3.5.4/maven-surefire-plugin/test-mojo.html): `skipTests`, `systemPropertyVariables`, `promoteUserPropertiesToSystemProperties`.
- [Maven Surefire 3.5.4 — System Properties](https://maven.apache.org/components/surefire-archives/surefire-3.5.4/maven-surefire-plugin/examples/system-properties.html): truyền giá trị `-D...` vào JUnit JVM.
- [Maven: The Complete Reference — Running Maven](https://www.sonatype.com/maven-complete-reference/running-maven): giải thích các chế độ xử lý build failures.
