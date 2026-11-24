# Health endpoint trong Spring Boot

Health endpoint cho biết ứng dụng có đang ở trạng thái phù hợp để tiếp tục chạy và nhận traffic hay không. Spring Boot Actuator cung cấp health endpoint tổng hợp trạng thái từ các thành phần như database, disk space, messaging và health indicators do ứng dụng định nghĩa. Load balancer, orchestrator và monitoring system có thể dùng kết quả này để quyết định có gửi traffic tới instance hay không. Muốn dùng đúng, cần hiểu health status phản ánh điều gì, contributor nào tham gia, cách phân biệt liveness với readiness và cách bảo vệ thông tin nội bộ.

Trong module **SPRING_BOOT_OBSERVABILITY**, Health endpoint thuộc chương **Actuator và management**, kết nối các cơ chế vận hành với metrics, logs và distributed tracing. Bài tập trung vào cấu hình, mở rộng và vận hành health endpoint trong Spring Boot: HealthContributor, HealthIndicator, status aggregation, health groups, Kubernetes probes, security, caching, kiểm thử và troubleshooting.

## Mục tiêu học tập

1. Giải thích vai trò của Actuator health endpoint và health contributors.
2. Đọc health status và component details.
3. Phân biệt liveness, readiness và health tổng hợp.
4. Cấu hình health groups và Kubernetes probes.
5. Viết custom HealthIndicator cho thành phần nghiệp vụ.
6. Thiết kế dependency checks để tránh cascade restart.
7. Bảo vệ endpoint và giới hạn thông tin trả về.
8. Kiểm soát caching, timeout và tác động của health checks.
9. Kiểm thử các trạng thái UP, DOWN, OUT_OF_SERVICE và UNKNOWN.

## 1. Health endpoint là gì?

Spring Boot Actuator cung cấp endpoint health để trả về trạng thái tổng quát của ứng dụng và các thành phần được kiểm tra. Với cấu hình mặc định, endpoint thường được truy cập tại:

~~~http
GET /actuator/health
~~~

Một response đơn giản:

~~~json
{
  "status": "UP"
}
~~~

Khi được phép hiển thị component details, response có thể bao gồm:

~~~json
{
  "status": "UP",
  "components": {
    "db": { "status": "UP" },
    "diskSpace": { "status": "UP" },
    "ping": { "status": "UP" }
  }
}
~~~

Tên components và cấu trúc response phụ thuộc dependencies, contributors, groups và cấu hình show-details. Không coi ví dụ là schema cố định cho mọi ứng dụng.

### 1.1. Health status không phải uptime

Health endpoint phản ánh trạng thái tại thời điểm kiểm tra theo contributors đang tham gia. Nó không chứng minh ứng dụng chưa từng lỗi, không thay thế lịch sử availability và không đo request success rate. Để theo dõi SLO/uptime, cần metrics, synthetic checks và monitoring có lịch sử.

### 1.2. Health endpoint không phải business API

Health endpoint phục vụ kiểm tra vận hành. Không dùng nó để trả dữ liệu nghiệp vụ, xác thực user hoặc cung cấp dashboard quản trị. Response nên nhỏ, nhanh và ổn định.

## 2. Actuator dependencies và exposure

Thêm Actuator starter:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
~~~

Giữ version theo Spring Boot BOM. Actuator endpoint có thể được expose qua HTTP hoặc JMX. Việc endpoint tồn tại trong application context không đồng nghĩa endpoint đã được expose qua web.

Ví dụ expose health và info qua HTTP:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info
~~~

Chỉ expose endpoint thực sự cần. Các endpoint như env, configprops, beans, heapdump hoặc loggers có thể tiết lộ cấu hình, topology hoặc thông tin nội bộ. Không dùng wildcard exposure trong production nếu chưa đánh giá từng endpoint và bảo vệ truy cập.

### 2.1. Management port và base path

Có thể đặt base path hoặc port quản lý riêng:

~~~yaml
management:
  endpoints:
    web:
      base-path: /actuator
  server:
    port: 8081
~~~

Khi dùng management port riêng, cấu hình network policy, firewall, service routing và probe path tương ứng. Port quản lý riêng không tự động được bảo vệ chỉ vì khác port ứng dụng.

