# Bảo vệ endpoint quản trị và quyền thay đổi cấu hình

Circuit Breaker có thể được quan sát và can thiệp khi vận hành: đội trực có thể xem trạng thái, kiểm tra metrics, buộc một mạch chuyển sang `FORCED_OPEN` để ngừng gọi dependency, hoặc reset mạch sau khi sự cố đã được xử lý. Các thao tác này ảnh hưởng trực tiếp đến lưu lượng production. Nếu endpoint quản trị bị công khai hoặc cấp quyền quá rộng, người không có thẩm quyền có thể làm gián đoạn dịch vụ, mở lại traffic khi dependency chưa phục hồi hoặc thay đổi ngưỡng bảo vệ khiến hệ thống dễ gặp lỗi dây chuyền.

Với Spring Cloud CircuitBreaker và Resilience4j, cần tách ba quyền: **quan sát**, **điều khiển trạng thái runtime**, và **thay đổi cấu hình chính sách**. Mỗi quyền có phạm vi, quy trình phê duyệt và cách kiểm toán riêng. Actuator phù hợp để cung cấp health và metrics đã chọn; thao tác thay đổi trạng thái hoặc chính sách nên đi qua một giao diện quản trị nội bộ có xác thực, phân quyền và audit rõ ràng.

## Phân biệt endpoint quan sát, điều khiển và cấu hình

| Nhóm | Ví dụ thao tác | Rủi ro | Quyền nên cấp |
|---|---|---|---|
| Quan sát | Đọc health, metrics, trạng thái Circuit Breaker | Lộ thông tin nội bộ hoặc tình trạng dependency | `circuitbreaker.read` hoặc quyền vận hành chỉ đọc |
| Điều khiển runtime | Buộc `FORCED_OPEN`, reset mạch | Ngừng hoặc mở lại traffic ngay lập tức | `circuitbreaker.write` với audit và lý do thay đổi |
| Thay đổi chính sách | Sửa failure threshold, sliding window, timeout, số probe | Làm thay đổi hành vi bảo vệ trên nhiều request hoặc nhiều replica | Quyền quản trị cấu hình, quy trình review và rollout |

Không nên gộp cả ba nhóm thành một endpoint nhận JSON tùy ý. Một người chỉ cần xem dashboard không nên có quyền reset mạch; người được phép force-open một dependency trong sự cố cũng không nhất thiết được phép thay đổi cấu hình chung của toàn hệ thống.

## Chỉ expose những Actuator endpoint cần thiết

Spring Boot Actuator cung cấp các endpoint vận hành như `health`, `metrics` và `prometheus`. Chỉ expose các endpoint cần cho nền tảng quan sát. Không mở rộng toàn bộ endpoint quản trị ra mạng công khai, đặc biệt các endpoint có thể tiết lộ cấu hình, environment, bean graph hoặc thông tin nội bộ.

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,metrics,prometheus
  endpoint:
    health:
      show-details: when-authorized
      roles: OPS
```

`show-details: when-authorized` giới hạn thông tin health chi tiết cho người dùng có vai trò phù hợp. Endpoint health liveness/readiness có thể cần truy cập từ hệ thống điều phối; hãy chỉ cho phép đúng đường dẫn probe cần thiết. Endpoint `metrics` và `prometheus` thường nên nằm trong mạng quan sát nội bộ hoặc yêu cầu quyền đọc, vì tên metric và tag có thể tiết lộ tên dependency, topology hoặc trạng thái hệ thống.

Nếu dùng `management.server.port` riêng, cần cấu hình security cho management port và giới hạn bằng network policy/firewall. Tách port không tự tạo bảo mật; nếu port đó vẫn có thể truy cập từ Internet hoặc mạng người dùng, endpoint vẫn cần xác thực và phân quyền.

## Xác thực và phân quyền bằng Spring Security

Với API quản trị nội bộ, có thể dùng OAuth2 Resource Server và phân quyền theo scope. Ví dụ sau cho phép health probe đọc hai đường dẫn liveness/readiness, yêu cầu scope vận hành để đọc Actuator còn lại, và yêu cầu scope riêng để gọi API thay đổi trạng thái Circuit Breaker:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
class ManagementSecurityConfiguration {

    @Bean
    SecurityFilterChain applicationSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers(
                    "/actuator/health/liveness",
                    "/actuator/health/readiness").permitAll()
                .requestMatchers("/actuator/**")
                    .hasRole("OPS")
                .requestMatchers("/internal/admin/circuit-breakers/**")
                    .hasAuthority("SCOPE_circuitbreaker.write")
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 -> oauth2.jwt(Customizer.withDefaults()))
            .build();
    }
}
```

