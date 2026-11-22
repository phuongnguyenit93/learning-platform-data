# Biến thể theo profile của tệp được import trong Spring Boot

Spring Boot hỗ trợ nạp cấu hình từ tệp khác bằng thuộc tính `spring.config.import`. Khi profile được kích hoạt, Spring Boot không chỉ xem xét tệp được import theo đúng tên đã khai báo mà còn **tự động xem xét các biến thể theo profile** của tệp đó, nếu chúng tồn tại và phù hợp.

Ví dụ, một import tới `file:./config/payment.yml` có thể dẫn tới việc nạp thêm `file:./config/payment-prod.yml` khi profile `prod` hoạt động. Đây là một phần của hệ thống **Config Data** trong Spring Boot, giúp tách cấu hình chung khỏi cấu hình theo môi trường mà không phải viết một dòng import riêng cho từng profile.

Bài học sử dụng Spring Boot 3.3.x và Java 21; trọng tâm là cơ chế tìm biến thể profile, giá trị hiệu lực, thứ tự ưu tiên và cách tổ chức tệp thực tế.

## 1. Ôn lại `spring.config.import`

Trong `src/main/resources/application.yml`, có thể khai báo:

~~~yaml
spring:
  config:
    import: "optional:file:./config/payment.yml"
~~~

Ý nghĩa:

- `spring.config.import` yêu cầu Spring Boot nạp một tài nguyên cấu hình khác trong quá trình xử lý Config Data.
- `file:./config/payment.yml` là đường dẫn hệ thống tệp, được phân giải dựa trên **working directory** của tiến trình.
- `optional:` cho phép bỏ qua location được khai báo nếu nó không tồn tại. Nếu cấu hình là bắt buộc, bỏ tiền tố này để Spring Boot báo lỗi khi thiếu.
- Khi tệp import có giá trị trùng khóa với document khai báo import, tài liệu được import có thể **ghi đè** giá trị trong document khai báo import theo quy tắc ưu tiên Config Data.
- Import này được xử lý lúc ứng dụng khởi động, không phải thao tác tải file mỗi lần có request.

Ví dụ trong file chính:

~~~yaml
spring:
  config:
    import: "file:./config/payment.yml"

app:
  payment:
    timeout: 2s
    mode: packaged
~~~

Và tệp `config/payment.yml`:

~~~yaml
app:
  payment:
    timeout: 5s
    mode: imported
~~~

Nếu không có nguồn ưu tiên cao hơn ghi đè, giá trị hiệu lực là `app.payment.timeout=5s` và `app.payment.mode=imported`. Vị trí của dòng import trong cùng document không phải công tắc xác định nó có ưu tiên hay không; Spring Boot xử lý imported document theo cơ chế Config Data.

## 2. Profile-specific variant là gì?

Một *profile-specific variant* là phiên bản cấu hình có hậu tố tên profile ngay trước phần mở rộng tệp:

| Tệp được import | Profile hoạt động | Biến thể có thể được xem xét |
| --- | --- | --- |
| `payment.yml` | `dev` | `payment-dev.yml` |
| `payment.yml` | `prod` | `payment-prod.yml` |
| `payment.yaml` | `staging` | `payment-staging.yaml` |
| `payment.properties` | `test` | `payment-test.properties` |
| `feature.yml` | `dev,prod` | `feature-dev.yml`, `feature-prod.yml` |

Đây là quy tắc áp dụng cho **tài nguyên được import**, không chỉ các tệp mặc định tên `application.yml`. Phần tên cơ sở giữ nguyên, thêm dấu gạch ngang và tên profile trước extension.

Ví dụ:

~~~text
config/
├── payment.yml
├── payment-dev.yml
├── payment-test.yml
└── payment-prod.yml
~~~

Nếu có cấu hình import:

~~~yaml
spring:
  config:
    import: "file:./config/payment.yml"
~~~

thì:

- Không bật profile `dev`/`test`/`prod`: dùng nội dung `payment.yml` làm cấu hình chung.
- Bật `dev`: Spring Boot xem xét `payment.yml` và `payment-dev.yml`.
- Bật `prod`: Spring Boot xem xét `payment.yml` và `payment-prod.yml`.
- Không có `payment-staging.yml` thì không có nội dung riêng từ biến thể đó; tệp chung vẫn có thể cung cấp cấu hình khi profile `staging` hoạt động.

