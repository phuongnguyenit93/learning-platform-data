# Environment, PropertySource và giá trị cấu hình tại thời điểm chạy

Một ứng dụng Spring Boot thường có cùng một đoạn mã Java nhưng chạy trong nhiều môi trường khác nhau: local, test, staging và production. Địa chỉ database, thời gian chờ HTTP client, chế độ bật/tắt tính năng hoặc cổng server có thể khác nhau, dù không cần sửa mã nguồn.

Spring Boot giải quyết nhu cầu này bằng cơ chế **externalized configuration**. Ở trung tâm là `Environment` của Spring Framework, cùng tập các `PropertySource` được sắp xếp theo thứ tự ưu tiên. Khi ứng dụng hỏi giá trị của một property, Spring tìm qua những nguồn cấu hình đó và trả về giá trị có hiệu lực ở thời điểm truy vấn.

Điểm cần hiểu thật rõ: **“giá trị cấu hình tại thời điểm chạy” không đồng nghĩa với “mọi thay đổi file cấu hình đều cập nhật bean ngay lập tức”**. `Environment#getProperty(...)` có thể đọc trạng thái hiện tại của các nguồn property đã được lắp vào nó, nhưng `@Value`, `@ConfigurationProperties`, condition và các bean đã khởi tạo có vòng đời riêng. Chúng không mặc nhiên được cập nhật khi một file trên đĩa hoặc biến môi trường thay đổi.

Bài học thuộc chương **Cấu hình ứng dụng** của **Spring Boot Fundamentals**. Chúng ta sẽ tìm hiểu `Environment`, `PropertySource`, thứ tự ưu tiên, profile, Config Data, cách đọc cấu hình trong code, và cách xác định giá trị thực tế mà ứng dụng đang sử dụng.

## 1. Ba khái niệm nền tảng

Trong Spring, bạn nên phân biệt ba lớp ý nghĩa:

| Khái niệm | Vai trò | Ví dụ |
|---|---|---|
| `Environment` | Cung cấp API đọc property và thông tin profile cho ứng dụng | `environment.getProperty("app.name")` |
| `PropertySource` | Biểu diễn một nguồn cung cấp key-value cấu hình | PropertySource từ environment variables, system properties hoặc file YAML |
| `PropertySources` | Tập các PropertySource được sắp xếp theo thứ tự ưu tiên | `MutablePropertySources` trong `ConfigurableEnvironment` |

Ví dụ, một ứng dụng có thể nhận cùng property `app.message` từ nhiều nguồn:

```text
Command-line argument
    --app.message="from-cli"
                  │
                  ▼
Java system property
    -Dapp.message=from-system
                  │
                  ▼
OS environment variable
    APP_MESSAGE=from-env
                  │
                  ▼
application.yml
    app.message: from-yaml
```

Trong một cấu hình Spring Boot thông thường, command-line argument có mức ưu tiên cao hơn ba nguồn còn lại. Vì vậy:

```java
environment.getProperty("app.message")
```

có thể trả về `from-cli` dù `application.yml` chứa giá trị khác.

### 1.1. Một key có thể có nhiều giá trị

Spring không yêu cầu một key chỉ được khai báo đúng một lần. Các nguồn khác nhau có thể cung cấp cùng key để cho phép ghi đè cấu hình theo môi trường.

Ví dụ:

```yaml
# application.yml
app:
  message: "from-yaml"
```

Chạy:

```bash
java -jar demo.jar --app.message=from-cli
```

Khi đó `Environment` có thể biết cả nguồn file và nguồn command line, nhưng kết quả resolve thông thường là `from-cli` vì nguồn đó được ưu tiên hơn.

### 1.2. Environment không phải một file

`Environment` không đồng nghĩa với `application.yml`.

Nó là lớp trừu tượng tập hợp nhiều nguồn dữ liệu và quy tắc phân giải. Một số nguồn có thể không tồn tại dưới dạng file nào cả, chẳng hạn biến môi trường của tiến trình, Java system properties, command-line arguments hoặc map được thêm bởi code.

Vì vậy, khi một giá trị “khác với application.yml”, chưa chắc Spring đọc sai file. Có thể một nguồn ưu tiên cao hơn đã ghi đè nó.

## 2. Environment là interface gì?

`Environment` nằm trong Spring Framework:

```java
import org.springframework.core.env.Environment;
```

Interface này cho phép đọc properties và thông tin profile. Các phương thức thường dùng:

```java
String value = environment.getProperty("app.message");

String fallback = environment.getProperty(
        "app.message",
        "Hello"
);

Boolean enabled = environment.getProperty(
        "app.feature.enabled",
        Boolean.class,
        false
);

boolean exists = environment.containsProperty("app.message");

String required = environment.getRequiredProperty("app.message");

String[] active = environment.getActiveProfiles();

String[] defaults = environment.getDefaultProfiles();
```

Một số phương thức được kế thừa từ `PropertyResolver`.

### 2.1. getProperty trả về gì nếu key không tồn tại?

Với lệnh:

```java
String name = environment.getProperty("app.name");
```

nếu không tìm thấy property, kết quả là `null`.

Nếu muốn giá trị mặc định:

```java
String name = environment.getProperty(
        "app.name",
        "Spring Boot App"
);
```

Nếu cấu hình bắt buộc phải tồn tại:

```java
String name = environment.getRequiredProperty("app.name");
```

`getRequiredProperty` ném `IllegalStateException` khi property không có giá trị có thể resolve. Điều này có thể hữu ích cho kiểm tra cấu hình bắt buộc, nhưng đối với bộ cấu hình lớn và phức tạp, nên cân nhắc `@ConfigurationProperties` cùng validation.

### 2.2. getProperty với kiểu dữ liệu

Spring có thể chuyển đổi giá trị khi bạn yêu cầu kiểu cụ thể:

```java
boolean enabled = environment.getProperty(
        "app.feature.enabled",
        Boolean.class,
        false
);

int retries = environment.getProperty(
        "app.client.retries",
        Integer.class,
        3
);
```

Nếu giá trị được cấu hình không chuyển đổi được sang kiểu mong muốn, có thể phát sinh lỗi conversion thay vì nhận một giá trị hợp lệ.

Ví dụ:

```properties
app.client.retries=not-a-number
```

không phải số nguyên, nên không phù hợp với `Integer.class`.

### 2.3. Environment không chứa logic nghiệp vụ

Nên dùng `Environment` để truy vấn cấu hình, không dùng nó làm nơi lưu dữ liệu nghiệp vụ như trạng thái đơn hàng, số dư hoặc phiên đăng nhập.

Một property như `app.client.timeout` là cấu hình; một giá trị như “số tiền còn lại của tài khoản 123” là dữ liệu nghiệp vụ và cần được quản lý bởi hệ thống dữ liệu phù hợp.

## 3. Tiêm Environment vào một Spring bean

`Environment` thường đã có sẵn để inject trong Spring ApplicationContext.

Ví dụ:

```java
package com.example.demo.config;

import org.springframework.core.env.Environment;
import org.springframework.stereotype.Service;

@Service
public class GreetingService {

    private final Environment environment;

    public GreetingService(Environment environment) {
        this.environment = environment;
    }

    public String greeting() {
        return environment.getProperty(
                "app.greeting.message",
                "Xin chào"
        );
    }
}
```

File cấu hình:

```yaml
app:
  greeting:
    message: "Chào từ application.yml"
```

Một component khác có thể gọi:

```java
String text = greetingService.greeting();
```

Kết quả là giá trị có hiệu lực của `app.greeting.message` trong `Environment` tại lúc gọi.

### 3.1. Dùng Environment trong CommandLineRunner

Ví dụ quan sát cấu hình sau khi ApplicationContext được khởi tạo:

```java
package com.example.demo;

import org.springframework.boot.CommandLineRunner;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class ConfigurationPrinter implements CommandLineRunner {

    private final Environment environment;

    public ConfigurationPrinter(Environment environment) {
        this.environment = environment;
    }

    @Override
    public void run(String... args) {
        System.out.println(
                "app.greeting.message = "
                        + environment.getProperty(
                                "app.greeting.message",
                                "<missing>"
                        )
        );
    }
}
```

