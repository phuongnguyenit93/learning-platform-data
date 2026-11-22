# Cấp bí mật qua biến môi trường hoặc tệp được gắn vào tiến trình trong Spring Boot

## 1. Bài toán: cấu hình cần thay đổi, nhưng bí mật không được đóng gói theo ứng dụng

Một dịch vụ Spring Boot thường phải kết nối cơ sở dữ liệu, gửi request tới hệ thống đối tác hoặc ký thông điệp bằng khóa bí mật. Các giá trị cần cấp cho ứng dụng có thể là:

- Mật khẩu kết nối database.
- API token của dịch vụ bên ngoài.
- Client secret cho OAuth2.
- Chuỗi xác thực của message broker.
- Chứng chỉ và private key của TLS.
- Khóa mã hóa do hệ thống quản lý bí mật cấp.

Những giá trị này có cùng một yêu cầu: **ứng dụng phải truy cập được khi chạy, nhưng không nên chứa bí mật thật trong source code, file cấu hình đã commit, container image hoặc log**.

Ví dụ cần tránh:

~~~yaml
# KHÔNG làm như sau trong repository có chứa bí mật thực:
spring:
  datasource:
    url: jdbc:postgresql://db.example.test:5432/orders
    username: orders_user
    password: real-secret-in-source
~~~

Nếu file đi vào Git, build artifact, Docker image hoặc bản sao lưu, giá trị có thể bị phân tán rộng hơn dự kiến. Xóa dòng khỏi commit mới không tự xóa nó khỏi lịch sử Git, build cache hoặc bản lưu của người khác.

Một hướng an toàn hơn là để code và cấu hình thông thường chứa **tên khóa**, còn giá trị bí mật do môi trường chạy cung cấp.

Trong Spring Boot, hai cách phổ biến là:

1. **Biến môi trường (environment variables):** nền tảng chạy đưa một biến như `SPRING_DATASOURCE_PASSWORD` vào môi trường tiến trình. Spring Boot đọc nó thông qua `Environment`.
2. **Tệp được mount vào tiến trình (mounted secret files/volumes):** nền tảng cấp một tệp chỉ được phép đọc ở đường dẫn như `/run/secrets/db.password`. Spring Boot có thể nạp thư mục tệp thành thuộc tính bằng `spring.config.import=configtree:/run/secrets/` hoặc ứng dụng đọc tệp trực tiếp khi cần.

Cả hai cách đều giúp **tách bí mật khỏi code/image**. Nhưng **cả hai không tự làm bí mật trở thành tuyệt đối an toàn**. Quyền của tiến trình, cấu hình container, quyền đọc file, cách ghi log, nguồn secret, thời hạn và cơ chế xoay vòng vẫn quyết định mức bảo vệ thực tế.

## 2. Kiến thức nền: Externalized Configuration và Environment

Spring Boot hỗ trợ *externalized configuration*: cùng một artifact có thể sử dụng các giá trị cấu hình khác nhau khi triển khai vào các môi trường khác nhau.

Các nguồn thường gặp:

~~~text
application.properties / application.yaml
profile-specific Config Data
external Config Data
OS environment variables
Java System properties
command-line arguments
một số PropertySource do nền tảng hoặc thư viện thêm vào
~~~

Các nguồn được đưa vào hệ thống property resolution của Spring, thường gọi chung là `Environment` hoặc các `PropertySource` có thứ tự ưu tiên.

Ví dụ code:

~~~java
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class CredentialLookup {

    private final Environment environment;

    public CredentialLookup(Environment environment) {
        this.environment = environment;
    }

    public boolean hasDatabasePassword() {
        String value =
                environment.getProperty("spring.datasource.password");

        // Không ghi giá trị vào log.
        return value != null && !value.isBlank();
    }
}
~~~

Tên khóa mà ứng dụng cần là:

~~~text
spring.datasource.password
~~~

Nhưng giá trị có thể được cấp bởi biến môi trường:

~~~text
SPRING_DATASOURCE_PASSWORD
~~~

hoặc bởi một file trong configuration tree có tên:

~~~text
spring.datasource.password
~~~

Điểm quan trọng: code đọc **tên thuộc tính logic**, không nhất thiết biết dữ liệu bắt nguồn từ file nào.

### Luồng khái niệm

~~~text
             Nền tảng triển khai
                    |
        +-----------+-----------+
        |                       |
        v                       v
Biến môi trường OS       Secret volume mount
SPRING_DATASOURCE_       /run/secrets/
PASSWORD                spring.datasource.password
        |                       |
        |                spring.config.import
        |                    configtree:
        |                       |
        +-----------+-----------+
                    |
                    v
         Spring Environment
          PropertySources
                    |
                    v
      spring.datasource.password
                    |
                    v
     DataSource hoặc bean cấu hình
~~~

Spring Boot **không cung cấp hệ thống quản lý vòng đời secret đầy đủ chỉ nhờ Environment**. Nó nhận giá trị; vấn đề secret được tạo, cấp quyền, bảo quản, thu hồi, cập nhật và kiểm toán thuộc nền tảng triển khai và chính sách vận hành.

## 3. Secret không nên bị nhầm với cấu hình thường

Ví dụ cấu hình thường:

~~~yaml
spring:
  application:
    name: order-service
  datasource:
    url: jdbc:postgresql://db.internal:5432/orders
    username: orders_app

app:
  request-timeout: 15s
  retry-count: 3
~~~

Các thông số trên có thể được version control tùy chính sách hệ thống. Còn mật khẩu hay token nên được cấp độc lập:

~~~text
spring.datasource.password = <bí mật được cấp khi chạy>
~~~

Một file `application.yaml` có thể mô tả **cách nạp secret** mà không chứa **giá trị secret**. Ví dụ:

~~~yaml
spring:
  config:
    import: "optional:configtree:/run/secrets/"
~~~

Đây là cấu hình đường dẫn, không phải mật khẩu.

Tuy nhiên, ngay cả **đường dẫn secret**, tên đối tác hoặc tên key đôi khi cũng tiết lộ thông tin cấu trúc hạ tầng. Không log tràn lan toàn bộ cấu hình chỉ vì đã tách giá trị bí mật.

## 4. Phương án A: cấp secret bằng biến môi trường

Cách đơn giản: hệ điều hành/container runtime truyền biến môi trường vào tiến trình Spring Boot trước lúc ứng dụng khởi động.

Tên property canonical:

~~~text
spring.datasource.password
~~~

Tên biến môi trường tương ứng:

~~~text
SPRING_DATASOURCE_PASSWORD
~~~

Trong Spring Boot, các biến môi trường được xét như một nguồn cấu hình có hỗ trợ quy tắc đặt tên tương ứng, nên dữ liệu ở biến này có thể dùng cho `spring.datasource.password`.

Nếu bạn đã cấu hình URL và username trong `application.yaml`:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://db.internal:5432/orders
    username: orders_app
    # Không chứa password thật
~~~

thì password có thể đến từ `SPRING_DATASOURCE_PASSWORD` mà không cần khai báo lại trong YAML.

### 4.1. Cơ chế đọc của Spring Boot

Khi ứng dụng khởi động:

1. Runtime tạo tiến trình với tập biến môi trường đã cấp.
2. Spring Boot xây dựng `Environment` với system environment property source.
3. Cơ chế kết nối database đọc `spring.datasource.password` từ các nguồn phù hợp.
4. Giá trị từ biến môi trường có thể được dùng mà không có một dòng mật khẩu literal trong `application.yaml`.

Một service cũng có thể đọc qua `Environment` hoặc `@ConfigurationProperties`:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "partner.auth")
public record PartnerAuthProperties(
        String clientId,
        String clientSecret) {
}
~~~

Tương ứng với tên canonical:

~~~text
partner.auth.client-id
partner.auth.client-secret
~~~

Nếu dùng biến môi trường theo quy tắc canonical:

~~~text
PARTNER_AUTH_CLIENTID
PARTNER_AUTH_CLIENTSECRET
~~~

Trong Java, class record dùng tên `clientId` và `clientSecret`. Đây là kết quả của relaxed binding; không cần đổi field Java sang chữ hoa gạch dưới.

Đăng ký class với `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties(PartnerAuthProperties.class)` nếu muốn inject bean vào service.

### 4.2. Quy tắc đổi tên biến môi trường

Theo quy tắc Spring Boot dành cho binding từ OS environment:

1. Dấu chấm `.` trong tên canonical → `_`.
2. Dấu gạch ngang `-` → bỏ đi.
3. Chuyển thành chữ hoa.

