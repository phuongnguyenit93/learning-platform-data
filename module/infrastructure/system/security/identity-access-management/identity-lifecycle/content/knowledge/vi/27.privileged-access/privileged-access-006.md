# Session recording – ghi nhận phiên truy cập đặc quyền trong IAM lifecycle

## Mục tiêu học tập

Sau bài học, người học có thể:

- Giải thích **session recording** trong **Privileged Access Management (PAM)**: mục tiêu, dữ liệu được ghi, giới hạn của bằng chứng và khác biệt với **session monitoring, audit logging, command logging, screen capture**.
- Mô tả kiến trúc dùng **PAM gateway/proxy, bastion hoặc jump host**, xác thực IdP/SSO, chính sách **JIT/JEA**, credential vault, kết nối tới hệ thống đích và kho bản ghi được bảo vệ.
- Lựa chọn phương án ghi nhận phù hợp với **SSH, RDP, web admin, database, container/Kubernetes và cloud control plane**, không giả định mọi giao thức đều tạo ra video có thể phát lại giống nhau.
- Thiết kế gắn **danh tính người thực, phiên đặc quyền, yêu cầu phê duyệt, hệ thống đích, quyền, thời điểm và sự kiện bảo mật** bằng mã tương quan có thể kiểm toán.
- Phân tích yêu cầu **bảo mật, tính toàn vẹn, khả dụng, retention, quyền riêng tư, phân quyền xem bản ghi, chống sửa/xóa** và các giới hạn chứng cứ của dữ liệu ghi hình.
- Thiết kế chính sách xử lý khi **recording thất bại, proxy bị bypass, phiên ngắt kết nối, break-glass, quyền bị thu hồi giữa phiên** hoặc bản ghi chứa thông tin bí mật.
- Liên hệ ghi phiên với **Joiner–Mover–Leaver (JML)**, **IdP/SSO, SCIM, RBAC/ABAC, tài khoản dịch vụ, reconciliation, incident response** và giảm **quyền truy cập tồn dư**.
- Xây dựng quy trình vận hành, chỉ số, checklist và bộ kiểm thử end-to-end cho hệ thống session recording.

## 1. Session recording là gì?

**Session recording** là việc hệ thống **thu thập và lưu trữ có kiểm soát hoạt động diễn ra trong một phiên truy cập**, đặc biệt là phiên có **quyền đặc biệt** như quản trị máy chủ, sửa cơ sở dữ liệu production, thay đổi cấu hình mạng, triển khai hệ thống hoặc cấp quyền IAM.

Một **privileged session** thường chứa các sự kiện nhạy cảm hơn phiên người dùng thông thường:

- Quản trị viên dùng SSH vào máy chủ production.
- DBA mở kết nối tới database và chạy câu lệnh thay đổi dữ liệu.
- Nhân viên vận hành đăng nhập qua RDP để sửa dịch vụ Windows.
- Kỹ sư dùng giao diện web để thay cấu hình cloud, IdP hoặc PAM.
- SRE dùng `kubectl exec` để kiểm tra ứng dụng trong container.
- Nhà thầu truy cập hệ thống của doanh nghiệp trong một khung thời gian được duyệt.

Session recording có thể lưu **dòng nhập/xuất terminal, hình ảnh màn hình, sự kiện tương tác, câu lệnh đã thực thi, metadata kết nối, event theo giao thức hoặc tập hợp nhiều loại dữ liệu**. Hình thức cụ thể phụ thuộc công cụ, giao thức, vị trí quan sát và chính sách.

**Ghi phiên không tự đồng nghĩa có video đầy đủ, cũng không tự bảo đảm mọi hành động được phát lại chính xác.** Một gateway SSH có thể lưu transcript theo byte; công cụ RDP có thể lưu khung hình; cloud audit có thể lưu API call mà không có video. Mỗi dạng có độ đầy đủ và khả năng điều tra khác nhau.

Trong module **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**, session recording là một kiểm soát bổ sung ở phần **Privileged access**: biết **ai** được cấp quyền sau Joiner, **quyền nào** đổi ở Mover, **đường truy cập nào** phải thu hồi ở Leaver, và **hành động nào thực sự diễn ra** trong thời gian quyền còn hiệu lực. Session recording **không thay thế** việc kiểm soát quyền hoặc thu hồi account.

### 1.1. Mục tiêu chính

| Mục tiêu | Câu hỏi mà bản ghi có thể hỗ trợ | Giới hạn |
| --- | --- | --- |
| **Accountability** | Ai đã dùng phiên đặc quyền, vào đích nào? | Phải liên kết được danh tính con người với phiên, không chỉ shared account |
| **Incident investigation** | Trước sự cố, người dùng thao tác gì? | Một số hành động ngoài kênh ghi nhận có thể không xuất hiện |
| **Compliance evidence** | Quy trình truy cập có để lại chứng cứ phù hợp không? | Retention, tính toàn vẹn và phạm vi phải đúng |
| **Deterrence** | Người được cấp quyền biết hoạt động đặc quyền có thể được xem lại? | Không dựa vào ghi hình thay cho hạn chế quyền |
| **Operational review** | Một thay đổi production xảy ra theo quy trình nào? | Cần ghép ticket, change, log đích và thời điểm |
| **Training / postmortem** | Có thể phân tích chuỗi thao tác gây lỗi không? | Bản ghi có thể chứa bí mật, không tự do chia sẻ |
| **Threat detection** | Có dấu hiệu lệnh nguy hiểm, bất thường hoặc exfiltration không? | Phân tích realtime phụ thuộc khả năng sản phẩm |

## 2. Phân biệt recording, monitoring, logging và enforcement

| Khái niệm | Câu hỏi chính | Ví dụ | Không đảm nhiệm |
| --- | --- | --- | --- |
| **Session recording** | Phiên đã có những tương tác gì? | Transcript SSH, screen recording RDP | Tự ngăn mọi thao tác bị cấm |
| **Session monitoring** | Phiên hiện đang làm gì, có bất thường không? | Live viewer, command alert | Không nhất thiết lưu video |
| **Session control** | Cho phép, chặn, ngắt, hạn chế phiên như thế nào? | Idle timeout, terminate, block clipboard | Không tự giải thích toàn bộ ngữ cảnh |
| **Authentication** | Ai vừa chứng minh danh tính? | IdP + MFA/passkey | Không tự cấp quyền admin |
| **Authorization/PEP** | Actor có được thao tác với tài nguyên không? | JIT, RBAC/ABAC, command policy | Không tự tạo bằng chứng thao tác |
| **Audit/event log** | Sự kiện cấu trúc nào đã xảy ra? | API call, process execution, IAM policy change | Có thể không ghi hình/đầu ra |
| **Endpoint detection / system logs** | Tiến trình, kết nối và sự kiện OS nào xảy ra? | Process tree, Windows Security Event, Linux audit | Không nhất thiết xác định phiên PAM gây ra |
| **Credential vault** | Bí mật/credential được cấp và quay vòng ra sao? | Check-out/check-in, rotation | Không tự theo dõi nội dung phiên |
| **Reconciliation** | Trạng thái quyền và kiểm soát thực tế có đúng mong muốn? | Quyền Leaver còn tồn dư, phiên không được ghi | Không phải video hay transcript |

**Session recording là kiểm soát quan sát và bằng chứng.** Nếu chính sách cấm xóa dữ liệu nhưng gateway chỉ ghi lại thao tác xóa rồi vẫn cho chạy, việc ghi được video **không biến hành động đó thành hợp lệ**.

### 2.1. Ghi càng nhiều không đồng nghĩa càng an toàn

Bản ghi có thể thu cả **mật khẩu, token, khóa, thông tin khách hàng, dữ liệu y tế, số tài khoản hoặc nội dung có tính riêng tư**. Ghi không giới hạn làm tăng khả năng điều tra nhưng đồng thời tạo **kho dữ liệu nhạy cảm mới**. Cần chọn phạm vi, loại dữ liệu và retention theo rủi ro, mục đích sử dụng và chính sách pháp lý hiện hành.

## 3. Các loại phiên đặc quyền cần xem xét

Không chỉ phiên SSH của root mới là privileged session.

| Loại phiên | Ví dụ hành động | Cách ghi thường gặp |
| --- | --- | --- |
| **SSH/terminal** | Sửa config, chạy shell, deploy, quản lý user | Terminal stream, command/output events, TTY recording |
| **RDP/remote desktop** | Quản trị Windows, đổi policy, chạy tool GUI | Screen frames + input/session metadata |
| **Web privileged console** | IAM admin, cloud console, SaaS admin | Web proxy/screen replay hoặc audit API/browser events |
| **Database** | `ALTER`, `DELETE`, quản lý grants | Proxy query log, DB native audit, recording công cụ client |
| **Kubernetes/containers** | `kubectl exec`, `port-forward`, đổi workloads | Kubernetes audit + terminal recording + cluster controls |
| **Network devices** | SSH/CLI vào router, firewall | Command transcript + change log |
| **Privileged file transfer** | Upload script, lấy bản sao dữ liệu | File transfer metadata, DLP/hash và kiểm soát luồng |
| **Cloud CLI/API** | Gán role, tạo access key, đổi policy | Cloud control-plane audit, proxy/session metadata |
| **Automation/service principal** | Pipeline thay hạ tầng | Job/run logs, API events, workload identity, artifact provenance |

**Video phát lại có ích nhất với giao diện tương tác.** Đối với hoạt động API không có UI, log cấu trúc và provenance thường quan trọng hơn “quay màn hình” một tác vụ tự động.

### 3.1. Đối tượng và mức bảo vệ theo rủi ro

Những tài nguyên thường được ưu tiên ghi phiên:

- Domain controller, IdP, PAM, credential vault và hệ IAM.
- Production database và hệ chứa dữ liệu nhạy cảm.
- Cloud organization/account, network core, firewall và secrets management.
- Hệ thống thanh toán, tài chính và dữ liệu chịu yêu cầu kiểm soát chặt.
- Môi trường nhà thầu hoặc nhà cung cấp có quyền quản trị.
- Những thao tác đặc quyền có nguy cơ làm gián đoạn hoặc xóa lượng lớn dữ liệu.

Không mặc định rằng chỉ có **nhóm Domain Admin** cần ghi. Một quyền `role.grant` trên IdP hoặc `secret.read` tại cloud cũng có thể có tác động rất lớn.

## 4. Kiến trúc PAM session recording điển hình

