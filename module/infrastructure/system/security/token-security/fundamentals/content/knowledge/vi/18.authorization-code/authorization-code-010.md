# Code replay protection

Một OAuth client vừa nhận **authorization code** sau khi người dùng đăng nhập và cấp quyền. Client gửi code đến token endpoint để đổi lấy access token. Nếu kẻ tấn công sao chép được code đó rồi gửi lại cùng request sau vài giây, Authorization Server có được phát thêm một bộ token không? **Không. Authorization code phải được sử dụng một lần duy nhất.**

**Code replay** là tình huống cùng một authorization code bị đưa ra đổi lấy token nhiều lần, do kẻ tấn công, do lỗi retry của client hoặc do các yêu cầu chạy đồng thời. Nếu Authorization Server chấp nhận lại code đã dùng, một chứng cứ ủy quyền ngắn hạn có thể bị biến thành phương tiện phát hành nhiều access token hoặc refresh token, vượt ranh giới của một lần ủy quyền.

Bài học thuộc chương **Authorization Code** của module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**. Trọng tâm là cách ngăn authorization code bị phát lại trong OAuth 2.0/OpenID Connect (OIDC), đồng thời liên hệ mô hình tin cậy và vòng đời **JWT, opaque access token, refresh token**, issuer, audience, scope, lưu trữ, thu hồi và những phương án giảm nguy cơ token bị đánh cắp.

Sau khi học, bạn sẽ biết vì sao **authorization code là credential ngắn hạn, dùng một lần**, phân biệt replay code với replay access/refresh token, hiểu cơ chế **atomic redemption**, kiểm **client/redirect URI/PKCE binding**, xử lý trường hợp phản hồi token bị mất, phát hiện sự cố và xây dựng ma trận kiểm thử an toàn.

## 1. Authorization code là gì và vì sao không thể dùng lại?

Trong **Authorization Code Flow**, client chuyển người dùng đến **authorization endpoint** của Authorization Server (AS). AS xác thực người dùng và xử lý ủy quyền khi cần, sau đó gửi **authorization code** về redirect URI hợp lệ của client. Client mang code tới **token endpoint** để xin token.

| Giá trị | Dùng ở đâu? | Mục đích | Có được dùng lại không? |
|---|---|---|---|
| **Authorization code** | Client gửi tới token endpoint của AS | Đổi một lần lấy token theo grant đã được phê duyệt | **Không**, chỉ một lần |
| **Access token** | Client gửi đến Resource Server đúng audience | Truy cập API trong scope và thời hạn được cấp | Có thể được dùng cho nhiều request hợp lệ đến khi hết hạn/thu hồi; cần chống lộ và replay khi phù hợp |
| **Refresh token** | Client gửi tới token endpoint của AS | Xin access token mới khi grant còn hiệu lực | Tùy policy; **rotation** khiến mỗi giá trị refresh token chỉ dùng một lần |
| **OIDC ID token** | Client/Relying Party | Xác minh kết quả xác thực danh tính | Không được dùng thay access token hoặc authorization code |
| **PKCE code_verifier** | Client gửi khi đổi code | Chứng minh bên đổi code sở hữu bí mật gắn với authorization request | Dùng cho đúng giao dịch PKCE, không phải access token |

**Code không phải access token**: Orders API không được chấp nhận authorization code trong header Bearer. **Code cũng không phải refresh token**: không thể gửi nó định kỳ để xin token mới. Code chỉ giúp hoàn tất đúng **một** giao dịch ủy quyền.

Theo **RFC 6749**, authorization code phải có thời gian sống ngắn và **MUST NOT** được client dùng hơn một lần; thời hạn tối đa **10 phút được khuyến nghị**, không phải bắt buộc mọi hệ thống phải để code sống đúng 10 phút. AS phải **từ chối** lần sử dụng thứ hai; khi phát hiện code bị dùng nhiều lần, tiêu chuẩn còn khuyến nghị thu hồi, **nếu có thể**, các token đã phát hành dựa trên code đó.

## 2. Một luồng hợp lệ và một lần replay

~~~mermaid
sequenceDiagram
    actor U as Người dùng
    participant C as OAuth Client
    participant AS as Authorization Server
    participant RS as Orders API
    participant X as Bên gửi lại code
    C->>AS: Authorization request + state + PKCE challenge
    AS->>U: Đăng nhập và ủy quyền khi cần
    U-->>AS: Hoàn tất
    AS-->>C: Redirect với code C1 và state
    C->>C: Kiểm state và flow
    C->>AS: POST /token: code=C1 + code_verifier
    AS->>AS: Kiểm client, redirect, PKCE, TTL
    AS->>AS: Đánh dấu C1 đã tiêu thụ một cách atomic
    AS-->>C: Access token AT1; token khác nếu được phép
    C->>RS: Bearer AT1
    RS-->>C: Kết quả sau khi kiểm quyền
    X->>AS: POST /token: code=C1 thêm lần nữa
    AS->>AS: Phát hiện C1 đã dùng
    AS-->>X: invalid_grant; không cấp token
~~~

Khi token endpoint xử lý request đầu tiên thành công, trạng thái code chuyển từ **có thể đổi** sang **đã tiêu thụ**. Mọi request sau sử dụng cùng code phải bị từ chối, kể cả:

- Request do cùng client hợp pháp gửi lại vì timeout.
- Request do hai tab hoặc hai instance cùng gửi.
- Request của kẻ tấn công có được code từ callback URL hoặc log.
- Request dùng cùng code nhưng thay đổi scope, redirect URI hay PKCE verifier.

**Chỉ nhận diện request lặp dựa trên IP, User-Agent hay client ID là không đủ**. Nhiều người có thể dùng chung IP; một client có thể chạy nhiều instance. Cần ràng buộc trực tiếp **định danh/code handle và trạng thái đã tiêu thụ** trong hệ thống của AS.

