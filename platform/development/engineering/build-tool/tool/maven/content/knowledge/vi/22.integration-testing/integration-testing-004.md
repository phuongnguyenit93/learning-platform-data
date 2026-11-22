# Gắn các goal Failsafe vào đúng phase trong POM Maven

## 1. Mục tiêu: chạy integration test đúng thời điểm, đánh giá kết quả đúng lúc

Trong một dự án Maven, kiểm thử đơn vị (unit test) và kiểm thử tích hợp (integration test, thường viết tắt **IT**) phục vụ những mục đích khác nhau:

- **Unit test** thường kiểm tra một đơn vị logic nhanh, ít phụ thuộc môi trường ngoài. Maven Surefire Plugin chạy các test này ở phase `test` theo default lifecycle thường gặp.
- **Integration test** kiểm tra sự phối hợp của các thành phần: ứng dụng đã đóng gói, tiến trình khác, cơ sở dữ liệu, dịch vụ HTTP, message broker hoặc hệ thống thật/giả lập phù hợp. Maven Failsafe Plugin được thiết kế để chạy và xác minh những bài test như vậy ở các phase phía sau `package`.

Điểm khác biệt quan trọng: **Failsafe có hai goal chính** với nhiệm vụ và thời điểm khác nhau:

1. **`failsafe:integration-test`**: chạy các integration tests và ghi kết quả. Theo thiết kế, lỗi assertion/test được ghi nhận mà không lập tức chặn lifecycle ngay tại goal này, để các bước dọn môi trường sau test còn cơ hội chạy.
2. **`failsafe:verify`**: đọc/tổng hợp kết quả do Failsafe ghi, rồi **đánh dấu build thất bại** khi integration tests thất bại theo chính sách đang cấu hình.

Do đó, không đủ chỉ khai báo plugin hoặc chỉ chạy `failsafe:integration-test`. Bài học này chỉ rõ cách **bind hai goal vào hai phase đúng trong `pom.xml`**, dùng Maven 3.9.x để minh họa; đồng thời xây dựng một dự án Java 17/JUnit 5 có unit test và integration test thật: integration test khởi chạy JAR đã được đóng gói ở phase `package` trong **một JVM con**, kiểm tra mã thoát và stdout.

```text
mvn clean verify
    |
    v
Maven lifecycle (jar packaging)
    |
    +--> compile + test-compile + test
    |         |
    |         +--> Surefire: CalculatorTest (2 unit tests)
    |
    +--> package
    |         |
    |         +--> Jar Plugin: tạo executable JAR
    |
    +--> pre-integration-test  (chuẩn bị môi trường nếu có goal gắn vào)
    |
    +--> integration-test
    |         |
    |         +--> Failsafe: integration-test
    |                |
    |                +--> CliIT chạy JAR bằng tiến trình Java riêng
    |                +--> ghi report và summary
    |
    +--> post-integration-test (dọn môi trường nếu có goal gắn vào)
    |
    +--> verify
              |
              +--> Failsafe: verify
                     |
                     +--> đánh giá summary, PASS hoặc FAIL build
```

Ở dự án ví dụ, không có server hoặc Docker cần khởi động, vì integration boundary được minh họa bằng **JAR và tiến trình JVM ngoài**. Vì vậy các phase `pre-integration-test` và `post-integration-test` vẫn có mặt trong lifecycle nhưng chưa có goal bổ sung nào được bind vào chúng.

## 2. Goal khác phase như thế nào?

Một số khái niệm Maven phải đọc chính xác:

| Khái niệm | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| **Lifecycle** | default | Trình tự các phase Maven thực hiện |
| **Phase** | `integration-test`, `verify` | Mốc trong lifecycle |
| **Plugin** | `maven-failsafe-plugin` | Artifact Maven cung cấp công cụ |
| **Goal** | `failsafe:integration-test` | Một thao tác do plugin định nghĩa |
| **Execution** | `run-integration-tests` | Định danh một lần bind goal/configuration trong POM |
| **Binding** | `goal=integration-test`, `phase=integration-test` | Nói Maven chạy goal nào khi lifecycle đạt phase nào |

Tên `integration-test` vừa xuất hiện như **phase** của Maven, vừa xuất hiện như **goal** của Failsafe, nhưng không nên xem đó là một khái niệm.

- `mvn integration-test` là yêu cầu chạy **default lifecycle đến phase `integration-test`**.
- `mvn failsafe:integration-test` là **gọi trực tiếp một goal của plugin**; nó không có nghĩa các phase trước như `package` tự được thực hiện trong cùng lệnh.
- `mvn verify` chạy toàn bộ các phase trước `verify`, gồm `package` và các phase kiểm thử tích hợp, **nếu các goals được bind đúng**.
- `mvn failsafe:verify` gọi trực tiếp goal kiểm tra kết quả Failsafe; nó không tự tạo JAR hay tự chạy các IT bị thiếu.

**Chốt về quy trình:** trong Maven 3, với integration tests được bind thông thường, lệnh nên chạy trên CI là **`mvn clean verify`** hoặc `mvn verify`, không dừng ở `mvn integration-test`.

## 3. Bốn phase quan trọng của kiểm thử tích hợp

Maven 3 có các phase chuyên dụng:

### 3.1. pre-integration-test

Đây là vị trí để chuẩn bị môi trường mà test sẽ tương tác:

- Bật database container hoặc một server kiểm thử.
- Chuẩn bị dữ liệu, cấu hình endpoint, certificate dành riêng cho test.
- Khởi tạo một hệ thống giả lập hoặc tài nguyên tạm.

Phase này **không tự khởi động server**. Bạn cần bind một goal của plugin tương ứng (ví dụ công cụ container hoặc dịch vụ thử nghiệm) nếu dự án thực sự cần bước chuẩn bị.

### 3.2. integration-test

Đây là vị trí để chạy IT bằng Failsafe:

```text
phase: integration-test
goal:  org.apache.maven.plugins:maven-failsafe-plugin:integration-test
```

Failsafe thường tìm các class test theo conventions của IT, ví dụ `*IT` hoặc `IT*`, rồi chạy chúng qua test provider/JUnit Platform phù hợp.

**Kết quả test thất bại** được Failsafe ghi vào reports/summary để chờ `failsafe:verify`. Tuy nhiên, không nên khẳng định **mọi** lỗi đều được trì hoãn: lỗi cấu hình plugin, thiếu artifact, lỗi khởi động runner hoặc vấn đề hạ tầng có thể khiến build lỗi sớm. Cơ chế trì hoãn đặc trưng áp dụng cho những **thất bại kiểm thử** mà Failsafe xử lý được.

