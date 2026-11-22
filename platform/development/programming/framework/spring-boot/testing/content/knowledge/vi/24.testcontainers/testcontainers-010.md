# Wait strategy, readiness và kiểm tra dịch vụ thực sự sẵn sàng

## 1. Vì sao container RUNNING chưa có nghĩa service READY?

Khi ứng dụng Spring Boot kiểm thử với Testcontainers, Docker có thể báo container đang chạy nhưng dịch vụ bên trong vẫn khởi tạo. PostgreSQL có thể đang recovery hoặc chạy migrations; Kafka có thể chưa có topic; một HTTP API có thể mở cổng 8080 trước khi tải cấu hình, cache hoặc dữ liệu nền.

Nếu test lập tức gọi API sau khi container bắt đầu nghe TCP, kết quả dễ bị **flaky**: máy phát triển chạy xanh, còn CI chậm trả HTTP 503 hoặc connection timeout. Thêm `Thread.sleep(10000)` không giải quyết đúng vấn đề: ngủ lâu vẫn có thể chưa đủ trên CI, và khiến test chậm vô ích trên máy nhanh.

Testcontainers có hai khái niệm cốt lõi:

- **Startup check strategy**: container đã đạt trạng thái lifecycle phù hợp hay chưa, ví dụ daemon đang running hoặc one-shot job đã exit 0.
- **Wait strategy**: dịch vụ bên trong container đã **usable cho mục tiêu test** chưa, ví dụ port nghe, HTTP `/ready` trả 200, log báo migration xong hoặc Docker HEALTHCHECK báo healthy.

Sau khi wait thành công, bài test vẫn nên gọi **operation nghiệp vụ thật** và assert kết quả. Readiness chỉ là điều kiện bắt đầu, không phải bằng chứng tất cả business functions đều đúng.

### Mục tiêu học tập

1. Phân biệt Docker running, socket listening, liveness, readiness và business-level verification.
2. Hiểu mặc định của `GenericContainer` và sự khác nhau giữa startup checks với readiness waits.
3. Dùng `Wait.forListeningPort()`, `Wait.forHttp(...)`, `Wait.forLogMessage(...)`, `Wait.forHealthcheck()` và `WaitAllStrategy`.
4. Chọn đúng status, path, body predicate, healthcheck và startup timeout theo backend.
5. Kết nối Spring Boot tới host/mapped port của Testcontainers bằng `@DynamicPropertySource` hoặc `@ServiceConnection`.
6. Biết vì sao Docker health state, log và port check đôi khi cho tín hiệu sai.
7. Chẩn đoán timeout, container exit, startup failure, HTTP 401/503, sai keyspace/schema và lifecycle cache.
8. Tạo integration test **deterministic** chứng minh cổng mở nhưng service chưa sẵn sàng, không dùng sleep ở test.
9. Kiểm một business HTTP operation sau khi readiness được xác nhận.
10. Biết khi nào nên dùng one-shot startup check, multi-container dependency, liveness/readiness Actuator và CI assertions về số tests thực sự chạy.

Bài dùng **Java 17, Spring Boot 3.5.16, Testcontainers Java 1.21.x API, JUnit Jupiter và Maven**. Một HTTP service giả lập chạy trong Docker image Python; test/Spring client đều viết bằng Java. Môi trường cần Docker-compatible runtime và khả năng tải image; không cần Python được cài trên máy host.

## 2. Năm trạng thái cần tách biệt

~~~text
Docker CREATE
   |
   v
Process RUNNING (Docker inspect state)
   |
   v
Port LISTENING (TCP accept connection)
   |
   v
Application READY (GET /ready => 200 + READY)
   |
   v
Business USABLE (GET /api/orders/42 => 200 + dữ liệu đúng)
~~~

| Tầng | Dấu hiệu | Không chứng minh |
| --- | --- | --- |
| Container created | Docker container ID tồn tại | Process còn sống |
| Container running | Entrypoint process chưa exit | TCP cổng đã mở |
| Port listening | Kết nối TCP thành công | Schema/credentials/cache đã sẵn sàng |
| Liveness | `GET /live` cho biết process khỏe | Dependencies đủ để phục vụ request |
| Readiness | `GET /ready` phản ánh khả năng nhận request | Mọi rule nghiệp vụ đều đúng |
| Business probe | Gọi endpoint/query thật với assertion cụ thể | Hệ thống không thể lỗi về sau |

### 2.1. Liveness và readiness khác nhau

Liveness trả lời: **process còn hoạt động không, có cần restart không?**

Readiness trả lời: **service hiện có đủ điều kiện xử lý request thuộc phạm vi đã định không?**

Khi database tạm thời down, một application có thể còn liveness UP nhưng readiness DOWN. Không nên biến mọi dependency failure thành liveness failure rồi khiến orchestrator restart toàn bộ pods liên tục. Ngược lại, readiness UP khi database/schema critical chưa sẵn sàng là tín hiệu sai.

### 2.2. Readiness phải có hợp đồng rõ

Ví dụ Order API cần:
- Đã khởi tạo HTTP routes.
- DB connection thực sự đăng nhập được.
- Migrations hoặc schema version yêu cầu đã được áp dụng.
- Các indices/tables/permissions cần thiết đã tồn tại.
- Internal state cần thiết đã load xong.

Nếu API vẫn phục vụ tốt phần cốt lõi khi một analytics backend optional bị lỗi, có thể không cần chặn readiness vì analytics. Health contract phải do requirement quyết định; không có một danh sách dependencies chung cho mọi ứng dụng.

### 2.3. Readiness chỉ là snapshot

Ngay sau `container.start()`, một backend có thể bị restart hoặc mất network. Readiness không thay thế retry/error handling/circuit breaker trong ứng dụng thật. Bài test vẫn cần xác minh operation thực tế thay vì nghĩ wait strategy bảo đảm mọi request tương lai.

### 2.4. Vì sao test nên có negative example?

Nếu chỉ viết `Wait.forHttp("/ready")` và test PASS, người học dễ nhầm nó tương đương TCP port wait. Project trong bài cố ý có chế độ **manual**: port và `/live` hoạt động, nhưng `/ready` trả 503 cho đến khi test gửi một lệnh bật readiness. Đây là bằng chứng không phụ thuộc tốc độ CI.

## 3. Startup check strategy khác wait strategy

### 3.1. Startup check

Testcontainers kiểm trạng thái của container bằng `StartupCheckStrategy`. Mặc định, `IsRunningStartupCheckStrategy` thích hợp với daemon/service lâu dài: process được coi là đã start khi running và không exit bất thường.

Với một job chạy ngắn, ví dụ migration:
- Job exit **0** có thể là thành công.
- Job exit **1** là failure.
- Không yêu cầu process running mãi hoặc mở TCP port.

`OneShotStartupCheckStrategy` dành cho kiểu job này; `IndefiniteWaitOneShotStartupCheckStrategy` là biến thể không áp cùng startup deadline. Chỉ sử dụng indefinite nếu job được giám sát riêng; một job treo vô hạn không phải integration test tốt.

