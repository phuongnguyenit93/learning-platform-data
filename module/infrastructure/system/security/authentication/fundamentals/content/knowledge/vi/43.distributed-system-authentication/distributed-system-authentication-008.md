# Độ sẵn sàng của identity service — Thiết kế xác thực phân tán có khả năng chịu lỗi

> **Chương:** Authentication trong distributed system  
> **Chủ đề:** Độ sẵn sàng của identity service  
> **Phạm vi:** Security Authentication Fundamentals — thiết kế identity service và các dependency xác thực có khả năng hoạt động ổn định khi một node, vùng, kho dữ liệu, key service hoặc identity provider gặp sự cố; cân bằng availability với tính đúng đắn và bảo mật của quyết định xác thực.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt availability của đăng nhập mới, token issuance, token validation, session, introspection và authorization.
2. Xây dựng SLI/SLO cho identity service dựa trên kết quả người dùng thực sự cần.
3. Lập dependency map và xác định failure domain của hệ thống xác thực phân tán.
4. Thiết kế active-active, active-passive, load balancing, health check và failover.
5. So sánh local JWT validation với opaque token introspection khi identity provider không khả dụng.
6. Thiết kế cache JWKS, discovery metadata, token và policy với TTL phù hợp.
7. Quyết định fail-closed, degraded mode hoặc last-known-good theo mức rủi ro của tài nguyên.
8. Ngăn retry storm bằng timeout, backoff, jitter, circuit breaker, bulkhead và load shedding.
9. Xử lý regional disaster, replication lag, key rotation, clock skew và session continuity.
10. Xây dựng runbook, observability và bộ kiểm thử chứng minh hệ thống phục hồi an toàn.

## 1. Độ sẵn sàng của identity service là gì?

**Identity service availability** là khả năng hệ thống cung cấp các chức năng liên quan đến danh tính và xác thực trong thời điểm client cần sử dụng. Nó không chỉ là việc một endpoint trả HTTP 200; người dùng hoặc workload cần hoàn tất đúng thao tác với kết quả bảo mật hợp lệ trong thời gian chấp nhận được.

Các chức năng thường nằm trong phạm vi:

- Đăng nhập bằng password, passkey hoặc MFA;
- Xác thực client/service và cấp access token;
- Refresh token hoặc đổi authorization code;
- Xác minh access token tại resource server;
- Introspection token opaque;
- Phân giải signing key và metadata của issuer;
- Tạo, đọc, gia hạn và thu hồi session;
- Kiểm tra trạng thái account, credential và policy;
- Step-up authentication, recovery và account linking.

Các chức năng này có dependency và đặc tính availability khác nhau. Identity provider có thể tạm ngừng cấp token nhưng resource server vẫn xác minh được JWT đã ký bằng public key đang cache. Ngược lại, token endpoint có thể hoạt động nhưng API không thể xử lý request vì policy service hoặc session store bị lỗi.

### Availability không đồng nghĩa với accept mọi request

Một hệ thống an toàn phải từ chối credential không hợp lệ, token hết hạn hoặc principal không có quyền. Những lần từ chối đúng policy không phải lỗi availability. SLI cần phân biệt:

- Request hợp lệ được xử lý thành công;
- Request không hợp lệ bị từ chối đúng;
- Request hợp lệ thất bại vì dependency hoặc hệ thống;
- Request bị timeout, quá tải hoặc không nhận được phản hồi.

Nếu chỉ đo tỷ lệ HTTP 2xx, hệ thống có thể trông như đang khỏe dù mọi login hợp lệ đều bị từ chối.

## 2. Các lớp availability trong authentication

Không nên gộp mọi chức năng identity vào một chỉ số duy nhất. Cần đo riêng các luồng có tác động khác nhau.

| Chức năng | Câu hỏi availability |
| --- | --- |
| Login | Người dùng có thể bắt đầu và hoàn tất xác thực mới không? |
| MFA/passkey | Challenge có được tạo, xác minh và hoàn tất không? |
| Token issuance | Client có đổi grant lấy token được không? |
| Token refresh | Session còn hiệu lực có thể lấy access token mới không? |
| Token validation | Resource server có thể xác minh token hiện có không? |
| Introspection | Resource server có lấy được trạng thái token opaque không? |
| JWKS/discovery | Client/verifier có lấy được metadata và public key cần thiết không? |
| Session | Session có thể được đọc, cập nhật và thu hồi không? |
| Authorization | Policy decision có được đưa ra đúng hạn không? |
| Recovery | Người dùng có thể khôi phục account theo assurance policy không? |

### Phân biệt control plane và request path

Một số thao tác xảy ra ít thường xuyên nhưng ảnh hưởng rộng:

- Quản trị issuer, client registration và trust configuration;
- Phát hành/rotate signing key;
- Cập nhật JWKS, discovery metadata và certificate;
- Thay policy, tenant mapping hoặc signing algorithm;
- Quản lý replication và disaster recovery.

Đây là control plane. Các request đăng nhập, đổi token, xác minh token và đọc session là data/request path. Control plane không khả dụng có thể chưa làm mọi request hiện tại thất bại ngay, nhưng có thể làm hệ thống không thể cấp credential mới, rotate key hoặc phục hồi sau sự cố.

## 3. SLI, SLO và error budget

Availability cần được đo bằng trải nghiệm hoàn tất luồng xác thực hợp lệ.

### Service Level Indicator (SLI)

Các SLI hữu ích:

- Tỷ lệ login hợp lệ hoàn tất thành công;
- Tỷ lệ token issuance thành công cho client hợp lệ;
- Tỷ lệ refresh token thành công;
- Tỷ lệ token validation hoàn tất trong latency budget;
- Tỷ lệ introspection thành công;
- Tỷ lệ session read/write/revoke thành công;
- p50/p95/p99 latency theo từng flow;
- Tỷ lệ timeout và dependency failure;
- Tỷ lệ MFA/passkey ceremony hoàn tất;
- Tỷ lệ authorization decision có kết quả đúng hạn.

