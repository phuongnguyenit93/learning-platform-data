# Chuyển tên thuộc tính chuẩn thành tên biến môi trường trong Spring Boot

## 1. Vì sao cần đổi tên thuộc tính khi dùng biến môi trường?

Spring Boot hỗ trợ **Externalized Configuration**: cùng một ứng dụng có thể nhận cấu hình từ tệp `application.yml`, `application.properties`, biến môi trường hệ điều hành, Java system properties, đối số dòng lệnh và những nguồn khác. Nhờ đó, nhóm phát triển có thể tạo một bản JAR hoặc container image rồi triển khai trên nhiều môi trường mà không phải sửa mã nguồn mỗi lần đổi URL dịch vụ, cổng HTTP hay ngưỡng timeout.

Các tên thuộc tính trong tệp cấu hình Spring Boot thường có dạng **chữ thường, các cấp phân cách bằng dấu chấm, từ trong một cấp phân cách bằng dấu gạch nối**:

~~~properties
server.port=8080
spring.datasource.url=jdbc:postgresql://localhost:5432/orders
app.gateway.connect-timeout=5s
app.retry.max-attempts=3
~~~

Nhưng biến môi trường trong shell, Docker hoặc Kubernetes thường được đặt tên bằng chữ hoa và dấu gạch dưới:

~~~text
SERVER_PORT
SPRING_DATASOURCE_URL
APP_GATEWAY_CONNECTTIMEOUT
APP_RETRY_MAXATTEMPTS
~~~

Spring Boot có cơ chế **relaxed binding** giúp ánh xạ những tên biến môi trường này sang thuộc tính có cấu trúc. Để tránh nhầm lẫn, ta cần nắm một bộ quy tắc chuyển đổi thống nhất.

Bài này tập trung vào ba vấn đề: **chuyển tên**, **truyền giá trị khi chạy ứng dụng**, và **hiểu cách Spring Boot sử dụng những giá trị đó**. Việc ứng dụng đọc được biến môi trường không đồng nghĩa biến đó luôn là nguồn có ưu tiên cao nhất: đối số dòng lệnh hoặc cấu hình kiểm thử có thể ghi đè tiếp.

## 2. Quy tắc chuyển đổi chính thức

Với một tên thuộc tính ở dạng chuẩn (canonical property name), quy tắc chuyển sang tên biến môi trường dành cho relaxed binding của Spring Boot gồm ba bước:

1. **Thay mọi dấu chấm (`.`) bằng dấu gạch dưới (`_`).**
2. **Xóa mọi dấu gạch nối (`-`).** Không thay dấu gạch nối bằng dấu gạch dưới.
3. **Chuyển toàn bộ chữ cái thành chữ hoa.**

Ví dụ với thuộc tính:

~~~properties
spring.main.log-startup-info=true
~~~

Ta thực hiện:

~~~text
Tên chuẩn:             spring.main.log-startup-info
Thay dấu chấm:         spring_main_log-startup-info
Bỏ dấu gạch nối:       spring_main_logstartupinfo
Chuyển chữ hoa:        SPRING_MAIN_LOGSTARTUPINFO
~~~

Tên biến môi trường theo quy tắc là:

~~~bash
SPRING_MAIN_LOGSTARTUPINFO=true
~~~

Điểm cần nhớ là **dấu chấm và dấu gạch nối không được xử lý giống nhau**:

- `.` mô tả ranh giới giữa các cấp thuộc tính, nên thành `_`.
- `-` nối các từ trong cùng một đoạn tên thuộc tính, nên bị **loại bỏ**.

Vì vậy, `app.client.read-timeout` trở thành `APP_CLIENT_READTIMEOUT`, còn `app.client.read.timeout` trở thành `APP_CLIENT_READ_TIMEOUT`. Hai tên sau thể hiện hai cấu trúc khác nhau.

### Bảng chuyển đổi thường gặp

| Tên thuộc tính chuẩn | Tên biến môi trường |
| --- | --- |
| `server.port` | `SERVER_PORT` |
| `spring.application.name` | `SPRING_APPLICATION_NAME` |
| `spring.profiles.active` | `SPRING_PROFILES_ACTIVE` |
| `spring.datasource.url` | `SPRING_DATASOURCE_URL` |
| `spring.datasource.username` | `SPRING_DATASOURCE_USERNAME` |
| `spring.datasource.hikari.maximum-pool-size` | `SPRING_DATASOURCE_HIKARI_MAXIMUMPOOLSIZE` |
| `management.endpoints.web.exposure.include` | `MANAGEMENT_ENDPOINTS_WEB_EXPOSURE_INCLUDE` |
| `app.client.base-url` | `APP_CLIENT_BASEURL` |
| `app.retry.max-attempts` | `APP_RETRY_MAXATTEMPTS` |
| `app.cache.expire-after-write` | `APP_CACHE_EXPIREAFTERWRITE` |
| `app.security.token-ttl` | `APP_SECURITY_TOKENTTL` |

Những ví dụ này minh họa **quy tắc hình thành tên**. Để một biến có tác dụng, ứng dụng còn phải sử dụng thuộc tính tương ứng, hoặc Spring Boot phải có thành phần tự cấu hình đọc thuộc tính đó.

