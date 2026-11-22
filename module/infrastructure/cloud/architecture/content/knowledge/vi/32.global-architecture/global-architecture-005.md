# Quản lý phiên, danh tính và trải nghiệm khi chuyển khu vực

> **Chương:** Kiến trúc toàn cầu  
> **Phạm vi:** Thiết kế kiến trúc ứng dụng trên đám mây từ yêu cầu nghiệp vụ đến lựa chọn mạng, compute, dữ liệu và mô hình triển khai. Bài học tập trung vào quản lý session, xác thực danh tính và giữ trải nghiệm người dùng liên tục khi traffic chuyển giữa các region; đồng thời đánh giá routing, data residency, consistency, security, availability, latency, chi phí và vận hành theo tư duy Well-Architected.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt global traffic steering, regional failover, session affinity và session continuity.
2. Chọn mô hình session stateless, centralized store, regional store hoặc replicated session phù hợp với yêu cầu trải nghiệm và consistency.
3. Thiết kế authentication, token validation, refresh, revocation và workload identity khi request được phục vụ ở region khác.
4. Phân tích tác động của DNS/Anycast/Global Load Balancer, health check, geo-routing, latency routing và failover tới session.
5. Xác định dữ liệu nào được phép di chuyển qua biên giới, dữ liệu nào cần lưu tại region và cách xử lý residency.
6. Thiết kế failover/failback, conflict resolution, cache, idempotency và trải nghiệm degraded mode mà không tạo lỗi bảo mật hoặc giao dịch.
7. Kiểm thử hành trình người dùng khi đổi region, mất region, mất identity provider hoặc replication lag.

## 1. Tại sao chuyển khu vực có thể làm mất phiên?

Một ứng dụng toàn cầu có thể phục vụ người dùng từ nhiều region để giảm latency, tăng resilience hoặc đáp ứng yêu cầu lưu trú dữ liệu. Global traffic manager có thể chuyển request từ region A sang region B khi A gặp sự cố, hoặc định tuyến người dùng đến region gần nhất.

Tuy nhiên, session của người dùng không chỉ là một cookie trên trình duyệt. Trạng thái có thể nằm ở:
- Memory của một application instance.
- Session store dùng chung.
- Database theo region.
- Cache phân tán.
- Identity provider hoặc token service.
- Client-side token và refresh token.
- Shopping cart, workflow state hoặc transaction state.
- Device/session registry, risk context và revocation list.

Nếu request đầu tiên được phục vụ ở region A nhưng request tiếp theo chuyển sang B, region B phải có đủ thông tin để xác minh danh tính và tiếp tục hành trình hợp lệ. Nếu state chỉ nằm trong memory hoặc database riêng ở A, người dùng có thể bị logout, mất giỏ hàng, bị tạo phiên trùng hoặc nhìn thấy dữ liệu cũ.

**Session continuity** là khả năng giữ trạng thái và quyền truy cập hợp lệ xuyên qua thay đổi instance, zone hoặc region trong giới hạn chính sách. Mục tiêu không phải giữ session bằng mọi giá. Khi token bị thu hồi, thiết bị có rủi ro hoặc giao dịch không xác định, hệ thống phải yêu cầu xác thực lại hoặc đưa trạng thái về pending an toàn.

### 1.1. Phân biệt các khái niệm

| Khái niệm | Ý nghĩa | Câu hỏi chính |
| --- | --- | --- |
| Global traffic steering | Chọn region/endpoint phục vụ request | User đi tới region nào? |
| Session affinity/stickiness | Giữ user hoặc connection ở một backend/region | Có cần ở cùng nơi trong một thời gian? |
| Session continuity | Giữ trạng thái và quyền truy cập qua thay đổi backend/region | Request mới có tiếp tục đúng phiên? |
| Identity federation | Tin cậy danh tính do một IdP hoặc issuer cấp | Region khác xác minh token ra sao? |
| Regional failover | Chuyển traffic khỏi region lỗi | State nào đã sẵn sàng ở nơi nhận? |
| Failback | Chuyển hoạt động về region ưu tiên | Dữ liệu và session có đồng bộ đủ an toàn? |

Traffic routing có thể thành công trong vài giây nhưng session continuity vẫn thất bại nếu session store, key, token signing configuration hoặc user data không sẵn sàng.

## 2. Xác định hành trình người dùng và yêu cầu toàn cầu

Bắt đầu từ journey, không bắt đầu từ DNS. Mỗi loại người dùng và giao dịch có yêu cầu khác nhau.

Ví dụ một nền tảng đặt chỗ:
1. Người dùng mở trang và nhận catalog.
2. Đăng nhập qua identity provider.
3. Tìm dịch vụ và tạo giỏ hàng.
4. Giữ chỗ và bắt đầu thanh toán.
5. Nhận kết quả booking.
6. Mở ứng dụng từ region khác hoặc sau khi region đang phục vụ gặp sự cố.

Các câu hỏi cần trả lời:
- Người dùng có thể di chuyển giữa quốc gia/region trong cùng một phiên không?
- Region nào là home region của tài khoản hoặc tenant?
- Dữ liệu session có chứa PII, payment context hoặc dữ liệu bị giới hạn residency không?
- Một phiên được phép sống bao lâu? Khi nào cần step-up authentication?
- Một giao dịch đang chạy có thể tiếp tục ở region khác hay cần tra cứu/reconcile?
- Nếu identity provider không sẵn sàng, phiên hiện tại được xử lý thế nào?
- Người dùng cần thấy trạng thái rõ ràng hay có thể nhận thông báo trễ?

