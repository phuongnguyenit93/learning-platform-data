# Local logout

**Local logout** là thao tác chấm dứt phiên đăng nhập do một ứng dụng hoặc một relying party (RP) đang quản lý. Khi người dùng chọn đăng xuất khỏi nền tảng học tập, ứng dụng phải vô hiệu hóa session phía server, ngừng chấp nhận cookie/session credential tương ứng, xử lý refresh token thuộc phiên đó và xóa trạng thái xác thực cục bộ ở client. Mục tiêu là khiến credential của phiên hiện tại không còn cấp quyền truy cập vào ứng dụng sau thời điểm logout được xác nhận.

Local logout có phạm vi cụ thể: nó chấm dứt phiên tại ứng dụng hiện tại. Nó không mặc nhiên đăng xuất người dùng khỏi Identity Provider (IdP), các ứng dụng SSO khác, thiết bị khác hoặc mọi phiên của account. Đây là điểm quan trọng trong hệ thống liên kết danh tính: cookie của ứng dụng và cookie SSO của IdP thường thuộc các miền và vòng đời khác nhau.

Bài học thuộc chương **Đăng xuất** của module **SECURITY_AUTHENTICATION_FUNDAMENTALS**. Người học cần hiểu cách kết thúc session server-side, xóa cookie đúng phạm vi, thu hồi refresh token, xử lý access token đã phát hành, đồng bộ nhiều tab/thiết bị, bảo vệ endpoint logout trước CSRF và phân biệt local logout với RP-Initiated Logout hoặc global logout.

Điểm cốt lõi: **xóa cookie trên browser không đủ để bảo đảm phiên đã bị chấm dứt**. Nếu session ID hoặc refresh token đã bị sao chép, credential đó vẫn có thể được sử dụng ở nơi khác trừ khi server đã thu hồi trạng thái tương ứng. Một quy trình logout an toàn phải xử lý cả trạng thái server, credential client và phạm vi federation theo đúng chính sách.

## 1. Local logout giải quyết điều gì?

Trong một ứng dụng web, người dùng thường đăng nhập một lần rồi gửi nhiều request với session cookie. Server tra cookie để xác định session và principal. Khi người dùng logout, ứng dụng cần làm cho session đó không còn hợp lệ.

Luồng khái quát:

1. Người dùng chủ động chọn Logout.
2. Browser gửi request logout tới đúng ứng dụng, kèm credential session và CSRF protection phù hợp.
3. Server xác định session hiện tại, kiểm tra request và ghi nhận yêu cầu chấm dứt.
4. Server đánh dấu session revoked/terminated và vô hiệu hóa các credential có phạm vi thuộc session đó theo policy.
5. Server gửi response xóa cookie bằng cùng phạm vi cookie đã thiết lập.
6. Client xóa trạng thái xác thực cục bộ, cập nhật giao diện và thông báo kết quả.
7. Hệ thống ghi audit event không chứa secret.

Một response logout thành công không nên chỉ có nghĩa “trình duyệt đã xóa một chuỗi”. Nó phải phản ánh việc server đã ngừng chấp nhận session credential.

### 1.1. Ví dụ luồng local logout

    Người dùng
      |
      | Chọn Logout
      v
    Browser
      |
      | POST /logout + session cookie + CSRF token
      v
    Ứng dụng / RP
      |
      | Xác minh request và xác định session
      v
    Session Store
      |
      | Thu hồi session hiện tại
      v
    Ứng dụng / RP
      |
      | (Nếu có) yêu cầu Authorization Server revoke refresh token
      | Set-Cookie hết hạn + response logout
      v
    Browser
      |
      | Xóa state xác thực ở client
      v
    Người dùng thấy trạng thái đã đăng xuất

Authorization Server có thể là một dịch vụ riêng hoặc cùng hệ thống với ứng dụng. Nếu ứng dụng dùng server-side session và không có refresh token, bước gọi authorization server không cần thiết.

### 1.2. Logout là một thao tác thay đổi trạng thái

Logout làm thay đổi trạng thái session và có thể làm mất khả năng truy cập hiện tại. Vì vậy endpoint local logout cần được bảo vệ trước request giả mạo. Không nên thực hiện logout chỉ vì browser tải một URL bằng GET, ví dụ khi attacker nhúng liên kết logout vào trang bên ngoài.

Một số giao thức federation có endpoint logout và tham số riêng. Chúng cần tuân theo specification của giao thức; không nên đồng nhất endpoint local logout của ứng dụng với endpoint federation.

## 2. Phân biệt các phạm vi logout

Từ “đăng xuất” có thể chỉ nhiều hành động khác nhau. UI và API cần xác định rõ phạm vi để người dùng biết điều gì sẽ xảy ra.