Profile thực tế được xác định bởi Spring `Environment`, có thể kích hoạt qua `spring.profiles.active`, biến môi trường hoặc nguồn cấu hình khác. Nếu không profile nào được đặt, Spring Boot thường dùng profile mặc định có tên `default`; tệp dạng `payment-default.yml` có thể được xem xét theo cơ chế profile-specific tương ứng.

## 3. Ví dụ đầy đủ: tệp import chung, dev và prod

Giả sử ứng dụng có cấu trúc:

~~~text
catalog-app/
├── build/libs/catalog-app.jar
├── config/
│   ├── payment.yml
│   ├── payment-dev.yml
│   └── payment-prod.yml
└── src/main/resources/
    └── application.yml
~~~

### 3.1. File `application.yml` trong ứng dụng

~~~yaml
spring:
  application:
    name: catalog-app
  config:
    import: "file:./config/payment.yml"

server:
  port: 8080

app:
  payment:
    mode: application-default
    retry-count: 2
    timeout: 3s
~~~

Chỉ có **một** lệnh import, chỉ rõ tệp `payment.yml`. Không cần viết thêm import tới `payment-dev.yml` hoặc `payment-prod.yml`.

### 3.2. File `config/payment.yml`: cấu hình chung

~~~yaml
app:
  payment:
    mode: standard
    retry-count: 3
    timeout: 5s
    provider: sandbox
~~~

### 3.3. File `config/payment-dev.yml`: ghi đè cho dev

~~~yaml
app:
  payment:
    mode: debug
    timeout: 15s
    provider: mock
~~~

### 3.4. File `config/payment-prod.yml`: ghi đè cho prod

~~~yaml
app:
  payment:
    mode: live
    retry-count: 5
    provider: production
~~~

Khi khởi động, cấu hình ứng dụng và các tài liệu được import kết hợp với nhau theo quy tắc thứ tự ưu tiên. Khóa không được khai báo lại vẫn có thể lấy từ một nguồn đã được nạp trước đó; khóa có mặt ở biến thể profile phù hợp sẽ ghi đè bản chung khi chúng cùng áp dụng.

### 3.5. Kết quả dự kiến với các profile

| Thuộc tính | Không kích hoạt profile riêng | `dev` | `prod` |
| --- | --- | --- | --- |
| `app.payment.mode` | `standard` | `debug` | `live` |
| `app.payment.retry-count` | `3` | `3` | `5` |
| `app.payment.timeout` | `5s` | `15s` | `5s` |
| `app.payment.provider` | `sandbox` | `mock` | `production` |

Lý do:

- Các giá trị `mode`, `retry-count`, `timeout` từ file chung `payment.yml` ghi đè các giá trị tương ứng trong document `application.yml` khai báo import.
- Với `dev`, `payment-dev.yml` chỉ thay `mode`, `timeout` và `provider`; `retry-count` vẫn lấy từ `payment.yml`.
- Với `prod`, `payment-prod.yml` thay `mode`, `retry-count` và `provider`; `timeout` vẫn lấy từ `payment.yml`.
- Khi profile không có biến thể tương ứng, chỉ các nguồn khác đang có hiệu lực quyết định giá trị.

Bảng giả định không có biến môi trường, Java system property, CLI argument, import khác hoặc test property ghi đè các khóa trong ví dụ.

## 4. Kích hoạt profile để Spring Boot chọn biến thể

### 4.1. Qua tham số dòng lệnh

Chạy dev:

~~~bash
java -jar build/libs/catalog-app.jar --spring.profiles.active=dev
~~~

Chạy prod:

~~~bash
java -jar build/libs/catalog-app.jar --spring.profiles.active=prod
~~~

Không truyền `spring.profiles.active` nếu muốn quan sát cấu hình không có profile riêng đang hoạt động.

### 4.2. Qua biến môi trường

Linux/macOS:

~~~bash
export SPRING_PROFILES_ACTIVE=prod
java -jar build/libs/catalog-app.jar
~~~

Windows PowerShell:

~~~powershell
$env:SPRING_PROFILES_ACTIVE = 'dev'
java -jar build/libs/catalog-app.jar
~~~

### 4.3. Qua Java system property

~~~bash
java -Dspring.profiles.active=prod -jar build/libs/catalog-app.jar
~~~

