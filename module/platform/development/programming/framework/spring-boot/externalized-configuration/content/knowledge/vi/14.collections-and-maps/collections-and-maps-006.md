# Liên kết Map có giá trị đơn hoặc đối tượng phức tạp trong Spring Boot 3.3

## 1. Mục tiêu và ý tưởng chính

Khi cấu hình một ứng dụng Spring Boot, không phải mọi nhóm thuộc tính đều có danh sách key cố định. Có lúc một dịch vụ cần cấu hình theo tên tenant, tên vùng triển khai, tên endpoint, nhãn của ứng dụng hoặc một tập provider mở rộng. `Map<K,V>` trong `@ConfigurationProperties` là công cụ phù hợp để diễn đạt nhóm cấu hình mà **tên key thay đổi theo dữ liệu**.

Có hai trường hợp quan trọng:

- **Map có giá trị đơn (scalar values):** mỗi key ánh xạ đến một giá trị như `String`, `Integer`, `Boolean`, `Duration` hoặc enum. Ví dụ `Map<String,String>` cho nhãn, `Map<String,Integer>` cho giới hạn retry.
- **Map có giá trị đối tượng phức tạp:** mỗi key ánh xạ đến một object chứa nhiều thuộc tính, có thể có object con, `List` và `Map` khác. Ví dụ `Map<String,ClientProperties>`, trong đó mỗi client gồm `baseUrl`, `connectTimeout` và `enabled`.

Hai dạng trên **khác nhau ở cách diễn giải các đoạn sau dấu chấm trong đường dẫn property**, cách binder tạo giá trị, mức độ cần getter/setter và cách kết hợp cấu hình giữa các PropertySource.

**Ví dụ trọng tâm:**

```properties
app.labels.team=platform
app.labels.region=ap-southeast-1

app.clients.billing.base-url=https://billing.example.test
app.clients.billing.connect-timeout=3s
app.clients.billing.enabled=true

app.clients.inventory.base-url=https://inventory.example.test
app.clients.inventory.connect-timeout=5s
app.clients.inventory.enabled=false
```

Từ đó, model Java có thể là:

```java
private Map<String, String> labels;
private Map<String, ClientProperties> clients;
```

Kết quả khái niệm:

```text
labels:
  team        -> "platform"
  region      -> "ap-southeast-1"

clients:
  billing:
    baseUrl        -> https://billing.example.test
    connectTimeout -> PT3S
    enabled        -> true
  inventory:
    baseUrl        -> https://inventory.example.test
    connectTimeout -> PT5S
    enabled        -> false
```

Spring Boot Binder dùng cấu trúc property path và **kiểu Java khai báo** để quyết định cách diễn giải từng nhánh.

## 2. Vì sao nên dùng @ConfigurationProperties thay vì tự parse Environment?

Spring Boot 3.3 có `Binder` chuyên biệt cho externalized configuration. Khi khai báo:

```java
@ConfigurationProperties(prefix = "app")
public class AppProperties {
    private Map<String, String> labels = new LinkedHashMap<>();
    // getters/setters...
}
```

Spring Boot có thể:

1. Lấy dữ liệu từ file `application.properties` hoặc YAML, biến môi trường, JVM system properties và CLI.
2. Nhận dạng prefix `app` và thuộc tính `labels` bằng **relaxed binding**.
3. Tìm các entry như `app.labels.team` và `app.labels.region`.
4. Tạo hoặc cập nhật các entry trong `Map`.
5. Chuyển đổi value theo kiểu đích, chẳng hạn từ `"3s"` thành `Duration`.
6. Kết hợp key từ những PropertySource thích hợp theo precedence.
7. Áp dụng validation nếu bean cấu hình được đăng ký để validate.

Tự `getProperty("app.labels.team")` chỉ tiện khi ta đã biết tên key `team`. Nếu key có thể là `payments`, `analytics` hoặc `client-42` do người vận hành thêm vào, khai báo `Map` giúp Binder tự phát hiện tập key thay vì phải duyệt thủ công toàn bộ nguồn cấu hình.

**Chú ý:** `Map` chỉ làm tên key động, không có nghĩa value luôn được bind đúng nếu kiểu Java không phù hợp, key bị làm sạch ký tự hoặc nguồn chứa cấu hình xung đột.

## 3. Bảng phân biệt các kiểu Map phổ biến

| Kiểu Java | Nội dung value | Ví dụ đường dẫn config | Lưu ý |
| --- | --- | --- | --- |
| `Map<String,String>` | Chuỗi scalar | `app.labels.team=platform` | Key có dấu `.` có thể được giữ nguyên trong dạng scalar Map |
| `Map<String,Integer>` | Số nguyên | `app.limits.billing=5` | `0` là số hợp lệ; giá trị text không parse được có thể lỗi |
| `Map<String,Boolean>` | Boolean | `app.flags.cache=false` | `false` là dữ liệu, không có nghĩa entry bị thiếu |
| `Map<String,Duration>` | Thời lượng | `app.timeouts.billing=750ms` | Cần chuyển đổi kiểu |
| `Map<String,ClientProperties>` | JavaBean với nhiều field | `app.clients.billing.base-url=...` | `billing` là key; `base-url` là field của value |
| `Map<String,Map<String,String>>` | Map lồng Map | `app.labels-by-team.sales.owner=Mai` | Hai cấp key động |
| `Map<String,List<String>>` | Map chứa List | `app.permissions.billing[0]=read` | Quy tắc bind List cũng áp dụng |
| `Map<String,Object>` | Giá trị động có thể lồng nhau | `app.metadata.a.b=value` | Dấu chấm không bracket có thể tạo nested Map |
| `Map<Enum,Something>` | Key là enum | `app.tiers.gold=...` | Key cần được chuyển sang enum tương ứng |

Mọi ví dụ đều giả định các `@ConfigurationProperties` đã được đăng ký, các file cấu hình nằm tại location được Boot tìm thấy, và không có PropertySource ưu tiên cao hơn ghi đè theo cách khác.

## 4. Ví dụ 1 — Map<String,String> chứa giá trị đơn

Tạo một JavaBean trong `src/main/java/com/example/demo/config/ServiceProperties.java`:

```java
package com.example.demo.config;

import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "service")
public class ServiceProperties {

    private Map<String, String> labels = new LinkedHashMap<>();

    public Map<String, String> getLabels() {
        return labels;
    }

    public void setLabels(Map<String, String> labels) {
        this.labels = labels;
    }
}
```

File `src/main/resources/application.properties`:

```properties
service.labels.owner=core-team
service.labels.region=ap-southeast-1
service.labels.stage=staging
```

YAML tương đương:

```yaml
service:
  labels:
    owner: core-team
    region: ap-southeast-1
    stage: staging
```

Sau khi bind:

```java
properties.getLabels().get("owner");  // "core-team"
properties.getLabels().get("region"); // "ap-southeast-1"
properties.getLabels().get("stage");  // "staging"
```

Không cần khai báo một field Java riêng cho `owner`, `region` hoặc `stage`; chúng là **key của Map**, không phải thuộc tính cố định của `ServiceProperties`.

