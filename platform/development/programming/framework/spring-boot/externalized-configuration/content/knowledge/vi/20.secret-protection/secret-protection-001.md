# Phân loại giá trị cấu hình thông thường và thông tin bí mật

Trong Spring Boot, cùng một cơ chế **Externalized Configuration** có thể cung cấp cả những giá trị rất bình thường như `server.port=8080` lẫn các giá trị cực kỳ nhạy cảm như mật khẩu cơ sở dữ liệu, API token hoặc private key. Cả hai đều có thể xuất hiện dưới dạng key/value và được truy cập qua `Environment`, `@Value` hay `@ConfigurationProperties`. Tuy nhiên, **cách một giá trị được đọc trong Java không quyết định nó có an toàn để lưu vào Git, hiển thị trong log hoặc đưa vào báo cáo hay không**.

Kỹ năng quan trọng là **phân loại trước khi lưu và sử dụng**: giá trị nào có thể công khai, giá trị nào chỉ dành cho nội bộ, giá trị nào là dữ liệu mật cần hạn chế truy cập, và giá trị nào là **secret** có thể trực tiếp cho phép truy cập hệ thống nếu bị lộ.

Bài này hướng dẫn nhận diện dữ liệu cấu hình theo rủi ro, phân biệt *secret* với *thông tin nhạy cảm nhưng không phải credential*, tổ chức `application.yml` an toàn, lựa chọn nguồn cấp secret, hạn chế rò rỉ qua Git/CI/CD/log/Actuator, triển khai ví dụ Spring Boot, và xây quy trình xử lý khi nghi ngờ lộ bí mật.

> **Nguyên tắc:** Cấu hình thông thường có thể được version-control theo chính sách dự án; **secret thật phải được quản lý bằng cơ chế cấp phát, phân quyền, bảo vệ và xoay vòng phù hợp**, không hardcode trong mã hoặc file cấu hình được commit.

## 1. Vì sao phải phân loại trước khi cấu hình?

Giả sử file `application.yml` chứa:

~~~yaml
server:
  port: 8080

app:
  feature:
    catalog-preview-enabled: false
  external-api:
    base-url: https://partner.example.test
    api-key: REDACTED_EXAMPLE_ONLY
  billing:
    tenant-id: tenant-demo
~~~

Về cú pháp, `server.port`, `catalog-preview-enabled`, `base-url`, `api-key` và `tenant-id` đều là property. Nhưng mức rủi ro khác nhau:

- `server.port` thường là thông số vận hành, không có khả năng tự cấp quyền truy cập.
- Feature flag có thể chỉ là thiết lập bình thường, nhưng flag tiết lộ chiến lược phát hành hoặc chức năng chưa công bố có thể mang tính nội bộ.
- API base URL công khai thường không phải secret, nhưng endpoint nội bộ có thể tiết lộ sơ đồ hệ thống và nên hạn chế phân phối.
- API key có thể là **secret**: ai sở hữu key hợp lệ có thể gọi API hoặc tiêu thụ hạn mức, tùy quyền của key.
- Tenant ID thường là **identifier**, không phải password; tuy nhiên vẫn có thể là dữ liệu nội bộ, định danh khách hàng hoặc nhạy cảm theo bối cảnh.

Nếu đối xử với mọi property như dữ liệu thường, bạn dễ commit nhầm credential, in nguyên object cấu hình trong log hoặc trả token qua endpoint hỗ trợ debug. Nếu đối xử với mọi property như secret, hệ thống lại khó vận hành, khó chia sẻ tài liệu và khó tự động hóa cần thiết.

Phân loại giúp trả lời các câu hỏi thiết kế: **giá trị được lưu ở đâu, ai được xem, có được đưa vào log không, có thể dùng default không, được thay đổi như thế nào và làm gì khi bị lộ?**

## 2. Taxonomy thực dụng cho cấu hình Spring Boot

Có thể bắt đầu với bốn mức. Tên mức là gợi ý; tổ chức có thể sử dụng chính sách khác.

| Mức | Ví dụ | Rủi ro nếu lộ | Cách xử lý điển hình |
| --- | --- | --- | --- |
| Công khai hoặc ít nhạy cảm | Cổng local, tên chức năng công khai, timeout chung | Thấp trong nhiều bối cảnh | Có thể nằm trong file cấu hình version-control nếu chính sách cho phép |
| Nội bộ | Tên service, hostname nội bộ, feature flag chưa phát hành, kiến trúc routing | Tiết lộ tổ chức hoặc hạ tầng | Giới hạn người đọc repository và tài liệu |
| Dữ liệu mật/nhạy cảm | Định danh khách hàng, endpoint riêng, business identifier, dữ liệu cá nhân | Có thể gây rủi ro riêng tư/kinh doanh | Kiểm soát truy cập, giảm log, mã hóa/retention theo chính sách |
| Secret xác thực hoặc mật mã | Password, access token, API key, client secret, private key, khóa ký | Có thể cho phép hành động trái phép | Secret manager hoặc kho bí mật được kiểm soát, không commit, xoay vòng và audit |

**Secret là một loại dữ liệu nhạy cảm đặc biệt vì chính giá trị đó thường có khả năng xác thực, giải mã, ký hoặc cấp quyền.** Không phải tất cả dữ liệu bí mật theo nghĩa kinh doanh đều là credential; nhưng cả hai vẫn cần cơ chế bảo vệ phù hợp.

Một giá trị có thể thay đổi mức phân loại theo bối cảnh. URL public endpoint có thể công khai; cùng URL nếu chứa query parameter `token=...` thì toàn bộ chuỗi URL phải được bảo vệ như secret. Một username đơn lẻ thường không xác thực được, nhưng username vẫn có thể là thông tin nội bộ/định danh cá nhân.

## 3. Cách nhận diện một secret thật

Hãy hỏi theo các câu sau:

1. **Giá trị này có được dùng để xác thực hoặc cấp quyền không?** Nếu có, thường là secret.
2. **Ai có giá trị này có thể đọc/sửa dữ liệu, ký request hoặc tiêu tốn tài nguyên không?** Nếu có, cần bảo vệ mạnh.
3. **Giá trị có thể được dùng để giải mã dữ liệu đã mã hóa không?** Khóa giải mã là secret.
4. **Giá trị có thể giả mạo một hệ thống hoặc một danh tính không?** Private key và signing key là secret.
5. **Giá trị có được một nhà cung cấp cấp phát kèm quyền/quota không?** API token/key thường là secret.
6. **Giá trị chỉ là tên định danh hoặc địa chỉ không có khả năng cấp quyền?** Có thể vẫn nhạy cảm, nhưng không tự động là authentication secret.
7. **Giá trị có chứa credential trong một chuỗi tổng hợp không?** Phải xét toàn bộ chuỗi, không chỉ tên key.

Những key hay báo hiệu secret:

~~~text
*.password
*.secret
*.token
*.api-key
*.private-key
*.client-secret
*.access-key
*.signing-key
*.credential
*.connection-string
~~~

Đây chỉ là **dấu hiệu nhận diện**, không phải bộ phân loại hoàn hảo. Key `app.demo.fake-token` có thể là placeholder không có quyền thật; ngược lại, `app.connection-url` có thể chứa username/password dù tên không có `password`.

### Không dựa vào tên key làm bằng chứng duy nhất

Ví dụ:

~~~properties
# Không chứa credential trong ví dụ này:
app.service.endpoint=https://api.example.test

# Có thể chứa credential thật nếu được cung cấp như DSN:
app.datasource.url=jdbc:postgresql://host.example.test/db?password=REDACTED

# Có thể mang token ở query string:
app.redirect-url=https://service.example.test/callback?access_token=REDACTED
~~~

Khi một URL, DSN hoặc chuỗi cấu hình có credential nhúng, hãy **phân loại toàn bộ value** ở mức cần bảo vệ. Đừng chỉ che một key tên `password` rồi để giá trị secret xuất hiện dưới key `url` trong log.

## 4. Ví dụ phân loại các property phổ biến

