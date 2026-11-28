# Exception policy: chính sách quản lý ngoại lệ trong PAM

## 1. Ngoại lệ là gì?

Trong quản lý truy cập đặc quyền (PAM), **ngoại lệ** là một sai lệch được nhận diện rõ so với yêu cầu kiểm soát đang áp dụng, được xem xét và cho phép trong phạm vi, điều kiện và thời hạn xác định bởi chủ thể có thẩm quyền.

Một hệ thống cũ có thể chưa hỗ trợ rotation tự động. Một công việc khẩn cấp có thể cần thao tác rộng hơn vai trò JEA đã xây dựng. Một tài khoản dịch vụ có thể chưa chuyển được sang credential ngắn hạn do phụ thuộc ứng dụng. Các tình huống này cần cơ chế quản trị, thay vì chỉ ghi chú “tạm thời bỏ qua”.

**Exception policy** quy định cách đề xuất, đánh giá, quyết định, thực thi, giám sát và kết thúc các ngoại lệ đó. Chính sách giúp tổ chức biết chính xác kiểm soát nào đang bị giảm, rủi ro còn lại là gì và ai chịu trách nhiệm đưa hệ thống trở về trạng thái phù hợp.

Ví dụ:

~~~text
Yêu cầu nền:
  Credential của tài khoản dịch vụ phải được rotation tự động
  theo cơ chế và lịch đã được phê duyệt.

Ngoại lệ có phạm vi:
  Tạm dừng tác vụ rotation tự động cho đúng credential của
  svc-legacy-pay tại hệ thống payment-legacy-prod,
  trong khoảng thời gian xác định, kèm kiểm soát bù và kế hoạch sửa.

Không phải một ngoại lệ đủ rõ:
  Các hệ thống legacy được miễn PAM cho đến khi nâng cấp xong.
~~~

Ngoại lệ không tự tạo quyền quản trị cho người yêu cầu. Việc cho phép giảm một kiểm soát và việc cấp quyền thực hiện công việc là hai quyết định có liên quan nhưng cần được biểu diễn riêng.

Mục tiêu học tập:

1. Phân biệt ngoại lệ với vi phạm, thay đổi chính sách và truy cập khẩn cấp.
2. Xây dựng hồ sơ có phạm vi, rủi ro còn lại và chủ thể chịu trách nhiệm.
3. Đánh giá kiểm soát bù theo cơ chế tác động thực tế.
4. Quản lý vòng đời, thời hạn, thu hồi và gia hạn.
5. Lưu bằng chứng để phục vụ rà soát, kiểm toán và ứng phó sự cố.

## 2. Những khái niệm cần tách rõ

| Khái niệm | Ý nghĩa |
|---|---|
| Chính sách nền | Yêu cầu kiểm soát mà đối tượng phải đáp ứng |
| Ngoại lệ được chấp thuận | Phần sai lệch cụ thể đã được xem xét theo thẩm quyền |
| Sai lệch chưa được chấp thuận | Trạng thái không đáp ứng yêu cầu nhưng chưa có quyết định hợp lệ |
| Finding | Phát hiện cần phân loại, xác minh hoặc khắc phục |
| Chấp nhận rủi ro | Quyết định chấp nhận phần rủi ro còn lại trong giới hạn được giao |
| Kiểm soát bù | Biện pháp giảm một phần rủi ro phát sinh do kiểm soát nền chưa đáp ứng |
| Biện pháp khắc phục | Công việc đưa đối tượng trở lại đáp ứng yêu cầu hoặc loại bỏ nguyên nhân |
| Thay đổi chính sách | Sửa yêu cầu nền cho một phạm vi theo cơ chế quản trị riêng |

### 2.1. Finding không tự trở thành ngoại lệ

Phát hiện tài khoản chưa đưa vào vault không có nghĩa tài khoản đã được miễn yêu cầu đó. Một ticket đang mở hoặc một email “đã biết vấn đề” cũng chưa chứng minh có quyết định chấp thuận.

Hồ sơ cần thể hiện được trạng thái: mới phát hiện, đang đánh giá, bị từ chối, được duyệt có điều kiện hay đang có hiệu lực.

### 2.2. Ngoại lệ không phải thay đổi chính sách ngầm

Nếu nhiều hệ thống đều cần cùng một ngoại lệ kéo dài, có thể yêu cầu nền hoặc kiến trúc triển khai đang có vấn đề. Khi đó cần xem xét chính sách, nền tảng hoặc lộ trình đầu tư ở cấp phù hợp.

Không biến một ngoại lệ cho một tài khoản thành quy tắc chung cho mọi tài khoản cùng tên, cùng nhãn hoặc cùng đội quản lý.

### 2.3. Truy cập khẩn cấp không đồng nhất với ngoại lệ

Break-glass là cơ chế truy cập khẩn cấp đã được thiết kế cho những tình huống nhất định. Nếu dùng đúng điều kiện của chính sách nền, việc sử dụng cơ chế đó không nhất thiết là một ngoại lệ.

Nếu tình huống khẩn cấp còn yêu cầu lệch khỏi kiểm soát nền, phần sai lệch cần được quản trị theo cơ chế phù hợp. Một đường xử lý khẩn cấp có thể rút ngắn thời gian quyết định, nhưng vẫn cần chủ thể, phạm vi, thời hạn, ghi nhận hoạt động và rà soát sau sự kiện.

### 2.4. Chấp nhận rủi ro không làm rủi ro biến mất

Một quyết định hợp lệ làm rõ ai chấp nhận rủi ro và trong giới hạn nào. Nó không chứng minh hệ thống đã an toàn tương đương thiết kế chuẩn.

Báo cáo phải tiếp tục thể hiện phần kiểm soát chưa đáp ứng, kiểm soát bù và rủi ro còn lại. Không chuyển tài khoản sang nhãn “compliant” chỉ vì có một mã ngoại lệ.

## 3. Nội dung tối thiểu của exception policy

Một chính sách ngoại lệ PAM nên trả lời được:

