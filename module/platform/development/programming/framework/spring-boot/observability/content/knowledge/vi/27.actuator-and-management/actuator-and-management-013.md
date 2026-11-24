# Không public endpoint nhạy cảm trong Spring Boot

Không public endpoint nhạy cảm là nguyên tắc cấu hình Spring Boot Actuator sao cho các endpoint có thể tiết lộ dữ liệu nội bộ hoặc thay đổi trạng thái ứng dụng không thể truy cập từ mạng công khai. Những endpoint như env, configprops, heapdump, threaddump, beans, mappings, loggers và shutdown có thể hữu ích cho operator khi điều tra sự cố, nhưng cũng làm tăng đáng kể bề mặt tấn công nếu expose rộng.

Trong module **SPRING_BOOT_OBSERVABILITY**, Actuator hỗ trợ health checks, metrics và thao tác quản trị. Bài thuộc chương **Actuator và management**, tập trung vào phân loại endpoint nhạy cảm, allowlist exposure, disable endpoint không cần thiết, tách management network, authentication/authorization, kiểm soát health details, kiểm thử và quy trình xử lý sự cố.

## 1. Vì sao không public endpoint nhạy cảm?

Actuator endpoint có thể trả về dữ liệu nội bộ hoặc thực hiện thao tác có ảnh hưởng tới runtime. Nếu endpoint nhạy cảm được mở qua public ingress, attacker có thể thu thập thông tin phục vụ reconnaissance, tìm secrets bị cấu hình sai, tải dữ liệu trong memory hoặc thay đổi hành vi ứng dụng.

Rủi ro thường gặp:
- Lộ cấu hình, hostname, endpoint nội bộ và thông tin môi trường.
- Lộ credentials nếu secret redaction không đầy đủ.
- Lộ object graph, tokens hoặc dữ liệu cá nhân qua heap dump.
- Lộ stack traces, thread names và request context qua thread dump.
- Thay đổi log level để tăng khả năng thu thập dữ liệu nhạy cảm.
- Tắt ứng dụng nếu shutdown endpoint được bật và expose.
- Tiết lộ API mappings, bean graph và cấu trúc dependency.

Không public endpoint nhạy cảm không có nghĩa operator không bao giờ được sử dụng chúng. Truy cập cần đi qua management network và quyền quản trị có kiểm soát.

## 2. Phân loại endpoint theo mức độ nhạy cảm

| Endpoint | Dữ liệu/tác động | Chính sách khuyến nghị |
| --- | --- | --- |
| health | Trạng thái ứng dụng/dependencies | Có thể expose hẹp; giới hạn details |
| info | Thông tin service/build | Chỉ công bố field đã chọn |
| prometheus | Metrics nội bộ | Chỉ scraper/network tin cậy |
| metrics | Measurements và tags | Operator/monitoring |
| loggers | Đọc và đổi log level | Operator được cấp quyền |
| env | Environment/property sources | Không public; thường không expose |
| configprops | Bound configuration | Không public; thường không expose |
| heapdump | Snapshot heap có thể chứa secrets/PII | Chỉ quy trình chẩn đoán đặc biệt |
| threaddump | Stack traces và runtime context | Chỉ operator |
| beans | Danh sách bean và cấu trúc nội bộ | Không public |
| mappings | Request mappings/API surface | Không public |
| conditions | Auto-configuration details | Chỉ chẩn đoán nội bộ |
| shutdown | Dừng application context | Disable trừ khi có use case đặc biệt |

Mức nhạy cảm thực tế phụ thuộc dữ liệu endpoint trả về, cấu hình redaction, Spring Boot version và môi trường. Xem xét response thực tế thay vì chỉ dựa vào tên endpoint.

## 3. Dùng allowlist thay vì expose wildcard

Cấu hình web exposure nên liệt kê endpoint cần thiết:

```yaml
management:
  endpoints:
    web:
      exposure:
        include:
          - health
          - info
          - prometheus
```

Cấu hình trên chỉ minh họa allowlist. Endpoint prometheus cần registry tương ứng; nếu monitoring không dùng endpoint đó thì bỏ khỏi danh sách.

Tránh cấu hình production kiểu include wildcard rồi cố gắng exclude từng endpoint nhạy cảm. Khi nâng cấp Spring Boot, endpoint mới có thể xuất hiện và vô tình được công bố qua wildcard.

### 3.1. Exclude là lớp bổ sung

