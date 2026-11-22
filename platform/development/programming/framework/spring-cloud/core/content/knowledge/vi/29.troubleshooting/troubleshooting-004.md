# Cùng thuộc tính có giá trị khác với tệp cấu hình dự kiến

## 1. Hiện tượng

Một ứng dụng Spring Boot có thể đọc cấu hình từ nhiều nguồn cùng lúc: file YAML trong JAR, file bên ngoài JAR, file theo profile, biến môi trường, JVM system property, tham số dòng lệnh, JSON môi trường, Config Server hoặc configuration tree được mount từ nền tảng triển khai.

Vì vậy, nhìn thấy một giá trị trong application.yml chưa đủ để kết luận đó là giá trị mà ứng dụng đang dùng. Ví dụ file chứa:

```yaml
inventory:
  routing:
    timeout: 2s
```

Nhưng log ứng dụng cho thấy timeout là 8s. Đây có thể là hành vi đúng theo thứ tự ưu tiên của Spring Boot: một PropertySource có ưu tiên cao hơn đã cung cấp cùng key và ghi đè giá trị trong file.

Bài này hướng dẫn tìm đúng nguồn của giá trị đang được sử dụng, xác định lý do nguồn đó thắng, rồi sửa ở nơi phát sinh override. Nội dung thuộc chương **Chẩn đoán sự cố** của mô-đun **SPRING_CLOUD_CORE**. Mô-đun tập trung vào các abstraction cốt lõi của Spring Cloud, Spring Cloud Context, cấu hình ngoài, tương thích Spring Boot, discovery, service registry, giao tiếp dịch vụ và kiểm thử, vận hành.

Sau bài học, người học có thể:

- Giải thích vì sao cùng một property có thể được khai báo ở nhiều nguồn.
- Đọc thứ tự ưu tiên PropertySource của Spring Boot.
- Kiểm tra profile, file bên ngoài JAR và spring.config.import.
- Phát hiện override từ environment variable, system property, command line và SPRING_APPLICATION_JSON.
- Truy nguồn giá trị bằng Actuator env và configprops.
- Phân biệt giá trị trong Environment với giá trị đã bind vào bean.
- Chẩn đoán khác biệt giữa Spring Cloud Config Config Data import và legacy bootstrap.
- Sửa cấu hình mà không vô tình làm mất các override hợp lệ khác.

## 2. Nguyên tắc: Spring đọc Environment, không đọc một file duy nhất

Spring Boot nạp các nguồn cấu hình thành những PropertySource trong Spring Environment. Khi cần một key, Spring tìm theo thứ tự ưu tiên; nguồn có ưu tiên cao hơn có thể ghi đè nguồn có ưu tiên thấp hơn.

Ví dụ, cùng key inventory.routing.timeout có thể xuất hiện ở:

| Nguồn | Giá trị |
| --- | --- |
| application.yml đóng gói trong JAR | 2s |
| application-prod.yml đóng gói trong JAR | 3s |
| ./config/application-prod.yml bên ngoài JAR | 5s |
| Biến môi trường INVENTORY_ROUTING_TIMEOUT | 8s |
| Tham số JVM -Dinventory.routing.timeout=9s | 9s |
| Tham số ứng dụng --inventory.routing.timeout=10s | 10s |

Nếu tất cả nguồn trên được nạp và cùng khai báo key, giá trị cuối cùng có thể là 10s. Việc file trong JAR vẫn chứa 2s là bình thường; file đó không phải nguồn có ưu tiên cao nhất.

Hãy tách ba câu hỏi:

1. **Nguồn nào khai báo key?** Có thể có nhiều nguồn.
2. **Nguồn nào thắng khi đọc từ Environment?** Đây là nguồn có ưu tiên cao nhất chứa key.
3. **Bean đang giữ giá trị nào?** Bean có thể đã bind lúc khởi động hoặc giữ một giá trị cũ sau refresh.

Chẩn đoán tốt phải trả lời được cả ba câu hỏi.

## 3. Thứ tự ưu tiên PropertySource của Spring Boot

Với Spring Boot 4.1.2, thứ tự tổng thể được tài liệu hóa từ nguồn ưu tiên thấp lên nguồn ưu tiên cao như sau:

| Thứ tự | Nguồn | Ví dụ |
| --- | --- | --- |
| 1 | Default properties | SpringApplication.setDefaultProperties(...) |
| 2 | @PropertySource | File được khai báo trên lớp @Configuration |
| 3 | Config Data | application.yml, profile-specific file, file import |
| 4 | Random value source | random.* |
| 5 | OS environment variables | INVENTORY_ROUTING_TIMEOUT |
| 6 | Java system properties | -Dinventory.routing.timeout=9s |
| 7 | JNDI attributes | java:comp/env |
| 8 | ServletContext init parameters | Tham số context |
| 9 | ServletConfig init parameters | Tham số servlet |
| 10 | SPRING_APPLICATION_JSON | JSON truyền qua environment/system property |
| 11 | Command-line arguments | --inventory.routing.timeout=10s |
| 12 | Test annotation properties | @SpringBootTest(properties = ...) |
| 13 | @DynamicPropertySource | Giá trị động trong test |
| 14 | @TestPropertySource | Test properties |
| 15 | Devtools global settings | Cấu hình devtools trong thư mục người dùng |

Các nguồn xuất hiện sau có thể ghi đè các nguồn trước. Vì vậy, command line thường thắng file YAML; test properties có thể thắng cấu hình ứng dụng khi chạy test.

@PropertySource có một điểm đặc biệt: property source này chỉ được thêm vào Environment khi ApplicationContext bắt đầu refresh. Thời điểm đó quá muộn để cấu hình một số thuộc tính được đọc sớm như logging.* hoặc spring.main.*. Nếu những key này không có hiệu lực, hãy kiểm tra thời điểm nạp thay vì chỉ kiểm tra tên key.

Thứ tự chi tiết có thể thay đổi theo phiên bản Spring Boot và loại ứng dụng. Khi nâng cấp, đối chiếu trang Externalized Configuration của đúng phiên bản đang chạy.

## 4. Kiểm tra file cấu hình và profile

Ngay cả khi không có biến môi trường hay command line override, một file khác vẫn có thể thắng.

### 4.1. Thứ tự các file application

Spring Boot tìm file cấu hình theo thứ tự khái quát:

1. application.properties hoặc YAML ở classpath root trong JAR.
2. File profile-specific trong JAR, ví dụ application-prod.yml.
3. File application.properties hoặc YAML bên ngoài JAR.
4. File profile-specific bên ngoài JAR, ví dụ application-prod.yml.

Các file được tìm thấy sau có thể ghi đè file trước. Ví dụ, nếu JAR chứa:

```yaml
# src/main/resources/application.yml
inventory:
  routing:
    timeout: 2s
```

và thư mục chạy ứng dụng có:

```yaml
# ./config/application-prod.yml
inventory:
  routing:
    timeout: 5s
```

với profile prod đang active, giá trị 5s có thể thắng giá trị 2s trong JAR.

Nếu cùng một thư mục có cả application.properties và application.yml, Spring Boot ưu tiên file .properties. Để tránh khó đoán, nên thống nhất một định dạng trong cùng ứng dụng.

### 4.2. Xác nhận profile thực sự đang active

Kiểm tra các nguồn có thể kích hoạt profile:

- spring.profiles.active trong file cấu hình.
- Environment variable SPRING_PROFILES_ACTIVE.
- JVM system property -Dspring.profiles.active=prod.
- Command line --spring.profiles.active=prod.
- Profile được kích hoạt qua SpringApplication hoặc API môi trường.

Nếu có nhiều profile active, profile được xét sau có thể ghi đè giá trị của profile trước. Ví dụ prod,region-a có thể khiến application-region-a.yml thắng một key đã khai báo trong application-prod.yml.

Kiểm tra cả spring.profiles.include, profile group và tài liệu nhiều phần trong cùng YAML. Một document có spring.config.activate.on-profile chỉ được nạp khi biểu thức profile khớp. Các document trong một file multi-document được xử lý từ trên xuống; document sau có thể ghi đè document trước.

### 4.3. Kiểm tra thư mục làm việc và đường dẫn cấu hình

Đường dẫn tương đối như ./config/application.yml được tính từ working directory của process, không nhất thiết là thư mục chứa JAR.

Hai lệnh sau có ý nghĩa khác nhau:

```bash
# Thêm các vị trí ngoài vào các vị trí mặc định
java -jar app.jar --spring.config.additional-location=optional:file:./config/

# Thay thế tập vị trí mặc định bằng các vị trí được chỉ định
java -jar app.jar --spring.config.location=optional:file:./config/
```

