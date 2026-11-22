# Vai trò của Spring Framework và phần mở rộng của Spring Boot trong Externalized Configuration

## 1. Bối cảnh và mục tiêu

**Externalized Configuration** là cách đưa các giá trị thay đổi theo môi trường chạy ra khỏi mã nguồn và gói ứng dụng. Cùng một bản build có thể chạy ở máy phát triển, môi trường kiểm thử hoặc production với địa chỉ dịch vụ, thời gian chờ, cổng HTTP và thông tin kết nối khác nhau. Ví dụ, ứng dụng không cần sửa Java để thay `app.client.timeout` từ `3s` thành `5s`.

Trong hệ sinh thái Spring, cần tách hai lớp trách nhiệm:

- **Spring Framework** cung cấp mô hình `Environment`, các nguồn thuộc tính (`PropertySource`), cơ chế tra cứu giá trị và profile. Đây là nền tảng để mã ứng dụng đọc cấu hình mà không phụ thuộc trực tiếp vào nơi lưu.
- **Spring Boot** xây trên nền tảng đó, tự tìm và nạp các tệp cấu hình theo quy ước, tích hợp biến môi trường/tham số chạy, xử lý profile, liên kết cấu hình thành đối tượng có kiểu, và dùng cấu hình để điều khiển auto-configuration.

Spring Boot **không thay thế** `Environment` của Spring Framework. Nó chuẩn bị thêm dữ liệu và quy ước cho `Environment`, sau đó các bean của Spring và các thành phần Boot cùng sử dụng kết quả.

## 2. Phần nền tảng do Spring Framework cung cấp

### 2.1. `Environment` và `PropertySource`

`org.springframework.core.env.Environment` đại diện cho môi trường cấu hình của ứng dụng. Các thao tác thường gặp gồm:

- `getProperty("app.name")`: đọc một thuộc tính, có thể nhận `null` khi không tồn tại.
- `getProperty("app.timeout", Integer.class)`: yêu cầu chuyển đổi giá trị sang kiểu cụ thể.
- `getProperty("app.retries", "3")`: cung cấp giá trị mặc định.
- `getRequiredProperty("app.name")`: báo lỗi khi thiếu cấu hình bắt buộc.
- `getActiveProfiles()` và `acceptsProfiles(...)`: kiểm tra các profile đang hoạt động.

Một `PropertySource` là nguồn chứa các cặp tên–giá trị, chẳng hạn Java system properties, biến môi trường hệ điều hành, bản đồ cấu hình tự tạo hoặc nội dung tệp được thêm vào. `ConfigurableEnvironment` cho phép truy cập chuỗi `MutablePropertySources` để bổ sung hoặc sắp xếp nguồn. Khi nhiều nguồn cùng khai báo một khóa, nguồn có **độ ưu tiên cao hơn trong chuỗi tra cứu** quyết định giá trị hiệu lực.

Nhờ lớp trừu tượng này, mã gọi `environment.getRequiredProperty("catalog.api.url")` không cần biết giá trị đến từ biến môi trường, JVM property hay tệp cấu hình. Việc nạp nguồn và xác định thứ tự ưu tiên là một trách nhiệm riêng.

### 2.2. Placeholder, `@Value` và `@PropertySource`

Spring Framework có thể chèn thuộc tính vào bean bằng placeholder:

~~~java
@Component
public class CatalogClient {
    private final String baseUrl;

    public CatalogClient(@Value("${catalog.api.url}") String baseUrl) {
        this.baseUrl = baseUrl;
    }
}
~~~

Cú pháp `${catalog.api.url:...}` có thể cung cấp giá trị mặc định sau dấu hai chấm. Khi sử dụng Spring Framework thuần và khai báo cấu hình thủ công, cần bảo đảm có cơ chế xử lý placeholder thích hợp, ví dụ `PropertySourcesPlaceholderConfigurer` trong một số kiểu cấu hình.

`@PropertySource` giúp đăng ký một tệp `.properties` vào môi trường:

~~~java
@Configuration
@PropertySource("classpath:catalog.properties")
public class CatalogConfiguration {
}
~~~

Ví dụ `catalog.properties`:

~~~properties
catalog.api.url=https://catalog.example.test
~~~

