# Công bố probe trên cổng chính với /livez, /readyz hoặc additional-path

## 1. Vì sao cổng của probe lại quan trọng?

Giả sử ứng dụng nhận yêu cầu nghiệp vụ ở cổng `8080`, còn Actuator ở cổng `8081`. Một lần kiểm tra thành công tại `8081` chưa chứng minh được rằng kết nối tới `8080` vẫn hoạt động. Nếu bộ phận tiếp nhận kết nối của cổng chính gặp sự cố, phép kiểm tra qua cổng quản trị có thể bỏ sót vấn đề.

Mục tiêu của bài này là giữ các endpoint quản trị trên cổng riêng, đồng thời công bố hai phép kiểm tra tình trạng trên cổng phục vụ ứng dụng:

- **Tình trạng sống (liveness):** phiên bản ứng dụng còn ở trạng thái có thể tiếp tục hoạt động hay không.
- **Mức sẵn sàng (readiness):** phiên bản ứng dụng đã sẵn sàng nhận lưu lượng hay chưa.
- **Nhóm sức khỏe (health group):** tập hợp các thành phần kiểm tra dùng để tính một kết quả sức khỏe.
- **Đường dẫn bổ sung (additional path):** một địa chỉ HTTP khác để truy cập kết quả của cùng nhóm.

Hai đường dẫn ngắn `/livez` và `/readyz` là cách thuận tiện để đưa probe lên cổng chính. Spring Boot cũng cho phép chọn tên khác bằng thuộc tính `additional-path`. Đây là cơ chế công bố của Actuator; không cần viết controller trả chuỗi `UP`. Xem [tài liệu probe của Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes).

## 2. Tách ba quyết định: trạng thái, nhóm và địa chỉ

Có thể đọc luồng xử lý theo thứ tự sau:

```text
Trạng thái của ứng dụng
        ↓
Thành phần kiểm tra sức khỏe
        ↓
Nhóm liveness hoặc readiness
        ↓
Kết quả sức khỏe + mã HTTP
        ↓
Đường dẫn trên cổng chính hoặc cổng quản trị
```

Đổi địa chỉ không làm ứng dụng tự động sẵn sàng hơn. Ngược lại, một nhóm được cấu hình đúng nhưng chỉ được truy cập trên cổng không phù hợp vẫn có thể cung cấp bằng chứng vận hành chưa đủ tốt.

Với ví dụ hai cổng trong bài:

| Mục đích | Địa chỉ |
| --- | --- |
| Yêu cầu nghiệp vụ | `http://localhost:8080/hello` |
| Nhóm liveness qua Actuator | `http://localhost:8081/actuator/health/liveness` |
| Nhóm readiness qua Actuator | `http://localhost:8081/actuator/health/readiness` |
| Liveness trên cổng chính | `http://localhost:8080/livez` |
| Readiness trên cổng chính | `http://localhost:8080/readyz` |

Hai hàng cuối chỉ xuất hiện sau khi đã cấu hình đường dẫn bổ sung. Không tự ghép `/actuator` vào trước `/livez` hoặc `/readyz`.

Khi kiểm tra, hãy ghi lại cả **scheme, địa chỉ máy, cổng và đường dẫn**. Chỉ ghi “probe trả 200” sẽ không đủ để biết phép kiểm tra đã đi qua đâu.

## 3. Cách 1: bật hai đường dẫn chuẩn

Cấu hình sau dành cho Spring Boot 3.3.x với Spring MVC và Actuator:

```yaml
server:
  port: 8080

management:
  server:
    port: 8081
  endpoints:
    web:
      exposure:
        include: health
  endpoint:
    health:
      show-details: never
      probes:
        enabled: true
        add-additional-paths: true
```

Các quyết định trong cấu hình:

| Thuộc tính | Vai trò |
| --- | --- |
| `server.port=8080` | Cổng chính của ứng dụng |
| `management.server.port=8081` | Tách HTTP quản trị sang cổng khác |
| `management.endpoints.web.exposure.include=health` | Công bố endpoint `health` qua HTTP |
| `management.endpoint.health.probes.enabled=true` | Bật hỗ trợ nhóm probe cả khi chạy thử ngoài Kubernetes |
| `management.endpoint.health.probes.add-additional-paths=true` | Thêm `/livez` và `/readyz` trên cổng chính |
| `management.endpoint.health.show-details=never` | Giữ phản hồi sức khỏe gọn, không đưa chi tiết kiểm tra ra ngoài |

