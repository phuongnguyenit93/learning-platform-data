# Separation of duties

## 1. Tách biệt nhiệm vụ giải quyết vấn đề gì trong PAM?

**Separation of duties — SoD**, hay tách biệt nhiệm vụ, là nguyên tắc phân chia những nhiệm vụ có xung đột để một chủ thể không thể tự kiểm soát toàn bộ chuỗi hành động nhạy cảm mà không có sự kiểm tra độc lập theo chính sách.

Trong quản lý quyền truy cập đặc biệt (Privileged Access Management — PAM), một chuỗi như vậy có thể gồm:

~~~text
Tạo yêu cầu
  -> phê duyệt
  -> cấp quyền
  -> sử dụng quyền
  -> ghi nhận hoạt động
  -> rà soát kết quả
~~~

Nếu cùng một người có thể tự yêu cầu, tự duyệt, cấp quyền quản trị rồi sửa hoặc xóa bằng chứng, việc chia chuỗi thành nhiều màn hình không tạo ra tách biệt thực tế.

SoD giúp giảm nguy cơ lạm dụng, sai sót không được phát hiện và việc tự xác nhận hoạt động của chính mình. Nguyên tắc này áp dụng cho quản trị viên, người phê duyệt, tài khoản dịch vụ, workload và những người có khả năng điều khiển các danh tính đó.

SoD không có nghĩa mọi nhiệm vụ phải do một người khác nhau thực hiện. Tổ chức cần xác định **cặp nhiệm vụ nào xung đột, trong phạm vi nào và ở thời điểm nào**. Quy tắc quá rộng có thể cản trở vận hành; quy tắc quá hẹp có thể để lại đường tự kiểm soát toàn bộ quy trình.

## 2. Phân biệt vai trò, nhiệm vụ và quyền kỹ thuật

Một chức danh hoặc tên role chưa đủ để đánh giá SoD.

| Khái niệm | Ý nghĩa | Ví dụ trong PAM |
|---|---|---|
| Nhiệm vụ nghiệp vụ hoặc quản trị | Kết quả mà chủ thể có thể tạo ra | Phê duyệt một lần truy cập sản xuất |
| Vai trò trách nhiệm | Đơn vị hoặc cá nhân được giao thực hiện nhiệm vụ | Approval owner của dịch vụ |
| Role kỹ thuật | Tập quyền do hệ thống định nghĩa | Role quản trị chính sách vault |
| Quyền hiệu lực | Khả năng thực tế sau khi xét gán quyền, kế thừa và điều kiện | Có thể sửa tuyến duyệt của yêu cầu mình đang gửi |
| Chủ thể hành động | Người hoặc workload thực hiện thao tác | Quản trị viên Lan hoặc bot cấp quyền |
| Chủ thể kiểm soát | Người hoặc danh tính có khả năng điều khiển chủ thể hành động | Người sửa được pipeline mà bot sẽ thực thi |

Một người không có role mang tên “approver” vẫn có thể gây xung đột nếu sửa được chính sách để tự trở thành người duyệt. Một người chỉ có quyền đọc log không giống người có quyền thay đổi thời gian lưu hoặc xóa log.

Bảng phân công trách nhiệm giúp biết ai làm gì, nhưng chưa chứng minh hệ thống đã ngăn các tổ hợp quyền xung đột. Cần nối nhiệm vụ với quyền kỹ thuật và đường điều khiển thực tế.

Ví dụ, hai nhóm có tên khác nhau vẫn có thể chứa cùng một người. Hai tài khoản đăng nhập khác nhau có thể thuộc cùng một người. Một nhóm độc lập về danh sách thành viên cũng có thể bị điều khiển bởi người có quyền sửa membership của cả hai nhóm.

## 3. Ba cách áp dụng SoD

### 3.1. Tách biệt tĩnh — Static SoD

Tách biệt tĩnh cấm một chủ thể nắm giữ đồng thời các tổ hợp quyền hoặc vai trò được xác định là xung đột trong cùng phạm vi.

Ví dụ giả định: chính sách không cho cùng một người vừa quản trị chính sách truy cập của vault sản xuất, vừa có quyền hủy bằng chứng kiểm toán của chính vault đó.

Việc đánh giá cần xét cả quyền gán trực tiếp, quyền qua nhóm và các đường nhận role được chính sách coi là liên quan. Không chỉ kiểm tra tên role trên một trang quản trị.

Ưu điểm là ngăn xung đột ngay khi thiết kế hoặc cấp quyền. Giới hạn là có thể quá cứng với nhóm vận hành nhỏ hoặc những nhiệm vụ chỉ xung đột trong một giao dịch cụ thể.