Ví dụ:

| Tên thuộc tính canonical | Biến môi trường |
| --- | --- |
| `spring.datasource.password` | `SPRING_DATASOURCE_PASSWORD` |
| `partner.auth.client-secret` | `PARTNER_AUTH_CLIENTSECRET` |
| `mail.smtp.api-key` | `MAIL_SMTP_APIKEY` |
| `app.payment.signing-key` | `APP_PAYMENT_SIGNINGKEY` |
| `security.jwt.private-key` | `SECURITY_JWT_PRIVATEKEY` |

Đừng tự suy luận rằng mọi dấu gạch ngang có thể đổi thành gạch dưới tùy ý. Ví dụ `partner.auth.client-secret` có tên biến chuẩn `PARTNER_AUTH_CLIENTSECRET` theo quy tắc trên, không phải mặc nhiên `PARTNER_AUTH_CLIENT_SECRET`.

### 4.3. Minh họa local trên shell kiểu Unix

Với dữ liệu thử nghiệm vô hại, có thể chạy:

~~~bash
export SPRING_DATASOURCE_PASSWORD='DEMO_ONLY_NOT_A_REAL_PASSWORD'
java -jar order-service.jar
unset SPRING_DATASOURCE_PASSWORD
~~~

**Đây chỉ là minh họa cú pháp.** Với bí mật thật, không nên gõ trực tiếp giá trị vào dòng lệnh được lưu trong shell history, tập lệnh version control hoặc log CI/CD.

Nếu phải nhập tương tác trong một môi trường thử nghiệm do bạn kiểm soát, có thể đọc mà không hiển thị ký tự:

~~~bash
read -r -s -p "Database password: " SPRING_DATASOURCE_PASSWORD
printf '\n'
export SPRING_DATASOURCE_PASSWORD
java -jar order-service.jar
unset SPRING_DATASOURCE_PASSWORD
~~~

Điều này chỉ tránh hiển thị mật khẩu khi nhập; nó **không bảo đảm bí mật không xuất hiện trong memory, môi trường tiến trình con, snapshot hoặc công cụ chẩn đoán khác**. Trong production, nên để secret manager, orchestrator hoặc pipeline có cơ chế secret masking phù hợp cấp biến cho tiến trình.

### 4.4. Windows và môi trường phát triển

Trên Windows PowerShell, một tiến trình con có thể nhận biến môi trường được cấp qua `$env:SPRING_DATASOURCE_PASSWORD`. Tuy nhiên, thiết lập một literal bí mật thật trong terminal hoặc lệnh script cũng có rủi ro bị lưu lại.

Trong IDE, trường “Environment variables” thường được dùng để cấp cấu hình khi chạy local. Không commit run configuration chứa secret, không chia sẻ ảnh chụp màn hình có hiển thị giá trị và không đưa secret vào video demo.

Cú pháp và cách lưu biến khác nhau giữa PowerShell, Bash, Docker hoặc CI; nguyên tắc chung vẫn là **chỉ cấp ở runtime và tránh đưa giá trị thật vào tài liệu công khai**.

## 5. Ưu điểm và giới hạn của biến môi trường

### Ưu điểm

- Rất phổ biến: hầu hết hệ điều hành, orchestrator và CI hỗ trợ.
- Không cần thay đổi artifact ứng dụng khi triển khai sang môi trường khác.
- Spring Boot có thể tự nhận các tên property tương ứng.
- Thuận tiện với một số lượng nhỏ giá trị dạng text.
- Dễ tích hợp với cơ chế cấp secret từ Kubernetes, container runtime hoặc nền tảng PaaS.

### Giới hạn

- Biến môi trường **không phải vùng chứa bí mật được mã hóa** trong chính tiến trình.
- Các công cụ chẩn đoán, crash report, process inspection hoặc log cấu hình không đúng có thể làm lộ giá trị.
- Một tiến trình con có thể kế thừa biến môi trường nếu không kiểm soát.
- Người có quyền truy cập thích hợp vào container/host/runtime có thể đọc environment.
- Khó sử dụng cho dữ liệu nhị phân dài hoặc private key đa dòng.
- Thay đổi secret trong hệ thống quản lý chưa chắc cập nhật environment của **tiến trình đang chạy**; thường cần tạo lại/restart tiến trình.
- Một số công cụ triển khai có thể hiển thị environment trong metadata hoặc màn hình quản trị nếu cấu hình phân quyền không tốt.

**Kết luận:** environment variables dễ vận hành, nhưng không nên coi chúng an toàn tuyệt đối chỉ vì không nằm trong `application.yaml`.

### Tránh truyền secret bằng command-line arguments

Ví dụ cần tránh với bí mật thật:

~~~bash
java -jar app.jar --spring.datasource.password=REAL_SECRET
~~~

Tham số tiến trình có thể xuất hiện trong process list, nhật ký launcher, script hoặc hệ thống giám sát. Trong Spring Boot, CLI cũng là một property source, nhưng một nguồn có thể hoạt động kỹ thuật **không đồng nghĩa** phù hợp bảo mật để chứa password/token.

Cũng nên thận trọng khi dùng:

~~~bash
java -Dspring.datasource.password=REAL_SECRET -jar app.jar
~~~

Java System properties có thể bị hiển thị bởi công cụ chẩn đoán hoặc JVM management. Đối với bí mật thật, ưu tiên kênh cấp bí mật của runtime.

## 6. Phương án B: mount tệp secret vào container/tiến trình

Nhiều nền tảng cho phép cấp một secret dưới dạng file thay vì biến môi trường.

Ví dụ cấu trúc trong container:

~~~text
/run/secrets/
├── spring.datasource.password
├── partner.auth.client-secret
└── mail.smtp.api-key
~~~

Mỗi file chứa **giá trị** của một thuộc tính. Tên file trở thành **tên khóa** khi Spring Boot nạp thư mục này dưới dạng *configuration tree*.

Ví dụ về quan hệ, không hiển thị nội dung thật:

~~~text
/run/secrets/spring.datasource.password
        |
        +-- tên file -> spring.datasource.password
        +-- nội dung -> giá trị password bí mật
~~~

Vì file nằm ngoài JAR và thường do container runtime/orchestrator mount khi triển khai, artifact ứng dụng không cần chứa các giá trị đó.

### 6.1. Tên file và directory là một phần của khóa

Spring Boot cho phép file name dùng dấu chấm.

~~~text
/run/secrets/
    db.password
~~~

khi được import đúng cách sẽ tạo property:

~~~text
db.password
~~~

Cấu trúc thư mục lồng nhau cũng hợp lệ:

~~~text
/etc/config/
└── myapp/
    ├── username
    └── password
~~~

Import `configtree:/etc/config/` sẽ cung cấp:

~~~text
myapp.username
myapp.password
~~~

Còn import `configtree:/etc/config/myapp/` sẽ cung cấp:

~~~text
username
password
~~~

Do vậy, cần **kiểm tra root directory được import**; không nên coi tên khóa mặc nhiên giống nhau trong cả hai cách.

## 7. spring.config.import=configtree: là cơ chế gì?

Khi một directory chứa **nhiều tệp, mỗi tệp là một key-value**, Spring Boot dùng prefix vị trí `configtree:` để biết rằng cần nạp chúng như một tập thuộc tính.

Ví dụ `application.properties`:

~~~properties
spring.config.import=optional:configtree:/run/secrets/
~~~

Hoặc `application.yaml`:

~~~yaml
spring:
  config:
    import: "optional:configtree:/run/secrets/"
~~~

Khi Spring Boot khởi động, nó xét thư mục tương ứng, đưa nội dung các file thành thuộc tính và cho phép truy xuất qua `Environment`, `@Value`, `@ConfigurationProperties` hoặc các cơ chế Spring Boot liên quan.

### 7.1. configtree: khác file:

Nếu đường dẫn là **một tệp YAML hoàn chỉnh**:

~~~text
/etc/secrets/credentials.yaml
~~~

thì một ví dụ import có thể là:

~~~properties
spring.config.import=file:/etc/secrets/credentials.yaml
~~~

Nếu đường dẫn là **một thư mục mỗi file một secret**:

~~~text
/run/secrets/db.password
/run/secrets/partner.auth.client-secret
~~~

thì dùng:

~~~properties
spring.config.import=configtree:/run/secrets/
~~~

**Không dùng `configtree:` để giả định nội dung một file YAML được parse thành nhiều field.** Configuration tree nạp key từ tên đường dẫn và value từ nội dung file, còn import YAML nạp cấu trúc cú pháp YAML.