## 3. Health contributors và aggregation

Actuator xây dựng health response từ HealthContributor. Các loại thường gặp:

- HealthIndicator: một contributor đồng bộ trả trạng thái.
- ReactiveHealthIndicator: contributor reactive.
- CompositeHealthContributor: nhóm nhiều contributors.
- HealthContributor: abstraction chung cho health tree.

Các auto-configured indicators có thể xuất hiện khi dependency tương ứng có mặt, ví dụ database hoặc disk space. Danh sách thực tế phụ thuộc classpath và cấu hình.

~~~mermaid
flowchart TD
    Endpoint["/actuator/health"] --> Aggregate["HealthEndpoint"]
    Aggregate --> DB["DataSource health"]
    Aggregate --> Disk["Disk space"]
    Aggregate --> Custom["Custom HealthIndicator"]
    Aggregate --> Broker["Messaging health"]
    DB --> Status["Aggregate status"]
    Disk --> Status
    Custom --> Status
    Broker --> Status
    Status --> Response["HTTP response"]
~~~

HealthEndpoint tổng hợp trạng thái contributors theo status aggregator. Một contributor DOWN có thể làm health tổng hợp thành DOWN, tùy group và aggregation policy.

### 3.1. Các status phổ biến

| Status | Ý nghĩa thường gặp | Hành động có thể |
| --- | --- | --- |
| UP | Thành phần hoạt động | Tiếp tục phục vụ |
| DOWN | Thành phần không hoạt động | Điều tra lỗi |
| OUT_OF_SERVICE | Không nên nhận traffic | Đưa khỏi load balancing |
| UNKNOWN | Chưa xác định trạng thái | Kiểm tra indicator/config |

Status có thể được mở rộng. Thứ tự ưu tiên và HTTP status mapping phụ thuộc cấu hình.

### 3.2. Status aggregation và HTTP mapping

Health aggregator chọn trạng thái tổng hợp dựa trên status của contributors và thứ tự ưu tiên. DOWN thường nghiêm trọng hơn UP. Nếu định nghĩa custom status, cấu hình mapping/ordering nhất quán để endpoint và orchestrator diễn giải giống nhau.

Health status có thể được ánh xạ sang HTTP status như UP → 200 và DOWN/OUT_OF_SERVICE → 503. UNKNOWN mapping phụ thuộc cấu hình. Khi thay đổi mapping, kiểm tra load balancer và Kubernetes probe có xử lý đúng response code hay không.

## 4. HealthIndicator và custom checks

Khi Actuator không có indicator phù hợp cho thành phần ứng dụng, triển khai HealthIndicator:

~~~java
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.stereotype.Component;

@Component
public class SearchIndexHealthIndicator implements HealthIndicator {
    private final SearchIndexClient client;

    public SearchIndexHealthIndicator(SearchIndexClient client) {
        this.client = client;
    }

    @Override
    public Health health() {
        try {
            if (client.ping()) {
                return Health.up()
                        .withDetail("component", "search-index")
                        .build();
            }
            return Health.down()
                    .withDetail("reason", "search index did not respond")
                    .build();
        } catch (Exception ex) {
            return Health.down(ex).build();
        }
    }
}
~~~

Ví dụ minh họa một kiểm tra nhẹ. Trong production, client.ping cần timeout ngắn, giới hạn retries và không thực hiện query nặng. Cân nhắc không đưa exception message hoặc host/credentials vào public details.

### 4.1. HealthIndicator phải nhanh và có giới hạn

Health endpoint có thể được gọi thường xuyên bởi orchestrator. Một indicator chậm có thể tiêu thụ threads, mở nhiều connections hoặc làm chính ứng dụng quá tải. Mỗi external check nên có timeout nhỏ phù hợp probe budget, không retry dài, operation nhẹ/read-only và giới hạn concurrency nếu check có thể chồng lấn.

### 4.2. Không dùng business transaction làm health check

Không tạo đơn hàng, gửi payment hoặc thay đổi dữ liệu để kiểm tra health mỗi vài giây. Dùng ping/read-only check hoặc health API chính thức của dependency. Nếu cần synthetic business transaction, chạy ở hệ thống kiểm thử riêng và có cleanup.

