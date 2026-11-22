# Liên kết linh hoạt (relaxed binding) và tên thuộc tính chuẩn trong Spring Boot 3.3

## 1. Mục tiêu

Spring Boot 3.3 thường nhận cấu hình từ nhiều nguồn cùng lúc: file `application.properties`, `application.yaml`, biến môi trường của hệ điều hành, Java system properties, command-line arguments và các nguồn Config Data khác. Các nguồn này không luôn có cùng quy ước đặt tên.

Ví dụ cùng một thuộc tính Java:

```java
private int maxRetries;
```

có thể được cấu hình bằng các cách viết:

```properties
app.max-retries=3
app.maxRetries=3
app.max_retries=3
```

hoặc khi truyền qua environment variable:

```bash
APP_MAXRETRIES=3
```

Đây là khả năng **relaxed binding** của Spring Boot: Binder nhận dạng các biến thể tên property tương đương và ánh xạ chúng vào cùng một JavaBean property hoặc constructor parameter khi dùng `@ConfigurationProperties`.

**Lưu ý quan trọng:** relaxed binding là một cơ chế **ánh xạ tên**, không có nghĩa mọi chuỗi tên với bất kỳ dấu phân cách nào cũng tự động tương đương; không có nghĩa các `Map` key luôn được chuẩn hóa mà không mất thông tin; cũng không xóa bỏ **thứ tự ưu tiên PropertySource** khi hai nguồn cùng cung cấp một thuộc tính.

Mục tiêu sau bài này:

- Nhận biết **tên thuộc tính chuẩn** (canonical property name) theo kiểu chữ thường và dấu gạch nối `-`.
- Biết đổi tên property giữa Java camelCase, .properties/YAML và environment variables.
- Phân biệt relaxed binding cho `@ConfigurationProperties` với truy cập bằng `@Value` hoặc `Environment`.
- Hiểu ngoại lệ đối với **List index**, **Map key**, chữ hoa/thường và ký tự đặc biệt.
- Biết cách tổ chức ví dụ, kiểm thử và xử lý lỗi tên khóa không bind được.

## 2. Canonical property name là gì?

Trong ngữ cảnh Spring Boot configuration properties, **canonical form** khuyến nghị là tên dùng:

1. Chữ cái **thường**.
2. Các từ trong cùng một thành phần được nối bằng **dấu gạch nối `-`** (*kebab-case*).
3. Dấu chấm `.` để phân chia các cấp cấu hình.
4. Chỉ số `[0]`, `[1]`… khi biểu diễn phần tử collection ở dạng property path.

Ví dụ:

```properties
app.name=Catalog
app.max-retries=3
app.client.connect-timeout=5s
app.security.require-https=true
app.endpoints[0].base-url=https://a.example.test
app.endpoints[1].base-url=https://b.example.test
```

Tên chuẩn tương ứng:

| Canonical property path | Phân cấp và ý nghĩa |
| --- | --- |
| `app.name` | `app` → `name` |
| `app.max-retries` | `app` → `maxRetries` |
| `app.client.connect-timeout` | `app` → `client` → `connectTimeout` |
| `app.security.require-https` | `app` → `security` → `requireHttps` |
| `app.endpoints[0].base-url` | `app` → phần tử 0 của `endpoints` → `baseUrl` |

Trong Java thường dùng **camelCase** cho property name (`maxRetries`, `connectTimeout`, `requireHttps`), còn trong file cấu hình nên dùng tên chuẩn **kebab-case** (`max-retries`, `connect-timeout`, `require-https`).

### Prefix cũng phải theo dạng chuẩn

Nếu khai báo:

```java
@ConfigurationProperties(prefix = "catalog.http-client")
public class HttpClientProperties {
    // ...
}
```

thì `catalog.http-client` là prefix theo dạng canonical. Không nên khai báo prefix thành `catalog.httpClient` hoặc `Catalog.Http_Client`. Spring Boot yêu cầu prefix của `@ConfigurationProperties` tuân theo dạng kebab-case phù hợp.

Đối với một prefix nhiều cấp:

```java
@ConfigurationProperties(prefix = "acme.checkout-service")
```

các property con có thể là:

```properties
acme.checkout-service.enabled=true
acme.checkout-service.request-timeout=3s
```

**Quy tắc đặt tên để viết tài liệu:** luôn dùng canonical form, ngay cả khi Binder vẫn chấp nhận một số dạng viết khác. Điều này giúp property name nhất quán giữa README, `@Value`, metadata cấu hình, các file profile và script triển khai.

## 3. Cơ chế relaxed binding ở `@ConfigurationProperties`

Spring Boot Binder nhận các property từ `Environment` và gán vào target Java type. Với một class:

```java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public class AppProperties {

    private String displayName;
    private int maxRetries;
    private boolean auditEnabled;

    public String getDisplayName() { return displayName; }
    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }

    public int getMaxRetries() { return maxRetries; }
    public void setMaxRetries(int maxRetries) {
        this.maxRetries = maxRetries;
    }

    public boolean isAuditEnabled() { return auditEnabled; }
    public void setAuditEnabled(boolean auditEnabled) {
        this.auditEnabled = auditEnabled;
    }
}
```

Spring Boot liên kết các khóa:

```properties
app.display-name=Catalog API
app.max-retries=4
app.audit-enabled=true
```

vào `displayName`, `maxRetries`, `auditEnabled`.

Nhưng cũng có thể nhận dạng các cách viết mang cùng ý nghĩa như:

```properties
app.displayName=Catalog API
app.maxRetries=4
app.auditEnabled=true
```

hoặc:

```properties
app.display_name=Catalog API
app.max_retries=4
app.audit_enabled=true
```

Ba block ví dụ là **ba phương án thay thế**, không phải ba bộ cấu hình nên khai báo cùng lúc. Nếu khai báo nhiều biến thể cho cùng một target trong cùng/khác PropertySource, người đọc khó xác định giá trị nào có hiệu lực; chuẩn hóa về một kiểu tên duy nhất để tránh mơ hồ.

### Không cần dùng cùng kiểu chữ với tên Java

Tên JavaBean property được xác định theo getter/setter hoặc constructor parameter (với constructor binding). Binder không yêu cầu file YAML viết `displayName` chỉ vì class có `getDisplayName()`; `display-name` vẫn là lựa chọn chuẩn.

### Relaxed binding khác với type conversion