| Phạm vi | Hành động | Điều không mặc nhiên xảy ra |
| --- | --- | --- |
| **Local logout** | Chấm dứt session tại ứng dụng hiện tại. | Không xóa session ở IdP hoặc ứng dụng khác. |
| **Current browser session** | Chấm dứt phiên hiện tại trong browser đang dùng. | Không nhất thiết chấm dứt phiên trên browser khác. |
| **Current device logout** | Thu hồi các phiên/credential được gắn với thiết bị hiện tại theo policy. | Không nhất thiết ảnh hưởng thiết bị khác. |
| **All application sessions** | Thu hồi mọi session của account tại một ứng dụng. | Không nhất thiết đăng xuất khỏi IdP hay dịch vụ khác. |
| **Global/IdP logout** | Kết thúc phiên tại IdP và phối hợp logout với RP liên quan nếu giao thức hỗ trợ. | Không bảo đảm mọi hệ thống downstream đã nhận sự kiện ngay lập tức. |
| **Account disable / incident containment** | Khóa account hoặc thu hồi rộng hơn theo phản ứng sự cố. | Đây không chỉ là thao tác logout thông thường. |

### 2.1. Local logout không đồng nghĩa global logout

Giả sử người dùng đăng nhập vào IdP công ty, sau đó mở ứng dụng học tập và ứng dụng quản lý nhân sự. Mỗi ứng dụng có thể tạo session riêng sau khi nhận kết quả federation.

Khi người dùng logout khỏi ứng dụng học tập:

- Session tại ứng dụng học tập cần bị thu hồi.
- Cookie của ứng dụng học tập cần được xóa.
- Refresh token thuộc client/session đó cần được xử lý theo policy.
- Session tại ứng dụng nhân sự có thể vẫn còn hiệu lực.
- Cookie SSO tại IdP có thể vẫn còn, vì vậy lần truy cập lại ứng dụng học tập có thể đăng nhập nhanh hoặc không cần nhập credential.

Điều này là hành vi bình thường nếu sản phẩm chỉ cung cấp local logout. Nếu UX cần “đăng xuất khỏi mọi ứng dụng”, phải triển khai global logout theo giao thức và khả năng của IdP.

### 2.2. Logout hiện tại và logout tất cả thiết bị

Nút “Logout” thường nên chấm dứt session đang sử dụng. Chức năng “Sign out all devices” cần một hành động riêng, có thể yêu cầu step-up vì nó tác động tới nhiều phiên và có thể làm gián đoạn công việc.

Server cần biết session nào thuộc account, thiết bị hoặc client nào. Không thể suy ra mọi phiên của một người chỉ bằng cách xóa cookie browser hiện tại.

## 3. Vô hiệu hóa session phía server

Với server-side session, browser thường chỉ giữ một opaque session ID. Server lưu record chứa account, tenant, trạng thái, thời hạn và metadata xác thực. Local logout cần thay đổi record hoặc trạng thái tra cứu sao cho session ID cũ không còn được chấp nhận.

Ví dụ record khái niệm:

    {
      "session_id_hash": "keyed-hash-of-session-id",
      "subject_id": "usr-57",
      "client_id": "learning-web",
      "tenant_id": "org-7",
      "created_at": "2026-11-22T05:00:00Z",
      "last_seen_at": "2026-11-22T05:10:00Z",
      "absolute_expires_at": "2026-11-22T13:00:00Z",
      "status": "active",
      "revoked_at": null
    }

Khi logout, server có thể chuyển status sang revoked, đặt revoked_at hoặc xóa record theo thiết kế. Giữ một tombstone ngắn hạn có thể hữu ích cho replay detection, audit và đồng bộ cache; không cần giữ dữ liệu session lâu hơn yêu cầu.

### 3.1. Không chỉ dựa vào cookie expiry

Cookie có thể hết hạn ở browser nhưng session record vẫn active. Nếu attacker đã sao chép session ID trước đó, họ có thể gửi cookie từ một client khác cho tới khi server thu hồi hoặc session hết hạn.

Ngược lại, server có thể thu hồi session trước khi cookie hết hạn. Browser vẫn gửi cookie cũ, nhưng server từ chối vì session không còn active. Vì vậy server-side invalidation là bước quyết định.

### 3.2. Session ID phải trở nên vô dụng sau logout

Sau khi session bị thu hồi:

- Mọi request mới dùng session ID đó phải bị từ chối.
- Không được tự động tạo lại session đã logout chỉ vì cookie vẫn còn.
- Không chấp nhận session ID cũ như bằng chứng đăng nhập khi cache/store tạm lỗi.
- Không cho endpoint refresh hoặc endpoint phụ khôi phục session đã revoked.
- Không tái sử dụng cùng session ID cho lần đăng nhập tiếp theo.

Lần đăng nhập sau phải tạo session ID mới bằng CSPRNG. Không “reactivate” session cũ để tiết kiệm thao tác.

### 3.3. Session store phân tán và cache

Trong hệ thống nhiều instance, session có thể được lưu trong Redis, database hoặc session service. Logout cần cập nhật trạng thái sao cho mọi node ngừng chấp nhận session.

Nếu một node cache kết quả active quá lâu, node đó có thể tiếp tục cho phép request sau logout. Cần:
- Cache TTL phù hợp với yêu cầu thu hồi.
- Cơ chế invalidation/event để các node nhận trạng thái revoke.
- Kiểm tra version/status mới nhất trước action nhạy cảm.
- Xử lý event duplicate/out-of-order và lỗi đồng bộ.
- Định nghĩa rõ mức trễ thu hồi tối đa mà hệ thống chấp nhận.

