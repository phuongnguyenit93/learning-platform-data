# Giới hạn truy cập Actuator và chính sách hiển thị giá trị khi chẩn đoán

## 1. Tại sao Actuator hữu ích nhưng cần một ranh giới bảo mật riêng?

Spring Boot Actuator giúp quan sát ứng dụng mà không phải tự viết rất nhiều API quản trị. Khi một service không khởi động đúng, bind sai `@ConfigurationProperties`, chọn nhầm profile, không kết nối được database hoặc có một auto-configuration không hoạt động, những endpoint như `health`, `env`, `configprops`, `conditions`, `beans`, `metrics` và `loggers` có thể rút ngắn đáng kể thời gian chẩn đoán.

Nhưng chính vì Actuator biết nhiều về ứng dụng, nó cũng có thể tiết lộ thông tin hữu ích cho người không có quyền: tên property, cấu trúc bean, tên host nội bộ, đường URL, trạng thái dependency, tên thread, số liệu runtime, đường dẫn API và thậm chí dữ liệu nằm trong heap dump hoặc log.

Ví dụ trong cấu hình:

```yaml
payments:
  gateway:
    endpoint: "https://gateway.example.test"
    api-key: "${PAYMENTS_API_KEY}"
  retry:
    max-attempts: 3
```

Một yêu cầu `/actuator/env` có thể giúp đội vận hành xác định **property đã được nạp từ nguồn nào**. Nhưng không nên biến yêu cầu chẩn đoán ấy thành cơ chế tiết lộ `PAYMENTS_API_KEY`.

Cần bảo vệ hệ thống theo **nhiều lớp độc lập**:

1. Endpoint có được **enable** và tồn tại trong application context không?
2. Endpoint có được **expose** qua HTTP hoặc JMX không?
3. Client mạng có kết nối được tới địa chỉ/port quản trị không?
4. Request có được **authenticate** và **authorize** đúng vai trò không?
5. Trong response, những giá trị nào được **sanitized/masked**?
6. Dữ liệu trả về có được lưu vào log, APM, proxy, cache hay ticket không?
7. Có cần một quyền quản trị tạm thời, có audit và thời hạn, thay vì mở endpoint vĩnh viễn không?

**Nguyên tắc:** Được phép truy cập một endpoint chưa có nghĩa được phép xem mọi giá trị bên trong endpoint đó. Và việc response đã che giá trị chưa có nghĩa endpoint an toàn để công khai ra Internet.

Bài thuộc nhóm **Chẩn đoán lỗi** trong chủ đề **Spring Boot Externalized Configuration**. Lab minh họa dùng Java 21, Spring Boot 3.3.13, Gradle, Spring MVC và Spring Security. Tất cả hostname, key và credential thử nghiệm đều là giả lập.

### Kết quả học tập

Sau bài này, bạn có thể:

- Phân biệt `enabled`, `exposed`, `reachable`, `authenticated`, `authorized` và `sanitized`.
- Biết mặc định HTTP exposure của Spring Boot Actuator 3.3.
- Khai báo allowlist HTTP endpoints và tránh `include: "*"` không kiểm soát.
- Sử dụng Spring Security `SecurityFilterChain` với `EndpointRequest` để phân quyền.
- Hiểu điều gì xảy ra khi một custom `SecurityFilterChain` khiến bảo mật Actuator tự động của Boot không còn áp dụng.
- Hiểu chính sách `management.endpoint.env.show-values` và `management.endpoint.configprops.show-values`.
- Phân biệt `never`, `when-authorized`, `always`; biết cách đặt `roles` và giới hạn khi dùng JMX.
- Áp dụng `SanitizingFunction` để che thêm key nhạy cảm theo chính sách ứng dụng.
- Chọn chiến lược bảo vệ `health`, `info`, `metrics`, `loggers`, `heapdump`, `logfile`, `threaddump` và endpoint tùy biến.
- Chạy demo local có profile chẩn đoán riêng và test `401`, `403`, `200` cùng yêu cầu không lộ key giả.
- Thiết kế kênh truy cập tạm thời cho đội vận hành và quy trình gỡ bỏ sau khi xử lý sự cố.

## 2. Đọc đúng khái niệm: enabled không giống exposed

Spring Boot Actuator có những endpoint tích hợp như:

```text
health, info, env, configprops, conditions, beans,
mappings, metrics, loggers, threaddump, heapdump,
logfile, httpexchanges, scheduledtasks, caches,
startup, prometheus, shutdown, quartz...
```

Không phải endpoint nào cũng luôn sẵn có. Một số endpoint yêu cầu bean/điều kiện bổ sung; chẳng hạn `prometheus` cần registry, `httpexchanges` cần repository, `startup` cần cơ chế ghi lại startup steps, `logfile` cần log file được cấu hình.

Có hai công tắc quan trọng:

**Enablement:** endpoint có được tạo và có thể hoạt động không?

```properties
management.endpoint.env.enabled=false
```

**Exposure:** endpoint có được công bố qua một transport như HTTP hay JMX không?

```properties
management.endpoints.web.exposure.include=health,info
```

Trong Spring Boot 3.3, các endpoint tích hợp nói chung được enable trừ `shutdown`, nhưng **chỉ `health` được expose qua HTTP và JMX theo mặc định**. Một endpoint như `env` có thể tồn tại trong hệ thống nhưng chưa có route HTTP công khai.

Bảng tóm tắt:

| Tình trạng | Ý nghĩa | Hành vi cần chú ý |
| --- | --- | --- |
| Không enabled | Endpoint không được tạo như endpoint khả dụng | Không thể gọi qua cơ chế thông thường |
| Enabled, không exposed qua HTTP | Không có route HTTP Actuator tương ứng | Có thể vẫn expose qua JMX nếu bạn cấu hình |
| Enabled và exposed qua HTTP | Route có thể tồn tại | Vẫn phải xét firewall và Spring Security |
| Reachable nhưng chưa authenticated | Caller tiếp cận route nhưng chưa có danh tính | Có thể nhận 401 tùy chính sách |
| Authenticated nhưng không đủ quyền | Có danh tính nhưng không thuộc vai trò yêu cầu | Thường nhận 403 |
| Authorized vào endpoint | Request được chấp nhận | Giá trị bên trong vẫn có thể masked |
| `show-values` cho phép xem raw | Một số giá trị có thể hiển thị | `SanitizingFunction` vẫn có thể che thêm |

Đừng xem một lần nhận `404` là bằng chứng duy nhất rằng endpoint đã được vô hiệu hóa. Tùy chain bảo mật và gateway, đường không exposed có thể bị một lớp bảo mật chặn trước khi tới route resolver.

### 2.1. Bảo vệ mặc định là điểm xuất phát, không phải chiến lược duy nhất

Với Spring Security có trên classpath và **không** có `SecurityFilterChain` tùy biến, Spring Boot thường bảo vệ các Actuator endpoints ngoài health bằng auto-configuration. Nhưng khi bạn định nghĩa **bất kỳ** custom `SecurityFilterChain` bean nào, cấu hình bảo mật tự động này sẽ nhường quyền để ứng dụng chịu trách nhiệm đầy đủ.

Vì vậy, thêm một chain để bảo vệ API nghiệp vụ có thể làm Actuator thay đổi cách được bảo vệ nếu bạn không khai báo các quy tắc cho Actuator.

**Không dựa vào câu “Spring Boot tự bảo vệ Actuator” sau khi đã tự viết security configuration.** Luôn kiểm tra effective filter chains và kết quả HTTP thật.

## 3. HTTP exposure: allowlist thay vì mở toàn bộ

Cấu hình tối giản:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,info"
```

Nếu cần metrics cho monitoring nội bộ:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,info,metrics,prometheus"
```

`prometheus` chỉ thực sự sẵn có khi dependency và registry cần thiết tồn tại. Việc thêm tên endpoint vào allowlist không tự bổ sung dependency.

Trong một buổi chẩn đoán có phê duyệt, bạn có thể **tạm thời** expose thêm:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,info,metrics,env,configprops,conditions"
```

Những endpoint nhạy cảm phải được chặn bằng mạng và security roles; không công khai chỉ vì chúng nằm sau `/actuator`.

### 3.1. `exclude` thắng `include`

Ví dụ:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: "*"
        exclude: "env,configprops,heapdump,logfile,shutdown"
```

Về cấu hình, `exclude` ưu tiên hơn `include`. Tuy nhiên, trong production **không khuyến khích** dùng `include: "*"` và hy vọng một danh sách cấm đầy đủ mãi mãi. Khi framework hoặc dependency bổ sung endpoint mới, endpoint ấy có thể vô tình được expose.

Cách dễ audit hơn là **chỉ liệt kê endpoint được phép**. Nếu đội vận hành cần endpoint mới, có một thay đổi cấu hình được review và test.

Trong YAML, ký tự `*` cần được quote. Ví dụ dùng:

```yaml
include: "*"
```

thay vì một bare star có thể bị YAML parser hiểu khác ý định.

### 3.2. Web exposure và JMX exposure độc lập

Các thuộc tính:

```properties
management.endpoints.web.exposure.include=health,info
management.endpoints.jmx.exposure.include=health
```

kiểm soát hai kênh khác nhau.

Nếu policy của hệ thống không dùng JMX để quản trị, có thể vô hiệu hóa exposure qua JMX:

```yaml
management:
  endpoints:
    jmx:
      exposure:
        exclude: "*"
```

Điều này đặc biệt quan trọng khi có chính sách `show-values: when-authorized`: với sanitizable Actuator endpoints trong Spring Boot 3.3, **JMX được coi là đã authorized cho mục đích hiển thị giá trị**. Vì vậy, đừng dựa vào vai trò HTTP để bảo vệ một endpoint được expose qua JMX.

Nếu tổ chức cần JMX, phải có quy tắc kết nối JMX riêng, xác thực, mã hóa và quyền truy cập mạng. HTTP RBAC không tự bảo vệ đường JMX.

