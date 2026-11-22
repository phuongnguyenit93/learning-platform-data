# Phân biệt dấu chấm trong khóa Map với đường dẫn đối tượng khi bind cấu hình Spring Boot

## 1. Vấn đề: cùng dấu chấm nhưng có thể mang hai ý nghĩa

Spring Boot cho phép ánh xạ các thuộc tính trong `application.yml`, `application.properties`, biến môi trường và các nguồn cấu hình khác vào Java class bằng `@ConfigurationProperties`. Một tên thuộc tính dạng phẳng thường chứa dấu chấm:

~~~properties
app.client.timeout=5s
app.labels.api.example.com=catalog
app.tenants.[team.alpha].timeout=8s
~~~

Nhìn bề ngoài, cả ba dòng đều dùng ký tự `.`. Tuy nhiên, ý nghĩa không giống nhau:

- `app.client.timeout`: dấu chấm phân tách các cấp đối tượng `app` → `client` → `timeout`.
- `app.labels.api.example.com`: nếu `labels` được bind thành `Map<String, String>`, phần `api.example.com` có thể là **một Map key duy nhất**.
- `app.tenants.[team.alpha].timeout`: `tenants` là Map có giá trị kiểu object; cặp dấu ngoặc vuông bảo vệ key `team.alpha`, còn dấu chấm sau dấu `]` bắt đầu thuộc tính `timeout` của object được map tới.

Nếu không phân biệt, ứng dụng có thể bind sai kiểu dữ liệu, đánh mất Map key, không tìm được cấu hình hoặc bỏ qua những giá trị mà người triển khai tưởng đã cung cấp.

Mục tiêu của bài:

1. Hiểu dấu chấm được Binder diễn giải theo **kiểu đích** chứ không chỉ theo chuỗi tên.
2. Phân biệt **đường dẫn object lồng nhau** và **Map key có chứa dấu chấm**.
3. Biết khi nào bắt buộc hoặc nên dùng cú pháp **`[key.with.dot]`**.
4. Viết đúng YAML/properties cho `Map<String,String>`, `Map<String,Object>` và `Map<String, CustomType>`.
5. Chẩn đoán và kiểm thử khi cấu hình có những key như domain name, tenant ID, tên nhóm hoặc chuỗi chứa ký tự đặc biệt.

Bài tập trung vào cơ chế binding Spring Boot 3.x, đặc biệt là `@ConfigurationProperties` và `ConfigurationPropertyName`; những chi tiết cụ thể nên đối chiếu với phiên bản Spring Boot đang dùng.

## 2. Từ YAML đến tên thuộc tính phẳng

Giả sử tệp `application.yml` có:

~~~yaml
app:
  http:
    client:
      connect-timeout: 5s
      max-retries: 3
~~~

Về mặt cấu trúc YAML, đây là một mapping lồng nhiều cấp. Spring Boot xem xét các đường dẫn thuộc tính tương đương:

~~~properties
app.http.client.connect-timeout=5s
app.http.client.max-retries=3
~~~

Với Java class:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public record AppProperties(Http http) {
    public record Http(Client client) {}
    public record Client(Duration connectTimeout, int maxRetries) {}
}
~~~

Dấu chấm lần lượt dẫn đến các thành phần `http`, `client`, `connectTimeout` và `maxRetries`. Đây là **object property path**.

Nếu thay `http` bằng một Map:

~~~java
@ConfigurationProperties(prefix = "app")
public record AppProperties(
        java.util.Map<String, String> http
) {}
~~~

Binder sẽ không còn coi `http` là class Java có thuộc tính `client`. Phần còn lại của đường dẫn có thể trở thành **Map key**, tùy kiểu phần tử của Map. Vì vậy, **cùng dữ liệu phẳng, đổi mô hình Java là có thể đổi cách hiểu ranh giới key**.

Đừng suy ra mọi dấu chấm xuất hiện trong tên thuộc tính đều bắt buộc là một cấp Java object.

## 3. Phân biệt theo kiểu đích

Xét một số mô hình Java:

| Kiểu đích | Tên thuộc tính | Cách diễn giải điển hình |
| --- | --- | --- |
| Bean lồng nhau `Client client` | `app.client.timeout` | `timeout` là thuộc tính của object `client` |
| `Map<String, String> labels` | `app.labels.api.example.com` | `api.example.com` có thể là một key đầy đủ |
| `Map<String, Integer> limits` | `app.limits.service.alpha` | Với value scalar, `service.alpha` có thể được giữ là key |
| `Map<String, Object> extras` | `app.extras.user.role` | Có thể tạo cấu trúc Map lồng nhau theo các đoạn `user` và `role` |
| `Map<String, TenantPolicy> tenants` | `app.tenants.[team.alpha].timeout` | Key Map là `team.alpha`; `timeout` là field của `TenantPolicy` |

**Quy tắc quan trọng của Spring Boot:** với Map có **giá trị scalar** (chẳng hạn `Map<String, String>`), dấu chấm trong phần key có thể được giữ nguyên mà không nhất thiết phải dùng ngoặc vuông. Với giá trị không phải scalar, ví dụ `Map<String, Object>` hoặc một object cấu hình có các trường con, dấu chấm có thể được hiểu như đường dẫn lồng nhau; nếu thật sự muốn dấu chấm thuộc Map key, hãy dùng **bracket notation**.

Trong ngữ cảnh tài liệu Spring Boot, scalar bao gồm các kiểu đơn giản như enum và những kiểu trong `java.lang`, trừ `Object`. Không nên tự mở rộng ngoại lệ đó cho mọi custom class hoặc mọi collection.

Hãy nhớ: **Map key không tự động bắt đầu ở dấu chấm cuối cùng**. Binder dựa trên cấu trúc property name, kiểu tham số/field và quy tắc binding để xác định ranh giới.

## 4. Trường hợp 1: `Map<String, String>` với key chứa dấu chấm

Một ứng dụng muốn ánh xạ hostname đến tên dịch vụ nội bộ:

~~~yaml
app:
  host-aliases:
    api.example.com: catalog
    images.example.com: media
    auth.example.org: identity
~~~

Java:

~~~java
import java.util.Map;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public record HostAliasProperties(
        Map<String, String> hostAliases
) {}
~~~

Các tên thuộc tính phẳng có thể được nhìn như:

~~~properties
app.host-aliases.api.example.com=catalog
app.host-aliases.images.example.com=media
app.host-aliases.auth.example.org=identity
~~~

Với `Map<String, String>`, Binder có thể giữ phần `api.example.com` làm **một key Map** chứ không biến nó thành object chứa `api` → `example` → `com`.

Kết quả mong muốn:

~~~java
Map<String, String> hosts = properties.hostAliases();

hosts.get("api.example.com");      // "catalog"
hosts.get("images.example.com");   // "media"
hosts.get("auth.example.org");     // "identity"
~~~

Điểm đáng chú ý: ngay cả khi YAML trình bày theo dạng:

~~~yaml
app:
  host-aliases:
    api:
      example:
        com: catalog
~~~

nó vẫn có thể được flatten thành đường dẫn `app.host-aliases.api.example.com`. Khi kiểu đích là `Map<String,String>`, Binder có thể coi chuỗi `api.example.com` là key scalar. Vì thế, **hình dạng YAML riêng lẻ không đủ để kết luận kết quả Map**; cần nhìn kiểu Java.

Dù dấu chấm có thể được giữ tự động trong Map scalar, dùng bracket notation là cách biểu đạt ý định rõ ràng hơn khi key được thiết kế là một identifier nguyên vẹn:

~~~yaml
app:
  host-aliases:
    "[api.example.com]": catalog
    "[images.example.com]": media
~~~

Cặp `[ ]` trong YAML key cần đặt trong dấu nháy để parser YAML đọc nó như **chuỗi tên key**, không phải cú pháp sequence/flow collection.

## 5. Trường hợp 2: object lồng nhau dùng dấu chấm làm đường dẫn

Giả sử yêu cầu cấu hình một HTTP client:

~~~yaml
app:
  client:
    connection:
      timeout: 3s
      max-connections: 20
~~~

Java:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public record AppProperties(Client client) {
    public record Client(Connection connection) {}
    public record Connection(Duration timeout, int maxConnections) {}
}
~~~

Ở đây các tên:

~~~properties
app.client.connection.timeout=3s
app.client.connection.max-connections=20
~~~

có ý nghĩa:

~~~text
app
 └─ client                      object Client
     └─ connection             object Connection
         ├─ timeout            Duration
         └─ max-connections    int
~~~

Không có Map nằm tại `app.client` hoặc `app.client.connection`. Vì vậy `connection.timeout` không phải một Map key. Binder phải đi qua các thuộc tính/nested type tương ứng.

Ví dụ này tạo ra ranh giới rõ:

- `Map<String,String>`: các đoạn sau tên Map có thể được gom thành key scalar.
- Nested Java object: mỗi cấp khớp với một thuộc tính Java; không có Map key tự do.

Nếu muốn đặt tên tùy ý cho từng client như `team.alpha`, mô hình Java nên có Map:

~~~java
public record AppProperties(
        java.util.Map<String, Client> clients
) {
    public record Client(Duration timeout, int maxConnections) {}
}
~~~

và khai báo key có dấu chấm bằng ngoặc vuông như phần tiếp theo.

## 6. Trường hợp 3: `Map<String, CustomType>` và key có dấu chấm

Một ứng dụng multi-tenant có các tenant ID là `team.alpha` và `team.beta`. Mỗi tenant có timeout và một cờ bật/tắt.

Cấu hình:

~~~yaml
app:
  tenants:
    "[team.alpha]":
      enabled: true
      timeout: 5s
    "[team.beta]":
      enabled: false
      timeout: 9s
~~~

Java:

~~~java
import java.time.Duration;
import java.util.Map;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public record TenantProperties(
        Map<String, TenantPolicy> tenants
) {
    public record TenantPolicy(
            boolean enabled,
            Duration timeout
    ) {}
}
~~~

Các tên thuộc tính sau flatten:

~~~properties
app.tenants.[team.alpha].enabled=true
app.tenants.[team.alpha].timeout=5s
app.tenants.[team.beta].enabled=false
app.tenants.[team.beta].timeout=9s
~~~

Kết quả:

~~~java
TenantProperties.TenantPolicy alpha =
        properties.tenants().get("team.alpha");

boolean enabled = alpha.enabled();        // true
Duration timeout = alpha.timeout();        // PT5S
~~~

Hãy phân tích đường dẫn:

~~~text
app.tenants.[team.alpha].timeout
│   │        │            │
│   │        │            └── field "timeout" của TenantPolicy
│   │        └─────────────── key nguyên vẹn "team.alpha"
│   └──────────────────────── tên field Map "tenants"
└──────────────────────────── prefix "app"
~~~

Nếu bỏ dấu ngoặc:

~~~properties
app.tenants.team.alpha.timeout=5s
~~~

thì các đoạn `team`, `alpha` và `timeout` có thể được Binder diễn giải như đường dẫn lồng nhau. Với kiểu `Map<String, TenantPolicy>`, đó **không phải cách đáng tin cậy để truyền key `team.alpha`**: Binder có thể cố liên kết key `team` với một object rồi tìm tiếp thuộc tính `alpha`, trong khi `TenantPolicy` chỉ có `enabled` và `timeout`.

Kết quả có thể là lỗi bind, bỏ qua một thuộc tính hoặc object không như mong đợi, tùy kiểu và thiết lập binder. Không cần đoán một kết quả cố định: hãy ghi rõ key bằng ngoặc vuông.

## 7. Cú pháp bracket notation: `[key]`

Spring Boot hỗ trợ ký hiệu bracket cho Map key cần giữ nguyên:

~~~text
map-name.[literal.key].field
map-name.[/literal/key].field
map-name.[some:key].field
~~~

Dạng trong `application.properties`:

~~~properties
app.tenants.[team.alpha].timeout=5s
app.tenants.[team.beta].timeout=9s
app.labels.[api.example.com]=catalog
~~~

Dạng trong `application.yml`:

~~~yaml
app:
  tenants:
    "[team.alpha]":
      timeout: 5s
    "[team.beta]":
      timeout: 9s
  labels:
    "[api.example.com]": catalog
~~~

### Hai lớp cú pháp cần phân biệt

1. **YAML syntax:** key có dấu ngoặc nên được **quote** như `"[team.alpha]"` để nó là một string key hợp lệ.
2. **Spring Boot binding syntax:** cặp `[ ]` cho biết phần bên trong là **Map key cần bảo toàn**, thay vì các cấp path thông thường.

Viết:

~~~yaml
app:
  tenants:
    team.alpha:
      timeout: 5s
~~~

không tương đương một cách chắc chắn với:

~~~yaml
app:
  tenants:
    "[team.alpha]":
      timeout: 5s
~~~

khi value của `tenants` là một custom class.

### Cần có dấu chấm trước ngoặc hay không?

Trong property names, có thể gặp cả các ví dụ dùng `map.[key]` và cú pháp index gắn liền với đoạn Map. Khi viết tài liệu/ứng dụng, dạng dễ đọc và phổ biến là:

~~~properties
app.tenants.[team.alpha].timeout=5s
~~~

Điều quan trọng không phải số dấu chấm ở các vị trí khác nhau mà là **key chứa dấu chấm phải được đặt trọn trong bracket**. Dùng một quy ước nhất quán và kiểm thử binding đúng phiên bản.

## 8. Map scalar khác `Map<String, Object>`

Đây là một ngoại lệ dễ bị bỏ qua. Giả sử property phẳng:

~~~properties
app.metadata.user.role=reader
~~~

Với:

~~~java
@ConfigurationProperties(prefix = "app")
public record MetadataProperties(
        java.util.Map<String, String> metadata
) {}
~~~

kiểu value là `String`. Binder có thể giữ khóa:

~~~text
metadata["user.role"] = "reader"
~~~

Nhưng với:

~~~java
@ConfigurationProperties(prefix = "app")
public record MetadataProperties(
        java.util.Map<String, Object> metadata
) {}
~~~

`Object` không nằm trong nhóm scalar được áp dụng ngoại lệ giữ dấu chấm tự động. Đường dẫn `user.role` có thể được diễn giải thành cấu trúc Map lồng nhau:

~~~text
metadata
  └─ user
      └─ role = "reader"
~~~

Thay vì một entry với key `user.role`.

Nếu yêu cầu là **giữ key nguyên văn** ngay cả khi Map value khai báo `Object`, hãy dùng bracket:

~~~properties
app.metadata.[user.role]=reader
~~~

hoặc:

~~~yaml
app:
  metadata:
    "[user.role]": reader
~~~

Trong cấu trúc có nhiều mức và nhiều kiểu dữ liệu, `Map<String, Object>` có tính linh hoạt nhưng cũng làm cách diễn giải tên khóa khó dự đoán hơn. Khi cấu trúc cố định, cân nhắc dùng **record hoặc class lồng nhau** thay vì Map Object tổng quát.

### Tại sao `Object` đặc biệt?

Không nên kết luận rằng “vì Object nhận được mọi giá trị nên nó là scalar”. Trong quy tắc binding Map của Spring Boot, `Object` là **ngoại lệ** so với những kiểu scalar thông dụng thuộc `java.lang`. Do vậy, chính kiểu generic value trong `Map<String, Object>` có thể làm dấu chấm được hiểu theo hướng lồng map.

Nếu đổi `Map<String, String>` thành `Map<String, Object>` trong lần refactor, hãy xem lại những key chứa dấu chấm và thêm bracket notation ở cấu hình khi cần giữ key nguyên vẹn.

## 9. Ký tự đặc biệt ngoài dấu chấm: gạch chéo, dấu hai chấm và khoảng trắng

Ngoài dấu chấm, Map key có thể chứa:

- Đường dẫn URL: `/api/v1`.
- Tên resource: `/metrics/prometheus`.
- Tên định danh có dấu hai chấm: `region:asia`.
- Những ký tự ký hiệu dùng trong một hệ thống bên ngoài.

Ví dụ:

~~~yaml
app:
  route-permissions:
    "[/api/v1]": read
    "[/internal/health]": monitor
    "[tenant:premium]": write
~~~

Java:

~~~java
import java.util.Map;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public record RouteProperties(
        Map<String, String> routePermissions
) {}
~~~

Khi bind đúng theo bracket notation:

~~~java
routeProperties.routePermissions().get("/api/v1");          // "read"
routeProperties.routePermissions().get("/internal/health"); // "monitor"
routeProperties.routePermissions().get("tenant:premium");   // "write"
~~~

Nếu bỏ bracket khỏi một key có dấu gạch chéo:

~~~yaml
app:
  route-permissions:
    /api/v1: read
~~~

thì những ký tự không thuộc nhóm được phép của tên property có thể bị loại bỏ hoặc chuẩn hóa trong quá trình binding, làm Map key **khác chuỗi gốc**. Theo quy tắc tên Map của Spring Boot, khi không được bọc bracket, các ký tự ngoài chữ/số, dấu gạch ngang và dấu chấm không được bảo toàn đầy đủ.

Vì thế:

- Key có dấu `.` với **scalar Map value**: có thể không cần bracket, nhưng bracket vẫn làm ý định rõ hơn.
- Key chứa dấu `/` hoặc các ký hiệu cần bảo toàn: **dùng bracket**.
- Key có `.` với **object/non-scalar Map value**: **dùng bracket** để tránh bị hiểu như path.

Với key chứa khoảng trắng hoặc ký hiệu lạ, cần quan tâm cả quy tắc quote của YAML và quy tắc bảo toàn key của Binder. Không nên đoán cách escape từ cú pháp của một ngôn ngữ khác.

## 10. Đường dẫn object trong Map: dấu chấm nào là path thật?

Một Map có value là object vẫn cần dấu chấm để đi vào các thuộc tính của value đó.

Ví dụ:

~~~yaml
app:
  queues:
    "[priority.high]":
      consumer:
        concurrency: 6
        poll-timeout: 2s
    "[priority.low]":
      consumer:
        concurrency: 2
        poll-timeout: 10s
~~~

Java:

~~~java
import java.time.Duration;
import java.util.Map;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public record QueueProperties(Map<String, Queue> queues) {
    public record Queue(Consumer consumer) {}

    public record Consumer(
            int concurrency,
            Duration pollTimeout
    ) {}
}
~~~

Tên phẳng:

~~~properties
app.queues.[priority.high].consumer.concurrency=6
app.queues.[priority.high].consumer.poll-timeout=2s
app.queues.[priority.low].consumer.concurrency=2
app.queues.[priority.low].consumer.poll-timeout=10s
~~~

Ở `app.queues.[priority.high].consumer.poll-timeout`:

1. `app` là prefix của class `QueueProperties`.
2. `queues` là field `Map<String, Queue>`.
3. `[priority.high]` là **một Map key**.
4. `consumer` là field của record `Queue`.
5. `poll-timeout` là field của record `Consumer`.

Một biểu thức tên chứa nhiều dấu chấm có thể đồng thời có **dấu chấm literal trong key** và **dấu chấm phân cấp object**. Bracket giúp Binder biết ranh giới mà lập trình viên muốn giữ.

### Vì sao không đơn giản dùng dấu gạch dưới thay dấu chấm?

Với key tenant `priority.high`, đổi thành `priority_high` sẽ tạo **một identifier khác**. Nếu hệ thống bên ngoài sử dụng tenant ID gốc có dấu chấm, việc đổi key là sai dữ liệu.

Brackets bảo toàn tên key như một đơn vị; chúng không yêu cầu đổi giá trị nghiệp vụ.

## 11. Ví dụ cùng tên thuộc tính nhưng hai kiểu Java cho kết quả khác nhau

Giả sử chỉ có một dòng:

~~~properties
app.flags.feature.alpha=true
~~~

**Cách A — bind vào Map scalar:**

~~~java
@ConfigurationProperties(prefix = "app")
public record FlagMapProperties(
        java.util.Map<String, Boolean> flags
) {}
~~~

`Boolean` là kiểu scalar. Tên `feature.alpha` có thể được giữ làm một Map key, cho kết quả tương đương:

~~~java
flags.get("feature.alpha"); // true
~~~

**Cách B — bind vào nested object:**

~~~java
@ConfigurationProperties(prefix = "app")
public record FlagObjectProperties(Flags flags) {
    public record Flags(Feature feature) {}
    public record Feature(boolean alpha) {}
}
~~~

