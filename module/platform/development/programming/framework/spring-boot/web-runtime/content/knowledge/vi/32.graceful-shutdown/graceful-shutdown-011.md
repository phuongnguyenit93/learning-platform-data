# Kiểm chứng không mất yêu cầu khi triển khai thay phiên bản Spring Boot

## 1. Mục tiêu và ý nghĩa của “không mất yêu cầu”

Một hệ thống Spring Boot phục vụ traffic liên tục cần thay dần phiên bản v1 bằng v2 mà không ngắt giao dịch đang xử lý. Quy trình này thường gọi là rolling deployment hoặc rolling update. Dù Kubernetes báo Deployment rollout thành công và các Pods mới đều Ready, điều đó **không tự chứng minh** mọi HTTP request của người dùng đã hoàn tất.

Các điểm rơi điển hình:

- Client mở connection tới Pod v1 ngay lúc load balancer chưa cập nhật endpoints đang terminating.
- Pod v1 đang xử lý HTTP request dài 5 giây nhưng bị SIGKILL trước khi trả response.
- POST đã ghi DB thành công, song TCP connection bị đóng trước khi HTTP 201 đến client.
- Client retry POST, hệ thống tạo hai đơn hàng vì thiếu idempotency.
- Worker đã ACK một message nhưng chưa COMMIT nghiệp vụ; Pod bị thay và message không được xử lý lại.
- SSE, WebSocket hoặc gRPC stream dài hàng giờ bị cắt lúc Pod cũ dừng.
- v2 báo Ready nhưng database migration hoặc shared-session format không tương thích với v1.

Vì thế cần phân biệt ít nhất bốn mục tiêu:

| Mục tiêu | Bằng chứng cần có | Không đủ để chứng minh |
| --- | --- | --- |
| **Availability liên tục** | Các instance đủ capacity và endpoints Ready trong rollout | Chỉ thấy replicas=3 |
| **HTTP completion** | Client nhận response thành công hoặc xác định được request lỗi | Server nhận được request |
| **Eventual success** | Mọi logical request ID hoàn tất sau số retries cho phép, trong SLO | Chỉ chạy một cURL 200 |
| **Durable business correctness** | Mọi accepted operation được ghi bền; không có duplicate effect | Chỉ bật graceful shutdown |

Cần ghi rõ hai loại tiêu chí khác nhau:

1. **Zero transient errors:** client không gặp 502, 503, timeout hoặc connection reset dù không retry. Rất khó đảm bảo tuyệt đối trên mạng phân tán.
2. **Zero lost logical operations:** request có thể cần retry/reconciliation nhưng không bị mất và không tạo hiệu ứng trùng. Đòi hỏi idempotency, durable storage và kiểm chứng.

Không thể hứa zero loss trong mọi tình huống node crash, OOM, network partition, client timeout và hệ thống thanh toán ngoài. Nhưng có thể xây dựng **bằng chứng đủ mạnh cho một SLO cụ thể**, kiểm chứng theo từng lớp, theo request ID và theo durable business state.

## 2. Hai đường dữ liệu phải kiểm tra

~~~text
Client / Synthetic test
          |
          v
Ingress / Reverse proxy / API gateway
          |
          v
Kubernetes Service / EndpointSlice
          |
    +-----+------+
    |            |
    v            v
 Spring v1    Spring v2
   (old)        (new)
    |            |
    +------+-----+
           |
           v
       DB / broker
           |
           v
   Business effect durable
~~~

**Đường điều phối:** có chuyển request mới khỏi Pod đang terminating đúng lúc không? Có request nào vẫn bị định tuyến tới IP cũ sau khi Spring đã ngừng nhận connection không?

**Đường nghiệp vụ:** request đã được nhận có hoàn tất trong thời gian graceful? Nếu app đã COMMIT nhưng response mất thì client có thể tra trạng thái/retry an toàn không? Nếu worker bị kill, message được xử lý lại và side effect có idempotent không?

Spring Boot chủ yếu tham gia xử lý HTTP và lifecycle trong Pod. Kubernetes/LB tham gia traffic routing. Database và broker quyết định durability; client quyết định retry/reconnect. **Một flag không thể thay cả bốn phần**.

## 3. Dòng thời gian của rolling update và shutdown

~~~text
T0  Các Pods v1 Ready, đang phục vụ traffic
T1  Deployment tạo một Pod v2 thêm theo maxSurge
T2  v2 khởi động; liveness có thể UP, readiness chưa Ready
T3  v2 Ready, EndpointSlice/LB bắt đầu route traffic
T4  Controller chọn v1 Pod cũ để delete
T5  EndpointSlice đánh dấu Pod terminating, ready=false
T6  LB/gateway dần loại backend cũ khỏi traffic mới
T7  preStop hook chạy nếu có, trong grace period
T8  SIGTERM được gửi đến Java process
T9  Spring ApplicationContext đóng, graceful shutdown bắt đầu
T10 HTTP listener từ chối request mới, chờ in-flight requests
T11 Process dừng xong, Pod bị xóa
T12 Lặp lại cho tới khi toàn bộ Pods là v2
~~~

Từ T5 tới T6 có một khoảng thời gian **propagation delay**: EndpointSlice, kube-proxy, ingress controller và cloud load balancer không cập nhật tức thời trên cùng một đồng hồ. HTTP keep-alive có thể còn dùng connection cũ.

Trong Kubernetes, endpoint đang terminating có điều kiện `ready=false` để loại khỏi regular traffic, còn `serving` có thể phản ánh việc nó vẫn phục vụ kết nối cũ. Điều đó tạo cơ chế draining nhưng **không xác nhận mọi LB ngoài cluster lập tức tôn trọng**.

**Quan sát cần có:** mốc request cuối được route vào Pod v1, thời điểm Pod bắt đầu terminating, lúc gửi SIGTERM, số in-flight hoàn tất trước process exit và các 502/503/EOF từ ingress.

## 4. Spring Boot 3.3 graceful shutdown

Với Spring Boot 3.3.x, Java 17+:

~~~properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=25s
~~~

Graceful shutdown được hỗ trợ bởi Tomcat, Jetty, Undertow, Reactor Netty trong Servlet MVC hoặc reactive WebFlux. Nó diễn ra khi Spring `ApplicationContext` được đóng. Server ngăn request mới, cho requests đang tồn tại thời gian để hoàn tất.

Theo tài liệu **Spring Boot 3.3**:

- Tomcat, Jetty và Reactor Netty ngừng nhận request mới ở network layer.
- Undertow có thể nhận connection mới nhưng trả HTTP **503 Service Unavailable** ngay.
- HTTP persistent connection và HTTP/2 có thể ảnh hưởng cách request mới bị từ chối.
- Grace period không thể kéo dài vô hạn; khi timeout đạt ngưỡng, các lifecycle shutdown phases tiếp tục.

**Đừng nhầm** `spring.lifecycle.timeout-per-shutdown-phase` với total runtime shutdown timeout. Đây là timeout theo phase của Spring lifecycle, JVM còn các nguồn khác cần dừng. Kubernetes termination grace phải có ngân sách đủ cho `preStop`, Spring phases, logging/cleanup và một khoảng đệm đo được.

Cũng đừng áp default của Spring Boot các phiên bản mới hơn cho Boot 3.3. Trong bài học này, cấu hình `server.shutdown=graceful` được khai báo **tường minh**.

### Những điều Spring không tự bảo đảm

- Khi SIGKILL/OOM/node loss, Java shutdown hook không có cơ hội chạy.
- Kubernetes LB không gửi request mới tới old Pod sau SIGTERM.
- Một `@Async` task tự được đợi và ghi bền.
- SSE/WebSocket stream vô hạn được chuyển tiếp sang Pod khác.
- HTTP 200 đã được client thực sự nhận.
- POST được phép retry mà không gây duplicate effect.
- v1 và v2 cùng đọc/ghi được DB/schema/session.
- Message consumer không ACK trước business COMMIT.

Graceful shutdown là **nền tảng**, không phải một end-to-end exactly-once guarantee.

## 5. Kubernetes termination grace và preStop

Ví dụ một ngân sách lab:

~~~text
terminationGracePeriodSeconds = 50s
preStop sleep                =  8s
Spring graceful phase        = 25s
Other cleanup + margin       = 17s
~~~

`preStop` chạy **trước** khi kubelet gửi TERM đến container và vẫn tính vào `terminationGracePeriodSeconds`. Nếu hook mất 40 giây và tổng grace chỉ 45 giây, Spring có thể bị kill khi mới bắt đầu dừng. Kubelet gửi forcible kill khi grace hết hạn, không tự cộng thời gian preStop vào ngân sách.

Một `preStop sleep 8` có thể cho EndpointSlice/LB thời gian nhận thông tin Pod terminating trong khi app vẫn nhận/xử lý requests hợp lệ. Nhưng **sleep 8 không phải bằng chứng** propagation đã hoàn tất; đo theo ingress/cluster thật. Nếu hạ tầng có terminating endpoint draining tốt, có thể không cần preStop ngủ.

Lưu ý: hook dùng lệnh shell cần image có shell/sleep. Distroless containers thường không có, dẫn tới hook thất bại. Hook phải ngắn, idempotent nếu được gọi lại trong tình huống hiếm và không mở một endpoint drain public không bảo vệ.

## 6. Readiness, liveness và startup không phải cùng một probe

- **Readiness:** Pod có sẵn sàng nhận *new traffic*? Khi unready, Service không nên route regular traffic tới Pod đó.
- **Liveness:** Pod còn có thể tự phục hồi không, hay cần restart? Không để toàn bộ Pods bị restart khi một shared DB tạm thời lỗi.
- **Startup:** chờ app khởi động lâu mà không bị liveness probe giết quá sớm.
- **Terminating endpoint:** dù trước đó Ready, Pod được đánh dấu đang kết thúc để load balancers ngừng cấp request mới.

Spring Boot Actuator hỗ trợ các health groups:

~~~text
GET /actuator/health/readiness
GET /actuator/health/liveness
~~~

Khi Spring Boot app đã Ready, readiness thường trả HTTP 200 và `"status":"UP"`. Khi đang startup hoặc draining, trạng thái có thể thay đổi hoặc HTTP listener không còn nhận probes; không chỉ nhìn status thô rồi suy tất cả mốc đã đồng bộ.

Nếu management server dùng **cổng khác** với HTTP app, có nguy cơ management port vẫn khỏe trong khi main HTTP listener đã lỗi. Trong ví dụ bên dưới dùng actuator trên cùng port 8080. Production cân nhắc probes trên main port, giới hạn network exposure và không đưa secrets vào Actuator.

## 7. Dự án Java 17+ runnable để đo in-flight HTTP

Ta tạo một app Spring MVC nhỏ, có:

- `GET /work/{id}`: một request đọc, giữ handler trong 350–5000 ms và echo request ID + revision + node.
- `GET /state`: phiên bản, node và in-flight counter của **JVM hiện tại**.
- Actuator readiness/liveness.
- Spring graceful shutdown khi nhận SIGTERM.

Đây là lab kiểm thử **HTTP drainage**. Counter trong RAM không phải durable ledger và endpoint GET không mô phỏng business COMMIT. Các phần durability sẽ được giải thích sau.

### 7.1. Cấu trúc

~~~text
rollout-verifier/
├── settings.gradle
├── build.gradle
├── Dockerfile
└── src/
    ├── main/
    │   ├── java/demo/rollout/RolloutVerifierApplication.java
    │   └── resources/application.properties
    └── test/
        └── java/demo/rollout/RolloutVerifierTest.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'rollout-verifier'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

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
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

`src/main/resources/application.properties`:

~~~properties
server.port=8080
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=25s
management.endpoint.health.probes.enabled=true
management.endpoints.web.exposure.include=health,info,metrics

app.revision=${APP_REVISION:local}
~~~

Không bật `management.endpoint.shutdown.enabled=true` chỉ để thử SIGTERM; actuator shutdown endpoint thường không cần public exposure và có rủi ro bảo mật.

### 7.2. Java main + controller

`src/main/java/demo/rollout/RolloutVerifierApplication.java`:

~~~java
package demo.rollout;

import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@SpringBootApplication
public class RolloutVerifierApplication {
    public static void main(String[] args) {
        SpringApplication.run(RolloutVerifierApplication.class, args);
    }
}

@RestController
class RolloutController {
    private final AtomicInteger inFlight = new AtomicInteger();
    private final String revision;
    private final String node;

    RolloutController(@Value("${app.revision:local}") String revision) {
        this.revision = revision;
        this.node = System.getenv().getOrDefault("HOSTNAME", "local");
    }

    @GetMapping("/state")
    Map<String, Object> state() {
        return Map.of(
                "revision", revision,
                "node", node,
                "inFlight", inFlight.get());
    }