### 3.3. post-integration-test

Đây là vị trí để **dọn tài nguyên** do pre-integration-test tạo:

- Stop server/container.
- Giải phóng port, file tạm, tài khoản hoặc dữ liệu test.
- Thu thập logs/coverage sau khi test.

Một ưu điểm của Failsafe là assertion failure trong IT không dừng ngay ở `integration-test`, nên goal dọn dẹp ở `post-integration-test` còn có thể chạy trước khi build bị đánh FAIL tại `verify`.

Cũng như pre-phase, **không có goal dọn dẹp mặc định** chỉ vì Failsafe đã được khai báo. Nếu plugin riêng của bạn khởi động môi trường, bạn cần cấu hình cả bước stop/cleanup đúng phase.

### 3.4. verify

Đây là phase đánh giá kết quả tổng thể, nơi bind:

```text
phase: verify
goal:  org.apache.maven.plugins:maven-failsafe-plugin:verify
```

Goal `failsafe:verify` đọc dữ liệu tổng kết của Failsafe, theo mặc định trong:

```text
target/failsafe-reports/failsafe-summary.xml
```

Nếu các bài IT thất bại và chính sách không bỏ qua failure, goal này làm build thất bại. Những bước cleanup đã gắn vào `post-integration-test` có cơ hội thực hiện **trước** việc đánh giá fail cuối.

### 3.5. Vì sao không dừng ở integration-test?

Với **Maven 3.9.x** dùng trong bài thực hành, nếu gọi trực tiếp phase `integration-test`, các phase **phía sau** như `post-integration-test` và `verify` không tự được chạy:

```bash
mvn integration-test
```

Điều đó có thể để lại môi trường test đang hoạt động và chưa đánh giá summary để fail build. **Không dùng lệnh này làm bằng chứng toàn bộ IT đã qua**.

Lưu ý phiên bản: Maven 4 có thay đổi về xử lý một số before/after phase; hành vi cụ thể không nên suy từ Maven 3 sang Maven 4. Nội dung và các lệnh ví dụ ở đây được kiểm soát cho **Maven 3.9.x**. Trong cả hai trường hợp, với workflow Failsafe thông dụng, `mvn verify` vẫn là mốc hoàn thành rõ ràng.

## 4. Cấu hình tối thiểu: bind bằng default phase của goal

Maven Failsafe Plugin có hai goal chính:

- `integration-test`: default phase là `integration-test`.
- `verify`: default phase là `verify`.

Vì hai goal đã có default phases, cấu hình thường gặp trong tài liệu chính thức là:

```xml
<build>
    <plugins>
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
    </plugins>
</build>
```

Đây là **đoạn dưới `<project>`**, không phải POM đầy đủ. Khi Maven lập execution plan, nó sử dụng default phase của từng goal. Hai goal **không nhất thiết cùng chạy ở một phase** chỉ vì chúng được liệt kê trong một `<execution>`.

Với cấu hình trên, `mvn verify` sẽ gọi Failsafe ở những mốc thích hợp, miễn dự án có đủ test dependencies và build configuration cần thiết.

**Khi nào nên dùng cách này?** Khi bạn muốn cấu hình gọn và không cần giải thích chi tiết từng execution, đồng thời chấp nhận phụ thuộc vào default phase được plugin descriptor công bố.

**Khi nào nên viết phase tường minh?** Khi mục tiêu là học về binding, cần đặt ID riêng cho từng execution, hoặc cần configuration khác nhau cho từng goal. Bài ví dụ sẽ dùng cách tường minh ở mục tiếp theo.

## 5. Cấu hình tường minh: hai executions và hai phases

Đây là cấu hình dễ đọc trong code review, vì phase và goal được đặt kề nhau:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-failsafe-plugin</artifactId>
    <version>3.5.2</version>

    <executions>
        <execution>
            <id>run-integration-tests</id>
            <phase>integration-test</phase>
            <goals>
                <goal>integration-test</goal>
            </goals>
        </execution>

        <execution>
            <id>check-integration-results</id>
            <phase>verify</phase>
            <goals>
                <goal>verify</goal>
            </goals>
        </execution>
    </executions>
</plugin>
```

**Đây chỉ là một phần tử `<plugin>`**, phải nằm trong `<build><plugins>` của POM dự án thật.

Giải thích:

- `<id>run-integration-tests</id>` giúp nhận diện lượt chạy test trong log và model.
- `<phase>integration-test</phase>` gắn goal `failsafe:integration-test` vào phase chạy IT.
- `<id>check-integration-results</id>` định danh lượt đánh giá.
- `<phase>verify</phase>` gắn goal `failsafe:verify` vào phase đánh giá kết quả.
- `<goals><goal>...</goal></goals>` chọn **tên goal bên trong plugin hiện tại**, không cần viết lại prefix `failsafe:` trong thẻ `goal`.

**Tránh lỗi sai:** nếu đặt cả hai goal trong **một execution có `<phase>integration-test</phase>` tường minh**, bạn có thể khiến `verify` chạy **quá sớm** ở phase integration-test. Tương tự, nếu để `verify` ở `package`, nó có thể kiểm tra report chưa được tạo. Hãy chọn một trong hai mẫu đúng: **mẫu một execution không có phase** để Maven dùng default phase từng goal, hoặc **mẫu hai executions có phase riêng** như trên.

## 6. Plugin configuration chung và riêng execution

Maven cho phép đặt cấu hình:

- **Ở cấp plugin**: phần `<configuration>` trực tiếp dưới `<plugin>`; các tham số tương ứng được dùng cho những goals của plugin phù hợp.
- **Ở cấp execution**: phần `<configuration>` bên trong một `<execution>`; khi cần, có thể khác với cấu hình chung cho execution đó.

Ví dụ cấu hình chung cho Failsafe:

```xml
<configuration>
    <failIfNoTests>true</failIfNoTests>
    <systemPropertyVariables>
        <demo.jar>${project.build.directory}/${project.build.finalName}.jar</demo.jar>
    </systemPropertyVariables>
