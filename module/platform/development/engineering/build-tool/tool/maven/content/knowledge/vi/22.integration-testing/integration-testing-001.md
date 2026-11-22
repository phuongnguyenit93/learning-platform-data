# Maven Failsafe Plugin và ranh giới với Surefire

## 1. Vì sao cần cả Surefire và Failsafe?

Trong một dự án Java, **unit test** thường chạy nhanh, cô lập và kiểm tra một class hoặc quy tắc nhỏ. **Integration test** kiểm tra nhiều thành phần phối hợp, ví dụ service gọi repository để ghi/đọc file, ứng dụng gọi database thật, HTTP endpoint trả kết quả, hoặc một hệ thống khởi động các dịch vụ phụ trợ trước khi test.

Maven có hai plugin cùng họ nhưng phục vụ mục đích khác nhau:

- **Maven Surefire Plugin:** chủ yếu chạy **unit tests**, thường gắn với lifecycle phase `test`.
- **Maven Failsafe Plugin:** được thiết kế cho **integration tests**, với hai goal `failsafe:integration-test` và `failsafe:verify`, thường gắn với các phase cùng tên.

Khác biệt không chỉ nằm ở tên lớp:

> **Failsafe trì hoãn việc báo build thất bại vì assertion/test failure cho đến goal `verify`**, giúp các goal bind ở phase `post-integration-test` vẫn có cơ hội chạy để dọn môi trường kiểm thử. Surefire thường đánh dấu build thất bại ngay tại phase `test` nếu unit test fail.

Câu cuối **không** bảo đảm mọi lỗi đều được trì hoãn: lỗi plugin resolution, lỗi khởi động môi trường, lỗi JVM nghiêm trọng, người dùng dừng process hoặc hạ tầng bị ngắt vẫn có thể làm lifecycle dừng trước khi cleanup. Cơ chế Failsafe nhằm xử lý **kết quả kiểm thử thất bại** một cách an toàn hơn.

Điều người học cần trả lời được sau bài:

1. Vì sao `mvn test` thường chưa chạy integration tests đặt tên `*IT`?
2. Vì sao phải bind **cả hai goal** `integration-test` và `verify` của Failsafe?
3. Quy tắc phát hiện test class mặc định của hai plugin khác nhau thế nào?
4. Khi chạy `mvn verify`, thứ tự unit test → setup → integration test → cleanup → verify ra sao?
5. Bật bảo vệ gì để CI không “xanh” dù không có integration tests?
6. Test report nào chứng minh Surefire/Failsafe **thực sự đã chạy**, thay vì chỉ compile source?

Ví dụ chính dùng Maven 3.9.x, Java 17 và JUnit Jupiter 5.11.4 để bạn có thể tự quan sát ranh giới bằng một unit test và một integration test tương tác với filesystem.

## 2. Ranh giới giữa unit test và integration test là mục tiêu, không phải một annotation Maven

**Unit test** thường xác minh một đơn vị logic với ít phụ thuộc, chạy nhanh và có kết quả dễ tái lập. Ví dụ: `GreetingFormatter.format(" Maven ")` trả `Hello, Maven!`.

**Integration test** xác minh sự phối hợp giữa các thành phần, ví dụ `GreetingService` lấy kết quả formatter, yêu cầu `GreetingRepository` ghi tệp thật, rồi đọc tệp trở lại. Khi ứng dụng thật phức tạp hơn, integration test có thể đụng tới HTTP server, database, message broker, container hoặc external API.

Về mặt JUnit, **cả hai vẫn có thể dùng `@Test`**:

~~~java
import org.junit.jupiter.api.Test;
~~~

JUnit không tự quyết định một test là unit hay integration chỉ vì class có annotation này. Maven tách các lượt chạy bằng **plugin + lifecycle phase + quy tắc chọn tên lớp hoặc custom includes/excludes**.

Ví dụ quy ước:

~~~text
src/test/java/org/example/boundary/GreetingFormatterTest.java
    -> Surefire, unit test

src/test/java/org/example/boundary/GreetingFlowIT.java
    -> Failsafe, integration test
~~~

Một test có tên `GreetingFlowIT` **không tự được Failsafe chạy** nếu project chưa bind Failsafe goals vào lifecycle hoặc chưa gọi plugin goal tương ứng. Và một test đặt tên `GreetingFormatterTest` **không tự trở thành unit test cô lập** nếu bên trong nó gọi một production database.

**Tên lớp là cơ chế phân tuyến mặc định, không phải định nghĩa học thuật của loại test.**

## 3. Maven lifecycle: chỗ hai plugin tách nhau

Với packaging `jar` và lifecycle thông thường, thứ tự phase có thể nhìn như sau:

~~~text
validate
   |
compile
   |
test-compile      -> biên dịch src/test/java
   |
test              -> Surefire chạy unit tests (*Test...)
   |
package           -> đóng gói artifact
   |
pre-integration-test   -> chuẩn bị môi trường, server, fixture... nếu đã bind goal
   |
integration-test       -> Failsafe chạy integration tests (*IT...)
   |
post-integration-test  -> dọn môi trường nếu đã bind goal
   |
verify                 -> Failsafe kiểm tra kết quả IT và fail build nếu test thất bại
~~~

Các tên `pre-integration-test`, `post-integration-test`, `integration-test` và `verify` là **phase của Maven lifecycle**, không phải tên class test. Trong một dự án chỉ khai báo Failsafe mà chưa có server/DB, phase setup và cleanup có thể không có goal nào được gắn; Maven vẫn có thể đi qua chúng.

| Lệnh từ root project | Những phase/goal đáng chú ý | Có chạy Failsafe IT trong POM mẫu ở phần 8? |
| --- | --- | --- |
| `mvn clean compile` | Compile main, chưa test | Không |
| `mvn clean test` | Test compile, Surefire `test` | Không |
| `mvn clean package` | Surefire rồi package | Không |
| `mvn clean integration-test` | Surefire, package, setup nếu có, Failsafe `integration-test` | Có; **chưa đi qua cleanup/verify** |
| `mvn clean verify` | Toàn bộ đến `verify` | **Có và kiểm tra kết quả cuối** |
| `mvn clean install` | Đi qua `verify` trước `install` | Có, nếu plugin đã bind |
| `mvn clean deploy` | Đi qua `verify` trước `deploy` | Có, nếu plugin đã bind và không skip |

**Khuyến nghị:** khi muốn chạy integration tests, dùng `mvn verify` hoặc `mvn clean verify`. Apache Maven Failsafe cảnh báo **không dùng `mvn integration-test` như lệnh kiểm thử hoàn chỉnh**, vì lệnh này kết thúc trước `post-integration-test` và `verify`.

Lệnh `mvn verify` **không tự kích hoạt Failsafe ở mọi dự án**. Bạn phải có cấu hình plugin/executions thích hợp (mục 8), hoặc một parent/plugin binding đã được áp dụng.