Lúc này `flags` là object, `feature` là object con, `alpha` là field boolean. Đó là một đường dẫn thuộc tính hoàn chỉnh, không phải Map key.

**Cách C — bind vào Map có value là object:**

~~~java
@ConfigurationProperties(prefix = "app")
public record FlagPolicyProperties(
        java.util.Map<String, FeaturePolicy> flags
) {
    public record FeaturePolicy(boolean enabled) {}
}
~~~

Nếu key dự kiến là `feature.alpha` và object value có field `enabled`, dòng cũ không mô tả đúng giá trị cần bind. Hãy dùng:

~~~properties
app.flags.[feature.alpha].enabled=true
~~~

Điểm rút ra: phải xác định kiểu dữ liệu mong muốn **trước khi viết property name**. Không có một phép tách chuỗi bằng dấu chấm có thể thay Binder trong mọi trường hợp.

## 12. Sử dụng `@ConfigurationProperties` đúng cách để kiểm chứng

Một ví dụ đầy đủ cho hai loại Map:

~~~yaml
# src/main/resources/application.yml
demo:
  host-aliases:
    "[api.example.com]": catalog
    "[images.example.com]": media
  tenants:
    "[team.alpha]":
      enabled: true
      timeout: 5s
    "[team.beta]":
      enabled: false
      timeout: 10s
~~~

Java record:

~~~java
package com.example.demo.config;

import java.time.Duration;
import java.util.Map;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "demo")
public record DemoProperties(
        Map<String, String> hostAliases,
        Map<String, TenantSettings> tenants
) {
    public record TenantSettings(
            boolean enabled,
            Duration timeout
    ) {}
}
~~~

Đăng ký quét:

~~~java
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
~~~

Service dùng bean:

~~~java
package com.example.demo.service;

import com.example.demo.config.DemoProperties;
import org.springframework.stereotype.Service;

@Service
public class RoutingService {

    private final DemoProperties properties;

    public RoutingService(DemoProperties properties) {
        this.properties = properties;
    }

    public String routeForHost(String host) {
        return properties.hostAliases().get(host);
    }

    public boolean tenantEnabled(String tenantId) {
        DemoProperties.TenantSettings settings =
                properties.tenants().get(tenantId);
        return settings != null && settings.enabled();
    }
}
~~~

Khi gọi:

~~~java
routeForHost("api.example.com");      // "catalog"
tenantEnabled("team.alpha");          // true
tenantEnabled("team.beta");           // false
~~~

Thông qua `Map<String, String>` và `Map<String, TenantSettings>`, ta có thể thấy hai loại key chứa dấu chấm được bảo toàn theo ý định.

Trong Spring Boot 3.x, record `@ConfigurationProperties` có constructor phù hợp thường được constructor-bound ngầm định khi được đăng ký bằng `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties`. Không cần đặt `@Component` trực tiếp trên record này.

## 13. Dùng `application.properties` thay vì YAML

Cùng ví dụ trên có thể viết:

~~~properties
demo.host-aliases.[api.example.com]=catalog
demo.host-aliases.[images.example.com]=media

demo.tenants.[team.alpha].enabled=true
demo.tenants.[team.alpha].timeout=5s

demo.tenants.[team.beta].enabled=false
demo.tenants.[team.beta].timeout=10s
~~~

Lợi ích của `.properties` là thấy rõ tên phẳng mà Binder xử lý. Với key chứa dấu chấm, phần giữa bracket được xem là đơn vị:

~~~text
demo.tenants.[team.alpha].timeout
             └──────────┘
                 Map key
~~~

Không nên cố thay đổi sang dạng:

~~~properties
demo.tenants.team.alpha.timeout=5s
~~~

và kỳ vọng kết quả hoàn toàn tương đương. Dạng không bracket có thể thể hiện object path lồng nhau, không phải Map key `team.alpha`.

### Khi nào có thể bỏ bracket?

Đối với `demo.host-aliases` kiểu `Map<String, String>`:

~~~properties
demo.host-aliases.api.example.com=catalog
~~~

có thể giữ key `api.example.com` vì Map value là scalar.

Tuy nhiên, nếu đang soạn một cấu hình sẽ được bảo trì lâu dài hoặc có thể refactor kiểu value thành object, cách viết bracket giúp ý định “đây là key chứa dấu chấm” được thể hiện trực tiếp, ít phụ thuộc suy đoán hơn.

## 14. Cảnh báo: key Map và relaxed binding không phải cùng một việc

Spring Boot có **relaxed binding**, giúp những tên thuộc tính như:

~~~text
demo.client.connect-timeout
demo.client.connectTimeout
DEMO_CLIENT_CONNECTTIMEOUT
~~~

được ánh xạ đến cùng một field `connectTimeout` trong nhiều ngữ cảnh cấu hình thích hợp.

Nhưng Map key thường là **dữ liệu có ý nghĩa riêng**, ví dụ:

~~~text
api.example.com
team.alpha
/metrics
priority.high
~~~

Không nên cho rằng mọi phép chuẩn hóa tên property sẽ bảo toàn mọi ký tự của một Map key. Điều này đặc biệt quan trọng với:

- Dấu chấm `.`.
- Dấu gạch chéo `/`.
- Chữ hoa/chữ thường trong identifier.
- Khoảng trắng.
- Dấu hai chấm hoặc các ký hiệu đặc biệt.
- Tên key có thể bị nhầm với đường dẫn object.

Brackets là cách để mô tả phần key cần được bảo toàn trong tên cấu hình, nhưng ở mỗi loại nguồn còn có **quy tắc đặt tên/escaping của chính nguồn đó**.

Chẳng hạn, biến môi trường của hệ điều hành thường không hỗ trợ tên chứa dấu `.` hoặc dấu `[ ]` theo cùng cách như file `.properties`. Khi Map key phức tạp, nên ưu tiên cấu hình file YAML/properties hoặc một định dạng cấu trúc khác phù hợp, thay vì tự đặt biến môi trường tùy ý rồi kỳ vọng Binder phục hồi hoàn toàn ký tự gốc.

## 15. Map key chứa dấu chấm qua biến môi trường: không chuyển cơ học

Ví dụ property trong file:

~~~properties
demo.tenants.[team.alpha].timeout=5s
~~~

Một công thức cơ bản khi đổi **tên property chuẩn** sang biến môi trường là thay dấu chấm bằng `_`, xóa dấu gạch nối, rồi viết hoa. Nhưng công thức đó **không tự giữ được ranh giới bracket và dấu chấm literal trong key**.

Nếu chuyển cơ học thành một tên như:

~~~text
DEMO_TENANTS_TEAM_ALPHA_TIMEOUT
~~~

thì thông tin “`team.alpha` là một Map key duy nhất” đã bị mất. Tên biến trông như một chuỗi nhiều cấp, và không nên mặc định nó bind thành Map entry mong muốn.

