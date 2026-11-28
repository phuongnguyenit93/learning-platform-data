# Approval trước khi cấp JIT

Trong quản lý truy cập đặc quyền (PAM), approval là quyết định chấp thuận một yêu cầu sử dụng quyền trong phạm vi xác định. Với just-in-time access (JIT), quyết định này phải có hiệu lực **trước khi quyền được cấp hoặc kích hoạt**, nếu chính sách yêu cầu phê duyệt trước. Việc bổ sung một dòng xác nhận sau khi người dùng đã có quyền không đáp ứng điều kiện đó.

Bài học thuộc chương **JIT và JEA**, tập trung vào cách phê duyệt quyền cho tài khoản quản trị, tài khoản dịch vụ và hạ tầng nhạy cảm. Mục tiêu là thiết kế luồng vừa hỗ trợ vận hành, vừa giữ nguyên nguyên tắc đặc quyền tối thiểu, kiểm soát thời hạn và có đủ bằng chứng để kiểm toán hoặc điều tra sự cố.

## 1. Kết quả cần đạt

Sau bài học, người học có thể:

- Phân biệt xác thực danh tính, đủ điều kiện xin quyền, phê duyệt và thực thi cấp quyền.
- Xác định người hoặc cơ chế được phép duyệt theo mức rủi ro và phân tách trách nhiệm.
- Ràng buộc quyết định với đúng chủ thể, thao tác, tài nguyên, phiên bản yêu cầu và thời hạn.
- Thiết kế vòng đời yêu cầu để quyền không xuất hiện khi còn thiếu phê duyệt.
- Xử lý thay đổi yêu cầu, quyết định hết hạn, lỗi bất đồng bộ, thu hồi và tình huống khẩn cấp.
- Lưu bằng chứng nối được người duyệt với quyền thực tế đã cấp và hoạt động sau đó.

## 2. Approval nằm ở đâu trong JIT và JEA?

**JIT** kiểm soát thời điểm quyền xuất hiện và thời gian quyền có hiệu lực. **JEA**, hiểu theo nguyên tắc just-enough access trong bài này, kiểm soát quyền đủ dùng: đúng thao tác, tài nguyên và điều kiện của công việc. Approval xác nhận rằng một yêu cầu cụ thể thỏa mãn chính sách để đi tiếp đến bước cấp quyền.

Các bước sau có ý nghĩa khác nhau:

| Bước | Câu hỏi được trả lời | Điều chưa được chứng minh |
|---|---|---|
| Xác thực | Ai đang gửi yêu cầu? | Người đó có được thực hiện công việc này hay không |
| Kiểm tra điều kiện xin quyền | Chủ thể có thuộc nhóm được phép yêu cầu quyền này không? | Lần yêu cầu hiện tại đã được chấp thuận chưa |
| Đánh giá chính sách | Yêu cầu có phù hợp các ràng buộc bắt buộc không? | Mọi phê duyệt cần thiết đã đầy đủ chưa |
| Phê duyệt | Ai hoặc cơ chế nào chấp thuận phiên bản yêu cầu này? | Quyền đã thực sự tồn tại ở hệ thống đích chưa |
| Cấp/kích hoạt quyền | Hệ thống đích đã tạo quyền hiệu lực nào? | Mọi thao tác về sau đều nằm trong phạm vi hay không |
| Giám sát và thu hồi | Quyền được dùng thế nào và đã chấm dứt chưa? | Tác động đã xảy ra có được tự động đảo ngược hay không |

MFA giúp tăng độ tin cậy khi xác thực chủ thể hoặc người duyệt. MFA không tự thay thế quyết định phê duyệt độc lập. Tương tự, có mã ticket không đồng nghĩa với việc người có thẩm quyền đã chấp thuận quyền đặc biệt được yêu cầu.

Một người có quyền duyệt cũng không nhất thiết cần có quyền quản trị trực tiếp trên tài nguyên. Vai trò ra quyết định và danh tính kỹ thuật thực thi cấp quyền nên được giới hạn theo trách nhiệm riêng.

## 3. Yêu cầu phải đủ cụ thể để có thể duyệt

Người duyệt cần biết chính xác điều gì sẽ xảy ra nếu chọn chấp thuận. Yêu cầu “cần quyền admin để xử lý gấp” thiếu dữ liệu để đánh giá phạm vi và tác động.