| Key hoặc loại dữ liệu | Phân loại gợi ý | Lý do |
| --- | --- | --- |
| `server.port` | Thường | Cổng ứng dụng, không tự xác thực |
| `spring.application.name` | Thường/nội bộ | Có thể tiết lộ tên hệ thống |
| `logging.level.com.example` | Thường, nhưng cần quản lý thay đổi | Mức log có thể tăng rủi ro rò rỉ dữ liệu |
| `app.client.timeout` | Thường | Thời lượng chờ |
| `app.feature.new-checkout-enabled` | Nội bộ tùy bối cảnh | Có thể tiết lộ chức năng chưa công bố |
| `app.partner.base-url` | Thường hoặc nội bộ | URL public khác endpoint nội bộ |
| `spring.datasource.username` | Nội bộ hoặc nhạy cảm | Identifier, có thể hỗ trợ khai thác khi kết hợp thông tin khác |
| `spring.datasource.password` | Secret | Credential truy cập database |
| `app.partner.api-key` | Secret | Có thể trực tiếp gọi API |
| `spring.security.oauth2.client.registration.*.client-secret` | Secret | OAuth client credential |
| `app.jwt.signing-key` | Secret | Có thể tạo token giả nếu key bị lộ |
| TLS private key | Secret | Chứng minh danh tính của dịch vụ |
| TLS public certificate | Thường có thể phân phối | Public certificate không chứa private key |
| Token định danh phiên | Secret | Có thể cho phép chiếm phiên |
| `app.customer-id` | Dữ liệu nội bộ/nhạy cảm | Có thể liên quan khách hàng |
| Hash password | Nhạy cảm cao | Có thể hỗ trợ tấn công offline; không coi là dữ liệu public |
| Khóa mã hóa dữ liệu | Secret | Có thể giải mã dữ liệu lưu trữ |
| Kubernetes Secret name | Thường/nội bộ | Tên resource không phải secret content; vẫn tiết lộ cấu trúc |

Bảng chỉ là gợi ý: phải áp dụng chính sách phân loại của tổ chức, môi trường triển khai, yêu cầu pháp lý và khả năng khai thác thực tế.

## 5. Tách cấu hình thông thường khỏi giá trị secret

Một cách tổ chức dễ duy trì là **commit cấu trúc và tên property**, nhưng cấp secret thật từ môi trường triển khai.

Ví dụ file `application.yml` có thể được lưu trong repository:

~~~yaml
spring:
  application:
    name: order-service

server:
  port: 8080

app:
  external-api:
    base-url: https://api.example.test
    timeout: 3s
    api-key: ${APP_EXTERNAL_APIKEY}
~~~

Ý nghĩa:

- `base-url` và `timeout` là cấu hình thông thường trong ví dụ.
- `api-key` vẫn là một property mà code Java có thể bind.
- `${APP_EXTERNAL_APIKEY}` là placeholder lấy value được cung cấp tại runtime qua Spring Environment.
- Giá trị thật của `APP_EXTERNAL_APIKEY` **không xuất hiện trong file được commit**.

Chú ý: placeholder không tự tạo ra secret và không tự làm mã hóa. Nó chỉ tách **nơi mô tả cấu hình** khỏi **nơi cung cấp giá trị**.

### Không dùng default giả làm credential production

Một mẫu có rủi ro:

~~~yaml
app:
  external-api:
    api-key: ${APP_EXTERNAL_APIKEY:demo-secret}
~~~

Nếu biến môi trường thiếu ở production, ứng dụng có thể nhận `demo-secret` rồi cố hoạt động hoặc thất bại ở thời điểm gọi API. Tùy ngữ cảnh, fallback này có thể che lỗi triển khai hoặc khiến một credential yếu xuất hiện trong hệ thống.

Với credential bắt buộc, nên yêu cầu cung cấp đầy đủ và dùng validation/fail-fast. Với test, có thể inject giá trị giả riêng trong test context, không lấy secret production làm default chung.

## 6. Spring Boot bind secret cũng như các property khác

`@ConfigurationProperties` không có một “bộ nhớ secret” tự động an toàn hơn String thông thường. Binder chỉ nhận value hiệu lực và chuyển thành kiểu Java.

Ví dụ:

~~~java
package com.example.orders.config;

import java.net.URI;
import java.time.Duration;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.external-api")
public record ExternalApiProperties(
    @NotNull URI baseUrl,
    @NotNull Duration timeout,
    @NotBlank String apiKey
) {}
~~~

Đăng ký bean:

~~~java
package com.example.orders;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class OrderApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrderApplication.class, args);
    }
}
~~~

Ví dụ consumer:

~~~java
package com.example.orders.client;

import com.example.orders.config.ExternalApiProperties;
import org.springframework.stereotype.Service;

@Service
public class ExternalApiClient {
    private final ExternalApiProperties properties;

    public ExternalApiClient(ExternalApiProperties properties) {
        this.properties = properties;
    }

    public boolean configured() {
        return properties.apiKey() != null
            && !properties.apiKey().isBlank();
    }
}
~~~

Đây là ví dụ minh họa việc inject typed config, **không phải ví dụ gửi credential đến một endpoint**. Trong ứng dụng thật, API client cần đưa key vào header theo quy định của nhà cung cấp và bảo vệ kết nối bằng TLS; không in key ra log.

`@NotBlank` giúp phát hiện secret rỗng hoặc thiếu trong một model được validate đúng, nhưng **không đánh giá chất lượng mật mã** của key và không chứng minh key đó còn hiệu lực trên hệ thống nhà cung cấp.

### Record có rủi ro toString()

Record Java tự tạo `toString()` bao gồm các component. Nếu có `apiKey`, gọi:

~~~java
System.out.println(properties);
~~~

có thể in secret. **Không log nguyên record cấu hình chứa credential.** Tương tự, Lombok `@Data` hoặc `@ToString` trên properties class có thể khiến password/token xuất hiện trong log nếu không được loại trừ.

Nếu bắt buộc cần log trạng thái cấu hình, chỉ log **trạng thái tồn tại của key**, version hoặc metadata không nhạy cảm đã được xem xét; không log giá trị bí mật. Việc log một vài ký tự đầu/cuối token cũng cần chính sách rõ vì có thể giúp liên kết hoặc khai thác thông tin.

## 7. @Value và Environment không tự che secret

Cùng một key có thể được truy cập bằng nhiều cách:

~~~java
String apiKey = environment.getProperty(
    "app.external-api.api-key");
~~~

~~~java
public ApiAdapter(
    @Value("${app.external-api.api-key}") String apiKey
) {
    this.apiKey = apiKey;
}
~~~

~~~java
public ApiAdapter(ExternalApiProperties props) {
    this.apiKey = props.apiKey();
}
~~~

Dù đọc bằng `Environment`, `@Value` hay `@ConfigurationProperties`, **giá trị sau khi đọc vẫn là secret**. Các cơ chế trên không tự mã hóa lại secret, giới hạn ai được debug JVM hoặc ngăn developer ghi nó ra log.

Đặc biệt:

- `System.getenv("APP_EXTERNAL_APIKEY")` đọc biến môi trường của process.
- `System.getProperty("app.external-api.api-key")` đọc Java system property tương ứng nếu được cung cấp.
- `Environment.getProperty(...)` tra qua các Spring `PropertySource` theo thứ tự ưu tiên.
- `@ConfigurationProperties` bind value hiệu lực vào object Java.

Không nên xem việc chuyển từ `@Value` sang `@ConfigurationProperties` là một biện pháp thay thế secret manager. Đây là thay đổi **cách tổ chức code**, không phải thay đổi mô hình bảo vệ thông tin.

## 8. Nguồn cấp secret: lợi ích và giới hạn

Có nhiều cách cung cấp secret cho Spring Boot; không có cách nào an toàn chỉ vì nó được gọi là “external”.