Cơ chế này hữu ích khi tự cấu hình một ứng dụng Spring Framework. Tuy nhiên, bản thân `@PropertySource` không mang theo toàn bộ quy ước `application.yml`, profile-specific config hay config import của Spring Boot; định dạng YAML cũng không được hỗ trợ trực tiếp bởi cách dùng `@PropertySource` mặc định.

### 2.3. Profile của Spring Framework

Profile là khái niệm nền tảng để kích hoạt bean theo điều kiện môi trường. Chẳng hạn:

~~~java
@Configuration
@Profile("dev")
public class DevelopmentCatalogConfiguration {
    // Các bean chỉ được tạo khi profile dev đang hoạt động.
}
~~~

`@Profile` điều khiển việc đăng ký bean; nó **không tự định nghĩa** cách tìm `application-dev.yml`. Quy ước tự nạp tệp theo profile là phần mà Spring Boot bổ sung.

## 3. Spring Boot mở rộng nền tảng đó như thế nào?

### 3.1. Tự nạp cấu hình theo quy ước

Khi khởi động một ứng dụng Spring Boot, Boot chuẩn bị `Environment` và xử lý **Config Data** từ các vị trí cấu hình được hỗ trợ. Với các phiên bản Spring Boot hiện đại, các tệp thường gặp là:

- `application.properties` hoặc `application.yml` / `application.yaml`;
- `application-{profile}.properties` hoặc `application-{profile}.yml`;
- các vị trí được chỉ định qua `spring.config.location` hoặc bổ sung bằng `spring.config.additional-location`;
- các nguồn được tham chiếu bởi `spring.config.import`, bao gồm tệp ngoài ứng dụng hay nguồn bổ sung được tích hợp phù hợp.

Boot cũng xem xét biến môi trường hệ điều hành, Java system properties, đối số dòng lệnh và một số nguồn khác. Những khóa như `server.port`, `logging.level.*` và `spring.datasource.*` có thể được dùng trực tiếp bởi các thành phần được Boot tự cấu hình.

Ví dụ, khai báo sau là đủ để Boot nhận một cổng HTTP khác khi ứng dụng có web server tương ứng:

~~~yaml
# application.yml
server:
  port: 8085
~~~

Mã ứng dụng không phải tự mở tệp YAML và gán giá trị cho web server.

### 3.2. Quy tắc ghi đè và thứ tự ưu tiên

Externalized Configuration hữu ích vì **cùng một khóa có thể được khai báo ở nhiều nơi**. Với thiết lập Spring Boot thông dụng, biến môi trường hoặc đối số dòng lệnh có thể ghi đè cấu hình trong `application.yml`; đối số `--server.port=9090` thường có ưu tiên cao hơn giá trị `server.port=8085` trong tệp. Java system properties và các nguồn khác cũng tham gia vào thứ tự ưu tiên của Boot.

Không nên tự suy ra một bảng thứ tự ưu tiên duy nhất cho mọi ứng dụng: thứ tự còn chịu ảnh hưởng của nguồn tùy chỉnh, cách khởi tạo `SpringApplication`, vị trí Config Data, profile đang bật và phiên bản Boot. Khi có xung đột, cần xác định **giá trị hiệu lực và nguồn đã cung cấp giá trị đó**.

Lưu ý: `spring.config.location` thay đổi các vị trí tìm kiếm mặc định, còn `spring.config.additional-location` thêm vị trí tìm kiếm. Các thuộc tính chọn vị trí cấu hình cần có sẵn đủ sớm khi Boot khởi động, ví dụ qua biến môi trường, JVM system property hoặc đối số chạy.

### 3.3. Liên kết cấu hình có kiểu với `@ConfigurationProperties`

Spring Framework cung cấp các giá trị ở dạng property; Spring Boot cung cấp cơ chế **binding** một nhóm property thành đối tượng Java. Đây là điểm khác biệt quan trọng khi hệ thống có nhiều khóa liên quan.

Ví dụ trong Spring Boot 3.x, với Java 17 trở lên:

~~~yaml
# application.yml
app:
  client:
    base-url: https://catalog.example.test
    timeout: 3s
    max-retries: 2
~~~