Một yêu cầu có thể kiểm tra được nên có các trường sau:

| Nhóm thông tin | Nội dung cần làm rõ |
|---|---|
| Chủ thể nhận quyền | Định danh cá nhân hoặc workload, miền quản lý/tenant, danh tính sẽ được cấp quyền |
| Mục đích | Công việc hoặc sự cố cụ thể, mã tham chiếu và kết quả cần đạt |
| Tài nguyên | Định danh đích, môi trường, chủ sở hữu và mức nhạy cảm |
| Thao tác | Hành động cần làm; tránh gộp thành “toàn quyền” nếu không cần |
| Thời gian | Cửa sổ được phép kích hoạt, thời lượng tối đa, thời điểm kết thúc tuyệt đối |
| Kênh sử dụng | Broker, phiên quản trị, API hoặc cách truy cập được kiểm soát |
| Kiểm soát đi kèm | Điều kiện xác thực, ghi nhận hoạt động, hạn chế xuất credential và cơ chế thu hồi |
| Phiên bản | Phiên bản nội dung và chính sách làm căn cứ cho quyết định |

Các thuộc tính ảnh hưởng đến mức rủi ro cần lấy từ nguồn được kiểm soát. Không để người xin quyền tự khai một máy production thành development để được áp dụng luồng duyệt nhẹ hơn. Mã ticket cũng cần được đối chiếu về đối tượng, trạng thái và tính liên quan khi chính sách sử dụng nó làm điều kiện.

### Ví dụ viết lại yêu cầu

Yêu cầu ban đầu:

> Cấp admin production 30 phút để xử lý INC-2088.

Yêu cầu có thể duyệt:

> Cấp cho `engineer-184` quyền xem trạng thái và khởi động lại service instance `svc-72e8` thuộc miền Acme, môi trường production, để xử lý INC-2088. Thao tác đi qua broker PAM, không mở shell và không xuất credential. Chỉ được kích hoạt trong cửa sổ đã duyệt, tối đa 20 phút mỗi lần cấp, với một lần kích hoạt cho yêu cầu này.

Ví dụ sau thu hẹp cả thao tác lẫn tài nguyên. Approval không nên trở thành cơ chế hợp thức hóa yêu cầu rộng chỉ vì thời gian sử dụng ngắn.

## 4. Chọn người duyệt và phân tách trách nhiệm

### 4.1. Thẩm quyền phải gắn với phạm vi quyết định

Một người được duyệt truy cập cho hệ thống A không tự có thẩm quyền duyệt cho hệ thống B. Quy tắc tìm người duyệt nên dựa trên chủ sở hữu tài nguyên, môi trường, loại quyền và trách nhiệm được giao.

Ví dụ phân công mang tính minh họa:

| Loại yêu cầu | Người/cơ chế có thể được tổ chức chỉ định | Lý do |
|---|---|---|
| Thao tác hẹp, ít tác động trên môi trường thực hành | Chính sách tự động hoặc người phụ trách môi trường | Điều kiện dễ xác minh và tác động đã được giới hạn |
| Restart một dịch vụ production | Chủ sở hữu dịch vụ hoặc người trực được ủy quyền | Hiểu ảnh hưởng vận hành và thời điểm phù hợp |
| Đọc secret nhạy cảm hoặc sửa quyền quản trị | Thêm người duyệt độc lập theo chính sách | Tác động rộng hơn và có nguy cơ mở đường truy cập khác |
| Công việc khẩn cấp | Vai trò ứng cứu được chỉ định, hoặc luồng khẩn cấp riêng | Cần thời gian phản ứng ngắn nhưng vẫn quy trách nhiệm được |

Đây không phải số lượng người duyệt bắt buộc cho mọi tổ chức. Cần chọn kiểm soát phù hợp với rủi ro thực tế và yêu cầu quản trị của hệ thống.

### 4.2. Không để việc tự duyệt làm mất tính độc lập

Nếu chính sách yêu cầu phê duyệt độc lập, người nhận quyền không được duyệt yêu cầu của chính mình. Cần so sánh danh tính gốc, không chỉ tên tài khoản: cùng một người dùng hai tài khoản vẫn có thể là tự duyệt.

