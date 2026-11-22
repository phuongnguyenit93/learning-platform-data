# Giám sát khả năng thu thập dữ liệu và nhận diện điểm mù của cổng quản trị riêng

## 1. Hai câu hỏi không được gộp thành một

Khi bảng giám sát xanh, cần biết nó đang xác nhận điều gì. “Bộ thu lấy được metric” khác với “người dùng gọi được dịch vụ”. Một cổng quản trị hoạt động có thể cung cấp dữ liệu JVM trong khi cổng nghiệp vụ không nhận kết nối. Ngược lại, cổng quản trị hoặc đường scrape hỏng có thể làm mất dữ liệu dù ứng dụng vẫn xử lý yêu cầu.

**Giám sát khả năng thu thập dữ liệu** là kiểm tra tuyến quan sát: có phát hiện được đích cần đo, kết nối được, đọc đúng định dạng, giữ đúng metric và đưa được dữ liệu tới nơi truy vấn hay không. **Điểm mù** xuất hiện khi một kết quả tốt ở tuyến đó được dùng để kết luận về một tuyến mà nó chưa đi qua.

Trong Spring Boot, `server.port` là cổng ứng dụng; `management.server.port` có thể đưa Actuator sang cổng khác. Hai cổng vẫn thuộc cùng ứng dụng/JVM, nhưng không nhất thiết đi qua cùng hạ tầng web. Cổng quản trị có thể còn trả lời khi cổng chính không nhận kết nối. [Spring Boot 3.3: probe trên management context riêng](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes).

Mô hình cần giữ trong đầu:

```text
Tuyến người dùng:
  Máy khách → DNS/TLS → proxy hoặc load balancer → cổng nghiệp vụ → xử lý nghiệp vụ

Tuyến thu metric:
  Prometheus → mạng quản trị/xác thực → cổng quản trị → /actuator/prometheus
             → lọc/ghi dữ liệu → nơi truy vấn → dashboard/cảnh báo

Tuyến kiểm tra từ ngoài:
  Bộ kiểm tra HTTP → cổng chính hoặc URL công khai → kết quả giao thức/nội dung mong đợi
```

Ba tuyến có thể chia sẻ tài nguyên nhưng phạm vi bằng chứng khác nhau. Không có một lần HTTP 200 nào tự chứng minh cả ba tuyến đều hoạt động.

## 2. Mỗi tín hiệu nói được điều gì?

| Tín hiệu | Bằng chứng trực tiếp | Chưa chứng minh |
| --- | --- | --- |
| `/actuator/health` trả UP | Các thành phần health được cấu hình cho kết quả tổng hợp đó | Mọi đường nghiệp vụ hoặc tuyến công khai đều tốt |
| Management readiness trả UP | Nhóm readiness ở cổng quản trị báo sẵn sàng | Cổng chính nhận được kết nối |
| `/readyz` trên cổng chính trả UP | HTTP đi qua cổng chính và nhóm readiness đang UP | Mọi truy vấn, giao dịch và đường nghiệp vụ đều đúng |
| HTTP scrape thành công | Bộ thu truy cập/đọc được endpoint theo cấu hình | Mọi metric cần thiết còn đủ hoặc dữ liệu nghiệp vụ còn mới |
| Prometheus `up=1` | Lần scrape của đúng target thành công theo bộ thu | Người dùng dùng được dịch vụ |
| Probe nghiệp vụ thành công | Từ vị trí bộ kiểm tra, thao tác đã chọn đáp ứng điều kiện | Mọi người dùng, vùng mạng và chức năng đều được bao phủ |

