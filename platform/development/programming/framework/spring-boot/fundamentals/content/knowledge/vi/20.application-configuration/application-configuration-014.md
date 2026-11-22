# Phân biệt cấu hình ứng dụng với secret cần cung cấp từ môi trường

Một ứng dụng Spring Boot thường cần nhiều thông số để hoạt động: cổng HTTP, timeout, tên service, địa chỉ database, mức log, khóa API, mật khẩu truy cập hoặc chứng chỉ xác thực. Các giá trị này đều có thể được Spring Boot đọc qua `Environment`, nhưng **không phải giá trị nào cũng nên được lưu và phân phối theo cùng một cách**.

Phân biệt hai nhóm là một nguyên tắc nền tảng:

- **Cấu hình ứng dụng (application configuration)**: những giá trị mô tả cách ứng dụng hoạt động, thường có thể lưu trong source control nếu không chứa thông tin nhạy cảm.
- **Secret**: những giá trị mà việc tiết lộ có thể cấp quyền truy cập, cho phép giả mạo danh tính, giải mã dữ liệu hoặc gây thiệt hại. Secret cần được cấp từ một kênh bảo mật bên ngoài mã nguồn và được quản lý theo quyền truy cập, vòng đời và chính sách xoay vòng riêng.

Từ “môi trường” trong chủ đề này nên hiểu là **môi trường triển khai và cơ chế cấp cấu hình runtime**, không chỉ là environment variables. Secret có thể được cung cấp qua biến môi trường, file được mount an toàn, Kubernetes Secret, secret manager hoặc cơ chế tích hợp danh tính của nền tảng. Những cách này khác nhau về mức độ bảo vệ và khả năng vận hành.

Bài học trình bày cách phân loại giá trị, kết hợp Spring Boot configuration với secret từ môi trường, sử dụng `@ConfigurationProperties` và thực hành triển khai/kiểm thử mà không đưa thông tin nhạy cảm vào repository.

## 1. Thế nào là cấu hình ứng dụng?

Cấu hình ứng dụng là những tham số làm thay đổi hành vi chương trình mà không cần biên dịch lại. Chúng giúp cùng một artifact có thể chạy ở môi trường phát triển, thử nghiệm và production với những giá trị phù hợp.

Ví dụ:

~~~yaml
server:
  port: 8080

spring:
  application:
    name: catalog-service

app:
  catalog:
    page-size: 50
    cache-enabled: true
  partner:
    base-url: https://partner-api.example.invalid
    connect-timeout: 3s
~~~

Những property này cho biết ứng dụng chạy ở cổng nào, có bật cache không, page size bao nhiêu và timeout kết nối là bao lâu.

Phần lớn các giá trị như vậy **không phải secret**. Chúng có thể nằm trong `application.yml` của dự án, được review trong pull request và quản lý phiên bản cùng code.

Tuy nhiên, **không phải mọi URL hay hostname đều mặc nhiên công khai**. Một URL chứa query token, embedded password hoặc endpoint nội bộ cần bảo mật có thể trở thành thông tin nhạy cảm. Phân loại dựa vào nội dung và hậu quả khi lộ, không chỉ dựa vào tên trường.

## 2. Thế nào là secret?

Secret là dữ liệu cần giữ bí mật vì người biết giá trị đó có thể nhận được quyền hoặc lợi thế không được phép.

Ví dụ:

- Mật khẩu database và thông tin xác thực của người dùng dịch vụ.
- API key, access token, refresh token, webhook signing secret.
- Private key dùng để ký JWT, TLS private key, SSH private key.
- Client secret trong OAuth2, mật khẩu kết nối message broker.
- Encryption key, khóa HMAC hoặc chuỗi dùng để giải mã dữ liệu.
- Credentials của cloud provider, nếu hệ thống vẫn phải sử dụng long-lived credentials.

Ví dụ sai trong `application-prod.yml`:

~~~yaml
spring:
  datasource:
    username: catalog_writer
    password: SuperSecretPassword123

app:
  payments:
    api-key: live-key-abcdef123456
~~~

Các giá trị trên chỉ là chuỗi minh họa, không phải credential thật. Vấn đề thiết kế là chúng được ghi **trực tiếp** trong source file có thể được commit, sao chép, đưa vào artifact hoặc hiển thị trong pipeline/log.

Khi secret bị đưa vào Git, xóa dòng khỏi nhánh hiện tại không xóa nó khỏi lịch sử commit, các bản clone, cache CI hoặc những bản sao đã tồn tại. Secret thật đã bị lộ cần được **thu hồi hoặc xoay vòng**, không chỉ “xóa rồi commit lại”.

## 3. Bảng phân loại config và secret