Với session quản trị hoặc dữ liệu nhạy cảm, không nên phụ thuộc vào cache active dài hạn. Nếu session store không khả dụng, chính sách phải ưu tiên từ chối các request cần session thay vì coi session chưa kiểm tra là hợp lệ.

## 4. Xử lý refresh token khi logout

Một ứng dụng có thể giữ refresh token để xin access token mới sau khi access token hết hạn. Nếu người dùng logout, refresh token của client/session đó thường cần được thu hồi hoặc vô hiệu hóa theo policy. Nếu không, client có thể tiếp tục xin token mới dù giao diện đã báo đăng xuất.

### 4.1. Refresh token rotation và token family

Với rotation, authorization server cấp refresh token mới sau mỗi lần sử dụng và đánh dấu token cũ đã tiêu thụ. Các token có thể thuộc một family/session. Khi local logout:
- Thu hồi refresh token hiện tại hoặc token family gắn với session/client theo semantics của hệ thống.
- Đánh dấu grant/session không còn active nếu policy yêu cầu.
- Xóa refresh token khỏi storage của client.
- Không thu hồi token của client khác hoặc session khác nếu phạm vi logout không yêu cầu.
- Xử lý retry và race giữa refresh đang chạy với logout.

Nếu refresh request và logout xảy ra gần như đồng thời, server cần quy tắc thứ tự rõ ràng. Một refresh bắt đầu trước logout có thể nhận response sau logout; client phải kiểm tra generation/session state trước khi lưu token mới. Server cũng nên bảo đảm refresh token đã bị revoke không thể tạo nhánh mới.

### 4.2. OAuth token revocation

OAuth Token Revocation (RFC 7009) định nghĩa endpoint để client yêu cầu authorization server thu hồi token. Endpoint và semantics cụ thể phụ thuộc nhà cung cấp và loại token. Authorization server có thể thu hồi token được gửi và token liên quan theo chính sách; client cần hiểu hành vi được hỗ trợ.

Một phản hồi revocation thành công không có nghĩa mọi resource server lập tức ngừng chấp nhận mọi access token đã phát hành. Điều đó phụ thuộc loại token, cách resource server xác minh và cơ chế trạng thái/revocation được triển khai.

### 4.3. Access token đã phát hành có thể còn hiệu lực

Đây là điểm cần phân biệt rõ:

- **Opaque access token** có thể được kiểm tra qua introspection; trạng thái inactive có thể được áp dụng theo cache policy.
- **JWT access token** được resource server xác minh offline có thể tiếp tục được chấp nhận tới exp nếu API không kiểm tra denylist, token version, session state hoặc một cơ chế revocation khác.
- **Sender-constrained token** giảm khả năng dùng token bị đánh cắp ở nơi khác, nhưng không thay thế logout/revocation.
- **Short-lived access token** giới hạn cửa sổ tồn tại của quyền cũ, nhưng không tạo hiệu lực thu hồi tức thì.

Nếu yêu cầu logout phải chặn quyền truy cập gần như ngay lập tức, thiết kế token/resource server phải có cơ chế kiểm tra trạng thái phù hợp. Không tuyên bố “logout đã thu hồi mọi token ngay” nếu chỉ xóa cookie và refresh token.

## 5. Xóa authentication cookie đúng cách

Server thường thiết lập session cookie bằng Set-Cookie. Khi logout, server gửi lại cookie cùng tên với giá trị rỗng hoặc hết hạn, giữ đúng các thuộc tính xác định phạm vi cookie.

Ví dụ cookie ban đầu:

    HTTP/1.1 200 OK
    Set-Cookie: __Host-session=RANDOM_OPAQUE_VALUE; Path=/; Secure; HttpOnly; SameSite=Lax

Response logout:

    HTTP/1.1 204 No Content
    Set-Cookie: __Host-session=; Path=/; Secure; HttpOnly; SameSite=Lax; Max-Age=0
    Cache-Control: no-store

### 5.1. Phạm vi cookie khi xóa phải khớp

Browser xác định cookie theo tên và các thuộc tính phạm vi như Domain/Path. Nếu cookie ban đầu được thiết lập với Domain hoặc Path cụ thể, response xóa phải khớp phạm vi đó. Gửi một cookie rỗng ở Path khác có thể tạo một cookie khác thay vì xóa cookie cũ.

Với cookie prefix __Host-, cookie cần có Secure, Path=/ và không có Domain. Khi xóa, giữ các điều kiện tương ứng. Không dùng JavaScript để cố xóa cookie HttpOnly; browser chỉ cho server điều khiển cookie đó qua response header.

### 5.2. Cookie expiry và server expiry là hai việc khác nhau

- Max-Age=0 hoặc Expires trong quá khứ yêu cầu browser xóa cookie.
- Server-side session revoke làm session credential không còn được chấp nhận.
- Hai thao tác cần được phối hợp nhưng không thay thế nhau.

Nếu browser không nhận được response xóa cookie do mất mạng, server-side session vẫn phải bị thu hồi nếu request logout đã được xử lý. Nếu server không xử lý được request, client có thể xóa state local để tránh sử dụng nhầm, nhưng cần phân biệt kết quả “đã thu hồi server-side” với “đã xóa dữ liệu cục bộ”.

