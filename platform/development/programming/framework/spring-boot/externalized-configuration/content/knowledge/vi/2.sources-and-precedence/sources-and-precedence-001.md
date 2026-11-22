# Các nhóm nguồn cấu hình và cách chúng cùng tham gia Environment

## Mục tiêu học tập

Sau bài này, bạn có thể nhận diện các nhóm nguồn cấu hình mà Spring Boot sử dụng, giải thích vì sao cùng một khóa có thể có nhiều giá trị nhưng ứng dụng chỉ đọc ra một giá trị có hiệu lực, và lần theo đường đi của một thuộc tính từ tệp cấu hình đến `Environment`, `@Value` hoặc `@ConfigurationProperties`.

## 1. Bài toán: một ứng dụng, nhiều môi trường chạy

Giả sử một ứng dụng chạy trên máy lập trình viên, môi trường kiểm thử và production. Mã Java vẫn giống nhau, nhưng cổng HTTP, địa chỉ dịch vụ bên ngoài, thời gian chờ và thông tin kết nối có thể khác. Nếu ghi trực tiếp những giá trị đó trong mã nguồn, mỗi lần triển khai sẽ phải sửa hoặc biên dịch lại ứng dụng.

Spring Boot cho phép đưa các giá trị này ra ngoài mã nguồn (externalized configuration). Một giá trị như `app.timeout` có thể xuất hiện trong `application.yaml`, tệp đặt cạnh ứng dụng, biến môi trường của hệ điều hành hoặc tham số khởi chạy. Spring Boot tổ chức chúng thành các nguồn cấu hình có thứ tự để ứng dụng dùng chung một cách đọc.

**Điểm cốt lõi:** `Environment` không phải bản sao của một tệp `application.yaml`. Nó là giao diện thống nhất để tra cứu thuộc tính từ **nhiều `PropertySource` có thứ tự ưu tiên**. Nguồn đứng trước trong thứ tự tra cứu có thể cung cấp giá trị trước những nguồn đứng sau.

## 2. Từ nguồn cấu hình đến Environment

Một `PropertySource` biểu diễn tập hợp các cặp khóa–giá trị đến từ một nguồn: tệp cấu hình, biến môi trường, Java System properties, tham số dòng lệnh, v.v. `ConfigurableEnvironment` quản lý tập hợp có thứ tự mang tên `PropertySources`; mã ứng dụng thường chỉ cần phụ thuộc vào giao diện `Environment`.

Có thể hình dung:

~~~text
application.yaml trong JAR -----┐
application-prod.yaml bên ngoài -┤
biến môi trường của hệ điều hành -┤
Java System properties ---------┼--> PropertySources có thứ tự --> Environment
tham số dòng lệnh ---------------┤                                 |
các nguồn khác ------------------┘                                 +--> getProperty(...)
                                                                  +--> @Value(...)
                                                                  +--> @ConfigurationProperties
~~~

Khi cần `app.timeout`, cơ chế tra cứu xét các nguồn theo thứ tự ưu tiên. Nếu nguồn ưu tiên cao có khóa phù hợp, giá trị đó có hiệu lực. Nếu không, nó tiếp tục tìm ở các nguồn tiếp theo. Một khóa chỉ có trong tệp mặc định vẫn dùng được ngay cả khi nhiều khóa khác đã bị biến môi trường ghi đè.

Do đó cần phân biệt hai hiện tượng:

- **Ghi đè theo khóa:** hai nguồn cùng định nghĩa `app.timeout`; giá trị ở nguồn ưu tiên cao thắng.
- **Bổ sung thuộc tính:** nguồn A định nghĩa `app.timeout` và nguồn B định nghĩa `app.endpoint`; ứng dụng đọc được cả hai qua cùng một `Environment`.

