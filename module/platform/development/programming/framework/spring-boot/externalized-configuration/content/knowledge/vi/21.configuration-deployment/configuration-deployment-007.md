# Chọn giá trị triển khai khi có cấu hình tệp và biến môi trường đồng thời trong Spring Boot 3.3

## 1. Bài toán cần giải quyết

Trong thực tế triển khai Spring Boot, một cấu hình có thể xuất hiện đồng thời tại nhiều nguồn: file `application.properties` hoặc `application.yaml` trong JAR; file ngoài JAR được mount; file `application-prod.yaml`; biến môi trường của container; Java system property `-D`; tham số dòng lệnh `--key=value`; và một số nguồn bổ sung như `SPRING_APPLICATION_JSON`.

Ví dụ ứng dụng có:

```yaml
# application.yaml
app:
  request-timeout: 5s
  max-retries: 3
  feature-enabled: true
```

Docker hoặc Kubernetes lại cung cấp:

```bash
APP_REQUESTTIMEOUT=10s
APP_MAXRETRIES=0
APP_FEATUREENABLED=false
```

**Kết luận chính:** với thứ tự `PropertySource` mặc định của **Spring Boot 3.3**, biến môi trường hệ điều hành (**OS environment**) có độ ưu tiên **cao hơn Config Data**, bao gồm các file `application.*`. Nếu tên biến ánh xạ đúng property và không có nguồn cao hơn ghi đè, Spring Boot sẽ chọn:

```text
app.request-timeout = 10s
app.max-retries     = 0
app.feature-enabled = false
```

Điều này **không có nghĩa biến môi trường thắng mọi nguồn**. Java system properties, `SPRING_APPLICATION_JSON` và command-line properties thông thường có thể có ưu tiên cao hơn OS environment. Hơn nữa, việc một value được chọn chưa bảo đảm Binder chuyển đổi kiểu thành công hoặc validation chấp nhận nó.

Bài viết giải thích cơ chế chọn source, cách đổi tên key giữa file và environment, Config Data theo profile, Docker Compose, Kubernetes, collection/Map, các trường hợp missing/empty/zero/false, chẩn đoán và kiểm thử.

## 2. Environment và PropertySource: chọn value theo từng key

Spring Boot quản lý cấu hình qua Spring `Environment` với một tập `PropertySource` có thứ tự. Mỗi source có thể cung cấp một số property; không cần mọi source đều có cùng tập key.

```text
    app.request-timeout
             |
             v
     Spring Environment
             |
       PropertySources
             |
    +--------+---------+----------------+
    |                  |                |
    v                  v                v
 Config Data        OS environment    CLI/-D/JSON
 5s                 10s               tùy deployment
    |                  |                |
    +------------------+----------------+
             |
             v
  Value từ source ưu tiên cao nhất
             |
             v
      Binder / @Value
             |
             v
      Duration hoặc Java type khác
```

Ba công đoạn khác nhau:

1. **Nhận dạng tên**: `app.request-timeout` trong file và `APP_REQUESTTIMEOUT` trong environment có thể tương ứng cùng Java property `requestTimeout`.
2. **Chọn theo precedence**: nguồn cao nhất có giá trị cho cùng property thắng.
3. **Chuyển kiểu và xác thực**: `10s` được chuyển thành `Duration`; nếu validation có ràng buộc ngưỡng, nó được kiểm tra riêng.

Nếu file khai báo thêm `app.service-name=Catalog` nhưng env không có biến tương ứng, tên dịch vụ vẫn lấy từ file. Spring Boot không tự bỏ toàn bộ namespace `app` của nguồn thấp khi nguồn cao chỉ cung cấp một key.

### Ví dụ override từng key

```properties
app.name=Catalog
app.request-timeout=5s
app.retries=3
```

Môi trường:

```bash
APP_REQUESTTIMEOUT=10s
```

Kết quả thông thường:

| Property | Giá trị hiệu lực | Nguồn |
| --- | --- | --- |
| `app.name` | `Catalog` | File |
| `app.request-timeout` | `10s` | Environment |
| `app.retries` | `3` | File |

Đây là trường hợp scalar properties. Với `List`, `Map` và nested structures cần xét thêm quy tắc merge riêng ở phần sau.

## 3. Thứ tự ưu tiên của Spring Boot 3.3

Tài liệu Spring Boot 3.3 nêu các nguồn cấu hình theo **thứ tự ưu tiên tăng dần**. Với triển khai thông thường, các nguồn quan trọng gồm:

```text
ƯU TIÊN THẤP
  SpringApplication default properties
           <
  @PropertySource thông thường
           <
  Config Data (application.properties / YAML /
               profile-specific / external / imports)
           <
  RandomValuePropertySource
           <
  OS environment variables
           <
  Java system properties (-D...)
           <
  JNDI / ServletContext / ServletConfig (nếu có)
           <
  SPRING_APPLICATION_JSON
           <
  Command-line arguments (--key=value)
           <
  Một số nguồn test / Devtools trong ngữ cảnh tương ứng
ƯU TIÊN CAO
```

Không phải mọi nguồn đều hiện diện trong mọi application. Một số framework hoặc ứng dụng có `EnvironmentPostProcessor`, custom `PropertySource` hoặc bootstrap tùy chỉnh, vì vậy **thứ tự thực tế có thể khác**. Bảng trên là hành vi mặc định cần hiểu trước.

### Bảng so sánh

| Nguồn | Ví dụ `app.mode` | Thông thường có thắng file Config Data? |
| --- | --- | --- |
| Default properties của ứng dụng | `setDefaultProperties(...)` | Không |
| `@PropertySource` | `custom.properties` | Không |
| File `application.yaml` | `file` | Nguồn cơ sở |
| External/profile Config Data | `prod` | Tùy thứ tự Config Data |
| OS environment | `APP_MODE=environment` | **Có** |
| JVM system property | `-Dapp.mode=system` | **Có**, cũng thắng OS env |
| `SPRING_APPLICATION_JSON` | `{"app":{"mode":"json"}}` | **Có**, thường thắng `-D` |
| Command line | `--app.mode=cli` | **Có**, thường thắng các nguồn trên |

Lưu ý property của môi trường test như `@SpringBootTest(properties=...)`, `@TestPropertySource` hoặc `@DynamicPropertySource` có thể được ưu tiên hơn trong test context. Đừng dùng kết quả test context tùy biến để suy luận thiếu căn cứ về một JAR chạy production.

