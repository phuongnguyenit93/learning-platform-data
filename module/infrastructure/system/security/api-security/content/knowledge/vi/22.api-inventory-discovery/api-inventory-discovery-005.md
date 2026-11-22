# Phân biệt public, partner và internal API

## 1. Vì sao cần phân loại API?

Một hệ thống có thể cung cấp API cho ứng dụng di động, khách hàng bên ngoài, đối tác tích hợp, dịch vụ nội bộ và tác vụ vận hành. Các nhóm caller này có mức độ tin cậy, cách xác thực, phạm vi dữ liệu và kỳ vọng vận hành khác nhau. Nếu tất cả endpoint được gom chung vào một nhóm “API đã đăng nhập” hoặc “API nội bộ”, đội phát triển khó xác định đúng ranh giới bảo mật và dễ cấp quyền rộng hơn nhu cầu.

Phân biệt **public API**, **partner API** và **internal API** giúp trả lời ba câu hỏi:

- Ai là đối tượng được thiết kế để sử dụng API?
- Quan hệ tin cậy giữa tổ chức vận hành API và caller được thiết lập, quản lý như thế nào?
- Những kiểm soát nào cần có cho truy cập, dữ liệu, mạng, thay đổi contract và vận hành?

Đây là phân loại theo **audience và trust boundary**. Nó không tự mô tả API có cho phép truy cập ẩn danh hay không, cũng không chỉ ra API có đang mở ra Internet hay chỉ nằm trong private network. Hai yếu tố đó cần được ghi nhận riêng.

## 2. Định nghĩa ba nhóm API

| Nhóm | Audience dự kiến | Quan hệ tin cậy | Ví dụ |
|---|---|---|---|
| Public API | Nhiều developer, khách hàng hoặc ứng dụng bên ngoài không thuộc một nhóm đối tác được phê duyệt riêng. | Mở cho một audience rộng; caller có thể thay đổi và không được tin cậy mặc định. | API sản phẩm cho developer, API tra cứu công khai, API dành cho mobile/web client. |
| Partner API | Một hoặc nhiều tổ chức đối tác đã được xác định và có quan hệ tích hợp/quản trị. | Trust được thiết lập theo từng partner, hợp đồng, credential, scope và quy trình onboarding/offboarding. | API trao đổi đơn hàng với nhà vận chuyển, API thanh toán, API đồng bộ dữ liệu với đại lý. |
| Internal API | Service, workload, ứng dụng hoặc nhóm vận hành trong cùng tổ chức và trust domain được quản lý. | Chỉ dành cho workload/principal nội bộ được nhận diện; không mặc định mọi thành phần trong mạng nội bộ đều đáng tin. | API giữa order-service và inventory-service, API quản trị service mesh, API nội bộ cho batch worker. |

Một API có thể có nhiều consumer nhưng vẫn thuộc một nhóm audience chính. Ví dụ, API của một nhà vận chuyển chỉ phục vụ các merchant đã ký hợp đồng là partner API, dù endpoint có thể truy cập qua Internet. API được công bố tài liệu công khai để developer đăng ký cũng có thể là public API nhưng yêu cầu API key hoặc OAuth trước khi sử dụng.

## 3. Không nhầm audience với khả năng truy cập mạng

Một nhầm lẫn phổ biến là cho rằng “public API” đồng nghĩa với endpoint không cần đăng nhập, còn “internal API” đồng nghĩa với endpoint an toàn vì chỉ nằm trong mạng nội bộ. Hai kết luận này đều sai.

Hãy phân loại theo hai trục độc lập:

1. **Audience/trust:** public, partner hay internal.
2. **Network exposure:** Internet-facing, private network, private link/VPN, service mesh hoặc chỉ loopback/local.

Ví dụ:

| Audience | Network exposure | Diễn giải |
|---|---|---|
| Public | Internet-facing | Developer bên ngoài có thể kết nối theo hợp đồng công khai; vẫn có thể yêu cầu xác thực và phân quyền. |
| Public | Private/VPN | API public theo mô hình sản phẩm nhưng chỉ phân phối qua kết nối riêng cho một số môi trường/khách hàng; cần ghi rõ điều kiện tiếp cận. |
| Partner | Internet-facing | Đối tác gọi qua Internet bằng mTLS, OAuth client credentials, API key hoặc cơ chế được thỏa thuận. |
| Partner | Private link/VPN | Chỉ đối tác được kết nối qua đường riêng; vẫn cần xác thực và authorization cho từng partner. |
| Internal | Private network/service mesh | Service nội bộ gọi nhau qua danh tính workload và policy; network location chỉ là một lớp bảo vệ. |
| Internal | Internet-facing do cấu hình sai | Đây là exposure ngoài dự kiến cần xử lý như sự cố cấu hình và đánh giá lại rủi ro. |