## 6. Xóa trạng thái xác thực ở client

Một ứng dụng có thể lưu trạng thái xác thực ở cookie, memory, sessionStorage, IndexedDB, native secure storage hoặc service worker. Logout cần xóa đúng dữ liệu mà ứng dụng sở hữu.

### 6.1. Browser application

Các việc có thể cần thực hiện:
- Xóa access/refresh token nếu ứng dụng lưu chúng ở client.
- Xóa thông tin principal, role hoặc cached authorization state khỏi memory.
- Xóa dữ liệu tạm liên quan tới session khỏi sessionStorage/IndexedDB nếu có.
- Dừng polling, background refresh và tác vụ dùng session cũ.
- Chuyển UI về trạng thái anonymous.
- Đồng bộ các tab khác trong cùng ứng dụng.
- Điều hướng tới trang công khai hoặc trang đăng nhập an toàn.

Không lưu bearer token dài hạn trong localStorage nếu có kiến trúc an toàn hơn. Với BFF, browser thường chỉ giữ cookie HttpOnly; token OAuth được giữ phía server. JavaScript không thể đọc cookie HttpOnly và không cần cố làm vậy để logout.

### 6.2. Mobile và desktop application

Ứng dụng native cần xóa credential/token thuộc app khỏi secure storage của hệ điều hành theo phạm vi phiên:
- Keychain/Keystore hoặc secure storage tương đương.
- Token cache và refresh state.
- Cookie jar riêng của app nếu có.
- In-memory credential và background task.
- Local account selection/session state.

Không xóa toàn bộ dữ liệu người dùng hoặc credential của ứng dụng khác. Nếu có nhiều account trong một app, logout một account phải giữ các account còn lại theo UX và policy.

### 6.3. CLI và workload

CLI có thể lưu token trong OS credential store hoặc file cấu hình. Logout cần xóa/revoke credential của profile tương ứng và ngăn command tiếp tục dùng cache cũ. Với workload/service account, thao tác tương ứng thường là rotate/revoke credential hoặc disable identity theo quy trình vận hành; không nên gọi đó là user logout nếu không có interactive session.

### 6.4. Không nhầm browser cache với session

Xóa browser cache không bảo đảm session server bị thu hồi. Ngược lại, logout không nhất thiết cần xóa mọi ảnh, CSS hoặc nội dung công khai khỏi cache. Với dữ liệu nhạy cảm, dùng response caching policy như Cache-Control: no-store phù hợp và tránh cache response chứa thông tin cá nhân trên shared device.

Header Clear-Site-Data có thể xóa nhiều loại dữ liệu của origin trong browser hỗ trợ, nhưng phạm vi có thể rộng và ảnh hưởng cả dữ liệu ứng dụng khác cùng origin. Chỉ dùng khi đã hiểu tác động; nó không thay thế server-side session invalidation.

## 7. Bảo vệ endpoint logout trước CSRF

Cookie được browser tự động gửi theo quy tắc cookie. Attacker có thể khiến browser gửi request tới ứng dụng mà người dùng đang đăng nhập. Nếu logout endpoint nhận GET và không kiểm tra nguồn, attacker có thể gây logout không mong muốn (logout CSRF).

Logout CSRF thường không trực tiếp cấp quyền cho attacker, nhưng có thể gây gián đoạn, phá flow và hỗ trợ một số kịch bản account confusion. Endpoint logout vẫn cần thiết kế an toàn.

### 7.1. Dùng POST và CSRF protection

Với local logout thông thường:
- Dùng POST hoặc phương thức thay đổi trạng thái theo hợp đồng API.
- Xác minh CSRF token gắn với session khi kiến trúc dùng cookie.
- Kiểm tra Origin/Referer theo policy và trusted proxy.
- Đặt SameSite phù hợp cho session cookie.
- Không thay đổi trạng thái chỉ khi browser tải một link GET.
- Không dựa riêng vào CORS để chống CSRF.

Ví dụ form:

    <form method="post" action="/logout">
      <input type="hidden" name="csrf_token" value="SERVER_GENERATED_TOKEN">
      <button type="submit">Đăng xuất</button>
    </form>

Token CSRF cần gắn với session hoặc được bảo vệ theo pattern đã chọn. Không đưa token vào URL vì URL có thể xuất hiện trong log, history và Referer.

### 7.2. GET có thể xuất hiện ở giao thức federation

Một số giao thức hoặc endpoint RP-Initiated Logout sử dụng điều hướng browser bằng GET tới endpoint của OP. Điều đó không có nghĩa endpoint local logout của ứng dụng nên dùng GET để thu hồi session mà không có bảo vệ. Hãy phân biệt giao thức federation, CSRF/state validation và thao tác local session.

## 8. Logout trong OpenID Connect và SSO

OIDC có các cơ chế logout để RP và OP phối hợp chấm dứt phiên. Local logout của RP và logout tại OP là hai phạm vi khác nhau.

### 8.1. Local RP logout

Ứng dụng RP có thể:
1. Thu hồi session local.
2. Xóa cookie của RP.
3. Xóa token/cache local.
4. Điều hướng người dùng tới trang logged-out.

