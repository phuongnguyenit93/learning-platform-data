# Liên kết kiểu JavaBean qua getter, setter và giá trị khởi tạo trong Spring Boot 3.3

## 1. Bản chất của JavaBean binding

`@ConfigurationProperties` cho phép Spring Boot gom các giá trị cấu hình cùng prefix thành một đối tượng Java có kiểu rõ ràng. Với **JavaBean binding**, Spring Boot tạo (hoặc nhận) một đối tượng có thể thay đổi trạng thái rồi gán property thông qua **JavaBean property descriptors**: getter, setter và đôi khi là getter trả về một đối tượng/collection đã được khởi tạo để Binder có thể cập nhật trực tiếp.

Ví dụ thay vì đọc bốn giá trị rời rạc:

```java
@Value("${app.name:Catalog}")
String name;

@Value("${app.enabled:true}")
boolean enabled;
```

ta đặt chúng trong một class:

```java
@ConfigurationProperties(prefix = "app")
public class AppProperties {
    private String name = "Catalog";
    private boolean enabled = true;

    public String getName() { return name; }
    public void setName(String name) { this.name = name; }

    public boolean isEnabled() { return enabled; }
    public void setEnabled(boolean enabled) { this.enabled = enabled; }
}
```

Từ file:

```properties
app.name=Order Service
app.enabled=false
```

Binder tìm `app.name` và `app.enabled`, chuyển kiểu nếu cần, rồi gọi các setter để cập nhật object. Kết quả `name="Order Service"` và `enabled=false`, **ghi đè** các giá trị khởi tạo tương ứng.

Điểm mấu chốt: giá trị mặc định đặt bằng phép gán trường trong JavaBean **chỉ có cơ hội được giữ lại khi Binder không bind một giá trị khác cho property đó**. Không được hiểu `null`, `""`, `0` và `false` là một trạng thái như nhau.

## 2. JavaBean binding diễn ra khi nào?

Trong một ứng dụng Spring Boot tiêu chuẩn:

1. Spring Boot xây dựng `Environment` từ các nguồn: Config Data (`application.properties`, YAML...), OS environment variables, JVM system properties, command-line options và những nguồn khác.
2. Spring Boot đăng ký bean cấu hình thông qua `@ConfigurationPropertiesScan`, `@EnableConfigurationProperties` hoặc cơ chế bean thông thường thích hợp.
3. Đối với **JavaBean binding**, đối tượng có constructor không tham số được khởi tạo; các field initializer và constructor body của nó chạy trước.
4. Binder đọc các property theo prefix, ánh xạ tên qua relaxed binding, chuyển giá trị từ nguồn sang kiểu đích và cập nhật những JavaBean properties có thể bind.
5. Các property không được cung cấp có thể giữ giá trị đã khởi tạo, trừ khi cơ chế lập trình khác làm thay đổi chúng. Bean cấu hình đã bind được tiêm vào service khác qua constructor injection.

Đây là mô hình khái quát. `@ConfigurationProperties` cũng hỗ trợ **constructor binding** và record, nơi các tham số được truyền vào constructor; cách đó có quy tắc khởi tạo khác. Bài này tập trung vào **JavaBean binding bằng getter/setter**.

### Điều kiện cơ bản cho JavaBean

Một JavaBean cấu hình thông thường cần:

- Class có thể được khởi tạo, thường là `public` và có **constructor không tham số**.
- Các giá trị scalar muốn ghi đè từ cấu hình có **setter** phù hợp (`setName`, `setMaxRetries`...).
- Getter phù hợp (`getName` hoặc `isEnabled` cho boolean) để sử dụng hoặc cho Binder truy cập object, map, collection.
- Các kiểu dữ liệu có thể được chuyển đổi từ giá trị cấu hình, ví dụ `String`, `int`, `boolean`, `Duration`, `List<String>`, `Map<String,String>`.
- Bean được **đăng ký** với Spring; chỉ có annotation `@ConfigurationProperties` trên một class bình thường chưa bảo đảm class đó đã trở thành Spring bean.

Trong JavaBean binding mặc định, Binder dựa vào **JavaBean properties**, không phải thao tác truy cập trực tiếp mọi private field bằng reflection bất kể có getter/setter hay không. Chỉ khai báo `private String name;` rồi mong Binder tự thay đổi nó là một giả định sai.

## 3. Ví dụ hoàn chỉnh: JavaBean có scalar, list, map và nested object

Ví dụ dưới đây dùng **Java 17+**, tương thích Spring Boot 3.3. Tạo file `src/main/java/com/example/demo/config/AppProperties.java`:

```java
package com.example.demo.config;

import java.time.Duration;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public class AppProperties {

    // Giá trị ban đầu: được giữ khi property tương ứng không được bind.
    private String name = "Catalog";
    private boolean enabled = true;
    private int maxRetries = 3;
    private Duration connectTimeout = Duration.ofSeconds(2);

    // Collection: dùng setter để hỗ trợ các cách bind thông thường.
    private List<String> regions =
            new ArrayList<>(List.of("ap-southeast-1"));

    // Map đã khởi tạo có thể được Binder cập nhật qua getter.
    private final Map<String, String> labels = new LinkedHashMap<>();

    // Nested object đã khởi tạo có thể được cập nhật qua getter.
    private final Security security = new Security();

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public int getMaxRetries() {
        return maxRetries;
    }

    public void setMaxRetries(int maxRetries) {
        this.maxRetries = maxRetries;
    }

    public Duration getConnectTimeout() {
        return connectTimeout;
    }

    public void setConnectTimeout(Duration connectTimeout) {
        this.connectTimeout = connectTimeout;
    }

    public List<String> getRegions() {
        return regions;
    }

    public void setRegions(List<String> regions) {
        this.regions = regions;
    }

    public Map<String, String> getLabels() {
        return labels;
    }

    public Security getSecurity() {
        return security;
    }

    public static class Security {
        private String username = "reader";
        private List<String> roles = new ArrayList<>(List.of("USER"));

        public String getUsername() {
            return username;
        }

        public void setUsername(String username) {
            this.username = username;
        }

        public List<String> getRoles() {
            return roles;
        }

        public void setRoles(List<String> roles) {
            this.roles = roles;
        }
    }
}
```