Giữa các nguồn khai báo profile hoặc thuộc tính ứng dụng, Spring Boot vẫn áp dụng thứ tự ưu tiên PropertySource thông thường. Ví dụ, `--app.payment.mode=manual` có thể ghi đè giá trị `live` từ file prod. Profile quyết định **những tài liệu nào được áp dụng**; thứ tự ưu tiên quyết định **giá trị cuối cùng** khi nhiều tài liệu cùng cung cấp một khóa.

## 5. Minh họa bằng Java và `Environment`

Một ứng dụng Spring Boot nhỏ có thể quan sát giá trị nạp từ các file như sau:

~~~java
package com.example.catalog;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;

import java.util.Arrays;

@SpringBootApplication
public class CatalogApplication {

    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }

    @Bean
    ApplicationRunner showPaymentConfig(Environment env) {
        return (ApplicationArguments args) -> {
            System.out.println("activeProfiles="
                    + Arrays.toString(env.getActiveProfiles()));
            System.out.println("mode="
                    + env.getProperty("app.payment.mode"));
            System.out.println("retry-count="
                    + env.getProperty("app.payment.retry-count", Integer.class));
            System.out.println("timeout="
                    + env.getProperty("app.payment.timeout"));
            System.out.println("provider="
                    + env.getProperty("app.payment.provider"));
        };
    }
}
~~~

Để chạy ví dụ, thêm `spring-boot-starter` (và các dependency tương ứng với ứng dụng thực tế) vào dự án. Nếu sử dụng `spring-boot-starter-web`, thuộc tính `server.port` mới có tác dụng điều khiển cổng máy chủ HTTP.

Khi chạy:

~~~bash
java -jar build/libs/catalog-app.jar --spring.profiles.active=dev
~~~

kết quả phần cấu hình có thể giống:

~~~text
activeProfiles=[dev]
mode=debug
retry-count=3
timeout=15s
provider=mock
~~~

Chạy với `--spring.profiles.active=prod`:

~~~text
activeProfiles=[prod]
mode=live
retry-count=5
timeout=5s
provider=production
~~~

`Environment` biểu diễn giá trị thuộc tính hiệu lực. Đọc từng khóa bằng `getProperty` là cách quan sát cấu hình sau khi các nguồn được tổng hợp và ghi đè.

## 6. Bind các cấu hình được import bằng `@ConfigurationProperties`

Khi số khóa tăng lên, sử dụng binding kiểu an toàn thay vì gọi `Environment.getProperty` ở nhiều nơi.

Với nội dung YAML tại mục 3:

~~~java
package com.example.catalog;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.payment")
public record PaymentProperties(
        String mode,
        int retryCount,
        Duration timeout,
        String provider) {
}
~~~

Trong ứng dụng chính, bật quét bean cấu hình:

~~~java
@SpringBootApplication
@ConfigurationPropertiesScan
public class CatalogApplication {
    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
~~~

Cần import `org.springframework.boot.context.properties.ConfigurationPropertiesScan` và các class Spring Boot tương ứng. Vì đây là mã minh họa trích phần, hãy giữ package và các import hợp lệ theo dự án.

Một bean sử dụng cấu hình:

~~~java
@Component
class PaymentPrinter implements ApplicationRunner {

    private final PaymentProperties properties;

    PaymentPrinter(PaymentProperties properties) {
        this.properties = properties;
    }

