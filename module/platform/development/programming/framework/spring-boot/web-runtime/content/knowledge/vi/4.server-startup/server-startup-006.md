# Phân biệt máy chủ đã mở cổng với ứng dụng đã sẵn sàng phục vụ

## 1. Vấn đề: một cổng đang LISTEN có đồng nghĩa ứng dụng đã dùng được?

Không. Khi triển khai dịch vụ Spring Boot, có ít nhất ba thời điểm cần phân biệt:

1. **Tiến trình Java đang chạy**: JVM còn tồn tại, nhưng có thể đang tải cấu hình, tạo Bean hoặc chưa khởi động HTTP server.
2. **Máy chủ web đã mở cổng**: hệ điều hành/web server có thể đã bind địa chỉ và lắng nghe TCP; kết nối đến cổng có thể thiết lập. Điều này chưa nói rõ Controller đã trả lời, thao tác khởi tạo đã xong hay ứng dụng nên nhận traffic thật.
3. **Ứng dụng đã sẵn sàng phục vụ (readiness)**: các công việc startup mà ứng dụng bắt buộc hoàn tất đã xong, ứng dụng tự báo có thể nhận traffic và hệ thống điều phối/load balancer đã xác nhận trạng thái thích hợp trước khi định tuyến request.

Một server có thể **mở cổng 8080 nhưng chưa ready**; cũng có thể **đã ready rồi lại tạm thời unready** trong lúc cổng vẫn mở. Ngược lại, một endpoint /health trả HTTP 200 chưa chắc chứng minh nghiệp vụ người dùng chạy đúng. Vì vậy không dùng duy nhất thông báo “Tomcat started on port ...”, phép thử mở TCP, hoặc kết quả ping đơn giản làm tiêu chí bàn giao ứng dụng.

Bài này tập trung vào quá trình **khởi động máy chủ web và tín hiệu readiness của Spring Boot**, không đi sâu sang tuning thread, database pool hay cơ chế xác thực.

## 2. Năm câu hỏi vận hành phải tách riêng

| Câu hỏi | Tín hiệu quan sát | Tín hiệu thực sự cho biết | Chưa chứng minh được |
| --- | --- | --- | --- |
| Process còn sống không? | PID/JVM, trạng thái container | Tiến trình chưa thoát | Server đang nghe cổng hoặc sẵn sàng xử lý |
| TCP port có mở không? | Socket LISTEN, TCP connect thành công | Có listener trên đúng địa chỉ và cổng | HTTP request thực thi được, startup hoàn tất |
| HTTP endpoint có trả lời không? | HTTP status, body, thời gian phản hồi | Đường mạng, server và endpoint cụ thể đã trả lời | Toàn bộ dependency hoặc workflow đều khỏe |
| Ứng dụng có live không? | LivenessState hoặc liveness probe | Ứng dụng có tình trạng nội bộ phù hợp để tiếp tục chạy | Đã sẵn sàng nhận traffic ngay |
| Instance có ready không? | ReadinessState hoặc readiness probe | Instance báo sẵn sàng/không sẵn sàng nhận traffic | Mọi API, dữ liệu và downstream đều đúng trong mọi tình huống |

Ví dụ: sau khi mở socket, server có thể chưa hoàn thành ApplicationRunner đang tải dữ liệu bắt buộc. TCP probe có thể thành công trong khi readiness vẫn là **REFUSING_TRAFFIC**. Nếu health endpoint cũng chưa xử lý request ở giai đoạn đó, kết quả HTTP có thể là timeout hoặc lỗi kết nối; không được giả định lúc nào cũng trả 503.

Đồng thời, phải kiểm tra **đúng instance, đúng cổng và đúng protocol**. Một proxy hoặc management server có thể trả lời trong khi cổng nghiệp vụ của ứng dụng bị lỗi.

## 3. Trình tự khởi động Spring Boot: web server và ApplicationReadyEvent là hai mốc khác nhau

Với Spring Boot 3.x, khởi động đi qua các mốc chính sau:

1. **SpringApplication.run(...)** chuẩn bị môi trường, đọc cấu hình, tạo ApplicationContext và nạp Bean definitions.
2. **Context refresh** khởi tạo thành phần cần thiết và web server nhúng (ví dụ embedded Tomcat cho Spring MVC); sự kiện **ServletWebServerInitializedEvent** được phát khi web server được khởi tạo, có thể cung cấp cổng thực tế.
3. **ApplicationStartedEvent** được phát sau khi context refresh, **trước** khi gọi các Bean ApplicationRunner và CommandLineRunner.
4. Spring Boot cập nhật trạng thái **LivenessState.CORRECT** sau ApplicationStartedEvent.
5. Các **ApplicationRunner/CommandLineRunner** được thực thi. Đây là giai đoạn phù hợp để thực hiện công việc khởi động bắt buộc trước khi nhận traffic.
6. **ApplicationReadyEvent** được phát sau khi các runner đã hoàn tất.
7. Ngay **sau** ApplicationReadyEvent, Spring Boot phát thay đổi trạng thái **ReadinessState.ACCEPTING_TRAFFIC**.

Thứ tự này quan trọng: **ApplicationStartedEvent không đồng nghĩa ApplicationReadyEvent**. Ngay cả khi nhận được ApplicationReadyEvent trong một listener đồng bộ, trạng thái ReadinessState.ACCEPTING_TRAFFIC có thể mới được phát ở bước tiếp theo. Nếu muốn biết trạng thái availability chính xác, truy vấn **ApplicationAvailability** hoặc quan sát **AvailabilityChangeEvent**.

Sơ đồ đơn giản:

~~~text
JVM chạy
   |
   v
Tạo ApplicationContext, khởi tạo web server
   |  WebServerInitializedEvent
   |  Cổng HTTP có thể đã được bind/mở
   v
Context refresh hoàn tất
   |  ApplicationStartedEvent
   |  LivenessState.CORRECT
   |  ReadinessState.REFUSING_TRAFFIC
   v
ApplicationRunner / CommandLineRunner đang chạy
   |  Chuẩn bị dữ liệu, kiểm tra cấu hình, warm-up bắt buộc
   |  Chưa nên đưa traffic đến instance
   v
ApplicationReadyEvent
   |
   v
ReadinessState.ACCEPTING_TRAFFIC
   |  Được hệ thống điều phối quan sát qua readiness probe
   v
Instance có thể được chọn để nhận traffic
~~~

Sơ đồ nói về **trạng thái logic và quy trình điều phối**. Hành vi socket/HTTP trong từng khoảnh khắc phụ thuộc embedded server, cơ chế tạm dừng connector và cấu hình thực tế. Tài liệu Spring Boot lưu ý ở giai đoạn “Started” server có thể **từ chối xử lý request**, dù context đã refresh. Không dựa vào một log hoặc một lần TCP connect để suy đoán rằng endpoint HTTP chắc chắn đã phản hồi.

### 3.1. Liveness khác readiness

- **Liveness:** ứng dụng có còn hoạt động đúng ở mức nội bộ để tiếp tục chạy không. Trạng thái thường gặp **BROKEN** và **CORRECT**. Kubernetes dùng liveness probe thất bại liên tiếp làm tín hiệu **restart container**.
- **Readiness:** instance có nên tiếp nhận request lúc này không. Trạng thái thường gặp **REFUSING_TRAFFIC** và **ACCEPTING_TRAFFIC**. Kubernetes dùng readiness probe thất bại để **rút Pod khỏi các endpoint Service phù hợp**; việc unready tự nó không đồng nghĩa restart.
- **Startup probe:** cơ chế Kubernetes giúp ứng dụng khởi động lâu có khoảng thời gian hoàn tất khởi động trước khi liveness/readiness probe chạy. Nó khác với ApplicationStartedEvent và không tự chứng nhận mọi workflow nghiệp vụ đã sẵn sàng.

Một ứng dụng có thể **live = CORRECT** nhưng **ready = REFUSING_TRAFFIC**. Đây là trạng thái hợp lệ khi runner đang chạy hoặc ứng dụng tạm từ chối traffic để bảo trì/giảm tải.

