# Phân biệt máy chủ khởi động thành công với toàn ứng dụng sẵn sàng trong Spring Boot

## 1. Hai mốc thời gian dễ bị nhầm lẫn

Trong một ứng dụng Spring Boot có HTTP server, thông báo như `Tomcat started on port 8080` cho biết **máy chủ web nhúng đã khởi động**. Nó **không tự động chứng minh rằng toàn bộ ứng dụng đã hoàn tất khởi động và sẵn sàng nhận lưu lượng nghiệp vụ**. Sau khi server có thể lắng nghe cổng, Spring Boot vẫn có thể phải thực thi các tác vụ khởi động, chẳng hạn `ApplicationRunner` và `CommandLineRunner`, trước khi công bố ứng dụng sẵn sàng.

Cần phân biệt ít nhất ba câu hỏi:

1. **Máy chủ đã khởi động chưa?** Web server đã được khởi tạo và bắt đầu phục vụ kết nối tại cổng dự kiến hay chưa? Đây là trạng thái của thành phần vận chuyển HTTP.
2. **Spring ApplicationContext đã khởi tạo xong chưa?** Các cấu hình và bean cần thiết cho context đã được nạp, xử lý và làm mới thành công chưa? Đây là một mốc của vòng đời Spring.
3. **Ứng dụng đã sẵn sàng nhận yêu cầu nghiệp vụ chưa?** Các bước khởi tạo trước khi phục vụ người dùng đã hoàn thành, và hệ thống kiểm tra readiness có cho phép định tuyến lưu lượng hay chưa? Đây là trạng thái vận hành của toàn ứng dụng.

Ba câu hỏi liên quan nhưng không đồng nhất. Một cổng HTTP trả lời được không chứng minh dữ liệu tham chiếu đã nạp xong, một background task đã sẵn sàng, hoặc mọi dependency bên ngoài đang hoạt động. Ngược lại, một chương trình `WebApplicationType.NONE` có thể hoàn tất khởi động và sẵn sàng thực thi công việc mà **không tồn tại HTTP server**.

> Quy tắc thực hành: **“server started” là tín hiệu hạ tầng đã lên; “application ready” là tín hiệu ứng dụng đã vượt qua trình tự khởi động theo hợp đồng của Spring Boot**. Độ sẵn sàng nghiệp vụ thực tế còn phụ thuộc những điều kiện riêng mà ứng dụng đã đưa vào cơ chế readiness.

## 2. Diễn tiến khởi động: thứ tự quan trọng

Với một ứng dụng Spring Boot Servlet hoặc Reactive thông thường, trình tự rút gọn là:

~~~text
JVM gọi main()
  |
  v
SpringApplication.run(...)
  |
  +-- Chuẩn bị Environment, profile, cấu hình
  |
  +-- Tạo và refresh ApplicationContext
  |     |
  |     +-- Nạp bean, dependency injection, auto-configuration
  |     +-- Khởi tạo web server nhúng (nếu là ứng dụng web)
  |     +-- Web server được khởi động trong vòng đời refresh
  |     +-- Có thể phát WebServerInitializedEvent
  |
  +-- Log ứng dụng đã "Started" (thông thường)
  +-- ApplicationStartedEvent
  +-- LivenessState = CORRECT
  |
  +-- Chạy ApplicationRunner / CommandLineRunner
  |     |
  |     +-- Có thể còn tải cache, kiểm tra tài nguyên,
  |         đăng ký dữ liệu khởi tạo hoặc thực hiện warm-up
  |
  +-- ApplicationReadyEvent
  +-- ReadinessState = ACCEPTING_TRAFFIC
  |
  v
Ứng dụng hoàn thành chuỗi startup thành công
~~~

Đây là sơ đồ khái quát: chi tiết khởi tạo server, log và callback có thể khác tùy phiên bản và loại ứng dụng. Điều cốt lõi là **`ApplicationStartedEvent` xảy ra sau khi context đã được refresh nhưng trước các runner**, còn **`ApplicationReadyEvent` xảy ra sau khi các runner được gọi và kết thúc thành công**. Spring Boot chuyển readiness sang `ACCEPTING_TRAFFIC` sau `ApplicationReadyEvent`.

### 2.1. Những tín hiệu không thể thay thế cho nhau

