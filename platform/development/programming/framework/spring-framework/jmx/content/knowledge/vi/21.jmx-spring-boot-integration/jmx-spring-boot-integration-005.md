# Chọn endpoint được phép expose theo môi trường trong Spring Boot Actuator và JMX

## 1. Mục tiêu

Trong ứng dụng Spring Boot, **Actuator** cung cấp các endpoint quản trị để quan sát trạng thái runtime, health, metrics, logging và một số thao tác điều hành. Spring Boot có thể expose các endpoint này qua **HTTP** và/hoặc **JMX**, tùy cấu hình và điều kiện của endpoint.

Không phải mọi endpoint nên có mặt trên mọi môi trường. Một endpoint hữu ích cho developer khi debug có thể tiết lộ quá nhiều thông tin hoặc cho phép thay đổi trạng thái khi đưa lên production. Vì vậy cần thiết kế chính sách **endpoint nào được bật, endpoint nào được công bố qua HTTP, endpoint nào được công bố qua JMX**, kết hợp bảo mật ở đúng lớp.

Bài này tập trung vào:

- Phân biệt `enabled` với `exposed` trong Spring Boot Actuator.
- Cấu hình include/exclude cho JMX và HTTP riêng biệt.
- Chọn chính sách dev, staging và production.
- Hiểu tác động của Spring profiles và thứ tự ưu tiên cấu hình.
- Tránh mở lộ các endpoint có dữ liệu nhạy cảm hoặc operation làm thay đổi ứng dụng.
- Kiểm tra endpoint thực tế được expose, không chỉ đọc file YAML.

**Nguyên tắc:** một endpoint chỉ nên được công bố ở những công cụ và môi trường thực sự cần nó. `exposure` là chọn bề mặt quản trị, còn authentication, authorization, TLS, network policy và dữ liệu trả về vẫn phải được bảo vệ riêng.

## 2. Phân biệt enable, exposure và quyền truy cập

Ba tầng cần hiểu:

1. **Availability/enabled:** endpoint có được tạo và hoạt động trong ApplicationContext không? Thường chịu ảnh hưởng của properties `management.endpoint.<id>.enabled` hoặc các cấu hình tổng quát.
2. **Exposure:** endpoint có được công bố qua một technology cụ thể không? Ví dụ `management.endpoints.jmx.exposure.include` và `management.endpoints.web.exposure.include`.
3. **Security/access:** một client có được kết nối và thực thi thao tác không? Với HTTP là security chain/network; với JMX là policy của connector/MBeanServer và quản trị runtime.

Luồng khái quát:

```text
Spring Boot Actuator endpoint
        |
        +-- enabled? -------- no --> không có endpoint khả dụng
        |
        v yes
Endpoint exposure selection
        |
        +-- web include/exclude --> HTTP endpoint
        |
        +-- jmx include/exclude --> JMX MBean
                                            |
                                    JMX connector/auth
                                            |
                                   JConsole / JMX client
```

Một endpoint có thể được enabled nhưng **không exposed qua JMX**. Ngược lại, thêm tên endpoint vào danh sách JMX include không thể đảm bảo nó tồn tại nếu endpoint bị disabled, thiếu dependency hoặc có điều kiện cấu hình khác.

Cần đặc biệt chú ý sự khác nhau giữa các phiên bản Spring Boot. Những thuộc tính bổ sung như endpoint-specific access có thể tồn tại ở phiên bản mới và làm thay đổi tính khả dụng. Khi triển khai production, kiểm tra reference docs đúng major/minor version đang chạy.

## 3. Cấu hình exposure qua JMX và HTTP là độc lập

Các thuộc tính tiêu biểu:

```properties
management.endpoints.jmx.exposure.include=health,info,metrics
management.endpoints.jmx.exposure.exclude=env,beans

management.endpoints.web.exposure.include=health,info
management.endpoints.web.exposure.exclude=env,heapdump
```