Một triển khai có thể đưa đường truy cập đặc quyền qua **PAM gateway/proxy** hoặc **bastion** để kiểm chứng danh tính, scope và thu dữ liệu phiên.

~~~mermaid
flowchart LR
    U["Admin / nhà thầu"] --> IDP["IdP / SSO / MFA"]
    U --> PORTAL["PAM portal / access request"]
    IDP --> PORTAL
    IGA["HRIS / IGA / JML"] -->|"Account, owner, eligibility"| PORTAL
    PORTAL --> AUTHZ["PDP / JIT approval"]
    AUTHZ --> GATE["PAM gateway / Session PEP"]
    VAULT["Credential vault / broker"] -->|"Credential ngắn hạn hoặc injection"| GATE
    GATE -->|"SSH / RDP / DB / web"| TARGET["Target system"]
    GATE --> REC["Recording collector"]
    REC --> STORE["Protected evidence storage"]
    TARGET --> LOG["Target audit logs"]
    STORE --> SIEM["Audit / SIEM / investigation"]
    LOG --> SIEM
    AUTHZ --> SIEM
~~~

Đây là **kiến trúc logic**, không phải mô tả bắt buộc của một sản phẩm. Một số hệ ghi ở **endpoint agent**, **host service**, **terminal server** hoặc cloud provider thay vì proxy. Một số kết hợp nhiều nguồn.

### 4.1. Các ranh giới tin cậy

1. **Người dùng → PAM:** xác thực danh tính, chống chiếm phiên, đánh giá JML, MFA/step-up và phê duyệt.
2. **PAM → hệ đích:** cấp credential/quyền phù hợp, hạn chế đường vào trực tiếp.
3. **Hệ đích → recorder:** thu hoạt động mà gateway/agent thật sự quan sát được.
4. **Recorder → storage:** vận chuyển an toàn, kiểm tính toàn vẹn, mã hóa.
5. **Investigator → replay:** quyền xem, phê duyệt, tra cứu và audit người xem.
6. **PAM/IdP/IGA → SIEM:** ghép danh tính, ticket, phiên, policy, trạng thái và sự kiện.

**Nếu admin vẫn có SSH trực tiếp tới target ngoài gateway, bản ghi ở gateway không thể phủ toàn bộ đường truy cập.** Kiểm soát mạng và credential phải khiến đường đi được quản trị là đường đi thực tế.

## 5. Luồng phiên đặc quyền từ yêu cầu tới đóng phiên

### 5.1. Trình tự chuẩn

~~~mermaid
sequenceDiagram
    autonumber
    actor A as Admin
    participant IDP as IdP / SSO
    participant PAM as PAM / PEP
    participant APPROVAL as IGA / Approval
    participant TARGET as Target
    participant STORE as Recorder / Evidence Store

    A->>PAM: Request privileged access
    PAM->>IDP: Xác thực + kiểm assurance
    IDP-->>PAM: Trusted identity/session
    PAM->>APPROVAL: Eligibility, JML, ticket, scope, expiry
    APPROVAL-->>PAM: Approved / denied
    PAM->>PAM: Tạo sessionId, policy, metadata
    PAM->>STORE: Khởi tạo recording & health check
    alt Recording và authorization đáp ứng policy
        PAM->>TARGET: Kết nối qua broker/credential
        A->>PAM: Thao tác đặc quyền
        PAM->>STORE: Truyền stream/events theo policy
        PAM->>TARGET: Chuyển thao tác được phép
        TARGET-->>PAM: Output/results
        PAM-->>A: Output
        PAM->>STORE: Finalize, hash/manifest và timestamps
        PAM->>APPROVAL: Đóng grant / cập nhật trạng thái
    else Không đủ điều kiện
        PAM-->>A: Từ chối hoặc break-glass đã được duyệt
    end
~~~

Sơ đồ đơn giản hóa một số công việc xảy ra song song. Hệ thống thật cần xử lý mất mạng, disconnect/reconnect, crash, idle timeout và sự kiện quyền đổi trong khi phiên đang chạy.

### 5.2. Những mốc không nên trộn lẫn

| Mốc | Ý nghĩa |
| --- | --- |
| **requestedAt** | Người dùng xin quyền truy cập |
| **approvedAt** | Chủ sở hữu/phê duyệt xác nhận phạm vi |
| **grantEffectiveAt** | Quyền JIT bắt đầu có giá trị |
| **recordingStartedAt** | Recorder thực sự sẵn sàng nhận dữ liệu |
| **targetConnectedAt** | Kết nối tới hệ đích được lập |
| **lastActivityAt** | Hoạt động được quan sát gần nhất |
| **disconnectedAt** | Mạng hoặc client bị ngắt |
| **targetSessionEndedAt** | Phiên trên target không còn dùng được |
| **recordingFinalizedAt** | Bản ghi được đóng, lưu và kiểm tra toàn vẹn |
| **verifiedAt** | Hệ thống đối soát xác nhận có bản ghi và đúng scope |

Đóng cửa sổ trình duyệt PAM **không chắc** đã kết thúc một tiến trình nền, tunnel hay session trên target. Cần định nghĩa quy tắc đóng và xác minh độc lập.

## 6. Kiểu dữ liệu trong bản ghi phiên

Không có một định dạng duy nhất cho mọi hệ thống. Dữ liệu có thể được chia:

| Dạng dữ liệu | Nội dung | Công dụng | Rủi ro |
| --- | --- | --- | --- |
| **Session metadata** | Actor, target, protocol, policy, sessionId, thời gian | Truy vết và liên kết | Sai attribution nếu dùng account chia sẻ |
| **Terminal transcript** | Dòng nhập/xuất của SSH/TTY | Tìm lệnh và xem kết quả | Secret có thể xuất hiện ở terminal |
| **Screen recording** | Khung hình hoặc video GUI | Phát lại luồng tương tác | Có thể ghi PII/credential trên màn hình |
| **Input/command events** | Keystroke, command boundary, event | Tìm kiếm và alert | Phụ thuộc mức quan sát, có thể hiểu sai |
| **Database query audit** | Query và context DB | Điều tra thay đổi dữ liệu | Query có thể chứa dữ liệu nhạy cảm |
| **File transfer metadata** | Tên file, hướng, size, hash | Phát hiện exfiltration | Không phải nội dung file hoặc toàn bộ quyền |
| **Target-native audit** | OS process, DB DDL/DML, cloud API | Xác định hiệu ứng hệ thống | Có thể thiếu thao tác theo GUI |
| **Integrity manifest** | Chunk IDs, hash, timestamps, state | Phát hiện sửa/xóa bản ghi | Chỉ hữu ích khi metadata được bảo vệ |

### 6.1. Screen replay khác command replay

**Screen replay** cho thấy khung hình người xem đã/được proxy hiển thị tại thời điểm đó. Nó không chứng minh toàn bộ thay đổi ở backend nếu thao tác có hiệu ứng không hiện trên màn hình.

**Command replay/transcript** có thể thể hiện chuỗi ký tự và phản hồi terminal, nhưng không nhất thiết ghi chính xác tất cả tiến trình sinh ra do shell script, subprocess hoặc API khác.

**Audit API/OS** có thể chứng minh một lời gọi hoặc thay đổi trạng thái mà recording giao diện không nhìn thấy. Với hệ trọng yếu, nên **tương quan các nguồn**, thay vì chọn một nguồn làm “chân lý tuyệt đối”.

## 7. Ghi phiên SSH và terminal

Một session qua SSH proxy có thể lưu dòng TTY, lời gọi shell hoặc command input/output theo capability. Mỗi phương án có khoảng trống:

- **Interactive shell:** lệnh, output, terminal control sequences có thể được thu qua PTY.
- **Non-interactive SSH command:** nếu proxy chỉ hỗ trợ interactive PTY, một lệnh chạy trực tiếp có thể không có transcript như mong đợi.
- **SCP/SFTP:** thường cần chính sách file-transfer riêng, không trông chờ video terminal.
- **SSH port forwarding/tunnels:** có thể tạo kênh dữ liệu mà recorder terminal không quan sát nội dung.
- **Multiplexed sessions:** nhiều channel trong một kết nối SSH; cần nhận diện và ghi đúng từng channel.
- **Full-screen terminal apps:** ví dụ editor dùng terminal control codes, chỉ đọc dòng text có thể gây sai ý nghĩa; playback TTY cần xử lý terminal state.
- **SSH agent forwarding:** có thể đưa khả năng sử dụng credential ra target; phải giới hạn hoặc cấm theo rủi ro.

### 7.1. Command logging có ghi đủ không?

Giả sử:

~~~text
operator> ./deploy.sh
deploy.sh gọi:
  thay cấu hình dịch vụ
  chạy migration dữ liệu
  gửi API thay role
  restart nhiều ứng dụng
~~~

Recording thấy `./deploy.sh`, nhưng không nhất thiết thấy **từng lời gọi API hoặc side effect** của script. Nên ghép **process audit, CI/CD logs, DB audit và cloud control-plane events**.

### 7.2. Bảo vệ thông tin bí mật khi ghi terminal

Khi một người gõ mật khẩu vào lệnh hoặc shell in access token ra stdout, transcript có thể chứa nguyên secret. Một số công cụ có **masking/secret redaction** hoặc không lưu một số input fields, nhưng khả năng này **không được giả định luôn chính xác**.

Cần:

- Hạn chế hiển thị secret ngay từ workflow, dùng credential injection nếu phù hợp.
- Giảm việc người dùng nhìn/copy secret, ưu tiên credential ngắn hạn.
- Giới hạn quyền đọc transcript thô.
- Định nghĩa quy trình phát hiện và xử lý bản ghi đã lộ secret.
- Tránh cắt/chỉnh bản ghi âm thầm khiến mất chuỗi bằng chứng; nếu redaction, lưu provenance và quyền tách biệt.

## 8. Ghi phiên RDP và giao diện đồ họa

Với **RDP**, recorder có thể thu hình ảnh màn hình theo khung hình, sự kiện bàn phím/chuột, clipboard hoặc file transfer metadata tùy sản phẩm và chính sách.

### 8.1. Những gì video có thể cho thấy

- Admin mở bảng quản lý và thay cấu hình.
- Người dùng truy cập thư mục, xem file, khởi chạy công cụ.
- Popup, hộp thoại phê duyệt hoặc thông báo lỗi.
- Thứ tự tương tác GUI trước sự cố.

### 8.2. Những gì video có thể bỏ sót

