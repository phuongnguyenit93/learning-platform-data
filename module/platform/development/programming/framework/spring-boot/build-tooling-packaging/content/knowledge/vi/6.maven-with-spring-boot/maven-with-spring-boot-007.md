# Chạy các goal `run`, `start`, `stop` và `help` đúng mục đích trong Spring Boot Maven Plugin

## 1. Chọn đúng goal trước khi gõ lệnh

Khi phát triển một ứng dụng Spring Boot bằng Maven, bạn có thể cần **chạy app để thử nhanh**, **khởi động app phục vụ integration test trong lifecycle**, **dừng đúng app đã được plugin khởi động**, hoặc **tra cứu cách cấu hình plugin**. Bốn mục đích này tương ứng với bốn goal khác nhau của `spring-boot-maven-plugin`:

| Goal | Mục đích | Maven invocation có chờ ứng dụng chạy không? | Khi nào nên dùng? |
| --- | --- | --- | --- |
| `spring-boot:run` | Chạy ứng dụng ngay từ classes/resources và dependency classpath của dự án. | **Có**: invocation ở foreground, thường tiếp tục chiếm terminal trong khi ứng dụng chạy. | Phát triển local, thử endpoint, debug hoặc kiểm tra cấu hình khi đang sửa mã. |
| `spring-boot:start` | Khởi động ứng dụng ở process riêng, xác nhận trạng thái start và **trả quyền điều khiển** cho Maven. | **Không chờ ứng dụng chạy đến khi dừng**; chỉ chờ startup/ready trong giới hạn cấu hình. | Trước khi chạy bài test tích hợp cần ứng dụng thực. |
| `spring-boot:stop` | Yêu cầu dừng ứng dụng do `start` trước đó quản lý. | Chạy xong thao tác dừng thì goal kết thúc. | Sau integration test, ở phase `post-integration-test` hoặc dừng phiên `start` thủ công. |
| `spring-boot:help` | In thông tin các goal/tham số cấu hình của plugin. | Không chạy ứng dụng. | Kiểm tra tên property, kiểu dữ liệu, default và tham số được plugin phiên bản hiện tại hỗ trợ. |

**Quy tắc một câu:** *run để phát triển*, *start + stop để quản lý vòng đời phục vụ kiểm thử*, *help để tra cứu*. Cả bốn là **Maven plugin goals**; chúng **không** phải các HTTP endpoint, không tương đương `java -jar`, và không tự thay thế `mvn test` / `mvn verify`.

Tên plugin đầy đủ là `org.springframework.boot:spring-boot-maven-plugin`. Cú pháp tiền tố `spring-boot:...` hoạt động khi Maven phân giải được plugin từ POM/plugin metadata. Tốt nhất dùng Maven Wrapper của project và khai báo plugin trong `pom.xml` để mọi người cùng dùng phiên bản dự định.

> **Bối cảnh phiên bản:** bài thực hành dùng Spring Boot **3.3.13**, Java 17 và Maven phù hợp dòng đó; đây là phiên bản minh họa để giải thích hành vi, không phải tuyên bố phiên bản mới nhất. Xem hướng dẫn plugin **đúng phiên bản project** khi tên goal/property hoặc chính sách vận hành có thay đổi.

## 2. Goal và Maven lifecycle: đừng nhầm cách gọi

Một Maven *phase* (ví dụ `compile`, `test`, `package`, `integration-test`, `verify`) có thể kích hoạt nhiều plugin goals đã được cấu hình. Một *goal* là thao tác cụ thể do plugin thực thi.

Hai cách chạy phổ biến:

~~~bash
# Gọi trực tiếp một goal của Spring Boot Maven Plugin
./mvnw spring-boot:run

# Chạy các phase của Maven, trong đó một số goal có thể được bind vào phase
./mvnw verify
~~~

Nếu gọi `spring-boot:run` trực tiếp, người dùng chủ ý mở app để dùng local. Nếu bind `start`, `failsafe:integration-test`, `stop` và `failsafe:verify` vào Maven lifecycle, `mvn verify` có thể **tự phối hợp** khởi động app, test, dừng app và báo kết quả. Nhiều người nhầm rằng chỉ cần thêm Spring Boot plugin thì `verify` đã có integration test; thực tế **phải khai báo Failsafe/test và executions đúng**.

### 2.1. Liên hệ với `package` và `repackage`