spring.config.location thay thế các vị trí mặc định; spring.config.additional-location thêm vị trí mới và cho phép chúng ghi đè cấu hình mặc định. Nếu ứng dụng chạy trong container, hãy kiểm tra working directory, volume mount và đường dẫn file bên trong container thay vì chỉ xem file trên máy phát triển.

spring.config.name, spring.config.location và spring.config.additional-location được dùng rất sớm để xác định file cần nạp. Chúng phải được đặt trong environment property, system property hoặc command line, không thể chỉ khai báo trong file mà chính chúng đang quyết định cách tìm.

### 4.4. Kiểm tra import và thứ tự Config Data

Một file có thể import thêm file khác:

```yaml
spring:
  config:
    import: optional:file:./secrets/local-overrides.yml

inventory:
  routing:
    timeout: 2s
```

Giá trị từ file import được đặt ngay dưới document khai báo import và có thể ghi đè document đó. Nếu một document import nhiều location, location được liệt kê sau có ưu tiên cao hơn location trước.

Ví dụ:

```yaml
spring:
  config:
    import:
      - optional:file:./defaults.yml
      - optional:file:./runtime-overrides.yml
```

Nếu cả hai file cùng khai báo inventory.routing.timeout, runtime-overrides.yml có thể thắng defaults.yml. Đừng chỉ tìm key trong application.yml; hãy theo hết chuỗi spring.config.import.

## 5. Kiểm tra override từ môi trường chạy

### 5.1. Environment variable

Spring Boot chuyển property name dạng canonical sang tên biến môi trường theo quy tắc:

1. Thay dấu chấm . bằng _.
2. Bỏ dấu gạch ngang -.
3. Chuyển thành chữ hoa.

Ví dụ:

| Property name | Environment variable |
| --- | --- |
| inventory.routing.timeout | INVENTORY_ROUTING_TIMEOUT |
| spring.main.log-startup-info | SPRING_MAIN_LOGSTARTUPINFO |
| spring.cloud.loadbalancer.cache.ttl | SPRING_CLOUD_LOADBALANCER_CACHE_TTL |

Không thay dấu gạch ngang trong tên property bằng một dấu gạch dưới bổ sung. Ví dụ SPRING_MAIN_LOG_STARTUP_INFO không phải cách chuyển đổi chuẩn của spring.main.log-startup-info.

Kiểm tra biến môi trường trong đúng process/container:

```bash
# Linux/macOS
printenv INVENTORY_ROUTING_TIMEOUT

# Hoặc liệt kê các biến có liên quan
env | grep '^INVENTORY_'
```

Trên Kubernetes, kiểm tra cả env, envFrom, ConfigMap, Secret và manifest của Deployment/StatefulSet. Biến môi trường được tạo từ ConfigMap/Secret có thể không giống file YAML mà bạn đang xem trong repository.

### 5.2. JVM system property

Tham số -D được truyền cho JVM có thể ghi đè cấu hình file:

```bash
java -Dinventory.routing.timeout=9s -jar app.jar
```

Kiểm tra script start, Docker ENTRYPOINT, biến JAVA_TOOL_OPTIONS, JDK_JAVA_OPTIONS, cấu hình systemd và tham số JVM của IDE. Một tham số -D có thể được thêm ở pipeline triển khai mà không nằm trong repository ứng dụng.

### 5.3. Command-line argument

Spring Boot mặc định chuyển tham số bắt đầu bằng -- thành property:

```bash
java -jar app.jar --inventory.routing.timeout=10s
```

Command-line properties có ưu tiên cao hơn các nguồn cấu hình file. Kiểm tra command thực tế mà container hoặc process manager khởi chạy, không chỉ kiểm tra Dockerfile hoặc script ở một môi trường khác.

### 5.4. SPRING_APPLICATION_JSON

Một JSON block có thể cung cấp nhiều property cùng lúc:

```bash
SPRING_APPLICATION_JSON='{"inventory":{"routing":{"timeout":"11s"}}}' java -jar app.jar
```

Nguồn JSON này có ưu tiên cao hơn system properties và environment variables trong thứ tự Spring Boot, nhưng thấp hơn command-line arguments. Giá trị JSON null được xem như property thiếu khi resolver tìm giá trị, nên không dùng null để xóa một giá trị ở nguồn có ưu tiên thấp hơn.

## 6. Spring Cloud Config có thể cung cấp một nguồn khác

Nếu ứng dụng dùng Spring Cloud Config, cần xác định Config Client đang sử dụng Config Data import hay legacy bootstrap.

### 6.1. Config Data import