Không dùng tên DNS, subnet hoặc việc endpoint nằm sau VPN làm bằng chứng duy nhất về quyền truy cập. Network control giúp giảm bề mặt tiếp cận; API vẫn phải xác minh principal và quyền của hành động.

## 4. Tiêu chí quyết định API thuộc nhóm nào

Khi inventory một API, hãy xem xét các tiêu chí sau:

| Tiêu chí | Public API | Partner API | Internal API |
|---|---|---|---|
| Caller | Audience rộng, có thể chưa biết trước từng tổ chức. | Tổ chức/ứng dụng đối tác đã đăng ký. | Workload hoặc ứng dụng thuộc trust domain nội bộ. |
| Onboarding | Developer registration, self-service hoặc quy trình công khai. | Due diligence, hợp đồng, phê duyệt và cấu hình từng partner. | Quy trình cấp workload identity, service ownership và deployment. |
| Identity | User/client identity, OAuth, API key hoặc truy cập ẩn danh có giới hạn. | Partner/client identity riêng, có thể gắn tenant và môi trường. | Workload identity, mTLS, service token hoặc danh tính nền tảng. |
| Authorization | Scope/role, quyền user và quyền trên object. | Scope theo partner, tenant, chức năng, object và hợp đồng. | Service-to-service permission theo workload và operation. |
| Data | Dữ liệu đã xác định có thể cung cấp cho audience rộng. | Dữ liệu trao đổi theo mục đích/hợp đồng của partner. | Dữ liệu nội bộ theo nhiệm vụ và quyền của service. |
| Contract | Tài liệu, versioning và hỗ trợ cho developer bên ngoài. | Contract tích hợp, SLA, schema và lịch thay đổi với partner. | Contract giữa team/service, compatibility và release coordination. |
| Lifecycle | Developer support, quota, version deprecation công khai. | Onboarding, rotate/revoke credential, suspension và offboarding partner. | Service ownership, deployment lifecycle và thu hồi workload identity. |
| Monitoring | Abuse, scraping, enumeration, quota và traffic bất thường. | Traffic theo partner, credential, tenant và SLA. | East-west traffic, service identity, policy violation và lateral movement. |

Đừng phân loại chỉ dựa vào tên endpoint như `/public`, `/partner` hoặc `/internal`. Tên path là quy ước hữu ích nhưng không thay thế metadata, policy và kiểm soát thực thi.

## 5. Public API: thiết kế cho caller rộng và không mặc định tin cậy

Public API được thiết kế để một audience bên ngoài rộng có thể tìm hiểu và tích hợp. Caller có thể là ứng dụng do tổ chức khác phát triển, browser, mobile app, script tự động hoặc người dùng chưa đăng nhập. Vì không thể dựa vào một nhóm caller cố định, API cần contract rõ và kiểm soát lạm dụng từ đầu.

### Xác thực và phân quyền

- Quyết định rõ endpoint nào thực sự cho phép anonymous access. Nếu endpoint cần identity, yêu cầu xác thực ở server trên mọi request.
- Với user-facing API, xác minh access token/session và kiểm tra audience, scope, thời hạn cùng principal.
- Với public client như SPA/mobile, không nhúng client secret dùng chung vào binary hoặc source phân phối cho người dùng. Dùng flow phù hợp như Authorization Code với PKCE khi áp dụng.
- Với thao tác nhạy cảm, kiểm tra permission ở mức chức năng, object, thuộc tính và tenant. Không coi API key hoặc việc biết URL là quyền truy cập mọi dữ liệu.
- Trả dữ liệu tối thiểu, tránh lộ thông tin nội bộ qua error message, stack trace hoặc metadata.

### Chống lạm dụng

Public API cần quota và rate limit phù hợp theo principal, API key/client, IP hoặc tenant; không dựa duy nhất vào IP vì caller có thể dùng NAT, proxy hoặc nhiều địa chỉ. Giới hạn page size, filter complexity, upload, request body, concurrent request và các thao tác tốn tài nguyên. Có cơ chế phát hiện scraping, enumeration, credential stuffing và traffic bất thường.

