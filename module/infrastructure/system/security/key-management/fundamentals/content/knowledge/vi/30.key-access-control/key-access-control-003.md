# Human access vào key

Trong hệ thống quản lý khóa mật mã, con người cần vận hành, xử lý sự cố, phê duyệt thay đổi và kiểm tra bằng chứng kiểm toán. Tuy nhiên, quyền của một quản trị viên đối với hệ thống KMS/HSM có thể ảnh hưởng trực tiếp đến tính bí mật, toàn vẹn và khả năng truy cập của dữ liệu. Một người có quyền gọi thao tác giải mã có thể đọc được dữ liệu được bảo vệ; người có quyền ký có thể tạo chữ ký hợp lệ; người có quyền thay đổi chính sách có thể mở rộng quyền cho chính mình; người có quyền hủy khóa có thể làm dữ liệu không thể khôi phục.

Vì vậy, **human access vào key** cần được thiết kế như một tập hợp quyền có mục đích rõ ràng, gắn với danh tính cá nhân, thời hạn, quy trình phê duyệt và bằng chứng kiểm toán. Mục tiêu là để nhân sự thực hiện đúng nhiệm vụ mà không tạo ra quyền truy cập rộng, kéo dài hoặc khó truy vết.

## 1. Human access vào key là gì?

Human access là quyền mà một người dùng có danh tính trong tổ chức được cấp để xem thông tin, quản trị hoặc yêu cầu thực hiện thao tác liên quan đến khóa mật mã. Người đó có thể là kỹ sư nền tảng, quản trị viên bảo mật, người trực vận hành, chủ sở hữu ứng dụng, nhân viên tuân thủ hoặc người tham gia quy trình khôi phục.

Cụm từ “truy cập key” dễ gây hiểu nhầm rằng người dùng phải đọc được byte của khóa. Trong hệ thống được thiết kế tốt, phần lớn công việc của con người chỉ cần quyền quản lý metadata hoặc gọi một thao tác được kiểm soát. Vật liệu khóa có thể được giữ bên trong KMS/HSM và không được xuất ra cho người vận hành.

Có thể chia human access thành các nhóm:

| Nhóm quyền | Ví dụ | Rủi ro chính |
|---|---|---|
| Xem metadata | Xem key ID, alias, thuật toán, trạng thái, phiên bản, ngày tạo | Lộ thông tin về kiến trúc, tài nguyên hoặc vòng đời |
| Xem trạng thái vận hành | Xem lỗi, số lần gọi, thời điểm sử dụng, cấu hình rotation | Lộ dấu vết hoạt động hoặc dữ liệu vận hành nhạy cảm |
| Gọi phép toán mật mã | Yêu cầu encrypt, decrypt, sign, verify, wrap hoặc unwrap | Có thể đọc dữ liệu, tạo chữ ký hoặc mở khóa vật liệu được bảo vệ |
| Quản trị cấu hình | Tạo key, gắn alias, đặt policy, cấu hình rotation | Có thể thay đổi phạm vi sử dụng hoặc quyền truy cập |
| Quản lý vòng đời | Enable, disable, schedule deletion, cancel deletion, rotate | Có thể làm gián đoạn dịch vụ hoặc mất khả năng giải mã |
| Nhập hoặc xuất key material | Import key material, export key nếu thiết kế cho phép | Rủi ro lộ vật liệu khóa ở dạng có thể sử dụng |
| Quản trị nền tảng | Quản lý HSM partition, cluster, backup hoặc quyền quản trị KMS | Có thể tác động đến nhiều key và nhiều workload |
| Kiểm toán | Đọc audit log, policy history, approval record | Lộ thông tin vận hành; có thể bị lợi dụng nếu quyền sửa log đi kèm |

Những nhóm này không nên tự động được cấp cùng nhau. Ví dụ, người cần xem metadata không nhất thiết cần quyền decrypt; người cần vận hành rotation không nhất thiết cần quyền export key material; người kiểm toán cần đọc bằng chứng nhưng không nên có quyền sửa policy hoặc xóa log.

### Phân biệt quyền xem key, quyền dùng key và quyền quản lý key

Ba quyền sau có tác động rất khác nhau:

- **Xem key material**: đọc được dữ liệu khóa ở dạng có thể dùng trực tiếp. Đây là quyền đặc biệt nhạy cảm và thường nên bị cấm đối với người vận hành.
- **Dùng key**: yêu cầu KMS/HSM thực hiện một phép toán bằng key. Người dùng có thể không nhìn thấy byte của khóa, nhưng kết quả thao tác vẫn có thể tiết lộ dữ liệu hoặc tạo ra hành động có giá trị.
- **Quản lý key**: thay đổi cấu hình, policy, trạng thái hoặc vòng đời. Người có quyền này có thể gián tiếp cấp quyền sử dụng key cho bản thân hoặc người khác.

