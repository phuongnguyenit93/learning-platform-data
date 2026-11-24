# Logout khi token bị nghi lộ

Một nhân viên phát hiện đường dẫn debug chứa **access token** bị ghi vào hệ thống log có nhiều người xem được. Hoặc một ứng dụng mobile thông báo thiết bị bị mất, còn đăng nhập và có **refresh token**. Người dùng bấm nút **Đăng xuất** trên một trình duyệt khác. Liệu như vậy đã chặn được bên đang giữ bản sao token?

**Không thể mặc định là đã chặn.** Logout local thường chỉ làm mất phiên và credentials mà **thiết bị đang thao tác** giữ. Kẻ tấn công có thể tiếp tục dùng bản sao **Bearer access token** trong thời hạn và phạm vi token còn hiệu lực. Nếu có **refresh token**, người giữ token có thể xin access token mới cho đến khi refresh token hoặc grant bị vô hiệu. Nếu hệ thống dùng JWT tự chứa không kiểm trạng thái thu hồi, ngay cả khi authorization server (AS) đã ghi nhận logout, resource server (RS) vẫn có thể chấp nhận access token cũ tới `exp`.

Vì vậy **logout khi token bị nghi lộ** là một phần của **quy trình ứng phó credential compromise**, không chỉ thao tác dọn giao diện. Mục tiêu là **giới hạn tổn thất, chặn sử dụng tiếp, khôi phục phiên an toàn, xác minh hiệu lực thu hồi và điều tra nguyên nhân**, đồng thời không làm vô hiệu quá rộng các phiên/tài khoản không liên quan.

Bài thuộc chương **Logout** của module `SECURITY_TOKEN_SECURITY_FUNDAMENTALS`. Nội dung kết nối mô hình tin cậy và vòng đời **JWT, opaque token, access token, refresh token, ID token**, các claims `iss`, `aud`, `scope`, `jti`, quy trình OAuth 2.0/OIDC, lưu trữ token, revocation, chống replay, Java/Spring Security, tình huống vận hành và kiểm thử.

## 1. Phân biệt “nghi lộ” với “đã xác nhận bị lạm dụng”

**Nghi lộ (suspected compromise):** Có dấu hiệu token/secret có thể đã đi vào nơi không an toàn, nhưng chưa xác nhận bị người khác sử dụng.

Ví dụ:

- Một token xuất hiện trong log, error report hoặc đoạn chat hỗ trợ.
- Một thiết bị có session đang mở bị mất.
- Browser extension hoặc script lạ có khả năng đọc token trong storage.
- Repository hoặc CI artifact từng chứa credential.
- Refresh token rotation phát hiện một token cũ bị dùng lại.
- API thấy bearer token từ vị trí/thiết bị bất thường.

**Đã xác nhận lạm dụng (confirmed misuse):** Có bằng chứng token bị dùng trái phép, ví dụ các API calls, token refresh hoặc thay đổi dữ liệu không do chủ thể thực hiện.

Không cần chờ đến khi xác nhận mất tiền/dữ liệu mới hành động. **Biện pháp containment có thể được kích hoạt theo mức độ rủi ro**, nhưng phạm vi phải được ghi rõ và tránh gây outage lớn không cần thiết.

### Ba nguyên tắc đầu tiên

1. **Coi bản sao token có khả năng vẫn tồn tại ở ngoài client.** Xóa storage hiện tại không xóa bản sao trong log, bộ nhớ attacker hay proxy.
2. **Chặn khả năng tái phát hành token**, đặc biệt refresh token family/grant và session cho phép silent login.
3. **Xác minh tài nguyên bảo vệ đã thực sự từ chối token nghi lộ**, không chỉ xác nhận nút Logout đã trả HTTP 200.

## 2. Mô hình tin cậy và những bên phải phối hợp

| Thành phần | Trách nhiệm khi nghi lộ |
|---|---|
| **Client / Relying Party (RP)** | Dừng dùng credentials, invalidate local session, xóa storage/cache, cancel refresh jobs, yêu cầu reauthentication. |
| **Authorization Server (AS)** | Xác định token/grant, thu hồi refresh/access tokens theo khả năng, khóa reuse, phát audit và quản lý client/subject sessions. |
| **OpenID Provider (OP)** | Quản lý phiên SSO; kết thúc OP session theo OIDC logout flow nếu rủi ro liên quan authentication session. |
| **Resource Server (RS)** | Thực thi revoke/status, `aud`/`scope`/token type, từ chối token hết hạn hoặc bị chặn, kiểm tra truy cập dữ liệu. |
| **Security/operations** | Xác minh nguồn rò, phạm vi, thời gian, tokens/grants liên quan, cập nhật chính sách và thông báo phù hợp. |
| **Người dùng/admin** | Kích hoạt report, xác nhận thao tác bảo mật hoặc reauthentication qua kênh tin cậy khi cần. |

```mermaid
flowchart TD
    SIGNAL[Phát hiện token nghi lộ] --> TRIAGE{Loại credential và mức độ ảnh hưởng?}
    TRIAGE --> LOCAL[Invalidate local session / device state]
    TRIAGE --> AS[AS: revoke token / refresh family / grant]
    TRIAGE --> OP[OP: kết thúc SSO session nếu cần]
    AS --> RS[RS: enforce denylist / introspection / status]
    LOCAL --> REAUTH[Yêu cầu tái xác thực an toàn]
    OP --> REAUTH
    RS --> VERIFY[Kiểm thử token cũ bị từ chối]
    REAUTH --> VERIFY
    VERIFY --> ROOT[Điều tra nguồn rò, audit, khắc phục]
    ROOT --> CLOSE{Xác minh hết nguy cơ trọng yếu?}
    CLOSE -- Chưa --> TRIAGE
    CLOSE -- Rồi --> DONE[Đóng incident theo chính sách]
```

**Không phải mọi vụ lộ access token đều cần logout toàn bộ SSO của người dùng**, nhưng nếu token leak đi kèm session hijacking, malware, hoặc nhiều credentials bị rò, xử lý chỉ một access token là chưa đủ.

## 3. Phân loại credential trước khi chọn hành động

| Credential bị nghi lộ | Có thể bị lạm dụng để làm gì? | Xử lý ưu tiên |
|---|---|---|
| **Bearer access token** | Gọi RS trong `aud`/`scope` khi token còn hiệu lực. | Thu hồi/chặn token tại AS/RS; xác định `exp` và blast radius. |
| **Refresh token** | Xin access token mới, có thể kéo dài truy cập. | Revoke refresh token **và family/grant liên quan theo policy**, chặn rotation race; xử lý token đã phát. |
| **RP session cookie** | Mạo danh session ứng dụng nếu server còn chấp nhận. | Invalidate **server-side session**, clear cookie, chống session fixation; xem xét refresh/access tokens trong session. |
| **OP/SSO session** | Khởi tạo authentication mới không cần mật khẩu theo OP policy. | Terminate OP session(s), SLO nếu cần; không giả định token revoke. |
| **OIDC ID token** | Lộ claims danh tính, hỗ trợ nhầm token/login nếu RP validation sai. | Xác định PII/transaction impact; chống token substitution; logout RP/OP nếu session liên quan; **không coi ID token là API access token**. |
| **Client secret** | Xác thực confidential client, có thể xin tokens theo grant được phép. | Rotate/revoke secret, audit mọi grants của client, xử lý workload rollout; logout user chưa chắc giải quyết. |
| **DPoP private key / mTLS private key** | Có thể dùng token bị ràng buộc với key nếu attacker cũng có token. | Thu hồi/rotate key, certificates và bound tokens; kiểm proof/cert tại RS. |
| **Authorization code / device code** | Hoàn tất một giao dịch chưa kết thúc trong điều kiện phù hợp. | Hủy giao dịch, enforce PKCE/client binding/TTL/one-time; không chỉ xóa access token. |

**Loại token và đối tượng đã bị lộ quyết định phạm vi logout.** Token sở hữu bởi client credentials grant không đại diện user session; revoke client credential không có nghĩa phải đăng xuất tất cả người dùng.

## 4. Tín hiệu nào là bằng chứng đủ để containment?

Không chỉ dựa vào địa chỉ IP thay đổi, vì VPN/mobile/NAT có thể tạo false positive. Cần kết hợp:

| Tín hiệu | Giá trị | Giới hạn |
|---|---|---|
| Token được ghi nguyên trong log bên ngoài boundary. | Có con đường lộ credential cụ thể. | Chưa chứng minh có ai đọc log. |
| Refresh token reuse sau rotation. | Có thể chứng tỏ token cũ bị phát lại. | Race/retry hợp pháp cũng cần được phân biệt. |
| Cùng token xuất hiện từ hai môi trường bất thường gần nhau. | Tăng mức nghi vấn token copy. | NAT, shared proxy hoặc roaming làm nhiễu. |
| User báo mất thiết bị đã đăng nhập. | Phơi bày local session/token/key có thể có. | Storage encryption và device lock ảnh hưởng xác suất lộ. |
| Token xuất hiện trong URL/Referer. | Có thể rò qua analytics, web server, third-party. | Xác định phạm vi log/tracing cần điều tra. |
| Client secret bị commit vào repository. | Có dấu vết lộ credential. | Cần kiểm repo visibility, forks, CI logs, artifacts. |
| API operations bất thường sau thời điểm leak. | Có thể là misuse đã xảy ra. | Cần so với business activity hợp pháp. |

