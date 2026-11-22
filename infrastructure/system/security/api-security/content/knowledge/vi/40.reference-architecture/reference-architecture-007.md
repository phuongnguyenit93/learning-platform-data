# Versioning, inventory và incident response

API security không dừng ở việc xác thực request hay bật HTTPS. Một hệ thống có nhiều endpoint, nhiều phiên bản contract, nhiều consumer và nhiều dependency cần biết chính xác API nào đang tồn tại, ai sở hữu, dữ liệu nào được xử lý, policy nào áp dụng và cách ứng cứu khi một endpoint hoặc credential bị khai thác. Nếu inventory không đầy đủ, đội vận hành có thể bỏ sót API cũ, route shadow hoặc consumer chưa được nâng cấp. Nếu versioning không gắn với security policy, một phiên bản mới có thể vô tình mở rộng quyền hoặc làm mất validation. Nếu incident response không có bản đồ endpoint và dependency, việc khoanh vùng có thể chậm và bỏ sót dữ liệu đã bị truy cập.

Kiến trúc tham chiếu nên nối ba năng lực thành một vòng đời:

- **Inventory:** ghi nhận API, endpoint, owner, consumer, dữ liệu, quyền, dependency và trạng thái vòng đời.
- **Versioning:** quản lý phiên bản contract, schema, security policy, implementation và dependency; kiểm soát tương thích, deprecation và migration.
- **Incident response:** dùng inventory và version history để phát hiện, khoanh vùng, bảo toàn evidence, containment, khôi phục và xác minh sau sự cố.

Thiết kế bảo mật phải đi theo từng endpoint, object và business flow. Một API version mới không được xem là an toàn chỉ vì route đã đổi từ /v1 sang /v2; cần kiểm tra authentication, function/object authorization, tenant isolation, validation, rate limit, dữ liệu trả về và side effect của từng operation.

## 1. Mô hình kiến trúc tham chiếu

Một API platform nên có data plane xử lý request và control plane quản lý catalog, policy, version, rollout và incident metadata. Hai phần cần liên kết bằng identifier và version rõ ràng.

~~~mermaid
flowchart TB
    subgraph CP[Control plane]
        CAT[API catalog and inventory]
        VER[Contract and policy versions]
        OWN[Owners and consumers]
        IR[Incident runbooks]
        CAT <--> VER
        CAT <--> OWN
        CAT <--> IR
    end
    subgraph DP[Data plane]
        C[Clients and partners] --> E[CDN / WAF / Edge]
        E --> G[API Gateway]
        G --> AU[Authentication]
        AU --> AZ[Function and object authorization]
        AZ --> V[Validation and abuse controls]
        V --> S[API services]
        S --> D[(Database)]
        S --> Q[Queue / Event bus]
        S --> U[Upstream providers]
    end
    CAT -. route and owner metadata .-> G
    VER -. contract and policy version .-> G
    VER -. schema and release version .-> S
    DP --> OBS[Logs / traces / audit / metrics]
    OBS --> IR
    IR --> OWN
~~~

Control plane không cần nằm trong cùng một sản phẩm. API catalog có thể là service catalog, developer portal hoặc CMDB được mở rộng; contract có thể lưu trong repository; policy có thể quản lý bằng code; incident runbook có thể nằm trong hệ thống vận hành. Điều quan trọng là chúng liên kết được với nhau và có owner rõ ràng.

### 1.1. Nguyên tắc thiết kế

1. Mỗi API và endpoint có owner chịu trách nhiệm.
2. Mỗi endpoint có contract và security requirements có thể kiểm tra.
3. Mỗi version đang phục vụ có consumer, dữ liệu và dependency được nhận diện.
4. Security policy được version hóa và có thể xác định theo thời điểm request.
5. API cũ, shadow API và route không còn owner phải được phát hiện.
6. Incident runbook dùng cùng identifier với inventory và telemetry.
7. Thay đổi contract/security có review, test và audit.
8. Deprecation có thông báo, thời hạn, migration path và bằng chứng consumer đã chuyển.

## 2. Inventory API là gì?

API inventory là danh mục có cấu trúc về các API đang được phát triển, triển khai, công bố hoặc vẫn có thể truy cập. Nó không chỉ là danh sách URL. Một inventory hữu ích cần mô tả ai dùng API, dữ liệu nào đi qua, endpoint nào thay đổi trạng thái, cơ chế xác thực và phân quyền nào áp dụng, cùng dependency nào có thể bị ảnh hưởng.

### 2.1. Phân biệt API, service, endpoint và operation

| Đối tượng | Ý nghĩa | Ví dụ |
|---|---|---|
| Product/API | Nhóm contract phục vụ một năng lực | Billing API |
| Service | Thành phần triển khai xử lý logic | billing-service |
| API version | Phiên bản contract công bố | v1, v2 |
| Endpoint | Route và HTTP method cụ thể | GET /invoices/{id} |
| Operation | Hành động nghiệp vụ được thực hiện | Read invoice, issue refund |
| Consumer | Client hoặc service gọi API | Web app, mobile app, partner |
| Dependency | Thành phần API phụ thuộc | Database, payment provider, queue |