## 3. Những lớp bảo vệ nào cùng ngăn code bị lạm dụng?

Replay protection **không chỉ là một cờ used=true**. Authorization Server và client cần nhiều lớp kiểm soát bổ sung:

| Lớp bảo vệ | Chống nguy cơ gì? | Giới hạn |
|---|---|---|
| **Single-use code** | Đổi cùng code nhiều lần | Không tự ngăn kẻ tấn công đổi code **trước** client hợp pháp nếu các bằng chứng khác cũng bị lấy |
| **Short expiration** | Code bị giữ lại lâu rồi đem đổi | Trong thời gian code còn hạn, vẫn cần binding và PKCE |
| **Client binding** | Client B cố đổi code đã cấp cho client A | Public client ID tự nó không phải bí mật xác thực |
| **Redirect URI binding** | Code bị đổi trong ngữ cảnh callback khác giao dịch ban đầu | Không thay thế kiểm tra URI hợp lệ lúc authorization |
| **PKCE** | Code bị chặn nhưng kẻ tấn công không có verifier | Nếu code và verifier cùng bị lộ, PKCE không còn đủ để chặn người giữ cả hai |
| **Client authentication** | Kẻ khác mạo danh confidential client | Secret/khóa client cần được bảo vệ và có thể bị xâm phạm |
| **state và session binding** | Client nhận authorization response không thuộc phiên đã khởi tạo | state không thay cho single-use code ở AS |
| **Issuer/mix-up defense** | Code bị xử lý ở token endpoint sai AS | Cần cấu hình issuer tin cậy và ràng buộc giao dịch |
| **TLS, bảo vệ log và callback** | Code/verifier bị đọc hoặc phát tán trên đường đi | Không chữa lỗi AS cho phép dùng code hai lần |

Mỗi lớp bảo vệ giải quyết một dạng sai lệch riêng. Một client dùng **PKCE tốt** nhưng Authorization Server cho phép **redeem code nhiều lần** vẫn có lỗi. Ngược lại, chỉ đánh dấu code đã dùng mà bỏ PKCE khiến kẻ lấy được code có thể chạy đua để đổi trước client.

## 4. TTL ngắn, entropy cao và trạng thái code

Authorization Server nên phát hành **authorization code khó đoán**, có đủ entropy từ bộ sinh số ngẫu nhiên an toàn hoặc cấu trúc được bảo vệ mật mã theo profile. Code không được lộ cách suy ra từ user ID, timestamp, số thứ tự hay client ID.

Ví dụ vòng đời:

~~~text
09:00:00  AS phát code C1, expires_at=09:05:00
09:00:09  Client đổi C1 hợp lệ => C1 được tiêu thụ
09:00:10  Bên khác gửi C1 => từ chối do đã tiêu thụ
09:05:01  Một code chưa dùng nhưng hết hạn => từ chối do expired
~~~

**5 phút** chỉ là TTL minh họa. Tùy mức rủi ro và trải nghiệm, AS quyết định hạn phù hợp; RFC 6749 khuyến nghị code sống không quá **10 phút**. Việc clock skew hoặc độ trễ mạng cần được giải quyết bằng thiết kế thời gian nhất quán, **không** bằng cách cho phép code hết hạn đổi lấy token.

Một bản ghi code khái niệm:

~~~text
code_digest:        HMAC-or-hash-of-code-handle
issuer_id:          issuer-shop
client_id:          shop-web
redirect_uri:       https://app.example.org/oauth/callback
pkce_challenge:     <stored-S256-challenge>
pkce_method:        S256
subject_ref:        user-42
granted_scope:      orders:read
approved_audience:  orders-api
issued_at:          <server-timestamp>
expires_at:         <server-timestamp>
status:             ISSUED
redeemed_at:        null
issued_token_refs:  []
~~~

Đây là **mô hình dữ liệu**, không phải schema chuẩn hoặc yêu cầu mọi AS phải lưu code ở database. AS có thể dùng mã tham chiếu opaque, code được bảo vệ mật mã hoặc cơ chế quản lý khác, nhưng **vẫn cần ngăn việc đổi cùng code hai lần**. Một code ký tự chứa grant tự thân (**stateless**) cũng phải có cơ chế theo dõi dùng một lần hoặc giải pháp chống replay tương đương; **chỉ kiểm chữ ký và thời gian của code là chưa đủ**.

Code là credential ngắn hạn: không ghi nguyên code vào log, analytics, tracing, ticket hỗ trợ hoặc URL ngoài callback hợp lệ. Khi cần tra cứu, có thể sử dụng handle băm/HMAC với chính sách quản lý dữ liệu phù hợp, không xuất giá trị có thể dùng để redeem.

## 5. Ràng buộc với client và redirect URI

**Authorization code được cấp cho một OAuth client cụ thể**, thường có **client_id** và redirect URI gắn với authorization request. Token endpoint phải kiểm đúng các ràng buộc ấy, ngoài single-use.

Ví dụ ban đầu:

~~~text
client_id:    shop-web
redirect_uri: https://app.example.org/oauth/callback
code:         C1
~~~

Client A nhận code C1; client B không thể đổi C1 chỉ bằng cách biết code. Theo **RFC 6749**, AS phải bảo đảm code được cấp cho client đang đưa code ra đổi; confidential client còn phải **xác thực client** bằng phương thức đã đăng ký.

Trong token request Authorization Code, nếu **redirect_uri** đã được đưa vào authorization request, token request phải chứa **redirect_uri** với giá trị **giống hệt** giá trị ban đầu. AS phải kiểm ràng buộc này:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.org
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code&code=<code-C1>&redirect_uri=https%3A%2F%2Fapp.example.org%2Foauth%2Fcallback&client_id=shop-web&code_verifier=<verifier-C1>
~~~

