# Tệp `application-{profile}` và quan hệ với tệp cấu hình chung trong Spring Boot

## 1. Bài toán: một ứng dụng, nhiều môi trường cấu hình

Một ứng dụng Spring Boot thường dùng cùng mã nguồn và cùng bản JAR để chạy trong các môi trường phát triển (dev), kiểm thử (test), staging và production (prod). Các môi trường này có nhiều cấu hình giống nhau, nhưng cũng có những khác biệt:

- Tên ứng dụng, thiết lập log chung và các giá trị mặc định có thể giống nhau.
- Cổng máy chủ, địa chỉ dịch vụ bên ngoài, giới hạn kết nối, thời gian chờ và cờ bật/tắt tính năng có thể khác nhau.
- Production có thể cần log ít chi tiết hơn, giới hạn tài nguyên rõ hơn và địa chỉ hạ tầng khác dev.

Spring Boot giải quyết nhu cầu này bằng cách cho phép kết hợp **tệp cấu hình chung** với **tệp cấu hình dành riêng cho profile**. Cách đặt tên quen thuộc là:

~~~text
application.yml
application-dev.yml
application-test.yml
application-prod.yml
~~~

Trong đó:

- `application.yml` chứa những thuộc tính chung, dùng làm mặc định cho nhiều môi trường.
- `application-dev.yml` bổ sung hoặc ghi đè những thuộc tính dành cho profile `dev`.
- `application-prod.yml` bổ sung hoặc ghi đè những thuộc tính dành cho profile `prod`.

Tên `application-{profile}` là một **mẫu đặt tên**. Khi profile có tên `prod` thì `{profile}` được thay bằng `prod`, tạo thành `application-prod.yml`. Nó không phải tên file có dấu ngoặc nhọn thật.

Mục tiêu của bài là hiểu lúc nào các file được nạp, cách chúng kết hợp với nhau và vì sao một thuộc tính cuối cùng lại nhận giá trị cụ thể.

## 2. Profile là gì?

Một **Spring profile** là tên đại diện cho một nhóm điều kiện cấu hình. Spring có thể dùng profile để quyết định những thành phần nào được tạo, chẳng hạn bean có `@Profile("prod")`. Riêng đối với Config Data, Spring Boot còn dùng profile để **kích hoạt các file cấu hình tương ứng**.

Ví dụ:

~~~text
Profile đang hoạt động: dev
→ application.yml
→ application-dev.yml

Profile đang hoạt động: prod
→ application.yml
→ application-prod.yml
~~~

Hai dòng dưới mỗi trạng thái chỉ biểu diễn các file được áp dụng trong cùng một vị trí cấu hình, không phải toàn bộ mọi `PropertySource`. Spring Boot vẫn có thể nhận giá trị từ biến môi trường, system properties và đối số dòng lệnh.

Một ứng dụng có thể kích hoạt **nhiều profile cùng lúc**, ví dụ `prod,monitoring`. Khi đó, Spring Boot xem xét cả những file tương ứng với `prod` và `monitoring`.

Điều quan trọng: **profile không tự tạo ra môi trường vật lý**. Tên `prod` chỉ có ý nghĩa vì ứng dụng và hệ thống triển khai đã dùng tên đó để tổ chức cấu hình.

## 3. Tệp chung `application.yml` được nạp như thế nào?

Nếu ứng dụng có file:

~~~yaml
# src/main/resources/application.yml
spring:
  application:
    name: catalog-service

server:
  port: 8080

app:
  banner: "Xin chào từ Catalog"
  feature:
    recommendation-enabled: false
  request-timeout: 5s
~~~

Các thuộc tính tương ứng là:

~~~properties
spring.application.name=catalog-service
server.port=8080
app.banner=Xin chào từ Catalog
app.feature.recommendation-enabled=false
app.request-timeout=5s
~~~

File `application.yml` cung cấp **giá trị mặc định**. Nó được nạp trong cơ chế tìm Config Data thông thường bất kể profile nào đang hoạt động, trừ khi cách xác định vị trí/tên cấu hình đã được tùy chỉnh hoặc file đó không nằm ở vị trí được Spring Boot tìm đến.