Đây là một chính sách minh họa cho ứng dụng dùng JWT bearer token. JWT cần được ánh xạ thành role `ROLE_OPS` cho các endpoint Actuator được bảo vệ và scope phù hợp cho API quản trị. Nếu cần endpoint đọc snapshot riêng, cấp `SCOPE_circuitbreaker.read` cho route GET và giữ `SCOPE_circuitbreaker.write` cho route POST thay đổi trạng thái. Không dùng chung một scope rộng như `admin` cho mọi thao tác nếu có thể tách quyền nhỏ hơn.

Trong hệ thống dùng session cookie cho giao diện quản trị trên trình duyệt, giữ CSRF protection cho các thao tác thay đổi trạng thái. Với API chỉ nhận bearer token không dựa vào cookie trình duyệt, chính sách CSRF có thể khác; hãy quyết định theo cơ chế xác thực thực tế thay vì tắt CSRF toàn cục một cách máy móc.

## Tách endpoint đọc khỏi endpoint thay đổi trạng thái

Endpoint đọc nên trả DTO chỉ chứa các trường cần cho vận hành: tên Circuit Breaker, trạng thái, số mẫu, failure rate, slow call rate và số lời gọi bị từ chối. Không trả trực tiếp object Resilience4j, cấu hình nội bộ đầy đủ, exception message chưa lọc hoặc thông tin xác thực.

Endpoint thay đổi trạng thái nên dùng HTTP `POST` với hành động được định nghĩa rõ, ví dụ `force-open` hoặc `reset`. Không dùng `GET` để thay đổi state. Yêu cầu một change/ticket ID và lý do thao tác để liên kết với hệ thống incident hoặc change management.

Ví dụ controller minh họa hai hành động runtime:

```java
import java.security.Principal;
import java.util.Set;

import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerRegistry;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/internal/admin/circuit-breakers")
class CircuitBreakerAdminController {

    private static final Set<String> MANAGED_NAMES = Set.of("catalog", "inventory");

    private final CircuitBreakerRegistry registry;
    private final CircuitBreakerAuditService auditService;

    CircuitBreakerAdminController(
            CircuitBreakerRegistry registry,
            CircuitBreakerAuditService auditService) {
        this.registry = registry;
        this.auditService = auditService;
    }

    @PostMapping("/{name}/force-open")
    @PreAuthorize("hasAuthority('SCOPE_circuitbreaker.write')")
    AdminActionResult forceOpen(
            @PathVariable String name,
            @RequestHeader("X-Change-Id") String changeId,
            @RequestHeader("X-Change-Reason") String reason,
            Principal principal) {
        CircuitBreaker breaker = requireManagedBreaker(name);
        String before = breaker.getState().name();

        auditService.recordRequested(
            principal.getName(), changeId, reason,
            name, before, "FORCE_OPEN");
        breaker.transitionToForcedOpenState();

        auditService.recordCompleted(
            principal.getName(), changeId, reason,
            name, before, breaker.getState().name(), "FORCE_OPEN");

        return new AdminActionResult(name, before,
            breaker.getState().name(), "FORCE_OPEN");
    }

    @PostMapping("/{name}/reset")
    @PreAuthorize("hasAuthority('SCOPE_circuitbreaker.write')")
    AdminActionResult reset(
            @PathVariable String name,
            @RequestHeader("X-Change-Id") String changeId,
            @RequestHeader("X-Change-Reason") String reason,
            Principal principal) {
        CircuitBreaker breaker = requireManagedBreaker(name);
        String before = breaker.getState().name();

        auditService.recordRequested(
            principal.getName(), changeId, reason,
            name, before, "RESET");
        breaker.reset();

        auditService.recordCompleted(
            principal.getName(), changeId, reason,
            name, before, breaker.getState().name(), "RESET");

        return new AdminActionResult(name, before,
            breaker.getState().name(), "RESET");
    }

    private CircuitBreaker requireManagedBreaker(String name) {
        if (!MANAGED_NAMES.contains(name)) {
            throw new IllegalArgumentException("Circuit Breaker không được quản lý: " + name);
        }

        return registry.getAllCircuitBreakers().stream()
            .filter(candidate -> candidate.getName().equals(name))
            .findFirst()
            .orElseThrow(() -> new IllegalArgumentException(
                "Không tìm thấy Circuit Breaker: " + name));
    }
}

record AdminActionResult(
    String name,
    String previousState,
    String currentState,
    String action
) {}
```