- Lệnh nền/tiến trình không hiển thị.
- Trạng thái backend thay đổi ngoài màn hình.
- Nội dung clipboard hoặc file transfer nếu gateway không thu metadata tương ứng.
- Một số màn hình bảo mật, UAC/secure desktop, session switch hoặc tính năng đồ họa bị sản phẩm giới hạn.
- Hành động ở một RDP connection khác hoặc đường truy cập trực tiếp.
- Dữ liệu phát sinh khi recorder mất kết nối, rơi frame hoặc bị pause.

**Không khẳng định “RDP recording đầy đủ 100%” nếu chưa kiểm thử các tình huống thực tế** gồm multiple monitors, reconnect, clipboard, file redirection và đặc tính ứng dụng.

### 8.3. Độ phân giải và khả năng đọc lại

Một video rất nén có thể đủ quan sát thao tác nhưng không đọc được chi tiết tên file hoặc câu lệnh. Ngược lại, độ phân giải cao làm tăng dung lượng và dữ liệu nhạy cảm được lưu. Chọn cấu hình theo **mục đích điều tra, hiệu năng, bảo mật, dung lượng và retention**, rồi kiểm thử replay.

## 9. Ghi phiên web, database, cloud và container

### 9.1. Web admin console

Cloud/SaaS admin thường hoạt động qua HTTPS. Một công cụ có thể thu **browser activity** qua proxy, extension/agent hoặc ghi screen theo mô hình được chấp thuận. Tuy vậy:

- Nếu traffic được mã hóa đầu-cuối mà gateway không có khả năng quan sát hợp lệ, nó không thể tự đọc nội dung.
- Dynamic web app và session token có thể không dễ tái hiện thành video chuẩn.
- Console có thể gọi API nền không hiển thị với recorder.
- Hành vi dùng một browser/tab khác có thể nằm ngoài phạm vi ghi.

**Cloud audit logs và application audit** là nguồn bắt buộc cân nhắc để đối chiếu tác động của phiên web.

### 9.2. Database privileged session

DB proxy có thể ghi metadata và SQL statements; DB native audit có thể ghi DDL, DML, role/grant hoặc transaction outcome theo cấu hình.

Ví dụ:

~~~sql
-- Ví dụ lệnh cần kiểm soát và kiểm toán, không phải thao tác thực thi.
ALTER ROLE finance_reader NOLOGIN;

REVOKE SELECT ON payroll FROM finance_reader;
~~~

Ghi được câu lệnh **không đủ chứng minh transaction đã COMMIT thành công**; cần đối chiếu DB native logs và trạng thái thực.

Query có thể chứa thông tin khách hàng hoặc bí mật trong literal; log cần masking và quyền truy cập nghiêm ngặt. DDL, stored procedures và gọi qua ứng dụng có thể có side effect khác câu lệnh hiển thị.

### 9.3. Kubernetes và container

Một người có quyền `kubectl exec` có thể mở shell vào container. Session recording cần xác định:

- Ai được phép exec vào pod/namespace nào?
- Đường truy cập có qua gateway/agent/terminal được quản trị không?
- Kubernetes audit có ghi API request và identity không?
- Terminal output có được lưu, hoặc chỉ có event `pods/exec`?
- `kubectl cp`, `port-forward`, ephemeral containers hoặc API trực tiếp có nằm trong scope không?
- ServiceAccount token trong workload có thể bị lấy và dùng ngoài phiên không?

**Một Kubernetes API audit event thường không thay thế toàn bộ transcript nội dung shell.** Ngược lại, transcript không thay chứng cứ cluster audit về đối tượng đã đổi.

### 9.4. Cloud CLI và API-only automation

Một pipeline có thể dùng cloud API không hề có màn hình. Trong trường hợp này, thu:

- Workload principal, issuer/audience/token scope hoặc identity liên quan.
- Pipeline/job/run ID, artifact digest và approval.
- Cloud API audit log, resource ID, request/result, thời gian.
- Trạng thái quyền được cấp hoặc thu hồi.
- Hash của artifact/script đã thực thi nếu được phép và có ích.

Không cố “ghi video phiên API” bằng cách quay màn hình của một trình chạy tự động; cách đó có thể bỏ sót điều quan trọng và làm tăng dữ liệu nhạy cảm.

## 10. Liên kết danh tính thật với phiên dùng account đặc quyền

Một nguyên nhân quan trọng của session recording là **truy vết ai thực hiện thao tác**, đặc biệt khi hệ thống đích dùng account chia sẻ như `root`, `Administrator` hoặc `db_admin`.

### 10.1. Chuỗi attribution cần có

~~~text
Human identity (identityId)
  -> IdP authentication + assurance
  -> PAM access request / approval
  -> JIT grant and policy
  -> PAM sessionId
  -> Privileged target account / credential
  -> Target session / connection ID
  -> Recording / target audit events
~~~

Nếu bản ghi chỉ thể hiện `root` đăng nhập, không có liên kết được bảo vệ tới **người nào đã sử dụng root**, accountability vẫn yếu.

### 10.2. Thông tin nhận diện nên dùng

| Thành phần | Ví dụ | Lưu ý |
| --- | --- | --- |
| **Internal identityId** | `person-1042` | Bền vững và do identity registry quản lý |
| **IdP issuer + subject** | `(issuer, sub)` | Không dùng email làm khóa duy nhất |
| **PAM actor ID** | `pam-user-718` | Phải liên kết đúng identity |
| **PAM session ID** | `ps-20261123-8492` | Duy nhất trong scope, có thể gắn segment |
| **Access request ID** | `req-2146` | Bằng chứng yêu cầu và phê duyệt |
| **Approval ID** | `approval-1120` | Gắn đúng action, target, TTL |
| **Target account** | `root`, `svc-deploy` | Không đồng nghĩa người dùng thực |
| **Target resource ID** | `server-prod-07` | Tránh phụ thuộc hostname tái sử dụng |
| **Recording ID** | `rec-4842` | Tham chiếu bằng chứng được bảo vệ |

Một số nền tảng dùng cơ chế định danh khác; trọng tâm là **correlation có thể chứng minh, không tự nối bằng tên hiển thị hoặc email trùng**.

### 10.3. Shared account và credential checkout

Nếu PAM cho nhiều người **checkout cùng một mật khẩu trong thời gian chồng lấn**, chỉ có thời điểm checkout chưa đủ xác định ai thực hiện lệnh. Cần:

- Session độc lập gắn mỗi actor.
- Hạn chế hoặc ngăn đường đăng nhập ngoài PAM.
- Credential broker/injection hoặc rotation theo thiết kế.
- Ràng buộc phiên với hệ đích, IP/channel, session ID và event.
- Quy trình điều tra khi attribution không chắc chắn.

**Ghi phiên không tự sửa vấn đề shared credential.** Thiết kế nên ưu tiên privileged identity cá nhân hoặc broker có thể gắn attribution.

## 11. JIT, JEA và điều kiện cấp phiên ghi hình

**Just-in-Time (JIT) privileged access** giới hạn thời gian cấp quyền. **Just Enough Administration (JEA)** hoặc mô hình quyền tối thiểu theo lệnh/tác vụ giới hạn những gì người dùng được thao tác.

Ví dụ policy minh họa:

~~~text
PERMIT privileged_session.start WHEN
    identity.lifecycleStatus == ACTIVE
    AND identity.proofingSatisfied
    AND actor.hasApprovedEligibility("PROD_OPERATOR")
    AND accessRequest.target == "prod-server-07"
    AND accessRequest.ticketIsValid
    AND approval.isValidFor(actor, target, purpose)
    AND now BETWEEN grant.startsAt AND grant.expiresAt
    AND authentication.assuranceSatisfiesRequiredLevel
    AND sessionRecording.isHealthy
    AND targetAccess.mustUseManagedGateway
ELSE DENY
~~~

Đây là **mã giả**, không phải cú pháp một sản phẩm PAM hay PBAC. Những điều kiện phải đến từ nguồn đáng tin, không phải các trường do client tự điền.

### 11.1. JIT hết hạn khi phiên còn mở

Một lỗi phổ biến là cấp quyền 30 phút, nhưng session SSH/RDP vẫn tồn tại nhiều giờ sau khi grant hết hạn.

Cần xác định một trong các hành vi theo mức rủi ro:

- Chấm dứt phiên khi hết TTL.
- Chặn thao tác mới, yêu cầu gia hạn và phê duyệt lại.
- Thu hồi target credential hoặc session capability theo hỗ trợ sản phẩm.
- Cho hoàn tất một thao tác đang chạy trong phạm vi hẹp nếu chính sách cho phép, có audit và thời hạn tối đa.

**Hết TTL của grant không tự kill tiến trình trên target.** Session recording nên kết hợp session management và target telemetry để phát hiện đường truy cập còn sống.

### 11.2. Một phiên mới cần quyết định mới

Không tự áp approval của `prod-server-07` sang `prod-db-02` hoặc mở nhiều phiên cùng lúc ngoài hạn mức nếu policy không cho phép. Mọi phiên phải gắn với action/resource/scope/TTL cụ thể.

## 12. Step-up, phê duyệt và Segregation of Duties

Các phiên đặc quyền có thể yêu cầu:

- Xác thực mới hoặc MFA đủ assurance theo IdP/PAM contract.
- Một **business justification** hoặc change/incident ticket còn hiệu lực.
- Phê duyệt bởi đúng owner hoặc người được ủy quyền.
- **Segregation of Duties (SoD)**: người yêu cầu không tự phê duyệt quyền của mình khi policy cấm.
- Điều kiện thiết bị, mạng, risk score và time window.
- Có health check của recorder và lưu bằng chứng.
- Ghi rõ nhu cầu thao tác, scope và quy trình hoàn tất.

### 12.1. Approval không thay thế target authorization

Một ticket được phê duyệt để sửa service A không cho quyền xóa database B. PAM/PEP phải giới hạn đúng target/permission; nếu target account vẫn có quyền quá rộng, cần giảm quyền tại hệ đích hoặc có kiểm soát bổ sung.

### 12.2. Step-up không giải quyết sai quyền

Một người dùng đã Mover từ Operations sang Finance có thể xác thực bằng passkey rất mạnh, nhưng **không còn đủ eligibility** để vào production host Operations. Step-up thành công **không hợp thức hóa role đã bị thu hồi**.

## 13. Bảo vệ tính toàn vẹn và chuỗi bằng chứng

Một bản ghi có giá trị điều tra khi có thể chứng minh **đã thu gì, khi nào, bản ghi còn nguyên vẹn ra sao và ai đã truy cập nó**.

### 13.1. Nguyên tắc bảo vệ

