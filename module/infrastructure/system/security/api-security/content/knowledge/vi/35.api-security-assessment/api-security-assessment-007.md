# Test deprecated, shadow và internal endpoint

API có thể tồn tại lâu hơn phiên bản ứng dụng đã tạo ra nó. Một endpoint cũ được đánh dấu deprecated nhưng vẫn public, một route thử nghiệm bị quên sau khi release, hoặc một endpoint nội bộ chỉ được thiết kế cho service-to-service có thể trở thành đường truy cập ít được kiểm soát hơn API chính. Các endpoint này thường thiếu test mới, không còn owner rõ ràng, không xuất hiện trong tài liệu hiện hành hoặc được bảo vệ dựa trên giả định rằng chỉ mạng nội bộ mới gọi được.

**Deprecated endpoint** là endpoint đã được công bố sẽ thay thế hoặc ngừng hỗ trợ nhưng vẫn còn hoạt động trong một giai đoạn. **Shadow endpoint** là route/API đang chạy nhưng không được quản lý đầy đủ trong inventory, contract hoặc quy trình release. **Internal endpoint** là endpoint dành cho workload, operator hoặc mạng nội bộ, không nhằm phục vụ caller Internet thông thường. Ba nhóm này có thể chồng lấn: một internal endpoint có thể trở thành shadow nếu không ai biết nó tồn tại; một endpoint deprecated có thể vẫn được gọi bởi mobile app cũ.

Trong phạm vi SECURITY_API_SECURITY, đánh giá phải tìm ra endpoint nào thực sự có thể truy cập, ai có thể gọi, dữ liệu/action nào được phép và đường đi nào có thể bỏ qua gateway hoặc policy chuẩn. Kiểm thử cần đối chiếu inventory, route trong ứng dụng, cấu hình gateway/ingress, service mesh, DNS/network exposure và telemetry. Mục tiêu là loại bỏ endpoint không cần thiết, đưa endpoint còn cần dùng về cùng baseline bảo mật và có bằng chứng rằng các route đã ngừng hỗ trợ không còn tạo ra đường bypass.

## 1. Phân biệt ba loại endpoint

| Loại | Trạng thái | Rủi ro thường gặp |
|---|---|---|
| Deprecated | Được biết và đã thông báo sẽ thay thế/ngừng hỗ trợ | Client cũ tiếp tục dùng; policy cũ không được cập nhật; endpoint bị quên sau ngày sunset |
| Shadow | Đang tồn tại nhưng thiếu inventory/owner/contract hoặc không qua quy trình quản lý chuẩn | Không có security review, không có monitoring, route thử nghiệm bị public |
| Internal | Được thiết kế cho service, operator hoặc mạng riêng | Tin mạng nội bộ quá mức; gateway bypass; thiếu authentication hoặc object authorization |

Không thể kết luận endpoint an toàn chỉ từ tên route, ví dụ /internal, /legacy, /debug hoặc /v1. Cần kiểm tra runtime behavior và network reachability. Tương tự, route không có trong OpenAPI không có nghĩa route không tồn tại; nó có thể được khai báo bằng framework annotation, router động, gateway rewrite hoặc service khác.

### 1.1. Vì sao endpoint cũ và endpoint ẩn dễ bị bỏ sót?

- Team chỉ review route mới trong pull request, không kiểm kê route đang chạy.
- Gateway có route cũ nhưng code/controller đã thay đổi, hoặc ngược lại.
- Một service mở thêm management port mà inventory chỉ ghi application port.
- Mobile app hoặc đối tác vẫn gọi endpoint cũ theo lịch release riêng.
- Feature flag tắt giao diện nhưng backend route vẫn hoạt động.
- Route thử nghiệm được thêm tạm để debug rồi không bị xóa.
- Internal endpoint dựa vào source IP hoặc header do proxy truyền mà không xác minh caller.
- Service có thể được gọi trực tiếp qua cluster IP, NodePort, load balancer hoặc DNS nội bộ.
- API version cũ vẫn còn một authorization rule yếu hơn version mới.

## 2. Xác định phạm vi đánh giá và quy tắc an toàn