Hai cơ chế liên quan nhưng độc lập:

- **Tên:** `app.connect-timeout` được nhận dạng là property Java `connectTimeout`.
- **Giá trị:** chuỗi `5s` được chuyển thành `Duration` nếu Java target là `Duration`.

Ví dụ:

```java
private Duration connectTimeout = Duration.ofSeconds(2);

public Duration getConnectTimeout() {
    return connectTimeout;
}

public void setConnectTimeout(Duration connectTimeout) {
    this.connectTimeout = connectTimeout;
}
```

```properties
app.connect-timeout=5s
```

Đường bind gồm **nhận dạng tên** và **chuyển đổi giá trị**, không chỉ đơn thuần đổi dấu gạch nối thành camelCase.

## 4. Những dạng tên được chấp nhận theo nguồn cấu hình

Các cách biểu diễn cơ bản trong Spring Boot 3.3:

| Nguồn | Những kiểu tên thường được Binder hỗ trợ | Ví dụ cho Java `firstName` |
| --- | --- | --- |
| `application.properties` | Kebab-case, camelCase, underscore | `person.first-name`, `person.firstName`, `person.first_name` |
| `application.yaml` / `.yml` | Kebab-case, camelCase, underscore | `person:` → `first-name:` / `firstName:` / `first_name:` |
| Java system properties (`-D`) | Kebab-case, camelCase, underscore | `-Dperson.first-name=An` |
| OS environment variables | Uppercase, underscore, bỏ dấu gạch nối | `PERSON_FIRSTNAME=An` |

Bảng này nói về tên được liên kết qua `@ConfigurationProperties`; không nên suy rộng rằng mọi API đọc raw key đều xử lý biến thể tương tự trong mọi hoàn cảnh.

### 4.1. .properties

```properties
app.http-client.connect-timeout=5s
```

Java target:

```java
private HttpClient httpClient;
public static class HttpClient {
    private Duration connectTimeout;
    // getters/setters
}
```

Đường property chuẩn là `app.http-client.connect-timeout`; cả dấu chấm lẫn dấu gạch nối đều có ý nghĩa: dấu chấm phân cấp, dấu gạch nối ngăn từ trong một tên Java property.

### 4.2. YAML

```yaml
app:
  http-client:
    connect-timeout: 5s
    retry-count: 3
```

Spring Boot flatten YAML thành các property paths thích hợp, ví dụ:

```text
app.http-client.connect-timeout
app.http-client.retry-count
```

YAML có thể dùng camelCase, nhưng viết kebab-case giúp mọi ví dụ thống nhất với canonical form.

### 4.3. Java system properties

```bash
java -Dapp.http-client.connect-timeout=5s -jar myapp.jar
```

System property giữ cách ghi có dấu chấm và gạch nối; Binder vẫn dùng relaxed binding để ánh xạ sang `httpClient.connectTimeout`.

### 4.4. Command-line options

```bash
java -jar myapp.jar \
  --app.http-client.connect-timeout=5s \
  --app.http-client.retry-count=3
```

Các đối số dạng `--key=value` được Spring Boot thêm vào `Environment` theo mặc định nếu chúng được truyền cho `SpringApplication.run(args)`. Command line là một PropertySource riêng có mức ưu tiên cao trong cấu hình thông thường.

Nếu ứng dụng chủ động tắt `setAddCommandLineProperties(false)` thì không nên mặc định các option đó sẽ được xử lý như Spring property.

## 5. Quy tắc chuyển sang biến môi trường OS

Một trong những điểm dễ sai nhất là chuyển canonical property name sang environment variable. Spring Boot 3.3 mô tả ba bước:

1. **Thay dấu chấm `.` bằng dấu gạch dưới `_`**.
2. **Bỏ dấu gạch nối `-`**, không thay nó bằng `_`.
3. **Chuyển toàn bộ thành chữ hoa**.

Ví dụ:

```text
spring.main.log-startup-info
        ↓ thay dấu chấm
spring_main_log-startup-info
        ↓ bỏ dấu gạch nối
spring_main_logstartupinfo
        ↓ viết hoa
SPRING_MAIN_LOGSTARTUPINFO
```

Bảng chuyển đổi:

| Canonical property | Biến môi trường chuẩn |
| --- | --- |
| `app.name` | `APP_NAME` |
| `app.display-name` | `APP_DISPLAYNAME` |
| `app.max-retries` | `APP_MAXRETRIES` |
| `app.http-client.connect-timeout` | `APP_HTTPCLIENT_CONNECTTIMEOUT` |
| `spring.main.log-startup-info` | `SPRING_MAIN_LOGSTARTUPINFO` |
| `spring.config.additional-location` | `SPRING_CONFIG_ADDITIONALLOCATION` |
| `spring.profiles.active` | `SPRING_PROFILES_ACTIVE` |
| `management.endpoints.web.exposure.include` | `MANAGEMENT_ENDPOINTS_WEB_EXPOSURE_INCLUDE` |

**Cảnh báo:** `APP_MAX_RETRIES` trông “có vẻ hợp lý” nhưng không phải kết quả chuyển đổi chuẩn của `app.max-retries`. Dấu gạch dưới của environment variable chủ yếu biểu diễn **dấu chấm phân cấp**, còn dấu gạch nối **bị loại bỏ**. Khi đặt tên biến cho Docker/Kubernetes/CI, ưu tiên dùng đúng `APP_MAXRETRIES`.

### Ví dụ môi trường Unix-like

```bash
APP_NAME="Catalog API" \
APP_MAXRETRIES=0 \
APP_HTTPCLIENT_CONNECTTIMEOUT=750ms \
java -jar myapp.jar
```

Với target Java phù hợp, kết quả có thể là:

```text
name = "Catalog API"
maxRetries = 0
httpClient.connectTimeout = 750 ms
```

`0` vẫn là giá trị explicit; relaxed binding không biến số không thành “không khai báo”.

### Docker Compose

```yaml
services:
  catalog:
    image: example/catalog:1.0
    environment:
      APP_NAME: "Catalog API"
      APP_MAXRETRIES: "0"
      APP_HTTPCLIENT_CONNECTTIMEOUT: "750ms"
```

Nên sử dụng dấu nháy cho value môi trường trong YAML để rõ ý định biểu diễn chuỗi. Tên biến phải nằm trong môi trường của **tiến trình Java**, không chỉ tồn tại trong terminal ở nơi khác.