`up` do Prometheus tạo cho từng đích thu thập, không phải JSON `health.status` được Spring Boot tự chuyển thành metric. Khi target còn trong discovery nhưng scrape thất bại, Prometheus ghi `up=0`. Prometheus cũng cung cấp `scrape_duration_seconds` và các số lượng mẫu phục vụ chẩn đoán. [Các chuỗi tự sinh khi scrape](https://prometheus.io/docs/concepts/jobs_instances/).

Nếu cần health thành metric, phải có phép chuyển đổi rõ ràng hoặc exporter/probe phù hợp. Không viết truy vấn dùng một metric như `health_status` rồi mặc định mọi ứng dụng Actuator đều xuất nó.

## 3. Phân tích tuyến thu thập theo từng tầng

### 3.1. Có đúng và đủ đích dự kiến không?

Đích không còn trong danh sách discovery khác với đích đang có `up=0`. Ví dụ một bản sao bị loại nhầm khỏi bộ lọc nhãn: Prometheus không còn scrape nó, nên một rule chỉ kiểm tra `up == 0` có thể không phát hiện được.

Đối chiếu danh sách target với nguồn kiểm kê/triển khai: dịch vụ, môi trường, bản sao, cổng và đường dẫn. Đừng dùng số chuỗi đang hiện diện làm nguồn duy nhất để xác định số bản sao đáng lẽ phải có. Khi triển khai thay thế bản sao, danh tính nào được xem là ổn định cũng cần được quy định.

### 3.2. Có kết nối và đọc được endpoint không?

Kiểm tra từ cùng vị trí mạng với bộ thu: tên miền, địa chỉ bind, cổng, giao thức, chứng chỉ, xác thực và timeout. Truy cập thành công từ laptop không chứng minh Prometheus trong một mạng khác có cùng quyền truy cập.

Các lỗi 401/403 thường cần kiểm tra thông tin xác thực/quyền; 404 có thể do sai base path, sai cổng hoặc endpoint chưa được expose. Lỗi định dạng có thể đến từ HTML trang đăng nhập hoặc phản hồi proxy. Không bỏ xác thực chỉ để làm target chuyển xanh.

### 3.3. Thu được có đúng dữ liệu cần theo dõi không?

HTTP 200 và định dạng metric hợp lệ chưa đủ. Một thay đổi tên, nhãn hoặc `metric_relabel_configs` có thể loại đúng chuỗi mà dashboard cần, trong khi metric JVM khác vẫn được giữ.

Đối chiếu ít nhất ba điểm: nội dung endpoint gốc, dữ liệu sau lọc tại bộ thu và kết quả truy vấn ở nơi dashboard sử dụng. Các chỉ số `scrape_samples_scraped` và `scrape_samples_post_metric_relabeling` hỗ trợ tìm thay đổi số lượng mẫu, nhưng không tự chứng minh một metric nghiệp vụ cụ thể còn tồn tại.

### 3.4. Mẫu còn mới có đồng nghĩa nội dung còn mới không?

Không. Một gauge cố định bằng 1 có thể được scrape mới liên tục mà không chứng minh tác vụ nghiệp vụ vừa hoàn thành. Timestamp của mẫu cho biết thời điểm đo/lưu theo ngữ nghĩa của tuyến thu, không mặc định là thời điểm dữ liệu nguồn được cập nhật thành công.

Với tác vụ định kỳ, có thể cần một metric riêng thể hiện thời điểm hoàn thành thành công cuối cùng. Chỉ cập nhật nó sau khi công việc thật hoàn tất; thời điểm thử chạy hoặc thời điểm gọi getter không thay thế được thời điểm thành công. Đồng hồ, chu kỳ chạy và ngưỡng trễ phải được xác định cùng nhau.

Nếu có remote write hoặc một tầng lưu trữ/truy vấn khác, metric có trong Prometheus cục bộ chưa chứng minh dashboard ở tầng sau nhận được dữ liệu mới. Xác minh độ trễ và sự hiện diện tại chính nơi đánh giá cảnh báo.

## 4. Đưa probe lên cổng chính để giảm một loại điểm mù

Với một ứng dụng web đã có Actuator và registry Prometheus, cấu hình minh họa `application.yml`:

```yaml
server:
  port: 8080
management:
  server:
    port: 8081
    address: 127.0.0.1
  endpoints:
    web:
      exposure:
        include: health,prometheus
  endpoint:
    health:
      probes:
        enabled: true
        add-additional-paths: true
      group:
        liveness:
          include: livenessState
        readiness:
          include: readinessState
```

Cổng 8081 trong ví dụ chỉ bind loopback để thực hành trên cùng máy. Trong production, chọn địa chỉ/dịch vụ mạng mà bộ thu thật có thể truy cập theo chính sách triển khai. `127.0.0.1` bên trong container là chính không gian mạng đó; một container Prometheus khác không tự truy cập được loopback của container ứng dụng. [Cổng, địa chỉ và đường dẫn quản trị](https://docs.spring.io/spring-boot/3.3/reference/actuator/monitoring.html).

`management.endpoint.health.probes.add-additional-paths=true` đưa liveness/readiness ra cổng chính tại `/livez` và `/readyz`. Cần cấu hình bộ kiểm tra gọi đúng cổng chính; bật thuộc tính nhưng tiếp tục chỉ gọi 8081 không thay đổi phạm vi quan sát.

Hai nhóm trong ví dụ chỉ đọc trạng thái availability. Chúng không tự chạy mọi đường nghiệp vụ. Đưa một phụ thuộc vào readiness phải theo yêu cầu phục vụ của ứng dụng; không đưa hệ thống ngoài vào liveness chỉ để tăng số thứ được kiểm tra.

Cổng chính, cổng quản trị, proxy và chính sách bảo mật có thể có đường đi khác nhau. Kiểm tra thực tế rằng bộ kiểm tra truy cập được `/readyz` và không bị redirect sang trang đăng nhập. Chỉ mở các endpoint cần thiết; cổng riêng không thay cho xác thực và kiểm soát mạng.

## 5. Thí nghiệm Java đầy đủ: hai cổng, bốn tình huống

Ví dụ sau chạy Spring Boot 3.3.13 bằng JUnit 5, biên dịch theo Java 17 và chạy được bằng JDK 21. Nó dùng Spring MVC/Tomcat và hai cổng ngẫu nhiên, không tác động tới ứng dụng production.

Mỗi lần gây lỗi đều được khôi phục ngay trong test. Đặc biệt, chỉ dừng connector của một cổng; không dừng cả JVM hay đóng toàn bộ application context. Đây là cách kiểm tra đúng giả thuyết “một cổng hỏng nhưng cổng kia còn hoạt động”.

### 5.1. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.3.13</version>
    <relativePath/>
  </parent>
  <groupId>example</groupId>
  <artifactId>management-port-observability-lab</artifactId>
  <version>1.0.0</version>
  <properties><java.version>17</java.version></properties>
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
      <groupId>io.micrometer</groupId>
      <artifactId>micrometer-registry-prometheus</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-test</artifactId>
      <scope>test</scope>
    </dependency>
  </dependencies>
</project>
```

### 5.2. `src/test/java/example/ManagementPortTest.java`

```java
package example;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

import com.fasterxml.jackson.databind.ObjectMapper;
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;
import org.apache.catalina.connector.Connector;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.parallel.Execution;
import org.junit.jupiter.api.parallel.ExecutionMode;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.autoconfigure.actuate.observability.AutoConfigureObservability;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalManagementPort;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.boot.web.embedded.tomcat.TomcatWebServer;
import org.springframework.boot.web.context.WebServerInitializedEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@SpringBootTest(
    classes = ManagementPortTest.TestApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties = {
        "server.address=127.0.0.1",
        "management.server.address=127.0.0.1",
        "management.server.port=0",
        "management.endpoints.web.exposure.include=health,prometheus",
        "management.endpoint.health.probes.enabled=true",
        "management.endpoint.health.probes.add-additional-paths=true",
        "management.endpoint.health.group.liveness.include=livenessState",
        "management.endpoint.health.group.readiness.include=readinessState"
    }
)
@AutoConfigureObservability
@Execution(ExecutionMode.SAME_THREAD)
class ManagementPortTest {
    static final AtomicBoolean rejectOrders = new AtomicBoolean();
    static final HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(1)).build();

    @SpringBootConfiguration
    @EnableAutoConfiguration
    @Import({OrdersController.class, ServerReferences.class})
    static class TestApplication {
        @Bean
        AtomicInteger collectionMarker(MeterRegistry registry) {
            AtomicInteger marker = new AtomicInteger(1);
            Gauge.builder("lab.collection.marker", marker, AtomicInteger::get)
                .register(registry);
            return marker;
        }
    }

    @RestController
    static class OrdersController {
        @GetMapping("/orders/check")
        ResponseEntity<String> check() {
            return rejectOrders.get()
                ? ResponseEntity.status(503).body("orders-unavailable")
                : ResponseEntity.ok("orders-ok");
        }
    }

    static class ServerReferences
            implements ApplicationListener<WebServerInitializedEvent> {
        final Map<Integer, TomcatWebServer> servers = new ConcurrentHashMap<>();

        @Override
        public void onApplicationEvent(WebServerInitializedEvent event) {
            if (event.getWebServer() instanceof TomcatWebServer server) {
                servers.put(server.getPort(), server);
            }
        }

        Connector connector(int port) {
            TomcatWebServer server = servers.get(port);
            if (server == null) {
                throw new IllegalStateException("No test server at port " + port);
            }
            return server.getTomcat().getConnector();
        }
    }

    @LocalServerPort int applicationPort;
    @LocalManagementPort int managementPort;
    @Autowired ServerReferences references;
    @Autowired ObjectMapper json;

    @AfterEach
    void restoreBusinessMode() {
        rejectOrders.set(false);
    }

    HttpResponse<String> get(int port, String path) throws Exception {
        var request = HttpRequest.newBuilder(
                URI.create("http://127.0.0.1:" + port + path))
            .timeout(Duration.ofSeconds(2)).GET().build();
        return client.send(request, HttpResponse.BodyHandlers.ofString());
    }

    void assertReady(int port, String path) throws Exception {
        var response = get(port, path);
        assertThat(response.statusCode()).isEqualTo(200);
        assertThat(json.readTree(response.body()).path("status").asText())
            .isEqualTo("UP");
    }

    void assertMetricsReadable() throws Exception {
        var response = get(managementPort, "/actuator/prometheus");
        assertThat(response.statusCode()).isEqualTo(200);
        assertThat(response.body()).contains("lab_collection_marker");
    }

    @Test
    void separatePortsExposeDifferentEvidence() throws Exception {
        assertThat(applicationPort).isNotEqualTo(managementPort);
        assertReady(managementPort, "/actuator/health/readiness");
        assertReady(applicationPort, "/readyz");
        assertMetricsReadable();
        var response = get(applicationPort, "/orders/check");
        assertThat(response.statusCode()).isEqualTo(200);
        assertThat(response.body()).isEqualTo("orders-ok");
    }

    @Test
    void mainConnectorFailureDoesNotImplyManagementFailure() throws Exception {
        Connector connector = references.connector(applicationPort);
        connector.stop();
        try {
            assertThatThrownBy(() -> get(applicationPort, "/readyz"))
                .isInstanceOf(IOException.class);
            assertReady(managementPort, "/actuator/health/readiness");
            assertMetricsReadable();
        } finally {
            connector.setPort(applicationPort);
            connector.start();
        }
        assertReady(applicationPort, "/readyz");
        assertThat(get(applicationPort, "/orders/check").statusCode()).isEqualTo(200);
    }

    @Test
    void managementFailureDoesNotImplyBusinessFailure() throws Exception {
        Connector connector = references.connector(managementPort);
        connector.stop();
        try {
            assertThatThrownBy(() -> get(managementPort, "/actuator/prometheus"))
                .isInstanceOf(IOException.class);
            assertReady(applicationPort, "/readyz");
            assertThat(get(applicationPort, "/orders/check").statusCode()).isEqualTo(200);
        } finally {
            connector.setPort(managementPort);
            connector.start();
        }
        assertMetricsReadable();
    }

    @Test
    void mainPortReadinessDoesNotProveEveryBusinessRouteWorks() throws Exception {
        rejectOrders.set(true);
        var response = get(applicationPort, "/orders/check");
        assertThat(response.statusCode()).isEqualTo(503);
        assertThat(response.body()).isEqualTo("orders-unavailable");
        assertReady(applicationPort, "/readyz");
        assertReady(managementPort, "/actuator/health/readiness");
        assertMetricsReadable();
        rejectOrders.set(false);
        assertThat(get(applicationPort, "/orders/check").statusCode()).isEqualTo(200);
    }
}
```

### 5.3. Chạy và xác minh

Trong thư mục chứa `pom.xml`:

```shell
mvn test
```

Maven cung cấp classpath Spring/JUnit; không chạy tệp test bằng `javac` đơn lẻ. Báo cáo `target/surefire-reports/example.ManagementPortTest.txt` cần có phần kết quả:

```text
Tests run: 4, Failures: 0, Errors: 0, Skipped: 0
```

Cổng, thời gian chạy và log khởi động thay đổi theo môi trường. Nếu JDK Windows gặp lỗi socket nội bộ do đường dẫn tạm quá dài, cần kiểm tra môi trường JVM; có thể đặt `jdk.net.unixdomain.tmpdir` tới thư mục ngắn tồn tại và được phép ghi. Đó là cấu hình môi trường test, không phải cách sửa health indicator.

### 5.4. Đọc đúng bằng chứng

| Test | Kết quả đã kiểm tra |
| --- | --- |
| Hai cổng bình thường | Cổng khác nhau; readiness cả hai đường UP; có metric đánh dấu; nghiệp vụ trả nội dung đúng |
| Dừng connector cổng chính | `/readyz` không truy cập được; management readiness vẫn UP và endpoint metric còn đọc được; khôi phục cổng chính hoạt động lại |
| Dừng connector quản trị | Endpoint metric không truy cập được; cổng chính vẫn trả readiness và nghiệp vụ; khôi phục metric đọc lại được |
| Một đường nghiệp vụ trả 503 | Readiness ở cả hai cổng vẫn UP và metric vẫn có; bỏ lỗi thì nghiệp vụ trả 200 lại |

`@AutoConfigureObservability` giúp kiểm thử nạp registry xuất dữ liệu thật thay vì vô tình chỉ dùng registry trong bộ nhớ. HTTP test đọc định dạng scrape của registry Prometheus, nhưng chưa có Prometheus server để xác nhận dữ liệu đã được ghi vào kho. [Metrics trong kiểm thử Spring Boot](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html#testing.spring-boot-applications.metrics).

`ServerReferences` thu các server từ sự kiện khởi tạo rồi chọn connector theo cổng. Khi khởi động lại connector, test gán cổng thực đã được cấp để tránh một cổng ngẫu nhiên mới làm sai đích HTTP. API connector là phần hỗ trợ gây lỗi chỉ dành cho thí nghiệm Tomcat, không phải endpoint điều khiển được mở cho production. [API Connector của Tomcat](https://tomcat.apache.org/tomcat-10.1-doc/api/org/apache/catalina/connector/Connector.html).

Gauge `lab.collection.marker` luôn được đăng ký để kiểm tra một dữ liệu biết trước có xuất hiện ở endpoint. Nó không phải heartbeat nghiệp vụ và không chứng minh dữ liệu nghiệp vụ còn mới. Cờ `rejectOrders` cố ý chỉ tác động một route, nên test cuối cho thấy một probe trên cổng chính vẫn có giới hạn bao phủ.

## 6. Bổ sung kiểm tra từ ngoài với Blackbox Exporter

Kiểm tra bên trong JVM giúp tìm nguyên nhân; kiểm tra từ ngoài giúp quan sát một đường gọi thực tế. Blackbox Exporter nhận yêu cầu tại `/probe`, tự gọi target rồi trả metric như `probe_success`. Prometheus thu kết quả đó. [Mô hình exporter nhiều target](https://prometheus.io/docs/guides/multi-target-exporter/).

### 6.1. `blackbox.yml`

Cấu hình minh họa hai phép kiểm tra: readiness chấp nhận HTTP 200; nghiệp vụ phải trả HTTP 200 và đúng chuỗi `orders-ok`.

```yaml
modules:
  http_ready:
    prober: http
    timeout: 3s
    http:
      method: GET
      valid_status_codes: [200]
      follow_redirects: false
  http_orders:
    prober: http
    timeout: 3s
    http:
      method: GET
      valid_status_codes: [200]
      follow_redirects: false
      fail_if_body_not_matches_regexp:
        - '^orders-ok$'
```

`follow_redirects: false` tránh việc redirect sang trang khác bị coi là thành công cho hợp đồng này. Module nghiệp vụ kiểm tra cả nội dung nên một trang HTML trả 200 không đáp ứng điều kiện. Đây là các trường cấu hình HTTP của Blackbox Exporter; cần đối chiếu phiên bản đang dùng. [Cấu hình Blackbox Exporter 0.26.0](https://github.com/prometheus/blackbox_exporter/blob/v0.26.0/CONFIGURATION.md).

Module readiness ở đây chỉ kiểm tra mã HTTP theo ánh xạ health mặc định. Nếu ứng dụng tùy chỉnh HTTP mapping hoặc cần khẳng định nội dung cụ thể, phải điều chỉnh phép kiểm tra tương ứng. Một phép kiểm tra không được coi là kiểm tra body nếu cấu hình mới chỉ giới hạn status code.

### 6.2. `prometheus.yml`

Mẫu dưới đây dành cho ứng dụng đang chạy cố định ở 8080/8081 trên cùng máy, với route kiểm tra nghiệp vụ có hợp đồng như thí nghiệm. Nó không trỏ trực tiếp tới các cổng ngẫu nhiên của JUnit; ứng dụng test đã đóng khi `mvn test` kết thúc. Khi áp dụng cho dịch vụ thật, dùng địa chỉ và thao tác đọc đại diện của chính dịch vụ.

```yaml
global:
  scrape_interval: 15s
  scrape_timeout: 4s
  evaluation_interval: 30s
scrape_configs:
  - job_name: orders-management
    metrics_path: /actuator/prometheus
    static_configs:
      - targets: ["127.0.0.1:8081"]
        labels:
          service: orders
          env: lab

  - job_name: orders-readyz
    metrics_path: /probe
    params:
      module: [http_ready]
    static_configs:
      - targets: ["http://127.0.0.1:8080/readyz"]
        labels:
          service: orders
          env: lab
    relabel_configs:
      - source_labels: [__address__]
        target_label: __param_target
      - source_labels: [__param_target]
        target_label: instance
      - target_label: __address__
        replacement: 127.0.0.1:9115

  - job_name: orders-business
    metrics_path: /probe
    params:
      module: [http_orders]
    static_configs:
      - targets: ["http://127.0.0.1:8080/orders/check"]
        labels:
          service: orders
          env: lab
    relabel_configs:
      - source_labels: [__address__]
        target_label: __param_target
      - source_labels: [__param_target]
        target_label: instance
      - target_label: __address__
        replacement: 127.0.0.1:9115

  - job_name: blackbox-self
    static_configs:
      - targets: ["127.0.0.1:9115"]
        labels:
          env: lab
```

Ba bước relabel của mỗi job probe có vai trò khác nhau:

1. Chuyển URL đích sang tham số `target` của yêu cầu `/probe`.
2. Giữ URL đích trong nhãn `instance` để biết kết quả thuộc mục tiêu nào.
3. Đổi địa chỉ mà Prometheus thực sự scrape sang Blackbox Exporter ở 9115.

Nếu chỉ thay `__address__` mà không truyền target, bộ kiểm tra không tự biết URL nghiệp vụ cần gọi. Nếu giữ `instance` bằng địa chỉ exporter cho mọi mục tiêu, việc truy vết cảnh báo dễ bị nhầm.

Lệnh chạy khi đã cài hai công cụ và có ứng dụng thực hành đang phục vụ các target tương ứng:

```shell
blackbox_exporter --config.file=blackbox.yml --web.listen-address=127.0.0.1:9115
prometheus --config.file=prometheus.yml --web.listen-address=127.0.0.1:9090
```

Chạy mỗi tiến trình ở một terminal riêng; trên Windows dùng tệp `.exe` tương ứng. Các địa chỉ loopback minh họa việc chạy cùng máy. Nếu dùng container hoặc máy khác, cấu hình đích theo vị trí mạng thật của từng tiến trình. Chỉ cho các thành phần đã được xác định truy cập endpoint quản trị và endpoint điều khiển probe.

Có thể kiểm tra cú pháp tệp Prometheus trước khi chạy:

```shell
promtool check config prometheus.yml
```

Kết quả với promtool 3.2.1:

```text
Checking prometheus.yml
 SUCCESS: prometheus.yml is valid prometheus config file syntax
```

Lệnh này không xác minh nội dung `blackbox.yml`, không kiểm tra mạng và không chứng minh target đang phục vụ. Phải kiểm tra cả module của exporter và dữ liệu nhận được khi hệ thống chạy thật.

### 6.3. Đọc đúng `up` và `probe_success`

Hai biểu thức sau thuộc cùng job nhưng trả lời hai câu hỏi:

```promql
up{job="orders-business", env="lab"}
```

```promql
probe_success{job="orders-business", env="lab"}
```

| `up` của job probe | `probe_success` | Diễn giải |
| --- | --- | --- |
| 1 | 1 | Prometheus lấy được kết quả và phép kiểm tra target thành công |
| 1 | 0 | Exporter trả metric được nhưng target không đạt hợp đồng kiểm tra |
| 0 | Không có mẫu mới đáng tin | Đường thu kết quả probe đang lỗi; chưa đủ bằng chứng về target |
| Không có chuỗi | Không có chuỗi | Kiểm tra discovery, lịch sử dữ liệu và nguồn kiểm kê; đừng đổi mặc định thành “khỏe” |

Ví dụ cổng chính ngừng nhận kết nối: exporter vẫn có thể trả HTTP 200 chứa `probe_success=0`. Lúc đó `up` của job probe vẫn có thể bằng 1. Đây không phải mâu thuẫn; scrape thành công nhưng phép kiểm tra nghiệp vụ thất bại. [Kết quả probe và metric riêng của exporter](https://github.com/prometheus/blackbox_exporter/tree/v0.26.0).

Job `blackbox-self` thu metric của chính exporter; nó không thay thế job `orders-business`. Tương tự, job `orders-management` xanh không thay thế `orders-readyz`.

## 7. Theo dõi độ đủ và độ mới của dữ liệu

### 7.1. Phân biệt target không scrape được và target biến mất

Target còn được Prometheus theo dõi nhưng lần scrape thất bại:

```promql
up{job="orders-management", env="lab"} == 0
```

Không có mẫu `up` của job trong cửa sổ 5m:

```promql
absent_over_time(up{job="orders-management", env="lab"}[5m])
```

Hai biểu thức không tương đương. `absent_over_time` kiểm tra sự hiện diện của mẫu trong cửa sổ, kể cả mẫu giá trị 0. Nó không biến một lần scrape thất bại thành “không có dữ liệu”. [Ngữ nghĩa absent_over_time](https://prometheus.io/docs/prometheus/latest/querying/functions/#absent_over_time).

Biểu thức thiếu mẫu của toàn job không phát hiện riêng một bản sao bị mất nếu các bản sao khác vẫn có mẫu. Phải đối chiếu từng danh tính dự kiến từ nguồn kiểm kê. Khi mới khởi động và chưa có lịch sử, biểu thức thiếu mẫu có thể thỏa ngay; cửa sổ 5m không mặc định là bộ hẹn giờ bắt buộc đợi đủ 5m.

### 7.2. Kiểm tra một metric có hợp đồng hiện diện

Với gauge luôn được đăng ký trong thí nghiệm:

```promql
absent_over_time(lab_collection_marker{
  job="orders-management", env="lab"
}[5m])
```

Nếu `up=1` nhưng biểu thức này có kết quả, cần kiểm tra có đang scrape đúng ứng dụng không, marker có được đăng ký không, tên/nhãn có đổi không và bộ lọc metric có loại nó không. Marker chỉ xác nhận chuỗi đánh dấu đi qua tuyến; nó không chứng minh mọi metric nghiệp vụ khác được giữ lại.

Không áp dụng điều kiện hiện diện như vậy một cách máy móc cho một chuỗi HTTP chỉ xuất hiện sau lần request đầu tiên. Trước tiên phải biết metric đó có được đăng ký ngay khi khởi động hay chỉ được tạo khi có hoạt động.

Một thí nghiệm hữu ích là cố ý loại `lab_collection_marker` bằng metric relabeling trong môi trường thử nghiệm. Endpoint gốc vẫn có marker, scrape vẫn có thể thành công, nhưng truy vấn trong Prometheus không còn dữ liệu marker mới. Bài học là phải kiểm tra dữ liệu sau lọc, không chỉ tải endpoint bằng trình duyệt.

### 7.3. Đọc tuổi của mẫu một cách có giới hạn

Tuổi của mẫu marker mà truy vấn đang nhìn thấy:

```promql
time() - timestamp(lab_collection_marker{
  job="orders-management", env="lab"
})
```

Kết quả là số giây giữa thời điểm đánh giá và timestamp mẫu được chọn, không phải “số giây kể từ giao dịch thành công cuối”. Nếu chuỗi không còn xuất hiện, biểu thức cũng có thể không trả phần tử; do đó cần kiểm tra thiếu dữ liệu riêng.

Một gauge được scrape liên tục sẽ có mẫu mới dù giá trị nguồn bị giữ nguyên. Muốn biết nguồn nghiệp vụ cập nhật thành công cần metric có ngữ nghĩa tương ứng, cùng kiểm tra đồng hồ, độ trễ và chu kỳ tác vụ. Đừng đổi tên marker cố định thành heartbeat rồi coi vấn đề đã được giải quyết.

Khi đánh giá chất lượng thu thập, xem đồng thời trạng thái target, thời gian scrape so với timeout và số lượng mẫu. Thời gian scrape tiến sát ngân sách 4s của cấu hình minh họa là dấu hiệu cần điều tra; ngưỡng vận hành thực tế phải xét tải, lịch sử và giới hạn của hệ thống.

## 8. Đặt phép kiểm tra ở đúng vị trí mạng

Probe từ cùng Pod tới 8080 xác minh được một phần cổng chính nhưng có thể bỏ qua DNS công khai, TLS, ingress, chính sách truy cập và bộ cân bằng tải. Probe qua URL công khai đi qua nhiều thành phần hơn nhưng không chỉ ra ngay lỗi thuộc bản sao nào.

Cần xác định mục đích từng vị trí:

| Vị trí kiểm tra | Phạm vi hữu ích | Điểm chưa được bao phủ |
| --- | --- | --- |
| Cùng tiến trình/máy tới management | Chẩn đoán bên trong và xuất dữ liệu | Tuyến người dùng và phần hạ tầng cổng chính |
| Mạng nội bộ tới cổng chính | Kết nối và readiness trên cổng chính | Có thể bỏ qua ingress/TLS công khai |
| Từ mạng gần người dùng qua URL dịch vụ | Đường truy cập bên ngoài theo vị trí đó | Các vùng mạng/người dùng khác và mọi nghiệp vụ khác |
| Thao tác tổng hợp có kiểm tra kết quả | Một luồng nghiệp vụ được chọn | Chức năng không có trong kịch bản |

Một GET nhẹ trả lời sẵn có không kiểm tra được tính đúng đắn của thao tác ghi hoặc giao dịch nhiều bước. Chọn phép kiểm tra có giá trị nhưng có chi phí được kiểm soát. Nếu phải thực hiện thao tác ghi, cần dữ liệu/tài khoản thử nghiệm và cơ chế tránh tạo tác dụng phụ lặp lại.

Trong hệ thống nhiều bản sao, cổng quản trị có `instance` dạng `host:8081` còn probe có thể có `instance` dạng URL. Không ghép chúng chỉ bằng giá trị `instance` rồi mong tự khớp. Chọn danh tính chung như môi trường/dịch vụ/bản sao, hoặc công bố rõ đang kiểm tra ở mức toàn dịch vụ. Chỉ ghép theo `service` có thể làm bằng chứng của bản sao A bị hiểu nhầm cho bản sao B.

## 9. Ma trận xử lý khi các tín hiệu khác nhau

| Management scrape | Probe cổng chính/nghiệp vụ | Hướng điều tra |
| --- | --- | --- |
| Tốt | Tốt | Tiếp tục kiểm tra độ đủ, độ mới và bao phủ; chưa mặc định mọi chức năng tốt |
| Tốt | Cổng chính lỗi | Kiểm tra connector, đường mạng, proxy và tài nguyên phục vụ cổng chính; metric còn có là bằng chứng chẩn đoán hữu ích |
| Tốt | Readiness tốt nhưng nghiệp vụ lỗi | Kiểm tra hợp đồng route, dữ liệu và phụ thuộc nghiệp vụ; bổ sung phạm vi kiểm tra cần thiết |
| Lỗi | Nghiệp vụ tốt | Điều tra đường thu: địa chỉ, cổng, endpoint, xác thực, TLS, timeout và exporter |
| Lỗi hoặc thiếu | Nghiệp vụ cũng lỗi | Ưu tiên giảm ảnh hưởng người dùng, dùng tuyến quan sát độc lập và xác định phạm vi sự cố chung |
| Tốt nhưng thiếu metric chọn lọc | Probe có thể vẫn tốt | Kiểm tra đăng ký metric, đổi nhãn/tên, relabeling và đường lưu trữ phía sau |

Quy trình điều tra ngắn:

1. Ghi rõ target, môi trường, bản sao, đường dẫn và thời điểm bắt đầu. Xác nhận mình đang xem dữ liệu từ đúng nơi đánh giá.
2. Kiểm tra đích có còn được khám phá và số lượng có khớp kiểm kê không.
3. Từ vị trí bộ thu, phân biệt lỗi kết nối, HTTP, chứng chỉ, quyền và định dạng dữ liệu. Không chỉ thử từ vị trí thuận tiện nhất.
4. So sánh management readiness, probe cổng chính và một thao tác nghiệp vụ an toàn. Không dùng một tín hiệu để phủ định vô điều kiện hai tín hiệu còn lại.
5. Đối chiếu endpoint gốc, dữ liệu sau lọc và kết quả ở kho/query backend. Xác minh mẫu còn mới và hiểu đúng thời gian nguồn.
6. Sau thay đổi, kiểm tra lại từng tuyến đã lỗi, độ đủ của target/metric và nghiệp vụ. Việc dashboard có màu xanh trở lại chưa đủ nếu nó xanh vì biểu thức không còn dữ liệu.

Cổng quản trị riêng giúp tách đường truy cập và giữ khả năng chẩn đoán trong một số sự cố. Nó không tạo JVM độc lập: hết bộ nhớ, CPU bão hòa hay lỗi tài nguyên chung vẫn có thể ảnh hưởng cả hai cổng. Không thiết kế tuyến giám sát dự phòng dựa trên giả định hai cổng hoàn toàn độc lập.

## 10. Kiểm thử điểm mù trước khi dựa vào dashboard

Lập kế hoạch gây lỗi trong môi trường thử nghiệm, với điều kiện gỡ lỗi và bằng chứng phục hồi:

- Dừng hoặc chặn riêng cổng chính: xác nhận management có thể còn xanh nhưng probe cổng chính phát hiện lỗi.
- Chặn riêng đường scrape: xác nhận nghiệp vụ còn chạy và tín hiệu chất lượng thu thập báo lỗi.
- Trả 503 hoặc nội dung sai cho một route nghiệp vụ: xác nhận probe có hợp đồng đủ sâu để nhận biết, kể cả readiness vẫn UP.
- Loại một target khỏi discovery: kiểm tra nguồn kiểm kê và điều kiện thiếu đích.
- Loại một metric sau scrape: kiểm tra cảnh báo hợp đồng dữ liệu, không chỉ `up`.
- Làm tác vụ cập nhật dữ liệu ngừng thành công nhưng endpoint vẫn trả lời: kiểm tra metric ngữ nghĩa về lần thành công cuối.
- Kiểm tra độc lập hệ thống giám sát: nếu nơi đánh giá rule ngừng hoạt động, cần một tuyến khác nhận biết được việc mất quan sát.

Các phép thử phải ghi rõ mình chứng minh được tầng nào. Bốn JUnit test trong bài xác nhận HTTP hai cổng và một route mẫu; không tự chứng minh cấu hình mạng Kubernetes, bộ thu production, remote write hay tuyến gửi thông báo.

## 11. Bài tập tự kiểm chứng

1. Tắt `add-additional-paths` trong thí nghiệm và dự đoán assertion nào không còn đúng. Giải thích vì sao gọi management readiness không thay thế được `/readyz` trên cổng chính.
2. Giữ readiness UP nhưng đổi nội dung route nghiệp vụ. So sánh probe chỉ kiểm tra HTTP 200 với probe kiểm tra cả body.
3. Thêm nhiều bản sao có nhãn ổn định rồi thiết kế phép đối chiếu target dự kiến. Chứng minh rule thiếu toàn job không phát hiện được mọi bản sao mất riêng lẻ.
4. So sánh dữ liệu trước và sau metric relabeling. Nêu một trường hợp `up=1` nhưng dashboard nghiệp vụ mất dữ liệu.
5. Thiết kế metric thể hiện lần hoàn thành thành công cuối của một tác vụ định kỳ. Xác định thời điểm cập nhật, đơn vị, giới hạn trễ và điều kiện thiếu mẫu.

Đánh giá sức khỏe phục vụ và sức khỏe quan sát bằng những bằng chứng riêng, rồi ghép chúng theo đúng phạm vi. Nhờ vậy, cổng quản trị riêng trở thành nguồn chẩn đoán hữu ích mà không tạo cảm giác an toàn sai về đường người dùng đang sử dụng.