Ví dụ là **public client** để nhấn mạnh PKCE; confidential client phải xác thực client theo policy.

| Request đổi code | Kết quả dự kiến |
|---|---|
| C1, client shop-web, đúng redirect URI, đúng PKCE và code chưa dùng | Có thể cấp token nếu các điều kiện khác đạt |
| C1, client other-web, dù cùng redirect host | **Từ chối** |
| C1, đúng client nhưng URI có thêm dấu / cuối | **Từ chối** khi không khớp redirect URI gốc |
| C1, đúng client/URI nhưng code đã được tiêu thụ | **Từ chối** |
| C1, đúng client/URI nhưng code hết hạn | **Từ chối** |

**Exact redirect URI matching** phải được AS thực thi tại authorization endpoint đối với URI đã đăng ký; tại token endpoint phải thực thi **binding với chính URI của giao dịch được cấp code**. Việc biết một redirect URI hợp lệ khác của cùng client **không** cho phép đổi code bằng URI không thuộc giao dịch ấy.

## 6. PKCE ngăn code interception nhưng không thay single-use

**Proof Key for Code Exchange (PKCE, RFC 7636)** buộc bên đổi authorization code chứng minh sở hữu một bí mật ngẫu nhiên đã được ràng buộc lúc bắt đầu flow.

~~~mermaid
flowchart LR
    C["Client tạo code_verifier bí mật"] --> H["Tính code_challenge = BASE64URL(SHA256(verifier))"]
    H --> A["Authorization request gửi challenge, S256"]
    A --> AS["AS lưu challenge với code C1"]
    C --> T["Token request: C1 + code_verifier"]
    AS --> V["AS so khớp S256(verifier) với challenge đã lưu"]
    T --> V
    V --> P{"Khớp, code chưa dùng và binding đúng?"}
    P -->|Có| R["Atomic consume, có thể cấp token"]
    P -->|Không| X["invalid_grant"]
~~~

Các điểm quan trọng:

1. Client tạo **code_verifier** ngẫu nhiên, đủ entropy, riêng cho mỗi giao dịch.
2. Client gửi **code_challenge** dẫn xuất (ưu tiên phương thức **S256**) trong authorization request, **không** gửi code_verifier ở bước này.
3. AS liên kết challenge với authorization code.
4. Client giữ verifier trong ngữ cảnh giao dịch an toàn, gửi verifier khi đổi code tại token endpoint.
5. AS kiểm verifier khớp challenge **trước khi phát token**, đồng thời đảm bảo code chưa dùng, chưa hết hạn và đúng client/redirect.

Nếu kẻ tấn công chỉ lấy được **code C1**, họ thường không đổi được code vì không có verifier. Nếu kẻ tấn công lấy được **cả C1 và verifier**, hoặc có quyền chạy mã trong ngữ cảnh client, PKCE không còn đảm bảo một bên nào luôn thắng. AS vẫn chỉ được chấp nhận **một lần đổi**, sau đó xử lý lần lặp lại như tình huống đáng nghi.

**Không cho phép PKCE downgrade tùy tiện**. Nếu authorization request đã đăng ký challenge, token endpoint không được bỏ qua verifier hoặc chấp nhận verifier không khớp. Hệ thống có thể yêu cầu **S256** thay vì hỗ trợ phương thức yếu hơn theo chính sách. PKCE cũng không thay thế **state**, ràng buộc issuer, redirect URI hoặc client authentication phù hợp.

## 7. Bảo vệ giao dịch của client bằng state và issuer

Replay protection tại token endpoint không giải quyết mọi tấn công nhắm vào **callback của client**. Client còn phải bảo vệ liên kết giữa yêu cầu OAuth đã khởi tạo và authorization response quay về.

- **state**: một giá trị khó đoán, gắn với browser/session và giao dịch OAuth, được client kiểm tra khi nhận callback. Nó giúp giảm nguy cơ authorization response injection/CSRF.
- **issuer/Authorization Server binding**: client phải nhớ flow thuộc AS nào, gọi token endpoint **đúng AS đó**. Trong hệ thống nhiều AS, dùng biện pháp chống **mix-up**, chẳng hạn RFC 9207 nếu profile hỗ trợ.
- **PKCE verifier**: lưu cùng giao dịch, không lấy verifier của flow khác để thử đổi code.
- **OIDC nonce**: khi OIDC flow yêu cầu, client kiểm trong ID token như một ràng buộc riêng. Nonce **không thay** state hoặc single-use authorization code.
- **Redirect URI**: callback được AS kiểm exact matching với URI đăng ký; client không được là open redirector làm lộ code/state.

Ví dụ một client tạo **hai giao dịch song song**:

~~~text
Flow F1: state=S1, verifier=V1, expectedIssuer=AS1
Flow F2: state=S2, verifier=V2, expectedIssuer=AS1

Callback cho F1: code=C1, state=S1
=> chỉ dùng V1, redirect URI và token endpoint của F1
~~~

Nếu client lấy **verifier mới nhất** trong biến toàn cục thay vì verifier của đúng state, request có thể bị từ chối hoặc sai ngữ cảnh. Nếu client không kiểm state, kẻ tấn công có thể cố đưa một code của phiên khác vào callback. **Client-side transaction binding và AS-side single-use** là hai chốt an ninh cần đồng thời có.

## 8. Atomic redemption: không chỉ kiểm rồi cập nhật

Đây là lỗi kỹ thuật cốt lõi trong nhiều hệ thống tự triển khai Authorization Server:

~~~text
Request A: đọc code C1, thấy status=ISSUED
Request B: đọc code C1, thấy status=ISSUED
Request A: phát token AT-A
Request B: phát token AT-B
Request A: set status=CONSUMED
Request B: set status=CONSUMED
~~~

Cả hai request được cấp token vì việc **kiểm trạng thái** và **đánh dấu code đã dùng** không được thực hiện như một thao tác thống nhất. Đây là **race condition / TOCTOU** (*time-of-check to time-of-use*).

Yêu cầu cốt lõi là **atomic consume**: đúng một request có thể chuyển code còn dùng được sang trạng thái đã dùng, còn mọi request cạnh tranh phải thấy code không thể đổi nữa.

### 8.1. Một state machine đơn giản

~~~mermaid
stateDiagram-v2
    [*] --> ISSUED: AS tạo code C1
    ISSUED --> CONSUMED: Một request đổi hợp lệ và commit
    ISSUED --> EXPIRED: Hết TTL trước khi được dùng
    ISSUED --> REVOKED: Grant bị vô hiệu hóa
    CONSUMED --> REPLAY_DETECTED: Code C1 xuất hiện lại
    REPLAY_DETECTED --> INCIDENT_REVIEW: Ghi sự kiện và áp policy
    CONSUMED --> [*]
    EXPIRED --> [*]
    REVOKED --> [*]
    INCIDENT_REVIEW --> [*]
~~~

Các trạng thái là **mô hình khái niệm**, không bắt buộc phải được lưu thành từng enum như sơ đồ. **REPLAY_DETECTED** có thể chỉ là audit event; code vẫn là CONSUMED và không bao giờ trở về ISSUED.

### 8.2. Transaction và khóa hàng

Một cách triển khai với kho dữ liệu hỗ trợ transaction:

~~~text
redeemAuthorizationCode(request):
    client = identifyAndAuthenticateClientAsRequired(request)

    beginTransaction()
        grant = selectCodeByDigestForUpdate(hash(request.code))
        if grant missing:
            deny invalid_grant
        if grant.status != ISSUED:
            recordSafeReplaySignalIfConsumed(grant)
            deny invalid_grant
        if grant.expiresAt <= trustedServerNow():
            deny invalid_grant
        if grant.clientId != client.id:
            deny invalid_grant
        if not exactRedirectBindingMatches(grant, request):
            deny invalid_grant
        if not pkceVerifierMatches(grant, request.codeVerifier):
            deny invalid_grant
        if not currentGrantPolicyAllows(grant):
            deny invalid_grant

        grant.status = CONSUMED
        grant.redeemedAt = trustedServerNow()
        persistConsumptionAndTokenIssueTracking(grant)
    commitTransaction()

    # Chỉ request đã commit thành công mới được phép trả token.
    result = issueAndDeliverTokenSafelyForConsumedGrant(grant)
    return result
~~~

Pseudocode chỉ minh họa **thứ tự trách nhiệm**. Hệ thống thực tế cần thiết kế trạng thái phát hành token, lưu liên kết code→token và khả năng khôi phục sao cho **không phát token khi transaction thất bại**. Nếu sau commit việc tạo/gửi token thất bại, code có thể đã bị tiêu thụ: cách khôi phục an toàn là **khởi tạo flow mới**, không đơn giản bật lại code hoặc cho mọi retry tiếp tục nhận token.

### 8.3. Compare-and-swap hoặc unique redemption

Một phương án khác là thực hiện cập nhật có điều kiện, ví dụ SQL khái niệm:

~~~sql
UPDATE authorization_codes
SET status = 'CONSUMED',
    redeemed_at = CURRENT_TIMESTAMP
WHERE code_digest = :code_digest
  AND status = 'ISSUED'
  AND expires_at > CURRENT_TIMESTAMP;
~~~

**Chỉ khi số hàng bị cập nhật chính xác bằng 1** request mới được coi đã giành quyền tiêu thụ code. Phải xác minh **client, redirect URI, PKCE, issuer/grant** bằng dữ liệu tin cậy và cơ chế transaction/locking phù hợp trước hoặc cùng bước tiêu thụ; câu SQL trên **không tự kiểm hết các điều kiện**, cũng không phải đoạn mã dùng nguyên xi cho mọi database.

Trong hệ thống phân tán, không thể chỉ dùng **mutex trong bộ nhớ một instance** nếu các instance khác cùng xử lý token endpoint. Cần trạng thái dùng một lần mang tính nhất quán ở nơi chia sẻ, transaction/locking hoặc primitive atomic tương đương.

## 9. Chú ý thứ tự phát token, commit và phản hồi HTTP

Tránh ba lỗi đặc biệt:

**Lỗi A – phát token trước khi kiểm code đã được consume:** hai request song song có thể cùng nhận token hợp lệ.

**Lỗi B – đánh dấu dùng rồi rollback nhưng vẫn gửi token:** database trở về ISSUED, trong khi client đã nhận token. Code có thể bị đổi lại. Không gửi response token thành công trước khi trạng thái bảo vệ single-use đã được commit ổn định.

**Lỗi C – commit đã dùng, lỗi mạng làm mất response:** client không biết AS đã phát token hay chưa; request retry bằng cùng code phải **không tạo thêm token**. Nếu AS chỉ chấp nhận một lần dùng, client nên bắt đầu authorization flow mới khi không thể khôi phục an toàn.

Với JWT access token tự chứa, token có thể được ký rất nhanh, nhưng điều đó **không bỏ yêu cầu theo dõi trạng thái code đã tiêu thụ**. Với opaque token, AS còn cần lưu mapping và trạng thái token, gắn với grant. Các bước tiêu thụ code, ghi nhận token đã cấp và xuất response phải được thiết kế nhất quán để không có đường đua tạo nhiều token từ cùng code.