- `spring-boot:run`: chạy từ classpath build; **không** phải phép thử xem executable JAR đã đóng gói chạy được chưa.
- `spring-boot:start`: cũng chạy ứng dụng phục vụ build/test; không phải “khởi chạy JAR production” theo nghĩa deploy.
- `spring-boot:stop`: đóng vòng đời của `start`; không quản lý tất cả JVM trên máy.
- `spring-boot:help`: chỉ hiển thị thông tin plugin.
- `spring-boot:repackage`: một goal **khác**, dùng để tạo executable archive từ JAR/WAR đã có. Để kiểm chứng chính sản phẩm bàn giao, chạy `mvn clean package` rồi `java -jar target/<ten-file-that>.jar` (với artifact phù hợp).

Đối với app Web có endpoint, việc `run` thành công **chưa đủ** thay thế unit test, integration test, đóng gói artifact, smoke test hay quality gate phát hành.

## 3. `spring-boot:run` — chạy local, invocation ở foreground

### 3.1. Điều kiện cần

Project có Spring Boot application class với `public static void main(String[] args)`, classpath dependency và Spring Boot Maven plugin. Trong dự án Maven đang có Java source, Maven có thể chuẩn bị những output cần thiết theo cấu hình và goal; khi cần phân biệt build lỗi với runtime lỗi, chạy `./mvnw test-compile` trước là cách làm rõ trạng thái compile.

~~~bash
# macOS/Linux
./mvnw spring-boot:run

# Windows PowerShell/cmd, khi dùng Maven Wrapper của project
mvnw.cmd spring-boot:run
~~~

Maven invocation **tiếp tục ở terminal** khi ứng dụng còn chạy. Ứng dụng thực tế chạy trong **JVM fork** do plugin tạo; do đó JVM option và system property cho ứng dụng phải chuyển đúng kênh. Không xem `-Dfoo=bar` của Maven là Java system property tự động truyền vào process ứng dụng.

Để dừng `run` khi chạy tương tác, thông thường nhấn **Ctrl+C tại terminal đang chạy goal** và xác nhận process đã kết thúc. `spring-boot:stop` được thiết kế cho app do `start` quản lý; **không dùng nó như nút dừng mặc định cho `run`**.

### 3.2. Truyền application arguments đúng cách

Spring Boot command-line application arguments là các đối số mà `SpringApplication` có thể đọc, ví dụ `--server.port=18085`, `--spring.profiles.active=dev`. Plugin 3.3 cung cấp property `spring-boot.run.arguments` để truyền chúng.

~~~bash
# Chạy ứng dụng web trên cổng HTTP 18085
./mvnw spring-boot:run -Dspring-boot.run.arguments="--server.port=18085"

# Truyền hai đối số ứng dụng
./mvnw spring-boot:run -Dspring-boot.run.arguments="--server.port=18085 --spring.application.name=goal-demo"
~~~

Khi app thực sự khởi động và có endpoint `/ping`, ở terminal khác:

~~~bash
curl -i http://localhost:18085/ping
~~~

Đánh giá response bằng status HTTP và body **thực tế**, không suy từ chữ `BUILD SUCCESS` hay một log startup cố định. Nếu server mặc định đang dùng 8080 hoặc port khác, cần dùng đúng giá trị đã truyền. Với ứng dụng không có embedded HTTP server (ví dụ batch/CLI), thay phép thử endpoint bằng kiểm chứng job/exit code/đầu ra đặc trưng của ứng dụng.

### 3.3. Profile, JVM arguments và system properties

| Loại thiết lập | Ví dụ lệnh | Được gửi tới đâu? |
| --- | --- | --- |
| Spring profile | `./mvnw spring-boot:run -Dspring-boot.run.profiles=dev,local` | Shortcut của plugin để chọn profile ứng dụng. |
| Application arguments | `./mvnw spring-boot:run -Dspring-boot.run.arguments="--server.port=18085"` | Các đối số Spring Boot nhận trong `main(String[] args)`. |
| JVM arguments | `./mvnw spring-boot:run -Dspring-boot.run.jvmArguments="-Xmx512m -Dexample.mode=local"` | JVM fork chạy ứng dụng: heap, JDWP, system properties. |
| Maven user property | `./mvnw spring-boot:run -Dsome.maven.option=value` | Maven/plugin configuration; **không mặc định biến thành JVM property** bên trong app. |

Bạn cũng có thể khai báo `<arguments>`, `<jvmArguments>`, `<profiles>`, `<systemPropertyVariables>` hoặc `<environmentVariables>` trong `<configuration>` của plugin. Khi dùng nhiều profile, dấu phẩy trong `spring-boot.run.profiles=dev,local` là định dạng được plugin hỗ trợ.

