# Mô phỏng database lỗi, HTTP chậm và tài nguyên cạn để thực hành chẩn đoán

## 1. Mục tiêu: đi từ triệu chứng đến bằng chứng

Một API trả lỗi hoặc chạy chậm chưa cho biết lỗi nằm ở đâu. Cùng một phản hồi 503 có thể xuất hiện khi database ngừng hoạt động hoặc khi database vẫn khỏe nhưng ứng dụng không mượn được kết nối. Tương tự, CPU thấp không có nghĩa ứng dụng còn khả năng phục vụ: tất cả luồng xử lý có thể đang chờ I/O.

Trong bài thực hành thuộc phần **Thực hành tổng hợp** của Spring Boot Actuator, ta chủ động tạo từng sự cố, quan sát rồi khôi phục. Đích đến là giải thích được **tài nguyên nào đang bị giữ, yêu cầu đang chờ ở đâu và bằng chứng nào bác bỏ giả thuyết khác**.

Bốn khái niệm cần phân biệt:

- **Triệu chứng:** mã HTTP, độ trễ và lỗi người dùng nhìn thấy.
- **Tình trạng sức khỏe (health):** kết quả các phép kiểm tra tại thời điểm gọi endpoint; không phải bản ghi mọi lỗi của ứng dụng.
- **Số liệu vận hành (metrics):** số lượng, thời gian, mức sử dụng và hàng chờ; phải đọc cùng thời điểm và nhãn (tag).
- **Bằng chứng thực thi:** log và bản chụp luồng (thread dump), giúp biết yêu cầu đang làm gì khi số liệu thay đổi.

Liveness trả lời tiến trình có đang ở trạng thái sống hợp lệ không. Readiness trả lời ứng dụng có sẵn sàng nhận lưu lượng theo chính sách đã cấu hình không. Database hỏng không tự biến liveness thành DOWN; đưa phụ thuộc dùng chung vào liveness có thể khiến nhiều bản sao khởi động lại mà không sửa được phụ thuộc đó.

Bài này dùng một ứng dụng Servlet, một PostgreSQL và một HTTP server giả lập chạy riêng. Tình huống cạn tài nguyên gồm **hết kết nối trong HikariCP** và **bão hòa luồng Tomcat**. Đây là các dạng cạn năng lực phục vụ dù bộ nhớ và CPU chưa đầy.

## 2. Mô hình và điều kiện thực hành

Đường đi của ba loại yêu cầu:

1. `/lab/db` → Tomcat → mượn kết nối Hikari → PostgreSQL.
2. `/lab/remote` → Tomcat → RestClient → HTTP server giả lập ở cổng 9090.
3. `/lab/sleep` → Tomcat → giữ luồng xử lý trong một khoảng thời gian hữu hạn.

Actuator chạy ở cổng quản trị 8081; API chạy ở 8080. Cổng riêng giúp tiếp tục lấy bằng chứng khi luồng xử lý API bị giữ. Hai cổng vẫn dùng chung JVM, CPU, bộ nhớ và DataSource; cổng quản trị không phải hệ thống giám sát độc lập và không cứu được JVM đã chết.

Chuẩn bị JDK 21, Gradle 8.5, Docker Compose, Python 3 và curl. Dự án mẫu ghim Spring Boot **3.3.0** để có mốc API cụ thể thuộc nhánh 3.3.x; đây là mốc của bài thực hành, không phải tuyên bố về phiên bản mới nhất. Lần dựng đầu cần tải được plugin và dependency. Mọi địa chỉ dưới đây đều là loopback và dùng tài khoản database dành riêng cho lab.

Tạo một thư mục thực hành riêng. Không chép endpoint gây lỗi vào dịch vụ thật. Chạy lần lượt từng kịch bản và khôi phục hoàn toàn trước khi sang kịch bản tiếp theo. Ta dừng đúng database của lab, không dừng Docker toàn máy; không tạo vòng lặp cấp phát bộ nhớ vô hạn hoặc làm đầy ổ đĩa.

Cấu trúc tệp:

```text
actuator-diagnosis-lab/
├── settings.gradle
├── build.gradle
├── compose.yml
├── SlowUpstream.java
├── load.py
└── src/main/
    ├── java/lab/LabApplication.java
    └── resources/application.yml
```

Các lệnh `curl` dùng được trong terminal có curl. Trên Windows PowerShell, dùng `curl.exe` để tránh alias khác nghĩa. Những lệnh `javac`, `java`, `gradle` bên dưới phải trỏ tới bộ công cụ đã nêu. Nếu đã có Gradle wrapper 8.5, dùng `./gradlew` hoặc `.\gradlew.bat` thay `gradle`.

## 3. Dựng môi trường tối thiểu

### 3.1. Cấu hình build và database

Tệp `settings.gradle`:

```groovy
rootProject.name = 'actuator-diagnosis-lab'
```

Tệp `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
    id 'io.spring.dependency-management' version '1.1.5'
}

group = 'lab'
version = '1.0.0'

java {
    toolchain { languageVersion = JavaLanguageVersion.of(21) }
}

repositories { mavenCentral() }

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'org.postgresql:postgresql'
}
```

Starter JDBC cung cấp JdbcTemplate, DataSource và HikariCP. Starter Actuator cung cấp health và metrics; không cần Prometheus cho bài này vì ta đọc trực tiếp endpoint `/actuator/metrics`.

Tệp `compose.yml`:

```yaml
services:
  db:
    image: postgres:16
    ports:
      - "127.0.0.1:15432:5432"
    environment:
      POSTGRES_DB: lab
      POSTGRES_USER: lab
      POSTGRES_PASSWORD: lab
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U lab -d lab"]
      interval: 2s
      timeout: 2s
      retries: 20
```

