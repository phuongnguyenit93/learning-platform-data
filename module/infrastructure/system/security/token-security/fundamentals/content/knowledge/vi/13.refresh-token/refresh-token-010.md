# Đổi refresh token khi đăng xuất

## 1. Khi đăng xuất, nên xoay vòng hay thu hồi refresh token?

Trong chương **Refresh token** của module `SECURITY_TOKEN_SECURITY_FUNDAMENTALS`, câu hỏi “**Đổi refresh token khi đăng xuất**” đòi hỏi phân biệt hai thao tác nhìn giống nhau nhưng có mục đích bảo mật khác nhau:

- **Refresh-token rotation** (*xoay vòng refresh token*): trong một lần sử dụng refresh token hợp lệ tại token endpoint, authorization server (AS) có thể cấp một refresh token **mới** và vô hiệu refresh token **cũ**, giúp duy trì một phiên được cấp phép và phát hiện việc sử dụng lại token cũ.
- **Refresh-token revocation** (*thu hồi refresh token*): khi đăng xuất, hủy cấp quyền, mất thiết bị hoặc phát hiện credential bị lộ, hệ thống **vô hiệu hóa** refresh token/grant để nó không thể xin access token mới. **Không cấp refresh token thay thế cho phiên vừa đăng xuất.**

Vì vậy, nếu “đổi” được hiểu là tạo token mới để tiếp tục dùng, thì **đây không phải hành động logout mong muốn**. Nếu “đổi” nhằm loại bỏ token cũ khỏi hiệu lực, cách thực hiện đúng thường là **revoke** token/grant, đóng phiên ứng dụng và xóa những bản sao credential mà client kiểm soát.

> **Quy tắc nhớ nhanh:** *Refresh hợp lệ để duy trì phiên → có thể rotate. Logout để kết thúc phiên → revoke và xóa credential, không mint refresh token mới cho phiên đó.*

Giả sử Alice đăng nhập ứng dụng `sales-dashboard`. AS `https://auth.example.test` đã cấp:

~~~text
Access token  AT-1: aud=orders-api; scope=orders.read; hết hạn sau 5 phút
Refresh token RT-1: gắn với client, Alice, grant/phiên theo chính sách AS
~~~

Alice nhấn **Đăng xuất**. Nếu ứng dụng chỉ xóa `AT-1` nhưng giữ `RT-1` dùng được, một tiến trình khác hoặc kẻ đã sao chép refresh token có thể xin `AT-2`, rồi tiếp tục truy cập `orders-api`. Ngược lại, nếu AS chỉ thay `RT-1` bằng `RT-2` và trao nó lại cho client, phiên trên thực tế **được tiếp tục**, không bị kết thúc.

Bài này tập trung vào **ngữ nghĩa logout**, phối hợp revocation/rotation và token family, xử lý nhiều thiết bị, rủi ro race khi refresh đồng thời, khác biệt giữa JWT và opaque token, logout OIDC và cách triển khai an toàn với Java/Spring.

### Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **rotate**, **revoke**, **delete local token**, **terminate session** và **logout ở nhà cung cấp danh tính**.
2. Giải thích vì sao logout phải ngăn **cấp access token mới**, nhưng không tự động vô hiệu mọi access token còn hạn.
3. Thiết kế quy trình revoke theo RFC 7009 và phạm vi từng phiên/thiết bị hoặc toàn bộ phiên.
4. Xử lý refresh-token rotation, token-family reuse, yêu cầu refresh đang chạy và sự cố mạng trong lúc logout.
5. Áp dụng giải pháp trong ứng dụng Java/Spring Security và xây bộ kiểm thử âm/dương về logout.

## 2. Vòng đời access token, refresh token và phiên đăng nhập

Ba đối tượng cần quản lý độc lập:

| Đối tượng | Dùng ở đâu? | Khi nào hết hiệu lực? | Logout phải cân nhắc gì? |
| --- | --- | --- | --- |
| **Access token (AT)** | Client trình tới resource server, ví dụ `orders-api` | Theo `exp`/TTL, revocation hoặc policy RS | AT còn hạn có thể vẫn được dùng sau logout nếu RS chỉ xác minh JWT offline |
| **Refresh token (RT)** | Client trình tới **token endpoint của AS** để xin AT mới | Hết hạn, bị revoke, rotate, sai binding hoặc chính sách grant | Cần ngăn RT phiên logout tiếp tục xin AT mới |
| **Application session** | BFF/backend hoặc browser cookie/session | Logout, idle/absolute timeout, session invalidation | Phải chặn phiên và không cho hệ thống tiếp tục sử dụng RT đã lưu |
| **OP/SSO session (OIDC)** | Phiên tại OpenID Provider/identity provider | OIDC logout, chính sách SSO và IdP | Đóng phiên ứng dụng không nhất thiết đóng phiên SSO; SSO logout không đồng nghĩa revoke tất cả token |
| **OAuth grant/consent** | AS lưu quan hệ quyền đã được chấp thuận | Thu hồi grant/consent hoặc chính sách AS | Logout một thiết bị không nhất thiết xóa consent hoặc grant dùng chung của nhiều thiết bị |

**Access token và refresh token không chỉ khác TTL.** AT dùng để gọi API; RT là credential nhạy cảm để **mint AT mới**. Với JWT AT, RS có thể xác minh chữ ký, issuer, audience, `exp`, scope mà không hỏi AS. Với opaque AT, RS thường dùng introspection của AS. Cả hai loại AT có thể có ngữ nghĩa **bearer** và bị phát lại nếu lộ.

### 2.1. Vì sao chỉ xóa cookie hoặc access token là chưa đủ?

Giả sử tại thời điểm 10:00:

~~~text
09:59:00  Client có AT-1, RT-1.
10:00:00  Alice bấm Logout.
10:00:01  Ứng dụng xóa AT-1 và cookie phiên ở trình duyệt.
10:01:00  Một actor vẫn sở hữu RT-1 gửi POST /token.
10:01:01  AS không biết logout/revocation, cấp AT-2.
~~~

Nếu một RT còn dùng được và client/actor đủ điều kiện sử dụng token endpoint, nó vẫn có khả năng duy trì truy cập. Logout cần kết thúc **khả năng gia hạn**, không chỉ xóa giá trị đang hiển thị trên thiết bị.

Ngược lại, nếu RT bị thu hồi lúc 10:00 nhưng AT-1 có `exp=10:04`, một RS kiểm tra JWT offline có thể vẫn chấp nhận AT-1 tới lúc hết hạn (trừ khi có cơ chế thu hồi/trạng thái bổ sung). Vì vậy, thiết kế phải công bố **độ trễ logout có hiệu lực tại từng API** và không hứa logout “lập tức chặn mọi request” khi kiến trúc không thực hiện được.

### 2.2. Một mô hình an toàn về mặt logic

~~~mermaid
flowchart TD
    A["Phiên đăng nhập hoạt động"] --> B{"Người dùng yêu cầu Logout?"}
    B -->|"Không"| C["Access token gần hết hạn"]
    C --> D["Client dùng RT để xin AT mới"]
    D --> E{"AS cho refresh và rotation?"}
    E -->|"Có"| F["Lưu AT/RT mới theo cùng phiên"]
    F --> A
    E -->|"Không"| G["Yêu cầu xác thực/cấp quyền lại"]
    B -->|"Có"| H["Đánh dấu phiên không còn được refresh"]
    H --> I["Thu hồi RT / grant liên quan tại AS"]
    I --> J["Hủy phiên và xóa credential local"]
    J --> K["RS từ chối AT cũ khi hết hạn hoặc khi cơ chế thu hồi có hiệu lực"]
~~~

Sơ đồ biểu diễn **mục tiêu bảo mật**, không quy định mọi bước đều xảy ra thành công trong cùng một transaction. AS có thể là hệ thống từ xa; nếu gọi revocation bị timeout thì ứng dụng phải ghi nhận **trạng thái chưa chắc chắn** và áp dụng quy trình recovery, không báo cáo rằng AS đã revoke thành công khi chưa có bằng chứng.

## 3. Rotation khi refresh khác với revocation khi logout

### 3.1. Rotation: duy trì phiên mà vẫn phát hiện RT bị dùng lại

Một refresh-token family theo chính sách rotation có thể được biểu diễn:

~~~text
RT-1 --refresh hợp lệ--> RT-2 --refresh hợp lệ--> RT-3
       RT-1 vô hiệu         RT-2 vô hiệu
~~~

RT-1 và RT-2 bị vô hiệu sau khi sử dụng đúng, nhưng `RT-3` là credential **đang hoạt động** giúp tiếp tục phiên. Nếu `RT-1` bị gửi lại sau rotation, AS có thể xem đây là dấu hiệu **refresh-token replay**, rồi thực hiện xử lý theo policy như từ chối request và có thể thu hồi token family.

Lưu ý: refresh-token rotation là một cơ chế được sử dụng rộng rãi để phát hiện replay, đặc biệt với public client. **Không phải mọi AS đều rotate**, cũng không phải mọi AS đều có cùng thời gian dung sai/reuse detection. Client cần biết hợp đồng nhà cung cấp.

### 3.2. Revocation: chấm dứt khả năng sử dụng credential

Khi Alice logout, mục tiêu của hệ thống thường là:

~~~text
Đang hoạt động: RT-3
Logout:          revoke RT-3 và grant/session tương ứng
Sau logout:      RT-3 không thể xin AT-4
                Không phát hành RT-4 để duy trì phiên vừa logout
~~~

Nếu AS có bảng trạng thái `ACTIVE/CONSUMED/REVOKED` và token family, nó cần xử lý đúng bản token **mới nhất**. Chỉ thu hồi RT-1 đã bị rotate từ lâu **không bảo đảm** RT-3 đang hoạt động bị vô hiệu — điều này phụ thuộc việc AS revoke từng token hay grant/family. Không tự suy luận rằng mọi AS luôn revoke cả family khi nhận một ancestor token.

### 3.3. So sánh quyết định thiết kế

| Câu hỏi | Trong một lần refresh bình thường | Khi logout |
| --- | --- | --- |
| Có cần tiếp tục phiên? | Có, nếu grant và policy hợp lệ | Không |
| Có thể tạo access token mới? | Có | Không tạo mới cho phiên đã logout |
| Có cấp refresh token mới? | Có thể, khi bật rotation | Không nhằm duy trì phiên logout |
| RT cũ có bị vô hiệu? | Có nếu rotation; tùy AS nếu RT reusable | Cần revoke RT/grant phù hợp |
| Có phải xóa client credential local? | Thường cập nhật cặp AT/RT an toàn | Có, cùng session và token cache |
| Xử lý AT còn hạn? | Tiếp tục theo policy RS | Cần có chính sách thu hồi/TTL riêng |
| Lỗi mạng gây vấn đề gì? | Không biết rotation đã commit chưa | Không biết revocation ở AS đã thành công chưa |

**Đừng dùng “đổi refresh token” như một tên hành động chung cho cả refresh và logout.** Những tên API rõ hơn như `rotateOnRefresh`, `revokeOnLogout`, `terminateSession` giúp tránh bugs nghiệp vụ.

## 4. OAuth 2.0 Token Revocation (RFC 7009)

RFC 7009 định nghĩa **token revocation endpoint**: client yêu cầu AS vô hiệu hóa một token đã được cấp. Với logout, mục tiêu thường là refresh token, vì nó cho phép tiếp tục lấy access token mới.

### 4.1. Request thu hồi refresh token

Một confidential client có thể gọi AS:

~~~http
POST /oauth2/revoke HTTP/1.1
Host: auth.example.test
Authorization: Basic <client-authentication>
Content-Type: application/x-www-form-urlencoded

token=<urlencoded-refresh-token>&token_type_hint=refresh_token
~~~

Giải thích:

- `token` là giá trị credential **cần thu hồi**, được form-encode đúng quy tắc.
- `token_type_hint=refresh_token` là **gợi ý** giúp AS tra cứu, không phải trường làm thay đổi ngữ nghĩa token. AS vẫn cần xác minh token và quyền client phù hợp.
- Confidential client cần xác thực theo **client authentication method** đã đăng ký; không nhất thiết mọi client dùng Basic. Public client có contract xác định client riêng và không được giả vờ có secret bí mật ở browser.
- HTTPS/TLS là bắt buộc để không lộ RT trong truyền tải; không dùng query URL, không ghi raw body vào log.

Ví dụ phản hồi:

~~~http
HTTP/1.1 200 OK
Cache-Control: no-store
~~~

Theo RFC 7009, AS **trả HTTP 200 khi revocation request được xử lý thành công, kể cả trường hợp token được gửi vốn đã không hợp lệ**. Client không nên suy luận từ 200 rằng “token chắc chắn đã tồn tại”, hay yêu cầu AS tiết lộ token đó thuộc user nào. Với lỗi client authentication hoặc revocation không được hỗ trợ, có thể nhận phản hồi lỗi; ứng dụng phải phân loại và không báo thành công từ xa nếu AS chưa xác nhận.

### 4.2. Revoking RT có hủy access token liên quan không?

RFC 7009 yêu cầu AS hỗ trợ thu hồi **refresh token** (nếu có hỗ trợ), và cho phép AS hỗ trợ thu hồi access token; thu hồi RT **có thể** dẫn đến vô hiệu các access token cùng grant theo chính sách/khả năng AS. Nhưng:

- Không được mặc định **mọi JWT AT đã phát hành bị từ chối ngay**: RS xác minh JWT offline có thể không biết trạng thái revoke.
- Nếu yêu cầu chặn ngay, cần introspection/denylist, session-state lookup, token version, event-driven invalidation hoặc cơ chế tương đương theo SLA.
- Khi access token opaque được kiểm tra trạng thái tại AS, `active:false` có thể phản ánh thu hồi nhanh, nhưng **introspection cache** vẫn tạo cửa sổ trễ.

Đăng xuất không nên phụ thuộc vào kỳ vọng “revoke RT là xong mọi API request”. Cần thiết kế hành vi cụ thể theo loại token và từng RS.

### 4.3. Revocation request có thể gửi lặp lại không?

Gửi lại yêu cầu revoke **cùng token** thường an toàn về mục tiêu “token không còn dùng được”: AS xử lý token đã invalid như token không hợp lệ và trả 200 theo RFC 7009. Tuy nhiên, việc retry vẫn phải:

1. Tuân thủ quota/rate limit, timeout và backoff; không tạo retry storm.
2. Bảo vệ refresh token đang giữ để retry, tránh lưu plaintext trong log/queue tùy tiện.
3. Ràng buộc request với **đúng client và phiên**; không vô tình revoke grant của user/thiết bị khác.
4. Hiểu rằng nếu phiên đã rotate, **revoke một RT cũ có thể không revoke RT mới** nếu AS không hỗ trợ family/grant revocation.

Vì thế “revocation có hiệu ứng idempotent” **không tự giải quyết** race refresh-token rotation trong lúc logout. Client và AS phải bảo đảm đang chấm dứt đúng grant/session/family theo hợp đồng.

## 5. Luồng logout an toàn: chặn refresh, revoke, xóa và xác nhận

Với ứng dụng backend-for-frontend (BFF) hoặc web backend lưu refresh token phía server, có thể tách **hai mục tiêu**:

1. **Local logout:** dừng sử dụng session/token ở ứng dụng của mình ngay cả khi AS tạm thời không truy cập được.
2. **AS revocation:** cố gắng thu hồi refresh token/grant từ AS để ngăn credential tiếp tục được sử dụng ở nơi khác.

Một sequence minh họa:

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Alice
    participant B as Browser
    participant APP as BFF / Application
    participant DB as Session + Token Store
    participant AS as Authorization Server
    participant RS as Resource Server
    U->>B: Chọn Đăng xuất
    B->>APP: POST /session/logout (CSRF/session checks)
    APP->>DB: Đánh dấu phiên LOGGING_OUT, cấm refresh mới
    APP->>DB: Đọc RT đang hoạt động theo session/grant
    APP->>AS: POST /revoke (RT phù hợp + client auth)
    alt AS xác nhận
        AS-->>APP: 200 OK
        APP->>DB: Đánh dấu revoked/closed, xóa token lưu
    else AS lỗi/timeout
        AS-->>APP: Lỗi hoặc unknown outcome
        APP->>DB: Đóng phiên local; lưu retry trạng thái an toàn nếu cần
    end
    APP-->>B: Xóa cookie/session local và trả kết quả logout local
    Note over RS: AT còn hạn chịu chính sách thu hồi/TTL riêng
