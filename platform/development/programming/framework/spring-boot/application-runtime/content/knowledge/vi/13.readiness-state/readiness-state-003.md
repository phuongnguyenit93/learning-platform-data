# ReadinessState.ACCEPTING_TRAFFIC và REFUSING_TRAFFIC trong Spring Boot

## 1. Readiness trả lời câu hỏi gì?

Trong vận hành một ứng dụng Spring Boot, **tiến trình vẫn còn sống** và **tiến trình sẵn sàng nhận request mới** là hai thuộc tính khác nhau.

Ví dụ: một service đã khởi tạo Spring ApplicationContext nhưng vẫn đang tải dữ liệu tra cứu bắt buộc, làm nóng cache hoặc thực hiện các startup runners. JVM có thể hoạt động bình thường, nhưng nếu bộ cân bằng tải đưa request nghiệp vụ vào quá sớm thì request có thể thất bại. Ngược lại, khi một instance đang quá tải hoặc chuẩn bị đóng, service có thể cần tạm ngừng nhận traffic mới dù các tiến trình bên trong vẫn vận hành bình thường.

Spring Boot biểu diễn quyết định này bằng **ReadinessState** (package **org.springframework.boot.availability**). Enum có hai giá trị:

- **ReadinessState.ACCEPTING_TRAFFIC:** ứng dụng tự báo rằng mình **đã sẵn sàng và sẵn lòng nhận traffic**.
- **ReadinessState.REFUSING_TRAFFIC:** ứng dụng tự báo rằng mình **chưa sẵn sàng hoặc đang chủ động từ chối nhận traffic mới**.

Tín hiệu này có ích cho **container orchestrator**, **Kubernetes readinessProbe**, **load balancer** và hạ tầng điều phối lưu lượng. Nó không tự bảo đảm nghiệp vụ đúng, không thay thế cơ chế health checks đầy đủ và cũng **không tự ngắt kết nối HTTP** khi chuyển sang REFUSING_TRAFFIC.

**Quy tắc cốt lõi:** readiness là lời tuyên bố **có nên route request mới tới instance này lúc này hay không**, không phải lệnh kết thúc process.

## 2. Readiness khác liveness như thế nào?

Spring Boot có hai nhóm availability độc lập về ý nghĩa:

| Thuộc tính | Readiness | Liveness |
| --- | --- | --- |
| API | **ReadinessState** | **LivenessState** |
| Câu hỏi | Instance có nên nhận traffic mới không? | Instance có còn ở trạng thái có thể tiếp tục hoạt động/khôi phục không? |
| Giá trị | **ACCEPTING_TRAFFIC**, **REFUSING_TRAFFIC** | **CORRECT**, **BROKEN** |
| Khi kiểm tra thất bại ở Kubernetes | Bỏ instance khỏi danh sách endpoint sẵn sàng để route traffic | Kubelet có thể restart container sau khi đạt ngưỡng lỗi |
| Tình huống tiêu biểu | Khởi động chưa xong, service tạm quá tải, chuẩn bị shutdown | Deadlock/điều kiện nội bộ không thể tự hồi phục |
| Khi hệ thống DB bên ngoài tạm lỗi | Có thể giảm readiness nếu DB là dependency bắt buộc | Thường **không** đánh BROKEN chỉ vì DB bên ngoài lỗi |
| Mục tiêu | Giữ service sống nhưng ngăn nhận việc mới khi chưa phù hợp | Khôi phục tiến trình đã không còn vận hành đúng |

Một instance có thể cùng lúc mang **LivenessState.CORRECT** và **ReadinessState.REFUSING_TRAFFIC**. Đó là tình huống hợp lệ: process vẫn khỏe nhưng chưa nên đưa traffic vào.

Nếu biến lỗi của database dùng chung thành liveness failure ở tất cả replicas, Kubernetes có thể restart hàng loạt pods, làm hệ thống mất ổn định hơn. Việc đưa dependency ngoài vào readiness cũng phải cân nhắc: khi toàn bộ replicas cùng phụ thuộc một DB đang hỏng, toàn bộ service có thể bị rút khỏi routing; một số ứng dụng lại có thể phục vụ chế độ degraded với fallback.

## 3. Thứ tự readiness trong lifecycle Spring Boot

Theo Spring Boot 3.5, khi startup thành công, readiness chuyển từ chưa sẵn sàng sang chấp nhận traffic **sau khi các startup runners hoàn tất**.

~~~text
SpringApplication.run(args)
        |
        v
Chuẩn bị Environment và ApplicationContext
        |
        v
Tạo bean, refresh context
        |
        +--> ContextRefreshedEvent
        |
        v
ApplicationStartedEvent
        |
        +--> LivenessState.CORRECT
        |
        v
ApplicationRunner / CommandLineRunner
        |      Seed dữ liệu, kiểm tra cấu hình,
        |      warm-up bắt buộc...
        |      Readiness vẫn REFUSING_TRAFFIC
        |
        v
ApplicationReadyEvent
        |
        +--> AvailabilityChangeEvent(
        |      ReadinessState.ACCEPTING_TRAFFIC)
        |
        v