PostgreSQL bên trong container dùng cổng 5432; ứng dụng trên máy chủ kết nối qua **15432**. Đừng sửa URL ứng dụng thành cổng container nếu ứng dụng vẫn chạy trên máy chủ.

### 3.2. Cấu hình Actuator và giới hạn tài nguyên

Tệp `src/main/resources/application.yml`:

```yaml
server:
  address: 127.0.0.1
  port: 8080
  tomcat:
    threads:
      max: 8
      min-spare: 2
    mbeanregistry:
      enabled: true

spring:
  application:
    name: actuator-diagnosis-lab
  threads:
    virtual:
      enabled: false
  datasource:
    url: jdbc:postgresql://127.0.0.1:15432/lab?connectTimeout=2&socketTimeout=3
    username: lab
    password: lab
    hikari:
      pool-name: lab-pool
      maximum-pool-size: 3
      minimum-idle: 1
      connection-timeout: 3000
      validation-timeout: 1000

management:
  server:
    address: 127.0.0.1
    port: 8081
  endpoints:
    web:
      exposure:
        include: health,metrics,threaddump
  endpoint:
    health:
      show-details: always
      probes:
        enabled: true
      group:
        liveness:
          include: livenessState
        readiness:
          include: readinessState,db
```

Các lựa chọn quyết định cách đọc kết quả:

- Hikari chỉ có **3** kết nối. `connection-timeout=3000` là thời gian tối đa chờ mượn kết nối từ pool, không phải timeout của một câu SQL.
- Tham số JDBC `connectTimeout` và `socketTimeout` của PostgreSQL dùng **giây** trong URL này. Chúng kiểm soát các giai đoạn khác với thời gian chờ pool.
- Tomcat API có tối đa **8** luồng xử lý. Virtual threads bị tắt để thí nghiệm giữ luồng có ý nghĩa rõ ràng.
- Readiness gồm `readinessState` và `db`; liveness chỉ gồm `livenessState`. Đây là chính sách có chủ ý của lab. Boot không mặc định bắt mọi phụ thuộc vào readiness.
- `mbeanregistry.enabled=true` hỗ trợ lấy số liệu Tomcat qua MBean. Khi lọc metrics phải xem nhãn connector thực tế vì có hai cổng.
- Chỉ mở `health`, `metrics`, `threaddump`. `show-details=always` và việc không cấu hình xác thực chỉ phù hợp môi trường lab đã giới hạn loopback; không dùng nguyên cấu hình này làm chính sách public.

### 3.3. Ứng dụng Spring Boot hoàn chỉnh

Tệp `src/main/java/lab/LabApplication.java`:

```java
package lab;

import java.net.http.HttpClient;
import java.sql.Connection;
import java.sql.SQLException;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;
import javax.sql.DataSource;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.dao.DataAccessException;
import org.springframework.http.ResponseEntity;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;

@SpringBootApplication
public class LabApplication {
    private static final Logger LOG = LoggerFactory.getLogger(LabApplication.class);

    public static void main(String[] args) {
        SpringApplication.run(LabApplication.class, args);
    }

    @Bean
    RestClient upstreamClient(RestClient.Builder builder) {
        HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofMillis(500)).build();
        JdkClientHttpRequestFactory factory = new JdkClientHttpRequestFactory(client);
        factory.setReadTimeout(Duration.ofMillis(1000));
        return builder.baseUrl("http://127.0.0.1:9090")
                .requestFactory(factory).build();
    }

    @Bean(destroyMethod = "close")
    PoolHolder poolHolder(DataSource dataSource) {
        return new PoolHolder(dataSource);
    }

    static final class PoolHolder implements AutoCloseable {
        private final DataSource dataSource;
        private final List<Connection> held = new ArrayList<>();
        private final ScheduledExecutorService timer =
                Executors.newSingleThreadScheduledExecutor(task -> {
                    Thread thread = new Thread(task, "pool-auto-release");
                    thread.setDaemon(true);
                    return thread;
                });
        private long generation;

        PoolHolder(DataSource dataSource) {
            this.dataSource = dataSource;
        }

        synchronized int hold(int seconds) throws SQLException {
            if (seconds < 1 || seconds > 30) {
                throw new IllegalArgumentException("seconds must be in 1..30");
            }
            if (!held.isEmpty()) {
                throw new IllegalStateException("pool is already held");
            }
            long current = ++generation;
            try {
                for (int i = 0; i < 3; i++) {
                    held.add(dataSource.getConnection());
                }
                timer.schedule(() -> releaseIfCurrent(current), seconds, TimeUnit.SECONDS);
                return held.size();
            } catch (SQLException ex) {
                closeHeld();
                throw ex;
            }
        }

        private synchronized void releaseIfCurrent(long expected) {
            if (generation == expected) {
                release();
            }
        }

        synchronized int release() {
            generation++;
            return closeHeld();
        }

        private int closeHeld() {
            int count = held.size();
            for (Connection connection : held) {
                try {
                    connection.close();
                } catch (SQLException ex) {
                    LOG.warn("Cannot return a held connection", ex);
                }
            }
            held.clear();
            return count;
        }

        @Override
        public void close() {
            timer.shutdownNow();
            release();
        }
    }

    @RestController
    @RequestMapping("/lab")
    static class LabController {
        private final JdbcTemplate jdbc;
        private final RestClient upstream;
        private final PoolHolder holder;

        LabController(JdbcTemplate jdbc, RestClient upstream, PoolHolder holder) {
            this.jdbc = jdbc;
            this.upstream = upstream;
            this.holder = holder;
        }

        @GetMapping("/db")
        String db() {
            Integer result = jdbc.queryForObject("SELECT 1", Integer.class);
            return "db=" + result + "\n";
        }

        @GetMapping("/remote")
        ResponseEntity<String> remote(@RequestParam(name = "delayMs", defaultValue = "0") int delayMs) {
            if (delayMs < 0 || delayMs > 5000) {
                throw new IllegalArgumentException("delayMs must be in 0..5000");
            }
            try {
                String body = upstream.get().uri("/work?delayMs={delay}", delayMs)
                        .retrieve().body(String.class);
                return ResponseEntity.ok(body);
            } catch (ResourceAccessException ex) {
                LOG.warn("Upstream I/O failed", ex);
                return ResponseEntity.status(504).body("remote-io-failed\n");
            } catch (RestClientException ex) {
                LOG.warn("Upstream request failed", ex);
                return ResponseEntity.status(502).body("remote-call-failed\n");
            }
        }

        @PostMapping("/pool/hold")
        String hold(@RequestParam(name = "seconds", defaultValue = "20") int seconds) throws SQLException {
            return "held=" + holder.hold(seconds) + "\n";
        }

        @PostMapping("/pool/release")
        String release() {
            return "released=" + holder.release() + "\n";
        }

        @GetMapping("/sleep")
        String sleep(@RequestParam(name = "ms", defaultValue = "8000") int ms)
                throws InterruptedException {
            if (ms < 0 || ms > 10000) {
                throw new IllegalArgumentException("ms must be in 0..10000");
            }
            Thread.sleep(ms);
            return "sleptMs=" + ms + "\n";
        }

        @ExceptionHandler({DataAccessException.class, SQLException.class})
        ResponseEntity<String> databaseError(Exception ex) {
            LOG.warn("Database request failed", ex);
            return ResponseEntity.status(503).body("db-unavailable\n");
        }

        @ExceptionHandler(IllegalArgumentException.class)
        ResponseEntity<String> badInput(IllegalArgumentException ex) {
            return ResponseEntity.badRequest().body(ex.getMessage() + "\n");
        }

        @ExceptionHandler(IllegalStateException.class)
        ResponseEntity<String> conflict(IllegalStateException ex) {
            return ResponseEntity.status(409).body(ex.getMessage() + "\n");
        }
    }
}
```

