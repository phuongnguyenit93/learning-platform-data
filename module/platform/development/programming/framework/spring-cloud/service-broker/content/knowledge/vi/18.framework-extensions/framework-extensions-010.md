# Bổ sung dashboard và endpoint quản trị mà không xung đột đường dẫn OSB

## Hai mặt giao tiếp trong một ứng dụng broker

Một ứng dụng Spring Cloud Service Broker thường phục vụ hai nhóm người gọi có mục đích rất khác nhau:

- **Nền tảng tiêu thụ dịch vụ** gọi Open Service Broker API (OSB API) để đọc catalog, provision, update, bind, unbind, deprovision và theo dõi operation.
- **Người vận hành hoặc quản trị viên** cần dashboard và API quản trị để xem trạng thái broker, tra cứu instance, kiểm tra operation, xem lỗi tích hợp và thực hiện các tác vụ vận hành được cấp quyền.

Hai nhóm giao tiếp có thể nằm trong cùng một ứng dụng Spring, nhưng phải có ranh giới rõ ràng về đường dẫn, xác thực, phân quyền và dữ liệu được phép trả về. OSB API là hợp đồng máy-máy với nền tảng; dashboard/admin API là giao diện vận hành riêng. Nếu đặt các route tùy chỉnh chồng lên route OSB, một request hợp lệ của nền tảng có thể bị controller khác bắt nhầm, hoặc endpoint quản trị vô tình được mở ra qua cơ chế xác thực dành cho broker.

Trong module `SPRING_CLOUD_SERVICE_BROKER`, phần mở rộng cần giữ nguyên hành vi của OSB API và bổ sung giao diện vận hành theo namespace riêng. Spring Cloud Open Service Broker xử lý các endpoint giao thức; các controller dashboard và admin nên gọi domain service hoặc query service của ứng dụng, không can thiệp trực tiếp vào handler giao thức.

## Xác định namespace cho từng nhóm endpoint

Trước khi thêm controller, hãy lập bảng route của ứng dụng. Một cách bố trí dễ nhận biết:

| Nhóm | Prefix ví dụ | Mục đích | Người gọi |
|---|---|---|---|
| OSB API | `/v2/**` | Catalog và vòng đời service instance/binding theo chuẩn. | Cloud Foundry hoặc platform OSB tương thích. |
| Dashboard | `/console/**` | Trang giao diện cho người vận hành. | Quản trị viên qua trình duyệt. |
| Admin API | `/admin/api/v1/**` | Truy vấn trạng thái, operation và thực hiện tác vụ quản trị. | Dashboard hoặc công cụ vận hành đã xác thực. |
| Health/metrics | `/actuator/health`, `/actuator/prometheus` | Kiểm tra sức khỏe và metric theo cấu hình. | Orchestrator và hệ thống giám sát. |
| Internal integration | `/internal/**` nếu thực sự cần | Endpoint nội bộ giữa các thành phần được kiểm soát. | Thành phần nội bộ có xác thực và giới hạn mạng. |

Các prefix trên là quy ước đề xuất cho ứng dụng. Cần đối chiếu base path OSB API thực tế mà phiên bản Spring Cloud Open Service Broker và cấu hình ứng dụng đang sử dụng công bố. Nếu broker đặt OSB API ở một base path khác, namespace của dashboard/admin vẫn phải tách biệt và không được chồng lên base path đó.

Ví dụ các endpoint OSB API quan trọng:

| Method | Path OSB | Chức năng |
|---|---|---|
| `GET` | `/v2/catalog` | Công bố service và plan. |
| `PUT` | `/v2/service_instances/{instance_id}` | Provision instance. |
| `PATCH` | `/v2/service_instances/{instance_id}` | Update instance. |
| `DELETE` | `/v2/service_instances/{instance_id}` | Deprovision instance. |
| `GET` | `/v2/service_instances/{instance_id}/last_operation` | Poll trạng thái operation. |
| `PUT` | `/v2/service_instances/{instance_id}/service_bindings/{binding_id}` | Bind consumer. |
| `DELETE` | `/v2/service_instances/{instance_id}/service_bindings/{binding_id}` | Unbind consumer. |