1. **Thu thập từ nguồn có thẩm quyền:** PAM gateway, agent hoặc native audit, theo mô hình quản trị.
2. **Mã phiên duy nhất:** có thể liên kết actor, target, approval, timestamp và event.
3. **Ghi theo chunk hoặc stream:** giảm mất dữ liệu khi phiên dài/crash; lưu trạng thái từng phần.
4. **Hash/checksum:** phát hiện byte của file/chunk thay đổi sau khi tính hash.
5. **Manifest có xác minh:** gắn chunk order, hash, size, timestamps, completion state và nguồn capture.
6. **Bảo vệ quyền ghi/sửa/xóa:** tách recorder writer và investigator reader.
7. **Immutable/WORM retention nếu phù hợp:** chống sửa/xóa ngoài quy trình.
8. **Mã hóa dữ liệu at rest/in transit:** bảo vệ bản ghi nhạy cảm.
9. **Đồng bộ thời gian và ký hiệu timezone:** đối chiếu giữa PAM, IdP, OS, DB, SIEM.
10. **Chain of custody:** ghi nhận ai export, xem, chia sẻ hoặc chuyển giao bằng chứng.

### 13.2. Hash không tự chứng minh actor đúng

Ví dụ:

~~~text
Recording chunk 1 -> sha256: <digest-1>
Recording chunk 2 -> sha256: <digest-2>
Recording manifest:
  sessionId
  recordingId
  chunk sequence
  sizes
  digests
  start/end times
  capture-complete status
  integrity/signature reference
~~~

Hash chứng minh **dữ liệu so với giá trị hash** không bị sửa nếu hash và nguồn lưu tin cậy. Nó không tự chứng minh **người xuất hiện trên màn hình là người được phê duyệt**, hoặc recorder đã thu đủ mọi hoạt động.

Tương tự, một chữ ký hợp lệ của manifest không biến dữ liệu bị bỏ sót thành dữ liệu đã được ghi. **Completeness** cần kiểm tra riêng.

### 13.3. UTC, đồng hồ và thứ tự sự kiện

Dùng timestamp rõ timezone, thường lưu UTC và chuyển sang giờ địa phương khi hiển thị. Đồng bộ NTP hoặc dịch vụ thời gian đáng tin theo kiến trúc.

Nếu PAM và target lệch đồng hồ, một event có thể trông như xảy ra trước khi user đăng nhập. Khi điều tra cần lưu **clock source, observed skew và correlation ID**, không chỉ dựa vào timestamp thô.

## 14. Kho lưu trữ, phân quyền xem và thời hạn giữ

Session recording có thể chứa **toàn bộ màn hình production, dữ liệu khách hàng, nội dung bí mật, chi tiết cấu hình và credential**. Kho lưu cần mức bảo vệ tương xứng hoặc cao hơn nhiều log thông thường.

### 14.1. Phân quyền ở evidence store

| Vai trò | Quyền gợi ý | Không nên mặc định |
| --- | --- | --- |
| **Recorder service** | Tạo/append bản ghi được cấp | Đọc mọi phiên hoặc xóa lịch sử |
| **PAM operator** | Xem metadata, kiểm health | Tự xem mọi video nhạy cảm |
| **Security investigator** | Xem/replay phiên theo case có thẩm quyền | Xuất hàng loạt không audit |
| **Compliance reviewer** | Truy cập bằng chứng thuộc scope đã duyệt | Sửa hoặc xóa nội dung |
| **Retention admin** | Thực thi lifecycle theo chính sách | Xóa legal-hold bằng thao tác tùy ý |
| **Key administrator** | Quản lý khóa mã hóa theo SoD | Đồng thời tự xem dữ liệu chưa được duyệt |
| **System owner** | Yêu cầu xem bản ghi liên quan tài nguyên | Xem mọi credential trong bản ghi |

**Người có đặc quyền vận hành PAM không nên mặc nhiên tự xóa bằng chứng phiên của chính mình**. Có thể áp SoD, approval kép hoặc independent audit cho thao tác phá hủy/khôi phục bằng chứng.

### 14.2. Data minimization và retention

Một chính sách retention cần xem xét:

- Mục đích ghi và phạm vi phiên phải ghi.
- Dạng dữ liệu: transcript, video, metadata, command logs, API events.
- Thời gian giữ theo mức rủi ro, nghĩa vụ pháp lý và hợp đồng.
- Chính sách thông báo cho nhân sự/đối tác khi phù hợp.
- Quyền truy cập, dữ liệu cá nhân, jurisdiction và cross-border transfer nếu có.
- Legal hold, incident preservation, truy vết xóa và quy trình xóa theo hạn.
- Khả năng mã hóa, rotate key, khôi phục và xóa an toàn.

**Không có một thời hạn lưu cố định áp dụng cho mọi doanh nghiệp hoặc mọi quốc gia.** Đội pháp chế, bảo mật và chủ sở hữu dữ liệu cần xác định yêu cầu thực tế. Không viện dẫn compliance như lý do mặc định lưu vô hạn.

### 14.3. Recording vs quyền riêng tư

Giám sát phiên quản trị phải cân bằng **an ninh và quyền riêng tư**. Nên giới hạn capture ở phiên quản trị đúng mục đích, tránh quay màn hình cá nhân ngoài scope, giải thích chính sách cho đối tượng bị ghi và kiểm soát nghiêm ngặt ai xem bản ghi.

## 15. Bảo vệ bí mật và xử lý nội dung nhạy cảm trong recording

Một rủi ro của session recording là **vô tình thu thập nhiều bí mật hơn dự kiến**. Quản trị viên có thể xem secret trong vault, copy access token, chạy lệnh chứa mật khẩu hoặc mở bảng dữ liệu cá nhân. Nếu mọi nội dung được lưu nguyên dạng, bản ghi trở thành một **nguồn lộ credential** có giá trị cao.

### 15.1. Phòng ngừa theo nhiều lớp

- **Trước phiên:** cấp credential qua broker/injection hoặc token ngắn hạn, giảm việc nhập/copy mật khẩu.
- **Trong phiên:** giới hạn quyền đọc secret, kiểm soát clipboard/file transfer, masking những trường được hỗ trợ, dùng command controls theo policy.
- **Khi thu thập:** tránh lưu password field, khóa riêng, token thô nếu công cụ cho phép; kiểm thử thực tế khả năng masking.
- **Tại kho lưu:** mã hóa, tách quyền, hạn chế replay/download, áp approval và audit.
- **Khi điều tra:** ưu tiên bản xem đã redacted nếu phù hợp; bản gốc được giữ có kiểm soát phục vụ chain of custody.
- **Khi phát hiện lộ bí mật:** mở incident, hạn chế quyền xem, đánh giá rotation/revocation và truy vết người đã truy cập bản ghi.

### 15.2. Masking không phải đảm bảo tuyệt đối

Một công cụ có thể che ký tự nhập ở form password nhưng không biết **terminal đã in secret ra stdout**, hoặc người dùng dán token vào text editor. Tương tự, tự động nhận dạng thông tin cá nhân trên video có thể bỏ sót hoặc che nhầm.

Vì vậy, trong tài liệu vận hành nên ghi:

> **Redaction làm giảm nguy cơ phơi lộ, không chứng minh bản ghi không chứa bất kỳ bí mật nào.**

Không hứa rằng mọi bản ghi có thể được chia sẻ rộng chỉ vì đã bật một tùy chọn masking.

### 15.3. Bản gốc và bản chia sẻ

Nếu chính sách cần bảo tồn chứng cứ, có thể quản lý:

1. **Original protected recording** – chỉ nhóm rất hạn chế truy cập.
2. **Derived/redacted copy** – dùng cho review theo phạm vi.
3. **Provenance metadata** – xác định copy bắt nguồn từ recording ID nào, được xử lý lúc nào, bởi ai, công cụ/phiên bản nào.
4. **Audit trail** – ghi hoạt động xuất/xem/chia sẻ/xóa và thời hạn sử dụng.

Không sửa trực tiếp bản gốc rồi vẫn tuyên bố chưa chỉnh sửa. Tùy quy định, một số dữ liệu cần được loại bỏ hoặc xử lý theo nghĩa vụ bảo vệ dữ liệu; quy trình phải do tổ chức phê duyệt.

## 16. Khi recorder không sẵn sàng: fail-safe và break-glass

Hệ thống cần có chính sách **trước khi sự cố xảy ra**: liệu một phiên đặc quyền có được bắt đầu nếu recorder đang lỗi hay không? Điều gì xảy ra khi recorder hỏng giữa phiên?

### 16.1. Mô hình quyết định

~~~mermaid
flowchart TD
    S["Yêu cầu phiên đặc quyền"] --> A{"Authorization/JIT hợp lệ?"}
    A -->|"Không"| DENY["DENY + audit"]
    A -->|"Có"| H{"Recorder và storage có khỏe?"}
    H -->|"Có"| START["Bắt đầu phiên, ghi sessionId"]
    H -->|"Không"| R{"Có break-glass được duyệt cho target này?"}
    R -->|"Không"| DENY
    R -->|"Có"| BG["Giới hạn quyền, TTL, MFA, alert, target audit"]
    START --> L{"Recording còn hoạt động?"}
    L -->|"Có"| CONT["Tiếp tục, kiểm TTL/lifecycle"]
    L -->|"Không"| G{"Policy xử lý mất recording?"}
    G -->|"Terminate"| STOP["Chặn thao tác, kết thúc phiên"]
    G -->|"Controlled fallback"| BG
    CONT --> CLOSE["Đóng phiên, finalize, verify"]
    BG --> POST["Review ngoại lệ và bằng chứng bổ sung"]
~~~

Đây là mô hình logic, không phải yêu cầu rằng mọi tổ chức phải **terminate mọi phiên** khi mất recording. Rủi ro và độ an toàn vận hành phải được đánh giá; một thao tác trên hệ thống trọng yếu có thể cần quy trình khẩn cấp có bảo vệ, thay vì cắt ngắt gây sự cố.

### 16.2. Recording health gồm những gì?

Không đủ chỉ kiểm process recorder còn chạy. Nên quan sát:

- **Recorder ready:** có thể tạo bản ghi cho giao thức/target này.
- **Capture started:** dữ liệu thật đã được nhận, không phải chỉ tạo ID.
- **Buffer/backlog:** có nguy cơ tràn bộ đệm hay mất frame/chunk không.
- **Storage reachable:** có thể truyền và ghi dữ liệu theo yêu cầu.
- **Integrity checks:** chunk/manifest được xác minh.
- **Finalize status:** bản ghi được đóng, kết thúc nhất quán.
- **Replay validation:** một mẫu bản ghi có thể thực sự đọc/phát lại.
- **Time sync:** timestamp đủ chính xác để correlation.
- **Alert delivery:** sự cố capture có được gửi tới owner/SIEM không.