Ví dụ cấu hình mặc định ở POM (mảnh cấu hình **không phải POM đầy đủ**):

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <configuration>
        <profiles>
            <profile>local</profile>
        </profiles>
        <jvmArguments>-Xmx512m</jvmArguments>
        <arguments>
            <argument>--server.port=18085</argument>
        </arguments>
    </configuration>
</plugin>
~~~

**Phân biệt hai port:** `server.port` là cổng HTTP ứng dụng, **không** phải `jmxPort` của plugin dùng cho `start`/`stop` (xem mục 4).

### 3.4. Debug và DevTools

Khi cần gắn debugger vào JVM ứng dụng, cấu hình JDWP qua `spring-boot.run.jvmArguments`. Ví dụ trên máy phát triển với JDWP chỉ bind loopback:

~~~bash
./mvnw spring-boot:run -Dspring-boot.run.jvmArguments="-agentlib:jdwp=transport=dt_socket,server=y,suspend=y,address=127.0.0.1:5005"
~~~

Khi `suspend=y`, app chờ debugger trước khi chạy vào main; việc chưa thấy server mở cổng HTTP là hành vi có chủ đích. Không mở cổng debug công khai cho môi trường không tin cậy.

`spring-boot-devtools` là hỗ trợ quá trình phát triển (restart/Livereload trong điều kiện phù hợp); `spring-boot:run` tự nó không bảo đảm hot reload mọi thay đổi Java/resource. Khi bật `addResources=true`, plugin có thể đưa resource source trực tiếp lên classpath nhưng làm mất hiệu lực filtering ở build time cho resource đó; kiểm tra nhu cầu thật trước khi bật.

## 4. `spring-boot:start` — khởi động cho integration test, rồi trả quyền điều khiển

`start` cũng tạo JVM riêng để chạy Spring Boot application nhưng có mục đích khác `run`:

1. Khởi động ứng dụng và thiết lập cơ chế quản lý trạng thái thông qua **JMX**.
2. Chờ trong giới hạn `maxAttempts` và `wait` để nhận diện app sẵn sàng theo cơ chế plugin.
3. **Trả quyền điều khiển cho Maven** sau khi goal hoàn tất bước start, trong khi app vẫn chạy.
4. Cho phép các Maven goals tiếp theo (ví dụ Failsafe integration test) tương tác với app.
5. Dùng `stop` để yêu cầu shutdown sau khi kiểm thử.

~~~text
Maven lifecycle:
  pre-integration-test
     -> spring-boot:start     (spawn app + JMX readiness)
  integration-test
     -> failsafe:integration-test (test HTTP/DB/service thật)
  post-integration-test
     -> spring-boot:stop      (lifecycle cleanup)
  verify
     -> failsafe:verify      (đánh giá kết quả test)
~~~

Đây là chuỗi thích hợp cho build/test pipeline. `start` **không** phải daemon/service manager dùng để vận hành production; hệ thống triển khai thật nên dùng executable artifact và process manager/container orchestrator đúng môi trường.

### 4.1. JMX handshake khác với HTTP

Mặc định plugin sử dụng cổng JMX **9001** để liên lạc với ứng dụng khởi động bởi `start`. Cổng HTTP (mặc định Spring Boot Web thường 8080) độc lập. Nếu một cổng bị chiếm, đổi đúng cổng và giữ đồng bộ chỗ cấu hình.

| Cổng | Do ai dùng? | Dùng để làm gì? |
| --- | --- | --- |
| `server.port=18085` | Embedded web server của Spring Boot. | Client/test gọi `http://localhost:18085/...`. |
| `jmxPort=19009` | Spring Boot Maven Plugin và JVM app trong cơ chế quản lý start/stop. | Maven đợi startup, liên lạc qua MBean, ra lệnh stop. |

**Không** gửi HTTP request đến cổng JMX và không cho `curl` gọi `localhost:19009`; `curl` phải gọi HTTP port. Plugin dùng MBean name mặc định `org.springframework.boot:type=Admin,name=SpringApplication`; nếu tùy biến `jmxName` hay `jmxPort` thì **start và stop cần cùng cấu hình**.

Các tham số thường gặp:

- `jmxPort`: cổng JMX dùng để liên lạc; ví dụ 19009.
- `jmxName`: tên MBean quản lý, dùng mặc định nếu không có nhu cầu đặc biệt.
- `wait`: số mili giây giữa các lần kiểm tra readiness, mặc định 500 ms trong tài liệu dòng 3.3.
- `maxAttempts`: số lần kiểm tra tối đa, mặc định 60; theo cấu hình mặc định tương ứng xấp xỉ 30 giây chờ.
- `arguments` / `profiles` / `jvmArguments`: truyền thiết lập ứng dụng/JVM tương tự `run`.
- `skip`: cho phép bỏ qua goal khi điều kiện đã được phê duyệt.