Đặc điểm được chủ ý thể hiện:

- `name`, `enabled`, `maxRetries`, `connectTimeout` là scalar/giá trị có kiểu: đều có getter và setter.
- `regions` được khởi tạo với một phần tử và **vẫn có setter**, để hỗ trợ cả cách cấu hình list theo index lẫn dạng chuỗi phân tách bằng dấu phẩy.
- `labels` là một **Map đã khởi tạo**, field `final` và **chỉ có getter**: Binder có thể thay đổi nội dung Map mà không cần thay tham chiếu field.
- `security` là một **nested JavaBean đã khởi tạo**, field `final` và **chỉ có getter**: Binder có thể lấy instance hiện tại, sau đó gọi setter trên các property con.
- `Security.roles` là List có getter/setter, cũng có giá trị ban đầu. Từng property con có thể được ghi đè độc lập khi phù hợp.

### Đăng ký bean cấu hình

Tại `src/main/java/com/example/demo/DemoApplication.java`:

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

`@ConfigurationPropertiesScan` quét class được đánh dấu `@ConfigurationProperties` trong package của ứng dụng và các package con, bao gồm `com.example.demo.config` trong ví dụ.

Một cách thay thế khi muốn đăng ký tường minh:

```java
@SpringBootApplication
@EnableConfigurationProperties(AppProperties.class)
public class DemoApplication {
    // main(...) như bình thường
}
```

Với cách thứ hai cần import `org.springframework.boot.context.properties.EnableConfigurationProperties`. Chỉ dùng một chiến lược đăng ký rõ ràng; tránh vô tình khai báo hai bean tương đương nếu thêm `@Component` và scan không được thiết kế phù hợp.

### File cấu hình bằng .properties

```properties
# src/main/resources/application.properties
app.name=Order Service
app.enabled=false
app.max-retries=0
app.connect-timeout=5s

app.regions[0]=ap-southeast-1
app.regions[1]=eu-west-1

app.labels.team=platform
app.labels.env=staging

app.security.username=operator
app.security.roles[0]=AUDITOR
app.security.roles[1]=ADMIN
```

### File cấu hình bằng YAML tương đương

```yaml
# src/main/resources/application.yaml
app:
  name: Order Service
  enabled: false
  max-retries: 0
  connect-timeout: 5s
  regions:
    - ap-southeast-1
    - eu-west-1
  labels:
    team: platform
    env: staging
  security:
    username: operator
    roles:
      - AUDITOR
      - ADMIN
```

Hai ví dụ file là **lựa chọn thay thế**, không cần đặt đồng thời trong cùng location. Trong trường hợp một location có cả .properties và YAML, Spring Boot ưu tiên file .properties khi trùng basename.

### Kết quả sau khi bind

Khi ứng dụng khởi chạy với một trong hai file trên và không có nguồn ưu tiên cao hơn ghi đè:

| Property của `AppProperties` | Giá trị khởi tạo | Giá trị sau bind |
| --- | --- | --- |
| `name` | `"Catalog"` | `"Order Service"` |
| `enabled` | `true` | `false` |
| `maxRetries` | `3` | `0` |
| `connectTimeout` | `2s` | `5s` |
| `regions` | `["ap-southeast-1"]` | `["ap-southeast-1", "eu-west-1"]` |
| `labels` | Map rỗng | `team=platform`, `env=staging` |
| `security.username` | `"reader"` | `"operator"` |
| `security.roles` | `["USER"]` | `["AUDITOR", "ADMIN"]` |

Không có bước bắt buộc phải gọi thủ công `load()` hoặc `bind()` trong ứng dụng chỉ để nhận các property này; `@ConfigurationProperties` đã được đăng ký và Boot thực hiện binding khi tạo/khởi tạo bean.

## 4. Getter và setter có nhiệm vụ khác nhau

### 4.1. Scalar thường phải có setter

Đối với String, số, boolean, `Duration`, enum..., cách JavaBean phổ biến là:

```java
private int maxRetries = 3;

public int getMaxRetries() {
    return maxRetries;
}

public void setMaxRetries(int maxRetries) {
    this.maxRetries = maxRetries;
}
```

Binder ánh xạ cấu hình như `app.max-retries=5` vào property `maxRetries` và gọi setter với số nguyên đã chuyển kiểu. Nếu **không có setter**, một giá trị scalar chỉ đọc thường không được Binder cập nhật theo JavaBean binding; muốn trường bất biến được đặt ngay khi tạo instance, dùng constructor binding.

Với boolean, tên getter JavaBean thường là `isEnabled()`:

```java
private boolean enabled = true;

public boolean isEnabled() { return enabled; }
public void setEnabled(boolean enabled) { this.enabled = enabled; }
```

`isEnabled` không có nghĩa giá trị mặc định là true; nó chỉ là quy ước tên getter boolean. Setter vẫn có thể nhận `false`.

### 4.2. Getter không chỉ dành để đọc từ service

Getter cũng giúp Binder tìm object hiện tại để **cập nhật bên trong**. Hai trường hợp quan trọng:

```java
private final Map<String, String> labels = new LinkedHashMap<>();
public Map<String, String> getLabels() { return labels; }
```

và:

```java
private final Security security = new Security();
public Security getSecurity() { return security; }
```

Trong trường hợp Map/nested POJO này, Binder có thể lấy tham chiếu qua getter và cập nhật entry/property con mà **không cần** `setLabels(...)` hay `setSecurity(...)`.

Ngược lại, getter-only trả về object **chưa khởi tạo** không bảo đảm có thể bind nested data:

```java
// Rủi ro: security là null và không có setter để gán object mới.
private Security security;
public Security getSecurity() { return security; }
```

Nếu muốn Binder tạo nested object khi cần, có thể thêm setter:

```java
private Security security;

public Security getSecurity() { return security; }
public void setSecurity(Security security) { this.security = security; }
```

Khi đó Binder có con đường để gán một instance `Security` mới, với điều kiện lớp con có cách tạo instance phù hợp. Nếu không muốn setter cho nested object, hãy khởi tạo nó ngay ở field hoặc constructor:

```java
private final Security security = new Security();
public Security getSecurity() { return security; }
```

### 4.3. Getter-only Map cần có giá trị mutable

Một Map được khởi tạo và có getter thường đủ:

```java
private final Map<String, String> labels = new HashMap<>();

public Map<String, String> getLabels() {
    return labels;
}
```

Nhưng không nên dùng immutable Map nếu Binder cần cập nhật trực tiếp:

```java
// Không thích hợp làm Map getter-only để Binder thêm entry.
private final Map<String, String> labels = Map.of();

public Map<String, String> getLabels() {
    return labels;
}
```

`Map.of()` tạo một Map không cho thay đổi nội dung; cơ chế binding qua getter có thể thất bại hoặc không đạt kỳ vọng nếu không có setter cho phép thay thế toàn Map. Một `LinkedHashMap` hoặc `HashMap` mutable phù hợp hơn với JavaBean binding kiểu này.

## 5. Collection và array: các ngoại lệ phải nhớ

Spring Boot 3.3 có các trường hợp getter-only đặc biệt, nhưng **khuyến nghị thêm setter cho List/collection** để hoạt động nhất quán với các dạng đầu vào.

### 5.1. List có setter: lựa chọn ổn định

```java
private List<String> regions = new ArrayList<>();

public List<String> getRegions() { return regions; }
public void setRegions(List<String> regions) {
    this.regions = regions;
}
```

Có thể bind từ .properties theo index:

```properties
app.regions[0]=vn
app.regions[1]=sg
```

hoặc dạng comma-delimited:

```properties
app.regions=vn,sg
```

YAML:

```yaml
app:
  regions:
    - vn
    - sg
```

Khi đầu vào là **một chuỗi CSV** `app.regions=vn,sg`, tài liệu Spring Boot 3.3 nêu **setter là bắt buộc** cho collection trong cách bind đó. Vì vậy không nên sử dụng List getter-only làm một quy tắc chung cho tất cả dạng cấu hình.

### 5.2. List getter-only đã khởi tạo

Một List đã khởi tạo và **mutable** có thể được Binder truy cập qua getter trong một số trường hợp, đặc biệt cấu hình phần tử theo index:

```java
private final List<String> regions = new ArrayList<>();

public List<String> getRegions() {
    return regions;
}
```

Tuy nhiên, đây không phải lý do để bỏ setter bất kể cách dữ liệu được cung cấp. Tài liệu chính thức khuyến nghị **luôn thêm setter cho collection/array** vì cách biểu diễn và chuyển đổi giá trị ảnh hưởng tới việc Binder cần thao tác trên List hiện tại hay gán List mới. Nếu thiết kế bắt buộc getter-only, cần chọn định dạng được hỗ trợ rõ ràng, giữ collection mutable và không dựa vào CSV binding.

### 5.3. `List.of()` và `Collections.unmodifiableList()`

Không nên dùng immutable collection làm giá trị khởi tạo rồi trông đợi Binder thêm/xóa phần tử:

```java
// List không thể sửa trực tiếp:
private final List<String> regions = List.of("vn");

public List<String> getRegions() {
    return regions;
}
```

An toàn hơn nếu muốn vừa có danh sách mặc định vừa có setter:

```java
private List<String> regions =
        new ArrayList<>(List.of("vn"));

public List<String> getRegions() { return regions; }
public void setRegions(List<String> regions) { this.regions = regions; }
```

Lưu ý khác biệt: `List.of("vn")` là List immutable; `new ArrayList<>(List.of("vn"))` tạo một List mutable chứa cùng phần tử ban đầu.

### 5.4. Nested collection

Nếu field nested object đã được khởi tạo, Binder có thể đi vào object con và cập nhật List bên trong nó theo getter/setter của object con:

```java
private final Security security = new Security();

public Security getSecurity() { return security; }

public static class Security {
    private List<String> roles = new ArrayList<>(List.of("USER"));

    public List<String> getRoles() { return roles; }
    public void setRoles(List<String> roles) { this.roles = roles; }
}
```

Đầu vào:

```properties
app.security.roles[0]=ADMIN
app.security.roles[1]=AUDITOR
```

Nếu `app.security.roles` được bind từ nguồn cao hơn, **đừng mặc định rằng phần tử `USER` ban đầu sẽ tự động được nối thêm**. List có ngữ nghĩa thay thế trong quy tắc precedence; muốn thêm role mặc định bên cạnh role cấu hình thì hãy thiết kế thao tác hợp nhất rõ ràng ở tầng ứng dụng.

## 6. Giá trị khởi tạo: fallback khi thiếu cấu hình

