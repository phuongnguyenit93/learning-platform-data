# Đóng ApplicationContext và vòng đời SmartLifecycle của máy chủ

**Module:** Spring Boot → web-runtime → **Dừng có kiểm soát**.

Khi ứng dụng nhận tín hiệu dừng, việc quan trọng không chỉ là “tắt Tomcat” hay “gọi `System.exit`”, mà là điều phối **ApplicationContext**, **SmartLifecycle của web server**, những HTTP requests đang xử lý, job/background consumers và việc hủy singleton resources. Bài này trình bày quy trình **context close → ContextClosedEvent → LifecycleProcessor.onClose() → dừng SmartLifecycle theo phase → @PreDestroy/DisposableBean → giải phóng BeanFactory**, cách dùng `server.shutdown`/`spring.lifecycle.timeout-per-shutdown-phase`, thiết kế `stop(Runnable)` đúng, các bẫy khi chạy Docker/Kubernetes và dự án **Java 17 + Maven + Spring Boot 3.5.16** với kiểm tra thật bằng `SIGTERM`.

**Phạm vi cụ thể:** Spring Boot 3.5.x / Spring Framework 6.2.x, embedded Servlet container (demo dùng Tomcat qua `spring-boot-starter-web`). Nguyên tắc context và `SmartLifecycle` áp dụng cho nhiều ứng dụng Spring, còn hành vi web server có thể khác với WebFlux/Jetty/Undertow/Netty, external servlet container và Boot major versions khác. Bản 3.5.16 thuộc dòng đã hết OSS support từ giữa 2026; production nên dùng nhánh/bản bảo trì được hỗ trợ và kiểm chứng với version thật.

## 1. “Dừng có kiểm soát” khác “process chết ngay” như thế nào?

Giả sử request đang xử lý chuyển khoản 7 giây. Process nhận yêu cầu dừng tại giây thứ 3.

**Dừng đột ngột:** container/process bị kết thúc ngay, socket đóng, request có thể mất response; transaction đang dở có thể rollback hoặc đã commit nhưng caller không nhận kết quả. Không bảo đảm business operation được thực hiện đúng một lần.

**Graceful shutdown:** hệ thống **ngừng nhận thêm traffic mới** trong khi cho in-flight requests cơ hội hoàn tất trong **grace period**. Sau đó dừng các thành phần nền theo thứ tự, giải phóng kết nối/database pools và đóng context. Grace period là **hữu hạn**, không cam kết mọi long-running job sẽ hoàn tất nếu vượt hạn.

~~~text
T+0s   JVM nhận SIGTERM / ctx.close() được gọi
  │
  ├── ContextClosedEvent
  │
  ├── stop SmartLifecycle pha cao trước (có thể chặn nhận job mới)
  │
  ├── WebServer graceful shutdown trong phase đầu của quá trình stop
  │     ├── ngừng cho phép HTTP requests mới
  │     └── chờ requests đang chạy xong, tối đa deadline của phase
  │
  ├── stop SmartLifecycle pha thấp hơn (consumers, scheduler của ứng dụng)
  │
  ├── destroy singleton beans (@PreDestroy, DisposableBean, destroyMethod)
  │
  └── close BeanFactory / context và process thoát
~~~

**Đây là trình tự khái niệm của một Spring Boot context đóng bình thường**, không phải log/timestamp chính xác áp đặt cho mọi phiên bản. Các beans cùng phase có thể stop đồng thời bằng callbacks; dependency declarations có thể ảnh hưởng thứ tự; các context lồng nhau và framework integrations có thể thêm các bước riêng.

**Điểm mấu chốt:** nếu JVM nhận `SIGKILL`/`kill -9`, bị OOM-kill, crash native hoặc `Runtime.halt(...)` thì không có bảo đảm chạy shutdown hook, `ContextClosedEvent`, `stop` hoặc `@PreDestroy`. Graceful shutdown là **best effort dưới thời hạn cho phép**, không thay thế transactionality, retry, idempotency và durability.

## 2. ApplicationContext đóng bằng cách nào?

Trong Spring Boot, `SpringApplication.run(...)` trả về một `ConfigurableApplicationContext`. Spring Boot theo mặc định **đăng ký JVM shutdown hook** để gọi close khi JVM có cơ hội dừng bình thường. Có các con đường hợp lệ:

| Tác nhân | Cơ chế | Có cơ hội graceful không? |
| --- | --- | --- |
| Lệnh `kill -TERM <pid>` gửi tới **JVM process** | JVM thực thi shutdown hooks, context close | **Có**, nếu process/OS cho đủ thời gian |
| Container orchestrator gửi SIGTERM tới PID 1 | Shutdown hook chạy nếu tín hiệu đến đúng JVM | **Có**, trong termination grace period |
| `context.close()` trên `ConfigurableApplicationContext` | Gọi Spring context close trực tiếp | **Có**; caller thread thực hiện chu trình đóng |
| `SpringApplication.exit(context)` | Đóng context và tính exit code từ ExitCodeGenerators | **Có**; **không tự bảo đảm JVM đã gọi System.exit** |
| JVM crash / `kill -9` / force-stop | Bỏ qua shutdown hooks hoặc dừng tức thì | **Không** |
| IDE Stop button | Tùy IDE gửi tín hiệu gì tới JVM | **Không nên giả định** luôn graceful |

Có thể đóng một context khi code có quyền quản lý nó:

~~~java
ConfigurableApplicationContext context =
        SpringApplication.run(DemoApplication.class, args);

// Chỉ là ví dụ vòng đời trong ứng dụng CLI/test,
// không gọi close ngay sau run ở production web server.
context.close();
~~~

Ở đây cần các imports tương ứng `SpringApplication` và `ConfigurableApplicationContext`. Nếu gọi `close()` ngay sau khởi động web app thì server sẽ lập tức shutdown — **đây là mảnh minh họa** chứ không nằm trong main của project demo.

**Không tạo endpoint unauthenticated `GET /shutdown` gọi `System.exit(0)`.** Spring Boot Actuator có endpoint shutdown hỗ trợ context close nhưng **bị tắt theo mặc định**, cần enable/expose riêng và kiểm soát authentication/network cực chặt. Trong phần lớn ứng dụng, để process manager/orchestrator quản lý lifetime thay vì web API công khai.

### 2.1. Đóng context khác gì refresh/restart?

`ContextRefreshedEvent` thuộc quá trình context được refresh/start. `ContextClosedEvent` thuộc quá trình close. Đừng gọi `context.refresh()` để “dừng và tự khởi động lại” web server: đó không phải API rolling restart/zero-downtime. Để rollout phiên bản mới, dùng nhiều replicas qua load balancer và orchestration, hoặc restart toàn process có chuẩn.

`@PreDestroy` được gọi khi singleton bị hủy theo vòng đời context, không mặc nhiên “mỗi request một lần”. Với prototype scope, Spring không quản lý destruction giống singleton thông thường; người sử dụng scope phải tự giải phóng đúng. `SmartLifecycle` quản lý **chạy/dừng các component đang hoạt động**, không phải cách thay thế mọi resource cleanup.

## 3. Thứ tự close thực sự bên trong Spring

Ở Spring Framework `AbstractApplicationContext#doClose()`, khi context đang active và quá trình close được thực hiện bình thường:

1. Phát **`ContextClosedEvent`**.
2. Gọi **`LifecycleProcessor.onClose()`**, thường là `DefaultLifecycleProcessor`, để stop những beans implement `Lifecycle`/`SmartLifecycle`.
3. Gọi **`destroyBeans()`**, hủy các singleton beans và gọi destruction callbacks (ví dụ `@PreDestroy`, `DisposableBean.destroy()`, inferred/custom destroy methods).
4. Đóng bean factory/mark context state và thực hiện hook cleanup của context.

Trên startup, `ContextRefreshedEvent` và lifecycle startup cũng có tương tác; người học cần tập trung distinction: `ContextClosedEvent` **không phải** tín hiệu “mọi servlet đã dừng xong”. Khi một listener nhận event này, web server có thể **vẫn đang chờ request hoàn tất**. Do đó:

- Listener `ContextClosedEvent` nên **nhanh**, đánh dấu state, ghi log/metrics hoặc gửi tín hiệu drain nhẹ.
- **Không đóng database pool ngay trong listener** nếu HTTP requests còn đang cần DB.
- **Không sleep 30 giây trong listener** để “chờ request”: điều đó có thể trì hoãn luôn việc lifecycle processor bắt đầu graceful shutdown.
- Nếu cần thứ tự drain background jobs và kiểm soát stop completion, triển khai `SmartLifecycle` với phase, callback và deadline.
- Nếu chỉ cần close một resource khi các thành phần đã ngừng, dùng `@PreDestroy` hoặc `DisposableBean`.
- Chú ý exception/timeout: logging và cleanup phải chịu lỗi; dừng process không bảo đảm mọi bước hoàn tất.

### 3.1. Event vs lifecycle vs destruction

| Hook | Được dùng cho | Điểm thời gian thường thấy | Có chờ async callback không? |
| --- | --- | --- | --- |
| `ApplicationListener<ContextClosedEvent>` / `@EventListener` | Quan sát bắt đầu đóng context, đánh dấu quiescing | Trước stop lifecycle beans | Không; synchronous listener mặc định nên không block lâu |
| `SmartLifecycle.stop(Runnable)` | Dừng một active component có thứ tự và completion signal | Trong `LifecycleProcessor.onClose` | **Có**, processor đợi callback trong timeout phase |
| `Lifecycle.stop()` | Dừng active component đơn giản | Trong lifecycle processor | Không có async completion callback trong API thường |
| `@PreDestroy` | Cleanup khi bean bị hủy | Sau lifecycle stop processing | Không có phase ordering của SmartLifecycle |
| `DisposableBean.destroy()` | Explicit cleanup contract | Singleton destruction | Không phải event tương đương shutdown bắt đầu |
| `@Bean(destroyMethod = "...")` | Hủy third-party bean | Singleton destruction | Không dùng để chờ in-flight network drain quá hạn |

Một bean có thể implement SmartLifecycle **và** có `@PreDestroy`, nhưng phải bảo đảm các operations là idempotent và tránh chạy cleanup nguy hiểm hai lần. `stop(Runnable)` nên dừng activity/không nhận việc mới, còn `@PreDestroy` giải phóng resources cuối cùng nếu cần.

## 4. Lifecycle, SmartLifecycle, DefaultLifecycleProcessor

### 4.1. `Lifecycle`: start/stop thông thường

~~~java
public interface Lifecycle {
    void start();
    void stop();
    boolean isRunning();
}
~~~

Khi context có `LifecycleProcessor`, nó có thể start/stop các beans. `Lifecycle` bản cơ bản **không** tự động được start mọi lúc như `SmartLifecycle`; theo Spring docs, regular Lifecycle beans thuộc phase 0 và auto-start semantics khác (thường cần explicit start). Tránh viết `Lifecycle` rồi tin nó chắc chắn được auto-start khi context refresh.

### 4.2. `SmartLifecycle` thêm auto-start, phase và async stop callback

Các method quan trọng:

~~~java
public interface SmartLifecycle extends Lifecycle, Phased {
    boolean isAutoStartup();    // mặc định true
    int getPhase();             // mặc định Integer.MAX_VALUE
    void stop(Runnable callback);
}
~~~

Đây là **mô tả API rút gọn** để học (không phải copy interface đầy đủ từ Spring). Khi implement SmartLifecycle:
- `isAutoStartup()` mặc định **true**, cho phép processor tự start khi context refresh.
- `getPhase()` mặc định `SmartLifecycle.DEFAULT_PHASE` = `Integer.MAX_VALUE`.
- `start()` phải làm trạng thái `isRunning()` trở thành true khi start thành công.
- `stop(Runnable callback)` phải gọi **`callback.run()` sau khi component thực sự stop**; không được quên callback, nếu không processor có thể chờ tới timeout.
- `stop()` vẫn là method của `Lifecycle`; callback variant là phương thức lifecycle processor dùng cho SmartLifecycle trong shutdown thông thường. Nếu override cả hai, bảo đảm semantics consistent.
- `stop` có thể async; callback là completion contract, **không** phải một HTTP callback hay event listener.

### 4.3. Phase ordering: start tăng, stop giảm

**Quy tắc:**

~~~text
Component                   phase     Startup          Shutdown
Consumer                    -100      1                3
Worker                        0      2                2
Publisher                   +100      3                1

START:  -100 → 0 → +100
STOP:   +100 → 0 → -100
~~~

Trong **cùng phase**, các components không được bảo đảm một thứ tự tuyến tính có thể phụ thuộc implementation/parallel callbacks. **Bean dependency** có thể ghi đè thứ tự phase: nếu bean A phụ thuộc B thì B start trước A, và A stop trước B, bất kể phase khai báo. Trong Spring Framework, một bean implement chỉ `Lifecycle` được xem ở phase 0 cho lệnh start/stop processor.

**Không nhầm `@Order` trên bean với `getPhase` của SmartLifecycle.** Để điều khiển lifecycle bean order, dùng phase và dependency relationships; `@Order` trên method bean không phải lời hứa stop trước/sau server. Không nên chọn ngẫu nhiên `Integer.MAX_VALUE` hoặc `Integer.MIN_VALUE` khi chưa xem framework lifecycle phase constants.

### 4.4. Graceful shutdown của embedded server thuộc phase nào?

Spring Boot 3.5 có `WebServerGracefulShutdownLifecycle` để kích hoạt `WebServer.shutDownGracefully(...)` trong một trong các phase cao, vì lifecycle processor **stop từ phase lớn đến nhỏ**. Boot document diễn đạt graceful shutdown chạy trong **earliest phase of stopping SmartLifecycle beans**.

Để code có thứ tự rõ:
- Một `SmartLifecycle` muốn **chặn nhận thêm work mới trước** server drain có thể dùng phase **cao hơn** phase graceful của web server (và test trên version hiện tại).
- Một component cần **giữ resource sống đến khi HTTP drain xong** nên có stop phase **thấp hơn** web server graceful stop, hoặc dependency relationship phù hợp.
- Một bean dùng mặc định `SmartLifecycle.DEFAULT_PHASE` có phase rất cao; nó có thể dừng **trước web server graceful stop**. Đừng mặc định mọi custom SmartLifecycle sẽ dừng sau khi server xong.

Trên Boot 3.5, Java class `org.springframework.boot.web.context.WebServerGracefulShutdownLifecycle` công bố hằng phase `SMART_LIFECYCLE_PHASE`. Để không khóa ứng dụng vào số magic hoặc đoán integer, có thể kiểm tra Javadoc/version hoặc dùng hằng này khi thiết kế nghiêm ngặt. **Không đổi framework bean phase bằng patch/reflection** chỉ để có log “đúng thứ tự”.

### 4.5. Timeout theo phase, không phải một đồng hồ tổng

`DefaultLifecycleProcessor` dùng **timeout per shutdown phase**, Spring Framework 6.2 mặc định khoảng **30 giây cho mỗi phase** (có thể được Boot config). Với config:

~~~properties
spring.lifecycle.timeout-per-shutdown-phase=20s
~~~

processor chờ tối đa 20 giây cho completion callbacks trong **từng phase**. Đây **không** phải “ứng dụng luôn dừng trong 20 giây”: có thể có nhiều phases khác nhau, còn `ContextClosedEvent`, `@PreDestroy`, library cleanup và process exit overhead. Nếu một component không gọi callback, phase có thể chờ tới timeout rồi tiếp tục các phases sau; tài nguyên component đó có thể chưa ngừng hoàn toàn.

### 4.6. Callback phải báo hoàn tất, kể cả khi lỗi

Mẫu synchronous stop:

~~~java
@Override
public void stop(Runnable callback) {
    try {
        stopAcceptingNewWork();
        waitForCurrentWorkWithinDeadline();
        closeInternalListener();
    } finally {
        callback.run();
    }
}
~~~

Đây là **mảnh minh họa**, không chạy độc lập vì các methods cần được triển khai. Cần tính đến exceptions và không nên block startup/shutdown thread quá lâu. Với async stop:

~~~java
@Override
public void stop(Runnable callback) {
    executor.execute(() -> {
        try {
            drainAndStop();
        } finally {
            callback.run();
        }
    });
}
~~~

