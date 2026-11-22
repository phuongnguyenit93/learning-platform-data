# Phân biệt công bố readiness với việc tự động chặn yêu cầu trong Spring Boot

**Phạm vi:** Spring Boot Application Runtime → Trạng thái sẵn sàng. Bài này giải thích sự khác biệt giữa **công bố trạng thái readiness**, **hiển thị readiness qua health probe**, **quyết định định tuyến traffic của hạ tầng** và **từ chối một HTTP request trong chính ứng dụng**. Mục tiêu là tránh hiểu nhầm rằng chỉ cần phát `AvailabilityChangeEvent<ReadinessState.REFUSING_TRAFFIC>` thì mọi controller, socket hay request đến trực tiếp đều tự trả 503.

Ví dụ thực hành dùng **Java 17+**, **Spring Boot 3.5.x**, **Spring MVC** và **Spring Boot Actuator**. Các API, cấu hình probe và hành vi của connector cần đối chiếu tài liệu đúng phiên bản khi áp dụng cho Spring Boot khác. Tác vụ thử nghiệm chỉ chạy trên localhost và không tạo thay đổi nghiệp vụ thật.

## 1. Kết luận nền tảng

**Công bố readiness là một tín hiệu trạng thái, không phải một bộ lọc HTTP áp dụng cho mọi endpoint.**

Khi ứng dụng đang chạy và code chủ động gọi:

~~~java
AvailabilityChangeEvent.publish(
        applicationContext, ReadinessState.REFUSING_TRAFFIC);
~~~

Spring Boot cập nhật `ApplicationAvailability`; health indicator của readiness được Actuator dùng để phản ánh trạng thái này. Với mapping HTTP mặc định, endpoint `/actuator/health/readiness` sẽ chuyển sang trạng thái `OUT_OF_SERVICE` và thường trả **503**.

Tuy nhiên, nếu client **gọi trực tiếp** một endpoint nghiệp vụ đang được web server phục vụ và ứng dụng không có bộ lọc/gateway chặn request, controller đó **vẫn có thể xử lý và trả 200**. Nói cách khác:

- **Readiness state**: ứng dụng nói “tôi không nên nhận thêm lưu lượng”.
- **Readiness probe**: endpoint vận hành báo cho hệ thống giám sát hoặc orchestrator tình trạng đó.
- **Router/load balancer/Kubernetes Service**: hạ tầng **có thể** ngừng đưa request mới đến instance sau khi quan sát probe không đạt.
- **Application-level gate**: bộ lọc/interceptor hoặc logic riêng do người phát triển cấu hình có thể **chủ động từ chối request** ngay trong JVM.
- **Web server shutdown**: quá trình graceful shutdown thật sự có thể đóng/chuyển trạng thái HTTP connector và xử lý request theo chính sách dừng; **khác** với việc chỉ publish readiness event khi server đang chạy bình thường.

Hai trường hợp cuối không tự phát sinh chỉ vì một đoạn code công bố `REFUSING_TRAFFIC` giữa runtime. Phân biệt chúng giúp thiết kế chính xác readiness, vận hành Kubernetes và thử nghiệm hành vi khi ứng dụng tạm quá tải.

## 2. Bốn lớp cần hiểu độc lập

~~~text
                 Spring Boot process (JVM)
                 +--------------------------------------+
                 | Business controller /lab/process     |
                 |                                      |
                 | ApplicationAvailability              |
                 |   ReadinessState                     |
                 |    ACCEPTING_TRAFFIC / REFUSING ...  |
                 |                |                     |
                 |     ReadinessStateHealthIndicator     |
                 |                |                     |
                 | /actuator/health/readiness            |
                 +----------------|---------------------+
                                  |
                           kubelet/LB probes
                                  |
                            routing decision
                                  |
                    normal client -> Service / LB
                                  |
                       selected application pod

Direct client -> pod IP:port -> controller
   (có thể vẫn vào được nếu mạng, web connector và ứng dụng cho phép)
~~~

**Lớp 1 — State bên trong JVM:** `ApplicationAvailability.getReadinessState()` cho biết snapshot readiness hiện hành mà Spring Boot đang theo dõi. Không phải socket firewall.

**Lớp 2 — Probe:** `/actuator/health/readiness` bộc lộ state qua health group; body thường là `{"status":"UP"}` khi `ACCEPTING_TRAFFIC` và `{"status":"OUT_OF_SERVICE"}` khi `REFUSING_TRAFFIC`. HTTP 200/503 là mapping **của health endpoint**, không phải mapping tự động cho toàn bộ controller.

**Lớp 3 — Hạ tầng:** kubelet hoặc load balancer gọi probe theo chu kỳ và thay đổi điều kiện routing. Quá trình này có độ trễ và tùy mạng, service mesh, endpoints, connection reuse. Một client gọi thẳng đến Pod IP hay server port có thể bỏ qua Service/LB và vẫn gửi request thành công.

**Lớp 4 — Từ chối tại ứng dụng:** muốn application trả 503 cho một request cụ thể, cần **chủ động kiểm tra readiness và đặt HTTP status** trong Servlet Filter, WebFlux WebFilter, gateway hoặc thiết kế route handler. Bộ lọc phải có chính sách rõ ràng về những endpoint được miễn, request đang xử lý, race giữa chuyển state và nhận request, và nguy cơ vô tình chặn health/control endpoint.

## 3. ReadinessState, AvailabilityChangeEvent và ApplicationAvailability

### 3.1. Hai trạng thái readiness

