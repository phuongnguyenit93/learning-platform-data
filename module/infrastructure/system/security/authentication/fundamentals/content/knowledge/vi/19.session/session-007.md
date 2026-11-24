# Concurrent session — Quản lý nhiều phiên đăng nhập đồng thời

> **Chương:** Session  
> **Chủ đề:** Concurrent session

**Concurrent session** là tình huống một danh tính có nhiều phiên đăng nhập còn hiệu lực cùng lúc, chẳng hạn người dùng mở nền tảng học tập trên laptop, điện thoại và máy tính bảng. Đây là hành vi hợp lệ trong nhiều sản phẩm. Tuy nhiên, mỗi phiên là một đường truy cập độc lập tới tài nguyên; nếu một phiên bị đánh cắp, bị bỏ quên trên thiết bị dùng chung hoặc không được thu hồi sau khi credential thay đổi, kẻ tấn công có thể tiếp tục truy cập dù người dùng đã đăng nhập lại ở thiết bị khác.

Quản lý concurrent session là việc xác định **một tài khoản được có bao nhiêu phiên, phiên nào được tiếp tục, phiên nào bị thay thế hoặc thu hồi, và các quyết định đó có hiệu lực nhất quán ra sao khi nhiều request xảy ra đồng thời**. Chính sách có thể cho phép nhiều phiên, giới hạn theo số lượng, chỉ cho một phiên, hoặc áp dụng quy tắc riêng cho thiết bị và mức đặc quyền.

Bài học thuộc module **SECURITY_AUTHENTICATION_FUNDAMENTALS**, kết nối credential, MFA, passkey, token, liên kết danh tính và khôi phục tài khoản với vòng đời phiên. Người học cần phân biệt nhiều phiên hợp lệ với việc dùng lại session token, hiểu các race condition khi login/refresh/logout và thiết kế thu hồi phiên đáng tin cậy.

## 1. Kết quả học tập

Sau bài học, người học có thể:

1. Giải thích concurrent session và phân biệt nó với nhiều tab hoặc nhiều request đồng thời trong cùng một phiên.
2. Chọn chính sách cho phép nhiều phiên, giới hạn số phiên, một phiên duy nhất hoặc giới hạn theo thiết bị/client.
3. Mô hình hóa session registry và các trạng thái active, expired, revoked, replaced.
4. Thiết kế tạo phiên và áp dụng giới hạn một cách nguyên tử để tránh race condition khi nhiều login cùng lúc.
5. Quản lý access token, refresh token, cookie, logout và thu hồi phiên trên nhiều thiết bị.
6. Nhận diện session fixation, session hijacking, refresh-token reuse, stale session và các rủi ro từ thiết bị dùng chung.
7. Xây dựng giao diện xem/thu hồi phiên, audit event và test plan cho các tình huống đồng thời.

## 2. Session là gì và concurrent session có nghĩa gì?

Sau khi verifier xác nhận credential và policy xác thực đạt yêu cầu, hệ thống có thể tạo **authenticated session**. Session đại diện trạng thái truy cập đã được thiết lập cho một principal trong một khoảng thời gian và một phạm vi nhất định. Nó thường gắn với một session ID hoặc token mà client gửi trong các request tiếp theo.

Một người dùng có thể có:

- Một phiên trên trình duyệt laptop;
- Một phiên trên ứng dụng mobile;
- Một phiên trên trình duyệt của máy tính ở nhà;
- Một phiên trên thiết bị dùng chung ở phòng học;
- Một phiên quản trị riêng với mức bảo đảm cao hơn.

Đó là nhiều phiên đồng thời nếu server quản lý chúng như các session riêng biệt. Ngược lại, mở mười tab cùng một browser profile thường chỉ gửi cùng một cookie và cùng một session; không nên mặc định tính mỗi tab là một phiên độc lập.

### 2.1. Phân biệt các khái niệm

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Session** | Trạng thái xác thực/uy quyền truy cập được duy trì | Cookie phiên của trình duyệt |
| **Concurrent sessions** | Nhiều session còn hiệu lực cho cùng principal | Laptop và điện thoại cùng đăng nhập |
| **Concurrent requests** | Nhiều request chạy đồng thời trong một session | Hai tab cùng tải danh sách khóa học |
| **Multiple tabs** | Nhiều tab có thể dùng chung cookie/session | Tab điểm số và tab lịch học |
| **Session reuse** | Dùng lại cùng một session credential | Browser gửi cùng cookie trong nhiều request |
| **Session hijacking** | Kẻ tấn công lấy và sử dụng session credential của người khác | Cookie bị đánh cắp |
| **Refresh-token family** | Nhóm refresh token kế tiếp nhau trong một chuỗi rotation | Token cũ được thay bằng token mới |

Chính sách concurrent session phải xác định đơn vị đếm: theo user, theo tenant, theo application/client, theo thiết bị hay theo loại phiên. Nếu không định nghĩa rõ, giới hạn có thể chặn nhầm người dùng hoặc không chặn được phiên rủi ro.

## 3. Vì sao cần quản lý nhiều phiên?

Nhiều phiên đem lại trải nghiệm linh hoạt, nhưng cũng làm tăng số credential đang có khả năng truy cập tài khoản.

### 3.1. Lợi ích

- Người dùng tiếp tục công việc trên nhiều thiết bị;
- Mobile app có thể duy trì phiên trong khi browser dùng phiên riêng;
- Người dùng không phải đăng nhập lại liên tục khi chuyển thiết bị;
- Tổ chức có thể tách phiên thường và phiên quản trị;
- Hỗ trợ vận hành, thiết bị kiosk và các ứng dụng tích hợp theo chính sách.