### 4.1. Map có thể có key bất kỳ — nhưng phải tôn trọng cú pháp

Ví dụ nhu cầu dùng nhãn `source-system`:

```properties
service.labels.source-system=crm
```

Dấu gạch nối `-` là ký tự hợp lệ trong Map key khi sử dụng cách viết bình thường. Nếu key có ký tự đặc biệt khác, cần áp dụng cú pháp bracket `[key]` theo phần sau.

### 4.2. Giá trị có kiểu vẫn được chuyển đổi

Thay kiểu Java:

```java
private Map<String, Integer> retryLimits = new LinkedHashMap<>();

public Map<String, Integer> getRetryLimits() {
    return retryLimits;
}

public void setRetryLimits(Map<String, Integer> retryLimits) {
    this.retryLimits = retryLimits;
}
```

Cấu hình:

```properties
service.retry-limits.billing=3
service.retry-limits.analytics=0
service.retry-limits.search=5
```

Kết quả:

```text
billing   -> 3 (Integer)
analytics -> 0 (Integer)
search    -> 5 (Integer)
```

`0` là giá trị explicit, có thể có nghĩa **không retry**. Binder không loại entry đó chỉ vì giá trị bằng không.

Tương tự:

```java
private Map<String, Boolean> featureFlags = new LinkedHashMap<>();
```

```properties
service.feature-flags.new-search=true
service.feature-flags.old-checkout=false
```

`false` vẫn được lưu thành entry có key `old-checkout`, không phải chỉ dẫn bỏ qua hoặc xóa key.

### 4.3. Duration, DataSize và enum là scalar theo nghĩa binding

```java
private Map<String, Duration> timeouts = new LinkedHashMap<>();
```

```properties
service.timeouts.billing=500ms
service.timeouts.inventory=2s
```

Binder có thể chuyển `500ms`, `2s` sang `Duration` mà không cần JavaBean lồng nhau. Tương tự, các kiểu chuyển đổi được như enum hoặc `DataSize` có thể làm value của Map; khi conversion lỗi, startup có thể thất bại thay vì bỏ qua key.

## 5. Ví dụ 2 — Map<String,ClientProperties> chứa object phức tạp

Khi mỗi entry cần nhiều property, thay `String` bằng một class.

```java
package com.example.demo.config;

import java.time.Duration;
import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "gateway")
public class GatewayProperties {

    private Map<String, Client> clients = new LinkedHashMap<>();

    public Map<String, Client> getClients() {
        return clients;
    }

    public void setClients(Map<String, Client> clients) {
        this.clients = clients;
    }

    public static class Client {
        private String baseUrl;
        private Duration connectTimeout = Duration.ofSeconds(2);
        private boolean enabled = true;

        public String getBaseUrl() {
            return baseUrl;
        }

        public void setBaseUrl(String baseUrl) {
            this.baseUrl = baseUrl;
        }

        public Duration getConnectTimeout() {
            return connectTimeout;
        }

        public void setConnectTimeout(Duration connectTimeout) {
            this.connectTimeout = connectTimeout;
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

Cấu hình .properties:

```properties
gateway.clients.billing.base-url=https://billing.example.test
gateway.clients.billing.connect-timeout=3s
gateway.clients.billing.enabled=true

gateway.clients.inventory.base-url=https://inventory.example.test
gateway.clients.inventory.connect-timeout=1s
gateway.clients.inventory.enabled=false
```

YAML tương đương:

```yaml
gateway:
  clients:
    billing:
      base-url: https://billing.example.test
      connect-timeout: 3s
      enabled: true
    inventory:
      base-url: https://inventory.example.test
      connect-timeout: 1s
      enabled: false
```

**Cách đọc property path:**

```text
gateway.clients.billing.connect-timeout
   |       |      |          |
 prefix  Map    Map key     Client.connectTimeout

gateway.clients.inventory.enabled
   |       |      |          |
 prefix  Map    Map key     Client.enabled
```

Khi Binder thấy `Map<String,Client>`, đoạn `billing` không trở thành một field Java của `GatewayProperties`. Nó là key động của Map. Đoạn `connect-timeout` được relaxed-bind thành field `connectTimeout` **bên trong** object `Client` tương ứng.

### 5.1. Giá trị khởi tạo trong object con

Trong ví dụ, mỗi `Client` có:

```java
private Duration connectTimeout = Duration.ofSeconds(2);
private boolean enabled = true;
```

Nếu cấu hình cho `gateway.clients.billing` chỉ chứa `base-url`, Binder có thể tạo `Client` và giữ mặc định `connectTimeout=2s`, `enabled=true`. Nếu file ghi:

```properties
gateway.clients.billing.enabled=false
gateway.clients.billing.connect-timeout=0ms
```

thì `false` và `0ms` là những giá trị explicit; không lấy lại default.

### 5.2. Sử dụng object đã bind

```java
GatewayProperties.Client billing =
        gatewayProperties.getClients().get("billing");

if (billing != null && billing.isEnabled()) {
    Duration timeout = billing.getConnectTimeout();
    String baseUrl = billing.getBaseUrl();
    // Sử dụng các giá trị cho việc tạo client.
}
```

Nếu `get("billing")` trả về `null`, không có entry đã bind cho key đó; không nên gọi `billing.getBaseUrl()` khi chưa kiểm tra. Nếu ứng dụng yêu cầu key `billing` bắt buộc, hãy xác thực sau binding.

## 6. Điểm khác nhau quan trọng: dấu chấm trong Map key

Spring Boot 3.3 diễn giải Map key dựa vào **kiểu value** và cú pháp `[key]`. Một dấu chấm `.` có thể là một phần của key scalar Map, hoặc là ranh giới object lồng nhau.

### 6.1. Map<String,String> — dấu chấm có thể nằm trong key

Giả sử:

```java
private Map<String, String> values = new LinkedHashMap<>();
```

Config:

```properties
app.values.a.b=hello
```

Khi bind một `Map<String,String>`, key có thể được giữ nguyên là `"a.b"`, value là `"hello"`:

```text
values = {"a.b": "hello"}
```

Điều này được tài liệu Spring Boot mô tả cho các Map có **scalar value**, ví dụ `Map<String,String>`. Dấu chấm không bắt buộc phải chỉ định cấp mới trong trường hợp này.

### 6.2. Map<String,Object> — dấu chấm có thể tạo cấp lồng nhau

Đổi kiểu Java:

```java
private Map<String, Object> values = new LinkedHashMap<>();
```

Cùng config:

```properties
app.values.a.b=hello
```

có thể được diễn giải thành dữ liệu có cấu trúc:

```text
values:
  a:
    b: hello
```

Tức là entry `"a"` chứa một Map con có entry `"b"`, **khác** với key nguyên văn `"a.b"`.

### 6.3. Giữ nguyên key có dấu chấm bằng bracket

Nếu phải giữ đúng tên key `a.b`, dùng `[a.b]`:

```properties
app.values.[a.b]=hello
```

Trong YAML, bracket phải nằm trong dấu nháy:

```yaml
app:
  values:
    "[a.b]": hello
