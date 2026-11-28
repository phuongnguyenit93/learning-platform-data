# Ưu tiên nguồn cấu hình theo cơ chế Config Data

Spring Boot có thể đọc cấu hình từ nhiều vị trí: tệp `application.yml` nằm trong JAR, tệp bên ngoài thư mục chạy, tệp riêng cho profile, tệp được import, biến môi trường, thuộc tính JVM và tham số dòng lệnh. Khi cùng một khóa xuất hiện ở nhiều nơi, ứng dụng cần một quy tắc xác định giá trị nào có hiệu lực.

Từ Spring Boot 2.4, Config Data là cơ chế chuẩn để nạp cấu hình từ tệp và các nguồn được import. Cơ chế này xác định cách tìm vị trí cấu hình, kết hợp tài liệu theo profile và sắp xếp các nguồn được import. Sau khi Config Data được nạp, nó trở thành một phần của `Environment`; các nguồn có độ ưu tiên cao hơn như biến môi trường, thuộc tính JVM hoặc tham số dòng lệnh vẫn có thể ghi đè giá trị từ tệp.

Bài học tập trung vào thứ tự ưu tiên của Config Data và cách đọc kết quả khi nhiều nguồn cùng khai báo một khóa. Đây là nền tảng để cấu hình Spring Cloud Config Client, profile và cấu hình ngoài ứng dụng một cách có thể dự đoán.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích Config Data và vai trò của nó trong quá trình khởi động Spring Boot.
- Phân biệt cấu hình đóng gói trong classpath với cấu hình bên ngoài ứng dụng.
- Dự đoán kết quả khi có `application.yml` và tệp theo profile.
- Hiểu cách `spring.config.import` ảnh hưởng đến thứ tự ưu tiên.
- Phân biệt `spring.config.location` và `spring.config.additional-location`.
- Dùng location group để kiểm soát thứ tự xử lý profile-specific files.
- So sánh Config Data với biến môi trường, thuộc tính JVM và tham số dòng lệnh.
- Chẩn đoán giá trị bị ghi đè bằng `Environment` và danh sách `PropertySource`.

## 1. Config Data là gì?

Config Data là cơ chế Spring Boot sử dụng để tìm, đọc và kết hợp cấu hình trước khi hoàn tất việc tạo `ApplicationContext`. Nguồn cấu hình thường gặp là:

- `application.properties` hoặc `application.yml`.
- Tệp theo profile như `application-prod.yml`.
- Các vị trí classpath hoặc filesystem.
- Tệp được chỉ định qua `spring.config.import`.
- Nguồn ngoài được tích hợp qua Config Data, chẳng hạn Spring Cloud Config Server hoặc config tree.

Config Data không phải một cú pháp tệp mới. Nó là quy trình nạp cấu hình có quy tắc về vị trí tìm kiếm, profile, import và precedence. Sau khi được nạp, các giá trị có thể được đọc qua `Environment`, `@Value` hoặc bind vào `@ConfigurationProperties`.

```text
Các vị trí Config Data
  classpath:/application.yml
  classpath:/config/application.yml
  file:./application.yml
  file:./config/application.yml
  application-prod.yml
  spring.config.import
          |
          v
    Config Data processing
          |
          v
   Environment / PropertySources
          |
          v
     Bean configuration
```

Config Data được xử lý sớm để các thuộc tính quan trọng cho quá trình khởi động có thể được biết trước khi phần lớn bean được tạo. Đây là lý do một số thuộc tính điều khiển việc nạp cấu hình phải được đặt ở nguồn sớm, thay vì trong một bean thông thường.

## 2. Quy tắc tổng quát: nguồn được xử lý sau có thể ghi đè nguồn trước

Khi cùng một khóa xuất hiện trong nhiều nguồn cấu hình, nguồn có độ ưu tiên cao hơn sẽ cung cấp giá trị được sử dụng. Trong chuỗi Config Data, các vị trí và tài liệu được xử lý theo thứ tự; nguồn có precedence cao hơn có thể ghi đè giá trị từ nguồn có precedence thấp hơn.

Ví dụ, ứng dụng có cấu hình mặc định:

```yaml
# application.yml
catalog:
  search:
    base-url: http://localhost:9080
    timeout: 3s
```

Và cấu hình production:

```yaml
# application-prod.yml
catalog:
  search:
    base-url: https://search.prod.internal
```