Với yêu cầu cần hai người duyệt, hai quyết định phải đáp ứng điều kiện độc lập đã đặt ra. Hai lần bấm của cùng người, hoặc cùng danh tính qua hai nhóm, không tạo ra hai người duyệt độc lập.

Cũng cần xem xét xung đột lợi ích và quyền sửa chính sách. Một người có thể không trực tiếp tự duyệt nhưng lại sửa nhóm người duyệt hoặc sửa luồng để yêu cầu của mình tự được thông qua. Các thay đổi này cần được kiểm soát theo mức ảnh hưởng.

### 4.3. Ủy quyền và thay ca

Ủy quyền duyệt cần có phạm vi và thời hạn: ai ủy quyền, cho ai, áp dụng với tài nguyên hoặc loại yêu cầu nào, từ lúc nào đến lúc nào. Không dùng việc chuyển tiếp email như bằng chứng duy nhất về thẩm quyền.

Khi người duyệt vắng mặt, hệ thống có thể chuyển đến người thay thế đã được chỉ định. Việc không có người phản hồi không làm phát sinh quyền. Một yêu cầu hết thời gian chờ cần chuyển trạng thái rõ ràng thay vì tự coi là được duyệt.

Thẩm quyền phải được kiểm tra tại thời điểm quyết định. Trước khi cấp quyền, cần xác minh quyết định chưa bị thu hồi và vẫn đáp ứng chính sách hiện hành; cách xử lý khi người duyệt đổi vai trò sau lúc duyệt phải được quy định rõ, không suy đoán từ việc quyết định từng hợp lệ.

## 5. Ràng buộc quyết định với đúng phiên bản yêu cầu

Một quyết định có giá trị với nội dung cụ thể đã được duyệt. Nếu nội dung thay đổi, cần đánh giá lại ảnh hưởng tới quyết định đó.

Có thể hình dung một gói dữ liệu cần ràng buộc:

```text
request_id + request_version
+ chủ thể nhận quyền + miền quản lý
+ tập tài nguyên + tập thao tác
+ cửa sổ kích hoạt + thời lượng tối đa + hạn kết thúc
+ kênh sử dụng + điều kiện bắt buộc
+ phiên bản chính sách liên quan
```

Hệ thống nên lưu bản chụp nội dung được duyệt hoặc cách tham chiếu bất biến tới nội dung đó. Nếu dùng digest để phát hiện sửa đổi, dữ liệu phải có cách chuẩn hóa nhất quán và bản ghi quyết định vẫn phải được bảo vệ. Một giá trị hash do bên không tin cậy tự gửi không thay thế xác thực và kiểm soát toàn vẹn.

### Những thay đổi thường cần phê duyệt lại

- Thêm tài nguyên hoặc chuyển sang môi trường có mức nhạy cảm khác.
- Tăng thao tác, đổi sang vai trò rộng hơn hoặc cho phép xuất credential.
- Đổi người nhận quyền, danh tính thực thi hoặc miền quản lý.
- Kéo dài thời lượng, mở thêm lần kích hoạt hoặc đổi cửa sổ sử dụng.
- Thay kênh truy cập theo cách làm mất kiểm soát phiên hoặc thao tác.

Nếu người duyệt muốn thu hẹp yêu cầu, giao diện phải thể hiện rõ tập quyền cuối cùng và lưu phiên bản đó. Không để một người duyệt phiên bản 2 còn người khác duyệt phiên bản 3 rồi gộp hai quyết định như thể cùng duyệt một nội dung.

Để đơn giản và dễ kiểm toán, có thể yêu cầu mọi quyết định bắt buộc cùng tham chiếu một phiên bản cuối cùng. Những thay đổi chỉ mang tính trình bày có thể được xử lý nhẹ hơn nếu chính sách phân biệt được chúng và vẫn giữ lịch sử.

## 6. Phân biệt các mốc thời gian

Các mốc sau không đồng nghĩa với nhau:

| Mốc | Ý nghĩa |
|---|---|
| Hạn chờ phê duyệt | Sau mốc này, yêu cầu chưa đủ quyết định không còn tiếp tục luồng cũ |
| Hạn kích hoạt của quyết định | Sau mốc này, không được dùng quyết định để tạo một grant mới |
| Cửa sổ vận hành | Khoảng thời gian công việc đặc quyền được phép diễn ra |
| Thời lượng tối đa của grant | Khoảng thời gian quyền có hiệu lực kể từ lúc kích hoạt thành công theo thiết kế |
| Hạn kết thúc tuyệt đối | Quyền phải hết hiệu lực muộn nhất ở mốc này |