### Kubernetes (minh họa)

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: catalog
spec:
  replicas: 1
  selector:
    matchLabels:
      app: catalog
  template:
    metadata:
      labels:
        app: catalog
    spec:
      containers:
        - name: app
          image: example/catalog:1.0
          env:
            - name: APP_HTTPCLIENT_CONNECTTIMEOUT
              value: "750ms"
            - name: APP_MAXRETRIES
              value: "0"
```

Mỗi cặp `name/value` được cung cấp khi container tạo process, do đó Spring Boot có thể đọc qua OS environment source.

### Biến môi trường và case sensitivity

Tên biến môi trường trên Linux thường phân biệt chữ hoa/chữ thường ở mức OS; nhưng tên chuẩn của Spring Boot dùng chữ hoa. Nếu tạo nhiều tên gần giống chỉ khác case/dấu gạch dưới, có thể dẫn đến hành vi khó dự đoán giữa nền tảng và cách chúng được đưa vào PropertySource. Tốt nhất **không dùng hai biến khác tên chỉ để mô phỏng cùng một property**.

## 6. List/array index trong relaxed binding

Cấu hình collection trong .properties thường viết:

```properties
app.servers[0].host=alpha.example.test
app.servers[0].port=8080
app.servers[1].host=beta.example.test
app.servers[1].port=8081
```

Java target có thể là:

```java
private List<Server> servers;

public static class Server {
    private String host;
    private int port;

    public String getHost() { return host; }
    public void setHost(String host) { this.host = host; }

    public int getPort() { return port; }
    public void setPort(int port) { this.port = port; }
}
```

Dạng YAML tương đương:

```yaml
app:
  servers:
    - host: alpha.example.test
      port: 8080
    - host: beta.example.test
      port: 8081
```

Quy tắc riêng cho environment variable: **chỉ số phải được bao quanh bằng dấu `_`**. Ví dụ tài liệu chính thức dùng:

```text
my.service[0].other -> MY_SERVICE_0_OTHER
```

Áp dụng cho ví dụ trên:

```bash
APP_SERVERS_0_HOST=alpha.example.test
APP_SERVERS_0_PORT=8080
APP_SERVERS_1_HOST=beta.example.test
APP_SERVERS_1_PORT=8081
```

**Không viết** `APP_SERVERS0_HOST` với kỳ vọng chắc chắn Binder sẽ nhận đây là `servers[0].host`. Cấu trúc `_0_` thể hiện rõ vị trí phần tử trong list.

### Index và source precedence

Nếu một nguồn ưu tiên cao hơn định nghĩa một `List`, Spring Boot thường **thay thế toàn bộ List** từ nguồn thấp hơn, không ghép theo index hoặc thuộc tính của từng phần tử. Ví dụ file base có hai `servers`, còn profile dev chỉ có một server, danh sách cuối ở dev chỉ gồm server dev. Điều này là quy tắc binding collection, không phải hệ quả riêng của việc đặt tên.

## 7. Map key không giống JavaBean property name

Đây là ngoại lệ rất quan trọng. **Tên property trong đường dẫn** có thể được relaxed-bind, nhưng **key của Map là dữ liệu ứng dụng**, nhiều khi cần giữ nguyên ký tự.

Giả sử model:

```java
@ConfigurationProperties(prefix = "app")
public class RouteProperties {
    private Map<String, String> routes = new LinkedHashMap<>();

    public Map<String, String> getRoutes() { return routes; }
    public void setRoutes(Map<String, String> routes) {
        this.routes = routes;
    }
}
```

Và cấu hình:

```properties
app.routes.public=frontend
app.routes.internal=backend
```

Binder hiểu `public`, `internal` là **key** của `Map<String,String> routes`, chứ không phải hai JavaBean fields bắt buộc. Nếu một key chứa dấu `/` hoặc ký tự đặc biệt, nó cần cú pháp riêng.

### 7.1. Dùng `[key]` để bảo toàn ký tự đặc biệt

Muốn key thật sự là `/api/v1`:

```properties
app.routes.[/api/v1]=frontend
app.routes.[/admin]=backend
```

Trong YAML:

```yaml
app:
  routes:
    "[/api/v1]": frontend
    "[/admin]": backend
```

Kết quả kỳ vọng:

```text
routes.get("/api/v1") == "frontend"
routes.get("/admin")  == "backend"
```

**Chỉ trong YAML, key có bracket notation phải được đặt trong dấu nháy**, ví dụ `"[/api/v1]"`. Nếu không bao bằng `[]`, những ký tự không phải chữ/số, dấu `-` hoặc dấu `.` có thể bị loại khỏi key khi binding. Ví dụ:

```properties
app.routes./api/v1=frontend
```

có thể tạo key `apiv1` thay vì `/api/v1`; đây là lỗi dữ liệu, không chỉ lỗi phong cách đặt tên.

### 7.2. Key chứa dấu chấm phụ thuộc kiểu giá trị Map

Nếu `routes` là `Map<String,String>`, key chứa dấu chấm như `a.b` có thể được giữ nguyên mà không cần bracket:

```properties
app.routes.a.b=value
```

Nhưng nếu kiểu đích là `Map<String,Object>` hoặc một cấu trúc phức tạp, dấu chấm không được bracket có thể đại diện cho một **cấp lồng nhau**.

Để bảo đảm key nguyên văn `a.b` trong tình huống không chắc kiểu Map:

```properties
app.metadata.[a.b]=value
```

YAML:

```yaml
app:
  metadata:
    "[a.b]": value
```

Không được suy luận rằng relaxed binding sẽ tự “xóa dấu chấm”, “giữ dấu chấm” hoặc “chuyển thành nested key” giống hệt nhau cho mọi Map type. Cần xét **kiểu Map value** và bracket notation.

### 7.3. Case của Map key từ environment variable

Khi bind Map từ environment variables, Spring Boot chuyển tên Map key từ environment source thành **chữ thường**. Ví dụ:

```bash
APP_LABELS_TEAM=platform
```

Với `Map<String,String> labels`, key thu được có dạng `team`, không phải `TEAM`. Nếu business cần giữ key hỗn hợp chữ hoa/thường, dấu `/`, dấu `.` hoặc Unicode đặc biệt, environment variable không phải lúc nào cũng là nguồn diễn đạt dễ dàng nhất; dùng file Config Data có key bracket khi cần bảo toàn chính xác.

## 8. Phân biệt tên key trong nguồn và tên Java property đích

Nhìn vào một cấu hình:

```properties
app.payment-gateway.base-url=https://pay.example.test
```

Có thể mô hình hóa thành:

```java
@ConfigurationProperties(prefix = "app")
public class AppProperties {
    private PaymentGateway paymentGateway = new PaymentGateway();

