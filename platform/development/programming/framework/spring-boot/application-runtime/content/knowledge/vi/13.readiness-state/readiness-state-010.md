# Liên hệ giữa startupProbe, livenessProbe và readinessProbe trong Spring Boot trên Kubernetes

## 1. Ba probe giải quyết ba câu hỏi khác nhau

Kubernetes có ba loại **container probe** phổ biến để quyết định một container đã khởi động hay chưa, cần restart hay có nên được định tuyến request mới. Trong dự án Spring Boot, Spring Boot Actuator thường cung cấp các HTTP health endpoints để kubelet thực hiện những phép kiểm tra này.

Ba câu hỏi cốt lõi:

1. **startupProbe:** Ứng dụng đã vượt qua giai đoạn khởi động ban đầu đến mức có thể bắt đầu kiểm tra liveness/readiness bình thường chưa?
2. **livenessProbe:** Ứng dụng còn đang vận hành hợp lệ không, hay đã rơi vào trạng thái nên **khởi động lại container**?
3. **readinessProbe:** Ứng dụng hiện tại có **sẵn sàng nhận traffic mới** từ Kubernetes Service không?

Không nên dùng ba probe như ba cách gọi tên khác nhau của cùng một phép kiểm tra. Chúng có **tần suất**, **hậu quả khi thất bại** và **mốc lifecycle** khác nhau.

| Probe | Mục đích | Khi kiểm tra thất bại liên tiếp tới ngưỡng | Khi kiểm tra thành công |
| --- | --- | --- | --- |
| **startupProbe** | Cho ứng dụng có thời gian khởi động | Kubelet chấm dứt container để restart theo restart policy | Chấm dứt giai đoạn kiểm tra startup; bắt đầu cho phép liveness/readiness probes chạy |
| **livenessProbe** | Phát hiện container mắc kẹt/không thể tự hồi phục | Kubelet restart container | Tiếp tục chạy; không tự làm Pod Ready |
| **readinessProbe** | Quyết định instance có nhận request từ Service không | Pod bị xem là chưa sẵn sàng; rút khỏi những Service endpoints tương ứng | Pod có thể được xem là Ready khi các điều kiện Pod/container khác cũng đáp ứng |

**Câu cần nhớ:** startup bảo vệ **thời gian khởi động**, liveness bảo vệ **khả năng tự hồi phục bằng restart**, readiness bảo vệ **định tuyến lưu lượng**.

Các phép kiểm tra này do **kubelet** thực hiện. Spring Boot không trực tiếp quyết định kubelet có restart Pod hay chọn endpoints cho Service; Boot chỉ cung cấp thông tin trạng thái hoặc endpoint mà Kubernetes có thể gọi.

## 2. Spring Boot cung cấp trạng thái nào cho Kubernetes?

Spring Boot mô hình hóa availability bằng API thuộc package **org.springframework.boot.availability**.

### 2.1. LivenessState

Hai giá trị:

- **LivenessState.BROKEN:** ứng dụng được đánh giá không ở trạng thái live đúng.
- **LivenessState.CORRECT:** ứng dụng được xem là live.

Khi triển khai với Actuator, trạng thái này được ánh xạ qua **LivenessStateHealthIndicator** thành liveness health group.

### 2.2. ReadinessState

Hai giá trị:

- **ReadinessState.REFUSING_TRAFFIC:** instance chưa nên nhận traffic mới.
- **ReadinessState.ACCEPTING_TRAFFIC:** instance cho biết nó đã sẵn sàng nhận traffic.

Actuator dùng **ReadinessStateHealthIndicator** để expose readiness health group.

### 2.3. Spring Boot không có StartupState tương đương

Điểm cực kỳ quan trọng: **startupProbe là cơ chế Kubernetes**, không phải một giá trị enum thứ ba của **ApplicationAvailability**. Spring Boot mặc định cung cấp hai nhóm trạng thái **liveness** và **readiness**, chứ không có một endpoint Actuator **/actuator/health/startup** mặc định chỉ vì Kubernetes hỗ trợ startupProbe.

Đừng nhầm **Actuator /actuator/startup** (endpoint quan sát các bước startup khi ứng dụng cấu hình ApplicationStartup phù hợp) với **một health probe dành cho kubelet**. Nó không phải một health group có status UP/DOWN tương ứng theo mặc định.

Trong nhiều ứng dụng Spring Boot, startupProbe có thể **gọi chính endpoint liveness** với ngân sách khởi động rộng hơn; readinessProbe sẽ tiếp tục kiểm tra điều kiện ready sau đó. Cách lựa chọn được giải thích ở mục 6.

## 3. Vòng đời Spring Boot và những lúc probe hoạt động

Trong Spring Boot 3.5, các availability state điển hình khi startup thành công:

~~~text
SpringApplication.run(args)
      |
      v
[STARTING]
  LivenessState.BROKEN
  ReadinessState.REFUSING_TRAFFIC
  Context / HTTP server đang được tạo
      |
      v
ApplicationContext.refresh()
      |
      v
ApplicationStartedEvent
  -> LivenessState.CORRECT
      |
      v
ApplicationRunner / CommandLineRunner
  (dữ liệu nền, warm-up, validation...)
  ReadinessState vẫn REFUSING_TRAFFIC
      |
      v
ApplicationReadyEvent
  -> ReadinessState.ACCEPTING_TRAFFIC
      |
      v
Ứng dụng vận hành và có thể xử lý traffic
      |
      v
Shutdown / graceful shutdown
  -> ReadinessState.REFUSING_TRAFFIC
  -> đóng web server, giải phóng tài nguyên
~~~

Các mốc Boot then chốt:

- **ApplicationStartedEvent:** xảy ra sau refresh nhưng trước runners. Boot phát **LivenessState.CORRECT** ngay sau event.
- **ApplicationReadyEvent:** xảy ra sau khi các runners hoàn tất. Boot phát **ReadinessState.ACCEPTING_TRAFFIC** ngay sau event.
- Trước đó, readiness được xem là **REFUSING_TRAFFIC**; một ứng dụng còn đang khởi tạo không tự nhiên được phép nhận traffic.
- Trong graceful shutdown, Boot bắt đầu từ chối traffic mới theo cơ chế runtime/shutdown hỗ trợ.