## 3. Phân biệt dấu chấm và dấu gạch nối qua cấu trúc YAML

Một tệp YAML có thể diễn tả phân cấp bằng thụt lề:

~~~yaml
app:
  client:
    base-url: "https://api.example.org"
    connect-timeout: 5s
  retry:
    max-attempts: 3
~~~

Khi được nạp thành Config Data, các tên thuộc tính là:

~~~properties
app.client.base-url=https://api.example.org
app.client.connect-timeout=5s
app.retry.max-attempts=3
~~~

Tên biến môi trường tương ứng:

~~~bash
APP_CLIENT_BASEURL=https://api.example.org
APP_CLIENT_CONNECTTIMEOUT=5s
APP_RETRY_MAXATTEMPTS=3
~~~

Không cần “dịch” thụt lề YAML thành nhiều dấu gạch dưới tùy ý. Trước tiên, hãy tìm **tên thuộc tính phẳng** bằng cách nối các cấp YAML qua dấu chấm, sau đó áp dụng ba bước ở phần trước.

Ví dụ, hãy so sánh hai cấu trúc:

~~~yaml
# Cấu trúc A
app:
  retry:
    max-attempts: 3
~~~

~~~yaml
# Cấu trúc B (một tệp ví dụ riêng)
app:
  retry:
    max:
      attempts: 3
~~~

Tên chuẩn của cấu trúc A là `app.retry.max-attempts`, tương ứng `APP_RETRY_MAXATTEMPTS`.

Tên chuẩn của cấu trúc B là `app.retry.max.attempts`, tương ứng `APP_RETRY_MAX_ATTEMPTS`.

**Không nên tự chèn dấu gạch dưới ở mọi ranh giới từ tiếng Anh.** Dấu `_` trong phép đổi tên chuẩn đánh dấu **ranh giới cấp của thuộc tính**, còn ranh giới giữa các từ trong một đoạn kebab-case được bỏ đi.

## 4. Cách diễn tả danh sách bằng chỉ số

Một tên thuộc tính Spring Boot có thể chỉ đến phần tử danh sách thông qua cú pháp `[index]`, với chỉ số bắt đầu từ 0.

Ví dụ YAML:

~~~yaml
app:
  regions:
    - vn
    - sg
    - jp
~~~

Các tên thuộc tính phẳng:

~~~properties
app.regions[0]=vn
app.regions[1]=sg
app.regions[2]=jp
~~~

Để chuyển sang biến môi trường, Spring Boot yêu cầu **bao chỉ số bằng dấu gạch dưới** thay cho dấu ngoặc vuông:

~~~bash
APP_REGIONS_0=vn
APP_REGIONS_1=sg
APP_REGIONS_2=jp
~~~

Mẫu tổng quát là:

~~~text
my.service[0].other
           ↓
MY_SERVICE_0_OTHER
~~~

Các dấu gạch dưới bao quanh số `0` cho biết đây là **chỉ số danh sách**, không phải tên một thuộc tính con có chữ số.

### Danh sách các object

Giả sử:

~~~yaml
app:
  backends:
    - name: primary
      base-url: "https://primary.example.org"
      max-connections: 20
    - name: backup
      base-url: "https://backup.example.org"
      max-connections: 10
~~~

Dạng phẳng:

~~~properties
app.backends[0].name=primary
app.backends[0].base-url=https://primary.example.org
app.backends[0].max-connections=20
app.backends[1].name=backup
app.backends[1].base-url=https://backup.example.org
app.backends[1].max-connections=10
~~~

Tên biến môi trường theo quy tắc:

~~~bash
APP_BACKENDS_0_NAME=primary
APP_BACKENDS_0_BASEURL=https://primary.example.org
APP_BACKENDS_0_MAXCONNECTIONS=20
APP_BACKENDS_1_NAME=backup
APP_BACKENDS_1_BASEURL=https://backup.example.org
APP_BACKENDS_1_MAXCONNECTIONS=10
~~~

Cách đọc `APP_BACKENDS_1_MAXCONNECTIONS` là: `app` → `backends` → phần tử thứ hai của danh sách → thuộc tính `max-connections`.

Với danh sách lồng nhau, mỗi tầng danh sách lại có chỉ số riêng. Ví dụ tên phẳng `app.teams[0].members[1].name` chuyển thành `APP_TEAMS_0_MEMBERS_1_NAME`.

## 5. Tên biến môi trường và relaxed binding không phải hai cơ chế hoàn toàn tách biệt

Spring Boot thường dùng `@ConfigurationProperties` để bind các tên thuộc tính dạng chuẩn sang trường Java. Giả sử Java có record:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
        String baseUrl,
        Duration connectTimeout,
        int maxRetries
) {}
~~~

Một file cấu hình có thể viết:

~~~yaml
app:
  client:
    base-url: "https://api.example.org"
    connect-timeout: 5s
    max-retries: 3
~~~

Khi triển khai, thay vì sửa YAML, có thể truyền:

~~~bash
APP_CLIENT_BASEURL=https://prod-api.example.org
APP_CLIENT_CONNECTTIMEOUT=2s
APP_CLIENT_MAXRETRIES=6
~~~