Đây là cách mặc định hiện đại:

```yaml
spring:
  application:
    name: inventory-service
  config:
    import: optional:configserver:https://config.example.com
```

Config Server phục vụ các property source theo application, profile và label. Với cấu hình chia sẻ, response có thể chứa các nguồn như:

1. application.yml
2. application-prod.yml
3. inventory-service.yml
4. inventory-service-prod.yml

Các property source trả về sau có thể ghi đè nguồn trước. Nếu spring.cloud.config.name chứa nhiều tên, thứ tự các tên trong danh sách cũng ảnh hưởng đến ưu tiên.

Config Data import có thể tạo nhiều request Config Server khi khởi động: lần đầu dùng profile default để tìm các profile được kích hoạt, sau đó request thêm cho các profile active. Đây là hành vi bình thường, không nhất thiết là Config Client tải cấu hình trùng.

Với Config Data, dữ liệu được import được xử lý như document bổ sung ngay sau document khai báo import và có thể ghi đè giá trị trong document đó. Vì vậy, nếu application.yml vừa khai báo spring.config.import vừa khai báo inventory.routing.timeout=2s trong cùng document, giá trị 5s từ Config Server có thể thắng giá trị local 2s. Các nguồn có ưu tiên cao hơn trong Environment, chẳng hạn environment variable hoặc command line, vẫn có thể ghi đè remote value.

Có thể gọi trực tiếp Config Server để xem các property sources mà server trả về, ví dụ GET /inventory-service/prod. So sánh thứ tự các nguồn application, application-prod, inventory-service và inventory-service-prod; nguồn được trả về sau có thể ghi đè nguồn trước.

Vị trí URL trong spring.config.import có ưu tiên hơn spring.cloud.config.uri. Nếu hai giá trị khác nhau, client có thể kết nối tới server trong import chứ không phải URI bạn đang kiểm tra.

Tiền tố optional: có nghĩa ứng dụng vẫn có thể khởi động khi Config Server không kết nối được. Trong trường hợp đó, ứng dụng có thể chỉ dùng các nguồn local và cho ra giá trị khác với cấu hình remote mà bạn kỳ vọng. Nếu Config Server là nguồn bắt buộc, bỏ optional: hoặc bật fail-fast theo hướng dẫn của Config Client để lỗi kết nối được phát hiện ngay khi khởi động.

### 6.2. Legacy bootstrap và remote property override

Ứng dụng cũ có thể dùng bootstrap.yml hoặc spring-cloud-starter-bootstrap. Với config-first bootstrap, remote property sources thường không cho local configuration ghi đè theo mặc định.

Các thuộc tính điều khiển hành vi này:

| Property | Ý nghĩa |
| --- | --- |
| spring.cloud.config.allow-override | Remote property source có cho phép điều chỉnh cách override hay không. |
| spring.cloud.config.override-none=true | Khi được cho phép, remote properties được đặt ở mức ưu tiên thấp nhất để local sources có thể ghi đè. |
| spring.cloud.config.override-system-properties=false | Cho phép system properties, command line và environment variables ghi đè remote properties, nhưng không cho local config files ghi đè. |

Điểm quan trọng: allow-override phải được cấp từ **remote property source**. Đặt nó trong application.yml cục bộ không tự cấp quyền ghi đè cho client.

Các cờ này chỉ có tác dụng với config-first bootstrap. Không dùng chúng để giải thích thứ tự của Config Data import trong ứng dụng hiện đại. Nếu ứng dụng đã chuyển sang spring.config.import, hãy chẩn đoán theo thứ tự Config Data và PropertySource thực tế.

### 6.3. Config Server overrides

Config Server có thể khai báo spring.cloud.config.server.overrides để cung cấp giá trị chung cho mọi client. Các giá trị này được đặt ở vị trí ưu tiên cao trong property sources của Config Client. Tuy nhiên, tài liệu Spring Cloud lưu ý một configuration system không thể buộc mọi ứng dụng phải sử dụng một giá trị theo mọi cách; ví dụ legacy bootstrap có thể đặt overrideNone=true để các override của server hoạt động giống giá trị mặc định hơn.

Nếu một property luôn xuất hiện với cùng giá trị ở nhiều ứng dụng, hãy kiểm tra:

- File application.yml chung trong config repository.
- Các file shared config được liệt kê trong spring.cloud.config.name.
- spring.cloud.config.server.overrides.
- Branch/label mà client thực sự yêu cầu.
- Remote property override policy nếu đang dùng legacy bootstrap.

