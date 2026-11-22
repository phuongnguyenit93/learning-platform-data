# Chẩn đoán một sự cố cấu hình từ bằng chứng nguồn gốc giá trị

> **Chủ đề:** Spring Boot Externalized Configuration  
> **Nhóm:** Thực hành tổng hợp

## 1. Tình huống mở đầu: “Trong YAML đã ghi 5 giây, sao ứng dụng vẫn timeout sau 800 ms?”

Một nhóm vận hành một Spring Boot service tên `payment-gateway`. Khi gọi một dịch vụ thanh toán bên ngoài, ứng dụng liên tục bị timeout. Người phụ trách mở `src/main/resources/application.yml` và thấy:

~~~yaml
payments:
  client:
    timeout: 5s
    base-url: "https://payments.example.test"
~~~

Họ kết luận timeout phải là 5 giây. Thế nhưng khi kiểm tra một bean cấu hình đang chạy, giá trị thực tế lại là `PT0.8S`, tương đương **800 mili giây**.

Trên một môi trường staging giả định, cấu hình còn có:

~~~yaml
# src/main/resources/application-staging.yml
payments:
  client:
    timeout: 3s
~~~

~~~yaml
# ./config/application-staging.yml (bên ngoài JAR)
payments:
  client:
    timeout: 2s
~~~

Biến môi trường của tiến trình:

~~~text
PAYMENTS_CLIENT_TIMEOUT=1500ms
~~~

Và tham số khởi động:

~~~bash
java -jar payment-gateway.jar \
  --spring.profiles.active=staging \
  --payments.client.timeout=800ms
~~~

Ở thứ tự property sources mặc định thường gặp của Spring Boot, command-line argument có ưu tiên cao hơn OS environment, và các nguồn này có thể ghi đè giá trị của Config Data. Vì vậy, **800 ms** là giá trị có hiệu lực trong ví dụ này.

Nhưng nhiệm vụ của kỹ sư không chỉ là đoán “CLI thắng”. Họ phải đưa ra **bằng chứng nguồn gốc giá trị**, chứng minh:

1. Tiến trình đang chạy đúng phiên bản artifact nào?
2. Những nguồn configuration nào được nạp thực sự?
3. Profile nào đang active, file nào nằm trong/ngoài JAR?
4. Key chính xác đang được tra cứu là gì?
5. Giá trị hiệu lực là bao nhiêu?
6. `PropertySource` nào cung cấp giá trị đang thắng?
7. Bean `@ConfigurationProperties` có bind từ giá trị đó không?
8. HTTP client đã tạo có thật sự dùng timeout mới không?
9. Tại sao người vận hành nhìn thấy giá trị 5s trong file mà runtime lại thấy 800ms?
10. Cần thay đổi ở đâu để sửa lỗi **đúng nguồn**, không tạo một override khác che lấp nguyên nhân?

Bài này là một **bài thực hành điều tra từ triệu chứng đến nguyên nhân gốc (root cause)** bằng bằng chứng có thể kiểm tra lại. Tất cả domain, endpoint và giá trị nêu trong bài đều là ví dụ minh họa.

### Mục tiêu học tập

Sau khi thực hành, bạn có thể:

- Xây dựng timeline từ startup đến lỗi runtime và phân biệt sự kiện đã quan sát với suy đoán.
- Thu thập thông tin về effective property, active profiles, property source và origin.
- Hiểu sự khác biệt giữa **tên nguồn (source name)**, **origin vị trí file/dòng**, **giá trị cuối trong Environment** và **giá trị client đang sử dụng**.
- Dùng `ConfigurableEnvironment`, Actuator `env`/`configprops` và các công cụ test phù hợp mà không để lộ secret.
- Phân tích thứ tự ưu tiên giữa CLI, Java system properties, OS environment, `SPRING_APPLICATION_JSON`, Config Data, `@PropertySource` và default properties.
- Kiểm tra profiles, documents, imports, relative paths, Config Tree và những nguồn bị nạp quá muộn.
- Phân biệt source không nạp, source bị override, Binder không bind và resource client giữ snapshot cũ.
- Đưa ra một bản incident report có giả thuyết, chứng cứ, root cause, khắc phục và bằng chứng xác nhận.
- Viết regression tests để sự cố không tái diễn.

## 2. Nguyên tắc điều tra: bằng chứng thay vì suy đoán

Khi xuất hiện lỗi cấu hình, không nên bắt đầu bằng câu hỏi “File nào cần sửa?”. Hãy bắt đầu bằng câu hỏi:

> **Ứng dụng đang chạy thực sự dùng giá trị nào, giá trị ấy đến từ nguồn nào và được áp dụng vào component ở thời điểm nào?**

Một quy trình tin cậy phải chia rõ ba lớp:

~~~text
LỚP 1 — Nguồn dữ liệu trên hệ thống
    file YAML / properties / env / JVM args / CLI
    Secret / ConfigMap / imported file / defaults
                     |
                     v
LỚP 2 — Spring Environment và Binder
    ordered PropertySources
    effective property resolution
    relaxed binding và type conversion
    @ConfigurationProperties / @Value
                     |
                     v
LỚP 3 — Resource và hành vi thực tế
    HTTP client, connection pool, scheduler
    request timeout, reconnect, retry
    metrics, traces, business results
~~~

Một file có thể chứa giá trị đúng nhưng **không được nạp**. Một file được nạp có thể **bị nguồn cao hơn override**. Một bean đã bind đúng có thể được cấp cho client không đúng. Một client được tạo đúng lúc startup vẫn có thể **giữ cấu hình cũ sau khi nguồn bên ngoài bị sửa**.

Kết luận nguyên nhân gốc phải xác định rõ sự cố nằm ở lớp nào.

### 2.1. Quan sát khác kết luận

Ví dụ:

| Loại phát biểu | Ví dụ | Mức bằng chứng |
| --- | --- | --- |
| Quan sát | File source `application.yml` hiện ghi `5s` | Chỉ chứng minh nội dung file đang được mở |
| Quan sát | `Environment.getProperty(...)` trả `800ms` | Chứng minh effective lookup lúc đo |
| Quan sát | `@ConfigurationProperties.timeout()` trả `PT0.8S` | Chứng minh bean đã bind 800ms |
| Quan sát | HTTP request tới mock server thất bại sau khoảng 800ms | Bằng chứng hành vi, còn phải loại trừ network/other timeouts |
| Giả thuyết | CLI override file cấu hình | Cần xác nhận đúng process args và property sources |
| Kết luận | Tham số `--payments.client.timeout=800ms` thắng và client bind từ nó | Chỉ nói khi có chuỗi chứng cứ phù hợp |

Một hệ thống có thể có nhiều timeout khác nhau: DNS, TCP connect, TLS handshake, read, total request, retry deadline hoặc timeout của load balancer. “Sau 800ms” không tự chứng minh đó là đúng property `payments.client.timeout`; vẫn cần xác nhận component nào dùng nó.

### 2.2. Không dùng dữ liệu nhạy cảm để debug

Chỉ nên quan sát key không nhạy cảm như timeout, port demo hoặc feature flag. Nếu key liên quan tới mật khẩu, API token, JWT private key hay connection URL chứa credentials:

- Không log raw values.
- Không in toàn bộ `Environment`.
- Không gửi screenshot chứa secret vào ticket.
- Không mở Actuator env/configprops công khai.
- Có thể ghi nhận **tên property**, **nguồn**, **có/không có giá trị** và version identifier không nhạy cảm theo chính sách.

Bài thực hành chỉ sử dụng giá trị timeout và hostname giả.

## 3. Chuẩn bị một ứng dụng mẫu để tái hiện

Ví dụ sử dụng Java 17+ và Spring Boot 3.x/4.x phù hợp với toolchain của dự án. Bài học nhấn mạnh đường đi của cấu hình; chi tiết API HTTP client có thể khác theo phiên bản.

### 3.1. Định nghĩa typed configuration

~~~java
package com.example.payments.config;

import java.net.URI;
import java.time.Duration;

import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@ConfigurationProperties(prefix = "payments.client")
@Validated
public record PaymentClientProperties(
        @NotNull URI baseUrl,
        @NotNull Duration timeout
) {
    public PaymentClientProperties {
        if (timeout == null || timeout.isZero()
                || timeout.isNegative()) {
            throw new IllegalArgumentException(
                    "payments.client.timeout must be positive");
        }
    }
}
~~~

Các property canonical là:

~~~text
payments.client.base-url
payments.client.timeout
~~~

Với `@ConfigurationProperties`, Spring Boot Binder hỗ trợ relaxed binding khi phù hợp, nên một biến môi trường như `PAYMENTS_CLIENT_TIMEOUT` có thể tương ứng với property `payments.client.timeout`.

Đừng nhầm dấu gạch ngang trong tên key với cơ chế thay đổi ngẫu nhiên tên biến môi trường. Quy tắc canonical được Boot định nghĩa; với nested maps/list indices cần phân tích riêng.

### 3.2. Đăng ký @ConfigurationProperties

~~~java
package com.example.payments;

import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;
import org.springframework.boot.SpringApplication;

@SpringBootApplication
@ConfigurationPropertiesScan
public class PaymentGatewayApplication {

    public static void main(String[] args) {
        SpringApplication.run(PaymentGatewayApplication.class, args);
    }
}
~~~