Một key không thể export vẫn có thể bị lạm dụng nếu policy cho phép một cá nhân gọi decrypt với dữ liệu tùy ý. Tương tự, private signing key nằm trong HSM vẫn có thể bị sử dụng để ký một thông điệp trái phép nếu người gọi có quyền sign quá rộng. Do đó, “không xuất được key” là một lớp bảo vệ quan trọng, nhưng chưa đủ để chứng minh quyền sử dụng key đã an toàn.

## 2. Xác định ranh giới truy cập trước khi cấp quyền

Trước khi tạo role hoặc policy, cần xác định người dùng đang cần truy cập tới đối tượng nào và để thực hiện nhiệm vụ gì.

Một yêu cầu truy cập nên chỉ rõ:

- Danh tính cá nhân và nhóm công việc của người yêu cầu.
- Key hoặc tập key cụ thể, tốt nhất bằng định danh tài nguyên ổn định.
- Môi trường và tenant liên quan, chẳng hạn development, staging hoặc production.
- Thao tác cần thực hiện: xem metadata, encrypt, decrypt, sign, rotate, disable hay một hành động quản trị khác.
- Mục đích nghiệp vụ hoặc mã sự cố/change ticket.
- Thời hạn quyền truy cập.
- Người phê duyệt và điều kiện giám sát.
- Cách xác nhận hoàn thành và thu hồi quyền.

Không nên cấp quyền “toàn bộ key trong tài khoản” chỉ vì người dùng thuộc nhóm kỹ thuật. Phạm vi nên thu hẹp theo key, ứng dụng, tenant, môi trường, loại thao tác và thời gian.

### Tách quyền truy cập theo mức tác động

| Mức tác động | Ví dụ | Hướng kiểm soát |
|---|---|---|
| Thấp | Xem metadata không nhạy cảm, xem trạng thái | Role đọc riêng, giới hạn theo môi trường và phạm vi |
| Trung bình | Xem audit log, xem policy, cập nhật alias hoặc mô tả | Read-only hoặc quyền thay đổi metadata riêng; ghi audit |
| Cao | Decrypt dữ liệu, sign, unwrap DEK, thay đổi policy | JIT, MFA mạnh, ticket, phê duyệt và giới hạn tài nguyên |
| Rất cao | Export key material, thay đổi trust boundary, xóa key, quản trị HSM | Mặc định từ chối; dual control/quorum, phiên đặc quyền và kiểm soát độc lập |

Mức độ tác động phụ thuộc vào loại key và dữ liệu. Quyền decrypt một khóa dùng cho dữ liệu công khai có thể ít nhạy cảm hơn quyền decrypt khóa bảo vệ hồ sơ tài chính hoặc dữ liệu định danh. Quyền sign một khóa phát hành phần mềm hoặc CA có thể ảnh hưởng tới toàn bộ chuỗi tin cậy. Việc phân loại phải xét hậu quả khi quyền bị lạm dụng.

## 3. Danh tính con người và xác thực

Mọi hành động quản trị key cần gắn với danh tính cá nhân có thể truy vết. Không dùng tài khoản dùng chung như `kms-admin` hoặc `hsm-operator` cho nhiều người, vì log sẽ không cho biết ai thực hiện hành động.

### Dùng danh tính tập trung và quyền ngắn hạn

Một mô hình phổ biến là liên kết KMS/HSM với hệ thống danh tính doanh nghiệp:

1. Nhân sự đăng nhập qua Identity Provider (IdP) bằng tài khoản cá nhân.
2. IdP xác minh danh tính và áp dụng chính sách xác thực.
3. Người dùng nhận phiên hoặc credential ngắn hạn theo role được cấp.
4. KMS/HSM kiểm tra principal, policy, phạm vi key và thao tác được yêu cầu.
5. Hoạt động được ghi vào audit log với danh tính gốc và thông tin phiên.

Liên kết danh tính giúp tổ chức áp dụng quy trình onboarding, thay đổi vị trí và offboarding tập trung. Credential ngắn hạn giảm nguy cơ khóa truy cập tĩnh bị sao chép và sử dụng sau khi nhân sự đã rời tổ chức.

### MFA và thiết bị truy cập

Với quyền có tác động cao, nên yêu cầu xác thực đa yếu tố (MFA), ưu tiên phương thức chống phishing như security key hoặc passkey theo chính sách tổ chức. MFA không thay thế authorization: xác thực mạnh chỉ chứng minh người dùng là ai, còn policy vẫn phải xác định người đó được phép làm gì.

Đối với phiên đặc quyền, có thể yêu cầu thêm:

- Thiết bị do tổ chức quản lý và có trạng thái bảo mật đạt yêu cầu.
- Kết nối qua mạng quản trị hoặc môi trường truy cập đặc quyền.
- Không lưu credential trong shell history, script, notebook hoặc tệp cấu hình.
- Không cho phép chia sẻ session hoặc chuyển tiếp credential.
- Ghi nhận nguồn truy cập, thời điểm, session ID và ticket liên quan.

