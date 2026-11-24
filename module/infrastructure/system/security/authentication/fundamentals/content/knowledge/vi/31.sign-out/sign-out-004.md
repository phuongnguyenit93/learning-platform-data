# Token logout — Thu hồi token và kết thúc quyền truy cập

**Token logout** là quy trình làm cho một hoặc nhiều token không còn được chấp nhận, đồng thời cập nhật trạng thái phiên và xóa bản sao credential ở client. Trong OAuth 2.0, việc thu hồi token thường được thực hiện qua **revocation endpoint** theo RFC 7009. Hành động này khác với việc chỉ xóa token khỏi bộ nhớ ứng dụng: nếu server vẫn chấp nhận token đã bị sao chép, attacker vẫn có thể sử dụng nó.

Đăng xuất có thể chỉ áp dụng cho thiết bị hiện tại, cho một phiên, cho một token family hoặc cho toàn bộ tài khoản. Thiết kế phải nói rõ phạm vi đó, vì access token đã phát hành có thể tiếp tục hợp lệ tới khi hết hạn nếu resource server chỉ kiểm tra chữ ký JWT cục bộ. Thu hồi refresh token cũng không tự động làm mọi access token đang tồn tại mất hiệu lực tức thì trong mọi kiến trúc.

Bài học thuộc module SECURITY_AUTHENTICATION_FUNDAMENTALS, tập trung vào credential, token, session, ranh giới tin cậy và khôi phục tài khoản. Người học cần hiểu token lifecycle, phân biệt logout ở client với revocation phía server, lựa chọn cách lan truyền trạng thái thu hồi và thiết kế luồng an toàn khi timeout, retry hoặc token bị đánh cắp.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt xóa token cục bộ, thu hồi token tại authorization server và kết thúc session.
2. Giải thích vai trò của OAuth revocation endpoint theo RFC 7009.
3. Phân biệt access token, refresh token, ID token và token family trong ngữ cảnh logout.
4. Mô tả vì sao JWT access token có thể còn hiệu lực sau khi refresh token đã bị thu hồi.
5. Chọn cơ chế thu hồi phù hợp: introspection, denylist, session version, token family state hoặc access token lifetime ngắn.
6. Thiết kế logout một thiết bị, logout mọi thiết bị và phản ứng khi token bị lộ.
7. Xử lý propagation, cache, race condition, timeout và retry một cách idempotent.
8. Phân biệt OAuth token revocation với OpenID Connect RP-Initiated Logout và logout tại ứng dụng.
9. Bảo vệ token trong request, log, storage và audit.
10. Viết bộ kiểm thử cho token revoked, token replay, session logout và độ trễ thu hồi.

## 2. Logout có nhiều lớp

Một ứng dụng thường có ít nhất ba nơi lưu trạng thái truy cập:

- **Client:** giữ access token, refresh token hoặc cookie phiên trong memory, secure storage hay server-side session store.
- **Authorization server:** quản lý grant, refresh token, token family, consent và trạng thái phiên/ủy quyền.
- **Resource server:** kiểm tra access token khi API nhận request; có thể xác minh JWT cục bộ, introspect token hoặc tra trạng thái thu hồi.

Logout đầy đủ thường phối hợp nhiều thao tác:
1. Đánh dấu phiên local không còn hoạt động và ngăn request mới dùng phiên đó.
2. Gửi yêu cầu thu hồi refresh token hoặc grant tới authorization server theo policy.
3. Thu hồi token family hoặc các token liên quan nếu kiến trúc hỗ trợ.
4. Xóa token/cookie phía client và xóa cache token trong ứng dụng.
5. Làm cho resource server ngừng chấp nhận access token theo yêu cầu thời gian thu hồi.
6. Ghi audit event và hiển thị đúng phạm vi logout cho người dùng.

