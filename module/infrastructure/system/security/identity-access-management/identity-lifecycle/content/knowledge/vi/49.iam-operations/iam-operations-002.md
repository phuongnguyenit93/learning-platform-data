# Xử lý account lockout trong IAM: điều tra, khôi phục và phòng ngừa

## 1. Mục tiêu của quy trình xử lý account lockout

**Account lockout** là trạng thái tài khoản tạm thời không được phép xác thực sau khi vi phạm điều kiện khóa của hệ thống, thường là vượt ngưỡng đăng nhập sai trong một khoảng thời gian. Tùy nền tảng, khóa có thể tự hết hạn hoặc cần người có thẩm quyền thực hiện thao tác mở khóa. Lockout là một kiểm soát chống thử mật khẩu sai liên tiếp; đồng thời có thể trở thành tín hiệu cho thấy cấu hình ứng dụng bị lỗi hoặc đang có tấn công.

Trong **IAM operations**, xử lý lockout không đơn giản là nhấn **Unlock**. Người vận hành phải xác định **hệ thống nào từ chối truy cập, nguyên nhân thất bại, tình trạng hợp lệ của danh tính và liệu có dấu hiệu tấn công hay không**. Mở khóa nhầm một tài khoản đang bị đình chỉ hoặc đã nghỉ việc có thể vô hiệu hóa các kiểm soát trong mô hình **Joiner–Mover–Leaver (JML)**.

Bài học tập trung vào xử lý account lockout xuyên suốt **IdP, SSO, SCIM, RBAC/ABAC, tài khoản dịch vụ và audit**, với mục đích khôi phục quyền truy cập hợp lệ, giảm quyền tồn dư và ngăn tình trạng tái khóa.

**Sau bài học, bạn có thể:**

1. Phân biệt khóa do xác thực sai với vô hiệu hóa tài khoản, chặn do chính sách và thiếu quyền ứng dụng.
2. Đọc đúng dấu hiệu từ IdP, directory, SSO và ứng dụng đích để xác định nguồn khóa.
3. Áp dụng runbook xác minh danh tính, đánh giá rủi ro, sửa nguyên nhân, mở khóa và kiểm chứng.
4. Xử lý các trường hợp đặc biệt: Joiner, Mover, Leaver, tài khoản đặc quyền, service account và lockout hàng loạt.
5. Thiết lập kiểm toán, giám sát và bài học phòng ngừa sau sự cố.

> **Giới hạn áp dụng:** Tên nút, mã lỗi, ngưỡng số lần đăng nhập sai, thời gian tự mở khóa và cách quản trị khác nhau giữa các nhà cung cấp. Các bước sau là runbook tham chiếu; mọi thay đổi trong hệ thống thật phải tuân theo quyền thao tác, chính sách bảo mật và quy trình ứng phó của tổ chức.

## 2. Nhận biết đúng trạng thái: không phải mọi lỗi đăng nhập đều là lockout

| Trạng thái | Dấu hiệu điển hình | Hướng xử lý chính |
|---|---|---|
| **Account lockout** | Nhiều lần sai mật khẩu, nền tảng ghi nhận khóa tạm thời | Điều tra retry, xác minh chủ thể rồi mở theo chính sách |
| **Disabled / deactivated** | Tài khoản bị tắt bởi quản trị viên, HR/JML hoặc đồng bộ SCIM | Kiểm tra quyết định vô hiệu hóa; không tự ý mở khóa |
| **Suspended** | Bị đình chỉ tạm do nhân sự, pháp lý hoặc bảo mật | Chờ owner có thẩm quyền xác nhận điều kiện tái kích hoạt |
| **Risk/Conditional Access block** | Địa điểm, thiết bị, mức rủi ro hoặc điều kiện đăng nhập không đạt | Xác định policy đã chặn, xử lý điều kiện; Unlock đơn lẻ không giúp |
| **MFA failure** | Mất thiết bị, phương thức MFA lỗi, yêu cầu MFA bị từ chối | Khôi phục phương thức theo xác minh tăng cường |
| **Password expired / reset required** | Người dùng phải đổi mật khẩu | Thực hiện đổi/reset hợp lệ; chưa chắc cần Unlock |
| **SSO protocol failure** | OIDC/SAML lỗi cấu hình, token, trust, clock skew hoặc claim | Điều tra IdP và Service Provider |
| **Authorization denied** | Đăng nhập IdP thành công nhưng ứng dụng thiếu RBAC role hoặc không thỏa ABAC | Kiểm tra quyền và phê duyệt; không reset mật khẩu |
| **Local app lockout** | Tài khoản cục bộ của ứng dụng bị khóa dù SSO vẫn hoạt động | Xử lý ở ứng dụng và kiểm tra đường đăng nhập local |
| **Throttling / rate limit** | API hoặc client nhận giới hạn tần suất | Giảm retry, chờ hạn mức, kiểm tra nguồn gửi yêu cầu |

**Authentication** trả lời “chủ thể có xác thực thành công không?”, còn **authorization** trả lời “chủ thể được phép thực hiện hành động nào?”. Một người có thể xác thực thành công nhưng không có quyền xem dữ liệu; tình huống đó không được sửa bằng cách mở khóa hoặc tự cấp lại vai trò cũ.

