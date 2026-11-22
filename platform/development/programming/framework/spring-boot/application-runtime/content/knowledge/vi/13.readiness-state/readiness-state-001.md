# Phân biệt liveness, readiness và khả năng mở cổng mạng

## 1. Ba câu hỏi không thể thay thế nhau

Khi một ứng dụng Spring Boot đang chạy, ba câu hỏi dưới đây thuộc ba tầng khác nhau:

1. **Liveness:** Ứng dụng còn ở trạng thái nội bộ có thể làm việc hoặc tự phục hồi không? Nếu trạng thái nội bộ không thể phục hồi, có nên restart instance?
2. **Readiness:** Instance hiện **có nên được gửi request mới** không? Nó có thể đang nạp dữ liệu, tạm quá tải hoặc đang dừng có kiểm soát, dù tiến trình vẫn sống.
3. **Khả năng mở cổng mạng:** Web server đã bind/listen cổng TCP chưa, và từ vị trí của client có kết nối được tới đúng host, port, protocol hay không?

Một instance có thể có **liveness = CORRECT** nhưng **readiness = REFUSING_TRAFFIC** trong khi Spring Boot đang chạy `ApplicationRunner`. Nó cũng có thể đã khởi tạo web server trên `8080` nhưng chưa đạt mốc ready. Ngược lại, TCP connect thành công không chứng minh controller xử lý được request hoặc dữ liệu nghiệp vụ đã sẵn sàng.

> **Port mở không có nghĩa ready; live không có nghĩa ready; một health endpoint trả 200 không tự chứng minh toàn bộ API và các dependency đang khỏe.**

Bài áp dụng cho Spring Boot 3.3.x, Spring Framework 6.1.x, Java 17+; đặc biệt giải thích `ApplicationAvailability`, probe của Actuator và định tuyến Kubernetes.

## 2. Bảng phân biệt ngữ nghĩa

| Tín hiệu | Câu hỏi trả lời | Giá trị/API thông dụng | Hệ thống thường làm gì? |
| --- | --- | --- | --- |
| **Liveness** | Nội bộ instance có hoạt động hợp lệ, không bị hỏng không thể phục hồi? | `LivenessState.CORRECT` / `BROKEN` | Kubernetes có thể restart container sau khi liveness probe thất bại đủ ngưỡng |
| **Readiness** | Instance có muốn nhận traffic mới bây giờ? | `ReadinessState.ACCEPTING_TRAFFIC` / `REFUSING_TRAFFIC` | Kubernetes thường rút instance khỏi endpoints nhận traffic khi readiness probe thất bại |
| **TCP bind/listen** | Socket ở một địa chỉ/cổng đã sẵn sàng nhận kết nối? | `server.address`, `server.port`, embedded web server | Chẩn đoán socket, firewall, NAT, Service targetPort |
| **HTTP response** | Một route trả được response? | `/ping`, controller, Actuator health | Kiểm tra khả năng xử lý một HTTP endpoint |
| **Business readiness** | Một thao tác thiết yếu đáp ứng hợp đồng nghiệp vụ? | HealthIndicator, synthetic transaction, SLO | Quyết định fallback, alert, traffic routing theo thiết kế |

**Liveness** nên mô tả lỗi nội bộ mà restart có khả năng giải quyết; nó không nên mặc định phụ thuộc database, cache, broker hay HTTP API bên ngoài. Nếu phụ thuộc chung bị hỏng, restart hàng loạt replica có thể gây cascading failure.

**Readiness** biểu diễn “hãy gửi traffic mới cho tôi hay chưa”, không đồng nghĩa “tôi đã chết”. Instance không ready vẫn có thể chạy background work hoặc chuẩn bị phục hồi.

**Port** là trạng thái socket/hạ tầng. Có kết nối TCP không bảo đảm HTTP endpoint trả 200; HTTP 200 từ `/ping` cũng không bảo đảm `/actuator/health/readiness` trả UP.

## 3. ApplicationAvailability của Spring Boot

Spring Boot 3.3 có bean `ApplicationAvailability` cung cấp trạng thái availability hiện tại:

```java
import org.springframework.boot.availability.ApplicationAvailability;
import org.springframework.boot.availability.LivenessState;
import org.springframework.boot.availability.ReadinessState;

// Trong bean Spring đã được inject ApplicationAvailability availability:
LivenessState liveness = availability.getLivenessState();
ReadinessState readiness = availability.getReadinessState();
```

Đây là **đoạn minh họa**, không phải file Java độc lập; `availability` phải được Spring inject.

