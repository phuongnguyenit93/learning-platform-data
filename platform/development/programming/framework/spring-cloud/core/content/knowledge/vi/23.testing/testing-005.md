# Kiểm thử thứ tự PropertySource và profile

Một ứng dụng Spring Cloud thường nhận cấu hình từ nhiều nơi: file `application.yml`, file theo profile, biến môi trường, JVM system properties, tham số dòng lệnh, Config Server và các nguồn do ứng dụng tự đăng ký. Khi chạy test, Spring còn có thể bổ sung giá trị từ `@SpringBootTest(properties)`, `@TestPropertySource` hoặc `@DynamicPropertySource`.

Nếu nhiều nguồn cùng khai báo một key, ứng dụng phải xác định được giá trị nào thắng và vì sao. Kiểm thử thứ tự `PropertySource` giúp phát hiện cấu hình bị ghi đè ngoài ý muốn, kiểm tra profile được kích hoạt đúng, và bảo đảm môi trường test không vô tình dùng endpoint, credential hoặc tài nguyên của môi trường khác.

Bài học thuộc chương **Kiểm thử** của module **SPRING_CLOUD_CORE**. Nội dung tập trung vào Spring `Environment`, `PropertySource`, Spring Boot Config Data, profile, test property sources và cách kiểm chứng giá trị cuối cùng mà bean thực sự nhận được. Các ví dụ dùng Spring Boot và Spring Test; cần đối chiếu phiên bản Spring Boot/Spring Cloud trong BOM của dự án.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích quan hệ giữa `Environment`, `PropertySource` và `PropertyResolver`.
2. Phân biệt thứ tự ưu tiên được công bố trong tài liệu Spring Boot với thứ tự duyệt thực tế trong `Environment`.
3. Xác định nguồn cung cấp giá trị cuối cùng của một property.
4. Kiểm thử thứ tự giữa file mặc định, file theo profile, biến môi trường, system property và command line.
5. Sử dụng `@ActiveProfiles` để kích hoạt profile trong test.
6. Dùng `@SpringBootTest(properties)`, `@TestPropertySource` và `@DynamicPropertySource` đúng mục đích.
7. Kiểm tra các property source được thêm bởi Spring Cloud Config.
8. Nhận diện ảnh hưởng của context caching và dữ liệu động giữa các test.
9. Viết test xác nhận cả giá trị trong `Environment` lẫn giá trị được bind vào `@ConfigurationProperties`.
10. Chẩn đoán lỗi do sai profile, nguồn ưu tiên cao hơn, property source bị thêm sai vị trí hoặc cấu hình test bị dùng lại.

## 2. `Environment` và `PropertySource` là gì?

### 2.1. `Environment` là điểm truy cập cấu hình

Spring `Environment` biểu diễn môi trường của ứng dụng. Nó cho phép đọc property và kiểm tra profile đang hoạt động.

~~~java
@Component
class RegionResolver {

    private final Environment environment;

    RegionResolver(Environment environment) {
        this.environment = environment;
    }

    String currentRegion() {
        return environment.getProperty("app.region", "local");
    }
}
~~~

`Environment` không nhất thiết chứa giá trị cấu hình trong một file duy nhất. Nó tổng hợp nhiều nguồn và áp dụng quy tắc ưu tiên khi cùng một key xuất hiện nhiều lần.

Các thành phần thường dùng cùng cơ chế này:

- `Environment#getProperty(...)`.
- `@Value("${...}")`.
- `@ConfigurationProperties`.
- `Binder`.
- Điều kiện cấu hình dựa trên property.
- Các integration bổ sung nguồn cấu hình như Spring Cloud Config.

### 2.2. `PropertySource` đại diện cho một nguồn

`PropertySource` là abstraction biểu diễn một nguồn key/value. Ví dụ:

| Property source thường gặp | Nguồn dữ liệu |
| --- | --- |
| `systemEnvironment` | Biến môi trường của hệ điều hành |
| `systemProperties` | JVM system properties |
| `applicationConfig: [...]` hoặc nguồn Config Data tương ứng | File application properties/YAML |
| `commandLineArgs` | Tham số dòng lệnh của `SpringApplication` |
| Nguồn test | Giá trị được thêm bởi test framework |
| Nguồn Config Server | Property source từ dịch vụ cấu hình từ xa |
| `MapPropertySource` | Một `Map` được ứng dụng hoặc test thêm vào |

Mỗi nguồn có thể chứa cùng một key. Spring cần biết nguồn nào được ưu tiên để chọn giá trị.

### 2.3. `PropertyResolver` tìm giá trị như thế nào?

Khi gọi:

~~~java
String region = environment.getProperty("app.region");
~~~

Spring duyệt các property source theo thứ tự ưu tiên của `Environment`. Nguồn có giá trị phù hợp đầu tiên sẽ cung cấp kết quả. Nếu một nguồn không chứa key hoặc giá trị được xem như không có, resolver tiếp tục tìm ở nguồn kế tiếp.

Vì vậy, cùng một ứng dụng có thể có:

~~~text
application.yml       -> app.region=global
application-test.yml  -> app.region=test
OS environment        -> APP_REGION=ci
Test property         -> app.region=mock
~~~

Giá trị cuối cùng phụ thuộc nguồn nào có ưu tiên cao hơn trong context đang chạy.

### 2.4. Thứ tự trong `MutablePropertySources`

`ConfigurableEnvironment` cung cấp `MutablePropertySources` để thêm, xóa hoặc sắp xếp nguồn:

~~~java
MutablePropertySources sources =
        configurableEnvironment.getPropertySources();

sources.addFirst(new MapPropertySource(
        "test-high",
        Map.of("app.region", "test")
));

sources.addLast(new MapPropertySource(
        "test-low",
        Map.of("app.region", "fallback")
));
~~~

Các quy tắc quan trọng:

- `addFirst(...)`: thêm nguồn ở vị trí ưu tiên cao.
- `addLast(...)`: thêm nguồn ở vị trí ưu tiên thấp.
- `addBefore(name, source)`: thêm trước một nguồn đã có.
- `addAfter(name, source)`: thêm sau một nguồn đã có.
- `replace(name, source)`: thay nguồn có cùng tên.
- `remove(name)`: xóa nguồn theo tên.

