# Kích hoạt một hoặc nhiều profile phía client

Spring Cloud Config Client cần biết ứng dụng đang chạy trong ngữ cảnh nào để yêu cầu đúng bộ cấu hình từ Config Server. Thông tin quan trọng nhất là tên ứng dụng, danh sách profile đang hoạt động và label của repository cấu hình. Profile xác định lớp cấu hình cần áp dụng, còn label xác định phiên bản cấu hình cần lấy.

Trong bài này, dịch vụ `catalog-service` được triển khai với profile `prod`. Dịch vụ cũng cần profile `observability` để bật các thiết lập giám sát dùng chung. Client có thể kích hoạt cả hai profile trong cùng một lần chạy; Config Server nhận danh sách đó và trả về các nguồn cấu hình tương ứng. Các bean trong ứng dụng cũng nhìn thấy danh sách profile đang hoạt động để Spring chọn đúng cấu hình và bean.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Kích hoạt một profile hoặc nhiều profile ở Spring Boot Config Client.
- Phân biệt profile đang hoạt động ở client với profile được dùng trong yêu cầu Config Server.
- Bổ sung profile bằng `spring.profiles.include` hoặc gom nhóm bằng profile group.
- Hiểu cách application name, profile và label xác định bộ cấu hình từ xa.
- Dùng profile trong kiểm thử và trong điều kiện tạo bean.
- Kiểm tra thứ tự cấu hình và xử lý tình huống client nhận sai profile.

## 1. Ba thông tin trong yêu cầu cấu hình

Spring Cloud Config Server cung cấp cấu hình theo ba chiều:

| Thành phần | Ý nghĩa | Ví dụ |
|---|---|---|
| Application | Dịch vụ đang yêu cầu cấu hình | `catalog-service` |
| Profile | Nhóm cấu hình cần áp dụng | `prod,observability` |
| Label | Nhánh, tag hoặc revision của repository cấu hình | `release-2026-11` |

Client có thể gửi yêu cầu tương ứng đến endpoint:

```text
GET http://config-server:8888/catalog-service/prod,observability/release-2026-11
```

Đường dẫn trên minh họa endpoint môi trường của Config Server: `/{application}/{profile}/{label}`. Nếu không chỉ định label, Config Server sử dụng label mặc định được cấu hình ở phía server. Vì vậy, hai client có cùng application name và profile vẫn có thể nhận cấu hình khác nhau nếu chúng yêu cầu label khác nhau.

Profile `prod` cho biết ứng dụng chạy với cấu hình production. Profile `observability` có thể bổ sung cấu hình logging, metrics hoặc tracing. Label `release-2026-11` cố định revision cấu hình mà lần triển khai này sử dụng. Ba giá trị có vai trò riêng và không thay thế lẫn nhau.

## 2. Kích hoạt một profile ở Config Client

Spring Boot đọc thuộc tính `spring.profiles.active` để xác định profile đang hoạt động. Nên chọn profile từ môi trường chạy hoặc tham số triển khai để cùng một artifact có thể được dùng ở nhiều môi trường.

### Dùng biến môi trường

Trên Linux hoặc macOS:

```bash
SPRING_PROFILES_ACTIVE=prod java -jar catalog-service.jar
```

Trên PowerShell:

```powershell
$env:SPRING_PROFILES_ACTIVE = "prod"
java -jar catalog-service.jar
```

Spring Boot ánh xạ biến `SPRING_PROFILES_ACTIVE` thành thuộc tính `spring.profiles.active`. Khi Config Client khởi động, profile `prod` trở thành một phần của ngữ cảnh cấu hình và được dùng khi yêu cầu cấu hình từ Config Server.

### Dùng tham số dòng lệnh

```bash
java -jar catalog-service.jar --spring.profiles.active=prod
```

Tham số dòng lệnh phù hợp khi chạy thử một lần hoặc khi muốn thể hiện profile ngay trong lệnh khởi động. Thuộc tính dòng lệnh có độ ưu tiên cao trong cơ chế cấu hình của Spring Boot, do đó có thể ghi đè giá trị profile được khai báo ở một nguồn có độ ưu tiên thấp hơn.

### Dùng thuộc tính JVM

```bash
java -Dspring.profiles.active=prod -jar catalog-service.jar
```

Thuộc tính `-D` phải được đặt trước `-jar`, vì đây là đối số của JVM. Nếu đặt sau tên JAR, nó được truyền cho chương trình ứng dụng và không có tác dụng như thuộc tính hệ thống JVM.

