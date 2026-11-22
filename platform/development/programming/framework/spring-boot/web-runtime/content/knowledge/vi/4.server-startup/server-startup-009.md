# Phân biệt `server.port=0`, `server.port=-1` và ứng dụng không có web server trong Spring Boot

## 1. Bản chất của bài toán: cấu hình **cổng** khác với cấu hình **loại ứng dụng**

Khi ứng dụng Spring Boot khởi động, cần trả lời **hai câu hỏi độc lập**:

1. **Spring Boot tạo loại `ApplicationContext` nào?** Đây là quyết định của `WebApplicationType`: `SERVLET`, `REACTIVE` hay `NONE`. Nếu là ứng dụng web, Spring Boot chuẩn bị hạ tầng xử lý request tương ứng với Spring MVC hoặc WebFlux.
2. **Ứng dụng web có nhận HTTP qua một cổng mạng hay không?** Đây là phần liên quan đến `server.port`. Giá trị `0` yêu cầu hệ điều hành cấp một cổng thực tế; giá trị `-1` vô hiệu hóa các HTTP endpoint của web server chính, nhưng vẫn giữ web application context.

Do đó, **`server.port=-1` không đồng nghĩa với `WebApplicationType.NONE`**. Cả hai đều không cung cấp HTTP endpoint trên cổng chính, nhưng tạo context và nạp hạ tầng khác nhau. Ngược lại, `server.port=0` hoàn toàn **không có nghĩa là tắt cổng**.

Phạm vi: ứng dụng Spring Boot 3.x chạy độc lập với embedded web server (Tomcat cho `spring-boot-starter-web` theo cấu hình mặc định, hoặc runtime reactive tương ứng). Với ứng dụng WAR chạy trong servlet container bên ngoài, cổng lắng nghe được container ngoài quyết định; không áp dụng máy móc quy tắc `server.port` của embedded server.

## 2. So sánh trực tiếp ba chế độ

| Cấu hình | Loại context điển hình khi có `spring-boot-starter-web` | HTTP listener của ứng dụng chính | Có thể gọi `GET /ping` qua mạng? | Mục đích thường gặp |
| --- | --- | --- | --- | --- |
| `server.port=0` | `ServletWebServerApplicationContext` (web) | **Có**, cổng thực tế do OS chọn, > 0 | **Có**, nếu biết cổng đã cấp | Integration test với HTTP thật; chạy nhiều instance không xung đột cổng |
| `server.port=-1` | Vẫn là web application context | **Không** mở cổng HTTP chính để phục vụ endpoint | **Không** qua cổng chính | Khởi tạo web context/bean phục vụ kiểm thử hay tác vụ đặc biệt mà không công bố HTTP |
| `spring.main.web-application-type=none` | `AnnotationConfigApplicationContext` (non-web) | **Không** tạo web server cho ứng dụng này | **Không** | CLI, batch job, migration, worker, ứng dụng xử lý nền |

Bảng giả định **chỉ cấu hình một HTTP server chính**. Nếu bật Actuator trên **một cổng management riêng**, hoặc ứng dụng tự mở socket/server khác, cần kiểm tra listener đó độc lập; `server.port=-1` không phải quy tắc bảo đảm toàn bộ tiến trình không còn bất kỳ cổng mạng nào.

Để đối chiếu, khi dùng web starter với cấu hình mặc định, ứng dụng standalone thường lắng nghe HTTP ở **8080**. `server.port=8081` là cổng cố định; `0` và `-1` là hai giá trị mang ý nghĩa đặc biệt.

## 3. Trường hợp A — `server.port=0`: có web server, nhưng cổng được chọn lúc chạy

### Cơ chế

~~~properties
# src/main/resources/application.properties
server.port=0
~~~

Spring Boot tạo **web application context** và khởi động embedded server. Thay vì buộc listener vào cổng 8080, ứng dụng yêu cầu hệ điều hành chọn một cổng TCP còn trống. Ví dụ một lần chạy có thể được cấp cổng `49176`, lần khác `50231`; **các số này chỉ minh họa**, không phải giá trị mặc định hay cam kết cố định.