## 4. Những tín hiệu dễ gây kết luận sai

### 4.1. “Tomcat started on port 8080”

Log này chỉ mô tả mốc của web server nhúng. Nó không tự xác nhận ApplicationRunner kết thúc, cache/dữ liệu bắt buộc được khởi tạo, hoặc readiness đã ACCEPTING_TRAFFIC. Một số lỗi startup muộn còn có thể xảy ra sau khi cổng xuất hiện trong log.

### 4.2. “Started ReadinessDemoApplication in ... seconds”

Dòng log startup của framework không phải hợp đồng readiness cuối cùng cho hệ thống điều phối. Đối với Spring Boot, hãy căn cứ vào vòng đời sự kiện và readiness state; không đặt probe dựa trên việc dò chuỗi log.

### 4.3. TCP connect thành công

Lệnh thử cổng cho biết host:port có nhận kết nối tại thời điểm kiểm tra. TCP probe không biết code Controller, security filter, router, runner hay DB đang sẵn sàng. Vì vậy dùng TCP probe cho readiness của dịch vụ HTTP có nguy cơ báo **false positive**.

### 4.4. GET / trả HTTP 200

Trang mặc định hoặc endpoint ping đơn giản có thể hoạt động khi một luồng nghiệp vụ chính đã hỏng; nhiều phụ thuộc không bị kiểm tra. Ngược lại, HTTP 401/403 ở endpoint có bảo vệ có thể là lỗi xác thực của người kiểm tra, không đồng nghĩa ứng dụng unready. Health tổng quát, liveness, readiness và kiểm tra nghiệp vụ là những phép đo khác nhau.

### 4.5. GET /actuator/health báo UP hoặc DOWN

Global health có thể tổng hợp nhiều health indicator (ví dụ DB nếu được cấu hình). Readiness group của Spring Boot mặc định thể hiện **readinessState**, không mặc nhiên đòi hỏi mọi dịch vụ bên ngoài đều khỏe. Vì vậy có thể có trường hợp global health báo DOWN nhưng readiness probe vẫn UP, hoặc ngược lại theo cấu hình; cần xem thành phần trong từng health group.

## 5. Thực hành: quan sát server khởi tạo trước khi readiness chuyển sang ACCEPTING_TRAFFIC

Ví dụ sau là một **ứng dụng Spring Boot 3.3.x + Spring MVC + Actuator + Java 17+** tối thiểu có thể chạy với Maven. Nó cố ý giữ ApplicationRunner trong 10 giây để làm lộ khoảng thời gian giữa server khởi tạo và ứng dụng hoàn thành startup. Không đặt thao tác Thread.sleep này vào ứng dụng production.

### 5.1. Tạo cấu trúc dự án

~~~text
readiness-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── com/example/readinessdemo/ReadinessDemoApplication.java
        └── resources/application.yml
~~~

**pom.xml**:

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
    <artifactId>readiness-demo</artifactId>
    <version>1.0.0</version>

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
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**src/main/resources/application.yml**:

~~~yaml
server:
  port: 8080

management:
  endpoint:
    health:
      probes:
        enabled: true
        add-additional-paths: true
  endpoints:
    web:
      exposure:
        include: health,info
~~~

Ở đây chủ động bật health probes cho **môi trường local**, kể cả khi không chạy trong Kubernetes. Spring Boot 3.3 có thể tự bật khi phát hiện môi trường Kubernetes, nhưng không nên suy luận rằng hai path probe đều sẵn có trong mọi cấu hình.

Sau khi khởi động xong, health groups sẽ có:
- **GET /actuator/health/liveness**
- **GET /actuator/health/readiness**
- **GET /livez** và **GET /readyz** trên **cổng ứng dụng chính** nhờ add-additional-paths=true.

Không đặt management.server.port riêng trong ví dụ này. Nếu dùng cổng quản trị khác, truy vấn vào cổng đó có thể không phản ánh việc cổng ứng dụng nhận request được; vì thế các đường dẫn /livez và /readyz trên **main server port** thường phù hợp hơn để kiểm tra đường phục vụ traffic thực.