Các file `application.properties` và `application.yaml` cũng được hỗ trợ. Nên thống nhất một định dạng để dễ theo dõi; khi cùng một vị trí có cả `.properties` và YAML cho cùng tên, Spring Boot ưu tiên `.properties`.

Một khóa trong file chung không cần phải được lặp lại trong mọi file theo profile. Nếu không có nguồn nào có ưu tiên cao hơn ghi đè, giá trị chung tiếp tục có hiệu lực.

## 4. File `application-{profile}.yml` chỉ bổ sung hoặc ghi đè khóa cần khác biệt

Giữ file chung ở trên, thêm file:

~~~yaml
# src/main/resources/application-dev.yml
server:
  port: 8081

app:
  banner: "Đang chạy ở DEV"
  feature:
    recommendation-enabled: true
~~~

Và một file khác:

~~~yaml
# src/main/resources/application-prod.yml
server:
  port: 9090

app:
  request-timeout: 15s
~~~

Khi kích hoạt `dev`, kết quả trong phạm vi các file đóng gói này là:

| Khóa | Giá trị hiệu lực | Nguồn |
| --- | --- | --- |
| `spring.application.name` | `catalog-service` | File chung |
| `server.port` | `8081` | `application-dev.yml` |
| `app.banner` | `Đang chạy ở DEV` | `application-dev.yml` |
| `app.feature.recommendation-enabled` | `true` | `application-dev.yml` |
| `app.request-timeout` | `5s` | File chung |

Khi kích hoạt `prod`:

| Khóa | Giá trị hiệu lực | Nguồn |
| --- | --- | --- |
| `spring.application.name` | `catalog-service` | File chung |
| `server.port` | `9090` | `application-prod.yml` |
| `app.banner` | `Xin chào từ Catalog` | File chung |
| `app.feature.recommendation-enabled` | `false` | File chung |
| `app.request-timeout` | `15s` | `application-prod.yml` |

Một điểm quan trọng: **Spring Boot không thay thế toàn bộ file chung bằng file profile**. Các nguồn thuộc tính được chồng lên nhau. Khi nhiều nguồn cùng có một khóa, nguồn ưu tiên cao hơn quyết định giá trị cuối cùng của khóa đó; các khóa không bị ghi đè vẫn còn.

Ví dụ, nếu `application-prod.yml` không có `spring.application.name`, ứng dụng vẫn dùng `catalog-service` từ file chung.

## 5. Kích hoạt profile để Spring Boot chọn file tương ứng

Spring Boot cần biết profile nào đang hoạt động. Những cách thông dụng nhất gồm:

### 5.1. Đối số khi chạy JAR

~~~bash
java -jar catalog-service.jar --spring.profiles.active=dev
~~~

Hoặc:

~~~bash
java -jar catalog-service.jar --spring.profiles.active=prod
~~~

Dấu `--spring.profiles.active=...` là một đối số ứng dụng được Spring Boot nhận khi khởi động.

### 5.2. Biến môi trường

Trên một môi trường shell hỗ trợ cú pháp sau:

~~~bash
export SPRING_PROFILES_ACTIVE=prod
java -jar catalog-service.jar
~~~

Trên PowerShell:

~~~powershell
$env:SPRING_PROFILES_ACTIVE = "prod"
java -jar catalog-service.jar
~~~

Spring Boot hỗ trợ ánh xạ tên biến môi trường sang thuộc tính, nên `SPRING_PROFILES_ACTIVE` tương ứng với `spring.profiles.active`.

### 5.3. Java system property

~~~bash
java -Dspring.profiles.active=prod -jar catalog-service.jar
~~~

Chú ý thứ tự tham số Java: `-Dspring.profiles.active=prod` nằm **trước** `-jar`.

### 5.4. Cấu hình trong file chung

Có thể đặt một profile mặc định muốn kích hoạt ngay trong phần cấu hình **không đặc thù profile**:

~~~yaml
# application.yml
spring:
  profiles:
    active: dev
~~~

Tuy nhiên, không nên cứng hóa `prod` hoặc các profile triển khai trong JAR chung nếu việc lựa chọn môi trường do hệ thống deploy chịu trách nhiệm. Việc dùng đối số hoặc biến môi trường khi triển khai giúp một artifact phục vụ nhiều môi trường.

