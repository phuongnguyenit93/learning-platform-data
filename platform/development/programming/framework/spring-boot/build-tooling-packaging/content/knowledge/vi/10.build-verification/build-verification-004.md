# Phối hợp `spring-boot:start` và `spring-boot:stop` trong vòng đời kiểm thử tích hợp với Maven

## 1. Mục tiêu và tình huống

Một unit test có thể gọi trực tiếp method Java, nhưng nhiều **integration test** cần kiểm tra ứng dụng Spring Boot thật đang lắng nghe HTTP, kết nối các dịch vụ cần thiết và trả response qua mạng. Nếu chỉ mở server thủ công trước khi chạy test, quy trình CI phụ thuộc vào người thao tác, dễ bỏ sót bước tắt ứng dụng và gây xung đột cổng giữa các lần build.

**Spring Boot Maven Plugin** có hai goal dành riêng cho bài toán:

- **`spring-boot:start`** khởi động Spring Boot application trong một **process riêng** và **không giữ Maven ở trạng thái chặn liên tục** như goal `spring-boot:run`. Maven có thể tiếp tục chạy test khi app đang sống.
- **`spring-boot:stop`** gửi yêu cầu dừng ứng dụng đã được `start` khởi động trước đó, thông qua cơ chế quản lý **JMX** của plugin.
- **Maven Failsafe Plugin** chịu trách nhiệm thực thi integration tests tại `integration-test` và đánh giá kết quả ở `verify`. Failsafe được thiết kế để **lùi việc làm fail build do test assertion đến phase verify**, để phase `post-integration-test` có cơ hội chạy cleanup.

Sau bài học, bạn có thể:

1. Sắp xếp đúng `start → integration-test → stop → verify` theo Maven lifecycle.
2. Phân biệt phase Maven, goal Spring Boot Maven Plugin và goal Maven Failsafe Plugin.
3. Cấu hình **cổng HTTP** và **cổng JMX** độc lập, đảm bảo `start` và `stop` dùng cùng JMX port.
4. Viết `pom.xml` và test Java 17 độc lập có thể gọi HTTP ứng dụng thật trong process do Maven quản lý.
5. Chạy `mvn clean verify` và kiểm chứng test report, log start/stop, endpoint hoạt động khi test và đã dừng sau test.
6. Xử lý test fail, không tìm thấy IT, JMX port conflict, timeout, cấu hình parent khác, skip IT, CI và multi-module.
7. Hiểu giới hạn của cơ chế cleanup: những lỗi build/start/plugin nghiêm trọng vẫn có thể khiến Maven không chạy đến phase stop, do đó CI cần bước thu dọn bổ sung khi cần.

**Ví dụ:** Spring Boot 4.1.2, Java 17+, Maven 3.6.3+ và Maven Failsafe Plugin 3.6.1. Các ví dụ sử dụng endpoint `GET /ping` với body chính xác `pong`, HTTP port `18081`, JMX port `19091` để phân biệt rõ hai loại cổng.

## 2. Bốn phase tích hợp và hai plugin

Maven lifecycle `default` có trình tự quan trọng:

~~~text
validate
   |
compile
   |
test-compile
   |
test                         -> Surefire: unit tests
   |
package                      -> JAR/WAR, Boot repackage nếu cấu hình
   |
pre-integration-test         -> Spring Boot Maven Plugin: start
   |
integration-test             -> Maven Failsafe Plugin: integration-test
   |
post-integration-test        -> Spring Boot Maven Plugin: stop
   |
verify                       -> Maven Failsafe Plugin: verify
~~~

Bảng vai trò:

| Phase | Goal được gắn vào | Đầu vào | Đầu ra / điều kiện PASS |
| --- | --- | --- | --- |
| `test` | `surefire:test` | `*Test.java`, test classes, test runtime | Unit tests kết thúc, report ở `target/surefire-reports` |
| `package` | `jar:jar`, có thể `spring-boot:repackage` | Compiled classes, resources, dependencies | Artifact phục vụ đóng gói; không phải integration test |
| `pre-integration-test` | **`spring-boot:start`** | Classpath ứng dụng, main class, runtime config, cổng | App forked process khởi động và JMX admin sẵn sàng |
| `integration-test` | **`failsafe:integration-test`** | `*IT.java`, endpoint đang chạy, config test | Failsafe chạy IT, ghi kết quả; không làm fail build ngay vì *test assertion failure* |
| `post-integration-test` | **`spring-boot:stop`** | JMX port/name khớp process do start mở | Gửi yêu cầu đóng Spring ApplicationContext và tiến trình có thể kết thúc |
| `verify` | **`failsafe:verify`** | Kết quả IT ở `target/failsafe-reports` | Fail/success build dựa trên integration test result |

**Điểm đặc biệt:** kết quả assertion của integration test **không được vội làm build dừng tại phase `integration-test`**. Nếu chạy test bằng Surefire hoặc một goal thất bại ngay tại phase đó, Maven có thể bỏ qua `post-integration-test` và để ứng dụng tiếp tục chạy. Failsafe sử dụng một goal để chạy test và một goal khác để quyết định kết quả sau cleanup.

**Lưu ý phạm vi:** một process crash, lỗi trong plugin, lỗi phân giải dependency, Maven bị kill, máy CI mất kết nối hoặc stop goal gặp exception có thể làm lifecycle không đến bước stop, dù Failsafe có khả năng hoãn *test failure*. Không nên coi đây là bảo đảm cleanup bất kể mọi loại sự cố.

## 3. Tại sao dùng `spring-boot:start` thay vì `spring-boot:run`?