### 2.1. Phân loại trạng thái theo khả năng chuyển region

| Trạng thái | Ví dụ | Hành vi khi chuyển region |
| --- | --- | --- |
| Public/read-only | Catalog, nội dung công khai | Có thể cache/replicate rộng theo policy |
| Identity proof | Access token, session ID | Xác minh chữ ký, issuer, audience, expiry và policy |
| User preference | Ngôn ngữ, theme | Có thể replicate/cache nếu cho phép |
| Ephemeral session | CSRF nonce, short-lived workflow state | Cần TTL, secure replication hoặc yêu cầu tạo lại |
| Shopping cart | Items, quantities, promotion | Cần versioning, consistency và conflict handling |
| Transaction state | Booking/payment/reservation | Theo source of truth; không suy đoán từ cache |
| Sensitive/regional data | PII, financial, regulated data | Chỉ di chuyển theo residency và transfer policy |
| Risk/revocation state | Device risk, revoked session/token | Cần propagation nhanh và fail-safe policy |

Không phải mọi trạng thái nên replicate. Một số state có thể tái tạo từ dữ liệu bền vững; một số chỉ nên giữ tại home region; một số có thể mất mà không ảnh hưởng tính đúng đắn.

## 3. Global traffic steering và regional routing

### 3.1. Các cách định tuyến phổ biến

| Cơ chế | Cách hoạt động | Phù hợp | Giới hạn cần biết |
| --- | --- | --- | --- |
| DNS geolocation routing | Trả endpoint theo vị trí resolver/client ước lượng | Route theo quốc gia/vùng | DNS cache và resolver location không luôn phản ánh user thật |
| DNS latency-based routing | Chọn endpoint có latency đo được thấp hơn | Tối ưu trải nghiệm truy cập | Health, DNS TTL và dữ liệu đo có thể trễ |
| Anycast | Nhiều location quảng bá cùng IP; mạng đưa traffic tới điểm phù hợp | Edge, DDoS, global ingress | Không đồng nghĩa session state tự đồng bộ |
| Global HTTP load balancer | Routing theo host/path, health, region và policy | HTTP(S), failover có health awareness | Cần giới hạn timeout, health check và policy |
| Geo/tenant home-region routing | Chọn region theo tài khoản, tenant hoặc data residency | Dữ liệu có home region | User ở xa có thể chịu latency cao |
| Client-side region selection | Client nhận danh sách endpoint và chọn theo policy | Một số app/mobile | Cache DNS, app version và logic client khó đồng nhất |

Có thể kết hợp global load balancer ở edge với regional ingress nội bộ. DNS failover dễ triển khai nhưng không phải lúc nào cũng đủ nhanh do TTL và cache; global load balancer có thể điều phối request tốt hơn nhưng vẫn cần health signal và state readiness.

### 3.2. Routing policy không chỉ dựa vào địa lý

Một quyết định route có thể xét:
- Region health và capacity.
- User latency và network quality.
- Tenant home region/data residency.
- Feature availability ở region.
- Version compatibility.
- Maintenance window.
- Region đang phục hồi sau incident.
- Security/risk policy.

Nếu tài khoản thuộc tenant có dữ liệu chỉ được xử lý trong một khu vực, không tự động route dữ liệu sang region khác chỉ vì region đó có latency thấp hơn.

### 3.3. Ví dụ kiến trúc global ingress

~~~mermaid
flowchart TB
    U["Global users"] --> G["Global DNS / Anycast / HTTP load balancer"]
    G --> R1["Regional ingress A"]
    G --> R2["Regional ingress B"]
    G --> R3["Regional ingress C"]
    subgraph A["Region A"]
      R1 --> AAPI["Application/API"]
      AAPI --> ADB[("Regional data A")]
    end
    subgraph B["Region B"]
      R2 --> BAPI["Application/API"]
      BAPI --> BDB[("Regional data B")]
    end
    subgraph C["Region C"]
      R3 --> CAPI["Application/API"]
      CAPI --> CDB[("Regional data C")]
    end
    IDP["Federated identity provider"] --> AAPI
    IDP --> BAPI
    IDP --> CAPI
~~~

Sơ đồ mang tính khái niệm. Tùy mô hình data ownership, một số region có thể là active-active cho stateless API nhưng dùng home-region data access; không mặc định mỗi region có một bản database ghi độc lập.

## 4. Thiết kế mô hình session

### 4.1. Stateless session bằng token

Với token tự chứa (ví dụ signed access token), service có thể xác minh token bằng public key/JWKS mà không cần truy vấn session store trên mỗi request.

Thành phần thường có:
- Subject/user ID.
- Issuer (iss).
- Audience (aud).
- Expiry (exp) và issued-at (iat).
- Scope/role/claims cần thiết.
- Token ID (jti) nếu phục vụ revocation/deduplication.
- Tenant hoặc context đã được issuer xác nhận.