**src/main/java/com/example/readinessdemo/ReadinessDemoApplication.java**:

~~~java
package com.example.readinessdemo;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.availability.ApplicationAvailability;
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.boot.web.servlet.context.ServletWebServerInitializedEvent;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.EventListener;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class ReadinessDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReadinessDemoApplication.class, args);
    }

    @EventListener
    public void webServerInitialized(ServletWebServerInitializedEvent event) {
        System.out.println("WEB_SERVER_INITIALIZED port="
                + event.getWebServer().getPort());
    }

    @EventListener
    public void applicationStarted(ApplicationStartedEvent event) {
        System.out.println("APPLICATION_STARTED");
    }

    @Bean
    ApplicationRunner prepareBeforeTraffic(ApplicationAvailability availability) {
        return args -> {
            System.out.println("RUNNER_BEGIN readiness="
                    + availability.getReadinessState());
            Thread.sleep(10_000);
            System.out.println("RUNNER_END");
        };
    }

    @EventListener
    public void applicationReady(ApplicationReadyEvent event) {
        System.out.println("APPLICATION_READY");
    }

    @EventListener
    public void availabilityChanged(AvailabilityChangeEvent<?> event) {
        if (event.getState() instanceof ReadinessState) {
            System.out.println("READINESS_CHANGE=" + event.getState());
        }
    }
}

@RestController
class PingController {

    @GetMapping("/api/ping")
    String ping() {
        return "pong";
    }
}
~~~

Ví dụ ghi rõ cả mốc **web server initialized**, **application started**, **runner begin/end**, **application ready** và **readiness state changed**. PingController minh họa API nghiệp vụ tối thiểu, không thay thế readiness probe. Đoạn Java là mã độc lập của một ứng dụng khi đặt đúng cấu trúc Maven và có hai dependencies nêu trên.

### 5.2. Chạy và quan sát

Trong thư mục **readiness-demo**, dùng terminal thứ nhất:

~~~bash
mvn spring-boot:run
~~~

Những thông điệp do mã mẫu tự in sẽ theo thứ tự ý nghĩa:

~~~text
WEB_SERVER_INITIALIZED port=8080
APPLICATION_STARTED
RUNNER_BEGIN readiness=REFUSING_TRAFFIC
RUNNER_END
APPLICATION_READY
READINESS_CHANGE=ACCEPTING_TRAFFIC
~~~

Framework có thể in **các log khác chen giữa**; danh sách trên chỉ mô tả thứ tự thông điệp do mã mẫu in, không phải toàn bộ stdout. Bước RUNNER_BEGIN đến RUNNER_END mất khoảng 10 giây do Thread.sleep; thời điểm HTTP socket bắt đầu nhận request phụ thuộc server.

Trong terminal thứ hai, kiểm tra **trong lúc runner đang chờ**, rồi kiểm tra lại **sau** khi nhận READINESS_CHANGE=ACCEPTING_TRAFFIC:

~~~bash
curl -i --max-time 3 http://localhost:8080/readyz
curl -i --max-time 3 http://localhost:8080/api/ping
~~~

Trên Windows PowerShell, gọi **curl.exe** thay cho alias curl khi muốn dùng đúng tham số curl. Nếu muốn xem socket, dùng Get-NetTCPConnection -LocalPort 8080 trên PowerShell hoặc ss -lnt trên Linux; hãy kiểm tra PID thực sự sở hữu port khi có nhiều tiến trình.

Khi còn ở giai đoạn startup, request có thể **chưa được nhận, bị giữ chờ, timeout hoặc báo unready**, tùy embedded server và giai đoạn kiểm tra; đừng cứng hóa một mã HTTP duy nhất vào bài kiểm thử. Sau khi ready, với cấu hình và ứng dụng mẫu còn hoạt động bình thường, kết quả thường là:

~~~http
HTTP/1.1 200

{"status":"UP"}
~~~

cho **GET /readyz**; và:

~~~http
HTTP/1.1 200

pong
~~~

cho **GET /api/ping**. Header thực tế (Content-Type, Content-Length, Date...) và HTTP protocol version phụ thuộc client/server, nên ví dụ chỉ nêu status/body có ý nghĩa.

Kết luận quan sát phải gồm **mốc trong log**, **readiness state** và **phản hồi HTTP**, không chỉ một trong ba. Nếu chạy lại quá muộn, có thể bạn không kịp nhìn thấy trạng thái giữa chừng; hãy khởi động lại ứng dụng mẫu để quan sát.

### 5.3. Vì sao ví dụ không dùng @PostConstruct để giữ startup?

@PostConstruct gắn với khởi tạo Bean; kéo dài hoặc chặn ở đó có thể khiến context chưa refresh xong, nên không minh họa rõ giai đoạn “context đã started nhưng app chưa ready”. **ApplicationRunner/CommandLineRunner** là điểm thích hợp để thực hiện các startup task được thiết kế chạy **trước** khi ứng dụng được coi là sẵn sàng phục vụ.

Không đưa những tác vụ trì hoãn vô hạn, chờ người dùng hoặc gọi mạng không có timeout vào runner. Nếu công việc phải khởi động bất đồng bộ sau khi trả về từ runner, mặc định Spring Boot có thể đã chuyển sang ready dù việc đó chưa xong; lúc ấy phải thiết kế cổng readiness riêng và chỉ chuyển sang ACCEPTING_TRAFFIC khi đúng các điều kiện bắt buộc.

## 6. Health probe và Kubernetes: ai quyết định traffic đến instance?

Trong môi trường Kubernetes, **kubelet** gọi probe của container, còn **Service/EndpointSlice và các thành phần mạng** dựa vào trạng thái sẵn sàng để định tuyến. Readiness của ứng dụng phải được **biểu lộ qua endpoint**; chỉ đổi một biến Boolean trong code mà không gắn nó với probe sẽ không tự thay đổi tuyến traffic.

Một đoạn cấu hình minh họa **đặt bên trong mục containers[]** của Pod spec:

~~~yaml
startupProbe:
  httpGet:
    path: /livez
    port: 8080
  periodSeconds: 5
  failureThreshold: 24

livenessProbe:
  httpGet:
    path: /livez
    port: 8080
  periodSeconds: 10
  failureThreshold: 3

readinessProbe:
  httpGet:
    path: /readyz
    port: 8080
  periodSeconds: 5
  failureThreshold: 2
  successThreshold: 1
~~~

Đây là **fragment cấu hình**, cần đặt vào definition của container thực; không phải manifest Deployment độc lập. Vì ứng dụng mẫu bật additional paths, cả /livez và /readyz chạy trên cổng web chính 8080.

- **startupProbe** cho phép tối đa khoảng 24 × 5 giây chờ probe thành công, với lưu ý thời điểm kiểm tra và các timeout có thể ảnh hưởng thời gian thực tế. Khi startupProbe được cấu hình, Kubernetes chưa chạy liveness/readiness probe cho đến khi startup probe thành công.
- **livenessProbe** hỏi “có nên restart vì ứng dụng không còn live?”. Không gắn liveness với tình trạng DB hay API ngoài dùng chung vì một sự cố downstream có thể làm mọi replica bị restart hàng loạt.
- **readinessProbe** hỏi “Pod có nên nhận request lúc này?”. Khi probe thất bại đủ ngưỡng, Pod bị đánh dấu unready và bị loại khỏi tập endpoint nhận traffic của Service. Kubelet vẫn giữ container chạy nếu nguyên nhân chỉ là readiness thất bại.

HTTP probe coi status **200–399** là thành công; status lỗi hoặc không kết nối được là không thành công. Đừng suy ra rằng Kubernetes luôn trả HTTP 503 về client khi không còn endpoint ready: hành vi ở Service, ingress, gateway và load balancer có thể khác nhau.

