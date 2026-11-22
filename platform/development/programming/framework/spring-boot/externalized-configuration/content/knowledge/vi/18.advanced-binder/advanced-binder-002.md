# Lấy Binder từ Environment và liên kết theo prefix

## 1. Mục tiêu: chủ động bind một nhánh cấu hình thành đối tượng

**Spring Boot Externalized Configuration** cho phép ứng dụng lấy cấu hình từ file **application.yml**, **application.properties**, biến môi trường, system properties, command-line arguments, config data ngoài JAR và những PropertySource khác.

Khi cần một giá trị đơn lẻ, có thể gọi:

~~~java
String url = environment.getProperty("integration.payment.base-url");
~~~

Nhưng nếu cần cả một nhóm thông số như URL, timeout, retry policy, danh sách endpoints và map header, việc gọi từng key rồi tự chuyển kiểu sẽ trở nên dài và dễ sai. Spring Boot cung cấp **Binder** để liên kết những property có cùng **prefix** vào một đối tượng Java có cấu trúc.

Phần lớn ứng dụng sẽ khai báo một bean **@ConfigurationProperties** và để Spring Boot tự xử lý. Tuy nhiên, đôi khi ta cần **bind chủ động**: chọn prefix ở thời điểm nhất định, tạo một snapshot phục vụ chẩn đoán, kiểm thử một nhóm property hoặc xây component hạ tầng không muốn đăng ký thêm configuration bean.

Cách bắt đầu:

~~~java
Binder binder = Binder.get(environment);
~~~

Sau đó:

~~~java
PaymentSettings settings = binder
        .bind("integration.payment",
              Bindable.of(PaymentSettings.class))
        .orElseThrow(() -> new IllegalStateException(
                "Missing integration.payment configuration"));
~~~

Trong đoạn trên:

1. **Environment** chứa hoặc có thể truy cập các nguồn cấu hình đang hoạt động.
2. **Binder.get(environment)** tạo một Binder dựa trên Environment ấy.
3. **"integration.payment"** là đường prefix cần liên kết.
4. **Bindable.of(PaymentSettings.class)** diễn tả kiểu đích.
5. **bind(...)** trả **BindResult<PaymentSettings>**.
6. **orElseThrow(...)** cung cấp chính sách khi không bind được kết quả.

Đây là API chính của bài, không phải đọc từng field bằng **Environment.getProperty(...)**.

## 2. Mô hình các lớp liên quan

Hình dung quá trình:

~~~text
application.yml    application-prod.yml    env / CLI / system properties
       \                  |                         /
        \                 |                        /
         +----------------+-----------------------+
                          |
                          v
                     Environment
                          |
                          v
                 Binder.get(environment)
                          |
                          v
             bind("integration.payment",
                  Bindable.of(PaymentSettings.class))
                          |
                          v
                 BindResult<PaymentSettings>
                          |
                          v
               PaymentSettings Java object
~~~

Các thành phần:

| Thành phần | Vai trò |
| --- | --- |
| **Environment** | Giao diện truy xuất các property và profile đang hiệu lực |
| **PropertySource** | Nguồn cung cấp property cụ thể, ví dụ environment variables hoặc Config Data |
| **Binder** | Engine ánh xạ nhiều property thành cấu trúc Java |
| **ConfigurationPropertyName** | Cách Spring Boot biểu diễn tên cấu hình chuẩn trong Binder |
| **Bindable<T>** | Mô tả type/instance cần bind, kể cả generic types |
| **BindResult<T>** | Kết quả cho biết có giá trị được bind hay không và cung cấp API lấy giá trị |
| **BindHandler** | Hook tùy chọn cho quá trình bind, lỗi, kiểm tra và các chính sách khác |
| **@ConfigurationProperties** | Cách khai báo type để Spring Boot tự tổ chức binding trong lifecycle của bean |

Một nguyên tắc quan trọng: **Binder.get(environment)** tạo Binder từ Environment hiện có, không tự quét thư mục, không tự bật profile và không tạo một hệ thống cấu hình độc lập.

Nếu property chưa được nạp vào Environment, Binder không thể tự phát hiện nó chỉ bằng cách đổi prefix.

## 3. Chuẩn bị ví dụ Java và Config Data

Ví dụ sử dụng **Spring Boot 3.3.x**, **Java 21** và **spring-boot-starter-web**.

**src/main/resources/application.yml**:

~~~yaml
integration:
  payment:
    base-url: "https://payments.example.invalid"
    connect-timeout: 2s
    request-timeout: 10s
    retry:
      enabled: true
      max-attempts: 3
      initial-delay: 200ms
    regions:
      - asia
      - europe
    headers:
      client-id: sandbox-client
      api-version: v2
~~~

Đường key tương ứng sau khi YAML được làm phẳng:

~~~text
integration.payment.base-url
integration.payment.connect-timeout
integration.payment.request-timeout
integration.payment.retry.enabled
integration.payment.retry.max-attempts
integration.payment.retry.initial-delay
integration.payment.regions[0]
integration.payment.regions[1]
integration.payment.headers.client-id
integration.payment.headers.api-version
~~~

Domain **example.invalid** là dữ liệu minh họa, không yêu cầu gọi API thực.

Ví dụ dùng Java record để mô tả nhóm cấu hình:

~~~java
package com.example.binder;

import java.net.URI;
import java.time.Duration;
import java.util.List;
import java.util.Map;

public record PaymentSettings(
        URI baseUrl,
        Duration connectTimeout,
        Duration requestTimeout,
        Retry retry,
        List<String> regions,
        Map<String, String> headers) {

    public record Retry(
            boolean enabled,
            int maxAttempts,
            Duration initialDelay) {
    }
}
~~~

Record **không cần @ConfigurationProperties** khi ta sử dụng **Binder thủ công** với **Bindable.of(PaymentSettings.class)**. Dữ liệu được bind vì **code chủ động yêu cầu**, không vì class được đăng ký làm configuration properties bean.

Tuy vậy, Binder vẫn cần một target type có cấu trúc phù hợp: tên record components và nested types cần khớp với các property theo quy tắc Spring Boot.

## 4. Đọc toàn bộ group bằng Binder.get(environment)

Một service minh họa:

~~~java
package com.example.binder;

import org.springframework.boot.context.properties.bind.Bindable;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Service;

@Service
public class PaymentSettingsReader {