Ở đây danh sách JMX và danh sách HTTP có thể khác nhau. Nếu `metrics` được include ở JMX nhưng không include ở web, monitoring qua JMX có thể truy cập endpoint Metrics trong khi URL HTTP tương ứng không được công bố.

Ngược lại, `health` có thể được công bố qua HTTP để phục vụ load balancer, nhưng không nhất thiết cần được expose qua JMX nếu hệ thống đã dùng health checks qua một kênh khác.

**Exclude thắng include** trong cấu hình exposure: nếu một endpoint vừa xuất hiện ở include vừa ở exclude của cùng technology, cấu hình exclude được dùng để loại endpoint đó khỏi bề mặt tương ứng.

Đối với production, ưu tiên danh sách include tường minh các endpoint cần dùng thay vì wildcard expose tất cả.

## 4. Ví dụ cấu hình theo profile

Một cấu hình chung có thể giới hạn HTTP mặc định:

```yaml
# application.yml
management:
  endpoints:
    web:
      exposure:
        include: health,info
    jmx:
      exposure:
        include: health,info
```

Trong development, công cụ local có thể cần thêm endpoints để debug:

```yaml
# application-dev.yml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,loggers
    jmx:
      exposure:
        include: health,info,metrics,beans,loggers,threaddump
```

Trong staging, mục tiêu thường là kiểm chứng gần production nhưng vẫn cho phép chẩn đoán có kiểm soát:

```yaml
# application-staging.yml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics
    jmx:
      exposure:
        include: health,info,metrics,threaddump
```

Trong production, một chính sách hẹp hơn:

```yaml
# application-prod.yml
management:
  endpoints:
    web:
      exposure:
        include: health,info
    jmx:
      exposure:
        include: health,info,metrics
```

Đây là **ví dụ thiết kế**, không phải danh sách mặc định bắt buộc. Nếu production không cần JMX Actuator, có thể cấu hình:

```yaml
management:
  endpoints:
    jmx:
      exposure:
        exclude: "*"
```

Nếu dùng Spring Boot phiên bản có hỗ trợ thuộc tính tổng thể để tắt JMX management exposure, cũng có thể dùng tùy chọn tương ứng theo tài liệu version. Không được nhầm việc tắt Actuator JMX exposure với việc tắt hoàn toàn một remote JMX connector của JVM.

## 5. Include và exclude theo môi trường: thực hiện cẩn thận

Ví dụ một profile dev có:

```yaml
management:
  endpoints:
    jmx:
      exposure:
        include: "*"
        exclude: env,configprops,heapdump
```

Khi cần exposure rộng để debug, vẫn nên dùng môi trường phát triển cô lập và tránh truyền secrets vào endpoint. Tuy nhiên wildcard có tác động đáng kể: nếu version hoặc dependency mới thêm endpoint, endpoint đó có thể tự xuất hiện mà không cần sửa cấu hình.

Do đó production nên ưu tiên allowlist:

```yaml
management:
  endpoints:
    jmx:
      exposure:
        include: health,info,metrics
```

Đừng coi exclude danh sách vài endpoint nhạy cảm tương đương allowlist: một endpoint chưa được liệt kê trong exclude vẫn có thể được expose nếu include là wildcard.

Với YAML, ký tự `*` cần đặt trong dấu nháy để không bị parser xem là alias marker. Trong `.properties`, có thể dùng `management.endpoints.jmx.exposure.include=*` theo cú pháp properties.

## 6. Bảng khuyến nghị sơ bộ cho từng môi trường

