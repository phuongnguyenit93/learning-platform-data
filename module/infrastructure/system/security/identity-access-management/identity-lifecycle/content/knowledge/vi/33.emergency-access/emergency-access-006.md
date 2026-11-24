# Giám sát phiên khẩn cấp trong IAM: theo dõi break-glass, bảo toàn bằng chứng và kết thúc đặc quyền an toàn

**Giám sát phiên khẩn cấp (emergency session monitoring)** là tập hợp hoạt động **quan sát, ghi nhận, cảnh báo, đánh giá và đối soát** những phiên truy cập được mở theo cơ chế **emergency access/break-glass** khi tổ chức cần xử lý sự cố nghiêm trọng hoặc khôi phục khả năng vận hành. Phiên khẩn cấp thường mang quyền lớn, được sử dụng ngoài workflow thông thường hoặc khi một phần hạ tầng xác thực/quản trị không khả dụng; vì vậy nó cần **kiểm soát được ai thực hiện, thực hiện việc gì, trên tài nguyên nào, trong khoảng thời gian nào và quyền còn lại gì sau khi kết thúc**.

Ví dụ, một sự cố làm hệ thống IAM/SSO không thể đăng nhập thông thường. Người vận hành đã được chỉ định sử dụng phương án emergency access để khôi phục dịch vụ xác thực. Kết quả tốt không chỉ là “SSO đã chạy lại” mà còn gồm **bằng chứng phiên khẩn cấp thuộc ai, các thao tác có đúng mục đích, cảnh báo có được xử lý, credential/phiên có được thu hồi hoặc bảo vệ lại, và các thay đổi được hậu kiểm**.

Bài học thuộc chương **Emergency access** của mô-đun **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**, tập trung **quản lý vòng đời danh tính (IAM) theo Joiner–Mover–Leaver**: từ xác minh, tạo tài khoản và cấp quyền đến điều chỉnh khi đổi vai trò, rà soát và thu hồi khi rời tổ chức. Giám sát phiên khẩn cấp liên kết **IdP/SSO, PAM/PIM, SCIM, RBAC/ABAC, các tài khoản dịch vụ/workload, kiểm toán và giảm quyền truy cập tồn dư**.

**Nguyên tắc cốt lõi:** **Break-glass là một ngoại lệ được thiết kế trước, không phải quyền bỏ qua mọi kiểm soát.** Giám sát cần hoạt động tốt trong điều kiện bình thường và có **phương án suy giảm an toàn** khi hệ thống trung tâm gặp sự cố. **“Đã ghi hình phiên” không đồng nghĩa “mọi hành động đều an toàn”**, và **“đã đóng ticket khẩn cấp” không đồng nghĩa “mọi quyền, token và phiên còn sót đã hết hiệu lực”**.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích giám sát phiên emergency access và phân biệt **xác thực, cấp quyền, ghi nhật ký, ghi hình, cảnh báo, can thiệp và hậu kiểm**.
2. Xác định các đối tượng phải gắn với phiên: **actor, subject/account, emergency identity, ticket/incident, target, action, scope, thời gian và policy version**.
3. Mô tả các điểm thu thập giám sát: **PAM/bastion, IdP, PIM, hệ điều hành, cloud audit, API/PEP, database, workload và SIEM**.
4. Thiết kế kiểm soát **trước–trong–sau phiên**: kích hoạt, theo dõi, cảnh báo, chấm dứt, khóa/rotate credential và readback quyền hiệu dụng.
5. Phân biệt **monitoring/recording** với **prevention/enforcement** và nhận diện đường truy cập ngoài PAM/SSO.
6. Phân loại sự kiện nguy hiểm như **vượt phạm vi, tăng quyền, thay policy, vô hiệu log, truy xuất dữ liệu lớn, truy cập chéo tenant và dùng quá hạn**.
7. Bảo vệ **tính toàn vẹn, tính sẵn có, bí mật và giá trị chứng cứ** của log/recording, kể cả khi hạ tầng giám sát bị suy giảm.
8. Xử lý giám sát phiên emergency access của **human privileged account, shared/legacy account và service/workload identity**.
9. Liên kết hậu kiểm với **Joiner–Mover–Leaver**, quyền đặc quyền tồn dư, credential, session/token và ownership.
10. Xây dựng checklist, tình huống và chỉ số để chứng minh phiên đã được **sử dụng đúng mục đích và đóng an toàn**.

## 2. Phiên khẩn cấp khác phiên quản trị thường như thế nào?

**Phiên quản trị thông thường** phục vụ hoạt động được lập kế hoạch hoặc hỗ trợ vận hành; có thể đi qua workflow phê duyệt, IdP/SSO, MFA và PAM/PIM như thường lệ.

**Phiên khẩn cấp** là phiên được sử dụng theo **quy trình ngoại lệ đã định nghĩa** khi có nhu cầu bảo vệ/khôi phục hệ thống khẩn cấp, chẳng hạn:

- IdP hoặc MFA thông thường không khả dụng.
- Công cụ PAM/PIM trung tâm bị gián đoạn và cần truy cập phục hồi.
- Lỗi hạ tầng trọng yếu cần thao tác ngoài quy trình thay đổi thông thường.
- Sự cố bảo mật đòi hành động nhanh để chặn ảnh hưởng hoặc phục hồi.
- Đường quản trị chuẩn đã bị hỏng hoặc thiếu một phụ thuộc thiết yếu.

**Không phải mọi phiên ngoài giờ đều là phiên khẩn cấp.** Một đợt bảo trì có lịch 02:00 vẫn có thể là quyền quản trị thông thường. Ngược lại, phiên lúc 10:00 có thể là break-glass nếu hệ thống đang sự cố và quy trình emergency access được kích hoạt đúng điều kiện.

### 2.1. Ba thứ phải tách ra

| Khái niệm | Trả lời câu hỏi | Ví dụ |
|---|---|---|
| **Emergency authorization** | Vì sao được dùng đường khẩn cấp, ai có thẩm quyền? | Incident INC-204, người trực ứng cứu được chỉ định |
| **Emergency session** | Phiên/kết nối cụ thể bắt đầu, thực hiện và kết thúc thế nào? | Phiên SSH/Bastion hoặc cloud console |
| **Session monitoring** | Quan sát, phát hiện và chứng minh hoạt động gì? | Login event, command/API audit, alert, recording |
| **Post-use review** | Hoạt động có đúng mục đích và các quyền đã được đóng chưa? | Phê duyệt hậu kiểm, readback và rotation |

**Một approval không phải là session**, và **một session record không tự chứng minh việc kích hoạt đã được phê duyệt**. Cần liên kết dữ liệu của cả ba tầng.

## 3. Vì sao phải giám sát chặt khi emergency access được kích hoạt?

Trong tình huống khẩn cấp, tổ chức thường chịu áp lực thời gian, hạ tầng có thể suy giảm và người vận hành cần thao tác với quyền rất lớn. Đó cũng là thời điểm dễ xuất hiện:

- **Lạm dụng đặc quyền:** Dùng emergency role cho nhiệm vụ không nằm trong sự cố.
- **Sai sót do áp lực:** Xóa nhầm dữ liệu, sửa nhầm tenant, áp thay đổi quá rộng.
- **Chiếm quyền phiên:** Credential hoặc token khẩn cấp bị dùng bởi người không có thẩm quyền.
- **Mất giám sát:** Một phần SIEM, IdP, PAM hoặc mạng truyền log không còn hoạt động.
- **Thiếu quy trách nhiệm:** Nhiều người biết mật khẩu break-glass hoặc cùng dùng tài khoản dùng chung.
- **Persistence sau sự cố:** Role, key, session hoặc đường truy cập emergency vẫn còn sau khôi phục.
- **Che dấu hành động:** Người có quyền cao có thể cố tắt audit hoặc sửa chính sách ghi log.
- **Rò rỉ dữ liệu:** Dùng quyền rộng để đọc/export secret hay dữ liệu không liên quan.

**Giám sát giúp phát hiện, điều tra và điều phối phản ứng**, nhưng không thay thế **least privilege, MFA khi khả dụng, hạn thời gian, phê duyệt phù hợp và bảo vệ tài nguyên ở PEP/API/target**.

## 4. Mục tiêu kiểm soát: an toàn và khả năng khôi phục phải cùng tồn tại

Một thiết kế chỉ tập trung “mọi thao tác phải đi qua PAM” có thể tạo **single point of failure**: khi PAM bị sự cố, người vận hành không thể khôi phục chính PAM. Ngược lại, một đường emergency access không được kiểm soát có thể trở thành **cửa hậu thường trực**.

Cần cân bằng:

| Mục tiêu | Cách tiếp cận | Điều cần tránh |
|---|---|---|
| **Availability** | Có đường emergency độc lập với thành phần có thể hỏng | Phụ thuộc chính hệ thống đang bị sự cố để đăng nhập phục hồi |
| **Accountability** | Gắn actor với emergency identity, incident và session | Một shared password không thể quy trách nhiệm |
| **Least privilege** | Scope theo target/action khi kỹ thuật cho phép | Dùng global admin cho mọi sự cố |
| **Monitoring** | Nhật ký đa nguồn, cảnh báo và bằng chứng độc lập | Chỉ tin bản ghi tại target mà admin có thể xóa |
| **Timely response** | Cảnh báo bất thường, người trực giám sát, can thiệp | Ghi hình nhưng không ai xem hoặc xử lý |
| **Safe closure** | Thu hồi grant/credential/session, readback, review thay đổi | Đóng incident rồi để quyền tồn dư |
| **Privacy** | Giảm dữ liệu, phân quyền xem recording, retention | Thu thập token/password/PII tùy tiện |

**Không có cấu hình duy nhất cho mọi tổ chức.** Một trung tâm dữ liệu, cloud tenant và ứng dụng nghiệp vụ có dependency/điểm kiểm soát khác nhau. Các đường khẩn cấp phải được **đánh giá trước sự cố và diễn tập định kỳ theo chính sách**.

## 5. Các thành phần của một phiên khẩn cấp cần được theo dõi

Một bản mô tả tốt nên phân biệt:

| Thành phần | Ý nghĩa | Ví dụ |
|---|---|---|
| **Actor** | Người thật hoặc automation thực hiện thao tác | Nhân viên trực ứng cứu P-2048 |
| **Subject/account** | Identity/account mà target thực sự chấp nhận | `emergency-admin-02` |
| **Emergency role/grant** | Quyền khẩn cấp đang được dùng | `directory.recovery.admin` |
| **Incident/change** | Căn cứ kích hoạt | `INC-204` |
| **Target/resource** | Hệ thống, máy, tenant, dữ liệu | IdP management node, tenant-A |
| **Connection/session ID** | Định danh phiên có thể truy vết | `SES-8801` |
| **Start/stop time** | Mốc bắt đầu và kết thúc thực tế | Timestamp kèm UTC/offset |
| **Action** | Hành động được thực hiện | Thay cấu hình, restart service |
| **Authorization evidence** | Approval, break-glass policy, người trực | `EMG-POL-v5` |
| **Monitoring sources** | Nhật ký/recording nào có sẵn | Bastion, host audit, API, SIEM |
| **Result/impact** | Hệ thống thay đổi thế nào | SSO trở lại hoạt động |
| **Closeout evidence** | Phiên/quyền/credential được xử lý ra sao | Target readback, secret rotation |

### 5.1. Actor không nhất thiết trùng account trên target

Trong legacy system, một người có thể dùng tài khoản `root` hoặc `emergency-admin`. Audit chỉ ghi `user=root` **không đủ quy trách nhiệm cho cá nhân**. Phải có **cơ chế liên kết actor–session–target account**, chẳng hạn đăng ký yêu cầu có xác thực, credential checkout có owner hoặc broker kiểm danh tính.

Nếu không thể đạt attribution đầy đủ khi hạ tầng suy giảm, **phải ghi nhận giới hạn bằng chứng**, không suy đoán người thực hiện từ tên account.

## 6. Kiến trúc giám sát tham chiếu

~~~mermaid
flowchart TD
    INC["Incident / Emergency declaration<br/>Mục đích + owner + phạm vi"] --> E["Emergency authorization<br/>Actor, account, TTL, policy"]
    ID["Identity source / IAM<br/>JML + authorized responders"] --> E
    E --> BR["PAM/Bastion hoặc<br/>đường phục hồi dự phòng"]
    BR --> PEP["PEP / Target enforcement<br/>RBAC/ABAC, resource scope"]
    PEP --> T["IdP / Cloud / OS / DB / App<br/>Tài nguyên cần phục hồi"]
    BR --> L1["Session metadata / recording<br/>Nếu khả dụng"]
    T --> L2["Native target audit<br/>Command / API / config"]
    E --> L3["Approval + activation log"]
    L1 --> SEC["Log pipeline / SIEM<br/>Cảnh báo và correlation"]
    L2 --> SEC
    L3 --> SEC
    SEC --> ON["SOC / Security / Incident lead<br/>Giám sát và can thiệp"]
    T --> VER["Post-use verification<br/>Session, role, credential, token"]
    ON --> VER
    VER --> AUD["Audit evidence + closeout<br/>Unresolved exception nếu có"]
~~~

**Mô hình là logic**, không phải yêu cầu nhất thiết phải triển khai mỗi khối thành một dịch vụ riêng. Trong tình huống **PAM/IdP/SIEM bị lỗi**, đường dự phòng cần được thiết kế **không phụ thuộc tuyệt đối vào thành phần đang hỏng**, trong khi vẫn cố gắng giữ **log cục bộ được bảo vệ, bản ghi dự phòng, nhân chứng/dual control hoặc cơ chế chuyển log khi phục hồi**.

### 6.1. Monitoring cần đa nguồn

Một điểm thu thập duy nhất thường không đủ:

- PAM broker có thể biết **ai mở phiên**, nhưng không biết hết API gọi trực tiếp từ máy.
- Cloud audit biết **API đổi policy**, nhưng không chắc ai đang ngồi sau shared account nếu chưa có correlation.
- Ghi hình RDP có thể thấy màn hình, nhưng khó chứng minh mọi thay đổi của service chạy nền.
- Host audit có thể ghi command, nhưng quyền root có thể ảnh hưởng tính nguyên vẹn log cục bộ.

Nên phối hợp **identity/authorization log, session metadata, native audit, application action logs và hạ tầng log độc lập** phù hợp rủi ro.

## 7. Vòng đời phiên: trước, trong và sau emergency access

~~~mermaid
sequenceDiagram
    autonumber
    actor O as Người ứng cứu
    participant I as Incident lead / Approver
    participant E as Emergency access control
    participant P as PAM/Bastion hoặc fallback
    participant T as Target / API
    participant M as Monitoring / SOC
    participant V as Verification / Audit

    O->>I: Nêu sự cố, nhiệm vụ, target, thời hạn
    I-->>E: Xác nhận kích hoạt theo emergency policy
    E->>E: Kiểm actor, eligibility, scope, TTL
    E->>P: Cấp đường truy cập đã kiểm soát
    P-->>M: Session start, actor, incident, target
    O->>P: Thực hiện công việc khẩn cấp
    P->>T: Thao tác trên tài nguyên
    T-->>M: API/host/config events
    M-->>I: Cảnh báo nếu vượt scope/rủi ro
    O->>P: Kết thúc phiên
    P-->>M: Session end
    E->>T: Revoke role/credential khi thích hợp
    V->>T: Readback, verify sessions/tokens/grants
    T-->>V: Kết quả hiện hành
    V-->>I: Hậu kiểm hành động và quyền tồn dư
    I-->>V: Xác nhận đóng hoặc mở exception
~~~

**Không phải mọi emergency đều có approval đồng bộ** trước khi hành động. Quy trình tổ chức có thể cho **kích hoạt khẩn cấp theo điều kiện được thiết kế trước**, kèm **thông báo tức thời, giám sát độc lập và hậu kiểm bắt buộc**. Không nên mô tả “approval đã có” nếu thực tế mới là **post-use approval pending**.

## 8. Trước phiên: kiểm tra căn cứ khẩn cấp và người thực hiện

Giám sát tốt bắt đầu **trước khi kết nối target**:

1. **Xác minh incident:** ID, thời điểm, ảnh hưởng, mục đích khôi phục.
2. **Xác định actor:** Identity, đơn vị, ca trực, quyền được phép dùng break-glass.
3. **Xác định account/credential:** Emergency account nào, có owner và kiểm soát bảo vệ không.
4. **Giới hạn target/action:** Chỉ những hệ thống và thao tác cần cho mục đích.
5. **Giới hạn thời gian:** Session/activation TTL và điều kiện kết thúc sớm.
6. **Đặt cơ chế giám sát:** Native logs, PAM recording, alert receiver, fallback nếu một luồng mất.
7. **Gắn correlation:** Incident ID, activation ID, session ID và change ticket khi có.
8. **Đặt trách nhiệm:** Ai trực giám sát, ai quyết định can thiệp, ai hậu kiểm.
9. **Kiểm tính sẵn có:** Đường phục hồi có thực sự hoạt động khi IdP/PAM bị lỗi?
10. **Bảo vệ bí mật:** Không dán credential/OTP/private key vào ticket hoặc bản ghi không được bảo vệ.

### 8.1. “Đúng người” khác “đúng tài khoản”

Một emergency account có thể đăng nhập được vì credential hợp lệ, nhưng chưa chứng minh **người cụ thể đang sử dụng đúng được phép**. Khi hệ thống bình thường suy giảm, cần phương án **out-of-band xác minh actor** đã được thiết kế sẵn; nếu không thể xác nhận tuyệt đối, phải ghi rõ mức chắc chắn và áp kiểm soát bổ sung theo rủi ro.

## 9. Trong phiên: giám sát những sự kiện nào?

Một chương trình session monitoring nên ưu tiên **sự kiện có tác động bảo mật**.

| Nhóm sự kiện | Dữ liệu quan sát | Cảnh báo cần cân nhắc |
|---|---|---|
| **Activation/login** | Actor, account, factor, source, time, session | Đăng nhập ngoài quy trình hoặc đồng thời bất thường |
| **Scope/target access** | Target ID, tenant, environment, role | Kết nối target không thuộc incident |
| **Policy/identity changes** | Tạo user, gán role, đổi MFA/SSO config | Tự mở quyền, thay trust hoặc loại bỏ kiểm soát |
| **Credential operations** | Truy cập vault, rotate key, tạo credential | Đọc secret không thuộc nhiệm vụ hoặc tạo key dài hạn |
| **Infrastructure operations** | Deploy, restart, firewall, cluster config | Thay đổi ảnh hưởng nhiều hệ thống ngoài mục tiêu |
| **Data operations** | Read/export/delete bulk, backup, restore | Export nhạy cảm, xóa hoặc thay retention |
| **Audit modifications** | Tắt agent, đổi logging config, xóa dữ liệu audit | Nghi vấn che giấu hoạt động |
| **Delegation/lateral movement** | Tạo session/account/role khác | Mở rộng actor/target ngoài phê duyệt |
| **Session lifecycle** | Idle, reconnect, concurrent use, logout | Phiên kéo dài sau TTL, nối lại không có căn cứ |
| **Monitoring health** | Log agent, broker, collector, timestamp | Mất log đúng lúc privileged activity tăng |
| **Emergency status** | Incident open/closed, control mode | Phiên vẫn active sau khi sự cố được đóng |

**Không ghi mật khẩu hoặc token nguyên văn** chỉ để đạt “khả năng quan sát”. Nên ghi **sự kiện và tham chiếu** đủ cho truy vết, hạn chế thu thập nội dung nhạy cảm không cần thiết.

## 10. Ghi log, ghi hình và giám sát trực tiếp khác nhau ra sao?

| Kiểm soát | Giá trị | Giới hạn |
|---|---|---|
| **Session start/end metadata** | Biết ai kết nối đâu, khi nào, bao lâu | Không chỉ ra mọi hành động trong phiên |
| **Command/audit logs** | Biết lệnh/API/action và kết quả | Có thể thiếu ngữ cảnh hoặc nội dung kết quả |
| **Screen/session recording** | Hỗ trợ hậu kiểm trực quan cho phiên RDP/SSH theo cơ chế phù hợp | Không chắc thấy API/service hoạt động nền; có thể chứa secrets |
| **Live session observation** | Có người/engine theo dõi và phản hồi trong lúc diễn ra | Cần nhân sự, SLO và kênh liên lạc |
| **Rule-based alert** | Phát hiện hành vi ngoài profile/scope nhanh | False positives, false negatives, thiếu context |
| **SIEM correlation** | Ghép nhiều nguồn để hiểu chuỗi hành động | Phụ thuộc thời gian/sự kiện và data quality |
| **PEP/command controls** | Ngăn hành động không được phép | Chỉ bảo vệ các đường thực thi được phủ |
| **Post-use certification** | Xác minh lý do, thao tác, kết quả và quyền tồn dư | Phát hiện sau hành động không ngăn được mọi thiệt hại |