    private final Environment environment;

    public PaymentSettingsReader(Environment environment) {
        this.environment = environment;
    }

    public PaymentSettings read() {
        Binder binder = Binder.get(environment);

        return binder
                .bind("integration.payment",
                      Bindable.of(PaymentSettings.class))
                .orElseThrow(() -> new IllegalStateException(
                        "integration.payment is not configured"));
    }
}
~~~

Tại thời điểm **read()** được gọi, Binder sử dụng các giá trị mà Environment có thể cung cấp. Kết quả là một **PaymentSettings** chứa các trường đã được chuyển kiểu.

Không cần gọi:

~~~java
environment.getProperty("integration.payment.base-url");
environment.getProperty("integration.payment.connect-timeout");
environment.getProperty("integration.payment.retry.max-attempts");
~~~

rồi ghép tay thành record.

Một lời gọi **bind(prefix, target)** thể hiện rõ ý định: *lấy cấu hình dưới prefix này và liên kết thành type này*.

### 4.1. Kết quả mong đợi

Từ YAML ở mục 3:

~~~text
baseUrl           = https://payments.example.invalid
connectTimeout    = PT2S
requestTimeout    = PT10S
retry.enabled     = true
retry.maxAttempts = 3
retry.initialDelay= PT0.2S
regions           = [asia, europe]
headers           = {client-id=sandbox-client, api-version=v2}
~~~

Khi hiển thị Duration, cách Java biểu diễn bằng **toString()** có thể là **PT2S**, **PT10S**, **PT0.2S**; đó vẫn là các khoảng thời gian được khai báo bằng **2s**, **10s**, **200ms**.

Binder có nhiệm vụ chuyển chuỗi phù hợp thành **Duration**, **URI**, **int**, **boolean** và cấu trúc List/Map.

## 5. Tạo ứng dụng chạy thử

**src/main/java/com/example/binder/BinderDemoApplication.java**:

~~~java
package com.example.binder;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BinderDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(BinderDemoApplication.class, args);
    }
}
~~~

Một controller chỉ hiển thị vài giá trị không nhạy cảm:

~~~java
package com.example.binder;

import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class BindingDemoController {

    private final PaymentSettingsReader reader;

    public BindingDemoController(PaymentSettingsReader reader) {
        this.reader = reader;
    }

    @GetMapping("/demo/payment-settings")
    public Map<String, Object> settings() {
        PaymentSettings p = reader.read();

        Map<String, Object> result = new LinkedHashMap<>();
        result.put("baseUrl", p.baseUrl().toString());
        result.put("connectTimeoutMs",
                p.connectTimeout().toMillis());
        result.put("requestTimeoutMs",
                p.requestTimeout().toMillis());
        result.put("retryEnabled", p.retry().enabled());
        result.put("maxAttempts", p.retry().maxAttempts());
        result.put("regions", p.regions());
        return result;
    }
}
~~~

Sau khi build và chạy:

~~~bash
./gradlew bootJar
java -jar build/libs/app.jar
~~~

**app.jar** chỉ là tên ví dụ; thay bằng tên artifact thực tế mà Gradle đã tạo.

Gọi:

~~~bash
curl http://localhost:8080/demo/payment-settings
~~~

Kết quả minh họa:

~~~json
{
  "baseUrl": "https://payments.example.invalid",
  "connectTimeoutMs": 2000,
  "requestTimeoutMs": 10000,
  "retryEnabled": true,
  "maxAttempts": 3,
  "regions": ["asia", "europe"]
}
~~~

Không mở endpoint xuất toàn bộ cấu hình ra Internet trong ứng dụng thực tế. Những property như API key hoặc token có thể chứa secret. Ví dụ trên chủ động không trả về header hoặc credential.

## 6. Prefix quyết định phạm vi liên kết

Trong lời gọi:

~~~java
binder.bind("integration.payment",
            Bindable.of(PaymentSettings.class));
~~~

**integration.payment** là prefix gốc. Tên **baseUrl** trong record tương ứng với:

~~~text
integration.payment.base-url
~~~

Tên **retry.maxAttempts** tương ứng:

~~~text
integration.payment.retry.max-attempts
~~~

Nếu đổi prefix:

~~~java
binder.bind("integration.shipping",
            Bindable.of(PaymentSettings.class));
~~~

thì Binder sẽ tìm nhóm **integration.shipping.***. Nó không tự suy rằng payment và shipping có thể dùng chung cấu hình. Nếu nhóm shipping không có property phù hợp, kết quả có thể là **unbound**.

### 6.1. Kết hợp nhiều prefix khác nhau

Bạn có thể dùng cùng một target type cho nhiều nhóm có cùng cấu trúc:

~~~yaml
integration:
  primary-payment:
    base-url: "https://primary.example.invalid"
    connect-timeout: 2s
    request-timeout: 10s
    retry:
      enabled: true
      max-attempts: 3
      initial-delay: 200ms
    regions: [asia]
    headers:
      client-id: primary

  backup-payment:
    base-url: "https://backup.example.invalid"
    connect-timeout: 4s
    request-timeout: 15s
    retry:
      enabled: false
      max-attempts: 1
      initial-delay: 100ms
    regions: [europe]
    headers:
      client-id: backup
~~~

Trong Java:

~~~java
Binder binder = Binder.get(environment);

PaymentSettings primary = binder
        .bind("integration.primary-payment",
                Bindable.of(PaymentSettings.class))
        .orElseThrow();

PaymentSettings backup = binder
        .bind("integration.backup-payment",
                Bindable.of(PaymentSettings.class))
        .orElseThrow();
~~~

Điều này hữu ích khi cùng một kiểu cấu hình có thể xuất hiện nhiều lần với **những namespace khác nhau**.

**Lưu ý bảo mật:** nếu prefix được chọn theo input của request, chỉ cho phép lựa chọn trong một danh sách namespace đã được phê duyệt. Không cho người dùng tự truyền tên prefix bất kỳ để đọc các nhóm cấu hình chứa secret.

## 7. BindResult: có dữ liệu hay không?

**Binder.bind(...)** trả về **BindResult<T>**, không trả trực tiếp **T**.

Ví dụ:

~~~java
import org.springframework.boot.context.properties.bind.BindResult;

BindResult<PaymentSettings> result =
        Binder.get(environment)
                .bind("integration.payment",
                        Bindable.of(PaymentSettings.class));