**Không biến Authorization Code grant thành một API idempotent trả lại cùng bộ token khi caller cứ gửi lại code cũ**, trừ khi có một cơ chế chuyên biệt đã được phân tích bảo mật rất kỹ và tuân thủ yêu cầu single-use. Theo luồng OAuth thông thường, code đã dùng là **invalid_grant**, không phải “retry để lấy thêm token”.

## 10. HTTP token request, response và lỗi replay

Một yêu cầu đổi code hợp lệ:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.org
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code&code=<C1>&redirect_uri=https%3A%2F%2Fapp.example.org%2Foauth%2Fcallback&client_id=shop-web&code_verifier=<V1>
~~~

Response thành công **chỉ cho lần đổi hợp lệ đầu tiên** có thể là:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "access_token": "<new-access-token>",
  "token_type": "Bearer",
  "expires_in": 900,
  "scope": "orders:read",
  "refresh_token": "<refresh-token-if-issued>"
}
~~~

Các giá trị đều là **placeholder**, không phải credential thật. **expires_in=900** là thời hạn access token minh họa 15 phút, không phải TTL của authorization code hoặc refresh token. AS chỉ cấp refresh token nếu flow/client/chính sách cho phép.

Sau khi code C1 đã được tiêu thụ, client hoặc bên khác gửi lại cùng code:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.org
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code&code=<C1>&redirect_uri=https%3A%2F%2Fapp.example.org%2Foauth%2Fcallback&client_id=shop-web&code_verifier=<V1>
~~~

AS trả về lỗi theo OAuth 2.0:

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "error": "invalid_grant"
}
~~~

**invalid_grant** có thể có nhiều nguyên nhân: code sai, hết hạn, đã dùng, không thuộc client, redirect binding sai, PKCE mismatch hoặc những tình huống grant không hợp lệ khác. Vì vậy **không tiết lộ công khai** liệu một code cụ thể đã từng hợp lệ hay đã bị sử dụng; giữ chi tiết nhạy cảm ở audit nội bộ với quyền xem phù hợp.

**Không phải mọi lỗi token endpoint đều là HTTP 400**: nếu xác thực confidential client thất bại, **invalid_client** có các quy tắc HTTP/challenge tương ứng. Client không được coi mọi lỗi là dấu hiệu có thể retry cùng code vô hạn.

## 11. Phát hiện code replay và thu hồi token đã cấp

**RFC 6749 yêu cầu từ chối code được dùng nhiều hơn một lần**. Khi code đã được đổi thành công nhưng sau đó lại xuất hiện, AS **nên thu hồi các token trước đây đã cấp dựa trên code đó nếu có thể**. Mục đích là xử lý trường hợp kẻ tấn công có thể đã đổi code trước, trong khi client hợp pháp vừa đưa code ra đổi và nhận lỗi.

Ví dụ hai khả năng:

| Tình huống | Ai đổi code trước? | Tín hiệu quan sát được | Hướng xử lý |
|---|---|---|---|
| Client hợp pháp đổi trước, attacker thử sau | Client | Code đã CONSUMED; có request replay | Từ chối; điều tra nguy cơ lộ code, thu hồi token liên quan theo policy |
| Attacker có code và đủ proof, đổi trước | Attacker | Client hợp pháp nhận invalid_grant khi đổi | Từ chối lần sau; đánh dấu có nguy cơ lộ token đã cấp, thu hồi nếu có thể |
| Client gửi retry do mất HTTP response | Có thể là chính client | Code đã CONSUMED, không chắc có tấn công | Từ chối replay; đánh giá false positive nhưng không cho đổi lần nữa |

**AS không thể biết chắc request đầu hay sau là của ai chỉ bằng việc code được dùng lại**. IP/User-Agent hoặc thời gian có thể giúp điều tra, nhưng không chứng minh sở hữu hợp pháp. Đừng cấp thêm token để “sửa” lỗi retry.

### Theo dõi token phát hành từ code

Khi AS cấp access token/refresh token, có thể lưu liên kết với **authorization grant, code redemption record, client, subject và token identifiers** để hỗ trợ thu hồi có chọn lọc. Với opaque access token, AS có thể cập nhật trạng thái để introspection báo **active=false**. Với JWT access token tự chứa được Resource Server kiểm tại chỗ, cần cơ chế **denylist/jti, grant epoch, kiểm tra phiên hoặc tuổi token ngắn** nếu muốn vô hiệu hóa trước exp; chỉ thu hồi refresh token không làm JWT cũ tự hết hiệu lực.

**Thu hồi khi code replay không đồng nghĩa phải xoay toàn bộ signing key hoặc khóa mọi tài khoản**. Phạm vi phản ứng phụ thuộc tín hiệu, loại token, mức rủi ro và khả năng khoanh vùng. Nếu private key của issuer bị lộ mới cần quy trình thu hồi gốc tin cậy mạnh hơn.

## 12. Retry, timeout và nhiều tab: tránh gây replay do chính client

Lỗi replay không nhất thiết do kẻ tấn công. Ví dụ:

1. Client gửi đổi code C1.
2. AS tiêu thụ C1 và tạo token.
3. Response bị timeout hoặc kết nối bị ngắt trước khi client đọc được.
4. HTTP client tự retry POST đổi code C1.
5. AS từ chối vì C1 đã được sử dụng.

**Client không nên tự động retry một token request chứa authorization code như một GET idempotent**. Nếu không nhận được token response và không thể khôi phục theo thiết kế an toàn, nên **khởi tạo lại authorization flow**, tạo state, PKCE verifier và code mới. Không ghi code cũ vào log để phân tích retry.

### Tránh hai lần đổi code ở client