| Thuộc tính | `spring-boot:run` | `spring-boot:start` |
| --- | --- | --- |
| Mục đích thường dùng | Chạy ứng dụng ở chế độ phát triển | Dùng app đang chạy để phục vụ goal khác, nhất là integration tests |
| Maven có thể tiếp tục goal sau start? | `run` là goal chạy app theo kiểu blocking cho tới khi app dừng | **Có**, goal `start` trở về sau khi startup check thành công |
| Process | Goal có cấu hình fork/run riêng tùy plugin | Khởi động **process riêng** dành cho app IT |
| Tắt tự động trong lifecycle | Không có cặp tự nhiên theo kiểu run | Có goal đồng hành **`spring-boot:stop`** |
| Cơ chế stop | Dừng thủ công/logic khác | JMX quản lý application được start |
| Thích hợp cho `mvn verify` chạy IT HTTP | Không thuận tiện khi dùng run như bước blocking | **Có** khi gắn vào pre/post-integration-test |

`spring-boot:start` thường **không chạy lệnh `java -jar target/...jar`** để mở executable JAR đóng gói; nó khởi động app từ compiled classes và classpath mà plugin thiết lập. Vì vậy IT dùng `start/stop` giúp kiểm tra HTTP behavior ở runtime nhưng **không tự chứng minh JAR cuối cùng đã được repackage và chạy độc lập bằng `java -jar`**. Nếu release yêu cầu kiểm chứng archive thực tế, thêm một smoke test riêng cho packaged artifact.

## 4. Hai loại cổng dễ nhầm: HTTP và JMX

**Cổng HTTP** phục vụ HTTP requests do ứng dụng Spring Boot mở (ví dụ `18081`); các integration tests sẽ gọi `http://127.0.0.1:18081/ping`.

**Cổng JMX** phục vụ quản lý process mà Spring Boot Maven Plugin tự khởi động (ví dụ `19091`; mặc định của plugin là `9001`). `spring-boot:stop` tìm application admin MBean qua kết nối này. Hai cổng **không liên quan về mục đích** và có thể đều cần trống.

~~~text
Maven process
   |
   | spring-boot:start (JMX control; plugin config jmxPort=19091)
   v
Forked Spring Boot process
   | HTTP listener: 18081                -> integration test GET /ping
   | JMX admin listener: 19091           -> spring-boot:stop gửi lệnh dừng
   |
   v
Maven continues failsafe:integration-test -> post-integration-test:stop -> verify
~~~

**Quy tắc:** khi đổi `jmxPort`, nên đặt ở **`<configuration>` cấp plugin**, để `start` và `stop` cùng nhận **một giá trị**; nếu chỉ đổi cổng cho `start` mà `stop` vẫn dùng mặc định `9001`, goal stop không tìm được process cần dừng. Tương tự, nếu server HTTP chạy `18081` nhưng test dùng `8080`, Failsafe sẽ báo lỗi kết nối dù JMX hoạt động đúng.

Tham số đáng nhớ:

| Tham số Boot plugin | Giá trị mặc định / ví dụ | Ý nghĩa |
| --- | --- | --- |
| `jmxPort` | Mặc định `9001`; ví dụ `19091` | Cổng quản lý mà `start` và `stop` phải cùng sử dụng |
| `jmxName` | `org.springframework.boot:type=Admin,name=SpringApplication` | Tên MBean quản lý; cũng cần khớp khi đổi |
| `arguments` | `--server.port=18081` | Argument truyền cho Spring app; quyết định HTTP port |
| `profiles` | Danh sách profile Spring | Chỉ định profile cho process được start |
| `environmentVariables` | Các key/value runtime | Env vars của forked process |
| `systemPropertyVariables` | JVM properties cho forked process | Truyền cấu hình JVM vào app |
| `wait` | Mặc định `500` ms | Khoảng đợi giữa lần kiểm tra startup |
| `maxAttempts` | Mặc định `60` | Số lần kiểm tra tối đa; mặc định khoảng 30 giây |
| `skip` | `false` | Bỏ qua goal khi policy yêu cầu; phải đồng bộ với Failsafe |

Tăng `maxAttempts`/`wait` khi app khởi động chậm có thể giúp môi trường CI; nhưng cần đọc startup log và nguyên nhân vì timeout đôi khi là thiếu DB, profile sai hoặc JVM không đủ bộ nhớ. **JMX readiness của goal start** không đồng nghĩa mọi dịch vụ nghiệp vụ hoặc Actuator readiness probe đều khỏe; test cần tự xác nhận contract mà nó dựa vào.

## 5. Maven POM đầy đủ: một ứng dụng có unit test và HTTP integration test

Ví dụ dùng **Spring Boot starter parent** để giảm số plugin configuration cần quản lý, vì mục tiêu chính của bài là phối hợp start/stop và Failsafe. Phần dùng corporate parent / BOM thuần được trình bày riêng ở mục 12.

Cấu trúc tệp:

~~~text
boot-it-demo/
├── pom.xml
└── src/
    ├── main/
    │   └── java/dev/example/
    │       ├── BootItApplication.java
    │       └── PingText.java
    └── test/
        └── java/dev/example/
            ├── PingTextTest.java
            └── PingIT.java
~~~

### 5.1. `pom.xml` có các execution đúng phase

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

    <groupId>dev.example</groupId>
    <artifactId>boot-it-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <java.version>17</java.version>
        <it.http.port>18081</it.http.port>
        <it.jmx.port>19091</it.jmx.port>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webmvc</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.6.1</version>
            </plugin>

            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
                <configuration>
                    <!-- Cùng một JMX port cho start và stop -->
                    <jmxPort>${it.jmx.port}</jmxPort>
                </configuration>
                <executions>
                    <execution>
                        <id>pre-integration-test</id>
                        <phase>pre-integration-test</phase>
                        <goals>
                            <goal>start</goal>
                        </goals>
                        <configuration>
                            <arguments>
                                <argument>--server.port=${it.http.port}</argument>
                            </arguments>
                            <wait>500</wait>
                            <maxAttempts>120</maxAttempts>
                        </configuration>
                    </execution>
                    <execution>
                        <id>post-integration-test</id>
                        <phase>post-integration-test</phase>
                        <goals>
                            <goal>stop</goal>
                        </goals>
                    </execution>
                </executions>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-failsafe-plugin</artifactId>
                <version>3.6.1</version>
                <configuration>
                    <classesDirectory>${project.build.outputDirectory}</classesDirectory>
                    <systemPropertyVariables>
                        <it.http.port>${it.http.port}</it.http.port>
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
                        <id>verify-integration-tests</id>
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
~~~

