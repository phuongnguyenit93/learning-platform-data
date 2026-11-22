# Quy tắc đặt tên kiểm thử tích hợp và cấu hình nhận diện trong Maven

## 1. Bài toán: tại sao cùng là JUnit test nhưng có lớp chạy, có lớp bị bỏ qua?

Trong dự án Maven, một lớp Java chứa `@Test` **chưa chắc** sẽ được chạy khi gọi `mvn test` hoặc `mvn verify`. Ngoài test framework, Maven còn cần một **plugin chạy test** và một **quy tắc nhận diện lớp kiểm thử (test class discovery)**.

Hai plugin thường dùng của Apache Maven có nhiệm vụ khác nhau:

- **Maven Surefire Plugin**: chạy **unit tests**, mặc định ở phase `test`.
- **Maven Failsafe Plugin**: chạy **integration tests (IT)** tại phase `integration-test` và xác nhận kết quả tại phase `verify`.

Tên lớp là một trong những đầu vào để các plugin quyết định **lớp nào thuộc nhóm cần chạy**. Ví dụ với cấu hình mặc định:

```text
src/test/java/com/example/it/
├── GreetingServiceTest.java         -> Surefire unit test
├── GreetingServiceIT.java           -> Failsafe integration test
├── ITGreetingService.java           -> Failsafe integration test
├── GreetingServiceITCase.java       -> Failsafe integration test
└── GreetingServiceIntegrationTest.java
                                     -> Surefire (mặc định),
                                        không phải Failsafe (mặc định)
```

Ở đây tất cả đều có thể dùng JUnit 5, nhưng **plugin chọn lớp dựa vào pattern tên**. Tên `*IntegrationTest` nghe giống “integration test”, song **không nằm trong tập mẫu mặc định của Failsafe**. Trái lại, nó kết thúc bằng `Test` nên **khớp mẫu Surefire**.

**Mục tiêu bài học:** nắm các quy ước tên của cả hai plugin; hiểu cách `includes`/`excludes` thay đổi discovery; thiết lập Failsafe đúng lifecycle; tránh chạy trùng hoặc bỏ sót test; kiểm tra kết quả bằng Maven log và report; thực hành với Java 17, JUnit 5.

## 2. Hai plugin, hai thời điểm chạy: Surefire và Failsafe

| Nội dung | Surefire | Failsafe |
| --- | --- | --- |
| Mục đích thông dụng | Unit tests, kiểm tra logic cục bộ | Integration tests, kiểm tra phối hợp nhiều thành phần |
| Maven plugin | `maven-surefire-plugin` | `maven-failsafe-plugin` |
| Goal chạy test | `surefire:test` | `failsafe:integration-test` |
| Phase chính | `test` | `integration-test` |
| Goal xác nhận kết quả riêng | Thường fail ngay trong phase `test` | `failsafe:verify` ở phase `verify` |
| Thư mục test classes mặc định | `target/test-classes` | `target/test-classes` |
| Thư mục test source thông thường | `src/test/java` | `src/test/java` |
| Report mặc định | `target/surefire-reports/` | `target/failsafe-reports/` |
| Cách gọi lifecycle | `mvn test` | `mvn verify` |
| Naming mặc định | `Test*`, `*Test`, `*Tests`, `*TestCase` | `IT*`, `*IT`, `*ITCase` |

**Một khác biệt dễ bỏ sót:** Failsafe **không mặc định lấy source từ `src/it/java`**. Tương tự Surefire, nó thường tìm **test classes đã biên dịch trong `target/test-classes`**. Nếu muốn lưu IT source ở `src/it/java`, phải **đăng ký thêm test source root** hoặc cấu hình build chuyên biệt; chỉ tạo thư mục ấy không làm Compiler Plugin tự biên dịch.

Hai plugin có thể dùng cùng JUnit 5 engine, cùng test dependencies và cùng classpath, nhưng **khác phase/lifecycle và bộ quy tắc chọn lớp**. Không nhầm “test được JUnit công nhận” với “test đã được plugin đưa vào lượt chạy”.

## 3. Quy tắc đặt tên mặc định của Maven Failsafe Plugin

Theo tài liệu chính thức, Failsafe mặc định nhận diện những lớp khớp một trong ba pattern sau:

| Pattern trong Failsafe | Ý nghĩa | Tên lớp ví dụ |
| --- | --- | --- |
| `**/IT*.java` | Tên bắt đầu bằng `IT` | `ITPayment.java`, `ITDatabaseConnection.java` |
| `**/*IT.java` | Tên kết thúc bằng `IT` | `PaymentIT.java`, `GreetingServiceIT.java` |
| `**/*ITCase.java` | Tên kết thúc bằng `ITCase` | `PaymentITCase.java`, `OrderITCase.java` |

Hai ký tự `**/` cho phép pattern áp dụng trong các package/subdirectory. Ký tự `*` mang nghĩa wildcard trong pattern (không phải wildcard của shell cho lệnh `mvn`).

**Điểm kỹ thuật:** mặc dù pattern được ghi dưới dạng `.java`, Failsafe thực tế thực thi **test classes đã được biên dịch**, thường nằm trong `target/test-classes`. Pattern được plugin chuyển/xử lý để match class tương ứng; nó không tự tìm rồi biên dịch ngẫu nhiên các file `.java` nằm ngoài Maven test source roots.

Với naming mặc định:

```text
UserRepositoryIT.java       -> được Failsafe nhận diện
ITUserRepository.java       -> được Failsafe nhận diện
UserRepositoryITCase.java   -> được Failsafe nhận diện
UserRepositoryTest.java     -> KHÔNG được Failsafe mặc định nhận diện
UserRepositoryTests.java    -> KHÔNG được Failsafe mặc định nhận diện
UserRepositoryIntegrationTest.java -> KHÔNG được Failsafe mặc định nhận diện
UserRepositoryE2E.java      -> KHÔNG được Failsafe mặc định nhận diện
```

Các ví dụ này nói về **pattern chọn lớp**, chưa khẳng định mọi lớp đều có phương thức test hợp lệ hoặc test framework có thể chạy chúng. Chẳng hạn một lớp tên `UserRepositoryIT` nhưng không có phương thức `@Test` phù hợp với JUnit Jupiter có thể tạo ra **0 test methods**; đổi tên file không thay thế được JUnit engine/annotation.

### Khuyến nghị đặt tên

