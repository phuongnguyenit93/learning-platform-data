# Dừng có kiểm soát (graceful shutdown) và dừng ngay trong Spring Boot

## 1. Tại sao cần phân biệt các cách dừng?

Một ứng dụng Spring Boot có thể đang phục vụ HTTP request, ghi database, gửi message, chạy `@Scheduled` hoặc xử lý `@Async` khi được yêu cầu kết thúc. Nếu tiến trình bị ngắt khi công việc chưa tới ranh giới commit, client có thể thấy lỗi; message có thể được xử lý lại hoặc mất trạng thái tạm; connection và resource có thể chưa được giải phóng sạch.

**Graceful shutdown** là cách dừng có điều phối: dừng nhận việc mới, cho việc đang diễn ra cơ hội hoàn tất trong một ngân sách thời gian hữu hạn, sau đó đóng tài nguyên và kết thúc process. **Immediate server shutdown** là tắt chế độ chờ các HTTP requests đang xử lý khi đóng web server, **không phải** cưỡng bức kill toàn JVM. Còn `SIGKILL` là dừng cưỡng bức ở mức hệ điều hành/container và không cho Java tiếp tục đường shutdown thông thường.

Trong Spring Boot **3.5.x**, graceful shutdown là cấu hình mặc định với **Tomcat, Jetty, Undertow và Reactor Netty**, đối với servlet và reactive web applications. Spring Boot thực hiện graceful shutdown như một phần của quá trình đóng `ApplicationContext`, tại một phase dừng sớm của các `SmartLifecycle` beans.

Các câu hỏi cần trả lời khi thiết kế:
- Request mới bị xử lý thế nào khi đang dừng?
- Request và job đã chạy có cơ hội hoàn tất không?
- Bean, executor, scheduler và database connection đóng theo thứ tự nào?
- Thời hạn Spring khác với thời hạn Kubernetes ra sao?
- Khi nào dừng bằng `SIGTERM`, khi nào một process bị `SIGKILL`?
- Làm sao kiểm chứng bằng Java code, HTTP client, log và exit status?

## 2. Bốn phương thức kết thúc và hệ quả

| Cơ chế | Tác động trọng tâm | In-flight HTTP | Callback dọn dẹp |
| --- | --- | --- | --- |
| `server.shutdown=graceful` kết hợp context close | Web server ngừng nhận request mới và chờ có giới hạn | Có cơ hội hoàn tất | Spring lifecycle/destroy callbacks chạy theo cơ chế đóng context |
| `server.shutdown=immediate` kết hợp context close | Bỏ giai đoạn chờ graceful HTTP | Không được bảo đảm, nhưng một số request có thể kịp hoàn tất | Context vẫn gọi các callback lifecycle/destroy phù hợp |
| `SIGTERM` JVM nhận được | Bắt đầu đường shutdown JVM, thông thường kích hoạt shutdown hooks | Phụ thuộc Spring hook và các timeout | Có cơ hội nếu không bị kill trước hạn |
| `SIGKILL` / kill -9 | Kernel/container cưỡng bức dừng process | Không | JVM shutdown hooks và `@PreDestroy` không có cơ hội chạy |
| `context.close()` | Đóng `ConfigurableApplicationContext` theo Java API | Tùy graceful/immediate của server | Có |
| `SpringApplication.exit(context)` | Đóng context, tính exit code | Tùy server | Có |
| `System.exit(status)` | Khởi tạo JVM shutdown theo cơ chế bình thường | Tùy hooks và timing | Hooks có thể chạy |
| `Runtime.halt(status)` | Dừng JVM cưỡng bức | Không | Không theo đường hook bình thường |

**Không đồng nhất `server.shutdown=immediate` với `System.exit` hoặc `SIGKILL`.** Một property Spring Boot chỉ quyết định cách embedded web server đóng trong context lifecycle; nó không tự gửi signal, tắt nguồn process hay bỏ qua mọi bean destruction.

### Lược đồ đường dừng bình thường

~~~mermaid
flowchart TD
  A["App đang phục vụ request"] --> B["SIGTERM hoặc context.close()"]
  B --> C["ContextClosedEvent"]
  C --> D["SmartLifecycle shutdown theo phase"]
  D --> E{"server.shutdown?"}
  E -->|"graceful"| F["Dừng nhận request mới, chờ in-flight có hạn"]
  E -->|"immediate"| G["Dừng web server không đợi theo cơ chế graceful"]
  F --> H["Dừng lifecycle components còn lại"]
  G --> H
  H --> I["@PreDestroy / DisposableBean / custom destroy"]
  I --> J["Resource cleanup, kết thúc context"]
  J --> K["JVM thoát khi điều kiện process cho phép"]
~~~

Sơ đồ là **mô hình khái niệm**, không phải một khẳng định tuyệt đối về thứ tự log giữa những bean custom, executor và thư viện. Đường `SIGKILL` không đi theo các bước cleanup trên.

## 3. Cấu hình Spring Boot 3.5

### Graceful shutdown được bật mặc định

~~~properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
~~~

Hoặc:

~~~yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 20s
~~~