| Tín hiệu | Cho biết điều gì? | Chưa chứng minh điều gì? |
| --- | --- | --- |
| Log `Tomcat started on port ...` hoặc thông báo tương đương | Web server đã lên theo triển khai cụ thể | Runner đã hoàn tất, readiness đã mở, mạng bên ngoài đã định tuyến được |
| `WebServerInitializedEvent` | Web server gắn với Spring context đã được khởi tạo và cung cấp thông tin, ví dụ cổng thực tế | Toàn bộ quá trình khởi động ứng dụng đã hoàn tất |
| Log `Started MyApplication in ... seconds` | Spring Boot đã đạt mốc ghi log sau khi refresh context | Runner hoặc công việc sau refresh đã xong |
| `ApplicationStartedEvent` | Context đã refresh thành công, trước các runner | Ứng dụng đã sẵn sàng nhận traffic |
| `LivenessState.CORRECT` | Theo tín hiệu liveness nội bộ, ứng dụng đang chạy và không bị coi là hỏng không thể tự phục hồi | Readiness đã mở hoặc downstream đang khỏe |
| `ApplicationReadyEvent` | Các runner đã được thực hiện thành công, Boot đang hoàn tất giai đoạn startup | Mọi dependency nghiệp vụ hay tác vụ bất đồng bộ đều thực sự đã sẵn sàng |
| `ReadinessState.ACCEPTING_TRAFFIC` | Spring Boot đã công bố trạng thái có thể nhận traffic | Một yêu cầu HTTP bất kỳ chắc chắn thành công; hệ thống bên ngoài đang route đúng |

Ví dụ, nếu `CommandLineRunner` chạy trong 10 giây, web server có thể đã nghe ở cổng 8080 trong khoảng thời gian đó, nhưng readiness vẫn là `REFUSING_TRAFFIC`. Sau khi runner kết thúc thành công, Boot mới hoàn tất mốc application ready. Nếu runner ném exception, startup thất bại dù server có thể từng mở cổng trước đó.

### 2.2. “Lên cổng” và “đã sẵn sàng” khác nhau thế nào?

Một ứng dụng có thể ở các trạng thái sau:

- **Chưa có server**: kết nối đến cổng không thành công; có thể do đang khởi động, khởi động thất bại hoặc ứng dụng vốn không phải web.
- **Server đã lên, readiness chưa mở**: endpoint có thể trả lời, nhưng ứng dụng chưa nên nhận traffic nghiệp vụ từ load balancer; đây thường là giai đoạn chờ runner hoàn tất.
- **Readiness đã mở**: hệ thống readiness cho phép nhận traffic, với điều kiện tín hiệu đó phản ánh đầy đủ những điều kiện cần để phục vụ.
- **Ứng dụng đang shutdown**: server hoặc context có thể chưa dừng hẳn, nhưng readiness nên chuyển về từ chối traffic để hệ thống định tuyến ngừng gửi yêu cầu mới.

**Không thể suy ra readiness chỉ bằng việc thử TCP connect** hay nhìn một dòng log. Một HTTP 200 từ endpoint tự viết cũng không bảo đảm đó là một readiness probe được thiết kế đúng.

## 3. Liveness, readiness và startup probe

Spring Boot cung cấp `ApplicationAvailability` để biểu diễn trạng thái khả dụng của ứng dụng:

- **`LivenessState`**: `BROKEN` hoặc `CORRECT`. Dùng để biểu diễn việc tiến trình có còn vận hành đúng về mặt sống còn hay không. Trong môi trường orchestrator, liveness probe thường quyết định có cần khởi động lại container.
- **`ReadinessState`**: `REFUSING_TRAFFIC` hoặc `ACCEPTING_TRAFFIC`. Dùng để cho biết có nên định tuyến lưu lượng mới đến instance hay không. Một instance có thể sống nhưng tạm thời chưa sẵn sàng.
- **Startup probe**: đây là cơ chế của Kubernetes để cho tiến trình thời gian hoàn tất giai đoạn khởi động dài trước khi áp dụng liveness/readiness probe theo thiết lập. Nó **không phải một trạng thái thứ ba của `ApplicationAvailability`**.

### Vì sao không gộp mọi thứ vào một probe?