Spring Boot cung cấp `org.springframework.boot.availability.ReadinessState` với hai giá trị:

| ReadinessState | Ý nghĩa | Dùng để quyết định |
|---|---|---|
| `ACCEPTING_TRAFFIC` | Ứng dụng sẵn sàng nhận traffic | Hạ tầng có thể chọn instance để route |
| `REFUSING_TRAFFIC` | Ứng dụng hiện không muốn nhận thêm traffic | Hạ tầng nên tạm ngừng route request mới |

`REFUSING_TRAFFIC` không có nghĩa JVM đã chết, web connector đóng, hoặc mọi HTTP request phải bị trả về 503. Nó cũng không có nghĩa app cần restart. Đó là tín hiệu có thể thay đổi khi ứng dụng vượt qua/khỏi giai đoạn quá tải, warm-up hoặc maintenance.

### 3.2. Công bố sự kiện

Để yêu cầu chuyển trạng thái:

~~~java
AvailabilityChangeEvent.publish(
        context, ReadinessState.REFUSING_TRAFFIC);
~~~

và để chuyển trở lại:

~~~java
AvailabilityChangeEvent.publish(
        context, ReadinessState.ACCEPTING_TRAFFIC);
~~~

Hai đoạn là **snippets** đặt trong một Spring-managed component đã có `ApplicationContext context`; không phải chương trình Java độc lập. API `AvailabilityChangeEvent.publish(...)` phát sự kiện đến các listener. Implementation mặc định của `ApplicationAvailability` theo dõi sự kiện và cho code đọc trạng thái cuối.

Với event multicaster mặc định (đồng bộ cho phần lớn listener thông thường), callback state được xử lý trong luồng publish. Nếu project tự cấu hình multicast bất đồng bộ hoặc listener đặc biệt, không lấy tính tức thời của read-after-publish làm hợp đồng toàn hệ thống nếu chưa kiểm chứng.

### 3.3. Đọc trạng thái

~~~java
ReadinessState state = availability.getReadinessState();
boolean ready = state == ReadinessState.ACCEPTING_TRAFFIC;
~~~

Đoạn trên giả định bean đã inject `ApplicationAvailability availability`. Không cần và không nên truy cập trường nội bộ của `ApplicationAvailabilityBean` để sửa state; dùng event.

**Readiness khác liveness:**

- `LivenessState.CORRECT`: process có thể tiếp tục hoạt động/phục hồi theo định nghĩa internal liveness.
- `LivenessState.BROKEN`: trạng thái nội bộ có vấn đề không thể phục hồi bình thường, hạ tầng có thể restart.
- `ReadinessState.REFUSING_TRAFFIC` và `LivenessState.CORRECT` **có thể tồn tại đồng thời**. Ví dụ instance còn sống nhưng tạm ngừng nhận thêm traffic.

Không đưa health của database chung hoặc upstream API vào liveness một cách máy móc; outage chung khiến nhiều replica bị restart cùng lúc và tạo cascading failure.

## 4. Thời điểm Boot tự thay đổi readiness trong startup/shutdown

Trong luồng khởi động thành công của Spring Boot 3.5:

~~~text
SpringApplication.run(...)
    |
    +-- refresh ApplicationContext
    +-- ApplicationStartedEvent
    +-- LivenessState.CORRECT được công bố
    +-- ApplicationRunner / CommandLineRunner hoàn thành
    +-- ApplicationReadyEvent
    +-- ReadinessState.ACCEPTING_TRAFFIC được công bố
    |
    v
ứng dụng sẵn sàng theo vòng đời Boot
~~~

Boot khởi tạo theo trạng thái chưa sẵn sàng (`REFUSING_TRAFFIC`) cho đến mốc có thể nhận traffic. Khi dừng ứng dụng, readiness cũng có thể chuyển về `REFUSING_TRAFFIC` và HTTP connector chịu tác động bởi **vòng đời shutdown thật**, không chỉ sự kiện availability.

**Phân biệt hai bối cảnh quan trọng:**

1. **Startup/shutdown lifecycle:** Tài liệu Spring Boot mô tả trạng thái HTTP server tương ứng với các phase; trong startup runner hoặc graceful shutdown, server có thể chưa nhận request hoặc từ chối request mới do connector/lifecycle.
2. **Đang chạy bình thường, tự publish `REFUSING_TRAFFIC`:** Context và embedded server vẫn active. Việc publish state **không tự yêu cầu servlet container dừng/đóng cổng, không tự chèn `Filter` vào request chain**. Vì vậy cần dùng probe/routing hoặc bộ lọc riêng nếu muốn chặn.

Không lấy ví dụ server ngừng nhận kết nối **khi shutdown thật** để suy ra rằng một `AvailabilityChangeEvent` đơn lẻ cũng luôn đóng web server. Đây chính là ranh giới của đề bài.

## 5. Ma trận hành vi khi ứng dụng đang hoạt động

Giả sử đã startup xong, server nghe cổng 8080, không có filter chặn, Actuator health probes bật và HTTP status mapping mặc định:

| Tình huống | `ApplicationAvailability` | `GET /actuator/health/readiness` | `POST /lab/process` gọi trực tiếp |
|---|---|---|---|
| Vừa ready | `ACCEPTING_TRAFFIC` | HTTP 200, `UP` | HTTP 200 |
| Publish `REFUSING_TRAFFIC` | `REFUSING_TRAFFIC` | HTTP 503, `OUT_OF_SERVICE` | **Có thể vẫn HTTP 200** |
| Publish lại `ACCEPTING_TRAFFIC` | `ACCEPTING_TRAFFIC` | HTTP 200, `UP` | HTTP 200 |
| Refusing + có custom gate filter | `REFUSING_TRAFFIC` | HTTP 503 | **HTTP 503 do filter** |
| Web server đang dừng thật | Thường từ chối traffic | Có thể 503 hoặc không kết nối được | Có thể 503/không kết nối; phụ thuộc server và thời điểm |