Điểm cần hiểu trong chương trình:

1. `RestClient.Builder` được Spring Boot cung cấp nên vẫn đi qua cơ chế cấu hình quan sát của Boot. Tự gọi `RestClient.create()` có thể bỏ qua phần cấu hình đó.
2. HTTP client dùng connect timeout 500 ms và read timeout 1000 ms. Thời gian đo ngoài ứng dụng còn có chi phí xử lý, xếp hàng và lập lịch; không yêu cầu đồng hồ phải dừng đúng 1,000 giây.
3. `PoolHolder` mượn đủ ba kết nối rồi **cố ý không trả ngay**, mô phỏng lỗi giữ tài nguyên. Sau tối đa 30 giây, bộ định thời trả kết nối; endpoint release cho phép trả sớm. Bộ đếm `generation` ngăn tác vụ giải phóng của lượt cũ đóng kết nối của lượt mới.
4. Database lỗi và timeout mượn pool cùng được ánh xạ thành 503 trong API mẫu. I/O tới HTTP server giả lập được ánh xạ thành 504; lỗi RestClient khác thành 502. Đây là quy ước của mã lab, không phải mọi ứng dụng Spring Boot tự trả như vậy. Một ứng dụng thật nên phân loại lỗi kết nối, timeout và lỗi HTTP chính xác hơn.
5. Các tham số gây tải đều có giới hạn. Giữ kết nối không chạy câu SQL nặng: PostgreSQL có thể vẫn hoạt động bình thường trong lúc ứng dụng hết kết nối để cấp cho yêu cầu mới.

### 3.4. HTTP server giả lập độc lập

Tệp `SlowUpstream.java` sau đây dùng module `jdk.httpserver` có trong JDK. Nó chạy **ngoài** ứng dụng để độ trễ của phụ thuộc không bị lẫn với hàng chờ Tomcat của chính ứng dụng.

```java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class SlowUpstream {
    public static void main(String[] args) throws IOException {
        HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", 9090), 0);
        ExecutorService workers = Executors.newFixedThreadPool(8);
        server.setExecutor(workers);
        server.createContext("/work", exchange -> {
            try {
                String query = exchange.getRequestURI().getRawQuery();
                int delay = query == null ? 0 : Integer.parseInt(query.replace("delayMs=", ""));
                if (delay < 0 || delay > 5000) {
                    throw new IllegalArgumentException();
                }
                Thread.sleep(delay);
                reply(exchange, 200, "upstream-ok\n");
            } catch (IllegalArgumentException ex) {
                reply(exchange, 400, "invalid-delay\n");
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                reply(exchange, 503, "interrupted\n");
            } finally {
                exchange.close();
            }
        });
        Runtime.getRuntime().addShutdownHook(new Thread(() -> {
            server.stop(0);
            workers.shutdownNow();
        }));
        server.start();
        System.out.println("upstream=http://127.0.0.1:9090/work");
    }

    private static void reply(HttpExchange exchange, int status, String text)
            throws IOException {
        byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
        exchange.sendResponseHeaders(status, bytes.length);
        exchange.getResponseBody().write(bytes);
    }
}
```