**Giải thích POM:**

- Starter parent `4.1.2` quản lý dependency versions và cấu hình Maven tương ứng. Khi Spring Boot Maven Plugin được khai báo, cấu hình repackage từ parent thường tạo executable JAR ở `package`.
- `spring-boot-starter-webmvc` cấp MVC/web server; `spring-boot-starter-test` cung cấp JUnit Jupiter cùng bộ thư viện test.
- `maven-surefire-plugin` phiên bản `3.6.1` chạy **unit tests** ở phase `test`, theo default patterns, trong đó tên `PingTextTest` phù hợp.
- `spring-boot-maven-plugin` có execution **`start` tại `pre-integration-test`** và **`stop` tại `post-integration-test`**. Global `jmxPort` dùng chung. Chỉ execution start cần `--server.port=...`.
- `maven-failsafe-plugin` phiên bản `3.6.1` có **`integration-test` tại phase `integration-test`** và **`verify` tại phase `verify`**. Failsafe nhận giá trị HTTP port qua JVM system property `it.http.port`.
- `<classesDirectory>${project.build.outputDirectory}</classesDirectory>` khiến Failsafe lấy compiled application classes từ `target/classes` thay vì dựa vào cấu trúc class bên trong executable Boot JAR. Spring Boot starter parent đã cấu hình trường này, nhưng việc khai báo tường minh giúp ví dụ rõ và có ích khi chuyển sang parent khác.
- Hai thuộc tính `it.http.port`, `it.jmx.port` giúp tránh hardcode giá trị ở nhiều nơi. Trong CI có thể override bằng `-Dit.http.port=...` và `-Dit.jmx.port=...`, miễn hai cổng trống và mọi goal/test sử dụng cùng cấu hình.
- `wait=500` và `maxAttempts=120` cho startup tối đa khoảng 60 giây (theo cơ chế kiểm tra readiness của plugin), thay vì mặc định khoảng 30 giây.

**Không cấu hình Failsafe goal `verify` vào phase `integration-test`:** Failsafe cần thực hiện verification **sau** `post-integration-test`, để cleanup có thể xảy ra trước khi Maven báo build failure vì assertion.

### 5.2. Ứng dụng Java 17

Tệp **`src/main/java/dev/example/PingText.java`**:

~~~java
package dev.example;

public final class PingText {
    private PingText() {
    }

    public static String body() {
        return "pong";
    }
}
~~~

Tệp **`src/main/java/dev/example/BootItApplication.java`**:

~~~java
package dev.example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class BootItApplication {
    public static void main(String[] args) {
        SpringApplication.run(BootItApplication.class, args);
    }

    @GetMapping("/ping")
    public String ping() {
        return PingText.body();
    }
}
~~~

`@SpringBootApplication` bật các cơ chế Spring Boot application, còn `@RestController` cùng `@GetMapping` xuất HTTP endpoint cho test. Chương trình thực sự nghe HTTP ở cổng được cung cấp bởi `--server.port=...` khi goal start khởi động process.

### 5.3. Unit test `PingTextTest.java`: chạy trước lúc app được start

Tệp **`src/test/java/dev/example/PingTextTest.java`**:

~~~java
package dev.example;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class PingTextTest {
    @Test
    void returnsPong() {
        assertEquals("pong", PingText.body());
    }
}
~~~

`PingTextTest` không cần ứng dụng chạy. Surefire nhận tên `*Test.java` mặc định, nên nó chạy ở phase `test`, **trước `package` và `pre-integration-test`**. Test này chỉ kiểm tra logic, không chứng minh HTTP endpoint hoạt động.

### 5.4. Integration test `PingIT.java`: gọi app đang chạy trong process khác

Tệp **`src/test/java/dev/example/PingIT.java`** sau đây tương thích **Java 17** và là một class hoàn chỉnh:

~~~java
package dev.example;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class PingIT {
    @Test
    void answersOverRealHttp() throws IOException, InterruptedException {
        int port = Integer.parseInt(
                System.getProperty("it.http.port", "18081"));

        HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(5))
                .build();

        HttpRequest request = HttpRequest.newBuilder(
                        URI.create("http://127.0.0.1:" + port + "/ping"))
                .timeout(Duration.ofSeconds(10))
                .GET()
                .build();

        HttpResponse<String> response = client.send(
                request,
                HttpResponse.BodyHandlers.ofString());

        assertEquals(200, response.statusCode());
        assertEquals("pong", response.body());
    }
}
~~~

**Lưu ý tương thích:** Trong Java 17, `java.net.http.HttpClient` chưa triển khai `AutoCloseable`, nên không đặt `HttpClient` vào `try-with-resources`. Ví dụ này tạo client và gọi HTTP trực tiếp; nó biên dịch với JDK 17 khi dự án đã khai báo JUnit Jupiter và có `pom.xml` như trên. Nếu nâng Java, cần xác minh API và cách quản lý tài nguyên theo phiên bản mục tiêu.

Test gọi tới địa chỉ HTTP thực bằng JDK HttpClient. Nó **không** dùng `@SpringBootTest` để mở một application context thứ hai trong JVM của test. Nếu muốn test một ứng dụng đang chạy bằng Maven `start`, gửi HTTP request là phương pháp đơn giản và dễ kiểm chứng nhất.

- Tên class `PingIT` khớp default patterns của Failsafe như `*IT.java`; Surefire mặc định không tự coi class này là `*Test.java`.
- Port lấy từ system property `it.http.port` được Failsafe cấu hình trong POM; vì thế có thể đổi cổng bằng một Maven property.
- `assertEquals(200, ...)` xác nhận status; `assertEquals("pong", ...)` xác nhận response body **chính xác**, không thêm newline.
- `HttpClient.send` có thể ném `IOException` khi app không nghe cổng, `InterruptedException` nếu bị ngắt; Failsafe ghi test failure/error tương ứng.
- Không cần khởi động ứng dụng trong test; Maven `spring-boot:start` đã làm ở `pre-integration-test`.

