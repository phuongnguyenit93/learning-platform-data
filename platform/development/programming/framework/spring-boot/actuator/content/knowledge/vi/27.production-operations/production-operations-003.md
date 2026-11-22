# Xây dựng dashboard cho lưu lượng, lỗi, độ trễ và mức sử dụng tài nguyên

## 1. Dashboard phải giúp đưa ra quyết định vận hành

Bảng theo dõi (dashboard) là tập các biểu đồ được tổ chức để trả lời một nhóm câu hỏi. Với dịch vụ HTTP chạy trên Spring Boot, người trực hệ thống cần biết:

- Ứng dụng đang nhận bao nhiêu yêu cầu?
- Có bao nhiêu yêu cầu thất bại, thuộc nhóm nào?
- Người dùng đang phải chờ bao lâu?
- Bản sao ứng dụng nào đang thiếu tài nguyên hoặc có dấu hiệu quá tải?

Bốn nhóm tín hiệu này phải được đọc cùng nhau. Lưu lượng giảm có thể do nhu cầu giảm, nhưng cũng có thể do một bản sao ngừng nhận yêu cầu. CPU thấp không loại trừ việc ứng dụng đang chờ cơ sở dữ liệu. Độ trễ trung bình thấp cũng chưa chứng minh những yêu cầu chậm nhất vẫn đáp ứng mục tiêu.

Một dashboard hữu ích có hai tầng:

1. **Tầng dịch vụ:** tổng lưu lượng, tỷ lệ lỗi và phân bố độ trễ của phạm vi nghiệp vụ đang theo dõi.
2. **Tầng từng bản sao:** CPU, bộ nhớ, luồng và tài nguyên có giới hạn để tìm nơi phát sinh bất thường.

Bài này dùng Spring Boot **3.3.x**, Micrometer, Prometheus và Grafana. Ví dụ thực hành dùng một ứng dụng Servlet trên máy cá nhân. Cấu hình production cần giữ cùng ý nghĩa phép đo nhưng thay địa chỉ, quyền truy cập và cơ chế phát hiện target cho phù hợp.

## 2. Hiểu đường đi của số liệu

```text
Yêu cầu HTTP / hoạt động JVM
          ↓
Micrometer ghi nhận số đo trong ứng dụng
          ↓
Actuator /actuator/prometheus xuất số liệu
          ↓  Prometheus chủ động lấy theo chu kỳ
Prometheus lưu chuỗi thời gian
          ↓  Grafana gửi truy vấn PromQL
Dashboard hiển thị kết quả theo thời gian và nhãn
```

Endpoint Prometheus xuất số liệu theo định dạng để hệ thống thu thập đọc. [REST API Prometheus của Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/prometheus.html)

