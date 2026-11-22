# Giới hạn kết nối, hàng đợi và khả năng từ chối khi quá tải

## 1. Mục tiêu và tình huống

Trong **Spring Boot - web-runtime**, một ứng dụng có thể nhận request nhanh hơn tốc độ hoàn thành công việc. Khi số kết nối, thread, task chờ, kết nối database hoặc HTTP client tăng vượt khả năng phục vụ, hệ thống có thể chậm, timeout, hết bộ nhớ hoặc ngừng nhận kết nối. Chủ đề **Hiệu năng và giới hạn** yêu cầu thiết kế để **chịu tải có kiểm soát**, không chỉ tối ưu trường hợp ít người dùng.

Ví dụ một API tạo báo cáo mất hai giây mỗi request. Nếu 100 người cùng gọi, việc đưa cả 100 tác vụ vào queue vô hạn không làm report tạo nhanh hơn: người đến sau có thể chờ nhiều phút và retry khi client timeout. Một hệ thống lành mạnh có thể chọn **nhận tối đa N công việc đang chạy, cho phép M công việc chờ ngắn hạn, rồi từ chối phần vượt tải** với phản hồi rõ ràng.

Cần phân biệt bốn năng lực:

1. **Kết nối (connections):** các TCP sockets HTTP client, load balancer và Tomcat đang giữ.
2. **Xử lý đồng thời (concurrency):** request threads, worker threads, database connections, HTTP client connections.
3. **Hàng đợi (queueing):** yêu cầu chưa được xử lý đang chờ ở OS, proxy, Servlet connector, executor hoặc downstream pool.
4. **Từ chối khi bão hòa (load shedding/rejection):** request không được nhận thêm vì quota hoặc năng lực đã hết, có thể nhận HTTP 429/503, hoặc bị TCP timeout/refused khi chưa vào HTTP.

Bài tập trung vào **Spring Boot 3.3.13, embedded Tomcat 10.1, Spring MVC và Java 17+**. Những số cấu hình được chọn để phục vụ lab, **không phải ngưỡng production mặc định hay khuyến nghị chung**.

## 2. Các tầng của một request: không có một hàng đợi duy nhất

~~~text
Client / Load generator
        |
        v
TCP handshake và OS accept backlog
        |
        v
Ingress / API gateway / Load balancer (nếu có)
        |       - connection limits
        |       - per-user quotas / rate limiting
        |       - upstream timeout / retry
        v
Tomcat HTTP connector
        |       - maxConnections: số connections
        |       - maxThreads: request workers
        |       - acceptCount: yêu cầu OS listen backlog
        v
Spring Security / Spring MVC Controller
        |
        v
Application admission control
        |       - số worker tasks chạy song song
        |       - hàng đợi bounded
        |       - reject khi saturated
        v
Database (HikariCP) / External HTTP pool
        |       - active connections
        |       - pending acquire / timeouts
        v
HTTP response: 2xx / 4xx / 5xx nếu còn đường trả lời
~~~

Nếu **OS backlog đầy**, TCP client có thể gặp refused hoặc connect timeout **trước khi Spring Security hay Controller chạy**. Khi ấy ứng dụng **không thể phát HTTP 503**. Nếu request đã tới Controller và business pool đầy, ứng dụng có thể chủ động trả 503.

Đây là ranh giới quan trọng khi quan sát hệ thống: **không có 503 trong app logs không chứng minh là không bị quá tải**. Phải xem cả proxy, Tomcat, OS và downstream.

## 3. Connection không bằng HTTP request và không bằng thread

| Tài nguyên | Đơn vị | Sự khác biệt |
| --- | --- | --- |
| TCP connection | socket | Một connection keep-alive có thể xử lý nhiều HTTP requests theo thời gian |
| HTTP/1.1 request | request | Không phải mỗi request tạo TCP connection mới |
| HTTP/2 stream | stream | Một connection có thể multiplex nhiều requests đồng thời |
| Tomcat worker | thread | Phục vụ Servlet request, không đồng nghĩa với một socket |
| Servlet async request | request còn mở | Worker có thể được thả trong khi chờ CompletableFuture |
| Business executor worker | Java thread/task | Khác với Tomcat worker, có queue riêng |
| Task queue | phần việc chưa chạy | Giữ dữ liệu trong JVM RAM, cần giới hạn capacity |
| OS accept backlog | TCP connections chờ accept | Không chứa Java Runnable |
| HikariCP connection | JDBC connection | Do DB và pool giới hạn |
| Outbound HTTP pool | connection tới upstream | Có active/idle/pending requests riêng |

Ví dụ 120 connections đang mở không có nghĩa 120 requests đang chạy. Nhiều connections có thể **idle keep-alive**. Ngược lại, với HTTP/2, số requests đồng thời có thể lớn hơn số TCP connections.

CPU thấp vẫn có thể quá tải khi threads đang **đợi DB, network, queue hoặc lock**. Chỉ dựa vào CPU utilization để tăng số threads là dễ sai.

## 4. Tomcat: maxThreads, maxConnections, acceptCount

### 4.1. maxThreads: số luồng xử lý request

