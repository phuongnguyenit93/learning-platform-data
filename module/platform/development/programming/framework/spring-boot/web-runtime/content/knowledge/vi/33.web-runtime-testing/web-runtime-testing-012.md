# Kiểm thử vòng đời khởi động, lỗi cổng và graceful shutdown trong Spring Boot

**Ngữ cảnh:** Spring Boot → web-runtime → **Kiểm thử web runtime**.

Một ứng dụng web có thể trả `200 OK` trong test controller nhưng **không khởi động được** trên server vì port đang bị chiếm; hoặc khởi động được nhưng readiness báo sớm, nhận traffic trước khi nạp dữ liệu quan trọng; hoặc deploy phiên bản mới làm đứt các HTTP requests đang xử lý. Vì thế kiểm thử web runtime phải vượt ra ngoài `@WebMvcTest`/`MockMvc`: xác minh **trạng thái và sự kiện khởi động**, **bind socket thật và xử lý startup failure**, **đóng ApplicationContext**, **SmartLifecycle**, **graceful drain của HTTP server**, **SIGTERM/container orchestration** và những giới hạn của automation.

Bài sử dụng **Java 17+, Maven, Spring Boot 3.5.16, Spring MVC + embedded Tomcat, JUnit 5**. Có project đầy đủ biên dịch được, các integration tests chạy bằng `RANDOM_PORT`, một test giữ `ServerSocket` để ép port conflict, test `ApplicationRunner` cố ý thất bại, test shutdown khi HTTP request đang bị chặn bởi `CountDownLatch`, hướng dẫn thử `SIGTERM` bằng `curl` và checklist CI/Kubernetes. Các log/đầu ra minh họa được ghi rõ là **kỳ vọng từ mã**, không phải kết quả thực thi đã được đo tại máy của người đọc.

> **Cần phân biệt:** `ApplicationReadyEvent` nói startup lifecycle đã chạy đến mốc ready, còn readiness state, network acceptance, business dependencies và load balancer mới quyết định client có nhận dịch vụ hữu ích hay không. `ApplicationContext.close()` kiểm tra cơ chế teardown trong JVM, **không chứng minh** shell/Docker/Kubernetes đã chuyển SIGTERM đúng đến Java. `MockMvc` không mở cổng thật nên **không bao giờ là phép thử port-in-use đáng tin cậy**.

**Version:** Bài cố định Spring Boot 3.5.16 để đồng nhất API, là bản cuối trong dòng 3.5 đã hết hỗ trợ OSS năm 2026. Với production phải dùng phiên bản hoặc gói hỗ trợ còn vá bảo mật và kiểm tra lại các API/cấu hình tương ứng. Đặc biệt Spring Boot 4.x thay đổi một số test starters/module packages.

## 1. Bản đồ vòng đời của một web application

Khi chạy:

~~~java
SpringApplication.run(RuntimeLabApplication.class, args);
~~~

Spring Boot không chỉ gọi constructor controller. Nó tạo `Environment`, dựng `ApplicationContext`, đăng ký bean definitions, refresh context, tạo singleton beans, khởi động `SmartLifecycle`, tạo/khởi động embedded web server, gọi `ApplicationRunner`/`CommandLineRunner`, phát `ApplicationReadyEvent` rồi chuyển trạng thái readiness.

### 1.1. Thứ tự SpringApplication events quan trọng

Theo Spring Boot 3.5 docs, thứ tự chính khi startup **thành công**:

1. `ApplicationStartingEvent`: bắt đầu run, trước khi chuẩn bị Environment/context.
2. `ApplicationEnvironmentPreparedEvent`: Environment đã sẵn sàng, context chưa được tạo.
3. `ApplicationContextInitializedEvent`: context được tạo và initializers đã chạy, bean definitions chưa được load.
4. `ApplicationPreparedEvent`: bean definitions đã load, ngay trước refresh.
5. Trong refresh có `ServletWebServerInitializedEvent` và `ContextRefreshedEvent` (thứ tự chính xác với các sự kiện nội bộ phụ thuộc context/runtime).
6. `ApplicationStartedEvent`: context đã refresh, **chưa gọi runners**.
7. `AvailabilityChangeEvent<LivenessState>` với `LivenessState.CORRECT`.
8. `ApplicationRunner`/`CommandLineRunner` được thực thi theo `@Order`/`Ordered`.
9. `ApplicationReadyEvent`: runners đã hoàn tất thành công.
10. `AvailabilityChangeEvent<ReadinessState>` với `ReadinessState.ACCEPTING_TRAFFIC`.
11. Nếu startup lỗi ở bất kỳ giai đoạn thích hợp nào, `ApplicationFailedEvent` được phát thay cho hoàn tất ready.

~~~text
process start
  │ ApplicationStartingEvent
  ▼
prepare Environment
  │ ApplicationEnvironmentPreparedEvent
  ▼
create context
  │ ApplicationContextInitializedEvent
  │ ApplicationPreparedEvent
  ▼
refresh ApplicationContext
  ├─ create beans, @PostConstruct
  ├─ SmartLifecycle.start() (phase tăng)
  ├─ embedded web server initialized/started
  └─ ContextRefreshedEvent
  │
  ▼
ApplicationStartedEvent
  │ LivenessState.CORRECT
  ▼
ApplicationRunner / CommandLineRunner
  │ (có thể đọc cache, kiểm tra config, warm-up ngắn)
  ▼
ApplicationReadyEvent
  │ ReadinessState.ACCEPTING_TRAFFIC
  ▼
running HTTP requests
  │
  │ SIGTERM / context.close()
  ▼
ReadinessState.REFUSING_TRAFFIC; ContextClosedEvent
  │ LifecycleProcessor.onClose() / SmartLifecycle.stop(...)
  ├─ web server graceful drain in-flight requests
  ├─ custom workers stop theo phase
  └─ singleton @PreDestroy / destroy callbacks
  ▼
process exit
~~~

Sơ đồ là **khái quát**, không áp đặt thứ tự chính xác giữa mọi listener/bean do thư viện tạo. **`ContextClosedEvent` không có nghĩa server đã hoàn tất drain**, vì nó được phát **trước** `LifecycleProcessor.onClose()`.

### 1.2. Những sự kiện không thể bắt tin cậy bằng `@EventListener` bean

`ApplicationStartingEvent`, `ApplicationEnvironmentPreparedEvent` và một số failure xảy ra **trước khi ApplicationContext hoặc bean được tạo**. Vì vậy:

~~~java
@Component
class VeryEarlyListener {
    @EventListener
    public void onFailure(ApplicationFailedEvent event) { ... }
}
~~~

**Không đủ** để bao phủ startup failure rất sớm: bean listener có thể chưa tồn tại. Để bắt sự kiện tiền context hoặc failure của cả quá trình, đăng ký **trực tiếp vào `SpringApplication` trước `run()`**:

~~~java
SpringApplication app = new SpringApplication(RuntimeLabApplication.class);
app.addListeners(event -> {
    if (event instanceof ApplicationFailedEvent failed) {
        System.err.println("Startup failed: "
                + failed.getException().getClass().getSimpleName());
    }
});
app.run(args);
~~~

Đây là **mảnh minh họa**, không nằm trong main project ở mục 6. Import `org.springframework.boot.SpringApplication` và `org.springframework.boot.context.event.ApplicationFailedEvent`. Nếu cần một listener luôn có hiệu lực ở mọi cách khởi động, tham khảo đăng ký qua `META-INF/spring.factories` với key `org.springframework.context.ApplicationListener`. Tránh cho event listener thực hiện thao tác network/blocking rất lâu trên startup thread.

### 1.3. Startup “thành công” không bảo đảm nghiệp vụ sẵn sàng

Một context có thể refresh xong, HTTP connector bind và accept TCP, nhưng `ApplicationRunner` còn đang preload dữ liệu. Spring Boot sẽ chưa phát `ApplicationReadyEvent`/`ReadinessState.ACCEPTING_TRAFFIC` cho đến khi runners hoàn tất. Với Kubernetes, readiness probe giúp tránh route traffic quá sớm; tuy nhiên nếu load balancer không dùng readiness hoặc có direct access, HTTP port **có thể đã lắng nghe trước mốc ready**.

Đừng dùng `@PostConstruct` để làm migration dữ liệu dài hàng phút: nó chạy trong bean initialization, có thể gây failure trước khi startup events/health infrastructure sẵn sàng và làm khó chẩn đoán. Runner dùng cho nhiệm vụ khởi động cần hoàn tất trước ready, nhưng không nên chứa vô hạn hoặc secret side effects; các job kéo dài nên chạy nền có progress/readiness policy riêng.

## 2. Chọn tầng kiểm thử chính xác

| Mục tiêu | Công cụ | Có server/socket thật? | Giới hạn |
| --- | --- | --- | --- |
| Controller mapping/JSON/validation | `@WebMvcTest` + `MockMvc` | **Không** | Không kiểm tra port bind, Tomcat shutdown |
| Boot wiring đủ beans nhưng HTTP giả | `@SpringBootTest` (MOCK) + `@AutoConfigureMockMvc` | **Không** | Không có TCP listener |
| Bootstrap, startup events, readiness và HTTP thật | `@SpringBootTest(RANDOM_PORT)`, `@LocalServerPort` | **Có** | Framework test quản lý context/cache |
| Kiểm thử bind vào port đã biết | `SpringApplication.run(server.port=...)` trong test độc lập, giữ `ServerSocket` | **Có** và cố ý fail | Phải cô lập cổng/JVM, cleanup resources |
| Test startup dependency failure | `ApplicationContextRunner` (bean config) hoặc `SpringApplication.run` (full startup) | ContextRunner: **không**; SpringApplication: tùy web type | ContextRunner không thử embedded connector |
| Drain một request đang chạy | App context riêng + real HTTP + `CountDownLatch` + `context.close()` | **Có** | Không chứng minh OS SIGTERM |
| SIGTERM, PID 1 và graceful termination | Chạy executable JAR thành process con hoặc thủ công `kill -TERM` | **Có** | Cần Linux/container/CI hỗ trợ signal |
| Kubernetes rollout/readiness/preStop | Staging/ephemeral namespace + Service/Ingress | **Có**, qua hạ tầng | Không thể chứng minh bằng unit test trong JVM |
| Timeout/long-lived connections/proxy | E2E/stress/protocol test thật | **Có** | Đòi hỏi môi trường đúng như production |