Ưu điểm:
- Dễ phục vụ request ở nhiều region.
- Giảm phụ thuộc vào session database trung tâm.
- Có thể xác minh local nếu key và issuer metadata được cache an toàn.
- Hợp với API stateless và service-to-service.

Đánh đổi:
- Token bị lộ có thể dùng tới khi hết hạn nếu không có revocation mechanism.
- Claim có thể stale khi role/tenant membership thay đổi.
- Token lớn làm tăng header/network overhead.
- Rotation signing key và JWKS cache phải đồng bộ.
- Không nên nhét toàn bộ profile, permission và business state vào token.

### 4.2. Stateful session store

Session ID ngẫu nhiên được lưu server-side; cookie chỉ giữ ID có tính bí mật. Server tra cứu session để biết user, expiry, state và revocation.

Ưu điểm:
- Thu hồi và cập nhật session tập trung.
- Có thể giữ workflow state và thiết bị.
- Token/cookie phía client nhỏ hơn.
- Dễ buộc logout toàn bộ phiên khi cần.

Đánh đổi:
- Session store trở thành dependency runtime.
- Cross-region read/write có latency và replication complexity.
- Store outage có thể ảnh hưởng đăng nhập hoặc mọi request.
- Cần thiết kế partition, replication, expiry, failover và backup.

### 4.3. Hybrid session

Một mô hình phổ biến kết hợp access token ngắn hạn và refresh/session record server-side:
- Access token sống ngắn, xác minh local ở regional API.
- Refresh token được bảo vệ và gắn với session record.
- Refresh/rotation kiểm tra trạng thái session, device và revocation.
- Khi chuyển region, API có thể tiếp tục xác minh access token; việc refresh phụ thuộc home region hoặc session service đã được thiết kế cho HA.

Hybrid giảm truy vấn state trên mọi request nhưng vẫn giữ điểm kiểm soát cho refresh/revocation.

### 4.4. So sánh mô hình

| Tiêu chí | Stateless token | Centralized stateful | Hybrid/regional state |
| --- | --- | --- | --- |
| Cross-region request | Thường đơn giản nếu key/claim hợp lệ | Phụ thuộc session store reachability | Tùy access token và refresh policy |
| Revocation nhanh | Cần denylist/introspection/short TTL | Có thể cập nhật store trực tiếp | Có thể kiểm soát refresh và token TTL |
| Latency | Xác minh local | Có thể thêm network hop | Thấp cho access, stateful cho refresh |
| Consistency | Claim có thể stale tới expiry | Cần replication consistency | Cần định nghĩa theo từng state |
| Availability dependency | Issuer/key metadata và clock | Session store | Cả local verify và regional state |
| Operational complexity | Key lifecycle/JWKS/revocation | Store replication/failover | Kết hợp hai nhóm kiểm soát |

Không có mô hình tốt nhất cho mọi ứng dụng. Chọn theo yêu cầu revocation, session lifetime, dữ liệu được lưu, số region, RTO/RPO và latency objective.

## 5. Cookie, session ID và bảo vệ trình duyệt

Với web session:
- Dùng cookie Secure để chỉ gửi qua HTTPS.
- Dùng HttpOnly để giảm khả năng JavaScript đọc cookie.
- Chọn SameSite phù hợp luồng cross-site và CSRF protection.
- Dùng domain/path hẹp nhất có thể.
- Session ID phải đủ entropy, không chứa PII hoặc business data.
- Xoay session ID sau login, privilege elevation hoặc thay đổi danh tính.
- Có idle timeout và absolute lifetime.
- Thu hồi session khi logout, password reset hoặc incident theo policy.
- Không lưu refresh token dài hạn trong nơi dễ bị script truy cập.
- Bảo vệ chống CSRF nếu cookie được browser tự động gửi.

Cookie domain rộng để dùng chung giữa subdomain có thể tăng blast radius. Đặt cùng cookie cho mọi vùng/ứng dụng mà không phân tích trust boundary có thể cho phép một subdomain yếu ảnh hưởng session chính.

### 5.1. Session fixation và token theft

- **Session fixation:** attacker khiến nạn nhân sử dụng session ID do attacker biết; rotate ID sau authentication.
- **Token theft:** token bị lấy từ browser, log, malware hoặc network; dùng TLS, HttpOnly cookie nếu phù hợp, short TTL, audience/scope hẹp và revocation.
- **Replay:** token/cookie bị dùng lại; có thể áp dụng token binding/sender-constrained token nếu hệ sinh thái hỗ trợ, device/risk controls và rotation.
- **CSRF:** browser gửi credential tự động trong request cross-site; dùng SameSite, CSRF token và origin validation phù hợp.

Chuyển region không được làm yếu các kiểm soát cookie, CSRF hoặc token validation.

## 6. Identity federation và xác minh token trên nhiều region

### 6.1. Issuer và audience

Các region có thể dùng cùng một identity provider hoặc federation trust. Regional API phải xác minh:
- Issuer được phép.
- Signature hợp lệ với key tương ứng.
- Audience đúng service/resource.
- Expiry và not-before hợp lệ.
- Algorithm được policy chấp nhận.
- Scope/role/tenant claim phù hợp.
- Clock skew nằm trong giới hạn cấu hình.
- Token không bị revoke nếu luồng yêu cầu kiểm tra revocation.