~~~mermaid
sequenceDiagram
    actor U as Người dùng
    participant C as Client / BFF
    participant AS as Authorization Server
    participant DB as Token + Session Store
    participant RS as Resource Server
    U->>C: Chọn đăng xuất
    C->>C: Chặn request mới, đánh dấu local session pending logout
    C->>AS: POST revocation endpoint với refresh token
    AS->>DB: Thu hồi token / family / grant theo policy
    DB-->>AS: Trạng thái revoked
    AS-->>C: HTTP 200
    C->>C: Xóa token local và cookie/session
    RS->>AS: Introspection hoặc kiểm tra trạng thái nếu kiến trúc dùng
    AS-->>RS: Token inactive
    C-->>U: Đã đăng xuất theo phạm vi thông báo
~~~

Không phải mọi kiến trúc đều gọi introspection sau mỗi request. Sơ đồ cho thấy một cách triển khai có kiểm tra trạng thái tập trung; hệ thống dùng JWT offline cần cơ chế khác để giới hạn thời gian token còn được chấp nhận.

## 3. Xóa token cục bộ không phải là thu hồi token

Nếu client chỉ xóa access token khỏi memory và refresh token khỏi storage, token đã bị sao chép trước đó vẫn có thể được dùng. Ví dụ attacker lấy refresh token từ thiết bị bị nhiễm malware; người dùng bấm logout nhưng ứng dụng không gọi revocation endpoint. Attacker có thể tiếp tục đổi refresh token lấy access token mới.

| Thao tác | Điều gì thay đổi? | Giới hạn |
| --- | --- | --- |
| Xóa token ở client | Ứng dụng hiện tại không còn giữ token | Không làm token đã bị sao chép mất hiệu lực ở nơi khác. |
| Xóa cookie phiên | Browser không gửi cookie đó trong request sau | Server-side session có thể vẫn active nếu không bị revoke. |
| Thu hồi refresh token | Authorization server từ chối refresh token đã thu hồi | Access token đã phát hành có thể còn hiệu lực tới khi hết hạn hoặc được kiểm tra trạng thái. |
| Thu hồi token family/grant | Các refresh token liên quan trong family/grant bị vô hiệu theo policy | Không đảm bảo mọi JWT access token tự chứa biến mất tức thì ở mọi resource server. |
| Kết thúc IdP/SSO session | Phiên đăng nhập tại identity provider được kết thúc theo giao thức | Không nhất thiết thu hồi mọi token của mọi relying party nếu không có phối hợp. |

Một nút “Đăng xuất” nên thực hiện cả phần local cleanup và server-side revocation khi token architecture hỗ trợ. Nếu revocation endpoint tạm lỗi, client cần giữ trạng thái logout pending, retry an toàn hoặc hiển thị rõ giới hạn; không được tuyên bố chắc chắn rằng token đã bị thu hồi khi server chưa xác nhận.

## 4. OAuth 2.0 Token Revocation — RFC 7009

RFC 7009 định nghĩa endpoint để client thông báo authorization server rằng token không còn cần thiết và nên bị thu hồi. Endpoint thường nhận request HTTP POST với form-urlencoded body qua TLS.

Ví dụ minh họa thu hồi refresh token:

~~~http
POST /oauth/revoke HTTP/1.1
Host: auth.studyhub.example
Authorization: Basic <client-credentials>
Content-Type: application/x-www-form-urlencoded

token=<refresh-token-value>&token_type_hint=refresh_token
~~~

Các điểm cần nhớ:
- `token` là giá trị token cần thu hồi; gửi qua TLS và không ghi vào log.
- `token_type_hint` là gợi ý để authorization server tra cứu loại token; đây không phải bằng chứng về loại token và có thể bị bỏ qua.
- Confidential client phải xác thực theo phương thức đã đăng ký. Public client không được giả vờ có client secret bí mật.
- Authorization server có thể thu hồi token liên quan trong cùng grant theo policy và yêu cầu của RFC.
- Theo RFC 7009, response thành công HTTP 200 được dùng cả khi token đã được thu hồi hoặc token không hợp lệ/không tồn tại; client không nên dùng response này để suy ra token trước đó chắc chắn còn active.
- Lỗi xác thực client hoặc request không hợp lệ vẫn cần được xử lý theo response/error semantics của endpoint.