## 4. Ba tầng bảo mật cần triển khai cùng nhau

Một hệ thống có thể được bảo vệ theo hướng:

```text
Client
  |
  | 1. VPN / private network / firewall / NetworkPolicy
  v
Management address/port
  |
  | 2. Endpoint enabled + HTTP allowlist
  v
/actuator/{id}
  |
  | 3. Spring Security authentication + authorization
  v
Endpoint handler
  |
  | 4. show-values + SanitizingFunction
  v
JSON hoặc response artifact
  |
  | 5. Log/proxy/APM/ticket/retention policy
  v
Người được phép sử dụng
```

Từng tầng ngăn một loại rủi ro khác nhau.

Ví dụ:

- Tắt `env` exposure khiến đường HTTP không còn xuất hiện trong Actuator web mappings.
- NetworkPolicy chặn caller không thuộc mạng quản trị.
- Spring Security đòi vai trò `OPS` trước khi gọi endpoint.
- `show-values=never` che giá trị cả khi role OPS đã gọi thành công.
- `SanitizingFunction` che những key đặc thù kể cả lúc policy được mở để hiển thị giá trị.
- Quy trình chẩn đoán cấm copy cả response chứa dữ liệu nội bộ vào ticket công khai.

Một lớp mạnh không thay được tất cả lớp khác.

## 5. Các endpoint nên đánh giá theo mức độ rủi ro

| Endpoint | Dữ liệu/tác vụ | Chính sách thường nên chọn |
| --- | --- | --- |
| `health` | Tình trạng tổng quát và có thể gồm các dependency | Có thể dùng cho probe; giới hạn details |
| `info` | Metadata tùy ứng dụng | Chỉ publish allowlist không nhạy cảm |
| `metrics` | Số liệu, tên metric, tag/label | Giới hạn monitoring role/network |
| `prometheus` | Metrics exposition | Chỉ cho scraper được phép |
| `env` | Danh sách property sources/keys, values tùy sanitizer | Thường tắt; tạm expose cho OPS |
| `configprops` | ConfigurationProperties beans và dữ liệu đã bind | Thường tắt; tạm expose cho OPS |
| `conditions` | Lý do auto-config match/mismatch | Dùng trong chẩn đoán hạn chế |
| `beans` | Bean names/types và dependencies | Chỉ nhân sự vận hành được phép |
| `mappings` | Request mappings và endpoint structure | Không công khai |
| `loggers` | Xem và có thể thay logging levels | Quyền quản trị, kiểm soát POST/CSRF |
| `heapdump` | Dump bộ nhớ process | Rất nhạy cảm; không expose thường trực |
| `threaddump` | Stack traces, thread names | Hạn chế, có thể tiết lộ dữ liệu |
| `logfile` | Nội dung log file | Hạn chế; có thể chứa dữ liệu nhạy cảm |
| `httpexchanges` | HTTP request-response metadata | Phụ thuộc repository, cần xem retention |
| `shutdown` | Yêu cầu shutdown ứng dụng | Mặc định disabled; không mở tùy tiện |
| `quartz` | Job và scheduler data | Có khả năng chứa thông tin nhạy cảm |
| Custom endpoint | Tùy code người phát triển | Bảo vệ theo dữ liệu và hành động thực tế |

`health` không mặc định an toàn nếu bạn quyết định hiển thị toàn bộ component details như database hostname hoặc lỗi của dependency. `info` cũng có thể trở nên nhạy cảm nếu đội phát triển tự đưa commit metadata hoặc connection string vào đó.

### 5.1. Endpoint có hành động thay đổi trạng thái đáng cảnh giác hơn

Những endpoint như `loggers` có khả năng thay log level; nếu để DEBUG quá lâu có thể tạo lưu lượng log lớn và lộ dữ liệu. `shutdown` có thể kết thúc process. Các endpoint tùy biến còn có thể trigger jobs hoặc thay cấu hình.

Cần phân loại **read-only** so với **write/operation**. Spring Security thường bật CSRF cho HTTP request thay đổi trạng thái theo defaults của nó; nếu caller nhận `403` khi POST, đừng tắt toàn bộ CSRF mà không đánh giá. Với endpoint quản trị dành cho máy, có thể thiết kế một security chain chuyên biệt, auth mạnh và CSRF policy phù hợp, nhưng phạm vi phải hẹp và có test.

## 6. `env` và `configprops` giúp chẩn đoán gì?

**`/actuator/env`** cung cấp thông tin về `ConfigurableEnvironment` và các property sources. Nó hữu ích khi cần biết:

- Ứng dụng có đọc được key được đặt trong environment không?
- Có những sources nào và thứ tự ra sao?
- Có một property ở nhiều nguồn khác nhau không?
- Profile đã được bật đúng chưa?
- Property cụ thể có được nhìn thấy trong một source không?

**`/actuator/configprops`** cung cấp thông tin tổng hợp về các bean `@ConfigurationProperties`, giúp biết bean nào đã được bind, thuộc prefix nào, và dữ liệu bind được trình bày như thế nào trong phạm vi endpoint cho phép.

Hai endpoint này **không hoàn toàn tương đương**:

```text
/env        -> góc nhìn các nguồn property trong Environment
/configprops -> góc nhìn các configuration properties beans
```

Một key có trong `Environment` nhưng bean vẫn nhận dữ liệu khác có thể do tên canonical sai, conversion/validation, constructor binding, thời điểm bind hoặc một bean đã được tạo trước. `/env` không tự chứng minh mọi object nghiệp vụ đã áp dụng giá trị đó.

### 6.1. Nhìn thấy source metadata cũng có rủi ro

Ngay cả khi tất cả giá trị được hiển thị là `******`, một phản hồi `/env` có thể cho thấy:

- Có `SPRING_DATASOURCE_URL` trong môi trường.
- Một config file nằm ở một đường dẫn cụ thể.
- Tên property tùy biến của tính năng đang được bật.
- Mối quan hệ giữa các cấu hình và secrets.
- Những nguồn cấu hình đã được import.

Do đó, masking chỉ giảm rủi ro **giá trị**, chứ không loại bỏ mọi rủi ro **metadata và cấu trúc**. Ràng buộc truy cập `/env` vẫn cần thiết.

## 7. Chính sách hiển thị giá trị: `show-values`

Spring Boot 3.3 hỗ trợ `show-values` cho các endpoint có khả năng chứa giá trị nhạy cảm, đặc biệt `env`, `configprops` và `quartz`.

Ví dụ:

```properties
management.endpoint.env.show-values=never
management.endpoint.configprops.show-values=never
```

Các giá trị cấu hình có ý nghĩa:

| Giá trị | Ý nghĩa | Rủi ro |
| --- | --- | --- |
| `never` | Các giá trị bị che/masked | An toàn hơn, nhưng metadata key/source vẫn có thể lộ |
| `when-authorized` | Chỉ principal được xem là authorized mới có thể xem giá trị chưa che, trừ sanitizer tùy biến | Cần auth và roles đúng |
| `always` | Cho phép hiển thị cho mọi người có thể gọi endpoint, trừ sanitizer tùy biến | Nguy hiểm nếu endpoint reachable |

Trong Spring Boot 3.3, giá trị mặc định là **`never`**, các giá trị thường được thay bằng:

```text
******
```

Điều đáng chú ý: từ Spring Boot 3.x, mặc định `/env` và `/configprops` **che mọi giá trị**, không chỉ những key có tên chứa chữ `password` hoặc `secret`. Không nên dựa vào mô tả từ các phiên bản cũ mà nghĩ chỉ một số mẫu tên key mới bị masked.

### 7.1. `never`: lựa chọn production phù hợp khi vẫn cần biết source

```yaml
management:
  endpoint:
    env:
      show-values: never
    configprops:
      show-values: never
```

Bạn có thể xác nhận **key có tồn tại** và có thể hiểu nguồn của nó mà không trả về raw value.

Tuy nhiên, vì đường dẫn property, nguồn và tên bean cũng là thông tin nội bộ, vẫn nên hạn chế endpoint truy cập bởi OPS/diagnostics role và mạng quản trị.

### 7.2. `when-authorized`: có điều kiện và phải xác định roles

Ví dụ:

```yaml
management:
  endpoint:
    env:
      show-values: when-authorized
      roles: "OPS"
    configprops:
      show-values: when-authorized
      roles: "OPS"
```

Với HTTP, Spring Boot coi một người dùng là được phép xem raw value khi:

1. Đã được **authenticate**.
2. Có role nằm trong danh sách `roles` của endpoint (nếu danh sách được cấu hình).

**Nếu không cấu hình `roles`, bất kỳ người dùng HTTP đã authenticated nào có thể được coi là authorized để xem giá trị**, miễn endpoint cho phép họ truy cập. Đây là lý do quan trọng để khai báo role cụ thể khi cho phép `when-authorized`.

Trong Spring Security, `hasRole("OPS")` thường yêu cầu authority `ROLE_OPS`. Cấu hình user với `roles: OPS` tương ứng với authority đó.

### 7.3. `always`: không phải cách debug mặc định

Ví dụ nguy hiểm:

```properties
management.endpoint.env.show-values=always
```

Nếu endpoint bị expose và caller vượt qua được các lớp mạng/auth, giá trị có thể hiển thị rõ ràng trừ những key mà custom sanitizer vẫn che.

Không bật `always` trong production chỉ để tìm một lỗi bind. Thường có giải pháp ít rủi ro hơn: xem metadata, kiểm tra key bằng allowlist, thêm một diagnostic endpoint trả kết quả boolean hoặc dùng role hạn chế cùng `SanitizingFunction`.

### 7.4. JMX là trường hợp cần lưu ý riêng