Bộ Binder hiểu `base-url` có thể ánh xạ sang trường Java `baseUrl`, `connect-timeout` sang `connectTimeout`, và `max-retries` sang `maxRetries`.

Ở đây cần phân biệt ba bước:

1. **Flattening YAML:** `app.client.connect-timeout` là tên đường dẫn thuộc tính.
2. **Chuyển sang biến môi trường:** `APP_CLIENT_CONNECTTIMEOUT` là tên chuẩn dùng cho môi trường hệ điều hành.
3. **Binding vào Java:** `connectTimeout` là tên field/record component mà Spring Boot gán giá trị kiểu `Duration`.

Tên biến môi trường không phải tên trường Java; tên trường Java cũng không phải lúc nào là tên thuộc tính chuẩn trong cấu hình.

Trong Java, bật quét `@ConfigurationProperties`:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class ClientApplication {
    public static void main(String[] args) {
        SpringApplication.run(ClientApplication.class, args);
    }
}
~~~

Nếu không có nguồn ưu tiên cao hơn ghi đè, `ClientProperties` sẽ nhận base URL production, timeout 2 giây và số lần retry 6.

## 6. Ví dụ hoàn chỉnh: cấu hình chung và ghi đè bằng biến môi trường

Giả sử một ứng dụng xử lý đơn hàng có `src/main/resources/application.yml`:

~~~yaml
spring:
  application:
    name: order-service

server:
  port: 8080

app:
  checkout:
    enabled: false
    request-timeout: 5s
  retry:
    max-attempts: 2
  alerts:
    channels:
      - email
      - log
~~~

Những biến môi trường tương ứng:

| Thuộc tính | Biến môi trường |
| --- | --- |
| `spring.application.name` | `SPRING_APPLICATION_NAME` |
| `server.port` | `SERVER_PORT` |
| `app.checkout.enabled` | `APP_CHECKOUT_ENABLED` |
| `app.checkout.request-timeout` | `APP_CHECKOUT_REQUESTTIMEOUT` |
| `app.retry.max-attempts` | `APP_RETRY_MAXATTEMPTS` |
| `app.alerts.channels[0]` | `APP_ALERTS_CHANNELS_0` |
| `app.alerts.channels[1]` | `APP_ALERTS_CHANNELS_1` |

Ví dụ chạy trên Linux/macOS:

~~~bash
export SERVER_PORT=9090
export APP_CHECKOUT_ENABLED=true
export APP_CHECKOUT_REQUESTTIMEOUT=12s
export APP_RETRY_MAXATTEMPTS=5

java -jar order-service.jar
~~~

Trong điều kiện không có nguồn ưu tiên cao hơn, giá trị hiệu lực sẽ là:

~~~properties
spring.application.name=order-service
server.port=9090
app.checkout.enabled=true
app.checkout.request-timeout=12s
app.retry.max-attempts=5
~~~

Những khóa không bị thay đổi, chẳng hạn `app.alerts.channels`, vẫn có thể lấy từ tệp chung đã đóng gói trong JAR.

**Lưu ý vận hành:** thay đổi biến môi trường của một terminal sau khi tiến trình Java đã khởi động không tự làm Config Data hoặc những bean được bind cập nhật. Thông thường ứng dụng cần được khởi động lại để nhận cấu hình từ môi trường mới, trừ khi có cơ chế refresh được thiết kế riêng.

## 7. Đặt biến môi trường trên các hệ điều hành và công cụ chạy

### 7.1. Linux và macOS

Cách phổ biến với shell là `export`:

~~~bash
export SPRING_PROFILES_ACTIVE=prod
export SERVER_PORT=9090
export APP_CLIENT_CONNECTTIMEOUT=3s

java -jar app.jar
~~~

Có thể đặt biến chỉ cho **một lệnh**:

~~~bash
SERVER_PORT=9090 APP_CLIENT_CONNECTTIMEOUT=3s java -jar app.jar
~~~

Cách thứ hai giúp giới hạn phạm vi biến ở quá trình khởi chạy từ lệnh đó. Tên biến cần theo quy tắc của shell; chữ hoa và dấu gạch dưới thường dễ tương thích.

### 7.2. Windows PowerShell

~~~powershell
$env:SPRING_PROFILES_ACTIVE = "dev"
$env:SERVER_PORT = "8082"
$env:APP_CLIENT_CONNECTTIMEOUT = "4s"

java -jar app.jar
~~~

Đừng dùng cú pháp `export ...` của Bash trực tiếp trong PowerShell. Biến môi trường của PowerShell được đặt qua namespace `$env:`.

### 7.3. Windows Command Prompt

~~~bat
set SPRING_PROFILES_ACTIVE=dev
set SERVER_PORT=8082
set APP_CLIENT_CONNECTTIMEOUT=4s

java -jar app.jar
~~~

Trong batch script, có thể dùng `setlocal` và `endlocal` để giới hạn những thay đổi biến môi trường ở phạm vi tập lệnh. Lưu ý giá trị không cần dấu nháy bao quanh nếu không có lý do đặc biệt; với `set "NAME=value"`, dấu nháy giúp tránh đưa khoảng trắng thừa vào giá trị.

### 7.4. Docker