| Nguồn | Điểm thuận tiện | Rủi ro cần kiểm soát |
| --- | --- | --- |
| File local nằm ngoài repository | Dễ dùng cho máy dev/server | Permission, backup, file bị copy, tệp vô tình bị commit |
| Biến môi trường | Hợp với container/CI, dễ tham chiếu | Có thể bị lộ qua debug, runtime inspection, crash dump hoặc log |
| JVM `-Dkey=value` | Thuận tiện cho hệ thống Java | Command/process arguments, script, log triển khai có thể lộ |
| App command-line `--key=value` | Dễ override | Argument thường có nguy cơ hiển thị qua process listing, history/log |
| File mount bởi orchestrator | Tách secret khỏi artifact | Quyền đọc file, volume/mount, vòng đời cập nhật |
| Secret manager tập trung | RBAC, audit, version/rotation tùy sản phẩm | Cần bảo vệ identity truy cập và kết nối tới secret store |
| KMS / encrypted configuration | Bảo vệ dữ liệu lưu trữ | Cần quản lý khóa giải mã, permission và thời điểm giải mã |
| Kubernetes Secret | Tích hợp deployment và container | Base64 không phải mã hóa; cần RBAC và encryption at rest |

Vì vậy, câu hỏi không chỉ là “đặt secret ở file hay env”, mà là: **ai cấp nó, ai đọc được, có bị lộ tại các điểm trung gian không, có quyền hạn gì, và có thể thu hồi khi lộ không?**

## 9. Vì sao hardcode secret trong source code là nguy hiểm?

Ví dụ chống chỉ định:

~~~java
public class DatabaseConfig {
    private static final String PASSWORD =
        "real-production-password-goes-here";
}
~~~

Vấn đề không dừng ở việc file Java có mật khẩu:

1. Secret đi vào lịch sử Git và có thể tồn tại trong commit cũ.
2. Fork, mirror, cache CI hoặc bản build lưu trữ có thể chứa giá trị.
3. Một số công cụ phân tích code, hỗ trợ AI, log hoặc issue có thể vô tình sao chép.
4. Artifact đóng gói có thể chứa chuỗi hardcoded.
5. Đổi credential đòi sửa mã và phát hành lại, làm vòng đời secret khó kiểm soát.
6. Việc xóa dòng khỏi commit mới **không tự thu hồi quyền truy cập của credential đã bị lộ**.

Không hardcode token, private key, database password hoặc credential production trong Java source, YAML đã commit, resource file, Dockerfile hoặc script deploy được chia sẻ.

### Kể cả file config tách biệt vẫn có thể bị commit

Một file:

~~~text
src/main/resources/application-prod.yml
~~~

cũng nằm trong artifact và có thể được commit. Chỉ vì tên chứa `prod` hoặc lưu trong `resources` không khiến nó trở thành nơi chứa secret an toàn.

Tương tự, Docker image layer có thể giữ nội dung được COPY vào, kể cả khi một bước build sau đã xóa file khỏi filesystem cuối. Tránh đưa secret vào Docker build context/layer hoặc artifact, trừ khi có cơ chế quản lý bí mật được thiết kế riêng phù hợp.

## 10. .gitignore là hàng rào phụ, không phải secret manager

Một repo có thể loại trừ các file local:

~~~gitignore
# Chỉ là ví dụ tên file local, cần phù hợp với dự án
.env.local
secrets/
config/local-secrets.yml
*.private-key.pem
~~~

Cách này giúp giảm commit nhầm với file **chưa được Git theo dõi**. Nhưng:

- `.gitignore` không tự bỏ theo dõi file đã được commit.
- Secret vẫn có thể bị lộ qua copy/paste, log, CI artifact hoặc email.
- Một file bị lộ trước đó có thể còn trong Git history.
- Tên file khác quy ước có thể lọt qua.
- Một repository private vẫn có thể bị chia sẻ hoặc truy cập trái phép.

Khi phát hiện secret thật từng được commit, **điều quan trọng trước tiên là thu hồi hoặc xoay credential**, rồi mới xử lý xóa nội dung khỏi nơi lưu trữ và lịch sử theo quy trình phù hợp. Không coi việc xóa file trong commit mới là đã xử lý xong sự cố.

## 11. Cách cấp secret bằng biến môi trường

Một mẫu đơn giản, thích hợp với nhiều nền tảng triển khai, là để Spring Boot nhận giá trị từ biến môi trường do runtime cung cấp.

File được commit:

~~~yaml
app:
  external-api:
    base-url: https://api.example.test
    timeout: 3s
    api-key: ${APP_EXTERNAL_APIKEY}
~~~

Runtime cần cung cấp `APP_EXTERNAL_APIKEY`. Cách nó được cấp nên đến từ hệ thống quản lý secret của nền tảng deploy, không từ một câu lệnh chứa key thật được lưu trong shell history hoặc job log.

Spring Boot có relaxed binding cho tên biến môi trường. Với key canonical `app.external-api.api-key`, tên biến tương ứng có thể là:

~~~text
APP_EXTERNAL_API_APIKEY
~~~

Ở đây cần phân biệt hai đường:

- Placeholder `${APP_EXTERNAL_APIKEY}`: đọc **chính xác property tên `APP_EXTERNAL_APIKEY`** được dùng trong placeholder.
- Relaxed binding trực tiếp cho `app.external-api.api-key`: chuyển tên canonical thành biến môi trường tương ứng, thường là `APP_EXTERNAL_API_APIKEY`.

Hai cách đặt tên **không tự đồng nhất** chỉ vì cùng muốn cấp một API key. Chọn một convention, ghi rõ trong deployment contract và kiểm thử. Ví dụ YAML trên đang dùng placeholder `APP_EXTERNAL_APIKEY`; nền tảng phải cấp đúng tên đó.

### Không coi environment variables là bí mật tuyệt đối

Environment variables giúp tách giá trị khỏi source repository nhưng có thể bị thấy bởi process có quyền thích hợp, dump, công cụ observability, màn hình quản trị deployment hoặc các lệnh debug. Giới hạn quyền truy cập runtime, tắt hành vi in toàn bộ environment và không xuất secret qua metric/log.

Với một số hệ thống, file-mounted secret có phân quyền chặt hoặc secret manager được truy xuất bằng workload identity phù hợp có thể giảm nguy cơ lộ qua shell/process arguments.

## 12. Dùng Config Data configtree cho file-mounted secret

Spring Boot hỗ trợ Config Data import từ **configuration tree**: mỗi file dưới một directory có thể cung cấp một property, với nội dung file là value của property.

Ví dụ một runtime mount thư mục:

~~~text
/run/secrets/
  app.external-api.api-key
  spring.datasource.password
~~~

Trong đó tên file đóng vai trò tên property, còn nội dung file (không minh họa secret thật ở đây) là giá trị tương ứng.

Có thể dùng:

~~~properties
# application.properties
spring.config.import=configtree:/run/secrets/
~~~

Khi khởi động và location có thể đọc được, Spring Boot đưa dữ liệu từ config tree vào hệ thống Config Data/Environment theo cơ chế tương ứng.

Với file:

~~~text
/run/secrets/app.external-api.api-key
~~~

code có thể bind:

~~~java
@ConfigurationProperties(prefix = "app.external-api")
public record ExternalApiProperties(String apiKey) {}
~~~

### optional: và môi trường production

Cho môi trường local không có mount, có thể gặp ví dụ:

~~~properties
spring.config.import=optional:configtree:/run/secrets/
~~~

`optional:` cho phép bỏ qua location không tồn tại theo quy tắc Config Data. Nhưng ở production, nếu secret là **bắt buộc**, việc đánh dấu optional thiếu suy nghĩ có thể che lỗi cấu hình. Hãy xác định rõ môi trường nào được phép thiếu mount, có validation bắt buộc và chính sách startup phù hợp.

### Quyền file và vòng đời

Config tree không tự làm nội dung file an toàn. Cần kiểm tra:

- Đường dẫn mount chỉ đọc được bởi process cần secret.
- Không mở secret volume cho container không liên quan.
- Quyền người dùng/nhóm và chế độ file phù hợp.
- Secret không bị copy vào image, artifact hoặc thư mục backup không kiểm soát.
- Cơ chế cập nhật file của nền tảng có thực sự dẫn tới ứng dụng nhận giá trị mới không.

Spring Boot Config Data thông thường được nạp lúc startup. Một file secret được rotate trên volume **không mặc nhiên khiến mọi bean `@ConfigurationProperties` tự rebind**.

## 13. Kubernetes Secret: hiểu đúng vai trò

