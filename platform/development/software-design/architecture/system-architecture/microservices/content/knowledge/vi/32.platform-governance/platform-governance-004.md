# Chuẩn chung cho danh tính, quan sát và hợp đồng

> **Chủ đề:** Software Design · System Architecture · Microservices  
> **Nhóm kiến thức:** Nền tảng và quản trị  
> **Mục tiêu:** Thiết kế bộ tiêu chuẩn nền tảng cho **danh tính (identity)**, **khả năng quan sát (observability)** và **hợp đồng tích hợp (contracts)** để nhiều nhóm phát triển dịch vụ có thể triển khai độc lập mà vẫn bảo mật, vận hành, kiểm chứng tương thích và phối hợp nhất quán.

## 1. Vì sao cần tiêu chuẩn chung trong kiến trúc microservices?

Giả sử tổ chức có Order, Payment, Inventory, Customer, Notification và Reporting services. Mỗi nhóm được chọn ngôn ngữ, framework, database và nhịp phát hành phù hợp. Sự độc lập đó là ưu điểm của microservices, nhưng nếu thiếu những chuẩn tối thiểu thì chi phí tích hợp và vận hành tăng rất nhanh:

- Order Service dùng một cách xác thực JWT, Inventory nhận API key tùy biến, Payment lại tin một header do client gửi.
- Mỗi service đặt một tên khác nhau cho cùng khái niệm người dùng, tenant, transaction và correlation.
- Khi checkout thất bại, log của ba service không có **trace_id** chung; đội vận hành không biết lỗi ở tầng nào.
- Order công bố **amount** là số tiền VND, Payment diễn giải thành đơn vị nhỏ nhất và Reporting đổi cách tính mà không báo consumer.
- API công khai đổi field nhưng không có kiểm tra tương thích với ứng dụng mobile cũ.
- Một nhóm đưa email hoặc orderId vào metric label khiến cardinality tăng, làm hệ quan sát quá tải và chi phí lưu trữ cao.
- Không rõ ai chịu trách nhiệm xử lý khi event schema phá consumer hoặc thiếu dữ liệu giữa hai service.

Bộ tiêu chuẩn nền tảng giải quyết những **giao diện ngang (cross-cutting interfaces)** mà nhiều service phải dùng chung. Nó không nhằm bắt mọi team dùng chung một domain model, một database, một monolith utility library hay một framework duy nhất.

**Ba trụ cột:**

1. **Identity:** Ai hoặc workload nào đang yêu cầu? Quyền truy cập được xác minh và chuyển qua các trust boundary như thế nào?
2. **Observability:** Có thể tái dựng đường đi request, hiểu tình trạng hệ thống và đo SLO mà không làm lộ dữ liệu hay bùng chi phí không?
3. **Contracts:** Producer và consumer thống nhất về schema, semantics, lỗi, phiên bản, độ trễ, idempotency và cách thay đổi tương thích ra sao?

Các trụ cột cần được hỗ trợ bởi **governance nhẹ, automated checks, ownership, tài liệu thực thi và golden paths** để tiêu chuẩn trở thành mặc định dễ dùng, không phải một tài liệu PDF ít người đọc.

## 2. Standardization khác centralization

**Standardization:** Nhiều team độc lập tuân theo cùng những quy tắc cần thiết ở ranh giới. Ví dụ mọi service có service identity rõ, xuất trace context theo chuẩn và công bố OpenAPI được version.

**Centralization:** Một nhóm hoặc hệ thống kiểm soát toàn bộ quyết định và quá trình thực thi. Tập trung quá mức dễ thành bottleneck: mọi service phải chờ platform team thêm endpoint, release hoặc sửa một thư viện chung.

Mục tiêu tốt là **centralize platform capabilities, decentralize domain decisions**:

~~~text
Platform team
  ├── Identity/PKI/secret primitives
  ├── OpenTelemetry collection, schemas, dashboards templates
  ├── API/event contract registries + CI checks
  ├── Starter projects / policy-as-code / golden paths
  └── SLO, security and incident governance

Domain teams
  ├── Own their API/event semantics and data
  ├── Choose safe implementations within guardrails
  ├── Maintain service SLO and incident runbooks
  ├── Verify consumers and backward compatibility
  └── Operate services and fix domain defects
~~~

Một tiêu chuẩn có giá trị khi mô tả rõ **điều bắt buộc**, **điều đề xuất**, **điều tự chọn**, **cách kiểm chứng** và **cách xin ngoại lệ**. Câu “các team nên làm bảo mật tốt” không đủ kiểm chứng.

## 3. Bản đồ các chuẩn nền tảng

| Lớp | Câu hỏi chuẩn cần trả lời | Đầu ra hữu hình |
|---|---|---|
| **User identity** | Ai đăng nhập, token do ai phát, audience nào hợp lệ? | OIDC/OAuth profile, issuer config |
| **Workload identity** | Service A chứng minh là Service A thế nào? | Workload ID, mTLS/short-lived credentials |
| **Authorization** | Principal này được thực hiện hành động gì trên resource nào? | Policy, scopes, role/attribute rules |
| **Trace context** | Request đi qua những service nào? | W3C Trace Context, trace/span IDs |
| **Logs** | Lỗi có được mô tả nhất quán và tìm được không? | JSON log schema, redaction policy |
| **Metrics** | Tình trạng, SLO và saturation có đo được không? | Metric conventions, label budgets |
| **API contracts** | Client/server thống nhất path, types, errors, auth, behavior? | OpenAPI, examples, compatibility report |
| **Event contracts** | Producer/consumer hiểu payload và delivery semantics? | AsyncAPI/schema registry, version policy |
| **Data contracts** | Các phép chiếu có cùng nghĩa, freshness, ownership? | Dataset contract, DQ rules |
| **Governance** | Ai sở hữu, kiểm tra, phê duyệt exceptions? | Service catalog, CI gates, ADR/runbook |

Không bắt buộc mọi công nghệ trong bảng phải dùng ngay. Một tổ chức nhỏ có thể bắt đầu bằng OIDC/JWT, structured logging, tracing và OpenAPI; tổ chức nhiều service có thể cần workload identity, schema registry, policy-as-code và contract broker.

## 4. Nguyên tắc thiết kế tiêu chuẩn chung

1. **Trust boundaries rõ:** Không coi request vào cluster là đáng tin chỉ vì có địa chỉ IP nội bộ.
2. **Least privilege:** Cấp đúng quyền cần dùng và đúng thời hạn cho người dùng/workload.
3. **Explicit contracts:** Không dựa vào “code của hai service tự hiểu nhau” thay cho hợp đồng.
4. **Stable identity:** Service names, contract identifiers và semantic attributes phải có quy tắc nhất quán.
5. **End-to-end context:** Trace ID, error code và thời hạn request không bị mất khi qua proxy, queue hoặc batch.
6. **Fail safe:** Khi không xác minh được token, contract hoặc nguồn telemetry thiết yếu, xử lý theo risk policy chứ không tự cho PASS.
7. **Data minimization:** Logs/traces/tokens chỉ mang thông tin cần thiết, có kiểm soát truy cập và retention.
8. **Backward compatibility by design:** Các phiên bản producer/consumer có thể cùng tồn tại trong rolling deployment.
9. **Automation first:** Kiểm tra schema, policy, static rules và instrumentation bằng CI hoặc admission.
10. **Ownership rõ:** Platform sở hữu primitives; domain team sở hữu ý nghĩa và SLO dịch vụ.
11. **Measured usefulness:** Chuẩn phải giúp giảm incident/lead time/chi phí, không chỉ tăng checklist.
12. **Versioned evolution:** Tiêu chuẩn và công cụ nâng cấp có lộ trình, migration và ngoại lệ có thời hạn.

**Đừng chuẩn hóa mọi thứ.** Tên table, thuật toán domain hoặc cách tổ chức nội bộ có thể khác nhau miễn là boundary behavior và nền tảng được đảm bảo.

## 5. Identity gồm những loại nào?

Trong một request có thể tồn tại đồng thời nhiều danh tính:

- **Human user:** Người dùng đăng nhập vào ứng dụng.
- **Client application:** Ứng dụng web/mobile hoặc batch client được đăng ký.
- **Workload/service:** Order Service hoặc Payment Worker đang chạy.
- **Tenant/organization:** Phạm vi kinh doanh của dữ liệu và quyền truy cập.
- **Operator/administrator:** Người vận hành có đặc quyền.
- **Automation:** CI/CD pipeline, scheduled job hoặc integration agent.

Ví dụ:

~~~text
User Alice
   |
   | đăng nhập qua OIDC
   v
Web/Mobile Client
   |
   | access token dành cho Order API
   v
Gateway → Order Service
           |
           | gọi Payment Service với workload identity của Order
           | cùng ngữ cảnh người dùng được ủy quyền theo policy
           v
        Payment Service
~~~

Không đồng nhất **user identity** với **workload identity**. Payment có thể xác minh lời gọi đến từ Order Service nhưng vẫn cần biết tác vụ có hợp lệ theo quyền user và state nghiệp vụ hay không.

**Dịch vụ gọi nhau an toàn không có nghĩa tự động được quyền xem dữ liệu của mọi user.**

## 6. OAuth 2.0 và OpenID Connect: Vai trò khác nhau

**OAuth 2.0** là framework để ủy quyền truy cập tài nguyên thông qua access tokens và các luồng phù hợp.

**OpenID Connect (OIDC)** bổ sung lớp xác thực danh tính người dùng trên OAuth 2.0, trong đó **ID token** cung cấp thông tin xác thực user cho client OIDC theo hợp đồng.

Một số quy tắc:

- API nhận **access token** phù hợp với chính API, **không dùng ID token như access token** chỉ vì cả hai là JWT.
- Không mặc định mọi access token đều là JWT; chúng có thể opaque và phải introspect qua cơ chế thích hợp.
- Token phải được xác minh **issuer, audience, signature, thời hạn, thuật toán và claims theo policy**.
- Tránh chấp nhận JWT do một issuer tùy ý mà client đưa vào; issuer/trust configuration phải được quản lý.
- Web/mobile public clients dùng flow phù hợp với đặc tính client; **Authorization Code + PKCE** thường là lựa chọn cho client phù hợp, không lưu client secret trong mobile code.
- Với service-to-service, có thể dùng workload identity, mTLS, client credentials hoặc token exchange tùy threat model.
- Authorization không thể chỉ dựa vào claim **authenticated=true**.

### 6.1. Vì sao cần audience?

Một token được cấp cho **Inventory API** không nên được Payment API chấp nhận chỉ vì chữ ký của cùng Identity Provider hợp lệ. Audience **aud** thể hiện resource nhận token được hướng tới. Bỏ kiểm tra audience có thể tạo **token confusion** và vi phạm ranh giới giữa các dịch vụ.

Tương tự, một token có scope **orders.read** không tự cấp quyền **payments.refund**.

## 7. Chuẩn xác minh token cho API

Một profile tham khảo cho resource server:

1. **Trusted issuer(s)** được cấu hình sẵn.
2. **Audience** phải khớp service/API được cấp.
3. **Signature** được kiểm bằng key/metadata từ nguồn tin cậy, có cache và rotation policy.
4. **Temporal claims** gồm **exp**, **nbf**, **iat** theo chính sách; chỉ cho phép clock skew nhỏ, có kiểm soát.
5. **Algorithm allowlist** không tin thuật toán tự khai nếu không được policy cho phép.
6. **Scopes/permissions** phải được xác minh theo endpoint/operation.
7. **Tenant/subject** được giải thích theo namespace và ownership rõ.
8. **Revocation/short lifetime** phù hợp risk model; không tự coi JWT là có thể revoke tức thời nếu không có cơ chế.
9. **Failure behavior** khi không lấy được keys/identity provider phải rõ ràng; tránh tự cho qua.
10. **Audit** các hành động đặc quyền nhưng không log nguyên token.

Ví dụ Spring Boot application configuration:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.com/realms/shop
~~~

Đây chỉ là **bước cấu hình issuer** cho môi trường ứng dụng tương thích, không phải một security policy hoàn chỉnh. Cần thêm **audience validation**, endpoint authorization, clock-skew/algorithm policy nếu cần và integration tests. Chi tiết API cấu hình phụ thuộc phiên bản Spring Security thực tế.

Ví dụ định nghĩa quyền theo HTTP method:

~~~java
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/api/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .requestMatchers(HttpMethod.POST, "/api/orders")
                .hasAuthority("SCOPE_orders.write")
            .anyRequest().authenticated())
        .oauth2ResourceServer(oauth2 -> oauth2.jwt(Customizer.withDefaults()))
        .build();
}
~~~

**Hàm trên là ví dụ định hướng**, chưa đầy đủ CSRF/session policies, actuator/public endpoints và validation của object-level ownership. Nếu server dùng browser cookies/session, CSRF cần xử lý theo ranh giới đó; không tắt mặc định chỉ để tests xanh. Bản production phải có audience validator và tests cho 401/403.

## 8. Authentication, authorization và object ownership

**Authentication** trả lời “principal là ai?”.  
**Authorization** trả lời “principal được làm gì với resource này?”.

Ví dụ Alice có token hợp lệ và scope **orders.read**, nhưng Alice không phải chủ của đơn **ORDER-BOB**. Để tránh BOLA/IDOR:

~~~text
GET /api/orders/ORDER-BOB
Authorization: Bearer <valid access token for Alice>

Expected:
  Reject theo resource ownership/tenant policy
  Không trả nội dung đơn của Bob
~~~

Các rules có thể xét:

- **Subject:** user ID, service principal hoặc delegated actor.
- **Action:** read, create, cancel, refund.
- **Resource:** order/payment/tenant/customer cụ thể.
- **Context:** tenant, environment, risk, amount, MFA/step-up khi cần.
- **Policy version:** phiên bản quy tắc được áp dụng và dấu vết audit.

RBAC dùng roles/scopes cho cấp quyền rộng; ABAC/ReBAC/domain checks có thể cần để kiểm tra object-level permissions. Gateway có thể kiểm tra một số điều kiện đầu vào, nhưng **service sở hữu dữ liệu phải thực thi kiểm tra truy cập cần thiết ở boundary của nó**.

### 8.1. 401 khác 403

- **401 Unauthorized:** request thiếu hoặc không có credentials hợp lệ theo cơ chế của API; có thể yêu cầu xác thực.
- **403 Forbidden:** đã có ngữ cảnh xác thực nhưng không đủ quyền theo policy.
- Có thể chọn 404 để không lộ sự tồn tại của tài nguyên theo thiết kế; phải nhất quán, không biến đó thành cách bỏ logging/audit.

Response không nên tiết lộ nguyên token, group membership nội bộ hoặc chi tiết policy nhạy cảm.

## 9. Workload identity: Service cũng phải chứng minh danh tính

Trong Kubernetes, tên Deployment, IP Pod và namespace labels giúp tổ chức tài nguyên, nhưng **không tự tạo một bằng chứng danh tính mật mã** đối với mọi giao tiếp mạng.

Các cơ chế thường dùng:

- **mTLS:** hai phía xác minh certificate identity khi kết nối.
- **SPIFFE-style IDs:** danh tính workload theo trust domain và workload selector được kiểm chứng.
- **Short-lived service tokens:** cấp cho workload dựa trên trust được thiết lập, tránh secret tồn tại quá lâu.
- **Cloud workload identity federation:** workload chứng minh danh tính qua cơ chế cloud/Kubernetes phù hợp để nhận token ngắn hạn.
- **Service mesh:** có thể cấp certificates, thực thi mTLS và identity-based policies trong phạm vi được triển khai.

Ví dụ danh tính logic:

~~~text
spiffe://shop.example/ns/orders/sa/order-api
spiffe://shop.example/ns/payments/sa/payment-api
~~~

Đây là **format minh họa**, không khẳng định hai string là identities đang tồn tại trong bất kỳ cluster nào. Trust domain, selectors và policy cần được hệ thống cấp danh tính kiểm chứng.

**Không đồng nhất Kubernetes ServiceAccount token với một access token được mọi API chấp nhận.** Token audience và trust policy cần được cấu hình cho resource nhận.

### 9.1. mTLS không thay business authorization

Order có certificate hợp lệ không có nghĩa nó được quyền gọi **refund** cho mọi khách hàng. Payment phải kiểm tra operation, tenant, delegated authority và state nghiệp vụ.

mTLS chứng minh một workload connection theo trust configuration; business authorization quyết định quyền dùng tài nguyên cụ thể.

## 10. Chuyển danh tính qua các tầng mà không đánh mất trust boundary

Một request có thể đi qua:

~~~text
User → Gateway → Order → Payment → External Provider
              |
              +--> Kafka Event → Reporting Consumer
~~~

Các rủi ro:

- Gateway nhận **X-User-Id** do client tự đặt rồi để các service tin là danh tính đã xác minh.
- Order chuyển nguyên user access token cho mọi service, dù token chỉ có audience Order.
- Payment không biết request được gửi bởi workload nào.
- Consumer Kafka lấy một field **requestedBy** không được bảo vệ và xem đó là quyền admin.
- Trace baggage vô tình mang email/JWT đi khắp service.

Giải pháp:

1. Gateway xác minh credentials/áp dụng policy của chính nó, **không mặc định tin headers từ Internet**.
2. Mỗi receiving service xác minh token hoặc trusted, integrity-protected identity assertion theo kiến trúc.
3. Khi cần **on-behalf-of/delegation**, dùng token exchange hoặc cơ chế delegation phù hợp, có audience, scope, expiry cụ thể; không tự ký “user header” không kiểm chứng.
4. Phân biệt **initiating user** với **calling service** trong audit.
5. Message metadata chỉ là dữ liệu không đáng tin trừ khi integrity/source được bảo vệ theo policy.
6. Không đưa secrets/PII vào trace propagation headers.
7. Ghi principal/tenant identifiers trong audit theo policy bảo mật và cardinality budget.

Một request có thể vừa được xác thực bởi **Order Service workload identity**, vừa mang ngữ cảnh **Alice initiated checkout**; Payment vẫn phải quyết định những quyền nào thực sự được delegate.

## 11. Multi-tenancy là ranh giới bảo mật, không chỉ một nhãn

Trong hệ thống nhiều khách hàng doanh nghiệp:

- Dữ liệu có thể dùng **tenant_id** trong primary/unique keys.
- Access token có thể có tenant context, nhưng phải đối chiếu với resource ownership.
- Một người dùng có thể được phép thao tác nhiều tenants theo vai trò; không chọn tenant bằng một header tùy ý không kiểm chứng.
- Cần tenant isolation ở query, cache keys, blob paths, event partitioning hoặc policy DB theo mô hình thực tế.
- Audit records phải chỉ rõ actor, tenant scope, resource và action.
- Metrics có thể nhóm theo **tenant tier** thay vì tenant_id khi số tenants lớn.

Ví dụ lỗi:

~~~sql
-- NGUY HIỂM nếu order_id chỉ unique trong mỗi tenant.
SELECT *
FROM orders
WHERE order_id = :order_id;

-- Đúng hơn nếu thiết kế yêu cầu tenant-scoped keys.
SELECT *
FROM orders
WHERE tenant_id = :authorized_tenant_id
  AND order_id = :order_id;
~~~

Biến **authorized_tenant_id** phải được xác lập qua chính sách truy cập, không copy từ query parameter mà không kiểm chứng.

## 12. Chuẩn secret management và credential lifecycle

Một API có thể chuẩn hóa OAuth nhưng vẫn lộ secret nếu pipeline và runtime quản lý kém.

Yêu cầu nền tảng thường gồm:

- Không commit password, API key, private key hoặc token vào repository.
- Dùng secret manager/KMS/HSM hoặc cơ chế được phê duyệt để quản lý bí mật.
- Ưu tiên **short-lived credentials** và workload federation khi phù hợp.
- Quy định rotation, revocation, audit và behavior khi credential hết hạn.
- Tách quyền **đọc secret**, **sửa secret** và **quản lý policy**.
- CI từ pull request không tin cậy không được nhận deploy credentials production.
- Logs, traces, crash dumps và error responses không chứa bí mật.
- Có khả năng emergency revoke/rotate khi nghi ngờ lộ.
- Phân biệt encryption key management với signing key management và retention policy.

**Một secret được mã hóa trong Kubernetes Secret không tự đồng nghĩa hoàn toàn an toàn.** Phải cấu hình encryption-at-rest, RBAC, access logging và đường cấp secret phù hợp môi trường; đồng thời bảo vệ cluster control plane và backup chứa Secrets.

## 13. Identity standards cần có hồ sơ kiểm thử

Những kịch bản tối thiểu:

| Kịch bản | Kỳ vọng |
|---|---|
| Không có token | 401 hoặc hợp đồng xác thực tương ứng |
| Token hết hạn | Bị từ chối |
| Token sai issuer | Bị từ chối |
| Token chữ ký sai | Bị từ chối |
| Token hợp lệ nhưng sai audience | Bị từ chối |
| Token scope không đủ | 403 hoặc chính sách tương đương |
| User A đọc dữ liệu tenant B | Bị từ chối không lộ dữ liệu |
| Service token giả mạo từ workload khác | Bị từ chối |
| Key rotation trong IdP | Token mới/cũ xử lý đúng thời hạn chuyển tiếp |
| Token đã revoke theo cơ chế ứng dụng | Hành vi đúng revocation policy |
| Delegated token vượt quyền user gốc | Bị từ chối |
| Identity provider tạm unavailable | Có failure behavior rõ, không auto-bypass |
| Auditing cho refund/admin action | Có actor và business context tối thiểu, không log token |

Test ở API và trust boundaries, không chỉ test utility parse JWT. Có thể dùng identity provider test fixture, JWKS mock an toàn và tests giao tiếp service-to-service; cần phân biệt kiểm tra mô phỏng và cấu hình production.

## 14. Observability: Ba nguồn tín hiệu và ngữ cảnh liên kết

**Logs:** Các sự kiện chi tiết được ghi có cấu trúc.  
**Metrics:** Dữ liệu định lượng theo thời gian để đo health, SLO, saturation.  
**Traces:** Đường đi và thời gian các thao tác trong một yêu cầu phân tán.

~~~text
               Single checkout request
                           |
                        Trace ID
                           |
        +------------------+------------------+
        |                  |                  |
      Gateway            Order              Payment
      span A             span B             span C
        |                  |                  |
        +------------------+------------------+
                           |
                           v
         Metrics: request count, duration, errors
         Logs: structured event with trace_id
         Traces: spans, attributes, parent/child context
                           |
                           v
               Alert, query, diagnosis
~~~

Một hệ thống quan sát tốt cần trả lời:

1. Request nào bị lỗi và ảnh hưởng bao nhiêu người?
2. Lỗi xuất hiện tại service/operation nào?
3. Có liên quan deployment/config/version vừa thay không?
4. Downstream dependency, database, queue hay external provider chậm?
5. Mức độ ảnh hưởng tới SLO và business outcomes?
6. Ai nhận alert và runbook nào phải dùng?

**Chỉ có log files không có correlation cũng khó chẩn đoán như chỉ có dashboard CPU.** Tiêu chuẩn chung giúp liên kết các dữ liệu với nhau.

## 15. Chuẩn resource identity trong telemetry

Mỗi telemetry record nên có **resource attributes** đủ để nhận diện nguồn phát:

- **service.name:** Tên logic ổn định của dịch vụ.
- **service.namespace:** Không gian tên logic, có thể dùng phân nhóm service/domain theo conventions.
- **service.version:** Phiên bản release, image digest hoặc version label có kiểm soát.
- **deployment.environment.name** hoặc thuộc tính môi trường tương ứng theo semantic conventions/version đang dùng.
- **cloud.region / k8s.namespace.name / k8s.pod.name:** Khi infrastructure instrumentation hỗ trợ và phù hợp dữ liệu.
- **service.instance.id:** Khi cần phân biệt instance, có giới hạn cách sử dụng trong metric labels.

Ví dụ thông tin:

~~~text
service.name=order-api
service.namespace=shop
service.version=1.4.2
deployment.environment.name=production
k8s.namespace.name=shop-prod
cloud.region=example-region
~~~

Đây là **giá trị minh họa**. OpenTelemetry semantic conventions có thể phát triển theo phiên bản; platform nên chọn một phiên bản/compatibility policy và migration plan, thay vì các team tự đổi tên attributes tùy ý.

Phân biệt **resource attributes** với **metric labels**: không phải mọi resource attribute nên xuất hiện dưới dạng một dimension của mọi metric. Pod/instance IDs có thể có cardinality cao; collector/backend cần chính sách hữu hạn.

## 16. W3C Trace Context: Duy trì trace xuyên HTTP

W3C Trace Context định nghĩa các header phổ biến như **traceparent** và **tracestate**. Trước khi tạo span mới cho một HTTP request, server instrumentation có thể trích xuất context hợp lệ từ upstream để liên kết các spans.

Một traceparent có cấu trúc minh họa:

~~~text
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
~~~

Các thành phần gồm version, trace ID, parent/span ID và trace flags. Header trên là **ví dụ định dạng**; cần validate chuẩn, không tự parse bằng tách chuỗi đơn giản nếu dùng thư viện instrumentation chuẩn.

Dòng chảy:

~~~text
Gateway root/server span
   |
   | inject trace context vào HTTP request
   v
Order server span
   |
   +--> DB client span
   |
   +--> Payment HTTP client span
                |
                v
          Payment server span
                |
                +--> Provider client span
~~~

Lưu ý:

- Traceparent từ Internet là **context được cung cấp bởi caller**, không phải bằng chứng danh tính.
- Không dùng trace ID làm authentication token.
- Không tin các attribute bên ngoài như user role, admin flag chỉ vì chúng nằm trong baggage.
- Instrumentation có thể khởi tạo trace mới nếu context không hợp lệ hoặc trust policy yêu cầu.
- Sampling flags hướng dẫn behavior trace sampling; không đảm bảo toàn bộ spans luôn được lưu.

## 17. Async tracing với Kafka, RabbitMQ và scheduled tasks

Message-driven flows không có một HTTP call chain liên tục. Một event có thể được enqueue, retry, tiêu thụ bởi nhiều consumers hoặc xử lý sau hàng giờ.

~~~text
Order Service
  |
  | publish OrderConfirmed (event_id, trace context)
  v
Broker topic / queue
  |
  +--> Inventory Consumer
  |
  +--> Notification Consumer
  |
  +--> Reporting Consumer
~~~

Nên chuẩn hóa:

- **event_id / message_id:** Định danh sự kiện phục vụ dedup và audit.
- **correlation_id:** Gắn các nghiệp vụ liên quan theo hợp đồng, không phải secret.
- **trace context:** Context propagation theo messaging instrumentation và trust policy.
- **causation_id:** Tùy domain, ID của command/event gây ra sự kiện hiện tại.
- **consumer group / operation:** Thuộc tính phục vụ chẩn đoán.
- **dead-letter/retry metadata:** Số lần thử và nguyên nhân theo format đã chuẩn hóa.

Không ép mọi message consumption là child span trực tiếp của request gốc nếu semantics là xử lý bất đồng bộ sau rất lâu hoặc fan-out; **span links** có thể phù hợp để mô tả quan hệ không phải parent/child liên tục.

Trace và event id phục vụ **quan sát**, không thay điều kiện nghiệp vụ về idempotency hoặc chữ ký/xác thực thông điệp.

## 18. Structured logging: Một schema chung hữu ích hơn các chuỗi tùy ý

Ví dụ log ở dạng JSON:

~~~json
{
  "timestamp": "2026-11-12T09:00:00Z",
  "severity": "ERROR",
  "service.name": "order-api",
  "service.version": "1.4.2",
  "environment": "production",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "span_id": "00f067aa0ba902b7",
  "event_name": "payment.authorization.failed",
  "error_code": "PAYMENT_PROVIDER_TIMEOUT",
  "operation": "authorize",
  "duration_ms": 1500,
  "retry_attempt": 1,
  "message": "Payment provider did not respond within deadline"
}
~~~

**Tên field là profile minh họa**; đội nền tảng nên ánh xạ với log semantic conventions/exporter thực tế, tránh service này dùng **traceId** và service kia dùng **trace_id** mà không có mapping.

Các trường nên có:

- Timestamp có timezone/UTC, timezone policy rõ.
- Severity chuẩn hóa và tên sự kiện có cấu trúc.
- Service/resource identity.
- Trace/span IDs khi có context.
- Error code ổn định và loại thao tác.
- Duration, attempt count và dependency nếu cần.
- Định danh nghiệp vụ tối thiểu khi thật sự cần, dưới chính sách data classification.
- Không log token, password, card details, OTP hoặc raw payload nhạy cảm.

**Một log line là dữ liệu, không phải nơi đưa secrets chỉ để tiện debug.**

## 19. Quy tắc log level và tránh noise

| Level | Mục đích | Ví dụ |
|---|---|---|
| **DEBUG/TRACE** | Chẩn đoán chi tiết, nên kiểm soát mức và phạm vi | Các bước nội bộ không nhạy cảm |
| **INFO** | Sự kiện vận hành quan trọng, thành công milestone | Bắt đầu/hoàn tất tác vụ lớn |
| **WARN** | Bất thường có thể hồi phục, chưa thất bại | Retry có kiểm soát, nguồn dữ liệu đến chậm |
| **ERROR** | Thao tác thất bại hoặc invariant quan trọng vi phạm | Charge outcome unknown, failed transaction |

Không in log **INFO cho mỗi câu SQL**, mỗi request heartbeat hoặc mỗi object nhỏ ở traffic rất lớn; số bản ghi sẽ tăng theo RPS và chi phí. HTTP request count/latency nên ưu tiên metrics, truy vết mẫu và logs được thiết kế phù hợp.