Luồng khởi động:

~~~text
SpringApplication.run(...)
        |
        v
Chọn WebApplicationType.SERVLET/REACTIVE
        |
        v
Tạo web ApplicationContext và khởi tạo embedded server
        |
        v
server.port = 0 --> OS cấp cổng thực tế, ví dụ 49176
        |
        v
WebServerInitializedEvent --> biết cổng đã gắn
        |
        v
Client gọi http://localhost:49176/...
~~~

**Không truy cập `http://localhost:0`.** Số `0` là yêu cầu cấp cổng động lúc server **bind**, không phải cổng để client kết nối. Cổng thực tế phải lấy **sau** khi server khởi tạo, thông qua log, `WebServerApplicationContext.getWebServer().getPort()`, hoặc `WebServerInitializedEvent`.

Trong mã ứng dụng, ưu tiên bắt sự kiện khởi tạo server. Không dựa vào `@Value` của thuộc tính `local.server.port` trong bean được tạo quá sớm: thuộc tính cổng thực tế chỉ được thiết lập sau khi server khởi tạo. Trong **integration test** với `RANDOM_PORT` có thể dùng `@LocalServerPort`.

### Khi nào nên dùng?

- Test integration cần HTTP thật mà không tranh cổng 8080 với ứng dụng khác.
- Nhiều instance local/container trên cùng host, mỗi instance tự chọn cổng.
- Công cụ local/embedded service có cơ chế đăng ký hoặc truyền lại cổng thực tế cho client.

### Điểm cần lưu ý

- Cổng thay đổi giữa các lần chạy; không hard-code vào client, tài liệu hoặc automation.
- Cổng được chọn tự động vẫn **có HTTP endpoint hoạt động**; nếu không giới hạn interface, có thể nhận kết nối trên các địa chỉ tương ứng với `server.address` và cấu hình mạng. Đừng mặc định cổng động là một cơ chế bảo mật.
- `server.port=0` giảm rủi ro **đụng cổng trong lúc bind** nhờ OS, nhưng các tài nguyên khác (database, file, remote service) vẫn có thể gây xung đột.
- Với `spring.main.web-application-type=none`, `server.port=0` không thể tự bật web server vì ứng dụng đã chọn loại context không-web.

## 4. Trường hợp B — `server.port=-1`: giữ web context, tắt HTTP endpoint chính

~~~properties
# src/main/resources/application.properties
server.port=-1
~~~

Spring Boot có thể vẫn chọn loại web application `SERVLET` hoặc `REACTIVE` dựa trên classpath/cấu hình và **vẫn tạo một `WebApplicationContext`**. Tuy nhiên, theo hợp đồng cấu hình của Spring Boot, `server.port=-1` **vô hiệu hóa các HTTP endpoint chính**: client không thể dùng một cổng HTTP chính để gọi controller. Đây là chế độ được tài liệu Spring Boot nhắc đến như một lựa chọn cho một số trường hợp test.

Điểm phân biệt quan trọng:

- `@RestController`, `@GetMapping` và các bean hỗ trợ web có thể vẫn được quét/khởi tạo tùy cấu hình, bởi ứng dụng vẫn là **web application context**; điều đó **không đồng nghĩa** controller có URL HTTP công khai.
- `server.port=-1` là một lựa chọn cấu hình **đường nhận HTTP của web server chính**. Không nên mô tả nó là "không tạo web server" hay "không có web context".
- Không có cổng HTTP chính được gắn nên không có "cổng thật" để truy vấn như ở `server.port=0`. Đừng dùng giá trị `-1` làm URL để gửi request.
- Đừng suy luận từ việc không gọi HTTP được rằng mọi bean, scheduler, database connection hoặc background task đều ngừng hoạt động.
- Việc toàn bộ tiến trình Java có tự kết thúc sau startup hay không phụ thuộc các thread và thành phần khác đang chạy; **không dùng riêng `-1` để điều khiển vòng đời batch job**.