## 7. Truy nguồn giá trị bằng Actuator

Spring Boot cung cấp hai endpoint đặc biệt hữu ích:

- env: cho biết property sources trong Environment, nguồn chứa property và origin nếu có.
- configprops: cho biết các bean @ConfigurationProperties sau khi bind.

Để dùng qua HTTP, cần expose endpoint tương ứng và bảo vệ bằng authentication/authorization. Ví dụ cấu hình chỉ dành cho môi trường chẩn đoán:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,env,configprops
```

Không expose env và configprops ra mạng công khai. Các endpoint này có thể tiết lộ cấu trúc cấu hình và thông tin nhạy cảm; giá trị nhạy cảm được sanitize mặc định nhưng vẫn phải giới hạn quyền truy cập.

### 7.1. Xem một property cụ thể

Gọi endpoint env với canonical property name:

```bash
curl -u "$OPS_USER:$OPS_PASSWORD" \
  http://localhost:8080/actuator/env/inventory.routing.timeout
```

Response có thể cho biết:

- Giá trị hiện tại của property.
- Tên PropertySource đang cung cấp giá trị được chọn.
- Danh sách property sources theo thứ tự ưu tiên.
- Origin của giá trị, ví dụ file và số dòng nếu nguồn hỗ trợ origin tracking.

Ví dụ rút gọn:

```json
{
  "property": {
    "source": "systemEnvironment",
    "value": "8s"
  },
  "propertySources": [
    {
      "name": "commandLineArgs"
    },
    {
      "name": "systemProperties"
    },
    {
      "name": "systemEnvironment",
      "property": {
        "origin": "System Environment Property \"INVENTORY_ROUTING_TIMEOUT\"",
        "value": "8s"
      }
    }
  ]
}
```

Đây là ví dụ minh họa cấu trúc, không phải response cố định của mọi phiên bản. Nếu commandLineArgs không chứa key, nguồn systemEnvironment có thể là nguồn thắng. Hãy đọc property.source và propertySources thực tế.

### 7.2. Xem giá trị đã bind vào bean

Nếu Environment cho thấy 8s nhưng bean vẫn dùng 2s, kiểm tra configprops:

```bash
curl -u "$OPS_USER:$OPS_PASSWORD" \
  http://localhost:8080/actuator/configprops
```

Tìm prefix của lớp @ConfigurationProperties đang chứa property, ví dụ inventory.routing. So sánh giá trị bound với giá trị ở env.

| Kết quả | Hướng điều tra |
| --- | --- |
| env và configprops cùng giá trị ngoài dự kiến | Tìm nguồn override trong Environment. |
| env đúng, configprops khác | Kiểm tra binding, prefix, kiểu dữ liệu, validation và thời điểm khởi tạo. |
| configprops đúng, hành vi runtime khác | Kiểm tra bean khác, cache, object giữ state hoặc code ghi đè sau binding. |
| Mọi endpoint đều đúng nhưng log cũ | Kiểm tra instance/pod đang xem và log có thuộc instance đó không. |

Giá trị trong env hoặc configprops có thể được sanitize thành ******. Không bật hiển thị tất cả secret chỉ để chẩn đoán một timeout. Nếu thật sự cần xem giá trị gốc, giới hạn endpoint và role ở môi trường an toàn, sau đó khôi phục chính sách bảo vệ.

## 8. Chẩn đoán bằng code

Khi không thể dùng Actuator, có thể đọc giá trị thắng và liệt kê các nguồn chứa key.

Ví dụ component chẩn đoán chỉ dành cho môi trường phát triển:

```java
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.PropertySource;
import org.springframework.stereotype.Component;

@Component
public class PropertyOriginDiagnostics {

    private final ConfigurableEnvironment environment;

    public PropertyOriginDiagnostics(ConfigurableEnvironment environment) {
        this.environment = environment;
    }