### Contract và hỗ trợ developer

Công bố OpenAPI/SDK/changelog khi phù hợp, định nghĩa error semantics, pagination, idempotency, rate limit và quy tắc deprecation. Không đưa endpoint admin, debug hoặc dữ liệu nội bộ vào spec public chỉ vì chúng cùng nằm trên một host.

Public không có nghĩa là mọi dữ liệu đều công khai. Một API có thể public về audience nhưng chỉ trả dữ liệu của user đã đăng nhập theo quyền của họ.

## 6. Partner API: trust theo từng đối tác

Partner API phục vụ tổ chức đã được xác định, thường trao đổi dữ liệu hoặc thực hiện nghiệp vụ theo hợp đồng. Việc đối tác đã được onboarding không có nghĩa mọi request từ đối tác đều được phép.

### Định danh partner

- Cấp credential riêng cho từng partner, từng môi trường và khi cần từng integration/workload.
- Dùng OAuth client credentials, mTLS, private key JWT hoặc API key theo khả năng và mức bảo đảm cần thiết.
- Ràng buộc credential với client/partner ID, audience, scope, tenant và trạng thái hoạt động.
- Có thời hạn, rotation, revoke và quy trình xử lý key/certificate bị lộ.
- Không dùng một API key chung cho tất cả đối tác; nếu một partner bị xâm nhập, có thể thu hồi riêng mà không làm gián đoạn toàn bộ hệ sinh thái.

### Authorization và dữ liệu

Partner A chỉ được truy cập tài nguyên và thao tác đã thỏa thuận. Server cần kiểm tra partner identity, tenant mapping, function permission, object ownership/relationship và giới hạn nghiệp vụ. Không lấy `partnerId` hoặc `tenantId` trong request làm căn cứ duy nhất; phải ràng buộc với identity đã xác minh.

Chỉ chia sẻ field cần thiết cho mục đích tích hợp. Dùng schema/DTO riêng, phân loại dữ liệu, mã hóa phù hợp và audit các thao tác có tác động lớn. Cần xác định partner được đọc dữ liệu trong bao lâu, có được lưu bản sao hay chuyển tiếp cho bên thứ ba không.

### Onboarding và offboarding

Quy trình partner nên xác định owner nội bộ, pháp nhân/đối tác, use case, môi trường, endpoints, dữ liệu, scope, credential, IP/network requirements nếu có, SLA và contact xử lý sự cố. Khi chấm dứt tích hợp, thu hồi key/certificate/token, xóa hoặc vô hiệu hóa webhook, dừng job, gỡ allowlist và xử lý dữ liệu theo hợp đồng.

Partner API có thể Internet-facing hoặc đi qua private link. Kết nối riêng không loại bỏ nhu cầu xác thực và authorization theo partner.

## 7. Internal API: bảo vệ east-west traffic

Internal API được thiết kế cho service hoặc workload trong cùng tổ chức. Tuy nhiên, mạng nội bộ có thể bị xâm nhập qua một service yếu, credential bị lộ, cấu hình sai hoặc workload bị chiếm. Một khi attacker có chỗ đứng, các API nội bộ thiếu kiểm soát có thể cho phép lateral movement.

### Workload identity

- Xác định caller bằng workload identity, mTLS certificate hoặc token do hệ thống danh tính nội bộ cấp.
- Mỗi service có danh tính riêng; tránh một credential dùng chung cho toàn bộ cluster.
- Xác minh issuer, audience, scope và trạng thái credential ở service nhận.
- Giới hạn service nào được gọi operation nào; không mặc định mọi pod trong cùng subnet đều tin cậy.
- Khi service thay mặt user gọi downstream, truyền delegation context đã xác thực thay vì chỉ chuyển tiếp header tùy ý.

### Network và service boundary

Network policy, service mesh, firewall và private DNS có thể giới hạn đường kết nối. Nhưng authorization vẫn cần ở application/service boundary vì cùng một service có thể được gọi từ nhiều nguồn và có nhiều chức năng với mức nhạy cảm khác nhau.

Không để API nội bộ có quyền truy cập dữ liệu toàn cục chỉ vì nó không được expose ra Internet. Áp least privilege cho database, queue, object storage và secret manager; tách quyền đọc, ghi, admin và batch operation.

### Vận hành

Ghi nhận service owner, upstream/downstream dependency, contract version, SLO, timeout, retry, circuit breaker, quota và runbook. Khi deploy hoặc scale service, identity và policy phải được cập nhật tự động, có thể thu hồi khi workload biến mất.