### 16.3. Break-glass có kiểm soát

Khi không thể ghi hình và phải xử lý sự cố khẩn cấp, một chế độ break-glass có thể áp:

- Actor định danh riêng, MFA/step-up phù hợp.
- Incident ID và lý do bắt buộc.
- Phê duyệt hoặc kiểm soát bù theo mức rủi ro.
- Target/action hạn chế, thời hạn ngắn.
- Native audit ở target, SIEM, notification và hậu kiểm.
- Tự động thu hồi grant sau khi hết thời gian.
- Ghi một **exception** rõ ràng thay vì giả vờ bản ghi đã tồn tại.

**Không gắn nhãn `recorded=true` cho phiên chỉ có PAM start/end event.** Sự thật về completeness là thông tin kiểm toán quan trọng.

## 17. Ngăn đường bypass session recording

Session recording không hữu ích nếu người dùng có thể vào target qua một đường khác mà chính sách không quản lý.

### 17.1. Các đường bypass phổ biến

| Đường bypass | Ví dụ | Kiểm soát |
| --- | --- | --- |
| **Direct SSH/RDP** | Admin dùng VPN vào IP target thay gateway | Firewall/host policy chỉ cho đường được quản trị |
| **Local admin account** | Login console vật lý/VM console ngoài PAM | Inventory, local account controls, audit và break-glass policy |
| **Cloud console/API** | Người dùng dùng role cloud trực tiếp không qua broker | IAM roles, federation, audit/control plane |
| **Credential leak** | Mật khẩu shared account được dùng ngoài vault | Rotation, broker, không tiết lộ bí mật |
| **SSH tunnel/port forwarding** | Mở kênh tới DB sau proxy chỉ ghi terminal | Hạn chế forwarding hoặc giám sát kênh phù hợp |
| **SFTP/SCP** | Truyền dữ liệu ngoài transcript shell | File transfer controls/DLP/metadata |
| **Alternate protocol** | Dùng WinRM, PowerShell Remoting hoặc DB client khác | Quy định target protocol allowlist và coverage |
| **Container exec** | Truy cập cluster API trực tiếp | Kubernetes audit/RBAC và proxy/terminal controls |
| **Service account key** | Credential máy bị dùng từ nơi khác | Secrets management, rotation, audience/scope |
| **Agent tampering** | Tắt recording service trên endpoint | Hardening, independent alerts, integrity monitoring |

**Không giả định mạng phân đoạn hoặc PAM proxy tự bao phủ mọi giao thức.** Cần lập danh mục các đường truy cập có thể tạo quyền và xác minh chúng có bị giới hạn hay có nguồn evidence tương đương.

### 17.2. Giảm khả năng bypass

- Tách management plane khỏi mạng ứng dụng thông thường.
- Chỉ cho giao thức quản trị từ gateway/approved jump hosts khi phù hợp.
- Hạn chế quyền tạo local admin, SSH key, service token ngoài quản lý.
- Bảo vệ hệ thống PAM và các quyền quản trị PAM bằng MFA, SoD và audit.
- Theo dõi direct login ở target dù đã triển khai proxy.
- Đối soát những privileged accounts và session không có PAM correlation ID.
- Kiểm tra sự tồn tại của đường emergency access, không xóa chúng một cách thiếu kế hoạch.

## 18. Session recording trong Joiner lifecycle

**Joiner** là quá trình một người mới được xác minh, tạo identity/account và cấp quyền theo vai trò. Với người chuẩn bị làm quản trị viên, việc cấp quyền cần đồng thời bảo đảm **phiên đặc quyền bắt buộc đi qua kênh được quản trị**.

### 18.1. Quy trình minh họa

1. HRIS/hợp đồng xác nhận người mới, workerType, effectiveAt, manager/sponsor.
2. Identity proofing thiết lập tin cậy và gắn `identityId` ổn định.
3. IdP cấp account và đăng ký phương thức xác thực phù hợp (MFA/passkey).
4. IGA xác định **privileged eligibility** theo role và approval; không tự cấp admin chỉ vì account đã tạo.
5. PAM tạo actor mapping, nhóm được phép và enrollment theo sản phẩm.
6. Target account/credential được provision/broker theo thiết kế, có owner.
7. Policy buộc phiên SSH/RDP/DB đi qua gateway và có recording/health check.
8. Reconciliation xác minh account, role và recording coverage cho các hệ đích quan trọng.

**Một người Joiner đăng nhập SSO thành công nhưng chưa có quyền production admin thì vẫn bị từ chối vào target.** Recording không phải lý do cấp tạm role quá rộng.

### 18.2. Preboarding và ngày hiệu lực

Có thể pre-provision PAM account trước ngày bắt đầu, nhưng không bật production access trước `effectiveAt` nếu không có policy riêng. Ghi sẵn cấu hình recorder không làm quyền truy cập hợp lệ.

### 18.3. Người mới chưa có mapping đúng

Nếu IAM chưa liên kết người dùng với PAM actor, **không tự dùng account admin chia sẻ và giả định attribution đúng**. Nên từ chối hoặc đưa vào exception/approval flow cho tới khi mapping đủ tin cậy.

## 19. Session recording trong Mover lifecycle

**Mover** thay đổi bộ phận, nhiệm vụ, dự án hoặc nhóm quản trị. Người dùng vẫn có thể ACTIVE nhưng không còn cần quyền trên các target trước đây.

### 19.1. Ví dụ thay đổi nhiệm vụ

~~~text
Trước Mover:
  role: DatabaseOperator
  allowedTargets: [prod-db-01, prod-db-02]
  PAM eligibility: DBA-PROD
  active privileged session: ps-109

Sau Mover:
  role: ApplicationDeveloper
  desiredTargets: [dev-app-01]
  DBA-PROD: REVOKE
  active privileged session ps-109: cần đánh giá/terminate
~~~

Những bước bắt buộc:

- IGA tính lại **desired privileged access**, thu hồi DBA-PROD và target permissions cũ.
- PAM cập nhật eligibility, group, JIT grants và các approval đang chờ.
- Đánh giá **phiên đang mở**: có tiếp tục được phép, cần terminate hay phải tái xác thực/phê duyệt?
- Rotation/revocation credential có thể tái sử dụng ngoài PAM.
- Kiểm tra target account local và cloud role cũ.
- Reconciliation xác minh quyền cũ đã bị gỡ và phiên không còn đường truy cập.
- Recording của phiên trước đó vẫn được giữ theo retention và quyền truy cập phù hợp.

### 19.2. Recording không thu hồi quyền

Một bản ghi cho thấy người dùng thao tác sau Mover là **bằng chứng rủi ro**, không phải biện pháp chặn. Nếu policy đã gỡ quyền, **PAM/PEP phải từ chối hoặc ngắt phiên theo khả năng và chính sách**; recorder chỉ bổ sung điều tra.

### 19.3. Token/phiên còn mang role cũ

Claim SSO hoặc phiên PAM có thể cache role cũ. Khi quyền DBA bị thu hồi, cần kiểm **lifecycle/current entitlement** và invalidation hoặc TTL phù hợp; không trông chờ người dùng đăng xuất để policy mới có tác dụng.

## 20. Session recording trong Leaver lifecycle

**Leaver** yêu cầu chặn đường truy cập khi người dùng nghỉ hoặc hợp đồng kết thúc. Đặc biệt với quyền production, không được kết luận offboarding chỉ dựa vào account IdP bị disabled.

### 20.1. Các lớp cần xử lý

~~~mermaid
flowchart TD
    HR["HRIS: Leaver effectiveAt"] --> IGA["IGA: Revoke privileged access"]
    IGA --> IdP["IdP: chặn login và phiên theo policy"]
    IGA --> PAM["PAM: revoke eligibility/JIT, terminate session"]
    IGA --> TARGET["Target: gỡ role/key/account/credential"]
    IGA --> SCIM["SCIM/API: deprovision SaaS/cloud"]
    PAM --> REC["Finalize recording + integrity"]
    IdP --> VERIFY["Reconciliation"]
    TARGET --> VERIFY
    SCIM --> VERIFY
    REC --> VERIFY
    VERIFY --> Q{"Các đường truy cập trong scope đã chặn?"}
    Q -->|"Chưa"| EX["Exception + owner + escalation"]
    Q -->|"Đã xác minh"| CLOSE["Audit và close"]
    EX --> VERIFY
~~~

### 20.2. Phiên đang hoạt động sau effectiveAt

Giả sử nhà thầu được phép truy cập hệ thống đến 18:00 nhưng phiên SSH bắt đầu lúc 17:55. Nếu PAM chỉ kiểm authorization khi mở kết nối, lúc 18:01 họ có thể vẫn chạy lệnh.

Thiết kế phải xác định:

- **Grant expiry** có chấm dứt phiên hiện hữu không?
- PAM có nhận event Leaver kịp thời không?
- PEP hoặc target có **current-state check** cho hành động nhạy cảm không?
- SSH tunnel/background process có tồn tại sau khi gateway đóng không?
- Credential hoặc token đã phát có được thu hồi/rotate đúng phạm vi không?
- Bản ghi có được finalize và lưu bằng chứng đủ integrity không?

**IdP disabled không tự kết thúc mọi PAM session, target session hoặc API token**. Các kênh độc lập cần hành động riêng.

### 20.3. Giữ bản ghi của người đã nghỉ

Đóng identity hoặc xóa user ở PAM không nên tự xóa recording còn trong thời hạn retention hoặc legal hold. Bản ghi cần được lưu bằng **immutable IDs** và mapping lịch sử để phục vụ điều tra, đồng thời tuân thủ chính sách quyền riêng tư.

### 20.4. Nhiều quan hệ việc làm

Một người có thể kết thúc hợp đồng A nhưng vẫn còn quan hệ hợp lệ B. Cần thu hồi **target/approval/privileged eligibility gắn với quan hệ A**, không tự giữ hoặc hủy toàn bộ theo email chung. Identity registry và policy phải nêu rõ phạm vi.

## 21. Tài khoản dịch vụ, automation và ghi nhận hoạt động đặc quyền

Không phải mọi phiên đặc quyền đều do một người ngồi trước màn hình.