### 3.2. Tách biệt động — Dynamic SoD

Tách biệt động cho phép có một số vai trò nhưng giới hạn cách chúng được kích hoạt hoặc sử dụng cùng lúc theo ngữ cảnh.

Ví dụ, một người có thể đủ điều kiện tham gia vận hành và phê duyệt cho các yêu cầu của người khác, nhưng không được đồng thời sử dụng các vai trò xung đột trong phiên hoặc tình huống mà chính sách quy định.

Cần phân biệt quyền **đủ điều kiện kích hoạt** và quyền **đang hoạt động**. Một quy tắc xét quyền đang hoạt động không tự động có cùng ý nghĩa với quy tắc cấm nắm giữ mọi quyền đủ điều kiện.

Chỉ ngăn hai phiên đồng thời có thể chưa đủ: người dùng kết thúc phiên tạo yêu cầu rồi mở phiên duyệt vẫn có thể tự duyệt. Vì vậy, nhiều quy trình cần thêm quy tắc theo đối tượng công việc.

### 3.3. Tách biệt theo giao dịch hoặc nhiệm vụ

Loại này gắn xung đột với một yêu cầu, thay đổi hoặc đối tượng công việc cụ thể.

Ví dụ:

- Người hưởng quyền không được duyệt chính yêu cầu cấp quyền đó.
- Người sửa nội dung yêu cầu quan trọng không được đóng vai trò người kiểm tra độc lập cho phiên bản đó.
- Người thực hiện thay đổi không được là người duy nhất xác nhận độc lập rằng thay đổi đã đúng.

Quy tắc vẫn giữ hiệu lực dù các thao tác diễn ra cách nhau nhiều giờ hoặc sử dụng tài khoản khác nhau.

| Cách áp dụng | Thời điểm kiểm tra chính | Câu hỏi |
|---|---|---|
| Tĩnh | Khi gán hoặc đối soát quyền | Có tổ hợp quyền bị cấm không? |
| Động | Khi kích hoạt hoặc sử dụng vai trò | Ngữ cảnh hiện tại có cho phép tổ hợp này không? |
| Theo giao dịch | Khi chuyển bước của yêu cầu hoặc thay đổi | Người này đã làm bước xung đột trên cùng đối tượng chưa? |

Các cách trên có thể phối hợp. Không nên coi một kiểm tra duy nhất là đã bao phủ mọi dạng xung đột.

## 4. Những cặp nhiệm vụ cần xem xét trong PAM

Bảng sau là các ví dụ để xây dựng chính sách, không phải danh sách cấm bắt buộc cho mọi tổ chức:

| Nhiệm vụ thứ nhất | Nhiệm vụ có thể xung đột | Rủi ro cần đánh giá |
|---|---|---|
| Yêu cầu hoặc hưởng quyền đặc biệt | Phê duyệt chính yêu cầu đó | Tự cấp tính hợp lệ cho nhu cầu truy cập của mình |
| Sửa chính sách cấp quyền | Tự phê duyệt thay đổi chính sách do mình tạo | Mở rộng thẩm quyền mà thiếu kiểm tra độc lập |
| Quản trị quyền trên hệ thống đích | Quản trị việc xóa hoặc sửa bằng chứng hoạt động | Có thể thực hiện rồi che giấu hành động |
| Lấy credential đặc quyền | Thay điều kiện kiểm soát việc lấy credential đó | Tự nới kiểm soát trước khi sử dụng |
| Triển khai thay đổi sản xuất | Là người duy nhất rà soát độc lập thay đổi đó | Sai sót hoặc lạm dụng không có kiểm tra thực tế |
| Quản lý thành viên nhóm phê duyệt | Tự đưa mình vào tuyến duyệt cho yêu cầu đang chờ | Vượt qua kiểm tra chỉ dựa trên membership hiện tại |
| Sửa pipeline hoặc bot quản trị | Điều khiển luôn cơ chế chấp nhận kết quả của bot | Tạo một chuỗi tự động nhưng không độc lập |
| Thực hiện truy cập khẩn cấp | Tự ghi rằng đã có rà soát độc lập | Hồ sơ không phản ánh đúng người đã đánh giá |

Cần xác định phạm vi tài nguyên. Một quyền trên môi trường thử nghiệm không mặc nhiên xung đột với quyền trên một tài nguyên sản xuất hoàn toàn khác. Ngược lại, quyền trên một hệ thống điều khiển chung có thể tác động nhiều tài nguyên dù tên role chỉ nhắc một dịch vụ.

Đối với dữ liệu kiểm toán, cần phân biệt quyền xem, xuất, quản lý thời gian lưu và hủy dữ liệu. Cấm mọi người vận hành đọc log có thể làm khó điều tra mà không giải quyết đúng khả năng che giấu bằng chứng.