Xét JavaBean:

```java
@ConfigurationProperties(prefix = "app")
public class DefaultsProperties {
    private String displayName = "Catalog";
    private int retryCount = 3;
    private boolean enabled = true;

    public String getDisplayName() { return displayName; }
    public void setDisplayName(String value) { displayName = value; }

    public int getRetryCount() { return retryCount; }
    public void setRetryCount(int value) { retryCount = value; }

    public boolean isEnabled() { return enabled; }
    public void setEnabled(boolean value) { enabled = value; }
}
```

Các trường hợp:

| Giá trị có trong `Environment` | Kết quả sau bind |
| --- | --- |
| Không có `app.display-name` | Giữ `"Catalog"` |
| `app.display-name=Store` | `"Store"` |
| `app.display-name=` | Chuỗi rỗng `""` (nếu kiểu String) |
| Không có `app.retry-count` | Giữ `3` |
| `app.retry-count=0` | `0`, không lấy lại `3` |
| Không có `app.enabled` | Giữ `true` |
| `app.enabled=false` | `false`, không lấy lại `true` |

Giá trị khởi tạo **không phải** chỉ thị “không chấp nhận 0, false hoặc chuỗi rỗng”. Các giá trị explicit có thể ghi đè default nếu chúng chuyển đổi được sang kiểu property.

Đặc biệt, `int` và `boolean` có default ngôn ngữ Java là `0` và `false` ngay cả khi không gán trong code. Vì vậy **`retryCount == 0` không chứng minh property được khai báo bằng 0** và **`enabled == false` không chứng minh người vận hành đã chủ động tắt tính năng**. Nếu phải phân biệt chưa khai báo và đã khai báo, có thể dùng wrapper `Integer`/`Boolean` và validation, hoặc kiểm tra nguồn property.

### Vì sao field initializer chạy trước Binder?

Một đối tượng Java mới có lifecycle:

```text
new DefaultsProperties()
  ├─ giá trị mặc định của JVM
  ├─ field initializers, ví dụ retryCount = 3
  ├─ constructor body (nếu có)
  └─ Binder gán các property tìm được bằng JavaBean setters
       └─ property không được bind giữ nguyên giá trị trước đó
```

Nếu constructor không tham số chủ động ghi giá trị khác cho trường đã khởi tạo, giá trị cuối trước khi bind là giá trị do constructor quyết định. Binder không phân biệt default đến từ field initializer hay constructor; nó chỉ có một object ban đầu để cập nhật.

## 7. Nested JavaBean: khởi tạo sẵn hoặc để Binder tạo

### 7.1. Khởi tạo sẵn và không cần setter ở cấp cha

```java
@ConfigurationProperties(prefix = "app")
public class ServiceProperties {
    private final Client client = new Client();

    public Client getClient() {
        return client;
    }

    public static class Client {
        private String host = "localhost";
        private int port = 8080;

        public String getHost() { return host; }
        public void setHost(String host) { this.host = host; }
        public int getPort() { return port; }
        public void setPort(int port) { this.port = port; }
    }
}
```

Cấu hình:

```yaml
app:
  client:
    host: api.example.test
```

Sau bind, `client.host = "api.example.test"` và `client.port = 8080`, bởi `port` không xuất hiện trong cấu hình. Field `client` vẫn là object được tạo ban đầu; Binder chỉ cập nhật property con.

### 7.2. Không khởi tạo sẵn nhưng có setter

```java
private Client client;

public Client getClient() { return client; }
public void setClient(Client client) { this.client = client; }
```

Khi có `app.client.host`, Binder có thể tạo instance `Client` (nếu có constructor thích hợp), bind property con rồi gán lại qua `setClient(...)`. Nếu không có thuộc tính con nào, `client` có thể giữ `null`; điều này **khác với** việc đã khởi tạo sẵn một object có các default.

### 7.3. Đặt tên nested property dựa theo field, không theo tên class

Đối với:

```java
private final Client client = new Client();
```

tên property là `app.client.host`, không phải `app.Client.host` hay `app.ServiceProperties.Client.host`. Binder tạo đường dẫn property từ **prefix + tên JavaBean property + property của nested object**.

Với field `readTimeout` bên trong `Client`, dạng canonical được khuyến nghị là `app.client.read-timeout`. Spring Boot hỗ trợ relaxed binding giữa tên kebab-case trong file và camelCase trong Java.

## 8. Default trong JavaBean và cấu hình từ nhiều PropertySource

Giá trị khởi tạo là fallback **sau khi Binder xét nguồn cấu hình hiệu lực**, không có nghĩa field initializer là một PropertySource được đặt ở một mức ưu tiên cụ thể trong `Environment`.

Giả sử field:

```java
private String name = "Catalog";
public String getName() { return name; }
public void setName(String name) { this.name = name; }
```

Và file `application.properties`:

```properties
app.name=FileName
```

Nếu chạy:

```bash
java -jar myapp.jar --app.name=CliName
```

Giá trị cuối trong bean là `CliName` vì command-line property có ưu tiên cao hơn file. Nếu không có giá trị nào của `app.name` từ các nguồn thì field giữ `Catalog`.

Đây là **hai bước**:

1. `Environment`/Binder xác định giá trị cấu hình có hiệu lực dựa trên nhiều PropertySource.
2. Binder cập nhật JavaBean property tương ứng hoặc để nguyên khi không có property phù hợp.

Không nên dùng code trong constructor để tự đọc `System.getenv()` và lắp logic precedence riêng nếu mục tiêu chỉ là override property; điều đó phá tính nhất quán với thứ tự Config Data, JVM system properties và command-line arguments.

### Chuỗi rỗng là giá trị explicit