</configuration>
```

Đoạn này thuộc `<plugin>` Failsafe, **không phải cấu hình của Compiler hoặc Surefire Plugin**.

- `failIfNoTests=true`: chặn tình huống không có integration tests được chọn khi dự án này **bắt buộc phải có IT**.
- `systemPropertyVariables`: đưa system property tới process chạy IT (khi plugin/provider thực thi test), để test biết đường dẫn JAR đã được build.
- Property `demo.jar` là tên **do bài ví dụ tự đặt**; trong Java đọc qua `System.getProperty("demo.jar")`.
- `${project.build.directory}` và `${project.build.finalName}` là Maven expressions trong POM, được Maven nội suy thành đường dẫn và tên artifact.

Tham số cho một goal cụ thể phải được plugin hỗ trợ; **không dùng một cấu hình XML ngẫu nhiên rồi mặc định mọi goal sẽ hiểu nó**. Cách kiểm chứng là tài liệu goal và:

```bash
mvn help:describe -Dplugin=org.apache.maven.plugins:maven-failsafe-plugin -Dgoal=integration-test -Ddetail
mvn help:describe -Dplugin=org.apache.maven.plugins:maven-failsafe-plugin -Dgoal=verify -Ddetail
```

Lưu ý `failsafe:verify` đọc summary, không trực tiếp thực thi mã test; không cần truyền property tới goal verify để nó tìm `CliIT`.

## 7. Tại sao Failsafe không tự chạy chỉ vì có trong POM?

Một POM có thể khai báo:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-failsafe-plugin</artifactId>
    <version>3.5.2</version>
</plugin>
```

**Chỉ liệt kê plugin chưa đủ để thêm hai goal vào lifecycle** của dự án dạng `jar`. Bạn cần `<executions>` phù hợp hoặc gọi goal trực tiếp. Với dự án thực tế, dùng lifecycle bindings là cách rõ ràng vì CI chỉ cần gọi `mvn verify`.

Tương tự, `<pluginManagement>` ở POM cha có thể **quản lý version và configuration** để module dùng khi kích hoạt plugin, nhưng bản thân nó **không phải lệnh bắt chạy thêm một goal**.

Khi kiểm tra một dự án Maven có parent POM, profile hoặc pluginManagement, nên nhìn **effective POM** để thấy execution cuối cùng thay vì chỉ xem một đoạn ở child module:

```bash
mvn help:effective-pom
mvn help:active-profiles
```

Nếu module không thực sự kích hoạt plugin/executions đúng cách, `mvn verify` có thể thành công nhưng không chạy IT nào.

## 8. Ví dụ hoàn chỉnh Java 17: đóng JAR rồi chạy integration test

Dự án này có thể chạy mà **không cần Docker, server hoặc database**. Integration test khởi chạy **JAR đã đóng gói** bằng một tiến trình Java mới, quan sát kết quả bên ngoài JVM chạy JUnit. Nhờ vậy ta thấy rõ vì sao `package` phải có trước `integration-test`.

### 8.1. Yêu cầu và cấu trúc thư mục

Cần:

- Maven **3.9.x** (hoặc bản Maven 3 tương thích với các plugins sử dụng).
- JDK **17 trở lên** và lệnh `mvn` trong PATH.
- Kết nối repository phù hợp để tải plugins và JUnit trong lần chạy đầu nếu cache chưa có.

Cấu trúc:

```text
failsafe-phase-demo/
├── pom.xml
└── src/
    ├── main/
    │   └── java/dev/lesson/
    │       ├── Calculator.java
    │       └── App.java
    └── test/
        └── java/dev/lesson/
            ├── CalculatorTest.java
            └── CliIT.java
```

Tên lớp được chọn có chủ đích:

- `CalculatorTest.java` phù hợp conventions của **Surefire**, nên chạy như unit test ở phase `test`.
- `CliIT.java` phù hợp conventions của **Failsafe**, nên chạy như integration test ở phase `integration-test`.
- Hai lớp đều ở `src/test/java` và dùng JUnit Jupiter API. Khác nhau chủ yếu là **plugin nào chọn test class và thời điểm nào test được thực thi**.

### 8.2. pom.xml độc lập, đầy đủ

Tạo `failsafe-phase-demo/pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.lesson</groupId>
    <artifactId>failsafe-phase-demo</artifactId>
    <version>1.0.0-SNAPSHOT</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.junit</groupId>
                <artifactId>junit-bom</artifactId>
                <version>5.11.4</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.junit.platform</groupId>
            <artifactId>junit-platform-launcher</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-clean-plugin</artifactId>
                <version>3.4.1</version>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
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
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
                <configuration>
                    <archive>
                        <manifest>
                            <mainClass>dev.lesson.App</mainClass>
                        </manifest>
                    </archive>
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
                        <id>run-integration-tests</id>
                        <phase>integration-test</phase>
                        <goals>
                            <goal>integration-test</goal>
                        </goals>
                    </execution>
                    <execution>
                        <id>check-integration-results</id>
                        <phase>verify</phase>
                        <goals>
                            <goal>verify</goal>
                        </goals>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
```

Cách đọc POM:

1. Maven Compiler Plugin dùng Java release 17 theo property.
2. JUnit BOM 5.11.4 quản lý các version tương thích của JUnit Jupiter 5.11.4 và Platform 1.11.4.
3. JUnit dependencies ở scope `test`, không trở thành runtime dependencies của chương trình CLI.
4. Surefire Plugin **3.5.2** được dùng ở phase `test` theo lifecycle mapping của packaging `jar`.
5. Jar Plugin tạo JAR có manifest `Main-Class: dev.lesson.App`, cho phép dùng `java -jar`.
6. Failsafe Plugin **3.5.2** có hai executions tường minh: `integration-test` và `verify`.
7. `demo.jar` được cấp qua `systemPropertyVariables`, để IT mở đúng JAR vừa tạo.
8. `failIfNoTests=true` là chốt dành cho dự án demo **luôn phải có** unit tests và integration tests. Một dự án nhiều module có module không có IT có thể cần policy khác phù hợp.

POM không có custom goals ở `pre-integration-test` hoặc `post-integration-test`, bởi bài ví dụ không cần tài nguyên ngoài. Điều đó **không làm sai binding Failsafe**.

### 8.3. Java application: Calculator

Tạo `src/main/java/dev/lesson/Calculator.java`:

```java
package dev.lesson;

public final class Calculator {
    private Calculator() {
    }

    public static int sum(int left, int right) {
        return Math.addExact(left, right);
    }
}
```

Dùng `Math.addExact` thay vì phép cộng int trần để từ chối overflow. Không có external runtime dependency.

### 8.4. Điểm vào App

Tạo `src/main/java/dev/lesson/App.java`:

```java
package dev.lesson;

public final class App {
    private App() {
    }

    public static void main(String[] args) {
        if (args.length != 2) {
            System.err.println("need two integers");
            System.exit(2);
            return;
        }

        int left = Integer.parseInt(args[0]);
        int right = Integer.parseInt(args[1]);
        System.out.println("sum=" + Calculator.sum(left, right));
    }
}
```

Với hai đối số `9` và `5`, App in một dòng ASCII ổn định:

```text
sum=14
```