Grafana gửi truy vấn tới nguồn dữ liệu để dựng biểu đồ; trong mô hình này nguồn đó là Prometheus. [Truy vấn dữ liệu trong Grafana](https://grafana.com/docs/grafana/latest/visualizations/panels-visualizations/query-transform-data/)

Không lấy giá trị hiện tại từ endpoint rồi coi đó là lịch sử dài hạn. Lịch sử cần được hệ thống số liệu lưu lại. Cũng không mở thêm `env`, `beans` hoặc dump chỉ vì muốn làm dashboard cho bốn nhóm tín hiệu trên.

### Ba dạng số liệu cần nhận ra

| Dạng | Ý nghĩa | Cách sử dụng trong bài |
| --- | --- | --- |
| Bộ đếm tích lũy (counter) | Đếm sự kiện, có thể về lại giá trị thấp khi tiến trình khởi động lại | Tính tốc độ yêu cầu và lỗi từ phần tăng theo thời gian |
| Giá trị tức thời (gauge) | Có thể tăng hoặc giảm | Vẽ CPU, bộ nhớ, số kết nối đang dùng |
| Histogram | Ghi phân bố quan sát thành các khoảng | Tính p95/p99 từ các bucket của độ trễ |

Với counter, Prometheus `rate()` tính tốc độ tăng trung bình mỗi giây và xử lý counter reset. Khi gộp nhiều bản sao, tính rate từng chuỗi trước rồi cộng. [Hàm rate của Prometheus](https://prometheus.io/docs/prometheus/latest/querying/functions/#rate)

## 3. Chuẩn bị một ứng dụng thí nghiệm có số liệu thật

Dùng **dự án Spring Boot 3.3.x Servlet riêng**, JDK 21 và Gradle Wrapper đã có sẵn. Các đoạn sau bổ sung vào dự án đó; không phải hướng dẫn thay đổi ứng dụng production đang phục vụ.

### 3.1. Dependency và cấu hình ứng dụng

Bổ sung dependency trong `build.gradle` của dự án đã dùng plugin và quản lý phiên bản Spring Boot:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
}
```

Tạo `src/main/resources/application.yml` trong dự án thí nghiệm:

```yaml
spring:
  application:
    name: orders-lab

server:
  address: 127.0.0.1
  port: 8080

management:
  server:
    address: 127.0.0.1
    port: 9001
  endpoints:
    enabled-by-default: false
    web:
      exposure:
        include: [health, prometheus]
  endpoint:
    health:
      enabled: true
    prometheus:
      enabled: true
  metrics:
    tags:
      application: orders-lab
    distribution:
      percentiles-histogram:
        "http.server.requests": true
      slo:
        "http.server.requests": 100ms,300ms,1s
```

Spring Boot ghi số liệu HTTP dưới tên `http.server.requests`; cấu hình distribution cho phép xuất histogram và thêm các mốc thời gian cần quan sát. [Số liệu HTTP và cấu hình từng meter](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html)

Histogram hỗ trợ gộp bucket giữa các bản sao trước khi ước lượng percentile. Percentile tính sẵn tại từng tiến trình không có tính chất gộp như vậy. [Histogram và percentile của Micrometer](https://docs.micrometer.io/micrometer/reference/concepts/histogram-quantiles.html)

Các mốc 100 ms, 300 ms, 1 s là lựa chọn cho bài thử. Đặt bucket theo khoảng thời gian thực sự cần phân biệt; không tăng số bucket vô hạn.

Cấu hình dùng loopback vì Prometheus sẽ chạy trực tiếp trên cùng máy. Với container hoặc máy khác, địa chỉ cần truy cập được từ nơi chạy bộ thu thập. Production cần giới hạn nguồn mạng và xác thực phù hợp; không công bố cổng quản trị trực tiếp ra Internet.

### 3.2. Tạo ba đường dẫn có hành vi dễ kiểm chứng

Đặt tệp `src/main/java/lab/dashboard/DashboardLabApplication.java` trong dự án thí nghiệm. Chỉ giữ một lớp khởi động chính phù hợp trong dự án đó:

```java
package lab.dashboard;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class DashboardLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(DashboardLabApplication.class, args);
    }
}

@RestController
@RequestMapping("/demo")
class DemoController {
    @GetMapping("/ok")
    public String ok() {
        return "ok";
    }

    @GetMapping("/fail")
    public ResponseEntity<String> fail() {
        return ResponseEntity.status(500).body("failed");
    }

    @GetMapping("/slow")
    public String slow() throws InterruptedException {
        Thread.sleep(250);
        return "slow";
    }
}
```

Mã này chạy trong Spring Boot với các dependency bên trên, không biên dịch bằng `javac` đơn lẻ khi thiếu classpath.

Khởi động trên Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Trên Linux/macOS dùng `./gradlew bootRun`. Nếu dự án thí nghiệm có Spring Security, cấu hình quyền cho các đường dẫn dùng trong bài; ví dụ này giả định chưa thêm thư viện bảo mật.

Kiểm tra bằng chương trình `curl.exe` trên Windows:

```powershell
curl.exe -i http://127.0.0.1:8080/demo/ok
curl.exe -i http://127.0.0.1:8080/demo/fail
curl.exe -i http://127.0.0.1:8080/demo/slow
curl.exe http://127.0.0.1:9001/actuator/prometheus
```

Ba phản hồi nghiệp vụ có thân lần lượt là `ok`, `failed`, `slow`; mã trạng thái lần lượt là 200, 500, 200. Lệnh gọi slow chờ ít nhất thời gian ngủ trong controller cộng thêm chi phí xử lý. Không coi độ trễ quan sát được là chính xác 250 ms.

## 4. Cấu hình Prometheus và xác nhận chuỗi thời gian

Ví dụ này giả định Prometheus và Grafana đã được cài, chạy trực tiếp trên máy thí nghiệm. Tạo `prometheus.yml`:

```yaml
global:
  scrape_interval: 15s
  scrape_timeout: 5s

scrape_configs:
  - job_name: orders-lab
    metrics_path: /actuator/prometheus
    static_configs:
      - targets: ["127.0.0.1:9001"]
        labels:
          environment: lab