Docker cho phép cấp biến môi trường khi chạy container:

~~~bash
docker run --rm \
  -e SPRING_PROFILES_ACTIVE=prod \
  -e SERVER_PORT=9090 \
  -e APP_CLIENT_CONNECTTIMEOUT=3s \
  -p 9090:9090 \
  example/order-service:latest
~~~

Ở đây:

- `SPRING_PROFILES_ACTIVE` chọn profile.
- `SERVER_PORT` có thể đổi cổng web server trong container.
- `-p 9090:9090` ánh xạ cổng máy host sang cổng container, là thao tác của Docker **khác** với cấu hình thuộc tính Spring Boot.

Nếu đổi `SERVER_PORT` sang 8085 nhưng giữ nguyên ánh xạ `-p 9090:9090`, host có thể truy cập sai cổng. Khi đổi cổng ứng dụng cần cập nhật cấu hình mạng cho tương ứng.

### 7.5. Docker Compose

~~~yaml
services:
  order-service:
    image: example/order-service:latest
    environment:
      SPRING_PROFILES_ACTIVE: "prod"
      SERVER_PORT: "9090"
      APP_CLIENT_CONNECTTIMEOUT: "3s"
      APP_RETRY_MAXATTEMPTS: "5"
    ports:
      - "9090:9090"
~~~

Một số giá trị trông như số hoặc boolean nên được đặt trong dấu nháy ở YAML Compose để thể hiện rõ ý định truyền chuỗi biến môi trường.

### 7.6. Kubernetes

Trong manifest Deployment, Kubernetes có trường `env`:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: order-service
spec:
  replicas: 1
  selector:
    matchLabels:
      app: order-service
  template:
    metadata:
      labels:
        app: order-service
    spec:
      containers:
        - name: order-service
          image: example/order-service:latest
          env:
            - name: SPRING_PROFILES_ACTIVE
              value: "prod"
            - name: SERVER_PORT
              value: "9090"
            - name: APP_CLIENT_CONNECTTIMEOUT
              value: "3s"
          ports:
            - containerPort: 9090
~~~

Kubernetes sẽ cung cấp các biến đó cho tiến trình bên trong container. Spring Boot đọc chúng thông qua nguồn cấu hình môi trường hệ điều hành khi khởi động.

Đối với dữ liệu nhạy cảm, nên dùng cơ chế cung cấp secret của môi trường triển khai thay vì viết giá trị thật vào manifest công khai.

## 8. Tên chuẩn, tên biến và tên thuộc tính Java: bảng đối chiếu

Giả sử ứng dụng có Java record:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public record AppProperties(
        Api api,
        Retry retry,
        boolean auditEnabled
) {
    public record Api(
            String baseUrl,
            Duration readTimeout
    ) {}

    public record Retry(int maxAttempts) {}
}
~~~

Cách đặt tên tương ứng:

| Đường dẫn Java | Tên thuộc tính chuẩn | Biến môi trường |
| --- | --- | --- |
| `api().baseUrl()` | `app.api.base-url` | `APP_API_BASEURL` |
| `api().readTimeout()` | `app.api.read-timeout` | `APP_API_READTIMEOUT` |
| `retry().maxAttempts()` | `app.retry.max-attempts` | `APP_RETRY_MAXATTEMPTS` |
| `auditEnabled()` | `app.audit-enabled` | `APP_AUDITENABLED` |

Khi đọc bảng, đừng tự tạo tên `APP_API_BASE_URL` chỉ vì record component là `baseUrl`. Theo quy tắc biến môi trường chuẩn của Spring Boot, `app.api.base-url` tạo thành `APP_API_BASEURL`.

Spring Boot có thể hỗ trợ những phép chuẩn hóa tên linh hoạt ở một số ngữ cảnh, nhưng **khi thiết kế cấu hình, nên theo đúng phép chuyển đổi tài liệu hóa** để kết quả dễ dự đoán và mọi môi trường dùng một cách đặt tên.

## 9. Nhiều biến môi trường cho danh sách: cách bind vào Java

Giả sử ứng dụng nhận danh sách địa chỉ dịch vụ:

~~~yaml
app:
  services:
    - name: catalog
      url: "https://catalog-dev.example.org"
    - name: payment
      url: "https://payment-dev.example.org"
~~~

Cấu hình có kiểu:

~~~java
import java.util.List;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public record ServicesProperties(List<ServiceEndpoint> services) {
    public record ServiceEndpoint(String name, String url) {}
}
~~~

Khi chuyển sang biến môi trường:

~~~bash
APP_SERVICES_0_NAME=catalog
APP_SERVICES_0_URL=https://catalog.example.org
APP_SERVICES_1_NAME=payment
APP_SERVICES_1_URL=https://payment.example.org
~~~

Bộ Binder có thể dựng `List<ServiceEndpoint>` từ những tên có chỉ số `_0_` và `_1_`.

Nếu danh sách đến từ nhiều nguồn có mức ưu tiên khác nhau, **đừng giả định Spring Boot sẽ nối các phần tử giữa các nguồn theo từng chỉ số**. Với binding vào `List`, danh sách từ nguồn ưu tiên cao hơn thường thay thế danh sách cũ. Khi ghi đè danh sách trong môi trường triển khai, hãy cấp **đầy đủ các phần tử mong muốn** để tránh cấu hình thiếu.