`LivenessState` có `CORRECT` và `BROKEN`; `ReadinessState` có `ACCEPTING_TRAFFIC` và `REFUSING_TRAFFIC`. Các giá trị này là **thông tin trong runtime**; chúng không tự đóng/mở cổng mạng hoặc tự thay đổi toàn bộ cấu hình load balancer. Muốn bên ngoài quan sát, cần một cơ chế phơi bày như Actuator health groups và một bộ điều phối thực sự đọc probe.

Trong ứng dụng đang khởi động, Boot coi liveness chưa đạt cho tới khi context refresh và Boot công bố state tương ứng. Điều đó **không** có nghĩa “chưa live” nhất thiết là lỗi cần restart ngay lập tức: Kubernetes startupProbe/liveness probe thresholds quyết định lúc nào mới hành động.

## 4. Timeline: started khác ready

Với luồng khởi động thông thường của Spring Boot 3.3.x:

```text
SpringApplication.run(...)
   |
   +--> Chuẩn bị Environment, tạo ApplicationContext
   +--> Nạp bean definitions, refresh context
   |       +--> web server initialization nếu là web application
   |       +--> WebServerInitializedEvent/ContextRefreshedEvent
   |
   +--> log "Started ..." nếu bật startup INFO
   +--> ApplicationStartedEvent
   +--> AvailabilityChangeEvent(LivenessState.CORRECT)
   |
   +--> ApplicationRunner / CommandLineRunner
   |       (công việc cần hoàn tất trước ready)
   |
   +--> ApplicationReadyEvent
   +--> AvailabilityChangeEvent(ReadinessState.ACCEPTING_TRAFFIC)
   +--> return ApplicationContext
```

**Mốc started:** Context đã refresh; `ApplicationStartedEvent` xảy ra **trước** runner. Spring Boot công bố `LivenessState.CORRECT` ngay **sau** event started.

**Mốc ready:** Boot đã gọi xong các runner thành công; `ApplicationReadyEvent` xảy ra **sau** runner. Boot công bố `ReadinessState.ACCEPTING_TRAFFIC` ngay **sau** event ready.

Vì thế khi code đang nằm trong listener của `ApplicationReadyEvent`, giá trị readiness đọc ngay lập tức chưa nhất thiết là `ACCEPTING_TRAFFIC`: event cập nhật state theo thứ tự chuẩn đến **sau** event ready. Muốn quan sát chuyển trạng thái, nghe `AvailabilityChangeEvent<ReadinessState>` hoặc đọc sau khi `SpringApplication.run(...)` trả về.

Dòng log `Started ExampleApplication in ... seconds` không chứng minh runner đã hoàn tất. Nó không đồng nghĩa readiness UP. `WebServerInitializedEvent` cũng không phải `ApplicationReadyEvent`.

### 4.1. Trạng thái theo giai đoạn

| Giai đoạn | Liveness | Readiness | HTTP/server |
| --- | --- | --- | --- |
| **Starting** (chưa refresh) | `BROKEN` trong mô hình vòng đời trước mốc live | `REFUSING_TRAFFIC` | Server/probe có thể chưa truy cập được |
| **Started** (sau refresh, đang xử lý startup) | `CORRECT` | `REFUSING_TRAFFIC` | Web server có thể đã bind nhưng không xem là traffic-ready |
| **Ready** (sau runner) | `CORRECT` | `ACCEPTING_TRAFFIC` | Sẵn sàng được định tuyến khi probe và hạ tầng đồng ý |
| **Graceful shutdown** | Có thể vẫn `CORRECT` | `REFUSING_TRAFFIC` | Thường ngừng nhận request mới, xử lý in-flight tùy cấu hình |
| **Shutdown complete** | Không còn instance chạy | Không còn instance chạy | Cổng/server đã dừng |

Điều kiện HTTP connector và khả năng probe phản hồi có thể khác nhau theo giai đoạn, web server, mạng và cách deployment. Bảng này mô tả **trạng thái availability**, không phải cam kết rằng mọi lần thử TCP tại mỗi mốc đều nhận HTTP response.

### 4.2. Khi runner lỗi hoặc chạy nền

Nếu runner ném ngoại lệ ra ngoài, Boot xử lý startup failure; `ApplicationReadyEvent` theo luồng thành công không được phát và context/server có thể bị đóng. Port từng bind được trước lỗi không chứng minh startup cuối cùng thành công.