**server.tomcat.threads.max** giới hạn số request processing threads của Tomcat internal executor. Với request MVC đồng bộ, một worker thường bận trong lúc Controller thực thi, kể cả khi bị chặn bởi JDBC, file I/O hoặc HTTP client blocking.

Nếu các workers đều bận, nhiều connections/requests có thể chờ tới khi có thread rảnh hoặc bị gián đoạn do timeout. Tăng maxThreads không tự làm database xử lý nhiều queries hơn. Nếu connector dùng một executor được cung cấp riêng, thuộc tính thread của internal executor có thể không còn quyết định con số thực.

### 4.2. maxConnections: số TCP connections chấp nhận

**server.tomcat.max-connections** giới hạn số connections mà connector chấp nhận và xử lý ở cùng một thời điểm. Connection có thể idle, đang đọc request hoặc đang chờ xử lý. Đây **không phải giới hạn RPS**, cũng không phải số tasks trong một ExecutorService.

### 4.3. acceptCount: OS backlog, không phải Java task queue

**server.tomcat.accept-count** yêu cầu kích thước queue kết nối ở OS khi Tomcat không thể nhận thêm connections theo connector limits. **Hệ điều hành có thể không áp dụng đúng con số yêu cầu**. Khi backlog cũng đầy, client có thể nhận connect refused, timeout hoặc hành vi phụ thuộc network/OS.

Không nhầm accept-count với **queueCapacity** của ThreadPoolTaskExecutor hay ArrayBlockingQueue. Chúng thuộc **hai tầng khác nhau**.

### 4.4. Hai timeout dễ bị hiểu sai

- **server.tomcat.connection-timeout:** thời gian connector đợi request line sau khi chấp nhận kết nối; không phải deadline “Controller phải xử lý xong”.
- **server.tomcat.keep-alive-timeout:** thời gian chờ request tiếp theo trên keep-alive connection; không phải timeout xử lý business.

Một request đang chạy SQL 15 giây có thể vẫn giữ Servlet thread dù connection-timeout đặt 5 giây. Muốn giới hạn tổng thời gian cần đặt deadline ở gateway, ứng dụng, JDBC và HTTP client.

### 4.5. Mẫu cấu hình Tomcat

~~~yaml
server:
  port: 8080
  tomcat:
    threads:
      max: 24
      min-spare: 4
    max-connections: 120
    accept-count: 30
    connection-timeout: 5s
    keep-alive-timeout: 10s
~~~

Mẫu dành cho Boot 3.3/Tomcat, không dùng nguyên namespace khi server là Jetty, Undertow hay Reactor Netty. Các con số trên **chỉ minh họa**. Trong Java 21 với virtual threads được bật hoặc khi chọn executor khác, một số tham số platform-thread cần được xem xét lại; bài lab sử dụng **Java 17**.

## 5. Từ Java Executor đến hàng đợi hữu hạn

**ThreadPoolExecutor** nhận tasks theo nguyên tắc:

1. Khi số worker dưới corePoolSize, tạo worker trước.
2. Khi đã đủ core workers, ưu tiên xếp task vào queue nếu queue nhận được.
3. Nếu queue đầy, tăng worker tới maximumPoolSize khi được phép.
4. Khi số workers đã đạt max và queue đầy, gọi RejectedExecutionHandler.

Điểm bất ngờ: với **core=2, max=8, queue=100**, worker thứ ba **không nhất thiết được tạo ngay khi request thứ ba đến**. Task thứ ba có thể được xếp queue. Nếu queue rất dài, maxPoolSize lớn đôi khi không phát huy như người cấu hình tưởng.

### 5.1. Các rejection policies

| Policy | Khi saturated | Rủi ro |
| --- | --- | --- |
| AbortPolicy | Ném RejectedExecutionException | Phải catch và map thành status/domain error |
| CallerRunsPolicy | Thread nộp task sẽ chạy công việc nếu executor còn hoạt động | Nếu thread ấy là Servlet worker, có thể làm Tomcat nghẽn |
| DiscardPolicy | Bỏ task mà không báo rõ | Request có thể không bao giờ nhận kết quả |
| DiscardOldestPolicy | Loại task lâu nhất trong queue để thử nộp task mới | Mất công việc đã nhận; phá kỳ vọng thứ tự |
| Custom handler | Do app tự chọn | Cần đúng hợp đồng nghiệp vụ và observability |

Một HTTP endpoint cần phản hồi rõ nên thường dễ quản lý hơn với **bounded queue + AbortPolicy + trả 503** tại admission boundary. Không phải mọi trường hợp CallerRunsPolicy đều sai, nhưng phải hiểu ai là caller và việc chạy task trực tiếp có thể chặn thread đó bao lâu.

### 5.2. Vì sao queue vô hạn nguy hiểm?

Giả sử tải đến là 1.000 tasks/giây nhưng hệ thống chỉ hoàn thành 100 tasks/giây. Backlog tăng gần **900 tasks mỗi giây** trong khoảng quá tải kéo dài. Một queue vô hạn chỉ tích lũy latency và chiếm RAM; cuối cùng user có thể timeout rồi retry, làm backlog còn tăng thêm.

Một queue ngắn hấp thụ burst ngắn hạn; khi capacity đã hết, **từ chối sớm** thường tốt hơn nhận vô hạn rồi để cả hệ thống cùng chết vì OOM.