SpringApplication.run(...) trả về
        |
        v
Ứng dụng tiếp tục vận hành
~~~

Các mốc quan trọng:

1. **Trong quá trình starting:** readiness mặc định được xem là **REFUSING_TRAFFIC**. ApplicationContext và web server có thể chưa sẵn sàng.
2. **Sau ApplicationStartedEvent, khi runner đang chạy:** liveness thường đã **CORRECT**, nhưng readiness vẫn **REFUSING_TRAFFIC**.
3. **Sau khi tất cả ApplicationRunner/CommandLineRunner hoàn tất bình thường:** Boot phát **ApplicationReadyEvent**.
4. **Ngay sau ApplicationReadyEvent:** Boot công bố availability event với **ReadinessState.ACCEPTING_TRAFFIC**.
5. **Nếu runner ném exception không xử lý:** startup thất bại; Boot không hoàn tất trình tự Ready thông thường.
6. **Khi shutdown/graceful shutdown:** Spring Boot chuyển readiness sang **REFUSING_TRAFFIC** trong quá trình ngừng nhận công việc mới, nếu đã cấu hình và runtime hỗ trợ các bước shutdown tương ứng.

Mốc **ApplicationReadyEvent** và việc công bố **ReadinessState.ACCEPTING_TRAFFIC** không phải cùng một lệnh: Spring Boot phát availability event **ngay sau** ready event. Trong listener đang xử lý ApplicationReadyEvent, không nên mặc định rằng availability state mới đã được công bố xong.

**Không dùng @PostConstruct để kết luận app đã ready.** @PostConstruct chỉ là initialization callback của một bean; nhiều bean hoặc runner khác vẫn có thể chưa hoàn thành.

## 4. Hai trạng thái readiness có tác động gì?

### ACCEPTING_TRAFFIC

State này nghĩa là instance **muốn được coi là ready để nhận request**. Trong mô hình Kubernetes chuẩn, readiness probe thành công giúp instance được đưa vào tập endpoints sẵn sàng của Service theo cơ chế cập nhật của Kubernetes.

Điều này **không cam kết**:

- Mọi dependency bên ngoài đều đang khỏe.
- Mọi key trong cache đã tồn tại.
- Tất cả traffic mới sẽ đến ngay lập tức.
- Hệ thống thực sự phân phối đều request tới mọi instance.
- Mọi request đều trả HTTP 200.

Đây là một tín hiệu phục vụ routing, không phải một chứng nhận chất lượng nghiệp vụ.

### REFUSING_TRAFFIC

State này nghĩa là instance **không muốn nhận traffic mới**. Khi readiness probe phản ánh state này là không healthy, hạ tầng như Kubernetes sẽ loại instance khỏi nhóm ready endpoints sau khi trạng thái được quan sát và xử lý.

Cần hiểu rõ giới hạn:

- **HTTP listener thường vẫn mở**. Nếu gọi trực tiếp vào IP/port của instance, request nghiệp vụ vẫn có thể được phục vụ tùy ứng dụng.
- **Không kill hoặc restart JVM** chỉ vì readiness false. Đó không phải semantics của readiness.
- **Không đóng các kết nối đang xử lý** theo lệnh state; graceful shutdown có các cơ chế riêng để xử lý in-flight requests.
- Không bảo đảm việc ngừng route có hiệu lực tức thì; probe period, thresholds, controller/load balancer propagation và connection reuse có độ trễ.
- Nếu không có orchestrator hoặc readiness-aware proxy, đổi state có thể chỉ làm thay đổi thông tin nội bộ và Actuator probe.

Do đó câu **"REFUSING_TRAFFIC thì mọi HTTP request trực tiếp đều bị trả 503" là sai**. Mã 503 trong ví dụ dưới đây đến từ **Actuator readiness endpoint** theo cơ chế mapping health status, không phải middleware tự động chặn mọi URL nghiệp vụ.

## 5. Các API thường dùng

Spring Boot cung cấp ba thành phần chính:

| API | Vai trò |
| --- | --- |
| **ReadinessState** | Enum mô tả hai trạng thái có/không chấp nhận traffic |
| **ApplicationAvailability** | Đọc liveness/readiness hiện tại từ bean Spring |
| **AvailabilityChangeEvent** | Sự kiện công bố thay đổi availability state |

Trong bean Spring đã được khởi tạo, có thể inject:

~~~java
import org.springframework.boot.availability.ApplicationAvailability;
import org.springframework.boot.availability.ReadinessState;

public final class StateReader {
    private final ApplicationAvailability availability;

    public StateReader(ApplicationAvailability availability) {
        this.availability = availability;
    }

    public ReadinessState currentReadiness() {
        return availability.getReadinessState();
    }
}
~~~

Đây là **class Java minh họa**; cần tạo/inject nó thông qua Spring nếu muốn chạy như bean, không phải chương trình có main. Lời gọi **getReadinessState()** trả trạng thái mà availability component hiện đang ghi nhận.

Với code chạy cực sớm trước khi Spring Boot phát readiness event đầu tiên, API tổng quát **getState(ReadinessState.class)** có thể trả **null** nếu chưa có event; khi cần giá trị fallback, dùng:

~~~java
ReadinessState state = availability.getState(
        ReadinessState.class, ReadinessState.REFUSING_TRAFFIC);
~~~

Đây là mảnh code đặt trong method có biến **availability**. Không dùng null để tự suy diễn instance đã sẵn sàng.

### Công bố state mới

Spring Boot 3.5 JavaDoc hỗ trợ hai overload rõ ràng:

~~~java
// Khi đã có ApplicationContext:
AvailabilityChangeEvent.publish(
        applicationContext, ReadinessState.REFUSING_TRAFFIC);

// Khi chỉ có ApplicationEventPublisher:
AvailabilityChangeEvent.publish(
        eventPublisher, this, ReadinessState.ACCEPTING_TRAFFIC);
~~~

Hai đoạn chỉ minh họa method calls, không phải chương trình đầy đủ; biến applicationContext và eventPublisher phải được inject/định nghĩa. **Overload thứ hai cần ba tham số: publisher, source, state.** Không viết nhầm thành publish(eventPublisher, state).

Với cấu hình event multicaster đồng bộ mặc định, component quản lý availability nhận sự kiện và cập nhật state để Actuator readiness indicator phản ánh. Nếu ứng dụng tùy biến cơ chế publish/listener bất đồng bộ, việc quan sát state tức thời trong cùng luồng cần được kiểm thử lại.

## 6. Ví dụ Java 17+ chạy được: đổi readiness và xem HTTP probe

Ví dụ dưới đây tạo một Spring Boot HTTP service có:

- **GET /demo/readiness:** xem ReadinessState trong ApplicationAvailability.
- **POST /demo/readiness/refuse:** phát AvailabilityChangeEvent với REFUSING_TRAFFIC.
- **POST /demo/readiness/accept:** phát AvailabilityChangeEvent với ACCEPTING_TRAFFIC.
- **GET /actuator/health/readiness:** probe Actuator thật, trả HTTP status theo trạng thái readiness.

Ví dụ dùng **Spring Boot 3.5.x và Java 17+**. Các endpoint POST chỉ dành cho thử nghiệm trên máy phát triển. **Không triển khai các endpoint điều khiển readiness công khai trong production**; cần xác thực/phân quyền và logic điều khiển rõ ràng.

### 6.1. Tạo project

Tạo project Maven bằng Spring Initializr, group **com.example**, artifact **readiness-demo**, package **com.example.demo**, Java 17+, Spring Boot 3.5.x. Chọn:

- **Spring Web**
- **Spring Boot Actuator**

Phần dependencies chính trong POM do Initializr tạo:

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

Đây chỉ là **phần dependencies** trong POM hoàn chỉnh, không phải một pom.xml đứng riêng. Dùng parent/BOM của Spring Boot do Initializr cung cấp để quản lý dependency versions.

### 6.2. File Java hoàn chỉnh

Tạo file **src/main/java/com/example/demo/ReadinessDemoApplication.java**:

~~~java
package com.example.demo;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.availability.ApplicationAvailability;
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.ApplicationContext;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class ReadinessDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReadinessDemoApplication.class, args);
    }

    @RestController
    static class ReadinessController {
        private final ApplicationAvailability availability;
        private final ApplicationContext applicationContext;

        ReadinessController(
                ApplicationAvailability availability,
                ApplicationContext applicationContext) {
            this.availability = availability;
            this.applicationContext = applicationContext;
        }

        @GetMapping("/demo/readiness")
        public Map<String, String> getReadiness() {
            return Map.of(
                    "readiness",
                    availability.getReadinessState().name());
        }

        @PostMapping("/demo/readiness/refuse")
        public ResponseEntity<Void> refuseTraffic() {
            AvailabilityChangeEvent.publish(
                    applicationContext, ReadinessState.REFUSING_TRAFFIC);
            return ResponseEntity.noContent().build();
        }

        @PostMapping("/demo/readiness/accept")
        public ResponseEntity<Void> acceptTraffic() {
            AvailabilityChangeEvent.publish(
                    applicationContext, ReadinessState.ACCEPTING_TRAFFIC);
            return ResponseEntity.noContent().build();
        }
    }
}
~~~

**Vì sao mã này phù hợp?**

- **ApplicationAvailability** là bean do Boot cung cấp để đọc availability state hiện tại.
- **ApplicationContext** hỗ trợ overload **AvailabilityChangeEvent.publish(ApplicationContext, state)** của Boot 3.5; đây là overload chính xác theo JavaDoc.
- **ReadinessController** là nested static class có **@RestController**, được component scan của ứng dụng phát hiện.
- Hai POST endpoints chỉ publish **availability event**; chúng không dừng HTTP server hoặc đổi liveness state.
- **ResponseEntity.noContent().build()** trả HTTP 204 cho thao tác công bố state; không cố gắng diễn giải HTTP 204 là trạng thái readiness. Probe cần được gọi riêng.

Code trên là **file Java hoàn chỉnh** trong project có dependencies tương ứng. Không thể biên dịch riêng bằng javac nếu không đưa Spring Boot/Framework libraries vào classpath; Maven Wrapper sẽ xử lý điều này.