## 6. Chạy đúng lệnh và xem kết quả

Tại thư mục gốc của ví dụ với JDK 17+ và Maven tương thích:

~~~bash
mvn -version
mvn clean verify
~~~

**Lệnh nên dùng là `mvn clean verify`**. Đây là lệnh chạy toàn bộ các phase cần thiết đến `verify`. Không dùng `mvn integration-test` làm lệnh chính của CI, vì lệnh đó có thể **dừng trước `post-integration-test`** và bỏ qua stop/verification.

Dạng log mong đợi (chỉ là các mốc, không phải stdout cố định):

~~~text
... maven-surefire-plugin:3.6.1:test ...
... maven-jar-plugin:jar ...
... spring-boot-maven-plugin:4.1.2:repackage ...
... spring-boot-maven-plugin:4.1.2:start (pre-integration-test) ...
... maven-failsafe-plugin:3.6.1:integration-test ...
... spring-boot-maven-plugin:4.1.2:stop (post-integration-test) ...
... maven-failsafe-plugin:3.6.1:verify ...
[INFO] BUILD SUCCESS
~~~

**Log có thể hiển thị tên execution, plugin version, timestamp và các thông tin khác tùy Maven; thứ tự phase mới là điều cần kiểm tra.**

Đầu ra report:

~~~text
target/
├── classes/...
├── test-classes/...
├── boot-it-demo-1.0.0.jar
├── surefire-reports/                 # unit tests
│   └── TEST-dev.example.PingTextTest.xml
└── failsafe-reports/                 # integration tests
    ├── TEST-dev.example.PingIT.xml
    └── failsafe-summary.xml
~~~

Mốc report khi hoàn tất:

- `PingTextTest` được Surefire phát hiện, ít nhất 1 unit test chạy và 0 failure/error.
- `PingIT` được Failsafe phát hiện, ít nhất 1 integration test chạy và 0 failure/error.
- `failsafe-summary.xml` và Failsafe verify không báo lỗi.
- Spring Boot start/stop xuất hiện theo đúng thứ tự.
- Khi Maven hoàn tất, không còn HTTP listener của process IT ở cổng `18081`, trừ khi có ứng dụng khác tự dùng cổng đó.

Trên Windows có thể dùng `mvnw.cmd clean verify` nếu dự án **đã có Maven Wrapper**; ví dụ không tự tạo wrapper. Trong Linux/macOS, `./mvnw clean verify` là tương đương khi wrapper tồn tại.

## 7. Chứng minh test failure vẫn cho phép stop chạy

Để kiểm chứng nguyên tắc Failsafe một cách có kiểm soát, tạm đổi assertion integration test (ở một nhánh thử nghiệm) thành giá trị mong đợi sai:

~~~java
assertEquals("not-pong", response.body());
~~~

Rồi chạy:

~~~bash
mvn clean verify
~~~

Kết quả logic mong đợi:

1. App khởi động qua `spring-boot:start` ở `pre-integration-test`.
2. `PingIT` chạy trong `failsafe:integration-test`, assertion **FAIL** và kết quả được lưu.
3. Vì đây là *test failure* mà Failsafe hoãn báo build failure, Maven vẫn đi tiếp tới `post-integration-test`.
4. `spring-boot:stop` được gọi để đóng application context.
5. `failsafe:verify` phát hiện kết quả lỗi trước đó; Maven kết thúc **`BUILD FAILURE`**.

Trong báo cáo Failsafe, dấu hiệu có dạng:

~~~text
PingIT: expected <not-pong> but was <pong>
~~~

Thông điệp assertion cụ thể tùy phiên bản JUnit; đây là **mô tả ý nghĩa**, không phải stdout cố định. Sau bài tập, khôi phục assertion `assertEquals("pong", response.body())` và chạy lại `mvn clean verify`.

**Vì sao không dùng Surefire để chạy IT tại phase `integration-test`?** Surefire có thể làm build fail ngay khi assertion fail, khiến Maven không chạy tới `post-integration-test`. Failsafe được thiết kế để **defer failure tới `verify`**, giúp teardown được thực hiện trong trường hợp test assertion thất bại bình thường.

**Giới hạn cần nhớ:** nếu `spring-boot:start` không thể khởi động app, nếu Maven JVM chết đột ngột, build bị hủy, hoặc một goal khác trả lỗi fatal trước stop, không có bảo đảm `post-integration-test` sẽ chạy. Trong CI nghiêm ngặt, thêm bước cleanup cuối cùng theo khả năng của runner, cô lập process/container và kiểm tra cổng sau build.

## 8. Phân biệt JMX readiness, HTTP readiness và business readiness

`spring-boot:start` dùng một admin MBean trong forked process và kiểm tra trạng thái để biết Spring application đã sẵn sàng theo **cơ chế khởi động của plugin**. Điều này giúp giảm race condition so với việc chạy lệnh `java -jar` trong background rồi cho test chạy ngay lập tức.

Nhưng ba mức trạng thái không giống nhau:

| Mức | Bằng chứng | Chứng minh |
| --- | --- | --- |
| **Startup control** | `start` hoàn thành, MBean được tìm thấy | Process được Boot plugin quản lý và application startup theo điều kiện plugin |
| **HTTP availability** | Integration test gọi `GET /ping` nhận 200 và `pong` | Web listener và route cần thử hoạt động |
| **Business readiness** | Health/readiness probe, DB/message broker, các thao tác nghiệp vụ | Hệ thống đáp ứng những dependency/contract bắt buộc cho testcase |