Giả sử database bên ngoài mất kết nối tạm thời. Ứng dụng có thể còn sống, có thể phục hồi khi database quay lại, nhưng tạm thời không thể xử lý những yêu cầu phụ thuộc database. Việc đưa lỗi database vào **liveness** có thể khiến Kubernetes liên tục restart toàn bộ pod và làm tình hình xấu hơn. Trường hợp này thường phù hợp hơn với **readiness**, nếu chức năng ứng dụng thật sự không thể phục vụ khi thiếu database.

Ngược lại, nếu chính tiến trình ứng dụng rơi vào trạng thái hỏng nghiêm trọng không thể phục hồi, liveness không khỏe có thể là tín hiệu để orchestrator khởi động lại. Thiết kế probe phải dựa trên hành vi phục hồi thực tế, tránh kiểm tra phụ thuộc bên ngoài một cách máy móc.

**Spring Boot Actuator** có thể cung cấp các endpoint phục vụ Kubernetes:

~~~text
GET /actuator/health/liveness
GET /actuator/health/readiness
~~~

Để dùng những đường dẫn trên, ứng dụng cần dependency Actuator và bật hỗ trợ probes trong môi trường không được tự động kích hoạt (chẳng hạn chạy ngoài Kubernetes). Ví dụ với `application.properties`:

~~~properties
management.endpoint.health.probes.enabled=true
~~~

Khi probes hoạt động, readiness indicator mặc định phản ánh `ReadinessState`. Trạng thái từ chối traffic thường được biểu diễn là `OUT_OF_SERVICE` (HTTP 503 theo mapping mặc định), còn khi sẵn sàng là `UP` (HTTP 200), **với giả định không có health indicator bổ sung làm thay đổi tổng trạng thái**. Liveness khỏe vẫn có thể trả HTTP 200 trong lúc readiness trả HTTP 503.

Các đường dẫn, khả năng truy cập endpoint, status aggregation và mã HTTP phụ thuộc cấu hình Actuator, cấu hình bảo mật và phiên bản. Không nhầm `/actuator/health` nói chung với nhóm `/actuator/health/readiness`: một health endpoint trả 200 không nhất thiết mang ý nghĩa readiness.

### Readiness mặc định có đủ cho nghiệp vụ không?

Chưa chắc. Sự chuyển trạng thái mặc định phản ánh **vòng đời khởi động do Spring Boot quản lý**, đặc biệt là runners. Nó **không tự biết** một Kafka consumer đã subscribe xong, một cache được nạp bất đồng bộ, một token từ dịch vụ ngoài đã lấy được, hay một job phải hoàn tất trước khi được định tuyến traffic.

Nếu nghiệp vụ cần điều kiện đặc biệt, hãy thiết kế quá trình khởi tạo để những điều kiện bắt buộc hoàn thành trước khi ứng dụng được xem là ready, hoặc thêm kiểm tra trạng thái đáng tin vào readiness health group. Không đưa tất cả dịch vụ bên ngoài vào health group theo phản xạ: một phụ thuộc không thiết yếu bị lỗi không nhất thiết làm toàn instance mất khả năng phục vụ.

## 4. Ví dụ Java 17+: server lên trước, ứng dụng ready sau

Ví dụ sau **cố ý giữ `ApplicationRunner` trong 10 giây** để quan sát trạng thái. Đây là chương trình Spring Boot có thể chạy trong dự án Java 17+ phù hợp, không phải mẫu tối ưu về thời gian khởi động cho production.

Tạo dự án Maven bằng [Spring Initializr](https://start.spring.io/) với group `com.example`, artifact `readiness-demo`, package `com.example.readinessdemo`, chọn JDK 17 hoặc mới hơn tương thích với Spring Boot và hai dependency **Spring Web** cùng **Spring Boot Actuator**. Dùng Maven Wrapper có sẵn trong dự án và tạo cấu trúc:

~~~text
readiness-demo/
├─ pom.xml
└─ src/main/
   ├─ java/com/example/readinessdemo/
   │  ├─ ReadinessDemoApplication.java
   │  └─ DiagnosticController.java
   └─ resources/
      └─ application.properties
~~~

**Tệp `src/main/java/com/example/readinessdemo/ReadinessDemoApplication.java`:**

~~~java
package com.example.readinessdemo;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.availability.ApplicationAvailability;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class ReadinessDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReadinessDemoApplication.class, args);
    }

    @Bean
    ApplicationRunner simulateCriticalInitialization(
            ApplicationAvailability availability) {

        return args -> {
            System.out.println("RUNNER_BEGIN=" + availability.getReadinessState());
            Thread.sleep(10_000L);
            System.out.println("RUNNER_END");
        };
    }
}
~~~

