# Sensitive data access

## 1. Vì sao truy cập dữ liệu nhạy cảm cần step-up?

Một người dùng có thể đã đăng nhập và có session hợp lệ, nhưng điều đó không có nghĩa mọi dữ liệu hoặc hành động đều nên được mở trong suốt vòng đời session. **Sensitive data access** là tình huống ứng dụng yêu cầu một mức xác thực mạnh hơn hoặc mới hơn trước khi cho phép xem, tải xuống, xuất hoặc chia sẻ dữ liệu có tác động lớn nếu bị lộ.

Ví dụ, người dùng có thể được phép xem trang tổng quan thông thường bằng session hiện tại, nhưng khi mở hồ sơ sức khỏe, thông tin tài chính, dữ liệu nhân sự, bí mật kinh doanh hoặc bản xuất chứa dữ liệu của nhiều người, hệ thống có thể yêu cầu xác thực lại bằng passkey hoặc MFA. Quyết định này được gọi là **step-up authentication**.

Step-up là một phần của authorization context: hệ thống đánh giá danh tính, quyền, độ nhạy của tài nguyên, mục đích sử dụng, thời điểm xác thực và mức assurance trước khi tiết lộ dữ liệu. Nó không thay thế authorization. Người dùng xác thực mạnh vẫn chỉ được xem dữ liệu mà họ có quyền truy cập.

Trong module **SECURITY_AUTHENTICATION_FUNDAMENTALS**, bài học này kết nối credential, password, MFA, passkey, authentication context, session và trust boundary. Thiết kế đúng cần trả lời ba câu hỏi: ai đang yêu cầu dữ liệu, họ có quyền xem dữ liệu đó không, và bằng chứng xác thực hiện tại có đủ mạnh và đủ mới cho hành động này không?

Sau bài học, người học có thể:

- Phân loại dữ liệu và xác định hành động nào cần step-up.
- Phân biệt authentication, authorization, freshness và assurance.
- Thiết kế policy theo principal, resource, action, purpose và risk context.
- Chọn phương thức step-up phù hợp, ưu tiên phương thức chống phishing khi rủi ro yêu cầu.
- Ràng buộc kết quả step-up với dữ liệu, hành động và transaction cụ thể.
- Thực thi policy ở backend/API và kiểm soát dữ liệu được trả về.
- Bảo vệ session, cache, export, audit và quy trình break-glass.
- Kiểm thử cả trường hợp được phép, bị từ chối, replay và context hết hạn.

## 2. Dữ liệu nhạy cảm là gì?

Dữ liệu nhạy cảm là dữ liệu mà việc tiết lộ, sửa đổi hoặc sử dụng sai có thể gây tổn hại cho cá nhân, tổ chức hoặc hệ thống. Mức độ nhạy cảm phụ thuộc vào bối cảnh, luật áp dụng, nghĩa vụ hợp đồng và tác động thực tế.

Ví dụ:

- **Dữ liệu cá nhân:** địa chỉ nhà, số định danh, ngày sinh, thông tin liên hệ riêng tư.
- **Dữ liệu tài chính:** số dư, lịch sử giao dịch, thông tin thanh toán, hồ sơ tín dụng.
- **Dữ liệu sức khỏe:** hồ sơ khám chữa bệnh, chẩn đoán, kết quả xét nghiệm, đơn thuốc.
- **Dữ liệu nhân sự:** lương, đánh giá hiệu suất, hồ sơ kỷ luật, thông tin nghỉ phép.
- **Dữ liệu tổ chức hạn chế:** kế hoạch kinh doanh, hợp đồng, báo cáo điều tra, thông tin khách hàng.
- **Bí mật kỹ thuật:** khóa API, token, private key, cấu hình bảo mật và thông tin vận hành nhạy cảm.

Không phải mọi trường dữ liệu trong một hồ sơ đều có cùng mức độ nhạy cảm. Ví dụ, tên hiển thị có thể ít nhạy cảm hơn số định danh hoặc thông tin tài khoản ngân hàng. Policy nên phân loại theo trường hoặc nhóm dữ liệu khi hệ thống có thể thực hiện.

### 2.1. Phân loại theo tác động

Một mô hình phân loại minh họa:

| Mức | Ví dụ | Hướng kiểm soát |
| --- | --- | --- |
| **Public** | Nội dung công khai, tài liệu đã xuất bản | Không cần step-up chỉ vì đọc dữ liệu |
| **Internal** | Tài liệu nội bộ không chứa dữ liệu cá nhân nhạy cảm | Session hợp lệ và quyền theo vai trò |
| **Confidential** | Hồ sơ khách hàng, hợp đồng, dữ liệu nhân sự | Có thể yêu cầu xác thực mới hơn, giới hạn tải và audit |
| **Restricted / Highly sensitive** | Hồ sơ sức khỏe, dữ liệu tài chính đặc biệt, bí mật quản trị | Step-up mạnh, purpose check, giới hạn phiên truy cập, kiểm soát export và giám sát |