## 5. Đánh giá theo chủ thể thực, không chỉ theo username

### 5.1. Một người có nhiều tài khoản

Lan có tài khoản làm việc và tài khoản quản trị. Nếu Lan gửi yêu cầu bằng tài khoản thứ nhất rồi duyệt bằng tài khoản thứ hai, đó vẫn là cùng một người trong quy tắc cấm tự phê duyệt.

Cần liên kết tài khoản với định danh người dùng đủ tin cậy, có phạm vi nguồn và lịch sử thích hợp. Không chỉ so sánh chuỗi username hoặc tên hiển thị.

Không tự gộp hai tài khoản chỉ vì tên giống nhau. Tài khoản cục bộ cùng tên trên hai máy có thể thuộc hai chủ thể khác nhau. Việc liên kết sai cũng làm quy tắc SoD từ chối nhầm hoặc chấp nhận nhầm.

### 5.2. Yêu cầu thay mặt người khác

Giả sử nhân viên hỗ trợ gửi yêu cầu thay Lan. Người gửi kỹ thuật là nhân viên hỗ trợ, nhưng người hưởng quyền vẫn là Lan.

Nếu chính sách chỉ cấm người gửi bấm duyệt, Lan có thể tự duyệt quyền mình sẽ dùng. Vì vậy, cần xét các vai trò liên quan:

~~~text
Người khởi tạo yêu cầu
Người hưởng quyền
Người chỉnh sửa nội dung quan trọng
Người phê duyệt
Người thực hiện
Người rà soát độc lập
~~~

Cặp nào xung đột phải do chính sách quy định. Không mặc định tất cả đều cần khác nhau trong mọi tình huống.

### 5.3. Tài khoản dùng chung

Hai người sử dụng cùng một tài khoản làm khó việc chứng minh ai đã thực hiện bước nào. Nếu không có cơ chế gắn phiên với người thực tế, hệ thống không nên tuyên bố đã chứng minh tính độc lập chỉ từ tên tài khoản.

Có thể cần danh tính cá nhân trước khi vào PAM, cấp quyền theo phiên, bằng chứng lấy credential và giám sát tương ứng. Account owner chịu trách nhiệm vòng đời tài khoản không thay thế cho việc nhận diện người sử dụng từng lần.

## 6. Quyền gián tiếp và danh tính phi con người

### 6.1. Nhóm lồng nhau và khả năng đổi quyền

Một kiểm tra chỉ nhìn role trực tiếp dễ bỏ sót:

~~~text
Người dùng
  -> thành viên nhóm A
  -> nhóm A thuộc nhóm B
  -> nhóm B có quyền duyệt
~~~

Cũng cần xem người đó có thể sửa nhóm, thay tuyến duyệt hoặc nhận một role mạnh hơn hay không. Đây là các đường điều khiển cần đánh giá, không phải lúc nào cũng đồng nghĩa đã có quyền hiệu lực ở cuối đường.

Nếu thiếu điều kiện hoặc chính sách của một lớp, ghi nhận chưa đủ bằng chứng. Không biến một đồ thị đường ứng viên thành kết luận chắc chắn về xung đột hoặc về sự độc lập.

### 6.2. Workload và bot

Một bot cấp quyền có thể thực thi quyết định tự động hợp lệ. Nhưng việc có một tài khoản bot riêng không tự làm quyết định độc lập với người yêu cầu.

Cần hỏi:

- Ai sửa được mã hoặc cấu hình mà bot chạy?
- Ai sửa được điều kiện cho phép cấp quyền?
- Ai có thể đổi danh tính hoặc credential mà bot sử dụng?
- Có bước kiểm tra độc lập mà người yêu cầu không thể tự thay đổi không?
- Có thể nối quyết định với phiên bản chính sách đã thực thi không?

Ví dụ, một người sửa được cả pipeline triển khai và điều kiện tự duyệt pipeline đó có thể kiểm soát cả hai bước, dù bước sau được thực hiện bởi bot.

Ngược lại, một cơ chế tự động được quản trị độc lập và có điều kiện thực thi không thể bị người yêu cầu tự thay đổi có thể tạo ra kiểm soát phù hợp theo chính sách. Không nên mặc định mọi quyết định do máy thực hiện đều thiếu độc lập.

### 6.3. Quản trị nền tảng kiểm soát

Người quản trị hệ điều hành, cơ sở dữ liệu hoặc dịch vụ lưu trạng thái của PAM có thể có khả năng tác động ngoài API thông thường. Cần xem các đường quản trị nền tảng khi đánh giá khả năng vượt kiểm soát.

