# Đánh giá nhu cầu Front-Channel hoặc Back-Channel Logout và phần cần mở rộng

## 1. Vì sao phải đánh giá logout đa ứng dụng?

Một OpenID Provider (OP) có thể phục vụ nhiều Relying Party (RP): portal, admin console, mobile backend và các ứng dụng nội bộ. Người dùng đăng nhập một lần tại OP, sau đó tạo session độc lập tại từng RP. Khi OP kết thúc phiên SSO, các RP có thể vẫn giữ cookie/session của riêng chúng.

**Single Logout (SLO)** là yêu cầu phối hợp kết thúc các session liên quan trên nhiều RP. OpenID Connect định nghĩa các cơ chế bổ sung nhau để giải quyết bài toán này:

- **RP-Initiated Logout:** một RP yêu cầu OP kết thúc phiên SSO, thường qua browser redirect tới `end_session_endpoint`.
- **Front-Channel Logout:** OP dùng browser/User Agent để gọi logout URI của các RP, thường qua iframe.
- **Back-Channel Logout:** OP gửi HTTP request trực tiếp từ server tới server của RP, kèm Logout Token đã ký.
- **Session Management:** RP theo dõi trạng thái phiên OP qua cơ chế browser/iframe và phát hiện session thay đổi.

Không phải hệ thống nào cũng cần triển khai cả bốn. Câu hỏi thiết kế là: **cần kết thúc session ở những RP nào, độ tin cậy thông báo cần tới đâu, RP có thể truy cập bằng kênh nào, và framework đang hỗ trợ vai trò nào?**

Bài thuộc chương **OIDC Logout** của module `SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER`, nhằm đánh giá lựa chọn Front-Channel/Back-Channel và xác định phần cần mở rộng trong ứng dụng Spring Security/Spring Authorization Server.

Sau bài học, bạn có thể:
1. Xác định yêu cầu SLO theo ứng dụng, browser, thiết bị và tenant.
2. So sánh Front-Channel và Back-Channel theo độ tin cậy, khả năng tiếp cận và vận hành.
3. Hiểu metadata, client registration và cách OP ghi nhớ các RP đã đăng nhập.
4. Xác minh Logout Token và ánh xạ `iss`, `aud`, `sub`, `sid` vào local session.
5. Xác định hỗ trợ sẵn của Spring Security và ranh giới mở rộng tại Spring Authorization Server.
6. Thiết kế fan-out, retry, replay protection, session registry và observability.
7. Viết kiểm thử chứng minh logout đúng session, đúng client và không xóa nhầm người dùng khác.

## 2. Phân biệt các cơ chế logout

| Cơ chế | Bên khởi tạo | Kênh truyền | Tác động chính |
| --- | --- | --- | --- |
| RP-Initiated Logout | RP | Browser redirect tới OP | Yêu cầu OP kết thúc SSO session |
| Front-Channel Logout | OP | Browser, thường qua iframe | Gọi logout URI ở từng RP |
| Back-Channel Logout | OP | HTTP server-to-server | Gửi Logout Token để RP kết thúc session |
| Session Management | RP và OP | Browser/iframe | Phát hiện trạng thái session OP thay đổi |
| Local logout | RP | Nội bộ ứng dụng | Xóa session hiện tại của RP |

Các cơ chế có thể kết hợp. Ví dụ, người dùng bấm logout tại Portal:
1. Portal kết thúc local session.
2. Portal điều hướng browser tới OP bằng RP-Initiated Logout.
3. OP kết thúc SSO session.
4. OP thông báo cho các RP khác bằng Back-Channel Logout hoặc Front-Channel Logout.
5. Mỗi RP kết thúc đúng local session tương ứng.

**RP-Initiated Logout không tự động thực hiện Front-Channel hay Back-Channel Logout.** Nó chỉ là request từ RP tới OP. Việc OP thông báo cho các RP là năng lực riêng mà OP và các RP phải triển khai, đăng ký và kiểm thử.

### 2.1. Hai luồng phối hợp

~~~mermaid
flowchart LR
    U[Người dùng] --> P[RP khởi tạo logout]
    P -->|Browser redirect| O[OpenID Provider]
    O --> S[Kết thúc OP session]
    S --> F[Front-channel fan-out]
    S --> B[Back-channel fan-out]
    F -->|Browser iframe| R1[RP A]
    F -->|Browser iframe| R2[RP B]
    B -->|HTTP POST + Logout Token| R1
    B -->|HTTP POST + Logout Token| R2
    R1 --> L1[Invalidate local session]
    R2 --> L2[Invalidate local session]
~~~

Front-channel và back-channel là hai nhánh thông báo khác nhau. OP có thể bật một nhánh, cả hai hoặc không bật nhánh nào; metadata phải phản ánh đúng năng lực đang hoạt động.

## 3. Quyết định khi nào cần Front-Channel Logout?

Front-Channel Logout phù hợp khi:
- RP chủ yếu là browser application và local logout có thể thực hiện bằng request từ browser.
- RP không có back-channel endpoint public/reachable từ OP.
- Muốn tận dụng cookie và browser session hiện có để xóa trạng thái phía client.
- Hệ thống có ít RP, browser support đã được kiểm chứng và chấp nhận giới hạn iframe.
- Có nhu cầu thông báo cho ứng dụng legacy chỉ có HTTP logout URL.

Front-channel **không phải lựa chọn tốt duy nhất** cho yêu cầu bảo đảm logout toàn hệ thống. OP cần browser đang hoạt động và browser phải cho iframe truy cập được trạng thái của RP.

### 3.1. Metadata và client registration

RP hỗ trợ Front-Channel Logout đăng ký các metadata:
- `frontchannel_logout_uri`: URL tại RP để OP mở trong iframe.
- `frontchannel_logout_session_required`: RP có yêu cầu `iss` và `sid` để nhận diện session hay không; nếu bỏ qua, mặc định là `false`.