Các hướng thiết kế:

1. Nếu Map key là định danh tự do chứa dấu chấm, **đặt cấu hình trong YAML/properties** có bracket notation.
2. Nếu bắt buộc dùng biến môi trường, cân nhắc đổi **schema** để key chỉ dùng ký tự dễ tương thích, đồng thời có một trường lưu identifier gốc; hoặc dùng một property chứa cấu hình có cấu trúc mà ứng dụng parse rõ ràng.
3. Nếu dùng `SPRING_APPLICATION_JSON` hoặc nguồn Config Data hỗ trợ cấu trúc, hãy kiểm tra cách nguồn đó biểu diễn key và cách Binder nhận lại tên thuộc tính; không suy diễn từ tên biến đơn giản.
4. Viết integration test cho đúng loại môi trường triển khai (shell, Docker, Kubernetes).

Ví dụ một schema tránh dotted Map key:

~~~yaml
demo:
  tenants:
    team-alpha:
      external-id: "team.alpha"
      enabled: true
      timeout: 5s
~~~

Java có thể bind theo key nội bộ `team-alpha` nhưng xử lý `external-id` như dữ liệu. Đổi schema như vậy là **quyết định thiết kế**, không phải phép tương đương tự động khi dữ liệu gốc có vai trò định danh bên ngoài.

Không nên đổi key nghiệp vụ một cách âm thầm nếu các hệ thống khác đang tham chiếu tên gốc.

## 16. YAML quoting và lý do không viết bracket trần

Trong YAML, `[ ]` là ký hiệu có ý nghĩa đặc biệt trong flow sequence. Vì vậy, khi muốn key mang chuỗi `[team.alpha]`, hãy đặt trong dấu nháy:

~~~yaml
demo:
  tenants:
    "[team.alpha]":
      enabled: true
~~~

Cũng có thể dùng dấu nháy đơn:

~~~yaml
demo:
  tenants:
    '[team.alpha]':
      enabled: true
~~~

Nhưng không nên viết:

~~~yaml
demo:
  tenants:
    [team.alpha]:
      enabled: true
~~~

và mặc định parser YAML sẽ đọc đó như một scalar key bình thường. Dạng này có thể bị coi là cấu trúc khác hoặc không hợp lệ tùy ngữ cảnh.

Các dấu nháy **không trở thành một phần Map key** sau khi parser YAML giải mã. Chuỗi mà Binder cần xử lý là `[team.alpha]`, từ đó bracket notation biểu thị key `team.alpha`.

### Không đặt brackets ở sai vị trí

Hai tên khác nhau:

~~~properties
demo.tenants.[team.alpha].enabled=true
demo.tenants.team.[alpha].enabled=true
~~~

Tên thứ nhất muốn một key `team.alpha`. Tên thứ hai nhấn mạnh `alpha`, sau một đoạn `team`, có thể tạo hình dạng khác theo kiểu đích. **Đặt bracket quanh toàn bộ key cần giữ**, không chỉ quanh đoạn sau dấu chấm.

## 17. Không nhầm bracket Map với bracket chỉ số List

Spring Boot cũng dùng dấu ngoặc vuông để biểu diễn phần tử danh sách:

~~~yaml
demo:
  endpoints:
    - name: first
      url: "https://first.example.org"
    - name: second
      url: "https://second.example.org"
~~~

Các tên thuộc tính:

~~~properties
demo.endpoints[0].name=first
demo.endpoints[0].url=https://first.example.org
demo.endpoints[1].name=second
demo.endpoints[1].url=https://second.example.org
~~~

Khác biệt:

| Biểu thức | Khi bind vào kiểu phù hợp | Ý nghĩa |
| --- | --- | --- |
| `endpoints[0]` | `List<Endpoint>` | Phần tử index 0 của danh sách |
| `tenants.[team.alpha]` | `Map<String, Tenant>` | Key chuỗi `team.alpha` của Map |
| `labels.[api.example.com]` | `Map<String, String>` | Key `api.example.com` |
| `routes.[/api/v1]` | `Map<String, String>` | Key `/api/v1` |

Sự khác biệt đến từ **kiểu đích và vị trí trong đường dẫn**. Không thể chỉ thấy dấu ngoặc vuông rồi kết luận đó là List.

Một Map có key chuỗi `"0"` về nguyên tắc khác một List có index `0`. Nếu schema cấu hình có các key số, hãy chọn rõ kiểu Java và thêm test để tránh việc diễn giải mơ hồ.

## 18. Tác động của profile và thứ tự ưu tiên PropertySource

Giả sử file chung:

~~~yaml
# application.yml
demo:
  host-aliases:
    "[api.example.com]": catalog-default
    "[images.example.com]": media-default
~~~

File profile production:

~~~yaml
# application-prod.yml
demo:
  host-aliases:
    "[api.example.com]": catalog-prod
~~~

Khi profile `prod` đang hoạt động và không có nguồn ưu tiên cao hơn, giá trị cho key `api.example.com` đến từ file profile, còn key `images.example.com` có thể giữ giá trị từ file chung:

~~~text
api.example.com    → catalog-prod
images.example.com → media-default
~~~

Map binding có thể kết hợp các **entry khác key** từ nhiều PropertySource khi cấu trúc cho phép; với cùng key, nguồn ưu tiên cao hơn thường thắng. Tuy nhiên, **đừng đánh đồng Map với List**: khi bind danh sách từ nhiều nguồn, danh sách ưu tiên cao hơn thường thay thế danh sách thấp hơn thay vì ghép từng phần tử.

Ví dụ nếu một nguồn khác viết không có bracket:

~~~properties
demo.host-aliases.api.example.com=override
~~~

với `Map<String, String>`, cả hai cách viết có thể cùng hướng đến key `api.example.com`. Nhưng nếu Map đổi thành `Map<String,Object>` hoặc Map của custom object, kết luận này không còn an toàn.

### Dotted key được cấu hình ở nhiều nguồn

Đừng chỉ kiểm tra giá trị cuối; hãy kiểm tra xem **các nguồn đang diễn tả đúng cùng một key** hay không.

Ví dụ:

~~~properties
demo.tenants.[team.alpha].timeout=5s
~~~

và:

~~~properties
demo.tenants.team.alpha.timeout=8s
~~~

không nên được coi là hai định nghĩa chắc chắn ghi đè lẫn nhau trong Map của custom object. Dấu ngoặc ảnh hưởng đến tên key khi bind, nên khả năng hai nguồn nhắm cùng một entry phải được xác nhận trên kiểu đích.

## 19. Bind Map lồng trong object và object lồng trong Map

Hai cấu trúc sau khác nhau đáng kể.

### 19.1. Một object chứa Map

~~~yaml
demo:
  routing:
    enabled: true
    destinations:
      "[api.example.com]": catalog
      "[images.example.com]": media
~~~

Java:

~~~java
@ConfigurationProperties(prefix = "demo")
public record DemoProperties(Routing routing) {
    public record Routing(
            boolean enabled,
            java.util.Map<String, String> destinations
    ) {}
}
~~~

Đường dẫn:

~~~text
demo.routing.destinations.[api.example.com]
│    │       │            └── Map key
│    │       └─────────────── Map field
│    └─────────────────────── nested Routing object
└──────────────────────────── prefix
~~~

### 19.2. Một Map chứa object

~~~yaml
demo:
  routing:
    "[api.example.com]":
      enabled: true
      destination: catalog
    "[images.example.com]":
      enabled: false
      destination: media
~~~

Java:

~~~java
@ConfigurationProperties(prefix = "demo")
public record DemoProperties(
        java.util.Map<String, Route> routing
) {
    public record Route(boolean enabled, String destination) {}
}
~~~

Đường dẫn:

~~~text
demo.routing.[api.example.com].destination
│    │       │                 └── field Route.destination
│    │       └──────────────────── key của Map
│    └──────────────────────────── Map routing
└───────────────────────────────── prefix
~~~

Điểm khác nhau là **kiểu của `routing`**. Trong mô hình đầu, `routing` là object và `destinations` là Map bên trong. Trong mô hình sau, chính `routing` là Map và mỗi entry chứa object `Route`.

Nếu copy cấu hình YAML của mô hình này sang Java class của mô hình kia, Binder có thể không đọc ra object như mong muốn. Trước khi xử lý dấu chấm, hãy đối chiếu sơ đồ dữ liệu thực tế.

## 20. Lỗi do đổi từ `Map<String, String>` sang `Map<String, Object>`

Giả sử ứng dụng ban đầu có:

~~~java
@ConfigurationProperties(prefix = "demo")
public record DemoProperties(java.util.Map<String, String> tags) {}
~~~

Và cấu hình:

~~~properties
demo.tags.security.level=high
demo.tags.app.version=1.2
~~~

Ban đầu người lập trình muốn hai entry:

~~~text
tags["security.level"] = "high"
tags["app.version"]     = "1.2"
~~~

Sau đó thay generic value thành `Object` để “hỗ trợ thêm kiểu dữ liệu”:

~~~java
@ConfigurationProperties(prefix = "demo")
public record DemoProperties(java.util.Map<String, Object> tags) {}
~~~

Nếu giữ nguyên tên thuộc tính, Binder có thể tạo cấu trúc Map lồng nhau thay vì key chứa dấu chấm:

~~~text
tags
  security
    level = high
  app
    version = 1.2
~~~

Điều này có thể phá vỡ code gọi:

~~~java
properties.tags().get("security.level");
~~~

Cách diễn đạt key chính xác sau refactor:

~~~properties
demo.tags.[security.level]=high
demo.tags.[app.version]=1.2
~~~

Ngoài ra, nên xem xét liệu nhu cầu dùng `Object` có thực sự cần thiết hay không. Nếu mọi value đều là text, giữ `Map<String,String>` thường đơn giản và ít mơ hồ hơn.

Một thay đổi generic type tưởng nhỏ có thể là **thay đổi schema cấu hình**. Cần test để xác nhận cách bind trước khi triển khai.

## 21. Lỗi do key chứa dấu slash bị mất hoặc biến dạng

Giả sử một ứng dụng ánh xạ HTTP path sang quyền:

~~~properties
demo.permissions./api/v1=read
demo.permissions./admin/write=write
~~~

Người viết mong Map key giữ `/api/v1` và `/admin/write`. Nhưng ký tự `/` không được bảo toàn như một đoạn tên property thông thường khi thiếu bracket.

Cách diễn đạt rõ:

~~~properties
demo.permissions.[/api/v1]=read
demo.permissions.[/admin/write]=write
~~~

Tương đương trong YAML:

~~~yaml
demo:
  permissions:
    "[/api/v1]": read
    "[/admin/write]": write
~~~

Đối với các key được dùng trong logic truy cập hoặc routing, mất dấu slash có thể khiến lookup thất bại hoặc ánh xạ nhầm route.

Cần phân biệt **tính đúng đắn khi bind key** với **an toàn của chính sách truy cập**: ngay cả khi Binder đọc đúng Map, ứng dụng vẫn cần áp dụng nguyên tắc bảo mật phù hợp, không lấy một file cấu hình ví dụ làm cơ chế phân quyền hoàn chỉnh.

## 22. Trường hợp tên property giống tên key literal

Giả sử:

~~~properties
demo.metadata.region.code=VN
~~~

Có ít nhất ba cách diễn giải tùy Java model:

**A. Nested object**

~~~java
record Metadata(Region region) {}
record Region(String code) {}
~~~

`region.code` là đường dẫn field.

**B. Scalar Map**

~~~java
Map<String, String> metadata
~~~

`region.code` có thể là một key nguyên vẹn trong Map.

**C. Map value là custom object**

~~~java
Map<String, RegionInfo> metadata
record RegionInfo(String code) {}
~~~

Nếu muốn key `region` và property `code`, cấu hình `demo.metadata.region.code=VN` có thể phù hợp. Nhưng nếu muốn key literal `region.code`, cần một field của value object, ví dụ:

~~~properties
demo.metadata.[region.code].display-name=Vietnam
~~~

với kiểu `Map<String, RegionInfo>` mà `RegionInfo` có field `displayName`.

Hãy tự hỏi:

- “`region` là tên key hay tên field?”
- “`code` thuộc object value hay nằm trong key?”
- “Map value là scalar hay một object?”
- “Dấu chấm nào phải được giữ nguyên?”

Nếu không trả lời được bốn câu này, rất dễ viết tên thuộc tính chỉ đúng về mặt cú pháp nhưng sai về mặt mô hình dữ liệu.

## 23. Chẩn đoán bằng `@ConfigurationProperties` và test nhỏ

Thay vì đoán Binder sẽ phân tách dấu chấm như thế nào, có thể viết test Spring Boot nhỏ để xác nhận.

Ví dụ cấu hình:

~~~java
import java.time.Duration;
import java.util.Map;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "demo")
public record MapBindingProperties(
        Map<String, String> aliases,
        Map<String, Tenant> tenants
) {
    public record Tenant(boolean enabled, Duration timeout) {}
}
~~~

Test với `ApplicationContextRunner`:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

import java.time.Duration;
import static org.assertj.core.api.Assertions.assertThat;

class MapBindingPropertiesTest {

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(MapBindingProperties.class)
    static class TestConfig {}

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(TestConfig.class);