Một nút duyệt bị khóa ở giao diện không đủ nếu cùng người có thể sửa trực tiếp trạng thái cấp quyền hoặc hủy log mà không có kiểm soát bổ sung.

## 7. Mô hình hóa một quy tắc SoD

Một quy tắc cần đủ thông tin để giải thích cả quyết định cho phép và từ chối:

- Mục tiêu rủi ro.
- Phạm vi tài nguyên và loại nhiệm vụ.
- Chủ thể và quan hệ danh tính cần xét.
- Các hành động hoặc quyền xung đột.
- Khoảng thời gian hoặc đối tượng công việc ràng buộc xung đột.
- Cách xử lý thiếu dữ liệu.
- Ngoại lệ và thẩm quyền chấp nhận.
- Bằng chứng cần lưu.

Đoạn YAML sau là mô hình minh họa, không phải cấu hình chạy trực tiếp cho một sản phẩm:

~~~yaml
sod_policy:
  policy_id: production-privileged-access
  version: 5
  scope:
    environment: production
    resource_set_reference: protected-production-services
  rules:
    - rule_id: independent-access-approval
      type: task_based
      work_object: access_request_version
      required_decision: one_authorized_independent_approver
      approver_must_differ_from:
        - beneficiary_person
        - request_initiator_person
        - material_request_editor_person
      resolve_account_aliases: true
      preserve_decision_history: true
    - rule_id: protect-vault-audit-boundary
      type: static
      conflict_scope: same_vault_audit_boundary
      forbidden_capability_combination:
        - administer_vault_access_policy
        - destroy_vault_audit_evidence
      include_indirect_assignments: true
  uncertainty:
    mandatory_independence_check_unresolved: do_not_advance_protected_step
    record_missing_evidence: true
  exceptions:
    require_explicit_authority: true
    require_scope_and_expiry: true
    require_compensating_controls: true
  evidence:
    preserve_actor_identity_basis: true
    preserve_policy_version: true
    preserve_conflict_evaluation: true
~~~

Không nên sao chép các quy tắc trên vào mọi tổ chức. Ví dụ, chính sách có thể chọn không cấm người khởi tạo nếu đó chỉ là nhân viên hỗ trợ không hưởng quyền, nhưng vẫn cấm người hưởng quyền tự duyệt. Điều quan trọng là sự lựa chọn được giải thích và thực thi nhất quán.

Trường include_indirect_assignments thể hiện yêu cầu đánh giá; nó không chứng minh một sản phẩm đã giải được mọi đường kế thừa hoặc điều kiện.

## 8. Thực thi kiểm tra tại đúng thời điểm

### 8.1. Kiểm tra nhiều lớp

Một thiết kế đầy đủ có thể kiểm tra:

| Thời điểm | Nội dung |
|---|---|
| Thiết kế role và nhóm | Tổ hợp năng lực nào tạo xung đột? |
| Gán hoặc thay đổi quyền | Việc gán mới có tạo tổ hợp bị cấm không? |
| Tạo và sửa yêu cầu | Ai hưởng quyền, ai đã chỉnh nội dung, phạm vi là gì? |
| Ra quyết định phê duyệt | Người duyệt có thẩm quyền và độc lập không? |
| Kích hoạt hoặc cấp grant | Quyết định còn hợp lệ và ngữ cảnh có đổi không? |
| Sử dụng hoặc chuyển bước | Có quy tắc động hoặc theo giao dịch cần đánh giá lại không? |
| Đối soát định kỳ | Có quyền phát sinh hoặc đường quản trị chưa được kiểm tra không? |

Không chỉ kiểm tra trong giao diện. API, tác vụ nền và công cụ quản trị liên quan cũng phải đi qua cơ chế kiểm soát phù hợp.

### 8.2. Ràng buộc theo phiên bản

Nếu người dùng đổi tài nguyên, tập quyền hoặc người hưởng quyền sau phê duyệt, quyết định cũ có thể không còn phù hợp. Cần gắn đánh giá SoD với phiên bản yêu cầu và chính sách đã dùng.

Khi thay đổi nội dung quan trọng, đánh giá lại những bước liên quan theo chính sách. Không lấy một quyết định độc lập cho yêu cầu cũ để hợp thức hóa yêu cầu mới.

### 8.3. Tránh khoảng trống do cập nhật đồng thời

Hai lần gán role riêng lẻ có thể đều nhìn thấy trạng thái “chưa xung đột”, rồi cùng hoàn tất thành một tổ hợp bị cấm. Tương tự, yêu cầu có thể bị sửa trong lúc một quyết định được ghi nhận.