| Endpoint | Development | Staging | Production | Lưu ý |
| --- | --- | --- | --- | --- |
| `health` | Thường expose | Thường expose | Thường expose qua kênh cần thiết | Hạn chế chi tiết nhạy cảm |
| `info` | Có thể expose | Có thể expose | Có thể expose nếu nội dung an toàn | Metadata build/commit có thể tiết lộ thông tin |
| `metrics` | Hữu ích | Hữu ích | Tùy hạ tầng monitoring | Có thể chứa tên metric và tag nhạy cảm |
| `beans` | Chỉ khi debug | Hiếm khi cần | Thường không expose | Tiết lộ cấu trúc ApplicationContext |
| `env` | Cần kiểm soát | Hạn chế | Không expose đại trà | Properties có thể tiết lộ cấu hình |
| `configprops` | Debug có kiểm soát | Hạn chế | Không expose đại trà | Cấu trúc cấu hình có thể nhạy cảm |
| `loggers` | Tiện để debug | Theo nhu cầu | Chỉ cho operator được ủy quyền | Có thể đổi log level runtime |
| `threaddump` | Khi cần | Có thể cho chẩn đoán | Chỉ khi có quy trình incident | Có thể tiết lộ tên thread và hoạt động nội bộ |
| `heapdump` | Rất hạn chế | Rất hạn chế | Tránh expose thường trực | Heap dump có thể chứa secrets/PII |
| `shutdown` | Hạn chế và có chủ đích | Hiếm khi | Không expose đại trà | Thao tác dừng ứng dụng có side effect nghiêm trọng |

Không phải tất cả endpoint này luôn có mặt hay có khả năng expose qua mọi technology/version. Bảng nhằm giúp phân loại nhu cầu và rủi ro, không phải danh sách endpoint bảo đảm sẵn có.

## 7. Ví dụ dùng biến môi trường thay vì nhiều YAML

Nếu hệ thống deploy qua container hoặc orchestration, có thể điều khiển exposure bằng environment variables:

```text
MANAGEMENT_ENDPOINTS_JMX_EXPOSURE_INCLUDE=health,info,metrics
MANAGEMENT_ENDPOINTS_WEB_EXPOSURE_INCLUDE=health,info
```

Spring Boot hỗ trợ relaxed binding đối với environment variables trong nhiều trường hợp. Tuy nhiên cấu hình cuối cùng phụ thuộc thứ tự ưu tiên property sources, profile, command-line flags và platform. Vì thế cần xác minh properties **hiệu lực**, không chỉ giá trị nằm trong một file.

Ví dụ nên dùng deployment manifest có biến riêng cho môi trường:

```text
DEV:
  MANAGEMENT_ENDPOINTS_JMX_EXPOSURE_INCLUDE=health,info,metrics,beans

PROD:
  MANAGEMENT_ENDPOINTS_JMX_EXPOSURE_INCLUDE=health,info,metrics
```

Tránh cho phép mọi deployment tùy ý override chính sách nếu hạ tầng yêu cầu governance. Các môi trường nhạy cảm nên có guardrails ở CI/CD hoặc policy của platform để ngăn wildcard expose thiếu kiểm soát.

## 8. Cấu hình endpoint-specific enabled

Có thể tắt một endpoint hoàn toàn nếu không cần:

```yaml
management:
  endpoint:
    shutdown:
      enabled: false
```

Hoặc trong một số trường hợp:

```yaml
management:
  endpoint:
    env:
      enabled: false
```

Khi endpoint bị disabled, thay đổi danh sách exposure không làm endpoint trở lại khả dụng. Điều này hữu ích cho các endpoint có rủi ro cao mà tổ chức không muốn bật trong bất kỳ kênh nào.

Với các phiên bản Spring Boot mới có chính sách access riêng, cần xét thêm cấu hình access; không nên coi `enabled` và `exposure` là hai thuộc tính duy nhất trong mọi version.

**Lưu ý vận hành:** nếu tắt một endpoint mà hệ thống monitoring đang dùng, cần cập nhật dashboard, alert rule hoặc health probe tương ứng. Những cấu hình quản trị này nên được coi là contract vận hành.

## 9. JMX exposure không đồng nghĩa mở remote JMX