| Giá trị | Phân loại thông thường | Ghi chú |
|---|---|---|
| `server.port` | Config | Thường có thể lưu trong source control |
| `spring.application.name` | Config | Tên định danh service |
| `app.client.connect-timeout` | Config | Điều chỉnh hành vi |
| `app.feature.enabled` | Config | Cờ tính năng cố định theo triển khai |
| URL API không chứa credential | Config, có thể nhạy cảm tùy hệ thống | Xem chính sách công bố endpoint nội bộ |
| JDBC URL không chứa username/password | Config, có thể nhạy cảm tùy hệ thống | Không được nhúng mật khẩu trong URL |
| Database username | Thông tin cần kiểm soát tùy chính sách | Có thể là định danh không bí mật, nhưng không nên công bố bừa bãi |
| Database password | Secret | Cấp từ nguồn runtime an toàn |
| API key hoặc bearer token | Secret | Có quyền gọi hệ thống khác |
| TLS certificate public | Thường không phải secret | Public certificate khác với private key |
| TLS private key | Secret | Cần bảo vệ bằng quyền truy cập/secret manager |
| JWT signing key | Secret | Lộ key có thể cho phép giả mạo token |
| OAuth client ID | Thường không phải secret | Phân biệt với OAuth client secret |
| OAuth client secret | Secret | Không đặt trong frontend hoặc repository |
| Mật khẩu dummy dùng trong test | Test fixture, không có quyền thật | Vẫn phải ghi rõ là giá trị giả, không tái sử dụng production |

Không nên chỉ nhìn tên biến để kết luận. Một giá trị như `DATABASE_URL` có thể chứa `user:password@host`; khi đó toàn bộ URL phải được đối xử như secret. Ngược lại, public key có thể được chia sẻ có chủ đích, dù tên trường có chữ “key”.

## 4. Vì sao không nên đặt secret trong application.yml?

`application.yml` và `application.properties` thường là một phần của source tree hoặc artifact ứng dụng. Một secret hard-code có thể bị lộ qua nhiều đường:

1. **Repository và lịch sử Git:** commit, pull request, fork, bản clone và backup.
2. **Build artifact:** file cấu hình được đóng gói vào JAR hoặc image.
3. **CI/CD:** log build, thông số job, variables và artifact của pipeline.
4. **Chia sẻ tài liệu:** copy cấu hình vào issue, chat, wiki hoặc email.
5. **Chẩn đoán runtime:** dump Environment, exception, tracing, actuator hoặc debug log.
6. **Quyền truy cập không phù hợp:** quá nhiều developer có thể đọc credential production chỉ vì có quyền đọc code.

Phương án tốt hơn là **lưu cấu trúc cấu hình và tên tham chiếu** trong repository; secret thực tế được cấp từ môi trường triển khai.

Ví dụ `application.yml`:

~~~yaml
app:
  payments:
    base-url: https://payments.example.invalid
    connect-timeout: 3s
    api-key: ${PAYMENTS_API_KEY}

spring:
  datasource:
    url: ${DB_JDBC_URL}
    username: ${DB_USERNAME}
    password: ${DB_PASSWORD}
~~~

Ở đây repository chỉ chứa tên placeholder, không chứa giá trị khóa API hoặc mật khẩu. Khi khởi động, Spring Boot phân giải các placeholder thông qua `Environment` và các property sources khả dụng.

Đây chưa phải lời giải bảo mật hoàn chỉnh. Nếu bí mật được cấp bằng environment variable, secret vẫn tồn tại trong môi trường và bộ nhớ process. Bảo mật phụ thuộc vào cách hệ thống triển khai cấp giá trị, ai có thể đọc nó, có bị log không và quy trình xoay vòng.

## 5. Spring Boot nhận cấu hình từ những nguồn nào?

Spring Boot hỗ trợ cơ chế **externalized configuration**: ứng dụng không cần biên dịch lại khi cấu hình triển khai thay đổi.

Những nguồn phổ biến:

- `application.yml` và `application.properties` được đóng gói hoặc đặt ngoài artifact.
- `application-{profile}.yml` cho cấu hình theo profile.
- Environment variables của process.
- Java system properties.
- Command-line arguments.
- `spring.config.import` để nạp thêm configuration data từ vị trí được hỗ trợ.
- Các `PropertySource` bổ sung qua tích hợp/framework phù hợp.
- Secret manager hoặc nền tảng triển khai cung cấp dữ liệu cho những nguồn trên.

Các nguồn có **thứ tự ưu tiên**. Nếu cùng một property được khai báo nhiều lần, Spring Boot sử dụng giá trị từ nguồn có độ ưu tiên cao hơn theo cơ chế configuration của phiên bản đang dùng.

Ví dụ:

~~~yaml
server:
  port: 8080
~~~

Ứng dụng có thể nhận `SERVER_PORT=9090` từ environment của process; thông thường giá trị bên ngoài này có thể override giá trị trong file cấu hình.

Thứ tự chi tiết phụ thuộc Spring Boot version, config import, profile và các nguồn tùy chỉnh. Không nên giả định mọi loại nguồn có cùng mức ưu tiên ở mọi ứng dụng.

### 5.1. Environment variable không phải Spring profile

Hai khái niệm khác nhau:

- **Environment variable:** một cách cấp key/value cho process, ví dụ `DB_PASSWORD`.
- **Spring profile:** nhóm cấu hình/bean được kích hoạt như `dev`, `test` hoặc `prod`, thường qua `spring.profiles.active`.

Cùng profile `prod` có thể được chạy trên nhiều cluster với secret khác nhau. Một profile **không phải** kho lưu secret và không có cơ chế mã hóa riêng.

## 6. Ví dụ đầy đủ: config trong repository, secret từ runtime

Giả sử ứng dụng gọi một payment provider. Ta tách những giá trị an toàn để review khỏi khóa API bí mật.

`src/main/resources/application.yml`:

~~~yaml
spring:
  application:
    name: checkout-service

app:
  payments:
    endpoint: https://payments.example.invalid
    timeout: 5s
    api-key: ${PAYMENTS_API_KEY}
~~~

Ứng dụng dùng `@ConfigurationProperties`:

~~~java
package com.example.checkout.config;

import java.net.URI;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.payments")
public record PaymentProperties(
        URI endpoint,
        Duration timeout,
        String apiKey) {
}
~~~

Khai báo đăng ký properties type:

~~~java
package com.example.checkout;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class CheckoutApplication {

    public static void main(String[] args) {
        SpringApplication.run(CheckoutApplication.class, args);
    }
}
~~~

Dùng trong service:

~~~java
package com.example.checkout.service;

import com.example.checkout.config.PaymentProperties;
import org.springframework.stereotype.Service;

@Service
public class PaymentService {

    private final PaymentProperties properties;

    public PaymentService(PaymentProperties properties) {
        this.properties = properties;
    }

    public void submitPayment() {
        // Dùng properties.endpoint() và properties.apiKey()
        // khi cấu hình HTTP client để gọi provider.
        // Không ghi apiKey() ra log.
    }
}
~~~

Đây là cú pháp Spring Boot 3 với Java record. Dòng Boot 2.x có thể dùng JavaBean hoặc constructor binding theo API và phiên bản tương ứng. Điểm chính của bài học không phụ thuộc cách bind: **object có thể chứa secret khi chạy, nhưng giá trị secret không nằm trong repository**.

### 6.1. Cấp giá trị bằng biến môi trường

Ví dụ chạy local trong một shell POSIX:

~~~bash
export PAYMENTS_API_KEY='local-placeholder-value'
./gradlew bootRun
~~~

Giá trị trên chỉ là placeholder minh họa, không dùng cho production. Nếu copy một secret thật vào lệnh shell, nó vẫn có thể xuất hiện trong terminal history, command recording hoặc các công cụ quản lý phiên; cần chọn quy trình nhập/cấp secret không làm lộ giá trị.

Trên PowerShell, cú pháp là:

~~~powershell
$env:PAYMENTS_API_KEY = 'local-placeholder-value'
./gradlew bootRun
~~~

Biến môi trường được truyền vào **process** ứng dụng hoặc process con theo cách hệ điều hành/shell hỗ trợ. Nó không phải một cấu hình đã commit vào `application.yml`.

### 6.2. Dùng tên property trực tiếp qua relaxed binding

Nếu không có placeholder `app.payments.api-key` trong file YAML, Spring Boot có thể bind một environment variable tương ứng trực tiếp vào `@ConfigurationProperties` theo quy tắc chuyển đổi tên.

Ví dụ với property canonical:

~~~text
app.payments.api-key
~~~

Tên environment variable theo quy tắc relaxed binding của Spring Boot:

~~~text
APP_PAYMENTS_APIKEY
~~~

Quy tắc tổng quát: đổi dấu chấm thành underscore, bỏ dấu gạch nối rồi chuyển sang uppercase. Vì vậy `APP_PAYMENTS_API_KEY` không nên được giả định là tương đương trong mọi trường hợp; hãy theo quy tắc tên environment variable của Spring Boot và kiểm tra property được bind.

Sử dụng placeholder `${PAYMENTS_API_KEY}` trong YAML có một lợi ích thực dụng: tên biến triển khai ngắn, rõ ràng, không phải suy diễn từ relaxed binding. Cả hai mô hình đều hợp lệ nếu được cấu hình nhất quán.

## 7. Nếu thiếu secret thì ứng dụng phải làm gì?

Một secret bắt buộc không nên được thay bằng một mật khẩu yếu hoặc một khóa giả trong production.

Ví dụ nguy hiểm:

~~~yaml
app:
  payments:
    api-key: ${PAYMENTS_API_KEY:password123}
~~~

Phần sau dấu hai chấm là **giá trị mặc định** của placeholder. Nếu môi trường quên cấp secret, ứng dụng có thể dùng `password123` mà không có cảnh báo rõ ràng.

Nên khai báo không có default bí mật:

~~~yaml
app:
  payments:
    api-key: ${PAYMENTS_API_KEY}
~~~

Và thiết kế cơ chế **fail fast** trước khi chấp nhận request nếu secret không tồn tại hoặc không hợp lệ.

Với `@ConfigurationProperties`, có thể dùng Bean Validation:

~~~java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

import java.net.URI;

@Validated
@ConfigurationProperties(prefix = "app.payments")
public record PaymentProperties(
        @NotNull URI endpoint,
        @NotBlank String apiKey) {
}
~~~

Cần có implementation Bean Validation trên classpath, thường qua:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-validation'
}
~~~

**Lưu ý:** `@NotBlank` bắt được chuỗi rỗng hoặc whitespace, nhưng không tự chứng minh mọi placeholder đều đã được phân giải hay key thực sự có quyền trên provider. Tùy cách tạo property source và phiên bản, một placeholder chưa được phân giải có thể gây lỗi binding, bị giữ lại ở dạng chuỗi hoặc biểu hiện thành lỗi khác. Vì vậy, phải kiểm thử startup với secret bị thiếu và xây dựng kiểm tra cấu hình phù hợp, thay vì mặc định chỉ một annotation bảo đảm mọi trường hợp.

