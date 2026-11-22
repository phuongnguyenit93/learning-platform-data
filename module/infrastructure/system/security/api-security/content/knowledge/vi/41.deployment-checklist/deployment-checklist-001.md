# Checklist inventory, owner, contract và version

## 1. Mục tiêu trước khi triển khai API

Một API chỉ nên được đưa vào production khi tổ chức trả lời được bốn câu hỏi:

1. **Inventory:** API, operation và đường truy cập nào thực sự tồn tại?
2. **Owner:** Ai chịu trách nhiệm về chức năng, contract, bảo mật và vận hành?
3. **Contract:** Client và server đã thống nhất cấu trúc, semantics, authentication, authorization và lỗi chưa?
4. **Version:** Phiên bản nào đang được hỗ trợ, client nào đang dùng và kế hoạch ngừng phiên bản cũ là gì?

Thiếu một trong bốn phần này làm tăng rủi ro triển khai. Một route không có trong inventory có thể bỏ qua review; một endpoint không có owner có thể không được vá; contract không được quản lý có thể lệch giữa gateway và service; version cũ có thể tiếp tục public dù đã bị coi là retired.

Checklist này áp dụng cho REST/HTTP API, GraphQL, gRPC, webhook và asynchronous API. Cần inventory cả API public, partner, internal, admin, mobile/backend, service-to-service và endpoint do gateway hoặc framework tự sinh.

## 2. Inventory không chỉ là danh sách URL

API inventory là hồ sơ có thể truy vấn về bề mặt API đang được phát triển, triển khai và sử dụng. Một URL không đủ để mô tả một function. Cùng một path có thể có nhiều HTTP method, permission, request schema, side effect và version khác nhau.

Ví dụ:

| Operation | Method/path | Function | Permission |
|---|---|---|---|
| getUser | GET /api/users/{id} | Đọc hồ sơ user | users:read |
| updateUser | PATCH /api/users/{id} | Sửa hồ sơ user | users:update |
| disableUser | POST /api/users/{id}/disable | Vô hiệu hóa user | users:disable |
| exportUsers | POST /api/users/export | Export dữ liệu | users:export |

Inventory cần ghi theo operation/route đã resolve, không chỉ theo controller hoặc base path. Với GraphQL, cần ghi query/mutation hoặc resolver nhạy cảm; với gRPC, ghi service/method; với webhook, ghi sender, event type và receiver; với event API, ghi topic, schema và producer/consumer.

## 3. Phân biệt các lớp inventory

Nên quản lý ít nhất các lớp sau:

| Lớp | Nội dung | Câu hỏi kiểm soát |
|---|---|---|
| Service inventory | Service, workload, owner, environment | Ai vận hành service? |
| API surface inventory | Host, route, method, protocol, exposure | Đường nào có thể được gọi? |
| Operation inventory | Function, permission, side effect | Caller có thể làm gì? |
| Data inventory | Object, tenant scope, classification | Dữ liệu nào được trả hoặc thay đổi? |
| Contract inventory | OpenAPI, protobuf, AsyncAPI, schema | Hình dạng và semantics được phê duyệt là gì? |
| Version inventory | API version, contract version, lifecycle | Version nào được hỗ trợ? |
| Consumer inventory | Client, partner, service, SDK | Ai đang phụ thuộc API? |
| Runtime inventory | Route và version đang nhận traffic | Production thực tế đang chạy gì? |

Các lớp này liên kết bằng ID ổn định. Không dùng tên hiển thị hoặc URL thô làm khóa duy nhất vì tên có thể đổi, route có thể rewrite và path có thể chứa object ID.

## 4. Trường dữ liệu tối thiểu của API inventory

Mỗi API hoặc operation nên có các trường:

| Nhóm | Trường nên có |
|---|---|
| Định danh | API ID, service ID, operation ID, tên hiển thị |
| Giao thức | REST/HTTP, GraphQL, gRPC, webhook, event/message |
| Route | Host, base path, method, route template, protocol |
| Exposure | Public, partner, internal, admin, private network |
| Environment | Dev, test, staging, production |
| Owner | Business owner, technical owner, security contact, on-call |
| Contract | Artifact URI/version, format, canonical hash |
| API version | Version được expose và version negotiation rule |
| Lifecycle | Draft, active, deprecated, sunset scheduled, retired |
| Authentication | Scheme, issuer, audience, client identity |
| Authorization | Required permission/scope, object/tenant policy |
| Data | Data classification, PII/sensitive fields, retention |
| Dependencies | Upstream, downstream, database, queue, external provider |
| Consumer | Client/partner/service ID và owner |
| Operations | Rate limit, quota, timeout, payload/page limit |
| Reliability | SLO, availability tier, retry/idempotency semantics |
| Deployment | Build, gateway route version, policy version |
| Review | Last reviewed, next review, approval/evidence links |

Không phải mọi trường đều áp dụng cho mọi protocol. Nếu không áp dụng, ghi rõ not-applicable hoặc để trống theo schema đã định nghĩa; không điền dữ liệu phỏng đoán.

## 5. Khám phá API thực tế

Inventory ban đầu thường không đầy đủ. Cần kết hợp nhiều nguồn:

- OpenAPI/Swagger, protobuf, AsyncAPI và schema registry.
- Source code route/controller/resolver/interceptor.
- API Gateway, ingress, load balancer và service mesh config.
- DNS, certificate và public hostname inventory.
- Deployment manifest, service discovery và runtime metadata.
- Access log, metrics, trace và API discovery tooling.
- Client SDK, mobile app, partner registry và integration documents.
- Security scan, DAST, penetration test và incident history.

Không coi một nguồn đơn lẻ là sự thật tuyệt đối. OpenAPI có thể thiếu route cũ; source code có thể có controller không được expose; gateway có thể route tới service khác; runtime có thể còn một endpoint do cấu hình cũ.

### 5.1 So sánh declared và observed API

Đối chiếu:

| Declared | Observed | Dấu hiệu cần xử lý |
|---|---|---|
| Có trong contract | Có traffic | API được công bố và đang dùng |
| Có trong contract | Không có traffic | Có thể chưa dùng, client dormant hoặc spec cũ |
| Không có trong contract | Có traffic | Shadow/undocumented API, route drift hoặc scan |
| Có trong gateway | Upstream không còn | Route stale hoặc deployment lỗi |
| Không có trong gateway | Service vẫn expose | Direct upstream/bypass surface |

Traffic không chứng minh API hợp lệ. Request có thể là scan hoặc abuse. Cần xác minh owner, route và caller trước khi đưa một endpoint quan sát được vào danh mục được hỗ trợ.

## 6. Phân loại exposure và mức rủi ro

Ghi rõ API thuộc nhóm nào:

- **Public:** bất kỳ client Internet nào cũng có thể kết nối.
- **Partner:** chỉ client/đối tác được đăng ký.
- **Internal:** chỉ workload hoặc user trong tổ chức.
- **Admin/management:** thay đổi cấu hình, quyền, secret hoặc vận hành.
- **Webhook receiver:** nhận sự kiện từ hệ thống ngoài.
- **Async/event:** nhận hoặc phát message qua broker.

Exposure không phải là authorization. API nằm trong private network vẫn cần xác thực workload và kiểm tra permission. API public không nhất thiết cho phép anonymous operation.

Đánh giá rủi ro theo dữ liệu và hành động:

| Mức tác động | Ví dụ | Kiểm soát cần chú ý |
|---|---|---|
| Thấp | Public metadata, health summary tối thiểu | Abuse control, cache, availability |
| Trung bình | Hồ sơ user, search nội bộ | Authentication, object/tenant authorization, privacy |
| Cao | Export, billing, approval, account disable | Permission riêng, audit, rate/quota, idempotency |
| Rất cao | Secret rotation, role assignment, payment/refund, security config | Strong authentication, least privilege, approval, alert và rollback |

Phân loại phải phản ánh tác động thực tế, không chỉ dựa vào tên endpoint hoặc network location.

## 7. Owner phải được xác định rõ

Mỗi API cần một người hoặc nhóm chịu trách nhiệm. Tên team chung chung không đủ nếu không có contact và escalation path.

Nên phân biệt:

| Vai trò | Trách nhiệm |
|---|---|
| Business owner | Mục đích, consumer, SLA và lifecycle |
| API/product owner | Contract, usability, versioning và deprecation |
| Technical/service owner | Code, deployment, runtime, dependency và reliability |
| Security owner/contact | Threat model, authz, data handling, findings và exception |
| Data owner/steward | Classification, purpose, retention và sharing |
| Consumer owner | Migration và tương thích ở phía client |
| On-call/operations | Monitoring, incident và rollback |

Một người có thể đảm nhiệm nhiều vai trò ở team nhỏ, nhưng trách nhiệm vẫn phải được ghi riêng để không bỏ sót.

## 8. RACI cho thay đổi API

Trước khi phát hành breaking hoặc security-sensitive change, xác định ai Responsible, Accountable, Consulted và Informed:

| Hoạt động | Business/API owner | Service owner | Security | Consumer owner | Operations |
|---|---|---|---|---|---|
| Định nghĩa function/contract | A/R | R | C | C | I |
| Phê duyệt auth/data policy | C | R | A/R | I | C |
| Contract compatibility review | A | R | C | R/C | I |
| Rollout/rollback | I | A/R | C | I | R |
| Deprecation/sunset | A/R | R | C | R | C |
| Incident xử lý API | C | R | R/C | I | A/R theo quy trình |

Ma trận trên là mẫu. Tổ chức cần điều chỉnh theo governance thực tế và bảo đảm mỗi hoạt động có đúng một Accountable owner.

## 9. Kiểm tra owner trước khi deploy

- Owner chính và backup còn hoạt động.
- Có kênh liên lạc/on-call phù hợp mức criticality.
- Owner có quyền truy cập dashboard, logs và deployment controls cần thiết.
- Security contact biết API xử lý dữ liệu gì và public surface nào.
- Data owner đã xác nhận mục đích sử dụng/chia sẻ nếu API xử lý dữ liệu nhạy cảm.
- Consumer owner đã được đăng ký nếu API có client/partner phụ thuộc.
- Escalation path khi owner vắng mặt hoặc team giải thể.
- Có ngày review tiếp theo và quy trình chuyển giao ownership.

Không đưa production API vào trạng thái active mà không có owner chịu trách nhiệm. Nếu owner chưa xác định, cần giữ deployment ở trạng thái chưa được phê duyệt hoặc có ngoại lệ có thời hạn và người chịu trách nhiệm tạm thời.

## 10. Contract là nguồn chuẩn được phê duyệt

API contract mô tả cách consumer tương tác với provider. Tùy protocol, artifact có thể là:

- OpenAPI cho HTTP/REST.
- GraphQL schema cho query, mutation và subscription.
- Protobuf/service definition cho gRPC.
- AsyncAPI và schema format cho message/event.
- Webhook event catalog và signature/retry contract.

Contract phải được version control, review và liên kết với source/build. Không để contract chỉ nằm trong wiki hoặc tài liệu không có lịch sử thay đổi.

Contract không chỉ gồm field và type. Với API security, cần mô tả:

- Authentication scheme và token audience/issuer.
- Required scopes/permissions cho operation.
- Object/tenant access assumptions.
- Validation constraints và maximum size.
- Error status/code và retry behavior.
- Idempotency và side effect.
- Rate/quota và pagination.
- Data classification và field được phép trả.
- Deprecation/version policy.

OpenAPI security requirement mô tả security scheme ở mức contract, nhưng không tự chứng minh implementation đã enforce object-level authorization. Cần policy review và test bổ sung.

## 11. Version control và contract artifact

Mỗi contract change cần:

1. Pull request hoặc change request có owner.
2. Diff dễ đọc so với phiên bản đã phát hành.
3. Compatibility classification.
4. Security/data impact review.
5. Provider test và consumer contract test phù hợp.
6. Contract artifact được lưu cùng build/release metadata.
7. Approval và timestamp.

Ví dụ metadata gắn với artifact:

~~~yaml
serviceId: customer-api
operationGroup: customer-profile
apiVersion: v2
contract:
  format: openapi
  artifact: contracts/customer-api-v2.yaml
  artifactVersion: 2.4.1
  sha256: 7f2c...
ownership:
  business: customer-platform
  technical: customer-api-team
  security: security-engineering
lifecycle: active
~~~