    public PaymentGateway getPaymentGateway() {
        return paymentGateway;
    }

    public void setPaymentGateway(PaymentGateway paymentGateway) {
        this.paymentGateway = paymentGateway;
    }

    public static class PaymentGateway {
        private String baseUrl;

        public String getBaseUrl() { return baseUrl; }
        public void setBaseUrl(String baseUrl) { this.baseUrl = baseUrl; }
    }
}
```

Binder đi theo chuỗi:

```text
app.payment-gateway.base-url
 |         |              |
prefix   paymentGateway   baseUrl
```

Trong Java, `paymentGateway` và `baseUrl` là tên field/property; trong Config Data, `payment-gateway` và `base-url` là cách đặt tên canonical của chúng.

Cần phân biệt với:

```java
Map<String, PaymentGateway> gateways;
```

Khi đó:

```properties
app.gateways.billing.base-url=https://pay.example.test
```

`billing` là **key của Map**, không phải một JavaBean property cố định. Quy tắc bảo toàn key Map có thể trở nên quan trọng nếu key có ký tự đặc biệt.

## 9. `@Value` và placeholder: dạng canonical quan trọng

`@ConfigurationProperties` dùng Binder với relaxed binding chuyên biệt. `@Value` dùng cơ chế property placeholder của Spring Framework/Boot; hai API **không hoàn toàn giống nhau**.

**Khuyến nghị của Spring Boot 3.3:** khi viết placeholder trong `@Value`, dùng **tên property ở dạng canonical (kebab-case, chữ thường)**. Nhờ vậy Spring Boot có thể áp dụng logic nhận dạng tương tự relaxed binding của `@ConfigurationProperties` trong các trường hợp được hỗ trợ.

Ví dụ:

```java
@Value("${app.max-retries:3}")
private int maxRetries;
```

Với placeholder `app.max-retries` ở dạng chuẩn, Spring Boot có thể xem xét các biến thể tương ứng, ví dụ `app.max-retries`, `app.maxRetries` từ file và `APP_MAXRETRIES` từ biến môi trường.

Ngược lại:

```java
@Value("${app.maxRetries:3}")
private int maxRetries;
```

việc viết tên placeholder theo camelCase có thể **không xét đầy đủ** các biến thể tương đương như khi dùng tên canonical. Dù một source cụ thể vẫn có thể được đọc, không nên suy luận rằng `@Value` luôn có toàn bộ semantics của Binder cho mọi tên property.

**Chọn một cách viết chuẩn:**

```java
@Value("${app.http-client.connect-timeout:5s}")
private Duration connectTimeout;
```

Thay vì:

```java
@Value("${app.httpClient.connectTimeout:5s}")
private Duration connectTimeout;
```

### `@Value` phù hợp cho gì?

- Một hoặc vài giá trị scalar đơn giản.
- Placeholder có default như `${app.name:Catalog}`.
- Những trường hợp cần sử dụng biểu thức SpEL theo thiết kế của Spring.

### Khi nào nên dùng `@ConfigurationProperties`?

- Nhiều thuộc tính cùng prefix.
- Nested object, `List<T>`, `Map<K,V>`.
- Type-safe binding, constructor/record binding và validation.
- Cần metadata cấu hình cho IDE và tài liệu.
- Muốn nhất quán về relaxed binding từ nhiều nguồn.

Không dùng `@Value("${app.servers}")` để kỳ vọng nó tự tạo `List<Server>` phức tạp từ các key dạng `app.servers[0].host`. Dùng Binder/`@ConfigurationProperties` thay thế.

## 10. `Environment#getProperty` có cùng quy tắc không?

Một ví dụ:

```java
String timeout = environment.getProperty(
        "app.http-client.connect-timeout");
```

`Environment` giải quyết key thông qua các `PropertySource`; mức hỗ trợ biến thể tên còn phụ thuộc loại PropertySource và cơ chế property name mapping. Vì vậy:

- Khi đọc file và môi trường bằng `@ConfigurationProperties`, Binder là con đường được thiết kế riêng cho relaxed binding.
- Khi đọc một key String đơn lẻ, nên dùng **tên canonical** nhất quán.
- Không dùng `getProperty` để kiểm tra một tập hợp key gần giống nhau rồi tự ghép thành object nếu Binder có thể xử lý việc đó.
- `Environment.containsProperty(key)` và `getProperty(key)` mô tả property có thể giải quyết trong `Environment`, không chứng minh text key đã xuất hiện trong file nào.

Trong Spring Boot, các biến môi trường được biểu diễn bởi PropertySource có khả năng ánh xạ từ cách viết `APP_MAXRETRIES` sang tên property tương ứng; nhưng API sử dụng và tên tra cứu vẫn nên thống nhất theo canonical form để tránh sự khác nhau không mong muốn.

## 11. Ví dụ ứng dụng hoàn chỉnh

### 11.1. Class `CatalogProperties`

Ví dụ này dùng Spring Boot 3.3 và Java 17+:

```java
package com.example.demo.config;

import java.time.Duration;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "catalog")
public class CatalogProperties {

    private String displayName = "Catalog";
    private int maxRetries = 3;
    private boolean auditEnabled = true;

    private HttpClient httpClient = new HttpClient();
    private List<Endpoint> endpoints = new ArrayList<>();
    private Map<String, String> routes = new LinkedHashMap<>();

    public String getDisplayName() {
        return displayName;
    }

    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }

    public int getMaxRetries() {
        return maxRetries;
    }

    public void setMaxRetries(int maxRetries) {
        this.maxRetries = maxRetries;
    }

    public boolean isAuditEnabled() {
        return auditEnabled;
    }

    public void setAuditEnabled(boolean auditEnabled) {
        this.auditEnabled = auditEnabled;
    }

    public HttpClient getHttpClient() {
        return httpClient;
    }

    public void setHttpClient(HttpClient httpClient) {
        this.httpClient = httpClient;
    }

    public List<Endpoint> getEndpoints() {
        return endpoints;
    }

    public void setEndpoints(List<Endpoint> endpoints) {
        this.endpoints = endpoints;
    }

    public Map<String, String> getRoutes() {
        return routes;
    }

    public void setRoutes(Map<String, String> routes) {
        this.routes = routes;
    }

    public static class HttpClient {
        private Duration connectTimeout = Duration.ofSeconds(2);

        public Duration getConnectTimeout() {
            return connectTimeout;
        }

        public void setConnectTimeout(Duration connectTimeout) {
            this.connectTimeout = connectTimeout;
        }
    }

    public static class Endpoint {
        private String baseUrl;
        private boolean enabled = true;

        public String getBaseUrl() {
            return baseUrl;
        }

        public void setBaseUrl(String baseUrl) {
            this.baseUrl = baseUrl;
        }

        public boolean isEnabled() {
            return enabled;
        }

        public void setEnabled(boolean enabled) {
            this.enabled = enabled;
        }
    }
}
```