Nếu IdP vẫn giữ SSO session, lần sau người dùng truy cập RP có thể được xác thực lại mà không cần nhập mật khẩu, tùy prompt, max_age và policy. Đây không phải lỗi nếu sản phẩm chỉ hứa local logout.

### 8.2. RP-Initiated Logout

OIDC RP-Initiated Logout cho phép RP điều hướng browser tới logout endpoint của OP, thường được công bố trong discovery metadata. RP có thể gửi tham số như id_token_hint, post_logout_redirect_uri và state theo specification và cấu hình OP.

Các điểm cần lưu ý:
- RP cần kết thúc session local theo policy, không phụ thuộc hoàn toàn vào redirect thành công.
- post_logout_redirect_uri phải được đăng ký/kiểm tra chặt chẽ để tránh open redirect.
- state giúp tương quan kết quả quay lại với logout transaction.
- Không log ID Token hint hoặc token nhạy cảm.
- OP có thể không hỗ trợ mọi tính năng hoặc có hành vi riêng theo profile; cần tuân theo tài liệu triển khai đã thỏa thuận.

### 8.3. Front-channel và back-channel logout

- **Front-channel logout:** OP dùng browser/front channel để thông báo các RP liên quan. Browser privacy controls, iframe restrictions hoặc client không hoạt động có thể ảnh hưởng việc giao nhận.
- **Back-channel logout:** OP gửi Logout Token tới endpoint của RP qua back channel. RP xác minh token, issuer, audience, sự kiện logout và các định danh session/subject theo specification trước khi thu hồi session.

RP không được tin một logout message chỉ vì nó đến endpoint. Back-channel Logout Token cần được xác minh mật mã và kiểm tra claim theo OIDC Back-Channel Logout. Các session cần thu hồi phải được ánh xạ đúng; không xóa mọi session của account nếu message chỉ nhắm tới một session và protocol cung cấp session identifier.

### 8.4. Không thể giả định mọi ứng dụng đã logout

Global logout phụ thuộc vào khả năng hỗ trợ của IdP và RP, cấu hình federation, thời gian giao nhận và trạng thái các ứng dụng. Một RP offline hoặc không hỗ trợ logout có thể chưa nhận được thông báo. Với hệ thống cần thu hồi tức thời, cần thêm account/session revocation hoặc kiểm tra trạng thái ở resource server.

## 9. Xử lý nhiều tab và request đang chạy

Một người dùng có thể mở nhiều tab của cùng ứng dụng. Sau khi logout ở tab A, tab B không nên tiếp tục hiển thị trạng thái đăng nhập hoặc gửi request như thể session còn hoạt động.

### 9.1. Đồng bộ nhiều tab

Ứng dụng có thể dùng BroadcastChannel, storage event hoặc cơ chế đồng bộ UI để thông báo logout cho các tab cùng origin. Thông điệp chỉ nên chứa event đơn giản, không chứa session ID hoặc token.

Ví dụ pseudocode:

    // Tab đã logout
    const channel = new BroadcastChannel("app-auth-events");
    channel.postMessage({ type: "LOCAL_LOGOUT" });

    // Các tab khác
    channel.onmessage = (event) => {
      if (event.data?.type === "LOCAL_LOGOUT") {
        clearInMemoryAuthState();
        stopBackgroundRefresh();
        showSignedOutView();
      }
    };

Đây là đồng bộ giao diện và tác vụ client. Server-side session revoke vẫn là nguồn quyết định; tab khác dù bỏ lỡ message cũng phải nhận 401/unauthorized khi gửi request bằng session đã bị thu hồi.

### 9.2. Request đang chạy tại thời điểm logout

Logout không nhất thiết hủy được một request đã vượt qua authorization và bắt đầu thực thi. Cần định nghĩa semantics:
- Request bắt đầu sau khi revoke phải bị từ chối.
- Request đã được authorize trước thời điểm revoke có thể hoàn tất tùy transaction boundary.
- Với thao tác nhạy cảm, có thể kiểm tra session/account state lại ngay trước commit.
- Job nền được tạo trước logout cần có policy riêng về việc tiếp tục hay hủy.
- Không để refresh response đến muộn ghi đè trạng thái logged-out ở client.

Nếu cần bảo đảm chặt, gắn request/job với session version hoặc authorization decision ID và kiểm tra lại trước side effect quan trọng.

### 9.3. Race giữa refresh và logout

Một tình huống phổ biến:
1. Tab A gửi refresh request.
2. Tab B thực hiện logout và thu hồi refresh token/session.
3. Refresh response từ bước 1 đến sau logout.
4. Client vô tình lưu access/refresh token mới và khôi phục trạng thái đăng nhập.

Cách xử lý:
- Dùng một auth-state generation/version ở client; logout tăng generation.
- Refresh request ghi nhận generation khi bắt đầu; response chỉ được lưu nếu generation vẫn khớp.
- Server serialize refresh/revoke theo token family/session và bảo đảm token đã revoked không thể tạo nhánh mới sau đó.
- Dừng refresh timer và abort request có thể hủy.
- Kiểm tra trạng thái session trước khi chấp nhận response refresh.

## 10. Logout thất bại và khả năng phục hồi

