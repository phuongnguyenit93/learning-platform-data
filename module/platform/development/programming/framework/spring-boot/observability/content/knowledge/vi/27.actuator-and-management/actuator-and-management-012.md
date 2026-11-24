# Shutdown endpoint

Trong chương **Actuator và management** của mô-đun **SPRING_BOOT_OBSERVABILITY**, Shutdown endpoint là endpoint quản trị cho phép yêu cầu Spring Boot application dừng bằng cách đóng ApplicationContext. Nó hữu ích trong một số quy trình vận hành có kiểm soát, nhưng cũng có thể làm một instance ngừng phục vụ ngay khi endpoint bị gọi. Vì vậy, endpoint này thường không được bật hoặc expose mặc định và cần được xem như một thao tác đặc quyền.

Cần phân biệt **Shutdown endpoint** với **graceful shutdown** của web server. Endpoint phát lệnh đóng ứng dụng; graceful shutdown là cơ chế để server ngừng nhận request mới và cho request đang xử lý thời gian hoàn tất trong giới hạn cấu hình. Chỉ bật endpoint không tự bảo đảm traffic đã được drain khỏi load balancer, scheduler đã dừng đúng cách hoặc mọi công việc nền đã hoàn tất. Các bước phối hợp với orchestration platform, readiness và lifecycle của ứng dụng vẫn cần được thiết kế.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:
1. Giải thích Shutdown endpoint thực hiện thao tác gì trong Spring Boot.
2. Phân biệt enablement, HTTP exposure và authorization của endpoint.
3. Hiểu vì sao Shutdown endpoint cần được bảo vệ như thao tác quản trị đặc quyền.
4. Gửi yêu cầu shutdown bằng HTTP POST theo cấu hình phù hợp.
5. Cấu hình graceful shutdown cho embedded web server.
6. Hiểu vai trò của spring.lifecycle.timeout-per-shutdown-phase.
7. Phối hợp readiness, load balancer và orchestration trước khi dừng instance.
8. Đánh giá ảnh hưởng tới in-flight requests, scheduled tasks và message consumers.
9. Viết integration tests cho endpoint, security và shutdown lifecycle.
10. Xây dựng runbook có kiểm soát để dừng một instance mà không làm gián đoạn toàn hệ thống.

## 2. Shutdown endpoint là gì?

Spring Boot Actuator cung cấp endpoint shutdown để yêu cầu đóng ApplicationContext của ứng dụng. Khi được bật và expose qua HTTP, endpoint nhận request POST và kích hoạt quá trình shutdown của context.

Endpoint này có những đặc điểm quan trọng:
- Nó là thao tác thay đổi trạng thái ứng dụng, không phải endpoint đọc thông tin.
- Nó thường bị disable theo mặc định.
- Cần enable endpoint và expose qua HTTP trước khi gọi được.
- Security policy phải giới hạn caller có quyền thực hiện.
- Sau khi shutdown thành công, instance sẽ không tiếp tục phục vụ requests mới.

Ví dụ lời gọi HTTP:

~~~http
POST /actuator/shutdown
~~~

Đường dẫn thực tế phụ thuộc management base path, management port và cấu hình web exposure. Nếu base path đổi thành /manage, endpoint tương ứng là /manage/shutdown.

Không gửi POST này tới toàn bộ replicas hoặc service load-balanced endpoint nếu mục tiêu chỉ là dừng một instance. Xác định rõ instance đích trước khi thực hiện.

## 3. Enablement, exposure và authorization

Ba lớp cần phân biệt:

| Lớp | Câu hỏi | Cấu hình/kiểm soát |
| --- | --- | --- |
| Enablement | Endpoint có được tạo và cho phép hoạt động không? | management.endpoint.shutdown.enabled |
| Exposure | Endpoint có được truy cập qua HTTP/JMX không? | management.endpoints.web.exposure hoặc JMX exposure |
| Authorization | Ai được phép gửi yêu cầu shutdown? | Spring Security role, network policy và operator identity |