Trong Kubernetes, `Secret` là API object dùng để chứa dữ liệu nhạy cảm và cấp cho workload thông qua env hoặc volume. Nó hữu ích nhưng không phải “két sắt tuyệt đối”.

**Base64 là encoding, không phải encryption.** Một manifest chứa:

~~~yaml
apiVersion: v1
kind: Secret
metadata:
  name: external-api
type: Opaque
data:
  api-key: <BASE64_VALUE_REDACTED>
~~~

không được coi là an toàn để commit chỉ vì giá trị trong `data` được encode. Người có quyền đọc manifest có thể giải mã lại.

Một container có thể tham chiếu Secret object đã được provision:

~~~yaml
env:
  - name: APP_EXTERNAL_APIKEY
    valueFrom:
      secretKeyRef:
        name: external-api
        key: api-key
~~~

Đây chỉ là fragment cấu hình container trong Pod/Deployment, không phải toàn bộ Kubernetes Deployment manifest. Nó không chứa secret value thật. Cần bảo vệ chính Secret object bằng RBAC, quản lý cách tạo/cập nhật, kiểm soát người có thể đọc env trong runtime và bật encryption at rest cho dữ liệu cluster khi phù hợp.

### Khi dùng volume mount

Có thể mount Secret thành file rồi dùng `configtree:/run/secrets/`. Cách này hữu ích khi muốn tránh đưa secret vào environment của process, nhưng file vẫn phải được phân quyền và các ứng dụng cần đọc nó an toàn.

Kubernetes có cơ chế cập nhật một số loại secret volume khi Secret thay đổi, nhưng **ứng dụng Spring Boot thường không tự refresh bean đã bind**. Với env variables, Pod/process thường cần khởi động lại để nhận giá trị mới. Đừng nhầm “volume file đã đổi” với “connection pool đã sử dụng credential mới”.

## 14. Secret manager tập trung: ranh giới trách nhiệm

Một hệ thống có thể dùng kho quản lý bí mật như HashiCorp Vault hoặc dịch vụ secret manager của cloud provider. Lợi ích có thể gồm:

- Phân quyền truy cập theo workload, môi trường và resource.
- Version/rotation và hỗ trợ thu hồi quyền.
- Audit truy xuất (tùy sản phẩm/cấu hình).
- Giảm số nơi lưu secret cố định.
- Phân tách identity của ứng dụng khỏi dữ liệu secret.
- Tích hợp CI/CD và orchestrator.

Tuy nhiên, **cách ứng dụng xác thực với secret manager cũng phải được bảo vệ**. Nếu cần một token vô hạn hardcoded trong source để lấy secret khác, rủi ro chỉ bị chuyển chỗ.

Các lựa chọn thường được cân nhắc là workload identity, service account với quyền tối thiểu, cơ chế cấp token ngắn hạn hoặc identity của nền tảng triển khai. Spring Boot có thể nhận dữ liệu được đưa vào Environment thông qua integration tương ứng hoặc qua file/env do nền tảng cung cấp.

**Không mặc định mọi ứng dụng Spring Boot tự hỗ trợ mọi secret manager mà không cần dependency và cấu hình tích hợp.** Chọn một integration thực sự phù hợp với stack và phiên bản đang dùng; tránh tự viết client lấy secret quá sớm gây vòng dependency khởi động.

## 15. Secrets trong database configuration

Một số thông số datasource thuộc nhóm bình thường hoặc nội bộ:

~~~properties
spring.datasource.url=jdbc:postgresql://db.internal.example.test:5432/orders
spring.datasource.username=orders_app
spring.datasource.hikari.maximum-pool-size=10
~~~

Trong khi:

~~~properties
spring.datasource.password=REDACTED_EXAMPLE_ONLY
~~~

là **secret** nếu chứa mật khẩu thật. Cách an toàn hơn là cấp value bên ngoài file được commit:

~~~properties
spring.datasource.password=${ORDERS_DB_PASSWORD}
~~~

Hoặc giữ file cấu hình chung không khai báo password rồi dùng environment binding hoặc config tree với tên property tương ứng.

### Tránh nhúng credential vào JDBC URL

Một URL có `user=...` hoặc `password=...` trong query/connection string có thể làm **cả URL trở nên nhạy cảm**. Khi log thông tin kết nối, không log JDBC URL nguyên văn nếu nó có thể chứa credential.

Đừng dùng API chung `toString()` của datasource config để debug. Với log cấu hình, nên chỉ hiển thị các thuộc tính đã được chọn lọc, ví dụ pool size không nhạy cảm, hoặc trạng thái “credential configured” mà không xuất giá trị.

## 16. OAuth2 client secret, JWT signing key và private key

Không phải mọi “token” có cùng vai trò, nhưng nhiều loại đều cần bảo vệ.

### OAuth client secret

~~~properties
spring.security.oauth2.client.registration.partner.client-id=public-id-example
spring.security.oauth2.client.registration.partner.client-secret=${PARTNER_OAUTH_CLIENT_SECRET}
~~~

`client-id` thường là identifier, không phải bí mật theo bản chất, nhưng có thể là nội bộ. `client-secret` là credential giúp client xác thực với authorization server và phải bảo vệ.

### JWT signing key

Nếu ứng dụng ký JWT bằng khóa đối xứng, việc lộ signing key có thể cho phép tạo chữ ký hợp lệ. Nó cần được quản lý như secret. Nếu dùng bất đối xứng, **private key** để ký là secret, còn public key có thể được phân phối cho bên xác minh theo thiết kế.

Đừng in key, PEM private content hoặc token còn hiệu lực vào log; không dùng “demo key” làm default production.

### Certificate không đồng nghĩa private key

File certificate công khai có thể được chia sẻ theo thiết kế TLS. Nhưng private key tương ứng **không được** đưa vào artifact công khai hoặc repository. Nếu một file keystore chứa cả private key và certificate, hãy phân loại toàn bộ file theo mức cần bảo vệ.

Ngay cả passphrase bảo vệ keystore cũng là secret; không hardcode nó vào cùng file được commit.

## 17. Không bỏ quên secret nằm trong chuỗi tổng hợp

Nhiều rò rỉ đến từ một property tưởng chừng không có tên secret:

~~~properties
app.partner.connection-string=...
app.partner.url=...
app.legacy.headers=...
app.proxy.url=...
app.callback.template=...
~~~

Những chuỗi này có thể mang:

- Username/password trong URL userinfo.
- Query parameter `api_key`, `token` hoặc `signature`.
- Authorization header hoặc cookie.
- DSN có credential.
- Presigned URL có chữ ký và thời hạn.
- Session identifier, reset password token hoặc một mật mã dùng một lần.

Ví dụ chuỗi dạng:

~~~text
https://user:REDACTED@example.test/path
https://example.test/download?signature=REDACTED
~~~

phải được xem là nhạy cảm dù key bao ngoài chỉ tên `endpoint` hoặc `url`.

**Quy tắc:** phân loại dựa trên **nội dung, công dụng và quyền mà value cấp**, không chỉ dựa trên regex tên property. Đừng cho phép log toàn bộ query string nếu nó có thể mang credential.

## 18. Cảnh giác log và exception

Một ví dụ nguy hiểm:

~~~java
log.info("Loaded external API config: {}", properties);
~~~

Nếu `properties` là record chứa `apiKey`, log có thể lộ secret.

Nguy hiểm tương tự:

~~~java
log.debug("Environment: {}", System.getenv());
log.info("API key: {}", apiKey);
log.error("Connection failed with properties {}", connectionOptions);
~~~

Hãy tránh in tràn lan Environment, system properties, header Authorization, cookies, connection options hoặc request/response body có credential.

### Log như thế nào cho hữu ích?

Một thông điệp có thể chỉ chứa trạng thái:

~~~java
log.info(
    "External API configured: endpointPresent={}, credentialPresent={}",
    properties.baseUrl() != null,
    properties.apiKey() != null
        && !properties.apiKey().isBlank()
);
~~~

Trong ví dụ, không log giá trị thật. Cũng không phải lúc nào trạng thái “có credential” được phép lộ ra công khai; log này vẫn là dữ liệu vận hành nội bộ. Với các trường rủi ro cao, chỉ log một mã trạng thái đã phân loại.

### Redaction phải áp dụng trước khi xuất