Dùng ASCII cho stdout ở ví dụ này để việc so sánh đầu ra từ **tiến trình JVM con** không phụ thuộc encoding terminal, nhưng phần giải thích vẫn bằng tiếng Việt.

### 8.5. Hai unit tests chạy qua Surefire

Tạo `src/test/java/dev/lesson/CalculatorTest.java`:

```java
package dev.lesson;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class CalculatorTest {
    @Test
    void addsTwoNumbers() {
        assertEquals(14, Calculator.sum(9, 5));
    }

    @Test
    void detectsOverflow() {
        assertThrows(ArithmeticException.class,
                () -> Calculator.sum(Integer.MAX_VALUE, 1));
    }
}
```

Surefire quét lớp có hậu tố `Test`, dùng JUnit Jupiter Engine và chạy **2 unit test methods** trong phase `test`, trước khi JAR của dự án được đóng gói. Unit tests không cần tệp JAR đích.

### 8.6. Integration test khởi chạy JAR trong JVM con

Tạo `src/test/java/dev/lesson/CliIT.java`:

```java
package dev.lesson;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Locale;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.junit.jupiter.api.Assertions.fail;

class CliIT {
    @Test
    void runsPackagedApplication() throws Exception {
        String configured = System.getProperty("demo.jar");
        assertNotNull(configured, "Failsafe must supply demo.jar");

        Path jar = Path.of(configured).toAbsolutePath();
        assertTrue(Files.isRegularFile(jar),
                () -> "Packaged JAR not found: " + jar);

        boolean windows = System.getProperty("os.name")
                .toLowerCase(Locale.ROOT)
                .startsWith("windows");
        String binary = windows ? "java.exe" : "java";
        Path java = Path.of(System.getProperty("java.home"),
                "bin", binary);

        Process child = new ProcessBuilder(
                java.toString(),
                "-jar", jar.toString(), "9", "5")
                .redirectErrorStream(true)
                .start();

        if (!child.waitFor(15, TimeUnit.SECONDS)) {
            child.destroyForcibly();
            fail("Child Java process did not finish in 15 seconds");
        }

        String output = new String(
                child.getInputStream().readAllBytes(),
                StandardCharsets.UTF_8).strip();

        assertEquals(0, child.exitValue());
        assertEquals("sum=14", output);
    }
}
```

Vì đây là **một integration test cần JAR đã được đóng gói**, nếu chạy sai thứ tự và tệp chưa có, assertion `Files.isRegularFile(jar)` sẽ thất bại.

Các chi tiết kỹ thuật làm ví dụ đáng tin:

- `System.getProperty("demo.jar")` lấy đường dẫn do Maven Failsafe truyền tới test JVM; không ghi cứng đường dẫn máy cá nhân.
- `Path.of(...).toAbsolutePath()` chỉ tới JAR của project hiện tại.
- Cách xác định `java.exe` so với `java` dựa trên tiền tố `windows` của `os.name`, **không chỉ dùng `contains("win")`**, vì tên hệ điều hành khác có thể chứa chuỗi tương tự.
- JVM con được chọn từ `java.home/bin` của môi trường chạy test, tránh vô tình chọn lệnh `java` không tương ứng từ PATH.
- `ProcessBuilder` chạy chính artifact đầu ra, nên IT kiểm tra **đường biên build artifact → JVM mới → stdout/exit code** chứ không chỉ gọi lại `Calculator.sum`.
- `redirectErrorStream(true)` gộp stderr vào cùng luồng để có thể đọc kết quả; ví dụ chỉ in một dòng nhỏ nên việc chờ tiến trình rồi đọc output không làm đầy pipe. Với chương trình có lượng output lớn, cần xử lý streams bất đồng bộ để tránh deadlock.
- Có timeout 15 giây và `destroyForcibly()` khi child không kết thúc, tránh integration test treo vô hạn.
- Output dùng ASCII `sum=14` nên giải mã UTF-8 là ổn định cho dữ liệu của bài; chương trình thực tế có Unicode cần định nghĩa encoding ở cả hai phía.

**Vì sao đặt tên `CliIT`?** Failsafe mặc định quét các tên kiểu `*IT`, trong khi Surefire không quét lớp này theo patterns unit-test thường gặp. Đó là cách cùng một `src/test/java` được tách theo **phase/plugin** mà không cần module source test riêng.

### 8.7. Lệnh build và stdout

Chạy từ thư mục `failsafe-phase-demo` chứa `pom.xml`:

```bash
mvn -version
mvn clean verify
```

Với các điều kiện đã nêu và không có lỗi khác, kết quả logic dự kiến:

- **Surefire**: `CalculatorTest` chạy **2 tests**, không có failures/errors.
- **Jar Plugin**: tạo `target/failsafe-phase-demo-1.0.0-SNAPSHOT.jar`.
- **Failsafe integration-test**: `CliIT` chạy **1 integration test**, khởi động được JAR bằng Java process và kiểm tra output.
- **Failsafe verify**: đọc summary IT và hoàn thành đánh giá.
- Maven kết thúc **`BUILD SUCCESS`**.

Phần số liệu quan trọng trong output tương tự:

```text
CalculatorTest: Tests run: 2, Failures: 0, Errors: 0, Skipped: 0
CliIT: Tests run: 1, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
```

Đây là **minh họa số liệu cần đối chiếu**, không phải copy nguyên log Maven. Plugin có thể thêm timestamp, thời gian, prefix, đường dẫn và định dạng khác nhau.

Chạy trực tiếp artifact ngoài Maven:

```bash
java -jar target/failsafe-phase-demo-1.0.0-SNAPSHOT.jar 9 5
```

Stdout đúng là:

```text
sum=14
```

Không cần JUnit ở runtime của ứng dụng vì các lớp sản phẩm chỉ dùng Java Standard Library; JUnit phục vụ những lớp kiểm thử ở scope `test`.

### 8.8. Các đường dẫn kết quả cần tìm

Sau `mvn clean verify` thành công:

```text
target/classes/dev/lesson/Calculator.class
target/classes/dev/lesson/App.class
target/test-classes/dev/lesson/CalculatorTest.class
target/test-classes/dev/lesson/CliIT.class
target/failsafe-phase-demo-1.0.0-SNAPSHOT.jar

target/surefire-reports/
target/failsafe-reports/
target/failsafe-reports/failsafe-summary.xml
```

Thư mục `surefire-reports` chứa thông tin unit tests. Thư mục `failsafe-reports` chứa thông tin integration tests và summary cần cho `failsafe:verify`. Tên từng file TXT/XML báo cáo có thể khác nhau theo cấu hình, nhưng vị trí này là mặc định thông dụng.