Cấu hình cần được đăng ký thành bean để injection có hiệu lực. Có thể thay `@ConfigurationPropertiesScan` bằng `@EnableConfigurationProperties(PaymentClientProperties.class)` trong một cấu hình thích hợp.

### 3.3. Tạo một component tiêu thụ value

~~~java
package com.example.payments.client;

import com.example.payments.config.PaymentClientProperties;
import java.net.http.HttpClient;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class PaymentHttpClientConfiguration {

    @Bean
    HttpClient paymentHttpClient(PaymentClientProperties properties) {
        return HttpClient.newBuilder()
                .connectTimeout(properties.timeout())
                .build();
    }
}
~~~

Ở ví dụ này, timeout của `HttpClient.newBuilder().connectTimeout(...)` là **connect timeout**. Nếu bài toán production là **toàn bộ thời gian chờ response**, phải cấu hình request timeout ở `HttpRequest` hoặc client tương ứng. Không được coi một property tùy chỉnh tên `payments.client.timeout` tự động quyết định mọi timeout của HTTP.

Đây là một ví dụ minh họa quan trọng: **tên property có thể đúng, binding đúng, nhưng hành vi sai vì developer gán nó cho sai loại timeout**.

### 3.4. Các file cấu hình của case study

File trong JAR:

~~~yaml
# src/main/resources/application.yml
payments:
  client:
    base-url: "https://payments.example.test"
    timeout: 5s
~~~

Profile file trong JAR:

~~~yaml
# src/main/resources/application-staging.yml
payments:
  client:
    timeout: 3s
~~~

External file ở working directory:

~~~yaml
# ./config/application-staging.yml
payments:
  client:
    timeout: 2s
~~~

Environment:

~~~text
PAYMENTS_CLIENT_TIMEOUT=1500ms
~~~

CLI:

~~~bash
java -jar payment-gateway.jar \
  --spring.profiles.active=staging \
  --payments.client.timeout=800ms
~~~

Ở những cấu hình tìm file mặc định tương ứng, external config nằm dưới `./config/` sẽ được Boot xét khi chạy từ đúng working directory. Khi đồng thời có CLI và env, giá trị hiệu lực của `payments.client.timeout` là `800ms` trong case study.

## 4. Dựng timeline của sự cố

Một timeline rõ ràng giúp tách việc đã xảy ra khỏi phỏng đoán.

| Thời điểm | Sự kiện | Cần thu thập |
| --- | --- | --- |
| 09:00 | Bản phát hành mới được triển khai | Image digest/JAR version, commit ID |
| 09:02 | Process bắt đầu chạy | Process start time, args đã được redacted, active profiles |
| 09:03 | Spring Boot báo started | Startup logs, condition report khi cần |
| 09:10 | Requests tới Payment API timeout | Request metrics, exception type, tracing |
| 09:20 | Operator mở `application.yml` thấy `5s` | Đường dẫn tuyệt đối của file đang đọc |
| 09:25 | Quan sát bean config thấy `800ms` | Giá trị typed bean/Environment, thời điểm quan sát |
| 09:30 | Phát hiện CLI có `800ms` | Source precedence và command thực tế |
| 09:40 | Sửa startup config, rollout | Change ID, artifact/config revision |
| 09:50 | Kiểm tra lại chức năng | Typed bean, effective property, HTTP behavior |

Lưu ý: thời gian chỉ là ví dụ. Khi debug thật cần giữ timestamp/timezone nhất quán và tránh nhầm process cũ với Pod mới.

### 4.1. Đảm bảo đang kiểm tra đúng instance

Kubernetes service có thể có nhiều replicas:

~~~text
payment-gateway-abc: timeout=800ms
payment-gateway-def: timeout=800ms
payment-gateway-ghi: timeout=2s
~~~

Nếu chỉ xem log của một Pod hoặc gọi endpoint qua load balancer, kết luận có thể sai khi nhiều bản config đồng tồn tại. Hãy xác định **instance identity**, version của image, container start time và bản cấu hình của từng replica.

Một kết quả từ một Pod chỉ chứng minh trạng thái của Pod đó, không chứng minh toàn deployment đã đồng nhất.

## 5. Thứ tự ưu tiên: lý do “có trong file” chưa chắc là giá trị thắng

Spring Boot có danh sách thứ tự `PropertySource` theo mức ưu tiên. Bảng sau chỉ liệt kê một số nhóm thường gặp trong một ứng dụng, theo định hướng **từ mức thấp lên mức cao**:

| Nhóm nguồn | Mô tả |
| --- | --- |
| Default properties | Giá trị mặc định cấp trực tiếp cho `SpringApplication` |
| `@PropertySource` | Thêm vào khi xử lý configuration class; thời điểm tương đối muộn |
| Config Data | `application.yml`, `application.properties`, profile files, imports, external files |
| `RandomValuePropertySource` | Ví dụ `random.uuid` |
| OS environment | Ví dụ `PAYMENTS_CLIENT_TIMEOUT` |
| Java system properties | Ví dụ `-Dpayments.client.timeout=...` |
| `SPRING_APPLICATION_JSON` | JSON được truyền qua env, system property hoặc CLI theo cách Boot hỗ trợ |
| Command-line arguments | Ví dụ `--payments.client.timeout=...` |
| Các test-specific sources | Có thể được thêm với ưu tiên riêng trong test runtime |

Trong web/container hoặc tests còn có các nguồn khác như JNDI, ServletContext init parameters, test properties, DynamicPropertySource và DevTools settings. Không dùng bảng rút gọn để thay thế danh sách precedence chính thức cho mọi môi trường.

Đối với ví dụ:

~~~text
application.yml                   : 5s
application-staging.yml trong JAR : 3s
./config/application-staging.yml  : 2s
PAYMENTS_CLIENT_TIMEOUT           : 1500ms
--payments.client.timeout         : 800ms
----------------------------------------
Effective value                   : 800ms
~~~

Đây là **kết quả phân tích giả định có đủ cả năm nguồn**, không phải xác nhận đã đọc chúng trên một hệ thống thật.

### 5.1. Đừng kết luận bằng thời gian chỉnh sửa file

File được sửa sau cùng không nhất thiết có precedence cao hơn. Thứ tự trong Spring Boot được quyết định bởi loại nguồn, location, profile, import và những customizations; timestamp trên filesystem không phải luật override.

### 5.2. Trùng một key với hai giá trị

Khi nhiều nguồn cung cấp **cùng property name**, nguồn ưu tiên cao thắng trong lookup thông thường. Tuy nhiên, với collection/list binding, môi trường có thể áp dụng quy tắc thay thế cả list thay vì merge từng item. Với Map có thể có behavior hợp nhất keys theo Binder.

Không áp dụng quy tắc “merge tất cả” cho mọi kiểu cấu hình; khi sự cố liên quan list/map, phải kiểm tra **typed binding** chứ không chỉ một scalar key.

### 5.3. Runtime có thể thêm nguồn tùy chỉnh

Một `EnvironmentPostProcessor` hoặc initializer có thể thêm `MapPropertySource` ở đầu danh sách. Một ứng dụng sử dụng Spring Cloud Config hoặc secret integration cũng có thể có thêm nguồn với thứ tự riêng.

Vì vậy, **bảng precedence trong tài liệu là điểm xuất phát**; bằng chứng mạnh nhất là `PropertySources` của đúng ứng dụng đang chạy.

## 6. Năm câu hỏi trước khi mở code

Trước khi thêm logs hoặc debugger, thu thập:

1. **Runtime identity:** chính xác image digest, JAR version, commit, Pod name hoặc VM?
2. **Process launch:** command-line arguments, JVM options, environment names, working directory?
3. **Profiles:** `spring.profiles.active` hoặc profiles được đưa vào qua cơ chế được hỗ trợ?
4. **Config locations:** Boot đang tìm ở những thư mục/file nào, có `spring.config.location`, `additional-location` hoặc `import` không?
5. **Target property:** tên canonical và bean/client nào nhận nó?

Nếu chưa biết năm điều này, có nguy cơ đọc đúng một file nhưng trên **sai môi trường hoặc sai tiến trình**.

### 6.1. Phân biệt tên file và tên nguồn

Một đường dẫn như:

~~~text
./config/application-staging.yml
~~~

là một **candidate config file**. Để nói nó đã có hiệu lực, cần chứng minh Boot thực sự nạp nó, profile phù hợp và không có nguồn cao hơn ghi đè key được quan tâm.

### 6.2. Đừng thu thập command-line nguyên văn nếu chứa secret

Các tham số JVM/CLI có thể chứa password hoặc token. Trong incident report, ghi:

~~~text
--payments.client.timeout=800ms
--partner.api.token=<REDACTED>
~~~

Nhưng không phát tán raw arguments/logs từ production khi chưa được kiểm soát. Nếu thông tin rất nhạy cảm, chỉ ghi key name và có hay không theo chính sách.

## 7. Cách xem effective value từ Spring Environment

Đối với key không nhạy cảm, có thể dùng một `ApplicationRunner`:

~~~java
package com.example.payments.diagnostics;

import com.example.payments.config.PaymentClientProperties;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.stereotype.Component;

@Component
class PaymentConfigProbe implements ApplicationRunner {

    private final ConfigurableEnvironment environment;
    private final PaymentClientProperties properties;