~~~

**Thứ tự thực tế phụ thuộc kiến trúc**: quá trình gọi AS là thao tác mạng ngoài transaction database local; không thể giả định mọi bước là một transaction ACID duy nhất. Điều quan trọng là không có thread nào tiếp tục refresh sau khi hệ thống đã quyết định logout, và trạng thái local phải rõ ngay cả khi AS revocation chưa được xác nhận.

### 5.1. Những bước tối thiểu cần có

1. **Xác thực yêu cầu logout và bảo vệ CSRF** đối với browser session/cookie tự động gửi; không cho request của user A logout user B bằng session ID tùy ý.
2. **Đánh dấu session/grant là đang đóng** theo cách nguyên tử và từ chối hoạt động refresh mới.
3. **Phối hợp với refresh đang chạy** để xác định refresh token hiện hành; không revoke nhầm ancestor token rồi bỏ sót bản mới.
4. **Gọi revocation endpoint** bằng phương thức client authentication đã đăng ký; giới hạn timeout, bảo vệ credential.
5. **Invalidate session local, xóa token cache/bản lưu**, hủy cookie hoặc credential tại client theo thiết kế.
6. **Ghi trạng thái xác nhận remote revocation**. Nếu không nhận được 200 đáng tin, không ghi nhận “đã revoke ở AS”; cần quy trình retry/reconciliation hoặc cảnh báo theo rủi ro.
7. **Áp chính sách cho AT còn hạn**: TTL ngắn, introspection/denylist hoặc kiểm tra session/ACL khi yêu cầu logout tức thì.

Đối với browser app, đừng đánh đồng đóng tab, xóa localStorage, xóa cookie ở frontend và thu hồi credential trong AS. Với BFF, RT nên nằm ở backend bảo vệ; browser chỉ giữ phiên ứng dụng qua cookie `HttpOnly`, `Secure` và `SameSite` phù hợp, kèm CSRF defense khi dùng cookie tự động gửi.

## 6. Race condition: refresh token bị rotate đúng lúc logout

Trường hợp dễ gây lỗi nhất là hai thao tác đến gần nhau:

- **Request A:** refresh access token bằng `RT-1`, AS cấp `RT-2`.
- **Request B:** người dùng bấm logout; ứng dụng đang lưu `RT-1` và gửi revoke `RT-1`.

Nếu revoke một RT cũ không kéo theo revocation của cả grant/family, `RT-2` có thể vẫn dùng được. Ứng dụng báo “đăng xuất thành công” nhưng đã có **refresh token mới đang sống** mà chưa được thu hồi.

~~~mermaid
sequenceDiagram
    autonumber
    participant F as Refresh worker
    participant L as Logout handler
    participant S as Session/token store
    participant AS as Authorization Server
    F->>S: Đọc RT-1 khi session ACTIVE
    F->>AS: POST /token refresh_token=RT-1
    L->>S: Đọc RT-1
    L->>AS: POST /revoke token=RT-1
    AS-->>F: Cấp AT-2, RT-2 (thứ tự tùy race)
    F->>S: Ghi RT-2?
    Note over F,L: Nếu logout không ngăn ghi và không revoke RT-2, phiên còn credential sống
~~~

### 6.1. Bốn bất biến cần thiết

1. **Sau khi session chuyển sang trạng thái logout, không được bắt đầu refresh mới.**
2. **Kết quả refresh đang chạy không được “hồi sinh” session đã đóng.** Worker refresh phải so phiên bản/trạng thái trước khi lưu AT/RT mới.
3. **Logout phải giải quyết token RT hiện hành**, hoặc revoke **grant/family** bằng cơ chế AS hỗ trợ, thay vì chỉ gửi ancestor token rồi cho rằng đủ.
4. **Nếu refresh hoàn tất sau khi local logout đã quyết định đóng phiên, RT vừa nhận phải được xử lý an toàn** (ví dụ revoke trong quy trình cleanup đáng tin), không lưu để dùng tiếp.

Những bất biến này cần được chứng minh trong môi trường nhiều thread/nhiều Pod. Một `synchronized` trên một JVM không bảo vệ trường hợp worker ở JVM khác.

### 6.2. Mô hình trạng thái phiên

~~~mermaid
stateDiagram-v2
    [*] --> ACTIVE
    ACTIVE --> REFRESHING: Claim quyền refresh
    ACTIVE --> LOGGING_OUT: User logout
    REFRESHING --> ACTIVE: Lưu AT/RT mới nếu phiên vẫn hợp lệ
    REFRESHING --> LOGGING_OUT: Logout được ghi nhận
    LOGGING_OUT --> REVOKING: Xác định RT/grant cuối và yêu cầu revoke
    REVOKING --> CLOSED: Remote revoke xác nhận + local cleanup
    REVOKING --> CLOSED_PENDING_REVOKE: AS timeout/lỗi
    CLOSED_PENDING_REVOKE --> CLOSED: Reconciliation xác nhận hoặc expiry
    CLOSED --> [*]
~~~

Các tên trạng thái là ví dụ cho implementation; không phải enum chuẩn OAuth. **`CLOSED_PENDING_REVOKE` có nghĩa client đã logout local nhưng remote revocation chưa được xác nhận**, không phải cam kết RT đã vô hiệu ở AS. Nên lưu metadata tối thiểu để reconciliation; nếu phải giữ RT để retry, credential phải được bảo vệ trong storage truy cập hạn chế và xóa ngay khi hoàn tất.

### 6.3. Phối hợp bằng lock/lease hoặc token broker

Trong BFF nhiều instance, có thể xử lý theo **cùng grant/session key**:

~~~text
logout(session):
    atomic mark session as LOGGING_OUT
    block new refresh requests
    wait for / coordinate with already-running refresh
    read currently active RT or grant identifier
    revoke RT or grant at AS
    clear session and token cache
    if revocation outcome unknown:
        register secure reconciliation; never report remote success
~~~

Nếu AS cho phép **grant/session/family revocation**, cơ chế đó có thể giải quyết trường hợp RT liên tục rotate tốt hơn việc revoke từng token. Nếu chỉ có RFC 7009 token revocation, ứng dụng cần quy tắc rõ về bản RT cuối cùng và cuộc gọi refresh đang chạy.

Giữ một transaction database mở trong suốt cuộc gọi HTTP ra AS có thể khóa tài nguyên rất lâu, không phù hợp cho nhiều hệ thống. Thay vào đó có thể dùng state machine + version/CAS, serialized token broker, lease/fencing và cleanup sau khi refresh hoàn tất. Mỗi phương án phải xử lý crash, lease timeout và retry để không bỏ sót RT mới.

### 6.4. Lost update: RT mới bị ghi đè sau logout

Giả sử token store chứa:

~~~json
{
  "session_id": "sess-alice-device-1",
  "status": "ACTIVE",
  "version": 20,
  "refresh_token": "<encrypted-RT-1>"
}
~~~

Một refresh worker đọc version 20; đồng thời logout chuyển status sang `LOGGING_OUT`, version 21. Khi worker nhận RT-2 và muốn ghi, câu lệnh CAS phải đòi:

~~~text
UPDATE session_token_store
SET access_token = :newAT,
    refresh_token = :newRT,
    version = version + 1
WHERE session_id = :session
  AND status = 'ACTIVE'
  AND version = :oldVersion;
~~~

Nếu không update được, worker **không được ghi RT-2 và coi phiên ACTIVE**. Nhưng chỉ CAS thôi chưa đảm bảo RT-2 bị revoke ở AS; cần cleanup/grant revocation. Ngược lại, logout phải đợi hoặc quan sát đúng worker refresh đang chạy trước khi quyết định revoke credential cuối.

### 6.5. Đừng chữa race bằng cách bỏ rotation

Một số hệ thống có reuse grace period ngắn dành cho refresh token rotation. Đây là lựa chọn riêng của AS, không phải lý do để ứng dụng bỏ đồng bộ hoặc để RT cũ dùng lại vô hạn. Grace period quá dài có thể mở cửa cho kẻ đã lấy RT cũ tiếp tục xin token sau khi người dùng logout.