Đây là ví dụ để xây policy; tên mức và yêu cầu cụ thể phải theo hệ thống phân loại dữ liệu của tổ chức. Không áp dụng một ngưỡng step-up cố định cho mọi lĩnh vực.

### 2.2. Xem, tải, xuất và chia sẻ có rủi ro khác nhau

Policy không nên chỉ xét tên trang hoặc loại bản ghi. Cùng một dữ liệu có thể được truy cập theo nhiều cách:

| Action | Rủi ro thường gặp | Policy có thể cân nhắc |
| --- | --- | --- |
| Xem một bản ghi | Tiết lộ dữ liệu cho người không có quyền | Authorization; step-up nếu dữ liệu rất nhạy cảm hoặc context cũ |
| Xem hàng loạt bản ghi | Lộ dữ liệu trên quy mô lớn | Step-up, giới hạn số lượng, purpose và audit |
| Tải tệp | Dữ liệu rời khỏi môi trường kiểm soát | Step-up, watermark, expiry và download audit |
| Xuất báo cáo | Tập hợp nhiều nguồn dữ liệu | Step-up mạnh, phê duyệt hoặc dual control |
| Chia sẻ với người khác | Mở rộng đối tượng nhận dữ liệu | Reauth, kiểm tra recipient, scope và thời hạn chia sẻ |
| In hoặc copy | Tạo bản sao khó thu hồi | Hạn chế theo policy, audit và kiểm soát thiết bị |
| Thay đổi hoặc xóa | Tác động tính toàn vẹn và khả năng khôi phục | Step-up, xác nhận transaction và quyền riêng |

Một lần step-up cho phép xem một bản ghi không mặc nhiên cấp quyền xuất toàn bộ dữ liệu cùng loại.

## 3. Bốn quyết định cần tách biệt

Khi người dùng yêu cầu dữ liệu nhạy cảm, hệ thống cần đánh giá riêng bốn khía cạnh:

1. **Authentication:** chủ thể nào đang kiểm soát session hoặc credential?
2. **Authorization:** chủ thể đó có quyền trên resource và action này không?
3. **Freshness:** lần xác thực đáng tin cậy gần nhất xảy ra cách đây bao lâu?
4. **Assurance:** lần xác thực dùng phương thức và mức bảo đảm nào?

Ví dụ: nhân viên có quyền xem hồ sơ khách hàng trong phạm vi phụ trách. Session của họ vẫn còn hạn nhưng authentication đã xảy ra từ hôm trước. Policy yêu cầu xác thực lại trong vòng 10 phút khi mở hồ sơ tài chính. Người dùng cần step-up. Sau khi xác thực lại thành công, hệ thống vẫn phải kiểm tra họ có quyền xem đúng khách hàng đó hay không.

~~~mermaid
flowchart TD
    A[Request dữ liệu nhạy cảm] --> B{Principal đã được xác thực?}
    B -- Không --> X[401 / yêu cầu đăng nhập]
    B -- Có --> C{Có quyền trên resource và action?}
    C -- Không --> Y[403 / từ chối]
    C -- Có --> D{Freshness và assurance đáp ứng policy?}
    D -- Có --> E[Tiếp tục kiểm tra purpose và giới hạn dữ liệu]
    D -- Không --> F[Yêu cầu step-up]
    F --> G{Step-up hợp lệ và đúng context?}
    G -- Không --> Z[Từ chối / giữ dữ liệu chưa tiết lộ]
    G -- Có --> E
    E --> H{Các điều kiện khác đạt?}
    H -- Không --> Y
    H -- Có --> I[Trả dữ liệu theo phạm vi được phép]
~~~

Step-up không thể sửa một quyết định authorization bị từ chối. Một người dùng không có quyền trên hồ sơ vẫn phải bị từ chối, dù vừa hoàn tất passkey hoặc MFA.

## 4. Xây dựng policy truy cập dữ liệu nhạy cảm

Một policy tốt xét nhiều yếu tố thay vì chỉ kiểm tra role hoặc yêu cầu nhập lại password.

Có thể biểu diễn quyết định:

~~~text
allow_sensitive_access =
    authenticated_principal
    AND authorized_for_resource
    AND authorized_for_action
    AND purpose_is_allowed
    AND authentication_is_fresh_enough
    AND assurance_meets_requirement
    AND risk_policy_allows
~~~

Đây là mô hình logic khái niệm. Hệ thống thực tế cần định nghĩa cách xử lý missing context, lỗi IdP, risk signal không xác định và các ngoại lệ.

### 4.1. Principal