```

Đây là cách rõ ràng khi đối tượng đích là `Map<String,Object>`, hoặc khi muốn tránh ambiguity cho một Map được đổi kiểu value sau này.

**Bảng đối chiếu:**

| Target type | Input | Key/cấu trúc được bind |
| --- | --- | --- |
| `Map<String,String>` | `app.values.a.b=hello` | Có thể là key `"a.b"` → `"hello"` |
| `Map<String,Object>` | `app.values.a.b=hello` | Có thể là `"a"` → Map con `"b"` |
| `Map<String,Object>` | `app.values.[a.b]=hello` | Key nguyên văn `"a.b"` |
| `Map<String,String>` | `app.values.[a.b]=hello` | Key nguyên văn `"a.b"` |

Với `Map<String,Client>`, phần sau key thường được hiểu là property con của `Client`. Nếu key thực sự chứa dấu chấm, ví dụ `eu.west`, nên dùng `gateway.clients.[eu.west].base-url` để xác định ranh giới key.

## 7. Bracket notation để bảo toàn Map key chứa ký tự đặc biệt

Một key của Map có thể là:

- Đường dẫn: `/api/v1`
- Chuỗi có dấu chấm: `eu.west`
- Tên có dấu `_` hoặc các ký tự không theo tập key thông thường.
- Tên chứa dấu `/` và dấu `.` cùng lúc: `/hooks/v2.public`.

Theo Spring Boot, nếu không bao key trong `[]`, những ký tự khác chữ cái/số, dấu `-` hoặc dấu `.` có thể bị loại khỏi tên key trong khi binding. Điều này có thể làm hai key khác nhau bị quy thành cùng tên ngoài ý muốn.

### 7.1. Cách viết .properties

```properties
gateway.routes.[/api/v1]=billing
gateway.routes.[/api/v2]=inventory
gateway.routes.[/hooks/v2.public]=webhook
```

Tương ứng:

```text
routes.get("/api/v1")        -> "billing"
routes.get("/api/v2")        -> "inventory"
routes.get("/hooks/v2.public")-> "webhook"
```

Viết thiếu bracket:

```properties
gateway.routes./api/v1=billing
```

có thể khiến dấu `/` bị loại, tạo key `"apiv1"` thay vì `"/api/v1"`. Đây là lỗi dữ liệu có ảnh hưởng nghiệp vụ nếu Map key là đường routing.

### 7.2. Cách viết YAML

```yaml
gateway:
  routes:
    "[/api/v1]": billing
    "[/api/v2]": inventory
    "[/hooks/v2.public]": webhook
```

Trong YAML, **phải quote key có bracket notation**. Không dựa vào:

```yaml
gateway:
  routes:
    [/api/v1]: billing
```

để có semantics tương tự. YAML có cú pháp flow collection dùng dấu `[ ]`, vì vậy key biểu diễn bracket notation cần được đặt trong chuỗi có dấu nháy.

### 7.3. Map key đặc biệt khi value là object

```properties
gateway.clients.[tenant/eu].base-url=https://eu.example.test
gateway.clients.[tenant/eu].enabled=true
```

Tương đương YAML:

```yaml
gateway:
  clients:
    "[tenant/eu]":
      base-url: https://eu.example.test
      enabled: true
```

Key của Map là `"tenant/eu"`; còn `base-url` và `enabled` là thuộc tính của object con.

### 7.4. Map key có dấu chấm với object con

```properties
gateway.clients.[eu.west].base-url=https://eu-west.example.test
gateway.clients.[eu.west].connect-timeout=5s
```

Không đặt:

```properties
gateway.clients.eu.west.base-url=https://eu-west.example.test
```

nếu ý định là **một key `eu.west`**: các đoạn `eu`, `west` không bracket có thể bị hiểu theo cấu trúc sâu hơn và không bind vào `Client` như mong muốn.

## 8. Map lồng Map (nested Map)

Không phải mọi Map value phức tạp đều cần là JavaBean. Có thể dùng `Map<String,Map<String,String>>`.

```java
@ConfigurationProperties(prefix = "access")
public class AccessProperties {

    private Map<String, Map<String, String>> policies =
            new LinkedHashMap<>();

    public Map<String, Map<String, String>> getPolicies() {
        return policies;
    }

    public void setPolicies(
            Map<String, Map<String, String>> policies) {
        this.policies = policies;
    }
}
```

File YAML:

```yaml
access:
  policies:
    billing:
      read: role-billing-read
      write: role-billing-admin
    inventory:
      read: role-inventory-read
      write: role-inventory-admin
```

Đường đi dữ liệu:

```text
policies["billing"]["read"]    = "role-billing-read"
policies["billing"]["write"]   = "role-billing-admin"
policies["inventory"]["read"]  = "role-inventory-read"
policies["inventory"]["write"] = "role-inventory-admin"
```

Dạng .properties:

```properties
access.policies.billing.read=role-billing-read
access.policies.billing.write=role-billing-admin
access.policies.inventory.read=role-inventory-read
access.policies.inventory.write=role-inventory-admin
```

Ở đây `policies` là Map ngoài, `billing`/`inventory` là key cấp một, `read`/`write` là key cấp hai. Kiểu Java giúp Binder biết mỗi cấp nên là một Map.

Nếu key tầng trong chứa dấu `/` hoặc các ký tự đặc biệt, bracket notation vẫn áp dụng:

```properties
access.policies.billing.[/reports/export]=role-exporter
```

## 9. Map chứa List hoặc object chứa List

Một ví dụ tập quyền theo tenant:

```java
@ConfigurationProperties(prefix = "tenants")
public class TenantProperties {

    private Map<String, List<String>> roles = new LinkedHashMap<>();

    public Map<String, List<String>> getRoles() {
        return roles;
    }

    public void setRoles(Map<String, List<String>> roles) {
        this.roles = roles;
    }
}
```

YAML:

```yaml
tenants:
  roles:
    billing:
      - READ
      - WRITE
    analytics:
      - READ
```

.properties:

```properties
tenants.roles.billing[0]=READ
tenants.roles.billing[1]=WRITE
tenants.roles.analytics[0]=READ
```

Khi bind, `roles.get("billing")` có thể là `["READ", "WRITE"]`; `roles.get("analytics")` là `["READ"]`.

Tương tự, một complex Map value có thể chứa List:

```java
public static class Client {
    private List<String> allowedMethods = new ArrayList<>();

    public List<String> getAllowedMethods() {
        return allowedMethods;
    }

    public void setAllowedMethods(List<String> allowedMethods) {
        this.allowedMethods = allowedMethods;
    }
}
```

```properties
gateway.clients.billing.allowed-methods[0]=GET
gateway.clients.billing.allowed-methods[1]=POST
```

Cần nhớ **Map merge** và **List replacement** là hai quy tắc khác nhau. Khi một property List được định nghĩa ở nhiều PropertySource/profile, Spring Boot thường lấy List từ nguồn có ưu tiên cao hơn thay vì ghép List từ các nguồn; Map có thể giữ các key không trùng nhau.

## 10. Cơ chế merge Map từ nhiều PropertySource

Spring Boot hỗ trợ Map binding qua các PropertySource khác nhau. Một Map có thể kết hợp các key xuất hiện ở nhiều nguồn, trong khi các key trùng nhau sử dụng giá trị từ nguồn ưu tiên cao hơn.

### 10.1. Map giá trị đơn: merge theo key

Giả sử cấu hình chung trong `application.yaml`:

```yaml
app:
  labels:
    owner: platform
    environment: base