    @GetMapping(value = "/work/{id}",
                produces = MediaType.TEXT_PLAIN_VALUE)
    String work(@PathVariable long id,
                @RequestParam(defaultValue = "350") int delayMs)
            throws InterruptedException {

        if (id < 1 || delayMs < 0 || delayMs > 5000) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    "invalid request parameters");
        }

        inFlight.incrementAndGet();
        try {
            // LAB: giữ request thread trong khoảng được chỉ định.
            Thread.sleep(delayMs);
            return "id=" + id
                    + "|revision=" + revision
                    + "|node=" + node;
        } finally {
            inFlight.decrementAndGet();
        }
    }
}
~~~

**Cách đọc kết quả:**

- `id` là synthetic ID do client tạo; dùng so từng request. Đừng đưa PII/token vào path trong production.
- `revision` lấy từ environment variable APP_REVISION, giúp thấy request được xử lý bởi v1 hay v2.
- `node` có thể lấy từ Kubernetes HOSTNAME để tìm Pod.
- `inFlight` được tăng khi controller bắt đầu, giảm lúc phần xử lý kết thúc; nó **không chứng minh response đã qua mạng tới client**.
- `Thread.sleep` ở đây chỉ mô phỏng công việc đồng bộ, không phải hướng dẫn thiết kế production endpoint.
- Không dùng số inFlight trong RAM để đối chiếu kết quả business transactions sau Pod bị kill.

### 7.3. JUnit HTTP integration tests

`src/test/java/demo/rollout/RolloutVerifierTest.java`:

~~~java
package demo.rollout;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment =
        SpringBootTest.WebEnvironment.RANDOM_PORT)
class RolloutVerifierTest {

    @Autowired
    TestRestTemplate http;

    @Test
    void workEchoesRequestId() {
        ResponseEntity<String> response = http.getForEntity(
                "/work/42?delayMs=1", String.class);

        assertThat(response.getStatusCode())
                .isEqualTo(HttpStatus.OK);
        assertThat(response.getBody())
                .startsWith("id=42|revision=");
    }

    @Test
    void invalidDelayReturns400() {
        ResponseEntity<String> response = http.getForEntity(
                "/work/42?delayMs=9000", String.class);

        assertThat(response.getStatusCode())
                .isEqualTo(HttpStatus.BAD_REQUEST);
    }

    @Test
    void stateHasInFlightCounter() {
        ResponseEntity<String> response = http.getForEntity(
                "/state", String.class);

        assertThat(response.getStatusCode())
                .isEqualTo(HttpStatus.OK);
        assertThat(response.getBody())
                .contains("inFlight");
    }
}
~~~

Chạy với Java 17 và Gradle wrapper:

~~~bash
./gradlew test
./gradlew bootJar
~~~

PowerShell:

~~~powershell
.\gradlew.bat test
.\gradlew.bat bootJar
~~~

Nếu chưa có wrapper, dùng Gradle tương thích để tạo wrapper hoặc chạy Gradle đã cài. Test này kiểm tra HTTP routing; **không tự kiểm tra rollout, LB, SIGTERM hoặc side effects bền**.

## 8. Thử SIGTERM khi HTTP request vẫn xử lý

Chạy JAR:

~~~bash
APP_REVISION=v1 java -jar build/libs/rollout-verifier-1.0.0.jar
~~~

Terminal khác:

~~~bash
curl -i http://localhost:8080/actuator/health/readiness
curl -i http://localhost:8080/state
~~~

Sau đó bắt đầu request 5 giây:

~~~bash
curl -i "http://localhost:8080/work/42?delayMs=5000"
~~~

Trong khi nó đang chạy, gửi **SIGTERM** cho đúng Java PID (Linux: `kill -TERM PID`). Nếu SIGTERM đến **sau khi /work/42 đã vào controller**, Spring graceful shutdown có cơ hội giữ request ấy đến khi nhận response 200 trong khoảng 25 giây, rồi tắt listener/process.

**Thử lại hai lần:** lần một với SIGTERM sau khi đã nhìn thấy request in-flight; lần hai gửi SIGTERM trước khi request tới controller. Ở lần hai, request mới có thể bị từ chối và đây là trạng thái khác với việc đánh mất một request đang chạy.

Đừng dùng `kill -9` để test graceful: SIGKILL không chạy Java shutdown hooks. Một số nút Stop trong IDE không gửi đúng SIGTERM; dùng shell/container runtime. Nếu client nhận TCP reset, kiểm tra request có thực sự được dispatch trước SIGTERM hay không bằng request ID + timestamps/metrics.

### Kiểm chứng không phải chỉ là “server đã tắt đẹp”

Ngay cả khi app log có “graceful shutdown complete”, HTTP request đã COMMIT nhưng response mất vẫn có thể khiến client retry. Đối với GET read-only ở ví dụ này, retry thường an toàn. Đối với POST có side effect, cần cơ chế ở mục 12.

## 9. Docker ENTRYPOINT và truyền SIGTERM

`Dockerfile`:

~~~dockerfile
FROM eclipse-temurin:17-jre
WORKDIR /opt/app
COPY build/libs/rollout-verifier-1.0.0.jar app.jar
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/opt/app/app.jar"]
~~~

Build/run:

~~~bash
docker build -t rollout-verifier:v1 .
docker run --rm --name rollout-old \
  -e APP_REVISION=v1 -p 8080:8080 rollout-verifier:v1
~~~

Gửi stop request:

~~~bash
docker stop --time 40 rollout-old
~~~

Exec-form ENTRYPOINT giúp Java nhận stop signal trực tiếp. Nếu dùng shell wrapper `sh -c java ...` mà không `exec`/forward signal đúng, Java có thể không nhận SIGTERM kịp để chạy graceful. `docker stop --time 40` là ví dụ timeout của Docker CLI, không phải Kubernetes terminationGracePeriodSeconds.

Dự án production cần kiểm tra signal thực tế của container image/runtime và shutdown logs, không chỉ đọc Dockerfile.

## 10. Kubernetes Deployment + Service mẫu

Manifest sau dành cho cluster đã có image `rollout-verifier:v1` (push registry hoặc load vào kind/minikube nodes). Nó không tự build image; Dockerfile ở phần trước dùng để tạo image. File `k8s-rollout.yaml`:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: rollout-verifier
spec:
  replicas: 3
  minReadySeconds: 5
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  selector:
    matchLabels:
      app: rollout-verifier
  template:
    metadata:
      labels:
        app: rollout-verifier
    spec:
      terminationGracePeriodSeconds: 50
      containers:
        - name: app
          image: rollout-verifier:v1
          imagePullPolicy: IfNotPresent
          ports:
            - name: http
              containerPort: 8080
          env:
            - name: APP_REVISION
              value: "v1"
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: http
            periodSeconds: 2
            timeoutSeconds: 1
            failureThreshold: 2
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 10
            timeoutSeconds: 1
            failureThreshold: 3
          startupProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 2
            timeoutSeconds: 1
            failureThreshold: 30
          lifecycle:
            preStop:
              exec:
                command: ["/bin/sh", "-c", "sleep 8"]