Khi hệ thống có structured logging, log appender, APM hoặc tracing, cần bảo đảm các field nhạy cảm được loại bỏ/mask **trước** khi gửi đi. Không dựa hoàn toàn vào một lớp lọc cuối pipeline, vì bản sao secret có thể đã xuất hiện ở stdout, agent, queue hoặc buffer.

Với một secret xuất hiện trong exception message từ thư viện, cần xử lý chính sách log exception an toàn. Không swallow mọi exception khiến mất khả năng chẩn đoán; hãy giữ loại lỗi, key/path và metadata cần thiết mà không làm lộ nội dung bí mật.

## 19. Spring Boot Actuator env và configprops

Spring Boot Actuator có các endpoint chẩn đoán như `env` và `configprops`. Chúng hữu ích để hiểu property sources và typed configuration, nhưng **có thể làm lộ thông tin môi trường nếu cấu hình truy cập sai**.

Không mở endpoint chẩn đoán cấu hình ra Internet công khai. Hãy bảo vệ bằng authentication, authorization, network restrictions và nguyên tắc chỉ cấp quyền cho người vận hành phù hợp.

Trong các phiên bản Spring Boot có hỗ trợ, các property như:

~~~properties
management.endpoint.env.show-values=never
management.endpoint.configprops.show-values=never
~~~

là một cách cấu hình không hiển thị giá trị qua hai endpoint này. Những giá trị lựa chọn khác như `when-authorized` hoặc `always` (khi phiên bản hỗ trợ) cần được cân nhắc rất kỹ, vì có thể mở rộng người có thể xem thông tin cấu hình. Cần tham khảo chính xác phiên bản Spring Boot đang chạy và security configuration.

### Masking không thay thế access control

Ngay cả khi giá trị được che, **tên key, profile, nguồn cấu hình, cấu trúc property hoặc origin** có thể tiết lộ chi tiết hạ tầng. Không coi mọi metadata trong Actuator là public.

Ngoài ra, việc Actuator mask value **không bảo vệ** giá trị secret nếu một controller riêng, log statement hoặc exception của thư viện khác đã xuất nó. Bảo vệ cần áp dụng tại mọi ranh giới.

## 20. Cẩn trọng với debug, heap dump và thread dump

Một secret được nạp thành `String` có thể tồn tại trong bộ nhớ JVM trong thời gian ứng dụng chạy. Một số công cụ chẩn đoán có quyền truy cập phù hợp có thể quan sát vùng nhớ hoặc thông tin process.

Những điểm cần chú ý:

- Heap dump có thể chứa object với password/token.
- Core dump hoặc crash artifact có thể chứa dữ liệu nhạy cảm.
- Process arguments có thể tiết lộ các giá trị truyền trực tiếp bằng `--key=value` hoặc `-Dkey=value`.
- Debugger và quyền attach vào JVM có thể truy cập thông tin runtime.
- APM/tracing đôi khi thu thập request headers hoặc parameters nếu không cấu hình lọc.
- File log và backup có thể lưu lại dữ liệu rất lâu sau khi request kết thúc.

Không có một kỹ thuật Java đơn lẻ loại bỏ hoàn toàn mọi bản sao secret khỏi bộ nhớ. Hãy giới hạn quyền vào server/process, kiểm soát retention và phân quyền đối với dump/log/artifact.

### Đừng truyền secret trong lệnh nếu có kênh tốt hơn

Ví dụ cú pháp:

~~~bash
java -Dapp.external-api.api-key=REDACTED -jar app.jar
~~~

là **minh họa một đường cấp property**, không phải khuyến nghị đưa token thật lên dòng lệnh. Trong môi trường hỗ trợ secret manager, file-mounted secret hoặc runtime injection có kiểm soát, ưu tiên kênh giảm exposure hơn.

## 21. Secret trong CI/CD và build pipeline

Một pipeline có thể cần credentials để triển khai hoặc kiểm thử tích hợp. Các rủi ro hay gặp:

- In env vars trong bước debug.
- Dùng lệnh shell có secret trong argument rồi log cả command.
- Ghi secret vào artifact, test report, cache hoặc workspace được tải xuống.
- Cấp credential production cho mọi branch hoặc pull request không tin cậy.
- Fork/untrusted code có thể chạy trong job có quyền đọc secret.
- Không thu hồi temporary credential sau khi job hoàn thành.
- Dùng một credential chung cho build, deploy và runtime, khiến quyền quá rộng.

### Một quy trình tốt hơn

1. Phân tách build/test với deployment job cần quyền bí mật.
2. Chỉ cấp secret vào job và môi trường thực sự cần.
3. Ưu tiên short-lived identity hoặc workload identity khi nền tảng hỗ trợ.
4. Không chạy untrusted code với credentials có quyền production.
5. Bật masking phù hợp nhưng không coi masking là biện pháp duy nhất.
6. Giảm thời gian sống của secret và retention của artifact.
7. Audit quyền truy xuất và hành vi job.

Với Docker build, tránh đặt secret trong `ARG`/`ENV` mà artifact hoặc layer có thể lưu. Nếu build thực sự cần credential để truy xuất dependency, cân nhắc cơ chế secret mount chuyên dụng của build system, không copy credential vào image.

## 22. Least privilege: secret không chỉ cần giấu, còn cần giới hạn quyền

Giả sử một API key chỉ cần đọc danh sách đơn hàng. Nếu bạn cấp cho nó quyền quản trị toàn hệ thống, việc giấu key vẫn không giảm được **mức độ thiệt hại khi key bị lộ**.

Nguyên tắc quyền tối thiểu:

- Credential chỉ có quyền gọi đúng API/operation.
- Database user chỉ có schema/table/permission cần thiết.
- Tách key đọc và key ghi nếu nghiệp vụ cho phép.
- Không dùng database superuser cho service thông thường.
- Tách môi trường development, staging và production.
- Tách credentials giữa các service/tenant khi phù hợp.
- Giới hạn quota, network policy, IP allowlist hoặc phạm vi sử dụng khi nền tảng hỗ trợ.
- Ưu tiên secret ngắn hạn hoặc có thể rotate.

Một hệ thống quản lý secret tốt không chỉ lưu “chuỗi bí mật”, mà còn cần quản lý **identity, authorization, audit và thu hồi quyền**.

## 23. Phân tách secret theo môi trường

Một lỗi thiết kế nguy hiểm là dùng cùng API key cho local development, test, staging và production. Khi đó máy laptop hoặc một pipeline thử nghiệm bị lộ có thể dẫn đến mất quyền kiểm soát production.

Một bảng policy minh họa:

| Môi trường | Giá trị cấu hình thông thường | Credential |
| --- | --- | --- |
| Local development | URL giả lập, timeout dev, cổng local | Credential dev/test riêng, quyền tối thiểu |
| CI unit test | Config test và mock | Không cần secret thật |
| Integration test | Endpoint sandbox | Secret sandbox được giới hạn |
| Staging | Endpoint staging | Credential staging, không dùng production |
| Production | Endpoint production | Credential production qua kênh kiểm soát chặt |

Có thể dùng Spring profiles để chọn **những giá trị thường khác nhau**:

~~~yaml
# application-dev.yml
app:
  external-api:
    base-url: https://sandbox.example.test
~~~

~~~yaml
# application-prod.yml
app:
  external-api:
    base-url: https://api.example.test
~~~

Nhưng không nên đặt credential thật trực tiếp vào `application-prod.yml` đã commit. Profile giúp lựa chọn Config Data, **không phải boundary bảo mật** và không tự mã hóa secret.

## 24. Phân loại theo vòng đời: static, short-lived, rotating

Không phải secret nào cũng có cùng vòng đời.

**Credential tĩnh:** password/long-lived API key có thể được lưu nhiều tháng. Cần rotation policy, giới hạn quyền và quy trình thu hồi.

**Credential ngắn hạn:** access token, session token hoặc temporary cloud credential có thời hạn ngắn. Cần cơ chế cấp phát và làm mới, không commit vào file.

**Khóa ký hoặc khóa mã hóa:** có ảnh hưởng đến dữ liệu đã được ký/mã hóa. Rotation phải cân nhắc key version, khả năng xác minh token cũ, giải mã dữ liệu lịch sử và thời gian chuyển tiếp.