Đây là trạng thái **trong memory của ứng dụng**, không phải bằng chứng HTTP endpoint có thể truy cập được ở mọi thời điểm. Khi web server chưa bind cổng, kubelet có thể nhận lỗi kết nối thay vì JSON health status. Trong giai đoạn startup, một số web stacks có thể chưa chấp nhận request dù context đã tiến khá xa. Cần tách **availability state** và **probe có thể tiếp cận endpoint qua network**.

## 4. Điều kiện để Kubernetes thực sự dùng những trạng thái đó

Spring Boot chỉ báo **LivenessState.CORRECT** không tự bảo đảm Kubernetes biết điều này. Phải có ít nhất:

1. Dependency **Spring Boot Actuator** nếu dùng các health endpoints chuẩn.
2. Những health probe groups được bật và expose theo cấu hình.
3. HTTP listener, port, path và security/network policy cho phép **kubelet truy cập**.
4. **livenessProbe** và **readinessProbe** thích hợp trong PodSpec.
5. Nếu cần, **startupProbe** riêng với ngân sách thời gian khởi động hợp lý.

Spring Boot Actuator 3.5 cung cấp:

| Endpoint thường dùng | Kiểm tra | Mapping mặc định khi healthy | Mapping mặc định khi unhealthy |
| --- | --- | --- | --- |
| **/actuator/health/liveness** | **LivenessState** | CORRECT → **UP**, HTTP **200** | BROKEN → **DOWN**, HTTP **503** |
| **/actuator/health/readiness** | **ReadinessState** | ACCEPTING_TRAFFIC → **UP**, HTTP **200** | REFUSING_TRAFFIC → **OUT_OF_SERVICE**, HTTP **503** |

Các status/HTTP codes trong bảng là **mặc định của Actuator**. Nếu thêm health indicators hoặc tùy biến status mapping, kết quả có thể khác. Mã HTTP 503 ở readiness endpoint **không có nghĩa mọi business controller tự động trả 503** khi ứng dụng refusing.

Trong môi trường Kubernetes, Boot có thể tự bật liveness/readiness probe groups. Để kiểm tra trong local hoặc môi trường không được nhận diện là Kubernetes, đặt:

~~~properties
management.endpoint.health.probes.enabled=true
~~~

Nếu ứng dụng chạy Actuator management server riêng, cần phân biệt management port và main application port. Mục 9 giải thích cách đặt thêm **/livez** và **/readyz** trên main port để kiểm tra web infrastructure sát thực tế hơn.

## 5. Quan hệ giữa ba probe ở phía kubelet

Quy tắc vận hành quan trọng nhất của Kubernetes:

**Nếu container có startupProbe, kubelet không thực thi livenessProbe hoặc readinessProbe cho container đó cho tới khi startupProbe thành công.**

Sơ đồ:

~~~text
Container process được tạo
          |
          v
   Có startupProbe?
       /       \
     Không      Có
       |         |
       |         v
       |   Chạy startupProbe
       |         |
       |       Thành công? -- không --> tiếp tục retry
       |         |                     trong failure budget
       |        Có                            |
       |         |                   Thất bại đủ ngưỡng
       |         |                            |
       |         |                       restart container
       |         v
       +----> LivenessProbe và ReadinessProbe
                    chạy độc lập theo chu kỳ
                          |
           +--------------+---------------+
           |                              |
    Liveness thất bại               Readiness thất bại
    quá ngưỡng                      quá ngưỡng
           |                              |
    Restart container              Không route request
                                  qua Service endpoint
~~~

**StartupProbe chỉ có vai trò ở giai đoạn startup.** Sau khi lần đầu trả thành công, kubelet dừng sử dụng startupProbe trong vòng đời của container hiện tại và chuyển sang các liveness/readiness probes. Một service trở nên unready sau 20 phút **không** kích hoạt startupProbe chạy lại; readiness tiếp tục đánh giá trong toàn bộ vòng đời.

**ReadinessProbe và livenessProbe không chờ nhau thành công.** Không có startupProbe, cả hai có thể được gọi song song theo thời gian cấu hình. Việc readiness fail **không tự ngăn liveness chạy**; muốn trì hoãn liveness khi ứng dụng khởi động lâu, cân nhắc startupProbe hoặc initialDelaySeconds phù hợp.

## 6. Chọn endpoint cho startupProbe thế nào?

Đây là câu hỏi quan trọng khi thiết kế Spring Boot và Kubernetes cùng nhau.

### Lựa chọn A — StartupProbe gọi liveness endpoint

Với Spring Boot, đây là cách thường được tài liệu chính thức đề xuất khi cần bảo vệ **giai đoạn startup chậm**:

~~~yaml
startupProbe:
  httpGet:
    path: /actuator/health/liveness
    port: 8080
  periodSeconds: 5
  failureThreshold: 60

livenessProbe:
  httpGet:
    path: /actuator/health/liveness
    port: 8080
  periodSeconds: 10
  failureThreshold: 3

readinessProbe:
  httpGet:
    path: /actuator/health/readiness
    port: 8080
  periodSeconds: 5
  failureThreshold: 2
~~~

Đây là **fragment thuộc một container trong Kubernetes PodSpec**, không phải Deployment manifest hoàn chỉnh. Boot phải expose các paths trên port 8080 như cấu hình mô tả.

Cơ chế:

1. StartupProbe chờ HTTP liveness đạt **UP**. Trước thời điểm đó, liveness/readiness probes bị tạm hoãn.
2. Sau khi context refresh thành công và Boot phát **LivenessState.CORRECT**, startupProbe có thể bắt đầu thành công. **Không nhất thiết phải đợi runners đã hoàn tất**.
3. Từ đây readinessProbe bắt đầu chạy và tiếp tục nhận **OUT_OF_SERVICE/503** cho đến khi các startup runners kết thúc và Boot báo **ACCEPTING_TRAFFIC**.
4. Nếu liveness thật sự chuyển BROKEN về sau và fail đủ ngưỡng, kubelet có thể restart.

**Lợi thế:** phân biệt **"container đã qua giai đoạn khởi động để được kiểm tra sống/chết"** với **"ứng dụng sẵn sàng phục vụ"**. Một runner hợp lệ mất thêm vài chục giây sẽ không cần giả làm liveness failure; readiness đơn giản tiếp tục fail cho đến khi ready.