- Callback handler phải nhận diện **state đã được xử lý**, chống một URL callback bị load lại tạo hai token requests.
- Hai tab cùng nhận cùng callback không được cùng redeem một code; nếu một tab đã xử lý, tab kia nên dừng ở trạng thái lỗi/đã hoàn thành.
- Backend nhiều instance nên có **transaction state one-time** hoặc cơ chế phối hợp phù hợp, không chỉ giữ cờ local trong một tiến trình.
- HTTP interceptors không được âm thầm retry các token requests không idempotent; cân nhắc chính sách retry theo từng grant.
- Nếu browser người dùng bấm Refresh tại callback URL, client không được lập lại đổi code đã dùng.

Ví dụ timeline:

~~~text
10:00:00  Client nhận callback code=C1, state=S1
10:00:01  Callback handler A bắt đầu token request
10:00:01  Callback handler B do double navigation cũng bắt đầu
10:00:02  AS chấp nhận đúng một redemption
10:00:02  Request còn lại nhận invalid_grant
~~~

**AS vẫn phải chống race condition kể cả khi client có cơ chế single-flight.** Sự nhất quán ở client là giảm lỗi và cảnh báo giả; atomic single-use tại AS mới là ranh giới an ninh quyết định.

## 13. Replay của authorization code khác replay của các token khác

| Tình huống replay | Bên phải bảo vệ | Cơ chế đặc trưng |
|---|---|---|
| **Authorization code** được đổi nhiều lần | Token endpoint của Authorization Server | Single-use atomic, TTL ngắn, client/redirect/PKCE binding, phát hiện reuse |
| **Refresh token** đã rotation bị dùng lại | Authorization Server | Rotation và phát hiện reuse/token family, client binding, sender-constraining |
| **Bearer access token** bị gửi lại khi còn hạn | Resource Server và client/AS | TLS, bảo vệ lưu trữ, audience/scope/TTL, thu hồi và DPoP/mTLS khi hỗ trợ |
| **OIDC ID token** bị dùng sai hoặc phát lại ở client | OIDC client/Relying Party | Kiểm issuer, audience, thời hạn, nonce theo flow và session binding |
| **Message nghiệp vụ** bị broker redeliver | Producer/consumer, hệ thống nghiệp vụ | Message ID, job state, idempotency key và policy tại thời điểm thực thi |

**Không lấy cơ chế rotation refresh token để thay cho single-use code**: cả hai có thể dùng trạng thái một lần, nhưng grant, bên nhận và hậu quả khác nhau. **Không coi việc một access token được gửi nhiều lần đến API là lỗi code replay**: một bearer access token bình thường có thể được sử dụng cho nhiều request trong hạn, nếu chính sách chấp nhận. Chống phát lại access token ở mức yêu cầu cần cơ chế sender-constraining và proof/nonce đúng giao thức khi áp dụng.

## 14. Bảo vệ redirect URI, callback, log và đường truyền

Authorization code thường đi qua browser redirect dưới dạng **query parameter** trong Authorization Code Flow. Nó là credential ngắn hạn, vì vậy phải bảo vệ cả đường đi:

### Redirect URI exact matching

AS chỉ redirect tới URI đã được đăng ký cho **đúng client**, không dùng wildcard hoặc prefix. Ví dụ:

~~~text
Registered:
https://app.example.org/oauth/callback

Không chấp nhận thay thế:
https://app.example.org/oauth/callback/
https://app.example.org.attacker.example/oauth/callback
https://app.example.org/open-redirect?next=https://attacker.example
~~~

AS không được gửi cả **code hoặc error response** tới URI mà nó không xác minh được thuộc client. Callback phía client cũng không được là **open redirect** cho phép chuyển code/state sang domain lạ.

### Không ghi secrets

- **Không ghi raw callback URL** chứa code/state vào proxy log, tracing, crash report hoặc analytics.
- **Không ghi code_verifier** từ token request form body, cũng không ghi client secret/private key assertion.
- Hạn chế third-party scripts trên callback; xem xét **Referrer-Policy: no-referrer** và xử lý code/state để tránh phát tán trong URL.
- Không truyền authorization code qua message broker, queue retry hoặc email để worker đổi sau.
- Dùng **HTTPS/TLS** cho authorization/token endpoints và callback web; ngoại lệ HTTP loopback native app theo **RFC 8252** phải được giới hạn đúng loại client.

**Code hết hạn không có nghĩa các bản sao trong log trở nên vô hại về quyền riêng tư**; giá trị state/correlation và metadata đi kèm vẫn có thể tiết lộ hành vi hoặc ngữ cảnh tài khoản. Phòng ngừa và giảm thu thập vẫn cần thiết.

## 15. Ví dụ kiến trúc Java: khóa giao dịch khi redeem

Trong Java, một Authorization Server tự triển khai phải đảm bảo code **được khóa/tiêu thụ** bằng primitive có tính nhất quán, thay vì dùng **ConcurrentHashMap** trong một instance nếu hệ thống chạy nhiều instance.

Một ví dụ thiết kế dạng Java/pseudocode:

~~~java
// MẪU THIẾT KẾ: các lớp Repository, Grant, Policy... chỉ là mô phỏng.
// Không phải một OAuth Authorization Server hoàn chỉnh.