Khi `PropertySourcesPropertyResolver` duyệt collection, nguồn xuất hiện trước được kiểm tra trước. Vì vậy, khi đọc `Environment#getPropertySources()`, hãy hiểu thứ tự iterator thực tế; đừng sao chép máy móc danh sách thứ tự trong tài liệu Spring Boot, vì tài liệu Boot thường trình bày các nguồn theo chiều từ ưu tiên thấp lên ưu tiên cao.

## 3. Kiểm tra nguồn thắng trong Environment

### 3.1. Đọc giá trị cuối cùng

Cách đơn giản nhất là đọc trực tiếp property:

~~~java
String value = environment.getProperty("app.region");
~~~

Đây là giá trị mà các thành phần dùng cùng `Environment` có thể resolve tại thời điểm kiểm tra. Với `@ConfigurationProperties`, cần kiểm tra thêm object đã bind nếu muốn xác nhận quá trình binding.

### 3.2. Liệt kê nguồn chứa một key

Có thể duyệt các property source để tìm nơi đầu tiên chứa key:

~~~java
void logWinningSource(
        ConfigurableEnvironment environment,
        String propertyName
) {
    for (PropertySource<?> source : environment.getPropertySources()) {
        if (source.containsProperty(propertyName)) {
            log.info(
                    "Property {} is supplied by source {}",
                    propertyName,
                    source.getName()
            );
            return;
        }
    }
}
~~~

Ví dụ này chỉ ghi tên nguồn, không ghi giá trị. Trong production, không log giá trị của password, token hoặc secret.

Khi duyệt theo thứ tự thực tế của `PropertySources`, nguồn đầu tiên chứa key là nguồn thắng cho phép resolve thông thường. Nếu property có placeholder hoặc được biến đổi bởi post-processor, giá trị được resolve cuối cùng có thể còn phụ thuộc các bước xử lý khác.

### 3.3. In toàn bộ PropertySource có thể làm lộ dữ liệu

Một số property source chứa password, token, private key hoặc URL có credential. Khi debug, chỉ nên ghi:

- Tên property đang điều tra.
- Tên property source.
- Profile đang active.
- Revision hoặc label cấu hình không nhạy cảm.
- Kết quả kiểm tra có/không có giá trị.

Không in `source.getSource()` hoặc dump toàn bộ `Environment` vào log.

### 3.4. `@PropertySource` có giới hạn về thời điểm

`@PropertySource` trên lớp `@Configuration` được thêm vào Environment trong quá trình refresh context. Một số property như `logging.*` hoặc `spring.main.*` đã được đọc trước thời điểm đó. Do vậy, không dùng `@PropertySource` để cung cấp các cấu hình cần có rất sớm trong startup.

Đối với cấu hình ứng dụng thông thường, ưu tiên Spring Boot Config Data (`application.properties`, `application.yml`, `spring.config.import`) thay vì tự thêm nguồn muộn.

## 4. Thứ tự PropertySource của Spring Boot

### 4.1. Danh sách tổng quát

Tài liệu Spring Boot hiện hành trình bày các nguồn theo thứ tự từ ưu tiên thấp lên ưu tiên cao; nguồn xuất hiện sau có thể ghi đè nguồn xuất hiện trước.

Một danh sách phổ biến trong Spring Boot 4.1 reference là:

| Thứ tự | Nguồn | Ghi chú |
| ---: | --- | --- |
| 1 | Default properties | `SpringApplication.setDefaultProperties(...)` |
| 2 | `@PropertySource` | Được thêm khi context refresh |
| 3 | Config Data | `application.properties`, YAML và dữ liệu import |
| 4 | `RandomValuePropertySource` | Các key `random.*` |
| 5 | OS environment variables | Biến môi trường |
| 6 | Java system properties | `System.getProperties()` |
| 7 | JNDI | `java:comp/env` |
| 8 | `ServletContext` init parameters | Ứng dụng servlet |
| 9 | `ServletConfig` init parameters | Ứng dụng servlet |
| 10 | `SPRING_APPLICATION_JSON` | JSON nhúng trong môi trường hoặc system property |
| 11 | Command line arguments | Ví dụ `--app.region=cli` |
| 12 | `@SpringBootTest(properties)` | Property khai báo trên test annotation |
| 13 | `@DynamicPropertySource` | Giá trị động trong Spring TestContext |
| 14 | `@TestPropertySource` | Test properties từ file hoặc inline |
| 15 | Devtools global settings | Khi DevTools được bật |

Danh sách này cần được đọc theo đúng phiên bản Spring Boot. Không mặc định mọi dự án Spring Boot cũ có chính xác cùng một tập nguồn hoặc cùng thứ tự.

### 4.2. Command line thường ghi đè file cấu hình

Ví dụ file:

~~~yaml
app:
  region: file
~~~

Chạy ứng dụng:

~~~bash
java -jar app.jar --app.region=command-line
~~~

Khi command line properties được thêm vào Environment theo mặc định, giá trị `app.region` là `command-line`. Có thể tắt việc thêm command line properties bằng `SpringApplication.setAddCommandLineProperties(false)`.

### 4.3. Biến môi trường và system property

Ví dụ:

~~~bash
APP_REGION=environment java -jar app.jar
~~~

Hoặc:

~~~bash
java -Dapp.region=system-property -jar app.jar
~~~

Tên biến môi trường được chuyển đổi theo quy tắc relaxed binding; ví dụ `app.region` thường tương ứng `APP_REGION`.

Trong danh sách Spring Boot nêu ở trên, Java system properties được đặt sau OS environment variables, nên có ưu tiên cao hơn. Tuy nhiên, test runner, container runtime hoặc CI có thể thêm các nguồn khác. Hãy kiểm tra `Environment` thực tế thay vì suy luận chỉ từ lệnh chạy.

### 4.4. `SPRING_APPLICATION_JSON`

Có thể đưa một nhóm property vào JSON:

~~~bash
SPRING_APPLICATION_JSON='{"app":{"region":"json","timeout":"2s"}}' java -jar app.jar
~~~

JSON được phân tích và thêm vào Environment. Giá trị `null` trong JSON được xem như thiếu khi resolver tìm property, nên không dùng `null` để xóa hoặc ghi đè một giá trị từ nguồn ưu tiên thấp hơn.

## 5. Thứ tự Config Data và file application

### 5.1. Các vị trí cấu hình mặc định

Spring Boot tự tìm `application.properties`, `application.yaml` hoặc `application.yml` trong các vị trí mặc định như:

- Thư mục gốc classpath.
- `classpath:/config/`.
- Thư mục làm việc hiện tại.
- `./config/`.
- Các thư mục con trực tiếp của `./config/`.