Không chỉ kiểm tra token "decode được". JWT có thể giải mã payload mà không xác minh chữ ký; không được tin claim trước khi xác minh đầy đủ.

### 6.2. JWKS và signing key rotation

Nếu dùng public-key token signing:
1. Issuer công bố public key trong JWKS.
2. API region cache JWKS theo TTL và xử lý key ID (kid).
3. Khi rotation, issuer publish key mới trước khi bắt đầu ký bằng key đó.
4. API lấy được key mới theo refresh policy.
5. Key cũ được giữ đủ thời gian để xác minh token còn hiệu lực.
6. Key compromised cần quy trình khẩn cấp để revoke, invalidate cache và yêu cầu re-authentication khi cần.

Nếu region B chưa có key mới do cache/egress outage, token hợp lệ từ issuer có thể bị từ chối. Nếu region tiếp tục chấp nhận key bị compromise quá lâu, bảo mật bị giảm. Cần kiểm thử cả normal rotation lẫn emergency revocation.

### 6.3. Identity provider outage

Phải phân biệt:
- Request có access token hiện tại còn hợp lệ và có thể xác minh local.
- Request cần refresh token.
- Request cần login/step-up.
- Quyết định authorization cần dữ liệu membership/role vừa thay đổi.
- Session hoặc credential đã bị revoke.
- Workload cần lấy token mới để gọi dependency.

Có thể cho phép token hiện hành tới expiry trong một số luồng đọc ít rủi ro nếu policy cho phép; thao tác nhạy cảm có thể fail closed hoặc yêu cầu xác thực lại. Không tự kéo dài expiry hoặc bỏ qua revocation chỉ để giữ availability.

## 7. Session continuity khi chuyển region

### 7.1. Luồng chuyển vùng

~~~mermaid
sequenceDiagram
    participant C as Client
    participant G as Global router
    participant A as Region A
    participant B as Region B
    participant I as Identity/JWKS
    participant S as Session service
    C->>G: Request + session cookie/token
    G->>A: Route tới region A
    A->>I: Verify issuer/key (cache hoặc fetch)
    A->>S: Read session/risk state nếu cần
    A-->>C: Response + session context
    Note over A: Region A unhealthy
    C->>G: Request tiếp theo
    G->>B: Route tới region B
    B->>I: Verify token và policy
    B->>S: Resolve session ở home/regional store
    S-->>B: Session state/version hoặc safe failure
    B-->>C: Tiếp tục, re-auth hoặc trạng thái pending phù hợp
~~~

Trong thực tế global router có thể chuyển request ngay cả khi client vẫn giữ connection/cookie. Regional B cần kiểm tra session ID/token, session version, user status và data access policy của vùng.

### 7.2. Session migration hay session reconstruction?

Có hai cách:

- **Migration/replication:** sao chép state sang region khác. Hữu ích cho session cần giữ nguyên nhưng làm tăng độ phức tạp consistency, encryption, residency và revocation.
- **Reconstruction:** chỉ giữ session identifier/identity proof, rồi tải lại state bền vững từ source of truth ở home region hoặc tạo lại state ephemeral. Cách này giảm dữ liệu cần replicate nhưng có thể tăng latency hoặc yêu cầu người dùng thao tác lại.

Không nhất thiết sao chép toàn bộ session object. Có thể chỉ replicate metadata cần thiết như session version, revocation status và routing/home-region pointer.

## 8. Regional session store và data consistency

### 8.1. Đặt session ở đâu?

| Mô hình | Cách hoạt động | Ưu điểm | Rủi ro |
| --- | --- | --- | --- |
| Home-region store | Session thuộc một region/tenant gốc | Dễ giữ authority và residency | Region khác cần cross-region call |
| Global centralized store | Mọi region đọc/ghi store logic chung | State nhất quán theo một điểm quản lý | Latency, regional dependency và blast radius |
| Active-passive replicated store | Một region ghi, region khác nhận replication | Failover có thể đơn giản hơn active-active | Replication lag và write fencing |
| Active-active store | Nhiều region cùng ghi | Có thể phục vụ gần user | Conflict, consistency và split-brain |
| Local ephemeral + durable source | Cache/session ngắn hạn tại region; state chuẩn ở durable store | Giảm latency và dữ liệu replicate | Cache invalidation và stale state |

### 8.2. Chia state theo consistency requirement

Không phải mọi field cần cùng mức nhất quán:

| State | Consistency phù hợp | Lý do |
| --- | --- | --- |
| Theme/language preference | Eventual consistency thường chấp nhận được | Xung đột ít ảnh hưởng giao dịch |
| Catalog cache | Eventual + bounded staleness | Có thể chấp nhận dữ liệu cũ trong giới hạn |
| Active session/revocation | Strong hoặc propagation nhanh theo risk | Tránh tiếp tục phiên đã thu hồi |
| Cart quantity | Versioned update/optimistic concurrency | Tránh ghi đè thay đổi giữa thiết bị |
| Inventory reservation | Strong transactional control theo business rule | Tránh oversell |
| Payment status | Source of truth và reconciliation | Không suy ra kết quả từ cache |
| Device risk/step-up requirement | Policy-defined freshness | Bảo vệ thao tác nhạy cảm |