## 8. So sánh các kiểm soát trọng yếu

| Kiểm soát | Public | Partner | Internal |
|---|---|---|---|
| Authentication | Theo endpoint; anonymous chỉ khi được chủ đích cho phép. | Luôn xác minh partner/client identity theo hợp đồng. | Xác minh workload/service identity. |
| Authorization | User, client, function, object, property và tenant. | Partner, tenant, function, object và data sharing scope. | Service, operation, resource và delegation context. |
| Credential | OAuth/session/API key; không đặt secret trong public client. | Credential riêng từng partner/integration, rotation và revoke. | Credential ngắn hạn/workload identity; hạn chế shared secret. |
| Network | Internet edge, WAF/gateway và egress policy. | Internet hoặc private link; allowlist chỉ là lớp bổ sung. | Private network/service mesh và east-west policy. |
| Rate/resource limits | Quota và chống abuse theo caller/tenant. | Quota theo partner và SLA. | Concurrency, budget và quota theo service/operation. |
| Data protection | Tối thiểu hóa response, privacy và public disclosure policy. | Purpose limitation, tenant isolation và hợp đồng dữ liệu. | Phân loại dữ liệu, least privilege và service boundary. |
| Change management | Versioning, changelog và deprecation công khai. | Thông báo, migration window và kiểm thử với partner. | Contract tests và phối hợp release giữa team. |
| Monitoring | Abuse, scraping, enumeration và availability. | Partner-specific traffic, SLA và credential misuse. | East-west anomalies, lateral movement và policy violations. |

Đây là baseline để bắt đầu thiết kế. Endpoint có dữ liệu nhạy cảm hoặc tác động tài chính cần kiểm soát bổ sung bất kể thuộc nhóm nào.

## 9. Một API có thể có nhiều nhóm caller không?

Có thể, nhưng cần tránh để một endpoint có policy mơ hồ. Nếu cùng một API phục vụ public developer, partner và service nội bộ, hãy phân biệt caller bằng identity đã xác minh và áp policy theo từng principal. Cân nhắc tách audience, hostname, route hoặc API product khi các nhóm có contract, dữ liệu, SLA hay yêu cầu bảo mật khác nhau.

Ví dụ, `POST /v1/orders` có thể được gọi bởi:

- Mobile app của customer để tạo đơn của chính user.
- Partner logistics để cập nhật trạng thái giao hàng của đơn đã được phân công.
- `checkout-service` nội bộ để khởi tạo đơn sau khi hoàn tất quy trình checkout.

Ba caller này không nên được cấp chung một role `API_USER`. Customer có quyền tạo đơn trong phạm vi user; logistics chỉ cập nhật một số trường/trạng thái trong đơn được giao; checkout service có quyền tạo đơn theo contract nội bộ. Server cần xác minh identity, function permission, object relationship, field allowlist và tenant cho từng loại caller.

Nếu policy quá phức tạp để phân biệt an toàn trong cùng endpoint, tách endpoint/API product hoặc service boundary. Tách route giúp rõ contract nhưng vẫn cần authorization ở server.

## 10. Mẫu inventory cho một API

Một bản ghi inventory có thể dùng các trường sau:

| Trường | Nội dung cần ghi |
|---|---|
| API ID/name | Tên duy nhất và mô tả nghiệp vụ. |
| Classification | Public, partner hoặc internal; có thể ghi nhiều audience nếu có lý do. |
| Network exposure | Internet, private, VPN/private link, service mesh hoặc local. |
| Owner | Team chịu trách nhiệm và contact vận hành. |
| Consumers | Ứng dụng, partner, service hoặc nhóm developer sử dụng. |
| Entry points | Hostname, path, method, protocol và version. |
| Identity model | Anonymous, user session, OAuth client, mTLS workload, API key. |
| Authorization model | Role/scope, object, tenant, property và policy owner. |
| Data classification | Loại dữ liệu vào/ra, mức nhạy cảm và retention. |
| Dependencies | Database, queue, storage, downstream API và provider. |
| Limits | Rate limit, quota, body/page size, timeout và concurrency. |
| Contract | OpenAPI/schema version, changelog và compatibility policy. |
| Lifecycle | Active, deprecated, planned retirement và ngày review. |
| Security controls | TLS, WAF/gateway, mTLS, egress, audit, encryption và secret handling. |
| Monitoring | Metrics, alert, SLO, abuse detection và incident runbook. |