### 3.2. Rủi ro

- Một session bị đánh cắp có thể tồn tại sau khi người dùng đổi password;
- Máy tính công cộng hoặc thiết bị cũ vẫn giữ cookie đăng nhập;
- Kẻ tấn công tạo một phiên mới rồi giữ quyền song song với người dùng thật;
- Giới hạn số phiên không được áp dụng nguyên tử, dẫn đến vượt ngưỡng;
- Logout chỉ xóa cookie phía client nhưng server vẫn chấp nhận session;
- Refresh token được dùng đồng thời gây lỗi rotation hoặc false positive reuse;
- Session cũ tiếp tục mang role/tenant membership đã bị thu hồi;
- Người dùng không biết có thiết bị lạ đang đăng nhập.

Quản lý concurrent session cần cân bằng **an toàn, khả dụng và trải nghiệm**. Ép chỉ một phiên có thể phù hợp tài khoản đặc quyền hoặc thiết bị kiosk, nhưng có thể gây khó chịu và tạo cơ hội DoS nếu kẻ tấn công liên tục đăng nhập để đá người dùng thật ra.

## 4. Mô hình vòng đời của một session

Một session nên có định danh riêng, principal, thời điểm, thời hạn, trạng thái và ngữ cảnh xác thực đủ để áp dụng policy.

~~~mermaid
stateDiagram-v2
    [*] --> Created: Authentication đạt policy
    Created --> Active: Phát hành session credential
    Active --> Active: Request hợp lệ / cập nhật last_seen
    Active --> Reauthenticated: Step-up hoặc xác thực lại
    Reauthenticated --> Active: Cập nhật assurance/auth_time
    Active --> Replaced: Bị phiên mới thay thế theo policy
    Active --> Revoked: Logout / admin revoke / compromise
    Active --> Expired: Idle timeout hoặc absolute expiry
    Replaced --> [*]
    Revoked --> [*]
    Expired --> [*]
~~~

Các trạng thái là mô hình khái niệm. Một hệ thống có thể lưu trạng thái bằng revoked_at, expires_at, replaced_by hoặc credential version thay vì cột enum. Điều quan trọng là server có thể quyết định session còn hợp lệ tại thời điểm request.

### 4.1. Thuộc tính nên quản lý

| Thuộc tính | Mục đích |
| --- | --- |
| **session_id** | Định danh ngẫu nhiên, khó đoán của phiên |
| **subject_id** | User/service principal mà phiên đại diện |
| **tenant_id / client_id** | Phạm vi tổ chức và ứng dụng |
| **created_at** | Thời điểm tạo |
| **last_seen_at** | Hoạt động gần nhất |
| **idle_expires_at** | Hạn khi không hoạt động |
| **absolute_expires_at** | Hạn tối đa kể từ lúc tạo |
| **auth_time** | Thời điểm xác thực gần nhất |
| **auth_method / assurance** | Phương thức và mức bảo đảm đã đạt |
| **device_label / client_context** | Nhãn và tín hiệu thiết bị đã được làm sạch |
| **status / revoked_at** | Trạng thái thu hồi/hết hiệu lực |
| **refresh_family_id** | Liên kết với chuỗi refresh token nếu có |
| **credential_version** | Phiên bản trạng thái credential/account dùng để vô hiệu hóa hàng loạt |

Không cần lưu mọi trường trong một bảng. Cần lưu tối thiểu đủ để kiểm tra, audit và thực thi chính sách. Device label, IP, user-agent và vị trí là **tín hiệu bối cảnh**, không phải bằng chứng danh tính tuyệt đối.

## 5. Chính sách concurrent session

Không có một chính sách tối ưu cho mọi ứng dụng. Hãy chọn theo giá trị tài khoản, thiết bị, yêu cầu nghiệp vụ và khả năng thu hồi.

| Chính sách | Hành vi | Trường hợp phù hợp | Rủi ro/đánh đổi |
| --- | --- | --- | --- |
| **Unrestricted** | Cho phép nhiều phiên trong giới hạn vận hành | Ứng dụng người dùng phổ thông | Cần quản lý thiết bị và thu hồi tốt |
| **Maximum N sessions** | Giới hạn số phiên active cho mỗi principal | Dịch vụ cần kiểm soát số thiết bị | Cần định nghĩa phiên nào bị loại khi vượt ngưỡng |
| **Single session** | Chỉ giữ một phiên; phiên mới thay phiên cũ | Kiosk hoặc tài khoản đặc biệt | Dễ bị lạm dụng để đá người dùng ra |
| **Per-device** | Một hoặc số phiên nhất định cho mỗi thiết bị đã đăng ký | Ứng dụng doanh nghiệp | Device identity có thể thay đổi hoặc bị giả mạo |
| **Per-client/application** | Giới hạn riêng theo web, mobile, API client | Sản phẩm có nhiều client | Một principal có thể có nhiều phiên ở nhiều client |
| **Risk-based** | Tăng mức kiểm soát khi đăng nhập rủi ro | Tài khoản nhạy cảm | Cần tín hiệu tốt và xử lý false positive |
| **Privileged session** | Phiên admin riêng, TTL ngắn, step-up | Quản trị và thao tác nhạy cảm | Tăng chi phí UX và vận hành |

### 5.1. Xác định đơn vị đếm

Ví dụ một người có hai phiên browser trên hai thiết bị và một phiên mobile. Nếu policy giới hạn tối đa bốn **active sessions**, cần quyết định có loại phiên nào. Nếu giới hạn bốn **devices**, nhiều phiên trên cùng thiết bị có thể được tính một. Nếu giới hạn theo **client_id**, phiên browser và mobile có quota riêng.