Trạng thái **Active** trong IdP cũng không chứng minh account còn hợp lệ ở mọi ứng dụng: SCIM có thể đã deprovision tại ứng dụng, phiên đăng nhập còn hiệu lực có thể chưa bị thu hồi, hoặc tài khoản cục bộ không dùng SSO. Ngược lại, việc khóa IdP không mặc nhiên thu hồi mọi refresh token, API key và session độc lập ở ứng dụng.

## 3. Khóa tài khoản có thể diễn ra tại nhiều lớp

~~~mermaid
flowchart LR
    U[Người dùng hoặc workload] --> APP[Ứng dụng]
    APP -->|OIDC / SAML SSO| IDP[Identity Provider]
    IDP --> DIR[Directory / Credential Store]
    IDP --> POLICY[MFA / Risk / Access Policy]
    APP --> LOCAL[Local Authentication]
    HR[HRIS / Nguồn nhà thầu] --> JML[Điều phối JML]
    JML --> IDP
    JML -->|SCIM / API| APP
    IDP --> LOG[Audit / SIEM]
    DIR --> LOG
    APP --> LOG
    POLICY --> LOG
~~~

Trong luồng trên, cần xác định **điểm quyết định lỗi** thay vì chỉ nhìn màn hình thông báo:

- **IdP hoặc directory:** duy trì trạng thái lockout, bộ đếm thử sai và chính sách mật khẩu; có thể gây ảnh hưởng nhiều ứng dụng cùng dùng SSO.
- **MFA/risk engine:** chặn theo ngữ cảnh, hành vi hoặc điều kiện bảo mật, không nhất thiết liên quan bộ đếm mật khẩu.
- **Ứng dụng đích:** có thể giữ cơ chế local login, token, session hoặc policy riêng.
- **SCIM/provisioning:** cập nhật tài khoản từ JML; trạng thái inactive có thể là hành vi Leaver đúng thiết kế.
- **Các kênh phụ trợ:** VPN, SSH, Wi-Fi enterprise, ứng dụng di động, service agent và legacy protocol có thể tiếp tục gửi mật khẩu cũ gây lockout lặp.

**Quy tắc:** tra cứu log từ hệ thống tạo ra trạng thái khóa. Không suy luận rằng ứng dụng hiển thị thông báo chính là nơi phát sinh vấn đề.

## 4. Dữ liệu đầu vào và trách nhiệm vận hành

### 4.1. Hồ sơ tối thiểu cho một yêu cầu lockout

| Trường | Mục đích |
|---|---|
| Ticket ID và correlation ID | Liên kết yêu cầu, sign-in event và hành động quản trị |
| Subject ID bất biến | Đối chiếu cùng một chủ thể qua HR, IdP và ứng dụng; tránh dựa chỉ vào email |
| Ứng dụng, client và phương thức login | Xác định IdP SSO, VPN, API hoặc local authentication |
| Thời điểm phát sinh, múi giờ | Đối chiếu event chính xác và phát hiện lỗi xảy ra đồng thời |
| Mã lỗi / error category | Phân biệt lockout, MFA, federation, provisioning và authorization |
| Trạng thái vòng đời danh tính | Active, Pending, Suspended, Terminated hoặc Mover đang xử lý |
| Dấu hiệu tấn công và ảnh hưởng | Một user, nhiều user, account admin, dịch vụ sản xuất |
| Người phê duyệt và kết quả | Truy vết quyết định và xác minh sau xử lý |

**Không** yêu cầu hoặc lưu mật khẩu, mã OTP, recovery code, access token hay bí mật thô trong ticket/log. Chỉ ghi ID tham chiếu và dữ kiện cần thiết, tuân thủ phân quyền truy cập PII.

### 4.2. Ai xử lý?

| Vai trò | Trách nhiệm |
|---|---|
| Service Desk / L1 | Tiếp nhận, xác minh người yêu cầu theo quy trình cho phép, thu thập triệu chứng |
| IAM Operations / L2 | Điều tra IdP/directory, xác định nguồn lockout, thực thi Unlock và kiểm chứng |
| Security Operations (SOC) | Điều tra credential stuffing, password spraying, chiếm quyền, chỉ đạo containment |
| HR hoặc sponsor | Xác nhận tình trạng lao động, nhà thầu, ngày hiệu lực, quyền tái kích hoạt |
| Application Owner | Điều tra account cục bộ, retry từ connector và quyền ứng dụng |
| PAM/Security Owner | Phê duyệt thao tác với tài khoản đặc quyền và break-glass |

**Điều kiện an toàn:** người yêu cầu được xác minh đủ tin cậy; nguồn JML xác nhận chủ thể được phép đăng nhập; không có hold do bảo mật/nhân sự đang có hiệu lực; nguyên nhân khóa đã được phân loại; người thực thi có quyền quản trị hợp lệ.

## 5. Cây quyết định khi nhận ticket account lockout