Trước khi kiểm thử, xác định rõ môi trường, hostname, service, namespace, gateway, dải mạng và thời gian được phép. Dùng staging hoặc môi trường test có dữ liệu tổng hợp khi có thể. Nếu cần xác minh production exposure, ưu tiên request không gây side effect và phối hợp với owner vận hành.

Một assessment plan nên ghi:

- Mục tiêu: service/API nào, môi trường nào, domain và network zone nào.
- Phạm vi: route, method, version, port, gateway và internal listener.
- Identity test: anonymous, user thường, tenant admin, service account và operator.
- Dữ liệu: synthetic tenant/object và canary marker, không dùng PII thật.
- Kỹ thuật: inventory review, passive traffic analysis, authenticated route test và network reachability test.
- Giới hạn: request rate, concurrency, payload size và thao tác không được thực hiện.
- Thời gian: cửa sổ test và người liên hệ khi có ảnh hưởng.
- Tiêu chí dừng: latency/5xx tăng, queue backlog, dữ liệu ngoài tenant xuất hiện hoặc side effect ngoài dự kiến.

Không chạy fuzzing, brute force, tải lớn hoặc gọi endpoint có thể gửi payment/email/xóa dữ liệu trên production nếu chưa có phê duyệt và giới hạn riêng. Với mục tiêu xác định endpoint có public hay không, thường chỉ cần kiểm tra handshake, status và response header an toàn.

## 3. Lập inventory endpoint từ nhiều nguồn

Không có một nguồn duy nhất phản ánh đầy đủ attack surface. Đối chiếu các nguồn độc lập để phát hiện route bị thiếu hoặc route không còn được sử dụng.

| Nguồn | Có thể phát hiện | Giới hạn |
|---|---|---|
| OpenAPI/Swagger | Contract và endpoint đã công bố | Có thể thiếu route legacy, admin hoặc dynamic |
| Source code/router | Controller, annotation, route registration | Không luôn phản ánh cấu hình runtime/gateway |
| API gateway/ingress config | Public host/path/method và rewrite | Có thể bỏ sót service listener trực tiếp |
| Service mesh/service registry | Service-to-service route và identity | Cần quyền đọc cấu hình cluster |
| DNS, load balancer và firewall | Hostname/port/network reachability | Không mô tả đầy đủ semantics ứng dụng |
| Access log/APM/tracing | Endpoint thực sự được gọi | Không thấy route chưa từng được gọi trong cửa sổ quan sát |
| Client SDK/mobile binaries | Contract mà consumer cũ đang dùng | Không bao quát mọi integration |
| Deployment manifests | Port, ingress, actuator và profile | Có thể khác cấu hình sau deploy |
| Security test/DAST inventory | Route phát hiện được từ bên ngoài | Phụ thuộc credential, crawl coverage và role |

### 3.1. Chuẩn hóa endpoint identity

Một endpoint record nên phân biệt:

- Service và environment.
- Hostname/listener/port.
- HTTP method.
- Route template, ví dụ /v1/orders/{orderId}.
- API version và operation ID.
- Exposure class: public, partner, internal, management hoặc test-only.
- Authentication mechanism.
- Function/object/tenant authorization policy.
- Data classification và side effect.
- Owner, consumer và lifecycle state.
- Ngày review, deprecation và sunset nếu có.

Không dùng URL thực chứa object ID làm định danh endpoint. Route template giúp đối chiếu code, gateway, metrics và test mà không tạo một entry cho mỗi resource.

### 3.2. Đối chiếu chênh lệch

Tạo tập hợp route từ OpenAPI, router/runtime, gateway và traffic logs, sau đó phân loại:

- Có trong contract và runtime: endpoint đã được quản lý, cần review policy.
- Có trong runtime nhưng thiếu contract: candidate shadow endpoint.
- Có trong gateway nhưng backend không còn route: stale gateway mapping hoặc rewrite sai.
- Có trong traffic nhưng không map được operation/owner: cần điều tra.
- Có trong code nhưng không expose ở runtime: kiểm tra config và xác nhận có chủ đích.
- Không có traffic trong cửa sổ quan sát nhưng vẫn expose: candidate cần owner xác nhận, không tự kết luận có thể xóa.