## 4. Hai goal Failsafe phối hợp như thế nào?

### 4.1. Goal failsafe:integration-test

Goal này:

- Chọn các test classes thích hợp theo includes/excludes hoặc `-Dit.test=...`.
- Chạy tests qua provider, ví dụ JUnit Platform/Jupiter trong dự án mẫu.
- Ghi reports dưới `target/failsafe-reports` và summary file `failsafe-summary.xml`.
- Khi **assertion trong integration test fail**, ghi nhận kết quả nhưng được thiết kế **không lập tức làm Maven lifecycle dừng vì test failure tại chính phase integration-test**, để phase cleanup có cơ hội chạy.

Đây là điểm khác với việc ép Surefire chạy lại ở phase `integration-test`, vì Surefire không được thiết kế để trì hoãn lỗi assertion đến cuối vòng lifecycle theo cách Failsafe.

### 4.2. Goal failsafe:verify

Goal này:

- Đọc **Failsafe summary file** từ lần chạy `integration-test` tương ứng.
- Kiểm tra trạng thái integration tests.
- Là nơi thông báo **BUILD FAILURE** khi integration test thực sự thất bại và không có chính sách ignore được cho phép.

**Vì sao không bỏ goal verify?** Nếu chỉ bind `failsafe:integration-test` mà quên `failsafe:verify`, test failure có thể đã được ghi vào report nhưng **không chuyển thành build failure đúng cách**. Điều này khiến pipeline có khả năng báo thành công dù test thực tế fail.

**Vì sao không chỉ chạy goal verify?** Nó cần summary/test results phù hợp. Nếu chưa chạy integration-test và không có summary đúng cho build hiện tại, bạn không thể coi verify đơn độc là một lần chạy test hoàn chỉnh.

### 4.3. Khi nào môi trường được dọn?

Giả sử dự án có goal khởi động database/server trong `pre-integration-test` và goal dừng nó ở `post-integration-test`. Nếu assertion ở một IT fail, Failsafe thường ghi nhận lỗi, để cleanup tiếp tục chạy, sau đó `verify` mới fail build.

Không hứa cơ chế này là “finally tuyệt đối”: nếu server không khởi động được, process bị kill, JVM crash hoặc một plugin khác fail sớm thì cleanup có thể không chạy. Với hệ thống thật, CI vẫn nên dùng cleanup trên runner/container theo chính sách riêng, kể cả khi Maven bị ngắt.

## 5. Quy tắc tên lớp mặc định: Surefire so với Failsafe

Theo tài liệu chính thức, **Surefire** mặc định chọn bốn pattern:

~~~text
**/Test*.java
**/*Test.java
**/*Tests.java
**/*TestCase.java
~~~

**Failsafe** mặc định chọn ba pattern:

~~~text
**/IT*.java
**/*IT.java
**/*ITCase.java
~~~

Những pattern kiểu `*.java` là **cú pháp của plugin**, dùng để lọc classes đã biên dịch trong test output; chúng không có nghĩa Maven chỉ biên dịch những file source mang tên đó. Maven Test Compiler có thể biên dịch mọi test source hợp lệ trong `src/test/java` trước khi Surefire/Failsafe chọn test để chạy.

| Tên class | Surefire mặc định | Failsafe mặc định | Giải thích |
| --- | --- | --- | --- |
| `GreetingFormatterTest` | Có | Không | Đuôi `Test`. |
| `TestGreetingFormatter` | Có | Không | Tiền tố `Test`. |
| `GreetingFormatterTests` | Có | Không | Đuôi `Tests`. |
| `GreetingFormatterTestCase` | Có | Không | Đuôi `TestCase`. |
| `GreetingFlowIT` | Không | Có | Đuôi `IT`. |
| `ITGreetingFlow` | Không | Có | Tiền tố `IT`. |
| `GreetingFlowITCase` | Không | Có | Đuôi `ITCase`. |
| `GreetingFlowSpec` | Không | Không | Cần đổi tên hoặc custom include. |
| `TestGreetingFlowIT` | **Có** | **Có** | Vừa bắt đầu `Test`, vừa kết thúc `IT`; dễ bị chạy hai lần. |
| `ITGreetingFlowTest` | **Có** | **Có** | Vừa bắt đầu `IT`, vừa kết thúc `Test`. |

**Lưu ý thực tế:** Những tên như `TestGreetingFlowIT` và `ITGreetingFlowTest` có thể bị cả hai plugin chọn nếu được cấu hình cùng project/lifecycle. Đừng cho rằng hai bộ pattern không bao giờ giao nhau. Hãy thống nhất convention **`*Test` cho unit** và **`*IT` cho integration** (tránh prefix `Test` trong tên IT) để giảm khả năng test bị chạy hai lượt.

**Chỉ đổi tên class không đủ nếu plugin chưa được bind:** `GreetingFlowIT` vẫn không chạy khi project chỉ có Surefire và không có Failsafe executions.

## 6. Cả hai loại test có thể đặt ở src/test/java

Một hiểu nhầm phổ biến là “integration tests bắt buộc phải đặt trong `src/it/java`”. Với Failsafe cấu hình thông thường, **không bắt buộc**.

Một project có thể tổ chức:

~~~text
src/
├── main/java/
│   └── ... application classes ...
└── test/java/
    ├── .../GreetingFormatterTest.java
    └── .../GreetingFlowIT.java

target/
├── classes/
├── test-classes/
├── surefire-reports/
└── failsafe-reports/
~~~

Maven Compiler Plugin mặc định biên dịch cả hai lớp ở `src/test/java` vào `target/test-classes` trong phase `test-compile`. Sau đó:

- Surefire tìm các class khớp naming rules cho unit tests.
- Failsafe tìm các class khớp naming rules cho integration tests.
- Hai plugin dùng cùng test sources/classes directory mặc định, nhưng **hai thời điểm chạy và hai reports directories khác nhau**.

Nếu tổ chức muốn source root riêng như `src/it/java`, cần **thêm nguồn kiểm thử** cho Maven/Compiler Plugin (ví dụ bằng build-helper plugin hoặc cấu hình riêng) và giải quyết classpath/resource phù hợp. **Chỉ tạo thư mục `src/it/java` không làm Maven tự compile tệp ở đó.**

Khi cần bộ integration tests phụ thuộc môi trường rất khác, có thể tách thành Maven module riêng hoặc profile/stage riêng; không bắt buộc cho project nhỏ.

## 7. POM tối thiểu để bind Failsafe vào lifecycle

Cấu hình mấu chốt:

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

Đây là **mảnh của `<build><plugins>`**, không phải toàn bộ POM. Maven biết default phase của mỗi goal (`integration-test` cho goal tương ứng, `verify` cho goal `verify`), nên kiểu cấu hình này theo hướng dẫn chính thức Failsafe Usage có thể bind hai goals mà không cần ghi `<phase>` thủ công.