**Quan trọng:** Port mở không tự làm Kubernetes cho traffic qua, nếu bạn cấu hình readinessProbe đúng. Ngược lại, nếu **không có readinessProbe**, ứng dụng có thể bị định tuyến sớm dù startup runner chưa xong.

## 7. Định nghĩa “ready” đúng với nghiệp vụ

Mặc định, Spring Boot chuyển readiness sang ACCEPTING_TRAFFIC khi runner kết thúc. Điều đó **không tự kiểm tra đầy đủ** tính đúng đắn của nghiệp vụ. Hãy xác định các điều kiện thiết yếu để nhận traffic theo thực tế hệ thống:

- Cấu hình quan trọng đã nạp và được kiểm tra, dữ liệu khởi tạo bắt buộc đã sẵn sàng.
- Thành phần cục bộ mà mọi request cần sử dụng (ví dụ một bảng tra cứu nạp một lần) đã dựng xong.
- Instance có đủ năng lực để nhận request mới; nếu hệ thống chủ động draining/bảo trì thì nên chuyển sang unready.
- Những dependency bên ngoài thật sự cần để **xử lý hầu hết request** được đánh giá theo chiến lược chịu lỗi của hệ thống. Không đưa tất cả dependency vào liveness; và không tự động đưa mọi dependency dùng chung vào readiness nếu điều đó làm toàn bộ replica bị rút khỏi Service khi dịch vụ dùng chung chập chờn.

Có thể xây dựng **HealthIndicator riêng** rồi đưa vào readiness health group nếu cần kiểm tra điều kiện bổ sung, hoặc phát **AvailabilityChangeEvent** để điều khiển readiness trong những giai đoạn chủ động tạm dừng/resume. Việc điều chỉnh trạng thái phải được quản lý thống nhất để không có hai thành phần ghi đè nhau trái ý muốn.

Cú pháp minh họa **chỉ là lệnh bên trong một Bean đã có ApplicationContext**, không phải chương trình độc lập:

~~~java
AvailabilityChangeEvent.publish(
    applicationContext,
    ReadinessState.REFUSING_TRAFFIC
);
~~~

Muốn đưa instance trở lại phục vụ, phát **ReadinessState.ACCEPTING_TRAFFIC** sau khi xác nhận điều kiện đã phục hồi. Nếu chỉ cập nhật state trong một listener ApplicationReadyEvent nhưng sau đó Spring Boot vẫn phát ACCEPTING_TRAFFIC của chính nó, state bạn đặt có thể bị ghi đè; cần thiết kế đúng thời điểm và cơ chế sở hữu trạng thái.

## 8. Khi readiness đã UP nhưng request vẫn lỗi

Readiness là **tín hiệu nhận traffic**, không phải kiểm thử end-to-end cho từng chức năng. Có những tình huống:

| Hiện tượng | Giải thích có thể | Cần kiểm tra |
| --- | --- | --- |
| Cổng 8080 LISTEN, /readyz chưa trả 200 | Startup chưa xong, connector chưa xử lý request hoặc readiness REFUSING_TRAFFIC | Event startup, runner, probe status, timeout |
| /readyz 200, API quan trọng trả 500 | Logic API, dữ liệu, dependency hoặc security sai ngoài phạm vi readiness | Logs, traces, functional/smoke test, custom indicator |
| /actuator/health DOWN, /readyz UP | Global health và readiness group đo những tập điều kiện khác nhau | Thành phần health group, status mapping |
| /readyz 404 | Probes chưa bật, path/context-path khác hoặc gọi nhầm cổng | application.yml, Actuator dependency, URL đang dùng |
| /readyz 401/403 | Endpoint bị chặn bởi lớp bảo mật | SecurityFilterChain và cấu hình access phù hợp |
| Management health UP nhưng cổng web chính không nhận kết nối | Management chạy ở port/stack khác | /readyz trên main port, network/connector |
| Pod ready nhưng bên ngoài chưa truy cập được | Route, Service selector, ingress, gateway hoặc chính sách mạng chưa đúng | Pod condition, EndpointSlice, Service, ingress, TLS |
| Instance unready sau khi đã phục vụ | Chủ động draining, bảo trì hoặc readiness indicator thất bại | ReadinessChangeEvent, downstream, pod events |

