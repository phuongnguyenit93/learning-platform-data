# Thực thi song song và kiểm soát tài nguyên dùng chung trong kiểm thử đơn vị Maven

## 1. Tại sao bài kiểm thử chạy tuần tự thì ổn nhưng chạy song song lại thất bại?

Bộ kiểm thử đơn vị (unit test suite) thường chạy nhiều test case độc lập. Khi tổng thời gian tăng, nhóm phát triển muốn tận dụng CPU bằng cách thực thi nhiều test cùng lúc. **Song song có thể giúp giảm thời gian build**, nhưng cũng có thể làm lộ những phụ thuộc ngầm vào trạng thái chung mà trước đây bị che khuất bởi thứ tự chạy tuần tự.

Một số triệu chứng thường gặp:

- Test A đặt một **system property**, test B đọc hoặc sửa cùng property; nếu chạy xen kẽ, kết quả khác dự kiến.
- Nhiều test cùng ghi **một file tạm có tên cố định**, làm dữ liệu bị ghi đè hoặc đọc nhầm.
- Test cùng dùng **static mutable state**, singleton, cache, mock hoặc collection không thread-safe.
- Hai test cùng chiếm **một cổng TCP**, cùng cập nhật bảng database, cùng dùng schema hoặc tài khoản thử nghiệm.
- Test thay đổi **default Locale, TimeZone, System.out/System.err**, biến môi trường mô phỏng hoặc trạng thái bên ngoài.
- Các tác vụ khởi tạo/cleanup xảy ra đồng thời, làm một test xóa dữ liệu mà test khác còn cần.
- CPU, RAM, heap, số kết nối DB hoặc giới hạn container không đủ khi cùng lúc chạy nhiều test.

Điểm chung: test vốn được viết với giả định **“mình là test duy nhất đang chạy”**. Giả định này không còn đúng khi JUnit, Surefire, Maven reactor hoặc CI tạo nhiều luồng/process.

**Mục tiêu bài học:** phân biệt các tầng song song, bật đúng chế độ cho **JUnit Jupiter**, bảo vệ tài nguyên chung bằng `@ResourceLock`, dùng `@TempDir` cho file riêng, hiểu `forkCount`/`reuseForks`/`-T`, và xây dựng một chiến lược vừa nhanh vừa đáng tin.

## 2. Có ba tầng song song khác nhau trong Maven

Một câu “cho Maven chạy test song song” có thể chỉ ba cơ chế độc lập:

| Tầng | Điều khiển bởi | Đơn vị thực thi | Ví dụ |
| --- | --- | --- | --- |
| **Test trong cùng JVM** | **JUnit Jupiter parallel execution** qua `junit-platform.properties` hoặc configuration parameters | Test class và test method | Hai phương thức test chạy trên nhiều worker threads trong một fork. |
| **Nhiều forked JVM** | **Maven Surefire Plugin** `forkCount`, `reuseForks` | Process JVM riêng | Surefire cho các test class chạy trong nhiều JVM; static state không được chia sẻ giữa các process. |
| **Nhiều module Maven** | **Maven Core** `-T` | Các module trong reactor | `mvn -T 2 verify` xử lý các module độc lập có thể chạy đồng thời. |

Còn một tầng khác là **nhiều CI jobs hoặc máy runner độc lập**. Chúng có thể cùng chạm database hay artifact server nhưng không cùng JVM, không cùng process và thường không chia sẻ local file system.

Một kiến trúc thực tế:

~~~text
CI pipeline (có thể chạy nhiều job song song)
  |
  +-- Maven reactor: -T 2
        |
        +-- module-a / Surefire forkCount=1
        |     |
        |     +-- JUnit Jupiter worker threads (parallelism=4)
        |           +-- Test A
        |           +-- Test B
        |           +-- Test C (ResourceLock)
        |
        +-- module-b / Surefire forkCount=1
              |
              +-- JUnit Jupiter worker threads (parallelism=4)
                    +-- Test D
                    +-- Test E
~~~

**Tổng mức đồng thời có thể lớn hơn con số bạn đặt ở một tầng**, vì nhiều module/fork/job đang chạy. Không nên nhìn `parallelism=4` rồi kết luận toàn bộ CI chỉ có tối đa bốn test. Số thread thực tế cũng chịu ảnh hưởng cách JUnit sử dụng ForkJoinPool.

### Tài nguyên được chia sẻ đến cấp nào?

- **Biến static, system properties, default Locale và TimeZone:** chung trong **một JVM**, không chung trực tiếp giữa các JVM khác nhau.
- **Filesystem, network port, database, container và dịch vụ từ xa:** có thể chung giữa **nhiều JVM, nhiều module, thậm chí nhiều CI jobs**.
- **`@ResourceLock` của JUnit Jupiter:** phối hợp giữa những test do **cùng một JUnit Jupiter execution engine** quản lý, sử dụng **cùng tên khóa**. Nó **không phải khóa liên tiến trình hoặc khóa phân tán**.
- **`@Execution(SAME_THREAD)`** không đồng nghĩa chiếm quyền độc quyền với mọi test của suite; nó chỉ định chế độ thực thi cho node test trong cây JUnit.

Đây là lý do một test đã có `@ResourceLock` vẫn có thể xung đột với process Surefire fork khác hoặc pipeline khác đang dùng cùng database.

## 3. Surefire thực thi unit test ở đâu trong lifecycle?

Với packaging `jar` phổ biến, khi chạy:

~~~bash
mvn test
~~~

Maven đi qua các phase đến **test**: xử lý resources chính, biên dịch mã chính, xử lý resources kiểm thử, biên dịch test, rồi chạy goal **`surefire:test`** theo lifecycle binding phù hợp.

Các đường dẫn thường gặp:

~~~text
src/main/java/              nguồn chính
src/test/java/              mã test
src/test/resources/         cấu hình test, ví dụ junit-platform.properties
target/classes/             class chính
target/test-classes/        class và resource test
target/surefire-reports/    báo cáo test
~~~

**Surefire** chọn test và gọi test framework qua provider tương ứng. Với **JUnit Jupiter**, engine của JUnit Platform quản lý cơ chế parallel execution ở tầng test method/class. Vì vậy **đừng chỉ đặt `<parallel>methods</parallel>` trong Surefire rồi cho rằng JUnit 5 đã chạy đa luồng**.

Các tùy chọn Surefire `parallel`/`threadCount` được tài liệu hóa đặc biệt cho **JUnit 4 provider và TestNG provider**; với **JUnit Platform/Jupiter**, nên điều khiển sự đồng thời của các test trong JVM qua **các cấu hình `junit.jupiter.execution.parallel.*`**.

Lưu ý: tài liệu Maven Surefire mới có thay đổi về provider mặc định theo phiên bản; nguyên tắc phân biệt **JUnit Platform controls** và **Surefire fork controls** vẫn quan trọng. Luôn đối chiếu docs theo **version Surefire** dự án thực sự sử dụng.

### Surefire và Failsafe

- **Surefire** thường chạy **unit tests** trong phase `test`.
- **Failsafe** thường chạy **integration tests** ở phase `integration-test` và kiểm tra kết quả tại phase `verify`, theo cấu hình plugin và tên test tương ứng.
- Cùng một tài nguyên DB/test server có thể bị đụng bởi unit tests và integration tests nếu build/profile cấu hình sai. Không nên lấy cấu hình parallel cho unit test rồi áp dụng hàng loạt cho integration tests có tài nguyên ngoài JVM mà chưa kiểm tra.

## 4. JUnit Jupiter mặc định không tự song song