Quy tắc tra cứu thuộc tính đơn lẻ này không đồng nghĩa với việc mọi đối tượng phức tạp hoặc danh sách đều được nối phần tử với nhau. Việc gắn cấu hình vào `List`, `Map` và đối tượng Java còn tuân theo quy tắc của bộ gắn kết (`Binder`).

## 3. Những nhóm nguồn cấu hình thường gặp

| Nhóm | Ví dụ | Vai trò |
| --- | --- | --- |
| Giá trị mặc định của ứng dụng | `SpringApplication.setDefaultProperties(...)` | Cung cấp giá trị dự phòng, ưu tiên thấp. |
| Khai báo bổ sung từ mã cấu hình | `@PropertySource("classpath:extra.properties")` | Nạp một tệp properties vào `Environment` khi ngữ cảnh Spring được khởi tạo. |
| Config Data | `application.properties`, `application.yaml`, `application-prod.yaml`, tệp import, configuration tree | Nguồn cấu hình chính của Spring Boot; hỗ trợ vị trí tệp, profile và import. |
| Giá trị đặc biệt do Spring tạo | `random.*` | Sinh các giá trị ngẫu nhiên cho những khóa thuộc không gian `random`. |
| Môi trường của tiến trình | `APP_TIMEOUT`, `SERVER_PORT` | Truyền cấu hình từ hệ điều hành, container hoặc nền tảng triển khai. |
| Java System properties | `-Dapp.timeout=10s` | Cấu hình ở mức JVM khi khởi chạy. |
| Nguồn từ môi trường web truyền thống | JNDI, tham số khởi tạo Servlet | Có ý nghĩa khi chạy trong môi trường Servlet hoặc application server hỗ trợ. |
| JSON cấu hình nhúng | `SPRING_APPLICATION_JSON` hoặc `spring.application.json` | Cung cấp nhiều thuộc tính qua một giá trị JSON. |
| Tham số dòng lệnh | `--app.timeout=5s` | Ghi đè thuận tiện khi chạy một phiên bản ứng dụng cụ thể. |
| Nguồn dành cho kiểm thử và phát triển | `@SpringBootTest(properties=...)`, `@DynamicPropertySource`, `@TestPropertySource`, Devtools | Phục vụ tình huống kiểm thử hoặc phát triển; có thể thay đổi giá trị hiệu lực so với lần chạy thông thường. |

Đây là **các nhóm theo công dụng**, không phải những tệp được gộp thành một tệp duy nhất. Trong thực tế, một nhóm có thể tạo nhiều `PropertySource`. Chẳng hạn, từng tài liệu cấu hình được nạp từ các vị trí và profile khác nhau có thể trở thành các nguồn riêng trong `Environment`.

### 3.1. Giá trị mặc định và @PropertySource

`SpringApplication.setDefaultProperties(...)` thích hợp để đặt các giá trị dự phòng mà những nguồn cấu hình khác có thể thay thế.

`@PropertySource` cho phép bổ sung tệp properties trong lớp `@Configuration`:

~~~java
@Configuration
@PropertySource("classpath:extra.properties")
class ExtraConfiguration {
}
~~~

Tuy nhiên `@PropertySource` được thêm khi ApplicationContext đang làm mới (`refresh`). Nó có thể đến **quá muộn** đối với những thuộc tính được Spring Boot đọc rất sớm, như một số thiết lập `logging.*` và `spring.main.*`. Với cấu hình khởi động ứng dụng, hãy ưu tiên cơ chế Config Data chuẩn.

### 3.2. Config Data: tệp, profile và nguồn nhập thêm

Các tệp `application.properties` hoặc `application.yaml` là điểm bắt đầu quen thuộc. Spring Boot tự tìm các tệp này ở classpath và ở một số vị trí bên ngoài ứng dụng, bao gồm thư mục làm việc, `./config/` và các thư mục con trực tiếp của `./config/`. Cấu hình được đóng gói trong JAR thuận tiện cho mặc định; cấu hình bên ngoài thuận tiện cho triển khai mà không sửa JAR.