Nếu hệ thống yêu cầu kiểm tra key thật với dịch vụ ngoài, cân nhắc sự cân bằng giữa fail-fast và khả năng khởi động khi upstream tạm thời không khả dụng. Không nên gọi mạng trong constructor của properties record.

## 8. Cấu hình theo profile vẫn không phải nơi lưu secret

Profile giúp phân nhóm những **giá trị không bí mật** theo môi trường.

Ví dụ:

`application.yml`:

~~~yaml
app:
  client:
    timeout: 3s
~~~

`application-dev.yml`:

~~~yaml
app:
  client:
    endpoint: http://localhost:9090
    timeout: 10s
~~~

`application-prod.yml`:

~~~yaml
app:
  client:
    endpoint: https://partner.example.invalid
    timeout: 2s
~~~

Những file này có thể được review trong repository nếu không chứa thông tin nhạy cảm. Secret cho mỗi môi trường vẫn được cấp riêng:

~~~text
dev deployment  -> PAYMENTS_API_KEY của dev
test deployment -> PAYMENTS_API_KEY của test
prod deployment -> PAYMENTS_API_KEY của production
~~~

Không nên lưu một password production trong `application-prod.yml` chỉ vì file đó “chỉ được dùng ở production”. File vẫn có thể được commit, đưa vào JAR hoặc đọc được từ artifact.

### Phân tách quyền truy cập theo môi trường

Trong hệ thống triển khai tốt, quyền đọc secret production khác với quyền đọc secret dev/test. Một developer có thể chạy unit test và integration test với dữ liệu giả mà không cần credential production. Nếu cùng một secret được tái sử dụng giữa dev và production, việc lộ ở môi trường ít được bảo vệ có thể ảnh hưởng môi trường quan trọng hơn.

## 9. Environment variables: thuận tiện nhưng không tự động an toàn

Biến môi trường là một cách phổ biến để truyền secret từ hệ thống triển khai cho process Spring Boot. Ưu điểm:

- Không cần lưu giá trị trong source file.
- Dễ tích hợp với container, CI/CD, cloud runtime.
- Cùng một artifact chạy ở nhiều môi trường với secret khác nhau.
- Spring Boot tự đọc môi trường và hỗ trợ bind giá trị.

Tuy nhiên, environment variable **không được mã hóa mặc định chỉ vì nó là environment variable**. Rủi ro gồm:

- Process cùng quyền hoặc người có quyền quản trị hệ thống có thể đọc environment theo điều kiện hệ điều hành.
- Debugger, process dump hoặc công cụ chẩn đoán có thể thu thập giá trị.
- Một ứng dụng có thể vô tình log toàn bộ Environment.
- CI job có thể in secret khi bật shell tracing hoặc log cấu hình sai.
- Một số nền tảng có UI/CLI hiển thị biến môi trường cho người có quyền xem workload.
- Environment của process thường được chụp lúc khởi động; thay giá trị trong secret store không tự cập nhật process đang chạy.

Vì vậy, dùng environment variable là **cách vận chuyển**, không phải sự bảo đảm bí mật tuyệt đối. Cần kết hợp với quản lý quyền, tránh log, cơ chế triển khai phù hợp và quy trình xoay vòng.

### 9.1. Không truyền secret trực tiếp trên command line nếu có lựa chọn an toàn hơn

Ví dụ nên tránh trong production:

~~~bash
java -jar checkout.jar --app.payments.api-key=real-secret-here
~~~

Argument có thể bị thấy trong process listing, log command hoặc monitoring. Cũng tránh để secret nằm trong command được ghi lại trong shell history.

Dùng kênh secret do nền tảng hỗ trợ (environment được inject có kiểm soát hoặc file được mount an toàn) thường phù hợp hơn, nhưng vẫn phải đánh giá quyền truy cập và khả năng bị ghi log.

### 9.2. Không ghi toàn bộ Environment khi debug

Ví dụ nguy hiểm:

~~~java
log.info("Payment API key: {}", properties.apiKey());
~~~

Không ghi token, password hoặc private key ra log. Đối với thông tin chẩn đoán, có thể ghi trạng thái tồn tại hoặc metadata không nhạy cảm:

~~~java
log.info("Payment provider endpoint configured: {}",
        properties.endpoint() != null);
~~~

Ngay cả endpoint cũng có thể nhạy cảm nếu chứa token hoặc tham số truy cập. Khi thiết kế log, hãy chủ động quyết định dữ liệu nào có thể được xuất ra.

## 10. Cấp secret qua file được mount và configtree

Một cách khác là cung cấp secret dưới dạng file ở filesystem của runtime. Ví dụ một orchestrator hoặc secret manager mount file:

~~~text
/run/secrets/
└── app.payments.api-key
~~~

Nội dung file là secret do hệ thống triển khai cấp, không thuộc repository và không được đóng gói trong image.

Spring Boot hỗ trợ nhập cấu hình kiểu `configtree` từ phiên bản 2.4 trở đi. Ví dụ:

~~~yaml
spring:
  config:
    import: "configtree:/run/secrets/"
~~~

Với cấu trúc như trên, tên file `app.payments.api-key` tương ứng property `app.payments.api-key`, còn nội dung file là giá trị được bind.