Tên JavaBeans ở đây là camelCase (`displayName`, `maxRetries`, `auditEnabled`, `httpClient`, `connectTimeout`, `baseUrl`), trong khi file config chuẩn sẽ là kebab-case.

### 11.2. Bật quét `@ConfigurationProperties`

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

`@ConfigurationPropertiesScan` đăng ký các class `@ConfigurationProperties` nằm trong package được quét. Có thể thay thế bằng `@EnableConfigurationProperties(CatalogProperties.class)` khi muốn đăng ký rõ một class, nhưng không cần dùng cả hai chỉ để có cùng một bean.

### 11.3. Cấu hình YAML chuẩn

```yaml
# src/main/resources/application.yaml
catalog:
  display-name: Catalog API
  max-retries: 3
  audit-enabled: true

  http-client:
    connect-timeout: 2s

  endpoints:
    - base-url: https://first.example.test
      enabled: true
    - base-url: https://second.example.test
      enabled: false

  routes:
    "[/api/v1]": first
    "[/health]": second
```

### 11.4. Cấu hình .properties tương đương

```properties
# src/main/resources/application.properties
catalog.display-name=Catalog API
catalog.max-retries=3
catalog.audit-enabled=true

catalog.http-client.connect-timeout=2s

catalog.endpoints[0].base-url=https://first.example.test
catalog.endpoints[0].enabled=true
catalog.endpoints[1].base-url=https://second.example.test
catalog.endpoints[1].enabled=false

catalog.routes.[/api/v1]=first
catalog.routes.[/health]=second
```

Chỉ cần dùng **một** trong hai file tương đương cho tình huống này. Đừng đưa cả hai vào cùng một location rồi giả định Boot sẽ ghép từng khóa theo thứ tự không cần quan tâm.

### 11.5. Override bằng environment variables

```bash
CATALOG_DISPLAYNAME="Catalog deployed" \
CATALOG_MAXRETRIES=0 \
CATALOG_AUDITENABLED=false \
CATALOG_HTTPCLIENT_CONNECTTIMEOUT=750ms \
CATALOG_ENDPOINTS_0_BASEURL=https://internal.example.test \
java -jar myapp.jar
```

Các tên environment variable được tạo theo quy tắc canonical, bỏ `-` và đổi dấu `.` thành `_`. Trong trường hợp ví dụ, property `max-retries` có thể nhận `0`, `audit-enabled` có thể nhận `false` và `connect-timeout` có thể nhận `750ms`.

**Lưu ý collection precedence:** nếu override list phần tử bằng environment variable có ưu tiên cao hơn, List có thể được thay thế toàn bộ; không dựa vào giả định chỉ `endpoints[0].base-url` bị thay còn các thuộc tính/phần tử của nguồn thấp hơn tự được ghép lại. Khi cần override một list, nên cung cấp đầy đủ cấu trúc từ nguồn có ưu tiên cao hoặc thiết kế cấu hình dạng Map nếu muốn hợp nhất theo key.

### 11.6. Sử dụng trong service

```java
package com.example.demo.service;

import com.example.demo.config.CatalogProperties;
import org.springframework.stereotype.Service;

@Service
public class CatalogService {

    private final CatalogProperties properties;

    public CatalogService(CatalogProperties properties) {
        this.properties = properties;
    }

    public void showEffectiveSettings() {
        System.out.println(properties.getDisplayName());
        System.out.println(properties.getMaxRetries());
        System.out.println(properties.isAuditEnabled());
        System.out.println(
                properties.getHttpClient().getConnectTimeout());
        System.out.println(
                properties.getRoutes().get("/api/v1"));
    }
}
```

Ví dụ trên chỉ in các giá trị không nhạy cảm. Không nên log password, API key, token hoặc toàn bộ `Environment` trong ứng dụng thực tế.

## 12. Khi nhiều nguồn dùng tên khác nhau cho cùng property

Giả sử:

```properties
# application.properties
catalog.max-retries=5
```

Biến môi trường:

```bash
CATALOG_MAXRETRIES=3
```

Command line:

```bash
java -jar myapp.jar --catalog.max-retries=0
```

Với thứ tự ưu tiên PropertySource mặc định của Spring Boot 3.3, command line có ưu tiên cao hơn OS environment và Config Data. Giá trị cuối có thể là `maxRetries=0`.

**Không nhầm hai cơ chế:**

1. **Relaxed binding:** `catalog.max-retries` và `CATALOG_MAXRETRIES` có thể ánh xạ cùng Java property `maxRetries`.
2. **PropertySource precedence:** nguồn nào thắng khi hai hoặc nhiều nguồn cùng có thể cung cấp giá trị cho property đó.

Tên khác nhau không có nghĩa đó là hai cấu hình độc lập. Và `0` là một giá trị explicit có thể ghi đè `5` hay `3`; nó không phải tín hiệu “không cấu hình”.

### Đừng khai báo duplicate alias trong cùng file

Ví dụ nên tránh:

```properties
catalog.max-retries=3
catalog.maxRetries=5
catalog.max_retries=7
```

Các dòng này nhắm cùng ý nghĩa Java property, dễ gây mơ hồ về hiệu lực và source origin. Chỉ viết:

```properties
catalog.max-retries=3
```

Nếu cần nhiều override, hãy dùng các **nguồn cấu hình rõ ràng** theo môi trường và xác định precedence, không tạo nhiều alias trong một file như một thủ thuật điều khiển thứ tự.

## 13. Canonical names cho nested structures

### Nested JavaBean