`server.shutdown=graceful` đã là mặc định trên Spring Boot 3.5 với embedded servers được hỗ trợ; khai báo rõ để người đọc biết chủ đích. Giá trị `20s` là **ví dụ tự đặt**, không phải default: trong tài liệu Spring Boot 3.5, `spring.lifecycle.timeout-per-shutdown-phase` mặc định là **30s**.

**Timeout này tính theo từng phase/group `SmartLifecycle`**, không phải giới hạn tuyệt đối cho toàn bộ việc dừng JVM. Có thể tồn tại nhiều phases, destroy callbacks, shutdown hooks và việc ngoài container. Tổng thời gian SIGTERM→exit có thể dài hơn một khoảng timeout phase.

### Dừng web server không chờ graceful

~~~properties
server.shutdown=immediate
~~~

Khi context đóng, server không thực hiện giai đoạn bảo vệ HTTP in-flight bằng cơ chế graceful. Tuy nhiên, một request ngắn có thể đã kết thúc đúng lúc trước khi server đóng; vì thế không được khẳng định “mọi request immediate luôn lỗi”. Phải quan sát request ở thời điểm thực sự đã được server nhận.

### Các thuộc tính liên quan nhưng khác mục đích

| Thuộc tính | Tác dụng | Không làm được |
| --- | --- | --- |
| `server.shutdown` | Chọn HTTP graceful hoặc immediate | Không tự kill JVM |
| `spring.lifecycle.timeout-per-shutdown-phase` | Giới hạn thời gian chờ cho từng lifecycle stop phase | Không tự chặn tác vụ Java không hợp tác interrupt |
| `spring.main.register-shutdown-hook` | Có đăng ký JVM shutdown hook từ `SpringApplication` hay không | Không làm `SIGKILL` thành graceful |
| `spring.task.execution.shutdown.await-termination` | Cấu hình chờ task executor phù hợp khi đóng | Không ảnh hưởng executor tùy ý tự tạo ngoài Spring |
| `spring.task.scheduling.shutdown.await-termination` | Cấu hình chờ scheduler phù hợp khi đóng | Không làm mọi job nghiệp vụ chắc chắn commit |
| `spring.main.keep-alive` | Giữ app sống khi thiếu non-daemon threads | Không phải cờ bật graceful shutdown |

## 4. Request đang chạy và request mới

### Hành vi HTTP trong grace period

Spring Boot 3.5 mô tả:
- **Tomcat, Jetty, Reactor Netty** ngừng chấp nhận request/kết nối mới tại tầng network trong cơ chế graceful.
- **Undertow** có thể chấp nhận kết nối mới nhưng đáp ngay `HTTP 503 Service Unavailable`.
- Cơ chế kết nối giữ sống, HTTP protocol và embedded server implementation có thể làm chi tiết khác nhau.

Khi bắt đầu drain, những request đã được xử lý có cơ hội kết thúc trong giới hạn. Nếu một HTTP handler cần 45 giây nhưng timeout phase chỉ có 20 giây, **không có bảo đảm** handler trả thành công; client có thể thấy timeout, connection reset hoặc trạng thái tương ứng web server.

Với **SSE, WebSocket, streaming, long-polling**, request/connection có thể kéo dài rất lâu và không phù hợp với giả định “tất cả kết thúc trong vài giây”. Cần thiết kế cách đóng session/stream và gửi tín hiệu reconnect phù hợp.

### Request hoàn tất khác job hoàn tất

Nếu endpoint trả `HTTP 202 Accepted` ngay sau khi enqueue job, request HTTP coi như đã kết thúc nhưng background job có thể vẫn chạy. HTTP graceful shutdown **không tự chờ** mọi future hay queue job chỉ vì request khởi tạo job từng chạy thành công.

Tương tự, dòng log “response sent” không nhất thiết chứng minh toàn bộ database transaction, message acknowledgement hay remote side effect đã commit. Đừng dùng một response 200 đơn lẻ làm bằng chứng không thể mất dữ liệu khi shutdown.

## 5. Spring Context lifecycle và callback dọn dẹp

Spring Boot mặc định đăng ký JVM shutdown hook cho mỗi `SpringApplication` để context được đóng theo đường shutdown bình thường. Khi context đóng, Spring Framework có các extension point:

- `ContextClosedEvent`: tín hiệu context bắt đầu đóng.
- `SmartLifecycle.stop(Runnable callback)`: cơ chế stop theo phase, có thể chờ bất đồng bộ.
- `@PreDestroy`: callback destroy trên managed bean, dùng package `jakarta.annotation` trong Spring Boot 3.x.
- `DisposableBean.destroy()`: callback theo interface Spring.
- Custom destroy method: ví dụ bean `@Bean(destroyMethod = "close")`.

### ContextClosedEvent

~~~java
import org.springframework.context.event.ContextClosedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
class ClosingListener {
    @EventListener
    void onContextClosed(ContextClosedEvent event) {
        System.out.println("CONTEXT_CLOSING");
    }
}
~~~

Đây là class có thể đặt trong package Spring component scan. Listener nên ngắn, an toàn, không tự tạo tác vụ không được quản lý, không giả định mọi network client vẫn hoạt động trong suốt shutdown.

### @PreDestroy