`configtree:` ở đây là **nguồn config data**, không phải một công cụ mã hóa. Độ an toàn đến từ cách mount, file permissions, phân quyền container, volume, secret store và những process có thể đọc file.

### 10.1. optional:configtree và secret bắt buộc

Có thể thấy cấu hình:

~~~yaml
spring:
  config:
    import: "optional:configtree:/run/secrets/"
~~~

Tiền tố `optional:` cho phép vị trí import không tồn tại mà không làm startup thất bại chỉ vì thiếu đường dẫn. Điều này tiện trong môi trường phát triển, nhưng **không phù hợp nếu production bắt buộc có secret tại thư mục đó** và không có kiểm tra bổ sung.

Nếu một secret là bắt buộc, nên để đường dẫn bắt buộc hoặc có validation/fail-fast thích hợp. Đừng chọn `optional` một cách vô thức rồi để ứng dụng khởi động không có credentials cần thiết.

### 10.2. File permissions và quyền truy cập

Để bảo vệ secret file:

- Chỉ mount vào workload cần dùng.
- Hạn chế quyền đọc của user/group trong container.
- Không ghi secret vào lớp image.
- Tránh copy nội dung file vào log hoặc artifact.
- Cân nhắc hành vi update mount của nền tảng và liệu ứng dụng có đọc lại file hay không.
- Nếu dùng secret volume, kiểm tra backup và quyền truy cập node/host.

Thay đổi nội dung file secret không đồng nghĩa `@ConfigurationProperties` hoặc kết nối đang sử dụng sẽ tự động refresh. Cần thiết kế cơ chế áp dụng secret mới.

## 11. Kubernetes Secret: không đồng nghĩa mã hóa an toàn mặc định

Trong Kubernetes, workload có thể nhận secret qua environment variable hoặc volume. Ví dụ một container tham chiếu secret đã được tạo trước đó:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: checkout-service
spec:
  replicas: 1
  selector:
    matchLabels:
      app: checkout-service
  template:
    metadata:
      labels:
        app: checkout-service
    spec:
      containers:
        - name: app
          image: example/checkout-service:1.0
          env:
            - name: PAYMENTS_API_KEY
              valueFrom:
                secretKeyRef:
                  name: payments-credentials
                  key: api-key
~~~

Manifest trên không chứa giá trị secret, chỉ tham chiếu Secret object bằng tên và key. Việc tạo, phân quyền và quản lý `payments-credentials` thuộc quy trình triển khai riêng.

**Cảnh báo quan trọng:** Kubernetes Secret object thường có thể biểu diễn dữ liệu bằng Base64 trong manifest/API; **Base64 là encoding, không phải encryption**. Để đạt mức bảo vệ phù hợp, cần xem xét RBAC, encryption at rest của cluster, quyền truy cập API server/etcd, network/runtime security và hạn chế người có quyền đọc secret.

### 11.1. Env injection hay volume?

| Cách cấp | Ưu điểm | Giới hạn |
|---|---|---|
| Secret thành environment variable | Dễ dùng với placeholder và relaxed binding | Giá trị environment của process thường không tự cập nhật sau khi Secret thay đổi |
| Secret được mount thành file | Không cần đẩy giá trị vào biến môi trường; phù hợp `configtree` | Quyền truy cập file và cơ chế reload phải được kiểm soát |
| External secret manager / CSI integration | Tích hợp quản lý quyền, audit, rotation | Cần cấu hình identity và hành vi cấp/làm mới secret phù hợp |

Không có lựa chọn nào an toàn tuyệt đối trong mọi tổ chức. Chọn dựa trên threat model, khả năng vận hành, quy trình quản lý và quyền truy cập thực tế.

## 12. Secret manager: tốt hơn cho hệ thống cần kiểm soát chặt

Với production, nhiều hệ thống sử dụng secret manager chuyên dụng, chẳng hạn dịch vụ cloud hoặc hệ thống quản lý secret nội bộ. Những công cụ này có thể cung cấp:

- Chính sách truy cập theo service/workload identity.
- Audit log cho hành động đọc/thay đổi secret.
- Rotation/expiration với quy trình có kiểm soát.
- Phiên bản secret và cách rollback khi cần.
- Tích hợp deploy để cấp secret cho workload không cần ghi vào Git.
- Mã hóa và quản trị khóa theo khả năng cụ thể của nhà cung cấp.

Hai cách tích hợp phổ biến:

1. **Nền tảng cấp secret cho process:** deploy controller/agent đọc secret manager và đưa vào environment hoặc mount file trước khi Spring Boot bắt đầu.
2. **Ứng dụng tích hợp secret store ở runtime/config bootstrap:** sử dụng thư viện tương thích để tải cấu hình từ dịch vụ ngoài hoặc yêu cầu credential qua SDK theo quyền của workload.

Sơ đồ:

~~~text
                Source repository
                (code + non-secret defaults)
                          |
                          v
                    Build artifact
                          |
                          v
                     Deployment
                          |
             +------------+------------+
             |                         |
             v                         v
    Application config           Secret manager
    (endpoint, timeout)          (API keys, passwords)
             |                         |
             +------------+------------+
                          |
                          v
                Spring Boot process
                   Environment /
                   mounted files /
                   approved client
                          |
                          v
               Typed configuration beans
~~~