`MinimumDurationRunningStartupCheckStrategy` hoặc `withMinimumRunningDuration(Duration...)` có thể xác nhận container duy trì running một khoảng thời gian, nhưng vẫn **không chứng minh readiness ứng dụng**.

### 3.2. Wait strategy

Sau khi container đạt trạng thái startup, Testcontainers dùng `WaitStrategy` để xác định service ready. Với `GenericContainer`, tài liệu Testcontainers Java mô tả mặc định thường đợi **cổng mapped đầu tiên bắt đầu lắng nghe** và thời hạn wait cơ bản khoảng 60 giây.

~~~java
GenericContainer<?> nginx = new GenericContainer<>(
        DockerImageName.parse("nginx:1.27-alpine"))
        .withExposedPorts(80);
~~~

Đoạn trên là snippet minh họa, không phải Java class độc lập. Với Nginx trả trang tĩnh, port wait có thể đủ. Nhưng đối với API cần migration, cổng mở quá sớm.

### 3.3. Lifecycle khi gọi start()

~~~text
new GenericContainer(...) 
        |
        v
Docker pull/create/start
        |
        v
StartupCheckStrategy: running / one-shot exit?
        |
        v
WaitStrategy: port / HTTP / log / healthy?
        |
        v
Container.start() returns
        |
        v
Spring context / JUnit test uses service
        |
        v
Business assertions
~~~

Phân loại lỗi:
- **Process exit 1**: startup check fail; tăng HTTP wait timeout không sửa được invalid command/config.
- **Process vẫn running, HTTP wait timeout**: chưa ready, path/port sai, auth lỗi, service treo hoặc wait predicate sai.
- **Wait thành công, business GET fail**: readiness quá yếu hoặc lỗi business/authorization/data/runtime sau wait.

## 4. Các wait strategies thông dụng

### 4.1. Wait.forListeningPort()

~~~java
GenericContainer<?> redis = new GenericContainer<>(
        DockerImageName.parse("redis:7.2-alpine"))
        .withExposedPorts(6379)
        .waitingFor(Wait.forListeningPort());
~~~

Đây là test fixture snippet với Testcontainers imports. Socket open là tín hiệu tối thiểu; nếu test cần Redis thực sự xử lý commands, hãy gửi `PING`/SET/GET bằng client hoặc command sau start. Với SQL database, cần SQL query/schema readiness khi mục tiêu vượt ngoài kết nối đơn thuần.

### 4.2. Wait.forHttp() cho HTTP readiness

~~~java
GenericContainer<?> app = new GenericContainer<>(
        DockerImageName.parse("nginx:1.27-alpine"))
        .withExposedPorts(80)
        .waitingFor(Wait.forHttp("/")
                .forPort(80)
                .forStatusCode(200)
                .withStartupTimeout(Duration.ofSeconds(60)));
~~~

Với app thật, thay `/` bằng endpoint readiness có ý nghĩa. Các method hữu ích:
- `forPort(int)` chọn **cổng bên trong container** được Testcontainers map.
- `forStatusCode(200)` yêu cầu status HTTP.
- `forStatusCodeMatching(code -> code >= 200 && code < 300)` nếu contract chấp nhận nhiều mã.
- `forResponsePredicate(body -> ...)` kiểm payload readiness chứ không chỉ 200.
- `usingTls()` cho HTTPS; `allowInsecure()` chỉ khi test-only certificate có chủ đích.
- `withMethod("GET")`, `withHeader(...)`, `withBasicCredentials(...)` cho endpoint có yêu cầu đặc thù.
- `withReadTimeout(Duration...)` giới hạn từng HTTP probe.
- `withStartupTimeout(Duration...)` giới hạn khoảng chờ readiness.

Ví dụ quan trọng:

~~~java
Wait.forHttp("/ready")
        .forPort(8080)
        .forStatusCode(200)
        .forResponsePredicate(body ->
                body.contains("\"status\":\"READY\""))
        .withStartupTimeout(Duration.ofSeconds(45));
~~~

Nếu endpoint trả 200 với body `{"status":"STARTING"}`, body predicate ngăn false-positive. Nếu endpoint trả 503 cho not-ready, status check đã đủ cho điều kiện cơ bản, nhưng body assertion vẫn giúp bảo vệ contract.

**Không** tùy tiện chấp nhận 401/302 là success nếu downstream test cần authenticated API. Chỉ cho phép các status đó khi đúng readiness contract và có business probe riêng.

### 4.3. Wait.forLogMessage()

~~~java
GenericContainer<?> redis = new GenericContainer<>(
        DockerImageName.parse("redis:7.2-alpine"))
        .withExposedPorts(6379)
        .waitingFor(Wait.forLogMessage(
                ".*Ready to accept connections.*\\n", 1));
~~~

Log wait dùng regex và số lần match. Nó có ích khi service không có HTTP readiness endpoint nhưng có message xuất hiện **sau** khi initialization hoàn tất.

Cạm bẫy:
- Wording/log format có thể đổi giữa phiên bản.
- “Starting server” không đồng nghĩa “ready”.
- Regex match rộng quá có thể bắt một line không mong muốn.
- Buffering có thể giữ log chưa flush.
- Log ready đôi khi xuất hiện trước permission/index/config init của một operation đặc biệt.

Vì thế sau log wait phải thử **protocol command hoặc business operation**.

### 4.4. Wait.forHealthcheck()

~~~java
GenericContainer<?> app = new GenericContainer<>(
        DockerImageName.parse("example/my-app:1.0"))
        .withExposedPorts(8080)
        .waitingFor(Wait.forHealthcheck());
~~~

Chỉ áp dụng khi image có Docker `HEALTHCHECK` thực sự. Nếu image không khai báo healthcheck, Docker không có trạng thái healthy có nghĩa để chờ. `Wait.forHealthcheck()` không tự tạo health endpoint.

Dockerfile minh họa cho HTTP service của bài:

~~~dockerfile
FROM python:3.12-alpine
COPY ready_server.py /app/ready_server.py

HEALTHCHECK --interval=1s --timeout=2s \
  --start-period=2s --retries=12 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/ready', timeout=1)"

CMD ["python", "-u", "/app/ready_server.py"]
~~~

`urlopen` ném HTTPError khi `/ready` trả 503, làm healthcheck command exit khác 0. Khi 200, healthcheck trả exit 0. Dockerfile này là **mẫu mở rộng tùy chọn**, không phải file cần tạo cho runnable lab: lab dùng prebuilt Python image với HTTP/log waits.

### 4.5. WaitAllStrategy

Khi cần nhiều tín hiệu:

~~~java
WaitAllStrategy combined = new WaitAllStrategy()
        .withStrategy(Wait.forLogMessage(
                ".*SERVICE_READY.*\\n", 1))
        .withStrategy(Wait.forHttp("/ready")
                .forPort(8080)
                .forStatusCode(200))
        .withStartupTimeout(Duration.ofMinutes(2));

container.waitingFor(combined);
~~~

