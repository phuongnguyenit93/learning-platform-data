# Kiến thức đầu vào và trình tự học từ khởi động đến vận hành ứng dụng

Bài học này cung cấp bản đồ học tập cho **Spring Boot web runtime**: từ nền tảng cần có, tạo và khởi động tiến trình Java, đi theo một HTTP request, đến kiểm thử, triển khai, quan sát và xử lý sự cố. Mục tiêu là hiểu **vì sao ứng dụng chạy được và làm sao biết nó đang phục vụ đúng**, thay vì chỉ chạy được lệnh khởi động.

## 1. Sau bài này cần làm được gì?

1. Nêu được những kiến thức Java, HTTP và Spring tối thiểu để theo dõi web runtime.
2. Giải thích được vai trò của JVM, **SpringApplication**, **ApplicationContext**, bean, auto-configuration và máy chủ HTTP nhúng.
3. Mô tả đường đi của request/response trong ứng dụng Spring MVC; biết WebFlux khác ở điểm nào.
4. Tự chạy ứng dụng nhỏ, gọi endpoint, đọc lỗi cấu hình/khởi động và kiểm thử luồng HTTP.
5. Nhận diện các tín hiệu cần theo dõi khi vận hành: health, readiness/liveness, log, metric, graceful shutdown và cấu hình môi trường.
6. Học các chủ đề theo đúng thứ tự phụ thuộc, với bằng chứng đầu ra kiểm tra được ở từng chặng.

**Giới hạn phạm vi:** tập trung vào vòng đời và năng lực vận hành của một ứng dụng web Spring Boot. Cơ chế xác thực/ủy quyền, tối ưu cơ sở dữ liệu, triển khai đám mây chuyên sâu và thiết kế hệ phân tán là các nhánh học tiếp sau khi hiểu runtime căn bản.

## 2. Kiến thức đầu vào

### 2.1. Java và JVM

- **Java 17 trở lên:** lớp, phương thức, interface, record, generic, collection, exception; biết cách đọc stack trace để tìm lỗi gốc.
- **Biên dịch và chạy:** phân biệt mã nguồn .java, bytecode .class, JAR và JVM; hiểu classpath, dependency và phiên bản JDK chạy chương trình.
- **Thread và tài nguyên:** biết thread xử lý công việc, blocking I/O, timeout, heap/GC ở mức khái niệm. Chưa cần tối ưu sâu nhưng phải nhận ra rằng một request chiếm tài nguyên runtime.
- **Annotation và reflection:** hiểu annotation cung cấp metadata để framework phát hiện cấu hình, web mapping và injection; annotation tự nó không thực thi logic nghiệp vụ.

Nếu chưa biết cú pháp record, có thể hiểu đơn giản **record** là cách ngắn gọn khai báo kiểu dữ liệu bất biến cho payload; ví dụ ở phần thực hành dùng một record làm JSON response.

### 2.2. HTTP, JSON và mạng cơ bản

- **Client/server:** trình duyệt hoặc công cụ curl gửi request đến địa chỉ host và port mà server lắng nghe; DNS, TCP, TLS/HTTPS và reverse proxy là các lớp liên quan khi triển khai thật.
- **Request:** method (GET, POST, PUT, PATCH, DELETE), path, query, header, body và Content-Type; **response:** status, header và body.
- **Status:** 2xx thành công; 400 thường là request không hợp lệ; 401 chưa xác thực; 403 không đủ quyền; 404 không tìm thấy route/tài nguyên; 5xx là lỗi phía server.
- **JSON:** object, array, chuỗi, số, boolean, null; hiểu ánh xạ giữa JSON và DTO Java. Đọc được log HTTP và dùng curl hoặc HTTP client để tái hiện lỗi.
- **Tính không trạng thái:** một request có thể được phục vụ bởi nhiều instance khác nhau; không nên dựa vào biến của controller để giữ dữ liệu riêng từng người dùng.

Ví dụ, **GET /api/ping** yêu cầu kiểm tra một đường dẫn; server trả **200 OK** cùng JSON khi xử lý thành công. Một endpoint 200 không chứng minh toàn bộ hệ thống nghiệp vụ đã sẵn sàng.