Không phải mọi request logout đều thành công. Mạng có thể mất, session store có thể lỗi hoặc authorization server không phản hồi. Giao diện cần nói đúng điều đã xảy ra.

### 10.1. Server đã thu hồi nhưng browser không nhận response

Nếu server đã ghi revoke thành công nhưng response bị mất, cookie có thể còn trong browser. Request sau vẫn gửi cookie cũ nhưng server phải từ chối. Khi người dùng tải lại, ứng dụng có thể nhận 401 và xóa cookie còn sót.

Đây là lý do server-side invalidation phải độc lập với việc browser có nhận được Set-Cookie hay không.

### 10.2. Client xóa state nhưng server không xác nhận

Nếu server không xử lý được request logout, client có thể xóa token khỏi bộ nhớ local và chuyển UI sang trạng thái logged-out để tránh tiếp tục sử dụng. Tuy nhiên, nếu session ID đã bị sao chép, nó có thể vẫn hoạt động ở nơi khác.

Ứng dụng nên:
- Hiển thị rõ khi chưa xác nhận được việc thu hồi server-side.
- Cho phép thử lại khi kết nối phục hồi.
- Có thể gửi yêu cầu revoke qua một kênh retry an toàn/idempotent.
- Không tuyên bố mọi session đã bị chấm dứt khi chỉ mới xóa state local.
- Với rủi ro cao, cung cấp đường liên hệ hoặc chức năng quản lý session khác đã được xác thực.

### 10.3. Logout cần idempotent

Người dùng có thể bấm Logout nhiều lần, browser retry request hoặc proxy gửi lại sau timeout. Gọi logout lặp trên session đã revoked nên cho kết quả an toàn và nhất quán; không tạo session mới hoặc làm thay đổi account khác.

Server có thể trả cùng một trạng thái thành công khi session đã bị thu hồi, miễn là không tiết lộ thông tin nhạy cảm. Việc revoke refresh token cũng cần xử lý token đã inactive theo semantics của authorization server.

## 11. Bảo vệ dữ liệu sau logout

Sau logout, ứng dụng cần tránh để dữ liệu riêng tư của phiên cũ tiếp tục hiển thị hoặc được truy cập từ shared device.

- Không cache response nhạy cảm ở browser/proxy nếu không cần; dùng Cache-Control: no-store phù hợp.
- Xóa thông tin principal và dữ liệu account khỏi UI state.
- Chặn truy cập lại các trang protected qua back/forward cache theo thiết kế và kiểm tra authorization khi trang/request được khôi phục.
- Không coi việc ẩn nút hoặc chuyển về trang login là kiểm soát bảo mật.
- Kiểm tra API ở server cho mọi request, kể cả request phát sinh từ tab cũ.
- Với ứng dụng native, xóa dữ liệu session nhạy cảm khỏi vùng lưu trữ phù hợp.
- Không xóa dữ liệu người dùng cần giữ như tài liệu offline nếu policy sản phẩm cho phép và dữ liệu đã được bảo vệ; phân biệt dữ liệu công khai với dữ liệu riêng tư.

Trang được khôi phục từ browser back-forward cache có thể hiển thị nội dung đã render trước logout. Ứng dụng cần xử lý sự kiện page restore và xác minh session trước khi tiếp tục thao tác; server vẫn phải bảo vệ API và response mới.

## 12. Audit và thông báo logout

Logout là sự kiện bảo mật hữu ích, nhất là khi liên quan tới thiết bị bị mất, account takeover hoặc thu hồi phiên hàng loạt.

Audit event có thể ghi:
- Event ID và timestamp.
- Subject/account và tenant ID.
- Application/client ID.
- Session reference đã được hash hoặc ID nội bộ không phải secret.
- Phạm vi logout: current session, all app sessions hoặc federation logout.
- Kết quả server-side revoke và refresh-token handling.
- Nguồn khởi tạo: user action, admin action hoặc incident response.
- Correlation/request ID và policy version nếu có.

Không ghi session cookie, raw session ID, access token, refresh token, ID Token hoặc CSRF token vào log.

Notification có thể phù hợp khi có logout từ thiết bị lạ, logout all devices hoặc admin revoke. Logout thông thường ở cùng thiết bị không nhất thiết cần email; tránh tạo thông báo quá mức khiến người dùng bỏ qua cảnh báo thực sự.

## 13. API và pseudocode local logout

Một API minh họa:

    POST /logout
    Cookie: __Host-session=RANDOM_OPAQUE_VALUE
    X-CSRF-Token: SERVER_GENERATED_TOKEN
    Content-Type: application/json

    {}

Response:

    HTTP/1.1 204 No Content
    Set-Cookie: __Host-session=; Path=/; Secure; HttpOnly; SameSite=Lax; Max-Age=0
    Cache-Control: no-store

Pseudocode server-side:

    localLogout(request):
        require request.method == "POST"
        session = resolveSessionFromCookie(request)
        require validCsrf(request, session)

        if session is absent:
            clearSessionCookieInResponse()
            return noContent()

        with atomicTransaction:
            current = loadSessionForUpdate(session.id)

            if current.status == "active":
                markSessionRevoked(current.id, nowUtc())
                revokeRefreshCredentialBoundTo(current.id)
                stopOrInvalidateSessionBoundJobs(current.id)
                writeAuditEvent(
                    type = "local_logout",
                    subject = current.subjectId,
                    client = current.clientId,
                    sessionRef = safeReference(current.id)
                )

        clearSessionCookieInResponse()
        return noContent()