### 21.1. Non-human identities

- **CI/CD pipeline:** triển khai software và thay cloud resources.
- **Service account:** chạy job, ứng dụng hoặc connector.
- **Managed identity:** nhận quyền gọi cloud APIs.
- **Database maintenance bot:** chạy scheduled SQL migrations.
- **Break-glass automation:** thực hiện playbook khôi phục hệ thống.

Với automation, cần ưu tiên **job logs, structured API audit, artifact provenance, identity of workload, owner và quyền cụ thể**, thay vì khẳng định có screen recording.

### 21.2. Chuỗi attribution cho automation

~~~text
Human change requester / approver (nếu có)
    -> source commit / change ID
    -> CI/CD pipeline run
    -> workload identity / credential
    -> target resource / API
    -> native audit event + job logs
    -> evidence record and checksum
~~~

Phải phân biệt **người đã approve workflow** và **principal thực thi API**. Người approve không nhất thiết là người trực tiếp phát mọi API call.

### 21.3. Owner Mover hoặc Leaver

Khi người phụ trách service account nghỉ hoặc đổi vai trò:

1. Gỡ quyền cá nhân trên repo, PAM, vault và cloud.
2. Bàn giao owner của service account và recording policy.
3. Rotate/revoke secret hoặc token liên quan người cũ.
4. Kiểm quyền workload còn phù hợp business purpose.
5. Không tắt nhầm workload cần thiết cho production.
6. Đối soát job/API audit và lưu bằng chứng chuyển giao.

**Recording của con người không thay thế governance cho service identity.**

## 22. Live session monitoring và can thiệp

Ngoài bản ghi xem lại sau, một số PAM triển khai **live monitoring** để người được ủy quyền quan sát và can thiệp khi phiên đang chạy.

### 22.1. Các loại hành động

| Hành động | Ví dụ | Điều cần bảo vệ |
| --- | --- | --- |
| **Live view** | Security nhìn phiên quản trị viên | Approval, scope và audit người xem |
| **Keyword/command alert** | Cảnh báo lệnh nguy hiểm | Độ chính xác, xử lý false positives |
| **Suspend/pause** | Dừng tương tác khi rủi ro | Tránh gây lỗi ứng dụng hoặc dữ liệu |
| **Terminate** | Ngắt session tại gateway | Xác minh target process/tunnel còn hay không |
| **Force reauthentication** | Yêu cầu step-up khi hành động nhạy cảm | Không coi MFA là permission |
| **Escalate incident** | Gửi sự kiện tới SOC/on-call | Đúng owner, dữ liệu tối thiểu |
| **Require dual control** | Hai người giám sát thao tác nhạy cảm | SoD và audit |

### 22.2. Monitoring không phải không thể sai

Một số phát hiện dựa vào pattern lệnh có thể bị bỏ qua bằng script, alias, encoding hoặc API. Chúng cũng có thể báo sai khi người dùng nhập lệnh trong tài liệu thay vì thực thi.

**Đừng xây hệ thống bằng một danh sách chuỗi cấm đơn giản rồi xem đó là chặn đặc quyền toàn diện.** Cần kiểm soát quyền ở target, command/role scope và OS/API audit.

### 22.3. Khi nào can thiệp?

Quy trình nên định nghĩa:

- Mức nguy cơ nào cần alert, suspend hoặc terminate.
- Ai có quyền ngắt phiên.
- Cách thông báo và ghi lý do.
- Cách bảo toàn recording khi ngắt bất thường.
- Cách xử lý khi thao tác đang ảnh hưởng hệ thống an toàn/tính sẵn sàng.
- Cách review quyết định can thiệp và cải thiện detection.

## 23. Điều tra sự cố với session recording

Khi một thay đổi production gây mất dịch vụ hoặc nghi ngờ lạm dụng quyền, recording là một phần của **incident evidence**, không phải nguồn duy nhất.

### 23.1. Quy trình phân tích

1. **Khoanh vùng incident:** target, thời gian, loại thay đổi và dữ liệu bị ảnh hưởng.
2. **Tìm actor/phiên:** tra IdP auth, PAM access request, sessionId, target account và target logs.
3. **Bảo vệ bằng chứng:** đặt retention hold theo thẩm quyền, tránh thay đổi bản gốc, kiểm hash/manifest.
4. **Kiểm completeness:** bản ghi có đủ đầu-cuối, có missing chunks hoặc recorder outage không?
5. **Xem replay/transcript:** dùng quyền được duyệt, theo dõi hành động và dấu hiệu bất thường.
6. **Tương quan target evidence:** OS audit, DB transactions, cloud API, Kubernetes audit, file transfers.
7. **Xác định tác động:** thay đổi thực tế, quyền đã dùng, dữ liệu đã truy cập/chuyển.
8. **Đối chiếu policy:** role, JIT approval, target, effectiveAt và SoD lúc thực hiện.
9. **Ghi kết luận kèm mức chắc chắn:** phân biệt quan sát trực tiếp với suy luận.
10. **Remediation và follow-up:** revoke credential, sửa bypass, bổ sung detection và kiểm lại.

### 23.2. Những điều không nên kết luận từ recording đơn độc

- “Không thấy trên video” **không chứng minh** một API action không xảy ra.
- “Video thấy dòng lệnh” **không chứng minh** lệnh đã hoàn tất và commit thành công.
- “Đăng nhập root” **không xác định chắc chắn người thực** nếu shared credential chưa được liên kết.
- “Bản ghi có hash hợp lệ” **không chứng minh recorder bao phủ toàn bộ đường truy cập**.
- “Phiên kết thúc ở gateway” **không chứng minh** background job hoặc token đã được thu hồi.
- “Có recording” **không đồng nghĩa thao tác được phê duyệt**.

Một kết luận điều tra tốt ghi rõ **bằng chứng nào hỗ trợ điều gì**, giới hạn từng nguồn và các khoảng trống chưa được giải thích.

## 24. Schema metadata và correlation cho audit

Dữ liệu metadata nên liên kết được với bản ghi và sự kiện quyền mà không cần lưu token/password.

~~~json
{
  "recordingId": "rec-20261123-08492",
  "sessionId": "pam-session-10492",
  "actorIdentityRef": "person-1042",
  "actorType": "HUMAN",
  "idpSubjectRef": "trusted-subject-reference",
  "pamAccountRef": "pam-user-718",
  "targetResourceId": "prod-db-07",
  "targetAccountRef": "db_admin",
  "protocol": "SSH",
  "accessRequestId": "req-2146",
  "approvalRef": "approval-1120",
  "grantId": "jit-grant-900",
  "grantExpiresAt": "2026-11-23T18:00:00+07:00",
  "recordingStartedAt": "2026-11-23T17:15:00+07:00",
  "recordingEndedAt": "2026-11-23T17:44:00+07:00",
  "recordingStatus": "COMPLETE",
  "manifestDigest": "sha256:illustrative-placeholder",
  "integrityVerified": true,
  "reviewClassification": "PRIVILEGED_CONFIDENTIAL"
}
~~~

Đây là **mẫu JSON minh họa**. Không có format bắt buộc chung cho mọi PAM. `integrityVerified=true` chỉ đáng tin khi có quá trình kiểm tra đã được thực hiện thật, không phải boolean người dùng tự đặt.

### 24.1. Tách nhiều trạng thái

~~~text
ACCESS_REQUEST: APPROVED
PAM_SESSION: TERMINATED
TARGET_CONNECTION: CLOSED
RECORDING_CAPTURE: PARTIAL
RECORDING_INTEGRITY: VERIFIED_FOR_AVAILABLE_CHUNKS
RECONCILIATION: EXCEPTION_OPEN
~~~

Dữ liệu trên mô tả một tình huống có thể có: phiên đã đóng nhưng bản ghi thiếu một phần, những phần còn lại vẫn nguyên vẹn. Không nên gộp thành một dòng **SUCCESS** gây hiểu nhầm.

### 24.2. Tiêu chí completeness

Một chính sách có thể yêu cầu kiểm:

- Bản ghi bắt đầu **trước khi** quyền tương tác target được mở.
- Không có khoảng trống không được giải thích giữa start/end.
- Mọi segment/chunk được ghi với thứ tự và trạng thái.
- Dấu hiệu reconnect hoặc child sessions được liên kết.
- Target connection được kết thúc hoặc có event rõ về tồn dư.
- Manifest, chữ ký hoặc checksum được xác minh.
- Bản ghi có thể xem lại theo mức độ được hỗ trợ.
- Những ngoại lệ được gán owner và remediation deadline.

## 25. Phát lại, tìm kiếm và xuất bản ghi an toàn

Bản ghi có thể được tra theo sessionId, actor, target, thời gian, ticket, lệnh hoặc cảnh báo. Tính năng tìm kiếm giúp điều tra nhưng cũng tăng nguy cơ **truy cập dữ liệu nhạy cảm hàng loạt**.

### 25.1. Quy trình replay

1. Investigator có case/ticket và quyền phù hợp.
2. Hệ thống kiểm RBAC/ABAC theo **target, dữ liệu, tenant, mục đích và thời gian**.
3. Mở bản ghi đã được bảo vệ, xác minh integrity/completeness.
4. Ghi audit: người xem, recordingId, mục đích, thời gian, phần đã xem.
5. Dùng bản redacted nếu phù hợp, chỉ truy cập raw content khi có thẩm quyền.
6. Nếu export, tạo gói có manifest, watermark hoặc quyền truy cập phù hợp.
7. Có hạn chia sẻ và retention riêng cho bản copy.

### 25.2. Tìm kiếm nội dung nhạy cảm

Một công cụ có thể index transcript SSH để tìm lệnh `useradd` hoặc SQL `GRANT`. Nếu index chứa **full secrets** và cho phép mọi operator tìm kiếm, bản thân search index là một nguồn rò rỉ.

Cần giới hạn phạm vi index, tokenization/redaction theo khả năng, phân quyền query và retention. Không bảo đảm search sẽ tìm thấy mọi hành động vì transcript có thể chứa mã hóa hoặc thao tác qua GUI/script.

### 25.3. Xuất bằng chứng

Một export phục vụ điều tra nên có:

- Recording ID, session ID, target, thời gian.
- Nội dung/chunk có scope phù hợp.
- Checksum/digest và manifest.
- Nguồn xuất, người xuất, thời điểm, case ID.
- Ghi nhận redaction/processing nếu có.
- Hướng dẫn lưu trữ/chuyển giao an toàn và thời hạn.