Server chỉ dành cho đường dẫn và tham số của lab. Khi client hết thời gian chờ trước, server có thể vẫn ngủ rồi gặp IOException lúc ghi phản hồi vào kết nối đã đóng. Timeout của client không bảo đảm công việc phía server đã bị hủy.

### 3.5. Công cụ phát một đợt yêu cầu hữu hạn

Tệp `load.py` tạo đúng số yêu cầu đã chọn, không phát tải vô hạn. Nó đọc hết phản hồi để phép đo bao gồm việc nhận body; dùng đồng hồ đơn điệu để đo thời gian. Giới hạn 16 yêu cầu đồng thời tránh vô tình tạo lượng tải lớn do nhập nhầm.

```python
import collections
import concurrent.futures
import sys
import threading
import time
import urllib.error
import urllib.request

route = sys.argv[1] if len(sys.argv) > 1 else "/lab/db"
workers = int(sys.argv[2]) if len(sys.argv) > 2 else 8
if not 1 <= workers <= 16:
    raise SystemExit("workers must be in 1..16")
barrier = threading.Barrier(workers)

def call(_):
    barrier.wait()
    start = time.perf_counter()
    try:
        with urllib.request.urlopen("http://127.0.0.1:8080" + route, timeout=25) as response:
            response.read()
            status = response.status
    except urllib.error.HTTPError as error:
        status = error.code
        error.close()
    except (urllib.error.URLError, TimeoutError):
        status = "transport-error"
    return status, round(time.perf_counter() - start, 3)

with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
    results = list(executor.map(call, range(workers)))
print("statuses:", dict(collections.Counter(status for status, _ in results)))
print("seconds:", sorted(duration for _, duration in results))
```

Nếu kết quả có `transport-error`, đó là lỗi phía công cụ phát tải hoặc lỗi kết nối, không phải mã HTTP do server trả. Khi đó cần đọc log của cả client lẫn server trước khi kết luận.

## 4. Khởi động và ghi đường cơ sở

### 4.1. Chạy các tiến trình

Trong thư mục chứa `compose.yml`, khởi động và chờ database sẵn sàng:

```shell
docker compose up -d --wait db
```

Terminal thứ nhất biên dịch và chạy HTTP server giả lập:

```shell
javac --release 21 --add-modules jdk.httpserver SlowUpstream.java
java --add-modules jdk.httpserver SlowUpstream
```

Dòng stdout của chương trình giả lập khi khởi động thành công:

```text
upstream=http://127.0.0.1:9090/work
```

Giữ terminal đó chạy. Terminal thứ hai chạy ứng dụng Spring Boot:

```shell
gradle bootRun
```

Chờ ứng dụng khởi động xong trước khi gọi API. Nếu cổng đã bị chiếm hoặc database chưa sẵn sàng, sửa nguyên nhân đó trước; không lấy trạng thái khởi động lỗi làm đường cơ sở cho thí nghiệm.

### 4.2. Xác nhận cả hai nhánh hoạt động bình thường

```shell
curl -sS http://127.0.0.1:8080/lab/db
curl -sS "http://127.0.0.1:8080/lab/remote?delayMs=0"
curl -sS -i http://127.0.0.1:8081/actuator/health/liveness
curl -sS -i http://127.0.0.1:8081/actuator/health/readiness
```

Hai lệnh đầu lần lượt in đúng body sau nếu mọi phụ thuộc hoạt động:

```text
db=1
upstream-ok
```

Hai health group phải trả HTTP 200 và có `status` cấp ngoài cùng là `UP`. JSON thực tế có thêm component/details; không cần giống từng byte với một mẫu JSON cố định. Chạy `/lab/db` trước cũng giúp khởi tạo DataSource và đăng ký các metrics gắn với pool.

### 4.3. Chụp các số liệu cần so sánh

```shell
curl -sS http://127.0.0.1:8081/actuator/metrics
curl -sS "http://127.0.0.1:8081/actuator/metrics/hikaricp.connections.max?tag=pool:lab-pool"
curl -sS "http://127.0.0.1:8081/actuator/metrics/hikaricp.connections.active?tag=pool:lab-pool"
curl -sS "http://127.0.0.1:8081/actuator/metrics/hikaricp.connections.idle?tag=pool:lab-pool"
curl -sS "http://127.0.0.1:8081/actuator/metrics/hikaricp.connections.pending?tag=pool:lab-pool"
curl -sS "http://127.0.0.1:8081/actuator/metrics/http.server.requests?tag=uri:/lab/db"
curl -sS http://127.0.0.1:8081/actuator/metrics/http.client.requests
curl -sS http://127.0.0.1:8081/actuator/metrics/tomcat.threads.busy
```

Xem `measurements` và `availableTags` trong JSON. Với pool `lab-pool`, giới hạn là 3; khi không có yêu cầu đang thực thi, active và pending nên về 0. Idle có thể nhỏ hơn 3 vì minimum-idle chỉ là 1. Một health probe đang chạy cũng có thể tạm mượn kết nối.

Metrics HTTP chỉ xuất hiện sau khi có hoạt động tương ứng. Nếu một tên trả 404, kiểm tra danh sách `names`, khởi tạo đúng hoạt động rồi kiểm tra lại; 404 không có nghĩa giá trị bằng 0. Không tự đổi sang tên Prometheus có dấu gạch dưới: tên đọc tại endpoint này là tên Micrometer có dấu chấm.