**Giới hạn:** nếu startupProbe thành công ngay khi Boot đã started nhưng một runner tiếp tục treo vô hạn, readiness có thể giữ REFUSING mãi trong khi liveness vẫn CORRECT. Không phải lỗi của startupProbe; bạn cần **deadline, timeout và failure policy của runner**, hoặc health/metrics để phát hiện stuck startup work.

### Lựa chọn B — StartupProbe gọi readiness endpoint

Có thể cấu hình startupProbe kiểm tra **/actuator/health/readiness** nếu điều kiện "startup succeeded" của container **được định nghĩa bằng startup tasks hoàn tất và readiness đã đạt**.

Tuy nhiên:

- StartupProbe lúc này sẽ không thành công cho đến khi **ApplicationReadyEvent** và trạng thái ACCEPTING_TRAFFIC hoặc custom readiness indicator trả healthy.
- Toàn bộ liveness/readiness probes sẽ tiếp tục bị trì hoãn trong thời gian đó.
- Nếu readiness phụ thuộc một hệ thống ngoài đang lỗi, container có thể bị startupProbe kill/restart liên tục do **không bao giờ đạt ready**, ngay cả khi tiến trình Spring Boot hoàn toàn còn sống. Đây có thể là thiết kế không mong muốn.

Vì vậy **không dùng startupProbe=readiness chỉ theo phản xạ**. Với Spring Boot, phương án startupProbe dùng **liveness** cộng readinessProbe riêng thường thể hiện ranh giới trách nhiệm rõ hơn.

### Lựa chọn C — Không cấu hình startupProbe

Nhiều ứng dụng không cần startupProbe. Spring Boot đã giữ readiness REFUSING_TRAFFIC cho đến khi runners hoàn tất, nên Kubernetes không đưa traffic qua Service vào Pod quá sớm. Nếu livenessProbe có khoảng thời gian đủ cho bootstrap thường lệ và không gây restart sai, có thể dùng **chỉ livenessProbe + readinessProbe**.

**StartupProbe hữu ích khi vấn đề là:** livenessProbe bắt đầu quá sớm, fail nhiều lần trong lúc JVM và Spring Boot vẫn khởi động bình thường, dẫn tới CrashLoopBackOff. Nó **không** phải thành phần bắt buộc của mọi Deployment.

## 7. Tính thời gian cho startupProbe và các ngưỡng

Các trường quan trọng của một HTTP probe:

- **periodSeconds:** chu kỳ kiểm tra.
- **timeoutSeconds:** thời gian chờ tối đa của mỗi lần probe.
- **failureThreshold:** số lần thất bại liên tiếp trước khi kubelet coi probe thất bại theo ngưỡng.
- **successThreshold:** ngưỡng thành công; liveness và startup không được cấu hình giá trị khác 1; readiness có thể cần nhiều lần thành công.
- **initialDelaySeconds:** chờ trước khi kubelet bắt đầu probe; với startupProbe thường không cần lạm dụng nếu đã có failure budget đủ.

Ví dụ:

~~~yaml
startupProbe:
  httpGet:
    path: /livez
    port: 8080
  periodSeconds: 5
  timeoutSeconds: 2
  failureThreshold: 60
~~~

Ngân sách khởi động thường được ước tính:

~~~text
failureThreshold × periodSeconds
= 60 × 5 giây
≈ 300 giây
~~~

Đây là **ước lượng cấu hình** chứ không phải lời hứa kubelet chắc chắn đợi chính xác 300 giây từ khi process khởi chạy: thời gian thực chịu ảnh hưởng scheduler, initial delay, thời gian mỗi probe, timeout và cách phân bố lần kiểm tra.

Nếu ứng dụng mất 40–60 giây để khởi động khi lạnh, hãy chọn budget dựa trên đo lường thực tế và margin phù hợp. **Không đặt failureThreshold cực lớn** chỉ để che deadlock hoặc lỗi config vĩnh viễn: hệ thống phải vẫn có giới hạn để khôi phục.

So sánh hai ngưỡng:

~~~text
startupProbe:  60 lần × 5 giây ≈ 300 giây ở startup
livenessProbe: 3 lần × 10 giây ≈ 30 giây sau startup
~~~

Mục đích là **rộng lúc khởi động**, **nhạy hơn khi đang vận hành**. Liveness failure budget vẫn phải tính tới GC pause, CPU throttling, sự chậm trễ network và khả năng đáp ứng của endpoint.

## 8. Ví dụ Spring Boot 3.5 / Java 17+ có thể chạy

Ví dụ tạo một web application đơn giản, có:

- **ApplicationRunner** giả lập việc khởi tạo mất khoảng 10 giây.
- **Actuator liveness/readiness probes**.
- **/livez** và **/readyz** trên main port.
- Một controller chỉ xuất hiện trong Spring profile **local-demo**, giúp thử chuyển readiness giữa ACCEPTING_TRAFFIC và REFUSING_TRAFFIC.
- Những lệnh curl quan sát HTTP status thực tế.

**Không copy các endpoint thay đổi readiness vào production khi không có kiểm soát bảo mật.** Demo tách chúng bằng profile và chỉ hướng dẫn bật trên localhost.

### 8.1. Project và dependencies

Tạo dự án Spring Initializr với:

- Maven, **Java 17 hoặc mới hơn**.
- Spring Boot **3.5.x**, group **com.example**, artifact **probe-demo**, package **com.example.demo**.
- Dependencies: **Spring Web**, **Spring Boot Actuator**.

Trong POM do Initializr tạo, các dependency chính:

~~~xml
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
~~~

Đây là **fragment POM**, cần dùng project Maven có Spring Boot parent/BOM và build plugin do Initializr cung cấp, không phải một file pom.xml độc lập.

Cấu trúc:

~~~text
probe-demo/
  pom.xml
  mvnw
  mvnw.cmd
  src/main/java/com/example/demo/ProbeDemoApplication.java
  src/main/resources/application.properties
~~~

### 8.2. File Java hoàn chỉnh

Tạo **src/main/java/com/example/demo/ProbeDemoApplication.java**:

~~~java
package com.example.demo;