Ví dụ minh họa, tất cả thời điểm cùng ngày và múi giờ `+07:00`:

```text
09:00  Gửi yêu cầu phiên bản 3.
09:03  Chủ sở hữu dịch vụ duyệt phiên bản 3.
09:05  Người duyệt độc lập duyệt phiên bản 3.
09:15  Hạn cuối được bắt đầu kích hoạt từ các quyết định này.
09:40  Hạn kết thúc tuyệt đối của quyền.
20 phút  Thời lượng tối đa cho một grant.
```

Nếu kích hoạt thành công lúc 09:10, quyền hết hạn muộn nhất lúc 09:30. Việc hạn kích hoạt đến lúc 09:15 không có nghĩa grant đã tạo lúc 09:10 phải hết hạn lúc 09:15; đây là hai ràng buộc khác nhau trong thiết kế ví dụ.

```text
expires_at = min(activated_at + maximum_duration, absolute_end_at)
```

Một yêu cầu bắt đầu kích hoạt lúc 09:16 phải bị từ chối theo cửa sổ kích hoạt, dù hạn kết thúc tuyệt đối vẫn chưa đến. Nếu thao tác cấp quyền mất thời gian và đã vượt điều kiện thời gian trước khi quyền có thể có hiệu lực, hệ thống phải kiểm tra lại hoặc áp dụng cơ chế bảo đảm không cấp grant muộn ngoài điều kiện.

Quy tắc xử lý đúng tại ranh giới thời gian phải rõ ràng, chẳng hạn dùng khoảng nửa mở `start <= now < end`. Đồng hồ phục vụ quyết định cần được quản lý tin cậy; không lấy thời gian do máy người yêu cầu cung cấp làm căn cứ duy nhất.

## 7. Vòng đời yêu cầu và điều kiện chuyển trạng thái

Một luồng tham khảo:

```text
DRAFT → SUBMITTED → PENDING_APPROVAL → APPROVED → GRANTING → ACTIVE
                         │                 │          │         │
                         ├→ REJECTED       ├→ EXPIRED │         ├→ REVOKED
                         ├→ EXPIRED        └→ CANCELLED         └→ EXPIRED
                         └→ CANCELLED                 │
                                                     ├→ FAILED
                                                     └→ RECONCILIATION_REQUIRED
```

Sơ đồ rút gọn để phân biệt những trạng thái quan trọng; hệ thống thực tế có thể tách trạng thái yêu cầu và trạng thái grant thành hai đối tượng riêng. Ví dụ, một yêu cầu bị hủy khi đang cấp quyền vẫn cần xử lý grant có thể đã được tạo ở đích.

- **PENDING_APPROVAL:** còn thiếu quyết định bắt buộc; không cấp quyền hiệu lực từ yêu cầu này.
- **APPROVED:** đủ quyết định cho đúng phiên bản; chưa đồng nghĩa quyền đã có ở đích.
- **GRANTING:** đang thực hiện thay đổi tại hệ thống đích; phải kiểm soát việc gọi lặp và hủy đồng thời.
- **ACTIVE:** đã có bằng chứng về grant thực tế, đúng phạm vi và thời hạn.
- **REJECTED/EXPIRED/CANCELLED:** không được tiếp tục cấp mới từ yêu cầu đó.
- **RECONCILIATION_REQUIRED:** chưa xác định chắc chắn trạng thái ở hệ thống đích; cần đối soát và xử lý quyền có thể đã phát sinh.

### 7.1. Kiểm tra ngay trước bước cấp quyền

Logic sau là **mã giả**, không phải cấu hình hoặc chương trình dùng trực tiếp cho một sản phẩm:

```text
function prepare_grant(request_id, requested_version, caller):
    request = load_current_request_with_concurrency_control(request_id)
    require caller_can_activate_for_subject(caller, request.subject)
    require request.version == requested_version
    require request.state == APPROVED
    require not request.cancelled
    require activation_window_is_open(trusted_now())
    require request.activation_count < request.maximum_activations

    decisions = load_decisions_for(request.id, request.version)
    require required_approvals_are_satisfied(decisions)
    require decisions_are_authentic_and_not_revoked(decisions)
    require approver_authority_rules_are_satisfied(decisions)
    require separation_of_duties_rules_are_satisfied(decisions)

    require subject_is_still_eligible(request.subject)
    require targets_still_match_approved_scope(request.resources)
    require mandatory_controls_are_available(request)
    require policy_still_allows_this_grant(request)

    grant_operation = reserve_one_activation_and_record_intent(
        request,
        idempotency_key_for_this_activation
    )
    return grant_operation
```