Không gộp tất cả thành một bản ghi “Billing API”. Một API có thể có nhiều endpoint với rủi ro và quyền khác nhau. Ví dụ GET /invoices/{id} có thể chỉ đọc dữ liệu; POST /invoices/{id}/refund có thể tạo side effect tài chính và cần permission, idempotency, approval và audit riêng.

### 2.2. Trường thông tin tối thiểu

Một API catalog nên có ít nhất:

| Nhóm | Trường |
|---|---|
| Identity | API ID, tên, domain, service, environment |
| Ownership | Business owner, technical owner, security contact, support channel |
| Contract | OpenAPI/AsyncAPI reference, schema version, API version |
| Exposure | Public, partner, internal, private; hostname/gateway |
| Lifecycle | Draft, active, deprecated, sunset, retired |
| Consumer | Client ID, partner, calling service, contact và version đang dùng |
| Endpoint | Method, route template, operation ID, sensitivity |
| Data | Classification, PII/financial/secrets, read/write/export behavior |
| Authentication | Scheme, issuer, audience, client/workload identity |
| Authorization | Function permission, scope, object policy, tenant boundary |
| Abuse controls | Rate limit, quota, payload size, concurrency, idempotency |
| Dependencies | Database, queue, provider, identity, secret manager |
| Operations | SLO, dashboards, logs, traces, alerts, runbook |
| Version history | Contract/policy/release versions, change ID, effective time |
| Incident | Incident contact, evidence source, containment action, recovery dependency |

Không phải mọi trường đều cần hiển thị công khai trong developer portal. Catalog có thể có metadata public và metadata nội bộ; access control cần theo độ nhạy cảm của thông tin.

## 3. Inventory theo endpoint, object và business flow

Inventory ở cấp API tổng thể chưa đủ để kiểm soát BOLA, function authorization hoặc lạm dụng nghiệp vụ. Với mỗi endpoint, ghi rõ operation, resource và security boundary.

### 3.1. Endpoint inventory

Ví dụ một phần inventory:

| Method/route | Operation | Data access | Permission | Rủi ro cần kiểm soát |
|---|---|---|---|---|
| GET /v1/invoices | List invoices | Read theo tenant | invoice:read | Pagination, filter abuse, tenant scope |
| GET /v1/invoices/{id} | Read invoice | Read object | invoice:read + object policy | BOLA/IDOR, data minimization |
| POST /v1/invoices | Create invoice | Write | invoice:create | Validation, quota, idempotency |
| POST /v1/invoices/{id}/refund | Refund invoice | Financial side effect | invoice:refund + workflow approval | Replay, fraud, state transition, audit |
| GET /v1/reports/export | Export report | Bulk read | report:export | Data exfiltration, async job, quota |

Đây là ví dụ minh họa. Permission name và concealment policy phải được định nghĩa trong hệ thống thực tế. Không dùng inventory như bằng chứng duy nhất rằng code đã enforce permission; cần test và telemetry xác minh.

### 3.2. Object inventory và tenant boundary

Với resource có dữ liệu nhạy cảm, cần xác định:

- Object ID và nơi sinh ID.
- Owner/tenant relationship.
- Các role có thể đọc, sửa, xóa, export hoặc chuyển quyền sở hữu.
- Quan hệ parent-child và object lồng nhau.
- Field-level visibility và mass assignment restrictions.
- Soft delete, archive và retention behavior.
- Các endpoint khác có thể truy cập cùng object.

Một invoice có thể được đọc qua endpoint detail, list, export, search, webhook status hoặc admin endpoint. Inventory phải liên kết các đường truy cập này để kiểm tra nhất quán object authorization và data exposure.

### 3.3. Business flow inventory

Một workflow có thể đi qua nhiều endpoint và service. Ví dụ tạo payment:

1. Client tạo payment intent.
2. API xác thực principal và kiểm tra tenant.
3. Service validate amount, currency và merchant configuration.
4. Payment service gọi provider.
5. Provider gửi webhook.
6. Webhook verification xác minh signature và event.
7. Queue/worker xử lý event theo idempotency.
8. Payment state chuyển sang succeeded hoặc failed.
9. API trả trạng thái cho client.

Inventory cần ghi operation ID, state machine, endpoint liên quan, provider account, webhook endpoint, queue/topic, permission và evidence source. Khi xảy ra sự cố, đội ứng cứu có thể xác định toàn bộ flow bị ảnh hưởng thay vì chỉ nhìn endpoint đầu tiên.

## 4. Phát hiện API và duy trì inventory chính xác

Catalog do con người nhập thủ công dễ lỗi thời. Nên kết hợp metadata từ source repository, OpenAPI, gateway, service mesh, cloud discovery, DNS, deployment platform và telemetry.

### 4.1. Nguồn discovery

- OpenAPI/AsyncAPI trong repository.
- Gateway route/config và deployed API products.
- Service registry, Kubernetes ingress/service và service mesh.
- DNS record, load balancer và public certificate inventory.
- Cloud API gateway, function, load balancer và serverless endpoint.
- Runtime access log và distributed trace.
- CI/CD release/deployment metadata.
- Identity provider client registration và OAuth audience/scope.
- Partner integration records và contract owner.