```bash
java -jar myapp.jar --app.name=
```

Khi Binder nhìn thấy property String tồn tại với giá trị rỗng, setter có thể nhận `""` và ghi đè default `"Catalog"`. Nếu nghiệp vụ yêu cầu tên không rỗng, dùng validation `@NotBlank`; field initializer không tự biến empty thành default.

### Boolean false và zero là giá trị hợp lệ

```bash
java -jar myapp.jar --app.enabled=false --app.max-retries=0
```

Dù JavaBean đặt `enabled=true` và `maxRetries=3`, giá trị sau bind là `false` và `0`. Chúng là lựa chọn vận hành có ý nghĩa, ví dụ tắt tính năng và tắt retry.

### Lưu ý với property không chuyển kiểu được

Một cấu hình `app.max-retries=abc` không phải “vắng mặt”, và không được xem là cơ hội trở về giá trị khởi tạo `3` một cách tự động. Binder có thể báo lỗi chuyển đổi, tùy thuộc loại property và các tùy chọn binding. Nên sửa cấu hình sai kiểu hoặc sử dụng validation/exception handling phù hợp, thay vì che lỗi bằng default.

## 9. Binding List và Map khi nhiều nguồn ghi đè nhau

Khi hai PropertySource cùng chứa collection/map, cần hiểu ngữ nghĩa **binding từ nhiều nguồn**, ngoài chuyện setter/getter.

### 9.1. List từ nguồn ưu tiên cao thường thay thế toàn bộ list

File đóng gói:

```yaml
# application.yaml
app:
  regions:
    - vn
    - sg
```

File cho profile dev:

```yaml
# application-dev.yaml
app:
  regions:
    - localhost
```

Khi profile `dev` active, `regions` được bind từ danh sách ở nguồn ưu tiên cao hơn, với kết quả mong đợi:

```text
["localhost"]
```

Đừng trông đợi list từ source thấp được nối với list từ source cao. Tương tự, các phần tử mặc định được tạo trong Java field initializer không phải cam kết rằng chúng luôn được cộng vào list cấu hình mới.

Nếu muốn hành vi “thêm giá trị mới vào danh sách mặc định”, hãy mô hình hóa và thực hiện rõ hành vi merge ở code nghiệp vụ, hoặc dùng kiểu dữ liệu phù hợp (như Map có key rõ ràng) thay cho phụ thuộc ngầm vào Binder.

### 9.2. Map có thể kết hợp key từ nhiều nguồn

Giả sử `labels` là Map được khởi tạo rỗng:

```java
private final Map<String, String> labels = new LinkedHashMap<>();
public Map<String, String> getLabels() { return labels; }
```

File chung:

```properties
app.labels.team=platform
app.labels.env=dev
```

Nguồn ưu tiên cao hơn:

```properties
app.labels.env=prod
app.labels.owner=backend
```

Kết quả thường có ba key:

```text
team  -> platform
env   -> prod
owner -> backend
```

Map binding có thể hợp nhất **key** từ các nguồn, trong khi key bị trùng nhận giá trị từ nguồn ưu tiên cao hơn. Điều này khác list. Map chứa object còn có thể lấy các thuộc tính con khác nhau từ các nguồn khác nhau.

Nếu key chứa dấu `/` hoặc ký tự đặc biệt, dùng cú pháp ngoặc vuông của Map, ví dụ `app.labels.[/service/api]=active`; trong YAML đặt key `"[/service/api]"` trong dấu nháy để giữ nguyên tên.

## 10. Relaxed binding và chuyển đổi kiểu

`@ConfigurationProperties` hỗ trợ **relaxed binding**, nên tên config không cần giống cách viết chính xác của tên field Java, miễn tuân theo quy tắc tương ứng.

| JavaBean property | Dạng chuẩn trong file | Biến môi trường gợi ý |
| --- | --- | --- |
| `maxRetries` | `app.max-retries` | `APP_MAXRETRIES` |
| `connectTimeout` | `app.connect-timeout` | `APP_CONNECTTIMEOUT` |
| `displayName` | `app.display-name` | `APP_DISPLAYNAME` |
| `security.username` | `app.security.username` | `APP_SECURITY_USERNAME` |
| `regions[0]` | `app.regions[0]` | `APP_REGIONS_0_` |

Tên canonical được khuyến nghị: **lowercase kebab-case**. Với biến môi trường theo quy tắc Boot: dấu `.` thành `_`, dấu `-` bị bỏ, chuyển thành chữ hoa; chỉ số list được kẹp bằng `_`.

Binder cũng có khả năng chuyển đổi kiểu:

```properties
app.enabled=false
app.max-retries=0
app.connect-timeout=750ms
```

Có thể bind thành `boolean false`, `int 0` và `Duration.ofMillis(750)`. Khi dùng thời gian nên ghi đơn vị rõ ràng `ms`, `s`, `m`... để tránh đoán cách diễn giải số.

Ví dụ command line:

```bash
java -jar myapp.jar \
  --app.name=Catalog-API \
  --app.connect-timeout=5s \
  --app.enabled=false
```

Khi command-line properties được Spring Boot xử lý theo mặc định, chúng có thể ghi đè những property cùng tên đã có trong file.

### Prefix và tên property

`@ConfigurationProperties(prefix = "app")` ánh xạ các key bắt đầu bằng `app.`. Ví dụ:

- `app.name` → `setName(...)`.
- `app.max-retries` → `setMaxRetries(...)`.
- `app.security.username` → getter `getSecurity()` rồi `setUsername(...)` của nested JavaBean.

Không đặt prefix tùy ý gồm chữ hoa và cách viết lẫn lộn; ưu tiên tên lowercase với dấu chấm phân cấp, kebab-case cho các từ ghép.