Với timer `http.server.requests`, đọc chênh lệch COUNT và TOTAL_TIME giữa hai lần lấy mẫu cùng nhãn. Thời gian trung bình của các yêu cầu mới hoàn tất là `ΔTOTAL_TIME / ΔCOUNT` khi `ΔCOUNT > 0`. Đọc `baseUnit` để xác nhận đơn vị. Không suy ra p95 từ trung bình hoặc MAX; bài này chưa cấu hình phân phối percentile/histogram. MAX thường phản ánh cửa sổ thời gian của timer, không phải cực đại bất biến từ lúc tiến trình khởi động.

Các timer này chủ yếu phản ánh yêu cầu đã hoàn tất. Khi yêu cầu đang treo, cần xem pending, luồng đang bận và thread dump thay vì chỉ chờ COUNT tăng. Độ trễ client đo còn có thể bao gồm thời gian chờ trước khi servlet bắt đầu xử lý mà server timer không thể hiện đầy đủ.

Đối với metrics Tomcat, đọc nhãn `name` thực tế rồi lọc connector API 8080 nếu dữ liệu có phân tách connector. Không lấy tổng cả cổng 8080 và 8081 để khẳng định đã dùng hết 8 luồng API. Một yêu cầu lấy metrics cũng có thể làm cổng quản trị có thêm một luồng bận.

Ghi thời điểm, số liệu ban đầu và mã HTTP vào sổ quan sát riêng. Metrics dạng counter/timer không tự về 0 khi hết sự cố; chỉ gauge như active/pending có thể giảm về mức ban đầu.

## 5. Kịch bản A — Database ngừng hoạt động

### 5.1. Tạo lỗi phụ thuộc thực sự

Chỉ dừng service database của thư mục lab:

```shell
docker compose stop db
curl -sS -i http://127.0.0.1:8080/lab/db
curl -sS -i http://127.0.0.1:8081/actuator/health/readiness
curl -sS -i http://127.0.0.1:8081/actuator/health/liveness
```

Khi lỗi đã được phát hiện, `/lab/db` trả 503 với body:

```text
db-unavailable
```

Readiness chuyển DOWN/503 vì group có kiểm tra `db`. Liveness vẫn UP/200 nếu tiến trình và trạng thái sống chưa có vấn đề khác. Thời gian chờ có thể kéo dài qua các giai đoạn phát hiện kết nối hỏng, mượn pool và I/O; không cộng các timeout rồi coi đó là thời gian cố định cho mọi lần gọi.

Nếu vừa dừng database mà lần đọc đầu chưa phản ánh như dự đoán, kiểm tra container đã dừng hẳn và quan sát lại trong khoảng hữu hạn. Không kết luận từ một ảnh chụp đúng lúc trạng thái đang chuyển tiếp.

### 5.2. Thu thập và giải thích bằng chứng

1. Đối chiếu lỗi trong log ứng dụng: tìm chuỗi nguyên nhân JDBC phía dưới lỗi DataAccessException hoặc SQLException, chẳng hạn kết nối bị từ chối/đóng. Thông điệp chính xác phụ thuộc driver và thời điểm.
2. Đọc chi tiết component `db` của health. `DOWN` cho biết phép kiểm tra thất bại; phần nguyên nhân và log mới giúp phân biệt mất database với hết pool.
3. Chụp active, idle, pending và số liệu yêu cầu 503. Giá trị pool khi database dừng có thể biến động do Hikari loại bỏ kết nối hỏng và thử kết nối lại. Không đặt quy tắc máy móc rằng database down luôn làm active đạt 3.
4. Gọi `/lab/remote?delayMs=0`. Nếu nhánh HTTP vẫn thành công thì sự cố đang khu trú ở nhánh database, dù readiness toàn ứng dụng hiện DOWN theo chính sách lab.

Readiness là tín hiệu cho nơi điều phối lưu lượng; trong lab không có bộ điều phối tự động chặn cổng 8080. Vì vậy, client vẫn gọi trực tiếp API ngay cả khi readiness DOWN.

### 5.3. Khôi phục và nghiệm thu

```shell
docker compose up -d --wait db
curl -sS -i http://127.0.0.1:8080/lab/db
curl -sS -i http://127.0.0.1:8081/actuator/health/readiness
```

Chờ Hikari tạo lại kết nối nếu cần, rồi xác nhận database API trở lại 200 với `db=1` và readiness UP. Giới hạn thời gian chờ theo môi trường, ví dụ 60 giây; nếu chưa phục hồi thì đọc log và trạng thái database thay vì khởi động lại ứng dụng ngay. Việc phục hồi không cần restart ứng dụng là một kết quả đáng kiểm tra của thí nghiệm này.

## 6. Kịch bản B — HTTP phụ thuộc phản hồi chậm

Đảm bảo database và HTTP server giả lập đều hoạt động. Thử một yêu cầu chậm nhưng còn trong giới hạn:

```shell
curl -sS -i "http://127.0.0.1:8080/lab/remote?delayMs=700"
```

Nếu không có sự cố khác, phản hồi là 200 với `upstream-ok` và thời gian tăng theo độ trễ đã đặt. Tiếp theo, đặt độ trễ vượt read timeout:

```shell
curl -sS -i "http://127.0.0.1:8080/lab/remote?delayMs=4000"
curl -sS -i http://127.0.0.1:8081/actuator/health/readiness
curl -sS -i http://127.0.0.1:8081/actuator/health/liveness
curl -sS http://127.0.0.1:8081/actuator/metrics/http.client.requests
curl -sS "http://127.0.0.1:8081/actuator/metrics/http.server.requests?tag=uri:/lab/remote"
```

Trong điều kiện lab bình thường, API remote hết thời gian chờ quanh ngưỡng 1 giây cộng chi phí xử lý và trả 504 với body:

```text
remote-io-failed
```