~~~java
import java.net.URI;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
        URI baseUrl,
        Duration timeout,
        int maxRetries
) {}
~~~

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

~~~java
import org.springframework.stereotype.Service;

@Service
public class CatalogService {
    private final ClientProperties properties;

    public CatalogService(ClientProperties properties) {
        this.properties = properties;
    }

    public Duration timeout() {
        return properties.timeout();
    }
}
~~~

Boot nhận `app.client.base-url` và ánh xạ vào `baseUrl`, chuyển `3s` thành `Duration`, và chuyển `2` thành `int`. Cách khớp tên này gọi là **relaxed binding**: các biến thể tên như kebab-case, camelCase hoặc dạng biến môi trường có thể được liên kết theo quy tắc của Boot.

`@ConfigurationPropertiesScan` là một cách đăng ký các lớp thuộc tính; cũng có thể dùng `@EnableConfigurationProperties(ClientProperties.class)`. Nếu lớp chưa được đăng ký, Boot sẽ không tự tạo bean `ClientProperties` chỉ vì có annotation trên record. Cơ chế constructor binding của record trong ví dụ phù hợp với Spring Boot 3.x; ứng dụng dùng các phiên bản cũ có thể cần cú pháp khác.

Có thể dùng Bean Validation, chẳng hạn `@Validated` và các ràng buộc `jakarta.validation`, để phát hiện cấu hình sai trong giai đoạn khởi động khi dependency và cơ chế validation tương ứng đã được thiết lập.

### 3.4. Profile-specific Config Data và config import

Spring Boot kết hợp profile của Spring Framework với quy ước tệp theo môi trường. Ví dụ:

~~~yaml
# application.yml
app:
  client:
    timeout: 3s
~~~

~~~yaml
# application-prod.yml
app:
  client:
    timeout: 10s
~~~

Khi chạy với `SPRING_PROFILES_ACTIVE=prod`, cấu hình dành cho profile `prod` được cân nhắc để ghi đè giá trị cơ sở. Một tệp YAML cũng có thể chứa nhiều document và dùng `spring.config.activate.on-profile` để kích hoạt document theo profile.

Boot cho phép nhập cấu hình ngoài thông qua `spring.config.import`, ví dụ:

~~~properties
spring.config.import=optional:file:./config/catalog-extra.properties
~~~

Tiền tố `optional:` cho phép khởi động khi vị trí không tồn tại; bỏ tiền tố này khi muốn thiếu cấu hình phải gây lỗi. Việc có thể nhập một tệp không đồng nghĩa với việc ứng dụng tự động được phép truy cập mọi secret store; tích hợp với nguồn từ xa thường cần cơ chế hoặc thư viện hỗ trợ tương ứng.

### 3.5. Liên hệ với auto-configuration

Auto-configuration của Spring Boot thường sử dụng thuộc tính trong `Environment` để quyết định có tạo bean hay không và cách cấu hình chúng. Ví dụ, `spring.datasource.url` có thể được dùng trong cấu hình `DataSource` nếu các điều kiện auto-configuration thích hợp được đáp ứng; `management.endpoints.web.exposure.include` có thể ảnh hưởng đến Actuator khi dependency liên quan có mặt.

Điểm cốt lõi: **Spring Framework cung cấp nền tảng đọc/tra cứu cấu hình; Spring Boot thêm cơ chế nạp, binding và sử dụng cấu hình theo quy ước để thiết lập ứng dụng.** Một property chỉ có hiệu lực chức năng nếu có bean hoặc thành phần thực sự đọc nó.

## 4. Luồng xử lý từ cấu hình ngoài đến bean

Có thể hình dung tiến trình như sau:

1. Người vận hành cung cấp cấu hình từ tệp, biến môi trường, JVM properties hoặc đối số chạy.
2. Spring Boot khởi tạo và bổ sung các nguồn Config Data vào `Environment` theo quy tắc khởi động.
3. Spring Framework dùng `Environment` để phân giải placeholder, kiểm tra profile và cung cấp property cho các bean.
4. Spring Boot Binder liên kết các nhóm property với `@ConfigurationProperties`, chuyển đổi kiểu và thực hiện validation nếu được thiết lập.
5. Auto-configuration và bean ứng dụng sử dụng những giá trị hiệu lực này để khởi tạo thành phần.