Khi profile `prod` hoạt động, `catalog.search.base-url` nhận giá trị production. Khóa `catalog.search.timeout` không được khai báo trong tệp profile nên vẫn dùng giá trị `3s` từ cấu hình chung.

Spring không hợp nhất chuỗi hoặc cộng các giá trị của cùng một khóa. Nó chọn giá trị từ nguồn ưu tiên cao nhất có khai báo khóa đó. Các khóa không trùng vẫn có thể được lấy từ những nguồn có ưu tiên thấp hơn.

## 3. Vị trí cấu hình mặc định

Nếu không tùy chỉnh các thuộc tính tìm kiếm, Spring Boot tìm Config Data ở các vị trí mặc định, gồm các vị trí classpath và filesystem. Các vị trí thường gặp được xét theo thứ tự từ thấp đến cao như sau:

| Thứ tự | Vị trí | Ví dụ |
|---|---|---|
| 1 | Gốc classpath | `classpath:/application.yml` |
| 2 | Thư mục `config` trong classpath | `classpath:/config/application.yml` |
| 3 | Thư mục hiện tại | `file:./application.yml` |
| 4 | Thư mục `config` bên ngoài | `file:./config/application.yml` |
| 5 | Các thư mục con trực tiếp của `config` bên ngoài | `file:./config/*/application.yml` |

Các vị trí bên ngoài ứng dụng có thể ghi đè cấu hình đóng gói trong JAR. Đây là cách triển khai phổ biến: build một artifact, sau đó cấp tệp cấu hình riêng cho từng môi trường mà không cần build lại.

Ví dụ cấu trúc triển khai:

```text
deployment/
├── catalog-service.jar
└── config/
    └── application.yml
```

Nếu JAR chứa `application.yml` với `catalog.search.timeout: 3s`, còn `./config/application.yml` khai báo `catalog.search.timeout: 5s`, giá trị từ tệp bên ngoài được ưu tiên hơn do vị trí filesystem được xử lý sau trong thứ tự mặc định.

Tệp cấu hình bên ngoài thường phù hợp cho endpoint, timeout, mức log và các giá trị thay đổi theo môi trường. Bí mật như password hoặc token nên được cấp từ secret store hoặc nguồn được bảo vệ, thay vì commit vào thư mục triển khai.

## 4. Cấu hình chung và cấu hình theo profile

Spring Boot hỗ trợ tên tệp `application-{profile}.properties` và `application-{profile}.yml`. Tệp profile-specific chỉ được nạp khi profile tương ứng hoạt động.

Ví dụ:

```text
application.yml
application-local.yml
application-test.yml
application-prod.yml
```

Tệp `application.yml` cung cấp giá trị chung. Tệp `application-prod.yml` bổ sung hoặc ghi đè giá trị cho profile `prod`.

```yaml
# application.yml
catalog:
  search:
    base-url: http://localhost:9080
    timeout: 3s
    retry-count: 2
```

```yaml
# application-prod.yml
catalog:
  search:
    base-url: https://search.prod.internal
    timeout: 2s
```

Với `SPRING_PROFILES_ACTIVE=prod`, kết quả là:

| Khóa | Giá trị hiệu lực | Nguồn |
|---|---|---|
| `catalog.search.base-url` | `https://search.prod.internal` | `application-prod.yml` |
| `catalog.search.timeout` | `2s` | `application-prod.yml` |
| `catalog.search.retry-count` | `2` | `application.yml` |

Tài liệu profile-specific có ưu tiên cao hơn tài liệu không gắn profile tương ứng trong cùng quy trình Config Data. Vì vậy, có thể giữ mặc định dùng chung trong một tệp và chỉ khai báo phần khác biệt trong từng profile.

### Khi nhiều profile cùng hoạt động

Có thể kích hoạt nhiều profile, phân tách bằng dấu phẩy:

```bash
SPRING_PROFILES_ACTIVE=prod,observability java -jar catalog-service.jar
```

Khi nhiều profile cùng cung cấp một khóa, profile được xử lý sau có thể ghi đè profile được xử lý trước. Ví dụ, nếu `application-prod.yml` đặt mức log `INFO` và `application-observability.yml` đặt `DEBUG`, profile `observability` đứng sau có thể quyết định giá trị cuối cùng của khóa đó.

Thứ tự profile vì thế là một phần của cấu hình triển khai. Hãy tránh để nhiều profile ghi đè cùng khóa nếu không có chủ đích; nếu cần, xác nhận bằng Environment thực tế thay vì suy luận từ tên profile.