**Phòng vệ đúng:** phối hợp refresh/logout, xác định đúng session/grant, xử lý trạng thái AS và local một cách nhất quán; không làm suy yếu replay detection để che lỗi race.

## 7. Logout một thiết bị, mọi thiết bị hay thu hồi toàn bộ grant?

“Đăng xuất” là yêu cầu nghiệp vụ cần xác định **phạm vi**. Alice có thể dùng cùng OAuth client trên laptop và điện thoại, hoặc có nhiều phiên browser; các phiên có thể chia sẻ hoặc không chia sẻ một grant/refresh-token family tùy AS.

| Hành động | Mục tiêu | Kiểm soát cần có | Rủi ro nếu làm sai |
| --- | --- | --- | --- |
| **Logout phiên hiện tại** | Đóng một browser/app session | Hủy local session và RT/grant riêng của phiên đó | Revoke token chung khiến mọi thiết bị bị logout |
| **Logout một thiết bị** | Chặn thiết bị thất lạc hoặc user chọn xóa thiết bị | Liên kết device/session ID với RT family, revoke đúng family | Chỉ xóa cookie trên thiết bị khác không chặn RT bị đánh cắp |
| **Logout khỏi mọi thiết bị** | Chấm dứt tất cả phiên liên quan của user/client | AS session/grant management, session version/denylist, revoke các RT family phù hợp | Chỉ revoke một RT đang thấy rồi tuyên bố mọi thiết bị đã bị chặn |
| **Thu hồi quyền ứng dụng** | Ngăn client tiếp tục dùng grant được chấp thuận | Revocation/consent management tại AS | Đăng xuất local nhưng app vẫn được cấp quyền khi user quay lại |
| **Khóa tài khoản/ứng phó compromise** | Chặn hành vi trái phép trên toàn tài khoản | Vô hiệu session/grant theo policy, cập nhật RS/ACL và audit | Chỉ revoke RT nhưng AT dài hạn vẫn dùng được |

OAuth 2.0 không định nghĩa một API chung “logout all devices” cho mọi nhà cung cấp. RFC 7009 thu hồi **token được cung cấp** theo quan hệ và chính sách AS; phạm vi thu hồi toàn thiết bị, toàn user hoặc toàn grant cần **contract cụ thể với AS/IdP**.

### 7.1. Không suy luận từ sub hoặc client_id

Một JWT access token có `sub=alice` và `client_id=sales-dashboard` không tự cho biết tất cả RT nào của Alice đang hoạt động. Session ID, device binding, RT family ID và grant ID thường là **trạng thái nội bộ của AS**, không mặc nhiên xuất hiện trong JWT.

Để hỗ trợ “logout mọi thiết bị”, AS hoặc hệ thống quản lý phiên phải lưu quan hệ phiên/grant đủ an toàn và xác minh người yêu cầu có quyền thực hiện thao tác. Không cho browser gửi một `user_id` tùy ý để revoke tất cả token của người khác.

### 7.2. Multi-tenant và machine identity

Nếu user Alice thuộc tenant A và tenant B, logout trong tenant A có thể có policy khác logout khỏi tài khoản trên mọi tenant. Việc revoke phải có **phạm vi user/client/tenant/resource** rõ ràng.

Với machine-to-machine `client_credentials`, thông thường không có phiên đăng nhập của end-user và **refresh token không được khuyến nghị cấp**. “Logout service” có thể là ngừng workload, revoke grant/token nếu AS hỗ trợ, rotate client secret/certificate hoặc chấm dứt workload identity. **Không áp mô hình user logout và RT rotation cho mọi service account.**

## 8. OIDC logout, SSO logout và OAuth revocation là các cơ chế khác nhau

Trong OpenID Connect (OIDC), **Relying Party (RP)** là ứng dụng sử dụng đăng nhập qua OpenID Provider (OP). Một người dùng có thể có:

1. Session/cookie **ở ứng dụng RP**.
2. Session đăng nhập **ở OP/Identity Provider** cho SSO.
3. Access token và refresh token cấp cho RP theo OAuth/OIDC.

Đóng một trong ba lớp không tự đóng hai lớp còn lại.

### 8.1. RP-Initiated Logout

OIDC RP-Initiated Logout 1.0 mô tả cách RP yêu cầu OP đăng xuất end-user qua `end_session_endpoint`, với các tham số được hỗ trợ như `id_token_hint`, `post_logout_redirect_uri` và `state`. Redirect sang OP để đóng SSO session là việc **khác với POST revocation RFC 7009**.

Luồng minh họa:

~~~mermaid
sequenceDiagram
    autonumber
    actor U as User
    participant RP as Ứng dụng / Relying Party
    participant OP as OpenID Provider
    U->>RP: Logout
    RP->>RP: Khóa refresh, đóng session local
    RP->>OP: Revoke refresh token/grant qua AS (nếu chính sách yêu cầu)
    RP-->>U: Điều hướng qua end_session_endpoint
    U->>OP: Yêu cầu kết thúc SSO session
    OP-->>U: Redirect về RP theo policy
~~~

Đây là luồng khái niệm. Thời điểm gọi revocation, điều kiện OP chấp nhận logout, `id_token_hint`, allowed post-logout URI và session coupling phụ thuộc IdP và OIDC profile. **Không mặc định end-session endpoint luôn revoke refresh token** hoặc làm AT đang dùng ở mọi RS hết hạn ngay.

### 8.2. Front-channel và back-channel logout

Các đặc tả OIDC Front-Channel Logout và Back-Channel Logout mô tả cơ chế OP thông báo cho RP về sự kiện đăng xuất. Back-channel logout dùng **logout token** có claims/profile riêng để RP xử lý; **logout token không phải access token hoặc refresh token**.

RP nhận logout notification phải xác minh token/message theo profile, issuer, audience, session ID/subject và replay requirements, rồi invalid session tương ứng. Nếu RP cần revoke refresh token còn lưu thì phải có **bước/token policy riêng**, không chỉ xóa session UI.

### 8.3. Khi logout khỏi RP nhưng vẫn đăng nhập SSO

Alice logout `sales-dashboard`; RP xóa cookie phiên và revoke RT. Nếu OP session vẫn hoạt động, lần sau Alice truy cập ứng dụng có thể được đăng nhập lại nhanh bằng OIDC authorization flow, tùy `prompt`, policy OP và consent hiện hành. Điều đó **không chứng minh** logout trước đó thất bại: RP session cũ đã đóng nhưng SSO có thể vẫn sống.

Nếu product requirement là “logout toàn hệ thống SSO”, cần hỗ trợ ở OP và các RP, cùng quản lý token/grant. Không hứa logout mọi ứng dụng chỉ bằng xóa local cookie.

## 9. JWT, opaque token và hiệu lực logout tại resource server

Khi logout, AS có thể vô hiệu RT/grant; nhưng **bearer access token** còn hạn vẫn cần được kiểm soát riêng.

| Mô hình access token | RS xác minh bằng gì? | Điều xảy ra sau logout | Muốn chặn nhanh cần gì? |
| --- | --- | --- | --- |
| **JWT AT tự chứa** | Chữ ký/JWKS, `iss`, `aud`, `exp`, scope | Có thể vẫn hợp lệ tới `exp` nếu chỉ kiểm tra offline | Denylist, session-version check, introspection hoặc policy trạng thái tương đương |
| **Opaque AT** | AS introspection hoặc cơ chế trạng thái tin cậy | AS có thể trả `active:false` nếu token/grant đã bị revoke | TTL cache ngắn và bảo đảm revocation có hiệu lực tại AS |
| **Sender-constrained AT** | JWT/opaque validation + DPoP/mTLS proof | Copy token đơn thuần không đủ gọi API; token còn hạn vẫn tồn tại theo policy | Kết hợp revocation, expiry, audience/scope và bảo vệ private key |

### 9.1. Tại sao không tự ý đổi signing key khi user logout?

Khóa ký JWT thường dùng chung cho **nhiều** token, client và user. Xóa public key khỏi JWKS hoặc rotate signing key mỗi lần một người logout có thể khiến token hợp lệ của người khác bị từ chối và làm mất ổn định hệ thống. **Revocation của một session** cần cơ chế ở đúng mức hạt: token ID, grant/family/session hoặc policy server-side.