Các vị trí được xử lý theo thứ tự ưu tiên. Nguồn được xử lý sau có thể ghi đè nguồn trước nếu cùng key.

### 5.2. File đóng gói và file bên ngoài

Tài liệu Spring Boot hiện hành mô tả thứ tự Config Data khái quát như sau:

1. `application.properties` đóng gói bên trong JAR.
2. `application-{profile}.properties` đóng gói bên trong JAR.
3. `application.properties` bên ngoài JAR.
4. `application-{profile}.properties` bên ngoài JAR.

Các biến thể YAML cũng tuân theo quy tắc tương ứng. File profile-specific có thể ghi đè file không profile-specific; file bên ngoài có thể ghi đè dữ liệu đóng gói.

Ví dụ:

~~~text
classpath:/application.yml
classpath:/application-test.yml
file:./config/application.yml
file:./config/application-test.yml
~~~

Nếu cùng khai báo `app.region`, giá trị trong nguồn có ưu tiên cao hơn sẽ được chọn.

### 5.3. `spring.config.location` và `spring.config.additional-location`

Hai thuộc tính này có mục đích khác nhau:

- `spring.config.location`: thay thế các vị trí tìm kiếm mặc định.
- `spring.config.additional-location`: thêm vị trí mới sau các vị trí mặc định, để giá trị ở đó có thể ghi đè cấu hình mặc định.

Ví dụ:

~~~bash
java -jar app.jar \
  --spring.config.additional-location=optional:file:./deploy-config/
~~~

Tiền tố `optional:` cho phép ứng dụng tiếp tục nếu location không tồn tại. Nếu location là thư mục, thường cần dấu `/` ở cuối.

`spring.config.name`, `spring.config.location` và `spring.config.additional-location` được đọc rất sớm; hãy cung cấp qua environment variable, system property hoặc command line, không chỉ đặt trong file mà ứng dụng cần tìm.

### 5.4. `spring.config.import`

Config Data có thể import nguồn khác:

~~~yaml
spring:
  config:
    import: optional:file:./extra.yml
~~~

Giá trị từ file được import có thể có ưu tiên cao hơn file đã khai báo import. Khi một property xuất hiện ở nhiều file, hãy xác minh thứ tự import và thứ tự location thay vì chỉ đọc vị trí dòng trong YAML.

### 5.5. Properties và YAML cùng location

Nếu cùng một location có cả `application.properties` và `application.yaml`, Spring Boot ưu tiên file `.properties`. Để giảm nhầm lẫn, nên thống nhất một định dạng cho một nhóm cấu hình.

## 6. Profile và file profile-specific

### 6.1. Profile là gì?

Profile cho phép kích hoạt cấu hình hoặc bean phù hợp với một môi trường hoặc mục đích chạy.

Ví dụ:

- `local`: chạy trên máy lập trình.
- `test`: kiểm thử tự động.
- `staging`: môi trường tiền production.
- `prod`: production.

Profile ảnh hưởng tới cả Config Data và bean được đánh dấu bằng `@Profile`.

### 6.2. File `application-{profile}.yml`

Giả sử có hai file:

~~~yaml
# application.yml
app:
  region: global
  timeout: 5s
~~~

~~~yaml
# application-test.yml
app:
  region: test
  timeout: 2s
~~~

Khi profile `test` được kích hoạt, file `application-test.yml` được nạp và các key trùng có thể ghi đè giá trị trong file mặc định.

Test có thể khai báo:

~~~java
@SpringBootTest
@ActiveProfiles("test")
class ApplicationProfileTest {
    // assertions
}
~~~

### 6.3. Kích hoạt nhiều profile

Có thể kích hoạt nhiều profile:

~~~properties
spring.profiles.active=staging,cloud
~~~

Nếu cả `application-staging.yml` và `application-cloud.yml` cùng khai báo một key, profile được xử lý sau có thể ghi đè profile trước. Tài liệu Spring Boot mô tả chiến lược last-wins cho danh sách profile.

Ví dụ:

~~~yaml
# application-staging.yml
app:
  region: staging
~~~

~~~yaml
# application-cloud.yml
app:
  region: cloud
~~~

Với thứ tự profile `staging,cloud`, giá trị `app.region` là `cloud` nếu cả hai file đều được nạp và không có nguồn ưu tiên cao hơn ghi đè.

### 6.4. Profile mặc định

Nếu không có active profile, Spring `Environment` sử dụng default profile, mặc định có tên `default`. Do đó, file `application-default.yml` có thể được xem xét khi không có profile cụ thể nào được active.

Có thể thay đổi tên default profile bằng `spring.profiles.default`. Không nhầm default profile với một profile luôn được cộng thêm vào mọi active profile.

### 6.5. Kích hoạt document trong YAML

Một file YAML có thể chứa nhiều document, phân tách bằng `---`:

~~~yaml
app:
  region: global
---
spring:
  config:
    activate:
      on-profile: test
app:
  region: test
---
spring:
  config:
    activate:
      on-profile: prod
app:
  region: production
~~~

Document thứ hai chỉ được kích hoạt khi profile `test` khớp; document thứ ba chỉ hoạt động khi `prod` khớp.

Đây là điều kiện kích hoạt Config Data document. Nó khác với `@Profile` trên bean.

### 6.6. Không đặt `spring.profiles.active` trong profile-specific document

`spring.profiles.active` và một số thuộc tính điều khiển profile phải được khai báo ở document không profile-specific. Không dùng một profile-specific document để tự kích hoạt profile khác theo cách không được hỗ trợ.

Nếu cần nhóm profile hoặc include profile, hãy dùng các thuộc tính profile group/include theo tài liệu của phiên bản Spring Boot.

## 7. `@Profile` trên bean và profile trên Config Data

Hai khái niệm thường bị nhầm:

| Cơ chế | Tác động |
| --- | --- |
| `application-test.yml` | Nạp property source khi profile `test` active |
| `spring.config.activate.on-profile` | Kích hoạt một document Config Data theo biểu thức profile |
| `@Profile("test")` | Chỉ đăng ký bean hoặc cấu hình khi profile phù hợp |
| `@ActiveProfiles("test")` | Chỉ định profile cho ApplicationContext được tải bởi Spring TestContext |

Ví dụ:

~~~java
@Configuration(proxyBeanMethods = false)
@Profile("test")
class TestClientConfiguration {