Không tạo dashboard route như `/v2/admin`, `/v2/dashboard` hoặc controller catch-all `/v2/**` để xử lý giao diện riêng. Prefix `/v2` nên được dành cho giao thức OSB mà broker công bố hỗ trợ.

## Nguyên tắc thiết kế route để tránh xung đột

### Dùng prefix riêng, có version cho Admin API

Đặt endpoint quản trị dưới một namespace rõ ràng, ví dụ `/admin/api/v1`. Version riêng giúp thay đổi cấu trúc response của dashboard mà không ảnh hưởng đến hợp đồng OSB API.

Ví dụ:

```text
GET  /admin/api/v1/overview
GET  /admin/api/v1/instances
GET  /admin/api/v1/instances/{instanceId}
GET  /admin/api/v1/operations/{operationId}
POST /admin/api/v1/instances/{instanceId}/reconciliation
```

Các endpoint mutation như retry, reconciliation hoặc cancel operation cần được thiết kế riêng theo quyền và audit policy. Không nên cho phép dashboard gọi trực tiếp các endpoint OSB như thể nó là platform client.

### Dùng prefix riêng cho dashboard và static assets

Trang quản trị có thể được phục vụ dưới `/console`, còn CSS, JavaScript, ảnh và font được đặt dưới `/console/assets/**`. Nếu dùng SPA, fallback route trả `index.html` chỉ nên áp dụng trong namespace dashboard.

Một lỗi thường gặp là cấu hình fallback quá rộng, ví dụ mọi path không khớp controller đều trả `index.html`. Khi đó request sai đường dẫn `/v2/catalog` có thể nhận HTML thay vì JSON hoặc response lỗi OSB. Fallback phải loại trừ các prefix giao thức, admin API và actuator.

### Tránh mapping tổng quát và path động quá rộng

Các mapping như `/**`, `/{path}`, hoặc `/v2/**` có thể bắt request mà broker controller cần xử lý. Nếu thật sự cần route tổng quát cho dashboard, hãy giới hạn dưới `/console/**` và kiểm tra thứ tự `HandlerMapping`.

Spring MVC/WebFlux chọn handler dựa trên path, HTTP method, điều kiện mapping và thứ tự cấu hình. Không nên dựa vào giả định rằng controller được khai báo sau sẽ luôn được ưu tiên. Hãy kiểm tra mapping thực tế trong ứng dụng và viết integration test cho các path OSB quan trọng.

## Ví dụ Admin API trong Spring MVC

Admin controller nên nhận request, xác thực input và gọi application service. Nó không nên chứa logic trực tiếp tạo/xóa database hoặc thao tác với repository của OSB framework.

```java
@RestController
@RequestMapping("/admin/api/v1/instances")
public class InstanceAdminController {

    private final InstanceAdminQueryService queryService;

    public InstanceAdminController(InstanceAdminQueryService queryService) {
        this.queryService = queryService;
    }

    @GetMapping
    public Page<InstanceSummaryDto> list(
            @RequestParam(required = false) String state,
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "25") int size) {
        return queryService.search(state, page, size);
    }

    @GetMapping("/{instanceId}")
    public InstanceDetailDto get(@PathVariable String instanceId) {
        return queryService.getDetail(instanceId);
    }
}
```

Đây là ví dụ cho Spring MVC. `InstanceAdminQueryService`, DTO và kiểu `Page` là thành phần ứng dụng; có thể thay bằng kiểu phân trang khác. Với ứng dụng WebFlux, dùng controller reactive và kiểu trả về reactive phù hợp. Không trộn `SecurityFilterChain` của Servlet với `SecurityWebFilterChain` của WebFlux trong cùng một web stack.

Một DTO quản trị chỉ nên chứa thông tin cần cho vận hành, ví dụ:

```json
{
  "instanceId": "inst-orders-001",
  "serviceName": "postgresql",
  "planName": "standard",
  "state": "READY",
  "createdAt": "2026-11-27T08:30:00Z",
  "lastOperation": {
    "operationId": "op-123",
    "type": "PROVISION",
    "state": "SUCCEEDED"
  }
}
```