### Vòng đời danh tính phải đồng bộ với vòng đời quyền key

Khi nhân sự chuyển nhóm, nghỉ việc hoặc thay đổi trách nhiệm, quyền truy cập key cần được cập nhật kịp thời. Không nên chỉ dựa vào việc xóa tài khoản trong một hệ thống nếu session hoặc credential tạm thời vẫn còn hiệu lực ở hệ thống khác.

Quy trình offboarding cần bao gồm thu hồi session, token, quyền JIT đang hoạt động, membership nhóm, quyền qua PAM và quyền trực tiếp trong KMS/HSM. Với các key nhạy cảm, cần rà soát cả quyền gián tiếp thông qua role, group, policy inheritance và tài khoản quản trị nền tảng.

## 4. Thiết kế role và phân tách nhiệm vụ

Role nên được định nghĩa theo nhiệm vụ thực tế, không theo chức danh chung chung. Một người có thể giữ nhiều vai trò trong môi trường thử nghiệm, nhưng môi trường production và các thao tác có tác động cao cần có sự phân tách rõ.

| Vai trò | Nhiệm vụ | Quyền nên có | Quyền nên tách riêng |
|---|---|---|---|
| Key owner | Chịu trách nhiệm nghiệp vụ về key và dữ liệu phụ thuộc | Xác nhận mục đích, phạm vi, thời hạn và yêu cầu thay đổi | Không mặc nhiên có quyền export hoặc destroy |
| Key operator | Vận hành thao tác đã được phê duyệt | Xem trạng thái, thực hiện rotation hoặc thao tác vận hành trong phạm vi | Không tự phê duyệt yêu cầu của chính mình |
| Security administrator | Quản lý policy và tiêu chuẩn bảo vệ | Đề xuất hoặc áp dụng policy theo quy trình | Không đồng thời kiểm soát toàn bộ approval và audit |
| Application owner | Xác nhận ứng dụng cần quyền sử dụng key | Đề xuất quyền workload, xác nhận kiểm thử | Không tự cấp quyền decrypt tùy ý cho cá nhân |
| Approver | Đánh giá lý do và tác động của yêu cầu | Phê duyệt hoặc từ chối yêu cầu | Không nhất thiết có quyền thực thi |
| Auditor | Kiểm tra hoạt động và bằng chứng | Đọc log, policy history và approval record | Không sửa policy, không xóa audit |
| HSM custodian | Quản lý vật lý hoặc thủ tục quản trị HSM | Tham gia ceremony theo quy trình | Không đơn phương kiểm soát mọi thành phần của ceremony |

### Separation of duties

Separation of duties (SoD) yêu cầu những hành động có xung đột lợi ích được chia cho các chủ thể khác nhau. Ví dụ, người tạo yêu cầu hủy key không nên tự phê duyệt và tự thực hiện việc hủy. Người thay đổi policy cấp quyền decrypt không nên là người duy nhất xác nhận thay đổi đó hợp lệ.

Có thể tách quy trình thành ba vai trò:

- Người yêu cầu nêu mục đích, phạm vi và tác động.
- Người phê duyệt xác nhận yêu cầu hợp lệ và đúng thẩm quyền.
- Người thực thi thực hiện thao tác đã được phê duyệt.

Trong nhóm nhỏ, không phải lúc nào cũng có đủ ba cá nhân khác nhau. Khi đó, tổ chức cần đánh giá rủi ro và dùng kiểm soát bù như phê duyệt độc lập từ on-call khác, giám sát phiên, cảnh báo tức thời và review sau hành động. Với thao tác hủy hoặc export key material, không nên hạ yêu cầu kiểm soát chỉ vì thiếu nhân sự.

### Không dùng một role “super-admin” cho công việc hằng ngày

Tài khoản có quyền quản trị tối cao thường là mục tiêu hấp dẫn. Nên giữ quyền này cho tình huống quản trị nền tảng thực sự cần thiết, bảo vệ bằng PAM, MFA mạnh, thời hạn ngắn, phê duyệt và ghi nhận phiên. Công việc thường ngày cần role hẹp hơn, ví dụ chỉ đọc metadata hoặc chỉ thực hiện rotation cho một nhóm key.

## 5. RBAC, ABAC và policy theo từng thao tác

RBAC (Role-Based Access Control) gán quyền theo role. ABAC (Attribute-Based Access Control) đánh giá thuộc tính của principal, tài nguyên, hành động và ngữ cảnh yêu cầu. Hệ thống thực tế có thể kết hợp hai cách.

RBAC giúp quản lý quyền theo nhóm nhiệm vụ. ABAC giúp giới hạn sâu hơn theo thuộc tính như tenant, môi trường, loại key, mức phân loại dữ liệu, vị trí mạng hoặc ticket đã được xác thực.

Ví dụ, một role `production-key-operator` có thể được phép thực hiện rotation, nhưng chỉ khi:

- Key thuộc ứng dụng mà người đó chịu trách nhiệm.
- Key có tag môi trường là production và service owner phù hợp.
- Hành động nằm trong danh sách được cho phép.
- Yêu cầu được thực hiện qua phiên đặc quyền đã xác thực.
- Ticket thay đổi hợp lệ được đính kèm hoặc tham chiếu.
- Thời hạn cấp quyền chưa hết.

### Quyền nên được cấp theo từng API operation

Không nên dùng một quyền tổng quát kiểu “access key” nếu nền tảng cho phép phân tách thao tác. Có thể cần tách:

| Hành động | Ví dụ quyền | Lưu ý |
|---|---|---|
| Đọc metadata | Describe/GetMetadata/ListVersions | Không đồng nghĩa được đọc key material |
| Xem policy | GetPolicy | Có thể lộ cấu trúc quyền và principal |
| Thay đổi policy | PutPolicy/UpdateAccess | Rủi ro tự cấp quyền hoặc mở rộng phạm vi |
| Mã hóa | Encrypt | Thường không tiết lộ plaintext, nhưng vẫn có chi phí và lạm dụng tài nguyên |
| Giải mã | Decrypt | Có thể làm lộ dữ liệu nhạy cảm; cần giới hạn context và mục đích |
| Ký | Sign | Có thể tạo chữ ký hợp lệ mang danh tính của tổ chức |
| Xác minh | Verify | Thường ít nhạy cảm hơn sign nhưng cần giới hạn tài nguyên |
| Wrap/unwrap | WrapKey/UnwrapKey | Unwrap có thể làm lộ DEK bản rõ |
| Rotation | Rotate/UpdateVersion | Cần quản lý phụ thuộc dữ liệu cũ và phiên bản |
| Disable/Enable | DisableKey/EnableKey | Có thể ảnh hưởng tính sẵn sàng hoặc khôi phục trạng thái |
| Schedule deletion | ScheduleKeyDeletion | Có thể dẫn tới mất khả năng giải mã không thể đảo ngược |
| Export/import | Export/ImportKeyMaterial | Rủi ro trực tiếp với vật liệu khóa |

Tên API thực tế phụ thuộc nhà cung cấp. Bảng trên mô tả các nhóm thao tác, không phải cấu hình policy có thể sao chép nguyên xi.

### Giới hạn theo tài nguyên và ngữ cảnh

Policy nên gắn với key cụ thể hoặc tập key có thuộc tính rõ ràng. Có thể áp dụng điều kiện theo:

- Key ID hoặc key ARN/resource path.
- Ứng dụng, tenant và môi trường.
- Purpose hoặc key usage: encrypt, decrypt, sign, verify, wrap.
- Encryption context hoặc thông tin ràng buộc dữ liệu.
- Principal role và danh tính cá nhân.
- Nguồn mạng, thiết bị hoặc session.
- Ticket/change ID và thời hạn của quyền.

Encryption context trong các hệ thống hỗ trợ AEAD/KMS thường là dữ liệu bổ sung được xác thực cùng ciphertext. Nó không phải secret và không tự chứng minh người gọi có quyền. Policy có thể yêu cầu context chứa tenant hoặc resource phù hợp, nhưng ứng dụng phải tạo context theo quy tắc canonical và authorization vẫn phải xác minh principal được phép truy cập tenant/resource đó.

### Mẫu policy khái niệm

Ví dụ dưới đây minh họa cách diễn đạt một yêu cầu kiểm soát. Đây không phải policy của một nhà cung cấp cụ thể:

~~~json
{
  "principal": "individual:engineer-123",
  "role": "production-key-operator",
  "resource": "key:payments-data-encryption",
  "actions": [
    "DescribeKey",
    "RotateKey"
  ],
  "conditions": {
    "environment": "production",
    "application": "payments",
    "ticket_required": true,
    "mfa": "phishing-resistant",
    "session_max_minutes": 45
  },
  "approval": {
    "required": true,
    "approver_role": "payments-security-approver",
    "requester_must_differ": true
  },
  "expires_at": "end-of-approved-session"
}
~~~

Một policy thực tế còn cần xác định deny behavior, cách kiểm tra ticket, cách xác minh approval, phạm vi session, điều kiện thu hồi và cách xử lý lỗi của hệ thống cấp quyền. Không nên tin vào một trường do client tự gửi nếu không có thành phần tin cậy xác minh nó.

## 6. Just-in-time access và Privileged Access Management

Just-in-time (JIT) access cấp quyền khi có nhu cầu cụ thể và tự hết hạn sau khoảng thời gian được phê duyệt. Privileged Access Management (PAM) quản lý việc sử dụng tài khoản và phiên có đặc quyền, thường bao gồm cấp credential, kiểm soát session, ghi nhận hoạt động và thu hồi.

JIT/PAM phù hợp với các thao tác như decrypt phục vụ điều tra, thay đổi policy, rotation khẩn cấp hoặc quản trị HSM. Nhân sự không cần giữ quyền production rộng trong suốt cả ngày nếu chỉ thực hiện một nhiệm vụ ngắn.