## 9. So sánh ba lệnh có thể dễ nhầm

Dùng **POM và nguồn giống nhau**:

| Lệnh | Những bước chính đạt tới trong Maven 3.9.x | Kết luận hợp lệ |
| --- | --- | --- |
| `mvn clean test` | Biên dịch source/test, Surefire chạy unit tests | Đã kiểm tra unit tests; **chưa** đóng gói JAR/IT |
| `mvn clean package` | Như trên, sau đó tạo JAR | Artifact đã được tạo; **chưa** chạy Failsafe IT |
| `mvn clean integration-test` | Build tới package rồi Failsafe integration-test | IT có thể đã chạy, nhưng **chưa tới post-integration-test/verify** trong Maven 3 |
| `mvn clean verify` | Đi hết package, IT, post-IT và verify | **Chốt workflow tích hợp** theo các goals đã bind |
| `mvn failsafe:integration-test` | Gọi trực tiếp goal | Không tự đảm bảo JAR hay môi trường đã được chuẩn bị |
| `mvn failsafe:verify` | Chỉ đọc/đánh giá kết quả IT đã tồn tại | Không tự chạy toàn bộ integration tests |
| `mvn -Dit.test=CliIT verify` | Chạy lifecycle tới verify với bộ IT được chọn theo Failsafe | Có thể hữu ích khi debug, nhưng không thay cho full suite |

**Cẩn thận khi dùng lệnh `mvn clean test` với `failIfNoTests=true`:** trong demo có `CalculatorTest` nên pass. Nhưng một module chuyên IT, không có unit test, có thể cần policy Surefire khác nếu chỉ có class `*IT`.

### 9.1. Thử riêng một integration test

Failsafe hỗ trợ property chọn IT:

```bash
mvn -Dit.test=CliIT verify
```

Trên Windows PowerShell có thể quote đối số:

```powershell
mvn '-Dit.test=CliIT' verify
```

Nếu bạn muốn kiểm tra artifact luôn được làm mới, dùng `mvn clean verify` cùng lựa chọn test tương ứng:

```bash
mvn -Dit.test=CliIT clean verify
```

Lưu ý `-Dit.test` phục vụ lựa chọn của Failsafe; Surefire vẫn có thể chạy những unit tests bình thường ở phase `test` nếu không cấu hình khác.

Không dùng `mvn failsafe:integration-test -Dit.test=CliIT` trên một checkout chưa đóng gói JAR rồi kết luận cấu hình Failsafe sai khi test không tìm thấy artifact. **Gọi goal trực tiếp bỏ qua nhiều phase cần thiết.**

## 10. Thí nghiệm cố ý làm integration test thất bại

Sau khi demo ban đầu đã chạy thành công, thử sửa **một assertion** trong `CliIT.java`:

Từ:

```java
assertEquals("sum=14", output);
```

Thành (cố ý sai):

```java
assertEquals("sum=15", output);
```

Chạy lại:

```bash
mvn clean verify
```

Đây là **thí nghiệm tạo lỗi**, không phải thay đổi nên giữ trong bản chính.

Diễn biến mong đợi trên Maven 3.9.x và Failsafe 3.5.2:

1. Unit tests của `CalculatorTest` vẫn pass.
2. JAR được đóng gói thành công.
3. `failsafe:integration-test` chạy `CliIT`; assertion thất bại và kết quả được ghi trong Failsafe reports.
4. Maven tiếp tục qua `post-integration-test`, nơi một dự án thật có thể bind plugin để dừng container/thu hồi tài nguyên.
5. `failsafe:verify` đọc report rồi **làm build thất bại**.

Nếu gọi chỉ tới phase `integration-test` của Maven 3, test fail có thể đã được ghi nhận nhưng **chưa được Failsafe verify chuyển thành build failure**. Đó là nguyên nhân phải có cả hai goal và kết thúc ở phase `verify`.

Sau thí nghiệm, **khôi phục `assertEquals("sum=14", output)`**, chạy:

```bash
mvn clean verify
```

Đối chiếu báo cáo về 0 failure rồi mới chốt PASS cho bài học.

### 10.1. Điều gì không được hứa khi test lỗi?

Không nên hiểu Failsafe sẽ bảo đảm mọi cleanup xảy ra khi JVM bị tắt đột ngột, máy mất điện hoặc một plugin ném lỗi cấu hình trước khi Maven kịp chạy post-phase. Failsafe giúp trì hoãn **thất bại của test mà nó ghi nhận được** để post-integration-test có cơ hội chạy; nó không thay thế cơ chế bảo đảm cleanup của hệ thống vận hành.

Trong CI có môi trường ngoài, nên kết hợp teardown rõ ràng, timeout, idempotent cleanup và cơ chế cleanup cấp runner/orchestrator nếu cần.

## 11. Gắn plugin chuẩn bị và dọn môi trường thế nào?

Với integration tests dùng một service thật, mô hình đúng là:

```text
pre-integration-test
    └── plugin-goal START môi trường test

integration-test
    └── failsafe:integration-test

post-integration-test
    └── plugin-goal STOP/TEARDOWN môi trường

verify
    └── failsafe:verify
```

Cú pháp khái niệm cho plugin chuẩn bị/dọn dẹp, sử dụng **tên goal giả định** để diễn giải vị trí — **KHÔNG copy nguyên vào POM**:

```xml
<executions>
    <execution>
        <id>start-test-env</id>
        <phase>pre-integration-test</phase>
        <goals>
            <goal>start</goal>
        </goals>
    </execution>
    <execution>
        <id>stop-test-env</id>
        <phase>post-integration-test</phase>
        <goals>
            <goal>stop</goal>
        </goals>
    </execution>
</executions>
```

**Quan trọng:** `start` và `stop` ở đoạn trên là **tên goal giả định** của một plugin có hỗ trợ chúng, không phải goals của Maven Failsafe Plugin. Failsafe chỉ có goals chuyên biệt để **chạy và verify IT**. Muốn dùng Jetty, Cargo, Docker hoặc một container plugin thật, hãy kiểm tra đúng tài liệu goal/version trước khi bind; một số công cụ có tên goal khác và cơ chế cleanup riêng.

### 11.1. Tránh chạy server ở chế độ chặn

Nếu plugin ở `pre-integration-test` khởi chạy server trong foreground rồi không trả quyền điều khiển cho Maven, lifecycle sẽ không tới `integration-test`. Với những plugin hỗ trợ, cần một goal hoặc mode khởi động server **non-blocking** rồi để goal khác dừng ở post-phase.