Đối với dự án mới không có quy ước khác, tên `*IT.java` như `PaymentGatewayIT.java` thường:
- dễ nhận diện khi đọc code;
- không khớp bộ pattern mặc định của Surefire;
- khớp Failsafe mặc định, không cần cấu hình `includes` riêng;
- giúp CI và người phát triển phân biệt ngay mức kiểm thử.

Nên dùng `*ITCase.java` hoặc `IT*.java` nếu đội ngũ có quy ước rõ, nhưng **tránh đặt lẫn các kiểu tùy hứng** nếu không có lý do.

## 4. Quy tắc mặc định của Surefire để tránh chạy nhầm

Surefire có những mẫu mặc định:

| Pattern của Surefire | Ví dụ |
| --- | --- |
| `**/Test*.java` | `TestGreetingService.java` |
| `**/*Test.java` | `GreetingServiceTest.java` |
| `**/*Tests.java` | `GreetingServiceTests.java` |
| `**/*TestCase.java` | `GreetingServiceTestCase.java` |

Một lớp `GreetingServiceIT.java` **không khớp** các mẫu này, còn `GreetingServiceIntegrationTest.java` **có khớp** `**/*Test.java`.

Sự khác nhau quan trọng:

```text
GreetingServiceTest.java        -> Surefire: YES; Failsafe: NO
GreetingServiceIT.java          -> Surefire: NO;  Failsafe: YES
ITGreetingService.java          -> Surefire: NO;  Failsafe: YES
GreetingServiceIntegrationTest.java
                                -> Surefire: YES; Failsafe: NO (mặc định)
ITGreetingServiceTest.java      -> Surefire: YES; Failsafe: YES
```

**Lớp cuối là một trường hợp trùng quan trọng:** `ITGreetingServiceTest` vừa bắt đầu bằng `IT` (Failsafe) vừa kết thúc bằng `Test` (Surefire). Nếu cả hai plugin được cấu hình chạy, lớp có thể **chạy hai lần trong `mvn verify`**. Điều đó có thể gây tốn thời gian, làm bẩn dữ liệu test hoặc gây side effects trên môi trường tích hợp.

Vì vậy quy ước tên nên vừa **nhắm đúng plugin mong muốn**, vừa **tránh khớp plugin kia**. Đừng giả định có chữ `IT` ở bất kỳ đâu trong tên thì Failsafe mặc định sẽ nhận, hoặc có chữ `Test` ở giữa tên thì Surefire mặc định sẽ nhận.

## 5. Phân biệt tên file, package, annotation và JUnit engine

Để một JUnit 5 integration test thực sự chạy trong Failsafe, thông thường cần đồng thời:

1. Lớp được **test compiler biên dịch thành công** ở source root mà Maven quản lý.
2. File/class name **khớp `includes`** và không bị `excludes` của Failsafe loại.
3. Dự án có **JUnit Jupiter API + engine** hoặc dependency tổng hợp phù hợp; với POM bài này dùng `org.junit.jupiter:junit-jupiter:5.11.4`.
4. Lớp/method có cấu trúc được JUnit engine hỗ trợ, chẳng hạn method có `@org.junit.jupiter.api.Test`.
5. Maven **thực sự chạy đến phase `integration-test`**, với goal Failsafe đã được cấu hình vào lifecycle.
6. Không bị skip bởi `-DskipITs` hoặc các lựa chọn cấu hình khác.
7. Goal `failsafe:verify` được gọi khi bạn muốn build **thất bại nếu integration tests thất bại**.

Đặt tên `PaymentIT.java` chưa đủ nếu file nằm ở `src/it/java` mà chưa được thêm làm test source root. Ngược lại, lớp đặt tại `src/test/java` có annotation đúng nhưng tên `PaymentIntegrationTest.java` vẫn sẽ được **Surefire** nhận trước trong cấu hình mặc định.

Trong ví dụ chính, ta giữ mọi test class trong **`src/test/java`** để tránh nhầm tên và thư mục trong cùng một bước.

## 6. Integration-test lifecycle: vì sao nên gọi mvn verify?

Những phase liên quan trong default lifecycle được Maven định nghĩa:

```text
validate
  ...
test-compile
   |
test                        -> Surefire chạy unit tests
   |
package                     -> tạo artifact JAR/WAR
   |
pre-integration-test        -> chuẩn bị DB, server, container... (nếu đã cấu hình)
   |
integration-test            -> Failsafe chạy integration tests
   |
post-integration-test       -> dọn tài nguyên/stop server... (nếu đã cấu hình)
   |
verify                      -> Failsafe xác nhận kết quả IT
```

**Maven không tự khởi chạy database/web server chỉ vì có phase pre-integration-test.** Nếu cần start/stop dịch vụ, bạn phải cấu hình plugin/goal phù hợp ở các phase ấy. Failsafe cũng **không tự bind vào lifecycle chỉ bởi dependency JUnit hoặc tên *IT**; cần khai báo plugin execution.

### Vì sao Failsafe có hai goals?

- `failsafe:integration-test` **thực thi** integration tests, ghi report và summary, nhưng được thiết kế **không fail build ngay tại phase integration-test vì một test assertion thất bại**.
- `failsafe:verify` **kiểm tra kết quả** và làm build fail khi integration test fail, sau khi các phase dọn môi trường đã có cơ hội chạy.

Nếu dùng cơ chế fail ngay ở phase integration-test, plugin stop server ở `post-integration-test` có thể không được gọi khi test thất bại. Đây là lý do Failsafe tách phần **run** và **verify**.

**Gọi lệnh đúng:**

```bash
mvn -B -ntp clean verify
```

Không dùng `mvn integration-test` thay cho `mvn verify` trong quy trình kiểm thử tích hợp chuẩn: gọi riêng phase `integration-test` có thể kết thúc **trước `post-integration-test` và `verify`**, khiến tài nguyên chưa được dọn hoặc test fail chưa chuyển thành build failure.

`mvn test` chỉ đi tới phase `test`, nên **không chạy integration tests ở Failsafe** theo cấu hình chuẩn này, dù các lớp `*IT` có thể đã được biên dịch cùng test sources.

## 7. Cấu hình Failsafe Plugin tối thiểu trong POM

Một đoạn plugin tiêu chuẩn:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-failsafe-plugin</artifactId>
    <version>3.5.4</version>
    <executions>
        <execution>
            <id>run-integration-tests</id>
            <goals>
                <goal>integration-test</goal>
                <goal>verify</goal>
            </goals>
        </execution>
    </executions>