Traffic không xuất hiện trong 7 hoặc 30 ngày không chứng minh endpoint không còn consumer. Batch theo tháng, disaster recovery, đối tác ít hoạt động hoặc ứng dụng mobile cũ có thể gọi rất thưa.

## 4. Test deprecated endpoint

Deprecated endpoint cần được quản lý theo vòng đời: thông báo, đo consumer, migration, sunset và removal. Trong giai đoạn hỗ trợ, endpoint vẫn phải tuân thủ security policy hiện hành.

### 4.1. Xác minh deprecation metadata

Kiểm tra:

- API documentation đánh dấu đúng endpoint/field/version.
- Có replacement endpoint hoặc migration guide.
- Có owner chịu trách nhiệm và consumer inventory.
- Có ngày deprecation và sunset theo chính sách công bố.
- Response/header có thể thông báo deprecation nếu contract hỗ trợ.
- SDK và client được hỗ trợ biết thời điểm kết thúc.

Có thể dùng các header Deprecation, Sunset và Link rel=deprecation theo contract đã chọn. Header chỉ là tín hiệu cho client; nó không tự tắt endpoint và không thay thế thông báo đến consumer.

### 4.2. Security regression trên version cũ

Kiểm thử các trường hợp:

- Anonymous request đến endpoint cũ vẫn bị từ chối.
- Token sai issuer/audience/expiry không được chấp nhận.
- User thiếu function permission không thực hiện được action.
- User thuộc tenant khác không đọc/sửa object.
- Field nhạy cảm không xuất hiện trong response cũ.
- Mass assignment và input validation được áp dụng như baseline hiện hành.
- Rate limit, body limit và resource budget không bị bỏ qua.
- Legacy endpoint không gọi downstream bằng service account quá rộng.
- Endpoint cũ không bypass gateway authentication hoặc audit.

Nếu version cũ có security flaw, sửa policy trên route cũ hoặc tắt route theo incident plan. Không giữ lỗ hổng đến ngày sunset chỉ để bảo đảm backward compatibility.

### 4.3. Test ngày sunset

Sau thời điểm sunset:

- Route cũ không còn được route đến business handler.
- Gateway không còn public mapping cũ.
- Service không còn listener/alias ngoài ý muốn.
- Request cũ nhận response đã định nghĩa, ví dụ 404 hoặc 410, không fallback sang implementation yếu.
- Không tạo side effect hoặc enqueue job từ route đã sunset.
- Cache/CDN không tiếp tục phục vụ response nhạy cảm từ route cũ.
- Telemetry ghi nhận consumer còn gọi để owner xử lý migration.

Status code cần theo contract và chính sách công bố. 410 Gone có thể diễn tả resource đã ngừng vĩnh viễn; 404 có thể được chọn để không tiết lộ route/object. Dù dùng status nào, route đã sunset không được thực hiện nghiệp vụ.

## 5. Phát hiện shadow endpoint

Shadow endpoint là route tồn tại nhưng không được quản lý như một phần chính thức của API. Nó có thể là endpoint test, debug, admin, legacy hoặc route nội bộ bị expose ngoài dự kiến.

### 5.1. Các nguồn tìm kiếm

- So sánh route runtime với OpenAPI/contract registry.
- Review router mapping và controller annotation trong service thuộc phạm vi.
- Kiểm tra gateway/ingress rewrite, wildcard route và path prefix.
- Kiểm tra management port, actuator exposure và debug listener.
- Đối chiếu traffic log với owner/operation ID.
- Kiểm tra deployment profile và feature flag sau khi khởi động.
- Tìm endpoint test/dev trong artifact cấu hình đã deploy.

Tên route thường gặp như /debug, /test, /admin, /internal, /actuator, /metrics, /env, /console hoặc /graphql chỉ là dấu hiệu để review; không được coi danh sách tên này là đầy đủ hoặc bằng chứng endpoint tồn tại.

### 5.2. Shadow endpoint thường có lỗi gì?