Ví dụ một record rút gọn:

```yaml
api_id: logistics-shipment-status-v1
classification: partner
network_exposure: internet-facing
owner: fulfillment-platform
consumers:
  - partner: carrier-a
identity:
  type: oauth-client-credentials
  audience: logistics-api
  partner_binding: required
authorization:
  scopes:
    - shipment:status:update
  object_scope: assigned-shipments-only
data:
  classification: confidential-business
limits:
  requests_per_minute_per_partner: 300
lifecycle:
  state: active
  contract_version: v1
```

Đây là ví dụ minh họa, không phải schema chuẩn. Không đưa secret thật vào inventory; chỉ ghi secret reference hoặc key identifier không nhạy cảm. Các giới hạn cần dựa trên năng lực dịch vụ và thỏa thuận với caller.

## 11. Quy trình phân loại API mới

Khi tạo hoặc phát hiện một API mới, thực hiện các bước:

1. **Xác định use case:** API giải quyết nghiệp vụ gì và dữ liệu nào đi qua?
2. **Xác định audience:** developer/customer rộng, đối tác được phê duyệt hay workload nội bộ?
3. **Xác định trust relationship:** ai cấp identity, ai quản lý caller, credential được cấp/thu hồi ra sao?
4. **Xác định network exposure:** endpoint được route qua Internet, private network, VPN, private link hay service mesh?
5. **Chọn authorization model:** permission chức năng, object/tenant relationship, property và điều kiện nghiệp vụ.
6. **Đánh giá dữ liệu và tác động:** dữ liệu cá nhân, tài chính, nội bộ; thao tác đọc/ghi, export, admin và side effect.
7. **Chọn kiểm soát vận hành:** quota, timeout, retry, versioning, SLA, monitoring và incident response.
8. **Ghi inventory và owner:** cập nhật contract, consumer, dependency, trạng thái và ngày review.
9. **Kiểm thử:** xác minh đúng caller được phép, caller sai bị từ chối, network path và resource limits hoạt động.
10. **Rà soát định kỳ:** kiểm tra audience, consumer còn tồn tại, credential, scope, exposure và deprecation.

## 12. Các anti-pattern cần tránh

| Anti-pattern | Rủi ro | Cách xử lý |
|---|---|---|
| Gọi API là internal vì hostname không công khai | Workload bị xâm nhập có thể gọi ngang và lạm quyền. | Dùng workload identity và authorization từng operation. |
| Gọi API là public nghĩa là anonymous | Có thể bỏ xác thực cho dữ liệu riêng tư hoặc thao tác nhạy cảm. | Xác định anonymous access riêng theo endpoint. |
| Dùng chung một API key cho tất cả partner | Không thể cô lập hoặc thu hồi từng đối tác. | Credential riêng, scope và quota riêng. |
| Partner ID lấy từ body quyết định quyền | Caller có thể giả mạo partner/tenant. | Ràng buộc partner từ identity đã xác minh và policy. |
| VPN/IP allowlist là kiểm soát duy nhất | Caller bên trong đường mạng vẫn có thể sai quyền hoặc bị chiếm. | Kết hợp authentication, authorization và network controls. |
| Mọi service dùng một service account | Một service bị chiếm có thể giả mạo nhiều workload. | Danh tính riêng và least privilege. |
| Dùng chung endpoint cho mọi audience mà không phân policy | Quyền và dữ liệu bị trộn lẫn. | Policy theo principal hoặc tách API product/route/service. |
| Inventory chỉ ghi URL | Không biết owner, dữ liệu, caller, quyền và lifecycle. | Dùng inventory đầy đủ và có người chịu trách nhiệm. |
| Không thu hồi credential khi partner/service ngừng dùng | Credential cũ tiếp tục là đường truy cập. | Offboarding, revoke và review định kỳ. |

## 13. Kiểm thử phân loại và kiểm soát truy cập

Kiểm thử nên chứng minh rằng phân loại trong inventory khớp với hành vi thật của endpoint. Với mỗi API, tạo ma trận caller gồm anonymous, customer/user, partner A, partner B, service nội bộ đúng quyền và service nội bộ sai quyền.