```

Khởi động Prometheus với tệp trên, ví dụ trên Windows:

```powershell
.\prometheus.exe --config.file=prometheus.yml
```

Target và đường dẫn được khai báo trong cấu hình scrape. [Cấu hình Prometheus](https://prometheus.io/docs/prometheus/latest/configuration/configuration/)

Nếu Prometheus chạy trong container, `127.0.0.1` là chính container đó; phải thay bằng địa chỉ ứng dụng truy cập được từ container. Tương tự, URL nguồn dữ liệu Grafana phải truy cập được từ máy chủ Grafana.

### 4.1. Chốt bộ nhãn trước khi viết dashboard

Trong bài:

| Nhãn | Nguồn | Ý nghĩa |
| --- | --- | --- |
| `job="orders-lab"` | Cấu hình scrape | Nhóm target của ứng dụng thí nghiệm |
| `instance` | Prometheus gắn khi scrape | Target cụ thể, ví dụ `127.0.0.1:9001` |
| `environment="lab"` | Nhãn target trong cấu hình scrape | Môi trường |
| `application="orders-lab"` | Common tag trong ứng dụng | Tên ứng dụng trên các meter do ứng dụng xuất |
| `method`, `uri`, `status` | Số liệu HTTP | Phân loại yêu cầu |

Đặt environment ở **target** giúp cả số liệu ứng dụng và `up` có nhãn đó. Common tag nằm trong dữ liệu ứng dụng không tự trở thành nhãn của `up`.

Prometheus tự tạo `up`: 1 khi scrape thành công, 0 khi scrape thất bại. [Job, instance và các chuỗi tự sinh](https://prometheus.io/docs/concepts/jobs_instances/)

Kiểm tra trong giao diện truy vấn Prometheus:

```promql
up{job="orders-lab", environment="lab"}
```

Sau khi gọi các API thí nghiệm, kiểm tra:

```promql
http_server_requests_seconds_count{job="orders-lab", environment="lab"}
```

```promql
http_server_requests_seconds_bucket{job="orders-lab", environment="lab"}
```

Phải có dữ liệu và các nhãn đúng trước khi dựng biểu đồ. HTTP meter có thể chỉ xuất hiện sau khi có yêu cầu. Nếu thiếu bucket, kiểm tra cấu hình histogram và việc khởi động lại ứng dụng.

Các tên Prometheus trong bài dùng dạng xuất phổ biến của timer HTTP. Luôn đối chiếu với dữ liệu endpoint thực tế, nhất là khi nâng Micrometer hoặc đổi quy ước đặt tên.

### 4.2. Giữ số tổ hợp nhãn trong phạm vi quản lý được

Dùng nhãn URI dạng mẫu, ví dụ `/orders/{id}`, thay vì từng đường dẫn chứa mã đơn hàng. Không thêm user ID, request ID, email hoặc token làm nhãn số liệu.

Mỗi tổ hợp nhãn tạo một chuỗi thời gian. Bucket còn nhân thêm số chuỗi của histogram. [Quy ước tên và nhãn Prometheus](https://prometheus.io/docs/practices/naming/)

Có thể lưu ID của một yêu cầu trong log/trace để điều tra riêng. Dashboard cần phân nhóm đủ ổn định để so sánh theo thời gian.

## 5. Các panel lưu lượng, lỗi và độ trễ

Các truy vấn bên dưới dùng cửa sổ **5 phút**, chạy được trực tiếp trong Prometheus. Trên Grafana có thể thay đồng bộ `[5m]` bằng `[$__rate_interval]`; cấu hình scrape interval của nguồn dữ liệu phải khớp 15 giây trong bài. [Biến rate interval của Grafana](https://grafana.com/docs/grafana/latest/datasources/prometheus/template-variables/#use-__rate_interval)

Mọi panel HTTP cùng loại bỏ URI quản trị và probe bằng bộ lọc:

```text
uri!~"/actuator.*|/livez|/readyz"
```

Bộ lọc này giả định đường dẫn quản trị/probe mặc định. Nếu ứng dụng đổi đường dẫn, cập nhật nhất quán ở mọi truy vấn. Với hệ thống có nhiều loại API, xác định rõ phạm vi nghiệp vụ cần đo thay vì gộp tất cả.

### 5.1. Tổng lưu lượng: số yêu cầu mỗi giây

```promql
sum(
  rate(http_server_requests_seconds_count{
    job="orders-lab",
    environment="lab",
    uri!~"/actuator.*|/livez|/readyz"
  }[5m])
)
```

Đặt panel dạng Time series, đơn vị `req/s`. Giá trị 20 nghĩa là tốc độ trung bình 20 yêu cầu hoàn tất mỗi giây trong cửa sổ đang xét.

Không vẽ counter thô rồi đặt tên “RPS”. Counter thô tăng dần qua thời gian; nó trả lời câu hỏi khác.

Để xem phân bố tải giữa các bản sao, giữ nhãn instance:

```promql
sum by (instance) (
  rate(http_server_requests_seconds_count{
    job="orders-lab",
    environment="lab",
    uri!~"/actuator.*|/livez|/readyz"
  }[5m])
)
```

Hai biểu đồ cùng cần thiết: tổng dịch vụ cho biết nhu cầu; từng instance giúp nhận ra tải lệch hoặc một bản sao không nhận yêu cầu.

### 5.2. Số lỗi mỗi giây và tỷ lệ lỗi

Ở đây định nghĩa lỗi máy chủ bằng **HTTP 5xx**. Chọn định nghĩa này rõ ràng trong mô tả panel. 4xx và lỗi nghiệp vụ trả về HTTP 200 cần các panel hoặc meter riêng theo hợp đồng của hệ thống.

Tốc độ lỗi 5xx:

```promql
sum(
  rate(http_server_requests_seconds_count{
    job="orders-lab",
    environment="lab",
    uri!~"/actuator.*|/livez|/readyz",
    status=~"5.."
  }[5m])
)
```

Tỷ lệ lỗi 5xx, đơn vị phần trăm:

```promql
100 *
(
  sum(
    rate(http_server_requests_seconds_count{
      job="orders-lab",
      environment="lab",
      uri!~"/actuator.*|/livez|/readyz",
      status=~"5.."
    }[5m])
  )
  or
  (
    0 * sum(
      rate(http_server_requests_seconds_count{
        job="orders-lab",
        environment="lab",
        uri!~"/actuator.*|/livez|/readyz"
      }[5m])
    )
  )
)
/
(
  sum(
    rate(http_server_requests_seconds_count{
      job="orders-lab",
      environment="lab",
      uri!~"/actuator.*|/livez|/readyz"
    }[5m])
  ) > 0
)
```

Giải thích từng phần:

- Tử số là tốc độ lỗi của cùng phạm vi yêu cầu.
- Nhánh `or (0 * ...)` cung cấp số 0 khi đã có số liệu yêu cầu nhưng chưa có chuỗi 5xx.
- Mẫu số dùng phép so sánh lọc `> 0`, **không dùng `bool`**, để giữ giá trị tốc độ dương làm mẫu số.
- Khi không có yêu cầu trong cửa sổ, không có tỷ lệ có ý nghĩa để hiển thị. Panel nên thể hiện không có dữ liệu tỷ lệ, đồng thời có panel RPS và trạng thái scrape để giải thích.

Các phép toán vector, toán tử tập hợp và phép so sánh lọc có ý nghĩa khác nhau trong PromQL. [Toán tử Prometheus](https://prometheus.io/docs/prometheus/latest/querying/operators/)

Đừng thay mẫu số bằng `clamp_min(..., 1)` chỉ để hết lỗi chia cho 0. Với lưu lượng 0,1 yêu cầu/giây, thay mẫu số thành 1 làm tỷ lệ lỗi sai đi mười lần.

Cũng không trung bình cộng tỷ lệ của các instance. Ví dụ trong cùng khoảng thời gian:

| Instance | Tổng yêu cầu | Lỗi | Tỷ lệ |
| --- | ---: | ---: | ---: |
| A | 100 | 1 | 1% |
| B | 1 | 1 | 100% |
| Toàn dịch vụ | 101 | 2 | Khoảng 1,98% |

Trung bình 1% và 100% thành 50,5% không phản ánh tỷ lệ lỗi của 101 yêu cầu.

### 5.3. Độ trễ trung bình có trọng số

```promql
sum(
  rate(http_server_requests_seconds_sum{
    job="orders-lab",
    environment="lab",
    uri!~"/actuator.*|/livez|/readyz"
  }[5m])
)
/
(
  sum(
    rate(http_server_requests_seconds_count{
      job="orders-lab",
      environment="lab",
      uri!~"/actuator.*|/livez|/readyz"
    }[5m])
  ) > 0
)
```

Kết quả có đơn vị **giây**: tổng thời gian xử lý chia cho tổng số yêu cầu. Grafana có thể hiển thị đơn vị seconds với cách định dạng phù hợp, hoặc nhân 1000 và chọn milliseconds. Không nhân 1000 rồi vẫn ghi đơn vị seconds.

Ví dụ, 100 yêu cầu mất 10 ms mỗi yêu cầu và một yêu cầu mất 1000 ms: trung bình chung là `2000 / 101 ≈ 19,802 ms`, không phải 505 ms.

### 5.4. p95 và p99: quan sát phần đuôi độ trễ

p95 là ước lượng mốc mà khoảng 95% quan sát không vượt quá trong cửa sổ và phạm vi được chọn. Nó không phải 95% của giá trị lớn nhất.

```promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(http_server_requests_seconds_bucket{
      job="orders-lab",
      environment="lab",
      uri!~"/actuator.*|/livez|/readyz"
    }[5m])
  )
)
```

Với histogram cổ điển, nhãn `le` xác định cận trên của bucket. Giữ `le` khi cộng các bucket rồi tính percentile; thay 0.95 bằng 0.99 để có p99. [Histogram trong Prometheus](https://prometheus.io/docs/practices/histograms/)

Không lấy trung bình p95 của các instance. Hãy gộp phân bố trước, tính percentile sau. Các instance cần dùng cùng cách định nghĩa và ranh giới bucket để so sánh/gộp nhất quán.

Muốn tìm API chậm, giữ thêm phương thức và mẫu URI:

```promql
histogram_quantile(
  0.95,
  sum by (le, method, uri) (
    rate(http_server_requests_seconds_bucket{
      job="orders-lab",
      environment="lab",
      uri!~"/actuator.*|/livez|/readyz"
    }[5m])
  )
)
```

Đặt legend gồm method và uri. Tránh vẽ hàng nghìn đường trên một panel; lọc nhóm API hoặc dùng bảng để chọn tuyến cần điều tra.

Percentile phụ thuộc lượng quan sát và độ phân giải bucket. Khi rất ít yêu cầu, không dùng p99 như một kết luận chắc chắn. Xem đồng thời số yêu cầu trong cửa sổ và độ trễ theo từng API.

### 5.5. Đo tỷ lệ đáp ứng một mốc thời gian khi cần

Nếu đã xuất bucket `le="0.3"`, tỷ lệ yêu cầu hoàn tất trong tối đa khoảng 300 ms là:

```promql
100 *
sum(
  rate(http_server_requests_seconds_bucket{
    job="orders-lab",
    environment="lab",
    uri!~"/actuator.*|/livez|/readyz",
    le="0.3"
  }[5m])
)
/
(
  sum(
    rate(http_server_requests_seconds_count{
      job="orders-lab",
      environment="lab",
      uri!~"/actuator.*|/livez|/readyz"
    }[5m])
  ) > 0
)
```

Trước khi dùng, đọc giá trị nhãn `le` thực tế của endpoint để khớp đúng dạng xuất. Panel này chỉ đo thời gian, vẫn có thể tính cả phản hồi 500 rất nhanh. Nếu mục tiêu yêu cầu “thành công và đủ nhanh”, định nghĩa lại tập yêu cầu tốt và mẫu số theo SLO đó.

## 6. Panel tài nguyên: ưu tiên nhìn từng instance

Các panel tài nguyên giúp định hướng điều tra, không tự chứng minh nguyên nhân. Micrometer cung cấp các binder cho bộ nhớ, GC, CPU và luồng JVM. [Số liệu JVM của Micrometer](https://docs.micrometer.io/micrometer/reference/reference/jvm.html)

### 6.1. CPU của tiến trình

```promql
100 * process_cpu_usage{
  job="orders-lab",
  environment="lab"
}
```

Chọn đơn vị percent 0–100, legend theo instance. Không cộng phần trăm CPU của các instance thành một “phần trăm toàn dịch vụ”.

Đây là tỷ lệ CPU do JVM/hệ điều hành cung cấp cho phép đo đó. Nó không tự đồng nghĩa với phần trăm quota CPU của container. Nếu cần đánh giá throttling hoặc hạn mức container, bổ sung số liệu hạ tầng theo đúng nền tảng.

CPU thấp trong khi p95 cao có thể gợi ý chờ I/O, chờ kết nối hoặc chờ khóa. CPU cao đồng thời lưu lượng tăng có thể gợi ý nhu cầu tính toán tăng. Cả hai đều cần bằng chứng tiếp theo.

### 6.2. Heap đang dùng

```promql
sum by (instance) (
  jvm_memory_used_bytes{
    job="orders-lab",
    environment="lab",
    area="heap"
  }
)
```

Chọn đơn vị bytes. Khi chỉ chọn một môi trường/job, mỗi đường thể hiện tổng heap đang dùng của một instance.

Nếu muốn tỷ lệ theo **từng memory pool có maximum hợp lệ**:

```promql
100 *
jvm_memory_used_bytes{
  job="orders-lab",
  environment="lab",
  area="heap"
}
/
(
  jvm_memory_max_bytes{
    job="orders-lab",
    environment="lab",
    area="heap"
  } > 0
)
```

Giữ legend instance và id của pool. Pool không có maximum dương sẽ không xuất hiện trong tỷ lệ; không biến nó thành 0%. Không gọi biểu đồ này là “phần trăm bộ nhớ container”.

Micrometer ghi các pool và nhãn tương ứng từ JVM. [Mã nguồn JvmMemoryMetrics 1.13](https://raw.githubusercontent.com/micrometer-metrics/micrometer/v1.13.0/micrometer-core/src/main/java/io/micrometer/core/instrument/binder/jvm/JvmMemoryMetrics.java)

Quan sát xu hướng qua nhiều chu kỳ GC. Một đoạn heap tăng rồi giảm là chưa đủ để kết luận rò rỉ bộ nhớ. Bộ nhớ tiến trình còn gồm các phần ngoài heap; khi cần, đối chiếu số liệu tiến trình/container thay vì coi heap là toàn bộ bộ nhớ.

### 6.3. Luồng và thời gian GC

Số luồng JVM đang sống:

```promql
jvm_threads_live_threads{
  job="orders-lab",
  environment="lab"
}
```

Tốc độ thời gian pause GC tích lũy:

```promql
sum by (instance) (
  rate(jvm_gc_pause_seconds_sum{
    job="orders-lab",
    environment="lab"
  }[5m])
)
```

Panel GC có đơn vị giây pause mỗi giây quan sát. Xem cùng heap và độ trễ; không suy ra nguyên nhân chỉ từ một điểm tăng. Một số meter phụ thuộc JVM, bộ thu gom hoặc hoạt động đã xảy ra; xác nhận tên/nhãn trước khi dùng.

Luồng tăng không nhất thiết là luồng bị nghẽn. Nếu cần đánh giá hàng đợi hay mức bão hòa, thêm số liệu của executor/thread pool thực sự đang xử lý công việc.

### 6.4. Kết nối cơ sở dữ liệu, khi ứng dụng có pool

Ví dụ với các meter JDBC đã có trong endpoint:

```promql
100 *
jdbc_connections_active{
  job="orders-lab",
  environment="lab"
}
/
(
  jdbc_connections_max{
    job="orders-lab",
    environment="lab"
  } > 0
)
```

Giữ nhãn instance và tên pool/data source. Spring Boot có số liệu active, idle và giới hạn cho các DataSource được hỗ trợ. [Số liệu DataSource](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html#actuator.metrics.supported.jdbc)

Ứng dụng thí nghiệm chưa thêm cơ sở dữ liệu nên panel này có thể không có dữ liệu. Không thêm cơ sở dữ liệu giả chỉ để mọi panel đều có đường biểu diễn. Với production, tỷ lệ active/max cao là đầu mối; xem thêm thời gian chờ lấy kết nối, yêu cầu đang đợi và tải của cơ sở dữ liệu trước khi tăng pool.

## 7. Dựng bố cục Grafana từ các truy vấn đã kiểm chứng

Thêm nguồn dữ liệu Prometheus, đặt URL mà máy chủ Grafana truy cập được, ví dụ `http://127.0.0.1:9090` khi cả hai chạy trực tiếp cùng máy. Kiểm tra kết nối trước khi tạo panel.

