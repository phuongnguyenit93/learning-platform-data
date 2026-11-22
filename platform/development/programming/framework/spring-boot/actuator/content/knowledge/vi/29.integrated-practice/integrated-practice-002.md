# Xây dựng health indicator cho phụ thuộc ngoài và nhóm readiness phù hợp

Một ứng dụng đang chạy chưa chắc đã sẵn sàng nhận công việc. Tiến trình Java có thể còn sống, cổng HTTP còn trả lời, nhưng đường kết nối đến dịch vụ bắt buộc đã hỏng. Ngược lại, một dịch vụ gợi ý bị lỗi không nhất thiết khiến toàn bộ ứng dụng ngừng phục vụ.

Bài thực hành này xây dựng health indicator kiểm tra một phụ thuộc HTTP, sau đó đưa kết quả vào đúng nhóm readiness. Mục tiêu là tạo tín hiệu vận hành có ý nghĩa: loại một instance khỏi luồng nhận việc khi cần thiết, nhưng không khởi động lại hàng loạt instance chỉ vì một dịch vụ bên ngoài đang gặp sự cố.

Ví dụ dùng Spring Boot 3.3.x, Java 17+ và ứng dụng Servlet. Các quyết định về phụ thuộc bắt buộc, tùy chọn và khả năng phục vụ khi suy giảm phải được xác định trước khi viết cấu hình.

## 1. Tách ba câu hỏi trước khi viết mã

| Tín hiệu | Câu hỏi cần trả lời | Hành động thường gắn với tín hiệu |
| --- | --- | --- |
| Liveness | Tiến trình có ở trạng thái còn có thể tiếp tục hoạt động không? | Nếu thất bại đủ lâu, hệ thống điều phối có thể khởi động lại container |
| Readiness | Instance này hiện có nên nhận yêu cầu mới không? | Nếu thất bại, hệ thống điều phối có thể ngừng định tuyến yêu cầu mới đến instance |
| Health tổng hợp | Các thành phần được đăng ký đang báo trạng thái gì? | Chẩn đoán; không tự động là chính sách nhận lưu lượng |

**Không đưa mọi phụ thuộc ngoài vào liveness.** Khởi động lại ứng dụng thường không sửa được một dịch vụ bên ngoài đang mất kết nối. Nếu tất cả instance cùng khởi động lại, hệ thống còn mất thêm năng lực phục vụ và tạo thêm tải khi phục hồi.

Readiness cũng không mặc nhiên phải chứa mọi phụ thuộc. Hãy xét tác động đến khả năng phục vụ:

| Tình huống | Quyết định cần cân nhắc |
| --- | --- |
| Instance bị lỗi cấu hình kết nối riêng hoặc mất đường mạng riêng tới dịch vụ bắt buộc | Readiness có thể cần thất bại để chuyển lưu lượng sang instance khỏe |
| Dịch vụ gợi ý bị lỗi nhưng chức năng chính vẫn hoạt động | Theo dõi bằng health/metrics; thường không đưa vào readiness |
| Có dữ liệu lưu đệm đủ mới hoặc cơ chế phục vụ thay thế đáp ứng hợp đồng | Không nhất thiết loại instance; phản ánh suy giảm ở tín hiệu phù hợp |
| Chỉ một phần nhỏ API cần phụ thuộc đó | Readiness toàn instance có thể quá rộng; cần chính sách cho từng chức năng hoặc tuyến |
| Mọi instance cùng phụ thuộc vào một dịch vụ đang ngừng hoạt động | Đưa phụ thuộc đó vào readiness có thể loại toàn bộ instance; phải chủ động chấp nhận hệ quả này |

Trong Boot 3.3.x, các nhóm probe mặc định dựa vào trạng thái sống và sẵn sàng của ứng dụng; các phụ thuộc ngoài không tự động trở thành thành viên readiness. Khi thêm chúng, người thiết kế đang thay đổi chính sách vận hành.

## 2. Chính sách của bài thực hành

Giả sử có một dịch vụ chuyên tạo vận đơn:

- `shipping` là cổng cung cấp vận chuyển bắt buộc. Trong phạm vi giả định này, dịch vụ không có dữ liệu lưu đệm hay cách thay thế để hoàn thành công việc khi shipping không dùng được.
- `recommendations` cung cấp gợi ý bổ sung. Không có gợi ý, chức năng chính vẫn phục vụ được.
- Liveness chỉ phụ thuộc `livenessState`.
- Readiness kết hợp `readinessState` với `shipping`.
- Health tổng hợp vẫn quan sát cả hai phụ thuộc.