Trường hợp phù hợp: cần các bean và hạ tầng của web application context để kiểm thử cấu hình, nhưng không muốn ứng dụng chính mở cổng HTTP. Nếu mục tiêu là **chỉ chạy tác vụ không có hạ tầng web**, dùng `WebApplicationType.NONE` sẽ chính xác hơn.

**Lưu ý về Actuator:** nếu cài `spring-boot-starter-actuator` và cấu hình `management.server.port` khác cổng chính, management HTTP có cấu hình lắng nghe riêng. Muốn vô hiệu hóa HTTP management cần xử lý độc lập, ví dụ `management.server.port=-1` hoặc vô hiệu hóa web exposure phù hợp. Đừng tuyên bố "không còn bất kỳ HTTP listener nào" chỉ dựa vào `server.port=-1`.

## 5. Trường hợp C — ứng dụng **không có web server**: `WebApplicationType.NONE`

~~~properties
# src/main/resources/application.properties
spring.main.web-application-type=none
~~~

Đây là chỉ dẫn cho `SpringApplication` **không tạo web application context**. Context điển hình là `AnnotationConfigApplicationContext`, không phải `ServletWebServerApplicationContext` hay `ReactiveWebServerApplicationContext`. Spring vẫn có dependency injection, cấu hình, bean, `ApplicationRunner` / `CommandLineRunner` và các dịch vụ khác, nhưng không khởi động embedded HTTP web server. Khai báo `@RestController` không tự biến ứng dụng thành HTTP server khi chế độ `none` đã được chọn.

Có thể cấu hình bằng Java **trước khi gọi `run`**:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;

public class Main {
    public static void main(String[] args) {
        SpringApplication app = new SpringApplication(Main.class);
        app.setWebApplicationType(WebApplicationType.NONE);
        app.run(args);
    }
}
~~~

Đoạn này minh họa API thiết lập kiểu ứng dụng, **không phải chương trình độc lập hoàn chỉnh**: để chạy thực tế, `Main` cần cấu hình bean thích hợp (thường là `@SpringBootApplication`), dependency Spring Boot và cấu trúc dự án. Có thể dùng cấu hình `spring.main.web-application-type=none` thay cho lập trình trực tiếp.

### Không có web starter có phải luôn là `NONE`?

Khi không chỉ định rõ `spring.main.web-application-type`, Spring Boot **tự phát hiện** loại ứng dụng dựa trên classpath:

- Nếu có Spring MVC, mặc định chọn **`SERVLET`**.
- Nếu không có MVC mà có Spring WebFlux, thường chọn **`REACTIVE`**.
- Nếu không có dấu hiệu web stack tương ứng, chọn **`NONE`**.
- Nếu cả MVC và WebFlux cùng có, MVC thường được ưu tiên. Muốn buộc WebFlux dùng `spring.main.web-application-type=reactive` nếu kiến trúc ứng dụng phù hợp.

Vì vậy, có **hai cách thường gặp** để có ứng dụng non-web: (1) dùng các starter không-web để Boot tự phát hiện `NONE`; (2) giữ dependency web nhưng **chủ động** đặt `spring.main.web-application-type=none`. Cách (2) vẫn mang thư viện web trên classpath nhưng **không** thiết lập web context/HTTP server.

### Vòng đời non-web

Ứng dụng có thể thực hiện công việc trong `ApplicationRunner`/`CommandLineRunner`, rồi **tự thoát** nếu không còn thread non-daemon hoặc tiến trình đang giữ JVM sống. Nếu cấu hình `@Scheduled`, message listener, thread chạy nền hoặc tác vụ lâu dài, ứng dụng non-web vẫn có thể tiếp tục chạy. **Không có web server không đồng nghĩa ứng dụng bắt buộc thoát ngay.**

Khi có cả `spring.main.web-application-type=none` và `server.port=0` (hoặc `-1`), lựa chọn `NONE` quyết định không tạo web server; giá trị `server.port` không tạo ra listener hay web context.

## 6. Ví dụ Java 17+ chạy được: cùng một chương trình, ba cách khởi động