Một số nhóm thích chia thành hai executions để dễ đọc:

~~~xml
<executions>
    <execution>
        <id>run-integration-tests</id>
        <goals><goal>integration-test</goal></goals>
    </execution>
    <execution>
        <id>check-integration-test-results</id>
        <goals><goal>verify</goal></goals>
    </execution>
</executions>
~~~

Đây cũng chỉ là **mảnh cấu hình bên trong plugin**, và vẫn dựa trên default phase binding của Failsafe goals. Nếu cấu hình ở parent/profile, cần xem effective POM để bảo đảm các executions thực sự được áp dụng vào module cần chạy.

**Không nhầm `pluginManagement` với `plugins`:** ghi Failsafe vào `<build><pluginManagement>` chỉ cung cấp cấu hình/version mặc định, **không tự kích hoạt** các executions ở mọi child. Child cần sử dụng plugin hoặc thừa kế một `build/plugins` execution được áp dụng.

## 8. Ví dụ Java 17 chạy được: unit test và filesystem integration test

Dự án mẫu sau giữ mọi nguồn trong cùng một Maven project để làm nổi bật **ranh giới execution**, không kéo thêm server hay database ngoài. Dù gọn, integration test **không phải chỉ gọi một hàm thuần**: nó đi qua `GreetingService` và `GreetingRepository`, thực hiện I/O bằng `java.nio.file.Files` vào thư mục tạm do JUnit cung cấp.

Yêu cầu: JDK 17+, Maven 3.9.x tương thích, có thể tải dependencies và plugins từ repository tin cậy nếu chưa có cache.

Cấu trúc:

~~~text
failsafe-boundary-demo/
├── pom.xml
└── src/
    ├── main/java/org/example/boundary/
    │   ├── GreetingFormatter.java
    │   ├── GreetingRepository.java
    │   └── GreetingService.java
    └── test/java/org/example/boundary/
        ├── GreetingFormatterTest.java
        └── GreetingFlowIT.java
~~~

### 8.1. pom.xml đầy đủ

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>org.example.training</groupId>
    <artifactId>failsafe-boundary-demo</artifactId>
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
                    <failIfNoTests>true</failIfNoTests>
                </configuration>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-failsafe-plugin</artifactId>
                <version>3.5.2</version>
                <configuration>
                    <failIfNoTests>true</failIfNoTests>
                </configuration>
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
</project>
~~~

Đây là **POM hoàn chỉnh**. Hai plugin được pin **cùng version 3.5.2** để tránh trộn các phiên bản provider/reporting mà không có lý do. Đây là version cố định cho bài học, không phải khẳng định bản mới nhất trên Maven Central.

**Hai `failIfNoTests=true` là chính sách của project mẫu**, không phải defaults của hai plugin. Chúng thích hợp vì demo **cố ý có** cả unit lẫn integration tests; với module chỉ chứa codegen/BOM hoặc module không có một trong hai loại test, không nên áp đặt hai guards đó máy móc lên mọi module.

Không cần cấu hình `<includes>` vì tên hai lớp test khớp các default patterns. Không cần cấu hình `src/it/java` vì cả hai class đều nằm trong `src/test/java`.

### 8.2. Main source: GreetingFormatter.java

Đường dẫn `src/main/java/org/example/boundary/GreetingFormatter.java`:

~~~java
package org.example.boundary;

public final class GreetingFormatter {
    private GreetingFormatter() {
    }

    public static String format(String name) {
        String cleaned = name.strip();
        if (cleaned.isEmpty()) {
            cleaned = "guest";
        }
        return "Hello, " + cleaned + "!";
    }
}
~~~

Đây là mã thuần Java. `String.strip()` của Java 17 loại khoảng trắng hai đầu chuỗi. Với `"  Maven  "`, kết quả là `"Hello, Maven!"`; với chuỗi toàn dấu cách, trả `"Hello, guest!"`. Method giả định `name` không null; null không phải ca test của bài mẫu, nên không suy đoán có null handling.

### 8.3. Main source: GreetingRepository.java

Đường dẫn `src/main/java/org/example/boundary/GreetingRepository.java`:

~~~java
package org.example.boundary;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Objects;

public final class GreetingRepository {
    private final Path file;

    public GreetingRepository(Path file) {
        this.file = Objects.requireNonNull(file, "file");
    }

    public void save(String greeting) throws IOException {
        Files.writeString(file, greeting, StandardCharsets.UTF_8);
    }

    public String load() throws IOException {
        return Files.readString(file, StandardCharsets.UTF_8);
    }
}
~~~

Trong ví dụ, `file` trỏ tới một file nằm trong thư mục tạm đã tồn tại (xem IT). `Files.writeString` với options mặc định có thể tạo file nếu chưa có và ghi đè nội dung file hiện có. `Files.readString` đọc lại UTF-8. Hai method ném `IOException` khi filesystem báo lỗi; integration test sẽ kiểm tra kết quả end-to-end.

Không cần thư viện ngoài JDK cho repository. Không hard-code đường dẫn máy cá nhân hoặc file production.

### 8.4. Main source: GreetingService.java

Đường dẫn `src/main/java/org/example/boundary/GreetingService.java`:

~~~java
package org.example.boundary;

import java.io.IOException;
import java.util.Objects;

public final class GreetingService {
    private final GreetingRepository repository;

    public GreetingService(GreetingRepository repository) {
        this.repository = Objects.requireNonNull(repository, "repository");
    }

    public String greetAndStore(String name) throws IOException {
        String greeting = GreetingFormatter.format(name);
        repository.save(greeting);
        return repository.load();
    }
}
~~~

`GreetingService` kết hợp **formatter + repository**: tạo nội dung, ghi xuống file và tải lại giá trị được lưu. Đây là một luồng có sự phối hợp thực sự giữa nhiều class và I/O, phù hợp với ví dụ integration test tối giản.

### 8.5. Unit test: GreetingFormatterTest.java

Đường dẫn `src/test/java/org/example/boundary/GreetingFormatterTest.java`:

~~~java
package org.example.boundary;

import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class GreetingFormatterTest {
    @Test
    void removesSurroundingWhitespace() {
        assertEquals("Hello, Maven!", GreetingFormatter.format("  Maven  "));
    }

    @Test
    void usesGuestForBlankName() {
        assertEquals("Hello, guest!", GreetingFormatter.format("   "));
    }
}
~~~

Tên class kết thúc bằng `Test` nên Surefire **chọn theo mặc định**. Test có **2 methods `@Test`**. Chúng chỉ gọi formatter, không ghi file hoặc đòi database, nên là ví dụ unit test phù hợp.

JUnit Jupiter cho phép test class và test methods có package-private visibility. Không phải cứ thiếu `public` là Surefire không chạy.

### 8.6. Integration test: GreetingFlowIT.java

Đường dẫn `src/test/java/org/example/boundary/GreetingFlowIT.java`:

~~~java
package org.example.boundary;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class GreetingFlowIT {
    @TempDir
    Path tempDir;

    @Test
    void storesAndReloadsGreetingAcrossComponents() throws IOException {
        Path file = tempDir.resolve("greeting.txt");
        GreetingRepository repository = new GreetingRepository(file);
        GreetingService service = new GreetingService(repository);

        assertEquals("Hello, Maven!", service.greetAndStore("  Maven  "));
        assertEquals("Hello, Maven!",
                Files.readString(file, StandardCharsets.UTF_8));
    }
}
~~~

Đây là JUnit Jupiter integration test hợp lệ:

- `@TempDir` cấp một thư mục tạm do JUnit quản lý để test không đụng file production.
- `GreetingService` gọi `GreetingFormatter` và `GreetingRepository`.
- `GreetingRepository` ghi file thật; test kiểm kết quả trả về **và** đọc lại file từ filesystem.
- Class `GreetingFlowIT` kết thúc bằng `IT`, **không khớp Surefire default `*Test`**, nhưng khớp Failsafe default `*IT`.
- Có **1 test method**. Nó chỉ chạy ở Failsafe trong lượt mặc định của POM này khi lifecycle tiến đến `integration-test`.

Có thể chạy hai test classes bằng IDE bất kể tên, nhưng điều đó **không chứng minh Maven lifecycle có chạy chúng**. Hãy kiểm tra reports từ Maven.

## 9. Thực nghiệm 1: mvn clean test chỉ chạy unit tests

Tại thư mục `failsafe-boundary-demo`:

~~~bash
mvn -B -ntp clean test
~~~

Theo POM và source mẫu:

1. Maven compile ba main classes.
2. Maven test-compile **cả** `GreetingFormatterTest` và `GreetingFlowIT` vào `target/test-classes`.
3. Surefire chạy `GreetingFormatterTest` vì tên khớp `*Test`.
4. JUnit thực thi **2 unit test methods**.
5. Failsafe **chưa được gọi**, vì lifecycle mới tới phase `test`.

Một bản tóm tắt **kết quả dự kiến**, không phải stdout nguyên văn của toàn lệnh Maven:

~~~text
Surefire:
  GreetingFormatterTest -> Tests run: 2, Failures: 0, Errors: 0, Skipped: 0
Failsafe:
  Not executed by "mvn clean test"
~~~

Bạn có thể thấy:

~~~text
target/test-classes/org/example/boundary/GreetingFormatterTest.class
target/test-classes/org/example/boundary/GreetingFlowIT.class
target/surefire-reports/TEST-org.example.boundary.GreetingFormatterTest.xml
~~~

Nhưng **có `GreetingFlowIT.class` trong test output không đồng nghĩa nó đã chạy**. Test compile và test execution là hai bước khác nhau.

Do có `clean`, báo cáo từ một lần build cũ đã được loại bỏ; vì thế không nhầm một `failsafe-reports` cũ thành kết quả của lượt `mvn test` mới.

## 10. Thực nghiệm 2: mvn clean verify chạy cả Surefire và Failsafe

Chạy:

~~~bash
mvn -B -ntp clean verify
~~~

Theo POM mẫu:

1. Surefire ở phase `test`: chạy **2 tests** trong `GreetingFormatterTest`.
2. Maven thực hiện packaging `jar`.
3. Failsafe ở phase `integration-test`: chạy **1 test** trong `GreetingFlowIT`.
4. Phase `post-integration-test` có thể chạy những cleanup goals nếu dự án cấu hình; mẫu không có server riêng nên không có cleanup goal bổ sung.
5. Failsafe `verify` kiểm summary IT; nếu kết quả đúng như code mẫu, build thành công.

Tóm tắt đếm test theo **mã nguồn đã cho**:

~~~text
Surefire:
  GreetingFormatterTest: 2 tests, 0 failures
Failsafe:
  GreetingFlowIT:        1 test, 0 failures
Total methods run:       3 tests
BUILD SUCCESS expected when dependencies/plugins resolve and environment works
~~~

Đây là **số test dự kiến**, không phải giả mạo log thực tế hay thời gian build. Maven có thể hiển thị nhiều dòng phụ, tiền tố logger và report metadata khác nhau.

Sau `verify` thành công, output đáng kiểm tra:

~~~text
target/
├── classes/org/example/boundary/
│   ├── GreetingFormatter.class
│   ├── GreetingRepository.class
│   └── GreetingService.class
├── test-classes/org/example/boundary/
│   ├── GreetingFormatterTest.class
│   └── GreetingFlowIT.class
├── surefire-reports/
│   ├── TEST-org.example.boundary.GreetingFormatterTest.xml
│   └── org.example.boundary.GreetingFormatterTest.txt
├── failsafe-reports/
│   ├── TEST-org.example.boundary.GreetingFlowIT.xml
│   ├── org.example.boundary.GreetingFlowIT.txt
│   └── failsafe-summary.xml
└── failsafe-boundary-demo-1.0.0.jar
~~~

Đây là cây **rút gọn các tệp trọng tâm**, không phải liệt kê mọi Maven metadata/report generated file. Plugin versions hoặc test provider có thể sinh thêm outputs. Tệp `failsafe-summary.xml` là thứ `failsafe:verify` sử dụng để quyết định kết quả IT.

## 11. Vì sao không nên chạy riêng mvn integration-test?

So sánh hai lệnh:

~~~bash
mvn -B -ntp clean integration-test
mvn -B -ntp clean verify
~~~

Lệnh thứ nhất kết thúc **trước** `post-integration-test` và `verify`. Nếu dự án cần dừng một server/container sau IT, cleanup goal bind ở `post-integration-test` **không chạy** trong lệnh thứ nhất.

Quan trọng hơn, nếu integration test chứa assertion lỗi, Failsafe thiết kế để **trì hoãn lỗi kết quả IT**. Vì vậy `mvn integration-test` có thể **trả exit code thành công dù report ghi IT fail**, vì `failsafe:verify` chưa được thực thi. Đừng sử dụng status code ấy để chứng nhận integration tests pass.

Lệnh `mvn verify` đi hết vòng và cho Failsafe kiểm tra summary, nên là lựa chọn đúng.

### Thí nghiệm thất bại (chỉ áp dụng tạm trên bản sao)

Trong `GreetingFlowIT`, thay **một assertion**:

~~~java
assertEquals("WRONG", service.greetAndStore("  Maven  "));
~~~

Đây là **dòng thay thế tạm**, không phải source cuối của ví dụ. Khi chạy `mvn clean verify`, Surefire vẫn có thể pass hai unit tests, Failsafe ghi IT failure và goal `verify` đánh dấu build thất bại. Nếu môi trường có goal cleanup ở `post-integration-test`, nó có cơ hội chạy trước khi verify fail.

Không rút ra kết luận rằng **mọi** lỗi IT đều sẽ đợi tới verify; plugin resolution error hoặc fail tại pre-integration-test vẫn có thể chặn sớm.