---
apiVersion: v1
kind: Service
metadata:
  name: rollout-verifier
spec:
  selector:
    app: rollout-verifier
  ports:
    - name: http
      port: 80
      targetPort: http
~~~

### Vì sao chọn từng thiết lập?

| Thiết lập | Mục tiêu | Giới hạn |
| --- | --- | --- |
| `replicas: 3` | Có nhiều backends trong lúc thay | Không đảm bảo mỗi Pod đủ capacity |
| `maxSurge: 1` | Tạo Pod mới vượt desired một đơn vị | Cluster phải còn CPU/RAM và DB pool capacity |
| `maxUnavailable: 0` | Không chủ ý giảm số Pods Available dưới desired trong rollout chuẩn | Không bảo đảm không có 502 do race/network |
| `minReadySeconds: 5` | Pod mới Ready ổn định trước khi tính Available | Không tự kiểm chứng warm cache và API contract |
| `readinessProbe` | Gating request mới theo trạng thái readiness | Kubelet/EndpointSlice/ingress propagation không tức thì |
| `livenessProbe` | Restart khi process hỏng | Không dùng shared DB outage làm lý do restart cả fleet |
| `startupProbe` | Tránh liveness giết app khởi động chậm | Không thay readiness khi đã start |
| `terminationGracePeriodSeconds: 50` | Tổng thời gian trước forcible kill | Bao gồm cả preStop và shutdown |
| `preStop sleep 8` | Chờ LB biết terminating trước SIGTERM | Phải đo; không phải đảm bảo mọi LB cần đúng 8s |
| `imagePullPolicy: IfNotPresent` | Chạy được với image đã load vào local nodes | Production nên dùng immutable image digest/registry |

**Không đưa shell preStop vào distroless image** nếu không có `/bin/sh` hoặc `sleep`. Nếu môi trường đã hỗ trợ EndpointSlice terminating-aware draining tốt, preStop chờ có thể bỏ. Đừng sao chép các khoảng thời gian lab vào production nếu SLO/request durations khác.

### Chạy rollout

~~~bash
kubectl apply -f k8s-rollout.yaml
kubectl rollout status deployment/rollout-verifier --timeout=180s
kubectl get pods -l app=rollout-verifier -o wide
kubectl get endpointslice \
  -l kubernetes.io/service-name=rollout-verifier
~~~

Build/publish/load image v2. Trong **cùng manifest**, đổi `image: rollout-verifier:v1` thành `image: rollout-verifier:v2`, và `APP_REVISION` value từ `v1` thành `v2`. Sau đó:

~~~bash
kubectl apply -f k8s-rollout.yaml
kubectl rollout status deployment/rollout-verifier --timeout=180s
kubectl rollout history deployment/rollout-verifier
~~~

**Phải chạy tải trước và trong quá trình apply v2.** Nếu client test chỉ chạy sau rollout thành công, không đo được drain transition.

Cách nhìn EndpointSlice thay đổi và nguyên nhân Pod termination giúp tìm được khoảng traffic có thể bị route tới old Pod. Có thể chạy `kubectl get pods -w` và thu ingress logs trong cùng cửa sổ.

### Service DNS và lỗi port-forward

`kubectl port-forward service/rollout-verifier 8080:80` tiện cho debug nhưng thường forward vào **một Pod được chọn**, không đi qua toàn bộ Service load-balancing path. Không dùng kết quả port-forward làm bằng chứng LB chia requests giữa v1/v2.

Để kiểm chứng:
- Từ một test Pod trong cluster gọi `http://rollout-verifier.default.svc.cluster.local` khi namespace là `default`.
- Hoặc dùng staging ingress hostname thực của hệ thống.
- Đối chiếu thêm public edge traffic khi hạ tầng bên ngoài có cache/L7 connection pools.

HTTP keep-alive có thể giữ một connection tới old backend, nên cần đo multi-connection concurrency, per-node response fields và ingress upstream route.

## 11. Load generator Java 17 ghi rõ từng request ID

Chương trình độc lập `RolloutProbe.java` chạy ngoài Spring Boot, không cần thư viện bên ngoài. Nó gửi số lượng GET requests được yêu cầu, giới hạn parallelism, retry HTTP/connection failures có exponential backoff hữu hạn, ghi số IDs thành công, số IDs còn thiếu, số IDs đã retry và số responses theo revision.

**GET `/work` là read-only**, nên retry là phù hợp trong lab. Không tự copy chiến lược này vào POST đặt hàng/thanh toán trước khi có idempotency key.

~~~java
import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class RolloutProbe {
    record Outcome(
            int id, boolean success, int attempts,
            String revision, String detail) { }

    static Outcome call(HttpClient client, String base, int id)
            throws InterruptedException {

        String lastError = "not-started";

        for (int attempt = 1; attempt <= 5; attempt++) {
            HttpRequest req = HttpRequest.newBuilder()
                    .uri(URI.create(base + "/work/" + id
                            + "?delayMs=350"))
                    .timeout(Duration.ofSeconds(8))
                    .GET()
                    .build();

            try {
                HttpResponse<String> resp = client.send(
                        req, HttpResponse.BodyHandlers.ofString());

                if (resp.statusCode() == 200
                        && resp.body().startsWith("id=" + id + "|")) {
                    String revision = "unknown";
                    for (String part : resp.body().split("\\|")) {
                        if (part.startsWith("revision=")) {
                            revision = part.substring("revision=".length());
                        }
                    }

                    return new Outcome(
                            id, true, attempt, revision, "HTTP 200");
                }

                lastError = "HTTP " + resp.statusCode();
            } catch (IOException networkFailure) {
                lastError = networkFailure.getClass().getSimpleName();
            }

            if (attempt < 5) {
                long backoff = Math.min(1600L, 100L << (attempt - 1));
                Thread.sleep(backoff);
            }
        }

        return new Outcome(id, false, 5, "none", lastError);
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 3) {
            System.err.println(
                    "Usage: java RolloutProbe.java BASE_URL COUNT PARALLEL");
            System.exit(2);
        }

        String base = args[0].replaceAll("/+$", "");
        int count = Integer.parseInt(args[1]);
        int parallel = Integer.parseInt(args[2]);

        if (count < 1 || parallel < 1 || parallel > 100) {
            throw new IllegalArgumentException(
                    "COUNT >= 1 and 1 <= PARALLEL <= 100");
        }

        HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(3))
                .build();

        ExecutorService pool = Executors.newFixedThreadPool(parallel);
        List<Future<Outcome>> futures = new ArrayList<>();

        try {
            for (int i = 1; i <= count; i++) {
                final int requestId = i;
                Callable<Outcome> job =
                        () -> call(client, base, requestId);
                futures.add(pool.submit(job));
            }

            int ok = 0;
            int retried = 0;
            List<Integer> missing = new ArrayList<>();
            Map<String, Integer> byVersion = new HashMap<>();

            for (Future<Outcome> future : futures) {
                Outcome outcome = future.get();

                if (outcome.success()) {
                    ok++;
                    byVersion.merge(
                            outcome.revision(), 1, Integer::sum);
                } else {
                    missing.add(outcome.id());
                    System.err.println("FAILED id=" + outcome.id()
                            + " detail=" + outcome.detail());
                }

                if (outcome.attempts() > 1) {
                    retried++;
                }
            }

            System.out.println("planned=" + count);
            System.out.println("succeeded=" + ok);
            System.out.println("failed=" + missing.size());
            System.out.println("retriedIds=" + retried);
            System.out.println("revisions=" + byVersion);
            System.out.println("missingIds=" + missing);

            if (!missing.isEmpty()) {
                System.exit(1);
            }
        } finally {
            pool.shutdown();
        }
    }
}
~~~