Đây là chính sách minh họa có chủ đích. Nếu shipping là dịch vụ dùng chung và nó ngừng hoạt động hoàn toàn, toàn bộ instance áp dụng chính sách này có thể trở thành không sẵn sàng. Khi đó người dùng có thể nhận lỗi từ tầng định tuyến thay vì lỗi nghiệp vụ được ứng dụng kiểm soát. Trước khi áp dụng, cần quyết định kết quả nào phù hợp với hợp đồng của hệ thống.

Không dùng bài thực hành để suy ra quy tắc “phụ thuộc ngoài lỗi thì readiness luôn phải DOWN”.

Luồng kiểm tra:

```text
GET /actuator/health/readiness
    -> đọc readinessState của ứng dụng
    -> chạy shipping health indicator
        -> GET shipping /healthz với timeout
    -> tổng hợp trạng thái
    -> ánh xạ trạng thái thành mã HTTP

GET /actuator/health/liveness
    -> chỉ đọc livenessState

GET /actuator/health
    -> tổng hợp các health contributor đã đăng ký
       bao gồm shipping và recommendations trong ví dụ
```

## 3. Thiết kế phép kiểm tra phụ thuộc

### 3.1. Hợp đồng của endpoint bên ngoài

Ví dụ quy ước `GET /healthz` của từng phụ thuộc như sau:

- Trả mã 2xx khi phép kiểm tra nhẹ đã thành công.
- Trả 503 khi phụ thuộc không đáp ứng hợp đồng đó.
- Không tạo đơn hàng, đặt chỗ, gửi email hoặc thay đổi dữ liệu.
- Phản hồi nhỏ; bài này không cần đọc nội dung để quyết định trạng thái.

Không áp dụng quy tắc “2xx là khỏe” cho một API khác nếu API đó trả HTTP 200 cùng nội dung `{"status":"DOWN"}`. Phải hiểu hợp đồng thực tế và kiểm tra đúng tín hiệu.

Tránh gọi health tổng hợp của một hệ thống khác mà không biết nó chứa những gì. Một thành phần tùy chọn ở hệ thống đó có thể làm health tổng hợp DOWN dù thao tác mà ứng dụng cần vẫn hoạt động. Các dịch vụ gọi health của nhau theo vòng còn có thể tạo chuỗi kiểm tra đệ quy.

### 3.2. Phân biệt trạng thái ứng dụng với kết quả gọi HTTP

| Kết quả kiểm tra bên ngoài | Health indicator trong ví dụ | Ý nghĩa |
| --- | --- | --- |
| HTTP 2xx | UP | Phụ thuộc đáp ứng hợp đồng kiểm tra |
| HTTP 503 | DOWN | Phụ thuộc báo không dùng được |
| HTTP 401/403 | DOWN | Ứng dụng không thực hiện được kiểm tra đã cấu hình; cần kiểm tra quyền/xác thực |
| HTTP 404 | DOWN | Có thể sai URL hoặc sai hợp đồng endpoint |
| Timeout, lỗi DNS, lỗi kết nối hoặc TLS | DOWN | Từ instance này chưa xác nhận được khả năng sử dụng phụ thuộc |
| Trạng thái HTTP khác không được chấp nhận | DOWN | Không đáp ứng hợp đồng của phép kiểm tra |

Mã 401 của phụ thuộc không trở thành mã 401 của readiness. Indicator chuyển kết quả đó thành DOWN; nhóm health sau đó ánh xạ DOWN thành 503.

DOWN mô tả quan sát từ instance và phép kiểm tra hiện tại. Nó không tự chứng minh toàn bộ hệ thống bên ngoài đã hỏng.

### 3.3. Chọn timeout và chi phí hợp lý

Ví dụ dùng connect timeout 300 ms và read timeout 700 ms. Những giá trị này là thông số phòng thực hành, cần điều chỉnh theo độ trễ thực tế và ngân sách của probe.

Không coi `connect timeout + read timeout` là một thời hạn tổng tuyệt đối cho mọi request. DNS, nhiều giai đoạn kết nối, chuyển hướng và đặc điểm HTTP client có thể ảnh hưởng tổng thời gian. Nếu cần giới hạn tổng nghiêm ngặt, phải thiết kế và kiểm thử cơ chế phù hợp với client đang dùng.

Không retry nhiều lần trong mỗi lượt probe. Probe vốn đã được hệ thống điều phối gọi định kỳ; retry ở nhiều tầng dễ làm tăng tải đúng lúc phụ thuộc đang yếu.