1. Những yêu cầu kiểm soát nào có thể được xem xét ngoại lệ?
2. Những trường hợp nào nằm ngoài thẩm quyền hoặc không được cho phép?
3. Ai được đề xuất, đánh giá, chấp thuận và thực thi?
4. Hồ sơ phải có những bằng chứng gì?
5. Phạm vi và thời hạn tối đa được xác định theo cách nào?
6. Khi nào phải thu hồi sớm?
7. Cách giám sát, gia hạn và chuyển cấp khi quá hạn?
8. Điều kiện nào đủ để đóng hồ sơ?
9. Những hệ thống nào phải nhận được trạng thái ngoại lệ?
10. Ai có trách nhiệm kiểm tra việc áp dụng và khắc phục?

Không cần dùng cùng một thời hạn hay cùng số cấp phê duyệt cho mọi ngoại lệ. Có thể phân theo ảnh hưởng tài nguyên, loại đặc quyền, mức giảm kiểm soát và độ không chắc chắn của bằng chứng.

Điều quan trọng là cơ chế phân loại phải công bố rõ và không để người yêu cầu tự hạ mức rủi ro nhằm chọn người duyệt dễ hơn.

### 3.1. Ngoại lệ phải gắn với phiên bản yêu cầu nền

Nếu chỉ ghi “miễn rotation”, sau này sẽ khó biết yêu cầu nào đã được miễn và phạm vi ra sao.

Nên tham chiếu:

~~~text
control_id
policy_version
requirement_text_or_reference
deviation_description
affected_object_ids
~~~

Khi yêu cầu nền thay đổi, ngoại lệ có thể cần đánh giá lại. Không mặc định ngoại lệ cũ tiếp tục phù hợp với một chính sách mới có phạm vi hoặc ý nghĩa khác.

### 3.2. Phần còn lại của chính sách vẫn áp dụng

Nếu ngoại lệ chỉ tạm dừng rotation tự động, các yêu cầu khác như quản lý owner, hạn chế đọc credential, xác thực phù hợp, giới hạn quyền và lưu log vẫn áp dụng trừ khi có quyết định riêng rõ ràng.

Tránh một cờ chung như “PAM bypass” khiến cả chuỗi kiểm soát bị tắt. Hệ thống thực thi cần biết chính xác phần yêu cầu nào được phép thay đổi.

## 4. Phạm vi phải đủ hẹp để thực thi

Một phạm vi tốt gồm:

| Chiều phạm vi | Ví dụ |
|---|---|
| Chủ thể hoặc tài khoản | Định danh nguồn của svc-legacy-pay |
| Credential hoặc phiên bản | Credential được tham chiếu trong vault, không ghi giá trị secret |
| Tài nguyên | payment-legacy-prod hoặc tập tài nguyên đã liệt kê |
| Môi trường | Production |
| Kiểm soát bị lệch | Một yêu cầu rotation cụ thể |
| Hành động được phép thay đổi | Tạm dừng đúng tác vụ theo lịch được xác định |
| Thời gian | Có mốc bắt đầu và kết thúc tuyệt đối |
| Điều kiện | Kiểm soát bù đang hoạt động, kế hoạch sửa có owner |
| Điều kiện thu hồi | Có dấu hiệu lộ credential hoặc không còn đáp ứng điều kiện |

Dùng định danh ổn định kèm nguồn quản lý. Tên hiển thị, prefix hoặc tag có thể thay đổi và không nên là căn cứ duy nhất.

Nếu cần chọn tài nguyên theo điều kiện động, phải biết tập đối tượng có thể mở rộng tới đâu. Một ngoại lệ theo tag “legacy” có thể vô tình bao phủ tài nguyên mới khi ai đó sửa tag.

### 4.1. Phân biệt thời gian quyết định và thời gian có hiệu lực

Hồ sơ có thể được chấp thuận lúc 09:00 nhưng chỉ có hiệu lực từ 22:00, khi kiểm soát bù đã được xác minh.

Nên giữ riêng:

~~~text
requested_at
decided_at
valid_from
expires_at
activated_at
revoked_at
closed_at
~~~

Không coi một quyết định approved là đã được áp dụng thành công. Cũng không coi việc đến expires_at là bằng chứng mọi cấu hình liên quan đã trở về chuẩn.

## 5. Vai trò và thẩm quyền

### 5.1. Không để một người tự hoàn thành mọi bước

Tùy quy mô tổ chức, có thể phân vai:

| Vai trò | Trách nhiệm chính |
|---|---|
| Người đề xuất | Mô tả nhu cầu, đối tượng và lý do chưa đáp ứng yêu cầu |
| Owner của tài khoản hoặc dịch vụ | Xác nhận nhu cầu nghiệp vụ, phụ thuộc và kế hoạch khắc phục |
| Bên đánh giá kiểm soát PAM | Phân tích đường tấn công, kiểm soát bù và khả năng thực thi |
| Chủ thể chấp nhận rủi ro | Quyết định trong giới hạn thẩm quyền được giao |
| Nhóm thực thi kỹ thuật | Áp dụng đúng phần thay đổi và kiểm soát bù |
| Bên giám sát hoặc rà soát | Kiểm tra trạng thái, thời hạn, bằng chứng và ngoại lệ còn tồn tại |

Một người hoặc nhóm có thể giữ nhiều vai nếu quy định cho phép, nhưng cần xử lý xung đột lợi ích. Việc người đề xuất tự đánh giá, tự chấp nhận rủi ro và tự xác nhận hoàn tất sẽ làm giảm tính độc lập của quyết định.

Không mặc định owner kỹ thuật có thẩm quyền chấp nhận mọi rủi ro của dịch vụ. Giới hạn thẩm quyền có thể phụ thuộc mức ảnh hưởng hoặc phạm vi hệ thống.

### 5.2. Thẩm quyền phải theo đúng phạm vi

Một chủ thể có thể được phép quyết định cho một dịch vụ nhưng không cho toàn bộ production. Nếu hồ sơ bao phủ nhiều đơn vị, cần có chủ thể chịu trách nhiệm cuối cùng hoặc cơ chế phối hợp rõ ràng.