Key rotation phục vụ quản lý vòng đời và ứng phó khi **khóa ký bị lộ**, không phải công cụ logout thường nhật.

### 9.2. Một ví dụ về cửa sổ tồn tại của AT

~~~text
10:00  AS phát hành AT-1 (exp=10:05) và RT-1.
10:01  Alice logout; AS revoke RT-1.
10:02  Kẻ đã lấy AT-1 gọi orders-api.
10:05  AT-1 hết hạn.
~~~

- Nếu `orders-api` chỉ xác minh JWT offline, request 10:02 **có thể** thành công nếu token còn hợp lệ, đủ quyền và không có kiểm tra trạng thái logout.
- Nếu `orders-api` có session revocation lookup chính xác và đã cập nhật, request 10:02 bị từ chối.
- Nếu là opaque AT và introspection trả `active:false`, RS có thể từ chối; nếu cache `active:true` cũ còn hiệu lực, có thể có độ trễ.

**Yêu cầu sản phẩm phải ghi rõ:** Logout ngăn refresh ngay sau revocation xác nhận, hay còn phải ngăn **mọi access token hiện tại** trong tối đa N giây? Hai mức bảo đảm này đòi hỏi thiết kế khác nhau.

## 10. Khi không thể revoke tại AS: lỗi mạng và kết quả không chắc chắn

Một logout request có thể bị lỗi vì:

- AS timeout trước/sau khi xử lý revocation.
- Không có mạng từ BFF tới AS.
- Client authentication tới revocation endpoint lỗi.
- AS trả 5xx, 429 hoặc endpoint không hỗ trợ theo cấu hình.
- Browser đóng trang trước khi frontend nhận được response.

**Không thể suy ra “AS chưa revoke” chỉ từ timeout**, cũng không thể suy ra “AS chắc chắn đã revoke”. Kết quả cần được phân loại như sau:

| Trạng thái | Client/ứng dụng biết gì? | Hành động phù hợp |
| --- | --- | --- |
| Revocation trả 200 từ AS đáng tin | AS đã xử lý yêu cầu theo giao thức | Đóng local session, xóa token; giám sát AT policy |
| AS trả lỗi `invalid_client` | AS không chấp nhận client authentication | Đóng local session, sửa credential/config; không tự ghi remote revoked |
| Timeout hoặc connection reset | Kết quả remote chưa rõ | Đóng local session và ghi trạng thái pending để reconciliation an toàn |
| AS không hỗ trợ endpoint mong đợi | Không có bảo đảm revocation qua RFC 7009 | Cần API IdP khác, TTL/RS state policy hoặc thay thiết kế |
| Refresh/rotation race còn đang chạy | RT cuối cùng có thể khác bản vừa revoke | Phối hợp worker, revoke đúng RT/grant, không đánh dấu completed quá sớm |

### 10.1. Chọn UX chính xác

Có thể hoàn tất **logout local** và đưa user về trang chưa đăng nhập dù remote revocation bị lỗi, vì giữ user trong phiên chỉ để chờ AS có thể nguy hiểm. Tuy vậy, hệ thống **không được tuyên bố** rằng mọi refresh token đã bị revoke ở AS hoặc mọi API session đã bị chấm dứt.

Trong ứng dụng nhạy cảm, có thể hiển thị thông điệp rõ ràng rằng phiên trên thiết bị đã kết thúc nhưng việc ngắt các phiên ở hệ thống liên quan chưa được xác nhận, cùng hướng dẫn đổi mật khẩu/thu hồi thiết bị nếu cần. Thiết kế UX phải tuân thủ threat model và yêu cầu sản phẩm.

### 10.2. Retry revocation an toàn

Nếu ứng dụng cần retry, hãy bảo vệ dữ liệu dùng để retry:

1. Dùng hàng đợi trạng thái được mã hóa hoặc secure secret reference với TTL ngắn, hạn chế đọc.
2. Ràng buộc job với issuer/client/grant/session cụ thể; không trộn nhiều user hoặc tenant.
3. Sử dụng bounded retry/backoff/jitter; tuân thủ `Retry-After` nếu áp dụng.
4. Xóa raw RT/secret reference ngay khi đã xác nhận revoke hoặc token hết hạn theo policy.
5. Quan sát failure có correlation ID **không chứa raw token** và có cảnh báo khi backlog tăng.

Với nhiều AS, việc giữ RT để retry có thể gây rủi ro lưu trữ bổ sung; lựa chọn tốt hơn có thể là **revoke grant bằng handle không phải credential** nếu IdP có API phù hợp. Không tự tạo cơ chế lưu trữ RT rộng rãi chỉ để tối ưu UX.

## 11. Java/Spring Security: tích hợp logout và refresh-token revocation

Trong ứng dụng Spring Boot dùng Spring Security OAuth2 Client, một `OAuth2AuthorizedClient` có thể chứa access token và refresh token. Xóa bản ghi authorized client **chỉ tác động vào nơi ứng dụng lưu token**, không mặc nhiên gọi revocation endpoint của authorization server.

### 11.1. Local logout với Spring Security

Ví dụ một ứng dụng servlet dùng session cookie:

~~~java
@Configuration
@EnableWebSecurity
class ApplicationSecurity {

    @Bean
    SecurityFilterChain filterChain(
            HttpSecurity http,
            LogoutHandler refreshTokenLogoutHandler) throws Exception {

        http.logout(logout -> logout
                .logoutUrl("/logout")
                .addLogoutHandler(refreshTokenLogoutHandler)
                .invalidateHttpSession(true)
                .clearAuthentication(true)
                .deleteCookies("JSESSIONID"));

        return http.build();
    }
}
~~~

Ví dụ minh họa lớp logout của Spring Security: bảo đảm cấu hình CSRF, session storage và tên cookie đúng theo ứng dụng. Không vô hiệu CSRF chỉ để POST `/logout` cho dễ thử. Nếu ứng dụng là API stateless chỉ sử dụng bearer token, sẽ không có servlet session để xóa; lúc đó cần thiết kế endpoint revoke/grant ở đúng tầng quyền.

### 11.2. Đọc refresh token của đúng authorized client

Một `LogoutHandler` minh họa:

~~~java
@Component
class RefreshTokenLogoutHandler implements LogoutHandler {

    private final OAuth2AuthorizedClientService authorizedClients;
    private final LogoutCoordinator logoutCoordinator;

    RefreshTokenLogoutHandler(
            OAuth2AuthorizedClientService authorizedClients,
            LogoutCoordinator logoutCoordinator) {
        this.authorizedClients = authorizedClients;
        this.logoutCoordinator = logoutCoordinator;
    }

    @Override
    public void logout(
            HttpServletRequest request,
            HttpServletResponse response,
            Authentication authentication) {

        if (authentication == null) {
            return;
        }

        String registrationId = "sales-dashboard";
        String principalName = authentication.getName();

        // Điều phối theo đúng session/grant trước khi revoke.
        logoutCoordinator.freezeAndRevokeOrSchedule(
                registrationId, principalName, request.getSession(false));

        // Chỉ xóa local authorized-client record; thao tác này
        // KHÔNG phải OAuth token revocation tại authorization server.
        authorizedClients.removeAuthorizedClient(
                registrationId, principalName);
    }
}
~~~

**Quan trọng:** `LogoutCoordinator` là một **interface/abstraction của ứng dụng**, chưa được Spring Security cung cấp mặc định và chưa được định nghĩa trong ví dụ; phương thức `freezeAndRevokeOrSchedule` phải do đội phát triển triển khai đúng chính sách:

- Khóa/đánh dấu đúng session đang logout trước khi worker bắt đầu refresh.
- Tìm bản RT mới nhất và các refresh operations đang chạy, đồng bộ giữa các node.
- Gọi AS revocation (hoặc family/grant API nếu được hỗ trợ) với client authentication phù hợp.
- Lưu trạng thái xác nhận hoặc pending, xử lý timeout/retry an toàn.
- Đảm bảo không làm ảnh hưởng phiên của user/thiết bị khác.

Đoạn code không phải giải pháp production hoàn chỉnh: `registrationId + principalName` **có thể không phân biệt nhiều browser session** của cùng user/client nếu storage chia sẻ authorized client; application cần một session/grant key đúng mô hình lưu trữ. Việc gọi một method trước `removeAuthorizedClient` cũng **không tự tạo bảo đảm giao dịch** giữa database local và AS từ xa.

