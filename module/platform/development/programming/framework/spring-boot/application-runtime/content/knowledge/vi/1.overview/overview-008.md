# Lộ trình học qua ứng dụng mẫu và bằng chứng quan sát lúc chạy

**Phạm vi:** Spring Boot Application Runtime. Bài này hướng dẫn học bằng một ứng dụng Java nhỏ, mỗi thay đổi đều có lệnh thực hiện, tín hiệu quan sát và cách giải thích. Mục tiêu là hiểu điều gì xảy ra từ lúc khởi động một tiến trình Spring Boot cho đến khi ứng dụng phục vụ HTTP, nhận cấu hình, gặp lỗi và dừng lại.

## 1. Đích đến và nguyên tắc học

Sau bài thực hành, người học cần tự chứng minh được năm điều:

1. Một tiến trình Java được khởi tạo từ ứng dụng Spring Boot, tạo `ApplicationContext`, đăng ký bean và khởi động web server nhúng.
2. Ứng dụng đã sẵn sàng phục vụ yêu cầu bằng **bằng chứng HTTP và sự kiện runtime**, thay vì suy luận chỉ từ việc lệnh chạy chưa thoát.
3. Giá trị cấu hình và profile tác động trực tiếp đến hành vi của **cùng một bản mã**.
4. Có thể đối chiếu các quan sát khi chạy bằng Maven và khi chạy file JAR được đóng gói.
5. Phân biệt được lỗi khởi động, lỗi định tuyến HTTP, lỗi cấu hình và trạng thái health.

**Cách học:** đặt giả thuyết → chạy đúng một thí nghiệm → lưu lệnh, log và kết quả HTTP → giải thích theo cơ chế Spring Boot → thay một biến để kiểm chứng lại. Một kết luận tốt cần chỉ rõ bằng chứng, không dừng ở “chạy được”.

## 2. Bản đồ các thành phần trong runtime

Một ứng dụng Spring Boot dạng web có thể được hiểu qua tuyến quan sát sau:

~~~text
java / Maven
    |
    v
main() -> SpringApplication.run(...)
    |
    +--> tạo Environment; nạp cấu hình, profile và tham số dòng lệnh
    +--> tạo và refresh ApplicationContext
    |       +--> quét component, tạo và nối các bean
    |       +--> áp dụng auto-configuration theo dependency và điều kiện
    |       +--> khởi động web server nhúng nếu là ứng dụng web
    +--> chạy ApplicationRunner / CommandLineRunner
    +--> phát ApplicationReadyEvent
    |
    v
HTTP request -> servlet container -> DispatcherServlet -> controller -> HTTP response
    |
    +--> Actuator cung cấp điểm quan sát vận hành (nếu được thêm và cấu hình)
    |
Ctrl+C / tín hiệu dừng -> đóng ApplicationContext và tài nguyên
~~~

Các pha ở trên là **mô hình học tập**, không phải cam kết thứ tự của mọi dòng log hoặc mọi bean. `SpringApplication.run` tổ chức vòng đời khởi động; `ApplicationContext` quản lý bean; auto-configuration chỉ cấu hình những gì thỏa điều kiện trên classpath và trong môi trường. Với **Spring MVC**, server nhúng (thường là Tomcat khi dùng bộ starter web tương ứng) tiếp nhận kết nối, còn `DispatcherServlet` điều phối request đến controller.

`ApplicationReadyEvent` diễn ra sau khi các runner hoàn tất. Đây là dấu mốc tốt để **quan sát quá trình startup**, nhưng vẫn cần request HTTP thực tế để chứng minh endpoint đáp ứng đúng. Actuator health cho biết kết quả của các health indicator được cấu hình; `UP` không đồng nghĩa mọi luồng nghiệp vụ đều đúng.

## 3. Dựng một ứng dụng mẫu duy nhất

### 3.1. Chuẩn bị dự án