Principal là danh tính đã được xác minh mà hệ thống dùng để ra quyết định. Cần ràng buộc principal với tenant, tổ chức, nhóm và trạng thái tài khoản. Không dùng tên hiển thị hoặc email tự khai làm khóa authorization nếu chúng có thể thay đổi hoặc trùng lặp.

### 4.2. Resource và action

Resource cần được xác định cụ thể: bản ghi nào, trường nào, tập dữ liệu nào, tenant nào. Action cần phân biệt read, export, download, share, update, delete và các thao tác khác.

Không nên kiểm tra quyền ở giao diện rồi giả định backend đã an toàn. API phải tự kiểm tra resource và action trên mỗi request.

### 4.3. Purpose of use

Một số hệ thống cần biết vì sao người dùng truy cập dữ liệu: điều trị bệnh nhân, xử lý yêu cầu hỗ trợ, kiểm toán, điều tra sự cố hoặc thực hiện nhiệm vụ nhân sự.

Purpose có thể là thuộc tính của request hoặc workflow được cấp quyền. Hệ thống cần xác định purpose có hợp lệ với vai trò, resource và chính sách hay không. Một ô văn bản tự do do người dùng nhập không tự tạo ra quyền truy cập.

### 4.4. Authentication context

Context có thể bao gồm:

- Issuer và subject đã được xác minh.
- Thời điểm xác thực gần nhất.
- Phương thức đã dùng: password, passkey, security key, certificate hoặc MFA.
- ACR/AMR hoặc assurance mapping theo hợp đồng với issuer.
- Thời điểm MFA hoặc user verification được hoàn tất.
- Session ID và authentication event ID.
- Mức rủi ro và trạng thái recovery/credential change nếu có.

Chỉ tin context lấy từ token/assertion đã xác minh hoặc từ backend nội bộ có integrity bảo vệ. Không tin các header như X-MFA-Verified do browser tự gửi.

## 5. Khi nào nên yêu cầu step-up?

Một policy có thể yêu cầu step-up khi:

- Dữ liệu thuộc nhóm confidential hoặc restricted.
- Người dùng truy cập dữ liệu lần đầu trong một phiên hoặc từ một thiết bị mới.
- Authentication time vượt quá freshness window.
- Context hiện tại không đáp ứng assurance cần thiết.
- Người dùng yêu cầu export, download hoặc chia sẻ số lượng lớn.
- Tài khoản vừa khôi phục, đổi password, đổi email hoặc thay phương thức MFA.
- Hành vi truy cập khác thường hoặc tín hiệu rủi ro tăng.
- Một thao tác có tác động lớn hoặc khó đảo ngược.

Không nên yêu cầu step-up cho mọi request bất kể rủi ro. Điều đó làm tăng ma sát, gây mệt mỏi MFA và có thể khiến người dùng chấp thuận prompt theo thói quen. Hãy áp dụng theo dữ liệu, action, context và mức tác động.

### 5.1. Freshness window

Freshness window là khoảng tuổi tối đa của authentication event được chấp nhận cho một hành động. Ví dụ minh họa:

| Hành động | Freshness có thể cân nhắc |
| --- | --- |
| Xem nội dung nội bộ thông thường | Session hợp lệ; không nhất thiết cần xác thực mới |
| Xem hồ sơ cá nhân nhạy cảm | Xác thực trong khoảng thời gian ngắn hơn theo policy |
| Tải hồ sơ tài chính | Xác thực mới và assurance phù hợp |
| Thay đổi phương thức recovery | Xác thực rất mới, step-up mạnh |
| Xuất dữ liệu hàng loạt | Xác thực mới, purpose và có thể cần phê duyệt bổ sung |

Không dùng các con số ví dụ làm mặc định chung. Chủ sở hữu dữ liệu và đội bảo mật phải xác định ngưỡng theo threat model, yêu cầu pháp lý, giá trị dữ liệu và khả năng xác thực.

### 5.2. Assurance window

Freshness và assurance là hai chiều độc lập. Một password vừa được nhập có thể mới nhưng không đáp ứng yêu cầu phishing-resistant MFA. Một passkey đã dùng cách đây nhiều giờ có thể mạnh nhưng không còn đủ mới.

Policy có thể yêu cầu đồng thời:
- Authentication age không vượt quá giới hạn.
- ACR/AMR hoặc event nội bộ xác nhận phương thức đạt yêu cầu.
- User verification đã xảy ra nếu policy cần.
- Credential chưa bị thu hồi và tài khoản không ở trạng thái rủi ro.
- Step-up thuộc đúng session/transaction đang yêu cầu dữ liệu.

## 6. Chọn phương thức step-up

Chọn phương thức theo mức rủi ro và môi trường người dùng. Không phải mọi MFA đều có cùng khả năng chống phishing.