~~~

Các thao tác thông dụng:

~~~java
boolean found = result.isBound();

PaymentSettings settings = result.orElse(null);

PaymentSettings required = result.orElseThrow();
~~~

Ý nghĩa:

- **isBound()**: có giá trị được bind hay không.
- **get()** hoặc **orElseThrow()**: lấy giá trị khi cần kết quả bắt buộc.
- **orElse(fallback)**: dùng giá trị dự phòng khi không bind được.
- **orElseThrow(supplier)**: có thể chủ động tạo exception mang thông báo rõ ràng khi thiếu cấu hình.

Phân biệt **không tìm thấy cấu hình** với **cấu hình tồn tại nhưng sai kiểu**:

~~~text
Không có integration.payment.*:
  bind(...) có thể trả BindResult không bound

Có integration.payment.connect-timeout=wrong:
  bind(...) có thể ném exception do conversion/binding

Có đủ property nhưng quan hệ nghiệp vụ sai:
  Binder mặc định không tự suy ra quy tắc nghiệp vụ
~~~

Đừng dùng **orElse(...)** để che giấu lỗi chuyển đổi kiểu. Nó nhằm xử lý trường hợp kết quả không bound, không phải lời hứa sẽ bỏ qua mọi lỗi khi bind.

### 7.1. Khi nào dùng get?

Nếu đã kiểm tra:

~~~java
if (result.isBound()) {
    PaymentSettings settings = result.get();
}
~~~

thì **get()** phù hợp.

Nếu không kiểm tra mà gọi **get()** trên một kết quả unbound, API có thể ném exception. Với cấu hình bắt buộc, **orElseThrow(...)** thường diễn đạt ý định rõ hơn.

### 7.2. Khi nào dùng orElse?

Với cấu hình tùy chọn:

~~~java
BindResult<Boolean> flagResult = Binder.get(environment)
        .bind("feature.search.enabled",
                Bindable.of(Boolean.class));

boolean enabled = flagResult.orElse(false);
~~~

Code quy định rõ chức năng không được khai báo thì mặc định tắt. Nhưng nếu cấu hình có **feature.search.enabled=not-a-boolean**, lỗi chuyển đổi cần được xử lý đúng thay vì bỏ qua.

## 8. Binder.bind với Class và với Bindable khác nhau gì?

API **Binder** có overload:

~~~java
binder.bind("integration.payment", PaymentSettings.class);
~~~

và:

~~~java
binder.bind("integration.payment",
            Bindable.of(PaymentSettings.class));
~~~

Với một class cụ thể không có generic type parameter, hai cách này thường cùng thể hiện type đích.

**Bindable** hữu ích hơn khi bạn cần:

- Bind generic types như **List<Endpoint>** hoặc **Map<String, Integer>**.
- Bind tới một instance có sẵn.
- Cung cấp thông tin bổ sung về target type hoặc annotation binding.
- Truyền target vào overload có **BindHandler**.

Đối với một class đơn giản, overload với **Class<T>** rất gọn. Nhưng khi học Binder nâng cao, việc hiểu **Bindable<T>** giúp bạn kiểm soát đối tượng đích rõ ràng hơn.

## 9. Liên kết List bằng Bindable.listOf

YAML:

~~~yaml
integration:
  payment:
    endpoints:
      - name: primary
        url: "https://primary.example.invalid"
      - name: backup
        url: "https://backup.example.invalid"
~~~

Record:

~~~java
package com.example.binder;

import java.net.URI;

public record Endpoint(String name, URI url) {
}
~~~

Bind cả List:

~~~java
import java.util.List;
import org.springframework.boot.context.properties.bind.Bindable;
import org.springframework.boot.context.properties.bind.Binder;

Binder binder = Binder.get(environment);

List<Endpoint> endpoints = binder
        .bind("integration.payment.endpoints",
                Bindable.listOf(Endpoint.class))
        .orElse(List.of());
~~~

Ý nghĩa:

- Prefix giờ là **integration.payment.endpoints**.
- Đích là **List<Endpoint>**, không phải **Endpoint** đơn.
- Binder tìm các phần tử **[0]**, **[1]** và tạo record tương ứng.
- Kết quả có thể được xử lý bằng code Java thông thường.

Ví dụ:

~~~java
for (Endpoint endpoint : endpoints) {
    System.out.println(endpoint.name());
}
~~~

Không phải tự gọi từng key như:

~~~java
environment.getProperty(
        "integration.payment.endpoints[0].name");

environment.getProperty(
        "integration.payment.endpoints[1].name");
~~~

Điểm mạnh của Binder là **dựng cả collection theo cấu trúc**, không chỉ đọc một phần tử đã biết.

### 9.1. Chỉ số trong biến môi trường

Các tên canonical:

~~~text
integration.payment.endpoints[0].name
integration.payment.endpoints[1].url
~~~

có dạng env:

~~~text
INTEGRATION_PAYMENT_ENDPOINTS_0_NAME
INTEGRATION_PAYMENT_ENDPOINTS_1_URL
~~~

Spring Boot hỗ trợ quy tắc chỉ số List được phân tách bằng dấu gạch dưới khi bind từ environment variables.

### 9.2. Cẩn trọng với List ở nhiều nguồn

Nếu cùng một List được khai báo trong YAML và env, nguồn ưu tiên cao hơn có thể **thay thế toàn danh sách**. Nó không tự ghép phần tử 0 của env với phần tử 1 của YAML.

Nếu một môi trường cần một danh sách hoàn chỉnh, nên cấp đủ các phần tử ở nguồn có quyền override; không dựa vào thao tác merge từng chỉ số một cách ngầm định.

## 10. Liên kết Map bằng Bindable.mapOf

Ví dụ các giới hạn số lượng request theo tên vùng:

~~~yaml
integration:
  limits:
    asia: 100
    europe: 150
    america: 80
~~~

Ta muốn bind trực tiếp thành **Map<String, Integer>**:

~~~java
import java.util.Map;
import org.springframework.boot.context.properties.bind.Bindable;
import org.springframework.boot.context.properties.bind.Binder;

Map<String, Integer> limits = Binder.get(environment)
        .bind("integration.limits",
                Bindable.mapOf(String.class, Integer.class))
        .orElse(Map.of());
~~~

Bây giờ:

~~~java
Integer asiaLimit = limits.get("asia");
Integer europeLimit = limits.get("europe");
~~~

Cách này rất phù hợp nếu số lượng key có thể thay đổi theo môi trường hoặc customer mà không muốn sửa Java class để thêm mỗi trường mới.

### 10.1. Map key có ký tự đặc biệt

Spring Boot có quy tắc riêng cho map keys. Nếu cần giữ dấu **/** hoặc dấu chấm trong một key phức tạp, có thể phải dùng bracket notation.

Ví dụ:

~~~properties
integration.labels[/tenant-a]=A
integration.labels[/tenant-b]=B
~~~

Hoặc YAML:

~~~yaml
integration:
  labels:
    "[/tenant-a]": "A"
    "[/tenant-b]": "B"
~~~

Dấu ngoặc giúp bảo tồn key như **/tenant-a**. Nếu không có bracket, một số ký tự không thuộc bộ cho phép có thể bị loại bỏ trong binding.

Với **Map<String, String>**, key có dấu chấm thường được giữ trong một số trường hợp scalar; với **Map<String, Object>**, dấu chấm có thể tạo cấu trúc lồng nhau. Khi key có ý nghĩa đặc biệt, hãy kiểm tra quy tắc **Binding Maps** trong tài liệu Spring Boot.

## 11. Liên kết type có generic lồng nhau

**Bindable.listOf(Endpoint.class)** và **Bindable.mapOf(String.class, Integer.class)** xử lý những generic phổ biến. Với type phức tạp hơn như:

~~~java
Map<String, List<Endpoint>>
~~~

có thể sử dụng **ResolvableType** từ Spring Framework:

~~~java
import java.util.List;
import java.util.Map;
import org.springframework.boot.context.properties.bind.Bindable;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.core.ResolvableType;

ResolvableType listType =
        ResolvableType.forClassWithGenerics(
                List.class, Endpoint.class);

ResolvableType mapType =
        ResolvableType.forClassWithGenerics(
                Map.class,
                ResolvableType.forClass(String.class),
                listType);

Map<String, List<Endpoint>> groups =
        Binder.get(environment)
                .bind("integration.endpoint-groups",
                        Bindable.<Map<String, List<Endpoint>>>of(mapType))
                .orElse(Map.of());
~~~

Giả sử YAML:

~~~yaml
integration:
  endpoint-groups:
    asia:
      - name: primary
        url: "https://asia-primary.example.invalid"
    europe:
      - name: backup
        url: "https://eu-backup.example.invalid"
~~~

Binder sẽ có thông tin đủ về **Map**, **String**, **List** và **Endpoint** để tạo cấu trúc đích.

Đối với các cấu trúc generic sâu, cân nhắc một record trung gian có tên rõ ràng. Generic type quá phức tạp không phải lúc nào cũng là API cấu hình tốt nhất.

## 12. Liên kết vào object có sẵn

Thông thường Binder tạo object mới theo type đích. Trong một số tình huống, bạn có thể cung cấp một instance đã tồn tại bằng **Bindable.ofInstance(...)**.

Ví dụ một JavaBean:

~~~java
package com.example.binder;

import java.time.Duration;

public class MutableClientOptions {

    private String name = "default";
    private Duration timeout = Duration.ofSeconds(5);

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public Duration getTimeout() {
        return timeout;
    }

    public void setTimeout(Duration timeout) {
        this.timeout = timeout;
    }
}
~~~

Cấu hình:

~~~properties
integration.mutable-client.name=remote-client
integration.mutable-client.timeout=3s
~~~

Binder:

~~~java
MutableClientOptions existing = new MutableClientOptions();

MutableClientOptions result = Binder.get(environment)
        .bind("integration.mutable-client",
                Bindable.ofInstance(existing))
        .orElse(existing);
~~~

Cách này thể hiện ý định bind vào một target có giá trị ban đầu; những property không được cung cấp có thể giữ default của instance tùy cơ chế và loại object.

**Không dùng kiểu mutable shared instance trong nhiều thread mà không xem xét đồng bộ.** Nếu đây là cấu hình của một component, thường tốt hơn nên bind lúc khởi tạo thành một object riêng, hoặc dùng configuration properties bean đúng lifecycle.

## 13. bindOrCreate khác bind như thế nào?

Binder cung cấp các API **bindOrCreate(...)**. Mục đích là:

- Bind từ nguồn cấu hình khi có giá trị.
- Nếu kết quả bind là null, cố tạo một instance mới của target type.

Ví dụ với một JavaBean có constructor không tham số:

~~~java
MutableClientOptions options = Binder.get(environment)
        .bindOrCreate("integration.mutable-client",
                MutableClientOptions.class);
~~~

Tuy nhiên, **bindOrCreate không có nghĩa mọi target type đều có thể được tạo rỗng**. Một record bắt buộc các constructor parameters, hay một class không có constructor phù hợp, có thể không có cách tạo instance khi prefix trống.

Phân biệt ba ý định:

~~~text
bind(...).orElseThrow():
    Phải có cấu hình; nếu không bound, coi là lỗi.

bind(...).orElse(fallback):
    Tùy chọn; nếu không bound, dùng fallback đã chuẩn bị.

bindOrCreate(...):
    Cố tạo object khi không có dữ liệu để bind,
    phụ thuộc khả năng khởi tạo của target type.
~~~

Không chọn **bindOrCreate** chỉ để bỏ qua cấu hình bắt buộc. Nếu URL hay token là required, hãy dùng cơ chế fail-fast hoặc validation thích hợp.

## 14. BindHandler: mở rộng pipeline binding

API Binder có overload:

~~~java
binder.bind(
        "integration.payment",
        Bindable.of(PaymentSettings.class),
        handler);
~~~

Trong đó **handler** là một **BindHandler**. Nó cho phép can thiệp hoặc quan sát những giai đoạn của quá trình binding theo API của Spring Boot, chẳng hạn trước/sau bind, lỗi hoặc validation tùy handler.

Một số nhu cầu:

- Kiểm tra các trường bắt buộc theo quy tắc riêng.
- Thu thập thông tin phục vụ chẩn đoán.
- Áp dụng chính sách xử lý lỗi có kiểm soát.
- Kết hợp cơ chế validation khi bind thủ công.
- Kiểm tra property chưa được tiêu thụ trong những tình huống cần strict binding.