Một endpoint enabled không có nghĩa đã được exposed. Một endpoint exposed cũng không đồng nghĩa anonymous caller được phép thực hiện. Trong production, cần kiểm soát đồng thời cả ba lớp.

Ví dụ bật endpoint và expose riêng:

~~~yaml
management:
  endpoint:
    shutdown:
      enabled: true
  endpoints:
    web:
      exposure:
        include: health,info,shutdown
~~~

Cấu hình này chỉ minh họa enablement/exposure. Nó chưa thay thế authentication, authorization hoặc network isolation. Không dùng include wildcard chỉ để bật Shutdown; danh sách exposure nên chỉ chứa endpoints thực sự cần thiết.

Nếu endpoint không được enable, request có thể trả 404 hoặc không xuất hiện trong endpoint mappings tùy version/configuration. Nếu đã enable nhưng chưa expose, URL HTTP vẫn không truy cập được.

## 4. Gọi Shutdown endpoint

Khi endpoint đã enabled, exposed và caller được authorize, gửi HTTP POST:

~~~bash
curl -X POST http://localhost:8080/actuator/shutdown
~~~

Nếu dùng management port riêng:

~~~bash
curl -X POST http://localhost:9091/actuator/shutdown
~~~

Ví dụ response minh họa:

~~~json
{
  "message": "Shutting down, bye..."
}
~~~

Response cụ thể có thể khác theo Spring Boot version. Sau khi request được chấp nhận, ApplicationContext bắt đầu đóng và kết nối HTTP có thể kết thúc khi server shutdown. Không dùng response body làm bằng chứng duy nhất rằng mọi công việc đã drain hoặc mọi resource đã đóng thành công.

Nếu dùng authentication, truyền credential qua cơ chế an toàn của môi trường vận hành. Tránh ghi token vào shell history, URL, process arguments hoặc log của automation.

## 5. Shutdown endpoint và graceful shutdown

Hai cơ chế có liên quan nhưng có mục đích khác nhau:
- **Shutdown endpoint**: phát lệnh đóng Spring ApplicationContext.
- **Graceful web server shutdown**: ngừng nhận request mới và cho request đang xử lý thời gian hoàn tất trước khi server dừng.

Có thể cấu hình graceful shutdown:

~~~yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 30s
~~~

server.shutdown: graceful yêu cầu embedded server hỗ trợ graceful shutdown. spring.lifecycle.timeout-per-shutdown-phase đặt thời gian chờ tối đa cho mỗi lifecycle shutdown phase, không phải một deadline tổng thể duy nhất cho mọi resource trong toàn ứng dụng.

Khi context đóng, các lifecycle-managed components được yêu cầu dừng theo phase. Web server có thể ngừng nhận request mới và chờ request đang xử lý trong thời hạn. Nếu timeout hết, các hoạt động còn lại có thể bị kết thúc. Kiểm tra behavior theo server implementation và Spring Boot version.

Graceful shutdown không bảo đảm:
- Message đang consume được commit nếu handler không hỗ trợ graceful stop.
- Scheduled task dài sẽ hoàn tất nếu không có lifecycle coordination.
- Database transaction được giữ vô hạn.
- Request vượt quá timeout sẽ luôn hoàn tất.
- Load balancer đã ngừng gửi traffic trước khi shutdown bắt đầu.

## 6. Readiness và traffic draining

Trong môi trường có load balancer hoặc Kubernetes, nên đưa instance ra khỏi traffic trước khi đóng context.

~~~mermaid
sequenceDiagram
    participant Ops as Operator / Orchestrator
    participant LB as Load balancer
    participant App as Spring Boot instance
    participant Work as In-flight work

    Ops->>App: Mark instance unready
    App-->>Ops: Readiness DOWN
    Ops->>LB: Remove instance from targets
    LB-->>App: Stop routing new requests
    Note over App,Work: Wait for propagation and in-flight work
    Ops->>App: Initiate shutdown
    App->>Work: Stop accepting new work / drain
    Work-->>App: Complete or reach timeout
    App-->>Ops: Context closed