Đây là cấu trúc minh họa, không phải schema registry bắt buộc. Hash cần tính từ artifact canonicalized hoặc file release thực tế; không nhập hash giả vào production inventory.

## 12. Phân biệt API version, contract version và build version

Ba khái niệm thường bị trộn lẫn:

| Version | Mô tả | Ví dụ |
|---|---|---|
| API version | Phiên bản được consumer chọn hoặc route expose | /v2/customers |
| Contract version | Phiên bản artifact/schema đã được review | OpenAPI 2.4.1 |
| Build/release version | Phiên bản code/artifact được deploy | 2026.11.18.3 hoặc commit SHA |

OpenAPI info.version thường là version của tài liệu/API theo convention của team; nó không tự động có nghĩa route path phải chứa cùng chuỗi. Cần định nghĩa mapping rõ giữa API version, contract artifact và deployed build.

Ví dụ một build có thể phục vụ đồng thời /v1 và /v2; mỗi route map tới contract và policy riêng. Một contract version có thể có nhiều build sửa lỗi không breaking. Không dùng build number làm API version nếu client không có semantics ổn định để dựa vào.

## 13. Versioning strategy

Các cách phổ biến:

| Cách | Ví dụ | Điểm cần quản lý |
|---|---|---|
| URI path | /api/v2/orders | Rõ ràng, route và gateway phải map đúng |
| Header | API-Version: 2 | Client/gateway phải resolve header nhất quán |
| Media type | Accept: application/vnd.example.v2+json | Content negotiation và cache key |
| Schema/message version | Event schema version | Producer/consumer compatibility và replay |

Chọn một strategy nhất quán cho từng API family. Không cho client truyền version tùy ý để kích hoạt code path cũ hoặc policy yếu hơn.

Version phải được resolve ở biên tin cậy và ghi vào telemetry. Nếu version không được hỗ trợ, trả lỗi theo contract, không âm thầm fallback sang version gần nhất nếu điều đó thay đổi semantics hoặc security policy.

## 14. Phân loại contract change

Mỗi thay đổi nên được đánh giá theo consumer compatibility:

| Thay đổi | Tác động thường gặp | Cách xử lý |
|---|---|---|
| Thêm optional request field | Có thể tương thích nếu server/client xử lý unknown field phù hợp | Test parser và validation |
| Thêm required request field | Breaking với client cũ | Version mới hoặc migration |
| Xóa/đổi tên request field | Breaking nếu client còn gửi | Đo usage, deprecate và chuyển đổi |
| Thêm response field | Có thể phá strict deserializer | Test client behavior |
| Xóa response field | Breaking với client đang đọc | Migration/version mới |
| Đổi type/format | Thường breaking | Version mới hoặc adapter |
| Thêm enum value | Client cũ có thể không nhận diện | Quy định unknown-value handling |
| Thu hẹp enum | Có thể làm client lỗi | Đo consumer và migration |
| Đổi validation rule | Có thể từ chối request trước đây hợp lệ | Compatibility test |
| Đổi status/error semantics | Có thể làm client retry sai | Contract review |
| Đổi auth scope/audience | Security và compatibility impact | Security approval |
| Đổi tenant/object semantics | Nguy cơ truy cập sai dữ liệu | Security/domain review bắt buộc |

Additive không đồng nghĩa luôn backward-compatible. Client dùng strict schema, exhaustive enum switch hoặc validator riêng có thể bị lỗi khi xuất hiện field/value mới.

## 15. Kiểm tra security contract

Trước deploy, review từng operation:

- Authentication bắt buộc hay anonymous được phép?
- Issuer, audience, signature algorithm và token lifetime có đúng?
- Required permission/scope là gì?
- Có kiểm tra object ownership và tenant isolation không?
- Field nào được client ghi, field nào chỉ server được ghi?
- Có mass assignment hoặc property-level exposure không?
- Request size, page size, filter depth và batch size có giới hạn?
- Endpoint có thể gọi URL ngoài hoặc tạo SSRF không?
- File upload, webhook, export và async job có policy riêng?
- Error response có lộ stack, SQL, path hoặc secret không?
- Audit event có đủ principal, action, object và outcome không?