Nếu runner khởi động tác vụ bất đồng bộ rồi return ngay, Boot **không tự đợi Future/thread đó**. Nếu việc chuẩn bị là bắt buộc, phải chủ động đợi kết quả hoặc thiết kế readiness gate riêng; nếu không, Boot có thể chuyển sang ready quá sớm.


## 5. Phân biệt socket, HTTP và readiness

Một cổng mạng “mở” là kết quả của nhiều bước độc lập:

```text
Spring Boot chọn kiểu web application
   -> Web server được tạo / cấu hình server.port
   -> OS bind/listen địa chỉ:cổng
   -> Đường mạng từ client tới cổng hoạt động?
   -> HTTP connector nhận và xử lý request?
   -> Controller/filter/Actuator health trả response?
   -> Readiness health group có đang UP?
   -> Nghiệp vụ thật sự thực hiện thành công?
```

Những ví dụ thường gặp:

- Cấu hình `server.port=8080` **không** chắc bind thành công: có thể cổng đã bị process khác chiếm.
- TCP handshake đến 8080 thành công chỉ xác nhận một socket có thể nhận kết nối, không chứng minh dữ liệu đã preload hay repository hoạt động.
- HTTP `404 Not Found` có thể chứng tỏ server xử lý request, nhưng đường dẫn bạn gọi sai; chưa có thông tin readiness.
- HTTP `200 OK` tại `/ping` chỉ kiểm thử một route. Nếu `/ping` luôn trả `pong`, nó không kiểm tra database hoặc bộ dữ liệu cần thiết.
- `/actuator/health/readiness` trả `UP` có ý nghĩa **trong phạm vi các health indicator được group này cấu hình**, không phải toàn bộ business operations.
- `Connection refused` hoặc timeout có thể do server chưa start, firewall, sai port, NetworkPolicy, Service/Ingress hoặc shutdown; không thể kết luận ngay `LivenessState.BROKEN`.
- Web server được khởi tạo trong quá trình refresh, có thể được biết tới trước runner, trong khi readiness vẫn đang `REFUSING_TRAFFIC`.

Thời điểm TCP connect và thời điểm một HTTP request có thể được xử lý ở giữa startup còn chịu ảnh hưởng lifecycle connector; **không hứa luôn nhận HTTP 503 trong lúc runner đang chạy**. Nếu HTTP endpoint chưa có khả năng nhận request, client có thể không nhận HTTP response nào.

### 5.1. Các địa chỉ/cổng dễ nhầm

- `server.address=127.0.0.1` bind trên loopback: client ngoài host/container không kết nối được dù `ApplicationAvailability` là ready.
- `server.port=8080` là cổng ứng dụng; `management.server.port=8081` (nếu cấu hình) là cổng Actuator có thể tách riêng. Hai connector có thể không cùng tình trạng.
- Docker `EXPOSE` không đồng nghĩa đã publish cổng tới host; container networking vẫn phải cấu hình.
- Kubernetes `containerPort`, Service `targetPort`, selectors, EndpointSlice, NetworkPolicy và Ingress phải đúng. Readiness UP bên trong Pod không tự sửa đường mạng sai.
- TLS termination và proxy có thể làm client thấy lỗi khác với truy cập trực tiếp đến Pod.
- Thử nghiệm từ `localhost` trên chính máy chạy app không giống request từ một Pod khác hoặc từ Internet.

## 6. Actuator liveness/readiness probes

Khi có dependency `spring-boot-starter-actuator` và các probe health groups được bật/phơi bày trên web, Spring Boot 3.3 cung cấp:

```text
GET /actuator/health/liveness
GET /actuator/health/readiness
```

Hai indicator chính là `LivenessStateHealthIndicator` và `ReadinessStateHealthIndicator`, phản ánh trạng thái từ `ApplicationAvailability`.

Trong Kubernetes, Spring Boot có thể tự bật các health groups này khi phát hiện môi trường Kubernetes. Để bật **cả trong môi trường local** một cách rõ ràng:

```properties
management.endpoint.health.probes.enabled=true
```

Phải bảo đảm Actuator dependency, HTTP exposure và security tương thích. Không có Actuator thì việc khai báo Kubernetes path không tự tạo endpoint.

### 6.1. Mapping HTTP status thông dụng

| State | Health status mặc định | HTTP status thường gặp |
| --- | --- | --- |
| `LivenessState.CORRECT` | `UP` | `200 OK` |
| `LivenessState.BROKEN` | `DOWN` | `503 Service Unavailable` |
| `ReadinessState.ACCEPTING_TRAFFIC` | `UP` | `200 OK` |
| `ReadinessState.REFUSING_TRAFFIC` | `OUT_OF_SERVICE` | `503 Service Unavailable` |