OP công bố trong OpenID Provider Configuration:
- `frontchannel_logout_supported`: OP có hỗ trợ Front-Channel Logout không; nếu vắng, mặc định `false`.
- `frontchannel_logout_session_supported`: OP có thể gửi `iss` và `sid` để xác định session RP hay không; nếu vắng, mặc định `false`. Nếu hỗ trợ, `sid` cũng được đưa vào ID Token.

RP logout URI phải là absolute URI, không có fragment. Scheme, host và port của URI MUST giống với scheme, host và port của một Registered Redirect URI của client theo đặc tả. Dùng HTTPS trong production.

### 3.2. OP gửi request qua iframe

Khi OP kết thúc session, OP tìm các RP đã đăng nhập rồi dựng trang có iframe trỏ tới từng `frontchannel_logout_uri`. Nếu session-aware mode được bật, OP có thể thêm cả `iss` và `sid`:

~~~http
GET /oidc/front-channel-logout?iss=https%3A%2F%2Fauth.example.com&sid=SID_VALUE HTTP/1.1
Host: portal.example.com
~~~

Nếu OP gửi một trong hai tham số `iss` hoặc `sid` thì **phải gửi cả hai**. `sid` là session identifier opaque, duy nhất trong phạm vi issuer; RP không tự diễn giải cấu trúc hoặc dùng nó làm credential.

RP có thể đối chiếu `iss` và `sid` với ID Token đã phát hành cho session hiện tại hoặc session gần đây. Nếu không khớp, RP có thể bỏ qua request.

### 3.3. RP phải làm gì tại front-channel URI?

Endpoint nhận iframe request nên:
1. Kiểm tra request thuộc route logout đã đăng ký và xử lý query parameters theo contract.
2. Nếu có `iss`/`sid`, đối chiếu với session mapping phù hợp.
3. Kết thúc session RP tương ứng hoặc toàn bộ session của subject theo policy đã thống nhất.
4. Xóa state/cookie/local storage liên quan mà RP kiểm soát.
5. Trả response có `Cache-Control: no-store`.
6. Xử lý idempotent: nếu session đã hết, coi logout đã hoàn tất.

Không yêu cầu người dùng login lại hoặc hiển thị trang xác nhận trong iframe. Cũng không trả dữ liệu cá nhân, token hoặc trang có nội dung nhạy cảm từ logout URI.

### 3.4. Giới hạn browser và cookie

Front-channel phụ thuộc browser:
- Browser có thể chặn third-party cookies trong iframe.
- Cookie `SameSite=Lax` hoặc `SameSite=Strict` có thể không được gửi trong cross-site iframe context.
- Storage partitioning có thể làm iframe không nhìn thấy state mà top-level RP đã tạo.
- Content Security Policy, frame policy và browser tracking prevention có thể chặn hoặc làm thay đổi hành vi.
- Tab/browser có thể đóng hoặc điều hướng sang nơi khác trước khi OP fan-out xong.

Vì vậy, request iframe có thể đến RP nhưng RP không đọc được cookie/session cần xóa. Đặc tả khuyến nghị có defensive handling để phát hiện trường hợp không thực hiện được logout và thông báo phù hợp khi có thể.

Không tắt CSP hoặc mở rộng cookie policy toàn cục chỉ để iframe logout chạy. Hãy đánh giá ảnh hưởng bảo mật và privacy trước khi thay đổi.

## 4. Quyết định khi nào cần Back-Channel Logout?

Back-Channel Logout phù hợp khi:
- Cần thông báo logout đáng tin cậy hơn qua browser, kể cả khi tab RP không còn mở.
- RP là server-side web application, API backend hoặc hệ thống có session store trung tâm.
- OP có thể gọi endpoint RP qua mạng.
- RP cần ánh xạ chính xác một session hoặc tất cả session của một subject.
- Browser third-party cookie blocking khiến Front-Channel không đáng tin cậy.
- Chính sách tổ chức yêu cầu server-to-server audit, retry và trạng thái xử lý.

Back-channel cũng có chi phí:
- RP phải công khai endpoint nhận thông báo từ OP.
- RP phải duy trì mapping từ OIDC identity/session tới local session.
- Logout Token phải được xác minh và chống replay.
- RP phải xử lý request trùng, retry, concurrency và distributed session invalidation.
- Endpoint phải reachable từ OP; RP sau NAT/firewall có thể cần gateway hoặc kết nối mạng riêng.

### 4.1. Metadata và client registration

RP hỗ trợ Back-Channel Logout đăng ký:
- `backchannel_logout_uri`: endpoint server-side nhận Logout Token.
- `backchannel_logout_session_required`: RP có yêu cầu Logout Token phải có `sid` hay không; mặc định `false`.

OP công bố:
- `backchannel_logout_supported`: OP hỗ trợ Back-Channel Logout hay không; mặc định `false` nếu vắng.
- `backchannel_logout_session_supported`: OP có thể gửi `sid` trong Logout Token hay không; mặc định `false` nếu vắng. Nếu hỗ trợ, `sid` cũng được đưa vào ID Token.

Logout URI phải là absolute URI, không có fragment. Nên dùng HTTPS. Với HTTP confidential client, chỉ chấp nhận nếu OP policy cho phép và phù hợp đặc tả.

### 4.2. OP ghi nhớ các RP đã đăng nhập

OP cần biết RP nào đã tham gia session để gửi notification. Có thể lưu một tập quan hệ như:

~~~text
OP session:
  issuer
  subject
  sid
  authenticated_at
  active_rp_sessions:
    - client_id
    - backchannel_logout_uri
    - frontchannel_logout_uri (optional)
    - rp_local_session_reference (nếu có)
    - registration_version
~~~

Có thể dùng visited-sites cookie, session store hoặc database. Trong hệ thống phân tán, database/session event thường dễ audit và retry hơn việc chỉ dựa vào browser cookie.

Mỗi RP phải được liên kết với đúng client registration. Không broadcast Logout Token tới tất cả URI từng xuất hiện trong request; danh sách đích phải đến từ client registration đã được tin cậy và session tracking của OP.

### 4.3. OP gửi Logout Token qua HTTP POST

OP gửi request tới `backchannel_logout_uri` đã đăng ký bằng HTTP POST với form body:

~~~http
POST /oidc/back-channel-logout HTTP/1.1
Host: portal.example.com
Content-Type: application/x-www-form-urlencoded

logout_token=SIGNED_LOGOUT_TOKEN
~~~

Body có tham số `logout_token` chứa JWT. OP có thể gửi thêm tham số khác, nhưng RP phải bỏ qua các giá trị không hiểu. Logout Token phải được ký; có thể mã hóa nếu client đã thỏa thuận encryption.

## 5. So sánh Front-Channel và Back-Channel

| Tiêu chí | Front-Channel | Back-Channel |
| --- | --- | --- |
| Kênh | Browser/iframe | Server-to-server HTTP |
| Browser phải hoạt động | Có | Không |
| Third-party cookie | Có thể ảnh hưởng mạnh | Không phụ thuộc cookie browser |
| RP cần endpoint public | URI được browser truy cập | URI OP truy cập được |
| Session lookup | Có thể dựa cookie + iss/sid | Cần mapping issuer/client/sub/sid tới local session |
| Chống giả mạo | Kiểm tra iss/sid và bảo vệ endpoint | Xác minh chữ ký/claims Logout Token |
| Retry | Khó quan sát và khó xác nhận hoàn tất | Có thể queue/retry có kiểm soát |
| Phù hợp | Web UI, legacy browser logout | Backend/server-side session, yêu cầu SLO tin cậy hơn |
| Giới hạn chính | Browser privacy/cookie policy | Reachability, state mapping, triển khai phức tạp |

### 5.1. Ma trận quyết định

| Điều kiện nghiệp vụ | Lựa chọn khuyến nghị |
| --- | --- |
| Ứng dụng chỉ là browser UI, cookie có thể được xóa trong iframe và không yêu cầu bảo đảm cao | Front-Channel có thể đủ |
| Browser privacy policy chặn third-party cookie hoặc người dùng thường đóng tab | Back-Channel |
| RP nằm sau firewall/NAT, OP public không thể gọi vào | Front-Channel hoặc private network/gateway cho Back-Channel |
| RP cần logout chính xác một thiết bị/session | Back-Channel với `sid`; Front-Channel cũng cần session-aware mapping |
| RP chỉ quản lý một session cho mỗi subject/client | Cả hai có thể phù hợp; vẫn cần identity mapping |
| Hệ thống cần audit, retry và xác nhận kết quả từng RP | Back-Channel |
| RP legacy không thể triển khai token validation nhưng có endpoint iframe đơn giản | Front-Channel, kèm đánh giá browser constraints |
| Có cả web UI và backend session store | Có thể triển khai hybrid: Back-Channel là đường chính, Front-Channel bổ trợ |

Không chọn Back-Channel chỉ vì “an toàn hơn” nếu OP không thể truy cập RP. Không chọn Front-Channel chỉ vì dễ demo nếu yêu cầu logout phải hoạt động khi browser đóng. Hãy bắt đầu từ threat model, topology, browser support, session architecture và tiêu chí hoàn tất logout.

## 6. Mô hình danh tính và session: iss, aud, sub, sid

Logout đa RP thường thất bại do mapping session không rõ ràng. Các giá trị quan trọng:

| Claim | Vai trò | Phạm vi |
| --- | --- | --- |
| `iss` | Issuer OP phát hành ID Token/Logout Token | Trust domain |
| `aud` | Client/RP nhận token | Phân biệt RP |
| `sub` | Subject identifier của End-User | Phạm vi issuer |
| `sid` | Session ID tại OP | Phạm vi issuer |
| `jti` | ID duy nhất của Logout Token | Phát hiện replay |

Không dùng `sub` một mình làm khóa toàn cục. Hai OP có thể phát cùng chuỗi subject cho hai người khác nhau. Không dùng `sid` một mình vì nó chỉ duy nhất trong phạm vi issuer. Một khóa mapping phù hợp thường là:

~~~text
session_key = (issuer, client_id, sid)
subject_key = (issuer, client_id, sub)
~~~

Nếu RP dùng pairwise subject identifiers, `sub` có thể khác theo client/sector. Vì thế mapping subject phải theo issuer và client registration cụ thể. Khi nhận Logout Token:
- Có `sid`: kết thúc các local sessions được liên kết với `(iss, aud/client, sid)`.
- Chỉ có `sub`: kết thúc tất cả local sessions của subject đó tại RP/client tương ứng.
- Có cả `sid` và `sub`: kiểm tra hai claim cùng mô tả một session/subject trước khi xử lý.

### 6.1. Một subject có nhiều session

Ví dụ cùng người dùng đăng nhập từ laptop và điện thoại:

~~~text
Issuer: https://auth.example.com
Subject: user-123

Laptop:
  sid = sid-laptop
  RP local session = rp-session-A

Phone:
  sid = sid-phone
  RP local session = rp-session-B
~~~

Logout Token có `sid=sid-laptop` chỉ kết thúc session laptop. Nếu Logout Token chỉ có `sub=user-123`, RP phải kết thúc tất cả session của subject này tại RP. Đây là khác biệt nghiệp vụ lớn: không tự đổi logout theo `sid` thành logout toàn bộ subject.

## 7. Cấu trúc và validation của Back-Channel Logout Token

Logout Token là JWT được OP ký, mang claims mô tả logout action. Nó **không phải ID Token** và không được chấp nhận trong authentication response.

### 7.1. Claims bắt buộc

| Claim | Yêu cầu | Cách kiểm tra |
| --- | --- | --- |
| `iss` | REQUIRED | Khớp chính xác issuer OP đã cấu hình |
| `aud` | REQUIRED | Chứa client ID của RP nhận thông báo |
| `iat` | REQUIRED | Thời điểm phát hành hợp lý theo clock skew/policy |
| `jti` | REQUIRED | ID token duy nhất để chống replay |
| `events` | REQUIRED | JSON object có key event back-channel logout |
| `sub` | OPTIONAL | Subject bị logout |
| `sid` | OPTIONAL | Session bị logout |
| `nonce` | PROHIBITED | Không được xuất hiện |