### 4.3. ReactiveHealthIndicator

Với ứng dụng reactive, dùng ReactiveHealthIndicator khi check phụ thuộc reactive client. Không block event loop để chờ network check. Đặt timeout bằng reactive operator phù hợp và trả Health reactive result.

## 5. Liveness và readiness

Liveness và readiness trả lời hai câu hỏi khác nhau:

- **Liveness:** process/application có còn sống và có khả năng tự tiếp tục không?
- **Readiness:** instance hiện tại đã sẵn sàng nhận traffic chưa?

Nếu liveness thất bại, orchestrator có thể restart container. Nếu readiness thất bại, instance thường được rút khỏi service endpoints/load balancing nhưng vẫn tiếp tục chạy để phục hồi.

### 5.1. Vì sao không gộp hai khái niệm?

Nếu database tạm thời mất kết nối và database indicator làm liveness DOWN, Kubernetes có thể restart mọi pod. Restart không sửa được database; các pod khởi động lại có thể đồng loạt reconnect và làm database chịu tải lớn hơn.

Liveness nên phản ánh tình trạng process/runtime mà restart có khả năng khắc phục. Readiness có thể tính đến dependency thiết yếu nếu ứng dụng không thể phục vụ request khi dependency đó không sẵn sàng.

### 5.2. Bật Kubernetes probes

Spring Boot có thể expose liveness/readiness health groups khi probes được bật:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
~~~

Các path thường dùng:

~~~text
/actuator/health/liveness
/actuator/health/readiness
~~~

Trong Kubernetes, cấu hình startupProbe, livenessProbe và readinessProbe trỏ tới path phù hợp. Nếu management server chạy port riêng, probe phải dùng đúng port và network path.

### 5.3. Liveness group

Liveness group đánh giá ứng dụng có còn hoạt động và có khả năng tiếp tục chạy. Tránh thêm database, broker hoặc external API vào liveness group nếu restart ứng dụng không thể khắc phục sự cố dependency.

### 5.4. Readiness group

Readiness group đánh giá instance có nhận traffic được không. Có thể thêm dependency thực sự bắt buộc cho request path. Tuy nhiên, nếu dependency dùng chung bị lỗi, mọi pod có thể chuyển NOT READY đồng thời. Cần xem xét degraded mode, fallback, circuit breaker và khả năng xử lý request không phụ thuộc thành phần đó.

### 5.5. Startup probe

Ứng dụng có thể cần thời gian khởi động để warm cache, migrate schema hoặc load model. startupProbe cho phép container có khoảng thời gian khởi động trước khi liveness/readiness checks bắt đầu ảnh hưởng. Cấu hình startup budget dựa trên startup duration thực tế, không tăng vô hạn để che lỗi khởi động.

## 6. Health groups

Health groups tạo các tập contributors khác nhau cho từng mục tiêu kiểm tra. Ví dụ:

~~~yaml
management:
  endpoint:
    health:
      group:
        readiness:
          include: readinessState,db
        liveness:
          include: livenessState
~~~

Tên contributor và group configuration cần khớp Spring Boot version. Boot có thể tự cấu hình probe groups khi probes enabled. Nếu tùy chỉnh include/exclude, xác minh contributors thực tế và status mapping.

### 6.1. Custom group

Có thể tạo group riêng cho dependency hoặc operation cụ thể, chẳng hạn dependencies:

~~~yaml
management:
  endpoint:
    health:
      group:
        dependencies:
          include: db,searchIndex
~~~

Kiểm tra group path theo endpoint convention/version. Không expose group nhạy cảm công khai nếu details chứa thông tin nội bộ.

### 6.2. Include và exclude

Group include/exclude xác định contributors tham gia. Indicator không nằm trong group không ảnh hưởng status group đó. Điều này giúp tách liveness khỏi dependency health, nhưng cần tài liệu hóa để đội vận hành không hiểu nhầm health tổng hợp với health readiness.

## 7. Dependency health và degraded mode

Không phải mọi dependency đều cần làm instance unready. Phân loại theo mức độ bắt buộc:

| Dependency | Khi lỗi | Quyết định readiness |
| --- | --- | --- |
| Primary database cho mọi request | Không thể phục vụ use case chính | Có thể NOT READY |
| Search index có fallback DB | Search degraded nhưng API vẫn phục vụ | Có thể vẫn READY |
| Analytics sink bất đồng bộ | Có thể buffer/retry | Thường không ảnh hưởng readiness |
| Optional recommendation API | Có fallback | Thường vẫn READY |
| Payment provider cho endpoint payment | Payment route không dùng được | Cân nhắc monitoring riêng |

Readiness là trạng thái instance đối với traffic mà nó nhận, không phải báo cáo mọi dependency trong hệ thống. Nếu service có nhiều loại endpoint với dependency khác nhau, một readiness bit duy nhất có thể quá thô; dùng monitoring/dependency groups bổ sung và thiết kế routing/degraded mode rõ ràng.

### 7.1. Không tạo cascade failure

Nếu tất cả replicas cùng kiểm tra một dependency chung và đồng loạt chuyển unready khi dependency chập chờn, traffic có thể bị dồn vào không instance nào hoặc tạo restart/reconnect storm. Kết hợp readiness với circuit breaker, timeout, bulkhead và fallback. Không để probe gọi dependency với retry storm.

### 7.2. Health check và circuit breaker

Health endpoint không thay thế circuit breaker. Circuit breaker điều khiển lời gọi nghiệp vụ theo failure/slow-call behavior. Health indicator báo trạng thái cho hệ thống vận hành. Dùng cùng dependency client có timeout hợp lý nhưng không nhất thiết dùng chung mọi state nội bộ của circuit breaker làm readiness.

## 8. Security và hiển thị details

Health details có thể tiết lộ tên database, broker, internal host, version, disk path hoặc lỗi cấu hình. Cấu hình show-details theo nhu cầu và quyền truy cập:

~~~yaml
management:
  endpoint:
    health:
      show-details: when-authorized
      show-components: when-authorized
~~~

Giá trị được hỗ trợ phụ thuộc Spring Boot version. Có thể dùng never để ẩn chi tiết hoặc when-authorized khi có security authorization phù hợp.

### 8.1. Bảo vệ Actuator endpoints

Nếu endpoint quản lý được expose qua HTTP, cấu hình Spring Security để giới hạn quyền. Ví dụ filter chain riêng cho management paths:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ManagementSecurityConfiguration {
    @Bean
    SecurityFilterChain managementSecurity(HttpSecurity http) throws Exception {
        return http
                .securityMatcher("/actuator/**")
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(
                                "/actuator/health",
                                "/actuator/health/liveness",
                                "/actuator/health/readiness"
                        ).permitAll()
                        .anyRequest().hasRole("OPS")
                )
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}
~~~

Đây là ví dụ filter chain riêng; ứng dụng có thể cần chain khác cho business endpoints và thứ tự @Order phù hợp. Nếu probes cần truy cập không xác thực, chỉ cho phép path health tối thiểu và giới hạn network tới management port. Không mở tất cả Actuator endpoints.

### 8.2. Public status, private details

Có thể cho phép probe đọc status nhưng chỉ user có quyền xem component details. Không đưa exception stack trace, credentials, connection URL hoặc internal IP vào response công khai. Kiểm thử cả anonymous và authorized callers.

## 9. Caching, timeout và probe frequency

Health checks có thể được gọi mỗi vài giây từ nhiều orchestrator instances. Nếu mỗi lần check mở connection mới hoặc gọi nhiều remote APIs, endpoint trở thành nguồn tải bổ sung.

### 9.1. Cache health result

Actuator health endpoint hỗ trợ cache time-to-live trong cấu hình endpoint, tùy phiên bản. Ví dụ:

~~~yaml
management:
  endpoint:
    health:
      cache:
        time-to-live: 5s
~~~

Cache giảm số lần check dependency nhưng làm status có độ trễ. Chọn TTL ngắn hơn failure detection budget và hiểu cache áp dụng ở endpoint/group nào theo version.

### 9.2. Timeout phải ngắn hơn probe budget