    @Override
    public void run(ApplicationArguments args) {
        System.out.println(properties.mode());
        System.out.println(properties.retryCount());
        System.out.println(properties.timeout());
        System.out.println(properties.provider());
    }
}
~~~

Cần import `org.springframework.stereotype.Component`, `org.springframework.boot.ApplicationRunner` và `org.springframework.boot.ApplicationArguments`. Các tên `retry-count` trong YAML được bind vào `retryCount` theo cơ chế *relaxed binding*, còn `5s` hay `15s` được chuyển thành `Duration`.

**Điểm quan trọng:** `@ConfigurationProperties` không cần biết tệp cụ thể đến từ `payment.yml` hay `payment-prod.yml`. Binder chỉ quan tâm giá trị cuối cùng đã có trong `Environment`.

## 7. Spring Boot xác định biến thể của *file được import*, không chỉ của `application.yml`

Một hiểu nhầm thường gặp là Spring Boot tự động đọc `application-prod.yml` nhưng không làm tương tự với các tài nguyên import có tên khác. Trên thực tế, khi Config Data import một tài nguyên hỗ trợ profile-specific variants, những biến thể của tài nguyên ấy **cũng được xét**.

Ví dụ:

~~~yaml
spring:
  config:
    import:
      - "file:./config/inventory.properties"
      - "file:./config/payment.yml"
~~~

Khi `prod` hoạt động, ngoài hai tài nguyên gốc, Spring Boot còn có thể xét:

~~~text
config/inventory-prod.properties
config/payment-prod.yml
~~~

Không cần chỉ rõ hai biến thể này trong danh sách import. Mỗi biến thể theo profile áp dụng các giá trị của mình theo thứ tự Config Data. Việc có cùng tên `application` là không bắt buộc.

Lưu ý phân biệt với `spring.config.name`: thuộc tính đó điều khiển tên cấu hình được dò ở các *config location* thông thường; còn `spring.config.import` nêu tài nguyên cần import. Nếu đã import đích danh `payment.yml`, không phải đổi `spring.config.name` để Spring Boot nhận ra `payment-prod.yml`.

## 8. Dùng `spring.config.import` trong document chỉ hoạt động theo profile

Có thể đặt import trong một document YAML chỉ được áp dụng khi điều kiện profile phù hợp. Ví dụ `application.yml`:

~~~yaml
spring:
  application:
    name: catalog-app

app:
  payment:
    mode: basic

---
spring:
  config:
    activate:
      on-profile: dev
    import: "optional:file:./config/dev/payment.yml"

---
spring:
  config:
    activate:
      on-profile: prod
    import: "file:./config/prod/payment.yml"
~~~

Ý nghĩa:

- Document đầu là cấu hình chung.
- Document thứ hai chỉ hoạt động khi profile expression `dev` khớp; nó mới khai báo import tới thư mục `dev`.
- Document thứ ba tương ứng với `prod`.
- Trong mỗi import, Spring Boot vẫn có thể xét biến thể theo profile của chính tệp được import, chẳng hạn `config/prod/payment-prod.yml`, nếu chúng tồn tại.

Cách này khác với việc luôn import `config/payment.yml` rồi cho Spring Boot tự khám phá `payment-dev.yml`, `payment-prod.yml`. Với nhu cầu chủ yếu là điều chỉnh một số khóa theo môi trường, **một import chung cộng với các biến thể tên tệp** thường gọn hơn. Cách import riêng từng profile có ích khi các môi trường dùng vị trí hoặc bộ tài nguyên rất khác nhau.

Trong profile-specific document, dùng `spring.config.activate.on-profile` để điều kiện hóa document. Không đặt `spring.profiles.active` hoặc `spring.profiles.default` trong document chỉ áp dụng cho profile; Spring Boot giới hạn các thuộc tính kích hoạt profile ở những document không gắn điều kiện profile.

## 9. Thứ tự ghi đè: file chính, file import và biến thể profile

Đặt ba cấu hình cạnh nhau:

~~~yaml
# application.yml
spring:
  config:
    import: "file:./config/feature.yml"
app:
  feature:
    enabled: false
    label: from-application
~~~

~~~yaml
# config/feature.yml
app:
  feature:
    enabled: true
    label: from-import
~~~

~~~yaml
# config/feature-prod.yml
app:
  feature:
    label: from-prod-import
~~~

Khi profile `prod` hoạt động, trong phạm vi ba tài liệu này, kết quả hiệu lực thường là:

~~~text
app.feature.enabled = true
app.feature.label   = from-prod-import
~~~

Giải thích:

1. Tệp chính khai báo `enabled=false`, `label=from-application`.
2. Nội dung tài liệu được import có ưu tiên trên document khai báo import đối với khóa trùng, nên `enabled=true` và `label=from-import` được xét.
3. Biến thể `feature-prod.yml` áp dụng cho profile đang hoạt động và thay `label` bằng `from-prod-import`.
4. Vì biến thể prod không khai báo `enabled`, giá trị từ file chung `feature.yml` vẫn được sử dụng.

Đây là minh họa trong một tập file tối giản. Nếu còn tài nguyên import khác, profile khác, `application-prod.yml`, biến môi trường hoặc CLI, chúng có thể ảnh hưởng kết quả cuối cùng. Không nên chỉ dựa vào tên file để kết luận một khóa chắc chắn thắng trên mọi nguồn khác.

### Trường hợp có nhiều import

Spring Boot cho phép:

~~~yaml
spring:
  config:
    import:
      - "file:./config/feature.yml"
      - "file:./config/override.yml"
~~~

Các import được xử lý theo thứ tự khai báo; import xuất hiện sau có thể có ưu tiên cao hơn import trước đối với cùng thuộc tính. Với `prod`, các biến thể `feature-prod.yml` và `override-prod.yml` cũng được xem xét nếu có. Khi nhiều nguồn trùng khóa, kiểm tra thứ tự thực tế và giá trị hiệu lực bằng `Environment`.

## 10. Nhiều profile hoạt động cùng lúc

Có thể khởi động:

~~~bash
java -jar build/libs/catalog-app.jar --spring.profiles.active=dev,metrics
~~~

Nếu ứng dụng import `config/payment.yml`, các biến thể `payment-dev.yml` và `payment-metrics.yml` có thể được áp dụng nếu chúng tồn tại.

Một trường hợp khác:

~~~bash
java -jar build/libs/catalog-app.jar --spring.profiles.active=dev,prod
~~~

Khi nhiều profile đang hoạt động và các file profile-specific trùng khóa, Spring Boot sử dụng chiến lược ưu tiên theo thứ tự profile, thường là **profile được liệt kê sau thắng** trong các nguồn có cùng mức ưu tiên. Vì các location group, imports và nguồn ngoài cũng ảnh hưởng, nên đừng sử dụng nhiều profile có cấu hình đối nghịch nhau mà không kiểm tra thứ tự.

Chẳng hạn:

~~~yaml
# config/payment-dev.yml
app:
  payment:
    mode: debug
~~~

~~~yaml
# config/payment-prod.yml
app:
  payment:
    mode: live
~~~

Nếu `dev,prod` được kích hoạt cùng lúc và hai cấu hình cùng mức xử lý tương ứng, `live` có thể là giá trị cuối cùng. Với `prod,dev`, `debug` có thể thắng. Trong triển khai thực tế, tránh kết hợp `dev` và `prod` vì chúng thường biểu diễn môi trường loại trừ nhau.

Profile group (`spring.profiles.group.*`) có thể kích hoạt nhiều profile liên quan chỉ từ một tên nhóm; khi đó các biến thể import được cân nhắc theo tập profile có hiệu lực.

## 11. Phân biệt profile-specific imported file với import trực tiếp tệp profile

Có hai cách khác nhau:

**Cách A — Import tệp gốc, tự nhận biến thể**

~~~yaml
spring:
  config:
    import: "file:./config/payment.yml"
~~~

Khi `prod` hoạt động, Spring Boot có thể xét `payment-prod.yml`. Đây là cách ưu tiên khi các môi trường dùng chung cấu trúc và chỉ khác giá trị.

**Cách B — Import đích danh một tệp profile**

~~~yaml
spring:
  config:
    import: "file:./config/payment-prod.yml"
~~~

Cách này yêu cầu chính tệp `payment-prod.yml` được import khi document khai báo import được xử lý, dù profile prod có được kích hoạt hay không. Nó **không** tự biến tệp đó thành điều kiện chỉ áp dụng với `prod`. Nếu chỉ muốn import này khi prod hoạt động, cần đặt chỉ thị import trong document có `spring.config.activate.on-profile: prod` hoặc tổ chức import ở nơi phù hợp.

Đừng gắn hậu tố `-prod` vào tên import một cách thủ công chỉ để đạt hành vi profile-specific vốn đã được Spring Boot hỗ trợ.

## 12. Vị trí tệp, đường dẫn tương đối và `optional:`

### 12.1. Đường dẫn file phụ thuộc working directory

~~~yaml
spring:
  config:
    import: "file:./config/payment.yml"
~~~

`file:./config/payment.yml` là đường dẫn theo thư mục làm việc của tiến trình Java, không nhất thiết theo thư mục chứa JAR. Ví dụ JAR nằm ở `/opt/catalog/catalog-app.jar` nhưng chạy từ `/tmp` thì vị trí trên trỏ tới `/tmp/config/payment.yml`.

Trong container hoặc service manager, nên định nghĩa working directory rõ ràng hoặc sử dụng đường dẫn tuyệt đối như:

~~~yaml
spring:
  config:
    import: "file:/etc/catalog/payment.yml"
~~~

Biến thể `file:/etc/catalog/payment-prod.yml` nằm cạnh file gốc sẽ được xem xét khi phù hợp.

### 12.2. Import tương đối với tài nguyên khai báo

Spring Boot cũng hỗ trợ location tương đối khi không dùng tiền tố cố định như `file:` hoặc `classpath:`. Ví dụ trong `classpath:/config/application.yml`:

~~~yaml
spring:
  config:
    import: "payment.yml"
~~~

Đây là một *import-relative location* và được giải quyết tương đối với tài nguyên chứa chỉ thị import. Trong khi đó, `file:./config/payment.yml` là đường dẫn cố định trong hệ thống file theo working directory. Nắm sự khác nhau này giúp tránh lỗi “không tìm thấy tệp” khi di chuyển ứng dụng giữa IDE và môi trường triển khai.

### 12.3. Có hoặc không có `optional:`

Nếu tệp import bắt buộc:

~~~yaml
spring:
  config:
    import: "file:./config/payment.yml"
~~~

Nếu location này không tồn tại, Spring Boot thường dừng khởi động với lỗi `ConfigDataLocationNotFoundException` hoặc lỗi liên quan nạp cấu hình.

Nếu tệp import có thể vắng mặt:

~~~yaml
spring:
  config:
    import: "optional:file:./config/payment.yml"
~~~

Spring Boot có thể bỏ qua location đó. Tuy nhiên, khi thiếu file hoặc khóa, giá trị quan trọng cho ứng dụng có thể vẫn không tồn tại. `optional:` **không tạo giá trị mặc định** và cũng không bảo đảm các bean cấu hình bind thành công.

### 12.4. Không cần tạo mọi biến thể profile

Nếu `payment.yml` đã có cấu hình chung và chỉ môi trường prod cần khác biệt, chỉ cần thêm `payment-prod.yml`. Không bắt buộc tạo `payment-dev.yml`, `payment-test.yml` rỗng. Khi không có biến thể cho một profile, file chung vẫn có thể cung cấp giá trị.

## 13. Profile-specific file và tài liệu YAML nhiều document

Ngoài tên file `-prod`, Spring Boot còn cho phép định nghĩa nhiều document trong cùng một YAML bằng dấu phân tách `---` và điều kiện `spring.config.activate.on-profile`.

Ví dụ `config/payment.yml`:

~~~yaml
app:
  payment:
    mode: standard
    timeout: 5s

---
spring:
  config:
    activate:
      on-profile: dev
app:
  payment:
    mode: debug
    timeout: 20s

---
spring:
  config:
    activate:
      on-profile: prod
app:
  payment:
    mode: live
    timeout: 2s
~~~

Khi import `config/payment.yml`, document chung cùng document có điều kiện phù hợp sẽ được xử lý. Đây là một cách thay thế cho việc đặt các biến thể thành ba file riêng `payment.yml`, `payment-dev.yml` và `payment-prod.yml`.

Chọn phương án theo quy mô:

- File riêng theo profile dễ phân quyền và quản lý khi khác biệt nhiều.
- Multi-document YAML phù hợp khi khác biệt ngắn và người đọc muốn xem các trường hợp cạnh nhau.
- Không nên lặp cấu hình ở cả hai phương án cho cùng khóa mà không thiết kế rõ thứ tự ghi đè.

Chú ý `---` phải bắt đầu một document mới, không thụt như khóa con. `spring.config.activate.on-profile` dùng biểu thức profile; ví dụ `on-profile: "prod | staging"` khiến document áp dụng khi một trong hai profile phù hợp.

## 14. Cấu hình import được đánh giá trong quá trình xử lý Config Data

Quá trình khởi động có thể hình dung như sau:

~~~text
Ứng dụng bắt đầu
       |
       v
Spring Boot xác định các nguồn cấu hình ban đầu và profile
       |
       v
Nạp document chứa spring.config.import
       |
       v
Giải quyết location được import
       |
       v
Xem xét bản chung và biến thể theo profile có hiệu lực
       |
       v
Tổng hợp PropertySource theo quy tắc ưu tiên Config Data
       |
       v
Environment cung cấp giá trị cuối cho binder / bean
~~~

Sơ đồ này là mô tả khái niệm, không phải từng bước nội bộ chính xác của bộ xử lý. Trên thực tế, việc xác định profile và đọc Config Data có thể qua nhiều lượt xử lý vì tài liệu có thể khai báo thêm import và điều kiện profile.

Điều cần nhớ là **import được xử lý trước khi bean cấu hình thông thường được tạo và bind**. Vì thế, một bean sử dụng `@ConfigurationProperties` có thể nhận trực tiếp giá trị từ `payment-prod.yml` mà không cần tự đọc tên file hoặc quản lý profile thủ công.

Một tài nguyên import có thể được khai báo ở nhiều nơi, nhưng Spring Boot cố gắng chỉ import tài nguyên ấy một lần trong quá trình xử lý Config Data. Không nên dùng việc import lặp lại cùng tệp như cơ chế nhân bản hay tăng ưu tiên một cách thủ công.

## 15. Lỗi phổ biến và cách kiểm tra

### Lỗi 1: đặt sai hậu tố tên file

~~~text
Đúng:  payment.yml
       payment-prod.yml

Sai ý định: payment.yml
           prod-payment.yml
           payment.prod.yml
~~~

Khi import `payment.yml`, các tên `prod-payment.yml` hoặc `payment.prod.yml` không phải biến thể profile theo quy tắc `<base>-<profile>.<extension>`. Nếu bạn muốn dùng tên tùy biến, phải import tên đó một cách có chủ đích.

### Lỗi 2: kích hoạt profile khác tên biến thể

~~~bash
java -jar build/libs/catalog-app.jar --spring.profiles.active=production
~~~

Lệnh trên hoạt động với profile `production`, không tự đổi thành `prod`. Nếu muốn tự động nạp biến thể của `payment.yml`, hãy đặt `payment-production.yml` hoặc thay profile được kích hoạt cho khớp tên file.

### Lỗi 3: file import không nằm trong thư mục dự kiến

Kiểm tra working directory và đường dẫn trong `spring.config.import`. Với `file:./config/payment.yml`, tiến trình cần tìm đúng `./config/payment.yml` tính từ nơi chạy Java. Dùng đường dẫn tuyệt đối để chẩn đoán nếu có nghi ngờ.

### Lỗi 4: thiếu file chung hoặc import bắt buộc

Nếu import chỉ định một location bắt buộc mà không thể nạp, ứng dụng có thể dừng ngay trước khi khởi tạo bean. Hãy tạo tệp đúng vị trí hoặc dùng `optional:` **khi việc thiếu file thực sự được cho phép**.

### Lỗi 5: giá trị file theo profile không xuất hiện

Kiểm tra lần lượt:

1. Profile mong muốn có nằm trong `Environment.getActiveProfiles()` hay không.
2. Tên tệp `-<profile>` và phần mở rộng có khớp tệp import gốc không.
3. Tệp được import đã được tìm/nạp thành công hay chưa.
4. Khóa YAML/properties có đúng tên và đúng mức thụt lề không.
5. Có nguồn ưu tiên cao hơn, nhất là CLI hoặc biến môi trường, ghi đè khóa đó hay không.

### Lỗi 6: khai báo profile activation ở nơi không phù hợp

Không đặt `spring.profiles.active` trong một YAML document đã bị giới hạn bởi `spring.config.activate.on-profile` hoặc trong tài nguyên cấu hình profile-specific. Hãy kích hoạt profile từ nguồn không phụ thuộc điều kiện profile như CLI, biến môi trường hoặc document chung hợp lệ.

### Lỗi 7: chẩn đoán bằng nội dung file thay vì giá trị cuối

Một file `payment-prod.yml` có thể chứa `app.payment.mode=live` nhưng chương trình vẫn nhận `manual` nếu lúc chạy có:

~~~bash
java -jar build/libs/catalog-app.jar --spring.profiles.active=prod --app.payment.mode=manual
~~~

Đây là hành vi ưu tiên thuộc tính, không nhất thiết là lỗi chọn file. Dùng `Environment` hoặc các công cụ chẩn đoán có kiểm soát để phân biệt hai tình huống.

## 16. Quan sát Spring Boot xử lý import và profile

Có thể tăng mức log quá trình xử lý cấu hình:

~~~bash
java -jar build/libs/catalog-app.jar --spring.profiles.active=prod --logging.level.org.springframework.boot.context.config=TRACE
~~~

Log cho biết quá trình xử lý config data ở mức chi tiết; nội dung thông báo và định dạng log có thể khác nhau giữa các phiên bản. Việc ghi log TRACE phù hợp khi phát triển hoặc chẩn đoán, không nhất thiết bật lâu dài trong production.

Trong mã Java, in profile đang hoạt động và khóa cần quan sát:

~~~java
System.out.println(Arrays.toString(env.getActiveProfiles()));
System.out.println(env.getProperty("app.payment.mode"));
~~~

Nếu ứng dụng đã sử dụng Spring Boot Actuator, các endpoint `env` và `configprops` có thể hỗ trợ truy nguồn và quan sát cấu hình đã bind, với điều kiện endpoint được bật và bảo vệ phù hợp. Không công khai giá trị secret trong log hoặc endpoint chỉ để kiểm tra import.

## 17. Bài tập thực hành

### Bài 1 — Dự đoán giá trị từ file chung và file dev

File chính import `optional:file:./config/notification.yml`. Tạo:

~~~yaml
# config/notification.yml
app:
  notification:
    channel: email
    retries: 3
~~~

~~~yaml
# config/notification-dev.yml
app:
  notification:
    channel: console
~~~

Khi chạy với `--spring.profiles.active=dev`, các giá trị hiệu lực là gì?

**Đáp án:** `channel=console` và `retries=3`, giả định không nguồn khác ghi đè.

### Bài 2 — Thay profile mà không đổi import

Vẫn giữ:

~~~yaml
spring:
  config:
    import: "file:./config/notification.yml"
~~~

Tạo thêm `config/notification-prod.yml` chứa `app.notification.channel: queue`. Chạy một lần với `dev` và một lần với `prod`. Xác nhận rằng **không cần sửa `spring.config.import`**, nhưng giá trị `channel` thay đổi theo profile.

### Bài 3 — Thử nhiều nguồn ghi đè

Trong `notification-prod.yml` đặt `app.notification.retries: 5`. Chạy:

~~~bash
java -jar build/libs/catalog-app.jar --spring.profiles.active=prod --app.notification.retries=8
~~~

Dự đoán kết quả. **Đáp án:** `8`, do CLI argument có ưu tiên cao hơn config data trong tình huống này.

### Bài 4 — Điều kiện profile ở document import

Trong `application.yml`, tạo document thứ hai với:

~~~yaml
---
spring:
  config:
    activate:
      on-profile: test
    import: "optional:file:./config/test/notification.yml"
~~~

Chạy với `test` rồi với `prod`. Quan sát thời điểm tài nguyên `./config/test/notification.yml` được xét. Giải thích vì sao document mang điều kiện `test` không chủ động import file ấy khi chỉ có `prod`.

### Bài 5 — Chẩn đoán biến thể không được nhận

Ứng dụng import `file:./config/report.properties`, nhưng khi chạy với `prod`, tệp `config/report.production.properties` không được chọn theo hậu tố. Hãy đổi đúng thành `report-prod.properties` (hoặc thay profile/logic import phù hợp) rồi thử lại.

## 18. Ghi nhớ

- `spring.config.import` nạp cấu hình từ tài nguyên khác; khi một profile hoạt động, **biến thể theo profile của tài nguyên được import cũng được xem xét**.
- Với import `payment.yml`, biến thể thông thường là `payment-<profile>.yml`, ví dụ `payment-prod.yml`.
- Không cần viết thêm một import riêng cho mỗi biến thể nếu chỉ muốn Spring Boot tự chọn cấu hình theo profile.
- Bản chung cung cấp giá trị nền, bản theo profile có thể ghi đè các khóa tương ứng.
- Giá trị cuối cùng còn phụ thuộc các import, location group và `PropertySource` khác; CLI hoặc biến môi trường có thể ghi đè config data.
- Dùng `spring.config.activate.on-profile` nếu chính hành động import phải phụ thuộc profile; dùng biến thể `-prod` khi file import chung nhưng giá trị khác theo profile.
- Khi cấu hình không như mong đợi, kiểm tra profile đang hoạt động, tên file, đường dẫn, khóa và nguồn ghi đè.

## Tài liệu tham khảo

- [Spring Boot 3.3 — Externalized Configuration, Importing Additional Data](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.files.importing)
- [Spring Boot 3.3 — Profile-specific Files](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.files.profile-specific)
- [Spring Boot 3.3 — Profiles](https://docs.spring.io/spring-boot/3.3/reference/features/profiles.html)
- [Spring Boot 3.3 — Type-safe Configuration Properties](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.typesafe-configuration-properties)