## 5. Nhiều tài liệu trong một YAML

Một tệp YAML có thể chứa nhiều tài liệu, phân tách bằng `---`. Dùng `spring.config.activate.on-profile` để xác định tài liệu nào được áp dụng:

```yaml
# application.yml
catalog:
  search:
    timeout: 3s
    retry-count: 2

---
spring:
  config:
    activate:
      on-profile: prod

catalog:
  search:
    timeout: 2s
```

Tài liệu đầu tiên không gắn profile và luôn được xét. Tài liệu thứ hai chỉ được áp dụng khi profile `prod` hoạt động. Kết quả tương đương việc đặt cấu hình chung trong `application.yml` và cấu hình riêng trong `application-prod.yml`.

Không khai báo `spring.profiles.active`, `spring.profiles.default`, `spring.profiles.include` hoặc `spring.profiles.group` bên trong một tài liệu profile-specific hay tài liệu được kích hoạt bằng `on-profile`. Các thuộc tính này dùng để xác định profile và phải có mặt trong tài liệu không gắn profile.

## 6. Import một nguồn Config Data

`spring.config.import` cho phép thêm một nguồn cấu hình vào quá trình Config Data. Ví dụ import một tệp properties bên ngoài:

```yaml
spring:
  config:
    import: "optional:file:./config/extra.properties"
```

Tiền tố `optional:` cho phép ứng dụng tiếp tục nếu nguồn được import không tồn tại hoặc không thể tải theo điều kiện hỗ trợ của loader. Nếu bỏ `optional:`, nguồn được yêu cầu và lỗi tải có thể làm ứng dụng không khởi động.

Một điểm quan trọng về precedence: dữ liệu được import có ưu tiên cao hơn tài liệu khai báo `spring.config.import`. Vì vậy, nếu cả hai cùng khai báo `catalog.search.timeout`, giá trị trong nguồn được import sẽ thắng giá trị ở tài liệu chứa câu lệnh import.

Ví dụ:

```yaml
# application.yml
spring:
  config:
    import: "file:./config/extra.yml"

catalog:
  search:
    timeout: 3s
```

```yaml
# ./config/extra.yml
catalog:
  search:
    timeout: 5s
```

Kết quả là `catalog.search.timeout=5s`, vì nguồn `extra.yml` được import có precedence cao hơn tài liệu chứa import.

### Nhiều nguồn import

Một tài liệu có thể import nhiều nguồn:

```yaml
spring:
  config:
    import:
      - "optional:file:./config/base.yml"
      - "optional:file:./config/override.yml"
```

Thứ tự import trong tài liệu được giữ khi Config Data xử lý các nguồn. Khi nhiều nguồn import cùng khai báo một khóa, cần xem thứ tự các property source thực tế và kiểm thử giá trị cuối cùng theo phiên bản Spring Boot đang dùng. Không nên dựa vào danh sách import khó hiểu hoặc khai báo lặp cùng một khóa nếu không cần thiết.

Spring Boot chỉ import một nguồn một lần nếu cùng location được khai báo nhiều lần. Nếu nguồn có profile-specific variant, Config Data có thể tìm và nạp biến thể phù hợp với active profiles theo quy tắc của loader.

## 7. Import Spring Cloud Config Server

Spring Cloud Config Client tích hợp với Config Data bằng location `configserver:`. Ví dụ:

```yaml
spring:
  application:
    name: catalog-service
  config:
    import: "configserver:http://config-server:8888"
```

Client yêu cầu cấu hình từ xa theo application name, profile và label. Các nguồn từ Config Server được đưa vào chuỗi Config Data của ứng dụng. Dữ liệu import từ Config Server có precedence cao hơn tài liệu khai báo import theo quy tắc Config Data; các nguồn bên ngoài Config Data như biến môi trường và tham số dòng lệnh vẫn có thể ghi đè chúng theo thứ tự ưu tiên tổng thể của Spring Boot.

Nếu Config Server không bắt buộc trong local, có thể dùng:

```yaml
spring:
  config:
    import: "optional:configserver:http://localhost:8888"
```

Trong production, nếu ứng dụng không thể hoạt động đúng khi thiếu cấu hình từ xa, hãy dùng import bắt buộc và thiết kế readiness/khởi động phù hợp. `optional:` không thay đổi thứ tự ưu tiên; nó thay đổi cách ứng dụng xử lý khi nguồn không thể được tải.

