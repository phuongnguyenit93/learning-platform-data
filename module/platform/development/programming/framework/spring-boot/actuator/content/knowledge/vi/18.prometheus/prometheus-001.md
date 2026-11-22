# Tích hợp micrometer-registry-prometheus và công bố endpoint Prometheus

Trong ứng dụng Spring Boot, Micrometer ghi nhận các số đo như số lần gọi API và mức dùng bộ nhớ JVM. Registry Prometheus chuyển các số đo sang định dạng mà Prometheus đọc được. Actuator cung cấp đường dẫn HTTP để Prometheus chủ động lấy dữ liệu định kỳ. Mỗi lần lấy dữ liệu như vậy gọi là một lượt thu thập (scrape).

~~~text
Ứng dụng ghi số đo vào MeterRegistry của Micrometer
                   ↓
Registry Prometheus biểu diễn số đo dưới dạng mẫu
                   ↓
Actuator phục vụ GET /actuator/prometheus
                   ↑
Prometheus gọi định kỳ và lưu mẫu theo thời gian
~~~

Có hai điều kiện riêng để tích hợp thành công. Ứng dụng phải có registry Prometheus để chuẩn bị dữ liệu. Endpoint `prometheus» phải được mở qua HTTP để trình thu thập gọi được.

## 1. Thêm Actuator và registry

Với ứng dụng Spring Boot đã có Gradle, thêm hai dependency sau vào khối `dependencies» nếu còn thiếu. Dùng phần quản lý phiên bản của Spring Boot cho Micrometer.

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
}
~~~

`spring-boot-starter-actuator» cung cấp hạ tầng quản lý endpoint và Micrometer. Khi `micrometer-registry-prometheus» có mặt lúc chạy, Spring Boot có thể tự cấu hình registry Prometheus. Mã ứng dụng có thể nhận `MeterRegistry» qua hàm tạo và dùng API chung của Micrometer. Cách này dùng được ngay cả khi dự án có thêm một registry khác.

Để chạy ví dụ độc lập bằng Maven, tạo `pom.xml» sau. Ví dụ dùng Java 17 trở lên và Spring Boot 3.3.13. Starter Web cung cấp máy chủ HTTP cho cả API mẫu và endpoint Actuator.

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>prometheus-demo</artifactId>
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
            <scope>runtime</scope>
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

## 2. Mở endpoint qua HTTP

Thêm vào `src/main/resources/application.properties»:

~~~properties
server.address=127.0.0.1
management.endpoints.web.exposure.include=health,prometheus
~~~

Spring Boot 3.3 mặc định chỉ mở endpoint `health» qua HTTP. Danh sách `include» trong ví dụ giữ `health» và mở thêm `prometheus». Với cổng ứng dụng mặc định 8080 và tiền tố Actuator mặc định `/actuator», URL sẽ là `http://127.0.0.1:8080/actuator/prometheus». `server.address» giới hạn ví dụ vào loopback để ứng dụng và trình thu thập có thể chạy thử trên cùng máy.

Ba nhóm cấu hình tác động ở các lớp khác nhau:

| Lớp | Thuộc tính | Tác dụng |
| --- | --- | --- |
| Registry | `management.prometheus.metrics.export.enabled» | Điều khiển tự cấu hình bộ xuất Prometheus khi dependency có mặt. Mặc định là `true». |
| Endpoint | `management.endpoint.prometheus.enabled» | Điều khiển endpoint Actuator trong Spring Boot 3.3. Nếu dự án đã tắt endpoint mặc định bằng `management.endpoints.enabled-by-default=false», cần bật riêng `prometheus» để dùng. |
| Mở qua HTTP | `management.endpoints.web.exposure.include» | Chọn ID endpoint có thể được gọi qua web. Nếu `exclude» cũng khớp, `exclude» được ưu tiên. |

`/actuator/prometheus» trả mẫu ở định dạng Prometheus, chẳng hạn `text/plain» theo định dạng thu thập. `/actuator/metrics» là endpoint riêng để tra tên và số đo qua JSON khi được mở. Hãy dùng endpoint `prometheus» cho `metrics_path».

## 3. Xác minh dữ liệu bằng một bộ đếm

Tạo `src/main/java/example/PrometheusDemoApplication.java»:

~~~java
package example;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class PrometheusDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(PrometheusDemoApplication.class, args);
    }
}

@RestController
class PingController {
    private final Counter requests;

    PingController(MeterRegistry registry) {
        this.requests = registry.counter("demo.ping.requests");
    }

    @GetMapping("/demo/ping")
    String ping() {
        requests.increment();
        return "pong";
    }
}
~~~

Chạy từ thư mục chứa `pom.xml»:

~~~bash
mvn spring-boot:run
~~~

Sau khi ứng dụng sẵn sàng, mở terminal thứ hai và gửi ba yêu cầu thành công. Trên Windows PowerShell có thể dùng `curl.exe» trong cùng các lệnh.