Việc JMX báo ứng dụng đã start là tín hiệu để tiến hành test; **không thay thế assertion** rằng endpoint/DB/downstream hành xử đúng. Nếu startup timeout, đọc logs của JVM và kiểm tra cổng, profile, dependency bên ngoài, JMX config trước khi tùy tiện tăng `maxAttempts`.

## 5. `spring-boot:stop` — dừng đúng ứng dụng do `start` quản lý

Sau khi `start` hoàn tất, ứng dụng tiếp tục chạy riêng. `stop` tìm MBean tương ứng trên cổng JMX đã cấu hình và yêu cầu app kết thúc:

~~~bash
# Khi cùng POM đã cấu hình jmxPort/jmxName cho start và stop
./mvnw spring-boot:stop
~~~

Điều kiện quan trọng:

- `stop` được thiết kế cho **ứng dụng đã khởi động bằng `spring-boot:start`**.
- Nếu `start` dùng cổng JMX 19009, `stop` cũng phải dùng **19009**.
- Cổng JMX này **không phải** `server.port` và không phải một Spring MVC Actuator HTTP shutdown endpoint.
- Nếu test, shell hoặc Maven process bất thường ngắt trước `stop`, có thể còn process đang chạy. Cần xác định chính xác PID và cách cleanup theo môi trường; không kill tất cả process `java` vì có thể ảnh hưởng ứng dụng khác.
- Với project chạy nhiều app song song, mỗi process quản lý cần JMX port không xung đột. Nhiều module cùng dùng mặc định 9001 trên một host có thể làm integration test không ổn định.

Không coi việc chạy `stop` là test business logic. Nó chỉ đóng vòng đời mà `start` đã mở.

### 5.1. Vì sao nên bind vào `post-integration-test`?

Nếu chạy thủ công `start` rồi quên `stop`, app có thể giữ cổng, tệp tạm hoặc tài nguyên test. Gắn cặp goal vào hai phase của Maven giúp quy trình thống nhất và dễ dùng ở CI:

~~~text
pre-integration-test : spring-boot:start
integration-test     : maven-failsafe-plugin:integration-test
post-integration-test: spring-boot:stop
verify               : maven-failsafe-plugin:verify
~~~

Failsafe được thiết kế để **đánh giá kết quả test ở `verify`**, nhờ đó test assertion fail thường không làm Maven ngừng ở phase `integration-test` trước khi có cơ hội chạy `post-integration-test`. Tuy vậy lỗi build/tool nghiêm trọng, runner bị kill hoặc lỗi ngay khi `start` vẫn có thể phá luồng cleanup; CI nên có bước dọn process/container có kiểm soát nếu môi trường yêu cầu.

## 6. `spring-boot:help` — xem goal, parameter, version chính xác

`help` không cần chạy ứng dụng, không dùng HTTP/JMX port, và không tạo executable JAR. Đây là điểm bắt đầu tốt khi không chắc một tùy chọn được hỗ trợ ở version nào hoặc thuộc goal nào.

~~~bash
# Liệt kê help tổng quan của Spring Boot Maven Plugin
./mvnw spring-boot:help

# Xem toàn bộ tham số của riêng goal run
./mvnw spring-boot:help -Ddetail=true -Dgoal=run

# Xem tham số start và stop riêng biệt
./mvnw spring-boot:help -Ddetail=true -Dgoal=start
./mvnw spring-boot:help -Ddetail=true -Dgoal=stop

# Xem tham số chính goal help
./mvnw spring-boot:help -Ddetail=true -Dgoal=help
~~~

Ý nghĩa:

- `-Ddetail=true` yêu cầu help hiển thị các property và diễn giải đầy đủ hơn.
- `-Dgoal=start` chọn phần tài liệu của goal `start`; đây là **tham số cho plugin help**, không làm ứng dụng khởi động.
- Kiểm tra **version Spring Boot Maven Plugin** in trong output; thông tin của một bản trên mạng có thể khác version project.
- Không nhầm `spring-boot:help` với `help:effective-pom`: goal thứ hai thuộc **Maven Help Plugin**, dùng để xem cấu hình POM thực tế sau inheritance/management.