**Quy tắc chọn nhanh:** Nếu lỗi phụ thuộc **OS socket, Servlet container hoặc signal**, chỉ `MockMvc` là chưa đủ. Nếu muốn kiểm tra thứ tự beans mà không cần network, một test `SmartLifecycle`/`ApplicationContextRunner` nhanh hơn và ổn định hơn việc boot Tomcat.

### 2.1. `MOCK`, `RANDOM_PORT`, `DEFINED_PORT`, `NONE`

`@SpringBootTest` có `webEnvironment`:

- `MOCK` (mặc định): dựng `WebApplicationContext` với Servlet mocks nếu MVC có trên classpath; **không** mở HTTP port.
- `RANDOM_PORT`: mở embedded server thật trên cổng được OS cấp tự động (port `0`), inject actual port bằng `@LocalServerPort`. Đây là lựa chọn cho HTTP integration tests bình thường.
- `DEFINED_PORT`: dùng `server.port` từ config hoặc 8080 mặc định. Dễ bị xung đột khi CI chạy song song; dùng chỉ khi muốn test chính bind một cổng xác định.
- `NONE`: ứng dụng non-web; phù hợp kiểm tra bean configuration, nhưng không có Servlet container.

**Đừng bắt cổng rảnh bằng cách hỏi OS rồi đóng socket mới boot server** (time-of-check/time-of-use race). Khi muốn tránh xung đột, dùng `server.port=0`. Khi **muốn cố tình tạo xung đột**, giữ `ServerSocket` **mở suốt lúc SpringApplication cố bind**, như mã test mục 9.

### 2.2. Khi nào `@WebMvcTest` báo “xanh” nhưng app không chạy được?

Ví dụ controller test pass vì:
- service đã được mock bằng `@MockitoBean`, trong khi production thiếu bean/config;
- controller mapping hoạt động trong mock dispatcher, nhưng server.port thực đã bị tiến trình khác chiếm;
- test không nạp HTTP connector, custom servlet registrations hoặc graceful-shutdown lifecycle;
- `@SpringBootTest(MOCK)` không thực sự startup Tomcat/Jetty;
- test không chạy `ApplicationRunner` theo con đường boot giống production, hoặc dùng test profiles loại startup check;
- một `@EventListener(ApplicationFailedEvent)` dưới dạng bean chỉ được tạo sau khi lỗi đã xảy ra.

Các tình huống đó không làm `@WebMvcTest` vô ích. Nó đúng cho **MVC contract**, nhưng không phải bằng chứng của **runtime startup**. Test suite cần bổ sung vài bài đúng tầng.

## 3. Xác minh thứ tự startup và readiness

### 3.1. Dùng event recorder để quan sát, không dựa vào timestamps ngẫu nhiên

Cách vững chắc là có một bean ghi lại các mốc lifecycle vào thread-safe list:
- `SmartLifecycle.start()`;
- `ApplicationStartedEvent`;
- `ApplicationReadyEvent`;
- `ContextClosedEvent`;
- `SmartLifecycle.stop(Runnable)`;
- `@PreDestroy`.

Sau `SpringApplication.run(...)` trả context, kiểm tra event list và `ApplicationAvailability.getReadinessState()`. Với context đơn giản, worker lifecycle start **trước** ApplicationStarted/Ready; close event đến **trước** worker stop, destroy callback sau stop.

**Không assert exact log timestamp hay toàn bộ log line Boot.** Logger format, thread name, PID, GC pause, startup optimizations và auto-config bean count thay đổi theo môi trường. Hãy assert những **partial ordering invariants** được Spring contract bảo đảm.

### 3.2. `ApplicationStartedEvent` khác `ApplicationReadyEvent`

Một `ApplicationRunner` lỗi sẽ xảy ra **sau `ApplicationStartedEvent` nhưng trước `ApplicationReadyEvent`**. Khi đó:
- Server có thể đã bind port.
- Boot phát `ApplicationFailedEvent` và đóng context đang startup.
- Readiness không đạt `ACCEPTING_TRAFFIC` cho lần run đó.
- Không nên quảng bá endpoint “ready” chỉ vì đã thấy log “Tomcat started”.

Có thể tạo test cố tình ném `IllegalStateException("intentional runner failure")` trong runner. Test nên assert `SpringApplication.run` thất bại và listener trước-context nhận `ApplicationFailedEvent`. Đó là cách kiểm tra ứng dụng **không tuyên bố sẵn sàng** khi startup checks không đạt.

### 3.3. Availability API và Actuator probes

Spring Boot Actuator hỗ trợ:
- `ApplicationAvailability`: đọc current `LivenessState` và `ReadinessState` trong JVM.
- `/actuator/health/liveness`, `/actuator/health/readiness` khi bật probe groups.
- `AvailabilityChangeEvent.publish(...)`: ứng dụng đổi trạng thái khi cần ngừng nhận traffic/đánh dấu không khỏe.

Ví dụ properties:

~~~properties
management.endpoint.health.probes.enabled=true
management.endpoints.web.exposure.include=health
~~~

Readiness và liveness khác nhau:
- **Liveness**: JVM có còn trong trạng thái tự phục hồi được không? Không nên fail chỉ vì database tạm downtime, dễ tạo restart storm.
- **Readiness**: instance có nên nhận traffic mới không? Có thể fail khi warm-up hoặc drain.
- Một readiness 200 **không** thay kiểm thử feature path `GET /ping` hoặc database business contract.
- Trong shutdown, HTTP connector có thể đã ngừng nhận requests, nên probe có thể nhận **connection refused** thay vì JSON REFUSING_TRAFFIC; không hard-code “mọi shutdown probe đều trả 503”.

## 4. Lỗi cổng đã sử dụng: vì sao cần test bind thật?

Port conflict thường xảy ra khi:
- đã có JVM/Node/nginx/process khác giữ `0.0.0.0:8080` hoặc `127.0.0.1:8080`;
- hai replicas/dev profiles khởi động với cùng static port trên một host;
- Docker port mapping trùng host port hoặc Kubernetes hostPort xung đột;
- một test trước không close context/HTTP server, để lại listener;
- CI chạy song song nhiều suites ở `DEFINED_PORT`;
- application thử bind địa chỉ không tồn tại hoặc không có quyền, khác với EADDRINUSE.

### 4.1. Nhận diện lỗi thực

Triệu chứng có thể là:
- `Port 8080 was already in use` trong failure analysis của Boot;
- `java.net.BindException: Address already in use` trong nested exception;
- `ApplicationContextException: Unable to start web server` hoặc wrapped web-server exception;
- `ApplicationFailedEvent`; application không trả về usable context.

**Không khẳng định root exception type/string luôn cố định** giữa Tomcat/Jetty/Undertow/Netty/OS. Quan trọng là behavior: **startup fail, listener failure nhận event, không chiếm thêm socket thành công, không phát ready**. Test thông minh giữ port, gọi real `SpringApplication.run` và assert thất bại, tránh match toàn bộ stderr có thể thay theo version/localization.

### 4.2. Test port conflict an toàn và quyết định được

~~~java
try (ServerSocket occupied = new ServerSocket(
         0, 50, InetAddress.getByName("127.0.0.1"))) {
    int port = occupied.getLocalPort();
    // Socket vẫn MỞ trong suốt SpringApplication.run.
    // Spring Boot sẽ thử bind chính 127.0.0.1:port.
}
~~~

Lợi ích:
- Không đụng cổng 8080 cố định của đồng nghiệp/CI.
- OS cấp port ngẫu nhiên đang thật sự được giữ.
- Java `try-with-resources` đảm bảo giải phóng sau test.
- `server.address=127.0.0.1` đồng nhất interface với ServerSocket, tránh bind trên IPv4/IPv6 khác.
- **Không đóng occupied socket trước app.run**, nếu không test có thể pass nhầm.
- Kiểm tra `ApplicationFailedEvent` bằng listener được gắn vào `SpringApplication` trước `run`; không dựa vào bean event listener chưa được tạo.

### 4.3. Phân biệt “bind fail” với “port reachable but unhealthy”

- `connection refused` khi client gọi một port không có listener **không đồng nghĩa** app đã fail startup: có thể gọi sai địa chỉ, host firewall, LB/backend routing.
- Port conflict failure là **khi server cố bind** một địa chỉ/cổng đã được dùng.
- Hai JVM có thể bind các địa chỉ khác nhau trên cùng số port tùy OS/IPv4/IPv6/socket flags; đó là lý do test bắt buộc chỉ rõ `server.address`.
- Docker host port collision xảy ra ở daemon port publish, **có thể trước khi JVM bắt đầu**; test Spring port bind trong container không mô phỏng nguyên trạng lỗi host mapping.
- Nếu Linux process bị giữ ở `TIME_WAIT` sau khi đóng, đó không nhất thiết là active listening socket; đừng suy ra chỉ từ netstat grep.

### 4.4. Lệnh kiểm tra bên ngoài app

~~~bash
# Linux:
ss -ltnp | grep ':8080'
# Hoặc:
lsof -nP -iTCP:8080 -sTCP:LISTEN

# Windows PowerShell:
# Get-NetTCPConnection -LocalPort 8080 -State Listen
# và tra PID với Get-Process -Id <PID>
~~~

Chạy lệnh theo OS, quyền truy cập và namespace đúng. Không kill PID ngẫu nhiên chỉ vì một cổng đang listen; xác định owner/process trước. Trong Kubernetes xem Service/Pod IP/hostPort và logs của đúng replica.

## 5. Graceful shutdown: hành vi HTTP cần test

Spring Boot 3.5 bật **graceful shutdown mặc định** cho bốn embedded servers: **Tomcat, Jetty, Undertow, Reactor Netty**, cả Servlet và reactive stacks. `server.shutdown=graceful` cho phép chờ in-flight requests trong phase stop phù hợp và ngừng nhận new requests. `server.shutdown=immediate` tắt cơ chế graceful.

~~~properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=8s
~~~