Ví dụ này chỉ in một property không nhạy cảm. **Không in toàn bộ Environment ra log**, vì có thể có password, API key, token hoặc dữ liệu nhạy cảm trong các nguồn cấu hình.

### 3.2. Đọc cấu hình trực tiếp trong mỗi request?

Có thể gọi `environment.getProperty(...)` bất cứ khi nào cần. Nhưng nếu property chỉ là cấu hình cố định của một service, đọc lặp lại qua nhiều request làm code khó kiểm thử và tăng mức phụ thuộc vào framework.

Trong nhiều trường hợp nên bind cấu hình thành một object rõ ràng bằng `@ConfigurationProperties`. Việc dùng `Environment` trực tiếp phù hợp cho infrastructure code, trường hợp cần truy vấn key linh hoạt hoặc bài toán cần thấy giá trị nguồn hiện tại.

## 4. PropertySource là gì?

`PropertySource<T>` nằm trong:

```java
import org.springframework.core.env.PropertySource;
```

Nó biểu diễn một nguồn có thể trả lời câu hỏi: “Trong nguồn này, key X có giá trị gì?”

Ở mức khái niệm:

```java
Object value = propertySource.getProperty("app.message");
```

Một `PropertySource` có:

- Tên nguồn, ví dụ `systemProperties`.
- Một object nguồn dữ liệu tương ứng.
- Logic tra cứu property theo key.
- Có thể trả về `null` nếu không có key được yêu cầu.

Các implementation thường gặp gồm `MapPropertySource` và `SystemEnvironmentPropertySource`, cùng các loại nguồn do Spring Boot tạo khi nạp Config Data.

### 4.1. Ví dụ MapPropertySource

```java
import java.util.HashMap;
import java.util.Map;
import org.springframework.core.env.MapPropertySource;

Map<String, Object> values = new HashMap<>();
values.put("app.message", "from-map");
values.put("app.feature.enabled", true);

MapPropertySource source = new MapPropertySource(
        "custom-map",
        values
);

System.out.println(source.getProperty("app.message"));
```

Kết quả:

```text
from-map
```

Đây mới là một nguồn riêng lẻ. Để nó tham gia quá trình resolve của ứng dụng, cần thêm nó vào tập PropertySources của `Environment`.

### 4.2. PropertySource có thể dùng key khác nhau

Một nguồn từ Java properties có thể có key `app.client.timeout`, còn OS environment thường dùng tên `APP_CLIENT_TIMEOUT`.

Spring Boot có quy tắc binding và chuyển đổi tên giúp làm việc với các kiểu tên khác nhau. Nhưng đừng giả định rằng gọi trực tiếp `propertySource.getProperty("app.client.timeout")` trên từng nguồn sẽ giống hoàn toàn với quá trình resolve/bind của toàn bộ Environment.

Khi debug, phải phân biệt **tra cứu trong một nguồn cụ thể** và **tra cứu qua Environment có nhiều nguồn, adapter và quy tắc xử lý tên**.

## 5. PropertySources và thứ tự ưu tiên

Một `ConfigurableEnvironment` cung cấp `MutablePropertySources`:

```java
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.MutablePropertySources;

MutablePropertySources sources =
        configurableEnvironment.getPropertySources();
```

`MutablePropertySources` cho phép bạn xem và thay đổi thứ tự các nguồn cấu hình.

Khi resolve một key, nguồn có ưu tiên cao hơn thường được kiểm tra trước. Nguồn đầu tiên cung cấp giá trị phù hợp có thể quyết định giá trị được trả về.

### 5.1. Sơ đồ

```text
Environment.getProperty("app.mode")
                    │
                    ▼
         PropertySource ưu tiên cao
         --app.mode=production
                    │
          Có giá trị? ───── Có ───► production
                    │
                   Không
                    ▼
         Java system properties
         -Dapp.mode=staging
                    │
          Có giá trị? ───── Có ───► staging
                    │
                   Không
                    ▼
         OS environment
         APP_MODE=development
                    │
          Có giá trị? ───── Có ───► development
                    │
                   Không
                    ▼
         application.yml
         app.mode: default
                    │
                    ▼
                  default
```

Đây là sơ đồ khái niệm để hình dung precedence. Trong thực tế, Spring Boot còn có Config Data, JSON, test properties và các nguồn khác được áp dụng theo quy tắc riêng.

### 5.2. Một số nguồn cấu hình phổ biến và ưu tiên tương đối

Trong ứng dụng Spring Boot thông thường, nếu cùng một key xuất hiện ở nhiều nguồn sau, thứ tự thường là:

| Nguồn | Ưu tiên tương đối |
|---|---|
| Command-line argument `--app.mode=...` | Cao hơn các nguồn liệt kê dưới |
| `SPRING_APPLICATION_JSON` | Dưới command line, có thể cao hơn system properties |
| Java system property `-Dapp.mode=...` | Cao hơn biến môi trường OS và Config Data |
| OS environment variable `APP_MODE` | Cao hơn Config Data |
| Config Data (`application.yml`, `application.properties`, file profile, external config) | Theo thứ tự Config Data |
| `@PropertySource` trong cấu hình Java | Thường thấp hơn Config Data; được thêm trong giai đoạn refresh |
| Default properties của `SpringApplication` | Mức mặc định thấp trong các nguồn thông thường |

Bảng này nhấn mạnh một số quan hệ thường gặp, **không phải bản liệt kê đầy đủ mọi PropertySource**. Test framework có thể thêm nguồn ưu tiên cao hơn; Servlet/JNDI và DevTools có thể thêm nguồn riêng; cách chọn file Config Data cũng có thứ tự nội bộ.

Vì vậy, khi cần kết luận chính xác, hãy xem PropertySources hiện có trong đúng tiến trình đang chạy thay vì chỉ thuộc lòng một bảng tổng quát.

### 5.3. Ví dụ ba nguồn xung đột

Trong `application.yml`:

```yaml
app:
  mode: from-file
```

Đặt environment variable:

```bash
export APP_MODE=from-environment
```

Chạy:

```bash
java -Dapp.mode=from-system -jar demo.jar --app.mode=from-command-line
```

Kết quả mong đợi của:

```java
environment.getProperty("app.mode")
```

là:

```text
from-command-line
```

Nếu bỏ command-line argument, system property có thể thắng. Nếu bỏ cả system property, OS environment variable có thể thắng file YAML.

Đừng bỏ qua sự khác biệt giữa biến môi trường và Java system property: `APP_MODE` thuộc môi trường tiến trình, còn `-Dapp.mode=...` được truyền cho JVM.

## 6. Config Data: application.yml và application.properties được nạp khi nào?

Spring Boot dùng cơ chế **Config Data** để nạp các file cấu hình ứng dụng ở giai đoạn bootstrap.

Ví dụ:

```yaml
# application.yml
app:
  client:
    endpoint: "https://api.example.test"
    timeout: 5s
```

Spring Boot đưa những giá trị này vào Environment thông qua các nguồn cấu hình phù hợp trước khi phần lớn bean definitions được tạo và các constructor/configuration properties được bind.

Những nguồn Config Data thường gặp:

- `application.properties` trong classpath.
- `application.yml` trong classpath.
- File cấu hình bên ngoài artifact.
- File theo profile như `application-prod.yml`.
- Các vị trí được chỉ định bằng `spring.config.location`.
- Vị trí bổ sung bằng `spring.config.additional-location`.
- Resource được import qua `spring.config.import`.

### 6.1. File bên trong JAR và file ngoài JAR

Ví dụ:

```text
application.jar
  └── BOOT-INF/classes/application.yml

./config/application.yml
```

Khi chạy từ thư mục có file cấu hình bên ngoài ở vị trí được Spring Boot tìm kiếm, cấu hình bên ngoài có thể có precedence cao hơn giá trị đóng gói trong JAR.

Cách này giúp một artifact được triển khai ở nhiều môi trường mà không cần rebuild chỉ để đổi một URL hoặc timeout.

### 6.2. Thứ tự trong nhóm Config Data