Cần cơ chế nhất quán phù hợp, chẳng hạn kiểm tra và ghi nhận trong giao dịch, so sánh phiên bản hoặc một điểm quyết định tập trung có khả năng điều phối. Khi phiên bản không còn đúng, đánh giá lại thay vì tiếp tục với kết quả cũ.

Mã giả:

~~~text
snapshot = load_authoritative_work_object_and_versions()

actors = resolve_relevant_people_workloads_and_control_relationships(
    snapshot,
    required_identity_evidence
)

evaluation = evaluate_sod(
    policy_version,
    snapshot,
    actors,
    effective_permissions,
    prior_task_history
)

if evaluation.mandatory_checks_are_unresolved:
    record_unresolved(evaluation)
    do_not_advance_protected_step()
elif evaluation.has_unaccepted_conflict:
    record_denial(evaluation)
else:
    commit_transition_if_versions_unchanged(
        expected_versions = snapshot.versions,
        decision = evaluation
    )
~~~

Đây là mô tả logic. Cơ chế thực tế phụ thuộc hệ thống, đặc biệt khi quyền và trạng thái nằm ở nhiều nguồn.

## 9. Kết hợp SoD với least privilege, JIT/JEA và vault

### 9.1. Least privilege

SoD chia nhiệm vụ; least privilege giảm khả năng của từng nhiệm vụ. Hai nguyên tắc bổ sung cho nhau.

Chia việc cho hai người nhưng mỗi người đều có quyền tự sửa toàn bộ quy trình và bằng chứng sẽ tạo kiểm soát yếu. Cần giới hạn quyền của người yêu cầu, người duyệt, bộ phận cấp quyền và người quản lý log theo trách nhiệm.

### 9.2. JIT và JEA

JIT — Just-in-Time — giới hạn thời gian có quyền; JEA — Just-Enough Access — giới hạn thao tác và tài nguyên.

TTL ngắn không xóa xung đột nhiệm vụ. Một người có thể tự duyệt và tạo hậu quả trong vài phút. Ngược lại, việc kết thúc role này rồi kích hoạt role khác cũng không làm biến mất việc người đó đã thực hiện bước xung đột trên cùng yêu cầu.

Cần giữ lịch sử nhiệm vụ vượt ra ngoài vòng đời phiên khi chính sách yêu cầu. Không chỉ đối chiếu danh sách role đang hoạt động tại một thời điểm.

### 9.3. Vault và luân chuyển credential

Có thể tách trách nhiệm quản lý chính sách vault, cho phép sử dụng credential, sử dụng credential và rà soát hoạt động. Phải kiểm tra khả năng tiếp cận bí mật trực tiếp ngoài tuyến đó.

Nếu một người không được duyệt nhưng có thể lấy credential bằng một đường quản trị khác, kiểm soát phê duyệt chưa bao phủ toàn bộ khả năng truy cập.

Luân chuyển credential cần xét phụ thuộc dịch vụ. Tách biệt giữa người chấp nhận kế hoạch và người thực hiện có thể hữu ích theo mức rủi ro, nhưng không thay thế việc kiểm tra ứng dụng đã cập nhật và credential cũ đã được xử lý tại đích.

### 9.4. Giám sát phiên và bằng chứng

Người vận hành có thể cần đọc log để xử lý sự cố. Điều cần đánh giá là họ có thể sửa, hủy hoặc vô hiệu hóa bằng chứng cho chính hoạt động của mình hay không.

Có thể dùng nơi nhận log do đơn vị khác quản lý, giới hạn quyền thay đổi cấu hình lưu trữ và đối soát nhiều nguồn. Không tuyên bố log bất biến chỉ vì nó được lưu ở một máy khác.

## 10. Kiểm soát phòng ngừa, phát hiện và biện pháp bù

| Nhóm kiểm soát | Ví dụ | Giới hạn |
|---|---|---|
| Phòng ngừa | Từ chối tự duyệt, cấm tổ hợp role, giới hạn sửa tuyến duyệt | Chỉ hiệu quả trong phạm vi đường truy cập được kiểm soát |
| Phát hiện | Cảnh báo quyền xung đột, đối soát lịch sử, rà soát phiên | Hành động có thể đã xảy ra trước khi bị phát hiện |
| Biện pháp bù | Giám sát tăng cường, quyền ngắn hạn, kiểm tra độc lập sau sử dụng | Không mặc nhiên tương đương với việc đã ngăn xung đột |

Nếu nhóm nhỏ không thể tách mọi vai trò, cần xác định xung đột nào thật sự không tránh được, ai chấp nhận rủi ro, phạm vi và thời hạn ngoại lệ.

Một ngoại lệ hữu ích cần có:

- Quy tắc được miễn hoặc điều chỉnh.
- Tài nguyên, chủ thể và loại nhiệm vụ được bao phủ.
- Lý do không thể áp dụng cách thông thường.
- Người có thẩm quyền chấp nhận, độc lập theo yêu cầu.
- Biện pháp bù và cách kiểm chứng.
- Thời điểm kết thúc hoặc điều kiện rà soát.
- Người chịu trách nhiệm khắc phục hoặc thiết kế lại.

Không dùng “đội ít người” làm ngoại lệ vô thời hạn không có người chịu trách nhiệm.

Trong truy cập khẩn cấp, chính sách có thể cho phép một tuyến đặc biệt với trách nhiệm và rà soát riêng. Phải ghi đúng bản chất nếu không có kiểm tra độc lập trước hành động; không ghi rằng quy tắc SoD đã được đáp ứng khi thực tế đang sử dụng ngoại lệ.

## 11. Ví dụ xuyên suốt: thay đổi quyền truy cập sản xuất

Lan cần quyền thực hiện một thao tác vận hành trên service-a. Chính sách yêu cầu người duyệt độc lập với người hưởng quyền và người sửa nội dung quan trọng. Việc cấp quyền do dịch vụ tự động thực hiện theo chính sách được quản trị riêng.

### 11.1. Luồng hợp lệ

~~~mermaid
flowchart LR
    A[Lan yêu cầu quyền cho nhiệm vụ cụ thể] --> B[Minh kiểm tra và duyệt trong thẩm quyền]
    B --> C[Dịch vụ cấp quyền kiểm tra phiên bản và SoD]
    C --> D[Cấp grant với JEA và hạn cuối]
    D --> E[Lan thực hiện qua tuyến được giám sát]
    E --> F[Hệ thống kết thúc quyền]
    F --> G[Người rà soát đối chiếu bằng chứng]
~~~

Sự độc lập cần được kiểm chứng tại từng bước. Nếu Lan có thể sửa chính sách mà dịch vụ cấp quyền sẽ dùng để tự chấp nhận yêu cầu, cần đánh giá đường điều khiển đó.

### 11.2. Các cách làm không đáp ứng quy tắc

| Tình huống | Vì sao không đáp ứng? |
|---|---|
| Lan dùng tài khoản quản trị khác để duyệt | Cùng người hưởng quyền |
| Nhân viên hỗ trợ gửi thay Lan, rồi Lan duyệt | Đổi người khởi tạo không đổi người hưởng quyền |
| Lan thay người hưởng quyền thành một tài khoản mình kiểm soát | Cần đánh giá liên kết danh tính và quyền điều khiển, không chỉ tên |
| Minh duyệt rồi Lan mở rộng phạm vi yêu cầu | Quyết định cũ không bao phủ phiên bản mới |
| Lan tự thêm mình vào nhóm duyệt | Tạo đường vượt phân công thẩm quyền |
| Hai bước yêu cầu hai người nhưng cùng Minh thực hiện cả hai | Hai quyết định không tạo ra hai người độc lập |
| Lan kết thúc phiên yêu cầu rồi mới mở phiên duyệt | Lịch sử nhiệm vụ trên yêu cầu vẫn còn xung đột |

### 11.3. Kiểm tra sau khi hoàn tất

Cần nối được phiên bản yêu cầu, danh tính người hưởng quyền, người duyệt, căn cứ thẩm quyền, kết quả kiểm tra SoD, grant, phiên và trạng thái kết thúc.

Nếu quyền thực tế rộng hơn nội dung được duyệt hoặc tồn tại sau hạn cuối, đó là sai lệch thực thi cần xử lý dù bước phê duyệt đã độc lập.

Nếu không đọc được liên kết giữa tài khoản quản trị và danh tính người, kết quả phù hợp là chưa đủ bằng chứng về tính độc lập. Không tự ghi đạt chỉ vì hai tài khoản khác nhau.

## 12. Bằng chứng, đối soát và chỉ số

### 12.1. Bằng chứng cho quyết định SoD

Một bản ghi nên cho biết:

~~~text
evaluation_id
policy_id_and_version
work_object_id_and_version
resource_scope
relevant_actor_references
identity_resolution_basis
effective_permission_evidence
prior_task_history_reference
applicable_conflict_rules
result: allow | deny | unresolved | allowed_exception
exception_reference_if_any
evaluated_at
enforcement_result_reference
~~~

Không ghi credential hoặc nội dung nhạy cảm không cần thiết. Cần bảo vệ dữ liệu vì nó mô tả các đường quyền lực và quan hệ danh tính quan trọng.