| Phương thức | Đặc điểm | Khi cân nhắc |
| --- | --- | --- |
| **Passkey / WebAuthn** | Khóa công khai, ràng buộc origin và RP ID; có thể yêu cầu user verification | Ưu tiên cho ứng dụng web hiện đại khi thiết bị hỗ trợ |
| **Security key FIDO2** | Authenticator phần cứng, chống phishing tốt | Dữ liệu đặc biệt nhạy cảm hoặc tài khoản đặc quyền |
| **Authenticator app TOTP** | Mã dùng một lần dựa trên secret và thời gian | Phương án MFA phổ biến; vẫn có thể bị phishing/relay |
| **Push approval** | Người dùng chấp thuận trên thiết bị | Cần number matching và thông tin ngữ cảnh; tránh prompt mù |
| **SMS OTP** | Mã gửi qua mạng điện thoại | Phương án hạn chế khi không có lựa chọn tốt hơn; rủi ro SIM swap/SS7 |
| **Password re-entry** | Nhập lại password hiện tại | Có thể xác nhận biết secret nhưng không chống phishing tốt; không đủ cho policy đòi MFA mạnh |
| **Client certificate / mTLS** | Chứng minh kiểm soát private key của thiết bị/workload | Truy cập service hoặc môi trường quản lý phù hợp |

### 6.1. Ưu tiên chống phishing khi cần

Khi dữ liệu có tác động cao, nên cân nhắc passkey/WebAuthn hoặc security key FIDO2. WebAuthn gắn credential với origin/RP ID, giúp chống các trang phishing giả mạo domain hợp lệ. Tuy vậy, ứng dụng vẫn phải xác minh challenge, origin, RP ID hash, chữ ký, user presence và user verification theo policy.

Không tuyên bố mọi passkey đều đảm bảo cùng mức assurance trong mọi hoàn cảnh. Cần biết credential được đồng bộ hay gắn thiết bị, thiết bị có khóa màn hình an toàn hay không và issuer/IdP khẳng định context nào.

### 6.2. MFA fatigue và push bombing

Nếu ứng dụng gửi quá nhiều push prompt hoặc yêu cầu step-up lặp lại không có lý do, người dùng có thể chấp thuận chỉ để prompt biến mất. Giảm rủi ro bằng:

- Number matching hoặc challenge hiển thị trên màn hình.
- Hiển thị rõ ứng dụng, hành động và dữ liệu đang được truy cập.
- Rate limit prompt và phát hiện nhiều lần từ chối.
- Không gửi push tự động cho mỗi API request.
- Dùng passkey/security key cho hành động đặc biệt nhạy cảm khi phù hợp.
- Có thông báo và quy trình xử lý khi người dùng nhận prompt không chủ động.

## 7. Luồng step-up trước khi tiết lộ dữ liệu

Một luồng an toàn phải giữ dữ liệu nhạy cảm ở trạng thái chưa được trả về cho tới khi toàn bộ policy đạt.

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant W as Web / Client
    participant API as Backend API
    participant P as Policy Engine
    participant I as Identity Provider
    participant D as Data Store
    U->>W: Mở dữ liệu nhạy cảm
    W->>API: Request resource + action
    API->>P: Principal, resource, action, context
    P->>P: Kiểm tra authorization, purpose, freshness, assurance
    alt Context hiện tại đủ
        P-->>API: Allow theo phạm vi
    else Cần step-up
        P-->>API: Require step-up
        API-->>W: Challenge / redirect tới IdP
        W->>I: Reauthentication hoặc MFA
        I-->>W: Kết quả xác thực
        W->>API: Gửi kết quả / tiếp tục transaction
        API->>P: Xác minh context mới
        P-->>API: Allow hoặc deny
    end
    API->>D: Đọc đúng resource và fields được phép
    D-->>API: Dữ liệu đã giới hạn
    API-->>W: Trả response sau authorization
~~~

Các nguyên tắc quan trọng:

1. Backend kiểm tra quyền trước khi tiết lộ dữ liệu.
2. Nếu cần step-up, chỉ trả challenge hoặc trạng thái pending, không trả trước một phần dữ liệu nhạy cảm.
3. Kết quả xác thực phải được xác minh ở server.
4. Sau step-up, chạy lại authorization và purpose policy.
5. Chỉ lấy những trường dữ liệu cần thiết.
6. Challenge phải hết hạn và chỉ được dùng trong transaction phù hợp.
7. Side effect hoặc dữ liệu được trả về chỉ sau khi quyết định cuối cùng là allow.

Không để frontend tự quyết định rằng người dùng đã step-up. Giao diện chỉ hiển thị flow; backend là nơi thực thi policy.

## 8. Ràng buộc step-up với resource và transaction