    @Test
    void preservesDottedMapKeys() {
        runner.withPropertyValues(
                "demo.aliases.api.example.com=catalog",
                "demo.tenants.[team.alpha].enabled=true",
                "demo.tenants.[team.alpha].timeout=5s"
        ).run(context -> {
            assertThat(context).hasNotFailed();

            MapBindingProperties props =
                    context.getBean(MapBindingProperties.class);

            assertThat(props.aliases())
                    .containsEntry("api.example.com", "catalog");

            assertThat(props.tenants())
                    .containsKey("team.alpha");

            assertThat(props.tenants().get("team.alpha").enabled())
                    .isTrue();

            assertThat(props.tenants().get("team.alpha").timeout())
                    .isEqualTo(Duration.ofSeconds(5));
        });
    }
}
~~~

Test này xác nhận hai ý:

1. Dotted key của `Map<String,String>` có thể được bảo toàn.
2. Bracket notation giữ `team.alpha` làm key của Map với value là object.

Trong dự án thật, chạy test bằng dependency Spring Boot Test phù hợp, ví dụ `spring-boot-starter-test` ở scope test.

Với key dùng ký tự ngoài dấu chấm như slash, thêm case:

~~~java
runner.withPropertyValues(
    "demo.aliases.[/api/v1]=catalog"
).run(context -> {
    MapBindingProperties props =
            context.getBean(MapBindingProperties.class);
    assertThat(props.aliases())
            .containsEntry("/api/v1", "catalog");
});
~~~

Kết quả test là cách đáng tin cậy để xác nhận schema trước khi tích hợp vào hệ thống triển khai.

## 24. Cấu hình có nested Map sâu hơn

Một ứng dụng có Map các tenant, mỗi tenant chứa Map route:

~~~yaml
demo:
  tenants:
    "[tenant.alpha]":
      routes:
        "[/api/v1]": read
        "[/api/v2]": write
    "[tenant.beta]":
      routes:
        "[/api/v1]": monitor
~~~

Java:

~~~java
import java.util.Map;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "demo")
public record DemoProperties(
        Map<String, Tenant> tenants
) {
    public record Tenant(Map<String, String> routes) {}
}
~~~

Tên phẳng:

~~~properties
demo.tenants.[tenant.alpha].routes.[/api/v1]=read
demo.tenants.[tenant.alpha].routes.[/api/v2]=write
demo.tenants.[tenant.beta].routes.[/api/v1]=monitor
~~~

Phân tích:

~~~text
demo
└─ tenants (Map<String,Tenant>)
   ├─ [tenant.alpha] (key)
   │  └─ routes (Map<String,String>)
   │     ├─ [/api/v1] (key) → read
   │     └─ [/api/v2] (key) → write
   └─ [tenant.beta] (key)
      └─ routes (Map<String,String>)
         └─ [/api/v1] (key) → monitor
~~~

Có **hai tầng Map key** khác nhau. Mỗi key chứa ký tự đặc biệt nên được biểu diễn trong bracket riêng, còn `routes` là tên field của object `Tenant`.

Không nên gom cả `tenant.alpha.routes./api/v1` thành một key duy nhất, vì như vậy sẽ làm mất ranh giới các object/Map mà Java model mong đợi.

## 25. Kiểm tra tên thực tế bằng log, Actuator và code

Khi một Map key không được đọc đúng, chẩn đoán theo thứ tự:

1. **Xác định field Java:** nó là `Map<String,String>`, `Map<String,Object>`, `Map<String, CustomType>` hay nested object?
2. **Viết lại đường dẫn:** prefix của `@ConfigurationProperties`, tên Map field, key, rồi các field của value object.
3. **Đặt bracket quanh toàn bộ key literal cần giữ dấu chấm/ký hiệu.**
4. **Kiểm tra YAML quoting:** key bracket có được đặt trong dấu nháy chưa?
5. **Kiểm tra property sources:** có file profile, biến môi trường hoặc CLI ghi đè cùng tên không?
6. **Kiểm tra tên key trong object sau binding**, không chỉ nhìn text YAML.
7. **Viết test** cho key đặc biệt và một key bình thường.
8. **Kiểm tra validation:** nếu entry bắt buộc thiếu, đừng để ứng dụng chạy sai mà không phát hiện.

Có thể tạm quan sát **tên key** của Map trong một môi trường thử nghiệm:

~~~java
import org.springframework.boot.CommandLineRunner;
import org.springframework.stereotype.Component;

@Component
public class MapKeyPrinter implements CommandLineRunner {
    private final DemoProperties properties;

    public MapKeyPrinter(DemoProperties properties) {
        this.properties = properties;
    }

    @Override
    public void run(String... args) {
        if (properties.tenants() != null) {
            System.out.println("Tenant keys: "
                    + properties.tenants().keySet());
        }
    }
}
~~~

Đây chỉ là cách minh họa. Trong production, key có thể chứa tên khách hàng, định danh nhạy cảm hoặc thông tin cần bảo vệ; không nên log toàn bộ key/value một cách tùy tiện.

Nếu dùng Spring Boot Actuator, endpoint `configprops` có thể hỗ trợ xem bean cấu hình sau binding, còn `env` có thể hỗ trợ truy nguồn cấu hình khi được bật. Cần giới hạn quyền truy cập và che các giá trị nhạy cảm.

## 26. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| `Map<String,String>` giữ `a.b` làm một key | Đây là quy tắc với Map scalar | Nếu ý định là nested object, đổi Java model phù hợp |
| `Map<String,Object>` tạo nested Map không mong muốn | Dấu chấm được xem là path | Dùng `[a.b]` để giữ literal key |
| `Map<String,Tenant>` không có key `team.alpha` | Không đặt bracket quanh key chứa dấu chấm | Dùng `[team.alpha]` |
| YAML báo lỗi ở key `[team.alpha]` | Không quote tên key | Viết `"[team.alpha]"` |
| Key `/api/v1` bị mất dấu slash | Thiếu bracket bảo toàn ký tự đặc biệt | Dùng `"[/api/v1]"` hoặc `.[/api/v1]` tùy nguồn |
| Map key trông khác sau refactor generic type | Thay scalar value thành Object/custom class | Cập nhật schema property và test |
| Map entry có key nhưng field con không được bind | Đường dẫn còn lại không khớp kiểu object | Kiểm tra tên field và cấu trúc record/class |
| Dùng biến môi trường thay key có dấu chấm nhưng lookup thất bại | Tên biến không giữ nguyên ranh giới dotted Map key | Dùng nguồn cấu hình hỗ trợ bracket hoặc đổi schema có chủ đích |
| `@Value("${demo.tags.a.b}")` cho kết quả khác mong đợi | Placeholder đơn lẻ không thay thế đầy đủ cơ chế Map binding | Dùng `@ConfigurationProperties` và test kết quả Map |
| List index `[0]` bị nhầm là Map key | Không xét kiểu đích và cấu trúc dữ liệu | Phân biệt `List` và `Map` trong Java model |
| Key chứa dấu chấm bị xem là field lồng nhau | Value Map là custom object | Bao toàn bộ Map key trong bracket |
| Giá trị từ file ngoài khác file trong JAR | Thứ tự ưu tiên của PropertySource | Kiểm tra nguồn đang có hiệu lực |