Sau bước chuẩn bị, thành phần cấp quyền mới thực hiện thao tác với hệ thống đích và xác minh quyền tạo ra. Cần bảo vệ khoảng thời gian giữa kiểm tra và sử dụng: khóa hoặc kiểm soát phiên bản ở kho yêu cầu, kiểm tra lại điều kiện cần thiết và xử lý đối soát ở đích.

Kiểm soát đồng thời trong kho yêu cầu không tự làm mọi thay đổi trên hệ thống ngoài trở thành một giao dịch nguyên tử. Thiết kế phải dự liệu trường hợp một bên thành công trong khi bên kia chưa ghi nhận được kết quả.

### 7.2. Không dùng APPROVED làm quyền truy cập trực tiếp

Một URL “đã được duyệt”, trường boolean do client gửi hoặc mã ticket không phải credential cấp quyền. Backend phải tự tải quyết định, kiểm tra phiên bản và xác nhận điều kiện trước khi cấp grant.

Thông báo email hoặc chat chỉ nên dẫn người duyệt đến luồng xác thực và hiển thị đầy đủ yêu cầu. Không để việc xem trước liên kết hoặc một truy cập GET đơn thuần tự tạo quyết định phê duyệt. Hành động duyệt phải được xác thực, ràng buộc với nội dung và được ghi nhận rõ ràng.

## 8. Ví dụ chính sách phê duyệt cho một thao tác production

Đặc tả dưới đây là **YAML minh họa**, không phải cú pháp của một nền tảng PAM cụ thể:

```yaml
request_id: JIT-2088
request_version: 3
subject:
  type: human
  id: engineer-184
management_domain: acme
work_reference: INC-2088
resources:
  - type: os_service_instance
    id: svc-72e8
actions:
  - service.status
  - service.restart
approval:
  mode: human
  required_roles:
    - service_owner
    - independent_operations_approver
  distinct_people_required: 2
  requester_may_approve: false
  decisions_bound_to_request_version: true
  activation_deadline: '2026-11-26T09:15:00+07:00'
activation:
  maximum_count: 1
  maximum_duration_minutes: 20
  absolute_end_at: '2026-11-26T09:40:00+07:00'
execution:
  channel: pam_broker
  arbitrary_shell_allowed: false
  credential_export_allowed: false
  activity_evidence_required: true
policy_version: pam-production-v7
```

Trong ví dụ, hai người là yêu cầu riêng của chính sách giả định cho tình huống này. Đạt hai quyết định không cho phép mở rộng sang mọi dịch vụ, tăng thời hạn hoặc đổi người nhận quyền. Các điều kiện đó vẫn phải giữ nguyên.

`activity_evidence_required` cần được triển khai bằng cơ chế thực tế có thể kiểm tra. Đặt cờ này trong yêu cầu không tự tạo được log hoặc bản ghi phiên. Nếu một kiểm soát bắt buộc không sẵn sàng, hành vi cho phép hay từ chối phải theo chính sách đã định; với luồng yêu cầu kiểm soát đó làm điều kiện cấp quyền, không được âm thầm bỏ qua để cấp tiếp.

Khi cấp thành công, lưu thêm mã grant, danh tính có hiệu lực ở đích, thời điểm thực tế, thời hạn thực tế và tham chiếu tới các quyết định. Nếu đích không thể thực thi phạm vi đã duyệt, không tự đổi sang vai trò quản trị rộng hơn.

## 9. Phê duyệt tự động và tài khoản dịch vụ

Không phải mọi mô hình JIT đều yêu cầu một người bấm duyệt cho từng lần cấp. Tổ chức có thể cho phép quyết định tự động khi chính sách xác định rõ các trường hợp đủ điều kiện và tác động được kiểm soát.