Ví dụ response:

~~~http
HTTP/1.1 200 OK
Cache-Control: no-store
Pragma: no-cache
~~~

### 4.1. Thu hồi access token hay refresh token?

Nếu client đang giữ cả access token và refresh token, thường nên thu hồi refresh token trước hoặc cùng lúc để ngăn cấp access token mới. Nếu authorization server hỗ trợ thu hồi access token và policy cần, client có thể gửi thêm request revoke cho access token. Tuy nhiên, việc revoke một token có thể ảnh hưởng token liên quan tùy grant và implementation; phải hiểu semantics của nhà cung cấp.

Không giả định một request revoke refresh token tự động vô hiệu mọi access token đã cấp trước đó. Đặc biệt với JWT access token được resource server xác minh offline, chữ ký và `exp` vẫn có thể hợp lệ sau khi refresh token bị revoke.

## 5. Access token, refresh token và token family

| Token | Vai trò | Xử lý khi logout |
| --- | --- | --- |
| Access token | Truy cập resource server trong scope/audience được cấp | Revoke nếu endpoint/policy hỗ trợ; nếu self-contained JWT thì cần introspection/denylist/session check hoặc chờ hết hạn. |
| Refresh token | Xin access token mới tại authorization server | Nên thu hồi để ngăn cấp token mới; khi rotation, cân nhắc thu hồi cả family. |
| ID token | Assertion về sự kiện xác thực cho OIDC client | Không dùng như bearer token gọi API; logout OIDC/IdP session là quy trình riêng. |
| Session cookie | Tham chiếu phiên ứng dụng hoặc BFF | Xóa ở browser và revoke server-side session. |

Với refresh token rotation, các token kế tiếp có thể thuộc cùng một **token family**. Logout hoặc sự cố compromise có thể thu hồi token hiện tại và mọi token trong family để không còn nhánh refresh hoạt động. Nếu hệ thống có nhiều thiết bị, mỗi thiết bị/session nên có family hoặc grant reference riêng để hỗ trợ logout một thiết bị.

### 5.1. Logout một thiết bị và logout mọi thiết bị

Hai hành động có phạm vi khác nhau:
- **Logout thiết bị hiện tại:** revoke session/token family gắn với phiên đang dùng; các thiết bị khác tiếp tục hoạt động.
- **Logout mọi thiết bị:** revoke tất cả session, refresh token family hoặc grant liên quan tới tài khoản; resource server cần nhận biết trạng thái mới theo SLA thu hồi.

Không dùng một cờ `user.loggedOut=true` duy nhất nếu sản phẩm cần quản lý nhiều thiết bị. Cần lưu session/device reference và cho phép người dùng xem, thu hồi phiên cụ thể. Với tài khoản bị compromise nghiêm trọng, có thể revoke toàn bộ và yêu cầu đăng nhập lại.

## 6. Vì sao JWT access token có thể còn hiệu lực sau logout?

JWT thường chứa claims và chữ ký. Resource server có thể kiểm tra chữ ký, issuer, audience, `exp`, scope và các claim cần thiết mà không gọi authorization server mỗi lần. Cách xác minh offline giảm độ trễ và tăng khả năng phục vụ, nhưng resource server không tự biết một token vừa bị thu hồi ở nơi khác.

Ví dụ:
1. Authorization server phát hành access token JWT có `exp` sau 10 phút.
2. Người dùng logout ở phút thứ 2 và refresh token bị revoke.
3. Resource server vẫn xác minh chữ ký JWT thành công ở phút thứ 3.
4. Nếu không có kiểm tra trạng thái bổ sung, token có thể được chấp nhận tới `exp`.