~~~bash
curl -fsS http://127.0.0.1:8080/demo/ping
curl -fsS http://127.0.0.1:8080/demo/ping
curl -fsS http://127.0.0.1:8080/demo/ping
curl -fsSi http://127.0.0.1:8080/actuator/prometheus
~~~

Mỗi lần gọi `/demo/ping» trả thân phản hồi `pong». Lần gọi Actuator dự kiến trả HTTP 200 và nhiều dòng số đo. Nếu ứng dụng vừa khởi động và chỉ có ba lượt gọi trên, tìm mẫu sau trong thân phản hồi:

~~~text
demo_ping_requests_total 3.0
~~~

Micrometer chuyển `demo.ping.requests» thành tên theo quy ước Prometheus, với dấu gạch dưới và hậu tố `_total» cho bộ đếm. Giá trị 3 là tổng lượt của tiến trình hiện tại. Việc đọc endpoint Actuator không làm tăng bộ đếm này. Khi tiến trình khởi động lại, bộ đếm của ví dụ bắt đầu lại từ 0.

## 4. Cho Prometheus thu thập và kiểm tra từ phía máy chủ

Nếu đã có Prometheus chạy trực tiếp trên cùng máy, thêm job sau vào `scrape_configs» của `prometheus.yml». Nếu dùng một tệp cấu hình riêng để thử, có thể dùng nguyên khối này.

~~~yaml
scrape_configs:
  - job_name: 'spring-demo'
    metrics_path: '/actuator/prometheus'
    scrape_interval: 15s
    static_configs:
      - targets: ['127.0.0.1:8080']
~~~

`targets» nhận địa chỉ `host:port». `metrics_path» là phần đường dẫn, với giá trị mặc định của Prometheus là `/metrics» nếu bỏ trường này. Nếu chạy bằng tệp thử riêng, kiểm tra rồi khởi động Prometheus:

~~~bash
promtool check config prometheus.yml
prometheus --config.file=prometheus.yml
~~~

Sau lượt thu thập, xem trang Targets của Prometheus hoặc truy vấn `up{job="spring-demo"}». Giá trị `1» cho biết Prometheus thu thập thành công. Truy vấn thêm `demo_ping_requests_total{job="spring-demo"}» để xác nhận chuỗi của ứng dụng đã được lưu. Nếu gọi thêm `/demo/ping», chờ lượt thu thập kế tiếp để thấy giá trị tăng.

Địa chỉ đích được hiểu từ nơi **Prometheus** chạy. Trong container, `127.0.0.1» là chính container Prometheus. Khi hai tiến trình ở các môi trường mạng khác nhau, dùng tên dịch vụ hoặc địa chỉ mà Prometheus truy cập được, đồng thời cấu hình ứng dụng lắng nghe trên giao diện mạng phù hợp. Nếu tách `management.server.port» hoặc đổi `management.endpoints.web.base-path», cập nhật cổng hoặc đường dẫn của job tương ứng.

## Chẩn đoán theo điểm đứt

| Dấu hiệu | Nơi kiểm tra |
| --- | --- |
| HTTP 404 | Kiểm tra dependency Actuator và registry trong classpath lúc chạy. Sau đó xác nhận trạng thái registry, trạng thái endpoint, `include»/`exclude», đường dẫn và cổng quản lý thực tế. |
| HTTP 401 hoặc 403 | Kiểm tra thông tin xác thực và quyền gọi endpoint từ phía Prometheus. Với Spring Security, quy tắc truy cập và cấu hình mở endpoint là hai lớp riêng. |
| `curl» trên máy ứng dụng thành công, nhưng target báo DOWN | Đọc lỗi trên trang Targets. Kiểm tra kết nối từ môi trường chạy Prometheus, gồm DNS, cổng, đường dẫn, TLS hoặc quyền truy cập tùy lỗi. |
| `up» bằng 1, nhưng thiếu số đo mẫu | Tìm dòng số đo trong phản hồi scrape, kiểm tra tên theo quy ước Prometheus và thời điểm meter được đăng ký. Nếu phản hồi đã có dòng, kiểm tra bộ lọc nhãn và quy tắc lọc metric của job. |

Khi triển khai, giới hạn các ID endpoint được mở, giữ đường thu thập trong mạng giám sát và cấp quyền truy cập theo cấu hình bảo mật của môi trường. Nếu dự án tự định nghĩa `SecurityFilterChain», đặt quy tắc cho các endpoint Actuator trong cấu hình đó.

### Tài liệu tham khảo

- [Spring Boot 3.3 – Tích hợp registry và thu thập metrics](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html)
- [Spring Boot 3.3 – Mở và bảo vệ endpoint Actuator](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html)
- [Spring Boot 3.3 – Định dạng phản hồi của endpoint Prometheus](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/prometheus.html)
- [Prometheus – Cấu hình job thu thập](https://prometheus.io/docs/prometheus/latest/configuration/configuration/)