**Tệp `src/main/java/com/example/readinessdemo/DiagnosticController.java`:**

~~~java
package com.example.readinessdemo;

import org.springframework.boot.availability.ApplicationAvailability;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DiagnosticController {

    private final ApplicationAvailability availability;

    public DiagnosticController(ApplicationAvailability availability) {
        this.availability = availability;
    }

    @GetMapping("/internal/readiness-state")
    public String readinessState() {
        return availability.getReadinessState().name();
    }
}
~~~

**Tệp `src/main/resources/application.properties`:**

~~~properties
server.port=8080
management.endpoint.health.probes.enabled=true
~~~

Ở thư mục gốc dự án, chạy lệnh phù hợp:

~~~bash
# Linux / macOS
./mvnw spring-boot:run
~~~

~~~powershell
# Windows PowerShell
.\mvnw.cmd spring-boot:run
~~~

Trong quá trình startup, ứng dụng in hai dòng **do chính runner tạo** (ngoài các log của Spring Boot và web server):

~~~text
RUNNER_BEGIN=REFUSING_TRAFFIC
RUNNER_END
~~~

Dòng thứ nhất được in sau khi context đã refresh nhưng trước khi Boot công bố readiness. Dòng thứ hai xuất hiện khi tác vụ giả lập hoàn tất; ngay sau đó Boot mới đi qua các bước `ApplicationReadyEvent` và cập nhật readiness. Các log server có thể xuất hiện trước hai dòng trên; không nên dựa vào thứ tự của mọi dòng log từ các thư viện khác nhau để kết luận một thứ tự tổng quát ngoài các mốc lifecycle được định nghĩa.

**Thử trong một terminal khác khi ứng dụng đang ở khoảng chờ 10 giây**:

~~~bash
curl -i http://localhost:8080/internal/readiness-state
curl -i http://localhost:8080/actuator/health/readiness
curl -i http://localhost:8080/actuator/health/liveness
~~~

Trên Windows, có thể thay `curl` bằng `curl.exe` để tránh alias PowerShell tùy môi trường.

Kết quả mong đợi **trong lúc runner đang chạy**, nếu đã kịp gọi trước khi thời gian chờ kết thúc:

| URL | Trạng thái điển hình | Ý nghĩa |
| --- | --- | --- |
| `/internal/readiness-state` | HTTP 200; body `REFUSING_TRAFFIC` | Endpoint chỉ để quan sát giá trị enum |
| `/actuator/health/readiness` | HTTP 503; JSON có `"status":"OUT_OF_SERVICE"` | Probe khuyến nghị không gửi traffic mới |
| `/actuator/health/liveness` | HTTP 200; JSON có `"status":"UP"` | Ứng dụng có thể sống dù chưa ready |

**Sau khi runner hoàn tất và Boot sẵn sàng**, thử lại:

~~~bash
curl -i http://localhost:8080/internal/readiness-state
curl -i http://localhost:8080/actuator/health/readiness
~~~

Khi đó endpoint chẩn đoán điển hình trả `ACCEPTING_TRAFFIC`, còn readiness health endpoint trả HTTP 200 với `"status":"UP"`. Kết quả tùy cấu hình health group và việc có indicator bổ sung hay không. Nếu không quan sát được trạng thái trung gian do thao tác chậm, tăng thời gian `Thread.sleep` **chỉ khi thử nghiệm**, rồi chạy lại; không cần thay đổi vòng đời Spring Boot.

**Lưu ý quan trọng:** `/internal/readiness-state` trong ví dụ *luôn trả HTTP 200* vì controller chỉ trả một chuỗi. **Không sử dụng endpoint chẩn đoán đó làm readiness probe của Kubernetes**. Chọn endpoint Actuator trả mã HTTP đúng theo health status hoặc xây dựng endpoint vận hành khác với logic status phù hợp.