### 2.3. Spring Framework ở mức cần thiết

- **IoC/Dependency Injection:** Spring tạo, quản lý và nối các bean; ưu tiên constructor injection để biểu lộ dependency và giúp viết test.
- **ApplicationContext:** nơi lưu bean và quản lý cấu hình, sự kiện, vòng đời; không đồng nhất nó với servlet container hay JVM.
- **Component scanning:** các thành phần thường nằm trong package của lớp ứng dụng chính và các package con; vị trí package ảnh hưởng khả năng phát hiện controller/service.
- **Cấu hình có điều kiện:** starter cung cấp dependency; auto-configuration có thể tạo bean dựa trên classpath, property và bean sẵn có. Thêm starter không đồng nghĩa mọi tính năng đều bật vô điều kiện.
- **Web mapping:** annotation như @RestController, @GetMapping, @RequestBody dùng để nối URL, dữ liệu HTTP và phương thức Java.

### 2.4. Công cụ thực hành

Có JDK 17+ cùng Gradle wrapper hoặc Maven wrapper trong project, IDE, terminal, curl (hoặc công cụ HTTP tương đương), Git và khả năng xem biến môi trường/log. Biết chạy **java -version** và **./gradlew --version** (trên Windows dùng **gradlew.bat --version**) để kiểm tra môi trường. Không cần cài Tomcat riêng nếu dự án đã sử dụng embedded server qua starter thích hợp.

## 3. Bản đồ runtime: từ main() tới HTTP response

### 3.1. Luồng khởi động

~~~text
Lệnh chạy / java -jar
       |
       v
JVM nạp class và gọi main()
       |
       v
SpringApplication.run(...)
       |
       +--> chuẩn bị Environment, profile và cấu hình
       +--> tạo/refresh ApplicationContext
       +--> quét component, xử lý auto-configuration, tạo bean
       +--> dựng web application context và embedded web server
       +--> chạy các runner đã đăng ký, phát tín hiệu ready
       |
       v
Ứng dụng sẵn sàng phục vụ lưu lượng khi các điều kiện readiness đạt
~~~

**@SpringBootApplication** kết hợp vai trò cấu hình Spring Boot, bật auto-configuration và component scanning. **SpringApplication.run(...)** điều phối việc dựng context. Embedded server (thường là Tomcat với Spring MVC; Reactor Netty thường dùng với WebFlux) mở cổng nhận kết nối HTTP. Thứ tự chi tiết giữa các callback phụ thuộc lifecycle của context, vì vậy hãy dựa vào sự kiện/log thực tế, không giả định mọi bean chạy đúng một thứ tự tùy ý.

**ApplicationStartedEvent** và **ApplicationReadyEvent** không có cùng ý nghĩa: sau khi context đã refresh, runner vẫn có thể đang thực thi; ready thể hiện tiến trình khởi tạo dành cho nhận traffic đã đi tới giai đoạn cuối. Nếu tạo bean thất bại, cổng bị chiếm, cấu hình bắt buộc thiếu hoặc runner ném lỗi, ứng dụng có thể khởi động thất bại. Lỗi khởi động thường được thể hiện ở phần **Caused by** sâu nhất có ý nghĩa trong stack trace và Failure Analysis nếu Spring Boot cung cấp.

### 3.2. Luồng request với Spring MVC (Servlet)

~~~text
HTTP client
   |
   v
Embedded Servlet container (ví dụ Tomcat)
   |
   v
Servlet Filter chain (có thể gồm Spring Security)
   |
   v
DispatcherServlet
   |
   +--> HandlerMapping chọn endpoint
   +--> argument resolver / HTTP message converter đọc dữ liệu
   +--> @RestController gọi service và dependency cần thiết
   +--> chuyển kết quả Java thành JSON / response
   +--> xử lý exception qua cơ chế MVC khi có lỗi
   |
   v
HTTP status + header + body trả về client
~~~

Trong mô hình Servlet thông dụng, request được xử lý bởi thread từ pool của container; gọi dịch vụ chậm hoặc blocking I/O giữ tài nguyên của thread trong thời gian chờ. Controller nên nhận/kiểm tra request và điều phối, service chứa logic nghiệp vụ, repository hoặc client giao tiếp phụ thuộc ngoài. Không đặt toàn bộ logic trong controller chỉ vì ví dụ đơn giản chạy được.

