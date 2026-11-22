# Thu thập metrics bằng Prometheus và xây dựng dashboard Grafana

Bài thực hành này tạo một ứng dụng Spring Boot xuất metrics qua Actuator, cấu hình Prometheus thu thập định kỳ và cấp sẵn một dashboard Grafana có thể chạy lại từ các tệp cấu hình. Người học sẽ tạo lưu lượng thành công/lỗi để đọc ba tín hiệu HTTP: lưu lượng, tỷ lệ lỗi và độ trễ; sau đó đối chiếu với metrics JVM và bộ đếm nghiệp vụ.

Ví dụ dùng Spring Boot 3.3.5, mã nguồn Java 17+, JVM container Java 21, Prometheus 2.54.1 và Grafana 11.2.2. Đây là các phiên bản minh họa cụ thể, không phải khuyến nghị phiên bản production. Lệnh thao tác phía máy chủ trong bài dùng PowerShell 7, Maven và Docker Compose với Linux containers.

## 1. Hiểu đường đi của dữ liệu

```text
Yêu cầu thử nghiệm
    -> Spring MVC xử lý /demo/orders
        -> Micrometer ghi HTTP Timer và Counter tùy chỉnh
            -> Actuator /actuator/prometheus xuất dữ liệu
                <- Prometheus chủ động scrape mỗi 5 giây
                    -> lưu các chuỗi thời gian
                        <- Grafana gửi truy vấn PromQL
                            -> hiển thị dashboard
```

| Thành phần | Trách nhiệm |
| --- | --- |
| Micrometer | Cung cấp mô hình meter, ghi nhận số đo và nhãn trong ứng dụng |
| Registry Prometheus | Chuyển các meter sang tên và định dạng xuất cho Prometheus |
| Actuator | Cung cấp endpoint HTTP để đọc dữ liệu đã xuất |
| Prometheus | Thu thập định kỳ, gắn nhãn mục tiêu, lưu chuỗi thời gian và thực thi PromQL |
| Grafana | Gửi truy vấn tới Prometheus và trình bày kết quả |

Trong luồng này, ứng dụng không đẩy dữ liệu trực tiếp sang Grafana. Grafana cũng không dùng endpoint Actuator làm datasource Prometheus.

Ba loại meter sẽ quan sát:

- **Counter, bộ đếm tích lũy:** ví dụ số công việc đã hoàn tất. Giá trị trong một tiến trình chỉ tăng; có thể bắt đầu lại khi ứng dụng khởi động lại.
- **Gauge, số đo tức thời:** ví dụ số byte heap đang dùng.
- **Timer, số đo thời lượng:** ghi số lần và tổng thời gian; khi bật histogram còn xuất các bucket để ước lượng phân vị.

Một chuỗi thời gian được nhận diện bằng tên metric cùng toàn bộ tập nhãn. Thay giá trị nhãn có thể tạo thêm chuỗi, không chỉ thay một thuộc tính hiển thị.

## 2. Tạo ứng dụng có thể kiểm chứng

### 2.1. Cấu trúc dự án

```text
metrics-lab/
├── pom.xml
├── Dockerfile
├── compose.yml
├── src/main/
│   ├── java/demo/metrics/
│   │   ├── MetricsLabApplication.java
│   │   └── OrderController.java
│   └── resources/application.yml
└── observability/
    ├── prometheus.yml
    └── grafana/
        ├── dashboards/
        │   └── spring-boot.json
        └── provisioning/
            ├── datasources/
            │   └── prometheus.yml
            └── dashboards/
                └── lab.yml
```

Tạo các tệp đúng vị trí. Đây là dự án minh họa độc lập; không cần sửa cấu hình build của một repository có sẵn.

`pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>metrics-lab</artifactId>
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
            <groupId>io.micrometer</groupId>
            <artifactId>micrometer-registry-prometheus</artifactId>
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
```

Dependency `micrometer-registry-prometheus` cần có trên classpath để Boot thiết lập registry tương ứng. Chỉ thêm Actuator chưa đủ để mặc nhiên có endpoint Prometheus hoạt động.

`src/main/java/demo/metrics/MetricsLabApplication.java`:

```java
package demo.metrics;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MetricsLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(MetricsLabApplication.class, args);
    }
}
```

### 2.2. Endpoint tạo lưu lượng và Counter tùy chỉnh

`src/main/java/demo/metrics/OrderController.java`:

```java
package demo.metrics;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
public class OrderController {
    private final Counter successes;
    private final Counter failures;

    public OrderController(MeterRegistry registry) {
        this.successes = Counter.builder("lab.orders.completed")
                .description("Completed demo order attempts")
                .tag("outcome", "success")
                .register(registry);
        this.failures = Counter.builder("lab.orders.completed")
                .description("Completed demo order attempts")
                .tag("outcome", "failure")
                .register(registry);
    }

    @PostMapping("/demo/orders")
    public ResponseEntity<Map<String, String>> order(
            @RequestParam(name = "outcome", defaultValue = "success") String outcome) {
        Counter counter;
        long delayMs;
        switch (outcome) {
            case "success" -> {
                counter = successes;
                delayMs = 40;
            }
            case "failure" -> {
                counter = failures;
                delayMs = 120;
            }
            default -> throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "outcome must be success or failure");
        }

        try {
            Thread.sleep(delayMs);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new ResponseStatusException(
                    HttpStatus.SERVICE_UNAVAILABLE, "demo work interrupted");
        }

        counter.increment();
        HttpStatus status = outcome.equals("success")
                ? HttpStatus.OK : HttpStatus.SERVICE_UNAVAILABLE;
        return ResponseEntity.status(status).body(Map.of("outcome", outcome));
    }
}
```