**Đây là phần nâng cao.** Đừng gắn một handler tùy ý vào mọi lời gọi Binder khi chỉ cần đọc cấu hình thông thường. Hãy hiểu rõ lifecycle, error semantics và phạm vi của handler trước khi sử dụng.

Một lỗi thiết kế hay gặp là cố biến BindHandler thành service thực hiện HTTP/DB call trong lúc binding. Binding có thể xảy ra rất sớm, và một handler có side effect làm startup khó dự đoán.

### 14.1. @Validated trên class không bảo đảm Binder thủ công tự kiểm tra

Khi Spring Boot quản lý một **@ConfigurationProperties bean** có **@Validated**, hạ tầng Boot thường gắn bước validation phù hợp khi bind bean đó.

Ngược lại:

~~~java
Binder.get(environment)
        .bind("integration.payment",
                Bindable.of(PaymentSettings.class));
~~~

là một lời gọi Binder thủ công. **Không nên mặc nhiên coi nó tự động chạy toàn bộ validation của một @ConfigurationProperties bean chỉ vì target class có @Validated**. Nếu cần validation trong nhánh thủ công, hãy tích hợp một **BindHandler** phù hợp hoặc chạy **jakarta.validation.Validator** trên object đã bind.

Ví dụ kiểm tra sau bind:

~~~java
PaymentSettings settings = binder
        .bind("integration.payment",
                Bindable.of(PaymentSettings.class))
        .orElseThrow();

Set<ConstraintViolation<PaymentSettings>> violations =
        jakartaValidator.validate(settings);

if (!violations.isEmpty()) {
    throw new IllegalArgumentException(
            "Invalid integration.payment configuration");
}
~~~

Ví dụ này giả định **jakartaValidator** đã được cung cấp từ hạ tầng Bean Validation và target type có khai báo constraint. Không log toàn bộ giá trị cấu hình vì có thể chứa secret.

## 15. Thêm validation thực tế cho đối tượng bound

Một model khác có các ràng buộc đơn trường và quan hệ:

~~~java
package com.example.binder;

import java.net.URI;
import java.time.Duration;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.AssertTrue;

public record ValidatedPaymentSettings(
        @NotNull URI baseUrl,
        @NotNull Duration connectTimeout,
        @NotNull Duration requestTimeout) {

    @AssertTrue(
        message = "request-timeout must exceed connect-timeout")
    public boolean isTimeoutOrderValid() {
        if (connectTimeout == null || requestTimeout == null) {
            return true;
        }
        return requestTimeout.compareTo(connectTimeout) > 0;
    }
}
~~~

Bind và kiểm tra:

~~~java
ValidatedPaymentSettings settings = Binder.get(environment)
        .bind("integration.payment",
                Bindable.of(ValidatedPaymentSettings.class))
        .orElseThrow();

Set<ConstraintViolation<ValidatedPaymentSettings>> errors =
        validator.validate(settings);

if (!errors.isEmpty()) {
    throw new IllegalStateException(
            "Configuration validation failed");
}
~~~

Trong đoạn trên, **validator** là một **jakarta.validation.Validator** được tiêm vào component sử dụng, chẳng hạn qua constructor injection.

Cần dependency **spring-boot-starter-validation** hoặc một Bean Validation implementation tương thích.

Nếu **connectTimeout = 8s** và **requestTimeout = 3s**, cả hai Duration đúng kiểu, nhưng quan hệ sai và validator sẽ phát hiện. Điều này tách rõ **conversion** khỏi **business-level validation**.

### 15.1. Kiểm tra nested object

Nếu target chứa nested object với constraint riêng, đặt **@Valid** ở thuộc tính nested để Jakarta Bean Validation đi sâu vào các ràng buộc bên trong. **Binder tạo object**; **validator kiểm tra hợp đồng**. Đó là hai trách nhiệm khác nhau.

## 16. Nguồn dữ liệu vẫn tuân theo ưu tiên Spring Boot

**Binder.get(environment)** không thay đổi thứ tự ưu tiên của Spring Boot.

Giả sử:

**application.yml**:

~~~yaml
integration:
  payment:
    connect-timeout: 2s
~~~

**application-prod.yml**:

~~~yaml
integration:
  payment:
    connect-timeout: 4s
~~~

Biến môi trường:

~~~text
INTEGRATION_PAYMENT_CONNECTTIMEOUT=6s
~~~

Tham số command-line:

~~~text
--integration.payment.connect-timeout=8s
~~~

Trong một lượt chạy thông thường khi profile **prod** hoạt động và tất cả nguồn trên có mặt, command-line có độ ưu tiên cao hơn những nguồn trên, nên Binder có thể nhận **8s**.

Không có chuyện **Binder.bind(...)** chỉ đọc YAML trong JAR. Nó bind trên Environment đã được Spring Boot thiết lập cho application context.

### 16.1. Biến môi trường và canonical naming

Tên canonical:

~~~text
integration.payment.connect-timeout
integration.payment.retry.max-attempts
~~~

Tên biến môi trường:

~~~text
INTEGRATION_PAYMENT_CONNECTTIMEOUT
INTEGRATION_PAYMENT_RETRY_MAXATTEMPTS
~~~

Quy tắc:

1. Thay dấu chấm **.** bằng dấu dưới **_**.
2. Bỏ dấu gạch ngang **-**.
3. Viết hoa.

Không tự tách **connect-timeout** thành **CONNECT_TIMEOUT** nếu mục tiêu là tạo đúng tên canonical theo Spring Boot. Quy tắc relaxed binding này cũng có ích khi lấy Binder trực tiếp.

## 17. Placeholder có thể được giải quyết trong quá trình binding

Config Data:

~~~properties
integration.payment.base-url=${PAYMENT_GATEWAY_URL:https://sandbox.example.invalid}
integration.payment.connect-timeout=${payment.timeout:2s}
~~~

Khi Binder đọc những property này qua Environment, placeholder có thể được giải quyết theo nguồn phù hợp trước khi chuyển kiểu.

Ví dụ:

~~~bash
java -jar app.jar \
  --payment.timeout=5s
~~~

thì **connectTimeout** có thể trở thành Duration 5 giây.

**Lưu ý về tên placeholder:** trong ứng dụng mới, nên ưu tiên key canonical như **payment.gateway-url** hoặc **payment.timeout**, rồi cấp biến môi trường tương ứng theo quy tắc Spring Boot. Dùng tên biến môi trường viết hoa trực tiếp trong placeholder là một cách tham chiếu cụ thể, nhưng nên ghi rõ tính phụ thuộc vào nguồn đó nếu áp dụng.

### 17.1. Không nhầm resolve runtime với resource filtering

Placeholder **${...}** trong Config Data được xử lý trong hệ thống PropertyResolver/Environment lúc ứng dụng sử dụng cấu hình. Nó không đồng nghĩa Maven hoặc Gradle đã thay nội dung tài nguyên khi build.

Một **Binder thủ công** vẫn hoạt động trên các nguồn có mặt ở runtime, không sửa file YAML hoặc JAR.

## 18. Binding tại thời điểm nào và có tự cập nhật không?

Khi gọi:

~~~java
PaymentSettings snapshot = Binder.get(environment)
        .bind("integration.payment",
                Bindable.of(PaymentSettings.class))
        .orElseThrow();
~~~

bạn nhận một object chứa **giá trị được bind ở lần gọi đó**.

Nếu lời gọi nằm trong method service được chạy nhiều lần, code có thể thực hiện binding nhiều lần. Nhưng điều này **không bảo đảm Environment tự nạp lại biến môi trường hoặc file YAML từ ổ đĩa**.

Phân biệt:

- Environment là tập nguồn cấu hình đang được ứng dụng sử dụng.
- Binder đọc từ Environment theo trạng thái nguồn tại thời điểm binding.
- Object **PaymentSettings** đã được tạo không tự biến đổi nếu nguồn thay đổi.
- Thay đổi biến môi trường trong một shell khác không tự sửa biến môi trường của process Java đang chạy.
- Sửa file application.yml ngoài JAR cũng không tự khởi động cơ chế hot reload trong Spring Boot thông thường.

Nếu hệ thống cần dynamic configuration, cần một cơ chế cập nhật PropertySource và lifecycle refresh rõ ràng. Không dùng **Binder.get(environment)** như giải pháp theo dõi thay đổi cấu hình tự động.

### 18.1. Tính toán chi phí bind

Việc bind nhiều field, nested object và collection có chi phí CPU/allocations. Với một configuration group ổn định, nên bind **một lần ở lifecycle phù hợp** và inject object vào service.

Không nên bind lại toàn bộ cấu hình trong mỗi request HTTP chỉ vì API cho phép. Ví dụ REST controller ở mục 5 cố ý đọc mỗi lần để quan sát cơ chế; production code thường nên dùng bean cấu hình hoặc cache/snapshot được quản lý hợp lý.

## 19. Chọn giữa Environment.getProperty, Binder và @ConfigurationProperties

| Nhu cầu | Cách thích hợp |
| --- | --- |
| Đọc một key như **server.port** | **Environment.getProperty(...)** |
| Bind một object ngay tại thời điểm code chủ động chọn | **Binder.get(environment).bind(...)** |
| Bind danh sách/Map không biết trước số phần tử | **Binder** với **Bindable.listOf/mapOf** |
| Một module có cấu hình ổn định, cần dependency injection | **@ConfigurationProperties** |
| Cần validation tự động khi tạo configuration bean | **@ConfigurationProperties** với **@Validated** và validation implementation |
| Cần type generic lồng nhau | **Bindable.of(ResolvableType)** |
| Cần một object có defaults và setters đã tồn tại | **Bindable.ofInstance(...)** khi phù hợp |
| Cần chính sách xử lý lỗi/validation thủ công | **BindHandler** hoặc validate sau bind |
| Cần đọc một prefix khác nhau theo context | **Binder** với danh sách prefix được kiểm soát |

Đừng biến mọi property đơn thành một class chỉ vì Binder hỗ trợ. Ngược lại, đừng dùng mười lời gọi getProperty rời rạc để mô phỏng một object có nhiều field.

### 19.1. @ConfigurationProperties dùng Binder nhưng không giống Binder thủ công

Khai báo:

~~~java
@ConfigurationProperties(prefix = "integration.payment")
public record PaymentProperties(
        URI baseUrl,
        Duration connectTimeout) {
}
~~~

và đăng ký type bằng **@ConfigurationPropertiesScan** hoặc **@EnableConfigurationProperties** sẽ để Boot quản lý bean và các bước liên quan.

Gọi Binder thủ công không tự làm những việc sau:

- Tạo một singleton bean có thể inject ở mọi nơi.
- Đăng ký type vào container.
- Tạo configuration metadata cho một class không được annotation processor nhận diện theo cách tương ứng.
- Tự động áp dụng toàn bộ validation lifecycle cho target chỉ từ chữ ký **bind(...)**.

Với cấu hình cố định của một subsystem, **@ConfigurationProperties** thường là giải pháp dễ bảo trì hơn. Binder thủ công thích hợp khi có một lý do về hạ tầng/lifecycle rõ ràng.

## 20. Xử lý prefix tùy chọn và lỗi thiếu cấu hình

Một ứng dụng có thể hỗ trợ một integration tùy chọn:

~~~yaml
integrations:
  email:
    enabled: false
~~~

Đọc flag:

~~~java
boolean enabled = Binder.get(environment)
        .bind("integrations.email.enabled",
                Bindable.of(Boolean.class))
        .orElse(false);
~~~

Nếu flag tắt, ứng dụng có thể không cần bind thêm endpoint email. Nếu bật, bind các property cần thiết và fail-fast khi thiếu.

~~~java
if (enabled) {
    EmailSettings email = binder
            .bind("integrations.email",
                    Bindable.of(EmailSettings.class))
            .orElseThrow(() -> new IllegalStateException(
                    "integrations.email is required"));
}
~~~

Ví dụ trên chỉ minh họa flow; **EmailSettings** cần được khai báo thành model riêng trong ứng dụng thực tế.

**Quan trọng:** khi prefix có một vài property nhưng thiếu field quan trọng, kết quả bind vẫn có thể được tạo với các field null hoặc default. **orElseThrow() chỉ xử lý trường hợp không bound**, không mặc định chứng minh mọi field required đều hiện diện. Cần validation.

## 21. Test Binder trực tiếp mà không chạy web server

**ApplicationContextRunner** từ **spring-boot-test** cho phép tạo một context nhỏ và cấp những property cần kiểm thử. Khi bài test chỉ quan tâm Binder, không cần khởi tạo toàn bộ web app hoặc kết nối database.

Ví dụ JUnit 5 và AssertJ:

~~~java
package com.example.binder;

import java.net.URI;
import java.time.Duration;
import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.bind.Bindable;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

class ManualBinderTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner();

    @Test
    void bindsNestedConfigurationFromEnvironment() {
        runner.withPropertyValues(
                "integration.payment.base-url=https://test.example.invalid",
                "integration.payment.connect-timeout=500ms",
                "integration.payment.request-timeout=5s",
                "integration.payment.retry.enabled=true",
                "integration.payment.retry.max-attempts=4",
                "integration.payment.retry.initial-delay=100ms",
                "integration.payment.regions[0]=asia",
                "integration.payment.regions[1]=europe",
                "integration.payment.headers.client-id=test"
        ).run(context -> {
            PaymentSettings settings =
                    Binder.get(context.getEnvironment())
                            .bind("integration.payment",
                                    Bindable.of(PaymentSettings.class))
                            .orElseThrow();

            assertThat(settings.baseUrl()).isEqualTo(
                    URI.create("https://test.example.invalid"));
            assertThat(settings.connectTimeout()).isEqualTo(
                    Duration.ofMillis(500));
            assertThat(settings.requestTimeout()).isEqualTo(
                    Duration.ofSeconds(5));
            assertThat(settings.retry().maxAttempts()).isEqualTo(4);
            assertThat(settings.regions())
                    .containsExactly("asia", "europe");
            assertThat(settings.headers().get("client-id"))
                    .isEqualTo("test");
        });
    }
}
~~~