Đây là mapping health status mặc định trong cấu hình tương ứng; nó có thể được chỉnh bằng `management.endpoint.health.status.http-mapping.*` và health-group status mapping. **Không có response HTTP** là trường hợp khác hẳn **có response HTTP 503**.

### 6.2. Additional probe paths trên main port

Nếu Actuator chạy ở một management port riêng, probe ở cổng quản trị có thể trả 200 dù cổng HTTP chính đang lỗi. Để kiểm tra health trên **cùng cổng chính**, Boot 3.3 hỗ trợ:

```properties
management.endpoint.health.probes.add-additional-paths=true
```

Khi bật, có thêm đường mặc định:

```text
GET /livez
GET /readyz
```

Các đường này được tạo trên **main server port**. Ví dụ `server.port=8080` và `management.server.port=8081` thì request tới `http://localhost:8080/readyz` kiểm tra readiness qua connector chính. Health group còn có thể khai báo đường riêng như `management.endpoint.health.group.readiness.additional-path=server:/ready-check`.

Additional path giúp tránh “cổng quản trị khỏe, cổng chính hỏng”, nhưng vẫn không bảo đảm tất cả controller hay transaction nghiệp vụ đều khỏe. Phải dùng thêm kiểm tra end-to-end nếu yêu cầu vận hành cần điều đó.


## 7. Ví dụ Java 17+ / Spring Boot 3.3.13 chạy được

Mục tiêu của thí nghiệm là chứng minh **server đã có port trong runner, liveness CORRECT nhưng readiness vẫn REFUSING_TRAFFIC**; sau khi runner hoàn tất, readiness mới được Boot chuyển sang ACCEPTING_TRAFFIC.

### 7.1. build.gradle

Dự án Gradle Groovy có Gradle Wrapper, sử dụng Java 17:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
```

File `settings.gradle`:

```groovy
rootProject.name = 'availability-port-lab'
```

Tạo `src/main/resources/application.properties`:

```properties
server.port=8080
spring.main.banner-mode=off
spring.main.log-startup-info=false
logging.level.root=WARN

management.endpoint.health.probes.enabled=true
management.endpoint.health.probes.add-additional-paths=true
```

Ví dụ giả sử cổng `8080` đang rảnh. Nếu đã bị chiếm, chọn cổng khác và sửa các lệnh kiểm tra tương ứng.

### 7.2. Mã Java đầy đủ trong một file

Tạo `src/main/java/com/example/availability/AvailabilityPortLabApplication.java`:

```java
package com.example.availability;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.availability.ApplicationAvailability;
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.boot.web.servlet.context.ServletWebServerApplicationContext;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.EventListener;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class AvailabilityPortLabApplication {

    public static void main(String[] args) {
        ConfigurableApplicationContext context =
                SpringApplication.run(AvailabilityPortLabApplication.class, args);

        ApplicationAvailability availability =
                context.getBean(ApplicationAvailability.class);

        System.out.println("07 main: liveness=" + availability.getLivenessState()
                + ", readiness=" + availability.getReadinessState());
    }

    @EventListener
    public void started(ApplicationStartedEvent event) {
        System.out.println("01 ApplicationStartedEvent");
    }

    @Bean
    ApplicationRunner warmUp(ApplicationAvailability availability,
                             ServletWebServerApplicationContext context) {
        return args -> {
            System.out.println("02 runner: port=" + context.getWebServer().getPort());
            System.out.println("03 runner: liveness=" + availability.getLivenessState());
            System.out.println("04 runner: readiness=" + availability.getReadinessState());
            Thread.sleep(2500);
        };
    }

    @EventListener
    public void ready(ApplicationReadyEvent event) {
        System.out.println("05 ApplicationReadyEvent");
    }

    @EventListener
    public void readinessChanged(AvailabilityChangeEvent<ReadinessState> event) {
        if (event.getState() == ReadinessState.ACCEPTING_TRAFFIC) {
            System.out.println("06 readiness=ACCEPTING_TRAFFIC");
        }
    }

    @RestController
    public static class PingController {
        @GetMapping("/ping")
        public String ping() {
            return "pong";
        }
    }
}
```

Giải thích:

- `spring-boot-starter-web` khởi động embedded Tomcat (mặc định cho Spring MVC) khi refresh context.
- `ServletWebServerApplicationContext#getWebServer().getPort()` đọc cổng server ở thời điểm runner chạy sau refresh. Việc có port không tự chứng minh readiness.
- `ApplicationAvailability` có thể inject như một bean bình thường; trong runner, liveness đã `CORRECT` còn readiness chưa được chuyển sang `ACCEPTING_TRAFFIC`.
- `@EventListener(ApplicationReadyEvent)` chỉ in marker; readiness accepting được phát qua `AvailabilityChangeEvent` **sau** ready event.
- `Thread.sleep(2500)` là chậm giả lập, không phải cách đợi dependency trong production.
- `/ping` chỉ trả chuỗi `pong`, không phải readiness probe.
- Vì đây là web application, không tự đóng `ApplicationContext` ngay sau `run`: server cần tiếp tục phục vụ.