`spring.profiles.active` là thuộc tính chịu thứ tự ưu tiên thông thường giữa các property source: một giá trị được đưa từ nguồn ưu tiên cao hơn có thể ghi đè giá trị trong file chung.

**Giới hạn quan trọng:** `spring.profiles.active` và `spring.profiles.default` phải được khai báo trong **tài liệu không đặc thù profile**. Không đặt chúng vào `application-prod.yml` hoặc vào tài liệu YAML đã được kích hoạt bằng `spring.config.activate.on-profile`. Spring Boot sẽ coi những khai báo sai vị trí như vậy là cấu hình không hợp lệ.

## 6. Khi không kích hoạt profile nào: file chung và profile mặc định

Nếu không có active profile được chỉ định, Spring dùng profile mặc định có tên `default`. Với cấu hình thông thường, Spring Boot có thể nạp:

~~~text
application.yml
application-default.yml
~~~

Nếu file `application-default.yml` tồn tại và hợp lệ, các thuộc tính từ đó có thể bổ sung/ghi đè thuộc tính chung, giống cơ chế file theo profile. Nếu file không có, ứng dụng vẫn có thể dùng `application.yml` và những nguồn cấu hình khác.

Ví dụ:

~~~yaml
# application.yml
server:
  port: 8080
app:
  mode: common
~~~

~~~yaml
# application-default.yml
app:
  mode: fallback
~~~

Không có active profile khác, `app.mode` có thể nhận `fallback` từ file dành cho profile mặc định. Khi kích hoạt `prod`, file `application-default.yml` không còn tự động được nạp theo lý do “không có active profile”; các file dành cho `prod` sẽ được xét.

Có thể đổi tên profile mặc định bằng `spring.profiles.default` trong tài liệu không đặc thù profile hoặc qua nguồn cấu hình đủ sớm. `spring.profiles.default=none` là một lựa chọn nếu không muốn có profile mặc định. **Không cần tạo file `application-default.yml` chỉ vì Spring có khái niệm default profile**.

Phân biệt:

- **Không có active profile:** Spring xét profile mặc định, thông thường là `default`.
- **Có active profile `dev`:** Spring xét `dev`, không tự coi `default` là profile active bổ sung.

## 7. Thứ tự ưu tiên: packaged và external quan trọng không kém profile

Đây là phần dễ gây nhầm lẫn nhất. Tệp chung và tệp theo profile có thể nằm **bên trong JAR** hoặc **bên ngoài JAR**.

Trong cách tìm Config Data mặc định, đối với bốn nhóm điển hình, thứ tự từ ưu tiên thấp đến cao là:

1. File `application.*` chung **đóng gói trong JAR**.
2. File `application-{profile}.*` **đóng gói trong JAR**.
3. File `application.*` chung **bên ngoài JAR**.
4. File `application-{profile}.*` **bên ngoài JAR**.

Nguồn đứng sau trong danh sách này có thể ghi đè khóa trùng tên từ nguồn đứng trước. Điều đó dẫn đến kết quả tưởng như bất ngờ: **một file `application.yml` bên ngoài có thể thắng cả `application-prod.yml` bên trong JAR**.

Ví dụ:

~~~text
JAR / classpath:
  application.yml          → server.port=8080
  application-prod.yml     → server.port=8081

Working directory:
  ./config/application.yml      → server.port=9080
  ./config/application-prod.yml → server.port=9180
~~~

Bật profile `prod`:

| Các file đang tồn tại | `server.port` cuối cùng |
| --- | --- |
| Chỉ hai file trong JAR | `8081` |
| Thêm `./config/application.yml` | `9080` |
| Có đủ cả bốn file | `9180` |
| Bỏ file ngoài `application-prod.yml`, giữ file ngoài chung | `9080` |

Giải thích trường hợp thứ hai: file bên ngoài **không đặc thù profile** vẫn có mức ưu tiên cao hơn file theo profile **nhưng nằm trong JAR**, xét theo thứ tự Config Data thông thường.

Đây là lý do không thể chỉ nhìn tên file `application-prod.yml` rồi khẳng định mọi giá trị trong đó sẽ thắng.

### Working directory của tệp bên ngoài

Spring Boot mặc định tìm thêm các vị trí như `file:./`, `file:./config/` và các thư mục con trực tiếp `file:./config/*/`. Đường dẫn `./` được tính theo **thư mục làm việc của tiến trình Java**, không nhất thiết là thư mục chứa JAR.