Ví dụ, workload đã được xác thực có thể nhận credential ngắn hạn để đọc đúng một tài nguyên cần cho công việc, trong một môi trường xác định. Điều kiện có thể bao gồm danh tính workload, thuộc tính tài nguyên từ kiểm kê tin cậy, tập thao tác hẹp, giới hạn thời hạn và tín hiệu rủi ro có nguồn xác minh.

Cần phân biệt:

- **Phê duyệt chính sách trước:** con người có thẩm quyền cho phép một lớp yêu cầu trong các điều kiện xác định.
- **Quyết định tự động từng lần:** bộ máy kiểm tra yêu cầu hiện tại có thỏa mãn chính sách đó không.
- **Cấp quyền từng lần:** tạo grant hoặc credential với phạm vi và thời hạn thực tế.

Không coi việc “chạy bằng tài khoản dịch vụ” là lý do để bỏ qua kiểm soát. Danh tính dùng để cấp quyền không nên có khả năng tùy ý sửa chính sách tự duyệt hoặc giả mạo thuộc tính đầu vào.

Với workload hoạt động liên tục, chính sách có thể cho phép cấp lặp hoặc gia hạn theo điều kiện. Phải quy định rõ điều kiện tái đánh giá, giới hạn phiên hoặc chu kỳ công việc, và cách dừng cấp khi workload không còn hợp lệ. Không biến một phê duyệt ngắn hạn thành chuỗi gia hạn vô hạn ngoài ý định ban đầu.

Các yêu cầu vượt ngưỡng, thay tài nguyên hoặc tăng quyền cần đi vào luồng phù hợp thay vì được coi là một lần gia hạn bình thường. Chính sách tự động cũng cần được quản lý phiên bản, kiểm soát sửa đổi và lưu dấu vết quyết định.

## 10. Xử lý lỗi, thay đổi và tình huống khẩn cấp

### 10.1. Người duyệt không phản hồi

Gửi nhắc hoặc chuyển cấp theo vai trò đã được định nghĩa. Khi hết hạn, đóng yêu cầu hoặc yêu cầu gửi lại theo chính sách. Không dùng quy tắc “im lặng là đồng ý” nếu luồng yêu cầu chấp thuận rõ ràng.

Để giảm chậm trễ, cần có lịch trực, người dự phòng, thông tin yêu cầu đầy đủ và tiêu chí ưu tiên. Giải pháp vận hành không nên là cấp trước rồi chờ duyệt sau.

### 10.2. Có quyết định từ chối nhưng cũng có quyết định chấp thuận

Quy tắc kết hợp quyết định phải rõ ràng. Một thiết kế có thể quy định bất kỳ quyết định từ chối hợp lệ nào trong vòng duyệt hiện tại sẽ chặn cấp quyền. Không chỉ đếm số chấp thuận mà bỏ qua từ chối.

Nếu cần sửa yêu cầu để giải quyết lý do từ chối, tạo phiên bản mới và thu thập quyết định theo quy tắc cho phiên bản đó. Quyết định đến muộn cho phiên bản cũ không được tự áp dụng cho phiên bản mới.

### 10.3. API cấp quyền timeout hoặc sự kiện bị gửi lặp

Timeout có thể xảy ra sau khi hệ thống đích đã cấp quyền. Không kết luận “chưa cấp” chỉ vì không nhận được phản hồi, rồi gọi lại theo cách tạo thêm grant hoặc kéo dài thời hạn.

Cần có mã thao tác ổn định cho một lần kích hoạt, khả năng nhận diện yêu cầu lặp, truy vấn quyền thực tế và đối soát. Gọi lặp cùng thao tác không được tạo thêm một lần cấp quyền ngoài giới hạn đã duyệt. Chỉ tăng số lần kích hoạt theo một quy tắc nhất quán, có thể khôi phục sau lỗi.

Khi trạng thái chưa rõ, tạm chặn kích hoạt tiếp theo từ yêu cầu đó và xử lý quyền có thể đã xuất hiện. Nếu phát hiện grant sai hoặc cấp dở, thu hồi theo khả năng hệ thống và ghi nhận kết quả. Không đánh dấu FAILED rồi bỏ mặc quyền ở đích.

### 10.4. Hủy hoặc thu hồi trong lúc đang cấp quyền

Một lệnh hủy ở kho yêu cầu không tự ngăn được thao tác cấp quyền đã gửi sang hệ thống ngoài. Thành phần thực thi cần kiểm tra lại trạng thái, đối soát kết quả và thu hồi nếu quyền đã xuất hiện sau khi yêu cầu không còn hợp lệ.