~~~mermaid
flowchart TD
    A[Nhận ticket / cảnh báo] --> B{Xác minh đúng chủ thể?}
    B -->|Không| C[Giữ yêu cầu, xác minh qua kênh chuẩn]
    B -->|Có| D{JML cho phép truy cập?}
    D -->|Pending / Suspended / Leaver| E[Không Unlock; hỏi HR / Security]
    D -->|Active| F{Có dấu hiệu compromise / tấn công?}
    F -->|Có hoặc chưa loại trừ| G[Chuyển SOC và containment]
    F -->|Không| H{Nguồn từ chối?}
    H -->|IdP / Directory / App local| I[Phân tích log và nguồn retry]
    H -->|MFA / Risk| J[Quy trình khôi phục bảo mật]
    H -->|RBAC / ABAC| K[Quy trình quyền, không Unlock]
    H -->|SSO / SCIM| L[Điều tra cấu hình / provisioning]
    I --> M[Sửa nguyên nhân gây khóa]
    M --> N{Đủ phê duyệt và điều kiện mở?}
    N -->|Không| O[Giữ trạng thái và ghi ngoại lệ]
    N -->|Có| P[Unlock tại nguồn chính xác]
    P --> Q[Đăng nhập thử hợp lệ và verify quyền]
    Q --> R[Audit, giám sát tái khóa, đóng ticket]
~~~

Nhánh SOC có thể yêu cầu giữ tài khoản bị khóa, revoke phiên, rotate credential hoặc kiểm tra các login thành công bất thường. Không tự động chuyển từ cảnh báo bảo mật sang Unlock.

## 6. SOP-AL01 — Tiếp nhận, xác minh danh tính và điều kiện JML

**Kích hoạt:** người dùng báo lỗi login hoặc hệ thống cảnh báo account lockout. **Owner:** Service Desk phối hợp IAM.

1. Tạo ticket với source, thời điểm, ứng dụng, mã lỗi và kênh liên hệ. Tái sử dụng ticket cũ nếu cùng sự cố để tránh thao tác trùng.
2. Đối chiếu chủ thể qua **subject ID bất biến** trong IAM/HR. Nếu trùng email, đổi tên hoặc mapping mơ hồ, tạm dừng xử lý và xác minh thủ công.
3. Xác minh requester bằng **quy trình identity proofing được phê duyệt**; không chỉ dựa trên email khi email hoặc account đang có nguy cơ bị chiếm quyền. Không hỏi mật khẩu hay mã MFA.
4. Kiểm tra nguồn nhân sự/nhà thầu để xác định **Active, Pending Joiner, Mover, Suspended hoặc Terminated Leaver**. Ghi thời điểm hiệu lực và các hold liên quan.
5. Xác định tài khoản có quyền cao, ảnh hưởng sản xuất hoặc cảnh báo SOC không; nâng mức ưu tiên đúng quy trình nếu có.
6. Thu thập triệu chứng với số lần thử tối thiểu: ứng dụng, phương thức đăng nhập, thiết bị, thời gian, hình thức lỗi và event/correlation ID. Hướng dẫn người dùng **ngừng thử lại liên tục** cho tới khi điều tra.

**Đạt:** người yêu cầu đã được xác minh, danh tính và trạng thái JML đúng, ticket có hệ thống đích và dữ kiện đủ để truy log. Nếu chủ thể bị Leaver/Suspended, **không mở khóa**; chuyển yêu cầu tới HR/Security/owner có thẩm quyền.

## 7. SOP-AL02 — Điều tra nguồn khóa và dấu vết đăng nhập

### 7.1. Quy trình tra cứu

1. Tìm **sign-in events** tại IdP theo subject ID, ứng dụng và cửa sổ thời gian, chú ý độ trễ log và múi giờ.
2. Đọc kết quả xác thực, failure reason, loại client, MFA status, device context, location/risk signals và policy đã quyết định.
3. Nếu xác thực được ủy thác cho directory hoặc kiến trúc hybrid, kiểm tra điểm quyết định lockout trong directory; tránh Unlock ở sai nguồn rồi bị đồng bộ ghi đè.
4. Tra cứu log ứng dụng đích: local lockout, session, token, SAML/OIDC validation, user inactive, thiếu role hoặc lỗi access policy.
5. Kiểm tra sự kiện gần nhất từ JML, SCIM và RBAC/ABAC. Một thay đổi quyền hoặc deactivation đúng chính sách có thể giải thích lỗi.
6. Phân tích phạm vi: một chủ thể, một client, nhiều user chung IP hoặc nhiều ứng dụng cùng báo lỗi sau deploy.

### 7.2. Log minh họa

~~~json
{
  "event_id": "signin-example-081",
  "timestamp": "2026-11-23T09:12:05+07:00",
  "subject_id": "person-1042",
  "application_id": "portal-web",
  "authentication_source": "corporate-idp",
  "outcome": "DENIED",
  "reason_category": "ACCOUNT_LOCKED",
  "client_type": "browser",
  "source_network_ref": "network-context-42",
  "device_ref": "device-014",
  "correlation_id": "corr-example-310"
}
~~~