## 4. Tạo ứng dụng minh họa độc lập

Cấu trúc dự án:

```text
dependency-health-lab/
├── pom.xml
├── dependency_stub.py
└── src/main/
    ├── java/demo/health/
    │   ├── DependencyHealthApplication.java
    │   ├── HttpDependencyHealthIndicator.java
    │   └── DependencyHealthConfiguration.java
    └── resources/application.yml
```

Dùng JDK 17+ và Maven. Script mô phỏng phụ thuộc dùng Python 3 và thư viện chuẩn. Phiên bản Boot 3.3.5 được cố định để ví dụ có môi trường cụ thể; việc chọn phiên bản triển khai cần theo chính sách bảo trì riêng.

### 4.1. Dependency và lớp khởi động

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
    <artifactId>dependency-health-lab</artifactId>
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

Không cần thêm dependency riêng cho health indicator ngoài starter Actuator. Starter Web cung cấp nền HTTP Servlet và `RestClient` dùng trong ví dụ.

`src/main/java/demo/health/DependencyHealthApplication.java`:

```java
package demo.health;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DependencyHealthApplication {
    public static void main(String[] args) {
        SpringApplication.run(DependencyHealthApplication.class, args);
    }
}
```

### 4.2. Health indicator

`src/main/java/demo/health/HttpDependencyHealthIndicator.java`:

```java
package demo.health;

import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.http.ResponseEntity;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.RestClientResponseException;

public final class HttpDependencyHealthIndicator implements HealthIndicator {
    private final RestClient client;

    public HttpDependencyHealthIndicator(RestClient client) {
        this.client = client;
    }

    @Override
    public Health health() {
        try {
            ResponseEntity<Void> response = client.get()
                    .uri("/healthz")
                    .retrieve()
                    .toBodilessEntity();

            int code = response.getStatusCode().value();
            if (response.getStatusCode().is2xxSuccessful()) {
                return Health.up().withDetail("httpStatus", code).build();
            }
            return Health.down()
                    .withDetail("reason", "unexpected-http-status")
                    .withDetail("httpStatus", code)
                    .build();
        } catch (RestClientResponseException ex) {
            return Health.down()
                    .withDetail("reason", "http-error")
                    .withDetail("httpStatus", ex.getStatusCode().value())
                    .build();
        } catch (ResourceAccessException ex) {
            return Health.down()
                    .withDetail("reason", "transport-error")
                    .build();
        } catch (RestClientException ex) {
            return Health.down()
                    .withDetail("reason", "client-error")
                    .build();
        }
    }
}
```

Các điểm cần đọc từ mã:

1. Indicator thực hiện một yêu cầu GET nhẹ, không dùng endpoint nghiệp vụ có tác dụng phụ.
2. Phản hồi 4xx/5xx được `retrieve()` chuyển thành `RestClientResponseException` theo xử lý lỗi mặc định; mã bắt riêng để ghi nhận mã HTTP.
3. Lỗi truy cập tài nguyên được bắt riêng và chuyển thành DOWN.
4. Không đưa response body, URL đầy đủ, thông tin xác thực hay đối tượng exception vào details của những nhánh lỗi này.
5. Không giữ biến “đã lỗi” trong đối tượng. Lượt kiểm tra sau đánh giá lại nên có thể tự trở về UP khi phụ thuộc phục hồi.

Không trả UP trong `catch` để tránh probe bị đỏ. Cũng không dùng UNKNOWN như một cách từ chối quyết định mà vẫn mong readiness thất bại: theo ánh xạ mặc định, UNKNOWN trả HTTP 200.

Ví dụ chỉ xử lý các lỗi client dự kiến. Những lỗi lập trình ngoài phạm vi đó cần được kiểm thử và sửa, thay vì bắt mọi `Throwable` rồi che giấu nguyên nhân.

### 4.3. Đăng ký hai indicator và cấu hình timeout

`src/main/java/demo/health/DependencyHealthConfiguration.java`:

```java
package demo.health;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
public class DependencyHealthConfiguration {
    @Bean
    HealthIndicator shippingHealthIndicator(RestClient.Builder builder,
            @Value("${dependencies.shipping.base-url}") String baseUrl,
            @Value("${dependencies.connect-timeout-ms:300}") int connectTimeoutMs,
            @Value("${dependencies.read-timeout-ms:700}") int readTimeoutMs) {
        return createIndicator(builder, baseUrl, connectTimeoutMs, readTimeoutMs);
    }

    @Bean
    HealthIndicator recommendationsHealthIndicator(RestClient.Builder builder,
            @Value("${dependencies.recommendations.base-url}") String baseUrl,
            @Value("${dependencies.connect-timeout-ms:300}") int connectTimeoutMs,
            @Value("${dependencies.read-timeout-ms:700}") int readTimeoutMs) {
        return createIndicator(builder, baseUrl, connectTimeoutMs, readTimeoutMs);
    }

    private HealthIndicator createIndicator(RestClient.Builder builder,
            String baseUrl, int connectTimeoutMs, int readTimeoutMs) {
        if (connectTimeoutMs < 1 || readTimeoutMs < 1) {
            throw new IllegalArgumentException("Health-check timeouts must be positive");
        }

        SimpleClientHttpRequestFactory factory = new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(connectTimeoutMs);
        factory.setReadTimeout(readTimeoutMs);

        RestClient client = builder
                .requestFactory(factory)
                .baseUrl(baseUrl)
                .build();
        return new HttpDependencyHealthIndicator(client);
    }
}
```

`RestClient.Builder` được tiêm từ Boot. Request factory được cấu hình timeout rõ ràng; giá trị nhỏ hơn 1 bị từ chối để tránh vô tình dùng timeout bằng 0 với ý nghĩa không giới hạn ở client này.

Hai phương thức tạo bean sử dụng cùng lớp indicator nhưng có URL riêng. Health contributor ID được suy ra từ tên bean:

| Tên bean | Contributor ID dùng trong health group |
| --- | --- |
| `shippingHealthIndicator` | `shipping` |
| `recommendationsHealthIndicator` | `recommendations` |

Vì hậu tố `HealthIndicator` được bỏ khi xác định ID, cấu hình `include` dùng `shipping`, không dùng cả tên `shippingHealthIndicator`.

Nếu đổi tên bean, phải kiểm tra lại ID và cấu hình nhóm. Không tạo hai bean có tên khác nhau nhưng vô tình kiểm tra nhầm cùng một URL.

### 4.4. Cấu hình health group

`src/main/resources/application.yml`:

```yaml
server:
  port: 8080
spring:
  application:
    name: dependency-health-lab
dependencies:
  shipping:
    base-url: http://localhost:9091
  recommendations:
    base-url: http://localhost:9092
  connect-timeout-ms: 300
  read-timeout-ms: 700
management:
  endpoints:
    web:
      exposure:
        include: health
  endpoint:
    health:
      show-details: never
      validate-group-membership: true
      logging:
        slow-indicator-threshold: 2s
      probes:
        enabled: true
        add-additional-paths: true
      group:
        liveness:
          include: livenessState
        readiness:
          include: readinessState,shipping
```

Ý nghĩa của các lựa chọn:

- `probes.enabled: true` bật các probe kể cả khi chạy ngoài Kubernetes.
- Liveness chỉ chứa `livenessState`, không chứa shipping hoặc recommendations.
- Readiness giữ `readinessState` và thêm `shipping`. Nhờ giữ trạng thái ứng dụng, việc ứng dụng đang từ chối nhận lưu lượng vẫn được phản ánh dù shipping đang UP.
- `recommendations` không được đưa vào readiness, nhưng vẫn là health contributor để chẩn đoán.
- `validate-group-membership: true` giúp phát hiện ID thành viên không tồn tại khi khởi động. Không tắt kiểm tra này chỉ để che một tên bị gõ sai.
- `show-details: never` giữ phản hồi HTTP gọn và không công khai chi tiết các phụ thuộc.
- `add-additional-paths: true` tạo `/livez` và `/readyz` trên cổng HTTP chính.
- `logging.slow-indicator-threshold: 2s` là ngưỡng ghi cảnh báo indicator chậm. Nó không hủy phép kiểm tra, không thay thế timeout và không bảo đảm endpoint hoàn tất trong 2 giây.

Các endpoint cần phân biệt:

| Endpoint | Phạm vi |
| --- | --- |
| `/actuator/health` | Health tổng hợp |
| `/actuator/health/liveness` | Nhóm liveness |
| `/actuator/health/readiness` | Nhóm readiness |
| `/livez` | Đường dẫn bổ sung của liveness trên cổng chính |
| `/readyz` | Đường dẫn bổ sung của readiness trên cổng chính |

Trong ví dụ này tất cả cùng dùng cổng 8080. Nếu sau này tách `management.server.port`, các đường dẫn bổ sung trên cổng chính giúp probe đi qua máy chủ đang phục vụ lưu lượng ứng dụng, thay vì chỉ xác nhận máy chủ quản trị còn trả lời. Chúng vẫn không thay thế kiểm thử giao dịch nghiệp vụ.