### 6.3. Bật Actuator readiness probe

Tạo file **src/main/resources/application.properties**:

~~~properties
server.port=8080

# Bật health probes ngay cả khi chạy local, ngoài Kubernetes.
management.endpoint.health.probes.enabled=true

# Health endpoint là HTTP endpoint được expose.
management.endpoints.web.exposure.include=health

# Không hiển thị thông tin chi tiết của health checks công khai.
management.endpoint.health.show-details=never
~~~

Với cấu hình này và Spring Boot 3.5, Actuator cung cấp health groups:

- **/actuator/health/liveness**
- **/actuator/health/readiness**

**management.endpoint.health.probes.enabled=true** là điểm quan trọng để bài demo có probes trong môi trường local. Khi Spring Boot phát hiện môi trường Kubernetes, probes thường được bật tự động. Không cần tách management port cho demo; endpoint nằm trên port **8080** cùng ứng dụng.

### 6.4. Chạy và quan sát ACCEPTING_TRAFFIC

Trong thư mục gốc project:

~~~bash
# Linux/macOS
./mvnw spring-boot:run

# Windows PowerShell hoặc CMD dùng:
# .\mvnw.cmd spring-boot:run
~~~

Sau khi ứng dụng khởi động thành công và log báo ready, mở terminal thứ hai:

~~~bash
curl -i http://localhost:8080/actuator/health/readiness
curl -i http://localhost:8080/demo/readiness
~~~

Các kết quả dự kiến theo cấu hình mặc định:

~~~text
GET /actuator/health/readiness
HTTP/1.1 200
{"status":"UP"}

GET /demo/readiness
HTTP/1.1 200
{"readiness":"ACCEPTING_TRAFFIC"}
~~~

Đây là **phần status và body được rút gọn** để tập trung vào nội dung; curl thực tế có thể hiển thị HTTP version cụ thể, nhiều headers và định dạng JSON khác. Điều cần kiểm tra là **200/UP** ở Actuator và **ACCEPTING_TRAFFIC** ở endpoint demo.

Nếu máy dùng Windows PowerShell, nên gọi **curl.exe** thay vì alias **curl** cũ của Windows PowerShell; lệnh trên theo cú pháp curl CLI.

### 6.5. Chuyển sang REFUSING_TRAFFIC

Gửi yêu cầu POST tới endpoint demo:

~~~bash
curl -i -X POST http://localhost:8080/demo/readiness/refuse
curl -i http://localhost:8080/actuator/health/readiness
curl -i http://localhost:8080/demo/readiness
~~~

Với listener mặc định của Spring Boot và health status mapping mặc định:

~~~text
POST /demo/readiness/refuse
HTTP/1.1 204

GET /actuator/health/readiness
HTTP/1.1 503
{"status":"OUT_OF_SERVICE"}

GET /demo/readiness
HTTP/1.1 200
{"readiness":"REFUSING_TRAFFIC"}
~~~

**Điểm học quan trọng:**

- Readiness health group chuyển sang **OUT_OF_SERVICE** và Actuator trả **HTTP 503** theo mặc định, báo hiệu probe thất bại.
- **/demo/readiness** vẫn có thể được gọi trực tiếp và trả HTTP 200. Readiness state **không tự chặn tất cả controller endpoints**.
- Liveness vẫn có thể là CORRECT; thử **GET /actuator/health/liveness** thường nhận HTTP 200/UP khi ứng dụng còn khỏe.
- Nếu có Kubernetes readinessProbe, kubelet sẽ quan sát probe và cập nhật trạng thái Pod Ready theo lịch kiểm tra, không phải ngay lập tức chỉ vì client vừa gọi POST.

### 6.6. Chuyển lại ACCEPTING_TRAFFIC

~~~bash
curl -i -X POST http://localhost:8080/demo/readiness/accept
curl -i http://localhost:8080/actuator/health/readiness
curl -i http://localhost:8080/demo/readiness
~~~

Dự kiến:

~~~text
POST /demo/readiness/accept
HTTP/1.1 204

GET /actuator/health/readiness
HTTP/1.1 200
{"status":"UP"}

GET /demo/readiness
HTTP/1.1 200
{"readiness":"ACCEPTING_TRAFFIC"}
~~~

Việc publish trạng thái ACCEPTING_TRAFFIC phải dựa trên **điều kiện nghiệp vụ và dependency đã thật sự sẵn sàng**. Trong demo, nút điều khiển được gọi bằng HTTP chỉ để quan sát; production không nên cho một request tùy tiện ép instance báo ready.

### 6.7. Giới hạn và lưu ý bảo mật

- Các POST endpoints chỉ dùng **local demo**; khi triển khai thật, cần **authentication, authorization**, kiểm soát audit, rate limiting và chính sách tránh state flapping.
- Trên hệ thống có Spring Security, behavior của endpoint có thể thay đổi; các curl minh họa giả định **không cài Spring Security**.
- Không giả định chính xác thứ tự HTTP headers, tên phiên bản protocol hoặc logging.
- Actuator health endpoint nên chỉ expose dữ liệu cần thiết; **không bật show-details=always** trên mạng công cộng nếu có nguy cơ lộ thông tin về infrastructure.
- Nếu project dùng management context/port khác, URLs và cấu hình probe cần điều chỉnh.