**Phản ứng theo mức độ:** trường hợp token ngắn hạn và chỉ có bản sao trong vùng kiểm soát nội bộ khác với refresh token lâu dài bị công bố công khai. Dù vậy, **không dùng “chưa thấy API call lạ” để kết luận token chưa bị lấy**.

## 5. Bốn mục tiêu riêng trong logout khi nghi lộ

1. **Ngừng sử dụng phiên hiện tại** — local logout và cleanup.
2. **Ngừng khả năng tạo phiên mới qua SSO** — OP session logout/reauthentication khi cần.
3. **Ngừng cấp access token mới** — revoke refresh token/grant/credential.
4. **Ngừng RS chấp nhận access token cũ** — enforce revocation/status/denylist/expiration.

| Biện pháp | Local session | OP SSO | Refresh/access issuance | Access token đã phát |
|---|---|---|---|---|
| Local logout | Có | Không mặc định | Không mặc định | Không mặc định |
| OIDC RP-Initiated Logout | RP nên cleanup | Có theo OP policy | Không mặc định | Không mặc định |
| Revoke refresh token/grant | Không tự | Không tự | Có theo revocation policy | Cần xét riêng |
| Revoke access token tại AS | Không tự | Không tự | Chỉ token được xử lý | Cần RS enforcement |
| RS denylist/status | Không tự | Không tự | Không thay token issuance | Có tại RS được cấu hình |
| Global logout có phối hợp | Theo mục tiêu | Theo mục tiêu | Theo mục tiêu | Tùy cơ chế thực thi |

**Không gắn một trạng thái “LOGGED_OUT” chung cho tất cả các lớp**, vì một phần có thể thành công, phần khác timeout hoặc chưa được tích hợp.

## 6. Thứ tự ứng phó đề xuất: contain trước, điều tra sau

Một runbook cho vụ nghi lộ có thể bắt đầu:

1. **Tiếp nhận tín hiệu** và tạo incident ID; tránh yêu cầu người dùng gửi token nguyên bản.
2. **Phân loại credential** và định danh issuer/client/grant/token reference qua nguồn nội bộ đáng tin.
3. **Chọn phạm vi containment nhỏ nhất nhưng đủ an toàn**: token đơn lẻ, grant/family, một thiết bị, một user, một client hay toàn tenant.
4. **Chặn issuance/replay:** revoke grant/refresh family, invalidate session và dùng denylist/status tại RS khi cần.
5. **Chặn local tiếp tục sử dụng credential:** hủy refresh jobs, clear state, logout app.
6. **Kết thúc OP SSO session** nếu dấu hiệu cho thấy phiên SSO cũng không đáng tin.
7. **Xác minh kết quả ở RS/token endpoint**, không chỉ ở UI.
8. **Tái xác thực qua kênh đáng tin**; cấp phiên/credentials mới với key/secret rotation nếu cần.
9. **Khoanh vùng và khắc phục đường lộ**, audit tài nguyên bị truy cập, thông báo theo policy.
10. **Đóng incident** sau khi xác nhận các kênh replay trọng yếu đã được kiểm soát.

Không nên trì hoãn containment chỉ để thu thập toàn bộ chứng cứ. Đồng thời, **cần giữ bằng chứng tối thiểu đã được sanitize** trước khi xóa nguồn rò, theo quy trình điều tra và retention.

### Đường đi mẫu: lộ refresh token trong mobile

```mermaid
sequenceDiagram
    autonumber
    actor U as Người dùng
    participant APP as Mobile client
    participant AS as Authorization Server
    participant RS as Resource Server
    participant SOC as Security / Incident Service
    U->>APP: Báo mất thiết bị / nghi lộ token
    APP->>SOC: Gửi incident reference, không gửi raw token vào log
    SOC->>AS: Revoke refresh family / grant theo policy
    AS->>AS: Mark revoked, block refresh reuse
    SOC->>RS: Sync denylist/grant status nếu cần revoke access sớm
    APP->>APP: Clear local credentials, cancel jobs, invalidate app session
    SOC->>AS: Xem xét OP SSO logout / global sessions
    SOC->>RS: Kiểm token nghi lộ không còn truy cập được
    SOC-->>U: Yêu cầu reauthentication và báo phạm vi hoàn thành
```

Luồng này **không đòi mobile app bị mất phải trực tiếp gửi request revoke**; chủ thể có thể dùng một thiết bị an toàn khác và backend/AS hỗ trợ quản lý grants/sessions.

## 7. Logout local: cần làm nhưng chưa đủ

Ở RP, local logout bao gồm:

- Invalidate server session hiện hành.
- Clear authentication/SecurityContext.
- Xóa local cookies đúng Domain/Path và các token entries theo ownership.
- Hủy outstanding requests, background refresh/sync và UI authenticated state.
- Xóa hoặc chặn credential cache thuộc session.
- Đặt **generation/version** để response cũ không tạo lại session.
- Tránh đưa raw credentials vào redirect URLs, logs hoặc telemetry.

**Xóa cookie không thay invalidate session tại server.** Nếu attacker đã lấy cookie cũ và backend vẫn chấp nhận, logout ở browser không đủ.

### Nếu token bị lộ đã tồn tại ở nơi khác

```text
T0: Access token T được phát, exp = T0 + 15 phút.
T1: Bản sao T bị ghi vào logs/đọc bởi attacker.
T2: User logout local: client xóa T khỏi memory.
T3: Attacker dùng bản sao T tại Orders API.
T4: Nếu RS chưa biết revocation, request có thể vẫn thành công.
```

Để ngăn T3, cần **RS token validation và revoke enforcement**; không được dựa vào trạng thái UI của RP.

## 8. Logout OP/AS SSO khi nào là cần thiết?

Nếu nghi **SSO session cookie**, session fixation, browser compromise hoặc kẻ có thể tạo authentication mới qua phiên OP còn sống, local logout ở RP không đủ.

OIDC **RP-Initiated Logout 1.0** cho phép RP yêu cầu OP kết thúc authentication session bằng `end_session_endpoint` (nếu OP hỗ trợ) cùng các tham số như `id_token_hint`, `post_logout_redirect_uri`, `state` theo hợp đồng.

```http
GET /connect/logout?id_token_hint=ID_TOKEN_HINT_PLACEHOLDER&post_logout_redirect_uri=https%3A%2F%2Fapp.example.test%2Flogged-out&state=LOGOUT_STATE_PLACEHOLDER HTTP/1.1
Host: id.example.test
```

**Chỉ gửi hint đến OP đã tin cậy.** OP logout có thể tác động nhiều RP dùng chung SSO, nhưng **không mặc định vô hiệu access/refresh tokens đã cấp**. Trong sự cố token leak, thường cần kết hợp revoke token/grant.

**Logout OP không phải “logout tất cả thiết bị” theo chuẩn chung.** Việc ngắt tất cả OP sessions của cùng subject cần tính năng/session management riêng của provider.

## 9. Access token bị nghi lộ: JWT và opaque khác nhau

### Opaque access token

RS có thể gọi **RFC 7662 Token Introspection**. Sau khi AS revoke token, response có thể là:

```json
{"active": false}
```

Nhưng **introspection cache** tại RS có thể còn giữ kết quả `active=true` trong một khoảng thời gian. Cần tính **revocation latency budget**.

### JWT access token tự chứa

Một JWT access token có payload minh họa:

```json
{
  "iss": "https://id.example.test",
  "sub": "user-123",
  "aud": "orders-api",
  "scope": "orders.read",
  "jti": "reference-abc",
  "iat": 1795410000,
  "exp": 1795410900
}
```

Đây là payload ví dụ, **không phải JWT được ký**. RS có thể xác minh chữ ký, issuer, expiry, audience và scope **không gọi AS**. Nếu token bị lộ lúc chưa hết hạn, thao tác revoke tại AS **không tự khiến RS từ chối**.

Những cách chặn sớm tùy thiết kế:

- **Denylist `jti`** (hoặc token reference được RS nhận diện an toàn) đến khi `exp`.
- **Grant/session version** hoặc trạng thái revoked của grant được RS truy cập qua kênh tin cậy.
- **Issued-before cutoff** theo issuer/subject/client/grant đã xác định chính xác, khi cần chặn nhóm tokens.
- **Introspection/status check** với AS, có cache TTL phù hợp.
- **Access-token TTL ngắn** để giới hạn cửa sổ rủi ro nếu không hỗ trợ revoke tức thời.

**Không thay signing key toàn cục để revoke một token đơn lẻ** trừ khi có sự cố compromise khóa/signature và đã đánh giá ảnh hưởng toàn hệ thống. Key rotation toàn cục có thể làm mọi phiên bị lỗi và không phải cơ chế revocation thông thường.

## 10. Revocation latency: “đã revoke” phải đo được

Xét:

```text
T=00s: AS cấp opaque token; RS introspection active=true và cache 60s.
T=10s: Token nghi lộ; user yêu cầu logout.
T=12s: AS mark token revoked.
T=20s: RS vẫn dùng cache active=true, có thể tiếp tục cho phép.
T=60s: Cache hết hạn; RS gọi introspection -> active=false.
```

**Thời điểm AS ghi revoked ≠ thời điểm mọi RS từ chối token.** Với JWT local validation mà không có trạng thái, khoảng chậm có thể kéo dài đến expiry.

### Những biến số cần ghi trong incident

| Biến số | Cần đo/biết |
|---|---|
| `token.exp` | Giới hạn thời gian token tự hết hạn. |
| `revoked_at` | AS đã ghi nhận revoke lúc nào. |
| `rs_enforcement_at` | RS/gateway bắt đầu từ chối từ lúc nào. |
| Introspection positive cache TTL | Stale active=true tồn tại bao lâu. |
| Denylist propagation lag | Thời gian đồng bộ các nodes/regions. |
| Clock skew | Độ lệch đồng hồ giữa AS và RS. |
| In-flight API requests | Request đã được xác thực trước khi revoke có tiếp tục thực hiện side effect không. |

**Định nghĩa SLO cho revocation**, ví dụ “token bị nghi lộ phải bị các API nhạy cảm từ chối trong thời gian X theo policy”, thay vì hứa “vô hiệu tức thì” khi kiến trúc chưa hỗ trợ.

## 11. Refresh token bị nghi lộ: ưu tiên ngắt đường cấp token mới

Một refresh token có thể được dùng để xin access token mới mà **không cần người dùng tương tác**. Đây thường là nguy cơ lớn hơn một access token TTL ngắn.

Phản ứng:

1. Xác định **grant và refresh-token family** liên quan (nếu dùng rotation).
2. Chuyển grant/family sang **REVOKED/COMPROMISED** theo chính sách AS.
3. Từ chối mọi refresh từ family đã bị đánh dấu, kể cả token mới phát trong race.
4. Thu hồi access tokens liên quan theo revocation latency yêu cầu.
5. Dừng background jobs và xóa credential ở client.
6. Yêu cầu reauthentication từ một session/device đáng tin khi khôi phục.
7. Phát một family mới độc lập sau khi xác định nguồn rò đã được xử lý.

### Refresh token rotation và reuse detection

```text
Initial refresh token: R1
R1 được dùng hợp lệ -> AS phát R2; R1 bị invalidate.
R1 xuất hiện lại -> nghi vấn reuse.

Nếu reuse policy đánh dấu family compromised:
    R1: invalid
    R2: revoked
    R3 hoặc tokens đã phát trong race: bị xử lý theo grant policy
    Client: phải đăng nhập lại
```

**Reuse detection không luôn chứng minh attacker.** Có thể là client retry do timeout, hai browser tabs hoặc nhiều workers dùng chung token mà thiếu đồng bộ. Nhưng **về bảo mật không thể biết bên nào giữ token hợp lệ**, nên nhiều AS dùng chính sách revoke cả family và buộc reauthentication; điều tra lỗi đồng bộ sau containment.

## 12. RFC 7009 Token Revocation và giới hạn của response

OAuth 2.0 Token Revocation (RFC 7009) cho phép client yêu cầu AS revoke token:

```http
POST /oauth2/revoke HTTP/1.1
Host: id.example.test
Content-Type: application/x-www-form-urlencoded
Authorization: Basic CLIENT_AUTH_PLACEHOLDER

token=REFRESH_TOKEN_PLACEHOLDER&token_type_hint=refresh_token
```

**Lưu ý:**

- Request dùng TLS; `token` nằm trong form body, không URL.
- `token_type_hint` là **gợi ý**, không phải bằng chứng token type.
- Client authentication/authorization theo AS và client type.
- Theo RFC 7009, AS có thể trả **HTTP 200** cả khi token không tồn tại để tránh enumeration.
- Không dùng HTTP 200 làm bằng chứng rằng mọi access JWT liên quan đã bị RS từ chối.
- Cần biết liệu revoke token có kéo theo **grant/family** và access tokens liên quan theo policy AS.
- Một access token đã bị lộ ở logs không được gửi thêm tới những hệ thống ngoài AS/RS tin cậy chỉ để “kiểm tra”.

Trong quy trình nghi lộ, nên có **incident service/backend** điều phối revoke theo grant reference, không yêu cầu người dùng dán token vào helpdesk.

## 13. Logout all sessions, revoke one grant hay toàn account?

Phạm vi containment có thể khác nhau:

| Tình huống | Phạm vi tối thiểu có thể đủ | Khi cần mở rộng |
|---|---|---|
| Một access token lộ trong log có thể xác định `jti`. | Chặn token đó tại RS, dọn log, xem issued access rights. | Có dấu hiệu refresh/session cũng lộ hoặc token được dùng sai. |
| Refresh token của một mobile device bị mất. | Revoke family/grant của thiết bị, revoke access liên quan, xóa app state. | Malware/account takeover hoặc không thể xác định family. |
| RP session cookie bị lộ. | Invalidate session ID, clear cookie, hủy authorized clients thuộc session. | OP session cũng bị chiếm hoặc cookie bị lấy trên nhiều thiết bị. |
| User báo account takeover. | Revoke nhiều grants/SSO sessions, reauthentication và credential recovery. | Tất cả clients/sessions liên quan đã bị ảnh hưởng. |
| Client secret bị công khai. | Rotate/revoke client credentials và audit grants. | Có thêm token/signing key compromise hoặc khả năng mạo danh hàng loạt. |
| AS signing key bị nghi lộ. | Incident riêng về trust anchor/JWKS và token validity. | Có thể cần rotate keys, invalidate hàng loạt tokens, phối hợp mọi RS. |

**Không tự động logout mọi user của một tenant vì một token đơn lẻ nghi lộ**, trừ khi threat model buộc vậy. Nhưng cũng không chọn phạm vi quá nhỏ khi dấu hiệu cho thấy toàn bộ grant hoặc endpoint bị chiếm.

## 14. Global logout với nhiều thiết bị và tenants

Một người dùng có thể có:

```text
Desktop Orders:
    RP session S-WEB
    OP session O-WEB
    Refresh family F-WEB

Mobile Orders:
    App session S-MOB
    OP/browser session O-MOB
    Refresh family F-MOB

Reports:
    RP session S-REPORT
    Grant G-REPORT
```

Khi nghi lộ token của `F-WEB`, thao tác theo policy có thể chỉ revoke `G/F-WEB`. Khi nghi **toàn account bị chiếm**, cần xử lý rộng hơn: OP session invalidation, nhiều RPs, refresh families và active access token validation.

### Ràng buộc định danh

Mọi global revoke cần xác định đúng:

- **Issuer** (`iss`).
- **Subject ID** (`sub`) trong namespace issuer.
- **Tenant/organization** nếu hệ thống multi-tenant.
- **Client ID**, grant ID, device/session ID nếu chỉ một phạm vi.
- **Principal type**: end user, service account, workload.

**Không xóa sessions chỉ theo chuỗi `sub` trần** vì có thể trùng giữa issuers; không tin `tenant_id` do client gửi trong header để lựa chọn grant cần thu hồi.

## 15. OP logout, Front-/Back-Channel Logout không thay revoke

Khi user bấm “Đăng xuất tài khoản ở tất cả ứng dụng”, có thể phải kết thúc session SSO của OP, đồng thời thông báo RPs.

| Cơ chế | Vai trò | Giới hạn |
|---|---|---|
| **OIDC RP-Initiated Logout** | RP yêu cầu OP kết thúc SSO session qua `end_session_endpoint`. | Không mặc định revoke access/refresh token. |
| **OIDC Front-Channel Logout** | OP thông báo logout đến RP qua browser. | Phụ thuộc cookie/iframe/browser restrictions. |
| **OIDC Back-Channel Logout** | OP gửi **Logout Token** đến RP server-to-server. | Cần xác minh JWT sự kiện và invalidate đúng session; không tự revoke access tokens. |
| **RFC 7009 Revocation** | Client/AS xử lý token/grant revocation. | Không tự xóa browser session ở mọi RP/OP. |

**Back-Channel Logout Token không phải access token hoặc ID token thông thường**. RP phải kiểm issuer, audience, signature, `events`, `iat`, `jti`, `sid`/`sub` theo profile, xử lý replay và idempotency.

Trong vụ token leak, dùng SLO để chặn session-based re-login là hợp lý **khi dấu hiệu cho thấy SSO/session bị ảnh hưởng**. Tuy nhiên, RS vẫn phải có cơ chế từ chối token đã phát.

## 16. Khi nào cần tái xác thực (reauthentication)?

Sau khi vô hiệu credential nghi lộ, người dùng có thể cần **một authentication flow mới** để nhận token mới.

Tái xác thực an toàn cần:

1. Không lấy refresh token cũ để “khôi phục” phiên đã coi là compromised.
2. Không dùng browser session cũ nếu chính session đó không còn đáng tin.
3. Xử lý OP SSO đang hoạt động: nếu cần xác thực mới, dùng OP-supported `prompt=login` hoặc `max_age`/`auth_time` policy, không chỉ sinh nonce mới.
4. Yêu cầu step-up/MFA khi rủi ro và policy phù hợp.
5. Tạo RP session ID mới, tránh session fixation.
6. Phát grants/token family mới với scope tối thiểu và lifetime hợp lý.
7. Không cho response async từ phiên cũ ghi đè credential mới.
8. Thông báo người dùng những phiên/thiết bị đã bị kết thúc.

**OIDC nonce giúp ràng buộc ID token với request, không chứng minh user vừa nhập lại mật khẩu.** Muốn authentication freshness cần điều kiện riêng.

Nếu nghi kẻ tấn công còn kiểm soát browser hoặc thiết bị, reauthentication **trên chính môi trường đó** có thể tái làm lộ credentials. Cần xử lý thiết bị, malware/XSS, session integrity trước khi phát lại token.

## 17. Threat model: token lộ qua URL, Referer và logs

Bearer access token **không nên nằm trong URL query/fragment được xử lý như credential chung**, vì URL có thể lộ qua:

- Browser history, bookmarks.
- Reverse proxy/access logs.
- Referrer tới trang hoặc tài nguyên bên thứ ba.
- Analytics/session replay tools.
- Support tickets và screenshots.
- Crash reporting/APM traces.

Ví dụ thiết kế sai:

```http
GET /api/orders?access_token=REAL_TOKEN_VALUE HTTP/1.1
Host: api.example.test
```

Thiết kế gửi bearer token đúng hướng:

```http
GET /api/orders HTTP/1.1
Host: api.example.test
Authorization: Bearer ACCESS_TOKEN_PLACEHOLDER
```

**Kể cả Authorization header cũng phải được redact khỏi logs/traces**. Khi token đã rò vào log, việc xóa dòng log là bước hygiene, **không thay việc revoke token** vì token có thể đã được sao chép, xuất sang SIEM hoặc backup.

### Quy trình xử lý log leak

- Gỡ/rút quyền đọc nguồn log bị ảnh hưởng.
- Xác định tokens/grants bằng reference an toàn, không in token ra ticket.
- Revoke/chặn trong phạm vi phù hợp.
- Purge/redact các bản sao log, queue, analytics, backup theo khả năng và retention.
- Kiểm cấu hình logger/proxy/APM để ngăn lặp lại.
- Xem xét lịch sử truy cập log trong khoảng nghi lộ.
- Không làm lộ token lần nữa bằng cách gửi nó trong email/thông báo sự cố.

## 18. XSS, browser extension và storage compromise

Với SPA, token trong `localStorage` hoặc JS-accessible memory có thể bị script chạy cùng origin đọc khi XSS xảy ra. Một browser extension có quyền quá rộng cũng có thể ảnh hưởng bảo mật.

**Chỉ gọi `localStorage.clear()` rồi coi incident đã giải quyết là sai**, vì:

- Bản sao token có thể đã rời khỏi browser.
- Refresh token có thể đã bị sao chép.
- Script độc hại có thể tiếp tục chạy và lấy token mới ngay sau reauth.
- Nhiều tabs/service workers/background jobs có thể vẫn giữ state.

### Biện pháp phù hợp

1. Vô hiệu tokens/grants đã bị nghi ảnh hưởng qua AS/RS.
2. Dừng ứng dụng/refresh jobs, invalidate phiên.
3. Vá XSS và đánh giá third-party scripts/dependencies/extensions.
4. Kiểm CSP, HTML sanitization và origin isolation, không coi một header đơn lẻ là giải pháp trọn vẹn.
5. Ưu tiên **Backend-for-Frontend (BFF)** với tokens server-side khi phù hợp; browser giữ session cookie có HttpOnly/Secure và CSRF controls.
6. Reauth chỉ sau khi giảm khả năng script lạ tiếp tục lấy credentials.

**BFF cũng không miễn dịch session cookie theft, CSRF hoặc server-side token leakage**; chỉ thay đổi vị trí lưu token và bề mặt tấn công.

## 19. Thiết bị mobile bị mất và token storage

iOS/Android cung cấp **Keychain/Keystore** và các cơ chế kho bí mật được OS bảo vệ. Nếu thiết bị bị mất:

| Điều kiện | Hành động |
|---|---|
| Thiết bị bị khóa, OS storage được bảo vệ | Nguy cơ có thể giảm nhưng không coi bằng 0. |
| App vẫn có session và background sync | Revoke grant/family liên quan từ thiết bị an toàn khác. |
| App có offline refresh token | Chặn refresh tại AS, không chỉ “sign out” trên thiết bị bị mất. |
| OP browser session còn active | Xem xét revoke/terminate OP session/device theo khả năng provider. |
| Token sender-constrained với key trên thiết bị | Đánh giá key có thể bị sử dụng hoặc trích xuất không, revoke bound grant theo policy. |
| Người dùng đăng nhập lại trên máy mới | Phát grants/tokens mới, thiết bị cũ không được tự tiếp tục refresh. |

**Ứng dụng trên thiết bị khác không thể xóa Keychain/Keystore của thiết bị bị mất qua một nút local logout.** Cần khả năng quản lý grants/sessions từ AS và portal quản trị thiết bị nếu có.

### App lifecycle và tác vụ nền

App có thể bị suspend, network callbacks trả muộn hoặc queue retry. Thiết kế cần generation/session guard để không có token mới từ refresh trước logout được lưu sau logout.

## 20. Service-to-service token và client credential bị nghi lộ

Không phải vụ token leak nào cũng liên quan end user.

Ví dụ một service `billing-worker` dùng **client_credentials** để xin access token đến Orders API. Secret của service bị commit vào CI log.

**Không giải quyết bằng cách gọi OP logout cho một người dùng**, vì client credentials grant không có user SSO session tương ứng.

Containment:

- Disable/rotate client secret, private key hoặc mTLS certificate theo trust policy.
- Revoke access tokens do credential/client grant bị ảnh hưởng nếu cần.
- Kiểm scope/audience và chỉ cấp quyền service tối thiểu.
- Dùng short-lived credentials, workload identity và secret manager nếu hệ thống hỗ trợ.
- Audit token issuance/service API calls trong khoảng exposure.
- Roll out secret mới an toàn đến workloads; tránh secrets trong env dumps hoặc logs.
- Khi có signing key compromise của AS, xử lý riêng vì blast radius có thể trải rộng nhiều clients/RS.

**Credential của client và credential của user là hai ranh giới khác nhau.** Global user logout không thu hồi một client secret bị lộ.

## 21. Sender-constrained tokens: giảm replay, không miễn revocation

Một **Bearer access token** bị lấy có thể sử dụng bởi người giữ bản sao cho đến khi bị chặn. Với **sender-constrained tokens**, RS yêu cầu proof rằng caller sở hữu một khóa:

- **DPoP** (RFC 9449): DPoP proof JWT có chữ ký, ràng buộc HTTP method/URI, time/replay và access token.
- **mTLS-bound access tokens** (RFC 8705): token gắn với client certificate.

Nếu attacker lấy token nhưng **không lấy private key**, khả năng replay có thể bị hạn chế. Nhưng nếu attacker chiếm runtime hoặc key, sender constraint không còn đủ.

| Tình huống | Hành động |
|---|---|
| Chỉ bearer access token bị lộ | Revoke/chặn token và giới hạn phạm vi API. |
| DPoP-bound token lộ, key được bảo vệ | Đánh giá key containment; vẫn revoke theo policy/risk. |
| DPoP private key bị nghi lộ | Revoke bound tokens/grant, rotate key và reauthenticate. |
| mTLS certificate/private key bị nghi lộ | Revoke/rotate certificate, invalidate bound credentials. |
| RS không kiểm DPoP/mTLS proof | Xem đây là lỗi validation; token có thể bị dùng như Bearer. |

**Có claim `cnf` trong JWT/introspection không đủ** nếu RS không kiểm proof/certificate trên từng request.

## 22. Bảo vệ API: issuer, audience, scope vẫn phải kiểm

Ví dụ access JWT bị nghi lộ:

```json
{
  "iss": "https://id.example.test",
  "sub": "user-123",
  "client_id": "orders-web",
  "aud": "orders-api",
  "scope": "orders.read",
  "exp": 1795410900,
  "jti": "token-ref-123"
}
```

Đây chỉ là payload minh họa.

- **Payments API** phải từ chối vì `aud` không phải Payments.
- **Orders approve endpoint** phải từ chối nếu thiếu `orders.approve`.
- **Orders read endpoint** có thể cho phép nếu token chưa bị chặn và user có quyền đối tượng.
- Nếu token đã nằm trong denylist, **Orders read phải từ chối dù chữ ký và `exp` còn hợp lệ**.
- Với user đa tenant, scope đọc không cho phép xem đơn thuộc tenant khác.

**Least privilege giảm blast radius khi bị lộ, nhưng không thay revocation.** Chỉ kiểm chữ ký JWT mà bỏ `aud`/`scope`/token type có thể làm hậu quả token leak nặng hơn.