Đây là trade-off giữa hiệu năng/khả năng sẵn sàng và thời gian thu hồi. Không nói “JWT không thể revoke”; đúng hơn là **JWT offline không tự nhận biết revocation tức thời nếu không có trạng thái hoặc tín hiệu bổ sung**.

### 6.1. Các chiến lược thu hồi

| Chiến lược | Cách hoạt động | Đánh đổi |
| --- | --- | --- |
| Access token lifetime ngắn | Token hết hạn nhanh, giảm cửa sổ sử dụng sau logout | Không thu hồi tức thì; cần refresh token được bảo vệ. |
| Token introspection (RFC 7662) | Resource server hỏi authorization server token còn active không | Có network dependency, latency, cache và availability concern. |
| Denylist theo `jti`/token reference | Resource server kiểm tra token ID đã bị revoke chưa | Cần đồng bộ, TTL và bảo vệ danh sách; lưu đúng token reference, không lưu raw secret. |
| Session/version check | Token chứa session ID hoặc version; API so với trạng thái server | Tăng tra cứu trạng thái; phải xử lý cache và propagation. |
| Event-driven revocation | Authorization server phát sự kiện revoke tới resource server/cache | Có độ trễ propagation và cần đảm bảo event không bị mất. |
| Opaque access token | Resource server introspect hoặc tra trạng thái tập trung | Dễ quản lý revocation hơn nhưng phụ thuộc service trung tâm. |

Chọn theo yêu cầu: nếu cần revoke gần như tức thời cho thao tác tài chính/quản trị, không chỉ dựa vào JWT offline với TTL dài. Nếu hệ thống chấp nhận một cửa sổ ngắn, access token TTL ngắn kết hợp refresh revocation có thể đủ.

### 6.2. Cache và propagation

Nếu resource server cache kết quả introspection hoặc trạng thái session, token có thể vẫn được chấp nhận tới khi cache hết hạn. Hãy xác định:
- TTL cache tối đa theo mức rủi ro.
- Cách invalidate cache khi revoke.
- Thời gian propagation mục tiêu và đo lường thực tế.
- Hành vi khi authorization server hoặc event bus unavailable.
- Cách xử lý event duplicate/out-of-order.
- Fail-open hay fail-closed cho từng loại API.

Không dùng một TTL cache chung cho mọi tài nguyên. API đọc nội dung ít nhạy cảm có thể chấp nhận cache lâu hơn API đổi email recovery hoặc cấp role.

## 7. Logout trong OpenID Connect và SSO

OAuth token revocation và đăng xuất SSO là hai thao tác khác nhau. OAuth xử lý token được cấp cho client; OpenID Connect định nghĩa các cơ chế logout để relying party và OpenID Provider phối hợp kết thúc phiên đăng nhập.

### 7.1. RP-Initiated Logout

Trong RP-Initiated Logout, relying party chuyển người dùng tới endpoint logout của OP theo metadata OIDC đã tin cậy. Request có thể dùng `id_token_hint`, `post_logout_redirect_uri` đã đăng ký và `state` để liên kết callback. OP xử lý phiên của người dùng theo policy và có thể điều hướng về URI đã đăng ký.

Điểm cần phân biệt:
- Xóa session ở ứng dụng RP chỉ kết thúc phiên local.
- Gọi OAuth revocation endpoint thu hồi token theo policy.
- Gọi OIDC logout endpoint yêu cầu OP kết thúc SSO session; không tự động đảm bảo mọi RP khác đã kết thúc local session nếu không có cơ chế phối hợp.
- Front-Channel Logout và Back-Channel Logout có semantics riêng; phải triển khai theo spec/profile và xác minh issuer/session binding.

Không xây dựng URL logout từ redirect do người dùng tùy ý cung cấp. `post_logout_redirect_uri` phải được đăng ký và kiểm tra theo quy tắc của OP. Không đưa token hoặc dữ liệu bí mật vào URL không cần thiết.

### 7.2. Logout trên nhiều ứng dụng