Sau thí nghiệm, **khôi phục assertion chính xác** và chạy lại `mvn clean verify` để đưa project về trạng thái build tốt.

## 12. Setup và cleanup môi trường kiểm thử tích hợp

Với một integration test dùng HTTP server/database, vòng lifecycle thường được thiết kế:

~~~text
pre-integration-test
  -> start test server / database container
  -> prepare schema, test dataset

integration-test
  -> Failsafe runs *IT test classes
  -> saves failures to its summary rather than stopping immediately
  -> tests call real endpoint/database

post-integration-test
  -> stop server / container
  -> delete temporary resources

verify
  -> failsafe:verify reads summary
  -> fail build if IT failed
~~~

Những tác vụ start/stop **không tự có** chỉ vì thêm Failsafe. Phải bind goals của plugin quản lý môi trường, ví dụ một server/container plugin, đúng phases tương ứng. Đây là **mô hình lifecycle khái niệm**, không phải POM đầy đủ dùng được ngay cho mọi database.

Một mảnh config phase minh họa, không gắn vào POM runnable:

~~~xml
<execution>
    <id>start-test-environment</id>
    <phase>pre-integration-test</phase>
    <goals>
        <goal>start</goal>
    </goals>
</execution>
<execution>
    <id>stop-test-environment</id>
    <phase>post-integration-test</phase>
    <goals>
        <goal>stop</goal>
    </goals>
</execution>
~~~

**Lưu ý:** `start`/`stop` ở mảnh này là các goal **giả định của một plugin cụ thể**; không được chèn vào chính `maven-failsafe-plugin` vì Failsafe không cung cấp `start`/`stop`. Để cấu hình thật, chọn plugin quản lý test environment phù hợp và đọc tài liệu về goals/daemon/cleanup/port.

Những nguyên tắc nên áp dụng:

- Dùng **test data độc lập**, không gọi production database hoặc endpoint chứa dữ liệu thật.
- Có **timeout/health check** để xác định môi trường đã sẵn sàng trước khi IT chạy.
- Không chia sẻ port/database hoặc thư mục test cố định giữa các CI jobs chạy song song nếu chúng có thể xung đột.
- Cleanup resources kể cả khi job bị hủy bằng cơ chế bổ sung của CI/container platform.
- Không để credentials ở POM hoặc in secret trong log `-X`.
- Giữ environment/test fixtures tái lập bằng container image/version hoặc script ổn định.

## 13. Phân biệt reports và summary file của hai plugin

Mặc định:

| Loại kết quả | Surefire | Failsafe |
| --- | --- | --- |
| Report directory | `target/surefire-reports` | `target/failsafe-reports` |
| File XML test class | `TEST-...Test.xml` | `TEST-...IT.xml` |
| Text report | `...Test.txt` | `...IT.txt` |
| Summary dùng để quyết định IT failures sau cleanup | Không sử dụng Failsafe summary | `failsafe-summary.xml` |
| Phase đánh dấu test failure | Thường `test` | `verify` (đối với kết quả IT) |

Một file XML report có thể chứa:

~~~xml
<testsuite name="org.example.boundary.GreetingFlowIT"
           tests="1" failures="0" errors="0" skipped="0">
    <!-- Nội dung testcase/properties và thời gian chạy đã lược bỏ -->
</testsuite>
~~~

Đây là **mảnh XML minh họa**, không phải report thực từ Maven; nội dung thuộc tính, duration và các phần tử phụ khác có thể thay đổi. Hãy đọc những chỉ số:

- `tests`: số test cases được ghi nhận.
- `failures`: số assertion failures.
- `errors`: lỗi runtime/test infrastructure được báo trong suite.
- `skipped`: test bị bỏ/disabled.
- Tên test class có đúng ở **report directory của plugin mong đợi** không?
- Có `failsafe-summary.xml` và `verify` đã chạy chưa?

**Không ghép bừa số test của Surefire và Failsafe từ các lượt chạy khác nhau.** Nên dùng `mvn clean verify` để có một lần chạy rõ ràng, sau đó lưu cả hai report directories nếu CI cần tổng hợp.

Nếu Surefire pass 2 tests nhưng Failsafe có 0 tests, `mvn verify` có thể thành công **khi Failsafe chưa được cấu hình `failIfNoTests=true`**. Điều đó không chứng minh integration suite tồn tại.

## 14. Kiểm soát trường hợp 0 integration tests

Tài liệu Failsafe nêu `failIfNoTests` **mặc định là false**. Điều đó có nghĩa một module có Failsafe execution nhưng không có class nào khớp `IT*`/`*IT`/`*ITCase` có thể **không fail build chỉ vì thiếu IT**, tùy cấu hình và những điều kiện khác.

Đối với module **bắt buộc có integration tests**, cân nhắc:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-failsafe-plugin</artifactId>
    <version>3.5.2</version>
    <configuration>
        <failIfNoTests>true</failIfNoTests>
    </configuration>
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

Mảnh này thuộc `build/plugins`. POM mẫu ở mục 8 đã bật guard tương đương.

**Giới hạn:** `failIfNoTests=true` chỉ giúp phát hiện tình huống **không có test được chọn để chạy** theo semantics plugin. Nếu có một IT pass nhưng hai IT khác bị bỏ vì đặt tên sai, guard vẫn có thể pass. Cần kết hợp review naming và kiểm tra report/test count tối thiểu trong CI.

Không nên đặt guard `failIfNoTests=true` cho **mọi child** từ parent nếu một số module chỉ là BOM, aggregator, generated code hoặc không thiết kế có IT. Chỉ gắn policy với module/stage thực sự cần IT.

## 15. Chạy một integration test: -Dit.test khác -Dtest

Surefire cung cấp tham số chọn riêng test class:

~~~bash
mvn -B -ntp -Dtest=GreetingFormatterTest test
~~~

Failsafe sử dụng user property khác:

~~~bash
mvn -B -ntp -Dit.test=GreetingFlowIT verify
~~~

Lệnh thứ hai đi tới phase `verify` nên bao gồm Failsafe `integration-test` + `verify` khi cấu hình giống POM mẫu. Nó không phải lệnh chạy goal `failsafe:integration-test` đơn độc.

Bạn có thể chọn method (với provider và phiên bản Failsafe hỗ trợ):

~~~bash
mvn -B -ntp "-Dit.test=GreetingFlowIT#storesAndReloadsGreetingAcrossComponents" verify
~~~

**Phân biệt:**

- `-Dtest=...` chủ yếu dùng để điều khiển Surefire.
- `-Dit.test=...` dùng để điều khiển Failsafe.
- `-Dit.test` chọn **test class/method cho lượt Failsafe này**, không thay đổi quy ước tên mặc định của project trong CI.
- Nếu dùng `-Dit.test=DoesNotExistIT`, Failsafe có `failIfNoSpecifiedTests` (mặc định **true**) để fail khi không tìm thấy test được chỉ định.
- Trong reactor nhiều module, một bộ lọc test tường minh có thể không khớp ở một số module khác, khiến các module đó thất bại; dùng `-pl` chọn Maven module mục tiêu khi thích hợp.