Với các vị trí mặc định được hỗ trợ, thứ tự ưu tiên phổ biến (từ thấp lên cao) có thể hiểu là:

1. File cấu hình thường được đóng gói trong JAR.
2. File cấu hình theo profile được đóng gói trong JAR.
3. File cấu hình thường bên ngoài JAR.
4. File cấu hình theo profile bên ngoài JAR.

Các config import hoặc location group tùy chỉnh có thể ảnh hưởng thứ tự hiệu lực, vì vậy đây là cách hình dung các trường hợp mặc định, không phải quy tắc cho mọi cấu hình file tùy chỉnh.

### 6.3. application.properties và application.yml cùng vị trí

Spring Boot hỗ trợ cả hai định dạng. Tuy nhiên, nên chọn **một định dạng chính cho một location** để tránh khó hiểu về precedence.

Nếu `application.properties` và `application.yml` cùng tồn tại tại một location, trong cách xử lý Config Data thông thường `.properties` được ưu tiên hơn YAML. Không nên cố tạo logic override nghiệp vụ dựa trên việc giữ cả hai file và phụ thuộc vào chi tiết này.

### 6.4. Config Data khác @PropertySource

File `application.yml` được Boot nạp trong quá trình chuẩn bị Environment. `@PropertySource` là một cơ chế của Spring Framework được xử lý khi các configuration classes tham gia refresh context.

Vì `@PropertySource` được thêm muộn hơn, nó không phù hợp cho một số property cần có trước refresh, chẳng hạn một số thiết lập `logging.*` hoặc `spring.main.*`.

Do đó, **không nên dùng `@PropertySource` để thay thế toàn bộ hệ Config Data của Spring Boot**.

## 7. Profile ảnh hưởng giá trị hiệu lực ra sao?

Profile giúp ứng dụng chọn nhóm cấu hình theo môi trường.

Ví dụ file chung:

```yaml
# application.yml
app:
  payment:
    endpoint: "https://sandbox.example.test"
    timeout: 3s
```

File production:

```yaml
# application-prod.yml
app:
  payment:
    endpoint: "https://payment.example.test"
    timeout: 10s
```

Chạy:

```bash
java -jar demo.jar --spring.profiles.active=prod
```

Khi đó `Environment` có thể resolve:

```text
app.payment.endpoint = https://payment.example.test
app.payment.timeout  = 10s
```

vì file theo profile `prod` được nạp và có thể ghi đè những key tương ứng từ file chung.

### 7.1. Đọc active profiles

```java
import java.util.Arrays;
import org.springframework.core.env.Environment;

String[] activeProfiles = environment.getActiveProfiles();

System.out.println(Arrays.toString(activeProfiles));
```

Nếu chạy với `--spring.profiles.active=prod`, mảng thường chứa `prod`.

`getDefaultProfiles()` trả về danh sách default profiles được sử dụng khi không có profile active được chọn.

### 7.2. Một ứng dụng có thể có nhiều profile

Ví dụ:

```bash
java -jar demo.jar --spring.profiles.active=prod,metrics
```

Các profile có thể đóng góp cấu hình từ nhiều nguồn. Nếu các profile-specific files đặt cùng một key, thứ tự áp dụng profile và Config Data ảnh hưởng giá trị cuối.

Vì vậy, khi debug hãy kiểm tra **danh sách profile active thực tế**, không chỉ xem một file `application-prod.yml`.

### 7.3. Profile không giống OS environment

Từ “environment” trong “development environment” và `Environment` API của Spring có liên quan nhưng không đồng nhất.

- **Profile** là nhãn để lựa chọn các cấu hình/bean phù hợp.
- **OS environment variable** là biến môi trường của tiến trình.
- **Spring Environment** là abstraction cho cả properties lẫn profiles.

Ví dụ, có thể bật profile `prod` bằng biến môi trường `SPRING_PROFILES_ACTIVE`, nhưng điều đó không khiến profile và environment variable trở thành cùng một cơ chế.

## 8. Đặt property bằng biến môi trường

Trong triển khai container hoặc cloud, cấu hình qua OS environment variables rất phổ biến.

Ví dụ file YAML:

```yaml
app:
  feature:
    enabled: false
```

Có thể ghi đè bằng:

```bash
APP_FEATURE_ENABLED=true java -jar demo.jar
```

Trên một shell không hỗ trợ cú pháp gán biến tạm ở trước lệnh, cần đặt biến theo cú pháp của shell đó. Ví dụ PowerShell:

```powershell
$env:APP_FEATURE_ENABLED = "true"
java -jar demo.jar
```

Spring Boot có cơ chế relaxed binding hỗ trợ ánh xạ tên property chuẩn sang cách đặt tên environment variables phù hợp. Ví dụ `app.feature.enabled` tương ứng `APP_FEATURE_ENABLED`.

### 8.1. Cẩn thận với dấu gạch ngang

Với tên property canonical dạng kebab-case, quy tắc chuyển sang environment variable của Boot thường là:

1. Thay dấu chấm `.` bằng dấu gạch dưới `_`.
2. Bỏ dấu gạch ngang `-`.
3. Chuyển sang chữ hoa.

Ví dụ:

```text
spring.main.log-startup-info
        ↓
SPRING_MAIN_LOGSTARTUPINFO
```

Không nên tự đoán rằng mọi dấu gạch ngang luôn chuyển thành một dấu gạch dưới mới. Đối với `@ConfigurationProperties` và các kiểu bind phức tạp, hãy dùng tên canonical và kiểm tra quy tắc relaxed binding của Spring Boot.

### 8.2. Biến môi trường không nhất thiết thay đổi trong JVM đang chạy

OS environment variables được cung cấp cho tiến trình khi nó khởi động. Việc người vận hành chỉnh biến trong shell mới hoặc chỉnh cấu hình deployment bên ngoài **không tự sửa Environment của JVM đã chạy**.

Trong container orchestration, thay đổi environment variables thường yêu cầu restart hoặc rollout process mới để giá trị mới có hiệu lực.

Điều này khác với việc một MapPropertySource trong bộ nhớ được code chủ động cập nhật.

## 9. Java system properties và command-line arguments

### 9.1. Java system property

Chạy:

```bash
java -Dapp.client.retries=5 -jar demo.jar
```

Trong code Java:

```java
String raw = System.getProperty("app.client.retries");
```

Có thể trả về `5`.

Qua Spring:

```java
int retries = environment.getProperty(
        "app.client.retries",
        Integer.class,
        3
);
```

Trong cấu hình thông thường, Environment có thể resolve cùng system property đó, trừ khi một nguồn ưu tiên cao hơn ghi đè key.

### 9.2. Command-line argument

Chạy:

```bash
java -jar demo.jar --app.client.retries=8
```

Spring Boot có thể chuyển đối số dạng `--key=value` thành một nguồn property có ưu tiên cao.

Nếu đồng thời có `-Dapp.client.retries=5`, giá trị `8` từ command line thường thắng.

### 9.3. Không nhầm application arguments với Environment

`ApplicationArguments` giúp xử lý đối số dòng lệnh theo dạng option/non-option:

```java
public void run(ApplicationArguments args) {
    boolean hasMode = args.containsOption("mode");
}
```

`Environment` cung cấp cách xem giá trị cấu hình hiệu lực từ nhiều nguồn:

```java
String mode = environment.getProperty("app.mode");
```

Hai API phục vụ mục đích khác nhau, dù một command-line option có thể xuất hiện trong cả hai.

## 10. Placeholder: tham chiếu giá trị cấu hình khác

Spring hỗ trợ placeholder có cú pháp `${...}` trong nhiều ngữ cảnh cấu hình và injection.

Ví dụ:

```yaml
app:
  service:
    host: "localhost"
    port: 8081
    url: "http://${app.service.host}:${app.service.port}"
```

Khi resolve `app.service.url`, Spring có thể dùng các property `host` và `port` để tạo giá trị đầy đủ.

Ví dụ:

```java
String url = environment.getProperty("app.service.url");
```

có thể trả:

```text
http://localhost:8081
```

### 10.1. Placeholder có giá trị mặc định

```yaml
app:
  endpoint: "https://${API_HOST:api.example.test}"
```