Ví dụ SLI cho login:

`````````text
login_success_availability =
  valid_login_transactions_completed
  / valid_login_transactions_attempted
`````````

Không tính login failure do password sai, user cancel hoặc MFA proof không hợp lệ như outage. Cần phân loại theo reason code nội bộ để không làm đẹp số liệu bằng cách bỏ mọi request lỗi.

### Service Level Objective (SLO)

SLO là mục tiêu trong một cửa sổ thời gian, ví dụ tỷ lệ luồng token issuance hợp lệ thành công hoặc latency p99. Mục tiêu phải dựa trên nhu cầu ứng dụng, mức quan trọng của identity và khả năng vận hành.

Ví dụ minh họa:

| SLI | SLO minh họa |
| --- | --- |
| Login hợp lệ | 99,9% hoàn tất trong cửa sổ tháng |
| Token validation local | 99,99% quyết định trong latency budget |
| Token endpoint | p95 dưới 300 ms khi không có dependency degradation |
| Session read | 99,95% thành công |
| Revocation propagation | Đạt giới hạn thời gian đã định cho token/session cần thu hồi |

Các con số trên chỉ minh họa cách viết mục tiêu, không phải chuẩn chung. SLO thực tế cần tính đến region, tenant, giờ cao điểm, dependency và mức rủi ro.

### Error budget

Error budget là phần lỗi cho phép trong SLO. Khi budget bị tiêu thụ nhanh:

- Ưu tiên ổn định và giảm thay đổi rủi ro;
- Tạm hoãn deployment không thiết yếu;
- Điều tra dependency và capacity;
- Kiểm tra retry storm, cache miss và failover;
- Tăng synthetic monitoring và canary.

Không nên dùng error budget để nới lỏng kiểm tra chữ ký, MFA hoặc policy. Mục tiêu availability không cho phép chấp nhận credential chưa được xác minh.

## 4. Dependency map của identity service

Identity service thường phụ thuộc vào nhiều hệ thống. Một endpoint login có thể cần database, password hash service, risk engine, MFA provider, key service, session store và notification provider.

### Dependency thường gặp

| Dependency | Vai trò | Ảnh hưởng khi unavailable |
| --- | --- | --- |
| Account/credential database | Đọc account, password hash, factor metadata | Login mới có thể thất bại |
| Session store | Tạo/đọc/revoke session | Session-backed app có thể không hoạt động |
| Signing KMS/HSM | Ký token/assertion | Token issuance hoặc signing operation dừng |
| JWKS/discovery host | Cung cấp public key/issuer metadata | Verifier cache miss hoặc không nhận key mới |
| Token introspection | Kiểm tra trạng thái opaque token | API dùng opaque token có thể không quyết định được |
| MFA provider | Gửi/verify OTP hoặc push | Luồng yêu cầu factor đó bị ảnh hưởng |
| Risk engine | Risk score/adaptive policy | Có thể cần degraded policy theo risk |
| DNS/TLS/PKI | Kết nối và xác minh service | Request có thể không tới được dependency |
| Clock/NTP | Xác minh exp/nbf/iat, certificate và TOTP | Token/factor có thể bị từ chối sai |
| Policy/authorization service | Đưa ra quyết định quyền | Request cần policy động bị ảnh hưởng |
| Message/notification service | Gửi email/SMS recovery | Recovery/notification bị chậm hoặc dừng |

### Vẽ dependency trước khi thiết kế HA

`````````mermaid
flowchart TD
    C["Web/mobile/service clients"] --> G["Gateway / load balancer"]
    G --> I["Identity API"]
    I --> DB["Account and credential DB"]
    I --> S["Session/token state store"]
    I --> K["KMS/HSM signing"]
    I --> R["Risk and MFA services"]
    I --> P["Policy service"]
    I --> N["Notification provider"]
    RS["Resource servers"] --> J["JWKS / discovery"]
    RS --> X["Token introspection"]
    I --> J
`````````

Mỗi dependency cần owner, timeout, retry policy, health signal, failure mode và phương án phục hồi. Không thể gọi hệ thống là highly available nếu endpoint có nhiều replica nhưng tất cả cùng phụ thuộc một database hoặc một key service đơn lẻ.

## 5. Failure domain và single point of failure

Failure domain là phạm vi thành phần có thể cùng bị ảnh hưởng bởi một sự cố.

Ví dụ:

- Một process hoặc container;
- Một node/host;
- Một rack/availability zone;
- Một region;
- Một cloud account hoặc control plane;
- Một DNS provider;
- Một CA hoặc KMS tenant;
- Một database cluster;
- Một network path hoặc identity provider bên ngoài.

### Câu hỏi rà soát

- Các replica có chạy trên host/zone độc lập không?
- Load balancer có nằm cùng failure domain với service không?
- DNS và certificate renewal có phụ thuộc một vendor duy nhất không?
- Database có replica ở zone/region khác không?
- Signing key có thể dùng tại region dự phòng không?
- Secret manager có thể cấp credential cho workload sau failover không?
- Control plane có thể khôi phục nếu region chính mất hoàn toàn không?

HA ở lớp ứng dụng không đủ nếu mọi instance cùng một zone, cùng subnet hoặc cùng dependency. Cần xác định các failure domain độc lập và kiểm tra failover thực tế.

## 6. Kiến trúc active-active và active-passive

### Active-active

Nhiều region/zone cùng nhận traffic. Load balancer hoặc global routing phân phối request tới các instance đang hoạt động.

Ưu điểm:

- Tận dụng capacity của nhiều vùng;
- Có thể tiếp tục phục vụ khi một vùng mất;
- Giảm latency cho client gần region;
- Phù hợp với service stateless và token validation local.

Thách thức:

- State dùng chung cần consistency phù hợp;
- Replay cache và one-time token không được consume hai lần;
- Session revocation phải lan truyền;
- Key rotation và JWKS cần đồng bộ;
- Clock skew và network partition ảnh hưởng quyết định;
- Split-brain có thể tạo hai nguồn phát hành state không nhất quán.

### Active-passive

Một region phục vụ chính; region dự phòng được giữ sẵn và tiếp nhận traffic khi failover.

Ưu điểm:

- Có thể đơn giản hóa write ownership;
- Dễ giữ một nguồn authoritative cho một số state;
- Phù hợp workload không cần active-active toàn phần.

Thách thức:

- Failover có thể chậm;
- Replica có thể có replication lag;
- Region dự phòng có thể chưa đủ capacity;
- Runbook chưa được diễn tập có thể thất bại;
- Key, DNS, certificate và secret access cần hoạt động ở region dự phòng.

### Không có một lựa chọn đúng cho mọi thành phần

Identity API có thể active-active, database dùng primary/replica, KMS có key replication theo policy, còn token validation ở resource server thực hiện local. Thiết kế cần dựa vào semantics của từng state và rủi ro khi dữ liệu lệch.

## 7. Load balancing và health check

Load balancer phân phối request tới instance đủ điều kiện phục vụ. Health check sai có thể loại nhầm toàn bộ instance hoặc tiếp tục gửi traffic tới node hỏng.

### Liveness và readiness

- **Liveness:** process còn sống và có thể tiếp tục chạy không?
- **Readiness:** instance hiện có đủ dependency tối thiểu để nhận loại request này không?

Không nên làm liveness phụ thuộc vào mọi dependency bên ngoài. Nếu database tạm gián đoạn, tất cả instance restart liên tục có thể làm outage nghiêm trọng hơn. Readiness nên phản ánh khả năng phục vụ request cụ thể; có thể phân biệt endpoint local token validation với endpoint cần database.

### Health check nên nhẹ

- Không thực hiện password login thật mỗi vài giây;
- Không tạo token có quyền thật chỉ để kiểm tra;
- Không gửi OTP hoặc email trong synthetic health check;
- Dùng probe riêng, account test và resource giới hạn;
- Kiểm tra readiness của dependency quan trọng với timeout ngắn;
- Tránh health check tạo tải đáng kể lên identity provider.

### Canary và synthetic transaction

Health endpoint có thể xanh nhưng login flow vẫn lỗi vì cấu hình issuer, redirect URI, signing key hoặc MFA. Cần synthetic transaction định kỳ kiểm tra luồng end-to-end bằng identity test đã giới hạn quyền, không dùng credential thật của nhân viên.

## 8. Local JWT validation và opaque token introspection

Đây là một lựa chọn kiến trúc quan trọng khi identity provider tạm unavailable.

### Local JWT validation

Resource server kiểm tra JWT tại chỗ bằng public key đã nhận:

- Signature;
- Issuer;
- Audience;
- Expiration và not-before;
- Algorithm allowlist;
- Scope/claim theo profile;
- Token type và các điều kiện bổ sung.

Nếu public key đã được cache, resource server có thể tiếp tục xác minh token trong khi token endpoint hoặc identity API không khả dụng.

Ưu điểm:

- Không gọi identity provider trên từng request;
- Latency thấp;
- Giảm dependency runtime;
- Có thể tiếp tục phục vụ khi issuer outage.

Giới hạn:

- Khó thu hồi tức thời nếu verifier chỉ kiểm tra JWT local;
- Token đã phát hành có thể tiếp tục hợp lệ tới exp;
- Policy/role thay đổi có thể không được phản ánh ngay;
- Key mới chưa được cache có thể làm token mới không xác minh được;
- Cần quản lý JWKS cache và key rotation chính xác.

### Opaque token + introspection

Resource server gửi token tới authorization server/introspection endpoint để nhận trạng thái active và metadata.

Ưu điểm:

- Có thể phản ánh revoke/disable tập trung;
- Token không phải tự chứa nhiều claim;
- Policy và trạng thái có thể được cập nhật gần thời gian thực.

Giới hạn:

- Introspection trở thành dependency runtime;
- Latency và tải tăng;
- Issuer outage có thể làm API không thể quyết định;
- Cache introspection tạo trade-off giữa availability và độ mới của revoke.

### So sánh

| Tiêu chí | Local JWT | Opaque + introspection |
| --- | --- | --- |
| Runtime dependency | Public key cache | Introspection service |
| Latency | Thường thấp | Có thêm network round trip |
| Revocation freshness | Hạn chế nếu chỉ local | Có thể gần thời gian thực |
| Issuer outage | Có thể tiếp tục với key/token còn hợp lệ | Có thể không xác minh được khi cache miss |
| Claim exposure | Claim nằm trong token payload | Metadata trả qua introspection |
| Cache strategy | JWKS và policy cache | Introspection result cache |

Không có lựa chọn tuyệt đối tốt hơn. Có thể dùng JWT cho một số API và opaque token cho resource nhạy cảm cần revoke nhanh.

## 9. JWKS, discovery metadata và key cache

Resource server thường cần issuer metadata và public signing key để xác minh token. Nếu mỗi request đều tải JWKS, identity provider trở thành dependency nóng và outage dễ lan rộng.

### Cache JWKS

- Cache theo issuer đã cấu hình tin cậy;
- Dùng HTTPS và xác minh TLS;
- Tôn trọng cache header trong giới hạn policy;
- Lưu public key theo kid và thuật toán được phép;
- Không tin jku/x5u tùy ý do token gửi tới;
- Refresh khi gặp kid chưa biết, nhưng phải rate limit;
- Có negative cache ngắn cho kid không tồn tại để tránh request flood;
- Theo dõi refresh failure, age và key set version.