Mỗi nguồn có thể thiếu thông tin. OpenAPI cho biết contract dự định; gateway cho biết route đã publish; telemetry cho biết route thực sự được gọi. So sánh các nguồn để phát hiện drift.

### 4.2. Shadow, zombie và undocumented API

- **Shadow API:** endpoint đang chạy nhưng không có trong catalog hoặc chưa qua quy trình review.
- **Zombie API:** endpoint cũ vẫn truy cập được dù đã tuyên bố retired hoặc không còn owner.
- **Undocumented API:** endpoint có người dùng nhưng contract/owner/security requirement không rõ.
- **Orphan consumer:** client hoặc partner vẫn gọi API nhưng không còn contact/owner hợp lệ.

Không tự động xóa route chỉ vì catalog không có bản ghi; có thể đó là endpoint cần điều tra. Đưa vào quarantine/review, xác định owner và consumer, đánh giá dữ liệu/traffic rồi mới decommission theo change process.

### 4.3. Phát hiện drift

Định kỳ so sánh:

- Contract trong repository với contract được deploy.
- API catalog với gateway route.
- Gateway route với endpoint runtime.
- Permission catalog với policy thực tế.
- Consumer inventory với access telemetry.
- Dependency catalog với outbound network/trace.
- Lifecycle status với traffic thực tế.

Drift cần tạo finding có owner, mức rủi ro và deadline. Ví dụ endpoint mới xuất hiện nhưng không có authentication requirement là finding ưu tiên cao.

## 5. Versioning: không chỉ là đổi URL

Versioning có thể áp dụng cho nhiều lớp khác nhau. Cần ghi rõ loại version đang nói đến.

| Loại version | Ví dụ | Ý nghĩa |
|---|---|---|
| API contract | /v1, /v2 hoặc media type version | Cấu trúc request/response và semantics công bố |
| Schema/event | invoice.created.v2 | Cấu trúc message/event |
| Security policy | authz-policy-42 | Quy tắc authentication/authorization |
| Implementation | service release 2026.11.18.3 | Code đang chạy |
| Dependency | payment-provider API v3 | Contract của upstream |
| Key/certificate | signing-key-2026-04 | Key version được dùng để ký/xác minh |
| Configuration | gateway-config-128 | Route, WAF, rate limit và TLS config |

Không giả định API contract v2 đồng nghĩa security policy v2 hoặc implementation version v2. Một route /v1 có thể chạy implementation mới; một security policy có thể được cập nhật độc lập. Incident response cần truy ra đúng tổ hợp version đã có hiệu lực tại thời điểm request.

### 5.1. Các chiến lược API versioning

| Chiến lược | Ví dụ | Ưu điểm | Lưu ý bảo mật |
|---|---|---|---|
| URI path | /api/v2/invoices | Dễ quan sát và routing | Tránh để v1 cũ thiếu patch vẫn public |
| Header | API-Version: 2 | URL ổn định | Gateway/log/cache phải giữ và phân loại header |
| Media type | Accept: application/vnd.example.v2+json | Version gắn representation | Content negotiation cần test rõ |
| Query parameter | ?version=2 | Dễ thử nghiệm | Dễ bị bỏ qua ở cache/proxy và thường khó quản trị hơn |

Chọn một chiến lược nhất quán cho product. Không để version có thể được chọn đồng thời từ nhiều vị trí với precedence không rõ. Nếu client gửi path v1 nhưng header v2, server phải có quy tắc rõ ràng hoặc từ chối request mơ hồ.

### 5.2. Quy tắc tương thích

Thay đổi thường được xem là tương thích khi consumer cũ vẫn hoạt động theo contract đã công bố. Ví dụ:

- Thêm field response optional mà client cũ bỏ qua được.
- Thêm endpoint mới không làm thay đổi behavior endpoint cũ.
- Mở rộng enum có thể không tương thích với client dùng exhaustive switch.
- Thay đổi default value có thể làm thay đổi behavior dù schema không đổi.
- Siết validation có thể từ chối request trước đây được chấp nhận.
- Thay permission hoặc scope có thể làm client mất quyền.

Không chỉ dùng schema diff để kết luận compatibility. Cần đánh giá semantics, authorization, data visibility, error status, rate limit và side effect.

### 5.3. Breaking change và security change

Một thay đổi có thể cần major version hoặc migration riêng nếu:

- Xóa/đổi field hoặc endpoint.
- Đổi kiểu dữ liệu hoặc meaning của field.
- Đổi authentication scheme hoặc issuer/audience.
- Siết scope/permission hoặc object policy.
- Thay đổi tenant resolution.
- Đổi error semantics mà SDK dựa vào.
- Thay đổi idempotency hoặc retry behavior.
- Thay đổi validation khiến request hợp lệ trước đây bị từ chối.
- Thu hẹp data exposure hoặc xóa field nhạy cảm.

Security fix có thể cần triển khai khẩn cấp ngay cả khi gây breaking behavior. Không trì hoãn việc chặn BOLA hoặc credential compromise chỉ để giữ backward compatibility. Cần đánh giá consumer, truyền thông và migration path, nhưng security invariant được ưu tiên.

## 6. Version contract và OpenAPI

OpenAPI là một phần quan trọng của inventory vì mô tả path, method, schema, security scheme, response và operation ID. Contract nên được review như code.