**Ghi hình ≠ chặn thao tác.** Một phiên có recording đầy đủ vẫn có thể thực hiện hành động phá hoại. Đối với tác vụ nhạy cảm, cần **policy enforcement và hạn quyền** song song giám sát.

### 10.1. SSH, RDP, web console, API và automation

- **SSH/shell:** Có thể giám sát kết nối, lệnh, host audit và thay đổi file/config; command log không luôn phản ánh tác động của script phức tạp.
- **RDP/GUI:** Recording giúp thấy thao tác nhưng khó tìm kiếm; native audit bổ sung object/action cụ thể.
- **Cloud console:** Cần cloud control-plane API audit vì nhiều thay đổi xảy ra qua request nền, không chỉ click.
- **Database:** Audit truy vấn/DDL/role change phù hợp; screen recording không thay query audit.
- **Kubernetes:** API audit, RBAC/namespace, workload logs; cần phân biệt actor từ CLI và service account thực thi.
- **Ứng dụng web:** PEP/action/resource logs, không chỉ login IdP.
- **Automation/script:** Gắn deployment/job identity, caller, change ID và API events; không nhất thiết có màn hình để ghi hình.

**Không áp một công cụ recording chung rồi tuyên bố bao phủ toàn bộ đường truy cập.**

## 11. Correlation: nối người với account, phiên và thay đổi

Emergency access có thể trải qua nhiều chặng:

~~~text
Actor người: P-2048
  -> Emergency activation EMG-101
  -> PAM session SES-8801
  -> Target login: emergency-admin-02
  -> Cloud API request REQ-77
  -> Changed resource: idp-policy-prod
  -> Incident: INC-204
  -> Post-use review: REV-330
~~~

Nếu chỉ giữ từng log độc lập, người điều tra khó trả lời **ai đã sửa policy nào vì incident nào**.

### 11.1. Các ID nên thống nhất

- `actorId`: Identity của người thực hiện đã được xác minh.
- `subjectId`/`targetAccountId`: Account target sử dụng.
- `emergencyGrantId` hoặc `activationId`.
- `sessionId` và nếu có `parentSessionId`.
- `incidentId`/`changeId`.
- `targetId`, `resourceId`, `tenantId`.
- `requestId`/`traceId` cho API.
- `policyVersion` và trạng thái approval/review.

**Không dùng tên hiển thị/email đơn thuần làm khóa correlation** nếu có thể thay đổi hoặc tái sử dụng. Dùng ID ổn định và kiểm mapping theo nguồn danh tính.

### 11.2. Đồng bộ thời gian

Cần log **timestamp kèm offset/UTC** và biết mức sai lệch đồng hồ giữa các hệ thống. Nếu IdP log theo UTC nhưng server ghi giờ địa phương sai 12 phút, một chuỗi hành động có thể bị sắp xếp sai. Nên giám sát **time synchronization health** và ghi nhận clock skew khi phân tích.

## 12. Mô hình sự kiện tối thiểu có thể kiểm toán

Một bản ghi JSON ví dụ về bắt đầu phiên:

~~~json
{
  "eventType": "EMERGENCY_SESSION_STARTED",
  "eventId": "EVT-2026-3019",
  "time": "2026-12-08T21:04:00+07:00",
  "incidentId": "INC-204",
  "activationId": "EMG-101",
  "sessionId": "SES-8801",
  "actor": {
    "canonicalId": "P-2048",
    "kind": "HUMAN",
    "verificationMethodRef": "OUT_OF_BAND_VERIFIED"
  },
  "target": {
    "systemId": "idp-prod-01",
    "accountId": "emergency-admin-02",
    "environment": "production",
    "tenantId": "company-vn"
  },
  "requestedScope": [
    "identity-service.restart",
    "identity-config.read"
  ],
  "emergencyPolicyVersion": "emergency-v5",
  "plannedExpiresAt": "2026-12-08T22:00:00+07:00",
  "monitoring": {
    "pamRecording": "AVAILABLE",
    "targetAudit": "AVAILABLE",
    "centralLogDelivery": "DEGRADED",
    "fallbackRecordRef": "FALLBACK-330"
  },
  "result": "STARTED",
  "correlationId": "CORR-204-01"
}
~~~

Đây là **dữ liệu minh họa**, không phải nhật ký đã xảy ra hoặc schema chuẩn. Giá trị `verificationMethodRef` là tham chiếu phương pháp, **không được chứa câu trả lời bí mật** hoặc dữ liệu xác thực nhạy cảm.

### 12.1. Bản ghi kết thúc khác bản ghi bắt đầu

Session start event chỉ chứng minh **phiên đã bắt đầu**. Session end/closeout event cần xác định:

- `endedAt` và lý do kết thúc.
- Session bị logout bình thường, timeout, force termination hay mất kết nối.
- Target còn chấp nhận credential/token hay không.
- Quyền emergency còn ở role/group/direct ACL/PIM không.
- Các alert còn mở, log gaps và post-use review status.
- Readback hoặc ngoại lệ có owner/expiry.

**Không suy “mất kết nối với PAM” = “session ở target đã chấm dứt”**. Một số giao thức/phiên có thể tiếp tục tồn tại tùy kiến trúc.

## 13. Nhóm cảnh báo ưu tiên trong phiên khẩn cấp

Không cần cảnh báo mọi click chuột; nên ưu tiên những dấu hiệu **vượt căn cứ khẩn cấp hoặc gây tác động lớn**.

### 13.1. Cảnh báo về căn cứ và identity

- Emergency access được dùng khi **không có incident hợp lệ** hoặc lý do không khớp.
- Account khẩn cấp được dùng **ngoài danh sách actor đủ điều kiện**.
- Một emergency account đồng thời được sử dụng từ **hai nguồn độc lập** trái quy trình.
- Người trực đã **Mover/Leaver** nhưng credential còn được dùng.
- Có dấu hiệu credential bị chia sẻ, session bị chiếm hoặc authenticator bất thường.

### 13.2. Cảnh báo về privilege/scope

- Thay đổi policy IAM, federation trust, token signing config không nằm trong mục tiêu.
- Tạo admin mới hoặc cấp role rộng cho chính mình.
- Truy cập resource **khác tenant/project/environment** so với incident.
- Tải/export dữ liệu nhạy cảm với quy mô vượt nhu cầu khôi phục.
- Thao tác xóa backup/log hoặc thay retention không có căn cứ.
- Tạo credential dài hạn để duy trì truy cập sau khi phiên kết thúc.

### 13.3. Cảnh báo về giám sát và vòng đời

- Tắt/gián đoạn audit agent ngay khi phiên admin bắt đầu.
- Log pipeline bị mất hoặc lệch thời gian bất thường.
- Phiên tiếp tục hoạt động **sau mốc hết hạn** hoặc sau khi incident được đóng.
- Token/credential emergency vẫn cho truy cập sau quyết định thu hồi.
- Session recording báo hoàn thành nhưng target audit không có dữ liệu tương ứng.

**Cảnh báo phải có đường tới người chịu trách nhiệm**, thay vì tạo hàng nghìn thông báo không ai xác nhận.

## 14. Quy tắc giám sát phải đánh giá đúng ngữ cảnh

Một rule “mọi thay đổi IAM policy đều đáng ngờ” có thể tạo false positive trong chính sự cố IdP. Ngược lại, một rule “mọi thay đổi trong emergency đều hợp lệ” là quá rộng.

Ví dụ:

~~~text
Incident INC-204:
  Mục tiêu: khôi phục dịch vụ xác thực IdP.
  Target: idp-prod-01.
  Allowed actions: read config, restart identity service.
  Planned window: 21:00–22:00.

Action A: restart service trên idp-prod-01
  -> Có thể thuộc phạm vi, vẫn cần ghi audit.

Action B: cấp global admin cho một external account
  -> Vượt phạm vi, cần cảnh báo nghiêm trọng.

Action C: xóa SIEM logs của tháng trước
  -> Không liên quan mục tiêu, cần chặn/điều tra theo policy.

Action D: tiếp tục sửa config lúc 23:00
  -> Vượt cửa sổ; kiểm approval/extension hợp lệ hay không.
~~~

**Không biến mẫu thành engine tự phán quyết:** Trong thực tế cần xác minh semantics của action, owner, target, policy và trạng thái incident. Một số hoạt động bất thường có thể là **biện pháp khôi phục hợp lệ đã được chỉ huy sự cố cho phép**; phải có quy trình cập nhật scope/authorization, không bỏ log.

## 15. Mức độ cảnh báo và tuyến phản ứng

| Mức minh họa | Ví dụ | Tuyến hành động |
|---|---|---|
| **Thông tin** | Session bắt đầu/kết thúc đúng policy | Ghi nhận, correlation |
| **Cần chú ý** | Reconnect, session kéo dài, log chậm | Incident lead/PAM operator xác minh |
| **Cao** | Target ngoài scope, role vượt nhu cầu | SOC/security + emergency approver xem xét can thiệp |
| **Nghiêm trọng** | Tạo admin trái phép, tắt audit, nghi chiếm session | Security incident response theo policy |
| **Mất khả năng giám sát** | Cả log và recording không còn, phiên vẫn privileged | Kích hoạt fallback/kiểm soát bù trừ hoặc hạn chế theo mức rủi ro |

**Không có ngưỡng thời gian/số lượng chung** áp dụng mọi hệ thống. Việc chỉ định severity, SLA phản hồi và quyền chấm dứt phiên cần được thống nhất trước với nhóm ứng cứu.

### 15.1. Can thiệp khác quan sát

Một người trực SOC có thể **nhận alert** nhưng không có quyền **kill session**. Quy trình phải xác định:

- Ai được gọi người vận hành để tạm dừng?
- Ai có quyền chấm dứt phiên/khóa credential?
- Khi nào ưu tiên ngăn hành vi độc hại, khi nào cần cân nhắc nguy cơ gây outage?
- Ai lưu bằng chứng và hậu kiểm quyết định can thiệp?
- Nếu target đang trong quá trình phục hồi, làm sao tránh phá hỏng bước khôi phục quan trọng?

**Không để quyền can thiệp được cấp tùy tiện cho bất kỳ ai xem dashboard.**

## 16. Separation of Duties trong giám sát emergency access

Các vai trò nên phân biệt theo rủi ro:

| Vai trò | Nhiệm vụ | Điều cần kiểm soát |
|---|---|---|
| **Incident lead** | Xác định mục tiêu và ưu tiên khôi phục | Không mặc định có quyền sửa mọi evidence |
| **Emergency operator** | Thực hiện thao tác trên target | Không tự kiểm chứng mọi hành động của chính mình |
| **Emergency approver/risk owner** | Xác nhận hoặc hậu kiểm cơ sở sử dụng | Cần độc lập khi policy yêu cầu |
| **PAM/credential custodian** | Quản lý đường cấp và secret | Không đồng thời tùy ý xóa audit |
| **SOC/monitoring operator** | Theo dõi, triage và cảnh báo | Cần hiểu giới hạn quyền truy cập recording |
| **Application/target owner** | Kiểm tính đúng đắn của thay đổi | Không tự sửa chứng cứ không để lại dấu |
| **Audit/security reviewer** | Hậu kiểm, bằng chứng và phát hiện | Có quyền đọc phù hợp, độc lập với người thao tác |

### 16.1. Dual control và four-eyes

Trong một số môi trường, activation hoặc thao tác nhạy cảm cần **hai người**: người thực hiện và người xác nhận độc lập. Khi hệ thống bị lỗi, quy trình có thể sử dụng **người trực giám sát/biên bản out-of-band** nếu đã được phê duyệt. Điều này không có nghĩa mọi phiên đều phải có hai người theo cùng một hình thức; lựa chọn tùy **rủi ro và khả năng phục hồi**.

### 16.2. Không tự hậu kiểm phiên của chính mình

Nếu một người vừa dùng break-glass, vừa tự đánh dấu mọi hành động là hợp lệ và tự xóa recording, SoD đã bị phá. Hậu kiểm cần **reviewer đủ thẩm quyền, tham chiếu sự cố và bằng chứng từ nguồn không hoàn toàn do operator kiểm soát**.

## 17. Hạ tầng giám sát suy giảm: không phải lý do dừng ghi nhận hoàn toàn

Emergency access có thể xảy ra đúng lúc:

- Central SIEM mất kết nối.
- PAM broker không hoạt động.
- IdP/SSO/MFA platform chưa phục hồi.
- Network segmentation hoặc DNS gặp lỗi.
- Time sync bị ảnh hưởng.
- Cloud logging chuyển chậm hoặc tạm lỗi.

Một thiết kế có khả năng chống chịu nên xác định **điều kiện tối thiểu được phép vận hành** và **phương án fallback**.

| Thành phần hỏng | Rủi ro | Phương án cân nhắc |
|---|---|---|
| **SIEM collector** | Không nhận alert thời gian thực | Local audit buffer được bảo vệ, out-of-band notification, forward sau phục hồi |
| **PAM** | Mất session broker/recording | Đường emergency được phê duyệt riêng với native audit và giám sát bổ sung |
| **IdP** | Không xác thực qua SSO | Emergency identity độc lập đã được kiểm soát, out-of-band actor verification |
| **Time sync** | Khó xác định thứ tự thao tác | Ghi offset và clock health/skew, đối soát sau |
| **Target audit agent** | Thiếu command/action telemetry | Dùng cloud control-plane API log, broker hoặc kênh thay thế nếu có |
| **Log storage** | Nguy cơ mất bằng chứng | Spool/buffer có giới hạn và bảo vệ, kiểm integrity sau khi đẩy lên |
| **Alert delivery** | SOC không thấy nguy cơ | Kênh paging/phone riêng, danh sách người nhận cập nhật |

### 17.1. Không giả định fallback luôn hoạt động

Một kênh “dự phòng” phụ thuộc cùng network, IdP, vault hoặc cùng service account có thể hỏng đồng thời. Cần **diễn tập tình huống mất đồng thời các dependency** và công bố những điểm giám sát không thể bảo đảm.

### 17.2. Fail-open và fail-closed phải được quyết định trước

- **Fail-open tùy tiện** khi PAM/SIEM mất kết nối có thể biến emergency path thành cửa hậu.
- **Fail-closed cứng nhắc** có thể ngăn khôi phục hạ tầng trọng yếu, kéo dài ảnh hưởng sự cố.

Tổ chức cần **risk-based degraded mode được phê duyệt trước**, bao gồm actor, target, action, thời gian, cơ chế xác minh, ghi nhận thay thế và hậu kiểm. **Không viết rule `if monitoringDown then PERMIT_ALL`.**

## 18. Bảo toàn tính toàn vẹn của log và recording

Người dùng emergency access có thể có quyền `root` hoặc cloud admin; nếu log chỉ ở host mà chính họ quản trị, họ có thể tác động tới bằng chứng.

Các biện pháp cần cân nhắc:

1. **Đẩy log ra ngoài target** tới hệ thống có phân quyền độc lập khi khả dụng.
2. Dùng **append-only/WORM** hoặc biện pháp chống sửa/xóa thích hợp theo nền tảng.
3. **Mã hóa khi truyền/lưu**, kiểm soát khóa và quyền xem riêng.
4. **Dấu thời gian/correlation** từ nguồn đáng tin, giám sát clock skew.
5. **Integrity verification** bằng digest/signature hoặc cơ chế sản phẩm hỗ trợ khi cần.
6. Phân tách người quản trị target với người có quyền **xóa audit/retention**.
7. Ghi nhận **gaps, drop rate, pipeline health** và việc thiếu bằng chứng.
8. Khi khôi phục, **replay/forward buffer** có kiểm soát trùng lặp và kiểm nguồn.
9. Có chính sách **retention, legal hold và chain of custody** cho điều tra.
10. Không tuyên bố “tamper-proof” tuyệt đối nếu phụ thuộc bảo vệ vẫn thuộc cùng quyền admin.

### 18.1. Integrity không đồng nghĩa bí mật

Một hash có thể hỗ trợ phát hiện recording thay đổi, nhưng không che nội dung mật khẩu đang hiện trên màn hình. Cần **masking, encryption, access review** với recording và log, đồng thời bảo vệ integrity riêng.

### 18.2. Chứng cứ có giới hạn phải được nói rõ

Nếu một phiên dùng đường local console trong lúc máy chủ tách mạng và chỉ có nhật ký host, báo cáo cần nêu:

- Bằng chứng nào có thật.
- Nguồn nào không thu thập được.
- Ai đã kiểm trực tiếp hoặc biên bản out-of-band nào tồn tại.
- Giới hạn khả năng suy ra **mọi hành động**.
- Biện pháp khắc phục/điều tra bổ sung.

**Không tự điền “recorded=true” chỉ để vượt gate kiểm toán.**

## 19. Quyền riêng tư và bảo vệ dữ liệu trong giám sát phiên

Emergency recording có thể vô tình chứa:

- Mật khẩu, OTP, token, API key hoặc private key.
- Thông tin khách hàng/nhân sự trên màn hình.
- Dữ liệu nghiệp vụ nhạy cảm.
- Thông tin từ chat, ticket hoặc nội dung clipboard.
- Dấu vết cá nhân không liên quan sự cố.

Vì vậy cần:

- **Mục đích rõ:** Thu thập để bảo mật, điều tra và kiểm toán theo chính sách, không giám sát vô hạn.
- **Giảm thiểu dữ liệu:** Chỉ ghi những trường cần để truy vết; ưu tiên event metadata khi đủ.
- **Masking/redaction:** Bảo vệ vùng/input nhạy cảm nếu nền tảng hỗ trợ; tránh tạo một bản ghi chứa secret.
- **Giới hạn truy cập:** Chỉ SOC, security reviewer, audit hoặc owner có thẩm quyền được xem.
- **Lịch sử truy cập recording:** Ghi ai mở, xuất và chia sẻ chứng cứ.
- **Retention/deletion:** Theo chính sách, yêu cầu pháp lý và điều tra.
- **Xuất chứng cứ:** Dùng bản sao có kiểm soát, hạn chế phát tán.
- **Secret exposure handling:** Nếu recording vô tình chứa credential, xử lý theo quy trình lộ secret.

**Không vì lý do “emergency” mà đăng nhập/đính kèm credential nguyên văn vào ticket hoặc log**.

## 20. Ghi hình có thể bị bỏ qua bởi đường truy cập khác

Một tổ chức có PAM recording cho SSH, nhưng người dùng khẩn cấp có thể:

- Truy cập API trực tiếp bằng access token.
- Dùng cloud console khác với target nằm sau bastion.
- Kết nối local console ngoài PAM khi PAM gặp sự cố.
- Chạy script/CI job tạo hoạt động nền.
- Dùng database tool với account local.
- Dùng key/certificate đã biết từ trước.

Những đường truy cập này có thể **không xuất hiện trong recording của một phiên SSH**. Cần **kiểm kê và hạn chế các đường bypass** theo risk, đồng thời thu native audit trên từng hệ thống.

### 20.1. “Không có recording” không đồng nghĩa “không có hành động”

Nếu emergency actor không đi qua PAM, số phút recording bằng 0 không chứng minh không sử dụng quyền. Cần đối soát **IdP/direct login logs, cloud API events, local audit, session/token issuance và resource state changes**.

## 21. Phát hiện thao tác ngoài mục đích incident

Một phiên emergency có thể hợp lệ ở đầu phiên nhưng hành động về sau vượt phạm vi.

Cần đối chiếu ba tập:

~~~text
ApprovedPurpose / AuthorizedScope:
  Mục tiêu và hành động được phép của incident

ObservedActions:
  Hành động thực tế từ PAM/target/API logs

CurrentPolicy / JML State:
  Trạng thái actor, quyền còn hiệu lực,
  tenant/resource, thời gian, SoD