Vì vậy, cùng một giá trị có thể được đọc bằng API Spring Framework:

~~~java
String timeoutText = environment.getRequiredProperty("app.client.timeout");
~~~

hoặc được nhận dưới dạng `Duration` qua `ClientProperties.timeout()` của Spring Boot. Cách thứ hai thường phù hợp hơn với cấu hình có cấu trúc và nhiều trường liên quan.

## 5. So sánh nhanh phạm vi trách nhiệm

| Nhu cầu | Spring Framework | Phần Spring Boot bổ sung |
| --- | --- | --- |
| Truy cập một thuộc tính | `Environment`, `PropertyResolver`, `@Value` | Chuẩn bị thêm nguồn cấu hình để các API trên đọc được |
| Quản lý nhiều nguồn | `PropertySource`, `MutablePropertySources` | Thứ tự ưu tiên và các loại nguồn quen thuộc của ứng dụng Boot |
| Kích hoạt bean theo môi trường | `@Profile` và active profiles | Tự tìm và nạp các tệp/profile document tương ứng |
| Nạp tệp cấu hình | Có thể đăng ký nguồn tường minh, ví dụ `@PropertySource` | Quy ước `application.*`, Config Data, import và external locations |
| Nhóm cấu hình có kiểu | Có API chuyển đổi giá trị và cơ chế bean của Framework | `@ConfigurationProperties`, relaxed binding, chuyển đổi và validation tích hợp |
| Tự cấu hình thành phần | Có cơ sở DI, container và các extension point | Auto-configuration đọc property để quyết định cấu hình ứng dụng |

Ranh giới này giúp thiết kế đúng: dùng abstraction của Framework khi viết thư viện tái sử dụng không phụ thuộc Boot; dùng tiện ích Boot khi xây ứng dụng Boot cần cấu hình theo môi trường và binding có kiểu.

## 6. Thực hành chọn công cụ đúng

**Dùng `Environment` hoặc `@Value` khi:**

- Chỉ cần một vài khóa riêng lẻ, không tạo thành nhóm cấu hình ổn định.
- Đang viết thành phần Spring Framework chung hoặc cần truy cập property tại thời điểm chạy.
- Cần đọc trực tiếp giá trị đã được phân giải trong một tình huống cụ thể.

**Ưu tiên `@ConfigurationProperties` khi:**

- Có một nhóm cấu hình liên quan như `app.client.*`, `app.security.*` hay `app.storage.*`.
- Muốn chuyển đổi dữ liệu sang `Duration`, `URI`, danh sách hoặc các kiểu đối tượng cụ thể.
- Muốn áp dụng validation, dễ kiểm thử và tránh lặp các chuỗi khóa ở nhiều lớp.

**Dùng profile và Config Data khi:** cần thay đổi giá trị giữa các môi trường nhưng vẫn dùng cùng một gói ứng dụng. Không đặt toàn bộ logic nghiệp vụ vào những nhánh `if (prod)`; để profile quyết định phần cấu hình môi trường, còn hành vi nghiệp vụ nên có mô hình rõ ràng.

Ví dụ, có thể giữ `app.client.timeout=3s` trong `application.yml`, đặt `APP_CLIENT_TIMEOUT=5s` trên môi trường production, và tạm ghi đè bằng `--app.client.timeout=1s` trong một lần chạy thử. Trong cấu hình Boot thông thường, giá trị dòng lệnh sẽ thắng ở lần chạy đó.

## 7. Những nhầm lẫn thường gặp

### “Spring Framework tự tìm `application.yml`”

Không. Spring Framework có `Environment` và cơ chế nạp nguồn được cấu hình, còn việc tự tìm `application.*` theo quy ước là hành vi của Spring Boot. Một ứng dụng Spring Framework thuần không đột nhiên nhận đầy đủ Config Data chỉ vì dùng `@Value`.

### “`@PropertySource` tương đương với Config Data của Boot”