Sử dụng **JDK 17 trở lên**, Maven và một terminal. Với dự án Spring Boot **3.5.x**, tạo dự án từ Spring Initializr với các lựa chọn sau:

- Project: Maven; Language: Java; Group: `com.example`.
- Artifact: `runtime-lab`; Package: `com.example.runtimelab`; Packaging: Jar; Java: 17.
- Dependencies: **Spring Web** và **Spring Boot Actuator**.

Giữ các dependency và phiên bản plugin do Initializr sinh ra. Nếu đang dùng phiên bản Spring Boot khác, chọn starter web/MVC tương ứng trên Initializr của phiên bản đó và giữ nguyên các phần mã nguồn Java phía dưới. Không cần cài server Tomcat bên ngoài cho bài lab.

Sau khi giải nén, cây file quan trọng là:

~~~text
runtime-lab/
  pom.xml
  mvnw
  mvnw.cmd
  src/main/java/com/example/runtimelab/
    RuntimeLabApplication.java
    GreetingController.java
  src/main/resources/
    application.properties
    application-dev.properties
~~~

### 3.2. Main class và dấu mốc vòng đời

Nội dung `RuntimeLabApplication.java`:

~~~java
package com.example.runtimelab;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.EventListener;

@SpringBootApplication
public class RuntimeLabApplication {
    private static final Logger log =
            LoggerFactory.getLogger(RuntimeLabApplication.class);

    public static void main(String[] args) {
        SpringApplication.run(RuntimeLabApplication.class, args);
    }

    @Bean
    ApplicationRunner startupCheck() {
        return args -> log.info("LAB_RUNNER_DONE");
    }

    @EventListener(ApplicationReadyEvent.class)
    public void onReady() {
        log.info("LAB_APPLICATION_READY");
    }
}
~~~

`@SpringBootApplication` kết hợp cấu hình ứng dụng, component scan và auto-configuration. Runner thực hiện một việc đơn giản sau khi context đã được chuẩn bị. Listener ghi log khi Spring Boot phát sự kiện ready. Hai chuỗi `LAB_RUNNER_DONE` và `LAB_APPLICATION_READY` là **marker do ta tự định nghĩa**, nên dễ tìm trong log; chúng không phải thông báo mặc định của framework. Trong một lần startup thành công, marker runner xuất hiện trước marker ready.

### 3.3. Controller có hành vi đo được

Nội dung `GreetingController.java`:

~~~java
package com.example.runtimelab;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class GreetingController {
    private final String prefix;

    public GreetingController(
            @Value("${demo.greeting-prefix:Xin chào}") String prefix) {
        this.prefix = prefix;
    }

    @GetMapping("/hello")
    public Greeting hello(
            @RequestParam(defaultValue = "bạn") String name) {
        return new Greeting(prefix + ", " + name + "!");
    }

    public record Greeting(String message) {
    }
}
~~~

`@RestController` trả dữ liệu phản hồi HTTP, `@GetMapping` ánh xạ đường dẫn, `@RequestParam` đọc query parameter. Kiểu `record` của Java 17 có thể được Jackson trong starter web tuần tự hóa thành JSON. Giá trị `prefix` lấy từ môi trường cấu hình khi bean được tạo; điều này sẽ giúp kiểm chứng profile và override.

Nội dung `src/main/resources/application.properties`:

~~~properties
spring.application.name=runtime-lab
server.port=8080
demo.greeting-prefix=Xin chào
management.endpoints.web.exposure.include=health,info
management.endpoint.health.show-details=never
~~~

Nội dung `src/main/resources/application-dev.properties`:

~~~properties
demo.greeting-prefix=Chào từ dev
~~~

File `application-dev.properties` được dùng khi profile `dev` hoạt động. Không cần và không nên ghi mật khẩu, token, chuỗi kết nối thật vào log hay ví dụ cấu hình.

### 3.4. Chạy lần đầu và xác nhận kết quả