Review:
  ObservedActions trong phạm vi hợp lệ?
  Có thay đổi quyền, secret hoặc dữ liệu ngoài mục đích?
  Có hành động không thể quan sát hoặc thiếu log?
~~~

### 21.1. Không chỉ dựa vào danh sách tên lệnh

Một command `cat` hoặc `curl` có thể vô hại hoặc liên quan dữ liệu nhạy cảm tùy target/path/endpoint. Một API `POST` có thể tạo account hoặc chạy task được duyệt. Cần **ngữ cảnh của action/resource và dữ liệu app**, không chỉ match chuỗi ký tự thô.

### 21.2. Tín hiệu cần xác minh

- Truy cập khác tenant/region/cluster.
- Tạo thêm account/credential không nằm trong kế hoạch phục hồi.
- Tắt/đổi logging, alert hoặc backup.
- Export dữ liệu lớn không cần cho khôi phục.
- Kéo dài phiên/activation sau khi incident kết thúc.
- Đổi owner hoặc quyền review để tránh kiểm soát.

**Cảnh báo không tự chứng minh vi phạm.** Người triage cần đối chiếu thực tế sự cố và authority, rồi phân loại benign, authorized exception, policy violation hoặc incident.

## 22. Điều kiện kết thúc phiên và chấm dứt quyền

Một phiên khẩn cấp không nên tồn tại chỉ vì người vận hành chưa bấm logout.

### 22.1. Những mốc cần theo dõi

- Incident đã được phục hồi/đóng.
- Hoạt động được duyệt đã hoàn tất.
- `plannedExpiresAt` của emergency activation.
- Actor mất eligibility vì Mover/Leaver, account bị suspend hoặc security hold.
- Risk owner/security yêu cầu dừng.
- Session idle/concurrent-use vượt chính sách.
- Credential có dấu hiệu lộ hoặc dùng ngoài phạm vi.

### 22.2. Đóng kết nối không đủ

Cần phân biệt:

| Hành động | Có thể làm gì | Còn phải kiểm |
|---|---|---|
| **PAM session terminated** | Kết thúc phiên qua broker | Có phiên target trực tiếp khác không? |
| **IdP logout / account disabled** | Ngăn xác thực mới theo thiết kế | Access token/local session còn hạn? |
| **PIM activation expired** | Hết quyền nâng theo PIM | Target có cache/phiên admin còn hoạt động? |
| **SCIM role removed** | Gỡ group/role ở target hỗ trợ | Direct ACL và local account khác? |
| **Password rotated** | Vô hiệu hóa mật khẩu cũ khi target áp đúng | SSH key/cert/token khác còn? |
| **SSH/API key revoked** | Khóa một credential | Session đã mở hoặc grant khác còn? |
| **Incident closed** | Kết thúc quản lý sự cố | Emergency account và grants có còn quyền? |

**Điều kiện đóng về bảo mật** cần là **desired access và effective access đã phù hợp trong phạm vi bắt buộc**, có audit của những ngoại lệ còn mở.

## 23. Thu hồi token và session cũ sau emergency access

Một phiên khẩn cấp có thể sinh ra nhiều **đường truy cập tiếp tục**:

- Access token JWT còn hạn.
- Refresh token có thể xin access token mới.
- Local cookie/session của ứng dụng.
- Cloud console/CLI session credential.
- SSH key, certificate, API key hoặc PAT.
- Database connection hoặc tunnel.
- Role/group/ACL được thay đổi trong phiên.
- Credential backup hoặc secret đã được checkout.

Khi đóng, cần xác định:

1. **Credential nào đã dùng, cấp mới hoặc từng lộ?**
2. **Session nào còn active tại target, kể cả ngoài PAM?**
3. **Role/entitlement nào còn và qua nguồn grant nào?**
4. **Resource Server kiểm trạng thái hiện hành hay tin token tự chứa đến expiry?**
5. **Có thể chấm dứt/rotate/revoke an toàn mà không phá hoạt động phục hồi khác không?**

Không khẳng định “logout ngay = mọi JWT đã mất hiệu lực”. Thiết kế xác minh phải phù hợp **cơ chế token validation/revocation và cache** của hệ thống.

## 24. Post-use review: hậu kiểm bắt buộc, không chỉ đóng ticket

Sau sự cố, hoạt động hậu kiểm nên được thực hiện bởi **người có thẩm quyền độc lập theo policy**.

### 24.1. Các câu hỏi cần trả lời

1. Tại sao đường emergency được kích hoạt? Có điều kiện đúng policy?
2. Ai thực hiện và actor–account mapping có đủ chứng cứ?
3. Session bắt đầu/kết thúc lúc nào; có trùng hoạt động khác không?
4. Mọi target/action có khớp incident và giới hạn được phê duyệt?
5. Có bước mở rộng scope hoặc privilege không; đã được cập nhật approval?
6. Có cảnh báo nào chưa được triage hoặc thiếu log?
7. Có đọc/đổi secret, tạo key/role/account mới không?
8. Có thay đổi chính sách hoặc hạ tầng cần review/change management?
9. Session/token/grant/credential đã được đóng hay rotate theo policy?
10. Có **bằng chứng readback**, anomaly findings, owner và deadline ngoại lệ?
11. Có thể cải thiện đường phục hồi hoặc giảm nhu cầu dùng break-glass lần sau?
12. Review có phát hiện gian lận, lỗi quy trình hoặc vấn đề dữ liệu audit không?

### 24.2. Tách khôi phục dịch vụ với đóng bảo mật

**Service restored** là mốc khôi phục hoạt động. **Emergency access closed and verified** là mốc khác. Có thể dịch vụ hoạt động lúc 22:00 nhưng một direct grant/credential còn phải xử lý đến 22:30 theo kế hoạch đã phê duyệt. Tình trạng pending cần được công bố, không ép hai mốc thành một.

## 25. Vòng đời JML và quyền sử dụng emergency access

Khả năng dùng tài khoản khẩn cấp phải có **danh sách actor đủ điều kiện**, được kiểm tra và cập nhật từ IAM/HR/VMS và governance của đội ứng cứu.

### 25.1. Joiner

Người mới vào đội vận hành:

- Được identity proofing và đăng ký MFA/credential theo chính sách.
- **Không tự có quyền break-glass** chỉ vì thuộc bộ phận IT.
- Chỉ được thêm vào danh sách người ứng cứu khi training, approval và role eligibility hợp lệ.
- Có thể cần kiểm tra diễn tập, giới hạn target và phân tách account thường/admin.
- Truy cập trước mốc `effectiveAt` không tự được phép vì account đã tạo sẵn.

### 25.2. Mover

Khi SRE chuyển sang bộ phận khác:

- Gỡ quyền có thể **kích hoạt emergency account/role** không còn nhiệm vụ.
- Thu hồi credential/checkout eligibility, PAM/PIM role, nhóm IdP hoặc local emergency mapping liên quan.
- Kiểm các phiên/token hiện hành hoặc quyền đặc biệt từng có.
- Có thể cần bàn giao on-call theo ngoại lệ **time-bound** có owner.
- Review ai thay thế làm operator/approver/monitoring reviewer.
- Đối soát quyền hiệu dụng và khả năng mở lại phiên sau Mover.

### 25.3. Leaver

Khi người ứng cứu rời tổ chức:

- Thu hồi account/persona/eligible role và phiên đang mở theo chính sách.
- Đánh giá credential emergency từng được biết/checkout; rotate hoặc revoke ở target khi cần.
- Kiểm local account, PAT, SSH keys, cloud sessions, direct role và secret access.
- Thay người chịu trách nhiệm phân phát/giám sát credential khẩn cấp.
- Đảm bảo vẫn còn **đủ nhân sự và phương án emergency access hợp lệ** sau thu hồi.
- Lưu readback và bằng chứng mọi đường truy cập bắt buộc đã bị chặn.

**Không chờ access review định kỳ** mới xử lý Leaver. Sự kiện HR/VMS có thẩm quyền phải kích hoạt JML theo thời điểm quy định.

## 26. Session monitoring cho service account và workload

**Emergency access không phải lúc nào cũng do con người thao tác trực tiếp**. Một automation/workload có thể chạy job khôi phục, rotate key, rollback deployment hoặc restart service.

| Đặc tính | Phiên con người | Hoạt động workload khẩn cấp |
|---|---|---|
| **Subject** | Human identity/emergency persona | Workload/service principal |
| **Actor thực tế** | Người vận hành | Job, deployment và người kích hoạt nếu có |
| **Authenticator** | MFA/passkey/credential đặc quyền theo policy | Managed identity, certificate, client credential |
| **Session** | SSH/RDP/browser/PAM | API calls/job run/token context |
| **Recording** | Có thể có ghi màn hình/terminal | Thường dùng audit API, job logs, trace |
| **Scope** | Action/target/time | API audience, resource, environment, TTL |
| **Owner** | Incident lead và operator | Service owner/technical approver |
| **Closure** | Logout, revoke grant và kiểm session | Kết thúc job, revoke token/secret/role khi cần |

### 26.1. Cần nối job với người yêu cầu

Một job `restore-identity-service` có thể dùng service principal với quyền cao. Log chỉ ghi `client_id=svc-recovery` không trả lời **ai ra lệnh chạy job, theo incident nào và có approval không**.

Nên gắn:

~~~text
Incident ID
  -> Người yêu cầu / người phê duyệt
  -> Job run ID + deployment version
  -> Workload identity / client ID
  -> API/target action + resource
  -> Log và kết quả khôi phục
  -> Credential/grant cleanup
~~~

Nếu job tự kích hoạt theo trigger đã được duyệt, cần ghi **policy/trigger version**, không tự bịa actor là một cá nhân không thực hiện hành động.

### 26.2. Owner workload Leaver

Người tạo job đã Leaver không có nghĩa xóa ngay workload recovery production. Cần **chuyển owner, kiểm dependency và bảo vệ/rotate credential có rủi ro**, đồng thời không để **ownerless privileged service principal** tồn tại không kiểm soát.

## 27. Direct local emergency account và shared credential

Một số hệ thống cần **local emergency account** vì đường SSO có thể mất. Đây là lựa chọn kiến trúc phụ thuộc **khả năng phục hồi**, nhưng tăng khó khăn quy trách nhiệm.