Nếu mức rủi ro vượt thẩm quyền hiện có, phải chuyển cấp theo chính sách hoặc từ chối. Không chia nhỏ hồ sơ một cách hình thức để né giới hạn quyết định trong khi thực tế các phần phụ thuộc tạo cùng một rủi ro lớn.

### 5.3. Quyền sửa hồ sơ ngoại lệ cũng cần kiểm soát

Người có thể sửa phạm vi, thời hạn hoặc điều kiện ngoại lệ có thể tác động tới việc áp dụng kiểm soát. Các trường quan trọng phải có lịch sử và không được thay đổi sau quyết định mà không để lại dấu vết.

Nếu thay đổi làm mở rộng đối tượng, quyền, thời gian hoặc giảm kiểm soát bù, đó là thay đổi cần đánh giá theo thẩm quyền. Không chỉ sửa một ô expires_at rồi giữ nguyên quyết định cũ như thể không có gì thay đổi.

## 6. Đánh giá rủi ro còn lại

### 6.1. Bắt đầu từ một kịch bản cụ thể

Mô tả “rủi ro bảo mật tăng” quá chung để quyết định. Nên chỉ ra:

~~~text
Tác nhân hoặc sự kiện
  → điểm yếu phát sinh do sai lệch
  → đường sử dụng đặc quyền
  → tài nguyên bị ảnh hưởng
  → hậu quả có thể xảy ra.
~~~

Ví dụ, credential không được rotation theo cơ chế nền có thể tiếp tục bị lạm dụng lâu hơn nếu đã bị sao chép. Ảnh hưởng phụ thuộc credential dùng được ở đâu, quyền của tài khoản rộng tới mức nào và các đường sử dụng có bị giới hạn không.

Không đồng nhất việc credential có tuổi lớn với bằng chứng đã bị lộ. Cũng không vì chưa có cảnh báo mà kết luận không có khả năng lộ lọt.

### 6.2. Những chiều cần đánh giá

- Giá trị và mức độ nhạy cảm của tài nguyên.
- Tập hành động và khả năng tạo thay đổi bền vững.
- Phạm vi credential có thể sử dụng và khả năng dùng lại ở hệ thống khác.
- Đường truy cập trực tiếp ngoài PAM hoặc đường quản trị thay thế.
- Chủ thể có thể đọc secret, sửa chính sách hoặc thay thành viên nhóm.
- Thời gian tồn tại của sai lệch.
- Khả năng phát hiện và thời gian phản ứng.
- Phụ thuộc dịch vụ và ảnh hưởng nếu kiểm soát bù thất bại.
- Chất lượng bằng chứng và phần chưa biết.

Nếu dùng điểm số hoặc nhãn rủi ro nội bộ, giữ cách tính và giả định. Không tạo độ chính xác giả bằng một con số mà không giải thích cơ sở.

### 6.3. Thiếu dữ liệu là một giới hạn của quyết định

Nếu chưa biết tài khoản có quyền kế thừa nào hoặc credential có thể dùng ngoài đường đã kiểm soát hay không, chưa đủ cơ sở gọi rủi ro còn lại là thấp.

Có thể cần thu hẹp phạm vi đề xuất, bổ sung discovery hoặc áp dụng biện pháp tạm thời rõ ràng trước khi xem xét tiếp. Bản ghi quyết định nên nêu điều gì đã xác minh và điều gì vẫn chưa biết.

### 6.4. Đánh giá cả tổ hợp ngoại lệ

Một ngoại lệ về rotation, một ngoại lệ về xác thực và một ngoại lệ về ghi nhận phiên có thể cùng tác động lên một tài khoản. Từng hồ sơ riêng lẻ có vẻ giới hạn, nhưng tổ hợp có thể tạo ra đường truy cập ít được kiểm soát.

Cần liên kết các ngoại lệ có chung chủ thể, credential, tài nguyên hoặc đường truy cập. Không đánh giá chúng như các rủi ro hoàn toàn độc lập nếu chúng làm suy yếu các lớp bảo vệ liên tiếp.

## 7. Kiểm soát bù phải gắn với cơ chế rủi ro

### 7.1. Phòng ngừa, phát hiện và ứng phó có tác dụng khác nhau

| Biện pháp | Có thể hỗ trợ | Giới hạn cần ghi nhận |
|---|---|---|
| Giới hạn nguồn mạng và đường truy cập | Giảm nơi có thể sử dụng credential | Không tự ngăn lạm dụng từ máy hoặc đường đã được cho phép |
| Thu hẹp quyền tại đích | Giảm hành động và phạm vi ảnh hưởng | Phải xét quyền gián tiếp, kế thừa và khả năng sửa chính sách |
| Giữ credential khỏi người dùng tương tác | Giảm khả năng sao chép từ luồng truy cập đó | Ứng dụng hoặc nguồn khác vẫn có thể tiếp cận credential |
| Giới hạn thời hạn grant và phiên | Giảm thời gian sử dụng một phần quyền | Không tự thu hồi credential hoặc mọi đường quyền nền |
| Theo dõi thao tác và cảnh báo | Tăng khả năng phát hiện | Không thay thế việc ngăn hành động xảy ra |
| Quy trình thu hồi có thể thực hiện | Giảm thời gian ứng phó | Phụ thuộc phát hiện, nhân sự và khả năng thực thi |
| Rotation thủ công có kiểm soát | Có thể giảm thời gian giữ nguyên credential | Có độ trễ, phụ thuộc quy trình và nguy cơ cập nhật consumer không đồng bộ |

Không ghi hình phiên như thể nó thay thế hoàn toàn xác thực mạnh. Không coi việc có vault là đã loại bỏ mọi bản sao credential ngoài vault. Mỗi biện pháp cần được đánh giá theo đường tấn công đang xét.

### 7.2. Mỗi kiểm soát bù cần tiêu chí xác nhận

Thay vì ghi “đã hạn chế network”, nên nêu:

- Nguồn nào được phép kết nối tới dịch vụ nào.
- Đường trực tiếp nào bị chặn.
- Bản cấu hình hoặc bằng chứng kiểm tra ở đâu.
- Ai chịu trách nhiệm duy trì.
- Sự kiện nào làm điều kiện không còn đáp ứng.
- Khi điều kiện thất bại thì xử lý ngoại lệ như thế nào.

