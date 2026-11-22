# Vòng đời máy chủ trong ApplicationContext và giải phóng tài nguyên

Trong Spring Boot web, máy chủ HTTP nhúng và các thành phần nghiệp vụ không hoạt động độc lập: **Spring ApplicationContext** điều phối việc khởi tạo, phục vụ request, dừng và giải phóng tài nguyên. Khi kết thúc đúng cách, ứng dụng ngừng nhận request mới, cho request đang chạy cơ hội hoàn thành, dừng các worker chạy nền, đóng pool/client rồi trả lại port, thread và tài nguyên hệ điều hành. Nếu hiểu sai vòng đời này, ứng dụng có thể đã ngừng trả HTTP nhưng JVM vẫn treo, hoặc JVM thoát quá sớm khiến request/transaction bị gián đoạn.

Bài học sử dụng **Spring Boot 3.x, Java 17+**, lấy **Spring MVC + embedded Tomcat** làm ví dụ chính. Nguyên lý lifecycle của context vẫn áp dụng với WebFlux và server khác, nhưng hành vi nhận/từ chối kết nối trong lúc shutdown có thể khác.

## 1. Kết quả học tập

Sau bài này bạn có thể:

1. Phân biệt **JVM/process**, **ApplicationContext**, **WebServer**, singleton bean và tài nguyên bên ngoài.
2. Giải thích chuỗi **SpringApplication.run → ApplicationContext.refresh → WebServer khởi động → runner → ApplicationReadyEvent**.
3. Chọn đúng lifecycle hook: **@PostConstruct**, **ApplicationRunner**, **SmartLifecycle**, **ContextClosedEvent**, **@PreDestroy** hoặc destroy method.
4. Mô tả quá trình đóng context, quản lý thứ tự stop và giải phóng resource theo owner/dependency.
5. Cấu hình **server.shutdown=graceful**, phân biệt **liveness/readiness**, kiểm tra request đang thực thi trong khi deploy/dừng.
6. Phân tích các tình huống leak thread, shutdown timeout, cleanup không chạy và dừng cưỡng bức.

Cần biết Java/annotation, HTTP, IoC/DI, khái niệm server port và cách chạy một ứng dụng Spring Boot. Mục tiêu là hiểu runtime web, không đi sâu thiết kế database hay orchestration cụ thể.

## 2. Sơ đồ sở hữu tài nguyên

~~~text
Process/JVM
  |
  +-- SpringApplication: khởi động ứng dụng
         |
         +-- ApplicationContext: bean + lifecycle + event
                |
                +-- WebServer: Tomcat / Jetty / Reactor Netty / ...
                |      |
                |      +-- connector, socket, thread, HTTP request
                |
                +-- Controller -> Service -> repository/client bean
                |
                +-- DataSource, ExecutorService, scheduler, consumer...
                       |
                       +-- resource nào do bean tạo thì bean cần close đúng cách
~~~

| Thành phần | Trách nhiệm | Điều không được nhầm |
| --- | --- | --- |
| **JVM / process** | Chạy bytecode, thread, heap; nhận tín hiệu OS | JVM còn chạy không chứng minh HTTP server khỏe; kill cưỡng bức không bảo đảm gọi cleanup. |
| **SpringApplication** | Chuẩn bị Environment, tạo context, điều phối startup/event | Không phải là HTTP server; nó khởi tạo và điều phối các thành phần. |
| **ApplicationContext** | Đăng ký/tạo bean, injection, refresh, event, lifecycle, destroy | Có thể có context không có web server, ví dụ ứng dụng non-web hoặc unit test. |
| **ServletWebServerApplicationContext** | Web context cho Servlet và embedded server | Khác với ApplicationContext thường; không phải controller. |
| **ReactiveWebServerApplicationContext** | Web context cho reactive WebServer | Pipeline và thực thi request khác Servlet; nguyên tắc close vẫn tương tự. |
| **WebServer** | Mở cổng, nhận request, quản lý connector/event loop/thread pool | Server không tự đóng mọi executor/client mà ứng dụng tạo. |
| **Singleton bean** | Service, controller, worker, client, pool do Spring quản lý | Destroy hook chạy khi context hủy bean; không chạy cho object tự new bên ngoài. |
| **Resource ngoài Spring** | File, thread tự tạo, socket, native handle | GC không thay việc đóng đúng thời điểm; cần chủ sở hữu rõ ràng. |

Spring Boot sử dụng **ServletWebServerFactory** hoặc **ReactiveWebServerFactory** theo loại ứng dụng và dependency để tạo WebServer. Trong ứng dụng Spring MVC có **spring-boot-starter-web**, Tomcat thường là embedded server mặc định. Trong WebFlux, **Reactor Netty** thường được sử dụng với starter reactive. **Triển khai WAR vào Tomcat ngoài** là trường hợp đặc biệt: container bên ngoài cũng là chủ thể điều phối vòng đời, không được áp đặt rằng Spring Boot luôn sở hữu một embedded Tomcat.

## 3. Máy chủ được tạo và khởi động trong ApplicationContext như thế nào?

### 3.1. Các giai đoạn startup