Hợp đồng thử nghiệm:

| Request | Mã HTTP | Bộ đếm tùy chỉnh | Thời gian chờ mô phỏng |
| --- | --- | --- | --- |
| `POST /demo/orders?outcome=success` | 200 | `outcome=success` tăng 1 | 40 ms |
| `POST /demo/orders?outcome=failure` | 503 | `outcome=failure` tăng 1 | 120 ms |
| Giá trị outcome khác | 400 | Không tạo/tăng chuỗi nhãn mới | Không thực hiện công việc mô phỏng |

`Thread.sleep` chỉ tạo tình huống có độ trễ để học đọc dashboard. Nó không phải cách mô phỏng đầy đủ tải CPU, cơ sở dữ liệu hay hiệu năng production. Độ trễ HTTP đo được còn có các chi phí xử lý khác nên không bắt buộc chính xác bằng 40 hoặc 120 ms.

Hai counter được đăng ký một lần trong constructor với hai giá trị nhãn hữu hạn. Không đưa trực tiếp tham số request bất kỳ vào `tag("outcome", ...)`; nếu không, người gọi có thể làm số lượng chuỗi tăng liên tục.

Counter này đo các lần thử mô phỏng đã đi đến bước hoàn tất, bao gồm kết quả thành công và thất bại có chủ đích. HTTP Timer tự động đo request HTTP. Hai phạm vi không hoàn toàn đồng nhất: request 400 vẫn thuộc metrics HTTP nhưng không thuộc bộ đếm hoàn tất này.

### 2.3. Bật endpoint và histogram

`src/main/resources/application.yml`:

```yaml
server:
  port: 8080
spring:
  application:
    name: metrics-lab
management:
  endpoints:
    web:
      exposure:
        include: health,prometheus
  metrics:
    tags:
      application: ${spring.application.name}
    distribution:
      percentiles-histogram:
        http.server.requests: true
      slo:
        http.server.requests: 50ms,100ms,250ms,500ms,1s,2s
```

Các lựa chọn có ý nghĩa:

- Chỉ expose `health` và `prometheus` trong bài thực hành.
- Nhãn chung `application=metrics-lab` được áp dụng cho các meter của ứng dụng.
- Bật histogram cho `http.server.requests` để có dữ liệu bucket cho p95.
- Các mốc SLO bổ sung ranh giới bucket tại 50 ms, 100 ms, 250 ms, 500 ms, 1 giây và 2 giây.

Tên trong cấu hình Boot/Micrometer và tên xuất sang Prometheus khác nhau:

| Tên meter trong ứng dụng | Ví dụ tên xuất |
| --- | --- |
| `lab.orders.completed` | `lab_orders_completed_total` |
| `http.server.requests` | `http_server_requests_seconds_count`, `_sum`, `_bucket` |
| `jvm.memory.used` | `jvm_memory_used_bytes` |

Timer xuất thời gian theo giây trong các metric trên. Giá trị 0.12 tương ứng khoảng 120 ms; không hiểu là 0.12 ms.

Histogram làm tăng số lượng chuỗi vì mỗi tổ hợp nhãn có thêm nhiều bucket. Chỉ bật ở phạm vi cần thiết và kiểm soát số lượng URI, trạng thái và nhãn.

## 3. Chạy ba dịch vụ trong cùng mạng Compose

### 3.1. Đóng gói ứng dụng

`Dockerfile`:

```dockerfile
FROM eclipse-temurin:21-jre
WORKDIR /app
COPY target/metrics-lab-1.0.0.jar app.jar
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
```

Dockerfile nhận JAR đã build bằng Maven trên máy chủ. Vì vậy phải chạy `mvn clean package` trước `docker compose up --build`. Nó không tự biên dịch mã nguồn bên trong image.

### 3.2. Cấu hình Prometheus

`observability/prometheus.yml`:

```yaml
global:
  scrape_interval: 5s
  evaluation_interval: 5s

scrape_configs:
  - job_name: spring-boot-lab
    scrape_interval: 5s
    scrape_timeout: 3s
    metrics_path: /actuator/prometheus
    static_configs:
      - targets:
          - app:8080
```

Prometheus truy cập ứng dụng bằng `app:8080` qua DNS nội bộ Compose. Bên trong container Prometheus, `localhost:8080` trỏ tới chính container Prometheus, không trỏ tới ứng dụng.

`job` và `instance` là các nhãn quan trọng do quá trình thu thập bổ sung. Với cấu hình này, job là `spring-boot-lab` và mục tiêu là `app:8080`.

Độ dài timeout scrape là 3 giây, nhỏ hơn chu kỳ scrape 5 giây. Nếu endpoint chậm hơn ngân sách đó, cần điều tra endpoint, tải và kết nối; không mặc nhiên tăng mọi timeout.

### 3.3. Cấp sẵn datasource và dashboard provider

`observability/grafana/provisioning/datasources/prometheus.yml`:

```yaml
apiVersion: 1
datasources:
  - name: Prometheus Lab
    uid: prometheus-lab
    type: prometheus
    access: proxy
    url: http://prometheus:9090
    isDefault: true
    editable: false
    jsonData:
      httpMethod: POST
      timeInterval: 5s
```