**mTLS key/certificate:** key riêng là secret; certificate public có vòng đời hết hạn. Cần renewal policy và khả năng ứng dụng tải bộ key/certificate mới.

### Tại sao rotation không chỉ là đổi biến môi trường?

Spring Boot thường bind configuration properties khi khởi động. Nếu secret được thay ở secret store, ứng dụng có thể vẫn dùng instance cũ:

- HikariCP hoặc connection pool có thể giữ credential để tạo kết nối.
- HTTP client có thể giữ Authorization header/token provider.
- Bean immutable có thể giữ value đã bind.
- Pod env var có thể không đổi cho tới khi restart.
- Một số secret manager integration hỗ trợ refresh, nhưng phải được cấu hình và kiểm thử.

Thiết kế rotation cần xác định **khi nào consumer sử dụng credential mới** và **khi nào credential cũ bị thu hồi**, không chỉ thao tác cập nhật nơi lưu.

## 25. Quy trình rotation không làm gián đoạn dịch vụ

Một ví dụ khái quát cho API key có thể có giai đoạn chồng lấn:

1. Cấp secret mới với quyền tối thiểu.
2. Cập nhật secret manager hoặc deployment reference.
3. Khởi động lại/refresh những workload cần thiết theo khả năng của nền tảng.
4. Kiểm tra các request mới dùng key mới và thành công.
5. Thu hồi key cũ sau khi đảm bảo tất cả workload đã chuyển.
6. Ghi lại thời điểm và người thực hiện theo audit policy.
7. Xác nhận không còn key cũ ở pipeline, máy chủ hoặc backup dễ truy cập.

Quy trình thực tế phụ thuộc nhà cung cấp có hỗ trợ hai key đồng thời hay không. Nếu chỉ hỗ trợ một key hoạt động, cần một kế hoạch cutover khác để giảm downtime.

**Tránh log key thật trong bước xác nhận.** Có thể log key version hoặc identifier không nhạy cảm được hệ thống hỗ trợ, nhưng ngay cả metadata đó cũng cần được đánh giá trước khi hiển thị.

## 26. Khi nghi ngờ secret bị lộ: xử lý ưu tiên

Giả sử phát hiện một credential production trong commit, log, ticket hoặc screenshot. Đừng chỉ xóa dòng và coi là xong.

Quy trình xử lý tổng quát:

1. **Xác định phạm vi:** secret nào, quyền nào, thời gian có thể đã lộ, nơi bị sao chép.
2. **Kích hoạt xử lý sự cố** theo quy trình bảo mật của tổ chức.
3. **Thu hồi/xoay credential** càng sớm càng phù hợp với mức độ rủi ro và yêu cầu liên tục dịch vụ.
4. **Đánh giá khả năng bị lạm dụng** bằng audit logs, API usage và các dấu hiệu liên quan.
5. **Xóa hoặc hạn chế bản sao** trong Git, CI log, artifact, issue, chat, paste service, cache theo khả năng.
6. **Phát hành lại/cập nhật ứng dụng** để dùng credential mới.
7. **Cải thiện phòng ngừa:** secret scanning, controls và kiểm soát quyền truy cập.
8. **Báo cáo/đánh giá** theo chính sách nội bộ và nghĩa vụ liên quan.

Với Git, dọn lịch sử có thể cần đến bước rewrite history, nhưng hành động đó ảnh hưởng clone/fork và workflow của nhóm. **Việc xóa lịch sử không làm một credential lộ trở lại an toàn**: đổi/thu hồi credential vẫn là biện pháp trọng yếu.

Không đưa lại secret nguyên văn vào báo cáo sự cố, thông báo chat hoặc ví dụ tài liệu. Dùng ID/version và metadata đã được phân loại.

## 27. Cách kiểm tra repository và cấu hình một cách an toàn

Một nhóm phát triển có thể áp dụng secret scanning trong pre-commit, CI và giám sát repository. Những dấu hiệu gồm:

~~~text
api_key=
client_secret:
BEGIN PRIVATE KEY
Authorization: Bearer ...
password=...
jdbc:...password=...
~~~

Scanner có thể phát hiện nhiều mẫu nhưng cũng có false positive/false negative. Không suy ra “scanner pass nghĩa là repository không có secret”. Các giá trị được encode, chia thành nhiều mảnh hoặc nằm trong file binary có thể khó phát hiện.

Trong code review, nên hỏi:

- File chứa giá trị thật hay chỉ placeholder?
- Có credential production được đưa vào sample/test data không?
- Example URI có query token không?
- Docker image hoặc pipeline có in `env`/system properties không?
- Bean properties có `toString()` mặc định và được log không?
- CI artifact và backup có thể chứa secret không?
- Config tree/secret mount có bị quyền đọc quá rộng không?

Không bắt developer copy secret thật vào pull request để chứng minh cấu hình hoạt động. Có thể dùng secret giả và integration test có quyền phù hợp.

## 28. Test mà không cần production secrets

Một unit test của service nên nhận đối tượng cấu hình dùng giá trị giả, ví dụ:

~~~java
import java.net.URI;
import java.time.Duration;

ExternalApiProperties properties = new ExternalApiProperties(
    URI.create("https://api.example.test"),
    Duration.ofSeconds(1),
    "fake-test-credential-not-valid"
);
~~~

Đây là giá trị giả, không phải secret có khả năng truy cập hệ thống. Test logic bằng mock HTTP client hoặc fake server khi phù hợp.

Để kiểm Spring Boot binding:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest(properties = {
    "app.external-api.base-url=https://api.example.test",
    "app.external-api.timeout=2s",
    "app.external-api.api-key=fake-test-credential-not-valid"
})
class ExternalApiPropertiesTest {

    @Autowired
    ExternalApiProperties properties;

    @Test
    void bindsConfiguredValues() {
        assertThat(properties.baseUrl().getHost())
            .isEqualTo("api.example.test");
        assertThat(properties.timeout().toSeconds()).isEqualTo(2);
        assertThat(properties.apiKey()).isNotBlank();
    }
}
~~~

Test giả định `ExternalApiProperties` được scan/enable đúng cách và project có dependencies cần thiết. Mục tiêu là kiểm typed binding, **không cần gọi API provider với credential thật**.

### Kiểm fail-fast khi secret thiếu

Có thể tạo một test context không cấp `app.external-api.api-key` và xác nhận startup thất bại vì constraint `@NotBlank` khi Bean Validation được bật và model đã được đăng ký. Với integration test dùng `@SpringBootTest`, việc fail cả context có thể xảy ra trước test method; `ApplicationContextRunner` thường thuận tiện hơn để assert startup failure.

Nếu `application.yml` có placeholder bắt buộc mà test không cấp biến, việc fail có thể đến từ placeholder resolution trước khi Bean Validation chạy. Cần phân biệt nguyên nhân trong test thay vì mặc định mọi lỗi thiếu secret đều là `@NotBlank`.

## 29. Chính sách default: dữ liệu thường và secret khác nhau

Một cấu hình thông thường có thể có default an toàn:

~~~yaml
app:
  client:
    timeout: 3s
    max-retries: 2
~~~

Nhưng credential production thường không nên có default dùng chung:

~~~yaml
app:
  external-api:
    api-key: ${APP_EXTERNAL_APIKEY}
~~~

Một số bài test có thể dùng credential giả cố định trong test scope, nhưng credential giả **không được có quyền truy cập production**.

### Vì sao default bí mật nguy hiểm?

- Che việc deployment chưa cấu hình.
- Khuyến khích dùng cùng credential giữa các môi trường.
- Một “demo password” có thể bị đưa vào production.
- Khó rotate và thu hồi vì nhiều workload dùng chung.
- Một default hardcoded trong thư viện có thể bị trích xuất từ artifact.

**Quy tắc:** thông số hoạt động có thể có default nếu an toàn; secret bắt buộc nên được cấp từ môi trường phù hợp và được validate. Không nên “fail open” vì thiếu credential.

## 30. Masking và redaction: có giới hạn

Giả sử log cần ghi một tên property:

~~~text
app.external-api.api-key = [REDACTED]
~~~

Che value bằng `[REDACTED]` hữu ích, nhưng phải cẩn thận:

- Một value có thể xuất hiện nhiều lần ở các field khác.
- Secret có thể nằm trong URL, stack trace hoặc header chứ không ở field tên `api-key`.
- Một số library log request body hoặc error details.
- Base64/URL encoding làm regex nhận diện khó hơn.
- Một log đã được xuất trước khi masking bật không tự biến mất.
- Một phần token bị lộ cũng có thể hỗ trợ correlation hoặc tấn công trong một số hệ thống.

Nên áp dụng chính sách **allowlist trường được log** thay vì log tất cả rồi cố che các key có tên nhạy cảm. Redaction regex là lớp phòng vệ bổ sung, không phải toàn bộ chiến lược.

Đặc biệt cẩn trọng khi định dạng:

~~~java
log.info("Configuration: {}", properties);
~~~

vì một record/Lombok-generated `toString()` có thể in nhiều trường bí mật mà người viết log không để ý.

## 31. Cách phân loại configuration tree và cấu trúc file

Một dự án có thể tách:

~~~text
src/main/resources/
  application.yml
  application-dev.yml
  application-prod.yml

external runtime:
  /run/secrets/
    spring.datasource.password
    app.external-api.api-key
~~~

Phân loại:

- `application.yml`: thiết lập chung, tên property, timeout, không chứa secret thật.
- `application-dev.yml`: endpoint local/sandbox, không chứa credential thật trong Git.
- `application-prod.yml`: thiết lập non-secret cho production hoặc placeholder theo deployment contract.
- `/run/secrets`: dữ liệu bí mật do runtime/secret manager mount, được phân quyền.
- CI/CD: chịu trách nhiệm cấp reference và quyền sử dụng, không công khai value.

Một nguồn external secret có thể là file, environment hoặc dịch vụ; cấu trúc trên là một ví dụ chứ không phải yêu cầu mọi ứng dụng đều dùng `/run/secrets`.

### Không gắn secret vào tên file/đường dẫn

Tránh đặt credential trong filename hoặc directory name như:

~~~text
/run/secrets/token-realvalue-...
~~~

Tên file có thể bị log hoặc hiển thị trong chẩn đoán. Nên dùng **tên property ổn định, không chứa secret content**. Nếu cần versioning, dùng metadata/version ID không nhạy cảm theo thiết kế.

## 32. Bảo vệ quyền truy cập trong code và runtime

Secret cần tồn tại tại nơi ứng dụng có thể sử dụng, nhưng không có nghĩa mọi component trong cùng ứng dụng đều cần đọc nó.

Gợi ý thiết kế:

- Chỉ những bean client cần credential mới inject typed credentials/config.
- Không đưa object credential vào DTO trả về controller.
- Không serialize `@ConfigurationProperties` chứa secret thành JSON debug endpoint.
- Không truyền credential xuyên các tầng không cần biết.
- Không dùng secret làm message queue payload hoặc event.
- Không đặt secret vào metric label hoặc tracing attribute.
- Không lộ secret qua error response cho người dùng.
- Hạn chế quyền OS/container của process và quyền đọc mount.
- Kiểm soát diagnostic endpoints, heap dumps và quyền attach debugger.

Trong cùng một JVM, việc tách bean **không phải isolation bảo mật tuyệt đối**; code có quyền cao trong cùng process vẫn có thể truy cập memory hoặc context. Nhưng dependency boundaries rõ ràng giúp giảm sử dụng nhầm và giảm nơi secret bị sao chép.

## 33. Dữ liệu nhạy cảm không phải credential vẫn cần kiểm soát

Một mục cấu hình có thể là:

~~~properties
app.billing.customer-tenant-id=tenant-demo
app.ops.internal-runbook-url=https://internal.example.test/runbook
app.feature.unannounced-pricing-enabled=false
~~~

Các giá trị này có thể không cho phép authentication trực tiếp. Tuy nhiên, chúng có thể tiết lộ dữ liệu khách hàng, quy trình vận hành hoặc kế hoạch kinh doanh.

Không nên ép mọi giá trị như vậy vào secret store chỉ vì “nội bộ”; chọn mức bảo vệ dựa vào rủi ro, chính sách và đường phân phối. Ví dụ, một feature flag nội bộ có thể nằm trong config repository riêng với RBAC; một customer identifier có thể phải xử lý theo chính sách dữ liệu cá nhân.

**Phân loại giúp phân biệt mục đích bảo vệ:**
- Bảo vệ **quyền truy cập** (credential).
- Bảo vệ **tính riêng tư** (PII).
- Bảo vệ **bí mật kinh doanh** (nội dung nội bộ).
- Bảo vệ **tính toàn vẹn của cấu hình** (setting thay đổi có thể làm hệ thống không an toàn).

Ngay cả `logging.level` hoặc `security.enabled` không phải secret, nhưng việc thay đổi chúng có thể nguy hiểm. Đó là lý do cần change control riêng cho **giá trị không bí mật nhưng có tác động bảo mật lớn**.

## 34. Kiểm soát tính toàn vẹn của cấu hình

Câu hỏi “giá trị này có phải secret không?” khác với “ai được phép thay đổi giá trị này?”.

Ví dụ:

~~~properties
management.endpoints.web.exposure.include=health
app.security.enforce-mfa=true
app.rate-limit.enabled=true
~~~

Các setting trên không nhất thiết là secret. Nhưng thay đổi chúng có thể tác động đến surface tấn công hoặc khả năng phòng vệ.

Vì vậy, ngay cả cấu hình thường cũng có thể cần:

- Code review/approval trước khi thay đổi.
- Git protection và lịch sử thay đổi.
- Deployment promotion qua môi trường.
- Kiểm tra schema/validation.
- Audit thay đổi và rollback có kiểm soát.
- Phân quyền cập nhật production.

**Phân loại mức bí mật và phân loại mức quan trọng đối với tính toàn vẹn là hai trục khác nhau**. Một setting không bí mật vẫn có thể cần kiểm soát thay đổi nghiêm ngặt.

## 35. Các lỗi thường gặp và nguyên nhân

| Hiện tượng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| Secret xuất hiện trong Git | Commit giá trị thật vào YAML/.env | Rotate/revoke, xử lý lịch sử và nâng kiểm soát |
| App chạy local nhưng fail production vì thiếu key | Deployment không cấp secret hoặc sai tên biến | Kiểm runtime contract, fail fast |
| App dùng sai credential dù file đúng | Một env/CLI/Config Data source khác ghi đè | Kiểm precedence và nguồn hiệu lực, không in value |
| Log có token | Ghi nguyên config, headers, request body, toString() | Giảm dữ liệu log, redaction và xử lý bản sao |
| Actuator phơi lộ cấu hình | Endpoint mở rộng truy cập hoặc show-values | Restrict access, cấu hình masking |
| File mount thay nhưng app vẫn dùng key cũ | Bean/connection client không refresh | Thiết kế restart/rebind/rotation |
| Kubernetes Secret có base64 bị tưởng là encrypted | Nhầm encoding với encryption | RBAC, encryption at rest, giới hạn truy cập |
| API key dùng chung mọi môi trường | Không tách dev/staging/prod | Tách scope và cấp phát theo environment |
| Secret có quyền admin | Không áp dụng least privilege | Hạ quyền và rotate credential |
| CI upload artifact chứa secret | Script/log/cache hoặc build layer giữ value | Giảm scope, xóa/thu hồi, kiểm pipeline |
| Một URL tưởng thường lại chứa query token | Phân loại theo tên key thay vì nội dung | Bảo vệ toàn bộ URL và bỏ credential khỏi URL nếu có thể |
| Test cần credential production | Test chưa mock hoặc thiếu sandbox identity | Dùng fake, mock hoặc sandbox secret riêng |

Để chẩn đoán, cần phân biệt **lỗi cung cấp secret**, **lỗi cấp quyền**, **lỗi chuyển đổi/binding** và **lỗi sử dụng credential tại provider**. Một secret có mặt nhưng không hợp lệ hoặc đã bị thu hồi có thể làm API trả 401/403; đó không nhất thiết là lỗi Spring Boot Binder.