Đừng dùng IP làm định danh thiết bị: nhiều người có thể chung NAT, IP di động thay đổi và VPN làm vị trí khác đi. Fingerprint trình duyệt cũng có thể thay đổi hoặc bị giả mạo; chỉ nên dùng như tín hiệu hỗ trợ policy.

### 5.2. Chọn phiên bị thay thế

Khi vượt ngưỡng, có thể:

- Thu hồi phiên cũ nhất theo created_at;
- Thu hồi phiên ít hoạt động nhất theo last_seen_at;
- Từ chối login mới và yêu cầu người dùng tự kết thúc phiên cũ;
- Yêu cầu step-up trước khi thay thế;
- Cho người dùng chọn phiên cần đăng xuất.

Không tự động đá một phiên đang thực hiện giao dịch quan trọng mà không có chính sách an toàn. Với thao tác tài chính hoặc thay đổi dữ liệu, cần xác định điểm commit và cách xử lý request đang chạy.

## 6. Tạo phiên và thực thi giới hạn một cách nguyên tử

Một lỗi phổ biến là server đếm số phiên hiện tại, thấy còn quota, rồi tạo session. Nếu hai login xảy ra đồng thời, cả hai có thể cùng đọc một con số trước khi ghi và cùng tạo phiên, làm vượt giới hạn.

~~~mermaid
sequenceDiagram
    participant A as Login request A
    participant B as Login request B
    participant D as Session database
    A->>D: Đếm active sessions = 2 (limit 3)
    B->>D: Đếm active sessions = 2 (limit 3)
    A->>D: Insert session A
    B->>D: Insert session B
    Note over A,B: Có thể thành 4 phiên nếu không có đồng bộ
~~~

### 6.1. Transaction hoặc khóa theo principal

Việc **kiểm tra quota, chọn phiên bị thu hồi và tạo phiên mới** cần nằm trong một giao dịch nhất quán hoặc cơ chế serialization theo subject. Ví dụ:

~~~text
create_session_after_authentication(principal, context):
    begin transaction

    lock session quota for principal
    active = load_active_sessions(principal)

    if policy is SINGLE_SESSION:
        revoke_sessions(active)
    else if active.count >= policy.maximum:
        selected = choose_sessions_to_replace(active, policy)
        revoke_sessions(selected)

    new_session = generate_high_entropy_session_id()
    insert_session(
        principal = principal,
        context = context,
        status = ACTIVE,
        created_at = now
    )

    commit transaction
    return new_session
~~~

Pseudocode mô tả ý tưởng. Cách triển khai có thể dùng row lock, advisory lock, serializable transaction, atomic counter hoặc một dịch vụ session chuyên dụng. Cần xử lý retry khi transaction conflict và không tạo hai session do request retry sau timeout.

### 6.2. Idempotency và request retry

Nếu client gửi login request, server tạo session nhưng response bị mất, client có thể gửi lại. Hệ thống cần ngữ nghĩa rõ: retry có tạo session mới, trả lại kết quả cũ hay yêu cầu xác thực lại? Không giữ một session ID có thể tái sử dụng qua nhiều giao dịch không liên quan. Có thể gắn login transaction ID và trạng thái tiêu thụ để xử lý retry có kiểm soát.

### 6.3. Nhiều instance và eventual consistency

Nếu mỗi API instance giữ danh sách phiên trong cache riêng, một phiên bị thu hồi ở instance A có thể vẫn được chấp nhận ở instance B. Với yêu cầu thu hồi nhanh, session state cần nguồn dữ liệu chung hoặc cơ chế invalidation có độ trễ được xác định.

Không nên tuyên bố logout toàn bộ thiết bị có hiệu lực tức thời nếu hệ thống chỉ cập nhật cache eventual-consistent và chưa có SLA về thời gian lan truyền. Hãy đo và kiểm thử thời gian thu hồi thực tế.

## 7. Session ID và cookie an toàn

Session ID là bearer credential: ai có giá trị hợp lệ có thể được xem là đang sở hữu phiên theo mô hình server. Vì vậy, session ID phải khó đoán và được bảo vệ như bí mật.

### 7.1. Sinh và lưu session ID

- Dùng CSPRNG, entropy cao (ví dụ ít nhất 128 bit ngẫu nhiên theo thiết kế phù hợp);
- Không nhúng user ID, email, timestamp hoặc role vào session ID;
- Không tự tạo ID tuần tự hoặc hash từ thông tin công khai;
- Chỉ truyền qua HTTPS;
- Với session store phía server, cân nhắc lưu hash/HMAC của session token để giảm tác động nếu database bị đọc;
- Không ghi session ID nguyên dạng vào log, URL, analytics hoặc exception.

### 7.2. Cookie cho browser

Cookie phiên thường cần:

- **Secure:** chỉ gửi qua HTTPS;
- **HttpOnly:** JavaScript không đọc được cookie;
- **SameSite:** chọn Strict/Lax/None phù hợp luồng đăng nhập và tích hợp;
- **Path** và **Domain:** phạm vi hẹp;
- Thời hạn phù hợp với idle và absolute timeout.

HttpOnly làm giảm khả năng script đọc cookie nhưng không ngăn XSS thực hiện request thay mặt người dùng. Cần CSP, chống XSS, CSRF protection và kiểm soát origin phù hợp.

### 7.3. Session fixation