import java.util.Map;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.availability.ApplicationAvailability;
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Profile;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class ProbeDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ProbeDemoApplication.class, args);
    }

    @Bean
    ApplicationRunner simulateSlowStartup(
            ApplicationAvailability availability,
            org.springframework.core.env.Environment environment) {
        return args -> {
            long millis = environment.getProperty(
                    "demo.startup-delay-ms", Long.class, 10_000L);

            System.out.println("RUNNER_BEGIN readiness="
                    + availability.getReadinessState());

            Thread.sleep(millis);

            System.out.println("RUNNER_END");
        };
    }

    @RestController
    @Profile("local-demo")
    static class LocalProbeController {

        private final ApplicationContext context;
        private final ApplicationAvailability availability;

        LocalProbeController(
                ApplicationContext context,
                ApplicationAvailability availability) {
            this.context = context;
            this.availability = availability;
        }

        @GetMapping("/demo/state")
        public Map<String, String> state() {
            return Map.of(
                    "liveness", availability.getLivenessState().name(),
                    "readiness", availability.getReadinessState().name());
        }

        @PostMapping("/demo/refuse")
        public ResponseEntity<Void> refuse() {
            AvailabilityChangeEvent.publish(
                    context, ReadinessState.REFUSING_TRAFFIC);
            return ResponseEntity.noContent().build();
        }

        @PostMapping("/demo/accept")
        public ResponseEntity<Void> accept() {
            AvailabilityChangeEvent.publish(
                    context, ReadinessState.ACCEPTING_TRAFFIC);
            return ResponseEntity.noContent().build();
        }
    }
}
~~~

**Lưu ý compile:** ví dụ dùng kiểu **Environment** bằng tên fully qualified **org.springframework.core.env.Environment**, nên có một dòng import **Value** chưa được sử dụng. Java cho phép unused imports và chương trình vẫn biên dịch; có thể bỏ import Value để code gọn hơn nhưng không ảnh hưởng hoạt động. Đừng nhầm với tên property expression của @Value.

**ApplicationRunner.run(...)** khai báo ném Exception nên lời gọi **Thread.sleep(millis)** trong lambda hợp lệ; nếu bị interrupt thì startup có thể thất bại, không nên âm thầm coi ứng dụng ready khi việc chuẩn bị bắt buộc chưa xong.

**AvailabilityChangeEvent.publish(ApplicationContext, ReadinessState)** là API Spring Boot 3.5. Nó thay đổi availability state do Boot quản lý; nó không đóng web socket và không tự gây restart.

**@Profile("local-demo")** giúp các POST endpoints chỉ được đăng ký khi bật profile local-demo. Tuy nhiên profile không phải cơ chế authentication; trong production không bật profile này hoặc expose những endpoints điều khiển state không được bảo vệ.

### 8.3. application.properties

Tạo **src/main/resources/application.properties**:

~~~properties
server.port=8080

# Bật health groups cả ngoài Kubernetes để test tại localhost.
management.endpoint.health.probes.enabled=true

# Expose HTTP health endpoint (không expose toàn bộ actuator).
management.endpoints.web.exposure.include=health

# Expose thêm probes trên main server port:
# /livez và /readyz
management.endpoint.health.probes.add-additional-paths=true

management.endpoint.health.show-details=never

# Thời gian startup runner giả lập, đơn vị milliseconds.
demo.startup-delay-ms=10000
~~~

Tại local, cả hai cách truy cập có thể dùng:

~~~text
http://localhost:8080/actuator/health/liveness
http://localhost:8080/actuator/health/readiness

http://localhost:8080/livez
http://localhost:8080/readyz
~~~

Khi management port tách biệt, **/livez** và **/readyz** được bổ sung trên main application port để giảm rủi ro probe management context báo healthy trong khi connector chính không nhận được request.

### 8.4. Build và chạy

Từ thư mục gốc project Spring Initializr:

~~~bash
# Build:
./mvnw package

# Chạy local demo, chỉ bind 127.0.0.1 để giảm phạm vi truy cập:
java -jar target/probe-demo-0.0.1-SNAPSHOT.jar --spring.profiles.active=local-demo --server.address=127.0.0.1
~~~

Windows PowerShell/cmd dùng **.\mvnw.cmd package** ở bước build. Nếu Initializr dùng artifact/version khác, thay đúng tên jar thật trong target.

Trong log, riêng hai dòng do runner tự in là:

~~~text
RUNNER_BEGIN readiness=REFUSING_TRAFFIC
RUNNER_END
~~~

Chúng cách nhau xấp xỉ 10 giây trong điều kiện thread không bị interrupt. Spring Boot và Maven có thể in thêm log; không khẳng định hai dòng nằm liền nhau trong toàn bộ stdout.

**Quan sát khi runner đang chạy:** ở thời điểm RUNNER_BEGIN, Boot đã refresh context nhưng chưa ready. ReadinessState được in là REFUSING_TRAFFIC. Tùy web server và tình trạng connector, gọi probe lúc này có thể nhận **503/OUT_OF_SERVICE** hoặc chưa truy cập được endpoint. Không coi lỗi kết nối ở đầu startup là lỗi của logic readiness.

### 8.5. Kiểm tra sau khi ứng dụng ready

Khi Spring Boot báo startup thành công, từ terminal thứ hai:

~~~bash
curl -i http://localhost:8080/livez
curl -i http://localhost:8080/readyz
curl -i http://localhost:8080/demo/state
~~~

Các status/body quan trọng (lược bỏ các HTTP headers không cần thiết):

~~~text
GET /livez
HTTP 200
{"status":"UP"}

GET /readyz
HTTP 200
{"status":"UP"}

GET /demo/state
HTTP 200
{"liveness":"CORRECT","readiness":"ACCEPTING_TRAFFIC"}
~~~

JSON object từ **Map.of** có thể xuất các keys theo thứ tự khác; chỉ kiểm tra giá trị từng field, không phụ thuộc thứ tự JSON.

### 8.6. Đổi readiness sang refusing, rồi phục hồi

Gọi endpoint demo:

~~~bash
curl -i -X POST http://localhost:8080/demo/refuse
curl -i http://localhost:8080/readyz
curl -i http://localhost:8080/livez
curl -i http://localhost:8080/demo/state
~~~

Trong cấu hình mặc định, kỳ vọng:

~~~text
POST /demo/refuse -> HTTP 204
GET  /readyz      -> HTTP 503, {"status":"OUT_OF_SERVICE"}
GET  /livez       -> HTTP 200, {"status":"UP"}
GET  /demo/state  -> HTTP 200,
                    {"liveness":"CORRECT","readiness":"REFUSING_TRAFFIC"}
~~~