Ví dụ dùng **Spring Boot 3.x + Java 17+**, dependency runtime `spring-boot-starter-web`. Nếu dùng Gradle, dự án phải có Spring Boot Gradle plugin và `bootRun` đã cấu hình. Mã Java đầy đủ dưới đây đặt trong đúng tệp:

`src/main/java/demo/ports/PortModesApplication.java`

~~~java
package demo.ports;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.web.context.WebServerApplicationContext;
import org.springframework.boot.web.context.WebServerInitializedEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class PortModesApplication {
    public static void main(String[] args) {
        SpringApplication.run(PortModesApplication.class, args);
    }

    @Bean
    ApplicationRunner describeContext(ConfigurableApplicationContext context) {
        return args -> System.out.println(
                "WEB_CONTEXT=" + (context instanceof WebServerApplicationContext));
    }

    @Bean
    ApplicationListener<WebServerInitializedEvent> reportHttpPort() {
        return event -> {
            int actualPort = event.getWebServer().getPort();
            if (actualPort > 0) {
                System.out.println("BOUND_HTTP_PORT=" + actualPort);
            }
        };
    }
}

@RestController
class PingController {
    @GetMapping("/ping")
    String ping() {
        return "pong";
    }
}
~~~

Trong mã:

1. `@SpringBootApplication` khởi tạo ứng dụng. Vì dependency web có mặt, mặc định Boot nhận diện một **web application** nếu không cấu hình `none`.
2. `ApplicationRunner` in `WEB_CONTEXT=true` nếu context thuộc nhóm `WebServerApplicationContext`, ngược lại in `false`. Nó chạy sau quá trình refresh context.
3. `ApplicationListener<WebServerInitializedEvent>` nhận sự kiện khi web server đã khởi tạo; với cổng thực sự lớn hơn 0, in `BOUND_HTTP_PORT=<số_cổng>`. Điều kiện này tránh thông báo nhầm rằng có HTTP listener khi không có cổng dương. Nếu có server management riêng, sự kiện có thể được phát nhiều lần và cần lọc theo context/namespace ở ứng dụng thực tế.
4. `PingController` ánh xạ GET `/ping` thành văn bản `pong` **chỉ khi có HTTP endpoint hoạt động**. Sự hiện diện của controller bean không làm `-1` hoặc `NONE` nhận request.
5. Ví dụ không yêu cầu database hay Actuator; ba trường hợp nên được chạy **tách biệt**, mỗi lần dừng tiến trình cũ trước khi khởi động chế độ khác.

### 6.1 Chạy với cổng động (`server.port=0`)

Trên bash/macOS/Linux:

~~~bash
./gradlew bootRun --args='--server.port=0'
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun --args="--server.port=0"
~~~

Giả sử ứng dụng in (chỉ trích dòng do mã ví dụ phát ra):

~~~text
BOUND_HTTP_PORT=49176
WEB_CONTEXT=true
~~~

Cổng `49176` là **ví dụ**; hãy dùng cổng thực tế từ dòng `BOUND_HTTP_PORT`, chẳng hạn với đúng lần chạy minh họa:

~~~bash
curl -i http://localhost:49176/ping
~~~

Kỳ vọng HTTP status **200 OK** và body `pong` (kèm các header do embedded server tạo). Truy cập `localhost:8080` chỉ hợp lệ nếu có dịch vụ khác tình cờ lắng nghe ở đó; nó **không** phải cổng của lần chạy `server.port=0` này.

### 6.2 Chạy với HTTP chính tắt (`server.port=-1`)

~~~bash
./gradlew bootRun --args='--server.port=-1'
~~~

Đối với ví dụ đơn giản, có thể quan sát:

~~~text
WEB_CONTEXT=true
~~~

Không có cổng HTTP chính dương được in bởi listener, và không thể gọi `/ping` qua listener HTTP chính. **Không thử `curl http://localhost:-1/ping`**; `-1` chỉ là giá trị cấu hình Spring Boot, không phải cổng TCP hợp lệ. Việc `WEB_CONTEXT=true` là bằng chứng dễ thấy nhất để phân biệt trường hợp này với non-web.