Không nên lấy một secret từ secret manager rồi vô tình lưu lại vào một file `application-prod.yml` được commit, hoặc ghi nó ra stdout trong pipeline. Chuyển secret giữa các hệ thống chỉ an toàn khi mọi bước trung gian được kiểm soát.

### 12.1. Ưu tiên workload identity thay vì long-lived credentials

Nếu nền tảng hỗ trợ, ứng dụng có thể xác thực với secret manager bằng danh tính workload/service account thay vì phải lưu thêm một static master key để lấy các secret khác.

Điều này giảm bài toán “lưu secret để đọc secret”, nhưng không loại bỏ yêu cầu quản lý quyền. Identity vẫn cần scope tối thiểu và cơ chế bảo vệ metadata/service account token phù hợp.

## 13. CI/CD: secret không thuộc artifact và log

Một quy trình triển khai thường có ba giai đoạn:

~~~text
Build -> Test -> Deploy
~~~

Nguyên tắc nên áp dụng:

- **Build:** tạo cùng một artifact từ source code, không đưa production secret vào JAR hoặc image.
- **Test:** dùng fixture giả, test credential hoặc secret dành riêng môi trường thử nghiệm.
- **Deploy:** cấp secret production vào runtime bằng kênh triển khai có phân quyền.

Nếu build Docker image, tránh:

~~~dockerfile
# Không nên:
ARG PAYMENTS_API_KEY
ENV PAYMENTS_API_KEY=$PAYMENTS_API_KEY
~~~

Cách này có thể để lại dấu vết trong image history/metadata hoặc lớp image tùy quy trình build. Không dùng build argument hoặc Dockerfile ENV để nhúng long-lived secret vào image phát hành.

Thay vào đó, build một image trung tính và cấp secret khi triển khai:

~~~text
checkout-service:1.0
  +
runtime configuration
  +
secret injection
  =
checkout-service chạy ở môi trường cụ thể
~~~

### 13.1. Quyền của CI/CD pipeline

Pipeline cũng là một đối tượng có quyền và có thể làm lộ secret qua:

- Log verbose hoặc shell tracing.
- Step print environment.
- Lạm dụng quyền của job chạy trên pull request từ nguồn không tin cậy.
- Artifact hoặc cache chứa file secret.
- Cấp quyền production secret cho mọi branch/job.

Chỉ job cần thiết mới được truy cập secret tương ứng. Đối với PR từ nguồn không tin cậy, không cấp production credentials. Cần giới hạn người có thể chỉnh pipeline và cấu hình secret injection.

## 14. Actuator, lỗi cấu hình và dữ liệu nhạy cảm

Spring Boot Actuator giúp quan sát ứng dụng, nhưng một số endpoint có thể phản ánh cấu hình, property source hoặc bean metadata. Các phiên bản Boot có cơ chế kiểm soát hiển thị/sanitization giá trị; tuy nhiên, **không nên coi masking mặc định là lý do có thể công khai mọi endpoint hoặc ghi secret vào config tùy ý**.

Cần chú ý:

- Không expose `/actuator/env` hoặc `/actuator/configprops` ra internet công khai nếu chưa có chính sách bảo mật phù hợp.
- Giới hạn endpoint được expose theo nhu cầu vận hành.
- Bật authentication/authorization và mạng nội bộ cho endpoint nhạy cảm.
- Không log nguyên `Environment` hoặc bean properties chứa secret.
- Không đưa token vào exception message, HTTP error response hoặc trace attributes.
- Đừng ghi secret vào metric tag/label; metrics thường được lưu lâu và có nhiều người đọc.

Ví dụ nên tránh:

~~~java
log.debug("Datasource password: {}", dataSourceProperties.getPassword());
~~~

Có thể log thông tin chẩn đoán được chọn lọc:

~~~java
log.info("Datasource configuration loaded");
~~~

Không in password hoặc token ngay cả khi log level chỉ bật ở môi trường phát triển; log dev vẫn có thể được thu thập và chia sẻ.

## 15. Xử lý secret bị lộ

Nếu một secret thật đã xuất hiện trong repository, log, tài liệu hoặc artifact, quy trình xử lý không nên dừng ở việc xóa dòng code.

Các bước khái quát:

1. **Thu hồi hoặc rotate secret** tại hệ thống cấp quyền ngay khi phù hợp với quy trình ứng phó.
2. Đánh giá phạm vi ảnh hưởng: thời gian lộ, quyền truy cập, dịch vụ và môi trường bị ảnh hưởng.
3. Kiểm tra log/audit theo khả năng hệ thống để nhận diện truy cập bất thường.
4. Xóa dấu vết khỏi nơi không cần giữ và xử lý lịch sử Git theo quy trình có kiểm soát; không mặc định rewrite history là đã thu hồi quyền từ mọi bản sao.
5. Cấp secret mới bằng kênh runtime an toàn.
6. Đưa secret scanning, review và least-privilege vào quy trình phòng ngừa.

Với khóa API, credential database hoặc private key, thay giá trị thường phải phối hợp với rollout để tránh làm dịch vụ gián đoạn. Có thể cần hỗ trợ overlap ngắn giữa credential cũ/mới nếu provider cho phép, nhưng quyền của secret cũ phải được giới hạn và thu hồi theo kế hoạch.