Nếu không có property/environment variable thích hợp, phần sau dấu hai chấm cung cấp giá trị mặc định.

Trong `@Value`:

```java
@Value("${app.client.retries:3}")
private int retries;
```

Nếu key không tồn tại, giá trị mặc định là `3`.

### 10.2. resolvePlaceholders và resolveRequiredPlaceholders

`Environment` cung cấp:

```java
String value = environment.resolvePlaceholders(
        "Endpoint = ${app.service.url}"
);
```

Ngoài ra:

```java
String value = environment.resolveRequiredPlaceholders(
        "Endpoint = ${app.service.url}"
);
```

Phương thức required sẽ báo lỗi nếu có placeholder không thể resolve theo các quy tắc tương ứng.

Cần phân biệt default value ở cấp placeholder với default value khi gọi `getProperty(key, defaultValue)`. Cả hai giúp ứng dụng xử lý property chưa có giá trị, nhưng diễn ra ở ngữ cảnh khác nhau.

## 11. @Value và Environment: snapshot hay live lookup?

Một bean có thể nhận cấu hình bằng `@Value`:

```java
package com.example.demo;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class GreetingSettings {

    private final String message;

    public GreetingSettings(
            @Value("${app.greeting.message:Hello}") String message
    ) {
        this.message = message;
    }

    public String message() {
        return message;
    }
}
```

Khi Spring tạo `GreetingSettings`, placeholder được resolve và truyền vào constructor. Field `message` lưu giá trị đã inject.

Trong khi đó, bean dùng `Environment` có thể truy vấn lại ở mỗi lời gọi:

```java
@Component
public class GreetingReader {

    private final Environment environment;

    public GreetingReader(Environment environment) {
        this.environment = environment;
    }

    public String readNow() {
        return environment.getProperty(
                "app.greeting.message",
                "Hello"
        );
    }
}
```

Hai cách có ý nghĩa khác nhau:

| Cách đọc | Thời điểm đọc thông thường | Khi nguồn property trong bộ nhớ thay đổi |
|---|---|---|
| `@Value` trên constructor/field | Khi bean được tạo và inject | Giá trị đã inject thường không tự đổi |
| `@ConfigurationProperties` | Khi bean cấu hình được bind/tạo | Object đã bind không tự được bind lại |
| `environment.getProperty(...)` trong method | Mỗi lần method gọi property resolver | Có thể thấy giá trị mới nếu PropertySource thực tế đã cập nhật và không bị nguồn ưu tiên cao hơn ghi đè |

“Environment là live lookup” **không có nghĩa** Spring tự đọc lại `application.yml` trên đĩa hoặc mọi property source luôn tự thay đổi. Nó chỉ nói rằng lần gọi mới truy vấn trạng thái nguồn đã được container cấu hình tại thời điểm đó.

### 11.1. Vì sao giá trị @Value không tự đổi?

Spring không liên tục kiểm tra source rồi gán lại mọi field đã inject. Điều đó còn có thể phá vỡ các bất biến của object và tạo lỗi đồng thời.

Ví dụ, nếu `GreetingSettings` được tạo với `message = "Hello"`, một nguồn property mới được thêm sau đó không tự gọi lại constructor hoặc thay field `final`.

Nếu cần một feature flag thay đổi tại runtime, hãy thiết kế component đọc nguồn động có chủ đích thay vì mặc định coi `@Value` như một observable variable.

## 12. @ConfigurationProperties: binding có kiểu và cấu trúc

Khi ứng dụng có nhiều property liên quan, `@ConfigurationProperties` thường phù hợp hơn gọi `getProperty` nhiều lần.

Ví dụ cấu hình:

```yaml
app:
  client:
    endpoint: "https://api.example.test"
    timeout: 5s
    retries: 3
```

Với Spring Boot 3 và Java tương thích:

```java
package com.example.demo.config;

import java.net.URI;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
        URI endpoint,
        Duration timeout,
        int retries
) {
}
```

Bật scanning cho các class `@ConfigurationProperties`:

```java
package com.example.demo;

import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class DemoApplication {
}
```

Sau đó inject `ClientProperties` qua constructor:

```java
@Service
public class ApiClient {

    private final ClientProperties properties;

    public ApiClient(ClientProperties properties) {
        this.properties = properties;
    }

    public void connect() {
        URI endpoint = properties.endpoint();
        Duration timeout = properties.timeout();
        // Dùng endpoint và timeout để cấu hình client.
    }
}
```

### 12.1. Lợi ích

- Type-safe: có thể bind `Duration`, `URI`, số nguyên, boolean và nested objects.
- Có cấu trúc rõ ràng theo prefix.
- Dễ kiểm tra bằng validation.
- Dễ dùng trong unit test.
- Phù hợp khi nhiều giá trị cùng cấu hình một client/service.
- Spring Boot hỗ trợ relaxed binding từ nhiều nguồn cấu hình.

### 12.2. Binding vẫn có vòng đời

`@ConfigurationProperties` được bind khi bean tương ứng được tạo hoặc qua hạ tầng binding phù hợp, **không mặc nhiên bind lại sau mọi thay đổi nguồn property**.

Ví dụ, file `application.yml` đổi từ `timeout: 5s` sang `timeout: 10s` khi ứng dụng đang chạy sẽ không tự làm object `ClientProperties` đang tồn tại thay đổi.

Để áp dụng cấu hình mới theo mô hình mặc định, thường cần restart ứng dụng hoặc một cơ chế refresh/rebind được thiết kế tường minh.

### 12.3. Khi nào dùng Environment thay cho ConfigurationProperties?

Dùng `Environment` khi:

- Cần truy vấn một property bất kỳ theo key động.
- Viết infrastructure component hoặc startup diagnostics.
- Cần quan sát giá trị đang được resolver trả về.
- Cần kiểm tra active profiles.
- Cần thao tác với PropertySources trong một hạ tầng chuyên biệt.

Dùng `@ConfigurationProperties` khi một nhóm property là hợp đồng cấu hình của một bean hoặc subsystem. Đó là lựa chọn phổ biến cho application code.

## 13. ConfigurableEnvironment và MutablePropertySources

`Environment` là API đọc. Nếu thực sự cần tùy chỉnh tập nguồn property, làm việc với `ConfigurableEnvironment`:

```java
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.MutablePropertySources;
import org.springframework.core.env.PropertySource;
```

Một số thao tác:

```java
MutablePropertySources sources =
        configurableEnvironment.getPropertySources();

sources.addFirst(customPropertySource);
sources.addLast(otherPropertySource);

PropertySource<?> systemProperties =
        sources.get("systemProperties");
```

Ý nghĩa:

- `addFirst(...)`: thêm nguồn ở vị trí ưu tiên cao trong tập hiện tại.
- `addLast(...)`: thêm nguồn ở vị trí ưu tiên thấp.
- `addBefore(...)`, `addAfter(...)`: chèn tương đối so với một source name cụ thể.
- `remove(...)`: loại một source theo tên.
- `replace(...)`: thay một source có tên đã biết.

Các thao tác này ảnh hưởng việc resolve properties **từ thời điểm thay đổi trở đi**, nhưng không tự thay đổi bean đã bind cấu hình.

### 13.1. Ví dụ thêm một nguồn tùy chỉnh

```java
Map<String, Object> overrides = new HashMap<>();
overrides.put("app.message", "custom-value");

MapPropertySource customSource =
        new MapPropertySource("manual-overrides", overrides);

configurableEnvironment.getPropertySources()
        .addFirst(customSource);

System.out.println(
        configurableEnvironment.getProperty("app.message")
);
```

Nếu không có điều kiện đặc biệt, kết quả là:

```text
custom-value
```

vì nguồn tùy chỉnh vừa được thêm ở đầu tập PropertySources.

### 13.2. Tại sao không nên tùy tiện gọi addFirst?

`addFirst` có thể ghi đè giá trị đến từ command line, system property hoặc file cấu hình. Điều này có thể gây bất ngờ cho người vận hành.