Trong JUnit 5/Jupiter, **parallel execution là tính năng opt-in**. Để bật, trước hết đặt:

~~~properties
junit.jupiter.execution.parallel.enabled=true
~~~

Nhưng **chỉ có dòng đó chưa đủ để mọi test chạy đồng thời**. JUnit còn có execution mode:

- **`SAME_THREAD`**: chạy test trên luồng liên quan đến parent node, thường dùng cho chế độ tuần tự.
- **`CONCURRENT`**: cho phép chạy đồng thời nếu các ràng buộc lifecycle và resource locks không ngăn.

Cách chọn mode thường gặp:

~~~properties
junit.jupiter.execution.parallel.enabled=true
junit.jupiter.execution.parallel.mode.default=concurrent
junit.jupiter.execution.parallel.mode.classes.default=concurrent
~~~

Đặt file **`src/test/resources/junit-platform.properties`** để JUnit Platform đọc khi chạy test. Có thể cấu hình tham số tương ứng qua Surefire `configurationParameters`, nhưng **không nên khai báo mâu thuẫn cùng tham số ở nhiều nơi** rồi không biết nguồn nào được ưu tiên.

### Có thể chỉ bật một phần của suite

Nếu chưa sẵn sàng chạy mọi test đồng thời, có thể giữ default `same_thread` rồi đánh dấu những test class an toàn bằng:

~~~java
import org.junit.jupiter.api.parallel.Execution;
import static org.junit.jupiter.api.parallel.ExecutionMode.CONCURRENT;

@Execution(CONCURRENT)
class IndependentTest {
    // Các test ở đây cần thật sự độc lập và thread-safe.
}
~~~

Đây là **đoạn Java minh họa**, chưa phải file test độc lập. `@Execution(CONCURRENT)` không thay thế yêu cầu `junit.jupiter.execution.parallel.enabled=true`.

Với class dùng `@TestInstance(PER_CLASS)` hoặc method ordering như `@TestMethodOrder`, JUnit Jupiter có những quy tắc bảo thủ về thực thi đồng thời. Nếu muốn cố chạy concurrent, có thể cần `@Execution(CONCURRENT)`, nhưng **phải bảo đảm instance fields và lifecycle methods an toàn** trước; đừng dùng annotation để ép song song khi test vẫn chia sẻ state mutable.

## 5. Giới hạn mức song song: fixed, dynamic và tài nguyên thực tế

JUnit Jupiter có cơ chế cấu hình **parallel execution strategy**, thường dùng:

- **`fixed`**: đặt desired parallelism trực tiếp.
- **`dynamic`**: tính từ số CPU được báo cho JVM và một factor cấu hình.
- **`custom`**: dùng một strategy riêng nếu tổ chức có yêu cầu đặc biệt.

Ví dụ bảo thủ cho một module thử nghiệm:

~~~properties
junit.jupiter.execution.parallel.enabled=true
junit.jupiter.execution.parallel.mode.default=concurrent
junit.jupiter.execution.parallel.mode.classes.default=concurrent
junit.jupiter.execution.parallel.config.strategy=fixed
junit.jupiter.execution.parallel.config.fixed.parallelism=2
~~~

**`parallelism=2` là mức song song mong muốn, không phải bảo đảm cứng rằng toàn bộ JVM chỉ có hai thread**. JUnit Jupiter sử dụng ForkJoinPool; khi gặp những hoạt động chờ/synchronization, số thread thực tế có thể vượt mức parallelism. Phiên bản JUnit 5 phù hợp còn cung cấp tham số như `junit.jupiter.execution.parallel.config.fixed.max-pool-size` nếu cần giới hạn pool threads; dùng cẩn trọng với test có blocking logic để tránh starvation/deadlock.

Trong CI, việc tăng parallelism **không luôn nhanh hơn**:

- Test nhiều CPU có thể tranh nhau core.
- Test nhiều I/O có thể làm nghẽn DB, disk hoặc mạng.
- Nhiều thread làm tăng stack/memory, thread scheduling và áp lực GC.
- Nhiều Surefire forks đồng thời làm tăng nhiều heap JVM và classloaders.
- Đôi khi overhead setup/cleanup lớn hơn thời gian test.

**Đo trước, điều chỉnh sau.** Chọn mức song song nhỏ, đo tổng thời gian test, p95/độ biến thiên, flakiness, CPU/RAM, và khả năng chịu tải của DB/mock services; nâng dần nếu suite thực sự hưởng lợi.

## 6. Mẫu dự án Java 17/JUnit Jupiter hoàn chỉnh

Bài thực hành dùng **JDK 17+, Maven 3.x tương thích với các phiên bản plugin được chốt**, và JUnit Jupiter `5.10.2`. Có ba nhóm test:

1. Unit test **độc lập**, có thể chạy concurrently.
2. Test dùng **system property chung**, phải có `@ResourceLock`.
3. Test tạo **file riêng** qua `@TempDir`, không dùng tên cố định trong shared directory.

Cấu trúc dự án:

~~~text
parallel-unit-demo/
├── pom.xml
└── src/
    ├── main/
    │   └── java/vn/example/parallel/Calculator.java
    └── test/
        ├── java/vn/example/parallel/CalculatorTest.java
        ├── java/vn/example/parallel/PropertyAlphaTest.java
        ├── java/vn/example/parallel/PropertyBetaTest.java
        ├── java/vn/example/parallel/IsolatedFileTest.java
        └── resources/junit-platform.properties
~~~

### 6.1. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>vn.example</groupId>
    <artifactId>parallel-unit-demo</artifactId>
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
            <version>5.10.2</version>
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
                <version>3.2.5</version>
                <configuration>
                    <forkCount>1</forkCount>
                    <reuseForks>true</reuseForks>
                    <failIfNoTests>true</failIfNoTests>
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

**Giải thích POM:**

- JUnit Jupiter dùng scope `test`; mã ứng dụng không phụ thuộc vào thư viện test.
- Compiler Plugin biên dịch source theo Java 17.
- Surefire `3.2.5` hỗ trợ chạy JUnit Jupiter qua JUnit Platform provider tương ứng.
- **`forkCount=1`** tạo một forked JVM cho test của module trong cấu hình điển hình; nhờ đó JUnit Jupiter test thuộc cùng fork có thể phối hợp qua `@ResourceLock`.
- **`reuseForks=true`** cho phép Surefire tái sử dụng JVM đó cho nhiều test class, giảm chi phí khởi động nhưng cũng có nghĩa các static fields/system properties có thể tồn tại qua nhiều class.
- **`failIfNoTests=true`** giúp CI báo lỗi nếu cấu hình tên/lọc test làm suite không còn test nào được chạy.
- POM không dùng Surefire `<parallel>methods</parallel>`: JUnit Jupiter concurrency được bật ở **file JUnit configuration** bên dưới, không thông qua tham số Surefire dành cho provider khác.

Các version plugin/JUnit này là **phiên bản minh họa cố định**, không khẳng định mới nhất. Dự án thật nên chọn versions phù hợp với Maven/JDK và được kiểm chứng trong CI.

### 6.2. src/test/resources/junit-platform.properties

~~~properties
junit.jupiter.execution.parallel.enabled=true
junit.jupiter.execution.parallel.mode.default=concurrent
junit.jupiter.execution.parallel.mode.classes.default=concurrent
junit.jupiter.execution.parallel.config.strategy=fixed
junit.jupiter.execution.parallel.config.fixed.parallelism=2
~~~

Chỉ khi Surefire/JUnit Jupiter nhìn thấy file trên **test runtime classpath** thì các tham số mới có hiệu lực. Maven mặc định copy `src/test/resources` vào `target/test-classes`, trừ khi build đã thay cấu hình resources/testResources.