**`timeout-per-shutdown-phase` không phải tổng thời gian process stop.** Mỗi phase của `SmartLifecycle` có budget riêng; còn `ContextClosedEvent`, singleton destruction, JVM shutdown hook, preStop và logging flush. Với nhiều phases có thể vượt quá 8s tổng. Trong Kubernetes cần `terminationGracePeriodSeconds` đủ lớn cho **preStop + tổng các phases quan trọng + destruction + margin**.

### 5.1. Server reject requests mới khác nhau thế nào?

| Embedded server Boot 3.5 | Hành vi thường được tài liệu mô tả khi graceful drain |
| --- | --- |
| **Tomcat** | Dừng nhận new requests ở network layer |
| **Jetty** | Dừng nhận new requests ở network layer |
| **Reactor Netty** | Dừng nhận new requests ở network layer |
| **Undertow** | Có thể vẫn accept connection nhưng trả **503 Service Unavailable** |

Một reverse proxy có thể trả 502/503/504 hoặc connection error tùy timing/hop. Với keep-alive/HTTP2 connections có sẵn, cách xử lý chi tiết cũng tùy server. **Không hard-assert rằng request mới trong shutdown phải luôn trả 503**. Thay vào đó test bất biến:
1. Request bắt đầu **trước** shutdown có cơ hội nhận response thành công trong grace window.
2. Context close chưa hoàn tất khi một request vẫn đang xử lý và chưa vượt timeout.
3. Sau khi close hoàn tất, embedded server không tiếp tục phục vụ request mới.
4. Resources/lifecycle callbacks được dừng/hủy theo thứ tự hợp lý.

### 5.2. `SmartLifecycle` và thứ tự stop

Spring Framework quản lý component hoạt động qua `Lifecycle` và `SmartLifecycle`:
- `start()` theo phase **tăng dần**.
- `stop(Runnable callback)` theo phase **giảm dần**.
- `SmartLifecycle.isAutoStartup()` mặc định true.
- `SmartLifecycle.DEFAULT_PHASE` là `Integer.MAX_VALUE`.
- Regular `Lifecycle` không auto-start giống SmartLifecycle và thường được xem phase 0.
- Bean dependency có thể override phase: bean phụ thuộc start sau và stop trước dependency.
- `stop(Runnable)` **phải gọi callback.run() sau khi thực sự dừng**, không được bỏ quên hay gọi quá sớm.

Embedded web server graceful shutdown diễn ra ở một trong các phase stop đầu tiên. Một custom bean có phase thấp (ví dụ 0) thường stop **sau** web server drain, hữu ích nếu worker resource còn được HTTP handler dùng. Một bean phase cực cao có thể stop **trước** server; đừng vô tình đóng DB/HTTP client đang phục vụ in-flight requests tại phase cao.

### 5.3. ContextClosedEvent đến trước bean destruction

Khi `ConfigurableApplicationContext.close()`:
1. `ContextClosedEvent` được publish (listener có thể thấy server vẫn đang có request).
2. `LifecycleProcessor.onClose()` dừng lifecycle beans/web server theo phase; chờ callback tối đa per-phase timeout.
3. Destroy singleton beans (ví dụ `@PreDestroy`/`DisposableBean.destroy`/destroy method).
4. Context đánh dấu closed/giải phóng các structures.

**Không đóng DataSource trong `ContextClosedEvent`** nếu HTTP handlers còn dùng DB; nó có thể làm chính request đang được graceful drain thất bại. Không sleep lâu trong event listener vì sẽ làm chậm việc bắt đầu lifecycle stop.

### 5.4. Graceful không phải exactly-once và không chống SIGKILL

Nếu user POST tạo đơn hàng, server commit transaction rồi connection mất khi pod bị kill, client có thể retry và tạo trùng. Graceful chỉ giảm rủi ro cắt request, **không đảm bảo exactly-once**. Bài toán đúng cần `Idempotency-Key`, transaction/outbox, durable queues, retry/backoff và business reconciliation.

`SIGKILL`, JVM crash, máy mất điện, OOM-kill hoặc `Runtime.halt` có thể bỏ qua shutdown hook/`@PreDestroy`. Test SIGTERM bằng `kill -TERM`, không dùng `kill -9` để “xem graceful có chạy không”.

## 6. Project Spring Boot hoàn chỉnh: sự kiện, port, request đang chạy

Project mẫu thiết kế với **một executable JAR** có:
- Event journal ghi thứ tự mốc startup/close.
- Một `SmartLifecycle` bean có phase 0 để quan sát start/stop callbacks.
- `ApplicationRunner` có công tắc giả lập startup failure.
- `GET /ping` trả nhanh.
- `GET /hold` chờ **test-controlled `CountDownLatch`** khi được test arm, giúp test in-flight request **không cần đoán sleep bao lâu**.
- `GET /sleep?ms=7000` cho thử nghiệm SIGTERM thủ công với curl.
- Các test JUnit tạo **contexts riêng** và đóng chúng trong finally, không phá Spring TestContext cache.

### 6.1. Cây thư mục

~~~text
runtime-lifecycle-lab/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/runtimelab/
    │   │   ├── RuntimeLabApplication.java
    │   │   ├── EventJournal.java
    │   │   ├── WorkerLifecycle.java
    │   │   ├── StartupCheckRunner.java
    │   │   ├── HoldGate.java
    │   │   └── ProbeController.java
    │   └── resources/application.properties
    └── test/
        └── java/com/example/runtimelab/
            ├── RuntimeHttpTest.java
            ├── StartupFailureTest.java
            ├── PortConflictTest.java
            └── GracefulShutdownTest.java
~~~

### 6.2. `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>runtime-lifecycle-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>
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
            </plugin>
        </plugins>
    </build>
</project>
~~~

Các dependency versions do Spring Boot BOM quản lý. Demo dùng embedded Tomcat từ `spring-boot-starter-web`, không cần WebFlux. `spring-boot-starter-actuator` phục vụ health probes, không tự expose mọi actuator endpoints.

### 6.3. `src/main/java/com/example/runtimelab/RuntimeLabApplication.java`

~~~java
package com.example.runtimelab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RuntimeLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(RuntimeLabApplication.class, args);
    }
}
~~~

`SpringApplication.run` mặc định đăng ký JVM shutdown hook. Main **không gọi `context.close()` ngay** sau run vì server sẽ bị shutdown tức thì. Trong các JUnit tests, chúng ta tạo context riêng có kiểm soát, gọi close rõ ràng.

### 6.4. `src/main/java/com/example/runtimelab/EventJournal.java`

~~~java
package com.example.runtimelab;

import jakarta.annotation.PreDestroy;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.context.event.ContextClosedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class EventJournal {
    private static final Logger log =
            LoggerFactory.getLogger(EventJournal.class);

    private final List<String> events =
            new CopyOnWriteArrayList<>();
    private final CountDownLatch closeStarted =
            new CountDownLatch(1);

    public void mark(String event) {
        events.add(event);
        log.info("LIFECYCLE {}", event);
    }

    @EventListener
    public void onStarted(ApplicationStartedEvent event) {
        mark("application-started");
    }

    @EventListener
    public void onReady(ApplicationReadyEvent event) {
        mark("application-ready");
    }

    @EventListener
    public void onClosed(ContextClosedEvent event) {
        mark("context-closed");
        closeStarted.countDown();
    }

    public boolean awaitCloseStarted(long value, TimeUnit unit)
            throws InterruptedException {
        return closeStarted.await(value, unit);
    }

    public List<String> snapshot() {
        return List.copyOf(events);
    }

    @PreDestroy
    public void destroy() {
        mark("bean-destroy");
    }
}
~~~

`CopyOnWriteArrayList` giúp test đọc log mốc từ thread khác khi close đang chạy. Đây là **lab journal giữ trong RAM**, không thay logging/metrics backend. `closeStarted` là tín hiệu test để biết sự kiện context close đã được phát, **không** khẳng định web server đã drain xong. `@PreDestroy` ghi lại bước destroy sau lifecycle stop processing.

### 6.5. `src/main/java/com/example/runtimelab/WorkerLifecycle.java`

~~~java
package com.example.runtimelab;

import java.util.concurrent.atomic.AtomicBoolean;
import org.springframework.context.SmartLifecycle;
import org.springframework.stereotype.Component;

@Component
public class WorkerLifecycle implements SmartLifecycle {
    private final AtomicBoolean running = new AtomicBoolean();
    private final EventJournal journal;

    public WorkerLifecycle(EventJournal journal) {
        this.journal = journal;
    }

    @Override
    public void start() {
        running.set(true);
        journal.mark("worker-start");
    }

    @Override
    public void stop(Runnable callback) {
        try {
            running.set(false);
            journal.mark("worker-stop");
        } finally {
            // Spring LifecycleProcessor cần completion callback.
            callback.run();
        }
    }

    @Override
    public void stop() {
        running.set(false);
    }

    @Override
    public boolean isRunning() {
        return running.get();
    }

    @Override
    public int getPhase() {
        // Thấp hơn phase graceful stop của embedded web server.
        // Worker stop SAU khi server được drain trong Boot 3.5.
        return 0;
    }
}
~~~

Lưu ý:
- `SmartLifecycle` được auto-start trong context refresh nếu `isAutoStartup()` mặc định true.
- Phase 0 giúp worker tồn tại cho tới giai đoạn sau server graceful stop, thay vì dừng quá sớm.
- `stop(Runnable)` synchronous trong demo nên gọi callback ngay **sau khi** chuyển state sang stopped.
- Một worker production còn xử lý tasks async cần **drain thật rồi mới callback**; gọi callback khi work chưa xong có thể khiến context destroy beans đang được dùng.
- Đừng lấy `@Order` trên bean thay cho `getPhase`. Dependencies có thể ảnh hưởng thứ tự.

### 6.6. `src/main/java/com/example/runtimelab/StartupCheckRunner.java`

~~~java
package com.example.runtimelab;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;

@Component
public class StartupCheckRunner implements ApplicationRunner {
    private final boolean fail;

    public StartupCheckRunner(
            @Value("${demo.fail-runner:false}") boolean fail) {
        this.fail = fail;
    }

    @Override
    public void run(ApplicationArguments args) {
        if (fail) {
            throw new IllegalStateException(
                    "intentional runner failure");
        }
    }
}
~~~