### 7.3. Chạy và đối chiếu stdout

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

macOS/Linux:

```bash
./gradlew bootRun
```

Khi không có listener tùy biến khác, các dòng **do code Java chủ động in ra** theo thứ tự:

```text
01 ApplicationStartedEvent
02 runner: port=8080
03 runner: liveness=CORRECT
04 runner: readiness=REFUSING_TRAFFIC
05 ApplicationReadyEvent
06 readiness=ACCEPTING_TRAFFIC
07 main: liveness=CORRECT, readiness=ACCEPTING_TRAFFIC
```

Gradle/log có thể thêm dòng khác; chỉ so sánh những dòng bắt đầu bằng số. Dòng 02 và 04 là minh chứng trực tiếp cho sự khác biệt giữa “port đã được server khởi tạo” và “ready”.

### 7.4. HTTP sau khi ứng dụng ready

Mở terminal thứ hai sau dòng 07:

```bash
curl -i http://localhost:8080/ping
curl -i http://localhost:8080/livez
curl -i http://localhost:8080/readyz
curl -i http://localhost:8080/actuator/health/liveness
curl -i http://localhost:8080/actuator/health/readiness
```

Kết quả trong cấu hình mặc định:

- `/ping` trả HTTP 200 với body `pong`.
- `/livez` và `/actuator/health/liveness` trả trạng thái `UP`, HTTP 200.
- `/readyz` và `/actuator/health/readiness` trả trạng thái `UP`, HTTP 200.

Thử gọi `/readyz` trong khoảng thời gian runner sleep. Nếu connector đã có thể xử lý request, health endpoint thường phản ánh readiness `OUT_OF_SERVICE` với HTTP 503. Tuy nhiên, trong các cấu hình hoặc thời điểm cụ thể, request có thể không kết nối được hoặc chưa xử lý được; không coi “chắc chắn thấy 503 trước ready” là cam kết của mọi web server.

### 7.5. Khi runner throw

Nếu thay dòng `Thread.sleep(2500)` bằng:

```java
throw new IllegalStateException("Mandatory data unavailable");
```

thì runner làm startup fail: `ApplicationReadyEvent` và `ReadinessState.ACCEPTING_TRAFFIC` của luồng thành công **không xảy ra**, `SpringApplication.run` không trả về bình thường và dòng `07 main` không xuất hiện. Web server/context thường được Boot đóng trong failure handling, dù log server start có thể đã được in trước đó.


## 8. Kubernetes probes: đúng mục đích, đúng hành động

Kubernetes phân biệt:

- **`livenessProbe`:** Nếu nhiều lần thất bại tới ngưỡng, kubelet có thể restart container. Phù hợp khi trạng thái nội bộ không thể tự phục hồi.
- **`readinessProbe`:** Khi probe thất bại, Pod/instance bị đánh dấu chưa sẵn sàng và không còn được chọn nhận traffic qua Kubernetes Service tương ứng. Không mặc định restart vì thiếu readiness.
- **`startupProbe`:** Khi được cấu hình, nó có thể bảo vệ giai đoạn startup dài khỏi bị liveness/readiness probe đánh giá quá sớm. Khi startup probe chưa thành công, các probe kia chưa chạy theo cơ chế startup probe; nếu startup probe thất bại tới giới hạn, container có thể bị restart.

Một đoạn container YAML minh họa dùng thêm `/livez` và `/readyz` trên main port:

```yaml
containers:
  - name: availability-port-lab
    image: example/availability-port-lab:1.0
    ports:
      - containerPort: 8080
    startupProbe:
      httpGet:
        path: /livez
        port: 8080
      periodSeconds: 5
      failureThreshold: 30
    livenessProbe:
      httpGet:
        path: /livez
        port: 8080
      periodSeconds: 10
      timeoutSeconds: 2
      failureThreshold: 3
    readinessProbe:
      httpGet:
        path: /readyz
        port: 8080
      periodSeconds: 5
      timeoutSeconds: 2
      failureThreshold: 3
```