### 8.3. Conflict resolution

Nếu user mở hai thiết bị hoặc hai region cùng thay đổi cart:
- Dùng version/ETag/optimistic concurrency.
- Ghi actor/device/time và operation ID.
- Merge field độc lập nếu semantics cho phép.
- Dùng last-write-wins chỉ với dữ liệu mà overwrite không gây hậu quả.
- Với giao dịch, dùng transaction/source of truth thay vì merge tùy tiện.
- Hiển thị conflict hoặc yêu cầu user xác nhận khi không thể merge an toàn.

Không sử dụng timestamp đơn lẻ nếu clock giữa region không đáng tin hoặc hai update có cùng thời điểm. Có thể dùng version tăng đơn điệu, sequence hoặc causal metadata phù hợp.

## 9. Data residency và quyền riêng tư khi chuyển region

Kiến trúc toàn cầu phải xác định dữ liệu nào được lưu, xử lý và truyền ở đâu. Việc user đăng nhập từ một quốc gia khác không tự động cho phép chuyển toàn bộ dữ liệu tài khoản sang region gần nhất.

Phân loại:
- **Identity data:** subject ID, email, phone, credential metadata.
- **Session metadata:** session ID hash, expiry, device context, IP/risk data.
- **Business data:** booking, payment, profile, cart.
- **Security telemetry:** login event, audit, fraud/risk signals.
- **Secrets/cryptographic material:** refresh token, signing key, encryption key.

Các câu hỏi architecture:
- Có yêu cầu data residency hoặc transfer mechanism không?
- Có thể chỉ xử lý token opaque hoặc identifier thay vì copy PII không?
- Log chứa IP, user ID hoặc device fingerprint lưu tại đâu?
- Backup và disaster recovery có cùng residency constraint?
- Provider/processor nào được truy cập data?
- Key management và access log có bị chuyển vùng?
- Retention/deletion có đồng bộ qua replica/cache/backup không?

Có thể dùng home-region routing: identity/data của tenant ở region được chỉ định; user ở nước khác vẫn kết nối global edge, nhưng request được proxy tới home region. Cách này giữ data locality nhưng có latency và dependency cross-region. Yêu cầu pháp lý cụ thể cần được Privacy/Legal xác nhận; không suy diễn từ kiến trúc kỹ thuật.

## 10. Trải nghiệm người dùng khi region lỗi hoặc chuyển vùng

Session continuity tốt cần phản hồi rõ, nhất quán và không làm mất dữ liệu quan trọng.

### 10.1. Các trạng thái người dùng có thể gặp

| Tình huống | Trải nghiệm nên có |
| --- | --- |
| Chuyển region trong nền, access token còn hợp lệ | Request tiếp tục mà không yêu cầu login lại |
| Session state chưa có ở region mới | Tải từ home region hoặc giải thích cần xác minh lại |
| Access token hết hạn nhưng IdP hoạt động | Refresh hoặc đăng nhập lại theo policy |
| IdP tạm unavailable, token còn hợp lệ | Cho phép hoạt động trong giới hạn được phê duyệt |
| Refresh token bị revoke | Yêu cầu đăng nhập lại; không tái sử dụng phiên |
| Booking/payment chưa rõ kết quả | Hiển thị pending/processing và cho phép tra cứu |
| Giỏ hàng có conflict | Thông báo thay đổi và cho user chọn/merge |
| Home region không khả dụng | Dùng DR theo policy hoặc thông báo tạm thời chưa thể xử lý |
| Residency không cho phép xử lý ở region hiện tại | Route về home region hoặc từ chối rõ ràng |

### 10.2. Tránh logout hàng loạt khi failover

Các nguyên nhân khiến người dùng bị logout:
- Session store chỉ tồn tại ở region A.
- Encryption/signing key khác nhau giữa region.
- Cookie domain/path hoặc secret khác nhau theo region.
- Session version không được replicate.
- Clock skew làm token bị xem là expired/not-yet-valid.
- Regional API dùng issuer/audience configuration khác.
- Revocation cache không đồng bộ.
- User được chuyển sang home region sai do geo-routing.

Chuẩn hóa key management, token issuer/audience policy, cookie settings, clock synchronization và session version semantics giúp giảm lỗi. Không chia sẻ private signing key ở mọi region chỉ để giải quyết session; cân nhắc public-key verification và tách key theo purpose.

### 10.3. Màn hình và thông điệp lỗi

Thông điệp cần:
- Không để lộ internal region, host, session ID hoặc chi tiết security.
- Phân biệt yêu cầu đăng nhập lại, giao dịch đang xử lý và lỗi tạm thời.
- Không khuyến khích user nhấn thanh toán nhiều lần nếu kết quả chưa rõ.
- Có retry guidance với backoff khi phù hợp.
- Giữ correlation/reference để support có thể tra cứu.
- Giải thích dữ liệu nào đã được lưu và hành động nào cần làm lại.

## 11. Failover và failback có kiểm soát

### 11.1. Failover không chỉ là đổi DNS