</plugin>
```

Đây là **đoạn để đặt trong `<build><plugins>` của POM**, không phải một POM độc lập. Failsafe goal `integration-test` có default phase `integration-test`; goal `verify` có default phase `verify`. Vì vậy cấu hình mẫu không bắt buộc viết `<phase>`. Nếu muốn minh thị thời điểm, có thể tách thành **hai execution** có phase tương ứng.

**Không thay tên goal** thành `test`: tên goal là `integration-test` và `verify`. `verify` là cả tên **lifecycle phase** và tên **Failsafe goal**, nhưng chúng không phải một đối tượng; phase `verify` sẽ thực thi goal `failsafe:verify` khi đã bind.

Chỉ khai báo plugin `maven-failsafe-plugin` với version mà **không có `<executions>`** thường không đủ để kích hoạt integration tests khi gõ `mvn verify`. Khác với Surefire (được `jar` packaging bind sẵn vào phase test), Failsafe cần cấu hình goal binding theo tài liệu plugin.

## 8. Ví dụ Java 17 + JUnit 5 hoàn chỉnh, có unit test và integration test

Bài thực hành sử dụng Java standard library để:
- unit test một phương thức thuần của `GreetingService`;
- integration test việc ứng dụng đọc cấu hình **thật từ classpath**;
- integration test kiểm tra resource đã được **đóng gói vào JAR** tạo ở phase `package`.

Cách này đủ để quan sát integration giữa code, resource và Maven packaging **mà không cần database hay server bên ngoài**. Trong dự án lớn, integration tests có thể phối hợp thêm database, network, test container, message broker... theo yêu cầu kiến trúc.

### 8.1. Cấu trúc file

```text
it-naming-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/
    │   │   └── com/example/it/
    │   │       ├── GreetingService.java
    │   │       └── App.java
    │   └── resources/
    │       └── greeting.properties
    └── test/
        └── java/
            └── com/example/it/
                ├── GreetingServiceTest.java
                └── GreetingServiceIT.java
```

File `GreetingServiceTest` kết thúc bằng `Test` nên Surefire chọn; file `GreetingServiceIT` kết thúc bằng `IT` nên Failsafe chọn. **Không cần tạo `src/it/java`** cho ví dụ chính.

### 8.2. pom.xml đầy đủ

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>it-naming-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
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
                <artifactId>maven-failsafe-plugin</artifactId>
                <version>3.5.4</version>
                <executions>
                    <execution>
                        <id>run-integration-tests</id>
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
            </plugin>
        </plugins>
    </build>
</project>
```

POM trên là **file hoàn chỉnh**; dùng JDK 17+, Maven 3.6.3+ và các repository có plugin/dependency tương ứng. Các plugin được pin version để ví dụ dễ tái lập.

Phân tích:
- Dependency `junit-jupiter` có scope `test`, phục vụ biên dịch và chạy JUnit Jupiter test classes.
- Surefire 3.5.4 thực thi tại phase `test` nhờ binding của packaging `jar`, dùng bộ tên mặc định.
- Failsafe 3.5.4 có execution chứa `integration-test` và `verify`, dùng bộ tên Failsafe mặc định vì chưa khai báo `includes` tùy biến.
- Compiler Plugin có `release=17` thông qua property.
- JAR Plugin tạo `target/it-naming-demo-1.0.0.jar` tại `package`.
- Không có server/database tự khởi động. Integration test thực hành lấy input từ file resource và kiểm tra JAR đã package.

### 8.3. src/main/resources/greeting.properties

```properties
prefix=Welcome
```

File được Maven copy vào `target/classes/greeting.properties`, rồi vào JAR chính. Giá trị ASCII giúp tránh vấn đề encoding không cần thiết trong bài về naming.

### 8.4. src/main/java/com/example/it/GreetingService.java

```java
package com.example.it;

import java.io.IOException;
import java.io.InputStream;
import java.util.Properties;

public final class GreetingService {

    public String greet(String name) {
        return "Hello, " + name + "!";
    }

    public String greetFromResource(String name) throws IOException {
        Properties properties = new Properties();
        try (InputStream input =
                     GreetingService.class.getResourceAsStream("/greeting.properties")) {
            if (input == null) {
                throw new IOException("greeting.properties not found on classpath");
            }
            properties.load(input);
        }

        String prefix = properties.getProperty("prefix");
        if (prefix == null) {
            throw new IOException("Missing prefix in greeting.properties");
        }
        return prefix + ", " + name + "!";
    }
}
```

Phương thức `greet` thuần logic, dễ unit test. Phương thức `greetFromResource` phụ thuộc **file cấu hình thật trong classpath**, giúp kiểm tra sự phối hợp giữa Java code và resource copying của Maven.

### 8.5. src/main/java/com/example/it/App.java

```java
package com.example.it;

import java.io.IOException;

public final class App {
    private App() {
    }

    public static void main(String[] args) throws IOException {
        GreetingService service = new GreetingService();
        System.out.println(service.greet("Maven"));
        System.out.println(service.greetFromResource("Maven"));
    }
}
```

Chạy class `App` từ `target/classes` sau khi package sẽ in:

```text
Hello, Maven!
Welcome, Maven!
```

Đây là **stdout của lệnh chạy ứng dụng**, không phải log kết quả test của Surefire/Failsafe.

### 8.6. src/test/java/com/example/it/GreetingServiceTest.java

```java
package com.example.it;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class GreetingServiceTest {
    @Test
    void returnsSimpleGreeting() {
        GreetingService service = new GreetingService();
        assertEquals("Hello, Maven!", service.greet("Maven"));
    }
}
```

Class có tên `GreetingServiceTest`, phù hợp pattern `**/*Test.java` của **Surefire**. Nó kiểm tra một phương thức không cần resource hay JAR.

### 8.7. src/test/java/com/example/it/GreetingServiceIT.java

```java
package com.example.it;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.zip.ZipFile;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class GreetingServiceIT {

    @Test
    void loadsPackagedResourceFromClasspath() throws IOException {
        GreetingService service = new GreetingService();
        assertEquals("Welcome, Maven!", service.greetFromResource("Maven"));
    }

    @Test
    void jarContainsApplicationResource() throws IOException {
        Path jarPath = Path.of("target", "it-naming-demo-1.0.0.jar");
        assertTrue(Files.isRegularFile(jarPath),
                "Run mvn verify from project root so package creates the JAR");
        try (ZipFile zip = new ZipFile(jarPath.toFile())) {
            assertNotNull(zip.getEntry("greeting.properties"));
        }
    }
}
```