Đây là **đoạn cấu hình mẫu** nằm trong Pod/Deployment, không phải Deployment YAML hoàn chỉnh. Image `example/availability-port-lab:1.0` chỉ là tên minh họa. `periodSeconds`, `failureThreshold` và `timeoutSeconds` phải điều chỉnh theo startup time và nhu cầu vận hành.

Nếu dùng `startupProbe` cần chú ý endpoint `/livez` có thể thành công ngay sau context refresh, trước runner; nhưng `readinessProbe` vẫn bảo vệ việc nhận traffic đến khi startup hoàn tất. Với ứng dụng khởi động không dài, startupProbe không phải lúc nào cũng cần.

Kubernetes chỉ rút Pod khỏi tuyến qua Service khi sử dụng readiness. Một client gọi **trực tiếp Pod IP** có thể bỏ qua tuyến đó. Nếu mọi Pod đều unready, response của Service/Ingress/load balancer còn phụ thuộc implementation; đôi khi là connection failure, đôi khi proxy trả 503. Đừng quy mọi tình huống thành “Spring Boot trả 503”.

## 9. External dependencies: đưa vào readiness/liveness khi nào?

Ví dụ có 20 replica Spring Boot dùng chung database. Database mất kết nối 30 giây; những replica vẫn có khả năng retry hoặc dùng cache/fallback, chỉ phụ thuộc ngoài bị gián đoạn.

Nếu **liveness probe** phụ thuộc DB, tất cả replica có thể lần lượt bị restart, làm pool kết nối và quá trình warm-up tải trở lại database đồng thời. Đây là **cascading failure**. Vì vậy tài liệu Spring Boot khuyến cáo không gắn các kiểm tra hệ thống ngoài vào liveness theo mặc định.

Với **readiness**, cần quyết định theo hợp đồng:

1. Nếu dependency **bắt buộc cho mọi request**, không có fallback, có thể cân nhắc rút instance khỏi traffic khi dependency hỏng.
2. Nếu dependency **tùy chọn**, có circuit breaker/fallback đúng, đừng tự loại instance khỏi phục vụ.
3. Nếu dependency **riêng từng instance**, readiness indicator có thể giúp loại đúng instance.
4. Nếu dependency **dùng chung bởi mọi replica**, cho tất cả unready có thể khiến cả service không còn endpoint dù một số tác vụ vẫn có thể hoạt động. Cần đánh giá trade-off theo business contract.

Spring Boot 3.3 **không tự thêm mọi HealthIndicator của database, cache hoặc API vào nhóm readiness/liveness**. Mặc định probe groups dựa trên state tương ứng. Để thêm một HealthIndicator tùy chỉnh tên `catalog` vào readiness, có thể dùng:

```properties
management.endpoint.health.group.readiness.include=readinessState,catalog
```

Đây là **mẫu phụ thuộc vào việc đã có một HealthIndicator tên catalog**; cấu hình không tự sinh indicator. Custom check nên có timeout ngắn, tránh I/O vô hạn và không để probe gây thêm tải lớn lúc hệ thống sự cố.

### 9.1. Không dùng port-open thay health endpoint

TCP probe chỉ chứng minh khả năng bắt tay TCP. Với state liveness/readiness do Spring Boot quản lý, nên sử dụng HTTP probe tương ứng. Có thể bổ sung synthetic check xuyên qua controller/service nếu yêu cầu thật sự là đo end-to-end request path, nhưng không đưa check tốn kém vào liveness mỗi vài giây.

## 10. Ứng dụng chủ động thay đổi ReadinessState

Một ứng dụng có thể cập nhật availability state sau startup, chẳng hạn tự rút khỏi traffic khi queue nội bộ đầy hoặc một thành phần bắt buộc cần thời gian phục hồi. Spring Boot hỗ trợ phát `AvailabilityChangeEvent`:

```java
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.ApplicationEventPublisher;

// Trong một Spring bean đã inject ApplicationEventPublisher publisher:
AvailabilityChangeEvent.publish(
        publisher, this, ReadinessState.REFUSING_TRAFFIC);
```

Khi điều kiện được khôi phục và **đã kiểm chứng thực sự sẵn sàng**:

```java
AvailabilityChangeEvent.publish(
        publisher, this, ReadinessState.ACCEPTING_TRAFFIC);
```

Các đoạn là **minh họa cần class/field thật**. Phát readiness event **không đóng/mở socket**; health group phản ánh state mới khi được gọi, rồi Kubernetes/LB mới quan sát theo chu kỳ probe và cập nhật định tuyến. Có thể có độ trễ giữa event và thay đổi route.