Đây là snippet nằm trong class đã có `container` và imports Testcontainers. Kết hợp log “migration xong” và HTTP readiness có giá trị khi mỗi điều kiện bảo vệ một rủi ro khác nhau. Không gắn hàng loạt waits trùng lặp hoặc nested timeouts vô căn cứ.

### 4.6. Custom wait strategy

Nếu backend không có endpoint/log/HEALTHCHECK đáng tin, có thể kiểm trực tiếp giao thức bằng client hoặc viết subclass `AbstractWaitStrategy` và override `waitUntilReady()`. Custom strategy phải bounded, giải thích được lỗi, giữ thông tin nguyên nhân và không in secret. Cần cân nhắc API compatibility qua các phiên bản Testcontainers.

Một số module chuyên biệt đã có start checks phù hợp; không thay default wait của `PostgreSQLContainer` hoặc `KafkaContainer` bằng TCP check yếu hơn nếu chưa hiểu semantics module.

## 5. Chọn readiness theo backend

| Dịch vụ | Tín hiệu phù hợp hơn port mở | Assertion sau start |
| --- | --- | --- |
| HTTP API | `GET /ready` 200, body đúng | Business GET/POST, JSON/body/status |
| Spring Boot Actuator | `/actuator/health/readiness` nếu đã bật probes | Business endpoint và DB/schema |
| PostgreSQL | Connection/JDBC thực, schema migrations hoàn tất | `SELECT 1`, query bảng cần dùng |
| MySQL/MariaDB | Auth + SQL query, schema version | Query/insert test record riêng |
| Redis | `PING -> PONG` hoặc command cụ thể | SET/GET nếu test cache behavior |
| Kafka | Metadata/topics/partitions ready | Publish/consume test message |
| RabbitMQ | Connection/channel/queue/permissions sẵn | Publish và consume |
| Elasticsearch | Cluster/index/alias phù hợp | Search/index query với fixture |
| Cassandra | Session, datacenter, keyspace | Table/query theo partition key |
| Couchbase | Cluster/bucket/services/index | KV + SQL++ query theo requirement |
| S3-compatible service | Health hoặc signed API request | Put/get test-only object |
| Migration one-shot job | Exit code 0 | Schema version/query đúng |

Không có readiness signal nào chứng minh toàn bộ production SLA, failover hoặc distributed consistency. Test infrastructure càng gần production thì assertions càng nên xác định đúng phần contract cần kiểm.

## 6. Project thực hành — Spring Boot 3.5.16 + Java 17 + Testcontainers

### 6.1. Ý tưởng

Ta xây một service HTTP nhỏ chạy bằng Python **trong Docker**. Service có 4 endpoint:

| Endpoint | Khi mới mở port | Sau ready |
| --- | --- | --- |
| `GET /live` | 200, `{"status":"UP"}` | 200 |
| `GET /ready` | 503, `{"status":"NOT_READY"}` | 200, `{"status":"READY"}` |
| `GET /api/orders/42` | 503 | 200, `{"id":"42","status":"AVAILABLE"}` |
| `POST /admin/ready` | Chuyển sang ready, HTTP 204 | Giữ ready, HTTP 204 |

Chế độ `READY_MODE=manual` chỉ cho phép test chuyển readiness bằng POST; do đó test port-only không phụ thuộc wall-clock. Chế độ `READY_MODE=auto` tự chuyển ready sau 2 giây bên trong service và ghi log `SERVICE_READY`. Java tests không dùng `Thread.sleep`.

Ba class test:
- `PortIsNotReadinessTest`: TCP wait có thể return trong khi readiness/business vẫn 503; POST để bật ready rồi assert 200.
- `HttpReadinessSpringBootTest`: HTTP wait + response predicate; kết nối Spring Boot client qua `@DynamicPropertySource`.
- `LogReadinessTest`: log wait rồi gọi business endpoint để xác nhận.

### 6.2. Cấu trúc thư mục

~~~text
testcontainers-readiness-lab/
├── pom.xml
├── src/main/resources/application.properties
├── src/main/java/com/example/readiness/
│   ├── ReadinessLabApplication.java
│   └── BackendClient.java
├── src/test/resources/ready_server.py
└── src/test/java/com/example/readiness/
    ├── TestServices.java
    ├── HttpProbe.java
    ├── PortIsNotReadinessTest.java
    ├── HttpReadinessSpringBootTest.java
    └── LogReadinessTest.java
~~~

Đặt mỗi file đúng path/package. Không cần Python được cài trên host; Docker image chứa Python. Cần Docker daemon/remote runtime được Testcontainers hỗ trợ, JDK 17+ và Maven. CI phải có khả năng tải hoặc pull image từ cache nội bộ.

### 6.3. pom.xml

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
  <artifactId>testcontainers-readiness-lab</artifactId>
  <version>1.0.0</version>
  <properties>
    <java.version>17</java.version>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-test</artifactId>
      <scope>test</scope>
    </dependency>
    <dependency>
      <groupId>org.testcontainers</groupId>
      <artifactId>junit-jupiter</artifactId>
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

Spring Boot parent quản lý dependency versions, gồm Testcontainers cho Boot 3.5. Không trộn Testcontainers 2.x modules vào các import/code 1.x khi chưa kiểm tương thích. Project không cần Spring Web starter vì HTTP client dùng Java 17 `java.net.http.HttpClient`; backend là container Python chứ không phải Spring REST controller.

### 6.4. application.properties

`src/main/resources/application.properties`:

~~~properties
# Fallback cho lúc mở application ngoài test.
# Không có server ở port này trừ khi bạn tự chạy.
backend.base-url=http://127.0.0.1:9999
~~~

Trong test Spring Boot, `@DynamicPropertySource` override `backend.base-url` bằng mapped host/port của Testcontainers, không dùng fallback.

### 6.5. ReadinessLabApplication.java

~~~java
package com.example.readiness;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReadinessLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReadinessLabApplication.class, args);
    }
}
~~~

### 6.6. BackendClient.java

`src/main/java/com/example/readiness/BackendClient.java`:

~~~java
package com.example.readiness;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class BackendClient {

    private final String baseUrl;
    private final HttpClient http;

    public BackendClient(Environment environment) {
        this.baseUrl = environment.getRequiredProperty(
                "backend.base-url");
        this.http = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(3))
                .build();
    }

    public String baseUrl() {
        return baseUrl;
    }

    public HttpResponse<String> readiness()
            throws IOException, InterruptedException {
        return get("/ready");
    }

    public String order42()
            throws IOException, InterruptedException {
        HttpResponse<String> result = get("/api/orders/42");
        if (result.statusCode() != 200) {
            throw new IllegalStateException(
                    "upstream status " + result.statusCode());
        }
        return result.body();
    }

    private HttpResponse<String> get(String path)
            throws IOException, InterruptedException {
        HttpRequest request = HttpRequest.newBuilder(
                        URI.create(baseUrl + path))
                .timeout(Duration.ofSeconds(5))
                .GET()
                .build();
        return http.send(
                request, HttpResponse.BodyHandlers.ofString());
    }
}
~~~