Không chỉ so sánh schema. Một field có thể giữ nguyên type nhưng semantics thay đổi từ display label sang permission flag; đó là security-sensitive change dù OpenAPI diff rất nhỏ.

## 16. Kiểm tra consumer và dependency

Mỗi API active nên biết consumer nào đang dùng:

| Consumer | Loại | Thông tin cần có |
|---|---|---|
| Web frontend | First-party | Owner, release, API version |
| Mobile app | First-party | App version, minimum supported version |
| Partner | External | Organization, technical contact, credential/client ID |
| Internal service | Workload | Service identity, owner, deployed version |
| Batch/worker | Async | Schedule, queue/topic, schema version |
| Third-party integration | External | Contract, data sharing, retry behavior |

Không coi User-Agent hoặc header tự khai báo là consumer identity đã xác minh. Dùng OAuth client ID, mTLS identity, API key ID đã đăng ký hoặc workload identity; metadata client version chỉ là tín hiệu bổ sung.

Ghi nhận dependency ngược: API đang gọi upstream nào, publish event nào, database nào, secret/provider nào. Khi thay đổi contract, cần biết cả producer và consumer downstream.

## 17. Kiểm tra client compatibility trước khi deploy

- Consumer đã được liệt kê và có owner.
- Client SDK/app version được biết nếu có.
- Contract diff đã được phân loại.
- Consumer contract test hoặc compatibility test đã chạy.
- Client có xử lý unknown response field và enum value theo contract không?
- Retry/backoff và idempotency có tương thích?
- Client có gửi field cũ đã bị deprecate không?
- Có consumer không xác định hoặc traffic version cũ không?
- Partner đã được thông báo nếu thay đổi ảnh hưởng integration?
- Có migration guide và thời gian chuyển đổi?

Nếu không thể test mọi consumer, ghi rõ phần chưa xác minh, phạm vi rủi ro và owner chấp nhận. Không đánh dấu compatible chỉ vì provider unit test pass.

## 18. Deprecation và sunset

Deprecation là thông báo một version/operation sẽ ngừng được khuyến nghị hoặc hỗ trợ. Sunset là thời điểm dự kiến ngừng phục vụ. Hai mốc này cần được quản lý riêng.

Inventory nên ghi:

- Version/operation bị deprecated.
- Ngày công bố.
- Sunset date/time và timezone.
- Version/operation thay thế.
- Consumer/owner bị ảnh hưởng.
- Migration guide.
- Lý do và security impact.
- Ngoại lệ đã phê duyệt, người phê duyệt và ngày hết hạn.

Có thể dùng trường deprecated trong OpenAPI và header Sunset theo RFC 8594 khi phù hợp. Metadata chỉ có tác dụng nếu client/partner được thông báo và gateway/service thực thi lifecycle đúng kế hoạch.

Không retire version chỉ vì đã công bố deprecation. Cần đo traffic và xác nhận consumer trọng yếu đã chuyển đổi. Ngược lại, không kéo dài version cũ vô thời hạn nếu nó thiếu security fix hoặc còn auth policy yếu.

## 19. Version cũ là một bề mặt bảo mật

Version cũ có thể:

- Không có object-level authorization mới.
- Dùng scope rộng hoặc issuer/audience cũ.
- Trả field nhạy cảm đã bị loại khỏi version mới.
- Bỏ qua validation, rate limit hoặc tenant context.
- Route tới upstream cũ chưa được vá.
- Không hỗ trợ audit hoặc security headers hiện tại.

Do đó, inventory version cần gắn security posture:

| Version | Lifecycle | Security posture | Quyết định |
|---|---|---|---|
| v3 | Active | Policy hiện hành | Tiếp tục hỗ trợ |
| v2 | Deprecated | Có migration path, vẫn được vá | Theo dõi consumer và sunset |
| v1 | Sunset scheduled | Thiếu một số control mới | Chặn consumer mới, migration có deadline |
| v0/internal-old | Retired | Không còn hỗ trợ | Route phải bị đóng |

Ví dụ trên chỉ minh họa. Không để version retired vẫn được expose qua direct upstream hoặc gateway route cũ. Mọi ngoại lệ phải có owner, risk acceptance, expiry và compensating control.

## 20. Inventory cho API asynchronous và event