### 27.1. Giảm rủi ro khi dùng account local

- Có inventory, owner, mục đích và target rõ.
- Đặt phương án bảo vệ credential và kiểm tra định kỳ.
- Giới hạn người được tiếp cận credential theo quy trình.
- Nếu cần checkout, lưu actor/incident/timestamp và cơ chế trả/rotate.
- Ghi native target audit và lưu log ngoài target khi khả dụng.
- Hạn chế network/console/host path theo điều kiện khẩn cấp.
- Theo dõi login trực tiếp **ngoài phiên khẩn cấp** và báo động.
- Hậu kiểm, thay credential và session cleanup theo policy.
- Cân nhắc thay shared identity bằng khả năng gắn cá nhân khi hệ thống cho phép.

**Một shared password được nhiều người biết không thể cho attribution hoàn hảo** chỉ bằng host log. Cần bằng chứng bổ trợ và thừa nhận giới hạn chứng cứ.

### 27.2. Không “xóa emergency account” chỉ vì không dùng

Đường khẩn cấp có thể được thiết kế để sử dụng rất hiếm. Review cần đánh giá **khả năng sử dụng đúng lúc, người có quyền, bảo vệ credential, scope và giám sát**, không dựa đơn thuần vào last-login.

## 28. Chính sách giám sát phiên khẩn cấp có cấu trúc

Một tổ chức nên văn bản hóa:

- Các tình huống được phép kích hoạt.
- Cách xác minh actor/incident khi IdP hoặc approval service lỗi.
- Danh mục emergency accounts/roles/targets.
- Yêu cầu monitoring cho từng loại session/giao thức.
- Mức log tối thiểu, masking, lưu trữ và retention.
- Tín hiệu alert và người nhận, SLA triage.
- Cơ chế degraded/fallback và cách ghi gaps.
- Quyền kết thúc phiên, revoke và phối hợp incident lead.
- Post-use review deadline, reviewer, SoD và closeout evidence.
- Quy trình diễn tập và thay ownership khi JML.

### 28.1. Ví dụ policy YAML (minh họa)

~~~yaml
# Ví dụ học tập, không phải schema cấu hình của sản phẩm.
policyId: emergency-session-monitoring-v1
owner: security-iam-governance
scope:
  allowedPurposes: [identity-recovery, critical-service-restoration]
  privilegedSubjects: [approved-human-responders, recovery-workloads]
  permittedTargets: [registered-critical-systems]
activation:
  incidentReferenceRequired: true
  actorAttributionRequired: true
  timeBound: true
  onNormalApprovalUnavailable: USE_PREAPPROVED_FALLBACK
monitoring:
  minimum:
    - activation-and-authorization-events
    - session-start-and-end
    - target-native-privileged-actions
    - monitoring-health-state
  independentLogPathWhenAvailable: true
  onCollectorFailure: PROTECTED_LOCAL_BUFFER_AND_OUT_OF_BAND_ALERT
  prohibitSecretCaptureWherePossible: true
  gapsRequirePostUseReview: true
alerts:
  - out-of-scope-target
  - unauthorized-privilege-change
  - audit-disable-or-tamper
  - credential-created-outside-incident
  - session-past-approved-end
  - current-operator-ineligible
termination:
  verifyTargetSessions: true
  verifyRolesAndDirectGrants: true
  assessTokenCredentialRotation: true
postUse:
  independentReviewerRequiredByRisk: true
  evidenceAndExceptionsRequired: true
  noAutoCloseOnMissingReadback: true
~~~

Đây là **mẫu định nghĩa ý định kiểm soát**. Cần kiểm khả năng thực tế của các sản phẩm IAM/PAM/cloud/host, xác định ngưỡng rủi ro, trách nhiệm và thời hạn theo chính sách của tổ chức.

## 29. Mã giả đánh giá cảnh báo phiên khẩn cấp

Ví dụ Python chỉ minh họa cách **đối chiếu tín hiệu với căn cứ đã xác minh**; không tự cấp quyền hoặc chấm dứt phiên production.

~~~python
# Pseudocode học tập, không phải SOC/PAM production engine.
def evaluate_emergency_event(event, authoritative):
    issues = []

    activation = authoritative.activation(event["activationId"])
    actor = authoritative.actor(event["actorId"])
    incident = authoritative.incident(event["incidentId"])

    if activation is None or incident is None:
        issues.append("UNVERIFIED_EMERGENCY_CONTEXT")
    else:
        if not incident.is_open_or_authorized_closeout():
            issues.append("INCIDENT_NOT_ACTIVE")

        if not activation.includes_target(event["targetId"]):
            issues.append("OUT_OF_SCOPE_TARGET")

        if not activation.includes_action(event["action"]):
            issues.append("OUT_OF_SCOPE_ACTION")

        if event["time"] > activation.expires_at:
            issues.append("ACTION_AFTER_APPROVED_EXPIRY")

    if actor is None or not actor.eligible_for_emergency_access():
        issues.append("INELIGIBLE_OR_UNKNOWN_ACTOR")

    if event.get("auditTamperSignal"):
        issues.append("POTENTIAL_AUDIT_TAMPER")

    if event.get("monitoringState") == "UNAVAILABLE":
        issues.append("MONITORING_GAP")

    # Đây là tín hiệu để người có thẩm quyền triage,
    # KHÔNG kết luận vi phạm chỉ từ các mã cảnh báo.
    return {
        "alert": bool(issues),
        "reasonCodes": issues,
        "requiresHumanTriage": bool(issues)
    }


# Thiết kế thực tế cần chuẩn hóa timestamp/clock skew,
# concurrency/idempotency, trusted source validation,
# logging integrity, policy version và escalation workflow.
# Không đưa dữ liệu tự khai của client thành evidence đáng tin.
~~~

### 29.1. Hạn chế của mô hình

- `activation` và `incident` phải lấy từ nguồn có thẩm quyền, không tin JSON client.
- Event có thể đến trễ hoặc thiếu; không suy ra vắng sự kiện là vắng hành động.
- Timestamp phải được parse đúng offset và kiểm độ lệch đồng hồ.
- Triage cần kiểm sự thay đổi scope được chấp thuận giữa sự cố.
- Cần nhận diện **subject vs actor** trong delegated/shared-account context.
- Các biện pháp **block/terminate** phải qua policy và người/automation được ủy quyền.

## 30. Giám sát trực tiếp và phản ứng theo rủi ro

Một quy trình live monitoring có thể gồm:

1. Bắt đầu phiên, gửi event cho SOC/on-call.
2. Xác nhận incident và actor tương ứng.
3. Thiết lập những target/action đã được phép.
4. Theo dõi alert và monitoring health liên tục.
5. Triage các hành động lạ với incident lead và app owner.
6. Nếu phát hiện dấu hiệu compromise hoặc lạm dụng nghiêm trọng, **chuyển security incident response**.
7. Khi cần, người có thẩm quyền **hạn chế phiên, revoke grant hoặc chặn target** bằng phương án giảm tác động đã định nghĩa.
8. Lưu timeline, bằng chứng và các quyết định can thiệp.
9. Sau session, đối soát kết quả và thiếu hụt telemetry.

### 30.1. Tránh hai lỗi vận hành

**Chỉ ghi hình rồi xem lại sau:** Có thể bỏ lỡ hành vi gây tổn hại tức thời. Với quyền rất cao, nên có **alert và đường phản ứng** phù hợp.

**Tự kết thúc mọi phiên khi có bất kỳ alert:** Dễ làm gián đoạn thao tác phục hồi hợp lệ, nhất là khi hệ thống đang mất availability. Cần **severity/risk policy, khả năng xác minh và quyền can thiệp** được định nghĩa.

## 31. Đọc lại bằng chứng sau phiên (readback)

Sau khi người vận hành nói “đã xong”, hệ thống nên đối soát:

| Cần xác minh | Nguồn tham khảo | Vì sao cần |
|---|---|---|
| Phiên PAM đã kết thúc | Session controller/PAM | Session qua broker không còn |
| Phiên target đã kết thúc | Host/DB/cloud/app session state | Không còn kết nối sống ngoài broker |
| Role/grant emergency bị rút | PIM/IAM/directory/target | Quyền đặc biệt không còn |
| Account local có được bảo vệ lại | Target owner/credential system | Tránh đường truy cập thường trực |
| Credential/key có cần rotate | Secret/vault/target audit | Xử lý secret từng bị biết/cấp mới |
| Token/refresh token còn hiệu lực? | Authorization Server/Resource Server | Giảm cửa sổ quyền tồn dư |
| Config/policy đã được phê duyệt | Change/audit/diff | Không giữ cấu hình tạm rủi ro |
| Hành động trong phiên có khớp nhiệm vụ | API/host/cloud audit + incident | Hậu kiểm đúng mục đích |
| Cảnh báo đã được triage | SIEM/SOC case | Không đóng khi còn nghi vấn quan trọng |
| Log gaps có biện pháp điều tra | Monitoring pipeline | Không che thiếu bằng chứng |
| Tài khoản ứng cứu vẫn được quản trị đúng | IAM/IGA/JML | Không để owner/eligible role mồ côi |

### 31.1. Readback không cần gây hại

Không chạy hành động phá hoại để kiểm quyền đã mất. Có thể dùng **permission check, denied authorization attempt trong môi trường kiểm thử phù hợp, read-only state query hoặc mô phỏng được phê duyệt** để chứng minh quyền không còn. Với tài nguyên production nhạy cảm, cần thiết kế **negative test an toàn**.

### 31.2. Nếu readback không thực hiện được

Giữ trạng thái **PENDING_VERIFICATION/EXCEPTION_OPEN**, có owner, risk, next action và biện pháp bù trừ. Không điền `verified=true` chỉ vì incident ticket cần đóng.

## 32. Từ “đã ghi log” đến “bằng chứng kiểm toán đủ chất lượng”

Một hồ sơ hậu kiểm nên chứa:

- Incident/activation/session references, subject và actor.
- Danh sách target, time window, policy/approval.
- Session start/end, nguồn log, dữ liệu thiếu và data confidence.
- Các hành động quan trọng, config diffs và outcomes.
- Alert/triage decisions, người xử lý và thời điểm.
- Credential/role/token/session cleanup và target readback.
- Người hậu kiểm độc lập, decision, SoD status.
- Ngoại lệ, owner, deadline và risk acceptance nếu có.
- Retention, integrity evidence và audit trail ai truy cập hồ sơ.
- Bài học cải tiến emergency access workflow.