Giải thích:
- Bean chỉ thiết lập HTTP client, **không gọi endpoint trong constructor**.
- `Environment.getRequiredProperty` đọc configuration tại lúc Spring context tạo bean.
- Request/connection timeouts hữu hạn để test không treo vĩnh viễn.
- `order42()` kiểm HTTP status, rồi test kiểm thêm body chứa ID/state.
- Runtime production phải có retry/circuit breaker/tracing/credential handling theo nhu cầu; readiness lúc startup không bảo đảm upstream sống mãi.

### 6.7. ready_server.py

`src/test/resources/ready_server.py`:

~~~python
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

READY = threading.Event()


class Handler(BaseHTTPRequestHandler):
    def respond(self, status, body):
        data = json.dumps(body, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/live":
            self.respond(200, {"status": "UP"})
            return
        if self.path == "/ready":
            if READY.is_set():
                self.respond(200, {"status": "READY"})
            else:
                self.respond(503, {"status": "NOT_READY"})
            return
        if self.path == "/api/orders/42":
            if READY.is_set():
                self.respond(200, {
                    "id": "42", "status": "AVAILABLE"
                })
            else:
                self.respond(503, {
                    "error": "DEPENDENCY_NOT_READY"
                })
            return
        self.respond(404, {"error": "NOT_FOUND"})

    def do_POST(self):
        if self.path != "/admin/ready":
            self.respond(404, {"error": "NOT_FOUND"})
            return

        READY.set()
        print("SERVICE_READY", flush=True)
        self.send_response(204)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, format_string, *args):
        # Giảm access logs trong lab.
        pass


def complete_initialization():
    delay = float(os.environ.get("READY_DELAY_SECONDS", "2"))
    time.sleep(delay)
    READY.set()
    print("SERVICE_READY", flush=True)


server = ThreadingHTTPServer(("0.0.0.0", 8080), Handler)
mode = os.environ.get("READY_MODE", "auto")

if mode == "auto":
    threading.Thread(
        target=complete_initialization,
        daemon=True
    ).start()

print("LISTENING", flush=True)
server.serve_forever()
~~~

Đặc điểm:
- HTTP socket được bind **trước** khi readiness chuyển UP.
- `READY_MODE=manual` bảo đảm `/ready` **luôn 503** cho tới POST admin, bất kể image start nhanh/chậm.
- `READY_MODE=auto` mô phỏng initialization có delay 2 giây; Java wait strategy poll đúng status, không tự sleep.
- `SERVICE_READY` chỉ được in sau khi `READY.set()`, dùng làm log readiness signal.
- 204 response không có body, đúng semantics HTTP.
- `/admin/ready` chỉ là hook cho test, **không bao giờ nên expose cơ chế bypass này ở production**.
- Tất cả payload là synthetic JSON, không có credentials hoặc production data.

### 6.8. TestServices.java

`src/test/java/com/example/readiness/TestServices.java`:

~~~java
package com.example.readiness;

import org.testcontainers.containers.GenericContainer;
import org.testcontainers.utility.DockerImageName;
import org.testcontainers.utility.MountableFile;

final class TestServices {

    static final int PORT = 8080;

    private TestServices() {
    }

    static GenericContainer<?> pythonService(String mode) {
        return new GenericContainer<>(
                DockerImageName.parse("python:3.12-alpine"))
                .withExposedPorts(PORT)
                .withCopyFileToContainer(
                        MountableFile.forClasspathResource(
                                "ready_server.py"),
                        "/app/ready_server.py")
                .withCommand(
                        "python", "-u", "/app/ready_server.py")
                .withEnv("READY_MODE", mode)
                .withEnv("READY_DELAY_SECONDS", "2");
    }
}
~~~

Factory tạo **mô tả container mới**, không start nó, và không chia sẻ một mutable static container trên nhiều test classes. Mỗi test chọn wait strategy. `withExposedPorts(8080)` tạo host port mapping; không có nghĩa port ở host cũng là 8080.

Tag `python:3.12-alpine` phù hợp demo; CI cần pin image digest/version được kiểm duyệt nếu yêu cầu kết quả reproducible hoặc tránh supply-chain drift.

### 6.9. HttpProbe.java

`src/test/java/com/example/readiness/HttpProbe.java`:

~~~java
package com.example.readiness;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

import org.testcontainers.containers.GenericContainer;

final class HttpProbe {

    private static final HttpClient CLIENT =
            HttpClient.newBuilder()
                    .connectTimeout(Duration.ofSeconds(3))
                    .build();

    private HttpProbe() {
    }

    static HttpResponse<String> get(
            GenericContainer<?> container, String path)
            throws IOException, InterruptedException {
        HttpRequest request = HttpRequest.newBuilder(
                        url(container, path))
                .timeout(Duration.ofSeconds(5))
                .GET()
                .build();
        return CLIENT.send(
                request, HttpResponse.BodyHandlers.ofString());
    }

    static HttpResponse<String> post(
            GenericContainer<?> container, String path)
            throws IOException, InterruptedException {
        HttpRequest request = HttpRequest.newBuilder(
                        url(container, path))
                .timeout(Duration.ofSeconds(5))
                .POST(HttpRequest.BodyPublishers.noBody())
                .build();
        return CLIENT.send(
                request, HttpResponse.BodyHandlers.ofString());
    }

    static URI url(
            GenericContainer<?> container, String path) {
        return URI.create(
                "http://" + container.getHost()
                        + ":" + container.getMappedPort(
                                TestServices.PORT)
                        + path);
    }
}
~~~

Sử dụng `container.getHost()` và `getMappedPort(8080)` **sau container.start**. Không hard-code `localhost:8080`: Docker Desktop, CI, remote Docker hoặc Docker-in-Docker có thể map tới host/port khác. Nếu container giao tiếp với container khác trong cùng Docker network, dùng network alias và **internal port**, không copy host mapped port vào container-to-container URL.

### 6.10. PortIsNotReadinessTest.java

`src/test/java/com/example/readiness/PortIsNotReadinessTest.java`:

~~~java
package com.example.readiness;

import java.net.http.HttpResponse;
import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.containers.wait.strategy.Wait;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.assertj.core.api.Assertions.assertThat;

@Testcontainers(disabledWithoutDocker = true)
class PortIsNotReadinessTest {

    @Container
    static final GenericContainer<?> backend =
            TestServices.pythonService("manual")
                    .waitingFor(Wait.forListeningPort())
                    .withStartupTimeout(Duration.ofSeconds(45));