## 7. Actuator chuyển readiness state thành health status ra sao?

Spring Boot Actuator hỗ trợ **ReadinessStateHealthIndicator** và health group **readiness**. Nhóm này đọc giá trị readiness từ **ApplicationAvailability**.

Ánh xạ trong cấu hình mặc định:

| ReadinessState | Readiness health status | HTTP status của readiness probe |
| --- | --- | --- |
| **ACCEPTING_TRAFFIC** | **UP** | **200** |
| **REFUSING_TRAFFIC** | **OUT_OF_SERVICE** | **503** |

Cột HTTP mô tả **Actuator readiness probe trong Spring Boot với mặc định**. Có thể cấu hình status mapping hoặc thêm health indicators khiến kết quả khác. Nó **không** nói mọi URL trong ứng dụng sẽ trả status giống thế.

### Health root và readiness group khác nhau

**/actuator/health** là health endpoint tổng quát. **/actuator/health/readiness** là một health group. Trong project có JDBC, messaging hoặc nhiều HealthIndicator khác, root health có thể DOWN do một dependency, nhưng readiness group **mặc định không nhất thiết bao gồm dependency ấy**.

Nếu cần thêm indicator riêng:

~~~properties
management.endpoint.health.group.readiness.include=readinessState,customCheck
~~~

Đây là cú pháp **minh họa**. Muốn cấu hình hoạt động, phải có HealthIndicator với id **customCheck**, xác định đúng dependency và phiên bản Spring Boot. Đừng chép property này vào demo nếu chưa tạo customCheck; endpoint readiness có thể gặp lỗi cấu hình hoặc cho kết quả không mong đợi.

Khi cần thay đổi logic readiness, có hai lựa chọn với ý nghĩa khác nhau:

- **Publish AvailabilityChangeEvent:** chủ động thay đổi trạng thái willingness-to-accept-traffic do ứng dụng quản lý.
- **Thêm custom HealthIndicator vào readiness group:** bổ sung điều kiện kiểm tra khi probe được gọi (ví dụ một dependency nội bộ thiết yếu).

Đừng thêm tất cả health indicators vào readiness group chỉ vì có sẵn. Một hệ thống vẫn có thể phục vụ có ích khi một dependency tùy chọn đang lỗi.

## 8. Kubernetes readinessProbe: sử dụng đúng hai trạng thái

Một ví dụ cấu hình container trong Pod template:

~~~yaml
containers:
  - name: readiness-demo
    image: example/readiness-demo:1.0.0
    ports:
      - containerPort: 8080
    readinessProbe:
      httpGet:
        path: /actuator/health/readiness
        port: 8080
      periodSeconds: 5
      timeoutSeconds: 2
      failureThreshold: 2
    livenessProbe:
      httpGet:
        path: /actuator/health/liveness
        port: 8080
      periodSeconds: 10
      timeoutSeconds: 2
      failureThreshold: 3
~~~

Đoạn YAML là **một fragment của PodSpec**, không phải manifest Kubernetes hoàn chỉnh. Image, port và thresholds cần điều chỉnh theo môi trường triển khai. Nó giả định ứng dụng có Actuator health probes trên main port 8080 và không có security rule chặn kubelet.

**Kubernetes xử lý như sau:**

1. Kubelet gọi **/actuator/health/readiness** theo chu kỳ.
2. Khi probe thành công đủ điều kiện, Pod có trạng thái Ready và có thể được chọn làm endpoint phục vụ Service.
3. Khi probe thất bại, Pod bị coi là chưa sẵn sàng để route traffic mới sau ngưỡng/thời gian quan sát.
4. Container **không bị restart chỉ vì readiness probe thất bại**; liveness hoặc các cơ chế lỗi khác mới thường quyết định restart.
5. Khi chuyển lại ACCEPTING_TRAFFIC và probe thành công, Pod có thể được đưa lại vào tập endpoints.

**Một nuance quan trọng:** nếu tất cả replicas đều REFUSING_TRAFFIC, Service không còn ready endpoints. Client có thể thấy lỗi kết nối, lỗi từ ingress hoặc 503 tùy cách load balancer/proxy triển khai. **Đừng hứa mọi client chắc chắn nhận 503** trong trường hợp này.

### Khi management port khác main server port

Nếu chạy Actuator ở port riêng, health probe có thể trả UP dù **main HTTP connector** bị lỗi và không nhận request. Spring Boot có tùy chọn:

~~~properties
management.endpoint.health.probes.add-additional-paths=true
~~~

Nó cung cấp thêm các đường dẫn **/livez** và **/readyz** trên main server port theo cấu hình mặc định, giúp probe kiểm tra hạ tầng HTTP gần với đường phục vụ request thật. Phương án cụ thể còn phụ thuộc network policy, management endpoints và Spring Boot version.

### Ứng dụng startup lâu