### 3.1. Ví dụ nhiều nguồn cùng key

```properties
# application.properties
app.mode=file
```

```bash
APP_MODE=env java -Dapp.mode=system -jar app.jar --app.mode=cli
```

Kết quả với mặc định của Boot:

```text
app.mode = cli
```

Nếu bỏ `--app.mode=cli`, `system` thắng. Nếu bỏ cả `-Dapp.mode=system`, `env` thắng. Nếu bỏ env, `file` được dùng.

### 3.2. Phân biệt -D và --app

```bash
java -Dapp.mode=system -jar app.jar
```

là **Java system property**; option `-D` phải đứng trước `-jar`.

```bash
java -jar app.jar --app.mode=cli
```

là **Spring Boot command-line argument**, thông thường đứng sau tên JAR và được chuyển thành command-line property khi `SpringApplication.run(args)` xử lý arguments.

Ứng dụng có thể tắt việc thêm command-line properties thông qua `SpringApplication#setAddCommandLineProperties(false)`. Khi đã tùy biến, không được giả định mọi tham số `--...` tự động có precedence như trên.

## 4. Quy tắc tên biến môi trường: dấu chấm, dấu gạch nối và chữ hoa

Tên file nên ở dạng canonical **lowercase kebab-case**. Để chuyển sang biến môi trường OS theo Spring Boot 3.3:

1. Thay dấu chấm `.` bằng dấu gạch dưới `_`.
2. **Bỏ dấu gạch nối `-`**.
3. Đổi tất cả thành chữ hoa.

Ví dụ:

```text
spring.main.log-startup-info
 -> spring_main_log-startup-info
 -> spring_main_logstartupinfo
 -> SPRING_MAIN_LOGSTARTUPINFO
```

Bảng đối chiếu:

| Canonical property | Biến môi trường chuẩn |
| --- | --- |
| `app.name` | `APP_NAME` |
| `app.request-timeout` | `APP_REQUESTTIMEOUT` |
| `app.max-retries` | `APP_MAXRETRIES` |
| `app.feature-enabled` | `APP_FEATUREENABLED` |
| `app.client.base-url` | `APP_CLIENT_BASEURL` |
| `spring.profiles.active` | `SPRING_PROFILES_ACTIVE` |
| `spring.datasource.url` | `SPRING_DATASOURCE_URL` |
| `spring.datasource.password` | `SPRING_DATASOURCE_PASSWORD` |
| `spring.main.log-startup-info` | `SPRING_MAIN_LOGSTARTUPINFO` |
| `management.endpoints.web.exposure.include` | `MANAGEMENT_ENDPOINTS_WEB_EXPOSURE_INCLUDE` |

**Điểm dễ nhầm:** `app.max-retries` chuyển chuẩn thành `APP_MAXRETRIES`, **không phải** `APP_MAX_RETRIES`. Dấu gạch dưới thường mang nghĩa ranh giới phân cấp `.`, còn gạch nối trong một property segment bị loại.

Tương tự, `app.client.connect-timeout` chuyển thành `APP_CLIENT_CONNECTTIMEOUT`. `APP_CLIENT_CONNECT_TIMEOUT` có thể được diễn giải như tên property phân cấp khác và không nên dựa vào nó để override `connectTimeout`.

### 4.1. Java dùng camelCase, file dùng kebab-case

```java
@ConfigurationProperties(prefix = "app")
public class AppProperties {
    private Duration requestTimeout = Duration.ofSeconds(5);

    public Duration getRequestTimeout() {
        return requestTimeout;
    }

    public void setRequestTimeout(Duration requestTimeout) {
        this.requestTimeout = requestTimeout;
    }
}
```

Cùng Java field `requestTimeout` nhận giá trị từ:

```properties
app.request-timeout=5s
```

hoặc:

```bash
APP_REQUESTTIMEOUT=10s
```

đó là **relaxed binding**, không cần đặt field Java thành `request_timeout`.

### 4.2. @Value khác với @ConfigurationProperties

`@ConfigurationProperties` có Binder riêng, hỗ trợ nested object, list/map, conversion, validation và relaxed binding. Với `@Value`, nên dùng placeholder ở **dạng canonical** để tận dụng khả năng tra cứu biến thể tên:

```java
@Value("${app.request-timeout:5s}")
private Duration requestTimeout;
```

Cách viết:

```java
@Value("${app.requestTimeout:5s}")
private Duration requestTimeout;
```

có thể không xét đầy đủ các alias như dạng canonical trong một số trường hợp. Nếu có cả một nhóm cấu hình, ưu tiên `@ConfigurationProperties` thay vì nhiều trường `@Value`.

## 5. Một ví dụ JavaBean hoàn chỉnh

File `AppProperties.java`:

```java
package com.example.demo.config;

import java.time.Duration;
import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public class AppProperties {

    private String displayName = "Catalog";
    private Duration requestTimeout = Duration.ofSeconds(5);
    private int maxRetries = 3;
    private boolean featureEnabled = true;
    private Map<String, String> labels = new LinkedHashMap<>();

    public String getDisplayName() { return displayName; }
    public void setDisplayName(String value) { displayName = value; }

    public Duration getRequestTimeout() { return requestTimeout; }
    public void setRequestTimeout(Duration value) {
        requestTimeout = value;
    }

    public int getMaxRetries() { return maxRetries; }
    public void setMaxRetries(int value) { maxRetries = value; }

    public boolean isFeatureEnabled() { return featureEnabled; }
    public void setFeatureEnabled(boolean value) {
        featureEnabled = value;
    }

    public Map<String, String> getLabels() { return labels; }
    public void setLabels(Map<String, String> labels) {
        this.labels = labels;
    }
}
```

Đăng ký bean bằng Spring Boot:

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

File `src/main/resources/application.yaml`:

```yaml
app:
  display-name: "Catalog"
  request-timeout: 5s
  max-retries: 3
  feature-enabled: true
  labels:
    owner: platform
    stage: default
```

Môi trường khi chạy production:

```bash
APP_DISPLAYNAME="Catalog Production" \
APP_REQUESTTIMEOUT=10s \
APP_MAXRETRIES=0 \
APP_FEATUREENABLED=false \
APP_LABELS_STAGE=production \
java -jar app.jar
```

Kết quả:

| Thuộc tính Java | File | Env | Giá trị cuối |
| --- | --- | --- | --- |
| `displayName` | `Catalog` | `Catalog Production` | `Catalog Production` |
| `requestTimeout` | `5s` | `10s` | `Duration.ofSeconds(10)` |
| `maxRetries` | `3` | `0` | `0` |
| `featureEnabled` | `true` | `false` | `false` |
| `labels.owner` | `platform` | Vắng mặt | `platform` |
| `labels.stage` | `default` | `production` | `production` |

Điều kiện: bean đã được đăng ký, tên env ánh xạ đúng, OS env được cấp cho đúng JVM, không có nguồn ưu tiên cao hơn ghi đè.

**Hai giá trị đáng chú ý:** `0` và `false` là giá trị explicit. Spring Boot không dùng chúng làm dấu hiệu “không có cấu hình”; chúng có thể ghi đè default 3 và true.

### Service sử dụng bean đã bind

```java
package com.example.demo.service;

import com.example.demo.config.AppProperties;
import org.springframework.stereotype.Service;

@Service
public class CatalogService {

    private final AppProperties properties;

    public CatalogService(AppProperties properties) {
        this.properties = properties;
    }

    public String describeSafeSettings() {
        return properties.getDisplayName()
                + " / timeout=" + properties.getRequestTimeout()
                + " / retries=" + properties.getMaxRetries();
    }
}
```

Không nên viết thêm thủ tục tự đọc `System.getenv("APP_REQUESTTIMEOUT")` rồi ghi đè tay khi đã có Binder trừ khi nghiệp vụ thật sự cần một chính sách khác.

## 6. Những cấp Config Data: file đóng gói, file ngoài, profile

Trong cùng hệ thống Config Data, Spring Boot có thứ tự ưu tiên riêng. Theo mức tăng dần cơ bản trong các location mặc định:

1. Packaged `application.properties` hoặc `application.yaml` trong JAR.
2. Packaged `application-{profile}.properties`/YAML.
3. External `application.properties`/YAML ngoài JAR.
4. External `application-{profile}.properties`/YAML.

Ví dụ:

```yaml
# application.yaml
app:
  request-timeout: 5s
  mode: safe
```

```yaml
# application-prod.yaml
app:
  request-timeout: 8s
```

```yaml
# /app/config/application-prod.yaml
app:
  mode: batch
```

Với `SPRING_PROFILES_ACTIVE=prod` và external location được Spring Boot nạp, nếu không có env override tương ứng thì `app.request-timeout` có thể là `8s` và `app.mode` có thể là `batch`.

Thêm env:

```bash
APP_REQUESTTIMEOUT=12s
APP_MODE=live
```

thì hiệu lực thông thường:

```text
app.request-timeout = 12s
app.mode            = live
```

**Active profile không làm profile-specific Config Data thắng OS environment.** Profile chỉ ảnh hưởng tài liệu Config Data nào được xét, trong khi OS environment vẫn có vị trí ưu tiên cao hơn theo mặc định.

### 6.1. Thứ tự profile-specific

Khi nhiều profile active, các file profile-specific tham gia theo quy tắc Config Data và thứ tự profile; profile khai báo sau có thể ghi đè profile trước tại location tương ứng. Không đoán chỉ dựa vào tên file alphabet mà bỏ qua active profile và location group.

### 6.2. .properties và YAML cùng một location

Nếu cùng location có `application.properties` và `application.yaml` với trùng basename, Spring Boot ưu tiên file `.properties` hơn YAML. Nên giữ một định dạng thống nhất hoặc tránh khai báo cùng property ở hai file cùng mức.

### 6.3. spring.profiles.active là một property startup

`SPRING_PROFILES_ACTIVE=prod` có thể override `spring.profiles.active` trong file không phụ thuộc profile theo precedence thông thường. Nhưng Spring Boot hạn chế nơi được khai báo `spring.profiles.active`: không đặt nó trong profile-specific document hoặc document kích hoạt qua `spring.config.activate.on-profile` theo quy tắc của Boot 3.3.

## 7. File Config Data ngoài JAR

Deploy không cần build lại image khi muốn thay phần lớn config. Một lựa chọn là mount file bên ngoài:

```text
/app/app.jar
/etc/catalog/application.yaml
```

Cấp từ lúc khởi động:

```bash
SPRING_CONFIG_ADDITIONALLOCATION=file:/etc/catalog/ \
java -jar /app/app.jar
```

Phân biệt:

- `spring.config.location`: thay thế các search location mặc định bằng location khai báo theo quy tắc Boot.
- `spring.config.additional-location`: bổ sung location bên ngoài location mặc định.

Nếu muốn giữ cả default trong JAR và overlay bên ngoài, `additional-location` thường là lựa chọn phù hợp hơn.

Ví dụ:

```yaml
# file trong JAR
app:
  request-timeout: 5s
  max-retries: 3
```

```yaml
# /etc/catalog/application.yaml
app:
  request-timeout: 8s
```

Env:

```bash
APP_REQUESTTIMEOUT=12s
```

Khi external file được nạp, `app.request-timeout` có thể là `12s` vì env ưu tiên cao hơn Config Data. `app.max-retries` vẫn lấy từ file trong JAR nếu không có nguồn khác ghi đè.

### 7.1. Khai báo vị trí đủ sớm

`spring.config.name`, `spring.config.location` và `spring.config.additional-location` ảnh hưởng giai đoạn Boot tìm/nạp Config Data rất sớm. Hãy cấp qua OS env, JVM system property hoặc CLI lúc startup, không đặt trong một `ApplicationRunner` và trông chờ hệ thống quay lại tải file.

### 7.2. Location groups có ảnh hưởng thứ tự file

Dấu phẩy và dấu chấm phẩy trong `spring.config.location` có semantics nhóm khác nhau. Nếu dự án có nhiều profile và locations, cần thử nghiệm precedence thực tế, không suy luận rằng chỉ thứ tự ký tự file path luôn quyết định ai thắng.

### 7.3. optional: không có nghĩa sửa lỗi config

`optional:file:/etc/catalog/` có thể cho phép location thiếu được bỏ qua. Nhưng một file có mặt mà sai định dạng hoặc value không chuyển kiểu được vẫn có thể gây lỗi. Với production location bắt buộc, không dùng optional vô thức để che thiếu mount.

## 8. spring.config.import và configuration tree