Nếu Maven báo `No plugin found for prefix 'spring-boot'`, cần kiểm tra plugin được khai báo/phân giải qua POM/repositories. Có thể gọi đầy đủ tọa độ plugin phiên bản đã xác định:

~~~bash
./mvnw org.springframework.boot:spring-boot-maven-plugin:3.3.13:help -Ddetail=true -Dgoal=run
~~~

Cách gọi tọa độ đầy đủ hữu ích để xác định plugin/version mà không phụ thuộc khả năng resolve tiền tố, miễn Maven truy cập được artifact plugin.

## 7. Ví dụ hoàn chỉnh: app Web và vòng đời kiểm thử bằng Maven Failsafe

Ví dụ này minh họa **tất cả bốn goal**, đồng thời tách test ứng dụng thật khỏi kiểm tra bằng tay. Yêu cầu Maven Wrapper hoạt động, JDK 17, các dependency tải được và hai cổng **HTTP 18085 / JMX 19009** chưa được dùng. Nếu dự án đã có chuẩn toolchain/port riêng, dùng các giá trị theo dự án.

Cấu trúc:

~~~text
boot-goals-demo/
  pom.xml
  mvnw                      (Maven Wrapper đã được tạo/lưu)
  mvnw.cmd
  .mvn/wrapper/...
  src/main/java/com/example/goals/BootGoalsApplication.java
  src/test/java/com/example/goals/BootGoalsApplicationIT.java
~~~

### 7.1. POM độc lập

`pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>boot-goals-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <name>boot-goals-demo</name>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
                <configuration>
                    <!-- Cổng JMX của plugin; KHÁC với cổng HTTP -->
                    <jmxPort>19009</jmxPort>
                    <arguments>
                        <argument>--server.port=18085</argument>
                    </arguments>
                </configuration>
                <executions>
                    <execution>
                        <id>pre-integration-test</id>
                        <goals>
                            <goal>start</goal>
                        </goals>
                    </execution>
                    <execution>
                        <id>post-integration-test</id>
                        <goals>
                            <goal>stop</goal>
                        </goals>
                    </execution>
                </executions>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-failsafe-plugin</artifactId>
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

**Giải thích cấu hình:**

- `spring-boot-starter-parent` quản lý version của các dependency/plugin trong ví dụ và cấu hình packaging hỗ trợ executable Spring Boot JAR. Nếu project dùng **parent riêng và import BOM**, cần khai báo plugin versions, cấu hình compiler/Failsafe và `repackage` phù hợp, không giả định BOM import mang theo build defaults.
- Global `<jmxPort>19009</jmxPort>` giúp cả `start` và `stop` dùng cùng cổng JMX. Đổi chỉ một execution sẽ gây không khớp.
- `<arguments><argument>--server.port=18085</argument></arguments>` chỉ cổng **HTTP**, truyền vào app khi `run/start` hoạt động.
- Execution `pre-integration-test` bind `start` vào phase mặc định tương ứng của goal; `post-integration-test` bind `stop` vào phase tương ứng. Có thể khai báo `<phase>` rõ ràng nếu quy ước build của nhóm yêu cầu.
- Failsafe `integration-test` chạy lớp test tích hợp, `verify` đánh giá kết quả sau cleanup. File đặt tên `*IT.java` được Maven Failsafe nhận theo convention mặc định.
- Parent Boot có cấu hình Failsafe `classesDirectory` phù hợp cho bài toán package Spring Boot. Nếu dùng BOM import mà không kế thừa parent, hãy kiểm tra/cấu hình `classesDirectory` là `${project.build.outputDirectory}` theo tài liệu Spring Boot để tránh việc Failsafe lấy nhầm repackaged archive.

**Điểm cần tránh:** không bind `spring-boot:run` vào `pre-integration-test`, vì `run` giữ invocation ở foreground và lifecycle không thể tiếp tục bình thường tới Failsafe. Cặp `start` + `stop` là lựa chọn dành cho vòng đời này.

### 7.2. Main class: endpoint dễ kiểm chứng

File `src/main/java/com/example/goals/BootGoalsApplication.java`:

~~~java
package com.example.goals;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class BootGoalsApplication {
    public static void main(String[] args) {
        SpringApplication.run(BootGoalsApplication.class, args);
    }

    @GetMapping("/ping")
    public String ping() {
        return "pong";
    }
}
~~~

`@SpringBootApplication` bật cấu hình ứng dụng, `@RestController` cho phép method trả nội dung HTTP, `@GetMapping("/ping")` ánh xạ GET. Đây là class Java **hoàn chỉnh trong project Maven đã khai báo Spring Boot dependency**; sẽ không biên dịch độc lập chỉ bằng `javac BootGoalsApplication.java` nếu không có Spring Boot jars trên classpath.

### 7.3. Integration test gọi ứng dụng thật

File `src/test/java/com/example/goals/BootGoalsApplicationIT.java`:

~~~java
package com.example.goals;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class BootGoalsApplicationIT {
    @Test
    void liveHttpEndpointReturnsPong() throws Exception {
        HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(5))
                .build();

        HttpRequest request = HttpRequest.newBuilder(
                        URI.create("http://127.0.0.1:18085/ping"))
                .timeout(Duration.ofSeconds(10))
                .GET()
                .build();

        HttpResponse<String> response = client.send(
                request, HttpResponse.BodyHandlers.ofString());

        assertEquals(200, response.statusCode());
        assertEquals("pong", response.body());
    }
}
~~~

Test dùng Java 17 `HttpClient` gửi request thật đến ứng dụng được `start` khởi động. Nó chứng minh hành vi tại HTTP port **18085**, không phụ thuộc `MockMvc` hay việc load một Spring context thứ hai bên trong test JVM. Failsafe nhận test tên `*IT` và JUnit Platform chạy test nhờ starter-test/phiên bản plugin phù hợp.

**Giới hạn ví dụ:** một cổng cố định có thể đụng các bản build chạy song song. Trong CI chạy parallel, nên cấp mỗi job một cặp cổng riêng hoặc dùng cơ chế reserve network port và truyền cùng cổng cho app/test; không chọn các cổng ngẫu nhiên khác nhau mà không chia sẻ thông tin.

### 7.4. Bốn thao tác chính và kết quả kỳ vọng

**Thử `help` trước, không chạy app:**

~~~bash
./mvnw spring-boot:help -Ddetail=true -Dgoal=start
./mvnw spring-boot:help -Ddetail=true -Dgoal=stop
~~~

Kỳ vọng: xuất hiện tài liệu `jmxPort` (và các parameter riêng của goal), không có HTTP server mới nào khởi động.

**Thử `run` trong foreground:**

~~~bash
./mvnw spring-boot:run
~~~

Kỳ vọng: app Web mở HTTP port **18085** theo cấu hình POM; Maven invocation giữ terminal. Tại terminal khác:

~~~bash
curl -i http://localhost:18085/ping
~~~

Kỳ vọng: HTTP **200**, response body **`pong`**. Sau đó Ctrl+C để dừng `run` và xác nhận port 18085 được giải phóng.

**Thử `start` và `stop` bằng tay:**

~~~bash
# Nếu chưa compile project từ đầu, chuẩn bị output:
./mvnw test-compile

# Goal trả quyền điều khiển sau startup; ứng dụng vẫn đang chạy
./mvnw spring-boot:start
~~~

Khi `start` thành công, ở terminal khác gọi:

~~~bash
curl -i http://localhost:18085/ping
~~~

Sau khi kiểm tra, chạy tại terminal dự án:

~~~bash
./mvnw spring-boot:stop
~~~

Kỳ vọng: process ứng dụng do plugin quản lý được tắt; yêu cầu mới tới HTTP 18085 không còn phản hồi thành công từ instance đó. Không giả định `curl` luôn báo cùng thông điệp lỗi khi app đã dừng vì lỗi TCP/HTTP tùy hệ điều hành.

**Thử cả lifecycle trong một lệnh:**

~~~bash
./mvnw clean verify
~~~

Kỳ vọng theo thứ tự phase: compile, test thông thường (nếu có), package, `start`, Failsafe `integration-test`, `stop`, Failsafe `verify`. Kết luận thành công khi Failsafe báo test thực sự chạy, 0 failures/errors, app được shutdown và Maven kết thúc với exit code 0. Nếu file này là integration test duy nhất, report Failsafe phải thể hiện bài `liveHttpEndpointReturnsPong` đã chạy.

Đường dẫn report thường gặp:

~~~text
target/failsafe-reports/           # kết quả integration test
target/surefire-reports/           # unit test qua Surefire, nếu có
target/boot-goals-demo-0.0.1-SNAPSHOT.jar  # executable artifact ví dụ
~~~

Lưu ý: project ví dụ chỉ có một `*IT.java`; nó không tự tạo unit test `*Test.java`. `mvn test` riêng thường không chạy bài `*IT`, trong khi `mvn verify` có Failsafe execution sẽ chạy. Có thể bổ sung unit test nhưng đừng hiểu report Surefire rỗng là bằng chứng integration test đã chạy.

### 7.5. Thử tình huống lỗi có chủ đích

Trong integration test, đổi `assertEquals("pong", response.body())` thành `assertEquals("pang", response.body())` rồi chạy `./mvnw verify`. Kỳ vọng test **FAIL**, Failsafe ghi report; Maven có cơ hội thực hiện `post-integration-test` và `stop` trước khi `failsafe:verify` báo build fail. Đây là điều người học cần quan sát: khác với goal `run` chặn invocation, cặp `start`/`stop` quản lý cleanup của integration-test lifecycle.

Khôi phục assertion gốc rồi chạy lại `./mvnw clean verify`. Nếu app còn chạy do lỗi bất thường, xác định đúng PID/port trước khi dọn, tránh đóng nhầm JVM khác.

## 8. Chạy với corporate parent hoặc không dùng starter parent

Mục tiêu bài này là **cách dùng goals**, nên mẫu đầy đủ ở trên dùng Boot starter parent cho ngắn gọn. Với dự án giữ parent nội bộ và import `spring-boot-dependencies` BOM:

- BOM quản lý **dependency versions**, không tự cung cấp toàn bộ `pluginManagement`/execution của Boot starter parent.
- Khai báo `spring-boot-maven-plugin` với version khớp dòng Boot, cấu hình các execution `start`/`stop`, và goal `repackage` cho application module nếu cần executable JAR.
- Khai báo `maven-failsafe-plugin` với version hỗ trợ JUnit Platform, execution `integration-test`/`verify` và `classesDirectory` phù hợp.
- Kiểm tra compiler release/`-parameters`, Java version, test classpath và thông số JMX/HTTP khi chuyển dự án.
- Chỉ application module có main class và web/job runtime thích hợp nên tham gia start/stop. Parent aggregator/library module không nên khởi động server chỉ vì có BOM.
- Chạy `./mvnw help:effective-pom` để thấy cấu hình đã áp dụng, rồi dùng `spring-boot:help -Ddetail=true -Dgoal=start` để kiểm tra các tham số mà version plugin đó hỗ trợ.

Các goal không thay thế logic kiểm thử của Maven Failsafe; cần kết quả test và assertions thực để nói một pipeline đạt yêu cầu.

## 9. Các lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân hay gặp | Hành động kiểm chứng |
| --- | --- | --- |
| `spring-boot:run` giữ terminal lâu, tưởng bị treo. | Web server đang chạy ở foreground; đây là thiết kế của `run`. | Dùng terminal khác gọi endpoint, rồi Ctrl+C tại terminal chạy `run`. |
| `-Dserver.port=18085` không đổi cổng app trong `run`. | Option của Maven không tự đi vào JVM fork. | Dùng `-Dspring-boot.run.arguments="--server.port=18085"` hoặc config plugin phù hợp. |
| `spring-boot:start` không trả quyền điều khiển vì startup timeout. | App không sẵn sàng, JVM lỗi, JMX port xung đột hoặc backend dependency không sẵn sàng. | Đọc startup log, HTTP/JMX port, profile, env; sau đó kiểm tra `wait`/`maxAttempts` nếu cần. |
| App HTTP chạy nhưng `stop` không tìm thấy nó. | App khởi động bằng `run`/`java -jar`, hoặc JMX port/name khác. | Xác định cơ chế start thực tế; dùng cùng `jmxPort`/`jmxName` cho cả `start` và `stop`. |
| `curl localhost:19009/ping` thất bại. | 19009 trong ví dụ là JMX, không phải HTTP. | Gọi `http://localhost:18085/ping`. |
| `mvn test` không chạy `BootGoalsApplicationIT`. | Failsafe integration test được gắn vào phase sau `test`, theo convention `*IT`. | Chạy `mvn verify`, đọc `target/failsafe-reports`. |
| `mvn verify` thành công nhưng Failsafe không chạy test. | Test naming/filter hoặc plugin executions không đúng; report có thể rỗng. | Kiểm tra execution `integration-test` + `verify` và report số test thực thi. |
| `mvn verify` báo port đã dùng. | Bản app trước chưa dừng, build song song dùng cùng HTTP/JMX port. | Tìm process sở hữu **đúng cổng**, dừng instance đúng và cấp port riêng. |
| `spring-boot:help` báo không tìm thấy plugin prefix. | POM/plugin repositories/prefix resolution chưa đúng. | Xem POM, gọi tọa độ đầy đủ của đúng plugin version, kiểm tra Maven settings. |
| `stop` xảy ra trước khi có integration test. | Gắn execution vào phase sai hoặc thiếu Failsafe binding. | Xem `help:effective-pom` và log phase thực tế; `start` ở pre-integration-test, `stop` ở post-integration-test. |
| Test fail và app còn chạy. | Build ngắt bất thường, plugin start/stop thất bại hoặc runner bị kill. | Đọc log, report, xác định đúng PID/JMX port, cleanup theo chính sách CI. |
| `run` pass nhưng executable JAR không chạy. | `run` dùng classes/classpath build; package/plugin `repackage` thiếu hoặc artifact sai. | Chạy `package`, xem archive/manifest, thử `java -jar` thật. |