`CircuitBreakerAuditService` là adapter của ứng dụng ghi audit vào kho lưu trữ bền vững; `AdminActionResult` là DTO trả về cho caller. Trong code production, hãy kiểm tra `changeId` và `reason` không rỗng, giới hạn độ dài, xác thực định dạng và xử lý lỗi ghi audit. Nếu audit bắt buộc theo chính sách tổ chức, không báo thao tác thành công trước khi sự kiện audit được ghi bền vững.

Hai phương thức audit trong ví dụ tách bản ghi yêu cầu và kết quả: `recordRequested(...)` phải ghi bền vững ý định trước khi thay đổi state; `recordCompleted(...)` ghi trạng thái sau thao tác. Nếu thao tác lỗi giữa hai bước, bản ghi yêu cầu còn lại giúp đội vận hành phát hiện một hành động chưa có kết quả xác nhận và điều tra tiếp.

Ví dụ dùng allowlist tên mạch để caller không thể tạo hoặc điều khiển tùy ý một Circuit Breaker khác. `getAllCircuitBreakers()` được dùng để tìm instance hiện có; tránh gọi `registry.circuitBreaker(name)` trong endpoint quản trị chỉ để kiểm tra, vì thao tác đó có thể tạo một instance mới nếu tên chưa tồn tại.

Registry được inject vào controller phải là registry thực sự được backend/factory của ứng dụng sử dụng. Nếu controller đọc một registry khác, nó có thể điều khiển một instance không nhận traffic production. Hãy xác minh wiring của backend và dùng cùng nguồn registry ở cả factory lẫn adapter quản trị.

## Hiểu đúng tác động của force-open và reset

`transitionToForcedOpenState()` buộc mạch vào `FORCED_OPEN`; lời gọi mới bị từ chối cho đến khi có thao tác chuyển trạng thái khác. Đây là biện pháp vận hành để ngừng traffic đến dependency trong tình huống cần cô lập khẩn cấp. Nó không sửa dependency và không chứng minh dependency đã phục hồi.

`reset()` đưa Circuit Breaker về trạng thái ban đầu và xóa các thống kê runtime của instance. Vì vậy, reset có thể làm mạch bắt đầu nhận traffic trở lại trong khi sliding window chưa có mẫu mới. Nếu dependency vẫn lỗi, mạch phải thu thập đủ mẫu mới trước khi có thể mở lại theo ngưỡng; trong khoảng đó hệ thống có thể gửi thêm request lỗi.

Không reset chỉ vì dashboard đã hết báo động hoặc vì một khoảng thời gian đã trôi qua. Trước khi reset, hãy kiểm tra dependency bằng canary hoặc health check phù hợp, xem latency và tỷ lệ lỗi, xác nhận connection pool và downstream đã ổn định, rồi mở lại traffic theo kế hoạch. Nếu chỉ cần bỏ trạng thái `FORCED_OPEN`, hãy chọn thao tác chuyển state phù hợp với phiên bản Resilience4j đang dùng và hiểu rõ ảnh hưởng lên metrics; đừng mặc định mọi thao tác chuyển về `CLOSED` đều tương đương `reset()`.