Spring Boot có thể đăng ký Actuator endpoints dưới dạng MBean trong một MBeanServer, kể cả khi ứng dụng **không mở cổng JMX remote**. Việc `management.endpoints.jmx.exposure.include` chứa một endpoint chỉ làm endpoint đó đủ điều kiện hiển thị qua JMX layer tương ứng; nó không tự cấu hình toàn bộ RMI connector, xác thực hay firewall.

Để công cụ remote kết nối, JVM/container còn cần JMX connector và chính sách bảo mật. Vì vậy:

- Không mặc định JMX đã được bảo vệ chỉ vì HTTP Spring Security yêu cầu login.
- Không mặc định `management.server.port` tạo cổng JMX remote tương ứng.
- Không mặc định `management.endpoints.web.exposure.exclude` chặn endpoint ở JMX.
- Không mặc định `management.endpoints.jmx.exposure.exclude` chặn endpoint qua HTTP.

HTTP và JMX là hai công nghệ exposure tách biệt. Mỗi đường truy cập cần chính sách security tương ứng.

## 10. Hạn chế HTTP Actuator bằng Spring Security

Với HTTP, Spring Security có thể bảo vệ actuator requests. Ví dụ minh họa dùng `EndpointRequest` để chỉ cho phép health công khai và yêu cầu xác thực với endpoint khác:

```java
import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;
import org.springframework.boot.actuate.health.HealthEndpoint;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ActuatorHttpSecurityConfig {
    @Bean
    SecurityFilterChain actuatorChain(HttpSecurity http) throws Exception {
        http.securityMatcher(EndpointRequest.toAnyEndpoint())
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(EndpointRequest.to(HealthEndpoint.class))
                .permitAll()
                .anyRequest().authenticated()
            );
        return http.build();
    }
}
```

Đây là ví dụ cho một Spring Boot/Spring Security generation có API cấu hình tương ứng. Trong ứng dụng thực, phải có security chain cho traffic còn lại và xét CSRF, session, authentication providers, endpoint management port/context path. Ví dụ không tự bảo vệ JMX connector.

Nếu health public nhưng trả chi tiết thành phần nội bộ, cần giới hạn cấu hình health detail. Cho phép HTTP GET health công khai không nên có nghĩa tiết lộ database URL hoặc thông tin hạ tầng nhạy cảm.

## 11. Cấu hình health details theo môi trường

Health endpoint thường cần cho orchestration, nhưng mức chi tiết khác nhau theo đối tượng truy cập. Ví dụ:

```yaml
management:
  endpoint:
    health:
      show-details: never
```

Hoặc triển khai có bảo vệ:

```yaml
management:
  endpoint:
    health:
      show-details: when-authorized
```

Trường hợp `when-authorized` cần hiểu cách role/authorization được Actuator xác định trong version và technology sử dụng. Không nên suy ra cùng một kiểm soát role của HTTP tự động áp dụng giống hệt với JMX.

Đối với production, có thể chọn public health summary trong khi chi tiết diagnostics chỉ được cấp cho operator qua kênh riêng được kiểm soát.

## 12. Tách endpoint exposure khỏi chính sách dữ liệu

Một endpoint dù chỉ đọc vẫn có thể tiết lộ:

- Runtime configuration, environment variables, URL và connection details.
- Spring bean graph, tên class, package, tên dependency.
- Metric tags chứa user ID hoặc tenant ID nếu ứng dụng gắn tag không an toàn.
- Thread names, stack traces hoặc dữ liệu debug.
- Build metadata, SCM commit hoặc thông tin deployment.

Không nên đưa secrets vào endpoint rồi chỉ dựa vào việc nó không xuất hiện trên một trang UI. Các JMX client có thể truy cập metadata và attributes qua API.

Phân loại dữ liệu nên bắt đầu từ nguồn. Trong custom actuator endpoint, chỉ trả summary an toàn và tránh trả raw object graph. Đối với môi trường được bảo vệ tốt vẫn cần data minimization, vì credential hoặc account có thể bị lộ hoặc cấp sai quyền.

## 13. Custom Actuator endpoint và điều kiện exposure