Logout Token **MUST** chứa ít nhất `sub` hoặc `sid`; có thể chứa cả hai. Nếu không có `sid`, ý định là kết thúc tất cả session của subject được xác định bởi `iss` và `sub` tại RP.

Event claim có key:

~~~text
http://schemas.openid.net/event/backchannel-logout
~~~

Giá trị tương ứng phải là JSON object và SHOULD là object rỗng:

~~~json
{
  "http://schemas.openid.net/event/backchannel-logout": {}
}
~~~

Logout Token MUST được ký. `typ=logout+jwt` được RECOMMENDED để tránh nhầm token này với ID Token trong các JWT validation paths khác. `alg=none` MUST NOT được sử dụng.

### 7.2. Ví dụ Logout Token

~~~json
{
  "iss": "https://auth.example.com",
  "aud": "portal-web",
  "iat": 1794800100,
  "jti": "logout-event-2b7d5f",
  "sid": "op-session-a91",
  "sub": "user-123",
  "events": {
    "http://schemas.openid.net/event/backchannel-logout": {}
  }
}
~~~

Payload trên chỉ minh họa claims. Token thực tế phải được ký bằng signing key của OP và RP phải lấy key từ trust configuration/JWKS đã xác minh. Không chấp nhận token chỉ vì payload JSON trông đúng.

### 7.3. Trình tự validation tại RP

RP phải thực hiện:
1. Nếu token được mã hóa, giải mã theo thuật toán/keys đã thỏa thuận trong client registration. Nếu RP đã thương lượng ID Token encryption với OP khi đăng ký, nhưng Logout Token không được mã hóa, RP SHOULD từ chối token.
2. Xác minh chữ ký như khi xác minh ID Token, theo allowlist algorithm.
3. Kiểm tra `iss` và `aud` theo issuer/client registration đang xử lý.
4. Kiểm tra `iat` theo policy thời gian và clock skew.
5. Xác nhận có ít nhất một trong `sub` hoặc `sid`.
6. Xác nhận `events` có event URI back-channel logout.
7. Xác nhận `nonce` không tồn tại.
8. Kiểm tra `jti` đã từng được xử lý gần đây hay chưa; nên dùng replay store dùng chung, atomic.
9. Có thể đối chiếu `iss`, `sub`, `sid` với ID Token/session hiện tại hoặc gần đây để tăng kiểm soát.
10. Chỉ sau validation thành công mới tìm và invalidate local sessions.

Nếu bất kỳ validation bắt buộc nào thất bại, từ chối token và trả HTTP 400 theo đặc tả. Không xóa session trước khi hoàn tất validation.

### 7.4. Không nhầm exp với claim bắt buộc

Back-Channel Logout Token yêu cầu `iat` và `jti`, nhưng `exp` không nằm trong danh sách required claims của Logout Token profile. RP có thể áp dụng freshness window dựa trên `iat` và clock skew để hạn chế token cũ. Nếu OP và RP thỏa thuận thêm `exp`, phải thống nhất semantics và không làm sai contract OIDC.

## 8. Xử lý logout an toàn và idempotent tại RP

Sau validation, RP tìm session:
- Ưu tiên mapping `(iss, client_id, sid)` nếu token có `sid`.
- Nếu chỉ có `sub`, tìm toàn bộ local sessions theo `(iss, client_id, sub)`.
- Không dùng email, username hoặc display name để tìm session.
- Không xóa session thuộc client khác hoặc issuer khác.

### 8.1. Idempotency và replay

Có hai khái niệm cần tách:
- **Idempotent session invalidation:** logout cùng một session nhiều lần không gây lỗi và không ảnh hưởng session khác.
- **Replay protection:** không xử lý lại cùng một Logout Token như một event mới.

RP nên lưu `jti` đã xử lý trong thời gian phù hợp với freshness window. Việc check-and-insert phải atomic để hai node không cùng chấp nhận một token replay. Nếu token hợp lệ được OP gửi lại sau lỗi mạng, RP có thể trả success khi trạng thái session đã bị xóa; nhưng vẫn ghi nhận duplicate theo policy.

### 8.2. Invalidate session đúng cách

Không chỉ xóa một row mapping rồi để HTTP session còn hoạt động. Cần:
1. Đánh dấu session mapping là logout-pending hoặc revoked.
2. Invalidate session store/session ID thực tế.
3. Xóa SecurityContext và session-associated data.
4. Thu hồi hoặc xóa refresh-token/session credentials theo policy riêng nếu cần.
5. Phát event nội bộ để các node/cache khác đồng bộ.
6. Ghi audit event không chứa raw Logout Token.

Với session distributed, phải xử lý race giữa request đang chạy và logout event. Có thể cần đánh dấu principal/session revoked để request kế tiếp bị từ chối ngay cả khi việc xóa session vật lý đang chờ.

## 9. Thiết kế OP fan-out: gửi logout tới đúng RP

OP phải duy trì quan hệ giữa session và RP đã đăng nhập. Một thiết kế có thể gồm các bảng/aggregate:

| Entity | Trường quan trọng |
| --- | --- |
| `op_session` | `issuer`, `sub`, `sid`, `created_at`, `status`, `ended_at` |
| `client_registration` | `client_id`, `backchannel_logout_uri`, `frontchannel_logout_uri`, `session_required` |
| `op_session_client` | `issuer`, `sid`, `client_id`, `rp_session_ref`, `last_authenticated_at` |
| `logout_delivery` | `event_id`, `client_id`, `target_uri`, `jti`, `attempt`, `status`, `next_attempt_at` |

Khi session OP kết thúc:
1. Trong cùng transaction, đánh dấu OP session đã kết thúc.
2. Tạo logout event/outbox record cho từng client liên kết.
3. Worker lấy delivery records và gửi notification theo kênh client đăng ký.
4. Lưu HTTP status, thời gian, attempt và error class.
5. Retry lỗi tạm thời theo exponential backoff/jitter và giới hạn số lần.
6. Đưa delivery thất bại kéo dài vào dead-letter queue để vận hành xử lý.