Một biện pháp dự kiến triển khai chưa phải kiểm soát đang hoạt động. Nếu đó là điều kiện trước khi kích hoạt, ngoại lệ phải giữ trạng thái chờ cho tới khi có bằng chứng phù hợp.

### 7.3. Kiểm soát bù không phải lúc nào cũng đủ

Nếu không thể giới hạn đường sử dụng credential, không có bằng chứng hoạt động và không có khả năng thu hồi phù hợp, có thể không có phương án ngoại lệ chấp nhận được trong phạm vi thẩm quyền.

Khi đó, quyết định có thể là từ chối, thu hẹp chức năng, đổi cách thực hiện công việc hoặc ưu tiên khắc phục trước. Áp lực tiến độ là dữ kiện cần cân nhắc, không phải bằng chứng kiểm soát bù có hiệu quả.

## 8. Hồ sơ ngoại lệ có thể thực thi và kiểm toán

### 8.1. Các nhóm dữ liệu cần có

| Nhóm | Nội dung |
|---|---|
| Định danh | Exception ID, phiên bản, hồ sơ liên quan |
| Yêu cầu nền | Control ID, phiên bản chính sách, phần yêu cầu bị lệch |
| Phạm vi | Chủ thể, credential, tài nguyên, môi trường, thao tác |
| Nhu cầu | Lý do, phụ thuộc, lựa chọn khác đã xem xét |
| Rủi ro | Kịch bản, ảnh hưởng, phần chưa biết và rủi ro còn lại |
| Kiểm soát bù | Biện pháp, owner, bằng chứng và điều kiện hoạt động |
| Quyết định | Kết quả, chủ thể có thẩm quyền, lý do, thời điểm |
| Thời hạn | Bắt đầu, hết hạn, lịch rà soát và mốc khắc phục |
| Thực thi | Thay đổi nào đã áp dụng, ở đâu, kết quả đọc lại |
| Kết thúc | Lý do, bằng chứng khôi phục hoặc loại bỏ đối tượng, phần còn tồn tại |

Không lưu mật khẩu, token hoặc private key trong hồ sơ. Tham chiếu tới đối tượng credential được quản lý là đủ để liên kết bằng chứng khi hệ thống hỗ trợ.

### 8.2. Mẫu dữ liệu minh họa

~~~yaml
exception_id: EX-PAM-042
revision: 1
baseline:
  control_id: PAM-CR-04
  policy_version: revision-6
  requirement: automated-scheduled-credential-rotation
scope:
  account_ref: identity-prod/account-legacy-pay-18
  credential_ref: vault-prod/credential-legacy-pay-7
  resource_ref: service-prod/payment-legacy
  environment: production
deviation:
  permitted_change: suspend-one-scheduled-rotation-task
  task_ref: rotation-task-legacy-pay-7
  unrelated_controls_remain_required: true
ownership:
  service_owner_ref: payment-legacy-owners
  remediation_owner_ref: application-platform-team
decision:
  status: approved-with-conditions
  authority_ref: authorized-risk-role
  decision_record_ref: decision-204
timing:
  valid_from: '2026-11-26T17:00:00+07:00'
  expires_at: '2026-12-10T17:00:00+07:00'
  review_at: '2026-12-03T09:00:00+07:00'
activation:
  requires_verified_compensating_controls: true
  enforcement_state: pending
remediation:
  plan_ref: change-legacy-credential-refresh
  due_at: '2026-12-09T17:00:00+07:00'
~~~

Đây là mô hình hồ sơ, không phải cấu hình của sản phẩm PAM. Trường unrelated_controls_remain_required chỉ có ý nghĩa khi quy trình và điểm thực thi thật sự giữ các kiểm soát đó.

Mẫu đã có quyết định có điều kiện nhưng enforcement_state vẫn pending. Vì vậy chưa thể coi phần nới kiểm soát đã được áp dụng hoặc ngoại lệ đang hoạt động.

## 9. Vòng đời của một ngoại lệ

~~~mermaid
stateDiagram-v2
    [*] --> Requested
    Requested --> Assessing: Hồ sơ đủ để đánh giá
    Assessing --> Rejected: Không đáp ứng điều kiện
    Assessing --> ApprovedPending: Chấp thuận có điều kiện
    ApprovedPending --> Active: Đến thời điểm và xác nhận điều kiện
    ApprovedPending --> Cancelled: Hủy hoặc không còn nhu cầu
    Active --> ReviewRequired: Có thay đổi cần đánh giá lại
    ReviewRequired --> Active: Xác nhận tiếp tục trong hạn
    Active --> Revoked: Điều kiện thu hồi xảy ra
    Active --> Expired: Đến hạn
    Active --> RemediationVerification: Khắc phục trước hạn
    Revoked --> RemediationVerification: Xử lý phần còn tồn tại
    Expired --> RemediationVerification: Xử lý phần còn tồn tại
    RemediationVerification --> Closed: Đủ bằng chứng kết thúc
    Rejected --> [*]
    Cancelled --> [*]
    Closed --> [*]
~~~

Tên trạng thái có thể khác tùy hệ thống. Điều cần giữ là không đánh đồng approved, active, expired và closed.

### 9.1. Tiếp nhận và kiểm tra phạm vi

Trước khi đánh giá rủi ro, xác nhận đúng đối tượng, đúng yêu cầu nền và quyền sở hữu. Hồ sơ thiếu định danh hoặc chưa biết owner cần được bổ sung.

Nếu người đề xuất chỉ yêu cầu “miễn toàn bộ PAM”, cần phân rã thành phần yêu cầu thực tế chưa đáp ứng. Không đánh giá một phạm vi mơ hồ như thể đã có giới hạn cụ thể.

### 9.2. Đánh giá phương án thay thế

Có thể tránh hoặc giảm ngoại lệ bằng cách:

- Chạy một tác vụ tự động có đầu vào giới hạn thay cho mở shell quản trị rộng.
- Dùng tài khoản hoặc credential riêng cho công việc.
- Thu hẹp vai trò tại tài nguyên.
- Dùng cơ chế cấp quyền ngắn hạn phù hợp.
- Chuyển sang endpoint hoặc phương thức xác thực được hỗ trợ.
- Lập lịch thay đổi để consumer nhận credential mới an toàn.