    @Bean
    PaymentGateway paymentGateway() {
        return new FakePaymentGateway();
    }
}
~~~

Bean này chỉ được tạo khi profile `test` đang active. Nó không tự nạp `application-test.yml`; việc nạp file do Config Data thực hiện theo active profiles.

## 8. Spring Cloud Config và remote PropertySource

### 8.1. Config Server là một nguồn cấu hình từ xa

Một Config Client có thể lấy property source từ Spring Cloud Config Server. Với Config Data, cấu hình import thường có dạng:

~~~yaml
spring:
  config:
    import: optional:configserver:
~~~

Nếu bỏ `optional:`, client có thể fail startup khi không truy cập được Config Server. Có thể chỉ rõ URL trong import hoặc qua `spring.cloud.config.uri` theo cách được tài liệu hỗ trợ.

### 8.2. Config Client có thể gửi nhiều request lúc startup

Với Config Data, Spring Boot/Config Client có thể thực hiện hai bước:

1. Lấy cấu hình với profile `default` để tìm thông tin có thể kích hoạt profile bổ sung.
2. Sau khi xác định active profile, lấy tiếp cấu hình theo profile đó.

Vì vậy, thấy nhiều request tới Config Server trong quá trình startup không nhất thiết là lỗi. Khi test, hãy kiểm tra application name, profile và label mà client gửi.

### 8.3. Thứ tự property source từ Config Server

Config Server có thể trả về các property source theo thứ tự, ví dụ:

1. `application.properties`.
2. `application-prod.properties`.
3. `orders-service.properties`.
4. `orders-service-prod.properties`.

Nguồn được trả về sau có thể ghi đè nguồn trước. Nếu `spring.cloud.config.name` liệt kê nhiều tên cấu hình, thứ tự tên trong danh sách cũng có ý nghĩa; tên xuất hiện sau có thể ghi đè tên trước khi cùng khai báo một key.

### 8.4. Kiểm thử theo label/revision

`spring.cloud.config.label` có thể chọn branch, tag hoặc commit mà Config Server sử dụng, tùy backend. Trong test integration, dùng một label riêng hoặc revision cố định để tránh kết quả thay đổi khi repository cấu hình được cập nhật đồng thời.

Không để test tự ý đọc label production hoặc một branch thay đổi liên tục nếu mục tiêu là kiểm tra một kết quả lặp lại được.

### 8.5. Bootstrap legacy và Config Data không giống nhau

Spring Boot 2.4 trở lên đưa Config Data import thành cách kết nối Config Server mặc định. Cơ chế bootstrap cũ vẫn tồn tại trong một số dự án và có thứ tự/override semantics riêng.

Với bootstrap mode, remote property source có thể mặc định có ưu tiên cao hơn cấu hình local. Các thuộc tính như:

- `spring.cloud.config.allow-override`
- `spring.cloud.config.override-none`
- `spring.cloud.config.override-system-properties`

điều khiển một số cách sắp xếp remote property source trong bootstrap mode. Quyền cho phép override cần được cấp từ nguồn cấu hình phía Config Server theo hướng dẫn của Spring Cloud Config; không giả định chỉ đặt `allow-override` ở local client là đủ.

Các thuộc tính này không nên được sao chép vào Config Data mode mà không kiểm tra tài liệu tương ứng. Khi test, xác định rõ ứng dụng đang dùng `spring.config.import=configserver:` hay bootstrap legacy trước khi viết assertion về thứ tự remote/local.

## 9. Test property sources trong Spring Test

### 9.1. Vì sao test cần property source riêng?

Test thường cần thay endpoint, port, credential giả, feature flag hoặc thời gian timeout mà không thay cấu hình ứng dụng. Spring Test cung cấp nhiều cách thêm property:

- `@SpringBootTest(properties = "...")`.
- `@TestPropertySource`.
- `@DynamicPropertySource`.
- `@ActiveProfiles`.
- `ApplicationContextInitializer`.
- `TestPropertyValues` hoặc `ApplicationContextRunner` trong các test nhỏ.

Chọn công cụ theo loại dữ liệu. Giá trị tĩnh phù hợp với inline property; giá trị chỉ có sau khi container khởi động phù hợp với dynamic property.

### 9.2. `@SpringBootTest(properties)`

Ví dụ:

~~~java
@SpringBootTest(properties = {
        "app.region=from-spring-boot-test",
        "app.timeout=750ms"
})
class ClientConfigurationTest {
}
~~~

Các giá trị này được thêm vào Environment của test context và có thể ghi đè cấu hình ứng dụng thông thường. Cách này gọn cho một vài property cố định chỉ dùng trong test đó.

### 9.3. `@TestPropertySource`

Có thể khai báo file:

~~~java
@SpringBootTest
@TestPropertySource(locations = "classpath:/test-config.properties")
class ClientConfigurationTest {
}
~~~

Hoặc khai báo trực tiếp:

~~~java
@SpringBootTest
@TestPropertySource(properties = {
        "app.region=from-test-property-source",
        "app.timeout=500ms"
})
class ClientConfigurationTest {
}
~~~

Nếu cùng annotation có cả `locations` và `properties`, các giá trị inline có ưu tiên cao hơn giá trị đọc từ resource location.

`@TestPropertySource` mặc định hỗ trợ file properties truyền thống và XML. Với Spring Framework 6.1 trở lên, có thể dùng custom `PropertySourceFactory` để hỗ trợ định dạng khác như YAML hoặc JSON. Không giả định `@TestPropertySource("application-test.yml")` tự động được parse như Spring Boot Config Data nếu chưa cấu hình factory phù hợp.

### 9.4. `@DynamicPropertySource`

Khi property phụ thuộc một tài nguyên có địa chỉ chỉ biết lúc chạy, dùng `@DynamicPropertySource`. Trường hợp thường gặp là Testcontainers cấp host và port ngẫu nhiên.

~~~java
@Testcontainers
@SpringBootTest
class DatabaseIntegrationTest {

    @Container
    static final PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }
}
~~~

Phương thức được đánh dấu phải là `static` và nhận một `DynamicPropertyRegistry`. Mỗi property được đăng ký bằng một `Supplier`; supplier chỉ được gọi khi giá trị được resolve.

Không hard-code port ngẫu nhiên của container trước khi container khởi động. Dùng method reference như `postgres::getJdbcUrl` để giá trị được lấy từ container đang chạy.

### 9.5. Lưu ý về thứ tự DynamicPropertySource và TestPropertySource