~~~text
main()
  -> SpringApplication.run(...)
  -> chuẩn bị Environment, profile, cấu hình
  -> suy ra WebApplicationType (SERVLET / REACTIVE / NONE)
  -> tạo ApplicationContext phù hợp
  -> load bean definitions, xử lý auto-configuration
  -> context.refresh()
       -> tạo/inject/khởi tạo bean
       -> web context tạo WebServer
       -> lifecycle processor khởi động các lifecycle bean thích hợp
       -> WebServer start và bind port
  -> ApplicationStartedEvent
  -> ApplicationRunner / CommandLineRunner
  -> ApplicationReadyEvent
  -> ReadinessState.ACCEPTING_TRAFFIC
~~~

Đây là **sơ đồ ý nghĩa**, không phải call stack chính xác cho mọi nội bộ Spring. Các bước trong refresh có thể đan xen; thứ tự giữa mọi bean không thể suy ra chỉ từ sơ đồ. **WebApplicationType.NONE** không cần tạo HTTP server, còn **SERVLET** và **REACTIVE** dùng các context và server factory phù hợp.

Trong Servlet web context, Spring Boot chuẩn bị server qua cơ chế web context trong quá trình refresh rồi dùng lifecycle component để điều phối start/stop. Bạn thông thường **không tự gọi Tomcat.start()** trong main và cũng không trực tiếp gọi stop() trên server từ controller. Việc giữ hạ tầng server trong lifecycle của context cho phép Spring điều phối các bean khác lúc khởi động và shutdown.

### 3.2. Khởi tạo bean không đồng nghĩa ứng dụng ready

**@PostConstruct** hoặc init method của bean chạy trong quá trình khởi tạo bean. Chúng nên nhẹ và tập trung chuẩn bị trạng thái của chính bean. Nếu một @PostConstruct chờ API ngoài vài phút hoặc chạy vô hạn, quá trình refresh có thể treo; lỗi trong đó có thể khiến startup thất bại.

**ApplicationRunner** và **CommandLineRunner** chạy sau khi context refresh và trước **ApplicationReadyEvent**. Đây là nơi thích hợp hơn cho công việc cần hoàn tất trước khi công bố sẵn sàng, ví dụ validate một điều kiện khởi động. Tuy nhiên, **port HTTP có thể đã bind trước khi runner kết thúc**. Nếu không có bộ định tuyến tôn trọng readiness, client vẫn có thể gọi trực tiếp cổng đó. Không coi “port mở” là bằng chứng đầy đủ cho khả năng phục vụ thật.

### 3.3. Event và mốc readiness

| Event / state | Diễn giải chính xác |
| --- | --- |
| **ApplicationStartingEvent** | SpringApplication vừa bắt đầu, context chưa được tạo. |
| **ApplicationEnvironmentPreparedEvent** | Environment đã chuẩn bị, trước khi context được tạo. |
| **ApplicationContextInitializedEvent** | Context đã được tạo và initializer chạy, trước khi load bean definition. |
| **ApplicationPreparedEvent** | Bean definition đã load, ngay trước refresh. |
| **ContextRefreshedEvent** | Context hoàn thành refresh. |
| **WebServerInitializedEvent** | WebServer đã được khởi tạo; có biến thể ServletWebServerInitializedEvent và ReactiveWebServerInitializedEvent. |
| **ApplicationStartedEvent** | Context đã refresh, trước runner. |
| **AvailabilityChangeEvent: LivenessState.CORRECT** | Spring Boot xem application live sau mốc started. |
| **ApplicationReadyEvent** | Các runner đã được gọi xong. |
| **AvailabilityChangeEvent: ReadinessState.ACCEPTING_TRAFFIC** | Ứng dụng công bố ready để nhận traffic. |
| **ApplicationFailedEvent** | Có exception khi startup; không đảm bảo mọi cleanup hook đều đã chạy như đường đi shutdown bình thường. |

**ContextRefreshedEvent** và **WebServerInitializedEvent** xuất hiện trước **ApplicationStartedEvent** trong startup điển hình; không nên phụ thuộc một thứ tự tương đối cứng nhắc của hai event này cho mọi kiểu context. Listener là bean với **@EventListener** không thể bắt các event trước khi bean/context tồn tại; listener cần thiết ở giai đoạn cực sớm phải đăng ký với SpringApplication trước khi run.

Event listener thông thường thực thi đồng bộ với publisher. Đừng đặt công việc lâu, blocking I/O hoặc vòng lặp vô hạn vào listener chỉ để theo dõi trạng thái.

## 4. Vòng đời request không phải vòng đời server

Với Spring MVC:

~~~text
HTTP client
   -> Tomcat connector + Servlet thread
   -> Filter chain
   -> DispatcherServlet
   -> Controller -> Service -> dependency bên ngoài
   -> chuyển dữ liệu thành response
   -> trả response, kết thúc tài nguyên gắn với request
~~~