Một file có thể import thêm Config Data:

```properties
spring.config.import=file:/etc/catalog/extra.properties
```

Hoặc import tệp secret volume dạng một key mỗi file:

```properties
spring.config.import=configtree:/run/secrets/
```

Trong Config Data, file imported có quy tắc precedence so với document khai báo import. Tuy nhiên, nguồn import vẫn là **Config Data**, không tự trở thành OS environment chỉ vì nó nằm trong container.

### Ví dụ secret

Container:

```text
/run/secrets/
├── spring.datasource.username
└── spring.datasource.password
```

Import:

```properties
spring.config.import=configtree:/run/secrets/
```

Những file này đưa property `spring.datasource.username` và `spring.datasource.password` vào Environment. Nếu cũng cấp `SPRING_DATASOURCE_PASSWORD` bằng OS env, env thường có ưu tiên cao hơn imported configtree.

**Khuyến nghị:** hạn chế một credential tồn tại ở nhiều nguồn khác nhau. Việc env cao hơn file secret có thể khiến ứng dụng dùng một giá trị cũ, sai hoặc do người khác đặt. Quy tắc ưu tiên là kỹ thuật; “nguồn đáng tin cậy” phải được tổ chức xác định và bảo vệ quyền ghi.

## 9. Docker Compose: tách file mặc định và environment theo deployment

Giả sử JAR có:

```yaml
# application.yaml đóng gói
server:
  port: 8080
app:
  request-timeout: 5s
  max-retries: 3
  feature-enabled: true
```

`compose.yaml`:

```yaml
services:
  catalog:
    image: example/catalog:1.0
    ports:
      - "8080:8080"
    environment:
      SPRING_PROFILES_ACTIVE: "prod"
      APP_REQUESTTIMEOUT: "12s"
      APP_MAXRETRIES: "0"
      APP_FEATUREENABLED: "false"
```

Khi container chạy, OS environment của JVM chứa những giá trị đó. Nếu không có `-D`/CLI/JSON/custom source cao hơn, kết quả sau binding là `12s`, `0` và `false`. `server.port` vẫn từ Config Data với `8080`.

### 9.1. .env của Compose và env của container khác nhau

Một file tên `.env` đặt cạnh Compose:

```dotenv
APP_REQUESTTIMEOUT=12s
```

thường phục vụ **interpolation** của Compose; nó **không mặc nhiên đưa mọi biến trong file vào container**.

Để cấp vào service:

```yaml
services:
  catalog:
    image: example/catalog:1.0
    environment:
      APP_REQUESTTIMEOUT: "${APP_REQUESTTIMEOUT:-5s}"
```

hoặc dùng:

```yaml
services:
  catalog:
    image: example/catalog:1.0
    env_file:
      - ./catalog.env
```

Trong ví dụ đầu, `${APP_REQUESTTIMEOUT:-5s}` là **placeholder của Docker Compose**, được Compose giải quyết trước khi tạo container, không phải placeholder `@Value` của Spring. `env_file` cấp các biến được liệt kê vào container theo quy tắc Compose.

### 9.2. Hai tầng precedence riêng

Nếu `environment`, `env_file`, Compose interpolation và các tùy chọn Compose cùng đặt một biến, **Docker Compose** quyết định giá trị cuối của biến trong container. Sau đó **Spring Boot** mới quyết định giữa process environment và Config Data/JVM/CLI.

Không gộp hai thứ tự ưu tiên thành một. Khi nghi env sai, kiểm tra trước Compose đã đưa giá trị nào vào **đúng container JVM**, rồi kiểm tra Spring Binder.

### 9.3. Không sao chép secrets không cần thiết

Nếu dùng `secrets:` để mount file tại `/run/secrets/`, không cần đồng thời đưa plaintext secret vào `environment:` chỉ để dùng Spring Boot. Có thể import bằng `spring.config.import=configtree:/run/secrets/`. Bảo vệ host file, mount permissions, logs và quyền truy cập secret theo môi trường thật.

## 10. Kubernetes: ConfigMap, Secret, environment và volume

Kubernetes có nhiều cách đưa dữ liệu vào container, nhưng đối với Spring Boot cần quy về hai hình thức chính:

1. **Process environment**: `env`, `envFrom`, `configMapKeyRef`, `secretKeyRef`.
2. **Config Data file**: ConfigMap/Secret/projected volume được mount vào filesystem rồi Boot đọc từ `file:` hoặc `configtree:`.

### 10.1. Deployment với env

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
            - name: SPRING_PROFILES_ACTIVE
              value: "prod"
            - name: APP_REQUESTTIMEOUT
              value: "15s"
            - name: APP_MAXRETRIES
              value: "0"
            - name: APP_FEATUREENABLED
              value: "false"
```

Nếu file trong JAR đặt `app.request-timeout=5s`, OS environment do Kubernetes cấp có thể ghi đè thành `15s`.

### 10.2. Lấy value từ ConfigMap

```yaml
env:
  - name: APP_REQUESTTIMEOUT
    valueFrom:
      configMapKeyRef:
        name: catalog-settings
        key: request-timeout
```

Kubernetes đọc `request-timeout` từ ConfigMap rồi cấp vào env var `APP_REQUESTTIMEOUT`. Spring Boot nhìn thấy **tên biến đã cấp cho container**, không trực tiếp sử dụng tên ConfigMap object trong property lookup.

ConfigMap là nguồn cấu hình không nhạy cảm. Với password hoặc token, dùng Kubernetes Secret hoặc giải pháp quản lý bí mật được phê duyệt.

### 10.3. Mount ConfigMap thành file

```yaml
volumeMounts:
  - name: external-config
    mountPath: /etc/catalog
    readOnly: true
volumes:
  - name: external-config
    configMap:
      name: catalog-application-config