Lệnh `start` hoàn tất **không tự bảo đảm** database bên ngoài có dữ liệu, broker đã kết nối hay một endpoint được test cụ thể trả đúng. Các điều kiện đó thuộc trách nhiệm integration test/health check. Nếu cần một điều kiện readiness phức tạp, dùng Actuator đúng cách hoặc chiến lược test/retry với timeout tổng thể; không gộp JMX control port vào HTTP port.

### Timeout của `start`

Mặc định `maxAttempts=60` và `wait=500` ms, thời gian chờ xấp xỉ 30 giây. Nếu dự án cần thêm thời gian khởi động ở CI, tăng có kiểm soát và ghi nhận nguyên nhân. Timeout không nên vô hạn vì có thể che lỗi DB, Java/port config hoặc các bean không khởi tạo được.

## 9. Khi project không dùng starter parent

Nếu dự án có **corporate parent** hoặc chỉ import `spring-boot-dependencies` BOM, cần tự xem tất cả cơ chế kế thừa liên quan. Không thể vừa khai báo corporate parent và Boot parent trực tiếp trong cùng `pom.xml`.

Ba trách nhiệm độc lập:

1. **Dependency management:** import `spring-boot-dependencies` vào `dependencyManagement` để các starter/third-party dependencies có version phù hợp.
2. **Build plugin management và packaging:** khai báo đúng version cho `spring-boot-maven-plugin`, compiler, surefire, failsafe; nếu cần executable JAR, gắn `spring-boot:repackage` vào phase `package` khi parent không cung cấp execution.
3. **IT lifecycle:** gắn `spring-boot:start` vào `pre-integration-test`, `spring-boot:stop` vào `post-integration-test` và Failsafe `integration-test` + `verify` vào đúng phase.

**Điểm mà tài liệu Spring Boot đặc biệt nhắc:** starter parent cấu hình Failsafe:

~~~xml
<classesDirectory>${project.build.outputDirectory}</classesDirectory>
~~~

Khi không dùng starter parent, bạn nên khai báo tường minh trong Maven Failsafe Plugin. Nếu không có cấu hình phù hợp, Failsafe có thể cố dùng executable JAR đã được repackage thay vì compiled classes, khiến test không load được class ứng dụng theo đường dẫn classpath thông thường. POM hoàn chỉnh ở mục 5 cũng ghi tường minh thuộc tính này để người học không quên khi chuyển parent.

**Đoạn cấu hình bổ sung khi import BOM, không phải POM độc lập:**

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>4.1.2</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Và khi Boot parent không cấp repackage execution, khai báo goal tại plugin Boot cùng các execution start/stop:

~~~xml
<execution>
    <id>repackage</id>
    <phase>package</phase>
    <goals>
        <goal>repackage</goal>
    </goals>
</execution>
~~~

Đoạn `<execution>` trên thuộc `<executions>` của **chính `spring-boot-maven-plugin`**, bên cạnh start và stop, không phải goal Failsafe. Nếu corporate parent đã cấp execution `repackage`, kiểm tra effective POM để tránh khai báo trùng dẫn tới chạy goal hai lần.

## 10. Cách skip integration tests mà không khởi động app thừa

Khi chạy thử nhanh, đôi khi cần bỏ integration tests nhưng vẫn compile/package ứng dụng. Nếu chỉ dùng một property của Failsafe, chẳng hạn `-DskipITs`, **chưa chắc** goal Boot `start/stop` cũng được skip; kết quả là Maven vẫn khởi động server dù không chạy IT.

Giải pháp là dùng **một property điều khiển cùng lúc ba goal**:

1. Boot `start`: skip khi `skip.it=true`.
2. Boot `stop`: skip khi `skip.it=true`.
3. Failsafe `integration-test` / `verify`: skip cùng property.

Ví dụ đặt property mặc định trong POM:

~~~xml
<properties>
    <skip.it>false</skip.it>
</properties>
~~~

Đoạn dưới đây là **fragment cấu hình bổ sung**, cần ghép vào đúng các plugin/execution đã có, không được tạo trùng `<properties>` hoặc `<configuration>`:

~~~xml
<!-- Bên trong execution spring-boot:start -->
<configuration>
    <skip>${skip.it}</skip>
</configuration>

<!-- Bên trong execution spring-boot:stop -->
<configuration>
    <skip>${skip.it}</skip>
</configuration>

<!-- Bên trong maven-failsafe-plugin -->
<configuration>
    <skip>${skip.it}</skip>
</configuration>
~~~

**Chú ý khi áp dụng:** execution start đã có `<configuration><arguments>...`, nên **thêm `<skip>${skip.it}</skip>` vào cùng `<configuration>` hiện có**; đừng tạo hai khối configuration trùng nhau. Failsafe đã có `classesDirectory` và `systemPropertyVariables` cũng cần được giữ trong cùng configuration.

**Không đặt `<skip>${skip.it}</skip>` ở cấp global Spring Boot plugin** nếu còn cần `repackage` chạy, vì tham số `skip` có thể khiến goal đóng gói cũng bị bỏ qua. Chỉ skip **các execution start/stop**.

Sau khi cấu hình đầy đủ:

~~~bash
mvn clean verify -Dskip.it=true
~~~

có thể bỏ qua IT, start và stop, nhưng những kiểm tra khác vẫn thực hiện theo cấu hình. Lệnh này **không thể được coi là CI quality gate đã chạy đầy đủ IT**; chỉ nên dùng khi policy cho phép.

## 11. Cách kiểm tra kết quả khi Maven chạy

### Bằng chứng 1: effective POM

~~~bash
mvn help:effective-pom -Doutput=effective-pom.xml
~~~

Trong file được tạo, tìm các execution:

- `spring-boot:start` → `pre-integration-test`.
- `failsafe:integration-test` → `integration-test`.
- `spring-boot:stop` → `post-integration-test`.
- `failsafe:verify` → `verify`.
- `jmxPort` dùng chung cho hai goal Boot; HTTP port truyền cho app và cho test cùng giá trị.

### Bằng chứng 2: test report