### 5.3. Little's Law để suy luận, không phải sizing máy móc

Trong trạng thái ổn định, **L = lambda × W** với:
- L: số requests trung bình ở trong hệ thống;
- lambda: throughput trung bình (requests/giây);
- W: thời gian request ở trong hệ thống (giây).

Ví dụ 100 requests/giây, trung bình mỗi request mất 0,2 giây, ta có khoảng **20 requests in-flight trung bình**. Đây **không phải** bằng chứng maxThreads=20 là đủ: burst, p99 latency, CPU vs I/O, queues và downstream concurrency còn ảnh hưởng rất lớn.

## 6. HTTP 503, HTTP 429 và lỗi kết nối: ai đang từ chối?

### 6.1. 503 Service Unavailable

Theo HTTP semantics, **503** phù hợp khi server tạm thời không thể phục vụ vì **overload hoặc maintenance**. Khi application admission layer vẫn có thể trả response, có thể dùng:

~~~http
HTTP/1.1 503 Service Unavailable
Retry-After: 1
Content-Type: application/json

{"status":"rejected","detail":"bounded queue is full"}
~~~

**Retry-After: 1** gợi ý client chờ khoảng 1 giây trước khi thử lại. Nó **không cam kết** capacity sẽ có ở thời điểm đó. Retry nên dùng exponential backoff có jitter, giới hạn số lần và deadline tổng.

### 6.2. 429 Too Many Requests

**429** hợp khi một user/API key/tenant đã vượt **rate limit/quota**. Một client gửi 1.000 requests/phút trong khi quota 60 requests/phút là trường hợp 429 điển hình. Không nên coi mọi lần worker pool của cả hệ thống bị đầy là lỗi rate limit của riêng user.

### 6.3. 502, 504 và network failures

- **502 Bad Gateway:** gateway/proxy nhận lỗi upstream hoặc response không hợp lệ.
- **504 Gateway Timeout:** gateway đợi upstream vượt deadline.
- **TCP refused / connect timeout:** xảy ra trước khi có HTTP response, ví dụ OS backlog đầy hoặc network policy.
- **500:** có thể do bug/exceptions chưa được map; không tự động đồng nghĩa quá tải.

Chỉ theo dõi số HTTP 503 ở application **không đủ**. Có thể một phần requests thậm chí chưa vào Servlet container và không được ghi vào application logs.

### 6.4. Retry storm và idempotency

Nếu 1.000 clients cùng nhận 503 rồi cùng retry sau đúng 1 giây, tải có thể tạo một đỉnh lớn mới. Dùng backoff/jitter và retry budget. Với POST tạo đơn/thanh toán, phải có **idempotency key hoặc logic chống xử lý trùng**; không tự retry tùy tiện vì side effect có thể đã được server thực hiện dù response lỗi.

## 7. Java 17 lab: kết quả từ chối tất định

Đây là chương trình Java độc lập, **không cần Maven hoặc Spring**. Nó tạo **2 workers và queue chỉ có 2 slots**, giữ hai workers bằng CountDownLatch, nộp thêm hai tasks vào queue rồi thử nộp task thứ năm. Vì trạng thái được giữ bằng latch nên dễ tái hiện chính xác, khác thử nghiệm dựa vào sleep không kiểm soát.

**Tệp BoundedExecutorProof.java:**

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public class BoundedExecutorProof {

    public static void main(String[] args) throws Exception {
        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                2, 2, 0L, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(2),
                new ThreadPoolExecutor.AbortPolicy()
        );

        CountDownLatch started = new CountDownLatch(2);
        CountDownLatch release = new CountDownLatch(1);

        Runnable hold = () -> {
            started.countDown();
            try {
                release.await();
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            }
        };

        try {
            pool.execute(hold);
            pool.execute(hold);

            if (!started.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Workers did not start");
            }

            pool.execute(() -> {});
            pool.execute(() -> {});

            int running = pool.getActiveCount();
            int queued = pool.getQueue().size();

            boolean rejected = false;
            try {
                pool.execute(() -> {});
            } catch (RejectedExecutionException ex) {
                rejected = true;
            }

            System.out.println("running=" + running);
            System.out.println("queued=" + queued);
            System.out.println("rejected=" + rejected);
        } finally {
            release.countDown();
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }
}
~~~

**Biên dịch và chạy:**

~~~bash
javac BoundedExecutorProof.java
java BoundedExecutorProof
~~~

**Stdout chính xác khi thực thi hoàn tất bình thường:**

~~~text
running=2
queued=2
rejected=true
~~~

**Giải thích:** main đợi started latch xác nhận hai workers đã vào hold. Vì release chưa mở, workers không thể hoàn thành. Hai tasks tiếp theo được giữ trong ArrayBlockingQueue(2). Task thứ năm không thể được nhận và AbortPolicy ném RejectedExecutionException. Khối finally mở latch và shutdown, tránh để chương trình treo.

Đây là **queue của ThreadPoolExecutor trong JVM**, không phải OS socket backlog hay Tomcat accept-count.

## 8. Spring Boot MVC lab: overload chủ động trả 503