### Quy trình JIT đề xuất

1. **Tạo yêu cầu:** người dùng nêu key, thao tác, mục đích, ticket, phạm vi dữ liệu và thời lượng cần thiết.
2. **Kiểm tra điều kiện:** hệ thống xác minh người yêu cầu còn thuộc nhóm được phép, thiết bị đạt chuẩn, MFA hợp lệ và ticket còn hiệu lực.
3. **Phê duyệt:** approver độc lập xem xét tác động, phạm vi và phương án thay thế.
4. **Cấp quyền ngắn hạn:** hệ thống tạo session hoặc policy grant có giới hạn tài nguyên, hành động và thời gian.
5. **Thực hiện:** người dùng thao tác qua môi trường quản trị được kiểm soát; hoạt động được ghi lại.
6. **Thu hồi tự động:** session hết hạn, grant bị thu hồi và credential tạm thời bị vô hiệu hóa.
7. **Đối soát:** xác nhận kết quả, kiểm tra audit log và đóng ticket.

Một phiên 30–60 phút có thể phù hợp với một số nhiệm vụ vận hành, nhưng thời lượng phải dựa trên công việc thực tế và chính sách tổ chức. Phiên không nên tự gia hạn vô hạn. Nếu cần thêm thời gian, người dùng phải cung cấp lý do và thực hiện lại bước phê duyệt tương ứng.

### Vì sao JIT tốt hơn quyền thường trực?

Quyền thường trực tạo ra một cửa sổ dài để tài khoản bị chiếm dụng hoặc bị lạm dụng. JIT giới hạn thời gian mà quyền nhạy cảm tồn tại, đồng thời gắn quyền với một nhiệm vụ và một bằng chứng phê duyệt cụ thể.

JIT không tự động làm yêu cầu trở nên an toàn. Nếu approver không xem xét nội dung, nếu grant cấp quá rộng hoặc nếu session có thể được chia sẻ, hệ thống chỉ tự động hóa việc cấp quyền rộng. Vì vậy, JIT phải kết hợp least privilege, kiểm tra policy, giám sát và thu hồi thực sự.

## 7. Dual control, quorum và key ceremony

Với thao tác có thể gây hậu quả nghiêm trọng, một người không nên có khả năng tự mình hoàn tất toàn bộ quy trình. Dual control yêu cầu ít nhất hai cá nhân độc lập cùng tham gia hoặc xác nhận một hành động nhạy cảm. Quorum yêu cầu đủ số người có thẩm quyền trước khi hành động được thực hiện.

Các trường hợp có thể cần dual control hoặc quorum:

- Import hoặc export key material.
- Khởi tạo, thay đổi hoặc phục hồi HSM security domain.
- Thay đổi policy gốc hoặc trust boundary.
- Hủy key quan trọng hoặc hủy key recovery.
- Khôi phục bản backup chứa vật liệu khóa.
- Thực hiện thao tác break-glass có ảnh hưởng lớn.
- Thay đổi cơ chế quản lý root key hoặc key-encryption hierarchy.

Không cần áp dụng quorum cho mọi thao tác đọc metadata hoặc mọi lần gọi encrypt thông thường. Mức kiểm soát phải tương xứng với tác động, tần suất và khả năng khôi phục.

### Dual control không phải chia sẻ mật khẩu

Hai người không nên cùng dùng một tài khoản hoặc trao đổi mật khẩu để tạo cảm giác có hai người tham gia. Mỗi người cần xác thực bằng danh tính riêng; hệ thống ghi nhận ai đã yêu cầu, ai đã phê duyệt và ai đã thực hiện.

Trong HSM ceremony, split knowledge có thể chia một bí mật quản trị thành nhiều phần hoặc dùng cơ chế quorum theo thiết kế của sản phẩm. Người giữ từng phần không có đủ thông tin để tự mình tái tạo bí mật hoàn chỉnh. Cần phân biệt split knowledge với threshold cryptography: split knowledge là biện pháp quản trị/giữ bí mật; threshold cryptography phân tán việc tạo chữ ký hoặc phép toán mật mã giữa nhiều bên theo giao thức.

### Một ceremony cần có bằng chứng

Một key ceremony nên xác định trước:

- Mục tiêu và phạm vi thao tác.
- Danh sách người tham gia và vai trò.
- Thiết bị, HSM partition hoặc key cụ thể.
- Điều kiện xác thực và kiểm tra môi trường.
- Thứ tự thao tác và điểm dừng nếu có sai lệch.
- Cách ghi nhận approval, log và bằng chứng.
- Cách xử lý khi một người tham gia mất kết nối hoặc từ chối.
- Kết quả xác minh sau ceremony.

Không ghi key material, PIN hoặc secret share vào biên bản. Biên bản nên lưu định danh tài nguyên, phiên bản, thời điểm, người tham gia, approval ID, kết quả và hash hoặc tham chiếu tới bằng chứng được bảo vệ.