Một request hoàn tất **không có nghĩa** controller, singleton service, HTTP client hoặc DataSource phải bị đóng. Chúng thường phục vụ nhiều request trong suốt vòng đời context. Nếu gọi **executor.shutdown()** sau mỗi request thì request tiếp theo có thể lỗi; ngược lại, nếu request tự mở file/socket mà không đóng, ứng dụng sẽ rò rỉ resource cho dù có @PreDestroy ở cuối vòng đời ứng dụng.

Với WebFlux, request thường đi qua **WebFilter** và **DispatcherHandler**, và Reactor Netty có thể chạy event loop. Đừng gọi blocking API tùy tiện trên event loop. Dù mô hình thực thi khác, context vẫn phải dừng WebServer cùng các bean và resource trước khi process thoát.

**Quy tắc scope:** tài nguyên sống ngắn nên dùng **try-with-resources/finally** tại đúng scope. Tài nguyên sống suốt application nên được sở hữu bởi bean có cleanup hook hoặc thành phần framework đã quản lý. Tránh đặt client/connection pool trong biến static không có chính sách close.

## 5. Khi đóng context, thực sự diễn ra điều gì?

### 5.1. Shutdown có thể bắt đầu từ đâu?

- **SIGTERM** từ hệ điều hành, Docker hay orchestrator: thường cho JVM chạy shutdown hook, từ đó đóng context.
- **Ctrl+C** trong terminal: có thể kích hoạt xử lý shutdown của JVM, tùy môi trường và cách chạy.
- **ConfigurableApplicationContext.close()**: API đóng context tường minh, giải phóng bean/resource do context quản lý.
- **SpringApplication.exit(context)**: đóng context và tính exit code phục vụ tiến trình; không đồng nghĩa tự động gọi System.exit trong mọi chương trình.
- **External servlet container undeploy/stop**: một phần lifecycle được điều phối bởi container ngoài.

Spring Boot thông thường đăng ký JVM shutdown hook để đóng context khi JVM shutdown một cách bình thường. **Không bảo đảm gọi @PreDestroy hoặc stop callback khi kill -9/SIGKILL, JVM crash, Runtime.halt(), mất điện hay process bị hệ điều hành cưỡng bức chấm dứt.** Một số thao tác Stop của IDE hoặc công cụ quản lý process trên Windows có thể bỏ qua graceful shutdown.

### 5.2. Trình tự close bình thường

~~~text
Yêu cầu ngừng ứng dụng
         |
         v
ApplicationContext.close()
         |
         +-- ContextClosedEvent
         |
         +-- LifecycleProcessor dừng các Lifecycle/SmartLifecycle
         |      |
         |      +-- graceful WebServer hạn chế request mới
         |      +-- cho request đang chạy thời gian hoàn thành
         |      +-- dừng component lifecycle theo phase/dependency
         |
         +-- destroy singleton bean
         |      |
         |      +-- @PreDestroy
         |      +-- DisposableBean / destroyMethod
         |      +-- đóng executor, pool, socket, file, client...
         |
         +-- hoàn tất đóng hạ tầng context/server
         v
JVM kết thúc khi không còn thread giữ tiến trình
~~~

Đây là thứ tự **khái niệm của đóng context bình thường**: một số server component còn có bước stop/destroy nội bộ. Với refresh thất bại hoặc hot refresh, framework có thể gọi destroy mà không có đủ stop notification, nên **không khẳng định SmartLifecycle.stop() luôn được gọi trước @PreDestroy trong mọi đường đi**.

**ContextClosedEvent** thông báo quá trình close bắt đầu, không phải xác nhận tất cả resource đã đóng. **ContextStoppedEvent** dành cho context **stop()**, là khái niệm khác với **close()**. Một context đã close không còn là context hoạt động để tiếp tục phục vụ; restart ứng dụng cần tạo context mới hoặc theo quy trình khởi động riêng.

### 5.3. Vì sao server có thể dừng mà JVM vẫn không thoát?

Dừng cổng HTTP chỉ loại bỏ một nhóm resource. Một **ScheduledExecutorService**, thread tự tạo, Kafka consumer hoặc HTTP client có background thread vẫn có thể giữ JVM sống. Ngược lại, **SIGKILL** khiến OS thu hồi bộ nhớ và socket nhưng không cho transaction, job hoặc log của ứng dụng cơ hội flush/commit. Vì vậy cần thiết kế cả **cleanup** lẫn **recovery/idempotency** cho công việc quan trọng.

Nếu có **parent/child ApplicationContext**, đóng context con không tự động đóng tất cả context cha; resource phải được giải phóng theo context sở hữu. Dependency cũng quan trọng: nếu một bean cần dùng client khi stop, client không nên bị đóng trước khi bean dừng đúng cách.

## 6. Hook nào dùng cho trách nhiệm nào?