```

Giả sử nó tạo file:

```text
/etc/catalog/application.yaml
```

Boot có thể import:

```properties
spring.config.import=file:/etc/catalog/application.yaml
```

Nếu đồng thời có env `APP_REQUESTTIMEOUT=20s`, env thường vẫn thắng `app.request-timeout` trong file mount.

### 10.4. Mount Secret bằng configtree

```text
/etc/secrets/
├── spring.datasource.username
└── spring.datasource.password
```

```properties
spring.config.import=configtree:/etc/secrets/
```

Giá trị được đưa vào Config Data. Nếu đồng thời `SPRING_DATASOURCE_PASSWORD` tồn tại trong container, source environment thường cao hơn configtree. Tránh cấp credential trùng nguồn không cần thiết.

### 10.5. Đừng bỏ qua precedence trước Spring Boot

Kubernetes có quy tắc riêng khi nhiều mục `env` và `envFrom` cùng định nghĩa một environment variable. Spring Boot không thấy toàn bộ bản gốc ConfigMap/Secret sau khi Kubernetes đã xây dựng process environment cuối; nó chỉ thấy biến mà JVM nhận được.

Vì vậy cần kiểm tra hai lần: Kubernetes chọn biến nào, sau đó Spring Boot chọn value nào giữa env và các PropertySource khác.

## 11. SPRING_APPLICATION_JSON là nguồn cao hơn OS environment

Spring Boot 3.3 có thể nhận một object JSON qua `SPRING_APPLICATION_JSON`:

```bash
SPRING_APPLICATION_JSON='{"app":{"request-timeout":"20s"}}' \
java -jar app.jar
```

Dữ liệu JSON được thêm như một PropertySource riêng, với độ ưu tiên thông thường **cao hơn OS environment và Java system properties**, nhưng thấp hơn command-line arguments.

Ví dụ đồng thời:

```text
application.yaml         -> app.request-timeout=5s
APP_REQUESTTIMEOUT       -> app.request-timeout=10s
-Dapp.request-timeout    -> app.request-timeout=15s
SPRING_APPLICATION_JSON  -> app.request-timeout=20s
--app.request-timeout    -> app.request-timeout=30s
```

Kết quả mặc định:

```text
app.request-timeout=30s
```

Nếu bỏ CLI thì JSON có thể thắng với 20s. Nếu bỏ JSON thì `-D` có thể thắng 15s. Nếu bỏ `-D` thì env có thể thắng 10s.

### 11.1. JSON null không xóa property từ nguồn thấp

Ví dụ:

```json
{"app":{"mode":null}}
```

Một giá trị JSON `null` được Spring PropertySource resolver xem tương đương thiếu property trong quá trình resolve, nên không nên dùng JSON null để “xóa” một property vốn đã có từ nguồn thấp hơn. Muốn tắt một feature, dùng boolean false theo contract hoặc sửa nguồn cấu hình.

### 11.2. Bảo mật JSON env

Không sử dụng `SPRING_APPLICATION_JSON` như một secret store mặc định. Nó có thể đưa nhiều credential vào process environment, làm tăng rủi ro khi dump config hoặc chụp logs. Với secret, ưu tiên cơ chế secret mount hoặc secret manager của tổ chức.

## 12. Missing, chuỗi rỗng, 0, false và giá trị sai định dạng

Các giá trị này có semantics khác nhau:

| Trường hợp | Ý nghĩa khi chọn source |
| --- | --- |
| Không có env var | Có thể lấy property từ Config Data thấp hơn |
| Env var chứa `""` | Chuỗi rỗng có thể được xem là value có mặt; phụ thuộc kiểu đích |
| Env var chứa `0` | Một giá trị số explicit |
| Env var chứa `false` | Một giá trị boolean explicit |
| Env var chứa `abc` cho kiểu int | Có thể lỗi conversion thay vì fallback |
| Env var có tên sai | Không override property dự định |
| Env var bị JVM không nhận | Environment source không có property đó |

Ví dụ:

```properties
app.name=Catalog
app.retries=3
app.enabled=true
```

Môi trường:

```bash
APP_NAME=""
APP_RETRIES=0
APP_ENABLED=false
```

Sau binding:

- `app.name` với target String có thể thành chuỗi rỗng, ghi đè `Catalog`.
- `app.retries` thành `0`, không phải 3.
- `app.enabled` thành `false`, không phải true.

Một số target typed properties có cách xử lý empty string khác nhau; không suy luận empty tự động thành missing/zero/false. Với `String` bắt buộc, có thể dùng `@NotBlank` để từ chối chuỗi rỗng.

### 12.1. Biến shell chưa được export

Trên Linux:

```bash
APP_REQUESTTIMEOUT=10s
java -jar app.jar
```

Một shell variable không export có thể không được truyền cho tiến trình JVM. Để bảo đảm:

```bash
export APP_REQUESTTIMEOUT=10s
java -jar app.jar
```

hoặc:

```bash
APP_REQUESTTIMEOUT=10s java -jar app.jar
```

Biến trong một terminal quản trị không chứng minh đã tồn tại trong process JVM do systemd/Docker/Kubernetes tạo ra.

## 13. Conversion: env có thể thắng nhưng sai đơn vị

Giả sử file:

```properties
app.request-timeout=5s
app.cache-size=32MB
```

Môi trường:

```bash
APP_REQUESTTIMEOUT=10
APP_CACHESIZE=64
```

Nếu target Java lần lượt là `Duration` và `DataSize`, và không có annotation đổi đơn vị:

- `Duration` số trần mặc định tính bằng **mili giây**: `10` = 10ms.
- `DataSize` số trần mặc định tính bằng **byte**: `64` = 64B.

Đây là hai env overrides đúng tên và có thể bind thành công, nhưng **sai về ngữ nghĩa** nếu người vận hành muốn 10 giây và 64MB.

Nên dùng:

```bash
APP_REQUESTTIMEOUT=10s
APP_CACHESIZE=64MB
```

### 13.1. Không tự fallback khi env sai kiểu

File:

```properties
app.max-retries=3
```

Env:

```bash
APP_MAXRETRIES=abc
```

Nếu target `int`, Binder có thể chọn value `abc` từ nguồn cao rồi thất bại khi chuyển kiểu. **Không có quy tắc chung “env sai thì tự quay về giá trị 3 từ file”.** Fail-fast thường an toàn hơn khi cấu hình quan trọng bị lỗi.

### 13.2. Bean Validation là bước độc lập

```java
@Min(1)
@Max(50)
private int workerCount = 4;
```

`APP_WORKERCOUNT=0` có thể parse thành int 0 nhưng vi phạm `@Min(1)`. `APP_WORKERCOUNT=abc` có thể lỗi conversion trước validation. Cần phân biệt lỗi source precedence, lỗi kiểu và lỗi domain policy.

## 14. List và Map có semantics khác nhau

Không nên áp dụng máy móc câu “env thắng file” cho toàn bộ cấu trúc nested.

### 14.1. List thường được thay thế

File:

```yaml
app:
  servers:
    - https://a.example.test
    - https://b.example.test