Nếu probe timeout ở orchestrator là 2 giây nhưng indicator có thể block 10 giây, nhiều probe threads có thể bị chiếm dụng. Đặt timeout mỗi dependency nhỏ hơn tổng health request budget. Health endpoint phải trả kết quả nhanh hoặc fail fast.

### 9.3. Tránh health check gây tải database

Không chạy full table scan, count toàn bảng hoặc query nghiệp vụ nặng. Dùng validation nhẹ như lấy connection và thực hiện query hằng số nếu phù hợp. SELECT 1 cũng có chi phí network/connection; chọn tần suất và timeout hợp lý.

## 10. Kiểm thử health endpoint

Cần test HTTP response, status aggregation, group membership, security và custom indicator.

### 10.1. Test custom HealthIndicator

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.actuate.health.Status;
import static org.assertj.core.api.Assertions.assertThat;

class SearchIndexHealthIndicatorTest {
    @Test
    void reportsDownWhenIndexUnavailable() {
        SearchIndexClient client = () -> false;
        SearchIndexHealthIndicator indicator =
                new SearchIndexHealthIndicator(client);

        assertThat(indicator.health().getStatus()).isEqualTo(Status.DOWN);
    }
}
~~~

Ví dụ giả định client interface có ping trả boolean. Test này xác minh mapping logic của indicator, không chứng minh endpoint HTTP/security.

### 10.2. Test endpoint với MockMvc

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class HealthEndpointTest {
    @Autowired
    MockMvc mvc;

    @Test
    void healthEndpointIsAvailable() throws Exception {
        mvc.perform(get("/actuator/health"))
                .andExpect(status().isOk());
    }
}
~~~

Test cần cấu hình exposure và security phù hợp. Nếu health check trả DOWN, endpoint có thể trả 503; test status phải phản ánh fixture/indicator state thay vì giả định luôn 200.

### 10.3. Test readiness và liveness groups

Gửi request tới hai group paths và xác minh:
- readiness bao gồm đúng contributors;
- liveness không phụ thuộc external database/broker nếu thiết kế yêu cầu;
- contributor DOWN ảnh hưởng group dự kiến;
- HTTP status mapping đúng;
- group details chỉ hiện với caller được phép.

### 10.4. Test security và details

Test anonymous caller, caller có role OPS và caller thiếu role. Xác minh public status không chứa internal details, authorized details chỉ có thông tin đã duyệt và endpoint quản lý khác vẫn bị bảo vệ.

## 11. Troubleshooting

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| /actuator/health trả 404 | Actuator thiếu hoặc endpoint không expose | Kiểm tra dependency và web exposure |
| Health trả DOWN | Một contributor thất bại | Xem details với quyền phù hợp và kiểm tra dependency |
| Health trả 503 dù app vẫn nhận request | Aggregator/group contributor DOWN | Kiểm tra group và HTTP mapping |
| Kubernetes liên tục restart pod | Liveness phụ thuộc external dependency | Tách liveness khỏi readiness |
| Pod không nhận traffic | Readiness group DOWN | Xác minh dependency thật sự bắt buộc |
| Probe timeout | Indicator block hoặc retry lâu | Timeout ngắn, cache và giảm check cost |
| Component details không xuất hiện | show-details policy hoặc authorization | Kiểm tra security và config |
| Custom indicator không xuất hiện | Bean không được scan hoặc group không include | Kiểm tra component scan/group |
| Health check làm DB load tăng | Query nặng hoặc probe quá thường xuyên | Lightweight check và TTL |
| Status UNKNOWN | Contributor không xác định trạng thái | Xử lý fallback/status mapping |
| Mọi pod unready khi broker lỗi | Shared dependency check gây cascade | Degraded mode và readiness policy |
| Health endpoint lộ topology | Details mở rộng cho anonymous | Ẩn details và giới hạn truy cập |

### 11.1. Quy trình điều tra