### Khi kid chưa biết

Verifier có thể thực hiện một lần refresh JWKS có kiểm soát. Nếu key vẫn không có hoặc endpoint unavailable, token cần bị từ chối hoặc xử lý theo policy đã định; không được bỏ qua signature verification.

### JWKS outage và stale key

Nếu cache có public key đang được tin cậy và token vẫn trong thời hạn, local validation có thể tiếp tục. Nhưng chấp nhận key cache cũ có nghĩa verifier có thể chưa biết key đã bị thu hồi hoặc compromise. Với key compromise, cần emergency denylist/forced refresh hoặc cơ chế key status khác; không giữ stale key vô thời hạn chỉ để duy trì availability.

### Discovery metadata

OIDC discovery document chứa endpoint và capability metadata. Cache metadata để tránh phụ thuộc discovery trên từng request, nhưng thay đổi issuer/endpoint cần được rollout và xác minh. Không lấy issuer URL từ token hoặc request chưa tin cậy để tự động tải discovery.

## 10. Session store và state consistency

Nếu session được lưu server-side, mỗi request có thể cần đọc session store. Store outage có thể làm người dùng mất khả năng sử dụng session dù identity provider vẫn hoạt động.

### Các lựa chọn

- Distributed key-value store có replication;
- Database session table;
- Stateless signed/encrypted session cookie;
- Kết hợp local cache ngắn hạn với authoritative store.

### Trade-off

| Mô hình | Ưu điểm | Rủi ro |
| --- | --- | --- |
| Server-side session | Revoke và update tập trung | Store là dependency runtime |
| Stateless cookie/token | Không cần đọc session store mỗi request | Revoke và thay đổi quyền khó phản ánh ngay |
| Local session cache | Giảm latency và tải | Stale state, cache invalidation và consistency |

### Consistency

Không phải mọi state đều có thể eventual-consistent:

- One-time authorization code phải consume một lần;
- Password reset/recovery token không được dùng đồng thời hai lần;
- Session revoke cần lan truyền trong SLA đã xác định;
- MFA enrollment và recovery state cần tránh rollback;
- Last-used timestamp hoặc telemetry có thể chấp nhận eventual consistency.

Phân loại state theo yêu cầu correctness trước khi chọn database/cache. Không đánh đổi one-time semantics để tăng throughput mà không có phân tích rủi ro.

## 11. Fail-closed, fail-open và degraded mode

Khi dependency không khả dụng, hệ thống phải quyết định tiếp tục, từ chối hay cung cấp chức năng giới hạn. Đây là quyết định theo loại thao tác và tài nguyên, không phải một cờ chung cho toàn bộ identity service.

### Fail-closed

Không thực hiện hành động nếu không thể xác minh credential hoặc quyền cần thiết.

Phù hợp khi:

- Không thể kiểm tra chữ ký/token;
- Không có public key tin cậy cho kid mới;
- Recovery hoặc credential enrollment không thể xác minh;
- Hành động nhạy cảm yêu cầu policy mới nhất;
- Authorization dependency không trả được quyết định và không có cache được phép dùng.

### Degraded mode

Tiếp tục một phần chức năng đã được xác minh độc lập, trong giới hạn policy rõ ràng.

Ví dụ:

- Resource server tiếp tục validate JWT bằng public key cache còn tin cậy;
- Session hiện tại tiếp tục truy cập chức năng ít rủi ro trong thời gian ngắn;
- Cho phép đọc dữ liệu công khai không yêu cầu danh tính;
- Tạm dừng login mới, recovery, thay đổi factor và thao tác đặc quyền;
- Dùng last-known-good policy trong TTL ngắn cho một tập action đã được phê duyệt.

### Fail-open

Chỉ nên cân nhắc trong trường hợp rất cụ thể, có risk acceptance rõ ràng và giới hạn resource/action. Không thể xác minh credential không có nghĩa là credential hợp lệ. Không biến outage thành lý do cấp quyền mặc định.

### Ma trận quyết định minh họa

| Tình huống | Hành vi an toàn gợi ý |
| --- | --- |
| Login mới, credential database unavailable | Tạm từ chối login; trả service unavailable |
| JWT đã ký, public key tin cậy đang cache | Tiếp tục local validation nếu token/policy còn hợp lệ |
| JWT kid chưa biết, JWKS unavailable | Từ chối token đó; không bỏ qua chữ ký |
| Opaque token, introspection cache còn mới | Dùng cache trong TTL/policy cho phép |
| Opaque token, cache miss và introspection unavailable | Không coi token active; từ chối hoặc trả dependency unavailable |
| High-risk transfer, policy service unavailable | Fail-closed |
| Public content không cần identity | Tiếp tục không cần authentication |
| Existing low-risk session, policy cache còn trong TTL | Có thể degraded theo policy đã phê duyệt |
| MFA enrollment/recovery, factor service unavailable | Không hoàn tất thay đổi credential |

Trả 503 khi hệ thống không thể đưa ra quyết định do dependency outage; không giả vờ token sai bằng 401 hoặc quyền bị từ chối bằng 403.

## 12. Cache và stale decision

Cache có thể tăng availability và giảm tải, nhưng cache làm dữ liệu cũ tồn tại lâu hơn.

### Loại dữ liệu có thể cache

- JWKS/public key;
- OIDC discovery metadata;
- Introspection result;
- Account status;
- Authorization policy/role mapping;
- Session metadata;
- Tenant configuration;
- Risk decision trong một số flow.

### TTL theo rủi ro

TTL nên dựa trên:

- Thời gian token còn hiệu lực;
- SLA revoke;
- Mức nhạy cảm của resource;
- Khả năng cache invalidation;
- Tần suất thay đổi policy;
- Hậu quả khi dùng dữ liệu cũ.

Một quyết định quyền cho trang đọc thông tin ít nhạy cảm có thể chấp nhận TTL ngắn hơn một quyết định chuyển tiền hoặc thay đổi MFA. Không dùng một TTL duy nhất cho mọi loại cache.

### Cache invalidation

Có thể dùng event invalidation, version/epoch, pub-sub, push notification hoặc polling. Cần xử lý trường hợp event bị mất, consumer offline hoặc message đến sai thứ tự. Cache cần có max age để tự hết hạn ngay cả khi invalidation không hoạt động.

### Last-known-good

Nếu dùng last-known-good, lưu cả thời điểm, version và phạm vi policy. Khi quá TTL, không tiếp tục chấp nhận vô hạn. Mọi lần dùng degraded decision cần được audit và có metric riêng.

## 13. Timeout, retry và exponential backoff

Một dependency chậm có thể nguy hiểm gần như dependency bị down. Nếu request chờ quá lâu, thread, connection pool và worker sẽ bị chiếm giữ; nhiều request đồng thời có thể làm toàn bộ identity service cạn tài nguyên.

### Timeout theo từng hop

- Đặt connect timeout và response/read timeout;
- Đặt deadline tổng cho toàn bộ authentication transaction;
- Timeout nội bộ phải nhỏ hơn deadline của caller;
- Propagate remaining deadline qua service-to-service call;
- Không để retry kéo dài quá deadline;
- Tách timeout cho KMS, database, introspection, MFA và policy service.

Không dùng một timeout quá dài cho mọi dependency. KMS signing operation và database query có đặc tính latency khác nhau; timeout cần dựa trên percentile đo được và ngân sách end-to-end.

### Retry có kiểm soát

Retry chỉ phù hợp với lỗi tạm thời và thao tác có semantics an toàn. Không retry vô hạn khi:

- Credential sai hoặc thiếu quyền;
- Request sai cú pháp;
- Token đã hết hạn;
- One-time code đã consume;
- Request không idempotent có thể đã thực hiện side effect.

### Exponential backoff và jitter

Một client có thể tăng khoảng chờ sau mỗi lần retry, đồng thời thêm jitter để nhiều client không retry cùng lúc:

`````````
delay = min(max_delay, base_delay * 2^attempt)
wait = random_between(0, delay)
`````````

Đây là công thức minh họa. Cần giới hạn số lần retry, tổng thời gian và retry budget. Nếu server trả Retry-After, client nên tôn trọng giá trị đó trong giới hạn deadline của chính nó.

### Retry storm

Khi identity provider chậm, hàng nghìn service có thể retry đồng thời. Retry làm tăng tải lên dependency vốn đang quá tải, khiến recovery chậm hơn. Dùng exponential backoff, jitter, retry budget, circuit breaker và load shedding để ngăn khuếch đại.

## 14. Circuit breaker, bulkhead và load shedding

Các pattern resilience giúp giới hạn ảnh hưởng của dependency failure.

### Circuit breaker

Circuit breaker có ba trạng thái:

- **Closed:** request được gửi bình thường; theo dõi failure/latency;
- **Open:** tạm dừng gọi dependency sau khi vượt ngưỡng;
- **Half-open:** cho một số probe có giới hạn để xác định dependency đã phục hồi chưa.

Không dùng một circuit breaker chung cho toàn bộ identity service nếu các dependency có hành vi khác nhau. Introspection outage không nhất thiết phải ngắt local JWT validation.

### Bulkhead

Bulkhead tách tài nguyên cho từng dependency hoặc loại request:

- Connection pool riêng cho database và introspection;
- Thread/worker pool riêng cho MFA và notification;
- Giới hạn concurrency cho KMS operation;
- Quota theo tenant/client;
- Tách login, token refresh và administrative API.

Nếu MFA provider bị chậm, bulkhead giúp nó không chiếm hết worker phục vụ token validation hoặc session read.

### Load shedding

Khi hệ thống gần quá tải, có thể từ chối sớm request ít ưu tiên hoặc vượt quota để giữ năng lực cho request quan trọng.

Ví dụ:

- Giới hạn burst của client;
- Ưu tiên refresh/validation đang trong deadline;
- Tạm dừng report/admin query nặng;
- Giới hạn login thử lại tự động;
- Từ chối request không có deadline hợp lý.

Không được bỏ qua xác minh chữ ký hoặc authorization để tăng throughput. Load shedding từ chối request có kiểm soát; nó không làm giảm tiêu chuẩn xác thực.

## 15. Capacity planning và bảo vệ dependency

Identity service thường có tải không đều: giờ bắt đầu làm việc, đầu ngày, sau deployment, khi access token hết hạn đồng loạt hoặc sau một sự cố.

### Những nguồn tạo spike

- Token TTL đồng loạt hết hạn;
- Nhiều client refresh cùng thời điểm;
- Mobile app khởi động sau outage;
- Browser retry sau 401/503;
- JWKS cache miss trên nhiều region;
- MFA push/SMS resend;
- Login attack hoặc credential stuffing;
- Service restart làm mất local cache;
- Failover dồn toàn bộ traffic sang một region.

### Kiểm soát

- Jitter khi refresh token trước expiry;
- Stagger rollout và cache warmup;
- Giới hạn concurrency và queue depth;
- Rate limit theo client/tenant/subject;
- Đặt quota cho JWKS refresh và introspection;
- Autoscaling có giới hạn để không làm database/KMS quá tải;
- Dự phòng capacity cho failover;
- Load test với pattern token expiry đồng loạt.

### Tránh thundering herd ở JWKS