Một quy trình failover gồm:
1. Xác định region unhealthy bằng health signal và business SLI.
2. Phân loại lỗi: ingress, compute, identity, session store, database hay external dependency.
3. Kiểm tra region nhận có capacity và dependency cần thiết.
4. Xác định data consistency, replication lag và write authority.
5. Quyết định traffic shift theo policy, có thể theo wave.
6. Validate authentication, session lookup, authorization và business transaction.
7. Theo dõi error rate, latency, login success, session continuity và data correctness.
8. Giữ old region fenced nếu cần để tránh split-brain.
9. Thông báo người vận hành và ghi incident/change evidence.

### 11.2. Active-active và active-passive

| Khía cạnh | Active-passive | Active-active |
| --- | --- | --- |
| Ghi dữ liệu | Primary region; secondary standby/replica | Nhiều region có thể nhận ghi theo thiết kế |
| Session | Có thể replicate hoặc resolve về home region | Cần shared/replicated state hoặc stateless model |
| Failover | Cần promote/enable secondary | Traffic có thể chuyển nhưng data conflicts vẫn phải xử lý |
| Complexity | Thường thấp hơn | Cao hơn về consistency, routing, operations |
| Cost | Standby capacity và replication | Nhiều region chạy thường xuyên |
| Use case | Nơi cần DR và write ownership rõ | Nơi cần local serving, availability và scale cao |

Active-active không có nghĩa mọi state đều multi-master. Có thể active-active ở edge/stateless API nhưng active-passive ở transaction database.

### 11.3. Failback

Khi region gốc phục hồi:
- Không chuyển traffic ngay trước khi kiểm tra replication và data divergence.
- Xác định write authority và xử lý data mới sinh ra ở region DR.
- Reconcile session/revocation state và pending workflows.
- Đồng bộ cache/version và key metadata.
- Chạy canary/low-percent traffic.
- Theo dõi login, refresh, session, business transaction và error rate.
- Chỉ tăng traffic khi đủ điều kiện.
- Ghi nhận thời gian và kết quả failback.

Failback sai có thể ghi đè dữ liệu mới hoặc làm session bị stale. Cần có fencing để ngăn hai region cùng nhận ghi không được điều phối.

## 12. Security: session và identity không được yếu đi khi failover

Các kiểm soát cần duy trì xuyên region:
- TLS giữa client, edge, regional ingress và service.
- Token issuer/audience/signature validation nhất quán.
- Key rotation, JWKS cache và emergency revocation.
- Session cookie Secure/HttpOnly/SameSite phù hợp.
- CSRF, replay, fixation và token theft protections.
- Session idle timeout và absolute lifetime.
- User disable/password reset/session revoke propagation.
- MFA/step-up cho hành động nhạy cảm.
- Tenant isolation và object-level authorization.
- Workload identity giữa regional services.
- Audit log có correlation và region metadata nhưng không log raw secret/token.
- Rate limit và abuse protection ở global lẫn regional scope.

Nếu một region không nhận được revocation update, policy phải xác định có thể tiếp tục action nào và trong bao lâu. Với payment/admin/data export, có thể yêu cầu introspection hoặc check state mới hơn; với catalog public có thể cho phép access token còn hạn. Rủi ro và UX cần được phân loại theo action.

## 13. Privacy-aware observability

Để chẩn đoán session continuity, cần log đủ để liên kết request nhưng không thu thập quá nhiều dữ liệu cá nhân.

Có thể ghi:
- Pseudonymous subject/session reference hoặc keyed hash.
- Session version và token issuer/key ID; không ghi token.
- Source/target region và routing decision.
- Auth decision, result class và policy version.
- Session lookup source, replication version/lag.
- Request/correlation ID, latency, retry và failover event.
- Device/risk signals ở mức cần thiết và theo retention policy.

Không ghi raw cookie, access token, refresh token, private key hoặc full session object vào log. IP/device fingerprint có thể là dữ liệu cá nhân; phải có purpose, access control, residency và retention phù hợp.

## 14. Kiểm thử session continuity và global experience

### 14.1. Test matrix

| Kịch bản | Kết quả mong muốn |
| --- | --- |
| User login ở region A, request kế tiếp ở B | Token/session được xác minh đúng, không logout bất ngờ |
| Region A mất ingress | Router chuyển traffic; B có state/policy cần thiết |
| Region A mất session store | B dùng home/replicated store theo policy hoặc fail an toàn |
| Token hết hạn trong lúc failover | Refresh hợp lệ hoặc yêu cầu login lại |
| Signing key rotation | Region A/B đều xác minh key hợp lệ; key cũ được xử lý đúng |
| Revocation khi một region partitioned | Action nhạy cảm tuân theo freshness/fail-closed policy |
| Hai thiết bị cập nhật cart đồng thời | Conflict được phát hiện/merge theo rule |
| Payment timeout rồi chuyển region | Không tạo charge/booking trùng; status được tra cứu |
| Replication lag cao | Không route write nếu consistency chưa đủ |
| Failback sau DR | Không mất update, không split-brain |
| User di chuyển sang region bị hạn chế residency | Route home region hoặc từ chối theo policy |
| Clock skew | Token/session expiry không bị xử lý sai ngoài tolerance |

### 14.2. Đo SLI/SLO