Nếu thực sự cần cấu hình mặc định, `addLast` hoặc `SpringApplication#setDefaultProperties` có thể phù hợp hơn. Nếu cần override có chủ đích, hãy đặt tên nguồn rõ ràng và ghi lại nguồn đó được thêm ở giai đoạn nào.

Không dùng việc thay đổi PropertySources trong business method như một cách quản lý trạng thái nghiệp vụ.

## 14. Thời điểm thêm PropertySource ảnh hưởng kết quả

Có hai thời điểm cần phân biệt:

1. **Trước khi context hoàn tất tạo bean:** property mới có thể ảnh hưởng injection, binding hoặc condition chưa được đánh giá.
2. **Sau khi context đã khởi tạo:** property mới có thể ảnh hưởng các lần lookup tiếp theo, nhưng không tự đảo ngược các quyết định đăng ký bean hoặc bind cấu hình đã hoàn thành.

Sơ đồ:

```text
Khởi động JVM
      │
      ▼
SpringApplication chuẩn bị Environment
      │
      ▼
Đọc Config Data và thêm PropertySources
      │
      ▼
Xử lý configuration và @Conditional
      │
      ▼
Tạo bean, inject @Value,
bind @ConfigurationProperties
      │
      ▼
ApplicationReadyEvent
      │
      ▼
Ứng dụng đang chạy
      │
      ├── Environment#getProperty(...)
      │       đọc nguồn property hiện tại
      │
      └── @Value / ConfigurationProperties
              đã được inject/bind trước đó
```

Đây là mô hình đơn giản. Spring Boot còn nhiều lifecycle events và post-processors, nhưng quan hệ thời điểm trên là mấu chốt.

### 14.1. Thêm nguồn trước khi bean được tạo

Bạn có thể thêm source thông qua `ApplicationContextInitializer`:

```java
package com.example.demo;

import java.util.Map;
import org.springframework.boot.SpringApplication;
import org.springframework.core.env.MapPropertySource;

public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(DemoConfiguration.class);

        application.addInitializers(context -> {
            Map<String, Object> overrides = Map.of(
                    "app.message", "from-initializer"
            );

            context.getEnvironment()
                    .getPropertySources()
                    .addFirst(new MapPropertySource(
                            "bootstrap-overrides",
                            overrides
                    ));
        });

        application.run(args);
    }
}
```

Ở đây, source được thêm trong giai đoạn khởi tạo context, trước khi phần lớn application beans được tạo. Bean được inject `app.message` sau đó có thể nhận giá trị `from-initializer` theo precedence.

Lưu ý rằng một số property đặc biệt ảnh hưởng đến chính `SpringApplication` hoặc logging **được đọc sớm hơn giai đoạn initializer**. Nếu cần tác động đến những thiết lập cực sớm đó, hãy dùng cơ chế configuration được nạp ở thời điểm thích hợp như Config Data, command line hoặc EnvironmentPostProcessor.

### 14.2. EnvironmentPostProcessor

Spring Boot cung cấp extension point `EnvironmentPostProcessor` để tùy chỉnh Environment trong quá trình chuẩn bị ứng dụng.

Ví dụ ở mức khái niệm:

```java
package com.example.demo.bootstrap;

import java.util.Map;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.env.EnvironmentPostProcessor;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.MapPropertySource;

public class CustomEnvironmentPostProcessor
        implements EnvironmentPostProcessor {

    @Override
    public void postProcessEnvironment(
            ConfigurableEnvironment environment,
            SpringApplication application
    ) {
        environment.getPropertySources().addLast(
                new MapPropertySource(
                        "custom-defaults",
                        Map.of("app.feature.enabled", "false")
                )
        );
    }
}
```

Để extension point này được nạp, thư viện phải đăng ký implementation theo cơ chế Spring Boot tương ứng, phổ biến là entry `EnvironmentPostProcessor` trong `META-INF/spring.factories`.

Không cần tự viết `EnvironmentPostProcessor` để đọc `application.yml`. Đây là công cụ dành cho thư viện hạ tầng hoặc yêu cầu bootstrap đặc biệt.

## 15. Demo: Environment có thể đổi, @Value vẫn giữ giá trị cũ

Ví dụ sau cố ý thay đổi một PropertySource **trong bộ nhớ** sau khi context đã refresh. Mục tiêu là quan sát khác biệt giữa lần lookup mới và giá trị đã inject trước đó.

### 15.1. application.yml

```yaml
app:
  greeting:
    message: "from-yaml"
```

### 15.2. Bean nhận giá trị bằng @Value

```java
package com.example.demo;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class GreetingSnapshot {

    private final String message;

    public GreetingSnapshot(
            @Value("${app.greeting.message}") String message
    ) {
        this.message = message;
    }

    public String message() {
        return message;
    }
}
```

### 15.3. Runner bổ sung property source lúc runtime

```java
package com.example.demo;

import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import org.springframework.boot.CommandLineRunner;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.MapPropertySource;
import org.springframework.stereotype.Component;

@Component
public class RuntimePropertyDemo implements CommandLineRunner {

    private final ConfigurableEnvironment environment;
    private final GreetingSnapshot snapshot;

    public RuntimePropertyDemo(
            ConfigurableEnvironment environment,
            GreetingSnapshot snapshot
    ) {
        this.environment = environment;
        this.snapshot = snapshot;
    }

    @Override
    public void run(String... args) {
        System.out.println("Trước: "
                + environment.getProperty("app.greeting.message"));
        System.out.println("Snapshot: " + snapshot.message());

        ConcurrentMap<String, Object> values =
                new ConcurrentHashMap<>();
        values.put("app.greeting.message", "from-runtime-map");

        environment.getPropertySources().addFirst(
                new MapPropertySource("runtime-overrides", values)
        );

        System.out.println("Sau: "
                + environment.getProperty("app.greeting.message"));
        System.out.println("Snapshot: " + snapshot.message());
    }
}
```

Với ví dụ và precedence như trên, log minh họa:

```text
Trước: from-yaml
Snapshot: from-yaml
Sau: from-runtime-map
Snapshot: from-yaml
```

Lý do:

- `Environment#getProperty(...)` thực hiện một lần resolve mới qua tập PropertySources hiện tại.
- `GreetingSnapshot` giữ giá trị mà Spring đã inject khi tạo bean.
- Việc thêm source runtime không yêu cầu Spring tạo lại `GreetingSnapshot`.

### 15.4. Đây không phải cơ chế cấu hình động hoàn chỉnh

Ví dụ chỉ minh họa đặc tính lookup của Environment. Trong ứng dụng production, thay đổi property sources cần xem xét:

- Đồng thời giữa các thread.
- Validation và atomic update cho nhóm property liên quan.
- Quyền truy cập và audit khi cấu hình thay đổi.
- Side effect lên component có thể đọc property tại nhiều thời điểm.
- Các bean đã bind/configure trước đó không được cập nhật.
- Những property được sử dụng trong lúc startup không tự được áp dụng lại.

Nếu cần cấu hình runtime động, hãy thiết kế một service/cache cấu hình có hợp đồng rõ ràng, hoặc dùng công cụ cấu hình động thích hợp.

## 16. Vì sao sửa application.yml khi app chạy thường không có tác dụng?

Giả sử ứng dụng đang chạy với:

```yaml
app:
  client:
    timeout: 5s
```

Bạn sửa file thành:

```yaml
app:
  client:
    timeout: 10s
```

Trong Spring Boot thông thường, file Config Data đã được đọc và đưa giá trị vào các PropertySources trong quá trình startup. Spring Boot **không mặc định theo dõi mọi file YAML trên đĩa để nạp lại ngay**.

Do đó:

- `Environment#getProperty("app.client.timeout")` có thể vẫn trả `5s` vì PropertySource đang giữ dữ liệu đã nạp.
- Một bean `@ConfigurationProperties` có thể vẫn giữ `Duration.ofSeconds(5)`.
- Một field `@Value` vẫn giữ giá trị đã inject trước đó.
- Một condition `@ConditionalOnProperty` không tự được đánh giá lại để tạo/hủy bean.

Muốn dùng `10s` theo cách đơn giản, hãy restart ứng dụng sau khi chỉnh cấu hình hoặc triển khai phiên bản cấu hình mới theo quy trình vận hành.