Profile bổ sung lớp cấu hình chỉ có hiệu lực trong hoàn cảnh phù hợp. Khi profile `prod` được kích hoạt, `application-prod.yaml` có thể ghi đè thuộc tính từ `application.yaml`. Một profile chưa được kích hoạt thì tệp dành riêng cho profile đó không tham gia như một nguồn cấu hình đang hoạt động.

Ngoài các tệp tự động phát hiện, `spring.config.import` cho phép một tài liệu cấu hình nhập nguồn khác:

~~~properties
spring.config.import=optional:file:./local-overrides.properties
~~~

`optional:` cho phép tệp không tồn tại mà không khiến quá trình khởi động thất bại vì thiếu vị trí đó. Theo cơ chế Config Data, nội dung được import có thể ghi đè những khóa trùng với tài liệu khai báo lệnh import.

Khi nền tảng triển khai gắn mỗi bí mật thành một tệp, có thể import cấu hình dạng cây:

~~~properties
spring.config.import=optional:configtree:/run/secrets/
~~~

Ví dụ tệp `/run/secrets/db.password` sẽ tạo thuộc tính `db.password`. Cần bảo vệ quyền truy cập các tệp này; việc đưa giá trị vào `Environment` không tự động mã hóa hoặc bảo vệ bí mật.

### 3.3. Nguồn do tiến trình và hạ tầng cung cấp

Biến môi trường phù hợp với Docker, Kubernetes và CI/CD vì có thể thay đổi khi chạy mà không đóng gói lại ứng dụng. Chẳng hạn:

~~~bash
export SERVER_PORT=9090
export APP_TIMEOUT=15s
~~~

Với `@ConfigurationProperties`, quy tắc gắn kết linh hoạt (relaxed binding) giúp nối tên cấu hình Java với tên biến môi trường. Để chuyển tên thuộc tính chuẩn sang biến môi trường, thay dấu chấm bằng dấu gạch dưới, bỏ dấu gạch ngang và viết hoa: `spring.main.log-startup-info` tương ứng `SPRING_MAIN_LOGSTARTUPINFO`. Tránh đoán tên biến theo thói quen riêng khi thuộc tính chứa dấu gạch ngang.

Java System properties là nhóm khác với biến môi trường hệ điều hành:

~~~bash
java -Dapp.timeout=10s -jar app.jar
~~~

Tham số dạng `--key=value` của Spring Boot là một nguồn riêng:

~~~bash
java -jar app.jar --app.timeout=5s
~~~

Theo cấu hình mặc định, Spring Boot đưa những tùy chọn dòng lệnh này vào `Environment`. Chương trình có thể tắt cơ chế đó qua `SpringApplication.setAddCommandLineProperties(false)`, nhưng đa số ứng dụng giữ mặc định.

`SPRING_APPLICATION_JSON` dùng khi cần gửi nhiều khóa trong một biến:

~~~bash
SPRING_APPLICATION_JSON='{"app":{"timeout":"8s","region":"apac"}}' java -jar app.jar
~~~

Các giá trị JSON trở thành thuộc tính như `app.timeout` và `app.region`. Giá trị JSON `null` không thể dùng để “xóa” giá trị từ nguồn ưu tiên thấp hơn, vì cơ chế phân giải thuộc tính xem `null` là không có giá trị.

### 3.4. Những nguồn phụ thuộc ngữ cảnh

`RandomValuePropertySource` chủ yếu phục vụ các biểu thức thuộc nhóm `random.*`, không phải cơ chế thay thế cho bí mật được quản lý an toàn. JNDI và các tham số khởi tạo Servlet có thể xuất hiện trong ứng dụng web chạy dưới container tương ứng; nhiều ứng dụng Spring Boot chạy JAR độc lập sẽ không dùng tới chúng.