Lab Spring Boot dùng **2 business workers + 2 queue slots**. Tomcat tiếp nhận HTTP; Controller nộp business task vào **bounded executor**, trả CompletableFuture để Spring MVC xử lý bằng Servlet async. Khi executor full, Controller trả **503 + Retry-After: 1** ngay tại admission boundary.

**Giới hạn dùng lab:** chỉ chạy localhost/staging, không áp dụng thông số cố định này cho production. Tác vụ giả lập bằng Thread.sleep, không phải một service thực có database hay upstream.

### 8.1. Cây thư mục

~~~text
overload-control-demo/
├── pom.xml
├── BoundedExecutorProof.java
└── src/main/
    ├── java/com/example/overload/OverloadApplication.java
    └── resources/application.yml
~~~

### 8.2. pom.xml

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
    <artifactId>overload-control-demo</artifactId>
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

### 8.3. application.yml

~~~yaml
server:
  port: 8080
  tomcat:
    threads:
      max: 24
      min-spare: 4
    max-connections: 120
    accept-count: 30
    connection-timeout: 5s
    keep-alive-timeout: 10s
    mbeanregistry:
      enabled: true

spring:
  mvc:
    async:
      request-timeout: 8s

management:
  endpoints:
    web:
      exposure:
        include: health,metrics
~~~

**server.tomcat.threads.max** giới hạn request workers, **max-connections** giới hạn connections theo Connector, **accept-count** là backlog mong muốn của OS. **spring.mvc.async.request-timeout** đo lifetime Servlet async response, không thay timeout business/downstream. **mbeanregistry.enabled** cho phép Tomcat metrics khi Actuator auto-config instrument.

**Bảo mật:** /actuator/metrics được expose trong lab, nhưng phải giới hạn truy cập ở production bằng network/authentication; đừng coi metrics là API công khai.

### 8.4. Java code đầy đủ

**src/main/java/com/example/overload/OverloadApplication.java:**

~~~java
package com.example.overload;

import java.util.Map;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class OverloadApplication {
    public static void main(String[] args) {
        SpringApplication.run(OverloadApplication.class, args);
    }
}

@Configuration
class WorkerConfig {
    @Bean(destroyMethod = "shutdown")
    ThreadPoolExecutor boundedWorker() {
        AtomicInteger workerNumber = new AtomicInteger();
        return new ThreadPoolExecutor(
            2, 2, 0L, TimeUnit.MILLISECONDS,
            new ArrayBlockingQueue<>(2),
            job -> new Thread(
                job,
                "business-worker-" + workerNumber.incrementAndGet()
            ),
            new ThreadPoolExecutor.AbortPolicy()
        );
    }
}

record Reply(String status, long millis, String detail) {}

@RestController
class CapacityController {
    private final ThreadPoolExecutor executor;

    CapacityController(ThreadPoolExecutor boundedWorker) {
        this.executor = boundedWorker;
    }

    @GetMapping("/api/work")
    CompletableFuture<ResponseEntity<Reply>> work(
            @RequestParam(defaultValue = "1500") long ms
    ) {
        if (ms < 0 || ms > 3000) {
            return CompletableFuture.completedFuture(
                ResponseEntity.badRequest()
                    .body(new Reply("invalid", 0, "ms must be 0..3000"))
            );
        }

        try {
            return CompletableFuture.supplyAsync(() -> {
                try {
                    Thread.sleep(ms);
                    return ResponseEntity.ok(
                        new Reply("completed", ms, "ok")
                    );
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                    return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                        .body(new Reply(
                            "interrupted", 0, "worker interrupted"
                        ));
                }
            }, executor);
        } catch (RejectedExecutionException ex) {
            return CompletableFuture.completedFuture(
                ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                    .header(HttpHeaders.RETRY_AFTER, "1")
                    .body(new Reply(
                        "rejected", 0, "bounded queue is full"
                    ))
            );
        }
    }

    @GetMapping("/api/capacity")
    Map<String, Object> capacity() {
        return Map.of(
            "active", executor.getActiveCount(),
            "queued", executor.getQueue().size(),
            "poolSize", executor.getPoolSize(),
            "maxPoolSize", executor.getMaximumPoolSize(),
            "queueRemaining", executor.getQueue().remainingCapacity(),
            "completed", executor.getCompletedTaskCount()
        );
    }
}
~~~

**Vì sao code này phân biệt được hai tầng capacity?**
- Tomcat có thể tiếp nhận HTTP requests trên tối đa 24 Servlet workers cho luồng đồng bộ; business executor là **một pool khác** với **2 workers + 2 queued tasks**.
- **CompletableFuture.supplyAsync** chuyển phép thử Thread.sleep sang business executor, không giữ request thread đợi kết quả đồng bộ theo cách gọi block() trong Controller.
- Spring MVC có hỗ trợ CompletableFuture asynchronous return. Request vẫn chiếm state/response resources và cần async dispatch khi future hoàn tất.
- **RejectedExecutionException** được ném ngay khi submit task không thể được nhận. Controller catch và trả **HTTP 503**, không giấu lỗi thành HTTP 200 hoặc 500.
- **ms ngoài 0..3000** trả HTTP 400 vì là invalid input, **không nhầm với overload**.
- Bean có **destroyMethod=shutdown** để dừng executor khi Spring context đóng.
- **GET /api/capacity** là snapshot số liệu Java executor, **không đo số TCP connections hoặc OS backlog**.