Đặt desired parallelism = 2 để bài tập dễ quan sát và không cần quá nhiều thread. **Số lượng thread có thể thay đổi bởi engine, pool, CI và test blocking**, vì thế không assert tên/ID thread hoặc thời gian chạy cố định.

### 6.3. src/main/java/vn/example/parallel/Calculator.java

~~~java
package vn.example.parallel;

public final class Calculator {
    private Calculator() {
    }

    public static int sum(int a, int b) {
        return a + b;
    }

    public static int product(int a, int b) {
        return a * b;
    }

    public static void main(String[] args) {
        System.out.println("Parallel unit demo: " + sum(2, 3));
    }
}
~~~

Class không có mutable shared state. Những phép tính thuần phụ thuộc tham số và không viết biến toàn cục là ứng viên tốt để test song song.

### 6.4. src/test/java/vn/example/parallel/CalculatorTest.java

~~~java
package vn.example.parallel;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.parallel.Execution;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.parallel.ExecutionMode.CONCURRENT;

@Execution(CONCURRENT)
class CalculatorTest {
    @Test
    void addsNumbers() {
        assertEquals(5, Calculator.sum(2, 3));
    }

    @Test
    void multipliesNumbers() {
        assertEquals(12, Calculator.product(3, 4));
    }

    @Test
    void handlesNegativeNumbers() {
        assertEquals(-2, Calculator.sum(-5, 3));
    }
}
~~~

Các test không có thứ tự phụ thuộc nhau, không viết file chung hoặc static mutable state. JUnit có thể đặt chúng ở các worker threads khác nhau khi cấu hình parallel được bật.

**Không đặt kiểm tra kiểu `assertNotEquals(Thread.currentThread(), ...)` hoặc assert thời gian tối thiểu** để “chứng minh chắc chắn” concurrent: scheduling do engine/OS/CI quyết định, một lần chạy không đảm bảo chính xác thứ tự hay overlap.

### 6.5. src/test/java/vn/example/parallel/PropertyAlphaTest.java

~~~java
package vn.example.parallel;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.parallel.Execution;
import org.junit.jupiter.api.parallel.ResourceAccessMode;
import org.junit.jupiter.api.parallel.ResourceLock;
import org.junit.jupiter.api.parallel.Resources;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.parallel.ExecutionMode.CONCURRENT;

@Execution(CONCURRENT)
@ResourceLock(value = Resources.SYSTEM_PROPERTIES,
              mode = ResourceAccessMode.READ_WRITE)
class PropertyAlphaTest {
    @Test
    void usesAlphaMode() {
        String key = "demo.parallel.mode";
        String before = System.getProperty(key);

        try {
            System.setProperty(key, "alpha");
            assertEquals("alpha", System.getProperty(key));
        } finally {
            if (before == null) {
                System.clearProperty(key);
            } else {
                System.setProperty(key, before);
            }
        }
    }
}
~~~

**System properties là tài nguyên chung trong JVM**. Với `@ResourceLock(Resources.SYSTEM_PROPERTIES, READ_WRITE)`, Jupiter không cho một test khác có lock mâu thuẫn trên cùng resource chạy xen vào vùng được bảo vệ. `try/finally` phục hồi giá trị cũ ngay cả nếu assertion thất bại.

**Chỉ khóa mà không cleanup là chưa đủ:** state của test trước có thể làm test sau lệ thuộc order. **Chỉ cleanup mà không khóa cũng chưa đủ:** hai test có thể cùng thay đổi property trước khi kịp restore.

### 6.6. src/test/java/vn/example/parallel/PropertyBetaTest.java

~~~java
package vn.example.parallel;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.parallel.Execution;
import org.junit.jupiter.api.parallel.ResourceAccessMode;
import org.junit.jupiter.api.parallel.ResourceLock;
import org.junit.jupiter.api.parallel.Resources;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.parallel.ExecutionMode.CONCURRENT;

@Execution(CONCURRENT)
@ResourceLock(value = Resources.SYSTEM_PROPERTIES,
              mode = ResourceAccessMode.READ_WRITE)
class PropertyBetaTest {
    @Test
    void usesBetaMode() {
        String key = "demo.parallel.mode";
        String before = System.getProperty(key);

        try {
            System.setProperty(key, "beta");
            assertEquals("beta", System.getProperty(key));
        } finally {
            if (before == null) {
                System.clearProperty(key);
            } else {
                System.setProperty(key, before);
            }
        }
    }
}
~~~

Hai class dùng **cùng resource key** và `READ_WRITE`, vì vậy JUnit Jupiter có thể chạy test độc lập khác song song, nhưng không cho hai test trên truy cập đối kháng cùng nguồn system properties trong cùng JUnit execution engine.

**Giới hạn:** nếu một test khác tự sửa `System.setProperty` mà **không khai báo lock tương ứng**, JUnit không thể tự biết để chặn. `@ResourceLock` là **cơ chế phối hợp có khai báo**; tất cả test cùng dùng tài nguyên cần tuân thủ quy ước. Nó cũng **không khóa system properties trong JVM/process khác**.

### 6.7. src/test/java/vn/example/parallel/IsolatedFileTest.java

~~~java
package vn.example.parallel;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.assertEquals;

class IsolatedFileTest {
    @Test
    void firstFileIsPrivate(@TempDir Path tempDir) throws IOException {
        Path output = tempDir.resolve("result.txt");
        Files.writeString(output, "alpha", StandardCharsets.UTF_8);
        assertEquals("alpha",
                Files.readString(output, StandardCharsets.UTF_8));
    }

    @Test
    void secondFileIsPrivate(@TempDir Path tempDir) throws IOException {
        Path output = tempDir.resolve("result.txt");
        Files.writeString(output, "beta", StandardCharsets.UTF_8);
        assertEquals("beta",
                Files.readString(output, StandardCharsets.UTF_8));
    }
}
~~~

Cả hai test đều dùng tên **`result.txt`**, nhưng mỗi lần JUnit inject một `@TempDir` vào test method là một **thư mục tạm riêng theo scope của annotation**, nên đường dẫn thực tế không trùng nhau. JUnit quản lý lifecycle/cleanup của thư mục tạm theo cấu hình của nó.

**Chú ý:** nếu cố thay `@TempDir` bằng một đường dẫn tĩnh như `Path.of("target/result.txt")`, hai test có thể ghi đè lẫn nhau khi chạy song song. Khi test ghi ra một directory ngoài workspace đang được nhiều module/CI jobs chia sẻ, cần namespace riêng theo test/module/process, không chỉ dựa vào lock nội JVM.

## 7. Chạy ví dụ và đọc kết quả đúng

Từ thư mục dự án:

~~~bash
mvn --version
mvn -B -ntp clean verify
java -cp target/classes vn.example.parallel.Calculator
~~~

Nếu Maven/JDK/dependencies sẵn sàng, Surefire chạy các test và tạo báo cáo trong `target/surefire-reports`. Cụ thể trong project ví dụ:

- `CalculatorTest`: **3** test methods.
- `PropertyAlphaTest`: **1** test method.
- `PropertyBetaTest`: **1** test method.
- `IsolatedFileTest`: **2** test methods.

Tổng cộng **7 test methods** nếu không áp dụng thêm filters/profiles hay thay nội dung ví dụ. Test framework có thể sắp xếp thứ tự và thực thi concurrent khác nhau qua các lần chạy. **Đừng dự đoán một thứ tự hiển thị test cụ thể** trong console.

**Stdout chính xác của riêng lệnh `java` cuối cùng:**