    public void inspect(String key) {
        String effectiveValue = environment.getProperty(key);
        System.out.println("Effective value for " + key + ": " + effectiveValue);

        for (PropertySource<?> source : environment.getPropertySources()) {
            Object candidate = source.getProperty(key);
            if (candidate != null) {
                System.out.println(
                        "Found in " + source.getName() + ": " + candidate);
            }
        }
    }
}
```

Environment.getProperty(key) trả về giá trị hiệu lực. Vòng lặp cho biết những nguồn nào cùng khai báo key. PropertySources được duyệt theo thứ tự ưu tiên; nguồn đầu tiên tìm thấy key là nguồn được resolver chọn.

Chỉ dùng đoạn code này với key không nhạy cảm. Không log password, token, private key, connection string hoặc toàn bộ Environment trong production. Sau khi chẩn đoán, xóa hoặc vô hiệu hóa component debug.

## 9. Kiểm tra tên key và cách bind

Không phải mọi khác biệt đều do một nguồn có ưu tiên cao hơn. Key sai, prefix sai hoặc cách biểu diễn không đúng cũng tạo ra kết quả giống như property bị bỏ qua.

### 9.1. Dùng canonical kebab-case

Nên khai báo property theo lowercase kebab-case:

```yaml
inventory:
  routing:
    read-timeout: 2s
```

Trong placeholder, cũng nên dùng canonical form:

```java
import java.time.Duration;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class RoutingSettings {

    @Value("${inventory.routing.read-timeout}")
    private Duration readTimeout;

    public Duration getReadTimeout() {
        return readTimeout;
    }
}
```

Với @ConfigurationProperties, Spring Boot hỗ trợ relaxed binding cho các cách viết tương đương như kebab-case, camelCase và environment variable uppercase. Tuy nhiên, dùng một cách viết canonical giúp tìm kiếm, truy nguồn và so sánh dễ hơn.

### 9.2. Kiểm tra biến môi trường đã chuyển đổi đúng chưa

Property inventory.routing.read-timeout được chuyển thành:

```text
INVENTORY_ROUTING_READTIMEOUT
```

Không dùng INVENTORY_ROUTING_READ_TIMEOUT để thay thế dấu gạch ngang. Trong environment variable, dấu chấm thành _, dấu gạch ngang bị bỏ, rồi tên được chuyển thành uppercase.

### 9.3. Kiểm tra prefix và tên trường

Ví dụ:

```java
@ConfigurationProperties(prefix = "inventory.routing")
public class RoutingProperties {

    private Duration timeout;

    public Duration getTimeout() {
        return timeout;
    }

    public void setTimeout(Duration timeout) {
        this.timeout = timeout;
    }
}
```

Class này bind key inventory.routing.timeout. Nếu file khai báo inventory.route.timeout hoặc annotation dùng prefix inventory.client, giá trị sẽ không đi vào field mong đợi.

Kiểm tra thêm:

- Bean đã được đăng ký bằng @ConfigurationPropertiesScan hoặc @EnableConfigurationProperties chưa?
- Prefix trong annotation có khớp cấu trúc YAML không?
- Field có setter/constructor binding phù hợp không?
- Có @Validated, constraint hoặc custom converter nào tác động không?
- Kiểu dữ liệu có được parse đúng không, ví dụ Duration, DataSize, enum hoặc list?

### 9.4. List có quy tắc ghi đè riêng

Khi một list được khai báo ở nhiều nguồn, Spring Boot thay thế toàn bộ list bằng list từ nguồn có ưu tiên cao hơn; nó không tự nối các phần tử của hai list.

Ví dụ:

```yaml
# application.yml
inventory:
  routing:
    regions:
      - region-a
      - region-b
```

```yaml
# application-prod.yml
inventory:
  routing:
    regions:
      - region-c
```

Trong profile prod, list hiệu lực có thể chỉ còn region-c, không phải ba phần tử. Nếu muốn giữ các giá trị chung, hãy khai báo đầy đủ list trong nguồn override hoặc dùng cấu trúc map phù hợp với mục đích.

## 10. Kiểm tra giá trị sau khi ứng dụng đã khởi động

Một trường hợp khác là giá trị trong Environment đã thay đổi nhưng object đang chạy vẫn giữ giá trị cũ.

Điều này có thể xảy ra khi:

- Bean đọc property một lần trong constructor hoặc @PostConstruct.
- Một object khác đã sao chép giá trị vào field riêng.
- Bean không thuộc @RefreshScope và không được rebinding.
- Cấu hình đã được refresh nhưng component sử dụng reference/state cũ.
- Có cache nội bộ hoặc connection pool không hỗ trợ thay đổi động.

Với Spring Cloud Context, @RefreshScope cho phép bean được tạo lại khi refresh scope được làm mới:

```java
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.cloud.context.config.annotation.RefreshScope;
import org.springframework.stereotype.Component;

@RefreshScope
@Component
@ConfigurationProperties(prefix = "inventory.routing")
public class RoutingProperties {