### 7.2. optional: không có nghĩa secret là tùy chọn về nghiệp vụ

~~~properties
spring.config.import=optional:configtree:/run/secrets/
~~~

`optional:` cho phép ứng dụng tiếp tục qua bước nạp Config Data nếu vị trí được chỉ định không tồn tại. Nhưng một hệ thống production vẫn có thể **bắt buộc** phải có password hoặc token.

Ví dụ với ứng dụng triển khai nhiều môi trường:

- Local: không mount `/run/secrets/`, có thể dùng một hệ thống database thử nghiệm được cấu hình riêng.
- Production: mount `/run/secrets/` và yêu cầu `db.password` có giá trị.

Nếu secret thật sự bắt buộc để chức năng chính chạy, bạn có thể:

- Bỏ `optional:` ở cấu hình môi trường đó để phát hiện sớm directory thiếu.
- Dùng `@Validated` / `@NotBlank` hoặc kiểm tra rõ ràng để phát hiện **file/key rỗng hoặc thiếu**.
- Cấu hình platform không cho workload khởi chạy nếu Secret bắt buộc không có.

**Có thư mục không đồng nghĩa có đúng file/key.** Một thư mục rỗng hoặc file sai tên có thể khiến import không tạo thuộc tính cần dùng, ngay cả khi directory tồn tại.

### 7.3. Nếu import nằm trong file nào?

`spring.config.import` được xử lý trong giai đoạn nạp Config Data. Có thể đặt nó trong `application.yaml` đóng gói sẵn hoặc tại một tệp cấu hình ngoài JAR. Đường dẫn bắt đầu bằng `configtree:` và đường dẫn tuyệt đối được xử lý theo cơ chế location của Spring Boot.

Với container Linux, sử dụng đường dẫn tuyệt đối như `/run/secrets/` hoặc `/etc/secrets/` thường dễ xác định hơn đường dẫn tương đối chịu ảnh hưởng working directory.

## 8. Ví dụ đầy đủ: cấp database password từ mounted file

Giả sử ứng dụng có `application.yaml`:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://db.internal:5432/orders
    username: orders_app
  config:
    import: "configtree:/run/secrets/"
~~~

Trên runtime, có file:

~~~text
/run/secrets/spring.datasource.password
~~~

Nội dung file là mật khẩu do nền tảng cấp, **không nằm trong image hoặc Git repository**.

Khi ứng dụng khởi động, configuration tree tạo property:

~~~text
spring.datasource.password
~~~

Spring Boot DataSource configuration có thể sử dụng nó như một property bình thường.

### 8.1. Lợi ích của việc khớp tên file với property

Không cần viết code:

~~~java
Files.readString(
        Path.of("/run/secrets/spring.datasource.password"));
~~~

chỉ để truyền password vào DataSource. Spring Boot đã có cơ chế nhận giá trị qua `Environment`.

Bản thân đường dẫn file có thể thay đổi nếu platform khác nhau; ứng dụng chỉ cần khai báo chính xác thư mục import và giữ ổn định tên khóa logic.

### 8.2. Nếu file chỉ tên password

Giả sử directory:

~~~text
/run/secrets/
└── password
~~~

Với import root `configtree:/run/secrets/`, key logic là `password`, **không tự biến thành `spring.datasource.password`**.

Có hai hướng:

1. Đổi tên file trong mount thành `spring.datasource.password`.
2. Giữ key `password` và khai báo một property alias tham chiếu:

~~~yaml
spring:
  config:
    import: "configtree:/run/secrets/"
  datasource:
    password: "${password}"
~~~

Nếu key `password` có trong Environment, placeholder có thể được phân giải. Tuy nhiên, tên `password` quá chung dễ xung đột; trong hệ thống có nhiều secret, nên dùng namespace rõ ràng.

### 8.3. Một alias rõ ràng hơn

Mount:

~~~text
/run/secrets/db.password
~~~

Khai báo:

~~~yaml
spring:
  config:
    import: "configtree:/run/secrets/"
  datasource:
    url: jdbc:postgresql://db.internal:5432/orders
    username: orders_app
    password: "${db.password}"
~~~

Ở đây:

- File `db.password` tạo property `db.password`.
- `spring.datasource.password` tham chiếu giá trị đó.
- Không có literal secret trong YAML.

Đây là cách phù hợp khi muốn giữ tên file nhất quán với các secret được một nền tảng quản lý, nhưng framework hoặc thư viện yêu cầu tên property khác.

## 9. Ví dụ với @ConfigurationProperties và xác thực cấu hình

Nếu một module ứng dụng dùng credentials riêng, có thể định nghĩa:

~~~java
package com.example.demo.config;

import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "partner.auth")
public record PartnerCredentials(

        @NotBlank String clientId,

        @NotBlank String clientSecret) {
}
~~~

Đăng ký:

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

Trong một môi trường cấp secret bằng environment:

~~~text
PARTNER_AUTH_CLIENTID    = <giá trị được platform cấp>
PARTNER_AUTH_CLIENTSECRET = <giá trị được platform cấp>
~~~

Trong môi trường khác, có thể mount:

~~~text
/run/secrets/partner.auth.client-id
/run/secrets/partner.auth.client-secret
~~~

và nạp bằng:

~~~yaml
spring:
  config:
    import: "optional:configtree:/run/secrets/"
~~~

Trong cả hai trường hợp, service có thể nhận cùng một bean:

~~~java
package com.example.demo.service;

import com.example.demo.config.PartnerCredentials;
import org.springframework.stereotype.Service;

@Service
public class PartnerService {

    private final PartnerCredentials credentials;

    public PartnerService(PartnerCredentials credentials) {
        this.credentials = credentials;
    }

    public boolean hasCredentials() {
        return !credentials.clientId().isBlank()
                && !credentials.clientSecret().isBlank();
    }
}
~~~

**Không log toàn bộ record `PartnerCredentials`.** Java record tự sinh `toString()`, có thể in ra giá trị của tất cả thành viên, bao gồm `clientSecret`. Nếu cần thông báo trạng thái, chỉ xuất tên property hoặc Boolean đã che giá trị.

### Vì sao @NotBlank quan trọng?

Nạp được directory chưa chứng minh từng file có nội dung. Một file rỗng hoặc key bị đặt sai tên có thể dẫn tới String thiếu/rỗng.

`@NotBlank` giúp phát hiện thiếu dữ liệu cần thiết khi bean được bind và validation được bật. Dự án cần Jakarta Bean Validation provider, thường qua `spring-boot-starter-validation`, để constraint được thực thi.

Một ứng dụng production không nên lặng lẽ chuyển sang credential mặc định công khai khi dữ liệu bí mật bị thiếu.

## 10. Docker Compose Secrets: mount file, không cần môi trường chứa giá trị

Docker Compose hỗ trợ khai báo secret ở cấp top-level và chỉ cấp cho service được liệt kê. Trong môi trường Linux container, secret được mount thành file trong `/run/secrets/`.

Ví dụ Compose:

~~~yaml
services:
  order-service:
    image: example/order-service:1.0.0
    environment:
      SPRING_CONFIG_IMPORT: "configtree:/run/secrets/"
      PARTNER_AUTH_CLIENTID: "DEMO_CLIENT_ID"
    secrets:
      - source: partner_client_secret
        target: partner.auth.client-secret

secrets:
  partner_client_secret:
    file: ./secrets/partner-client-secret.txt
~~~

Trong container:

~~~text
/run/secrets/partner.auth.client-secret
~~~

Spring Boot đọc file thành thuộc tính:

~~~text
partner.auth.client-secret
~~~

và có thể kết hợp với:

~~~text
PARTNER_AUTH_CLIENTID
~~~

để bind `PartnerCredentials`.

### Đường dẫn trong Compose

- `secrets.partner_client_secret.file` là file nguồn mà Compose sử dụng khi triển khai.
- `services.order-service.secrets` cấp quyền truy cập secret cho riêng service.
- `target` quyết định tên file được mount trong container.
- `SPRING_CONFIG_IMPORT` nói cho Spring Boot nơi nạp configuration tree.

Giá trị thực tế không xuất hiện trong Compose YAML của ví dụ; nó nằm trong nguồn secret file và phải được bảo vệ bởi quyền file, thư mục, chính sách CI và quản lý secret.

### Cảnh báo về file nguồn

Nếu sử dụng:

~~~yaml
file: ./secrets/partner-client-secret.txt
~~~