**Không suy luận rằng 2 workers + 2 queue slots có nghĩa tối đa bốn TCP connections.** Sockets có thể nhiều hơn rất nhiều; chỉ các tasks được executor nhận mới bị giới hạn ở đây.

**Cảnh báo timeout:** nếu client disconnect hoặc async request hết hạn, business task có thể vẫn đang thực thi. CompletableFuture không tự rollback transaction hay dừng mọi side effects. Để dùng production cần deadline/cancellation và idempotency policy tương ứng.

### 8.5. Chạy ứng dụng và kiểm tra

Cần **JDK 17+, Maven và cổng 8080 chưa bị chiếm**. Ở root dự án:

~~~bash
mvn test
mvn package
java -jar target/overload-control-demo-1.0.0.jar
~~~

Mở terminal khác:

~~~bash
curl -i "http://localhost:8080/api/work?ms=500"
curl -s "http://localhost:8080/api/capacity"
~~~

Với request đơn lẻ thành công, HTTP status dự kiến **200** và JSON body chứa:

~~~json
{"status":"completed","millis":500,"detail":"ok"}
~~~

Thứ tự JSON fields có thể do serializer quyết định. Request với ms=9000 trả **HTTP 400** và nội dung:

~~~json
{"status":"invalid","millis":0,"detail":"ms must be 0..3000"}
~~~

### 8.6. Burst nhỏ trên localhost

Trên Bash/Linux/macOS:

~~~bash
for i in 1 2 3 4 5 6 7 8 9 10 11 12; do
  curl -sS -o /dev/null -w "%{http_code}\n" \
    "http://localhost:8080/api/work?ms=2500" &
done
wait
~~~

**Chỉ chạy trên localhost/staging được phép**. Do chỉ có 2 business workers và 2 slots chờ, dưới burst đủ đồng thời thường thấy **một số 200 và một số 503**. Nhưng **không có đúng một bộ stdout cố định**: thứ tự TCP arrival và thời điểm tasks hoàn tất có thể khác giữa các lần. Đừng hứa chắc “4 lần 200, 8 lần 503” cho HTTP load test có race.

Để kiểm nghiệm rejection **tất định**, dùng BoundedExecutorProof của phần 7. Để quan sát HTTP, chạy nhiều lượt và tổng hợp status, latency, active workers và queued tasks.

### 8.7. Actuator và custom executor metrics

Với Actuator được thêm vào pom và Tomcat MBean registry bật:

~~~bash
curl -s http://localhost:8080/actuator/health
curl -s http://localhost:8080/actuator/metrics
curl -s http://localhost:8080/api/capacity
~~~

**/actuator/metrics** trả danh sách meters thực sự có trong runtime. Tên/nhãn phụ thuộc phiên bản và điều kiện auto-config. Tomcat metrics có prefix **tomcat.** khi instrumentation có đủ MBean registry; JVM, process và HTTP server metrics cũng có thể xuất hiện.

**Custom ThreadPoolExecutor** của demo chưa tự có đầy đủ rejection counter và queue-wait histogram chỉ vì Actuator được cài. Với production, instrument rõ **active/queued/rejected/completed/queue-wait duration** và thêm alert khi rejection tăng, pending queue cao hoặc p99 vượt SLO. /api/capacity chỉ là snapshot cho lab.

## 9. Connection cap khác business admission cap

Một request có thể bị dừng ở bất kỳ nơi nào:

~~~text
TCP client
    |
    +-- OS backlog full ----------> connect refused / timeout
    |
    v
Gateway
    +-- per-caller quota ---------> HTTP 429
    +-- upstream unavailable -----> 502 / 503 / 504
    |
    v
Tomcat
    +-- max connections / worker saturation
    |       -> delay, timeout, close; không bắt buộc HTTP 503
    |
    v
Spring MVC Controller
    +-- invalid ms ---------------> HTTP 400
    +-- bounded task pool full ---> HTTP 503 + Retry-After
    +-- accepted and completed ---> HTTP 200
~~~

**Nếu Java executor bị đầy nhưng Tomcat vẫn còn threads**, Controller có thể trả JSON 503 rõ ràng. **Nếu TCP connection không được accept**, nó không có cơ hội tạo HTTP response. Vì vậy health/metrics của application không thay thế network load balancer telemetry.

## 10. Database pool và HTTP client pool: nơi nghẽn tiếp theo

Ví dụ một ứng dụng có Tomcat 100 workers nhưng HikariCP chỉ có 10 DB connections. Nhiều requests có thể cùng chờ lấy JDBC connection, dẫn tới tail latency và timeout. Tăng Tomcat threads chỉ làm nhiều requests đứng chờ hơn nếu database là bottleneck.

Một fragment cấu hình cho ứng dụng có JDBC DataSource:

~~~yaml
spring:
  datasource:
    hikari:
      maximum-pool-size: 10
      connection-timeout: 2s
~~~

**Đây là fragment, không phải cấu hình của lab bên trên.** application.yml của lab không có database hay JDBC driver. Với HikariCP:
- maximum-pool-size là số JDBC connections pool quản lý.
- connection-timeout là thời gian một caller chờ connection từ pool trước khi bị lỗi.
- Một thread đang chờ acquire connection vẫn có thể giữ business/Servlet worker.