    PaymentConfigProbe(
            ConfigurableEnvironment environment,
            PaymentClientProperties properties) {
        this.environment = environment;
        this.properties = properties;
    }

    @Override
    public void run(ApplicationArguments args) {
        String key = "payments.client.timeout";

        System.out.println(
                "Effective Environment value: "
                        + environment.getProperty(key)
        );
        System.out.println(
                "Bound Duration: " + properties.timeout()
        );
        System.out.println(
                "Active profiles: "
                        + String.join(",", environment.getActiveProfiles())
        );
    }
}
~~~

Với case study, output có thể như:

~~~text
Effective Environment value: 800ms
Bound Duration: PT0.8S
Active profiles: staging
~~~

Lưu ý:

- `environment.getProperty` trả một chuỗi theo property source resolution tại thời điểm được gọi.
- `properties.timeout()` là một `Duration` đã được bind, nên Java hiển thị chuẩn ISO-8601 `PT0.8S`.
- Giá trị raw `800ms` và typed `PT0.8S` **không phải hai timeout khác nhau**.
- Nếu probe chạy sau khi Environment bị thay đổi bởi cơ chế tùy chỉnh, effective value tại lúc probe có thể khác snapshot lúc bean được bind.

### 7.1. Vì sao không chỉ dùng @Value?

Có thể đọc:

~~~java
@Value("${payments.client.timeout:5s}")
private Duration timeout;
~~~

Nhưng dùng `@Value` chỉ cho biết field được inject trong một bean; nó không chỉ ra nguồn nào thắng. Đối với cấu hình có cấu trúc, `@ConfigurationProperties` thường dễ kiểm soát và validate hơn.

### 7.2. Không để probe production vô tình tiết lộ dữ liệu

Đừng mở một endpoint public trả về mọi `Environment` key/value. Trong môi trường production, probe chỉ nên được kích hoạt có kiểm soát, giới hạn key allowlist không nhạy cảm, tránh token/password và không lộ cấu trúc hệ thống ngoài mức cần thiết.

Có thể loại bỏ probe sau incident nếu nó chỉ là công cụ debug tạm.

## 8. Xem thứ tự PropertySources trong đúng tiến trình

`ConfigurableEnvironment` cho phép truy cập danh sách `PropertySource` có thứ tự. Với key không nhạy cảm:

~~~java
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.PropertySource;

public class PropertySourceInspector {

    public static void inspect(
            ConfigurableEnvironment environment,
            String key) {

        System.out.println("Effective: "
                + environment.getProperty(key));

        for (PropertySource<?> source :
                environment.getPropertySources()) {

            Object raw = source.getProperty(key);
            if (raw != null) {
                System.out.println(
                        source.getName()
                                + " -> " + raw
                );
            }
        }
    }
}
~~~

Ở đây, vòng lặp lần theo thứ tự hiện tại của `MutablePropertySources`. Một source ở phía trên có thể thắng một source bên dưới cho cùng tên key.

### 8.1. Tên source không nhất thiết là origin file/dòng

Một `PropertySource` có tên đại diện một config data resource, command-line args hoặc environment. Tuy nhiên, `source.getName()` **không luôn chứa** đường dẫn file và số dòng cụ thể của value. Nó là định danh của nguồn, khác với **origin tracking**.

Các loader của Spring Boot có thể gắn origin metadata, nhưng không phải mọi source đều hỗ trợ. Với OS env hoặc custom source, có thể chỉ biết nguồn hoặc key, không biết nơi một người đã tạo biến ở cấp deployment manifest.

### 8.2. Hạn chế của getProperty với tên raw

`source.getProperty("payments.client.timeout")` có thể không đủ để khám phá mọi biến môi trường theo relaxed binding trong mọi tình huống. Boot Binder và các lớp adaptation có thể xử lý tên canonical/alias theo cách khác với một lookup raw trên một source.

Vì vậy, nếu vòng lặp không in một environment variable nhưng Binder vẫn nhận value, đừng vội kết luận source không tồn tại. Hãy kiểm tra cách source giữ key (`PAYMENTS_CLIENT_TIMEOUT`) và nguyên tắc relaxed binding.

### 8.3. Chỉ in key đã được cho phép

Snippet trên minh họa với timeout không nhạy cảm. Không dùng nó để duyệt toàn bộ sources và in mọi property. Một nguồn có thể chứa secret, URL có credentials, private key hoặc dữ liệu tenant-specific.

## 9. Origin là gì và vì sao nó mạnh hơn việc nhìn thấy key?

Trong Spring Boot, origin metadata có thể gắn một giá trị cấu hình với thông tin nơi nó được nạp, ví dụ:

~~~text
class path resource [application-staging.yml]
  - line 4, column 14
~~~

hoặc:

~~~text
file [./config/application-staging.yml]
  - line 3, column 14
~~~

Các chuỗi trên chỉ minh họa hình thức. Location cụ thể tùy loader, file và phiên bản. Origin không tồn tại đối với mọi PropertySource.

### 9.1. Source name vs origin location

| Thông tin | Câu hỏi trả lời |
| --- | --- |
| Tên PropertySource | “Nguồn có tên gì trong Environment?” |
| Raw property key | “Key nào tồn tại trong source?” |
| Effective property value | “Lookup hiện tại trả giá trị nào?” |
| Origin metadata | “Loader biết value đến từ file/dòng/cột hoặc resource nào?” |
| Bean bound value | “Java object sau conversion có giá trị gì?” |
| Behavior của client | “Component thực tế dùng giá trị đó như thế nào?” |

Không có một dòng log nào luôn trả lời đủ sáu câu hỏi. Kỹ sư phải ghép bằng chứng theo đường đi của cấu hình.

### 9.2. Origin theo nguồn được nạp, không phải lịch sử chỉnh sửa

Nếu origin trỏ tới `application-staging.yml:4`, nó cho biết loader tạo value từ vị trí đó trong lần nạp. Nó **không** cho biết Git commit nào tạo ra dòng ấy, ai sửa nó, hoặc có một override khác đang thắng hay không.

Muốn biết lịch sử thay đổi, cần deployment revision, Git history hoặc audit logs của hệ thống quản lý cấu hình.

### 9.3. Origin không nhất thiết trả chính xác một line

Đối với environment variable, Java system property, dynamic property source hoặc custom PropertySource, origin có thể thiếu line/column hoặc được trình bày khác. **Thiếu origin cụ thể không bằng thiếu value.**

Với những trường hợp origin metadata không sẵn có, ghi nhận giới hạn bằng chứng thay vì tự bịa đường dẫn file.

## 10. Actuator env và configprops: nhìn từ ứng dụng đang chạy

Nếu dự án có `spring-boot-starter-actuator` và cấu hình bảo mật phù hợp, hai endpoint thường hữu ích là:

- `/actuator/env` hoặc `/actuator/env/{property.name}`: thông tin về Environment/property sources.
- `/actuator/configprops`: thông tin về các bean `@ConfigurationProperties` và giá trị đã bind, tùy phiên bản và các cài đặt hiển thị.

### 10.1. Dùng endpoint env cho một key cụ thể

Với key không nhạy cảm:

~~~text
GET /actuator/env/payments.client.timeout
~~~

Kết quả JSON thực tế tùy Spring Boot version, endpoint configuration và sanitation. Thông tin thường có các property sources đã góp value, metadata về source và có thể origin nếu có.

**Không được suy ra response luôn chứa raw value.** Spring Boot Actuator có chính sách che giấu giá trị theo cài đặt `management.endpoint.env.show-values` và cơ chế authorization/sanitization tương ứng. Mặc định có thể che giấu giá trị.

### 10.2. Không bật show-values=ALWAYS trong production chỉ để debug

Các tùy chọn hiển thị value của Actuator có thể được điều chỉnh trong môi trường được kiểm soát. Nhưng bật tất cả giá trị trên endpoint công khai có thể làm lộ secrets.

Nếu chỉ cần tìm nguồn, thường đã đủ khi quan sát tên key, source name, origin metadata và typed value được kiểm tra an toàn. Không biến sự cố timeout thành sự cố lộ credential.

### 10.3. Endpoint configprops trả lời câu hỏi khác

`env` tập trung vào property sources và Environment. `configprops` tập trung vào những bean được đăng ký bằng `@ConfigurationProperties` và kết quả binding.

Nếu effective Environment timeout là 10s nhưng bean đang dùng 3s, có thể bean được bind trước một thay đổi runtime hoặc đang có hai bean/config objects khác nhau. Đây là dấu hiệu cần điều tra lifecycle, không chỉ file precedence.

### 10.4. Actuator phải được bảo vệ

Chỉ expose những endpoint cần thiết, qua authentication/authorization và network controls thích hợp. Không dùng `management.endpoints.web.exposure.include=*` một cách tùy tiện trên môi trường production. Giá trị có thể bị sanitize hoặc bị giới hạn để bảo vệ thông tin; không nên tắt biện pháp đó chỉ vì muốn nhanh chóng thấy secrets.

## 11. Đọc bằng chứng từ case study

Sau khi chạy ứng dụng giả định với năm nguồn, một báo cáo an toàn có thể ghi:

| Ưu tiên tương đối | Nguồn | Property | Value |
| --- | --- | --- | --- |
| Cao nhất trong case | Command-line arguments | `payments.client.timeout` | `800ms` |
| Dưới CLI | OS environment | `PAYMENTS_CLIENT_TIMEOUT` | `1500ms` |
| Dưới env | External `application-staging.yml` | `payments.client.timeout` | `2s` |
| Dưới external | Packaged `application-staging.yml` | `payments.client.timeout` | `3s` |
| Dưới packaged profile | Packaged `application.yml` | `payments.client.timeout` | `5s` |

Bằng chứng cần đủ để giải thích **vì sao 800ms thắng**. Đây là mô hình điều tra khi hệ thống chạy với thứ tự mặc định và không có nguồn tùy chỉnh cao hơn.

Root cause của ví dụ:

> Script khởi động staging vẫn truyền `--payments.client.timeout=800ms` từ lần thử nghiệm latency trước. Tham số CLI có precedence cao hơn giá trị trong các file YAML và biến môi trường. Vì vậy, mặc dù file application mặc định đã ghi `5s`, bean `PaymentClientProperties` nhận `Duration=800ms` và HTTP client lấy timeout từ bean đó lúc khởi tạo.

### 11.1. Một kết luận tốt nêu cả bằng chứng và phạm vi

Không chỉ viết “do config bị override”. Cần nêu:

- Key bị ảnh hưởng.
- Nguồn thắng và vị trí/định danh có thể xác minh.
- Giá trị thắng.
- Những nguồn thấp hơn bị ghi đè.
- Bean/client nào bị ảnh hưởng.
- Từ khi nào lỗi xuất hiện và những instances nào cùng bị ảnh hưởng.
- Thay đổi gì đã gây ra sự cố.

### 11.2. Khi nào kết luận vẫn chưa đủ?

Nếu `PaymentClientProperties.timeout()` cho ra 800ms nhưng HTTP client không dùng property đó, lỗi 800ms ở network có thể có nguyên nhân khác. Cần đối chiếu bean creation code và tests về timeout behavior.

Không được lấy một giá trị cấu hình hợp lý làm bằng chứng duy nhất cho nguyên nhân của một latency spike.

## 12. Root cause và biện pháp sửa đúng nơi

Trong ví dụ, nguồn thắng là CLI:

~~~bash
java -jar payment-gateway.jar \
  --spring.profiles.active=staging \
  --payments.client.timeout=800ms
~~~

Nếu mục tiêu deployment là dùng timeout từ external configuration, có thể bỏ override:

~~~bash
java -jar payment-gateway.jar \
  --spring.profiles.active=staging
~~~

Khi đó, nếu vẫn có `PAYMENTS_CLIENT_TIMEOUT=1500ms` trong environment, giá trị hiệu lực có thể chuyển thành **1500ms**, chứ chưa chắc thành `2s` hay `5s`. Vì vậy, việc xóa một nguồn cao hơn chỉ “lộ ra” nguồn tiếp theo.

Muốn cuối cùng dùng `5s`, phải thống nhất **một nguồn canonical** và loại bỏ/đổi các overrides khác theo policy triển khai.

### 12.1. Không sửa bằng cách thêm override thứ sáu

Một phản ứng thiếu bền vững là thêm:

~~~bash
java -jar payment-gateway.jar \
  --payments.client.timeout=5s
~~~

vào một pipeline mới nhưng giữ nguyên các nguồn cũ ở nơi khác. Điều đó có thể sửa triệu chứng hôm nay nhưng khiến cấu hình ngày càng khó bảo trì và không rõ owner.

Biện pháp tốt hơn: xác định nơi team muốn quản trị timeout, xóa overrides tạm, document precedence và thêm test/guardrail để tránh lập lại.

### 12.2. Không sửa toàn bộ YAML khi chỉ một key có vấn đề

Nếu file có database credentials, HTTP endpoints và các toggle không liên quan, đừng thay toàn bộ để “reset config”. Chỉ sửa phần đã có bằng chứng là nguyên nhân; giữ change diff nhỏ giúp rollback và review an toàn.

### 12.3. Cần rollout/restart để giá trị mới có hiệu lực

Nếu tiến trình Spring Boot đã đọc cấu hình và tạo singleton client, sửa startup script hoặc YAML chưa làm client đang chạy tự đổi. Phải restart hoặc rollout theo cơ chế của hạ tầng, hoặc sử dụng một refresh mechanism được thiết kế và kiểm chứng.

## 13. Kiểm tra đúng file thực tế, không chỉ file trong repository

Khi developer mở:

~~~text
src/main/resources/application.yml
~~~

đó là source resource. Khi chạy executable JAR, Boot có thể đọc resource đã đóng gói tại build time. Một lần sửa file source sau build không làm JAR cũ thay đổi.

Đồng thời Boot có thể đọc external file:

~~~text
./config/application.yml
./config/application-staging.yml
~~~

được giải quyết từ **working directory**.

### 13.1. Working directory là yếu tố quyết định

Một shell chạy từ `/opt/payments`:

~~~bash
cd /opt/payments
java -jar payment-gateway.jar
~~~

sẽ có `./config/` khác với một service được systemd đặt working directory `/srv/payment-gateway` hoặc Docker container có `WORKDIR /app`.

Đừng hỏi “file application.yml nằm ở đâu trong máy” mà không hỏi “**process này đang đọc đường dẫn nào**?”.

### 13.2. External config locations mặc định

Spring Boot thường xét các vị trí như:

~~~text
classpath:/
classpath:/config/
file:./
file:./config/
file:./config/*/
~~~

Tính năng location groups và profile-specific files làm thứ tự nạp có thêm chi tiết. Khi có `spring.config.location`, danh sách mặc định có thể bị thay thế. Với `spring.config.additional-location`, các location được thêm vào thay vì thay toàn bộ default list.

### 13.3. Sửa nhầm JAR hoặc image revision

Trong container/GitOps, deployment có thể đang chạy image digest khác với Git revision developer đang xem. Cần xác nhận image thực tế trong Pod, không chỉ branch name ở máy local.

Nếu một ConfigMap mount đã thay nhưng process chưa restart, filesystem và Environment cũng có thể phản ánh hai version khác nhau.

## 14. Khi profile-specific source thắng

Giả sử không có CLI/env override, nhưng:

~~~yaml
# application.yml
reports:
  export:
    enabled: false

---
spring:
  config:
    activate:
      on-profile: staging

reports:
  export:
    enabled: true
~~~

Khi profile `staging` active và không có nguồn cao hơn, effective value của `reports.export.enabled` có thể là `true` dù document mặc định ghi `false`.

### 14.1. Đọc active profiles thật

Trong Spring:

~~~java
String[] active = environment.getActiveProfiles();
~~~

Đừng chỉ suy ra từ tên file đã có trong repository. Profile có thể được cấp qua command line, environment, Java system properties hoặc test setup. Một instance staging có thể đang active cả nhiều profiles nếu deployment cấu hình như vậy.

### 14.2. Multi-document ordering

Trong YAML, `---` tách các documents. Có thể đặt:

~~~yaml
spring:
  config:
    activate:
      on-profile: prod
~~~

trong một document, và chỉ khi điều kiện profile khớp thì document mới đóng góp properties. Với một file nhiều documents, những documents active xuất hiện sau có thể override những key trước theo quy tắc Config Data.

Nhưng thứ tự document chỉ là một phần. Một CLI option hoặc environment variable vẫn có thể thắng file.

### 14.3. Không đặt active profile muộn để mong nạp lại config

Một property `spring.profiles.active` được thêm bằng nguồn xử lý muộn như `@PropertySource` không thể được kỳ vọng khiến Boot quay lại giai đoạn nạp Config Data và kích hoạt mọi profile-specific file đã bỏ qua.

Đây là bài học về **thời điểm nạp** ngoài bài học về precedence.

## 15. Khi spring.config.location thay đổi hẳn nơi tìm cấu hình

Giả sử vận hành chạy:

~~~bash
java -jar payment-gateway.jar \
  --spring.config.location=optional:file:/etc/payments/
~~~

`spring.config.location` có thể **thay thế** các default search locations. Khi đó, một file `./config/application-staging.yml` mà developer vừa sửa có thể không được Boot tìm thấy theo dự định.

Một cách khác:

~~~bash
java -jar payment-gateway.jar \
  --spring.config.additional-location=optional:file:/etc/payments/
~~~

thường giữ các default locations và thêm vị trí khác. Nhưng vẫn phải hiểu thứ tự location groups và profile-specific documents; không phải cứ thêm nguồn là mọi key trong nó chắc chắn thắng CLI/env.

### 15.1. optional không phải bằng chứng nạp thành công

`optional:` cho phép bỏ qua location không tồn tại trong những tình huống được Boot hỗ trợ. Nó không chứng minh file đã có mặt hoặc đã được nạp.

Khi một setting quan trọng đến từ optional import/location, nên có validation để fail fast nếu giá trị bắt buộc cuối cùng bị thiếu.

### 15.2. Một location thiếu có thể làm default thắng

Nếu external config bị bỏ qua do file không tồn tại, application có thể trở về giá trị trong JAR. Lúc đó người vận hành thấy file ngoài host nhưng JVM không đọc đúng path, nhất là trong Docker mount.

Cần kiểm tra **path bên trong process/container**, không chỉ filesystem của host.

## 16. Khi spring.config.import góp thêm một nguồn

Ví dụ:

~~~yaml
# application.yml
spring:
  config:
    import: "optional:file:./overrides/payment.yml"

payments:
  client:
    timeout: 5s
~~~

File import:

~~~yaml
# ./overrides/payment.yml
payments:
  client:
    timeout: 2s
~~~

Trong cơ chế Spring Boot Config Data, file import được xử lý như Config Data và có quy tắc ưu tiên so với document khai báo import. Do đó imported file có thể override key của tài liệu gốc.

### 16.1. Điều cần chứng minh

- Tài liệu chứa `spring.config.import` thực sự được Boot nạp.
- Import location được giải quyết từ đúng context/path.
- File import tồn tại, hoặc được đánh dấu optional hợp lệ.
- Document/profile trong import active.
- Không có nguồn ưu tiên cao hơn như CLI/env.
- Typed bean cuối cùng nhận giá trị mong đợi.

### 16.2. Không dùng một phép grep cho cả import graph

File import có thể tiếp tục import file khác, hoặc location groups có semantics riêng. Nếu cấu hình có import phức tạp, cần lập bản đồ dependencies giữa các sources và xác định file nào thực sự đóng góp property.

Không tự viết cơ chế parse `spring.config.import` bằng regular expression đơn giản rồi khẳng định đã mô phỏng chính xác loader Boot.

## 17. Environment variables và relaxed binding: một nguồn dễ bỏ sót

Spring Boot hỗ trợ chuyển tên environment variable sang canonical property names theo quy tắc relaxed binding. Ví dụ:

~~~text
Property canonical : payments.client.timeout
OS environment     : PAYMENTS_CLIENT_TIMEOUT
~~~

Tuy nhiên, đối với nhiều keys, quy tắc đổi tên phải được áp dụng chính xác. Dấu gạch ngang trong tên canonical, nested maps và list indices có các trường hợp đặc biệt.

### 17.1. Một biến môi trường từ CI có thể override YAML

Nếu CI hoặc container platform đã cấp:

~~~text
PAYMENTS_CLIENT_TIMEOUT=1500ms
~~~

thì thay YAML thành `5s` vẫn có thể không thay đổi giá trị mà Binder nhận.

Kiểm tra deployment template, CI variables và environment configuration của **process đang chạy**. Không chỉ nhìn môi trường shell local nếu process được khởi tạo bởi systemd, Docker hoặc Kubernetes.

### 17.2. System.getenv không phải Environment.getProperty

~~~java
System.getenv("PAYMENTS_CLIENT_TIMEOUT");
~~~

đọc OS process environment. Còn:

~~~java
environment.getProperty("payments.client.timeout");
~~~

đọc theo Spring property source order. Nếu CLI thắng, hai giá trị có thể khác nhau mà không có lỗi.

### 17.3. Nguồn giá trị và thời điểm bind

Nếu Java code trực tiếp gọi `System.getenv` ở một nơi, còn phần khác dùng `@ConfigurationProperties`, chúng có thể dùng hai giá trị khác nhau. Nên thống nhất cách cấp cấu hình qua Spring Environment và typed configuration.

## 18. Java system properties và CLI cũng cần được kiểm kê

JVM property:

~~~bash
java -Dpayments.client.timeout=1200ms \
  -jar payment-gateway.jar
~~~

CLI argument:

~~~bash
java -jar payment-gateway.jar \
  --payments.client.timeout=800ms
~~~

Trong thứ tự mặc định thông thường, Spring Boot command-line arguments ưu tiên hơn Java system properties. Nhưng ứng dụng có thể đã vô hiệu hóa command-line properties bằng cấu hình SpringApplication hoặc có custom EnvironmentPostProcessor. Do đó cần kiểm tra application startup code.

### 18.1. Cú pháp JVM option và application argument khác nhau

Option `-Dname=value` phải được truyền cho JVM trước `-jar` ở cách gọi lệnh thông thường. Option `--name=value` sau tên JAR là argument của application mà Spring Boot có thể đọc.

Đặt sai vị trí có thể khiến nguồn tưởng được cấp không có hiệu lực.

### 18.2. Không tự cho rằng test environment giống production

Một `@SpringBootTest(properties=...)` có thể thêm nguồn có precedence khác với CLI/env của production. Test chạy pass không chứng minh process production dùng cùng value, trừ khi test mô phỏng nguồn cần kiểm chứng.

## 19. SPRING_APPLICATION_JSON có thể là nguồn thắng

Spring Boot hỗ trợ đưa một JSON object qua `SPRING_APPLICATION_JSON`, Java system property hoặc command line theo cơ chế tương ứng.

Ví dụ:

~~~bash
export SPRING_APPLICATION_JSON='{"payments":{"client":{"timeout":"900ms"}}}'
java -jar payment-gateway.jar
~~~

Nếu không có CLI override cao hơn, JSON có thể thắng OS environment và Config Data trong thứ tự mặc định của Spring Boot.

### 19.1. Null không phải lệnh xóa override thấp hơn

Với:

~~~json
{
  "payments": {
    "client": {
      "timeout": null
    }
  }
}
~~~

`null` từ JSON property source không được xem là giá trị ghi đè hiệu quả lên giá trị thấp hơn theo semantics của property resolution. Không dùng `null` như một cách chắc chắn để “unset” property đã được cấp từ application.yml.

### 19.2. Không đưa secret trực tiếp vào ví dụ JSON thực tế

JSON environment có thể chứa API keys/password, và dữ liệu có thể lộ qua công cụ process/container inspection nếu quyền sai. Khi debug, chỉ ghi nhận tên nguồn và key không nhạy cảm, không dump toàn bộ payload.

## 20. Config Tree và file mount: có file mới nhưng bean cũ

Trong Kubernetes/Docker, một secret hoặc config có thể được mount dạng file:

~~~text
/run/config/payments.client.timeout
~~~

Với nội dung:

~~~text
2s
~~~

Spring Boot có thể nạp qua Config Data:

~~~properties
spring.config.import=optional:configtree:/run/config/
~~~

Khi đó tên file tương ứng property name, còn nội dung file là value.

### 20.1. Cập nhật filesystem không đồng nghĩa hot reload

Nếu file được mount thay từ 2s thành 5s khi JVM đã chạy:

- Filesystem view có thể nhận bản mới.
- Config Data đã được nạp lúc startup **không mặc định tự đọc lại**.
- `@ConfigurationProperties` đã bind **không mặc định tự rebind**.
- HTTP client đã xây dựng **không mặc định tự rebuild**.

Vì vậy, nếu một operator mở file trong Pod và thấy `5s` nhưng bean vẫn là `2s`, có thể không phải lỗi precedence; đó là **lifecycle snapshot**.

### 20.2. Kubernetes ConfigMap/Secret env vs volume

- Dữ liệu cấp qua **environment variables** được gắn vào container khi tạo, không tự cập nhật environment của process đang chạy khi ConfigMap/Secret object đổi.
- Dữ liệu cấp qua **volume mount thông thường** có thể được cập nhật sau độ trễ, nhưng Spring Bean không tự refresh.
- Mount qua **subPath** có giới hạn cập nhật: không trông chờ nội dung tự đổi giống volume mount thường.

Một incident report cần nói rõ config source thay đổi ở tầng nào và process/container nào đã được tạo mới.

### 20.3. Không log secret trong Config Tree

Nếu file tên `db.password` hoặc `partner.api.token`, không đưa raw value vào diagnostics. Đối với secret rotation, dùng version ID không nhạy cảm, audit logs và kiểm tra authentication có kiểm soát.

## 21. Một trường hợp dễ gây nhầm: @PropertySource quá muộn

Một `@Configuration` có thể thêm file properties:

~~~java
@Configuration(proxyBeanMethods = false)
@PropertySource("classpath:legacy.properties")
class LegacyPropertyConfig {}
~~~

File:

~~~properties
logging.level.root=DEBUG
spring.main.banner-mode=off
payments.client.timeout=2s
~~~

Những property như `logging.*` và `spring.main.*` được Boot sử dụng rất sớm, trước khi configuration class này được xử lý trong refresh. Vì vậy, ngay cả khi cuối cùng `Environment` chứa một key, nó có thể đã được thêm **sau thời điểm** component cần thiết đọc value.

### 21.1. Nguồn tồn tại nhưng tác động không còn kịp

Đây là loại lỗi khác với source có precedence thấp:

~~~text
Nguồn có trong Environment?             Có thể có.
Lookup sau refresh trả đúng value?      Có thể có.
Logging system đã được setup lại?       Không thể kết luận.
SpringApplication đã đọc lại main.*?    Không thể mặc định.
~~~

Khi gặp thuộc tính bootstrap, cần kiểm tra **thời điểm nạp**. Giải pháp thường là chuyển giá trị sang Config Data hoặc nguồn sớm thích hợp, chứ không chỉ tăng precedence của `@PropertySource` sau refresh.

### 21.2. YAML và multi-document

`@PropertySource` mặc định không phải cơ chế tương đương Boot Config Data cho YAML, profile activation hoặc multi-document configuration. Nếu file legacy là YAML có `---` và `spring.config.activate.on-profile`, việc dùng custom `PropertySourceFactory` chỉ giải quyết một phần parsing và không tự tạo toàn bộ Config Data semantics.

## 22. Phân biệt lỗi nạp nguồn, lỗi chọn source và lỗi binding

Một ma trận hữu ích:

| Lớp | Triệu chứng | Kiểm tra đầu tiên |
| --- | --- | --- |
| Source absent | File đã sửa không xuất hiện trong origin/source list | Path, working directory, profile, import |
| Source present but overridden | File có key nhưng effective value khác | PropertySource order, CLI/env |
| Wrong canonical name | YAML/env var có key gần đúng nhưng bean không nhận | Prefix, kebab case, relaxed binding |
| Conversion failure | Timeout dạng `nonsense` làm startup fail | Type `Duration` và đơn vị |
| Missing @ConfigurationProperties bean | Environment có key nhưng injection fail | Scan/EnableConfigurationProperties |
| Bean snapshot | Environment đổi sau startup, bean không đổi | Rebind/restart lifecycle |
| Client snapshot | Bean mới đúng nhưng client cũ vẫn chạy | Client creation, cache/rebuild |
| Wrong timeout semantic | Config có `800ms` nhưng behavior là read timeout của proxy | Phân biệt connect/request/read/total |
| Multi-instance mismatch | Request này 800ms, request khác 2s | Pod identity, version, rollout |
| Sensitive source masked | Actuator che value | Dùng evidence an toàn, không tắt masking công khai |

### 22.1. Sai prefix

Code:

~~~java
@ConfigurationProperties(prefix = "payments.client")
public record PaymentClientProperties(Duration timeout) {}
~~~

Nhưng YAML:

~~~yaml
payment:
  client:
    timeout: 5s
~~~

Thiếu chữ `s` trong `payments`. Loader YAML vẫn parse thành công nhưng key khác với prefix được bind. Trường hợp này không thể chữa bằng đổi precedence.

### 22.2. Conversion failure

Giá trị:

~~~yaml
payments:
  client:
    timeout: "very slow"
~~~

không phải Duration hợp lệ. Boot Binder có thể báo lỗi conversion khi tạo properties bean. Khi đó, log lỗi và origin file/line của giá trị nếu được loader hỗ trợ là bằng chứng quan trọng.

### 22.3. Null và default

Một bean primitive có thể có default khác một record nullable, và `@DefaultValue` trong constructor binding có thể ảnh hưởng hành vi khi key vắng. Khi điều tra “giá trị cuối là 0”, cần phân biệt:
- Property không tồn tại.
- Property tồn tại nhưng bị null semantics.
- Class có default initializer/constructor value.
- Bean được tạo từ cơ chế không bind như tưởng tượng.

## 23. Đối chiếu Environment và bean khi xảy ra sai khác

Ví dụ log an toàn:

~~~text
At startup:
  effective timeout = 800ms
  bound timeout     = PT0.8S

After a manual runtime override:
  effective timeout = 2s
  bound timeout     = PT0.8S
~~~

Một giải thích có thể là một component đã cập nhật `Environment` sau khi bean được bind, nhưng chưa rebind bean. Một giải thích khác là hai phép đo đến từ hai instances khác nhau.

Cần ghi timestamp và instance identity khi đo để không kết luận sai.

### 23.1. Không coi @ConfigurationProperties là live view

`@ConfigurationProperties` là object chứa các giá trị Binder cấp trong vòng đời tạo/bind. Một record immutable không tự thay đổi sau khi file được sửa. JavaBean mutable cũng không tự cập nhật setter nếu không có cơ chế refresh.

### 23.2. @Value cũng thường là snapshot

Field/constructor `@Value` thường được giải quyết khi bean được tạo. Gọi một method trên bean sau khi file sửa không có nghĩa annotation sẽ được tính lại.

### 23.3. Dynamic refresh là khả năng bổ sung

Spring Cloud có những cơ chế như `@RefreshScope` trong các môi trường tích hợp phù hợp, nhưng nó **không thuộc tính năng tự động của Spring Boot core** và không bảo đảm mọi client/pool được tạo lại. Khi có refresh mechanism, phải xác minh source reload, bean rebind/recreation và behavior cuối cùng.

## 24. Tạo một test nhỏ để chứng minh precedence

`ApplicationContextRunner` phù hợp khi cần kiểm tra bean config từ những property values cụ thể, không cần khởi động toàn bộ service.

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

class PaymentClientPropertiesTest {

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(PaymentClientProperties.class)
    static class Config {}

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(Config.class);

    @Test
    void bindsDurationFromInput() {
        runner.withPropertyValues(
                "payments.client.base-url=https://payments.example.test",
                "payments.client.timeout=800ms"
        ).run(context -> {
            var props =
                    context.getBean(PaymentClientProperties.class);
            assertThat(props.timeout())
                    .isEqualTo(Duration.ofMillis(800));
        });
    }
}
~~~

Test này chứng minh **conversion và binding**. Nó không chứng minh Spring Boot trong production đã nạp đúng external files hoặc CLI args. Để kiểm tra source order của các nguồn thật, cần integration test đúng pipeline hoặc kiểm tra process startup.

### 24.1. MockEnvironment cho hai nguồn tự định nghĩa

~~~java
import java.util.Map;

import org.springframework.core.env.MapPropertySource;
import org.springframework.mock.env.MockEnvironment;

MockEnvironment env = new MockEnvironment();

env.getPropertySources().addLast(
        new MapPropertySource(
                "application-config",
                Map.of("payments.client.timeout", "5s")
        )
);

env.getPropertySources().addFirst(
        new MapPropertySource(
                "command-line-example",
                Map.of("payments.client.timeout", "800ms")
        )
);

String value = env.getProperty("payments.client.timeout");
// value = "800ms"
~~~

Đây là một test model của precedence bằng các sources bạn kiểm soát. Nó không mô phỏng mọi rule Boot Config Data hoặc relaxed binding từ hệ điều hành.

### 24.2. End-to-end startup test

Khi cần kiểm chứng command-line override thật:

1. Build một Spring Boot test fixture có typed properties.
2. Cấp file `application.yml` với `5s`.
3. Khởi động fixture bằng `--payments.client.timeout=800ms`.
4. Cho fixture in một **key allowlisted không nhạy cảm** hoặc expose test-only probe được bảo vệ.
5. Assert bean có `800ms`.
6. Bỏ CLI override và chạy lại trong môi trường được kiểm soát.
7. Đối chiếu nguồn tiếp theo thắng.

Với OS environment thật, có thể dùng `ProcessBuilder.environment()` cho một child process. Không cố mutate `System.getenv` trong JVM test bằng reflection.

## 25. Debug Spring Boot configuration: dùng công cụ đúng mục đích

### 25.1. --debug và auto-configuration condition report

Chạy:

~~~bash
java -jar payment-gateway.jar --debug
~~~

có thể giúp in auto-configuration condition evaluation report. Nó hữu ích để xem vì sao auto-configuration được kích hoạt hoặc không, nhưng **không thay thế bằng chứng origin của một property cụ thể**.

Không đọc condition report rồi khẳng định biết value của `payments.client.timeout` nếu chưa xem nguồn.

### 25.2. Logging Config Data

Có thể điều chỉnh logging của thành phần Config Data ở môi trường thử nghiệm để quan sát hoạt động load. Tên logger và mức chi tiết có thể khác theo phiên bản Spring Boot, và logs có thể chứa thông tin nhạy cảm về đường dẫn nội bộ.

Không bật TRACE trên production lâu dài và không dùng logging để xuất mọi property value.

### 25.3. Actuator info/health

Health endpoint có thể xác nhận instance ready, nhưng một health response 200 không chứng minh HTTP client timeout đã đổi đúng. Muốn xác minh cấu hình có hiệu lực, cần kiểm tra typed bean hoặc một hành vi liên quan đến property.

### 25.4. Distributed tracing

Một trace có thể cho thấy request bị hủy sau 800ms tại component nào. Kết hợp trace với bean config và source origin giúp phân biệt lỗi config với lỗi network hoặc timeout của bên trung gian.

Không gửi authorization header, cookies hoặc token vào trace attributes.

## 26. Quy trình 10 bước để xử lý một incident cấu hình

### Bước 1 — Xác định triệu chứng

Viết rõ:
- Đường nghiệp vụ nào lỗi?
- Thời điểm bắt đầu?
- Ảnh hưởng bao nhiêu requests/instances?
- Expected behavior là gì?
- Có rollback hoặc mitigation an toàn ngay không?

Tránh viết “YAML lỗi” khi chỉ biết request timeout.

### Bước 2 — Chọn property cần kiểm tra

Từ code/config contract, xác định canonical key và type:

~~~text
payments.client.timeout
Type: java.time.Duration
Consumer: PaymentClientProperties -> HttpClient.connectTimeout
~~~

Nếu có nhiều timeout layers, liệt kê từng layer.

### Bước 3 — Đo effective value ở đúng instance

Dùng `Environment.getProperty` cho key không nhạy cảm hoặc endpoint Actuator được bảo vệ. Ghi instance ID và timestamp.

### Bước 4 — Đo bean value và resource behavior

Đọc `PaymentClientProperties.timeout()` và xác định client có sử dụng bean đó lúc khởi tạo hay không. Phân biệt connect timeout với total request timeout.

### Bước 5 — Tìm nguồn thắng

Dùng property source order/Actuator env và origin nếu sẵn có. Không đoán từ tên file source đang mở.

### Bước 6 — Vẽ precedence chain

Liệt kê tất cả các nguồn có cùng key hoặc alias liên quan, với giá trị an toàn và thứ tự tương ứng. Không chỉ liệt kê nguồn thắng; nguồn tiếp theo sẽ thắng nếu bỏ override.

### Bước 7 — Kiểm tra profiles, locations, imports

Xác nhận active profiles, working directory, file thực tế đã nạp, Config Data activation và optional imports.

### Bước 8 — Kiểm tra lifecycle

Có chỉnh file sau startup không? Có config watcher/refresh không? Các Pods mới/cũ có cùng revision không? Bean/client đã được xây dựng lại chưa?

### Bước 9 — Sửa đúng nguồn và triển khai an toàn

Bỏ override tạm hoặc sửa nguồn canonical, validate config, rollout đúng instances với readiness/graceful shutdown, giữ rollback revision.

### Bước 10 — Chứng minh kết quả và phòng tái diễn

Xác nhận effective value, typed bean, behavior, metrics và logs. Thêm regression tests, ghi owner của config và kiểm tra deployment scripts.

## 27. Incident report mẫu

### 27.1. Tóm tắt

> Staging `payment-gateway` gặp timeout kết nối ngắn hơn mong đợi. Trong repository, `application.yml` đặt `payments.client.timeout=5s`, nhưng bean chạy thực tế nhận `800ms`.

### 27.2. Phạm vi

- Môi trường: staging.
- Component: HTTP client kết nối Payment API.
- Thời điểm: từ sau đợt rollout giả định.
- Instances: cần xác nhận theo danh sách Pods/VM thực tế.
- Key: `payments.client.timeout`.

### 27.3. Bằng chứng

| ID | Bằng chứng | Ý nghĩa |
| --- | --- | --- |
| E1 | `application.yml` trong JAR có `5s` | Có default ở một nguồn thấp hơn |
| E2 | Profile `staging` active | Profile-specific Config Data được xét |
| E3 | External `application-staging.yml` có `2s` | Có nguồn external cung cấp cùng key |
| E4 | Environment có `PAYMENTS_CLIENT_TIMEOUT=1500ms` | OS env có override |
| E5 | Process arguments chứa `--payments.client.timeout=800ms` | CLI cung cấp nguồn cao |
| E6 | Effective lookup trả `800ms` | Giá trị Environment thắng |
| E7 | Bound `Duration=PT0.8S` | Binder dùng value tương ứng |
| E8 | HTTP client tạo từ bean đó | Liên hệ cấu hình với component |

### 27.4. Nguyên nhân gốc

Startup script để lại CLI timeout `800ms` từ một thí nghiệm latency trước. Do thứ tự ưu tiên, nó thắng những nguồn YAML và env thấp hơn. Sửa repository default không tác động tới runtime khi override vẫn tồn tại.

### 27.5. Khắc phục

- Xóa CLI override không còn đúng với policy.
- Quy định rõ nơi quản lý timeout canonical.
- Kiểm tra env override còn lại trước khi rollout.
- Cập nhật script/deployment manifest.
- Khởi động lại/rolling rollout các instances có liên quan.
- Test timeout thực tế, thay vì chỉ assert YAML value.

### 27.6. Phòng ngừa

- Review process args/Helm values khi thay timeout.
- Thêm test cho binding và profile-specific behavior.
- Ghi version config không nhạy cảm trong deployment metadata.
- Giới hạn override ad hoc của CLI/CI.
- Cung cấp một quy trình observability cho allowlisted config keys.
- Không cho debug endpoint làm lộ secrets.

## 28. Một case khác: file đúng nhưng không được nạp

Giả sử:

~~~text
Host file: /srv/payment/config/application.yml
JVM cwd:   /app
Expected:  /app/config/application.yml
~~~

Operator sửa file ở host nhưng Pod chạy trong container với volume mount tại đường dẫn khác, hoặc không có volume mount.

Bằng chứng:

- Host file có `5s`.
- Container filesystem không có file ở location Boot tìm.
- `Environment` không có origin từ file đó.
- Bean dùng default trong JAR `2s`.

Root cause không phải precedence giữa hai sources. Nó là **path/mount mismatch** khiến source mới hoàn toàn không được đọc.

### Hướng xử lý

- Xác nhận working directory và container mount path.
- Dùng `spring.config.additional-location` hoặc một import đúng khi cần.
- Bảo đảm file tồn tại trong filesystem mà JVM nhìn thấy.
- Khởi động lại instance sau khi nguồn đã được phân phối.
- Xác nhận origin từ đúng file/path trên instance mới.

Không chỉ tăng value ở một file sai đường dẫn.

## 29. Case thứ ba: profile không active

File:

~~~yaml
# application-prod.yml
feature:
  payments:
    strict-validation: true
~~~

Nhưng ứng dụng chạy với profile `staging`. Giá trị `strict-validation=true` không tự áp dụng từ `application-prod.yml`.

Bằng chứng:

- `Environment.getActiveProfiles()` không chứa `prod`.
- Config Data của `application-prod.yml` không tham gia theo profile như kỳ vọng.
- Effective value đến từ default hoặc source khác.
- Không có lỗi YAML syntax nào bắt buộc xuất hiện.

Root cause: **đang sửa configuration cho một profile không active**.

Giải pháp là sửa nguồn/profile thực sự dùng hoặc chọn active profile theo deployment policy. Không nên kích hoạt `prod` một cách tùy tiện trên staging chỉ để một key có hiệu lực, vì profile đó có thể kéo theo nhiều thay đổi khác.

## 30. Case thứ tư: Environment đúng nhưng client vẫn dùng giá trị cũ

Giả sử:

~~~text
T0: Bean được bind với timeout 2s.
T1: HTTP client được tạo với timeout 2s.
T2: Custom logic thêm MapPropertySource ưu tiên cao timeout 5s.
T3: Environment.getProperty() trả 5s.
T4: HTTP client cũ vẫn giữ 2s.
~~~

Sự cố nằm ở **binding/client lifecycle**, không còn là tranh chấp file source thông thường.

### Hướng xử lý

- Với cấu hình startup-only, restart/recreate process.
- Nếu cần dynamic refresh, thiết kế lại cơ chế nạp, validate, bind và rebuild client.
- Xác định request đang chạy có tiếp tục dùng snapshot cũ không.
- Kiểm tra toàn bộ replicas và rollback behavior.

Không cố làm `Environment` hiển thị đúng bằng cách chèn thêm source rồi kết luận client đã tự đổi.

## 31. Case thứ năm: giá trị có hiệu lực đúng nhưng ý nghĩa timeout sai

Bean `PaymentClientProperties.timeout()` là 5s. Người vận hành vẫn thấy một request fail sau 800ms do:

- Một load balancer hoặc gateway có timeout riêng.
- Connect timeout khác total request timeout.
- Một `HttpRequest.timeout` khác được đặt trên từng request.
- Circuit breaker hoặc retry budget ngắn hơn.
- Cancellation từ caller hoặc deadline upstream.
- Socket/read timeout ở một client library khác.

Trong trường hợp này, nguồn cấu hình đã đúng; cần mở rộng điều tra sang **hợp đồng các lớp timeout** và tracing. Chỉ tăng `payments.client.timeout` có thể không giải quyết.

Đây là điểm kiểm tra cuối của lập luận: **provenance giải thích một giá trị đến từ đâu**, nhưng nguyên nhân nghiệp vụ cần nối value đó với component thực sự gây lỗi.

## 32. Cách giữ bằng chứng mà không làm lộ bí mật

Một incident có thể yêu cầu hỗ trợ từ nhiều team. Bản evidence package nên chứa:

- Tên key không nhạy cảm.
- Instance/revision và timestamp.
- Active profiles.
- Tên sources và origin metadata được phép chia sẻ.
- Giá trị scalar không nhạy cảm đã được xác nhận.
- Typed bean value nếu không nhạy cảm.
- Log lỗi/trace đã redact.
- Diff của startup args hoặc deployment manifest, đã che tokens.
- Quyết định thay đổi, người chịu trách nhiệm và kết quả rollout.

Không đưa vào:

- Password và API tokens.
- Full `System.getenv()` dump.
- File Secret hoặc `SPRING_APPLICATION_JSON` raw có credential.
- TLS private keys.
- Connection URLs có username/password trong query.
- Actuator env output chưa được rà soát.

### 32.1. Có thể chỉ cần presence thay vì value

Nếu key nhạy cảm, thay vì log:

~~~text
partner.api.token = <raw token>
~~~

hãy log dạng:

~~~text
partner.api.token: present
source: approved secret provider
secret version: v17 (non-sensitive identifier)
~~~

Chỉ sử dụng secret version ID khi hệ thống quản trị bí mật thực sự cung cấp và chính sách cho phép hiển thị.

## 33. Những sai lầm thường gặp

| Sai lầm | Tại sao sai | Cách đúng hơn |
| --- | --- | --- |
| “application.yml ghi 5s, vậy app nhận 5s” | Có nguồn cao hơn và profile/import | Xem effective value và source |
| “File nào sửa sau sẽ thắng” | Precedence không dựa vào timestamp | Xem property source order |
| “Chỉ cần xem source.getName() là có line origin” | Source name và origin metadata khác nhau | Dùng origin tracking nếu có |
| “Actuator env luôn in value” | Có chính sách masking/sanitization | Không tắt bảo vệ tùy tiện |
| “Env var không liên quan key dotted” | Relaxed binding có thể ánh xạ | Kiểm tra naming rules |
| “getProperty null trong một raw source nghĩa là Binder không thể thấy” | Canonical adaptation khác raw lookup | Kiểm tra effective binding |
| “YAML ngoài JAR luôn được nạp” | Working directory/location/import có thể sai | Xác minh source thực tế |
| “optional:file: nghĩa là file tồn tại” | optional chỉ cho phép thiếu | Kiểm tra path và validation |
| “Thêm CLI override là sửa được nguyên nhân” | Chỉ che lấp nguồn sai | Sửa source canonical |
| “Sửa ConfigMap là Pod đã đổi config” | Env snapshots và bean lifecycle | Trigger rollout/rebind phù hợp |
| “Environment đổi tức bean/client đổi” | Bean và resource thường là snapshots | Restart hoặc refresh có thiết kế |
| “Active profile là tên môi trường từ CI” | Cần kiểm tra profiles trong process | Đọc activeProfiles |
| “@PropertySource có thể quyết định mọi cấu hình rất sớm” | Được xử lý tương đối muộn | Dùng Config Data/early source |
| “--debug in toàn bộ property origin” | Chủ yếu condition report | Dùng env/source/origin riêng |
| “Bean value đúng chứng minh timeout network do bean” | Có nhiều timeout layers | Test hành vi và tracing |
| “Một Pod đúng là cả deployment đúng” | Replicas có thể lệch revision | Kiểm tra mọi instance |

## 34. Bài tập thực hành

### Bài tập A — Truy tìm 800ms

Dùng năm nguồn cấu hình ở phần 3. Dự đoán effective value. Sau đó lần lượt xóa CLI, environment variable và external file trong các lần startup riêng. Ghi nguồn tiếp theo thắng ở mỗi trường hợp và giải thích precedence.

### Bài tập B — Làm chứng cứ nguồn gốc

Thêm một probe chỉ đọc `payments.client.timeout`, liệt kê `PropertySource` names và effective value. Nếu Config Data source có origin metadata, ghi file/dòng không nhạy cảm. So sánh với `@ConfigurationProperties` bean.

### Bài tập C — Nhầm working directory

Đặt `application.yml` dưới `./config`. Chạy ứng dụng từ hai working directories khác nhau. So sánh sources đã nạp. Sử dụng một location rõ ràng để sửa tình huống file không được tìm.

### Bài tập D — Profile-specific document

Đặt `feature.payments.strict-validation` khác nhau giữa default, `staging` và `prod`. Chạy với từng profile. Thử thêm một CLI override và giải thích source thắng.

### Bài tập E — spring.config.import

Tạo file import `./overrides/payment.yml` với timeout 2s và file application có timeout 5s. Quan sát behavior của import. Thử xóa file khi có/không có `optional:` và so sánh startup failure.

### Bài tập F — Relaxed binding

Với property `payments.client.timeout`, cấp `PAYMENTS_CLIENT_TIMEOUT=1500ms` qua child process environment hoặc container configuration. So sánh với `Environment.getProperty` và `System.getenv`. Không mutate OS environment của JVM test bằng reflection.

### Bài tập G — Runtime Environment change

Dựng một context với timeout 2s, tạo bean/client; sau đó thêm `MapPropertySource` ở đầu với 5s. So sánh effective lookup, bound bean, client. Giải thích vì sao kết quả có thể khác.

### Bài tập H — Phân biệt connect và request timeout

Dùng Java `HttpClient` với connectTimeout và từng `HttpRequest.timeout`. Tạo một mock HTTP server có delay được kiểm soát. Kiểm tra loại timeout nào thực sự chặn request. Không dùng public payment provider.

### Bài tập I — Kubernetes ConfigMap

Cấp một ConfigMap qua env var và qua volume mount trong sandbox. Thay ConfigMap khi Pod chạy; quan sát source trên filesystem, process env, bean đã bind và behavior sau rollout. Không dùng secret production.

### Bài tập J — Viết incident report

Cho evidence:
- File JAR ghi timeout 5s.
- Profile staging active.
- External YAML ghi 2s.
- Env ghi 1500ms.
- CLI ghi 800ms.
- Bean có `PT0.8S`.

Viết một báo cáo gồm symptom, evidence chain, root cause, remediation, verification và prevention. Ghi rõ nguồn nào sẽ thắng **sau khi chỉ xóa CLI**.

## 35. Checklist trước khi đóng sự cố

### Xác định nguồn

- [ ] Đã biết chính xác artifact/image revision và instance.
- [ ] Đã biết startup args/JVM flags sau khi redact.
- [ ] Đã biết active profiles, working directory và file locations.
- [ ] Đã biết Config Data imports và active documents.
- [ ] Đã kiểm tra OS environment, system properties, JSON và CLI có key liên quan không.
- [ ] Đã xác nhận tên canonical và relaxed binding của key.

### Xác định giá trị

- [ ] Đã đo effective Environment value.
- [ ] Đã xác định source thắng và các sources thấp hơn.
- [ ] Đã lưu source name/origin thực tế nếu có.
- [ ] Đã đối chiếu bean `@ConfigurationProperties`.
- [ ] Đã kiểm tra client/connection pool/scheduler dùng value thế nào.
- [ ] Đã xét thời điểm bind, restart/refresh và khác biệt giữa replicas.

### Sửa và xác nhận

- [ ] Đã sửa đúng nguồn, không chỉ thêm override khác.
- [ ] Đã cập nhật owner/deployment scripts tương ứng.
- [ ] Đã kiểm tra YAML/properties syntax và validation.
- [ ] Đã có rollout/restart hoặc refresh mechanism phù hợp.
- [ ] Đã xác nhận mọi instance dùng cùng version mong muốn.
- [ ] Đã đo behavior của component sau thay đổi.
- [ ] Đã giữ rollback được cả image lẫn config khi cần.
- [ ] Đã thêm regression tests hoặc guardrails.
- [ ] Bằng chứng/logs đã được che secret.

## 36. Kết luận: một giá trị có cả nguồn, vòng đời và nơi sử dụng

Khi một property trong Spring Boot “không đúng như file”, không nên vội gọi đó là bug cấu hình. Hãy lần theo một chuỗi có thể kiểm chứng:

~~~text
Nguồn trên filesystem/deployment
             |
             v
Config Data / OS env / JVM / CLI
             |
             v
PropertySource order và origin
             |
             v
Effective Spring Environment value
             |
             v
Binder / @ConfigurationProperties / @Value
             |
             v
Bean/client đã tạo và lifecycle
             |
             v
Hành vi request/transaction thực tế
~~~

Trong case study, lỗi đến từ **CLI override 800ms** còn sót lại. File `application.yml` ghi 5s không sai, nhưng đó không phải nguồn có ưu tiên cao nhất. Nếu chỉ xóa CLI mà vẫn giữ `PAYMENTS_CLIENT_TIMEOUT=1500ms`, ứng dụng có thể nhận **1500ms**, chứ không tự quay về 5s.

Một kết luận điều tra tốt phải trả lời bốn câu:

1. **Giá trị nào đang có hiệu lực?**
2. **Nguồn nào cung cấp nó, có origin nào hỗ trợ?**
3. **Component nào đã thực sự sử dụng giá trị ấy?**
4. **Cần thay đổi và xác nhận điều gì để sửa lỗi bền vững?**

Nếu chỉ trả lời được câu 1 và 2, bạn mới hoàn thành **truy xuất nguồn giá trị**. Để đóng sự cố, còn phải xác nhận **binding, resource lifecycle và hành vi nghiệp vụ**.

## Tài liệu tham khảo

- [Spring Boot Reference — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): danh sách PropertySources, precedence, Config Data, profile-specific sources và imports.
- [Spring Boot Reference — External Application Properties](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.files): classpath/external locations, profile-specific documents và location groups.
- [Spring Boot Reference — Importing Additional Data](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.files.importing): `spring.config.import`, optional imports và Config Tree.
- [Spring Boot Reference — Type-safe Configuration Properties](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties): Binder, relaxed binding, constructor binding và validation.
- [Spring Boot Actuator — Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html): `env`, `configprops`, security, exposure và value sanitation.
- [Spring Boot API — Origin](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/origin/Origin.html): biểu diễn nguồn gốc cấu hình.
- [Spring Boot API — OriginLookup](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/origin/OriginLookup.html): truy vấn origin metadata khi được hỗ trợ.
- [Spring Framework API — ConfigurableEnvironment](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/env/ConfigurableEnvironment.html): quản lý PropertySources và đọc Environment.
- [Spring Framework API — PropertySource](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/env/PropertySource.html): phân biệt source name, property lookup và thứ tự nguồn.
- [Kubernetes — ConfigMaps](https://kubernetes.io/docs/concepts/configuration/configmap/): env vs mounted config, cập nhật và những giới hạn.
- [Kubernetes — Secrets](https://kubernetes.io/docs/concepts/configuration/secret/): secret sources, volumes và yêu cầu bảo vệ dữ liệu nhạy cảm.