Java:

```java
public class Logging {
    private boolean includeRequestId;
    public boolean isIncludeRequestId() { return includeRequestId; }
    public void setIncludeRequestId(boolean value) {
        includeRequestId = value;
    }
}
```

Nếu parent có property `logging` thì path chuẩn có thể là:

```properties
catalog.logging.include-request-id=true
```

YAML:

```yaml
catalog:
  logging:
    include-request-id: true
```

Environment variable:

```bash
CATALOG_LOGGING_INCLUDEREQUESTID=true
```

### Nested Map

Java:

```java
private Map<String, ServiceConfig> services;
```

Config:

```properties
catalog.services.billing.base-url=https://billing.example.test
catalog.services.inventory.base-url=https://inventory.example.test
```

Trong đó:

- `catalog.services` là đường dẫn đến Map.
- `billing` và `inventory` là **Map keys**.
- `base-url` là canonical name cho Java property `baseUrl` của `ServiceConfig`.

Nếu một Map key chứa dấu chấm hoặc dấu slash, phải cân nhắc bracket notation riêng như phần Map key.

### Map chứa List

Java:

```java
private Map<String, List<String>> allowedRegionsByService;
```

Config:

```properties
catalog.allowed-regions-by-service.billing[0]=vn
catalog.allowed-regions-by-service.billing[1]=sg
catalog.allowed-regions-by-service.inventory[0]=vn
```

Ở đây `allowed-regions-by-service` là canonical name của Java property `allowedRegionsByService`; `billing`/`inventory` là Map keys, `[0]`/`[1]` là List indexes. Mỗi loại đoạn của property path có ý nghĩa riêng, không được chỉ áp dụng một quy tắc thay dấu gạch nối cho cả cấu trúc.

## 14. Tương tác với constructor binding và record

Relaxed binding không chỉ dành cho JavaBean có setter. Spring Boot 3.3 cũng có thể bind record hoặc class dùng constructor binding.

Ví dụ:

```java
package com.example.demo.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "checkout")
public record CheckoutProperties(
        @DefaultValue("false") boolean enabled,
        @DefaultValue("3s") Duration requestTimeout,
        @DefaultValue("3") int maxRetries) {
}
```

File:

```properties
checkout.enabled=true
checkout.request-timeout=5s
checkout.max-retries=0
```

Environment:

```bash
CHECKOUT_ENABLED=true
CHECKOUT_REQUESTTIMEOUT=5s
CHECKOUT_MAXRETRIES=0
```

Binder nhận `request-timeout` để truyền vào constructor parameter `requestTimeout` và `max-retries` cho `maxRetries`, dù không có setter. Tên property chuẩn vẫn giữ nguyên.

`@DefaultValue` có thể dùng cho constructor-binding parameters khi property tương ứng **không được tìm thấy**. Việc có default không làm biến `false`/`0` explicit trở thành missing. Với JavaBean binding, giá trị khởi tạo field là một cơ chế default khác.

**Chú ý:** constructor binding của `@ConfigurationProperties` được hỗ trợ với các bean đăng ký bằng cơ chế cấu hình properties phù hợp, như `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties`. Nó không áp dụng tự động cho mọi bean do `@Component` hoặc một `@Bean` factory thông thường tạo ra.

## 15. Dấu gạch nối, dấu gạch dưới và khoảng trắng: đặt đúng nơi

### 15.1. Kebab-case dùng cho tên, không làm thay đổi value

```properties
app.display-name=Hello World
```

`display-name` là **tên property**, còn `Hello World` là **value**. Relaxed binding chỉ giúp ánh xạ tên vào Java property, không tự đổi value thành `hello-world` hoặc bỏ khoảng trắng.

### 15.2. Dấu gạch dưới trong file không đồng nghĩa quy tắc môi trường

```properties
app.max_retries=3
```

có thể được Binder nhận dạng như biến thể của `app.max-retries`, nhưng environment variable chuẩn vẫn là:

```text
APP_MAXRETRIES
```

không phải `APP_MAX_RETRIES`. Dấu `_` trong tên OS environment biểu diễn dấu chấm phân cấp, không nên dùng nó để thay thế mọi dấu phân cách từ file .properties.

### 15.3. Java snake_case và đặt tên không chuẩn

Trong Java có thể viết trường `max_retries`, nhưng JavaBean property name và getter/setter trở nên kém tự nhiên. Nên dùng `maxRetries` trong Java, `max-retries` trong file cấu hình, và `MAXRETRIES` ở thành phần cuối của environment variable tương ứng.

### 15.4. Ký tự không bình thường trong Map key

Khi một Map key thực sự là đường dẫn `/api/v1`, đừng biến nó thành tên Java property `apiV1`. Key là dữ liệu: dùng `[/api/v1]` trong property path hoặc `"[/api/v1]"` trong YAML. Điều này giữ nguyên hành vi định tuyến và tránh key bị làm sạch ngoài ý muốn.

## 16. Configuration metadata và lợi ích của tên chuẩn

Spring Boot có **configuration metadata** để hỗ trợ IDE gợi ý, kiểm tra mô tả thuộc tính và hiển thị tài liệu cho `@ConfigurationProperties`.

Với Maven có thể khai báo processor như một dependency có mục đích build:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-configuration-processor</artifactId>
    <optional>true</optional>