**Không yêu cầu in mọi command hoặc nội dung recording ra ticket**. Dùng tham chiếu tới chứng cứ được bảo vệ, tránh lộ secret hoặc dữ liệu khách hàng.

## 33. Các tình huống thực hành

### 33.1. Tình huống A — SIEM không hoạt động khi cần break-glass

**Bối cảnh:** Hệ thống IdP lỗi; SIEM cũng mất kết nối với mạng production. Đội trực được phép sử dụng emergency account để phục hồi IdP. Central alerts không đến SOC.

**Sai lầm thường gặp:** Cho toàn quyền không thời hạn và ghi nhận “không có log vì hệ thống lỗi”.

**Cách xử lý:**

1. Kích hoạt quy trình emergency đã được thiết kế cho outage của hạ tầng giám sát.
2. Xác minh actor/incident qua kênh còn khả dụng, ghi timestamp và target.
3. Duy trì native host/cloud audit và buffer/log kênh độc lập khi có thể.
4. Chỉ định người trực quan sát bổ sung, lưu biên bản/correlation có kiểm soát.
5. Giới hạn tác vụ khôi phục, theo dõi thời hạn và không nới quyền vô hạn.
6. Khi SIEM phục hồi, đẩy logs có integrity checking và ghi rõ gaps.
7. Hậu kiểm các thao tác, quyền, session và credential; mở exception nếu thiếu bằng chứng.

**Bài học:** **Fallback monitoring phải được chuẩn bị trước**, không thể sáng tạo tùy ý trong sự cố rồi coi mọi bằng chứng hoàn chỉnh.

### 33.2. Tình huống B — PAM ghi hình, nhưng actor gọi API trực tiếp

**Bối cảnh:** Người ứng cứu vào bastion có recording và được phép restart một service. Sau đó họ sử dụng một API key đã có sẵn để thay đổi firewall rule; thao tác API không nằm trong recording.

**Sai lầm:** Báo cáo “100% thao tác đã ghi hình” dựa vào file video PAM.

**Cách xử lý:**

- Kiểm cloud/API audit và định danh key.
- Xác định action thay firewall có trong incident scope không.
- Truy người có quyền dùng key và nguồn credential.
- Ghi rõ PAM recording chỉ bao phủ kết nối qua broker.
- Rà soát API key, IAM policy, token lifetime và direct access path.
- Sửa kiến trúc monitoring để ghép **session + API actions**, đồng thời bảo vệ quyền trực tiếp.

**Bài học:** Giám sát phiên phải xét **mọi đường tác động đến target**, không chỉ giao thức đầu tiên.

### 33.3. Tình huống C — Hai người dùng chung account emergency

**Bối cảnh:** Account `emergency-root` được dùng bởi hai kỹ sư trong ca trực. Native host log chỉ biết `root`, không biết ai đã thay policy quan trọng.

**Cách xử lý:**

- Đối chiếu thời điểm checkout, incident, bastion/network và biên bản ca trực.
- Không tự khẳng định actor cụ thể nếu chứng cứ không đủ.
- Xác định mức thiếu attribution và mở finding kiểm toán.
- Cải tiến workflow dùng identity riêng, actor binding, secret checkout, session tracking khi khả dụng.
- Xem lại phương án shared account có còn cần cho khả năng phục hồi không.

**Bài học:** **Accountability không thể chỉ dựa trên tên shared account**.

### 33.4. Tình huống D — Phiên emergency không kết thúc khi incident đã đóng

**Bối cảnh:** IdP được khôi phục lúc 22:00, nhưng một phiên database admin emergency còn hoạt động tới 23:15; PIM cho biết grant đã hết hạn lúc 22:05.

**Rủi ro:** TTL của grant không chặn được quyền ở target/session đã mở.

**Cách xử lý:**

1. Kiểm current target session/connection và người chịu trách nhiệm.
2. Đánh giá có thao tác hợp lệ hậu phục hồi không; nếu có, cần approval/scope mới.
3. Theo chính sách, terminate hoặc hạn chế session, gỡ ACL/role liên quan.
4. Kiểm token, key, local credential được phiên dùng.
5. Readback quyền thực tế và timestamp hết quyền.
6. Điều chỉnh runbook PIM/PAM/target để tránh tái diễn.

**Bài học:** **Grant expired không tự chứng minh emergency access đã hết hiệu lực**.

### 33.5. Tình huống E — Operator vô hiệu hóa audit trong lúc khôi phục

**Bối cảnh:** Để cải thiện hiệu năng máy chủ khi phục hồi, operator tắt một audit agent rồi quên bật lại. SIEM báo mất event và phiên kết thúc bình thường.

**Câu hỏi cần giải quyết:**

- Tắt agent có thật sự cần cho recovery, có được approver chấp thuận?
- Native logs hoặc kênh giám sát khác còn không?
- Có khoảng thời gian nào thiếu hoàn toàn bằng chứng?
- Agent đã bật lại và hoạt động đúng chưa?
- Có thay đổi nào khác trong khoảng thiếu log cần đối soát?
- Quy trình bảo vệ audit cần thay thế bằng gì nếu agent gây lỗi vận hành?

**Bài học:** Không nên mặc định mọi audit-disable là malicious, nhưng **phải điều tra và bảo đảm monitoring được phục hồi**, không bỏ qua vì có giải thích kỹ thuật.

### 33.6. Tình huống F — Mover vẫn có thể kích hoạt break-glass

**Bối cảnh:** An chuyển khỏi đội Platform; nhóm emergency responder chưa được gỡ. Trong một cuộc diễn tập, An dùng account khẩn cấp mở phiên Cloud Admin.

**Cách xử lý:**

- Đối chiếu HR/VMS Mover và hiện trạng eligible role.
- Thu hồi quyền kích hoạt không còn căn cứ.
- Kiểm credential, PIM/PAM, local account, token/session.
- Xem lại người quản lý danh sách responder và event-driven sync.
- Ghi finding và test An không thể sử dụng emergency access trái chính sách.

**Bài học:** **Emergency eligibility cũng phải theo vòng đời JML**, không phải quyền vĩnh viễn.

### 33.7. Tình huống G — Leaver từng biết mật khẩu emergency

**Bối cảnh:** Một người ứng cứu nghỉ việc. IdP account bị disable, nhưng mật khẩu local emergency account tại một hệ thống legacy chưa được rotate; người đó đã từng checkout credential.

**Cách xử lý:**

1. Xác định target và những người từng biết credential.
2. Đánh giá rủi ro theo khả năng truy cập bên ngoài, network và phạm vi admin.
3. Có kế hoạch rotate tại target, cập nhật vault và hệ thống phụ thuộc.
4. Đánh giá session/SSH key/token và local login khác.
5. Readback credential cũ không còn được chấp nhận.
6. Kiểm emergency path vẫn hoạt động cho responder hiện tại.
7. Ghi audit và cải tiến trigger Leaver.

**Bài học:** **Disable IdP không thể thu hồi mật khẩu đã được người nghỉ biết nếu target vẫn tin mật khẩu đó**.

### 33.8. Tình huống H — Automation khôi phục tạo quyền lâu dài

**Bối cảnh:** Job emergency khôi phục database tạo role `recovery_admin` để thao tác nhanh, rồi không xóa role sau khi job kết thúc. Recording con người không có vì hành động đến từ workload.

**Cách xử lý:**

- Truy job run ID, workload identity, người kích hoạt và incident.
- Kiểm target audit/role history để biết quyền được tạo khi nào.
- Đối soát lý do, owner và thời hạn của role.
- Gỡ role/credential khi hết nhu cầu và bảo đảm không phá dependency hợp lệ.
- Bổ sung cleanup/TTL và verification bắt buộc vào runbook job.
- Theo dõi account/role xuất hiện lại khi chạy workflow tương tự.

**Bài học:** **Session monitoring cho emergency automation phải dựa API/workload audit và grant lifecycle**, không chỉ video PAM.

### 33.9. Tình huống I — Recording chứa secret

**Bối cảnh:** Trong quá trình thay cấu hình, màn hình RDP hiển thị một private key; video được lưu ở hệ thống recording và nhiều reviewer có thể tải về.

**Cách xử lý:**

- Hạn chế quyền xem/tải recording liên quan.
- Đánh giá secret có cần rotate/revoke ngay không.
- Không gửi video nguyên bản qua email/ticket không được bảo vệ.
- Thực hiện redaction/copy phục vụ audit khi có khả năng và chính sách cho phép.
- Ghi người đã truy cập và phạm vi lộ.
- Cải tiến masking, quy trình thao tác và retention.

**Bài học:** **Chứng cứ bảo mật có thể trở thành nguồn rò rỉ credential nếu không được bảo vệ**.

## 34. Chỉ số đánh giá chất lượng giám sát phiên

| Chỉ số | Ý nghĩa | Bẫy cần tránh |
|---|---|---|
| **Emergency activation coverage** | Tỷ lệ activation có actor, incident, scope, TTL | Có ticket không bảo đảm đúng người |
| **Session attribution coverage** | Tỷ lệ phiên map được actor–account–target | Shared account có thể không quy người đầy đủ |
| **Monitoring-path coverage** | Các giao thức/target/API có telemetry phù hợp | PAM recording không bao phủ đường trực tiếp |
| **Session start/end completeness** | Phiên có event đầu/cuối đáng tin | Mất kết nối không luôn là kết thúc ở target |
| **Target audit coverage** | Hành động đặc quyền có log từ target | Log cục bộ có thể bị admin sửa |
| **Log delivery delay** | Thời gian từ event đến nơi giám sát | Log đến chậm không có nghĩa không xảy ra |
| **Monitoring gap duration** | Khoảng thiếu telemetry khi phiên active | Không tính thiếu log là an toàn |
| **Alert triage latency** | Thời gian từ alert đến người chịu trách nhiệm | ACK không đồng nghĩa xử lý |
| **Out-of-scope action findings** | Hành động ngoài phạm vi incident | Cần review ngữ cảnh, tránh kết luận vội |
| **Policy/privilege change after session** | Role/key/policy được tạo/đổi còn tồn tại | Không chỉ xét session logout |
| **Emergency access closure time** | Từ kết thúc tác vụ đến verified revoke | Đóng ticket không bằng quyền mất |
| **Post-use review coverage** | Tỷ lệ phiên có review đúng thẩm quyền | Reviewer tự kiểm chính mình không đủ |
| **Credential rotation findings** | Credential cần rotate sau phiên và đã xử lý | Không rotate vô tội vạ gây outage |
| **Residual access findings** | Token/session/grant còn sau mốc phải thu hồi | Phân biệt verified active vs unknown |
| **Exception aging** | Ngoại lệ thiếu bằng chứng hoặc chưa thu hồi | Không coi exception được duyệt là fixed |
| **Recording privacy incidents** | Recording làm lộ secret/dữ liệu | Ghi nhiều không tự bằng an toàn |