Nếu ứng dụng sử dụng `OAuth2AuthorizedClientRepository` gắn token với HTTP session thay vì `OAuth2AuthorizedClientService`, phải lấy và xóa credential theo repository/session tương ứng; không giả định tất cả cấu hình dùng cùng một kho.

### 11.3. Gọi revocation endpoint bằng HTTP

Một revocation client server-side có thể dùng Spring `RestClient` với form body:

~~~java
MultiValueMap<String, String> form = new LinkedMultiValueMap<>();
form.add("token", currentRefreshToken);
form.add("token_type_hint", "refresh_token");

ResponseEntity<Void> response = restClient.post()
        .uri("https://auth.example.test/oauth2/revoke")
        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
        .headers(headers -> headers.setBasicAuth(
                registeredClientId, protectedClientSecret))
        .body(form)
        .retrieve()
        .toBodilessEntity();
~~~

Trong ví dụ, `restClient`, `currentRefreshToken`, `registeredClientId` và `protectedClientSecret` là các giá trị do hệ thống cấu hình/quản lý an toàn; không hardcode secret hoặc RT thật. Dùng **HTTP Basic** chỉ khi AS đăng ký `client_secret_basic`; nếu dùng `private_key_jwt`, mTLS hoặc một phương thức khác, phải cấu hình cách xác thực client đúng.

`RestClient.retrieve()` có thể ném exception với mã lỗi HTTP theo cấu hình. Thực tế cần timeout, che token trong log, giới hạn redirect, phân loại `200`/`4xx`/`5xx` và xử lý **unknown outcome**. Không đọc `currentRefreshToken` từ tham số request do browser cung cấp nếu backend vốn sở hữu phiên/RT; request logout nên xác định đúng session bằng authentication/cookie bảo vệ.

### 11.4. Không để logout handler tạo cơ hội mint RT mới

Một cách tổ chức rõ ràng là **điều phối riêng**:

~~~text
LogoutCoordinator.freezeAndRevokeOrSchedule(grantKey):
    atomically:
        mark grantKey as LOGGING_OUT
        reject any new refresh acquisitions for this grantKey

    await/coordinate any in-flight refresh with a bounded deadline
    finalGrant = read current AS grant/family handle (if supported)
    finalRt    = read newest protected RT for this grantKey

    if finalGrant is available:
        revoke grant/family using AS-specific authorized API
    else if finalRt is available:
        POST /revoke with finalRt and correct client authentication

    if remote outcome is confirmed:
        mark revoked/closed
    else:
        mark local closed + remote revocation pending

    remove local token references and invalidate application session
    ensure any late refresh result cannot restore session
~~~

Đây là **pseudo-code**, không phải API Spring thực tế. Sự tồn tại và cú pháp `grant/family handle` phụ thuộc IdP. Khi chỉ có RFC 7009 token revocation, phải giải quyết race bằng token manager/AS semantics thay vì giả định endpoint có chức năng revoke entire family.

### 11.5. Dùng OIDC logout handler khác với RT revocation

Ở ứng dụng OIDC hỗ trợ RP-Initiated Logout, Spring Security cung cấp các tiện ích liên quan logout như `OidcClientInitiatedLogoutSuccessHandler` (theo phiên bản). Nó có thể điều hướng browser tới endpoint logout của OP. **Nó không tự bảo đảm refresh token được revoke bằng RFC 7009**, không bảo đảm mọi RS chặn AT còn hạn và không thay thế logic revoke RT/grant nếu policy yêu cầu.

Vì vậy, trong thiết kế logout kết hợp OIDC + OAuth, cần xác định rõ:

~~~text
Local application session cleanup
    + Refresh token/grant revocation tại AS
    + OIDC OP session logout nếu người dùng yêu cầu
    + Access-token invalidation strategy tại resource servers
~~~

Từng bước có thể thất bại riêng; hệ thống cần tính toán trạng thái và thông điệp cho user tương ứng.

## 12. Thực hành lưu trữ, phát hiện đánh cắp và bảo vệ credential

Một RT có thể sống lâu hơn AT nên thường có giá trị lớn đối với kẻ tấn công. Nếu RT bị lộ trước logout, kẻ tấn công có thể cố refresh để lấy AT mới hoặc xoay vòng RT, làm client hợp lệ gặp `invalid_grant`. Vì vậy, logout đúng cần được hỗ trợ bởi **bảo vệ từ lúc phát hành**:

| Lớp phòng vệ | Ví dụ | Vai trò |
| --- | --- | --- |
| **Lưu trữ** | BFF lưu RT trong token store mã hóa, least privilege; native app dùng secure storage phù hợp | Giảm khả năng lấy RT |
| **Truyền tải** | HTTPS/TLS, client authentication đúng, không chuyển tiếp RT tới RS | Ngăn lộ credential trên đường đi |
| **Rotation/replay** | RT rotation và phát hiện RT cũ bị reuse; token family tracking | Phát hiện bản sao RT bị dùng cạnh tranh |
| **Sender constraint** | Sender-constrained refresh token khi AS và client hỗ trợ | Làm credential khó dùng nếu chỉ bị sao chép |
| **Thời hạn** | Idle/absolute expiry, revoke khi đóng grant | Hạn chế khả năng duy trì phiên vô hạn |
| **Xác thực và quyền** | Kiểm tra client binding, grant/consent và tenant trên refresh | Không cho dùng RT sai client hoặc quyền |
| **Thu hồi** | RFC 7009 hoặc revoke grant/family theo AS | Chặn xin AT mới sau logout |
| **Giám sát** | Sự kiện refresh reuse, failed revocation, anomalous token issuance | Phát hiện và xử lý compromise |

### 12.1. Refresh-token rotation không phải cơ chế chống đánh cắp tuyệt đối

Nếu kẻ tấn công sao chép RT-1 rồi sử dụng **trước** client hợp lệ, AS có thể cấp RT-2 cho attacker. Sau đó khi client dùng RT-1 cũ, AS phát hiện reuse và có thể thu hồi family. Rotation giúp **phát hiện bất thường**, nhưng có thể đã có AT được cấp cho attacker trước lúc hệ thống phát hiện.

Khi user logout, cần kiểm tra log/telemetry xem RT có bị rotate bất thường hay không; không chỉ tin bản RT cuối cùng local thấy là credential duy nhất còn tồn tại. Chính sách AS về family revocation và incident response quyết định cách xử lý rộng hơn.

### 12.2. Không ghi RT vào log khi logout thất bại

Một lỗi logging phổ biến:

~~~text
ERROR Revoke failed: POST /revoke body=token=RT-SECRET-123...
~~~

Đây là **rò rỉ RT thứ hai**, có thể bị khai thác ngay cả khi sự cố ban đầu chỉ là timeout. Thay vào đó, log:

~~~text
WARN oauth_revocation_pending
     client=sales-dashboard
     session_ref=<non-secret-reference>
     error_class=TIMEOUT
     correlation_id=<request-id>
~~~

`session_ref` phải là tham chiếu không bí mật, không cho phép bearer-style access và không bị lộ sang bên không có quyền. Nếu cần so khớp sự kiện theo token, sử dụng fingerprint/HMAC được quản lý an toàn thay vì raw token. Không ghi private key, client secret, PKCE verifier, bearer AT hay RT vào audit trail.

### 12.3. XSS, CSRF và logout endpoint

Ở browser:

- XSS có thể gây request bằng quyền phiên hiện có ngay cả khi JavaScript không đọc được `HttpOnly` cookie. Ngăn XSS vẫn cần thiết.
- Logout POST sử dụng cookie phiên tự động gửi cần CSRF defense phù hợp, để bên thứ ba không ép người dùng logout hoặc kích hoạt thay đổi trạng thái ngoài ý muốn.
- `SameSite` hỗ trợ giảm một số CSRF, nhưng không được xem là biện pháp duy nhất trong mọi kiến trúc.
- Nếu refresh token nằm trong localStorage, một script độc hại có thể lấy nó trước khi user logout. Xóa localStorage sau logout không thể xóa **bản sao đã bị lấy cắp**; cần revoke tại AS.