### Vì sao ví dụ chứng minh hai mốc riêng biệt?

Sau khi Spring refresh web context, server có thể nhận kết nối. Runner vẫn ngủ 10 giây, nên `ApplicationAvailability` tiếp tục trả về `REFUSING_TRAFFIC`. Chỉ sau khi runner thành công, Spring Boot mới phát mốc application ready và công bố `ACCEPTING_TRAFFIC`. Như vậy, **HTTP server có thể trả lời yêu cầu thăm dò trong khi ứng dụng yêu cầu hệ thống định tuyến chưa gửi traffic nghiệp vụ**.

Đây là bài thử mang tính minh họa thời điểm, không bảo đảm rằng mỗi HTTP request tới server đều được xử lý thành công trước application ready: các ứng dụng có bộ lọc, bảo mật, phụ thuộc hoặc worker đặc thù có thể hành xử khác nhau.

## 5. Phân biệt theo kiểu ứng dụng (Application Type)

Spring Boot có thể suy ra hoặc được cấu hình với các kiểu ứng dụng khác nhau. Cách quan sát server started phải đặt trong bối cảnh đó.

| `WebApplicationType` | Hạ tầng điển hình | “Server started” có ý nghĩa? | “Application ready” có ý nghĩa? |
| --- | --- | --- | --- |
| `SERVLET` | Servlet container nhúng như Tomcat hoặc Jetty | Có, nếu app thực sự chạy HTTP server | Có; sau refresh context và runners |
| `REACTIVE` | Reactive web server như Reactor Netty | Có, dù không nhất thiết có dòng log Tomcat | Có; sau refresh context và runners |
| `NONE` | CLI, batch hoặc ứng dụng không tạo web context | Không có web server mặc định để quan sát | Có, theo lifecycle Spring Boot; quá trình có thể kết thúc ngay sau việc cần làm |

Cơ chế lựa chọn loại ứng dụng dựa trên classpath và/hoặc thiết lập tường minh, vì vậy **đừng xem thiếu log Tomcat là lỗi** trong mọi tình huống. Ứng dụng Reactive thường không dùng Tomcat; ứng dụng `NONE` không phải mở HTTP port. Mặt khác, ứng dụng `SERVLET` có thể đã log server started nhưng readiness vẫn từ chối traffic khi runner chưa xong.

Có thể đặt loại ứng dụng tường minh khi thật sự cần:

~~~java
SpringApplication app = new SpringApplication(ReadinessDemoApplication.class);
app.setWebApplicationType(WebApplicationType.NONE);
app.run(args);
~~~

Đoạn trên **chỉ minh họa cấu hình thay thế bên trong `main()`** (cần import `org.springframework.boot.WebApplicationType`); không thực hiện đồng thời với `SpringApplication.run(...)` trong ví dụ đầy đủ. Khi chuyển sang `NONE`, các HTTP endpoint và phép thử `curl` phía trên không còn thích hợp.

## 6. ApplicationReadyEvent có đồng nghĩa với mọi công việc nền đã xong?

Không. `ApplicationReadyEvent` thể hiện việc **các runner đồng bộ đã được thực thi xong** và Boot hoàn tất giai đoạn startup. Nó không chờ vô hạn mọi luồng, future hoặc tác vụ bất đồng bộ do ứng dụng tự khởi tạo.

Ví dụ các cách thiết kế tạo ra “ready giả”:

~~~java
@Bean
ApplicationRunner badInitialization() {
    return args -> {
        new Thread(() -> loadCriticalCache()).start();
        // Runner trả về ngay, trong khi cache có thể chưa nạp xong.
    };
}
~~~

Đây là **đoạn minh họa ý tưởng, không phải mã độc lập biên dịch được**: `loadCriticalCache()` đại diện cho một thao tác nghiệp vụ chưa khai báo. Nó minh họa vấn đề: runner trả về ngay, Boot có thể công bố `ACCEPTING_TRAFFIC` mặc dù dữ liệu bắt buộc vẫn chưa sẵn sàng.

Những cách tốt hơn tùy yêu cầu:

1. Nếu bước khởi tạo thực sự bắt buộc trước mọi yêu cầu, cho runner **đợi đến khi bước đó hoàn tất** hoặc thất bại có kiểm soát, và quyết định chính sách retry/fail-start phù hợp.
2. Nếu khởi tạo phải bất đồng bộ, tạo một trạng thái readiness chuyên biệt được theo dõi nhất quán và tích hợp vào health group, để probe chưa trả healthy cho đến khi công việc quan trọng hoàn tất.
3. Nếu chỉ một nhóm tính năng cần tài nguyên đó, cân nhắc readiness theo khả năng phục vụ thực tế thay vì chặn toàn instance vô điều kiện. Đưa quyết định này vào hợp đồng hệ thống, đừng giấu bằng một log “Started”.

Spring Boot cho phép công bố chuyển trạng thái có chủ đích bằng `AvailabilityChangeEvent.publish(context, ReadinessState.REFUSING_TRAFFIC)` và `AvailabilityChangeEvent.publish(context, ReadinessState.ACCEPTING_TRAFFIC)` khi có nhu cầu. Tuy nhiên **thứ tự sự kiện rất quan trọng**: Boot tự phát `ACCEPTING_TRAFFIC` sau `ApplicationReadyEvent`, nên một lần gửi `REFUSING_TRAFFIC` quá sớm trong lúc khởi động có thể bị trạng thái tự động ghi đè. Không sửa readiness chỉ để làm đèn báo đẹp; chỉ thiết lập khi có cơ chế xác định chính xác điều kiện nhận traffic và chuyển trạng thái lại sau khi điều kiện thay đổi.

## 7. Áp dụng trong container, Kubernetes và load balancer

Trong môi trường nhiều instance, nếu load balancer đưa request đến pod ngay khi cổng HTTP mở, request có thể rơi vào giai đoạn ứng dụng chưa sẵn sàng. Hệ thống điều phối cần dựa vào **readiness**, không dựa vào log server started.

Ví dụ Kubernetes (minh họa phần cấu hình container, cần ghép vào Pod/Deployment hợp lệ):

~~~yaml
readinessProbe:
  httpGet:
    path: /actuator/health/readiness
    port: 8080
  initialDelaySeconds: 0
  periodSeconds: 5
  timeoutSeconds: 2
  failureThreshold: 3
livenessProbe:
  httpGet:
    path: /actuator/health/liveness
    port: 8080
  periodSeconds: 10
  timeoutSeconds: 2
  failureThreshold: 3
~~~

Các khoảng thời gian trên là **giá trị ví dụ**, phải điều chỉnh theo thời gian startup, tài nguyên và yêu cầu vận hành thực tế. Nếu startup thường rất lâu, cân nhắc `startupProbe` để tránh liveness probe restart tiến trình khi nó vẫn đang khởi tạo hợp lệ. Cấu hình probe chỉ hoạt động khi ứng dụng có các endpoint tương ứng, bật Actuator probes và cho phép Kubernetes truy cập.

Cũng cần hiểu giới hạn của cơ chế kiểm tra:

- **Kubernetes readiness:** probe thất bại thường khiến pod bị loại khỏi các điểm cuối sẵn sàng để nhận lưu lượng của Service; nó không mặc nhiên giết tiến trình.
- **Kubernetes liveness:** probe thất bại theo ngưỡng có thể dẫn đến restart container; dùng sai điều kiện có thể gây restart loop.
- **Graceful shutdown:** trước khi hoặc trong quá trình dừng, hệ thống cần ngừng định tuyến request mới và cho request đang xử lý hoàn thành theo chính sách. Tín hiệu readiness giúp điều phối, nhưng thời gian cập nhật route và drain kết nối còn phụ thuộc hạ tầng.
- **Management port riêng:** nếu Actuator chạy trên cổng quản trị khác cổng ứng dụng, health endpoint có thể trả lời trong lúc HTTP server chính gặp lỗi. Với Kubernetes, cần cân nhắc đặt probe tại cùng cổng lắng nghe nghiệp vụ; Spring Boot có hỗ trợ các additional paths cho probe khi được cấu hình phù hợp.
- **Ingress và mạng bên ngoài:** ngay cả khi Spring báo `ACCEPTING_TRAFFIC`, DNS, firewall, TLS, ingress, service discovery và mạng có thể tiếp tục ngăn request đi tới ứng dụng. Readiness ứng dụng là một thành phần của khả dụng end-to-end.