Trong kiểm thử, các thuộc tính khai báo ngay trên annotation kiểm thử và `@DynamicPropertySource` có thể bổ sung nguồn được ưu tiên riêng. Devtools cũng có nguồn cấu hình toàn cục khi được bật. Khi quan sát danh sách `PropertySource` ở một lần chạy test, đừng mặc định thứ tự và tên nguồn phải giống hoàn toàn lần chạy production.

## 4. Thứ tự ưu tiên: nhiều nguồn cùng có một khóa thì sao?

Với **một ứng dụng Spring Boot 3.3 chạy thông thường**, có thể đọc thứ tự sau từ **ưu tiên thấp đến cao**:

1. Giá trị mặc định do `SpringApplication.setDefaultProperties` cung cấp.
2. `@PropertySource` trên các lớp `@Configuration`.
3. Config Data: `application.properties`/YAML, tệp theo profile và các import liên quan.
4. `RandomValuePropertySource` (chỉ liên quan các khóa `random.*`).
5. Biến môi trường hệ điều hành.
6. Java System properties.
7. Thuộc tính JNDI `java:comp/env`.
8. Tham số khởi tạo `ServletContext`.
9. Tham số khởi tạo `ServletConfig`.
10. Thuộc tính từ `SPRING_APPLICATION_JSON`.
11. Tham số dòng lệnh `--...`.

Các nguồn riêng của kiểm thử và Devtools có thể nằm ở mức ưu tiên cao hơn trong những ngữ cảnh tương ứng. Trong danh sách trên, mục ở **dưới** có thể ghi đè mục ở **trên**. Còn khi duyệt `ConfigurableEnvironment.getPropertySources()` trong Java, nguồn được tra cứu trước xuất hiện trước trong danh sách duyệt; đừng nhầm hai chiều trình bày.

Ngay bên trong nhóm Config Data cũng có ưu tiên. Trường hợp phổ biến, khi cùng một khóa được khai báo ở nhiều nơi, thứ tự từ thấp đến cao là:

1. `application.properties`/YAML nằm **trong JAR**.
2. `application-{profile}.properties`/YAML nằm **trong JAR**.
3. `application.properties`/YAML nằm **ngoài JAR**.
4. `application-{profile}.properties`/YAML nằm **ngoài JAR**.

Vị trí tìm kiếm, nhóm location, nhiều profile đang hoạt động và `spring.config.import` có quy tắc chi tiết riêng. Bảng bốn mức trên giúp hình dung trường hợp thông dụng, không thay thế toàn bộ thuật toán Config Data. Nếu cùng vị trí có cả `.properties` và YAML tương ứng, Spring Boot ưu tiên `.properties`; nên chọn nhất quán một định dạng để tránh nhầm lẫn.

## 5. Ví dụ xuyên suốt: năm nguồn cùng tham gia một Environment

Giả sử ứng dụng có tệp mặc định `src/main/resources/application.yaml`:

~~~yaml
app:
  greeting: "Chào từ JAR"
  retries: 2
  endpoint: "https://api.example.test"
  feature-enabled: false
~~~

Khi triển khai production, đặt tệp `./config/application-prod.yaml` cạnh nơi chạy ứng dụng:

~~~yaml
app:
  greeting: "Chào từ tệp ngoài"
  retries: 5
  feature-enabled: true
~~~

Sau đó khởi chạy trên shell kiểu Unix:

~~~bash
APP_GREETING='Chào từ biến môi trường' java -Dapp.retries=8 -jar app.jar --spring.profiles.active=prod --app.greeting='Chào từ CLI'
~~~

Giả sử thư mục làm việc hiện tại chứa `./config/application-prod.yaml` và không có nguồn khác can thiệp, kết quả là:

| Thuộc tính | Giá trị có hiệu lực | Nguồn thắng |
| --- | --- | --- |
| `app.greeting` | `Chào từ CLI` | Tham số dòng lệnh, vượt lên biến môi trường và hai tệp. |
| `app.retries` | `8` | Java System property, vượt lên giá trị `5` trong tệp ngoài. |
| `app.endpoint` | `https://api.example.test` | Tệp mặc định trong JAR; không nguồn nào ghi đè khóa này. |
| `app.feature-enabled` | `true` | Tệp `application-prod.yaml` bên ngoài, do profile `prod` đang bật. |

Bốn giá trị có thể đến từ **ba nguồn khác nhau trong cùng một lần chạy**. Spring Boot không buộc chọn nguyên một tệp “chiến thắng”; nó phân giải từng thuộc tính theo thứ tự nguồn.

Nếu bỏ tham số `--app.greeting`, biến `APP_GREETING` sẽ thắng cho `app.greeting`. Nếu bỏ tiếp biến môi trường đó, giá trị trong tệp `application-prod.yaml` sẽ có hiệu lực. Nếu bỏ profile `prod`, tệp theo profile sẽ không còn được nạp theo cách trên.

## 6. Mã Java lấy giá trị từ Environment

Dùng `Environment` khi cần truy vấn trực tiếp một hoặc vài khóa:

~~~java
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Service;

@Service
public class GreetingService {
    private final Environment environment;

    public GreetingService(Environment environment) {
        this.environment = environment;
    }

    public String greeting() {
        return environment.getProperty("app.greeting", "Xin chào");
    }
}
~~~

Nếu mục tiêu là nhóm cấu hình có kiểu dữ liệu rõ ràng, `@ConfigurationProperties` thích hợp hơn. Với Java record:

~~~java
import java.net.URI;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public record AppProperties(
        String greeting,
        int retries,
        URI endpoint,
        boolean featureEnabled) {
}
~~~

Đăng ký record này bằng `@ConfigurationPropertiesScan` trên ứng dụng hoặc `@EnableConfigurationProperties(AppProperties.class)` trong cấu hình. Bộ gắn kết đọc giá trị hiệu lực từ `Environment` và chuyển sang kiểu tương ứng; ví dụ `feature-enabled` được gắn vào `featureEnabled`. `@Value("${app.greeting:Hi}")` cũng đọc được giá trị đơn lẻ, nhưng không thuận tiện bằng `@ConfigurationProperties` đối với nhóm thuộc tính có cấu trúc.

Lưu ý: `Environment` là cơ chế phân giải cấu hình tại thời điểm đọc, nhưng thay đổi tệp `application.yaml` sau khi ứng dụng đã chạy không có nghĩa Spring Boot sẽ tự nạp lại cấu hình hay cập nhật mọi bean. Cơ chế làm mới động cần giải pháp riêng.

## 7. Quan sát và xác định nguồn thắng

Khi một thuộc tính không có giá trị mong đợi, hãy kiểm tra **tên khóa, những nguồn thực sự được nạp, profile đang hoạt động và thứ tự ưu tiên**.

Có thể duyệt **tên nguồn** trong quá trình phát triển mà không in giá trị nhạy cảm:

~~~java
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.PropertySource;
import org.springframework.stereotype.Component;

@Component
class PropertySourceNames implements ApplicationRunner {
    private final ConfigurableEnvironment environment;

    PropertySourceNames(ConfigurableEnvironment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        for (PropertySource<?> source : environment.getPropertySources()) {
            System.out.println(source.getName());
        }
    }
}
~~~

Các nguồn được duyệt theo thứ tự tra cứu của `Environment`. Tên nguồn có thể chứa dấu hiệu vị trí tệp hoặc loại nguồn, giúp tìm nơi đặt cấu hình. Với ứng dụng cần giám sát, Spring Boot Actuator cung cấp endpoint `env` và `configprops` nếu được cấu hình/cho phép; chúng có thể chứa thông tin nhạy cảm nên cần hạn chế truy cập và dùng cơ chế che giá trị. Không đưa mật khẩu, token hoặc toàn bộ `Environment` vào log.