đừng commit file này vào repository. Đường dẫn relative trên máy phát triển không phải một kho bí mật an toàn mặc định. Với production, ưu tiên nguồn secret được nền tảng quản lý, kiểm soát quyền và có quy trình cấp/thu hồi.

### _FILE là quy ước, không phải khả năng phổ quát

Một số Docker Official Images hỗ trợ biến như:

~~~text
MYSQL_PASSWORD_FILE=/run/secrets/db_password
~~~

Đó là **quy ước của image/entrypoint cụ thể**. Không nên suy ra Spring Boot tự đọc mọi biến có hậu tố `_FILE` rồi chuyển file tương ứng thành thuộc tính.

Ví dụ:

~~~text
SPRING_DATASOURCE_PASSWORD_FILE=/run/secrets/db_password
~~~

không tự được Spring Boot diễn giải như một lệnh “đọc file và dùng nội dung làm password” chỉ vì tên có `_FILE`.

Nếu muốn dùng file trong Spring Boot, hãy dùng `configtree:` với tên file/property phù hợp, hoặc viết logic đọc file có chủ đích và bảo đảm kiểm soát quyền.

## 11. Kubernetes: cấp secret qua biến môi trường

Kubernetes có đối tượng `Secret` và cơ chế `secretKeyRef` để cung cấp một key vào environment của container.

Ví dụ Pod fragment minh họa:

~~~yaml
apiVersion: v1
kind: Pod
metadata:
  name: order-service
spec:
  containers:
    - name: app
      image: example/order-service:1.0.0
      env:
        - name: SPRING_DATASOURCE_PASSWORD
          valueFrom:
            secretKeyRef:
              name: order-db-credentials
              key: password
~~~

Ở đây:

1. Kubernetes tìm đối tượng Secret tên `order-db-credentials` trong namespace phù hợp.
2. Lấy key `password` của Secret.
3. Cấp nội dung như biến môi trường `SPRING_DATASOURCE_PASSWORD` cho container.
4. Spring Boot đọc property `spring.datasource.password` từ environment.

Giá trị bí mật **không được ghi literal vào Pod spec**.

### Secret phải được chuẩn bị trước

Kubernetes cần đối tượng Secret tồn tại và có key phù hợp, trừ khi tài nguyên được đánh dấu tùy chọn theo cơ chế tương ứng. Với Secret bắt buộc bị thiếu, Pod có thể không khởi chạy được; sự cố sẽ được báo trong trạng thái hoặc event của Pod.

**Không đưa một Secret manifest có giá trị thật vào Git.** Kubernetes `stringData` và `data` (base64) đều có rủi ro nếu file được chia sẻ; **base64 chỉ mã hóa biểu diễn, không phải encryption**. Một secret manager/external-secrets workflow hoặc kênh provisioning bảo mật là lựa chọn phù hợp hơn cho giá trị production.

### Quy tắc tên biến trong container

Kubernetes có giới hạn về tên biến môi trường được cấp cho container. Nếu key của Secret chứa dấu chấm hoặc ký tự không hợp lệ với môi trường triển khai, bạn có thể chọn một tên biến hợp lệ trong `env.name` và tham chiếu key thực tế ở `secretKeyRef.key`.

Ví dụ key của Secret có thể tên `spring.datasource.password`, còn environment name nên dùng `SPRING_DATASOURCE_PASSWORD`.

## 12. Kubernetes: mount Secret thành volume file

Kubernetes cũng có thể mount Secret thành volume. Ví dụ Pod fragment:

~~~yaml
apiVersion: v1
kind: Pod
metadata:
  name: order-service
spec:
  containers:
    - name: app
      image: example/order-service:1.0.0
      env:
        - name: SPRING_CONFIG_IMPORT
          value: "configtree:/etc/secrets/"
      volumeMounts:
        - name: db-credentials
          mountPath: /etc/secrets
          readOnly: true
  volumes:
    - name: db-credentials
      secret:
        secretName: order-db-credentials
        items:
          - key: password
            path: spring.datasource.password
        defaultMode: 0400
~~~

Kết quả mong đợi trong container:

~~~text
/etc/secrets/spring.datasource.password
~~~

Và Spring Boot import directory:

~~~text
configtree:/etc/secrets/
~~~

để có property:

~~~text
spring.datasource.password
~~~

### Các thành phần cần hiểu

- `volumes[].secret.secretName` chọn Secret nguồn.
- `items[].key` chọn key trong Kubernetes Secret.
- `items[].path` đặt tên đường dẫn của file được tạo trong mount.
- `volumeMounts[].mountPath` xác định vị trí mount trong container.
- `volumeMounts[].readOnly` thể hiện ý định chỉ đọc từ ứng dụng.
- `defaultMode: 0400` đặt quyền file theo POSIX trong môi trường tương thích (chỉ owner đọc).

### Chú ý về quyền 0400

Một file có quyền `0400` chỉ có owner được đọc, nhưng **owner thực tế và user mà container chạy dưới quyền đó phải tương thích**. Nếu workload chạy non-root mà secret file không được cấp ownership hoặc quyền nhóm thích hợp, ứng dụng có thể gặp `AccessDeniedException` dù file được mount.

Phải thiết kế `runAsUser`, `runAsGroup`, `fsGroup` hoặc cơ chế quyền tương ứng theo môi trường thật. Không nên mở quyền toàn bộ bí mật thành `0777` chỉ để “chữa lỗi” đọc file.

Cách cấu hình quyền chính xác có thể thay đổi tùy runtime, driver và loại volume. Cần xác minh trên cluster thực tế với nguyên tắc ít quyền nhất.

## 13. Kubernetes Secret không tự bảo đảm mã hóa và phân quyền đầy đủ

Đối tượng Kubernetes `Secret` là cơ chế tích hợp với workload, nhưng không mặc nhiên giải quyết mọi vấn đề bảo mật.

Những điều cần triển khai ở cấp cluster/platform:

- **Encryption at rest** cho dữ liệu Secret trong datastore của control plane khi cần.
- **RBAC theo nguyên tắc least privilege** để chỉ những danh tính cần thiết có quyền đọc Secret.
- Hạn chế quyền tạo Pod/Deployment hoặc chạy container debug ở namespace có secret nhạy cảm.
- Không tự ý dump Secret bằng `kubectl get secret -o yaml` vào log, ticket hoặc terminal được ghi hình.
- Cân nhắc external secret store/CSI driver khi hạ tầng có yêu cầu quản lý vòng đời tập trung.
- Giảm số service nhận cùng một Secret; chia nhỏ theo phạm vi chức năng.
- Gắn lịch rotation, audit và quy trình revoke.

**Base64 không phải mã hóa bảo mật.** Giá trị ở trường `data` của Kubernetes Secret có thể được giải mã bởi người có quyền truy cập object. Bảo vệ chính nằm ở quyền truy cập, mã hóa khi lưu/truyền, quản lý khóa và kiểm soát vận hành.

## 14. Configuration tree: file name là key, file content là value

Tính năng `configtree:` có những chi tiết kỹ thuật cần nhớ.

### 14.1. Tên file có dấu chấm

~~~text
/etc/config/
└── service.auth.client-secret
~~~

Import:

~~~properties
spring.config.import=optional:configtree:/etc/config/
~~~

tạo property:

~~~text
service.auth.client-secret
~~~

### 14.2. Thư mục lồng nhau

~~~text
/etc/config/
└── service/
    └── auth/
        └── client-secret
~~~

Import `configtree:/etc/config/` cũng có thể tạo đường dẫn property logic:

~~~text
service.auth.client-secret
~~~

### 14.3. Thay root import thay đổi key

Nếu bạn import:

~~~properties
spring.config.import=configtree:/etc/config/service/
~~~

thì file trong nhánh:

~~~text
auth/client-secret
~~~

trở thành tên logic:

~~~text
auth.client-secret
~~~

không phải `service.auth.client-secret`. Cần chọn root import nhất quán với tên khóa mà application muốn đọc.

### 14.4. Nhiều cây cấu hình và wildcard

Giả sử:

~~~text
/etc/config/
├── database/
│   └── db/
│       └── password
└── messaging/
    └── mq/
        └── password
~~~

Spring Boot hỗ trợ cú pháp wildcard ở mức thư mục con ngay dưới một parent:

~~~properties
spring.config.import=optional:configtree:/etc/config/*/
~~~

Các khóa có thể là:

~~~text
db.password
mq.password
~~~

Các directory wildcard được xét theo thứ tự tên; nếu cần thứ tự ưu tiên rõ ràng, liệt kê từng vị trí import. Tránh đặt nhiều bí mật cùng tên khóa trong nhiều tree mà không quyết định nguồn nào được ưu tiên.

### 14.5. Chuỗi và byte[]

Configuration tree có thể được bind thành `String` hoặc `byte[]` theo kiểu đích và khả năng conversion của Spring Boot. Điều này hữu ích với dữ liệu không chỉ là text đơn giản.

Tuy vậy, đừng coi việc có thể bind `byte[]` đồng nghĩa mọi trường hợp certificate/private key đều nên được xử lý thành String. Với khóa nhị phân hoặc certificate, cần chọn API và định dạng an toàn cho thư viện tiêu thụ, kiểm tra encoding và hạn chế bản sao dữ liệu nhạy cảm trong bộ nhớ.

## 15. Import YAML hoàn chỉnh so với nhiều file secret

Nền tảng có thể mount **một file chứa nhiều thuộc tính**:

~~~text
/etc/secrets/secure-config.yaml
~~~

Ví dụ file theo cú pháp YAML:

~~~yaml
partner:
  auth:
    client-id: DEMO_ID_ONLY
    client-secret: DEMO_SECRET_ONLY
~~~

Nếu nguồn file YAML nằm ngoài artifact và được mount có quyền phù hợp, có thể import như config data:

~~~properties
spring.config.import=file:/etc/secrets/secure-config.yaml
~~~

Còn nếu file không có extension:

~~~text
/etc/secrets/secure-config
~~~

có thể cung cấp extension hint:

~~~properties
spring.config.import=file:/etc/secrets/secure-config[.yaml]
~~~

Spring Boot hiểu rằng file không extension đó mang cú pháp YAML.

### So sánh

| Trường hợp | Định dạng | Cách import |
| --- | --- | --- |
| Một file YAML chứa nhiều khóa | Cấu trúc YAML | `file:/etc/secrets/secure-config.yaml` |
| Một file extensionless chứa YAML | YAML, nhưng không có đuôi | `file:/etc/secrets/secure-config[.yaml]` |
| Một directory với mỗi file là một giá trị | Configuration tree | `configtree:/run/secrets/` |
| Giá trị trực tiếp trong môi trường tiến trình | Biến môi trường OS | Không cần `spring.config.import` |

Không dùng `configtree:` chỉ vì “file có chứa bí mật”. Chọn cách nạp phù hợp với **cách nền tảng trình bày dữ liệu**.

## 16. Thứ tự ưu tiên: secret có thể bị nguồn khác ghi đè

Spring Boot hợp nhất các giá trị cấu hình theo thứ tự `PropertySource`. Trong cấu hình thông thường, các biến môi trường có ưu tiên hơn Config Data được nạp từ `application.yaml` hoặc `configtree:`; command-line properties có thể ưu tiên cao hơn environment.

Ví dụ:

~~~text
Config tree:
    /run/secrets/spring.datasource.password
    -> property: spring.datasource.password

Environment:
    SPRING_DATASOURCE_PASSWORD=another-value
~~~

Trong cách sắp xếp property source mặc định, biến môi trường có thể là giá trị cuối được dùng thay vì nội dung mounted file.

Đây là điểm **rất quan trọng khi xử lý secret**:

- Nguồn tồn tại không có nghĩa nguồn đó được sử dụng.
- Mount file đúng không chứng minh DataSource đã lấy password từ file đó.
- Một biến môi trường cũ còn tồn tại có thể làm ứng dụng tiếp tục dùng credential cũ.
- Một tham số CLI vô tình chứa cùng khóa có thể ghi đè cả hai.

### Không tự thiết kế “nguồn nào an toàn hơn thì tự thắng”

Spring Boot không thay đổi thứ tự ưu tiên chỉ vì một giá trị được coi là secret. Nguồn nào thắng phụ thuộc vào cơ chế cấu hình và thứ tự thực tế.

Khi vận hành production:

1. Chọn **một kênh cấp secret chủ đạo** cho từng khóa.
2. Tránh để cùng credential tồn tại đồng thời trong nhiều nguồn.
3. Nếu có chuyển đổi env → mounted file, xóa cấu hình env cũ khi đã triển khai an toàn.
4. Kiểm tra nguồn có hiệu lực **mà không in giá trị**.
5. Có kiểm thử khởi động với đúng kênh mà production sử dụng.

### Placeholder cũng dùng giá trị có hiệu lực

Ví dụ:

~~~yaml
spring:
  datasource:
    password: "${db.password}"
~~~

Nếu `db.password` xuất hiện trong nhiều `PropertySource`, placeholder sử dụng giá trị mà `Environment` tìm được theo cơ chế ưu tiên. Vì vậy tránh tạo cùng key ở nhiều nguồn mà không hiểu giá trị nào thắng.

## 17. Cách xác minh secret đã được cấp mà không in bí mật

Một health/startup check có thể chỉ trả lời **secret có mặt hay không**, thay vì xuất nội dung.

Ví dụ:

~~~java
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class SecretAvailability {

    private final Environment environment;

    public SecretAvailability(Environment environment) {
        this.environment = environment;
    }

    public boolean hasPartnerSecret() {
        String secret =
                environment.getProperty("partner.auth.client-secret");

        return secret != null && !secret.isBlank();
    }
}
~~~

**Không** làm:

~~~java
System.out.println(
        environment.getProperty("partner.auth.client-secret"));
~~~

Và không viết:

~~~java
log.info("Partner config: {}", credentials);
~~~

nếu `credentials` là record/POJO có `toString()` trả cả client secret.

Một cơ chế quan sát tốt có thể thông báo:

~~~text
partner.auth.client-secret: configured
~~~

mà không có bản sao của giá trị.

### Kiểm tra thư mục mount

Khi cần xác minh ở runtime, nên kiểm tra:

- Directory có tồn tại?
- Tên các file có đúng không?
- Tiến trình có quyền đọc không?
- Có nhầm mount path không?
- File có kích thước không bằng 0?
- Đường dẫn và `spring.config.import` có khớp không?

Tránh sử dụng các lệnh như `cat /run/secrets/...` để hiển thị nội dung thật trên terminal/ticket/chat. Với lỗi quyền, xem owner/mode hoặc thử khả năng đọc mà không in ra byte bí mật.

## 18. Quyền file và nguyên tắc least privilege

Mounted secret file vẫn là file. Nếu nhiều process hoặc user có quyền đọc nó, bí mật có thể bị lộ.

Trong container Linux, các yếu tố cần xác định:

1. Người dùng chạy JVM là ai?
2. File secret thuộc owner/group nào?
3. File mode là gì?
4. Directory cha có quyền traverse `x` phù hợp không?
5. Container có mount secret ở chế độ chỉ đọc không?
6. Có process khác trong container/Pod có thể đọc cùng mount không?
7. Container có quyền nâng cấp hoặc truy cập host filesystem quá rộng không?

Một file `0400` có thể phù hợp nếu JVM chạy đúng owner. Nếu JVM chạy non-root khác owner, `0400` có thể khiến ứng dụng không đọc được.

Không giải quyết bằng cách cấp toàn bộ `0777`. Thay vào đó, điều chỉnh identity, ownership, group hoặc cơ chế phân quyền của nền tảng theo nguyên tắc ít quyền nhất.

### Phân quyền ở cấp nền tảng

Tại Kubernetes, quyền đọc Secret object qua API và quyền đọc file mount trong Pod là **hai lớp khác nhau**:

- Kubernetes RBAC quyết định principal nào đọc Secret object hoặc quản lý workload.
- Quyền file và isolation của container quyết định tiến trình nào đọc file đã mount.

Cần bảo vệ cả hai lớp, không chỉ cấu hình một trong hai.

## 19. Cập nhật/rotation secret: điều gì tự đổi, điều gì không?

Secret thường có vòng đời:

~~~text
tạo -> cấp -> sử dụng -> đổi/rotation -> thu hồi
~~~

Tuy nhiên, việc nền tảng cập nhật secret **không đồng nghĩa JVM hoặc mọi Spring bean đang chạy tự nhận giá trị mới**.

### 19.1. Nếu secret được cấp qua biến môi trường

Environment variable được cấp khi tiến trình/container khởi động. Nếu Secret trong hệ thống quản lý thay đổi, môi trường của tiến trình đang chạy thường **không tự đổi**.

Trong Kubernetes, khi secret được dùng qua `secretKeyRef` làm environment variable, tiến trình thường phải được khởi chạy lại/recreated để nhận giá trị mới.

### 19.2. Nếu secret được cấp qua mounted file

Kubernetes có thể cập nhật dữ liệu secret volume một cách *eventually consistent* khi Secret object thay đổi. Có thể có độ trễ do chu kỳ đồng bộ và cache.

**Ngoại lệ quan trọng:** Secret volume mount qua `subPath` không tự nhận các cập nhật theo cơ chế này.

Nhưng ngay cả khi **nội dung file đã đổi**, Spring Boot thường nạp `spring.config.import` trong giai đoạn Config Data ở lúc khởi động. Một bean `@ConfigurationProperties`, DataSource hoặc HTTP client đã được tạo **không tự được bảo đảm rebind/recreate** vì file mount đổi.

### 19.3. Rotation an toàn cần phối hợp nhiều tầng

Một quy trình có thể gồm:

1. Nền tảng tạo secret mới và cập nhật/đổi bản cấp.
2. Bảo đảm file mount hoặc environment của workload mới nhận giá trị đúng.
3. Restart/rolling deployment hoặc kích hoạt một cơ chế reload được thiết kế, kiểm thử và hỗ trợ.
4. Cập nhật/recreate connection pool hoặc client nếu credentials đã được cache.
5. Xác minh kết nối bằng tiêu chí thành công/thất bại, **không log giá trị secret**.
6. Thu hồi secret cũ sau khi xác nhận các workload đã chuyển đổi.

Một ứng dụng có khả năng refresh động cần kiểm soát race condition giữa secret cũ và mới, thứ tự triển khai và khả năng rollback. Không nên chỉ nhìn thấy file đã đổi rồi tuyên bố rotation đã hoàn tất.

## 20. Ví dụ về một quy trình chuyển đổi từ env sang mounted file

Giả sử phiên bản cũ dùng:

~~~text
SPRING_DATASOURCE_PASSWORD
~~~

Phiên bản mới muốn dùng:

~~~text
/run/secrets/spring.datasource.password
~~~

và import:

~~~properties
spring.config.import=configtree:/run/secrets/
~~~

Một quy trình chuyển đổi có kiểm soát:

**Giai đoạn 1 — chuẩn bị**

- Kiểm tra nền tảng có thể cấp file bí mật cho đúng workload.
- Chọn tên file đúng property cần dùng.
- Bảo đảm JVM user đọc được file.
- Chuẩn bị khả năng rollback và cách thu hồi credential.

**Giai đoạn 2 — triển khai**

- Thêm cấu hình `spring.config.import` ở môi trường mục tiêu.
- Mount secret file theo tên đã chọn.
- **Loại bỏ biến môi trường cũ chứa cùng khóa** khỏi deployment specification trong cùng kế hoạch.
- Triển khai một nhóm instance nhỏ trước nếu hệ thống cho phép.

**Giai đoạn 3 — xác minh**

- Kiểm tra ứng dụng khởi động thành công.
- Kiểm tra DataSource/HTTP client thực sự kết nối được.
- Không so sánh hoặc in password thô.
- Kiểm tra log có hiển thị secret không.
- Kiểm tra đường dẫn mount và quyền file mà không trích nội dung.

**Giai đoạn 4 — hoàn tất**

- Mở rộng rollout.
- Thu hồi credential cũ khi an toàn.
- Xóa biến/volume/secret name không còn dùng.
- Cập nhật tài liệu vận hành về nguồn duy nhất của secret.

Nếu để cả môi trường và file mount tồn tại cùng lúc, bạn phải hiểu rõ độ ưu tiên. Chỉ mount được file không chứng minh nó đang thắng giá trị environment.

## 21. Những sai lầm thường gặp

### Lỗi 1 — Để bí mật thật trong application.yaml

~~~yaml
partner:
  auth:
    client-secret: REAL_SECRET
~~~

Dữ liệu có thể đi vào Git, JAR, image và log. Hãy externalize giá trị.

### Lỗi 2 — Dùng biến môi trường nhưng in toàn bộ Environment

~~~java
System.out.println(System.getenv());
~~~

Cách này có thể xuất các secret mà runtime cấp. Chỉ kiểm tra tên khóa cần thiết hoặc trạng thái có/không có.

### Lỗi 3 — Đặt secret ở command line

~~~bash
java -jar app.jar --partner.auth.client-secret=REAL_SECRET
~~~

Tham số có thể bị lưu trong process list, script và công cụ chẩn đoán. Tránh dùng với bí mật thật.

### Lỗi 4 — Nghĩ _FILE tự động được Spring Boot hỗ trợ cho mọi khóa

~~~text
PARTNER_AUTH_CLIENTSECRET_FILE=/run/secrets/token
~~~

Đây không phải cam kết chung rằng Spring Boot sẽ đọc nội dung file và gắn vào `partner.auth.client-secret`. Dùng `configtree:` hoặc cơ chế đọc file được thiết kế rõ ràng.

### Lỗi 5 — Mount file đúng nhưng quên configtree:

File:

~~~text
/run/secrets/partner.auth.client-secret
~~~

Nếu chưa cấu hình import hoặc một cơ chế đọc trực tiếp, Spring Boot không mặc nhiên có `partner.auth.client-secret` chỉ vì file xuất hiện.

### Lỗi 6 — Sai root của configtree

~~~text
/etc/config/myapp/password
~~~

Import root `/etc/config/` có thể tạo `myapp.password`, nhưng import root `/etc/config/myapp/` tạo `password`. Kiểm tra tên khóa chính xác.

### Lỗi 7 — Mount một YAML file nhưng import như configtree:

~~~text
/run/secrets/secure-config.yaml
~~~

Nếu muốn nội dung YAML được parse thành nhiều thuộc tính, dùng `file:/run/secrets/secure-config.yaml` chứ không phải giả định `configtree:` sẽ parse YAML tự động.

### Lỗi 8 — Không xử lý key thiếu hoặc file rỗng

Directory tồn tại không chứng minh có file cần thiết. Dùng validation và cấu hình orchestration phù hợp để thất bại sớm.

### Lỗi 9 — optional: được hiểu thành “credential có thể thiếu”

`optional:` chỉ ảnh hưởng cách xử lý **vị trí Config Data không tồn tại**. Nếu secret bắt buộc, validation nghiệp vụ vẫn phải bảo đảm ứng dụng không hoạt động với credential thiếu.

### Lỗi 10 — Có hai nguồn cùng tên khóa

Environment và configtree đều cấp `spring.datasource.password`. Người vận hành tưởng file mới được dùng, nhưng environment ưu tiên hơn theo thứ tự thông thường. Loại bỏ nguồn cũ hoặc kiểm soát rõ độ ưu tiên.

### Lỗi 11 — File không đọc được do owner/mode

Secret có quyền `0400` nhưng JVM chạy user không sở hữu file. Cần sửa quyền theo principle of least privilege, không mở quyền quá rộng.

### Lỗi 12 — Cho rằng Kubernetes Secret tự được mã hóa khi lưu

Kubernetes Secret không mặc nhiên bảo đảm encryption at rest của datastore. Cần cấu hình mã hóa, RBAC và quản lý quyền phù hợp.

### Lỗi 13 — Base64 bị coi là bảo vệ bí mật

Một giá trị `data` ở dạng base64 có thể được giải mã. Đây không phải là mật mã bảo vệ dữ liệu.

### Lỗi 14 — Cập nhật file và mong Spring bean tự refresh

Kubernetes có thể cập nhật file mount, nhưng `@ConfigurationProperties`/DataSource đã tạo không tự động nhận credential mới nếu ứng dụng không hỗ trợ reload. Cần kế hoạch restart hoặc refresh rõ ràng.

### Lỗi 15 — Dùng subPath nhưng mong volume tự cập nhật

Kubernetes Secret mount qua `subPath` không nhận tự động cập nhật theo cơ chế volume thông thường. Điều này ảnh hưởng chiến lược rotation.

### Lỗi 16 — Log toàn bộ record chứa secret

~~~java
log.info("credentials = {}", credentials);
~~~

Record thường có `toString()` tự sinh chứa cả thành viên secret. Không log object chứa password/token.

### Lỗi 17 — Commit file local secret để “dễ chạy thử”

File như `./secrets/token.txt` được đặt trong thư mục dự án có thể bị Git add nhầm, bị đồng bộ lên cloud hoặc được đính kèm ticket. Dùng file ngoài repository, cơ chế local secret manager hoặc dữ liệu demo không có giá trị thật.

### Lỗi 18 — Coi mounted file là tuyệt đối an toàn

Một tiến trình có quyền đọc file vẫn có thể làm lộ bí mật qua code độc hại, log, memory dump hoặc quyền host. Mount chỉ là một cách cấp dữ liệu và giới hạn bề mặt tiếp xúc; bảo mật còn cần isolation, RBAC, patching và kiểm toán.

## 22. Kiểm thử không cần secret thật

Không bao giờ đưa credential production vào bài test thông thường.

### 22.1. Test với Environment giả

Bạn có thể dùng Spring Boot test properties chứa chuỗi **giả, không có hiệu lực** để xác minh binding:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest(properties = {
        "partner.auth.client-id=demo-client",
        "partner.auth.client-secret=DEMO_ONLY_TEST_VALUE"
})
class PartnerAuthBindingTest {

    @Autowired
    PartnerCredentials credentials;

    @Test
    void bindsCredentials() {
        assertEquals(
                "demo-client",
                credentials.clientId());

        // Chỉ dùng giá trị test hoàn toàn giả.
        assertEquals(
                "DEMO_ONLY_TEST_VALUE",
                credentials.clientSecret());
    }
}
~~~

Yêu cầu class properties đã được đăng ký phù hợp với `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties`.

### 22.2. Test mounted configuration tree trong môi trường tạm

Một bài integration test có thể tạo temporary directory, viết **dữ liệu giả** vào các file tên đúng và khởi chạy Spring Boot context với `spring.config.import=configtree:<test-dir>/`.

Cần chuẩn bị path trước thời điểm Config Data được nạp; vì vậy khi dùng test động, nên triển khai bằng cơ chế phù hợp với startup configuration (ví dụ tham số trước lúc tạo context) thay vì ghi file sau khi ứng dụng đã khởi tạo.

Điểm kiểm tra:

1. File tên `partner.auth.client-secret` tạo đúng property.
2. Nội dung test được bind vào class.
3. Nếu file thiếu hoặc root sai, test phát hiện.
4. Nếu có biến môi trường/PropertySource ưu tiên hơn, test xác định nguồn nào thắng mà không dùng secret thật.

### 22.3. Kiểm tra lỗi khi file bị thiếu

Nếu import bắt buộc:

~~~properties
spring.config.import=configtree:/some/nonexistent/dir/
~~~

ứng dụng có thể thất bại ở giai đoạn Config Data. Đây là hành vi cần thiết nếu môi trường không cho phép chạy thiếu secret directory.

Nếu import optional:

~~~properties
spring.config.import=optional:configtree:/some/nonexistent/dir/
~~~

giai đoạn nạp có thể tiếp tục, nhưng bean cấu hình có `@NotBlank` trên credential bắt buộc vẫn cần báo vi phạm nếu key không có giá trị.

### 22.4. Kiểm tra không có secret trong log

Trong CI/integration test, sử dụng một marker giả dễ nhận biết như `DEMO_ONLY_SENTINEL_VALUE` rồi xác minh luồng log không chứa marker. Điều này không thay thế kiểm toán đầy đủ, nhưng giúp phát hiện các lệnh log `Environment`, `toString()` hoặc lỗi debug vô tình xuất giá trị.

Chỉ dùng marker không có quyền truy cập hệ thống thật.

## 23. Khi nào ứng dụng cần đọc file trực tiếp thay vì configtree?

`configtree:` đặc biệt phù hợp nếu secret là **một giá trị cấu hình logic** mà Spring/third-party auto-configuration cần lấy qua `Environment`.

Có những trường hợp bạn có thể cần đường dẫn file trực tiếp:

- Một thư viện TLS yêu cầu đường dẫn tới certificate hoặc private key ở filesystem.
- Secret chứa dữ liệu binary được tiêu thụ qua stream.
- Kích thước file lớn hoặc dữ liệu không nên chuyển thành một property String.
- Cơ chế rotation do ứng dụng giám sát file và tự nạp lại bằng API của thư viện.
- Ứng dụng cần xác thực file permission/format trước khi truyền cho thư viện.

Ví dụ chỉ kiểm tra path:

~~~java
import java.nio.file.Files;
import java.nio.file.Path;

public final class SecretFileCheck {

    public static void requireReadable(Path path) {
        if (!Files.isRegularFile(path) || !Files.isReadable(path)) {
            throw new IllegalStateException(
                    "Secret file không tồn tại hoặc không thể đọc");
        }
    }
}
~~~

Mã trên không in nội dung file. Nếu cần đọc bytes:

~~~java
byte[] data = Files.readAllBytes(path);
~~~

thì phải cân nhắc lifecycle, giới hạn kích thước, khả năng xóa bản sao khỏi memory nếu thích hợp, nguy cơ secret bị chuyển sang String bất biến, và hợp đồng của thư viện nhận dữ liệu.

**Không bắt buộc phải đưa mọi private key vào Environment.** Spring Boot có `configtree:` để thuận tiện cho cấu hình, nhưng các thư viện tiêu thụ certificate/keys có thể có API file/resource trực tiếp phù hợp hơn.

## 24. Bảng so sánh hai phương án cấp secret

| Tiêu chí | Biến môi trường | Mounted file + configtree |
| --- | --- | --- |
| Dạng dữ liệu | Cặp tên biến và giá trị | File name/path là key, nội dung là value |
| Cấp trong Kubernetes | `env.valueFrom.secretKeyRef` | Secret volume + `volumeMounts` |
| Cấp trong Compose | Environment do runtime/provisioner truyền | Compose `secrets` mount vào `/run/secrets/` |
| Spring Boot đọc như nào? | Tự động qua OS environment source | Cần `spring.config.import=configtree:/.../` hoặc cơ chế tương đương |
| Phù hợp với | Giá trị text ngắn | Text, nhiều key, certificate/file secrets |
| Nguy cơ phổ biến | Lộ qua environment/process metadata, log, child process | Sai quyền file, mount path, đọc file hoặc log |
| Secret thay đổi khi runtime | Thường cần restart tiến trình | File có thể đổi tùy nền tảng; Spring bean không tự refresh |
| Quyền truy cập | Phụ thuộc process/runtime isolation | File mode, owner/group, mount và container isolation |
| Thứ tự PropertySource | Có ưu tiên theo OS env | Là Config Data; có thể bị environment/CLI ghi đè |
| Lỗi điển hình | Sai tên biến hoặc biến chưa được cấp | Sai root `configtree:`, thiếu file, permission denied |

Không có một phương án luôn thắng cho mọi hệ thống. Lựa chọn phụ thuộc vào yêu cầu vận hành, loại dữ liệu, secret manager, quyền tiến trình và kế hoạch rotation.

## 25. Bài thực hành có đáp án

### Bài 1 — đổi tên property thành biến môi trường

Cho:

~~~text
spring.datasource.password
partner.auth.client-secret
security.jwt.signing-key
~~~

**Đáp án:**

~~~text
SPRING_DATASOURCE_PASSWORD
PARTNER_AUTH_CLIENTSECRET
SECURITY_JWT_SIGNINGKEY
~~~

Dấu chấm thành gạch dưới, dấu gạch ngang bị bỏ và các ký tự được viết hoa.

### Bài 2 — cấu trúc configtree

Container có:

~~~text
/run/secrets/
└── partner.auth.client-secret
~~~

Spring Boot import:

~~~properties
spring.config.import=configtree:/run/secrets/
~~~

**Đáp án:** có property `partner.auth.client-secret` với giá trị là nội dung file, nếu import thành công.

### Bài 3 — root thư mục

Có:

~~~text
/etc/config/app/password
~~~

**Hỏi:** hai import sau cho tên khóa gì?

~~~properties
spring.config.import=configtree:/etc/config/
~~~

và:

~~~properties
spring.config.import=configtree:/etc/config/app/
~~~

**Đáp án:** cách đầu tạo `app.password`, cách sau tạo `password`.

### Bài 4 — YAML file so với config tree

Có file:

~~~text
/etc/secrets/app-secrets.yaml
~~~

trong đó chứa nhiều khóa YAML.

**Đáp án:** dùng `spring.config.import=file:/etc/secrets/app-secrets.yaml` nếu muốn Spring Boot parse file YAML. `configtree:` dùng cho directory chứa file theo dạng key-value.

### Bài 5 — optional có đủ bảo vệ bí mật không?

~~~properties
spring.config.import=optional:configtree:/run/secrets/
~~~

Ứng dụng bắt buộc cần `partner.auth.client-secret`.

**Đáp án:** chưa đủ. `optional:` chỉ cho phép không có vị trí import; cần ràng buộc missing/blank secret qua validation hoặc startup check thích hợp.

### Bài 6 — Docker Compose _FILE

Bạn đặt:

~~~text
PARTNER_AUTH_CLIENTSECRET_FILE=/run/secrets/partner-token
~~~

**Hỏi:** Spring Boot có tự lấy nội dung file làm `partner.auth.client-secret` không?

**Đáp án:** không nên giả định. `_FILE` là quy ước của một số container images/entrypoints, không phải khả năng chung cho mọi property Spring Boot. Dùng `configtree:` hoặc logic file-reading có chủ đích.

### Bài 7 — Kubernetes env

Trong Pod:

~~~yaml
env:
  - name: SPRING_DATASOURCE_PASSWORD
    valueFrom:
      secretKeyRef:
        name: db-credentials
        key: password
~~~

**Đáp án:** Kubernetes lấy key `password` của Secret và cấp vào environment variable của container; Spring Boot có thể dùng cho `spring.datasource.password`.

### Bài 8 — Kubernetes file mapping

~~~yaml
volumes:
  - name: db
    secret:
      secretName: db-credentials
      items:
        - key: password
          path: spring.datasource.password
~~~

Mount vào `/etc/secrets/`, rồi import `configtree:/etc/secrets/`.

**Đáp án:** file tên `spring.datasource.password` cung cấp khóa logic tương ứng khi Spring Boot nạp tree.

### Bài 9 — hai nguồn tranh nhau

Có mounted file cho `spring.datasource.password`, nhưng container vẫn có `SPRING_DATASOURCE_PASSWORD`.

**Đáp án:** trong thứ tự nguồn mặc định, biến môi trường có thể ưu tiên hơn Config Data từ tree. Cần loại bỏ nguồn cũ hoặc xác minh thứ tự, không suy luận file chắc chắn được dùng.

### Bài 10 — xoay vòng bí mật

Một Kubernetes Secret được cập nhật. Volume mount đã có file mới.

**Hỏi:** DataSource đã tạo chắc chắn dùng password mới chưa?

**Đáp án:** chưa chắc. File có thể cập nhật, nhưng Spring Boot nạp Config Data lúc startup và DataSource có thể giữ credential cũ. Cần rollout/restart hoặc cơ chế refresh/recreate được thiết kế riêng.

### Bài 11 — chmod 0400

Một Secret file có quyền `0400` và JVM chạy dưới user không sở hữu file.

**Đáp án:** ứng dụng có thể không đọc được. Hãy sửa quyền/identity theo least privilege, không mở `0777`.

### Bài 12 — phòng ngừa lộ dữ liệu qua log

Một record có:

~~~java
public record PartnerCredentials(
        String clientId,
        String clientSecret) {
}
~~~

**Hỏi:** có nên `log.info("{}", credentials)` không?

**Đáp án:** không. Record `toString()` có thể in `clientSecret`. Chỉ log tình trạng cấu hình hoặc thông tin đã được che.

### Bài 13 — validate file rỗng

Secret file đúng tên nhưng có nội dung chuỗi rỗng.

**Đáp án:** directory import có thể thành công nhưng credential vẫn không hợp lệ. Dùng `@NotBlank` hoặc validation rõ ràng để từ chối chạy nếu credential bắt buộc.

### Bài 14 — Base64

Kubernetes `Secret.data` chứa giá trị base64.

**Đáp án:** đó là mã hóa biểu diễn, không phải lớp bảo mật mã hóa nội dung. Cần hạn chế quyền truy cập, bật encryption at rest, bảo vệ API và điều phối secret.

### Bài 15 — lựa chọn phương án

Một hệ thống cần đưa certificate và private key cho thư viện chỉ nhận file path; đồng thời có một API token text.

**Đáp án gợi ý:** xem xét mount certificate/private key thành file với quyền hạn chế để thư viện đọc trực tiếp; token có thể được cấp qua một file tree hoặc environment tùy chính sách. Không bắt buộc mọi secret phải được chuyển thành String trong `Environment`.

## 26. Checklist triển khai an toàn

Trước khi đưa Spring Boot application lên production, nên kiểm tra theo các nhóm sau.

### 26.1. Nguồn bí mật

- Giá trị thật không nằm trong Git, container image, Dockerfile hoặc tài liệu công khai.
- Secret được cấp qua một hệ thống có chính sách kiểm soát quyền và rotation.
- Không có bản sao bí mật không cần thiết trong script, CI variables hoặc file local.
- Một secret chỉ được cấp cho workload thực sự cần dùng.

### 26.2. Spring Boot configuration

- Tên property đúng canonical/relaxed binding.
- Nếu dùng env, tên biến môi trường đúng.
- Nếu dùng mount, root `configtree:` và tên file đúng.
- Nếu dùng file YAML hoàn chỉnh, chọn import `file:` phù hợp.
- Không có hai nguồn cùng khóa một cách ngoài ý muốn.
- Cấu hình bắt buộc có validation hoặc startup check.
- Không có mật khẩu mặc định công khai ở production.

### 26.3. Quyền và phạm vi

- Container chạy với user thích hợp.
- Mounted secret chỉ cho tiến trình cần thiết đọc.
- Volume ở trạng thái read-only khi phù hợp.
- File mode, owner, group và directory permission hợp lệ.
- Kubernetes RBAC theo least privilege, có encryption at rest khi cần.
- Hạn chế quyền debug/exec vào container production.

### 26.4. Quan sát và log

- Không in toàn bộ `Environment`, record chứa secret hay secret file.
- Không bật logging cấu hình ở mức có thể phơi bày giá trị mà không kiểm soát.
- Actuator endpoints liên quan `env` / `configprops` được bảo vệ; không giả định mọi dữ liệu luôn được che ở mọi phiên bản/cấu hình.
- Lỗi startup báo **tên khóa thiếu hoặc không đọc được**, không báo nội dung bí mật.
- Có cơ chế kiểm thử phát hiện secret marker bị log ra ngoài.

### 26.5. Rotation và khôi phục

- Biết secret cập nhật qua environment hay volume.
- Biết trường hợp `subPath` không tự cập nhật.
- Biết Spring Boot có cần restart/rebind/recreate client không.
- Có kế hoạch rolling deployment và rollback.
- Credential cũ được thu hồi sau khi workload mới đã sử dụng thành công.
- Có quy trình sự cố nếu secret bị lộ hoặc cấp sai đối tượng.

## 27. Kết luận

Có hai con đường phổ biến để **cấp bí mật cho Spring Boot khi ứng dụng đang chạy**:

- **Biến môi trường:** nền tảng đưa `SPRING_DATASOURCE_PASSWORD` hoặc một tên biến tương ứng vào environment của tiến trình. Spring Boot đọc giá trị qua `Environment`; không cần chứa password literal trong application file.
- **Tệp được mount:** nền tảng cấp file ở đường dẫn như `/run/secrets/spring.datasource.password`, và Spring Boot có thể import bằng `spring.config.import=configtree:/run/secrets/` để ánh xạ tên file thành tên property.

Cả hai phương án giúp tách **giá trị bí mật** khỏi **mã nguồn và artifact**, nhưng không thay thế quản lý bí mật an toàn. Hệ thống vẫn cần phân quyền file/container, RBAC, kiểm soát log, encryption at rest khi phù hợp, validation khi thiếu credential, thứ tự ưu tiên cấu hình và một quy trình rotation rõ ràng.

Hãy luôn xác định **secret được cấp ở đâu, Spring Boot đọc bằng cơ chế nào, tên property có đúng không, nguồn nào thắng, và tiến trình sẽ nhận secret mới như thế nào**. Năm câu hỏi ấy giúp chẩn đoán phần lớn lỗi khi chuyển ứng dụng từ mật khẩu hard-code sang environment hoặc mounted secret files.

## Tài liệu tham khảo

- [Spring Boot 3.3 — Externalized Configuration và Configuration Trees](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html).
- [Spring Boot — Type-safe Configuration Properties](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties).
- [Docker Compose — Manage secrets securely](https://docs.docker.com/compose/how-tos/use-secrets/).
- [Kubernetes — Secrets](https://kubernetes.io/docs/concepts/configuration/secret/).
- [Kubernetes — Distribute Credentials Securely Using Secrets](https://kubernetes.io/docs/tasks/inject-data-application/distribute-credentials-secure/).