Không bắt buộc mọi phương án đều khả thi. Hồ sơ nên giải thích lựa chọn nào đã xem xét, vì sao chưa dùng được và phần sai lệch tối thiểu còn cần giữ.

### 9.3. Quyết định và điều kiện kích hoạt

Quyết định có thể là từ chối, yêu cầu bổ sung hoặc chấp thuận với phạm vi và điều kiện cụ thể.

Nếu các điều kiện phải có trước khi hoạt động, bước kích hoạt cần kiểm tra bằng chứng. Ví dụ, quy tắc mạng chưa áp dụng thì chưa được tắt tác vụ rotation theo ngoại lệ.

Người thực thi không tự mở rộng phạm vi vì phát hiện thêm máy hoặc tài khoản liên quan. Phần phát sinh phải được đối chiếu với quyết định hiện có hoặc đưa qua cơ chế thay đổi phù hợp.

### 9.4. Giám sát trong thời gian có hiệu lực

Theo dõi cả trạng thái ngoại lệ lẫn tình trạng kiểm soát bù. Những sự kiện cần xem xét lại có thể gồm:

- Phạm vi quyền của tài khoản tăng.
- Tài nguyên được chuyển sang môi trường nhạy cảm hơn.
- Credential bị xuất ra ngoài luồng đã kiểm soát.
- Đường truy cập trực tiếp được mở.
- Log hoặc cảnh báo không còn hoạt động như điều kiện đã cam kết.
- Owner thay đổi hoặc kế hoạch khắc phục bị trễ.
- Có sự cố hoặc bằng chứng lạm dụng liên quan.

Không chờ tới lịch rà soát nếu đã xảy ra điều kiện thu hồi sớm.

### 9.5. Hết hạn và thu hồi sớm

Hết hạn có nghĩa không còn được dùng quyết định đó để cho phép sai lệch mới sau mốc kết thúc. Còn các tác động đã áp dụng cần được xử lý bằng cơ chế thực thi và khắc phục tương ứng.

Một ngoại lệ cho phép tạm giữ credential cũ có thể kết thúc về mặt quyết định trong khi credential vẫn chưa được thay. Trạng thái này phải được ghi là sai lệch chưa xử lý hoặc xử lý chưa hoàn tất, không được gọi là đã khôi phục chuẩn.

Chính sách cần xác định trước phương án khi không thể khắc phục đúng hạn: hạn chế chức năng, cô lập phạm vi, chuyển sang cách vận hành khác hoặc xin quyết định mới theo thẩm quyền. Không để hệ thống tự chọn gia hạn vô hạn.

## 10. Liên kết với điểm thực thi chính sách

### 10.1. Không dùng Exception ID làm một vé bỏ qua

Client gửi một mã ngoại lệ không đủ để được nới kiểm soát. Điểm thực thi phải lấy hồ sơ từ nguồn tin cậy và xác minh:

- Trạng thái có hiệu lực.
- Đúng phiên bản quyết định.
- Đúng đối tượng và phạm vi.
- Đúng phần kiểm soát được phép thay đổi.
- Thời gian còn hợp lệ.
- Điều kiện bắt buộc vẫn được đáp ứng.
- Không có trạng thái thu hồi.

Một người biết mã EX-PAM-042 không vì vậy được dùng ngoại lệ cho tài khoản hoặc tài nguyên khác.

### 10.2. Pseudocode đánh giá một sai lệch

~~~text
evaluate_control(context, control):
    baseline_result = evaluate_baseline_control(context, control)

    if baseline_result == SATISFIED:
        return SATISFIED

    exception = lookup_trusted_exception(
        context.object_references,
        control.id,
        control.policy_version
    )

    if exception does not exist:
        return DEVIATION_NOT_AUTHORIZED

    if exception.state != ACTIVE:
        return DEVIATION_NOT_AUTHORIZED

    if not scope_matches_exactly_or_by_verified_rule(context, exception):
        return DEVIATION_NOT_AUTHORIZED

    if not exception.valid_from <= trusted_now() < exception.expires_at:
        return DEVIATION_NOT_AUTHORIZED

    if exception.revoked:
        return DEVIATION_NOT_AUTHORIZED

    if not required_conditions_verified(context, exception):
        return CONDITION_NOT_MET_OR_UNKNOWN

    record_exception_application(context, control, exception)
    return DEVIATION_AUTHORIZED_FOR_THIS_CONTROL
~~~

Đây là mô hình đánh giá sai lệch, không phải bộ quyết định cấp quyền đầy đủ. Kết quả DEVIATION_AUTHORIZED_FOR_THIS_CONTROL không đồng nghĩa toàn bộ request được phép. Các kiểm tra danh tính, quyền, tài nguyên và kiểm soát khác vẫn phải được đánh giá.

Không xác minh được điều kiện không nên bị coi là điều kiện đã đạt. Cách xử lý phiên hoặc dịch vụ đang hoạt động khi điều kiện trở thành unknown cần được thiết kế theo mức rủi ro và phương án vận hành, thay vì âm thầm bỏ kiểm tra.

### 10.3. Đồng bộ, cache và độ trễ thu hồi

Nếu điểm thực thi cache ngoại lệ, việc thu hồi ở hệ thống quản trị có thể chưa có tác dụng ngay tại mọi nơi.

Cần biết thời gian cache, cơ chế làm mới, mốc hết hạn kiểm tra tại chỗ và cách xử lý khi không liên lạc được với nguồn. Một bản sao trạng thái approved không được tiếp tục cho phép sai lệch vô thời hạn khi mất kết nối.

Theo dõi độ trễ từ quyết định thu hồi tới khi các điểm thực thi ngừng áp dụng ngoại lệ. Với thay đổi cấu hình không tự hoàn tác, cần thêm tác vụ khôi phục và xác nhận kết quả.

## 11. Ví dụ xuyên suốt: tạm hoãn rotation tự động cho hệ thống cũ