Đừng nhầm `enabled` với `add-additional-paths`: một thuộc tính bật hỗ trợ probe, thuộc tính kia công bố thêm địa chỉ. Việc nhóm đã tồn tại tại `/actuator/health/readiness` không có nghĩa `/readyz` đã tồn tại.

Tách cổng được cấu hình bằng `management.server.port`. Đổi tiền tố endpoint là việc khác, dùng `management.endpoints.web.base-path`; thao tác đó không thay thế việc chọn cổng cho probe. Xem [cấu hình HTTP quản trị](https://docs.spring.io/spring-boot/3.3/reference/actuator/monitoring.html).

## 4. Ví dụ độc lập để thực hành

Ví dụ dùng Java 17 trở lên, Maven và Spring Boot `3.3.13` để cố định phiên bản minh họa thuộc nhánh 3.3.x. Không cần cơ sở dữ liệu, Docker hoặc Spring Security cho lần thực hành này.

Tạo cấu trúc:

```text
probe-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── example/
        │       └── probe/
        │           └── ProbeApplication.java
        └── resources/
            └── application.yml
```

Nội dung `pom.xml`:

```xml
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

  <groupId>example</groupId>
  <artifactId>probe-demo</artifactId>
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

Nội dung `src/main/java/example/probe/ProbeApplication.java`:

```java
package example.probe;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class ProbeApplication {
    public static void main(String[] args) {
        SpringApplication.run(ProbeApplication.class, args);
    }

    @GetMapping("/hello")
    public String hello() {
        return "hello";
    }
}
```

Đặt YAML ở mục 3 vào `src/main/resources/application.yml`. Phương thức `hello()` chỉ cung cấp một yêu cầu nghiệp vụ đơn giản để xác nhận cổng chính; các endpoint probe do Actuator đăng ký.

Chạy tại thư mục chứa `pom.xml`:

```bash
mvn clean package
java -jar target/probe-demo-1.0.0.jar
```

Không dùng `javac ProbeApplication.java` đơn lẻ: chương trình này cần các thư viện Spring và quá trình đóng gói của Maven. Chờ ứng dụng khởi động hoàn tất rồi mở terminal khác để kiểm tra.

### 4.1. Kiểm tra cổng nghiệp vụ

```bash
curl -sS -w '\nHTTP %{http_code}\n' http://localhost:8080/hello
```

Kết quả mong đợi:

```text
hello
HTTP 200
```

### 4.2. Kiểm tra probe trên cổng chính

```bash
curl -sS -w '\nHTTP %{http_code}\n' http://localhost:8080/livez
curl -sS -w '\nHTTP %{http_code}\n' http://localhost:8080/readyz
```

Với ứng dụng đã khởi động hoàn tất và trạng thái bình thường, mỗi lệnh có kết quả mong đợi:

```text
{"status":"UP"}
HTTP 200
```

Trên Windows PowerShell, dùng `curl.exe` thay cho `curl` nếu tên `curl` đang trỏ tới một lệnh khác.

### 4.3. Đối chiếu nhóm trên cổng quản trị

```bash
curl -sS -w '\nHTTP %{http_code}\n' http://localhost:8081/actuator/health/liveness
curl -sS -w '\nHTTP %{http_code}\n' http://localhost:8081/actuator/health/readiness
```

Với cùng điều kiện ổn định, mỗi lệnh cũng được kỳ vọng trả:

```text
{"status":"UP"}
HTTP 200
```

Các địa chỉ bổ sung không thay thế hai địa chỉ nhóm này. Khi đối chiếu hai lần gọi liên tiếp, cần nhớ rằng trạng thái có thể thay đổi giữa hai thời điểm; không đòi chúng luôn giống từng byte nếu ứng dụng đang chuyển trạng thái.

### 4.4. Thí nghiệm kiểm soát: tắt địa chỉ bổ sung

Dừng tiến trình bằng `Ctrl+C`, rồi chạy lại:

```bash
java -jar target/probe-demo-1.0.0.jar --management.endpoint.health.probes.add-additional-paths=false
```

Sau khi khởi động hoàn tất:

| Phép kiểm tra | Kết quả mong đợi với đúng ví dụ này |
| --- | --- |
| `8080/hello` | `200`, nội dung `hello` |
| `8081/actuator/health/liveness` | `200`, trạng thái `UP` |
| `8081/actuator/health/readiness` | `200`, trạng thái `UP` |
| `8080/livez` | `404` |
| `8080/readyz` | `404` |

Thí nghiệm giúp phân biệt “nhóm probe tồn tại” với “nhóm được công bố thêm trên cổng chính”. Điều kiện của bảng là không có controller, bộ lọc hoặc quy tắc định tuyến khác xử lý các địa chỉ đó.

## 5. Cách 2: tự chọn additional-path cho từng nhóm

Nếu hạ tầng đã quy định tên đường dẫn riêng, thay phần cấu hình `management.endpoint.health` của mục 3 bằng:

```yaml
management:
  endpoint:
    health:
      show-details: never
      probes:
        enabled: true
        add-additional-paths: false
      group:
        liveness:
          additional-path: "server:/health-live"
        readiness:
          additional-path: "server:/health-ready"
```

Đây là **đoạn cấu hình thay thế cho phần tương ứng**; vẫn giữ `server.port`, `management.server.port` và cấu hình exposure ở mục 3. Khi chỉnh một tệp YAML, hợp nhất vào khóa `management` đang có, không tạo hai khóa `management` cùng cấp.

Khởi động lại rồi kiểm tra:

```bash
curl -sS -w '\nHTTP %{http_code}\n' http://localhost:8080/health-live
curl -sS -w '\nHTTP %{http_code}\n' http://localhost:8080/health-ready
```

Với trạng thái bình thường, mỗi lệnh được kỳ vọng trả `{"status":"UP"}` và `HTTP 200`. Trong cấu hình thay thế này, ứng dụng dùng hai tên mới; đừng tiếp tục trỏ probe tới `/livez` và `/readyz`.

### 5.1. Hiểu tiền tố và giới hạn đường dẫn

`additional-path` biểu diễn cả **nơi công bố** lẫn **đường dẫn**, không chỉ là một URL tương đối. Spring Boot có kiểu dữ liệu riêng [AdditionalHealthEndpointPath](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/AdditionalHealthEndpointPath.html) cho khái niệm này.

| Giá trị | Cách hiểu |
| --- | --- |
| `server:/health-live` | Công bố tại `/health-live` trên cổng chính |
| `management:/health-live` | Công bố tại `/health-live` trên cổng quản trị khi cấu hình cổng riêng |
| `/health-live` | Thiếu tiền tố chọn nơi công bố |
| `server:/health/live` | Có nhiều đoạn đường dẫn, không phù hợp giới hạn một đoạn |
| `server:http://localhost:8080/health-live` | Nhầm cấu hình đường dẫn với URL đầy đủ |

Chọn `server:` khi cần kiểm tra qua cổng chính. Với ví dụ hai cổng, chọn `management:` vẫn đặt phép kiểm tra ở phía quản trị.

Mỗi nhóm có một thuộc tính `additional-path`; đừng coi nó là danh sách các địa chỉ phân cách bằng dấu phẩy. Nếu cần tên chuẩn, dùng cách 1. Nếu cần tên do hạ tầng quy định, cấu hình rõ từng nhóm theo cách 2 để dễ kiểm tra.

## 6. Đưa đúng địa chỉ vào Kubernetes

Dưới đây là **đoạn cấu hình một container**, không phải manifest Deployment đầy đủ. Nó dùng cấu hình chuẩn của mục 3:

```yaml
ports:
  - name: http
    containerPort: 8080
  - name: management
    containerPort: 8081

startupProbe:
  httpGet:
    path: /livez
    port: http
  periodSeconds: 5
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
```

Tên `http` trỏ tới cổng `8080` trong cùng cấu hình container. Nếu chọn đường dẫn tùy biến ở mục 5, sửa đường dẫn của cả ba probe tương ứng.

Khi khai báo `startupProbe`, Kubernetes đợi probe này thành công trước khi thực hiện liveness và readiness. Readiness thất bại làm Pod không sẵn sàng nhận lưu lượng qua Service; liveness thất bại đủ ngưỡng dẫn tới khởi động lại container. Vì hậu quả khác nhau, không dùng chung một địa chỉ chỉ vì cả hai đều đang trả `200`. Xem [hướng dẫn probe của Kubernetes](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/).

Các khoảng thời gian trong ví dụ là điểm bắt đầu cho bài thực hành; cần đo thời gian khởi động và độ trễ của ứng dụng để chọn giá trị phù hợp. Không dùng timeout rất ngắn để che giấu một phép kiểm tra đang chậm.

## 7. Đọc kết quả đúng và xử lý lỗi thường gặp

Một probe cần cung cấp được bằng chứng ở cả hai lớp:

1. **Kết nối và định tuyến:** đúng cổng, đúng đường dẫn, đúng giao thức, đi được tới ứng dụng.
2. **Tình trạng được công bố:** kết quả nhóm có phản ánh đúng điều kiện nhận lưu lượng hoặc tiếp tục hoạt động không.

`/readyz` chạy qua cổng chính vẫn không thực thi mọi API nghiệp vụ. Vì vậy, phép kiểm tra này không thay thế kiểm thử chức năng. Một controller luôn trả `200` cũng không chứng minh được rằng nhóm readiness đang cho phép nhận lưu lượng.

| Hiện tượng | Hướng kiểm tra |
| --- | --- |
| `/actuator/health/readiness` chạy được nhưng `/readyz` trả `404` | Kiểm tra `add-additional-paths` và địa chỉ tùy biến của nhóm |
| `/livez` trả `404` | Xác nhận đang gọi cổng chính; kiểm tra probe đã bật và không dùng `/actuator/livez` |
| Cả nhóm Actuator lẫn địa chỉ bổ sung đều không truy cập được | Xác nhận có starter Actuator, endpoint `health` được bật và công bố qua HTTP |
| Phản hồi `401`, `403` hoặc chuyển tới đăng nhập | Kiểm tra quy tắc Spring Security thực tế cho đúng địa chỉ probe |
| Không kết nối được hoặc hết thời gian chờ | Kiểm tra tiến trình, cổng lắng nghe, mạng và giao thức trước khi suy luận về trạng thái sức khỏe |
| Đổi đường dẫn trong ứng dụng nhưng Kubernetes liên tục báo lỗi | Đồng bộ `httpGet.path` và `httpGet.port` với cấu hình mới |
| Cổng quản trị báo tốt nhưng người dùng không kết nối được cổng chính | Kiểm tra probe có thực sự đang đi qua `server:` và cổng nghiệp vụ không |

Nếu ứng dụng dùng Spring Security, hãy cho phép chính xác các địa chỉ mà bộ kiểm tra cần gọi theo chính sách truy cập của hệ thống. Không suy ra rằng quy tắc chỉ khớp `/actuator/**` đã bao gồm `/livez` hoặc `/health-ready`. Giữ phản hồi probe tối thiểu và kiểm tra cả mã HTTP; không chỉ tìm chữ `UP` trong nội dung.

Các URL trong bài giả định context path gốc, HTTP và không có proxy sửa đường dẫn. Khi ứng dụng có tiền tố ngữ cảnh, HTTPS hoặc định tuyến qua proxy, xác nhận lại URL mà bộ kiểm tra thực sự gọi; không áp nguyên URL của bài mà bỏ qua cấu hình triển khai.

## 8. Bài thực hành tự kiểm chứng

1. Chạy cấu hình chuẩn; lập bảng kết quả cho `/hello`, `/livez`, `/readyz` và hai địa chỉ nhóm trên cổng quản trị.
2. Tắt `add-additional-paths`; kiểm tra xem lỗi là mất địa chỉ bổ sung hay mất cả nhóm.
3. Đổi sang `server:/health-live` và `server:/health-ready`; cập nhật lệnh gọi cùng cấu hình probe.
4. Giải thích vì sao gọi `management:/health-ready` chưa đáp ứng mục tiêu kiểm tra cổng chính.
5. Xác nhận không có controller trả `UP` giả lập và không có quy tắc bảo mật biến probe thành phản hồi đăng nhập.

Sau bài thực hành, người học cần chỉ ra được bốn thông tin cho mỗi probe: **nhóm được đọc, đường dẫn được công bố, cổng được gọi và hành động khi kiểm tra thất bại**.