Bảng là **kết quả dự kiến trong lab**, không cam kết mạng ngoài cluster hay mọi embedded server luôn có hành vi giống nhau ở phase shutdown. Nếu health group/status mapping được sửa, HTTP code của probe có thể khác; nếu endpoint nghiệp vụ có authentication/authorization hoặc logic lỗi riêng, response cũng có thể khác 200.

Một readiness probe 503 **không** buộc controller nghiệp vụ 503. Một HTTP controller 200 **không** chứng minh instance sẵn sàng được Service đưa vào tuyến traffic.

## 6. Ứng dụng mẫu: thấy readiness 503 nhưng nghiệp vụ vẫn xử lý

### 6.1. Chuẩn bị project

Tạo Maven project trong **Spring Initializr**:

- Group: `com.example`
- Artifact: `readiness-gate-lab`
- Package: `com.example.readinessgate`
- Java: **17**
- Spring Boot: **3.5.x**
- Dependencies: **Spring Web**, **Spring Boot Actuator**
- Packaging: **Jar**.

Giữ `pom.xml`, `mvnw` và plugin versions từ Initializr. Tạo cấu trúc:

~~~text
readiness-gate-lab/
  pom.xml
  mvnw
  mvnw.cmd
  src/main/java/com/example/readinessgate/
    ReadinessGateApplication.java
    LabController.java
    ReadinessTrace.java
    OptionalReadinessGateFilter.java
  src/main/resources/
    application.properties
~~~

Các class được đặt vào file riêng trùng public class. Toàn bộ code này biên dịch trong Maven project có Spring Web/Actuator; không chạy `javac` từng file mà thiếu classpath Spring.

### 6.2. Main: in mốc ready

File `src/main/java/com/example/readinessgate/ReadinessGateApplication.java`:

~~~java
package com.example.readinessgate;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.availability.ApplicationAvailability;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;

@SpringBootApplication
public class ReadinessGateApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReadinessGateApplication.class, args);
    }

    @EventListener(ApplicationReadyEvent.class)
    public void onReady(ApplicationReadyEvent event) {
        ApplicationAvailability availability =
                event.getApplicationContext()
                        .getBean(ApplicationAvailability.class);

        System.out.println(
                "LAB_APPLICATION_READY_EVENT readiness="
                        + availability.getReadinessState());
    }
}
~~~

Trong vòng đời Boot thông thường, `ApplicationReadyEvent` được phát **trước** event chuyển sang `ACCEPTING_TRAFFIC`. Nếu không có custom publisher khác, tại thời điểm ready listener xử lý, giá trị vẫn có thể là `REFUSING_TRAFFIC`; đừng suy rằng tên event “Ready” đồng nghĩa field readiness đã lập tức đổi khi callback bắt đầu.

### 6.3. Controller: endpoint nghiệp vụ, đọc state, đổi state

File `src/main/java/com/example/readinessgate/LabController.java`:

~~~java
package com.example.readinessgate;

import java.util.concurrent.atomic.AtomicLong;
import org.springframework.boot.availability.ApplicationAvailability;
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.ApplicationContext;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class LabController {

    private final ApplicationAvailability availability;
    private final ApplicationContext context;
    private final AtomicLong processed = new AtomicLong();

    public LabController(
            ApplicationAvailability availability,
            ApplicationContext context) {
        this.availability = availability;
        this.context = context;
    }

    @GetMapping("/lab/status")
    public Status status() {
        return new Status(
                availability.getReadinessState().name(),
                availability.getLivenessState().name(),
                processed.get());
    }

    @PostMapping("/lab/process")
    public ProcessResult process() {
        long number = processed.incrementAndGet();
        System.out.println("LAB_PROCESS_ACCEPTED count=" + number);

        return new ProcessResult("processed", number);
    }

    @PostMapping("/lab/control/refuse")
    public Status refuse() {
        AvailabilityChangeEvent.publish(
                context, ReadinessState.REFUSING_TRAFFIC);
        return status();
    }

    @PostMapping("/lab/control/accept")
    public Status accept() {
        AvailabilityChangeEvent.publish(
                context, ReadinessState.ACCEPTING_TRAFFIC);
        return status();
    }

    public record Status(
            String readiness, String liveness, long processed) {
    }

    public record ProcessResult(String outcome, long processed) {
    }
}
~~~

**Thiết kế minh họa:**

- `GET /lab/status` **đọc** readiness/liveness và số lượt xử lý; bản thân GET không cập nhật counter.
- `POST /lab/process` tượng trưng request nghiệp vụ và **tăng counter in-memory**. Không có filter, method này **không hề hỏi readiness** nên vẫn có thể xử lý khi state là refusing.
- `POST /lab/control/refuse` và `/accept` publish `AvailabilityChangeEvent` theo trạng thái mong muốn; các endpoint này chỉ dùng để làm lab.
- `AtomicLong` là counter phục vụ quan sát, không phải transaction hoặc business data thật.
- Các endpoint control phải được **loại bỏ hoặc bảo vệ mạnh** trong production. Ví dụ bind localhost để tránh người ngoài tùy ý thay readiness.