| Ca kiểm thử | Thao tác | Kết quả mong đợi |
|---|---|---|
| Public endpoint cần đăng nhập | Gọi không token, sau đó gọi bằng user hợp lệ. | Request đầu bị từ chối; request sau chỉ được thao tác trong quyền user. |
| Anonymous endpoint | Gọi chức năng được công bố công khai. | Chỉ trả dữ liệu/operation đã được duyệt; có quota và abuse controls. |
| Partner isolation | Partner A thay ID/tenant để truy cập dữ liệu của B. | Bị từ chối; không rò dữ liệu chéo partner. |
| Partner credential revoke | Thu hồi credential của A rồi gọi lại. | Credential cũ không còn được chấp nhận trong SLA thu hồi. |
| Internal workload identity | Service không có identity hoặc dùng token sai audience gọi API. | Bị từ chối. |
| Internal least privilege | Service hợp lệ gọi operation ngoài scope. | Bị từ chối ở function/resource policy. |
| Network exposure | Thử truy cập internal API từ network không được phép. | Network control chặn; nếu đến được ứng dụng thì identity/policy vẫn từ chối. |
| Multi-audience endpoint | Gọi cùng route bằng từng loại principal. | Mỗi principal chỉ có quyền và field theo policy tương ứng. |
| Rate/resource limits | Tạo traffic vượt quota theo user/partner/service. | Bị giới hạn và phát metric/alert phù hợp. |
| Inventory drift | Thêm route hoặc consumer mới mà chưa có owner/classification. | CI/review hoặc discovery workflow phát hiện và yêu cầu cập nhật inventory. |

Ngoài status code, kiểm tra response body, dữ liệu trả về, database changes, event, file, outbound request và audit event. Một request bị trả `403` nhưng đã tạo side effect trước đó vẫn là lỗi bảo mật.

## 14. Giám sát và quản trị vòng đời

Inventory chỉ hữu ích khi được cập nhật cùng thay đổi thực tế. Nên kết hợp dữ liệu khai báo (spec, gateway config, service registry, IaC) với discovery từ traffic, DNS, load balancer, service mesh và log triển khai. Discovery tự động giúp tìm endpoint bị bỏ quên, nhưng cần owner xác nhận trước khi thay đổi policy.

Theo dõi các tín hiệu:

- Public API: traffic bất thường, enumeration, scraping, credential stuffing, quota exhaustion và endpoint không còn trong contract.
- Partner API: credential dùng từ nguồn lạ, partner gọi sai scope, tăng lỗi, vượt SLA hoặc gọi tenant khác.
- Internal API: workload lạ, service-to-service call mới, privilege escalation, lateral movement và truy cập từ namespace không mong đợi.
- Tất cả nhóm: endpoint mới không có owner, API version cũ, TLS/certificate sắp hết hạn, secret chưa rotate và route không còn consumer.

Mỗi API cần owner, review date và quy trình decommission. Khi ngừng API, thông báo consumer, dừng traffic, thu hồi credential, gỡ route/network policy, xóa secret/config không còn dùng và lưu audit evidence theo chính sách.

## 15. Checklist phân biệt public, partner và internal API

- [ ] Audience chính và use case của API được ghi rõ?
- [ ] Classification dựa trên caller/trust relationship, không chỉ hostname hoặc vị trí mạng?
- [ ] Network exposure được ghi riêng: Internet, private, VPN/private link hay service mesh?
- [ ] Endpoint nào anonymous và endpoint nào yêu cầu authentication được xác định rõ?
- [ ] Identity của user, partner hoặc workload được xác minh bằng nguồn tin cậy?
- [ ] Authorization kiểm tra function, object, property và tenant theo từng request?
- [ ] Credential riêng theo user/client/partner/workload, có scope, rotation và revoke?
- [ ] Network policy bổ sung cho application authorization thay vì thay thế nó?
- [ ] Data classification, response fields, retention và sharing purpose được xác định?
- [ ] Quota, timeout, retry, concurrency và abuse detection phù hợp audience?
- [ ] Contract, versioning, deprecation và owner được ghi trong inventory?
- [ ] Có test cho caller đúng/sai, cross-tenant, credential revoked và network path?
- [ ] Có monitoring, audit, review date và quy trình decommission?

Public, partner và internal API khác nhau chủ yếu ở audience và quan hệ tin cậy. Network exposure là một trục riêng; authentication và authorization vẫn cần được thực thi ở từng endpoint. Khi inventory ghi rõ caller, identity, quyền, dữ liệu, network path, contract và owner, tổ chức có thể chọn kiểm soát phù hợp, giới hạn tác động khi credential bị lộ và phát hiện sớm API đang bị sử dụng ngoài mục đích thiết kế.