Tài liệu Spring Framework TestContext hiện hành nói rõ property từ `@DynamicPropertySource` có ưu tiên cao hơn property từ `@TestPropertySource`.

Tuy nhiên, danh sách tổng quát trong trang Externalized Configuration của Spring Boot 4.1.2 liệt kê `@DynamicPropertySource` trước `@TestPropertySource` trong chuỗi nguồn mà trang đó mô tả là nguồn sau có thể ghi đè nguồn trước. Cách trình bày này không thống nhất với phần precedence riêng của Spring Framework TestContext.

Khi hai annotation cùng khai báo một key, không nên dựa vào một bảng tổng quát duy nhất để kết luận kết quả cho mọi tổ hợp và phiên bản. Hãy viết một test nhỏ đọc `Environment#getProperty(...)` và kiểm tra source thắng trên đúng Spring Boot/Spring Framework version mà dự án đang dùng. Với dữ liệu động từ Testcontainers, dùng `@DynamicPropertySource` vì đó là mục đích của API.

### 9.6. Thứ tự inline property và file trong `@TestPropertySource`

Ví dụ:

~~~java
@SpringBootTest
@TestPropertySource(
        locations = "classpath:/test-defaults.properties",
        properties = {
                "app.region=inline-value"
        }
)
class TestPropertySourceOrderTest {
}
~~~

Nếu `test-defaults.properties` cũng khai báo `app.region`, giá trị inline `inline-value` sẽ thắng. Nếu có nhiều `@TestPropertySource` repeatable, các khai báo trực tiếp và thứ tự kết hợp annotation cũng có quy tắc riêng; tránh tạo nhiều lớp annotation lồng nhau nếu không cần thiết.

## 10. Kiểm thử profile bằng `@ActiveProfiles`

### 10.1. Kích hoạt profile trong test

`@ActiveProfiles` là cách khai báo profile cho ApplicationContext do Spring TestContext tải:

~~~java
@SpringBootTest
@ActiveProfiles("test")
class TestProfileConfigurationTest {
}
~~~

Spring Boot sẽ nạp Config Data phù hợp với profile test, ví dụ `application-test.yml`. Các bean có `@Profile("test")` cũng có thể được đăng ký.

### 10.2. Nhiều profile và thứ tự

~~~java
@SpringBootTest
@ActiveProfiles({"staging", "cloud"})
class MultiProfileConfigurationTest {
}
~~~

Khi cả hai profile đều có file cấu hình và cùng định nghĩa một property, profile được xử lý sau có thể ghi đè profile trước. Nên kiểm tra cả danh sách active profiles và giá trị property cuối cùng.

### 10.3. `@ActiveProfiles` và biến `spring.profiles.active`

Khi test class dùng `@ActiveProfiles`, Spring TestContext không dùng giá trị `spring.profiles.active` từ environment variable hoặc JVM system property để tự quyết định active profiles. Nếu muốn cho system property/environment quyết định, cần một `ActiveProfilesResolver` tùy chỉnh.

Đây là điểm quan trọng trong CI: một biến `SPRING_PROFILES_ACTIVE=prod` trên runner không nhất thiết làm test có `@ActiveProfiles("test")` chạy với profile prod. Ngược lại, đừng bỏ `@ActiveProfiles` nếu test cần một profile xác định và an toàn.

### 10.4. Kế thừa profile

`@ActiveProfiles` có thể được kế thừa từ superclass hoặc enclosing class. Mặc định, profile được kế thừa. Dùng `inheritProfiles = false` khi test con cần thay toàn bộ danh sách profile của lớp cha.

~~~java
@ActiveProfiles("integration")
abstract class BaseIntegrationTest {
}

@SpringBootTest
@ActiveProfiles(
        profiles = "isolated",
        inheritProfiles = false
)
class IsolatedConfigurationTest extends BaseIntegrationTest {
}
~~~

Không để lớp base vô tình thêm `prod` hoặc profile không phù hợp vào test con.

## 11. Kiểm thử kết hợp profile và test override

### 11.1. File cấu hình ví dụ

`application.yml`:

~~~yaml
app:
  region: global
  timeout: 5s
  client:
    endpoint: https://default.example.internal
~~~

`application-test.yml`:

~~~yaml
app:
  region: test-profile
  timeout: 2s
  client:
    endpoint: http://localhost:18080
~~~

Test:

~~~java
@SpringBootTest(properties = "app.region=spring-boot-test")
@ActiveProfiles("test")
class ProfileAndTestOverrideTest {

    @Autowired
    Environment environment;

    @Test
    void testPropertyOverridesProfileConfiguration() {
        assertThat(environment.getActiveProfiles())
                .containsExactly("test");

        assertThat(environment.getProperty("app.region"))
                .isEqualTo("spring-boot-test");

        assertThat(environment.getProperty("app.timeout"))
                .isEqualTo("2s");
    }
}
~~~

Test xác nhận:

- `@ActiveProfiles("test")` kích hoạt file profile.
- `app.timeout` đến từ profile test.
- `app.region` bị `@SpringBootTest(properties)` ghi đè.

### 11.2. Kiểm tra cả bean đã bind

Giả sử có:

~~~java
@ConfigurationProperties(prefix = "app")
public record AppProperties(
        String region,
        Duration timeout
) {
}
~~~

Đăng ký type bằng `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties`. Sau đó test cả `Environment` và bean:

~~~java
@Autowired
AppProperties properties;

@Test
void boundPropertiesUseTheWinningValues() {
    assertThat(properties.region()).isEqualTo("spring-boot-test");
    assertThat(properties.timeout()).isEqualTo(Duration.ofSeconds(2));
}
~~~

Điều này giúp phân biệt lỗi ở bước resolve property với lỗi ở bước binding hoặc conversion.

## 12. Kiểm tra thứ tự bằng một test PropertySource cụ thể

### 12.1. Thêm hai MapPropertySource có giá trị trùng nhau

Ví dụ dùng `ApplicationContextRunner`:

~~~java
class PropertySourceOrderTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withInitializer(context -> {
                        MutablePropertySources sources =
                                context.getEnvironment().getPropertySources();

                        sources.addLast(new MapPropertySource(
                                "test-low",
                                Map.of("app.region", "low")
                        ));

                        sources.addFirst(new MapPropertySource(
                                "test-high",
                                Map.of("app.region", "high")
                        ));
                    });

    @Test
    void firstPropertySourceWins() {
        runner.run(context -> {
            Environment environment = context.getEnvironment();

            assertThat(environment.getProperty("app.region"))
                    .isEqualTo("high");
        });
    }
}
~~~