~~~java
import jakarta.annotation.PreDestroy;
import org.springframework.stereotype.Component;

@Component
class ManagedResource {
    @PreDestroy
    void release() {
        System.out.println("RESOURCE_DESTROYED");
    }
}
~~~

Chỉ bean do container quản lý mới được lifecycle callbacks này. Nếu class được tạo bằng `new` ngoài context, container không tự gọi `release()`. Nếu bị `SIGKILL`, `@PreDestroy` không chạy. Nếu không thể tạo bean ngay từ startup, cũng không thể kỳ vọng bean chưa tạo nhận destroy callback.

Nếu cùng bean khai báo đủ các hook destroy, tài liệu Spring Framework mô tả thứ tự phổ biến là `@PreDestroy`, `DisposableBean.destroy()` và custom destroy method. Tránh đóng một resource nhiều lần nếu API không idempotent.

### SmartLifecycle phase

`SmartLifecycle` cho phép tự động start/stop một component và chọn phase:

~~~text
START: phase nhỏ -> phase lớn
STOP:  phase lớn -> phase nhỏ
~~~

Thứ tự còn chịu ảnh hưởng quan hệ `depends-on`: bean phụ thuộc phải được dừng trước khi dependency của nó bị hủy. Spring Boot dùng phase thích hợp để xử lý HTTP graceful shutdown sớm trong quá trình stop.

`SmartLifecycle.stop(Runnable callback)` phải gọi callback sau khi việc dừng đã hoàn thành. Nếu không gọi, lifecycle processor có thể chờ đến timeout của phase. Với tác vụ async, callback nên được gọi trong `finally` của worker drain hoặc đường hoàn tất tương ứng, không được gọi ngay khi tác vụ còn chạy rồi tuyên bố đã dừng sạch.

### Một class minh họa quản lý executor

~~~java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

import org.springframework.context.SmartLifecycle;
import org.springframework.stereotype.Component;

@Component
public final class ManagedJobLifecycle implements SmartLifecycle {
    private final AtomicBoolean running = new AtomicBoolean(false);
    private final ExecutorService pool =
            Executors.newSingleThreadExecutor();

    @Override
    public void start() {
        running.set(true);
    }

    @Override
    public boolean isRunning() {
        return running.get();
    }

    @Override
    public int getPhase() {
        return 0;
    }

    @Override
    public void stop(Runnable callback) {
        running.set(false);  // cần ngừng nhận job mới ở đây
        pool.shutdown();

        Thread waiter = new Thread(() -> {
            try {
                if (!pool.awaitTermination(
                        8, TimeUnit.SECONDS)) {
                    pool.shutdownNow();
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                pool.shutdownNow();
            } finally {
                callback.run();
            }
        }, "job-drain-waiter");

        waiter.setDaemon(true);
        waiter.start();
    }

    @Override
    public void stop() {
        running.set(false);
        pool.shutdownNow();
    }
}
~~~

Đây là class Java có cú pháp hợp lệ, nhưng chưa có API submit job vì trách nhiệm của nó là minh họa stop. Trong ứng dụng thật phải có intake gate và theo dõi job đã commit hay chưa. `shutdownNow()` chỉ **cố gắng** interrupt; nếu job bỏ qua interrupt, callback gọi sau deadline **không có nghĩa tất cả business work đã thành công**.

Nếu không cần quản lý thủ công, ưu tiên `TaskExecutor`/`TaskScheduler` hoặc các container listener của Spring với chính sách stop được framework hỗ trợ.

## 6. Ví dụ Spring Boot Java 17+ chạy được

Dự án dùng Spring Boot 3.5.16, Java 17+, Maven, Spring Web và Actuator. Một endpoint giữ request 5 giây để thử graceful, một endpoint `/ping` để kiểm tra, và một bean ghi mốc shutdown.

Cây file:

~~~text
graceful-lab/
├── pom.xml
└── src/main/
    ├── java/com/example/grace/
    │   ├── GracefulLabApplication.java
    │   ├── WorkController.java
    │   └── ClosingObserver.java
    └── resources/application.yaml
~~~

### pom.xml

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
    <artifactId>graceful-lab</artifactId>
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

### application.yaml

~~~yaml
spring:
  application:
    name: graceful-lab
  main:
    banner-mode: "off"
  lifecycle:
    timeout-per-shutdown-phase: 12s

server:
  port: 18080
  shutdown: graceful

management:
  endpoint:
    health:
      probes:
        enabled: true
~~~

Timeout 12s là thời gian lab đủ để quan sát request 5s và thử request dài hơn ngưỡng. Không coi đây là con số production mặc định. Readiness health probe được bật để script chờ startup xong trước khi thử dừng.

### GracefulLabApplication.java

~~~java
package com.example.grace;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class GracefulLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(GracefulLabApplication.class, args);
    }
}
~~~

### WorkController.java

~~~java
package com.example.grace;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
public class WorkController {
    private final AtomicInteger active = new AtomicInteger();

    @GetMapping("/ping")
    public String ping() {
        return "pong";
    }

    @GetMapping("/active")
    public int active() {
        return active.get();
    }