Pseudocode chỉ mô tả nguyên tắc. Thực tế cần xử lý trường hợp session store và authorization server nằm ở hai dịch vụ khác nhau. Không giữ transaction database mở trong khi chờ network call dài; có thể dùng outbox/event hoặc saga với trạng thái rõ để bảo đảm revoke và retry. Không để lỗi revoke refresh token làm session local đã thu hồi quay trở lại active.

### 13.1. Thứ tự thao tác và tính nhất quán

Một thiết kế thường ưu tiên:
1. Xác thực request logout và xác định session.
2. Ghi nhận local session revoked một cách bền vững.
3. Ngừng chấp nhận request mới bằng session đó.
4. Phát yêu cầu revoke refresh token/grant theo client/session.
5. Xóa cookie và client state.
6. Audit kết quả từng bước và retry các bước downstream chưa hoàn tất.

Nếu token revocation service tạm thời không khả dụng, local session vẫn phải bị vô hiệu hóa. Hệ thống cần ghi trạng thái pending/retry cho bước revoke downstream và bảo đảm refresh endpoint không cấp token mới cho session đã logout.

## 14. Threat model cho local logout

| Mối đe dọa | Cách xảy ra | Tác động | Kiểm soát |
| --- | --- | --- | --- |
| **Cookie-only logout** | Client chỉ xóa cookie mà server giữ session active. | Session ID bị sao chép vẫn dùng được. | Server-side revoke và cookie deletion. |
| **Refresh token survives logout** | Refresh token vẫn active sau khi UI báo logout. | Client/attacker có thể xin access token mới. | Revoke token/family và xóa local storage. |
| **Logout CSRF** | Trang bên ngoài ép browser gửi request logout. | Người dùng bị đăng xuất ngoài ý muốn. | POST, CSRF token, Origin check, SameSite. |
| **Local/global confusion** | UI hứa logout toàn hệ thống nhưng chỉ thu hồi RP session. | Người dùng tưởng IdP và ứng dụng khác đã logout. | Hiển thị phạm vi chính xác, dùng federation logout khi hỗ trợ. |
| **Refresh/logout race** | Refresh response đến sau logout và ghi lại token. | Client vô tình đăng nhập lại. | Generation/version, server-side serialization và revoke. |
| **Stale session cache** | Node khác tiếp tục coi session active sau revoke. | Request sau logout vẫn được chấp nhận. | Cache invalidation, TTL và state check. |
| **Back-button data exposure** | Browser khôi phục trang đã render trước logout. | Người dùng sau nhìn thấy dữ liệu cũ trên shared device. | No-store phù hợp, page restore handling, API authorization. |
| **Open redirect after logout** | Redirect URL do client kiểm soát. | Điều hướng tới trang phishing hoặc lộ thông tin. | Allowlist post-logout redirect URI và state validation. |
| **Partial logout failure** | Server revoke thất bại nhưng client báo thành công hoàn toàn. | Session bị sao chép vẫn có thể hoạt động. | Trạng thái kết quả rõ, retry và audit. |
| **Overbroad revocation** | Logout một app thu hồi token/session của client khác. | Gián đoạn SSO hoặc dịch vụ không liên quan. | Ràng buộc revoke theo client, session và phạm vi được yêu cầu. |

## 15. Tình huống thực hành: người dùng logout nhưng vẫn tự động đăng nhập lại

**Bối cảnh:** Học viên An đăng nhập vào nền tảng qua IdP công ty. Ứng dụng tạo session cookie riêng. An chọn Logout, ứng dụng xóa cookie local và chuyển về trang login. Khi An bấm Login lần nữa, browser được chuyển tới IdP và lập tức quay lại ứng dụng mà không hỏi mật khẩu.

**Phân tích:**

1. Local session của ứng dụng có thể đã được thu hồi đúng.
2. Cookie SSO tại IdP vẫn còn hiệu lực.
3. Khi RP bắt đầu OIDC/SAML login mới, IdP nhận ra browser vẫn có session và có thể trả kết quả xác thực theo policy.
4. Người dùng nhìn thấy đăng nhập lại ngay nên có thể nghĩ logout không hoạt động.
5. Đây là khác biệt giữa local logout và IdP/global logout, không nhất thiết là lỗi session invalidation.

**Thiết kế UX và kỹ thuật:**

- Ghi rõ “Bạn đã đăng xuất khỏi ứng dụng này” nếu chỉ local logout.
- Nếu cần đăng xuất cả IdP, điều hướng qua RP-Initiated Logout hoặc cơ chế federation đã hỗ trợ.
- Không hứa tất cả RP đã logout nếu IdP không có cơ chế phối hợp hoặc một RP không nhận được thông báo.
- Khi cần yêu cầu xác thực mới cho lần đăng nhập kế tiếp, dùng tham số/policy phù hợp như prompt=login hoặc max_age theo OIDC và thỏa thuận với OP; không dùng chúng thay cho session revoke.
- Kiểm thử trên browser có nhiều RP, nhiều tab và chính sách cookie khác nhau.