### Nguồn local và nguồn remote cùng khai báo khóa

Khi Config Server và tệp local cùng có `catalog.search.base-url`, kết quả phụ thuộc cách import và thứ tự Config Data. Với import được khai báo trong `application.yml`, giá trị từ Config Server có thể ghi đè giá trị trong tài liệu đó. Nếu cần một nguồn local khác ghi đè remote, hãy đặt nguồn đó ở vị trí có precedence cao hơn theo cơ chế Config Data hoặc cấp giá trị qua biến môi trường/CLI.

Không mặc định rằng mọi giá trị từ Config Server luôn thắng mọi nguồn khác. Hãy kiểm tra danh sách `PropertySource` của client để biết thứ tự thực tế, nhất là khi ứng dụng còn dùng tệp ngoài, nhiều import hoặc cơ chế bootstrap cũ.

## 8. spring.config.location và spring.config.additional-location

Hai thuộc tính này điều khiển nơi Spring Boot tìm Config Data:

| Thuộc tính | Hành vi |
|---|---|
| `spring.config.location` | Thay thế các vị trí tìm kiếm mặc định bằng vị trí được chỉ định. |
| `spring.config.additional-location` | Bổ sung vị trí mới bên cạnh các vị trí mặc định. |

Ví dụ thay thế vị trí mặc định:

```bash
java -jar catalog-service.jar \
  --spring.config.location=file:./deployment-config/
```

Ứng dụng tìm cấu hình ở vị trí được chỉ định. Các vị trí mặc định không còn tự động được sử dụng, trừ khi được khai báo lại.

Ví dụ bổ sung vị trí:

```bash
java -jar catalog-service.jar \
  --spring.config.additional-location=optional:file:./deployment-config/
```

Ứng dụng vẫn tìm các vị trí mặc định và bổ sung thư mục `deployment-config`. Các giá trị trong vị trí bổ sung được xử lý ở mức ưu tiên cao hơn các vị trí mặc định tương ứng, nên có thể ghi đè cấu hình đóng gói.

Các thuộc tính này phải được cung cấp đủ sớm để ảnh hưởng đến quá trình Config Data, ví dụ qua biến môi trường, thuộc tính JVM hoặc tham số dòng lệnh. Không khai báo chúng trong chính tệp mà chúng cần quyết định vị trí tìm kiếm.

## 9. Location groups: dấu phẩy và dấu chấm phẩy

Khi chỉ định nhiều location, dấu phân cách có ý nghĩa:

- Dấu phẩy `,` tách các location group; các group được xử lý theo thứ tự.
- Dấu chấm phẩy `;` đặt nhiều location trong cùng một group, tức cùng một mức ưu tiên khi xử lý tài liệu theo profile.

Ví dụ:

```bash
--spring.config.location=classpath:/cfg/,file:./cfg/
```

Hai location thuộc hai group riêng. Khi xử lý nhiều profile, profile-specific file của group sau có thể ghi đè profile-specific file của group trước.

So với:

```bash
--spring.config.location=classpath:/cfg/;file:./cfg/
```

Hai location nằm trong cùng một group. Cách nhóm này hữu ích khi muốn các tệp profile-specific ở nhiều vị trí được xét cùng một mức trước khi chuyển sang group tiếp theo.

Sự khác nhau trở nên quan trọng khi ứng dụng kích hoạt nhiều profile. Nếu cần thứ tự rõ ràng giữa cấu hình chung, cấu hình theo profile và cấu hình override bên ngoài, hãy dùng location group có chủ đích và kiểm tra kết quả thực tế.

## 10. Thứ tự Config Data trong tổng thể PropertySource

Config Data chỉ là một phần của thứ tự ưu tiên cấu hình tổng thể trong Spring Boot. Một số nguồn phổ biến, xếp từ ưu tiên thấp đến cao, gồm:

| Mức tương đối | Nguồn | Ví dụ |
|---|---|---|
| Thấp | Giá trị mặc định của ứng dụng | `SpringApplication.setDefaultProperties(...)` |
| | `@PropertySource` | Tệp được khai báo trên lớp cấu hình Spring |
| | Config Data | `application.yml`, profile-specific file, import và Config Server |
| | Thuộc tính ngẫu nhiên | `RandomValuePropertySource` |
| | Biến môi trường hệ điều hành | `CATALOG_SEARCH_TIMEOUT` |
| | Thuộc tính hệ thống JVM | `-Dcatalog.search.timeout=7s` |
| | JNDI, ServletContext hoặc ServletConfig | Tham số do container cung cấp trong ứng dụng web |
| | `SPRING_APPLICATION_JSON` | JSON truyền qua biến môi trường hoặc thuộc tính JVM |
| Cao | Tham số dòng lệnh Spring Boot | `--catalog.search.timeout=9s` |
| | Nguồn thuộc tính dành cho test | `@DynamicPropertySource`, `@TestPropertySource`, thuộc tính của `@SpringBootTest` |

Thứ tự đầy đủ có thể có thêm nguồn theo môi trường chạy, test và DevTools. Bảng trên tập trung vào các nguồn thường gặp để minh họa rằng biến môi trường và CLI có thể ghi đè Config Data.

Ví dụ:

```yaml
# application.yml
catalog:
  search:
    timeout: 3s
```

```bash
CATALOG_SEARCH_TIMEOUT=5s java -jar catalog-service.jar \
  --catalog.search.timeout=9s
```

Giá trị hiệu lực là `9s` vì tham số dòng lệnh có precedence cao hơn biến môi trường, và cả hai đều cao hơn Config Data. Điều này hữu ích cho override có chủ đích, nhưng cũng có thể gây khó điều tra nếu pipeline vô tình truyền tham số cũ.

## 11. Thuộc tính điều khiển profile phải được khai báo đúng chỗ

Các thuộc tính điều khiển việc chọn profile ảnh hưởng đến chính quá trình nạp Config Data:

- `spring.profiles.active`: profile được kích hoạt.
- `spring.profiles.default`: profile mặc định khi không có profile active.
- `spring.profiles.include`: bổ sung profile.
- `spring.profiles.group`: gom nhiều profile dưới một tên.

Chúng phải được khai báo trong tài liệu không gắn profile. Không đặt `spring.profiles.active` trong `application-prod.yml` hoặc tài liệu `on-profile: prod`, vì Spring cần biết profile nào hoạt động trước khi quyết định nạp tài liệu đó.

Ví dụ:

```yaml
# application.yml
spring:
  profiles:
    group:
      production:
        - prod
        - observability
```

Khi chạy `--spring.profiles.active=production`, Spring kích hoạt group và các profile thành viên. Các tệp `application-prod.yml` và `application-observability.yml` được xét theo quy tắc profile-specific.

## 12. Chẩn đoán giá trị bị ghi đè

Khi một bean nhận giá trị khác mong đợi, hãy xác định khóa chính xác rồi kiểm tra theo trình tự:

1. Xác nhận profile thực tế bằng `Environment.getActiveProfiles()`.
2. Xác nhận vị trí Config Data đã được nạp, gồm classpath, filesystem và import.
3. Kiểm tra tệp profile-specific có ghi đè tệp chung hay không.
4. Kiểm tra thứ tự các location group và các import.
5. Kiểm tra biến môi trường, thuộc tính JVM, `SPRING_APPLICATION_JSON` và tham số dòng lệnh.
6. Đọc danh sách `PropertySource` theo thứ tự ưu tiên và xác định nguồn đầu tiên có khóa.
7. Nếu dùng Config Server, kiểm tra application name, profile, label và property sources từ xa.

Có thể đọc giá trị cuối cùng qua `Environment`:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.stereotype.Component;

@Component
public class SearchConfigurationReporter {
    private static final Logger log =
        LoggerFactory.getLogger(SearchConfigurationReporter.class);