Một kết quả step-up chung chung có thể bị tái sử dụng sai mục đích. Ví dụ, người dùng vừa xác thực để xem hồ sơ A; attacker cố đổi request thành hồ sơ B hoặc export toàn bộ tenant bằng cùng kết quả đó.

Cần ràng buộc bằng transaction hoặc access grant có phạm vi:

- Principal cụ thể.
- Session hoặc authentication event cụ thể.
- Resource ID hoặc tập resource có giới hạn.
- Action cụ thể: view, download, export hoặc share.
- Purpose đã được phê duyệt nếu áp dụng.
- Audience/API cụ thể.
- Thời hạn ngắn.
- Nonce/challenge dùng một lần hoặc cơ chế chống replay.
- Các tham số giao dịch quan trọng, chẳng hạn loại báo cáo và phạm vi dữ liệu.

Ví dụ grant khái niệm:

~~~json
{
  "subject": "user-4821",
  "resource": "customer-record-731",
  "action": "view_sensitive_fields",
  "purpose": "customer_support_case",
  "auth_event": "evt-91a2",
  "assurance": "phishing-resistant-mfa",
  "authenticated_at": "2026-11-22T09:15:00Z",
  "expires_at": "2026-11-22T09:20:00Z",
  "nonce": "single-use-value"
}
~~~

Đây là mô hình minh họa, không phải schema chuẩn. Không nhất thiết phải phát hành một token riêng; hệ thống có thể lưu grant server-side gắn với session. Điều quan trọng là phạm vi và thời hạn được backend kiểm tra.

### 8.1. Không biến step-up thành quyền rộng

Sau khi user hoàn tất MFA, không nên đặt một cờ toàn cục như mfa_recent=true rồi mở mọi dữ liệu nhạy cảm trong thời gian dài. Grant cần giới hạn theo resource/action và policy. Nếu sản phẩm cần một freshness window rộng hơn, vẫn phải kiểm tra lại quyền và purpose cho mỗi request.

### 8.2. Challenge one-time và chống replay

Challenge step-up cần gắn với session, principal và transaction. Khi thành công, server tiêu thụ challenge theo thao tác nguyên tử. Một callback hoặc assertion bị gửi lại không được tạo thêm grant hoặc thực hiện hành động lần thứ hai.

Nếu challenge hết hạn, session đổi principal hoặc transaction bị sửa, yêu cầu flow mới. Không chấp nhận response xác thực cũ chỉ vì chữ ký của nó hợp lệ.

## 9. Enforcement tại API và data layer

Kiểm soát ở frontend không đủ. API có thể được gọi trực tiếp, qua mobile client, script, browser console hoặc một service khác.

Backend cần:

- Xác minh access token/session và issuer.
- Kiểm tra audience, expiry, scope và token purpose.
- Resolve principal và tenant từ nguồn tin cậy.
- Kiểm tra quyền resource/action ở phía server.
- Đánh giá authentication freshness và assurance.
- Kiểm tra purpose, case assignment hoặc quan hệ công việc.
- Lấy đúng các field được phép, không trả toàn bộ record rồi ẩn field ở frontend.
- Ghi audit quyết định và dữ liệu đã truy cập theo policy.
- Áp dụng giới hạn pagination, bulk access, export và rate.

### 9.1. Field-level authorization

Một người dùng có thể được xem thông tin liên hệ nhưng không được xem số định danh hoặc thông tin thanh toán. Vì vậy, authorization nên có thể áp dụng tới field hoặc data projection.

Ví dụ:
- Hỗ trợ khách hàng được xem tên và trạng thái đơn hàng.
- Chỉ nhân viên được phân công mới xem địa chỉ giao hàng đầy đủ.
- Thông tin thanh toán chỉ hiển thị dạng mask; truy cập đầy đủ cần step-up và quyền chuyên biệt.
- Nhân sự chỉ xem hồ sơ lương trong phạm vi nhân viên được phân quyền.

Không trả dữ liệu nhạy cảm trong JSON rồi chỉ dùng CSS hoặc JavaScript để che. Dữ liệu đã gửi tới client có thể bị đọc qua DevTools, cache, extension hoặc log.

### 9.2. Bulk access và export

Truy cập hàng loạt có rủi ro cao hơn mở từng record. Policy có thể yêu cầu:
- Step-up riêng cho export.
- Mục đích và phạm vi dữ liệu rõ.
- Ngưỡng số lượng bản ghi.
- Phê duyệt thứ hai với tập dữ liệu lớn.
- File mã hóa hoặc link tải ngắn hạn.
- Watermark hoặc đánh dấu người xuất.
- Audit số lượng, loại dữ liệu và người nhận.
- Hạn chế tải lặp và phát hiện hành vi bất thường.

Không cho phép một grant xem một bản ghi được dùng để tải file tổng hợp.