### Khai báo trong application.yml

Có thể đặt profile mặc định trong `application.yml`:

```yaml
spring:
  profiles:
    active: local
```

Cách này tiện cho một ứng dụng chỉ chạy local trong giai đoạn phát triển. Với ứng dụng có nhiều môi trường, nên để nền tảng chạy ứng dụng chọn profile bằng biến môi trường hoặc tham số triển khai. Nếu ghi cứng `prod` trong artifact, việc chạy lại cùng artifact ở test hoặc local có thể vô tình sử dụng cấu hình sai.

## 3. Kích hoạt nhiều profile cùng lúc

`spring.profiles.active` nhận danh sách profile, phân tách bằng dấu phẩy. Ví dụ, client production cần cấu hình nghiệp vụ và cấu hình giám sát:

```bash
SPRING_PROFILES_ACTIVE=prod,observability java -jar catalog-service.jar
```

Hoặc:

```bash
java -jar catalog-service.jar \
  --spring.profiles.active=prod,observability
```

Spring Boot kích hoạt cả hai profile. Config Client gửi danh sách profile này trong yêu cầu cấu hình; Config Server có thể kết hợp các nguồn chung với các nguồn riêng cho `prod` và `observability`.

Khi nhiều profile cùng khai báo một thuộc tính, thứ tự profile có thể ảnh hưởng đến giá trị được chọn. Trong cơ chế kết hợp tài liệu profile của Spring Boot, profile đứng sau có thể ghi đè giá trị từ profile đứng trước. Vì vậy, hãy chọn thứ tự có chủ đích và kiểm tra các property source thực tế khi có khóa trùng nhau.

Ví dụ, nếu `prod` đặt mức log `INFO` còn `diagnostic` đặt mức log `DEBUG`, việc bật cả hai có thể khiến giá trị sau cùng phụ thuộc thứ tự profile và thứ tự nguồn mà Config Client nhận được. Không nên dựa vào thứ tự ngầm nếu một khóa quan trọng cần có một giá trị duy nhất; hãy đặt khóa đó ở một nguồn có ưu tiên được xác định rõ.

### Profile phụ bằng spring.profiles.include

Nếu mọi lần chạy với một profile đều cần bổ sung một profile khác, có thể khai báo `spring.profiles.include`:

```yaml
spring:
  profiles:
    include:
      - observability
```

Khi client kích hoạt `prod`, profile `observability` cũng được thêm vào nhóm profile hoạt động. Cách này phù hợp với các profile phụ như `metrics`, `tracing` hoặc `diagnostic` cần được bật cùng một cấu hình nền.

Các thuộc tính `spring.profiles.active`, `spring.profiles.default` và `spring.profiles.include` phải được khai báo trong tài liệu cấu hình không gắn profile. Không đặt chúng bên trong `application-prod.yml` hoặc tài liệu chỉ được kích hoạt bởi `prod`, vì Spring cần biết danh sách profile trước khi chọn tài liệu profile-specific.

## 4. Dùng profile group để đặt tên cho một tổ hợp

Khi một môi trường luôn cần nhiều profile phụ, profile group giúp đặt một tên ngắn cho tổ hợp đó:

```yaml
spring:
  profiles:
    group:
      production:
        - prod
        - observability
        - metrics
```

Khi chạy:

```bash
SPRING_PROFILES_ACTIVE=production java -jar catalog-service.jar
```

Spring kích hoạt profile group `production` và các profile thành viên `prod`, `observability`, `metrics`. Config Client sử dụng nhóm profile đã được phân giải để lấy cấu hình tương ứng.

Profile group giúp chuẩn hóa tổ hợp profile trong nhiều manifest triển khai. Nhóm có thể thay đổi thành viên ở một nơi, thay vì lặp lại danh sách dài trong từng môi trường. Khai báo group phải nằm trong tài liệu không gắn profile, thường là `application.yml` hoặc một nguồn cấu hình được nạp sớm.

Phân biệt hai cách bổ sung:

| Cơ chế | Mục đích | Cách dùng điển hình |
|---|---|---|
| `spring.profiles.include` | Thêm profile phụ vào danh sách đang hoạt động | Bổ sung `observability` cho một ứng dụng |
| `spring.profiles.group` | Định nghĩa tên đại diện cho một tập profile | `production` mở rộng thành `prod`, `metrics`, `tracing` |