Không gọi tất cả RP đồng bộ trong transaction login/session logout. Một RP chậm hoặc down không nên giữ transaction session OP mở quá lâu.

### 9.1. Tạo Logout Token cho từng client

Logout Token có `aud` gắn với RP nhận. Vì vậy, OP nên tạo token theo từng client:
- `iss`: issuer của OP.
- `aud`: client ID của RP đích.
- `iat`: thời điểm phát hành.
- `jti`: ID ngẫu nhiên duy nhất cho event/token.
- `events`: back-channel logout event.
- `sid` và/hoặc `sub`: session/subject theo metadata client và session mapping.

Nếu RP đăng ký `backchannel_logout_session_required=true`, OP phải có `sid` để gửi token phù hợp; nếu không thể cung cấp sid thì không thể giả vờ hỗ trợ session-specific logout cho client đó. Nếu token chỉ có `sub`, semantics là logout mọi RP sessions của subject.

Mỗi RP nhận một token có audience riêng. Không tạo một JWT có `aud` là danh sách tất cả client nếu contract triển khai mong mỗi client xác minh audience chính xác và session isolation riêng.

Ví dụ tạo một Logout Token ký bằng RSA với Nimbus JOSE + JWT:

~~~java
String eventType =
        "http://schemas.openid.net/event/backchannel-logout";

JWTClaimsSet.Builder claims = new JWTClaimsSet.Builder()
        .issuer("https://auth.example.com")
        .audience(clientId)
        .issueTime(new Date())
        .jwtID(UUID.randomUUID().toString())
        .claim("events", Map.of(eventType, Map.of()));

if (subject != null) {
    claims.subject(subject);
}
if (sessionId != null) {
    claims.claim("sid", sessionId);
}

JWSHeader header = new JWSHeader.Builder(JWSAlgorithm.RS256)
        .type(new JOSEObjectType("logout+jwt"))
        .keyID(signingJwk.getKeyID())
        .build();

SignedJWT logoutToken = new SignedJWT(header, claims.build());
logoutToken.sign(new RSASSASigner(signingJwk.toRSAKey()));
String compactLogoutToken = logoutToken.serialize();
~~~

Đoạn code giả định `clientId`, `subject`, `sessionId` và `signingJwk` đã được lấy từ registration/session/key management đáng tin cậy. Cần từ chối trường hợp cả `subject` và `sessionId` đều null. Private key chỉ được dùng trong OP; RP xác minh bằng public key. Chọn thuật toán theo key/policy và registration thực tế, không hard-code RSA nếu OP dùng key type khác.

Mỗi token được tạo cho một client nên `aud` chỉ ra đúng RP đích. Không tái sử dụng cùng `jti` cho các client khác nhau; mỗi JWT cần ID duy nhất.

### 9.2. Delivery, retry và kết quả

| HTTP result | Cách xử lý đề xuất |
| --- | --- |
| 2xx | Đánh dấu delivered; giữ audit event |
| 400 | Token/request không hợp lệ; không retry vô hạn, cảnh báo integration |
| 401/403 | Kiểm tra endpoint authentication/network policy/client config |
| 404 | URI đăng ký sai hoặc endpoint chưa deploy; đánh dấu permanent/configuration error |
| 429 | Retry theo Retry-After/backoff |
| 5xx/network timeout | Retry có giới hạn, jitter và circuit breaker |
| Timeout sau khi RP đã xử lý | Có thể gửi lại; RP phải idempotent/replay-aware |

Back-Channel Logout spec khuyến nghị OP chỉ retransmit khi có lý do nghi ngờ lần gửi trước thất bại do lỗi có thể khôi phục, và nên trì hoãn phù hợp để không làm quá tải RP.

### 9.3. Hybrid fan-out

Nếu OP hỗ trợ cả hai:
- Back-channel gửi notification server-to-server là nguồn chính.
- Front-channel có thể giúp browser UI/local storage xóa nhanh hơn.
- RP phải xử lý cùng một session logout đến từ hai kênh mà không xóa nhầm hoặc báo lỗi.
- Cả hai đường phải có audit correlation và trạng thái hoàn tất riêng.
- Không giả định front-channel thành công nếu back-channel thất bại hoặc ngược lại.

## 10. Hỗ trợ trong Spring Security và Spring Authorization Server

Phải phân biệt **RP nhận logout** và **OP phát logout**. Đây là hai vai trò khác nhau.

### 10.1. Spring Security: RP hỗ trợ Back-Channel Logout

Tài liệu Spring Security 7.1.x cung cấp DSL `oidcLogout(...).backChannel(...)` cho ứng dụng OAuth2 Login làm RP. Spring Security có:
- `OidcBackChannelLogoutHandler` để xử lý session invalidation theo OIDC Back-Channel Logout.
- `OidcSessionRegistry` để liên kết ID Token/`sid`/`sub` với local session.
- Endpoint mặc định dạng `/logout/connect/back-channel/{registrationId}`.
- `HttpSessionEventPublisher` để dọn các `OidcSessionInformation` khi session bị invalidate.

Ví dụ:

~~~java
@Bean
OidcBackChannelLogoutHandler oidcBackChannelLogoutHandler() {
    return new OidcBackChannelLogoutHandler();
}

@Bean
HttpSessionEventPublisher sessionEventPublisher() {
    return new HttpSessionEventPublisher();
}

@Bean
SecurityFilterChain rpSecurityFilterChain(HttpSecurity http) throws Exception {
    http
        .authorizeHttpRequests(authorize -> authorize
            .anyRequest().authenticated()
        )
        .oauth2Login(Customizer.withDefaults())
        .oidcLogout(oidc -> oidc
            .backChannel(Customizer.withDefaults())
        );
    return http.build();
}
~~~

Đây là cấu hình phía **RP**. `oidcLogout` yêu cầu `oauth2Login` cũng được cấu hình. Cần kiểm tra cookie name và session store theo version; cấu hình mặc định của Spring Security dùng `JSESSIONID` để correlate local session. Nếu dùng Spring Session với cookie `SESSION`, cần cấu hình `OidcBackChannelLogoutHandler.setSessionCookieName("SESSION")` hoặc thiết lập tương ứng của version đang dùng.