    @GetMapping("/work")
    public String work(
            @RequestParam(defaultValue = "5000") long millis)
            throws InterruptedException {

        if (millis < 0 || millis > 15000) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "Invalid millis");
        }

        int count = active.incrementAndGet();
        System.out.println("WORK_BEGIN active=" + count);
        try {
            Thread.sleep(millis);
            System.out.println("WORK_FINISHED");
            return "finished";
        } finally {
            active.decrementAndGet();
        }
    }
}
~~~

`AtomicInteger` đếm request đang chạy để quan sát trong lab, không thay cho transaction commit hay durable job queue. `Thread.sleep` chỉ giả lập một request chờ, không nên dùng trong logic production để làm ứng dụng “graceful”.

### ClosingObserver.java

~~~java
package com.example.grace;

import jakarta.annotation.PreDestroy;
import org.springframework.context.event.ContextClosedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class ClosingObserver {

    @EventListener
    public void onClose(ContextClosedEvent event) {
        System.out.println("CONTEXT_CLOSING");
    }

    @PreDestroy
    void destroy() {
        System.out.println("BEAN_DESTROYED");
    }
}
~~~

Nếu JVM nhận signal shutdown bình thường và Spring context được đóng, bean ghi hai mốc này. Không kỳ vọng callback chạy nếu process bị `SIGKILL` hoặc OOMKill.

### Chạy

~~~bash
mvn -q -DskipTests package
java -jar target/graceful-lab-0.0.1-SNAPSHOT.jar
~~~

Ở terminal khác:

~~~bash
curl -fsS http://127.0.0.1:18080/ping
curl -fsS http://127.0.0.1:18080/actuator/health/readiness
~~~

Body của `/ping`:

~~~text
pong
~~~

Khi ứng dụng đã ready, health readiness trong cấu hình mặc định thường trả status `UP`. Không kiểm thử dựa vào thứ tự trường JSON vì Actuator có thể được cấu hình thêm.

## 7. Thử gửi SIGTERM đúng lúc request đang xử lý

Cần **gửi signal tới Java PID**, không chỉ tới một shell wrapper. Dùng Linux/Bash để tự động chờ server ready, bảo đảm request đã vào controller rồi mới gửi TERM.

Tạo **measure-shutdown.sh** trong thư mục cùng `pom.xml`:

~~~bash
#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: bash measure-shutdown.sh graceful|immediate" >&2
  exit 2
fi

mode="$1"
if [[ "$mode" != "graceful" &&
      "$mode" != "immediate" ]]; then
  echo "Invalid mode" >&2
  exit 2
fi

jar="target/graceful-lab-0.0.1-SNAPSHOT.jar"
log="app-$mode.log"
response="response-$mode.txt"

java -jar "$jar" "--server.shutdown=$mode" \
    >"$log" 2>&1 &
pid=$!

cleanup() {
  kill -TERM "$pid" 2>/dev/null || true
}
trap cleanup EXIT

ready=0
for ((i=0; i<300; i++)); do
  if curl --max-time 1 -fsS -o /dev/null \
      http://127.0.0.1:18080/actuator/health/readiness \
      2>/dev/null; then
    ready=1
    break
  fi

  if ! kill -0 "$pid" 2>/dev/null; then
    echo "App exited early, inspect $log" >&2
    exit 1
  fi
  sleep 0.1
done

if [[ "$ready" -ne 1 ]]; then
  echo "Readiness timeout" >&2
  exit 1
fi

curl --max-time 25 -fsS \
    "http://127.0.0.1:18080/work?millis=5000" \
    >"$response" 2>"curl-$mode.err" &
reqpid=$!

seen=0
for ((i=0; i<100; i++)); do
  if grep -q "WORK_BEGIN active=" "$log"; then
    seen=1
    break
  fi
  if ! kill -0 "$reqpid" 2>/dev/null; then
    break
  fi
  sleep 0.05
done

if [[ "$seen" -ne 1 ]]; then
  echo "Request not confirmed; inspect $log" >&2
  kill -TERM "$pid" 2>/dev/null || true
  wait "$reqpid" 2>/dev/null || true
  wait "$pid" 2>/dev/null || true
  exit 1
fi

started_ns=$(date +%s%N)
kill -TERM "$pid"

set +e
wait "$reqpid"
request_exit=$?
wait "$pid"
java_exit=$?
set -e

ended_ns=$(date +%s%N)
duration_ms=$(( (ended_ns - started_ns) / 1000000 ))

echo "mode=$mode"
echo "request_exit=$request_exit"
echo "java_exit=$java_exit"
echo "shutdown_ms=$duration_ms"

grep -E "WORK_BEGIN|WORK_FINISHED|CONTEXT_CLOSING|BEAN_DESTROYED" \
    "$log" || true
~~~

Chạy từng lượt, không chạy cùng lúc trên port 18080:

~~~bash
bash measure-shutdown.sh graceful
bash measure-shutdown.sh immediate
~~~

**Đây là script dành cho Linux với GNU `date`** hỗ trợ `%N`; Bash/macOS mặc định có thể không hỗ trợ cách lấy nanoseconds này. Ngoài ra cần `curl`, `grep`, Java 17+ và JAR đã build. Script có timeout để tránh chờ server vô hạn, nhưng khi một task bỏ qua TERM hoặc shutdown hook treo bất thường, lệnh `wait "$pid"` vẫn có thể kéo dài; trong CI nên bọc thêm một watchdog/timeout bên ngoài với chính sách kill rõ ràng.