- Không có authentication vì chỉ được gọi từ frontend nội bộ.
- Chỉ kiểm tra role ở UI, không kiểm tra ở server.
- Dùng shared API key hoặc credential mặc định.
- Trả stack trace, environment/config hoặc diagnostic dump.
- Cho phép export/search không giới hạn.
- Bỏ tenant scope hoặc field masking.
- Không có rate limit, audit hoặc alert.
- Chấp nhận HTTP method không được dự kiến.
- Có CORS wildcard hoặc phản chiếu Origin.
- Chạy trong profile dev nhưng bị expose trên production listener.

### 5.3. Xác minh owner và mục đích

Khi phát hiện route chưa có inventory, không tự giả định nó là rác. Tìm owner qua service/team metadata được cung cấp trong phạm vi dự án, commit/deployment ownership và traffic pattern. Ghi nhận mục đích, consumer, data sensitivity, authentication và side effect. Nếu không xác định được owner, phân loại là finding cần xử lý, giới hạn truy cập theo policy và yêu cầu owner xác nhận trước khi giữ lại.

## 6. Test internal endpoint và nguy cơ gateway bypass

Internal endpoint thường được thiết kế để chỉ service trong mạng riêng gọi. Tuy nhiên, mạng riêng không đồng nghĩa caller đáng tin. Workload bị xâm nhập, SSRF từ một service public hoặc cấu hình network sai có thể cho attacker tiếp cận route nội bộ.

### 6.1. Kiểm tra exposure thực tế

Xác định endpoint có thể được truy cập qua:

- Public DNS/load balancer/ingress.
- Public application listener.
- Management listener hoặc management port.
- ClusterIP, NodePort hoặc service mesh route.
- Internal DNS từ workload khác.
- Direct pod/container port.
- Reverse proxy route hoặc path rewrite.
- Admin VPN/bastion/zero-trust access path.

Đối chiếu intended exposure với thực tế từ các network zone được phép test. Một endpoint intended internal nhưng public reachable là finding nghiêm trọng; một endpoint chỉ reachable trong cluster vẫn cần authentication và authorization phù hợp với workload caller.

### 6.2. Kiểm tra gateway bypass

Nếu gateway thực hiện authentication, rate limit hoặc request validation, kiểm tra service backend có thể bị gọi trực tiếp hay không. Các câu hỏi:

- Backend listener có public IP hoặc port ngoài dự kiến không?
- Firewall/security group chỉ cho gateway hoặc service identity được duyệt truy cập không?
- Service có tự xác minh token/audience/issuer hay tin header gateway?
- Header identity có bị client Internet giả mạo khi đi đường trực tiếp không?
- Có route khác trong cluster truy cập cùng controller mà không qua policy không?
- Health/management listener có bị nhầm với application listener không?

Không coi header như X-Authenticated-User, X-User-Role hoặc X-Tenant-Id là đáng tin nếu backend có thể nhận trực tiếp từ client. Gateway phải xóa header do caller gửi và tạo lại trên trust channel; backend cần xác minh caller gateway hoặc token/delegation context.

### 6.3. Internal không có nghĩa là permit-all

Service-to-service request vẫn cần workload identity, mTLS hoặc token có audience/scope phù hợp. Service nhận phải kiểm tra:

- Workload caller nào đang kết nối?
- Caller được gọi function nào?
- Tenant/resource scope nào được phép?
- Có delegation user context không, và delegation có hợp lệ?
- Message/request có integrity và freshness cần thiết không?

Không cấp quyền admin cho mọi workload chỉ vì chúng nằm trong cluster. Dùng service account riêng và least privilege.

## 7. Kiểm tra management, health và diagnostic endpoint

Management endpoint có thể tiết lộ trạng thái, cấu hình hoặc cho phép thao tác vận hành. Cần phân loại endpoint:

| Endpoint family | Dữ liệu/hành động có thể chứa | Kiểm soát cần xem xét |
|---|---|---|
| Health/liveness | Trạng thái process/dependency | Public chỉ khi response tối giản và không lộ topology |
| Readiness | Khả năng nhận traffic | Chỉ expose trong network cần thiết |
| Metrics | Route, service, runtime labels | Management network, không chứa secret/PII |
| Environment/config | Biến môi trường, config values | Không public; thường không expose ở production |
| Heap/thread dump | Memory, request data, token có thể còn trong heap | Quyền vận hành rất hạn chế, audit và retention |
| Loggers | Thay đổi log level | Operator authorization, TTL và audit |
| Shutdown/restart | Side effect vận hành | Không public; approval và privilege riêng |
| Mappings/routes | Inventory nội bộ | Chỉ truy cập từ management plane |

Không expose toàn bộ actuator hoặc diagnostic endpoints chỉ để tiện hỗ trợ. Chỉ bật phần cần thiết, tách management listener/network nếu phù hợp và bảo vệ cả endpoint lẫn dữ liệu response.

## 8. Ma trận identity và authorization khi test endpoint

Một endpoint cần được test bằng nhiều loại caller. Một request thành công từ admin không chứng minh user thường bị giới hạn đúng.

| Caller | Mục đích test | Kết quả mong đợi |
|---|---|---|
| Anonymous Internet caller | Xác minh public exposure và authentication | Chỉ endpoint public được phép; endpoint riêng bị chặn |
| Authenticated user thường | Kiểm tra function/object/field permission | Chỉ truy cập dữ liệu và action được grant |
| Tenant admin | Kiểm tra quyền trong tenant | Không vượt tenant boundary |
| Service account | Kiểm tra workload identity và scope | Chỉ gọi service/action được cấp |
| Operator | Kiểm tra management access | Chỉ endpoint và thao tác vận hành được phép |
| Caller từ network zone không tin cậy | Kiểm tra network segmentation | Không tiếp cận internal-only listener |
| Gateway identity | Kiểm tra trust giữa gateway và backend | Backend xác minh gateway và security context |

Với mỗi endpoint, test allow/deny theo method và action. Ví dụ GET có thể public nhưng POST/DELETE trên cùng path cần permission khác. Không đánh giá exposure chỉ theo hostname.

## 9. Kiểm tra method, path và routing khác biệt

Gateway và application có thể diễn giải path/method khác nhau. Điều này có thể tạo route bypass hoặc khiến endpoint bị bảo vệ ở một đường nhưng mở ở đường khác.

Các test cần cân nhắc:

- HTTP method ngoài allowlist, bao gồm method lạ và method override header nếu framework hỗ trợ.
- Trailing slash và path normalization.
- Case sensitivity theo router/proxy.
- Encoded slash, dot segment và double encoding.
- Duplicate slash và path parameter encoding.
- Version prefix, alias và rewrite rule.
- OPTIONS/CORS preflight so với OPTIONS nghiệp vụ.
- Host header và forwarded host handling.
- Content type và request body parser khác nhau.

Chạy các test parser/routing bất thường trong môi trường test được kiểm soát. Mục tiêu là xác minh gateway và backend cùng nhận diện một route, không tạo một đường đi khác với security policy yếu hơn.

## 10. Kiểm tra deprecation, shadow và internal endpoint bằng telemetry

Telemetry giúp biết endpoint nào đang được gọi và bởi ai. Thu thập:

- Route template, method, version và service.
- Client ID/API key ID/principal/tenant từ security context đã xác minh.
- Authentication và authorization decision.
- Status code, latency, response size và resource cost.
- Request origin/network zone hoặc workload identity khi có.
- Correlation ID, operation ID và side effect status.
- Deprecated version usage và endpoint owner.

Không log token, API key secret, cookie, raw body hoặc PII không cần thiết. Metrics nên dùng route template và low-cardinality labels; client/tenant chi tiết phù hợp hơn với structured log hoặc analytics có access control.

### 10.1. Tìm endpoint deprecated còn được sử dụng

Theo dõi traffic theo API version/client trong một khoảng đủ dài để bao phủ consumer ít hoạt động. Phân biệt:

- Client đang dùng endpoint theo lịch bình thường.
- Client mới vẫn gọi nhầm route cũ.
- Bot/scanner hoặc traffic không xác thực.
- Retry loop sau response lỗi.
- Integration không có owner hoặc không khai báo.

Không xóa endpoint chỉ dựa trên một biểu đồ traffic ngắn. Xác minh với consumer owner và lịch job/DR.