Đối chiếu ba lớp bằng chứng:

- Log `Upstream I/O failed` có nguyên nhân timeout tương ứng. Nếu nguyên nhân là connection refused thì server giả lập chưa chạy; đó không phải thí nghiệm phản hồi chậm.
- Timer client và timer server có thêm lần gọi/độ trễ, với các nhãn lỗi/status đúng theo dữ liệu thực tế. Không giả định tên nhãn lỗi luôn giống giữa các HTTP client và phiên bản thư viện.
- Pool database vẫn có kết nối rảnh; `/lab/db` vẫn thành công. Như vậy tăng Hikari maximum-pool-size không giải quyết được đường gọi HTTP này.

Cả readiness lẫn liveness có thể vẫn UP: group readiness ở đây chỉ kiểm tra trạng thái sẵn sàng và database, chưa kiểm tra HTTP phụ thuộc. **Health UP không cam kết mọi API đều thành công hoặc đạt mục tiêu độ trễ.** Muốn phản ánh phụ thuộc HTTP, phải thiết kế health indicator và chính sách group phù hợp, kể cả timeout riêng cho phép kiểm tra; không chèn một lời gọi chậm không giới hạn vào health.

Không tăng timeout chỉ để làm mất mã 504. Nếu thời gian chờ tăng từ 1 lên 10 giây mà khả năng phục vụ không đổi, nhiều luồng có thể bị giữ lâu hơn và tạo sự cố thứ hai. Trong hệ thống thật, cần xét ngân sách thời gian toàn yêu cầu, giới hạn số lời gọi đồng thời và cơ chế ngắt mạch khi thích hợp. Retry không giới hạn có thể khuếch đại tải; bài này cố ý không tự retry.

Khôi phục bằng `/lab/remote?delayMs=0` và xác nhận 200. Đợi ít nhất 5 giây sau lời gọi 4000 ms để các công việc giả lập cũ kết thúc trước thí nghiệm tiếp theo; timeout client không bảo đảm upstream đã dừng làm việc. Khác với gauge, số lần lỗi đã ghi nhận vẫn tồn tại trong timer.

## 7. Kịch bản C — Database khỏe nhưng pool kết nối đã cạn

### 7.1. Giữ hết kết nối của ứng dụng

Xác nhận `/lab/db` đang trả 200 rồi giữ cả ba kết nối trong 20 giây:

```shell
curl -sS -X POST "http://127.0.0.1:8080/lab/pool/hold?seconds=20"
```

Body mong đợi sau khi giữ thành công:

```text
held=3
```

Ngay sau đó, terminal phát tải chạy một đợt tám yêu cầu:

```shell
python load.py /lab/db 8
```

Trong lúc các yêu cầu đang chờ, dùng terminal khác lấy bằng chứng. Cần bắt đầu ngay trong cửa sổ giữ 20 giây; pending chỉ tăng khi còn yêu cầu đang đợi:

```shell
curl -sS "http://127.0.0.1:8081/actuator/metrics/hikaricp.connections.active?tag=pool:lab-pool"
curl -sS "http://127.0.0.1:8081/actuator/metrics/hikaricp.connections.idle?tag=pool:lab-pool"
curl -sS "http://127.0.0.1:8081/actuator/metrics/hikaricp.connections.pending?tag=pool:lab-pool"
curl -sS http://127.0.0.1:8081/actuator/threaddump
curl -sS -i http://127.0.0.1:8081/actuator/health/readiness
curl -sS -i http://127.0.0.1:8081/actuator/health/liveness
```

### 7.2. Dấu hiệu phân biệt với database ngừng hoạt động

Khi ba kết nối còn được giữ, active của pool đạt 3 và idle bằng 0. Pending lớn hơn 0 **trong lúc** các yêu cầu phải đợi; nó có thể đã về 0 nếu ta lấy mẫu sau khi chúng timeout. Sau khoảng 3 giây chờ pool cộng chi phí xử lý, các yêu cầu chưa mượn được kết nối trả 503. Nếu đợt tải bắt đầu và hoàn tất trước lúc tự giải phóng, dòng tổng hợp status của script là:

```text
statuses: {503: 8}
```

Dòng `seconds` chứa các giá trị đo thực tế; không có dãy số cố định để sao chép. Nếu có 200, kiểm tra thời điểm phát tải so với thời điểm tự giải phóng trước khi kết luận mã gây lỗi không hoạt động.

Thread dump thường thể hiện luồng yêu cầu đang chờ mượn kết nối, với các khung gọi thuộc HikariPool/ConcurrentBag và cơ chế đợi của JDK. Không kết luận chỉ từ tên trạng thái WAITING hoặc TIMED_WAITING: nhiều luồng nền nhàn rỗi cũng có trạng thái đó. Phải nối khung gọi với endpoint đang chịu tải.

Kiểm tra PostgreSQL trực tiếp, không đi qua Hikari của ứng dụng:

```shell
docker compose exec -T db psql -U lab -d lab -c "SELECT 1;"
```

Nếu lệnh này thành công nhưng API báo timeout mượn pool, ta có bằng chứng rằng database vẫn tiếp nhận truy vấn từ một kết nối khác. Việc giữ kết nối ở ứng dụng là nguyên nhân được tạo trong thí nghiệm. PostgreSQL có thể thấy các phiên được giữ ở trạng thái idle; **active trong Hikari nghĩa là đang được mượn**, không đồng nghĩa database đang chạy truy vấn trên tất cả các phiên đó.