```

Cấu hình có ưu tiên cao hơn, ví dụ `application-prod.yaml` khi profile `prod` hoạt động:

```yaml
app:
  labels:
    environment: production
    cost-center: cc-42
```

Kết quả Map thường là:

```text
owner       -> platform
environment -> production
cost-center -> cc-42
```

Lý do: key `owner` không có ở nguồn cao nên được giữ từ nguồn thấp; `environment` trùng key nên giá trị từ nguồn ưu tiên cao thắng; `cost-center` được thêm từ nguồn cao.

Đây không phải hành vi merge vô điều kiện cho mọi cấu trúc Java. Nó là quy tắc **Map binding** trong Spring Boot, được áp dụng qua Binder và thứ tự PropertySource.

### 10.2. Map giá trị object: hợp nhất các field

Cấu hình chung:

```yaml
# application.yaml
gateway:
  clients:
    billing:
      base-url: https://billing.example.test
      connect-timeout: 2s
      enabled: true
    inventory:
      base-url: https://inventory.example.test
      connect-timeout: 4s
```

Cấu hình production:

```yaml
# application-prod.yaml
gateway:
  clients:
    billing:
      connect-timeout: 10s
      enabled: false
    payments:
      base-url: https://payments.example.test
      connect-timeout: 3s
```

Khi profile `prod` active, cấu hình Map có thể thu được:

```text
billing:
  baseUrl        = https://billing.example.test   # nguồn chung
  connectTimeout = 10s                            # nguồn prod
  enabled        = false                          # nguồn prod

inventory:
  baseUrl        = https://inventory.example.test # nguồn chung
  connectTimeout = 4s                             # nguồn chung
  enabled        = true                           # field initializer

payments:
  baseUrl        = https://payments.example.test  # nguồn prod
  connectTimeout = 3s                             # nguồn prod
  enabled        = true                           # field initializer
```

Cấu hình Map value là JavaBean cho phép các field con của cùng key đến từ những nguồn khác nhau. Ví dụ `billing.base-url` không bị xóa chỉ vì `application-prod.yaml` ghi đè `billing.connect-timeout`. Tuy nhiên, **khi các field con là List**, quy tắc thay thế List vẫn cần được xét riêng.

### 10.3. Mức ưu tiên Config Data và nguồn ngoài

Thứ tự ưu tiên tiêu biểu cho cùng một property: command-line arguments có thể cao hơn Java system properties, OS environment và file Config Data (với cấu hình Boot thông thường). Ví dụ:

```properties
# application.properties
gateway.clients.billing.connect-timeout=2s
```

```bash
java -jar myapp.jar \
  --gateway.clients.billing.connect-timeout=8s
```

Property từ command line có thể làm `billing.connectTimeout=8s`. Các property khác của `billing` có thể vẫn đến từ Config Data nếu không bị ghi đè.

**Điểm tinh tế:** Map key có thể bị chuẩn hóa khác nhau tùy loại nguồn, đặc biệt environment variables, nên hai key trông khác nhau trong đầu vào không nhất thiết tạo hai entry độc lập.

## 11. Environment variables cho Map: cách viết và giới hạn

Spring Boot 3.3 hỗ trợ relaxed binding với environment variables. Đổi một tên property chuẩn sang environment variable:

1. Thay dấu chấm `.` bằng `_`.
2. Bỏ dấu gạch nối `-`.
3. Viết hoa.

Ví dụ:

```text
gateway.clients.billing.connect-timeout
→ GATEWAY_CLIENTS_BILLING_CONNECTTIMEOUT

gateway.clients.billing.enabled
→ GATEWAY_CLIENTS_BILLING_ENABLED

service.retry-limits.analytics
→ SERVICE_RETRYLIMITS_ANALYTICS
```

Khai báo:

```bash
GATEWAY_CLIENTS_BILLING_CONNECTTIMEOUT=750ms \
GATEWAY_CLIENTS_BILLING_ENABLED=false \
SERVICE_RETRYLIMITS_ANALYTICS=0 \
java -jar myapp.jar
```

Map key `billing`/`analytics` được lấy từ phần tương ứng trong tên biến. Với **Map lấy từ environment variables**, Spring Boot chuẩn hóa Map key về **chữ thường**, vì vậy không nên dựa vào OS environment để bảo toàn khác biệt `Billing` và `billing`.

### 11.1. Map key có dấu chấm, slash hoặc ký tự đặc biệt

Đối với key `"/api/v1"`, không dễ mã hóa bracket notation và các ký tự `/` trong tên environment variable chuẩn. Nếu một key thật sự là URL path, route pattern hoặc nhãn có dấu chấm cần giữ nguyên, **dùng Config Data (.properties/YAML) với `[key]`** thường rõ ràng và an toàn hơn.

Ví dụ:

```properties
gateway.routes.[/api/v1]=billing
```

Không tự biến nó thành `GATEWAY_ROUTES_API_V1` rồi cho rằng Map key sẽ khôi phục chính xác `/api/v1`. Relaxed binding không có khả năng suy ngược tùy ý những ký tự đã bị loại.

### 11.2. Map key phân biệt hoa/thường

Nếu business cần hai key độc lập `"US-East"` và `"us-east"`, environment variable không phù hợp để giữ nguyên phân biệt này sau khi Spring Boot chuẩn hóa Map keys. Nên dùng một source biểu diễn key không bị mất case hoặc đổi mô hình key (ví dụ enum chuẩn hóa) theo yêu cầu nghiệp vụ.

### 11.3. Container và CI

Kubernetes/Compose có thể cấp environment variables cho map scalar và object values, ví dụ:

```yaml
services:
  gateway:
    image: example/gateway:1.0
    environment:
      GATEWAY_CLIENTS_BILLING_CONNECTTIMEOUT: "750ms"
      GATEWAY_CLIENTS_BILLING_ENABLED: "false"
```

Giá trị truyền dưới dạng text sẽ được Binder chuyển đổi sang `Duration` và `boolean` nếu target type phù hợp. Khi debug, cần phân biệt lỗi đặt tên environment variable với lỗi conversion value.

## 12. Map key có kiểu enum hoặc số

### 12.1. Enum key

Giả sử tập cấp dịch vụ cố định:

```java
public enum Tier {
    FREE, STANDARD, PREMIUM
}
```

```java
@ConfigurationProperties(prefix = "plan")
public class PlanProperties {

    private Map<Tier, Integer> quotas =
            new EnumMap<>(Tier.class);

    public Map<Tier, Integer> getQuotas() {
        return quotas;
    }