Tên `GreetingServiceIT` **khớp Failsafe mặc định**, không khớp Surefire mặc định. Hai phương thức trên:
1. Kiểm tra Java code phối hợp resource thực tế từ classpath;
2. Kiểm tra artifact JAR thật tạo từ phase `package` có chứa resource.

Test `jarContainsApplicationResource` cố ý phụ thuộc JAR đã có trước phase `integration-test`. Vì vậy **chạy `mvn verify` từ root project** là cách đúng cho ví dụ. Chạy riêng goal `failsafe:integration-test` trên một workspace chưa package có thể thất bại do không có JAR.

`ZipFile` đọc được JAR vì JAR dùng định dạng ZIP. Các resource path trong ZIP dùng dấu `/`. `Path.of("target", ...)` hoạt động đúng với thư mục làm việc mặc định là basedir của Maven test fork; nếu công ty tùy biến `workingDirectory` cho Failsafe, điều chỉnh test theo basedir tương ứng thay vì giả định luôn là project root.

## 9. Thực hành: phân biệt mvn test với mvn verify

### 9.1. Chạy unit tests

Tại thư mục `it-naming-demo`:

```bash
mvn -version
mvn -B -ntp clean test
```

Maven đi tới phase `test`. Surefire nhận `GreetingServiceTest` và **chạy 1 test method**. `GreetingServiceIT` đã có thể được test-compile nhưng **chưa được Failsafe thực thi**.

Mốc cần đọc trong log thường tương tự:

```text
Running com.example.it.GreetingServiceTest
Tests run: 1, Failures: 0, Errors: 0, Skipped: 0
```

Đây là **trích đoạn tiêu biểu**, không phải bản sao nguyên văn của một lượt Maven thực tế. Các dòng INFO, timing và plugin metadata có thể khác.

Đường dẫn report unit tests:

```text
target/surefire-reports/TEST-com.example.it.GreetingServiceTest.xml
```

Sau `mvn clean test`, JAR có thể **chưa được tạo** vì phase `package` chưa chạy. Điều này không phải lỗi: bài test tích hợp kiểm tra JAR được thiết kế cho phase đứng sau.

### 9.2. Chạy cả unit và integration tests

```bash
mvn -B -ntp clean verify
```

Khi build thành công:
- Surefire nhận `GreetingServiceTest`: **1 unit test method**;
- Maven JAR Plugin tạo `target/it-naming-demo-1.0.0.jar` ở `package`;
- Failsafe nhận `GreetingServiceIT`: **2 integration test methods**;
- Goal `failsafe:verify` đánh giá kết quả IT và cho phép build hoàn tất nếu không có lỗi.

Hai report chính:

```text
target/surefire-reports/TEST-com.example.it.GreetingServiceTest.xml
target/failsafe-reports/TEST-com.example.it.GreetingServiceIT.xml
target/failsafe-reports/failsafe-summary.xml
```

Trong báo cáo unit test, mong đợi `tests=1`. Trong báo cáo Failsafe của `GreetingServiceIT`, mong đợi `tests=2` và không có failures/errors. Tùy định dạng XML, metadata và thứ tự thuộc tính có thể khác; quan trọng là **report cho biết thực sự có test được chạy**, không chỉ tên class trong source.

Chạy ứng dụng sau build:

```bash
java -cp target/classes com.example.it.App
```

**Stdout chính xác:**

```text
Hello, Maven!
Welcome, Maven!
```

Đây không phải log JUnit. Maven có thể in log trước đó, nhưng câu trên là output của riêng chương trình `App`.

### 9.3. Thử một lượt test fail để hiểu verify

Để tự quan sát, trên **bản sao của project thực hành** có thể đổi assertion trong `GreetingServiceIT` từ `"Welcome, Maven!"` sang `"Wrong value"` rồi chạy `mvn clean verify`.

Khi đó:
- Lượt chạy `failsafe:integration-test` có thể ghi failure và summary nhưng không fail build ngay tại phase ấy;
- Maven vẫn có cơ hội đi qua `post-integration-test`;
- `failsafe:verify` phát hiện integration-test failure và làm lượt Maven `verify` thất bại.

**Khôi phục assertion đúng** sau bài tập. Không dùng `-Dmaven.test.failure.ignore=true` làm “cách sửa”: nó có thể che lỗi test trong CI.

## 10. Cấu hình includes/excludes khi cần quy ước tên riêng

Nếu team chọn `*IntegrationTest.java` thay cho `*IT.java`, Failsafe **không mặc định** nhận pattern này. Phải cấu hình `<includes>` trong `maven-failsafe-plugin`.

Ví dụ muốn giữ cả ba mẫu mặc định và bổ sung mẫu riêng:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-failsafe-plugin</artifactId>
    <version>3.5.4</version>
    <configuration>
        <includes>
            <include>**/IT*.java</include>
            <include>**/*IT.java</include>
            <include>**/*ITCase.java</include>
            <include>**/*IntegrationTest.java</include>
        </includes>
    </configuration>
    <executions>
        <execution>
            <id>run-integration-tests</id>
            <goals>
                <goal>integration-test</goal>
                <goal>verify</goal>
            </goals>
        </execution>
    </executions>
</plugin>
```

Đây là **đoạn thay thế khai báo Failsafe Plugin** trong POM mẫu, không thêm một plugin Failsafe thứ hai. Điểm thiết yếu:
- `<includes>` **cấu hình tập mẫu được chọn** thay cho việc chỉ dựa vào default. Nếu muốn vẫn nhận `*IT`/`IT*`/`*ITCase`, liệt kê chúng rõ ràng cùng mẫu mới.
- `**/*IntegrationTest.java` sẽ nhận `PaymentIntegrationTest.java`.
- Các pattern nên nhất quán với vị trí class được biên dịch và package structure.

### Phải loại *IntegrationTest khỏi Surefire

Vì `PaymentIntegrationTest.java` kết thúc bằng `Test.java`, Surefire **mặc định cũng nhận lớp đó**. Để không chạy hai lần, cấu hình Surefire exclude:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-surefire-plugin</artifactId>
    <version>3.5.4</version>
    <configuration>
        <excludes>
            <exclude>**/*IntegrationTest.java</exclude>
            <exclude>**/IT*Test.java</exclude>
        </excludes>
    </configuration>
</plugin>
```

Đây là **khối Surefire thay thế** trong POM ví dụ, nếu team thực sự sử dụng naming tùy chỉnh. Pattern `**/IT*Test.java` còn bảo vệ những lớp như `ITPaymentTest.java` vốn khớp cả Failsafe và Surefire.