### Chạy

Java 17 source-file mode cho phép:

~~~bash
java RolloutProbe.java http://localhost:8080 200 12
~~~

Từ test Pod có Java 17 trong cluster:

~~~bash
java RolloutProbe.java \
  http://rollout-verifier.default.svc.cluster.local 200 12
~~~

**Sample output mang tính minh họa**, không phải đầu ra cố định:

~~~text
planned=200
succeeded=200
failed=0
retriedIds=3
revisions={v1=92, v2=108}
missingIds=[]
~~~

Nếu chỉ có v1 hoặc chỉ có v2, có thể test không trùng lúc cả hai cùng chạy hoặc connections giữ lâu về một Pod; không vội kết luận lỗi. Cần tạo request liên tục xuyên rollout window và phân phối đủ connections.

### Kết quả nào là pass?

1. `planned` bằng số unique logical IDs được gửi.
2. `succeeded=planned` và `missingIds=[]` sau không quá 5 attempts.
3. Nếu `retriedIds>0`, đó là **transient failures đã được che bởi retry**, không thể nói zero errors. Phải ghi số và nguyên nhân.
4. `revisions` có v1 và v2 khi muốn chứng minh bài test chạm vào thời điểm overlap.
5. Client results phải khớp ingress access logs và server node/version logs.
6. **Đây chỉ là kiểm chứng GET response**, không phải bằng chứng không mất side effects của POST hoặc background jobs.

Trong môi trường có authentication, test client phải xác thực hợp lệ và không log raw credentials. Giới hạn COUNT/PARALLEL theo staging capacity; tránh tạo tải ngoài phạm vi được phép.

## 12. Trường hợp DB COMMIT xong nhưng response mất

~~~text
Client POST /orders, key K
       |
       v
Pod v1 executes INSERT and COMMIT
       |
       v
Pod receives SIGKILL / network resets
       |
       X response 201 chưa tới client
       |
       v
Client retries POST /orders with same key K
~~~

Nếu client không biết operation đã thành công, retry là cách phục hồi hợp lý, nhưng có nguy cơ tạo **hai orders** nếu server không có idempotency. Vì thế **graceful shutdown không thể giải quyết riêng chuyện retry an toàn**.

Một API mutation nên dùng:

- `Idempotency-Key` có entropy cao do client tạo, scope theo tenant/actor/action.
- Unique constraint ở durable DB.
- Request hash để cùng key nhưng payload khác bị từ chối.
- Transaction ràng buộc business effect và idempotency result nếu cùng database.
- Khi cùng key đang chạy, có concurrency conflict/wait/status semantics được định nghĩa.
- Khi retry sau COMMIT, trả về **cùng result/resource ID**, không thực hiện thêm effect.
- TTL/retention phải phù hợp retry window; key hết hạn không có bảo đảm dedup mãi mãi.
- External payment/email/webhook cần idempotency từ provider, outbox/inbox hoặc reconciliation riêng.

### SQL minh họa (không phải API hoàn chỉnh)

~~~sql
CREATE TABLE idempotency_records (
    tenant_id VARCHAR(64) NOT NULL,
    operation_type VARCHAR(64) NOT NULL,
    idempotency_key VARCHAR(128) NOT NULL,
    request_hash VARCHAR(64) NOT NULL,
    state VARCHAR(20) NOT NULL,
    response_status INT,
    response_body TEXT,
    PRIMARY KEY (tenant_id, operation_type, idempotency_key)
);

CREATE TABLE orders (
    order_id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL,
    amount_cents BIGINT NOT NULL
);
~~~

**Workflow**:

~~~text
authenticate + authorize principal and tenant
validate request and idempotency key
BEGIN TRANSACTION
    claim unique (tenant, operation, key)
    if existing result:
        compare request hash
        return recorded outcome or conflict
    insert business row exactly once
    record final result with same key
COMMIT
return result
~~~

Transaction isolation, unique-key conflict handling và concurrent retry phải được implement/test theo DB cụ thể. Đừng chỉ kiểm tra bằng một JVM `ConcurrentHashMap`; v1/v2 chạy trên **hai Pods** vẫn có thể cùng thực thi effect.

Nếu side effect là external payment, SQL transaction không rollback được charge bên ngoài. Cần provider idempotency key và reconciliation theo transaction ID; không tuyên bố exactly-once chỉ nhờ unique record local.

### 201, 202 và timeout

- **201 Created** sau DB commit: trạng thái được ghi bền, nhưng response vẫn có thể mất. Client tra lại bằng key.
- **202 Accepted** chỉ nên trả khi request/job đã được enqueue **bền** và client có operation ID để truy vấn tiến độ.
- **HTTP 503/504** không tự nói side effect đã/ chưa COMMIT. Có thể do gateway, network hoặc server sau commit.
- **Retry POST** phải dựa vào idempotency contract và backoff, không mặc định retry tùy tiện.

## 13. Background workers, Kafka, RabbitMQ và outbox

Rolling deployment thường khiến v1 và v2 tồn tại đồng thời. Ngoài HTTP handlers, app có thể chạy Kafka listeners, RabbitMQ consumers, scheduled jobs và async executors.

### Kafka/RabbitMQ consumer

Một flow an toàn cần:

1. Ngừng nhận message mới khi Pod được drain.
2. Hoàn tất các messages đang xử lý theo budget.
3. Chỉ ACK/commit offset **sau** khi business effect được ghi bền theo processing contract.
4. Nếu Pod chết trước ACK, broker được phép redeliver; handler phải **idempotent**.
5. Hạn chế retries/poison messages và có DLQ nếu cần.
6. Phân biệt Pod graceful exit với crash, rebalancing và zombie consumer.

**Kafka:** commit offset trước DB commit có thể gây mất effect; commit offset sau DB commit có thể bị replay sau crash. Cần transactional/idempotent design. **RabbitMQ:** ACK quá sớm gây cùng lỗi, unacked messages thường được redeliver khi consumer/connection chết.

### Outbox pattern

~~~text
HTTP request
    |
    v
DB transaction:
    update business state
    insert outbox event
COMMIT
    |
    v
outbox publisher -> broker -> idempotent consumer
~~~

Nếu Pod v1 bị dừng sau commit nhưng trước publish, outbox record còn trong DB và một publisher khác tiếp tục. Message có thể được gửi lại nếu publish acknowledgment mất, nên consumer vẫn phải deduplicate theo event ID.

### Scheduled jobs

`@Scheduled` không tự bảo đảm chỉ chạy một bản sao khi Deployment có nhiều replicas. Trong lúc v1/v2 overlap, cả hai có thể chạy job cùng lúc. Với nhiệm vụ chỉ chạy một lần, dùng distributed lease/leader election, dedicated worker/scheduler hoặc transactional claim trong DB.

### Async executor

`@Async` hoặc manually created `ExecutorService` không tự tạo durability. Nếu trả HTTP 202 rồi chỉ đặt tác vụ vào queue bộ nhớ, một Pod restart có thể làm mất nó. Quản lý lifecycle, bounded queue, shutdown/awaitTermination và durable jobs khi nghiệp vụ cần recover.

## 14. Long-lived connections: SSE, WebSocket, gRPC

| Loại kết nối | Vấn đề trong rollout | Phương án |
| --- | --- | --- |
| HTTP keep-alive | Reuse connection tới old Pod | Draining và client retry/idempotency |
| HTTP/2 | Nhiều streams trên cùng một connection | Transport GOAWAY/drain support, stream lifetime |
| SSE | Một response mở hàng giờ | Last-Event-ID, durable event replay/resync |
| WebSocket | TCP session không thể chuyển Pod trực tiếp | Close/reconnect/reauth/resume |
| gRPC unary | RPC COMMIT nhưng response timeout | Idempotency + deadline/retry contract |
| gRPC streaming | Stream bị cắt giữa sự kiện | Checkpoint/resubscribe, sequence dedup |
| File upload | Request body nhận một phần | Resumable upload + checksum + cleanup |
| File download | Client chỉ nhận một phần | Range requests/ETag/checksum nếu hỗ trợ |

**Quan trọng:** WebSocket/SSE connection của v1 không tự “chuyển” sang process v2 khi Service endpoint đổi. Nếu stream có event quan trọng, phải có sequence ID và nguồn durable/replay. SSE `Last-Event-ID` không tự tạo log để replay; phía server phải thực thi.

Đừng kéo Spring graceful timeout thành hàng giờ chỉ vì có WebSocket. Thay bằng stream maximum lifetime, graceful close signal, client reconnect + resume, bounded per-client queues. Kiểm chứng gaps/duplicates từ durable source thay vì chỉ đếm số reconnections.

Response headers HTTP 200 đã gửi rồi không thể đổi thành 503 khi body bị cắt giữa chừng. Vì vậy access-log status 200 không chứng minh client đã nhận đầy đủ stream.

## 15. Version compatibility: v1 và v2 cùng tồn tại

Dù shutdown đúng, v1/v2 có thể lỗi khi dùng chung database, session, broker hoặc external APIs.

Checklist:

- **Schema expand/contract:** thêm cột/tables tương thích trước; đợi không còn v1 mới xóa cột cũ.
- **Session serialization:** HttpSession lưu tại JVM Pod cũ sẽ mất khi client đổi Pod; cân nhắc Spring Session shared store hoặc stateless design.
- **Auth keys/tokens:** v1/v2 phải verify được cùng issuer/signing key/cookie policy.
- **Cache format:** không để v2 ghi cache object mà v1 không deserialize được.
- **Message schemas:** producer v2 và consumer v1 vẫn đọc được events khi overlap.
- **API contracts:** v1/v2 chấp nhận payload từ clients cũ và mới theo compatibility policy.
- **Flyway/Liquibase:** tránh destructive migrations chạy ngay trong overlapping window.
- **Flags:** tránh bật tính năng chỉ v2 hiểu khi vẫn route vào v1.
- **Rollback:** nếu v2 đã ghi data không tương thích, rollback code v1 không tự đảo migration.

Một health probe trả UP không tự kiểm chứng sự tương thích này. Cần contract tests chạy qua cả hai revisions, DB migration tests, canary và rollback rehearsal.

## 16. Điểm kiểm chứng bằng logs và metrics

Một bảng evidence nên có:

| Trường | Tại sao |
| --- | --- |
| Synthetic request ID | So planned, succeeded, missing |
| Client attempt number | Đo số retries, không che errors |
| Client send/receive timestamps | Gắn vào rollout timeline |
| Client HTTP status/EOF/timeout | Phân biệt thành công và failure |
| Target revision/node | Biết v1 hay v2 đã xử lý |
| Ingress upstream IP/status | Tách lỗi LB khỏi origin |
| Spring handler start/completion | Phân biệt new request và in-flight |
| Durable operation ID/COMMIT time | Bằng chứng nghiệp vụ hoàn tất |
| Idempotency key/hash/result | Tìm duplicates và reconciliation |
| EndpointSlice terminating transition | Điểm Pod được rút khỏi routing |
| SIGTERM/shutdown start/end | Đo grace thời gian thực |
| Pod exit reason/code | Phân biệt graceful, OOM, SIGKILL |
| SSE event sequence/replay | Tìm gaps/duplicates sau reconnect |

Các metrics có ích: `http.server.requests` theo status/route/revision, in-flight requests, active connections, readiness failures, 502/503/504 ingress, shutdown duration, DB commit counts, queue consumer lag, retries, missing/duplicate logical IDs, SSE reconnect/event lag.

**Không đưa raw access tokens, session IDs, email hoặc high-cardinality request IDs vào Prometheus metric labels.** Request ID nên trong logs đã kiểm soát quyền/retention; metrics dùng route template, revision, pod, status và outcome.

### Chẩn đoán 502 tại thời điểm rollout