~~~

Readiness DOWN không tự động bảo đảm load balancer đã cập nhật target list. Cần chờ propagation/drain interval theo platform và kiểm tra thực tế. Với Kubernetes, readiness probe khiến pod không còn được xem là ready cho Service endpoints sau khi control plane cập nhật; quá trình cập nhật không tức thời.

Không dùng liveness DOWN như cách drain traffic. Liveness failure có thể khiến platform restart container, tạo vòng lặp restart hoặc kill process trước khi drain hoàn tất.

Nếu cần một thao tác chuẩn hóa để drain, hãy điều phối readiness state, load balancer deregistration và shutdown theo một quy trình rõ ràng. Shutdown endpoint chỉ là một trong các bước cuối.

## 7. Background tasks và message consumers

Ứng dụng có thể có scheduled tasks, @Async executors, message listeners hoặc batch jobs đang chạy khi shutdown bắt đầu. Graceful web server shutdown không tự xử lý toàn bộ các workload này.

Cần xem xét riêng:
- **Scheduled tasks**: không bắt đầu lần chạy mới khi ứng dụng đang dừng; xác định xử lý lần đang chạy và timeout.
- **Message consumers**: dừng nhận message mới, hoàn tất hoặc rollback message hiện tại, commit/ack theo semantics của broker.
- **@Async executors**: cấu hình wait-for-tasks-to-complete và await termination phù hợp.
- **Batch jobs**: lưu checkpoint hoặc trạng thái để resume an toàn.
- **Database transactions**: bảo đảm rollback khi execution bị hủy; không giữ connection vô thời hạn.
- **External locks**: release lock đúng lifecycle hoặc dựa trên lease/TTL để phục hồi khi process bị kill.

Task cần idempotency nếu có thể bị dừng giữa chừng và chạy lại sau khi instance khởi động. Không giả định shutdown signal luôn đến trước khi container bị terminate cưỡng bức.

## 8. Bảo vệ Shutdown endpoint

Shutdown endpoint có thể gây denial of service nếu caller không phù hợp có thể gọi nó. Các biện pháp bảo vệ:
1. Không expose endpoint nếu không có use case vận hành rõ.
2. Nếu cần dùng, chỉ expose trên management interface/port riêng.
3. Dùng authentication mạnh và role chuyên biệt, ví dụ ROLE_INSTANCE_ADMIN.
4. Giới hạn network bằng firewall, private network hoặc Kubernetes NetworkPolicy.
5. Audit người gọi, instance đích, thời điểm và kết quả thao tác.
6. Không đặt endpoint sau public ingress thông thường.
7. Không nhúng credential trong URL hoặc script có log command line.
8. Có approval/change procedure ở hệ thống vận hành nếu môi trường yêu cầu.

Ví dụ SecurityFilterChain minh họa:

~~~java
@Configuration(proxyBeanMethods = false)
class ManagementSecurityConfiguration {