## 11. JavaBean binding so với constructor binding

Spring Boot 3.3 hỗ trợ cả hai mô hình, nhưng cách biểu diễn “giá trị mặc định” khác nhau.

| Vấn đề | JavaBean binding | Constructor binding |
| --- | --- | --- |
| Cách tạo object | Constructor không tham số; Binder cập nhật object | Binder gọi constructor với các tham số đã bind |
| Trường phải có setter? | Scalar thường cần setter; map/nested đã khởi tạo có ngoại lệ | Không cần setter vì gán qua constructor |
| Giá trị ban đầu | Field initializer hoặc constructor không tham số | Mặc định của tham số/`@DefaultValue` theo quy tắc constructor |
| Mức độ mutable | Thường mutable | Có thể immutable, thích hợp record |
| Collection getter-only | Có giới hạn theo định dạng và tình trạng mutable | Giá trị được truyền vào constructor |
| Mục đích | Bean cấu hình mutable, kể cả bean do Spring tạo | Cấu hình bất biến, dependency rõ qua constructor |

Ví dụ record (để so sánh, **không phải JavaBean binding**):

```java
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "app")
public record ImmutableAppProperties(
        @DefaultValue("Catalog") String name,
        @DefaultValue("true") boolean enabled) {
}
```

`@DefaultValue` trong ví dụ này dùng cho **constructor binding**. Nó không thay thế việc gán giá trị khởi tạo field cho JavaBean. Nếu tạo một JavaBean với `private boolean enabled = true;` thì logic default của nó là giá trị object có trước khi setter được gọi.

**Đừng vô tình tạo constructor binding:** với một class `@ConfigurationProperties` đăng ký qua scan/`@EnableConfigurationProperties`, một constructor có tham số duy nhất có thể được Boot chọn cho constructor binding. Muốn dùng JavaBean binding, hãy cung cấp constructor không tham số thích hợp và tuân thủ cách Binder xác định constructor. Lombok annotation như `@AllArgsConstructor` có thể thay đổi hình dạng constructor; cần chọn Lombok annotations phù hợp, tránh tạo ra constructor làm thay đổi cơ chế binding ngoài ý định.

Với bean được Spring tạo qua `@Component` hoặc `@Bean`, constructor binding của `@ConfigurationProperties` không áp dụng như khi đăng ký class qua configuration-properties scanning/enablement. Có thể dùng **JavaBean binding** cho bean tạo qua cơ chế Spring thông thường, nhưng cần cấu hình rõ và tránh lạm dụng injection dependency vào class thuần cấu hình.

## 12. Đăng ký bean đúng cách: scan, enable, component và @Bean

### Phương án A — `@ConfigurationPropertiesScan`

```java
@SpringBootApplication
@ConfigurationPropertiesScan
public class DemoApplication {
}
```

Dùng khi muốn quét các class cấu hình rõ ràng trong package của ứng dụng. `@ConfigurationPropertiesScan` **không tự quét các class đã được đánh dấu `@Component` theo cùng cách**; tránh dựa vào hai cơ chế chồng lên nhau.

### Phương án B — `@EnableConfigurationProperties`

```java
@SpringBootApplication
@EnableConfigurationProperties(AppProperties.class)
public class DemoApplication {
}
```

Dùng khi muốn đăng ký chính xác những class cấu hình biết trước. Đây cũng là cách đăng ký được khuyến nghị khi muốn constructor binding với class riêng.

### Phương án C — `@Component` cùng `@ConfigurationProperties`

```java
@Component
@ConfigurationProperties(prefix = "app")
public class AppProperties {
    private String name = "Catalog";

    public String getName() { return name; }
    public void setName(String name) { this.name = name; }
}
```

Cách này dùng Spring tạo bean theo cơ chế thông thường rồi JavaBean bind property. Nó có thể phù hợp với class mutable đơn giản, nhưng không nên dùng để tìm cách constructor-bind một object immutable thông qua các constructor tham số được Spring dùng cho dependency injection.

### Phương án D — Trên một `@Bean` method

Khi cần cấu hình một component của thư viện mà không sở hữu source code:

```java
@Configuration(proxyBeanMethods = false)
public class LibraryConfiguration {

    @Bean
    @ConfigurationProperties(prefix = "client.pool")
    public LibraryPoolProperties libraryPoolProperties() {
        return new LibraryPoolProperties();
    }
}
```

`LibraryPoolProperties` trong ví dụ là class giả định của một thư viện có JavaBean properties phù hợp; tên đó không phải class có sẵn của Spring Boot. `@ConfigurationProperties` đặt trên method yêu cầu Binder cập nhật **instance đã tạo và trả về**. Nó không sửa được API của class bên thứ ba nếu class không cung cấp getter/setter/cách bind tương ứng.

### Không inject service vào class thuần cấu hình một cách tùy tiện

Một class `@ConfigurationProperties` nên chủ yếu biểu diễn dữ liệu external configuration. Thay vì tiêm `DataSource`, `RestClient` hoặc service vào class này, hãy tiêm **AppProperties** vào service sử dụng nó. Điều đó làm sự phụ thuộc rõ ràng và tránh trộn lifecycle của container với mô hình property.

## 13. Validation: giá trị mặc định không thay thế việc kiểm tra dữ liệu

Ví dụ thêm validation:

```java
package com.example.demo.config;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app")
public class ValidatedAppProperties {

    @NotBlank
    private String name = "Catalog";

    @Min(0)
    private int maxRetries = 3;

    @Valid
    private final Security security = new Security();

    public String getName() { return name; }
    public void setName(String name) { this.name = name; }

    public int getMaxRetries() { return maxRetries; }
    public void setMaxRetries(int maxRetries) {
        this.maxRetries = maxRetries;
    }

    public Security getSecurity() { return security; }

    public static class Security {
        @NotBlank
        private String username = "reader";

        public String getUsername() { return username; }
        public void setUsername(String username) {
            this.username = username;
        }
    }
}
```

Ý nghĩa:

- `@NotBlank`: tên và username không được null, rỗng hoặc chỉ có khoảng trắng.
- `@Min(0)`: maxRetries bằng 0 là hợp lệ, số âm không hợp lệ.
- `@Valid`: kích hoạt kiểm tra nested object `Security` để các constraint trong object con được xét đúng ngữ cảnh.

Nếu cấu hình cung cấp `app.name=`, giá trị String rỗng không tự biến thành `"Catalog"`; validation có thể từ chối nó. Nếu cấu hình cung cấp `app.max-retries=-1`, validation có thể báo lỗi thay vì dùng mặc định 3. Với ví dụ trên, cần có Bean Validation implementation tương thích, thường qua `spring-boot-starter-validation` và đăng ký class configuration properties vào context.

Trong Spring Boot, việc validate nested properties còn có các chi tiết khi cấu hình con không được bind; đánh dấu `@Valid` trên trường nested là cách thể hiện rõ mong muốn validate object con ngay cả khi nó được khởi tạo sẵn.

**Tách biệt ba thứ:**

1. *Field initializer*: cung cấp một giá trị ban đầu.
2. *Binder*: thay đổi giá trị theo cấu hình hiệu lực.
3. *Validation*: kiểm tra đối tượng cuối có thỏa yêu cầu nghiệp vụ hay không.

Không dùng giá trị mặc định để che một cấu hình sai định dạng hoặc sai ràng buộc.

## 14. Sử dụng object đã bind trong ứng dụng

Ví dụ một service lấy bean `AppProperties` qua constructor:

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

    public void printEffectiveConfig() {
        System.out.println(properties.getName());
        System.out.println(properties.isEnabled());
        System.out.println(properties.getMaxRetries());
        System.out.println(properties.getConnectTimeout());
        System.out.println(properties.getRegions());
        System.out.println(properties.getLabels().get("team"));
        System.out.println(properties.getSecurity().getUsername());
    }
}
```

Trong ứng dụng thực tế, tránh in ra password/token hoặc toàn bộ environment. Nếu class cấu hình chứa thông tin bí mật, chỉ log giá trị không nhạy cảm cần để chẩn đoán. Bean `AppProperties` được quản lý bởi Spring; service không cần gọi setter lại để “kích hoạt binding”.

### So sánh ngắn với `@Value`

```java
@Value("${app.name:Catalog}")
private String name;
```

`@Value` phù hợp khi chỉ lấy một vài property đơn giản. Nhưng khi cấu hình có nested object, List, Map, yêu cầu validation và nhiều property cùng prefix, `@ConfigurationProperties` cho mô hình type-safe rõ hơn và relaxed binding đầy đủ hơn. Không dùng `@Value` với kỳ vọng tự bind mọi nested object phức tạp theo đúng quy tắc JavaBean.

## 15. Những lỗi dễ gặp và cách xử lý

| Dấu hiệu | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| Property String luôn giữ giá trị khởi tạo | Không có nguồn config đúng key, bean chưa được đăng ký, hoặc thiếu setter | Kiểm tra prefix, nguồn, `@ConfigurationPropertiesScan`/`@EnableConfigurationProperties` và `setXxx` |
| Getter đọc được nhưng Binder không thay đổi scalar | Chỉ có getter, thiếu setter phù hợp | Thêm setter hoặc chuyển hẳn sang constructor binding |
| `client.host` không bind vào nested object | `client` chưa khởi tạo và không có setter | Khởi tạo nested object + getter hoặc thêm setter để Binder tạo |
| Map getter-only không nhận thêm entry | Map chưa khởi tạo hoặc immutable | Dùng `new HashMap<>()`/`new LinkedHashMap<>()` mutable và getter |
| List getter-only không nhận giá trị `a,b` | CSV binding cần setter cho collection | Thêm setter cho List; không dựa vào getter-only cho mọi định dạng |
| List mặc định mất phần tử khi file profile ghi đè | List được thay thế bởi nguồn ưu tiên cao | Cấu hình đầy đủ List hoặc thiết kế logic merge rõ ràng |
| Bean cấu hình không xuất hiện trong context | Chỉ có `@ConfigurationProperties`, chưa đăng ký | Thêm scan/enable hoặc đăng ký bean tương ứng |
| Class JavaBean bị đối xử như constructor-bound | Có một constructor tham số, Lombok tạo constructor không như ý | Cung cấp constructor không tham số phù hợp hoặc chủ động chọn constructor binding |
| `maxRetries=0` không giữ mặc định 3 | Đây là hành vi đúng: 0 là giá trị explicit | Đừng dùng 0 như sentinel cho missing |
| `enabled=false` không giữ mặc định true | Đây là hành vi đúng: false ghi đè default | Tách rõ “không cấu hình” và “cố ý tắt” |
| Cấu hình `abc` cho property kiểu số | Conversion không thành công | Sửa config về giá trị hợp lệ; dùng validation |
| Getter trả `List.of(...)` và Binder không cập nhật được | Collection immutable | Dùng collection mutable và setter |
| Cấu hình YAML không bind vào camelCase field | Tên key sai cấp thụt lề hoặc prefix | Kiểm tra YAML indentation, tên canonical kebab-case |
| Dùng field static làm configuration property | JavaBean binding không hỗ trợ bind static property | Đổi sang instance field |
| Property nested bị bind nhưng constraint không được kiểm tra | Thiếu validation hoặc `@Valid` trên nested member | Thêm validation phù hợp và dependency |
| Sử dụng @ConfigurationPropertiesScan cho @Component class | Scanning cấu hình loại trừ @Component class | Đăng ký rõ bằng cơ chế bean thích hợp và tránh trùng |

### Một đoạn mã không đủ điều kiện JavaBean binding

```java
@ConfigurationProperties(prefix = "app")
public class IncompleteProperties {
    private String name = "Catalog";
}
```

Dù có `app.name=NewName`, class không có getter/setter JavaBean cho `name`, nên không thể kỳ vọng Binder thay field theo cách JavaBean tiêu chuẩn. Phương án tối thiểu:

```java
@ConfigurationProperties(prefix = "app")
public class FixedProperties {
    private String name = "Catalog";

