# Approval owner

## 1. Approval owner chịu trách nhiệm về quyết định nào?

Trong quản lý quyền truy cập đặc biệt (Privileged Access Management — PAM), **approval owner** là cá nhân hoặc nhóm được giao trách nhiệm tổ chức và đưa ra quyết định phê duyệt trong một phạm vi xác định. Phạm vi đó có thể là truy cập quản trị một ứng dụng, lấy credential từ vault, kích hoạt quyền JIT hoặc thay đổi một nhóm quyền nhạy cảm.

Trong bài học này, thuật ngữ được dùng theo nghĩa trách nhiệm quản trị. Tên trường và cách triển khai trong từng sản phẩm có thể khác nhau. Điều cần xác định là: **ai có thẩm quyền chấp nhận yêu cầu nào, trên tài nguyên nào, với những điều kiện gì**.

Approval owner không chỉ là địa chỉ nhận thông báo. Một nhóm nhận được yêu cầu nhưng không có người có thẩm quyền, không hiểu tài nguyên hoặc không tiếp nhận công việc chưa tạo thành cơ chế phê duyệt có thể vận hành.

Ví dụ, Lan cần quyền khởi động lại một dịch vụ sản xuất trong 15 phút. Người quản lý của Lan có thể xác nhận nhu cầu công việc, nhưng chưa chắc có thẩm quyền chấp nhận quyền quản trị toàn máy. Nhóm chịu trách nhiệm dịch vụ cần xác nhận phạm vi thao tác và tác động kỹ thuật theo chính sách áp dụng.

Xác định đúng approval owner giúp PAM phối hợp least privilege, JIT/JEA, quản lý credential, giám sát phiên và lưu bằng chứng. Phê duyệt phải gắn với yêu cầu cụ thể; nó không thay thế cơ chế thực thi quyền tại hệ thống đích.

## 2. Phân biệt approval owner với các vai trò liên quan

| Vai trò | Trách nhiệm chính | Không tự động suy ra |
|---|---|---|
| Người yêu cầu | Nêu mục đích, tài nguyên, hành động và thời gian cần truy cập | Được tự chấp nhận yêu cầu của mình |
| Account owner | Chịu trách nhiệm về mục đích và vòng đời tài khoản | Có quyền phê duyệt mọi truy cập tới mọi tài nguyên mà tài khoản chạm tới |
| Asset owner | Chịu trách nhiệm với tài nguyên hoặc dịch vụ | Luôn là người duyệt duy nhất cho mọi loại thay đổi |
| Approval owner | Chịu trách nhiệm về phạm vi và quy trình phê duyệt được giao | Được tự mở rộng phạm vi thẩm quyền |
| Approver | Chủ thể thực hiện một quyết định phê duyệt cụ thể | Có thẩm quyền chỉ vì nhận được liên kết yêu cầu |
| Người thực thi hoặc hệ thống cấp quyền | Cấp grant, phát hành credential hoặc áp dụng thay đổi | Được bỏ qua quyết định hoặc điều kiện phê duyệt |
| Người rà soát | Đánh giá quyết định và hoạt động sau đó | Có thể thay thế mọi bước phê duyệt trước truy cập |
| Người chấp nhận rủi ro | Quyết định ngoại lệ theo thẩm quyền | Mặc nhiên là người quản trị kỹ thuật hoặc người yêu cầu |

Approval owner có thể là một nhóm, còn approver là thành viên đủ điều kiện ra quyết định cho lần yêu cầu cụ thể. Cần lưu cả đơn vị chịu trách nhiệm và danh tính thực hiện quyết định.

Một người có thể đảm nhiệm nhiều vai trò khi chính sách cho phép. Với yêu cầu phải tách biệt nhiệm vụ, hệ thống cần kiểm tra tính độc lập thực tế. Cùng một người dùng hai tài khoản không trở thành hai approver độc lập.

Trong một số quy trình, approval owner chịu trách nhiệm duy trì ma trận phê duyệt và tổ chức người trực; không có nghĩa mọi thành viên của nhóm đó đều được duyệt. Quyền duyệt cần được cấp và kiểm tra riêng.

## 3. Gắn thẩm quyền với phạm vi trong inventory

Một trường approval owner chung trên tài khoản có thể không đủ nếu tài khoản truy cập nhiều tài nguyên hoặc phục vụ nhiều mục đích.

Một quan hệ phê duyệt nên làm rõ:

- Loại yêu cầu: truy cập JIT, checkout credential, thay đổi quyền, gia hạn hoặc thay đổi credential.
- Tài khoản hoặc loại danh tính được áp dụng.
- Tài nguyên, môi trường và phạm vi quyền.
- Điều kiện chọn tuyến phê duyệt.
- Cá nhân hoặc nhóm chịu trách nhiệm.
- Quy tắc về số quyết định, tính độc lập và thứ tự các bước.
- Thời hạn hiệu lực, cơ chế ủy quyền và xử lý khi không có người duyệt.

Ví dụ một ma trận minh họa:

| Loại yêu cầu | Phạm vi | Approval owner cần tham gia | Quy tắc minh họa |
|---|---|---|---|
| Xem log vận hành nhạy cảm | Một dịch vụ sản xuất | Nhóm chịu trách nhiệm dịch vụ | Một approver đủ điều kiện, độc lập với người yêu cầu |
| Khởi động lại dịch vụ | Dịch vụ đã xác định | Nhóm vận hành dịch vụ | Chỉ duyệt các hành động được cho phép |
| Sửa cấu hình xác thực | Hạ tầng danh tính trung tâm | Nhóm quản trị danh tính và bên kiểm soát được chỉ định | Hai quyết định độc lập theo chính sách |
| Lấy credential tài khoản dùng chung | Tài khoản và hệ thống đích cụ thể | Đơn vị chịu trách nhiệm tài khoản hoặc tài nguyên theo quy định | Gắn việc lấy credential với người dùng và phiên |
| Đổi credential tài khoản dịch vụ | Ứng dụng và các phụ thuộc đã biết | Nhóm chịu trách nhiệm dịch vụ | Xác nhận phương án cập nhật và khôi phục |
| Truy cập của nhà cung cấp | Tài nguyên theo hợp đồng | Bên bảo trợ nội bộ và đơn vị quản lý tài nguyên theo chính sách | Có thời hạn và phạm vi rõ ràng |

Bảng này là ví dụ thiết kế, không đặt ra số bước bắt buộc cho mọi tổ chức.

Hai tài khoản cùng tên trên hai môi trường có thể có approval owner khác nhau. Một nhóm có thẩm quyền ở môi trường thử nghiệm cũng không mặc nhiên được duyệt ở sản xuất.

Nếu có nhiều quy tắc khớp, cần xác định cách kết hợp: yêu cầu tất cả các bước, chọn theo mức cụ thể hoặc áp dụng ưu tiên đã định nghĩa. Không để thứ tự ngẫu nhiên của dữ liệu quyết định tuyến phê duyệt.

## 4. Mô hình dữ liệu cho approval owner

Nên phân biệt bản ghi **phân công thẩm quyền** với bản ghi **quyết định cho một yêu cầu**.

Đoạn YAML sau là mô hình minh họa, không phải cấu hình chạy trực tiếp cho một sản phẩm:

~~~yaml
approval_rule:
  rule_id: production-service-restart
  policy_version: 4
  scope:
    request_type: activate_jit_access
    environment: production
    resource_reference: service-a
    allowed_actions:
      - inspect_service_health
      - restart_service
  responsibility:
    approval_owner_type: team
    approval_owner_reference: team-service-a-operations
    responsibility_status: confirmed
    effective_from: '2026-11-01T00:00:00Z'
    review_due_at: '2026-12-01T00:00:00Z'
  decision_requirements:
    mode: one_authorized_approver
    requester_may_approve: false
    evaluate_conflicts_by_person_identity: true
    approver_authentication_required: true
  delegation:
    allowed: true
    must_remain_within_original_scope: true
    explicit_expiry_required: true
  timing:
    approval_validity_minutes: 10
    maximum_grant_duration_minutes: 15
    automatic_extension: false
  evidence:
    bind_to_request_version: true
    preserve_authority_basis: true
    preserve_decision_conditions: true
~~~

Các giá trị thời gian là giả định cho bài học, cần được lựa chọn theo nhiệm vụ và rủi ro.

Một bản ghi quyết định tương ứng cần có những trường như:

~~~text
decision_id
request_id
request_version
policy_version
approval_rule_id
approval_owner_reference
approver_identity_reference
authority_basis_reference
delegation_reference_if_any
decision: approve | deny
approved_scope
conditions
decided_at
decision_expires_at
reason_reference
~~~

Không chỉ lưu tên hiển thị của approver. Cần một định danh ổn định có phạm vi nguồn để truy vết, kể cả khi người đó đổi tên hoặc chuyển bộ phận.

Bằng chứng quyết định không được chứa mật khẩu, private key hay token của tài khoản sẽ được cấp quyền.

## 5. Điều kiện để một approver được ra quyết định

Một yêu cầu chỉ nên chấp nhận quyết định nếu đã kiểm tra các điều kiện áp dụng:

1. Chủ thể đã được xác thực theo mức yêu cầu.
2. Danh tính vẫn đủ điều kiện tham gia quy trình.
3. Có thẩm quyền trong đúng loại yêu cầu, tài nguyên và môi trường.
4. Thẩm quyền hoặc ủy quyền chưa hết hạn.
5. Không vi phạm quy tắc tách biệt nhiệm vụ.
6. Quyết định gắn với đúng phiên bản yêu cầu đang chờ.
7. Các bước phê duyệt khác được kết hợp đúng chính sách.

Tư cách thành viên nhóm cần được đánh giá theo mô hình cấp quyền đã định nghĩa. Một nhóm nhận thông báo có thể rộng hơn nhóm thực sự có quyền duyệt.

### 5.1. Kiểm tra xung đột bằng danh tính con người

Ví dụ, Lan gửi yêu cầu bằng tài khoản làm việc và mở trang duyệt bằng tài khoản quản trị. Nếu hai tài khoản liên kết với cùng Lan, đó vẫn là tự duyệt khi chính sách cấm người yêu cầu tự phê duyệt.

Tương tự, nếu một người thuộc cả nhóm vận hành và nhóm kiểm soát, hai lần bấm duyệt của người đó không đáp ứng yêu cầu “hai người độc lập”.

Khi chưa liên kết được hai tài khoản với danh tính con người đáng tin cậy, hệ thống không nên tuyên bố đã chứng minh tính độc lập chỉ vì username khác nhau. Cần ghi nhận khoảng trống và áp dụng cách xác minh phù hợp.

### 5.2. Tách biệt với người thực thi theo chính sách

Một số quy trình yêu cầu người phê duyệt khác người triển khai. Quy trình khác cho phép người quản trị phê duyệt về kỹ thuật nhưng cần thêm người chấp nhận nghiệp vụ độc lập.

Quy tắc phải được thể hiện bằng điều kiện cụ thể. Không để giao diện hiển thị “đã tách biệt nhiệm vụ” trong khi hệ thống chỉ đếm số nút duyệt hoặc số nhóm có mặt.

### 5.3. Phê duyệt tự động

Không phải mọi yêu cầu đều cần một người bấm duyệt. Có thể cho phép quyết định tự động với phạm vi hẹp và điều kiện đủ rõ.

Khi đó, cần phân biệt:

- Người hoặc nhóm chịu trách nhiệm với chính sách phê duyệt tự động.
- Danh tính hệ thống thực thi chính sách.
- Kết quả đánh giá cho từng yêu cầu.

Một bot thực hiện quyết định không trở thành người chấp nhận mọi rủi ro. Cần biết ai có thẩm quyền thay đổi chính sách, phiên bản nào đã chạy và điều kiện nào làm yêu cầu được chấp nhận.

## 6. Approver cần thấy gì trước khi duyệt?

Một yêu cầu có thể được định tuyến đúng người nhưng vẫn bị duyệt sai nếu thông tin không đủ hoặc gây hiểu nhầm.

Thông tin cốt lõi gồm:

| Nội dung | Câu hỏi cần trả lời |
|---|---|
| Người hoặc workload yêu cầu | Chủ thể thực sự sẽ sử dụng quyền là ai? |
| Tài khoản và cơ chế truy cập | Dùng tài khoản riêng, role tạm thời hay credential dùng chung? |
| Tài nguyên | Hệ thống, môi trường và phạm vi đích chính xác là gì? |
| Hành động | Được xem, sửa, khởi động lại, cấp quyền hay đọc bí mật? |
| Mục đích | Nhiệm vụ hoặc sự cố nào cần quyền này? |
| Thời gian | Khi nào được kích hoạt, quyền tồn tại bao lâu, hạn cuối là gì? |
| Mức tác động | Có dữ liệu nhạy cảm, thay đổi quyền hoặc khả năng tạo truy cập lâu dài không? |
| Kiểm soát áp dụng | Có JEA, vault, giám sát phiên và thu hồi khi hết hạn không? |
| Căn cứ công việc | Phiếu thay đổi, sự cố hoặc phê duyệt nghiệp vụ liên quan nào? |
| Điều kiện còn thiếu | Phần nào chưa được xác minh hoặc có ngoại lệ? |

Không chỉ hiển thị nhãn “quyền quản trị” nếu tập quyền thực tế rộng hơn nhiệm vụ. Chẳng hạn, “khởi động lại dịch vụ” và “được tạo tài khoản quản trị mới” là hai mức tác động khác nhau.

Thông tin nhạy cảm chỉ cần hiển thị ở mức phục vụ quyết định. Approver không cần nhìn thấy giá trị credential để quyết định có cho sử dụng tài khoản hay không.

