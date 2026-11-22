# Mô phỏng phụ thuộc ngoài lỗi, probe chuyển trạng thái và hệ thống xuất dữ liệu gián đoạn

## 1. Ba đường lỗi cần phân biệt

Một ứng dụng có thể còn trả lời HTTP khi phụ thuộc bên ngoài không truy cập được, khi một bản sao đang từ chối nhận tải, hoặc khi bộ thu dữ liệu giám sát ngừng hoạt động. Ba tình huống này cần ba kết luận khác nhau. Chỉ kiểm tra `/actuator/health` trả 200 trong trạng thái bình thường chưa cho biết hệ thống sẽ phản ứng thế nào khi gặp lỗi.

Bài này xây dựng thí nghiệm theo chuỗi **bình thường → gây lỗi → quan sát → gỡ lỗi → xác nhận phục hồi**. Ta kiểm tra đồng thời mã HTTP, trạng thái health, khả năng xử lý yêu cầu và dữ liệu thực sự đi qua bộ xuất metric. Ví dụ dùng Spring Boot 3.3.13, Java 17+ và JUnit 5; có thể chạy bằng JDK 21.

| Khái niệm | Câu hỏi cần trả lời | Bằng chứng |
| --- | --- | --- |
| Phụ thuộc ngoài | Dịch vụ được gọi có trả lời đúng và đúng hạn không? | Lỗi HTTP, quá hạn hoặc lỗi kết nối được xử lý đúng |
| Kiểm tra khả năng sống (liveness probe) | Bản sao ứng dụng có còn ở trạng thái hoạt động hợp lệ không? | Nhóm `liveness` và `LivenessState` |
| Kiểm tra sẵn sàng (readiness probe) | Bản sao có nên nhận yêu cầu mới không? | Nhóm `readiness` và `ReadinessState` |
| Bộ xuất dữ liệu (exporter) | Dữ liệu đo lường có đi ra ngoài ứng dụng không? | Lần gửi, nội dung gửi và kết quả phía bộ thu |
| Phục hồi | Sau khi lỗi hết, hệ thống có hoạt động lại đúng không? | Thực hiện lại hành động và quan sát kết quả mới |

`HealthIndicator` tạo kết quả health; nhóm health tổng hợp các kết quả được cấu hình. `ApplicationAvailability` lưu trạng thái sẵn sàng/khả năng sống. Micrometer đảm nhiệm đường ghi nhận và xuất metric. Các cơ chế này liên quan nhưng không tự động trở thành một trạng thái duy nhất.

## 2. Chọn chính sách trước khi viết assertion

### 2.1. Phụ thuộc lỗi không đồng nghĩa bản sao cần khởi động lại

Không đưa cơ sở dữ liệu, API ngoài hoặc bộ thu giám sát vào liveness chỉ vì muốn phát hiện lỗi nhanh. Khởi động lại ứng dụng thường không sửa được dịch vụ ngoài. Nếu mọi bản sao cùng kiểm tra một phụ thuộc qua liveness, một sự cố chung có thể dẫn tới khởi động lại hàng loạt. Spring Boot mặc định không tự thêm các health indicator khác vào hai nhóm probe; đưa một phụ thuộc vào readiness phải là lựa chọn có chủ đích. [Nhóm probe của Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes).

Với readiness, hãy hỏi: khi phụ thuộc này lỗi, bản sao còn phục vụ được phần công việc có ý nghĩa nào không?

- **Phụ thuộc bắt buộc, không có cách xử lý thay thế:** có thể đưa vào readiness, nhưng phải chấp nhận khả năng mọi bản sao cùng bị rút khỏi luồng yêu cầu khi một hệ thống chung hỏng.
- **Phụ thuộc tùy chọn hoặc có phương án thay thế:** kiểm thử phải chứng minh đường xử lý còn lại hoạt động; chính sách có thể chỉ đưa lỗi này vào health chẩn đoán.
- **Bộ thu dữ liệu giám sát:** trong bài này, xuất metric là chức năng hỗ trợ. Bộ thu lỗi không làm readiness/liveness thất bại. Yêu cầu nghiệp vụ đặc biệt khác cần chính sách và kiểm thử riêng.

Không có một lựa chọn phù hợp mọi ứng dụng. Phải ghi rõ chính sách trước rồi mới chọn kết quả mong đợi.

### 2.2. Trạng thái availability và định tuyến là hai tầng