Khi cache hết hạn, nhiều verifier có thể cùng tải JWKS. Dùng single-flight/coalescing refresh, jitter TTL và cache kết quả theo issuer. Nếu refresh thất bại, áp dụng stale-key policy có giới hạn; không để mỗi request tự tạo một lần fetch.

## 16. Database, KMS và clock trong failure handling

### Database

Identity database thường lưu account, credential metadata, recovery state, session hoặc refresh token. Cần:

- Replication và backup được kiểm tra;
- Connection pool có giới hạn;
- Query/index phù hợp;
- Failover có fencing để tránh hai primary cùng ghi;
- Consistency cho one-time state và revoke;
- Restore procedure có kiểm tra dữ liệu mới nhất;
- Theo dõi replication lag.

Nếu database failover sang replica có lag, password reset token đã consume hoặc session revoke có thể xuất hiện lại. Với dữ liệu one-time/revocation, cần bảo đảm semantics không bị rollback; không tự động promote replica mà chưa đánh giá RPO và state quan trọng.

### KMS/HSM

Signing key service có thể là critical dependency cho token issuance. Cần kiểm tra:

- Key được phép sử dụng ở region dự phòng;
- IAM policy cho workload signer;
- Quota, concurrency và latency;
- HSM cluster failover;
- Key version/alias mapping;
- Backup/recovery theo policy của provider;
- Không export private key chỉ để làm failover dễ hơn.

Nếu KMS không khả dụng, có thể tiếp tục verify bằng public key cache nhưng không được giả mạo signing operation hoặc dùng một key không được phê duyệt.

### Clock synchronization

Clock sai ảnh hưởng exp, nbf, iat, TOTP, certificate validity, assertion time window và cache TTL.

- Đồng bộ server với nguồn thời gian tin cậy;
- Giám sát offset và drift;
- Không chấp nhận clock skew quá rộng để che lỗi;
- Dùng monotonic clock cho duration/timeout;
- Dùng UTC cho timestamp audit;
- Xử lý leap/clock step theo nền tảng;
- Alert khi node có offset khác biệt lớn.

Clock skew có thể khiến một region từ chối token mà region khác chấp nhận. Cần đo và cảnh báo trước khi lỗi lan rộng.

## 17. Regional failover và disaster recovery

Regional disaster có thể làm mất identity API, database, key service hoặc network tới dependency. Disaster recovery cần xác định dữ liệu nào phải được phục hồi, thời gian chấp nhận được và cách bảo đảm trust không bị hạ thấp.

### RTO và RPO

- **RTO (Recovery Time Objective):** thời gian tối đa mục tiêu để khôi phục dịch vụ;
- **RPO (Recovery Point Objective):** lượng dữ liệu/thời gian có thể mất theo mục tiêu khôi phục.

Ví dụ, mất vài phút telemetry có thể chấp nhận; mất trạng thái revoke, one-time token hoặc account recovery có thể tạo lỗ hổng bảo mật. RPO cần phân loại theo data domain, không áp dụng chung cho mọi bảng.

### Kế hoạch failover

1. Phát hiện region lỗi bằng synthetic check và dependency telemetry;
2. Xác định failure domain và khả năng phục vụ của region còn lại;
3. Ngăn split-brain hoặc ghi đồng thời ngoài thiết kế;
4. Chuyển traffic theo global routing/load balancer;
5. Xác minh issuer, signing key, JWKS, database và secret access;
6. Kiểm tra session/revocation/one-time state;
7. Warm cache và giới hạn traffic ramp-up;
8. Theo dõi login, token issuance, validation và error rate;
9. Giữ region lỗi ở trạng thái cách ly cho tới khi an toàn;
10. Sau phục hồi, reconcile state và failback theo kế hoạch.

### Failback

Không tự động chuyển traffic về region chính ngay khi health check xanh. Cần xác minh replication, key state, revoke events, cache và capacity. Failback là một thay đổi production có thể gây split-brain hoặc cache stampede nếu làm đột ngột.

### Diễn tập

DR plan cần được diễn tập với:

- Mất một availability zone;
- Mất region chính;
- KMS/HSM không khả dụng;
- Database failover có replication lag;
- JWKS endpoint không truy cập được;
- DNS hoặc certificate issue;
- Secret manager outage;
- Khôi phục từ backup.

## 18. Token và session continuity khi identity provider outage

Identity provider outage không nhất thiết làm mọi user đang đăng nhập bị đăng xuất. Cần thiết kế theo loại credential và mức rủi ro.

### Existing JWT

Resource server có thể tiếp tục xác minh JWT bằng public key cache nếu:

- Issuer/audience/algorithm đúng;
- Signature hợp lệ;
- exp/nbf còn hợp lệ;
- Key vẫn được policy tin cậy;
- Authorization claims đủ cho action;
- Token chưa nằm trong denylist/revocation signal cần áp dụng.

Nếu không có cơ chế revoke tức thời, token có thể tiếp tục được chấp nhận tới khi hết hạn. Vì vậy token lifetime, scope và risk phải được cân nhắc.

### Opaque token

Nếu cần introspection trực tuyến, outage có thể làm resource server không biết token còn active hay không. Cache introspection có thể giúp trong TTL, nhưng quyết định cũ có thể bỏ sót revoke mới. Với tài nguyên nhạy cảm, fail-closed khi cache hết hạn.

### Existing session

Session server-side có thể tiếp tục nếu session store còn khả dụng và policy cho phép. Nếu store outage, không tự chuyển mọi session thành trusted dựa trên cookie không xác minh. Stateless session cookie cần signature/encryption và expiry; revoke sẽ phụ thuộc denylist/version/TTL.

### Login mới và refresh

Khi issuer outage:

- Tạm dừng login mới nếu không thể xác minh credential;
- Không phát hành token bằng key không được phê duyệt;
- Refresh token cần được xử lý theo availability của token endpoint;
- Không biến refresh failure thành account lockout;
- Không xóa session cục bộ chỉ vì dependency timeout;
- Cho client retry có backoff khi dịch vụ phục hồi.

## 19. Runbook xử lý identity service outage

Runbook cần giúp operator phân biệt lỗi hạ tầng, lỗi key, lỗi cấu hình và tấn công.

### Triage

1. Xác định chức năng nào lỗi: login, token endpoint, validation, introspection, session hay authorization;
2. Phân loại phạm vi: tenant, client, region, route và authentication method;
3. Kiểm tra deployment/key rotation/configuration gần nhất;
4. Kiểm tra DNS, TLS, clock, database, KMS, secret manager và network;
5. Đối chiếu synthetic checks với production traffic;
6. Xem timeout, connection pool, queue depth, retry và circuit breaker;
7. Xác định request hợp lệ có bị từ chối nhầm hay request không hợp lệ đang được chấp nhận;
8. Kích hoạt degraded mode đã phê duyệt nếu điều kiện phù hợp;
9. Truyền thông trạng thái và cập nhật ETA khi có căn cứ.

### Phục hồi

- Khôi phục dependency theo thứ tự dependency graph;
- Không mở tất cả circuit breaker cùng lúc;
- Ramp traffic từ từ;
- Warm JWKS/discovery/session cache có kiểm soát;
- Kiểm tra token issuance và signature;
- Xác minh revoke/one-time state;
- Theo dõi retry backlog và token refresh storm;
- Chỉ đóng incident khi synthetic transaction và production SLI ổn định.

### Sau sự cố

- Ghi timeline, impact và customer effect;
- Xác định root cause và contributing factors;
- Rà soát security decision trong degraded window;
- Kiểm tra token/session phát hành hoặc được chấp nhận trong outage;
- Thu hồi credential nếu có nghi ngờ compromise;
- Cập nhật SLO, runbook, capacity và test suite.

## 20. Threat model và bộ kiểm thử chấp nhận

### Threat model

| Rủi ro | Cách xảy ra | Kiểm soát |
| --- | --- | --- |
| **Single point of failure** | Một DB/KMS/DNS/provider làm dừng toàn bộ auth | Failure-domain mapping, redundancy, DR |
| **Retry storm** | Client retry đồng loạt khi issuer chậm | Backoff, jitter, retry budget, circuit breaker |
| **Thundering herd** | Cache expiry khiến mọi node fetch JWKS | Single-flight, TTL jitter, bounded refresh |
| **Stale revocation** | Cache cũ tiếp tục chấp nhận token đã revoke | TTL theo risk, invalidation, denylist/short lifetime |
| **Unknown kid bypass** | Verifier bỏ qua signature khi key chưa tải được | Fail closed cho unknown key |
| **Split-brain** | Hai region cùng ghi one-time/revoke state | Fencing, single-writer hoặc consistency protocol |
| **Replication rollback** | Replica cũ làm sống lại token/session đã revoke | RPO theo data class, reconciliation |
| **KMS outage** | Không thể ký token mới | Multi-zone/region key availability, local verify |
| **Clock drift** | Node chấp nhận/từ chối token khác nhau | NTP monitoring, bounded skew |
| **Fail-open abuse** | Outage được lợi dụng để bỏ qua auth | Degraded policy giới hạn, audit, fail-closed high-risk |
| **Cache poisoning** | Metadata/JWKS từ issuer không tin cậy | Issuer allowlist, HTTPS, no arbitrary jku |
| **Session store outage** | Session lookup thất bại | HA store, controlled degraded mode |
| **Refresh storm** | Token đồng loạt hết hạn | Refresh jitter, stagger, client retry budget |
| **Regional overload** | Traffic failover vượt capacity | Capacity reserve, gradual ramp, load shedding |
| **Health-check loop** | Dependency lỗi khiến mọi pod restart | Tách liveness/readiness, probe budget |
| **Secret manager outage** | Workload không lấy được secret | Runtime cache có giới hạn, workload identity, DR |
| **Policy stale** | Quyền cũ tiếp tục được chấp nhận | Versioned policy, short TTL cho action nhạy cảm |
| **Revocation lag** | Token/session còn dùng được ở region khác | Propagation SLI, event reconciliation |

### Bộ kiểm thử