Khi override default `excludes`, hãy kiểm tra thêm quy tắc xử lý nested test classes của plugin/version đang dùng. Nếu cần giữ loại trừ inner classes theo quy ước mặc định của plugin, có thể khai báo thêm `<exclude>**/*$*</exclude>`. Đừng mặc nhiên coi thay toàn bộ `excludes` chỉ là một phép “append” vào tất cả default rules.

**Lưu ý thiết kế:** nếu không có yêu cầu đặt `*IntegrationTest`, cách ít cấu hình nhất là dùng `*IT.java` và giữ default patterns của hai plugin.

### Loại một IT khỏi Failsafe có chủ đích

Ví dụ một IT không thể chạy trong CI vì cần hệ thống ngoài, có thể tạm exclude:

```xml
<configuration>
    <excludes>
        <exclude>**/RequiresRealPaymentGatewayIT.java</exclude>
    </excludes>
</configuration>
```

Đoạn này chỉ minh họa **phần configuration của Failsafe Plugin**. Không nên dùng exclude vĩnh viễn để che lỗi: tốt hơn là tách suite theo profile/CI job phù hợp hoặc làm test độc lập với môi trường ngoài.

## 11. Tên file đúng nhưng test vẫn không được chạy: kiểm tra discovery ở cấp class

Các pattern `*.java` trong cấu hình là cách viết quen thuộc của Surefire/Failsafe. Plugin thường **scan compiled test classes**. Nếu bạn chỉ tạo file `src/it/java/PaymentIT.java` mà Maven không biết đây là test source root, test compiler không biên dịch nó, nên Failsafe không thể phát hiện lớp.

Quy trình đúng:
1. Tìm file nguồn tại test source root hợp lệ;
2. Xác nhận `target/test-classes/.../PaymentIT.class` đã được tạo;
3. Kiểm tra class name có khớp `includes` và không bị `excludes`;
4. Kiểm tra JUnit 5 Jupiter engine/provider có trong test dependencies;
5. Kiểm tra method `@Test` hoặc annotation khác phù hợp với framework;
6. Kiểm tra Failsafe goal đã được bind vào lifecycle;
7. Chạy `mvn verify`, đọc `target/failsafe-reports`.

**Không có quy tắc Maven phổ quát rằng cứ đặt lớp trong package `integration` thì Failsafe sẽ tự nhận.** Package name chỉ được xét khi pattern/configuration yêu cầu như vậy. Naming convention và đường dẫn source là hai khía cạnh riêng.

### Regex và pattern khác Ant

Surefire/Failsafe hỗ trợ pattern kiểu Ant và một số cú pháp `%regex[...]`. Cần nhớ:
- `**/*IT.java` là pattern chọn test classes theo quy tắc plugin, không phải Java regex thuần;
- Regex được áp dụng trên đường dẫn compiled `.class`, dùng `/`, khác với chuỗi package viết bằng dấu chấm;
- Nếu định dùng regex, kiểm tra kỹ điều kiện match và escaping của phiên bản plugin;
- Trong phần lớn dự án, Ant-style patterns dễ đọc, dễ review hơn và đủ dùng.

**Đừng đổi pattern khi vấn đề thực là test class không được biên dịch.** Trước tiên hãy kiểm tra compiled class có tồn tại.

## 12. Nếu tổ chức muốn tách nguồn IT tại src/it/java

Một số team muốn bố cục:

```text
src/main/java             -> production
src/test/java             -> unit test sources
src/it/java               -> integration test sources
src/it/resources          -> integration test resources
```

Đây là quy ước hợp lý về mặt tổ chức **nhưng không phải Maven default**. Nếu đặt `GreetingServiceIT.java` trong `src/it/java`, cần giúp Maven Compiler Plugin đưa thư mục này vào test source roots, ví dụ thông qua **Build Helper Maven Plugin**.

Một đoạn plugin để **bổ sung** trong `<build><plugins>` của POM:

```xml
<plugin>
    <groupId>org.codehaus.mojo</groupId>
    <artifactId>build-helper-maven-plugin</artifactId>
    <version>3.6.2</version>
    <executions>
        <execution>
            <id>register-integration-test-sources</id>
            <phase>generate-test-sources</phase>
            <goals>
                <goal>add-test-source</goal>
            </goals>
            <configuration>
                <sources>
                    <source>src/it/java</source>
                </sources>
            </configuration>
        </execution>
    </executions>
</plugin>
```

**Đây là cấu hình biến thể, không bắt buộc cho POM chính.** Goal `add-test-source` thêm directory vào **test source roots**, để test compilation có thể tạo class trong `target/test-classes`. Failsafe sau đó vẫn chọn lớp bằng **pattern tên**, không phải do vị trí source directory `src/it/java`.

Nếu test cần file `src/it/resources`, còn phải **đăng ký test resource directory** bằng cấu hình `<testResources>` hoặc goal phù hợp như `build-helper:add-test-resource`. Chỉ thêm Java source root không tự làm các file resource mới xuất hiện trên test classpath.

**Thận trọng:** khi thêm `src/it/java` vào test sources chung, Surefire cũng có thể nhìn thấy các compiled classes. Do vậy vẫn phải đặt tên IT không khớp Surefire hoặc cấu hình excludes, chứ **không** trông cậy vị trí directory để tự cách ly hai plugin.

Đối với ứng dụng nhỏ, sử dụng `src/test/java` với quy tắc `*Test`/`*IT` thường đơn giản hơn và không cần Build Helper.

## 13. Chạy chọn một integration test thay vì cả suite

Failsafe có user property `it.test` để chọn test class hoặc method, tương tự Surefire có `test`.

Ví dụ chạy đúng lớp `GreetingServiceIT`:

```bash
mvn -B -ntp -Dit.test=GreetingServiceIT verify
```

Chạy một phương thức riêng của lớp đó:

```bash
mvn -B -ntp "-Dit.test=GreetingServiceIT#jarContainsApplicationResource" verify
```

Lưu ý:
- `-Dit.test` là bộ lọc của **Failsafe**, không thay thế `-Dtest` của Surefire;
- Khi gọi `mvn verify`, các unit tests được Surefire chọn vẫn có thể chạy ở phase `test` như bình thường, trừ khi được cấu hình khác;
- Dùng `-Dtest=GreetingServiceTest` với `mvn test` để lọc unit tests của Surefire;
- Lệnh Failsafe chọn một class/method không tự sinh JAR nếu bạn gọi goal trực tiếp mà không chạy đủ lifecycle;
- Cú pháp lọc có thể khác đôi chút giữa các phiên bản plugin, vì vậy khi chốt CI hãy dùng version/plugin docs tương ứng.