Nếu cần thống nhất cách đặt tên, hãy chọn một quy tắc trong toàn dự án: **key định danh tự do có dấu chấm hoặc ký tự đặc biệt luôn dùng bracket notation khi lưu file**. Quy tắc này làm ý định rõ hơn, kể cả lúc hiện tại Map chỉ có value scalar.

## 27. Bài tập thực hành

### Bài 1 — Map scalar với key dạng domain

Cấu hình:

~~~properties
demo.hosts.api.example.com=catalog
demo.hosts.auth.example.com=identity
~~~

Java:

~~~java
@ConfigurationProperties(prefix = "demo")
public record HostProperties(
        java.util.Map<String, String> hosts
) {}
~~~

Hỏi: key `api.example.com` có thể được giữ nguyên không?

**Đáp án:** có. Với `Map<String,String>`, value là scalar, nên dấu chấm trong key có thể được giữ. Có thể chuyển sang `demo.hosts.[api.example.com]` để thể hiện ý định một cách tường minh.

### Bài 2 — Map chứa object

Có:

~~~java
@ConfigurationProperties(prefix = "demo")
public record TenantProperties(
        java.util.Map<String, Tenant> tenants
) {
    public record Tenant(String region, boolean enabled) {}
}
~~~

Muốn tenant ID `team.alpha` có `region=asia` và `enabled=true`. Hãy viết YAML.

**Đáp án:**

~~~yaml
demo:
  tenants:
    "[team.alpha]":
      region: asia
      enabled: true
~~~

Hoặc `.properties`:

~~~properties
demo.tenants.[team.alpha].region=asia
demo.tenants.[team.alpha].enabled=true
~~~

### Bài 3 — Đường dẫn object hay Map key?

Hai tên:

~~~properties
demo.client.connection.timeout=5s
demo.clients.[connection.timeout].enabled=true
~~~

Hỏi: dấu chấm trong `connection.timeout` ở hai dòng giống nhau không?

**Đáp án:** không. Dòng thứ nhất có thể là đường dẫn object `client` → `connection` → `timeout`. Dòng thứ hai, nếu `clients` là Map với value có field `enabled`, chứa key nguyên vẹn `connection.timeout` trong bracket.

### Bài 4 — Khác nhau giữa `Map<String,String>` và `Map<String,Object>`

Dữ liệu:

~~~properties
demo.tags.security.level=high
~~~

Hỏi: tại sao khi đổi kiểu từ `Map<String,String>` sang `Map<String,Object>`, code `tags.get("security.level")` có thể không còn hoạt động?

**Đáp án:** với Map scalar, `security.level` có thể được giữ làm key. Với Map value `Object`, dấu chấm có thể biểu diễn cấu trúc nested Map. Dùng `demo.tags.[security.level]=high` khi muốn bảo toàn key literal.

### Bài 5 — Key chứa slash

Cho:

~~~yaml
demo:
  routes:
    /api/v1: catalog
~~~

Cần một `Map<String,String>` có key đúng `/api/v1`. Hãy sửa YAML.

**Đáp án:**

~~~yaml
demo:
  routes:
    "[/api/v1]": catalog
~~~

### Bài 6 — Map chứa Map

Java:

~~~java
@ConfigurationProperties(prefix = "demo")
public record RoutingProperties(
        java.util.Map<String, java.util.Map<String, String>> routes
) {}
~~~

Muốn key ngoài là `tenant.alpha` và key trong là `/orders`, value `allow`. Hãy viết property.

**Đáp án gợi ý:**

~~~properties
demo.routes.[tenant.alpha].[/orders]=allow
~~~

Trong YAML:

~~~yaml
demo:
  routes:
    "[tenant.alpha]":
      "[/orders]": allow
~~~

Hai cặp bracket biểu thị hai key khác nhau, không phải một đường dẫn duy nhất.

### Bài 7 — Phát hiện lỗi từ cấu hình không có bracket

Có:

~~~properties
demo.tenants.team.alpha.timeout=5s
~~~

Java:

~~~java
@ConfigurationProperties(prefix = "demo")
public record TenantProperties(
        java.util.Map<String, Tenant> tenants
) {
    public record Tenant(java.time.Duration timeout) {}
}
~~~

Mục tiêu là `tenants.get("team.alpha").timeout()` bằng 5 giây. Nên thay thành gì?

**Đáp án:**

~~~properties
demo.tenants.[team.alpha].timeout=5s
~~~

Bracket giữ key `team.alpha` nguyên vẹn trước khi Binder vào field `timeout`.

### Bài 8 — Dấu chấm trong key có nghĩa là key phải chứa bracket ở mọi trường hợp?

**Đáp án:** không bắt buộc trong mọi trường hợp. Với Map có value scalar như `Map<String,String>`, Spring Boot có thể giữ dấu chấm trong key ngay cả khi thiếu bracket. Nhưng với Map value non-scalar, bracket cần thiết để phân biệt literal key và đường dẫn object. Về phong cách cấu hình, dùng bracket cho key định danh có dấu chấm vẫn rất hữu ích.

## 28. Ghi nhớ

- **Dấu chấm `.` trong tên thuộc tính có thể là dấu phân cấp hoặc một phần Map key**, tùy kiểu đích mà Spring Boot Binder đang xử lý.
- Với **`Map<String,String>`** và một số value scalar khác, key như `api.example.com` có thể được bảo toàn mà không cần bracket.
- Với **`Map<String,Object>` hoặc `Map<String, CustomType>`**, dấu chấm không bracket có thể bị diễn giải thành đường dẫn lồng nhau.
- Khi muốn một key giữ nguyên `team.alpha`, hãy dùng **`[team.alpha]`**; nếu value là object, tiếp tục bằng `.field`, ví dụ `app.tenants.[team.alpha].timeout`.
- Trong **YAML**, key bracket cần được đặt trong dấu nháy: `"[team.alpha]"`.
- Với ký tự đặc biệt như **`/api/v1`**, bracket là cách diễn tả literal key cần bảo toàn.
- **List index** như `[0]` khác **Map key** như `[tenant.alpha]`; việc diễn giải dựa vào kiểu Java và vị trí.
- Đổi từ scalar Map sang Map object có thể là một **schema change**, nên kiểm thử các key chứa dấu chấm.
- Không biến key dotted thành biến môi trường bằng phép thay ký tự cơ học rồi kỳ vọng giữ nguyên ý nghĩa literal.
- Khi chẩn đoán, hãy kiểm tra **prefix, kiểu Map value, bracket notation, file YAML/properties, property source ưu tiên và Map key thực tế**.

## Tài liệu tham khảo

- [Spring Boot Reference — Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html)
- [Spring Boot Reference — Binding Maps](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.relaxed-binding.maps)
- [Spring Boot Reference — Type-safe Configuration Properties](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.typesafe-configuration-properties)
- [Spring Boot API — ConfigurationProperties](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/ConfigurationProperties.html)