Để khảo sát quá trình nạp Config Data, có thể bật log mức TRACE cho `org.springframework.boot.context.config` trong môi trường phát triển. Lệnh này hữu ích khi một tệp ngoài JAR, một profile hoặc một import không được tải như dự kiến.

## 8. Những nhầm lẫn dễ gặp

- **“Spring Boot chỉ đọc application.yaml.”** Sai: tệp đó chỉ là một nhóm nguồn; biến môi trường, System properties, CLI và các nguồn khác cùng tham gia.
- **“Nguồn ưu tiên cao thay thế toàn bộ nguồn thấp hơn.”** Sai với tra cứu thuộc tính đơn lẻ: nguồn cao chỉ thắng ở những khóa mà nó cung cấp; khóa còn thiếu vẫn được tìm ở nguồn thấp.
- **“Chỉ cần tệp application-prod.yaml tồn tại là có hiệu lực.”** Cần kích hoạt profile tương ứng và để tệp ở vị trí được Spring Boot nạp.
- **“@PropertySource tương đương tệp application.properties về thời điểm nạp.”** Không hẳn: một số thuộc tính khởi động đã được xử lý trước khi `@PropertySource` tham gia.
- **“Tên biến môi trường luôn là thay dấu chấm và dấu gạch ngang thành dấu gạch dưới.”** Khi gắn kết theo quy tắc Spring Boot, dấu gạch ngang được **bỏ**, dấu chấm mới đổi thành gạch dưới rồi viết hoa.
- **“spring.config.location chỉ thêm một vị trí.”** Thuộc tính này thay thế những vị trí tìm mặc định; dùng `spring.config.additional-location` nếu muốn bổ sung mà vẫn giữ mặc định. Những khóa định vị này phải được cung cấp đủ sớm, ví dụ qua biến môi trường, JVM property hoặc CLI.
- **“Có thể dùng null trong SPRING_APPLICATION_JSON để xóa một giá trị cũ.”** `null` không ghi đè giá trị từ nguồn ưu tiên thấp theo cơ chế phân giải property thông thường.
- **“Đổi tệp cấu hình trên đĩa thì bean tự nhận giá trị mới.”** Không tự động; đây là câu chuyện làm mới cấu hình, khác với việc tổng hợp nguồn khi khởi động.

## 9. Tự thực hành

1. Tạo `application.yaml` có `app.mode: default` và `app.timeout: 30s`. Chạy với `APP_MODE=staging`, sau đó thêm `--app.mode=demo`. Truy vấn hai khóa qua `Environment`; giải thích vì sao `app.mode` đổi còn `app.timeout` giữ nguyên.
2. Bật profile `prod`, tạo `./config/application-prod.yaml` ghi đè `app.timeout`. Thêm `-Dapp.timeout=12s` để quan sát nguồn nào có hiệu lực. Bỏ từng nguồn theo thứ tự để thấy giá trị quay về lớp cấu hình phía dưới.
3. Liệt kê tên `PropertySource` khi chạy bình thường và khi chạy test. Quan sát sự khác biệt về nguồn và tránh in giá trị của các khóa nhạy cảm.

## 10. Ghi nhớ

`Environment` là điểm truy cập chung cho các thuộc tính được lấy từ nhiều `PropertySource` có thứ tự. Config Data cung cấp nền cấu hình theo tệp, vị trí, profile và import; môi trường hệ điều hành, JVM và tham số dòng lệnh giúp điều chỉnh theo nơi triển khai. Khi trùng khóa, thứ tự nguồn xác định giá trị có hiệu lực; khi một nguồn thiếu khóa, những nguồn phía dưới tiếp tục cung cấp giá trị. Hiểu ba ý này sẽ giúp bạn giải thích được phần lớn tình huống “vì sao ứng dụng đọc ra giá trị cấu hình này?”.

**Tài liệu tham khảo:** [Spring Boot 3.3 — Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html).