**Không gửi trực tiếp file video nhạy cảm qua chat/email chung** nếu không có cơ chế bảo vệ được tổ chức chấp thuận.

## 26. Chỉ số vận hành và cảnh báo

| Chỉ số | Ý nghĩa | Điểm cần chú ý |
| --- | --- | --- |
| **Required-session recording coverage** | Tỷ lệ phiên cần ghi có bản ghi hợp lệ | Phải có mẫu số từ session inventory, không chỉ recorder logs |
| **Complete recording rate** | Tỷ lệ bản ghi có đủ segment theo policy | Khác với số lần tạo recording ID |
| **Recording start gap** | Khoảng giữa target connect và capture start | Khoảng trống đầu phiên đặc quyền |
| **Unrecorded privileged access count** | Số phiên/đường vào không có evidence | Phát hiện bypass hoặc thiếu instrumentation |
| **Recorder health / availability** | Gateway, collector, storage và kiểm replay | Không chỉ kiểm process alive |
| **Storage backlog / dropped chunks** | Mức dữ liệu đang chờ hoặc bị mất | Khả năng thiếu bản ghi |
| **Integrity verification failures** | Hash/manifest sai, file hỏng | Ưu tiên điều tra |
| **Session termination latency** | Từ revoke/JML event tới target session bị chặn | Đo rủi ro Mover/Leaver |
| **JIT overrun count** | Phiên tiếp tục sau grant expiry | Có thể có target process tồn dư |
| **Recording review access anomalies** | Download, replay, export bất thường | Dấu hiệu lạm dụng kho evidence |
| **Retention compliance** | Xóa/giữ đúng thời hạn và legal hold | Tránh lưu vô hạn hoặc xóa sớm |
| **Critical alert response latency** | Thời gian từ detection tới xử lý | Monitoring không có người phản ứng sẽ yếu |
| **Attribution completeness** | Tỷ lệ phiên liên kết đúng human/workload owner | Shared account là rủi ro |
| **Bypass channel findings** | Kênh SSH/RDP/API ngoài PAM được phát hiện | Cần chặn hoặc chứng cứ tương đương |

### 26.1. Không dùng số giờ video làm KPI duy nhất

Một tổ chức có thể ghi hàng trăm nghìn giờ video nhưng vẫn còn:

- API cloud không được audit.
- Direct SSH ngoài gateway.
- Phiên root dùng shared credential không truy ra actor.
- Recorder mất 10 phút đầu phiên.
- Video không được bảo vệ hoặc khó phát lại.
- Người Leaver giữ token cũ.

Chất lượng nên đo bằng **coverage, attribution, completeness, integrity, detection, session control và effective access**.

## 27. Vận hành, troubleshooting và xử lý lỗi

### 27.1. Các dạng sự cố thường gặp

| Hiện tượng | Nguyên nhân có thể | Điều cần kiểm tra |
| --- | --- | --- |
| PAM có session nhưng không có recording | Chưa start collector, policy route sai, storage lỗi | Session path, health, policy, collector events |
| Recording chỉ có vài giây | Client disconnect, recorder crash hoặc chunk upload lỗi | Segment timeline, backlog, target logs |
| SSH transcript thiếu lệnh | Non-PTY, tunnel, alternate shell/channel | SSH mode, channel instrumentation, OS audit |
| RDP replay đen/trống | Tính năng đồ họa, secure desktop, capture limitation | Product capability, thử nghiệm GUI |
| Video khó đọc | Resolution/compression quá thấp | Replay fidelity, storage/cost policy |
| Không liên kết được actor | Shared account, SSO mapping sai | IdentityId, sessionId, approval và target audit |
| Bản ghi thiếu chữ ký hoặc hash | Finalize lỗi, manifest chưa tạo | Integrity job và storage state |
| Admin vào được ngoài PAM | Direct network path, credential còn dùng | Firewall, local accounts, key management |
| Session vẫn còn sau revoke | PAM chỉ gỡ eligibility, target session độc lập | Session terminate, target processes, token TTL |
| Playback không mở được dù file có | Codec/format/key/role lỗi | Tool compatibility, key management, audit |
| Legal hold bị xóa nhầm | Retention policy/ACL hoặc workflow sai | Hold registry, deletion logs, permissions |

### 27.2. Các bước xử lý an toàn

1. **Xác định scope:** actor, target, giao thức, thời điểm, sessionId và recordingId.
2. **Phân loại rủi ro:** có production admin, credential, Leaver hoặc dữ liệu nhạy cảm không?
3. **Kiểm đường truy cập thật:** gateway/agent/target, có bypass hay không?
4. **Kiểm collector và storage:** health, bắt đầu, backlog, chunk, finalize.
5. **Tương quan target logs:** phiên/command/API nào được ghi tại nguồn?
6. **Kiểm quyền và thời hạn:** approval, JIT, session TTL, JML, credential.
7. **Bảo toàn bằng chứng:** tránh xóa/cắt bản ghi gốc, mở incident khi cần.
8. **Khắc phục theo runbook:** cấu hình, quyền, storage hoặc network; không tự mở direct admin access vô thời hạn.
9. **Test lại:** một phiên mẫu qua đúng protocol và target, replay/verify.
10. **Đóng exception:** ghi owner, nguyên nhân, phạm vi ảnh hưởng, thời điểm xử lý và xác minh.

Không dùng thao tác “restart collector” như câu trả lời đầy đủ nếu vẫn còn **đường SSH trực tiếp không được ghi**.

## 28. Tình huống tổng hợp: quản trị production qua JML

Giả sử doanh nghiệp có hệ thống quản trị **production database** qua PAM gateway, nhân viên đăng nhập bằng IdP/SSO và chỉ được cấp JIT sau phê duyệt.

### 28.1. Joiner: DBA mới

**Lan** bắt đầu ngày 01/12/2026:

- HRIS xác nhận quan hệ làm việc và ngày hiệu lực; identity proofing hoàn tất.
- IdP tạo account, MFA/passkey theo policy.
- IGA phê duyệt eligibility `DBA_PROD_ELIGIBLE`, không cấp quyền truy cập database liên tục.
- PAM liên kết Lan với identityId, yêu cầu ticket và approval cho mỗi phiên production.
- Gateway broker credential, tạo sessionId, kiểm recorder ready rồi mới kết nối DB.
- Recording lưu transcript, metadata và hash manifest; DB audit ghi lệnh thực thi thực tế.

**Điểm quan trọng:** một recording hợp lệ không thay thế việc chỉ cấp những quyền DBA được duyệt, trong thời hạn hợp lệ.

### 28.2. Mover: sang nhóm phát triển ứng dụng

Ba tháng sau, Lan chuyển sang Application Developer:

- HRIS/IGA cập nhật desired role, gỡ `DBA_PROD_ELIGIBLE`.
- PAM ngăn mở phiên DB mới và đánh giá session DBA đang hoạt động.
- Nếu còn phiên, PAM terminate hoặc áp policy thu hồi theo rủi ro.
- Credential/role ở DB và local admin được gỡ/rotate khi cần.
- Recording đã có được giữ theo retention.
- Reconciliation xác minh không còn quyền DB và không có active privileged session.

**Điểm quan trọng:** ghi video Lan thao tác sau Mover là dấu vết, nhưng mục tiêu là **chặn được thao tác đó**.

### 28.3. Leaver: nhà thầu hết hợp đồng

Nhà thầu **An** được phép làm việc đến 18:00. An mở SSH lúc 17:45 và chạy deployment. 18:00, sự kiện Leaver có hiệu lực:

- IdP chặn xác thực mới.
- IGA thu hồi JIT và PAM eligibility.
- PAM chấm dứt phiên SSH theo policy, ghi end reason `LIFECYCLE_REVOKE`.
- Target audit xác minh kết nối và tiến trình liên quan đã xử lý; secret/key được revoke khi cần.
- Recorder finalize, lưu bằng chứng; SIEM correlation đến HRIS và ticket.
- Reconciliation đóng Leaver khi các đường truy cập bắt buộc đã được chặn.

Nếu PAM ngắt nhưng một `nohup` job tiếp tục chạy, **target/session/automation checks** cần xử lý riêng. Recording không tự kết thúc tiến trình đã tách khỏi phiên.

### 28.4. Sự cố recorder giữa phiên

Trong một phiên khôi phục dịch vụ khẩn cấp, collector mất kết nối:

- PAM nhận cảnh báo recording health.
- Chính sách target nhạy cảm yêu cầu dừng thao tác mới hoặc chuyển break-glass đã được chấp thuận.
- Kho bằng chứng đánh dấu `PARTIAL`, không giả `COMPLETE`.
- Target native audit/SIEM hỗ trợ điều tra phần thiếu, nhưng không tự được gọi là full recording.
- Sau sự cố, nhóm vận hành xác minh collector và chạy negative tests.

**Điểm quan trọng:** trung thực về evidence gap là điều kiện của kiểm toán đáng tin.

## 29. Ma trận kiểm thử session recording

| Ca kiểm thử | Trạng thái giả lập | Kỳ vọng |
| --- | --- | --- |
| Joiner chưa tới effectiveAt | Có PAM account, chưa đủ điều kiện | DENY production session |
| Admin được duyệt đúng target | JIT còn hạn, recorder khỏe | Start, record, finalize, integrity PASS |
| Sai target | Approval cho server A, vào server B | DENY |
| Thiếu step-up | Actor có eligibility nhưng assurance thấp | Chặn, yêu cầu xác thực phù hợp |
| Mover mất role DB | Token cũ còn DBA group | Không mở phiên mới; xử lý phiên hiện tại |
| Leaver đang SSH | HRIS hết hợp đồng trong phiên | Terminate/revoke theo policy, audit |
| Recorder lỗi trước khi connect | Không có capture ready | Không mở phiên thường; exception nếu đã duyệt |
| Recorder chết giữa phiên | Mất chunk hoặc storage unreachable | Thực hiện fail-safe, ghi PARTIAL |
| Shared account không mapping actor | Có root login nhưng thiếu human ID | Từ chối hoặc exception, không tuyên bố attribution PASS |
| RDP reconnect | Session ngắt rồi nối lại | Segment mapping đầy đủ, không bỏ mất khoảng trống |
| SSH port forwarding | Tunnel ngoài TTY | Chặn hoặc kiểm soát/audit riêng |
| File transfer qua SFTP | Không có shell command | Có file-transfer controls/metadata theo scope |
| Replay của người không được phép | Reviewer không có quyền tenant/target | DENY replay |
| Export recording chứa secret | Investigator xin bản thô | Approval/SoD, bảo vệ và audit |
| Bản ghi bị thay một chunk | Digest không khớp | Integrity FAILURE và alert |
| Bản ghi hết hạn nhưng legal hold | Deletion job chạy | Không xóa khi hold hợp lệ |
| Service pipeline dùng API | Không có interactive session | Có workload/API evidence thay vì video giả |
| Break-glass không có lý do | Actor yêu cầu bypass recorder | DENY hoặc kiểm soát theo policy |
| PAM proxy bị bypass | SSH trực tiếp target | Chặn mạng hoặc phát hiện/alert |
| Session kết thúc nhưng target job sống | Background process tồn tại | Detect và remediation theo policy |