Khi đăng nhập thành công hoặc nâng quyền, server nên **rotate session ID**. Nếu session ID trước xác thực được giữ lại, kẻ tấn công có thể cố định một ID mà họ biết rồi chờ nạn nhân đăng nhập bằng ID đó.

Việc rotate cần vô hiệu hoặc đánh dấu session cũ theo chính sách; không để hai session ID cùng đại diện quyền cao sau khi đã nâng assurance. Các thay đổi nhạy cảm như xác thực lại, thay đổi password hoặc đổi principal cũng cần xem xét rotation.

## 8. Access token, refresh token và nhiều phiên

Một session ứng dụng có thể được biểu diễn bằng cookie opaque, server-side session record hoặc token. Không phải mọi token đều là session và mỗi loại có vòng đời khác nhau.

| Thành phần | Vai trò | Điểm cần lưu ý khi concurrent sessions |
| --- | --- | --- |
| **Session cookie opaque** | Trỏ tới session record phía server | Dễ quản lý danh sách và thu hồi nếu mọi request kiểm tra trạng thái |
| **Access token** | Cho phép gọi resource server trong audience/scope và thời hạn | JWT tự chứa có thể tiếp tục hợp lệ tới exp nếu không kiểm tra trạng thái |
| **Refresh token** | Cấp access token mới | Rotation có thể gặp race khi nhiều tab/thiết bị refresh đồng thời |
| **ID token** | Truyền thông tin xác thực người dùng cho OIDC client | Không dùng thay access token cho API |
| **Session registry** | Theo dõi phiên active/revoked | Là nguồn dữ liệu cho quota, logout và device management |

### 8.1. Refresh-token rotation

Trong refresh-token rotation, mỗi lần dùng refresh token hợp lệ, authorization server cấp token mới và vô hiệu token cũ. Nếu token cũ được dùng lại sau khi đã thay thế, đây có thể là dấu hiệu token bị sao chép.

Nhưng nhiều tab có thể cùng gửi refresh gần như đồng thời. Nếu request A đã dùng token cũ và request B tới ngay sau đó, server có thể coi B là reuse và thu hồi cả token family dù đó chỉ là race hợp lệ.

Biện pháp:

- Client điều phối **single-flight refresh** để chỉ một request refresh diễn ra cho cùng token family;
- Các tab chia sẻ trạng thái refresh qua cơ chế đồng bộ phù hợp;
- Server xử lý idempotency và transaction state rõ ràng;
- Nếu có grace window, giới hạn rất chặt theo token, thời gian và kết quả đã phát; không mở cửa sổ reuse rộng;
- Khi phát hiện reuse thực sự, thu hồi token family/session liên quan và yêu cầu xác thực lại.

Không cho phép hai refresh token cũ hoạt động lâu dài chỉ để tránh lỗi đồng thời. Cần test cả race hợp lệ lẫn reuse từ thiết bị khác.

### 8.2. JWT và thu hồi session

JWT có chữ ký hợp lệ vẫn có thể bị chấp nhận sau khi session đã bị logout nếu resource server chỉ kiểm tra chữ ký và exp. Muốn thu hồi nhanh, có thể:

- Dùng access token TTL ngắn;
- Kiểm tra session/credential version hoặc denylist ở API;
- Dùng token introspection với authorization server;
- Thu hồi refresh token để ngăn cấp token mới;
- Ràng buộc token với sender/credential khi phù hợp.

Mỗi lựa chọn có đánh đổi về latency, availability và consistency. Cần nói rõ “logout mọi thiết bị” có nghĩa là dừng cấp token mới hay chặn cả access token đã phát hành.

## 9. Logout và thu hồi nhiều phiên

Logout có nhiều phạm vi:

| Hành động | Phạm vi |
| --- | --- |
| **Logout current session** | Thu hồi phiên đang dùng |
| **Logout this device** | Thu hồi các session gắn với thiết bị theo mapping đáng tin cậy |
| **Logout all other sessions** | Giữ phiên hiện tại, thu hồi các phiên còn lại |
| **Logout all sessions** | Thu hồi toàn bộ session của subject |
| **Admin revoke** | Người có quyền thu hồi phiên của một subject theo policy |
| **Compromise response** | Thu hồi session/token và có thể credential liên quan |

Xóa cookie ở browser chỉ xóa bản sao phía client. Server cần đánh dấu session revoked hoặc vô hiệu hóa token family; nếu không, bản sao cookie bị đánh cắp vẫn có thể sử dụng.

### 9.1. Logout hiện tại

Server xác định session từ credential đã xác thực, đánh dấu revoked, thu hồi refresh token liên quan và xóa cookie bằng cùng thuộc tính Path/Domain. Request tiếp theo với cookie cũ phải bị từ chối.

### 9.2. Logout mọi thiết bị

Một endpoint có thể tăng **session/credential version** của principal hoặc đánh dấu toàn bộ session active là revoked. Nếu dùng version, mọi verifier phải kiểm tra version mới hoặc có cơ chế cache invalidation; nếu JWT tự chứa không kiểm tra version, token cũ có thể còn hiệu lực.

### 9.3. Đổi password và logout

Đổi password không tự động quyết định tất cả phiên phải bị thu hồi. Chính sách nên dựa vào bối cảnh:

- Đổi password bình thường sau xác thực lại mạnh: có thể giữ phiên hiện tại và thu hồi phiên khác;
- Nghi ngờ credential bị lộ: thu hồi tất cả phiên và refresh token, cân nhắc chặn access token còn hạn;
- Reset qua recovery: thường nên thu hồi phiên cũ theo policy vì người dùng không chứng minh được password hiện tại;
- Admin reset hoặc account suspension: áp dụng chính sách tổ chức và audit rõ.