## Một thao tác quản trị chỉ tác động đến replica nhận request

Resilience4j giữ state Circuit Breaker trong bộ nhớ của tiến trình. Nếu API quản trị được gọi qua load balancer và request đến replica A, thao tác `force-open` hoặc `reset` trong ví dụ chỉ tác động đến instance ở replica A. Các replica B và C có state riêng và không tự nhận thay đổi đó.

Điều này cần được thể hiện rõ trong API và quy trình:

- Trả về instance/pod identity cùng tên Circuit Breaker đã thay đổi.
- Nếu mục tiêu là toàn deployment, management plane phải fan-out đến từng replica đã xác định và thu kết quả riêng; không gửi một request qua load balancer rồi coi đó là thao tác toàn cụm.
- Theo dõi replica mới khởi động hoặc replica scale out trong lúc sự cố; chúng có thể bắt đầu với Circuit Breaker `CLOSED`.
- Nếu cần chặn traffic toàn cụm ngay lập tức, cân nhắc gateway, service mesh, routing policy hoặc admission control có phạm vi toàn cụm thay vì dựa vào một state cục bộ.
- Khi fan-out, giới hạn concurrency, timeout từng replica và ghi nhận replica không phản hồi; tránh tạo một đợt quản trị đồng thời làm quá tải control plane.

Không nên giả định metrics tổng hợp từ Prometheus có nghĩa state runtime đã được đồng bộ. Hệ thống quan sát có thể gom số liệu của nhiều replica, trong khi mỗi Circuit Breaker vẫn ra quyết định riêng.

## Thay đổi cấu hình chính sách có kiểm soát

Các thuộc tính như `slidingWindowSize`, `minimumNumberOfCalls`, `failureRateThreshold`, `slowCallDurationThreshold`, `waitDurationInOpenState` và `permittedNumberOfCallsInHalfOpenState` là chính sách bảo vệ. Thay đổi chúng có thể làm mạch mở sớm hơn, muộn hơn, cho phép nhiều probe hơn hoặc giữ traffic bị chặn lâu hơn.

Với cấu hình khai báo trong `application.yml`, một quy trình an toàn là:

1. Thay đổi cấu hình trong repository hoặc nguồn cấu hình được quản lý.
2. Review giá trị mới, phạm vi instance, tác động tới traffic và khả năng rollback.
3. Kiểm tra cú pháp, giới hạn hợp lệ và tương thích phiên bản trước khi triển khai.
4. Rollout có kiểm soát, ưu tiên canary hoặc một nhóm replica nhỏ.
5. Theo dõi state, failure rate, slow call rate, not-permitted calls, retry và fallback sau khi thay đổi.
6. Nếu kết quả xấu đi, rollback về phiên bản cấu hình đã biết là an toàn và xác nhận các replica đã áp dụng lại.

Không giả định việc sửa file YAML hoặc gọi một endpoint refresh bất kỳ sẽ cập nhật cấu hình của các Circuit Breaker object đang tồn tại. `CircuitBreakerConfig` là cấu hình được dùng khi instance được tạo; khả năng refresh và tái tạo instance phụ thuộc phiên bản, cơ chế Spring Cloud Config và cách factory/registry được tích hợp. Hãy kiểm thử rõ hành vi reload trong môi trường staging. Nếu không có cơ chế dynamic reconfiguration được xác nhận, rolling restart có kiểm soát là cách dễ dự đoán hơn để áp dụng cấu hình mới.