Không nên tạo group chỉ để che giấu một danh sách profile khó hiểu. Tên group cần thể hiện ý nghĩa vận hành và các profile thành viên phải có mục đích rõ ràng.

## 5. Profile mặc định khi client không chọn profile

Nếu không có profile nào được kích hoạt, Spring sử dụng profile mặc định tên `default`. Config Client vì vậy có thể yêu cầu cấu hình cho profile `default`. Config Server thường tìm các tệp cấu hình chung như `application.yml` hoặc `catalog-service.yml` để trả về giá trị nền.

Có thể đổi profile mặc định:

```yaml
spring:
  profiles:
    default: local
```

Chỉ dùng `local` làm mặc định khi đó là quy ước có chủ đích cho môi trường phát triển. Production nên truyền profile tường minh và có thể kiểm tra profile khi khởi động để tránh kết nối nhầm tài nguyên. Một profile mặc định không phải cách phân biệt môi trường an toàn cho các hệ thống quan trọng.

Trong mã ứng dụng, có thể đọc profile đang hoạt động bằng `Environment`:

```java
import java.util.Arrays;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class ProfileReporter {
    public ProfileReporter(Environment environment) {
        String[] profiles = environment.getActiveProfiles();
        System.out.println("Active profiles: " + Arrays.toString(profiles));
    }
}
```

Ví dụ chỉ nhằm minh họa cách lấy danh sách profile. Trong ứng dụng thực tế, hãy dùng logger của dự án và chỉ ghi tên profile; không ghi giá trị cấu hình hoặc bí mật.

## 6. Cấu hình Config Client để lấy profile từ xa

Ứng dụng cần dependency `spring-cloud-starter-config` tương thích với phiên bản Spring Boot và Spring Cloud đang dùng. Với Config Data integration hiện đại, client khai báo `spring.config.import`:

```yaml
# application.yml của catalog-service
spring:
  application:
    name: catalog-service
  config:
    import: "configserver:http://config-server:8888"
  cloud:
    config:
      label: release-2026-11
```

Trong cấu hình trên:

- `spring.application.name` xác định application name mà Config Server tìm kiếm.
- `spring.profiles.active` được chọn từ môi trường chạy hoặc nguồn cấu hình khác.
- `spring.cloud.config.label` chọn nhánh, tag hoặc revision của repository cấu hình.
- `spring.config.import` khai báo nơi Config Client lấy cấu hình lúc khởi động.

Ví dụ khởi động production với hai profile:

```bash
SPRING_PROFILES_ACTIVE=prod,observability \
SPRING_CLOUD_CONFIG_LABEL=release-2026-11 \
java -jar catalog-service.jar
```

Nếu Config Server là thành phần bắt buộc để dịch vụ hoạt động, giữ import ở dạng bắt buộc để ứng dụng báo lỗi khi không lấy được cấu hình. Nếu local có thể chạy bằng cấu hình mặc định khi Config Server chưa sẵn sàng, dùng tiền tố `optional:` một cách có chủ đích:

```yaml
spring:
  config:
    import: "optional:configserver:http://localhost:8888"
```

`optional:` ảnh hưởng đến hành vi khi không tải được nguồn từ xa; nó không làm thay đổi cách profile được kích hoạt. Không nên dùng import optional trong production nếu ứng dụng không thể vận hành an toàn khi thiếu cấu hình từ xa.

### Phân biệt profile của ứng dụng và profile yêu cầu từ xa

Trong cấu hình Config Client có thể gặp thuộc tính `spring.cloud.config.profile` để chỉ định profile dùng cho yêu cầu đến Config Server. Với luồng thông thường, hãy để client lấy profile từ danh sách active profiles của Spring Boot. Chỉ đặt một profile từ xa riêng khi kiến trúc thật sự cần tách cấu hình server khỏi profile dùng để chọn bean tại client; nếu hai danh sách khác nhau, hãy ghi rõ lý do và kiểm thử kết quả.

`@Profile` trong ứng dụng được đánh giá theo active profiles của `Environment`. Việc đổi profile chỉ dùng cho yêu cầu Config Server không tự động làm các bean `@Profile` tại client chuyển sang một profile khác. Vì vậy, thông thường hãy quản lý `spring.profiles.active` làm nguồn sự thật chung.

## 7. Config Server kết hợp cấu hình cho nhiều profile

Config Server dùng application name và danh sách profile để tìm các tệp cấu hình phù hợp trong backend, thường là Git. Với `catalog-service` và các profile `prod,observability`, repository có thể có cấu trúc:

```text
config-repo/
├── application.yml
├── application-prod.yml
├── application-observability.yml
├── catalog-service.yml
├── catalog-service-prod.yml
└── catalog-service-observability.yml
```

Ý nghĩa:

- `application.yml`: cấu hình chung có thể dùng cho nhiều ứng dụng.
- `application-prod.yml`: cấu hình chung cho profile `prod`.
- `application-observability.yml`: cấu hình chung cho profile `observability`.
- `catalog-service.yml`: cấu hình mặc định riêng cho `catalog-service`.
- `catalog-service-prod.yml`: cấu hình riêng cho `catalog-service` khi chạy production.
- `catalog-service-observability.yml`: cấu hình giám sát riêng cho `catalog-service`.

Config Server kết hợp các nguồn phù hợp và trả về danh sách `propertySources`. Config Client đưa các nguồn đó vào quá trình nạp cấu hình của Spring Boot. Mã nghiệp vụ tiếp tục đọc các khóa như `catalog.search.base-url` qua `Environment` hoặc `@ConfigurationProperties`; mã không cần biết giá trị đến từ tệp nào trong Git.

Khi nhiều profile cùng có một khóa, kiểm tra thứ tự `propertySources` mà Config Server trả về và thứ tự các nguồn trong client. Thứ tự kết hợp có thể chịu ảnh hưởng của phiên bản Spring Boot, Spring Cloud, Config Data import và các nguồn cấu hình cục bộ. Hãy tránh giả định rằng một giá trị từ xa luôn ghi đè mọi giá trị cục bộ.

## 8. Thứ tự profile và thứ tự ưu tiên cấu hình

Hai quy tắc thường bị nhầm lẫn:

1. **Thứ tự profile:** quyết định cách các tài liệu theo profile được kết hợp khi nhiều profile cùng hoạt động.
2. **Thứ tự PropertySource:** quyết định nguồn nào cung cấp giá trị khi cùng một khóa xuất hiện ở nhiều nguồn.

Ví dụ client kích hoạt `prod,observability`. Cả hai profile đều có thể cung cấp khóa `logging.level.root`. Nếu profile `observability` được xử lý sau và cùng lớp nguồn có quy tắc last-wins, giá trị của profile này có thể thay thế giá trị `prod`. Sau đó, biến môi trường hoặc tham số dòng lệnh vẫn có thể có độ ưu tiên cao hơn các nguồn Config Data theo quy tắc Spring Boot.

Khi cấu hình quan trọng bị ghi đè, hãy kiểm tra theo trình tự:

1. In tên active profiles qua `Environment.getActiveProfiles()`.
2. Xác nhận đúng application name và label được client sử dụng.
3. Xem các tệp mà Config Server đã ghép cho application và từng profile.
4. Kiểm tra thứ tự `propertySources` trong phản hồi của Config Server.
5. Kiểm tra các nguồn cục bộ như biến môi trường, thuộc tính JVM, tham số dòng lệnh và Config Data bên ngoài.
6. Đọc giá trị cuối cùng bằng `Environment.getProperty(key)` và xác nhận nguồn nào cung cấp nó.

Không in toàn bộ giá trị nguồn cấu hình vào log. Nguồn có thể chứa thông tin xác thực hoặc khóa bí mật. Khi cần chẩn đoán, ưu tiên ghi tên nguồn và tên profile; sử dụng endpoint quản trị có bảo vệ để xem chi tiết theo quyền được cấp.

## 9. Chọn bean theo một hoặc nhiều profile

Spring dùng `@Profile` để điều khiển bean hoặc cấu hình nào được đăng ký. Ví dụ, một adapter HTTP chỉ dùng trong production:

```java
@Configuration
@Profile("prod")
public class ProductionClientConfiguration {
    @Bean
    SearchClient searchClient(SearchProperties properties) {
        return new HttpSearchClient(properties.baseUrl());
    }
}
```

Một bean có thể áp dụng cho một trong nhiều profile bằng mảng tên:

```java
@Component
@Profile({"local", "test"})
public class StubSearchClient implements SearchClient {
    // Trả kết quả giả lập cho local và test.
}
```

Trong annotation dạng mảng, các profile được hiểu theo điều kiện OR: bean được đăng ký khi `local` hoặc `test` đang hoạt động. Nếu cần cả hai profile cùng hoạt động, dùng biểu thức profile:

```java
@Configuration
@Profile("prod & observability")
public class ProductionObservabilityConfiguration {
    // Bean chỉ có mặt khi cả prod và observability cùng hoạt động.
}
```

Spring hỗ trợ các toán tử `!`, `&` và `|` trong biểu thức profile. Khi biểu thức có cả `&` và `|`, dùng dấu ngoặc để thể hiện rõ ý định. Tránh đăng ký hai implementation cùng vai trò trong cùng một tổ hợp profile nếu không có cơ chế chọn bean rõ ràng.

## 10. Kích hoạt nhiều profile trong kiểm thử

Spring Test hỗ trợ kích hoạt một hoặc nhiều profile qua `@ActiveProfiles`:

```java
@SpringBootTest
@ActiveProfiles({"test", "observability"})
class CatalogServiceIntegrationTest {
    // Test dùng cấu hình test và cấu hình quan sát.
}
```

Điều này giúp test có ngữ cảnh cố định, không phụ thuộc biến `SPRING_PROFILES_ACTIVE` của máy lập trình viên. Nếu test cần endpoint động từ Testcontainers, đăng ký chúng bằng `@DynamicPropertySource`:

```java
@DynamicPropertySource
static void registerProperties(DynamicPropertyRegistry registry) {
    registry.add("spring.datasource.url", postgres::getJdbcUrl);
    registry.add("spring.datasource.username", postgres::getUsername);
    registry.add("spring.datasource.password", postgres::getPassword);
}
```

Đoạn mã là phần phương thức trong lớp test có container `postgres` được khởi tạo. Thuộc tính động giúp test dùng đúng địa chỉ và thông tin kết nối mà container cung cấp.

Nếu test chạy trong CI, không để profile test sử dụng endpoint production hoặc secret production. Hãy cấp dữ liệu và tài khoản riêng cho pipeline, đồng thời kiểm tra danh sách active profiles trong log test khi context được khởi tạo.

## 11. Kích hoạt profile bằng mã Java

Trong trường hợp một launcher cần thêm profile phụ theo logic khởi động, có thể dùng `SpringApplication.setAdditionalProfiles` trước khi gọi `run`:

```java
public static void main(String[] args) {
    SpringApplication application =
        new SpringApplication(CatalogApplication.class);
    application.setAdditionalProfiles("observability");
    application.run(args);
}
```

`setAdditionalProfiles` bổ sung profile vào danh sách được kích hoạt. Cách này phù hợp với profile phụ mà launcher luôn cần. Profile môi trường như `local`, `test` hoặc `prod` vẫn nên được chọn từ cấu hình triển khai để có thể thay đổi mà không sửa mã hoặc build lại artifact.

Không thay đổi active profiles sau khi context đã khởi tạo với kỳ vọng mọi bean và Config Client tự tải lại cấu hình. Profile tham gia quyết định quá trình tạo context và chọn bean; muốn thay đổi môi trường chạy, thông thường cần khởi động lại ứng dụng với danh sách profile mới.

## 12. Lưu ý với bootstrap context cũ

Các phiên bản Spring Cloud Config Client cũ có thể sử dụng `bootstrap.yml` và bootstrap context để lấy cấu hình từ xa trước khi tạo context chính. Khi đó, cấu hình kết nối Config Server thường được khai báo qua `spring.cloud.config.uri`, cùng các thuộc tính `spring.cloud.config.name`, `spring.cloud.config.profile` hoặc `spring.cloud.config.label` khi cần tùy chỉnh.

Với các phiên bản hiện đại sử dụng Spring Boot Config Data, `spring.config.import=configserver:...` là cách tích hợp phổ biến. Không sao chép nguyên cấu hình bootstrap cũ sang ứng dụng Config Data mà chưa xác định phiên bản và chế độ bootstrap của dự án. Chọn một cơ chế theo release train đang dùng, rồi kiểm thử profile và label thực sự được gửi đến server.

## 13. Chẩn đoán khi Config Client nhận sai profile

Khi Config Client nhận cấu hình không như mong đợi, kiểm tra lần lượt:

1. Xem `Environment.getActiveProfiles()` để biết các profile thật sự hoạt động.
2. Kiểm tra `SPRING_PROFILES_ACTIVE`, tham số dòng lệnh và thuộc tính JVM tại tiến trình.
3. Kiểm tra `spring.application.name`; tên này phải khớp với quy ước file trong repository cấu hình.
4. Kiểm tra `spring.cloud.config.label` và xác nhận label tồn tại ở backend Git.
5. Gọi endpoint môi trường của Config Server với đúng application, danh sách profile và label để xem các property source được trả về.
6. Kiểm tra log kết nối Config Client và các nguồn cấu hình cục bộ có ghi đè kết quả từ xa hay không.
7. Xác nhận profile group hoặc `spring.profiles.include` có bổ sung profile ngoài dự kiến hay không.