| API | Lúc thực thi | Lý do chọn |
| --- | --- | --- |
| **@PostConstruct** | Sau injection, lúc khởi tạo bean | Chuẩn bị/validate trạng thái ngắn gọn. |
| **ApplicationRunner** / **CommandLineRunner** | Sau refresh, trước ready | Việc phải xong trước khi SpringApplication ready. |
| **@EventListener(ApplicationReadyEvent.class)** | Khi ứng dụng ready | Quan sát/đánh dấu mốc ready; tránh block trong listener. |
| **SmartLifecycle.start()** | Khi lifecycle processor khởi động component | Bật consumer hoặc worker cần điều phối start/stop. |
| **SmartLifecycle.stop(Runnable)** | Khi lifecycle processor yêu cầu dừng | Ngừng nhận job, đợi drain, báo callback sau khi đã dừng. |
| **@EventListener(ContextClosedEvent.class)** | Context bắt đầu close | Thông báo trạng thái đóng, ngừng intake sớm hoặc quan sát. |
| **@PreDestroy** | Khi singleton bean được hủy | Close resource thuộc sở hữu bean, trong thời gian hữu hạn. |
| **DisposableBean.destroy()** | Khi bean do Spring quản lý được hủy | Cần interface destroy của Spring; tăng coupling framework. |
| **@Bean(destroyMethod = "close")** | Bean tạo bằng factory method bị hủy | Đóng client thư viện có close/shutdown mà không sửa class gốc. |

Trong **Spring Boot 3.x**, import lifecycle annotation từ **jakarta.annotation.PostConstruct** và **jakarta.annotation.PreDestroy**. Ví dụ dùng namespace **javax.annotation** của các thế hệ cũ có thể không phù hợp.

**Cảnh báo scope:** Spring quản lý vòng đời destroy của singleton bean, nhưng **prototype bean** không được container tự động theo dõi toàn bộ quá trình giải phóng sau khi giao instance cho caller. Một object tự tạo bằng **new** ngoài container cũng không được Spring tự gọi @PreDestroy. Nếu library bean đã có cơ chế auto-close được Spring cấu hình sẵn, không đóng cùng resource ở nhiều nơi.

### 6.1. SmartLifecycle và thứ tự phase

**SmartLifecycle** có **start()**, **stop()**, **stop(Runnable)**, **isRunning()**, **isAutoStartup()** và **getPhase()**. Theo quy tắc phase thông thường: phase nhỏ **start trước**, phase lớn **stop trước**; lifecycle processor còn xét quan hệ dependency giữa bean. Khi dừng không đồng bộ, implementation phải gọi **callback.run()** sau khi hoàn tất shutdown thực sự, nếu không lifecycle processor có thể phải đợi timeout.

Ví dụ một consumer mô phỏng, là Java class hoàn chỉnh để đặt trong package của project ở phần thực hành:

~~~java
package com.example.lifecycledemo;

import java.util.concurrent.atomic.AtomicBoolean;
import org.springframework.context.SmartLifecycle;
import org.springframework.stereotype.Component;

@Component
public class ConsumerLifecycle implements SmartLifecycle {
    private final AtomicBoolean running = new AtomicBoolean(false);

    @Override
    public void start() {
        if (running.compareAndSet(false, true)) {
            System.out.println("consumer started");
        }
    }

    @Override
    public void stop(Runnable callback) {
        try {
            if (running.compareAndSet(true, false)) {
                System.out.println("consumer stopped");
            }
        } finally {
            callback.run();
        }
    }

    @Override
    public void stop() {
        stop(() -> { });
    }

    @Override
    public boolean isRunning() {
        return running.get();
    }

    @Override
    public boolean isAutoStartup() {
        return true;
    }

    @Override
    public int getPhase() {
        return 0;
    }
}
~~~

Lớp demo chỉ thay đổi cờ trạng thái nên callback chạy ngay là phù hợp. Một consumer thật phải **dừng nhận message/job mới, đợi các job đang xử lý hoàn tất hoặc chuyển giao an toàn**, rồi mới gọi callback. Không dùng callback như tín hiệu “đã bắt đầu shutdown” nếu worker vẫn xử lý dữ liệu. Nếu stop() bị chạy trên một thread mà nó lại đợi chính thread đó kết thúc, có thể deadlock.

**@PreDestroy** thường dành cho dispose cuối của resource; **SmartLifecycle.stop(...)** dành cho điều phối dừng có thứ tự và thời hạn. Có thể phối hợp cả hai nếu hoạt động close idempotent. Không hardcode phase của bean hạ tầng Spring Boot chỉ dựa trên một quan sát ngẫu nhiên ở một phiên bản cụ thể.

## 7. Graceful shutdown của WebServer

### 7.1. Cấu hình

Đặt trong **src/main/resources/application.yml**:

~~~yaml
spring:
  application:
    name: lifecycle-demo
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

Trong **Spring Boot 3.3**, **server.shutdown=graceful** bật graceful shutdown. Việc khai báo tường minh giúp bài tập dễ tái hiện dù một số phiên bản Spring Boot mới có default khác. **spring.lifecycle.timeout-per-shutdown-phase** đặt thời gian chờ **cho từng lifecycle phase**, không phải tổng thời gian tối đa tuyệt đối cho toàn bộ shutdown và mọi destroy callback. Tránh suy luận “20s chắc chắn process thoát trong 20s”.