Đây là **dữ liệu giả lập**; tên trường và mã lỗi thật phụ thuộc nền tảng. Trong production, không đưa raw token, mật khẩu hay PII nhạy cảm vào ticket.

### 7.3. Đọc mẫu lỗi

| Triệu chứng | Giả thuyết | Hướng điều tra |
|---|---|---|
| Thất bại lặp từ một thiết bị sau đổi mật khẩu | Credential cache, VPN hoặc client cũ | Xác định client gây retry, cập nhật credential an toàn |
| Nhiều account cùng bị thử từ một hay nhiều IP | Password spraying / credential stuffing | Chuyển SOC, kiểm tra thành công bất thường xen giữa |
| IdP báo success, app báo denied | Role, claim, SCIM, session, local app | So actual state với quyền RBAC/ABAC dự kiến |
| Lỗi sau thay đổi thiết bị/vị trí | Conditional Access/MFA | Xem chính sách và trạng thái thiết bị |
| Nhiều app lỗi sau thay đổi cấu hình | Federation, cert, routing, clock skew, outage | Kiểm tra các thay đổi gần nhất |
| Lockout đều đặn dù user không thao tác | Scheduled task, agent, script, legacy auth | Lần theo source client và lịch retry |
| Account disabled bởi JML | Leaver/Suspend hoặc sai dữ liệu nguồn | Xác thực quyết định ở HR/sponsor trước khi tái kích hoạt |

Đừng xem IP lạ là bằng chứng chắc chắn có tấn công, cũng đừng xem IP quen là bằng chứng an toàn. Cần phối hợp các tín hiệu và đánh giá của Security.

## 8. SOP-AL03 — Xử lý theo từng nhóm nguyên nhân

### A. Người dùng hợp lệ nhập sai mật khẩu

Khi người dùng đã được xác minh, danh tính Active và log khớp thao tác hợp lệ, hướng dẫn dừng retry. Nếu policy có **self-service unlock/timeout**, thực hiện theo cơ chế đó; nếu quên mật khẩu, dùng **Self-Service Password Reset (SSPR)** hoặc quy trình admin reset được phê duyệt. Xác nhận người dùng đã cập nhật credential trên các thiết bị khác trước khi Unlock. Không yêu cầu họ gửi lại mật khẩu, không tắt MFA và không tạo mật khẩu dùng chung.

### B. Ứng dụng hoặc thiết bị giữ credential cũ

Nguồn có thể là VPN, mail client, Wi-Fi doanh nghiệp, điện thoại, máy tính cũ, tác vụ theo lịch hay script. Xác định **client ID/thiết bị/khung thời gian**, phối hợp owner dừng retry có kiểm soát, xóa hoặc cập nhật credential qua công cụ phù hợp rồi mới mở khóa. Nếu dịch vụ production phụ thuộc, phải theo quy trình change/incident để tránh gián đoạn dây chuyền.

**Hiện tượng thường gặp:** Unlock thành công, vài phút sau lại lock vì job tiếp tục gửi mật khẩu cũ. Cứ mở khóa liên tục chỉ xử lý triệu chứng. Cần sửa nguồn retry và giám sát ít nhất một chu kỳ chạy liên quan.

### C. Nghi brute force, spraying, credential stuffing hoặc compromise

Tín hiệu có thể gồm nhiều account bị khóa gần nhau, nguồn truy cập bất thường, account admin bị nhắm tới hoặc có login thành công đáng ngờ. Thao tác chính là **giữ bằng chứng và chuyển SOC**, kiểm tra sự kiện đăng nhập thành công, mức độ ảnh hưởng, trạng thái MFA, các session/token và credential có thể bị lộ.

SOC có thể chỉ đạo containment như chặn client theo chính sách, revoke session, reset/rotate credential và giữ tài khoản khóa. Việc mở lại phải chờ điều kiện khôi phục được phê duyệt; lời xác nhận của người dùng không tự loại trừ tấn công đang diễn ra.

### D. MFA, risk policy hoặc Conditional Access

Nếu sign-in bị chặn vì thiết bị không tuân thủ, MFA bị mất hoặc rủi ro tăng, xác định **policy cụ thể** rồi dùng quy trình sửa thiết bị, identity proofing và MFA recovery. Không nới policy toàn tổ chức hoặc bypass yếu tố xác thực để giải quyết một ticket. Với dấu hiệu chiếm quyền, Security phải kiểm tra trước khi reset phương thức MFA.

### E. SSO, provisioning hoặc authorization

Nếu IdP xác thực thành công nhưng ứng dụng từ chối, kiểm tra OIDC/SAML, audience/issuer, claim, trạng thái provisioning, RBAC role và điều kiện ABAC. Nếu user chưa được SCIM tạo hoặc đã inactive do Leaver, phải xử lý ở **nguồn JML và connector**. Nếu quyền chưa phê duyệt, chuyển quy trình access request; không tự gán nhóm cũ để vượt lỗi.

## 9. SOP-AL04 — Mở khóa có kiểm soát và xác nhận kết quả

**Trigger:** đã xác định lockout thực sự, trạng thái JML cho phép truy cập, nguyên nhân đã xử lý hoặc kiểm soát, không có security hold đang có hiệu lực và có người có quyền thực thi.