Không log cùng một exception là ERROR năm lần ở năm tầng nếu không tạo thêm ngữ cảnh. Có thể ghi một event lỗi chủ đạo tại boundary có trách nhiệm, đồng thời trace còn thể hiện đường đi.

## 20. Trace/log correlation trong Java/Spring

Một service Spring Boot có thể tích hợp OpenTelemetry instrumentation, Micrometer Tracing hoặc cách được platform hỗ trợ. Cần chuẩn hóa:

- Instrumentation tạo và kết thúc spans đúng lifecycle.
- HTTP client tự inject context qua interceptor/instrumentation.
- Server tự extract context và tạo server spans.
- MDC/log encoder chứa trace_id/span_id theo cấu hình.
- Context không bị mất khi chuyển thread, CompletableFuture, Reactor, executor hoặc messaging.
- Async tasks xử lý cancellation và tránh dùng context đã hết vòng đời.
- Propagation dùng trusted libraries, không tự sinh một chuỗi “X-Trace-Id” rồi mặc định đó là trace chuẩn.

Ví dụ environment variables OpenTelemetry khái niệm:

~~~text
OTEL_SERVICE_NAME=order-api
OTEL_RESOURCE_ATTRIBUTES=service.namespace=shop,service.version=1.4.2
OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector.observability.svc:4317
OTEL_TRACES_EXPORTER=otlp
OTEL_METRICS_EXPORTER=otlp
OTEL_LOGS_EXPORTER=otlp
~~~

Transport/protocol, TLS, authentication và exporter support phụ thuộc SDK/agent/version; endpoint **4317** thường được dùng cho OTLP/gRPC trong cấu hình thích hợp nhưng không phải bảo đảm ở mọi collector. Trong production, telemetry pipeline phải có **network policy, credentials, TLS và resource budgets** đúng.

Đừng kết luận tracing hoạt động chỉ vì biến môi trường tồn tại. Cần gửi một synthetic request và xác minh span gắn đúng service/trace context ở backend.

## 21. Metrics chung: RED, USE và business SLI

### RED cho request-serving services

- **Rate:** Requests/s hoặc operations/s.
- **Errors:** Tỷ lệ lỗi theo phân loại có ý nghĩa.
- **Duration:** Thời gian response, histogram và percentiles tại hệ thống quan sát.

### USE cho tài nguyên

- **Utilization:** Mức dùng của tài nguyên.
- **Saturation:** Queue length, connection pending, threads/CPU throttling.
- **Errors:** Lỗi ở tài nguyên.

### Business SLIs

- Tỷ lệ checkout thành công.
- Số payment authorized/captured theo trạng thái nghiệp vụ.
- Đơn hàng không bị xử lý trùng.
- Thời gian từ OrderConfirmed tới InventoryReserved.
- Tỷ lệ sự kiện nằm trong freshness objective.

Ví dụ metric names minh họa:

~~~text
http_server_requests_total{service="order-api",route="/orders/{id}",method="GET",status_class="2xx"}
http_server_request_duration_seconds_bucket{service="order-api",route="/orders/{id}",le="0.5"}
payment_authorization_attempts_total{service="payment-api",outcome="timeout"}
kafka_consumer_lag{service="reporting-worker",topic="order-events",group="reporting"}
db_connection_pool_pending{service="order-api",pool="orders"}
~~~

Tên ở đây là **profile đề xuất**, không khẳng định SDK/exporter mặc định cung cấp đúng chúng. Platform phải chọn một convention/canonical mapping và đảm bảo dashboards/alerts tương thích.

**Metric phải phản ánh service boundary**, còn business events phải có định nghĩa không tạo đo đếm trùng khi retry/duplicate delivery.

## 22. Cardinality budgets và quy tắc về labels

Sai lầm thường gặp:

~~~text
http_requests_total{user_id="alice",order_id="O1",raw_path="/orders/O1"}
http_requests_total{user_id="bob",order_id="O2",raw_path="/orders/O2"}
...
~~~

Số series có thể tăng theo users × orders × routes × statuses × pods, gây chi phí cao và giảm khả năng truy vấn.

Nên dùng labels hữu hạn:

~~~text
http_requests_total{
  service="order-api",
  method="GET",
  route="/orders/{id}",
  status_class="2xx"
}
~~~

Các quy tắc:

1. Dùng **route template**, không dùng raw URL/path chứa IDs.
2. Không đưa request_id, trace_id, session_id, email, phone, order_id vào metric labels.
3. Nếu cần tenant breakdown, cân nhắc **tenant tier** hoặc bounded groups, trừ trường hợp có budget explicit.
4. Đặt **per-metric series budget** và retention/storage tier phù hợp.
5. Monitor series count, churn, label cardinality, ingestion failures và backend cost.
6. Histogram buckets phải chọn theo SLO; quá nhiều buckets × labels cũng làm tăng series.
7. Cân nhắc aggregation/recording rules và sampling logs/traces theo nhu cầu chẩn đoán.

**Metrics dùng để đo quy mô, traces/logs có thể giữ chi tiết từng request trong phạm vi retention và truy cập phù hợp.**

## 23. Sampling, retention và privacy trong observability

**Trace sampling** giúp giảm chi phí lưu khi hệ thống xử lý rất nhiều requests:

- **Head-based:** quyết định sớm khi bắt đầu trace; dễ triển khai nhưng có thể bỏ sót lỗi hiếm.
- **Tail-based:** xét spans/trace information sau một khoảng thời gian để ưu tiên traces có lỗi/chậm; cần bộ nhớ, routing/collector design và định nghĩa sampling rules.
- **Parent-based:** kế thừa quyết định sampling theo propagated context trong những trường hợp phù hợp.
- **Log sampling:** giảm volume logs lặp lại, nhưng có exceptions cho security/audit records theo policy.
- **Metrics:** thường cần độ đầy đủ cho SLI quan trọng; không trực tiếp lấy số request tổng từ một mẫu trace không được hiệu chỉnh.

Lưu ý:

- Không thể suy ra tỷ lệ lỗi production từ tỷ lệ lỗi trong các traces bị **tail-sampling ưu tiên lỗi**, vì mẫu bị thiên lệch.
- Audit/security logs có nghĩa vụ lưu riêng; không áp sampling bừa bãi.
- Trace exporter có thể phải loại bỏ attributes nhạy cảm trước khi ra khỏi trust boundary.
- Retention tách theo logs, metrics, traces và pháp lý/cost/SLO requirements.
- Khi collector bị nghẽn hoặc exporter drop spans, phải có metrics báo telemetry loss, không giả định “không có span = request không xảy ra”.

## 24. Alerting và SLO: Từ dashboard sang khả năng hành động

Một dashboard đẹp nhưng không có on-call owner hoặc alert policy sẽ không tạo giá trị khi xảy ra sự cố.

Mỗi service cần có:

- **SLI/SLO** theo user-facing behavior.
- **Error budget** và chính sách khi tiêu thụ nhanh.
- Alert ngắn gọn về symptoms có tác động, tránh alert cho mọi CPU spike.
- Incident severity, paging routing và owner.
- Runbook với steps xác minh request path, downstream, rollout và rollback.
- Links từ alert tới dashboards, traces, logs và deployment history.
- Cơ chế kiểm tra sau incident để cập nhật instrumentation/contract tests.

Ví dụ SLO:

~~~text
Order API availability:
  eligible requests successful / total eligible requests
  target: 99.9% in rolling 30 days

Order latency:
  fraction of eligible requests <= 500ms
  target: 99% in rolling 30 days
~~~

Đây là **ví dụ**, không phải SLO mặc định. Phải định nghĩa eligible requests, lỗi 4xx theo policy, timeout ở đâu đo và cách xử lý planned maintenance. Không coi mọi HTTP 404 là server failure; cũng không bỏ qua payment 503 chỉ vì caller map nó thành 200 với status body FAILED.

## 25. Error taxonomy chung

Không nên để mỗi service tạo một kiểu lỗi tùy hứng:

~~~json
{
  "type": "https://errors.example.com/payment/capacity",
  "title": "Payment temporarily unavailable",
  "status": 503,
  "code": "PAYMENT_CAPACITY_EXCEEDED",
  "detail": "Please retry later",
  "correlationId": "example-correlation-id"
}
~~~

Một profile có thể dựa trên **Problem Details cho HTTP APIs** hoặc error envelope tương đương, nhưng phải chọn và công bố cụ thể.

Nguyên tắc:

- HTTP status diễn đạt loại kết quả ở HTTP layer.
- Error **code** ổn định cho xử lý máy.
- Correlation/trace ID dùng để hỗ trợ support/diagnostics, không chứa thông tin nhạy cảm.
- Phân biệt **validation**, **authentication**, **authorization**, **not found**, **conflict**, **rate limited**, **unavailable**, **timeout**, **unknown outcome**.
- Không trả stack trace, raw SQL, secrets hoặc tên topology nội bộ cho client.
- API clients phải hiểu **retryability** và **idempotency** chứ không tự retry mọi 5xx.
- Các service có thể có domain-specific codes nhưng phải nằm trong taxonomy chung và có owner.

**Trace IDs không thay thế business transaction IDs**, còn HTTP status không thay toàn bộ semantics nghiệp vụ.

## 26. Hợp đồng HTTP API: Không chỉ OpenAPI schema

Một API contract đầy đủ cần bao gồm:

1. **Method, path và base URL/service discovery.**
2. **Request/response schema**, required/optional fields, nullability.
3. **Authentication** và authorization scopes/audience.
4. **HTTP statuses** cùng error codes.
5. **Pagination, sorting, filtering** và maximum payload size.
6. **Timeout, retry và idempotency semantics.**
7. **Units, timezone, enum meaning**, currency/precision.
8. **Versioning và compatibility policy.**
9. **Rate limits/quotas** và overload response.
10. **Data classification**/redaction cho fields nhạy cảm.
11. **Ownership, support contact và deprecation schedule.**
12. **Availability/freshness SLO** nếu consumer phụ thuộc.