    @Test
    void openPortDoesNotMeanBusinessReady()
            throws Exception {
        HttpResponse<String> live =
                HttpProbe.get(backend, "/live");
        HttpResponse<String> before =
                HttpProbe.get(backend, "/ready");
        HttpResponse<String> unavailable =
                HttpProbe.get(backend, "/api/orders/42");

        assertThat(live.statusCode()).isEqualTo(200);
        assertThat(live.body())
                .contains("\"status\":\"UP\"");

        assertThat(before.statusCode()).isEqualTo(503);
        assertThat(before.body())
                .contains("\"status\":\"NOT_READY\"");
        assertThat(unavailable.statusCode())
                .isEqualTo(503);

        HttpResponse<String> activate =
                HttpProbe.post(backend, "/admin/ready");

        assertThat(activate.statusCode()).isEqualTo(204);

        HttpResponse<String> ready =
                HttpProbe.get(backend, "/ready");
        HttpResponse<String> business =
                HttpProbe.get(backend, "/api/orders/42");

        assertThat(ready.statusCode()).isEqualTo(200);
        assertThat(ready.body())
                .contains("\"status\":\"READY\"");
        assertThat(business.statusCode()).isEqualTo(200);
        assertThat(business.body())
                .contains("\"status\":\"AVAILABLE\"");
    }
}
~~~

Đây là test minh họa quan trọng nhất: **chắc chắn** `/ready=503` sau port wait vì READY_MODE=manual, không phụ thuộc timing. Sau admin POST, test xác minh readiness và business endpoint. Không có JUnit `Thread.sleep` hoặc sự phụ thuộc vào máy nhanh/chậm.

### 6.11. HttpReadinessSpringBootTest.java

`src/test/java/com/example/readiness/HttpReadinessSpringBootTest.java`:

~~~java
package com.example.readiness;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.containers.wait.strategy.Wait;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@Testcontainers(disabledWithoutDocker = true)
class HttpReadinessSpringBootTest {

    @Container
    static final GenericContainer<?> backend =
            TestServices.pythonService("auto")
                    .waitingFor(Wait.forHttp("/ready")
                            .forPort(TestServices.PORT)
                            .forStatusCode(200)
                            .forResponsePredicate(body ->
                                    body.contains(
                                            "\"status\":\"READY\""))
                            .withReadTimeout(
                                    Duration.ofSeconds(3))
                            .withStartupTimeout(
                                    Duration.ofSeconds(45)));

    @DynamicPropertySource
    static void backendProperties(
            DynamicPropertyRegistry registry) {
        registry.add("backend.base-url",
                () -> "http://" + backend.getHost()
                        + ":" + backend.getMappedPort(
                                TestServices.PORT));
    }

    @Autowired
    BackendClient client;

    @Test
    void readinessWaitAllowsBusinessCall()
            throws Exception {
        assertThat(client.readiness().statusCode())
                .isEqualTo(200);

        String response = client.order42();

        assertThat(response).contains("\"id\":\"42\"");
        assertThat(response)
                .contains("\"status\":\"AVAILABLE\"");
    }

    @Test
    void springBeanUsesDynamicMappedAddress() {
        String expected = "http://" + backend.getHost()
                + ":" + backend.getMappedPort(
                        TestServices.PORT);

        assertThat(client.baseUrl()).isEqualTo(expected);
    }
}
~~~

Điểm kiểm:
- `@Container` quản lý service trong JUnit class.
- `@DynamicPropertySource` cung cấp mapped host/port cho Spring bean khi test context tạo.
- `Wait.forHttp("/ready")` đợi HTTP 200 **và** response chứa `READY`.
- `BackendClient` gọi business endpoint thật qua HTTP, không mock backend response.
- `withReadTimeout` giới hạn một HTTP probe, còn `withStartupTimeout` là budget của readiness waiting. Không nhầm hai timeout này.
- Không cần `@ServiceConnection` cho custom Python HTTP server, vì Boot không có built-in connection factory cho service tùy ý này.
- Nếu ứng dụng cần import container configuration qua nhiều classes, phải chú ý lifecycle của JUnit static containers và Spring TestContext caching; lab chỉ dùng một Spring integration class riêng.

### 6.12. LogReadinessTest.java

`src/test/java/com/example/readiness/LogReadinessTest.java`:

~~~java
package com.example.readiness;

import java.net.http.HttpResponse;
import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.containers.wait.strategy.Wait;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.assertj.core.api.Assertions.assertThat;

@Testcontainers(disabledWithoutDocker = true)
class LogReadinessTest {

    @Container
    static final GenericContainer<?> backend =
            TestServices.pythonService("auto")
                    .waitingFor(Wait.forLogMessage(
                            ".*SERVICE_READY.*\\n", 1))
                    .withStartupTimeout(Duration.ofSeconds(45));

    @Test
    void readinessLogMustBeFollowedByBusinessProbe()
            throws Exception {
        HttpResponse<String> ready =
                HttpProbe.get(backend, "/ready");
        HttpResponse<String> order =
                HttpProbe.get(backend, "/api/orders/42");

        assertThat(ready.statusCode()).isEqualTo(200);
        assertThat(order.statusCode()).isEqualTo(200);
        assertThat(order.body())
                .contains("\"status\":\"AVAILABLE\"");

        assertThat(backend.getLogs())
                .contains("SERVICE_READY");
    }
}
~~~

Chỉ đợi log `LISTENING` sẽ quá sớm; vì demo in `SERVICE_READY` **sau khi set trạng thái ready**, log wait phản ánh condition mạnh hơn. Nhưng bài test vẫn verify HTTP thật để không coi một dòng log là bằng chứng tuyệt đối.

### 6.13. Chạy Maven

~~~bash
mvn -q clean test

mvn -q -Dtest=PortIsNotReadinessTest test
mvn -q -Dtest=HttpReadinessSpringBootTest test
mvn -q -Dtest=LogReadinessTest test
~~~

Khi Docker có sẵn:
- Port test kiểm 200 liveness / 503 readiness trước admin, sau đó 200 readiness/business.
- HTTP Spring test đợi service sẵn sàng rồi kiểm business JSON và mapped address.
- Log test đợi log `SERVICE_READY` rồi kiểm HTTP status/payload.
- Maven thành công trả exit code 0, xem số tests và reports trong `target/surefire-reports`.

**Cực kỳ quan trọng:** `@Testcontainers(disabledWithoutDocker = true)` có thể **skip tests** khi Docker không có. Exit code 0 với các tests bị skip không chứng minh integration đã PASS. Trong CI dành riêng cho integration, yêu cầu Docker runtime, kiểm tổng số tests executed và `skipped=0`.

Đây là mã nguồn mẫu được rà soát theo API Testcontainers 1.21.x; chưa thực thi Maven/Docker trong quá trình biên soạn. Không hứa một elapsed time hay console output cố định vì image pull, Docker host, JDK/Maven caches và CI resources khác nhau.

## 7. Spring Boot integration và service connections

### 7.1. @DynamicPropertySource cho custom backend

`@DynamicPropertySource` đăng ký supplier tạo property khi cần:

~~~java
@DynamicPropertySource
static void serviceProperties(DynamicPropertyRegistry registry) {
    registry.add("backend.base-url",
            () -> "http://" + backend.getHost() + ":"
                    + backend.getMappedPort(8080));
}
~~~

Cần có `static GenericContainer<?> backend` cùng test class. Không tính mapped port khi container chưa start. Supplier dùng host/port thực tế nên chạy được trên Docker remote thay vì hard-code URL.

### 7.2. @ServiceConnection với known container