### 6.4. Listener nhận sự kiện readiness

File `src/main/java/com/example/readinessgate/ReadinessTrace.java`:

~~~java
package com.example.readinessgate;

import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class ReadinessTrace {

    @EventListener
    public void onState(AvailabilityChangeEvent<ReadinessState> event) {
        System.out.println("LAB_READINESS_CHANGED=" + event.getState());
    }
}
~~~

Log `LAB_READINESS_CHANGED=REFUSING_TRAFFIC` xác nhận state event được nhận, **không** xác nhận bộ lọc chặn request đã được kích hoạt. Ta sẽ đối chiếu nó với response của `POST /lab/process`.

### 6.5. Optional filter: chỉ bật trong kịch bản đối chứng

File `src/main/java/com/example/readinessgate/OptionalReadinessGateFilter.java`:

~~~java
package com.example.readinessgate;

import java.io.IOException;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.availability.ApplicationAvailability;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

@Component
@ConditionalOnProperty(
        name = "lab.gate.enabled",
        havingValue = "true")
public class OptionalReadinessGateFilter extends OncePerRequestFilter {

    private final ApplicationAvailability availability;

    public OptionalReadinessGateFilter(
            ApplicationAvailability availability) {
        this.availability = availability;
    }

    @Override
    protected boolean shouldNotFilter(HttpServletRequest request) {
        String path = request.getServletPath();

        return path.startsWith("/actuator/")
                || path.equals("/lab/status")
                || path.startsWith("/lab/control/");
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {

        if (availability.getReadinessState()
                != ReadinessState.ACCEPTING_TRAFFIC) {
            response.setStatus(HttpServletResponse.SC_SERVICE_UNAVAILABLE);
            response.setContentType("application/json");
            response.setCharacterEncoding("UTF-8");
            response.getWriter().write(
                    "{\"error\":\"not_ready\"}");
            return;
        }

        chain.doFilter(request, response);
    }
}
~~~

**Cơ chế có thể kiểm chứng:** mặc định `lab.gate.enabled=false` nên Spring không tạo filter này. Khi chạy bằng `--lab.gate.enabled=true`, bean filter được đăng ký vào servlet filter chain. Nó tự **đọc readiness state** và trả 503 cho các request không nằm trong danh sách miễn trừ. Đó là **logic do chính chúng ta viết**, không phải tác dụng tự động của `AvailabilityChangeEvent`.

Các đường `/actuator/` và `/lab/control/` được miễn để vẫn gọi probe và chuyển state trở lại; `/lab/status` được miễn để vẫn quan sát counter trong thử nghiệm. Trong ứng dụng thật, danh sách miễn trừ phải được xem xét cẩn thận: có thể cần health, metrics, auth, admin hoặc những API phục vụ draining khác. Đây là filter đơn giản để học, không phải giải pháp bảo mật, DDoS protection, admission control hay maintenance policy hoàn chỉnh.

**Giới hạn kỹ thuật:** filter kiểm tra snapshot lúc request đi qua; một request đã qua filter rồi mới có sự kiện refusing thì **không tự bị hủy**. Nhiều requests đồng thời có thể thấy trạng thái khác nhau tại ranh giới chuyển state. Với streaming, async requests, WebFlux và service mesh, cách áp dụng khác; đừng dùng `OncePerRequestFilter` của servlet stack cho WebFlux thuần.

### 6.6. Cấu hình ứng dụng

File `src/main/resources/application.properties`:

~~~properties
spring.application.name=readiness-gate-lab
server.address=127.0.0.1
server.port=8080
management.endpoint.health.probes.enabled=true
management.endpoints.web.exposure.include=health
management.endpoint.health.show-details=never
lab.gate.enabled=false
~~~

`management.endpoint.health.probes.enabled=true` làm các health groups readiness/liveness được tạo cả khi chạy ngoài Kubernetes. `health` được expose qua HTTP; liveness và readiness là các health groups nằm dưới health endpoint. `server.address=127.0.0.1` chỉ dùng để lab an toàn trên máy cá nhân; nếu deploy container và cần kubelet probe qua network, đừng giữ địa chỉ bind localhost mà không kiểm tra kiến trúc mạng.

Không thêm Spring Security vào project mẫu, nên ví dụ curl ở local không cần token. Trong production phải xác định rõ authentication/authorization cho endpoint điều khiển và các admin functions.

## 7. Thực nghiệm A — Readiness refusing nhưng nghiệp vụ vẫn trả 200

### 7.1. Chạy ứng dụng

Trên Linux/macOS:

~~~bash
java -version
./mvnw -version
./mvnw spring-boot:run
~~~

Trên Windows PowerShell:

~~~powershell
java -version
./mvnw.cmd -version
./mvnw.cmd spring-boot:run
~~~

Nếu cổng 8080 đã có service khác, dừng service đó hoặc đổi `server.port` và dùng cổng mới. Trong ví dụ có các marker liên quan:

~~~text
LAB_APPLICATION_READY_EVENT readiness=REFUSING_TRAFFIC
LAB_READINESS_CHANGED=ACCEPTING_TRAFFIC
~~~

Đây là thứ tự minh họa cho startup mặc định **không có publisher tùy chỉnh khác**. Log framework có thể xen vào; liveness/readiness do Spring Boot quản lý có thể có thêm markers ở shutdown.

Trong terminal thứ hai, kiểm tra trạng thái ban đầu:

~~~bash
curl -i http://127.0.0.1:8080/lab/status
curl -i http://127.0.0.1:8080/actuator/health/readiness
curl -i http://127.0.0.1:8080/actuator/health/liveness
~~~

Kỳ vọng sau startup:

~~~json
{"readiness":"ACCEPTING_TRAFFIC","liveness":"CORRECT","processed":0}
~~~

Hai probe thường HTTP 200 và body `{"status":"UP"}` khi ứng dụng lab khỏe. Nếu cấu hình group, auth hoặc HTTP mapping khác, kết quả có thể khác; lab dựa trên cấu hình ở trên.

### 7.2. Gọi nghiệp vụ khi state accepting

~~~bash
curl -i -X POST http://127.0.0.1:8080/lab/process
~~~

Kỳ vọng HTTP 200 cùng JSON:

~~~json
{"outcome":"processed","processed":1}
~~~

Controller in `LAB_PROCESS_ACCEPTED count=1`. Đây là giá trị theo một JVM mới chạy và chưa có lượt process trước đó.

### 7.3. Công bố readiness refusing

~~~bash
curl -i -X POST http://127.0.0.1:8080/lab/control/refuse
curl -i http://127.0.0.1:8080/lab/status
curl -i http://127.0.0.1:8080/actuator/health/readiness
~~~

Kỳ vọng:

- Listener in `LAB_READINESS_CHANGED=REFUSING_TRAFFIC`.
- `/lab/status` trả `"readiness":"REFUSING_TRAFFIC"` và liveness vẫn `CORRECT`.
- `/actuator/health/readiness` trả HTTP 503 và body tương đương `{"status":"OUT_OF_SERVICE"}` với cấu hình/mapping mặc định.

Bây giờ **đừng bật gate filter**. Gọi thẳng endpoint nghiệp vụ:

~~~bash
curl -i -X POST http://127.0.0.1:8080/lab/process
curl -i http://127.0.0.1:8080/lab/status
~~~

Kết quả mong đợi cho POST thứ hai:

~~~json
{"outcome":"processed","processed":2}
~~~

`/lab/status` xác nhận counter đã thành 2 dù readiness vẫn `REFUSING_TRAFFIC`. Đây là bằng chứng **trực tiếp và quyết định**: publish readiness event chỉ làm đổi availability/probe trong lab, **không tự chặn request nghiệp vụ** đến trực tiếp servlet server đang hoạt động.

**Lưu ý kỹ thuật:** Nếu client thông qua Kubernetes Service đã loại Pod khỏi endpoints, request có thể không đến được Pod. Nhưng điều đó do tuyến hạ tầng, không phải vì controller/Filter mặc định của Spring tự trả 503 cho mọi endpoint.

### 7.4. Khôi phục state

~~~bash
curl -i -X POST http://127.0.0.1:8080/lab/control/accept
curl -i http://127.0.0.1:8080/actuator/health/readiness
~~~

Marker trở lại `LAB_READINESS_CHANGED=ACCEPTING_TRAFFIC`, probe thường trả 200 `UP`. Không cần restart app, không cần gọi lại `SpringApplication.run()` và không có `ApplicationReadyEvent` mới chỉ vì ta đổi state sau startup.

## 8. Thực nghiệm B — Chủ động thêm HTTP gate để chặn

Dừng bản chạy A. Đóng gói bằng Maven:

~~~bash
./mvnw clean package
java -jar target/readiness-gate-lab-0.0.1-SNAPSHOT.jar --lab.gate.enabled=true
~~~

Trên Windows PowerShell dùng `./mvnw.cmd clean package`. Tên JAR là ví dụ khi artifact/version giống Initializr `readiness-gate-lab` / `0.0.1-SNAPSHOT`; nếu khác lấy đúng JAR thực tế trong `target/`.

Đợi ready, gọi:

~~~bash
curl -i -X POST http://127.0.0.1:8080/lab/process
~~~

Khi readiness accepting, filter gọi `chain.doFilter(...)` nên response vẫn 200. Sau đó:

~~~bash
curl -i -X POST http://127.0.0.1:8080/lab/control/refuse
curl -i http://127.0.0.1:8080/lab/status
curl -i http://127.0.0.1:8080/actuator/health/readiness
curl -i -X POST http://127.0.0.1:8080/lab/process
~~~

Lần gọi `POST /lab/process` cuối được **`OptionalReadinessGateFilter` chủ động trả 503** với body:

~~~json
{"error":"not_ready"}
~~~

Console **không tăng** marker `LAB_PROCESS_ACCEPTED` cho request bị chặn; `/lab/status` vẫn truy cập được để đối chiếu counter. Health probe tiếp tục báo `OUT_OF_SERVICE`/503 vì state refusing, dù filter miễn endpoint Actuator. Đây là phép tách nguyên nhân:

| Kết quả | Không có gate | Có gate |
|---|---|---|
| Publish `REFUSING_TRAFFIC` cập nhật availability | Có | Có |
| Readiness probe trả 503 | Có | Có |
| `POST /lab/process` gọi trực tiếp | Vẫn 200 | **503 do custom filter** |
| Controller `process()` có chạy ở request bị chặn? | Có | Không |
| Cần thay web server hoặc refresh context để đổi state? | Không | Không |

Gọi `POST /lab/control/accept` sẽ chuyển state lại và cho request process mới đi qua filter. Khi filter hoạt động, đó là chính sách do ứng dụng cài đặt. Không nhầm nó với cách kubelet gỡ Pod khỏi routing.

## 9. Vì sao không tự chặn mọi request ngay khi state là refusing?

Tự chặn ở application level nghe có vẻ đơn giản, nhưng có trade-off:

1. **Đường health và management:** nếu filter vô tình chặn luôn `/actuator/health/readiness`, hạ tầng vẫn thấy 503 nhưng bạn khó phân biệt nguyên nhân. Nếu chặn `/actuator/health/liveness`, Pod có thể bị restart dù JVM hoàn toàn khỏe.
2. **Admin/repair:** một endpoint để tắt gate hoặc sửa điều kiện không thể truy cập nếu cũng nằm sau gate; cần đường điều khiển bảo vệ, có khả năng phục hồi.
3. **Request đang xử lý:** state refusal không có nghĩa nên cắt ngang transaction/request đã chạy. Graceful draining muốn giảm request mới, đồng thời cho request cũ hoàn tất trong deadline.
4. **Health group khác nhau:** một app có thể có endpoint public và internal; không phải request nào cũng có cùng policy.
5. **Authentication và security:** health/routing không thay authentication/authorization; bypass gate không có nghĩa được bypass security.
6. **Race condition:** readiness là snapshot có thể thay đổi giữa check và processing. Filter không cung cấp “no new requests after exact nanosecond” tuyệt đối.
7. **WebFlux vs Servlet:** web filter khác với Servlet Filter; dùng đúng stack.
8. **Đa instance:** gate trong một replica không bảo đảm các replica khác đồng bộ state.
9. **Nguy cơ self-inflicted outage:** nếu chọn sai health dependency hoặc gate quá mạnh, cả cụm có thể không phục vụ request dù có thể fallback.

Trong đa số triển khai Kubernetes, readiness probe để **quản lý routing** là cơ chế chính; custom gate chỉ nên thêm khi có hợp đồng nghiệp vụ yêu cầu **bản thân instance không được thực hiện một số request ngay cả khi bị truy cập trực tiếp**, và cần kiểm thử recovery paths.

## 10. Kubernetes readinessProbe quyết định routing, không sửa Controller

Ví dụ đoạn cấu hình **trong container spec** của Pod/Deployment (không phải manifest YAML đầy đủ):

~~~yaml
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

startupProbe:
  httpGet:
    path: /actuator/health/liveness
    port: 8080
  periodSeconds: 5
  failureThreshold: 24
~~~

Kubelet dùng kết quả readiness để cập nhật trạng thái Pod và eligibility của các Service endpoints. Điều này làm routing **qua Service** tránh gửi request mới đến Pod chưa ready, sau khi cập nhật lan truyền. Nhưng:

- Routing không nhất thiết chuyển ngay lập tức tại thời điểm JVM publish event.
- Existing keep-alive connections, ingress, service mesh hoặc client direct PodIP có thể có hành vi khác.
- `readinessProbe` fail **không** mặc nhiên giết container; đó là khác biệt với liveness probe có thể khiến restart.
- Khi tất cả replica đều không ready, Service có thể không có endpoints khỏe để phục vụ; cần thiết kế dependency/readiness policy cẩn trọng.
- `startupProbe` có thể bảo vệ ứng dụng khởi động chậm khỏi bị liveness restart sớm; không phải bộ chặn nghiệp vụ trong JVM.

**Chú ý khi triển khai:** Lab bind `server.address=127.0.0.1` chỉ để local. Trong Kubernetes, servlet server phải bind interface mà kubelet có thể kết nối, thường bằng cách bỏ property này hoặc bind `0.0.0.0`. Nếu để loopback tùy tiện trong container, HTTP probe qua Pod network có thể fail dù ứng dụng thực chất chạy.

### 10.1. Probe trên management port riêng

Nếu ứng dụng cấu hình `management.server.port` khác port của service, health probe chỉ kiểm tra được management connector. Có thể xảy ra trường hợp management server còn hoạt động nhưng main application port gặp sự cố. Spring Boot hỗ trợ tạo thêm `/livez` và `/readyz` trên **main server port** với:

~~~properties
management.endpoint.health.probes.add-additional-paths=true
~~~

Nếu sử dụng, hãy xác minh URL và security/routing thực tế trước khi đổi manifest; không phỏng đoán port chính có thể truy cập từ kubelet khi chưa thử.

## 11. Readiness và phụ thuộc ngoài: công bố state có giới hạn gì?

Tại mốc startup ready, Spring Boot công bố `ACCEPTING_TRAFFIC` dựa trên vòng đời ứng dụng; **không mặc định chứng minh mọi dependency ngoài luôn khỏe**. Theo thiết kế, health group readiness mặc định chú trọng `readinessState`; nếu bổ sung một database/cache/broker vào readiness group, phải tự đánh giá tác động lên routing toàn bộ replicas.

Ví dụ khi ứng dụng có `HealthIndicator` được đặt ID `ordersBackend`, có thể cấu hình readiness group kết hợp:

~~~properties
management.endpoint.health.group.readiness.include=readinessState,ordersBackend
~~~

Đây là **cấu hình minh họa** — project lab chưa có `ordersBackend`, không copy vào lab trừ khi bạn đã cung cấp indicator tương ứng. Health group aggregation trả tình trạng tổng hợp; nó không đồng nghĩa framework publish `AvailabilityChangeEvent<ReadinessState>` mới cho mọi lần check indicator fail.

Nếu dependency tạm thời lỗi nhưng app có fallback, rút mọi replica khỏi Service có thể gây outage nặng hơn. Không đưa dependency ngoài vào liveness một cách máy móc. Một policy tốt xác định rõ: yêu cầu nào cần dependency, error budget, fallback, retry, trạng thái nào thực sự nên refusing.

## 12. Phân biệt rõ với graceful shutdown

Khi process nhận tín hiệu shutdown bình thường, Boot có thể công bố `REFUSING_TRAFFIC` và phối hợp đóng embedded web server. Với graceful shutdown được hỗ trợ, server ngừng chấp nhận request mới theo cơ chế của nó, tiếp tục xử lý in-flight requests trong thời gian cho phép, sau đó dừng.

Cấu hình thường dùng:

~~~properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
~~~

**Cần hiểu:** `server.shutdown=graceful` là chính sách **dừng web server trong lúc đóng context**. Nó không biến mọi lần publish `REFUSING_TRAFFIC` trong runtime thành một lời gọi `close()`, và một event từ controller không tự invoke graceful shutdown. Ngược lại, shutdown thật có thể chấm dứt HTTP connector, làm probe không thể truy cập: không nên đòi lúc nào cũng nhìn được status 503 cuối cùng qua curl.

Kubernetes cần phối hợp readiness changes, endpoint propagation và `terminationGracePeriodSeconds`. Một Pod có thể còn nhận request từ connection đã tồn tại hoặc qua đường route chưa kịp cập nhật. Nếu yêu cầu business không chấp nhận thêm lệnh sau một mốc đóng nhất định, chính sách application-level cần có kiểm soát và idempotency tương ứng.

Không thử nghiệm shutdown bằng `kill -9` để kết luận graceful behavior; SIGKILL không cho JVM chạy shutdown hooks và callback cleanup.

## 13. Bảng chẩn đoán sự cố

| Triệu chứng | Giải thích khả dĩ | Việc cần kiểm chứng |
|---|---|---|
| Readiness probe 503 nhưng `/lab/process` trả 200 | State chỉ là tín hiệu; controller không tự check | Thử direct localhost và kiểm có custom filter không |
| Readiness 503 nhưng Pod vẫn nhận request qua PodIP | Client đi vòng qua Service/LB | Kiểm tra đường client, PodIP, network policy và ingress |
| App đã publish refusing nhưng Service còn gửi request trong vài giây | Chu kỳ probe/endpoints, cache/connection reuse | Kiểm thời gian publish, kubelet probes, endpoints và LB |
| Readiness refusing nhưng liveness vẫn UP | Process sống nhưng không muốn traffic | Đọc hai health groups và policy |
| Filter bật nhưng endpoint process vẫn 200 | Property không hiệu lực, filter không được đăng ký, path bypass | Kiểm bean condition, startup arguments, servlet path |
| Filter bật khiến health/liveness trả 503 dù app khỏe | Filter chặn cả management endpoints | Xem `shouldNotFilter(...)`, log và probe status |
| Sau refusal không thể gọi accept | Filter cũng chặn control/admin path | Thiết kế đường recovery được bảo vệ và miễn gate |
| HTTP 503 từ `/lab/process` nhưng readiness là accepting | Lỗi controller/security/gateway khác, không nhất thiết gate | Kiểm response body, access logs và status endpoint |
| Probe 404 | Chưa có Actuator, probes chưa enabled, path/custom config | Kiểm dependencies và `management.endpoint.health.probes.enabled` |
| K8s readiness luôn fail, local curl chạy được | Bind loopback trong container hoặc port/path sai | Kiểm `server.address`, manifest, connection từ Pod network |
| Management probe UP nhưng main port chết | Health chạy trên management connector riêng | Thử probe trên main port hoặc additional paths |
| Publish accept nhưng probe vẫn 503 | Indicator khác trong readiness group fail, custom mapping hoặc event chưa xử lý | Đọc health group aggregation và listeners |
| Controller thấy state vừa chuyển nhưng request trước vẫn hoàn tất | Filter kiểm tại thời điểm request đi qua | Phân biệt request in-flight và request mới |
| Shutdown probe không kết nối được | Embedded server đã dừng | Dựa thêm shutdown logs; không suy là state chưa đổi |
| Toàn bộ replicas bị rút khi DB chung outage | Readiness phụ thuộc shared DB quá chặt | Đánh giá fallback, retry và policy về external indicators |

Khi điều tra, ghi **thời điểm**, **state event**, **status probe**, **status controller**, **đường client đi qua**, và **số request đã vào controller**. Nếu chỉ có một log `REFUSING_TRAFFIC` thì chưa đủ kết luận hạ tầng hoặc tất cả HTTP endpoints đã từ chối.

## 14. Lựa chọn giải pháp theo mục tiêu

| Mục tiêu | Cơ chế chính | Điểm cần tránh |
|---|---|---|
| Báo platform instance tạm không ready | Publish `AvailabilityChangeEvent<ReadinessState>` | Mong controller tự trả 503 |
| Bộc lộ tình trạng readiness qua HTTP | Actuator readiness health group | Dùng endpoint nghiệp vụ làm probe mơ hồ |
| Ngừng routing qua Kubernetes Service | `readinessProbe` và Service endpoints | Giả định direct PodIP cũng bị chặn |
| Chặn request **ngay trong JVM** theo policy | Filter/WebFilter/interceptor/gateway hoặc guard trong handler | Chặn health/admin/recovery và in-flight không chủ ý |
| Dừng web server và drain request | Graceful shutdown + termination policy | Chỉ publish state mà không đóng context |
| Bảo vệ lệnh nghiệp vụ khi client retry | Idempotency key, transaction, dedupe | Dựa readiness để bảo đảm exactly-once |
| Giảm thời gian khởi động hoặc chặn traffic đến khi warm-up | Runner/readiness state và probe | Dựa dòng log “Started” hoặc listener “Ready” duy nhất |

**Lời khuyên thiết kế:** xác định thật rõ “không sẵn sàng” là **không được route request mới từ hạ tầng**, hay **không được thực hiện mọi lệnh mới trong tiến trình**. Hai yêu cầu có phạm vi và chi phí khác nhau. Readiness state là ngôn ngữ giao tiếp rất tốt với platform; nó không thay thế business authorization, throttling, admission control hoặc transaction semantics.

## 15. Bài tập thực hành và tiêu chí nghiệm thu

### Bài tập A — Chứng minh state không tự gate request

1. Chạy lab với `lab.gate.enabled=false`.
2. Ghi `/lab/status`, `/actuator/health/readiness` và `/actuator/health/liveness` sau startup.
3. POST `/lab/process`: kiểm HTTP 200, processed=1.
4. POST `/lab/control/refuse`: kiểm log `LAB_READINESS_CHANGED=REFUSING_TRAFFIC`.
5. GET readiness probe: HTTP 503/`OUT_OF_SERVICE`.
6. POST `/lab/process` lần nữa: **vẫn HTTP 200**, processed=2.
7. Giải thích vì sao hai endpoint cùng process đưa ra HTTP status khác nhau mà không mâu thuẫn.

### Bài tập B — Chứng minh filter tạo ra khác biệt

1. Restart lab với `--lab.gate.enabled=true`.
2. Khi accepting, `/lab/process` trả 200.
3. Publish refusing, xác minh readiness probe 503.
4. POST process: HTTP **503** với `{"error":"not_ready"}`.
5. GET `/lab/status`: counter không tăng do request vừa bị filter chặn.
6. Publish accepting; POST process lại trả 200.
7. Chỉ ra dòng `response.setStatus(...)` trong filter là nơi thực sự chặn request.

### Bài tập C — Readiness và đường đi của client

Vẽ hai đường đi: Client → Kubernetes Service → Pod và Client → PodIP → port. Giải thích vì sao fail readiness có thể loại instance khỏi Service nhưng không đóng cổng HTTP trên Pod. Nêu các yếu tố làm thay đổi thời điểm thấy kết quả: probe period, failure threshold, EndpointSlice update, kube-proxy/mesh và existing connections.

### Bài tập D — Readiness khác liveness

Giữ `REFUSING_TRAFFIC` nhưng liveness `CORRECT`; đối chiếu `/actuator/health/readiness` và `/actuator/health/liveness`. Giải thích vì sao Kubernetes có thể ngừng route mà không restart Pod. Thử đề xuất chính sách readiness cho dependency chung, phân biệt khi nào fallback đủ để vẫn nhận traffic.

### Bài tập E — Graceful shutdown

Trong bản JAR của lab, bổ sung cấu hình graceful shutdown. Dừng tiến trình bằng Ctrl+C hoặc SIGTERM hợp lệ, quan sát hành vi request mới và log shutdown. Không nhầm một connector dừng với việc chỉ publish refusing khi app vẫn đang chạy.

### Checklist nghiệm thu

- [ ] Nêu được 4 lớp: readiness state, readiness probe, infrastructure routing và application-level gate.
- [ ] Giải thích `ReadinessState.REFUSING_TRAFFIC` không tự làm mọi controller trả 503.
- [ ] Dựng và chạy thành công Spring Boot 3.5.x/Java 17 với Web + Actuator.
- [ ] Phát event refusing/accepting và đọc `ApplicationAvailability`.
- [ ] Gọi được readiness/liveness endpoints, phân biệt 200/503 theo lab mặc định.
- [ ] Chứng minh `/lab/process` vẫn trả 200 khi readiness refusing mà chưa bật filter.
- [ ] Chứng minh custom filter tạo 503 cho nghiệp vụ khi refusing.
- [ ] Biết vì sao cần bypass health/control endpoints khi xây filter trong lab.
- [ ] Phân biệt readiness gating và graceful shutdown.
- [ ] Giải thích routing theo Service không đồng nghĩa chặn direct PodIP.
- [ ] Hiểu mối liên hệ startup runner/ready event và trạng thái accepting.
- [ ] Không dùng readiness thay cho authorization, business validation hoặc idempotency.

## 16. Tài liệu chính thức

- Spring Boot 3.5 — Application Availability và readiness/liveness: https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html
- Spring Boot 3.5 — Actuator endpoints, Kubernetes probes, lifecycle và health groups: https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html
- Spring Boot 3.5 — `ApplicationAvailability` API: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/availability/ApplicationAvailability.html
- Spring Boot 3.5 — `AvailabilityChangeEvent` API: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/availability/AvailabilityChangeEvent.html
- Spring Boot 3.5 — `ReadinessState` API: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/availability/ReadinessState.html
- Spring Framework — Servlet Filter và Spring Web `OncePerRequestFilter`: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/filter/OncePerRequestFilter.html

**Kết luận:** `REFUSING_TRAFFIC` trả lời “instance **không nên được định tuyến request mới**”, không trả lời “mọi HTTP request trực tiếp **đã bị Spring tự chặn**”. Muốn kiểm chứng, luôn đo **cả readiness probe lẫn endpoint nghiệp vụ** trong hai cấu hình có và không có gate. Muốn chặn request, phải bổ sung một cơ chế có chủ sở hữu rõ ràng ở hạ tầng hoặc ứng dụng; muốn dừng server, dùng cơ chế shutdown thực sự.