Test này xác nhận quy tắc của `MutablePropertySources`: nguồn được thêm bằng `addFirst` có ưu tiên cao hơn nguồn được thêm bằng `addLast`.

### 12.2. Kiểm tra tên nguồn thắng

Có thể mở rộng test để xác định source name:

~~~java
String winningSource = StreamSupport.stream(
        environment.getPropertySources().spliterator(),
        false
)
.filter(source -> source.containsProperty("app.region"))
.map(PropertySource::getName)
.findFirst()
.orElseThrow();

assertThat(winningSource).isEqualTo("test-high");
~~~

Đoạn mã dùng thứ tự iterator của `PropertySources`, nên nguồn đầu tiên chứa key là nguồn thắng. Chỉ sử dụng property test không nhạy cảm.

### 12.3. Khi cần kiểm tra Config Data thật

`ApplicationContextRunner` thích hợp cho test cấu hình nhỏ, nhưng nó không tự mô phỏng toàn bộ startup Config Data như `SpringApplication`. Nếu mục tiêu là kiểm tra `application.yml`, profile file, `spring.config.import` hoặc Config Server, dùng `@SpringBootTest` hay một test chạy với Config Data loader phù hợp.

Không kết luận thứ tự Config Data chỉ từ một unit test thêm `MapPropertySource`.

## 13. Kiểm tra nhiều profile bằng integration test

### 13.1. Xác nhận profile active

~~~java
@SpringBootTest
@ActiveProfiles({"test", "cloud"})
class ActiveProfileOrderTest {

    @Autowired
    Environment environment;

    @Test
    void expectedProfilesAreActive() {
        assertThat(environment.getActiveProfiles())
                .containsExactly("test", "cloud");
    }
}
~~~

Nếu thứ tự profile có ý nghĩa đối với file cùng khai báo một key, hãy kiểm tra đúng thứ tự, không chỉ kiểm tra có chứa các tên profile.

### 13.2. Xác nhận giá trị last-wins

Giả sử `application-test.yml` có:

~~~yaml
app:
  region: test
~~~

và `application-cloud.yml` có:

~~~yaml
app:
  region: cloud
~~~

Test:

~~~java
assertThat(environment.getProperty("app.region"))
        .isEqualTo("cloud");
~~~

Nếu test thất bại, kiểm tra:

- `@ActiveProfiles` có đúng thứ tự không.
- Profile có thực sự active không.
- Có file ngoài JAR hoặc import khác ghi đè không.
- Có biến môi trường, system property hoặc test property nào có ưu tiên cao hơn không.
- Có Config Server property source nào được thêm vào không.

### 13.3. Kiểm tra profile bean riêng

Có thể dùng `ApplicationContext` để xác nhận bean phù hợp được tạo:

~~~java
assertThat(context).hasBean("testPaymentGateway");
assertThat(context).doesNotHaveBean("productionPaymentGateway");
~~~

Không chỉ kiểm tra `Environment#getActiveProfiles()`: một bean có thể không được tạo do điều kiện khác, thiếu dependency hoặc component scan không tìm thấy cấu hình.

## 14. Testcontainers và dynamic property

### 14.1. Không đoán port của container

Testcontainers thường ánh xạ cổng container sang một cổng host ngẫu nhiên. Vì vậy, không viết cứng:

~~~properties
spring.datasource.url=jdbc:postgresql://localhost:5432/testdb
~~~

trừ khi test environment thực sự cố định port đó.

Dùng `@DynamicPropertySource` để đăng ký giá trị runtime:

~~~java
@DynamicPropertySource
static void postgresProperties(DynamicPropertyRegistry registry) {
    registry.add("spring.datasource.url", postgres::getJdbcUrl);
    registry.add("spring.datasource.username", postgres::getUsername);
    registry.add("spring.datasource.password", postgres::getPassword);
}
~~~

### 14.2. Supplier được gọi khi property được resolve

`registry.add("key", supplier)` không nhất thiết gọi supplier ngay lúc đăng ký. Giá trị được lấy khi resolver yêu cầu property. Điều này giúp sử dụng địa chỉ/port sau khi container được khởi tạo.

Supplier phải đọc trạng thái hiện tại của resource. Tránh tạo side effect hoặc trả một giá trị khác nhau tùy mỗi lần gọi nếu property cần ổn định trong suốt vòng đời context.

### 14.3. Dynamic properties thay đổi giữa test class

Nếu `@DynamicPropertySource` được đặt ở base class và các subclass dùng resource khác nhau, context cache có thể tái sử dụng context không còn phù hợp với supplier mới.

Nếu dynamic properties thay đổi giữa các subclass, cân nhắc `@DirtiesContext` để buộc tạo context mới hoặc thiết kế mỗi nhóm test có context key riêng. Không dùng một static mutable map để đổi endpoint giữa các test đang chia sẻ cùng ApplicationContext.

## 15. Context caching và tính cô lập của test

### 15.1. Vì sao test có thể dùng lại context?

Spring TestContext cache `ApplicationContext` khi cấu hình test tương ứng giống nhau. Việc tái sử dụng giúp suite chạy nhanh hơn, nhưng cũng có nghĩa trạng thái bean và Environment của context có thể tồn tại giữa nhiều phương thức test.

Các thành phần tham gia vào cấu hình context có thể bao gồm:

- Configuration classes.
- Context initializers.
- Active profiles.
- Test property source locations và inline properties.
- Context customizers.
- Dynamic property methods.
- Web environment và các thuộc tính test liên quan.

### 15.2. Không sửa system property trong một test rồi quên khôi phục

Ví dụ không tốt:

~~~java
System.setProperty("app.region", "temporary");
~~~

Nếu test khác chạy trong cùng JVM, system property có thể còn tồn tại và làm thay đổi kết quả. Nếu phải sửa system property, cần khôi phục trong `finally` hoặc dùng cơ chế test hỗ trợ quản lý property.

Không dùng thứ tự thực thi test để che giấu việc rò rỉ cấu hình.

### 15.3. Khi nào dùng `@DirtiesContext`?

`@DirtiesContext` đánh dấu context đã thay đổi và cần loại khỏi cache theo phạm vi được chỉ định. Có thể dùng khi test thực sự làm thay đổi state context không thể khôi phục an toàn hoặc dynamic configuration khác nhau giữa lớp test.