Nên đo riêng:
- Global routing success và failover convergence.
- Authentication success theo region.
- Session continuity rate sau regional transition.
- Re-authentication rate do lỗi hệ thống (phân biệt với security re-auth).
- Session lookup latency và error.
- Token validation/JWKS refresh failure.
- Revocation propagation time.
- Booking/payment correctness sau failover.
- Regional latency và user experience theo geography.
- Residency policy denial/violation.
- Time to recover và data reconciliation duration.

Ví dụ SLI session continuity:

\[
SLI_{\text{continuity}} =
\frac{\text{Số transition hợp lệ tiếp tục đúng phiên}}
{\text{Tổng transition hợp lệ được thử}}
\]

Cần loại trừ trường hợp buộc đăng nhập lại vì lý do bảo mật hợp lệ khi định nghĩa "lỗi continuity"; nếu không, SLI có thể khuyến khích hệ thống chấp nhận phiên đã revoke.

## 15. Tình huống thực tế: nền tảng đặt chỗ phục vụ ba khu vực

### 15.1. Bối cảnh

Một SaaS đặt chỗ có người dùng tại ba khu vực. Hệ thống có:
- Global DNS/HTTP load balancer.
- Regional API và worker tại mỗi region.
- Central identity provider hỗ trợ OIDC.
- Access token ngắn hạn, refresh session record.
- Booking database có home region theo tenant.
- Catalog cache được replicate.
- Payment provider và notification provider bên ngoài.

Yêu cầu giả định:
- Người dùng có thể đi du lịch và tiếp tục phiên ở region khác.
- Tenant giữ dữ liệu booking ở home region theo policy.
- Catalog có thể đọc gần user.
- Payment không được tạo giao dịch trùng khi region failover.
- Revocation và account disable phải được xử lý theo risk policy.

### 15.2. Kiến trúc đề xuất

~~~mermaid
flowchart TB
    USER["User / browser / mobile"] --> GLB["Global traffic manager"]
    GLB --> A["Region A API"]
    GLB --> B["Region B API"]
    GLB --> C["Region C API"]
    IDP["OIDC Identity Provider"] --> A
    IDP --> B
    IDP --> C
    A --> AUTH["Token validation + policy"]
    B --> AUTH
    C --> AUTH
    AUTH --> SESS["Session / revocation service"]
    A --> ROUTE["Tenant home-region resolver"]
    B --> ROUTE
    C --> ROUTE
    ROUTE --> DB[("Home-region booking data")]
    A --> CACHE["Regional catalog cache"]
    B --> CACHE
    C --> CACHE
    A --> PAY["Payment provider"]
    B --> PAY
    C --> PAY
~~~

Luồng minh họa. Session/revocation service có thể là replicated hoặc home-region routed; lựa chọn phải dựa vào latency, residency và failover objective. Sơ đồ không hàm ý mọi region được ghi trực tiếp vào cùng database.

### 15.3. Quyết định thiết kế

- Access token sống ngắn và được xác minh local bằng public key đã tin cậy.
- Refresh session record có authority rõ; có thể route về home region hoặc store HA được phép.
- Tenant home region quyết định nơi xử lý booking và payment state.
- Catalog cache được replicate vì dữ liệu này có thể chấp nhận bounded staleness.
- Cart dùng version/optimistic concurrency; xung đột được hiển thị/merge theo quy tắc.
- Payment request dùng idempotency key toàn cục và status query trước retry.
- Revocation có propagation objective; thao tác nhạy cảm yêu cầu kiểm tra trạng thái mới.
- Region failover phải có capacity và data state đã được kiểm chứng trước khi nhận write.

### 15.4. User journey khi region A lỗi

1. Global router phát hiện A unhealthy và route request tiếp theo sang B.
2. Browser vẫn gửi cookie/access token; B xác minh issuer, audience, expiry và signature.
3. B lấy session/revocation state theo policy.
4. B xác định tenant home region và kiểm tra residency.
5. Catalog được phục vụ từ cache B nếu đủ freshness.
6. Nếu booking database home region vẫn khỏe, request được định tuyến tới đó qua đường riêng đã bảo vệ.
7. Nếu transaction state không xác định, UI hiển thị pending và dùng reference để query status; không tạo transaction mới.
8. Telemetry ghi source/serving region, correlation ID và kết quả mà không log token/cookie.

## 16. Các sai lầm thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Chỉ đổi DNS để tuyên bố đã có session continuity | Region mới không có session/key/data | Test toàn journey và state dependency |
| Dùng session in-memory trên API instance | User logout khi đổi backend/region | Externalize state hoặc token stateless phù hợp |
| Replicate toàn bộ session không phân loại | Tăng chi phí và có thể vi phạm residency | Chia state theo sensitivity/consistency |
| Dùng JWT quá dài để tránh refresh | Token bị lộ/revoke khó xử lý | Short TTL, refresh policy và revocation |
| Region dùng signing key/issuer config khác không kiểm soát | Token hợp lệ bị từ chối hoặc trust sai | Chuẩn hóa issuer/audience và key lifecycle |
| Bỏ qua revocation khi IdP outage | Phiên bị thu hồi vẫn truy cập | Policy theo action, fail-safe và propagation objective |
| Shared session store không có DR | Mọi region cùng mất session | Store HA, recovery và failure isolation |
| Active-active database không có conflict model | Lost update hoặc split-brain | Home-region ownership, versioning và conflict control |
| Dùng last-write-wins cho payment/inventory | Giao dịch sai | Source of truth và transaction semantics |
| Route theo latency bỏ qua residency | Dữ liệu đi sai khu vực | Tenant/data policy trước latency optimization |
| Failback ngay khi region cũ lên lại | Ghi đè dữ liệu mới hoặc session stale | Reconcile, fencing và canary failback |
| Log raw cookie/token để debug | Credential leak | Pseudonymous reference và redaction |
| Không kiểm thử clock skew/key rotation | Token expiry/validation lỗi theo region | Automated rotation và clock tests |
| Re-authentication do lỗi bị coi là security success | UX kém bị che trong metric | Phân loại security-driven và failure-driven re-auth |
| Payment retry ở region mới không idempotent | Charge hoặc booking trùng | Global idempotency key và reconciliation |