Đối với biến môi trường đơn lẻ, cách dễ hiểu nhất là mỗi phần tử có tên riêng với chỉ số chính xác. Đừng đặt toàn bộ một danh sách object vào một chuỗi ngăn cách bằng dấu phẩy rồi mặc định rằng Spring Boot sẽ parse thành object lồng nhau.

## 10. Giá trị biến môi trường và chuyển đổi kiểu

Biến môi trường từ hệ điều hành được truyền vào tiến trình dưới dạng **chuỗi**. Khi bind vào đối tượng Java, Spring Boot có thể chuyển chuỗi sang kiểu dữ liệu đích bằng các converter đã hỗ trợ.

Ví dụ:

~~~yaml
# application.yml — các giá trị mặc định
app:
  worker:
    enabled: false
    count: 2
    timeout: 5s
    ratio: 0.25
~~~

Các biến override:

~~~bash
APP_WORKER_ENABLED=true
APP_WORKER_COUNT=6
APP_WORKER_TIMEOUT=12s
APP_WORKER_RATIO=0.75
~~~

Java record:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.worker")
public record WorkerProperties(
        boolean enabled,
        int count,
        Duration timeout,
        double ratio
) {}
~~~

Các chuỗi `true`, `6`, `12s` và `0.75` được chuyển thành `boolean`, `int`, `Duration` và `double` khi binding thành công.

Nhưng nếu truyền:

~~~bash
APP_WORKER_COUNT=not-a-number
~~~

thì phép chuyển sang `int` có thể thất bại khi ứng dụng tạo cấu hình/bean. **Đặt tên biến chính xác không bảo đảm giá trị có kiểu hợp lệ**.

Đối với các thuộc tính bắt buộc, nên có validation tại lớp cấu hình hoặc bước kiểm tra khi khởi động. Với secret, không đưa giá trị thật vào log hay bản chụp màn hình.

## 11. Thứ tự ưu tiên: biến môi trường có thể thắng file theo profile

Giả sử có file chung:

~~~yaml
# application.yml
server:
  port: 8080
app:
  client:
    read-timeout: 5s
~~~

File profile:

~~~yaml
# application-prod.yml
server:
  port: 9090
app:
  client:
    read-timeout: 10s
~~~

Và môi trường triển khai truyền:

~~~bash
SPRING_PROFILES_ACTIVE=prod
SERVER_PORT=7070
APP_CLIENT_READTIMEOUT=3s
~~~

Nếu chỉ xét những nguồn này, các giá trị cuối là:

| Thuộc tính | File chung | File prod | Biến môi trường | Kết quả |
| --- | --- | --- | --- | --- |
| `server.port` | 8080 | 9090 | 7070 | **7070** |
| `app.client.read-timeout` | 5s | 10s | 3s | **3s** |

Biến môi trường hệ điều hành có mức ưu tiên cao hơn Config Data trong thứ tự nguồn cấu hình mặc định của Spring Boot.

Tuy vậy, đối số dòng lệnh có thể ưu tiên cao hơn biến môi trường:

~~~bash
SERVER_PORT=7070 java -jar app.jar --server.port=6060
~~~

Nếu không có nguồn đặc biệt nào khác chi phối, ứng dụng dùng cổng **6060**, vì `--server.port=6060` là đối số cấu hình của Spring Boot.

Vì vậy, cần phân biệt hai câu hỏi:

1. **Tên biến nào ánh xạ tới thuộc tính?** Ví dụ `SERVER_PORT` → `server.port`.
2. **Giá trị cuối lấy từ đâu?** Có thể từ biến môi trường, hoặc một nguồn ưu tiên cao hơn.

Việc thay đổi tên đúng chỉ giải quyết câu hỏi thứ nhất.

## 12. \`@Value\`, \`Environment\` và \`@ConfigurationProperties\`

Spring Boot có nhiều cách đọc thuộc tính. Ba cách thường gặp là:

### 12.1. \`@ConfigurationProperties\`

Phù hợp cho một nhóm thuộc tính có cấu trúc và có kiểu rõ ràng:

~~~java
@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(String baseUrl, int maxRetries) {}
~~~

Nếu hệ thống cung cấp `APP_CLIENT_BASEURL` và `APP_CLIENT_MAXRETRIES`, bộ Binder có thể ánh xạ các giá trị vào record.

Cách này tận dụng **relaxed binding** một cách rõ ràng và phù hợp khi cấu hình có nhiều trường.

### 12.2. \`@Value\`

Phù hợp cho thuộc tính đơn giản:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class ServiceMode {
    private final String mode;

    public ServiceMode(@Value("${app.service-mode:default}") String mode) {
        this.mode = mode;
    }

    public String currentMode() {
        return mode;
    }
}
~~~

Ở đây, placeholder dùng **tên thuộc tính chuẩn kebab-case** `app.service-mode`. Tên biến tương ứng là `APP_SERVICEMODE`. Cách viết canonical trong placeholder giúp Spring Boot áp dụng cách tra cứu tên linh hoạt đúng hơn.