Ví dụ unit test riêng:

```bash
mvn -B -ntp -Dtest=GreetingServiceTest test
```

Nếu tên truyền vào `-Dit.test` không khớp test thực tế, plugin có thể báo lỗi không tìm thấy test được chỉ định theo chính sách `failIfNoSpecifiedTests`. Đọc log và report, không suy từ exit code rằng toàn bộ integration suite đã chạy.

## 14. Skip IT và chính sách không có test

Đôi khi cần chạy nhanh phần unit tests:

```bash
mvn -B -ntp -DskipITs=true verify
```

`-DskipITs=true` là property của Failsafe để bỏ **thực thi integration tests**; test sources vẫn có thể được compiler xử lý. Đây là ngoại lệ tiện dụng, **không nên trở thành mặc định của CI chính** nếu chất lượng release phụ thuộc IT.

Phân biệt:

| Cấu hình | Phạm vi tác động |
| --- | --- |
| `-DskipITs=true` | Failsafe bỏ chạy integration tests |
| `-Dtest=GreetingServiceTest` | Surefire chỉ chọn unit test tương ứng |
| `-Dit.test=GreetingServiceIT` | Failsafe chỉ chọn IT tương ứng |
| `-Dmaven.test.skip=true` | Các plugin hỗ trợ có thể bỏ cả test compilation và test execution; phạm vi rộng |
| `-DskipTests` | Thường dùng cho Surefire; với Failsafe hãy ưu tiên `skipITs` theo docs thay vì giả định semantics giống hệt |

**Không dùng skip để làm “fix” cho integration test fail.** Nếu IT chậm, cân nhắc phân tầng CI: job unit tests nhanh, job verify IT có hạ tầng phù hợp, job nightly E2E. Nhưng một release pipeline phải có chính sách rõ ràng về những tầng kiểm thử bắt buộc.

### Không có test nào được nhận diện

Nếu báo `No tests to run` nhưng build vẫn xanh, một số nguyên nhân là:
- Class `GreetingServiceIntegrationTest` không match Failsafe default;
- Failsafe chưa được bind vào lifecycle;
- Test nằm ngoài source root nên không được compile;
- JUnit Jupiter engine không hiện diện;
- Test class không có method hợp lệ;
- `includes/excludes` hoặc `it.test` sai.

Failsafe có tham số `failIfNoTests`. Nếu một module **bắt buộc phải có IT**, có thể đặt:

```xml
<configuration>
    <failIfNoTests>true</failIfNoTests>
</configuration>
```

Đây là **đoạn configuration cho Failsafe Plugin**, không phải POM độc lập; nó khiến tình huống không có IT được phát hiện thành lỗi theo semantics plugin. **Không bật cứng cho mọi module trong reactor** nếu một số module chỉ có unit tests hoặc không có IT, vì những module đó có thể bị fail dù thiết kế hoàn toàn hợp lệ.

## 15. JUnit 5 tags và nhóm test khác naming pattern

JUnit Jupiter hỗ trợ gắn nhãn test qua `@Tag`:

```java
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

class RemoteServiceIT {
    @Test
    @Tag("slow")
    void requiresExternalService() {
        // Trong dự án thật, method cần assertion và fixture/hạ tầng phù hợp.
    }
}
```

Đây chỉ là **minh họa annotation**, không phải test tích hợp đầy đủ để copy vào project mẫu. Nó không thay thế ví dụ chạy được ở mục 8.

**Naming pattern** quyết định lớp có thuộc tập ứng viên mà Failsafe quét hay không. **JUnit tag filtering** có thể chọn method/test bổ sung trong số các lớp đã được engine nhận biết, khi plugin/provider được cấu hình cho groups/tags tương ứng.

Vì thế:
- Đặt `@Tag("integration")` trên lớp `PaymentIntegrationTest` **không tự bảo đảm** Failsafe mặc định sẽ quét lớp, nếu tên vẫn không match pattern;
- Đổi tên thành `PaymentIT` nhưng không có `@Test`/engine phù hợp cũng không sinh test methods;
- Chỉ khi đồng bộ naming, includes/excludes, JUnit engine và tag selection thì tổ chức suite mới rõ ràng.

Nếu muốn chia nhóm “slow/fast” hoặc “DB/API”, kiểm tra tài liệu JUnit Platform và Failsafe Plugin bản dùng trong dự án thay vì áp dụng máy móc cấu hình TestNG/JUnit 4.

## 16. IT cần môi trường bên ngoài: kết hợp pre/post-integration-test

Một integration test thực tế có thể phải:
1. Khởi động container database/server hoặc fixture;
2. Tạo dữ liệu thử;
3. Gọi API/SQL/message queue;
4. Kiểm tra kết quả;
5. Dừng tài nguyên và dọn dữ liệu dù test thất bại.

Maven có phase phù hợp:

```text
pre-integration-test  -> start service / prepare fixture
integration-test      -> failsafe:integration-test
post-integration-test -> stop service / cleanup
verify                -> failsafe:verify
```

Các bước start/stop cần plugin/execution riêng (ví dụ một plugin quản lý container hoặc server) và cấu hình chính xác. **Failsafe không tự tạo hạ tầng** chỉ bằng tên `*IT`.

Nếu một assertion ở IT fail, thiết kế Failsafe giúp `post-integration-test` có cơ hội chạy trước khi `failsafe:verify` đánh dấu build fail. Nhưng cơ chế này không xử lý mọi trường hợp cực đoan như máy CI bị kill, container runtime crash hoặc build lỗi ngay khi start service; vẫn cần cleanup/timeout/retention ở cấp CI.

Bài thực hành dùng resource/JAR để **không yêu cầu các tác vụ ngoài**. Đây là ví dụ về test liên kết nhiều phần build, không đại diện cho toàn bộ độ phức tạp của integration tests trong sản phẩm thật.

## 17. Kiểm tra qua log và report thay vì chỉ nhìn BUILD SUCCESS

Sau `mvn clean verify`, nên kiểm tra:

```text
target/surefire-reports/
    TEST-com.example.it.GreetingServiceTest.xml
target/failsafe-reports/
    TEST-com.example.it.GreetingServiceIT.xml
    failsafe-summary.xml
```