Đây là **failure injection chỉ dành cho lab**. Khi `--demo.fail-runner=true`:
1. Context đã refresh.
2. `ApplicationStartedEvent` có thể đã được phát.
3. Runner ném lỗi.
4. `ApplicationReadyEvent` không được phát.
5. `ApplicationFailedEvent` được gửi tới các listeners đã đăng ký đủ sớm; Boot dọn context.

**Không dùng một endpoint không auth để bật fail-runner trên production.** Với startup checks thật (cấu hình chứng chỉ, database schema), phải quyết định liệu failing fast có đúng yêu cầu triển khai không. Nếu downstream tạm thời unavailable, readiness báo not-ready và retries có thể tốt hơn restart storm; không có một lựa chọn đúng mọi hệ thống.

### 6.7. `src/main/java/com/example/runtimelab/HoldGate.java`

~~~java
package com.example.runtimelab;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import org.springframework.stereotype.Component;

@Component
public class HoldGate {
    private final AtomicBoolean armed = new AtomicBoolean();
    private final CountDownLatch entered = new CountDownLatch(1);
    private final CountDownLatch released = new CountDownLatch(1);

    public void arm() {
        armed.set(true);
    }

    public boolean awaitEntered(long duration, TimeUnit unit)
            throws InterruptedException {
        return entered.await(duration, unit);
    }

    public void release() {
        released.countDown();
    }

    public void blockIfArmed() throws InterruptedException {
        if (armed.get()) {
            entered.countDown();
            if (!released.await(15, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "lab hold request timed out");
            }
        }
    }
}
~~~

`HoldGate` tồn tại để **kiểm thử đồng bộ hóa không phụ thuộc sleep**. Test bật `arm()` trước request; handler báo `entered` khi nó đã thực sự chạy, rồi bị giữ đến khi test gọi `release()`. Ngưỡng 15s **bảo vệ test khỏi treo vô hạn** nếu callback quên release. Production không có lý do để expose kiểu gate này, và app lab chỉ bind localhost.

**Không cho phép nhiều parallel test requests cùng dùng gate**: `CountDownLatch` là one-shot trong một ApplicationContext. Mỗi graceful test tạo một context riêng; nếu muốn test multi-client, thiết kế gate per-request và active count thay vì dùng global latch.

### 6.8. `src/main/java/com/example/runtimelab/ProbeController.java`

~~~java
package com.example.runtimelab;

import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProbeController {
    private final HoldGate gate;

    public ProbeController(HoldGate gate) {
        this.gate = gate;
    }

    @GetMapping(path = "/ping",
                produces = MediaType.TEXT_PLAIN_VALUE)
    public String ping() {
        return "pong\n";
    }

    @GetMapping(path = "/hold",
                produces = MediaType.TEXT_PLAIN_VALUE)
    public String hold() throws InterruptedException {
        gate.blockIfArmed();
        return "finished\n";
    }

    @GetMapping(path = "/sleep",
                produces = MediaType.TEXT_PLAIN_VALUE)
    public ResponseEntity<String> sleep(
            @RequestParam(defaultValue = "5000") long ms)
            throws InterruptedException {
        if (ms < 0 || ms > 15000) {
            return ResponseEntity.badRequest()
                    .body("ms must be 0..15000\n");
        }
        Thread.sleep(ms);
        return ResponseEntity.ok("slept " + ms + "ms\n");
    }
}
~~~

`/ping` phục vụ health/function smoke test. `/hold` dùng trong automated graceful test; `/sleep` giúp tạo request 7s trong quá trình SIGTERM thủ công. `Thread.sleep` chỉ để tái hiện request đang chạy và **không phải ứng dụng production**. Trong production, request có thể chậm do SQL/network/synchronization, cần enforce timeouts và cách retry phù hợp.

### 6.9. `src/main/resources/application.properties`

~~~properties
spring.application.name=runtime-lifecycle-lab

# Không expose các endpoint demo ra mạng ngoài.
server.address=127.0.0.1
server.port=8080

# Spring Boot 3.5 mặc định đã graceful, set explicit để học.
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=8s

management.endpoint.health.probes.enabled=true
management.endpoints.web.exposure.include=health

demo.fail-runner=false
logging.level.com.example.runtimelab=INFO
~~~

Chú ý:
- `server.address=127.0.0.1` chỉ cho truy cập loopback trên host; khi container hóa phải override đúng Pod binding và thêm security/network policy.
- `server.port=8080` tiện chạy JAR bằng tay. **Integration tests** sẽ override sang `server.port=0` để tránh conflict.
- `8s` là **mỗi lifecycle shutdown phase**, không phải cả JVM.
- Actuator probes có thể dùng `/actuator/health/readiness`, nhưng trong quá trình close port có thể đã không accept nên external probe không luôn trả JSON.
- Không bật actuator shutdown endpoint chỉ để test; khi thực sự cần, endpoint này đòi hỏi thiết kế bảo vệ đặc biệt.

## 7. Test HTTP startup thành công với RANDOM_PORT

File `src/test/java/com/example/runtimelab/RuntimeHttpTest.java`:

~~~java
package com.example.runtimelab;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.availability.ApplicationAvailability;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.web.client.RestClient;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(webEnvironment =
        SpringBootTest.WebEnvironment.RANDOM_PORT)
class RuntimeHttpTest {
    @LocalServerPort
    int port;

    @Autowired
    EventJournal journal;

    @Autowired
    ApplicationAvailability availability;

    @Test
    void realHttpServerIsReadyAfterRunners() {
        String body = RestClient.create().get()
                .uri("http://127.0.0.1:" + port + "/ping")
                .retrieve()
                .body(String.class);

        assertEquals("pong\n", body);
        assertEquals(ReadinessState.ACCEPTING_TRAFFIC,
                     availability.getReadinessState());

        List<String> events = journal.snapshot();
        int worker = events.indexOf("worker-start");
        int started = events.indexOf("application-started");
        int ready = events.indexOf("application-ready");

        assertTrue(worker >= 0, "SmartLifecycle did not start");
        assertTrue(started > worker,
                   "ApplicationStartedEvent should follow refresh");
        assertTrue(ready > started,
                   "ReadyEvent should follow StartedEvent");
    }
}
~~~

**Giá trị của test:**
- Dùng cổng do OS chọn nên không phụ thuộc static `8080`.
- `RestClient.create()` là **HTTP client thật**, nên request đi qua TCP đến embedded Tomcat.
- Assert body tránh tình trạng server lắng nghe nhưng route không hoạt động.
- Kiểm tra `ApplicationAvailability` sau `SpringApplication.run` do Spring Test tạo đã hoàn tất; readiness được đánh dấu accepting.
- Event recorder xác minh partial ordering, không so exact timestamps.
- `@SpringBootTest` tự khởi tạo/đóng context theo test framework; **không gọi `context.close()` thủ công trong test này**, tránh phá Spring TestContext cache.

Nếu test fail chỉ ở `availability.getReadinessState()`, kiểm tra application đã publish custom readiness state hay chưa hoặc có Spring context hierarchy/phần khác thay đổi trạng thái. Ví dụ lab không đổi readiness bằng tay.

## 8. Test startup thất bại ở ApplicationRunner

Một số startup errors xuất hiện **sau khi HTTP connector được tạo**. Ta muốn chắc chắn Boot phát `ApplicationFailedEvent` và **không phát `ApplicationReadyEvent`**.

File `src/test/java/com/example/runtimelab/StartupFailureTest.java`:

~~~java
package com.example.runtimelab;

import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.Test;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.context.event.ApplicationFailedEvent;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.ApplicationEvent;
import org.springframework.context.ApplicationListener;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class StartupFailureTest {

    @Test
    void runnerFailureIsNotReadyAndEmitsFailedEvent() {
        SpringApplication app =
                new SpringApplication(RuntimeLabApplication.class);

        AtomicBoolean ready = new AtomicBoolean();
        AtomicReference<Throwable> failure =
                new AtomicReference<>();

        // Đăng ký TRƯỚC run để bắt events kể cả khi context lỗi.
        app.addListeners((ApplicationListener<ApplicationEvent>) event -> {
            if (event instanceof ApplicationReadyEvent) {
                ready.set(true);
            }
            if (event instanceof ApplicationFailedEvent failed) {
                failure.set(failed.getException());
            }
        });

        RuntimeException thrown = assertThrows(
                RuntimeException.class,
                () -> app.run(
                    "--server.port=0",
                    "--server.address=127.0.0.1",
                    "--demo.fail-runner=true",
                    "--spring.main.banner-mode=off"));

        assertNotNull(thrown);
        assertFalse(ready.get());
        assertNotNull(failure.get());
        assertTrue(containsMessage(failure.get(),
                "intentional runner failure"));
    }

    private static boolean containsMessage(
            Throwable error, String fragment) {
        for (Throwable cursor = error;
             cursor != null; cursor = cursor.getCause()) {
            if (String.valueOf(cursor.getMessage())
                    .contains(fragment)) {
                return true;
            }
        }
        return false;
    }
}
~~~

**Giải thích:**
- `--server.port=0` tránh xung đột với test chạy song song.
- Failure injection đến từ `StartupCheckRunner`, nên không cần database/network thật.
- Failure listener được register **ngoài context**, đủ sớm để nhận `ApplicationFailedEvent` ngay cả lúc application startup không hoàn thành.
- Assert không có `ApplicationReadyEvent`, vì runner ném exception trước mốc ready.
- `containsMessage` đi dọc cause chain thay vì assert exact top-level exception type/message, vì framework có thể wrap dưới `IllegalStateException`/`ApplicationContextException`.
- SpringApplication trên failure sẽ có cơ chế cleanup partial context; không gọi `System.exit` trong test.
- Nếu exception do một failure khác (ví dụ port conflict), cause chain sẽ không có chuỗi intentional và test **fail đúng**, tránh false positive “bất kỳ startup failure nào cũng đạt”.

**Không** dùng `@SpringBootTest` cho test cố tình fail context kiểu này rồi mong nhận `ApplicationFailedEvent` qua `@Autowired` bean: Spring TestContext sẽ fail trước khi gọi test method. Tạo `SpringApplication` riêng bên trong JUnit method như trên mới kiểm soát được expected exception.

## 9. Test port conflict bằng ServerSocket đang giữ

File `src/test/java/com/example/runtimelab/PortConflictTest.java`:

~~~java
package com.example.runtimelab;