Có thể dùng exclude để chặn một số endpoint ngay cả khi include rộng:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: "*"
        exclude:
          - env
          - configprops
          - heapdump
          - threaddump
          - beans
          - mappings
          - shutdown
```

Đây là ví dụ cho môi trường lab hoặc tình huống cần giải thích precedence. Với production, allowlist include rõ ràng dễ kiểm soát hơn.

### 3.2. Quote wildcard trong YAML

Dấu * phải được đặt trong dấu nháy để tránh bị YAML hiểu là alias indicator:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: "*"
```

Không sử dụng wildcard trên public-facing application mà không có lý do và kiểm soát bổ sung.

## 4. Disable endpoint không cần thiết

Exposure quyết định endpoint nào được công bố qua transport. Enablement quyết định endpoint có được bật trong application context hay không. Endpoint không cần dùng nên được disable nếu version và endpoint hỗ trợ property đó.

Ví dụ disable shutdown:

```yaml
management:
  endpoint:
    shutdown:
      enabled: false
```

Có thể áp dụng cùng nguyên tắc cho endpoint khác bằng property management.endpoint.<id>.enabled khi endpoint/version hỗ trợ. Kiểm tra configuration metadata của Spring Boot đang dùng.

Không giả định disable một endpoint sẽ tự bảo vệ các endpoint liên quan khác. Xem riêng enablement, web exposure và JMX exposure.

## 5. Tách management port khỏi application port

Có thể dùng management port riêng để giới hạn traffic quản trị:

```yaml
management:
  server:
    port: 9001
  endpoints:
    web:
      base-path: /manage
      exposure:
        include:
          - health
          - prometheus
```

Port riêng giúp tách listener quản trị khỏi traffic ứng dụng, nhưng không tự tạo security boundary. Nếu container publish port 9001 ra Internet hoặc ingress route tới port đó, endpoint vẫn public.

Cần phối hợp:
- Chỉ publish management port trong network nội bộ.
- Không cấu hình public ingress tới management service.
- Dùng firewall/security groups/network policies.
- Bind vào interface phù hợp nếu môi trường hỗ trợ.
- Chỉ cho phép monitoring/operator network truy cập.
- Kiểm tra service mesh và reverse proxy routing.

## 6. Authentication và authorization

Management endpoints cần kiểm soát caller. Authentication xác định danh tính; authorization quyết định caller được phép gọi endpoint nào và thực hiện thao tác gì.

Ví dụ phân quyền theo mục đích:
- Health probe: chỉ đọc trạng thái tối thiểu.
- Prometheus scraper: chỉ scrape metrics.
- Operator: đọc metrics/loggers và có thể đổi log level nếu được cấp quyền.
- Administrator: truy cập endpoint chẩn đoán nhạy cảm theo quy trình đặc biệt.

Không dùng một role rộng cho mọi endpoint chỉ vì dễ cấu hình. Đặc biệt, endpoint read-only vẫn có thể tiết lộ dữ liệu quan trọng.

### 6.1. Không coi mạng nội bộ là đủ

Network isolation giảm khả năng tiếp cận nhưng không thay thế authorization. Workload nội bộ bị xâm nhập hoặc misconfiguration có thể tạo đường truy cập ngoài dự kiến. Kết hợp network policy, authentication và quyền tối thiểu.

### 6.2. CSRF và endpoint thay đổi trạng thái

Các endpoint có thao tác POST như loggers hoặc shutdown cần được xem xét trong security policy. Không disable CSRF toàn ứng dụng chỉ để gọi một Actuator endpoint. Cấu hình security chain theo management path/port và loại client thực tế.

## 7. Health endpoint không nên tiết lộ dependency details

Health thường là endpoint cần thiết cho load balancer và orchestrator. Tuy nhiên, response chi tiết có thể tiết lộ database, broker, disk và dependency status.

Ví dụ giới hạn details:

```yaml
management:
  endpoint:
    health:
      show-details: never
      show-components: never
```

Tùy Spring Boot version, các giá trị show-details/show-components và quyền truy cập có thể khác. Nếu operator cần details, dùng when-authorized cùng authorization policy phù hợp.

### 7.1. Health groups cho probes

Kubernetes liveness/readiness có thể dùng health groups riêng. Chỉ expose các path cần thiết và tránh trả dependency details cho caller công khai.