## 5. Mô phỏng phụ thuộc ngoài

`dependency_stub.py` là chương trình chạy độc lập:

```python
import argparse
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--port", type=int, required=True)
parser.add_argument("--mode-file", type=Path, required=True)
args = parser.parse_args()

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/healthz":
            code = 404
        else:
            try:
                mode = args.mode_file.read_text(encoding="ascii").strip()
            except FileNotFoundError:
                mode = "up"

            if mode == "slow":
                time.sleep(2)
            code = 200 if mode in ("up", "slow") else 503

        try:
            self.send_response(code)
            self.send_header("Content-Length", "0")
            self.end_headers()
        except (BrokenPipeError, ConnectionResetError):
            pass

    def log_message(self, format, *values):
        pass

print(f"stub listening on 127.0.0.1:{args.port}", flush=True)
ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()
```

Script đọc tệp trạng thái trong từng request:

- `up`: trả HTTP 200.
- `down`: trả HTTP 503.
- `slow`: chờ 2 giây rồi mới trả HTTP 200.
- Giá trị khác: trả 503.
- Nếu chưa có tệp trạng thái, mặc định của chương trình mô phỏng là `up`.

Không dùng chương trình này làm health endpoint production; nó chỉ giúp chủ động tạo lỗi và phục hồi trong bài thực hành.

### 5.1. Khởi tạo và chạy các tiến trình

Các lệnh thay đổi tệp bên dưới dùng PowerShell và dữ liệu ASCII để Python đọc nhất quán.

Tại thư mục dự án, tạo trạng thái ban đầu:

```powershell
Set-Content -LiteralPath shipping.mode -Value up -Encoding ascii
Set-Content -LiteralPath recommendations.mode -Value up -Encoding ascii
```

Terminal thứ nhất, vẫn ở thư mục dự án:

```powershell
python dependency_stub.py --port 9091 --mode-file shipping.mode
```

Dòng stdout đầu tiên:

```text
stub listening on 127.0.0.1:9091
```

Terminal thứ hai:

```powershell
python dependency_stub.py --port 9092 --mode-file recommendations.mode
```

Dòng stdout đầu tiên:

```text
stub listening on 127.0.0.1:9092
```

Terminal thứ ba, đóng gói ứng dụng:

```powershell
mvn clean package
```

Sau khi build thành công, chạy:

```powershell
java -jar target/dependency-health-lab-1.0.0.jar
```

Chờ ứng dụng khởi động xong. Các cổng 8080, 9091 và 9092 phải đang trống. Nếu đổi cổng phụ thuộc, cập nhật URL trong `application.yml` tương ứng.

### 5.2. Kiểm tra trạng thái ban đầu

Ở một terminal khác:

```powershell
curl.exe -i http://localhost:8080/actuator/health
curl.exe -i http://localhost:8080/actuator/health/liveness
curl.exe -i http://localhost:8080/actuator/health/readiness
curl.exe -i http://localhost:8080/readyz
```

Với các thành phần nền như đĩa vẫn khỏe và cả hai stub ở chế độ up, các endpoint trên trả HTTP 200 với trạng thái UP. Header như thời gian phản hồi có thể khác nhau; không đối chiếu toàn bộ stdout HTTP như một chuỗi cố định.

Trong Linux/macOS, dùng `curl` thay cho `curl.exe` và tạo tệp mode bằng công cụ tương ứng. Cần giữ các giá trị `up`, `down`, `slow` và thư mục làm việc nhất quán với các stub.

## 6. Thực hiện các tình huống lỗi và phục hồi

Mỗi tình huống chỉ thay đổi một điều kiện để kết quả có thể giải thích được.

### 6.1. Phụ thuộc tùy chọn bị lỗi

Đặt recommendations thành down:

```powershell
Set-Content -LiteralPath recommendations.mode -Value down -Encoding ascii
curl.exe -i http://localhost:8080/actuator/health
curl.exe -i http://localhost:8080/actuator/health/readiness
curl.exe -i http://localhost:8080/actuator/health/liveness
```

Kỳ vọng:

- Health tổng hợp: DOWN, HTTP 503.
- Readiness: UP, HTTP 200.
- Liveness: UP, HTTP 200.

Đây không phải mâu thuẫn. Health tổng hợp đang báo một thành phần lỗi, còn readiness đang thực hiện chính sách khác: instance vẫn có thể phục vụ chức năng chính.