## 8. Quan sát và chẩn đoán khi hệ thống không phục vụ

Khi thấy log server started nhưng người dùng nhận lỗi, hãy đặt câu hỏi theo thứ tự hợp lý:

| Hiện tượng | Diễn giải cần kiểm tra | Thao tác xác minh |
| --- | --- | --- |
| Log web server started, nhưng readiness 503 | Ứng dụng có thể đang chạy runner, đang từ chối traffic, hoặc health group có indicator lỗi | Kiểm tra runner, `ReadinessState`, chi tiết health và log sau startup |
| Log `Started ...` nhưng chưa thấy ready | Mốc context refresh có thể đã đạt nhưng runner chưa kết thúc | Theo dõi `ApplicationReadyEvent` và `ApplicationRunner`/`CommandLineRunner` |
| Liveness 200, readiness 503 | Tiến trình được xem là sống nhưng chưa thể nhận yêu cầu | Xem điều kiện readiness; tránh restart theo phản xạ |
| Readiness 200 nhưng API vẫn 500 | Readiness không đo được lỗi endpoint hay phụ thuộc liên quan, hoặc lỗi nảy sinh sau khi ready | Kiểm tra request trace, error log, các chỉ báo nghiệp vụ và phụ thuộc cụ thể |
| `curl localhost` chạy nhưng khách ngoài không tới | Khác biệt network bind, port mapping, proxy, ingress, TLS hoặc security | Kiểm tra từ bên ngoài container, routing và port được expose |
| Ứng dụng có `WebApplicationType.NONE` không mở cổng | Có thể hoàn toàn đúng với CLI/batch | Xem application type, exit code, runner và log |
| Lúc shutdown vẫn thấy cổng lắng nghe | Dừng graceful và tuyến lưu lượng cần thời gian hội tụ | Xác minh readiness giảm trước, drain thời gian hợp lý, cấu hình shutdown |

**Điểm mấu chốt:** log, TCP connect, HTTP 200, Spring availability và kết quả một nghiệp vụ là những phép đo khác nhau. Muốn khẳng định hệ thống sẵn sàng phục vụ, cần xác định **điều kiện nghiệp vụ phải đúng**, rồi tạo probe phản ánh điều kiện đó. Readiness không phải phép màu suy ra mọi lỗi từ mạng hoặc phụ thuộc.

### Quan sát qua lifecycle event

Khi cần đo chính xác thời điểm Boot hoàn tất startup, sử dụng `ApplicationReadyEvent` hoặc readiness health state thay vì parse một chuỗi log của server. Một listener ví dụ đặt bên trong lớp cấu hình Spring:

~~~java
@Bean
ApplicationListener<ApplicationReadyEvent> readyLogListener() {
    return event -> System.out.println("APPLICATION_READY_EVENT");
}
~~~

Đây là **đoạn minh họa cần import** `org.springframework.context.ApplicationListener`, `org.springframework.boot.context.event.ApplicationReadyEvent` và `org.springframework.context.annotation.Bean`. Listener được gọi lúc `ApplicationReadyEvent` phát ra; trạng thái `ReadinessState.ACCEPTING_TRAFFIC` được Boot công bố **sau sự kiện đó**, vì vậy tránh giả định listener này đã thấy readiness ACCEPTING khi nó vừa được gọi.

Đối với thời gian khởi động hoặc khả năng quan sát ở production, dùng metrics, tracing, health probes và event theo định nghĩa của framework; không phụ thuộc vào vị trí tương đối của các dòng console log đến từ nhiều thư viện khác nhau.

## 9. Lỗi hiểu nhầm thường gặp