~~~text
Parallel unit demo: 5
~~~

`mvn verify` **không tự chạy `Calculator.main`**; dòng trên chỉ được in khi gọi Java launcher. Đường dẫn class của ví dụ thuộc `target/classes`; mã chính không phụ thuộc thư viện bên thứ ba nên không cần thêm JUnit vào classpath để chạy nó.

### Kiểm tra báo cáo Surefire

~~~bash
ls target/surefire-reports
~~~

Trên Windows PowerShell:

~~~powershell
Get-ChildItem target\surefire-reports
~~~

Tìm những file có tên kiểu `TEST-vn.example.parallel.CalculatorTest.xml` và các class tương ứng. Báo cáo giúp biết số test, số lỗi, số skip và thời gian thực tế; **không nên suy luận có chạy song song hay không chỉ từ tổng thời gian một lượt**.

Để kiểm tra JUnit Platform properties đã được copy:

~~~bash
ls target/test-classes/junit-platform.properties
~~~

PowerShell:

~~~powershell
Get-Item target\test-classes\junit-platform.properties
~~~

Nếu file vắng mặt, kiểm tra `src/test/resources`, effective POM và cấu hình testResources. Thay đổi config phải chạy lại build/test với môi trường đúng.

## 8. Vì sao `@ResourceLock` tốt hơn dựa vào thứ tự test?

Giả sử hai test cùng thay đổi system property:

~~~text
Test Alpha: set mode = alpha --> assert alpha --> restore
Test Beta : set mode = beta  --> assert beta  --> restore
~~~

Nếu không bảo vệ:

~~~text
Thread A: set alpha
Thread B: set beta
Thread A: assert alpha        (thực tế đang thấy beta -> fail)
Thread B: assert beta
~~~

Đây là **interleaving minh họa có thể xảy ra**, không phải thứ tự đảm bảo sẽ xảy ra trong mọi run. Thêm `Thread.sleep` để tái hiện có thể làm tăng khả năng va chạm nhưng không sửa được root cause; **không nên dùng sleep để đồng bộ hóa**.

Với Jupiter `@ResourceLock` trên **cùng key**:

~~~text
Resource: SYSTEM_PROPERTIES
  |
  +-- Alpha lấy READ_WRITE lock, chạy test rồi release
  |
  +-- Beta lấy READ_WRITE lock, chạy test rồi release
~~~

Hai test không đồng thời chiếm khóa WRITE trong cùng execution engine. Những test độc lập như `CalculatorTest` có thể tiếp tục chạy ở các worker threads khác khi không cần resource này.

### READ và READ_WRITE

`@ResourceLock` hỗ trợ hai mode:

| Mode | Nghĩa | Có thể chạy cùng |
| --- | --- | --- |
| **`READ`** | Test chỉ cần đọc một shared resource ổn định. | Các test khác dùng **READ** trên cùng key. |
| **`READ_WRITE`** | Test có thể sửa resource hoặc cần độc quyền. | Không cùng lúc với READ hoặc READ_WRITE khác trên cùng key. |

Ví dụ đoạn annotation **minh họa, không phải class độc lập**:

~~~java
@ResourceLock(value = "shared-catalog",
              mode = ResourceAccessMode.READ)
~~~

Hai test chỉ đọc snapshot bất biến có thể chạy đồng thời. Test cập nhật catalog nên dùng `READ_WRITE` trên **cùng key**. Nếu giá trị thay đổi ngoài JUnit (service ngoài, process khác), khóa trong JUnit **không bảo đảm** dữ liệu ngoài ấy đứng yên.

### Đặt khóa ở class hay method?

- **Class-level**: đơn giản khi mọi test trong class đều dùng cùng resource; có thể giảm mức song song nhiều hơn cần thiết.
- **Method-level**: tinh chỉnh từng test thực sự truy cập resource, giúp những method độc lập khác tiếp tục concurrent.
- **`@Isolated`**: dành cho một test class cần chạy cách ly khỏi những test Jupiter khác trong engine; mức phạm vi lớn, dùng khi ResourceLock theo key không đủ diễn đạt, nhưng **không cách ly khỏi JVM khác, module khác hoặc CI job khác**.

Đặt khóa theo **resource thực sự**, không đặt tùy tiện chỉ để che một test flaky rồi mất khả năng song song.

## 9. Những tài nguyên chung nguy hiểm nhất

| Tài nguyên | Vì sao xung đột? | Cách xử lý ưu tiên |
| --- | --- | --- |
| **Static mutable fields/singleton** | Hai test cập nhật chung object, cache hoặc counter. | Tạo instance riêng cho test; tránh global state; dùng cấu trúc thread-safe khi thật sự cần. |
| **System properties** | Là trạng thái JVM-wide, test sửa ảnh hưởng test khác. | `@ResourceLock(Resources.SYSTEM_PROPERTIES)`, `try/finally` restore; tối ưu hơn là inject config theo instance. |
| **Default Locale/TimeZone** | Test đổi giá trị mặc định làm định dạng/ngày giờ của test khác đổi. | Truyền Locale/ZoneId tường minh; nếu buộc đổi global thì khai báo lock tương ứng và restore. |
| **System.out/System.err** | Nhiều test capture/replace stream hoặc trộn output. | Không dùng stdout để assert đồng thời; dùng logger/test extension an toàn hoặc lock. |
| **Thư mục/file dùng chung** | Ghi đè, xóa file, đọc dữ liệu dở dang. | `@TempDir` riêng, tên namespace duy nhất; lock liên process nếu thật sự cần dùng cùng file. |
| **Cổng TCP cố định** | Chỉ một server bind được cùng port trong cùng network namespace. | Dùng cổng được OS cấp (`port=0`), cơ chế cấp phát và cleanup đúng; không đoán port “rảnh” bằng hai bước dễ race. |
| **Database/schema/bảng** | Test mutate cùng rows hoặc truncate dữ liệu. | Transaction rollback khi áp dụng được, unique schema/table/tenant/ID, container/database riêng hoặc lịch chạy hạn chế. |
| **Mock server/HTTP endpoint** | Cấu hình response/scenario chung, test ảnh hưởng nhau. | Mỗi test có instance riêng/namespace, teardown, port động. |
| **Queue/topic/bucket** | Message từ test này lọt sang test khác. | Namespace riêng, correlation IDs, cleanup theo ownership, TTL. |
| **CPU/RAM/file handles** | Quá tải gây timeout, GC, OOM, connection exhaustion. | Giới hạn concurrency/forks, phân loại test và đo tài nguyên. |

**Tránh dựa vào thứ tự test** như “test tạo dữ liệu chạy trước test xóa dữ liệu”. Unit test đúng nghĩa nên tự setup/cleanup dữ liệu và độc lập với test khác. Nếu có luồng nghiệp vụ cần nhiều bước theo thứ tự, cân nhắc **một test kịch bản** thay vì chia thành nhiều test phụ thuộc ngầm.

## 10. Tối ưu thiết kế test trước khi tăng luồng

Từ dễ bảo trì đến phức tạp hơn:

1. **Loại trạng thái chung**: mỗi test có object riêng, dữ liệu riêng, mock riêng. Đây là cách tốt nhất.
2. **Dùng dữ liệu bất biến**: constants/immutable DTO có thể chia sẻ mà không cần khóa cập nhật.
3. **Tạo namespace tài nguyên riêng**: `@TempDir`, database schema unique, random test identifier, port do OS cấp.
4. **Khôi phục global state**: `try/finally`, `@AfterEach`, cleanup sau khi test kết thúc — nhưng nhớ cleanup phải nằm trong vùng bảo vệ nếu đang chạy parallel.
5. **Dùng `@ResourceLock`** với các global state không thể tách trong **cùng JUnit engine/JVM**.
6. **Dùng isolation/serial execution** cho test không thể concurrency-safe, thay vì ép mọi test cùng bị chặn.
7. **Giới hạn Surefire forks/Maven -T/CI matrix** cho những tài nguyên chia sẻ xuyên JVM/process.
8. **Dùng distributed lock hoặc dedicated fixture service** chỉ khi thực sự cần phối hợp qua nhiều process/máy; có timeout, owner và cơ chế khôi phục.

### Một ví dụ chống pattern: static counter

Giả sử nhiều test cùng làm:

~~~java
static int counter = 0;

// Trong nhiều test khác nhau:
counter++;
~~~

Đây là **đoạn Java minh họa, không phải class runnable độc lập**. `counter++` không phải thao tác nguyên tử; hai thread có thể đọc cùng giá trị rồi ghi đè cập nhật của nhau. Chỉ thay `int` thành `volatile int` **không biến ++ thành atomic**.

Nếu counter là phần của code production cần thread-safe, cân nhắc `AtomicInteger.incrementAndGet()` hoặc đồng bộ hóa phù hợp, và viết test kiểm tra concurrency của **production code**. Nếu counter chỉ tồn tại để test đếm số lần chạy, tốt hơn **tránh shared counter** hoặc dùng công cụ của framework.

**Đừng dùng `@ResourceLock` để hợp thức hóa một race condition thật trong production class.** Lock trong test chỉ làm các test bớt xung đột, nhưng không chứng minh code ứng dụng đúng khi nhiều request thật chạy đồng thời.

## 11. forkCount: Surefire tạo bao nhiêu JVM?

Trong Surefire:

~~~xml
<configuration>
    <forkCount>2</forkCount>
    <reuseForks>true</reuseForks>
</configuration>
~~~

Đoạn XML này nằm **trong plugin `maven-surefire-plugin`**, không phải POM độc lập. `forkCount=2` cho phép Surefire dùng **tối đa hai JVM forked chạy đồng thời** trong phạm vi execution tương ứng.

Các lựa chọn:

| Cấu hình | Hành vi chính | Lưu ý |
| --- | --- | --- |
| **`forkCount=1`, `reuseForks=true`** | Một JVM test được tái sử dụng cho nhiều test class trong module. | Tiết kiệm startup, static state có thể tồn tại giữa các class. |
| **`forkCount=1`, `reuseForks=false`** | Mỗi test class dùng JVM riêng, xử lý lần lượt trong cách thiết lập này. | Tách static state giữa class, chi phí khởi động cao. |
| **`forkCount=2`, `reuseForks=true`** | Tối đa hai JVM thực thi các class, reuse cho nhiều class. | `@ResourceLock` không phối hợp qua hai JVM; cần tài nguyên riêng nếu có chia sẻ ngoài process. |
| **`forkCount=1C`** | Hệ số theo CPU cores mà Maven/Surefire nhìn thấy. | Trên CI có nhiều CPUs có thể tạo quá nhiều JVM, cần đo memory. |
| **`forkCount=0`** | Không fork JVM, có thể chạy test trong process Maven. | Chia sẻ system properties/heap của Maven, rủi ro lớn hơn khi build reactor `-T`. |

Cú pháp hậu tố `C` gắn với CPU count, ví dụ `1C` khác số JVM cố định 1. Khi CPU count do container/host báo khác giới hạn tài nguyên thực, kết quả có thể quá tải. Không áp dụng tùy tiện trên máy CI chia sẻ.

### reuseForks không phải “dùng lại test instance”

`reuseForks=true` tái sử dụng **process JVM** cho nhiều test class. Nó **không đồng nghĩa** JUnit tái sử dụng cùng một instance object của mỗi test method.

JUnit Jupiter mặc định tạo test instance theo phương thức (lifecycle PER_METHOD), trừ khi bạn cấu hình `@TestInstance(PER_CLASS)` hoặc thay default. Nhưng **static state, system properties và các singletons vẫn sống trong JVM**, dù JUnit tạo các test instance mới.

### Khi forkCount tăng, ResourceLock có còn bảo vệ không?

Trong **một fork**, Jupiter biết những test thuộc execution plan của nó và có thể điều phối resource keys. Nhưng hai fork là **hai JVM khác nhau**; mỗi engine có bộ locks riêng. Nếu hai test ở hai forks cùng mở file `target/shared.tmp` hoặc kết nối DB schema `test`, annotation giống nhau **không đảm bảo loại trừ lẫn nhau**.

Giải pháp tốt hơn là **mỗi fork có namespace tài nguyên riêng**, ví dụ dùng một thư mục hay DB schema có fork identifier, hoặc giữ forkCount thấp đối với suite dùng tài nguyên chung.

## 12. ${surefire.forkNumber}: phân biệt tài nguyên theo fork

Surefire hỗ trợ placeholder **`${surefire.forkNumber}`** trong một số tham số như system property và `argLine`/workingDirectory. Giá trị của nó được Surefire thay bằng số fork trong ngữ cảnh execution, có tính đến mức song song Maven reactor khi áp dụng.

Ví dụ cấu hình **minh họa trong Surefire Plugin**:

~~~xml
<configuration>
    <forkCount>2</forkCount>
    <reuseForks>true</reuseForks>
    <systemPropertyVariables>
        <test.fork.id>${surefire.forkNumber}</test.fork.id>
    </systemPropertyVariables>
</configuration>
~~~

Khi test chạy, code có thể lấy:

~~~java
String forkId = System.getProperty("test.fork.id", "unknown");
~~~

Đây là **dòng Java minh họa**, không phải một class độc lập. Dùng `forkId` để tạo namespace theo process, nhưng **không dùng một mình forkId nếu nhiều CI jobs/máy có thể cùng dùng một database hoặc file share** — chúng có thể cùng dùng số `1`.

Một tên tài nguyên đủ tách biệt thường cần thêm **build/job identifier, module identifier, fork identifier và test identifier**, được tạo từ dữ liệu CI có kiểm soát. Không nhúng credentials vào tên/URL log.

**Cẩn trọng** nếu test chạy nhiều thread trong **cùng một fork**: mọi test trong fork vẫn có **cùng fork number**. Muốn tách tài nguyên theo test, dùng unique test ID hoặc `@TempDir` thay vì chỉ dùng fork ID.

## 13. Maven -T: đồng thời giữa các module

Maven Reactor hỗ trợ xây dựng nhiều module theo dependency graph:

~~~bash
mvn -T 2 -B -ntp clean verify
~~~

Điều này có thể tăng thông lượng nếu có các module độc lập, nhưng **không có nghĩa hai module luôn chạy đồng thời**; quan hệ dependency và lifecycle quyết định những module nào đủ điều kiện.

Khi `-T 2` và mỗi module chạy Surefire với `forkCount=2`, có thể có nhiều JVM test process đồng thời. Trong mỗi JVM lại có JUnit Jupiter worker threads. **Đừng giả định chi phí tài nguyên bằng một fork hoặc một thread pool**.

Các rủi ro riêng của reactor:

- Hai module có thể dùng cùng **schema database**, cùng thư mục external hoặc cùng cổng.
- Plugin goal không thread-safe có thể tạo rủi ro hoặc làm Maven cảnh báo trong parallel build.
- Nếu `forkCount=0`, test có thể dùng chung process Maven và các system properties của các build threads.
- Các module có packaging/plugin khác nhau có thể thực thi test profile khác nhau; đọc effective POM của từng module.
- Một số integration test dựa vào artifact của module khác phải tôn trọng thứ tự reactor/build graph, không tự viết script bỏ qua dependency.