Nếu dùng `/actuator/health` làm readiness probe trong tình huống này, phụ thuộc tùy chọn sẽ gián tiếp loại instance khỏi lưu lượng. Đó là lý do phải chọn đúng endpoint của nhóm.

Khôi phục:

```powershell
Set-Content -LiteralPath recommendations.mode -Value up -Encoding ascii
```

### 6.2. Phụ thuộc bắt buộc bị lỗi

```powershell
Set-Content -LiteralPath shipping.mode -Value down -Encoding ascii
curl.exe -i http://localhost:8080/actuator/health/readiness
curl.exe -i http://localhost:8080/actuator/health/liveness
```

Kỳ vọng:

- Readiness: DOWN, HTTP 503.
- Liveness: UP, HTTP 200.

Shipping đang không dùng được nên readiness thất bại theo chính sách đã chọn. Liveness không thất bại vì khởi động lại ứng dụng chưa giải quyết được shipping.

Khôi phục:

```powershell
Set-Content -LiteralPath shipping.mode -Value up -Encoding ascii
curl.exe -i http://localhost:8080/actuator/health/readiness
```

Khi ứng dụng vẫn chấp nhận lưu lượng và các điều kiện khác bình thường, readiness trở lại UP/HTTP 200. Không cần khởi động lại Java chỉ để xóa một cờ DOWN trong indicator.

### 6.3. Phụ thuộc còn trả lời nhưng quá chậm

```powershell
Set-Content -LiteralPath shipping.mode -Value slow -Encoding ascii
curl.exe -i http://localhost:8080/actuator/health/readiness
```

Stub cố ý chờ 2 giây trước khi trả phản hồi, dài hơn read timeout 700 ms. Với phép kiểm tra này, lỗi đọc được chuyển thành DOWN và readiness trả 503.

Điều đó không có nghĩa dependency chắc chắn không bao giờ hoàn thành yêu cầu. Nó có nghĩa instance chưa nhận được phản hồi trong giới hạn chờ đã đặt cho phép kiểm tra.

Không khẳng định tổng thời gian endpoint chính xác là 700 ms: còn có thời gian kết nối, điều phối và xử lý của ứng dụng. Hãy đo tổng độ trễ thực tế khi chọn timeout của probe.

Khôi phục:

```powershell
Set-Content -LiteralPath shipping.mode -Value up -Encoding ascii
```

### 6.4. Phụ thuộc không còn lắng nghe

Dừng riêng tiến trình stub shipping bằng Ctrl+C trong terminal của nó, rồi gọi lại readiness. Lỗi kết nối phải được chuyển thành DOWN/503; liveness vẫn UP/200.

Chạy lại đúng lệnh stub shipping, bảo đảm tệp mode là up rồi kiểm tra phục hồi. Đừng dừng ứng dụng Java hoặc stub recommendations trong cùng lượt thử vì sẽ không còn cô lập được nguyên nhân.

### 6.5. Bảng nghiệm thu

Giả sử ứng dụng đã sẵn sàng, các thành phần nền khác khỏe và chỉ thay đổi các điều kiện trong bảng:

| Shipping | Recommendations | Health tổng hợp | Readiness | Liveness |
| --- | --- | --- | --- | --- |
| UP | UP | UP / 200 | UP / 200 | UP / 200 |
| UP | DOWN | DOWN / 503 | UP / 200 | UP / 200 |
| DOWN | UP | DOWN / 503 | DOWN / 503 | UP / 200 |
| Timeout | UP | DOWN / 503 | DOWN / 503 | UP / 200 |
| Phục hồi UP | UP | UP / 200 | UP / 200 | UP / 200 |

Ngoài bảng này, khi trạng thái ứng dụng là `ReadinessState.REFUSING_TRAFFIC`, thành viên `readinessState` báo OUT_OF_SERVICE. Nếu shipping UP và không có trạng thái lỗi mạnh hơn trong nhóm, readiness vẫn là OUT_OF_SERVICE/503. Một phụ thuộc khỏe không được phép làm ứng dụng đang từ chối nhận việc trở thành sẵn sàng.

## 7. Nối với probe của hệ thống điều phối

Khối YAML sau đặt bên trong một phần tử container của PodSpec; đây không phải tệp Deployment hoàn chỉnh:

```yaml
ports:
  - name: http
    containerPort: 8080

startupProbe:
  httpGet:
    path: /livez
    port: http
  periodSeconds: 2
  timeoutSeconds: 2
  failureThreshold: 30

livenessProbe:
  httpGet:
    path: /livez
    port: http
  periodSeconds: 10
  timeoutSeconds: 2
  failureThreshold: 3

readinessProbe:
  httpGet:
    path: /readyz
    port: http
  periodSeconds: 5
  timeoutSeconds: 2
  failureThreshold: 3
  successThreshold: 2
```