### 6.3 Chạy với ứng dụng non-web (`none`)

~~~bash
./gradlew bootRun --args='--spring.main.web-application-type=none'
~~~

Mã ví dụ dự kiến in:

~~~text
WEB_CONTEXT=false
~~~

Không có sự kiện web server để in cổng và không có HTTP endpoint `/ping`. Vì ví dụ không có tác vụ nền dài hạn, JVM có thể kết thúc sau startup; đây là hành vi vòng đời, **không** phải lỗi bind port. Chương trình vẫn chạy `ApplicationRunner` để in kết quả.

### 6.4 Cấu hình tương đương

Mỗi cách sau chỉ nên dùng trong một lần chạy riêng:

~~~properties
# application.properties: kiểu A
server.port=0
~~~

~~~properties
# application.properties: kiểu B
server.port=-1
~~~

~~~properties
# application.properties: kiểu C
spring.main.web-application-type=none
~~~

Tương đương bằng YAML (chọn **một** cấu hình khi chạy):

~~~yaml
server:
  port: 0
~~~

~~~yaml
server:
  port: -1
~~~

~~~yaml
spring:
  main:
    web-application-type: none
~~~

Có thể cấu hình cổng bằng biến môi trường `SERVER_PORT` nhờ cơ chế relaxed binding, ví dụ `SERVER_PORT=0`. Nếu giá trị từ command line, biến môi trường, profile và file cấu hình không giống nhau, kiểm tra **độ ưu tiên của nguồn cấu hình** để biết giá trị thực tế; không giả định file `application.properties` luôn thắng.

## 7. Kiểm thử: tránh nhầm `@SpringBootTest` với cấu hình production

Spring Boot cung cấp `@SpringBootTest(webEnvironment = ...)` để định nghĩa môi trường test; lựa chọn này **khác phạm vi** với thay đổi `server.port` trong ứng dụng thường chạy.

| `WebEnvironment` | Context trong test | HTTP listener thật? | Ý nghĩa |
| --- | --- | --- | --- |
| `MOCK` (mặc định) | Web context mô phỏng nếu có web stack; nếu không có thì non-web | **Không** | Kiểm thử web layer với `MockMvc` hay công cụ tương đương |
| `RANDOM_PORT` | Web context với embedded server | **Có**, port động | Kiểm thử HTTP end-to-end ở tầng web server |
| `DEFINED_PORT` | Web context với embedded server và port theo cấu hình, mặc định 8080 | **Có**, trừ khi bạn cấu hình vô hiệu hóa cổng HTTP chính, chẳng hạn `server.port=-1` | Test gọi HTTP trên port định trước |
| `NONE` | Context non-web | **Không** | Kiểm thử bean/logic không cần web |

**Bẫy quan trọng:** `@SpringBootTest` mặc định **không** mở cổng HTTP, nhưng khi có MVC nó dùng **mock web environment**; vì vậy không được coi kết quả test mặc định là bằng chứng ứng dụng production có `WebApplicationType.NONE`. Và `MockMvc` có thể gọi controller **trong bộ nhớ** mà không cần TCP listener.

### Ví dụ kiểm thử tích hợp cổng động

Với dependency test `spring-boot-starter-test`, tệp `src/test/java/demo/ports/RandomPortTest.java`:

~~~java
package demo.ports;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.boot.test.web.server.LocalServerPort;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class RandomPortTest {
    @LocalServerPort
    int port;

    @Autowired
    TestRestTemplate restTemplate;

    @Test
    void servesHttpOnAssignedPort() {
        assertThat(port).isGreaterThan(0);
        assertThat(restTemplate.getForObject("/ping", String.class))
                .isEqualTo("pong");
    }
}
~~~

Test dùng `RANDOM_PORT` để **mở server thật**, lấy cổng đã bind bằng `@LocalServerPort` và xác nhận body endpoint. Với `TestRestTemplate` được Spring Boot test tự cấu hình trong môi trường phù hợp, có thể gọi path tương đối `/ping`. Lệnh Gradle (khi dự án đã cấu hình test JUnit 5):