Readiness có thể DOWN/503 dù database còn khỏe vì phép kiểm tra `db` cũng cần mượn kết nối từ cùng DataSource. Liveness vẫn UP. Component `db` thất bại không đủ để phân biệt database hỏng với ứng dụng hết pool: phải ghép health với metrics, log, thread dump và phép thử độc lập.

### 7.3. Khôi phục có giới hạn

Đợi tác vụ tự giải phóng hoặc gọi:

```shell
curl -sS -X POST http://127.0.0.1:8080/lab/pool/release
curl -sS -i http://127.0.0.1:8080/lab/db
curl -sS -i http://127.0.0.1:8081/actuator/health/readiness
```

Release trả số kết nối vừa trả lại: `released=3` nếu còn giữ đủ ba, hoặc `released=0` nếu tác vụ định thời đã trả chúng trước đó. Sau khi các yêu cầu cũ kết thúc, pending về 0, active về mức nghỉ, API và readiness phục hồi.

Endpoint release vẫn chạy trên Tomcat API. Nếu tám luồng đều đang chờ pool, lệnh release có thể phải xếp hàng. Bộ định thời chạy riêng để việc khôi phục không phụ thuộc hoàn toàn vào endpoint cứu hộ bị xếp hàng này.

Trong mã thật, rà soát kết nối không được đóng, phạm vi transaction quá dài, truy vấn chậm và việc giữ transaction trong lúc gọi HTTP. Dùng try-with-resources khi trực tiếp quản lý Connection. Tăng pool chỉ có ý nghĩa sau khi hiểu giới hạn database và thời gian giữ kết nối; tăng số lượng không chữa được rò rỉ.

## 8. Kịch bản D — Hết luồng xử lý dù CPU thấp

Đảm bảo pool đã được trả hết, database và HTTP server đều khỏe. Phát 16 yêu cầu cùng ngủ 8 giây trong khi Tomcat API chỉ có 8 luồng:

```shell
python load.py "/lab/sleep?ms=8000" 16
```

Trong terminal khác, khi đợt tải đang chạy:

```shell
curl -sS --max-time 2 -i http://127.0.0.1:8080/lab/db
curl -sS -i http://127.0.0.1:8081/actuator/health/liveness
curl -sS http://127.0.0.1:8081/actuator/metrics/tomcat.threads.busy
curl -sS http://127.0.0.1:8081/actuator/threaddump
```

Một phần yêu cầu được xử lý trước, phần còn lại chờ luồng nên thời gian client thường tạo thành các đợt quanh 8 và 16 giây, cộng chi phí thực tế. Đừng yêu cầu hai cụm phải chính xác tuyệt đối. Lệnh curl tới `/lab/db` có thể hết `--max-time` dù câu SQL rất đơn giản và database khỏe: yêu cầu chưa được cấp luồng để đi đến bước mượn kết nối.

Bằng chứng cần đối chiếu:

- Số luồng bận của connector API tiến sát giới hạn 8 trong cửa sổ gây tải.
- Thread dump có các luồng yêu cầu đang ở `LabController.sleep` / `Thread.sleep`.
- Pool database không có mẫu active=3, idle=0 do thí nghiệm giữ kết nối; nó thường còn nhàn rỗi trong lúc các luồng đang ngủ.
- CPU có thể thấp vì ngủ/chờ không cần nhiều thời gian CPU. Có thể xem thêm `process.cpu.usage` và `jvm.threads.live` nếu các tên này hiện diện trong danh sách metrics; tổng số luồng JVM không phải số luồng Tomcat đang bận.
- Liveness ở cổng quản trị vẫn có thể UP. Readiness cũng có thể UP vì chính sách hiện tại chưa đo bão hòa connector API. Đây là giới hạn quan trọng của phép kiểm tra health trên cổng riêng.

Timeout của curl chỉ khiến client dừng chờ; không bảo đảm yêu cầu đang xếp hàng hay công việc phía server đã bị hủy. Vì thế vẫn đợi toàn bộ đợt tải kết thúc rồi kiểm tra `/lab/db` trở lại nhanh. Các yêu cầu sleep hữu hạn tự hết; không cần giết JVM để khôi phục kịch bản này.

Nếu áp dụng trong môi trường có probe thật, cần kiểm tra đường đi của probe có đại diện cho khả năng nhận lưu lượng ở cổng ứng dụng không. Cổng quản trị hoạt động không chứng minh connector nghiệp vụ hoạt động tốt. Đồng thời không được coi mọi WAITING trong thread dump là deadlock hoặc mọi luồng bận là CPU-bound.

## 9. Bảng đối chiếu để đặt giả thuyết

Các dấu hiệu sau là kết quả dự kiến trong **cấu hình lab này**, cần đọc cùng thời điểm. Chúng không thay thế log và bằng chứng thực thi.

| Sự cố được tạo | Triệu chứng API | Health dự kiến | Bằng chứng phân biệt |
| --- | --- | --- | --- |
| PostgreSQL bị dừng | Nhánh db lỗi 503 | Readiness DOWN; liveness UP | Phụ thuộc không truy cập được, lỗi JDBC có nguyên nhân kết nối; phép thử trực tiếp tới database thất bại |
| HTTP server trả quá chậm | Nhánh remote lỗi 504 theo mã mẫu | Có thể cả hai group vẫn UP | Lỗi timeout phía client HTTP; số liệu request client/server tăng; nhánh db vẫn hoạt động |
| Giữ hết ba kết nối | Nhánh db đợi rồi lỗi 503 | Readiness có thể DOWN; liveness UP | active=3, idle=0, pending tăng khi có người đợi; database trực tiếp vẫn trả SELECT 1 |
| Giữ hết luồng Tomcat API | Cả API đơn giản cũng phải chờ | Cổng quản trị có thể vẫn báo UP | Luồng connector API bận, stack nằm trong sleep; pool database không phải nút thắt |