### 6.1. Ví dụ contract có security requirement

~~~yaml
openapi: 3.1.0
info:
  title: Invoice API
  version: 2.1.0
servers:
  - url: https://api.example.test
paths:
  /v2/invoices/{invoiceId}:
    get:
      operationId: getInvoice
      security:
        - bearerAuth: []
      parameters:
        - name: invoiceId
          in: path
          required: true
          schema:
            type: string
      responses:
        "200":
          description: Invoice returned
        "401":
          description: Authentication required
        "403":
          description: Action not permitted
        "404":
          description: Invoice not found or concealed
components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
~~~

Đây là ví dụ contract rút gọn. OpenAPI security requirement mô tả authentication scheme, không thể thay thế kiểm tra object-level authorization trong code. Cần bổ sung mô tả scope, data classification, rate limit, idempotency và policy reference bằng convention/extension được tổ chức quản lý nếu cần.

### 6.2. Contract test và security test

CI có thể kiểm tra:

- OpenAPI parse và schema validation.
- Operation ID duy nhất.
- Endpoint mới có security requirement hoặc lý do public được phê duyệt.
- Request/response schema không vô tình lộ field nhạy cảm.
- Error response theo contract.
- Breaking change được phát hiện và có approval.
- Security policy reference có version.
- Deprecated endpoint có sunset metadata.
- Consumer contract test với các client quan trọng.

Contract test chứng minh request/response phù hợp schema; nó không chứng minh caller không thể truy cập object của tenant khác. Cần test authorization riêng.

## 7. Version hóa security policy

Authentication và authorization policy cần có version hoặc hash để xác định quyết định tại thời điểm request. Nếu policy thay đổi nhưng log chỉ lưu endpoint version, điều tra sẽ không biết rule nào đã cho phép request.

Một policy record có thể bao gồm:

- Policy ID và version.
- API/operation ID áp dụng.
- Authentication scheme và issuer/audience.
- Required scope/function permission.
- Object/tenant authorization rule reference.
- Field-level data visibility.
- Rate limit/quota profile.
- Validation profile.
- Effective-from/effective-to.
- Owner, reviewer và change ticket.

### 7.1. Policy rollout

Triển khai policy theo giai đoạn:

1. Review thay đổi và threat model.
2. Chạy unit/integration/security tests.
3. Kiểm tra consumer impact và exception được phê duyệt.
4. Deploy canary hoặc một nhóm instance.
5. Theo dõi deny rate, error rate và business outcome.
6. Mở rộng rollout.
7. Ghi policy version và effective time vào audit.
8. Có rollback plan nếu policy gây lỗi vận hành.

Rollback không được khôi phục một lỗ hổng đã biết. Nếu policy mới là security fix, phương án rollback phải giữ security invariant bằng một biện pháp khác.

### 7.2. Policy drift và emergency change

Emergency policy có thể cần áp dụng nhanh để chặn abuse hoặc lộ dữ liệu. Vẫn phải ghi actor, incident ID, reason, scope, effective time, expiry/review time và version. Sau incident, chuyển thay đổi khẩn cấp thành cấu hình được quản lý và review lại.

## 8. Deprecation, sunset và migration

Một API version cũ không nên tồn tại vô thời hạn. Mỗi version cần lifecycle state và ngày đánh giá/deprecation/sunset.

Lifecycle tham khảo:

~~~mermaid
stateDiagram-v2
    [*] --> Draft
    Draft --> Active: Approved and released
    Active --> Deprecated: Replacement available
    Deprecated --> Sunset: Migration window ends
    Sunset --> Retired: Traffic disabled
    Active --> Suspended: Security incident
    Deprecated --> Suspended: Security incident
    Suspended --> Active: Remediated and approved
    Suspended --> Retired: Decommission
    Retired --> [*]
~~~

### 8.1. Deprecation plan

Kế hoạch deprecation cần nêu:

- Version/endpoint bị deprecate.
- Replacement version và migration guide.
- Consumer/partner bị ảnh hưởng.
- Ngày bắt đầu deprecation và sunset.
- Hỗ trợ song song trong bao lâu.
- Cách đo traffic còn lại.
- Owner chịu trách nhiệm liên hệ consumer.
- Quy trình exception và ngày hết hạn.
- Security fix hoặc compatibility issue có thể rút ngắn thời hạn.

### 8.2. HTTP deprecation metadata

Có thể dùng header Deprecation và Sunset theo quy ước phù hợp, cùng link tới migration documentation. Header chỉ là thông báo; catalog và consumer communication vẫn cần cập nhật. Gateway có thể thêm warning nhưng không nên làm sai response contract.

Ví dụ:

~~~http
HTTP/1.1 200 OK
Deprecation: @1785542400
Sunset: Thu, 31 Dec 2026 00:00:00 GMT
Link: <https://developer.example.test/migrations/invoices-v2>; rel="deprecation"
~~~

Giá trị ngày trong ví dụ chỉ minh họa format; production phải dùng ngày thực tế và kiểm tra cú pháp theo chuẩn đang áp dụng.

### 8.3. Quyết định tắt version cũ

Trước khi tắt:

1. Xác định consumer còn traffic.
2. Phân biệt health check, scanner và request nghiệp vụ.
3. Liên hệ owner/partner.
4. Xác nhận consumer đã chuyển hoặc có exception.
5. Kiểm tra data migration và workflow đang chạy.
6. Thông báo sunset và hỗ trợ.
7. Tắt canary trước, theo dõi lỗi.
8. Thu hồi credential/route/certificate không còn cần.
9. Xóa DNS, gateway route và backend khi đã xác minh không còn dependency.
10. Cập nhật catalog thành retired và giữ version history.

Nếu version cũ có lỗ hổng nghiêm trọng, có thể phải suspend ngay. Ghi nhận tác động và cung cấp workaround/migration khẩn cấp.

## 9. Liên kết inventory với consumer và dependency

Biết endpoint tồn tại chưa đủ; cần biết ai đang gọi và endpoint phụ thuộc vào gì. Consumer inventory giúp xác định blast radius khi thay đổi hoặc incident.

### 9.1. Consumer registry

Mỗi consumer nên có:

- Client/service ID và owner.
- Loại consumer: browser, mobile app, backend, partner, batch job.
- API version và operation được sử dụng.
- Environment và region.
- Authentication method, issuer và credential reference.
- Contact và support escalation.
- Last seen và traffic baseline.
- Data classification được phép nhận.
- Migration status và exception expiry.

Không lưu secret value trong consumer registry. Chỉ lưu secret reference/version hoặc credential identifier có thể truy vết.

### 9.2. Dependency map

Ghi quan hệ giữa endpoint và:

- Database/table/domain service.
- Queue/topic/event schema.
- Payment, identity, email hoặc storage provider.
- DNS hostname, egress route và TLS trust.
- Secret path/key version reference.
- JWKS/issuer/introspection endpoint.
- KMS/HSM operation.

Dependency map giúp trả lời: nếu payment provider bị lỗi hoặc secret version bị lộ, endpoint nào và tenant nào bị ảnh hưởng?

### 9.3. Blast radius

Đánh giá blast radius theo:

- Số API/endpoint dùng chung credential.
- Số consumer và tenant.
- Loại dữ liệu được đọc hoặc ghi.
- Mức quyền của workload.
- Số region/cluster có cùng policy hoặc key.
- Side effect tài chính hoặc workflow.
- Khả năng truy cập lateral sang service khác.

Dùng credential dùng chung cho nhiều API làm blast radius lớn và khó quy trách nhiệm. Tách workload identity, secret và permission theo service giúp containment có mục tiêu hơn.

## 10. Incident response gắn với API inventory

Incident response là quy trình có thể kích hoạt khi phát hiện dấu hiệu compromise, abuse, data exposure, authentication failure bất thường hoặc dependency bị xâm nhập.

Catalog giúp nhóm ứng cứu biết:

- Endpoint nào đang public hoặc partner-facing.
- Owner và người có quyền thay đổi route/policy.
- Consumer và tenant bị ảnh hưởng.
- Dữ liệu được xử lý và retention.
- Authentication/key version nào có hiệu lực.
- Dependency nào cần kiểm tra hoặc liên hệ.
- Dashboard, log, audit và runbook ở đâu.

### 10.1. Phân loại incident API

| Loại sự cố | Ví dụ | Ưu tiên ứng cứu |
|---|---|---|
| Authentication compromise | JWT signing key hoặc API key bị lộ | Revoke/rotate, xác minh token/traffic |
| Authorization failure | BOLA, tenant isolation bypass | Chặn endpoint/action, xác định dữ liệu bị truy cập |
| Data exposure | Response trả thừa PII hoặc export trái phép | Giới hạn truy cập, bảo toàn request/response evidence |
| API abuse | Credential stuffing, scraping, resource exhaustion | Rate limit, challenge, quota và bảo vệ dependency |
| SSRF/outbound abuse | API gọi URL nội bộ hoặc metadata endpoint | Chặn egress, preserve DNS/network evidence |
| Webhook compromise | Signature bypass, replay, queue poisoning | Tắt ingress/consumer có kiểm soát, xác minh event |
| Gateway/config compromise | Route public ngoài dự kiến hoặc WAF bị đổi | Khôi phục config, xác minh origin và traffic |
| Dependency compromise | Provider, database, broker hoặc KMS bị xâm nhập | Cô lập integration và phối hợp owner/provider |

### 10.2. Incident severity

Severity nên xét:

- Dữ liệu nhạy cảm đã bị đọc hoặc xuất ra ngoài chưa.
- Có thay đổi dữ liệu hoặc giao dịch không thể đảo ngược không.
- Credential có quyền rộng hay chỉ giới hạn một operation.
- Có bao nhiêu tenant/consumer/region bị ảnh hưởng.
- Hành vi còn đang diễn ra không.
- Có dấu hiệu persistence hoặc lateral movement không.
- Có yêu cầu thông báo theo hợp đồng/quy định không.

Không chỉ dựa vào số lượng request. Một request thành công đọc dữ liệu tài chính của tenant khác có thể nghiêm trọng hơn hàng nghìn request bị WAF chặn.

## 11. Incident workflow: detect, triage, contain, recover

### 11.1. Detect và triage

Nguồn phát hiện:

- Tỷ lệ 401/403/404/429 bất thường.
- Access pattern vượt baseline.
- Cross-tenant authorization denial hoặc success bất thường.
- Token/key/certificate bị sử dụng từ môi trường/network lạ.
- WAF, gateway, service mesh hoặc egress alert.
- Queue backlog, duplicate event, DLQ tăng đột biến.
- Secret manager/KMS access bất thường.
- Provider báo abuse hoặc credential compromise.

Triage:

1. Mở incident ID và chỉ định incident commander.
2. Ghi thời điểm phát hiện, alert source và phạm vi ban đầu.
3. Tra inventory theo API ID, endpoint, owner và consumer.
4. Xác định version contract, implementation, policy và key đang chạy.
5. Xác định tenant/object/data class liên quan.
6. Kiểm tra traffic đang diễn ra và dependency bị ảnh hưởng.
7. Chọn severity và quyết định containment.

### 11.2. Preserve evidence

Thu thập trước khi retention hoặc runtime thay đổi làm mất dữ liệu:

- Gateway/WAF access log, route và rule version.
- Application log, trace, audit và request/operation ID.
- Authentication/authorization decision, issuer, kid, policy version.
- Database transaction/audit và queue offset/retry/DLQ metadata.
- Secret manager/KMS access event và secret/key version reference.
- DNS, TLS, network flow và upstream provider request ID.
- Deployment/image digest, config và feature flag version.

Ghi source, query/filter, time range, collector, timestamp, hash và nơi lưu. Giữ bản gốc read-only; phân tích trên working copy. Redact PII/secret trong bản làm việc nhưng không sửa bản gốc restricted nếu cần giữ tính chứng cứ.

### 11.3. Contain

Chọn biện pháp theo loại sự cố và blast radius:

- Tắt route hoặc method bị khai thác.
- Siết WAF/gateway policy hoặc rate limit.
- Revoke API key, token, certificate hoặc signing key.
- Thu hồi session/refresh-token family.
- Chặn egress destination hoặc cô lập workload.
- Tạm dừng consumer/queue subscription có thể tạo side effect.
- Giới hạn tenant hoặc operation bị ảnh hưởng.
- Chặn origin direct access nếu gateway là trust boundary.

Containment phải ghi actor, thời điểm, incident ID, change ID, policy/config version và kết quả. Không replay queue hoặc retry thao tác tài chính trước khi xác minh operation state.

### 11.4. Eradicate và recover

- Vá nguyên nhân gốc và thêm regression test.
- Xoay credential/key bị ảnh hưởng tại issuer/provider.
- Xác minh mọi instance/region nhận key/policy mới.
- Khôi phục route theo canary.
- Đối soát database, queue, provider và business state.
- Xác minh tenant isolation, authorization và validation.
- Theo dõi traffic, error rate, abuse signal và dependency health.
- Mở lại endpoint khi owner/security approve theo severity.

### 11.5. Post-incident

- Dựng timeline từ nguồn độc lập.
- Xác định consumer, tenant, object và dữ liệu bị ảnh hưởng.
- Phân biệt điều đã xác minh với giả thuyết.
- Đánh giá credential, key và policy exposure.
- Ghi evidence gap và giới hạn retention.
- Tạo action item có owner/deadline.
- Cập nhật catalog, runbook, threat model và version history.
- Kiểm tra deprecation hoặc retire API cũ nếu đó là nguồn rủi ro.

## 12. Evidence cần liên kết với version và inventory

Khi điều tra, chỉ có request ID chưa đủ. Cần biết request đã đi qua contract, implementation, policy và dependency version nào.

| Evidence field | Dùng để xác định |
|---|---|
| API ID và operation ID | API/endpoint bị gọi |
| Contract version | Schema và semantics được công bố |
| Implementation release/image digest | Code thực tế đang chạy |
| Gateway route/config version | Routing, TLS và edge policy |
| Authorization policy version | Quy tắc allow/deny |
| Issuer, audience, kid | Trust source và key xác minh |
| Secret/key version reference | Credential/key metadata đã được dùng |
| Schema/event version | Message được publish/consume |
| Dependency/provider API version | Upstream contract |
| Consumer/client ID | Caller hoặc nhóm client |
| Tenant/object reference | Phạm vi dữ liệu và đối tượng |
| Deployment/config change ID | Thay đổi có thể liên quan |

Version phải được ghi tại thời điểm request hoặc có cách tái dựng chính xác. Chỉ biết version hiện tại sau incident không đủ nếu deployment/policy đã thay đổi.

## 13. Mẫu API inventory record

Ví dụ YAML rút gọn cho một endpoint:

~~~yaml
api:
  id: billing-invoices
  service: billing-service
  owner:
    business: finance-platform
    technical: billing-oncall
    security: api-security
  lifecycle: active
  contract:
    version: v2
    openapi: contracts/billing-v2.yaml
    implementation: billing-service-2026.11.18.3
    policy: authz-billing-42
  exposure: partner
  consumers:
    - id: partner-portal
      owner: partner-integrations
      version: v2
  endpoints:
    - operationId: getInvoice
      method: GET
      route: /v2/invoices/{invoiceId}
      data:
        classification: confidential
        tenantScoped: true
        fields: [invoice-summary]
      authentication:
        scheme: oauth2-bearer
        issuer: trusted-issuer
        audience: billing-api
      authorization:
        function: invoice:read
        objectPolicy: invoice-tenant-owner
      controls:
        rateLimitProfile: partner-read
        maxResponseBytes: 1048576
      dependencies:
        - invoice-database
      operations:
        dashboard: billing-api-overview
        runbook: billing-api-incident