**Đừng sửa race xuyên module bằng `@ResourceLock` của JUnit.** Nó không phải khóa Maven reactor. Hãy cấp database/port/file namespace riêng theo module hoặc dùng một workflow tích hợp có lịch chạy có kiểm soát.

### Ví dụ tăng dần độ song song

Bắt đầu một module test trong một JVM:

~~~bash
mvn -B -ntp clean test
~~~

Sau khi kiểm chứng ổn định, mới thử reactor:

~~~bash
mvn -T 2 -B -ntp clean test
~~~

Nếu xuất hiện flaky test, chạy lại nhiều lần, đối chiếu module bị lỗi, shared resources, CPU/RAM/DB quota; **không kết luận “-T gây lỗi” mà bỏ qua race đã tồn tại**.

## 14. `@Isolated`, SAME_THREAD và SERIAL khác nhau như thế nào?

**`@Execution(SAME_THREAD)`** yêu cầu node test thực thi trong luồng gắn với parent theo semantics của Jupiter. Nó hữu ích khi một test method không được concurrent với những method cùng vùng thực thi, nhưng **không có nghĩa mọi test khác trong engine đều phải đứng chờ**.

**`@ResourceLock("resource-name")`** cho JUnit biết **resource cụ thể** cần đồng bộ. Những test không có xung đột với tên khóa có thể tiếp tục chạy song song.

**`@Isolated`** là cách cách ly một class cần **độc quyền ở phạm vi Jupiter execution engine**, khiến lớp đó chạy tuần tự không cùng lúc với test Jupiter khác trong engine. Dùng khi test chạm rất nhiều global state không dễ liệt kê từng resource key, nhưng nó làm giảm mức song song.

Ví dụ đoạn annotation minh họa:

~~~java
import org.junit.jupiter.api.parallel.Isolated;

@Isolated
class LegacyGlobalFixtureTest {
    // Các test ở đây không nên đụng tài nguyên toàn cục
    // của những test khác trong cùng Jupiter engine.
}
~~~

Không có phần thân test nên đoạn trên **không phải unit test runnable hoàn chỉnh**. Cả `@Isolated` lẫn ResourceLock **không khóa các JVM khác**; nếu database dùng chung với job CI khác, phải xử lý ở cấp hạ tầng hoặc phân tách tài nguyên.

Khi đã có test độc lập, **không cần đánh dấu mọi test @Isolated**. Cách đó làm suite gần như tuần tự và không giải quyết được nguyên nhân thiết kế shared state.

## 15. Race condition trong setup và teardown

Một lớp test có thể dùng:

- `@BeforeEach`: chuẩn bị state cho mỗi method.
- `@AfterEach`: cleanup state sau mỗi method.
- `@BeforeAll`: chuẩn bị state chung trước test class.
- `@AfterAll`: giải phóng state chung sau class.

Nếu setup/teardown chạm **resource chia sẻ**, phần này cũng có thể xảy ra cạnh tranh với test khác. JUnit Jupiter `@ResourceLock` áp dụng synchronization cho lifecycle scope của test/class được khai báo, bao gồm các lifecycle methods phù hợp trong execution plan.

Ví dụ hai test cùng đổi default TimeZone rồi restore:

~~~text
BeforeEach: set default TimeZone
Test: assert format
AfterEach: restore TimeZone
~~~

Nếu không có lock thích hợp, hai test có thể xen vào giữa setup và teardown của nhau. **Một `synchronized` block chỉ bọc assertion mà không bọc setup/teardown có thể không đủ**.

Trong ví dụ dùng system property ở mục 6, `try/finally` nằm bên trong test method có lock ở class level; như vậy cả thay đổi và phục hồi thuộc cùng vùng bảo vệ.

### Với test instance PER_CLASS

`@TestInstance(PER_CLASS)` cho phép nhiều test methods của class chia sẻ **cùng test object**. Nếu bật `@Execution(CONCURRENT)`, các instance fields mutable có thể bị nhiều method sửa đồng thời. JUnit có quy tắc mặc định tránh một số kết hợp nguy hiểm, nhưng khi override concurrency bạn **phải tự đảm bảo thread safety**.

Một pattern tốt là **instance PER_METHOD + dữ liệu khởi tạo riêng**; nếu phải PER_CLASS, nên dùng immutable setup data, tránh dùng field mutable làm scratch buffer chung, hoặc giữ class ở mode tuần tự.

## 16. Timeout, rerun và flaky test

**Flaky test** là test có kết quả thay đổi giữa các lần chạy dù source không đổi. Không phải flaky test nào cũng do concurrency: network, thời gian, random seed, resource leak, timezone và thứ tự test cũng thường gây lỗi.

Surefire có các tham số như `rerunFailingTestsCount` để **chạy lại test thất bại** và ghi nhận flakiness. Đây là công cụ **chẩn đoán/chống nhiễu nhất thời**, không phải lời giải race condition. Nếu một test fail rồi pass khi rerun, phải điều tra nguyên nhân.

Không nên “sửa” test flaky bằng:

- Tăng `Thread.sleep(...)` tùy tiện.
- Chạy test thất bại nhiều lần cho tới khi pass rồi bỏ qua lần fail đầu.
- Tắt toàn bộ test song song mãi mãi mà không ghi lại căn nguyên và rủi ro.
- Đổi run order để tạm tránh đụng shared state.
- Dùng timeout rất dài khiến CI trễ mà resource leak vẫn còn.

Thay vào đó, dùng assertion có điều kiện rõ ràng, polling với deadline phù hợp cho thao tác bất đồng bộ, tài nguyên riêng, cleanup đáng tin và khóa đúng phạm vi. Unit test thuần đồng bộ như ví dụ Calculator **không cần sleep hay polling**.

### Lặp kiểm tra trong CI

Với một test suite có nguy cơ race, chạy lại nhiều lần trong môi trường thử nghiệm có thể tăng khả năng phát hiện lỗi:

~~~bash
mvn -B -ntp clean test
mvn -B -ntp test
mvn -B -ntp test
~~~

Ba lệnh chỉ là ví dụ, **không chứng minh tính đúng đắn tuyệt đối** nếu đều pass. Một race có thể rất hiếm hoặc chỉ xuất hiện khi CPU/DB tải cao. Các thay đổi về test order/randomized scheduling có kiểm soát và stress tests hỗ trợ, nhưng phải tránh làm CI không tái lập được.

## 17. Cách chẩn đoán khi Surefire chạy test lỗi không ổn định

Đi từ phạm vi nhỏ tới lớn:

1. **Xác nhận phiên bản**: `mvn --version`, JDK đang chạy Maven và Surefire/JUnit versions từ effective POM/log.
2. **Tìm test thật sự fail**: mở `target/surefire-reports` thay vì chỉ nhìn dòng `BUILD FAILURE` cuối cùng.
3. **Chạy test/class riêng**: dùng `-Dtest=CalculatorTest` hoặc tên đầy đủ để tách môi trường.
4. **Tắt Jupiter parallel để so sánh**: đổi `junit.jupiter.execution.parallel.enabled=false` trong test config trên nhánh thử nghiệm rồi chạy lại.
5. **Giữ forkCount=1** để giảm biến số; xác nhận lỗi trong cùng JVM hay chỉ khi tăng forks.
6. **Giảm Maven -T về mặc định**: nếu lỗi chỉ xảy ra khi nhiều module chạy cùng lúc, tìm tài nguyên xuyên module.
7. **Rà shared mutable state**: static variables, caches, system properties, default Locale/TimeZone, file paths, DB rows, ports.
8. **Kiểm tra thiết kế setup/teardown**: một test có thể xóa fixture test khác đang sử dụng.
9. **Phân loại khóa**: resource có thể tạo riêng không? Nếu không, `@ResourceLock` có đủ phạm vi không hay cần lock liên process?
10. **Kiểm tra tài nguyên máy**: memory, CPU, open files, DB connection pool, ephemeral ports, container limits.
11. **Chạy lại với cùng seed/config** nếu framework có randomized order hoặc property riêng, và lưu log mức đủ chẩn đoán.
12. **Sau khi sửa**: xác minh test pass nhiều lần với đúng parallel/fork/reactor/CI settings cần dùng, rồi đóng issue với nguyên nhân cụ thể.