Graceful shutdown diễn ra khi đóng context và được tổ chức ở giai đoạn stop phù hợp, cho các request đang chạy cơ hội hoàn tất và hạn chế request mới. Spring Boot 3.3 hỗ trợ trên Tomcat, Jetty, Reactor Netty và Undertow. Cách từ chối request phụ thuộc server: nhiều server ngừng nhận kết nối mới tại lớp mạng, còn Undertow có thể trả **503 Service Unavailable**. Connection keep-alive và proxy có thể làm kết quả quan sát khác.

Một request 60 giây không có bảo đảm hoàn tất với grace period 20 giây. Với **WebSocket, SSE, streaming, upload lớn, transaction dài hoặc job queue**, phải có kế hoạch drain, retry, giới hạn thời gian và phục hồi riêng. Graceful HTTP server shutdown không thay cho an toàn dữ liệu của message consumer.

### 7.2. Readiness khi startup và shutdown

Spring Boot dùng **ApplicationAvailability** với hai loại state:

- **LivenessState.CORRECT/BROKEN:** ứng dụng có hoạt động đúng ở mức sống còn của runtime hay không.
- **ReadinessState.ACCEPTING_TRAFFIC/REFUSING_TRAFFIC:** instance có nên nhận thêm lưu lượng hay không.

Trong startup, context có thể đã refresh và server có thể sẵn sàng ở mức kỹ thuật nhưng **readiness vẫn REFUSING_TRAFFIC** cho đến khi runner hoàn tất. Trong graceful shutdown, readiness chuyển sang từ chối lưu lượng mới. Nếu có Spring Boot Actuator và cấu hình health probes như trên, các endpoint thông dụng là:

~~~text
GET /actuator/health/liveness
GET /actuator/health/readiness
~~~

**Readiness chỉ hữu ích khi load balancer/orchestrator thực sự tôn trọng nó.** Một client gọi thẳng port có thể bỏ qua hợp đồng readiness. Readiness không nhất thiết bao gồm mọi dependency ngoài ứng dụng: phải thêm indicator/health group thích hợp nếu business thật cần xác minh điều kiện đó. Tránh đưa phụ thuộc dễ dao động vào liveness dẫn đến vòng lặp restart lan rộng.

### 7.3. Mối quan hệ giữa graceful shutdown và rollout

~~~text
Yêu cầu thay phiên bản
  -> readiness của instance cũ từ chối traffic
  -> load balancer dừng route request mới (cần thời gian lan truyền)
  -> graceful web server cho request đang chạy hoàn tất có giới hạn
  -> worker/consumer dừng intake và drain
  -> bean được destroy và pool/client được đóng
  -> process thoát hoặc bị orchestrator chấm dứt khi quá deadline
  -> instance mới phục vụ theo readiness
~~~

Ở hệ thống thật, có thể có giai đoạn overlap giữa instance mới/cũ và có timeout của orchestrator, proxy, client và message broker. Phải chọn timeout hợp lý theo độ trễ thực tế; deadline riêng của HTTP server không kiểm soát toàn bộ các deadline kia.

## 8. Bài thực hành chạy được: quan sát từng mốc và cleanup resource

Tạo project từ **https://start.spring.io** với Gradle, **Spring Boot 3.x**, **Java 17+**, group **com.example**, artifact **lifecycle-demo**, package **com.example.lifecycledemo**, dependencies **Spring Web**, **Spring Boot Actuator**, **Spring Boot Starter Test**. Sử dụng Gradle wrapper được tạo sẵn. Nếu dùng một version mới hơn Boot 3.x, cần so lại package/API và default của bản tương ứng.

### 8.1. Main và ApplicationContext

**src/main/java/com/example/lifecycledemo/LifecycleDemoApplication.java**

~~~java
package com.example.lifecycledemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class LifecycleDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(LifecycleDemoApplication.class, args);
    }
}
~~~

Đặt main ở package cha để các @Component/@RestController phía dưới được component scan. **SpringApplication.run(...)** dựng web context và server; không tạo Tomcat bằng tay.

### 8.2. Controller có request nhanh và chậm

**src/main/java/com/example/lifecycledemo/WorkController.java**

~~~java
package com.example.lifecycledemo;

import java.util.concurrent.TimeUnit;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class WorkController {
    public record Ping(String message) { }

    @GetMapping("/demo/ping")
    public Ping ping() {
        return new Ping("pong");
    }

    @GetMapping("/demo/slow")
    public String slow(@RequestParam(defaultValue = "6") int seconds)
            throws InterruptedException {
        int boundedSeconds = Math.max(0, Math.min(seconds, 10));
        TimeUnit.SECONDS.sleep(boundedSeconds);
        return "finished";
    }
}
~~~

Ở đây **sleep** chỉ mô phỏng một Servlet request đang xử lý để thử shutdown, giới hạn tối đa 10 giây. Không dùng sleep làm nghiệp vụ thật hoặc làm giải pháp điều khiển tải. Response body của **GET /demo/ping** khi chạy với Jackson trong Spring Web là:

~~~json
{"message":"pong"}
~~~

Response body của **GET /demo/slow?seconds=6** khi hoàn tất bình thường là:

~~~text
finished
~~~

### 8.3. Quan sát event