Một lời đồng ý trong kênh trao đổi bên ngoài chỉ có thể trở thành bằng chứng phê duyệt nếu quy trình được phép sử dụng kênh đó và có cách xác thực, gắn đúng nội dung, thời điểm, phiên bản yêu cầu. Một câu “đồng ý” rời khỏi ngữ cảnh không đủ để cấp quyền tùy ý.

## 7. Ràng buộc quyết định với yêu cầu và thời gian

### 7.1. Không tái sử dụng quyết định cho nội dung đã thay đổi

Giả sử yêu cầu ban đầu xin xem log trên máy thử nghiệm trong 10 phút. Sau khi được duyệt, người yêu cầu đổi sang máy sản xuất và thêm quyền sửa cấu hình.

Quyết định cũ không được áp dụng cho yêu cầu mới. Các thuộc tính quan trọng cần được cố định trong một phiên bản yêu cầu phía máy chủ:

~~~text
request_snapshot = {
    requester_identity,
    account_or_role,
    target_resources,
    allowed_actions,
    requested_time_window,
    maximum_duration,
    purpose,
    applicable_conditions
}

decision applies only to request_id + request_version
~~~

Thay đổi các thuộc tính ảnh hưởng quyết định phải tạo phiên bản mới và đánh giá lại những bước phê duyệt liên quan theo chính sách. Không dựa vào dữ liệu giao diện có thể sửa sau khi approver đã xem.

### 7.2. Thời hạn phê duyệt khác TTL của quyền

Cần phân biệt:

- **Thời hạn chờ phê duyệt:** yêu cầu còn được xét trong bao lâu.
- **Thời hạn dùng quyết định:** trước lúc nào có thể kích hoạt dựa trên phê duyệt.
- **TTL của grant:** quyền có hiệu lực bao lâu sau khi bắt đầu.
- **Hạn cuối vận hành:** cửa sổ thay đổi hoặc điều kiện khác chặn truy cập.

Ví dụ:

- 09:00: yêu cầu được duyệt, phải kích hoạt trước 09:10.
- 09:08: kích hoạt thành công.
- TTL được duyệt tối đa 15 phút.
- Cửa sổ thay đổi kết thúc lúc 09:20.
- Grant hết hạn lúc 09:20, thay vì 09:23.

Tại 09:10, quyết định không còn dùng được để mở một lần kích hoạt mới. Grant đã kích hoạt hợp lệ trước đó có thể tiếp tục đến 09:20 theo điều kiện đã cấp. Không mặc nhiên coi hai thời hạn là một.

Nếu có nhiều bước duyệt, quyết định ở từng bước cũng phải còn hiệu lực khi kết hợp để cấp quyền. Việc bước cuối vừa hoàn tất không làm sống lại bước đầu đã quá hạn.

### 7.3. Kiểm tra lại trước khi cấp quyền

Khoảng thời gian giữa phê duyệt và kích hoạt có thể có thay đổi. Trước khi cấp grant, cần kiểm tra phiên bản yêu cầu, các quyết định bắt buộc, hạn cuối, tư cách của chủ thể và các điều kiện mà chính sách yêu cầu tại thời điểm cấp.

Nếu approver mất thẩm quyền trước khi kích hoạt, xử lý theo quy tắc đã định nghĩa, chẳng hạn yêu cầu đánh giá lại. Không tiếp tục cấp mới chỉ vì đã có một quyết định cũ mà không kiểm tra tính hợp lệ hiện tại theo chính sách.

Với grant đang hoạt động, việc approver đổi vai trò không tự động có cùng nghĩa với thu hồi grant. Cần quy định khi nào sự kiện thay đổi thẩm quyền dẫn đến rà soát hoặc thu hồi, và thực thi riêng tại điểm sử dụng quyền.

## 8. Nhóm phê duyệt, ủy quyền và chuyển tuyến

### 8.1. Nhóm cần có trách nhiệm và cơ chế vận hành

Nếu approval owner là một nhóm, inventory nên có:

- Mã nhóm ổn định và phạm vi được giao.
- Tiêu chí thành viên nào được duyệt.
- Đầu mối duy trì danh sách và xử lý khi thiếu người.
- Cách kiểm tra nhóm còn hoạt động.
- Quy tắc trực, chuyển tuyến hoặc nâng cấp quyết định.
- Lịch rà soát thẩm quyền.

Một nhóm không còn người hợp lệ phải được xem là tuyến phê duyệt không sẵn sàng. Không giải quyết bằng cách tự thêm người yêu cầu hoặc một quản trị viên bất kỳ vào vai trò duyệt.

### 8.2. Ủy quyền phải có giới hạn

Một lần ủy quyền cần chỉ rõ ai ủy quyền, ai nhận, phạm vi, thời điểm bắt đầu, thời điểm kết thúc và căn cứ cho phép.