Vì không tạo **PaymentSettings** qua bean registration, test này minh họa đúng con đường **Binder.get(context.getEnvironment())**.

Trong dự án thực tế, cần dependency **spring-boot-starter-test**. Test không yêu cầu endpoint mạng thật vì **URI** chỉ là dữ liệu đã được chuyển kiểu.

### 21.1. Test prefix không tồn tại

~~~java
@Test
void missingPrefixReturnsUnbound() {
    runner.run(context -> {
        boolean found =
                Binder.get(context.getEnvironment())
                        .bind("missing.integration",
                                Bindable.of(PaymentSettings.class))
                        .isBound();

        assertThat(found).isFalse();
    });
}
~~~

Trường hợp này khác với một key hiện diện nhưng có giá trị không thể parse.

### 21.2. Test conversion failure

Có thể truyền property thời gian sai:

~~~text
integration.payment.connect-timeout=not-a-duration
~~~

Khi Binder cố tạo một Duration từ đó, thông thường binding sẽ thất bại. Trong test, có thể assert thrown binding/conversion exception. Đừng nhầm lỗi này với kết quả **unbound**, vì property có tồn tại nhưng không chuyển sang kiểu đích.

## 22. Những lỗi hay gặp

### Lỗi 1: cho rằng Binder.get(environment) tự đăng ký bean

Nó tạo Binder. Object kết quả không tự trở thành Spring bean. Nếu muốn singleton injectable, hãy dùng @ConfigurationProperties hoặc tự đăng ký bean hợp lý.

### Lỗi 2: gọi bind với sai prefix

Nhóm YAML có **integration.payment**, nhưng code dùng **integrations.payment**; kết quả có thể unbound. Hãy so sánh đúng đường property canonical.

### Lỗi 3: bind một List thành Class phần tử

Nếu đích là List<Endpoint>, dùng **Bindable.listOf(Endpoint.class)**, không dùng **Bindable.of(Endpoint.class)** ở prefix của cả danh sách.

### Lỗi 4: quên generic type của Map

**Map<String, Integer>** và **Map<String, Endpoint>** có kiểu giá trị khác nhau. Dùng **Bindable.mapOf** hoặc **ResolvableType** để Binder biết rõ kiểu đích.

### Lỗi 5: coi orElseThrow là validation đầy đủ

Kết quả bound không bảo đảm mọi field bắt buộc có giá trị hoặc quan hệ giữa nhiều field hợp lệ. Dùng Bean Validation hoặc logic kiểm tra phù hợp.

### Lỗi 6: nghĩ bind lại sẽ tự refresh file

Binder đọc từ Environment. Nếu nguồn bên trong Environment chưa thay đổi, bind lại không tạo ra dữ liệu mới.

### Lỗi 7: lặp bind trong mỗi HTTP request

Với cấu hình ít thay đổi, repeated binding tạo thêm allocations và logic khó kiểm soát. Bind một lần vào configuration object và sử dụng lại.

### Lỗi 8: bỏ qua lỗi chuyển kiểu

Nếu **timeout=wrong**, đừng dùng fallback để âm thầm coi cấu hình đúng. Cần phân biệt giá trị thiếu với giá trị sai.

### Lỗi 9: dùng tên env sai chuẩn

**integration.payment.connect-timeout** → **INTEGRATION_PAYMENT_CONNECTTIMEOUT**; không tự thêm dấu dưới cho từng từ trong kebab-case.

### Lỗi 10: quên List replacement

Khi nhiều nguồn định nghĩa một List, nguồn ưu tiên cao hơn thay List của nguồn thấp hơn. Không mặc định merge từng phần tử.

### Lỗi 11: để người dùng chọn prefix bất kỳ

Một endpoint nhận tên prefix tự do có thể làm lộ cấu hình nội bộ. Whitelist các prefix được phép và không trả secret ra response.

### Lỗi 12: log toàn bộ object đã bind

Một cấu hình có thể chứa username, password, token hoặc secret. Không tự động in **toString()** của toàn bộ record trong production.

### Lỗi 13: thay thế Environment bằng binder mới không đầy đủ

Nếu tự tạo một **new Binder(...)** chỉ từ một MapPropertySource, bạn có thể bỏ lỡ placeholder, conversion hoặc các nguồn cấu hình khác. Khi muốn bind theo Environment ứng dụng đang chạy, ưu tiên **Binder.get(environment)**.

### Lỗi 14: dùng bindOrCreate cho type không thể tạo khi thiếu dữ liệu

Một record có required constructor parameters không nhất thiết tạo được object khi không có property; cần kiểm tra type đích và chính sách default.

### Lỗi 15: coi BindHandler là nơi chứa nghiệp vụ phụ thuộc hạ tầng