~~~text
target/surefire-reports/TEST-dev.example.PingTextTest.xml
target/failsafe-reports/TEST-dev.example.PingIT.xml
target/failsafe-reports/failsafe-summary.xml
~~~

Không chỉ nhìn `BUILD SUCCESS`. Nếu report không có `PingIT`, integration test **chưa chắc đã chạy**. Mặc định Failsafe nhận các pattern như `**/IT*.java`, `**/*IT.java`, `**/*ITCase.java`; kiểm tra package, tên class, test engine và báo cáo.

### Bằng chứng 3: process được dừng

Sau `mvn clean verify`, ứng dụng dành cho IT cần đóng xong. Trong ví dụ, `http://127.0.0.1:18081/ping` không còn trả `pong` từ process do build vừa tạo. Không lấy việc port đang không nghe làm bằng chứng duy nhất: cần đối chiếu log `stop` và process/port của chính build; một ứng dụng khác có thể đang sử dụng cùng port.

**Không gọi `mvn integration-test` để “tiết kiệm phase”**: Maven sẽ không đi qua `post-integration-test` và `verify`. Nếu bạn đã chạy lệnh đó và app vẫn sống, có thể chạy goal `spring-boot:stop` trong cùng project với đúng `jmxPort`, nhưng không được mặc định nó luôn sửa được mọi tình huống process/JMX. Khi stop thất bại, xử lý process thuộc build theo cơ chế vận hành phù hợp.

## 12. Tránh xung đột port và trạng thái khi CI chạy song song

Trong ví dụ dùng:

~~~text
HTTP app port: 18081
JMX admin port: 19091
~~~

Đây là **hai port cố định** để dễ học. Khi nhiều module, nhiều branch hoặc hai job CI chạy đồng thời trên cùng host/network namespace, cổng có thể bị chiếm.

Cách giải quyết:

- **Isolate mỗi job** bằng container/runner riêng, hoặc cấp một cặp HTTP/JMX port riêng cho từng ứng dụng và mỗi job.
- Nếu dùng property override, thay cả HTTP và JMX một cách nhất quán, ví dụ:

~~~bash
mvn clean verify -Dit.http.port=18082 -Dit.jmx.port=19092
~~~

- Với integration tests cần ephemeral port, có thể dùng **Build Helper Maven Plugin** để reserve một port trong phase sớm, chuyển port đó vào `<arguments>--server.port=...` và đồng thời vào Failsafe `<systemPropertyVariables>`; Spring Boot có ví dụ chính thức. Tuy nhiên “reserve port” không ngăn race tuyệt đối nếu resource được release trước khi app bind, nên CI vẫn cần isolation/retry có giới hạn.
- Khi đổi JMX port, **giữ cùng `jmxPort` cho start và stop**; khi đổi HTTP port, test phải gọi đúng value được truyền vào app.
- Không để test trên máy A gọi `localhost` với giả định app ở máy B; Failsafe và forked Boot process trong ví dụ này chạy cùng network namespace. Nếu CI chia job/container, phải truyền địa chỉ/port theo kiến trúc thực.

**Rủi ro khi có nhiều instance:** cùng JMX port/HTTP port có thể khiến start thất bại vì bind port hoặc khiến stop gọi nhầm process không thuộc build. Quy tắc operational tốt là tách namespace, gắn nhãn tiến trình và log rõ connection targets.

## 13. Startup chậm, readiness và dependency ngoài

Khi app phụ thuộc database, broker hoặc service ngoài, goal `start` có thể báo timeout hoặc application startup thất bại. Cách khắc phục có thứ tự:

1. Đọc log của Spring Boot forked process để tìm exception gốc, không chỉ dòng “Failed to connect to JMX”.
2. Kiểm tra profile Spring đang được start, environmentVariables, JVM arguments và cấu hình application.
3. Xác minh HTTP port và JMX port đều còn trống.
4. Kiểm tra test dependencies được provision trong CI trước phase pre-integration-test (Testcontainers, Docker Compose hoặc service job theo thiết kế).
5. Điều chỉnh `wait` và `maxAttempts` có giới hạn khi thực sự cần thêm thời gian, không che nguyên nhân.
6. Trong IT, xác minh endpoint và business contract thay vì chỉ dựa vào việc goal start kết thúc.
7. Bổ sung cleanup cuối job để tránh dữ liệu/test process còn tồn tại khi các bước trước đó thất bại bất thường.

Nếu integration test tự khởi động application bằng `@SpringBootTest(webEnvironment=RANDOM_PORT)` trong JVM của test, **không cần đồng thời dùng start/stop chỉ để có HTTP server đó**. Hai chiến lược phục vụ mục tiêu khác nhau:

| Chiến lược | Ai mở app? | Khi nào phù hợp? |
| --- | --- | --- |
| `@SpringBootTest` với server test | Spring TestContext trong JVM test | Test dùng injection, application context, mock/customizers và embedded server |
| Maven `spring-boot:start/stop` + Failsafe | Boot plugin mở process riêng | Kiểm thử black-box HTTP từ bên ngoài process app, hoặc tool không trực tiếp tạo Spring context |
| `java -jar` smoke test | Script/CI mở executable archive | Kiểm thử chính artifact sẽ phát hành, Boot loader và runtime package |

Không cần dùng cả ba ở mọi dự án. Chọn chiến lược dựa trên contract cần chứng minh.

## 14. Multi-module và thứ tự start/stop

Ví dụ Maven reactor:

~~~text
platform-parent/             packaging=pom
├── core/                    packaging=jar (library)
├── data/                    packaging=jar (library)
└── web-app/                 packaging=jar (Spring Boot application)
~~~

**Chỉ bind `start/stop` vào module cần một application đang chạy**, ví dụ `web-app`. Parent `pom` không có main application, còn module library không có server HTTP để khởi động. Có thể đặt plugin version/config quản lý chung trong `pluginManagement` của parent rồi kích hoạt execution ở module web.

Nếu các module được build **song song** qua Maven `-T`, phải chú ý:

- Các ứng dụng/module chạy đồng thời không được tranh cùng port HTTP/JMX.
- Dependencies theo thứ tự Maven reactor không tự quản lý test databases hoặc lifecycle process của module khác.
- Nếu IT của module này gọi ứng dụng khác, cần bố trí các dịch vụ đó ở CI hoặc profile rõ ràng.
- Một execution `start` bị inheritance lan tới mọi child module có thể khiến reactor fail vì module library thiếu main class.

**Quy tắc review:** xác minh trong `mvn help:effective-pom` của đúng module, xem start/stop chỉ xuất hiện ở module app.

## 15. Lỗi thường gặp và chẩn đoán

| Triệu chứng | Nguyên nhân đáng kiểm tra | Cách xử lý |
| --- | --- | --- |
| `mvn integration-test` hoàn thành nhưng app vẫn chạy | Chưa tới phase `post-integration-test` | Dùng `mvn verify` / `mvn clean verify`; stop process còn sót có kiểm soát |
| `mvn verify` không thấy goal `start` | Plugin execution chưa được bind, profile chưa bật hoặc đang chạy nhầm module | Xem effective POM, ID, phase, goals, reactor |
| App chạy ở HTTP 18081 nhưng IT gọi 8080 | Port trong Failsafe và start không đồng bộ | Dùng property chung `it.http.port` |
| `spring-boot:stop` không tìm được MBean | JMX port/name khác, app đã chết, process khác chiếm port | Dùng global `jmxPort` cho start/stop, kiểm tra startup log |
| `Address already in use` khi start | HTTP/JMX port trùng với job khác hoặc process cũ chưa thoát | Cấp port riêng, isolate runner, dọn process cũ đúng ownership |
| `start` timeout | App chưa ready, lỗi config/DB, thiếu JDK hoặc chậm startup | Xem forked process log, tăng wait/maxAttempts có chủ đích |
| `PingIT` bị Surefire chạy quá sớm | Đổi pattern/ cấu hình Surefire nhận cả `*IT` | Tách naming/include theo đúng Surefire `*Test` và Failsafe `*IT` |
| `BUILD SUCCESS` nhưng không có IT report | Failsafe goal chưa bind, skip flag, không phát hiện test | Xem Failsafe reports và tên `PingIT`; coi “0 tests” theo policy |
| Integration test fail nhưng stop không chạy | Fatal lỗi plugin/start/Maven bị kill hoặc Failsafe verify bind sai phase | Đảm bảo Failsafe verify **sau** stop; thêm CI cleanup khi cần |
| Failsafe không load được class ứng dụng | Không dùng starter parent, `classesDirectory` sai khi JAR đã repackage | Cấu hình `${project.build.outputDirectory}` |
| `@SpringBootTest` mở server khác làm test sai port | Vừa dùng Boot plugin start vừa để Spring test tự mở context riêng | Dùng black-box HTTP test hoặc chọn một chiến lược phù hợp |
| Test pass khi app đã chết | IT chỉ kiểm tra method/mock mà không gửi HTTP tới process đang chạy | Dùng JDK HttpClient/RestClient thật và assert status/body |
| App không thoát dù stop được gọi | Spring ApplicationContext đóng nhưng còn non-daemon threads/resource chưa shutdown | Đóng thread pools/schedulers và xác minh process thực sự kết thúc |
| CI parallel bị flake | Cổng cố định, DB chung, dữ liệu test chưa cách ly | Dùng isolated environment và port/cơ sở dữ liệu riêng |
| `mvn package` không chạy integration test | Dừng trước `pre-integration-test` | Dùng `mvn verify` để chạy IT lifecycle |

Để truy nguyên, tìm **goal/phase đầu tiên bị lỗi**, kiểm tra input tương ứng, đối chiếu log Maven cùng report Surefire/Failsafe và trạng thái forked process. Không chữa sai bằng cách xóa random cache hoặc bỏ qua test bắt buộc.

## 16. Cổng QA cho CI

Một pipeline tích hợp cơ bản nên áp dụng:

| Cổng | Điều kiện PASS | Bằng chứng |
| --- | --- | --- |
| Maven/JDK hợp lệ | Wrapper/build tool và Java đủ yêu cầu | `mvn -version`, version file |
| Unit tests | `PingTextTest` đã chạy và không fail | Surefire XML |
| Packaging | Có executable archive phù hợp nếu phát hành JAR | Log Boot repackage, `jar tf` |
| Boot start | Process khởi động, JMX admin trả tín hiệu đúng | `spring-boot:start` log, startup log |
| Integration tests | `PingIT` được phát hiện, HTTP status/body khớp | Failsafe XML |
| Boot stop | `spring-boot:stop` thực hiện; process đóng | Maven goal log, kiểm tra port/process |
| Failsafe verify | Kết quả IT được đánh giá và build pass/fail đúng | `failsafe:verify` + Maven exit code |
| Cleanup khi bất thường | Không còn process IT mà pipeline đã tạo | CI finally/post-job cleanup |

**Nếu policy yêu cầu IT, báo cáo `Tests run: 0` là FAIL về chất lượng dù Maven trả exit code 0.** Có thể bật `failIfNoTests` trong cấu hình Failsafe khi phù hợp, nhưng cần xem tương tác với teardown khi cấu hình đó làm plugin báo lỗi ở thời điểm chạy; phải có CI cleanup vững chắc trong những tình huống fail sớm.

Không đăng Maven/JMX debug port ra mạng công cộng. Trong môi trường CI, chỉ mở cổng trên network namespace đáng tin, quản lý biến môi trường/credentials cẩn thận và không đưa secrets vào log.

## 17. Bài tập tự kiểm tra

**Câu 1.** Vì sao `spring-boot:run` không phải lựa chọn thuận tiện để gắn trước Failsafe integration test?

**Đáp án:** Goal `run` thường chạy app theo cách giữ Maven chờ cho đến khi app dừng; `start` được thiết kế để không block pipeline, để Maven tiếp tục chạy test và dùng `stop` dừng app.