Một cách tạm đưa suite về tuần tự ở tầng Jupiter là dùng file:

~~~properties
junit.jupiter.execution.parallel.enabled=false
~~~

Lưu ý **tắt Jupiter parallel không tự vô hiệu hóa** Surefire nhiều fork JVM, Maven `-T` hoặc nhiều CI jobs. Cần kiểm soát tất cả các tầng để cô lập nguyên nhân.

## 18. Kiểm soát tài nguyên bộ nhớ và CPU trong CI

### Heap JVM

Khi Surefire fork nhiều JVM, mỗi fork có **heap, metaspace, threads và classloader riêng**. Tổng memory thực tế gồm heap cộng overhead ngoài heap. Nếu nhiều forks chạy cùng lúc, RAM có thể tăng đáng kể.

`argLine` của Surefire có thể dùng để cung cấp JVM options:

~~~xml
<configuration>
    <forkCount>1</forkCount>
    <reuseForks>true</reuseForks>
    <argLine>-Xmx512m</argLine>
</configuration>
~~~

Đây là **đoạn cấu hình minh họa**, không phải mức heap khuyến nghị cho mọi dự án. `512m` chỉ phù hợp nếu workload đã được đo và vừa memory budget; với ứng dụng lớn, DB in-memory hay framework test có thể thiếu.

Đặt `-Xmx` quá cao cho từng fork khiến tổng RAM vượt giới hạn container. Đặt quá thấp dẫn tới OOM hoặc GC quá nặng. **Chọn theo metrics**, không đoán từ số core.

### Ước lượng tải đồng thời

Có thể dùng tư duy:

~~~text
Số job CI đồng thời
  x số module build đồng thời
  x số Surefire forked JVM cho mỗi module
  x mức parallelism JUnit Jupiter trong mỗi fork
~~~

Đây là **công thức tư duy về mức độ khuếch đại**, không phải phép dự báo chính xác số test cùng chạy hoặc số OS threads. Reactor dependency graph, JVM pool, blocking, policy của CI và test scheduling làm kết quả thực tế thay đổi.

Nếu mỗi test mở connection DB, tăng parallelism có thể làm quá tải pool. Nếu test đồng thời start nhiều containers, disk và Docker daemon có thể trở thành nút nghẽn. Nên có **quota riêng cho resource ngoài JVM** và đừng mở rộng mức đồng thời chỉ vì CPU chưa dùng hết.

### Dấu hiệu cần giảm concurrency

- `OutOfMemoryError`, process bị hệ điều hành kill hoặc container exit 137.
- Connection pool timeout, DB `too many connections`.
- `BindException: Address already in use`.
- File lock conflict hoặc test đọc nhầm output của test khác.
- Thời gian test trung bình tăng khi tăng forks.
- CPU bị oversubscribe, load cao nhưng throughput không tăng.

Một số lỗi trong danh sách là resource contention thật, không chỉ do test assertion. Sửa phải phối hợp **cấu hình executor** và **thiết kế tài nguyên**.

## 19. DB, filesystem, network: khóa trong JVM không đủ

### Database

Nếu hai test cùng dùng schema `test` và cùng thực hiện `DELETE FROM users`, chúng có thể phá dữ liệu của nhau. `@ResourceLock("db-test")` chỉ giúp nếu mọi test truy cập schema nằm trong **cùng Jupiter engine**, đều khai báo **đúng key**. Một fork khác hoặc CI job khác vẫn có thể ghi.

Các phương án tốt hơn:

- Mỗi test/worker có **schema hoặc database riêng**.
- Tạo bản ghi với **ID unique** và cleanup đúng ownership thay vì xóa toàn bảng.
- Dùng transaction rollback nếu thao tác nằm trong cùng transaction được quản lý và phù hợp môi trường.
- Có **test containers/DB instances** tách biệt khi chi phí cho phép.
- Chạy một nhóm integration tests cần DB chung theo lịch có kiểm soát nếu chưa thể cô lập.

### File

**Không dùng** chung file như `target/result.json` cho nhiều test và module. Có thể dùng `@TempDir`, prefix riêng theo test và cleanup trong thư mục test sở hữu. Nếu dùng file share ngoài JVM, cần locking phù hợp với hệ điều hành và kiểm tra cross-process behavior; `synchronized` Java không khóa process khác.

### Port

Chọn port cố định `8080` cho mọi test thường gây lỗi khi nhiều test server chạy song song. Hãy để OS cấp cổng động khi framework hỗ trợ, rồi đọc cổng **đang được bind thực sự**. Cách “thử socket để thấy port rảnh rồi đóng, sau đó mở server ở port ấy” có race condition, vì process khác có thể lấy port ở giữa.

### System.out và logging

Nếu test chặn/capture System.out bằng cách thay global stream, cần lock **`Resources.SYSTEM_OUT`** nếu thực hiện trong cùng Jupiter engine. Nhưng output từ nhiều process độc lập vẫn phải được phân luồng theo job/module để đọc log chính xác. Dùng logger và test harness phù hợp thường tốt hơn capture stdout toàn cục.

## 20. Vì sao `@Execution(SAME_THREAD)` không thay thế khóa chung?

Giả sử test class X có một test thay system property, và test class Y có test khác cũng thay property đó. Cả hai đánh dấu `@Execution(SAME_THREAD)` ở method **không nhất thiết ép X và Y chạy trên cùng một thread hoặc ngăn hai class chạy đồng thời**, vì mỗi method có parent khác nhau.

Để phối hợp **một resource chung** giữa hai class, dùng cùng resource key:

~~~java
@ResourceLock(value = Resources.SYSTEM_PROPERTIES,
              mode = ResourceAccessMode.READ_WRITE)
~~~

Khi sử dụng key mặc định của JUnit như `Resources.SYSTEM_PROPERTIES`, các test khác biết đúng “tên” resource. Nếu tự dùng `"system-property"` ở một class và `"sysprops"` ở class khác, chúng **không phối hợp** vì khóa khác tên dù cùng đụng System properties.

Nếu cần bảo vệ **chỉ một property** mà không cản những test dùng properties khác, có thể dùng một key riêng như `"demo.parallel.mode"` **nếu mọi test liên quan cùng tuân thủ key ấy**. Dùng khóa hệ thống chung đơn giản hơn nhưng có thể làm giảm concurrency. Lựa chọn dựa trên phạm vi tài nguyên và mức độ kiểm soát test suite.

## 21. Lịch chạy test, kiểm thử deterministic và khả năng tái lập

Không nên để một test quyết định kết quả dựa vào:

- “Test A luôn chạy trước test B”.
- “Test C luôn chạy trên main thread”.
- “Máy CI luôn có bốn core”.
- “Không ai khác dùng port 8080”.
- “Thư mục `/tmp/demo` luôn rỗng”.
- “Một process fork nhất định luôn nhận một test class cụ thể”.
- “Thread.sleep(200) chắc chắn đợi đủ cho async event”.
- “Test sẽ luôn pass nếu mạng trả lời trong 100 ms”.

Tính đúng đắn cần dựa trên **hợp đồng của test và dữ liệu đầu vào**, không phải các tình cờ của scheduler. Có thể dùng `@Order` khi kiểm thử một kịch bản có chủ đích và lifecycle phù hợp, nhưng **không dùng ordering để che một sự phụ thuộc xấu giữa các unit test độc lập**.

Một cách viết test tốt: mỗi test **Arrange → Act → Assert**, tài nguyên cục bộ và teardown đáng tin; nếu cùng chia sẻ global state thì khóa trong đúng phạm vi. Khi build nhanh hơn nhờ parallel, số lượng flaky tests không nên tăng.

## 22. Checklist thực hành khi bật parallel execution

1. **Đo baseline tuần tự**: thời gian test và tỷ lệ lỗi; biết được hiện trạng trước khi tăng concurrency.
2. **Pin Maven Compiler/Surefire/JUnit versions** đủ khả năng hỗ trợ tính năng cần dùng.
3. **Bật JUnit Jupiter parallel** trong `src/test/resources/junit-platform.properties` hoặc một nguồn config rõ ràng.
4. **Chọn execution modes** phù hợp; mặc định `SAME_THREAD` rồi opt-in cho những class an toàn thường là lộ trình thận trọng.
5. **Chọn desired parallelism nhỏ trước**, không biến con số đó thành cam kết số thread tối đa.
6. **Chuyển test sang độc lập**: hạn chế mutable static state, global properties và fixed file names.
7. **Dùng `@TempDir` riêng** cho file test; namespace schema/port/queue cho tài nguyên ngoài JVM.
8. **Dùng `@ResourceLock` READ/READ_WRITE** cho tài nguyên chung không thể tách trong cùng Jupiter engine.
9. **Xử lý `@BeforeEach/@AfterEach` đúng phạm vi khóa** và luôn restore global state.
10. **Giữ Surefire forkCount=1 khi bắt đầu**, tăng forks chỉ khi tài nguyên ngoài JVM đã được tách.
11. **Kiểm soát Maven -T** riêng; đừng nhân nhiều tầng concurrency mà không biết memory/DB budget.
12. **Chạy `mvn clean verify` và đọc surefire-reports**; không suy đoán output theo thứ tự.
13. **Thử nhiều lần/CI matrix phù hợp** để phát hiện flakiness nhưng không coi nhiều lần pass là chứng minh tuyệt đối.
14. **Theo dõi CPU, RAM, cổng, DB connections, file handles** khi mở rộng test.
15. **Ghi rõ nhóm test phải serial/isolated** và lý do, không tắt concurrency của toàn suite không cần thiết.
16. **Nếu phát hiện flaky**, phân loại shared-state race, môi trường, timeout, version và resource contention; sửa root cause.
17. **Phân phối tài nguyên riêng cho mỗi CI job** nếu dùng một dịch vụ hoặc file share chung ngoài process.
18. **Review lại sau khi đổi Surefire/JUnit version**, vì default/provider/configuration behavior có thể thay đổi.

## 23. Bài tập củng cố

**Bài 1 — lắp dự án chạy được.** Tạo POM, `Calculator.java`, bốn test classes và `junit-platform.properties` như mục 6. Chạy `mvn -B -ntp clean verify`; giải thích vì sao có tổng **7 test methods** và không cần một thứ tự chạy cố định.

**Bài 2 — stdout.** Sau build, chạy `java -cp target/classes vn.example.parallel.Calculator`; đối chiếu chính xác **Parallel unit demo: 5**. Phân biệt stdout của main với log và báo cáo Surefire.

**Bài 3 — mở song song có kiểm soát.** Đổi `parallelism` giữa 1 và 2 trong môi trường thử nghiệm, quan sát thời gian chạy/test threads khi cần. Không viết assertion phụ thuộc thứ tự hay thread name.

**Bài 4 — khóa theo tài nguyên.** Giải thích vì sao `PropertyAlphaTest` và `PropertyBetaTest` cần cùng `Resources.SYSTEM_PROPERTIES` `READ_WRITE`, còn `CalculatorTest` không cần khóa.

**Bài 5 — file riêng.** Xóa `@TempDir` trong bản sao thử nghiệm và cho cả hai test ghi cùng một file dưới `target/`. Dự đoán và nhận diện nguy cơ race; sửa bằng cấp path riêng thay vì tăng `Thread.sleep`.

**Bài 6 — nhiều JVM.** Đổi `forkCount` từ 1 sang 2 khi đã cô lập resource, phân tích vì sao `@ResourceLock` không bảo vệ một file chung xuyên JVM. Không dùng khóa nội JVM để bảo vệ database thật đang chia sẻ với CI khác.

**Bài 7 — reactor.** Trong dự án nhiều module, thử `mvn -T 2 clean test` sau khi kiểm tra module independence. Vẽ số tầng concurrency và liệt kê resource nào có thể đụng giữa các module.

**Bài 8 — xử lý flaky.** Cho một test thay `TimeZone.setDefault`, test khác format ngày giờ. Phân tích ba hướng: truyền `ZoneId` tường minh, khóa `Resources.TIME_ZONE` và restore, hoặc chạy test cần global state trong nhóm isolated. Chọn hướng tách state nếu code cho phép.

### Tóm tắt

**Thực thi song song không chỉ là bật một cờ.** Với Maven/JUnit Jupiter phải phân biệt **thread-level parallelism của JUnit**, **JVM forks của Surefire**, **module-level concurrency của Maven `-T`** và **các job CI**. Chạy nhanh hơn chỉ có giá trị khi kết quả test còn chính xác và tái lập được.

Ưu tiên **test độc lập, dữ liệu bất biến và tài nguyên riêng**; khi không tránh được resource chung trong một JUnit engine, khai báo `@ResourceLock` với cùng key và quyền `READ`/`READ_WRITE`, bảo vệ cả setup/cleanup. Với file, dùng `@TempDir`; với DB, port và dịch vụ ngoài JVM, cần cách ly theo process/module/job. Điều chỉnh concurrency dựa trên đo lường và kiểm tra **`target/surefire-reports`**, không dựa vào cảm giác build nhanh hơn trong một lần chạy.

### Tài liệu chính thức

- [JUnit 5.10.2 — User Guide, Parallel Execution](https://docs.junit.org/5.10.2/user-guide/index.html#writing-tests-parallel-execution)
- [JUnit 5.10.2 — ResourceLock API](https://docs.junit.org/5.10.2/api/org.junit.jupiter.api/org/junit/jupiter/api/parallel/ResourceLock.html)
- [JUnit 5 — Jupiter @TempDir](https://docs.junit.org/5.10.2/user-guide/index.html#writing-tests-built-in-extensions-TempDirectory)
- [Apache Maven Surefire Plugin — Fork Options and Parallel Test Execution](https://maven.apache.org/surefire/maven-surefire-plugin/examples/fork-options-and-parallel-execution.html)
- [Apache Maven Surefire Plugin — Using JUnit Platform](https://maven.apache.org/surefire/maven-surefire-plugin/examples/junit-platform.html)
- [Apache Maven Surefire Plugin — surefire:test parameters](https://maven.apache.org/surefire/maven-surefire-plugin/test-mojo.html)
- [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Apache Maven — Guide to Working with Multiple Modules](https://maven.apache.org/guides/mini/guide-multiple-modules.html)