Khi tải dữ liệu lớn hoặc chạy migrations kéo dài, hãy cân nhắc **startupProbe** nếu livenessProbe có nguy cơ kill container trước khi ứng dụng đạt mốc startup hợp lệ. StartupProbe sẽ cho tiến trình đủ thời gian khởi động theo chính sách riêng; readiness vẫn kiểm soát routing.

Không kéo dài startup vô hạn chỉ để đạt ready. Đặt deadline, error handling và quan sát thời gian khởi động thực tế.

## 9. Chủ động chuyển sang REFUSING_TRAFFIC khi runtime xuống cấp

Spring Boot tự quản lý state lúc startup/shutdown. Trong runtime, ứng dụng có thể chủ động phát readiness event để từ chối traffic mới khi một điều kiện thiết yếu không đáp ứng.

Một ví dụ phương thức trong Spring-managed service:

~~~java
public void onRequiredCacheUnavailable() {
    AvailabilityChangeEvent.publish(
            applicationContext, ReadinessState.REFUSING_TRAFFIC);
}
~~~

Đây là **mảnh code minh họa**, giả định service có ApplicationContext được inject. Khi cache được sửa xong và đã xác minh nhất quán, service có thể publish lại ACCEPTING_TRAFFIC.

Tuy nhiên, logic thực tế cần có:

- **Điều kiện chuyển sang refusing:** ví dụ dữ liệu thiết yếu không thể đọc, queue nội bộ quá tải hoặc instance cần drain.
- **Điều kiện phục hồi:** kiểm tra lại dependency hoạt động và trạng thái nội bộ ổn định.
- **Hysteresis/debounce:** tránh liên tục chuyển nhận/từ chối traffic theo từng lỗi ngắn.
- **Backoff và retry:** phục hồi có kiểm soát, không tạo bão truy vấn tới dependency.
- **Observability:** metric, structured log và tracing để tìm hiểu vì sao state thay đổi.
- **An toàn khi có nhiều instances:** tránh cho tất cả replicas đồng thời tự REFUSING nếu hệ thống vẫn có thể phục vụ degraded.
- **Security:** chỉ một bộ điều khiển đáng tin được quyền thay đổi trạng thái.

**ReadinessState không lưu vĩnh viễn qua restart.** Nó là trạng thái trong memory của instance đang chạy. Mỗi lần khởi động, Spring Boot tự đi qua chuỗi availability states mới theo lifecycle.

## 10. Vì sao không nên điều khiển readiness quá sớm trong ApplicationRunner?

Một bẫy phổ biến:

~~~java
@Bean
ApplicationRunner launchWarmup(
        ApplicationContext context, Executor executor) {
    return args -> {
        executor.execute(this::warmUpSlowly);
        AvailabilityChangeEvent.publish(
                context, ReadinessState.REFUSING_TRAFFIC);
    };
}
~~~

Đây chỉ là **mảnh pseudocode/Java minh họa** (chưa khai báo warmUpSlowly và bean Executor). Runner tạo tác vụ async rồi **trả về ngay**. Sau khi tất cả runners trả về, Spring Boot vẫn thực hiện chuỗi mặc định: **ApplicationReadyEvent**, tiếp theo là **ReadinessState.ACCEPTING_TRAFFIC**. Vì vậy trạng thái REFUSING_TRAFFIC mà runner vừa phát có thể bị **ghi đè bởi event startup mặc định**, trong khi warm-up vẫn chưa xong!

**Cách đúng nếu warm-up là điều kiện bắt buộc trước ready:**

- Chạy warm-up đồng bộ trong runner hoặc **đợi CompletableFuture/Future hoàn tất với timeout** trước khi runner trả về.
- Nếu warm-up thất bại và ứng dụng không được phép phục vụ, runner ném exception phù hợp để startup fail rõ ràng; không tự ép ACCEPTING.
- Nếu bắt buộc dùng startup bất đồng bộ nhưng vẫn kiểm soát readiness, thiết kế một custom HealthIndicator/readiness gate phản ánh tiến độ hoặc cơ chế sau-ready để quản lý state, và kiểm thử race giữa các events.
- Nếu warm-up chỉ tối ưu tốc độ, có thể xem là **best effort**, startup chấp nhận traffic và dùng fallback cho cache misses.

Một **ApplicationRunner hoàn tất** chỉ chứng minh chính phương thức run đã return, không chứng minh các tác vụ async tự tạo đã hoàn thành.

## 11. Readiness trong graceful shutdown

Spring Boot hỗ trợ graceful shutdown cho các web server được hỗ trợ khi bật:

~~~properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=30s
~~~

Đây là tùy chọn cấu hình Spring Boot 3.5; thời gian 30 giây là ví dụ và phải phù hợp với chính sách hạ tầng. Khi tiến trình nhận tín hiệu shutdown và bắt đầu đóng context:

1. Boot báo instance đang đi vào trạng thái từ chối traffic mới.
2. Kubernetes hoặc load balancer có thể rút instance ra khỏi routing dựa trên readiness/probe.
3. Graceful shutdown xử lý các request đang in-flight trong giới hạn server và timeout đã cấu hình.
4. Context và HTTP connector lần lượt được đóng, tài nguyên được giải phóng.