### 16.1. Trường hợp nguồn thực sự thay đổi

Nếu một PropertySource được xây dựng để đọc từ một nguồn thay đổi theo thời gian, hoặc code chủ động thay nội dung map trong bộ nhớ, lời gọi `Environment#getProperty(...)` tiếp theo **có thể** thấy giá trị mới.

Điều đó chỉ đúng cho các nguồn có hành vi động tương ứng. Không được suy ra rằng mọi PropertySource tự làm vậy.

### 16.2. System.setProperty có thể khác việc sửa OS environment

Ví dụ:

```java
System.setProperty("app.message", "new-system-value");

String now = environment.getProperty("app.message");
```

Nếu không có nguồn ưu tiên cao hơn ghi đè, Environment có thể thấy giá trị mới từ Java system properties. Đây là thay đổi trong JVM hiện tại.

Ngược lại, chạy `export APP_MESSAGE=...` trong một shell khác sau khi JVM đã khởi động không làm môi trường của tiến trình Java tự đổi.

## 17. Condition, @Profile và giá trị lúc đăng ký bean

Một condition có thể sử dụng Environment để quyết định bean nào được đăng ký:

```java
@Configuration(proxyBeanMethods = false)
public class FeatureConfiguration {

    @Bean
    @ConditionalOnProperty(
            prefix = "app.feature",
            name = "enabled",
            havingValue = "true"
    )
    public FeatureService featureService() {
        return new FeatureService();
    }
}
```

Nếu `app.feature.enabled=false` ở lúc condition được đánh giá, bean definition từ method trên không được đăng ký.

Thay đổi một PropertySource thành `true` sau khi context đã sẵn sàng **không tự làm Spring chạy lại condition và đăng ký FeatureService**.

Tương tự, `@Profile("prod")` được xét trong quá trình xử lý configuration. Thay đổi danh sách active profiles sau khi context khởi tạo không tự tạo lại những bean trước đó đã bị bỏ qua.

### 17.1. Phân biệt ba thời điểm

| Thao tác | Thời điểm thông thường | Khi property thay đổi sau startup |
|---|---|---|
| `@ConditionalOnProperty` | Khi xử lý configuration/bean definitions | Không tự đánh giá lại |
| `@Value` và `@ConfigurationProperties` | Khi bean được tạo hoặc binding diễn ra | Không tự inject/bind lại |
| `Environment#getProperty` | Khi method được gọi | Có thể thấy thay đổi nếu nguồn thực sự đổi |

Đây là bảng quan trọng khi debug tính năng bật/tắt theo cấu hình.

### 17.2. Khi nào dùng feature flag runtime?

Nếu yêu cầu nghiệp vụ là bật/tắt một tính năng **mà không restart**, condition khi đăng ký bean thường không phù hợp.

Hãy giữ bean/service đã tồn tại, nhưng cho nó tham khảo một nguồn feature flag có thể thay đổi có kiểm soát:

```java
@Service
public class NotificationService {

    private final FeatureFlagService flags;

    public NotificationService(FeatureFlagService flags) {
        this.flags = flags;
    }

    public void notifyUser(String message) {
        if (!flags.isEnabled("notification")) {
            return;
        }

        // Thực hiện gửi thông báo.
    }
}
```

`FeatureFlagService` trong ví dụ là abstraction do ứng dụng cung cấp. Cách triển khai và quản lý thay đổi của nó là một bài toán runtime riêng, không phải hành vi mặc định của `@ConditionalOnProperty`.

## 18. Config import và cấu hình từ nhiều file

Spring Boot hỗ trợ import Config Data qua `spring.config.import`.

Ví dụ:

```yaml
spring:
  config:
    import: "optional:file:./config/extra.yml"

app:
  greeting:
    message: "from-main-file"
```

File ngoài:

```yaml
# ./config/extra.yml
app:
  greeting:
    message: "from-imported-file"
```

Khi import được resolve, file import có thể đóng góp một PropertySource có precedence cao hơn tài liệu khai báo import theo quy tắc Config Data.

### 18.1. optional: là gì?

Prefix `optional:` cho phép ứng dụng tiếp tục nếu vị trí cấu hình được chỉ định không tồn tại, thay vì fail startup vì không tìm thấy Config Data resource.

Ví dụ:

```yaml
spring:
  config:
    import: "optional:file:./config/extra.yml"
```

Nếu `extra.yml` không có, Boot có thể bỏ qua vị trí optional đó.

Điều này có ích khi một file cấu hình chỉ tồn tại trong một số môi trường. Tuy nhiên, với cấu hình bắt buộc như thông tin kết nối thiết yếu, việc đánh dấu optional có thể che giấu lỗi triển khai. Hãy chọn theo yêu cầu hệ thống.

### 18.2. Config import không phải runtime refresh

Việc import một file ngoài JAR chỉ làm Spring Boot nạp nó ở quá trình xử lý Config Data. Nó **không tự biến file thành một nguồn được theo dõi và reload liên tục**.

Nếu người vận hành chỉnh file import sau startup, thông thường vẫn cần restart hoặc cơ chế refresh được thiết kế riêng.

## 19. @PropertySource: thêm nguồn từ Java configuration

Spring Framework cho phép:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.PropertySource;

@Configuration(proxyBeanMethods = false)
@PropertySource("classpath:legacy.properties")
public class LegacyPropertiesConfiguration {
}
```

Ví dụ file:

```properties
# src/main/resources/legacy.properties
legacy.feature.enabled=true
```

Khi configuration class được xử lý, Spring thêm PropertySource tương ứng để Environment có thể resolve key `legacy.feature.enabled`.

### 19.1. Khi nào dùng @PropertySource?

Hữu ích khi cần tích hợp một file `.properties` của thư viện cũ, hoặc khi một cấu hình Java chủ động bổ sung property resource.

Nhưng nó không phải lựa chọn mặc định cho cấu hình ứng dụng Spring Boot mới. `application.yml` và Config Data giải quyết tốt hơn các yêu cầu profile, external config và bootstrap.

### 19.2. @PropertySource không tự hỗ trợ YAML như application.yml

Mặc định `@PropertySource` dùng cơ chế property source factory phù hợp với Java properties và không cung cấp parsing YAML theo cách Spring Boot nạp `application.yml`.

Nếu muốn đọc YAML qua `@PropertySource`, cần một `PropertySourceFactory` tùy chỉnh hoặc dùng Config Data, nhưng với ứng dụng Boot thông thường, hãy ưu tiên Config Data thay vì tự triển khai YAML loader.

### 19.3. Một số cấu hình cần có rất sớm

Các giá trị điều khiển chính SpringApplication hoặc logging được đọc sớm. `@PropertySource` được xử lý trong giai đoạn context refresh, nên có thể quá muộn để ảnh hưởng chúng.

Ví dụ, khi cần cấu hình `spring.main.banner-mode` hoặc các property logging khởi động, hãy dùng `application.yml`/`application.properties`, command-line arguments, environment variables hoặc nguồn bootstrap phù hợp.

## 20. Xem các PropertySource thực tế đang có

Khi cần xác định vì sao property bị ghi đè, bạn có thể inspect danh sách nguồn đang có trong `ConfigurableEnvironment`.

```java
package com.example.demo.diagnostics;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.PropertySource;
import org.springframework.stereotype.Component;

@Component
public class PropertySourceNamesPrinter implements ApplicationRunner {

    private final ConfigurableEnvironment environment;

    public PropertySourceNamesPrinter(
            ConfigurableEnvironment environment
    ) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        System.out.println("Các PropertySource hiện có:");