Spring Security thực hiện validation Logout Token và tìm session theo `sid`; nếu không có sid thì có thể kết thúc các session của subject cho client tương ứng. Hãy xác minh behavior của dependency version đang chạy và đọc `OidcSessionRegistry` lifecycle trong môi trường cluster.

### 10.2. Spring Security: OP logout không phải RP back-channel receiver

`OidcBackChannelLogoutHandler` được dùng ở ứng dụng RP nhận notification. Nó không tự biến ứng dụng thành OP và không tự gửi Logout Token tới các RP khác.

Nếu ứng dụng chỉ dùng `oauth2Login` và `oidcLogout`, nó vẫn cần một OP riêng để phát notification. Đừng lấy endpoint receiver của RP làm endpoint fan-out ở Authorization Server.

### 10.3. Spring Authorization Server: RP-Initiated Logout và ranh giới hiện tại

Trong Spring Authorization Server 1.5.x, `OidcLogoutEndpointConfigurer` cấu hình OIDC RP-Initiated Logout Endpoint. Các extension point gồm converter, authentication provider, logout response handler và error handler; provider dùng `SessionRegistry` để tìm session cần kết thúc.

Tài liệu Protocol Endpoints của SAS 1.5.8 mô tả `OidcLogoutEndpointConfigurer` cho RP-Initiated Logout. Tài liệu đó không liệt kê configurer/endpoint hoàn chỉnh để OP tự fan-out Front-Channel hoặc Back-Channel Logout. Do đó, không được giả định rằng bật `oidc(...).logoutEndpoint(...)` đồng nghĩa OP đã:
- Ghi nhớ toàn bộ RP đã đăng nhập theo từng OP session.
- Công bố đầy đủ frontchannel/backchannel metadata.
- Lưu `sid` nhất quán trong ID Token/session.
- Tạo Logout Token theo từng audience.
- Gửi notification, retry và theo dõi kết quả tới các RP.

Với SAS 1.5.x, nếu yêu cầu OP fan-out, cần thiết kế extension/integration riêng hoặc dùng một OP có hỗ trợ đầy đủ feature đó. Đối chiếu tài liệu/version thực tế trước khi cam kết khả năng.

### 10.4. Những thành phần cần mở rộng ở OP

Một thiết kế mở rộng thường có:

| Thành phần | Trách nhiệm |
| --- | --- |
| `Session correlation service` | Gắn OP session, `sid`, `sub`, client và RP sessions |
| `Client logout metadata registry` | Lưu backchannel/frontchannel URI và flags đã đăng ký |
| `ID Token customizer` | Phát hành `sid` khi OP quảng cáo session-specific logout |
| `Logout event publisher` | Phát event khi OP session kết thúc |
| `Logout Token issuer` | Tạo và ký token theo client audience |
| `Fan-out dispatcher` | Gửi POST tới backchannel URI, quản lý retry |
| `Front-channel page renderer` | Tạo iframe tới các frontchannel URI đã đăng ký |
| `Delivery/outbox store` | Theo dõi attempt, status, next retry và audit |
| `Revocation/session policy` | Quyết định refresh token/authorization nào bị thu hồi cùng logout |

Không nên đặt toàn bộ trách nhiệm này vào một `LogoutSuccessHandler` đồng bộ. Nên phát event/outbox từ transaction kết thúc OP session rồi để dispatcher xử lý độc lập.

## 11. Ví dụ kiến trúc end-to-end với hai RP

Giả sử có:
- Portal web dùng Spring Security OAuth2 Login.
- Admin Console dùng Spring Security OAuth2 Login.
- OP dùng Spring Authorization Server 1.5.x và một module fan-out tự xây.
- Cả hai RP công bố Back-Channel Logout URI; Portal cũng hỗ trợ Front-Channel.

~~~mermaid
sequenceDiagram
    autonumber
    participant P as Portal RP
    participant O as OP / Spring Authorization Server
    participant D as Logout Dispatcher
    participant A as Admin RP
    P->>O: RP-Initiated Logout (id_token_hint)
    O->>O: Validate hint, end OP session
    O->>O: Persist logout event + recipients
    O-->>P: Post-logout redirect
    O->>D: Outbox event
    par Back-channel delivery
        D->>P: POST logout_token (aud=portal)
        P->>P: Validate JWT, map sid, invalidate session
        D->>A: POST logout_token (aud=admin)
        A->>A: Validate JWT, map sid, invalidate session
    and Optional front-channel
        O-->>P: Browser iframe frontchannel_logout_uri
    end
~~~

Từng RP nhận Logout Token riêng có `aud` tương ứng. Nếu Portal đã local logout trước, notification sau đó vẫn phải được xử lý idempotent. Nếu Admin RP có nhiều session của cùng subject, `sid` xác định session cụ thể; nếu chỉ có `sub` thì toàn bộ session của subject tại Admin RP bị kết thúc.

## 12. Bảo mật, privacy và vận hành

### 12.1. Front-channel endpoint

- Không cho request front-channel xóa session tùy ý dựa trên `sub`/`sid` không được xác minh.
- Nếu nhận `iss` và `sid`, kiểm tra cả hai và map theo issuer.
- Xử lý idempotent và trả `Cache-Control: no-store`.
- Không yêu cầu browser third-party cookie được bật như điều kiện duy nhất để đảm bảo logout.
- Giới hạn response content, không render dữ liệu người dùng hoặc script không cần thiết.
- Kiểm tra CSP/frame behavior và tránh mở frame policy toàn cục.

### 12.2. Back-channel endpoint

- Chỉ chấp nhận POST form với `logout_token` theo contract.
- Xác minh JWT signature bằng key OP tin cậy; không lấy `jku`/`x5u` tùy ý từ token để tải key.
- Kiểm tra `iss`, `aud`, `iat`, `jti`, `events`, `sub`/`sid` và absence của `nonce`.
- Dùng allowlist signing algorithms; từ chối `none`.
- Replay store phải atomic và dùng chung giữa các node.
- Có giới hạn kích thước request, timeout, rate limit và audit.
- Có thể bổ sung mTLS/network allowlist giữa OP và RP như lớp bảo vệ transport; nó không thay validation Logout Token.
- Không ghi raw Logout Token vào access log hoặc tracing.