import java.net.InetAddress;
import java.net.ServerSocket;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.Test;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.context.event.ApplicationFailedEvent;
import org.springframework.context.ApplicationListener;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;

class PortConflictTest {

    @Test
    void occupiedLoopbackPortFailsRealServerStartup()
            throws Exception {

        // OS cấp một cổng IPv4 loopback thực sự và vẫn GIỮ cổng.
        try (ServerSocket occupied = new ServerSocket(
                0, 50, InetAddress.getByName("127.0.0.1"))) {

            int busyPort = occupied.getLocalPort();
            SpringApplication app =
                    new SpringApplication(RuntimeLabApplication.class);

            AtomicReference<Throwable> failure =
                    new AtomicReference<>();

            app.addListeners(
                (ApplicationListener<ApplicationFailedEvent>) event ->
                    failure.set(event.getException()));

            RuntimeException thrown = assertThrows(
                RuntimeException.class,
                () -> app.run(
                    "--server.address=127.0.0.1",
                    "--server.port=" + busyPort,
                    "--spring.main.banner-mode=off"));

            assertNotNull(thrown);
            assertNotNull(failure.get(),
                "Expected ApplicationFailedEvent");
        }
        // Chỉ SAU test, try-with-resources mới release occupied port.
    }
}
~~~

**Vì sao test này có giá trị mà MOCK không có?**
- Nó khởi động **Tomcat thật** trên một cổng đang được chiếm thật.
- `ApplicationFailedEvent` được bắt qua listener gắn trước `run()`, không phụ thuộc context bean đã khởi tạo.
- `assertThrows(RuntimeException.class, ...)` không yêu cầu một exception class cố định; failure analyzer và nested `BindException` có thể khác giữa embedded servers.
- Không khóa static port 8080, giảm interference trong CI.

**Giới hạn thực nghiệm:** một số OS có socket configuration/reuse behavior khác nhau, nhưng giữ `ServerSocket` IPv4 loopback có cùng `server.address` là setup đáng tin trong phần lớn môi trường Java. Nếu test thực tế bất ngờ bind thành công, trước hết xác minh Java/Tomcat có cùng network namespace, IPv4 bind address, port và socket options; không sửa test thành “chỉ cần log có port” vì như thế mất ý nghĩa test.

### 9.1. Các kiểu lỗi không được lẫn với port occupied

| Lỗi | Ví dụ | Phép thử đúng |
| --- | --- | --- |
| **EADDRINUSE** | Process khác giữ `127.0.0.1:8080` | Giữ ServerSocket trên cùng IP/port, assert startup fail |
| **EADDRNOTAVAIL** | App bind IP không tồn tại trên host | Cấu hình server.address sai cố ý trong isolated test |
| **EACCES/permission** | OS ngăn bind port/host policy | Test trong container/OS tương ứng |
| **Host port collision Docker** | Hai containers publish host port giống nhau | Docker orchestration test, có thể fail trước Java |
| **Timeout connecting downstream** | Port của backend không listen | Client HTTP connection failure, không phải own server bind |
| **Port rảnh nhưng controller lỗi** | Server 200/500 tùy route | RANDOM_PORT HTTP test |

Không dùng `@SpringBootTest(DEFINED_PORT)` chạy song song mặc định cho mọi test trong một repo lớn: chính bộ test có thể tạo cổng tranh chấp ngoài ý muốn. Port conflict phải là **một test chủ đích**, được cô lập rõ.

## 10. Automated graceful shutdown test: request thực sự đang xử lý

**Mục tiêu kiểm tra:** khi request vào controller đã chạy và chưa hoàn tất, `context.close()` ở thread khác không được phá response ngay; server sẽ chờ in-flight request (nằm trong timeout 8s), rồi process/context đóng sau response. Dùng latch để chắc chắn request **đã vào handler** trước khi đóng.

**Không** đóng context của `@SpringBootTest(RANDOM_PORT)` đang được Spring TestContext cache quản lý, vì có thể làm các test classes sau fail ngẫu nhiên. Test dưới đây **không có @SpringBootTest**, mà tạo fresh `SpringApplication` và giữ context riêng.

File `src/test/java/com/example/runtimelab/GracefulShutdownTest.java`:

~~~java
package com.example.runtimelab;

import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.Test;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.web.servlet.context.ServletWebServerApplicationContext;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.web.client.RestClient;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class GracefulShutdownTest {

    @Test
    void inflightHttpRequestFinishesBeforeContextCloses()
            throws Exception {

        SpringApplication application =
                new SpringApplication(RuntimeLabApplication.class);

        ConfigurableApplicationContext context = application.run(
                "--server.port=0",
                "--server.address=127.0.0.1",
                "--server.shutdown=graceful",
                "--spring.lifecycle.timeout-per-shutdown-phase=8s",
                "--spring.main.banner-mode=off");

        ExecutorService callers =
                Executors.newSingleThreadExecutor();
        HoldGate gate = context.getBean(HoldGate.class);
        EventJournal journal = context.getBean(EventJournal.class);
        AtomicReference<Throwable> closeError =
                new AtomicReference<>();

        try {
            // Mỗi test tạo context mới nên latch chưa bị sử dụng.
            gate.arm();
            int port =
                ((ServletWebServerApplicationContext) context)
                    .getWebServer().getPort();

            Future<String> request = callers.submit(
                    () -> RestClient.create().get()
                        .uri("http://127.0.0.1:" + port + "/hold")
                        .retrieve().body(String.class));

            // Chỉ đóng KHI controller đã thật sự nhận request.
            assertTrue(gate.awaitEntered(10, TimeUnit.SECONDS),
                       "HTTP handler did not enter");

            Thread closer = new Thread(() -> {
                try {
                    context.close();
                } catch (Throwable error) {
                    closeError.set(error);
                }
            }, "context-close-test");
            closer.start();

            // ContextClosedEvent xảy ra trước web-server drain.
            assertTrue(journal.awaitCloseStarted(
                    5, TimeUnit.SECONDS));

            // Khi request còn bị gate giữ, graceful close còn chờ.
            assertFalse(request.isDone());
            assertTrue(closer.isAlive());

            // Cho request hoàn tất trước khi hết grace 8s.
            gate.release();
            assertEquals("finished\n",
                         request.get(8, TimeUnit.SECONDS));

            closer.join(10_000L);
            assertFalse(closer.isAlive(),
                        "Context close did not finish");
            assertNull(closeError.get());

            List<String> events = journal.snapshot();
            assertTrue(events.indexOf("context-closed") >= 0);
            assertTrue(events.indexOf("worker-stop") >
                       events.indexOf("context-closed"));
            assertTrue(events.indexOf("bean-destroy") >
                       events.indexOf("worker-stop"));
        } finally {
            // Luôn mở gate trước cleanup để test failure không kẹt.
            gate.release();
            context.close();
            callers.shutdownNow();
        }
    }
}
~~~

### 10.1. Vì sao test này tránh được race phổ biến?

Một test kém ổn định thường:

~~~java
CompletableFuture.runAsync(() -> callHttp("/sleep?ms=5000"));
Thread.sleep(100);
context.close();
~~~

Đây là **mảnh phản ví dụ** chứ không độc lập runnable. Sau 100 ms, HTTP request **có thể chưa tới controller** do CI chậm, DNS, thread scheduling hoặc Tomcat startup. Khi close trước request, assertion “graceful failed” là false alarm. Với `HoldGate`:
1. Test `arm()`.
2. HTTP client gửi request qua real socket.
3. Controller gọi `blockIfArmed()` và `entered.countDown()`.
4. Test chờ `awaitEntered(10s)`; chỉ khi handler thực sự chạy mới gửi context.close.
5. Test chờ `ContextClosedEvent` để biết close đã bắt đầu.
6. Gate giữ request, nên close thread còn chạy và future chưa xong.
7. Test `release()`, request trả `200 OK`/`finished\n`, close hoàn tất.
8. Test xác minh worker stop/destroy ordering qua journal.

**Đây là test "drain đúng một request"**, không phải load test nhiều clients, streaming SSE/WebSocket hoặc HTTP/2 multiplex. `CountDownLatch` là đồng bộ hóa JUnit trong cùng JVM, không tương đương distributed coordination.

### 10.2. Vì sao timeout có nhiều giá trị?

| Timeout | Giá trị lab | Bảo vệ phần nào? |
| --- | --- | --- |
| Gate `released.await(15s)` | 15 giây | Không để request giữ vô hạn nếu test quên release |
| Test chờ HTTP entry | 10 giây | CI/network có đủ thời gian request vào controller |
| Test chờ close event | 5 giây | Phát hiện context không đi vào shutdown |
| Spring lifecycle phase | 8 giây | Graceful HTTP in-flight drain deadline |
| HTTP future get | 8 giây | Nếu request không hoàn tất thì fail có giới hạn |
| Close thread join | 10 giây | Không treo JUnit do teardown không hoàn tất |

Đây là các deadline **riêng**, không cộng dồn thành “total 56s”. Trong CI máy quá chậm có thể cần margin hơn; nhưng không khắc phục bằng xóa timeouts. Test cần **chắc chắn đang thử điều gì** và log source of delay. Với app có nhiều SmartLifecycle phases, total close có thể lớn hơn một phase timeout.

### 10.3. Đọc kết quả kỳ vọng thế nào?

Khi test thành công, các quan hệ partial ordering đáng mong đợi:

~~~text
worker-start
application-started
application-ready
... HTTP /hold has entered ...
context-closed
... blocked in-flight HTTP /hold completes ...
worker-stop
bean-destroy
~~~

Đây là **mô hình mong đợi**, không phải stdout chính xác. Spring Boot/Tomcat thêm nhiều log lines giữa các mốc. `ContextClosedEvent` xảy ra **trước** phase stop; `worker-stop` phase 0 chạy **sau** web-server graceful phase; `bean-destroy` sau lifecycle processing. Log trong shutdown hook/worker thread có thể interleave theo timing, nên test chỉ kiểm tra ordering của những records mình chủ động phát.

### 10.4. Không hard-assert new-request status trong grace