Không chỉ inventory HTTP endpoint. Với message/event API, ghi:

- Topic/queue/subject và exposure.
- Producer service/operation.
- Consumer group/service và owner.
- Event name, schema format/version và compatibility mode.
- Tenant/security context trong message.
- Authentication/integrity của producer.
- Retention, replay và dead-letter policy.
- Retry, idempotency và ordering semantics.
- Data classification và retention.

Consumer có thể replay message cũ sau nhiều ngày/tháng. Khi retire schema version, kiểm tra broker retention, archive, DLQ và backfill workflow. Một schema mới tương thích với message hiện tại vẫn có thể làm replay dữ liệu cũ thất bại.

Với webhook, inventory thêm signing key/secret reference, signature algorithm, timestamp tolerance, retry schedule, event ID và receiver owner. Không ghi secret thực vào inventory.

## 21. Contract diff và CI/CD gate

Mỗi pull request thay đổi API cần qua pipeline:

~~~text
Contract change
      |
      v
Parse and normalize artifact
      |
      v
Compare with released contract
      |
      v
Classify compatibility and semantic changes
      |
      v
Check inventory, owner and lifecycle
      |
      v
Check auth/data/security policy
      |
      v
Provider + consumer contract tests
      |
      v
Approval for breaking/high-risk change
      |
      v
Deploy canary and verify runtime mapping
~~~

CI gate nên chặn hoặc yêu cầu approval khi:

- Operation mới không có owner hoặc permission.
- Public/admin route không được đăng ký trong inventory.
- Contract hash không gắn với build.
- Breaking change chưa có version/migration plan.
- Security scheme bị gỡ hoặc scope bị nới rộng ngoài phê duyệt.
- Response schema thêm field bị phân loại nhạy cảm.
- API retired vẫn có route active.
- Consumer contract test thất bại.
- Version negotiation có fallback không rõ ràng.

Không chỉ dựa vào một tool diff. Tool có thể phát hiện field/type change nhưng khó hiểu semantics, tenant isolation hoặc thay đổi quyền. Security-sensitive change cần review của owner và security.

## 22. Runtime verification sau deploy

Sau deploy, đối chiếu:

- Gateway route/version với API inventory.
- Service build với contract artifact hash.
- Runtime policy với permission/security metadata.
- Upstream target với service owner và environment.
- Client traffic với supported/deprecated version.
- Error/validation rate với baseline.
- Response schema sampling với contract.
- Consumer/schema registry với producer version.

Mọi request nên có route/operation ID, API version, deployed build và request ID trong telemetry. Không ghi token, raw payload hoặc PII chỉ để chứng minh version.

Nếu gateway và service chạy contract hash khác nhau ngoài kế hoạch, dừng rollout hoặc điều tra trước khi mở traffic rộng. Nếu version retired còn request, xác minh caller và đường truy cập; không tự động cho phép chỉ vì request đến từ private network.

## 23. Quy trình cập nhật inventory

Inventory cần được cập nhật theo lifecycle:

1. **Design:** tạo API/operation ID, owner, exposure, contract draft và permission.
2. **Review:** security/data owner xác nhận policy, classification và consumer impact.
3. **Build:** gắn contract hash và test evidence vào artifact.
4. **Deploy:** đăng ký route/version/build/policy được triển khai.
5. **Operate:** thu thập observed traffic, consumer và drift signals.
6. **Change:** cập nhật contract/version/lifecycle qua review.
7. **Deprecate:** ghi sunset, migration guide và owner consumer.
8. **Retire:** gỡ route, credential, DNS/certificate hoặc subscription không còn dùng.
9. **Archive:** lưu contract và evidence cần thiết theo retention policy.

Không xóa lịch sử version cũ khỏi inventory. Lịch sử giúp điều tra incident, xác định consumer đã gọi version nào và chứng minh route đã được retire.

## 24. Mẫu hồ sơ inventory

Ví dụ rút gọn cho một REST API:

~~~yaml
apiId: customer-profile-api
serviceId: customer-service
protocol: https-rest
exposure: partner
environment: production
owners:
  business: customer-platform
  technical: customer-service-team
  securityContact: api-security
contract:
  format: openapi
  artifact: contracts/customer-profile-v2.yaml
  version: 2.1.0
  hash: sha256:<computed-at-build>