### Kết quả cần quan sát

Với chế độ `graceful` và request năm giây, nếu signal đến đúng lúc, timeout phase là mười hai giây và không có thành phần nào khác cản trở, **kỳ vọng**:
- Controller đã log `WORK_BEGIN`.
- Request có cơ hội log `WORK_FINISHED` và client nhận body `finished`.
- Spring log mốc đóng context/destroy.
- Tiến trình kết thúc sau khi request drain và các callback đóng hoàn tất.

Nhưng **không hứa kết quả timing cố định**. Mode `immediate` có thể làm request thất bại hoặc kịp hoàn tất tùy timing/server. So sánh các log, `request_exit` và `shutdown_ms` qua nhiều lần chạy; không kết luận chỉ bằng một run.

Nếu `request_exit=0`, client đã nhận response thành công, nhưng **không** chứng minh mọi message/DB transaction trong ứng dụng lớn đã commit. Nếu `java_exit` khác 0, đọc JVM/server logs và status signal để hiểu chính xác.

### Thử vượt deadline

Thay `millis=5000` bằng `millis=15000` trong script, giữ `timeout-per-shutdown-phase=12s`. Vì request dài hơn ngân sách phase, **không có bảo đảm** client sẽ nhận body hoàn chỉnh. Thí nghiệm này cho thấy vì sao application cần request timeouts, retry và idempotency, không chỉ tăng grace vô hạn.

## 8. Từ signal đến context: System.exit và SpringApplication.exit

### Đóng context trong Java

~~~java
ConfigurableApplicationContext context =
        SpringApplication.run(MyApplication.class, args);

// Khi đã đến điểm cần dừng hợp lệ:
context.close();
~~~

Đây là **snippet**, cần import `ConfigurableApplicationContext` và `SpringApplication`, và phải có class `MyApplication`. Đối với một web application chạy lâu, **không gọi `context.close()` ngay sau `run`**: điều đó khiến web server bắt đầu shutdown ngay sau startup.

### SpringApplication.exit và exit code

Đối với CLI/batch app, có thể dùng:

~~~java
int status = SpringApplication.exit(context);
System.exit(status);
~~~

`SpringApplication.exit` đóng context và lấy exit code thông qua `ExitCodeGenerator` nếu phù hợp, sau đó `System.exit` truyền code cho OS. Ví dụ bean:

~~~java
@Bean
ExitCodeGenerator exitCodeGenerator() {
    return () -> 7;
}
~~~

Snippet cần import `ExitCodeGenerator` và `@Bean`, và đặt trong một Spring config class. Đây không phải cách mặc định để web application tự exit sau khi `ApplicationReadyEvent`: event ready báo startup xong chứ **không** phải lệnh kết thúc service.

### System.exit và Runtime.halt

`System.exit(code)` yêu cầu JVM shutdown theo đường bình thường và các shutdown hooks được khởi chạy. Nhưng không bảo đảm hoàn tất mọi worker tùy biến đang chạy. `Runtime.halt(code)` chấm dứt cưỡng bức, không chạy đường hook; tránh dùng để quản lý shutdown bình thường.

### Spring Boot shutdown hook

Mặc định `SpringApplication` đăng ký shutdown hook. Nếu cấu hình `spring.main.register-shutdown-hook=false` hoặc tự xây lifecycle khác, đường TERM→context.close không còn được bảo đảm theo cấu hình mặc định. Trong container, kiểm tra Java có thật sự là PID nhận signal không.

## 9. Readiness, liveness và giai đoạn drain

Spring Boot có `ApplicationAvailability` và Actuator health groups cho liveness/readiness. Mô hình trong shutdown:

| Giai đoạn | Liveness | Readiness | Ý nghĩa |
| --- | --- | --- | --- |
| Đang hoạt động | `CORRECT` | `ACCEPTING_TRAFFIC` | Có thể route request |
| Graceful shutdown | `CORRECT` | `REFUSING_TRAFFIC` | Không nên gửi việc mới; xử lý in-flight nếu còn |
| Đóng xong context | Không còn probe HTTP có ý nghĩa | Không còn probe HTTP có ý nghĩa | Process ngừng phục vụ |

**Điểm tinh tế:** khi web server đã từ chối request mới, endpoint HTTP `/actuator/health/readiness` cũng có thể không truy cập được. Vì vậy bên ngoài không nhất thiết đọc được JSON chứa trạng thái `REFUSING_TRAFFIC`; đó là hành vi hợp lệ trong giai đoạn đóng.

Mốc `ApplicationReadyEvent` khi startup không chứng minh mọi background job đã hoàn tất. Một application có thể ready, trả HTTP 200 và đồng thời vẫn xử lý queue jobs; cần quan sát, dừng và xác nhận vòng đời công việc đó riêng.

## 10. Kubernetes và Docker: ngân sách dừng của nền tảng