Liveness nên phản ánh process có tiếp tục chạy được không. Readiness có thể phản ánh instance có thể nhận traffic không. Không đưa dependency outage vào liveness nếu điều đó có thể gây restart loop.

## 8. Env và configprops

Endpoint env và configprops có thể cho thấy property sources, cấu hình đã bind và metadata về ứng dụng. Dù Spring Boot có cơ chế sanitization một số key nhạy cảm, không nên xem redaction mặc định là bảo đảm mọi secret đều được che.

Các secret có thể xuất hiện dưới tên property không phổ biến hoặc nằm trong custom object. Vì vậy:
- Không expose env/configprops công khai.
- Disable nếu không có use case.
- Nếu operator cần, chỉ truy cập qua management network và role đặc biệt.
- Kiểm tra sanitization với custom property names.
- Không đưa password/token vào custom info endpoint.
- Không dựa vào việc property name có chữ password để bảo vệ mọi loại secret.

Ví dụ disable endpoint:

```yaml
management:
  endpoint:
    env:
      enabled: false
    configprops:
      enabled: false
```

Cấu hình chính xác phụ thuộc endpoint và Spring Boot version; đồng thời cần bảo đảm chúng không được expose qua JMX.

## 9. Heapdump và threaddump

Heap dump có thể chứa toàn bộ object graph tại thời điểm chụp, bao gồm tokens, credentials, session data và dữ liệu người dùng còn trong memory. File dump cũng có thể rất lớn và gây áp lực disk/CPU.

Thread dump có thể tiết lộ class names, stack traces, thread names, endpoint nội bộ và request context. Đây là dữ liệu chẩn đoán hữu ích nhưng cần quyền truy cập hẹp.

Quy trình an toàn:
1. Chỉ tạo dump khi có incident/use case cụ thể.
2. Dùng management access nội bộ có xác thực.
3. Lưu dump vào storage hạn chế quyền và có encryption.
4. Không đính kèm dump vào ticket/chat công khai.
5. Đặt retention ngắn và xóa theo policy.
6. Ghi audit ai tạo/tải dump và thời điểm.

Thông thường không cần expose heapdump/threaddump qua public web exposure.

## 10. Loggers và shutdown endpoint

Loggers endpoint có thể thay đổi log level runtime. Bật DEBUG/TRACE rộng có thể làm tăng log volume, lộ dữ liệu và chi phí ingest. Chỉ cấp quyền cho operator, giới hạn thời gian thay đổi và audit thao tác.

Shutdown endpoint có tác động trực tiếp đến availability. Nếu không có yêu cầu quản trị rõ ràng, giữ disabled và không expose.

```yaml
management:
  endpoint:
    shutdown:
      enabled: false
  endpoints:
    web:
      exposure:
        include:
          - health
          - prometheus
```

Nếu endpoint shutdown được dùng trong một hệ thống đặc biệt, cần xác thực, authorization, network isolation, audit và quy trình xác nhận vận hành.

## 11. JMX cũng cần được kiểm soát

Ẩn endpoint khỏi web không có nghĩa endpoint biến mất khỏi JMX. JMX exposure có policy riêng:

```yaml
management:
  endpoints:
    jmx:
      exposure:
        include:
          - health
          - metrics
        exclude:
          - env
          - configprops
          - heapdump
          - shutdown
```

Nếu không cần JMX remote access, tắt hoặc không mở remote JMX listener theo runtime policy. Remote JMX cần authentication, TLS và network restriction; không expose cổng JMX công khai.

## 12. Reverse proxy, ingress và service mesh

Management endpoint có thể bị public ngoài dự kiến qua reverse proxy hoặc ingress dù ứng dụng không trực tiếp publish port.

Kiểm tra:
- Ingress rules có route /actuator hoặc /manage không.
- Reverse proxy có forward toàn bộ path không.
- Service mesh gateway có route management port không.
- Kubernetes Service có expose management port ra network rộng không.
- Load balancer health check có dùng endpoint có details không.
- CDN/WAF/cache có lưu response management không.

Không chỉ dựa vào URL path để quyết định endpoint có public hay không. Xác minh network path từ bên ngoài và từ operator network.

## 13. Cấu hình theo environment

Có thể dùng baseline an toàn và chỉ thêm endpoint cần thiết theo từng profile.

application.yml:

```yaml
management:
  endpoints:
    web:
      exposure:
        include:
          - health
  endpoint:
    health:
      show-details: never
      show-components: never
  endpoint:
    shutdown:
      enabled: false
```