</dependency>
```

Với Gradle (ví dụ Java plugin):

```groovy
dependencies {
    annotationProcessor "org.springframework.boot:spring-boot-configuration-processor"
}
```

Tùy cấu hình build và version management của dự án, cần bảo đảm version được quản lý tương thích với Spring Boot 3.3.

Processor có thể tạo metadata trong:

```text
META-INF/spring-configuration-metadata.json
```

Các property được mô tả ở dạng tên phù hợp với convention, ví dụ `catalog.display-name`, `catalog.max-retries` và `catalog.http-client.connect-timeout`.

Metadata giúp tooling hỗ trợ người chỉnh file cấu hình, nhưng bản thân nó không bắt buộc để Binder hoạt động runtime. Không được dựa vào việc IDE gạch chân tên nào đó như chứng cứ duy nhất rằng runtime Binder chắc chắn bind được hoặc không; xét model Java, property path và PropertySource thực tế.

## 17. Khi nào relaxed binding không cứu được cấu hình?

### Trường hợp A — Prefix sai

```java
@ConfigurationProperties(prefix = "catalog")
public class CatalogProperties { /* ... */ }
```

```properties
payments.max-retries=3
```

Property `payments.max-retries` không tự bind vào `catalog.maxRetries` chỉ vì cả hai cùng có đoạn `max-retries`. Relaxed binding hỗ trợ **biến thể cách viết của cùng tên logic**, không thay đổi prefix theo ý nghĩa nghiệp vụ.

### Trường hợp B — Tên thuộc tính không tương đương

```java
private int maxRetries;
```

```properties
catalog.retry-limit=3
```

`retry-limit` không cùng tên với `maxRetries`. Muốn dùng tên đó, đổi Java property thành `retryLimit`, đổi file thành `catalog.max-retries` hoặc tự xây dựng logic alias rõ ràng ở tầng ứng dụng.

### Trường hợp C — JavaBean thiếu setter

```java
private String displayName;
public String getDisplayName() { return displayName; }
```

Dù file `catalog.display-name=Catalog` có tên đúng, JavaBean binding thông thường không thể cập nhật scalar getter-only nếu không có setter. Bổ sung `setDisplayName(...)` hoặc dùng constructor binding.

### Trường hợp D — Bean chưa được đăng ký

Chỉ gắn `@ConfigurationProperties` vào một class không bảo đảm Boot quét nó. Nếu không có `@ConfigurationPropertiesScan`, `@EnableConfigurationProperties` hoặc phương pháp bean registration phù hợp, không có bean nào được bind. Lỗi không nằm ở cách viết `maxRetries`/`max-retries`.

### Trường hợp E — Value không chuyển kiểu được

```properties
catalog.max-retries=unlimited
```

Dù tên đúng, `unlimited` không chuyển thành `int` theo quy tắc thông thường. Binder có thể báo lỗi chuyển đổi. Đừng quy lỗi type conversion thành lỗi relaxed binding.

### Trường hợp F — Map key bị mất ký tự

```properties
catalog.routes./api/v1=frontend
```

Tên nhìn giống một property path, nhưng nếu mục tiêu là Map key nguyên văn `/api/v1`, cần viết:

```properties
catalog.routes.[/api/v1]=frontend
```

### Trường hợp G — Environment variable viết sai

```text
APP_HTTP_CLIENT_CONNECT_TIMEOUT
```

Tên này thường bị hiểu theo ranh giới phân cấp khác với ý định `app.http-client.connect-timeout`. Dùng dạng chuẩn:

```text
APP_HTTPCLIENT_CONNECTTIMEOUT
```

Lỗi đặc biệt dễ xảy ra khi người viết chỉ chuyển mọi dấu `-` và `.` thành `_`.

### Trường hợp H — Viết camelCase trong placeholder @Value

```java
@Value("${catalog.maxRetries:3}")
private int maxRetries;
```

Có thể không tận dụng đầy đủ canonical property name lookup như:

```java
@Value("${catalog.max-retries:3}")
private int maxRetries;
```

Dùng dạng canonical trong placeholder.

### Trường hợp I — Nhầm empty với missing

```properties
catalog.display-name=
```

`""` là String rỗng explicit, không có nghĩa “không khai báo”. Giá trị rỗng có thể ghi đè giá trị từ nguồn khác; default placeholder thường chỉ được dùng khi property không tìm thấy. Relaxed binding không tự thay rỗng bằng default.

### Trường hợp J — Nhiều source cùng property

```properties
# application.properties
catalog.max-retries=5
```

```bash
CATALOG_MAXRETRIES=1 java -jar myapp.jar
```

Binder có thể nhận hai tên là cùng một Java property, nhưng kết quả phụ thuộc PropertySource precedence. Đây là behavior đúng; cần xác định source cao hơn, không đổi Java field từ `maxRetries` thành `max_retries` để né vấn đề.

## 18. Chẩn đoán lỗi binding một cách có hệ thống

Khi một trường Java không nhận đúng giá trị, thực hiện theo trình tự:

1. **Kiểm tra đúng prefix:** `@ConfigurationProperties(prefix="catalog")` phải khớp đầu đường dẫn cấu hình.
2. **Viết canonical name:** chuyển camelCase trong Java thành kebab-case ở từng cấp, ví dụ `httpClient.connectTimeout` → `http-client.connect-timeout`.
3. **Xem source type:** .properties, YAML, JVM `-D`, CLI hay OS environment? Áp dụng quy tắc tên tương ứng, đặc biệt việc **bỏ dấu `-`** ở environment variable.
4. **Xem nested path:** dấu chấm phân cấp, List có `[i]`, Map key có bracket khi cần.
5. **Kiểm tra bean registration:** scan/enable/component/factory đã tạo bean hay chưa.
6. **Kiểm tra binding strategy:** JavaBean setter hoặc constructor binding có phù hợp không.
7. **Kiểm tra conversion:** value có chuyển thành kiểu Java (`Duration`, `DataSize`, `Boolean`, enum…) được không?
8. **Kiểm tra precedence:** một OS env, JVM property, test property hay CLI có thể ghi đè file.
9. **Quan sát nguồn cấu hình:** dùng `Environment` hoặc Actuator với endpoint được bảo vệ để tìm property hiệu lực và nguồn của nó.
10. **Chuẩn hóa tên ở cấu hình lâu dài:** tránh nhiều biến thể alias gây khó debug, giữ một canonical property name trong README và source files.

### Đoạn code chẩn đoán tối giản

```java
package com.example.demo.config;

import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;

@Configuration(proxyBeanMethods = false)
class ConfigDiagnostics {