Ở thư mục gốc dự án, với Linux/macOS:

~~~bash
java -version
./mvnw spring-boot:run
~~~

Trên Windows PowerShell có thể dùng `java -version` và `./mvnw.cmd spring-boot:run`. Giữ terminal này mở. Trong một terminal khác, gửi yêu cầu:

~~~bash
curl -i "http://localhost:8080/api/hello?name=Lan"
curl -i "http://localhost:8080/actuator/health"
~~~

Trên Windows PowerShell, dùng `curl.exe -i` nếu `curl` được ánh xạ đến lệnh PowerShell khác.

Với ứng dụng mẫu và cấu hình mặc định, tín hiệu cần tìm là:

~~~http
HTTP/1.1 200
Content-Type: application/json

{"message":"Xin chào, Lan!"}
~~~

Ở endpoint `/actuator/health`, môi trường lab tối giản, không có phụ thuộc lỗi, thường trả HTTP 200 với JSON tương đương:

~~~json
{"status":"UP"}
~~~

Các header khác, thời gian, PID, thứ tự một số log hoặc nội dung chi tiết từ health indicator có thể khác giữa các máy và phiên bản. **Không** đối chiếu cả log theo từng ký tự; hãy đối chiếu phần có ý nghĩa: mã HTTP, body, tên ứng dụng, cổng, marker sự kiện và nguyên nhân lỗi.

## 4. Lộ trình thực hành với bằng chứng cho từng chặng

Mỗi chặng giữ cùng ứng dụng mẫu. Chỉ chuyển sang chặng sau khi có ít nhất một bằng chứng quan sát được và một câu giải thích cơ chế.

### Chặng 0 — Chốt môi trường trước khi chạy

**Câu hỏi:** tiến trình này sẽ dùng runtime và công cụ build nào?

Thực hiện `java -version`, `./mvnw -version` (hoặc `./mvnw.cmd -version` trên Windows) rồi xác nhận JDK mà Maven thực sự dùng. Đối chiếu `pom.xml` để xác nhận project dùng Java 17 và có Spring Web, Actuator.

**Bằng chứng:** dòng version của Java; Java home và Maven version; dependency trong `pom.xml`. **Giải thích:** build không thành công vì JDK quá thấp là vấn đề môi trường/build, chưa thể suy luận runtime web đã chạy sai.

### Chặng 1 — Quan sát startup theo vòng đời

**Câu hỏi:** ứng dụng đã đi qua các mốc nào trước khi nhận yêu cầu?

Khởi động bằng `./mvnw spring-boot:run`. Tìm dấu hiệu web server bắt đầu nghe cổng 8080, `LAB_RUNNER_DONE` và `LAB_APPLICATION_READY`. Các bản Spring Boot có thể ghi log kiểu `Started RuntimeLabApplication`; nội dung và vị trí của dòng đó không cần giống tuyệt đối.

**Bằng chứng:** tiến trình còn sống; có marker runner và ready; cổng 8080 bắt đầu nhận request. **Giải thích:** context và server được chuẩn bị, runner đã chạy, rồi event ready được phát. Nếu một runner ném exception, startup có thể thất bại dù một số thành phần đã từng được tạo.

**Tiêu chí qua chặng:** giải thích được vai trò riêng của `main`, `SpringApplication`, `ApplicationContext`, runner và event ready.

### Chặng 2 — Kiểm chứng request đi vào ứng dụng

**Câu hỏi:** server “đã mở cổng” có bảo đảm controller trả đúng không?

Thực hiện:

~~~bash
curl -i "http://localhost:8080/api/hello?name=Lan"
curl -i "http://localhost:8080/api/hello"
curl -i "http://localhost:8080/api/khong-ton-tai"
~~~

Hai request đầu trả HTTP 200 và body lần lượt là `{"message":"Xin chào, Lan!"}` và `{"message":"Xin chào, bạn!"}`. Request thứ ba có HTTP 404 vì không có mapping tương ứng; hình dạng body lỗi phụ thuộc cấu hình Spring Boot.