application-local.yml:

```yaml
management:
  endpoints:
    web:
      exposure:
        include:
          - health
          - info
          - metrics
          - loggers
```

application-prod.yml:

```yaml
management:
  endpoints:
    web:
      exposure:
        include:
          - health
          - prometheus
  endpoint:
    health:
      show-details: when-authorized
```

Trong YAML cần gộp các key trùng nhau trong cùng document để tránh duplicate-key parsing. Ví dụ baseline trên cần đặt shutdown dưới cùng mapping endpoint với health:

```yaml
management:
  endpoints:
    web:
      exposure:
        include:
          - health
  endpoint:
    health:
      show-details: never
      show-components: never
    shutdown:
      enabled: false
```

Profile chỉ điều khiển configuration. Network isolation và security policy phải được áp dụng độc lập trong deployment.

## 14. Kiểm thử không public endpoint nhạy cảm

Kiểm thử cần xác minh endpoint không truy cập được từ web public, và chỉ caller phù hợp mới truy cập được qua management path được bảo vệ.

Ví dụ integration test kiểm tra endpoint env không được expose:

```java
@SpringBootTest
@AutoConfigureMockMvc
class SensitiveActuatorExposureTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void envEndpointIsNotExposed() throws Exception {
        mockMvc.perform(get("/actuator/env"))
                .andExpect(status().isNotFound());
    }
}
```

Status thực tế có thể là 404, 401 hoặc 403 tùy security/routing configuration. Test phải xác nhận contract bảo mật mong muốn thay vì phụ thuộc một status code không được cam kết.

### 14.1. Test authorization

Tạo test caller không có role operator và xác nhận không thể đọc endpoint nhạy cảm hoặc gọi loggers POST. Test operator chỉ có thể truy cập đúng endpoint được cấp quyền.

### 14.2. Test network boundary

Integration test trong process không chứng minh ingress/network đã chặn public traffic. Cần kiểm tra deployment manifests, ingress rules, service ports và thực hiện probe từ network boundary tương ứng trong môi trường staging.

## 15. Troubleshooting

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Endpoint env vẫn truy cập được | Vẫn nằm trong include hoặc được expose qua JMX | Kiểm tra web/JMX exposure |
| Endpoint trả 401/403 | Authentication/authorization đang chặn | Kiểm tra caller identity và role |
| Endpoint nhạy cảm public qua ingress | Reverse proxy route rộng | Kiểm tra ingress/proxy/service |
| Heapdump vẫn tải được | Endpoint enabled và exposed ở transport khác | Kiểm tra enablement, web và JMX |
| Health response lộ dependency | show-details/show-components quá rộng | Giới hạn details theo policy |
| Prometheus không scrape được | Network policy hoặc auth chặn scraper | Kiểm tra scraper identity và path |
| Loggers POST không hoạt động | Endpoint chưa expose hoặc thiếu quyền | Kiểm tra exposure và authorization |
| Shutdown vẫn khả dụng | Endpoint chưa disabled | Kiểm tra management.endpoint.shutdown.enabled |
| JMX lộ endpoint dù web đã ẩn | JMX exposure/remote listener còn mở | Kiểm tra JMX config và runtime |
| Local an toàn nhưng prod public | Profile/deployment override hoặc ingress khác | Kiểm tra effective config và network |
| Secret xuất hiện trong env/configprops | Sanitization không nhận diện custom key | Không expose; sửa secret handling và policy |
| Endpoint mới xuất hiện sau upgrade | Wildcard include tự động expose | Chuyển sang allowlist và review upgrade |

### Quy trình điều tra

1. Xác định tất cả management ports, base paths và transports.
2. Kiểm tra endpoint enabled state.
3. Kiểm tra web exposure include/exclude.
4. Kiểm tra JMX exposure và remote JMX listener.
5. Kiểm tra authentication/authorization theo endpoint.
6. Kiểm tra ingress, reverse proxy, service mesh và firewall.
7. Kiểm tra response data có chứa secrets hoặc dependency details.
8. Kiểm tra profile và property source precedence.
9. Thêm test để endpoint nhạy cảm không thể truy cập từ public-facing path.
10. Xác minh lại từ network boundary sau khi deploy.

## 16. Bài thực hành: khóa endpoint nhạy cảm

Mục tiêu là xây dựng cấu hình Actuator chỉ công bố health và metrics cần thiết, đồng thời khóa các endpoint chẩn đoán.