1. Kiểm tra ticket, subject ID, nguồn khóa chính xác, bằng chứng identity proofing, đánh giá Security và phê duyệt theo mức nhạy cảm tài khoản.
2. Chọn hành động nền tảng hỗ trợ: **đợi hết thời gian tự mở**, self-service recovery hoặc thao tác admin unlock tại **hệ thống sở hữu trạng thái khóa**. Không đoán lệnh dùng cho nền tảng khác.
3. Nếu đã xác định credential có vấn đề, thực hiện password reset/rotation an toàn; xem xét revoke session/token khi có nghi ngờ compromise. Khôi phục MFA theo quy trình riêng.
4. Hạn chế thử đăng nhập lặp; để **người dùng tự đăng nhập** qua kênh được phép, tránh việc người hỗ trợ biết mật khẩu. Xác nhận luồng MFA/Conditional Access thực sự đạt.
5. Đối chiếu account và entitlement tại ứng dụng đích theo **desired state**. Đăng nhập được ở IdP chưa bảo đảm có đúng quyền dữ liệu; không mở quyền rộng để kiểm thử.
6. Theo dõi lockout event mới và nguồn retry trong cửa sổ phù hợp lịch tác vụ; nếu account tái khóa, quay lại điều tra nguyên nhân.
7. Ghi audit event, người thực hiện, thời điểm, kết quả đăng nhập hợp lệ, tình trạng quyền và các ngoại lệ còn mở. Chỉ đóng ticket khi điều kiện nghiệm thu đã đạt.

### Điều kiện trước Unlock

| Kiểm tra | Quyết định |
|---|---|
| Chủ thể và requester đã xác minh? | Chưa → giữ ticket, tiếp tục proofing |
| Trạng thái HR/JML cho phép login? | Không → không Unlock |
| Có hold hoặc tấn công chưa xử lý? | Có → chuyển SOC/owner |
| Đã biết nguồn khóa và lý do? | Chưa → tiếp tục tra log |
| Có retry từ client gây lỗi? | Có → sửa nguồn trước hoặc áp biện pháp kiểm soát |
| Đã có approval/phân quyền phù hợp? | Chưa → không thao tác |

### Kiểm chứng ba lớp

| Lớp | Tín hiệu xác nhận | Giới hạn |
|---|---|---|
| **IdP/directory** | Lockout state đã được xử lý, sign-in hợp lệ thành công | Không chứng minh tài khoản đích và role đã đúng |
| **Ứng dụng** | Tạo phiên và thực hiện hành động được phép | Không chứng minh phiên/token cũ đã thu hồi sau incident |
| **Giám sát** | Không có lockout mới từ nguồn lỗi trong cửa sổ hợp lý | Vẫn cần kiểm tra nếu job chỉ chạy theo lịch dài |

## 10. Ảnh hưởng của Joiner–Mover–Leaver đến quyết định mở khóa

### 10.1. Joiner

Người mới chưa tới ngày bắt đầu, chưa xác minh identity, chưa đăng ký MFA hoặc chưa được cấp tài khoản có thể nhận thông báo chung “Account blocked”. Thao tác đúng là đối chiếu **nguồn HR/sponsor → ngày hiệu lực → IdP active → MFA → SCIM user → role RBAC/ABAC**. Không kích hoạt trước thời điểm được phép. Nếu IdP hoạt động nhưng SCIM chưa provision, sửa connector và kiểm chứng app thay vì reset mật khẩu.

### 10.2. Mover

Khi đổi bộ phận, người dùng có thể mất role cũ, được cấp role mới hoặc chịu điều kiện ABAC/MFA khác. Một thông báo “Access denied” sau chuyển vai trò có thể là kết quả **thu hồi quyền đúng chính sách**, không phải lockout. Đánh giá delta quyền cũ cần gỡ và quyền mới được phê duyệt, đồng thời kiểm tra SoD và session cũ. Không cấp lại nhóm cũ chỉ để làm thông báo biến mất: hành động đó tạo **quyền truy cập tồn dư**.

### 10.3. Leaver và Suspended

Với người nghỉ việc, nhà thầu hết hạn hoặc tài khoản bị đình chỉ, login bị từ chối thường là mục tiêu bảo mật. Không đổi trạng thái IdP/SCIM từ inactive sang active chỉ dựa trên yêu cầu hỗ trợ. Nếu người cũ cần bàn giao dữ liệu, dùng quy trình ủy quyền người nhận phù hợp, không tái kích hoạt danh tính Leaver. Nếu HR ghi nhầm trạng thái, nguồn chủ quản phải sửa dữ liệu và tạo **sự kiện reactivation có phê duyệt**, sau đó review quyền hiện hành thay vì khôi phục toàn bộ grant lịch sử.

### 10.4. SCIM và khóa tại ứng dụng