**Phương pháp chẩn đoán:** trước tiên xác định **đúng goal nào đang được gọi và phase nào đang chạy**. Tiếp theo xem process JVM có tồn tại, cổng HTTP/JMX có đúng, log startup nói gì, Failsafe đã chạy bao nhiêu test và Maven có trả exit code 0 hay không. Đừng “chữa” lỗi bằng cách bỏ qua integration test hoặc tắt `stop`.

## 10. Checklist tự đánh giá

Sau bài này, bạn có thể kiểm chứng các phát biểu dưới đây bằng lệnh và log:

- [ ] `run` khởi động app và giữ Maven invocation chờ ứng dụng, dù app thực thi trong JVM fork.
- [ ] `start` khởi động app, chờ readiness theo plugin rồi trả quyền điều khiển cho Maven để test tiếp tục.
- [ ] `stop` chỉ quản lý app mà `start` đã khởi động; `run` thường dừng bằng Ctrl+C ở terminal.
- [ ] `help` không khởi động app, có `-Ddetail=true` và `-Dgoal=...` để tra tham số.
- [ ] Phân biệt `server.port` (HTTP) và `jmxPort` (Maven plugin/JMX); hai cổng phải được cấu hình đúng cho từng mục đích.
- [ ] Phân biệt application argument, JVM argument và Maven user property khi app chạy trong JVM fork.
- [ ] Nối `start`/`stop` với `pre-integration-test`/`post-integration-test` và dùng Failsafe `integration-test`/`verify`.
- [ ] Xác nhận report Failsafe có test thật chạy; không coi `mvn test` là integration test ở ví dụ này.
- [ ] Chạy `mvn verify` và đọc được lỗi test, startup, JMX hoặc cleanup theo đúng nguồn gốc.
- [ ] Không coi `spring-boot:run` tương đương phép kiểm thử executable JAR đã đóng gói.
- [ ] Trong multi-module reactor, chỉ gọi start/stop ở module ứng dụng phù hợp, tránh khởi động nhầm module thư viện.
- [ ] Nếu CI build song song, có cách cấp cổng và dọn process an toàn, không kill tất cả JVM.