Giữ căn cứ tại thời điểm quyết định. Danh sách nhóm hiện tại không đủ để giải thích một quyết định cũ nếu membership hoặc chính sách đã thay đổi.

### 12.2. Đối soát định kỳ

Cần tìm:

- Tổ hợp quyền xung đột phát sinh sau thay đổi nhóm hoặc role.
- Đường quản trị trực tiếp chưa đi qua cơ chế kiểm tra.
- Yêu cầu có đủ số quyết định nhưng không đủ tính độc lập.
- Ngoại lệ hết hạn hoặc không có biện pháp bù thực tế.
- Quyền workload và người có khả năng điều khiển chúng.
- Bản ghi đánh giá thiếu kết quả thực thi hoặc thiếu nguồn danh tính.
- Khả năng cùng một chủ thể sửa cả chính sách và bằng chứng liên quan.

Lỗi thu thập không phải bằng chứng không có xung đột. Giữ trạng thái chưa đánh giá đủ cho nguồn thiếu dữ liệu.

### 12.3. Các chỉ số có ích

- Tỷ lệ phạm vi đã có quy tắc SoD và cơ chế thực thi được xác minh.
- Số xung đột đang mở theo mức tác động.
- Số lần ngăn tự duyệt hoặc tổ hợp quyền bị cấm.
- Số đánh giá chưa đủ bằng chứng danh tính hoặc quyền.
- Số ngoại lệ, thời gian tồn tại và tình trạng biện pháp bù.
- Số yêu cầu không nối được đầy đủ lịch sử nhiệm vụ.
- Số xung đột tái diễn sau khi đã khắc phục.

Ví dụ, có 50 yêu cầu trong phạm vi: 42 yêu cầu đủ dữ liệu để đánh giá, 38 đáp ứng quy tắc, 4 có vi phạm và 8 chưa đủ dữ liệu. Có thể báo 38 / 42 đáp ứng trong tập đã đánh giá đủ, đồng thời báo riêng 8 yêu cầu chưa xác định. Không coi 8 trường hợp đó là đạt.

Số lần bị chặn thấp chưa chứng minh kiểm soát tốt. Có thể quy tắc quá hẹp, không bao phủ API hoặc không liên kết được các tài khoản cùng người.

## 13. Triển khai SoD mà vẫn hỗ trợ vận hành

Một lộ trình thực tế:

1. Chọn các chuỗi hoạt động có mức tác động cao.
2. Xác định nhiệm vụ và khả năng kỹ thuật ở từng bước.
3. Thu thập danh tính, quyền trực tiếp, quyền gián tiếp và đường quản trị.
4. Viết quy tắc có phạm vi, thời gian và bằng chứng rõ.
5. Quan sát xung đột trên dữ liệu thử nghiệm hoặc phạm vi được phép.
6. Xác minh các trường hợp báo nhầm và khoảng trống dữ liệu.
7. Áp dụng cơ chế ngăn chặn phù hợp, có tuyến xử lý khi không thể đánh giá.
8. Theo dõi ngoại lệ, vận hành và thay đổi tổ chức.

Không chỉ chia lại tên role. Có thể cần giảm quyền, tách điểm quản trị, thay cách cấp credential hoặc chuyển log sang một ranh giới quản lý khác.

Với quyền đang tồn tại, việc sửa xung đột có thể ảnh hưởng dịch vụ. Cần xác định phụ thuộc, thẩm quyền thay đổi và cách khôi phục. Đặc biệt, không đổi credential hoặc xóa role hàng loạt chỉ vì báo cáo xung đột chưa được xác minh.

Các sự kiện như nhân sự chuyển vai trò, nhóm đổi chức năng, ứng dụng chuyển đội, thay pipeline hoặc đổi chính sách nên kích hoạt đánh giá lại. Kết quả SoD không phải thuộc tính cố định của một tài khoản.

## 14. Bài thực hành với tình huống giả lập

Giả định chính sách của môi trường bài tập quy định:

- Người hưởng quyền không được duyệt yêu cầu của mình.
- Yêu cầu mức tác động cao cần hai approver là hai người khác nhau.
- Người có thể sửa chính sách cấp quyền của vault không được đồng thời có khả năng hủy bằng chứng kiểm toán của cùng ranh giới đó.
- Mọi kết luận độc lập bắt buộc phải có đủ dữ liệu danh tính.

### 14.1. Phân loại tình huống