Trình tự hiển thị ra bên ngoài có thể khác vì readiness probe có chu kỳ và HTTP server có thể đóng trong quá trình shutdown. **Không kỳ vọng luôn truy vấn được /actuator/health/readiness để nhìn thấy REFUSING_TRAFFIC trong lúc shutdown**.

State không phải cơ chế trì hoãn request theo thời gian cố định. Nếu cần bảo đảm drain, kết hợp graceful shutdown, terminationGracePeriodSeconds, preStop hook (khi cần), ứng dụng và hạ tầng load balancer.

## 12. Lỗi thường gặp và cách sửa

| Hiểu nhầm / lỗi | Giải thích đúng |
| --- | --- |
| **REFUSING_TRAFFIC sẽ kill ứng dụng** | Sai; nó thể hiện không muốn nhận traffic, không phải liveness/restart |
| **Đổi readiness là đóng socket 8080** | Sai; đây là state phục vụ routing/probe |
| **ACCEPTING_TRAFFIC nghĩa là mọi DB/API đều khỏe** | Sai; chỉ phản ánh readiness theo chính sách hiện hành |
| **ApplicationStartedEvent nghĩa là ready** | Sai; runners còn chưa chạy |
| **ApplicationReadyEvent và availability ACCEPTING là một event** | Sai; Boot phát readiness event ngay sau ready event |
| **Liveness DOWN do DB lỗi là cách an toàn** | Có thể gây restart hàng loạt; cần đánh giá đúng readiness/dependency |
| **Actuator readiness mặc định gồm mọi HealthIndicator** | Không; group readiness mặc định gắn với readiness state, tùy cấu hình |
| **GET trực tiếp một business endpoint phải trả 503 khi refusing** | Sai; Actuator readiness probe mới phản ánh status; controller có thể vẫn chạy |
| **Publish refusing trong runner async là đủ** | Không; ready event mặc định có thể ghi đè trạng thái nếu runner return sớm |
| **Kubernetes rút traffic ngay tức thì** | Probe, thresholds, endpoint updates và proxy routing cần thời gian |
| **Có thể tự publish ACCEPTING để sửa lỗi startup** | Không; state chỉ là tín hiệu, dependency thực tế vẫn phải hoạt động |
| **Actuator luôn có /actuator/health/readiness** | Cần dependency Actuator, health probes enabled và đường dẫn/port phù hợp |
| **Dùng GET để đổi readiness** | Dễ bị crawler/cache/probe kích hoạt; thao tác thay đổi state nên dùng POST và bảo vệ |
| **Readiness và liveness đều có hai trạng thái cùng nghĩa** | Cả hai có hai enum constants nhưng mục tiêu và hệ quả hạ tầng khác nhau |

## 13. Các tình huống thực tế để quyết định trạng thái

### Trường hợp A — Đang chạy startup runner đồng bộ

Một instance đang tải danh mục bắt buộc. Spring Boot chưa phát ApplicationReadyEvent và **REFUSING_TRAFFIC** vẫn phù hợp. Không cần tự publish ACCEPTING khi runner mới chạy một nửa.

### Trường hợp B — Mất kết nối DB bắt buộc ở runtime

Nếu mọi request quan trọng đều cần DB và không có fallback, readiness có thể chuyển sang REFUSING_TRAFFIC trong thời gian DB không khả dụng. Nhưng nếu DB dùng chung và mọi replicas cùng unready, toàn bộ service có thể bị rút khỏi traffic; cần so sánh với phương án trả lỗi có kiểm soát hoặc degraded mode. Không đổi liveness thành BROKEN chỉ vì DB bên ngoài tạm lỗi.

### Trường hợp C — Hệ thống email ngoài lỗi, nhưng API chính vẫn hoạt động

Nếu email là chức năng phụ và đã có queue/retry, readiness vẫn có thể là ACCEPTING_TRAFFIC. Đánh instance unready chỉ vì phụ thuộc không thiết yếu lỗi có thể gây gián đoạn không cần thiết.

### Trường hợp D — Quá tải tạm thời

Instance có thể tạm REFUSING_TRAFFIC để được rút khỏi routing, nhưng phải có tiêu chí tải, debounce và tự phục hồi. Với lưu lượng lớn, các cơ chế load shedding, concurrency limit và circuit breaker cũng có thể cần thiết vì readiness probe không phản ứng tức thời.

### Trường hợp E — Rolling deployment và graceful shutdown

Instance cũ chuẩn bị dừng và công bố không nhận việc mới; instance mới cần qua readiness trước khi được route. Kết hợp rolling update strategy và số replicas sẵn có giúp giảm downtime, nhưng trạng thái sẵn sàng không tự bảo đảm zero-downtime nếu tất cả replicas bị rút hoặc các kết nối lâu dài chưa được xử lý.

## 14. Bài tập tự kiểm tra

**Bài 1.** Một instance có **LivenessState.CORRECT** và **ReadinessState.REFUSING_TRAFFIC**. Đây có phải trạng thái mâu thuẫn không?

**Bài 2.** Sau ApplicationStartedEvent, runner mất 20 giây để seed DB. Trong khoảng đó readiness mặc định là gì? Khi runner thành công, event nào xảy ra trước khi Boot báo accepting?