Giải thích: **readiness** báo không muốn nhận traffic nên readinessProbe thất bại; **liveness** vẫn healthy nên Kubernetes không restart chỉ vì thay đổi này. URL **/demo/state** vẫn có thể được gọi trực tiếp và trả 200 vì REFUSING_TRAFFIC không phải bộ lọc tự động chặn controller.

Phục hồi:

~~~bash
curl -i -X POST http://localhost:8080/demo/accept
curl -i http://localhost:8080/readyz
curl -i http://localhost:8080/demo/state
~~~

Kết quả:

~~~text
POST /demo/accept -> HTTP 204
GET  /readyz      -> HTTP 200, {"status":"UP"}
GET  /demo/state  -> HTTP 200,
                     {"liveness":"CORRECT","readiness":"ACCEPTING_TRAFFIC"}
~~~

Chỉ nên publish ACCEPTING_TRAFFIC trong ứng dụng thật khi các điều kiện phục vụ đã đáp ứng. Demo cố tình cho phép kích hoạt thủ công để quan sát behavior, **không phải một mẫu quản trị production**.

## 9. Kubernetes Deployment: kết nối ba probe với Boot

Sau khi đóng gói ứng dụng vào một container image có khả năng nghe trên port **8080**, một Deployment mẫu có thể trông như sau:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: probe-demo
spec:
  replicas: 2
  selector:
    matchLabels:
      app: probe-demo
  template:
    metadata:
      labels:
        app: probe-demo
    spec:
      containers:
        - name: app
          image: registry.example.com/probe-demo:1.0.0
          ports:
            - name: http
              containerPort: 8080

          startupProbe:
            httpGet:
              path: /livez
              port: http
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 60

          livenessProbe:
            httpGet:
              path: /livez
              port: http
            periodSeconds: 10
            timeoutSeconds: 2
            failureThreshold: 3

          readinessProbe:
            httpGet:
              path: /readyz
              port: http
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 2
~~~

**Lưu ý:** địa chỉ image **registry.example.com/probe-demo:1.0.0** là ví dụ cấu trúc; cần build/push image thật và thay bằng registry/tag thật. Bài không chứa Dockerfile vì trọng tâm là startup/liveness/readiness probes, không phải quy trình container build. Không bật profile local-demo trong Deployment.

**Vì sao dùng /livez và /readyz?** Cấu hình application.properties ở mục 8 bật **management.endpoint.health.probes.add-additional-paths=true**, cho phép những endpoints này chạy trên **main HTTP server port**. Kubelet kiểm tra đường xử lý request gần với cổng ứng dụng thật.

**Vì sao startupProbe trỏ /livez mà không trỏ /readyz?** Mục tiêu là cho Boot đủ thời gian tới mốc liveness CORRECT mà không bị kill sớm. Sau đó readinessProbe tiếp tục đợi toàn bộ startup runners hoàn tất; việc app chưa ready không nhất thiết đồng nghĩa nó đã broken.

**Vì sao liveness và readiness có chu kỳ khác nhau?** Liveness restart là hành động tốn kém và có thể gây cascading failure; readiness có thể được kiểm tra thường xuyên hơn để kịp rút traffic. Cần tuning bằng dữ liệu thực tế thay vì copy ngưỡng cố định.

**Không sử dụng image/bản cấu hình ví dụ cho production** trước khi cân chỉnh CPU/memory requests, shutdown, security, Service, observability và ngân sách startup thực tế.

## 10. Startup probe không thay thế readiness probe

Một cách hiểu sai thường gặp: "Khi startupProbe báo thành công, Pod đã ready và không cần readinessProbe".

Sự thật:

- **StartupProbe success** chỉ xác nhận điều kiện do chính startupProbe kiểm tra.
- Nếu startupProbe trỏ **/livez**, nó có thể thành công khi Boot vừa started, trong khi **ApplicationRunner vẫn chạy** và readiness vẫn REFUSING_TRAFFIC.
- **ReadinessProbe** mới là thành phần kiểm tra có nên route traffic mới, bao gồm khả năng chuyển sang unready trong **runtime**.
- LivenessProbe cũng tiếp tục chạy sau startup và có nhiệm vụ riêng là phát hiện lỗi cần restart.

Sơ đồ thời gian ví dụ:

~~~text
0s  Container được tạo; Boot đang khởi động
    startupProbe (/livez): fail / connection refused
    liveness/readiness chưa chạy

18s ApplicationContext refresh xong
    ApplicationStartedEvent -> LivenessState.CORRECT
    startupProbe (/livez): thành công ở lần kiểm tra kế tiếp

20s LivenessProbe: /livez -> 200/UP
    ReadinessProbe: /readyz -> 503/OUT_OF_SERVICE
    Runner bắt đầu tải dữ liệu

33s Runner hoàn thành
    ApplicationReadyEvent
    ReadinessState.ACCEPTING_TRAFFIC

35s ReadinessProbe: /readyz -> 200/UP
    Pod có thể trở thành Ready và được đưa vào Service endpoints
~~~

**Các mốc giây là ví dụ giả định**, không phải số liệu đo hay cam kết Spring Boot luôn khởi động trong 18/33 giây. Thời điểm probe thực tế phụ thuộc periodSeconds, scheduling, tải máy và lifecycle của chương trình.

Một startupProbe trỏ /livez không thay nhiệm vụ của readinessProbe, cũng không có nghĩa request qua service tự động được route ngay sau mốc started.

## 11. Khi nào startupProbe thực sự cần thiết?

### Tình huống A — Spring Boot khởi động nhanh

Ứng dụng ổn định, context refresh và runner hoàn tất trong vài giây. LivenessProbe không gây restart trước khi Boot live. Có thể chỉ cần:

~~~yaml
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
~~~

Việc bỏ startupProbe giúp cấu hình đơn giản hơn. Cần quan sát thời gian startup ở cold deployments, không chỉ trên laptop.

### Tình huống B — Context refresh mất hai phút

Ví dụ classpath lớn, tạo nhiều singleton hoặc thực hiện initialization đắt đỏ. Nếu livenessProbe bắt đầu quá sớm và đủ lần fail, kubelet có thể restart trước khi ứng dụng khởi động xong. Một startupProbe với budget lớn hơn có thể ngăn vòng lặp restart sai.

Điều quan trọng là **startupProbe phải kiểm tra mốc mà app có thể đạt được nếu khởi động thành công**, và budget phải lớn hơn thời gian khởi động hợp lệ nhưng vẫn có giới hạn.