Kubernetes thường có các bước:
1. Pod được đánh dấu terminating; EndpointSlice/traffic routing bắt đầu cập nhật.
2. Nếu có `preStop` hook, kubelet chạy nó trước khi yêu cầu runtime gửi TERM.
3. Runtime gửi `SIGTERM` cho PID 1 trong container.
4. JVM/Spring Boot xử lý shutdown nếu còn khả năng.
5. Nếu vượt `terminationGracePeriodSeconds`, kubelet gửi `SIGKILL` để dừng cưỡng bức.

**Thời gian của `preStop` nằm trong tổng ngân sách termination**, không phải khoảng thời gian miễn phí cộng thêm. Kubernetes có xử lý gia hạn nhỏ trong một số trường hợp preStop vượt hạn, nhưng không nên thiết kế dựa vào gia hạn đó.

### Deployment minh họa

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: graceful-lab
spec:
  replicas: 2
  selector:
    matchLabels:
      app: graceful-lab
  template:
    metadata:
      labels:
        app: graceful-lab
    spec:
      terminationGracePeriodSeconds: 45
      containers:
        - name: app
          image: registry.example.org/demo/graceful-lab:1.0
          ports:
            - containerPort: 18080
          startupProbe:
            httpGet:
              path: /actuator/health/liveness
              port: 18080
            periodSeconds: 2
            failureThreshold: 30
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: 18080
            periodSeconds: 5
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: 18080
            periodSeconds: 10
~~~

Đây là **manifest minh họa**; image phải được build/push và thay bằng image hợp lệ của dự án. Cần security, namespace, quotas, image credentials và các điều kiện deploy phù hợp. Không tự áp dụng manifest thẳng vào production.

`terminationGracePeriodSeconds=45` là ngân sách tổng của Pod; `spring.lifecycle.timeout-per-shutdown-phase=12s` tính cho từng phase. Nếu có nhiều phases, preStop hoặc cleanup lâu, tổng có thể vẫn vượt 45 giây. Hãy đo **TERM→exit thực tế** dưới tải trước khi chọn ngân sách Kubernetes.

### Container PID 1

Dạng Dockerfile:

~~~dockerfile
ENTRYPOINT ["java", "-jar", "/app/graceful-lab.jar"]
~~~

giúp JVM trực tiếp nhận signal trong container thông thường. Nếu khởi chạy Java qua shell script, đoạn cuối nên dùng `exec java ...` hoặc bảo đảm shell forward TERM đúng, thay vì để shell nhận signal nhưng JVM con không nhận. Đừng cho rằng nhấn stop trên IDE sẽ có cùng hành vi SIGTERM của Kubernetes.

### preStop có luôn cần thiết không?

Không. Có thể cần nếu load balancer đặc thù yêu cầu khoảng drain để đồng bộ routing, nhưng một `preStop` chỉ ngủ quá lâu sẽ ăn mất ngân sách shutdown. Nếu container dùng distroless image, `/bin/sh` hoặc `sleep` có thể không tồn tại. Chỉ thêm preStop khi đã xác định được vấn đề routing cụ thể và có phép đo.

## 11. @Async, scheduler, message consumer và transaction

**Web graceful shutdown chỉ xử lý web requests**, không tự đảm bảo mọi tác vụ trong process hoàn tất. Với các executor/scheduler được Spring Boot auto-configure, có thể cân nhắc:

~~~properties
spring.task.execution.shutdown.await-termination=true
spring.task.execution.shutdown.await-termination-period=20s
spring.task.scheduling.shutdown.await-termination=true
spring.task.scheduling.shutdown.await-termination-period=20s
~~~

Tác dụng chính xác phụ thuộc loại executor và Spring Boot version; chúng không tự áp dụng lên một `Executors.newFixedThreadPool(...)` mà ứng dụng tự tạo. Nếu đang dùng virtual threads trên Java 21+, kiểm tra lại loại task executor và thông số có còn tác dụng hay không.

### Dừng một queue consumer an toàn

Trình tự thực tế thường là:
1. Đánh dấu consumer không nhận job mới.
2. Ngừng polling/claim thêm message.
3. Chờ những job đang xử lý đến ranh giới commit hoặc deadline.
4. Ack/commit khi thực sự thành công; retry/requeue theo hợp đồng broker khi chưa xong.
5. Đóng producer/consumer/network clients sau khi công việc liên quan không còn dùng chúng.

Các chi tiết khác nhau giữa Kafka, RabbitMQ, JMS và queue custom. Không khẳng định một message “không mất” chỉ vì Spring Boot đã đóng context. Dùng idempotency, durable queue, timeout và checkpoint.

### Database và resource dependencies

Một executor dừng quá muộn có thể cố sử dụng datasource/client đã bị destroy. Đảm bảo stop phase/dependency order phù hợp. Lỗi client HTTP hoặc interrupt không tự chứng minh transaction đã rollback hay commit; kiểm tra transaction manager, DB logs và business outcome.

### Scheduler

Dừng scheduler khác với hoàn tất tất cả job đang chạy. Với Quartz, Spring Boot có property `spring.quartz.wait-for-jobs-to-complete-on-shutdown`; phải cấu hình theo yêu cầu tác vụ. Đừng để một job không có timeout giữ quá trình shutdown vô hạn.