```

Nguồn cao hơn có:

```properties
app.servers[0]=https://prod.example.test
```

List sau binding có thể chỉ là:

```text
["https://prod.example.test"]
```

**Không tự nối** `b.example.test` từ nguồn thấp vào. Nếu muốn List gồm hai phần tử trong env, dùng các biến tương ứng:

```bash
APP_SERVERS_0_=https://prod.example.test
APP_SERVERS_1_=https://backup.example.test
```

Quy tắc môi trường: chỉ số List được bao quanh bằng `_`. Đối với object nested `app.clients[0].base-url`, env theo quy tắc là `APP_CLIENTS_0_BASEURL`.

### 14.2. Map có thể hợp nhất các key

File:

```yaml
app:
  labels:
    team: platform
    stage: default
```

Env:

```bash
APP_LABELS_STAGE=production
APP_LABELS_OWNER=catalog
```

Với `Map<String,String> labels`, kết quả thường:

```text
team  -> platform
stage -> production
owner -> catalog
```

Key `team` không bị xóa chỉ vì env có thêm hai Map entries.

### 14.3. Map với object value

File:

```yaml
app:
  clients:
    billing:
      base-url: https://billing.example.test
      connect-timeout: 2s
      enabled: true
```

Env:

```bash
APP_CLIENTS_BILLING_CONNECTTIMEOUT=5s
APP_CLIENTS_BILLING_ENABLED=false
```

Với `Map<String,ClientProperties>`, Binder có thể kết hợp:

```text
billing.baseUrl        = https://billing.example.test
billing.connectTimeout = 5s
billing.enabled        = false
```

Những property con độc lập có thể đến từ nhiều nguồn. Tuy nhiên, một List nằm trong value object vẫn có quy tắc replacement riêng.

### 14.4. Map keys đặc biệt

Map key chứa slash/dấu chấm cần cú pháp bracket notation khi muốn bảo toàn chính xác trong file:

```properties
app.routes.[/api/v1]=billing
```

YAML:

```yaml
app:
  routes:
    "[/api/v1]": billing
```

Environment variables không phải lúc nào cũng biểu diễn được một Map key có ký tự đặc biệt hoặc phân biệt case. Nếu cần key nguyên văn, Config Data với bracket notation thường rõ hơn.

## 15. Xác định nguồn có hiệu lực khi debug

Một hướng đơn giản là kiểm tra giá trị không nhạy cảm từ `Environment` và bean đã bind:

```java
package com.example.demo;

import com.example.demo.config.AppProperties;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;

@Configuration(proxyBeanMethods = false)
class ConfigDiagnostics {

    @Bean
    ApplicationRunner showConfig(
            Environment env, AppProperties props) {
        return args -> {
            System.out.println("Resolved app.request-timeout: "
                    + env.getProperty("app.request-timeout"));
            System.out.println("Bound timeout: "
                    + props.getRequestTimeout());
        };
    }
}
```

Ví dụ file `5s`, env `10s`, không có source cao hơn, output có thể là:

```text
Resolved app.request-timeout: 10s
Bound timeout: PT10S
```

**Không áp dụng cho secret:** không in password, API token, full `Environment` hoặc object chứa credential. Có thể kiểm tra presence/nguồn thay vì value.

### 15.1. Liệt kê tên PropertySource

```java
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.PropertySource;

public void showSourceNames(ConfigurableEnvironment env) {
    for (PropertySource<?> source : env.getPropertySources()) {
        System.out.println(source.getName());
    }
}
```

Điều này giúp quan sát danh sách nguồn và thứ tự tương đối; nó không phải bằng chứng duy nhất value của một property đã được bind từ đâu. Tên env var và tên canonical file có thể được adapter/relaxed binding xử lý khác nhau.

### 15.2. Origin từ Config Data

Khi binding thất bại, failure analysis có thể đưa `Property`, `Value`, `Origin` và `Reason`. Ví dụ định dạng minh họa:

```text
Property: app.max-retries
Value: "bad-value"
Origin: systemEnvironment
Reason: failed to convert String to int
```

Với file, Origin có thể chứa tên file và số dòng. Với biến môi trường, có thể không có dòng/cột. Không có line number không đồng nghĩa property vắng mặt.

### 15.3. Actuator

`/actuator/env` và `/actuator/configprops` có thể hỗ trợ chẩn đoán PropertySources và configuration-properties beans. Hai endpoint này cần được bảo vệ và cấu hình masking/sanitization. Không expose public hoặc gửi raw output nhạy cảm vào ticket.

## 16. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| Env có nhưng file vẫn thắng | Sai tên env hoặc không vào process JVM | Kiểm tra mapping/cấp biến |
| `APP_MAX_RETRIES` không hoạt động như `app.max-retries` | Dấu gạch dưới tạo phân cấp khác | Dùng `APP_MAXRETRIES` |
| Docker Compose .env có value nhưng container không có | .env dùng interpolation, thiếu `environment`/`env_file` | Cấp env cho service |
| Kubernetes ConfigMap có key nhưng Spring không thấy | Pod không dùng key qua env/mount | Thêm `env`/`envFrom`/volume mount |
| JVM `-D` thắng env | Thứ tự mặc định | Sửa/gỡ `-D` nếu không chủ đích |
| CLI thắng env | Command-line source ưu tiên cao | Kiểm tra entrypoint và args |
| `application-prod.yaml` không thắng env | Profile file vẫn là Config Data | Điều chỉnh env hoặc bỏ override |
| Env chứa `false`/`0` vẫn ghi đè | Đây là value explicit | Không xem là missing |
| Env rỗng ghi đè String default | Empty khác missing | Validation hoặc bỏ env |
| Env chứa `10` nhưng timeout quá ngắn | Duration mặc định ms | Viết `10s` |
| Env chứa `64` nhưng cache quá nhỏ | DataSize mặc định B | Viết `64MB` |
| Env sai kiểu làm app không khởi động | Conversion error của value ưu tiên cao | Sửa value, không mong fallback |
| Env override List làm mất phần tử từ file | List replacement | Cấp trọn List ở nguồn cao |
| Map giữ key từ file | Map merge | Đây thường là hành vi đúng |
| Bean không nhận dù Environment có key | Chưa đăng ký bean hoặc thiếu setter/constructor | Sửa `@ConfigurationProperties` |
| File thay đổi mà JVM dùng giá trị cũ | Config Data/bean không tự reload | Rollout/restart/refresh riêng |
| Một nguồn custom thắng env | Custom PropertySource priority | Xem thứ tự Environment thực tế |
| @Value placeholder camelCase khó nhận alias | Placeholder không canonical | Dùng kebab-case |
| App chỉ sai ở prod | Profile, mount, CLI hoặc env khác dev | So sánh runtime sources |

### Lỗi kỹ thuật không phải lỗi precedence

Nếu JavaBean chỉ có getter scalar, thiếu setter, Binder có thể không cập nhật target dù env đã được chọn đúng. Nếu class `@ConfigurationProperties` chưa đăng ký, không có Spring bean để inject. Nếu service tự tạo `new AppProperties()`, đó là object Java chưa trải qua binding. Phân biệt sai **nguồn**, sai **kiểu**, sai **bean registration** và sai **nơi sử dụng**.

## 17. Kiểm thử thứ tự ưu tiên

### 17.1. Test binding cơ bản bằng ApplicationContextRunner

```java
package com.example.demo;