    public SearchConfigurationReporter(ConfigurableEnvironment environment) {
        String timeout = environment.getProperty("catalog.search.timeout");
        log.info("catalog.search.timeout is configured: {}", timeout != null);

        environment.getPropertySources().forEach(source ->
            log.debug("Property source: {}", source.getName())
        );
    }
}
```

Ví dụ trên chỉ ghi nhận khóa có được cấu hình hay không để tránh lộ giá trị nhạy cảm. Trong một bài kiểm tra local có dữ liệu không nhạy cảm, có thể đọc trực tiếp giá trị để xác nhận.

Không ghi toàn bộ nội dung của mỗi nguồn ra log. Chúng có thể chứa password, token, URL nội bộ hoặc khóa mã hóa. Nếu bật Actuator `env` để chẩn đoán, hãy giới hạn quyền truy cập và cấu hình che giấu giá trị nhạy cảm.

## 13. Những lỗi cấu hình thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Tệp ngoài không ghi đè tệp trong JAR | Dùng `spring.config.location` sai hoặc đường dẫn không được nạp | Kiểm tra đường dẫn, dấu `/` cuối thư mục và dùng `additional-location` nếu muốn bổ sung. |
| Profile không áp dụng | Tên profile sai hoặc chưa được kích hoạt | Kiểm tra `SPRING_PROFILES_ACTIVE` và tên `application-{profile}.yml`. |
| Import không được tải | Thiếu loader, URI sai hoặc nguồn bắt buộc không sẵn sàng | Kiểm tra dependency, scheme và log Config Data. |
| Giá trị từ import không như mong đợi | Hiểu sai precedence giữa imported document và document khai báo import | Kiểm tra property source và thứ tự import. |
| CLI không có tác dụng | Đặt đối số sai cú pháp hoặc truyền cho JVM thay vì ứng dụng | Dùng `--key=value` sau `-jar` cho tham số Spring Boot. |
| Client dùng giá trị khác Config Server | Nguồn local, env hoặc CLI ghi đè remote | Kiểm tra Environment cuối cùng ở client. |

Khi sửa lỗi, thay đổi từng yếu tố một. Nếu đồng thời đổi profile, location, import và biến môi trường, sẽ khó xác định yếu tố nào làm thay đổi kết quả.

## 14. Ví dụ tổng hợp: cùng một JAR cho local và production

Giả sử JAR chứa cấu hình mặc định:

```yaml
# application.yml trong JAR
catalog:
  search:
    base-url: http://localhost:9080
    timeout: 3s
```

Thư mục triển khai production có:

```yaml
# ./config/application-prod.yml
catalog:
  search:
    base-url: https://search.prod.internal
    timeout: 2s
```

Khởi động:

```bash
SPRING_PROFILES_ACTIVE=prod java -jar catalog-service.jar
```

Spring Boot tìm cấu hình đóng gói và cấu hình bên ngoài, sau đó áp dụng profile `prod`. Tệp bên ngoài và profile-specific ghi đè các giá trị tương ứng trong JAR. Nếu deployment còn truyền:

```bash
--catalog.search.timeout=5s
```

thì timeout cuối cùng là `5s`, vì tham số dòng lệnh có độ ưu tiên cao hơn Config Data.

Luồng này cho phép build artifact một lần và triển khai ở nhiều môi trường. Các khác biệt được cấp từ cấu hình bên ngoài và profile; những override tạm thời có thể được truyền qua CLI hoặc biến môi trường, nhưng cần được quản lý để không tạo ra cấu hình khó tái hiện.

## 15. Những điểm cần ghi nhớ

- Config Data là cơ chế Spring Boot tìm, đọc và kết hợp cấu hình trước khi hoàn tất tạo ApplicationContext.
- Tệp bên ngoài có thể ghi đè cấu hình đóng gói trong JAR theo thứ tự vị trí mặc định.
- Tệp profile-specific ghi đè giá trị tương ứng trong tài liệu không gắn profile.
- Dữ liệu được import qua `spring.config.import` có ưu tiên cao hơn tài liệu khai báo import.
- `spring.config.location` thay thế vị trí mặc định; `spring.config.additional-location` bổ sung vị trí.
- Dấu phẩy tạo location group riêng; dấu chấm phẩy đặt nhiều location trong cùng group.
- Biến môi trường, thuộc tính JVM và tham số dòng lệnh có thể ghi đè Config Data theo thứ tự PropertySource tổng thể.
- Kiểm tra active profiles, location, import và property source khi giá trị hiệu lực khác mong đợi.

Nắm được precedence của Config Data giúp bạn dự đoán giá trị cuối cùng trước khi triển khai. Khi cấu hình được tổ chức theo tệp chung, profile, import và vị trí bên ngoài có chủ đích, cùng một ứng dụng Spring Boot có thể chạy nhất quán trên nhiều môi trường và dễ điều tra khi có giá trị bị ghi đè.

## Tài liệu tham khảo

- [Spring Boot – Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Spring Boot – Profiles](https://docs.spring.io/spring-boot/reference/features/profiles.html)
- [Spring Cloud Config – Config Data Import](https://docs.spring.io/spring-cloud-config/reference/client.html)