Tránh nhiều module cùng tự phát các trạng thái mâu thuẫn, vì thay đổi mới có thể ghi đè quyết định cũ. Nếu readiness phụ thuộc nhiều điều kiện, nên có một owner tổng hợp state.

Chỉ dùng `LivenessState.BROKEN` cho trạng thái nội bộ thực sự không thể tự phục hồi, nơi restart có khả năng giải quyết. Đừng đánh BROKEN chỉ vì API ngoài trả lỗi tạm thời.

## 11. Graceful shutdown và readiness

Một instance có thể còn **live** để hoàn thành request đang xử lý nhưng chuyển readiness sang `REFUSING_TRAFFIC` để tránh nhận request mới khi deployment đang thu hồi nó.

Trong ứng dụng Spring Boot web server hỗ trợ graceful shutdown, có thể cấu hình:

```properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
```

Việc xử lý in-flight request và từ chối request mới phụ thuộc loại embedded server, Kubernetes termination grace period, cấu hình `preStop` và hành vi của proxy. Trong giai đoạn server đã ngừng nhận request, probe có thể không nhận HTTP response dù nội bộ ứng dụng đã cập nhật readiness.

`SIGKILL` hoặc crash không bảo đảm callback dọn dẹp chạy; hệ thống vẫn cần timeout/retry/idempotency phù hợp.

## 12. Checklist khi “Started nhưng không có traffic”

1. Đúng **host, Pod, namespace, cổng** nào? Main port hay management port?
2. Context đã refresh nhưng runner chưa hoàn tất? Có `ApplicationStartedEvent` mà chưa có `ApplicationReadyEvent` không?
3. `ApplicationAvailability` hiện là `CORRECT/REFUSING_TRAFFIC` hay `CORRECT/ACCEPTING_TRAFFIC`?
4. Actuator dependency đã có, probe group đã bật, HTTP endpoint có exposure/security đúng không?
5. `/actuator/health/readiness` hoặc `/readyz` trên main port trả HTTP status gì? Nếu không kết nối được, kiểm tra network trước.
6. Port bind đúng interface? Docker publish, Kubernetes Service selectors, targetPort, EndpointSlice và NetworkPolicy đúng chưa?
7. Nếu management port trả 200, main port có thật sự nhận request không? Có cần additional paths trên main port?
8. Kubernetes có đưa Pod vào Endpoints chưa? Probe period/threshold và propagation delay có gây chậm không?
9. Health group readiness gồm những contributor nào? Có dependency check chậm, timeout hoặc flapping không?
10. Có đang graceful shutdown, draining hoặc vừa nhận SIGTERM không?
11. Nếu port/connectivity/health đều tốt nhưng client vẫn lỗi, kiểm tra route HTTP thực, auth, reverse proxy, DNS, TLS và nghiệp vụ.
12. Nếu runner đã chạy background task rồi return, readiness có đang lên quá sớm không?

**Đừng kết luận chỉ từ một chỉ số.** Kết hợp event timeline, state của Boot, HTTP probe, TCP socket, Service routing và một request nghiệp vụ tối thiểu sẽ chỉ ra lỗi đúng tầng.

## 13. Ngộ nhận thường gặp

| Nhận định | Vì sao không chính xác? |
| --- | --- |
| “8080 mở nên app ready” | Port không chứa thông tin runner hoặc readiness state |
| “Liveness CORRECT nên DB chắc khỏe” | Liveness là tình trạng nội bộ, thường không kiểm DB |
| “Readiness false thì phải restart” | Nó chỉ nói nên tạm ngừng gửi traffic |
| “/ping 200 thì ứng dụng ready” | Ping đơn giản có thể không kiểm điều kiện nghiệp vụ |
| “Management port UP thì main port UP” | Hai connector có thể lỗi độc lập |
| “Kubernetes luôn trả 503 khi unready” | Service/Ingress có thể tạo lỗi kết nối hoặc phản hồi tùy implementation |
| “Probe được tự tạo chỉ bằng YAML Kubernetes” | Spring phải thực sự có endpoint và HTTP exposure phù hợp |
| “@EventListener(ApplicationStartedEvent) đọc readiness accepting” | Started đến trước runner, readiness accepting đến sau ready |
| “@Async runner xong là dữ liệu nền đã nạp” | Runner có thể return trước khi task nền hoàn tất |
| “Bật startupProbe thì không cần readinessProbe” | Startup và readiness có mục đích khác nhau |
| “Tất cả dependency phải đưa vào liveness” | Dễ gây restart hàng loạt và cascading failure |
| “/readyz UP bảo đảm mọi API không lỗi” | Health group có phạm vi kiểm tra cụ thể, không bao phủ toàn hệ thống |
| “Readiness event làm OS đóng TCP port” | Event thay state, routing phải do hạ tầng thực hiện |
| “Port được bind thì client bên ngoài luôn truy cập được” | Bind interface, firewall, proxy và Service routing còn có thể sai |