**Bằng chứng:** status và body của từng request. **Giải thích:** Tomcat nhận kết nối, Spring MVC tìm mapping và gọi controller; không có mapping dẫn đến 404. HTTP 404 chứng minh server có thể vẫn đang hoạt động, khác với `Connection refused` khi chưa có tiến trình lắng nghe đúng cổng.

**Tiêu chí qua chặng:** phân biệt được “không kết nối được”, “kết nối được nhưng 404” và “200 với dữ liệu hợp lệ”.

### Chặng 3 — Thay hành vi bằng externalized configuration

**Câu hỏi:** có cần sửa Java để đổi lời chào hoặc cổng?

Dừng phiên chạy trước bằng Ctrl+C. Đóng gói JAR, sau đó chạy với tham số cấu hình:

~~~bash
./mvnw clean package
java -jar target/runtime-lab-0.0.1-SNAPSHOT.jar --server.port=8081 --demo.greeting-prefix=Hello
~~~

Tên file JAR ở trên áp dụng nếu artifact/version do Initializr tạo là `runtime-lab/0.0.1-SNAPSHOT`; nếu khác, kiểm tra tên JAR thực tế trong `target/`.

Từ terminal thứ hai:

~~~bash
curl -i "http://localhost:8081/api/hello?name=Lan"
~~~

**Bằng chứng mong đợi:** HTTP 200, body `{"message":"Hello, Lan!"}` ở cổng 8081 mà mã Java không đổi. **Giải thích:** các tham số `--...` được Spring Boot đưa vào nguồn cấu hình dòng lệnh và có thể override giá trị ứng dụng trong `application.properties`.

**Tiêu chí qua chặng:** chỉ ra rõ nguồn của `server.port` và `demo.greeting-prefix` trong hai lần chạy; hiểu rằng khởi động lại tạo môi trường cấu hình mới.

### Chặng 4 — Thử profile và so sánh ưu tiên cấu hình

**Câu hỏi:** cùng một artifact có thể biểu hiện khác nhau theo môi trường không?

Dừng phiên trước rồi chạy:

~~~bash
java -jar target/runtime-lab-0.0.1-SNAPSHOT.jar --spring.profiles.active=dev
curl -i "http://localhost:8080/api/hello?name=Lan"
~~~

**Bằng chứng:** log hiển thị profile `dev` đang hoạt động và HTTP 200 với `{"message":"Chào từ dev, Lan!"}`. Tiếp tục chạy riêng một lần với cả `--spring.profiles.active=dev` và `--demo.greeting-prefix=Hello`; phản hồi đổi thành `Hello, Lan!`.

**Giải thích:** `application-dev.properties` đóng góp giá trị khi profile `dev` kích hoạt; tham số dòng lệnh trong thí nghiệm này ưu tiên hơn giá trị ở file cấu hình. Các nguồn cấu hình khác như biến môi trường cũng tồn tại; khi chẩn đoán, luôn xác định nguồn nào thắng, không suy từ tên file.

**Tiêu chí qua chặng:** trình bày được một bảng “lệnh khởi động → profile → giá trị prefix → HTTP body” để giải thích sự khác biệt.

### Chặng 5 — Dùng Actuator đúng mục đích

**Câu hỏi:** “ứng dụng khỏe” là bằng chứng cho phần nào?

Với một phiên đang chạy, gọi:

~~~bash
curl -i "http://localhost:8080/actuator/health"
curl -i "http://localhost:8080/actuator/info"
~~~

Dùng đúng cổng thực tế nếu đã đổi `server.port`. `health` thường cho trạng thái tổng hợp, còn `info` có thể là `{}` nếu không khai báo thông tin. Việc có đường dẫn `health` và `info` là nhờ Actuator cùng cấu hình exposure trong lab.