        for (PropertySource<?> source :
                environment.getPropertySources()) {
            System.out.println("- " + source.getName());
        }
    }
}
```

Ví dụ log tên source có thể chứa:

```text
commandLineArgs
systemProperties
systemEnvironment
...
```

**Tên nguồn thực tế có thể khác giữa các phiên bản Spring Boot và các loại ứng dụng.** Đừng hard-code việc chẩn đoán dựa vào một tên file hoặc source name mà không kiểm tra context đang chạy.

### 20.1. Vì sao chỉ in tên nguồn, không in tất cả giá trị?

PropertySources có thể chứa:

- Database passwords.
- API tokens.
- OAuth client secrets.
- Private keys hoặc thông tin truy cập dịch vụ.
- Cấu hình endpoint nội bộ.

In toàn bộ property values ra stdout hoặc log có thể làm lộ bí mật. Khi chẩn đoán, ưu tiên in danh sách nguồn và chỉ truy vấn **những key không nhạy cảm** đã được xác định.

### 20.2. Nếu muốn xem source nào thắng

Với key an toàn như `app.greeting.message`, có thể in giá trị resolve của Environment:

```java
System.out.println(
        environment.getProperty("app.greeting.message")
);
```

Sau đó xem các nguồn có liên quan. Tuy nhiên, việc gọi trực tiếp `source.getProperty(key)` trên từng nguồn không luôn tái hiện toàn bộ relaxed binding hoặc adapter logic của Boot. Vì vậy không nên viết một bộ debug thủ công quá đơn giản rồi coi kết quả của nó là lời giải tuyệt đối.

Đối với Boot hiện đại, Actuator và các API origin-aware có thể hỗ trợ thông tin chính xác hơn.

## 21. Actuator và nguồn gốc của một property

Spring Boot Actuator có những endpoint hữu ích cho việc điều tra cấu hình:

- `/actuator/env`: thông tin Environment và các nguồn property theo khả năng được cấu hình/expose.
- `/actuator/configprops`: thông tin các bean dùng `@ConfigurationProperties` và dữ liệu binding có thể quan sát.
- `/actuator/conditions`: báo cáo condition evaluation, giúp xác định một auto-configuration được áp dụng hoặc bị loại vì sao.

Để sử dụng, ứng dụng cần dependency Actuator và cấu hình endpoint exposure/security phù hợp.

### 21.1. Actuator không tự làm lộ mọi giá trị

Các endpoint cấu hình có cơ chế sanitization hoặc chính sách hiển thị giá trị. Tùy phiên bản Boot, giá trị có thể bị che và việc cho phép xem giá trị cần cấu hình rõ ràng.

Không nên bật hiển thị toàn bộ config values trên production chỉ để debug một property. Dữ liệu cấu hình có thể chứa secret; endpoint cần được bảo vệ bằng authentication, authorization và network policy thích hợp.

### 21.2. Nhìn origin để tìm lỗi

Một số property được Spring Boot theo dõi thông tin **origin**, ví dụ file và dòng cấu hình từ nơi giá trị được đọc.

Thông tin này có thể giúp trả lời:

- Giá trị đang đến từ `application-prod.yml` hay `application.yml`?
- Có file ngoài JAR ghi đè giá trị được đóng gói không?
- Một biến môi trường có đang được áp dụng không?
- Profile nào đang đóng góp nguồn cấu hình?
- Có test property hoặc command-line argument ghi đè không?

Không phải mọi PropertySource đều hỗ trợ origin với mức chi tiết giống nhau. Hãy dùng thông tin origin được công cụ báo cáo thật sự thay vì suy ra từ tên source.

## 22. Spring Boot externalized configuration và kiểm tra sai khác giữa môi trường

Một artifact JAR có thể chạy khác nhau ở local và production vì các nguồn cấu hình khác nhau.

Ví dụ local:

```yaml
# application.yml
app:
  payment:
    mode: sandbox
```

Production:

```bash
APP_PAYMENT_MODE=live java -jar demo.jar
```

Hoặc deployment container cung cấp biến môi trường `APP_PAYMENT_MODE=live`.

Dù JAR giống nhau, `Environment#getProperty("app.payment.mode")` có thể trả `sandbox` ở local và `live` ở production.

### 22.1. Quy trình debug một giá trị bất ngờ

1. **Xác định key canonical** đang được ứng dụng đọc, ví dụ `app.payment.mode`.
2. **Kiểm tra giá trị hiệu lực** qua Environment hoặc cơ chế diagnostics an toàn.
3. **Xác định active profiles**.
4. **Xem thứ tự PropertySources** và các nguồn có thể cung cấp key đó.
5. **Kiểm tra command-line arguments** khi khởi động process.
6. **Kiểm tra Java system properties** được truyền bằng `-D...`.
7. **Kiểm tra OS environment variables** và mapping tên.
8. **Kiểm tra file cấu hình bên ngoài và imports**.
9. **Kiểm tra property đã được inject/bind khi nào**.
10. **Xác định có kỳ vọng runtime refresh hay không**; nếu có, xem cơ chế refresh thực tế.

Đừng chỉ mở `application.yml` rồi kết luận giá trị runtime phải giống file. Property trong file có thể đã bị nguồn ưu tiên cao hơn ghi đè.

### 22.2. Tránh ghi đè bằng một default không có chủ đích

Ví dụ:

```java
configurableEnvironment.getPropertySources().addFirst(
        new MapPropertySource(
                "defaults",
                Map.of("app.payment.mode", "sandbox")
        )
);
```

Dù tên source là `defaults`, `addFirst` khiến nó có ưu tiên cao trong tập hiện tại. Như vậy nó có thể ghi đè `APP_PAYMENT_MODE=live` do production cung cấp, dẫn tới hành vi nguy hiểm.

Nếu thật sự muốn default, hãy dùng cơ chế default properties hoặc đặt source ở độ ưu tiên phù hợp. **Tên nguồn không quyết định precedence; vị trí của nó trong PropertySources mới quyết định.**

## 23. Nguồn dữ liệu cấu hình trong integration test

Test thường cần ghi đè cấu hình mà không ảnh hưởng production.

Có một số cách phổ biến:

```java
@SpringBootTest(properties = {
        "app.feature.enabled=true",
        "app.client.retries=1"
})
class FeatureIntegrationTest {
}
```

Hoặc:

```java
@TestPropertySource(properties = {
        "app.feature.enabled=true"
})
class FeatureIntegrationTest {
}
```

Với các giá trị động như cổng database test container, Spring Test hỗ trợ `@DynamicPropertySource`:

```java
@DynamicPropertySource
static void databaseProperties(
        DynamicPropertyRegistry registry
) {
    registry.add(
            "app.database.port",
            () -> testContainer.getMappedPort(5432)
    );
}
```

Đây là các cách bổ sung nguồn property phục vụ test. Chúng thường có precedence được thiết kế để ghi đè application config thông thường.

### 23.1. Test property khác runtime refresh

`@DynamicPropertySource` cung cấp một nguồn property cho quá trình chuẩn bị test context, không có nghĩa tất cả bean đã bind sẽ tự đổi khi dữ liệu bên ngoài thay đổi.

Tương tự, `@SpringBootTest(properties = ...)` chỉ có hiệu lực trong test context mà test framework tạo. Nó không sửa file `application.yml` của ứng dụng.

### 23.2. Test đúng giá trị hiệu lực

Một test đơn giản:

```java
@SpringBootTest(properties = "app.mode=test")
class EnvironmentTest {

    @Autowired
    private Environment environment;

    @Test
    void readsOverriddenMode() {
        assertThat(environment.getProperty("app.mode"))
                .isEqualTo("test");
    }
}
```

Ví dụ giả định project có JUnit, AssertJ và Spring Boot test dependencies. Test cho thấy một nguồn cấu hình của test có thể ghi đè giá trị từ file ứng dụng.