Dấu `:default` là giá trị mặc định của placeholder nếu không tìm thấy thuộc tính. Nó không thuộc tên biến môi trường.

### 12.3. \`Environment\`

Có thể truy xuất thuộc tính trực tiếp:

~~~java
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class ServerConfigReader {
    private final Environment environment;

    public ServerConfigReader(Environment environment) {
        this.environment = environment;
    }

    public Integer serverPort() {
        return environment.getProperty("server.port", Integer.class);
    }
}
~~~

`Environment` trả giá trị đang được giải quyết từ các property source, nhưng cách tra cứu tên trực tiếp không nên được xem là hoàn toàn giống cơ chế Binder của `@ConfigurationProperties` ở mọi trường hợp ký tự đặc biệt hoặc cấu trúc phức tạp. Hãy dùng tên canonical nhất quán và ưu tiên `@ConfigurationProperties` cho nhóm thuộc tính.

## 13. Những trường hợp đặc biệt: Map, logger và ký tự bất thường

Quy tắc tên biến môi trường hoạt động dễ dự đoán nhất với **tên thuộc tính chuẩn** có các đoạn chữ, số, dấu chấm và dấu gạch nối.

Một số cấu hình có tên khóa đặc biệt, chẳng hạn Map với key là đường dẫn:

~~~yaml
app:
  rules:
    "[/public/api]": allow
    "[user.role]": admin
~~~

Khi bind vào `Map<String, String>`, cú pháp có ngoặc vuông trong cấu hình giúp giữ những ký tự đặc biệt của key. Việc chuyển cơ học mọi dấu chấm thành `_` và bỏ mọi ký tự đặc biệt trong tên biến môi trường có thể **làm mất thông tin về key gốc**.

Tương tự, tên logger theo package/class có thể chứa dấu chấm, chữ hoa hoặc các ký tự có ý nghĩa riêng. Không nên giả định rằng mọi tên logger hoặc mọi Map key phức tạp đều biểu diễn chính xác được bằng một biến môi trường theo quy tắc thông thường.

Với những trường hợp này, có thể:

- Đặt cấu hình có cấu trúc trong file YAML/properties phù hợp.
- Sử dụng biến môi trường cho những khóa cấu hình đơn giản, rõ ràng.
- Xem xét nguồn cấu hình JSON được Spring Boot hỗ trợ (`SPRING_APPLICATION_JSON`) khi cần diễn tả cấu trúc mà tên biến môi trường thông thường khó giữ nguyên.

Ví dụ biến chứa JSON:

~~~bash
export SPRING_APPLICATION_JSON='{"app":{"client":{"base-url":"https://api.example.org"}}}'
java -jar app.jar
~~~

`SPRING_APPLICATION_JSON` là một cách đưa cấu hình dạng JSON vào Spring Boot, **khác với việc chuyển từng tên khóa thành biến môi trường riêng lẻ**. Cũng cần nhớ nó có vị trí ưu tiên riêng trong thứ tự property source và không nên chứa secret nếu môi trường có thể làm lộ nội dung biến hoặc tham số.

Với các Map key có yêu cầu giữ chính xác chữ hoa, dấu chấm hoặc dấu gạch chéo, cần kiểm tra cách Binder xử lý loại Map đích thay vì đoán kết quả chỉ từ tên biến hệ điều hành.

## 14. Tránh xung đột tên khi bỏ dấu gạch nối

Vì quy tắc chuẩn **bỏ dấu gạch nối**, có những cặp tên chỉ khác cách phân tách từ nhưng chuyển thành cùng một biến môi trường:

~~~text
app.feature-mode      → APP_FEATUREMODE
app.featuremode       → APP_FEATUREMODE
~~~

Nếu cố ý định nghĩa hai thuộc tính khác nghĩa dưới những tên như vậy, cách truy xuất qua biến môi trường sẽ khó phân biệt.

Tương tự:

~~~text
app.client.read-timeout   → APP_CLIENT_READTIMEOUT
app.client.readtimeout    → APP_CLIENT_READTIMEOUT
~~~

Thiết kế tên cấu hình nên theo **một quy ước canonical nhất quán**, thông thường là lowercase kebab-case. Tránh tạo hai khóa chỉ khác dấu gạch nối nhưng mô tả hai giá trị độc lập.

Một kiểu nhầm lẫn khác là gộp tên có dấu chấm và tên có dấu gạch nối:

~~~text
app.retry.max-attempts  → APP_RETRY_MAXATTEMPTS
app.retry.max.attempts  → APP_RETRY_MAX_ATTEMPTS
~~~

Hai đường dẫn này có cấu trúc khác nhau. Khi cùng nhóm thuộc tính được biểu diễn bằng class Java, sự nhầm lẫn giữa object lồng nhau và trường camelCase sẽ dẫn đến tên biến môi trường không đúng như ý định.

## 15. Cấu hình profile qua biến môi trường

Một trong những ví dụ phổ biến nhất là `spring.profiles.active`:

~~~properties
spring.profiles.active=prod
~~~

Tên biến môi trường chuẩn:

~~~bash
SPRING_PROFILES_ACTIVE=prod
~~~

Đặt cùng lúc nhiều profile:

~~~bash
SPRING_PROFILES_ACTIVE=prod,metrics
~~~

Spring Boot sử dụng danh sách profile đang hoạt động để quyết định file `application-{profile}.yml` hoặc những tài liệu `spring.config.activate.on-profile` nào sẽ được xem xét.

Điều quan trọng là **biến môi trường có thể ảnh hưởng đến việc chọn file Config Data**, chứ không chỉ ghi đè thuộc tính sau khi file đã nạp. Các thuộc tính điều khiển cách tìm file, như `spring.config.name`, `spring.config.location` và `spring.config.additional-location`, được xử lý sớm trong quá trình khởi động. Chúng nên được truyền qua nguồn sẵn có ở giai đoạn đó, ví dụ đối số dòng lệnh, Java system property hoặc biến môi trường.

Khi chuyển tên những thuộc tính này thành biến môi trường, vẫn áp dụng quy tắc chung. Ví dụ:

~~~text
spring.config.name                 → SPRING_CONFIG_NAME
spring.config.location             → SPRING_CONFIG_LOCATION
spring.config.additional-location  → SPRING_CONFIG_ADDITIONALLOCATION
~~~

Không nên dựa vào việc tự thêm dấu gạch dưới giữa `ADDITIONAL` và `LOCATION` để suy luận quy tắc chính thức: trong tên chuẩn, hai từ này được nối bằng dấu gạch ngang, nên phép biến đổi chuẩn là **xóa** dấu gạch ngang.

## 16. Mối quan hệ với tệp \`.env\`

Trong thực tế, lập trình viên thường có file tên `.env`:

~~~dotenv
SPRING_PROFILES_ACTIVE=dev
SERVER_PORT=8085
APP_CLIENT_CONNECTTIMEOUT=3s
~~~

Cần phân biệt:

- **Biến môi trường thật:** cặp tên/giá trị được hệ điều hành truyền cho tiến trình Java.
- **Tệp `.env`:** một file văn bản được một công cụ hoặc thư viện nào đó đọc rồi dùng để cấp biến.

Bản thân Spring Boot **không tự động đọc mọi file `.env` tùy ý trên filesystem như một file Config Data mặc định**. Một công cụ như Docker Compose có cách dùng file `.env` riêng cho việc thay thế biến trong cấu hình Compose; muốn biến đến container, vẫn cần khai báo `environment`, `env_file` hoặc cơ chế cấp môi trường phù hợp.

Ví dụ Compose:

~~~yaml
services:
  app:
    image: example/app:latest
    env_file:
      - .env
    ports:
      - "8085:8085"
~~~

Ở đây chính Docker Compose truyền biến từ `.env` vào môi trường container. Spring Boot chỉ đọc các biến đã được truyền đến tiến trình.

Không commit các file `.env` chứa mật khẩu/token thật. Khi lưu template, có thể dùng `.env.example` với giá trị giả và hướng dẫn người triển khai cấp giá trị qua kênh an toàn.

## 17. Chẩn đoán khi biến môi trường không có tác dụng

Một biến đặt tên gần giống tên thuộc tính nhưng giá trị cuối không đổi có thể do **sai quy tắc đổi tên**, **biến chưa thực sự đi vào tiến trình**, hoặc **nguồn ưu tiên cao hơn đã ghi đè**.

Có thể đi theo thứ tự sau:

1. **Viết tên thuộc tính canonical** từ YAML, metadata hoặc record `@ConfigurationProperties`. Ví dụ `app.payment.retry-delay`.
2. **Đổi dấu chấm thành `_`**, bỏ dấu `-`, rồi viết hoa: `APP_PAYMENT_RETRYDELAY`.
3. **Kiểm tra cách cấp biến** trong shell, IDE Run Configuration, Docker Compose, Kubernetes hoặc hệ thống triển khai.
4. **Kiểm tra thời điểm đặt biến**: tiến trình Java phải được khởi chạy sau khi biến được cấp.
5. **Kiểm tra giá trị có hợp lệ với kiểu Java** hay không, như số, boolean, `Duration`.
6. **Kiểm tra nguồn nào thắng**: file profile, biến môi trường, system properties, CLI hoặc cấu hình test.
7. **Nếu là danh sách**, kiểm tra chỉ số và những phần tử được cung cấp trong nguồn có ưu tiên cao.
8. **Nếu là Map key đặc biệt**, xem xét dùng YAML/JSON thay vì ép biểu diễn bằng tên biến đơn giản.

Ví dụ, thuộc tính chuẩn:

~~~properties
app.api.request-timeout=5s
~~~

Thì biến theo quy tắc là:

~~~bash
APP_API_REQUESTTIMEOUT=10s
~~~

Tên `APP_API_REQUEST_TIMEOUT` có thêm ranh giới `_` giữa `REQUEST` và `TIMEOUT`, nên **không phải phép chuyển đổi chuẩn** của `app.api.request-timeout`. Tránh dựa vào khả năng hệ thống diễn giải linh hoạt các tên không theo quy ước khi cấu hình production.