## 17. Bài tập thực hành

Một nền tảng SaaS đặt chỗ có region A phục vụ tenant trong nước và region B phục vụ tenant quốc tế. Global load balancer chọn region gần user. Session hiện lưu trong Redis riêng tại từng region; access token có thời hạn 30 phút; refresh token được lưu trong browser; một số booking/payment request có thể chạy bất đồng bộ. Khi region A gặp sự cố, user chuyển sang B nhưng thường bị logout, một số giỏ hàng mất cập nhật và support không biết payment đã thành công hay chưa.

Hãy thực hiện:

1. Vẽ journey và dependency graph cho login, refresh, cart, booking và payment.
2. Phân loại state theo ephemeral, reconstructable, durable, sensitive và regional.
3. So sánh stateless token, centralized session store, home-region session và hybrid model.
4. Thiết kế cookie/session/refresh lifecycle, token issuer/audience, key rotation và revocation.
5. Chọn global routing policy có xét health, latency, tenant home region và data residency.
6. Thiết kế session continuity khi chuyển A sang B; chỉ rõ state nào replicate, resolve từ home region hoặc tạo lại.
7. Đặt consistency/conflict rules cho cart, session revocation, booking và payment.
8. Thiết kế failover/failback gồm fencing, replication lag, idempotency và reconciliation.
9. Đề xuất UX cho expired token, IdP outage, payment unknown và residency restriction.
10. Lập SLI/SLO và test matrix cho regional transition, key rotation, revocation, split-brain và clock skew.
11. Viết ADR nêu tradeoff latency, availability, security, cost và operational complexity.

**Tiêu chí tự đánh giá:** giải pháp không chỉ giữ user login. Nó phải duy trì đúng identity/authorization, tránh mất hoặc nhân đôi business state, tuân thủ residency, xử lý token/revocation an toàn và cho người dùng biết chính xác giao dịch đang ở trạng thái nào.

## 18. Checklist trước khi phát hành kiến trúc chuyển khu vực

- [ ] Journey login, refresh, cart, checkout và payment được định nghĩa.
- [ ] Session state được phân loại theo sensitivity, consistency, TTL và residency.
- [ ] Global routing policy xét health, capacity, latency, tenant/home region và compliance.
- [ ] Session model (stateless/stateful/hybrid) có rationale và failure behavior.
- [ ] Cookie có Secure/HttpOnly/SameSite phù hợp; session ID được rotate và expire.
- [ ] Token issuer/audience/signature/expiry/scope được xác minh ở mọi region.
- [ ] JWKS/key rotation, emergency revocation và clock skew đã được thử.
- [ ] Refresh session, logout, account disable và revocation propagation có objective rõ.
- [ ] Home-region routing và cross-region data access tuân thủ residency.
- [ ] State replicate có version/conflict policy; sensitive state không copy tùy tiện.
- [ ] Booking/payment có idempotency, status query và reconciliation.
- [ ] Failover có capacity, data readiness, write fencing và monitoring.
- [ ] Failback có reconciliation, canary và điều kiện mở traffic.
- [ ] Degraded mode xác định cho IdP/session store/home region outage.
- [ ] UX không khuyến khích retry side effect khi trạng thái chưa rõ.
- [ ] Logs/metrics không chứa raw token/cookie/secret; privacy/retention được duyệt.
- [ ] SLI/SLO đo session continuity và business correctness theo region.
- [ ] Test matrix gồm transition, region loss, revocation, key rotation, lag và split-brain.
- [ ] Runbook, owner, escalation và DR exercise được cập nhật.
- [ ] ADR ghi tradeoff và trigger đánh giá lại.

## Ghi nhớ

Kiến trúc toàn cầu cần phối hợp **routing, session, identity và data ownership**. Global load balancer có thể đưa request tới region khỏe, nhưng region đó chỉ có thể tiếp tục phiên khi xác minh đúng token, session/revocation state, quyền truy cập và dữ liệu cần thiết.

Hãy phân loại state trước khi replicate; ưu tiên token ngắn hạn và identity có thể xác minh; giữ transaction state tại source of truth hoặc home region; dùng consistency/versioning và idempotency cho dữ liệu nghiệp vụ; thiết kế residency, failover và failback từ đầu. Trải nghiệm xuyên vùng tốt là trải nghiệm vừa liền mạch, vừa đúng, an toàn và giải thích rõ khi hệ thống cần xác thực lại hoặc chờ kết quả giao dịch.