**src/main/java/com/example/lifecycledemo/RuntimeEvents.java**

~~~java
package com.example.lifecycledemo;

import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.web.servlet.context.ServletWebServerInitializedEvent;
import org.springframework.context.event.ContextClosedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class RuntimeEvents {
    @EventListener
    public void serverInitialized(ServletWebServerInitializedEvent event) {
        System.out.println("HTTP port: " + event.getWebServer().getPort());
    }

    @EventListener
    public void applicationReady(ApplicationReadyEvent event) {
        System.out.println("ApplicationReadyEvent");
    }

    @EventListener
    public void contextClosed(ContextClosedEvent event) {
        System.out.println("ContextClosedEvent");
    }
}
~~~

**ServletWebServerInitializedEvent** cung cấp port **thực tế** sau khi server được khởi tạo. Khi cấu hình **server.port=0**, port được OS chọn ngẫu nhiên; không suy ra 8080. **ContextClosedEvent** đến khi bắt đầu đóng, chưa chắc tài nguyên đều đã đóng. Dùng log để quan sát ý nghĩa mốc thay vì bắt chặt thứ tự tuyệt đối giữa tất cả dòng xuất ra từ các thread.

### 8.4. Resource thật do bean sở hữu

**src/main/java/com/example/lifecycledemo/MaintenanceTask.java**

~~~java
package com.example.lifecycledemo;

import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;
import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
import org.springframework.stereotype.Component;

@Component
public class MaintenanceTask {
    private final ScheduledExecutorService executor =
            Executors.newSingleThreadScheduledExecutor();

    @PostConstruct
    public void start() {
        executor.scheduleAtFixedRate(
                () -> System.out.println("maintenance tick"),
                0, 30, TimeUnit.SECONDS);
    }

    @PreDestroy
    public void close() {
        executor.shutdown();
        try {
            if (!executor.awaitTermination(3, TimeUnit.SECONDS)) {
                executor.shutdownNow();
                if (!executor.awaitTermination(2, TimeUnit.SECONDS)) {
                    System.err.println("maintenance task did not terminate");
                }
            }
        } catch (InterruptedException exception) {
            executor.shutdownNow();
            Thread.currentThread().interrupt();
        }
        System.out.println("maintenance cleanup attempted");
    }
}
~~~

Bean này **tự tạo ScheduledExecutorService**, vì thế nó chịu trách nhiệm ngừng tiếp nhận task mới và đóng thread khi context hủy bean. **shutdown()** yêu cầu dừng có trật tự; **awaitTermination** chờ tối đa theo deadline; **shutdownNow()** gửi yêu cầu interrupt cho task đang chạy nhưng không đảm bảo dừng được task không hợp tác. Trong thực tế, task cần tôn trọng interrupt và có chính sách phục hồi nếu dữ liệu chưa được commit.

Nếu resource được framework auto-config tạo và sở hữu sẵn (ví dụ nhiều DataSource/connection pool), cần kiểm tra cơ chế destroy hiện có trước khi tự viết thêm cleanup; đóng hai lần hoặc đóng quá sớm có thể gây lỗi cho bean khác.

### 8.5. Chạy và thử dừng

Trên Linux/macOS, tại root project:

~~~bash
./gradlew bootRun
~~~

Trên Windows:

~~~text
gradlew.bat bootRun
~~~

Mở terminal khác:

~~~bash
curl -s http://localhost:8080/demo/ping
curl -s "http://localhost:8080/demo/slow?seconds=6"
~~~

Ở bước thứ hai, để kiểm chứng graceful shutdown trong lúc request chậm vẫn chạy:

1. Đóng gói bằng **./gradlew bootJar**, chạy executable JAR bằng **java -jar build/libs/lifecycle-demo-0.0.1-SNAPSHOT.jar** (đổi tên nếu version thực tế khác).
2. Khởi chạy **curl -s "http://localhost:8080/demo/slow?seconds=6"** ở một terminal riêng.
3. Trong lúc request đang chạy, gửi **SIGTERM** tới PID của tiến trình JVM bằng **kill -TERM PID** trên Linux/macOS; hoặc dùng **docker stop** nếu chạy qua Docker. Tránh dùng SIGKILL.
4. Với grace period 20s, request 6s thường hoàn tất và trả **finished** nếu kết nối không bị cắt bởi môi trường; request mới bắt đầu trong lúc dừng có thể bị từ chối.
5. Quan sát **ContextClosedEvent**, log cleanup từ **@PreDestroy**, process và port sau khi dừng.

Kết quả phụ thuộc server, proxy, OS signal và thời điểm request được chấp nhận. Nút Stop của IDE hoặc lệnh terminate cưỡng bức có thể không chuyển SIGTERM theo cách cần cho bài thử. **Không chạy kill -9** để kiểm chứng graceful shutdown.

### 8.6. Test nhỏ xác nhận destroy callback

Test này chỉ chứng minh cơ chế bean lifecycle khi đóng context, không khởi động Tomcat.

**src/test/java/com/example/lifecycledemo/ContextCloseTest.java**

~~~java
package com.example.lifecycledemo;