Một người dùng có thể đăng nhập qua IdP vào nhiều ứng dụng. Logout ở một ứng dụng có thể chỉ kết thúc session của ứng dụng đó. Nếu yêu cầu đăng xuất toàn bộ SSO, cần phối hợp RP/OP bằng cơ chế logout phù hợp, quản lý session identifiers và xử lý trường hợp một RP offline.

Thông báo giao diện cần chính xác: “Bạn đã đăng xuất khỏi StudyHub” khác với “Bạn đã đăng xuất khỏi tất cả ứng dụng kết nối”. Không tuyên bố logout toàn cục nếu chỉ xóa local cookie.

## 8. Logout an toàn phía client

Client cần chặn việc token cũ tiếp tục được dùng trong khi logout đang xử lý:
- Đánh dấu local session là logging out và ngừng tạo request nghiệp vụ mới.
- Dừng timer/worker tự refresh token và hủy request có thể hủy an toàn.
- Gửi revocation request qua TLS tới endpoint issuer đã cấu hình.
- Xóa access token, refresh token và token cache sau khi đã gửi request; giữ trạng thái tối thiểu cần thiết để retry nếu policy yêu cầu.
- Xóa cookie/session cookie bằng `Set-Cookie` có cùng name/path/domain và thuộc tính phù hợp.
- Xóa dữ liệu cache cá nhân và state ứng dụng cần thiết, nhưng tránh xóa dữ liệu local không liên quan hoặc dữ liệu chưa đồng bộ mà người dùng cần.
- Điều hướng về trang đã đăng xuất và ngăn back navigation hiển thị dữ liệu nhạy cảm đã cache.

Không gửi token qua query string, URL fragment, analytics, crash log hoặc support ticket. Không hiển thị raw token trong thông báo lỗi.

### 8.1. Logout BFF

Với Backend-for-Frontend, browser thường giữ cookie session HttpOnly; BFF giữ access/refresh token phía server. Khi logout:
1. BFF xác thực session và lấy token reference tương ứng từ server-side store.
2. BFF đánh dấu local session revoked để request mới bị từ chối.
3. BFF gửi refresh token tới revocation endpoint theo client authentication.
4. BFF xóa token record và session state theo policy.
5. BFF phát response xóa cookie session.

Nếu bước revoke gặp lỗi mạng, BFF cần ghi trạng thái pending và retry qua worker an toàn. Session local nên bị chặn ngay để người dùng không tiếp tục thao tác trên ứng dụng, dù việc thu hồi token upstream còn đang được xử lý.

## 9. Timeout, retry và race condition

Một tình huống thường gặp: client gửi request revoke, authorization server đã commit revocation nhưng response bị mất. Client không biết server đã xử lý hay chưa. RFC 7009 thiết kế response để request revoke lặp lại có thể an toàn trong trường hợp token đã không còn hợp lệ; tuy nhiên client vẫn cần retry có giới hạn và xử lý lỗi xác thực client đúng cách.

Các nguyên tắc:
- Dùng cùng token reference cho retry revoke; không tạo token mới.
- Dùng timeout, backoff và jitter; giới hạn số lần retry.
- Không coi HTTP 200 là bằng chứng token từng tồn tại hoặc mọi access token liên quan đã lập tức bị chặn ở mọi API.
- Dùng idempotency/event ID ở hệ thống nội bộ để tránh ghi audit hoặc phát sự kiện lặp ngoài policy.
- Nếu refresh và logout chạy đồng thời, logout phải thắng: session/family chuyển sang trạng thái revoked và response refresh đến muộn không được khôi phục token.
- Kiểm tra generation/version của session trước khi commit kết quả refresh.

~~~mermaid
stateDiagram-v2
    [*] --> Active
    Active --> LoggingOut: User requests logout
    LoggingOut --> Revoked: Server confirms revoke
    LoggingOut --> RevokePending: Network timeout / provider unavailable
    RevokePending --> Revoked: Retry succeeds / token already invalid
    RevokePending --> RevokePending: Bounded retry
    Revoked --> [*]
    note right of Revoked
      Local session blocked
      Token state revoked by issuer
    end note