Với Spring Boot 3.5 và dependency `spring-boot-testcontainers`, nhiều typed container có factory tự tạo connection details. Ví dụ:

~~~java
@Container
@ServiceConnection
static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");
~~~

Đây là snippet **không thuộc runnable Python lab**; cần các Maven modules `spring-boot-testcontainers` và `org.testcontainers:postgresql`. Khi được nhận diện, Spring Boot tạo `JdbcConnectionDetails` (và các details khác khi applicable) để auto-config client kết nối đúng container.

`@ServiceConnection` **không**:
- Tự làm business schema migration.
- Tạo Kafka topic/index/bucket.
- Đảm bảo readiness mạnh hơn wait strategy của container.
- Tự biến HTTP generic service thành known backend type.
- Đảm bảo external credentials/authorization thành công.

Đối với `GenericContainer` được khai báo như Spring `@Bean`, khi cần connection details loại Redis có thể phải dùng `@ServiceConnection(name="redis")` để Boot biết image category. Custom HTTP service vẫn dùng dynamic property hoặc custom connection details.

### 7.3. Static @Container và cached ApplicationContext

Spring Boot 3.5 documentation lưu ý: JUnit `@Testcontainers` static fields thường stop sau khi test class chạy. Spring TestContext có thể cache ApplicationContext qua các classes; nếu context bị reuse với client trỏ tới container đã stop, test sau fail khó hiểu.

Khi nhiều Spring test classes dùng chung dependencies, cân nhắc `@TestConfiguration` khai báo **container như Spring bean**:
- Spring start container bean trước những beans phụ thuộc.
- Spring destroy dependent beans trước khi container bị stop.
- Container sống theo lifecycle của cached context.

Không mặc định dùng một static singleton container kết hợp `@Container`/`@Testcontainers` ở mọi class rồi tin context cache không ảnh hưởng. Nếu chỉ có một integration class như lab, static container là cách học đơn giản và hợp lệ.

### 7.4. Network trong multi-container tests

Nếu JVM test gọi container A, dùng:
- `container.getHost()`.
- `container.getMappedPort(internalPort)`.

Nếu container A gọi container B trong cùng `Network.newNetwork()`, dùng:
- `withNetworkAliases("database")`.
- `database:5432` hoặc internal port tương ứng.

Không lấy mapped host port của B làm container-to-container address trừ khi kiến trúc network thật sự yêu cầu. `dependsOn` thiết lập startup dependency ordering, nhưng readiness của B chỉ tốt bằng wait strategy đã đặt trên B.

## 8. Timeouts và startup attempts

| Timeout | Phạm vi | Gợi ý |
| --- | --- | --- |
| `WaitStrategy.withStartupTimeout` | Deadline để ready condition thành công | Dựa trên startup P95/P99, thêm CI margin |
| `GenericContainer.withStartupTimeout` | Container startup/wait budget theo API | Không đồng nghĩa một HTTP probe timeout |
| `HttpWaitStrategy.withReadTimeout` | Giới hạn thời gian đọc một HTTP probe | Nhỏ hơn hoặc hợp lý so với tổng readiness budget |
| HTTP client connect timeout | TCP connect từ JVM test | Không chờ vô hạn |
| HTTP request timeout | Một business request | Theo SLA test/operation |
| JUnit `@Timeout` | Toàn test method | Cẩn thận thread mode với transactional tests |
| Docker image pull/build | Image acquisition | Không luôn nằm trong HTTP readiness budget |

### 8.1. Đừng tăng timeout vô hạn

Nếu 60 giây chưa ready, kiểm:
1. Container có crash/restart không?
2. Docker daemon và image có được pull/build thành công không?
3. Service có bind đúng `0.0.0.0` và container internal port không?
4. `/ready` trả 404/401/503 hay timeout?
5. Có thiếu database/user/schema/credentials/migrations không?
6. Log regex có match đúng version, newline và buffering không?
7. Healthcheck command có sẵn trong image và có đủ quyền không?
8. CPU/memory trên CI có quá ít khiến init không tiến triển không?
9. Startup đang hợp lệ nhưng chậm hơn bình thường, hay đang bế tắc?

Chỉ tăng timeout khi quan sát thấy một initialization process hợp lệ cần thêm thời gian. Tăng lên vài phút không khắc phục sai keyspace/port/permission.

### 8.2. Startup attempts khác poll attempts

~~~java
container.withStartupAttempts(2);
~~~

Dùng khi có lý do retry **toàn bộ container launch**. HTTP wait strategy tự poll readiness trong một lần start; đó không phải cùng cơ chế. Retry launch có thể che bug cấu hình, nên luôn giữ logs và root cause khi fail.

### 8.3. Không dùng sleep bổ sung sau start

Sai:

~~~java
backend.start();
Thread.sleep(15000);
assertThat(client.fetch()).isNotNull();
~~~

Nếu backend đã ready sau 1 giây, test lãng phí 14 giây; nếu cần 20 giây, test vẫn fail. Sửa readiness contract và wait strategy. Với eventual consistency của index/replica, dùng **bounded polling ở đúng business assertion**, không lạm dụng startup wait cho một hành vi sau-write khác.

## 9. Spring Boot Actuator readiness probes

Với `spring-boot-starter-actuator` và cấu hình phù hợp:

~~~properties
management.endpoint.health.probes.enabled=true
management.endpoints.web.exposure.include=health,info
~~~

Ứng dụng có thể expose `/actuator/health/readiness`. Endpoint/path/management port có thể khác tùy configuration; cần kiểm thực tế. `HealthIndicator` custom cần được thiết kế sao cho readiness phản ánh các dependency **critical**, không phải chỉ web server lắng nghe.

Testcontainers snippet:

~~~java
GenericContainer<?> app = new GenericContainer<>(
        DockerImageName.parse("example/orders-service:1.0"))
        .withExposedPorts(8080)
        .waitingFor(Wait.forHttp(
                        "/actuator/health/readiness")
                .forPort(8080)
                .forStatusCode(200)
                .withStartupTimeout(Duration.ofMinutes(2)));
~~~

Đây là snippet cho một image đã có Actuator, **không** phải phần của Python lab. Nếu readiness báo DOWN/OUT_OF_SERVICE và trả 503 trong startup, wait sẽ tiếp tục; nếu 404 cần kiểm endpoint exposure/context path, nếu 401 cần auth đúng, không tùy tiện chấp nhận 401 là ready.

**Liveness không phải readiness**: tránh đưa DB ping vào liveness nếu DB lỗi ngắn gây restart loop; readiness có thể chuyển DOWN mà process vẫn sống để phục hồi.

## 10. One-shot migration jobs

### 10.1. Daemon khác batch job

Một database server là daemon: mong đợi process running liên tục. Một container chạy Flyway/CLI migration là **one-shot**: thành công khi exit 0 sau khi hoàn tất. Nếu dùng default is-running startup check, một process exit nhanh có thể bị coi là startup failure dù đúng contract.

Testcontainers có `OneShotStartupCheckStrategy` cho loại container này. Chỉ kiểm exit code là chưa đủ khi business requirement là schema thay đổi: sau job, dùng SQL/JDBC query kiểm schema version, table/index đúng.