Trong backend, bảo vệ revocation endpoint khỏi SSRF/redirect, cấu hình AS URL từ nguồn tin cậy và bảo vệ kết nối giữa gateway–service. Không gửi RT tới resource server để “nhờ API logout”: RT chỉ nên tới token/revocation endpoints của AS có thẩm quyền theo hợp đồng.

## 13. Bộ kiểm thử âm/dương cho logout và refresh token

Các bài kiểm thử nên dùng AS/IdP test, token giả có entropy phù hợp, simulated time và nhiều worker để bắt race. Không dùng RT thật trong file test, CI logs hoặc screenshot.

| ID | Kịch bản | Kết quả mong đợi |
| --- | --- | --- |
| L01 | User logout khi RT còn hoạt động | Local session đóng; revoke RT/grant đúng phạm vi được yêu cầu |
| L02 | Sau logout, thử dùng RT đã revoke tại `/token` | AS từ chối cấp AT mới theo hợp đồng (thường `invalid_grant`) |
| L03 | Logout lần thứ hai với phiên đã đóng | Không hồi sinh session; local logout an toàn, không lộ token |
| L04 | RFC 7009 revoke một token không tồn tại | AS trả 200 theo semantics chuẩn nếu request hợp lệ |
| L05 | `token_type_hint=refresh_token` sai hoặc không có | AS xử lý theo chuẩn/hợp đồng, không dựa hoàn toàn vào hint |
| L06 | Client A cố revoke token của client B | AS không cho can thiệp grant trái binding |
| L07 | Logout user A, user B vẫn đăng nhập | Không xóa token/phiên của B |
| L08 | Logout một thiết bị, thiết bị khác cùng user còn dùng | Kết quả đúng phạm vi per-device AS hỗ trợ |
| L09 | Chọn logout mọi thiết bị | Tất cả grant/session liên quan bị thu hồi theo API IdP, không chỉ RT hiện tại |
| L10 | Refresh RT-1 thành RT-2 rồi logout | Revoke RT-2/family, không chỉ RT-1 ancestor |
| L11 | Refresh đang in-flight khi logout bắt đầu | Refresh result không được ghi để hồi sinh session |
| L12 | Hai Pod refresh/logout đồng thời | Phối hợp nguyên tử, không bỏ sót RT mới; test nhiều interleavings |
| L13 | CAS update RT mới thất bại vì session đã LOGGING_OUT | Worker không lưu token mới; cleanup xử lý credential vừa nhận |
| L14 | Revocation response timeout sau khi AS đã commit | Local logout vẫn đóng; ghi unknown outcome, reconciliation an toàn |
| L15 | AS trả `invalid_client` khi revoke | Không báo remote revoked; log an toàn, recovery cấu hình |
| L16 | AS outage trong lúc logout | Không tiếp tục phiên local; có pending state/hạn mức retry khi phù hợp |
| L17 | AS trả 200 khi RT đã invalid | Không khôi phục RT, không tiết lộ trạng thái token trước đó |
| L18 | JWT AT còn hạn sau khi RT bị revoke | RS theo đúng TTL/denylist/session-state policy; không mặc định chặn tức thì |
| L19 | Opaque AT `active:false` sau revoke | RS từ chối; kiểm tra caching và SLA thực tế |
| L20 | Opaque introspection cache `active:true` cũ | Đo độ trễ thu hồi; không vượt policy đã cam kết |
| L21 | User logout ở RP nhưng OP SSO session còn | RP session vẫn đóng; SSO có thể cho login lại theo policy |
| L22 | OP logout front-/back-channel notification hợp lệ | RP xác minh notification và đóng đúng phiên tương ứng |
| L23 | Logout notification giả/sai issuer hoặc audience | RP từ chối, không đóng phiên người khác |
| L24 | Client credentials job không có RT | Không cố rotate RT không tồn tại; quản lý service credential và AT theo policy |
| L25 | RT bị đánh cắp và rotate trước client thật | Reuse detection/incident response theo token-family policy |
| L26 | BFF logout form POST từ origin không được phép | CSRF/session check chặn request theo chính sách |
| L27 | Backend ghi request revoke vào log lỗi | Kiểm tra raw AT/RT/client secret không xuất hiện trong logs |
| L28 | Revoke RT đúng nhưng AT sai audience được gửi tới API khác | RS vẫn từ chối AT sai audience độc lập với logout |
| L29 | Logout do người dùng mất thiết bị, chỉ biết session ID | Chỉ actor được ủy quyền mới được revoke đúng session/device |
| L30 | Mất response khi revoke và secure retry chạy lại | Không tạo grant/token mới; không tiết lộ credential |

### 13.1. Test có giá trị phải kiểm tra cả remote và local

Kiểm thử “browser không còn cookie” **chưa chứng minh** RT bị revoke ở AS. Để kiểm tra logout:

1. Tạo phiên và RT test, xác minh trước logout rằng refresh hợp lệ có thể cấp AT.
2. Gọi logout, kiểm tra local session/token store đã đóng theo policy.
3. Thử refresh bằng **RT đã được thu hồi** với test client/AS phù hợp, chờ phản hồi của AS.
4. Kiểm tra mọi RT còn hoạt động trong family/session theo khả năng quan sát hợp lệ của AS.
5. Nếu yêu cầu chặn AT tức thì, gọi resource server với AT còn hạn và xác minh nó thực sự bị từ chối; nếu policy chỉ chặn sau `exp`, kiểm tra thời gian đó chính xác.

Khi làm bước 3, không tự tạo nhiều replay request trên production. Trong test environment, tái sử dụng RT có thể kích hoạt revoke family/incident alerts; cần hiểu và cách ly các sự kiện này.

### 13.2. Test race bằng cách cố định các điểm dừng

Thay vì dựa vào sleep ngẫu nhiên, dùng test barrier/fake AS để kiểm soát thời điểm:

~~~text
T0  Refresh worker đọc RT-1.
T1  Refresh request đang ở token endpoint nhưng chưa nhận response.
T2  Logout chuyển session ACTIVE → LOGGING_OUT.
T3  AS trả RT-2 cho refresh worker.
T4  Worker cố lưu RT-2; CAS phải fail vì logout.
T5  Hệ thống revoke RT-2 hoặc grant/family theo policy.
T6  Xác nhận không còn local session có thể refresh.
~~~

Đảo thứ tự T2/T3 và thêm các ca AS timeout, crash node, retry để kiểm tra các interleaving. Một test chỉ chạy tuần tự có thể bỏ sót chính race dẫn đến “logout rồi vẫn còn RT sống”.

## 14. Ba tình huống kiến trúc

### Tình huống A: “Logout thành công”, nhưng refresh token vẫn hoạt động

Ứng dụng SPA lưu `AT-1` và `RT-1` ở browser. Khi user bấm logout, frontend xóa storage và chuyển sang trang login. Kẻ tấn công đã lấy `RT-1` trước đó và tiếp tục gọi `/token`, nhận `AT-2`.

**Chẩn đoán:** Ứng dụng chỉ hoàn tất local logout. AS vẫn nhận RT vì chưa có revocation. Nếu RT bị đánh cắp, việc xóa ở browser không xóa bản sao của attacker.

**Giải pháp:** Tích hợp revocation endpoint của AS, dùng loại client và authentication phù hợp; cân nhắc BFF để lưu RT phía server; áp policy rotation/sender constraint, giới hạn TTL và cơ chế xử lý AT đã cấp. Không phát hành một refresh token mới khi logout để “thay” RT bị lộ.

### Tình huống B: Logout đúng lúc refresh gây token rơi ngoài tầm kiểm soát

`sales-dashboard` đang dùng RT-1. Tab A bắt đầu refresh; tab B bấm logout. Tab B revoke RT-1. Tab A nhận RT-2 rồi ghi vào token store; lần mở trang sau ứng dụng lại tự đăng nhập bằng RT-2.

**Chẩn đoán:** Logout và refresh không được phối hợp. AS có thể đã rotate trước khi xử lý revoke RT-1, khiến RT-2 vẫn hoạt động tùy chính sách.

**Giải pháp:** Một session state machine, khóa bắt đầu refresh mới khi logout, phối hợp request đang chạy, CAS/version ngăn ghi hậu logout và cleanup RT mới; ưu tiên grant/family revocation khi AS hỗ trợ đúng semantics.