~~~

Không chuyển từ `Revoked` về `Active` chỉ vì một response refresh cũ tới muộn. Nếu người dùng đăng nhập lại, phải tạo session/grant mới và token lineage mới.

## 10. Thu hồi khi token bị đánh cắp

Khi phát hiện access token hoặc refresh token bị lộ, quy trình incident response có thể cần:
1. Xác định token, client, subject, session và grant bị ảnh hưởng bằng reference/audit an toàn.
2. Revoke refresh token family hoặc grant liên quan để ngăn phát hành token mới.
3. Revoke access token nếu có hỗ trợ; cập nhật denylist/introspection/session state để resource server từ chối.
4. Thu hồi các session/credential liên quan nếu có bằng chứng compromise tài khoản.
5. Xoay client credential nếu secret của confidential client bị lộ.
6. Kiểm tra request đã thực hiện bằng token và hành động dữ liệu bị ảnh hưởng.
7. Thông báo người dùng qua kênh đã xác minh và yêu cầu xác thực/recovery phù hợp.
8. Lưu audit và giữ bằng chứng cần thiết theo incident policy.

Không chỉ revoke token đang được báo cáo nếu attacker có thể đã dùng refresh token để tạo token khác. Cần xem xét token family, grant, session và các token con theo khả năng của authorization server.

## 11. Pseudocode cho logout và revocation

### 11.1. Client/BFF logout

~~~text
logout(sessionId):
    session = loadSession(sessionId)
    if session is missing:
        clearLocalSessionCookie()
        return alreadyLoggedOut

    atomicallyMarkSessionLoggingOut(session.id)
    blockNewRequests(session.id)
    stopRefreshJobs(session.id)

    result = revokeAtIssuer(
        token=session.refreshToken,
        tokenTypeHint="refresh_token",
        authenticatedClient=currentClient
    )

    if result is success:
        markSessionRevoked(session.id)
        deleteServerSideTokenMaterial(session.id)
        clearLocalSessionCookie()
        return loggedOut

    persistRevokePending(session.id, safeTokenReference)
    clearLocalSessionCookie()
    enqueueBoundedRetry(session.id)
    return loggedOutLocallyRevokePending
~~~

Pseudocode minh họa trạng thái. Nếu cần retry, lưu token material trong kho bí mật server-side với TTL và quyền truy cập giới hạn; không đưa token vào queue/log dưới dạng rõ. Nếu không thể lưu an toàn để retry, ghi nhận sự cố và áp dụng phương án thu hồi bằng session/grant reference.

### 11.2. Resource server kiểm tra token

~~~text
authorizeRequest(accessToken, request):
    claims = verifySignatureIssuerAudienceExpiry(accessToken)
    if claims invalid:
        reject

    if policy.requiresOnlineRevocationCheck:
        status = introspectOrCheckSessionVersion(claims)
        if status != active:
            reject

    if policy.usesRevocationDenylist:
        if claims.jti is revoked:
            reject

    requireScopeAndBusinessAuthorization(claims, request)
    allow
~~~

Kiểm tra chữ ký JWT không thay thế kiểm tra authorization. API vẫn phải kiểm tra scope, audience, tenant, subject và quyền đối với tài nguyên. Chỉ tra denylist khi policy cần và đảm bảo `jti`/reference không thể bị giả mạo.

## 12. Bài thực hành: thiết kế Token logout cho StudyHub

**Bối cảnh:** StudyHub có web BFF, mobile app và Course API. Authorization server cấp access token JWT 10 phút và refresh token rotation. Người dùng có thể đăng nhập trên nhiều thiết bị. Khi logout, họ có hai lựa chọn: đăng xuất thiết bị hiện tại hoặc đăng xuất mọi thiết bị. Tài khoản giảng viên có quyền sửa điểm và tài khoản quản trị có quyền cấp role.