    public void setQuotas(Map<Tier, Integer> quotas) {
        this.quotas = quotas;
    }
}
```

File:

```properties
plan.quotas.free=100
plan.quotas.standard=1000
plan.quotas.premium=10000
```

Binder chuyển Map key sang enum type theo conversion service phù hợp. Một key không chuyển được thành enum `Tier` có thể làm quá trình binding lỗi. Enum key hợp lý khi tập key đã biết và cố định, trong khi `Map<String, ...>` phù hợp cho tenant/provider có thể được thêm mới.

### 12.2. Key dạng số và YAML

Với `Map<String,String>`:

```yaml
app:
  http-status-labels:
    "200": success
    "404": not-found
```

Đặt dấu nháy quanh số là cách rõ ràng để YAML nhận key là chuỗi `"200"` thay vì dựa vào suy luận kiểu scalar của YAML parser.

Nếu dùng `Map<Integer,String>`, target key là Integer và được chuyển kiểu khi Binder hỗ trợ. Nên chọn kiểu key phù hợp với cách truy cập của code; đừng khai báo `Map<String,...>` rồi tra bằng `Integer`.

## 13. Map<String,Object> là cấu hình động, không phải JavaBean có schema

`Map<String,Object>` có thể hữu ích khi cấu hình chứa các key bất định và nhiều tầng lồng nhau, nhưng làm mất một phần lợi ích **type safety**.

Ví dụ:

```java
@ConfigurationProperties(prefix = "app")
public class DynamicProperties {

    private Map<String, Object> metadata =
            new LinkedHashMap<>();

    public Map<String, Object> getMetadata() {
        return metadata;
    }

    public void setMetadata(Map<String, Object> metadata) {
        this.metadata = metadata;
    }
}
```

YAML:

```yaml
app:
  metadata:
    service:
      name: catalog
      replicas: 3
    owner: platform
```

Trong Map nhận được, `metadata.get("service")` có thể là một Map lồng nhau, không phải một JavaBean tự định nghĩa. Code tiêu thụ phải hiểu kiểu dữ liệu thực tế và thực hiện kiểm tra/cast hợp lệ.

Nếu biết cấu trúc bên trong, nên chuyển sang:

```java
Map<String, ServiceMetadata>
```

với:

```java
public static class ServiceMetadata {
    private String name;
    private int replicas;

    public String getName() { return name; }
    public void setName(String name) { this.name = name; }

    public int getReplicas() { return replicas; }
    public void setReplicas(int replicas) {
        this.replicas = replicas;
    }
}
```

Như vậy Binder có thể chuyển kiểu, code được IDE hỗ trợ, và validation cho nested object dễ diễn đạt hơn.

**Đừng mặc định** `Object` sẽ luôn là `String` hoặc luôn là `Integer` khi lấy từ mọi loại PropertySource. Khi cần semantics chính xác, khai báo typed value thay vì dựa vào raw Object.

## 14. Getter-only Map và Map đã khởi tạo

Trong JavaBean binding, một Map được khởi tạo sẵn và có getter thường có thể được Binder cập nhật mà **không bắt buộc setter**.

```java
@ConfigurationProperties(prefix = "app")
public class LabelsProperties {

    private final Map<String, String> labels =
            new LinkedHashMap<>();

    public Map<String, String> getLabels() {
        return labels;
    }
}
```

Spring Boot có thể sử dụng getter để lấy Map hiện tại rồi bind các entry từ `app.labels.*`. Không cần `setLabels(Map<...>)` nếu Binder có thể cập nhật Map đã có.

Nhưng điều này **đòi hỏi Map có thể sửa được**:

```java
// Không thích hợp nếu Binder cần thêm entry vào Map.
private final Map<String, String> labels = Map.of();
```

`Map.of()` trả về Map immutable. Không nên cung cấp Map getter-only immutable rồi trông chờ Binder thêm key bằng mutation.

Lựa chọn an toàn:

```java
private final Map<String, String> labels =
        new LinkedHashMap<>();
```

Hoặc dùng field có setter để Binder có con đường gán giá trị Map mới:

```java
private Map<String, String> labels =
        new LinkedHashMap<>();

public Map<String, String> getLabels() {
    return labels;
}

public void setLabels(Map<String, String> labels) {
    this.labels = labels;
}
```

**Nested object value** của Map cần đáp ứng cách JavaBean bind tương ứng: class con có cách tạo instance thích hợp và các setter cho scalar properties. Nếu value là class immutable constructor-bound, nên đăng ký và biểu diễn theo một mô hình được Binder hỗ trợ đúng cách.

### Đối tượng Map đã có giá trị ban đầu

```java
private Map<String, String> labels =
        new LinkedHashMap<>(Map.of(
            "owner", "default-team",
            "region", "global"
        ));
```

Giá trị khởi tạo có thể đóng vai trò mặc định cho entry không bị ghi đè, nhưng khi Binder bind Map từ nguồn config có thể có các cơ chế merge/replace tùy loại đối tượng và cách nó được gán. Nếu ứng dụng đòi hỏi chính xác “mọi default key phải luôn tồn tại”, hãy xác định chính sách merge ở tầng ứng dụng và kiểm thử thay vì mặc định mọi kiểu Map/binding style đều giữ đúng reference và mọi entry ban đầu.

## 15. Constructor binding và record chứa Map

Spring Boot 3.3 cũng cho phép khai báo cấu hình theo kiểu bất biến (immutable) thay vì JavaBean setter.

```java
package com.example.demo.config;

import java.net.URI;
import java.time.Duration;
import java.util.Map;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "gateway")
public record GatewayConfig(
        Map<String, Endpoint> clients) {

    public record Endpoint(
            URI baseUrl,
            Duration connectTimeout,
            boolean enabled) {
    }
}
```

YAML:

```yaml
gateway:
  clients:
    billing:
      base-url: https://billing.example.test
      connect-timeout: 3s
      enabled: true
    inventory:
      base-url: https://inventory.example.test
      connect-timeout: 1s
      enabled: false
```

Binder có thể xây dựng `Endpoint` từ các trường được chỉ định và truyền Map kết quả vào record `GatewayConfig`. Cách này không cần setter nhưng có những khác biệt quan trọng:

- Không có JavaBean field initializer trong record để giữ default.
- Nếu property không được cung cấp, giá trị constructor argument có thể cần default hoặc validation tùy thiết kế.
- Dùng `@DefaultValue` theo cách Spring Boot hỗ trợ cho constructor-bound properties khi cần default được khai báo rõ.
- Với `Map` và nested value bất biến, cần kiểm tra mọi field bắt buộc trước khi tiêu thụ.

Record Java chỉ bảo đảm **tham chiếu trường của record** không thay đổi; một Map được truyền vào vẫn có thể mutable nếu không được sao chép bảo vệ. Nếu cần immutability của cả Map, ứng dụng có thể copy trong constructor sau khi binding theo quy tắc riêng.

Khi dùng constructor binding, đăng ký class qua `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties` thích hợp; không giả định constructor binding sẽ tự áp dụng cho mọi bean tạo qua `@Component` hoặc `@Bean` thông thường.

## 16. Đăng ký @ConfigurationProperties đúng cách

Class có annotation chưa chắc đã là bean nếu không được đăng ký.

### Cách 1 — ConfigurationPropertiesScan

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

Quét các class `@ConfigurationProperties` trong package tương ứng, kể cả các JavaBean Map properties như `GatewayProperties`.

### Cách 2 — EnableConfigurationProperties

```java
@SpringBootApplication
@EnableConfigurationProperties(GatewayProperties.class)
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