    @Bean
    SecurityFilterChain actuatorSecurity(HttpSecurity http) throws Exception {
        return http
                .securityMatcher(EndpointRequest.toAnyEndpoint())
                .authorizeHttpRequests(authorize -> authorize
                        .requestMatchers(EndpointRequest.to("health"))
                        .permitAll()
                        .requestMatchers(EndpointRequest.to("shutdown"))
                        .hasRole("INSTANCE_ADMIN")
                        .anyRequest()
                        .hasRole("OPS"))
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}
~~~

Đây là ví dụ minh họa. Nếu ứng dụng có nhiều SecurityFilterChains, kiểm tra matcher/order để endpoint shutdown không bị chain rộng hơn cho phép anonymous access. Role phải được map từ identity provider đáng tin cậy.

### Management port riêng

~~~yaml
management:
  server:
    port: 9091
    address: 127.0.0.1
~~~

Bind loopback chỉ phù hợp khi caller quản trị chạy cùng network namespace hoặc có proxy nội bộ được kiểm soát. Trong container, operator từ node khác thường không thể truy cập loopback bên trong container. Chọn bind address và network policy theo topology thực tế; management port riêng không tự động tạo security boundary đầy đủ.

## 9. Timeout và lifecycle phases

Khi đóng ApplicationContext, Spring lifecycle-managed beans được stop theo phases. spring.lifecycle.timeout-per-shutdown-phase xác định thời gian chờ cho mỗi phase. Nếu có nhiều phases, tổng thời gian shutdown có thể dài hơn giá trị này.

~~~yaml
spring:
  lifecycle:
    timeout-per-shutdown-phase: 45s
~~~

Chọn timeout dựa trên P99 duration của request đang xử lý, thời gian drain từ load balancer/orchestrator, thời gian dừng message listener, thời gian chờ executor tasks, thời gian commit/rollback database transactions và grace period mà platform cho phép trước kill signal.

Ví dụ, nếu platform chỉ cho 30 giây trước SIGKILL nhưng ứng dụng cần 45 giây mỗi shutdown phase, process có thể bị kill trước khi lifecycle hoàn tất. Đồng bộ timeout ứng dụng với terminationGracePeriodSeconds hoặc giới hạn tương đương của platform.

Không đặt timeout vô hạn để tránh mất request. Một task bị treo có thể giữ shutdown mãi và làm deployment rollout không hoàn tất.

## 10. Shutdown hooks và signal từ operating system

Spring Boot thường tích hợp với JVM shutdown hook để đóng ApplicationContext khi process nhận shutdown signal phù hợp. Container orchestrators thường gửi SIGTERM trước, chờ grace period, rồi có thể gửi SIGKILL nếu process chưa thoát.

Shutdown endpoint và OS signal có thể cùng dẫn đến đóng context, nhưng điểm khởi đầu khác nhau:
- Endpoint được gọi qua HTTP bởi operator/automation.
- SIGTERM được gửi bởi process manager/orchestrator.
- JVM shutdown hook điều phối context close trong process lifecycle.

Không gọi System.exit() như cách thay thế thông thường cho Spring lifecycle. Việc đó có thể bỏ qua trình tự quản lý resource mà framework cung cấp nếu thực hiện sai. Để đóng ứng dụng có chủ đích trong code, ưu tiên lifecycle/context APIs phù hợp và hiểu rõ ai sở hữu ApplicationContext.

## 11. Observability cho chính quá trình shutdown

Shutdown là một hoạt động vận hành cần được ghi nhận. Có thể dùng logs và metrics để trả lời:
- Ai hoặc thành phần nào khởi tạo shutdown?
- Instance nào được yêu cầu dừng?
- Readiness đã chuyển DOWN chưa?
- Có bao nhiêu request/task đang chạy?
- Lifecycle phase nào mất nhiều thời gian?
- Có component nào timeout hoặc không đóng được?
- Process kết thúc sạch hay bị orchestrator kill?

Log event nên chứa service/instance identity, reason category, trigger source và timestamp. Không ghi credential hoặc raw authorization headers.

Ví dụ log event:

~~~java
log.atInfo()
        .addKeyValue("event.name", "application.shutdown.requested")
        .addKeyValue("trigger.source", "operator")
        .addKeyValue("shutdown.mode", "graceful")
        .log("Application shutdown requested");
~~~

Có thể dùng ApplicationListener cho lifecycle events như ContextClosedEvent để ghi nhận thời điểm context bắt đầu đóng. Các event này không phải bằng chứng mọi bean đã dừng xong; theo dõi kết quả của từng lifecycle component và process exit.

Không cố export một trace mới tới backend sau khi exporter đã bắt đầu shutdown. Nếu cần audit, dùng log/metric pipeline có flush/close ordering rõ ràng và kiểm tra exporter shutdown timeout.

## 12. Kiểm thử Shutdown endpoint

Kiểm thử endpoint cần được cô lập vì request hợp lệ có thể đóng ApplicationContext của test. Có thể kiểm tra enablement/exposure/security trong test context riêng hoặc dùng integration test khởi động process độc lập.

Các nhóm kiểm thử:
1. Endpoint không hoạt động khi chưa enabled.
2. Endpoint không truy cập được qua HTTP nếu chưa exposed.
3. Anonymous caller bị từ chối.
4. Role không đủ quyền bị từ chối.
5. Role quản trị phù hợp có thể gửi POST trong môi trường test cô lập.
6. Graceful shutdown dừng nhận request mới theo server semantics.
7. In-flight request được phép hoàn tất trong timeout đã cấu hình.
8. Lifecycle-managed beans nhận callback stop đúng.
9. Scheduled/message consumers dừng nhận workload mới.
10. Process thoát trước platform grace period trong kịch bản bình thường.

Ví dụ kiểm tra security/exposure bằng test context không kích hoạt shutdown thật:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class ShutdownEndpointSecurityTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    @WithAnonymousUser
    void anonymousCannotShutdown() throws Exception {
        mockMvc.perform(post("/actuator/shutdown"))
                .andExpect(status().isUnauthorized());
    }
}
~~~