Người nhận không được nhận quyền duyệt rộng hơn người ủy quyền có thể giao. Chính sách cũng cần quyết định có cho ủy quyền tiếp hay không.

Mã giả kiểm tra:

~~~text
delegation_is_valid =
    delegation.is_active_at(server_now)
    and requested_scope_is_inside(delegation.scope)
    and delegator_has_delegable_authority_for(request)
    and delegate_is_eligible
    and no_separation_of_duties_conflict
~~~

Ủy quyền không xóa xung đột. Nếu người nhận ủy quyền chính là người yêu cầu, quyết định vẫn phải bị từ chối khi chính sách cấm tự duyệt.

### 8.3. Chuyển tuyến không phải bỏ qua bước

Khi quá thời gian chờ, có thể chuyển tới người dự phòng có thẩm quyền hoặc nâng cấp tới đơn vị được chỉ định. Hết thời gian chờ không đồng nghĩa đồng ý.

Nếu một bước đã từ chối, không tiếp tục hỏi những người khác chỉ để tìm một người sẽ duyệt, trừ khi có quy trình xem xét lại hoặc khiếu nại hợp lệ. Khi phạm vi yêu cầu được sửa, phải tạo phiên bản và xử lý lại quyết định liên quan.

## 9. Xử lý thiếu approval owner, lỗi hệ thống và khẩn cấp

### 9.1. Không xác định được approval owner

Khi thiếu người hoặc nhóm có thẩm quyền, cần phân biệt với yêu cầu đang chờ một người hợp lệ.

Trạng thái minh họa:

~~~text
APPROVAL_ROUTE_UNRESOLVED
APPROVAL_OWNER_INACTIVE
NO_ELIGIBLE_APPROVER
APPROVAL_AUTHORITY_DATA_UNAVAILABLE
~~~

Những trạng thái này phải dẫn tới sửa mapping, xác minh dữ liệu hoặc chuyển tới đơn vị có thẩm quyền xử lý. Không tự chọn account owner, người quản trị hệ thống hay người quản lý trực tiếp làm người thay thế nếu chính sách chưa giao quyền đó.

Trong phạm vi yêu cầu bắt buộc phê duyệt, khi chưa kiểm chứng được điều kiện thì không cấp mới hoặc gia hạn quyền. Grant đã cấp xử lý theo điều kiện và TTL hiện có, không tự kéo dài vì hệ thống phê duyệt bị lỗi.

### 9.2. Truy cập khẩn cấp

Một luồng break-glass có thể có tuyến và điều kiện riêng để phục vụ ứng phó sự cố. Tuyến đó cần được thiết kế trước, có thẩm quyền, giới hạn thời gian, bằng chứng và rà soát sau sử dụng.

Không biến việc người duyệt thường trực không phản hồi thành quyền tự khai báo khẩn cấp để bỏ qua mọi kiểm soát.

Nếu cho phép một hình thức truy cập khẩn cấp không có phê duyệt trước theo chính sách, phải ghi đúng bản chất của ngoại lệ đó. Không ghi một quyết định duyệt giả hoặc coi rà soát sau sử dụng là phê duyệt đã xảy ra từ trước.

### 9.3. Quyết định từ chối và hủy yêu cầu

Từ chối cần có lý do đủ để xử lý tiếp, nhưng không nhất thiết đưa mọi thông tin nhạy cảm vào thông báo rộng.

Một yêu cầu bị hủy không được tiếp tục kích hoạt chỉ vì trang duyệt còn mở. Hệ thống phải kiểm tra trạng thái phía máy chủ khi ghi quyết định và khi cấp quyền.

## 10. Phê duyệt phải nối được với việc thực thi PAM

Một quyết định hợp lệ chỉ là một phần của chuỗi kiểm soát:

~~~mermaid
flowchart LR
    A[Yêu cầu có phiên bản] --> B[Xác định approval owner]
    B --> C[Kiểm tra thẩm quyền và xung đột]
    C --> D[Thu đủ quyết định còn hiệu lực]
    D --> E[Kiểm tra lại trước kích hoạt]
    E --> F[Cấp quyền trong phạm vi được duyệt]
    F --> G[Giám sát và kết thúc quyền]
    G --> H[Đối soát bằng chứng]
~~~

### 10.1. JIT và JEA

Nếu approver duyệt khởi động lại một dịch vụ, hệ thống không nên cấp role quản trị rộng hơn chỉ vì thuận tiện triển khai.

Thời hạn grant không được vượt giới hạn đã duyệt và cửa sổ bắt buộc. Phê duyệt gia hạn là quyết định mới theo chính sách, không phải hệ quả của việc người dùng vẫn đang thao tác.