### 29.1. Kiểm thử âm tính rất quan trọng

Một demo chỉ cho thấy **recording có thể phát lại** chưa chứng minh hệ thống kiểm soát privileged access. Nên thử **đường không được phép**, actor sai, target sai, thời hạn hết, token cũ, recorder outage, mất mạng, secret leakage, replay unauthorized và phiên kéo dài sau revoke.

### 29.2. Test end-to-end

Kiểm thử hoàn chỉnh nên chứng minh được:

~~~text
HRIS/IGA state
   -> IdP authentication
   -> PAM authorization/JIT grant
   -> Gateway/session policy
   -> Recorder actual capture
   -> Target audit / effect
   -> Secure storage/integrity
   -> Replay access controls
   -> Reconciliation + audit
~~~

Dữ liệu đầu vào và kết quả cuối phải dùng cùng correlation IDs hoặc mapping tin cậy.

## 30. Checklist thiết kế và triển khai

| Câu hỏi kiểm tra | Bằng chứng mong đợi |
| --- | --- |
| Đã phân loại những privileged action/target cần ghi? | Target inventory, risk tier, owner |
| Có định nghĩa session recording khác audit logging? | Coverage matrix theo protocol |
| Có kiểm soát đường vào chỉ qua PAM khi cần? | Network/target policies, bypass tests |
| Có phân biệt human identity và target shared account? | identityId, approval, sessionId mapping |
| Có kiểm JML status trước và trong phiên? | Policy, revocation signal, tests |
| Có JIT/JEA, MFA/step-up và approval phù hợp? | Access request, SoD, TTL |
| Recording khởi tạo trước target connection? | Capture start evidence |
| Có ghi đúng SSH interactive/non-interactive? | Protocol test cases |
| Có kiểm SFTP/SCP/tunnel và file transfer? | Specific controls, audit events |
| RDP GUI có replay đúng/đủ theo scope? | Fidelity/secure desktop tests |
| Web/cloud/DB/Kubernetes có native audit bổ sung? | Correlated evidence |
| Có đo trạng thái COMPLETE/PARTIAL/FAILED? | Metadata và integrity jobs |
| Có hash/manifest và bảo vệ provenance? | Verification and key control |
| Có quản lý buffer, storage, dropped chunk? | Health telemetry và alert |
| Có encrypt và tách quyền xem/xóa không? | ACL/RBAC/ABAC, key management |
| Investigator phải có ticket và audit replay? | Case-scoped access record |
| Có quản lý secret/PII trong recording không? | Redaction process và quyền raw |
| Có retention và legal hold theo policy không? | Schedule, deletion/hold audit |
| Có hành vi khi recording lỗi? | Fail-safe/break-glass runbook |
| Có điều kiện ngắt phiên khi JIT hết hạn? | Session terminate/capability revoke test |
| Có kiểm background jobs/tunnels sau disconnect? | Target audit và active session checks |
| Có xử lý phiên Mover/Leaver còn sống? | Revoke latency và reconciliation |
| Có owner cho service/workload identity? | Inventory và credential lifecycle |
| Có tương quan IDP/PAM/target/SCIM logs? | Correlation IDs và SIEM |
| Có giám sát direct privileged access ngoài PAM? | Endpoint/network alerts |
| Có quy trình incident evidence preservation? | Chain of custody, review scope |
| Có KPI coverage, completeness, integrity, bypass? | Dashboard, owner, escalation |

## 31. Những nhầm lẫn thường gặp

1. **“Có PAM recorder thì mọi hành động đều được ghi.”** Phải kiểm giao thức, đường truy cập, agent/gateway và coverage thực tế.
2. **“Recording là video của mọi phiên.”** SSH, DB, API và automation có dạng evidence khác nhau.
3. **“Ghi video đồng nghĩa chặn thao tác trái phép.”** Authorization/PEP phải kiểm và từ chối.
4. **“Session root xác định chắc người thực.”** Shared account cần liên kết identity và PAM session.
5. **“Recorder có process running tức ghi đủ.”** Phải kiểm capture start, chunk, finalize và replay.
6. **“Hash hợp lệ chứng minh đã ghi toàn bộ hoạt động.”** Hash chỉ hỗ trợ phát hiện sửa dữ liệu đã có.
7. **“RDP video cho thấy lệnh đã commit thành công.”** Cần target/database audit và observed state.
8. **“Chỉ cần log lệnh SSH là thấy mọi việc script làm.”** Script/API/subprocess có thể có tác dụng ngoài transcript.
9. **“Tắt IdP là mọi SSH session lập tức chấm dứt.”** PAM/target session và token có vòng đời riêng.
10. **“JIT hết hạn nghĩa background process tự dừng.”** Cần điều khiển hoặc kiểm tra target.
11. **“Mọi recording nên lưu vĩnh viễn.”** Phải theo retention, privacy, legal hold và data minimization.
12. **“Mask password field nghĩa recording không có secret.”** Secret có thể xuất hiện ở stdout, clipboard hoặc màn hình khác.
13. **“PAM operator luôn có thể xem mọi video.”** Replay là quyền nhạy cảm cần SoD và audit.
14. **“Đã ghi phiên thì không cần native audit.”** Các nguồn evidence bổ trợ lẫn nhau.
15. **“Break-glass là truy cập tự do không cần evidence.”** Phải giới hạn, ghi exception và hậu kiểm.
16. **“Service account không cần audit vì không có người sử dụng.”** Workload cần owner, job provenance và API events.
17. **“Đóng cửa sổ PAM là mọi kết nối/tunnel đã chết.”** Cần target-level verification.
18. **“Recording COMPLETE thì việc Leaver đã hoàn tất.”** Phải thu hồi quyền và xác minh không còn đường truy cập.
19. **“Có video là đủ kết luận ý định người thao tác.”** Bản ghi là dữ liệu quan sát, không tự chứng minh động cơ.
20. **“Chỉ số giờ video tăng là hệ thống tốt hơn.”** Chất lượng là coverage, attribution, integrity và enforcement.

## 32. Câu hỏi tự đánh giá

1. Session recording khác audit log và session monitoring như thế nào?
2. Tại sao cần gắn privileged target account với identityId của con người?
3. Một PAM gateway SSH ghi transcript có nhìn được mọi hoạt động SCP, SFTP và port forwarding không?
4. RDP screen recording có những giới hạn gì khi phân tích sự cố backend?
5. Vì sao một cloud API call nên được điều tra cùng native audit, không chỉ video browser?
6. PEP phải kiểm điều kiện nào trước khi cho mở một phiên đặc quyền JIT?
7. Nếu grant JIT hết hạn nhưng phiên SSH vẫn đang mở, hệ thống cần làm gì?
8. Vì sao step-up MFA không thể khôi phục quyền đã bị thu hồi sau Mover?
9. Hash/manifest giúp chứng minh điều gì và không chứng minh điều gì?
10. Làm thế nào để kiểm một recording COMPLETE khác với PARTIAL?
11. Khi recorder lỗi trước khi kết nối target, có nên cho phép không? Những điều kiện nào ảnh hưởng quyết định?
12. Một quản trị viên có thể bypass PAM bằng những đường nào? Chọn hai biện pháp ngăn chặn.
13. Vì sao kho recording cần quyền xem/export riêng và audit người xem?
14. Nếu recording chứa access token, cần làm gì để giảm rủi ro trong lưu trữ và điều tra?
15. Khi nhân viên Joiner nhận account IdP sớm, vì sao chưa được mở quyền admin?
16. Một nhân viên Mover đã mất role DBA nhưng đang có phiên RDP: PAM/IGA phải xử lý ra sao?
17. Vì sao disable IdP trong Leaver không bảo đảm mọi API token và background job đã ngừng?
18. Làm sao bảo toàn bằng chứng khi cần redaction để chia sẻ ngoài nhóm điều tra?
19. Thế nào là attribution trong phiên dùng shared account root?
20. Ghi những trường correlation nào để nối HRIS event, PAM session, target audit và recording?
21. Khi pipeline CI/CD chạy cloud API, loại evidence nào phù hợp thay vì video tương tác?
22. Nêu năm KPI quan trọng để đo chất lượng privileged session recording.
23. Vì sao recorder available không đủ khi không có direct-access bypass detection?
24. Một log cho thấy `DROP TABLE` được gõ trong terminal: cần chứng cứ nào để xác nhận transaction thực sự xảy ra?

## 33. Ghi nhớ

**Session recording** là kiểm soát **thu thập, bảo vệ và có thể xem lại hoạt động trong các phiên truy cập đặc quyền**. Dữ liệu có thể là **terminal transcript, RDP screen capture, command metadata, database audit hoặc API events**, tùy giao thức và vị trí quan sát. Một bản ghi đáng tin cần **attribution đúng người/workload, sessionId, target, approval, thời gian, completeness, integrity, retention, quyền xem và chain of custody**.

Trong vòng đời **Joiner–Mover–Leaver**, **HRIS/identity proofing/IGA** xác định người và quyền được duyệt, **IdP/SSO** xác thực, **PAM/JIT/RBAC/ABAC** giới hạn phiên và thao tác, **SCIM/API** cấp hoặc thu hồi tài khoản ở hệ đích, còn **audit/reconciliation** xác minh quyền thực sự còn hay không. **Recording không thay thế authorization, không tự ngắt một phiên còn sống, không tự revoke credential/token và không chứng minh mọi hành động đã được ghi đầy đủ**. Để giảm quyền truy cập tồn dư, hệ thống phải **ngăn bypass, xử lý recorder failure, thu hồi phiên khi Mover/Leaver, bảo vệ bản ghi nhạy cảm và đối chiếu với target logs**. Mục tiêu cuối là **truy cập đặc quyền đúng người, đúng phạm vi, đúng thời điểm – với bằng chứng đủ tin cậy để kiểm tra và điều tra**.