versions:
  - value: v2
    lifecycle: active
  - value: v1
    lifecycle: deprecated
    sunsetAt: 2027-03-31T17:00:00Z
operations:
  - operationId: getCustomer
    method: GET
    path: /api/v2/customers/{customerId}
    permission: customers:read
    dataClassification: confidential
    objectPolicy: tenant-scoped
    ratePolicy: partner-and-tenant
consumers:
  - clientId: partner-client-42
    owner: partner-integration-team
    supportedVersions: [v1, v2]
deployment:
  build: <build-id>
  gatewayRouteVersion: <gateway-config-id>
  policyVersion: <authorization-policy-id>
~~~

Đây là ví dụ minh họa. sunsetAt và hash phải là dữ liệu thật đã được phê duyệt/tính toán; placeholder không được coi là giá trị production. Bảo vệ inventory vì nó có thể tiết lộ hostname, route admin, owner, data classification và dependency nội bộ.

## 25. Bảo vệ chính inventory

API inventory là tài sản nhạy cảm vì tập trung thông tin về bề mặt tấn công. Áp dụng:

- Authentication và role-based access cho người xem/sửa.
- Chỉ owner/governance role được thay đổi lifecycle và contract metadata.
- Audit thay đổi owner, exposure, version, permission và sunset date.
- Không lưu credential, private key, token hoặc secret value.
- Dùng secret reference/identifier nếu cần liên kết secret manager.
- Phân loại internal route và endpoint quản trị.
- Hạn chế export hoặc public hóa toàn bộ inventory.
- Retention/version history và backup phù hợp.
- Kiểm soát integration tự động ghi inventory để tránh dữ liệu giả mạo.

Không dùng API inventory làm nguồn authorization runtime nếu chưa có quy trình đồng bộ, validation và availability phù hợp. Runtime policy cần artifact được build/release và xác minh riêng.

## 26. Bằng chứng cần có trong deployment review

Trước go/no-go, lưu bằng chứng:

- Inventory record và owner approval.
- Contract artifact/hash đã phát hành.
- Contract diff và compatibility classification.
- Security review cho authentication, permission, object/tenant và data fields.
- Provider/consumer test results.
- Version/lifecycle và migration plan.
- Consumer list và thông báo partner nếu cần.
- Gateway route/policy diff.
- Deployment build, environment và rollback target.
- Canary/runtime verification.
- Monitoring dashboard, alert và runbook.
- Ngoại lệ/risk acceptance có owner và expiry.

Bằng chứng phải gắn với release cụ thể. Một tài liệu review cũ không chứng minh deployment hiện tại vẫn đúng contract hoặc policy.

## 27. Go/no-go checklist

### Inventory và exposure

- [ ] Service, API và operation có ID ổn định.
- [ ] Đã inventory route/method/protocol và mọi alias/version.
- [ ] Đã đối chiếu contract/source/gateway với runtime observed surface.
- [ ] Public, partner, internal, admin và async exposure được phân loại.
- [ ] Direct upstream và shadow/undocumented API đã được kiểm tra.
- [ ] Data classification và object/tenant scope đã được ghi.

### Owner và trách nhiệm

- [ ] Business owner và technical owner đã xác nhận.
- [ ] Security contact và data owner đã được chỉ định khi cần.
- [ ] On-call/escalation path hoạt động.
- [ ] Consumer/partner owner đã được đăng ký.
- [ ] RACI và approval path cho breaking/security change rõ ràng.
- [ ] Có next review date và quy trình chuyển giao ownership.

### Contract và security policy

- [ ] Contract artifact có version control và approval.
- [ ] API version, contract version và build version được phân biệt.
- [ ] Contract mô tả auth scheme, scope/permission, validation, error và limit.
- [ ] Object authorization, tenant isolation và writable/readable fields đã được review.
- [ ] Contract diff đã phân loại breaking, additive và semantic/security change.
- [ ] Provider/consumer tests pass hoặc gap có owner chấp nhận.
- [ ] Contract hash gắn với build/deployment evidence.

### Version và consumer