| Tình huống | Kết luận mong đợi |
|---|---|
| An gửi yêu cầu cho mình, dùng tài khoản khác để duyệt | Xung đột theo giao dịch nếu hai tài khoản thuộc cùng An |
| Bộ phận hỗ trợ gửi thay Bình, Bình là người hưởng quyền rồi tự duyệt | Xung đột, dù người khởi tạo khác người duyệt |
| Chi và Dũng là hai approver hợp lệ, không hưởng quyền và không có xung đột theo dữ liệu đầy đủ | Có thể đáp ứng yêu cầu hai người theo phạm vi đã đánh giá |
| Một người thuộc hai nhóm duyệt và thực hiện cả hai quyết định | Không đáp ứng yêu cầu hai người khác nhau |
| Một người quản trị chính sách vault sản xuất nhưng chỉ đọc log | Chưa vi phạm cặp cấm nêu trên chỉ từ quyền đọc; cần xét đầy đủ khả năng |
| Một người có quyền hủy bằng chứng qua nhóm lồng nhau, đồng thời quản trị chính sách cùng vault | Xung đột tĩnh theo quy tắc bài tập |
| Bot duyệt tự động, người yêu cầu sửa được cả điều kiện chấp nhận của bot | Có đường kiểm soát cần đánh giá; không coi bot mặc nhiên độc lập |
| Hai tài khoản khác tên nhưng không đọc được mapping danh tính | Chưa đủ bằng chứng; không kết luận đã độc lập |

### 14.2. Yêu cầu thực hiện

Với mỗi tình huống:

1. Xác định loại SoD đang áp dụng.
2. Nêu chủ thể, tài nguyên và đối tượng công việc liên quan.
3. Chỉ ra bằng chứng trực tiếp, bằng chứng còn thiếu và đường điều khiển cần xác minh.
4. Đề xuất cơ chế phòng ngừa hoặc cách xử lý.
5. Nêu điều kiện đủ để kết luận đã khắc phục.

Không cần thử khai thác hoặc cấp quyền trên hệ thống thật. Có thể làm bằng bảng quan hệ và lịch sử sự kiện giả lập.

### 14.3. Kiểm tra một cách khắc phục

Giả sử đã xóa một role trực tiếp xung đột nhưng người dùng vẫn nhận cùng khả năng qua nhóm lồng nhau. Xung đột chưa được giải quyết.

Giả sử hai người đã được chỉ định nhưng một người dùng credential chung để thực hiện cả hai quyết định, không có bằng chứng người thực tế. Việc đổi danh sách phân công chưa chứng minh quy trình đã độc lập.

Điều kiện hoàn tất cần là trạng thái quyền và hành vi thực thi đã phù hợp với quy tắc, có bằng chứng đúng phạm vi, chứ không chỉ ticket đã đóng hoặc tên role đã thay đổi.

## 15. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách cải thiện |
|---|---|---|
| Chỉ so username | Cùng người tự duyệt qua tài khoản khác | Liên kết danh tính có bằng chứng |
| Chỉ kiểm tra người gửi | Bỏ sót người hưởng quyền trong yêu cầu thay mặt | Mô hình hóa các vai trò trên đối tượng công việc |
| Chỉ đếm số quyết định | Cùng một người đáp ứng giả nhiều bước | Kiểm tra chủ thể độc lập theo chính sách |
| Chỉ kiểm tra role trực tiếp | Bỏ sót kế thừa, nhận role và quyền điều khiển | Đánh giá quyền hiệu lực và đường ứng viên liên quan |
| Kết thúc phiên là xóa lịch sử xung đột | Cho phép chuyển vai trò để tự hoàn tất chuỗi | Giữ lịch sử theo yêu cầu hoặc giao dịch |
| Bot khác tài khoản là coi độc lập | Người yêu cầu có thể điều khiển cả hai bước | Kiểm tra người và cơ chế kiểm soát bot |
| Khóa nút ở giao diện | API hoặc đường quản trị khác vẫn vượt được | Thực thi ở dịch vụ và các ranh giới liên quan |
| Thiếu dữ liệu thì mặc định đạt | Không chứng minh được tính độc lập | Ghi unresolved và xử lý theo điều kiện bắt buộc |
| Ngoại lệ không có hạn và người chịu trách nhiệm | Xung đột trở thành trạng thái thường trực | Giao thẩm quyền, thời hạn và biện pháp bù |
| Chia vai trò nhưng cùng người sửa được cả log | Có thể che giấu hoạt động | Bảo vệ bằng chứng theo ranh giới quản lý phù hợp |

Tách biệt nhiệm vụ có giá trị khi quyền thực tế, danh tính thực tế và lịch sử công việc cùng tuân theo quy tắc đã định nghĩa. Trong PAM, đó là cơ sở để quyết định cấp quyền, sử dụng credential, giám sát phiên và rà soát kết quả không bị kiểm soát trọn vẹn bởi cùng một chủ thể ngoài những ngoại lệ đã được chấp nhận rõ ràng.