### 10.2. Vì sao “migrations complete” log chưa đủ?

Một migration job có thể in log hoàn tất một bước rồi fail ở commit hoặc bước tiếp. Kiểm exit code 0; kiểm database state bằng transaction/query thật. Nếu error, hiển thị logs, không set `Wait.forLogMessage(".*Migration.*")` rồi coi như thành công.

### 10.3. Khi app phụ thuộc migration job

Đảm bảo migration job hoàn tất trước khi application được coi là ready. Nếu dùng Testcontainers `dependsOn`, dependency phải có chính startup check/wait contract phù hợp. Không lấy port mở của database làm bằng chứng migrations đã xong.

## 11. Cách xác minh dịch vụ **thực sự** dùng được

### 11.1. Readiness endpoint vẫn có thể báo sai

Một endpoint `/ready` trả 200 vì JVM lên có thể bỏ qua những lỗi:
- App đang đọc sai database/tenant/schema.
- Topic bắt buộc chưa được provision.
- Credentials chỉ cho connect, không cho query/insert.
- Index search chưa build, dù cluster HTTP đã ready.
- Cache warmup chưa hoàn tất nhưng endpoint phụ thuộc vào cache.

Vì vậy sau `start()`, phải gọi operation đại diện cho contract:
- JDBC: `SELECT 1` và query bảng/schema cần thiết.
- Redis: `PING`, hoặc SET/GET trên key test.
- Kafka: metadata topic, publish+consume test message.
- HTTP: route thật, status, response JSON/headers.
- Search: index, query, expected result.

### 11.2. Business assertion nên kiểm cả body

Nếu chỉ assert HTTP 200, một proxy/default route có thể trả HTML 200. Lab kiểm `"id":"42"` và `"status":"AVAILABLE"` để chứng minh routing + logic tối thiểu, không chỉ port hoặc homepage.

### 11.3. Readiness có thể đổi sau startup

Một backend có thể healthy lúc probe và fail ngay sau. Production client cần handling cho runtime errors. Testcontainers không cung cấp đảm bảo vĩnh viễn; trong tests, phân biệt startup race với resilience scenario chủ động fault injection.

### 11.4. Không tạo side effect trên production bằng readiness probe

Readiness nên idempotent và ít tốn tài nguyên. Nếu business probe phải INSERT/POST, dùng test-only namespace, synthetic identity, cleanup/ephemeral database. Không ping bằng cách tạo đơn hàng thật hoặc gọi payment provider thật mỗi giây.

## 12. Troubleshooting theo loại lỗi

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Docker không được phát hiện | Docker daemon/permission/remote context | Kiểm Docker runtime và Testcontainers environment |
| Pull image fail | Registry/auth/network/tag không tồn tại | Pin image và kiểm quyền registry |
| Process exit 1 | Invalid command/config/credential | Startup logs, entrypoint, env |
| TCP wait timeout | Bind sai interface/port | `withExposedPorts`, bind `0.0.0.0` |
| TCP PASS, HTTP 503 | Service chưa initialized | `Wait.forHttp("/ready")` đúng contract |
| HTTP 404 | Wrong context path/endpoint | Kiểm route, Actuator exposure |
| HTTP 401/403 | Readiness endpoint cần auth | Header/basic auth hoặc chính sách readiness |
| HTTP 200 nhưng body mismatch | Response chưa `READY` | `forResponsePredicate` đúng status payload |
| Log wait không kết thúc | Regex sai, log không flush, wording đổi | Kiểm raw logs và regex newline |
| HEALTHCHECK luôn unhealthy | Dockerfile health command sai hoặc service chưa ready | `docker inspect` health state/log |
| Test PASS rồi business call fail | Readiness quá yếu/sai data | Business query/credentials/schema |
| Docker tests skipped | `disabledWithoutDocker=true` | CI require tests executed, không coi skip là PASS |
| Context cached nhưng container đã stop | JUnit/Spring lifecycle mismatch | Spring-managed container bean/context isolation |
| CI đôi khi fail, local luôn PASS | Timing/CPU/memory/parallelism | Ghi startup progression, readiness polls, logs |
| Container chạy nhưng wrong tenant | Cấu hình namespace/schema/bucket sai | Assert identifier và query thật |
| One-shot process exit 0 nhưng wait fail | Dùng daemon startup check cho job | One-shot strategy và kiểm effects |

### 12.1. Đọc logs và error cause

~~~java
String output = backend.getLogs();
System.out.println(output);
~~~

Snippet chỉ phục vụ debug: log có thể chứa credentials/PII nên cần scrub/giới hạn. Giữ exception cause `ContainerLaunchException` và nội dung cuối của HTTP readiness response khi có thể.

Docker CLI khi container còn chạy:

~~~bash
docker ps -a
docker logs <container-id>
docker inspect <container-id>
~~~

Trong lệnh trên, `<container-id>` là tham số thay bằng ID thực. Testcontainers có thể stop container khi class hoàn tất; nếu không còn container để inspect, dùng logs thu trong test hoặc chạy targeted debugging session.

### 12.2. Protocol-level kiểm Redis

~~~java
Container.ExecResult ping =
        redis.execInContainer("redis-cli", "PING");

assertThat(ping.getExitCode()).isZero();
assertThat(ping.getStdout().trim()).isEqualTo("PONG");
~~~

Đây là snippet cần Redis container, imports và AssertJ; không phải file trong runnable lab. Command chạy **bên trong** container nên không chứng minh host-to-container networking hoàn toàn đúng; nếu networking là contract, thêm check từ test JVM/client thật.

### 12.3. Nếu sai readiness contract, đừng chữa bằng sleep

Một readiness endpoint cố tình always-200 dù còn migrations phải được sửa ở app. Nếu log “started” chưa phải “ready”, chờ log tương ứng hoặc probe mạnh hơn. Timeout lớn và retry vô hạn chỉ che lỗi, làm CI chậm.

## 13. Một số anti-pattern cần tránh

### 13.1. Đợi TCP cho API đang migrate

Cổng 8080 có thể mở trước khi business endpoint usable. Chọn `/ready` hoặc query/schema check.

### 13.2. Dùng /live như /ready

Liveness UP không chứng minh dependencies available. Phân biệt rõ hai endpoint.

### 13.3. Chấp nhận HTTP 200 bất kể body

Nếu service trả 200 với `STARTING`, `forResponsePredicate` nên kiểm trạng thái.

### 13.4. Log regex chỉ match “Starting”

Đợi “Ready” sau init chứ không phải “Starting”; vẫn kiểm business operation.

### 13.5. HEALTHCHECK không có trong image

`Wait.forHealthcheck()` yêu cầu Docker HEALTHCHECK thực sự, không tự suy ra từ endpoint.

### 13.6. Dùng localhost:8080 từ host JVM

Docker mapped port ngẫu nhiên. Dùng `getHost()` và `getMappedPort`.

### 13.7. Dùng host mapped port giữa hai containers