**Bằng chứng:** status HTTP và JSON trả về từ từng endpoint. **Giải thích:** health phản ánh các indicator đang được đăng ký, không thay thế kiểm thử nghiệp vụ `/api/hello`. Những đường dẫn như `/actuator/health/readiness` không mặc nhiên có mặt trong mọi cấu hình; chỉ sử dụng khi health probes được bật và đã xác minh endpoint tồn tại.

**Tiêu chí qua chặng:** nêu được ít nhất một trường hợp health `UP` nhưng nghiệp vụ vẫn lỗi, chẳng hạn controller trả sai dữ liệu dù server và các dependency cơ bản đều hoạt động.

### Chặng 6 — So sánh cách chạy trong lúc phát triển và lúc phân phối

**Câu hỏi:** khác nhau giữa `spring-boot:run` và `java -jar` là gì?

Chạy lần lượt bằng Maven plugin và bằng JAR đã đóng gói, cùng profile/cổng/prefix; thử đúng một request trong mỗi phiên. Không để hai phiên tranh cổng cùng lúc.

**Bằng chứng:** cùng endpoint và cùng body khi đầu vào/cấu hình giống nhau; đường dẫn khởi chạy khác nhau. **Giải thích:** `spring-boot:run` phục vụ vòng lặp phát triển, còn JAR chứa ứng dụng và các dependency cần thiết theo kiểu đóng gói của Spring Boot. Thay đổi `application.properties` sau khi đã build **không tự sửa nội dung JAR cũ**; phải build lại hoặc truyền cấu hình ngoài JAR.

**Tiêu chí qua chặng:** chỉ ra được sự khác biệt giữa “mã nguồn và resource hiện tại” với “nội dung artifact đã build”.

### Chặng 7 — Tạo lỗi có kiểm soát và đọc đúng tín hiệu

**Thí nghiệm A — Trùng cổng:** giữ một instance trên 8080, rồi thử khởi động instance thứ hai trên cùng cổng. Instance sau có thể thất bại với nguyên nhân `Port 8080 was already in use` hoặc `BindException`; từ ngữ phụ thuộc stack. Kết luận dựa vào nguyên nhân trong log và việc tiến trình mới không nghe cổng.

**Thí nghiệm B — Sai đường dẫn:** gọi `/api/hello-wrong` trên instance tốt; thường có HTTP 404, không phải lỗi startup.

**Thí nghiệm C — Sai profile:** chạy không có `--spring.profiles.active=dev`, sau đó so sánh `/api/hello` với khi có `dev`. Nếu kết quả không như kỳ vọng, đọc lại profile đang hoạt động, nguồn `demo.greeting-prefix` và trạng thái restart, không sửa controller theo cảm tính.

**Thí nghiệm D — Sai cổng khi kiểm tra:** cho ứng dụng nghe 8081 nhưng gọi 8080. Nếu không có service nào ở 8080, client báo lỗi kết nối; điều này khác lỗi 404 do chính ứng dụng trả.

**Bằng chứng:** câu lệnh, cổng được chọn, status hoặc thông báo lỗi, dòng nguyên nhân. **Tiêu chí qua chặng:** từ một log/response có thể chỉ ra đang lỗi ở pha startup, mạng/port, ánh xạ HTTP hay cấu hình.

### Chặng 8 — Dừng ứng dụng và kiểm tra vòng đời

Dùng Ctrl+C tại terminal khởi chạy, quan sát tiến trình kết thúc rồi thử request đến cổng vừa sử dụng. Nếu không có tiến trình khác nghe cổng đó, request không còn kết nối được. Có thể thử cấu hình `server.shutdown=graceful` cho một bài nâng cao và quan sát shutdown dưới tải, nhưng không được coi Ctrl+C là bằng chứng mọi request dở dang đều đã hoàn thành.