Datasource dùng `http://prometheus:9090` vì truy vấn được Grafana server gửi từ bên trong mạng Compose. URL trên trình duyệt của người học là một vị trí khác.

`timeInterval: 5s` khai báo chu kỳ thu thập cho datasource, giúp Grafana tính cửa sổ `$__rate_interval` phù hợp với scrape interval của bài.

`observability/grafana/provisioning/dashboards/lab.yml`:

```yaml
apiVersion: 1
providers:
  - name: spring-boot-lab
    orgId: 1
    folder: Spring Boot Lab
    type: file
    updateIntervalSeconds: 10
    allowUiUpdates: false
    options:
      path: /var/lib/grafana/dashboards
```

Provider đọc JSON dashboard trong thư mục được mount. Trong bài này, tệp JSON là nguồn cấu hình; chỉnh sửa nó để thay đổi dashboard. Không trông chờ thay đổi bằng giao diện sẽ thay thế cấu hình provisioning.

### 3.4. Tệp Compose

`compose.yml`:

```yaml
services:
  app:
    build: .
    environment:
      JAVA_TOOL_OPTIONS: "-Xms128m -Xmx256m"
    ports:
      - "127.0.0.1:8080:8080"

  prometheus:
    image: prom/prometheus:v2.54.1
    command:
      - "--config.file=/etc/prometheus/prometheus.yml"
      - "--storage.tsdb.path=/prometheus"
      - "--storage.tsdb.retention.time=2d"
    volumes:
      - ./observability/prometheus.yml:/etc/prometheus/prometheus.yml:ro
      - prometheus-data:/prometheus
    ports:
      - "127.0.0.1:9090:9090"
    depends_on:
      - app

  grafana:
    image: grafana/grafana:11.2.2
    environment:
      GF_SECURITY_ADMIN_USER: admin
      GF_SECURITY_ADMIN_PASSWORD: ${GRAFANA_ADMIN_PASSWORD:?Set GRAFANA_ADMIN_PASSWORD}
      GF_USERS_ALLOW_SIGN_UP: "false"
    volumes:
      - ./observability/grafana/provisioning:/etc/grafana/provisioning:ro
      - ./observability/grafana/dashboards:/var/lib/grafana/dashboards:ro
      - grafana-data:/var/lib/grafana
    ports:
      - "127.0.0.1:3000:3000"
    depends_on:
      - prometheus

volumes:
  prometheus-data:
  grafana-data:
```

Các cổng được publish trên loopback của máy chủ cho phòng thực hành:

| Địa chỉ mở từ máy chủ | Mục đích |
| --- | --- |
| `http://localhost:8080` | Ứng dụng và endpoint Actuator |
| `http://localhost:9090` | Giao diện/query API của Prometheus |
| `http://localhost:3000` | Grafana |

`depends_on` sắp thứ tự khởi động, không bảo đảm ứng dụng đã sẵn sàng. Prometheus có thể tạm báo target DOWN trong lúc Boot khởi động rồi tự thu thập lại ở các lần sau.

Hai volume có tên giữ dữ liệu Prometheus và Grafana qua việc tạo lại container. Prometheus được đặt thời gian lưu 2 ngày cho bài thực hành; đây không phải chính sách lưu dữ liệu production.

Biến môi trường mật khẩu Grafana phải được đặt trước khi Compose phân giải cấu hình. Mật khẩu khởi tạo chỉ có tác dụng theo cơ chế khởi tạo tài khoản trên dữ liệu Grafana; thay biến môi trường không có nghĩa tự đặt lại mật khẩu của tài khoản đã tồn tại trong volume.

## 4. Dashboard Grafana hoàn chỉnh

Lưu toàn bộ JSON sau vào `observability/grafana/dashboards/spring-boot.json`. UID datasource `prometheus-lab` phải khớp với tệp datasource đã tạo.

Dashboard có biến chọn ứng dụng, ba panel HTTP, bộ nhớ heap, tốc độ hoàn tất công việc mô phỏng, CPU theo instance và trạng thái scrape.