Đừng nghĩ chỉ thêm `<phase>pre-integration-test</phase>` vào bất kỳ `start` goal nào cũng đủ; phải đọc hành vi của plugin và xác nhận tiến trình vẫn tiếp tục được.

### 11.2. Teardown và dữ liệu thử nghiệm

Một integration test dùng database thật có thể thay đổi dữ liệu. Nên:

- Dùng database/schema/tài khoản riêng cho test; không trỏ vào production.
- Đặt cleanup ở post-phase, đồng thời có fallback dọn ngoài Maven nếu cần.
- Không lưu credentials trực tiếp vào POM hoặc log.
- Có timeout và bước kiểm tra môi trường đã dừng.
- Không chạy một bước `deploy` thật chỉ để thử Failsafe nếu không được cấp quyền.

Đây là những yêu cầu môi trường test, **không phải mặc định của Failsafe**.

## 12. Surefire và Failsafe khác nhau ở thời điểm và tập test

| Nội dung | Surefire | Failsafe |
| --- | --- | --- |
| Plugin | `maven-surefire-plugin` | `maven-failsafe-plugin` |
| Thời điểm mặc định thường dùng | `test` | `integration-test` rồi `verify` |
| Mục tiêu | Unit tests | Integration tests |
| Patterns mặc định tiêu biểu | `Test*`, `*Test`, `*Tests`, `*TestCase` | `IT*`, `*IT`, `*ITCase` |
| Reports | `target/surefire-reports` | `target/failsafe-reports` |
| Cơ chế báo test failure | Thường fail ngay trong phase test | Tách chạy test và verify kết quả |
| Framework | JUnit 4/5, TestNG... theo provider | Có thể dùng cùng framework phù hợp |
| Có cần bind execution bổ sung cho project jar? | `surefire:test` thường đã được lifecycle map | **Có**, nên khai báo goals Failsafe trong POM |

**Tên test class quyết định nhiều điều.** Nếu đặt class integration test tên `CliTest`, Surefire có thể quét và chạy nó ở phase `test`, **trước khi JAR được tạo**, gây lỗi thiếu artifact. Dùng `CliIT` giúp tách đúng vào Failsafe.

Ngược lại, nếu đặt unit test thành `CalculatorIT`, Surefire có thể không chạy nó theo patterns mặc định; Failsafe mới quét ở phase sau.

Hai plugin thường dùng cùng `src/test/java` và cùng JUnit Jupiter dependencies, nhưng **quy ước quét tên và phase khác nhau**. Không mặc định mỗi plugin đòi một source folder riêng.

## 13. Vì sao JUnit Platform và TestEngine vẫn quan trọng cho Failsafe?

Failsafe không phải JUnit Jupiter engine. Nó cần một provider tương thích và những dependencies JUnit phù hợp trong test classpath.

Với POM mẫu:

```xml
<dependency>
    <groupId>org.junit.jupiter</groupId>
    <artifactId>junit-jupiter</artifactId>
    <scope>test</scope>
</dependency>
```

JUnit Jupiter aggregator bao gồm API, Params và Jupiter Engine theo metadata của version được BOM quản lý. `junit-platform-launcher` là API phục vụ tooling/launcher, không thay TestEngine; POM đưa nó vào scope test để giữ version Platform phù hợp.

Đối với Failsafe 3.5.2, version JUnit Platform provider có thể được plugin chọn dựa trên test dependencies. Không cần khai báo `surefire-junit-platform` như một **project dependency** của ứng dụng; đó là thành phần provider của hệ plugin.

**Khi gặp lỗi `No TestEngine available` hoặc `NoSuchMethodError`**, hãy kiểm tra graph version JUnit Jupiter/Platform, BOM, parent, các exclusions và provider/launcher. Đừng sửa bằng cách copy JAR từ local repository của máy khác vào `target/classes`.

## 14. Chính sách failIfNoTests và skipITs

Trong POM demo, mỗi plugin có:

```xml
<failIfNoTests>true</failIfNoTests>
```

Chính sách này phù hợp cho dự án **bắt buộc có test**; nó giúp phát hiện chuyện Surefire/Failsafe không tìm được class theo pattern hoặc bị loại bởi cấu hình. Tuy nhiên:

- Với một aggregator module `pom` không có source test, bạn không nên bắt buộc không có test là lỗi nếu plugin được thực thi không cần thiết.
- Một plugin chạy được 1 test nhưng vô tình bỏ sót 20 test khác vẫn có thể PASS; phải kiểm tra test count.
- Nếu tests được skip một cách có chủ đích, kết quả `BUILD SUCCESS` không đồng nghĩa mọi test đã chạy.

Failsafe có property **`skipITs`** dành cho việc bỏ qua integration tests khi cần:

```bash
mvn -DskipITs=true clean verify
```

Không sử dụng lệnh này để chứng minh integration tests pass; chỉ dùng khi mục đích thật sự là **bỏ qua IT**, chẳng hạn một nhánh pipeline chuyên build artifact.

Phân biệt với `-DskipTests` của Surefire: cách hai plugin nhận property/parameter có khác biệt theo phiên bản. Với Failsafe, dùng **`-DskipITs`** để diễn đạt rõ việc skip IT. Còn `-Dmaven.test.skip=true` có thể làm bỏ cả compile/test ở những plugins hỗ trợ, không phù hợp cho một pipeline QA đầy đủ.

Nếu muốn bỏ qua IT khi test environment không có, tốt hơn là dùng Maven profile có chủ đích hoặc phân tách pipeline rõ ràng, rồi xác minh profile/flags nào đã active ở CI.

## 15. Failsafe báo cáo và nơi verify đọc kết quả

Sau khi Failsafe chạy, thư mục điển hình:

```text
target/failsafe-reports/
├── TEST-dev.lesson.CliIT.xml
├── dev.lesson.CliIT.txt
└── failsafe-summary.xml
```

Tên tệp reports có thể thay đổi theo cấu hình, nhưng summary mặc định quan trọng là `failsafe-summary.xml`. Goal `failsafe:verify` kiểm tra dữ liệu này và quyết định kết quả build.

Để đọc kết quả sau `mvn clean verify`:

- Xem tổng tests/failures/errors/skipped của Surefire và Failsafe trong log.
- Mở `target/failsafe-reports` để tìm stack trace khi IT lỗi.
- Kiểm tra summary XML và các test case reports khi cần xác định lỗi.
- Nếu test chạy theo nhiều execution hoặc module, xem paths tương ứng chứ không giả định chỉ có một file.

**Không coi việc file XML tồn tại là điều kiện PASS.** Có report thì test có thể đã được chạy và thất bại. Cần kiểm tra kết quả và trạng thái `failsafe:verify`.