## 36. Quy trình thực hiện trong một dự án Spring Boot

Một workflow tham khảo:

1. **Liệt kê property contracts** của service: key, loại dữ liệu, môi trường, người sở hữu.
2. **Phân loại** thành public/internal/confidential/secret theo rủi ro thực tế.
3. **Xác định nơi cấp giá trị**: code repository cho normal config; secret manager/runtime injection cho secret.
4. **Không commit giá trị bí mật**. Chỉ lưu tên key/placeholder/sample giả.
5. **Thiết kế typed config** với `@ConfigurationProperties`, validation cho key bắt buộc, và không log object chứa secret.
6. **Giới hạn quyền** truy xuất secret store và tài nguyên mà credential cho phép sử dụng.
7. **Bảo vệ observability**: log allowlist, masking, Actuator, tracing, dumps và artifact.
8. **Test** với fake/sandbox credentials, xác nhận fail-fast khi thiếu.
9. **Xác định cách rotate**: cách cập nhật, restart/refresh, giai đoạn chồng lấn và thu hồi.
10. **Giám sát và xử lý rò rỉ**: secret scanning, audit, incident response.
11. **Kiểm soát thay đổi** đối với setting thường nhưng có tác động bảo mật.
12. **Cập nhật tài liệu triển khai** bằng tên biến/key và policy, không đăng giá trị thật.

Đây là quy trình bảo vệ xuyên vòng đời, thay vì chỉ thay đổi một file `application.properties`.

## 37. Bài tập phân loại

### Bài 1 — server.port

~~~properties
server.port=8080
~~~

**Hỏi:** đây có phải secret?

**Đáp án:** thường không. Nó là thông số vận hành. Dù vậy, việc thay đổi cổng có thể cần kiểm soát theo chính sách deployment.

### Bài 2 — URL có token

~~~properties
app.partner.url=https://api.example.test/items?token=REDACTED
~~~

**Hỏi:** có thể log URL nguyên văn vì tên key là `url` không?

**Đáp án:** không. URL có token nên phải bảo vệ toàn value hoặc thiết kế bỏ credential khỏi URL theo API phù hợp.

### Bài 3 — database username và password

~~~properties
spring.datasource.username=orders_app
spring.datasource.password=REDACTED
~~~

**Đáp án:** password là secret. Username thường là identifier/nội bộ nhưng không nên tự coi là public trong mọi bối cảnh.

### Bài 4 — public certificate và private key

Có một file PEM chứa public certificate và một file PEM chứa private key tương ứng.

**Đáp án:** public certificate thường có thể phân phối theo thiết kế TLS; private key là secret. Nếu đóng gói cả hai trong keystore, keystore phải được bảo vệ tương ứng.

### Bài 5 — feature flag

~~~properties
app.feature.unannounced-pricing-enabled=true
~~~

**Đáp án:** không nhất thiết là authentication secret. Nhưng có thể là thông tin nội bộ nhạy cảm và cần quyền truy cập, change control.

### Bài 6 — biến môi trường

Runtime cấp `APP_EXTERNAL_APIKEY`. **Hỏi:** value đã an toàn tuyệt đối chưa?

**Đáp án:** chưa. Nó không nằm trong Git, nhưng vẫn có thể bị lộ qua process inspection, log, dump hoặc công cụ deployment có quyền. Cần giới hạn quyền và bảo vệ các điểm trung gian.

### Bài 7 — secret trong Git

Một API key thật đã được commit hôm qua, hôm nay developer xóa dòng đó.

**Đáp án:** chưa xử lý xong. Cần đánh giá sự cố, thu hồi/rotate key, kiểm bản sao và lịch sử, rồi cải thiện kiểm soát.

### Bài 8 — Kubernetes data field

Một Secret manifest chứa `data.api-key` bằng base64. **Hỏi:** có thể commit public vì “đã mã hóa” không?

**Đáp án:** không. Base64 chỉ là encoding; nó không ngăn người đọc giải mã lại secret.

### Bài 9 — record toString

Một record `ExternalApiProperties(String apiKey)` được in vào log dưới dạng `log.info("{}", props)`.

**Đáp án:** có nguy cơ in plaintext key từ `toString()` mặc định. Không log object; thay bằng thông tin trạng thái đã chọn lọc.

### Bài 10 — rotation

Secret store đã cập nhật password database, nhưng HikariCP vẫn dùng credential cũ.

**Đáp án:** cập nhật nơi lưu không bảo đảm pool/bean cập nhật tự động. Phải có thiết kế refresh/restart/recreate connection pool theo cách triển khai.

### Bài 11 — application-prod.yml

File production chứa host database, timeout và password.

**Đáp án:** host/timeout có thể là non-secret hoặc nội bộ tùy bối cảnh; password là secret và không nên commit. Có thể giữ host/timeout trong Config Data phù hợp, password được cấp ở runtime.

### Bài 12 — setting bảo mật

~~~properties
app.security.enforce-mfa=false
~~~

**Đáp án:** bản thân value boolean không phải secret, nhưng thay đổi nó có rủi ro lớn đến tính toàn vẹn của cấu hình. Cần review/approval, không chỉ giấu value.

## 38. Checklist cuối bài

| Câu hỏi | Điều cần kiểm |
| --- | --- |
| Value có trực tiếp xác thực, ký hoặc giải mã không? | Phân loại là secret |
| Value chỉ là địa chỉ/identifier? | Xét bối cảnh nhạy cảm và rủi ro kết hợp |
| Một URL/DSN có credential nhúng không? | Bảo vệ toàn value |
| Secret có nằm trong Git/source/artifact không? | Loại bỏ an toàn, rotate nếu đã lộ |
| Có placeholder nhưng runtime thiếu value? | Có validation/fail-fast rõ |
| Env/CLI có thể bị log/process listing không? | Giảm exposure và quyền truy cập |
| Config tree mount có permission đúng không? | Kiểm file/volume access |
| Kubernetes Secret có RBAC và at-rest protection không? | Không nhầm base64 là encryption |
| Secret manager có workload identity phù hợp không? | Không hardcode credential để lấy credential khác |
| Bean config có toString/log secret không? | Không in object chứa secret |
| Actuator env/configprops có được bảo vệ không? | Giới hạn exposure, show-values, authorization |
| CI có log environment hoặc artifact chứa key không? | Giảm secret scope và retention |
| Secret có quyền tối thiểu và phân tách môi trường không? | RBAC/scope/dev-staging-prod |
| Đã có rotation và incident response chưa? | Khả năng thu hồi và cập nhật consumer |
| Test có dùng fake/sandbox secret không? | Tránh production credential trong unit tests |
| Setting không bí mật nhưng có tác động bảo mật? | Change control và kiểm tính toàn vẹn |

## 39. Kết luận

Spring Boot Externalized Configuration là cơ chế cung cấp và bind key/value; **nó không tự biến mọi giá trị thành dữ liệu được bảo vệ**. Phân loại đúng giúp xác định cách lưu trữ, phân quyền, ghi log, cấp phát và thu hồi giá trị.

Có thể ghi nhớ ba nhóm quyết định:

1. **Cấu hình thường:** cổng, timeout, mức retry, tên service, endpoint công khai — có thể version-control nếu không chứa thông tin nhạy cảm và đáp ứng chính sách.
2. **Cấu hình nội bộ/nhạy cảm:** hostname riêng, customer identifier, feature flag chưa công bố, thông tin vận hành — kiểm soát truy cập và phân phối theo bối cảnh.
3. **Secret:** password, API token, private key, client secret, signing/encryption key — không hardcode/commit, cấp qua kênh được kiểm soát, giới hạn quyền, mask trong observability và có kế hoạch rotation.

**Phân loại không phải chỉ nhìn tên key.** Phải xét **nội dung thực tế, quyền truy cập mà value cấp, khả năng kết hợp với dữ liệu khác và hậu quả khi lộ**. Một dự án an toàn vừa giữ secret ngoài source, vừa giới hạn quyền khi sử dụng, vừa không cho secret bị sao chép qua log/Actuator/CI/artifact, đồng thời kiểm soát thay đổi của các setting bình thường có tác động đến bảo mật.