**Bài tập:** Nếu người dùng muốn giữ đăng nhập ở IdP nhưng rời khỏi ứng dụng học tập trên máy dùng chung, nên chọn gì? Local logout có thể phù hợp nếu session của RP bị thu hồi và dữ liệu nhạy cảm không còn hiển thị. Nếu cần bảo đảm người dùng khác không thể tiếp tục SSO vào các ứng dụng khác trên cùng browser, cần logout IdP hoặc xóa browser profile theo chính sách thiết bị; local logout riêng không giải quyết phạm vi đó.

## 16. Checklist triển khai local logout

- [ ] Xác định rõ phạm vi: ứng dụng hiện tại, browser, thiết bị, mọi session của app hay IdP/global logout.
- [ ] Dùng endpoint thay đổi trạng thái được bảo vệ CSRF; không logout bằng GET thông thường.
- [ ] Xác định session từ credential server tin cậy và thu hồi server-side.
- [ ] Bảo đảm session ID cũ bị từ chối trên mọi node, cache và API.
- [ ] Tạo session ID mới khi người dùng đăng nhập lại; không tái kích hoạt session cũ.
- [ ] Thu hồi refresh token/token family/grant đúng client và đúng phạm vi theo policy.
- [ ] Hiểu giới hạn của access token đã phát hành, đặc biệt JWT được xác minh offline.
- [ ] Xóa cookie bằng cùng tên và phạm vi Domain/Path; giữ thuộc tính prefix phù hợp.
- [ ] Xóa token/state trong memory và storage do ứng dụng quản lý; dừng background refresh.
- [ ] Đồng bộ logout giữa các tab nhưng không gửi secret qua broadcast.
- [ ] Xử lý race giữa refresh và logout, callback đến muộn và request đang chạy.
- [ ] Có TTL/cache invalidation phù hợp cho session revocation phân tán.
- [ ] Định nghĩa hành vi khi session store hoặc token revocation service không khả dụng.
- [ ] Làm logout idempotent để retry an toàn.
- [ ] Không tuyên bố global logout khi mới thu hồi local session.
- [ ] Kiểm tra post-logout redirect, CSRF, back/forward cache và dữ liệu trên shared device.
- [ ] Ghi audit phạm vi và kết quả nhưng không log cookie/token/CSRF secret.
- [ ] Kiểm thử logout current session, all sessions, SSO re-login, multi-tab, multi-node và partial failure.

## 17. Câu hỏi tự kiểm tra

**1. Local logout là gì?**  
Là chấm dứt session do ứng dụng hiện tại quản lý, vô hiệu hóa credential của session đó và xóa trạng thái xác thực cục bộ theo phạm vi ứng dụng.

**2. Xóa cookie có đủ để logout an toàn không?**  
Không. Session ID đã sao chép có thể tiếp tục được dùng nếu server chưa thu hồi session record.

**3. Local logout có đăng xuất khỏi IdP không?**  
Không mặc nhiên. Cookie/session SSO tại IdP có thể vẫn còn và người dùng có thể được đăng nhập lại tự động.

**4. Refresh token có cần xử lý khi logout không?**  
Có, nếu ứng dụng dùng refresh token thuộc session/client đó. Cần revoke hoặc vô hiệu hóa theo policy và xóa khỏi client storage.

**5. Access token JWT đã phát hành có luôn mất hiệu lực ngay khi logout không?**  
Không. Resource server xác minh JWT offline có thể tiếp tục chấp nhận tới expiry nếu không có denylist, introspection, version/session check hoặc cơ chế tương đương.

**6. Vì sao local logout endpoint cần CSRF protection?**  
Vì browser tự động gửi cookie và trang ngoài có thể cố ép browser gửi request logout, gây gián đoạn hoặc account confusion.

**7. Xóa cookie cần khớp những thuộc tính nào?**  
Cần cùng tên và phạm vi cookie, đặc biệt Domain/Path. Với prefix __Host-, phải giữ yêu cầu Secure, Path=/ và không Domain.

**8. Nhiều tab nên nhận biết logout thế nào?**  
Có thể broadcast một sự kiện không chứa secret để cập nhật UI; server-side revoke vẫn là nguồn quyết định và mọi request sau đó phải bị từ chối.

**9. Nếu refresh response đến sau logout thì sao?**  
Client phải kiểm tra auth-state generation/session state trước khi lưu token; server cần serialize refresh và revoke để token bị thu hồi không tạo được phiên mới.

**10. Khi nào cần global logout?**  
Khi yêu cầu kết thúc cả phiên IdP hoặc các RP liên quan. Cần dùng cơ chế federation như RP-Initiated, front-channel hoặc back-channel logout và hiểu giới hạn giao nhận.

**Ghi nhớ:** Local logout chỉ hoàn tất khi ứng dụng chấm dứt session phía server và xử lý các credential thuộc phiên đó, đồng thời xóa cookie và state ở client. Hãy bảo vệ endpoint logout, thu hồi refresh token theo phạm vi, hiểu access token có thể còn hiệu lực, xử lý nhiều tab/race/cache và nói rõ local logout khác global SSO logout.