Một phép kiểm tra trực tiếp thành công tại một thời điểm chỉ bác bỏ những giả thuyết phù hợp với phép kiểm tra đó. Ví dụ, SELECT 1 thành công không chứng minh mọi truy vấn nghiệp vụ nhanh, không có khóa hoặc còn đủ kết nối cho toàn hệ thống.

## 10. Trình tự chẩn đoán có thể lặp lại

1. **Khoanh triệu chứng:** endpoint nào, mã gì, độ trễ bao nhiêu, bắt đầu lúc nào, một nhánh hay nhiều nhánh bị ảnh hưởng?
2. **Chụp bằng chứng đồng thời:** health theo component, metrics đúng nhãn, log cùng khoảng thời gian và thread dump khi đang chờ. Đừng lấy pending sau khi sự cố đã hết rồi suy luận rằng chưa có hàng chờ.
3. **Nêu ít nhất hai giả thuyết:** database mất kết nối hay pool hết; upstream chậm hay luồng servlet bị giữ trước khi gọi upstream.
4. **Dùng phép thử tách lớp:** SELECT 1 trực tiếp, gọi upstream trực tiếp với cùng delay, hoặc so sánh nhánh không dùng database. Thay đổi một yếu tố mỗi lần.
5. **Khôi phục nguyên nhân đã tạo:** chạy lại db, bỏ delay, trả pool hoặc chờ sleep kết thúc. Đo lại API, readiness và gauge; không yêu cầu counter lịch sử trở về 0.
6. **Ghi kết luận có giới hạn:** bằng chứng nào xác nhận vị trí chờ, bằng chứng nào bác bỏ giả thuyết khác, điều gì chưa được đo. Một ảnh chụp metrics đơn lẻ không chứng minh rò rỉ tài nguyên hay quan hệ nhân quả.

Lỗi thực hành thường gặp:

- Gọi sai cổng: `/actuator` ở 8081, endpoint lab ở 8080; 404 do sai URL không phải sự cố database.
- Dùng `-f` của curl rồi không thấy body lỗi: khi chẩn đoán, dùng `-i` để nhìn cả mã HTTP và body như các ví dụ.
- Chỉ giữ kết nối nhưng chưa phát yêu cầu rồi chờ pending tăng: pending đếm người đang chờ, không đếm số kết nối đã bị giữ.
- Thấy readiness DOWN rồi restart toàn bộ ứng dụng: hành động này xóa bằng chứng và không sửa được database đang ngừng hoạt động.
- Thấy health UP rồi phủ nhận lỗi người dùng: health chỉ phản ánh các phép kiểm tra đã cấu hình, không phải cam kết về mọi đường gọi.
- Dùng bộ nhớ/CPU cao làm điều kiện bắt buộc để gọi là cạn tài nguyên: pool hoặc luồng xử lý có thể hết từ trước.
- Chạy nhiều kịch bản chồng lên nhau: timeout HTTP làm giữ luồng, giữ luồng làm lệnh cứu hộ bị xếp hàng, khiến khó phân biệt nguyên nhân ban đầu với tác động dây chuyền.

## 11. Bài tập và tiêu chí hoàn thành

Tự thực hiện lại mà không nhìn bảng đối chiếu, mỗi lần chỉ tạo một sự cố. Với từng kịch bản, viết một đoạn chẩn đoán gồm: triệu chứng và thời điểm; giả thuyết; hai nguồn bằng chứng độc lập; phép thử phân biệt; thao tác khôi phục; kết quả sau khôi phục.

Bạn hoàn thành bài khi giải thích được các câu sau bằng bằng chứng đã thu:

- Vì sao database vẫn chạy mà health db lại DOWN khi hết pool?
- Vì sao thêm kết nối database không giải quyết được HTTP upstream phản hồi chậm?
- Vì sao CPU thấp nhưng yêu cầu SELECT 1 vẫn mất nhiều giây ở kịch bản giữ luồng?
- Vì sao cổng quản trị trả liveness UP chưa đủ chứng minh cổng API đang tiếp nhận yêu cầu tốt?
- Vì sao một timeout phía client không bảo đảm công việc phía server đã được hủy?

Bài nâng cao có kiểm soát: đổi maximum-pool-size từ 3 lên 4 **và giữ nguyên mã chỉ giữ ba kết nối**, khởi động lại lab rồi chạy kịch bản pool. Dự đoán trước rằng còn một kết nối có thể phục vụ SELECT 1; độ trễ và pending sẽ phụ thuộc tải. Đây là cách kiểm tra giả thuyết về sức chứa, không phải bằng chứng rằng cứ tăng pool là xử lý được lỗi giữ kết nối trong hệ thống thật. Sau thử nghiệm, trả cấu hình về 3 trước khi dùng lại kết quả đối chiếu của bài.

## 12. Dọn môi trường

Đợi mọi đợt tải hoàn tất, trả kết nối còn giữ nếu có, dừng ứng dụng và HTTP server bằng Ctrl+C ở đúng terminal, rồi dừng stack của lab:

```shell
docker compose down
```

Chương trình đóng các kết nối được giữ và bộ định thời khi Spring đóng bean. Tệp Compose mẫu không khai báo named volume cần giữ lại; không dùng thêm lệnh xóa volume hoặc prune toàn Docker. Khi ứng dụng được tái khởi động cho lần học khác, lấy lại đường cơ sở vì dữ liệu metrics trong bộ nhớ đã thay đổi vòng đời.