Ý nghĩa vận hành:

- Startup probe cho ứng dụng khoảng thời gian khởi động trước khi liveness/readiness được thực hiện. Nó không thay thế chính sách readiness.
- Liveness tiếp tục chỉ kiểm tra khả năng sống của ứng dụng.
- Readiness cần số lần thất bại liên tiếp theo ngưỡng trước khi bị xem là không đạt; ngưỡng thành công giúp giảm bật/tắt liên tục khi phục hồi.
- Timeout probe phải có khoảng dự phòng so với tổng thời gian health endpoint thực tế. Giá trị minh họa 2 giây cần được đo lại dưới tải và điều kiện mạng thật.

Không tính thời gian loại instance bằng một công thức tuyệt đối từ `periodSeconds × failureThreshold`. Thời điểm bắt đầu probe, thời gian mỗi lần gọi và việc cập nhật định tuyến đều có ảnh hưởng.

Readiness thất bại không tự giết tiến trình và không tự hủy các request đang chạy. Hệ thống điều phối cập nhật trạng thái nhận lưu lượng; việc xử lý request đang chạy và quá trình dừng êm cần thiết kế riêng. Ngược lại, liveness thất bại có thể dẫn đến khởi động lại sau khi đạt ngưỡng.

Nếu ứng dụng dùng cổng quản trị riêng, chọn đường dẫn/cổng probe có chủ đích. Một cổng quản trị còn khỏe không bảo đảm cổng nghiệp vụ đang chấp nhận kết nối.

## 8. Những điểm cần hoàn thiện trước khi đưa vào vận hành

### 8.1. Không biến probe thành tải gây sự cố

Ở ví dụ, mỗi lần đọc nhóm có thành viên shipping sẽ thực hiện phép kiểm tra shipping. Khi đồng thời có hệ thống điều phối, bộ giám sát và công cụ vận hành gọi health, tổng tần suất có thể cao hơn dự kiến.

Cần đánh giá:

- Số instance và số nơi đang gọi probe.
- Chi phí của phép kiểm tra, giới hạn kết nối và độ trễ khi phụ thuộc yếu.
- Có cần bộ nhớ đệm kết quả trong thời gian ngắn hoặc kiểm tra nền không.
- Nếu dùng kết quả lưu đệm, thời điểm kiểm tra cuối và giới hạn độ cũ được chấp nhận.

Không trả UP vô thời hạn từ một kết quả thành công đã cũ. Khi thêm cache hoặc kiểm tra nền, phải quy định chính sách cho kết quả quá hạn, tránh để hàng loạt probe đồng thời tạo cùng một lượt kiểm tra mới, và kiểm thử phục hồi.

Phép kiểm tra nhẹ cũng chỉ là một phép đo tại thời điểm cụ thể. Nó không bảo đảm yêu cầu nghiệp vụ ngay sau đó sẽ thành công. Mã nghiệp vụ vẫn cần timeout, xử lý lỗi và cơ chế phục hồi riêng.

### 8.2. Giữ đúng ý nghĩa của trạng thái và mã HTTP

Theo ánh xạ mặc định của health endpoint:

| Trạng thái | Mã HTTP mặc định |
| --- | --- |
| UP | 200 |
| DOWN | 503 |
| OUT_OF_SERVICE | 503 |
| UNKNOWN | 200 |

Vì vậy, lựa chọn UNKNOWN cho lỗi bắt buộc có thể khiến probe vẫn thành công. Nếu thiết kế thêm trạng thái tùy chỉnh, phải xem xét cả thứ tự tổng hợp trạng thái và ánh xạ HTTP.

Khi khai báo ánh xạ HTTP tùy chỉnh, cần giữ rõ hành vi mong muốn cho DOWN và OUT_OF_SERVICE; không giả định mọi ánh xạ mặc định vẫn được bảo toàn sau tùy chỉnh. Không đổi DOWN thành HTTP 200 chỉ để hệ thống điều phối ngừng báo lỗi.

### 8.3. Bảo vệ chi tiết nhưng vẫn để probe hoạt động

Cấu hình bài này chỉ công khai endpoint health và không công khai details. Nếu cần xem chi tiết, dùng cơ chế cho người được phép trong môi trường phù hợp; không công khai URL nội bộ, credential, token hoặc nội dung lỗi của nhà cung cấp.