## 16. Xoay vòng secret và khả năng áp dụng thay đổi

Secret có vòng đời khác với cấu hình thông thường.

Cấu hình như `app.client.timeout=3s` có thể chỉ thay đổi khi deploy phiên bản mới. Secret như database password, API key hoặc TLS private key có thể cần xoay vòng vì chính sách, hết hạn hoặc sự cố.

Một quy trình rotation thường gồm:

~~~text
Tạo secret mới
      |
      v
Cập nhật secret store / nguồn cấp runtime
      |
      v
Triển khai hoặc reload ứng dụng/connection
      |
      v
Xác nhận ứng dụng dùng credential mới
      |
      v
Thu hồi credential cũ
~~~

**Cần phân biệt thay secret ở nguồn với thay secret đang được ứng dụng sử dụng.**

- Environment variables thường được process nhận lúc khởi động, nên cập nhật secret ở nền tảng có thể cần restart/rollout.
- Mount secret file có thể thay đổi theo cơ chế volume, nhưng `@ConfigurationProperties` không tự rebind chỉ vì file nội dung thay đổi.
- Một database connection pool có thể giữ kết nối đã xác thực bằng credential cũ.
- HTTP client hoặc SDK có thể cache token/credential.
- Một secret manager client có thể hỗ trợ refresh theo cơ chế riêng, nhưng phải thiết kế rõ cache TTL, retry và xử lý lỗi.

Vì vậy, khi chọn kênh cấp secret, cần thiết kế **cách áp dụng phiên bản mới** và kiểm thử rotation, không chỉ cách đọc giá trị ban đầu.

## 17. Phân biệt secret với mã hóa cấu hình

Đôi khi người phát triển hỏi: “Có thể mã hóa password rồi lưu chuỗi mã hóa trong YAML không?”

Một giá trị encrypted trong file có thể an toàn hơn plain text **nếu** khóa giải mã được bảo vệ độc lập, quyền truy cập và lifecycle được quản lý tốt. Tuy nhiên, nó vẫn đặt ra các câu hỏi:

- Khóa giải mã nằm ở đâu?
- Ai có quyền giải mã và audit hành động?
- Khóa và ciphertext có cùng tồn tại trong repository/image không?
- Quy trình rotation của cả secret và encryption key như thế nào?
- App cần dữ liệu plaintext ở thời điểm nào, và có thể bị log/dump không?

Nếu lưu cả ciphertext và khóa giải mã cạnh nhau, lợi ích bảo mật có thể rất hạn chế. Một secret manager hoặc secret injection của nền tảng thường cung cấp mô hình quản lý thực tế rõ ràng hơn.

**Base64 không phải mã hóa**, và việc dùng file tên `secrets.yml` không làm file đó tự trở nên an toàn.

## 18. Kiểm thử cấu hình mà không cần secret production

Một dự án được thiết kế tốt phải cho phép developer chạy test với secret giả hoặc credential dành riêng cho môi trường thử nghiệm.

Ví dụ `application-test.yml`:

~~~yaml
app:
  payments:
    endpoint: http://localhost:9099
    timeout: 1s
    api-key: local-test-placeholder
~~~

Giá trị trong ví dụ là chuỗi thử nghiệm, không cấp quyền truy cập môi trường thật. Trong test, có thể override property trực tiếp:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest(properties = {
        "app.payments.endpoint=http://localhost:9099",
        "app.payments.timeout=1s",
        "app.payments.api-key=unit-test-placeholder"
})
class PaymentServiceTest {

    @Test
    void contextLoadsWithTestConfiguration() {
        // Có thể bổ sung assertion về bean và giá trị đã bind.
    }
}
~~~

Test cho configuration binding có thể dùng `ApplicationContextRunner` để tránh khởi động toàn bộ web server:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

class PaymentPropertiesTest {

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(PaymentProperties.class)
    static class TestConfiguration {
    }

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(TestConfiguration.class);

    @Test
    void bindsNonSecretAndPlaceholderTestValues() {
        runner
                .withPropertyValues(
                        "app.payments.endpoint=https://example.invalid",
                        "app.payments.timeout=2s",
                        "app.payments.api-key=test-only-placeholder"
                )
                .run(context -> {
                    PaymentProperties p =
                            context.getBean(PaymentProperties.class);

                    assertThat(p.timeout())
                            .isEqualTo(java.time.Duration.ofSeconds(2));
                    assertThat(p.apiKey())
                            .isEqualTo("test-only-placeholder");
                });
    }
}
~~~

Test này minh họa việc bind typed properties. Nó không cần credential production và không gọi dịch vụ thanh toán bên ngoài.

Các kịch bản cần có trong hệ thống thực tế:

- Secret được cấp hợp lệ từ nguồn test, ứng dụng bind đúng.
- Secret bị thiếu/blank, ứng dụng từ chối startup hoặc tắt tính năng theo chính sách.
- Secret sai định dạng, validation hoặc cơ chế khởi tạo client xử lý rõ ràng.
- Log và exception không in giá trị secret.
- Test profile không vô tình sử dụng production endpoint.
- Khi rotate secret, ứng dụng nhận phiên bản mới theo cơ chế đã thiết kế.
- Nếu dùng ConfigTree/Kubernetes, file/volume được mount với quyền đọc phù hợp.