## 12. Những lỗi vận hành hay gặp

| Dấu hiệu | Nguyên nhân khả dĩ | Cách xác minh và sửa |
| --- | --- | --- |
| `SIGTERM` gửi rồi process vẫn không thoát | Thread non-daemon tự tạo, task blocked, stop callback thiếu | Thread dump, xem `SmartLifecycle`, interrupt/timeout |
| `@PreDestroy` không chạy khi kill -9 | `SIGKILL` cưỡng bức | Sử dụng TERM bình thường; có recovery cho force kill |
| `server.shutdown=immediate` nhưng destroy callback vẫn chạy | Immediate chỉ ảnh hưởng HTTP graceful waiting | Đây có thể là hành vi đúng |
| Graceful request ngắt dù timeout đã cấu hình | Request vượt deadline, client cancel, SIGKILL sớm, server behavior | So logs, deadlines và signal |
| Readiness endpoint không truy cập được khi shutdown | Web server từ chối kết nối mới | Đọc log/EndpointSlice thay vì đòi health JSON |
| Shutdown lâu hơn timeout đã đặt | Timeout **per-phase**, còn cleanup/hook khác | Đo toàn bộ SIGTERM→exit và từng phase |
| Kubernetes SIGKILL dù Spring configured 20s | Pod grace không đủ, preStop tiêu tốn thời gian | Tăng hợp lý tổng grace dựa trên số đo |
| HTTP 202 trả rồi job chưa xong | Công việc được tách khỏi HTTP lifecycle | Quản lý queue/executor lifecycle |
| Context đóng nhưng JVM vẫn sống | Non-daemon raw thread không dừng | jcmd, dừng executor và join có hạn |
| JVM thoát nhưng không log graceful | PID/signal sai, OOMKill, shell wrapper | Kiểm tra container status/PID1 và exit code |
| SIGTERM chỉ được shell nhận | Entrypoint không forward TERM | Exec-form ENTRYPOINT hoặc shell `exec` |
| IDE stop gây mất request | IDE có thể dùng cơ chế dừng tức thời | Thử signal thực ở terminal/staging |
| DB transaction dang dở | Interrupt/timeout, resource destroy quá sớm | Idempotency, transaction metrics, retry |
| preStop bị timeout | Hook ăn hết grace period | Rút ngắn hook, điều chỉnh ngân sách tổng |

### Vì sao không nên gọi System.exit trong controller?

Nếu public HTTP request có thể chủ động gọi `System.exit`, một client có thể ngừng toàn bộ instance, tạo vấn đề bảo mật và độ sẵn sàng. Chỉ cho dừng qua control plane đáng tin cậy, service management hoặc một API nội bộ được bảo vệ nghiêm ngặt khi thật sự cần.

### Vì sao không tăng timeout lên vô hạn?

Request hoặc job có thể bị treo do deadlock, I/O không timeout hoặc downstream không phản hồi. Infinite graceful period có thể làm rollout/auto recovery bị treo, trong khi Kubernetes vẫn có kill deadline. Nên có thời hạn theo SLO, cancellation và retry/compensation cho công việc chưa hoàn tất.

## 13. Đo shutdown và kiểm thử trước khi triển khai

Các metric quan trọng:

| Chỉ số | Mục tiêu |
| --- | --- |
| SIGTERM→process exit | Biết tổng thời gian so với Kubernetes grace |
| In-flight HTTP khi bắt đầu | Biết khối lượng cần drain |
| Request hoàn tất trước exit | Đo hiệu quả graceful |
| Request timeout, connection reset, 5xx | Phát hiện request bị cắt |
| Queue backlog/in-flight jobs | Theo dõi việc nền |
| Message retry/requeue | Đánh giá bảo toàn công việc |
| DB commit/rollback outcome | Kiểm tra tính đúng dữ liệu |
| Per-phase stop latency | Tìm phase làm shutdown chậm |
| `@PreDestroy` và shutdown-hook logs | Kiểm tra lifecycle chạy |
| SIGKILL/OOMKilled/exit code | Phân biệt dừng bình thường và cưỡng bức |

Test ít nhất các tình huống:
- Không có request: ứng dụng thoát sạch.
- Một request ngắn đang chạy: graceful có cơ hội hoàn tất.
- Request dài hơn timeout: phản ứng rõ ràng và có retry khi cần.
- Nhiều request đồng thời: không để server nhận việc mới vô hạn khi drain.
- Background tasks hoặc consumer đang chạy: có chính sách stop riêng.
- Force kill: cơ chế recovery xử lý trường hợp không có callback.
- Rolling deployment nhiều replicas: không tạo mất availability ngoài SLO.
- Môi trường CPU/memory pressure: shutdown vẫn có deadline hợp lý.

Khi benchmark, chạy nhiều lượt ở cùng JVM/Boot version, cùng web server và workload; báo cáo số đo thật, không gán trước một khoảng milliseconds cố định. `WORK_FINISHED` trong lab chỉ cho biết code đi qua một điểm, không chứng minh mọi công việc business trong hệ thống thực đã commit.

## 14. Checklist triển khai