**Bài 3.** Đang REFUSING_TRAFFIC, gọi thẳng **GET /demo/readiness** trong ví dụ vẫn được HTTP 200. Vì sao không mâu thuẫn với kết quả HTTP 503 từ **/actuator/health/readiness**?

**Bài 4.** Một ứng dụng publish REFUSING_TRAFFIC rồi nghĩ Kubernetes sẽ restart pod. Cách nghĩ đó có đúng không?

**Bài 5.** Tại sao không nên đưa mọi check external database vào livenessProbe?

**Bài 6.** Trong Runner, code submit Future rồi return ngay, trước đó publish REFUSING_TRAFFIC. Sau Runner, Boot có thể làm gì khiến trạng thái đó không còn giữ nguyên?

**Bài 7.** Khi cần kiểm tra readiness trên main port dù Actuator ở management port riêng, có thể dùng cấu hình nào?

**Bài 8.** Nếu tất cả replicas đều REFUSING_TRAFFIC, có chắc client nhận HTTP 503 từ ứng dụng không?

**Đáp án gợi ý:**

1. Không: process sống nhưng chưa nhận việc.
2. REFUSING_TRAFFIC; **ApplicationReadyEvent** đến sau runner, tiếp theo là availability ACCEPTING_TRAFFIC.
3. State không tự chặn controllers; Actuator health group ánh xạ readiness sang OUT_OF_SERVICE/503.
4. Không: readiness kiểm soát routing, liveness mới thường kích hoạt restart.
5. Vì sự cố dependency dùng chung dễ gây restart hàng loạt và cascading failures.
6. Boot phát ApplicationReadyEvent rồi ACCEPTING_TRAFFIC, có thể ghi đè refusing trước đó.
7. **management.endpoint.health.probes.add-additional-paths=true**, sau đó dùng đường dẫn /readyz trên main port theo cấu hình mặc định.
8. Không; lỗi thực tế có thể đến từ Service/Ingress/load balancer hoặc thậm chí là không kết nối được.

## 15. Checklist vận hành readiness

- [ ] Đã định nghĩa rõ điều kiện **được nhận traffic mới**.
- [ ] Phân biệt **readiness** (route) với **liveness** (restart).
- [ ] Runners có kết thúc các công việc bắt buộc trước ready, không chỉ submit async rồi return?
- [ ] Đã bật và kiểm tra Actuator readiness probe phù hợp với environment?
- [ ] Probe đang kiểm tra đúng port/path và không bị chặn bởi bảo mật?
- [ ] Không expose endpoint điều khiển readiness chưa xác thực?
- [ ] Đã đánh giá external dependencies nào thật sự phải làm readiness fail?
- [ ] Có retry, timeout, hysteresis và metrics để chống state flapping?
- [ ] Không coi REFUSING_TRAFFIC là lệnh đóng socket hoặc dừng JVM?
- [ ] Đã thử rollout, restart, dependency outage và graceful shutdown trong staging?
- [ ] Đã cân đối probe period, failure thresholds và connection-draining delay?
- [ ] Không ràng buộc readiness vào tất cả các dịch vụ ngoài nếu app có thể dùng fallback?

## 16. Tổng kết và tài liệu tham khảo

**ReadinessState.ACCEPTING_TRAFFIC** nghĩa là instance báo có thể nhận request mới. **ReadinessState.REFUSING_TRAFFIC** nghĩa là instance báo không nên được route request mới vào thời điểm này. Hai trạng thái được Spring Boot quản lý theo lifecycle và có thể được ứng dụng cập nhật qua **AvailabilityChangeEvent**.

Chuỗi ghi nhớ:

~~~text
Startup / runner chưa xong  -> REFUSING_TRAFFIC
ApplicationReadyEvent      -> Boot công bố ACCEPTING_TRAFFIC
Runtime temporarily unready-> REFUSING_TRAFFIC (khi app chủ động đổi)
Runtime recovered          -> ACCEPTING_TRAFFIC (khi đã xác minh)
Graceful shutdown          -> REFUSING_TRAFFIC
~~~

**Readiness là tín hiệu phục vụ điều phối, không phải một bộ chặn HTTP request tự động.** Dùng Actuator probes và orchestrator/load balancer để hiện thực hóa tác dụng trên routing.

Tài liệu chính thức, đối chiếu với phiên bản Spring Boot 3.5:

1. Spring Boot — SpringApplication / Application Availability / startup events: https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html
2. Spring Boot API — ReadinessState enum: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/availability/ReadinessState.html
3. Spring Boot API — AvailabilityChangeEvent.publish overloads: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/availability/AvailabilityChangeEvent.html
4. Spring Boot API — ApplicationAvailability: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/availability/ApplicationAvailability.html
5. Spring Boot Actuator — Endpoints / Kubernetes Probes / Application Lifecycle: https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html

Ví dụ dùng **Spring Boot 3.5.x, Spring Framework 6.x và Java 17+**. Nếu dùng Spring Boot 4.x hoặc custom web management/security configuration, hãy đối chiếu JavaDoc và application properties đúng version để tránh nhầm API, URL hoặc HTTP status mapping.