Cần import `org.springframework.boot.context.properties.EnableConfigurationProperties`. Cách này đăng ký tường minh class cụ thể.

### Cách 3 — Component với JavaBean binding

```java
@Component
@ConfigurationProperties(prefix = "gateway")
public class GatewayProperties {
    // JavaBean getters, setters, Map...
}
```

Phù hợp với JavaBean mutable được Spring tạo như bean thông thường. Không dùng `@Component` để trông đợi constructor binding được chọn theo cách của configuration-properties scanning.

Không cần vừa `@Component` vừa scan/enable cùng class một cách vô thức; tránh đăng ký bean trùng lặp.

## 17. Validation cho Map giá trị đơn và Map object

Config có thể nạp thành công nhưng dữ liệu nghiệp vụ sai. Ví dụ endpoint thiếu `base-url`, timeout âm, hoặc Map không chứa provider bắt buộc.

Sử dụng Jakarta Bean Validation với `@Validated`:

```java
package com.example.demo.config;

import java.time.Duration;
import java.util.LinkedHashMap;
import java.util.Map;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "gateway")
public class ValidatedGatewayProperties {

    @NotEmpty
    @Valid
    private Map<String, Client> clients =
            new LinkedHashMap<>();

    public Map<String, Client> getClients() {
        return clients;
    }

    public void setClients(Map<String, Client> clients) {
        this.clients = clients;
    }

    public static class Client {

        @NotBlank
        private String baseUrl;

        @NotNull
        private Duration connectTimeout;

        public String getBaseUrl() {
            return baseUrl;
        }

        public void setBaseUrl(String baseUrl) {
            this.baseUrl = baseUrl;
        }

        public Duration getConnectTimeout() {
            return connectTimeout;
        }

        public void setConnectTimeout(Duration connectTimeout) {
            this.connectTimeout = connectTimeout;
        }
    }
}
```

**Ý nghĩa:**

- `@NotEmpty` trên Map: phải có ít nhất một entry.
- `@Valid`: yêu cầu cascade validation vào value objects chứa trong Map (tùy validator và cách đăng ký).
- `@NotBlank`: `baseUrl` không được thiếu, rỗng hoặc toàn khoảng trắng.
- `@NotNull`: `connectTimeout` phải có giá trị.

Trong dự án Spring Boot 3.3, thường cần `spring-boot-starter-validation` nếu classpath chưa có Jakarta Validation provider.

### 17.1. Constraint trên key và value

Java Bean Validation hỗ trợ các ràng buộc container elements, chẳng hạn:

```java
private Map<@NotBlank String, @NotNull String> labels;
```

Đây là ràng buộc về Map keys/values tại tầng Java type. Để validation hoạt động cần có Bean Validation provider tương thích và bean được validate đúng cách. Nếu key có thể có dấu `/`, không được dùng pattern cấm dấu đó khi ứng dụng thực sự cần nó.

### 17.2. Xác thực key bắt buộc

`@NotEmpty` chỉ đảm bảo Map không rỗng; nó không yêu cầu một key nhất định tồn tại:

```java
if (!clients.containsKey("billing")) {
    throw new IllegalStateException(
            "Missing gateway.clients.billing configuration");
}
```

Có thể đặt logic này vào tầng kiểm tra cấu hình hoặc dùng custom validator phù hợp. Cũng cần kiểm tra `Client` value không null nếu loại dữ liệu có thể sinh ra null.

### 17.3. Không dùng validation để che lỗi syntax

Nếu Map key chứa `/` nhưng bị mất dấu do thiếu bracket notation, `@NotBlank` trên value có thể vẫn vượt qua. Hãy viết key đúng cú pháp ngay từ file:

```properties
gateway.clients.[tenant/eu].base-url=https://eu.example.test
```

Validation kiểm tra tính hợp lệ của object đã bind, không tự sửa key đã bị normalize sai.

## 18. Missing key, empty String, zero và false trong Map

Map binding vẫn tuân theo ngữ nghĩa của giá trị cấu hình:

```properties
app.labels.display-name=
app.limits.analytics=0
app.flags.legacy=false
```

Các trường hợp:

- `app.labels.display-name=`: key `display-name` có thể tồn tại với `String ""`.
- `app.limits.analytics=0`: key `analytics` có value `Integer 0`.
- `app.flags.legacy=false`: key `legacy` có value `Boolean false`.
- Key không xuất hiện ở bất kỳ nguồn nào: thường không có entry tương ứng trong Map sau binding, trừ khi code cung cấp mặc định.

Không tự dùng:

```java
if (!flags.get("legacy")) {
    // ...
}
```

nếu `flags.get("legacy")` có thể null; unboxing `Boolean` null gây `NullPointerException`. Chọn rõ chính sách:

```java
boolean enabled = Boolean.TRUE.equals(
        flags.get("legacy"));
```

hoặc:

```java
Boolean configured = flags.get("legacy");

if (configured == null) {
    // Chưa cấu hình key này.
} else if (configured) {
    // Cố ý bật.
} else {
    // Cố ý tắt.
}
```

Với `Map<String, Integer>`, không nên xem zero là “không khai báo” nếu zero là giá trị hợp lệ. `null`, absence và value `0` có thể mang ý nghĩa khác nhau.

### Scalar Map và key có dấu chấm

Nếu một Map scalar dùng key `a.b`, muốn có sự phân biệt chính xác giữa key `"a.b"` và dữ liệu nested, cân nhắc bracket notation ngay từ đầu:

```properties
app.labels.[a.b]=value
```

Cách này giúp cấu hình ít bị ảnh hưởng nếu sau này đổi `Map<String,String>` thành `Map<String,Object>`.

## 19. Sử dụng Map trong một service thực tế

Ví dụ Spring service dùng Map để chọn client theo mã tenant:

```java
package com.example.demo.service;

import com.example.demo.config.GatewayProperties;
import com.example.demo.config.GatewayProperties.Client;

import org.springframework.stereotype.Service;

@Service
public class ClientRouter {

    private final GatewayProperties gatewayProperties;

    public ClientRouter(GatewayProperties gatewayProperties) {
        this.gatewayProperties = gatewayProperties;
    }

    public Client route(String clientName) {
        Client client = gatewayProperties.getClients().get(clientName);

        if (client == null) {
            throw new IllegalArgumentException(
                    "Unknown client configuration: " + clientName);
        }

        if (!client.isEnabled()) {
            throw new IllegalStateException(
                    "Client is disabled: " + clientName);
        }

        return client;
    }
}
```

Dùng `Map<String,Client>` giúp thêm key `notifications`/`payments` bằng cấu hình mà không phải tạo thêm Java field tương ứng. Nhưng service vẫn phải kiểm tra key hợp lệ, không cho tên client tùy ý tạo hành vi nguy hiểm nếu Map được nạp từ nguồn không đáng tin.