### 10.2. Phát hiện shadow endpoint qua access log

Route có traffic nhưng không map được operation/owner là dấu hiệu cần điều tra. Ngược lại, route có trong runtime nhưng không có traffic vẫn có thể là endpoint nguy hiểm nếu nó public và không được bảo vệ. Kết hợp runtime route inventory, network exposure và logs; không chỉ dựa vào usage.

## 11. Remediation: giữ, thay thế, giới hạn hoặc gỡ bỏ

Sau assessment, mỗi endpoint cần một quyết định và owner.

| Finding | Hướng xử lý |
|---|---|
| Deprecated endpoint còn consumer hợp lệ | Lập migration plan, enforce security baseline hiện hành, sunset theo lịch |
| Deprecated endpoint không còn consumer và owner xác nhận | Gỡ route, gateway mapping, credential và test fixture liên quan |
| Shadow endpoint có chức năng hợp lệ | Đưa vào inventory/contract, chỉ định owner, thêm authz, monitoring và release gate |
| Shadow endpoint không có mục đích | Disable/gỡ bỏ và xác minh không còn route runtime |
| Internal endpoint bị public | Chặn exposure tại ingress/firewall, sau đó kiểm tra authentication ở backend |
| Internal endpoint thiếu workload identity | Bổ sung mTLS/token audience/scope và least privilege |
| Management endpoint lộ dữ liệu | Tắt hoặc giới hạn listener, giảm response detail, audit access |
| Endpoint có policy yếu hơn version mới | Đồng bộ policy hoặc sunset khẩn cấp nếu có lỗ hổng |

Không chỉ xóa controller mà quên gateway route, DNS record, firewall rule, service account, SDK hoặc consumer config. Remediation cần xử lý toàn bộ đường đi và xác minh runtime sau deployment.

### 11.1. Deprecation có thời hạn

Một kế hoạch sunset cần:

1. Consumer inventory và owner.
2. Replacement endpoint và migration guide.
3. Thông báo deprecation/sunset.
4. Usage monitoring và reminder.
5. Security regression test cho endpoint cũ trong thời gian hỗ trợ.
6. Ngày disable và rollback/forward-fix plan.
7. Xác minh route không còn reachable hoặc chỉ trả response ngừng hỗ trợ.
8. Xóa policy, credential và code cũ không còn cần thiết.

Nếu endpoint cũ có thể truy cập dữ liệu ngoài tenant hoặc cho phép action nguy hiểm, ưu tiên sửa hoặc disable ngay theo incident process; không chờ chu kỳ deprecation thông thường.

## 12. Ví dụ kiểm thử với Spring Boot và gateway

Ví dụ một endpoint nội bộ chỉ dành cho service identity:

~~~java
@RestController
@RequestMapping("/internal/reconciliation")
class ReconciliationController {

    @PostMapping("/run")
    ResponseEntity<Void> run(
            @AuthenticationPrincipal Jwt principal,
            @RequestBody ReconciliationRequest request) {
        workloadAuthorization.requireScope(
            principal, "reconciliation:run");
        reconciliationService.run(request);
        return ResponseEntity.accepted().build();
    }
}
~~~

Đây là ví dụ minh họa. Trong hệ thống thực tế cần xác minh JWT issuer, audience, signature, expiry và workload identity; request DTO phải validate; service phải kiểm tra tenant/object scope và side effect. Chỉ gắn prefix /internal không tạo ra bảo vệ.