### 12.1. Thiết kế policy

Hãy xác định:
1. Client giữ token ở đâu và token nào được gửi tới revocation endpoint.
2. Token family/grant gắn với thiết bị và session ra sao.
3. Logout thiết bị hiện tại khác logout mọi thiết bị ở thao tác server nào.
4. Course API kiểm tra JWT offline hay introspection/session state; độ trễ thu hồi chấp nhận là bao nhiêu.
5. Cache introspection/denylist có TTL và invalidation thế nào.
6. OIDC SSO logout có được hỗ trợ không và giao diện mô tả phạm vi nào.
7. Xử lý revoke timeout, retry, worker outage và refresh/logout race ra sao.
8. Khi token bị đánh cắp, có cần revoke family, grant, session hoặc credential khác không.
9. Audit lưu reference nào mà không ghi raw token.
10. Hành động nhạy cảm nào phải fail closed khi không kiểm tra được trạng thái thu hồi.

### 12.2. Bộ ca kiểm thử chấp nhận

| Trường hợp | Kết quả mong đợi |
| --- | --- |
| Logout thiết bị hiện tại | Session và token family của thiết bị bị thu hồi; thiết bị khác vẫn hoạt động theo policy. |
| Logout mọi thiết bị | Tất cả session/family/grant thuộc phạm vi tài khoản bị thu hồi. |
| Client chỉ xóa token local | Test chứng minh token đã sao chép vẫn dùng được cho tới khi server revoke/expire; luồng logout thực tế phải gọi revoke. |
| Refresh token hợp lệ được revoke | Authorization server không cấp access token mới từ token đó. |
| Gửi token đã revoked lần nữa | Xử lý idempotent; không khôi phục token. |
| Token không tồn tại gửi tới RFC 7009 endpoint | Response theo RFC không tiết lộ token có tồn tại hay không. |
| Confidential client xác thực sai | Revocation request bị từ chối theo policy; client không được báo revoke thành công. |
| Access token JWT đã phát hành trước logout | API từ chối theo cơ chế online/denylist đã thiết kế hoặc chỉ chấp nhận trong cửa sổ TTL đã công bố. |
| Introspection cache còn active sau revoke | Cache invalidation/TTL đáp ứng SLA thu hồi của action. |
| Refresh và logout đồng thời | Logout thắng; response refresh cũ không khôi phục session/family. |
| Response revoke timeout sau khi server commit | Retry có giới hạn; trạng thái cuối vẫn revoked. |
| Authorization server outage | Local session bị chặn; revocation pending được ghi nhận và xử lý theo policy. |
| ID token gửi tới resource API | API từ chối; ID token không phải access token. |
| RP logout nhưng OP session còn | Giao diện chỉ tuyên bố logout local; SSO logout cần flow riêng. |
| `post_logout_redirect_uri` không đăng ký | OP/client từ chối redirect không hợp lệ. |
| Logout link bị replay | Không tạo hành động trái phép; state/nonce và session binding được kiểm tra. |
| Raw token xuất hiện trong log/queue | Kiểm thử thất bại; pipeline phải redact và payload chỉ dùng reference an toàn. |
| Token bị đánh cắp | Revoke family/grant và cập nhật trạng thái resource server theo incident policy. |
| Người dùng bấm back sau logout | Không hiển thị dữ liệu nhạy cảm từ cache và request mới bị từ chối. |
| Audit event được giao lặp | Event processing idempotent; không tạo tác động phụ ngoài policy. |

### 12.3. Câu hỏi tự đánh giá