**Vấn đề bảo mật:** Nếu value Map chứa credential, token hoặc secret, không log toàn bộ `getClients()`. Với Spring Actuator `/actuator/configprops`, `/actuator/env`, cần giới hạn exposure và đảm bảo sanitization, không công khai cấu hình nhạy cảm.

## 20. Unit/integration test cho Map binding

Một bài test `@SpringBootTest` có thể chứng minh nhiều Map entry được bind vào đúng kiểu Java:

```java
package com.example.demo;

import static org.junit.jupiter.api.Assertions.*;

import java.time.Duration;

import com.example.demo.config.GatewayProperties;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest(properties = {
        "gateway.clients.billing.base-url=https://billing.example.test",
        "gateway.clients.billing.connect-timeout=3s",
        "gateway.clients.billing.enabled=true",
        "gateway.clients.[tenant/eu].base-url=https://eu.example.test",
        "gateway.clients.[tenant/eu].enabled=false"
})
class GatewayPropertiesTest {

    @Autowired
    GatewayProperties gatewayProperties;

    @Test
    void bindsSimpleAndComplexMapValues() {
        GatewayProperties.Client billing =
                gatewayProperties.getClients().get("billing");

        assertNotNull(billing);
        assertEquals("https://billing.example.test",
                billing.getBaseUrl());
        assertEquals(Duration.ofSeconds(3),
                billing.getConnectTimeout());
        assertTrue(billing.isEnabled());

        GatewayProperties.Client eu =
                gatewayProperties.getClients().get("tenant/eu");
        assertNotNull(eu);
        assertFalse(eu.isEnabled());
    }
}
```

Bài test này giả định `GatewayProperties` đã được đăng ký qua `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties`, và không có source ưu tiên cao hơn làm thay đổi các key liên quan.

Với test có nhiều PropertySource, hãy xét precedence: `@SpringBootTest(properties=...)` thường thêm các property test với độ ưu tiên cao hơn file ứng dụng thông thường. Nếu cần kiểm thử chính xác logic merge của nhiều nguồn, có thể thiết kế test environment riêng có các PropertySource với thứ tự đã biết.

### Test riêng bằng ApplicationContextRunner

Nếu viết auto-configuration hoặc một component library, `ApplicationContextRunner` của `spring-boot-test` tiện tạo một context cô lập với property values tường minh:

```java
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.boot.context.properties.EnableConfigurationProperties;

class GatewayBindingRunnerTest {

    @Test
    void readsBillingClient() {
        new ApplicationContextRunner()
                .withUserConfiguration(GatewayConfig.class)
                .withPropertyValues(
                    "gateway.clients.billing.base-url=https://billing.example.test",
                    "gateway.clients.billing.enabled=false")
                .run(context -> {
                    GatewayProperties props =
                            context.getBean(GatewayProperties.class);
                    assertFalse(
                        props.getClients().get("billing").isEnabled());
                });
    }

    @EnableConfigurationProperties(GatewayProperties.class)
    static class GatewayConfig { }
}
```

Cần import static assertion phù hợp, ví dụ `org.junit.jupiter.api.Assertions.assertFalse`. Đây là ví dụ minh họa luồng kiểm thử; cấu hình của dự án có thể cần thêm những auto-configurations khác tùy component.

## 21. Chẩn đoán khi Map không bind đúng

Khi thấy `Map` rỗng hoặc key/value khác mong đợi, lần lượt kiểm tra:

1. **Prefix có đúng không?** Ví dụ `@ConfigurationProperties(prefix="gateway")` chỉ nhắm các đường dẫn `gateway.*`.
2. **Bean đã được đăng ký chưa?** `@ConfigurationProperties` không tự biến class thành bean nếu thiếu scan/enable/bean registration phù hợp.
3. **Tên JavaBean property có đúng không?** `clients` phải được Binder nhìn như property qua getter/setter hoặc constructor parameter.
4. **Map có thể sửa được không?** Getter-only Map cần instance mutable, tránh `Map.of()` nếu dựa vào mutation.
5. **Kiểu value khớp không?** `Map<String,String>` có ngữ nghĩa khác `Map<String,Object>` và `Map<String,Client>`.
6. **Key có dấu chấm/slash không?** Dùng `[key]`; YAML phải quote `"[key]"`.
7. **Value object có setter/constructor hợp lệ không?** Nested scalar property không tự bind vào một immutable object không có đường khởi tạo phù hợp.
8. **Có lỗi conversion không?** `Duration` nhận `750ms`, `5s`; một chuỗi `never` có thể không parse được.
9. **Đã xét PropertySource precedence chưa?** Một source cao hơn có thể ghi đè key hoặc thuộc tính con.
10. **Có List bên trong không?** List có quy tắc thay thế, khác Map merge.
11. **Environment variable đã được đặt theo quy tắc canonical chưa?** Dấu `-` bị bỏ, dấu `.` thành `_`; Map key có thể về chữ thường.
12. **Có validation làm startup thất bại không?** `@NotBlank`/`@NotEmpty`/`@Valid` có thể từ chối object thiếu dữ liệu.
13. **File cấu hình đã được Boot nạp chưa?** Kiểm tra `spring.config.location`, `spring.config.additional-location`, profile và `spring.config.import` nếu dùng.
14. **Có cấu hình không được nhận biết và bị bỏ qua không?** `ignoreUnknownFields` mặc định của `@ConfigurationProperties` có thể khiến lỗi typo không biểu hiện theo cách dễ thấy; nên thống nhất schema, dùng metadata và test.

### Đoạn chẩn đoán giá trị Map ở runtime

```java
@Configuration
class GatewayDiagnostics {

    @Bean
    ApplicationRunner showClients(GatewayProperties properties) {
        return args -> {
            for (String client : properties.getClients().keySet()) {
                GatewayProperties.Client value =
                        properties.getClients().get(client);

                System.out.println("Configured client key: " + client);
                System.out.println("Enabled: " + value.isEnabled());
            }
        };
    }
}
```

Imports cần có:

```java
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
```

Chỉ log key và những trường an toàn nếu cần. Không dump secret, password, API token hoặc toàn bộ Map chưa được sanitization.

## 22. Những lỗi thường gặp

### Lỗi 1 — Dấu chấm trong key bị diễn giải sai

```properties
app.metadata.a.b=value
```

Nếu target là `Map<String,Object>` và bạn cần đúng key `"a.b"`, hãy dùng:

```properties
app.metadata.[a.b]=value
```

### Lỗi 2 — Mất slash trong key đường dẫn

```properties
gateway.routes./api/v1=billing
```

Dùng:

```properties
gateway.routes.[/api/v1]=billing
```

### Lỗi 3 — YAML không quote bracket

```yaml
routes:
  [/api/v1]: billing
```

Dùng:

```yaml
routes:
  "[/api/v1]": billing
```

### Lỗi 4 — Tưởng Map merge giống List merge

File base chứa `roles.billing=[READ,WRITE]`, file prod chứa `roles.billing=[ADMIN]`. List value có thể bị thay bằng `[ADMIN]` từ nguồn cao hơn, không phải `[READ,WRITE,ADMIN]`. Map có thể hợp nhất key; List không được bảo đảm nối.

### Lỗi 5 — Complex Map value thiếu setter