Với grant đang hoạt động, thu hồi quyết định và thu hồi quyền là những hành động liên quan nhưng khác nhau. Phải có luồng gỡ quyền, xử lý token/phiên và xác minh tác dụng. Đổi mật khẩu trong vault hoặc gỡ một nhóm không bảo đảm mọi phiên đã mở đều kết thúc.

### 10.5. Cần mở rộng quyền giữa sự cố

Nếu sau restart cần sửa cấu hình hoặc thêm tài nguyên, gửi yêu cầu bổ sung hoặc phiên bản mới theo chính sách. Nêu rõ phần tăng thêm để người duyệt đánh giá. Không để broker tự nâng lên admin vì thao tác hẹp thất bại.

### 10.6. Truy cập khẩn cấp

Nếu tổ chức có luồng break-glass, luồng đó cần điều kiện kích hoạt, chủ thể được phép, thời hạn ngắn, phạm vi tối thiểu có thể thực thi, thông báo và bằng chứng phù hợp. Chính sách cũng phải xác định ai chịu trách nhiệm xử lý sau khi sử dụng.

Khi tình huống không thể chờ phê duyệt trước, đó là một luồng ngoại lệ được quản trị riêng. Không ghi một phê duyệt hồi tố thành bằng chứng rằng điều kiện “approval trước khi cấp JIT” đã được đáp ứng. Rà soát sau sự kiện vẫn hữu ích để xác minh lý do, tác động và việc thu hồi.

## 11. Bằng chứng cho kiểm toán và ứng phó sự cố

Chuỗi bằng chứng cần trả lời được: **ai xin, ai duyệt, duyệt nội dung nào, quyền nào đã xuất hiện và quyền đó đã được dùng ra sao**.

| Sự kiện | Dữ liệu cần liên kết |
|---|---|
| Gửi yêu cầu | Request ID, phiên bản, chủ thể, mục đích, tài nguyên, thao tác và thời gian |
| Quyết định duyệt/từ chối | Danh tính người hoặc bộ máy ra quyết định, thẩm quyền, thời điểm, phiên bản yêu cầu và chính sách |
| Kiểm tra trước cấp | Kết quả kiểm tra hiệu lực quyết định, điều kiện chủ thể, đích và kiểm soát bắt buộc |
| Cấp/kích hoạt | Mã thao tác, mã grant, danh tính hiệu lực, quyền thực tế, đích và thời hạn thực tế |
| Sử dụng quyền | Chủ thể, phiên hoặc token tham chiếu, thao tác, tài nguyên, kết quả và thời gian |
| Hủy/hết hạn/thu hồi | Lý do, thời điểm, các quyền/phiên liên quan và kết quả xác minh |

Bản ghi quyết định cần bảo vệ khỏi sửa hoặc xóa trái phép. Có thể dùng lịch sử sự kiện chỉ ghi thêm kết hợp kiểm soát truy cập và lưu trữ phù hợp; không chỉ giữ một trường `approved=true` có thể bị ghi đè mà không có lịch sử.

Không ghi mật khẩu, token, khóa riêng hoặc nội dung secret vào bằng chứng. Đầu ra lệnh và bản ghi phiên cũng có thể chứa dữ liệu nhạy cảm nên cần quyền truy cập và thời hạn lưu phù hợp.

Khi điều tra, cần so sánh thời điểm quyền thực sự có hiệu lực với thời điểm đủ phê duyệt. Đồng thời đối chiếu tập quyền đã cấp với phiên bản được duyệt. Một hệ thống ghi APPROVED sớm nhưng thực tế dùng quyết định sai phiên bản vẫn không đáp ứng mục tiêu kiểm soát.

Các dấu hiệu đáng điều tra gồm: cùng một người xin và duyệt qua hai tài khoản, phê duyệt hàng loạt rất nhanh, thay đổi nhóm người duyệt ngay trước yêu cầu nhạy cảm, kích hoạt sau hạn, quyền tồn tại sau thu hồi hoặc thao tác ở đích không có grant tương ứng.

## 12. Bài tập thiết kế và kiểm thử chấp nhận

### Tình huống thực hành