Đây là **mảnh minh họa**, cần executor còn hoạt động và implement drain. Thực tế phải xử lý cả trường hợp `executor.execute` bị reject trong lúc shutdown để callback vẫn được gọi, và bảo đảm callback **chính xác một lần**. Không dùng executor mà chính nó đã shutdown ở phase trước. Trong demo mục 7, một thread riêng được tạo cho chặng chờ hữu hạn để dễ quan sát.

## 5. Spring Boot 3.5: graceful shutdown embedded web servers

Spring Boot 3.5 **bật graceful shutdown mặc định** cho bốn embedded servers **Tomcat, Jetty, Reactor Netty và Undertow**, ở cả Servlet và reactive stacks. Cấu hình tường minh:

~~~properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
~~~

Để chủ động tắt cơ chế này (thường chỉ trong lab/debug hoặc yêu cầu đặc biệt):

~~~properties
server.shutdown=immediate
~~~

**Không khuyến nghị `immediate`** chỉ để process thoát nhanh hơn nếu ứng dụng còn xử lý requests có side effects. Graceful shutdown chờ **in-flight HTTP requests trong grace period** và **không tiếp tục nhận requests mới**. Nhưng chiến lược reject request mới khác từng server:
- **Tomcat, Jetty, Reactor Netty:** ngừng nhận requests mới ở network layer khi graceful drain.
- **Undertow:** có thể vẫn nhận kết nối nhưng trả **503 Service Unavailable** trong grace window.
- HTTP persistent connections/HTTP2 streaming có thể có behavior chi tiết khác; kiểm tra server cụ thể.
- Một request quá dài, SSE/WebSocket stream hoặc client gửi chậm có thể chiếm phase timeout; cần quyết định đóng/notify client theo protocol.
- Timeout hết không bảo đảm business task có rollback sạch; caller phải biết retry/idempotency semantics.

### 5.1. Graceful shutdown không đồng nghĩa chờ tất cả background jobs

Spring Boot quản lý web server, nhưng một custom `Thread`, scheduler, message consumer, file poller hay SDK client do ứng dụng tự tạo không nhất thiết tự stop đúng. Trách nhiệm của team:
1. Dừng nhận job mới khi bắt đầu termination.
2. Chờ/finish/cancel jobs đang chạy trong deadline phù hợp.
3. Gọi `callback.run()` của SmartLifecycle sau khi stop thực sự.
4. Đóng executor, consumer subscriptions, DB connections và resources khi không còn dùng.
5. Lưu durable progress/offset/idempotency để xử lý crash hoặc forced termination.

**Không nên đóng DataSource trong `ContextClosedEvent`** khi web requests vẫn đang chạy. Container request drain nên diễn ra trước khi bean database connections bị destroy.

### 5.2. Web server timeout vs request timeout vs process grace

| Tham số | Đo cái gì? | Điều gì không được bảo đảm? |
| --- | --- | --- |
| `spring.lifecycle.timeout-per-shutdown-phase=20s` | Processor chờ stop callback của một phase tối đa 20s | Không bao phủ mọi phase/`@PreDestroy`/preStop |
| `server.shutdown=graceful` | Cách stop embedded HTTP server | Không bảo đảm request vô hạn luôn xong |
| `server.tomcat.connection-timeout` | Một số khía cạnh timeout của Tomcat HTTP connection | Không thay lifecycle phase timeout |
| Client `curl --max-time` | Deadline của chính client command | Không phản ánh chính xác server shutdown |
| Kubernetes `terminationGracePeriodSeconds` | Tổng thời gian Pod được phép kết thúc sau khi Pod termination bắt đầu | Không tự cộng thêm preStop hay các Spring phases |
| Docker stop timeout | Thời gian chờ sau SIGTERM trước khi SIGKILL | Không phải HTTP per-request timeout |
| `@PreDestroy` | Cleanup bean lúc destroy | Không có timeout riêng tự động theo phase property |

Khi lập budget, dùng một upper bound an toàn bao gồm **preStop time + web drain phase + các phases cần thiết + destruction + margin**. Không nhầm default của orchestration và Spring là một.

## 6. Chọn hook nào cho nhiệm vụ nào?

| Việc cần làm | Hook/cơ chế gợi ý | Lý do |
| --- | --- | --- |
| Ghi log context bắt đầu close | `@EventListener(ContextClosedEvent.class)` | Nhanh, không chờ drain |
| Chặn batch job mới | `SmartLifecycle` phase cao, đóng admission gate | Có thứ tự trước downstream drain |
| Cho HTTP requests đang xử lý xong | Spring Boot web server graceful lifecycle | Framework biết in-flight HTTP requests |
| Dừng consumer queue sau khi traffic web đã ngừng | `SmartLifecycle` phase thấp, stop(Runnable) và deadline | Giữ downstream dependencies sống đủ lâu |
| Shutdown scheduler/executor | `SmartLifecycle` hoặc library/framework lifecycle integration | Explicit stop/awaitTermination semantics |
| Close ConnectionPool/HTTP client sau khi jobs xong | Bean destruction hook, `@PreDestroy` hoặc destroy method | Hủy resource cuối đời |
| Shutdown process bởi Kubernetes | SIGTERM tới JVM PID 1 + probes + grace | Hợp tác với load balancer/draining |
| Dừng một job sau SIGKILL/crash | Persistent lease/checkpoint, idempotency | Callback trong process không thể chạy |

**Chọn một cơ chế chịu trách nhiệm chính cho từng resource.** Không vừa gọi `executor.shutdownNow()` trong `ContextClosedEvent`, vừa cho web requests tiếp tục sử dụng executor, vừa tự ngăn Spring destroy cleanup: điều này dễ tạo race/RejectedExecutionException.

## 7. Dự án runnable Java 17: quan sát thứ tự close và giữ request đang chạy

Mục tiêu demo:
- `GET /work?ms=7000` mô phỏng một HTTP request đang làm việc trong 7 giây.
- `AdmissionLifecycle` có phase rất cao, **ngừng nhận job mới** lúc shutdown.
- Spring Boot HTTP graceful lifecycle chờ request đã bắt đầu hoàn tất trong 20s.
- `DrainLifecycle` phase 0, chạy async stop, đợi số work in-flight về 0 hoặc hết một deadline cục bộ, rồi gọi `callback.run()`.
- `ShutdownSignals` log `ContextClosedEvent` và `@PreDestroy` để đối chiếu đúng thứ tự.
- `@SpringBootTest(RANDOM_PORT)` test route, và một isolated test kiểm tra start phase tăng/stop phase giảm.

**Cảnh báo:** lab không có authentication và dùng `Thread.sleep` để mô phỏng. Chỉ bind trên `127.0.0.1`. Đây không phải giải pháp production về job queue, payment, exactly-once hay load balancing.

### 7.1. Cây thư mục

~~~text
lifecycle-shutdown-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/shutdown/
    │   │   ├── ShutdownDemoApplication.java
    │   │   ├── InFlightTracker.java
    │   │   ├── AdmissionLifecycle.java
    │   │   ├── DrainLifecycle.java
    │   │   ├── WorkController.java
    │   │   └── ShutdownSignals.java
    │   └── resources/application.properties
    └── test/java/com/example/shutdown/
        ├── LifecyclePhaseTest.java
        └── WorkHttpTest.java
~~~

### 7.2. `pom.xml`

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
  <artifactId>lifecycle-shutdown-demo</artifactId>
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

### 7.3. `src/main/java/com/example/shutdown/ShutdownDemoApplication.java`

~~~java
package com.example.shutdown;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ShutdownDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ShutdownDemoApplication.class, args);
    }
}
~~~

Spring Boot đăng ký JVM shutdown hook theo mặc định. `main` không gọi `close()` ngay sau `run()`, vì cần để server hoạt động tới lúc được stop bởi process manager.

### 7.4. `src/main/java/com/example/shutdown/InFlightTracker.java`

~~~java
package com.example.shutdown;

import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.stereotype.Component;

@Component
public class InFlightTracker {
    private final AtomicInteger active = new AtomicInteger();

    public void begin() {
        active.incrementAndGet();
    }

    public void finish() {
        active.decrementAndGet();
    }

    public int activeCount() {
        return active.get();
    }
}
~~~