Khi dựng dashboard, nên tách riêng: **thời gian khởi động JVM**, **thời điểm web server initialized**, **thời điểm ApplicationReadyEvent**, **lần đầu readiness probe thành công**, **thời điểm Pod Ready**, và **lần đầu kiểm thử nghiệp vụ thành công**. Đây là những mốc có thể chênh nhau do probe cadence và hệ thống mạng.

## 9. Quy trình kiểm tra khi triển khai

1. **Xác nhận đối tượng:** process/container nào, host nào, port chính nào, có proxy/management port riêng không.
2. **Xác nhận server:** kiểm tra log web server initialized, socket LISTEN và kết nối vào đúng cổng. Điều này chỉ xác nhận bước mạng.
3. **Xác nhận lifecycle:** quan sát ApplicationStartedEvent, trạng thái runner, ApplicationReadyEvent và ReadinessState.ACCEPTING_TRAFFIC. Đừng gộp chúng thành một mốc.
4. **Xác nhận probe HTTP:** gọi đúng /readyz hoặc /actuator/health/readiness, lưu HTTP status/body, thời gian chờ và các lỗi TLS/security.
5. **Xác nhận orchestrator:** trên Kubernetes dùng kubectl describe pod, xem Events/Conditions, kiểm tra endpoint đã ready; sự kiện Pod Ready có thể đến sau thời điểm app tự báo ready.
6. **Xác nhận nghiệp vụ:** thực hiện smoke test nhỏ với endpoint thật, phụ thuộc thiết yếu, dữ liệu tối thiểu và quyền hợp lệ.
7. **Xác nhận khi ngừng phục vụ:** khi rolling update hoặc shutdown, readiness nên chuyển sang REFUSING_TRAFFIC và hệ thống dừng đưa traffic mới trước khi process dừng; cấu hình graceful shutdown, thời gian drain và propagation của load balancer phải phù hợp.

Một lệnh kiểm tra trạng thái trong Kubernetes (thay giá trị namespace và tên deployment/pod theo hệ thống đang dùng):

~~~bash
kubectl get pods -n my-namespace
kubectl describe pod my-pod -n my-namespace
kubectl get endpointslices -n my-namespace
~~~

Các lệnh này chỉ minh họa đối tượng cần xem; tên namespace/pod thực tế do môi trường triển khai quyết định. “Pod Running” và “Pod Ready” là hai condition khác nhau: Running không chứng minh readiness probe đã thành công.

## 10. Lỗi thiết kế phổ biến và cách sửa

**Lỗi 1 — Đánh dấu ready ngay khi thấy server bind cổng.** Hệ thống gửi traffic trong lúc runner còn chạy hoặc dữ liệu chưa nạp. **Sửa:** dùng readiness endpoint dựa trên ApplicationAvailability, thêm điều kiện thiết yếu nếu cần, kiểm tra sau ApplicationReadyEvent/AvailabilityChangeEvent.

**Lỗi 2 — Dùng liveness thay readiness.** DB quá tải làm liveness fail, Kubernetes restart tất cả container, khiến sự cố lan rộng. **Sửa:** liveness phản ánh sức khỏe nội bộ; readiness quyết định nhận traffic; cân nhắc failover/circuit breaker cho phụ thuộc bên ngoài.

**Lỗi 3 — Dùng TCP probe cho ứng dụng HTTP có startup phức tạp.** Port mở là success dù Controller chưa sẵn sàng. **Sửa:** dùng HTTP readiness probe với đường dẫn có ngữ nghĩa.

**Lỗi 4 — Dùng /actuator/health tổng quát làm readiness mà không xét indicator.** Một dependency không bắt buộc chập chờn kéo toàn bộ instance ra khỏi Service. **Sửa:** định nghĩa readiness health group phù hợp nghiệp vụ, có timeout và chiến lược degrade.