### 12.3. Session và tenant isolation

Mọi mapping phải giữ issuer/client context:
- Không xóa mọi session chỉ vì `sub` trùng chuỗi giữa hai issuer.
- Không xử lý Logout Token có `aud` không chứa client ID của registration hiện tại.
- Không dùng email hoặc username để xác định session.
- Không dùng `sid` từ issuer khác.
- Nếu subject pairwise khác theo client, mapping phải giữ đúng client/sector context.
- Khi tenant/client registration bị xóa, cleanup mapping và delivery records theo policy.

### 12.4. Audit và privacy

Nên ghi:
- Issuer, client ID, session correlation ID nội bộ.
- Kênh logout và thời điểm nhận/gửi.
- Kết quả validation, session count bị invalidate.
- Delivery attempt, HTTP result, retry count và terminal status.

Không ghi raw token, cookie, access token, refresh token hoặc PII không cần thiết. `sub`/`sid` cũng là identifier nhạy cảm; có thể hash/pseudonymize trong log vận hành và giữ mapping trong kho audit được kiểm soát.

### 12.5. Logout không thay thế token revocation

Back-channel logout kết thúc RP session. Nó không tự động làm access token JWT đã phát hành mất hiệu lực tại mọi Resource Server. Nếu cần ngăn API tiếp tục chấp nhận token:
- Thu hồi refresh token/authorization tương ứng theo policy.
- Dùng access token lifetime ngắn.
- Dùng introspection hoặc revocation-aware validation khi cần.
- Có cơ chế truyền trạng thái thu hồi tới Resource Server.
- Kiểm thử riêng hành vi token sau logout.

## 13. Ma trận kiểm thử Front-Channel

| Tình huống | Kết quả mong đợi |
| --- | --- |
| OP gọi frontchannel URI trong iframe | RP kết thúc session theo policy |
| Có cả `iss` và `sid` đúng | Chỉ kết thúc session tương ứng |
| Chỉ có `iss` hoặc chỉ có `sid` | Request không hợp lệ theo contract; không đoán session |
| `iss` không đúng OP | Bỏ qua/từ chối request |
| `sid` không map tới local session | Idempotent; không xóa session khác |
| Session đã logout | Coi là thành công, không lỗi nghiêm trọng |
| Third-party cookie bị chặn | Phát hiện không thể correlate; không báo logout toàn cục thành công giả |
| Cache proxy/browser | Response `Cache-Control: no-store` |
| Request lặp | Không xóa nhầm session mới tạo sau session cũ |
| URL có fragment hoặc origin không khớp | Registration bị từ chối |

## 14. Ma trận kiểm thử Back-Channel

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Token chữ ký hợp lệ, iss/aud đúng | Tiếp tục kiểm tra claims và session |
| Chữ ký sai hoặc key không tin cậy | HTTP 400, không xóa session |
| `alg=none` | Từ chối |
| `iss` sai | Từ chối |
| `aud` không chứa client ID hiện tại | Từ chối |
| Thiếu `iat`, `jti` hoặc `events` | Từ chối |
| Không có cả `sub` lẫn `sid` | Từ chối |
| Có `nonce` | Từ chối |
| Event URI sai | Từ chối |
| `sid` đúng | Chỉ invalidate session map với sid đó |
| Chỉ có `sub` | Invalidate tất cả local sessions của subject cho client đó |
| `sub` và `sid` không nhất quán | Không xóa session; audit và xử lý theo validation policy |
| `jti` đã xử lý | Không thực thi lại event; phản hồi theo idempotency contract |
| Hai node nhận cùng token đồng thời | Replay store atomic, tối đa một lần xử lý logic |
| Local session đã bị xóa | Xử lý idempotent |
| RP session cookie là `SESSION` | Handler/registry được cấu hình đúng, không giả định `JSESSIONID` |
| OP timeout sau khi RP đã xử lý | Retry không gây xóa session khác |
| Logout Token quá cũ | Từ chối theo freshness policy |
| Request body quá lớn | Từ chối trước khi parse JWT tốn tài nguyên |

## 15. Ma trận kiểm thử OP fan-out và vận hành

| Tình huống | Kết quả mong đợi |
| --- | --- |
| OP session kết thúc | Tạo outbox event trong transaction |
| Một session có nhiều RP | Gửi đúng URI theo registration của từng RP |
| Client yêu cầu sid nhưng OP không có sid | Không gửi token sai contract; ghi capability/config error |
| Mỗi RP nhận token | `aud` khớp đúng client đích |
| RP trả 2xx | Delivery thành công |
| RP trả 5xx/timeout | Retry có backoff/jitter và giới hạn |
| RP trả 400 | Đánh dấu lỗi token/contract; không retry vô hạn |
| Worker restart | Outbox tiếp tục xử lý, không mất event |
| Hai dispatcher cùng claim event | Lock/lease hoặc optimistic concurrency tránh gửi trùng không kiểm soát |
| Front + Back channel cùng tới | RP xử lý idempotent |
| OP signing key rotation | RP xác minh được token trong giai đoạn overlap theo JWKS policy |
| Client registration bị thu hồi | Không tiếp tục gửi notification tới URI không còn tin cậy |
| RP URI bị thay đổi | Delivery chỉ dùng metadata registration mới đã xác thực |
| User có nhiều tenant/issuer | Không fan-out chéo trust domain |
| Audit query | Có thể truy vết delivery theo event/client mà không lộ raw token |

## 16. Bài tập tình huống

Một doanh nghiệp có OP và ba ứng dụng:
- Portal web dùng Spring Security session.
- Admin Console dùng Spring Session với cookie `SESSION`.
- Mobile API dùng access token, không giữ browser session.