Không trả password, token, binding credentials, private key hoặc toàn bộ provider payload trong DTO quản trị. Nếu người vận hành cần xác minh secret, dashboard nên hiển thị trạng thái/reference và quy trình truy cập secret riêng theo chính sách bảo mật.

## Phân biệt xác thực OSB và xác thực quản trị

OSB API và Admin API có đối tượng gọi khác nhau:

| Khía cạnh | OSB API | Dashboard/Admin API |
|---|---|---|
| Caller | Nền tảng hoặc service manager. | Người vận hành, quản trị viên hoặc hệ thống nội bộ được cấp quyền. |
| Authentication | Cơ chế broker/platform đã cấu hình, thường dùng thông tin xác thực service-to-service. | SSO/OIDC, JWT, session hoặc cơ chế danh tính doanh nghiệp. |
| Authorization | Xác định platform nào được phép gọi broker và thao tác theo hợp đồng. | RBAC/ABAC theo vai trò, tenant, phạm vi instance và hành động. |
| Audit | Log request OSB và operation ID. | Ghi rõ người thực hiện, hành động, đối tượng, lý do và kết quả. |
| Response | Đúng schema và semantics OSB API. | DTO phục vụ dashboard, có phân trang và lọc. |

Không dùng chung một tài khoản quản trị có quyền cao cho platform client. Cũng không coi việc request đi vào `/admin/**` là đủ để chứng minh người gọi đã được xác thực. Mỗi namespace cần được bảo vệ bằng security policy tương ứng.

### Phân quyền theo vai trò và hành động

Một mô hình vai trò tham khảo:

| Vai trò | Quyền ví dụ |
|---|---|
| `BROKER_VIEWER` | Xem dashboard, instance summary và operation status đã được phép. |
| `BROKER_OPERATOR` | Xem chi tiết, xem log đã lọc và chạy thao tác vận hành được phê duyệt. |
| `BROKER_ADMIN` | Quản lý cấu hình broker và thực hiện tác vụ quản trị có ảnh hưởng lớn. |
| `BROKER_AUDITOR` | Đọc audit trail, không thay đổi tài nguyên. |

Role chỉ là lớp đầu tiên. Với endpoint như `/admin/api/v1/instances/{instanceId}`, cần kiểm tra người dùng có quyền xem instance thuộc tenant hoặc phạm vi phụ trách hay không. Không dựa vào việc người dùng đoán được `instanceId` hoặc truyền một tenant ID trong query để cấp quyền.

### Ví dụ security matcher cho Admin API

Với ứng dụng Spring MVC sử dụng Spring Security Servlet, có thể tạo một security chain dành riêng cho Admin API. Cấu hình xác thực JWT bên dưới chỉ minh họa khi hệ thống đã có OAuth2 Resource Server và issuer/JWK được cấu hình:

```java
@Bean
@Order(1)
SecurityFilterChain adminApiSecurity(HttpSecurity http) throws Exception {
    return http
            .securityMatcher("/admin/api/v1/**")
            .authorizeHttpRequests(auth -> auth
                    .requestMatchers(HttpMethod.GET, "/admin/api/v1/**")
                    .hasAnyRole("BROKER_VIEWER", "BROKER_OPERATOR", "BROKER_ADMIN")
                    .requestMatchers(HttpMethod.POST, "/admin/api/v1/**")
                    .hasAnyRole("BROKER_OPERATOR", "BROKER_ADMIN")
                    .anyRequest().hasRole("BROKER_ADMIN"))
            .oauth2ResourceServer(oauth -> oauth.jwt())
            .build();
}
```

Đây là ví dụ minh họa cho một chain riêng; ứng dụng phải cấu hình chain OSB và chain còn lại sao cho mọi request đều được bao phủ đúng một policy dự kiến. Thứ tự `@Order`, matcher và cách ánh xạ role từ claim JWT cần được kiểm tra trong cấu hình thực tế. Không sao chép nguyên trạng nếu ứng dụng dùng WebFlux hoặc một cơ chế đăng nhập khác.

Nếu dashboard dùng cookie/session, cần giữ CSRF protection cho các thao tác thay đổi trạng thái. Nếu dùng bearer token stateless, chính sách CSRF có thể khác nhưng phải nhất quán với cách token được gửi. Không tắt CSRF toàn cục chỉ để một endpoint admin hoạt động.