Một lượt chạy thành công trong project ví dụ có:
- Unit test suite: **1 test**, `0 failures`, `0 errors`;
- Integration test suite: **2 tests**, `0 failures`, `0 errors`;
- Goal `failsafe:verify` hoàn tất.

Đây là **số test dự kiến** nếu sử dụng nguyên bộ source đã cung cấp, không tự thêm test, và plugin/engine hoạt động. Không nhầm chúng với số class file trong target hay số dependency JUnit được tải về.

Nếu log cho biết:
```text
No tests to run.
```

thì không thể kết luận suite đã được chạy đúng. Hãy kiểm tra class naming, compiled test classes và plugin binding. Bản build đôi khi vẫn có thể **BUILD SUCCESS** khi không có test được nhận diện, tùy `failIfNoTests` và cấu hình.

Khi điều tra:
- `target/surefire-reports` chỉ chứng minh **những test do Surefire chạy**;
- `target/failsafe-reports` chứng minh **những test do Failsafe chạy**;
- `failsafe-summary.xml` là dữ liệu giúp goal verify quyết định kết quả;
- cùng class xuất hiện ở cả hai report có thể là dấu hiệu đặt tên/pattern gây **chạy trùng**.

## 18. Các lỗi thường gặp về đặt tên và nhận diện

| Triệu chứng | Nguyên nhân cần kiểm tra | Cách sửa |
| --- | --- | --- |
| `PaymentIntegrationTest` chạy ở `mvn test` | Tên kết thúc bằng `Test` nên Surefire chọn | Đổi thành `PaymentIT`, hoặc thêm Failsafe include và Surefire exclude |
| `PaymentIntegrationTest` không chạy ở Failsafe | `*IntegrationTest` không nằm trong 3 default patterns Failsafe | Dùng `*IT` hoặc cấu hình `includes` |
| `ITPaymentTest` chạy hai lần | Bắt đầu `IT`, kết thúc `Test`: khớp cả hai plugin | Đổi tên rõ ràng hoặc exclude ở một plugin |
| `PaymentIT` không xuất hiện khi `mvn test` | Failsafe gắn ở phase sau `test` | Chạy `mvn verify` |
| `PaymentIT` không chạy cả với `mvn verify` | Failsafe chưa cấu hình executions hoặc bị skip | Bind `integration-test` và `verify`, kiểm tra `skipITs` |
| Không có IT report | Không có test match, phase chưa chạy hoặc plugin fail | Xem `target/test-classes`, reports, log và includes |
| Chỉ tạo `src/it/java` rồi mất IT | Maven không tự biên dịch thư mục này | Thêm test source root bằng Build Helper hoặc cấu hình build |
| Một class có `@Test` nhưng không chạy | Chưa được scan, thiếu Jupiter engine hoặc class/method không hợp lệ | Kiểm tra tên, provider, test dependency và report |
| Không rõ plugin nào chạy lớp | Cả Surefire và Failsafe có thể dùng JUnit 5 | Xem vị trí report và dòng plugin trong Maven log |
| Thêm Failsafe include mới làm các `*IT` cũ mất | Đã thay tập includes nhưng quên giữ ba mẫu mặc định | Liệt kê đủ các pattern cần giữ |
| IT báo fail nhưng `mvn integration-test` trả về success | Failsafe trì hoãn quyết định failure đến goal verify | Chạy `mvn verify` |
| Môi trường test chưa được dọn | Chỉ gọi `integration-test`, không đi qua `post-integration-test` | Chạy lifecycle tới `verify` và cấu hình teardown |
| IT test báo thiếu JAR | Chạy goal trực tiếp hoặc chạy trước phase package | Chạy `mvn clean verify`; kiểm tra đúng artifact name |
| Các tests cùng tên bị chạy nhiều lần | Includes/excludes quá rộng hoặc nhiều executions | Kiểm tra effective POM và log/report |
| `-Dtest` không chọn IT | Đây là property Surefire | Dùng `-Dit.test` khi chọn Failsafe tests |
| `-DskipITs` khiến số IT bằng 0 | Đã chủ động skip test | Bỏ skip khi xác minh release |
| CI build xanh nhưng không có test được nhận | `failIfNoTests` không bật/không phù hợp | Kiểm tra report và cân nhắc bật rule theo module |
| JUnit 5 `@Tag` không có tác dụng | Plugin không cấu hình tag selection hoặc lớp không match naming | Kiểm tra JUnit Platform provider và plugin filters |
| Không thấy class của IT trong `target/test-classes` | Test compilation không chạy hoặc source root sai | Chạy `mvn test-compile`, kiểm tra compiler logs |
| Parent POM thêm Failsafe nhưng child không chạy | Plugin chỉ ở `pluginManagement` hoặc execution không được áp dụng | Xem effective POM của child |

### Phương pháp debug có thứ tự

1. Đọc chính xác tên file/class IT và tên package.
2. Xác định đường dẫn source root: `src/test/java` hay `src/it/java` (đã đăng ký chưa).
3. Chạy `mvn -B -ntp test-compile`; tìm compiled test class trong `target/test-classes`.
4. Kiểm tra `pom.xml`, `pluginManagement` và `<build><plugins>`.
5. Dùng `mvn help:effective-pom -Doutput=effective-pom.xml` để xem Surefire/Failsafe thực tế và profile/parent sau merge.
6. So `includes/excludes` của từng plugin; tránh trùng nhau.
7. Kiểm tra dependency `junit-jupiter` và JUnit Platform engine.
8. Chạy `mvn -B -ntp clean verify`.
9. Đọc cả `target/surefire-reports` lẫn `target/failsafe-reports`.
10. Chỉ kết luận suite hoạt động khi **test methods đã chạy đúng số lượng** và `failsafe:verify` đã xác nhận kết quả.

Nếu cần log chi tiết:

```bash
mvn -X -B -ntp verify
```

Log debug có thể chứa cấu hình hạ tầng test, URL và property nhạy cảm; không gửi nguyên log lên nơi công khai trước khi kiểm tra.

## 19. Multi-module Maven, parent và pluginManagement

Với reactor nhiều module, mỗi module có source root, dependencies và build configuration của riêng mình. Ví dụ:
- `core` chỉ có unit tests, không có IT;
- `adapter` có unit tests và IT;
- `e2e-tests` chỉ chứa integration/end-to-end tests.

Có thể quản lý **versions** của Surefire/Failsafe trong `<pluginManagement>` của parent, nhưng một plugin chỉ nằm trong pluginManagement **không tự làm tất cả module chạy execution mới**. Để chạy Failsafe, cần plugin/execution được áp dụng trong `<build><plugins>` hoặc cấu hình kế thừa phù hợp.