Giả sử:

~~~text
/opt/catalog/
  catalog-service.jar
  config/
    application-prod.yml
~~~

Khi chạy:

~~~bash
cd /opt/catalog
java -jar catalog-service.jar --spring.profiles.active=prod
~~~

Spring có thể thấy `./config/application-prod.yml`. Nhưng khi chạy cùng file JAR từ thư mục `/tmp`, `./config/` sẽ trỏ đến `/tmp/config/`.

Muốn không phụ thuộc working directory, có thể cấu hình vị trí bên ngoài tuyệt đối bằng `spring.config.additional-location`:

~~~bash
java -jar /opt/catalog/catalog-service.jar --spring.profiles.active=prod --spring.config.additional-location=optional:file:/etc/catalog/
~~~

`spring.config.additional-location` giữ các vị trí mặc định và bổ sung vị trí mới. Trái lại, `spring.config.location` **thay thế** danh sách vị trí mặc định. Cân nhắc kỹ nếu dự án còn phụ thuộc `application.yml` đóng gói.

## 8. Nhiều profile cùng hoạt động: quy tắc “profile sau thắng”

Một ứng dụng có thể bật nhiều profile:

~~~bash
java -jar catalog-service.jar --spring.profiles.active=prod,observability
~~~

Giả sử cùng một nhóm vị trí có:

~~~yaml
# application.yml
app:
  feature-enabled: false
  log-sample-rate: 0.1
~~~

~~~yaml
# application-prod.yml
app:
  feature-enabled: true
  log-sample-rate: 0.2
~~~

~~~yaml
# application-observability.yml
app:
  log-sample-rate: 0.8
~~~

Với thứ tự `prod,observability` trong ví dụ cùng nhóm vị trí, file theo profile sau `observability` có thể ghi đè giá trị trùng khóa từ `prod`. Kết quả là:

~~~properties
app.feature-enabled=true
app.log-sample-rate=0.8
~~~

Đổi thành:

~~~bash
java -jar catalog-service.jar --spring.profiles.active=observability,prod
~~~

Trong cùng điều kiện trên, `app.log-sample-rate` có thể trở thành `0.2` do `prod` đứng sau.

Đây là quy tắc **last wins** giữa các profile đang hoạt động ở cùng ngữ cảnh nạp. Tuy nhiên, khi kết hợp nhiều vị trí packaged/external hoặc cấu hình `spring.config.location` với location group, cần xét cả **thứ tự giữa các vị trí**; không được áp dụng quy tắc “profile sau luôn thắng bất kể file nằm ở đâu”.

Ví dụ, một thuộc tính được đặt trong file chung external ưu tiên cao hơn vẫn có thể thắng thuộc tính trong file profile packaged, dù tên profile đó ở cuối danh sách.

Nếu ứng dụng có nhiều profile với trách nhiệm khác nhau, nên hạn chế định nghĩa cùng một khóa ở nhiều file nếu không có nhu cầu override rõ ràng.

## 9. Các file theo profile vắng mặt có làm ứng dụng khởi động lỗi không?

Thông thường, **không cần tạo đủ mọi file `application-{profile}.yml`**. Ví dụ, ứng dụng có `application.yml` và `application-prod.yml` nhưng không có `application-dev.yml`. Khi kích hoạt `dev` qua các vị trí tìm kiếm mặc định, ứng dụng vẫn có thể dùng các giá trị chung, vì việc không có file `application-dev.yml` tại một vị trí tìm kiếm mặc định không tự coi là lỗi.

Khác với trường hợp bạn **chỉ định tường minh một tài nguyên Config Data bắt buộc không tồn tại**, chẳng hạn dùng `spring.config.import` trỏ đến một file cụ thể. Tình huống đó có thể khiến Spring Boot dừng với lỗi vị trí không tìm thấy nếu không được đánh dấu tùy chọn.

Không nên dùng `optional:` để “tạo” profile hoặc làm file cấu hình mới được ưu tiên hơn. Tiền tố này chỉ cho phép vắng mặt một vị trí Config Data mà không xem riêng sự vắng mặt đó là lỗi.