import jakarta.annotation.PreDestroy;
import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ContextCloseTest {
    static class Probe {
        boolean closed;

        @PreDestroy
        void cleanup() {
            closed = true;
        }
    }

    @Test
    void closingContextInvokesPreDestroy() {
        AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext();
        context.registerBean(Probe.class);
        try {
            context.refresh();
            Probe probe = context.getBean(Probe.class);
            assertFalse(probe.closed);

            context.close();
            assertTrue(probe.closed);
        } finally {
            context.close();
        }
    }
}
~~~

Chạy **./gradlew test**. Test sử dụng **AnnotationConfigApplicationContext** thay vì web context, xác minh một bean được Spring quản lý có callback @PreDestroy chạy sau close. **close() có thể gọi lặp mà không làm hủy cùng context nhiều lần**, nhưng trong code production vẫn nên quản lý owner cẩn thận. Bài test không chứng minh request HTTP được drain; phải dùng phép thử SIGTERM ở mục trước để quan sát hành vi server thật.

## 9. Checklist tài nguyên cần giải phóng

| Resource | Vấn đề khi quên cleanup | Hướng xử lý |
| --- | --- | --- |
| **Embedded WebServer** | Port/connector/thread còn sống | Để Spring web context điều phối; cấu hình shutdown và kiểm chứng thực tế. |
| **ExecutorService/ScheduledExecutorService tự tạo** | Thread không thoát, job còn chạy | shutdown, awaitTermination theo deadline, xử lý interrupt, shutdownNow khi cần. |
| **Database connection pool** | Connection/socket không được trả | Sử dụng bean/pool có owner rõ; ưu tiên cơ chế framework đã cấu hình. |
| **HTTP client có pool** | Giữ connection, timer, thread | Tạo bean dùng lại, gọi close của đúng library khi context destroy nếu ứng dụng sở hữu. |
| **Message listener/consumer** | Nhận message khi shutdown, mất ack/offset | Dừng intake, drain/commit hoặc cho retry an toàn; tránh double-processing bằng idempotency. |
| **Scheduled task, background worker** | Job chạy khi phụ thuộc đã đóng | Dùng lifecycle stop phù hợp, deadline hữu hạn, đóng executor. |
| **File/socket/stream theo request** | Rò handle, dữ liệu chưa flush | try-with-resources/finally ngay khi kết thúc phạm vi sử dụng. |
| **WebSocket, SSE, long polling** | Kết nối dài cản shutdown | Thông báo đóng, giới hạn thời gian, reconnect/resume nếu cần. |
| **ThreadLocal** | Rò trạng thái giữa các request trên thread pool | Cleanup trong finally của request/task, không đợi @PreDestroy. |

**Owner rule:** chỉ đóng resource mà bean/ứng dụng chịu trách nhiệm. Một controller không nên đóng shared DataSource hoặc shared HTTP client cuối mỗi request. Trước khi thêm @PreDestroy, xác định resource có được Spring auto-config quản lý và tự đóng hay chưa.

## 10. Những lỗi thường gặp và cách chẩn đoán

### 10.1. HTTP đã tắt nhưng JVM vẫn sống

**Dấu hiệu:** port không nghe, log nói context đang close, process vẫn tồn tại. **Nghi ngờ:** non-daemon thread, executor tự tạo, scheduler, worker không tôn trọng interrupt, stop callback chưa hoàn tất. **Kiểm tra:** lấy thread dump bằng **jcmd PID Thread.print** hoặc **jstack PID** khi còn truy cập được JVM; tìm tên thread và stack của owner. **Giải pháp:** shutdown đúng API, timeout/interrupt, không đợi chính thread thực hiện stop.

### 10.2. Shutdown kéo dài hơn timeout cấu hình

**Nguyên nhân:** timeout-per-shutdown-phase áp dụng theo phase; có thể có nhiều phase hoặc destroy hook/client close bị block. **Kiểm tra:** đo thời gian callback, log phase, queue/active task, timeout client bên ngoài. **Giải pháp:** deadline rõ, dừng intake sớm, tránh callback blocking vô hạn; tăng timeout chỉ sau khi hiểu nguyên nhân.

### 10.3. Restart trả 502/503 hoặc connection reset

**Nguyên nhân:** load balancer vẫn gửi request mới khi instance dừng, readiness propagation chậm, grace period ngắn hơn request, proxy đóng kết nối trước server. **Giải pháp:** thử rolling shutdown dưới tải, đo p95/p99 và timeout của gateway, điều chỉnh drain, retry/idempotency ở client/consumer. Graceful shutdown của server chỉ là một phần của rollout an toàn.

### 10.4. @PreDestroy không được gọi

**Kiểm tra:** object tạo bằng new, prototype scope, annotation sai namespace, context chưa đóng, process bị SIGKILL/crash hoặc startup lỗi sớm. **Giải pháp:** đưa tài nguyên vào bean được quản lý đúng scope, khai báo hook hợp lệ và thiết kế recovery để không lệ thuộc hoàn toàn vào cleanup.

### 10.5. Startup báo lỗi port hoặc chưa ready

