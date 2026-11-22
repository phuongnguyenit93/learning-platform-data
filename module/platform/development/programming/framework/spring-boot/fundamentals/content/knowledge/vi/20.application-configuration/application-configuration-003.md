# Cấu hình trong classpath, file bên ngoài, biến môi trường và dòng lệnh

Một ứng dụng Spring Boot thường phải chạy trên nhiều môi trường: máy lập trình, môi trường kiểm thử, staging và production. Code có thể giống nhau, nhưng địa chỉ dịch vụ, timeout, mức log hoặc các tùy chọn vận hành lại khác nhau. Spring Boot giải quyết việc này bằng cơ chế **externalized configuration**: tách giá trị cấu hình ra khỏi code và hợp nhất các nguồn cấu hình thông qua `Environment`.

Bốn nguồn rất thường gặp là file nằm trong **classpath**, file cấu hình **bên ngoài ứng dụng**, **biến môi trường** của tiến trình và **tham số dòng lệnh**. Hiểu cách Spring Boot tìm, nạp và ưu tiên các nguồn này giúp triển khai cùng một JAR ở nhiều môi trường mà không phải biên dịch lại.

## 1. Cấu hình bên ngoài code nghĩa là gì?

Giả sử một ứng dụng kết nối tới dịch vụ Catalog. Những giá trị cần thay đổi theo môi trường có thể là:

- `app.catalog.base-url`: địa chỉ của Catalog API.
- `app.catalog.connect-timeout`: thời gian chờ kết nối.
- `app.catalog.enabled`: có bật tích hợp Catalog hay không.
- `logging.level.com.example.catalog`: mức log cho package liên quan.

Thay vì hard-code các giá trị đó trong Java, ứng dụng có thể dùng `application.yml`:

~~~yaml
app:
  catalog:
    base-url: https://catalog-dev.example.test
    connect-timeout: 3s
    enabled: true

logging:
  level:
    com.example.catalog: INFO
~~~

Khi chạy ở production, người vận hành có thể thay `app.catalog.base-url` hoặc timeout bằng file bên ngoài, biến môi trường hoặc tham số dòng lệnh. Các component đọc cấu hình thông qua Spring, chứ không cần tự mở từng file để tìm giá trị.

Các nguồn cấu hình được Spring hợp nhất thành một Environment có thứ tự ưu tiên. Nếu một thuộc tính xuất hiện ở nhiều nguồn, nguồn có độ ưu tiên cao hơn sẽ quyết định giá trị được đọc.

## 2. File trong classpath: cấu hình đóng gói cùng ứng dụng

Classpath là tập các vị trí mà JVM và class loader dùng để tìm class và resource. Với ứng dụng Spring Boot, các file cấu hình thường được đặt trong:

~~~text
src/main/resources/
├── application.yml
├── application-dev.yml
└── application-prod.yml
~~~

Khi build JAR, các resource này được đóng gói cùng ứng dụng. Spring Boot có thể tìm các file cấu hình tiêu chuẩn ở classpath, bao gồm những vị trí phổ biến:

~~~text
classpath:/
classpath:/config/
~~~

Ví dụ, `src/main/resources/application.yml` thường trở thành resource `application.yml` trong classpath của ứng dụng:

~~~yaml
spring:
  application:
    name: catalog-service

app:
  catalog:
    base-url: https://catalog-default.example.test
    connect-timeout: 5s
    enabled: true
~~~

Ưu điểm của classpath configuration:

- Dễ đưa cấu hình mặc định đi cùng phiên bản phần mềm.
- Cùng một artifact luôn có bộ default hợp lý.
- Phù hợp cho các tùy chọn không nhạy cảm và không phụ thuộc riêng vào một môi trường.
- Các developer nhìn thấy cấu hình mặc định ngay trong source code.

Hạn chế là thay trực tiếp file đã đóng gói thường không thuận tiện. Trên server, container hoặc Kubernetes, nên giữ JAR bất biến và dùng nguồn bên ngoài để ghi đè các giá trị khác nhau theo môi trường.

### .properties và .yml

Spring Boot hỗ trợ cả Java properties và YAML:

~~~properties
spring.application.name=catalog-service
app.catalog.base-url=https://catalog-default.example.test
app.catalog.connect-timeout=5s
app.catalog.enabled=true
~~~