Nếu một parent POM khai báo Failsafe trong `<build><plugins>` để tất cả children kế thừa, các module không có IT có thể không tạo report/test như mong đợi; nếu bật `failIfNoTests=true` toàn cục có thể làm reactor fail không cần thiết. Nên quy định **module nào bắt buộc phải có IT**, module nào không, và giữ rõ phân chia job CI.

Đối với từng module:
- xem effective POM đúng module;
- kiểm tra `target/test-classes` đúng module;
- đọc `target/failsafe-reports` trong module đó;
- không lấy report ở root để kết luận tất cả modules đều có IT.

Ví dụ chạy riêng một module trong reactor:

```bash
mvn -pl :adapter -am verify
```

`-pl` chọn module có artifactId `adapter` (nếu tồn tại); `-am` build những module cần thiết. Đây là cú pháp **minh họa**, không phải một module được khẳng định có trong dự án ví dụ. Các module kèm theo cũng có thể chạy test theo cấu hình của chúng; nếu muốn test đúng một module, cần xem kế hoạch CI thay vì suy rằng `-am` chỉ chạy dependency compilation.

## 20. Bài tập tự kiểm tra

1. Failsafe mặc định nhận ba pattern tên lớp nào?
2. Vì sao `OrderIntegrationTest.java` không được Failsafe mặc định chạy dù có chữ “Integration”?
3. `OrderIntegrationTest.java` có thể được Surefire mặc định chạy không? Vì sao?
4. `ITOrderTest.java` khớp plugin nào nếu giữ default includes?
5. Khi chạy `mvn test`, một class `OrderIT.java` có được Failsafe chạy không?
6. Để Failsafe chạy ở lifecycle, bạn cần cấu hình những goal nào?
7. Vì sao `mvn verify` là lựa chọn chuẩn hơn `mvn integration-test`?
8. Khi bạn ghi thêm `**/*IntegrationTest.java` vào Failsafe includes, có nên thêm excludes ở Surefire không?
9. Vì sao file IT ở `src/it/java` chưa chắc được biên dịch? Cấu hình nào có thể bổ sung test source root?
10. `-Dit.test=OrderIT` khác `-Dtest=OrderTest` ở chỗ nào?
11. Cần xem những thư mục report nào để phát hiện một lớp test bị chạy hai lần?
12. Tên class đúng và có JUnit `@Test` nhưng vẫn không chạy: hãy nêu ba nguyên nhân khác naming.
13. Khi một IT cần JAR đã package, nên dùng `mvn test` hay `mvn verify`?
14. Vì sao `@Tag("integration")` không tự thay thế naming pattern Failsafe?
15. Có nên bật `failIfNoTests=true` cho tất cả module trong reactor không?

## 21. Checklist trước khi đưa integration tests vào CI

- [ ] Đặt tên integration tests theo quy ước rõ ràng, ưu tiên `*IT.java` nếu không có yêu cầu riêng.
- [ ] Không để tên IT trùng pattern Surefire mặc định, đặc biệt kiểu `ITSomethingTest.java`.
- [ ] Nếu dùng `*IntegrationTest.java`, có Failsafe include **và** Surefire exclude.
- [ ] Nếu cấu hình Failsafe `includes`, đã giữ những default patterns vẫn cần dùng.
- [ ] IT classes nằm trong test source roots mà Maven thực sự biên dịch.
- [ ] Test dependencies có đúng JUnit 5 API và engine.
- [ ] Failsafe Plugin có version ghim và executions cho `integration-test` cùng `verify`.
- [ ] Pipeline chạy tới phase `verify` thay vì dừng ở `integration-test`.
- [ ] Nếu có hạ tầng ngoài, đã cấu hình start/stop ở pre/post-integration-test và cơ chế cleanup của CI.
- [ ] Đã phân biệt unit report và integration report, xem số test thực sự chạy.
- [ ] Không mặc định `skipITs` hoặc `maven.test.skip` trong release job.
- [ ] Với module bắt buộc có IT, cân nhắc `failIfNoTests` nhưng không áp cho modules không có IT.
- [ ] Nếu project nhiều module, xác minh từng module có cấu hình và reports phù hợp.
- [ ] Nếu IT dùng artifact đã package, không chạy trực tiếp goal trước khi tạo artifact.

**Kết luận:** Trong Maven, tên lớp là một phần của cơ chế **test discovery**. Surefire mặc định chạy những lớp dạng `*Test`/`*Tests`; Failsafe mặc định chọn `IT*`/`*IT`/`*ITCase`. Để integration tests được chạy đúng, cần đồng thời **compiled test class**, **test engine/annotation**, **pattern includes/excludes**, **Failsafe execution gắn lifecycle**, và **`mvn verify`** để xác nhận kết quả sau bước dọn môi trường. Quy tắc tên đơn giản `*IT.java` cùng báo cáo `target/failsafe-reports` thường là cách dễ kiểm chứng và ít gây nhầm lẫn nhất.

## Tài liệu tham khảo chính thức

- [Apache Maven Failsafe Plugin — Inclusions and Exclusions](https://maven.apache.org/surefire/maven-failsafe-plugin/examples/inclusion-exclusion.html)
- [Apache Maven Surefire Plugin — Inclusions and Exclusions](https://maven.apache.org/surefire/maven-surefire-plugin/examples/inclusion-exclusion.html)
- [Apache Maven Failsafe Plugin — Introduction, Integration Test Lifecycle](https://maven.apache.org/surefire/maven-failsafe-plugin/)
- [Apache Maven Failsafe Plugin — Usage and Lifecycle Binding](https://maven.apache.org/surefire/maven-failsafe-plugin/usage.html)
- [Apache Maven Failsafe Plugin — failsafe:integration-test](https://maven.apache.org/surefire/maven-failsafe-plugin/integration-test-mojo.html)
- [Apache Maven Failsafe Plugin — failsafe:verify](https://maven.apache.org/surefire/maven-failsafe-plugin/verify-mojo.html)
- [Apache Maven Surefire Plugin — surefire:test](https://maven.apache.org/surefire/maven-surefire-plugin/test-mojo.html)
- [Apache Maven Surefire Plugin — Using JUnit Platform](https://maven.apache.org/surefire/maven-surefire-plugin/examples/junit-platform.html)
- [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [MojoHaus Build Helper — add-test-source](https://www.mojohaus.org/build-helper-maven-plugin/add-test-source-mojo.html)