**Tổng nhiều replicas:** nếu có 10 instances mà mỗi HikariCP tự có tối đa 30 connections, tổng nhu cầu có thể lên tới 300 DB connections. Phải tính ngân sách theo **toàn hệ thống**, không chỉ một JVM.

Với **WebClient/Reactor Netty** hoặc một HTTP client khác, cũng có outbound pool, pending acquire queue, connect/response timeouts và retries. Tăng pending queue chỉ làm requests chờ lâu hơn nếu upstream service không có thêm capacity.

### 10.1. Deadline phải bao gồm cả queue wait

Một request chờ worker 1,5 giây, đợi DB connection 1,5 giây và chạy SQL 2 giây đã mất 5 giây **trước khi gửi response**. Nếu gateway timeout 4 giây, client có thể nhận 504 dù backend vẫn thực hiện SQL. Đặt timeout nhất quán qua **gateway → app admission → downstream acquire → execution**, thay vì chỉ giới hạn một thao tác.

## 11. Admission control, rate limiting, bulkhead và backpressure

**Admission control** quyết định có nhận công việc mới không dựa trên capacity. **Rate limiting** quyết định user/API key được gửi bao nhiêu yêu cầu trong một khoảng. **Bulkhead** tách ngân sách cho các nguồn tài nguyên khác nhau để upstream chậm không kéo sập mọi chức năng.

Một số kỹ thuật:
- **Bounded executor queue:** queue tối đa N chỗ; reject phần vượt.
- **Semaphore with tryAcquire():** giới hạn in-flight operations; không bắt người dùng phải xếp queue dài.
- **Per-tenant concurrency:** tránh noisy neighbor chiếm hết global budget.
- **Token bucket rate limiter:** hỗ trợ burst ngắn nhưng giữ tốc độ dài hạn.
- **Circuit breaker:** ngừng gọi liên tục vào upstream lỗi, không thay concurrency limit.
- **Load shedding:** tạm từ chối công việc ít ưu tiên.
- **Graceful degradation:** trả cache đã được phép hoặc rút gọn dịch vụ khi downstream yếu.
- **Autoscaling:** thêm instances khi bottleneck có thể mở rộng, không sửa được DB connection cap chung.
- **Backoff với jitter:** tránh retry storm.

Ví dụ Semaphore, **fragment trong service có permits và business method được định nghĩa**:

~~~java
if (!permits.tryAcquire()) {
    throw new CapacityExceededException();
}
try {
    return runBusinessOperation();
} finally {
    permits.release();
}
~~~

Đây là **fragment**. CapacityExceededException cần được định nghĩa và map thành HTTP 503 hoặc lỗi có ý nghĩa phù hợp. Với công việc async, permit phải được release **khi future thật sự hoàn tất**, không được release ngay sau khi nộp task.

### 11.1. 429 và 503 có thể kết hợp

Một user vượt quota 100 requests/phút có thể nhận **429** ngay cả khi server còn rảnh. Nhưng khi nhiều user hợp lệ cùng gây global saturation, service có thể trả **503** cho những requests không còn admission capacity. Kết hợp hai cơ chế giúp chống noisy neighbors và bảo vệ tài nguyên chung.

Không dùng IP address như nhận dạng quota duy nhất trong mọi ứng dụng: NAT/proxy có thể gom nhiều user hợp lệ chung một IP.

## 12. Chọn kích thước pool và queue dựa trên số liệu

Quy trình tuning:
1. Xác định target p95/p99 latency và **request deadline**.
2. Đo throughput, arrival bursts và thời gian phục vụ trung bình/đuôi.
3. Phân biệt workload **CPU-bound** với **I/O-bound**.
4. Kiểm bottleneck thật: Servlet threads, CPU, DB pool, outbound client pool, lock, disk, GC.
5. Chọn concurrency cap theo **downstream capacity**, không chỉ số lõi máy.
6. Đặt queue đủ hấp thụ burst ngắn, **không dài đến mức khách chắc chắn timeout trước khi được xử lý**.
7. Đặt chính sách reject (503/429) và retry có giới hạn.
8. Load test có kiểm soát, quan sát recovery và cập nhật config theo kết quả.

**CPU-bound:** threads quá nhiều có thể gây context switching, không làm CPU mạnh hơn. **I/O-bound:** có thể cần nhiều concurrent operations hơn, nhưng vẫn bị connection pools và memory giới hạn.

### 12.1. Sự khác biệt giữa queue time và execution time

Nếu chỉ đo business method duration, bạn có thể thấy method chạy 100ms nhưng user chờ 4 giây vì đứng queue. Nên đo các thời điểm:
- request admitted;
- task enqueued;
- task started;
- business completed;
- response completed.

Đo **queue wait**, **execution duration** và **end-to-end latency** riêng. Một queue rất dài có thể giữ 503 gần bằng không nhưng làm p99 và client timeout tệ hơn.

### 12.2. Ví dụ ngân sách thời gian

Nếu client deadline 2 giây, hệ thống có thể phân bổ minh họa 0,2 giây network, 0,2 giây queue, 1,2 giây xử lý và 0,4 giây dự phòng. Đây **không phải cấu hình áp dụng mọi API**, nhưng cho thấy yêu cầu mới không nên được nhận khi chắc chắn sẽ quá hạn.