1. **“Tomcat started = ứng dụng ready.”** Sai trong lúc runner hoặc điều kiện khởi tạo quan trọng vẫn chưa hoàn tất.
2. **“Log Started = ApplicationReadyEvent.”** Sai; mốc log thường đến trước khi runners chạy xong.
3. **“Liveness UP = an toàn nhận traffic.”** Sai; tiến trình có thể sống nhưng readiness đang `REFUSING_TRAFFIC`.
4. **“HTTP 200 của một endpoint bất kỳ là readiness.”** Sai; endpoint đó có thể luôn trả 200 dù tài nguyên nghiệp vụ chưa sẵn sàng.
5. **“Readiness mặc định kiểm tra hết database, cache, broker.”** Sai; phải hiểu từng indicator, điều kiện và cấu hình nhóm health.
6. **“Ứng dụng không có Tomcat log là khởi động hỏng.”** Sai với Reactive hoặc `NONE`.
7. **“Runner tạo thread xong là công việc khởi tạo đã xong.”** Sai nếu thread tiếp tục chạy bất đồng bộ.
8. **“Readiness 200 bảo đảm toàn bộ đường đi từ Internet thành công.”** Sai; ứng dụng và hạ tầng định tuyến có những điều kiện khác nhau.
9. **“Cho dependency tạm thời mất kết nối vào liveness để tự sửa bằng restart.”** Có thể tạo restart loop; xác định rõ tính phục hồi trước khi quyết định.
10. **“Viết listener ApplicationReadyEvent là đã kiểm soát được readiness.”** Không đủ; Boot tự phát readiness accepting ngay sau sự kiện và có thể ghi đè tín hiệu phát quá sớm.

## 10. Câu hỏi ôn tập và bài tập

**Câu hỏi 1.** HTTP server đã bind cổng 8080. Một `ApplicationRunner` vẫn đang xử lý trong 10 giây. Có nên coi ứng dụng đã ready chưa?

**Trả lời:** Chưa theo lifecycle readiness mặc định của Spring Boot. Server có thể nhận kết nối, nhưng `ReadinessState` vẫn là `REFUSING_TRAFFIC` cho tới khi các runner thành công và Boot hoàn tất bước ready.

**Câu hỏi 2.** Trong cùng thời điểm, `/actuator/health/liveness` trả 200 và `/actuator/health/readiness` trả 503. Có mâu thuẫn không?

**Trả lời:** Không. Liveness và readiness đo hai khía cạnh khác nhau: ứng dụng còn sống nhưng chưa nhận traffic.

**Câu hỏi 3.** Startup không tạo web server nhưng `ApplicationReadyEvent` vẫn phát. Có bất thường không?

**Trả lời:** Không. `WebApplicationType.NONE` vẫn có vòng đời Spring Boot và giai đoạn ready, dù không có máy chủ HTTP.

**Câu hỏi 4.** Sau ApplicationReadyEvent, một cache quan trọng vẫn tải trong background; readiness trả 200. Nên sửa ở đâu?

**Trả lời:** Cần xác định cache có bắt buộc cho mọi request không. Nếu bắt buộc, đồng bộ giai đoạn khởi tạo hoặc tích hợp trạng thái cache vào readiness; xem lại thứ tự chuyển trạng thái và điều kiện thất bại. Chỉ đổi tên log hoặc xem thêm cổng HTTP không giải quyết được.

**Bài tập thực hành:** Chạy ví dụ ở mục 4, quan sát health/readiness khi runner đang chạy, rồi đo lại sau khi runner hoàn tất. Tiếp theo, thay thời gian sleep bằng một nhiệm vụ chuẩn bị dữ liệu có kiểm soát; phân tích điều gì xảy ra khi nhiệm vụ thất bại. Thảo luận vì sao một `ApplicationRunner` tạo thread nền rồi trả về ngay có thể khiến hệ thống công bố sẵn sàng quá sớm.

## 11. Ghi nhớ áp dụng

- **Server started:** mốc web server có thể mở cổng, chưa nói đủ về toàn ứng dụng.
- **Application started:** context đã refresh, Boot phát `ApplicationStartedEvent`, trước runner.
- **Application ready:** runner hoàn tất, Boot phát `ApplicationReadyEvent` rồi chuyển `ReadinessState` sang `ACCEPTING_TRAFFIC`.
- **Liveness:** khả năng sống và hồi phục của tiến trình. **Readiness:** có nên gửi traffic mới vào instance không.
- Với Servlet/Reactive, dùng readiness probe phù hợp thay vì suy ra từ log server. Với `NONE`, không áp tiêu chí HTTP server cho ứng dụng.
- Với bước khởi tạo nghiệp vụ bất đồng bộ, phải quản lý trạng thái sẵn sàng theo điều kiện phục vụ thực tế.