~~~bash
./gradlew test --tests demo.ports.RandomPortTest
~~~

Không copy ví dụ `@LocalServerPort` vào bean tạo lúc startup thông thường: annotation này dành cho ngữ cảnh test đã khởi tạo cổng thật. Khi muốn chắc chắn **không có môi trường web trong test**, sử dụng `@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.NONE)`. Khi muốn **web context mà không nghe HTTP**, cân nhắc test với `server.port=-1` nếu phù hợp phạm vi, hoặc mock web test nếu chỉ cần controller mapping.

## 8. Phương pháp chẩn đoán khi khởi động không như mong đợi

### Tình huống 1: Đặt `server.port=0` nhưng không biết địa chỉ để gọi

**Nguyên nhân:** đang nhầm giá trị cấu hình `0` với cổng thực tế. **Cách kiểm tra:** xem log server, dùng `WebServerInitializedEvent` hoặc `WebServerApplicationContext.getWebServer().getPort()` **sau** khi khởi tạo. Trong test, dùng `@LocalServerPort` với `RANDOM_PORT`. Xác nhận listener bằng công cụ mạng và đúng port mới in, đừng gọi 0.

### Tình huống 2: Đặt `server.port=-1`, thấy web context vẫn được khởi tạo

**Đây là hành vi chủ định.** `-1` không loại bỏ web infrastructure. Nếu đang tạo batch/CLI và muốn tránh web auto-configuration/context, dùng `spring.main.web-application-type=none`. Nếu yêu cầu của test là giữ web bean nhưng không lắng nghe HTTP, `-1` có thể phù hợp.

### Tình huống 3: Đặt `server.port=8080` hoặc `0` nhưng vẫn không có HTTP server

Kiểm tra có đặt `spring.main.web-application-type=none` (kể cả qua command line/profile/biến môi trường) hay không. `server.port` không thể tự thay đổi `WebApplicationType.NONE` thành `SERVLET`. Ngoài ra, thiếu dependency web hoặc cấu hình application context đặc biệt cũng dẫn đến không có embedded web server.

### Tình huống 4: Không gọi được endpoint dù khởi động có thông báo thành công

Tách các nguyên nhân:

1. **Không có listener:** `-1` hoặc `NONE`; không có cổng chính để gọi.
2. **Gọi nhầm port:** `0` đã chọn cổng động khác; 8080 chưa chắc đúng.
3. **Bind địa chỉ khác:** xem `server.address`, mạng container và port mapping; việc server bind thành công không bảo đảm route từ mọi máy client.
4. **Sai endpoint:** path/method không khớp, response có thể là 404/405.
5. **Bảo mật hoặc actuator:** security filter, management port và endpoint exposure có thể tạo kết quả khác; đây là lớp cấu hình riêng, không thay thế ba chế độ trên.

### Tình huống 5: Ứng dụng "không có web server" vẫn chạy mãi

`NONE` chỉ điều khiển hạ tầng web. Scheduler, listener message, thread nền hoặc tác vụ dài hạn có thể giữ JVM sống. Ngược lại, `server.port=-1` vẫn có thể có các bean web; đừng dùng nó như công tắc đảm bảo kết thúc process.

## 9. Lỗi tư duy thường gặp

- **"`server.port=0` nghĩa là tắt HTTP."** Sai: `0` yêu cầu OS cấp **một cổng HTTP thực tế**. Muốn tắt endpoint chính: `-1`; muốn tắt hẳn web server: `NONE`.
- **"`server.port=-1` tương đương `spring.main.web-application-type=none`."** Sai: `-1` giữ web context; `NONE` tạo non-web context.
- **"Không có web listener tức là không có Spring application."** Sai: bean, DI, runner, scheduler và logic nghiệp vụ vẫn có thể hoạt động.
- **"`@SpringBootTest` mặc định đã chạy HTTP server."** Sai: default `MOCK` không dùng TCP listener thật.
- **"Cổng thực tế phải bằng giá trị property `server.port`."** Sai với `0`: property là yêu cầu cấp cổng; địa chỉ thật biết sau khi bind.
- **"Nếu cổng chính bị vô hiệu thì chắc chắn không có listener mạng nào."** Sai nếu Actuator management dùng port riêng hoặc chương trình tự mở socket khác.
- **"Thêm `server.port` sẽ ép một ứng dụng `NONE` trở thành web app."** Sai: cần context web và web runtime thích hợp.