Không. `@PropertySource` là một cách đăng ký property source, chủ yếu dùng trực tiếp với định dạng `.properties` theo cấu hình mặc định. Cơ chế Config Data của Boot có quy tắc riêng cho profile, vị trí, import và thời điểm nạp. `@PropertySource` cũng được xử lý khi context đang được dựng nên có thể đến quá muộn đối với một số thuộc tính khởi động sớm, chẳng hạn nhóm `logging.*` hoặc `spring.main.*`.

### “Có annotation `@ConfigurationProperties` là tự được inject”

Không nhất thiết. Lớp cấu hình phải được đăng ký bằng cơ chế phù hợp như `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties`. Nếu muốn phát hiện thiếu/sai giá trị ngay khi khởi động, cần khai báo các ràng buộc validation thích hợp.

### “Mọi biến môi trường đều ánh xạ nguyên văn sang tên trong YAML”

Boot có quy tắc relaxed binding, nhưng cú pháp tên biến và cấu trúc danh sách/bản đồ cần tuân theo quy tắc của Binder. Với `app.client.timeout`, ví dụ môi trường thông thường là `APP_CLIENT_TIMEOUT`. Khi binding không như dự kiến, hãy kiểm tra tên property chuẩn và nguồn đang thắng trước khi sửa mã.

### “Profile thay thế được quản lý secret”

Profile chỉ chọn cấu hình/bean theo môi trường. Mật khẩu, token và khóa riêng cần cơ chế phân phối bí mật an toàn theo môi trường triển khai; không đưa secret thật vào README, Git hoặc log. Các endpoint chẩn đoán cấu hình của Actuator phải được kiểm soát quyền truy cập và tránh làm lộ dữ liệu nhạy cảm.

## 8. Cách kiểm tra khi ứng dụng nhận sai giá trị

Khi một thuộc tính không đúng như kỳ vọng, hãy bắt đầu từ các câu hỏi có thể kiểm chứng:

1. **Tên khóa có đúng không?** Đối chiếu `app.client.timeout` với cấu trúc YAML, tên trường của `@ConfigurationProperties` và cách đặt biến môi trường.
2. **Profile nào đang hoạt động?** Kiểm tra `Environment.getActiveProfiles()`, `spring.profiles.active` và tài liệu cấu hình có điều kiện profile.
3. **Nguồn nào đang thắng?** Đối chiếu đối số chạy, biến môi trường, Java system properties, Config Data và các `PropertySource` tùy chỉnh.
4. **Tệp ngoài có thực sự được nạp không?** Kiểm tra đường dẫn, vị trí khởi động, `spring.config.import` và việc sử dụng `optional:`.
5. **Binding có lỗi chuyển kiểu hoặc validation không?** Đọc thông báo lỗi lúc khởi động để tìm property và kiểu đích; tránh che lỗi bằng mặc định không hợp lý.
6. **Có thành phần nào thực sự dùng khóa đó không?** Việc thêm `custom.feature.enabled=true` không tự tạo chức năng mới nếu chưa có mã hoặc auto-configuration xử lý khóa này.

Nếu Actuator được bật và bảo vệ phù hợp, `/actuator/env` hoặc `/actuator/configprops` có thể hỗ trợ điều tra cấu hình đã nạp, nguồn gốc và binding; mức chi tiết hiển thị phụ thuộc cấu hình bảo mật và chính sách che thông tin nhạy cảm. Với trường hợp đơn giản, có thể dùng `Environment.getProperty(...)` tại điểm khởi tạo thích hợp và chỉ log những giá trị không nhạy cảm.

## 9. Kết luận về kiến trúc

Spring Framework giải quyết câu hỏi **“Ứng dụng truy cập cấu hình từ những nguồn thuộc tính như thế nào?”** bằng `Environment`, `PropertySource`, placeholder và profile. Spring Boot mở rộng thành **“Một ứng dụng thực tế tự tìm, ghi đè, liên kết và sử dụng cấu hình theo môi trường như thế nào?”** bằng Config Data, quy ước `application.*`, `@ConfigurationProperties` và auto-configuration.

Khi hiểu rõ ranh giới này, có thể đặt cấu hình ở đúng chỗ, giảm mã tự đọc file, tránh hardcode giá trị môi trường và giải thích được vì sao một property cụ thể có hiệu lực trong mỗi lần triển khai.