### Tình huống C — Runner warm-up kéo dài sau refresh

Spring Boot có thể đã live nhưng chưa ready. Trong khi runner chạy, **readinessProbe vẫn fail đúng thiết kế**. Thường không cần restart ứng dụng chỉ vì runner chưa hoàn thành. Nếu runner bị treo hoặc vượt deadline nghiệp vụ, chính runner cần timeout/failure policy để báo lỗi startup.

### Tình huống D — DB bên ngoài tạm lỗi

Nếu pod đã live nhưng dependency DB bắt buộc không thể phục vụ, readiness có thể thất bại theo chính sách. **Liveness không nên phụ thuộc trực tiếp vào DB**: restart tất cả replicas trong một sự cố DB dùng chung thường không chữa được nguyên nhân.

Nếu startupProbe trỏ readiness chứa DB check, outage của DB có thể làm startupProbe kill/restart liên tục. Cần phân biệt **không thể khởi động** với **đã khởi động nhưng không thể nhận traffic vì dependency chưa sẵn sàng**.

## 12. Tại sao không nên đưa mọi dependency vào liveness?

Tài liệu Spring Boot khuyến cáo **liveness không phụ thuộc vào trạng thái của hệ thống bên ngoài** như database, web API hoặc cache dùng chung. Lý do:

1. DB tạm thời lỗi.
2. Mọi pod đều báo liveness DOWN nếu liveness gắn với DB.
3. Kubernetes restart tất cả pod.
4. Nhiều pod đồng loạt tái kết nối, tái tải dữ liệu và cạnh tranh tài nguyên.
5. Hệ thống có thể chuyển từ một sự cố có thể phục hồi thành cascading failure.

Ngược lại, **readiness** có thể bao gồm dependency quan trọng khi instance không thể xử lý request nếu dependency đó lỗi. Nhưng cũng phải cân nhắc:

- Dependency dùng chung cho mọi replicas: toàn bộ Service có thể không còn ready endpoints nếu lỗi.
- Dependency tùy chọn: nên cân nhắc fallback/circuit breaker và giữ instance ready nếu vẫn phục vụ được chức năng chính.
- Dependency chỉ một pod đang lỗi: readiness check có thể giúp loại đúng pod khỏi routing.

Mặc định trong Spring Boot 3.5, Actuator **không tự thêm mọi HealthIndicator vào liveness/readiness groups**. Muốn thêm custom check vào readiness, cần cấu hình chủ động, ví dụ:

~~~properties
management.endpoint.health.group.readiness.include=readinessState,customCheck
~~~

Đây là **ví dụ cấu hình** khi project đã có một **HealthIndicator** với id **customCheck**. Nếu chưa định nghĩa indicator này, không thêm property vào demo. Chính sách probe phải phản ánh yêu cầu nghiệp vụ thực, tránh coi mọi lỗi ngoài hệ thống là lý do restart process.

## 13. Management port riêng có thể đánh lừa probe

Giả sử:

~~~properties
server.port=8080
management.server.port=8081
~~~

Actuator health endpoints trên port 8081 có thể tiếp tục trả UP dù main application port 8080 không chấp nhận request vì một vấn đề trong web connector hoặc connection pool.

Để giảm rủi ro đó, Spring Boot có tùy chọn:

~~~properties
management.endpoint.health.probes.add-additional-paths=true
~~~

Khi bật, probe health groups có thêm các đường dẫn **/livez** và **/readyz** trên **main application port** theo mặc định. Trong Kubernetes, hãy trỏ startup/liveness/readiness tới main port đó nếu muốn kiểm tra web infrastructure gần với người dùng cuối.

Cần chọn đường kiểm tra phù hợp với network policy và security settings. Không expose các Actuator endpoints nhạy cảm khác chỉ để làm health probes.

Một số tổ chức chọn management port tách biệt để giới hạn truy cập; vẫn có thể dùng management endpoints cho monitoring, đồng thời expose hai đường probe tối thiểu trên cổng chính.

## 14. StartupProbe, readiness và graceful shutdown

Trong rolling deployment, quá trình chuyển traffic thường cần ba giai đoạn:

~~~text
Pod mới:
  Start container
    -> startupProbe success
    -> readinessProbe success
    -> Pod mới tham gia Service endpoints

Pod đang chạy:
  livenessProbe tiếp tục kiểm tra khả năng sống
  readinessProbe phản ánh thay đổi khả năng phục vụ

Pod cũ bị terminate:
  readiness chuyển sang REFUSING_TRAFFIC
  -> Pod được rút khỏi Service endpoints theo quá trình cập nhật
  -> graceful shutdown xử lý request đang chạy
  -> container đóng
~~~

Spring Boot 3.5 cho phép cấu hình graceful shutdown:

~~~properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=30s
~~~

**Phân biệt:**

- Readiness false yêu cầu hạ tầng **ngừng route traffic mới**; propagation không xảy ra tức thì.
- Graceful shutdown quản lý **request đang xử lý** và đóng web server theo contract hỗ trợ.
- Kubernetes **terminationGracePeriodSeconds** giới hạn thời gian container được dừng lịch sự trước khi bị kill.
- Một **preStop hook** có thể được cân nhắc khi cần buffer cho load balancer cập nhật, nhưng phải thiết kế theo phương án shutdown thực tế.

Trong shutdown, endpoints có thể không còn truy cập được sau khi web server bắt đầu đóng, nên không nên yêu cầu chính HTTP probe luôn phải quan sát được trạng thái REFUSING_TRAFFIC trong từng mili giây.

## 15. HTTP probes khác với TCP và exec probes thế nào?

Kubernetes hỗ trợ các cơ chế kiểm tra khác nhau:

| Handler | Điều nó kiểm tra | Khi nào dùng |
| --- | --- | --- |
| **httpGet** | Kết nối và nhận HTTP response status phù hợp | Rất phù hợp với Actuator health groups |
| **tcpSocket** | Có thể thiết lập kết nối TCP tới port | Đơn giản nhưng chưa xác nhận ứng dụng đã ready |
| **exec** | Chạy command trong container và đọc exit code | Khi không có HTTP server hoặc cần kiểm tra nội bộ |
| **grpc** | Gọi gRPC health checking protocol | Khi ứng dụng expose gRPC health protocol phù hợp |