`InFlightTracker` lưu số work HTTP đang hoạt động trên **một JVM**, chỉ phục vụ quan sát trong lab. Nó không đếm mọi request của Tomcat, không theo dõi worker ở node khác và không tự ngăn race giữa admission check và shutdown. Production có thể dùng metrics/in-flight accounting của HTTP server, queue-specific counters và bounded concurrency.

### 7.5. `src/main/java/com/example/shutdown/AdmissionLifecycle.java`

~~~java
package com.example.shutdown;

import java.util.concurrent.atomic.AtomicBoolean;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.SmartLifecycle;
import org.springframework.stereotype.Component;

@Component
public class AdmissionLifecycle implements SmartLifecycle {
    private static final Logger log =
            LoggerFactory.getLogger(AdmissionLifecycle.class);

    private final AtomicBoolean running = new AtomicBoolean();

    @Override
    public void start() {
        running.set(true);
        log.info("ADMISSION start: accepting new work");
    }

    @Override
    public void stop(Runnable callback) {
        try {
            running.set(false);
            log.info("ADMISSION stop: reject new work");
        } finally {
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
        // Cao hơn phase graceful shutdown của web server trong Boot 3.5.
        return SmartLifecycle.DEFAULT_PHASE;
    }

    public boolean acceptingNewWork() {
        return running.get();
    }
}
~~~

`getPhase()` dùng mặc định rất cao của SmartLifecycle để đóng admission gate ở chặng đầu. `stop(Runnable)` gọi callback ngay vì thao tác này đồng bộ; callback nằm `finally` để không bỏ quên dù logging gặp lỗi. `stop()` vẫn được implement để đáp ứng Lifecycle API, nhưng processor sẽ gọi callback variant trong close thông thường.

**Không dùng gate này như authorization hoặc tính toán exactly-once.** Một request đã qua admission check trước SIGTERM sẽ tiếp tục; một request đến quá gần thời điểm shutdown có thể gặp 503 hoặc network reject tùy server và vị trí trong pipeline. Hành vi race được bảo vệ ở mức **đừng cho công việc mới khi gate đã đóng**, không phải một distributed lock.

### 7.6. `src/main/java/com/example/shutdown/DrainLifecycle.java`

~~~java
package com.example.shutdown;

import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.SmartLifecycle;
import org.springframework.stereotype.Component;

@Component
public class DrainLifecycle implements SmartLifecycle {
    private static final Logger log =
            LoggerFactory.getLogger(DrainLifecycle.class);

    private final InFlightTracker tracker;
    private final AtomicBoolean running = new AtomicBoolean();

    public DrainLifecycle(InFlightTracker tracker) {
        this.tracker = tracker;
    }

    @Override
    public void start() {
        running.set(true);
        log.info("DRAIN start: tracking HTTP work");
    }

    @Override
    public void stop(Runnable callback) {
        // Không chặn chính lifecycle stop thread bằng Thread.sleep.
        Thread drainer = new Thread(() -> {
            try {
                long deadline = System.nanoTime()
                        + TimeUnit.SECONDS.toNanos(10);
                while (tracker.activeCount() > 0
                        && System.nanoTime() < deadline) {
                    Thread.sleep(100);
                }
                if (tracker.activeCount() > 0) {
                    log.warn("DRAIN timeout, active={}",
                             tracker.activeCount());
                } else {
                    log.info("DRAIN complete, active=0");
                }
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                log.warn("DRAIN interrupted");
            } finally {
                running.set(false);
                // Bắt buộc: báo LifecycleProcessor rằng stop đã xong.
                callback.run();
            }
        }, "demo-drain-lifecycle");

        drainer.setDaemon(true);
        drainer.start();
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
        // Thấp hơn web server graceful phase:
        // stop SAU khi server đã có cơ hội drain.
        return 0;
    }
}
~~~

`DrainLifecycle` minh họa rõ **asynchronous stop with callback**. Nó giữ `isRunning()==true` cho tới khi thread drain hoàn thành, rồi gọi `callback.run()` đúng **một lần** trong `finally`. Phần while có deadline **10s** độc lập; cấu hình phase timeout của Spring là **20s** để có biên độ. Nếu bạn thay vòng while bằng network calls/database operations, phải thêm timeout/budget cho từng thao tác.

**Caveat:** Nếu không thể tạo thread mới (ví dụ `Thread.start()` lỗi do tài nguyên cạn), callback chưa được gọi; processor vẫn chờ tới phase timeout. Production nên có fallback `try/catch` cho thread creation/rejected executor, đo lường stop errors và bảo đảm completion signal đúng một lần trong tất cả nhánh. Ví dụ cố ý giữ tối giản để tập trung lifecycle semantics.

Ở ứng dụng thực, không nhất thiết cần một `DrainLifecycle` khác chỉ để đếm HTTP work, vì server đã biết request in-flight. Nó hữu ích khi đại diện **jobs/consumers hoặc resource subscriptions** mà web server không quản lý, có deadline riêng.

### 7.7. `src/main/java/com/example/shutdown/WorkController.java`

~~~java
package com.example.shutdown;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class WorkController {
    private final AdmissionLifecycle admission;
    private final InFlightTracker tracker;

    public WorkController(AdmissionLifecycle admission,
                          InFlightTracker tracker) {
        this.admission = admission;
        this.tracker = tracker;
    }

    @GetMapping(path = "/work",
                produces = MediaType.TEXT_PLAIN_VALUE)
    public ResponseEntity<String> work(
            @RequestParam(name = "ms", defaultValue = "5000")
            long milliseconds) {

        if (milliseconds < 0 || milliseconds > 15000) {
            return ResponseEntity.badRequest()
                    .body("ms must be between 0 and 15000\n");
        }
        if (!admission.acceptingNewWork()) {
            return ResponseEntity.status(
                    HttpStatus.SERVICE_UNAVAILABLE).body("draining\n");
        }

        tracker.begin();
        try {
            Thread.sleep(milliseconds);
            return ResponseEntity.ok(
                    "done after " + milliseconds + "ms\n");
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            return ResponseEntity.status(
                    HttpStatus.SERVICE_UNAVAILABLE).body("interrupted\n");
        } finally {
            tracker.finish();
        }
    }
}
~~~

Trong lab, HTTP worker thread block trong `Thread.sleep` để có thời gian phát SIGTERM. **Không dùng sleep/blocking I/O không giới hạn trong production**, và không có business side-effect trong endpoint này. Khi đã bắt đầu trước shutdown, controller vẫn có thể hoàn tất response trong 20s grace. Khi request bắt đầu sau khi gate đóng nhưng trước khi server từ chối network, controller có thể trả **503**.

### 7.8. `src/main/java/com/example/shutdown/ShutdownSignals.java`

~~~java
package com.example.shutdown;

import jakarta.annotation.PreDestroy;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.ContextClosedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class ShutdownSignals {
    private static final Logger log =
            LoggerFactory.getLogger(ShutdownSignals.class);

    @EventListener
    public void onContextClosed(ContextClosedEvent event) {
        log.info("EVENT ContextClosedEvent: close requested for context={}",
                 event.getApplicationContext().getId());
    }

    @PreDestroy
    public void onDestroy() {
        log.info("DESTROY @PreDestroy: singleton cleanup");
    }
}
~~~

Cùng bean này có listener event và destroy hook để so logs. `ContextClosedEvent` thường xuất hiện **trước** lifecycle stop. `@PreDestroy` của bean này chạy **sau** lifecycle processor stop processing. Không gán `@PreDestroy` cho task chờ requests dài; ở đây nó chỉ log để chứng minh bước hủy bean.

### 7.9. `src/main/resources/application.properties`

~~~properties
server.address=127.0.0.1
server.port=8080
spring.application.name=lifecycle-shutdown-demo

# Spring Boot 3.5 mặc định đã graceful, khai báo rõ để học.
server.shutdown=graceful

# Áp vào TỪNG SmartLifecycle shutdown phase, không phải tổng process timeout.
spring.lifecycle.timeout-per-shutdown-phase=20s

# Cho phép health/readiness probe khi app đang chạy.
management.endpoint.health.probes.enabled=true
management.endpoints.web.exposure.include=health

logging.level.com.example.shutdown=INFO
~~~

Boot Actuator trả health endpoints theo config. Nếu dùng `/actuator/health/readiness` để quan sát khi chạy, nó có thể báo readiness phù hợp. **Trong shutdown, HTTP server cũng ngừng nhận request mới**, nên probe từ bên ngoài có thể không có response thay vì trả JSON `REFUSING_TRAFFIC` ở mọi thời điểm. Đừng dùng việc probe timeout làm bằng chứng readiness không đổi.

### 7.10. Build và chạy executable JAR

~~~bash
java -version
mvn clean package
java -jar target/lifecycle-shutdown-demo-0.0.1-SNAPSHOT.jar
~~~

Dùng **java -jar** thay vì chỉ `mvn spring-boot:run` để xác định rõ **PID JVM** cần gửi SIGTERM. Nếu chạy Maven/IDE, có thể có process wrapper hoặc IDE Stop gửi signal không như production.

Một terminal khác:

~~~bash
curl -i "http://127.0.0.1:8080/work?ms=20"
curl -i "http://127.0.0.1:8080/actuator/health/readiness"
~~~

Kỳ vọng `/work?ms=20` trả **200 OK**, body:

~~~text
done after 20ms
~~~

Giá trị response body có ký tự newline cuối. HTTP headers như Date, Content-Type và Keep-Alive có thể khác theo Tomcat/version. `/actuator/health/readiness` trong trạng thái sẵn sàng thường có JSON `status=UP` với health groups được bật; implementation/health contributors có thể khiến health khác trong các môi trường đặc biệt.

### 7.11. Thực nghiệm SIGTERM khi có request 7 giây

**Terminal A**, để JVM chạy `java -jar` và quan sát log startup/shutdown.

**Terminal B**, gọi request 7 giây:

~~~bash
curl -i -v "http://127.0.0.1:8080/work?ms=7000"
~~~

**Terminal C**, ngay sau khi xác nhận request đang chạy, gửi tín hiệu đến **PID của Java process**:

~~~bash
# Ví dụ Linux/macOS: tìm đúng PID trước khi gửi signal.
ps -ef | grep 'lifecycle-shutdown-demo-0.0.1-SNAPSHOT.jar'
kill -TERM <JAVA_PID>
~~~

`<JAVA_PID>` là **placeholder** phải thay bằng PID thật; không copy nguyên dấu ngoặc. **Không** dùng `kill -9`. Không gửi signal cho process ngẫu nhiên; xác nhận PID/jar name trước. Trên Windows, `Stop-Process -Force` là forceful, không phải thay thế tương đương SIGTERM; có thể dùng console Ctrl+C nếu terminal truyền sự kiện đúng, nhưng hành vi cần xác minh. Test production-like đáng tin hơn trong Linux/container môi trường kiểm soát.

**Kỳ vọng thiết kế:**
1. Spring Boot nhận shutdown request và bắt đầu close ApplicationContext.
2. `ShutdownSignals.onContextClosed` log `EVENT ContextClosedEvent`.
3. `AdmissionLifecycle` phase rất cao stop, log `ADMISSION stop`.
4. Web server graceful shutdown stop nhận HTTP requests mới, **đợi request 7 giây đang chạy** hoàn tất trong 20s.
5. `curl` của request đang chạy có thể nhận **200 OK** và body `done after 7000ms`.
6. `DrainLifecycle` phase 0 stop sau web server grace, log `DRAIN complete, active=0` (trừ lỗi/timeout) và gọi callback.
7. `ShutdownSignals.onDestroy` log `DESTROY @PreDestroy`, process thoát.
8. Request mới trong shutdown có thể bị **connection refused/connection reset/503** theo timing và server; **không** có một HTTP status cố định cho mọi hop.

**Không coi đây là captured output**: logs sẽ có timestamps/thread names khác, thứ tự giữa logs cùng phase/thành phần framework có thể chen thêm. Các mốc **giữa ba beans do bài tạo** và server phase mới quan trọng.

### 7.12. Thử request dài hơn grace period

Mục đích: phân biệt “best effort drain” với “mọi request đều xong”.

Trong lab, controller giới hạn `ms <= 15000`, còn server timeout per phase 20s, nên để tạo tình huống **cố tình vượt grace**, có thể chạy JAR với:

~~~bash
java -jar target/lifecycle-shutdown-demo-0.0.1-SNAPSHOT.jar \
  --spring.lifecycle.timeout-per-shutdown-phase=3s
~~~

Rồi gửi request 7s và SIGTERM khi request đang chạy. Tùy server và timing, HTTP response có thể bị cắt trước khi controller hoàn tất, hoặc server/context sẽ chuyển sang các phases sau sau timeout; không khẳng định chính xác TCP error code mọi phiên bản. `DrainLifecycle` có phase riêng và timeout 3s lúc này cũng bị ảnh hưởng. Đây là **test giới hạn**, không phải cấu hình production.

Nếu một request thực tế có SLA 2 phút, grace 20s không bảo đảm completion. Phương án là thiết kế API asynchronous durable jobs, progress polling/retry, idempotency keys, hoặc tăng budget dựa trên measured tail latency và khả năng orchestration.

## 8. Automated tests: phase ordering và HTTP path

### 8.1. `src/test/java/com/example/shutdown/LifecyclePhaseTest.java`

Test này dùng `AnnotationConfigApplicationContext` độc lập để chứng minh **quy tắc phase** mà không phụ thuộc timing hoặc server socket. Không trộn nó với Spring Boot web app context trong cùng test.

~~~java
package com.example.shutdown;

import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.context.SmartLifecycle;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

import static org.junit.jupiter.api.Assertions.assertEquals;

class LifecyclePhaseTest {