### 11.1. Bối cảnh và đề xuất ban đầu

payment-legacy-prod sử dụng svc-legacy-pay. Ứng dụng giữ credential trong ngữ cảnh chạy và cần cập nhật có phối hợp để tiếp nhận phiên bản mới. Đội kỹ thuật chưa hoàn tất cơ chế cập nhật tự động an toàn.

Yêu cầu ban đầu là tạm miễn rotation cho mọi tài khoản của ứng dụng trong ba tháng. Phạm vi này chưa cho biết:

- Tài khoản và credential nào thực sự bị ảnh hưởng.
- Cơ chế rotation nào chưa đáp ứng.
- Có quyền nào vượt nhu cầu hay không.
- Có bản sao credential bên ngoài kho quản lý không.
- Những biện pháp nào giảm rủi ro trong thời gian chờ.

Sau rà soát, đề xuất được thu hẹp về đúng một account ID, một credential reference và một tác vụ rotation, từ 17:00 ngày 26/11 đến 17:00 ngày 10/12/2026 theo giờ +07:00. Các mốc này là ví dụ của tình huống.

### 11.2. Phần yêu cầu được phép thay đổi

Ngoại lệ chỉ cho phép tạm dừng tác vụ rotation tự động đã chỉ định. Nó không cho phép:

- Cấp thêm quyền cho svc-legacy-pay.
- Phát credential cho người dùng tương tác ngoài chính sách.
- Mở đường truy cập trực tiếp mới.
- Tắt log hoặc bỏ trách nhiệm của owner.
- Bỏ xử lý khi có dấu hiệu credential bị lộ.

Việc rotation thủ công vẫn được thực hiện theo kế hoạch phối hợp và khi tình huống rủi ro yêu cầu. Khả năng thực hiện phải được xác minh, không chỉ viết thành lời cam kết.

### 11.3. Kiểm soát bù và bằng chứng

| Kiểm soát | Bằng chứng mong đợi | Rủi ro còn lại |
|---|---|---|
| Chỉ workload được xác định dùng credential qua đường cho phép | Cấu hình và kiểm tra các đường liên quan | Workload hoặc máy được cho phép vẫn có thể bị xâm phạm |
| Thu hẹp quyền tài khoản tại đích | Bản gán quyền và đánh giá phạm vi hành động | Quyền cần thiết vẫn có thể gây tác động nếu bị lạm dụng |
| Hạn chế đọc hoặc xuất secret | Chính sách vault và log sử dụng liên quan | Bản sao trước đó hoặc trong bộ nhớ ứng dụng cần được xem xét |
| Theo dõi sử dụng bất thường | Quy tắc cảnh báo, người tiếp nhận và bằng chứng hoạt động | Phát hiện có độ trễ, không ngăn mọi hành động |
| Kế hoạch rotation thủ công có thể thực hiện | Các bước cập nhật consumer và xác nhận kết quả | Có phụ thuộc vận hành và khả năng gián đoạn |
| Kế hoạch sửa cơ chế cập nhật | Công việc, owner và mốc hoàn thành | Tiến độ có thể thay đổi, cần giám sát |

### 11.4. Điều kiện thu hồi sớm

Trong tình huống này, các điều kiện đã thống nhất có thể gồm:

- Có bằng chứng hoặc nghi ngờ đáng kể về lộ credential.
- Quyền tài khoản được mở rộng ngoài phạm vi đã đánh giá.
- Xuất hiện đường truy cập ngoài đường đã kiểm soát.
- Kiểm soát bù quan trọng không còn hoạt động.
- Dịch vụ được di chuyển sang phạm vi khác mà chưa đánh giá lại.

Thu hồi sớm phải đi cùng phương án xử lý kỹ thuật và vận hành. Thay một trạng thái trong hồ sơ không tự rotation credential, đóng phiên hoặc chặn các đường sử dụng.

### 11.5. Kết thúc tình huống

Nếu cơ chế mới đã được triển khai, cần xác minh credential được cập nhật đúng tới consumer, tác vụ rotation hoạt động theo yêu cầu và không còn cấu hình tạm gây sai lệch.

Chỉ sau khi có bằng chứng phù hợp mới đóng hồ sơ với lý do đã khắc phục. Nếu dịch vụ bị loại bỏ, cần xác minh tài khoản, credential và các quyền liên quan đã được xử lý, thay vì đóng chỉ dựa trên thông báo “đã decommission”.

## 12. Gia hạn, thay đổi và xử lý quá hạn

### 12.1. Gia hạn là một quyết định mới về thời gian rủi ro

Hồ sơ gia hạn nên có:

1. Kết quả thực hiện kế hoạch khắc phục trước đó.
2. Lý do chưa hoàn thành và bằng chứng phụ thuộc còn tồn tại.
3. Thay đổi về tài khoản, quyền, tài nguyên hoặc môi trường.
4. Tình trạng kiểm soát bù và các sự kiện đã xảy ra.
5. Rủi ro còn lại được đánh giá lại.
6. Thời hạn mới, mốc khắc phục và chủ thể có thẩm quyền.

Không lấy lý do “ngoại lệ đã được duyệt trước đây” làm căn cứ đủ cho việc kéo dài. Thời gian tiếp xúc rủi ro dài hơn và những thay đổi tích lũy có thể làm kết luận cũ không còn phù hợp.

Một ngoại lệ được gia hạn nhiều lần nên được chuyển tới cấp quản trị phù hợp để xem xét nguyên nhân, nguồn lực khắc phục hoặc thiết kế thay thế.

### 12.2. Thay đổi ngoài phạm vi không được che bằng hồ sơ cũ

Nếu cần thêm tài khoản, tài nguyên hoặc bỏ một kiểm soát bù, phải ghi thay đổi và đánh giá tác động. Có thể tạo phiên bản mới hoặc hồ sơ liên quan theo mô hình hệ thống, nhưng phải tái hiện được quyết định nào áp dụng cho khoảng thời gian nào.

Không sửa lùi valid_from để biến một khoảng sai lệch chưa được phép thành khoảng đã được chấp thuận. Quyết định sau sự kiện cần giữ đúng thời điểm và phân biệt với thẩm quyền đã có trước đó.