**Kiểm tra:** giá trị **server.port** thực tế, process chiếm cổng, dependency/server factory, loại WebApplicationType, lỗi tạo bean hoặc runner. **Ứng dụng start** không đồng nghĩa **ready**; đọc root cause của stack trace và mốc lifecycle trước khi đoán lỗi HTTP mapping.

### 10.6. Gọi close() quá sớm hoặc nhiều owner cùng đóng

**Dấu hiệu:** controller trả lỗi sau lần request đầu, consumer mất connection khi chưa dừng, executor từ chối task. **Giải pháp:** phân định resource owner, không đóng shared pool trên mỗi request, thiết kế thao tác close idempotent, sắp xếp lifecycle theo dependency. Nếu cleanup ném exception, ghi log chi tiết và tiếp tục đóng các resource độc lập trong giới hạn an toàn thay vì bỏ qua toàn bộ.

### 10.7. ContextClosedEvent bị hiểu là “mọi thứ đã giải phóng”

Đây chỉ là **event mở đầu việc đóng context**. Nếu muốn kiểm chứng resource thật đã được thu hồi, đo callback, trạng thái executor/pool, số thread, port và việc tiến trình kết thúc. Tránh phát tín hiệu “safe to remove resources” dựa trên ContextClosedEvent khi những bean khác vẫn đang dọn dẹp.

## 11. Tự kiểm tra kiến thức

**1. ApplicationContext có thể tồn tại khi không có WebServer không?** Có. ApplicationContext có thể phục vụ non-web application hoặc unit test. WebServer chỉ thuộc loại context/app web phù hợp.

**2. Vì sao WebServerInitializedEvent khác ApplicationReadyEvent?** Server đã khởi tạo không đồng nghĩa runner đã xong hoặc readiness đã cho phép traffic. Ready là mốc ứng dụng sau runner.

**3. Close khác stop của context thế nào?** Stop điều phối Lifecycle component; close là kết thúc vòng đời context, hủy singleton và giải phóng resource, không được coi như một pause có thể tự restart context cũ.

**4. Vì sao SmartLifecycle cần callback?** Nó cho phép phase shutdown đợi tác vụ dừng bất đồng bộ thực sự hoàn tất. Gọi callback trước khi drain xong tạo tín hiệu thành công sai.

**5. Vì sao @PreDestroy không bảo vệ dữ liệu khi kill -9?** SIGKILL không cho JVM chạy hook; dữ liệu quan trọng cần transaction, retry, checkpoint/idempotency hoặc cơ chế recovery ngoài tiến trình.

**6. Grace period 20s có đủ cho mọi request không?** Không. Nó là thời gian chờ theo phase; request dài, stream, proxy và orchestrator có deadline khác. Phải đo theo hệ thống thật.

**7. Cần đóng một DataSource ở controller không?** Không. DataSource thường là resource dùng chung, được bean/framework quản lý; đóng theo owner vào shutdown, không theo từng request.

**8. Vì sao một thread tự tạo có thể khiến JVM treo sau khi port HTTP đóng?** Thread đó là resource độc lập; server shutdown không biết cách dừng nó nếu không có owner và callback cleanup.

## 12. Bài tập hoàn thành

- [ ] Giải thích quan hệ **JVM → SpringApplication → web ApplicationContext → WebServer → request**.
- [ ] Chạy demo và nhận chính xác **{"message":"pong"}** khi gọi /demo/ping.
- [ ] Chỉ rõ mốc **WebServerInitializedEvent**, **ApplicationStartedEvent**, **ApplicationReadyEvent**, cùng ý nghĩa readiness.
- [ ] Đóng gói JAR và thử SIGTERM khi /demo/slow đang xử lý; quan sát request đang chạy và request mới.
- [ ] Xác nhận **ContextClosedEvent**, **@PreDestroy** và việc executor không giữ JVM sau shutdown.
- [ ] Chạy test đóng context, giải thích vì sao test đó không kiểm chứng graceful shutdown của Tomcat.
- [ ] Xác định owner, thời hạn chờ và đường khôi phục cho ít nhất một resource thật trong ứng dụng.

### Tài liệu chính thức

- [Spring Boot 3.3: Graceful Shutdown](https://docs.spring.io/spring-boot/3.3/reference/web/graceful-shutdown.html) — khả năng server và timeout theo phase.
- [Spring Boot 3.3: SpringApplication](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html) — startup event và availability state.
- [Spring Framework: Lifecycle callbacks](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html) — bean destroy và SmartLifecycle.
- [Spring Framework: ConfigurableApplicationContext](https://docs.spring.io/spring-framework/docs/6.1.0/javadoc-api/org/springframework/context/ConfigurableApplicationContext.html) — close và shutdown hook.

Vòng đời máy chủ là một phần của vòng đời **ApplicationContext**, còn kết thúc request là phạm vi nhỏ hơn. Server có thể không nhận thêm lưu lượng trong lúc context vẫn đang drain và đóng bean; JVM chỉ thoát ổn định khi các resource do ứng dụng và framework sở hữu đã được giải phóng hoặc kết thúc theo deadline phù hợp.