**TCP socket mở không có nghĩa ứng dụng đã hoàn tất startup runner.** Một Spring web server có thể bind port trước mốc ApplicationReadyEvent. Nếu readiness cần thể hiện điều kiện cấp ứng dụng, dùng **/actuator/health/readiness** hoặc một endpoint health có semantics tương đương thay vì chỉ TCP port.

HTTP probe thành công trong Kubernetes thường là status thuộc dải **200–399**. Các status như 503 hoặc lỗi không kết nối được là thất bại. Không nên coi mọi HTTP 3xx redirect do login page là tình huống đúng cho health probe; cấu hình security/path rõ ràng để kubelet truy cập endpoint thực.

## 16. Chẩn đoán lỗi probe bằng công cụ Kubernetes

Khi pod không Ready hoặc liên tục restart, tìm nguyên nhân đúng loại probe trước khi thay đổi thresholds.

Các lệnh thường dùng:

~~~bash
kubectl get pods
kubectl describe pod probe-demo-xxxxx
kubectl logs probe-demo-xxxxx -c app
kubectl logs probe-demo-xxxxx -c app --previous
kubectl get endpointslices -l kubernetes.io/service-name=probe-demo
~~~

Tên **probe-demo-xxxxx** chỉ minh họa dạng Pod name, cần thay bằng tên thật. Lệnh EndpointSlice cuối chỉ có ý nghĩa khi có Kubernetes Service tên **probe-demo** và nhãn EndpointSlice tương ứng.

### StartupProbe fails

Dấu hiệu: kubelet ghi **Startup probe failed** nhiều lần; container có thể bị restart và dẫn tới CrashLoopBackOff.

Kiểm tra:

- Spring Boot có vượt qua context refresh trước ngân sách startup không?
- Port/path đúng chưa, app có bind trên **0.0.0.0** khi chạy trong container không?
- Spring Actuator đã có mặt và probe groups được bật chưa?
- Security hoặc network policy có chặn kubelet không?
- startupProbe có đang kiểm tra readiness chứa external dependency thay vì chỉ liveness không?
- CPU throttling, DB connection wait, DNS và GC có làm startup quá chậm không?

### LivenessProbe fails

Dấu hiệu: log kubelet **Liveness probe failed** và restart dù container có thể còn process Java.

Kiểm tra:

- Đúng **/livez** hay bị nhầm **/readyz**?
- Liveness có phụ thuộc DB/API chung không?
- Server quá tải khiến health check timeout? Điều chỉnh resource/timeout và tìm nguyên nhân bottleneck.
- Có deadlock/blocked event loop hay thiếu worker threads khiến cả request lẫn probe không được phục vụ?

Không sửa bằng cách vô hiệu hóa liveness vô điều kiện nếu chương trình có deadlock thật.

### ReadinessProbe fails

Dấu hiệu: Pod có trạng thái chưa sẵn sàng nhưng **không nhất thiết restart**.

Kiểm tra:

- Runner hoặc initialization bắt buộc đã xong chưa?
- Có custom readiness indicator nào bị DOWN/OUT_OF_SERVICE không?
- ApplicationAvailability có đang REFUSING_TRAFFIC do logic nghiệp vụ hoặc shutdown không?
- Cấu hình **successThreshold/failureThreshold** khiến cập nhật Pod Ready chậm hơn kỳ vọng?
- Pod labels/Service selector và port có khớp không?

Đừng tăng startupProbe budget khi vấn đề thực tế là **readiness vĩnh viễn không trở lại UP do dependency lỗi**.

## 17. Bảng quyết định: chọn probe cho từng tình huống

| Tình huống | Probe cần chú ý | Hành động hợp lý |
| --- | --- | --- |
| JVM và context khởi động lạnh mất nhiều thời gian | **startupProbe** | Tăng startup budget có giới hạn, dùng liveness endpoint |
| App khởi động xong nhưng runner đang seed DB | **readinessProbe** | Giữ unready đến khi runner hoàn tất |
| Một instance deadlock không còn xử lý tiến trình | **livenessProbe** | Restart khi fail đủ ngưỡng |
| DB dùng chung tạm lỗi nhưng process còn khỏe | **readiness**, có cân nhắc fallback | Không đánh liveness BROKEN chỉ vì DB lỗi |
| Cache local bắt buộc của một pod chưa sẵn | **readinessProbe** | Không route tới pod đó, khởi tạo lại có kiểm soát |
| Một chức năng không thiết yếu bị lỗi | Có thể vẫn **ready** | Dùng fallback/circuit breaker thay vì rút toàn bộ pod |
| Rolling deploy cần tránh traffic vào pod chưa ready | **readinessProbe** | Phối hợp Deployment strategy và probes |
| Pod nhận SIGTERM và đang drain | **readiness + graceful shutdown** | Rút traffic mới, xử lý in-flight theo timeout |
| Actuator ở management port nhưng main port hỏng | **probe paths trên main port** | Bật additional-paths và kiểm tra /livez /readyz |
| Pod cứ restart sau 30 giây khi init mất 90 giây | **startupProbe** | Cho phép budget startup tương ứng, kiểm tra timeout thực tế |

## 18. Những hiểu lầm phổ biến

1. **"StartupProbe là bắt buộc với mọi Spring Boot application."** Không; hữu ích khi liveness bị thực thi quá sớm với ứng dụng khởi động chậm.
2. **"StartupProbe success nghĩa là app ready."** Không nếu nó kiểm tra liveness; runners có thể còn đang chạy.
3. **"StartupProbe chạy mãi trong suốt runtime."** Không; chỉ thực thi tới lần thành công đầu tiên của container.
4. **"ReadinessProbe thất bại sẽ restart container."** Không; nó thay đổi trạng thái được định tuyến qua Service, không trực tiếp kill process.
5. **"LivenessProbe cần đợi readiness trở thành true."** Không; hai probe độc lập sau khi startupProbe success.
6. **"ReadinessState.REFUSING_TRAFFIC tự đóng cổng HTTP."** Không; đây là availability state và Actuator health signal; việc chặn routing do hạ tầng đảm nhận.
7. **"Một port TCP mở là app đã ready."** Không; startup runners có thể còn chạy.
8. **"Tất cả dependencies nên đưa vào liveness."** Không; lỗi external dependency có thể gây restart dây chuyền.
9. **"Root /actuator/health và readiness health group hoàn toàn giống nhau."** Không; tập HealthIndicators và mục tiêu kiểm tra có thể khác.
10. **"Nếu Service không có ready Pod, mọi client chắc chắn được HTTP 503."** Không; có thể lỗi kết nối hoặc lỗi từ ingress/proxy tùy nền tảng.
11. **"Có Actuator là tự có mọi probes ở mọi môi trường."** Không; phải có dependency, exposure và kiểm tra probe groups theo cấu hình/phiên bản.
12. **"Đổi readiness từ HTTP test endpoint là pattern production an toàn."** Không; cần chính sách bảo mật và điều kiện chuyển state có kiểm soát.