Nếu sản phẩm thật sự cần giao diện chỉnh ngưỡng runtime, không nhận trực tiếp một object cấu hình tùy ý. Hãy định nghĩa DTO có allowlist trường, giới hạn min/max, kiểu dữ liệu rõ, version cấu hình, người yêu cầu, change ID và thời hạn áp dụng. Sau khi xác thực, hệ thống phải cập nhật nguồn cấu hình có thẩm quyền, áp dụng thay đổi cho đúng instance/replica theo một cơ chế đã kiểm thử, xác minh cấu hình hiệu lực và hỗ trợ rollback. Nếu chỉ thay đổi một object trong bộ nhớ mà không cập nhật nguồn cấu hình bền vững, thay đổi sẽ mất khi restart và các replica có thể chạy chính sách khác nhau.

## Quyền thay đổi cấu hình và nguyên tắc least privilege

Nên chia vai trò vận hành theo trách nhiệm thực tế:

| Vai trò | Quyền phù hợp | Ví dụ |
|---|---|---|
| Observer | Đọc dashboard, health và metrics đã expose | Xem mạch `catalog` đang `OPEN` |
| On-call operator | Thực hiện thao tác runtime đã được phê duyệt | Force-open một mạch để cô lập dependency |
| Configuration maintainer | Đề xuất và review thay đổi chính sách | Điều chỉnh failure threshold qua pull request |
| Platform administrator | Quản lý security, management network và quyền hệ thống | Cấp scope, cấu hình management port |

Không cấp quyền ghi chỉ vì người dùng cần đọc metrics. Dùng token ngắn hạn, xác thực đa yếu tố ở hệ thống cấp quyền khi phù hợp, mTLS cho workload nội bộ và network policy để hạn chế nơi có thể gọi management endpoint. Không đặt endpoint quản trị sau cùng host/path công khai mà không có lớp bảo vệ tương đương các API nhạy cảm khác.

Nếu cần phê duyệt hai người cho hành động rủi ro cao như reset mạch đang `FORCED_OPEN` hoặc thay đổi threshold diện rộng, hãy thực hiện ở control plane hoặc change management workflow. Endpoint của service chỉ nên thực thi lệnh đã được xác thực và cấp quyền, không tự coi một header `approved=true` do caller gửi là bằng chứng phê duyệt.

## Audit log cho mọi thay đổi

Một sự kiện audit tối thiểu nên ghi:

- Thời điểm và định danh người hoặc workload thực hiện.
- Hành động: `FORCE_OPEN`, `RESET` hoặc thay đổi cấu hình cụ thể.
- Tên Circuit Breaker, service, môi trường và replica/pod đích.
- Trạng thái trước và sau thao tác.
- Giá trị cấu hình trước/sau nếu là thay đổi chính sách.
- Change ID, incident ID và lý do đã được xác thực.
- Kết quả thực thi, lỗi nếu có và mã tương quan của request quản trị.

Audit log cần được lưu ở nơi bền vững, có quyền ghi hạn chế và chống sửa/xóa tùy yêu cầu tổ chức. Không ghi bearer token, cookie, secret, toàn bộ request body hoặc exception chứa thông tin nhạy cảm. Log ứng dụng thông thường hữu ích cho debug nhưng không thay thế audit trail có kiểm soát truy cập.

## Quy trình vận hành khi cần cô lập dependency

Khi dependency đang gây lỗi dây chuyền và đội trực cần can thiệp, có thể dùng trình tự sau:

1. **Quan sát:** đọc state, failure/slow call rate, số lời gọi bị từ chối và latency theo từng replica.
2. **Xác định phạm vi:** xác nhận đúng dependency, Circuit Breaker name, môi trường và các replica chịu ảnh hưởng.
3. **Cô lập:** nếu cần ngừng gọi ngay, thực hiện `FORCED_OPEN` theo quyền và change/incident ID; nếu cần toàn cụm, xác nhận kết quả trên từng replica hoặc dùng lớp routing chung.
4. **Điều tra:** kiểm tra dependency, timeout client, connection pool, retry, Bulkhead và nguồn fallback. Force-open chỉ chặn lời gọi mới, không tự hủy các request đang chạy.
5. **Khôi phục:** xác minh dependency đã khỏe bằng canary và số liệu thực tế; đánh giá latency, lỗi và năng lực tiếp nhận traffic.
6. **Mở lại có kiểm soát:** reset hoặc chuyển trạng thái theo quy trình được hỗ trợ, bắt đầu với phạm vi nhỏ nếu có thể và theo dõi probe/traffic.
7. **Đóng sự cố:** lưu audit, ghi nhận thay đổi, kết quả và bài học; rollback cấu hình nếu chính sách mới gây tác dụng phụ.