Tạo dashboard mới, thêm panel, chọn nguồn dữ liệu và nhập PromQL trong trình soạn truy vấn. Lưu dashboard sau khi đặt tên và kiểm tra kết quả. [Tạo dashboard Grafana](https://grafana.com/docs/grafana/latest/visualizations/dashboards/build-dashboards/create-dashboard/), [trình soạn PromQL](https://grafana.com/docs/grafana/latest/datasources/prometheus/query-editor/)

Bố cục đề xuất:

| Hàng | Panel | Cách thể hiện |
| --- | --- | --- |
| 1 | Trạng thái scrape theo instance | Stat hoặc State timeline; 1 và 0 có ý nghĩa rõ |
| 1 | Tổng RPS, tỷ lệ 5xx, p95 | Các giá trị tổng quan kèm xu hướng |
| 2 | RPS theo instance, 5xx mỗi giây | Time series để đối chiếu tải và lỗi |
| 2 | Trung bình, p95, p99 | Cùng đơn vị và cùng phạm vi yêu cầu |
| 3 | Độ trễ theo method/uri | Bảng hoặc biểu đồ có bộ lọc API |
| 4 | CPU, heap, luồng, GC theo instance | Không để trung bình toàn cụm che instance bất thường |
| 5 | Pool/queue/container | Chỉ thêm khi có dữ liệu và câu hỏi vận hành tương ứng |

Mỗi panel ghi trong mô tả:

- Dịch vụ, môi trường và đường dẫn nào được tính.
- Cửa sổ tính và đơn vị.
- Điều kiện nào được gọi là lỗi.
- Cách hiểu khi giá trị bằng 0 hoặc không có dữ liệu.
- Liên kết tới biểu đồ chi tiết hoặc quy trình điều tra phù hợp.

Đặt khoảng thời gian ban đầu 30 phút, tự làm mới 15–30 giây cho bài thử. Đổi khoảng thời gian không làm một phép đo sai trở thành đúng; kiểm tra lại cách lấy rate và độ phân giải khi xem nhiều giờ hoặc nhiều ngày.

### Bộ lọc tái sử dụng

Sau khi bản cố định hoạt động, tạo biến job và environment dạng chọn một giá trị; instance có thể chọn nhiều. Truy vấn biến lấy các giá trị nhãn từ `up`, vì các nhãn phạm vi đã được đặt ở target.

Khi đưa vào panel, thay bộ chọn cố định bằng dạng:

```text
job="$job", environment="$environment", instance=~"$instance"
```

Với lựa chọn nhiều hoặc All, instance dùng `=~`. Đồng thời kiểm tra mọi panel đều áp dụng cùng bộ lọc. [Biến mẫu Prometheus trong Grafana](https://grafana.com/docs/grafana/latest/datasources/prometheus/template-variables/)

Chọn một instance phải làm các panel dịch vụ phản ánh đúng instance đó. Nếu panel RPS còn cộng toàn cụm trong khi CPU đã lọc một instance, người xem có thể ghép hai tín hiệu không cùng phạm vi.

### Trạng thái thu thập không phải trạng thái nghiệp vụ

```promql
up{job="orders-lab", environment="lab"}
```

`up=1` chứng minh scrape thành công, không chứng minh API nghiệp vụ thành công. Ứng dụng có thể xuất số liệu bình thường trong khi một API trả 500.

Ngược lại, `up=0` có thể do ứng dụng dừng, sai quyền, sai mạng hoặc endpoint lỗi. Nếu target bị loại khỏi cấu hình phát hiện, chuỗi `up` còn có thể biến mất; cần đối chiếu số target kỳ vọng từ nguồn triển khai.

Không cấu hình mọi giá trị thiếu thành 0 và tô xanh. Khi scrape vừa lỗi, truy vấn rate theo cửa sổ vẫn có thể còn giá trị từ các mẫu trước đó. Đọc panel trạng thái thu thập cùng các biểu đồ lịch sử.

## 8. Kiểm chứng dashboard bằng tình huống có chủ đích

### 8.1. Sinh hỗn hợp yêu cầu dễ kiểm đếm

Lưu đoạn sau thành `traffic.py` trên máy thí nghiệm có Python 3. Nó chỉ gọi các API thí nghiệm trên loopback:

```python
import time
import urllib.error
import urllib.request

base_url = "http://127.0.0.1:8080"
counts = {200: 0, 500: 0}

for index in range(1000):
    if index % 10 == 0:
        path = "/demo/fail"
    elif index % 5 == 0:
        path = "/demo/slow"
    else:
        path = "/demo/ok"

    try:
        with urllib.request.urlopen(base_url + path, timeout=3) as response:
            status = response.status
    except urllib.error.HTTPError as error:
        status = error.code
        error.close()

    if status not in counts:
        raise RuntimeError(f"Unexpected HTTP status: {status}")

    counts[status] += 1
    time.sleep(0.05)

print(
    f"sent={sum(counts.values())} "
    f"ok={counts[200]} server_errors={counts[500]}"
)
```

Chạy:

```text
python traffic.py
```

Nếu ứng dụng đúng như ví dụ và cả 1000 lần gọi đều nhận được phản hồi dự kiến, stdout là:

```text
sent=1000 ok=900 server_errors=100
```

Trong đó có 100 lần gọi slow, nằm trong 900 phản hồi 200. Lỗi kết nối hoặc timeout không bị giấu; script dừng để người học điều tra.

Kết quả kiểm đếm của script là chính xác theo vòng lặp. RPS và tỷ lệ trên dashboard là phép tính theo cửa sổ scrape, có thể chịu ảnh hưởng khởi động, khoảng thời gian chọn và các yêu cầu gọi tay trước đó. Khi cần quan sát trạng thái ổn định, chạy lặp bài thử đủ lâu.

### 8.2. Các phép thử nghiệm thu

| Tình huống | Dấu hiệu cần kiểm tra |
| --- | --- |
| Chỉ gọi `/demo/ok` | RPS tăng, không có lỗi 5xx; không bắt buộc đã có chuỗi 5xx |
| Gọi hỗn hợp bằng script | Có lỗi 5xx và nhóm yêu cầu chậm; kiểm đếm nguồn gần khớp xu hướng |
| Tăng tỷ trọng slow | p95/p99 phản ánh phần chậm theo phân bố mới, không yêu cầu đúng 250 ms |
| Ngừng gửi yêu cầu nhưng giữ ứng dụng | Rate dần về 0 khi cửa sổ hết lưu lượng; scrape vẫn thành công |
| Dừng ứng dụng | Scrape lỗi; dashboard không diễn giải thành hệ thống khỏe và không lỗi |
| Khởi động lại ứng dụng | Counter reset; panel rate không biến reset thành lưu lượng âm |
| Thêm bản sao | Tổng RPS cộng được, CPU/heap vẫn thấy từng instance |
| Đổi bộ lọc môi trường | Mọi panel chuyển cùng phạm vi, không trộn lab với production |

Nếu Prometheus được scrape trước khi script chạy, số liệu tốt hơn cho việc đối chiếu phần tăng của counter. `increase()` có thể nội suy nên không cam kết kết quả luôn là một số nguyên bằng đúng bộ đếm trong script.

### 8.3. Những sai sót cần phát hiện trước khi dùng thật

- Dùng count tích lũy làm tốc độ yêu cầu.
- Tính rate sau khi cộng các counter của nhiều tiến trình.
- Trung bình tỷ lệ lỗi hoặc percentile giữa các instance.
- Thiếu nhãn le trong phép gộp histogram cổ điển.
- Đếm cả probe/scrape vào lưu lượng nghiệp vụ nhưng không nói rõ.
- Nhầm giây với mili giây, nhầm tỷ lệ 0–1 với phần trăm 0–100.
- Dùng heap làm đại diện cho toàn bộ bộ nhớ container.
- Hiển thị chuỗi thiếu thành 0 hoặc nối đường qua khoảng mất dữ liệu.
- Chọn ngưỡng màu chỉ vì trông hợp lý, không gắn với mục tiêu dịch vụ.
- Suy ra quan hệ nguyên nhân chỉ vì hai biểu đồ tăng cùng lúc.

## 9. Đưa dashboard vào quy trình vận hành

Trước khi dùng cho production, ghi rõ người sở hữu dashboard, mục tiêu quan sát, nguồn dữ liệu, bộ nhãn chuẩn và cách thay đổi truy vấn. Lưu cấu hình dashboard theo cơ chế quản lý thay đổi của nhóm để có thể xem lại và phục hồi.

Dashboard và cảnh báo có vai trò khác nhau. Dashboard hỗ trợ khám phá; cảnh báo cần điều kiện, thời gian duy trì, cách xử lý thiếu dữ liệu và người nhận cụ thể. Một ngưỡng màu trên panel chưa tạo thành cơ chế ứng cứu.

Khi có bất thường, bắt đầu từ ảnh hưởng: lưu lượng, tỷ lệ thất bại và độ trễ. Sau đó xác định API/instance liên quan, đối chiếu tài nguyên và thời điểm triển khai, rồi dùng log/trace để kiểm tra giả thuyết.

Dashboard đạt yêu cầu khi người vận hành có thể xác định phạm vi ảnh hưởng, phân biệt sự cố dịch vụ với sự cố thu thập số liệu và chọn được bước điều tra tiếp theo bằng các phép đo có ý nghĩa rõ ràng.