**Bằng chứng:** terminal kết thúc, cổng ngừng phục vụ, thông báo shutdown nếu runtime phát ra. **Giải thích:** việc dừng tiến trình kết thúc server và đóng context; hành vi xử lý request đang chạy phụ thuộc cấu hình shutdown và loại server. Không kết luận về bảo toàn dữ liệu chỉ từ việc không còn response.

**Tiêu chí qua chặng:** mô tả được khác biệt giữa startup, ready, đang phục vụ và shutdown, cùng một tín hiệu quan sát cho mỗi trạng thái.

## 5. Nhật ký thực nghiệm: ghi bằng chứng thay vì chỉ ghi kết luận

Dùng mẫu cột `Bước | Lệnh và đầu vào | Quan sát trực tiếp | Cơ chế giải thích | Kết luận`. Ví dụ bản ghi đã hoàn chỉnh cho lab:

| Bước | Lệnh và đầu vào | Quan sát trực tiếp | Cơ chế giải thích | Kết luận |
|---|---|---|---|---|
| Startup | `./mvnw spring-boot:run` | `LAB_RUNNER_DONE` rồi `LAB_APPLICATION_READY` | Runner hoàn tất trước ready event | Qua mốc startup |
| HTTP | `GET /api/hello?name=Lan` | 200, `{"message":"Xin chào, Lan!"}` | MVC gọi controller và serialize record | Endpoint hoạt động đúng |
| Profile | `--spring.profiles.active=dev` | 200, `{"message":"Chào từ dev, Lan!"}` | File cấu hình profile cung cấp prefix | Cùng mã, khác config |
| Override | `--demo.greeting-prefix=Hello` | 200, `{"message":"Hello, Lan!"}` | CLI override cấu hình file | Xác nhận nguồn config ưu tiên |
| Health | `GET /actuator/health` | 200, trạng thái `UP` trong lab khỏe | Actuator tổng hợp health indicator | Sức khỏe runtime cơ bản |
| Mapping sai | `GET /api/hello-wrong` | 404 | Không có handler phù hợp | Server đang chạy nhưng route sai |

Các giá trị quan sát trong bảng là **mốc kỳ vọng khi môi trường lab vận hành đúng**. Khi thực hành thật, ghi lại output thực tế kể cả khi khác kỳ vọng và giải thích sự khác biệt. Nên lưu một đoạn log có timestamp, lệnh chạy, status HTTP và body thay vì ảnh chụp terminal không rõ bối cảnh.

## 6. Khung đọc log và phân tích lỗi

Hãy hỏi lần lượt:

1. **Ứng dụng có bắt đầu được không?** Nếu `java` hoặc Maven dừng trước `SpringApplication.run`, ưu tiên kiểm tra JDK, build, classpath và entrypoint.
2. **Context có khởi tạo thành công không?** Các lỗi tạo bean, thiếu property bắt buộc hoặc xung đột cấu hình thường xuất hiện trong startup exception; đọc cả chuỗi `Caused by` đến nguyên nhân gần nguồn.
3. **Web server nghe cổng nào?** Tìm cổng hiệu lực sau khi kết hợp config/profile/CLI; `server.port=0` sẽ yêu cầu chọn cổng động nên không thể mặc định dùng 8080.
4. **Đã đến pha ready chưa?** Tìm marker `LAB_APPLICATION_READY` và thử request thật; marker thiếu cần xem nguyên nhân startup hoặc runner.
5. **Client nhận lỗi thuộc loại nào?** `Connection refused` gợi ý chưa có listener đúng địa chỉ/cổng; 404 gợi ý route không khớp; 500 gợi ý exception xử lý request; phản hồi 200 sai body là lỗi logic/hợp đồng API.
6. **Actuator chứng minh gì?** `UP` chỉ là kết quả các check được đăng ký; muốn biết độ đúng của API vẫn phải gọi API và kiểm tra nội dung.