Kỹ sư trực ca cần restart `svc-72e8` để xử lý sự cố. Chính sách giả định yêu cầu hai người độc lập duyệt, một lần kích hoạt và thời lượng tối đa 20 phút. Trong lúc chờ, người yêu cầu thêm quyền sửa cấu hình. Sau khi gửi cấp quyền, API đích timeout.

### Các việc cần thiết kế

1. Xác định thông tin bắt buộc của yêu cầu, thẩm quyền hai người duyệt và cách chống tự duyệt qua tài khoản khác.
2. Quy định phiên bản mới khi thêm quyền sửa cấu hình và cách vô hiệu hóa việc dùng quyết định của phiên bản cũ.
3. Phân biệt hạn kích hoạt, thời lượng grant và thời điểm phải chấm dứt quyền.
4. Thiết kế mã thao tác cho một lần kích hoạt, cách tra quyền ở đích và cách xử lý timeout.
5. Chỉ ra các bằng chứng cần có để chứng minh quyền xuất hiện sau khi đủ phê duyệt hợp lệ.
6. Mô tả thu hồi nếu yêu cầu bị hủy trong khi đích đã cấp quyền nhưng backend chưa nhận phản hồi.

### Hướng giải tham khảo

Đóng băng nội dung mỗi phiên bản để quyết định duyệt có đích tham chiếu rõ ràng. Bổ sung sửa cấu hình làm thay đổi quyền nên phải đi qua quyết định phù hợp cho phiên bản mới. Không cộng quyết định giữa hai phiên bản. Trước kích hoạt, kiểm tra đủ quyết định, điều kiện hiện hành và giới hạn một lần cấp.

Nếu API timeout, giữ trạng thái cần đối soát và truy vấn hệ thống đích bằng mã thao tác hoặc tham chiếu được hỗ trợ. Không cấp lặp mù. Nếu quyền đã xuất hiện, xác minh phạm vi và thời hạn; nếu yêu cầu đã bị hủy hoặc grant không hợp lệ thì xử lý thu hồi và lưu kết quả. Chỉ tuyên bố quyền đã hết hiệu lực khi có cơ sở xác minh phù hợp với hệ thống đích.

### Ma trận kiểm thử

Thực hiện trên môi trường thực hành được phép, với quyền và tài nguyên thử nghiệm.

| Ca kiểm tra | Kết quả mong đợi |
|---|---|
| Chưa có quyết định hoặc chỉ có một trong hai quyết định bắt buộc | Không tạo quyền hiệu lực |
| Có đủ hai người độc lập duyệt cùng phiên bản và mọi điều kiện hợp lệ | Tạo đúng một grant, đúng quyền và thời hạn |
| Cùng một người duyệt qua hai tài khoản | Không đáp ứng điều kiện hai người độc lập |
| Một quyết định đến cho phiên bản cũ | Không được dùng để đủ điều kiện phiên bản mới |
| Sửa tài nguyên, thao tác hoặc thời lượng sau duyệt | Không tái sử dụng quyết định cũ để cấp quyền mở rộng |
| Quyết định bị thu hồi, yêu cầu bị hủy hoặc quá hạn kích hoạt | Chặn cấp mới và xử lý grant có thể đã phát sinh |
| API đích timeout rồi nhận lại cùng mã thao tác | Đối soát; không tạo grant trùng hoặc kéo dài quyền ngoài phê duyệt |
| Đích chỉ hỗ trợ vai trò rộng hơn yêu cầu được duyệt | Không tự cấp vai trò rộng hơn |
| Kiểm soát bắt buộc như kênh broker hoặc bằng chứng hoạt động không sẵn sàng | Xử lý theo chính sách đã định, không bỏ qua điều kiện một cách âm thầm |
| Hết thời hạn grant trong khi phiên vẫn mở | Chặn thao tác đặc quyền tiếp theo theo thiết kế; xác minh thu hồi và xử lý phiên |
| Quyền được sử dụng qua tài khoản quản trị thường trực khác | Phát hiện đường truy cập riêng; không coi grant JIT hẹp là đã giới hạn toàn bộ quyền của chủ thể |

Kết quả cần chứng minh bằng trạng thái và log ở cả bộ điều phối lẫn hệ thống đích. Một giao diện hiển thị “đã duyệt” hoặc “đã hết hạn” chưa đủ thay thế bằng chứng về quyền thực tế.