### 10.2. Vault và credential

Phê duyệt lấy credential cần gắn với tài khoản, tài nguyên, người dùng và thời gian. Không tái sử dụng quyết định đó để lấy credential của tài khoản khác có tên gần giống.

Hết hạn grant hoặc quyền checkout không bảo đảm mọi bản sao credential đã mất hiệu lực. Cơ chế thu hồi, luân chuyển và chặn đường truy cập phải được thiết kế riêng. Approval owner cần biết mức kiểm soát thực tế khi quyết định chấp nhận yêu cầu.

### 10.3. Giám sát phiên và bằng chứng

Mã quyết định cần nối được với grant, mã tham chiếu credential nếu có, phiên và tài nguyên. Điều này giúp kiểm tra hoạt động thực tế có nằm trong phạm vi được duyệt không.

Bản ghi “đã duyệt” không chứng minh rằng điểm đích chỉ cấp đúng quyền. Cần đối soát kết quả thực thi, gồm các lỗi cấp phát, cấp vượt phạm vi hoặc phiên chưa kết thúc.

### 10.4. Thử lại và chống dùng lặp quyết định

Lời gọi cấp quyền có thể được gửi lại sau lỗi mạng. Cần có cơ chế nhận diện lần kích hoạt để thử lại không tạo thêm grant hoặc khởi động lại toàn bộ TTL.

Nếu một phê duyệt chỉ cho phép một lần kích hoạt, hệ thống phải giữ được trạng thái đã sử dụng theo cơ chế nhất quán phù hợp. Một trang duyệt hoặc thông điệp bị gửi lặp không tạo thành quyền sử dụng nhiều lần.

## 11. Ví dụ xuyên suốt: truy cập dịch vụ sản xuất

Minh cần xử lý lỗi của service-a. Quyền được yêu cầu chỉ gồm xem trạng thái và khởi động lại dịch vụ. Chính sách minh họa yêu cầu một người thuộc tuyến vận hành đã được giao thẩm quyền, độc lập với Minh.

| Thời điểm | Sự kiện | Xử lý mong đợi |
|---|---|---|
| 08:55 | Minh gửi yêu cầu phiên bản 1 cho service-a sản xuất, TTL 15 phút | Chưa cấp quyền |
| 08:56 | Hệ thống xác định tuyến của nhóm vận hành service-a | Kiểm tra tuyến và thành viên có thẩm quyền |
| 08:57 | Minh mở liên kết duyệt bằng tài khoản quản trị khác của mình | Từ chối vì cùng danh tính người yêu cầu |
| 09:00 | An, approver hợp lệ, duyệt đúng phiên bản 1 | Ghi quyết định và điều kiện, hạn dùng quyết định trước 09:10 |
| 09:02 | Minh thử thêm quyền sửa cấu hình xác thực | Không dùng phê duyệt phiên bản 1 cho phạm vi mới |
| 09:03 | Minh giữ nguyên yêu cầu phiên bản 1, không sửa nội dung đã duyệt | Chỉ phiên bản còn hợp lệ theo trạng thái máy chủ mới có thể kích hoạt |
| 09:08 | Kích hoạt phiên bản 1 thành công; cửa sổ thao tác kết thúc 09:20 | Grant kết thúc không muộn hơn 09:20 |
| 09:12 | Minh đề nghị kéo dài đến 09:40 | Tạo yêu cầu gia hạn và kiểm tra cửa sổ, thẩm quyền; chưa có quyết định thì chưa kéo dài |
| 09:20 | Đến hạn cuối của grant | Chặn truy cập theo cơ chế thực thi đã cam kết |

Trong ví dụ, thao tác thêm quyền ở 09:02 phải được hệ thống xử lý rõ: hoặc tạo yêu cầu mới tách biệt mà phiên bản 1 vẫn còn hiệu lực, hoặc thay thế phiên bản 1 và làm nó không còn dùng được. Dòng 09:03 chỉ khả thi trong trường hợp phiên bản 1 vẫn tồn tại hợp lệ. Không tự khôi phục phê duyệt sau khi yêu cầu đã bị thay thế hoặc hủy.

Nếu An rời nhóm duyệt trước 09:08, việc kích hoạt phải tuân quy tắc kiểm tra thẩm quyền hiện hành. Nếu chính sách yêu cầu xác minh lại và không còn quyết định đủ điều kiện, yêu cầu quay lại bước phê duyệt phù hợp.

Ví dụ này cho thấy tuyến đúng, người đúng, nội dung đúng và thời điểm đúng đều cần được kiểm tra. Chỉ một dấu “Approved” trên giao diện không thể đại diện cho toàn bộ chuỗi.