### 12.3. Khi ngoại lệ đã hết mà khắc phục chưa xong

Tách ít nhất ba trạng thái:

~~~text
Decision state:
  Ngoại lệ đã hết hiệu lực.

Technical state:
  Sai lệch tại hệ thống có thể vẫn còn.

Governance state:
  Cần xử lý quá hạn, chuyển cấp hoặc quyết định tiếp theo.
~~~

Không đổi expires_at tự động chỉ để tránh cảnh báo đỏ. Cũng không xóa hồ sơ khi hết hạn, vì đó là bằng chứng quan trọng để theo dõi khoảng sai lệch chưa xử lý.

Các bước tiếp theo phải theo phương án đã thiết kế: giới hạn công việc mới, áp dụng kiểm soát thay thế có thẩm quyền, khắc phục hoặc xử lý tiếp diễn theo mức rủi ro. Nếu có quyết định mới, giữ rõ khoảng thời gian trước quyết định và trạng thái của nó.

### 12.4. Ngoại lệ khẩn cấp

Chính sách có thể có đường quyết định khẩn cấp với chủ thể trực ca hoặc cơ chế ủy quyền đã định trước. Hồ sơ cần ghi lý do không thể dùng luồng thông thường, phạm vi ngắn gọn và thời hạn rõ ràng.

Sau sự kiện, rà soát hoạt động, thu hồi phần quyền tạm, xử lý credential đã bị tiết lộ nếu có và đánh giá lại nguyên nhân. Rà soát sau sự kiện không tự biến mọi hành động trước đó thành đã có thẩm quyền; phải giữ đúng căn cứ thực tế.

Không dùng tính khẩn cấp để thiết lập một đường bỏ kiểm soát thường trực mà không có owner hoặc mốc kết thúc.

## 13. Bằng chứng và khả năng kiểm toán

### 13.1. Một chuỗi bằng chứng đầy đủ

~~~text
Yêu cầu nền và phiên bản
  → sai lệch được mô tả
  → đánh giá rủi ro và lựa chọn thay thế
  → quyết định theo thẩm quyền
  → kiểm soát bù được xác nhận
  → thay đổi thực thi và trạng thái hoạt động
  → sự kiện sử dụng hoặc giám sát
  → thu hồi, hết hạn hoặc khắc phục
  → xác nhận kết thúc trong phạm vi đã nêu.
~~~

Mỗi bước cần định danh và thời điểm để liên kết. Nếu một nhóm đóng vai trò quyết định, cần biết chủ thể thực hiện và căn cứ đại diện hoặc ủy quyền tại thời điểm đó.

Danh sách thành viên hiện tại không đủ để chứng minh một người có thẩm quyền vào thời điểm quá khứ. Giữ tham chiếu lịch sử phù hợp với cơ chế quản trị.

### 13.2. Bằng chứng thực thi khác bằng chứng quyết định

Một ticket approved chứng minh có quyết định được ghi nhận. Nó chưa chứng minh quy tắc mạng, tác vụ rotation hay chính sách vault đã đổi đúng.

Có thể cần:

- Bản ghi thay đổi cấu hình.
- Kết quả đọc lại từ nguồn có thẩm quyền.
- Kiểm tra phạm vi được áp dụng.
- Sự kiện từ điểm thực thi.
- Bằng chứng kiểm soát bù hoạt động.
- Kết quả xác minh sau khắc phục.

Một phản hồi API thành công cũng cần được hiểu đúng: đã nhận yêu cầu, đã áp dụng hay đã hoàn tất xác minh. Không dùng các mức đó thay nhau.

### 13.3. Bảo vệ dữ liệu ngoại lệ

Hồ sơ có thể chứa thông tin về điểm yếu, quyền quản trị, đường truy cập và thời điểm giảm kiểm soát. Cần giới hạn người xem, người sửa và hoạt động xuất dữ liệu.

Giữ lịch sử thay đổi và bảo vệ bằng chứng theo yêu cầu của tổ chức. Không lưu giá trị secret trong mô tả, bình luận hoặc ảnh chụp kèm theo.

Khi hết thời hạn ngoại lệ, việc lưu bằng chứng vẫn theo chính sách lưu trữ riêng. Hết hiệu lực quyết định không có nghĩa hồ sơ được xóa ngay.

## 14. Tiêu chí đóng ngoại lệ

Một hồ sơ có thể kết thúc theo những lý do khác nhau, nhưng phải giữ rõ lý do và bằng chứng.

| Lý do kết thúc | Điều cần xác minh |
|---|---|
| Đã khắc phục | Yêu cầu nền đã được đáp ứng và cấu hình tạm đã được xử lý |
| Đã loại bỏ đối tượng | Tài khoản, credential, quyền, consumer và tài nguyên liên quan đã được xử lý trong phạm vi tuyên bố |
| Đã thay bằng thiết kế được chấp thuận | Thiết kế và chính sách mới có hiệu lực, tác động chuyển đổi đã được xác minh |
| Bị từ chối hoặc hủy trước kích hoạt | Phần nới kiểm soát chưa được áp dụng, hoặc đã được xử lý nếu có thay đổi trước đó |
| Đã chuyển sang hồ sơ khác | Có liên kết và phạm vi trách nhiệm rõ ràng; không che giấu phần sai lệch vẫn tồn tại |

Chuyển hồ sơ không tự chứng minh khắc phục. Nếu sai lệch còn tồn tại dưới một quyết định mới, báo cáo cần thể hiện liên tục lịch sử và trạng thái kiểm soát.

Trước khi đóng, kiểm tra:

1. Đúng đối tượng và phạm vi của ngoại lệ.
2. Điều kiện kết thúc đã thực sự xảy ra.
3. Những thay đổi tạm được khôi phục hoặc thay thế có chủ đích.
4. Các đường quyền, credential, grant và phiên liên quan đã được xem xét.
5. Bằng chứng còn thiếu đã được ghi và xử lý theo quy định.
6. Owner và bên có trách nhiệm đã xác nhận trong phạm vi thẩm quyền.