**Spring WebFlux** có chuỗi xử lý reactive (WebFilter/DispatcherHandler) và kiểu dữ liệu như Mono/Flux; khi chạy trên event loop, gọi blocking I/O tùy tiện có thể làm nghẽn nhiều request. WebFlux và MVC có mô hình thực thi khác nhau; cần học nền tảng HTTP và bean trước khi so sánh. Một project có cả hai starter có thể có quy tắc chọn kiểu web application không như suy đoán; chỉ chọn stack đúng với mục đích.

## 4. Bài thực hành xuyên suốt: tạo, chạy, gọi và test một web application

Ví dụ này dùng **Spring Boot 3.x, Java 17+** và Spring MVC. Tạo project từ **https://start.spring.io** với Gradle (Groovy), group **com.example**, artifact **runtime-demo**, package **com.example.runtimedemo**; chọn dependency **Spring Web**, **Spring Boot Actuator** và **Spring Boot Starter Test**. Dùng Gradle wrapper được tạo cùng project. Nếu chọn một phiên bản Boot khác, cần đảm bảo dependency và phiên bản JDK tương thích.

### 4.1. Điểm vào ứng dụng

Tạo **src/main/java/com/example/runtimedemo/RuntimeDemoApplication.java**:

~~~java
package com.example.runtimedemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RuntimeDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(RuntimeDemoApplication.class, args);
    }
}
~~~

Lớp này ở package cha để component scanning tìm thấy controller ở cùng package. Phương thức main là điểm JVM bắt đầu; Spring Boot đảm nhiệm việc dựng context và server.

### 4.2. Endpoint và payload JSON

Tạo **src/main/java/com/example/runtimedemo/PingResponse.java**:

~~~java
package com.example.runtimedemo;

public record PingResponse(String status) {
}
~~~

Tạo **src/main/java/com/example/runtimedemo/PingController.java**:

~~~java
package com.example.runtimedemo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PingController {
    @GetMapping("/api/ping")
    public PingResponse ping() {
        return new PingResponse("ok");
    }
}
~~~

**@RestController** đăng ký handler trả nội dung response; **@GetMapping** ánh xạ GET tới đường dẫn; Jackson từ Spring Web chuyển **PingResponse** thành JSON. Mẫu này không dùng database, giúp quan sát rõ vòng đời HTTP trước khi thêm phụ thuộc bên ngoài.

### 4.3. Cấu hình runtime

Đặt nội dung sau trong **src/main/resources/application.yml**:

~~~yaml
spring:
  application:
    name: runtime-demo
  lifecycle:
    timeout-per-shutdown-phase: 20s

server:
  port: 8080
  shutdown: graceful

management:
  endpoint:
    health:
      probes:
        enabled: true
  endpoints:
    web:
      exposure:
        include: health,info
~~~

**server.port** chọn cổng mặc định; **server.shutdown=graceful** cho runtime thời gian kết thúc các request đang xử lý khi có tín hiệu dừng phù hợp; timeout giới hạn thời gian đợi theo phase. Actuator cung cấp tín hiệu health và probe. Ví dụ chỉ expose **health,info** qua web; không expose toàn bộ endpoint quản trị ra internet. Khi dùng cơ chế security, kiểm soát quyền truy cập và mạng đến endpoint vận hành.

Cấu hình Spring Boot có thể đến từ file, profile, biến môi trường, system property và command-line argument. Với thuộc tính đơn giản trong ví dụ, **SERVER_PORT=9090** là một cách override port qua biến môi trường; command-line argument **--server.port=9091** có độ ưu tiên cao hơn trong cấu hình mặc định. Không hardcode mật khẩu/token vào repository; cung cấp secret qua cơ chế cấu hình an toàn của môi trường triển khai.

### 4.4. Chạy và quan sát kết quả

Tại thư mục gốc project, trên Linux/macOS:

~~~bash
./gradlew bootRun
~~~

Trên Windows PowerShell hoặc Command Prompt:

~~~text
gradlew.bat bootRun
~~~

Ở terminal khác, gọi:

~~~bash
curl -s http://localhost:8080/api/ping
~~~

Response body chính xác của ví dụ:

~~~json
{"status":"ok"}
~~~

Với server khỏe và không có health contributor bị lỗi, lệnh:

~~~bash
curl -s http://localhost:8080/actuator/health
~~~

thường trả JSON có **status=UP**, chẳng hạn:

~~~json
{"status":"UP"}
~~~

Giá trị health có thể khác nếu ứng dụng bổ sung dependency, health indicator hoặc cấu hình chi tiết response. Có thể thử **/actuator/health/liveness** và **/actuator/health/readiness** vì ví dụ bật health probes. **Liveness** phản ánh trạng thái sống của tiến trình; **readiness** phản ánh trạng thái sẵn sàng nhận traffic. Mặc định, readiness không kiểm tra tự động mọi dependency bên ngoài; nếu cần đánh giá DB/message broker, phải thiết kế và cấu hình health group/indicator phù hợp.

Khi thấy lỗi 404, kiểm tra method và path trước; khi bị từ chối kết nối, kiểm tra process có chạy, port thực tế và binding/network. Nếu 8080 đang bị chiếm, dừng process xung đột hoặc đổi port bằng cấu hình có chủ đích.

### 4.5. Kiểm thử bằng HTTP thật với cổng ngẫu nhiên

Tạo **src/test/java/com/example/runtimedemo/PingIntegrationTest.java**:

~~~java
package com.example.runtimedemo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class PingIntegrationTest {
    @Autowired
    private TestRestTemplate client;

    @Test
    void pingReturnsOk() {
        ResponseEntity<PingResponse> response =
                client.getForEntity("/api/ping", PingResponse.class);

        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertNotNull(response.getBody());
        assertEquals("ok", response.getBody().status());
    }
}
~~~

Test khởi chạy Spring Boot trên cổng ngẫu nhiên, gửi HTTP request và đối chiếu status/payload. Dùng lệnh:

~~~bash
./gradlew test
./gradlew bootJar
java -jar build/libs/runtime-demo-0.0.1-SNAPSHOT.jar
~~~

Tên JAR minh họa khớp artifact và version **0.0.1-SNAPSHOT** mặc định của project vừa tạo; nếu thay đổi version thì dùng tên artifact thực tế. **bootRun** chạy qua Gradle cho phát triển, còn **java -jar** chạy executable Boot JAR cho đường triển khai. Không đồng nhất việc test HTTP cơ bản thành kiểm chứng đầy đủ cho chức năng, security, database và tải hệ thống.

## 5. Trình tự học đề xuất: hoàn thành theo bằng chứng

| Chặng | Học theo thứ tự | Bài tập có thể kiểm chứng |
| --- | --- | --- |
| 0. Nền tảng | Java/JVM, Gradle/Maven, HTTP/JSON, port và log, IoC/DI | Giải thích được HTTP request/response và một bean được inject như thế nào |
| 1. Tạo và khởi động | Starter, main(), @SpringBootApplication, SpringApplication, auto-configuration, context và embedded server | Chạy bootRun, nhận biết dòng log server lắng nghe cổng và nguyên nhân nếu startup fail |
| 2. Theo luồng web | MVC, DispatcherServlet, controller, mapping, JSON, status, filter và exception handling | Gọi GET /api/ping, đọc JSON và phân biệt 200/404/500 |
| 3. Cấu hình | application.yml, profile, environment, override, tách secret | Đổi port bằng biến môi trường; giải thích giá trị nào được áp dụng và vì sao |
| 4. Chất lượng request | DTO, validation khi thêm starter phù hợp, lỗi API có cấu trúc, service boundary | Có test thành công và test phản hồi lỗi rõ ràng, không lộ stack trace |
| 5. Kiểm thử runtime | Unit test, web-slice test, integration test, cổng ngẫu nhiên, stub dependency | ./gradlew test chạy thành công và phát hiện regression có chủ đích |
| 6. Quan sát và bảo vệ runtime | Actuator health, liveness/readiness, log, metric, timeout, graceful shutdown | Phân tích được tình huống process sống nhưng không nên nhận traffic |
| 7. Đóng gói và vận hành | bootJar, profile môi trường, cấu hình ngoài, deploy/restart/rollback, capacity | Chạy JAR, xem log/health và mô tả cách dừng hoặc rollback an toàn |