## 14. Tự kiểm tra

**Câu 1:** Một ứng dụng đã refresh context nhưng runner đang preload dữ liệu 10 giây. Liveness/readiness là gì?

**Đáp:** Theo đường startup mặc định sau started event: `CORRECT` và `REFUSING_TRAFFIC`. Port có thể đã được khởi tạo, nhưng chưa có mốc ready.

**Câu 2:** Vì sao TCP connect tới 8080 thành công nhưng readiness vẫn chưa đạt?

**Đáp:** Kết nối TCP xác nhận socket, không xác nhận runner xong hay health group `UP`.

**Câu 3:** Khi readiness probe fail, Kubernetes có nhất thiết restart Pod không?

**Đáp:** Không; readiness thường điều khiển định tuyến. Liveness/startup probe mới gắn với chính sách restart khi thất bại quá ngưỡng.

**Câu 4:** Có nên dùng Redis cache tùy chọn làm liveness check?

**Đáp:** Thường không. Redis ngoài hệ thống hỏng không đồng nghĩa instance mất khả năng tự phục hồi; restart có thể gây lỗi dây chuyền.

**Câu 5:** Muốn kiểm tra readiness trên cổng chính khi Actuator dùng management port riêng?

**Đáp:** Bật `management.endpoint.health.probes.add-additional-paths=true`, kiểm tra `/readyz` trên main port, bảo đảm security/network cho probe.

**Câu 6:** Sau `ApplicationReadyEvent`, sự kiện availability nào được Boot phát?

**Đáp:** `AvailabilityChangeEvent` với `ReadinessState.ACCEPTING_TRAFFIC` trong đường startup thành công.

**Câu 7:** Nếu ứng dụng tự phát `ReadinessState.REFUSING_TRAFFIC` thì port tự đóng chưa?

**Đáp:** Chưa. Đây là state nội bộ; hạ tầng quan sát probe và điều chỉnh route theo cấu hình.

**Câu 8:** Nếu tất cả Pod đều unready, có chắc chính Spring Boot trả 503?

**Đáp:** Không. Service/Ingress/proxy có thể không có endpoint để kết nối; hành vi HTTP tùy loại và triển khai mạng.

## 15. Ghi nhớ và tài liệu chính thức

- **Liveness:** `CORRECT/BROKEN` — tình trạng nội bộ, restart chỉ hữu ích khi lỗi không tự phục hồi.
- **Readiness:** `ACCEPTING_TRAFFIC/REFUSING_TRAFFIC` — có nên nhận request mới.
- **Port mạng:** server/socket/network path; **port mở không chứng minh ready**.
- **Thứ tự Boot 3.3:** context refresh → started → liveness correct → runner → ready → readiness accepting.
- **Actuator:** health groups `/actuator/health/liveness` và `/actuator/health/readiness`; bật rõ bằng `management.endpoint.health.probes.enabled=true` khi cần.
- **Main port:** `management.endpoint.health.probes.add-additional-paths=true` tạo `/livez` và `/readyz`.
- **Kubernetes:** liveness failure có thể restart, readiness failure rút traffic; startupProbe bảo vệ startup dài.
- **External dependencies:** tránh đưa vào liveness; cân nhắc readiness theo độ bắt buộc, khả năng fallback và tác động toàn cụm.

Tài liệu để đối chiếu với Spring Boot **3.3.13**:

- [SpringApplication — Application Availability and Events](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html).
- [Actuator Endpoints — Kubernetes Probes](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html).
- [API — ApplicationAvailability](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/availability/ApplicationAvailability.html).
- [API — LivenessState](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/availability/LivenessState.html).
- [API — ReadinessState](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/availability/ReadinessState.html).

Để chẩn đoán tình trạng “ứng dụng còn chạy nhưng không nhận request”, hãy tách riêng **process/liveness**, **startup/readiness**, **port/network**, **HTTP endpoint** và **hợp đồng nghiệp vụ**. Mỗi tầng có nguyên nhân và cách khắc phục khác nhau.