import static org.assertj.core.api.Assertions.assertThat;

import com.example.demo.config.AppProperties;
import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

class AppPropertiesTest {

    private final ApplicationContextRunner runner =
        new ApplicationContextRunner()
            .withUserConfiguration(Config.class);

    @Test
    void canBindExplicitValues() {
        runner.withPropertyValues(
            "app.request-timeout=10s",
            "app.max-retries=0",
            "app.feature-enabled=false")
        .run(context -> {
            assertThat(context).hasNotFailed();
            AppProperties props =
                    context.getBean(AppProperties.class);

            assertThat(props.getRequestTimeout())
                    .isEqualTo(java.time.Duration.ofSeconds(10));
            assertThat(props.getMaxRetries()).isZero();
            assertThat(props.isFeatureEnabled()).isFalse();
        });
    }

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(AppProperties.class)
    static class Config { }
}
```

Test trên xác minh việc bind vào model. Nó **không tự tái hiện mọi bước** nạp Config Data, profile và OS environment của một `SpringApplication` chạy production.

### 17.2. Integration/smoke test file vs env

Để kiểm chứng precedence thật sự:

1. Build JAR với `application.yaml` đặt `app.request-timeout=5s`.
2. Chạy một lần **không** có `APP_REQUESTTIMEOUT`, xác nhận 5s.
3. Chạy lại với `APP_REQUESTTIMEOUT=10s`, xác nhận 10s.
4. Chạy với thêm `-Dapp.request-timeout=12s`, xác nhận 12s.
5. Chạy với thêm `--app.request-timeout=15s`, xác nhận 15s.
6. Thử `APP_REQUESTTIMEOUT=bad`, xác nhận conversion/validation behavior đúng chính sách.
7. Không thực hiện test bằng credential production thật.

Ma trận kết quả mặc định:

| File | Env | `-D` | CLI | Kết quả |
| --- | --- | --- | --- | --- |
| `5s` | Vắng | Vắng | Vắng | `5s` |
| `5s` | `10s` | Vắng | Vắng | `10s` |
| `5s` | `10s` | `12s` | Vắng | `12s` |
| `5s` | `10s` | `12s` | `15s` | `15s` |
| `5s` | `invalid` | Vắng | Vắng | Có thể lỗi conversion |
| `5s` | `0ms` | Vắng | Vắng | `0ms` nếu type/validation cho phép |

Một test chỉ khẳng định context khởi động không thể phát hiện việc bare `10` được hiểu thành 10ms thay vì 10s. Assert **typed value và đơn vị**.

## 18. Cấu hình sớm, sửa file và restart

Một số property điều khiển quá trình khởi động:

```text
spring.config.name
spring.config.location
spring.config.additional-location
spring.profiles.active
spring.main.*
logging.*
```

Chúng có thể được sử dụng trước khi ApplicationContext hoàn tất. Muốn thay đổi vị trí nạp file hoặc active profile, phải cung cấp thông tin đủ sớm theo quy trình khởi động.

### 18.1. Đổi environment của deployment không làm JVM đang chạy tự đổi

Env vars thường được cấp khi tiến trình JVM/container được tạo. Sửa Kubernetes Deployment/ConfigMap hoặc Compose YAML không tự thay đổi environment của JVM đang chạy. Thông thường cần tạo Pod/container mới bằng rollout/restart.

### 18.2. File mount thay đổi không đồng nghĩa bean tự rebinding

Dù một ConfigMap/Secret volume có thể được Kubernetes cập nhật theo cơ chế volume projection, Spring Boot 3.3 không tự reload toàn bộ Config Data và làm mới các `@ConfigurationProperties` beans/connection pools chỉ vì file trên đĩa đã đổi. Nếu cần hot refresh, phải thiết kế hạ tầng riêng, kèm validation, concurrency control và cách tái tạo client/resource.

Một giá trị có hiệu lực ở thời điểm startup là một **snapshot thực tế** của ứng dụng, không nhất thiết bằng nội dung file hiện thấy sau vài giờ.

## 19. @PropertySource và custom precedence

`@PropertySource` có thể thêm một file vào Environment:

```java
@Configuration
@PropertySource("classpath:custom.properties")
public class LegacyConfig {
}
```

Nhưng theo thứ tự mặc định Boot, nguồn này thấp hơn Config Data và OS environment, đồng thời được thêm khi context refresh. Nó không phải cách đáng tin để “ép file luôn thắng env”, đặc biệt với các property startup sớm.

Có thể tùy chỉnh precedence bằng `EnvironmentPostProcessor` hoặc cấu hình hạ tầng riêng, nhưng đó là thay đổi chính sách có ảnh hưởng rộng:

- Làm khác hành vi tiêu chuẩn mà người vận hành quen thuộc.
- Có thể làm env overrides trong Docker/Kubernetes không còn hiệu lực.
- Tăng khó khăn tìm source khi chẩn đoán.
- Yêu cầu test thứ tự nguồn và bootstrap timing.

Trong đa số trường hợp, nên giữ defaults/precedence thông thường và thiết lập **quy trình quản trị nguồn** thay vì đảo thứ tự một cách ngầm định.

## 20. Quy trình điều tra khi env không thắng file

1. Xác định property canonical, ví dụ `app.request-timeout`.
2. Đổi sang env name chuẩn: `APP_REQUESTTIMEOUT`.
3. Xác nhận biến thực sự tồn tại trong **đúng tiến trình JVM**.
4. Xem file nào được nạp: packaged/external, profile, Config Data import.
5. Kiểm tra active profile `spring.profiles.active`.
6. Kiểm tra `-D`, `SPRING_APPLICATION_JSON` và CLI có key tương ứng không.
7. Nếu có custom bootstrap, kiểm tra các `PropertySources` thực tế.
8. Kiểm tra bean `@ConfigurationProperties` đã đăng ký đúng và có setter/constructor phù hợp.
9. Kiểm tra raw effective value trên key **không nhạy cảm**.
10. Kiểm tra converted type, unit annotation và Bean Validation constraints.
11. Xem client/service có thật sự dùng bean đã bind hay hard-code value ở chỗ khác.
12. Sửa đúng nguồn đang thắng rồi chạy smoke test/rollout lại.

Sơ đồ ngắn:

```text
Giá trị runtime khác file?
      |
      v