    private Duration timeout = Duration.ofSeconds(2);

    public Duration getTimeout() {
        return timeout;
    }

    public void setTimeout(Duration timeout) {
        this.timeout = timeout;
    }
}
```

Sau khi refresh, scope tạo lại target bean khi được truy cập. Không phải mọi bean trong ứng dụng đều tự động được refresh. Với @ConfigurationProperties, Spring Cloud có cơ chế rebinding; hãy kiểm tra bean và property cụ thể thay vì giả định mọi object đã đổi.

Nếu env đã có giá trị mới nhưng bean chưa đổi, xác minh:

1. Bean có nằm trong refresh scope hoặc cơ chế rebinding phù hợp không?
2. Refresh event có thực sự được phát tới instance này không?
3. Bean đang đọc cùng key hay một key alias khác?
4. Component có giữ bản sao giá trị cũ không?
5. Thư viện downstream có hỗ trợ cập nhật cấu hình sau khởi tạo không?

Nếu thành phần không hỗ trợ cập nhật động, dùng rolling restart/redeploy thay vì liên tục gọi refresh.

## 11. Quy trình chẩn đoán theo thứ tự

Khi một property khác với file dự kiến, thực hiện theo các bước:

1. **Ghi nhận instance:** xác định pod/container/host, process ID, profile active và thời điểm khởi động.
2. **Chọn canonical key:** chuẩn hóa tên property về lowercase kebab-case.
3. **Đọc giá trị hiệu lực:** dùng Environment.getProperty hoặc Actuator env.
4. **Xác định nguồn thắng:** xem property.source, tên PropertySource và origin.
5. **Liệt kê các nguồn khác:** tìm cùng key trong classpath, thư mục ngoài JAR, profile files, import, environment, system properties, JSON và command line.
6. **Kiểm tra profile:** xác minh spring.profiles.active, profile include/group và thứ tự profile.
7. **Kiểm tra Config Data:** lần theo spring.config.import, spring.config.location, spring.config.additional-location và working directory.
8. **Nếu dùng Config Server:** kiểm tra application name, profile, label, response property sources và bootstrap mode.
9. **So sánh bean:** dùng configprops hoặc log có kiểm soát để so giá trị đã bind với Environment.
10. **Sửa đúng nguồn:** xóa override không mong muốn hoặc thay giá trị tại nguồn chủ đích.
11. **Khởi động/refresh lại:** thực hiện theo khả năng cập nhật của bean.
12. **Xác minh lần nữa:** đọc lại property source và hành vi runtime trên từng instance.

## 12. Bật log để biết file nào được nạp

Nếu chưa rõ Spring Boot đã đọc file nào, tăng log của Config Data loader:

```yaml
logging:
  level:
    org.springframework.boot.context.config: TRACE
```

Hoặc truyền qua command line:

```bash
java -jar app.jar --logging.level.org.springframework.boot.context.config=TRACE
```

Log giúp xác định location được kiểm tra, file được nạp, profile được xét và import được xử lý. Thuộc tính logging.* được đọc sớm, vì vậy nên đặt nó qua environment, system property hoặc command line nếu cần chẩn đoán ngay từ đầu.

Sau khi tìm được nguồn gây override, đưa log về mức bình thường để tránh log quá nhiều trong môi trường production.

## 13. Ví dụ hoàn chỉnh

Giả sử ứng dụng mong muốn inventory.routing.timeout=2s từ file trong JAR.

File trong JAR:

```yaml
# src/main/resources/application.yml
inventory:
  routing:
    timeout: 2s
```

Manifest triển khai lại có:

```yaml
env:
  - name: INVENTORY_ROUTING_TIMEOUT
    value: 8s