```json
{
  "uid": "spring-boot-metrics-lab",
  "title": "Thực hành Spring Boot Metrics",
  "schemaVersion": 39,
  "version": 1,
  "editable": false,
  "refresh": "5s",
  "time": {
    "from": "now-15m",
    "to": "now"
  },
  "timezone": "browser",
  "tags": [
    "spring-boot",
    "prometheus",
    "lab"
  ],
  "templating": {
    "list": [
      {
        "name": "application",
        "label": "Ứng dụng",
        "type": "query",
        "datasource": {
          "type": "prometheus",
          "uid": "prometheus-lab"
        },
        "definition": "label_values(jvm_memory_used_bytes{job=\"spring-boot-lab\"}, application)",
        "query": {
          "query": "label_values(jvm_memory_used_bytes{job=\"spring-boot-lab\"}, application)",
          "refId": "PrometheusVariableQueryEditor-VariableQuery"
        },
        "refresh": 1,
        "sort": 1,
        "multi": false,
        "includeAll": false,
        "current": {
          "text": "metrics-lab",
          "value": "metrics-lab"
        },
        "options": []
      }
    ]
  },
  "panels": [
    {
      "id": 1,
      "title": "HTTP đơn hàng / giây",
      "type": "timeseries",
      "datasource": {
        "type": "prometheus",
        "uid": "prometheus-lab"
      },
      "gridPos": {
        "x": 0,
        "y": 0,
        "w": 8,
        "h": 8
      },
      "fieldConfig": {
        "defaults": {
          "unit": "reqps",
          "min": 0
        },
        "overrides": []
      },
      "options": {
        "legend": {
          "displayMode": "list",
          "placement": "bottom"
        }
      },
      "targets": [
        {
          "refId": "A",
          "expr": "sum(rate(http_server_requests_seconds_count{job=\"spring-boot-lab\",application=~\"${application:regex}\",uri=\"/demo/orders\",method=\"POST\"}[$__rate_interval]))",
          "legendFormat": "HTTP đơn hàng / giây",
          "range": true,
          "editorMode": "code",
          "instant": false
        }
      ]
    },
    {
      "id": 2,
      "title": "Tỷ lệ HTTP 5xx",
      "type": "stat",
      "datasource": {
        "type": "prometheus",
        "uid": "prometheus-lab"
      },
      "gridPos": {
        "x": 8,
        "y": 0,
        "w": 8,
        "h": 8
      },
      "fieldConfig": {
        "defaults": {
          "unit": "percentunit",
          "min": 0
        },
        "overrides": []
      },
      "options": {
        "colorMode": "value",
        "graphMode": "none",
        "reduceOptions": {
          "calcs": [
            "lastNotNull"
          ],
          "fields": "",
          "values": false
        }
      },
      "targets": [
        {
          "refId": "A",
          "expr": "(sum(rate(http_server_requests_seconds_count{job=\"spring-boot-lab\",application=~\"${application:regex}\",uri=\"/demo/orders\",method=\"POST\",status=~\"5..\"}[$__rate_interval])) or vector(0)) / sum(rate(http_server_requests_seconds_count{job=\"spring-boot-lab\",application=~\"${application:regex}\",uri=\"/demo/orders\",method=\"POST\"}[$__rate_interval]))",
          "legendFormat": "Tỷ lệ HTTP 5xx",
          "range": false,
          "editorMode": "code",
          "instant": true
        }
      ]
    },
    {
      "id": 3,
      "title": "Độ trễ HTTP p95",
      "type": "timeseries",
      "datasource": {
        "type": "prometheus",
        "uid": "prometheus-lab"
      },
      "gridPos": {
        "x": 16,
        "y": 0,
        "w": 8,
        "h": 8
      },
      "fieldConfig": {
        "defaults": {
          "unit": "s",
          "min": 0
        },
        "overrides": []
      },
      "options": {
        "legend": {
          "displayMode": "list",
          "placement": "bottom"
        }
      },
      "targets": [
        {
          "refId": "A",
          "expr": "histogram_quantile(0.95, sum by (le) (rate(http_server_requests_seconds_bucket{job=\"spring-boot-lab\",application=~\"${application:regex}\",uri=\"/demo/orders\",method=\"POST\"}[$__rate_interval])))",
          "legendFormat": "Độ trễ HTTP p95",
          "range": true,
          "editorMode": "code",
          "instant": false
        }
      ]
    },
    {
      "id": 4,
      "title": "Bộ nhớ heap JVM trên các instance",
      "type": "timeseries",
      "datasource": {
        "type": "prometheus",
        "uid": "prometheus-lab"
      },
      "gridPos": {
        "x": 0,
        "y": 8,
        "w": 12,
        "h": 8
      },
      "fieldConfig": {
        "defaults": {
          "unit": "bytes",
          "min": 0
        },
        "overrides": []
      },
      "options": {
        "legend": {
          "displayMode": "list",
          "placement": "bottom"
        }
      },
      "targets": [
        {
          "refId": "A",
          "expr": "sum(jvm_memory_used_bytes{job=\"spring-boot-lab\",application=~\"${application:regex}\",area=\"heap\"})",
          "legendFormat": "Bộ nhớ heap JVM trên các instance",
          "range": true,
          "editorMode": "code",
          "instant": false
        }
      ]
    },
    {
      "id": 5,
      "title": "Đơn mô phỏng hoàn tất / giây",
      "type": "timeseries",
      "datasource": {
        "type": "prometheus",
        "uid": "prometheus-lab"
      },
      "gridPos": {
        "x": 12,
        "y": 8,
        "w": 12,
        "h": 8
      },
      "fieldConfig": {
        "defaults": {
          "unit": "ops",
          "min": 0
        },
        "overrides": []
      },
      "options": {
        "legend": {
          "displayMode": "list",
          "placement": "bottom"
        }
      },
      "targets": [
        {
          "refId": "A",
          "expr": "sum by (outcome) (rate(lab_orders_completed_total{job=\"spring-boot-lab\",application=~\"${application:regex}\"}[$__rate_interval]))",
          "legendFormat": "{{outcome}}",
          "range": true,
          "editorMode": "code",
          "instant": false
        }
      ]
    },
    {
      "id": 6,
      "title": "CPU tiến trình theo instance",
      "type": "timeseries",
      "datasource": {
        "type": "prometheus",
        "uid": "prometheus-lab"
      },
      "gridPos": {
        "x": 0,
        "y": 16,
        "w": 12,
        "h": 8
      },
      "fieldConfig": {
        "defaults": {
          "unit": "percentunit",
          "min": 0
        },
        "overrides": []
      },
      "options": {
        "legend": {
          "displayMode": "list",
          "placement": "bottom"
        }
      },
      "targets": [
        {
          "refId": "A",
          "expr": "process_cpu_usage{job=\"spring-boot-lab\",application=~\"${application:regex}\"}",
          "legendFormat": "{{instance}}",
          "range": true,
          "editorMode": "code",
          "instant": false
        }
      ]
    },
    {
      "id": 7,
      "title": "Trạng thái scrape Prometheus",
      "type": "stat",
      "datasource": {
        "type": "prometheus",
        "uid": "prometheus-lab"
      },
      "gridPos": {
        "x": 12,
        "y": 16,
        "w": 12,
        "h": 8
      },
      "fieldConfig": {
        "defaults": {
          "unit": "none",
          "min": 0,
          "decimals": 0,
          "thresholds": {
            "mode": "absolute",
            "steps": [
              {
                "color": "red",
                "value": null
              },
              {
                "color": "green",
                "value": 1
              }
            ]
          }
        },
        "overrides": []
      },
      "options": {
        "colorMode": "value",
        "graphMode": "none",
        "reduceOptions": {
          "calcs": [
            "lastNotNull"
          ],
          "fields": "",
          "values": false
        }
      },
      "targets": [
        {
          "refId": "A",
          "expr": "up{job=\"spring-boot-lab\"}",
          "legendFormat": "{{instance}}",
          "range": false,
          "editorMode": "code",
          "instant": true
        }
      ]
    }
  ]
}
```