## 10. Session, cache và thời hạn truy cập

Dữ liệu nhạy cảm có thể tiếp tục tồn tại sau khi server đã từ chối request mới: browser cache, back-forward cache, service worker, CDN, proxy, file tạm hoặc ứng dụng client có thể giữ bản sao.

Cần cân nhắc:

- Dùng cache-control phù hợp, thường là no-store cho response rất nhạy cảm.
- Không đưa dữ liệu nhạy cảm vào URL hoặc query string.
- Không lưu session ID, access token hoặc nội dung hồ sơ trong localStorage nếu có lựa chọn an toàn hơn.
- Kiểm soát service worker và offline cache.
- Link tải có thời hạn ngắn, audience/scope phù hợp và không dùng bearer URL lâu dài.
- Thu hồi grant khi logout, session revoke, credential change hoặc risk event theo policy.
- Xem xét absolute timeout ngay cả khi session có hoạt động liên tục.
- Xóa dữ liệu khỏi UI khi session hết hạn hoặc chuyển user.

Cookie HttpOnly giúp hạn chế JavaScript đọc cookie session nhưng không ngăn script XSS thực hiện request trong context của trang. CSP, output encoding, dependency hygiene và CSRF defense vẫn quan trọng.

## 11. Purpose limitation và quyền riêng tư

Step-up không tự tạo cơ sở hợp pháp để xem dữ liệu. Một người dùng có thể xác thực mạnh nhưng vẫn không có mục đích hợp lệ để truy cập hồ sơ.

Hệ thống nên:
- Chỉ yêu cầu dữ liệu cần thiết cho nhiệm vụ.
- Giới hạn purpose theo vai trò và workflow.
- Hiển thị cho người dùng lý do truy cập khi phù hợp.
- Tránh lưu dữ liệu nhạy cảm trong audit log.
- Ghi loại dữ liệu, resource ID, action và purpose thay vì sao chép nội dung.
- Áp dụng retention cho grant, audit và dữ liệu tạm.
- Tách quyền đọc, export và chia sẻ.
- Có quy trình truy cập khẩn cấp được giám sát.

Không dùng việc user đã hoàn tất MFA để hợp thức hóa việc thu thập hoặc xử lý dữ liệu vượt quá mục đích được phép.

## 12. Break-glass và truy cập khẩn cấp

Một số môi trường có thể cần truy cập khẩn cấp khi hệ thống xác thực chính hoặc IdP gặp sự cố. Ví dụ, nhân viên y tế cần xem thông tin tối thiểu để xử lý tình huống cấp cứu. Cơ chế này thường gọi là **break-glass access**.

Một policy break-glass nên:
- Giới hạn cho vai trò và tình huống cụ thể.
- Yêu cầu lý do và mã case hoặc incident.
- Dùng xác thực mạnh nhất khả dụng trong điều kiện khẩn cấp.
- Giới hạn resource, field và thời gian truy cập.
- Hiển thị cảnh báo rõ rằng truy cập được ghi nhận và review.
- Gửi thông báo tới owner hoặc đội giám sát.
- Audit đầy đủ và review hậu kiểm bắt buộc.
- Thu hồi grant khi tình huống kết thúc.

Break-glass không nên là tài khoản dùng chung, mật khẩu tĩnh hoặc bypass không ghi log. Không để ngoại lệ khẩn cấp trở thành đường truy cập thường xuyên. Nếu hệ thống cần cho phép tiếp tục hoạt động khi IdP down, phải thiết kế và kiểm thử trước, với giới hạn và kiểm soát rõ.

## 13. Rủi ro và cách phòng tránh

| Mối đe dọa | Cách xảy ra | Kiểm soát |
| --- | --- | --- |
| **Session theft** | Attacker lấy cookie/token rồi truy cập dữ liệu | TLS, secure cookie, revoke, freshness và step-up theo risk |
| **MFA fatigue** | User chấp thuận push prompt không chủ động | Number matching, rate limit, thông tin hành động rõ |
| **Phishing / AiTM** | Attacker relay password/OTP qua trang giả | Passkey/security key, origin binding, không chỉ dựa OTP |
| **Step-up replay** | Dùng lại assertion/challenge thành công | Nonce, transaction binding, expiry và consume-once |
| **Privilege escalation** | Step-up xong được mở rộng quyền toàn hệ thống | Giữ authorization riêng, resource/action scope |
| **IDOR/BOLA** | Thay resource ID trong request để đọc hồ sơ khác | Object-level authorization tại API |
| **Bulk exfiltration** | Dùng quyền xem để export số lượng lớn | Export policy riêng, quota, approval và audit |
| **XSS** | Script độc hại gọi API bằng session người dùng | Output encoding, CSP, secure development và step-up không thay XSS defense |
| **CSRF** | Browser gửi request tự động với cookie | SameSite phù hợp, CSRF token, Origin/Fetch Metadata |
| **Cache leakage** | Dữ liệu vẫn có trong cache sau logout | Cache-Control, kiểm soát client cache và xóa state |
| **Recovery abuse** | Attacker dùng recovery yếu để đạt context mới | Re-proofing, delay, notification và revoke session |
| **Insider misuse** | Nhân viên hợp lệ xem dữ liệu ngoài nhiệm vụ | Purpose enforcement, least privilege, audit và review |
| **Break-glass abuse** | Ngoại lệ khẩn cấp bị lạm dụng | Scope nhỏ, time limit, alert và hậu kiểm |