```

Ứng dụng chạy với profile prod. Khi gọi:

```bash
curl http://localhost:8080/actuator/env/inventory.routing.timeout
```

nếu property.source là systemEnvironment và origin là biến INVENTORY_ROUTING_TIMEOUT, nguyên nhân đã rõ: manifest triển khai đang ghi đè file trong JAR.

Để sửa:

1. Cập nhật hoặc xóa biến môi trường trong manifest nếu không còn cần override.
2. Triển khai lại workload để process nhận environment mới.
3. Kiểm tra env trả về 2s hoặc giá trị mới được chọn.
4. Kiểm tra configprops cho bean routing.
5. Gửi request thực tế và xác nhận timeout runtime đã thay đổi.

Nếu biến môi trường là override có chủ đích, hãy cập nhật file tài liệu môi trường và release manifest để người vận hành không nhầm giá trị trong JAR là giá trị hiệu lực.

## 14. Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| File trong JAR đúng nhưng giá trị runtime khác | File ngoài JAR hoặc nguồn ưu tiên cao hơn ghi đè | Kiểm tra Actuator env và origin. |
| Chỉ production bị khác | Profile, ConfigMap, Secret hoặc deployment env riêng | Xác nhận profile active và manifest của đúng workload. |
| Local chạy đúng, container sai | Working directory, mounted file hoặc environment trong container khác | Kiểm tra đường dẫn và biến môi trường bên trong container. |
| Giá trị luôn giống nhau ở nhiều service | Shared Config Server source hoặc server overrides | Kiểm tra application.yml, spring.cloud.config.name và server.overrides. |
| Sửa spring.cloud.config.uri nhưng client vẫn kết nối server cũ | URL trong spring.config.import có ưu tiên cao hơn URI | Sửa import location hoặc loại bỏ cấu hình trùng. |
| Local YAML không ghi đè remote Config Server | Ứng dụng dùng legacy bootstrap và remote source không cấp quyền override | Kiểm tra allow-override từ remote và các cờ override đúng mode. |
| Giá trị Environment đúng nhưng bean sai | Binding/prefix/refresh hoặc object giữ state cũ | Kiểm tra configprops, bean registration và lifecycle. |
| Biến môi trường không được nhận | Tên biến chuyển đổi sai | Thay dấu chấm bằng _, bỏ dấu gạch ngang, viết hoa. |
| List bị mất phần tử | List từ nguồn ưu tiên cao thay thế toàn bộ list | Khai báo đầy đủ list trong nguồn override. |
| Actuator env không hiển thị giá trị | Endpoint chưa expose hoặc giá trị được sanitize | Kiểm tra exposure, authorization và sanitization policy. |
| File được sửa nhưng ứng dụng không đổi | File ngoài không được import hoặc ứng dụng chưa restart/refresh | Kiểm tra config location, import và lifecycle. |
| Một số pod có giá trị khác nhau | Pod khởi động với env/config revision khác nhau hoặc refresh không đồng đều | So sánh revision, manifest và env trên từng pod. |

## 15. Thực hành và câu hỏi tự kiểm tra

1. File application.yml chứa timeout=2s, nhưng command line truyền --timeout=5s. Giá trị nào thắng và vì sao?
2. Vì sao application-prod.yml có thể ghi đè application.yml?
3. Khác nhau giữa spring.config.location và spring.config.additional-location?
4. Một file import từ spring.config.import có thể ghi đè document khai báo import theo cách nào?
5. Chuyển spring.main.log-startup-info thành tên environment variable đúng như thế nào?
6. Actuator env và configprops trả lời hai câu hỏi khác nhau nào?
7. Vì sao đặt spring.cloud.config.allow-override=true trong file local không có tác dụng với legacy bootstrap?
8. spring.cloud.config.override-none chỉ có hiệu lực trong chế độ nào?
9. Vì sao Environment có giá trị mới nhưng một bean vẫn giữ giá trị cũ?
10. Khi nhiều profile active, làm thế nào xác định profile nào thắng?
11. Thiết kế các bước kiểm tra để xác định vì sao một pod dùng timeout khác các pod còn lại.

## 16. Tài liệu tham khảo chính thức

- [Spring Boot 4.1 — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Spring Boot 4.1 — Properties and Configuration](https://docs.spring.io/spring-boot/how-to/properties-and-configuration.html)
- [Spring Boot — Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
- [Spring Boot Actuator — Environment Endpoint API](https://docs.spring.io/spring-boot/api/rest/actuator/env.html)
- [Spring Cloud Config — Config Client](https://docs.spring.io/spring-cloud-config/reference/client.html)
- [Spring Cloud Config — Property Overrides](https://docs.spring.io/spring-cloud-config/reference/server/environment-repository/property-overrides.html)
- [Spring Cloud Commons — Configuration Properties](https://docs.spring.io/spring-cloud-commons/reference/configprops.html)
- [Spring Cloud Context — Application Context Services and Refresh Scope](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html)

Khi một property khác với file dự kiến, hãy tìm nguồn thắng trong Environment trước. Sau đó mới điều tra profile, import, Config Server và binding. Cách làm này xác định được nguồn gốc của giá trị, tránh thay đổi nhầm một file vốn không phải nguồn quyết định.