## 10. Quản lý phiên trên nhiều thiết bị

Người dùng cần biết tài khoản đang được truy cập ở đâu và có thể kết thúc phiên lạ. Giao diện “Your sessions / Devices” nên hiển thị thông tin vừa đủ và tránh giả vờ rằng metadata thiết bị là chính xác tuyệt đối.

### 10.1. Thông tin hiển thị

- Nhãn thiết bị hoặc loại client;
- Trình duyệt/ứng dụng và hệ điều hành ở mức khái quát;
- Thời điểm đăng nhập và hoạt động gần nhất;
- Vị trí gần đúng nếu có cơ sở, kèm giải thích độ chính xác;
- Phương thức xác thực và mức bảo đảm nếu phù hợp;
- Phiên hiện tại được đánh dấu rõ;
- Trạng thái active, expired hoặc revoked.

Không hiển thị session ID, refresh token, access token hoặc thông tin kỹ thuật có thể giúp chiếm phiên. Không tuyên bố thiết bị chắc chắn là “iPhone của người dùng” chỉ từ user-agent; nhãn có thể bị giả mạo.

### 10.2. Thu hồi từ giao diện

Khi người dùng chọn “Sign out” cho một thiết bị, server phải xác minh họ có quyền quản lý session của subject đó, kiểm tra CSRF và thực hiện revoke phía server. Nếu chọn “Sign out all other devices”, cần giữ hoặc thu hồi session hiện tại theo đúng nội dung UI đã nêu.

Sau khi thu hồi, cập nhật giao diện và gửi thông báo khi phù hợp. Nếu session được lưu ở nhiều hệ thống, cần theo dõi thời gian lan truyền và xử lý lỗi một phần.

### 10.3. Thiết bị dùng chung

Máy thư viện, phòng máy, kiosk và thiết bị gia đình dùng chung cần idle timeout ngắn hơn, không tự động duy trì đăng nhập quá lâu, có logout rõ ràng và xóa dữ liệu cục bộ nhạy cảm khi đăng xuất. Trình duyệt có thể giữ password/autofill riêng; session management không thay thế chính sách thiết bị.

## 11. Session context và mức bảo đảm xác thực

Không phải mọi session đều có cùng mức bảo đảm. Một session được tạo bằng password đơn lẻ có thể khác session được tạo bằng passkey hoặc password + MFA.

Session context có thể ghi:

- auth_time: thời điểm người dùng xác thực;
- amr: phương thức xác thực đã dùng, nếu giao thức cung cấp;
- acr: mức assurance theo hợp đồng IdP/RP;
- auth_method: phương thức nội bộ;
- step_up_at: thời điểm hoàn tất xác thực bổ sung;
- purpose: login, admin action hoặc giao dịch cụ thể.

Với OIDC, RP phải hiểu ngữ nghĩa và nguồn của claim; không tự suy diễn acr/amr thành bảo đảm mạnh hơn hợp đồng IdP. Với phiên nội bộ, server tự ghi kết quả verifier đã kiểm tra.

### 11.1. Step-up trên một phiên đang hoạt động

Người dùng có thể duy trì phiên bình thường nhưng cần xác thực lại trước khi:

- Xem dữ liệu nhạy cảm;
- Xuất dữ liệu lớn;
- Thay password, email hoặc recovery channel;
- Thêm/xóa passkey, MFA authenticator hoặc linked IdP;
- Thực hiện thao tác quản trị hoặc thanh toán.

Step-up có thể nâng assurance của session hiện tại hoặc tạo một context đặc quyền riêng có TTL ngắn. Không nhất thiết phải mở một session độc lập cho mọi thao tác, nhưng phải gắn kết quả với đúng principal, purpose và thời điểm.

### 11.2. Không ràng buộc cứng theo IP

IP có thể đổi giữa các request do mobile network, VPN, proxy hoặc chuyển Wi-Fi. Nếu buộc session chỉ hoạt động từ một IP, người dùng hợp lệ có thể bị logout liên tục và kẻ tấn công cùng mạng vẫn có thể dùng session. IP nên là tín hiệu phát hiện bất thường; ràng buộc mạnh hơn cần dựa trên credential hoặc sender-constrained mechanism phù hợp.

## 12. Timeout: idle và absolute

Một session có thể hết hạn vì không hoạt động hoặc vì đã đạt giới hạn tuổi tối đa.

| Loại timeout | Ý nghĩa | Ví dụ áp dụng |
| --- | --- | --- |
| **Idle timeout** | Hết hạn sau khoảng không có hoạt động hợp lệ | Tài khoản dùng trên máy dùng chung |
| **Absolute timeout** | Hết hạn sau thời gian tối đa từ lúc tạo, dù vẫn hoạt động | Phiên quản trị hoặc dữ liệu nhạy cảm |
| **Reauthentication timeout** | Yêu cầu xác thực lại sau một khoảng kể từ lần xác thực gần nhất | Thao tác thay đổi credential |
| **Step-up validity** | Thời gian kết quả MFA/step-up còn dùng được | Hành động đặc quyền |

Sliding expiration có thể cập nhật idle expiry khi request hợp lệ, nhưng không nên kéo dài absolute expiry vô hạn. Cập nhật last_seen ở mọi request có thể tạo tải; có thể throttle theo khoảng thời gian nhưng phải chấp nhận độ trễ đã định.

Timeout nên dựa trên rủi ro, mức quyền, thiết bị và yêu cầu nghiệp vụ. Không có một giá trị duy nhất phù hợp mọi ứng dụng.

## 13. Account state và session consistency