## 14. Ví dụ: truy cập hồ sơ tài chính

Giả sử nhân viên hỗ trợ được phép xem thông tin tài khoản của khách hàng trong case đang được giao. Dữ liệu gồm tên, trạng thái tài khoản, số dư và thông tin giao dịch.

Một policy có thể hoạt động như sau:

1. Người dùng đăng nhập và có session hợp lệ.
2. API kiểm tra principal là nhân viên đang hoạt động và thuộc nhóm hỗ trợ phù hợp.
3. API kiểm tra case được giao cho nhân viên và khách hàng nằm trong phạm vi case.
4. Policy xác định số dư và giao dịch là dữ liệu nhạy cảm; session hiện tại có authentication time quá cũ.
5. Backend yêu cầu step-up bằng passkey hoặc phương thức được policy chấp nhận.
6. IdP trả kết quả; backend xác minh issuer, audience, authentication time, ACR/AMR và transaction binding.
7. Backend chạy lại object-level authorization và purpose check.
8. API chỉ trả các trường cần thiết cho case, mask thông tin không cần thiết và ghi audit.
9. Nếu nhân viên yêu cầu export toàn bộ lịch sử giao dịch, policy đánh giá đó là action khác và yêu cầu quyền/step-up/phê duyệt riêng.

Trong ví dụ này, step-up xác nhận context xác thực mới hơn. Nó không thay thế việc nhân viên phải được giao case và có mục đích công việc hợp lệ.

~~~mermaid
flowchart TD
    A[Nhân viên mở hồ sơ tài chính] --> B[Kiểm tra nhân viên và case assignment]
    B --> C{Có quyền xem hồ sơ?}
    C -- Không --> X[Từ chối]
    C -- Có --> D[Đánh giá độ nhạy và purpose]
    D --> E{Auth freshness + assurance đạt?}
    E -- Không --> F[Passkey / MFA step-up]
    F --> G{Context hợp lệ, đúng transaction?}
    G -- Không --> X
    G -- Có --> H[Kiểm tra lại authorization]
    E -- Có --> H
    H --> I[Trả fields được phép, mask phần còn lại]
    I --> J[Audit resource, action, purpose]
~~~

## 15. Kiểm thử sensitive data access

Kiểm thử cần xác nhận dữ liệu không bị tiết lộ trước khi policy hoàn tất.

| Test case | Kết quả mong đợi |
| --- | --- |
| Session hợp lệ, quyền hợp lệ, context đủ mới | Trả dữ liệu đúng phạm vi |
| Session hết hạn | Yêu cầu đăng nhập lại |
| Session hợp lệ nhưng authentication quá cũ | Yêu cầu step-up trước khi trả dữ liệu |
| User không có quyền trên resource | Từ chối dù step-up thành công |
| ACR/AMR không đạt policy | Từ chối hoặc yêu cầu phương thức phù hợp |
| Token issuer/audience sai | Từ chối |
| Step-up response hết hạn | Từ chối và yêu cầu flow mới |
| Reuse challenge hoặc callback | Từ chối replay |
| Thay resource ID sau step-up | Từ chối nếu không thuộc grant |
| Đổi action view thành export | Đánh giá policy export riêng |
| Thay purpose sau khi xác thực | Từ chối hoặc yêu cầu transaction mới |
| User vừa recovery hoặc đổi MFA | Áp dụng hạn chế/step-up theo policy |
| XSS hoặc CSRF test | Kiểm soát tương ứng vẫn có hiệu lực |
| API bị gọi trực tiếp bỏ qua frontend | Backend vẫn kiểm tra đầy đủ |
| Browser cache/back-forward sau logout | Không lộ dữ liệu theo policy |
| Break-glass được kích hoạt | Có scope, expiry, alert và hậu kiểm |
| Bulk request vượt quota | Rate limit hoặc yêu cầu phê duyệt |
| Audit event được tạo | Không chứa token, session ID hoặc dữ liệu nhạy cảm thô |

### 15.1. Kiểm tra dữ liệu trước challenge