Ví dụ test anonymous và principal thiếu scope:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class InternalEndpointSecurityTest {

    @Autowired
    MockMvc mvc;

    @Test
    void anonymousCallerCannotRunReconciliation() throws Exception {
        mvc.perform(post("/internal/reconciliation/run")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"tenantId\":\"tenant-a\"}"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    @WithMockUser(authorities = "orders:read")
    void unrelatedServiceScopeCannotRunReconciliation() throws Exception {
        mvc.perform(post("/internal/reconciliation/run")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"tenantId\":\"tenant-a\"}"))
            .andExpect(status().isForbidden());
    }
}
~~~

Mock user chỉ test authority mapping trong filter/security context; nó không chứng minh JWT workload thực tế được xác minh. Cần thêm test signed token với issuer/audience/scope và test network path để xác minh endpoint không public ngoài dự kiến.

### 12.1. Test direct backend access

Trong staging, gửi cùng một request:

- Qua public gateway.
- Qua internal gateway/mesh path được cấp phép.
- Trực tiếp đến backend listener từ network zone test.
- Từ workload không được cấp service identity.

So sánh authentication, authorization, response và audit. Nếu direct backend request có thể bỏ qua gateway nhưng backend không tự xác minh identity, đó là gateway bypass. Không dùng header do client tự gửi để giả lập gateway identity.

### 12.2. Test sunset route

Sau khi disable route cũ, kiểm tra qua từng lớp: DNS/load balancer, gateway, application router và service mesh. Request cũ phải không thể đến business handler; không có event, job hoặc database mutation. Nếu cache/CDN có thể lưu response, kiểm tra invalidation và cache key theo version.

## 13. Test matrix tổng hợp

| Nhóm | Test | Kết quả mong đợi |
|---|---|---|
| Inventory | Runtime route không có trong OpenAPI | Được phát hiện, có owner hoặc finding |
| Inventory | Gateway route không map được backend | Được xử lý như stale mapping |
| Deprecated | Endpoint cũ còn trong thời gian hỗ trợ | Hoạt động theo contract và security baseline hiện hành |
| Deprecated | Anonymous gọi route cũ | Bị từ chối nếu route không public |
| Deprecated | Cross-tenant gọi route cũ | Không đọc/sửa object ngoài tenant |
| Deprecated | Route sau sunset | Không chạy business handler/side effect |
| Shadow | Debug/test route trong production | Không public; tắt hoặc bảo vệ đúng policy |
| Shadow | Route không owner/contract | Được ghi finding và xử lý |
| Internal | Anonymous từ Internet gọi internal route | Không truy cập được |
| Internal | Workload sai identity/scope | Bị từ chối |
| Internal | Direct backend access bypass gateway | Backend vẫn enforce authentication/authorization hoặc network chặn |
| Management | Env/heap dump/thread dump public | Không truy cập được |
| Routing | Encoded path/method override | Không tạo route bypass |
| Data | Internal response có secret/PII | Không lộ ngoài caller được phép |
| Monitoring | Route cũ còn traffic | Có client/version/owner context để migration |
| Audit | Operator truy cập management endpoint | Có audit actor/action/result |
| Network | Internal port public do deployment config | Phát hiện và chặn exposure |
| Side effect | Request bị deny hoặc sunset | Không ghi DB, enqueue hoặc gọi downstream |

## 14. Phân loại finding và mức độ ưu tiên

Đánh giá severity dựa trên khả năng truy cập, mức độ nhạy cảm, quyền cần có và tác động thực tế.

| Mức độ | Ví dụ |
|---|---|
| Critical | Public internal endpoint cho phép thao tác quản trị hoặc truy cập dữ liệu nhạy cảm không cần xác thực |
| High | Deprecated/shadow route bỏ qua object/tenant authorization hoặc gateway auth |
| Medium | Endpoint không có owner/contract, thiếu rate limit hoặc error detail lộ thông tin nội bộ có thể hỗ trợ tấn công |
| Low | Metadata deprecation thiếu, route cũ còn được công bố nhưng đã bảo vệ đúng và có migration plan |

Severity phải dựa trên evidence: request path, caller identity, response, side effect, network reachability và data classification. Không gán Critical chỉ vì route có tên /admin; cần chứng minh exposure và impact trong phạm vi được phép.

## 15. Báo cáo assessment và bằng chứng

Mỗi finding nên có:

- Finding ID, service, environment và endpoint identity.
- Loại: deprecated, shadow, internal hoặc nhiều loại cùng lúc.
- Host/listener/network zone và cách route được truy cập.
- Authentication và authorization behavior đã quan sát.
- Data/action có thể truy cập và tenant/object scope.
- Evidence đã redact: request metadata, status, response excerpt an toàn, trace/audit ID.
- Expected behavior và actual behavior.
- Impact, likelihood và severity.
- Owner, remediation, due date và verification plan.

Không lưu bearer token, API key, cookie, secret hoặc dữ liệu khách hàng thật trong report. Với finding liên quan cross-tenant, dùng synthetic IDs và mô tả kết quả tối thiểu đủ chứng minh. Artifact assessment cần quyền truy cập hạn chế và retention phù hợp.

## 16. Những lỗi đánh giá thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Chỉ scan OpenAPI | Bỏ sót shadow/admin/management route | Đối chiếu runtime, gateway, deployment và traffic |
| Coi endpoint không có traffic là an toàn | Endpoint vẫn có thể public và dễ khai thác | Kết hợp reachability với usage |
| Coi /internal là bảo vệ | Route vẫn có thể public hoặc bị gọi từ workload xâm nhập | Network segmentation + workload identity + authz |
| Chỉ test qua gateway | Không phát hiện direct backend access | Test từ các network zone được phép |
| Chỉ kiểm tra anonymous | Bỏ sót privilege escalation/cross-tenant | Test nhiều principal và tenant |
| Tắt UI nhưng giữ route | API vẫn gọi trực tiếp được | Disable route ở backend và gateway |
| Giữ policy yếu ở version deprecated | Legacy route thành bypass | Security baseline áp dụng mọi version |
| Xóa controller nhưng quên gateway | Route stale vẫn được expose | Verify từng hop và runtime inventory |
| Dựa vào IP nội bộ duy nhất | Workload bị xâm nhập có thể gọi endpoint | mTLS/token scope và least privilege |
| Chỉ assert status code | Request có thể đã tạo side effect | Kiểm tra DB, queue, outbox và downstream |

## 17. Checklist review deprecated, shadow và internal endpoint

- [ ] Có inventory endpoint hợp nhất từ contract, source/router, gateway, deployment, network và runtime telemetry.
- [ ] Mỗi route có owner, exposure class, version, method và security policy.
- [ ] Deprecated endpoint có consumer inventory, replacement, deprecation date và sunset date.
- [ ] Version cũ vẫn có authentication, function/object/tenant/field authorization hiện hành.
- [ ] Endpoint sau sunset không còn business handler, side effect hoặc route public.
- [ ] Shadow endpoint được xác định từ chênh lệch inventory/runtime và có owner xử lý.
- [ ] Debug/test/admin route không bị public ngoài chủ đích.
- [ ] Internal endpoint không dựa vào tên path hoặc vị trí mạng như cơ chế duy nhất.
- [ ] Backend không tin header identity do caller gửi; gateway identity/delegation được xác minh.
- [ ] Direct backend, management port, cluster service và ingress exposure được kiểm tra.
- [ ] Management/diagnostic response không lộ secret, environment hoặc dữ liệu nhạy cảm.
- [ ] Mỗi method/action được test với anonymous, user, tenant admin, service account và operator phù hợp.
- [ ] Có negative test cross-tenant, field access, invalid token và wrong scope.
- [ ] Có test path normalization, rewrite và method handling trong môi trường phù hợp.
- [ ] Test deny/sunset xác minh không có database, queue hoặc downstream side effect.
- [ ] Monitoring nhận diện client/version còn dùng endpoint cũ mà không log secret.
- [ ] Finding có evidence đã redact, severity, owner, due date và verification plan.
- [ ] Remediation bao gồm gateway, application, DNS/network, credentials, SDK và consumer khi liên quan.

Deprecated, shadow và internal endpoint là ba nhóm dễ bị bỏ sót khi chỉ kiểm thử API mới qua tài liệu hiện hành. Đánh giá hiệu quả cần đối chiếu contract với route runtime, gateway và network exposure; thử bằng nhiều identity; kiểm tra direct backend path và xác minh side effect. Endpoint còn cần dùng phải có owner, contract, authentication, authorization và monitoring rõ ràng. Endpoint không còn cần dùng phải được gỡ khỏi toàn bộ đường truy cập. Nhờ đó, route cũ hoặc route ít được biết đến không trở thành lối vòng qua các kiểm soát bảo mật của API.