```java
public static class Client {
    private String baseUrl;
    public String getBaseUrl() { return baseUrl; }
}
```

Nếu dùng JavaBean binding cho `Client`, cần `setBaseUrl(...)` hoặc chuyển sang constructor binding phù hợp. Đúng Map key không cứu được việc value object không thể cập nhật.

### Lỗi 6 — Map khởi tạo bằng Map.of()

```java
private final Map<String, String> labels = Map.of();
public Map<String, String> getLabels() { return labels; }
```

Khi Binder cần thêm entry vào Map getter-only, immutable Map không cho sửa. Dùng `new LinkedHashMap<>()` hoặc thiết kế setter/binding style khác.

### Lỗi 7 — Biến môi trường không giữ tên key phức tạp

```text
GATEWAY_ROUTES_API_V1=billing
```

Tên này không có thông tin đủ để khôi phục key `"/api/v1"`. Dùng file Config Data với `[/api/v1]`.

### Lỗi 8 — Dùng @Value để tạo Map complex tự động

```java
@Value("${gateway.clients}")
private Map<String, GatewayProperties.Client> clients;
```

Đây không phải cách được thiết kế để bind một Map value object từ các key `gateway.clients.billing.base-url`... Dùng `@ConfigurationProperties` và Binder cho nested structures.

### Lỗi 9 — Coi false hoặc 0 là key vắng mặt

```properties
gateway.clients.billing.enabled=false
app.retry-limits.billing=0
```

Hai giá trị này vẫn explicit, không nên tự quay lại default hoặc bỏ entry khi chúng có ý nghĩa vận hành.

### Lỗi 10 — Tưởng Map entry ở profile-specific xóa mọi field base

Map object có thể lấy các field con từ nhiều nguồn. Chỉ khai báo `enabled=false` ở profile cao hơn không mặc nhiên xóa `base-url` từ nguồn chung. Nếu business muốn ngăn sử dụng entry, phải kiểm tra flag `enabled` hoặc thực hiện quy tắc loại bỏ riêng.

### Lỗi 11 — Bỏ một key ở nguồn cao rồi tưởng đã xóa khỏi Map

Nếu key vẫn tồn tại ở PropertySource ưu tiên thấp, Binder có thể lấy nó từ nguồn đó. Không coi “xóa một dòng file prod” là thao tác xóa key toàn cục khỏi cấu hình hợp nhất.

### Lỗi 12 — Value Object không được validate

Binder có thể tạo `Client` nhưng `baseUrl` là null. Nếu caller cần giá trị bắt buộc, dùng validation `@NotBlank` và cascade `@Valid` cho Map, hoặc kiểm tra sau bind.

## 23. Bảng quyết định: chọn kiểu Map nào?

| Nhu cầu | Kiểu Java phù hợp | Cách viết trong file |
| --- | --- | --- |
| Nhãn tùy ý, mỗi nhãn một String | `Map<String,String>` | `app.labels.team=platform` |
| Giới hạn số theo dịch vụ | `Map<String,Integer>` | `app.limits.billing=5` |
| Bật/tắt feature theo tenant | `Map<String,Boolean>` | `app.flags.billing=false` |
| Timeout theo endpoint | `Map<String,Duration>` | `app.timeouts.billing=2s` |
| Nhiều client có URL/timeout/flag | `Map<String,Client>` | `app.clients.billing.base-url=...` |
| Tập quyền nhiều vai trò theo client | `Map<String,List<String>>` | `app.roles.billing[0]=READ` |
| Nhóm các key tùy ý theo key tầng ngoài | `Map<String,Map<String,String>>` | `app.policies.billing.read=role-a` |
| Cấu hình động không rõ schema | `Map<String,Object>` | `app.metadata.service.name=...` |
| Tập tier cố định bởi enum | `Map<Tier,Integer>` | `app.quotas.free=100` |
| Key có dấu slash | `Map<String,?>` | `app.routes.[/api/v1]=...` |
| Key có dấu chấm cần giữ nguyên | `Map<String,?>` | `app.metadata.[eu.west]=...` |

Khi value có schema ổn định, ưu tiên typed JavaBean/record hơn `Object` để có conversion, validation và metadata rõ ràng.

## 24. Checklist triển khai

- [ ] Xác định Map key là dữ liệu động hay thực chất là tên field cố định của một object.
- [ ] Chọn đúng value type: scalar, typed JavaBean/record, List hoặc Map con.
- [ ] Khai báo `@ConfigurationProperties` với prefix lowercase kebab-case hợp lệ.
- [ ] Đăng ký bean bằng `@ConfigurationPropertiesScan`/`@EnableConfigurationProperties`/bean registration phù hợp.
- [ ] Với JavaBean, có getter/setter cho scalar và object con tương ứng.
- [ ] Getter-only Map đã được khởi tạo bằng loại mutable khi cần mutation.
- [ ] Map key đặc biệt dùng bracket `[key]`.
- [ ] Trong YAML, key bracket được quote bằng `"[key]"`.
- [ ] Với Map value kiểu Object hoặc nested object, xử lý đúng ý nghĩa dấu chấm trong key.
- [ ] Với môi trường triển khai, đặt tên biến OS theo công thức canonical: dot → underscore, dash → remove, uppercase.
- [ ] Không phụ thuộc environment variable để giữ key có slash hoặc chữ hoa/thường quan trọng.
- [ ] Phân biệt Map merge qua nhiều nguồn với List replacement.
- [ ] Xác định rõ chính sách cho key thiếu, String rỗng, `0` và `false`.
- [ ] Validate complex value và key bắt buộc theo yêu cầu nghiệp vụ.
- [ ] Có test cho bracket notation, profile override, typed conversion và source precedence.
- [ ] Không log secrets; bảo vệ endpoints chẩn đoán cấu hình.
- [ ] Với key tên động quan trọng, mô tả format được cho phép trong tài liệu vận hành để tránh xung đột key sau normalization.

## 25. Tài liệu tham khảo

- Spring Boot **3.3 Reference — Externalized Configuration**, các phần *Type-safe Configuration Properties*, *Binding Maps*, *Merging Complex Types*, *Relaxed Binding*, *Binding From Environment Variables*: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- Spring Boot **3.3 API — @ConfigurationProperties**: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/ConfigurationProperties.html
- Spring Boot **3.3 API — Binder**: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/bind/Binder.html
- Spring Boot **3.3 Reference — Configuration Metadata**: https://docs.spring.io/spring-boot/3.3/reference/configuration-metadata/index.html
- Spring Framework Reference — `Environment` và `PropertySource`: https://docs.spring.io/spring-framework/reference/core/beans/environment.html

**Ghi nhớ:** `Map<String,String>` chứa scalar và có thể giữ dấu chấm trong key; `Map<String,Object>` hoặc `Map<String,Client>` có cách hiểu dấu chấm theo cấu trúc lồng nhau. Dùng **`[key]`** để bảo toàn Map key đặc biệt, dùng **typed JavaBean/record** cho value nhiều field, và nhớ rằng Spring Boot có thể **merge Map theo key/field từ nhiều PropertySource**, trong khi **List thường được thay thế** theo precedence.