## 12. Duy trì approval owner trong vòng đời inventory

Các sự kiện sau nên dẫn tới đối soát:

| Thay đổi | Nội dung cần kiểm tra |
|---|---|
| Approver nghỉ hoặc chuyển vai trò | Tư cách duyệt, ủy quyền và yêu cầu đang chờ |
| Nhóm giải thể hoặc đổi chức năng | Trách nhiệm và người tiếp nhận tuyến |
| Ứng dụng chuyển đội vận hành | Mapping tài nguyên–approval owner và yêu cầu đang xử lý |
| Tài khoản có thêm quyền mạnh | Tuyến cũ có còn đủ thẩm quyền cho phạm vi mới không? |
| Thay đổi chính sách | Quy tắc áp dụng với yêu cầu cũ, quyết định chưa dùng và grant hiện có |
| Hết hạn ủy quyền | Khả năng tiếp tục ra quyết định và tuyến dự phòng |
| Kết thúc hợp đồng nhà cung cấp | Người bảo trợ nội bộ, thời hạn và truy cập còn lại |
| Nguồn dữ liệu quyền duyệt lỗi | Mức độ tin cậy của việc xác minh và hành vi khi không đủ dữ liệu |

Cần lưu phiên bản mapping và chính sách. Khi điều tra một quyết định cũ, phải biết người đó có thẩm quyền tại thời điểm quyết định, không chỉ nhìn danh sách nhóm hiện tại.

Khi chuyển approval owner, không tự chuyển mọi quyết định cũ thành quyết định của người mới. Giữ nguyên tác giả lịch sử, đồng thời xử lý các yêu cầu đang chờ hoặc quyết định chưa sử dụng theo chính sách chuyển đổi.

Không suy ra nhóm đã bị xóa chỉ vì một lần đọc API không thấy nhóm. Lỗi nguồn, thiếu quyền đọc và dữ liệu quá cũ phải được biểu diễn riêng với việc thẩm quyền đã chấm dứt.

## 13. Bằng chứng, chỉ số và tiêu chí hoàn tất

### 13.1. Bằng chứng cho một lần phê duyệt

Nên nối được:

~~~text
Phiên bản yêu cầu
  -> quy tắc định tuyến
  -> căn cứ thẩm quyền hoặc ủy quyền
  -> quyết định và điều kiện
  -> kết quả kiểm tra trước kích hoạt
  -> grant hoặc lần lấy credential
  -> phiên và thao tác liên quan
  -> kết quả kết thúc hoặc thu hồi
~~~

Giữ dấu thời gian phía hệ thống có thẩm quyền, mã định danh và lý do quyết định. Hạn chế dữ liệu cá nhân và thông tin nhạy cảm ở mức cần cho truy vết.

Quyền xem, sửa mapping, ra quyết định và đọc bằng chứng nên được quản lý theo trách nhiệm. Người có thể sửa log hoặc tự thay thẩm quyền của mình có thể làm suy yếu bằng chứng nếu không có kiểm soát phù hợp.

### 13.2. Các chỉ số hữu ích

- Số phạm vi yêu cầu đã có approval owner hợp lệ và được xác nhận.
- Số tuyến thiếu người đủ điều kiện hoặc dùng mapping quá hạn rà soát.
- Số lần chặn tự duyệt hoặc vi phạm tính độc lập.
- Số lần sử dụng ủy quyền, ngoại lệ hoặc tuyến khẩn cấp.
- Thời gian chờ theo mức rủi ro và loại nhiệm vụ.
- Tỷ lệ yêu cầu bị sửa sau khi đã có quyết định.
- Số grant không nối được với đầy đủ bằng chứng phê duyệt bắt buộc.
- Số trường hợp quyền thực tế khác phạm vi được duyệt.

Ví dụ, có 30 phạm vi phê duyệt trong danh mục: 24 phạm vi có tuyến hợp lệ, 4 cần xác minh lại và 2 chưa có tuyến. Có thể báo 24 / 30 = 80% phạm vi đã có tuyến hợp lệ theo tiêu chí đó. Không dùng tỷ lệ này để khẳng định 80% tài khoản đã được kiểm soát, vì một phạm vi có thể bao phủ nhiều tài khoản và một tài khoản có thể cần nhiều tuyến.

Thời gian chờ ngắn không tự chứng minh chất lượng quyết định tốt. Cần xem cùng mức độ đầy đủ của thông tin, ngoại lệ, xung đột và sai lệch thực thi.

### 13.3. Khi nào một mapping được coi là sẵn sàng?