Đây là biểu diễn tương đương với YAML ở trên. Nên thống nhất một định dạng chính cho cùng một vị trí cấu hình; nếu `.properties` và YAML cùng tồn tại với cùng tên cơ sở trong một location, file `.properties` được ưu tiên.

YAML thuận tiện cho cấu trúc phân cấp. Properties phù hợp cho danh sách cặp key-value và các tình huống chỉ cần chỉnh vài dòng.

## 3. File bên ngoài JAR: cấu hình theo môi trường triển khai

Spring Boot cũng tìm file cấu hình trong hệ thống file bên ngoài JAR. Các vị trí tìm kiếm mặc định thường bao gồm:

~~~text
file:./
file:./config/
file:./config/*/
~~~

Dấu `./` là **thư mục làm việc hiện tại** của tiến trình, không nhất thiết là thư mục chứa file JAR. Đây là điểm quan trọng khi chạy ứng dụng bằng service manager, Docker hoặc một pipeline triển khai.

Ví dụ:

~~~text
/opt/catalog/
├── catalog-service.jar
└── config/
    └── application.yml
~~~

Khi tiến trình chạy với working directory là `/opt/catalog`, file `/opt/catalog/config/application.yml` là một nguồn cấu hình bên ngoài có thể được Spring Boot tìm thấy.

Giả sử trong JAR có:

~~~yaml
app:
  catalog:
    base-url: https://catalog-default.example.test
    connect-timeout: 5s
~~~

Còn file `./config/application.yml` ở ngoài JAR chứa:

~~~yaml
app:
  catalog:
    base-url: https://catalog-prod.example.test
    connect-timeout: 2s
~~~

Với các nguồn mặc định này, giá trị ngoài JAR có độ ưu tiên cao hơn giá trị đóng gói. Ứng dụng sẽ nhận `base-url` production và timeout `2s`.

File bên ngoài phù hợp khi:

- Vận hành muốn quản lý các giá trị theo từng môi trường.
- Cần thay cấu hình mà không tạo lại artifact.
- Cần mount cấu hình vào container hoặc Pod.
- Có nhiều cấu hình liên quan muốn quản lý cùng nhau trong một file.

**Việc sửa file ngoài JAR không đồng nghĩa Spring Boot tự tải lại cấu hình tại runtime.** Trong một ứng dụng thông thường, các giá trị được nạp lúc startup và được bind vào bean khi context khởi tạo; cần khởi động lại hoặc dùng một giải pháp refresh được thiết kế riêng nếu muốn thay đổi có hiệu lực sau đó.

## 4. Thứ tự ưu tiên giữa các nguồn

Một quy tắc thực dụng trong ứng dụng Spring Boot thông thường là:

| Mức ưu tiên | Nguồn | Ví dụ |
|---|---|---|
| 1 — thấp hơn | File đóng gói trong classpath | `classpath:/application.yml` |
| 2 | File cấu hình bên ngoài | `file:./config/application.yml` |
| 3 | Biến môi trường hệ điều hành | `APP_CATALOG_BASEURL` |
| 4 — cao hơn | Tham số dòng lệnh Spring Boot | `--app.catalog.base-url=...` |

Bảng tập trung vào **bốn nguồn trong bài học**. Environment của Spring Boot còn có các nguồn khác như Java system properties, `SPRING_APPLICATION_JSON`, các giá trị mặc định do code cung cấp và nguồn riêng của test. Chúng có vị trí ưu tiên riêng; trong một số trường hợp có thể nằm giữa hoặc phía trên những nguồn trong bảng.

Trong các Config Data files tiêu chuẩn, Spring Boot cũng phân biệt file thông thường và file theo profile, cũng như tài nguyên đóng gói và tài nguyên bên ngoài. Theo thứ tự ưu tiên tăng dần:

1. File `application` đóng gói trong JAR.
2. File `application-{profile}` đóng gói trong JAR.
3. File `application` nằm ngoài JAR.
4. File `application-{profile}` nằm ngoài JAR.

Một file bên ngoài thông thường vì vậy có thể ghi đè giá trị trong file theo profile đóng gói. Không nên chỉ dựa vào tên `application-prod.yml` để cho rằng nó luôn thắng tất cả các nguồn còn lại.

### Ví dụ cùng một thuộc tính xuất hiện ở bốn nơi

Giả sử `app.catalog.connect-timeout` có các giá trị:

| Nguồn | Giá trị |
|---|---|
| `classpath:/application.yml` | `5s` |
| `file:./config/application.yml` | `3s` |
| Biến môi trường `APP_CATALOG_CONNECTTIMEOUT` | `2s` |
| Dòng lệnh `--app.catalog.connect-timeout=1s` | `1s` |

Nếu cả bốn nguồn đều được áp dụng, giá trị hiệu lực theo các quy tắc thông thường là `1s` vì tham số dòng lệnh có độ ưu tiên cao nhất trong nhóm đó.

Nếu bỏ tham số dòng lệnh, biến môi trường `2s` sẽ được sử dụng. Nếu cũng bỏ biến môi trường, file bên ngoài `3s` sẽ được dùng. Nếu không có cấu hình bên ngoài, ứng dụng quay về giá trị đóng gói `5s`.

Thứ tự ưu tiên giúp người vận hành thay đổi một thuộc tính cụ thể mà không cần sao chép toàn bộ file cấu hình mặc định.

## 5. Cấu hình bằng biến môi trường

Biến môi trường được truyền cho tiến trình khi ứng dụng khởi chạy. Chúng rất hữu ích trong Docker, Kubernetes, CI/CD và các nền tảng triển khai cloud vì có thể đặt khác nhau cho từng instance mà không phải sửa artifact.

Spring Boot hỗ trợ relaxed binding: tên thuộc tính dạng kebab-case được chuyển đổi để ánh xạ tới các biến môi trường.

Quy tắc thông dụng khi chuyển một tên thuộc tính chuẩn sang biến môi trường:

1. Thay dấu chấm `.` bằng dấu gạch dưới `_`.
2. Bỏ dấu gạch nối `-` trong mỗi thành phần tên.
3. Chuyển sang chữ hoa.

Ví dụ:

| Property chuẩn | Biến môi trường |
|---|---|
| `spring.application.name` | `SPRING_APPLICATION_NAME` |
| `server.port` | `SERVER_PORT` |
| `app.catalog.base-url` | `APP_CATALOG_BASEURL` |
| `app.catalog.connect-timeout` | `APP_CATALOG_CONNECTTIMEOUT` |
| `app.catalog.enabled` | `APP_CATALOG_ENABLED` |

Trong terminal Linux/macOS:

~~~bash
export APP_CATALOG_BASEURL=https://catalog-prod.example.test
export APP_CATALOG_CONNECTTIMEOUT=2s
export APP_CATALOG_ENABLED=true

java -jar catalog-service.jar
~~~

Trong Windows PowerShell:

~~~powershell
$env:APP_CATALOG_BASEURL = "https://catalog-prod.example.test"
$env:APP_CATALOG_CONNECTTIMEOUT = "2s"
$env:APP_CATALOG_ENABLED = "true"

java -jar catalog-service.jar
~~~

Các giá trị có mặt trong environment của tiến trình con khi ứng dụng được khởi chạy từ shell đó.

### Lưu ý về dấu gạch nối

Với `app.catalog.connect-timeout`, biến môi trường đúng theo quy tắc relaxed binding là `APP_CATALOG_CONNECTTIMEOUT`, không phải `APP_CATALOG_CONNECT_TIMEOUT`. Dấu gạch nối trong tên thuộc tính được **bỏ đi**, không chuyển thành một dấu gạch dưới mới.

Nếu thuộc tính là một danh sách hoặc map, quy tắc binding của chỉ mục và key có thể có thêm chi tiết. Khi cấu hình phức tạp, nên dùng `@ConfigurationProperties` và kiểm tra kết quả bind thực tế thay vì đoán tên biến môi trường.

### Thời điểm đọc biến môi trường

Biến môi trường thông thường được Spring Boot đọc trong quá trình khởi động ứng dụng. Thay đổi biến trong một shell khác sau khi JVM đã chạy không làm Environment của tiến trình đang chạy tự cập nhật.

Muốn thay giá trị cho lần chạy tiếp theo, hãy cấu hình biến môi trường trong manifest, service definition hoặc môi trường thực thi và khởi động lại ứng dụng theo quy trình triển khai.

## 6. Cấu hình bằng tham số dòng lệnh

Spring Boot nhận các application arguments theo dạng:

~~~text
--property.name=value
~~~

Ví dụ:

~~~bash
java -jar catalog-service.jar \
  --app.catalog.base-url=https://catalog-cli.example.test \
  --app.catalog.connect-timeout=1s \
  --app.catalog.enabled=true
~~~

Các tham số bắt đầu bằng `--` được Spring Boot đưa vào command-line property source khi tính năng này được bật theo mặc định. Chúng có độ ưu tiên cao hơn các nguồn thông thường như file cấu hình và biến môi trường.

Cần phân biệt:

~~~text
java -Dserver.port=9090 -jar catalog-service.jar
java -jar catalog-service.jar --server.port=9090
~~~

Dòng thứ nhất dùng **Java system property** thông qua `-D` (đặt trước `-jar`). Dòng thứ hai dùng **Spring Boot application argument** bắt đầu bằng `--` (đặt sau tên JAR). Cả hai đều có thể cung cấp cấu hình, nhưng là hai loại property source khác nhau với mức ưu tiên khác nhau.

### Khi nào nên dùng dòng lệnh?

Tham số dòng lệnh phù hợp khi:

- Cần thử nhanh một giá trị mà không sửa file.
- Chạy một batch job chỉ một lần với cấu hình riêng.
- Pipeline triển khai cung cấp một vài override rõ ràng.
- Cần chỉ định profile hoặc vị trí file cấu hình ngay khi khởi động.

Không nên truyền password, token hoặc private key trực tiếp trên dòng lệnh nếu môi trường có nguy cơ lộ process arguments trong danh sách tiến trình, log triển khai hoặc lịch sử shell. Hãy ưu tiên cơ chế quản lý secret phù hợp.

### Nếu không muốn dùng command-line properties

Có thể vô hiệu hóa cơ chế đưa application arguments thành property source khi tạo `SpringApplication`:

~~~java
SpringApplication application = new SpringApplication(Application.class);
application.setAddCommandLineProperties(false);
application.run(args);
~~~

Trong trường hợp đó, các giá trị `--...` vẫn có thể là application arguments mà code nhận được qua cơ chế args, nhưng chúng không còn được SpringApplication tự đưa vào Environment theo cách mặc định.

Chỉ thay đổi hành vi này khi có yêu cầu rõ ràng; phần lớn ứng dụng nên giữ cơ chế command-line override tiêu chuẩn của Spring Boot.

## 7. Profile kết hợp với các nguồn cấu hình

Profile cho phép kích hoạt các giá trị theo môi trường hoặc nhóm chức năng. Ví dụ, classpath có:

~~~text
src/main/resources/
├── application.yml
├── application-dev.yml
└── application-prod.yml
~~~

`application.yml` chứa giá trị chung:

~~~yaml
app:
  catalog:
    connect-timeout: 5s
    enabled: true
~~~

`application-prod.yml` chỉ ghi đè những giá trị riêng cho production:

~~~yaml
app:
  catalog:
    base-url: https://catalog-prod.example.test
    connect-timeout: 2s
~~~

Kích hoạt profile bằng dòng lệnh:

~~~bash
java -jar catalog-service.jar --spring.profiles.active=prod
~~~

Hoặc bằng biến môi trường:

~~~bash
export SPRING_PROFILES_ACTIVE=prod
java -jar catalog-service.jar
~~~

Khi profile `prod` có hiệu lực, Spring Boot nạp các tài liệu config data tương ứng theo quy tắc ưu tiên. Các property không được ghi đè vẫn có thể lấy từ `application.yml` hoặc các nguồn khác.

Một cách khác là dùng nhiều YAML document và `spring.config.activate.on-profile`:

~~~yaml
app:
  catalog:
    connect-timeout: 5s
---
spring:
  config:
    activate:
      on-profile: prod

app:
  catalog:
    connect-timeout: 2s
~~~

Document thứ hai chỉ được áp dụng khi profile `prod` đang hoạt động.

**Không đặt `spring.profiles.active` bên trong document chỉ được kích hoạt bằng `spring.config.activate.on-profile`.** Thuộc tính kích hoạt profile phải được cung cấp từ nguồn thích hợp trước khi Boot quyết định document theo profile nào được áp dụng.

Nếu một thuộc tính đồng thời có trong file theo profile và biến môi trường, nguồn biến môi trường vẫn có thể ghi đè theo mức ưu tiên của nó. Profile không làm đảo ngược toàn bộ thứ tự ưu tiên giữa các nguồn.

## 8. Chỉ định vị trí file bằng spring.config.location

Theo mặc định Spring Boot tìm Config Data tại các vị trí chuẩn. Khi muốn thay đổi hẳn vị trí tìm kiếm, có thể cung cấp `spring.config.location` từ môi trường khởi chạy:

~~~bash
java -jar catalog-service.jar \
  --spring.config.location=optional:file:/etc/catalog/application.yml
~~~

Ví dụ này chỉ định file `/etc/catalog/application.yml`. Prefix `optional:` cho phép không tìm thấy vị trí đó mà không làm startup thất bại chỉ vì location bị thiếu.

Các dạng vị trí thường gặp:

~~~text
classpath:/custom/
file:./custom/
file:/etc/catalog/application.yml
optional:file:./custom/
~~~

Vị trí thư mục cần kết thúc bằng `/` để Spring Boot có thể ghép tên file cấu hình tiêu chuẩn như `application.yml`. Vị trí file được chỉ định với tên file cụ thể.

**`spring.config.location` thay thế danh sách vị trí tìm kiếm mặc định.** Nếu chỉ định riêng một file ở nơi khác, không nên mặc định rằng các vị trí classpath và `./config/` vẫn được nạp như trước.

Vì thuộc tính này được dùng rất sớm để quyết định nơi đọc Config Data, hãy truyền nó bằng tham số dòng lệnh, biến môi trường như `SPRING_CONFIG_LOCATION` hoặc Java system property. Đừng đặt nó trong một file `application.yml` rồi kỳ vọng Spring Boot đã tìm file đó nhờ chính thuộc tính ấy.

### Bổ sung thay vì thay thế: spring.config.additional-location

Nếu muốn giữ các vị trí mặc định nhưng thêm một nơi chứa cấu hình vận hành, dùng `spring.config.additional-location`:

~~~bash
java -jar catalog-service.jar \
  --spring.config.additional-location=optional:file:./operations/
~~~

Spring Boot vẫn tìm cấu hình mặc định, sau đó xét thêm location được cung cấp. Các giá trị ở location bổ sung có thể ghi đè những giá trị đã nạp từ vị trí mặc định theo quy tắc thứ tự của Config Data.

Điều này phù hợp với mô hình:

- JAR chứa các default.
- `./config/` chứa cấu hình môi trường theo chuẩn.
- `./operations/` chứa override được hệ thống triển khai đưa vào.

Với nhiều locations, có các quy tắc riêng về thứ tự và nhóm location. Khi cấu hình nhiều đường dẫn cùng profile-specific files, hãy xác định độ ưu tiên thực tế, không chỉ dựa vào thứ tự tên thư mục.

## 9. Import thêm Config Data bằng spring.config.import

Đôi khi cần một file cấu hình chính nhưng muốn tham chiếu tới một file bổ sung. Spring Boot hỗ trợ `spring.config.import`.

Ví dụ trong `application.yml`:

~~~yaml
spring:
  config:
    import: optional:file:./config/catalog-extra.yml

app:
  catalog:
    connect-timeout: 5s
~~~

Khi file `./config/catalog-extra.yml` tồn tại, Spring Boot đọc nó như một Config Data được import. Trong trường hợp các thuộc tính trùng nhau, giá trị của document import có độ ưu tiên cao hơn document đã khai báo import.

Ví dụ file import:

~~~yaml
app:
  catalog:
    connect-timeout: 2s
~~~

Giá trị hiệu lực sẽ là `2s` nếu không có một nguồn ưu tiên cao hơn ghi đè nó.

Nếu bỏ `optional:` và file bắt buộc không tồn tại, Spring Boot có thể báo lỗi `ConfigDataLocationNotFoundException` và dừng startup. Đây là hành vi hữu ích khi cấu hình bổ sung thực sự là yêu cầu bắt buộc.

`spring.config.import` khác `spring.config.location`:

- `location`: quyết định danh sách vị trí tìm kiếm Config Data từ rất sớm.
- `additional-location`: thêm vị trí tìm kiếm vào danh sách mặc định.
- `import`: một document cấu hình đang được đọc khai báo thêm nguồn Config Data khác.

Với tài liệu bí mật hoặc thông tin nhạy cảm, không nên đưa giá trị thực vào file đã commit lên Git. Có thể dùng secret manager hoặc cơ chế mount file từ hệ thống triển khai, kết hợp các khả năng import phù hợp.

## 10. Đọc cấu hình trong Java bằng @ConfigurationProperties

Sau khi Spring Boot hợp nhất các nguồn, bean có thể nhận giá trị qua `Environment`, `@Value` hoặc `@ConfigurationProperties`.

Với một nhóm giá trị liên quan, `@ConfigurationProperties` thường là lựa chọn dễ quản lý nhất. Nó hỗ trợ relaxed binding và chuyển đổi kiểu như `Duration`, `URI`, số và boolean.

Ví dụ:

~~~java
import java.net.URI;
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.catalog")
public record CatalogProperties(
        URI baseUrl,
        Duration connectTimeout,
        boolean enabled
) {
}
~~~

Kích hoạt scan cho các configuration properties trong ứng dụng:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class Application {

    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
~~~

Một service có thể inject `CatalogProperties`:

~~~java
import org.springframework.stereotype.Service;

@Service
public class CatalogService {

    private final CatalogProperties properties;

    public CatalogService(CatalogProperties properties) {
        this.properties = properties;
    }

    public String target() {
        return properties.baseUrl().toString();
    }

    public Duration timeout() {
        return properties.connectTimeout();
    }
}
~~~

Khi khởi tạo `CatalogProperties`, Binder đọc các giá trị `app.catalog.*` từ Environment theo thứ tự ưu tiên rồi chuyển đổi sang các kiểu tương ứng. Vì vậy, service không cần biết giá trị đến từ file trong JAR, file bên ngoài, biến môi trường hay dòng lệnh.

Với cấu hình bắt buộc, có thể thêm validation, ví dụ `@Validated` và các constraint Jakarta Validation như `@NotNull`. Ứng dụng cần có validation provider thích hợp, thường qua `spring-boot-starter-validation`, để chạy validation.

### Khi nào dùng Environment hoặc @Value?

Nếu chỉ cần tra cứu một thuộc tính đơn lẻ, có thể đọc bằng `Environment`:

~~~java
String applicationName = environment.getProperty(
        "spring.application.name",
        "catalog-service"
);
~~~

Hoặc dùng `@Value`:

~~~java
public CatalogBanner(
        @Value("${spring.application.name:catalog-service}")
        String applicationName) {
    this.applicationName = applicationName;
}
~~~

`@Value` phù hợp cho giá trị đơn lẻ. Khi cấu hình gồm nhiều trường liên quan, `@ConfigurationProperties` mang lại hợp đồng kiểu dữ liệu rõ hơn, dễ validate và test hơn.

## 11. Tìm nguyên nhân khi giá trị cấu hình không như mong muốn

Nếu ứng dụng nhận sai endpoint, timeout hoặc profile, có thể kiểm tra theo trình tự:

1. Xác nhận tên property được viết đúng, đặc biệt các dấu `-`, `.` và `_`.
2. Kiểm tra file `application.yml` đã được đóng gói vào JAR đúng đường dẫn hay chưa.
3. Kiểm tra working directory thực tế khi chạy để xác định `./config/` trỏ tới đâu.
4. Kiểm tra file bên ngoài có được nạp và có cấu hình trùng với file trong JAR không.
5. Kiểm tra active profiles và các file `application-{profile}` liên quan.
6. Kiểm tra biến môi trường của **chính tiến trình** đang chạy.
7. Kiểm tra tham số dòng lệnh và Java system properties.
8. Kiểm tra `spring.config.location`, `additional-location` hoặc `import` có thay đổi tập file được nạp không.

Spring Boot Actuator có thể cung cấp endpoint `env` và `configprops` để quan sát cấu hình đã nạp và kết quả binding khi được bật phù hợp. Các endpoint này có thể chứa hoặc phản ánh thông tin cấu hình nhạy cảm; cần hạn chế quyền truy cập và sử dụng cơ chế che giấu dữ liệu do Actuator cung cấp.

Có thể dùng `--debug` khi khởi chạy để nhận thêm chẩn đoán về điều kiện auto-configuration, nhưng nó không thay thế việc kiểm tra thứ tự property sources và giá trị bind thực tế.

### Sai working directory

Lệnh:

~~~bash
cd /opt/catalog
java -jar catalog-service.jar
~~~

khác về vị trí `./config/` so với việc đứng ở thư mục khác rồi chạy:

~~~bash
java -jar /opt/catalog/catalog-service.jar
~~~

Trong trường hợp thứ hai, `./config/` được giải quyết dựa trên thư mục hiện tại của shell, không phải `/opt/catalog`. Nếu muốn đường dẫn không phụ thuộc working directory, nên cấu hình location rõ ràng bằng đường dẫn tuyệt đối hoặc thiết lập working directory trong service/container.

### File YAML không được nạp như dự kiến

Kiểm tra indentation của YAML, tên file và profile. Một file tên `application-production.yml` sẽ không tự được sử dụng khi active profile là `prod`. Phải khớp đúng tên profile hoặc khai báo import/location phù hợp.

Nếu tồn tại cả `application.properties` và `application.yml` ở cùng location, hãy kiểm tra ưu tiên định dạng thay vì giả định YAML ghi sau sẽ thắng.

## 12. Bảo mật khi externalize cấu hình

Cơ chế externalized configuration giúp tách cấu hình khỏi code nhưng **không tự biến dữ liệu thành bí mật an toàn**.

- Không commit mật khẩu, access token hoặc private key vào `application.yml` trong source repository.
- Không log toàn bộ Environment hoặc nội dung configuration properties nếu có trường nhạy cảm.
- Hạn chế quyền đọc file cấu hình bên ngoài và volume chứa secret.
- Cân nhắc secret manager, Kubernetes Secret hoặc config tree được mount thay cho việc đặt secret trực tiếp trên command line.
- Tránh đưa secret trong tham số dòng lệnh vì có thể xuất hiện trong danh sách tiến trình hoặc log.
- Sử dụng phân quyền và cơ chế masking cho các endpoint chẩn đoán Actuator.

Biến môi trường thường tiện lợi cho triển khai, nhưng vẫn có rủi ro lộ qua cấu hình container, công cụ debug hoặc log CI. Chọn phương thức cung cấp secret theo mô hình bảo mật của nền tảng, không chỉ theo tính tiện dụng.

## 13. Chọn nguồn cấu hình trong từng tình huống

| Tình huống | Nguồn thường phù hợp | Lý do |
|---|---|---|
| Giá trị mặc định của ứng dụng | Classpath `application.yml` | Đi cùng artifact, dễ quản lý version |
| Giá trị riêng của môi trường triển khai | File ngoài JAR | Không phải build lại artifact |
| Override vài giá trị trong Docker/Kubernetes | Biến môi trường | Dễ tiêm theo container/Pod |
| Thử nghiệm nhanh một giá trị | Dòng lệnh | Áp dụng riêng cho một lần chạy |
| Kích hoạt profile khi start | Dòng lệnh hoặc biến môi trường | Có hiệu lực ở giai đoạn chuẩn bị Config Data |
| Bổ sung thư mục cấu hình vận hành | `spring.config.additional-location` | Giữ nguồn mặc định và thêm override |
| Cấu hình nằm ở vị trí hoàn toàn riêng | `spring.config.location` | Kiểm soát danh sách vị trí tìm kiếm |
| File cấu hình chính tham chiếu file khác | `spring.config.import` | Tách cấu hình thành nhiều nguồn |

Một quy trình triển khai đơn giản có thể bắt đầu bằng file `application.yml` đóng gói với các giá trị mặc định, thêm file ngoài JAR cho môi trường, dùng biến môi trường cho một số override và chỉ dùng command-line properties khi cần một cấu hình riêng cho lần chạy.

Điểm cốt lõi là Spring Boot không yêu cầu bean biết **giá trị đến từ đâu**. `Environment` tổng hợp các property sources theo thứ tự ưu tiên; Binder và các cơ chế injection chuyển chúng thành dữ liệu ứng dụng cần. Khi thiết kế ranh giới giữa classpath, external files, environment variables và command-line arguments rõ ràng, cùng một artifact có thể được triển khai linh hoạt, dễ kiểm soát và ít xảy ra lỗi cấu hình hơn.