Ví dụ tệp nhập thêm hợp lệ khi được phép vắng mặt:

~~~yaml
# application.yml
spring:
  config:
    import: "optional:file:/etc/catalog/feature-flags.yml"
~~~

Đây là cơ chế nhập tài nguyên riêng. Nó khác với việc Spring tự tìm `application-prod.yml` khi profile `prod` đã được kích hoạt.

## 10. Một file YAML nhiều tài liệu có thể thay thế cách chia file profile

Spring Boot cho phép đưa nhiều tài liệu YAML vào cùng `application.yml`, cách nhau bằng `---`. Một tài liệu có thể được kích hoạt khi profile phù hợp, bằng `spring.config.activate.on-profile`.

Ví dụ:

~~~yaml
# application.yml — tài liệu chung
app:
  shipping:
    provider: mock
    timeout: 3s

---
# Tài liệu chỉ kích hoạt khi profile prod hoạt động
spring:
  config:
    activate:
      on-profile: prod

app:
  shipping:
    provider: real
    timeout: 10s
~~~

Khi profile `prod` không hoạt động, ứng dụng nhận provider `mock` và timeout `3s` từ tài liệu chung. Khi `prod` hoạt động, tài liệu thứ hai được áp dụng và có thể ghi đè thành `real` và `10s`.

Hai cách tổ chức phổ biến:

| Tổ chức bằng file riêng | Tổ chức bằng nhiều tài liệu YAML |
| --- | --- |
| `application.yml` + `application-prod.yml` | Một `application.yml` chứa nhiều tài liệu ngăn bằng `---` |
| Dễ tách cấu hình từng môi trường thành file độc lập | Dễ nhìn cấu hình chung và các nhánh profile trong cùng file |
| Tên file xác định profile áp dụng | `spring.config.activate.on-profile` xác định điều kiện kích hoạt tài liệu |
| Có thể có bản đóng gói và bản ngoài JAR | Vẫn chịu thứ tự ưu tiên Config Data giữa các vị trí |

Một tài liệu đã có điều kiện `spring.config.activate.on-profile` là **tài liệu đặc thù profile**. Không đặt `spring.profiles.active`, `spring.profiles.default` hoặc `spring.profiles.include` vào tài liệu này để tìm cách bật thêm profile; những thuộc tính lựa chọn profile phải ở tài liệu không đặc thù profile.

Cú pháp `spring.config.activate.on-profile` chấp nhận biểu thức profile (ví dụ `prod | staging`); tên biểu thức dùng theo quy tắc profile expression của Spring, không phải một danh sách tên file.

## 11. Đọc giá trị cuối cùng trong mã Java

Cơ chế Config Data hợp nhất các nguồn thành các thuộc tính có thể tra cứu. Trong code Spring, có thể dùng `Environment`:

~~~java
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class DeploymentInfo {
    private final Environment environment;

    public DeploymentInfo(Environment environment) {
        this.environment = environment;
    }

    public String activeProfiles() {
        return String.join(", ", environment.getActiveProfiles());
    }

    public String displayBanner() {
        return environment.getProperty("app.banner", "Default banner");
    }

    public Integer port() {
        return environment.getProperty("server.port", Integer.class);
    }
}
~~~

`getActiveProfiles()` cho biết các profile đang được kích hoạt tường minh. Khi danh sách đó trống, `getDefaultProfiles()` mới là nguồn để kiểm tra profile mặc định. Việc dùng `getProperty("server.port")` trả về **giá trị hiệu lực sau khi xét thứ tự ưu tiên** trong `Environment`, không phải giá trị cố định từ một tên file.

Với nhóm thuộc tính, `@ConfigurationProperties` phù hợp hơn việc dùng nhiều `@Value` riêng lẻ. Giả sử YAML chung:

~~~yaml
app:
  client:
    base-url: "https://sandbox.example.org"
    timeout: 3s
~~~

File `application-prod.yml`:

~~~yaml
app:
  client:
    base-url: "https://api.example.org"
    timeout: 12s
~~~

Khai báo:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(String baseUrl, Duration timeout) {}
~~~