Trong cùng Docker network, dùng alias và internal port, tránh nhầm địa chỉ.

### 13.8. Sleep cố định sau start

Không có nghĩa readiness, làm test chậm/flaky. Đợi condition.

### 13.9. @ServiceConnection bị coi là migration tool

Connection details đúng không đồng nghĩa schema/index/topic đã được tạo.

### 13.10. Bắt mọi HTTP status là ready

HTTP 401/302 có thể là authentication/redirect bug; chỉ chấp nhận nếu contract xác định như vậy.

### 13.11. Kết hợp @Container và cached Spring context tùy tiện

Context có thể giữ client tới container đã stop. Cân nhắc Spring-managed container lifecycle.

### 13.12. Skip Docker tests nhưng tuyên bố integration PASS

Test status skipped khác test success. CI kiểm số tests thực sự chạy.

### 13.13. One-shot exit 0 bị coi là daemon crash

Dùng startup check phù hợp cho jobs, kiểm exit code và effects.

### 13.14. Readiness quá phụ thuộc optional system

Nếu service có thể degraded mode, readiness contract phải phản ánh phần chức năng critical, không gây cascading failure vì dependency không bắt buộc.

### 13.15. Kiểm endpoint nhưng không kiểm business output

Wait strategy chỉ là khởi đầu; thêm GET/SQL/protocol assertions.

## 14. Bài tập

1. Chạy `PortIsNotReadinessTest` và giải thích port mở nhưng `/ready=503`.
2. Thay `Wait.forListeningPort()` bằng `Wait.forHttp("/ready")` cho manual mode, không bật admin, quan sát startup timeout có chủ đích.
3. Dùng auto mode để HTTP wait nhận 200/READY sau init.
4. Thử predicate đòi body `NEVER_READY` và xem error khi timeout.
5. Thử log wait chỉ đợi `LISTENING`; lý giải vì sao nó yếu hơn `SERVICE_READY`.
6. Thêm endpoint `GET /api/orders/99` có dữ liệu khác và assert đúng ID/status.
7. Dùng `@DynamicPropertySource` và assert Spring bean nhận actual mapped host/port.
8. Tạo Dockerfile HEALTHCHECK gọi `/ready`, kiểm `Wait.forHealthcheck()`.
9. Kết hợp log và HTTP trong `WaitAllStrategy`, phân tích timeout khi một tín hiệu fail.
10. Khởi động Redis container và gọi `redis-cli PING` sau port wait.
11. Dùng PostgreSQLContainer, chạy migration và query bảng thật, chứng minh JDBC ready không thay schema ready.
12. Mô phỏng one-shot migration command exit 0 rồi verify schema, và một case exit 1.
13. Với Spring Actuator, bật `/actuator/health/readiness` và đặt HTTP wait chính xác.
14. Thử hard-code port 8080, chạy Docker Desktop/remote runner để thấy vì sao sai.
15. Đọc Surefire report khi Docker bị tắt: phân biệt skipped integration tests với PASS.
16. Tổ chức hai @SpringBootTest classes dùng cùng container, đánh giá context caching và lifecycle.
17. Cấu hình readiness endpoint có auth, kiểm status 401 và chứng minh request có credential hợp lệ mới làm việc được.
18. Định nghĩa P95/P99 startup budgets và chọn `withStartupTimeout` có cơ sở.
19. Với container-to-container, xây một Network alias và đổi từ host mapped port sang internal port.
20. Thêm business assertion sau readiness để phát hiện sai schema/namespace dù endpoint báo UP.

## 15. Checklist trước khi merge

- [ ] Phân biệt Docker created/running, TCP listening và application readiness?
- [ ] StartupCheckStrategy đúng daemon hay one-shot job?
- [ ] Wait strategy mạnh đủ cho operation cần test?
- [ ] Không nhầm liveness và readiness?
- [ ] HTTP wait kiểm port/path/status/body nếu cần?
- [ ] Không dùng `Thread.sleep` làm điều kiện readiness?
- [ ] Log regex match đúng “ready” sau init, không chỉ “starting”?
- [ ] Docker image có HEALTHCHECK trước khi dùng `Wait.forHealthcheck`?
- [ ] Timeouts connect/read/wait/test đều hữu hạn và hợp lý?
- [ ] Không tăng timeout vô hạn để che config bug?
- [ ] Host và mapped port lấy từ Testcontainers?
- [ ] Network alias/internal port dùng đúng cho container-to-container?
- [ ] Có business-level smoke check sau container.start()?
- [ ] Schema/index/topic/seed data đã thực sự sẵn sàng?
- [ ] Spring Boot @DynamicPropertySource/@ServiceConnection đúng trường hợp?
- [ ] Container lifecycle phù hợp Spring context caching?
- [ ] Docker CI image version/resource/permission được quản lý?
- [ ] Không dùng production credentials, data hoặc external side effects?
- [ ] Có logs/cause/health status cho timeout diagnostics?
- [ ] CI không coi skipped Docker tests là integration PASS?
- [ ] README code và lệnh Maven được chạy xác nhận trong build pipeline?

**Kết luận:** Container `RUNNING`, port `LISTENING` và service `READY` là ba trạng thái khác nhau. Startup check kiểm lifecycle, còn wait strategy kiểm điều kiện usable. Với HTTP API khởi tạo chậm, hãy đợi `/ready` trả status/payload đúng, log readiness đáng tin hoặc Docker HEALTHCHECK; sau đó kiểm request nghiệp vụ thật. Kết nối Spring Boot bằng mapped address động, quản lý container lifecycle đúng và giữ timeouts bounded để integration tests nhanh, ổn định và có giá trị chẩn đoán.

## 16. Tài liệu tham khảo

- Testcontainers Java — Startup and Wait Strategies: https://java.testcontainers.org/features/startup_and_waits/
- Testcontainers Java — JUnit Jupiter quickstart: https://java.testcontainers.org/quickstart/junit_5_quickstart/
- Testcontainers Java — Manual container lifecycle: https://java.testcontainers.org/test_framework_integration/manual_lifecycle_control/
- Testcontainers Java 1.21.x — HttpWaitStrategy API: https://javadoc.io/static/org.testcontainers/testcontainers/1.21.4/org/testcontainers/containers/wait/strategy/HttpWaitStrategy.html
- Testcontainers Java 1.21.x — WaitAllStrategy API: https://javadoc.io/static/org.testcontainers/testcontainers/1.21.4/org/testcontainers/containers/wait/strategy/WaitAllStrategy.html
- Spring Boot 3.5 — Testcontainers, Service Connections and bean lifecycle: https://docs.spring.io/spring-boot/3.5/reference/testing/testcontainers.html
- Spring Boot 3.5 — Testing Spring Boot Applications: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
- Spring Boot 3.5 — Actuator endpoints and Kubernetes probes: https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html
- Docker — Dockerfile HEALTHCHECK: https://docs.docker.com/reference/dockerfile/#healthcheck
- Docker — Testcontainers lifecycle for Java: https://docs.docker.com/guides/testcontainers-java-lifecycle/