~~~

Đây là cấu trúc minh họa, không phải schema chuẩn bắt buộc. Tránh đưa secret value vào catalog; issuer, audience, policy và dependency reference phải trỏ đến cấu hình được quản lý. Catalog cần validation và owner review để tránh trở thành tài liệu lỗi thời.

## 14. Mẫu version lifecycle record

~~~yaml
apiId: billing-invoices
contractVersion: v1
lifecycle: deprecated
releasedAt: 2025-05-01
deprecatedAt: 2026-08-01
sunsetAt: 2027-01-31
replacement: billing-invoices/v2
owners:
  technical: billing-oncall
  consumer-migration: partner-integrations
consumers:
  active: 3
  migrated: 7
  exceptions:
    - consumer: legacy-batch
      owner: finance-operations
      expiresAt: 2026-12-15
security:
  policyVersion: authz-billing-42
  knownLimitations:
    - legacy-scope-model
~~~

Ví dụ cho thấy version contract và policy version là hai metadata riêng. Nếu v1 có security limitation, catalog phải ghi rõ và có kế hoạch xử lý; không dùng deprecation như lý do để bỏ giám sát endpoint cũ.

## 15. CI/CD và governance

Versioning và inventory cần được kiểm tra trong quy trình phát triển, không chỉ cập nhật sau khi release.

### 15.1. Pull request checks

- OpenAPI/AsyncAPI lint và schema validation.
- Contract diff và breaking-change detection.
- Endpoint mới có owner và API ID.
- Endpoint có authentication requirement hoặc public exception được phê duyệt.
- Function/object authorization reference có mặt.
- Data classification và retention được khai báo.
- Rate limit, payload size và idempotency được định nghĩa cho operation phù hợp.
- Dependency và consumer được cập nhật.
- Security test cho BOLA, tenant isolation, mass assignment và error behavior.
- Version/deprecation metadata đúng.

### 15.2. Release gates

Trước production:

1. Security review cho endpoint/action mới hoặc thay đổi quyền.
2. Contract compatibility test với consumer quan trọng.
3. Integration test qua gateway và application.
4. Authorization test ở function và object level.
5. Abuse/resource limit test.
6. Logging/audit/trace field được kiểm tra redaction.
7. Runbook, dashboard và on-call owner tồn tại.
8. API inventory được cập nhật và gắn release/config version.

### 15.3. Runtime governance

Sau release:

- So sánh route thực tế với catalog.
- Phát hiện endpoint không có owner.
- Phát hiện version retired vẫn có traffic.
- Phát hiện security policy drift.
- Theo dõi consumer migration.
- Đánh giá credential/key rotation và dependency health.
- Cảnh báo khi audit/telemetry bị gián đoạn.

## 16. Kiểm thử kiến trúc tham chiếu

| Nhóm test | Tình huống | Kết quả mong đợi |
|---|---|---|
| Inventory completeness | Gateway có route không có catalog entry | Finding có owner xử lý |
| Ownership | API active không có technical/security owner | Release gate từ chối hoặc exception có hạn |
| Endpoint security | Endpoint mới thiếu auth policy | Không được publish ngoài public exception đã duyệt |
| Object authorization | Thay object ID sang tenant khác | Không đọc/sửa được dữ liệu ngoài tenant |
| Version compatibility | Xóa field đang được consumer dùng | Breaking change được phát hiện |
| Security compatibility | v2 vô tình bỏ scope hoặc object policy | Security test thất bại |
| Deprecation | Version deprecated vẫn có traffic | Consumer/owner được xác định và cảnh báo |
| Zombie API | Route retired còn truy cập | Phát hiện và xử lý theo decommission plan |
| Policy version | Policy thay đổi giữa incident | Có thể xác định version tại thời điểm request |
| Incident evidence | Request đi qua gateway/app/DB/queue | Correlation và evidence liên kết được |
| Containment | Revoke key hoặc disable route | Propagation được xác minh mọi instance/region |
| Recovery | Mở lại endpoint sau remediation | Regression/security tests pass |
| Dependency failure | Provider/broker/KMS lỗi | Degraded behavior đúng policy, không fail open ngoài chủ đích |
| Audit integrity | Workload cố xóa audit | Bị chặn hoặc có bản sao độc lập |

### 16.1. Diễn tập deprecation

Chọn một API version có nhiều consumer. Xác định traffic, liên hệ owner, phát hành warning, đo migration và tắt theo canary. Kiểm tra consumer chưa chuyển có được nhận diện và exception có expiry không. Xác minh route đã tắt thực sự ở edge và origin, không chỉ đổi trạng thái catalog.

### 16.2. Diễn tập incident

Kịch bản: một partner dùng API key cũ gọi endpoint export; key xuất hiện trong log của một job; endpoint v1 vẫn public và có quyền rộng.

Nhóm cần:

1. Tra API inventory để xác định owner, consumer, data class và dependency.
2. Xác định key ID, scope, version và endpoint/tenant đã sử dụng.
3. Bảo toàn gateway, app, audit và provider evidence.
4. Revoke key ở hệ thống cấp phát và kiểm tra propagation.
5. Giới hạn endpoint export hoặc chuyển sang policy chặt hơn.
6. Đánh giá dữ liệu đã export và tenant bị ảnh hưởng.
7. Cập nhật consumer sang version mới với permission tối thiểu.
8. Decommission v1 sau khi xác minh không còn consumer hợp lệ.
9. Thêm regression test và cập nhật inventory/runbook.

## 17. Chỉ số vận hành và security posture

Theo dõi chỉ số giúp biết inventory và version lifecycle có thực sự được duy trì:

- Tỷ lệ API/endpoint có owner và security contact.
- Tỷ lệ endpoint có contract và data classification.
- Số shadow/zombie API được phát hiện.
- Số version deprecated còn traffic.
- Số consumer chưa migration và số exception quá hạn.
- Tỷ lệ endpoint có function/object authorization test.
- Tỷ lệ request có correlation ID và audit cho action nhạy cảm.
- Thời gian phát hiện route/policy drift.
- Thời gian revoke credential và propagation đến mọi region.
- Thời gian xác định blast radius sau incident.
- Tỷ lệ incident có evidence manifest và timeline.
- Số dependency không có owner hoặc runbook.

Không tối ưu metric bằng cách làm đẹp con số. Ví dụ, đánh dấu mọi endpoint là retired không làm giảm rủi ro nếu route vẫn phục vụ traffic. Kết hợp catalog với runtime discovery và kiểm tra thực tế.

## 18. Những sai lầm thường gặp

- **Inventory chỉ liệt kê base URL:** không biết method, operation, data, permission và consumer.
- **Chỉ dựa vào OpenAPI:** contract có thể khác route đang deploy.
- **Không có owner:** incident không biết ai có quyền và trách nhiệm xử lý.
- **Không inventory consumer:** deprecation hoặc security change gây outage bất ngờ.
- **Gộp contract version với policy version:** không tái dựng được rule đã áp dụng.
- **Chỉ version hóa path:** schema, event, key, config và dependency không được quản lý.
- **Coi mọi schema change là tương thích:** semantic hoặc security behavior có thể đã thay đổi.
- **Giữ API cũ vô thời hạn:** endpoint không còn owner vẫn là attack surface.
- **Tắt route chỉ trong catalog:** gateway hoặc origin vẫn phục vụ endpoint.
- **Không phát hiện shadow API:** endpoint ngoài quy trình review vẫn truy cập được.
- **Không ghi version vào audit:** không biết code/policy nào đã xử lý request.
- **Containment không kiểm tra propagation:** một region vẫn chấp nhận key hoặc policy cũ.
- **Replay queue khi điều tra:** tạo thêm side effect và làm sai evidence.
- **Dựa vào metric tổng hợp để kết luận:** thiếu request-level evidence.
- **Không cập nhật inventory sau incident:** cùng một điểm yếu có thể tái xuất hiện.

## 19. Checklist trước khi phát hành

- [ ] API, service, endpoint và operation có ID ổn định.
- [ ] Mỗi API có business owner, technical owner và security contact.
- [ ] Inventory mô tả consumer, environment, exposure và lifecycle.
- [ ] Endpoint ghi data classification, read/write/export và tenant boundary.
- [ ] Authentication, function permission và object policy được khai báo riêng.
- [ ] Dependency map có database, queue, provider, identity, secret manager và KMS liên quan.
- [ ] Contract, schema, policy, implementation, config và key version được phân biệt.
- [ ] OpenAPI/AsyncAPI được lint, review và contract-test trong CI.
- [ ] Breaking change và security change có đánh giá consumer impact.
- [ ] Deprecation có replacement, migration guide, deadline và owner.
- [ ] Shadow/zombie/undocumented API được phát hiện từ runtime discovery.
- [ ] Route retired được tắt ở gateway và origin, không chỉ cập nhật catalog.
- [ ] Request/audit record có API ID, operation ID và version tại thời điểm xử lý.
- [ ] Incident runbook liên kết endpoint, owner, consumer, dependency và evidence source.
- [ ] Có quy trình preserve evidence, containment, revoke, recovery và post-incident.
- [ ] Revoke key/policy được xác minh trên mọi instance/region.
- [ ] CI có security test cho authentication, BOLA, tenant isolation, abuse và error behavior.
- [ ] Dashboard/alert theo dõi version drift, consumer migration và dependency health.
- [ ] Inventory được cập nhật sau release, incident và decommission.

Versioning, inventory và incident response tạo thành một hệ thống quản trị API liên tục. Inventory cho biết bề mặt tấn công và người chịu trách nhiệm; versioning cho biết contract, policy và implementation nào đang có hiệu lực; incident response dùng các dữ liệu đó để khoanh vùng và khôi phục có kiểm chứng. Khi ba năng lực được liên kết ở cấp endpoint, object và business flow, tổ chức có thể thay đổi API an toàn hơn và xử lý sự cố nhanh, chính xác hơn.