**Cách học:** ở mỗi chặng, giữ lại một phiên bản code chạy được, command đã thực thi và bằng chứng cụ thể (HTTP response, test result hoặc log). Chỉ thêm database, security, async hoặc external API sau khi xác nhận vòng đời web cơ bản; khi thêm mỗi dependency, cập nhật cả test và cách quan sát lỗi.

## 6. Từ máy phát triển đến ứng dụng vận hành

### 6.1. Khởi động thành công khác với phục vụ ổn định

Một JVM còn sống có thể gặp pool connection cạn, downstream chậm, queue đầy hoặc lỗi nghiệp vụ. Vì vậy cần phân biệt **liveness** (không bị treo/hỏng theo tiêu chí đã đặt), **readiness** (có thể nhận thêm traffic), **health tổng hợp** và **success rate/latency thực của API**. Không dùng một kết quả UP để tuyên bố mọi chức năng đều hoạt động.

Khi dùng orchestrator như Kubernetes, cấu hình probe theo đường dẫn và thời gian phù hợp; tránh đưa dependency dễ dao động vào liveness vì có thể gây vòng lặp restart. Readiness cần phản ánh đúng điều kiện có thể phục vụ theo kiến trúc thực tế, kể cả thời gian warm-up nếu có.

### 6.2. Cấu hình, bảo mật và phụ thuộc

- Tách cấu hình phát triển/staging/production, dùng profile có mục đích và kiểm tra active profile trong log/Environment khi debug. Biến môi trường là một nguồn override, không phải nơi cất secret duy nhất.
- Không commit credential; thiết lập timeout cho HTTP client, database và downstream; dùng connection pool hợp lý khi ứng dụng có I/O ngoài.
- Đặt authentication, authorization, TLS, CORS, proxy header và giới hạn payload theo yêu cầu hệ thống. Security filter có thể thay đổi status/path trước khi request tới controller.
- Đảm bảo tên host và network đúng môi trường: **localhost** bên trong container là chính container đó, không tự trỏ tới database hoặc service trên máy host.
- Với ứng dụng có trạng thái, lưu session/dữ liệu ở nơi phù hợp nếu cần nhiều instance; tránh trường mutable chia sẻ giữa các request trong singleton bean.

### 6.3. Quan sát trước khi tối ưu

**Log:** ghi sự kiện khởi động, lỗi có stack trace ở phía server, request identifier/correlation khi cần; phân loại mức log; không ghi token, password hoặc thông tin nhạy cảm tùy tiện. Khi chạy container, thông thường ghi log ra stdout/stderr để hệ thống thu thập.

**Metric:** tối thiểu theo dõi lượng request, tỷ lệ lỗi, latency (ví dụ p95/p99), CPU, memory/heap, GC, thread, connection pool và phụ thuộc ngoài khi có. Micrometer/Actuator hỗ trợ xuất metric khi được cấu hình; không mặc định mọi metric đều đã công khai qua HTTP.

**Trace:** khi có nhiều service, dùng trace ID để nối các bước gọi; phân biệt trace với log và metric. Đọc bằng chứng trước khi tăng thread, heap hoặc số instance; tăng tài nguyên không khắc phục logic blocking hoặc query kém.

### 6.4. Vòng đời deploy và shutdown

~~~text
Sửa code + cấu hình
   -> test + build artifact
   -> deploy với biến môi trường/secret đúng
   -> JVM khởi động, context/server được tạo
   -> readiness cho phép nhận traffic
   -> theo dõi log, metric, lỗi và độ trễ
   -> cần dừng: ngừng cấp traffic mới, graceful shutdown
   -> xác nhận instance mới khỏe hoặc rollback khi cần
~~~

Ở production cần cân nhắc port, health/readiness probe, giới hạn CPU/RAM, tín hiệu dừng (ví dụ SIGTERM), timeout từ load balancer/orchestrator, tài nguyên đã mở, cơ chế startup và rollback. **Graceful shutdown** chỉ có hiệu quả trong giới hạn timeout và cách client/downstream xử lý; nó không bảo đảm mọi request dài sẽ hoàn tất. Thử kịch bản restart dưới tải vừa phải để biết hành vi thật.