SCIM có thể cập nhật trạng thái người dùng ở ứng dụng đích, ví dụ trường **active = false** khi deprovision. Nếu sửa tay tại ứng dụng nhưng desired state ở nguồn IAM vẫn inactive, connector có thể đồng bộ lại. Vì vậy phải giải quyết **nguồn có thẩm quyền và sự sai lệch actual–desired**, rồi xác minh ở cả IdP và ứng dụng. SCIM deactivation không được mặc định phân loại là account lockout do mật khẩu.

## 11. Trường hợp đặc biệt: tài khoản đặc quyền và service account

### 11.1. Tài khoản quản trị/PAM

Thất bại đăng nhập vào cloud admin, directory administrator, tài khoản PAM hoặc hệ thống sản xuất là tín hiệu rủi ro cao. Xác minh danh tính mạnh và kiểm tra sign-in history, nguồn bất thường, quyền đặc quyền, hoạt động gần đây. Nếu có nghi compromise, phối hợp SOC, giữ log, revoke session/rotate credential phù hợp và chỉ mở khi được chấp thuận.

**Break-glass** chỉ dùng theo quy trình khẩn cấp định sẵn: người có thẩm quyền, xác thực an toàn, logging, giới hạn thời gian, hậu kiểm và rotation khi cần. Không sử dụng tài khoản khẩn cấp để bỏ qua việc xác minh người dùng thông thường.

### 11.2. Service account và workload identity

Service account có thể bị khóa do job chạy theo lịch, nhiều instance dùng cùng secret, rotation thiếu đồng bộ hoặc script lưu mật khẩu cũ. Việc mở khóa mù quáng gây lặp lỗi và có thể gián đoạn dịch vụ.

1. Tìm **owner kỹ thuật và owner nghiệp vụ**, dependency, lịch job, nguồn sign-in lỗi và mức ảnh hưởng.
2. Kiểm tra secret version/rotation trong vault, cấu hình client, credential cache; tuyệt đối không in secret ra log/ticket.
3. Phối hợp owner dừng hoặc điều chỉnh retry theo quy trình change/incident, cập nhật secret trên toàn bộ instance.
4. Mở khóa theo phê duyệt, xác minh workload chạy bằng **least privilege**, không tăng quyền IAM chỉ để vượt lỗi.
5. Giám sát qua các chu kỳ job và xem xét chuyển sang **managed identity**, workload federation hoặc short-lived credentials khi khả thi.

Khi nhân viên là owner cũ của service account nghỉ việc, phải chuyển owner và đánh giá lại các grant/secret. Không tự ý xóa service account còn dependency production; nhưng cũng không giữ quyền cá nhân hoặc khóa cá nhân của Leaver.

## 12. Lockout storm: nhiều tài khoản bị khóa cùng lúc

**Lockout storm** có thể do password spraying, đồng bộ mật khẩu sai, client lỗi, policy thay đổi, connector cấu hình sai hoặc outage của directory. Runbook cần giải quyết ở quy mô incident:

1. Đếm số **subject khác nhau** bị ảnh hưởng theo cửa sổ thời gian, client, IP/network, ứng dụng, user có đặc quyền và sự kiện triển khai gần nhất.
2. Phân loại sự cố bảo mật hoặc vận hành; cả hai nhóm có thể cần phối hợp. Chọn incident commander và người chịu trách nhiệm theo mức ảnh hưởng.
3. Duy trì bảo vệ chống thử sai; cách ly client gây retry có kiểm soát hoặc triển khai containment theo SOC.
4. Tránh Unlock hàng loạt khi chưa sửa nguyên nhân, nhất là khi trộn lẫn tài khoản Active và Leaver.
5. Khôi phục theo thứ tự ưu tiên hệ thống trọng yếu, quan sát sign-in success, lockout mới, MFA failures, session và lỗi ứng dụng.
6. Ghi root cause, phạm vi ảnh hưởng, thời điểm khắc phục, cập nhật monitoring/rule và owner để tránh tái diễn.

### Tình huống: job dùng secret cũ trên nhiều server

Vault đã rotate secret của một service account nhưng ba server vẫn chạy cấu hình cũ và thử xác thực mỗi 15 phút. Người vận hành chỉ Unlock thì account sẽ sớm tái khóa. Quy trình hợp lý là **xác định nguồn lỗi qua log → cập nhật phiên bản secret ở các instance → chấm dứt retry sai → xác minh job/đặc quyền → Unlock → giám sát hơn một chu kỳ job**.

### Tình huống: password spraying

Hàng trăm nhân viên đồng loạt bị khóa, log ghi các lần thử mật khẩu sai tới nhiều account trong thời gian ngắn từ nhiều nguồn. Đây có thể là chiến dịch password spraying. Ưu tiên SOC xác định phạm vi, xem có đăng nhập thành công đáng ngờ hay không, bảo vệ log và containment trước khi khôi phục có kiểm soát.

## 13. Pseudocode cho điều phối ticket

Đây là **pseudocode**, không phải API hay lệnh có thể chạy trực tiếp trên IdP. Mỗi nền tảng có cơ chế khóa, permission và event semantics khác nhau.