OpenAPI là định dạng mô tả API mạnh nhưng không chứng minh mọi business invariant tự động. Ví dụ **amount** vẫn là integer sau khi chuyển từ VND sang minor units; syntax checker không nhận ra nếu không có semantic contract/tests.

## 27. Ví dụ OpenAPI contract cho Order

~~~yaml
openapi: 3.0.3
info:
  title: Order API
  version: "1.0.0"
paths:
  /orders/{orderId}:
    get:
      operationId: getOrder
      security:
        - bearerAuth: []
      parameters:
        - name: orderId
          in: path
          required: true
          schema:
            type: string
      responses:
        "200":
          description: Order found
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/Order"
        "401":
          description: Missing or invalid credentials
        "403":
          description: Insufficient permission
        "404":
          description: Order not found or intentionally hidden
components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
  schemas:
    Order:
      type: object
      required: [id, status, amountMinor, currency]
      properties:
        id: { type: string }
        status:
          type: string
          enum: [PENDING, CONFIRMED, CANCELLED]
        amountMinor:
          type: integer
          format: int64
          description: Amount in minor units of the currency
        currency:
          type: string
          description: Currency code
~~~

Đây là **OpenAPI minh họa**. Trong triển khai thật cần document OAuth2 security flows/scopes nếu phù hợp, response headers, error schema, examples, constraints và status transition rules. Không tự mặc định bearerAuth = OAuth2 token validation đã được cấu hình đủ.

### 27.1. Vì sao phải version contract?

Source code của provider có thể thay độc lập với các consumers đã deploy. Hợp đồng phải được lưu và phát hành theo **version API** cùng lịch sử, không chỉ tồn tại trong controller annotations ở branch mới nhất.

Có thể dùng contract-first hoặc code-first, miễn là CI luôn kiểm tra spec được sinh ra đúng với implementation và so với baseline mà consumers đang dùng.

## 28. API compatibility: Các thay đổi nguy hiểm

| Thay đổi | Khả năng phá consumer |
|---|---|
| Xóa endpoint/path/method | Cao |
| Đổi tên/xóa response field mà consumer cần | Cao |
| Đổi kiểu field | Cao |
| Biến optional request field thành required | Cao |
| Đổi units/semantics nhưng giữ type | Rất cao vì khó phát hiện tự động |
| Thêm enum value | Có thể phá exhaustive switch ở consumer |
| Đổi nghĩa của HTTP status/error code | Có thể phá retry/UX logic |
| Đổi audience/scope/token policy | Có thể khiến client bị 401/403 |
| Thêm optional response field | Thường tương thích nhưng strict parsers có thể lỗi |
| Thêm optional request field | Thường ít rủi ro nếu default semantics rõ |
| Đổi pagination cursor/sort order | Có thể tạo lặp hoặc mất bản ghi |
| Đổi max payload/rate limit đột ngột | Có thể làm client hiện tại thất bại |

**Breaking change không chỉ là thay đổi YAML schema.** Cần kiểm tra consumer assumptions, nghĩa dữ liệu, security policy và behavior của các client lâu đời (đặc biệt mobile/public APIs).

Một policy thực dụng:

- So sánh spec mới với **published baseline đang được tiêu thụ**.
- Chạy provider/consumer contract verification.
- Có deprecation window và usage telemetry khi loại field.
- Dùng **expand–migrate–contract** khi consumers deploy độc lập.
- Không giả định deploy toàn bộ services đồng thời.

## 29. Consumer-driven contracts

Trong mô hình CDC, mỗi consumer mô tả tương tác kỳ vọng từ provider:

~~~text
Billing Consumer
    |
    | Contract: GET /orders/{id} returns
    | id, amountMinor, currency, status
    v
Versioned contract broker/repository
    |
    v
Order Provider
    |
    | Verify implementation đáp ứng contract
    v
Verification result tied to provider version
~~~

Có thể dùng Pact hoặc hệ thống kiểm thử tương đương. Điểm quan trọng không phải tên công cụ mà là:

1. Contract do consumer test tạo ra hoặc được review.
2. Provider được verify với **chính contract đó**.
3. Kết quả gắn với **consumer version / provider version** và môi trường.
4. Gate deploy xét **consumers hiện đang chạy hoặc dự định chạy**, không chỉ contract mới nhất.
5. Có kế hoạch migrate khi thay đổi breaking.

Mock consumer riêng mà không verify provider thật sẽ không tự bảo vệ trước breaking change của provider.

CDC không thay toàn bộ integration tests: provider có thể trả đúng shape nhưng ghi transaction sai hoặc có bug concurrency mà contract test chưa diễn tả.

## 30. Event contracts cho message-driven services

Một event có thể được nhiều consumers đọc, tồn tại qua nhiều phiên bản service và có semantics khác HTTP response.

Ví dụ envelope:

~~~json
{
  "eventId": "evt-example-123",
  "eventType": "OrderConfirmed",
  "eventVersion": 2,
  "occurredAt": "2026-11-12T09:00:00Z",
  "aggregateId": "ORD-1001",
  "correlationId": "corr-example-123",
  "producer": "order-service",
  "payload": {
    "orderId": "ORD-1001",
    "amountMinor": 590000,
    "currency": "VND"
  }
}
~~~

Hợp đồng event cần:

- **Type/version** và schema identifier.
- **Event ID** để dedup, **aggregate ID** cho ordering/partitioning nếu phù hợp.
- **OccurredAt** với UTC/clock-skew policy.
- **Payload semantics** gồm units, nullability, enums.
- **Delivery guarantees** như at-least-once, retries và duplicates.
- **Ordering/partition key** và những chỗ không được giả định global ordering.
- **Consumer compatibility** và thời gian tồn tại event cũ trong retention.
- **Idempotency, replay, dead-letter handling, observability context.**
- **Security classification** và quyền subscribe.
- **Tombstone/deletion/privacy** theo data lifecycle.

**Schema-compatible không đồng nghĩa semantic-compatible.** Một consumer hiểu JSON mới nhưng số tiền đổi đơn vị vẫn có thể tạo lỗi nghiêm trọng.

## 31. Schema registry và compatibility policies

Với Kafka/Avro/Protobuf/JSON Schema, có thể dùng schema registry hoặc kho schema đã version hóa. Một số chính sách thường gặp: **backward**, **forward**, **full**, và các biến thể **transitive**, nhưng định nghĩa chính xác phụ thuộc format/công cụ.

Quyết định mode phải xuất phát từ thực tế:

- Consumers thường được nâng cấp trước hay providers trước?
- Có replay events cũ từ nhiều tháng trước không?
- Schema evolution có default values và field numbering/aliases theo định dạng không?
- Có được phát event type mới song song với cũ?
- Có thể chặn producer thay đổi semantics mà vẫn cùng schema không?
- Có tiêu chuẩn ownership cho shared/common schemas không?

**Không chỉ dựa vào schema registry PASS.** Nó kiểm tra phần tương thích ở mức định dạng theo quy tắc của engine, không thể biết domain semantics như “trạng thái CANCELLED có hoàn tiền chưa”.

## 32. Data contracts cho dữ liệu phân tích và CDC

Một bảng analytics do service tạo ra cũng cần hợp đồng, nhất là khi dùng event/CDC:

~~~yaml
dataset: order-events
owner: order-domain
version: "2"
primaryKeys: [eventId]
dataClassification: internal
semantics:
  amountMinor: amount in currency minor units
  occurredAt: UTC event occurrence timestamp
quality:
  requiredFields: [eventId, orderId, eventType, occurredAt]
  uniquenessKey: [eventId]
  maxFreshnessLagMinutes: 5
  allowedLateArrivalMinutes: 10
consumers:
  - finance-reporting
  - customer-analytics
~~~

Đây là **hợp đồng minh họa**, không phải syntax bắt buộc của một nền tảng cụ thể.

Các yếu tố cần định nghĩa thêm:

- System of record và nguồn kiểm chứng khi sai lệch.
- Null, default, missing vs unknown.
- Timezone, precision, currency conversion.
- Dataset lineage và transformation version.
- Watermark, SLA cập nhật và reconciliation.
- Schema/semantic evolution.
- Handling deletes, GDPR/PII retention policy khi áp dụng.
- Business/data owner và người nhận data quality alerts.

Một nguồn dữ liệu không nên trở thành “sự thật” chỉ vì nó có timestamp mới nhất; ownership và semantics mới quyết định thẩm quyền.

## 33. Error contract, retries và idempotency liên quan chặt chẽ

Nếu Order gọi Payment và request timeout sau khi provider đã xử lý, **caller không biết outcome**. Một hợp đồng đúng cần:

- **Idempotency key** hoặc business operation ID có phạm vi và retention rõ.
- Cách tra trạng thái giao dịch bằng reference.
- Retryable errors vs terminal errors.
- Total deadline và bounded retry budget.
- Hành vi khi cùng key nhưng payload khác.
- Phân biệt authorization, capture, settlement, refund.
- Audit/correlation giúp đối soát.

Ví dụ:

~~~text
Order → Payment: Authorize 590000 VND, key=K1001
Payment provider processes operation
Network timeout before response
           |
           v
Outcome UNKNOWN
           |
           v
Lookup by idempotency/reference
           |
     +-----+-----------+
     |                 |
  Succeeded       Not found/failed
     |                 |
     v                 v
 Reconcile          Retry only
 without charging   if safe by policy
 twice
~~~

**Không chuẩn hóa “mọi POST timeout thì retry tối đa ba lần”**. Tính idempotent phải là một phần của contract và được test ở provider/consumer.

## 34. Phiên bản API và mô hình expand–migrate–contract

Một thay đổi từ **amount** sang **amountMinor** có thể đi qua nhiều release:

~~~text
Release 1:
  Provider trả amount (legacy)

Release 2 EXPAND:
  Provider trả amount và amountMinor
  Consumer cũ vẫn hiểu amount

Release 3 MIGRATE:
  Consumers chuyển sang amountMinor
  Đo usage của field legacy