## 7. Sự cố phổ biến: triệu chứng → nơi kiểm tra → hướng xử lý

| Triệu chứng | Kiểm tra đầu tiên | Hướng xử lý |
| --- | --- | --- |
| Không bind được cổng, Address already in use | Startup log, server.port, process đang nghe | Dừng process xung đột hoặc đặt cổng đúng môi trường |
| No qualifying bean / Unsatisfied dependency | Root cause của exception, package scan, điều kiện auto-config | Sửa dependency/bean/config; không thêm component scan diện rộng tùy tiện |
| GET trả 404 | Host, port, context path, method, @GetMapping, component scan | Sửa đúng đường dẫn hoặc handler được đăng ký |
| POST trả 400 hoặc 415 | Content-Type, JSON syntax, DTO, validation, converter | Chỉnh request và contract; trả thông báo lỗi hữu ích |
| Request trả 500 | Server log, exception gốc, downstream timeout | Sửa nguyên nhân; áp dụng xử lý lỗi thống nhất và không lộ stack trace ra client |
| Health UP nhưng người dùng lỗi | API latency/error rate, readiness group, dependency, business checks | Thêm tín hiệu phù hợp, điều tra downstream và luồng nghiệp vụ |
| Actuator endpoint không truy cập được | Dependency, exposure, base path, security, management port | Cấu hình và kiểm soát truy cập chính xác |
| Chạy local được, chạy container lỗi | Port binding, env/profile, host DNS, filesystem, secret | So sánh cấu hình và log theo môi trường, kiểm tra network thực |

Khi debug, tái hiện bằng một request cụ thể, ghi nhận **thời điểm, URL/method, status, request ID và log cùng thời điểm**, phân biệt lỗi startup với lỗi trong lúc nhận request. Nếu lỗi chỉ xuất hiện khi tải tăng, xem thread/blocking, pool, timeout và metric trước khi sửa ngẫu nhiên.

## 8. Checklist năng lực trước khi chuyển sang module nâng cao

- [ ] Tôi có thể giải thích **JVM → SpringApplication → ApplicationContext → embedded server** bằng lời của mình.
- [ ] Tôi biết request đi qua filter/DispatcherServlet/controller và response được serialize như thế nào trên MVC.
- [ ] Tôi có thể chạy ví dụ, nhận **{"status":"ok"}** và giải thích HTTP status, JSON.
- [ ] Tôi chạy được ít nhất một integration test HTTP và executable JAR.
- [ ] Tôi biết profile/config đến từ đâu, cách đổi port và cách tránh đưa secret vào code.
- [ ] Tôi phân biệt health, liveness, readiness với trải nghiệm API của người dùng; biết giới hạn của mỗi tín hiệu.
- [ ] Tôi biết đọc startup error, log request lỗi, và có phương án stop/restart/rollback cơ bản.

### Tự kiểm tra nhanh

**1. Vì sao chạy được main() vẫn có thể không phục vụ HTTP?** Vì context/bean, cấu hình, server binding hoặc runner có thể thất bại; tiến trình và trạng thái ready cần được quan sát riêng.

**2. Starter và auto-configuration có phải là một?** Không. Starter gom dependency thuận tiện; auto-configuration áp dụng cấu hình dựa trên điều kiện runtime/classpath/property.

**3. Vì sao test trả 200 chưa đủ để deploy?** Test đó chỉ xác minh một luồng; production còn cần readiness, config, security, phụ thuộc, tải, quan sát và khả năng phục hồi.

**4. Nên học MVC hay WebFlux trước?** Học request/response, IoC/DI, lifecycle và MVC cơ bản để nắm nguyên lý, sau đó học WebFlux khi có nhu cầu non-blocking/reactive và hiểu cách quản lý blocking I/O.

Sau khi hoàn thành các bằng chứng trên, người học đã có nền tảng để đi sâu vào Servlet filters/Spring Security, WebFlux, data access, resilience, Actuator/observability và triển khai theo yêu cầu của từng hệ thống.