## 23. Thiết kế trạng thái sự cố và kết quả từng lớp

Một bảng trạng thái logic giúp tránh hứa “đã bảo vệ an toàn” khi revoke mới làm được một phần.

| Trạng thái | Điều kiện |
|---|---|
| `DETECTED` | Có report/detection signal. |
| `TRIAGED` | Đã phân loại token/principal/trust domain và phạm vi tạm. |
| `CONTAINMENT_REQUESTED` | Yêu cầu local/grant/RS/OP actions được tạo. |
| `REFRESH_BLOCKED` | AS xác nhận grant/family không thể refresh. |
| `ACCESS_BLOCKED` | Các RS cần thiết xác nhận token cũ bị từ chối hoặc hết hạn. |
| `SESSION_INVALIDATED` | RP/OP sessions theo phạm vi đã vô hiệu. |
| `REAUTH_REQUIRED` | Thiết bị/user phải đăng nhập lại qua luồng an toàn. |
| `EVIDENCE_REVIEWED` | Tương quan sự kiện đã được kiểm tra và nguồn rò được xử lý. |
| `CLOSED` | Các tiêu chí bảo mật/kỹ thuật của incident được đáp ứng. |
| `PARTIAL/FAILED` | Có bước chưa hoàn tất, phải theo dõi/retry/escalate. |

Các trạng thái không nhất thiết tuyến tính và **không nên chỉ có một cờ boolean**. Ví dụ `REFRESH_BLOCKED=true` nhưng `ACCESS_BLOCKED=pending` là trạng thái có ý nghĩa an ninh thực tế.

### Kết thúc sự cố khác đóng ticket

Một phản hồi HTTP 200 từ `POST /logout` hoặc `POST /revoke` là **kết quả một bước**, không chứng minh mọi API đã chặn. Tiêu chí đóng incident cần dựa trên RS behavior, token family state, user session scope và evidence review.

## 24. Java/Spring Security: local logout cơ bản

Trong Spring Security 6.x (Servlet stack), local logout có thể dùng cấu hình chuẩn:

```java
@Configuration
@EnableWebSecurity
public class WebLogoutSecurity {

    @Bean
    SecurityFilterChain webSecurity(HttpSecurity http)
            throws Exception {

        http.authorizeHttpRequests(auth -> auth
            .requestMatchers("/", "/logged-out", "/health").permitAll()
            .anyRequest().authenticated());

        http.oauth2Login(Customizer.withDefaults());

        http.logout(logout -> logout
            .logoutUrl("/logout")
            .invalidateHttpSession(true)
            .clearAuthentication(true)
            .deleteCookies("JSESSIONID")
            .logoutSuccessUrl("/logged-out"));

        return http.build();
    }
}
```

**Đây là local logout**, không phải xử lý đầy đủ token compromise. Khi ứng dụng có cookie/session và CSRF bật, hãy dùng **POST /logout với CSRF token**. Không tự mở GET /logout thay đổi trạng thái chỉ để dễ test.

Với `OAuth2AuthorizedClientService` lưu token persistent (database), invalidate session **không tự bảo đảm mọi authorized-client records được xóa**. Cần cleanup theo owner/session/grant, có kiểm soát phạm vi để không xóa phiên của thiết bị khác.

### Session cookie bị nghi lộ

Ngoài dọn cookie browser, phải **invalidate server-side session ID** tại session store phân tán. Kiểm replay session cookie cũ trên mọi node, không chỉ node vừa xử lý logout.

## 25. Java: Incident Logout Coordinator (pseudocode)

Một chức năng “Báo nghi lộ token” nên gọi một **backend incident coordinator** có quyền truy cập an toàn tới AS/session registry. Không để client gửi user ID hoặc grant ID tùy ý rồi revoke người khác.

```java
// Pseudocode: interface, service và exception do hệ thống định nghĩa.
record CredentialExposureReport(
    String reporterSessionRef,
    String reason,
    String targetDeviceRef
) {}

record ContainmentResult(
    boolean localSessionInvalidated,
    boolean refreshGrantBlocked,
    boolean accessTokenEnforcementConfirmed,
    boolean providerSessionTerminated,
    String incidentReference
) {}

ContainmentResult reportAndContain(
        VerifiedPrincipal actor,
        CredentialExposureReport report) {

    // 1) Actor đã được xác thực hoặc qua recovery channel an toàn.
    requireAuthorizedReporter(actor, report);
    requireStepUpForHighRiskActions(actor);

    Incident incident = incidentStore.create(
        actor.issuer(), actor.subject(), actor.tenant(),
        report.reason());

    // 2) Target/grant IDs do backend tra qua ownership,
    // không tin chuỗi do browser tự khai.
    CompromiseScope scope =
        ownedGrantResolver.resolve(actor, report.targetDeviceRef());

    // 3) Chặn refresh trước khi client dùng lại.
    grantService.markCompromisedAtomically(scope.grantIds());
    refreshFamilyService.revokeFamilies(scope.familyIds());

    // 4) Chặn access tokens tại RS theo jti/grant status.
    revocationPublisher.publish(scope.accessTokenRefs());

    // 5) Invalidate đúng session(s) theo requested scope.
    sessionRegistry.invalidate(scope.rpSessionIds());

    // 6) OP SSO logout: tùy sự cố, OP capability và policy.
    boolean opRequested = scope.shouldTerminateOpSessions();
    if (opRequested) {
        opSessionService.requestTermination(scope.opSessionRefs());
    }

    // 7) Không báo access enforcement confirmed nếu chưa có evidence.
    boolean rsConfirmed =
        enforcementMonitor.hasConfirmed(scope.accessTokenRefs());

    auditWithoutCredentials(incident, scope, rsConfirmed);

    return new ContainmentResult(
        true, true, rsConfirmed, opRequested && 
            opSessionService.isConfirmed(scope.opSessionRefs()),
        incident.safeReference());
}
```

**Pseudocode**, không phải Spring Security/Spring Authorization Server API được cung cấp sẵn. Hệ thống thật cần xử lý transaction boundaries, idempotency, outbox/retries, partial failures, authorization to revoke, atomic status, distributed caches và data retention.

### Những quy tắc bất biến

- Actor không thể tự revoke grants của user khác chỉ bằng `targetDeviceRef`.
- Gắn mọi lookup với issuer + subject + tenant + client, theo owner đã xác minh.
- Revoke refresh/grant cần **atomic**, tránh token mới phát sau khi mark compromised.
- Không ghi token plaintext trong incident DB, message queue hoặc audit.
- Nếu publish denylist thất bại, giữ trạng thái **PARTIAL** và alert.
- Chỉ tạo authenticated session mới sau recovery flow, không tái sử dụng token bị nghi lộ.

## 26. Spring Resource Server: chặn JWT đã bị thu hồi

RS xác thực JWT với issuer/JWKS đáng tin, sau đó có thể thêm kiểm trạng thái revoke.

Ví dụ Java với một `TokenRevocationRegistry` do hệ thống tự triển khai:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
public class JwtRevocationSecurity {

    @Bean
    JwtDecoder jwtDecoder(TokenRevocationRegistry registry) {
        String issuer = "https://id.example.test";
        NimbusJwtDecoder decoder =
            NimbusJwtDecoder.withIssuerLocation(issuer).build();

        OAuth2TokenValidator<Jwt> revokedJti = jwt -> {
            String jti = jwt.getId();
            String actualIssuer = jwt.getIssuer() == null
                ? "" : jwt.getIssuer().toString();

            // Trong hệ thống này, mỗi revocable access JWT bắt buộc có jti.
            if (jti == null || jti.isBlank()) {
                return invalid("Missing jti");
            }

            // Registry theo issuer+jti; production cần TTL đến exp,
            // khả năng chịu lỗi, quy tắc fail closed và chống cache stale.
            if (registry.isRevoked(actualIssuer, jti)) {
                return invalid("Revoked access token");
            }

            return OAuth2TokenValidatorResult.success();
        };

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                JwtValidators.createDefaultWithIssuer(issuer),
                revokedJti));

        return decoder;
    }

    private static OAuth2TokenValidatorResult invalid(String reason) {
        return OAuth2TokenValidatorResult.failure(
            new OAuth2Error("invalid_token", reason, null));
    }
}