## 13. Metrics cần đọc đúng tầng

| Tầng | Chỉ số quan trọng | Câu hỏi |
| --- | --- | --- |
| OS/TCP | connection refused, backlog overflows, open sockets | Request có bị chặn trước HTTP không? |
| Ingress | upstream errors, pending requests, 429/502/503/504 | Gateway đang giới hạn gì? |
| Tomcat | busy/total threads, connections, request latency | Servlet workers có bị nghẽn? |
| Business executor | active, queued, rejected, completed | Queue có đạt ngưỡng chưa? |
| HikariCP | active/idle/pending, connection timeout | Đang chờ JDBC connections? |
| HTTP client pool | leased, pending, connection acquire latency | Outbound calls có nghẽn? |
| JVM | heap, GC pause, thread count, CPU | Queue có gây memory pressure? |
| API | 2xx, 429, 503, p95/p99, retry rate | Từ chối đúng policy hay sập dây chuyền? |
| Business | deadline exceeded, queue wait, error reason | User có nhận kết quả đúng hạn? |

**Actuator/Micrometer** giúp đo Tomcat, JVM và HTTP server. Spring Boot 3.3 yêu cầu bật **server.tomcat.mbeanregistry.enabled=true** để tự động instrument Tomcat MBeans. Custom executor có thể cần register meters rõ ràng cho rejected counts và queue wait.

Tránh gắn raw user IDs, bearer tokens hoặc request IDs vào metrics labels vì tăng cardinality/lộ dữ liệu. Đừng expose diagnostics công khai trong production.

## 14. Đọc đúng hiện tượng khi test overload

- **Smoke test:** một request hợp lệ trả 200.
- **Burst test:** một đợt request cùng lúc để quan sát queue/rejection.
- **Load test:** tăng từ từ RPS và xem throughput/latency.
- **Stress test:** vượt năng lực để kiểm fail-fast, không OOM.
- **Soak test:** tải duy trì để tìm leak và queue growth.
- **Recovery test:** giảm tải, xem p99/queues có về bình thường không.
- **Dependency fault test:** làm DB/upstream chậm để xem bulkhead/retry.

Chỉ test hệ thống được phép, kiểm thời gian/concurrency trước. Một HTTP burst sẽ có yếu tố scheduling nên **không hứa số lượng 200/503 chính xác**. Chương trình Java latch proof lại tái hiện rejection tất định.

**Đạt yêu cầu khi quá tải** không có nghĩa 100% requests thành công. Một hệ thống tốt có thể reject một phần sớm, giữ queue/heap bounded, phục vụ phần còn lại trong deadline và hồi phục nhanh khi giảm tải.

## 15. Những sai lầm thường gặp

| Lỗi hiểu | Vì sao sai | Cách sửa |
| --- | --- | --- |
| maxConnections=100 nghĩa 100 RPS | Connections không phải requests/giây | Đo throughput và service time |
| acceptCount là Java task queue | Đó là OS socket backlog | Kiểm queue của executor riêng |
| Tăng maxThreads sẽ giải quyết DB timeout | DB pool/downstream có giới hạn khác | Đo HikariCP và DB budget |
| Không có 503 tức không overload | TCP có thể refused/timeout trước Controller | Xem proxy/OS/Tomcat |
| CPU thấp tức chưa bão hòa | Workers có thể đang block I/O | Xem blocked threads và pool waits |
| Queue vô hạn giúp không mất request | Latency/RAM tăng và client retry | Bounded queue, load shedding |
| CallerRunsPolicy luôn an toàn | Caller có thể là Tomcat thread | Xác định thread, cân nhắc AbortPolicy |
| DiscardPolicy không có lỗi | Nó có thể nuốt task | Không dùng nếu task phải trả kết quả |
| Retry-After 1 giây là cam kết | Capacity biến động | Retry budget, jitter |
| Servlet async làm JDBC non-blocking | DB vẫn cần threads/connections | Tách pool và giới hạn concurrency |
| HTTP/2 một connection là một request | HTTP/2 multiplex streams | Đo concurrency thực |
| Actuator có sẵn mọi executor metrics | Custom pool có thể cần instrument | Đăng ký counters/gauges |
| Cứ thêm replicas là hết nghẽn | DB/upstream có thể bị chia sẻ và cạn | Capacity budgeting toàn cụm |

## 16. Câu hỏi kiểm tra kiến thức

**1.** Tomcat maxThreads khác maxConnections thế nào?  
**Đáp án:** maxThreads giới hạn request processing threads; maxConnections giới hạn connections được connector nhận/xử lý. Không cùng đơn vị.

**2.** acceptCount=30 có nghĩa có đúng 30 Runnable chờ trong Java không?  
**Đáp án:** Không, đó là OS accept backlog mong muốn và còn phụ thuộc OS.

**3.** Vì sao một TCP connection có thể phục vụ nhiều HTTP requests?  
**Đáp án:** Keep-alive reuse và HTTP/2 multiplexing tùy protocol.