    @Test
    void phaseAscendingAtStartDescendingAtClose() {
        List<String> events = new ArrayList<>();
        AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext();

        context.registerBean("low", Probe.class,
                () -> new Probe("low", -100, events));
        context.registerBean("high", Probe.class,
                () -> new Probe("high", 100, events));

        try {
            context.refresh();
            assertEquals(List.of("start low", "start high"), events);
        } finally {
            context.close();
        }

        assertEquals(List.of(
                "start low", "start high",
                "stop high", "stop low"), events);
    }

    static class Probe implements SmartLifecycle {
        private final String name;
        private final int phase;
        private final List<String> events;
        private boolean running;

        Probe(String name, int phase, List<String> events) {
            this.name = name;
            this.phase = phase;
            this.events = events;
        }

        @Override
        public void start() {
            events.add("start " + name);
            running = true;
        }

        @Override
        public void stop(Runnable callback) {
            try {
                events.add("stop " + name);
                running = false;
            } finally {
                callback.run();
            }
        }

        @Override
        public void stop() {
            events.add("stop " + name);
            running = false;
        }

        @Override
        public boolean isRunning() {
            return running;
        }

        @Override
        public int getPhase() {
            return phase;
        }
    }
}
~~~

Kỳ vọng **JUnit PASS** cho hai beans phase -100/+100, với chuỗi đúng như assertion. `stop(Runnable)` được gọi bởi lifecycle processor khi context close; method `stop()` không phải biến thể được processor ưu tiên cho SmartLifecycle.

**Giới hạn test:** nó không chứng minh embedded web server xử lý keep-alive/requests đang chạy thế nào. Điều đó cần smoke test `SIGTERM` ở mục 7 và kiểm thử hạ tầng thật.

### 8.2. `src/test/java/com/example/shutdown/WorkHttpTest.java`

~~~java
package com.example.shutdown;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.web.client.RestClient;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class WorkHttpTest {

    @LocalServerPort
    int port;

    @Test
    void workCompletesBeforeShutdown() {
        String body = RestClient.create().get()
                .uri("http://127.0.0.1:" + port + "/work?ms=10")
                .retrieve()
                .body(String.class);

        assertEquals("done after 10ms\n", body);
    }
}
~~~

Với Spring Boot test dependency trong POM, đây là HTTP test chạy **embedded Tomcat thật** trên random port, xác nhận route/controller hoạt động. Nó **không gửi SIGTERM** và không đóng context giữa test request; smoke test SIGTERM ở phần trước mới quan sát graceful drain.

Chạy:

~~~bash
mvn test
~~~

Dự kiến **hai tests PASS** khi project đúng và runtime Java/Maven/dependencies đầy đủ. Đây là **kết quả kỳ vọng từ source** chứ không phải khẳng định đã build/test trên máy người đọc.

## 9. Kubernetes: readiness, SIGTERM, preStop và termination budget

Một Pod chuẩn khi bị terminate:
1. Kubernetes bắt đầu đếm **`terminationGracePeriodSeconds`**.
2. Nếu có `preStop` hook, hook chạy trong khoảng grace ấy.
3. Runtime gửi SIGTERM cho process trong container (đường đi chính xác phụ thuộc runtime và preStop).
4. Ứng dụng Spring bắt đầu shutdown hook/context close, chuyển readiness **`REFUSING_TRAFFIC`** và ngừng nhận requests mới theo web server graceful logic.
5. Kubelet đợi process thoát; hết deadline có thể SIGKILL, mất cleanup.

**Không cộng `preStop` ngoài termination grace**: preStop **tiêu thụ cùng một budget**. Nếu app dùng nhiều SmartLifecycle phases, budget Kubernetes phải **đủ lớn hơn tổng các chặng có thể chờ + preStop + margin**.

Ví dụ cấu hình Pod/container **minh họa**:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: lifecycle-demo
spec:
  replicas: 2
  selector:
    matchLabels:
      app: lifecycle-demo
  template:
    metadata:
      labels:
        app: lifecycle-demo
    spec:
      terminationGracePeriodSeconds: 60
      containers:
        - name: app
          image: example/lifecycle-demo:1.0.0
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

**Caveat rất quan trọng:** `application.properties` của project lab bind `server.address=127.0.0.1` nên **không thể nhận traffic qua Pod IP** trong cấu hình Kubernetes trên nếu giữ nguyên. Khi container hóa, override `--server.address=0.0.0.0` (hoặc sửa config phù hợp) và có authentication/network policy. `image: example/lifecycle-demo:1.0.0` là **tên ảnh minh họa, không phải image có sẵn**. `preStop sleep 5` là **trade-off vận hành**, có thể tạo cơ hội cho endpoint propagation/routing updates, không thay correctness của graceful shutdown và không được xem là chuẩn bắt buộc. Chọn sleep bằng đo lường, không sao chép mù quáng.

### 9.1. Readiness khác liveness

| Tín hiệu | Ý nghĩa | Điều cần tránh |
| --- | --- | --- |
| **Liveness** | Process vẫn ở trạng thái có thể phục hồi; nếu deadlock nghiêm trọng thì restart | Đưa mọi dependency tạm lỗi vào liveness để gây restart storm |
| **Readiness** | Pod có nên nhận traffic mới từ service hay không | Coi readiness 200 như lời hứa request đang chạy đã xong |
| **Graceful stop** | Drain requests cũ, reject mới rồi hủy resources | Coi readiness REFUSING_TRAFFIC là kết nối HTTP vẫn trả 503 được |
| **preStop** | Hook chạy trong grace trước SIGTERM | Hook quá dài khiến không còn thời gian cho Spring |
| **terminationGracePeriodSeconds** | Deadline tổng Pod termination | Set đúng bằng mỗi timeout phase mà quên các phases khác |

Spring Boot Actuator có health probe groups và trạng thái `ReadinessState.ACCEPTING_TRAFFIC`, `ReadinessState.REFUSING_TRAFFIC`. Khi context close, readiness được chuyển thành từ chối traffic trong quá trình graceful; nhưng HTTP connector cũng đang đóng, nên một external probe **có thể không nhận được JSON**. Load balancer/endpoints controller có propagation delay; muốn không làm rớt requests, cần phối hợp routing + grace đủ dài, không chỉ state trong JVM.

### 9.2. Docker và PID 1

Ưu tiên exec form:

~~~dockerfile
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

để Java là PID 1 và nhận stop signal. Không dùng wrapper shell nuốt `SIGTERM` hoặc quên `exec java ...`. Nếu cần init process cho signal forwarding/reaping, dùng giải pháp đúng container runtime. `docker stop` thường gửi SIGTERM rồi SIGKILL sau timeout cấu hình; cần chỉnh stop-grace-timeout để app có thời gian tương ứng.

Đừng dựa vào `docker kill` (gửi hard kill mặc định) hoặc restart cưỡng bức để kiểm chứng graceful shutdown. Log app sau SIGTERM phải có lifecycle lines.

## 10. Quan hệ với background consumers, schedulers và database pool

Không phải mọi component nên có phase 0. Khi thiết kế thật, trước hết phân loại:

| Component | Mong muốn lúc shutdown | Lựa chọn điển hình |
| --- | --- | --- |
| Admission control hoặc queue listener nhận task mới | Stop early, không nhận work mới | SmartLifecycle phase **cao** |
| Embedded HTTP server | Chặn request mới, chờ in-flight | Boot web server graceful lifecycle |
| Handler dependencies như business service/DB repository | Còn dùng được khi HTTP requests đang drain | Chỉ destroy sau lifecycle stop |
| Batch worker xử lý task đã nhận | Finish/rollback/park within bound | SmartLifecycle phase thích hợp + bounded stop(Runnable) |
| Kafka listener / Rabbit listener container | Stop consume, commit/ack offsets theo contract | Dùng container lifecycle integration và phase đúng |
| Scheduled tasks | Stop scheduling và hoàn tất job hữu hạn | Scheduler lifecycle hooks, cooperative cancellation |
| JDBC/HikariCP pool | Đóng khi không ai còn dùng | Spring-managed bean destruction sau drain |
| HTTP client/connection pool | Finish in-flight downstream calls, sau đó close | Bean destruction hoặc explicit bounded stop |
| Metrics/OTLP exporter/logging | Flush có hạn, không mất signal bất ngờ | Framework shutdown integration + timeout |
| Custom executor | Ngừng nhận tasks, chờ bounded termination | Lifecycle hoặc destroy hook đúng thứ tự |

**Điểm dễ sai:** `@PreDestroy` của database bean có thể chạy sau `LifecycleProcessor.onClose` nhưng giữa các singleton destructions vẫn có dependency-aware ordering. Nếu bạn tự gọi `dataSource.close()` trong một **ContextClosedEvent** listener, đẩy DB sang trạng thái closed **trước** khi HTTP drain xong. Nếu một custom high-phase SmartLifecycle đóng queue/executor mà HTTP handlers còn gọi nó, các requests đang chạy có thể bị lỗi dù web server vẫn graceful.

Vì vậy cần **xem dependency graph và phase của toàn pipeline**, không chỉ giá trị phase của một bean. `@DependsOn`/constructor dependencies có thể ảnh hưởng start/stop; phải test khi có load và race. Spring Boot web server lifecycle không tự “biết” mọi side-effect trong app.

### 10.1. Khi có HTTP long-lived connections

Với **SSE, WebSocket, WebFlux Flux stream, streaming downloads hoặc async MVC**, một request có thể kéo dài hơn grace period. Cần policy rõ:
- ngừng subscription mới trước khi shutdown;
- gửi event thông báo server going away/reconnect hint nếu protocol phù hợp và connection còn sống;
- đóng stream/cancel subscription theo deadline, lưu cursor/Last-Event-ID nếu cần resume;
- dọn subscribers/resource handles;
- đảm bảo multi-replica reconnect tới instance còn sống và có replay mechanism nếu yêu cầu không mất dữ liệu.

Không tăng timeout lên vô hạn chỉ vì SSE kéo dài: rollout sẽ bị kẹt, Kubernetes có thể SIGKILL. Với WebFlux, các nguyên tắc `ApplicationContext`/`SmartLifecycle` vẫn áp dụng nhưng HTTP runtime là Reactor Netty hoặc servlet-compatible server; test shutdown qua runtime đang dùng.

### 10.2. Dừng message consumer có an toàn hơn HTTP drain không?

Không có một phase mặc định phù hợp cho mọi message broker. Một consumer đang xử lý message 30s có thể cần pause/stop receiving, commit offset/ack sau khi việc hoàn tất, tránh processing trùng sau restart. Nếu stop callback báo hoàn tất quá sớm, context có thể destroy DB/client khi consumer thread còn đang dùng. Nếu không bao giờ callback, LifecycleProcessor chờ hết phase và có thể chuyển tiếp khi consumer vẫn chạy.

Thiết kế theo contract của Kafka/Rabbit/SDK: in-flight count, ack/commit và transaction boundaries, retry/redelivery, bounded drain. **Idempotent consumers** vẫn cần vì force kill có thể xảy ra bất kỳ thời điểm nào.

## 11. Dừng bằng programmatic code: cách dùng và cảnh báo

### 11.1. `SpringApplication.exit`

Mảnh code trong một tool/CLI có chủ đích:

~~~java
ConfigurableApplicationContext ctx = SpringApplication.run(App.class, args);

// Khi có quyết định đóng ứng dụng từ luồng được kiểm soát:
int exitCode = SpringApplication.exit(ctx);
// exit() close context và tính code; muốn chấm dứt JVM:
// System.exit(exitCode);
~~~

Đây là **mảnh minh họa không độc lập** (cần `App` và imports). Không đưa đoạn này vào `main` ngay sau `run` của web service: ứng dụng sẽ đóng tức khắc. Không gọi `System.exit` từ request thread chỉ vì có lỗi nghiệp vụ; lỗi một request không phải lý do kill toàn bộ process.

### 11.2. `registerShutdownHook`

Spring Boot theo mặc định tạo shutdown hook cho context do SpringApplication quản lý. Bạn có thể có nhiều hooks JVM từ libraries; **không có thứ tự thực thi được bảo đảm giữa các JVM shutdown hooks độc lập**. Vì vậy đừng dựa vào một `Runtime.addShutdownHook` tùy ý sẽ chạy “trước Spring hook” để tự đóng DB hoặc gửi log. Ưu tiên đưa cleanup vào Spring-managed lifecycle khi các dependencies còn hoạt động.

Nếu cố ý `setRegisterShutdownHook(false)`, bạn chịu trách nhiệm explicit close theo đường đi của process. Không tắt hook để chữa một bean stop quá chậm; sửa bean stop/callback/deadline trước.

### 11.3. `ContextClosedEvent` gọi nhiều lần?

Một context bình thường chỉ close một lần, nhưng hệ thống có **context hierarchy** (parent/child Spring contexts), listeners có thể nhận events từ nhiều contexts, và test suites tạo/close nhiều contexts. Nếu business code dựa vào event để ghi audit hoặc gọi external API, phải kiểm tra event source context và idempotence; không giả định “một JVM duy nhất một event” cho mọi architecture.

## 12. Những anti-pattern về SmartLifecycle

| Anti-pattern | Nguy cơ | Cách đúng |
| --- | --- | --- |
| Implement `SmartLifecycle.stop(Runnable)` nhưng không gọi callback | Phase chờ đến timeout, shutdown kéo dài | Gọi callback sau khi stop, kể cả nhánh lỗi |
| Gọi callback ngay khi async task mới bắt đầu | Processor tiếp tục destroy beans khi task vẫn dùng | Chỉ callback sau khi thực sự hoàn tất hoặc quyết định abandon có kiểm soát |
| Block vô hạn trong `stop(Runnable)` | Shutdown hook treo, Kubernetes SIGKILL | Đặt deadline, stop cooperatively, callback |
| Dùng `@PreDestroy` để chặn HTTP request mới | Hook quá muộn so với web drain | Admission gate SmartLifecycle phase phù hợp |
| Dùng `ContextClosedEvent` để shutdown DataSource | HTTP requests chưa hoàn tất bị mất DB | Để Spring destroy resource sau drain |
| Nghĩ phase nhỏ sẽ stop trước | Thứ tự đảo: stop từ **cao xuống thấp** | Chọn phase từ dependency/drain design |
| Chỉ gắn `@Order` lên bean rồi mong lifecycle đổi | @Order không thay getPhase contract | Implement `getPhase` và dependency graph |
| Cho tất cả beans phase MAX_VALUE | Mất thứ tự có ý nghĩa, stop quá sớm | Phase rõ trách nhiệm và test |
| Dùng `server.shutdown=immediate` để “hết treo” | Cắt in-flight HTTP | Tìm slow requests/phase callback và đặt bounds |
| Đặt shutdown phase timeout quá nhỏ | Hủy app giữa transaction/download | Budget theo measured latency và retry |
| Đặt timeout quá lớn mà Pod grace 10s | Kubernetes force-kill trước khi app drain | Tăng orchestrator budget và phối hợp readiness |
| Test bằng `kill -9` rồi kết luận graceful lỗi | SIGKILL bỏ qua hooks | Test SIGTERM tới đúng JVM |
| Tin IDE Stop luôn gửi SIGTERM | Có thể force terminate | Chạy jar/process thật để test |
| Dựa vào `@PreDestroy` để lưu critical state | Không chạy khi crash/SIGKILL | Lưu state thường xuyên, retry/idempotency |
| Dùng shutdown endpoint public GET | Ai cũng có thể kill service | Process manager/orchestrator; security nghiêm |
| Dùng health readiness làm auth hoặc drain lock | Health state không ngăn races ở business | Admission gate + traffic routing + retries |
| Close thread pool trước khi consumer dùng xong | RejectedExecutionException/mất job | Stop nhận work → drain → close resource |
| Bỏ qua executor/context thread leaks | Process không thoát đúng hạn | Resource ownership, monitoring và finite deadlines |

## 13. Runbook khi service không thoát hoặc rớt request khi deploy

1. **Xác định tín hiệu dừng thật:** SIGTERM hay SIGKILL? Java là PID 1 chưa? Shell wrapper/IDE có forward signal không?
2. **Xem có `ContextClosedEvent` trong log không.** Nếu không, check signal, crash/OOM, logger shutdown order, process wrapper.
3. **Xem web server graceful logs.** Có bắt đầu drain không? `server.shutdown=immediate`? Boot version/server type?
4. **Kiểm tra `spring.lifecycle.timeout-per-shutdown-phase` và số phases**. Thời gian tổng có thể lớn hơn một phase timeout.
5. **Liệt kê các `SmartLifecycle` beans và phases** bằng dev-only instrumentation hoặc bean inspection; chú ý default phase Integer.MAX_VALUE, dependency ordering.
6. **Audit `stop(Runnable)`:** callback có được gọi đúng lúc? Có xử lý error/rejected task, isRunning state và timeout? Có thread bị block không?
7. **Tìm in-flight HTTP requests:** dài hơn grace, slow clients, SSE/WebSocket, large uploads/downloads, deadlock, slow DB.
8. **Xem background workers/DB pools:** có resource nào đóng trước khi request/job hoàn tất không? Có task mới được nhận khi sắp dừng không?
9. **Kiểm tra probes và load balancer:** readiness trở thành REFUSING_TRAFFIC, endpoint propagation delay, preStop và termination budget.
10. **Xem controller client errors:** connection refused/reset hay 503, 504 từ upstream gateway? Đừng coi mọi lỗi là ứng dụng trực tiếp trả status đó.
11. **Reproduce có kiểm soát:** chạy JAR, một request 7s, SIGTERM, quan sát log order, response; lặp với timeout 3s để thấy giới hạn.
12. **Sửa theo root cause:** phase/lifecycle callbacks, deadline, load balancer drain, retry/idempotency, thay vì chỉ tăng timeout vô hạn.

### 13.1. Bảng triệu chứng và cách phân biệt

| Dấu hiệu | Nguyên nhân khả dĩ | Phép kiểm tra |
| --- | --- | --- |
| SIGTERM nhưng không có close logs | Signal không đến Java, hard kill, crash | PID tree, container entrypoint, OS events |
| Có ContextClosedEvent nhưng server còn nhận request một lúc | Listener xảy ra trước stop phases | Theo dõi phase/grace; không coi event là server stopped |
| Bị kẹt đúng 20s ở một phase | Bean thiếu callback hoặc đang chờ 20s timeout | Inspect stop(Runnable), thread dumps |
| Pod bị giết đúng 30s | Kube terminationGracePeriod quá ngắn | Describe Pod, kubelet events, manifest |
| Đang xử lý GET 5s thì connection reset | immediate shutdown, upstream LB, timeout, SIGKILL | So web logs/curl/network/proxy |
| Graceful request xong nhưng process chưa thoát | Các phase/bean destruction/background non-daemon threads còn chạy | Thread dump và phase logs |
| HikariCP closed trước khi handler xong | Đóng resource ở event/high phase hoặc custom manual close | Find custom listener/stop logic |
| Shutdown không chờ job Kafka xong | Consumer stop callback hoàn tất quá sớm hoặc no drain | Consumer metrics/offsets/in-flight |
| Callback không được gọi do executor rejected | Executor đã stop trước component | Sửa phase/dependency, fallback completion |
| `@PreDestroy` không xuất hiện khi `kill -9` | SIGKILL không chạy hooks | Test `kill -TERM` |
| IDE stop khiến request rớt | IDE dùng force kill | Verify SIGTERM bằng jar process |
| Nginx 502/503, app chưa báo lỗi | LB/backend connector đang drain | Access logs mỗi hop, readiness |
| `/actuator/health/readiness` không trả JSON khi đang stop | Connector ngừng nhận HTTP mới | Đọc availability state trong process/logs |
| Consumer dừng trước web, gây 503 ở controller | Consumer SmartLifecycle phase cao không phù hợp | Điều chỉnh drain ordering hoặc tách pipeline |
| Ứng dụng restart nhưng job xử lý lại | At-least-once/redelivery sau crash | Idempotency, dedup, persistent checkpoints |

## 14. Checklist production

**Mục tiêu hoạt động:** Dừng nhận việc mới, xử lý xong việc được nhận trong thời hạn, đóng resources theo dependencies, kết thúc process trước deadline của orchestrator.

- [ ] Xác nhận Boot version và embedded server; `server.shutdown=graceful` đúng.
- [ ] `spring.lifecycle.timeout-per-shutdown-phase` hợp lý với tail latency thực tế.
- [ ] Có admission/drain policy cho web requests, consumers, schedulers và streaming endpoints.
- [ ] SmartLifecycle phases thể hiện dependency; không rely ngẫu nhiên vào MAX phase.
- [ ] Tất cả `stop(Runnable)` gọi callback đúng một lần sau stop hoặc kết thúc lỗi có kiểm soát.
- [ ] Mỗi drain có deadline; resources còn sống cho tới khi những callers cuối hoàn tất.
- [ ] `@PreDestroy` cleanup bounded, idempotent, không gọi service đã stop.
- [ ] JVM nhận SIGTERM tới đúng PID; không bị shell wrapper nuốt signal.
- [ ] Kubernetes terminationGracePeriodSeconds đủ cho preStop + sum stop phases + destruction + margin.
- [ ] Readiness không nhận traffic mới; load balancer có routing/drain policy phù hợp.
- [ ] Long-lived SSE/WebSocket/async requests có chiến lược close/reconnect.
- [ ] Hàng đợi/broker jobs có checkpoint, retry, idempotent processing.
- [ ] Test bằng SIGTERM với in-flight request, slow DB/client, background jobs, load và forced kill.
- [ ] Logs/metrics đo time-to-drain, active requests/jobs, phase timeouts và errors.
- [ ] Không coi graceful shutdown là sự bảo đảm exactly-once hoặc transaction commit.

## 15. Câu hỏi tự kiểm tra

1. `ApplicationContext.close()` có phải chỉ gọi `Tomcat.stop()` không?
2. `ContextClosedEvent` đến trước hay sau `LifecycleProcessor.onClose()`?
3. `@PreDestroy` thường chạy trước hay sau SmartLifecycle stop processing?
4. `SmartLifecycle.isAutoStartup()` mặc định là gì?
5. `SmartLifecycle.DEFAULT_PHASE` là giá trị gì?
6. Start phases tăng hay giảm? Stop phases tăng hay giảm?
7. Vì sao dependency relationships có thể thay đổi thứ tự dự kiến từ phase?
8. `DefaultLifecycleProcessor` chờ callback nào ở async stop?
9. Vì sao quên `callback.run()` khiến shutdown bị chậm?
10. `spring.lifecycle.timeout-per-shutdown-phase` là tổng thời gian JVM shutdown hay mỗi phase?
11. Trong Boot 3.5, graceful shutdown được bật mặc định với những web servers nào?
12. `server.shutdown=immediate` khác `graceful` ở điều gì?
13. Một component muốn giữ DB service sống đến khi HTTP drain xong nên stop trước hay sau web server?
14. Tại sao `ContextClosedEvent` không phải nơi lý tưởng để close HikariCP sớm?
15. Vì sao `@Order(1)` không tự thay thế `SmartLifecycle.getPhase()`?
16. `kill -9` có chạy JVM shutdown hooks và `@PreDestroy` không?
17. Vì sao `mvn spring-boot:run` có thể không phải cách ổn định nhất để test SIGTERM?
18. Kubernetes `preStop` có tiêu thụ terminationGracePeriodSeconds không?
19. Khi có readiness `REFUSING_TRAFFIC`, một external HTTP probe có nhất thiết nhận 503/JSON không?
20. Vì sao requests > grace period có thể fail dù đang dùng graceful mode?
21. Thế nào là stop callback báo hoàn tất quá sớm?
22. Khi một background queue consumer không có SmartLifecycle, web graceful có chờ nó không?
23. Vì sao cần idempotent retry sau crash dù đã bật graceful shutdown?
24. Có thể dùng `SpringApplication.exit(context)` mà không gọi `System.exit` không?
25. Với SSE/WebSocket mở vô hạn, cần policy gì khi rollout?
26. Trong test `LifecyclePhaseTest`, vì sao start low/high nhưng stop high/low?
27. Mốc nào đúng hơn để giải phóng bean resources: ContextClosedEvent hay singleton destroy callbacks?
28. Nếu process bị OOM kill, nên dựa vào những persistence primitives nào thay vì @PreDestroy?
29. Dùng phase rất cao cho admission gate có mục đích gì?
30. Khi timeout mỗi phase là 20s nhưng tổng shutdown mất 50s, có nhất thiết framework sai không?

**Đáp án trọng tâm:** (1) Không, đóng cả Spring context, lifecycle, destroy callbacks. (2) Trước. (3) Sau lifecycle stop processing. (4) True. (5) Integer.MAX_VALUE. (6) Start tăng, stop giảm. (7) Phụ thuộc được ưu tiên. (8) SmartLifecycle.stop(Runnable). (9) Processor đợi tới timeout. (10) Mỗi phase. (11) Tomcat, Jetty, Reactor Netty, Undertow. (12) Drain in-flight vs dừng ngay. (13) Sau web server drain. (14) Request còn cần DB. (15) Phase thuộc lifecycle processor, @Order không thay thế. (16) Không. (17) Tín hiệu có thể tới process wrapper. (18) Có. (19) Không, connector có thể đã đóng. (20) Deadline hữu hạn. (21) Báo xong khi task vẫn chạy và còn dùng dependencies. (22) Không tự biết job của bạn. (23) Forced kill và network failures vẫn xảy ra. (24) Có, return exit code; JVM termination riêng. (25) Close/cancel, reconnect/resume, limits. (26) Stop đảo phase start. (27) Sau drain, bean destruction. (28) Durable queue/checkpoints/idempotency. (29) Ngừng nhận việc trước web drain. (30) Không, nhiều phases/destruction/preStop.

## 16. Tài liệu chính thức

- Spring Boot 3.5 — **Graceful Shutdown** (mặc định, web servers, per-phase timeout, reject differences): https://docs.spring.io/spring-boot/3.5/reference/web/graceful-shutdown.html
- Spring Boot 3.5 — **SpringApplication, Application Exit, JVM shutdown hook và events**: https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html
- Spring Boot 3.5 — **Actuator Endpoints, Application Lifecycle and Probe States**: https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html
- Spring Framework 6.2 — **Customizing the Nature of a Bean: Lifecycle và SmartLifecycle phase**: https://docs.spring.io/spring-framework/reference/6.2/core/beans/factory-nature.html
- Spring Framework 6.2 — **SmartLifecycle API**, callback, DEFAULT_PHASE: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/SmartLifecycle.html
- Spring Framework 6.2 — **DefaultLifecycleProcessor API**, phase ordering và shutdown waits: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/support/DefaultLifecycleProcessor.html
- Spring Framework 6.2 — **AbstractApplicationContext API**, doClose/ContextClosedEvent/destroyBeans: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/support/AbstractApplicationContext.html
- Spring Boot 3.5 — **WebServerGracefulShutdownLifecycle API**: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/web/context/WebServerGracefulShutdownLifecycle.html
- Kubernetes — **Pod Termination/Lifecycle**, preStop and terminationGracePeriodSeconds: https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/#pod-termination
- Spring Boot 3.5.16 release và trạng thái hỗ trợ: https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now/