**Câu 2.** `spring-boot:start` thuộc phase nào, `spring-boot:stop` thuộc phase nào?

**Đáp án:** Bind `start` vào `pre-integration-test` và `stop` vào `post-integration-test`. Không phải Maven tự bind hai goal nếu chưa cấu hình execution.

**Câu 3.** Tại sao Failsafe cần hai goal `integration-test` và `verify`?

**Đáp án:** Goal đầu chạy/ghi nhận IT; goal sau đánh giá kết quả khi cleanup đã hoàn tất. Nhờ đó một lỗi assertion thông thường không khiến Maven bỏ qua `post-integration-test`.

**Câu 4.** Tại sao `mvn integration-test` không đủ?

**Đáp án:** Nó dừng trước `post-integration-test` và `verify`, nên có thể chưa stop app và chưa báo kết quả IT cuối cùng.

**Câu 5.** HTTP port `18081` có phải JMX port `19091` không?

**Đáp án:** Không. HTTP port phục vụ endpoint ứng dụng; JMX port là kênh plugin quản lý process để stop. Hai giá trị độc lập và phải được cấu hình đúng bên liên quan.

**Câu 6.** `PingTextTest` và `PingIT` khác nhau ra sao?

**Đáp án:** `PingTextTest` là unit test chạy bởi Surefire ở phase `test`; `PingIT` gửi request HTTP tới process Spring Boot do goal `start` mở và chạy qua Failsafe ở `integration-test`.

**Câu 7.** Project dùng corporate parent và import BOM Boot. Điều gì cần lưu ý?

**Đáp án:** Import BOM không cấp plugin executions. Phải cấu hình Boot start/stop, Failsafe integration-test/verify, plugin versions; đặt `classesDirectory=${project.build.outputDirectory}` khi không dùng starter parent để Failsafe load classes đúng.

**Câu 8.** Test assertion fail. Có chắc process luôn stop không?

**Đáp án:** Với flow Failsafe thông thường, assertion failure được defer để `post-integration-test` chạy. Nhưng lỗi fatal, kill Maven, crash JVM hoặc stop lỗi có thể ngăn cleanup; cần dự phòng ở CI.

**Câu 9.** Bật `-DskipITs` chỉ cho Failsafe có đủ để không khởi động app không?

**Đáp án:** Không chắc. Phải đồng bộ skip của cả Boot `start/stop` với Failsafe để tránh khởi động server không cần thiết.

**Câu 10.** Chạy `mvn clean verify` có nghĩa đã test executable JAR bằng `java -jar` chưa?

**Đáp án:** Chưa hẳn. `spring-boot:start` dùng compiled classes/classpath theo plugin; smoke test archive bằng `java -jar` là kiểm chứng bổ sung nếu artifact packaging là một phần release contract.

## 18. Checklist áp dụng ngay

- [ ] Đúng phiên bản Spring Boot/JDK/Maven và starter cần dùng.
- [ ] Boot `start` bound vào `pre-integration-test`, `stop` bound vào `post-integration-test`.
- [ ] Maven Failsafe `integration-test` bound vào phase `integration-test`; `verify` bound vào phase `verify`.
- [ ] Cùng `jmxPort`/`jmxName` cho start và stop, tách rõ với HTTP port.
- [ ] App nhận `--server.port` đúng, IT nhận cùng port qua JVM property.
- [ ] Test class IT khớp pattern Failsafe như `*IT.java`; unit test khớp Surefire `*Test.java`.
- [ ] Dùng `mvn clean verify` để chạy đầy đủ lifecycle; tránh dừng ở `integration-test`.
- [ ] Kiểm tra Surefire/Failsafe XML, test count, failures/errors, không chỉ đọc `BUILD SUCCESS`.
- [ ] Kiểm tra app process kết thúc sau stop; có phương án cleanup khi lifecycle bị ngắt.
- [ ] Với corporate parent, pin plugin versions, gắn repackage nếu cần và khai báo Failsafe `classesDirectory` đúng.
- [ ] Khi skip IT, đồng bộ skip của Boot start, Boot stop và Failsafe.
- [ ] Với CI chạy song song, mỗi app/job dùng port hoặc network namespace riêng.
- [ ] Với release executable, bổ sung kiểm tra `java -jar` nếu cần kiểm chứng archive thực tế.

**Ghi nhớ:** **`pre-integration-test: start → integration-test: Failsafe chạy IT → post-integration-test: stop → verify: Failsafe kết luận`**. Cặp start/stop quản lý vòng đời ứng dụng, còn Failsafe quản lý việc chạy và kết luận test; thực thi đầy đủ bằng `mvn verify` giúp tắt ứng dụng trước khi Maven trả lỗi do test assertion.

## 19. Tài liệu chính thức

1. [Spring Boot Maven Plugin 4.1.x — Running Integration Tests; start/stop](https://docs.spring.io/spring-boot/maven-plugin/integration-tests.html)
2. [Spring Boot Maven Plugin — Using the Plugin](https://docs.spring.io/spring-boot/maven-plugin/using.html)
3. [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
4. [Maven Failsafe Plugin — Introduction](https://maven.apache.org/surefire/maven-failsafe-plugin/index.html)
5. [Maven Failsafe Plugin — Usage](https://maven.apache.org/surefire/maven-failsafe-plugin/usage.html)
6. [Maven Failsafe Plugin — Test Pattern / JUnit Platform](https://maven.apache.org/surefire/maven-failsafe-plugin/examples/junit-platform.html)
7. [Maven Failsafe Plugin — integration-test Goal](https://maven.apache.org/surefire/maven-failsafe-plugin/integration-test-mojo.html)
8. [Maven Failsafe Plugin — verify Goal](https://maven.apache.org/surefire/maven-failsafe-plugin/verify-mojo.html)
9. [Spring Boot — System Requirements](https://docs.spring.io/spring-boot/system-requirements.html)