Các điểm cần hiểu từ cấu hình:

- Biến `application` lấy giá trị nhãn từ metrics JVM của job này; không bắt buộc phải có request nghiệp vụ trước khi chọn ứng dụng.
- Các truy vấn HTTP chỉ chọn `POST /demo/orders`, nên request health và request scrape không làm lệch biểu đồ của nghiệp vụ đang học.
- Panel tỷ lệ lỗi và panel `up` dùng truy vấn tức thời để đọc kết quả ở thời điểm hiện tại.
- Các panel thời gian dùng truy vấn theo khoảng thời gian.
- Tỷ lệ lỗi/CPU dùng đơn vị phần trăm từ đầu vào 0–1; p95 dùng giây; heap dùng byte.
- Metrics `up` do Prometheus tạo có nhãn mục tiêu như `job` và `instance`, không tự nhận nhãn chung Micrometer `application`. Panel up được chọn theo job của bài, vốn chỉ có ứng dụng minh họa này.
- Bộ nhớ heap trong panel là tổng trên các instance đang được chọn; CPU được giữ thành từng đường theo instance.

Nếu mở rộng cùng job cho nhiều ứng dụng, cần bổ sung nhãn mục tiêu thích hợp và sửa cách lọc `up`. Không giả định thay biến ứng dụng tự động lọc được mọi metric do Prometheus sinh ra.

### 4.1. Lưu lượng: Counter khác tốc độ

Truy vấn dùng được trực tiếp trong giao diện Prometheus:

```promql
sum(
  rate(http_server_requests_seconds_count{
    job="spring-boot-lab",
    application="metrics-lab",
    uri="/demo/orders",
    method="POST"
  }[1m])
)
```

`_count` là số request tích lũy của Timer. `rate(...[1m])` tính tốc độ trung bình mỗi giây trong cửa sổ 1 phút; `sum` cộng các chuỗi phù hợp.

Tính rate cho từng chuỗi trước rồi mới cộng để xử lý việc counter của các instance đặt lại độc lập. Không dùng trực tiếp giá trị counter tích lũy làm requests/second.

Trong dashboard JSON, cửa sổ được thay bằng `$__rate_interval`. Đây là biến của Grafana, không phải cú pháp biến do Prometheus tự hiểu. Khi thử ở giao diện Prometheus, dùng cửa sổ cụ thể như `[1m]` và nhãn cụ thể như ví dụ trên.

Cửa sổ rate cần đủ nhiều mẫu. Với scrape 5 giây, cửa sổ chỉ 5 giây dễ không có đủ điểm. Tăng tốc độ refresh dashboard không làm Prometheus thu thập dữ liệu thường xuyên hơn.

### 4.2. Tỷ lệ lỗi HTTP 5xx

```promql
(
  sum(
    rate(http_server_requests_seconds_count{
      job="spring-boot-lab",
      application="metrics-lab",
      uri="/demo/orders",
      method="POST",
      status=~"5.."
    }[1m])
  )
  or vector(0)
)
/
sum(
  rate(http_server_requests_seconds_count{
    job="spring-boot-lab",
    application="metrics-lab",
    uri="/demo/orders",
    method="POST"
  }[1m])
)
```

Tử số là tốc độ request 5xx; mẫu số là tốc độ tất cả request thuộc cùng tuyến và phương thức. Kết quả 0.2 là tỷ lệ 20%, không phải 0.2%.

`or vector(0)` ở tử số giúp biểu diễn không có chuỗi 5xx thành tử số 0 khi đã có lưu lượng ở mẫu số. Nó không biến việc thiếu toàn bộ dữ liệu thành một hệ thống khỏe. Nếu không có request trong cửa sổ, mẫu số có thể bằng 0; tỷ lệ khi đó không có ý nghĩa và có thể hiển thị No data/NaN.

Không dùng giá trị 0 thay cho mọi dữ liệu bị thiếu. Khi thấy khoảng trống, kiểm tra panel up và dữ liệu gốc trước.

Đây là tỷ lệ lỗi HTTP 5xx. Nó không mặc nhiên là tỷ lệ thất bại nghiệp vụ của mọi hệ thống, vì một số ứng dụng biểu diễn thất bại nghiệp vụ bằng mã HTTP khác.