Với dữ liệu nhạy cảm, không nên dùng lệnh in toàn bộ biến môi trường hoặc dump toàn bộ `Environment` ra log. Nếu cần quan sát, chỉ in **tên khóa không nhạy cảm**, trạng thái tồn tại và nguồn cung cấp đã được che giá trị. Những endpoint chẩn đoán như Spring Boot Actuator `env`/`configprops` cần được bảo vệ thích hợp.

## 18. Bài tập thực hành

### Bài 1 — Chuyển tên cơ bản

Chuyển các thuộc tính sau sang tên biến môi trường:

~~~text
server.port
spring.application.name
app.client.base-url
app.cache.max-entries
~~~

**Đáp án:**

~~~text
SERVER_PORT
SPRING_APPLICATION_NAME
APP_CLIENT_BASEURL
APP_CACHE_MAXENTRIES
~~~

Dấu chấm chuyển thành dấu gạch dưới, dấu gạch nối được loại bỏ.

### Bài 2 — Phân biệt object lồng nhau và kebab-case

Chuyển hai tên:

~~~text
app.file.max-size
app.file.max.size
~~~

**Đáp án:**

~~~text
APP_FILE_MAXSIZE
APP_FILE_MAX_SIZE
~~~

Tên đầu có một thuộc tính `max-size`; tên thứ hai có hai cấp `max` và `size`.

### Bài 3 — Danh sách object

Cho YAML:

~~~yaml
app:
  endpoints:
    - name: alpha
      read-timeout: 2s
    - name: beta
      read-timeout: 4s
~~~

Hãy viết tên biến môi trường của `read-timeout` ở phần tử thứ hai.

**Đáp án:** `APP_ENDPOINTS_1_READTIMEOUT`. Số `1` tương ứng phần tử thứ hai vì chỉ số danh sách bắt đầu từ 0.

### Bài 4 — Xác định giá trị cuối

File `application-prod.yml` đặt:

~~~yaml
server:
  port: 9090
~~~

Biến môi trường đặt:

~~~bash
SERVER_PORT=7070
~~~

Lệnh chạy ứng dụng:

~~~bash
java -jar app.jar --spring.profiles.active=prod --server.port=6060
~~~

Ứng dụng dùng cổng nào, nếu không có nguồn đặc biệt ưu tiên cao hơn?

**Đáp án:** `6060`. File profile cung cấp 9090, biến môi trường ghi đè thành 7070, đối số dòng lệnh ghi đè tiếp thành 6060.

### Bài 5 — Binding sang Java record

Cho record:

~~~java
@ConfigurationProperties(prefix = "app.notification")
public record NotificationProperties(
        boolean enabled,
        int maxAttempts,
        java.time.Duration retryDelay
) {}
~~~

Hãy viết tên ba biến môi trường tương ứng.

**Đáp án:**

~~~text
APP_NOTIFICATION_ENABLED
APP_NOTIFICATION_MAXATTEMPTS
APP_NOTIFICATION_RETRYDELAY
~~~

Tên thuộc tính canonical lần lượt là `app.notification.enabled`, `app.notification.max-attempts` và `app.notification.retry-delay`.

### Bài 6 — Phân biệt file và biến môi trường

Một file `.env` chứa:

~~~dotenv
SERVER_PORT=9191
~~~

Nhưng ứng dụng khởi động bằng `java -jar app.jar` không nhận giá trị `9191`. Có thể kết luận Spring Boot chuyển tên `SERVER_PORT` sai không?

**Đáp án:** chưa thể. Tên `SERVER_PORT` đúng cho `server.port`. Cần xác minh file `.env` đã được shell, IDE hoặc công cụ triển khai đọc và truyền thành biến môi trường thật cho tiến trình Java hay chưa.

## 19. Ghi nhớ

- Quy tắc đổi tên thuộc tính canonical sang biến môi trường là **dấu chấm → gạch dưới, xóa dấu gạch nối, viết hoa**.
- `spring.main.log-startup-info` chuyển thành **`SPRING_MAIN_LOGSTARTUPINFO`**, không phải phép thêm `_` giữa mọi từ.
- Danh sách dùng chỉ số được bao bằng dấu gạch dưới, ví dụ `app.targets[0].url` → `APP_TARGETS_0_URL`.
- `@ConfigurationProperties` là cơ chế phù hợp để bind các thuộc tính có cấu trúc sang record/class Java; relaxed binding hỗ trợ tên cấu hình dạng canonical.
- Biến môi trường thường có **ưu tiên cao hơn Config Data**, nhưng có thể bị CLI hoặc nguồn đặc biệt khác ghi đè.
- Cấp biến cho **tiến trình Java** qua shell, Docker, Compose, Kubernetes hoặc IDE. Một file `.env` đứng riêng không bảo đảm đã tạo biến môi trường.
- Tránh tự ý chèn dấu `_` vào những đoạn kebab-case; tránh đặt tên cấu hình gây xung đột sau khi loại bỏ dấu gạch nối.
- Với Map key phức tạp, giá trị nhạy cảm hoặc cấu trúc JSON lồng nhau, hãy chọn cơ chế cấu hình phù hợp thay vì cố mã hóa mọi thứ vào tên biến môi trường.

Tài liệu tham khảo:

- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html)
- [Spring Boot — Type-safe Configuration Properties](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.typesafe-configuration-properties)