Và bật quét:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class CatalogApplication {
    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
~~~

Ứng dụng sẽ bind các **giá trị cuối cùng** trong `Environment` vào `ClientProperties`. Khi `prod` hoạt động và không có override ưu tiên cao hơn, `baseUrl` và `timeout` lần lượt là `https://api.example.org` và `12s`.

## 12. Quan hệ giữa file profile và những nguồn cấu hình khác

File theo profile là một phần của Config Data, không phải toàn bộ hệ thống cấu hình Spring Boot.

Xét ví dụ sau trong file `application-prod.yml`:

~~~yaml
server:
  port: 9090
~~~

Nếu môi trường triển khai đặt thêm:

~~~bash
export SERVER_PORT=7070
java -jar catalog-service.jar --spring.profiles.active=prod
~~~

Với không có nguồn ưu tiên cao hơn nữa, `server.port` cuối cùng là `7070` do biến môi trường có ưu tiên cao hơn Config Data.

Tương tự, đối số ứng dụng:

~~~bash
java -jar catalog-service.jar --spring.profiles.active=prod --server.port=6060
~~~

có thể thắng cả file profile lẫn biến môi trường thông thường.

Hãy nhớ thứ tự tương đối thường gặp:

~~~text
Config Data (application.yml / application-prod.yml / file ngoài)
         < biến môi trường hệ điều hành
         < Java system properties
         < đối số dòng lệnh
~~~

Đây là **đoạn ưu tiên thường gặp**, không phải danh mục đầy đủ mọi property source. Spring Boot còn có nguồn cấu hình cho test và các môi trường runtime cụ thể.

Vì thế, nếu sửa file `application-prod.yml` mà ứng dụng không đổi giá trị, chưa chắc file đó bị bỏ qua: có thể một nguồn khác đang ghi đè.

## 13. Không phải cấu hình nào cũng “merge sâu” theo cách trực giác

Đối với các khóa scalar độc lập, nguồn ưu tiên cao hơn ghi đè theo khóa. Nhưng khi bind các cấu trúc phức tạp, cần lưu ý danh sách.

Ví dụ file chung:

~~~yaml
app:
  upstreams:
    - name: primary
      url: "https://primary.example.org"
    - name: backup
      url: "https://backup.example.org"
~~~

File `application-prod.yml`:

~~~yaml
app:
  upstreams:
    - name: production
      url: "https://prod.example.org"
~~~

Nếu bind vào `List<Upstream>`, danh sách từ nguồn profile ưu tiên cao hơn thường **thay thế danh sách cũ** trong cách binder xử lý danh sách, thay vì tự động giữ thêm phần tử `backup` từ file chung.

Do đó, khi cấu hình một list khác nhau giữa dev và prod, nên **khai báo đầy đủ danh sách mong muốn** trong file profile.

Trái lại, các khóa độc lập như `app.client.timeout` và `app.client.base-url` có thể được cung cấp từ những file khác nhau. Đừng đánh đồng cách chọn giá trị của một khóa với cách bind toàn bộ cấu trúc collection.

## 14. Ví dụ triển khai với Docker Compose

Một ứng dụng có cấu hình chung trong JAR:

~~~yaml
# application.yml
spring:
  application:
    name: inventory-service

server:
  port: 8080

app:
  stock:
    refresh-interval: 30s
~~~

File profile:

~~~yaml
# application-prod.yml
app:
  stock:
    refresh-interval: 5m
~~~

Docker Compose có thể truyền profile và vị trí file ngoài JAR:

~~~yaml
services:
  inventory:
    image: example/inventory-service:latest
    environment:
      SPRING_PROFILES_ACTIVE: "prod"
      SPRING_CONFIG_ADDITIONAL_LOCATION: "optional:file:/etc/inventory/"
    ports:
      - "8080:8080"
    volumes:
      - ./config:/etc/inventory:ro
~~~

Trong ví dụ này, nếu container có file `/etc/inventory/application-prod.yml`, nguồn đó có thể bổ sung hoặc ghi đè các khóa Config Data đã có. Giá trị `server.port` có thể bị thay bằng cấu hình triển khai nếu có override. Khi đổi cổng server thực tế, phải rà lại ánh xạ `ports` và cách kiểm tra sức khỏe container.

Cách cấu hình này cho phép tái sử dụng cùng image tại nhiều môi trường. Không nên đóng gói secret production vào file `application-prod.yml` đã commit; secret nên được cấp qua cơ chế quản lý bí mật hoặc môi trường triển khai phù hợp.

## 15. Profile trong kiểm thử tự động

Trong bài test tích hợp, có thể chọn profile bằng `@ActiveProfiles` của Spring Test:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.core.env.Environment;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@ActiveProfiles("test")
class ProfileConfigurationTest {
    @Autowired
    private Environment environment;

    @Test
    void shouldActivateTestProfile() {
        assertThat(environment.getActiveProfiles()).contains("test");
    }
}
~~~

Nếu có `src/test/resources/application-test.yml` hoặc nguồn cấu hình test phù hợp, các thuộc tính từ đó được xem xét theo cơ chế Config Data và thứ tự ưu tiên áp dụng cho test.

Có thể đặt trong `src/test/resources/application-test.yml`:

~~~yaml
app:
  external-service:
    url: "http://localhost:18080"
~~~

Tuy nhiên, không nên giả định mọi test sẽ tự dùng profile `test` chỉ vì file `application-test.yml` tồn tại. Test cần được kích hoạt profile bằng `@ActiveProfiles("test")`, cấu hình môi trường hoặc cơ chế test tương ứng.

## 16. Những lỗi thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `application-prod.yml` không được áp dụng | Chưa kích hoạt profile `prod` | Kiểm tra `spring.profiles.active` và `Environment#getActiveProfiles()` |
| Kích hoạt `prod` nhưng vẫn dùng giá trị chung | Khóa không tồn tại trong file profile, hoặc nguồn ưu tiên cao hơn đang chi phối | Kiểm tra tên khóa, thứ tự Config Data và các nguồn khác |
| Giá trị từ file chung external thắng file profile đóng gói | External Config Data có ưu tiên cao hơn packaged profile | Xác định chính xác đường dẫn của từng file |
| Đã đặt `SPRING_PROFILES_ACTIVE` nhưng không chạy như dự kiến | Biến môi trường chưa truyền vào tiến trình/container | Kiểm tra cấu hình launch, Compose hoặc môi trường runtime |
| File `application-prod.yml` đặt cạnh JAR nhưng không được tìm thấy | Working directory không phải thư mục chứa JAR | Chạy từ đúng thư mục hoặc dùng vị trí tuyệt đối |
| Bị lỗi khi đặt `spring.profiles.active` vào `application-prod.yml` | Thuộc tính lựa chọn profile không được đặt trong tài liệu đặc thù profile | Chuyển về file chung hoặc nguồn khởi động |
| Kích hoạt `dev,prod` cho ra giá trị khác `prod,dev` | Thứ tự profile ảnh hưởng đến override trong cùng nhóm vị trí | Chọn thứ tự profile có chủ đích, tránh khai báo trùng khóa không cần thiết |
| Danh sách cấu hình thiếu phần tử sau khi bật profile | Danh sách mới thay thế danh sách cũ khi bind | Định nghĩa đủ phần tử trong file profile |
| Không có profile nào nhưng vẫn nhận giá trị ngoài file chung | Có file `application-default.yml` hoặc nguồn khác | Kiểm tra default profile và tất cả Config Data thực tế |
| Đã sửa YAML nhưng tiến trình vẫn giữ giá trị cũ | Config Data thường nạp tại startup, không tự hot reload | Khởi động lại hoặc dùng cơ chế refresh được cấu hình riêng |

Khi cần tìm nguyên nhân một giá trị cụ thể, hãy xác định theo thứ tự:

1. Những profile nào thực sự đang hoạt động? Có profile mặc định nào được xét không?
2. Những file `application.*` nào được tìm thấy trên classpath và filesystem?
3. Có dùng `spring.config.location`, `additional-location` hoặc `import` thay đổi cách tìm file không?
4. Khóa được định nghĩa ở những nguồn nào và nguồn nào có mức ưu tiên cao nhất?
5. Có biến môi trường, Java system property, đối số CLI hoặc cấu hình test nào ghi đè không?

Nếu sử dụng Spring Boot Actuator, endpoint `env` và `configprops` có thể hỗ trợ điều tra nguồn và giá trị cấu hình khi được bật. Cần giới hạn quyền truy cập và che thông tin nhạy cảm.

## 17. Bài tập thực hành

### Bài 1 — Ghi đè khóa

Trong JAR có:

~~~yaml
# application.yml
server:
  port: 8080
app:
  feature-enabled: false
  message: "common"
~~~

~~~yaml
# application-dev.yml
server:
  port: 8082
app:
  feature-enabled: true
~~~

Chạy với `--spring.profiles.active=dev`, không có nguồn override khác. Hỏi ba giá trị cuối là gì?

**Đáp án:** `server.port=8082`, `app.feature-enabled=true` và `app.message=common`. Khóa `message` được giữ từ file chung vì file `dev` không khai báo lại.

### Bài 2 — File external không theo profile

Cho:

~~~text
classpath:/application.yml        → app.mode=common
classpath:/application-prod.yml   → app.mode=packaged-prod
file:./config/application.yml     → app.mode=external-common
~~~

Kích hoạt `prod` và không có override khác. `app.mode` bằng gì?

**Đáp án:** `external-common` vì Config Data chung bên ngoài có ưu tiên cao hơn Config Data theo profile nhưng đóng gói.

### Bài 3 — Hai profile active

Trong cùng một vị trí:

~~~text
application.yml                → app.color=gray
application-prod.yml           → app.color=blue
application-observability.yml  → app.color=green
~~~

Chạy lần lượt với `prod,observability` và `observability,prod`. Hãy xác định kết quả.

**Đáp án:** nếu không có override khác và chỉ xét nhóm vị trí này, lần thứ nhất là `green`, lần thứ hai là `blue`, do profile xuất hiện sau có thể ghi đè profile trước.

### Bài 4 — Không có active profile

Có `application.yml` và `application-default.yml` nhưng không có cấu hình `spring.profiles.active`. File nào được xem xét?

**Đáp án:** cả file chung và file theo profile mặc định `default` đều có thể được nạp từ vị trí tìm kiếm thích hợp. Nếu file default ghi đè cùng khóa, giá trị của nó thắng file chung trong cùng nhóm vị trí.

### Bài 5 — Chọn cách tổ chức

Dịch vụ có timeout chung `3s` và timeout production `12s`. Hãy viết hai file YAML để tránh lặp lại các khóa không cần thiết.

**Đáp án gợi ý:**

~~~yaml
# application.yml
app:
  client:
    base-url: "https://sandbox.example.org"
    timeout: 3s
~~~

~~~yaml
# application-prod.yml
app:
  client:
    base-url: "https://api.example.org"
    timeout: 12s
~~~

Hai file vẫn dùng cùng tiền tố `app.client`. Khi `prod` hoạt động, các khóa trùng được ghi đè; những khóa chung khác tiếp tục giữ nguyên.

## 18. Ghi nhớ

- `application.yml` là **cấu hình chung**; `application-{profile}.yml` được Spring Boot xét khi profile tương ứng hoạt động.
- File theo profile **bổ sung hoặc ghi đè từng thuộc tính**, không xóa toàn bộ nội dung file chung.
- Có thể kích hoạt profile qua `--spring.profiles.active=...`, `SPRING_PROFILES_ACTIVE` hoặc nguồn cấu hình phù hợp.
- Không có active profile thì Spring dùng profile mặc định, thông thường là `default`; `application-default.yml` có thể tham gia nếu tồn tại.
- Trong các nhóm Config Data thông dụng: **packaged chung → packaged theo profile → external chung → external theo profile**.
- Khi bật nhiều profile, **thứ tự profile** có thể thay đổi giá trị cuối; đồng thời phải xét cả nhóm vị trí và mức ưu tiên external/packaged.
- `spring.config.activate.on-profile` cho phép chia nhiều tài liệu theo profile trong một file YAML.
- Nguồn bên ngoài Config Data như biến môi trường hoặc CLI có thể ghi đè file profile.
- Cần khai báo đủ danh sách ở nguồn theo profile nếu muốn override một `List`, thay vì giả định các phần tử sẽ tự ghép.
- Để chẩn đoán, xác định **profile đang chạy, file thực sự được nạp và nguồn cuối cùng sở hữu khóa**.

Tài liệu tham khảo:

- [Spring Boot 3.3 — Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html)
- [Spring Boot 3.3 — Profiles](https://docs.spring.io/spring-boot/3.3/reference/features/profiles.html)