Người dùng đăng nhập trên cả ba ứng dụng. OP kết thúc SSO session do quản trị viên khóa tài khoản. Yêu cầu:
- Portal và Admin Console phải kết thúc local session ngay cả khi browser tab đóng.
- Mobile API phải từ chối token theo policy thu hồi.
- Hệ thống cần audit từng ứng dụng đã nhận logout.
- OP đang dùng Spring Authorization Server 1.5.x.

Hãy phân tích:

1. Front-Channel có đáp ứng yêu cầu browser tab đóng hay không?
2. Back-Channel phù hợp ở điểm nào và điều kiện network nào phải có?
3. Spring Security cấu hình Back-Channel receiver cho Portal/Admin Console ra sao?
4. Vì sao Admin Console cần kiểm tra session cookie name `SESSION`?
5. OP cần lưu mapping nào để gửi Logout Token tới đúng client?
6. Token cho Portal và Admin Console cần có `aud` như thế nào?
7. Mobile API không có local web session thì cần cơ chế gì để token bị từ chối?
8. Vì sao bật `OidcLogoutEndpointConfigurer` của SAS không tự hoàn thành OP fan-out?
9. Thiết kế outbox/retry như thế nào để một RP down không ngăn logout các RP khác?
10. Đề xuất test cho `sid` logout một session và `sub` logout tất cả session.

**Gợi ý:** Back-Channel là kênh chính cho yêu cầu khi browser đóng. Spring Security có receiver ở phía RP, nhưng OP phải có session/RP registry và dispatcher riêng nếu SAS version không cung cấp sender/fan-out tương ứng. Admin dùng Spring Session cần cấu hình cookie correlation. Mobile API cần token revocation/introspection hoặc policy kiểm tra trạng thái token; Logout Token không tự thu hồi access token tại Resource Server.

## 17. Checklist triển khai production

1. **Requirement:** định nghĩa logout cần kết thúc session nào, trên RP nào, trong bao lâu.
2. **Mechanism:** chọn Front-Channel, Back-Channel hoặc hybrid dựa browser, network và assurance.
3. **Metadata:** công bố đúng `frontchannel_logout_supported`, `backchannel_logout_supported` và session-supported flags.
4. **Client registration:** lưu URI logout và session-required flags theo từng client; xác minh URI trước khi dùng.
5. **Session model:** phát hành `sid` khi quảng cáo session-specific logout; lưu mapping issuer/client/sub/sid.
6. **Logout Token:** ký theo OP key, audience riêng từng RP, có iss/aud/iat/jti/events và sub/sid phù hợp; không có nonce.
7. **RP validation:** xác minh signature/alg/issuer/audience/time/event/sub-or-sid trước khi invalidate.
8. **Replay:** lưu jti atomic/distributed; xử lý duplicate và retry idempotent.
9. **Spring Security RP:** bật `.oidcLogout(...).backChannel(...)` đúng version, có `oauth2Login`, registry và session event cleanup.
10. **Cookie/session store:** kiểm tra `JSESSIONID` hay `SESSION`, Spring Session, cluster và session invalidation thực tế.
11. **SAS OP:** phân biệt RP-Initiated Logout Endpoint với OP fan-out; thiết kế phần mở rộng nếu cần.
12. **Delivery:** dùng outbox/queue, parallel dispatch, retry có backoff, dead-letter và dashboard.
13. **Front-channel:** kiểm tra iframe, SameSite, third-party cookies, CSP, no-store và fallback.
14. **Token lifecycle:** thiết kế revoke/introspection riêng nếu access token phải mất hiệu lực sau logout.
15. **Security:** không dùng email/username thay subject; kiểm tra issuer/client/tenant isolation.
16. **Observability:** theo dõi delivery success/failure, latency, retry, duplicate và số session đã invalidate.
17. **Testing:** chạy unit, integration và end-to-end qua browser/ingress/multi-node; thử network outage và key rotation.
18. **Incident response:** có khả năng force logout, rotate signing keys, revoke token và xử lý client registration bị compromise.

## 18. Tài liệu chuẩn và Spring cần đối chiếu

- [OpenID Connect Front-Channel Logout 1.0](https://openid.net/specs/openid-connect-frontchannel-1_0.html): `frontchannel_logout_uri`, `iss`, `sid`, iframe behavior, metadata và browser limitations.
- [OpenID Connect Back-Channel Logout 1.0](https://openid.net/specs/openid-connect-backchannel-1_0-final.html): client registration, Logout Token, validation, delivery và session logout actions.
- [OpenID Connect RP-Initiated Logout 1.0](https://openid.net/specs/openid-connect-rpinitiated-1_0.html): cơ chế RP yêu cầu OP kết thúc session.
- [OpenID Connect Session Management 1.0](https://openid.net/specs/openid-connect-session-1_0.html): session state qua browser.
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519.html): cấu trúc JWT, `iss`, `aud`, `iat`, `jti`.
- [Spring Security 7.1 — OIDC Logout](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/logout.html): RP-Initiated và Back-Channel Logout receiver, `OidcBackChannelLogoutHandler`, `OidcSessionRegistry`.
- [Spring Authorization Server 1.5 — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html): `OidcLogoutEndpointConfigurer` cho RP-Initiated Logout và các extension point của endpoint.
- [Spring Authorization Server — Core Model Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): session tracking và `SessionRegistry`.

**Ghi nhớ:** Front-Channel Logout dùng browser/iframe nên dễ tích hợp với web UI nhưng phụ thuộc third-party cookie, browser state và iframe policy. Back-Channel Logout dùng HTTP POST cùng Logout Token đã ký nên phù hợp hơn với server-side session và yêu cầu logout khi browser không hoạt động, nhưng cần endpoint reachable, session mapping, token validation, replay protection và delivery/retry. Spring Security 7.1.x cung cấp Back-Channel receiver cho RP; Spring Authorization Server 1.5.x có RP-Initiated Logout Endpoint, còn OP fan-out Front/Back-Channel cần kiểm tra version và thường phải bổ sung session/RP registry, Logout Token issuer, dispatcher và delivery tracking. Chọn cơ chế theo yêu cầu thực tế, không công bố capability chưa triển khai và không nhầm logout session với token revocation.