### 15.1. Không ghi đè summaryFile tùy tiện

Failsafe cho phép cấu hình đường dẫn `summaryFile`, nhưng các goal `integration-test` và `verify` **phải cùng nhìn đúng dữ liệu kết quả**. Nếu một execution ghi summary ở đường dẫn A còn verify đọc B, bạn có thể gặp báo cáo không khớp hoặc việc verify không đánh giá được đúng test run.

Bài ví dụ **không override summaryFile**, nên hai goal dùng default thống nhất. Chỉ thay khi có mục đích thực sự, chẳng hạn tách nhiều lượt IT với cấu hình rõ ràng.

## 16. Cách xem Maven thật sự bind goal vào phase nào

Khi code review, đừng chỉ nhìn trong POM một đoạn có `maven-failsafe-plugin`. Cần xác nhận rằng execution được đưa vào effective build:

```bash
mvn -version
mvn help:effective-pom
mvn help:active-profiles
mvn clean verify
```

Trong log Maven 3.9.x, bạn có thể thấy các đoạn tương tự:

```text
... maven-surefire-plugin:3.5.2:test (default-test) ...
... maven-jar-plugin:3.4.2:jar (default-jar) ...
... maven-failsafe-plugin:3.5.2:integration-test (run-integration-tests) ...
... maven-failsafe-plugin:3.5.2:verify (check-integration-results) ...
```

Đây là **minh họa về thứ tự goal và execution ID**, không phải log đầy đủ để so khớp nguyên văn: Maven có thể ghi prefix, tên project và phiên bản khác.

Với cấu hình kế thừa từ parent/profile:

- Một parent có thể khai báo executions; child có thể merge/override theo ID.
- `pluginManagement` quản lý plugin nhưng không mặc định tạo một execution mới trong child.
- Active profiles có thể bật/tắt plugin hoặc điều chỉnh configurations.
- Các module trong multi-module reactor có thể có cấu hình Surefire/Failsafe khác nhau.

Lệnh debug nâng cao:

```bash
mvn -X clean verify
```

Nó có thể cho thấy execution plan chi tiết và tham số của các goals. Hãy kiểm tra log trước khi chia sẻ vì `-X` có thể lộ đường dẫn môi trường, URL repository và thông tin cấu hình nội bộ.

## 17. Những lỗi cấu hình phổ biến

| Triệu chứng | Nguyên nhân ưu tiên kiểm tra | Cách khắc phục |
| --- | --- | --- |
| `mvn verify` không chạy IT | Failsafe chưa được bind goals vào lifecycle | Thêm executions đúng như mục 5 |
| Chỉ có `failsafe:integration-test` | Thiếu `failsafe:verify` | Bind verify vào phase `verify` |
| IT thất bại nhưng CLI trả thành công khi dừng `integration-test` | Chưa chạy phase `verify` trong Maven 3 | Dùng `mvn verify` |
| Server test không dừng | Không có goal stop ở post-phase hoặc đã dừng build quá sớm | Bind teardown vào `post-integration-test`, có fallback cleanup |
| Maven gọi `failsafe:verify` ở integration-test | Cả hai goals bị gắn cùng phase tường minh | Tách executions hoặc bỏ phase chung để dùng default phases |
| `CliIT` báo không thấy JAR | IT gọi quá sớm hoặc package chưa chạy | Dùng `mvn clean verify`; xác nhận Jar Plugin và path |
| `CliIT` không được phát hiện | Tên class/filters khác conventions Failsafe | Dùng `*IT`/`IT*` hoặc cấu hình includes |
| Surefire chạy integration test quá sớm | Tên IT khớp patterns Surefire | Đổi tên thành `CliIT` hoặc cấu hình excludes/includes |
| Unit tests không chạy | Surefire bị skip, class name sai hoặc plugin version | Xem phase test và reports |
| Failsafe không có engine JUnit | JUnit dependency/provider/Platform mismatch | Dùng Jupiter Engine/aggregator, kiểm tra BOM và tree |
| Chỉ có plugin trong pluginManagement | Chưa kích hoạt plugin/executions phù hợp | Khai báo trong `build/plugins`/child theo nhu cầu |
| IT reports có failure nhưng `verify` pass bất thường | Verify không đọc đúng summary hoặc testFailureIgnore | Kiểm tra `summaryFile`, plugin configuration và flags |
| `mvn package` pass nhưng CI chưa kiểm tra integration | Package dừng trước các IT phases | Chạy `verify` khi cần chốt |
| `-DskipITs=true` nhưng nhóm tưởng đã test | IT bị bỏ qua | Không dùng skip trong job QA chính |
| Build khác laptop và CI | JDK, settings, profiles, môi trường service khác | So sánh `mvn -version`, effective POM và endpoint |
| JAR chạy được thủ công nhưng CliIT lỗi timeout | Child process/env/timeout hoặc startup có vấn đề | Đọc lỗi/log, kiểm tra đường dẫn Java và timeout |

**Không sửa lỗi bằng cách tắt Failsafe hoặc đặt `testFailureIgnore=true` để luôn có `BUILD SUCCESS`**. Cách đó che kết quả QA; hãy tìm đúng phase/goal, reports và lỗi tích hợp thật sự.

## 18. Multi-module và profile: bind IT chỉ nơi cần

Trong một reactor nhiều module:

```text
workspace/
├── pom.xml             (packaging=pom)
├── core/
│   └── pom.xml         (library)
├── cli/
│   └── pom.xml         (app tạo JAR)
└── e2e-tests/
    └── pom.xml         (có integration tests)
```

Không phải module nào cũng cần chạy Failsafe:

- Một module `pom` aggregator không có source test có thể không nên dùng `failIfNoTests=true`.
- Module `core` có unit tests nhưng không có môi trường IT có thể chỉ cần Surefire.
- Module `e2e-tests` có thể chứa IT hoặc dùng Failsafe trên module app theo thiết kế.
- Nếu test cần artifact của một module khác, phải đảm bảo dependency/reactor được build theo thứ tự và artifact thực tế có sẵn khi IT chạy.

Một parent POM có thể giữ version plugin tại `pluginManagement`, còn các module thật sự có IT khai báo goals/executions ở `build/plugins`, hoặc dùng một profile rõ ràng.

**Đừng copy nguyên `failIfNoTests=true` lên mọi module** rồi coi tất cả failures là sai. Hãy đặt chính sách theo module nào thật sự bắt buộc có IT.

### 18.1. Dùng -pl và -am có chủ đích

Ví dụ **chỉ khi reactor thật có module `cli`**:

```bash
mvn -pl cli -am clean verify
```