1. Vì sao xóa token local không đủ để bảo vệ sau logout?
2. RFC 7009 định nghĩa endpoint và response như thế nào?
3. Vì sao HTTP 200 từ revocation endpoint không chứng minh token trước đó còn active?
4. Thu hồi refresh token có tự động vô hiệu mọi JWT access token ngay lập tức không?
5. Introspection và denylist giải quyết bài toán nào, có chi phí gì?
6. Logout một thiết bị khác logout mọi thiết bị ở đâu?
7. OAuth token revocation khác OIDC RP-Initiated Logout thế nào?
8. Vì sao logout phải thắng một refresh request đang chạy đồng thời?
9. Khi token bị đánh cắp, vì sao cần xem xét cả token family/grant?
10. Hệ thống nên nói gì với người dùng nếu local logout đã xong nhưng revoke upstream đang pending?

**Tiêu chí hoàn thành:** Người học có thể mô tả đầy đủ luồng logout từ client tới authorization server và resource server, giải thích giới hạn của JWT offline, lựa chọn cơ chế thu hồi phù hợp, phân biệt logout local/OAuth/OIDC và chứng minh bằng test rằng token đã revoke không thể tiếp tục tạo quyền truy cập vượt quá cửa sổ đã công bố.

## 13. Vận hành và giám sát

Các chỉ số nên theo dõi:
- Số yêu cầu logout theo phạm vi: device, session, family hoặc all sessions.
- Tỷ lệ revocation thành công, pending, timeout và lỗi client authentication.
- Thời gian từ logout request tới khi mỗi resource server ngừng chấp nhận token.
- Tỷ lệ token revoked vẫn được chấp nhận do cache hoặc propagation delay.
- Queue backlog, retry count và event duplicate.
- Tỷ lệ refresh request sau logout và reuse attempt.
- Số session/family bị revoke do incident compromise.
- Tỷ lệ OIDC logout callback thành công và lỗi redirect validation.

Audit nên lưu account reference, client ID, session/family reference, token type, issuer, thời điểm, phạm vi logout, actor, kết quả và policy version. Không lưu raw access token, refresh token, ID token, cookie hoặc client secret. Giới hạn quyền xem audit và đặt retention theo chính sách.

Định nghĩa một SLA thu hồi cụ thể cho từng loại API. Ví dụ, API quản trị có thể yêu cầu propagation nhanh hơn API đọc nội dung. Đo thời gian thực tế từ lúc revoke được commit tới khi token bị từ chối; không chỉ đo thời gian endpoint trả HTTP 200.

Khi provider hoặc event bus gặp sự cố, giữ trạng thái local logout nhất quán, lưu pending work an toàn, retry có giới hạn và cảnh báo vận hành. Khi khôi phục dịch vụ, đối soát các event chưa xử lý và kiểm tra token family vẫn revoked. Không tự động kích hoạt lại session chỉ vì worker retry thất bại.

## 14. Tài liệu nên đọc tiếp

- **RFC 7009 — OAuth 2.0 Token Revocation**: endpoint thu hồi token và response semantics.
- **RFC 6749 — OAuth 2.0 Authorization Framework**: vai trò access token, refresh token và grant.
- **RFC 7662 — OAuth 2.0 Token Introspection**: kiểm tra trạng thái token tại resource server.
- **OpenID Connect RP-Initiated Logout**: yêu cầu OP kết thúc phiên SSO.
- **OpenID Connect Front-Channel Logout / Back-Channel Logout**: phối hợp logout giữa OP và RP.
- **RFC 9700 — Best Current Practice for OAuth 2.0 Security**: bảo vệ token, refresh token rotation và replay.
- **OWASP OAuth 2.0 Cheat Sheet và Session Management Cheat Sheet**: thực hành bảo vệ token/session và logout.
- **OWASP ASVS**: tiêu chí kiểm thử authentication, session và access control.

Khi triển khai thật, hãy xác định phạm vi logout, semantics của issuer, cách resource server kiểm tra trạng thái, SLA propagation và fallback khi dịch vụ thu hồi không sẵn sàng. **Logout an toàn hoàn tất khi client ngừng dùng credential, authorization server thu hồi quyền phát hành tiếp và resource server từ chối token theo thời hạn thu hồi đã cam kết; chỉ xóa token khỏi giao diện chưa đủ.**