~~~text
Client ID=71 -> 502
    |
    v
Ingress upstream points to old Pod?
    | YES: connect refused after Pod stopping
    |      -> LB propagation/draining race
    |
    | NO: upstream responds slowly
           |
           v
    Spring handler started?
       | NO: proxy/connector/capacity issue
       | YES: DB committed?
                | YES: reconcile result and retry safely
                | NO: retry under contract/idempotency
~~~

Một 502 tại edge không nhất thiết xuất hiện trong origin logs. Một server-side HTTP 200 cũng không chứng minh client nhận đủ response. Vì vậy phải **đối soát end-to-end** từ client và DB.

## 17. Thiết kế acceptance gates

Trong một thử nghiệm staging, có thể chọn:

| Gate | Tiêu chí |
| --- | --- |
| Rollout | `kubectl rollout status` thành công và v2 Ready |
| Coverage | Load generator chạy trước, trong và sau v1→v2 |
| IDs | Planned logical IDs đúng, không thiếu trong test ledger |
| GET eventual success | `succeeded=planned`, `missingIds=[]` sau bounded retries |
| Transient errors | Báo rõ retries, 502/503/EOF/timeouts trong error budget |
| Revisions | Cả v1/v2 xuất hiện trong response/logs khi test overlap |
| Drain | Request đã dispatch trước SIGTERM có thời gian hoàn tất |
| Business operations | Durable committed unique IDs khớp accepted IDs |
| Duplicate effects | Mỗi idempotency key chỉ có một business effect |
| Async jobs | Queue/outbox có redelivery/recovery, không mất message |
| Streaming | Replay/resume không mất durable events |
| Compatibility | v1/v2 cùng truy cập DB/session/messages hợp lệ |
| Rollback | Khôi phục được route và data contract khi v2 lỗi |

**Không coi eventual success=100% là zero transient errors.** Nếu `retriedIds>0`, đã có failure cần ghi trong bài toán availability. Nếu GET test pass nhưng POST có duplicate charges, toàn bộ tiêu chí “không mất nghiệp vụ” vẫn không đạt.

## 18. Failure injection để xác định giới hạn của hệ thống

Chỉ thực hiện trong **staging/localhost được phép**, giới hạn tải và có rollback plan:

1. Rolling v1→v2 bình thường, so sánh IDs theo từng attempt.
2. Bỏ/giảm preStop rồi quan sát upstream connect resets ở ingress.
3. Đặt graceful timeout ngắn hơn request 5 giây, quan sát failures.
4. Gửi SIGTERM khi request đã được xác nhận đang xử lý.
5. Gửi SIGKILL cho một Pod: **không mong đợi graceful**, kiểm tra idempotent recovery.
6. Cho Pod mới readiness UP quá sớm, đo warm-up errors.
7. Ngắt DB tạm thời: liveness không nên kéo cả fleet restart.
8. Cắt response sau DB COMMIT, retry cùng idempotency key.
9. Hai Pods xử lý POST cùng key đồng thời, unique constraint phải ngăn double effect.
10. Queue consumer chết sau DB commit nhưng trước ACK; phải redeliver an toàn.
11. SSE reconnect trong lúc Pod thay, kiểm tra sequence gaps.
12. WebSocket reconnect/reauth/resume, không kỳ vọng TCP migration.
13. Thử rollback khi schema có migration tương thích và khi có flag mới.
14. Kiểm tra tải tăng khi một Pod draining, DB pool và memory còn đủ không.

**SIGTERM là graceful test; SIGKILL/OOM/node loss là recovery test.** Chúng chứng minh những đặc tính khác nhau và không được gộp chung thành một kết luận.

## 19. Rollback và canary

Kubernetes Deployment RollingUpdate không tự định tuyến theo % traffic chính xác kiểu 1% canary. Muốn kiểm chứng theo các tỷ lệ, dùng ingress/service mesh/Argo Rollouts hoặc công cụ routing phù hợp.

Một quy trình:

1. Release v2 trên một phần traffic trong staging/canary.
2. Gửi synthetic read + idempotent write operations có correlation ID.
3. Đo error/retry/latency/DB state, cả v1 và v2.
4. Nếu gate pass, tăng dần traffic v2 và quan sát HPA/resource/queue lag.
5. Nếu gate fail, pause, reconcile dữ liệu, rollback theo plan.

Lệnh rollback Deployment khi đã có quyền:

~~~bash
kubectl rollout history deployment/rollout-verifier
kubectl rollout undo deployment/rollout-verifier
kubectl rollout status deployment/rollout-verifier --timeout=180s
~~~

Rollback **cũng là một transition** cần draining/availability tests. Nó không tự đảo ngược schema hoặc side effects v2 đã ghi; đừng rollback sau destructive DB migration mà chưa có data compatibility plan.

## 20. Những anti-pattern cần loại bỏ

| Anti-pattern | Rủi ro | Cách làm |
| --- | --- | --- |
| Chỉ xem `kubectl rollout status` | Không thấy mất HTTP/DB effects | Load generator + request IDs + durable reconciliation |
| Chỉ bật `server.shutdown=graceful` | Không xử lý LB propagation | EndpointSlice/readiness + preStop khi đo thấy cần |
| preStop 10s và termination grace 10s | Không còn thời gian Spring dừng | Cộng preStop + graceful + margin |
| maxUnavailable=0 nghĩa không 502 | LB/network races vẫn có | End-to-end edge/client metrics |
| Dùng port-forward Service làm test LB | Thường chọn một Pod | Gọi actual Service DNS/Ingress |
| Test chỉ trước hoặc sau rollout | Bỏ qua thời điểm nguy hiểm | Gửi traffic liên tục xuyên rollout |
| Retry POST tùy tiện | Duplicate effects | Idempotency + DB unique constraint |
| 202 trước khi job durably enqueued | Mất job khi Pod restart | Transactional enqueue/outbox |
| Kafka ACK trước DB commit | Mất event effect khi crash | Commit/ACK sau durability + dedup |
| @Scheduled trên mọi Pod | Double execution trong overlap | Distributed leader/lease/job queue |
| App counter RAM làm nguồn truth | Counter mất khi Pod chết | Durable operation ledger |
| Bỏ qua 502 vì retry đã 200 | Che transient errors | Report attempts, retries, error SLO |
| SIGKILL để kiểm tra graceful | Shutdown hooks không chạy | SIGTERM cho graceful, SIGKILL cho recovery |
| Dừng long SSE bằng tăng timeout vô hạn | Rollout treo, quá resource budget | Reconnect, replay, TTL |
| Liveness kiểm tra DB shared | Restart storm khi DB lỗi | Readiness/circuit breakers theo mục đích |
| Test một Pod đơn lẻ | Không bắt gặp old/new compatibility | Multi-replica overlap |
| Public drain endpoint | Có thể bị lạm dụng làm Pod unready | Protected control-plane orchestration |
| Rollback code sau destructive schema migration | v1 không đọc được data | Expand/contract và rollback rehearsal |