### 4.3. Độ trễ p95 từ histogram

```promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(http_server_requests_seconds_bucket{
      job="spring-boot-lab",
      application="metrics-lab",
      uri="/demo/orders",
      method="POST"
    }[1m])
  )
)
```

Các bucket kiểu histogram cổ điển có nhãn `le`, biểu diễn cận trên và số lần tích lũy đến cận đó. Giữ `le` khi cộng dữ liệu từ các instance để `histogram_quantile` còn biết phân bố bucket.

p95 là ước lượng từ histogram: khoảng 95% quan sát có thời gian không lớn hơn phân vị ước lượng đó. Nó không có nghĩa request nào cũng mất đúng bằng p95 và không phải giá trị tối đa.

Không lấy trung bình p95 của từng instance để suy ra p95 chung. Muốn gộp, gộp bucket phù hợp rồi tính phân vị. Độ chính xác còn phụ thuộc ranh giới bucket và dữ liệu trong cửa sổ.

Các mốc SLO ở cấu hình histogram chỉ thêm ranh giới đo. Chúng không tự tạo cam kết SLO, kiểm tra tỷ lệ đạt mục tiêu hoặc gửi cảnh báo.

### 4.4. Đối chiếu nghiệp vụ và tài nguyên

Panel công việc mô phỏng tính rate của `lab_orders_completed_total` và nhóm theo `outcome`. Sau khi tạo dữ liệu, sẽ có đường success và failure. Chuỗi nhãn được giới hạn ở hai giá trị đã đăng ký trong mã.

Heap là số đo tức thời nên không áp dụng `rate` như với counter. CPU trong panel là mức sử dụng tiến trình do meter cung cấp; đơn vị phần trăm trên dashboard không tự biến nó thành số lõi CPU đã tiêu thụ.

Số đo CPU có thể phụ thuộc khả năng hỗ trợ của JVM/hệ điều hành. Nếu riêng panel CPU không có dữ liệu, kiểm tra metric có được xuất không trước khi kết luận toàn bộ quá trình thu thập hỏng.

## 5. Khởi động và kiểm chứng từng chặng

### 5.1. Build và chạy

Sau khi đã tạo đủ các tệp, tại thư mục có `pom.xml`:

```powershell
mvn clean package
```

Trong PowerShell 7, nhập mật khẩu khởi tạo cho Grafana mà không hiển thị ký tự gõ:

```powershell
$env:GRAFANA_ADMIN_PASSWORD = Read-Host -MaskInput "Mật khẩu Grafana cho bài thực hành"
docker compose config --quiet
docker compose up -d --build
docker compose ps
```

Lần đầu cần truy cập mạng để Maven tải dependency và Docker tải base image/image. Docker daemon phải đang hoạt động ở chế độ Linux containers.

Compose chỉ bind các cổng công khai về 127.0.0.1 cho việc học trên máy hiện tại. Không dùng nguyên cấu hình này làm thiết kế bảo mật/triển khai production.

### 5.2. Chặng 1: ứng dụng thực sự xuất metrics

```powershell
curl.exe -i http://localhost:8080/actuator/health
curl.exe -i http://localhost:8080/actuator/prometheus
```

Endpoint Prometheus phải trả nội dung metrics với HTTP 200, không phải trang đăng nhập hoặc JSON từ endpoint `/actuator/metrics`. Các dòng HELP/TYPE và các mẫu giá trị thể hiện định dạng xuất; nội dung đầy đủ thay đổi theo thời điểm và JVM.

Tạo hai request để các chuỗi HTTP của tuyến nghiệp vụ xuất hiện:

```powershell
curl.exe -i -X POST "http://localhost:8080/demo/orders?outcome=success"
curl.exe -i -X POST "http://localhost:8080/demo/orders?outcome=failure"
```

Request thứ nhất trả HTTP 200 với JSON:

```json
{"outcome":"success"}
```

Request thứ hai trả HTTP 503 có chủ đích với JSON:

```json
{"outcome":"failure"}
```

Đọc lại endpoint metrics và tìm các tên:

```text
lab_orders_completed_total
http_server_requests_seconds_count
http_server_requests_seconds_sum
http_server_requests_seconds_bucket
jvm_memory_used_bytes
```

Không cố đối chiếu toàn bộ response thành một chuỗi stdout cố định: giá trị JVM, thời gian và số lần scrape thay đổi liên tục. Hãy kiểm tra tên metric, nhãn và quan hệ giữa các số đo.

### 5.3. Chặng 2: Prometheus thu thập thành công