## 19. Câu hỏi và bài tập

**Bài 1.** Ứng dụng Spring Boot cần 110 giây để refresh context. LivenessProbe bắt đầu sau 10 giây, gọi mỗi 10 giây và fail đủ ngưỡng khi app chưa bind cổng. Bạn nên thêm probe nào, kiểm tra endpoint nào và chọn budget theo nguyên tắc gì?

**Bài 2.** StartupProbe gọi /livez và đã thành công. Một ApplicationRunner vẫn đang warm-up trong 15 giây. ReadinessState điển hình là gì, và Kubernetes có nên route traffic qua Service vào pod đó không?

**Bài 3.** Sau khi app ready, một controller/health logic đánh readiness REFUSING_TRAFFIC nhưng liveness vẫn CORRECT. Container có bắt buộc restart không? Điều gì thay đổi ở Kubernetes Service?

**Bài 4.** Tại sao startupProbe trỏ /readyz có thể không phù hợp khi readiness group kiểm tra một DB dùng chung mà DB tạm lỗi?

**Bài 5.** Nếu Actuator đang ở port 8081 và application thật ở 8080, tại sao chỉ kiểm tra /actuator/health/readiness trên 8081 có thể tạo tín hiệu gây hiểu nhầm?

**Bài 6.** Khi muốn probe trạng thái Spring Boot readiness, dùng tcpSocket tới 8080 có đủ không? Vì sao?

**Bài 7.** Một pod đang graceful shutdown. Readiness chuyển REFUSING_TRAFFIC nhưng một request HTTP đang xử lý vẫn được phép hoàn tất. Điều đó có mâu thuẫn không?

**Bài 8.** Nêu một trường hợp mà không cần startupProbe nhưng vẫn nên có readinessProbe.

### Gợi ý đáp án

1. Cân nhắc **startupProbe** trỏ liveness path, chọn periodSeconds × failureThreshold đủ bao phủ startup hợp lệ có margin; đồng thời điều tra nguyên nhân refresh chậm.
2. Thường **REFUSING_TRAFFIC** cho đến runners hoàn tất; readinessProbe chưa đạt, Service không nên đưa traffic vào.
3. Không; readiness ảnh hưởng routing, còn liveness mới thường dẫn tới restart khi thất bại đủ ngưỡng.
4. DB outage có thể làm startupProbe không thành công rồi kubelet kill/restart ứng dụng sống bình thường; dùng liveness cho startup và readiness riêng thường hợp lý.
5. Management connector khỏe không bảo đảm main connector phục vụ được; bật additional probe paths trên main port.
6. Không; TCP chỉ xác nhận có thể kết nối cổng, không xác nhận readiness logic.
7. Không; readiness từ chối **traffic mới**, graceful shutdown cho phép xử lý **request đang chạy** theo chính sách.
8. Một service khởi động nhanh nhưng đôi khi cần rút khỏi routing khi mất cache local bắt buộc.

## 20. Checklist triển khai và ghi nhớ

- [ ] Đã phân biệt rõ **startup = cho phép khởi động**, **liveness = restart khi cần**, **readiness = nhận traffic**.
- [ ] Spring Boot Actuator có trên classpath nếu dùng health endpoints chuẩn?
- [ ] Liveness/readiness groups đã bật theo môi trường?
- [ ] Kubelet kiểm tra đúng **port**, **path**, HTTP scheme và security?
- [ ] Probe paths có trên main port khi management port tách biệt?
- [ ] StartupProbe chỉ được cấu hình khi có nhu cầu và có failure budget hợp lý?
- [ ] StartupProbe không vô tình phụ thuộc external readiness condition không ổn định?
- [ ] Liveness không phụ thuộc DB/cache/web API dùng chung?
- [ ] Readiness phản ánh các điều kiện **thật sự bắt buộc** để nhận request?
- [ ] Runners có timeout/failure handling, không return sớm khi tác vụ async bắt buộc chưa hoàn thành?
- [ ] Đã kiểm tra startup lạnh, CPU throttling, pod restart và rolling deployment?
- [ ] Đã kiểm tra liveness BROKEN và readiness REFUSING thực sự có hậu quả Kubernetes khác nhau?
- [ ] Graceful shutdown, terminationGracePeriodSeconds và load balancer draining tương thích?
- [ ] Không dùng endpoints debug thay đổi readiness không được bảo vệ ở production?

**Kết luận:** startupProbe, livenessProbe và readinessProbe là ba điều khiển **khác mục tiêu nhưng bổ sung nhau**. Spring Boot Actuator cung cấp hai nguồn tín hiệu availability chính, còn Kubernetes startupProbe là **cơ chế bảo vệ cửa sổ khởi động**. Một thiết kế phổ biến là **startupProbe → liveness endpoint**, **livenessProbe → liveness endpoint**, **readinessProbe → readiness endpoint**; điều chỉnh theo thời gian startup và điều kiện phục vụ thực tế.

### Tài liệu chính thức

1. Spring Boot 3.5 Reference — Actuator / Kubernetes Probes / Application Lifecycle: https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html
2. Spring Boot 3.5 Reference — SpringApplication events và Application Availability: https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html
3. Spring Boot 3.5 API — ApplicationAvailability: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/availability/ApplicationAvailability.html
4. Spring Boot 3.5 API — AvailabilityChangeEvent: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/availability/AvailabilityChangeEvent.html
5. Kubernetes — Liveness, Readiness and Startup Probes: https://kubernetes.io/docs/concepts/workloads/pods/probes/
6. Kubernetes — Configure Liveness, Readiness and Startup Probes: https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/

Ví dụ ứng dụng sử dụng **Java 17+ / Spring Boot 3.5.x**. YAML dùng cấu trúc Kubernetes phổ biến, nhưng cần kiểm tra API, cluster policies, network/security, registry và resource settings thực tế trước khi áp dụng.