### Tình huống C: Logout ở SSO nhưng API vẫn chấp nhận JWT

Alice đăng xuất khỏi OIDC provider và ứng dụng; RT bị revoke tại AS. Trước đó một JWT access token có `aud=orders-api`, `scope=orders.read` và `exp` còn bốn phút đã bị sao chép. `orders-api` chỉ xác minh chữ ký/JWKS offline.

**Chẩn đoán:** AS/OP session đã đóng, nhưng RS không có cơ chế nhận biết token cụ thể đã bị vô hiệu trước `exp`. Đây không phải lỗi chữ ký JWT, mà là **khoảng trễ giữa logout và xác minh token tự chứa**.

**Giải pháp:** Quy định logout SLA rõ. Nếu chấp nhận tối đa bốn phút, dùng TTL ngắn, giới hạn audience/scope, bảo vệ token và thông tin minh bạch. Nếu yêu cầu chặn tức thì, bổ sung token/session revocation state tại RS, denylist, introspection hoặc token version lookup theo năng lực hệ thống.

## 15. Checklist thiết kế logout gắn với refresh token

Trước khi đưa vào production, cần trả lời:

1. **Khái niệm:** Chúng ta đang *rotate RT khi refresh* hay *revoke RT/grant khi logout*? API, tên biến và tài liệu có phân biệt rõ?
2. **Đúng loại credential:** Không gửi RT tới resource API; không dùng ID token hoặc logout token như access token.
3. **Đúng issuer và client:** Revocation endpoint cố định từ AS tin cậy; client xác thực bằng phương thức đã đăng ký, TLS và bảo vệ token trong request.
4. **Đúng phạm vi:** Logout phiên hiện tại, thiết bị hiện tại, tất cả thiết bị hay revoke toàn bộ consent? Hệ thống có định danh session/grant và quyền thao tác rõ ràng?
5. **Đúng token cuối:** Có xử lý refresh in-flight và RT đã rotate? Có ngăn RT mới bị ghi sau khi session đóng?
6. **Đúng semantics AS:** RFC 7009 xử lý token đã invalid ra sao; AS có revoke AT liên quan, token family, session/grant hay chỉ một RT?
7. **Đúng local state:** Session và authorized-client store được xóa/khóa; refresh không thể khởi động lại sau logout?
8. **Đúng lỗi mạng:** Phân biệt local logout thành công với remote revoke chưa được xác nhận; retry/reconciliation được bảo vệ và giới hạn?
9. **Đúng logout OIDC:** Local RP session, OP SSO session, refresh token/grant và resource-server AT được xử lý như các lớp khác nhau?
10. **Đúng AT policy:** JWT/opaque AT còn hạn sau logout được chấp nhận bao lâu; đã đo SLA thu hồi thực tế chưa?
11. **Đúng phòng vệ:** BFF/secure storage khi phù hợp, TLS, CSRF/XSS defense, refresh rotation/sender constraints và bảo vệ private key?
12. **Đúng kiểm thử:** Có test nhiều thiết bị, nhiều instance, logout-refresh race, RT family, unknown network outcome, replay detection và token không lộ log?

### Câu hỏi tự kiểm tra

**Câu 1.** Khi Alice nhấn Logout, AS có nên cấp `RT-2` thay cho `RT-1` để “đổi token an toàn” không?

**Trả lời:** Không, nếu mục đích là kết thúc phiên. Cần revoke RT/grant phù hợp, không mint credential thay thế cho phiên đã logout. Rotation diễn ra khi một phiên **tiếp tục** và request refresh hợp lệ.

**Câu 2.** Xóa RT khỏi database của BFF có bảo đảm RT bị đánh cắp trước đó không còn dùng được không?

**Trả lời:** Không. Cần revocation/expiry tại AS và chính sách replay detection. Xóa bản local không hủy bản sao bên ngoài.

**Câu 3.** Client nhận HTTP 200 sau `POST /revoke`. Nó có biết token đã từng tồn tại hay thuộc đúng user nào không?

**Trả lời:** Không. Theo RFC 7009, AS có thể trả 200 cho token đã invalid để không tiết lộ trạng thái tồn tại của credential.

**Câu 4.** Revoke RT tại AS có đảm bảo `orders-api` lập tức từ chối JWT access token còn hạn không?

**Trả lời:** Không mặc định. Nếu RS xác minh JWT offline và không tra trạng thái revoke/denylist, AT có thể tiếp tục dùng đến `exp`.

**Câu 5.** Hai Pod đồng thời refresh và logout; logout revoke RT-1 nhưng refresh nhận RT-2. Có thể xem logout đã hoàn tất an toàn không?

**Trả lời:** Chưa chắc. Cần kiểm tra RT-2/grant/family theo semantics AS, ngăn lưu credential mới sau logout và có cơ chế cleanup/revocation cho kết quả refresh đến muộn.

**Câu 6.** OIDC RP-Initiated Logout tự động tương đương RFC 7009 refresh-token revocation không?

**Trả lời:** Không. Logout tại OP/SSO, đóng session ở RP và revoke OAuth RT là các cơ chế độc lập có thể được phối hợp theo chính sách IdP/ứng dụng.

**Câu 7.** Nếu revocation endpoint timeout, ứng dụng nên giữ session người dùng hoạt động cho đến khi AS trả kết quả không?

**Trả lời:** Không nhất thiết, và thường không nên giữ local session chỉ vì revocation từ xa chưa xác nhận. Có thể logout local ngay, ghi remote outcome là **unknown/pending**, bảo vệ retry/reconciliation và không khẳng định token ở AS đã bị thu hồi.

**Câu 8.** Nếu ứng dụng chỉ có `client_credentials` và không được cấp refresh token, cần “rotate RT khi service logout” không?

**Trả lời:** Không. Cần quản lý vòng đời machine credential, access token, workload identity và revocation theo mô hình service; không tự tạo RT cho grant vốn không dùng RT.

## 16. Tài liệu chuẩn tham khảo

- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): access token, refresh token, refresh grant, client binding và client credentials.
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): revocation endpoint, `token`, `token_type_hint` và phản hồi đối với token invalid.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): trạng thái `active` và metadata cho resource server.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): refresh token rotation/sender constraint, replay detection và bảo vệ token.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): truyền AT, bearer replay risk và response lỗi.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): claims, issuer, audience và thời hạn AT.
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): `exp`, `iss`, `aud` và `jti`.
- [RFC 8705 — OAuth 2.0 Mutual TLS](https://www.rfc-editor.org/rfc/rfc8705) và [RFC 9449 — OAuth 2.0 DPoP](https://www.rfc-editor.org/rfc/rfc9449): sender-constrained tokens.
- [OpenID Connect RP-Initiated Logout 1.0](https://openid.net/specs/openid-connect-rpinitiated-1_0.html): yêu cầu kết thúc phiên ở OpenID Provider.
- [OpenID Connect Front-Channel Logout 1.0](https://openid.net/specs/openid-connect-frontchannel-1_0.html) và [Back-Channel Logout 1.0](https://openid.net/specs/openid-connect-backchannel-1_0.html): thông báo logout từ OP đến RP.
- [Spring Security — OAuth2 Client](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html): quản lý authorized clients và tích hợp OAuth2.
- [Spring Security — Logout](https://docs.spring.io/spring-security/reference/servlet/authentication/logout.html): local logout handlers, session invalidation và cookie cleanup.

**Điểm cần nhớ:** Với câu hỏi “đổi refresh token khi đăng xuất”, **điều đúng thường là thu hồi refresh token/grant chứ không xoay vòng để cấp token mới**. Rotation thuộc quá trình refresh nhằm duy trì phiên và phát hiện credential bị dùng lại; logout nhằm đóng phiên và ngăn tiếp tục phát hành AT. Thiết kế phải giải quyết **race giữa refresh và logout**, phân biệt phạm vi một thiết bị/toàn bộ grant, phối hợp OAuth revocation với OIDC logout và xác định rõ AT còn hạn được xử lý thế nào ở JWT hoặc opaque resource server. Chỉ khi trạng thái AS, local session và chính sách RS cùng nhất quán, hệ thống mới có thể đưa ra lời hứa logout phù hợp với mức bảo mật thực tế.