Có thể phát `AvailabilityChangeEvent` với `ReadinessState.REFUSING_TRAFFIC` hoặc `ACCEPTING_TRAFFIC` trong kiểm thử. Sự kiện cập nhật thông tin availability; nó không mặc định đóng bộ lắng nghe HTTP hay cài bộ lọc chặn mọi URL. [Application availability](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html#features.spring-application.application-availability).

Trong Kubernetes, readiness thất bại làm bản sao không còn đủ điều kiện nhận lưu lượng thông thường qua Service. Liveness thất bại đủ ngưỡng có thể khiến container được khởi động lại. Kiểm thử Spring cục bộ không có kubelet nên không chứng minh việc rút định tuyến, khởi động lại container hay thời gian hội tụ; các hành vi đó cần kiểm thử trong cụm. [Cấu hình probe Kubernetes](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/).

### 2.3. Ma trận kết quả cho thí nghiệm

Bên dưới, `external` được đưa vào readiness; bộ thu OTLP không được đưa vào hai nhóm probe; các trạng thái availability khác bình thường.

| Tình huống | Readiness | Liveness | Bằng chứng bổ sung |
| --- | --- | --- | --- |
| Phụ thuộc trả 200 | 200 / `UP` | 200 / `UP` | Mốc đối chiếu trước lỗi |
| Phụ thuộc trả 503 | 503 / `DOWN` | 200 / `UP` | Bỏ lỗi rồi readiness trở lại 200 |
| Phụ thuộc trả quá chậm | 503 / `DOWN` | 200 / `UP` | Phép kiểm tra có giới hạn thời gian |
| Phát sự kiện từ chối tải | 503 / `OUT_OF_SERVICE` | 200 / `UP` | Gọi trực tiếp `/work` vẫn trả 200 trong test |
| Bộ thu OTLP trả 503 | 200 / `UP` | 200 / `UP` | Đã thử gửi nhưng phía nhận từ chối |
| Bộ thu trở lại 200 | 200 / `UP` | 200 / `UP` | Có payload mới chứa giá trị metric mới |

Mã HTTP và chuỗi trạng thái là hai assertion riêng. Mặc định `DOWN` và `OUT_OF_SERVICE` được ánh xạ thành 503; nếu ứng dụng tùy chỉnh ánh xạ, phải kiểm tra theo hợp đồng thực tế. [Ánh xạ health sang HTTP](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.health.writing-custom-healthindicators).

## 3. Thiết kế lỗi có thể lặp lại

Dùng một máy chủ HTTP giả (stub) tại `127.0.0.1`, với cổng do hệ điều hành cấp:

- `/dependency` chuyển giữa trả 200, trả 503 và chờ lâu hơn thời hạn yêu cầu.
- `/v1/metrics` giải mã thông điệp OTLP, ghi nhận lần gửi rồi trả 200 hoặc 503 theo điều khiển.

Ứng dụng Spring chạy trên một cổng ngẫu nhiên khác. Test gọi endpoint Actuator qua HTTP thật. Gọi thẳng `HealthIndicator.health()` chỉ kiểm tra một phần logic; nó chưa chứng minh nhóm health, đường dẫn và mã HTTP được cấu hình đúng.

Giữ bốn nguyên tắc:

1. Một lỗi chính mỗi lượt để xác định nguyên nhân.
2. Có thời hạn phía máy khách để test không treo vô hạn. `HttpRequest.Builder.timeout(...)` đặt thời hạn nhận phản hồi cho yêu cầu. [JDK 21 HTTP request timeout](https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpRequest.Builder.html#timeout(java.time.Duration)).
3. Khôi phục trạng thái dùng chung sau mỗi test; đóng server, executor và registry sau khi dùng.
4. Luôn kiểm tra cả phục hồi. Chỉ chứng minh `UP → DOWN` có thể bỏ sót trạng thái kẹt hoặc bộ xuất không gửi lại.

`Thread.sleep(800)` trong ví dụ chỉ nằm ở máy chủ giả để tạo phản hồi chậm. Test không ngủ đoán lúc bộ xuất chạy; nó điều khiển từng lần xuất. Assertion ba giây là hàng rào chống treo, không phải cam kết rằng toàn bộ HTTP request kết thúc chính xác trong 250 ms.

## 4. Ví dụ chạy đầy đủ

Tạo một thư mục thí nghiệm độc lập với hai tệp sau. Không cần lớp `main`: cấu hình ứng dụng nằm ngay trong test. Không đưa endpoint điều khiển lỗi này vào mã production.

### 4.1. `pom.xml`

Spring Boot quản lý phiên bản thư viện. OTLP chỉ dùng trong test; `java.version=17` cho phép biên dịch theo Java 17 khi chạy bằng JDK 17 hoặc 21.

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent><groupId>org.springframework.boot</groupId><artifactId>spring-boot-starter-parent</artifactId><version>3.3.13</version><relativePath/></parent>
  <groupId>example</groupId><artifactId>actuator-failure-lab</artifactId><version>1.0.0</version>
  <properties><java.version>17</java.version></properties>
  <dependencies>
    <dependency><groupId>org.springframework.boot</groupId><artifactId>spring-boot-starter-web</artifactId></dependency>
    <dependency><groupId>org.springframework.boot</groupId><artifactId>spring-boot-starter-actuator</artifactId></dependency>
    <dependency><groupId>io.micrometer</groupId><artifactId>micrometer-registry-otlp</artifactId><scope>test</scope></dependency>
    <dependency><groupId>org.springframework.boot</groupId><artifactId>spring-boot-starter-test</artifactId><scope>test</scope></dependency>
  </dependencies>
</project>
```

### 4.2. `src/test/java/example/ActuatorFailureTest.java`

Đây là toàn bộ lớp test, gồm máy chủ giả, ứng dụng thử nghiệm và bốn tình huống. `@Execution(SAME_THREAD)` giữ các test của lớp không chạy đồng thời vì chúng điều khiển chung một máy chủ giả.

```java
package example;

import java.io.IOException;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import io.micrometer.core.instrument.Clock;
import io.micrometer.core.instrument.Counter;
import io.micrometer.registry.otlp.OtlpConfig;
import io.micrometer.registry.otlp.OtlpMeterRegistry;
import io.opentelemetry.proto.collector.metrics.v1.ExportMetricsServiceRequest;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.parallel.Execution;
import org.junit.jupiter.api.parallel.ExecutionMode;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.LivenessState;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
    classes = ActuatorFailureTest.TestApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties = {
        "management.endpoints.web.exposure.include=health,metrics",
        "management.endpoint.health.probes.enabled=true",
        "management.endpoint.health.group.liveness.include=livenessState",
        "management.endpoint.health.group.readiness.include=readinessState,external",
        "management.otlp.metrics.export.enabled=false"
    }
)
@Execution(ExecutionMode.SAME_THREAD)
class ActuatorFailureTest {
    enum DependencyMode { OK, ERROR, SLOW }

    static final AtomicReference<DependencyMode> dependencyMode =
        new AtomicReference<>(DependencyMode.OK);
    static final AtomicInteger collectorStatus = new AtomicInteger(200);
    static final List<Attempt> attempts = new CopyOnWriteArrayList<>();
    static final ExecutorService executor = Executors.newCachedThreadPool();
    static final HttpServer stub = createStub();
    static final HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofMillis(200)).build();

    record Attempt(int status, ExportMetricsServiceRequest payload) {}

    static HttpServer createStub() {
        try {
            HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);
            server.setExecutor(executor);
            server.createContext("/dependency", exchange -> {
                DependencyMode mode = dependencyMode.get();
                if (mode == DependencyMode.SLOW) {
                    try {
                        Thread.sleep(800);
                    } catch (InterruptedException exception) {
                        Thread.currentThread().interrupt();
                    }
                }
                respond(exchange, mode == DependencyMode.ERROR ? 503 : 200);
            });
            server.createContext("/v1/metrics", exchange -> {
                var payload = ExportMetricsServiceRequest.parseFrom(
                    exchange.getRequestBody().readAllBytes());
                int status = collectorStatus.get();
                attempts.add(new Attempt(status, payload));
                respond(exchange, status);
            });
            server.start();
            return server;
        } catch (IOException exception) {
            throw new ExceptionInInitializerError(exception);
        }
    }

    static void respond(HttpExchange exchange, int status) {
        try {
            // Thông điệp protobuf rỗng là phản hồi OTLP thành công hợp lệ.
            exchange.getResponseHeaders().set("Content-Type", "application/x-protobuf");
            exchange.sendResponseHeaders(status, -1);
        } catch (IOException ignored) {
            // Máy khách đã quá hạn có thể đóng kết nối trước khi máy chủ giả trả lời.
        } finally {
            exchange.close();
        }
    }

    static String stubUrl(String path) {
        return "http://127.0.0.1:" + stub.getAddress().getPort() + path;
    }

    @SpringBootConfiguration
    @EnableAutoConfiguration
    @Import(WorkController.class)
    static class TestApplication {
        @Bean
        HealthIndicator externalHealthIndicator() {
            return () -> {
                var request = HttpRequest.newBuilder(URI.create(stubUrl("/dependency")))
                    .timeout(Duration.ofMillis(250)).GET().build();
                try {
                    var response = client.send(request, HttpResponse.BodyHandlers.discarding());
                    return response.statusCode() == 200
                        ? Health.up().build()
                        : Health.down().withDetail("reason", "remote-status").build();
                } catch (InterruptedException exception) {
                    Thread.currentThread().interrupt();
                    return Health.down().withDetail("reason", "interrupted").build();
                } catch (IOException exception) {
                    return Health.down().withDetail("reason", "transport").build();
                }
            };
        }
    }

    @RestController
    static class WorkController {
        @GetMapping("/work")
        String work() {
            return "done";
        }
    }

    @Autowired TestRestTemplate http;
    @Autowired ObjectMapper json;
    @Autowired ConfigurableApplicationContext context;

    @BeforeEach
    void reset() {
        dependencyMode.set(DependencyMode.OK);
        collectorStatus.set(200);
        attempts.clear();
        AvailabilityChangeEvent.publish(context, LivenessState.CORRECT);
        AvailabilityChangeEvent.publish(context, ReadinessState.ACCEPTING_TRAFFIC);
    }

    @AfterEach
    void restore() {
        dependencyMode.set(DependencyMode.OK);
        AvailabilityChangeEvent.publish(context, LivenessState.CORRECT);
        AvailabilityChangeEvent.publish(context, ReadinessState.ACCEPTING_TRAFFIC);
    }

    @AfterAll
    static void stopStub() {
        stub.stop(0);
        executor.shutdownNow();
    }

    void assertHealth(String group, int code, String expected) throws Exception {
        var response = http.getForEntity("/actuator/health/" + group, String.class);
        assertThat(response.getStatusCode().value()).isEqualTo(code);
        assertThat(json.readTree(response.getBody()).path("status").asText())
            .isEqualTo(expected);
    }

    @Test
    void externalFailureAndRecovery() throws Exception {
        assertHealth("readiness", 200, "UP");
        dependencyMode.set(DependencyMode.ERROR);
        assertHealth("readiness", 503, "DOWN");
        assertHealth("liveness", 200, "UP");
        dependencyMode.set(DependencyMode.OK);
        assertHealth("readiness", 200, "UP");
    }

    @Test
    void slowDependencyAndRecovery() throws Exception {
        dependencyMode.set(DependencyMode.SLOW);
        long start = System.nanoTime();
        assertHealth("readiness", 503, "DOWN");
        assertThat(Duration.ofNanos(System.nanoTime() - start))
            .isLessThan(Duration.ofSeconds(3));
        assertHealth("liveness", 200, "UP");
        dependencyMode.set(DependencyMode.OK);
        assertHealth("readiness", 200, "UP");
    }

    @Test
    void readinessEventDoesNotCloseHttpConnector() throws Exception {
        AvailabilityChangeEvent.publish(context, ReadinessState.REFUSING_TRAFFIC);
        assertHealth("readiness", 503, "OUT_OF_SERVICE");
        assertHealth("liveness", 200, "UP");
        var response = http.getForEntity("/work", String.class);
        assertThat(response.getStatusCode().value()).isEqualTo(200);
        assertThat(response.getBody()).isEqualTo("done");
        AvailabilityChangeEvent.publish(context, ReadinessState.ACCEPTING_TRAFFIC);
        assertHealth("readiness", 200, "UP");
    }

    static class ManualOtlpRegistry extends OtlpMeterRegistry implements AutoCloseable {
        ManualOtlpRegistry() {
            super(new OtlpConfig() {
                @Override public String get(String key) { return null; }
                @Override public boolean enabled() { return false; }
                @Override public String url() { return stubUrl("/v1/metrics"); }
            }, Clock.SYSTEM);
        }

        void publishOnce() {
            super.publish();
        }
    }

    @Test
    void exporterFailureAndRecovery() throws Exception {
        try (var registry = new ManualOtlpRegistry()) {
            Counter counter = registry.counter("lab.completed");
            counter.increment(2);
            collectorStatus.set(503);
            registry.publishOnce();
            assertThat(attempts).hasSize(1);
            assertThat(attempts.get(0).status()).isEqualTo(503);
            assertThat(counter.count()).isEqualTo(2);
            assertHealth("readiness", 200, "UP");
            assertHealth("liveness", 200, "UP");
            var response = http.getForEntity("/work", String.class);
            assertThat(response.getStatusCode().value()).isEqualTo(200);
            assertThat(response.getBody()).isEqualTo("done");

            collectorStatus.set(200);
            counter.increment();
            registry.publishOnce();
            assertThat(attempts).hasSize(2);
            Attempt recovered = attempts.get(1);
            assertThat(recovered.status()).isEqualTo(200);
            double exported = recovered.payload().getResourceMetricsList().stream()
                .flatMap(resource -> resource.getScopeMetricsList().stream())
                .flatMap(scope -> scope.getMetricsList().stream())
                .filter(metric -> metric.getName().equals("lab.completed"))
                .mapToDouble(metric -> metric.getSum().getDataPoints(0).getAsDouble())
                .findFirst().orElseThrow();
            assertThat(exported).isEqualTo(3);
        }
    }
}
```

## 5. Chạy và đọc kết quả

Trong thư mục chứa `pom.xml`, dùng Maven với JDK 17 hoặc 21:

```shell
mvn test
```

Maven biên dịch mã test, khởi động ứng dụng ở cổng ngẫu nhiên và chạy JUnit. Không dùng `javac ActuatorFailureTest.java` đơn lẻ vì ví dụ cần các thư viện Spring, JUnit và OTLP trên classpath.

Trong `target/surefire-reports/example.ActuatorFailureTest.txt`, phần kết quả cần có:

```text
Tests run: 4, Failures: 0, Errors: 0, Skipped: 0
```

Đây là phần kết quả ổn định; cổng, PID, thời gian chạy và log khởi động thay đổi theo môi trường. Khi bộ thu giả trả 503, Micrometer ghi cảnh báo xuất dữ liệu thất bại là phù hợp với lỗi đang mô phỏng; toàn bộ assertion vẫn phải PASS. Không tắt mọi log chỉ để báo cáo trông sạch.

Nếu JDK Windows báo `Unable to establish loopback connection` với nguyên nhân tại `UnixDomainSockets.connect`, hãy kiểm tra môi trường socket và đường dẫn tạm trước khi kết luận Actuator lỗi. Với đường dẫn tạm quá dài, có thể đặt `jdk.net.unixdomain.tmpdir` trỏ tới một thư mục ngắn, tồn tại và được phép ghi. Đây là tùy chọn JVM của lượt test, không phải thuộc tính Spring. [Cách JDK Windows chọn thư mục socket](https://github.com/openjdk/jdk21u/blob/master/src/java.base/windows/classes/sun/nio/ch/UnixDomainSocketsUtil.java).

## 6. Đọc từng thí nghiệm và giới hạn của bằng chứng

### 6.1. HTTP 503 từ phụ thuộc ngoài

`externalFailureAndRecovery()` bắt đầu bằng readiness `UP`, đổi máy chủ giả sang 503, yêu cầu readiness `DOWN` và liveness vẫn `UP`, rồi bỏ lỗi và xác minh readiness `UP` trở lại.

Bean `externalHealthIndicator` có ID health `external`. Readiness được cấu hình gồm `readinessState,external`; liveness chỉ gồm `livenessState`. Vì vậy lỗi ngoài đi vào phép tổng hợp readiness, không đi vào phép tổng hợp liveness. Test kiểm tra việc phân tách đó qua endpoint HTTP.

Thí nghiệm chưa chứng minh truy vấn cơ sở dữ liệu, giao dịch, thử lại hoặc cách xử lý thay thế trong ứng dụng thật. Khi áp dụng, cần thêm assertion trên nghiệp vụ sử dụng phụ thuộc; endpoint health trả đúng không thay thế kiểm thử nghiệp vụ.

### 6.2. Phản hồi chậm và thời hạn

`slowDependencyAndRecovery()` trì hoãn phản hồi lâu hơn thời hạn 250 ms của yêu cầu. Lỗi I/O được chuyển thành `DOWN`; liveness vẫn trả lời; sau khi bỏ độ trễ, readiness trở lại `UP`.

Lỗi trả ngay và lỗi treo khác nhau về tài nguyên: chờ quá lâu có thể giữ luồng, kết nối và tác vụ đang xử lý. Vì vậy phải có tình huống chậm bên cạnh tình huống HTTP 503.

`connectTimeout(200 ms)` giới hạn giai đoạn tạo kết nối; `HttpRequest.timeout(250 ms)` là thời hạn của yêu cầu. Không coi chúng là cùng một đại lượng, cũng không yêu cầu toàn bộ test HTTP kết thúc đúng một mili giây định sẵn. Assertion ba giây có khoảng dung sai cho HTTP và môi trường CI.

Test này không mô phỏng đầy đủ DNS, TCP bị từ chối, cạn pool hoặc mọi giai đoạn đọc body lớn. Các trường hợp ấy cần kịch bản mạng riêng. Trong ứng dụng thật còn phải kiểm tra các thời hạn của chính thư viện HTTP/driver đang dùng; cấu hình timeout của kubelet không tự hủy mọi công việc phía ứng dụng.

### 6.3. Sự kiện readiness không đóng cổng HTTP

`readinessEventDoesNotCloseHttpConnector()` phát `REFUSING_TRAFFIC` rồi kiểm tra `OUT_OF_SERVICE`/503. Sau đó nó gọi trực tiếp `/work` và vẫn nhận 200. Điều này chứng minh availability là tín hiệu để hạ tầng sử dụng; ứng dụng chưa tự chặn mọi yêu cầu chỉ nhờ phát sự kiện.

`/work` chỉ trả kết quả nội bộ, không gọi phụ thuộc ngoài. Nó thành công không có nghĩa yêu cầu cần cơ sở dữ liệu cũng thành công. Test không có Kubernetes Service hay bộ cân bằng tải để loại bản sao khỏi tuyến.

Sau khi phát `ACCEPTING_TRAFFIC`, readiness phải trở lại `UP`. Nếu chỉ kiểm tra đối tượng sự kiện mà không gọi HTTP, ta bỏ sót phép chiếu availability thành kết quả endpoint. Ngược lại, phát thủ công sự kiện cũng chưa chứng minh logic startup thật đã phát sự kiện đúng thời điểm; điều đó cần kiểm thử riêng.

### 6.4. Bộ thu OTLP lỗi và phục hồi

`exporterFailureAndRecovery()` dùng `OtlpMeterRegistry` thật. Lớp con chỉ dành cho test công khai một phương thức gọi `publish()`; `enabled()=false` ngăn bộ lập lịch tự chạy. Mỗi lần `publishOnce()` là một lần xuất được điều khiển rõ ràng, không cần ngủ chờ chu kỳ `step`.

Trình tự kiểm chứng:

1. Tăng `lab.completed` lên 2, cho bộ thu trả 503 và gọi xuất dữ liệu.
2. Xác minh có một request OTLP giải mã được, bộ thu trả 503 và bộ đếm cục bộ vẫn bằng 2.
3. Ngay trong tình huống đó, gọi readiness, liveness và `/work` để xác minh đường HTTP thử nghiệm vẫn hoạt động.
4. Cho bộ thu trở lại 200, tăng bộ đếm thêm 1 và xuất lại.
5. Giải mã protobuf của lần gửi mới, tìm đúng metric `lab.completed` và kiểm tra giá trị bằng 3.

Micrometer 1.13 mặc định dùng cách tổng hợp tích lũy (`cumulative`) cho OTLP. Giá trị 3 cho thấy lần gửi sau phản ánh tổng bộ đếm mới; nó không chứng minh exporter đã lưu bền vững và phát lại mọi gói bị lỗi. Với `delta` hoặc histogram, cần assertion theo khoảng đo và dữ liệu tương ứng. [Cấu hình OTLP Micrometer 1.13](https://docs.micrometer.io/micrometer/reference/1.13/implementations/otlp.html).

`OtlpMeterRegistry` ở nhánh 1.13 ghi cảnh báo khi HTTP không thành công hoặc quá trình gửi gặp lỗi. Assertion “gọi xuất không ném exception” không đủ để kết luận dữ liệu đã được nhận. [Mã nguồn OtlpMeterRegistry 1.13.15](https://github.com/micrometer-metrics/micrometer/blob/v1.13.15/implementations/micrometer-registry-otlp/src/main/java/io/micrometer/registry/otlp/OtlpMeterRegistry.java).

Bộ thu giả chỉ giải mã và ghi nhận thông điệp. HTTP 200 ở đây không chứng minh dữ liệu đã được lưu bền vững trong một hệ thống time-series hoặc xuất hiện trên dashboard thật.

`ManualOtlpRegistry` khai báo `implements AutoCloseable` để dùng `try-with-resources` với phương thức `close()` kế thừa. Đây là lớp hỗ trợ kiểm thử, không phải yêu cầu sửa registry trong production.

## 7. Kiểm thử đường xuất dữ liệu thật mà không bị PASS giả

### 7.1. Chứng minh exporter thực sự đang hoạt động

Trong `@SpringBootTest`, các registry xuất ra hệ thống ngoài không tự được cấu hình giống khi chạy ứng dụng thông thường; registry trong bộ nhớ vẫn có thể tồn tại. Nếu muốn kiểm tra chính đường tự cấu hình exporter, dùng `@AutoConfigureObservability` và hướng exporter tới bộ thu thử nghiệm. [Metrics trong kiểm thử Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html#testing.spring-boot-applications.metrics).

Ví dụ trên tạo registry thủ công. Thuộc tính `management.otlp.metrics.export.enabled=false` ngăn registry tự cấu hình gửi nền ngoài ý muốn; nó không chi phối đối tượng được tạo bằng `new ManualOtlpRegistry()`. Vì vậy test chứng minh hành vi registry khi bộ thu lỗi cùng với khả năng HTTP vẫn hoạt động, chưa kiểm chứng toàn bộ cấu hình tự động và lịch gửi production.

Với bài tích hợp đường xuất thực tế, cần kiểm tra thêm:

- Registry/exporter đúng kiểu tồn tại và nhận chính metric cần quan sát.
- Địa chỉ xuất thuộc bộ thu thử nghiệm, không vô tình gửi tới hệ thống thật.
- Trước khi gây lỗi, phía nhận đã có một dữ liệu hợp lệ để xác nhận tuyến hoạt động.
- Trong khoảng lỗi, tác vụ nghiệp vụ đại diện vẫn đạt kết quả và ngân sách thời gian/tài nguyên theo chính sách.
- Sau phục hồi, phía nhận có dữ liệu mới đúng danh tính, giá trị và thời gian; không nhầm request cũ còn sót với kết quả mới.
- Registry và các luồng nền được đóng; không còn tác vụ gửi sau khi context kết thúc.

Với bộ lập lịch thật, dùng chờ theo điều kiện có thời hạn tổng. Không bắt buộc đúng một request nếu thiết kế có gửi theo lô hoặc thử lại. Lọc đúng dữ liệu của lượt thử, thay vì dựa vào thứ tự mọi request nền. Không dùng nhãn ngẫu nhiên không giới hạn trên metric production chỉ để tiện truy tìm trong test.

### 7.2. Prometheus lấy dữ liệu, OTLP trong ví dụ đẩy dữ liệu

Trong mô hình Prometheus thông thường, Prometheus chủ động lấy dữ liệu từ `/actuator/prometheus`. Prometheus ngừng chạy không có nghĩa ứng dụng đang thất bại ở một request đẩy HTTP tới Prometheus. Phân biệt mô hình này với cơ chế đẩy riêng như Pushgateway. [Mô hình Micrometer Prometheus](https://docs.micrometer.io/micrometer/reference/implementations/prometheus.html).

Kịch bản phù hợp cho đường lấy dữ liệu:

1. Ghi metric biết trước, gọi endpoint scrape và xác nhận nó được phơi bày đúng.
2. Dừng hoặc chặn bên thu thập trong môi trường thử nghiệm; tiếp tục tạo tải và kiểm tra ứng dụng theo chính sách.
3. Kiểm tra phía giám sát phát hiện mất lần lấy mẫu. Endpoint `/actuator/metrics` có số liệu cục bộ chưa chứng minh Prometheus đã nhận.
4. Khôi phục việc lấy dữ liệu rồi kiểm tra mẫu mới ở hệ thống giám sát.

Không cam kết mọi mẫu trung gian được phục hồi. Một bộ đếm tích lũy có thể thể hiện tổng mới sau sự cố nhưng không tái tạo mọi diễn biến đã xảy ra trong khoảng mất dữ liệu.

### 7.3. Metric phục hồi chưa chứng minh trace và log phục hồi

Trace cần kiểm soát việc lấy mẫu trong cấu hình test, kết thúc span rồi kiểm tra mã trace ở phía nhận. Log qua cơ chế bất đồng bộ cần kiểm tra giới hạn hàng đợi, chính sách khi đầy và việc flush khi đóng. Dùng danh tính dữ liệu thử nghiệm để phân biệt dữ liệu mới, bản trùng và bản đến muộn.

Chỉ tuyên bố không mất dữ liệu khi cơ chế lưu trữ/hàng đợi và phép thử thực sự chứng minh bảo đảm đó. Một cảnh báo biến mất hoặc dashboard xanh trở lại chưa đủ.

## 8. Mở rộng lỗi và kiểm thử theo đúng tầng

Máy chủ giả phù hợp cho mã HTTP và phản hồi chậm. Khi cần lỗi mạng thực tế hơn, dùng proxy gây lỗi hoặc môi trường container cô lập; không dừng dịch vụ đang phục vụ người dùng để chạy bộ kiểm thử tự động.

| Lỗi | Cách tạo trong môi trường thử nghiệm | Assertion cần thêm |
| --- | --- | --- |
| HTTP 500/503 | Máy chủ giả đổi mã trả về | Health đúng, gỡ lỗi phục hồi |
| Phản hồi chậm | Trì hoãn phản hồi ở máy chủ giả | Thời hạn máy khách có hiệu lực, probe không treo |
| Kết nối bị từ chối/đứt | Proxy hoặc dừng đúng container thử nghiệm | Tác vụ thoát đúng hạn, tài nguyên được giải phóng |
| Mạng chập chờn | Luân phiên hoạt động/lỗi theo kịch bản xác định | Không kẹt trạng thái sau nhiều vòng lỗi/phục hồi |
| Bộ thu không theo kịp | Làm chậm đường nhận | Theo dõi hàng đợi, luồng, bộ nhớ, độ trễ nghiệp vụ |
| Phụ thuộc chung hỏng | Chặn cùng phụ thuộc cho nhiều bản sao thử nghiệm | Đánh giá hệ quả readiness lên toàn dịch vụ và cách xử lý thay thế |

Nếu ứng dụng dùng management port riêng, phải kiểm tra cả cổng nghiệp vụ. Có thể đưa probe bổ sung ra cổng chính bằng `management.endpoint.health.probes.add-additional-paths=true` rồi kiểm tra đúng đường dẫn triển khai. Probe trên cổng quản trị hoạt động chưa đủ chứng minh cổng chính phục vụ được yêu cầu. [Probe trên cổng ứng dụng](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes).

Trong cụm thử nghiệm, đối chiếu cấu hình `periodSeconds`, `timeoutSeconds`, `failureThreshold` và điều kiện phục hồi của probe. Kiểm tra việc Pod bị rút/đưa lại vào tuyến bằng đường Service, đồng thời theo dõi số lần restart. Nếu có startup probe, kiểm tra riêng giai đoạn khởi động để tránh kết luận nhầm rằng liveness thất bại trong thời gian khởi tạo là lỗi nghiệp vụ. Không suy thời gian hội tụ trong cụm chỉ từ một test HTTP cục bộ.

## 9. Những lỗi kiểm thử thường gặp

| Cách làm | Vì sao kết luận chưa đủ | Cách kiểm tra tốt hơn |
| --- | --- | --- |
| Chỉ gọi `/actuator/health` | Không phân biệt mục đích từng nhóm | Gọi từng probe, kiểm tra mã HTTP và body |
| Mock cả kết quả health thành DOWN | Bỏ qua mã xử lý lỗi phụ thuộc | Giữ indicator thật, gây lỗi ở ranh giới HTTP/adapter |
| Chỉ phát sự kiện availability | Chưa kiểm tra endpoint nhận trạng thái | Gọi HTTP sau sự kiện và sau phục hồi |
| Thấy counter tăng rồi kết luận đã xuất | Đó mới là dữ liệu trong registry | Kiểm tra payload và kết quả phía nhận |
| Exporter chưa bật nhưng test xanh | Tuyến xuất chưa từng được dùng | Chứng minh có lần nhận hợp lệ trước và sau lỗi |
| Ngủ cố định vài giây | Phụ thuộc tốc độ CI/lịch chạy nền | Điều khiển lần gửi hoặc chờ điều kiện có thời hạn |
| Chỉ kiểm tra giai đoạn lỗi | Bỏ sót trạng thái kẹt hoặc rò rỉ | Assertion phục hồi và dọn tài nguyên |
| Log lỗi là assertion duy nhất | Không chứng minh nội dung đã tới bộ thu | Kiểm tra dữ liệu có cấu trúc và giá trị thực |

## 10. Thực hành tự kiểm chứng

1. Bỏ `external` khỏi readiness, chạy lại test và giải thích assertion nào thất bại. Sau đó viết kỳ vọng mới cho chính sách phụ thuộc tùy chọn; đừng đổi kỳ vọng chỉ để che một cấu hình sai.
2. Thêm test phát `LivenessState.BROKEN`, kiểm tra liveness `DOWN`/503 rồi khôi phục `CORRECT`. Giải thích vì sao readiness có thể vẫn `UP` nếu không cơ chế nào thay đổi nó.
3. Thêm lỗi kết nối tới bộ thu, xác minh tác vụ xuất kết thúc đúng hạn và lần gửi sau phục hồi chứa dữ liệu mới. Tách lỗi kết nối khỏi HTTP 503.
4. Tạo lớp test khác dùng cấu hình OTLP tự động. Chứng minh exporter được bật, bộ thu nhận dữ liệu và lịch gửi dừng khi context đóng.
5. Thay `/work` bằng nghiệp vụ đại diện của ứng dụng thật, có cả đường dùng phụ thuộc và đường xử lý thay thế. Kiểm tra kết quả khi lỗi đang diễn ra và sau phục hồi.

Một kịch bản đạt yêu cầu phải chỉ rõ lỗi được tạo ở đâu, tín hiệu nào phải đổi, chức năng nào phải tiếp tục hoạt động, dữ liệu nào thực sự tới bộ thu và bằng chứng nào xác nhận phục hồi. Nhờ vậy, kiểm thử đi từ một endpoint trả đúng mã tới đánh giá hành vi của ứng dụng trong sự cố.