    @Bean
    ApplicationRunner showConfig(
            Environment environment,
            CatalogProperties catalog) {

        return args -> {
            String key = "catalog.max-retries";
            System.out.println("Resolved raw value: "
                    + environment.getProperty(key));
            System.out.println("Bound JavaBean value: "
                    + catalog.getMaxRetries());
        };
    }
}
```

Nếu `environment.getProperty(key)` có giá trị mong đợi nhưng bean không đúng, cần xem bean registration, conversion và cách bind. Nếu raw value không có hoặc không như mong đợi, xem Config Data location, biến môi trường đúng tên và thứ tự PropertySource.

Không in toàn bộ secret vào log. Với Actuator, có thể tham khảo `/actuator/configprops` và `/actuator/env` nhưng cần cấu hình bảo vệ và sanitization phù hợp.

## 19. Bảng đối chiếu công thức chuyển đổi

| Java hoặc ý nghĩa | Canonical .properties | YAML key theo từng cấp | Environment variable |
| --- | --- | --- | --- |
| `displayName` thuộc `catalog` | `catalog.display-name` | `catalog:` → `display-name:` | `CATALOG_DISPLAYNAME` |
| `maxRetries` thuộc `catalog` | `catalog.max-retries` | `catalog:` → `max-retries:` | `CATALOG_MAXRETRIES` |
| `httpClient.connectTimeout` | `catalog.http-client.connect-timeout` | `http-client:` → `connect-timeout:` | `CATALOG_HTTPCLIENT_CONNECTTIMEOUT` |
| `logging.includeRequestId` | `catalog.logging.include-request-id` | `logging:` → `include-request-id:` | `CATALOG_LOGGING_INCLUDEREQUESTID` |
| `servers[0].baseUrl` | `catalog.servers[0].base-url` | `servers:` → `- base-url:` | `CATALOG_SERVERS_0_BASEURL` |
| `servers[1].enabled` | `catalog.servers[1].enabled` | `servers:` → `- enabled:` | `CATALOG_SERVERS_1_ENABLED` |
| `routes["/api/v1"]` | `catalog.routes.[/api/v1]` | `routes:` → `"[/api/v1]":` | Nên dùng Config Data để giữ nguyên key đặc biệt |
| `Map<String,Object> metadata["a.b"]` | `catalog.metadata.[a.b]` | `metadata:` → `"[a.b]":` | Nên dùng Config Data cho key có dấu chấm cần giữ nguyên |

### Câu ghi nhớ một dòng

```text
Java camelCase  →  file lowercase kebab-case
file có dấu .   →  env đổi . thành _
file có dấu -   →  env BỎ dấu -
List [0]        →  env _0_
Map key đặc biệt→  file dùng [key], YAML quote "[key]"
@Value          →  placeholder viết tên canonical
```

## 20. Câu hỏi thực hành

### Câu 1. Đổi tên đúng sang OS environment

Canonical property:

```properties
payments.card-reader.read-timeout=250ms
```

Tên biến môi trường chuẩn là gì?

**Đáp án:**

```text
PAYMENTS_CARDREADER_READTIMEOUT
```

Không phải `PAYMENTS_CARD_READER_READ_TIMEOUT`. Cả `card-reader` và `read-timeout` đều bỏ `-`.

### Câu 2. Biến môi trường cho List

Canonical:

```properties
app.backends[2].base-url=https://three.example.test
```

Tên biến môi trường:

```text
APP_BACKENDS_2_BASEURL
```

Chỉ số `2` được đặt giữa các dấu gạch dưới; `base-url` bỏ gạch nối.

### Câu 3. Map key /prod/api có giữ nguyên không?

Cấu hình:

```properties
app.routes./prod/api=payment
```

Không nên kỳ vọng Map key giữ dấu `/`. Viết:

```properties
app.routes.[/prod/api]=payment
```

Hoặc YAML:

```yaml
app:
  routes:
    "[/prod/api]": payment
```

### Câu 4. Vì sao `@Value` dùng kebab-case?

Để placeholder như `${app.max-retries:3}` tận dụng tốt logic canonical property name lookup của Spring Boot. Khi dùng camelCase trong placeholder, một số biến thể từ file/environment có thể không được xét giống Binder.

### Câu 5. Hai tên cấu hình cho một target có cộng dồn không?

```properties
app.max-retries=3
```

```bash
APP_MAXRETRIES=0
```

Chúng đều có thể bind vào Java `maxRetries`, nhưng giá trị không “cộng lại”. Nguồn ưu tiên cao hơn quyết định value; với cấu hình thông thường OS environment có ưu tiên cao hơn Config Data, nên `maxRetries=0`.

## 21. Checklist đặt tên cấu hình cho dự án

- [ ] Mọi tên property trong README và Config Data dùng lowercase kebab-case.
- [ ] Prefix của `@ConfigurationProperties` dùng dạng canonical, ví dụ `billing.http-client`.
- [ ] JavaBean fields/record components dùng camelCase, ví dụ `readTimeout`.
- [ ] Không đặt nhiều biến thể `read-timeout`, `readTimeout`, `read_timeout` cho cùng key trong một nguồn.
- [ ] Script deployment chuyển `.` thành `_`, **bỏ `-`**, rồi uppercase.
- [ ] List index trong environment variable ở dạng `_0_`, `_1_`...
- [ ] Map key chứa ký tự đặc biệt dùng `[key]` và YAML quote `"[key]"`.
- [ ] Placeholder `@Value` dùng tên canonical.
- [ ] Không nhầm lỗi conversion/registration/precedence với lỗi relaxed binding.
- [ ] Khi đổi tên một property đã công bố cho người dùng, có kế hoạch tương thích và cập nhật tài liệu; không dựa vào relaxed binding để tự biến hai tên logic khác nhau thành alias.
- [ ] Tránh để lộ bí mật trong log hoặc tài liệu ví dụ thực tế.
- [ ] Có test ở mức ứng dụng cho những tên environment variables quan trọng trước khi triển khai.

## 22. Tài liệu tham khảo

- **Spring Boot 3.3 Reference — Externalized Configuration**, các mục *Type-safe Configuration Properties*, *Relaxed Binding*, *Binding From Environment Variables*, *Binding Maps*, *Property Placeholders* và *PropertySource Order*: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- **Spring Boot 3.3 Reference — Configuration Metadata**, cách metadata mô tả canonical property names: https://docs.spring.io/spring-boot/3.3/reference/configuration-metadata/index.html
- **Spring Boot 3.3 API — `@ConfigurationProperties`**: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/ConfigurationProperties.html
- **Spring Boot 3.3 API — `ConfigurationPropertyName`**, mô hình tên configuration property và phân cấp: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/source/ConfigurationPropertyName.html

**Tóm tắt:** Relaxed binding giúp Spring Boot liên kết những cách viết tên khác nhau về **cùng property Java**, nhưng không bỏ qua prefix, cấu trúc List/Map, conversion hoặc PropertySource precedence. Hãy chuẩn hóa tên trong file và placeholder thành **lowercase kebab-case**, đổi sang OS environment theo công thức **dot → underscore, dash → remove, uppercase**, đồng thời dùng `[key]` khi Map cần giữ nguyên ký tự đặc biệt.