Release 4 CONTRACT:
  Chỉ bỏ amount khi xác nhận compatibility horizon
  và deprecation policy cho phép
~~~

Không mặc định Release 2 cho phép **hai field mang cùng nghĩa** nếu units khác nhau; contract phải mô tả rõ và có conversion tests.

Với **database schema**, tương tự: thêm column mới, dual-write/backfill, đổi readers, rồi mới drop column cũ khi không còn version cần nó.

Với **events**, có thể phát event version mới song song theo kế hoạch migration, nhưng cần bảo đảm không tạo **hai side effects** nếu một consumer đọc cả hai streams.

**Versioning không thay thế kế hoạch chuyển đổi.** V1/V2 đẹp trên tài liệu nhưng không có consumer tracking vẫn có thể phá production.

## 35. Nhận diện và sở hữu dịch vụ bằng service catalog

Một service catalog hữu ích nên có các trường:

~~~yaml
service: order-api
domain: ordering
team: ordering-platform
environment: production
criticality: tier-1
identity:
  workloadPrincipal: order-api-service-identity
  tokenAudience: order-api
  ingressAuth: oauth2-access-token
observability:
  serviceName: order-api
  tracePropagation: w3c-trace-context
  logsFormat: structured-json
  sloRef: order-api-availability
contracts:
  openapiRef: order-api-public-v2
  emits: [OrderConfirmed.v2]
  consumes: [PaymentOutcome.v1]
operations:
  onCall: order-rotation
  runbook: order-api-runbook
  repository: example-repository
~~~

Đây là **cấu trúc minh họa**, không phải biểu mẫu bắt buộc của một sản phẩm service catalog cụ thể. Quan trọng là metadata có owner, được version/review và có thể dùng để:

- Tìm service và API owner.
- Định tuyến alerts/incidents.
- Xem dependency graph và contract blast radius.
- Kiểm tra chuẩn tối thiểu qua CI.
- Phân loại dữ liệu và quyền truy cập.
- Lập kế hoạch migration khi thay công cụ nền tảng.

**Service catalog không nên là bảng đăng ký thủ công lỗi thời.** Tự đồng bộ từ repo, deployment, identity provider và contract registry khi có thể, kèm cơ chế human review cho metadata nghiệp vụ.

## 36. Golden path: Làm cách đúng trở thành dễ nhất

Một developer tạo service mới có thể bắt đầu bằng starter project:

~~~text
new-service/
  src/
  tests/
    security/
    contracts/
    observability/
  api/
    openapi.yaml
  events/
    schemas/
  deployment/
    helm/
  .github/workflows/
    ci.yaml
  docs/
    service.yaml
    runbook.md
    adr/
~~~

Golden path nên tự cung cấp:

- HTTP server middleware xác thực và authorization hook.
- Mẫu cấu hình issuer/audience, không kèm secrets.
- HTTP/gRPC client instrumentation và trace propagation.
- JSON logging và redaction.
- RED metrics và health/readiness endpoints.
- OpenAPI/event schema template.
- Contract compatibility tests.
- Linter/SAST/SCA/IaC scans phù hợp.
- Helm/Kubernetes security and resource defaults.
- Dashboard/runbook/alert routing templates.

**Không ép mọi domain chạy qua một centralized helper có thể trở thành single point of failure** khi chỉ cần một schema, config hoặc SDK. Golden path là **paved road**, có đường nâng cấp và exception cho workload đặc thù.

## 37. SDK chung và rủi ro shared library

Một SDK platform giúp giảm lặp lại việc:

- Khởi tạo tracing, metrics, structured logging.
- Xác minh access token và xây principal context.
- Chuẩn hóa error responses.
- HTTP client deadlines/retry/propagation.
- Contract serialization và idempotency helper.
- Health/readiness common endpoints.

Nhưng một shared library quá lớn gây:

- Nhiều services phải deploy cùng lúc để nâng version.
- Domain logic bị đưa vào platform core.
- Phụ thuộc transitive tăng và gây security vulnerabilities.
- Một bug SDK ảnh hưởng đồng thời toàn hệ.
- Khó hỗ trợ dịch vụ polyglot.
- Tổ chức bị khóa vào framework/version cụ thể.

Nên tách:

1. **Protocol contracts** độc lập ngôn ngữ.
2. **Small language-specific adapters** với semantic versioning.
3. **Automated conformance tests** để dịch vụ dùng SDK khác vẫn đạt chuẩn.
4. **Deprecation policy** và hỗ trợ version window rõ.
5. **Ownership/security review** của thay đổi SDK có phạm vi rộng.

**Tiêu chuẩn là hành vi tại boundary, không phải bắt buộc import cùng một JAR.**

## 38. Policy-as-code: Kiểm chứng thay vì chỉ nhắc nhở

Những quy tắc có thể tự động hóa:

- Endpoint nội bộ quan trọng phải có authentication/authorization.
- Không cho workload privileged chạy nếu không có ngoại lệ.
- Container không dùng registry/image tag không được duyệt.
- Service được public qua Ingress phải có TLS và API contract.
- API breaking changes phải bị chặn hoặc có approval/migration plan.
- Event schema có owner/version/compatibility policy.
- Telemetry không dùng raw URL/user ID làm metric labels.
- Service có declared owner, SLO và runbook.
- Không có secret plaintext trong repo/CI logs.
- Service identity audience và issuer không bị cấu hình nhầm.
- Required CI jobs chạy trên commit thực sự được merge.

Chỉ mã hóa các rule có **điều kiện kiểm tra thực tế**. Những quyết định như “service này có nên tách bounded context không?” vẫn cần architecture review/ADR, không thể suy từ một linter đơn giản.

## 39. CI gates cho identity, observability và contracts

Một pipeline đề xuất:

~~~text
Pull request
    |
    +--> Compile, unit tests, static analysis
    |
    +--> Identity/security policy tests
    |      token issuer/audience/authorization negative cases
    |      secret scanning, dependency policy
    |
    +--> Observability conformance
    |      required service attributes, trace propagation
    |      logging schema, cardinality rules
    |
    +--> Contract validation
    |      OpenAPI syntax and breaking diff
    |      event schema compatibility
    |      provider/consumer verification
    |
    +--> Architecture checks
    |      ownership, boundaries, ADR triggers
    |
    v
Merge decision based on required checks
    |
    v
Build immutable artifact + SBOM/provenance
    |
    v
Staging integration tests / release gates
    |
    v
Progressive delivery + SLO monitoring
~~~

Một check phải có **owner**, tài liệu sửa lỗi, output hành động được và chính sách ngoại lệ. Khi scanner hoặc contract broker không hoạt động, trạng thái phải là **UNKNOWN/BLOCKED** theo policy, không báo PASS tự động.

**Không yêu cầu mỗi PR chạy full end-to-end test 60 phút** nếu những checks nhanh có thể phát hiện rủi ro sớm; chia gates theo mức rủi ro và có release/nightly tests sâu.

## 40. Ma trận tiêu chuẩn theo mức bắt buộc

| Tiêu chuẩn | Tier quan trọng | Tier phổ thông | Cách kiểm chứng |
|---|---|---|---|
| Valid token issuer/audience | Required | Required khi có auth | Negative integration tests |
| User/resource authorization | Required | Required theo data access | Ownership/tenant tests |
| Workload identity/least privilege | Required | Required theo trust model | Policy checks |
| Trace context propagation | Required | Recommended/required theo platform | Synthetic cross-service trace |
| Structured log + redaction | Required | Required | Log schema tests |
| RED metrics | Required | Required | Metrics smoke tests |
| SLO/alert/runbook ownership | Required | Theo criticality | Service catalog validation |
| API contract versioned | Required khi có API | Required khi có API | OpenAPI diff |
| Event schema compatibility | Required khi phát event | Required khi phát event | Registry/provider tests |
| Idempotency/retry contract | Required nếu có side effects | Theo operation | Fault-injection tests |
| SBOM/security scanning | Required theo policy | Required theo policy | Supply-chain CI |
| Multi-region DR contract | Theo RPO/RTO | Theo impact | Recovery exercise |

**Bảng minh họa**, không phải quy định phổ quát. Nên tránh cơ chế “tier thấp không cần security” nếu dữ liệu/threat model vẫn yêu cầu bảo vệ.

## 41. RACI và ownership trong quản trị nền tảng

Một mô hình tham khảo:

| Công việc | Platform | Domain team | Security | SRE/Operations | Architecture review |
|---|---|---|---|---|---|
| Identity provider/workload identity primitives | R | C | A/C | C | I |
| API authorization nghiệp vụ | C | A/R | C | I | C |
| Telemetry pipeline/collector | A/R | C | C | R/C | I |
| Instrumentation service + SLO | C | A/R | I | R/C | I |
| OpenAPI/event schema semantics | C | A/R | C khi nhạy cảm | I | C nếu cross-domain |
| Contract registry/CI framework | A/R | R cho contract riêng | C | I | C |
| Deprecation và migration của một domain API | C | A/R | C nếu policy tác động | C | C |
| Ngoại lệ bảo mật | C | R | A | I | C khi cần |
| On-call incident service | C | A/R | C nếu security incident | R | I |

**R = Responsible; A = Accountable; C = Consulted; I = Informed.** Với từng quyết định cụ thể nên có một đầu mối A rõ ràng, tùy cơ cấu tổ chức. Bảng chỉ là mô hình.

Platform không nên chịu trách nhiệm phê duyệt **semantics của payment refund** nếu quyền nghiệp vụ thuộc Payment/Finance domain. Ngược lại, domain team không nên tự đổi trust root hoặc mTLS policy làm ảnh hưởng toàn cluster mà bỏ qua Security/Platform.

## 42. Exception policy: Cho phép khác chuẩn nhưng không buông quản trị

Có những trường hợp hợp lý cần ngoại lệ:

- Legacy service không thể chuyển ngay sang OIDC.
- Một batch offline không dùng HTTP tracing theo cách thông thường.
- Public API phải hỗ trợ một phiên bản cũ hơn compatibility window.
- Đối tác yêu cầu schema khác chuẩn nội bộ.
- Dịch vụ có dữ liệu nhạy cảm không thể export mọi trace attributes.