Status thực tế có thể là 401 hoặc 403 tùy authentication/authorization setup. Test cần endpoint exposure/security config phù hợp và không gửi request được authorize tới ApplicationContext dùng chung của test suite.

## 13. Troubleshooting

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| /actuator/shutdown trả 404 | Endpoint chưa enabled hoặc chưa expose; base path khác. | Kiểm tra enablement, exposure và base path. |
| POST trả 401 | Caller chưa authenticate. | Kiểm tra credentials/identity provider. |
| POST trả 403 | Caller authenticated nhưng thiếu role. | Kiểm tra role mapping và SecurityFilterChain. |
| POST được chấp nhận nhưng process chưa thoát ngay | Lifecycle phases hoặc in-flight work đang chờ. | Kiểm tra shutdown logs, timeout và bean lifecycle. |
| Request đang xử lý bị ngắt | Graceful shutdown chưa bật hoặc timeout quá ngắn. | Kiểm tra server.shutdown và timeout-per-shutdown-phase. |
| Pod bị SIGKILL trước khi shutdown xong | Platform grace period ngắn hơn thời gian cần thiết. | Đồng bộ application timeout và orchestrator termination grace. |
| Instance vẫn nhận traffic khi shutdown bắt đầu | Chưa drain readiness/load balancer trước endpoint call. | Kiểm tra deregistration và propagation delay. |
| Scheduled task bị dừng giữa chừng | Task không có graceful lifecycle/checkpoint. | Thiết kế cancellation, checkpoint và idempotency. |
| Message bị xử lý lặp | Ack/commit hoặc shutdown listener semantics không phù hợp. | Kiểm tra broker listener stop/ack/rollback behavior. |
| Shutdown không kết thúc | Bean stop callback bị treo hoặc executor chờ vô hạn. | Tìm lifecycle phase chậm và giới hạn wait time. |

## 14. Runbook: dừng một Spring Boot instance có kiểm soát

1. Xác định chính xác instance/pod/container cần dừng; không dùng service-wide load-balanced address.
2. Xác nhận có đủ replicas/capacity để tiếp tục phục vụ traffic.
3. Kiểm tra alert, active requests, queue backlog và scheduled/batch workload.
4. Chuyển instance sang not-ready hoặc deregister khỏi load balancer.
5. Chờ readiness propagation và connection draining theo platform.
6. Xác minh request mới không còn được route tới instance.
7. Gửi POST /actuator/shutdown qua management network với identity được phép, hoặc dùng lifecycle signal của orchestrator theo quy trình.
8. Theo dõi logs cho ContextClosedEvent, graceful server shutdown và component stop.
9. Xác minh in-flight requests/tasks hoàn tất hoặc kết thúc theo timeout policy.
10. Xác nhận process/container exit code và không bị SIGKILL.
11. Kiểm tra replica/service capacity sau khi instance dừng.
12. Ghi audit event và cập nhật incident/change record nếu áp dụng.