Ứng dụng mẫu không thêm Spring Security. Khi tích hợp vào ứng dụng đã có `SecurityFilterChain`, phải kiểm tra chính các đường probe đang dùng. Một phản hồi 401/403 do lớp bảo mật hoặc trang đăng nhập không phải kết quả health thành công. Không mở mọi Actuator endpoint chỉ để sửa quyền truy cập cho `/livez` và `/readyz`.

Trong ví dụ, các nhánh lỗi dự kiến chỉ lưu mã HTTP hoặc tên nguyên nhân đã được giới hạn. Điều đó giúp việc bật xem details có kiểm soát không vô tình hiển thị toàn bộ response body của phụ thuộc.

### 8.4. Trạng thái ứng dụng vẫn phải có tiếng nói

Không thay `readinessState,shipping` bằng chỉ `shipping` mà không xem xét hệ quả. Khi ứng dụng đang khởi động, dừng hoặc chủ động từ chối nhận việc, shipping UP chưa đủ để xác nhận instance đã sẵn sàng.

Không chủ động phát `LivenessState.BROKEN` chỉ vì phụ thuộc ngoài báo 503. Hãy giữ việc đánh giá phụ thuộc ở đúng chính sách readiness hoặc tín hiệu chẩn đoán đã chọn.

Nếu chủ động điều khiển `ReadinessState` bằng sự kiện availability, phải xác định thành phần nào chịu trách nhiệm đổi trạng thái và khi nào được phục hồi. Tránh để một tác vụ kiểm tra phụ thuộc tự ghi đè quyết định từ chối lưu lượng của quá trình dừng ứng dụng.

### 8.5. Với ứng dụng reactive

Không đưa lời gọi HTTP blocking của ví dụ lên luồng sự kiện WebFlux. Trong ứng dụng reactive, ưu tiên `ReactiveHealthIndicator`, client như `WebClient` và cơ chế timeout trong chuỗi reactive.

Không gọi `block()` trên luồng sự kiện để tái sử dụng nguyên xi indicator này. Nếu buộc phải tích hợp mã blocking, cần thực hiện qua cơ chế thích hợp và kiểm thử giới hạn tài nguyên. Chính sách chọn thành viên liveness/readiness vẫn phải được quyết định như ở ứng dụng Servlet.

## 9. Checklist kiểm chứng và bài tập mở rộng

Một lần kiểm chứng hoàn chỉnh cần bao gồm cả mã indicator và chính sách nhóm:

1. HTTP 2xx hợp lệ làm indicator UP.
2. HTTP 503 và lỗi xác thực của phụ thuộc làm indicator DOWN.
3. Lỗi kết nối và lỗi chờ đọc được chuyển thành kết quả health phù hợp.
4. Sau lỗi, lần kiểm tra thành công tiếp theo phục hồi được.
5. Contributor ID khớp với cấu hình nhóm và tên sai bị phát hiện khi khởi động.
6. Phụ thuộc tùy chọn DOWN không làm readiness thất bại.
7. Phụ thuộc bắt buộc DOWN làm readiness trả 503 nhưng không làm liveness thất bại.
8. `readinessState` từ chối nhận việc vẫn có hiệu lực khi phụ thuộc ngoài UP.
9. Tổng độ trễ endpoint nằm trong ngân sách đã đo; indicator chậm không được nhầm với timeout.
10. Các đường probe thực tế dùng đúng cổng, đúng quyền truy cập và không làm lộ dữ liệu nhạy cảm.

Kiểm thử HTTP giả lập hữu ích để xác nhận ánh xạ lỗi, phục hồi, nhóm health và mã HTTP. Nó không tự chứng minh connect/read timeout dưới mạng thật; các tình huống chậm, ngắt kết nối và DNS cần được kiểm tra riêng trong môi trường kiểm soát.

Bài tập tiếp theo: thay giả định “shipping bắt buộc và không có phương án thay thế” bằng tình huống ứng dụng có dữ liệu lưu đệm còn đủ mới để xử lý yêu cầu. Viết lại quyết định readiness trước, nêu rõ giới hạn độ cũ và tình huống phải ngừng nhận việc, rồi mới sửa cấu hình hoặc mã. Không chỉ xóa shipping khỏi nhóm để làm probe xanh.

Health indicator cung cấp một quan sát có giới hạn. Readiness biến quan sát đó thành quyết định nhận lưu lượng; liveness quyết định liệu khởi động lại có thể giúp ích. Giữ đúng ba vai trò này là điều làm cho probe hữu ích trong lúc hệ thống gặp sự cố.