Theo tài liệu Spring Boot 3.3, với sanitizable endpoints, **JMX callers được xem là authorized** khi đánh giá `when-authorized`. Điều đó nghĩa là `roles` trong cấu hình `env` không biến HTTP role policy thành một ACL tự động cho JMX.

Nếu không có nhu cầu dùng JMX, khai báo:

```yaml
management:
  endpoints:
    jmx:
      exposure:
        exclude: "*"
```

Nếu cần JMX, bảo vệ transport, authentication và quyền truy cập JMX theo chính sách hạ tầng. Không xem `when-authorized` là đủ cho mọi protocol.

## 8. `SanitizingFunction`: che thêm key dù đã authorized

Spring Boot cho phép định nghĩa các bean:

```java
org.springframework.boot.actuate.endpoint.SanitizingFunction
```

để quyết định một giá trị được che theo chính sách custom của ứng dụng.

Tài liệu nhấn mạnh rằng dù `show-values` là `when-authorized` hoặc `always`, một custom `SanitizingFunction` **vẫn có thể áp dụng**. Vì vậy, đội bảo mật có thể giữ một số loại giá trị nhạy cảm luôn ở dạng `******`, kể cả đối với người có quyền chẩn đoán.

Ví dụ policy:

```text
diagnostics.api-key  -> luôn che
any *.password        -> luôn che
any *.token           -> luôn che
any *.secret          -> luôn che
other safe diagnostics -> có thể hiện nếu đúng role
```

### 8.1. Code dùng `SanitizingFunction` trong Spring Boot 3.3

```java
package dev.example.actuator;

import java.util.Locale;

import org.springframework.boot.actuate.endpoint.SanitizingFunction;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class SanitizationConfiguration {

    @Bean
    public SanitizingFunction appSensitiveValues() {
        return data -> {
            String key = data.getKey()
                    .toLowerCase(Locale.ROOT)
                    .replace("_", "-");

            boolean sensitive =
                    key.contains("api-key")
                    || key.contains("apikey")
                    || key.contains("password")
                    || key.contains("token")
                    || key.contains("credential")
                    || key.contains("private-key")
                    || key.contains("secret")
                    || key.contains("authorization");

            return sensitive
                    ? data.withSanitizedValue()
                    : data;
        };
    }
}
```

`SanitizableData.withSanitizedValue()` tạo một dữ liệu sanitization mới với value đã bị thay thế. Code **không sửa `Environment` hoặc bean cấu hình thật**; nó thay cách trình bày dữ liệu trong endpoint.

Danh sách substring trên là **chính sách minh họa**, chưa thể bao phủ mọi secret. Secret có thể dùng key không có từ khóa nhạy cảm hoặc nằm trong một cấu trúc khác. Phân loại dữ liệu và kiểm soát endpoint vẫn cần thiết.

### 8.2. Không cố tự giải mã hoặc log giá trị trong sanitizing function

Sai ý định:

```java
// Không làm việc này trong sanitizer:
System.out.println("Current value: " + data.getValue());
```

Trong một hệ thống chẩn đoán, chính sanitizer phải là thành phần **giảm rò rỉ**, không phải nơi tập hợp raw values.

### 8.3. Khi sanitizer không đủ

`SanitizingFunction` chỉ áp dụng trong những endpoint sử dụng cơ chế sanitization tương ứng. Nó không tự bảo vệ:

- Response của một `@RestController` tùy biến.
- Log chứa `${PAYMENTS_API_KEY}` do chính ứng dụng in.
- Stacktrace hoặc exception message tự đưa secret vào.
- Heap dumps và memory snapshots.
- Trace tags, metrics labels hoặc message headers có dữ liệu nhạy cảm.
- Request/response body do debug logger hoặc HTTP client logging ghi lại.

Đừng triển khai sanitizer rồi tuyên bố hệ thống đã chống mọi hình thức lộ secret.

## 9. Phân biệt quyền gọi endpoint và quyền xem giá trị

Giả sử `/actuator/env` được expose, Spring Security yêu cầu role `OPS` để gọi nó, còn `show-values` đặt `when-authorized` với roles `OPS`.

Khi đó:

| Caller | Quyền HTTP vào `/env` | Policy hiển thị value |
| --- | --- | --- |
| Anonymous | Không được; thường 401 | Không có response giá trị |
| Authenticated `VIEWER` | Không được; thường 403 | Không có response giá trị |
| Authenticated `OPS` | Được | Có thể xem value trừ key custom sanitizer che |
| `OPS` nhưng key `diagnostics.api-key` | Được | Giá trị vẫn `******` nhờ custom sanitizer |
| Caller qua JMX | Phụ thuộc JMX access | Không dựa vào role HTTP để xác thực |

Nếu policy HTTP cho một `VIEWER` xem `/env` nhưng endpoint `roles` yêu cầu OPS, viewer **có thể được trả metadata nhưng các value bị masked**. Tuy nhiên, thường không cần cho viewer đọc danh sách property sources nếu không có lý do nghiệp vụ.

Tốt nhất là thiết kế hai lớp:

```text
HTTP authorization -> có được truy cập endpoint không?
show-values + sanitizer -> được xem dữ liệu chi tiết đến đâu?
```

Không trộn hai mục đích thành một thuộc tính duy nhất.

## 10. SecurityFilterChain của Spring Boot: tránh làm hở Actuator khi tùy biến

Một ứng dụng dùng Spring Security và khai báo custom filter chain:

```java
@Bean
SecurityFilterChain applicationSecurity(HttpSecurity http) { ... }
```

sẽ khiến một phần auto-configuration security của Boot **back off**. Vì vậy, cần khai báo tường minh security cho Actuator và API nghiệp vụ.

Một cấu hình gồm hai chain là cách minh họa rõ:

- Chain ưu tiên 1 khớp các Actuator endpoints qua `EndpointRequest.toAnyEndpoint()`.
- Chain ưu tiên 2 xử lý API ứng dụng.
- Health/info có chính sách nhẹ theo nhu cầu.
- Env/configprops/metrics yêu cầu role OPS.
- Mọi endpoint còn lại bị deny theo mặc định.
- Không tắt CSRF trên toàn ứng dụng.

Với thực tế production, có thể dùng OIDC/JWT/mTLS hoặc một cơ chế auth được tổ chức phê duyệt thay cho Basic Auth thử nghiệm.

### 10.1. Lưu ý khi có management port riêng

Nếu Actuator chạy trên management port khác, cấu trúc context và đường routing có thể khác cấu hình cùng cổng. Hãy test trên **đúng topology mà production chạy**, đặc biệt khi áp dụng filter chains và ingress/network policies.

Trong lab bên dưới, HTTP app và management endpoints cùng ở **localhost:8089** để bảo đảm kiểm thử dễ tái lập. Phần tách management port được mô tả riêng ở mục 22.

## 11. Dự án thực hành: Actuator Diagnostic Guard

Ta xây một project gồm:

1. Một bean `@ConfigurationProperties` để có dữ liệu kiểm tra `/configprops`.
2. Một endpoint nghiệp vụ `GET /public-status` chỉ trả status không nhạy cảm.
3. Actuator với exposure tối thiểu trong cấu hình nền.
4. Profile `diagnostics` tạm expose `env`, `configprops`, `metrics`.
5. Spring Security yêu cầu role `OPS`.
6. `show-values=when-authorized` nhưng một số key vẫn masked bởi `SanitizingFunction`.
7. JUnit/MockMvc kiểm tra 200, 401, 403 và không rò dữ liệu giả.

Không dùng credential production. Mọi giá trị trong lab đều có thể thay bằng dữ liệu tự tạo không nhạy cảm.

### 11.1. Cấu trúc project

```text
actuator-diagnostic-guard/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
└── src/
    ├── main/
    │   ├── java/dev/example/actuator/
    │   │   ├── ActuatorGuardApplication.java
    │   │   ├── DiagnosticProperties.java
    │   │   ├── PublicStatusController.java
    │   │   ├── ActuatorSecurityConfiguration.java
    │   │   └── SanitizationConfiguration.java
    │   └── resources/
    │       ├── application.yaml
    │       └── application-diagnostics.yaml
    └── test/
        └── java/dev/example/actuator/
            └── ActuatorAccessTest.java
```

Tạo project bằng Spring Initializr với Gradle, Java 21, Spring Boot 3.3.x, các dependency Web, Actuator, Security và Test. Dùng Gradle Wrapper do project tạo ra.

### 11.2. `settings.gradle`

```groovy
rootProject.name = 'actuator-diagnostic-guard'
```

### 11.3. `build.gradle`

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'dev.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Không có Spring Cloud ở lab này. Các thuộc tính `management.endpoint.env.show-values` và cơ chế `SanitizingFunction` là tính năng Spring Boot Actuator, không yêu cầu Config Server hoặc `@RefreshScope`.

### 11.4. Main class

`src/main/java/dev/example/actuator/ActuatorGuardApplication.java`:

```java
package dev.example.actuator;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class ActuatorGuardApplication {

    public static void main(String[] args) {
        SpringApplication.run(ActuatorGuardApplication.class, args);
    }
}
```

`@ConfigurationPropertiesScan` đăng ký record cấu hình để Spring Boot Binder quản lý. Nó không liên quan đến việc expose Actuator endpoints.

### 11.5. Configuration record

`src/main/java/dev/example/actuator/DiagnosticProperties.java`:

```java
package dev.example.actuator;

import java.net.URI;
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "diagnostics")
public record DiagnosticProperties(
        String mode,
        URI upstream,
        Duration timeout,
        String apiKey
) {}
```

Đây là record immutable. Nó nhận các property như:

```text
diagnostics.mode
diagnostics.upstream
diagnostics.timeout
diagnostics.api-key
```

Với lab, `apiKey` chỉ là một marker giả. Trong project thật, không nên log record này bằng `toString()`, vì record mặc định có thể đưa `apiKey` vào chuỗi. Với secret thật, dùng loại dữ liệu/secret-handling thích hợp và tránh mọi serialization/logging không cần thiết.