Binding cần ổn định và dễ dự đoán. Không chạy HTTP hoặc database query trong BindHandler chỉ để xác minh một URL có đang hoạt động.

## 23. Bài thực hành

### Bài A — lấy Binder và bind một record

1. Tạo **application.yml** với nhánh **integration.payment**.
2. Tạo record **PaymentSettings** có URI, Duration và Retry.
3. Inject **Environment** vào một service.
4. Gọi **Binder.get(environment)**.
5. Bind theo prefix và in các trường không nhạy cảm.
6. Thay một giá trị qua command-line, khởi động lại và đọc kết quả.

**Cần hiểu:** cùng Java type nhưng giá trị lấy từ Environment được cấu hình ở runtime.

### Bài B — so sánh với Environment.getProperty

1. Đọc **integration.payment.connect-timeout** qua **environment.getProperty**.
2. Bind cả **integration.payment** qua Binder.
3. So sánh String **2s** với **Duration.ofSeconds(2)**.
4. Thêm nested Retry và quan sát chênh lệch về số lời gọi cần thiết.

**Cần hiểu:** Environment thuận tiện cho key đơn; Binder giúp tạo object có cấu trúc.

### Bài C — thử prefix không tồn tại

1. Bind **missing.integration**.
2. Gọi **isBound()**.
3. Thử **orElse(...)** với một fallback hợp lệ.
4. Thử **orElseThrow(...)** để phát hiện thiếu cấu hình bắt buộc.

**Cần hiểu:** unbound khác conversion failure và validation failure.

### Bài D — bind List

1. Khai báo hai endpoints trong YAML.
2. Gọi **Bindable.listOf(Endpoint.class)**.
3. Kiểm tra thứ tự các phần tử.
4. Cấp danh sách mới qua nguồn ưu tiên cao hơn rồi khởi động lại.

**Cần hiểu:** Binder dựng cả List, và nguồn ưu tiên cao hơn có thể thay toàn bộ List.

### Bài E — bind Map

1. Tạo **integration.limits** với các key vùng.
2. Dùng **Bindable.mapOf(String.class, Integer.class)**.
3. Đọc key theo tên.
4. Thử key có dấu **/** bằng bracket notation.

**Cần hiểu:** Map binding bảo tồn cấu trúc key khi dùng cú pháp phù hợp.

### Bài F — thử validation thủ công

1. Tạo **ValidatedPaymentSettings** với @NotNull và @AssertTrue.
2. Bind bằng Binder.get(environment).
3. Gọi **jakarta.validation.Validator.validate(...)**.
4. Thử request-timeout nhỏ hơn connect-timeout.
5. Phân biệt conversion failure với constraint violation.

**Cần hiểu:** Binder thủ công cần chính sách validation rõ ràng.

### Bài G — chuyển sang @ConfigurationProperties bean

1. Lấy model PaymentSettings đã dùng.
2. Tạo một type có **@ConfigurationProperties(prefix = "integration.payment")**.
3. Đăng ký bằng **@ConfigurationPropertiesScan** hoặc **@EnableConfigurationProperties**.
4. Inject object vào service thay vì gọi Binder mỗi request.
5. So sánh lifecycle và validation.

**Cần hiểu:** Binder và configuration properties không đối lập; @ConfigurationProperties dùng hạ tầng binding để tích hợp với container.

## 24. Checklist trước khi dùng Binder thủ công

Trước khi triển khai một lời gọi **Binder.get(environment)**, hãy xác định:

1. Prefix là gì và có dùng lowercase kebab-case không?
2. Các property cần thiết đã thực sự được nạp vào Environment chưa?
3. Target là class, record, List, Map hay generic type lồng nhau?
4. Có cần **Bindable.of**, **listOf**, **mapOf** hoặc **ResolvableType**?
5. Khi không có prefix, bạn muốn fallback hay fail-fast?
6. Khi có property sai kiểu, có xử lý lỗi chuyển đổi đúng không?
7. Trường required có validation không?
8. Có nested object hoặc collection cần kiểm tra không?
9. Có cần **BindHandler** hay validation sau bind?
10. Khi nào lời gọi bind diễn ra và có bị gọi lặp quá nhiều không?
11. Binder lấy Environment của ApplicationContext nào?
12. Cấu hình có thể bị override từ env/CLI/profile không?
13. Có secret không và chúng có bị log/đưa ra API không?
14. Prefix có được chọn từ input không đáng tin cậy không?
15. Nếu cần configuration bean sống lâu dài, có nên dùng **@ConfigurationProperties** thay thế?

## 25. Tổng kết

- **Binder.get(environment)** tạo một Binder dựa trên Environment của ứng dụng.
- **bind(prefix, Bindable.of(Type.class))** liên kết các property của một nhánh vào object Java.
- **BindResult** cho phép phân biệt có bind được dữ liệu hay không và xử lý thiếu cấu hình bằng **isBound**, **orElse**, **orElseThrow**.
- **Bindable.listOf** và **Bindable.mapOf** hỗ trợ các collection có generic type.
- **ResolvableType** giúp biểu diễn cấu trúc generic phức tạp hơn.
- **Bindable.ofInstance** phù hợp khi có một mutable instance với giá trị mặc định cần xét trong binding.
- **bindOrCreate** có thể tạo một target object khi không bind được, nếu type cho phép.
- **BindHandler** là điểm mở rộng cho pipeline binding; không cần sử dụng cho các trường hợp đơn giản.
- Binder tuân theo nguồn cấu hình và thứ tự ưu tiên của Environment; nó không tự quét hoặc refresh file.
- Binding thủ công không tự đăng ký singleton bean hay tự đảm bảo mọi validation của cơ chế **@ConfigurationProperties**.
- Với cấu hình ổn định của một subsystem, nên ưu tiên **@ConfigurationProperties**; với binding động hoặc infrastructure code, **Binder** là công cụ phù hợp.

## Tài liệu tham khảo chính thức

- Spring Boot 3.3 — **Binder API**: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/bind/Binder.html
- Spring Boot 3.3 — **Bindable API**: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/bind/Bindable.html
- Spring Boot 3.3 — **BindResult API**: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/bind/BindResult.html
- Spring Boot 3.3 — **Externalized Configuration**, Type-safe Configuration Properties và Relaxed Binding: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- Spring Framework — **Environment** và **PropertySource**: https://docs.spring.io/spring-framework/reference/core/beans/environment.html