Session có thể được tạo khi tài khoản active, nhưng sau đó tài khoản bị suspend, tenant membership bị thu hồi hoặc role thay đổi. Nếu API chỉ kiểm tra session token, người dùng có thể giữ quyền cũ.

Các thay đổi cần ảnh hưởng đến phiên:

- Tài khoản bị khóa, suspended hoặc deprovisioned;
- Người dùng rời tenant;
- Membership hoặc role bị thu hồi;
- Password hoặc authenticator bị reset do compromise;
- Linked identity bị gỡ;
- Chính sách bảo mật thay đổi.

Có thể sử dụng credential version, account version, session registry, token introspection hoặc policy check trực tuyến. Cần cân nhắc cache và consistency: nếu role thay đổi lúc 10:00 nhưng cache chỉ refresh sau 15 phút, quyền cũ có thể còn tồn tại trong khoảng đó.

### 13.1. Tách session state khỏi authorization state

Session hợp lệ cho biết principal đã xác thực và phiên còn được chấp nhận. Nó không có nghĩa mọi quyền trong session context vẫn đúng mãi. Authorization nên dựa trên policy và trạng thái tài nguyên hiện thời, đặc biệt cho thao tác nhạy cảm.

## 14. Rủi ro và biện pháp phòng vệ

| Rủi ro | Kịch bản | Kiểm soát |
| --- | --- | --- |
| **Session hijacking** | Cookie/token bị lấy cắp và dùng trên thiết bị khác | TLS, HttpOnly/Secure, XSS protection, TTL, revoke, sender constraint khi phù hợp |
| **Session fixation** | Kẻ tấn công biết session ID trước login | Rotate ID sau login và nâng quyền |
| **Stale session** | Password/role/account state thay đổi nhưng session cũ vẫn dùng | Session version, revoke, policy check |
| **Concurrent login race** | Nhiều login cùng vượt quota do count/insert không nguyên tử | Transaction/lock theo principal |
| **Refresh-token race** | Nhiều tab refresh đồng thời gây reuse giả | Single-flight, idempotency, rotation state |
| **Logout không hiệu lực** | Chỉ xóa cookie client, server vẫn nhận token | Server-side revocation và kiểm tra trạng thái |
| **Shared-device exposure** | Phiên còn mở trên máy dùng chung | Idle timeout, logout rõ, session listing |
| **Cross-tenant session** | Session từ tenant A dùng truy cập tài nguyên tenant B | Tenant binding và authorization mỗi request |
| **Session DoS** | Attacker đăng nhập liên tục để đá người dùng thật | Rate limit, reauth, policy không khóa cứng tùy tiện |
| **Token leakage** | Token xuất hiện trong URL/log/analytics | Không log secret, không đặt token URL, bảo vệ storage |

## 15. Ví dụ xuyên suốt: nền tảng học tập đa tenant

Một giảng viên sử dụng nền tảng trên laptop và điện thoại. Mỗi phiên được gắn với cùng internal user ID nhưng có client context riêng. Chính sách cho phép tối đa bốn phiên thông thường; phiên quản trị cần passkey và có absolute timeout ngắn hơn.

### 15.1. Session registry minh họa

~~~json
{
  "session_ref": "sess_ref_82a",
  "subject_id": "usr_417",
  "tenant_id": "school-a",
  "client_id": "learning-web",
  "created_at": "2026-11-22T08:00:00Z",
  "last_seen_at": "2026-11-22T08:35:00Z",
  "idle_expires_at": "2026-11-22T09:05:00Z",
  "absolute_expires_at": "2026-11-22T20:00:00Z",
  "auth_method": "password+mfa",
  "status": "active"
}
~~~

Đây là bản ghi minh họa; không lưu raw session cookie trong registry hoặc hiển thị session credential cho người dùng. Có thể lưu hash/lookup reference để server xác định phiên.

### 15.2. Hai login đồng thời khi đã gần chạm quota

Giảng viên đang có ba phiên và hai thiết bị mới cùng login. Nếu quota là bốn, hệ thống cần serialize quyết định. Một transaction tạo phiên trước sẽ chiếm slot; transaction sau phải đọc trạng thái mới và áp dụng policy (từ chối hoặc thay phiên cũ). Không để cả hai cùng thấy một slot trống.

### 15.3. Đổi password sau khi thấy thiết bị lạ

Giảng viên xác thực lại bằng password + MFA, đổi password và chọn “Sign out all other devices”. Server cập nhật verifier, thu hồi các session khác và refresh token liên quan, giữ phiên hiện tại với session ID mới nếu policy cho phép. Nếu access token là JWT tự chứa, resource server phải có cơ chế kiểm tra trạng thái hoặc chấp nhận khoảng thời gian còn hiệu lực đến exp; không tuyên bố thu hồi tức thời nếu chưa thực hiện được.

### 15.4. Thu hồi quyền giảng viên trong một tenant

Giảng viên vẫn có tài khoản và phiên hợp lệ ở trường B nhưng bị gỡ membership ở trường A. Session không nên bị hiểu là quyền toàn cục. API của trường A phải kiểm tra membership/tenant hiện thời và từ chối tài nguyên A; quyền ở trường B vẫn được đánh giá độc lập.

## 16. Triển khai API và dữ liệu session

### 16.1. Mô hình dữ liệu gợi ý