## 21. Checklist production trước khi chốt “không mất yêu cầu”

- [ ] Đã định nghĩa logical request, HTTP attempt, durable operation và error budget?
- [ ] Đã bật graceful theo đúng Spring Boot version và đo SIGTERM thực?
- [ ] Container ENTRYPOINT truyền đúng stop signal tới JVM?
- [ ] Termination grace đủ preStop + measured shutdown + margin?
- [ ] maxSurge/maxUnavailable/replicas và cluster resources đủ capacity?
- [ ] v2 readiness chỉ UP khi warm-up và dependencies cần thiết đã sẵn sàng?
- [ ] Liveness không restart toàn fleet do shared dependency outage?
- [ ] EndpointSlice terminating và external LB drain đã được đo?
- [ ] Client load test có unique IDs, per-attempt errors/retries và revisions?
- [ ] Request đã bắt đầu trước SIGTERM được theo dõi đến response/client receipt?
- [ ] POST side effect có durable idempotency và conflict/reconcile API?
- [ ] Queue consumer ACK/offset và background jobs có shutdown recovery?
- [ ] SSE/WebSocket/gRPC có reconnect/resume và event sequence gap checks?
- [ ] Shared DB schemas, session store, cache, messages tương thích v1/v2?
- [ ] Có kiểm chứng cả lỗi graceful và SIGKILL/node loss riêng?
- [ ] Có logs/metrics từ ingress, Pod lifecycle, Spring và durable store?
- [ ] Có canary/rollback plan không làm mất data hoặc nhân đôi nghiệp vụ?
- [ ] Có runbook pause rollout, điều tra missing IDs và reconcile operations?

## 22. Câu hỏi tự kiểm tra

**1.** `server.shutdown=graceful` có chắc ngăn mọi HTTP 502 khi rolling update?

**Đáp án:** Không. LB có thể giữ endpoint cũ, clients giữ keep-alive hoặc node có thể chết. Cần draining và kiểm chứng end-to-end.

**2.** preStop sleep 8s có được cộng thêm ngoài terminationGracePeriodSeconds không?

**Đáp án:** Không. Hook ăn vào cùng termination grace, trước SIGTERM.

**3.** Readiness và liveness khác nhau thế nào?

**Đáp án:** Readiness quyết định nhận request mới; liveness quyết định có nên restart instance. Không đưa shared DB outage vào liveness một cách máy móc.

**4.** maxUnavailable=0 đã chứng minh không mất yêu cầu chưa?

**Đáp án:** Chưa. Nó chỉ kiểm soát Pod availability trong rollout, không chứng minh clients nhận responses hoặc DB commits.

**5.** Vì sao phải gửi GETs xuyên qua quá trình apply v2?

**Đáp án:** Chỉ khi traffic trùng cửa sổ draining/overlap mới có cơ hội phát hiện failures do đổi endpoints.

**6.** Test có 200/200 IDs thành công sau retry nhưng 3 IDs phải retry có phải zero transient errors?

**Đáp án:** Không. Eventual success pass, nhưng đã có transient failures phải điều tra.

**7.** Khi POST đã COMMIT mà response mất, client nên làm gì?

**Đáp án:** Reconcile/truy vấn theo idempotency key hoặc retry **cùng key** theo contract, tránh duplicate effect.

**8.** API trả 202 rồi chỉ enqueue job vào memory có đảm bảo không mất job khi Pod stop không?

**Đáp án:** Không. Accepted cần durable queue/outbox trước khi xác nhận.

**9.** SIGKILL có chạy Spring graceful shutdown hook không?

**Đáp án:** Không. SIGKILL dùng để test crash recovery/idempotency, không phải graceful shutdown.

**10.** SSE có Last-Event-ID là tự resume an toàn?

**Đáp án:** Không. Server phải có durable event log và replay/resync logic theo ID.

**11.** V1 và v2 dùng chung DB có thể gây lỗi dù graceful đúng không?

**Đáp án:** Có. Schema/session/message compatibility là bắt buộc trong giai đoạn đồng tồn tại.

**12.** kubectl port-forward Service có chứng minh HTTP requests được phân phối đều qua Pods không?

**Đáp án:** Không. Nó thường forward tới một Pod; test qua actual Service/Ingress.

## 23. Nguồn chính thức để đối chiếu

- [Spring Boot 3.3 — Graceful Shutdown](https://docs.spring.io/spring-boot/3.3/reference/web/graceful-shutdown.html): config grace, cách server nhận/từ chối requests mới.
- [Spring Boot 3.3 — Actuator Endpoints and Kubernetes Probes](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html): readiness, liveness, lifecycle và probes.
- [Kubernetes — Deployments](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/): RollingUpdate, maxSurge, maxUnavailable, minReadySeconds.
- [Kubernetes — Pod Lifecycle](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/): SIGTERM, SIGKILL, termination grace và EndpointSlice terminating.
- [Kubernetes — Container Lifecycle Hooks](https://kubernetes.io/docs/concepts/containers/container-lifecycle-hooks/): preStop hook chạy trước TERM và tính trong grace period.
- [Kubernetes — Endpoint Termination Flow](https://kubernetes.io/docs/tutorials/services/pods-and-endpoint-termination-flow/): ready, serving, terminating states và draining.
- [Spring Framework — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html): DB transaction boundaries và durability.
- [Spring Framework — SmartLifecycle](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html): lifecycle của managed beans.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): safe/idempotent HTTP operations, status semantics và retries.
- [Spring Session Reference](https://docs.spring.io/spring-session/reference/): shared sessions qua nhiều Pods.
- [Spring for Apache Kafka Reference](https://docs.spring.io/spring-kafka/reference/): consumer lifecycle, offset/ACK và transactional patterns.

**Kết luận:** kiểm chứng không mất yêu cầu khi thay phiên bản Spring Boot nghĩa là **đo traffic xuyên rollout, phân biệt requests đã bắt đầu với requests mới, xác minh draining và client receipts, rồi đối chiếu durable business state**. Graceful shutdown, readiness, Kubernetes rollingUpdate và preStop là lớp điều phối; idempotency, outbox/queue recovery, version compatibility và retry có kiểm soát mới giúp giữ đúng nghiệp vụ khi connection hay Pod thật sự bị mất.