**Bài tập kết thúc:** điền bảng gồm bốn dòng `run`, `start`, `stop`, `help` với (1) lệnh thật đã gọi, (2) terminal/process/JMX/HTTP biểu hiện ra sao, (3) bằng chứng pass/fail, (4) khi nào nên/không nên dùng. Nộp thêm report `BootGoalsApplicationIT` chạy qua Failsafe, log `start` và `stop`, output `spring-boot:help -Ddetail=true -Dgoal=start`, kết quả `GET /ping`, và giải thích tại sao app có thể chạy qua `run` nhưng package vẫn có thể lỗi.

## Tài liệu tham khảo chính thức

- [Spring Boot 3.3 Maven Plugin — Running your Application with Maven](https://docs.spring.io/spring-boot/3.3/maven-plugin/run.html)
- [Spring Boot 3.3 Maven Plugin — Running Integration Tests](https://docs.spring.io/spring-boot/3.3/maven-plugin/integration-tests.html)
- [Spring Boot 3.3 Maven Plugin — Help Information](https://docs.spring.io/spring-boot/3.3/maven-plugin/help.html)
- [Spring Boot 3.3 Maven Plugin — Goals](https://docs.spring.io/spring-boot/3.3/maven-plugin/goals.html)
- [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Apache Maven Failsafe Plugin — Introduction](https://maven.apache.org/surefire/maven-failsafe-plugin/)

Những lệnh trong bài là hướng dẫn thực hành với project minh họa. **Kết quả thực tế** phải được kiểm chứng bằng lệnh và report ở môi trường chạy; chỉ khi hiểu từng goal mới lựa chọn cách chạy ứng dụng nhất quán cho phát triển, kiểm thử và đóng gói.