Với Tomcat, connection mới có thể bị từ chối, client thấy `ConnectException`, connection reset hoặc status từ LB. Với Undertow có thể thấy 503. Một test `assertEquals(503, GET /ping trong shutdown)` sẽ fail trên Tomcat dù graceful hoạt động chính xác. Nếu muốn test rejection:
- chứng minh request mới **không được hoàn thành như request thường** sau khi drain bắt đầu;
- chấp nhận các kết quả thuộc contract của server/hop đang test;
- test riêng trên server type cụ thể với time synchronization và thời hạn phù hợp;
- đừng xem một 503 ngẫu nhiên do business controller là bằng chứng web server graceful đang hoạt động.

## 11. Build, chạy manual và output dự kiến

Tạo các file theo cây thư mục, tại root `runtime-lifecycle-lab`:

~~~bash
java -version
mvn clean test
mvn clean package
java -jar target/runtime-lifecycle-lab-0.0.1-SNAPSHOT.jar
~~~

**Bộ test dự kiến:**
- `RuntimeHttpTest`: real HTTP GET và startup/readiness event order.
- `StartupFailureTest`: runner failure, event failure, không có ready.
- `PortConflictTest`: bind đúng cổng đang giữ phải fail.
- `GracefulShutdownTest`: một HTTP in-flight request hoàn tất trước context close.

Các tests được thiết kế để PASS nếu project và môi trường đầy đủ; **không khẳng định các lệnh đã chạy thực tế ở máy người đọc**. Khi có lỗi thực, xem startup logs và error chain để sửa code/config, không đổi assertions thành luôn true.

### 11.1. Test endpoint thật

~~~bash
curl -i http://127.0.0.1:8080/ping
curl -i "http://127.0.0.1:8080/sleep?ms=100"
curl -i http://127.0.0.1:8080/actuator/health/readiness
~~~

**Kỳ vọng:**
- `GET /ping` → 200 và body `pong\n`.
- `GET /sleep?ms=100` → 200 và body `slept 100ms\n` sau khoảng 100ms (elapsed thời gian có thể nhiều hơn).
- Readiness endpoint ở app đang ready thường báo `UP` nếu health group đã bật và không có health failure, body/metadata tùy Boot/Actuator config.

Nếu `/actuator/health/readiness` trả 404, kiểm tra Actuator starter, `management.endpoint.health.probes.enabled` và actual management path/port. Nếu bị 401/403 ở app khác, xem security chain; demo không có security starter.

### 11.2. Tạo startup failure từ command line

~~~bash
java -jar target/runtime-lifecycle-lab-0.0.1-SNAPSHOT.jar \
  --server.port=0 \
  --demo.fail-runner=true
~~~

**Kỳ vọng:** có log `application-started`, runner cố ý ném exception, application startup fail và không log `application-ready`; process thoát với non-zero status theo Boot launcher/exception handling. Đây là lỗi **sau khi context refresh**, khác port conflict xảy ra ở bước mở server.

**Không tạo process thật** chạy liên tục khi property fail true; dòng lệnh kết thúc do runner fail.

### 11.3. Tạo port conflict thủ công

Mở ứng dụng thứ nhất:

~~~bash
java -jar target/runtime-lifecycle-lab-0.0.1-SNAPSHOT.jar \
  --server.port=8080
~~~

Ở terminal thứ hai, khi app thứ nhất còn chạy, chạy **một instance thứ hai** với cùng port và address:

~~~bash
java -jar target/runtime-lifecycle-lab-0.0.1-SNAPSHOT.jar \
  --server.port=8080 \
  --server.address=127.0.0.1
~~~

**Kỳ vọng:** instance thứ hai báo port in use, startup fail; instance thứ nhất vẫn phục vụ `/ping`. Không làm thử nghiệm trên production shared port; dùng VM/container/localhost lab. Port conflict test tự động dùng ephemeral port nên không ảnh hưởng cổng cố định.

### 11.4. Test SIGTERM với in-flight request

Trên **Linux/macOS** trong một terminal, chạy executable JAR và ghi lại **PID JVM thật**:

~~~bash
java -jar target/runtime-lifecycle-lab-0.0.1-SNAPSHOT.jar \
  --server.port=8080
~~~

Ở terminal thứ hai, bắt đầu request chậm:

~~~bash
curl -i -v "http://127.0.0.1:8080/sleep?ms=7000"
~~~

Trong terminal thứ ba, **sau khi request đã vào server**, xác định JVM PID và gửi:

~~~bash
ps -ef | grep 'runtime-lifecycle-lab-0.0.1-SNAPSHOT.jar'
kill -TERM <JAVA_PID>
~~~

`<JAVA_PID>` là placeholder phải thay bằng process ID thật, **không copy nguyên dấu ngoặc**. Đừng `kill -9`. Cần xác nhận request thực sự đang chạy, ví dụ thêm logging request-entered hoặc quan sát bằng thử nghiệm có coordination; thao tác thủ công gửi quá sớm có thể gây false negative.

**Kỳ vọng:** sau `SIGTERM`, JVM shutdown hook gọi context close, HTTP graceful stop chờ request đã được nhận hoàn tất trước budget 8s; `curl` có thể nhận `200` và body `slept 7000ms`. New requests trong lúc drain có thể bị refused/reset thay vì một status cố định. Log có `context-closed`, `worker-stop`, `bean-destroy` theo lifecycle ordering.

**Quan trọng:** Nếu gửi SIGTERM quá muộn, HTTP request đã xong thì chưa test in-flight drain; nếu gửi quá sớm, request chưa vào handler thì server có thể từ chối request hoàn toàn đúng. Đó là lý do automated `GracefulShutdownTest` dùng gate/latch thay sleep.

### 11.5. Linux/CI gợi ý script PID đúng

Có thể thử với shell được kiểm soát:

~~~bash
# Terminal A:
java -jar target/runtime-lifecycle-lab-0.0.1-SNAPSHOT.jar \
  --server.port=8080 > runtime.log 2>&1 &
app_pid=$!
echo "JVM PID: $app_pid"

# Terminal B: chờ cho health/ping thực sự ready.
curl -fsS http://127.0.0.1:8080/ping

# Terminal B: tạo request 7 giây ở background.
curl -fsS "http://127.0.0.1:8080/sleep?ms=7000" > response.txt &
req_pid=$!

# Sau khi biết request đã vào handler, gửi SIGTERM từ terminal A:
kill -TERM $app_pid

# Chờ kết quả request và process:
wait $req_pid
wait $app_pid
~~~

Đây là **các đoạn lệnh hướng dẫn** dùng chung hai terminals, **không phải một script CI hoàn chỉnh tự đồng bộ**. `wait` chỉ hoạt động với child PIDs của shell đã tạo chúng; khi chạy các terminals khác nhau, cần thực hiện `wait` tại shell sở hữu child tương ứng. Với CI, nên viết harness có server-side latch/log/event để chắc chắn request đã vào handler trước SIGTERM, và có cleanup/trap/timeouts.

## 12. So sánh `context.close()` với SIGTERM subprocess

| Tiêu chí | Đóng context trong JUnit JVM | SIGTERM gửi tới executable JAR |
| --- | --- | --- |
| Framework teardown | **Có**: Spring context/lifecycle | **Có** nếu JVM nhận signal và hook chạy |
| OS signal forwarding | **Không** | **Có** |
| Web server HTTP drain | **Có** nếu app context khởi tạo server thật | **Có** nếu graceful được bật và budget đủ |
| PID 1/entrypoint | Không kiểm tra | Có thể kiểm tra với container runtime |
| JVM shutdown hooks | Không nhất thiết chạy tất cả | Có cơ hội chạy khi JVM termination hợp lệ |
| Log flush/process exit | Không kiểm tra full process | Có thể kiểm tra |
| K8s preStop/Pod grace | Không | Chỉ khi thử qua Kubernetes thật |
| Test speed/determinism | Thường nhanh/dễ đồng bộ | Chậm hơn, cần xử lý signal và cleanup |
| Test failure diagnostics | JUnit assertions/exceptions | Process exit code, stderr, stdout, HTTP results |

Một suite tốt thường có:
1. **Nhiều unit/slice tests** cho business/API contract;
2. **Một số SpringApplication/real HTTP tests** cho startup, port conflict, graceful close;
3. **Một subprocess/Docker SIGTERM smoke test** trong CI Linux cho signal forwarding;
4. **Một staging/Kubernetes rollout test** nếu high availability/no-dropped-requests là SLO quan trọng.

## 13. Kubernetes và Docker: startup/readiness/termination budget

### 13.1. Probe endpoints

Spring Boot Actuator có thể expose:
- `/actuator/health/liveness`;
- `/actuator/health/readiness`.

Kubernetes readiness probe bắt đầu gửi traffic khi service ready. Tuy vậy:
- readiness update được phát **sau** `ApplicationReadyEvent`;
- endpoint sẵn sàng chỉ có ý nghĩa nếu Service/Ingress/load balancer thực sự dùng readiness;
- client truy cập pod trực tiếp có thể bypass routing;
- Kube EndpointSlice/Service propagation có delay, nên traffic mới có thể đến trong khoảng shutdown vừa bắt đầu;
- không nên đưa DB external unavailable vào **liveness** để tránh restart storm; readiness policy cần dựa trên failure modes.

Ví dụ Pod/Deployment fragment:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: runtime-lab
spec:
  replicas: 2
  selector:
    matchLabels:
      app: runtime-lab
  template:
    metadata:
      labels:
        app: runtime-lab
    spec:
      terminationGracePeriodSeconds: 45
      containers:
        - name: app
          image: example/runtime-lab:1.0
          ports:
            - name: http
              containerPort: 8080
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: http
            periodSeconds: 5
            timeoutSeconds: 2
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 10
            timeoutSeconds: 2
          lifecycle:
            preStop:
              exec:
                command: ["/bin/sh", "-c", "sleep 5"]
~~~

**Chưa phải manifest deploy chạy ngay:** `image: example/runtime-lab:1.0` là placeholder, không cung cấp Dockerfile/registry; cần build image. Quan trọng hơn, demo `server.address=127.0.0.1` không listen trên Pod IP. Khi container hóa, **override `--server.address=0.0.0.0`** hoặc environment property tương ứng và thêm NetworkPolicy/TLS/auth, nếu không Kubernetes probe tới Pod IP có thể thất bại dù localhost curl vẫn hoạt động.

### 13.2. Chọn termination grace theo budget