Spring Boot hỗ trợ custom actuator endpoints qua annotation như `@Endpoint`, với operations được đánh dấu `@ReadOperation`, `@WriteOperation` hoặc `@DeleteOperation` theo API version.

Ví dụ:

```java
import org.springframework.boot.actuate.endpoint.annotation.Endpoint;
import org.springframework.boot.actuate.endpoint.annotation.ReadOperation;
import org.springframework.stereotype.Component;

@Component
@Endpoint(id = "queueSummary")
public class QueueSummaryEndpoint {
    private final QueueMetrics metrics;

    public QueueSummaryEndpoint(QueueMetrics metrics) {
        this.metrics = metrics;
    }

    @ReadOperation
    public QueueSummary summary() {
        return new QueueSummary(
            metrics.pendingCount(),
            metrics.runningCount()
        );
    }
}

`QueueMetrics` là service do ứng dụng tự định nghĩa; `QueueSummary` là DTO có hai số liệu tổng hợp. Với custom endpoint, metadata id và operation phải phù hợp quy tắc endpoint của Spring Boot version sử dụng. Ví dụ minh họa ý tưởng, không đại diện cho mọi biến thể HTTP/JMX operation mapping.

Endpoint này cũng cần được enabled và exposed qua technology tương ứng. Nếu muốn expose trong dev nhưng không production, đưa id vào include list của profile dev và loại khỏi include list prod.

**Đừng tự động chuyển custom endpoint có write/delete operations ra production** mà chưa có policy cấp quyền và validation; những operation này có thể thay đổi hoặc xóa trạng thái ứng dụng.

## 14. Endpoint và Spring JMX @ManagedResource là hai cơ chế có thể cùng tồn tại

Spring Framework hỗ trợ custom JMX MBeans qua `@ManagedResource`, `@ManagedAttribute`, `@ManagedOperation` và `MBeanExporter`. Spring Boot Actuator hỗ trợ endpoint abstraction riêng có thể expose qua JMX.

Ví dụ:

```text
Spring custom @ManagedResource
  -> MBeanExporter
  -> JMX ObjectName

Spring Boot Actuator @Endpoint
  -> Actuator JMX exposure
  -> JMX MBean
```

Thuộc tính `management.endpoints.jmx.exposure.include` dành cho các **Actuator endpoints**, không nên xem đây là một bộ lọc tự động áp dụng lên mọi `@ManagedResource` do ứng dụng export thủ công.

Vì vậy khi muốn giảm surface JMX production, cần kiểm tra cả hai nhóm: Actuator endpoint exposure và custom MBeanExporter beans/autodetection. Việc exclude `env` không ngăn một custom MBean khác công bố cùng dữ liệu nhạy cảm qua getter riêng.

## 15. Kiểm tra cấu hình có hiệu lực

Không nên chỉ nhìn `application-prod.yml`. Để xác nhận exposure thực tế, hãy:

1. Xác định active profiles trong runtime (`spring.profiles.active`) và thứ tự PropertySources.
2. Kiểm tra properties quản trị được nạp từ environment, command-line, config server và deployment manifest.
3. Kiểm tra danh sách JMX MBeans thực sự đăng ký trong đúng MBeanServer.
4. Kiểm tra HTTP actuator discovery và truy cập trên đường dẫn/port đã cấu hình (nếu được phép).
5. Dùng account với quyền như monitoring/operator thật để xác minh hành vi, không dùng admin account làm đại diện.
6. Đối chiếu endpoint danh sách với danh sách được phê duyệt theo môi trường.

Với JMX, có thể query những MBean thuộc namespace quản trị phù hợp:

```java
import java.lang.management.ManagementFactory;
import java.util.Set;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();

Set<ObjectName> names = server.queryNames(
    new ObjectName("org.springframework.boot:*") ,
    null
);

names.stream()
     .map(ObjectName::getCanonicalName)
     .sorted()
     .forEach(System.out::println);