~~~text
handle_lockout(ticket):
    subject = resolve_immutable_subject_id(ticket)
    verify_requester_identity(subject, ticket)

    lifecycle = read_authoritative_lifecycle(subject)
    if lifecycle not in ["ACTIVE", "APPROVED_REACTIVATION"]:
        record(ticket, "BLOCKED_BY_LIFECYCLE")
        route_to_hr_or_security_owner(ticket)
        return

    evidence = read_auth_events(subject, ticket.time_window)
    cause = classify_failure(evidence)

    if cause.suspicious or has_security_hold(subject):
        escalate_to_soc(ticket, evidence.references_only)
        record(ticket, "SECURITY_REVIEW_REQUIRED")
        return

    if cause.category in ["AUTHORIZATION", "PROVISIONING", "SSO"]:
        route_to_owner(ticket, cause.category)
        return

    if cause.category != "ACCOUNT_LOCKOUT":
        follow_matching_recovery_policy(ticket, cause)
        return

    remediate_bad_retry_source(subject, cause)
    confirm_unlock_authorization(subject, ticket)
    unlock_at_authoritative_source(subject, cause.source)

    verify_user_sign_in_without_collecting_secrets()
    verify_required_application_entitlements()
    monitor_for_repeat_lockout()
    record_audit_and_close_or_escalate(ticket)
~~~

Khi nhiều sự kiện xảy ra đồng thời phải chống race condition. Một yêu cầu Unlock cũ không được kích hoạt lại account vừa trở thành Leaver; workflow cần kiểm tra phiên bản/trạng thái JML **ngay trước thao tác** và bảo đảm lệnh deprovision ưu tiên theo chính sách. API timeout cũng không có nghĩa thao tác thất bại: phải đọc trạng thái đích trước khi retry idempotent.

## 14. Các lỗi chẩn đoán và khôi phục thường gặp

| Sai lầm | Hậu quả | Cách sửa |
|---|---|---|
| Unlock ngay khi người dùng nhắn “tôi bị khóa” | Có thể bật lại Leaver hoặc account bị security hold | Kiểm tra identity proofing, JML và Security |
| Chỉ kiểm tra IdP, bỏ qua app | Người dùng vẫn bị khóa cục bộ hoặc thiếu role | Đối chiếu cả nguồn xác thực lẫn ứng dụng |
| Reset mật khẩu khi IdP đã sign-in success | Không sửa lỗi SSO/authorization | Điều tra claim, SCIM, RBAC/ABAC, policy |
| Nâng ngưỡng lockout/tắt MFA để giảm ticket | Làm suy yếu kiểm soát chống tấn công | Sửa root cause, rate-limit thích hợp và quy trình recovery |
| Mở khóa lặp cho service account | Gây lockout định kỳ và nguy cơ gián đoạn | Dò retry, cập nhật secret và theo dõi job |
| Chỉ dựa vào IP để đánh giá | Dễ nhận nhầm hợp lệ/tấn công | Tổng hợp nhiều tín hiệu rủi ro và lịch sử |
| Unlock rồi đóng ticket ngay | Không phát hiện tái khóa hoặc entitlement sai | Kiểm tra sign-in, actual access và cửa sổ giám sát |
| Cấp lại role cũ cho Mover | Tạo quyền truy cập tồn dư | Tôn trọng desired state và approval quyền |

Trong hệ thống **hybrid directory**, nguồn lockout thực tế có thể là directory khác nơi người vận hành thấy giao diện cloud. Phải xác định authentication source, xem replication/propagation và log ở hệ thống ra quyết định; tránh thao tác ngẫu nhiên ở nhiều console.

## 15. Giám sát, đo lường và bằng chứng kiểm toán

### 15.1. Chỉ số nên theo dõi

| Chỉ số | Ý nghĩa |
|---|---|
| **Lockout rate** | Số tài khoản khác nhau bị khóa mỗi khoảng thời gian, phân nhóm người dùng/service/admin |
| **Repeat lockout rate** | Tỷ lệ khóa lặp trong khoảng giám sát sau khi xử lý; cho thấy root cause chưa được giải quyết |
| **Time to diagnose / restore** | Thời gian từ ticket đến lúc xác định nguyên nhân và khôi phục đúng chính sách |
| **Security escalation ratio** | Tỷ lệ ticket liên quan nghi tấn công hoặc account nhạy cảm cần SOC |
| **Client/source distribution** | Nguồn gây khóa phổ biến: browser, VPN, directory, agent, job, app local |
| **JML conflict incidents** | Số yêu cầu mở khóa xung đột trạng thái Pending, Suspended hoặc Leaver |
| **Unresolved retry backlog** | Số client/connector đang tạo lỗi xác thực và thời gian tồn tại |

SLO/SLA cần được tổ chức tự xác định theo mức rủi ro. Ví dụ **P0** khi nghi tấn công vào account đặc quyền hoặc nhiều người dùng, **P1** khi service identity làm gián đoạn hệ thống trọng yếu và **P2/P3** cho trường hợp đơn lẻ theo ảnh hưởng. Đây là minh họa phân loại, không phải ngưỡng hay SLA tiêu chuẩn áp dụng mọi nơi.

### 15.2. Audit record mẫu