- [ ] Version negotiation chỉ cho phép version được hỗ trợ.
- [ ] Consumer/client/partner phụ thuộc version đã được nhận diện.
- [ ] Unknown consumer traffic đã được phân tích.
- [ ] Deprecated version có sunset date và migration guide.
- [ ] Retired version không còn route ở gateway hoặc direct upstream.
- [ ] Ngoại lệ có approver, lý do, compensating control và expiry.

### Runtime và vận hành

- [ ] Gateway route, upstream, build và policy khớp inventory.
- [ ] Runtime telemetry có route ID, API version, build và request ID.
- [ ] Có phát hiện contract hash/policy/version drift.
- [ ] Dashboard, alert và runbook có owner.
- [ ] Rollback target và cách khôi phục contract đã được xác minh.
- [ ] Inventory change có audit trail và access control.

## 28. Các anti-pattern cần tránh

1. **Inventory chỉ có URL:** bỏ sót method, function, permission và data scope.
2. **Chỉ tin OpenAPI:** bỏ sót route cũ, internal hoặc gateway-generated.
3. **Không có owner cụ thể:** không ai chịu trách nhiệm vá và deprecate.
4. **Một owner cho mọi API nhưng không có consumer owner:** migration không có người thực hiện.
5. **Contract nằm ngoài version control:** không biết thay đổi nào đã được phê duyệt.
6. **Nhầm contract version với build version:** client phụ thuộc version không ổn định.
7. **Mọi additive change đều coi là safe:** strict client hoặc semantic change có thể lỗi.
8. **Deprecated không có sunset:** version cũ tồn tại vô thời hạn.
9. **Retired chỉ xóa khỏi tài liệu:** route vẫn public ở gateway/upstream.
10. **Tin header client khai báo version/identity:** dễ giả mạo.
11. **Không inventory async/webhook:** producer/consumer và replay không được quản lý.
12. **Inventory chứa secret thật:** registry trở thành kho credential.
13. **Không đối chiếu runtime:** declared surface khác production thực tế.
14. **Không giữ history:** khó điều tra incident và consumer cũ.

## 29. Quy trình xử lý khi phát hiện thiếu inventory hoặc contract drift

Khi phát hiện route không có owner, contract hoặc version:

1. Xác định route/operation thực tế từ gateway và runtime evidence.
2. Kiểm tra caller, exposure, data classification và side effect.
3. Gán owner tạm thời có quyền xử lý.
4. Xác định contract đang được thực thi từ code/build và client behavior.
5. Đánh giá auth/authz, tenant isolation, validation và data exposure.
6. Nếu route không được phê duyệt hoặc có rủi ro cao, hạn chế traffic/disable theo incident/change process.
7. Tạo inventory record và contract artifact được review.
8. Xác định version/lifecycle và consumer bị ảnh hưởng.
9. Thêm contract test, runtime telemetry và CI gate.
10. Theo dõi tới khi declared và observed state đồng bộ.

Không tự động xóa route chỉ vì chưa có trong inventory; có thể đó là dependency production chưa được ghi nhận. Cần xác định owner và impact trước khi retire.

## 30. Chu kỳ review định kỳ

Inventory không phải tài liệu làm một lần trước release. Review theo chu kỳ và trigger:

- Trước mỗi public/partner API release.
- Khi thêm route, method, permission, field nhạy cảm hoặc consumer mới.
- Khi đổi auth issuer/audience, gateway, network path hoặc tenant semantics.
- Khi có incident, security finding hoặc contract drift.
- Khi owner/team/service thay đổi.
- Trước deprecation, sunset và retirement.
- Định kỳ theo criticality; API admin/high-impact cần review thường xuyên hơn.

Trong review, so sánh declared inventory, deployed config và observed traffic; xác minh owner còn chịu trách nhiệm; kiểm tra consumer version cũ; rà soát exception đã hết hạn; và xác nhận security policy vẫn phù hợp.

Một deployment chỉ có thể được quản lý tốt khi API surface có thể được tìm thấy, mỗi function có người chịu trách nhiệm, contract được version hóa và consumer biết version nào họ đang dùng. Inventory, ownership, contract và version phải liên kết với bằng chứng build/runtime để phát hiện route bị bỏ quên, thay đổi phá tương thích và API cũ còn mở sau khi đã ngừng hỗ trợ.