~~~sql
CREATE TABLE auth_sessions (
    session_ref          VARCHAR(80) PRIMARY KEY,
    subject_id           VARCHAR(80) NOT NULL,
    tenant_id            VARCHAR(80),
    client_id            VARCHAR(120),
    created_at           TIMESTAMP NOT NULL,
    last_seen_at         TIMESTAMP NOT NULL,
    idle_expires_at      TIMESTAMP NOT NULL,
    absolute_expires_at  TIMESTAMP NOT NULL,
    auth_time            TIMESTAMP NOT NULL,
    auth_method          VARCHAR(80),
    assurance_level      VARCHAR(80),
    status               VARCHAR(20) NOT NULL,
    revoked_at           TIMESTAMP,
    replaced_by          VARCHAR(80),
    refresh_family_id    VARCHAR(80),
    credential_version   BIGINT NOT NULL
);
~~~

Đây là schema khái niệm; kiểu dữ liệu, index, partition và chính sách retention phải phù hợp database thực tế. Không đưa raw cookie/access/refresh token vào bảng này. Có thể lưu hash token hoặc tham chiếu opaque riêng.

### 16.2. Kiểm tra session cho request

~~~text
authorize_request(session_cookie, request):
    token_hash = secure_lookup_hash(session_cookie)
    session = find_session(token_hash)

    if session is missing or session.status != ACTIVE:
        reject_unauthenticated()
    if now >= session.idle_expires_at:
        expire_session(session)
        reject_unauthenticated()
    if now >= session.absolute_expires_at:
        expire_session(session)
        reject_unauthenticated()
    if account_is_suspended(session.subject_id):
        revoke_session(session)
        reject_unauthenticated()

    principal = resolve_current_principal_and_membership(session)
    return evaluate_authorization(principal, request.action, request.resource)
~~~

Pseudocode chỉ mô tả ý tưởng. Trong hệ thống có JWT hoặc distributed cache, cần bổ sung kiểm tra issuer/audience/signature/expiry, version, revocation và consistency.

### 16.3. Thu hồi session theo principal

Một thao tác logout all có thể:

~~~text
revoke_all_sessions(subject_id):
    begin transaction
    mark_active_sessions_revoked(subject_id)
    revoke_refresh_token_families(subject_id)
    increment_session_version(subject_id)
    commit
    publish_session_invalidation(subject_id)
~~~

Nếu publish event thất bại sau commit, các instance có thể tiếp tục dùng cache cũ. Cần cơ chế retry/outbox hoặc kiểm tra version từ nguồn chung để bảo đảm thu hồi cuối cùng. Không chỉ dựa vào event không bền vững.

## 17. Kiểm thử concurrent session

Test trong môi trường thử nghiệm với account và session giả. Cần bao gồm cả hành vi đồng thời, không chỉ các request tuần tự.

| Nhóm | Tình huống | Kết quả mong đợi |
| --- | --- | --- |
| Multi-device | Đăng nhập trên browser và mobile | Mỗi phiên được ghi nhận riêng theo policy |
| Multi-tab | Mở nhiều tab cùng browser profile | Dùng cùng session cookie, không tạo session mới mỗi tab |
| Session cap | Tạo phiên vượt max N | Áp dụng đúng lựa chọn phiên thay thế/từ chối |
| Concurrent login | Nhiều login đồng thời khi gần chạm quota | Không vượt quota do race |
| Single-session | Hai login gần như cùng lúc | Chỉ phiên thắng theo policy còn active |
| Session fixation | Giữ session ID trước login | ID được rotate sau authentication |
| Logout current | Logout một phiên | Cookie/session hiện tại bị từ chối ở request sau |
| Logout all | Thu hồi mọi phiên trên nhiều API instance | Phiên/token cũ bị chặn trong SLA đã định |
| Password change | Đổi password sau xác thực lại | Session khác được xử lý đúng policy |
| Account suspension | Suspend user khi session còn active | Request tiếp theo bị từ chối theo policy |
| Tenant isolation | Session tenant A truy cập resource tenant B | Authorization DENY |
| Refresh race | Hai tab dùng refresh token gần đồng thời | Không tạo false reuse hoặc hai nhánh token ngoài policy |
| Refresh reuse | Token cũ bị dùng lại từ client khác | Phát hiện và thu hồi family theo policy |
| Idle timeout | Không hoạt động quá hạn | Session hết hiệu lực |
| Absolute timeout | Hoạt động liên tục nhưng quá tuổi tối đa | Yêu cầu đăng nhập lại |
| Shared device | Logout trên kiosk/máy dùng chung | Session server-side bị thu hồi, dữ liệu cục bộ được xử lý |
| Device revoke | Người dùng thu hồi phiên lạ từ trang bảo mật | Phiên đó không tiếp tục truy cập |
| Logging | Bật audit/trace | Không xuất raw session ID, cookie hoặc token |

### 17.1. Kiểm tra race condition

Chạy nhiều login cùng subject tại nhiều instance, đồng thời đo:

- Số session active sau khi mọi transaction hoàn tất;
- Có phiên nào bị revoke nhầm không;
- Có hai session cùng được coi là phiên duy nhất không;
- Thời gian và tính nhất quán của cache invalidation;
- Có session orphan nếu transaction lỗi giữa chừng không.

Với refresh-token rotation, mô phỏng hai tab và hai thiết bị; xác định request nào được phép retry, token family nào bị thu hồi và người dùng hợp lệ có phải đăng nhập lại hay không.