### 11.6. API trạng thái chỉ trả allowlist

`src/main/java/dev/example/actuator/PublicStatusController.java`:

```java
package dev.example.actuator;

import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PublicStatusController {

    private final DiagnosticProperties settings;

    public PublicStatusController(DiagnosticProperties settings) {
        this.settings = settings;
    }

    @GetMapping("/public-status")
    public Map<String, Object> status() {
        return Map.of(
                "status", "ok",
                "mode", settings.mode(),
                "timeoutMs", settings.timeout().toMillis());
    }
}
```

Endpoint cố ý **không** trả `settings.apiKey()` hoặc toàn bộ record. Đây là mô hình diagnostic-safe response: **chỉ đưa ra fields được cho phép**, không serialize một object cấu hình lớn rồi cố loại secret về sau.

Đối với production, ngay cả `mode` hoặc `timeout` cũng cần được xem có phù hợp công khai hay không; lab sử dụng dữ liệu giả và localhost.

## 12. Cấu hình nền: hạn chế Actuator ngay từ đầu

`src/main/resources/application.yaml`:

```yaml
server:
  address: 127.0.0.1
  port: 8089

diagnostics:
  mode: "training"
  upstream: "https://example.test"
  timeout: 750ms
  api-key: "${LAB_API_KEY:LAB_ONLY_NOT_A_SECRET}"

management:
  endpoints:
    web:
      exposure:
        include: "health,info"
      discovery:
        enabled: false
    jmx:
      exposure:
        exclude: "*"

  endpoint:
    health:
      show-details: never
    env:
      show-values: never
    configprops:
      show-values: never
```

Điểm cần ghi nhớ:

- Process chỉ listen ở `127.0.0.1` vì đây là lab local.
- Chỉ health/info được expose mặc định trong bài.
- Không expose JMX endpoints.
- Không cho xem raw values từ `env` và `configprops` trong profile nền.
- `LAB_API_KEY` có placeholder default là chuỗi **giả, không phải token thật**. Không dùng secret mặc định trong production.
- Bỏ discovery page để giảm chi tiết danh mục endpoint được quảng bá, nhưng điều này **không phải một firewall**.

Một cách khác để thu hẹp thêm là disable hẳn `env`/`configprops` khi không dùng:

```yaml
management:
  endpoint:
    env:
      enabled: false
    configprops:
      enabled: false
```

Nếu đã disable, một profile mở exposure thôi chưa đủ để endpoint hoạt động; phải enable lại theo mục đích. Trong lab, giữ chúng enabled nhưng chưa exposed trong cấu hình nền để dễ chuyển sang profile diagnostics.

### 12.1. Vì sao không đặt `management.endpoints.web.exposure.include: "*"`?

Vì nó có thể expose `beans`, `mappings`, `threaddump`, `loggers` hoặc những endpoint khác mà bạn chưa đánh giá. Nếu một dependency mới thêm endpoint mới, một wildcard có thể thay đổi bề mặt tấn công mà không có một lần review danh sách endpoint.

Với operational endpoints, **allowlist rõ ràng** dễ đọc, dễ test và dễ kiểm soát hơn denylist dài.

## 13. Profile chẩn đoán tạm thời

`src/main/resources/application-diagnostics.yaml`:

```yaml
spring:
  security:
    user:
      name: ops
      password: "${OPS_PASSWORD}"
      roles: OPS

management:
  endpoints:
    web:
      exposure:
        include: "health,info,metrics,env,configprops"

  endpoint:
    env:
      show-values: when-authorized
      roles: "OPS"
    configprops:
      show-values: when-authorized
      roles: "OPS"
```

Ý nghĩa:

- Các endpoint nhạy cảm chỉ được expose khi profile `diagnostics` được bật.
- User lab `ops` có role `OPS`. `OPS_PASSWORD` phải được đưa vào process từ biến môi trường, không commit password thật vào YAML.
- Dù request đã qua HTTP authorization, thuộc tính `roles` của `show-values` vẫn bảo đảm chính sách hiển thị theo role.
- Custom `SanitizingFunction` sẽ tiếp tục che các key cụ thể dù request đã được authorized.
- Profile `diagnostics` không nên được bật vĩnh viễn ở production. Nếu cần chẩn đoán production, áp dụng một thay đổi có phê duyệt, timebox, audit và rollback.

Trong project có identity provider hoặc RBAC tập trung, cấu hình user/password bằng property chỉ là demo. Production nên dùng cơ chế xác thực được tổ chức quản lý.

### 13.1. Dùng `when-authorized` nhưng quên `roles` có rủi ro gì?

Theo Spring Boot 3.3, nếu không đặt danh sách roles, mọi HTTP user đã authenticated có thể được xem là authorized với mục đích hiển thị giá trị.

Vì vậy, điều này quá rộng nếu nhiều người có tài khoản login:

```yaml
management:
  endpoint:
    env:
      show-values: when-authorized
```

Hãy thêm role cụ thể và vẫn kiểm soát endpoint access ở Spring Security.

## 14. Spring Security cho Actuator và API ứng dụng

Tạo `src/main/java/dev/example/actuator/ActuatorSecurityConfiguration.java`:

```java
package dev.example.actuator;

import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
public class ActuatorSecurityConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain actuatorSecurity(HttpSecurity http)
            throws Exception {

        http.securityMatcher(EndpointRequest.toAnyEndpoint())
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(
                                EndpointRequest.to("health", "info"))
                        .permitAll()
                        .requestMatchers(
                                EndpointRequest.to(
                                        "metrics", "env", "configprops"))
                        .hasRole("OPS")
                        .anyRequest()
                        .denyAll())
                .httpBasic(Customizer.withDefaults());

        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain applicationSecurity(HttpSecurity http)
            throws Exception {

        http.authorizeHttpRequests(auth -> auth
                        .requestMatchers("/public-status")
                        .permitAll()
                        .anyRequest()
                        .denyAll())
                .httpBasic(Customizer.withDefaults());

        return http.build();
    }
}
```

Phân tích:

1. `@Order(1)` cho Actuator chain ưu tiên trước.
2. `EndpointRequest.toAnyEndpoint()` khớp endpoint HTTP Actuator theo cơ chế Spring Boot, không chỉ là chuỗi path tùy tiện.
3. Health/info được phép đọc mà không auth trong lab local.
4. Env/configprops/metrics yêu cầu Spring Security role OPS.
5. Những Actuator endpoints còn lại bị `denyAll()`.
6. Chain ứng dụng tách riêng, chỉ cho `GET`/request tới `/public-status` theo matcher demo, các URL khác bị deny.
7. Không tắt CSRF globally. Lab chỉ thao tác GET.
8. `httpBasic` dùng để demo; trên mạng thật nên kết hợp TLS/mTLS/SSO và network restrictions. **Không dùng Basic Auth qua HTTP không mã hóa trên mạng công cộng.**

### 14.1. Khi thêm custom chain, Boot auto-security nhường quyền

Nếu chỉ định nghĩa chain đầu mà không có một chain tổng quát cho phần còn lại, các API nghiệp vụ khác có thể không được bảo vệ theo cách bạn nghĩ. Spring Boot documentation nhấn mạnh rằng khi bạn tự có `SecurityFilterChain`, auto-configuration bảo mật tương ứng không còn áp dụng nguyên vẹn cho toàn ứng dụng.

Bởi vậy, ví dụ có **hai chains**, dù ứng dụng demo chỉ có một API nghiệp vụ. Trong sản phẩm thật, chain thứ hai phải thay bằng policy auth của ứng dụng, không giữ `denyAll()` nếu ứng dụng cần phục vụ thêm API hợp lệ.

### 14.2. `EndpointRequest` tốt hơn hardcode path trong nhiều tình huống

Mặc định endpoint URL là:

```text
/actuator/{id}
```

nhưng base path có thể đổi bằng:

```properties
management.endpoints.web.base-path=/manage
```

Với management port riêng, context path còn có thể khác. `EndpointRequest` được thiết kế để match các endpoint Actuator đúng với configuration và cả subpaths liên quan, giảm phụ thuộc vào một chuỗi URL hardcoded.

Điều đó không thay thế network policy hay rule cho API ngoài Actuator.

### 14.3. Tránh CSRF “fix” rộng

Nếu sau này bạn muốn chỉnh log level qua endpoint `loggers`, các request POST có thể bị CSRF protection chặn trong cấu hình mặc định. Không nên lập tức viết:

```java
// Đừng copy cấu hình tắt CSRF cho toàn hệ thống:
http.csrf(csrf -> csrf.disable());
```

Chỉ cân nhắc ngoại lệ CSRF cho một endpoint quản trị **rõ ràng dành cho non-browser clients**, có auth mạnh, authorization hẹp, network isolation và test. Với các đường cookie/session từ browser, CSRF là biện pháp bảo vệ quan trọng.

## 15. Đăng ký custom sanitization

Sử dụng class `SanitizationConfiguration` ở mục 8. Trong demo, `api-key` có giá trị giả nhưng vẫn bị che.

Ví dụ khi user OPS gọi:

```text
GET /actuator/env/diagnostics.api-key
```

response có thể có cấu trúc tương tự:

```json
{
  "property": {
    "source": "...",
    "value": "******"
  }
}
```

Đoạn trên chỉ minh họa trường `value` bị masked; cấu trúc đầy đủ còn phụ thuộc endpoint, nguồn và version.

Đồng thời một property không nhạy cảm như `diagnostics.timeout` có thể hiển thị cho OPS khi `show-values: when-authorized`, miễn không có custom sanitizer nào che nó.

**Quan trọng:** Không cần cố truy cập raw `api-key` để “chứng minh sanitizer”. Có thể kiểm tra response **không chứa marker thử nghiệm** là đủ.

## 16. Chạy project ở chế độ mặc định

Từ thư mục project:

macOS/Linux:

```bash
./gradlew bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Kiểm tra:

```bash
curl -i http://127.0.0.1:8089/actuator/health
curl -i http://127.0.0.1:8089/public-status
curl -i http://127.0.0.1:8089/actuator/env
```

Kỳ vọng:

- `/actuator/health` có thể trả `200` và status tổng quát.
- `/public-status` trả một tập thông tin nhỏ đã được allowlist.
- `/actuator/env` **không được expose trong profile nền**; không có endpoint dữ liệu chẩn đoán khả dụng.
- `/actuator/heapdump`, `/actuator/logfile`, `/actuator/mappings` không được expose chỉ vì Actuator dependency tồn tại.

Status code cụ thể của đường không exposed có thể phụ thuộc vào security filter chain và routing (ví dụ `403` hoặc `404`), nhưng điều quan trọng là **không trả dữ liệu endpoint**. Trong integration test, hãy kiểm tra cả chính sách HTTP và exposure.

### 16.1. Health details khác việc endpoint health reachable

Ví dụ:

```yaml
management:
  endpoint:
    health:
      show-details: never
```

Health có thể công khai trạng thái `UP` mà không hiển thị chi tiết từng datasource, disk, broker hoặc dependency.

Nếu cần chi tiết cho OPS, có thể cân nhắc `show-details: when-authorized` và roles phù hợp, đồng thời bảo vệ đường access. Đừng giả định một public health response luôn chỉ có một field nếu app đã tùy biến details.

## 17. Bật profile diagnostics trong local

Dừng app rồi bật profile `diagnostics` với một mật khẩu **tự tạo chỉ dùng local**, không copy credential thật.

Bash:

```bash
export OPS_PASSWORD='local-training-password'
./gradlew bootRun --args='--spring.profiles.active=diagnostics'
unset OPS_PASSWORD
```

PowerShell:

```powershell
$env:OPS_PASSWORD = 'local-training-password'
.\gradlew.bat bootRun --args="--spring.profiles.active=diagnostics"
Remove-Item Env:OPS_PASSWORD
```

Lưu ý: password trong ví dụ là **placeholder huấn luyện**, không phải password vận hành. Giá trị này không được dùng ngoài localhost. Với production, dùng identity provider hoặc secrets source riêng được quản trị.

Mở terminal khác, gọi không auth:

```bash
curl -i http://127.0.0.1:8089/actuator/env
```

Kỳ vọng: `401 Unauthorized` theo chain lab.

Với curl, có thể dùng:

```bash
curl -i -u ops http://127.0.0.1:8089/actuator/env
```

`curl -u ops` sẽ hỏi password, tránh đưa password thẳng vào command line. Nhập mật khẩu lab đã thiết lập ở terminal của app. Nếu auth thành công và role OPS đúng, request có thể trả `200` cùng dữ liệu được phép.

Kiểm tra một key:

```bash
curl -i -u ops \
  http://127.0.0.1:8089/actuator/env/diagnostics.api-key
```

Kỳ vọng giá trị của key nhạy cảm vẫn `******` nhờ custom `SanitizingFunction`.

### 17.1. Không chụp toàn bộ response khi đang xử lý sự cố thật

Trong production, response `/actuator/env` có thể chứa danh sách nhiều nguồn và nhiều key. Đừng đưa toàn bộ vào chat, ticket hoặc log để nhờ debug. Hãy mô tả vấn đề bằng:

```text
Property name: payments.gateway.timeout
Source category: environment / Config Data
Was present: true
Was bindable: true
Expected unit/type: Duration
```

Không kèm secret values hoặc object config chứa credentials.

## 18. Test quyền truy cập bằng MockMvc

Tạo `src/test/java/dev/example/actuator/ActuatorAccessTest.java`:

```java
package dev.example.actuator;

import static org.hamcrest.Matchers.not;
import static org.hamcrest.Matchers.containsString;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest(properties = {
        "spring.security.user.password=test-password-only",
        "diagnostics.api-key=test-credential-only"
})
@ActiveProfiles("diagnostics")
@AutoConfigureMockMvc
class ActuatorAccessTest {

    @Autowired
    MockMvc mvc;

    @Test
    void anonymousCanReadMinimalHealth() throws Exception {
        mvc.perform(get("/actuator/health"))
                .andExpect(status().isOk())
                .andExpect(content().string(
                        not(containsString("test-credential-only"))));
    }