### 34.1. Coverage phải nói rõ mẫu số

Ví dụ: 100% phiên **đi qua PAM** có recording, nhưng 30% hoạt động emergency đi qua cloud API trực tiếp. Không nên quảng bá “100% emergency access được ghi hình”. Hãy báo:

~~~text
PAM sessions recorded:        100% of brokered sessions
Cloud API telemetry covered:  X% of identified API actions
Direct local sessions:        Y% have independent audit
Unattributed shared sessions: Z items under investigation
Verified emergency closure:   W% of completed activations
~~~

Các ký hiệu X/Y/Z/W cần được lấy từ số liệu thật, không suy đoán. **Khi inventory chưa đầy đủ, báo đúng phạm vi đã kiểm kê**.

## 35. Checklist triển khai và hậu kiểm giám sát phiên khẩn cấp

- [ ] **Định nghĩa emergency:** Sự cố nào được phép dùng break-glass, không dùng cho việc thường ngày?
- [ ] **Actor:** Có xác minh người/workload thực hiện và mapping tới target account?
- [ ] **Eligibility:** Người ứng cứu còn active đúng nhiệm vụ, Mover/Leaver đã cập nhật?
- [ ] **Approval/SoD:** Có điều kiện kích hoạt hoặc hậu kiểm độc lập theo mức rủi ro?
- [ ] **Purpose:** Có incident ID, mục tiêu và phạm vi target/action rõ?
- [ ] **Time:** Có activation/session TTL và điều kiện kết thúc sớm?
- [ ] **Least privilege:** Không cấp global admin nếu tác vụ hẹp hơn đáp ứng được?
- [ ] **Dependencies:** Đường emergency không hoàn toàn phụ thuộc hệ thống đang cần khôi phục?
- [ ] **PAM/session:** Nếu broker khả dụng, có start/end và recording phù hợp?
- [ ] **Direct path:** Có native audit cho console/API/local login ngoài PAM?
- [ ] **Cloud/DB/K8s:** Có audit thao tác đặc quyền, policy/role/secret changes?
- [ ] **Workload:** Automation có job ID, service principal, actor/trigger, resource và owner?
- [ ] **Correlation:** Nối actor, incident, activation, session, target, API request và policy version?
- [ ] **Timestamp:** UTC/offset, clock skew và thời gian đến log pipeline được giám sát?
- [ ] **Alert:** Có rule cho vượt scope, cấp admin, tắt audit, dữ liệu nhạy cảm, TTL và JML?
- [ ] **Response:** Alert có owner, mức độ ưu tiên và quyền can thiệp cụ thể?
- [ ] **SOC:** Có khả năng theo dõi trực tiếp hoặc kênh phản ứng phù hợp rủi ro?
- [ ] **Monitoring failure:** Có degraded mode và kênh fallback đã diễn tập?
- [ ] **Data gaps:** Có ghi chính xác phần bằng chứng không thu thập được?
- [ ] **Integrity:** Log/recording được bảo vệ khỏi sửa/xóa bởi operator target?
- [ ] **Privacy:** Không log token/secret/password; recording có quyền xem và retention?
- [ ] **SoD:** Người thao tác không tự hậu kiểm/xóa bằng chứng theo policy?
- [ ] **Change tracking:** Mọi policy, credential, role/account thay trong phiên có record?
- [ ] **Session end:** Đã chấm dứt target sessions, không chỉ PAM connection?
- [ ] **Token/credential:** Có đánh giá refresh/access token, key/cert/secret và rotation?
- [ ] **RBAC/ABAC:** Quyền còn lại có đúng target/tenant/resource và policy hiện hành?
- [ ] **IdP/SSO/SCIM:** Disable/gỡ group không bị nhầm với hiệu lực ở target?
- [ ] **JML:** Joiner được training, Mover gỡ eligibility, Leaver thu hồi credential biết trước?
- [ ] **Post-use review:** Có reviewer độc lập, evidence và finding với deadline?
- [ ] **Readback:** Có bằng chứng quyền hiệu dụng đã về desired state?
- [ ] **Exceptions:** Mọi phần chưa xác minh có owner, rủi ro, bù trừ và expiry?
- [ ] **Metrics:** Đo attribution, monitoring coverage, alert latency, residual access và closure?
- [ ] **Practice:** Đã diễn tập IdP/PAM/SIEM outage mà vẫn có phương án giám sát có căn cứ?
- [ ] **No shortcut:** Không dùng `monitoringDown => PERMIT_ALL` hoặc auto-close thiếu readback?

## 36. Câu hỏi tự kiểm tra

**Câu 1.** PAM ghi hình một phiên SSH. Có đủ chứng minh mọi hành động emergency đã được ghi nhận không?

**Gợi ý:** Không. Có thể có cloud API, local console, token, database hoặc automation ngoài phiên PAM; cần native audit và correlation.

**Câu 2.** Khác biệt giữa emergency activation và emergency session là gì?

**Gợi ý:** Activation cho phép/kích hoạt quyền theo căn cứ; session là kết nối thực tế dùng quyền đó; hai vòng đời có thể khác thời gian.

**Câu 3.** Khi SIEM không khả dụng, có nên cho mọi hành động admin đi qua mà không có log?

**Gợi ý:** Không. Cần degraded/fallback monitoring được phê duyệt trước, bảo vệ native/local evidence và hậu kiểm gaps.

**Câu 4.** Vì sao session recording có thể là nguồn rủi ro bảo mật?

**Gợi ý:** Có thể chứa password, token, secret hoặc dữ liệu nhạy cảm; cần giới hạn quyền xem, masking và retention.

**Câu 5.** Actor là P-2048 nhưng target log ghi `root`. Cần dữ liệu nào để quy trách nhiệm?

**Gợi ý:** Activation, credential checkout, broker/session mapping, incident và nguồn xác minh actor đủ tin cậy.

**Câu 6.** Incident đã đóng, PIM role hết hạn, nhưng target session admin vẫn chạy. Đã kết thúc quyền khẩn cấp chưa?

**Gợi ý:** Chưa nếu session còn thực hiện quyền trái policy; cần target readback, session termination và token/credential review.

**Câu 7.** Người điều hành đang khôi phục IdP, còn người giám sát phát hiện họ tạo một global admin mới. Có nên kết luận tấn công ngay?

**Gợi ý:** Đây là alert rủi ro cao cần triage; kiểm mục đích, approval, target và policy. Không bỏ qua, cũng không kết luận chỉ từ một rule.

**Câu 8.** Chủ emergency account đã Leaver nhưng account vẫn truy cập local console. Vì sao disable SSO không đủ?

**Gợi ý:** Local credential và account có thể độc lập IdP; cần revoke/rotate và kiểm target.

**Câu 9.** Vì sao không tự xóa một recovery workload khi người tạo job nghỉ việc?

**Gợi ý:** Workload có lifecycle/owner riêng, có thể cần cho production; phải kiểm dependency, chuyển owner và xử lý secret/quyền theo rủi ro.

**Câu 10.** Khi reviewer hậu kiểm đồng thời là người dùng break-glass, vấn đề gì xuất hiện?

**Gợi ý:** Xung đột lợi ích/SoD; cần reviewer đủ thẩm quyền, độc lập theo chính sách.

**Câu 11.** Target audit không ghi event trong 20 phút. Có thể kết luận không có thao tác đáng ngờ?

**Gợi ý:** Không. Đó có thể là monitoring gap; kiểm health, nguồn khác, timeline và ghi limitation.

**Câu 12.** Vì sao cần giám sát cả credential/role được tạo mới trong phiên?

**Gợi ý:** Chúng có thể duy trì quyền sau session end, tạo persistence/quyền tồn dư.

## 37. Kết luận

**Giám sát phiên khẩn cấp** là lớp kiểm soát trọng yếu giúp tổ chức vừa **khôi phục hệ thống khi cơ chế bình thường bị gián đoạn**, vừa duy trì khả năng **quy trách nhiệm, phát hiện hành động ngoài mục đích, bảo vệ chứng cứ và kết thúc đặc quyền an toàn**. Nó bao gồm **định danh actor, xác minh incident, giám sát session và hành động tại target, cảnh báo theo rủi ro, bảo vệ log/recording, phản ứng, hậu kiểm và readback**, chứ không chỉ bật chức năng ghi hình.

Một thiết kế vững phải phân biệt **PAM/SSO với native audit, recording với enforcement, activation với session, incident closure với verified revocation**. Khi hệ thống giám sát suy giảm, cần **fallback đã diễn tập và ghi rõ giới hạn bằng chứng**, không dùng đó làm lý do cho quyền truy cập không kiểm soát. **IAM/IGA, IdP/SSO, SCIM, RBAC/ABAC, PAM/PIM và quản lý workload/service account** phải phối hợp để biết quyền nào còn ở target.

Trong vòng đời **Joiner–Mover–Leaver**, **người mới** chỉ được dùng emergency access khi đủ điều kiện, **người đổi vai trò** bị gỡ eligibility không còn căn cứ, **người rời tổ chức** bị thu hồi account, token, credential và session cần thiết. **Một phiên chỉ thực sự được đóng về mặt bảo mật khi những quyền còn tồn tại đã được xác minh phù hợp chính sách và các ngoại lệ còn mở có người chịu trách nhiệm**. Đó là cách giám sát emergency access vừa hỗ trợ khả năng phục hồi vừa **giảm lạm dụng đặc quyền và quyền truy cập tồn dư**.