## 18. Lỗi triển khai thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Đếm session rồi insert ngoài transaction | Concurrent login vượt quota | Khóa/transaction theo principal |
| Chỉ xóa cookie phía client khi logout | Cookie bị sao chép vẫn hoạt động | Thu hồi phía server/token state |
| Giữ session ID sau login | Session fixation | Rotate ID sau xác thực và nâng quyền |
| Chỉ dùng JWT không có revocation strategy | Logout all không có hiệu lực ngay | TTL ngắn, version/introspection/denylist |
| Dùng IP làm định danh thiết bị | Khóa nhầm người dùng chung mạng hoặc IP thay đổi | Dùng device context như tín hiệu, không làm khóa duy nhất |
| Refresh song song không có điều phối | Reuse giả hoặc token family bị thu hồi | Single-flight và state machine |
| Coi mỗi tab là một session | Quota sai và UX kém | Đếm theo session credential/client policy |
| Không ràng buộc tenant | Session hợp lệ truy cập sai tenant | Tenant mapping và authorization theo resource |
| Không kiểm tra account status | User suspended vẫn dùng session cũ | Policy check/version/revocation |
| Lưu raw session token | DB/log leak dẫn tới chiếm phiên | Opaque random token, hash/reference và redaction |
| Không xử lý WebSocket/long-lived connection | Phiên đã revoke nhưng socket còn mở | Kiểm tra/re-auth/revoke connection theo policy |

## 19. Bài tập tình huống

Một nền tảng học tập cho phép tối đa hai phiên trên mỗi tài khoản. Backend thực hiện:

1. Đếm session active;
2. Nếu số lượng nhỏ hơn hai, tạo session mới;
3. Nếu đủ hai, từ chối login.

Ba request login có thể tới ba API instance cùng lúc. Session ID được lưu trong JWT có hạn 24 giờ; logout chỉ xóa cookie phía browser. Khi đổi password, server không thu hồi refresh token. Ứng dụng mobile tự refresh token ở mỗi request nền, không điều phối giữa các luồng.

**Yêu cầu:**

1. Xác định các race condition và rủi ro session hijacking/stale session.
2. Thiết kế lại việc thực thi quota hai phiên theo cách nguyên tử.
3. Đề xuất session registry và cách xử lý JWT/access/refresh token khi logout.
4. Thiết kế điều phối refresh token khi nhiều luồng mobile chạy đồng thời.
5. Xây dựng UX “đăng xuất thiết bị khác” và cách hiển thị phiên đáng ngờ.
6. Viết test kiểm tra ba login đồng thời không vượt quota và logout all có hiệu lực theo SLA.

**Gợi ý đối chiếu:** transaction/lock theo subject; session state có thể thu hồi; JWT tự chứa cần version/introspection/TTL; refresh rotation cần single-flight/idempotency; thay password phải áp dụng policy thu hồi; device/IP chỉ là tín hiệu; authorization vẫn kiểm tra tenant và account state.

## 20. Checklist thiết kế concurrent session

1. **Đơn vị phiên:** Đếm theo subject, tenant, client, device hay loại assurance?
2. **Policy:** Cho phép không giới hạn, max N, single session hay risk-based? Có giải thích cho người dùng?
3. **Atomicity:** Quota, revoke và insert có nằm trong transaction/lock để tránh race không?
4. **Session ID:** Ngẫu nhiên, khó đoán, không chứa thông tin cá nhân và được rotate sau login/step-up?
5. **Storage:** Session registry có trạng thái, idle/absolute expiry, auth context và credential version?
6. **Cookie/token:** Secure, HttpOnly, SameSite, TTL, audience và refresh policy phù hợp?
7. **Refresh:** Có single-flight, rotation state, replay detection và xử lý đồng thời?
8. **Logout:** Current, device, other sessions và all sessions có semantics rõ; server-side revoke thực sự?
9. **Consistency:** Cache, nhiều instance, WebSocket và service phụ có nhận invalidation trong SLA?
10. **Account changes:** Password reset, suspension, role/tenant change và authenticator revoke ảnh hưởng session thế nào?
11. **User visibility:** Người dùng xem và thu hồi phiên lạ được không? Metadata có được diễn giải đúng mức tin cậy?
12. **Privacy:** Log và telemetry không chứa session cookie/token; metadata thiết bị được giữ tối thiểu?
13. **Testing:** Đã test multi-tab, multi-device, concurrent login/refresh, race, logout và false positive?
14. **Recovery:** Nếu mọi phiên bị thu hồi hoặc thiết bị mất, người dùng có đường khôi phục an toàn không?

## 21. Ghi nhớ

- **Concurrent session** là nhiều phiên còn hiệu lực cho cùng principal; nhiều tab trong cùng browser thường dùng chung một session cookie.
- Chính sách có thể cho phép nhiều phiên, giới hạn tối đa, một phiên duy nhất hoặc áp dụng theo client/thiết bị/rủi ro.
- Quota phải được thực thi **nguyên tử**: đếm, chọn phiên bị thu hồi và tạo phiên mới không được chạy rời rạc khi có login đồng thời.
- Session cookie và token là credential có thể bị đánh cắp. Logout phải thu hồi phía server; xóa cookie ở client là chưa đủ.
- Refresh-token rotation cần xử lý race giữa nhiều tab/thiết bị; single-flight, idempotency và reuse detection phải có semantics rõ.
- Đổi password, suspend account, thu hồi MFA hoặc thay đổi membership cần chính sách cập nhật session/token và quyền hiện tại.
- Session hợp lệ không đồng nghĩa authorization luôn còn hợp lệ; API phải kiểm tra tenant, resource và trạng thái hiện thời.

Quản lý nhiều phiên tốt cho phép người dùng làm việc trên các thiết bị cần thiết, đồng thời giúp tổ chức biết phiên nào còn quyền truy cập, thu hồi phiên đáng ngờ và thực thi giới hạn nhất quán ngay cả khi nhiều login hoặc refresh xảy ra cùng lúc.