Một mapping sẵn sàng khi xác định được phạm vi, đơn vị chịu trách nhiệm, cách tìm approver đủ điều kiện, quy tắc xung đột, ủy quyền, thời gian, tuyến khi không có người và cơ chế bằng chứng.

Có tên nhóm nhưng không đọc được thành viên hoặc không xác định được ai được duyệt thì chưa đủ để tuyên bố quy trình sẵn sàng cấp quyền.

## 14. Bài thực hành với các tình huống giả lập

Không cần cấp quyền hay sử dụng credential thật. Dùng một yêu cầu giả lập và các bản ghi thẩm quyền để đánh giá.

| Tình huống | Câu hỏi cần trả lời |
|---|---|
| Người yêu cầu dùng tài khoản quản trị khác để duyệt | Hai tài khoản có thuộc cùng một người và có vi phạm quy tắc không? |
| Hai bước đều yêu cầu người độc lập, nhưng cùng một người thuộc cả hai nhóm | Có đủ hai người khác nhau không? |
| Người nhận ủy quyền có phạm vi thử nghiệm, yêu cầu thuộc sản xuất | Ủy quyền có bao phủ yêu cầu không? |
| Yêu cầu đổi tài nguyên sau khi được duyệt | Quyết định có còn gắn đúng phiên bản không? |
| Nhóm duyệt không còn thành viên hợp lệ | Có tuyến dự phòng có thẩm quyền hay phải xử lý mapping? |
| Quyết định hết hạn trước khi bước duyệt cuối hoàn tất | Có thể kết hợp các quyết định đó để cấp quyền không? |
| Yêu cầu khẩn cấp vì hệ thống thường trực không phản hồi | Có đáp ứng điều kiện của luồng khẩn cấp đã được định nghĩa không? |
| Lời gọi kích hoạt được gửi lại sau lỗi mạng | Có tạo grant mới hoặc kéo dài TTL ngoài ý muốn không? |

Kết quả mong đợi:

1. Không coi hai username của cùng người là hai approver độc lập.
2. Không chấp nhận ủy quyền ngoài phạm vi.
3. Không dùng quyết định cũ cho nội dung mới.
4. Không chuyển timeout thành phê duyệt.
5. Không cấp dựa trên tổ hợp quyết định đã không còn hiệu lực.
6. Phân biệt truy cập khẩn cấp hợp lệ với việc tự bỏ qua quy trình.
7. Thử lại giữ đúng lần kích hoạt và hạn cuối đã được quyết định.

Với mỗi tình huống, ghi kết luận, dữ liệu còn thiếu và loại bằng chứng cần có. Nếu không kiểm tra được danh tính gốc hoặc thẩm quyền, ghi chưa đủ bằng chứng thay vì giả định quy trình đã đạt.

## 15. Các lỗi thiết kế thường gặp

| Lỗi | Hệ quả | Hướng xử lý |
|---|---|---|
| Account owner luôn được coi là approval owner | Duyệt vượt thẩm quyền ở tài nguyên khác | Gắn quyền duyệt với loại yêu cầu và phạm vi |
| Nhóm nhận thông báo đồng nghĩa nhóm có quyền duyệt | Người không được giao trách nhiệm vẫn ra quyết định | Tách routing thông báo và kiểm tra thẩm quyền |
| Đếm số quyết định mà không kiểm tra người thực hiện | Cùng một người đáp ứng giả nhiều bước độc lập | Đối chiếu danh tính gốc và quy tắc xung đột |
| Phê duyệt không có hạn hoặc không gắn phiên bản | Quyết định cũ bị dùng cho truy cập mới | Cố định nội dung, thời gian và trạng thái sử dụng |
| Hết thời gian chờ thì tự cấp | Biến mất người duyệt thành đường bỏ qua kiểm soát | Chuyển tuyến hợp lệ hoặc từ chối cấp mới |
| Ủy quyền không có phạm vi và hạn cuối | Thẩm quyền tồn tại ngoài dự kiến | Ghi rõ điều kiện, kiểm tra hiệu lực và rà soát |
| Có phê duyệt là coi quyền đã đúng | Hệ thống đích có thể cấp rộng hoặc giữ quá lâu | Đối soát grant, credential, phiên và kết quả thu hồi |
| Đổi approval owner làm mất lịch sử | Không giải thích được quyết định tại thời điểm cũ | Giữ phiên bản và căn cứ thẩm quyền theo thời gian |

Approval owner được quản lý tốt khi mỗi quyết định truy vết được tới một thẩm quyền hợp lệ, một nội dung cụ thể và một khoảng thời gian rõ ràng. Inventory cần giữ được quan hệ đó trong suốt vòng đời để việc cấp quyền đặc biệt có căn cứ, thực thi đúng phạm vi và có thể kiểm chứng.