1. Gọi health endpoint tổng hợp và xác định status.
2. Nếu có quyền, xem component details để tìm contributor lỗi.
3. Kiểm tra group mà probe đang gọi: liveness hay readiness.
4. Xác minh indicator timeout và dependency availability.
5. Kiểm tra HTTP status mapping, security và management port.
6. Đối chiếu với logs/metrics của dependency.
7. Kiểm tra cache TTL và probe frequency.
8. Nếu Kubernetes restart pod, xác minh liveness có phụ thuộc hệ thống ngoài hay không.

## 12. Production checklist

| Tiêu chí | Bằng chứng cần có |
| --- | --- |
| Actuator health được expose | Chỉ path cần thiết |
| Liveness và readiness tách biệt | Group membership được kiểm thử |
| Dependency policy rõ ràng | Dependency bắt buộc và optional được phân loại |
| Custom indicators nhẹ | Timeout, read-only, không retry dài |
| Status aggregation rõ | DOWN/OUT_OF_SERVICE/UNKNOWN mapping |
| Security đúng | Public status, private details |
| Management network giới hạn | Port/firewall/network policy |
| Cache TTL hợp lý | Không stale quá failure budget |
| Probe budgets phù hợp | Startup/liveness/readiness timeout |
| Không cascade restart | Liveness không phụ thuộc external services |
| Details được redact | Không credentials/internal data |
| Tests đủ tình huống | UP/DOWN, groups, security, timeout |
| Monitoring có lịch sử | Metrics/alerts bổ sung point-in-time health |

## 13. Bài thực hành: cấu hình health probes cho order-service

**Bối cảnh:** order-service chạy trên Kubernetes, phụ thuộc PostgreSQL và inventory-service. Khi PostgreSQL gián đoạn ngắn, pod bị restart liên tục dù JVM vẫn khỏe và có thể phục hồi khi database trở lại.

**Nhiệm vụ:**
1. Thêm Spring Boot Actuator và expose health endpoint.
2. Bật liveness/readiness probes theo phiên bản Spring Boot.
3. Đảm bảo liveness group chỉ phản ánh tình trạng process/runtime.
4. Đưa database indicator vào readiness nếu database là dependency bắt buộc cho traffic.
5. Tạo custom SearchIndexHealthIndicator hoặc indicator tương đương với timeout ngắn.
6. Kiểm tra behavior khi database DOWN nhưng process vẫn hoạt động.
7. Cấu hình Kubernetes startupProbe/livenessProbe/readinessProbe với path và port đúng.
8. Bảo vệ component details; chỉ public status tối thiểu cho probe.
9. Thử cache TTL và đo tác động tới probe freshness.
10. Test security, group membership, status aggregation và timeout.
11. Xác minh database outage không gây liveness restart storm.
12. Viết runbook phân biệt pod unhealthy, pod not ready và dependency degraded.

**Kết quả mong đợi:** Actuator configuration, custom health indicator, probe groups, Kubernetes probe setup, integration tests và runbook vận hành.

## 14. Ghi nhớ

Health endpoint cung cấp trạng thái tại thời điểm kiểm tra từ các HealthContributor. Nó hỗ trợ load balancer, orchestrator và monitoring nhưng không thay thế metrics có lịch sử hoặc synthetic checks. Liveness trả lời process có nên tiếp tục chạy; readiness trả lời instance có nên nhận traffic. Hai group cần contributor membership khác nhau theo thiết kế.

Custom indicators phải nhanh, read-only, có timeout và không tạo tải đáng kể. Không đưa external dependency vào liveness nếu restart ứng dụng không thể khắc phục sự cố đó. Bảo vệ component details, giới hạn Actuator exposure, cấu hình management network và kiểm thử status/security mapping. Dùng health endpoint cho quyết định vận hành tức thời; dùng metrics, logs và traces để tìm nguyên nhân.

**Tài liệu tham khảo:**
- [Spring Boot — Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
- [Spring Boot — Health Information](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html#actuator.endpoints.health)
- [Spring Boot — Kubernetes Probes](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes)
- [Spring Boot — Actuator Security](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html#actuator.endpoints.security)
- [Spring Boot — Monitoring and Management](https://docs.spring.io/spring-boot/reference/actuator/)
- [Kubernetes — Liveness, Readiness and Startup Probes](https://kubernetes.io/docs/concepts/configuration/liveness-readiness-startup-probes/)