Không thêm `@DirtiesContext` vào mọi test. Nó làm tăng thời gian tạo context và có thể che giấu thiết kế test dùng chung state không tốt.

### 15.4. Tách test theo mục tiêu

Một cấu trúc dễ bảo trì:

| Loại test | Mục tiêu |
| --- | --- |
| Unit test | Kiểm tra logic dùng một property cụ thể |
| `ApplicationContextRunner` test | Kiểm tra binding/conditional configuration nhỏ |
| `@SpringBootTest` | Kiểm tra Config Data, profile và wiring đầy đủ |
| Integration test với Testcontainers | Kiểm tra dynamic property từ resource thật |
| Config Server integration test | Kiểm tra remote property source, label và profile |

Không cần khởi động toàn bộ ứng dụng cho một phép thử đơn giản về `MapPropertySource.addFirst()`.

## 16. Kiểm tra thứ tự property khi có Config Server

### 16.1. Xác định chế độ client

Trước khi viết test, xác định Config Client đang dùng:

- Config Data import: `spring.config.import=configserver:`.
- Bootstrap legacy: bootstrap context được bật bằng starter hoặc thuộc tính tương ứng.

Hai chế độ có lifecycle và override behavior khác nhau. Đừng trộn test của bootstrap legacy với test Config Data rồi mong kết quả giống nhau.

### 16.2. Kiểm tra application/profile/label

Một Config Client có thể yêu cầu cấu hình theo:

- `spring.application.name` hoặc `spring.cloud.config.name`.
- Active profiles.
- `spring.cloud.config.label`.

Nếu test đọc nhầm application name hoặc label, giá trị nhận được có thể hợp lệ nhưng không phải property source mong muốn.

### 16.3. Test remote source với revision cố định

Một integration test nên:

1. Khởi động Config Server test hoặc trỏ tới một server cô lập.
2. Chọn application name và profile rõ ràng.
3. Chọn label/commit ổn định.
4. Cung cấp một key có giá trị khác nhau giữa remote và local.
5. Khởi động Config Client.
6. Kiểm tra `Environment#getProperty`.
7. Kiểm tra tên property source thắng.
8. Xác nhận không có fallback ngoài ý muốn.

Không dùng Config Server production để test ghi đè hoặc thay đổi property. Dùng fixture/test repository riêng.

### 16.4. Kiểm tra `allowOverride` và bootstrap legacy

Với bootstrap legacy, các thuộc tính như `spring.cloud.config.allow-override`, `spring.cloud.config.override-none` và `spring.cloud.config.override-system-properties` ảnh hưởng cách remote property source được đặt trong Environment.

Theo tài liệu Spring Cloud, quyền cho phép override phải được cấp từ remote environment repository. Khi kiểm thử, hãy đặt fixture remote với giá trị rõ ràng và xác nhận local property có thắng hay không. Không giả định một biến local luôn có thể ghi đè remote Config Server trong mọi cấu hình.

## 17. Chẩn đoán bằng Actuator và Environment

### 17.1. `env` endpoint

Spring Boot Actuator có endpoint `env` giúp xem Environment và nguồn property. Nó hữu ích khi một property có giá trị khác dự kiến.

Nếu bật endpoint trong môi trường quản trị, cần giới hạn truy cập và che dữ liệu nhạy cảm. Không expose `env` công khai chỉ để debug.

### 17.2. `configprops` endpoint

`configprops` giúp quan sát các bean `@ConfigurationProperties` và giá trị đã bind. Nó hữu ích khi:

- `Environment#getProperty` đúng nhưng bean có giá trị khác.
- Conversion hoặc validation không như mong đợi.
- Prefix hoặc field name không khớp.
- Bean chưa được đăng ký hoặc không được bind.

### 17.3. Kiểm tra ở hai tầng

Khi một test thất bại, kiểm tra lần lượt:

1. `Environment#getProperty("app.region")`: giá trị resolve cuối cùng là gì?
2. Nguồn nào cung cấp giá trị?
3. `Environment#getActiveProfiles()`: profile nào đang active?
4. Bean `@ConfigurationProperties`: giá trị sau binding là gì?
5. Bean/client đã được tạo trước khi một property source được thêm hay chưa?
6. Test có đang dùng lại ApplicationContext cache không?

Cách này phân biệt lỗi ưu tiên nguồn với lỗi binding và lỗi lifecycle.

## 18. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `application-test.yml` không được nạp | Profile test chưa active hoặc sai vị trí file | Kiểm tra `@ActiveProfiles`, tên file và Config Data locations |
| Giá trị trong profile không thắng | Có nguồn ưu tiên cao hơn ghi đè | Duyệt property source và kiểm tra env/system/CLI/test overrides |
| Test dùng profile production ngoài ý muốn | `@ActiveProfiles` thiếu hoặc resolver tùy chỉnh chọn sai | Kiểm tra active profiles và CI environment |
| `@ActiveProfiles` không theo `SPRING_PROFILES_ACTIVE` | Annotation điều khiển profile của TestContext | Dùng `ActiveProfilesResolver` nếu muốn external override |
| `@TestPropertySource` không đọc YAML | Loader mặc định không xử lý YAML | Dùng properties hoặc custom `PropertySourceFactory` |
| Giá trị Testcontainers vẫn là localhost cũ | Property được hard-code hoặc dynamic property chưa đăng ký | Dùng `@DynamicPropertySource` và supplier từ container |
| Test A làm test B nhận property lạ | System property/static state hoặc context cache dùng chung | Khôi phục state, tách context hoặc dùng `@DirtiesContext` khi cần |
| Nguồn remote Config Server thắng local | Remote source có precedence cao hoặc bootstrap override policy | Xác định mode Config Data/legacy bootstrap và override flags |
| Bean `@ConfigurationProperties` không khớp Environment | Binding/conversion/registration issue | Kiểm tra prefix, type, binder và bean registration |
| `@PropertySource` không điều khiển được `spring.main.*` | Nguồn được thêm quá muộn trong lifecycle | Dùng Config Data hoặc nguồn được đọc sớm |
| `MapPropertySource` test không thắng | Dùng `addLast` hoặc thêm sau một nguồn ưu tiên cao | Dùng `addFirst` hoặc đặt đúng vị trí |
| Test chạy riêng pass nhưng suite fail | Context cache, global state hoặc test order dependency | Loại bỏ state dùng chung và kiểm tra isolation |
| Property `null` không ghi đè nguồn khác | Resolver xem null như property không tồn tại | Dùng giá trị sentinel hoặc cơ chế remove/override phù hợp |