## 8. Break-glass access cho tình huống khẩn cấp

Break-glass là cơ chế truy cập đặc biệt để xử lý sự cố khi quy trình thông thường không thể đáp ứng kịp thời. Ví dụ, KMS policy bị cấu hình sai khiến dịch vụ thanh toán không thể decrypt dữ liệu, hoặc hệ thống danh tính chính gặp sự cố trong khi cần khôi phục key.

Break-glass không nên trở thành đường tắt cho công việc hằng ngày. Cơ chế này cần được chuẩn bị và kiểm thử trước khi sự cố xảy ra.

Một thiết kế break-glass nên có:

- Danh tính riêng biệt, được bảo vệ bằng MFA mạnh và credential lưu giữ có kiểm soát.
- Phạm vi quyền tối thiểu đủ để phục hồi.
- Điều kiện kích hoạt rõ ràng và lý do khẩn cấp.
- Phê duyệt độc lập nếu thời gian cho phép; nếu buộc phải hành động ngay, yêu cầu review hậu kiểm bắt buộc.
- Session ngắn hạn, giới hạn tài nguyên và ghi nhận hoạt động.
- Cảnh báo tức thời tới nhóm bảo mật và người chịu trách nhiệm.
- Thu hồi hoặc xoay vòng credential sau khi sử dụng.
- Bài kiểm thử định kỳ để xác minh đường khẩn cấp còn hoạt động.

Break-glass không được bỏ qua mọi kiểm soát. Nếu phải giảm một bước phê duyệt để đáp ứng RTO, các kiểm soát khác như MFA, session recording, giới hạn hành động và hậu kiểm cần được tăng cường.

## 9. Audit, giám sát và rà soát quyền

Mọi hoạt động human access vào key cần để lại bằng chứng đủ để trả lời: ai đã làm gì, trên key nào, khi nào, từ đâu, vì lý do gì, theo approval nào và kết quả ra sao.

Một audit event hữu ích có thể gồm:

| Trường | Mục đích |
|---|---|
| Principal ID | Xác định cá nhân hoặc danh tính được liên kết |
| Session ID và source | Truy vết phiên và nguồn truy cập |
| Key ID/version | Xác định tài nguyên cụ thể |
| Operation | Biết thao tác metadata, decrypt, sign, policy update hay lifecycle |
| Timestamp | Xây dựng thứ tự sự kiện |
| Request/approval/ticket ID | Liên kết với lý do và phê duyệt |
| Policy decision | Ghi nhận allow/deny và điều kiện liên quan |
| Result/error code | Xác định thao tác thành công hay thất bại |
| Context an toàn | Tenant, application, environment hoặc resource đã được xác thực |

Không ghi key material, credential, plaintext, DEK bản rõ hoặc payload nhạy cảm vào audit log. Log cần được gửi tới hệ thống lưu trữ độc lập, có kiểm soát quyền sửa/xóa và có thời hạn lưu giữ phù hợp.

### Những tín hiệu cần cảnh báo

- Một cá nhân gọi decrypt hoặc sign với tần suất bất thường.
- Một principal lần đầu truy cập key thuộc hệ thống nhạy cảm.
- Quyền policy thay đổi ngay trước khi có decrypt, export hoặc delete.
- Người yêu cầu tự phê duyệt hoặc cố vượt qua SoD.
- Nhiều lần truy cập bị từ chối trên nhiều key.
- Phiên đặc quyền hoạt động ngoài khung thời gian hoặc từ nguồn bất thường.
- Quyền JIT không tự hết hạn hoặc session còn tồn tại sau khi ticket đóng.
- Một tài khoản nghỉ việc vẫn xuất hiện trong log.
- Break-glass được sử dụng nhưng không có incident record hoặc hậu kiểm.

Cảnh báo cần được kết nối với quy trình xử lý. Một sự kiện bất thường không tự chứng minh hành vi xấu, nhưng cần có người chịu trách nhiệm phân loại và quyết định hành động.

### Access review và recertification

Quyền truy cập phải được rà soát định kỳ và khi có thay đổi tổ chức. Reviewer cần kiểm tra quyền đang tồn tại, người sở hữu, mục đích, lần sử dụng gần nhất, phạm vi tài nguyên và approval liên quan.

Một quyền không được sử dụng trong thời gian dài nên được đánh giá để thu hồi. Không nên chỉ dựa vào “last used” vì một quyền recovery có thể hiếm khi được dùng nhưng vẫn cần thiết. Với quyền dự phòng, cần lưu owner, điều kiện kích hoạt và kết quả diễn tập.

## 10. Quy trình vận hành từ yêu cầu đến thu hồi

Sơ đồ sau mô tả một luồng human access điển hình:

~~~mermaid
flowchart TD
    A[Nhân sự tạo yêu cầu] --> B[Kiểm tra danh tính và MFA]
    B --> C{Yêu cầu hợp lệ?}
    C -->|Không| D[Từ chối và ghi audit]
    C -->|Có| E[Đánh giá key, action, scope và ticket]
    E --> F[Approver độc lập]
    F --> G{Được phê duyệt?}
    G -->|Không| D
    G -->|Có| H[Cấp JIT grant hoặc PAM session]
    H --> I[Thực hiện thao tác trong phạm vi]
    I --> J[Audit và giám sát]
    J --> K[Thu hồi quyền khi hết hạn]
    K --> L[Đối soát kết quả và đóng ticket]
~~~

### Ví dụ: kỹ sư cần decrypt một bản ghi production để điều tra

Giả sử nhóm vận hành cần kiểm tra một bản ghi thanh toán bị lỗi. Bản ghi được mã hóa bằng DEK, DEK được bọc bởi KEK trong KMS.

Quy trình nên diễn ra như sau:

1. Kỹ sư mở incident ticket, nêu ID bản ghi và lý do cần kiểm tra.
2. Hệ thống xác minh kỹ sư thuộc nhóm on-call có trách nhiệm với dịch vụ thanh toán.
3. Chủ sở hữu dữ liệu hoặc người phê duyệt độc lập xác nhận phạm vi điều tra.
4. PAM cấp session ngắn hạn. Policy chỉ cho phép thao tác cần thiết với key và context gắn với bản ghi/tenant đã xác thực.
5. Kỹ sư thực hiện qua công cụ quản trị có kiểm soát. Nếu có thể, dữ liệu được hiển thị qua giao diện an toàn và không được ghi vào terminal history, log hoặc tệp tạm không được bảo vệ.
6. Audit ghi principal, key, operation, context, ticket, approval, thời gian và kết quả.
7. Session tự hết hạn; quyền tạm thời được thu hồi.
8. Incident reviewer xác nhận dữ liệu được truy cập đúng phạm vi và ticket được đóng.

Không nên cấp quyền decrypt toàn bộ key của hệ thống thanh toán chỉ để điều tra một bản ghi. Nếu nền tảng không thể giới hạn theo từng bản ghi, cần áp dụng biện pháp bù như môi trường điều tra biệt lập, dữ liệu đã giảm nhạy cảm, giám sát phiên và phê duyệt tăng cường.

## 11. Xử lý khi nghi ngờ human access bị lạm dụng

Khi phát hiện tài khoản con người truy cập key bất thường, cần xử lý đồng thời danh tính, session, policy và tài nguyên bị ảnh hưởng.

Một trình tự phản ứng có thể gồm:

1. **Xác minh sự kiện:** đối chiếu principal, session, IP/device, ticket, approval và operation trong audit log.
2. **Containment:** thu hồi session/token, tạm khóa tài khoản hoặc bỏ grant JIT nếu có căn cứ; ngăn tiếp tục gọi các thao tác nhạy cảm.
3. **Bảo toàn bằng chứng:** giữ audit log, policy history, PAM recording và dấu vết thay đổi theo quy trình forensic.
4. **Đánh giá tác động:** xác định key nào bị truy cập, operation nào đã được gọi, ciphertext hoặc dữ liệu nào có thể đã bị giải mã, chữ ký nào có thể đã được tạo.
5. **Khôi phục kiểm soát:** sửa policy, thu hồi quyền gián tiếp, xoay credential danh tính và xem xét rotation/revocation key khi có dấu hiệu key material hoặc dữ liệu bảo vệ bị xâm phạm.
6. **Hậu kiểm:** xác định nguyên nhân, kiểm tra phạm vi ảnh hưởng, cập nhật role/policy và bổ sung kiểm thử.

Không phải mọi lần gọi decrypt trái quy trình đều đồng nghĩa key material đã bị lộ. Tuy nhiên, dữ liệu plaintext có thể đã bị truy cập và cần được đánh giá theo phạm vi tương ứng. Nếu private signing key chỉ được gọi sign mà không export, rủi ro vẫn có thể là chữ ký trái phép. Nếu người dùng chỉ xem metadata, tác động có thể chủ yếu là lộ thông tin cấu hình. Phân loại đúng operation giúp lựa chọn biện pháp ứng phó phù hợp.

## 12. Những sai lầm thường gặp

**Cấp quyền admin dài hạn cho cả đội kỹ thuật.** Một quyền quá rộng làm tăng tác động của tài khoản bị chiếm dụng và khiến khó xác định ai thực sự cần quyền. Hãy cấp role theo nhiệm vụ, key và thời hạn.

**Cho rằng non-exportable đồng nghĩa không thể lạm dụng.** Người có quyền decrypt hoặc sign vẫn có thể dùng key thông qua API. Cần giới hạn operation, context, dữ liệu và mục đích.

**Dùng chung tài khoản quản trị.** Điều này phá vỡ khả năng quy trách nhiệm. Mỗi người cần danh tính riêng và session riêng.