// Giao diện do ứng dụng định nghĩa:
interface TokenRevocationRegistry {
    boolean isRevoked(String trustedIssuer, String jti);
}
```

**Đây là một lớp bổ sung, không phải giải pháp production hoàn chỉnh.** Cần còn kiểm:

- JWT token type/profile, allowed algorithms, `aud` = API hiện tại, scopes/authorities.
- Registry fail-closed phù hợp với yêu cầu API nhạy cảm nếu không truy vấn được.
- Denylist TTL **không sớm hơn token expiry** cùng clock skew hợp lý.
- Propagation giữa nodes/regions và ảnh hưởng cache tại gateway.
- Không để cùng `jti` của issuer A tác động issuer B.
- Nếu token không mang `jti` hoặc cần revoke toàn grant, phải thiết kế **grant/session status** hay cutoff có dữ liệu tương ứng, không âm thầm bỏ qua kiểm revoke.
- Dòng log/exception không chứa raw JWT.

### Vì sao không chỉ check `jti`?

Một grant có thể phát nhiều access tokens trước khi bị nghi lộ. Revoke một `jti` không chặn tất cả token thuộc grant nếu attacker có các bản sao khác. Với refresh family compromise, cần cơ chế **grant-wide revocation** và RS enforcement tương ứng.

## 27. Spring Security: OIDC logout không thay token revocation

Nếu AS đồng thời là OP, Spring Security có `OidcClientInitiatedLogoutSuccessHandler` cho **RP-Initiated Logout**.

```java
@Bean
SecurityFilterChain oidcLogoutChain(
        HttpSecurity http,
        ClientRegistrationRepository registrations)
        throws Exception {

    OidcClientInitiatedLogoutSuccessHandler opLogout =
        new OidcClientInitiatedLogoutSuccessHandler(registrations);
    opLogout.setPostLogoutRedirectUri("{baseUrl}/logged-out");

    http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/", "/logged-out").permitAll()
        .anyRequest().authenticated());

    http.oauth2Login(Customizer.withDefaults());

    http.logout(logout -> logout
        .logoutUrl("/logout")
        .invalidateHttpSession(true)
        .clearAuthentication(true)
        .logoutSuccessHandler(opLogout));

    return http.build();
}
```

**Không triển khai thêm code này rồi tuyên bố token compromise đã được xử lý.** Handler chủ yếu yêu cầu OP logout qua `end_session_endpoint` nếu được hỗ trợ. Các bước revoke refresh/access token, invalidate sessions khác, revoke grant và audit nằm ở cơ chế độc lập.

Trong sự cố nghi lộ, nếu cần revoke token từ backend, phải capture credential/secure handle **trước khi xóa token store**, quản lý timeout và partial failures. Không lưu raw refresh token vào queue/log để retry không bảo vệ.

## 28. Race condition: refresh đã bắt đầu trước logout

Một tình huống thực tế:

```text
T0: Background worker gửi R1 đến AS để refresh.
T1: User bấm "Token có thể bị lộ"; client xóa R1 local.
T2: AS trả access token A2 + refresh token R2.
T3: Worker ghi A2/R2 vào store và bật lại session.    // SAI
```

**Chặn ở hai phía:**

**Client**

- Tăng session generation ngay khi bắt đầu logout.
- Hủy/cancel HTTP jobs nếu có thể.
- Khi response về, so generation hiện tại; nếu không khớp thì **không lưu**.
- Không tự re-login bằng OP SSO nếu user đang ở trạng thái security recovery.
- Nếu response chứa token mới do race, xử lý revoke bổ sung theo policy.

**AS**

- Dùng atomic grant/family state để chặn refresh sau khi compromised.
- Refresh rotation và revoke family phải có concurrency control.
- Nếu refresh thành công trước khi revoke commit, tokens vừa phát phải nằm trong phạm vi revocation/grant status cần thực thi.
- Audit sự kiện issuance trong khoảng race, không in raw tokens.

### Không hứa atomicity xuyên ba hệ thống

Một thao tác logout tại client, revoke tại AS và denylist tại RS **không phải một database transaction đơn nhất**. Cần trạng thái trung gian, outbox/retry, reconciliation và đo thời gian propagation.

## 29. Khi nào phải xử lý mật khẩu, MFA và thiết bị?

**Không phải cứ một access token lộ là bắt buộc đổi mật khẩu**, vì access token có thể bị lộ qua logs dù user password/MFA vẫn an toàn. Nhưng khi có dấu hiệu **account takeover**:

- Kẻ tấn công thay email/phương thức khôi phục.
- Có phiên OP/SSO bất thường hoặc credential phishing.
- Thiết bị có malware/keylogger.
- MFA factors/recovery codes bị sao chép.
- Có hành động nghiệp vụ trái phép kéo dài.

Khi đó, cần phối hợp các biện pháp theo policy:

1. Revoke sessions/grants/tokens bị ảnh hưởng.
2. Yêu cầu khôi phục credential và step-up qua **kênh độc lập đáng tin**.
3. Reset/re-enroll MFA hoặc recovery methods nếu bằng chứng cho thấy chúng cũng bị lộ.
4. Kiểm devices, email/phone recovery và các integrations bên thứ ba.
5. Khóa rủi ro cao tạm thời theo chính sách; tránh để attacker đang giữ session tự phê duyệt bỏ khóa.
6. Xác minh source of compromise trước khi phát tokens mới.

**Không tự gửi yêu cầu “nhập mật khẩu/MFA vào link này” từ một email không kiểm chứng**. Trong incident response, các thông báo cần dẫn người dùng đến domain/app chính thức và luồng recovery đã được thiết kế.

## 30. Audit và forensics mà không làm rò token lần thứ hai

Sự cố credential leak thường bắt đầu từ **logs chứa credential**. Do đó, audit incident không được lưu thêm raw tokens.

| Event | Dữ liệu nên lưu |
|---|---|
| `TOKEN_EXPOSURE_REPORTED` | Incident ID, source category, issuer/client/tenant reference, thời điểm. |
| `CREDENTIAL_KIND_IDENTIFIED` | ACCESS/REFRESH/SESSION/CLIENT_KEY, không raw credential. |
| `GRANT_MARKED_COMPROMISED` | Grant/family reference, policy version, kết quả atomic update. |
| `REFRESH_REVOKED` | Family/grant reference, AS outcome. |
| `ACCESS_DENYLIST_PUBLISHED` | `jti` digest/reference, audience, propagation status. |
| `RS_ENFORCEMENT_CONFIRMED` | RS ID, check time, outcome, test token reference an toàn. |
| `LOCAL_SESSION_INVALIDATED` | Session reference/HMAC, device reference. |
| `OP_SESSION_TERMINATION_REQUESTED` | Issuer, subject/sid reference, provider status. |
| `REAUTH_REQUIRED` | Subject/tenant, reason class, deadline nếu policy có. |
| `INCIDENT_CLOSED` | Evidence summary, residual risk, approved remediation. |

**Không log** Authorization header, raw access/refresh/ID tokens, session cookies, client secrets, DPoP private keys hoặc nguyên URL chứa token. Cần correlate token mà không lộ giá trị? Dùng reference nội bộ/HMAC có khóa riêng, retention/access control, không dùng hash yếu dễ đảo ngược với secrets có entropy thấp.

### Bằng chứng cần thu thập

- Thời điểm phát hành `iat` và hạn `exp`.
- Issuer, token/client/grant references, scope và audience theo nguồn đáng tin.
- Trạng thái credential và issuer/session tại các mốc.
- Tập API resources đã được truy cập trong cửa sổ rủi ro.
- Log access từ nguồn nghi vấn, đã sanitize và tuân thủ quyền riêng tư.
- Tình trạng cache/denylist giữa RS nodes.
- Thời điểm containment và thời điểm RS enforcement thực sự có hiệu lực.

Không khẳng định “chưa có dữ liệu bị lấy” chỉ vì không thấy logs: sampling, missing traces hoặc các kênh truy cập không log có thể khiến kết luận quá chắc chắn.

## 31. Giao tiếp với người dùng: chính xác về phạm vi

Một thông báo hữu ích khi người dùng báo nghi lộ:

> “Chúng tôi đã kết thúc phiên đăng nhập trên thiết bị được chọn và yêu cầu thu hồi quyền truy cập liên quan. Một số token đã cấp trước đó có thể còn chịu thời gian xử lý thu hồi; chúng tôi đang xác minh việc chặn tại các dịch vụ. Bạn cần đăng nhập lại qua ứng dụng chính thức.”

Câu chữ phải **phản ánh trạng thái thật**, không dùng nếu hệ thống chưa gửi revoke request.

### Ba trạng thái UX nên tách

| Trạng thái | Hiển thị phù hợp |
|---|---|
| Local logout hoàn thành, revoke đang chờ | “Đã đăng xuất khỏi ứng dụng; đang xử lý thu hồi quyền truy cập.” |
| AS xác nhận revoke nhưng RS propagation chưa được xác minh | “Đã yêu cầu thu hồi token; một số API đang cập nhật trạng thái.” |
| Containment được xác minh theo mục tiêu | “Đã chặn các phiên/quyền truy cập nằm trong phạm vi sự cố; cần đăng nhập lại.” |

Tránh thông báo:

- “Mọi token trên toàn Internet đã được xóa.”
- “Tất cả thiết bị đều an toàn” khi chỉ xử lý một browser.
- “Không có dữ liệu nào bị truy cập” nếu không có audit đủ cơ sở.
- “Đổi mật khẩu là đủ” khi refresh token, AS client credentials hoặc session cookie còn hiệu lực.

## 32. Bảng quyết định nhanh cho vận hành

| Dấu hiệu | Containment cấp thiết | Kiểm chứng sau xử lý |
|---|---|---|
| Access JWT bị lộ, `jti` xác định | Denylist/jti hoặc grant status; dọn storage/logs. | RS từ chối token cũ trước `exp` theo SLO. |
| Opaque access token bị lộ | AS revoke, introspection cache policy. | `active=false` hoặc RS 401 thực tế. |
| Refresh token bị lộ | Revoke family/grant, khóa refresh reuse. | Token endpoint không phát access token mới từ family cũ. |
| Session cookie bị lộ | Invalidate session server, cookie cleanup, session rotation. | Cookie cũ bị từ chối trên mọi node. |
| OP SSO bị chiếm | OP session termination, SLO theo support. | OP session cũ không tạo login mới không hợp lệ. |
| Client secret bị lộ | Rotate/revoke secret, đánh giá grants/tokens. | Credential cũ bị AS từ chối. |
| DPoP/mTLS key bị lộ | Rotate key/cert, revoke bound grants/tokens. | Proof/cert cũ không còn được chấp nhận. |
| Signing key AS nghi lộ | Coordinated key incident response. | RS tin đúng key set/new issuer policy; token giả bị từ chối. |
| Không xác định loại credential | Tạm thời kiểm soát phiên/grants theo phạm vi nghi vấn, điều tra. | Không đóng incident bằng phỏng đoán. |

## 33. Ma trận kiểm thử “Logout khi token bị nghi lộ”

Giả sử AS `https://id.example.test` phát JWT/opaque tokens, Orders API yêu cầu `aud=orders-api`, scopes chính là `orders.read` và `orders.approve`. BFF quản lý sessions và AS có refresh rotation/revocation, RS có denylist hoặc introspection theo profile.