Có env tương ứng?
  |            |
 Không         Có
  |            |
  v            v
Xem Config   Env name đúng?
Data/profile  |          |
/import       Không      Có
              |          |
              v          v
           Sửa tên     Có source cao hơn env?
                         |          |
                         Có        Không
                         |          |
                         v          v
                    Kiểm tra     Kiểm tra bind,
                    -D/JSON/CLI   conversion,
                                  validation,
                                  nơi dùng value
```

## 21. Chiến lược cấu hình triển khai đề xuất

| Mục tiêu | Nguồn nên dùng | Lý do |
| --- | --- | --- |
| Default không nhạy cảm | `application.yaml` trong JAR | Giữ contract gần code |
| Default theo profile | `application-prod.yaml` | Cấu hình theo nhóm môi trường |
| Override một vài key theo namespace | OS environment | Dễ thay giữa deployments |
| Cấu hình lớn ngoài image | External Config Data file | Có thể mount/phiên bản hóa riêng |
| Credential nhạy cảm | Docker/Kubernetes Secret volume, configtree hoặc secret manager | Tránh commit/bake plaintext vào image |
| Override khẩn cấp có kiểm soát | JVM -D hoặc CLI | Ưu tiên cao, cần audit |
| Nested object và validation | `@ConfigurationProperties` | Type-safe binding |
| Map keys cần hợp nhất | Map binding | Có merge theo key |
| Danh sách phải nhất quán | Cấp trọn List từ một nguồn | Tránh hiểu sai replacement |
| Cần biết value nào chạy thực tế | Safe diagnostic, integration test | Không dựa vào file đơn lẻ |

Một source có thứ tự cao hơn không có nghĩa đó là nguồn **được phép** thay đổi theo quy trình quản trị. Cần phân quyền ai được sửa deployment env, JVM args, Config Data mount và secret source.

## 22. Checklist release

- [ ] Mọi property được tài liệu hóa bằng lowercase kebab-case.
- [ ] Biến OS env đổi tên đúng theo dot → underscore, dash → remove, uppercase.
- [ ] Env thực sự vào container/process JVM, không chỉ vào Compose project-level .env.
- [ ] Không có alias trùng property với tên khác khó hiểu.
- [ ] File Config Data/profile/import được nạp đúng location.
- [ ] Đã kiểm tra các nguồn cao hơn như `-D`, JSON và CLI.
- [ ] `@ConfigurationProperties` beans được đăng ký và bind đúng.
- [ ] 0, false và empty có ý nghĩa rõ theo hợp đồng cấu hình.
- [ ] `Duration`/`DataSize` dùng hậu tố đơn vị explicit.
- [ ] Có Bean Validation hoặc checks cho các ràng buộc quan trọng.
- [ ] List và Map được test đúng theo semantics merge/replacement.
- [ ] Secrets không bị nhân bản không cần thiết giữa file và env.
- [ ] Actuator/logs không làm lộ credential.
- [ ] Có kiểm tra effective values không nhạy cảm ở startup.
- [ ] Có smoke test trong container với file/default/env overrides thật.
- [ ] Thay đổi env/file có kế hoạch restart/rollout hoặc refresh chuyên biệt.
- [ ] Có đường rollback khi config mới làm startup thất bại.
- [ ] Runbook nêu rõ nơi quản lý và chủ sở hữu từng loại cấu hình.

## 23. Tài liệu tham khảo

- **Spring Boot 3.3 — Externalized Configuration** (PropertySource Order, Config Data, profile files, imports, configuration trees, relaxed binding): https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- **Spring Boot 3.3 — Binding From Environment Variables** (canonical name → OS env): https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.relaxed-binding.environment-variables
- **Spring Boot 3.3 — Merging Complex Types** (List replacement, Map merge): https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.merging-complex-types
- **Spring Boot 3.3 — @ConfigurationProperties API**: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/ConfigurationProperties.html
- **Spring Framework — Environment Abstraction**: https://docs.spring.io/spring-framework/reference/core/beans/environment.html
- **Docker Compose — Environment Variables Precedence**: https://docs.docker.com/compose/how-tos/environment-variables/envvars-precedence/
- **Kubernetes — Define Environment Variables for a Container**: https://kubernetes.io/docs/tasks/inject-data-application/define-environment-variable-container/
- **Kubernetes — ConfigMaps / Secrets**: https://kubernetes.io/docs/concepts/configuration/configmap/ và https://kubernetes.io/docs/concepts/configuration/secret/

## 24. Ghi nhớ cuối bài

Khi **cùng một canonical property** được cung cấp trong file cấu hình và environment của JVM, Spring Boot 3.3 mặc định sẽ chọn theo thứ tự:

```text
Config Data file
      <
OS environment
      <
Java -D system properties
      <
SPRING_APPLICATION_JSON
      <
Command-line --key=value
```

**File đặt default, env đặt override cho deployment, nguồn cao hơn vẫn có thể thắng env.** Muốn ứng dụng chạy đúng, cần đảm bảo tên env ánh xạ đúng property, giá trị chuyển đổi được sang Java type, beans được bind đúng, validation có hiệu lực và runtime thật sự sử dụng kết quả đã chọn. Với Docker/Kubernetes, nhớ thêm một tầng cấu hình của nền tảng trước khi JVM nhìn thấy process environment.