**4.** Trong Java demo 2 workers + queue 2, tại sao task thứ 5 bị reject?  
**Đáp án:** Hai workers đang bị latch giữ, hai slots queue đã đầy, AbortPolicy ném RejectedExecutionException.

**5.** Tại sao maxPoolSize=8 với core=2 và queue lớn không nhất thiết tạo worker thứ 3 ngay?  
**Đáp án:** ThreadPoolExecutor ưu tiên queue sau khi core threads có mặt, chỉ tăng tới max khi queue không nhận task.

**6.** Khi OS backlog đầy, client có luôn nhận HTTP 503 không?  
**Đáp án:** Không; có thể connect refused hoặc timeout trước khi có HTTP request/response.

**7.** Global business executor đầy nên chọn 429 hay 503?  
**Đáp án:** Thường 503 cho overload của service; 429 dành cho rate limit/quota của caller.

**8.** Vì sao CPU 15% vẫn có thể p99 rất cao?  
**Đáp án:** Threads đợi DB connection, lock, network, queue hoặc downstream thay vì chạy CPU.

**9.** CallerRunsPolicy tác động gì nếu caller là Servlet worker?  
**Đáp án:** Servlet worker tự thực thi task, có thể bận và làm Tomcat nghẽn.

**10.** Servlet Controller trả CompletableFuture có giải quyết database bottleneck không?  
**Đáp án:** Không. Nó cho phép Servlet async nhưng business workers và JDBC connections vẫn hữu hạn.

**11.** Vì sao retry 503 ngay lập tức nhiều lần có thể hại?  
**Đáp án:** Tạo retry storm, tăng tải đang quá mức; cần backoff, jitter, retry budget.

**12.** Nhìn metric nào để biết queue đang bão hòa?  
**Đáp án:** Active workers, queue depth/capacity, rejected counts, queue wait, total latency.

**13.** Khi giảm tải, dấu hiệu phục hồi tốt là gì?  
**Đáp án:** Queue giảm, p95/p99 hồi phục, rejection rate giảm, memory và downstream pending về mức bình thường.

**14.** HTTP/2 làm capacity planning dễ nhầm chỗ nào?  
**Đáp án:** Nhiều HTTP streams/request cùng nằm trên một TCP connection; connection count không đo request concurrency.

**15.** Khi DB pool ở mức 10 nhưng Tomcat threads=100, tăng thêm Tomcat threads có chắc giải quyết timeout không?  
**Đáp án:** Không, có thể làm nhiều requests đợi DB connections hơn.

## 17. Checklist trước triển khai

- [ ] Phân biệt OS backlog, Tomcat threads/connections, app queue và downstream pools.
- [ ] Có bounded concurrency/queue phù hợp capacity và SLO.
- [ ] Không dùng hàng đợi vô hạn khi không kiểm soát thời gian chờ.
- [ ] Catch/map rõ rejection; phân biệt 503 với 429 và lỗi hệ thống khác.
- [ ] Retry có exponential backoff/jitter, tổng deadline và idempotency policy.
- [ ] Đặt connection/response/queue/DB timeouts theo ngân sách tổng request.
- [ ] Có bulkhead cho upstream quan trọng, quota công bằng per tenant khi cần.
- [ ] Quan sát rejected counts, active workers, queue depth và queue wait.
- [ ] Theo dõi refused/timeout ở OS/proxy, không chỉ 503 của ứng dụng.
- [ ] Bảo vệ Actuator metrics và không log bí mật.
- [ ] Thử burst, stress, recovery trong môi trường được phép.
- [ ] Tính capacity theo toàn bộ replicas, DB và upstream shared quotas.

## 18. Kết luận

**Giới hạn kết nối, giới hạn request workers và giới hạn hàng đợi xử lý là các lớp độc lập.** Tomcat có thể giữ nhiều connections nhưng chỉ dùng một số Servlet threads; OS có backlog; ứng dụng còn có executor queue; HikariCP và HTTP clients lại có pools riêng. Tăng một giới hạn không đảm bảo năng lực xử lý tăng, thậm chí có thể làm thời gian chờ và bộ nhớ xấu hơn.

Một web-runtime ổn định cần **admission control, bounded queue, timeout đồng bộ, khả năng từ chối có chủ đích, retry có giới hạn và giám sát đúng tầng**. Khi hết khả năng xử lý, trả 503 sớm (nếu request đã tới application) thường tốt hơn nhận mọi tác vụ rồi để chúng timeout hàng loạt.

## Tài liệu tham khảo chính thức

- Spring Boot 3.3 — Tomcat properties: https://docs.spring.io/spring-boot/3.3/appendix/application-properties/
- Apache Tomcat 10.1 — HTTP Connector, maxThreads, maxConnections, acceptCount: https://tomcat.apache.org/tomcat-10.1-doc/config/http.html
- Oracle Java 17 — ThreadPoolExecutor and rejection: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html
- Oracle Java 17 — AbortPolicy: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.AbortPolicy.html
- Spring Framework — Async Requests in MVC: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-async.html
- Spring Boot 3.3 — Actuator Metrics: https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html
- RFC 9110 — 503 Service Unavailable, Retry-After: https://www.rfc-editor.org/rfc/rfc9110.html
- RFC 6585 — 429 Too Many Requests: https://www.rfc-editor.org/rfc/rfc6585#section-4