    @Test
    void anonymousCannotReadEnvironment() throws Exception {
        mvc.perform(get("/actuator/env"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void viewerCannotReadEnvironment() throws Exception {
        mvc.perform(get("/actuator/env")
                        .with(user("viewer").roles("VIEWER")))
                .andExpect(status().isForbidden());
    }

    @Test
    void opsCanReadButSensitiveValueIsStillMasked()
            throws Exception {
        mvc.perform(get("/actuator/env/diagnostics.api-key")
                        .with(httpBasic(
                                "ops", "test-password-only")))
                .andExpect(status().isOk())
                .andExpect(content().string(
                        not(containsString("test-credential-only"))));
    }

    @Test
    void opsCanReadConfigpropsWithoutLeakingTestCredential()
            throws Exception {
        mvc.perform(get("/actuator/configprops")
                        .with(httpBasic(
                                "ops", "test-password-only")))
                .andExpect(status().isOk())
                .andExpect(content().string(
                        not(containsString("test-credential-only"))));
    }
}
```

Trong đây:

- `spring-security-test` tạo request giả có user/role hoặc HTTP Basic credentials.
- `@ActiveProfiles("diagnostics")` chỉ expose các endpoint cần cho lab.
- Test không cần Vault token, không cần database hoặc mạng công khai.
- Hai test sử dụng `not(containsString(...))` để kiểm tra credential giả **không xuất hiện** trong response của hai endpoint.
- `401` và `403` chứng minh authentication và authorization là hai quyết định khác nhau.
- Test `200` không tự chứng minh dữ liệu an toàn; phải kiểm tra masking.

Chạy:

macOS/Linux:

```bash
./gradlew test
```

Windows:

```powershell
.\gradlew.bat test
```

### 18.1. Kiểm thử role OPS với `when-authorized`

Một test thêm có thể gọi endpoint chứa property không nhạy cảm:

```text
diagnostics.mode=training
```

và kiểm tra OPS thấy `training` khi `show-values=when-authorized`, còn một user không thuộc OPS không được xem endpoint.

Nếu team cho phép VIEWER vào endpoint nhưng chỉ OPS xem raw values, hãy kiểm tra phần values của VIEWER được masked. Tuy nhiên, thiết kế đó chỉ nên dùng khi metadata của endpoint được đánh giá là không nhạy cảm với VIEWER.

### 18.2. Test không expose endpoint không mong đợi

Bổ sung test cho các đường:

```text
/actuator/heapdump
/actuator/logfile
/actuator/beans
/actuator/mappings
/actuator/shutdown
```

Trong profile lab, chúng **không được trả nội dung chức năng của endpoint**. Do có nhiều filter chains, không nên cố chốt mọi đường thiếu endpoint đều phải `404`; thay vào đó, xác nhận không có một response dữ liệu thành công, và kiểm tra exposure configuration riêng.

### 18.3. Test sản phẩm phải kiểm tra cả topology

MockMvc không mô phỏng đầy đủ firewall, ingress, Kubernetes NetworkPolicy hay TLS. Với production, cần thêm integration/smoke tests từ hai network zones: caller được phép vào management endpoint và caller không được phép.

Đừng kết luận rằng unit test role đã chứng minh một management port đang bị chặn từ Internet.

## 19. Đánh giá `show-values=always` bằng risk assessment

Một tình huống vận hành hay gặp:

> “Đội trực cần tìm giá trị thật của property X, cứ bật `always` trong 15 phút được không?”

Trước khi quyết định, cân nhắc:

1. Property X có chứa credential, token, private key, PII hay endpoint nội bộ không?
2. Có thể suy ra vấn đề bằng key/source mà không thấy raw value không?
3. Có thể viết một diagnostic endpoint chỉ trả kết quả so sánh, không tiết lộ giá trị không?
4. Có thể truy cập một instance qua VPN/kubectl port-forward thay vì expose ingress không?
5. Có thể dùng `when-authorized` và role chuyên biệt không?
6. Có custom sanitizer và kiểm thử đảm bảo một số keys luôn masked không?
7. Có proxy/access log hoặc tracing sẽ ghi response không?
8. Có thời hạn, audit và một owner chịu trách nhiệm tắt endpoint sau xử lý không?

Thường câu trả lời hợp lý không phải bật `always`. Một endpoint “check” có thể chỉ trả:

```json
{
  "property": "payments.gateway.timeout",
  "present": true,
  "parsed": true,
  "withinExpectedRange": true
}
```

Cách đó đủ chẩn đoán nhiều lỗi mà không công bố raw value.

## 20. Các tình huống chẩn đoán cấu hình

### 20.1. Ứng dụng không đọc được biến môi trường

Mục tiêu: biết `PAYMENTS_RETRY_TIMEOUT` đã vào process chưa và Binder có dùng đúng key `payments.retry.timeout` không.

Cách tiếp cận:

1. Kiểm tra cấu hình deployment đã truyền env var chưa.
2. Kiểm tra tên biến và relaxed binding.
3. Nếu cần, dùng endpoint chỉ cho OPS xác nhận tên property có xuất hiện trong Environment không.
4. Dùng `/configprops` đã masked để biết bean cấu hình tương ứng có tồn tại.
5. Không in tất cả env vars và không mở `/env` công khai.

Nếu property không nhạy cảm và bắt buộc xem value, chỉ dùng chính sách hiển thị có giới hạn; đừng dùng một thiết lập `always` cho toàn endpoint.

### 20.2. Profile nhầm làm service gọi nhầm backend

Mục tiêu: biết active profile và nguồn cấu hình nào đang áp dụng.

Chọn cách ít dữ liệu nhất:

```java
environment.getActiveProfiles()
```

hoặc một endpoint chẩn đoán nội bộ chỉ trả tên profile đã được duyệt. Không bắt buộc phải dump toàn bộ property sources có thể chứa secrets.

### 20.3. `@ConfigurationProperties` có dữ liệu sai

Mục tiêu: phân biệt lỗi property missing với type conversion.

Hướng debug:

- Kiểm tra prefix/root registration.
- Kiểm tra tên canonical và profile/precedence.
- Kiểm tra conversion/validation error lúc startup.
- Với app đã chạy, đối chiếu thông tin masked từ `/env` và `/configprops`.
- Không chuyển `show-values` sang `always` chỉ để in chuỗi có thể nhạy cảm.

### 20.4. Một bean không tồn tại vì auto-configuration condition

`/actuator/conditions` giúp biết auto-configuration nào match/mismatch. Nó có thể lộ class names, dependency và cấu trúc runtime. Nếu cần, expose tạm qua OPS, không đưa ra public ingress.

### 20.5. Log quá ít để xác định lỗi

`/actuator/loggers` có thể cho phép thay log level runtime khi được expose và authorize đúng. Rủi ro là việc tăng DEBUG cho package chứa HTTP clients hay authentication có thể khiến secret hoặc request data đi vào log.

Trước khi tăng log level:

- Chỉ chọn package/class cần thiết.
- Đặt thời hạn và kế hoạch revert.
- Hạn chế thao tác bằng role riêng.
- Không tắt CSRF rộng để tiện POST.
- Kiểm soát volume và retention log.
- Kiểm tra thư viện có log request headers/body không.

### 20.6. Cần heap dump để điều tra leak

`heapdump` có thể chứa dữ liệu ở bộ nhớ, bao gồm credentials và nội dung request. Không xem “chỉ là file debug” là lý do cho phép tải qua HTTP công khai.

Một quy trình an toàn hơn: lấy dump qua cơ chế admin của máy/container được phép, lưu vào kho riêng với thời hạn retention, encrypt at rest và hạn chế người truy cập. Không tải dump về máy cá nhân không được quản lý hoặc đính kèm ticket công khai.

## 21. Health endpoint: tối thiểu cho probe, chi tiết cho nội bộ

Health thường là endpoint duy nhất mà load balancer/orchestrator cần đọc liên tục. Nhưng nội dung **status** và **details** cần có policy riêng.

Cấu hình public tối giản:

```yaml
management:
  endpoint:
    health:
      show-details: never
```

Khi cần chi tiết cho vai trò quản trị:

```yaml
management:
  endpoint:
    health:
      show-details: when-authorized
      roles: "OPS"
```

Tuy nhiên, nếu security filter chain cho anonymous truy cập `/actuator/health`, người không authenticated chỉ thấy dữ liệu theo chính sách `show-details`; role OPS mới có thể nhận phần chi tiết. Hãy kiểm tra response thực tế của version đang dùng, vì health groups và components còn có các thuộc tính riêng.

Một application public có thể expose `health` cho probe, nhưng không nên vô thức expose:

- Database connection URL.
- Message broker endpoint.
- Nội dung exception chứa secret.
- Internal host inventory.
- Tên service backend mà public caller không cần biết.

### 21.1. Health groups và Kubernetes probes

Spring Boot Actuator có thể hỗ trợ health groups như `liveness` và `readiness`, phù hợp với Kubernetes probes khi được bật/cấu hình. Những endpoint này phục vụ điều phối traffic, không nhất thiết phải trả toàn bộ details.

Nếu dùng separate management port, cần cân nhắc các probes có kiểm tra được đường xử lý chính hay chỉ management context, và liệu port chính còn sẵn sàng thật không. Một management server healthy không tự chứng minh main HTTP application đang nhận được request ở port nghiệp vụ.

## 22. Management port và address: giảm bề mặt mạng

Spring Boot cho phép dùng port riêng:

```yaml
server:
  port: 8080

management:
  server:
    port: 8081
```

Với một lab chạy hoàn toàn local:

```yaml
management:
  server:
    port: 8081
    address: 127.0.0.1
```

Theo tài liệu Spring Boot, `management.server.address` chỉ có thể đặt một bind address khác khi management server dùng **port khác** server chính.

Ưu điểm của port riêng:

- Dễ áp dụng firewall hoặc NetworkPolicy chỉ mở port quản trị cho caller được phép.
- Có thể route monitoring traffic và business traffic qua mạng khác.
- Có thể cấu hình TLS riêng hoặc bảo vệ thêm bằng mTLS/gateway.
- Có thể giới hạn số hệ thống được scrape metrics.

Nhưng **port riêng không phải cơ chế authentication**. Nếu port đó reachable từ một mạng không tin cậy, Actuator vẫn cần được bảo vệ đúng. Không xem `management.server.port=8081` là tương đương với “nội bộ”.

### 22.1. Kubernetes: không mặc định dùng loopback cho một endpoint cần scrape

Bind management server vào `127.0.0.1` trong pod có thể khiến Prometheus hoặc kubelet từ bên ngoài network namespace không kết nối được theo topology của bạn.

Trước khi áp dụng:

- Xác định probe/scraper chạy ở đâu.
- Xác định Service hoặc ingress có expose management port không.
- Dùng NetworkPolicy để giới hạn source được phép.
- Nếu cần quyền theo role, cấu hình authentication phù hợp.
- Không công khai port qua một public LoadBalancer chỉ để monitoring tiện hơn.
- Kiểm tra thực tế từ pod hoặc monitoring namespace.

### 22.2. Thay base path không bảo vệ endpoint

Ví dụ:

```yaml
management:
  endpoints:
    web:
      base-path: "/internal-management"
```

đổi URL nhưng không phải một lớp authorization. Security by obscurity không đủ; cần exposure allowlist, network isolation và authentication.

### 22.3. Tắt HTTP management khi không cần

Có thể dùng:

```properties
management.server.port=-1
```

hoặc:

```yaml
management:
  endpoints:
    web:
      exposure:
        exclude: "*"
```

Tuy nhiên, việc tắt HTTP management không nhất thiết tắt JMX transport. Kiểm tra cả hai nếu policy yêu cầu không có kênh quản trị từ xa.

## 23. Phân quyền theo môi trường: một ma trận gợi ý

| Môi trường | Health | Info/Metrics | Env/Configprops | Heap/Logfile | Show values |
| --- | --- | --- | --- | --- | --- |
| Local dev | Health cho local | Có thể mở để học | Có thể bật tạm với test role | Chỉ khi thật cần | `never` hoặc `when-authorized` cho lab |
| CI tests | Health + test probes | Theo test | Chỉ trong test profile | Thường tắt | Kiểm tra masking |
| Staging | Health cho platform | Monitoring role | OPS trong mạng nội bộ | Qua workflow phê duyệt | Mặc định `never` |
| Production | Health/readiness tối thiểu | Scraper/OPS có quyền | Tắt hoặc tạm mở có phê duyệt | Không expose thường trực | `never` theo baseline |

Đây là gợi ý chính sách, không phải một cấu hình bắt buộc. Một doanh nghiệp có hệ thống mTLS/SSO/management network riêng có thể dùng cách cấp quyền khác, nhưng nguyên tắc **least privilege và data minimization** vẫn áp dụng.

### 23.1. Quy tắc tạm mở endpoint trong sự cố

Một runbook có thể yêu cầu:

1. Ticket/incident ID.
2. Người phê duyệt và phạm vi endpoint cần mở.
3. Nhóm host/pod đích và network source được phép.
4. Vai trò/credential có TTL ngắn.
5. Các keys được phép quan sát và các keys bắt buộc masked.
6. Thời gian bắt đầu/kết thúc.
7. Audit trail của request hoặc thay đổi cấu hình.
8. Thao tác đóng exposure/role sau khi kết thúc.
9. Kiểm tra không còn đường truy cập nhạy cảm.
10. Dọn dữ liệu chẩn đoán khỏi nơi lưu không phù hợp.

Một endpoint tạm thời cần có **cách đóng lại đã được lên kế hoạch ngay lúc mở**.

## 24. Cảnh báo về `info` và metadata build/Git

Một ứng dụng có thể công bố build info hoặc Git info qua `/actuator/info` khi cấu hình tương ứng. Các thông tin như version hoặc commit ID có thể hữu ích cho vận hành, nhưng cũng có thể là metadata nội bộ.

Không đưa:

```text
internal.repo.url
employee.email
deployment.secret
private.scm.token
```

vào `info` tùy tiện. Nếu public client chỉ cần biết version, tạo một allowlist nhỏ gồm fields được phép và tránh công khai nhiều provenance.

`info` không có cùng chính sách `show-values` của `env`; đừng nghĩ thiết lập `management.endpoint.env.show-values=never` tự bảo vệ mọi trường do bạn đưa vào info contributor.

## 25. `metrics` và `prometheus`: giá trị đo không mặc định vô hại

Metrics thường không chứa plaintext passwords, nhưng tag/label không được kiểm soát có thể chứa:

- Customer ID hoặc path có PII.
- Raw URL với query string.
- Token nếu ứng dụng tạo tag từ Authorization header.
- Tên tenant, region, service nội bộ.
- Username, host hoặc resource labels nhạy cảm.

Vì vậy:

- Chỉ expose metrics cho scraper có quyền.
- Kiểm soát metric tag cardinality và nội dung label.
- Tránh đưa input người dùng hoặc secret làm tag.
- Đặt network policy cho monitoring.
- Kiểm thử sample exposition thực tế.
- Không mặc định thêm `prometheus` vào public ingress.

`show-values` của `/env` không có tác dụng làm mờ những label do code metrics tạo ra.

## 26. Chẩn đoán không đồng nghĩa thu thập toàn bộ dữ liệu

Một cách thực hành tốt là tạo diagnostic report **dạng cho phép**:

```json
{
  "application": "payment-service",
  "environment": "production",
  "activeProfileCount": 1,
  "requiredKeyPresent": true,
  "requiredKeyConverted": true,
  "configRevision": "r42",
  "readiness": "UP"
}
```

Không cần trả:

```json
{
  "dbPassword": "plaintext",
  "vaultToken": "plaintext",
  "allEnvironmentVariables": "..."
}
```

Với trường config quan trọng, thay vì in raw value, có thể kiểm tra:

- Present/absent.
- Đúng kiểu khi bind.
- Nằm trong một khoảng an toàn.
- Nguồn thuộc nhóm được cho phép.
- Revision hiện tại.
- Đã kết nối được dependency chưa.
- Giá trị có tương thích với một hợp đồng đã công bố không.

Nếu có `configRevision`, không đưa hash thô của secret hoặc dữ liệu có entropy thấp theo cách có thể bị brute-force. Dùng định danh revision được quản lý như Git commit/config version đã duyệt, không phải fingerprint tiết lộ giá trị nhạy cảm.

## 27. Cách xử lý một lần rò rỉ Actuator

Nếu phát hiện `/actuator/env` hoặc `/actuator/heapdump` đã bị mở công khai:

1. Xác định endpoint, URL, thời gian, nguồn truy cập và exposure hiện tại.
2. **Chặn đường truy cập** bằng mạng/ingress và cấu hình exposure, bảo đảm không phá mất tuyến health cần thiết.
3. Kiểm tra logs/audit theo cách không làm lan truyền dữ liệu.
4. Đánh giá dữ liệu nào có thể lộ: tên key, property values, memory snapshot, log file, mapping information.
5. Nếu có secret có khả năng bị lộ, áp dụng chính sách incident response và rotation/revocation được phê duyệt.
6. Kiểm tra các endpoint khác (`configprops`, `logfile`, `heapdump`, custom endpoints).
7. Thêm regression test đảm bảo đường nguy hiểm không công khai lại.
8. Rà soát ingress, firewall, ACL, RBAC, security chains, monitoring exporters và log sinks.
9. Ghi lại postmortem tập trung vào nguyên nhân và lớp kiểm soát thiếu.

Chỉ đổi `show-values` từ `always` về `never` **không đủ** nếu trước đó dump đã bị truy cập hoặc endpoint khác vẫn còn mở.

## 28. Những lỗi cấu hình thường gặp

### 28.1. `404` khi gọi `/actuator/env`

Có thể do:

- Chưa thêm `spring-boot-starter-actuator`.
- Endpoint không được expose qua HTTP.
- Endpoint bị `enabled=false`.
- Base path không còn là `/actuator`.
- Đang gọi sai port.
- Gateway/ingress không route đường quản trị.
- Security chain/gateway đang cố tình ẩn hoặc chặn route.

Cách xử lý: kiểm tra dependency, `management.endpoints.web.exposure.include`, `management.endpoint.env.enabled`, management port/base path và security rules. Không bật wildcard chỉ để thử.

### 28.2. `401` khi endpoint đã exposed

Đó có thể là đúng policy: request chưa authenticated. Dùng danh tính OPS được cấp trong môi trường phù hợp; không tắt security để loại bỏ 401.

### 28.3. `403` với user đã đăng nhập

Kiểm tra:

- User có authority/role đúng (`ROLE_OPS`) không?
- `hasRole("OPS")` có khớp với principal không?
- Có custom filter chain nào được chọn khác dự kiến không?
- Endpoint có yêu cầu HTTP method khác GET và bị CSRF chặn không?
- Gateway/ingress có ACL khác không?

Với POST admin, `403` có thể do CSRF chứ không chỉ role. Không mặc định tắt CSRF toàn bộ.

### 28.4. Authorized rồi nhưng giá trị vẫn là `******`

Nếu:

```properties
management.endpoint.env.show-values=never
```

thì đây là hành vi mong đợi, dù OPS có quyền. Nếu dùng `when-authorized`, kiểm tra `roles` của endpoint, principal và custom `SanitizingFunction` có áp dụng không.

**Mục tiêu không phải “bằng mọi giá xem raw secret”**. Nếu một key thuộc danh sách phải luôn che, sanitizer đang làm đúng.

### 28.5. `when-authorized` nhưng mọi user login đều thấy giá trị

Kiểm tra có đặt:

```properties
management.endpoint.env.roles=OPS
```

hay không. Khi thiếu roles, quy tắc mặc định có thể coi bất kỳ HTTP user đã authenticated là authorized. Đồng thời kiểm tra endpoint HTTP access policy và custom security chain.

### 28.6. Không thấy dữ liệu mới khi thay `application.yaml`

Actuator chẩn đoán những giá trị/bean trong **process hiện tại**. Spring Boot core không mặc định watch file ngoài JAR và rebind mọi bean. Nếu thay Config Data rồi không restart/refresh theo cơ chế hỗ trợ, process có thể vẫn giữ snapshot cũ.

Đừng nhầm “endpoint đang che value” với “value vẫn cũ”. Tách câu hỏi loading, precedence, binding và sanitization.

### 28.7. Endpoint quản trị có thể truy cập ngoài VPN

Kiểm tra network exposure, ingress routes, Service type, port binding, firewall và NetworkPolicy. Spring Security vẫn nên có, nhưng một lỗi mạng không nên khiến endpoint nhạy cảm trở thành public target.

### 28.8. `/actuator/configprops` có dữ liệu không khớp API business

Có thể service đã copy giá trị từ bean cấu hình khi khởi tạo; hoặc có nhiều beans, prefix, custom binding. `/configprops` phản ánh góc nhìn configuration properties, không kiểm tra mọi client/resource đã áp dụng giá trị.

### 28.9. `include: "*"` bất ngờ mở endpoint mới

Một dependency/framework version thêm endpoint và wildcard expose nó. Chuyển sang allowlist; thêm test exposure trong CI.

### 28.10. `management.server.address` không có tác dụng

Trong Spring Boot, muốn bind management endpoints vào address khác, cần management port **khác** main server port. Nếu cùng port, phải kiểm soát bind address ở server chính và mạng.

### 28.11. Chỉ tắt HTTP nhưng JMX vẫn mở

Web exposure và JMX exposure độc lập. Nếu policy không cho JMX, đặt `management.endpoints.jmx.exposure.exclude="*"` và kiểm tra JMX transport hạ tầng.

### 28.12. Heap dump tải về có dữ liệu bí mật

Masking `env/configprops` không làm biến mất dữ liệu từ heap. Hãy coi dump là một artifact nhạy cảm, xử lý qua secure diagnostics workflow.

## 29. Bảng câu hỏi xác định chính sách cho từng endpoint

Khi review một endpoint, hãy trả lời:

| Câu hỏi | Gợi ý cần ghi |
| --- | --- |
| Ai sử dụng? | Load balancer, Prometheus, SRE, on-call, developer |
| Cần HTTP hay JMX? | Chọn một hoặc cả hai với controls riêng |
| Bật thường xuyên hay tạm thời? | Baseline vs incident profile |
| Có chứa dữ liệu nhạy cảm? | Key names, raw values, hostnames, dumps, logs |
| Chỉ đọc hay có khả năng ghi? | GET vs POST/DELETE |
| Quyền nào? | Public health, METRICS, OPS, incident-admin |
| Tầng mạng nào? | Internal Service, VPN, port-forward, mTLS |
| Có sanitizer không? | `never`, roles, custom masking |
| Có audit không? | Ai gọi, lúc nào, incident ID |
| Có retention policy không? | Response/log/dump lưu ở đâu |
| Có test? | 200,401,403, fail-close, secrets absent |
| Khi đóng thì làm gì? | Revert exposure, rotate credentials nếu cần |

Một endpoint chỉ nên được phê duyệt khi có chủ sở hữu và một mục đích vận hành xác định.

## 30. Bài tập thực hành

### Bài A — Enabled, exposed hay authorized?

Cho:

```properties
management.endpoint.env.enabled=true
management.endpoints.web.exposure.include=health,info
```

Giải thích vì sao `/actuator/env` chưa được public HTTP, dù endpoint có thể enabled. Nếu thêm `env` vào include, cần những bước bảo vệ nào nữa?

### Bài B — `show-values` theo role

Một endpoint có:

```properties
management.endpoint.env.show-values=when-authorized
management.endpoint.env.roles=OPS
```

Hãy dự đoán dữ liệu trả cho anonymous, authenticated VIEWER và authenticated OPS trong hai cấu hình Spring Security: chỉ OPS được gọi endpoint và cả VIEWER/OPS được gọi endpoint.

### Bài C — Sanitizer luôn che secret

Dùng `SanitizingFunction` để che mọi key có chứa `"credential"` hoặc `"api-key"`. Viết test với giá trị giả và xác nhận response không chứa marker. Có phải sanitizer bảo vệ heap dump không? Tại sao?

### Bài D — Thêm custom SecurityFilterChain

Một ứng dụng vốn dựa vào Boot auto-security. Developer thêm một chain cho `/api/**`. Hãy giải thích vì sao cần kiểm tra lại Actuator rules và đề xuất cấu hình với `EndpointRequest.toAnyEndpoint()`.

### Bài E — Profiles cho chẩn đoán

Thiết kế `application.yaml` expose `health,info`; `application-diagnostics.yaml` expose thêm `env,configprops` nhưng yêu cầu OPS role. Viết lệnh bật profile local với password giả từ biến môi trường; mô tả quy trình tắt khi xong.

### Bài F — Kubernetes management port

Ứng dụng dùng port 8080 cho API và 8081 cho Actuator. Hãy mô tả Service/NetworkPolicy để Prometheus scrape metrics nhưng public ingress không truy cập được `/actuator/env`.

### Bài G — HTTP method và CSRF

Đội vận hành muốn thay logger level qua POST. Khi nhận `403`, những nguyên nhân nào cần kiểm tra ngoài sai role? Vì sao không nên tắt CSRF global?

### Bài H — Phân biệt `/env` và `/configprops`

`Environment` thấy property `demo.timeout`, nhưng bean `DemoProperties` vẫn dùng giá trị cũ. Hãy liệt kê những nguyên nhân: startup snapshot, wrong prefix, conversion, profile, bean recreation, custom lifecycle. Có cần xem raw secret để tìm nguyên nhân không?

### Bài I — Metadata leak khi value đã masked

Trong response `/env`, tất cả values đều `******` nhưng có tên `internal.db.backup-host` và đường file tuyệt đối. Tại sao response này vẫn cần role/network restriction?

### Bài J — Audit và timebox

Một incident cần mở `/actuator/conditions` trong 30 phút. Thiết kế checklist owner, phê duyệt, access scope, audit, kiểm thử và rollback. Không bật wildcard.

### Bài K — Review policy health

Mọi người được gọi `/actuator/health`, nhưng details chứa database hostname. Hãy đổi cấu hình để anonymous chỉ thấy status tổng quát, trong khi OPS có thể xem details theo quyền.

### Bài L — Khi nào không cần `/env`?

Nếu sự cố chỉ cần biết `retry.timeout` có parse được thành `Duration` và lớn hơn 0 hay không, hãy đề xuất một endpoint diagnostics theo allowlist trả boolean/đơn vị thống nhất mà không expose toàn bộ property sources.

## 31. Câu hỏi tự kiểm tra

**1.** Mặc định Spring Boot 3.3 expose endpoint nào qua HTTP?

**2.** Enablement khác exposure ở điểm nào?

**3.** Nếu app đã có custom `SecurityFilterChain`, có nên mặc định tin Boot auto-security vẫn bao phủ toàn bộ Actuator không?

**4.** `include` và `exclude` cái nào ưu tiên hơn?

**5.** Có nên dùng `include: "*"` trong production như một baseline lâu dài không?

**6.** Ba giá trị `show-values` là gì?

**7.** Giá trị mặc định `show-values` cho `env/configprops` của Boot 3.3 là gì?

**8.** Với `when-authorized` mà thiếu `roles`, một HTTP user đã authenticated có thể được xem là authorized không?

**9.** `SanitizingFunction` có tiếp tục che giá trị khi user OPS đủ quyền không?

**10.** `SanitizingFunction` có bảo vệ dữ liệu trong heap dump không?

**11.** JMX authorization có giống HTTP roles khi xét show-values không?

**12.** `EndpointRequest.toAnyEndpoint()` giúp điều gì?

**13.** `management.endpoints.web.base-path=/manage` có phải security boundary không?

**14.** Vì sao Actuator `health` public vẫn cần quan tâm details?

**15.** Vì sao `/actuator/metrics` cũng có thể có rủi ro dù không chứa password?

**16.** `401` và `403` khác nhau thế nào?

**17.** Một POST vào `/actuator/loggers` trả `403` có thể do CSRF không?

**18.** Chỉ đặt `management.server.port=8081` đã đủ bảo vệ mạng chưa?

**19.** Có thể đặt `management.server.address` khác khi management cùng port với main server không?

**20.** Vì sao không nên copy toàn bộ `/env` response vào public ticket?

**21.** Sửa YAML trên disk rồi `/env` vẫn thấy dữ liệu cũ có nhất thiết là lỗi Actuator không?

**22.** Một test 200 với OPS đã đủ chứng minh không lộ secret chưa?

### Gợi ý đáp án

1. `health` theo mặc định.
2. Enabled quyết định endpoint khả dụng; exposure quyết định công bố qua transport.
3. Không; custom chain khiến auto-configuration bảo mật tự động nhường quyền.
4. `exclude` ưu tiên hơn `include`.
5. Không; ưu tiên allowlist.
6. `never`, `when-authorized`, `always`.
7. `never`, values được masked.
8. Có; nên cấu hình roles cụ thể.
9. Có; custom sanitizer vẫn áp dụng.
10. Không; heap dump là loại dữ liệu khác.
11. Không; JMX được xem authorized cho chính sách show-values, cần bảo vệ JMX riêng.
12. Match các endpoint Actuator dựa trên metadata/config path, kể cả khi base path thay đổi.
13. Không; chỉ đổi URL.
14. Details có thể lộ dependency và topology nội bộ.
15. Tag/label/metric name có thể chứa dữ liệu nhạy cảm.
16. 401 thường là chưa xác thực, 403 là có danh tính nhưng không đủ quyền hoặc bị chặn bởi một policy khác.
17. Có.
18. Không; còn firewall, network policy và auth.
19. Chỉ hỗ trợ bind management address khác khi dùng port khác.
20. Vì có thể lộ keys, nguồn, host, cấu trúc, và đôi khi values tùy policy.
21. Không; Boot Config Data không tự watch file để rebind, xem lại lifecycle.
22. Không; còn phải kiểm tra masking, sensitive metadata và logs.

## 32. Checklist triển khai production

Trước khi mở một Actuator endpoint để chẩn đoán:

- [ ] Xác định endpoint nào thực sự cần.
- [ ] Dùng web allowlist, không expose wildcard mặc định.
- [ ] Kiểm tra endpoint enablement riêng với exposure.
- [ ] Kiểm tra JMX exposure nếu tổ chức có JMX transport.
- [ ] Xác định source networks có thể kết nối tới management port.
- [ ] Bảo vệ bằng Spring Security/SSO/mTLS phù hợp.
- [ ] Có role riêng cho OPS/incident diagnostics.
- [ ] Không dựa vào Boot auto-security khi đã có custom filter chains.
- [ ] Chỉ công khai health/info nếu dữ liệu thật sự an toàn.
- [ ] Không làm lộ health details tới anonymous nếu không cần.
- [ ] Giữ env/configprops `show-values=never` trong baseline.
- [ ] Nếu dùng `when-authorized`, cấu hình `roles` rõ.
- [ ] Không dùng `always` cho một sự cố bình thường.
- [ ] Đặt custom sanitizer cho keys nhạy cảm của domain.
- [ ] Xác nhận sanitizer không thay đổi giá trị config thật.
- [ ] Không dựa vào sanitizer để bảo vệ heapdump/logfile/traces.
- [ ] Không in secrets vào log hoặc API khác.
- [ ] Bảo vệ metrics tags khỏi PII/token.
- [ ] Nếu cần thay log levels, quản lý quyền và CSRF phù hợp.
- [ ] Có audit, phê duyệt và thời hạn khi mở diagnostic profile.
- [ ] Có test 401/403/200 theo role.
- [ ] Có test không xuất hiện token giả trong response.
- [ ] Có test endpoint không mong đợi không trả dữ liệu.
- [ ] Có smoke test qua đúng management port/ingress của production.
- [ ] Có NetworkPolicy/firewall và TLS theo topology.
- [ ] Có quy trình xử lý artifact chẩn đoán có thể chứa dữ liệu nhạy cảm.
- [ ] Có kế hoạch khôi phục exposure baseline sau incident.
- [ ] Có cơ chế rotation/revocation nếu phát hiện rò secret.
- [ ] Có owner cho mọi endpoint tùy biến.
- [ ] Ghi rõ version Spring Boot/Spring Security áp dụng khi nâng cấp.

## 33. Tổng kết

Chẩn đoán lỗi cấu hình cần trả lời **đúng câu hỏi với ít dữ liệu nhất**. Spring Boot Actuator cho công cụ quan sát mạnh, nhưng những endpoint như `/env` và `/configprops` có thể tiết lộ nhiều thông tin hơn mục tiêu điều tra.

Một chính sách có thể nhớ bằng sơ đồ:

```text
Need to diagnose?
       |
       v
Select only required endpoint
       |
       v
Enable/expose intentionally
       |
       v
Restrict management network
       |
       v
Authenticate + authorize
       |
       v
Mask values by default
       |
       v
Optional OPS reveal with role + sanitizer
       |
       v
Audit response / retention / close after incident
```

**Điều cần nhớ nhất:**

- `enabled` không đồng nghĩa `exposed`.
- `exposed` không đồng nghĩa `authorized`.
- `authorized` không đồng nghĩa được phép thấy mọi raw value.
- `show-values=when-authorized` không thay authorization cho endpoint.
- `SanitizingFunction` không thay network isolation và không bảo vệ heapdump/logs.
- Custom `SecurityFilterChain` đòi hỏi bảo vệ Actuator rõ ràng.
- Một incident có thể cần mở tạm endpoint, nhưng luôn cần timebox, audit, và đóng lại.

Khi tuân thủ những nguyên tắc ấy, đội phát triển và vận hành vẫn tận dụng được Actuator để tìm lỗi `Environment`, profile và binding mà không biến đường chẩn đoán thành một kênh rò rỉ dữ liệu nhạy cảm.

### Tài liệu tham khảo chính thức

1. [Spring Boot 3.3 — Actuator Endpoints](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html): enablement, HTTP/JMX exposure, Spring Security, CSRF và sanitization.
2. [Spring Boot 3.3 — Monitoring and Management over HTTP](https://docs.spring.io/spring-boot/3.3/reference/actuator/monitoring.html): base path, management port, bind address, SSL và tắt HTTP management.
3. [Spring Boot 3.3 — Actuator REST API](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/index.html): URL, request và response của các endpoint.
4. [Spring Boot 3.3 — `SanitizingFunction` API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/endpoint/SanitizingFunction.html): custom value sanitization.
5. [Spring Boot 3.3 — Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html): `Environment`, property sources, profile và configuration binding.
6. [Spring Security — Servlet Authorization](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): filter chains, authorization và request matchers.
7. [Spring Security — CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html): protection cho các HTTP requests thay đổi trạng thái.
8. [Spring Boot 3.3 — Actuator Health](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.health): health groups, components và show-details.