**Người yêu cầu tự phê duyệt.** Approval mất ý nghĩa nếu cùng một người kiểm soát cả yêu cầu lẫn quyết định. Cần SoD hoặc kiểm soát bù có bằng chứng.

**Chỉ dựa vào MFA.** MFA xác minh danh tính nhưng không giới hạn key, operation hoặc dữ liệu mà người dùng được phép truy cập.

**Dùng quyền thường trực vì JIT bất tiện.** Quyền kéo dài làm tăng thời gian phơi nhiễm. Cần cải thiện quy trình JIT và tự động hóa việc cấp/thu hồi thay vì bỏ kiểm soát.

**Để break-glass không được kiểm thử.** Một cơ chế khẩn cấp chưa từng diễn tập có thể thất bại đúng lúc cần thiết. Cần thử nghiệm có kiểm soát và hậu kiểm.

**Cho auditor quyền sửa log hoặc policy.** Người kiểm tra cần bằng chứng độc lập. Quyền đọc và quyền sửa phải được tách riêng.

**Không thu hồi quyền sau khi nhân sự đổi vai trò.** Membership cũ, session cũ và policy trực tiếp có thể tồn tại sau thay đổi nhân sự. Offboarding phải rà soát toàn bộ đường cấp quyền.

**Ghi plaintext hoặc key material vào log để tiện debug.** Log thường được sao chép và chia sẻ rộng. Chỉ ghi metadata và định danh cần thiết để truy vết.

## 13. Checklist thiết kế human access vào key

Khi đưa một hệ thống KMS/HSM vào production, có thể rà soát các điểm sau:

- [ ] Mỗi người dùng quản trị có danh tính cá nhân, không dùng tài khoản chung.
- [ ] Workforce identity được liên kết với IdP và quy trình onboarding/offboarding.
- [ ] MFA mạnh được yêu cầu cho quyền nhạy cảm.
- [ ] Role được thiết kế theo nhiệm vụ và least privilege.
- [ ] Quyền xem metadata, gọi phép toán, quản trị policy và truy cập key material được tách riêng.
- [ ] Decrypt, sign, unwrap và export được đánh giá theo tác động dữ liệu.
- [ ] Quyền được giới hạn theo key, tenant, ứng dụng, môi trường và purpose.
- [ ] Policy kiểm tra principal, resource, action và context đã xác thực.
- [ ] Quyền production nhạy cảm được cấp JIT/PAM và tự hết hạn.
- [ ] Yêu cầu có ticket, mục đích, thời lượng và người chịu trách nhiệm.
- [ ] Người yêu cầu và người phê duyệt được tách theo SoD.
- [ ] Dual control hoặc quorum được áp dụng cho thao tác có tác động rất cao.
- [ ] Break-glass có điều kiện kích hoạt, giám sát, thu hồi và hậu kiểm.
- [ ] Audit log ghi principal, session, key, operation, approval, kết quả và timestamp.
- [ ] Log được bảo vệ độc lập; người vận hành key không thể tự xóa bằng chứng.
- [ ] Có cảnh báo cho hành vi bất thường và thay đổi policy nhạy cảm.
- [ ] Quyền được recertify định kỳ và khi thay đổi vai trò.
- [ ] Có quy trình xử lý khi nghi ngờ tài khoản hoặc quyền key bị lạm dụng.
- [ ] Không ghi credential, plaintext hoặc key material vào log và ticket.
- [ ] Đường JIT, PAM, break-glass và thu hồi quyền được diễn tập định kỳ.

## 14. Kết luận

Human access vào key là quyền của con người đối với metadata, phép toán mật mã, policy và vòng đời khóa. Mỗi nhóm quyền có tác động khác nhau: xem metadata có thể tiết lộ thông tin vận hành; decrypt có thể làm lộ dữ liệu; sign có thể tạo hành động mang danh tính của tổ chức; thay đổi policy có thể mở rộng quyền; hủy key có thể làm mất khả năng giải mã.

Một mô hình an toàn bắt đầu từ danh tính cá nhân, least privilege và phân tách quyền theo từng thao tác. Quyền production nên được cấp đúng lúc, đúng key, đúng mục đích và tự hết hạn. Với thao tác có tác động cao, cần phê duyệt độc lập, dual control hoặc quorum. Audit độc lập, access review, break-glass được kiểm thử và quy trình ứng phó sự cố giúp tổ chức duy trì khả năng kiểm soát trong suốt vòng đời của key.

Con người vẫn cần tham gia vận hành hệ thống mật mã, nhưng quyền của họ phải được thiết kế để mỗi hành động có phạm vi, lý do, thời hạn và bằng chứng rõ ràng. Khi KMS/HSM thực hiện phép toán trong ranh giới bảo vệ và hệ thống danh tính quản lý quyền ngắn hạn theo nhiệm vụ, tổ chức có thể vận hành key hiệu quả mà giảm nguy cơ lộ dữ liệu, lạm dụng chữ ký và phá hủy khả năng khôi phục.