Trong lúc vận hành, fallback cần được quan sát riêng. Một API có thể vẫn trả response từ cache khi Circuit Breaker `OPEN`; điều đó giúp giữ availability nhưng không có nghĩa dependency đã phục hồi. Không dùng tỷ lệ HTTP 200 của service làm tiêu chí duy nhất để reset mạch.

## Những lỗi bảo mật và vận hành thường gặp

- **Expose toàn bộ Actuator:** lộ environment, cấu hình hoặc thông tin nội bộ. Chỉ expose endpoint cần thiết và bảo vệ bằng scope/network policy.
- **Dùng một quyền admin cho mọi thứ:** người chỉ cần đọc metrics có thể reset mạch. Tách quyền read, runtime write và config change.
- **Dùng GET để thay đổi state:** gây tác động ngoài ý muốn từ cache, crawler hoặc prefetch. Dùng POST có xác thực và audit.
- **Cho phép tên Circuit Breaker tùy ý:** có thể tạo instance ngoài dự kiến hoặc điều khiển nhầm dependency. Dùng allowlist và tìm instance đang tồn tại.
- **Reset ngay khi hết thời gian chờ:** dependency có thể chưa phục hồi; reset làm mạch nhận traffic lại và xóa thống kê. Kiểm tra canary và năng lực trước.
- **Gọi qua load balancer nhưng tưởng đã tác động toàn cụm:** thao tác chỉ chạm replica nhận request. Xác định và xác nhận từng target.
- **Cho rằng refresh config luôn cập nhật instance hiện tại:** cấu hình có thể chỉ được dùng khi tạo instance. Kiểm thử reload hoặc rollout theo cách đã xác nhận.
- **Không ghi audit:** sau sự cố không thể biết ai thay đổi gì, khi nào và vì sao. Ghi audit bền vững cho mọi hành động write.
- **Để fallback che giấu dependency lỗi:** dashboard chỉ thấy response thành công. Theo dõi fallback rate và nguồn dữ liệu trả về.

## Checklist trước khi đưa endpoint quản trị vào production

| Hạng mục | Điều kiện cần xác nhận |
|---|---|
| Network | Management endpoint chỉ truy cập từ mạng/workload được phép |
| Authentication | Dùng danh tính đã xác thực, token/certificate có vòng đời phù hợp |
| Authorization | Tách quyền đọc, runtime control và config change |
| Exposure | Chỉ expose Actuator endpoint cần thiết |
| API design | GET chỉ đọc; POST cho thao tác thay đổi; tên mạch theo allowlist |
| Validation | Change ID, lý do và dữ liệu cấu hình được xác thực/giới hạn |
| Audit | Ghi người thực hiện, target, hành động, before/after và kết quả |
| Replica scope | Hiển thị rõ thao tác cục bộ hay toàn deployment |
| Recovery | Có canary, kế hoạch mở lại traffic và rollback |
| Observability | Theo dõi state, failure/slow rate, fallback và not-permitted calls |

Endpoint quản trị an toàn cần cho phép đội vận hành nhìn thấy đúng tình trạng, thực hiện đúng hành động trong phạm vi được cấp và truy vết đầy đủ mọi thay đổi. Khi tách quyền quan sát khỏi quyền điều khiển, giữ cấu hình trong quy trình có review và hiểu rõ state cục bộ của từng replica, Circuit Breaker có thể được vận hành chủ động mà không biến chính giao diện quản trị thành một nguồn gây gián đoạn mới.