## 19. Checklist thiết kế test property source

Trước khi kết luận thứ tự cấu hình đúng, xác nhận:

- [ ] Test đang dùng đúng Spring Boot/Spring Cloud version.
- [ ] Active profiles đúng và theo đúng thứ tự.
- [ ] File `application-{profile}.yml` nằm ở location được Config Data tìm thấy.
- [ ] Các location/import được xử lý theo thứ tự dự kiến.
- [ ] Không có biến môi trường hoặc system property vô tình ghi đè.
- [ ] Không có tham số command line từ build/test runner.
- [ ] `@SpringBootTest(properties)` chỉ chứa các override cần thiết.
- [ ] `@TestPropertySource` dùng định dạng được hỗ trợ.
- [ ] `@DynamicPropertySource` cung cấp giá trị từ resource đang chạy.
- [ ] Test không dùng chung context với dynamic property đã thay đổi.
- [ ] Config Server test dùng application/profile/label cố định.
- [ ] Assertion kiểm tra cả Environment và bean đã bind khi cần.
- [ ] Không log plaintext secret hoặc dump toàn bộ property source.
- [ ] Không phụ thuộc thứ tự chạy test để tạo kết quả đúng.

## 20. Bài tập vận dụng

**Bài tập 1 — PropertySource cơ bản.** Tạo hai `MapPropertySource` cùng khai báo `app.region`. Dùng `addFirst` và `addLast`, sau đó xác nhận giá trị thắng bằng `Environment#getProperty`.

**Bài tập 2 — File và profile.** Tạo `application.yml`, `application-test.yml` và `application-cloud.yml`. Kích hoạt hai profile theo hai thứ tự khác nhau và kiểm tra giá trị của key trùng.

**Bài tập 3 — Nguồn ngoài.** Chạy ứng dụng với `APP_REGION`, `-Dapp.region` và `--app.region`. Xác nhận nguồn nào thắng trong phiên bản Spring Boot đang dùng.

**Bài tập 4 — `@SpringBootTest(properties)`.** Đặt một giá trị trong `application-test.yml`, một giá trị khác trong `@SpringBootTest(properties)`. Kiểm tra giá trị cuối cùng và profile active.

**Bài tập 5 — `@TestPropertySource`.** Khai báo một file `test-defaults.properties` và một inline property trùng key. Chứng minh inline value ghi đè resource location.

**Bài tập 6 — Dynamic property.** Dùng Testcontainers khởi động PostgreSQL và đăng ký URL/username/password bằng `@DynamicPropertySource`. Kiểm tra bean DataSource kết nối đúng container.

**Bài tập 7 — Context cache.** Tạo base test class dùng dynamic property, sau đó hai subclass dùng resource khác nhau. Quan sát context reuse và thử `@DirtiesContext` nếu cần.

**Bài tập 8 — Config Server.** Tạo fixture remote có cùng key với local config. Chọn profile và label cố định, kiểm tra property source thắng trong Config Data mode.

**Bài tập 9 — Bootstrap legacy.** Với dự án hỗ trợ bootstrap legacy, kiểm tra tác động của `allow-override`, `override-none` và `override-system-properties`. Ghi rõ remote repository phải cấp quyền override ở đâu.

**Bài tập 10 — Chẩn đoán binding.** Tạo một `@ConfigurationProperties` bean có `Duration` và `DataSize`. Kiểm tra giá trị Environment, giá trị đã bind và lỗi khi property source có format không hợp lệ.

## 21. Ghi nhớ và nguồn tra cứu

- `Environment` tổng hợp nhiều `PropertySource`; giá trị được resolve theo thứ tự duyệt của các nguồn trong Environment.
- `MutablePropertySources.addFirst()` thêm nguồn ưu tiên cao; `addLast()` thêm nguồn ưu tiên thấp.
- Tài liệu Spring Boot trình bày danh sách nguồn từ ưu tiên thấp lên cao; nguồn xuất hiện sau có thể ghi đè nguồn trước.
- File profile-specific ghi đè file không profile-specific; nếu nhiều profile cùng khai báo một key, profile được xử lý sau có thể thắng.
- `@ActiveProfiles` xác định active profiles của Spring TestContext; khi annotation hiện diện, system/environment `spring.profiles.active` không tự quyết định profile cho test.
- `@SpringBootTest(properties)` và `@TestPropertySource` hữu ích cho giá trị test tĩnh; `@DynamicPropertySource` dành cho giá trị động từ resource runtime.
- Tài liệu Spring Framework nói `@DynamicPropertySource` có ưu tiên cao hơn `@TestPropertySource`; danh sách tổng quát trong tài liệu Spring Boot hiện hành trình bày thứ tự khác. Hãy kiểm tra Environment thực tế theo đúng version.
- Config Server có thể thêm remote property sources; phân biệt Config Data import với bootstrap legacy trước khi kết luận thứ tự override.
- Testcontainers thường cần `@DynamicPropertySource` để đưa host/port runtime vào Environment.
- Context caching giúp test nhanh nhưng cần xử lý cẩn thận khi dynamic properties thay đổi giữa các lớp test.
- Kiểm tra cả `Environment` và bean `@ConfigurationProperties` để phân biệt lỗi resolve với lỗi binding.

Nguồn chính thức để đối chiếu theo phiên bản Spring Boot/Spring Cloud của dự án:

1. [Spring Boot Reference – Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
2. [Spring Boot Reference – Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html)
3. [Spring Framework Reference – Context Configuration with Test Property Sources](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/property-sources.html)
4. [Spring Framework Reference – Context Configuration with Dynamic Property Sources](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/dynamic-property-sources.html)
5. [Spring Framework Reference – Context Configuration with Environment Profiles](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/env-profiles.html)
6. [Spring Framework Reference – Environment Abstraction](https://docs.spring.io/spring-framework/reference/core/beans/environment.html)
7. [Spring Cloud Config – Config Client](https://docs.spring.io/spring-cloud-config/reference/client.html)
8. [Spring Cloud Config – Property Overrides](https://docs.spring.io/spring-cloud-config/reference/server/environment-repository/property-overrides.html)
9. [Spring Cloud Commons – Configuration Properties](https://docs.spring.io/spring-cloud-commons/reference/configprops.html)
10. [Spring Cloud – Release train và tương thích Spring Boot](https://spring.io/projects/spring-cloud/)