**Cảnh báo:** `-Dit.test=...` không “tắt” Surefire. Khi chạy `mvn verify`, Surefire vẫn có thể chạy tại phase `test` trước Failsafe. Nếu muốn chỉ chạy một integration suite trong job đặc biệt, phải thiết kế pipeline/profile/skip flags phù hợp, không nhầm một tham số với việc bỏ qua những plugin khác.

## 16. Skip flags và rủi ro bỏ qua kiểm thử

Các cờ thường gặp:

| Cờ | Ảnh hưởng thường gặp | Cảnh báo |
| --- | --- | --- |
| `-DskipTests` | Bỏ chạy test ở Surefire; phạm vi ảnh hưởng Failsafe cần đối chiếu phiên bản/cấu hình. | Không dùng trong job yêu cầu cả unit/IT đầy đủ. |
| `-DskipITs=true` | Được Failsafe hỗ trợ để **skip execution của integration tests** nhưng test source có thể vẫn được biên dịch. | Có thể làm `mvn verify` “xanh” mà không có IT chạy. |
| `-Dmaven.test.skip=true` | Bỏ cả test compilation và execution đối với plugin tôn trọng property. | Có thể làm cả unit và IT không chạy. |
| `-Dmaven.test.failure.ignore=true` | Một số test plugins cho phép bỏ qua kết quả thất bại. | Nguy hiểm trong quality gate. |
| `-Dtest=...` | Bộ lọc Surefire. | Không đồng nghĩa Failsafe chọn test. |
| `-Dit.test=...` | Bộ lọc Failsafe. | Không đồng nghĩa Surefire chọn test. |

Vì `-DskipTests` từng có khác biệt giữa các thế hệ Failsafe, **cách rõ ràng nhất để skip riêng integration tests là `-DskipITs=true`** theo tài liệu của Failsafe. Nếu muốn chạy đủ bộ tests, không truyền các skip flags.

Maven phase cũng quan trọng: `mvn package` **không phải** lệnh IT thông thường dù JAR đã được build thành công.

Trước khi kết luận test không chạy do naming, xem log có thông báo “Tests are skipped” hay không, active profiles, hiệu lực của plugin executions và phiên bản plugin.

## 17. Surefire và Failsafe có thể được cấu hình includes/excludes độc lập