**Lỗi 5 — Chạy công việc startup quan trọng bằng fire-and-forget sau runner.** Runner trả về nhanh, framework báo ready khi khởi tạo thật vẫn chưa xong. **Sửa:** nếu công việc là bắt buộc trước traffic, hãy đợi nó kết thúc trong startup phase có timeout hợp lý hoặc chủ động quản lý readiness tới khi hoàn tất.

**Lỗi 6 — Nhầm endpoint management với cổng nghiệp vụ.** Health chạy trên cổng quản trị riêng vẫn UP trong khi connector phục vụ request đã hỏng. **Sửa:** expose probe phù hợp trên cổng chính và kiểm tra end-to-end nhỏ ngoài probe.

**Lỗi 7 — Cho rằng ready nghĩa là mọi request sẽ thành công.** Readiness chỉ quyết định có nên định tuyến; từng request còn có thể lỗi do dữ liệu, security, dependency, backpressure và bug. **Sửa:** kết hợp readiness với test nghiệp vụ, metrics, logging, tracing và cảnh báo lỗi.

**Lỗi 8 — Mặc định unready thì container tự restart.** Kubernetes readiness failure làm Pod không nhận traffic từ Service, còn restart là trách nhiệm liveness/startup failure hoặc lifecycle khác. **Sửa:** chọn probe đúng cho hậu quả mong muốn.

## 11. Bài tập tự kiểm tra

1. Một ứng dụng đã in WEB_SERVER_INITIALIZED nhưng runner đang tạo dữ liệu cache 15 giây. Có nên đưa Pod vào Service chưa? **Chưa**, nếu cache là điều kiện bắt buộc. Hãy chờ readiness probe thành công.
2. Một Pod trả GET /api/ping = 200 nhưng readiness probe trả thất bại. Kubernetes có định tuyến traffic qua Service đến Pod đó không? **Không**, khi Pod đã được đánh dấu unready và bị rút khỏi tập endpoint, dù ping thủ công vào IP Pod có thể vẫn thành công.
3. Có một lỗi API khiến 10% request thất bại nhưng readiness vẫn UP. Điều này có mâu thuẫn không? **Không**. Readiness không đảm bảo mọi chức năng; cần kiểm thử và quan sát lỗi nghiệp vụ.
4. Sau ApplicationStartedEvent, LivenessState.CORRECT nhưng ReadinessState.REFUSING_TRAFFIC. Đây có phải trạng thái lỗi không? **Không**; đây là khoảng thời gian khởi động được thiết kế để chưa nhận traffic.
5. Sau ApplicationReadyEvent, một event listener lập tức đọc ReadinessState. Vì sao có thể chưa thấy ACCEPTING_TRAFFIC? **Vì Spring Boot phát sự kiện đổi readiness sau ApplicationReadyEvent**; quan sát AvailabilityChangeEvent nếu cần dấu mốc trạng thái chính xác.

## 12. Kết luận

**Cổng mở** chỉ chứng minh một phần hạ tầng mạng. **ApplicationStartedEvent** nói context đã refresh và startup tiến tới giai đoạn runner. **ApplicationReadyEvent** xuất hiện khi runner hoàn tất; **ReadinessState.ACCEPTING_TRAFFIC** là tín hiệu availability sau đó. **Readiness probe** giúp nền tảng triển khai quyết định có chuyển traffic đến instance, còn **smoke test nghiệp vụ** chứng minh các đường chức năng quan trọng đang hoạt động.

Khi kiểm tra startup của Spring Boot, hãy lấy bằng chứng tại đúng tầng: **socket → HTTP → lifecycle → availability → orchestrator → nghiệp vụ**. Không thay thế sáu câu hỏi đó bằng một lần kiểm tra “port 8080 mở”.

## Tài liệu tham khảo chính thức

- Spring Boot 3.3 — SpringApplication, Application Events, Application Availability: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Boot 3.3 — Actuator endpoints, Kubernetes probes, lifecycle states: https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html
- Spring Boot 3.3 — Common application properties: https://docs.spring.io/spring-boot/3.3/appendix/application-properties/
- Kubernetes — Configure liveness, readiness and startup probes: https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/