Không nên đưa secret thật vào test fixture chỉ để “đơn giản hóa CI”.

## 19. Các lỗi phổ biến và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Ứng dụng không kết nối được database ở production | `DB_PASSWORD` chưa được cấp hoặc sai | Kiểm tra secret injection và quyền đọc của workload; không in password |
| Local chạy được, CI thất bại | CI job thiếu secret hoặc test vô tình cần credential thật | Dùng test placeholder/mock hoặc secret riêng cho CI được phân quyền |
| Secret bị commit vào `application-prod.yml` | Nhầm profile với kho bí mật | Rotate secret, loại bỏ khỏi source/artifact và chuyển sang nguồn runtime |
| `@ConfigurationProperties` nhận `null` | Sai prefix, property name, đăng ký bean hoặc nguồn cấu hình chưa nạp | Kiểm tra binding và startup; không log giá trị nhạy cảm |
| Biến môi trường có tên giống property nhưng không bind | Sai quy tắc relaxed binding | Dùng canonical property name hoặc placeholder `${...}` rõ ràng |
| App dùng secret cũ sau khi secret manager đổi | Process/cache/connection pool chưa reload | Thiết kế rollout/refresh và xác nhận credential mới đã được áp dụng |
| Secret xuất hiện trong log Actuator | Endpoint/response/log không được bảo vệ đúng | Giảm exposure, cấu hình quyền truy cập, tránh ghi secret |
| Kubernetes Secret nhìn thấy dưới dạng Base64 | Nhầm Base64 với encryption | Kiểm tra RBAC, encryption at rest và quyền runtime |
| Docker image chứa credential | Secret được truyền ở build-time hoặc nằm trong file đóng gói | Tạo image trung tính, inject secret lúc deploy, rotate credential đã lộ |
| Secret mặc định yếu được dùng ngoài ý muốn | Placeholder có default không an toàn | Bỏ default bí mật, kiểm tra startup khi secret thiếu |

## 20. Hướng dẫn lựa chọn nguồn cung cấp

| Nhu cầu triển khai | Phương án thường phù hợp |
|---|---|
| Config đơn giản, không nhạy cảm, dùng chung nhiều môi trường | `application.yml` trong repository |
| Config khác nhau giữa dev/test/prod, không chứa credential | Profile-specific files hoặc externalized config |
| Secret cho local development | Cơ chế local secret được bảo vệ, shell/env hoặc file không commit; credential test riêng |
| Container đơn giản có secret injection | Environment variables được cấp lúc runtime bởi nền tảng |
| Container cần secret dạng file | Mounted secret file + `configtree` nếu phù hợp |
| Kubernetes workload | Secret tham chiếu bằng `secretKeyRef` hoặc secret volume, kết hợp RBAC/encryption |
| Hệ thống cần audit, rotation và least privilege nghiêm ngặt | Secret manager và workload identity |
| Secret cần xoay vòng không restart | Cơ chế runtime refresh/rotation được thiết kế và kiểm thử rõ, không chỉ đặt env var |
| Cấu hình test | Placeholder/fixture không có quyền thật |

Cách thiết kế tốt là để ứng dụng biết **tên property và kiểu dữ liệu cần thiết**, không biết bí mật thật được lưu ở đâu trong source code. Nền tảng triển khai chịu trách nhiệm cấp quyền và giá trị; Spring Boot Binder biến chúng thành cấu hình typed cho bean sử dụng.

## 21. Nguyên tắc ghi nhớ

1. **Không đồng nhất config với secret.** Timeout và page size thường là config; password, token, private key là secret.
2. **Không commit secret thật.** Kể cả file dành riêng cho production hoặc file bị thêm vào `.gitignore` sau khi đã lộ.
3. **Giữ cùng một artifact cho nhiều môi trường.** Cấp các giá trị khác nhau qua deployment/config sources.
4. **Biến môi trường chỉ là kênh truyền.** Nó không tự mã hóa hoặc che secret khỏi mọi đối tượng có quyền truy cập máy/process.
5. **Dùng secret manager hoặc mount có quyền hạn khi phù hợp.** Đánh giá RBAC, audit, encryption at rest, workload identity và rotation.
6. **Đừng có fallback yếu cho secret bắt buộc.** Kiểm tra trường hợp thiếu secret và chính sách fail-fast.
7. **Không làm lộ secret qua log, Actuator, lỗi, tracing hoặc build artifact.**
8. **Phân tách secret của dev, test và production.** Không cho môi trường kiểm thử truy cập credential production.
9. **Rotation cần thay cả nơi sử dụng.** Cập nhật secret store không tự làm Spring bean, environment hay connection pool đổi giá trị.
10. **Kiểm thử với giá trị giả.** Các test phải chứng minh việc bind và xử lý lỗi mà không cần secret thật.

Kết luận: `application.yml`, profiles và `@ConfigurationProperties` mô tả **ứng dụng cần giá trị gì và sử dụng nó như thế nào**. Secret thực tế nên được cấp từ môi trường triển khai qua một kênh bảo mật thích hợp, có quyền truy cập tối thiểu, không đi vào lịch sử Git và có quy trình xoay vòng. Phân tách đúng hai trách nhiệm này giúp ứng dụng Spring Boot dễ triển khai giữa các môi trường mà vẫn giảm nguy cơ lộ thông tin xác thực.