1. Xác nhận phiên bản Spring Boot và embedded web server.
2. Biết rằng graceful là mặc định trong Spring Boot 3.5; ghi rõ `server.shutdown=graceful` nếu cần.
3. Cấu hình `spring.lifecycle.timeout-per-shutdown-phase` theo **mỗi phase**, không xem nó là process deadline.
4. Dừng intake trước khi đóng resource chung.
5. Chờ in-flight work với timeout có giới hạn và cancellation đúng.
6. Quản lý `@Async`, `@Scheduled`, message consumers và raw executors riêng.
7. Gọi callback `SmartLifecycle.stop(Runnable)` khi phase đã xử lý xong.
8. Dùng `@PreDestroy` cho resource bean-managed, không giả định nó chạy sau SIGKILL.
9. Không coi `server.shutdown=immediate` là `kill -9`.
10. Đảm bảo Java process nhận TERM, đặc biệt trong Docker/Kubernetes.
11. Tính `preStop` và mọi Spring phases vào `terminationGracePeriodSeconds`.
12. Kiểm tra readiness/EndpointSlice và cơ chế route traffic mới.
13. Đặt request timeout, retry, idempotency, checkpoint cho dữ liệu quan trọng.
14. Quan sát exit code, shutdown duration, in-flight, 5xx và broker commit outcomes.
15. Test lặp trong staging với mức tải và tín hiệu giống production.

## 15. Câu hỏi ôn tập

**1. Spring Boot 3.5 mặc định dùng graceful hay immediate?**  
Graceful với các embedded web servers được hỗ trợ.

**2. Property nào tắt chờ HTTP graceful?**  
`server.shutdown=immediate`.

**3. Nó có bỏ qua @PreDestroy giống SIGKILL không?**  
Không. Context vẫn có callback destroy nếu đóng bình thường.

**4. spring.lifecycle.timeout-per-shutdown-phase có phải global deadline không?**  
Không. Nó áp dụng theo từng phase của `SmartLifecycle`.

**5. SIGTERM khác SIGKILL thế nào?**  
TERM cho JVM cơ hội chạy hooks và cleanup; KILL cưỡng bức chấm dứt mà không có đường cleanup bình thường.

**6. SmartLifecycle.stop(Runnable callback) cần làm gì?**  
Gọi callback khi bước dừng phù hợp đã hoàn tất, để container tiếp tục lifecycle.

**7. Dừng theo phase số lớn hay nhỏ trước?**  
Phase lớn dừng trước; start theo chiều ngược lại.

**8. ApplicationReadyEvent có xác nhận mọi background job đã xong không?**  
Không. Nó là mốc startup, không tự chờ futures do ứng dụng tạo.

**9. Một request HTTP đã trả 202 nhưng job nền đang chạy được web graceful bảo vệ không?**  
Không tự động; cần queue/executor lifecycle.

**10. Vì sao health readiness có thể không trả HTTP khi shutdown?**  
Web server đang dừng chấp nhận request/kết nối mới.

**11. preStop trong Kubernetes có tiêu tốn termination grace không?**  
Có. Nó không phải phần thời gian cộng thêm miễn phí.

**12. Context đã đóng nhưng JVM vẫn chạy, cần kiểm tra gì?**  
Threads non-daemon hoặc executor chưa shutdown, không phải chỉ cấu hình web server.

**13. Để bảo toàn dữ liệu sau SIGKILL, cần gì ngoài @PreDestroy?**  
Transaction, idempotency, durable queue/checkpoint và retry/recovery.

**14. Immediate mode vẫn có một request hoàn tất thì có mâu thuẫn không?**  
Không. Tùy timing/server, một request có thể hoàn thành ngay trước hoặc trong lúc đóng.

## 16. Nguồn tài liệu chính thức

- [Spring Boot 3.5 — Graceful Shutdown](https://docs.spring.io/spring-boot/3.5/reference/web/graceful-shutdown.html): chế độ mặc định, server differences và timeout.
- [Spring Boot 3.5 — SpringApplication / Application Exit](https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html): JVM shutdown hook, `SpringApplication.exit` và `ExitCodeGenerator`.
- [Spring Boot 3.5 — Actuator Endpoints / Kubernetes Probes](https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html): readiness/liveness trong shutdown.
- [Spring Boot 3.5 — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/): timeout per phase, executor/scheduler shutdown và shutdown hook.
- [Spring Framework — Customizing the Nature of a Bean](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html): `@PreDestroy`, `DisposableBean`, `SmartLifecycle` và phase order.
- [Oracle Java 17 — Runtime API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Runtime.html): JVM exit, halt và hooks.
- [Kubernetes — Pod Lifecycle](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/): TERM/KILL, preStop và termination grace.

**Kết luận:** graceful shutdown là một **quy trình phối hợp có deadline** giữa Spring web server, context, background work và nền tảng triển khai. Chỉ khi tất cả các lớp này được thiết kế và kiểm thử cùng nhau, ứng dụng mới có cơ hội bảo vệ những request đang xử lý và duy trì đúng tính nhất quán dữ liệu. Không có một property duy nhất bảo đảm an toàn trước mọi timeout, crash hoặc SIGKILL.