Giả định:
- preStop sleep ≈5s;
- web server graceful phase tối đa 8s;
- custom SmartLifecycle phases thêm 5–10s;
- DB pool/metrics destruction 2s;
- safety margin ít nhất vài giây.

`terminationGracePeriodSeconds=45` là **minh họa** có dư, không phải chuẩn. Kubernetes **tính preStop trong cùng termination grace**, không cộng thêm free time ngoài. Nếu hết deadline, kubelet có thể gửi SIGKILL; `@PreDestroy`/callbacks có thể không chạy đến hết.

**Đừng đồng nhất** `spring.lifecycle.timeout-per-shutdown-phase=8s` với “Pod dừng trong 8s”. Các phases được chờ lần lượt và shutdown hooks/destruction cũng cần thời gian.

### 13.3. Docker PID 1 và tín hiệu

Ưu tiên exec-form container entrypoint:

~~~dockerfile
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

Dùng shell form `ENTRYPOINT java -jar ...` có thể làm shell wrapper thành PID 1 và không forward SIGTERM như mong đợi. Nếu cần shell, dùng `exec java -jar ...` để shell được thay bằng JVM hoặc dùng init đúng.

`docker stop` thông thường gửi SIGTERM rồi cưỡng bức SIGKILL sau stop timeout; cấu hình timeout đủ cho ứng dụng. `docker kill` mặc định thường là SIGKILL và không phải test graceful. Trong Windows IDE, nút Stop có thể force kill, không nhất thiết tương đương SIGTERM của Linux.

## 14. Test startup performance và sự kiện failure nâng cao

### 14.1. Startup profiling với ApplicationStartup

Spring Boot hỗ trợ `ApplicationStartup`. Có thể cấu hình `BufferingApplicationStartup`:

~~~java
SpringApplication app =
        new SpringApplication(RuntimeLabApplication.class);
app.setApplicationStartup(
        new BufferingApplicationStartup(2048));
app.run(args);
~~~

Imports:
- `org.springframework.boot.SpringApplication`;
- `org.springframework.boot.context.metrics.buffering.BufferingApplicationStartup`.

Đây là **mảnh minh họa** thay cách chạy main trong một bản profiling, không phải main của project runnable. Nếu expose Actuator `startup` endpoint cần security/exposure đúng, và buffer có kích thước hữu hạn. `FlightRecorderApplicationStartup` của Spring Framework cung cấp integration với Java Flight Recorder; dùng khi cần đo allocation/class loading/GC liên quan startup.

**Không lấy tổng log timestamp đến `Started Application in ... seconds` làm bằng chứng riêng của readiness**: mốc Boot báo started khác `ApplicationReadyEvent` sau runners. Đo cả time-to-ready/first successful health check nếu đó là SLO.

### 14.2. ApplicationContextRunner cho lỗi cấu hình/bean

`ApplicationContextRunner` (từ `spring-boot-test`) phù hợp kiểm thử từng auto-configuration/bean thiếu dependency mà không tạo HTTP server:

~~~java
new ApplicationContextRunner()
    .withBean(String.class, () -> {
        throw new IllegalStateException("missing required config");
    })
    .run(context -> {
        assertThat(context).hasFailed();
    });
~~~

Đây là **mảnh minh họa** cần imports:
- `org.springframework.boot.test.context.runner.ApplicationContextRunner`;
- static `org.assertj.core.api.Assertions.assertThat`.

Nó kiểm tra **context startup failure** nhưng **không** chứng minh socket port bị chiếm; để test EADDRINUSE phải chạy web server thật như `PortConflictTest`.

### 14.3. ApplicationFailedEvent và FailureAnalyzer

Spring Boot có **FailureAnalyzer** và `FailureAnalysisReporter` giúp đưa thông báo `Description` / `Action` khi startup lỗi quen thuộc (port in use, config missing...). Test nên ưu tiên:
- context.run throws;
- failure listener đã nhận event;
- cause chain chứa injected exception khi đó là failure chủ động;
- port đang giữ khiến bind thất bại;
- process không đạt readiness.

**Không assert toàn văn failure-analysis log**: thông điệp có thể thay theo OS/Boot version, format logging hoặc code path. Nếu hệ thống cần chuẩn hóa alert, nên xuất telemetry có schema ổn định riêng thay vì regex mọi console string.

## 15. Kiểm thử các tình huống khó

### 15.1. Request vượt shutdown timeout

Với `server.shutdown=graceful` và `timeout-per-shutdown-phase=3s`, một HTTP request thật mất 7 giây có thể **không hoàn tất trong cửa sổ drain**. Response có thể reset, truncated hoặc fail ở client, tùy server và proxy. Test production-like nên xác nhận policy retry/idempotency, không hard-code duy nhất `503`.

Thử thủ công (môi trường lab):

~~~bash
java -jar target/runtime-lifecycle-lab-0.0.1-SNAPSHOT.jar \
  --spring.lifecycle.timeout-per-shutdown-phase=3s
~~~

Rồi gọi `/sleep?ms=7000`, gửi SIGTERM sau khi request thực sự bắt đầu. Trường hợp này **cố ý tạo failure window**, không dùng config 3s cho business request có SLA dài hơn.

### 15.2. SSE/WebSocket và kết nối dài

Một `SseEmitter`, `Flux<ServerSentEvent>`, WebSocket hoặc streaming download có thể giữ request/connection lâu hơn mọi ordinary API. Nếu cứ chờ “đến khi client tự đóng” thì rolling deploy bị kẹt, Pod grace hết, SIGKILL xảy ra.

Nên test:
- ngừng mở stream/subscription mới khi readiness đang drain;
- phát event/reconnect hint trước close nếu protocol cho phép;
- đóng/cancel stream có deadline;
- client reconnect có backoff và `Last-Event-ID`/resume nếu yêu cầu không mất dữ liệu;
- resources/subscribers/queues được cleanup;
- multi-replica failover hoạt động qua ingress.

`MockMvc` test body/event format hữu ích nhưng **không** mô phỏng đầy đủ socket/network/proxy buffering/idle timeout; dùng real HTTP và staging test.

### 15.3. Background worker và SmartLifecycle phases

Một web server chờ HTTP requests xong **không tự biết** app còn Kafka consumer, scheduler, batch worker hay thread tự tạo. Khi stop:
1. dừng nhận work mới;
2. giữ DB/client dependencies sống trong thời gian drain;
3. stop consumers/executor theo phase/dependency;
4. gọi `SmartLifecycle.stop(Runnable)` completion callback **khi thực sự dừng**;
5. close singleton resources trong destruction step.

Kiểm tra startup/close ordering của worker bằng partial-order assertions như `worker-start` trước `application-started`, `context-closed` trước `worker-stop`, `worker-stop` trước `bean-destroy`. Với nhiều beans cùng phase, không assert thứ tự tuyệt đối không được contract hứa.

### 15.4. DB và transaction trong shutdown test

Nếu request commit DB transaction rồi server close connection, test client có thể không nhận success dù data đã persist. Graceful drain giảm khả năng này nhưng không tạo exactly-once semantics. Dùng idempotency key hoặc transactional outbox để xử lý retries.

`@Transactional` trên test class **không rollback tự động** các DB transactions do HTTP server thread xử lý trong `RANDOM_PORT` test, vì test thread và server thread có transaction scopes khác. Cần fixtures/test DB isolation rõ. Đừng dùng H2 memory/testcontainers trong shutdown test mà hủy DB trước HTTP drain.

### 15.5. Context caching và JUnit parallelism

`@SpringBootTest` có Spring TestContext caching. Nếu test gọi `context.close()` trên shared cached context, các tests sau có thể fail ngẫu nhiên. Trong ví dụ:
- `RuntimeHttpTest` dùng context do Spring Test quản lý, **không** đóng.
- `GracefulShutdownTest` tự tạo context riêng bằng `new SpringApplication(...)`, **có quyền close**.
- `StartupFailureTest`/`PortConflictTest` cũng tạo SpringApplication riêng và fail có chủ đích.
- Mọi test bình thường dùng `server.port=0` nên có thể chạy song song mà ít collision.

Nếu dùng JUnit parallel execution, test dựa vào static/global state hoặc cổng `DEFINED_PORT` phải được cô lập. Một test cố tình kill JVM sẽ chấm dứt toàn test runner; **không gọi `System.exit`/`Runtime.halt` trong cùng JVM JUnit**. Thử signal qua subprocess riêng.

## 16. Triệu chứng – nguyên nhân – cách sửa

| Triệu chứng | Nguyên nhân khả dĩ | Chẩn đoán phù hợp |
| --- | --- | --- |
| MockMvc pass, production không bind port | MOCK không mở socket | RANDOM_PORT và explicit PortConflictTest |
| Boot báo “Port already in use” | Process khác giữ IP/port | `ss`/`lsof`/PID; bind đúng address |
| PortConflictTest bất ngờ pass | Socket không được giữ hoặc interface/namespace khác | Giữ ServerSocket mở, cùng 127.0.0.1/IPv4 |
| `@SpringBootTest(DEFINED_PORT)` flaky trên CI | Parallel tests cùng port | Dùng RANDOM_PORT cho tests thường |
| `ApplicationStartedEvent` có nhưng ready không có | Runner fail/hang | Kiểm tra ApplicationRunner, ApplicationFailedEvent |
| Listener `@EventListener(ApplicationFailedEvent)` không chạy | Context/bean chưa được tạo lúc lỗi | Đăng ký listener trước `SpringApplication.run` |
| Liveness UP nhưng readiness chưa | Warm-up/runners chưa xong | Check ApplicationAvailability/probes |
| `ApplicationReadyEvent` có mà request 404 | Mapping/business khác readiness | HTTP smoke request thật |
| Test `@SpringBootTest(MOCK)` không phát hiện timeout TCP | Không có network | RANDOM_PORT hoặc process/staging |
| Server shutdown cắt request 7s | immediate mode, grace 3s, SIGKILL, LB disconnect | Phân biệt lifecycle vs OS/proxy, tăng/thiết kế deadline |
| Request mới trong drain không trả 503 | Tomcat/Netty stop accept network | Không hard-assert 503; xem server type |
| Context.close bị kẹt đến timeout | stop(Runnable) quên callback, request/worker stuck | Phase logs, thread dumps, deadlines |
| ContextClosedEvent log xuất hiện nhưng DB vẫn hoạt động | Event đến trước lifecycle/destroy | Đây là bình thường; giữ DB đến khi drain xong |
| `@PreDestroy` không chạy sau `kill -9` | SIGKILL bypass JVM hooks | Test SIGTERM; durable cleanup khác |
| IDE Stop không thể tái hiện grace | IDE có thể terminate immediate | Chạy java -jar và kill -TERM |
| Probe readiness timeout ngay lúc shutdown | Connector đã ngừng accept requests | Không assert JSON luôn có; kiểm tra log/state |
| K8s Pod bị kill sau 30s | terminationGracePeriodSeconds hết | Budget preStop+phases+destroy |
| Test `GracefulShutdownTest` fail lúc server chưa nhận request | Race do sleep arbitrarily | Đồng bộ bằng CountDownLatch entered |
| Test đóng context làm suite khác fail | Close Spring TestContext cached context | Tạo isolated SpringApplication context |
| HTTP response xong nhưng process chưa exit | Worker/phase @PreDestroy/thread còn chạy | Thread dump, lifecycle callbacks, executor cleanup |
| Docker container không nhận SIGTERM | Shell wrapper/PID 1 không forward | Exec-form ENTRYPOINT hoặc init/exec |
| Lỗi hostPort Docker khi Java vẫn tốt | Collision ở host publish | Docker/K8s-level test thay vì chỉ Spring bind |
| Graceful request vẫn tạo order trùng sau retry | Side effect commit nhưng caller không nhận ACK | Idempotency/outbox, không chỉ graceful |
| Startup failure test bắt sai lỗi | Exception từ DB/port khác injected runner | Assert cause chain chứa intentional marker |