## Dashboard không được làm lộ dữ liệu nhạy cảm

Dashboard thường tổng hợp dữ liệu từ instance, binding, operation và provider. Đây là nơi dễ vô tình hiển thị thông tin vượt quá nhu cầu vận hành.

Nên áp dụng các quy tắc:

- Che hoặc bỏ hoàn toàn password, token, private key và binding credentials.
- Không hiển thị header Authorization, provider secret hoặc raw request/response body có thông tin nhạy cảm.
- Giới hạn nội dung lỗi; không trả stack trace, SQL, internal hostname hoặc cấu hình secret.
- Phân quyền theo tenant/instance cho mọi truy vấn chi tiết.
- Dùng phân trang, giới hạn kích thước page và filter có kiểm soát để tránh query quá nặng.
- Ghi audit log cho thao tác retry, reconciliation, thay đổi plan hoặc can thiệp thủ công.
- Không cho phép dashboard thực hiện hành động phá hủy chỉ bằng một GET request.

Các thao tác admin có side effect nên dùng HTTP method phù hợp (`POST`, `PATCH`, `DELETE` theo thiết kế), yêu cầu quyền rõ ràng, có xác nhận nghiệp vụ ở tầng ứng dụng và lưu actor/reason trong audit record. Tránh thiết kế endpoint chung kiểu `/admin/execute?command=...` có thể gọi tùy ý các lệnh nội bộ.

## Tích hợp Spring Boot Actuator

Spring Boot Actuator có thể cung cấp health, info, metrics và các endpoint vận hành. Đây là nhóm endpoint riêng với OSB API và Admin API nghiệp vụ.

Một cấu hình minh họa:

```yaml
management:
  endpoints:
    web:
      base-path: /actuator
      exposure:
        include: health,info,prometheus
  endpoint:
    health:
      show-details: when_authorized
```

Tên property và khả năng chi tiết phụ thuộc phiên bản Spring Boot. Chỉ expose endpoint thực sự cần thiết. Các endpoint như `env`, `configprops`, `beans`, `heapdump`, `loggers` hoặc `shutdown` có thể tiết lộ cấu hình nội bộ hoặc thay đổi trạng thái; không mở công khai nếu chưa có yêu cầu và kiểm soát bảo mật phù hợp.

Trong môi trường production, có thể đặt management server trên port riêng bằng cấu hình `management.server.port` và giới hạn truy cập bằng network policy, firewall hoặc service mesh. Tách port không tự động bảo vệ endpoint; vẫn cần xác thực, phân quyền và giới hạn network. Liveness/readiness probe nên trả đúng mức thông tin mà orchestrator cần, không tiết lộ chi tiết provider hoặc secret.

## Tránh xung đột trong Spring MVC/WebFlux và reverse proxy

### Kiểm tra mapping đã đăng ký

Trong quá trình phát triển, có thể kiểm tra danh sách handler mapping qua log khởi động hoặc actuator mapping endpoint trong môi trường development được bảo vệ. Xác nhận:

- OSB controller vẫn nhận đúng `/v2/**` và HTTP method.
- Dashboard chỉ nhận `/console/**`.
- Admin API chỉ nhận `/admin/api/v1/**`.
- Actuator nằm ở base path riêng.
- Không có catch-all mapping chiếm các path OSB.

Không expose actuator `mappings` công khai chỉ để debug route. Có thể dùng log ở môi trường phát triển hoặc endpoint nội bộ được bảo vệ.

### Reverse proxy và context path

Nếu broker chạy sau ingress hoặc reverse proxy, cần thống nhất path bên ngoài và path ứng dụng nhìn thấy. Ví dụ proxy có thể public broker dưới `/broker`, rồi chuyển tiếp `/broker/v2/**` thành `/v2/**`. Dashboard có thể public dưới `/broker/console/**` nhưng vẫn chuyển đến `/console/**` ở ứng dụng.

Hãy kiểm tra:

- Proxy không rewrite `/v2` thành `/admin` hoặc ngược lại.
- Header forwarded và scheme HTTPS được xử lý đúng.
- Cookie path của dashboard không vô tình áp dụng cho OSB client.
- CORS chỉ cho phép origin dashboard cần thiết; OSB server-to-server không cần mở CORS rộng.
- Static resource và SPA fallback không bắt các request API.
- URL được sinh trong dashboard tôn trọng context path khi deploy dưới prefix.

Không dựa vào `X-Forwarded-*` từ bất kỳ client nào nếu proxy tin cậy chưa được cấu hình. Header giả mạo có thể làm sai host, scheme hoặc client address trong audit và redirect.

## Kiểm thử để bảo đảm OSB API không bị ảnh hưởng

Mỗi lần thêm dashboard/admin route cần có integration test cho cả route mới và route OSB hiện hữu.

| Kiểm thử | Điều cần xác nhận |
|---|---|
| `GET /v2/catalog` | Vẫn trả response catalog đúng schema OSB. |
| `PUT /v2/service_instances/{id}` | Vẫn được route đến handler provision, không bị admin controller bắt. |
| `GET /v2/service_instances/{id}/last_operation` | Vẫn trả response polling đúng hợp đồng. |
| `PUT/DELETE .../service_bindings/{binding_id}` | Bind/unbind không bị ảnh hưởng bởi dashboard route. |
| `GET /console/` | Chỉ trả dashboard cho người dùng được phép. |
| `GET /admin/api/v1/instances` | Yêu cầu authentication và role phù hợp. |
| `POST /admin/api/v1/...` | Người chỉ có quyền viewer bị từ chối. |
| Truy vấn instance tenant khác | Bị từ chối dù biết `instanceId`. |
| `/actuator/health` | Chỉ lộ trạng thái phù hợp với probe/monitoring policy. |
| Path không hợp lệ dưới `/v2/**` | Không bị SPA fallback trả `index.html`. |

Ví dụ kiểm thử route bằng MockMvc:

```java
@SpringBootTest
@AutoConfigureMockMvc
class BrokerRouteIntegrationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void catalogRouteRemainsOwnedByOsbApi() throws Exception {
        mvc.perform(get("/v2/catalog")
                        .header("X-Broker-API-Version", "2.17"))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON));
    }

    @Test
    void adminApiRequiresAuthentication() throws Exception {
        mvc.perform(get("/admin/api/v1/instances"))
                .andExpect(status().isUnauthorized());
    }
}
```

Đây là khung kiểm thử minh họa; kết quả status cụ thể của endpoint admin phụ thuộc cơ chế authentication (có thể là `401` hoặc redirect đến IdP/login). Test catalog cần cấu hình fixture và xác thực OSB phù hợp với ứng dụng. Với WebFlux, dùng `WebTestClient` thay cho MockMvc.

## Quy trình bổ sung dashboard an toàn

1. Liệt kê base path OSB API và các method/path đang được framework sử dụng.
2. Chọn namespace riêng cho dashboard, admin API và management endpoint.
3. Xây dựng DTO và query service chỉ trả dữ liệu cần cho vận hành.
4. Thiết lập authentication và authorization riêng cho dashboard/admin.
5. Bảo vệ thao tác mutation bằng role, resource-level authorization và audit.
6. Cấu hình static resource/SPA fallback chỉ trong `/console/**`.
7. Kiểm tra reverse proxy, context path, CORS, CSRF và forwarded headers.
8. Viết integration test xác nhận route OSB vẫn hoạt động.
9. Kiểm tra các endpoint Actuator được expose và giới hạn truy cập.
10. Theo dõi log route, authentication failure và audit event sau khi triển khai.

## Kết luận

Dashboard và Admin API có thể cùng tồn tại trong ứng dụng Spring Cloud Service Broker nếu được đặt trong namespace riêng, có security boundary riêng và chỉ truy cập domain service qua các interface rõ ràng. Dành `/v2/**` cho hợp đồng OSB, dùng `/console/**` cho giao diện, `/admin/api/v1/**` cho API quản trị và một base path management riêng giúp tránh xung đột route. Integration test cho catalog, provision, binding và polling là điều kiện cần mỗi khi mở rộng ứng dụng, để công cụ vận hành không làm thay đổi hành vi mà nền tảng OSB đang phụ thuộc.