## 24. Những lỗi và hiểu lầm thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| `application.yml` ghi `false` nhưng ứng dụng đọc `true` | OS env, system property hoặc CLI ưu tiên cao hơn | Xem PropertySources và giá trị hiệu lực |
| Đổi file YAML sau startup nhưng không thấy thay đổi | Config Data không tự reload file | Restart hoặc dùng refresh mechanism được thiết kế riêng |
| `Environment#getProperty` thấy giá trị mới nhưng `@Value` vẫn cũ | Field/constructor đã inject một lần | Phân biệt live lookup và snapshot |
| `@ConfigurationProperties` không thay đổi sau runtime override | Object đã bind trước đó | Không kỳ vọng auto rebind |
| `@ConditionalOnProperty` không tạo bean sau khi property đổi | Condition được đánh giá khi đăng ký bean | Dùng runtime feature flag nếu cần bật/tắt động |
| Property không resolve khi đặt biến môi trường | Sai tên mapping hoặc biến không thuộc môi trường tiến trình | Kiểm tra relaxed binding và process environment |
| Dùng `@PropertySource` cho YAML nhưng không parse đúng | Annotation không tự dùng parser Config Data YAML | Dùng `application.yml` hoặc custom factory |
| Property điều khiển logging không có hiệu lực từ `@PropertySource` | Nguồn được thêm quá muộn trong refresh | Dùng nguồn bootstrap sớm hơn |
| Thêm `MapPropertySource` nhưng giá trị không thắng | Source ưu tiên thấp hoặc có nguồn cao hơn | Kiểm tra thứ tự `MutablePropertySources` |
| Dùng `addFirst` cho default và vô tình ghi đè production | Hiểu sai precedence | Đặt default ở nguồn ưu tiên thấp |
| App local và container có giá trị khác nhau | Profiles, environment variables, config files khác | So sánh nguồn cấu hình của từng process |
| Config secret bị lộ khi debug | In toàn bộ Environment hoặc expose actuator | Hạn chế log, áp dụng sanitization và access control |

### 24.1. Đừng nhầm missing property với binding error

Nếu một property không tồn tại, `getProperty` có thể trả `null` hoặc default được chỉ định.

Nếu property tồn tại nhưng có giá trị không hợp lệ, việc chuyển kiểu hoặc binding có thể thất bại.

Ví dụ:

```properties
app.client.retries=abc
```

khác với:

```properties
# app.client.retries không được khai báo
```

Trường hợp đầu cần sửa giá trị không đúng kiểu; trường hợp sau có thể dùng default phù hợp hoặc yêu cầu property bắt buộc.

### 24.2. Đừng nhầm “đổi property” với “đổi cấu hình của một object”

Một DataSource được tạo từ `spring.datasource.*` thường đã mở hoặc thiết lập pool theo cấu hình tại thời điểm khởi tạo.

Ngay cả khi `Environment` sau đó trả về một URL mới, DataSource hiện tại không tự đóng pool cũ và tạo pool mới theo URL đó.

Quy tắc tương tự áp dụng cho HTTP client, scheduler, bean conditions và hầu hết component được cấu hình khi tạo. Cần một cơ chế reconfiguration có chủ đích hoặc restart ứng dụng.

## 25. Quy trình thiết kế cấu hình dễ vận hành

Khi xây dựng hệ thống Spring Boot, bạn có thể áp dụng các nguyên tắc:

- Dùng `application.yml` hoặc `application.properties` cho cấu hình mặc định đọc được và có version control phù hợp.
- Dùng profile-specific Config Data để tách sự khác biệt theo môi trường khi thật sự cần.
- Dùng OS environment variables hoặc external config cho những giá trị thay đổi theo deployment.
- Không commit secrets vào repository; dùng secret management phù hợp.
- Dùng `@ConfigurationProperties` cho nhóm cấu hình có kiểu, có thể validation.
- Dùng `Environment` trực tiếp khi cần tra cứu key động hoặc viết infrastructure/diagnostics.
- Đặt tên property nhất quán theo canonical kebab-case.
- Ghi rõ default, missing-value behavior và điều kiện khởi động.
- Tránh thêm `PropertySource` có precedence quá cao nếu không có lý do rõ ràng.
- Không giả định file config thay đổi sẽ tự cập nhật bean.
- Nếu cần runtime config động, thiết kế cơ chế update, validation, synchronization và rollback riêng.
- Khi debug, xem giá trị hiệu lực và nguồn gốc, không chỉ một file cấu hình.

Một cấu hình tốt có thể trả lời ba câu hỏi: **giá trị đến từ đâu, tại thời điểm nào nó được đọc, và thay đổi nó có làm thay đổi object đang chạy hay không?**

## 26. Bài thực hành

### Bài 1 — Đọc Environment

Tạo ứng dụng có property `app.greeting.message` trong `application.yml`. Inject `Environment` vào `CommandLineRunner` và in giá trị. Thử không khai báo property, dùng default và thử `getRequiredProperty`.

### Bài 2 — Kiểm tra precedence

Cấu hình cùng key `app.mode` trong YAML, OS environment variable, Java system property và command-line argument. Dự đoán giá trị có hiệu lực, chạy ứng dụng rồi bỏ dần các nguồn ưu tiên cao để so sánh.

### Bài 3 — In tên PropertySources

Inject `ConfigurableEnvironment` vào runner và lặp qua `getPropertySources()`. In **tên** từng nguồn, không in toàn bộ giá trị. So sánh danh sách giữa chạy local và chạy trong container/test.

### Bài 4 — So sánh @Value với Environment

Tạo một bean nhận `app.greeting.message` bằng `@Value` và một bean đọc nó qua `Environment#getProperty` mỗi lần được gọi. Thêm `MapPropertySource` tại runtime, quan sát giá trị mới và giá trị snapshot.

### Bài 5 — @ConfigurationProperties

Tạo record `ClientProperties` với `endpoint`, `timeout` và `retries`. Bind từ YAML và inject vào một service. Thử cấu hình `retries=abc` để quan sát lỗi binding.

### Bài 6 — Profiles

Tạo `application.yml` và `application-prod.yml` với các giá trị `app.payment.endpoint` khác nhau. Chạy với và không có `--spring.profiles.active=prod` rồi in giá trị hiệu lực và active profiles.

### Bài 7 — Config import

Thêm `spring.config.import=optional:file:./config/extra.yml`. Chạy khi file tồn tại và khi file không tồn tại. Quan sát nguồn cấu hình import và cách xử lý vị trí optional.

### Bài 8 — @PropertySource

Tạo `legacy.properties` và một class `@Configuration` có `@PropertySource`. Đọc key từ Environment. So sánh thời điểm bổ sung nguồn với file `application.yml`.

### Bài 9 — Điều kiện cấu hình

Tạo `@ConditionalOnProperty` cho một bean tùy chọn. Chạy với property true/false, sau đó thử thêm runtime MapPropertySource để thấy condition không tự chạy lại sau context refresh.

### Bài 10 — Xem property origin an toàn

Nếu project có Spring Boot Actuator, cấu hình và bảo vệ endpoint thích hợp để xem các nguồn Environment. Chọn một property **không nhạy cảm**, tìm nguồn gốc/giá trị thực tế, rồi giải thích lý do nó thắng các nguồn còn lại.

## 27. Tài liệu tham khảo chính thức

- [Spring Boot Reference — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): PropertySources, thứ tự ưu tiên, Config Data, profiles, environment variables và config imports.
- [Spring Framework Reference — Environment Abstraction](https://docs.spring.io/spring-framework/reference/core/beans/environment.html): cách Spring quản lý properties và profiles.
- [Spring Framework Javadoc — Environment](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/env/Environment.html): API đọc property và profiles.
- [Spring Framework Javadoc — ConfigurableEnvironment](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/env/ConfigurableEnvironment.html): truy cập và chỉnh sửa các PropertySources.
- [Spring Framework Javadoc — PropertySource](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/env/PropertySource.html): abstraction biểu diễn nguồn property.
- [Spring Boot Reference — Type-safe Configuration Properties](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties): `@ConfigurationProperties` và binding.
- [Spring Boot Reference — Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html): kiểm tra Environment/configuration properties và các cân nhắc bảo mật.

Điểm cốt lõi là **`Environment` cung cấp kết quả tra cứu property qua các `PropertySource` có thứ tự ưu tiên**, còn giá trị thực tế của ứng dụng phụ thuộc vào nguồn đã được nạp, profiles, thời điểm truy vấn và vòng đời của bean sử dụng cấu hình đó. Một lần gọi `getProperty` có thể thấy một nguồn property vừa được cập nhật; nhưng `@Value`, `@ConfigurationProperties`, condition và những component đã khởi tạo không tự được xây dựng lại. Hiểu được ranh giới này giúp bạn cấu hình Spring Boot nhất quán, tránh lỗi khác biệt giữa các môi trường và chẩn đoán chính xác giá trị đang có hiệu lực.