Một lỗi phổ biến là frontend tải toàn bộ hồ sơ trước, sau đó mới hiển thị màn hình step-up để mở khóa các trường nhạy cảm. Nếu dữ liệu đã nằm trong response, việc ẩn nó bằng UI không có tác dụng bảo mật.

Hãy kiểm tra Network tab và API response: trước khi step-up, server chỉ được trả dữ liệu mà session hiện tại được phép xem. Các trường yêu cầu step-up phải không xuất hiện trong response, cache hoặc dữ liệu preload.

## 16. Checklist review policy

| Câu hỏi | Dấu hiệu thiết kế tốt |
| --- | --- |
| Dữ liệu đã được phân loại? | Có owner, sensitivity và tác động rò rỉ |
| Action có được phân biệt? | View, export, download, share và modify có policy riêng |
| Principal/resource/tenant có rõ? | Object-level authorization phía backend |
| Purpose có hợp lệ? | Gắn với workflow/role, không chỉ ô nhập tự do |
| Freshness được đánh giá? | Dựa trên authentication event đáng tin cậy |
| Assurance có đáp ứng? | Phương thức/ACR/AMR được mapping và kiểm tra |
| Step-up có chống phishing khi cần? | Passkey/FIDO2 hoặc phương thức phù hợp rủi ro |
| Context có transaction binding? | Principal, resource, action, purpose và expiry được ràng buộc |
| Challenge có one-time? | Replay bị từ chối bằng consume-once |
| Backend thực thi policy? | Không phụ thuộc frontend hoặc hidden field |
| Field-level access có áp dụng? | Chỉ trả dữ liệu cần thiết |
| Export có policy riêng? | Quota, approval, watermark và audit |
| Session/cache có an toàn? | Idle/absolute timeout, no-store khi phù hợp |
| Recovery có được xem xét? | Session/credential change ảnh hưởng policy |
| Break-glass có kiểm soát? | Lý do, scope, expiry, alert và hậu kiểm |
| Audit không lộ dữ liệu? | Metadata đủ điều tra, không lưu secret hoặc nội dung nhạy cảm |
| Có negative tests? | Replay, IDOR, context cũ, wrong audience và cache leakage |

### Tình huống tự kiểm tra

**Tình huống 1:** Nhân viên vừa hoàn tất passkey. Có thể cho họ xem mọi hồ sơ tài chính trong hệ thống không?

**Trả lời:** Không. Passkey step-up chỉ cải thiện authentication context. Backend vẫn phải kiểm tra quyền trên từng resource, action, tenant và purpose.

**Tình huống 2:** Frontend tải toàn bộ hồ sơ rồi dùng CSS che số tài khoản cho tới khi người dùng MFA. Thiết kế này có an toàn không?

**Trả lời:** Không. Dữ liệu đã được gửi tới client và có thể đọc qua Network/DevTools. Backend phải giữ các trường nhạy cảm và chỉ trả sau khi policy đạt.

**Tình huống 3:** Người dùng step-up để xem hồ sơ A rồi thay ID thành hồ sơ B. Có được dùng lại kết quả không?

**Trả lời:** Không nếu grant được ràng buộc với hồ sơ A. Server cần kiểm tra resource/action và transaction binding.

**Tình huống 4:** Session vừa gửi heartbeat nên last activity mới. Có đủ chứng minh authentication mới không?

**Trả lời:** Không. Heartbeat chỉ là hoạt động của session; không tạo authentication event mới.

**Tình huống 5:** Người dùng không có quyền xem dữ liệu nhưng hoàn tất MFA mạnh. Có được truy cập không?

**Trả lời:** Không. Authentication và authorization là hai quyết định riêng. Thiếu quyền trên resource thì phải từ chối.

**Tình huống 6:** Một nhân viên dùng break-glass để truy cập hồ sơ khẩn cấp. Có thể bỏ audit vì đây là trường hợp đặc biệt không?

**Trả lời:** Không. Truy cập khẩn cấp cần audit và hậu kiểm rõ hơn, cùng scope và thời hạn giới hạn.

## 17. Ghi nhớ

**Sensitive data access cần đánh giá cả quyền truy cập lẫn chất lượng của authentication context tại thời điểm yêu cầu dữ liệu.** Step-up được dùng khi session hiện tại quá cũ, assurance chưa đủ hoặc rủi ro/action yêu cầu xác thực mạnh hơn. Nó không cấp quyền rộng và không thay thế kiểm tra principal, resource, action và purpose.

Thiết kế an toàn phân loại dữ liệu, đặt policy theo rủi ro, ưu tiên phương thức chống phishing khi cần, ràng buộc step-up với transaction và thực thi ở backend trước khi tiết lộ dữ liệu. Kiểm soát field-level access, export, cache, session, audit và break-glass để dữ liệu không bị lộ qua đường vòng.