    public String getName() { return name; }
    public void setName(String name) { this.name = name; }
}
```

Cũng cần đăng ký class thành bean cấu hình như đã hướng dẫn, nếu muốn ứng dụng tự thực hiện binding.

## 16. Kiểm tra giá trị hiệu lực và tìm nguyên nhân khác default

Nếu một field vẫn giữ giá trị khởi tạo, không có nghĩa ngay lập tức là Binder lỗi. Có thể config property thực sự không tồn tại ở các PropertySource đã được nạp, hoặc tên key bị viết sai.

Một đoạn đọc `Environment` sau startup:

```java
@Configuration
public class ConfigDiagnostics {

    @Bean
    ApplicationRunner showSource(Environment env, AppProperties app) {
        return args -> {
            String key = "app.max-retries";
            System.out.println("Present in Environment: "
                    + env.containsProperty(key));
            System.out.println("Raw effective value: "
                    + env.getProperty(key));
            System.out.println("Bound bean value: "
                    + app.getMaxRetries());
        };
    }
}
```

Imports cần dùng ở ví dụ:

```java
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
```

Với code trên:

- `env.containsProperty(key) == false` và bean có `maxRetries=3` có thể là kết quả hợp lệ khi không cung cấp config cho key này.
- `env.containsProperty(key) == true` và `env.getProperty(key)="0"` sẽ khiến một JavaBean hợp lệ có setter thường được bind `maxRetries=0`.
- Nếu raw property đã có nhưng bean không đổi, kiểm tra cách đăng ký bean, tên JavaBean property, setter, conversion và đường dẫn nested object.
- Nếu có nhiều nguồn cùng key, property hiệu lực chịu thứ tự ưu tiên Spring Boot; một environment variable hoặc command-line option có thể ghi đè file bạn đang xem.

Khi dùng Spring Boot Actuator, endpoint `/actuator/configprops` có thể hiển thị các configuration properties đã bind (với chính sách hiển thị/sanitization), và `/actuator/env` có thể hỗ trợ tìm nguồn cấu hình. Chỉ bật, bảo vệ và sử dụng chúng theo nhu cầu chẩn đoán; tránh công khai secret.

## 17. Bảng quyết định thiết kế

| Muốn đạt được | Cách triển khai |
| --- | --- |
| Một String có default nhưng cho phép file ghi đè | Field initializer + getter/setter |
| Boolean mặc định bật và cho phép operator tắt | `boolean enabled = true` + `isEnabled/setEnabled` |
| Retry mặc định 3, nhưng 0 hợp lệ | `int maxRetries = 3` + getter/setter; validation `@Min(0)` |
| Nested object luôn tồn tại và chứa default | `private final Nested nested = new Nested();` + getter |
| Nested object chỉ tồn tại khi cấu hình cung cấp | Field không khởi tạo + getter/setter phù hợp |
| Map được bổ sung entry từ config | Mutable initialized Map + getter (setter không bắt buộc) |
| List nhận cả comma string và indexed/YAML | Mutable List + getter/setter |
| Không muốn field mutable sau khi tạo | Constructor binding/record |
| Muốn đổi default theo môi trường | Cấu hình qua Config Data/OS env/JVM/CLI và thứ tự PropertySource |
| Muốn từ chối giá trị thiếu hoặc sai quy tắc | Bean Validation + `@Validated`/constraints |
| Muốn kiểm tra value thực sự được bind | Inject bean + đọc getter; đối chiếu key qua `Environment` |

## 18. Tài liệu chính thức

- Spring Boot **3.3 Reference — Externalized Configuration**, đặc biệt *Type-safe Configuration Properties*, *JavaBean Properties Binding*, *Constructor Binding*, *Relaxed Binding*, *Merging Complex Types*, *PropertySource Order*: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- Spring Boot **3.3 Reference — Configuration Properties**, hướng dẫn thực hành đặt tên và đăng ký config: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.typesafe-configuration-properties
- Spring Boot **3.3 API — `@ConfigurationProperties`**: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/ConfigurationProperties.html
- Spring Framework — JavaBeans, `Environment` và Bean Validation tích hợp: https://docs.spring.io/spring-framework/reference/core/beans/environment.html

**Quy tắc nhớ:** JavaBean binding tạo một object mutable rồi **gán các property có nguồn cấu hình hiệu lực** thông qua JavaBean accessors. Scalar cần setter; **Map đã khởi tạo** và **nested object đã khởi tạo** có thể bind qua getter; **List/array nên có setter**, nhất là khi nhận giá trị từ chuỗi phân tách bằng dấu phẩy. **Field initializer là giá trị ban đầu**, không được ưu tiên hơn giá trị explicit như `0`, `false` hay chuỗi rỗng.