Không đóng chỉ vì hết ngày, đạt một mốc dự án hoặc người thực hiện nói “đã xong” mà chưa có bằng chứng phù hợp.

## 15. Chỉ số quản trị hữu ích

| Chỉ số | Ý nghĩa |
|---|---|
| Số ngoại lệ đang có hiệu lực theo loại kiểm soát | Nhìn thấy phần kiểm soát đang được giảm |
| Số ngoại lệ hết hạn nhưng sai lệch chưa xử lý | Theo dõi khoảng trống tiếp diễn |
| Tỷ lệ hồ sơ có đủ owner, thời hạn và bằng chứng kiểm soát bù | Đánh giá chất lượng quản trị |
| Số lần gia hạn và tổng thời gian tồn tại | Phát hiện ngoại lệ kéo dài |
| Thời gian từ thu hồi tới ngừng áp dụng tại điểm thực thi | Đánh giá hiệu quả truyền trạng thái |
| Tỷ lệ đóng có bằng chứng khắc phục phù hợp | Phân biệt xử lý thực chất và đóng hành chính |
| Số tổ hợp ngoại lệ cùng tác động một đường đặc quyền | Đánh giá rủi ro tích lũy |
| Số thay đổi phạm vi không khớp quyết định | Theo dõi việc áp dụng vượt giới hạn |

Không đánh giá chương trình chỉ bằng mục tiêu giảm số lượng hồ sơ. Xóa hoặc gộp hồ sơ có thể làm con số đẹp hơn mà không giảm rủi ro.

Cũng không tính mọi đối tượng có ngoại lệ là đã đáp ứng toàn bộ chính sách. Nên phân biệt đáp ứng chuẩn, sai lệch được chấp thuận, sai lệch chưa được chấp thuận và chưa đủ dữ liệu.

## 16. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Phạm vi “mọi hệ thống legacy” | Bao phủ đối tượng chưa được đánh giá | Dùng định danh, loại sai lệch và điều kiện rõ ràng |
| Chỉ ghi một người biết vấn đề | Không có quyết định theo thẩm quyền | Giữ chủ thể, căn cứ và kết quả quyết định |
| Approved được hiểu là active | Nới kiểm soát trước khi đủ điều kiện | Tách quyết định và kích hoạt |
| Dùng Exception ID từ client làm bằng chứng | Có thể áp dụng nhầm hoặc lạm dụng | Tra cứu nguồn tin cậy và kiểm tra toàn bộ phạm vi |
| Ghi hình được coi là thay thế mọi kiểm soát | Nhầm phát hiện với phòng ngừa | Đánh giá tác dụng và rủi ro còn lại |
| Gia hạn tự động khi trễ kế hoạch | Ngoại lệ trở thành quyền thường trực | Đánh giá lại và chuyển cấp khi cần |
| Hết hạn là coi đã khắc phục | Sai lệch thực tế vẫn tồn tại | Theo dõi thực thi và xác nhận kết thúc |
| Mỗi ngoại lệ được xem độc lập | Bỏ sót tổ hợp làm suy yếu nhiều lớp | Liên kết theo đường truy cập và đối tượng |
| Sửa lịch sử để phủ khoảng chưa được phép | Mất tính trung thực của bằng chứng | Giữ đúng thời điểm sự kiện và quyết định |
| Đóng bằng một thông báo hoàn tất | Không chứng minh trạng thái tại nguồn | Đọc lại và xác minh trong phạm vi tuyên bố |

## 17. Bài tập áp dụng

Một đội vận hành đề xuất:

~~~text
Trong hai tháng, mọi quản trị viên của cụm production
được dùng tài khoản chung qua đường trực tiếp.
Lý do: cổng PAM hiện chưa hỗ trợ một số thao tác.
Đội đề xuất sẽ lưu ảnh chụp kết quả công việc.
Chưa xác định đầy đủ các thao tác bị thiếu.
~~~

Hãy phân tích:

1. Những yêu cầu nền nào có thể đang bị lệch?
2. Vì sao phạm vi chưa đủ rõ để quyết định?
3. Ảnh chụp kết quả giảm được rủi ro nào và không giải quyết được điều gì?
4. Có thể thay bằng tác vụ giới hạn hoặc chỉ mở một đường công việc cụ thể không?
5. Cần ai đánh giá và ai có thẩm quyền chấp nhận rủi ro?
6. Những điều kiện kích hoạt, thu hồi và kết thúc nào cần có?

Hướng phân tích:

- Có thể liên quan tới định danh cá nhân, kiểm soát đường truy cập, quản lý credential, giới hạn thao tác và bằng chứng phiên; phải đối chiếu yêu cầu nền thật.
- “Mọi quản trị viên”, “cụm production” và “một số thao tác” chưa xác định đủ chủ thể, tài nguyên hoặc năng lực cần thiết.
- Ảnh chụp kết quả có thể hỗ trợ ghi nhận một phần công việc, nhưng không chứng minh toàn bộ hành động, không ngăn lạm dụng và không tự giải quyết quy trách nhiệm của tài khoản chung.
- Nên xác định thao tác còn thiếu, đánh giá cách đóng gói tác vụ hoặc cấp quyền hẹp trước khi xem xét đường truy cập rộng.
- Nếu không có phương án kiểm soát bù và thu hồi phù hợp trong thẩm quyền, quyết định có thể là từ chối hoặc yêu cầu thay cách thực hiện.
- Mọi thời hạn và điều kiện phải gắn với cơ chế thực thi, owner và bằng chứng xác nhận.

## 18. Ghi nhớ

Exception policy giúp quản lý một phần sai lệch PAM bằng phạm vi rõ ràng, quyết định đúng thẩm quyền, kiểm soát bù có bằng chứng và mốc kết thúc có thể thực thi.

Một ngoại lệ có giá trị phải chỉ ra điều gì được phép khác chuẩn, rủi ro nào vẫn còn, ai chịu trách nhiệm và bằng chứng nào đủ để kết thúc. Quyết định được duyệt, ngoại lệ đang hoạt động, thời hạn đã qua và hệ thống đã khắc phục là những trạng thái cần được quản lý riêng.