Không tắt hoàn toàn log, bật `--debug` thường trực hay phơi các endpoint Actuator nhạy cảm chỉ để “dễ quan sát”. Khi cần xem báo cáo điều kiện auto-configuration, có thể khởi động riêng một lượt với `--debug`, tìm condition report, rồi tắt để trở về log phù hợp.

## 7. Những nhầm lẫn thường gặp

- **Lẫn trạng thái process với trạng thái sẵn sàng:** process tồn tại chưa đủ; kết hợp marker ready, HTTP và health.
- **Đọc dòng log startup như một bài test API:** một controller có thể sai mapping hoặc xử lý sai dù startup thành công.
- **Nghĩ `@SpringBootApplication` tạo mọi bean:** component scan tuân theo phạm vi package; auto-configuration có điều kiện, không tự sản sinh mọi thành phần tùy ý.
- **Sửa cấu hình mà không restart/build lại khi cần:** properties nằm trong JAR đã đóng gói không đổi chỉ vì sửa file nguồn; các giá trị `@Value` trong lab được lấy lúc tạo bean.
- **Nhầm `/actuator/health` với readiness tổng quát:** health indicator và readiness probe có ngữ nghĩa khác nhau, cấu hình endpoint có thể khác nhau.
- **Gọi sai cổng nhưng sửa controller:** hãy xác định listener và status kết nối trước khi đụng mã API.
- **So log theo từng dòng:** timestamp, PID, thứ tự khởi tạo chi tiết có thể thay đổi. Tập trung vào sự kiện và kết quả có ý nghĩa.
- **Mở `env`, `configprops`, `heapdump` ra mạng công khai:** quan sát vận hành phải giới hạn endpoint và quyền truy cập, không vô tình để lộ bí mật.

## 8. Bài tự đánh giá và tiêu chuẩn hoàn thành

Hãy chạy một chuỗi thử nghiệm độc lập: lần đầu không active profile trên 8080; lần hai profile `dev` trên 8080; lần ba profile `dev` nhưng CLI override prefix và port 8081; lần bốn cố gọi sai đường dẫn; cuối cùng dừng server. Với **mỗi lần**, lưu lệnh khởi động, profile/cổng hiệu lực, status/body, marker hoặc lỗi tương ứng và giải thích tại sao kết quả thay đổi.

Bài đạt khi người học có thể tự mình:

- Dựng và chạy ứng dụng Java 17 với `@SpringBootApplication`, Spring MVC và Actuator.
- Chỉ ra vị trí tạo context, web server, runner và ready event trên một sơ đồ vòng đời đơn giản.
- Chứng minh hai HTTP response đúng; phân biệt phản hồi 404 với lỗi kết nối.
- Chứng minh profile và CLI tạo kết quả khác nhau mà không sửa logic Java.
- So sánh chạy qua Maven plugin và JAR, kèm ít nhất một bằng chứng đóng gói.
- Giải thích được `/actuator/health` đo điều gì, không suy diễn từ `UP` thành “mọi nghiệp vụ đúng”.
- Chẩn đoán đúng một lỗi trùng cổng, một lỗi route và một lỗi chọn sai cấu hình.
- Ghi lại dữ liệu quan sát thực tế để người khác có thể tái hiện thí nghiệm.

Có thể mở rộng bài bằng `ApplicationFailedEvent`, `ApplicationStartup`, readiness/liveness probes và graceful shutdown khi đã vững các mốc nền tảng. Với mỗi tính năng mở rộng, tiếp tục dùng cùng quy tắc: **cơ chế được đề xuất phải có bằng chứng quan sát độc lập, tái lập được**.

## 9. Tài liệu tra cứu

Các mục tương ứng trong **Spring Boot Reference Documentation**: Running Your Application, SpringApplication, Externalized Configuration, Profiles, Actuator Endpoints và Monitoring and Management over HTTP. Dùng tài liệu của **đúng phiên bản Spring Boot** đang thực hành để đối chiếu tên starter, tập endpoint mặc định và tùy chọn cấu hình.