Một số dự án không dùng convention `*Test`/`*IT`, ví dụ integration tests kết thúc bằng `*E2E`. Có thể thêm includes cho Failsafe:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-failsafe-plugin</artifactId>
    <version>3.5.2</version>
    <configuration>
        <includes>
            <include>**/IT*.java</include>
            <include>**/*IT.java</include>
            <include>**/*ITCase.java</include>
            <include>**/*E2E.java</include>
        </includes>
    </configuration>
    <executions>
        <execution>
            <goals><goal>integration-test</goal><goal>verify</goal></goals>
        </execution>
    </executions>
</plugin>
~~~

Đây là **mảnh Failsafe config** chứ không phải POM mẫu hoàn chỉnh. Bài tập chính không cần custom includes.

**Quan trọng:** khi khai báo custom `includes`, bạn đang định nghĩa lại bộ patterns được chọn. Nếu chỉ thêm `**/*E2E.java` mà không giữ những pattern `*IT` đang cần, các IT trước đó có thể không còn được chọn.

Tương tự, nếu Surefire muốn chạy tên `*Spec`, cấu hình Surefire separately; đừng sửa Failsafe rồi mong Surefire tự áp dụng. Những excludes giữa hai plugin **không tự đồng bộ**.

Ví dụ một Failsafe exclusion có chủ đích:

~~~xml
<excludes>
    <exclude>**/*UnstableIT.java</exclude>
</excludes>
~~~

Chỉ dùng cách này khi đã có chính sách rõ ràng và tracking để khôi phục test. Việc tạm loại test có thể che regressions; không nên coi một build có nhiều excludes là bộ kiểm thử đầy đủ.

JUnit `@Tag("integration")` cũng **không tự đưa test từ Surefire sang Failsafe**. Muốn dùng tags để lọc, phải cấu hình providers/plugin và class naming/includes theo chủ đích.

## 18. Khi hai plugin vô tình chạy cùng một class

Surefire và Failsafe **không phải hai tập tên loại trừ nhau hoàn toàn**. Nhìn ví dụ:

~~~java
package org.example.boundary;

import org.junit.jupiter.api.Test;

class TestGreetingFlowIT {
    @Test
    void example() {
    }
}
~~~

Đây là **lớp minh họa độc lập**, không nằm trong project runnable mục 8. Tên `TestGreetingFlowIT`:

- Bắt đầu với `Test` → khớp Surefire `Test*.java`.
- Kết thúc với `IT` → khớp Failsafe `*IT.java`.

Vì vậy khi build `mvn verify`, test có thể chạy hai lần: một lần ở Surefire `test` và một lần ở Failsafe `integration-test`.

Tác động:

- Test tốn thời gian gấp đôi.
- Test tạo dữ liệu bên ngoài có thể ghi/đọc trùng, gặp trạng thái không mong muốn.
- Bộ report ghi cùng logic test ở hai thư mục làm người đọc tưởng có hai test riêng.

**Cách xử lý:** thống nhất naming không giao nhau, ví dụ `GreetingFormatterTest` cho unit và `GreetingFlowIT` cho integration. Nếu cần naming khác, cấu hình includes/excludes tương ứng và xác minh cả hai report directories sau `clean verify`.

Đặc biệt tránh `ITSomeTest`, vì prefix `IT` thuộc Failsafe và suffix `Test` thuộc Surefire. Đừng cho rằng nhãn “integration” ở test method là đủ để tránh Surefire chọn class.

## 19. Failsafe không thay thế kiểm thử tích hợp thực sự

Failsafe **chỉ là cơ chế chạy và kiểm kết quả test**. Nó không tự tạo database, Docker container, HTTP server, mock server, secrets, schema hay dữ liệu thử nghiệm.

Nếu integration test cần PostgreSQL, RabbitMQ, Kafka, S3 emulator hay endpoint HTTP, bạn phải thiết kế setup:

- Sử dụng service/container test riêng, version đã được pin.
- Cấp cấu hình qua environment variables hoặc test properties không chứa secrets trong Git.
- Chờ readiness/health checks thay vì chỉ sleep một khoảng cố định.
- Dùng tài nguyên riêng cho mỗi parallel worker.
- Thiết lập timeout và failure diagnostics.
- Cleanup sau test, đồng thời cleanup ở CI khi job bị dừng giữa chừng.
- Không gọi production infrastructure bằng dữ liệu không kiểm soát.

JUnit test method có thể được gắn `@Test` và gọi một HTTP endpoint; **chất lượng integration test nằm ở kiến trúc và assertions**, không nằm ở tên `*IT`. Failsafe giúp điều phối thời điểm chạy và kết quả, còn test suite phải kiểm đúng hành vi.

Với ví dụ file ở mục 8, tính tích hợp ở chỗ hai class và filesystem phối hợp, nhưng nó **không mô phỏng đủ** chi phí setup/teardown của một database server. Bài intentionally dùng một fixture nhỏ, tự cô lập và tái lập được mà không đụng hạ tầng.

## 20. Multi-module Maven: cấu hình Failsafe có chọn lọc

Một reactor có thể gồm:

~~~text
root/pom.xml             # parent/aggregator, packaging pom
├── domain/pom.xml       # unit tests
├── persistence/pom.xml  # integration tests với database
└── api/pom.xml          # unit + HTTP integration tests
~~~

Với project đa module:

- Không phải mọi child đều cần chạy integration tests.
- Nếu parent áp đặt Failsafe `failIfNoTests=true` vào tất cả children, những module không có `*IT` có thể fail một cách không cần thiết.
- Có thể quản lý **version/plugin config** trong parent `pluginManagement`, nhưng chỉ kích hoạt `build/plugins` và executions ở module có integration suite.
- Nếu tổ chức muốn Failsafe chạy trong mọi module, phải có quy tắc xử lý module không có IT và kiểm soát coverage theo module.
- Project dependencies giữa modules phải được khai báo trong `pom.xml`; chỉ liệt kê `<modules>` không tự tạo dependency.

Lệnh chọn Maven module:

~~~bash
mvn -pl :persistence -am clean verify
~~~

Đây là lệnh **minh họa cho reactor thực sự có artifactId persistence**, không áp dụng cho project đơn module mục 8. `-pl` chọn Maven projects; `-am` thêm upstream reactor dependencies. Nó **không tương đương** `-Dit.test=...`, vốn chọn lớp test cho Failsafe.

Nếu dùng `-Dit.test=GreetingFlowIT` khi chạy toàn reactor, module không có class này có thể fail do `failIfNoSpecifiedTests`. Hãy khoanh vùng module phù hợp thay vì vô hiệu hóa guard toàn tổ chức.

## 21. Debug nhanh: vì sao integration test không chạy?

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra |
| --- | --- | --- |
| `mvn test` không chạy `GreetingFlowIT`. | Chưa tới phase Failsafe integration-test. | Dùng `mvn clean verify` khi có Failsafe executions. |
| `mvn verify` chỉ có Surefire reports. | Failsafe chưa bind/không active hoặc không có IT phù hợp. | Xem effective POM, Failsafe log và test names. |
| Class `GreetingFlowIT` có trong `target/test-classes` nhưng không có IT report. | Test compile không đồng nghĩa được Failsafe chạy. | Kiểm `*IT` naming, includes/excludes, skip flags. |
| Class `TestGreetingFlowIT` chạy hai lần. | Tên giao nhau giữa Surefire `Test*` và Failsafe `*IT`. | Đổi tên hoặc cấu hình filters không chồng nhau. |
| `mvn integration-test` trả exit code 0 dù IT fail. | Failsafe trì hoãn test failure tới verify. | Dùng `mvn verify`. |
| `mvn integration-test` chạy server mà không dừng server. | `post-integration-test` chưa được gọi. | Dùng `verify`, có cleanup ở CI. |
| `mvn verify` chạy 0 IT nhưng BUILD SUCCESS. | `failIfNoTests` mặc định false, plugin skip hoặc không có test. | Xác định module cần guard, bật failIfNoTests và kiểm reports. |
| `-Dit.test=NameIT` không tìm thấy class. | Sai tên, wrong module, test source root/config. | Xem test-classes directory và Failsafe selected tests. |
| Unit test compile nhưng Surefire không chạy. | Tên khác default, engine thiếu hoặc test bị filter. | Xem Surefire logs/default patterns, junit-jupiter dependency. |
| Test Failsafe fail nhưng build cuối không fail. | Thiếu goal `failsafe:verify` hoặc bật ignore flags. | Bind cả hai goals, xem summary và effective POM. |
| IT chỉ chạy ở IDE nhưng Maven không chạy. | IDE runner không áp dụng Surefire/Failsafe lifecycle giống Maven. | Xác minh Maven commands/reports trên CI. |
| IT chạy trước khi service sẵn sàng. | Setup phase thiếu readiness check hoặc profile inactive. | Bind start/health-check, kiểm log server. |
| IT pass local, fail CI vì port/temp path. | Môi trường khác, resource dùng chung, race condition. | Dùng isolated fixtures, random ports, timeout, lifecycle cleanup. |
| Reports vẫn có IT dù chỉ gọi `mvn test`. | Reports cũ chưa clean. | Chạy `mvn clean test` rồi kiểm lại. |
| CI bỏ qua IT không chủ đích. | `skipITs`, `skipTests`, `maven.test.skip`, profile. | Xem CLI, effective POM và output Failsafe. |
| JUnit class không có `@Test` đúng framework. | Provider không tìm thấy test descriptor. | Kiểm dependency JUnit engine, annotations và version Surefire/Failsafe. |

Quy trình debug nên theo thứ tự: **lệnh Maven đang tới phase nào → Failsafe có được bind chưa → test source compile chưa → class tên có khớp không → engine chạy bao nhiêu methods → reports/summary có gì → verify goal đã kiểm kết quả chưa**.

## 22. Checklist CI cho unit và integration tests

- [ ] Maven/JDK/compiler/Surefire/Failsafe versions được pin hoặc quản lý rõ.
- [ ] Unit classes theo quy ước `*Test`; integration classes theo `*IT`, tránh tên giao nhau.
- [ ] Project test dependencies có JUnit/TestNG engine phù hợp.
- [ ] Failsafe có **cả goals `integration-test` và `verify`**.
- [ ] Job chạy `mvn clean verify` khi cần integration tests, không chỉ `mvn test` hoặc `mvn integration-test`.
- [ ] Test environment được chuẩn bị tại `pre-integration-test` hoặc workflow tương ứng.
- [ ] Environment có health checks và cleanup tại `post-integration-test`/CI.
- [ ] Có `failIfNoTests=true` cho những module bắt buộc có unit/IT tests.
- [ ] Không truyền skip flags trong CI quality gate.
- [ ] Đã kiểm `surefire-reports` và `failsafe-reports` của cùng một lần build.
- [ ] `failsafe-summary.xml` được tạo và `verify` đã chạy khi Failsafe active.
- [ ] Có quy tắc tối thiểu về số integration tests/coverage cho modules quan trọng.
- [ ] Unit tests chạy nhanh; integration tests tránh phụ thuộc hệ thống production.
- [ ] Port, filesystem, database, container names được cô lập theo CI job.
- [ ] Không lộ credentials qua POM, môi trường hoặc debug log.
- [ ] Khi test fail, phân biệt assertion failure, infrastructure failure và plugin resolution failure.
- [ ] Sau test failure, CI vẫn cố cleanup resources theo cơ chế bổ sung, không trông hoàn toàn vào Maven.
- [ ] Với reactor, cấu hình integration tests chỉ trên modules thật sự cần hoặc có chính sách ngoại lệ minh bạch.

Ví dụ workflow CI rút gọn **chỉ dùng khi repository có Maven Wrapper `mvnw`**:

~~~yaml
name: Verify Java tests
on:
  push:
  pull_request:

jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'
      - name: Run unit and integration tests
        run: ./mvnw -B -ntp clean verify
~~~

Dự án mẫu ở mục 8 **không tự cung cấp Maven Wrapper**. Nếu chưa commit `mvnw`/wrapper files, dùng Maven được CI cài đặt/quản lý và cố định version theo chính sách nhóm. Workflow chỉ minh họa quality gate, không khởi tạo server/database vì integration test mẫu dùng filesystem của runner.

## 23. Câu hỏi tự kiểm tra

1. **Tại sao `mvn test` không chạy `GreetingFlowIT` trong POM mẫu?**  
   Vì phase `test` thuộc Surefire; Failsafe IT goal được bind vào phase `integration-test`, sau `package`.

2. **Khi `mvn verify` chạy, Surefire và Failsafe mỗi plugin chọn class nào?**  
   Surefire chọn `GreetingFormatterTest` (2 methods); Failsafe chọn `GreetingFlowIT` (1 method).

3. **Có thể để cả hai classes trong `src/test/java` không?**  
   Có. Default Maven test compilation tạo `target/test-classes` chung; plugins lọc class theo naming/config khác nhau.

4. **Vì sao không chỉ bind `failsafe:integration-test`?**  
   Vì test failures được Failsafe ghi lại để sau cleanup có thể xử lý; goal `failsafe:verify` cần kiểm summary và fail build nếu IT không đạt.

5. **Lệnh `mvn integration-test` có phải cách đánh giá integration suite hoàn chỉnh?**  
   Không. Nó chưa tới `post-integration-test` và `verify`, nên cleanup và kiểm kết quả cuối có thể chưa chạy.

6. **`mvn verify` ở một dự án không khai báo Failsafe có chắc chạy `*IT`?**  
   Không. Failsafe phải được bind trong `build/plugins` hoặc có execution/lifecycle tương ứng.

7. **Failsafe mặc định chọn tên lớp gì?**  
   `IT*`, `*IT`, `*ITCase` theo ba wildcard patterns trong tài liệu.

8. **Tên `TestBillingIT` có thể gây điều gì khi cả hai plugin chạy?**  
   Có thể được chọn cả ở Surefire (prefix `Test`) và Failsafe (suffix `IT`), gây chạy trùng.

9. **Default `failIfNoTests` của Failsafe là true hay false?**  
   `false`. Nếu module bắt buộc có IT, cấu hình guard một cách có chủ đích.

10. **`-Dit.test=GreetingFlowIT` có đồng nghĩa `-Dtest=GreetingFlowIT`?**  
    Không. Property thứ nhất dành cho Failsafe, thứ hai dành cho Surefire.

11. **`@Tag("integration")` có làm Surefire tự giao test cho Failsafe không?**  
    Không. Plugin selection, includes/excludes và provider tag filtering cần được cấu hình.

12. **Một integration test fail nhưng môi trường vẫn cần cleanup, Failsafe hỗ trợ như thế nào?**  
    Trì hoãn thất bại do assertion/test results tới `verify` để `post-integration-test` có cơ hội chạy.

13. **Vì sao chỉ đọc status BUILD SUCCESS chưa đủ?**  
    Vì plugin có thể chưa được bind, 0 tests có thể không làm build fail theo default, hoặc skip flags đang bật. Cần đọc reports và count thực.

14. **Nếu có IT ở module A nhưng không ở module B, có nên áp `failIfNoTests=true` chung cho mọi module?**  
    Không mặc định. Chỉ áp chính sách bắt buộc IT ở module cần test hoặc thiết kế ngoại lệ rõ.

15. **Failsafe có tự tạo PostgreSQL/Docker server cho `*IT` không?**  
    Không. Test environment cần được tạo bởi framework, CI hoặc plugin/lifecycle goals khác.

## 24. Tài liệu tham khảo chính thức

- [Apache Maven Failsafe Plugin — Introduction](https://maven.apache.org/surefire/maven-failsafe-plugin/index.html): khác biệt với Surefire, bốn lifecycle phases và cơ chế fail-safe.
- [Apache Maven Failsafe Plugin — Usage](https://maven.apache.org/surefire/maven-failsafe-plugin/usage.html): cấu hình `integration-test`/`verify` executions và lệnh `mvn verify`.
- [Apache Maven Failsafe Plugin — Inclusions and Exclusions](https://maven.apache.org/surefire/maven-failsafe-plugin/examples/inclusion-exclusion.html): patterns `IT*`, `*IT`, `*ITCase`.
- [Apache Maven Failsafe Plugin — failsafe:integration-test](https://maven.apache.org/surefire/maven-failsafe-plugin/integration-test-mojo.html): tham số `it.test`, `failIfNoTests`, `failIfNoSpecifiedTests`, skip flags.
- [Apache Maven Failsafe Plugin — failsafe:verify](https://maven.apache.org/surefire/maven-failsafe-plugin/verify-mojo.html): summary file, verification goal và kết quả.
- [Apache Maven Surefire Plugin — Inclusions and Exclusions](https://maven.apache.org/surefire/maven-surefire-plugin/examples/inclusion-exclusion.html): patterns `Test*`, `*Test`, `*Tests`, `*TestCase`.
- [Apache Maven Surefire Plugin — surefire:test](https://maven.apache.org/surefire/maven-surefire-plugin/test-mojo.html): goal và tham số unit test execution.
- [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html): các phase `test`, `pre-integration-test`, `integration-test`, `post-integration-test`, `verify`.
- [JUnit 5 User Guide](https://docs.junit.org/5.11.4/user-guide/): Jupiter `@Test`, `@TempDir` và assertions.

**Ghi nhớ cuối:** **Surefire chạy unit tests trong `test`; Failsafe chạy integration tests ở `integration-test` và quyết định kết quả ở `verify`.** Hãy bind đủ hai goals, đặt tên `*Test` và `*IT` tránh giao nhau, dùng `mvn clean verify` để chạy trọn vòng và đọc **cả Surefire lẫn Failsafe reports**. Failsafe giúp trì hoãn lỗi assertion để cleanup có cơ hội chạy; nó không thay thế setup/teardown hạ tầng, không tự tạo integration tests và không tự bảo đảm test coverage.