### Chuẩn bị

- Spring Boot application có Actuator.
- Prometheus registry nếu cần scrape.
- Spring Security.
- Profile local và production-like.
- MockMvc/WebTestClient và môi trường staging để kiểm tra network.

### Bước 1 — Liệt kê endpoint cần dùng

Ghi rõ endpoint phục vụ health probe, scraper và operator. Không thêm endpoint chỉ vì nó tồn tại.

### Bước 2 — Dùng allowlist

Cấu hình include chỉ gồm health và prometheus nếu có nhu cầu. Không dùng wildcard trong production.

### Bước 3 — Disable endpoint nguy hiểm

Disable shutdown và các endpoint không có use case. Kiểm tra property support theo version.

### Bước 4 — Giới hạn health details

Đặt show-details/show-components phù hợp. Xác minh public caller chỉ nhận trạng thái tối thiểu.

### Bước 5 — Tách management network

Dùng management port hoặc service riêng nếu kiến trúc yêu cầu. Không route management port qua public ingress.

### Bước 6 — Thiết lập security roles

Cấp quyền riêng cho probe, scraper và operator. Kiểm tra caller không có quyền không thể đọc endpoint nhạy cảm.

### Bước 7 — Kiểm tra JMX

Xác minh endpoint không bị expose qua JMX ngoài dự kiến. Tắt remote JMX nếu không cần.

### Bước 8 — Kiểm tra ingress/proxy

Rà soát mọi route tới /actuator và management base path. Probe từ network bên ngoài để xác nhận endpoint không public.

### Bước 9 — Kiểm thử tự động

Thêm integration tests cho endpoint bị ẩn và authorization. Test riêng cho management port nếu ứng dụng dùng listener riêng.

### Bước 10 — Ghi nhận vận hành

Lưu danh sách endpoint được phép, owner, caller roles và quy trình truy cập tạm thời cho heap/thread dump khi incident.

### Checklist nghiệm thu

| Điều cần chứng minh | Kết quả mong đợi |
| --- | --- |
| Endpoint inventory | Biết endpoint nào cần và endpoint nào nhạy cảm |
| Allowlist | Không expose wildcard trên production |
| Enablement | Disable endpoint không có use case |
| Web/JMX | Kiểm soát độc lập cả hai transports |
| Network | Management port không public |
| Authentication | Caller được nhận diện |
| Authorization | Quyền theo endpoint/role |
| Health | Không lộ component details ngoài policy |
| Heap/thread dump | Chỉ truy cập qua quy trình đặc biệt |
| Loggers/shutdown | Quyền hạn chế; shutdown disabled nếu không cần |
| Ingress | Không route public tới management path |
| Testing | Có test exposure, auth và network boundary |

## 17. Những nguyên tắc cần ghi nhớ

1. **Không public endpoint nhạy cảm.** env, configprops, heapdump, threaddump, beans, mappings và shutdown cần quyền quản trị đặc biệt hoặc không expose.
2. **Ưu tiên allowlist.** Wildcard include có thể công bố endpoint mới sau khi nâng cấp.
3. **Phân biệt enabled, exposure và authorization.** Kiểm soát cả ba lớp.
4. **Web và JMX là hai transports độc lập.** Ẩn ở HTTP không đảm bảo JMX đã đóng.
5. **Management port riêng không tự tạo security boundary.** Cần network policy, ingress restriction và authentication.
6. **Giới hạn health details.** Probe chỉ nhận dữ liệu cần thiết.
7. **Bảo vệ heapdump/threaddump.** Dump có thể chứa dữ liệu trong memory và phải có retention/access policy.
8. **Hạn chế loggers và shutdown.** Loggers có thể thay đổi runtime; shutdown có thể dừng service.
9. **Kiểm tra proxy/ingress/service mesh.** Endpoint có thể public qua đường mạng gián tiếp.
10. **Kiểm thử từ đúng network boundary.** Unit test không chứng minh public ingress đã chặn endpoint.

Không public endpoint nhạy cảm giúp giữ Actuator hữu ích cho monitoring và operator mà không mở rộng quyền truy cập dữ liệu nội bộ. Khi dùng allowlist, disable endpoint không cần thiết, tách management network, phân quyền theo vai trò và kiểm tra cả ingress/JMX, Spring Boot có thể cung cấp observability production với bề mặt quản trị được kiểm soát.