Nếu shutdown endpoint không cần cho vận hành thường ngày, giữ endpoint disabled và dùng orchestration/lifecycle signal tiêu chuẩn để dừng process.

## 15. Bài tập tự kiểm tra

### Bài 1 — Endpoint có sẵn nhưng trả 404

Bạn đã thêm Actuator nhưng POST /actuator/shutdown trả 404. Cần kiểm tra những gì?

**Đáp án:** Shutdown endpoint có được enable không, có được expose qua HTTP không và base path/management port có đúng không. Có Actuator starter không đồng nghĩa endpoint shutdown tự động public.

### Bài 2 — GET hay POST?

Có nên dùng GET /actuator/shutdown để kiểm tra endpoint không?

**Đáp án:** Không. Shutdown là thao tác thay đổi trạng thái và sử dụng POST. Không dùng GET cho thao tác destructive.

### Bài 3 — Graceful shutdown

Đã bật Shutdown endpoint nhưng request đang xử lý bị ngắt ngay. Cần xem cấu hình nào?

**Đáp án:** Kiểm tra server.shutdown=graceful, spring.lifecycle.timeout-per-shutdown-phase, web server implementation và platform grace period.

### Bài 4 — Kubernetes rollout

Một pod nhận shutdown trong khi vẫn đang Ready và load balancer tiếp tục gửi request. Thiếu bước nào?

**Đáp án:** Cần readiness transition/deregistration và chờ traffic draining trước khi yêu cầu shutdown. Endpoint không tự phối hợp toàn bộ load balancer.

### Bài 5 — Scheduled task

Một scheduled task đang chạy khi ApplicationContext đóng. Graceful web server shutdown có bảo đảm task hoàn tất không?

**Đáp án:** Không. Cần quản lý scheduler/executor lifecycle, cancellation, timeout và checkpoint/idempotency riêng.

### Bài 6 — Timeout của platform

Application cần 45 giây để dừng nhưng orchestrator chỉ chờ 20 giây trước SIGKILL. Điều gì có thể xảy ra?

**Đáp án:** Process bị kill trước khi lifecycle hoàn tất. Đồng bộ timeout-per-shutdown-phase và orchestrator grace period với thời gian drain thực tế.

## 16. Checklist triển khai

- [ ] Có use case vận hành rõ ràng cho Shutdown endpoint.
- [ ] Endpoint giữ disabled nếu không cần sử dụng.
- [ ] Nếu bật, chỉ expose qua management interface/network được kiểm soát.
- [ ] Authorization dùng role quản trị chuyên biệt.
- [ ] Thao tác dùng HTTP POST và xác định đúng instance đích.
- [ ] Không gọi shutdown qua public load-balanced service address.
- [ ] Graceful web server shutdown được cấu hình nếu cần.
- [ ] spring.lifecycle.timeout-per-shutdown-phase phù hợp với workload.
- [ ] Platform termination grace period dài hơn thời gian cần thiết.
- [ ] Readiness/deregistration và traffic drain hoàn tất trước shutdown.
- [ ] In-flight requests có giới hạn thời gian hợp lý.
- [ ] Scheduled tasks, message consumers và executors có stop semantics rõ.
- [ ] Batch/consumer work có checkpoint, ack/rollback và idempotency.
- [ ] Logs/audit ghi nhận trigger source và kết quả nhưng không chứa credentials.
- [ ] Integration tests bao phủ enablement, exposure, authorization và lifecycle.
- [ ] Runbook xác minh process exit sạch, capacity và replica health sau shutdown.

**Ghi nhớ:** Shutdown endpoint yêu cầu Spring Boot đóng ApplicationContext; graceful shutdown giúp web server ngừng nhận request mới và chờ công việc đang xử lý trong thời hạn. Trong production, cần drain traffic qua readiness/load balancer, bảo vệ endpoint bằng authorization và network policy, phối hợp scheduler/message consumers/executors, rồi đồng bộ timeout của ứng dụng với grace period của platform. Nếu không có nhu cầu quản trị cụ thể, giữ endpoint disabled.