| ID | Kịch bản | Kết quả cần có |
|---|---|---|
| S01 | Một access JWT bị copy, user logout local. | RP session bị vô hiệu; test **không** giả định JWT cũ tự revoked. |
| S02 | Access JWT jti bị đưa vào denylist. | RS từ chối token dù `exp` chưa qua. |
| S03 | Denylist không đồng bộ tới một RS node. | Test phát hiện revoke propagation gap. |
| S04 | Denylist record hết hạn trước JWT `exp`. | Security test thất bại; TTL sai. |
| S05 | JWT có issuer đúng nhưng `aud=payments-api`. | Orders RS từ chối. |
| S06 | JWT đúng aud nhưng thiếu scope thao tác. | RS từ chối 403 theo policy. |
| S07 | JWT đủ scope nhưng order thuộc tenant khác. | RS từ chối object-level access. |
| S08 | Token đúng signature nhưng sai type/profile. | RS từ chối token confusion. |
| S09 | Opaque token bị AS revoke. | Introspection chuyển `active=false` theo policy. |
| S10 | RS cache `active=true` sau revoke. | Test đo revocation latency, không tuyên bố tức thời. |
| S11 | AS outage khi RS phải kiểm trạng thái. | Fail closed hoặc valid cache theo policy, không permit mặc định. |
| S12 | Refresh token bị lộ, AS revoke token đơn nhưng family còn active trái policy. | Security test thất bại. |
| S13 | Refresh token R1 đã rotation bị reuse. | AS phát hiện theo policy, revoke family phù hợp. |
| S14 | Hai refresh requests hợp lệ chạy đua. | Xử lý concurrency an toàn; không đánh đồng mọi race với attacker nhưng containment theo policy. |
| S15 | Refresh response đến sau logout. | Client generation guard không lưu token mới. |
| S16 | AS vừa mark grant compromised vừa nhận refresh. | Atomic state ngăn issuance mới theo contract. |
| S17 | Token được phát ngay trước revoke commit. | Grant-wide RS policy chặn theo scope. |
| S18 | Revoke endpoint trả HTTP 200 cho unknown token. | Client không dùng response để suy token tồn tại. |
| S19 | Revoke endpoint trả 401 invalid_client. | Không báo revocation success. |
| S20 | Client token issuer/endpoint sai. | Không gửi token sang endpoint không tin cậy. |
| S21 | RP session cookie bị lộ, local logout chỉ xóa browser cookie. | Test phát hiện server session vẫn hoạt động. |
| S22 | Session bị invalidate trên node A nhưng node B vẫn chấp nhận. | Test phát hiện distributed session invalidation failure. |
| S23 | Multi-tab browser, tab A logout, tab B tiếp tục request. | Session cũ bị chặn, UI cập nhật. |
| S24 | SPA xóa localStorage khi access JWT đã lộ. | Không tự coi revocation hoàn tất. |
| S25 | Browser có XSS còn tồn tại sau reauth. | Test phát hiện token mới có thể bị lấy; cần sửa XSS trước recovery. |
| S26 | Token xuất hiện trong proxy access log. | Incident event + redaction + revoke + log access review. |
| S27 | Raw token xuất hiện trong audit incident. | Security/redaction test thất bại. |
| S28 | User báo mất điện thoại không còn khả năng remote logout app. | AS server-side revoke device grant/family. |
| S29 | Mất điện thoại, OP browser SSO còn active. | Xử lý provider session policy và UX đúng phạm vi. |
| S30 | Local logout nhưng OP SSO tự login lại. | Test phân biệt phiên RP mới với session cũ. |
| S31 | OP logout request không có endpoint chính thức. | Fallback local; không tự đoán logout URL. |
| S32 | OP logout thành công nhưng refresh grant vẫn active. | Không báo toàn bộ credential revoked. |
| S33 | OIDC Back-Channel Logout Token sai chữ ký/audience. | RP từ chối không invalidate session. |
| S34 | Back-Channel `sid` thuộc issuer khác. | Không xóa session chéo issuer. |
| S35 | User yêu cầu global logout nhưng thiếu step-up khi policy yêu cầu. | Từ chối/thực hiện recovery flow an toàn. |
| S36 | User tenant A gửi `targetDeviceRef` thuộc tenant B. | Backend không revoke người khác. |
| S37 | Service client secret lộ; user logout local. | Incident vẫn mở; rotate client secret. |
| S38 | Client secret cũ sau rotation. | AS từ chối credential cũ. |
| S39 | DPoP-bound token bị lộ nhưng không có proof. | RS từ chối token nếu proof bắt buộc. |
| S40 | DPoP key bị lộ cùng token. | Revoke bound token/grant và rotate key. |
| S41 | mTLS-bound token dùng certificate khác. | RS từ chối. |
| S42 | RS chỉ kiểm `cnf` nhưng không kiểm proof. | Security test phát hiện lỗi. |
| S43 | Signing key AS bị nghi compromise. | Key incident plan, không chỉ revoke một user grant. |
| S44 | Token lộ chỉ có scope `orders.read` nhưng attacker gọi approve. | RS chặn; scope giảm blast radius. |
| S45 | User reauth với session ID cũ. | Session fixation test thất bại; cần rotation. |
| S46 | Reauth trong thiết bị vẫn có malware. | Security plan phát hiện nguy cơ tiếp tục lộ. |
| S47 | Logout request dùng GET trong app cookie-based không CSRF. | Security test thất bại. |
| S48 | Browser callback refresh cũ ghi đè token mới sau reauth. | Generation isolation chặn stale write. |
| S49 | AS revoke thành công, một RS ở region khác vẫn accept token. | Propagation test và alert. |
| S50 | Cache key chỉ theo token, chia sẻ giữa hai issuers. | Test phát hiện cross-issuer contamination. |
| S51 | Token hết hạn, actor gọi RS. | RS từ chối theo `exp`. |
| S52 | Incident status chỉ có boolean “done” khi access enforce chưa xác minh. | Test yêu cầu trạng thái PARTIAL/pending. |
| S53 | User nhận thông báo “mọi thiết bị đã logout” nhưng chỉ một session bị invalid. | UX/security test phát hiện phạm vi sai. |
| S54 | Third-party consent vẫn active sau OP logout. | Không tự coi grant đã revoke. |
| S55 | Third-party đã tải dữ liệu trước revoke. | Không khẳng định dữ liệu tự xóa. |
| S56 | Helpdesk yêu cầu người dùng gửi raw token qua chat. | Quy trình bị đánh dấu không an toàn. |
| S57 | Trong lúc điều tra, security agent gọi endpoint lạ để “check token”. | Không gửi credentials ra nguồn không tin cậy. |
| S58 | Audit log không đầy đủ, không thấy misuse. | Report nêu bất định, không khẳng định 0 exposure. |
| S59 | Global logout được yêu cầu từ phiên cũng nghi chiếm đoạt. | Cần xác minh quyền/step-up bằng kênh tin cậy, không cho attacker tùy ý revoke người khác. |
| S60 | AS revocation timeout, RP đã logout local. | Local cleanup giữ nguyên; incident PARTIAL và retry an toàn. |

### Các tầng kiểm thử cần tách

- **Unit tests:** phân loại token, grant ownership, session generation, idempotency, denylist TTL, trạng thái PARTIAL và scope matching.
- **OAuth/AS integration tests:** RFC 7009, refresh family rotation/reuse, atomic grant compromise và issuer/client binding.
- **RS integration tests:** JWT signature/issuer/aud/scope, denylist, opaque introspection, cache TTL và object authorization.
- **OIDC tests:** OP session logout, RP-Initiated Logout, SLO, reauthentication freshness và Logout Token validation.
- **Browser/mobile tests:** session cookie invalidation, CSRF, multi-tab, background refresh, OS secure storage và lost-device flow.
- **Resilience/security tests:** AS/RS outage, cache propagation, slow revoke, XSS, logs/URL token leakage, DPoP/mTLS proofs.
- **Forensics/UX tests:** metadata-only incident logs, correct exposure wording và evidence of RS enforcement.