```

Domain trong ví dụ là minh họa cho cấu hình Spring Boot phổ biến; nếu đã cấu hình JMX domain khác, phải thay pattern tương ứng. Không dùng một pattern cụ thể để khẳng định mọi Actuator MBean đều đã xuất hiện.

## 16. Những lỗi phổ biến

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Endpoint không xuất hiện trong JMX | Chưa include, endpoint disabled, không hỗ trợ JMX hoặc MBeanServer sai | Kiểm tra enabled, exposure, version và server |
| Dev expose đúng, prod lại thiếu metric cần thiết | Profile prod include thiếu id hoặc property override | Kiểm tra active profiles và property precedence |
| HTTP endpoint bị ẩn nhưng JConsole vẫn thấy | Web và JMX exposure là hai danh sách riêng | Điều chỉnh `management.endpoints.jmx.exposure` |
| JMX endpoint bị ẩn nhưng HTTP vẫn truy cập | JMX exclude không điều khiển HTTP | Điều chỉnh `management.endpoints.web.exposure` và security |
| Bật wildcard làm xuất hiện endpoint mới sau upgrade | Include `*` mở rộng theo tập endpoint có mặt | Ưu tiên allowlist trong production |
| Loggers có thể thay đổi từ xa | Endpoint expose write operation và client được cấp quyền | Giới hạn exposure và authorization |
| Health public tiết lộ chi tiết nội bộ | `show-details` quá rộng | Thu hẹp dữ liệu, cấu hình group/authorization |
| Không thấy custom @ManagedResource trong danh sách Actuator | Custom JMX MBean không thuộc Actuator endpoint catalog | Kiểm tra MBeanExporter riêng |

## 17. Khuyến nghị vận hành theo nguyên tắc least privilege

**Development:** có thể cần nhiều thông tin để phân tích lỗi. Chỉ expose thêm khi có nhu cầu; nếu wildcard, môi trường phải cô lập và không có dữ liệu thật nhạy cảm.

**Staging:** ưu tiên cấu hình gần production để kiểm tra deployment và monitoring. Bổ sung chẩn đoán trong khoảng thời gian/hình thức được kiểm soát, không để rộng vĩnh viễn.

**Production:** dùng allowlist endpoint cần thiết, ví dụ `health`, `info` và một phần metrics nếu hệ thống giám sát sử dụng. Các endpoint đổi trạng thái hoặc tiết lộ cấu trúc nội bộ cần bảo vệ đặc biệt hoặc không expose.

Đặc biệt tránh sử dụng JMX remote không xác thực hoặc không mã hóa trên mạng không tin cậy. Với HTTP, bảo vệ actuator bằng network policy, authentication, authorization và giới hạn thông tin trả về.

Thay exposure policy là thay đổi quản trị: monitoring, alerting hoặc operational runbooks có thể phụ thuộc vào endpoint. Vì vậy cần quản lý cấu hình như code, có review và xác nhận behavior ở môi trường đích.

## 18. Mô hình tư duy

```text
                    Spring Boot application
                              |
                       Actuator endpoints
                              |
                   enabled / access policy
                              |
                    +---------+---------+
                    |                   |
              WEB exposure         JMX exposure
                    |                   |
               HTTP path           JMX MBean
                    |                   |
              Spring Security      JMX connector
              + network policy     + JMX permissions
                    |                   |
                   Client / monitoring tools
```

**Kết luận:** để chọn endpoint được phép expose theo môi trường, hãy thiết kế riêng **tập endpoint enabled**, **danh sách HTTP exposure** và **danh sách JMX exposure**, rồi áp dụng security ở đúng technology. Spring profiles giúp cấu hình dev/staging/prod khác nhau, nhưng phải kiểm tra giá trị hiệu lực sau khi deploy. Trong production, ưu tiên allowlist hẹp, tránh wildcard và không nhầm cơ chế exposure của Actuator với toàn bộ custom MBean của Spring Framework.