## 10. Chọn chế độ bằng yêu cầu thực tế

~~~text
Có cần ứng dụng phục vụ HTTP thật không?
  |
  +-- Có --> Có cần cổng cố định?
  |             |
  |             +-- Có  --> server.port=8080 (hoặc cổng định trước)
  |             |
  |             +-- Không --> server.port=0
  |                          Đọc cổng thực tế sau khi server bind
  |
  +-- Không --> Có cần giữ web ApplicationContext?
                  |
                  +-- Có  --> server.port=-1
                  |          Giữ web context, tắt HTTP chính
                  |
                  +-- Không --> spring.main.web-application-type=none
                               Chạy ứng dụng non-web
~~~

Một ví dụ quyết định: (a) service HTTP trong integration test song song → `server.port=0`; (b) kiểm tra bean/config của web app nhưng không muốn expose endpoint → `server.port=-1` hoặc test web dạng mock tùy mục tiêu; (c) chạy job nhập dữ liệu mỗi đêm không cần MVC/WebFlux → `spring.main.web-application-type=none`.

### Câu hỏi tự kiểm tra

1. **Nếu `WEB_CONTEXT=true` và `BOUND_HTTP_PORT=51324`, chế độ nào phù hợp?** → `server.port=0` hoặc port cố định 51324; nhìn thêm cấu hình để phân biệt. Chắc chắn có một HTTP listener đã nhận cổng 51324.
2. **Nếu `WEB_CONTEXT=true` nhưng không gọi được controller qua mạng, có kết luận ứng dụng `NONE` không?** → Không. Có thể là `server.port=-1` hoặc vấn đề mạng/bảo mật; kiểm tra property và listener.
3. **Nếu có `spring-boot-starter-web` nhưng cấu hình `spring.main.web-application-type=none` thì controller có được phục vụ không?** → Không. Thư viện có mặt không vượt qua lựa chọn `NONE`.
4. **Nếu chỉ muốn test controller qua `MockMvc`, có cần `RANDOM_PORT` không?** → Không. Web mock test thường không cần server TCP; `RANDOM_PORT` dành cho kiểm tra luồng HTTP thật.
5. **Hai test độc lập dùng `server.port=0` có thể cùng chạy không?** → Thường có: OS cấp cổng còn trống cho mỗi lần bind, tránh xung đột cổng chính. Nhưng không bảo đảm các tài nguyên chung khác cũng độc lập.

## 11. Tài liệu tham khảo chính thức

- [Spring Boot 3.3 — Embedded Web Servers](https://docs.spring.io/spring-boot/3.3/how-to/webserver.html): hướng dẫn `server.port=0`, `server.port=-1`, cách vô hiệu hóa web server và truy xuất cổng runtime.
- [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): khác biệt `MOCK`, `RANDOM_PORT`, `DEFINED_PORT` và `NONE`.
- [Spring Boot 3.4 — SpringApplication / Web Environment](https://docs.spring.io/spring-boot/3.4/reference/features/spring-application.html): cơ chế lựa chọn `WebApplicationType` và override bằng `setWebApplicationType`.
- [Spring Boot — Monitoring and Management over HTTP](https://docs.spring.io/spring-boot/reference/actuator/monitoring.html): management port và cách điều khiển HTTP Actuator riêng.

**Điểm cần nhớ:** `0` = **có HTTP trên cổng OS cấp**; `-1` = **web context vẫn có nhưng HTTP endpoint chính bị tắt**; `NONE` = **không tạo web application context và không khởi động web server**.