`-pl` chọn module, `-am` xây thêm các module mà module được chọn phụ thuộc. Cần xem IT ở module nào và reactor có chứa nó không. Việc chỉ build `cli` không mặc định chạy IT nằm ở module `e2e-tests` độc lập.

## 19. CI/CD nên kiểm chứng những gì?

Một pipeline chuẩn cho dự án có IT:

```bash
mvn -B -ntp clean verify
```

Trong đó `-B` bật batch mode, `-ntp` giảm progress tải, không thay đổi phạm vi test.

Checklist:

1. JDK và Maven version rõ ràng; môi trường chạy được các plugins đã ghim.
2. Source/test dependency JUnit tương thích; runtime có TestEngine phù hợp.
3. Surefire và Failsafe đều có version cố định trong POM/parent.
4. Failsafe `integration-test` bind ở phase `integration-test`.
5. Failsafe `verify` bind ở phase `verify`.
6. Các plugin setup/teardown nếu có ở pre/post phase tương ứng.
7. POM không âm thầm skip IT hoặc ignore test failures.
8. Test classes theo naming convention phù hợp; không vô tình chạy IT tại phase test.
9. Logs/summary phản ánh đúng số unit tests và integration tests mong đợi.
10. Nếu có service ngoài, dùng credentials thử nghiệm, endpoint biệt lập và timeout phù hợp.
11. CI đánh dấu FAIL khi IT thật sự fail; không chỉ dựa vào thành công của `package`.
12. Build sau khi nâng versions phải xác nhận lại reports và runtime contract.

Với integration tests tốn nhiều thời gian, một tổ chức có thể có job nhanh chỉ tới `test` hoặc `package` và job chất lượng chính tới `verify`. Nhưng chỉ job thứ hai được tuyên bố đã **thực hiện và đánh giá integration tests**, khi Failsafe bindings và filters đúng.

## 20. Bài tập tự kiểm tra

1. Giải thích khác nhau giữa phase `integration-test` và goal `failsafe:integration-test`.
2. Viết cấu hình một execution không khai báo phase nhưng chứa cả hai goals; giải thích default phase của từng goal.
3. Viết hai executions tường minh, goal `integration-test` gắn vào phase nào, goal `verify` gắn vào phase nào?
4. Nếu đặt cả hai goals trong một execution có `<phase>integration-test</phase>` thì điều gì có thể sai?
5. Tạo project Java 17 của mục 8, chạy `mvn clean verify`; đối chiếu 2 unit tests và 1 integration test.
6. Chạy `java -jar target/failsafe-phase-demo-1.0.0-SNAPSHOT.jar 9 5` và kiểm tra stdout `sum=14`.
7. Tại sao integration test `CliIT` phải chạy **sau** phase package?
8. Chạy `mvn clean package`; giải thích vì sao JAR có nhưng IT chưa được chạy.
9. Thử sửa expected output trong `CliIT` thành `sum=15`, rồi chạy `mvn clean verify`. Ở phase nào build được đánh FAIL bởi Failsafe?
10. Vì sao không nên chỉ gọi `mvn integration-test` trên Maven 3 khi có container start/stop ở pre/post phases?
11. Phân biệt Surefire test naming conventions với Failsafe naming conventions; vì sao `CliTest` không phù hợp với mục đích demo?
12. Giải thích vai trò của `target/failsafe-reports/failsafe-summary.xml` và tại sao goal `verify` phải đọc đúng summary của goal trước.
13. Trong một dự án multi-module, Failsafe nằm ở parent `pluginManagement` nhưng không module nào kích hoạt, bạn sẽ kiểm tra gì?
14. Nêu sự khác nhau giữa `-DskipITs=true`, `-DskipTests` và `-Dmaven.test.skip=true` khi làm việc với các plugin test.
15. Khi IT fail do timeout của service bên ngoài, vì sao Failsafe không bảo đảm cleanup nếu máy CI bị tắt đột ngột?
16. Nếu CI chỉ chạy `mvn clean test` mà báo BUILD SUCCESS, có được kết luận IT đã PASS không?
17. Nêu các điều kiện để một plugin môi trường chạy ở `pre-integration-test` mà không chặn lifecycle.
18. Nếu muốn chạy đúng một IT trên Surefire/Failsafe, property chọn tên test của Failsafe là gì?
19. Vì sao một class test `CliIT` có thể ở `src/test/java` cùng `CalculatorTest` nhưng được chạy ở phase khác nhau?
20. Khi report Failsafe cho biết một assertion failed nhưng Maven vẫn tiếp tục tới post-phase, đó là thiết kế nhằm giải quyết vấn đề gì?

## 21. Tóm tắt

**Để integration tests của Maven có kết quả đáng tin cậy, phải bind cả hai goal của Failsafe:**

- **`failsafe:integration-test` → phase `integration-test`** để thực thi IT.
- **`failsafe:verify` → phase `verify`** để chốt PASS/FAIL sau bước cleanup.

Cách ngắn là khai báo cả hai goals trong một execution không ghi phase và dùng default phase của từng goal; cách rõ ràng hơn khi học là **hai executions với phase tường minh**. Với Maven 3.9.x, hãy gọi **`mvn clean verify`** thay vì chỉ dừng ở `integration-test`.

Trong bài Java 17, Surefire chạy hai unit tests trước `package`; Jar Plugin tạo executable JAR; Failsafe chạy một `CliIT` khởi động JAR ở JVM riêng; cuối cùng `failsafe:verify` đọc summary và quyết định trạng thái build. Sự tách biệt này là lý do Failsafe phù hợp với integration tests có môi trường cần khởi động và dọn dẹp.

## 22. Tài liệu chính thức và tham khảo

- [Maven Failsafe Plugin — Introduction](https://maven.apache.org/surefire/maven-failsafe-plugin/)
- [Maven Failsafe Plugin — Usage](https://maven.apache.org/surefire/maven-failsafe-plugin/usage.html)
- [Maven Failsafe Plugin — failsafe:integration-test](https://maven.apache.org/surefire/maven-failsafe-plugin/integration-test-mojo.html)
- [Maven Failsafe Plugin — failsafe:verify](https://maven.apache.org/surefire/maven-failsafe-plugin/verify-mojo.html)
- [Maven Failsafe Plugin — Inclusion and Exclusion](https://maven.apache.org/surefire/maven-failsafe-plugin/examples/inclusion-exclusion.html)
- [Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Apache Maven — Configuring Plug-ins](https://maven.apache.org/guides/mini/guide-configuring-plugins.html)
- [JUnit User Guide — Maven Build Support](https://docs.junit.org/5.11.4/user-guide/#running-tests-build-maven)