~~~yaml
ticket_id: IAM-LOCKOUT-EXAMPLE-042
correlation_id: corr-example-310
subject_id: person-1042
event_type: ACCOUNT_LOCKOUT
source_system: corporate-idp
lifecycle_state_at_check: ACTIVE
identity_verification_ref: verification-112
sign_in_evidence_refs:
  - signin-081
  - signin-082
root_cause_category: STALE_CLIENT_CREDENTIAL
remediation:
  action: update-client-credential-and-unlock
  operator_ref: iam-operator-07
  approval_ref: approval-19
  executed_at: "2026-11-23T09:23:00+07:00"
verification:
  sign_in: SUCCESS
  expected_application_access: VERIFIED
  repeat_lockout_observed: false
  evidence_ref: signin-085
case_status: CLOSED
~~~

Các giá trị là **giả lập**. Bằng chứng cần liên kết được **ticket → subject/identity proofing → trạng thái JML → sự kiện log và chẩn đoán → phê duyệt → hành động → kiểm chứng → quyết định đóng hoặc chuyển SOC**. Giới hạn quyền truy cập audit, thời hạn lưu và dữ liệu cá nhân theo chính sách. Không đưa password, OTP, token hay secret vào hồ sơ.

## 16. Checklist nghiệm thu cho Service Desk và IAM

| Giai đoạn | Điều kiện cần đạt |
|---|---|
| **Tiếp nhận** | Ticket, subject ID, ứng dụng, thời điểm và mô tả lỗi đầy đủ |
| **Xác minh** | Requester được identity proofing theo chính sách |
| **JML** | Account được phép login, không có hold chưa xử lý |
| **Điều tra** | Phân loại đúng authentication/authorization/provisioning; xác định nguồn khóa |
| **Security** | Đánh giá compromise/spraying, chuyển SOC khi cần |
| **Nguyên nhân** | Nguồn thử sai đã sửa hoặc được kiểm soát |
| **Phê duyệt** | Người thao tác có thẩm quyền, có record |
| **Khôi phục** | Thao tác tại authoritative source đúng subject |
| **Kiểm chứng** | Sign-in hợp lệ và quyền RBAC/ABAC tại ứng dụng đích đúng |
| **Đóng ticket** | Không tái khóa trong khoảng giám sát thích hợp; audit đầy đủ |

Không đánh dấu **Resolved** chỉ dựa trên thông báo “Unlocked” ở console khi người dùng vẫn thất bại hoặc job vẫn thử sai.

## 17. Tình huống luyện tập

### Tình huống A — Joiner bị chặn trước ngày bắt đầu

Một nhân viên ngày mai mới bắt đầu công việc được gửi lời mời app hôm nay, nhận thông báo “Account blocked”. HRIS đang ở trạng thái Pending. **Hướng xử lý:** xác minh ngày hiệu lực và quy trình kích hoạt. Không Unlock trước thời điểm cho phép; nếu dữ liệu HR sai, sửa tại nguồn chủ quản rồi chạy lại JML.

### Tình huống B — Mover mất quyền ứng dụng

Một nhân viên chuyển từ Support sang Finance. IdP sign-in thành công, portal Finance báo “Access denied” vì role mới chưa được phê duyệt. **Hướng xử lý:** đưa qua access request, xác minh SoD và quyền Finance. Không reset mật khẩu hay khôi phục quyền Support cũ.

### Tình huống C — Leaver yêu cầu đăng nhập để lấy tài liệu

Một nhà thầu hết hạn hợp đồng nói account bị khóa và cần tải file. SCIM đã đặt account ứng dụng inactive. **Hướng xử lý:** giữ nguyên trạng thái Leaver; chuyển yêu cầu sang quy trình bàn giao dữ liệu cho người có thẩm quyền.

### Tình huống D — Service account bị khóa mỗi 15 phút

Log cho thấy một server vẫn dùng secret cũ trong scheduled task. **Hướng xử lý:** sửa credential trong vault và cấu hình client, dừng retry gây lỗi, kiểm tra phụ thuộc rồi Unlock; chỉ đóng sau khi quan sát các chu kỳ job.

### Tình huống E — Cảnh báo spraying cùng lúc nhiều nhân viên bị khóa

Nhiều tài khoản bị thử sai từ các nguồn bất thường; một nhân viên khẳng định mình chỉ quên mật khẩu. **Hướng xử lý:** SOC đánh giá phạm vi và containment trước, xác minh từng chủ thể, xử lý credential/session có rủi ro rồi mới mở khóa có kiểm soát.

## 18. Kết luận vận hành

Xử lý account lockout đúng nghĩa phải **xác minh người yêu cầu, tôn trọng trạng thái JML, xác định chính xác nguồn lỗi, loại bỏ nguyên nhân retry, đánh giá dấu hiệu tấn công, khôi phục theo chính sách và xác minh quyền truy cập hiệu lực**. Nút Unlock chỉ là một thao tác trong chuỗi kiểm soát đó. Audit và giám sát sau xử lý giúp bảo đảm người hợp lệ lấy lại truy cập, trong khi tài khoản không còn hợp lệ và những quyền truy cập tồn dư vẫn bị chặn.