| Trường hợp | Cách thử | Kết quả kỳ vọng |
| --- | --- | --- |
| Login healthy | Synthetic valid login | Hoàn tất trong SLO |
| Invalid credential | Password sai | Bị từ chối đúng, không tính nhầm là outage |
| Token issuance | Client hợp lệ xin token | Token được cấp và kiểm tra đúng issuer/audience |
| Local JWT validation | Tắt token endpoint, giữ JWKS cache | Token hợp lệ còn hạn vẫn verify được theo policy |
| Unknown kid | Token dùng kid chưa biết | Refresh JWKS có giới hạn; không bỏ qua signature |
| JWKS outage | Chặn JWKS endpoint | Dùng key cache còn tin cậy theo TTL; unknown key bị từ chối |
| JWKS refresh flood | Gửi nhiều token kid lạ | Single-flight/rate limit ngăn request storm |
| Introspection healthy | Opaque token active | API nhận kết quả đúng |
| Introspection outage | Chặn introspection sau cache expiry | Fail-closed hoặc degraded policy đã phê duyệt |
| Revoked opaque token | Revoke rồi gọi API | Từ chối trong SLA |
| Session store outage | Làm session store unavailable | Không tạo session giả; lỗi được phân loại |
| Session cache stale | Revoke session khi node có cache | Revoke lan truyền theo SLA |
| Database failover | Chuyển primary sang replica | Không rollback one-time/revoke state ngoài RPO |
| KMS outage | Chặn signing API | Không phát hành token bằng key trái phép; validation cache tiếp tục nếu phù hợp |
| KMS failover | Chuyển sang region dự phòng | Signing tiếp tục với key được phê duyệt |
| Clock skew | Đặt node lệch thời gian | Alert và bounded validation behavior |
| One-time code race | Hai region consume cùng code | Chỉ một request thành công |
| Active-active failover | Tắt một zone | Traffic chuyển và SLI vẫn trong mục tiêu |
| Active-passive failover | Tắt region chính | Region dự phòng lên theo RTO |
| Split-brain | Mô phỏng mất liên lạc giữa region | Không có hai writer trái thiết kế |
| Retry storm | Mô phỏng dependency latency | Retry budget/backoff giới hạn tải |
| Circuit breaker | Làm dependency vượt failure threshold | Circuit mở và probe half-open có giới hạn |
| Bulkhead | Làm MFA provider chậm | Token validation không cạn worker |
| Load shedding | Tạo quá tải | Request ưu tiên được phục vụ, auth policy không bị bỏ |
| Refresh herd | Làm token đồng loạt gần expiry | Jitter/stagger phân tán refresh |
| Health probe | Làm database tạm unavailable | Liveness không restart toàn bộ service |
| Recovery outage | Tắt notification provider | Không hoàn tất recovery thiếu bằng chứng |
| Degraded low-risk | Tắt policy service trong action đã allowlist | Chỉ last-known-good trong TTL và audit |
| Degraded high-risk | Tắt policy service với thao tác nhạy cảm | Fail-closed |
| Regional failback | Khôi phục region chính | Reconcile state trước khi chuyển traffic |
| Backup restore | Khôi phục identity DB từ backup | Kiểm tra revoke, key và one-time state trước mở traffic |
| SLO alert | Tăng valid-login failure | Alert theo SLI, không nhầm invalid credential |
| Audit completeness | Chạy outage/degraded scenario | Có request ID, dependency reason và decision mode |

Kiểm thử phải bao gồm failure injection, load test, multi-region và security validation. Một endpoint health trả 200 không chứng minh toàn bộ login/token/session flow có availability.

## 21. Checklist thiết kế availability cho identity service

- **Service boundaries:** Đã tách SLI cho login, token issuance, validation, introspection, session và authorization?
- **SLO:** Mục tiêu availability/latency phản ánh request hợp lệ và error budget?
- **Dependency map:** Database, KMS, JWKS, MFA, policy, DNS, TLS và clock có owner/failure mode?
- **Failure domains:** Replica có độc lập host/zone/region và dependency?
- **HA model:** Active-active/active-passive được chọn theo semantics của state?
- **Health check:** Liveness, readiness và synthetic transaction được tách đúng?
- **Token model:** Local JWT hay introspection được chọn theo revoke freshness và outage behavior?
- **JWKS:** Cache, unknown kid refresh, stale key và key compromise có policy?
- **Session/state:** One-time code, revoke và recovery state có consistency phù hợp?
- **Degraded mode:** Fail-closed/last-known-good được xác định theo action risk?
- **Retry:** Timeout, deadline, backoff, jitter và retry budget được cấu hình?
- **Resilience:** Circuit breaker, bulkhead và load shedding không làm bypass auth?
- **Capacity:** Có dự phòng cho token expiry herd, failover và cache warmup?
- **DR:** Có RTO/RPO theo data class, runbook và failback?
- **Clock:** Time sync, drift monitoring và bounded skew?
- **Observability:** SLI, dependency latency, cache age, revoke propagation và degraded decision?
- **Incident response:** Có triage, recovery, audit và post-incident review?
- **Testing:** Đã diễn tập zone/region/KMS/DB/JWKS outage, retry storm và split-brain?

### Câu hỏi tự kiểm tra

1. Vì sao availability của login khác availability của token validation?
2. Khi identity provider outage, vì sao resource server vẫn có thể validate JWT đã ký?
3. Local JWT validation và opaque token introspection có trade-off nào?
4. JWKS cache stale giúp availability nhưng tạo rủi ro gì?
5. Vì sao token có kid chưa biết không được chấp nhận khi JWKS unavailable?
6. Khi nào dùng last-known-good policy và khi nào phải fail-closed?
7. Vì sao session revoke và one-time token cần consistency mạnh hơn telemetry?
8. Retry storm và thundering herd khác nhau như thế nào?
9. Liveness và readiness probe khác nhau ở mục đích nào?
10. RPO của revoke state khác RPO của metrics ra sao?
11. Vì sao không nên tự động failback chỉ vì region chính health check xanh?
12. Làm thế nào chứng minh hệ thống phục hồi mà không hạ tiêu chuẩn xác thực?

## Kết luận

**Độ sẵn sàng của identity service phải được thiết kế theo từng luồng và từng quyết định bảo mật, không chỉ theo số replica hoặc trạng thái HTTP endpoint.** Dependency map, failure-domain isolation, SLO/SLI, HA, cache và disaster recovery giúp hệ thống tiếp tục phục vụ những thao tác có thể xác minh an toàn. Local JWT validation có thể duy trì hoạt động khi issuer outage nếu public key cache còn tin cậy; introspection và session store cần policy riêng cho cache miss và revoke freshness. Khi dependency lỗi, degraded mode chỉ được áp dụng cho action đã đánh giá rủi ro, còn xác minh credential và thao tác nhạy cảm phải fail-closed khi không đủ bằng chứng. Timeout, retry budget, jitter, circuit breaker, bulkhead, capacity reserve và failover rehearsal giúp ngăn một dependency chậm biến thành outage toàn hệ thống. Chỉ khi SLI phản ánh luồng hợp lệ, revoke/one-time state giữ đúng semantics và runbook được diễn tập, identity service mới vừa sẵn sàng vừa đáng tin cậy.