Ngoại lệ nên gồm:

~~~text
Exception ID: EXAMPLE-PLATFORM-041
Standard: workload identity profile v2
Service: legacy-report-worker
Risk: static credential used temporarily
Reason: integration migration constraint
Mitigation: restricted network + short expiry + monitoring
Owner: reporting-platform
Approver: security-policy-owner
Expiry: 2027-01-31
Migration plan: service credential federation rollout
Review cadence: monthly
~~~

Đây là **mẫu minh họa**. Không biến ngoại lệ thành **disable scanner globally** hoặc “legacy được miễn vĩnh viễn”. Cần scope, owner, expiry, compensating controls, approval và tự động nhắc khi sắp hết hạn.

## 43. Governance lifecycle: Đề xuất, thử nghiệm, công bố, di trú

Một chuẩn mới không nên được áp toàn bộ production trong một ngày.

1. **Problem statement:** Rủi ro nào cần giảm? Có sự cố/chi phí cụ thể?
2. **Design RFC/ADR:** Xác định scope, phương án và trade-offs.
3. **Reference implementation:** Tạo một service mẫu, integration tests và examples.
4. **Pilot:** Thử với nhóm nhỏ các service khác nhau về ngôn ngữ/criticality.
5. **Documentation:** Chính sách required/recommended, how-to, troubleshooting và exception route.
6. **Versioned release:** Công bố profile v1 và compatibility horizon.
7. **CI enforcement:** Bắt đầu advisory nếu cần, rồi hard-gate phần chắc chắn theo lộ trình.
8. **Migration:** Starter/SDK upgrades, canary, dashboards và support.
9. **Measure:** Incident reduction, adoption, developer friction, scan false positives.
10. **Review/deprecate:** Dừng profiles cũ khi đã chứng minh consumers dùng được chuẩn mới.

**Tránh big-bang rollout** của authentication libraries, log schema hoặc event schemas: có thể làm hàng chục service đồng thời gặp lỗi.

## 44. Phiên bản của chính bộ tiêu chuẩn

Nên có một **platform standards profile** được version, ví dụ:

~~~text
platform-profile: 2026.2
  identity-profile: 2.1
  observability-profile: 1.4
  api-contract-profile: 2.0
  event-contract-profile: 1.3
  deployment-policy-profile: 3.0
~~~

Các version trong ví dụ là **giả định**, không phải một bộ tiêu chuẩn được công bố thật.

Một profile có thể quy định:

- Các field/headers bắt buộc.
- Các schema versions được hỗ trợ.
- Các lựa chọn compatible trong giai đoạn chuyển tiếp.
- Ngưỡng security/observability/contract checks.
- Consumer-facing behavior cần bảo đảm.
- Test suite tương ứng.
- Danh sách exceptions đang có hiệu lực.

Service catalog ghi **profile version adopted** để Platform biết tác động khi chuẩn thay đổi và không đòi nâng mọi service vào cùng ngày.

## 45. Bảo mật dữ liệu quan sát và dữ liệu hợp đồng

Telemetry và contract registries có thể vô tình chứa dữ liệu nhạy cảm:

- Request body có token/PII.
- Response samples có financial account IDs.
- Trace baggage có email, user ID hoặc session secrets.
- Labels/logs chứa tenant name không được công bố.
- OpenAPI examples chứa API key thật.
- Event fixtures lấy trực tiếp dữ liệu khách hàng production.

Chính sách:

1. **Data classification:** public/internal/confidential/restricted theo tổ chức.
2. **Redaction at source/collector:** Tránh xuất secrets; không chỉ dựa vào ẩn trên dashboard.
3. **RBAC:** Người xem business metrics khác người có quyền xem trace payload nhạy cảm.
4. **Retention:** Logs/traces/samples/contract fixtures theo nhu cầu và nghĩa vụ.
5. **Encryption:** In transit/at rest theo risk profile.
6. **Cross-region processing:** Tuân thủ giới hạn lưu trú dữ liệu nếu có.
7. **Incident access:** Audit các lượt xem và xuất dữ liệu nhạy cảm.
8. **Deletion handling:** Dữ liệu đã được xóa theo policy không bị tái sinh từ fixture/backup/trace.
9. **Test data:** Synthetic data hoặc masking phù hợp, không copy secrets thật.
10. **Supply chain:** Bảo vệ exporters, SDKs và contract tooling.

**Có trace đầy đủ không đáng giá nếu để lộ token hoặc dữ liệu thẻ.**

## 46. Platform conformance tests

Một bộ test có thể dùng cho mọi service mới:

### 46.1. Identity

~~~text
[ ] Valid token with correct issuer/audience/scope accepted
[ ] Invalid signature/expired/wrong audience rejected
[ ] Cross-tenant access rejected
[ ] Untrusted user header does not grant identity
[ ] Workload identity checked at service boundary
[ ] Sensitive operations audited without token leakage
~~~

### 46.2. Observability

~~~text
[ ] One synthetic request creates a cross-service trace
[ ] Logs include trace ID where applicable
[ ] Resource identity fields match service catalog
[ ] HTTP route metric uses template not raw order ID
[ ] Error code and deployment version searchable
[ ] Collector outage is observable and bounded
[ ] Telemetry samples contain no forbidden sensitive fields
~~~

### 46.3. API/event contracts

~~~text
[ ] OpenAPI syntax and examples validate
[ ] Breaking diff against published/deployed baselines passes
[ ] Consumer-provider interactions verified
[ ] Event schema version and compatibility tested
[ ] Semantic invariants (currency, timestamp, status) tested
[ ] Idempotency and duplicate event handling tested
[ ] Out-of-order and late events handled per contract
[ ] Deprecation/migration evidence attached when needed
~~~

Kết quả tests phải gắn với **commit/artifact version**, không phải chỉ một checkbox trong tài liệu. Các trường hợp cần kiểm tra quyền production nên được thực hiện trong môi trường phù hợp và được cấp phép.

## 47. Dashboard chung nhưng không phải một dashboard cho mọi service

Một dashboard template có thể có:

~~~text
Service Overview
  - Deployment version and region
  - Request rate/error/latency SLI
  - Active/available replicas and readiness
  - CPU/memory/GC and resource saturation
  - Downstream request latency/error/timeouts
  - Retry/circuit breaker/bulkhead metrics
  - Queue lag/DLQ (if event consumer)
  - Top errors with trace/log links
  - SLO burn rate and incident/runbook owner
~~~

Mỗi domain bổ sung business signals:

- Order: checkout success, failed order transitions, outbox lag.
- Payment: authorization outcomes, unknown-state count, reconciliation backlog.
- Inventory: reservation age, failed releases, negative stock invariants.
- Reporting: freshness lag, transform rejects, data quality issues.

Tiêu chuẩn nên đảm bảo **vị trí và ý nghĩa các tín hiệu lõi**, không cấm domain thêm metrics có giá trị.

## 48. Một incident minh họa: Checkout lỗi sau khi Payment triển khai

### Triệu chứng

Sau một release Payment, checkout 503 tăng. Order logs xuất hiện timeout nhưng Payment dashboards cho biết CPU vẫn bình thường.

### Điều tra theo chuẩn

1. Alert Order SLO kích hoạt đúng on-call owner.
2. Trace ID dẫn tới Order client span và Payment server span hoặc lỗi ở ingress boundary.
3. Service/version attributes cho biết Payment vừa thay image.
4. Metrics cho thấy Payment authorization endpoint có tỉ lệ 403 tăng, không phải CPU saturation.
5. Audit/security logs cho biết Order workload token không còn scope hoặc audience được chấp nhận do thay policy.
6. Contract/identity profile diff chỉ ra thay đổi tương thích đã bị bỏ qua.
7. Team quyết định rollback policy có kiểm soát hoặc triển khai delegation/token audience migration.
8. CI được bổ sung negative/positive tests cho workload token và contract của endpoint.
9. Dashboards, runbook và consumer compatibility records được cập nhật.

**Nhận xét:** Nếu chỉ có logs không liên kết trace, lỗi dễ bị quy thành “Payment chậm” và team có thể scale Payment vô ích. Chuẩn identity + observability + contracts giúp xác định đúng nguyên nhân và trách nhiệm.

## 49. Một incident khác: Event schema hợp lệ nhưng dashboard sai tiền

### Triệu chứng

Order confirmed events vẫn đến Reporting, schema registry báo compatible, nhưng doanh thu tăng 100 lần.

### Nguyên nhân minh họa

Producer chuyển **amount** từ VND nguyên sang minor units, giữ kiểu integer. Consumer chưa đổi transformation; schema vẫn hợp lệ.

### Bài học quản trị

- Contract phải ghi rõ **đơn vị, currency và version semantics**.
- Contract verification phải có **semantic examples** với expected output.
- Data quality rules phải phát hiện total amount outlier và lệch settlement ledger.
- Consumer có owner và nhận thông báo breaking behavior.
- Thay đổi nên dùng expand–migrate–contract, không đổi nghĩa field đang dùng.
- Backfill sửa reporting chỉ sau khi kiểm tra source of truth, scope và audit; không sửa ledger theo dashboard.

**Một schema registry không hiểu business semantics; chỉ có technical compatibility là chưa đủ.**

## 50. Trách nhiệm khi một chuẩn chung thất bại

Khi xảy ra lỗi, không nên phản xạ “Platform team chịu hết” hoặc “Domain team tự lo hết”.

Ví dụ:

| Vấn đề | Owner khắc phục chính thường là |
|---|---|
| Platform identity trust root bị cấu hình sai | Platform/Security |
| Order bỏ authorization object ownership | Order domain |
| Collector drop traces vì pipeline overload | Observability platform với domain phối hợp |
| Service log JWT nguyên văn | Service owner; Security phối hợp incident |
| OpenAPI contract breaking đổi field | Provider/domain owner |
| Consumer không nâng sau deprecation đúng thông báo | Consumer owner, provider hỗ trợ |
| Registry/CI gate không hoạt động | Platform tooling owner |
| Payment amount semantics sai | Payment domain + consumers liên quan |
| Không có dashboard/alert chủ sở hữu | Service owner + SRE governance |
| Chính sách quá cứng tạo bypass hàng loạt | Platform/Architecture governance |