Mở [Prometheus](http://localhost:9090), vào trang Targets và tìm job `spring-boot-lab`. Mục tiêu cần chuyển sang UP sau khi ứng dụng khởi động và một lượt scrape thành công.

Trong trang truy vấn, chạy:

```promql
up{job="spring-boot-lab"}
```

Giá trị 1 nghĩa lần scrape gần nhất của mục tiêu đó thành công; 0 nghĩa lần scrape thất bại. Nó không đồng nghĩa mọi nghiệp vụ của ứng dụng đều khỏe.

Tiếp tục kiểm tra dữ liệu nghiệp vụ thô:

```promql
lab_orders_completed_total{job="spring-boot-lab",application="metrics-lab"}
```

Nếu endpoint ứng dụng có dữ liệu nhưng truy vấn Prometheus chưa có, hãy kiểm tra target và chờ lượt scrape; không chuyển ngay sang sửa dashboard.

Có thể kiểm tra tệp cấu hình trong container bằng:

```powershell
docker compose exec prometheus promtool check config /etc/prometheus/prometheus.yml
```

### 5.4. Chặng 3: Grafana đọc đúng Prometheus

Mở [Grafana](http://localhost:3000), đăng nhập bằng user `admin` và mật khẩu vừa nhập. Tìm thư mục `Spring Boot Lab`, mở dashboard `Thực hành Spring Boot Metrics`.

Chọn ứng dụng `metrics-lab`, khoảng thời gian 15 phút gần nhất và quan sát các panel. Datasource đã được cấp sẵn với UID cố định; không cần nhập lại URL Prometheus qua giao diện.

Nếu sửa datasource provisioning, khởi động lại Grafana để áp dụng cấu hình tương ứng. Provider dashboard trong ví dụ kiểm tra thay đổi tệp JSON định kỳ; vẫn cần giữ JSON hợp lệ và chờ nó được nạp.

## 6. Tạo lưu lượng để đọc dashboard

Chạy vòng lặp sau trong PowerShell. Cứ năm request thì có một request failure. Script tuần tự nên thời gian nghỉ, độ trễ xử lý và chi phí mạng cùng quyết định tốc độ thực tế.

```powershell
for ($requestIndex = 1; $requestIndex -le 300; $requestIndex++) {
    $outcome = if ($requestIndex % 5 -eq 0) { "failure" } else { "success" }
    $httpCode = & curl.exe --silent --show-error -o NUL -w "%{http_code}" -X POST "http://localhost:8080/demo/orders?outcome=$outcome"

    if ($httpCode -ne "200" -and $httpCode -ne "503") {
        Write-Warning "Mã HTTP ngoài dự kiến: $httpCode"
    }
    Start-Sleep -Milliseconds 100
}
```

503 là kết quả đã chủ động tạo ở đây, nên vòng lặp không coi riêng mã đó là lỗi thực thi ngoài dự kiến. Các lệnh này dùng `NUL` của Windows để bỏ response body.

Quan sát sau khi có đủ nhiều mẫu, thường cần khoảng 30–60 giây của bài thực hành:

| Panel | Quan sát cần giải thích |
| --- | --- |
| HTTP đơn hàng / giây | Có lưu lượng; không phải tổng counter tăng dần từ khi khởi động |
| Tỷ lệ HTTP 5xx | Tiến gần tỷ lệ request failure trong cửa sổ; không bắt buộc đúng 20% ở từng thời điểm |
| Độ trễ HTTP p95 | Phản ánh phần chậm trong tập request; không phải trung bình 40 ms và 120 ms |
| Đơn mô phỏng hoàn tất / giây | Có hai đường success/failure với phạm vi như mã đã định nghĩa |
| Heap JVM | Có thể tăng/giảm theo cấp phát và thu gom rác, không cần tăng đơn điệu |
| CPU theo instance | Biểu diễn mức sử dụng tiến trình, không phải thời gian chờ sleep |
| Trạng thái scrape | 1 khi Prometheus thu thập được mục tiêu |

Khi dừng tạo tải, tốc độ giảm về 0 sau khi các request trước rời cửa sổ tính. Tỷ lệ lỗi và p95 có thể không còn giá trị hữu ích khi không có quan sát. Phải đọc cùng khoảng thời gian và trạng thái scrape.

Muốn thử sự khác biệt giữa metrics HTTP và counter nghiệp vụ, gửi một request với `outcome=unknown`. Nó trả 400 và được tính vào HTTP Timer, nhưng không tạo chuỗi `outcome=unknown` cho counter hoàn tất.

## 7. Tự gây lỗi để học cách chẩn đoán

### 7.1. Dừng ứng dụng nhưng giữ hệ thống quan sát

```powershell
docker compose stop app
```

Sau lượt scrape tiếp theo, target của ứng dụng thất bại và `up` phải phản ánh điều đó. Dữ liệu lịch sử vẫn nằm trong Prometheus. Một dashboard còn thấy đường lịch sử không có nghĩa ứng dụng vẫn đang xuất dữ liệu mới.

Khởi động lại:

```powershell
docker compose start app
```

Counter trong tiến trình ứng dụng mới có thể bắt đầu lại. Truy vấn `rate` được thiết kế để xử lý sự đặt lại counter trong chuỗi, nhưng kết quả ngay sau khởi động còn phụ thuộc số mẫu và cửa sổ. Không trừ hai số counter bất kỳ rồi coi chênh lệch âm là số request âm.

Nếu target bị xóa khỏi cấu hình thay vì chỉ ngừng trả lời, cần phân biệt “không còn chuỗi mục tiêu” với `up=0`. Không dùng một panel up đơn giản thay cho toàn bộ chiến lược phát hiện mất mục tiêu.

### 7.2. Bảng tìm lỗi theo chặng

| Hiện tượng | Kiểm tra trước |
| --- | --- |
| `/actuator/prometheus` trả 404 | Dependency registry, exposure, đường dẫn base/context và điều kiện tự cấu hình |
| Endpoint trả 401/403 hoặc HTML đăng nhập | Chính sách bảo mật áp dụng lên đường scrape |
| Target DOWN với lỗi kết nối | App đã chạy chưa; target có dùng `app:8080` đúng mạng Compose không |
| Target DOWN với timeout | Độ trễ endpoint, tải ứng dụng và scrape timeout |
| Target UP nhưng chưa có `http_server_requests_seconds_count` cho tuyến cần xem | Đã thực sự gọi endpoint đó chưa; nhãn URI/method có đúng không |
| Có `_count`, `_sum` nhưng thiếu `_bucket` | Histogram đã bật đúng tên meter và ứng dụng đã khởi động lại chưa |
| Prometheus có dữ liệu nhưng Grafana No data | UID/URL datasource, biến ứng dụng, nhãn truy vấn và khoảng thời gian |
| Truy vấn rate ít điểm hoặc trống | Số mẫu, scrape interval và cửa sổ rate |
| Tỷ lệ lỗi rất khác dự kiến | Tử/mẫu có cùng tuyến, phương thức, ứng dụng và cửa sổ không; có thêm 4xx không |
| p95 không có ý nghĩa khi ít request | Số quan sát và bucket; không suy ra độ tin cậy chỉ từ một con số |
| JSON dashboard không xuất hiện | Mount đúng tệp/thư mục, JSON hợp lệ, provider và log Grafana |

Các lệnh đọc log:

```powershell
docker compose logs --tail 100 app
docker compose logs --tail 100 prometheus
docker compose logs --tail 100 grafana
```

Chẩn đoán theo thứ tự ứng dụng → Prometheus → Grafana giúp tránh sửa truy vấn khi nguồn dữ liệu thực tế chưa được thu thập.

## 8. Những giới hạn cần giữ rõ khi mở rộng

### 8.1. Nhãn và số lượng chuỗi

Giữ nhãn ở tập giá trị có kiểm soát. Không dùng order ID, user ID, email, trace ID, URL thô có tham số hoặc nội dung exception làm nhãn metric.

Nhãn `uri` của HTTP nên biểu diễn mẫu tuyến, chẳng hạn `/orders/{id}`, thay vì một giá trị đường dẫn khác nhau cho từng đơn. Histogram còn nhân thêm số chuỗi theo số bucket; không bật histogram cho mọi meter một cách không tính toán.

Log và trace phù hợp hơn cho việc truy một yêu cầu cụ thể. Metrics phù hợp để tổng hợp xu hướng và tỷ lệ trên những tập nhãn có giới hạn.

### 8.2. Bảo mật và chi phí vận hành

Endpoint metrics có thể lộ tên dịch vụ, tuyến, tài nguyên và nhãn nội bộ. Khi triển khai thực tế, chọn chính sách mạng và xác thực cho luồng Prometheus → ứng dụng; nếu endpoint cần xác thực, Prometheus phải được cấu hình để scrape đúng hợp đồng đó.

Không đưa credential vào nhãn, JSON dashboard hoặc URL truy vấn. Giới hạn lượng dữ liệu, thời gian lưu, dung lượng volume và chi phí truy vấn theo nhu cầu thực tế.

Dashboard này chưa tạo cảnh báo. Ngưỡng SLO, cảnh báo, tuyến thông báo và cách xử lý sự cố là các quyết định cần thiết kế riêng. Không coi một dashboard có biểu đồ là hệ thống giám sát production đã hoàn chỉnh.

### 8.3. Khả năng lặp lại và phạm vi kiểm chứng

Các tệp provisioning giúp dựng lại datasource và dashboard. Chúng không bảo đảm hai lần chạy có cùng mọi giá trị: JVM, tải máy, thời điểm scrape và dữ liệu lịch sử khác nhau.

Kiểm tra mã bằng HTTP giả lập có thể xác nhận counter, HTTP Timer, nhãn và histogram được xuất đúng. Nó không thay thế kiểm tra Prometheus thực sự scrape được container hoặc xác nhận dashboard hiển thị trong Grafana. Cần đi đủ ba chặng ở mục 5 khi chạy môi trường thật.

Dừng phòng thực hành:

```powershell
docker compose down
Remove-Item Env:GRAFANA_ADMIN_PASSWORD
```

`docker compose down` ở đây không yêu cầu xóa các named volume. Khi chạy lại với volume Grafana cũ, dùng tài khoản/mật khẩu đã lưu trong dữ liệu đó.

## 9. Tiêu chí nghiệm thu

1. Registry Prometheus được tạo và `/actuator/prometheus` trả dữ liệu metrics.
2. HTTP request thành công/lỗi tạo đúng bộ đếm tùy chỉnh, không tạo nhãn từ đầu vào tùy ý.
3. HTTP Timer có count/sum và histogram bucket theo cấu hình.
4. Prometheus target UP và đọc được metrics của ứng dụng bằng PromQL.
5. Datasource Grafana trỏ đúng địa chỉ mạng nội bộ Prometheus và dashboard được nạp từ JSON.
6. Truy vấn lưu lượng dùng rate của counter; tỷ lệ lỗi dùng tử/mẫu cùng phạm vi; p95 được tính từ bucket.
7. Đơn vị thời gian, tỷ lệ và bộ nhớ đúng; dữ liệu thiếu được phân biệt với giá trị 0.
8. Tạo tải, dừng tải và khởi động lại app đều có thể giải thích từ hành vi metric và cửa sổ truy vấn.
9. Nhãn có giới hạn, đường scrape có chính sách truy cập phù hợp và dữ liệu lịch sử được quản lý rõ ràng.

Khi đọc một panel, luôn xác định nó đo điều gì, chọn những chuỗi nào, tổng hợp trong cửa sổ nào và dùng đơn vị gì. Những câu hỏi đó nối số đo trong mã với thông tin thực sự hữu ích trên dashboard.