@Transactional
public RedemptionRecord consumeCode(CodeExchangeRequest request,
                                    AuthenticatedClient client) {
    // Tìm theo digest, khóa bản ghi ở kho trạng thái dùng chung.
    AuthorizationCodeGrant grant =
            codeRepository.findByDigestForUpdate(
                    secureDigest(request.code()));

    if (grant == null || !grant.isIssued()) {
        throw invalidGrant();
    }
    if (grant.isExpired(trustedClock.instant())) {
        throw invalidGrant();
    }
    if (!grant.belongsTo(client.id())) {
        throw invalidGrant();
    }
    if (!grant.redirectUriBindingMatches(request.redirectUri())) {
        throw invalidGrant();
    }
    if (!pkceVerifier.verifyS256(
            request.codeVerifier(), grant.codeChallenge())) {
        throw invalidGrant();
    }
    if (!grantPolicy.stillAllowed(grant, client)) {
        throw invalidGrant();
    }

    grant.consume(trustedClock.instant());
    return redemptionRepository.recordForTokenIssuance(grant);
}
~~~

Đoạn ví dụ có các ý chính:

1. **Repository transaction và row lock** phải hoạt động trên **state dùng chung** của mọi instance. Annotation **@Transactional** đơn độc **không đủ** nếu repository không thật sự khóa/cập nhật atomic.
2. Lấy code bằng một **digest an toàn** thay vì in raw code ra log; code cần entropy cao. Cơ chế digest/HMAC và key management phải phù hợp kiến trúc.
3. Kiểm client, redirect URI, PKCE, TTL và policy **trước khi đánh dấu sử dụng**.
4. Ghi trạng thái CONSUMED và redemption record nhất quán; **token issuance/response phải được thiết kế để không trả token trước khi commit thành công**.
5. Nếu request cùng code đến sau, nó phải gặp **invalid_grant** dù đến một instance khác.

Thực tế nên dùng Authorization Server/framework OAuth được duy trì và có cơ chế single-use code sẵn, cấu hình đúng PKCE, client authentication, redirect URI, issuer và storage. Ví dụ không thay thế security review, test race condition hoặc chuẩn OAuth 2.0.

## 16. Ma trận kiểm thử Code replay protection

| Tình huống | Kết quả mong đợi |
|---|---|
| Code hợp lệ, chưa dùng, đúng client/redirect/PKCE, grant còn phép | **Chỉ một lần** cấp token phù hợp |
| Code hợp lệ được gửi lại sau khi đổi thành công | **invalid_grant**, không phát thêm token |
| Hai request đồng thời dùng cùng code trên một instance | Tối đa một request có quyền redeem |
| Hai request đồng thời trên hai AS instances | Tối đa một request có quyền redeem qua state dùng chung |
| Code chưa dùng nhưng đã quá TTL | Từ chối, không phát token |
| Code không tồn tại hoặc giá trị ngẫu nhiên | Từ chối, không tiết lộ code có tồn tại |
| Code của client A gửi bởi client B | Từ chối |
| Code đúng client nhưng redirect_uri sai một ký tự | Từ chối |
| Code đúng client/URI nhưng thiếu hoặc sai PKCE verifier | Từ chối |
| Code được cấp với PKCE challenge nhưng AS bỏ qua verifier | Test phải **phát hiện lỗi**; không cho cấp token |
| Client callback dùng state không thuộc phiên hoặc đã dùng | Client từ chối, không đổi code |
| Callback từ issuer B bị xử lý như flow issuer A | Từ chối/chặn AS mix-up |
| Callback open redirect gửi code sang domain lạ | Phải chặn; code không được phát tán |
| HTTP response token bị mất, client retry cùng code | AS từ chối replay; không tạo token mới |
| Retry tự động của HTTP client sau timeout | Không dẫn đến cấp nhiều token; client có đường khôi phục an toàn |
| Code đã dùng xuất hiện lại và AS có token lineage | Từ chối, kích hoạt event và thu hồi token liên quan nếu chính sách/khả năng cho phép |
| JWKS/key/issuer bị thu hồi sau khi cấp token | RS không tiếp tục tin nguồn bị ảnh hưởng theo policy |
| Code hợp lệ bị gửi trong Authorization Bearer tới Orders API | RS từ chối vì sai loại credential |
| Token đã phát cho orders-api được gửi sang payments-api | Payments API từ chối do sai audience |
| Token hợp lệ nhưng thiếu scope/tài nguyên thuộc tenant khác | Resource Server từ chối phân quyền |
| Log, APM, tracing và analytics được bật | Không chứa raw code, code_verifier, access/refresh token |
| Redelivery của message nghiệp vụ sau authorization flow | Không dùng lại code; side effect được bảo vệ bằng idempotency riêng |

**Kiểm thử concurrency phải kiểm số token hoặc grant records thực sự được phát hành**, không chỉ đếm HTTP 200/400. Trong môi trường có queue, nhiều worker và gateway, test cũng cần kiểm không có đường khác âm thầm redeem code thay client.

## 17. Quan sát và ứng cứu sự kiện code bị dùng lại

Khi AS phát hiện code đã tiêu thụ xuất hiện lần nữa, nên ghi một **security event không chứa credential thô**, ví dụ:

~~~json
{
  "event": "authorization_code_reuse_detected",
  "client_id": "shop-web",
  "issuer_id": "issuer-shop",
  "grant_ref": "grant-example-710",
  "result": "denied",
  "reason_code": "CODE_ALREADY_CONSUMED",
  "request_id": "req-example-184"
}
~~~

Các giá trị là ví dụ. **grant_ref** là định danh nội bộ phải được kiểm soát truy cập/retention; không dùng raw code hoặc raw token làm khóa tương quan. Nếu cần liên kết code, sử dụng một định danh/digest nội bộ được thiết kế an toàn và không thể dùng lại làm credential.

**Không kết luận mọi lần reuse đều là tấn công.** Retry do mạng, callback xử lý hai lần hoặc nhiều instance có thể gây báo động; nhưng AS vẫn phải từ chối theo nguyên tắc một lần. Dữ liệu vận hành có thể hỗ trợ xác định:

- Code có được đổi thành công trước đó không, token nào liên quan?
- Có bất thường về client authentication, source network, User-Agent và timing không?
- Có nhiều lần thất bại PKCE, sai redirect hoặc code replay trên cùng client không?
- Có dấu hiệu code/verifier bị lộ trong log, analytics hoặc browser callback không?
- Refresh token được cấp từ grant đó đã được sử dụng, rotation/reuse có bất thường không?

Ứng cứu tùy tình huống: hạn chế truy cập log, chặn nơi phát tán code, thu hồi token liên quan nếu có thể, yêu cầu xác thực lại và bổ sung kiểm thử. **Không sửa lỗi replay bằng cách kéo dài TTL hoặc cho phép code được dùng hai lần.**

## 18. Checklist trước khi đưa Authorization Code Flow vào production

1. **Code lifecycle:** authorization code có entropy cao, TTL ngắn, single-use và trạng thái tiêu thụ đáng tin không?
2. **Atomicity:** có row lock/CAS/transaction hoặc cơ chế tương đương bảo đảm tối đa một lần redeem trên mọi AS instance?
3. **Client binding:** code được gắn với đúng client; confidential client có xác thực đúng phương thức không?
4. **Redirect URI:** exact matching tại authorization endpoint; redirect_uri ở token request khớp ngữ cảnh ban đầu?
5. **PKCE:** code_challenge gắn với code, code_verifier được kiểm và không có đường fallback bypass?
6. **state:** client có kiểm callback thuộc đúng phiên/giao dịch, tránh CSRF và xử lý trùng không?
7. **Issuer:** nếu nhiều AS, code được đổi ở đúng token endpoint, có chống mix-up và xác minh issuer?
8. **One-time response:** token chỉ được trả sau khi commit bảo vệ single-use; mất response không cho retry cấp token mới?
9. **Revocation:** AS có thể liên kết code với token để xử lý code reuse theo khuyến nghị RFC 6749 và policy không?
10. **Access/refresh:** access token được cấp đúng issuer/audience/scope/TTL; refresh token chỉ cấp khi client/flow được phép?
11. **RS validation:** Resource Server có từ chối code, ID token, refresh token và access token sai audience không?
12. **Secret hygiene:** callback, token endpoint, proxy, logs, tracing, analytics và support tools có loại raw code/verifier/token không?
13. **Error handling:** code đã dùng/hết hạn/sai PKCE được từ chối, lỗi công khai không tiết lộ chi tiết nhạy cảm?
14. **Concurrency:** có test hai request cùng code trên nhiều instance và trường hợp transaction rollback, response lost không?
15. **Incident response:** có đường thu hồi token, vô hiệu hóa grant, điều tra lộ code và giảm false positive do client retry không?
16. **Authorization:** khi access token đã cấp, RS vẫn kiểm scope, audience và quyền trên từng tài nguyên thay vì tin riêng việc flow hoàn tất?

## 19. Câu hỏi tự đánh giá

**1. Authorization code có được đổi hai lần lấy token không?** Không. AS phải từ chối code đã dùng, bất kể request thứ hai đến từ client hay kẻ tấn công.

**2. Code chỉ sống 5 phút thì có thể bỏ theo dõi trạng thái đã dùng không?** Không. Trong 5 phút đó, cùng code vẫn có thể bị đổi nhiều lần nếu AS không thực thi single-use.

**3. PKCE đã đủ chống code replay chưa?** Chưa. PKCE ràng buộc code với verifier và giảm nguy cơ code interception; AS vẫn phải đảm bảo **atomic single-use**.

**4. Nếu kẻ tấn công có code nhưng không có verifier thì sao?** AS phải từ chối đổi code khi PKCE yêu cầu verifier hợp lệ, ngay cả khi code chưa hết hạn.

**5. Tại sao cần transaction khi đánh dấu code đã dùng?** Để hai request song song không cùng thấy code chưa dùng rồi đều nhận token.

**6. Nếu response đầu tiên từ token endpoint bị mất, client có thể retry code và nhận token lần nữa không?** Không theo semantics một lần. Client nên xử lý lỗi và khởi tạo lại authorization flow khi không thể khôi phục an toàn.

**7. RFC 6749 nói gì về code bị dùng nhiều lần?** AS phải từ chối lần dùng lại và **nên thu hồi khi có thể** các token đã phát dựa trên code đó, nhằm giảm thiệt hại nếu kẻ tấn công đổi code trước.

**8. state và OIDC nonce có cùng chức năng với single-use code không?** Không. state liên kết authorization response với phiên client, nonce có vai trò trong kiểm chứng OIDC ID token theo flow; single-use nằm ở cơ chế đổi code tại AS.

**9. Nếu token được cấp hợp lệ, Orders API có thể bỏ qua scope/audience không?** Không. Resource Server phải xác minh access token dành cho chính API và quyền với tài nguyên cụ thể.

**10. Có nên ghi authorization code vào log để điều tra replay?** Không. Ghi security event an toàn với request ID, mã lỗi và tham chiếu nội bộ được bảo vệ; không lưu credential thô.

**Ghi nhớ:** **Authorization code là credential ngắn hạn chỉ được đổi một lần, không phải access token hay refresh token.** Chống code replay cần **TTL ngắn, client/redirect binding, PKCE, state/issuer binding tại client và đặc biệt là atomic redemption tại Authorization Server**. Code đã dùng phải bị từ chối ở mọi instance; nếu có dấu hiệu reuse, AS cần đánh giá và thu hồi token liên quan khi có thể theo chính sách. Sau khi phát token, Resource Server vẫn có trách nhiệm xác minh **issuer, audience, scope, thời hạn và quyền tài nguyên**: bảo vệ code là một mắt xích của toàn bộ vòng đời token, không phải sự thay thế cho xác thực và phân quyền.