Ví dụ yêu cầu kiểm tra:

```bash
curl http://localhost:8888/catalog-service/prod,observability/release-2026-11
```

Phản hồi môi trường cho biết profile, label và danh sách `propertySources` mà Config Server đã kết hợp. Nếu phản hồi đúng nhưng giá trị cuối cùng trong ứng dụng sai, tiếp tục kiểm tra thứ tự PropertySource ở phía client và các nguồn có độ ưu tiên cao hơn.

## 14. Bảo vệ cấu hình theo profile

Profile giúp chọn cấu hình, nhưng không phải cơ chế phân quyền. Một client có quyền đọc repository hoặc endpoint Config Server có thể yêu cầu các profile mà quyền của nó cho phép. Vì vậy:

- Cấp quyền đọc Config Server theo danh tính workload và môi trường.
- Tách secret local, test và production; không dùng chung tài khoản hoặc token.
- Không commit secret vào `application-prod.yml` hoặc Git repository cấu hình.
- Dùng Vault hoặc secret store để cấp giá trị nhạy cảm cho đúng client.
- Giới hạn quyền truy cập endpoint quản trị và che giấu giá trị nhạy cảm trong thông tin chẩn đoán.
- Ghi nhận application, profile, label và revision đã triển khai để truy vết thay đổi.

Nếu Config Server dùng mã hóa thuộc tính, khóa giải mã phải được bảo vệ bên ngoài repository và chỉ cấp cho thành phần cần thiết. Mã hóa không thay thế xác thực client, phân quyền đọc cấu hình hoặc kiểm soát label.

## 15. Ví dụ triển khai hoàn chỉnh

`catalog-service` cần chạy production cùng cấu hình giám sát. File `application.yml` của client khai báo tên ứng dụng và Config Server:

```yaml
spring:
  application:
    name: catalog-service
  config:
    import: "configserver:http://config-server:8888"
  cloud:
    config:
      label: release-2026-11
```

Nền tảng triển khai khởi động ứng dụng:

```bash
SPRING_PROFILES_ACTIVE=prod,observability \
SPRING_CLOUD_CONFIG_LABEL=release-2026-11 \
java -jar catalog-service.jar
```

Config Client yêu cầu cấu hình cho `catalog-service`, hai profile `prod` và `observability`, cùng label phát hành. Config Server đọc repository Git và trả về cấu hình chung, cấu hình theo từng profile và cấu hình riêng cho ứng dụng. Spring Boot đưa các nguồn nhận được vào `Environment`; `@Profile` chọn bean tương ứng và `@ConfigurationProperties` bind các giá trị vào đối tượng cấu hình.

Khi cần rollback, nhóm vận hành triển khai lại artifact tương ứng với label cấu hình đã biết là ổn định. Việc lưu lại artifact version, active profiles, label và revision Git giúp tái tạo được bộ cấu hình của lần chạy đó.

## 16. Những điểm cần ghi nhớ

- `spring.profiles.active` chọn một hoặc nhiều profile ở Config Client.
- Danh sách profile có thể truyền qua `SPRING_PROFILES_ACTIVE`, tham số dòng lệnh hoặc thuộc tính JVM.
- `spring.profiles.include` bổ sung profile; profile group gom nhiều profile dưới một tên.
- Config Client dùng application name, profile và label để yêu cầu cấu hình từ Config Server.
- Thứ tự profile và thứ tự PropertySource ảnh hưởng đến giá trị cuối cùng khi có khóa trùng nhau.
- `@Profile` chọn bean theo active profiles; `@ActiveProfiles` cố định profile trong kiểm thử.
- Chọn profile trước khi ứng dụng khởi động, kiểm tra profile thực tế và quản lý secret bằng quyền truy cập riêng cho từng môi trường.

Khi quản lý danh sách profile phía client một cách tường minh, mỗi instance có thể yêu cầu đúng lớp cấu hình từ xa và khởi tạo đúng bean cho ngữ cảnh vận hành. Kết hợp profile với label bất biến giúp nhóm kiểm soát cả môi trường lẫn phiên bản cấu hình được phân phối đến từng dịch vụ Spring Boot.