Với sự cố xuyên domain, incident commander phối hợp, nhưng mỗi hệ thống phải có **technical owner, data/business owner và policy owner** được tìm thấy nhanh qua catalog.

## 51. Adoption metrics: Chuẩn có thực sự giúp ích?

Không nên chỉ đo “90% service cài SDK” mà không biết nó có tác dụng.

Các chỉ số hữu ích:

- % services có issuer/audience validation được kiểm chứng.
- % critical APIs có object-level authorization tests.
- % request journeys có traces liên kết xuyên dependency.
- % logs đạt schema/redaction policy.
- % services có RED metrics, SLO và runbook owner.
- % APIs/events có contract versions và compatibility gate.
- % breaking changes được phát hiện trước merge/deploy.
- Mean time to detect/resolve incidents qua signals đúng.
- Số policy exceptions quá hạn và độ tuổi remediation.
- Cardinality/ingestion cost per service tier.
- Thời gian từ tạo service đến first safe deployment.
- Developer feedback về độ khó sử dụng golden path.

Nếu CI checks tạo nhiều false positives và mọi người bắt đầu tìm đường tắt, đó là dấu hiệu cần cải thiện **chất lượng tiêu chuẩn/công cụ**, không phải siết quyền không có giải thích.

## 52. Lộ trình áp dụng theo giai đoạn

### Giai đoạn 1 — Baseline tối thiểu

- Service catalog có owner, repo, SLO/runbook.
- API dùng issuer/audience validation và authorization tests.
- JSON logs chuẩn, trace context, RED metrics.
- OpenAPI/event schemas được version control.
- Secret scanning và basic CI checks.

### Giai đoạn 2 — Chuẩn hóa ranh giới

- Workload identity và least-privilege policies.
- Contract compatibility với published consumer baselines.
- Event schema registry hoặc kiểm tra tương đương.
- End-to-end trace propagation qua HTTP/messaging.
- Metric label/cardinality budget và telemetry redaction.
- Data contract cho nguồn dữ liệu quan trọng.

### Giai đoạn 3 — Enforce và governance

- Required CI gates; service catalog integration.
- Platform starter/SDK adapters và conformance suite.
- SLO/error budget, alert ownership, incident runbooks.
- Exceptions có expiry, approved compensating controls.
- Deprecation tracking, impact graph và migration status.

### Giai đoạn 4 — Liên tục tối ưu

- Đánh giá impacts khi thay trust policy/schema conventions.
- Tự động liên kết contracts với deployed versions.
- Observability cost and sampling optimization.
- Security threat modeling và game days.
- Theo dõi incident reduction, developer experience và drift.
- Di trú profiles cũ theo lộ trình tránh breaking changes.

**Đừng áp đồng loạt tất cả tiêu chuẩn trong một lần release.** Tổ chức nên ưu tiên theo risk, maturity và khả năng hỗ trợ team.

## 53. Checklist cho một microservice mới

1. **Service name/domain/owner** đã đăng ký trong catalog?
2. API dùng **trusted issuer** và **audience** đúng resource chưa?
3. Scopes/permissions có phân biệt read/write/admin/refund?
4. Object-level và tenant-level authorization có tests âm tính?
5. Workload identity đã được cấp đúng scope, short-lived credentials khi phù hợp?
6. Không tin header danh tính tự khai từ client?
7. Secrets không nằm trong source, logs, traces, CI artifacts?
8. Service.name/version/environment được set nhất quán?
9. Trace context truyền qua HTTP/messaging và không dùng trace ID để auth?
10. Structured logs có error code, trace_id và redaction?
11. Metrics có RED/USE hoặc tương đương theo loại workload?
12. Metric labels có bounded cardinality, dùng route templates?
13. SLO/alert/runbook và on-call owner rõ?
14. OpenAPI có security, errors, pagination, timeout và semantic fields?
15. Event schemas có version, event IDs, delivery/idempotency semantics?
16. Data contracts có source of truth, quality/freshness SLO nếu cần?
17. Compatibility checks so với **consumers đang deploy**, không chỉ main?
18. Breaking changes có plan expand–migrate–contract và deprecation?
19. Contract tests có verify provider và consumer assumptions?
20. CI required checks có được enforce theo commit cuối?
21. Runtime policies và identity/tracing exporters đã chạy thử ở staging?
22. Platform profile version nào được adopted và exceptions nào đang có hiệu lực?
23. Có cách quan sát errors/unknown outcomes mà không lộ dữ liệu?
24. Có owner giải quyết ranh giới giữa các service khi incident?
25. Có hướng nâng cấp SDK/standard version mà không bắt deploy đồng thời?

## 54. Checklist cho Platform team

- Bộ standard profile có version và changelog.
- Có service catalog và cơ chế cập nhật ownership tự động khi khả thi.
- Identity issuer/trust roots và signing key rotation đã được diễn tập.
- Workload identity có failure policy, audit và least privilege.
- Golden paths có sample apps thật, security tests và tracing end-to-end.
- Observability collector/backend có SLO, capacity, cardinality limits và telemetry loss alerts.
- Logging fields có schema và data classification policy.
- Contract registry/CI có available baselines cho versions đang deploy.
- Event schema compatibility policy theo từng loại event.
- Exceptions có owner, expiry, reviewer và remediation plan.
- Các quy tắc bắt buộc có cách tái hiện lỗi và tài liệu khắc phục.
- Starter/SDK có semantic versioning, security patch policy và migration plan.
- SLO/incident runbooks có thể truy từ alert đến đúng domain owner.
- Kiểm chứng rằng các rules không chỉ xuất hiện trên giấy mà được enforce thật.
- Theo dõi developer experience, false positive rate, CI duration và adoption.
- Có chu kỳ review standards theo thay đổi threat model/technology/architecture.

## 55. Những anti-pattern cần tránh

**1. Dùng cùng một API key tĩnh cho mọi service.** Không có danh tính riêng/rotation/audit đúng nghĩa.

**2. Tin X-User-Id từ Internet.** Tạo lỗ hổng impersonation nếu header không được xác minh ở trust boundary.

**3. Chỉ verify JWT signature, bỏ issuer/audience.** Có thể chấp nhận token cấp cho API khác.

**4. Dùng ID token để gọi resource API.** Nhầm authentication của client với access authorization.

**5. Chỉ xác thực service, bỏ object-level authorization.** Workload hợp lệ vẫn có thể đọc dữ liệu sai tenant/user.

**6. Biến traceparent thành bằng chứng user đã xác thực.** Trace context không phải identity assertion.

**7. Log nguyên bearer token hoặc request payload nhạy cảm.** Observability trở thành kênh rò rỉ.

**8. Mỗi service tự đặt tên metrics/attributes.** Dashboards, alerts và cross-service queries không tái sử dụng được.

**9. Dùng raw path hoặc orderId làm metric label.** Cardinality explosion làm backend telemetry chậm/tốn kém.

**10. Chỉ có metrics CPU, không có request SLO.** Không nhìn thấy user-facing errors.

**11. Tail-sample lỗi rồi lấy tỷ lệ trong traces làm error rate toàn hệ.** Mẫu bị thiên lệch.

**12. Đổi nghĩa field mà giữ schema/type.** Consumer hỏng dù schema registry PASS.

**13. Chỉ so contract với branch main.** Bỏ qua mobile/client phiên bản cũ đang chạy.

**14. Chỉ dùng consumer mocks, không provider verify.** Stub vẫn xanh khi provider đã đổi.

**15. Dùng shared SDK chứa logic domain của mọi service.** Tạo coupling và release bottleneck.

**16. Bắt mọi team chờ một nhóm duyệt thay đổi nhỏ.** Standardization biến thành centralization không cần thiết.

**17. Tắt scanners toàn cục để né false positives.** Cần suppression scoped, owner và expiry.

**18. Không biết team nào nhận sự cố.** Thiếu service catalog, alert ownership và runbook.

**19. Một policy áp mọi tier mà không nhìn threat model.** Hoặc quá lỏng cho dữ liệu nhạy cảm, hoặc quá cứng gây bypass.

**20. Báo PASS khi check/tool không chạy.** Thiếu bằng chứng phải là UNKNOWN/BLOCKED theo policy.

## 56. Kết luận

**Một nền tảng microservices trưởng thành không phải nơi mọi team dùng chung mọi công nghệ, mà là nơi các ranh giới quan trọng có thể tin cậy, quan sát và kiểm chứng được.**

- **Danh tính:** User và workload đều có nguồn xác thực, audience, quyền truy cập và trust boundary rõ. Authentication không thay authorization.
- **Quan sát:** Logs, metrics và traces dùng ngữ cảnh chung, có SLO, owner, bảo vệ dữ liệu nhạy cảm và chi phí được kiểm soát.
- **Hợp đồng:** API, events và datasets có schema lẫn semantics, version, rules tương thích, consumer verification và migration policy.
- **Quản trị:** Golden paths, conformance tests, CI gates, catalog, RACI và exceptions có thời hạn giúp tiêu chuẩn hoạt động trong thực tế mà không bóp nghẹt sự độc lập của domain teams.

**Câu hỏi tự kiểm tra:** *Nếu Order gọi Payment sau một đợt triển khai, liệu Payment có chứng minh được ai/công việc nào có quyền thực hiện giao dịch, đội vận hành có theo được request xuyên cả hai services, và CI có phát hiện trước những thay đổi contract hoặc policy làm hỏng consumer đang chạy không?*

Một tổ chức trả lời được bằng **token/policy verification, trace evidence, contract reports, service ownership và runbooks có thể thực thi** đã biến tiêu chuẩn chung thành năng lực vận hành thật sự, không còn là tài liệu quy định đơn thuần.