## 17. Runbook kiểm chứng từ máy phát triển đến production

### 17.1. Trước merge

1. Chạy `mvn clean test`; phân biệt test unit/slice và real-port tests.
2. Kiểm tra `@SpringBootTest(RANDOM_PORT)` có thể GET `/ping` bằng client thật và readiness ACCEPTING_TRAFFIC.
3. Test runner cố ý fail: event failure được nhận, không ready.
4. Test port đã giữ: startup fail đúng lý do, không lấy cổng cố định.
5. Test close context với in-flight request đã vào controller: HTTP response hoàn tất trước khi context close.
6. Kiểm tra SmartLifecycle worker stop callback và `@PreDestroy` ordering.
7. Xác nhận cleanup resources trong `finally` dù assertions fail; không rò socket/threads.
8. Không tắt security/mocks bất chấp chỉ để test xanh. Với app thật, thêm assertions authn/authz, DB, retries.

### 17.2. Trước deploy

1. Build executable JAR và container image với JVM nhận SIGTERM đúng.
2. Test startup trên environment có config/secrets/profile giống production.
3. Check readiness/liveness probes, network binding và Service/Ingress routes.
4. Test SIGTERM trên JAR có request đang xử lý.
5. Test request timeout > grace và hiểu failure/retry contract.
6. Đo shutdown duration mỗi phase; đừng dùng một tổng timeout đoán.
7. Tính Kubernetes `terminationGracePeriodSeconds` > preStop + worst-case drain + destruction + margin.
8. Test rollout multi-replica, long-lived connections và proxy idle timers.
9. Đảm bảo no new jobs được nhận sau drain gate, resource dependencies còn sống đủ lâu.
10. Bảo vệ actuator; không expose shutdown endpoint và endpoints lab public.

### 17.3. Trong sự cố

- Tìm **đúng startup event** cuối cùng: Starting? Prepared? WebServerInitialized? Started? Ready? Failed?
- Xác minh exit code và exception cause chain, port/address/socket owner.
- Nếu app đã ready nhưng không có traffic: kiểm tra proxy/ingress/firewall/routing, không quy hết lỗi cho Spring.
- Nếu SIGTERM không có ContextClosedEvent: xem PID1/wrapper, crash/OOM, hard kill.
- Nếu có event nhưng chờ quá lâu: xem stop phases, callbacks, slow requests, thread dumps.
- Nếu process thoát nhanh nhưng user thấy lỗi: kiểm tra grace period, LB drain, new requests, TCP resets, client retry policies và DB committed side effects.
- Nếu lỗi chỉ CI: check parallel test ports, test context caching, resource leaks, OS-specific process signals, CPU starvation.

## 18. Câu hỏi tự kiểm tra

1. `@WebMvcTest` có phát hiện port 8080 đang bị chiếm không? Vì sao?
2. `@SpringBootTest(MOCK)` khác `RANDOM_PORT` ở điều gì?
3. Tại sao `DEFINED_PORT` dễ flaky khi CI chạy nhiều tests song song?
4. Event nào diễn ra sau refresh nhưng trước ApplicationRunner?
5. Event nào diễn ra sau runners thành công?
6. `ReadinessState.ACCEPTING_TRAFFIC` thường được publish trước hay sau ApplicationReadyEvent?
7. Port đã bind có luôn nghĩa application ready không?
8. Vì sao listener `@EventListener(ApplicationFailedEvent)` có thể bỏ lỡ startup failure sớm?
9. Cách đăng ký listener trước run là gì?
10. Vì sao `ApplicationFailedEvent` cần test ngoài Spring TestContext khi startup được cố ý làm fail?
11. Port conflict test nên giữ ServerSocket đóng hay mở lúc gọi SpringApplication.run?
12. Vì sao dùng cùng `127.0.0.1`/port trong test bind?
13. `PortInUseException` có phải luôn là top-level exception khi khởi động fail không?
14. Khi nào dùng ApplicationContextRunner, khi nào phải dùng real web server?
15. `server.shutdown=graceful` khác `immediate` ở nguyên tắc nào?
16. Với Tomcat, new requests trong shutdown có bắt buộc trả 503 không?
17. `spring.lifecycle.timeout-per-shutdown-phase` là tổng thời gian JVM stop hay deadline từng phase?
18. Phase start và stop có cùng hướng không?
19. `SmartLifecycle.stop(Runnable)` phải gọi callback khi nào?
20. Vì sao `ContextClosedEvent` không đồng nghĩa database phải đóng ngay?
21. `@PreDestroy` xảy ra trước hay sau lifecycle stop?
22. Vì sao một `@SpringBootTest` cached context không nên bị đóng thủ công trong test?
23. Vì sao test graceful tốt nên dùng `CountDownLatch` thay vì `Thread.sleep(100)`?
24. Test `ctx.close()` có chứng minh Docker ENTRYPOINT forward SIGTERM đúng không?
25. Vì sao `kill -9` không phải phép thử graceful?
26. Kubernetes `preStop` có cộng thêm ngoài terminationGracePeriodSeconds không?
27. Trong test thật, response body `finished\n` nhận được trước khi close hoàn tất có ý nghĩa gì?
28. Vì sao long-lived SSE/WebSocket connections cần drain/reconnect policy riêng?
29. `@Transactional` test có rollback mọi DB changes do RANDOM_PORT server thread không?
30. Port host Docker collision có nhất thiết làm `PortConflictTest` trong JVM pass/fail giống production không?
31. Khi ApplicationRunner fail, có thể thấy ApplicationStartedEvent nhưng không thấy ApplicationReadyEvent không?
32. Một request commit DB thành công nhưng client mất ACK cần giải pháp nghiệp vụ gì?
33. Liveness UP có đồng nghĩa readiness ACCEPTING không?
34. Sau khi context.close hoàn tất, nên kỳ vọng điều gì ở HTTP connector?
35. Startup profiling bằng BufferingApplicationStartup có thay thế health/readiness test không?

**Đáp án ngắn:** (1) Không, không mở socket. (2) HTTP mock vs embedded server thật. (3) Cạnh tranh fixed port. (4) ApplicationStartedEvent. (5) ApplicationReadyEvent. (6) Sau ReadyEvent. (7) Không, runner còn chạy. (8) Bean chưa tồn tại. (9) `SpringApplication.addListeners` trước run. (10) Context test không khởi tạo hoàn tất. (11) Mở. (12) Cùng network binding. (13) Không, có nested/wrapping. (14) Config bean vs socket/container. (15) Drain in-flight vs dừng ngay. (16) Không, có thể network refuse. (17) Từng phase. (18) Không; start tăng, stop giảm. (19) Sau khi dừng thật. (20) HTTP đang drain còn dùng DB. (21) Sau lifecycle stop. (22) TestContext cache còn dùng lại. (23) Biết request đã vào handler. (24) Không. (25) Bỏ qua hooks. (26) Không, cùng budget. (27) Graceful giữ request in-flight và context chờ. (28) Chúng kéo dài vượt grace. (29) Không, khác thread/transaction. (30) Không, lỗi ở host mapping. (31) Có. (32) Idempotency/retry/durable state. (33) Không. (34) Không tiếp tục nhận request mới. (35) Không, chỉ phân tích các startup steps.

## 19. Tài liệu chính thức

- **Spring Boot 3.5 — SpringApplication**, thứ tự Application events, Liveness/Readiness, ApplicationStartup/BufferingApplicationStartup: https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html
- **Spring Boot 3.5 — Testing Spring Boot Applications**, MOCK/RANDOM_PORT/DEFINED_PORT/NONE, @LocalServerPort và test context: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
- **Spring Boot 3.5 — Graceful Shutdown**, default embedded servers, graceful phase và server differences: https://docs.spring.io/spring-boot/3.5/reference/web/graceful-shutdown.html
- **Spring Boot 3.5 — Actuator Endpoints**, probes/health groups/readiness: https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html
- **Spring Boot 3.5 — Common Application Properties**, `server.shutdown`, `spring.lifecycle.timeout-per-shutdown-phase`, `management.endpoint.health.probes.enabled`: https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html
- **Spring Boot 3.5 — ApplicationContextRunner/Test Utilities**: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
- **Spring Framework 6.2 — SmartLifecycle and bean lifecycle**, getPhase/stop callback/bean destruction: https://docs.spring.io/spring-framework/reference/6.2/core/beans/factory-nature.html
- **Spring Framework 6.2 — MockMvc vs end-to-end tests**: https://docs.spring.io/spring-framework/reference/6.2/testing/mockmvc/vs-end-to-end-integration-tests.html
- **Kubernetes — Pod Termination and preStop**: https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/#pod-termination
- **Spring Boot 3.5.16 release**: https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now/