**Một unit test giả lập “POST /logout trả 200” không chứng minh token nghi lộ đã bị chặn.** End-to-end cần kiểm token endpoint không refresh được và RS thực sự từ chối token cũ trong revocation latency SLO.

## 34. Tình huống ứng dụng

### Tình huống A — Token xuất hiện trong log nhưng chưa thấy ai dùng

Một access JWT còn hạn 10 phút đã nằm trong log tập trung có 100 người được quyền đọc. Operations chưa thấy API call bất thường.

**Hỏi:** Có nên chỉ xóa dòng log và kết thúc incident?

> **Không.** Có dấu hiệu token đã vượt boundary mong muốn. Cần containment theo policy (denylist/AS revoke), kiểm đường truy cập logs, dọn bản sao và xác minh RS từ chối. Chưa thấy misuse **không chứng minh chưa bị lấy**.

### Tình huống B — Refresh token reuse sau rotation

AS phát R2 thay R1. Sau đó R1 bị sử dụng lại từ một request khác.

**Hỏi:** Chỉ revoke R1 có đủ không?

> **Không chắc.** Bên nào giữ token hợp lệ không thể xác định chỉ qua reuse event; AS thường áp family-level compromise policy, revoke cả R2/family và yêu cầu reauthentication. Đồng thời điều tra race/retry hợp lệ để sửa client.

### Tình huống C — User nhấn logout toàn bộ nhưng JWT vẫn chạy

AS đã thu hồi refresh family và OP đã logout SSO, nhưng Orders API vẫn nhận JWT tự chứa còn `exp` 6 phút.

**Hỏi:** Có mâu thuẫn không?

> Không. OP session, refresh grant và access JWT là các lớp độc lập. Nếu yêu cầu logout toàn bộ khiến API token phải dừng sớm, RS cần denylist/grant status hoặc TTL/contract phù hợp. Phải báo rõ **cửa sổ revocation latency**.

### Tình huống D — Thiết bị bị mất, user đang dùng máy khác

Người dùng không thể chạm vào điện thoại đã mất để xóa Keychain/Keystore. Họ mở tài khoản trên laptop an toàn.

**Hỏi:** Nút logout trên laptop có chặn điện thoại bị mất không?

> Chỉ nếu backend/AS hỗ trợ **revoke đúng device grant/refresh family hoặc global sessions**. Xóa phiên laptop không thể xóa storage của điện thoại từ xa. Cần quản lý thiết bị và token issuance phía server.

### Tình huống E — Client secret của service bị lộ

Một scheduled worker dùng `client_credentials`, secret bị commit vào repository công khai.

**Hỏi:** Có cần bắt mọi user đổi mật khẩu không?

> Không mặc định. Ưu tiên rotate/revoke **client credential**, thu hồi tokens/grants liên quan, audit quyền của workload và sửa đường lộ. Mở rộng sang user reauthentication chỉ khi có bằng chứng ảnh hưởng tới user identities/sessions.

### Tình huống F — XSS chưa được vá, user re-login

Người dùng được yêu cầu đăng nhập lại ngay, nhưng XSS còn chạy trong ứng dụng SPA.

**Hỏi:** Việc cấp refresh token mới có an toàn không?

> Có nguy cơ **bị lấy tiếp**. Phải chặn đường lộ (XSS/dependency/extension), invalidate tokens cũ và đảm bảo reauthentication trong môi trường đáng tin trước khi cấp credentials mới.

### Tình huống G — RS kiểm DPoP không đủ

Access token có `cnf.jkt` và AS bảo token sender-constrained. RS chỉ kiểm `active=true`, không kiểm DPoP proof của HTTP request.

**Hỏi:** Kẻ giữ bản sao token có thể dùng được không?

> Có nguy cơ. Một claim về key binding không đủ; RS phải xác minh DPoP proof đúng key/method/URI/time/replay trên từng request. Khi token/key bị nghi lộ, vẫn cần containment theo policy.

### Tình huống H — User report sai thiết bị

Một người dùng thuộc tenant A gửi request “revoke device” với ID thuộc tenant B.

**Hỏi:** Backend có được tin ID này không?

> **Không.** Backend phải kiểm ownership từ issuer/subject/tenant/session/grant đã xác minh. Bảo mật chức năng logout không được tạo lỗ hổng **revoke-of-other-users DoS**.

### Câu hỏi tự đánh giá

1. Vì sao logout local không thể ngăn ngay một Bearer token đã bị sao chép?
2. Những dấu hiệu nào đủ để coi token **nghi lộ** dù chưa thấy misuse?
3. Cần phân biệt access token, refresh token, session cookie, OP session và client secret thế nào?
4. Vì sao refresh token compromise thường cần xử lý family/grant?
5. RFC 7009 HTTP 200 nói gì và không nói gì về RS enforcement?
6. Với access JWT tự chứa, những phương án nào giúp revoke trước `exp`?
7. Với opaque token, cache introspection ảnh hưởng việc chặn token ra sao?
8. Revoke grant và OP RP-Initiated Logout có quan hệ gì?
9. Tại sao không được chỉ dùng `sub` trần để logout mọi thiết bị?
10. Một refresh response đến sau logout gây rủi ro gì? Generation guard giải quyết ra sao?
11. Vì sao không nên bắt user re-login trên browser có XSS chưa vá?
12. Trường hợp nào cần reset mật khẩu/MFA, trường hợp nào chỉ cần revoke token?
13. DPoP/mTLS làm giảm replay theo điều kiện nào?
14. Incident logs cần những reference nào, và vì sao không được chứa token?
15. Kiểm thử nào chứng minh RS đã chặn token, không chỉ AS trả revoke success?
16. Khi nào mới được thông báo “đã bảo vệ mọi thiết bị” một cách có cơ sở?

## 35. Ghi nhớ

- **Logout khi token bị nghi lộ là quy trình containment nhiều lớp**, không chỉ xóa localStorage hoặc cookie.
- **Xóa local session không xóa bản sao Bearer access token** đã ra ngoài thiết bị.
- **Refresh token/grant phải được xử lý ưu tiên** nếu bị nghi lộ; rotation/reuse detection có thể cần revoke toàn family và buộc reauthentication.
- **RFC 7009 revocation và OIDC RP/OP logout giải quyết các đối tượng khác nhau**. Kết thúc SSO không tự thu hồi mọi access/refresh token.
- **JWT tự chứa cần denylist/grant state hoặc TTL** để bị chặn trước `exp`; **opaque token** có thể dùng introspection nhưng cache gây độ trễ.
- **Resource server là nơi quyết định thực tế**: `iss`, token type, `aud`, `scope`, `exp`, tenant/owner và revoke enforcement.
- **Phạm vi incident cần được định danh theo issuer + subject + client + grant + tenant + device/session**, tránh revoke nhầm và tránh chặn quá hẹp.
- **OP SSO sessions, RP sessions và các thiết bị khác độc lập**; global logout cần hỗ trợ đồng bộ nhiều hệ thống.
- **Sender-constrained tokens chỉ giảm replay nếu key được bảo vệ và RS kiểm proof**.
- **Khắc phục nguồn lộ trước khi cấp token mới**, nhất là XSS, logs, malware, client secret và signing key compromise.
- **Dùng state PARTIAL và đo revocation latency**; HTTP 200 từ logout/revoke không đủ làm bằng chứng đã chặn.
- **Audit và thông báo phải bảo vệ credentials và chính xác về mức độ đã xử lý**, không công bố kết luận vượt bằng chứng.

### Tài liệu chuẩn tham khảo

- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): yêu cầu và phản hồi revoke access/refresh tokens.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): trạng thái token, `active` và độ trễ cache.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): token theft, refresh-token rotation/sender constraints và security hardening.
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): AS, RS, client, grants, token endpoint.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): Bearer token exposure/replay, lỗi API.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): JWT claims, access token validation, audience và type.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): JWT alg/key confusion và validation hardening.
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449): sender-constrained tokens và proof replay protection.
- [RFC 8705 — OAuth 2.0 mTLS](https://www.rfc-editor.org/rfc/rfc8705): client authentication và certificate-bound access tokens.
- [OpenID Connect RP-Initiated Logout 1.0](https://openid.net/specs/openid-connect-rpinitiated-1_0.html), [Front-Channel Logout](https://openid.net/specs/openid-connect-frontchannel-1_0.html) và [Back-Channel Logout](https://openid.net/specs/openid-connect-backchannel-1_0.html): session logout trong OIDC.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): ID token, authentication session, nonce/reauthentication.
- [OWASP OAuth2 Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/OAuth2_Cheat_Sheet.html) và [OWASP Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): token/session hardening.
- [Spring Security — Logout](https://docs.spring.io/spring-security/reference/servlet/authentication/logout.html), [OIDC Logout](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/logout.html) và [JWT Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): session invalidation, OP logout và JWT validation.
