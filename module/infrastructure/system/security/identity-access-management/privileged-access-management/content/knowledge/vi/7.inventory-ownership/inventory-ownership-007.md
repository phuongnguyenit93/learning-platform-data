# Allowed use case

Trong chương **Inventory và ownership**, allowed use case là trường hợp sử dụng được phép của một danh tính, tài khoản, credential hoặc quyền đặc biệt. Nó mô tả **công việc nào được làm, bởi ai, trên tài nguyên nào và dưới những điều kiện gì**, đồng thời chỉ rõ đơn vị chịu trách nhiệm xác nhận nhu cầu đó.

Trong quản lý truy cập đặc quyền (PAM), thông tin này kết nối nhu cầu nghiệp vụ với kiểm kê quyền, đặc quyền tối thiểu, JIT/JEA, vault, luân chuyển credential và bằng chứng sử dụng. Một tài khoản có quyền kỹ thuật rộng không có nghĩa mọi công việc mà nó làm được đều được tổ chức cho phép.

Bài học dùng allowed use case theo nghĩa mô hình quản trị. Tên trường, trạng thái và ví dụ không phải một chuẩn dữ liệu hay cấu hình riêng của sản phẩm PAM nào.

## 1. Kết quả cần đạt

Sau bài học, người học có thể:

- Viết một allowed use case đủ cụ thể để owner xem xét và người vận hành áp dụng.
- Phân biệt mục đích được phép, quyền kỹ thuật, phê duyệt từng yêu cầu và grant thực tế.
- Liên kết use case với danh tính, credential, system scope, consumer và trách nhiệm.
- Chuyển các điều kiện có thể kiểm tra thành kiểm soát khi cấp quyền và thực thi.
- Xử lý yêu cầu ngoài mục đích, ngoại lệ, thay đổi phiên bản và ngừng sử dụng.
- Đánh giá bằng chứng để phân biệt sử dụng phù hợp, vi phạm đã xác minh và phần chưa đủ dữ liệu.

## 2. Vì sao inventory cần ghi mục đích sử dụng được phép?

Một inventory chỉ ghi `svc-admin` là tài khoản quản trị và mật khẩu nằm trong vault vẫn chưa giải thích được tài khoản đó dùng để làm gì. Khi có yêu cầu sử dụng, người duyệt khó biết thao tác đề nghị có phù hợp với mục đích ban đầu hay không.

Allowed use case tạo căn cứ cho các câu hỏi:

- Tài khoản này phục vụ vận hành, triển khai, sao lưu, khôi phục hay truy cập khẩn cấp?
- Nó dành cho workload tự động, con người hoặc một broker thực thi thay?
- Những tài nguyên và thao tác nào thực sự cần cho công việc?
- Có được xem hoặc xuất giá trị credential không?
- Điều kiện nào phải có trước khi cấp quyền hoặc thực hiện thao tác?
- Ai chịu trách nhiệm xác nhận nhu cầu, rà soát thay đổi và xử lý khi dùng sai?

Ví dụ, tài khoản backup có thể cần đọc dữ liệu để tạo bản sao. Điều đó không tự cho phép dùng nó để truy vấn dữ liệu khách hàng cho một báo cáo tùy ý, mở console quản trị hoặc khôi phục dữ liệu production sang development.

Thông tin mục đích cũng giúp phát hiện quyền vượt nhu cầu. Nếu use case chỉ yêu cầu xem trạng thái và restart một dịch vụ, nhưng danh tính có thể sửa mọi dịch vụ trên máy, quyền kỹ thuật còn rộng hơn nhu cầu đã được xác nhận.

## 3. Phân biệt bốn lớp quyết định

| Lớp | Câu hỏi | Ví dụ |
|---|---|---|
| Allowed use case | Loại công việc nào được tổ chức cho phép trong điều kiện xác định? | Restart hai service instance khi xử lý sự cố production |
| Quyền kỹ thuật | Danh tính có khả năng thực hiện những thao tác nào? | Tài khoản có quyền quản trị toàn máy |
| Phê duyệt yêu cầu cụ thể | Lần sử dụng này có đủ điều kiện và được chấp thuận không? | Duyệt yêu cầu gắn với sự cố INC-2092 |
| Grant và thực thi | Quyền nào thực sự được cấp, trong bao lâu, và đã làm gì? | Grant 20 phút, broker thực hiện restart đúng instance |

Allowed use case đã được chấp thuận không tự thay thế phê duyệt từng lần nếu chính sách vẫn yêu cầu bước đó. Ngược lại, một người bấm duyệt yêu cầu không nên tự mở rộng mục đích đã được phép nếu người đó không có thẩm quyền thay đổi chính sách hoặc use case.

Một dòng mô tả trong inventory cũng không tự cưỡng chế hành vi. Nếu người dùng được nhận mật khẩu admin toàn máy, câu “chỉ dùng để restart dịch vụ” chưa ngăn họ dùng mật khẩu cho thao tác khác. Cần kiểm soát tương ứng ở lớp cấp quyền, broker hoặc hệ thống đích.

### Mục đích, thao tác và kết quả mong đợi

Ba nội dung nên được ghi riêng:

```text
Mục đích: Khôi phục xử lý đơn hàng bị treo trong một sự cố.
Thao tác: Xem trạng thái và restart service instance đã chọn.
Kết quả mong đợi: Instance hoạt động trở lại, có bằng chứng kiểm tra sau thao tác.
```

Một kết quả mong muốn không tự cho phép mọi cách đạt kết quả đó. “Khôi phục dịch vụ” không mặc nhiên cho phép reboot toàn máy, sửa mã nguồn, tắt giám sát hoặc đọc secret của ứng dụng khác.

## 4. Viết allowed use case đủ cụ thể

### 4.1. Các thành phần tối thiểu

| Thành phần | Nội dung cần ghi |
|---|---|
| Định danh và phiên bản | Use case ID, phiên bản, trạng thái và thời gian hiệu lực |
| Nhu cầu nghiệp vụ | Công việc hợp lệ và lý do cần đặc quyền |
| Chủ thể sử dụng | Người, nhóm đủ điều kiện hoặc workload có định danh xác minh được |
| Danh tính thực thi | Tài khoản đích, vai trò hoặc danh tính broker thực sự dùng quyền |
| Tài nguyên | System scope và tập đích cụ thể hoặc quy tắc chọn được kiểm soát |
| Thao tác | Hành động được phép ở mức đủ dùng |
| Điều kiện | Mã công việc, môi trường, kênh, thời gian, xác thực và phê duyệt cần thiết |
| Xử lý credential | Có cấp secret trực tiếp không, dùng qua broker hay cấp credential ngắn hạn |
| Bằng chứng | Dữ liệu cần để đối chiếu yêu cầu, grant và hoạt động thực tế |
| Ownership | Đầu mối xác nhận nhu cầu, vận hành, credential và rà soát |
| Vòng đời | Mốc xem lại, điều kiện tạm dừng, thay thế hoặc ngừng use case |

Không cần nhồi mọi chi tiết triển khai vào một ô văn bản. Có thể chia thành bản ghi use case và các quan hệ tới inventory, chính sách hoặc runbook được quản lý phiên bản. Điều quan trọng là người kiểm tra có thể truy tới đúng nội dung đang áp dụng.

### 4.2. So sánh mô tả yếu và mô tả có thể kiểm tra

| Mô tả quá rộng | Cách viết rõ hơn |
|---|---|
| Quản trị production | Xem trạng thái và restart hai service instance orders qua broker khi có sự cố thuộc hệ thống này |
| Dùng cho automation | Workload backup đã định danh được đọc đối tượng dữ liệu đã chọn trong lịch chạy được quản lý |
| Hỗ trợ kỹ thuật | Nhân sự nhà cung cấp đã được xác nhận được xem chẩn đoán trên tài nguyên chỉ định trong cửa sổ hỗ trợ |
| Xử lý khẩn cấp | Vai trò ứng cứu sử dụng luồng khẩn cấp theo điều kiện kích hoạt, thời hạn và bằng chứng riêng |
| Dùng khi cần | Nêu điều kiện phát sinh công việc, người có thẩm quyền và giới hạn trước khi sử dụng |

Không dùng `maintenance`, `admin` hoặc `support` như cách bao phủ mọi thao tác chưa nghĩ đến. Nếu một công việc mới xuất hiện, cần đánh giá và bổ sung có kiểm soát.

## 5. Gắn use case với inventory và ownership

### 5.1. Quan hệ không nhất thiết một–một

Một danh tính có thể phục vụ nhiều use case, và một use case có thể sử dụng nhiều danh tính ở các bước khác nhau. Tuy nhiên, việc dùng chung danh tính làm phạm vi quyền và trách nhiệm khó tách hơn.

Ví dụ:

```text
Use case restart dịch vụ
    → kỹ sư trực ca được xác thực riêng
    → broker thực thi bằng danh tính vận hành có giới hạn
    → service instance đã được duyệt

Use case workload chạy nghiệp vụ
    → danh tính workload
    → credential truy cập database
    → database orders
```

Kỹ sư cần restart dịch vụ không vì thế được phép đọc credential database của workload. Hai use case liên quan cùng một hệ thống nhưng khác chủ thể, quyền và cách xử lý secret.

Nếu một tài khoản vẫn phải phục vụ nhiều công việc, inventory cần thể hiện từng use case và tập quyền hợp nhất thực sự của tài khoản. Không đánh giá từng use case hẹp rồi bỏ qua việc danh tính thực tế có tổng quyền rộng hơn.

### 5.2. Các trách nhiệm cần làm rõ

| Vai trò | Trách nhiệm điển hình |
|---|---|
| Chủ sở hữu hệ thống/nghiệp vụ | Xác nhận mục đích có còn cần thiết và tác động chấp nhận được |
| Chủ sở hữu kỹ thuật | Xác định tài nguyên, thao tác tối thiểu, phụ thuộc và cách kiểm tra kết quả |
| Chủ sở hữu danh tính dịch vụ | Xác nhận consumer và việc danh tính có được dùng cho mục đích đó không |
| Đơn vị quản lý credential | Xác nhận phương thức cấp phát, luân chuyển và thu hồi phù hợp |
| Đơn vị vận hành PAM | Thực thi kiểm soát và cung cấp bằng chứng theo thẩm quyền |
| Người/cơ chế duyệt từng yêu cầu | Đánh giá lần sử dụng cụ thể theo chính sách hiện hành |

Người tạo tài khoản không tự trở thành owner hợp lệ. Owner được ghi trong inventory cũng không mặc nhiên có quyền bỏ qua phê duyệt, đọc secret hoặc sửa chính sách.

Với nhóm chịu trách nhiệm, cần đầu mối và cơ chế bàn giao khi thành viên hoặc đội vận hành thay đổi. Use case không nên tiếp tục được coi là đã rà soát chỉ vì trường owner còn chứa một tên nhóm không còn hoạt động.

## 6. Từ mục đích được phép đến điều kiện có thể thực thi

Có thể chia điều kiện thành ba nhóm:

| Nhóm | Ví dụ | Cách kiểm soát |
|---|---|---|
| Có thể kiểm tra kỹ thuật trực tiếp | Danh tính, tài nguyên, thao tác, thời hạn, kênh | Kiểm tra tại backend, broker và hệ thống đích |
| Cần đối chiếu nguồn nghiệp vụ | Ticket có đúng hệ thống, trạng thái, cửa sổ công việc không | Tra nguồn có thẩm quyền và áp quy tắc xác minh |
| Cần đánh giá trách nhiệm | Công việc có hợp lý, tác động có phù hợp tình huống không | Owner hoặc người duyệt có thẩm quyền đánh giá, lưu lý do |

Không thể chứng minh toàn bộ ý định của con người chỉ bằng một chuỗi lý do. Người dùng nhập “xử lý sự cố” chưa đủ. Hệ thống cần thu hẹp những gì họ có thể thực hiện và lưu bằng chứng để đánh giá việc sử dụng.

### 6.1. Điều kiện chủ thể

Nhóm đủ điều kiện là một đầu vào, không phải toàn bộ quyết định. Cần xác nhận danh tính cá nhân hoặc workload, trạng thái còn hợp lệ, môi trường và điều kiện xác thực theo chính sách.

Một người không nên lấy danh tính workload để tránh phê duyệt của con người. Với nhà cung cấp, cần xác định cá nhân hoặc danh tính được quản lý, phạm vi hỗ trợ và thời hạn; không dùng tên chung của nhà cung cấp để cho mọi nhân sự quyền truy cập.

### 6.2. Điều kiện thao tác và tài nguyên

Use case cần xác định đích bằng định danh và miền quản lý phù hợp. “Mọi tài nguyên trong system scope” thường rộng hơn nhu cầu của một công việc cụ thể.

Nếu chỉ cho restart dịch vụ, broker không nên đồng thời cho truyền lệnh tùy ý, chọn executable hoặc sửa cấu hình mà tiến trình đặc quyền sẽ thực thi. Những khả năng đó có thể làm thao tác thực tế vượt khỏi use case dù API vẫn được đặt tên là `restart`.

Các hệ thống chỉ hỗ trợ vai trò rộng hơn nhu cầu cần được đánh giá trung thực. Không ghi nhận đã thực thi JEA chỉ vì inventory có danh sách hành động hẹp. Có thể cần cơ chế trung gian, tách danh tính hoặc ngoại lệ theo chính sách tổ chức.

### 6.3. Điều kiện thời gian và credential

Use case xác định giới hạn; từng grant phải có thời điểm bắt đầu, hết hạn và xử lý thu hồi thực tế. Không coi use case còn hiệu lực một tháng là cho phép giữ một phiên admin suốt tháng.

Nếu thiết kế không cho xuất secret, cần cơ chế thực thi tương ứng. Quyền vault cho đọc giá trị secret rồi yêu cầu người dùng “chỉ dùng qua broker” không đáp ứng giới hạn đó.

Đối với workload hoạt động liên tục, có thể áp chính sách cấp hoặc gia hạn tự động khi điều kiện còn hợp lệ. Phải mô tả rõ chu kỳ, consumer, giới hạn và điều kiện dừng; không mặc nhiên áp luồng bấm duyệt thủ công cho từng lần cấp của mọi workload.

## 7. Ví dụ: use case restart service instance production

Giả sử đội orders cho phép kỹ sư trực ca xem trạng thái và restart `svc-72e8` hoặc `svc-91a4` để xử lý một sự cố. Công việc đi qua broker, không cấp shell hoặc xuất credential.

Đặc tả dưới đây là **YAML minh họa**, không phải cấu hình nạp vào sản phẩm:

```yaml
use_case_id: UC-ORDERS-PROD-RESTART
version: 3
state: approved
purpose: Khoi phuc order-worker instance bi treo trong su co
valid_from: '2026-11-01T00:00:00+07:00'
valid_until: '2026-12-31T00:00:00+07:00'
owner_ref: team-orders-service
technical_owner_ref: team-orders-operations
eligible_subjects:
  type: human
  group_ref:
    authority: identity-acme
    id: group-orders-oncall
execution_identity_ref: pam-broker-orders-operations
system_scope_ref:
  system_id: sys-orders-prod
  scope_version: 4
resources:
  authority: service-inventory-acme
  ids:
    - svc-72e8
    - svc-91a4
allowed_actions:
  - service.status
  - service.restart
requirements:
  work_reference_type: incident
  work_reference_must_match_system: true
  per_request_approval_policy_ref: orders-production-operations
  execution_channel: pam_broker
  credential_export_allowed: false
  arbitrary_shell_allowed: false
  maximum_grant_minutes: 20
  grant_must_end_before_use_case_expiry: true
  activity_evidence_required: true
review_due_at: '2026-12-01T17:00:00+07:00'
```

Trong ví dụ, use case là khuôn khổ cho một loại công việc. Mỗi yêu cầu vẫn cần chọn instance thực sự cần thao tác và đáp ứng chính sách phê duyệt từng lần. Người đủ điều kiện không tự nhận quyền trên cả hai instance nếu chỉ cần một.

`review_due_at` là mốc cần rà soát, còn `valid_until` là hạn hiệu lực của mô hình ví dụ. Hành vi khi quá hạn rà soát phải được chính sách quy định; không tự coi hai trường này đồng nghĩa.

Với thiết kế yêu cầu grant không vượt hạn use case, có thể tính:

```text
expires_at = min(
    activated_at + 20 phút,
    thời điểm kết thúc cửa sổ công việc đã duyệt,
    valid_until của use case
)
```

Chỉ kích hoạt khi các cửa sổ liên quan đang hợp lệ. Nếu không còn khoảng thời gian được phép, từ chối cấp mới. Việc đồng hồ hoặc trạng thái ở các thành phần bị trễ cần được tính đến trong thiết kế thực thi và thu hồi.

### 7.1. Những việc thuộc và ngoài use case

| Tình huống | Kết quả theo use case ví dụ |
|---|---|
| Kỹ sư đủ điều kiện xem trạng thái đúng instance trong yêu cầu hợp lệ | Có thể tiếp tục luồng kiểm tra, phê duyệt và cấp quyền |
| Restart đúng instance qua broker sau khi mọi điều kiện đã đủ | Được phép trong giới hạn grant |
| Restart một dịch vụ khác trên cùng máy | Ngoài tập tài nguyên |
| Reboot máy chủ chứa instance | Ngoài tập thao tác và có phạm vi ảnh hưởng rộng hơn |
| Sửa file cấu hình hoặc binary của dịch vụ | Cần use case hoặc yêu cầu thay đổi phù hợp riêng |
| Lấy mật khẩu database để tự chẩn đoán | Không thuộc mục đích và phương thức credential được phép |
| Dùng tài khoản runtime của workload để mở console cá nhân | Không được suy ra từ use case restart |
| Trích xuất dữ liệu production cho thử nghiệm development | Công việc khác, cần quy trình và kiểm soát tương ứng |

Một hành động nằm ngoài use case không nhất thiết không bao giờ được tổ chức cho phép. Nó cần một căn cứ và luồng phù hợp khác, thay vì mượn use case hiện tại để bỏ qua đánh giá.

## 8. Kiểm tra use case khi tiếp nhận yêu cầu

Mã giả sau chỉ minh họa đánh giá tính phù hợp của yêu cầu. Nó không cấp quyền và không thay thế kiểm tra tại thời điểm thực thi:

```text
function assess_use_case_fit(request, trusted_context):
    use_case = load_current_use_case(request.use_case_id)

    require use_case.state == APPROVED
    require use_case.is_valid_at(trusted_context.now)
    require request.use_case_version == use_case.version
    require subject_matches_eligible_type(request.subject, use_case)
    require subject_is_currently_eligible(request.subject, use_case)
    require request.actions is not empty
    require request.resources is not empty
    require request.actions is subset of use_case.allowed_actions
    require request.resources is subset of use_case.allowed_resources
    require request.execution_channel == use_case.required_channel
    require request.duration <= use_case.maximum_grant_duration

    work = read_authoritative_work_reference(request.work_reference)
    require work.matches_system(use_case.system_scope)
    require work.is_eligible_for_this_operation
    require required_controls_can_be_enforced(use_case)

    return ELIGIBLE_FOR_REQUIRED_APPROVAL_AND_GRANT_CHECKS
```

Backend tự lấy danh tính, thời gian và thông tin công việc từ nguồn tin cậy; không chỉ tin các cờ do client gửi. Nhận kết quả phù hợp mới là một bước trong luồng. Vẫn cần kiểm tra quyết định phê duyệt, trạng thái tài nguyên và những điều kiện khác trước khi cấp quyền.

Khi thực thi, tiếp tục ràng buộc thao tác và đích với grant đã cấp. Nếu mục đích được ghi đúng nhưng broker gửi lệnh sang tài nguyên khác, mục tiêu kiểm soát vẫn chưa đạt.

Các trường hợp không xác định được phiên bản, tài nguyên hoặc công việc cần đi vào trạng thái rõ ràng theo chính sách. Không dùng giá trị thiếu như “mọi tài nguyên”, “không giới hạn thời gian” hoặc “mục đích bất kỳ”.

## 9. Thay đổi, ngoại lệ và vòng đời

### 9.1. Quản lý phiên bản

Có thể dùng vòng đời minh họa:

```text
DRAFT → UNDER_REVIEW → APPROVED
                         ├→ SUSPENDED
                         ├→ SUPERSEDED
                         └→ RETIRED
```

Mỗi phiên bản đã được chấp thuận cần giữ được nội dung và quyết định tương ứng. Khi thêm tài nguyên, thao tác, loại chủ thể hoặc cách xuất credential, cần đánh giá lại ảnh hưởng. Không sửa nội dung rồi để các quyết định cũ trông như đã duyệt nội dung mới.

Việc đổi một lỗi chính tả có thể được xử lý khác với mở rộng quyền nếu quy trình phân biệt được. Dù vậy, lịch sử cần cho thấy nội dung nào đã được áp dụng cho từng lần sử dụng.

### 9.2. Mở rộng công việc giữa sự cố

Sau khi restart, kỹ sư có thể phát hiện cần sửa cấu hình. Đây là nhu cầu mới so với use case ban đầu. Có thể dùng một use case thay đổi cấu hình đã có hoặc gửi yêu cầu bổ sung theo thẩm quyền; không tự nâng quyền của grant restart.

Nếu cần ngoại lệ, phải có phạm vi, lý do, trách nhiệm, thời hạn và bằng chứng phù hợp. Ngoại lệ có thời hạn không nên biến thành allowed use case thường trực chỉ vì đã dùng một lần.

### 9.3. Truy cập khẩn cấp

Use case khẩn cấp cần xác định điều kiện kích hoạt, chủ thể ứng cứu, phạm vi tối thiểu có thể thực thi, thời hạn và việc rà soát. Nếu tổ chức cho phép luồng break-glass không chờ phê duyệt thông thường, phải ghi đúng đó là luồng ngoại lệ được quản trị riêng.

Rà soát sau sự kiện hữu ích để đánh giá mục đích và tác động, nhưng không biến một phê duyệt hồi tố thành bằng chứng rằng đã hoàn thành điều kiện phê duyệt trước.

### 9.4. Khi tạm dừng hoặc ngừng use case

Ngừng cấp mới không tự chấm dứt mọi grant, phiên hay credential đang có. Cần quy định việc rà soát và thu hồi các quyền còn hiệu lực, cùng xử lý workload đang phụ thuộc để tránh gián đoạn ngoài dự kiến.

Nếu use case bị dừng vì nghi bị lạm dụng, luồng ứng phó cần quyết định việc chặn cấp tiếp, thu hồi grant, xử lý credential và bảo toàn bằng chứng. Nếu use case bị thay thế bình thường, cần kiểm tra phiên bản mới có bảo toàn những kiểm soát cần thiết và consumer đã chuyển đúng cách.

Đổi owner cũng cần bàn giao nhu cầu, trách nhiệm credential và quyền quyết định. Một thay đổi trường owner không tự xác nhận mọi quyền cũ vẫn còn phù hợp.

## 10. Rà soát use case bằng hoạt động thực tế

Rà soát định kỳ hoặc theo sự kiện nên đặt các câu hỏi:

- Công việc còn cần thiết không, hay hệ thống và quy trình đã thay đổi?
- Chủ thể, danh tính thực thi và consumer còn đúng không?
- Thao tác và tài nguyên có thể thu hẹp hơn không?
- Có lần sử dụng nào nằm ngoài điều kiện đã xác nhận không?
- Có đường dùng credential trực tiếp ngoài kênh được phép không?
- Bằng chứng có đủ nối hoạt động tới người/workload và công việc cụ thể không?
- Owner, kiểm soát và cơ chế thu hồi còn hoạt động không?

Không thấy sử dụng trong một cửa sổ ngắn chưa đủ để ngừng use case. Công việc khôi phục, tác vụ theo quý hoặc hỗ trợ hiếm gặp có thể vẫn cần. Cần đối chiếu mục đích và lịch sử phù hợp với chu kỳ công việc.

Ngược lại, thấy nhiều lần dùng thành công không chứng minh việc dùng đều đúng mục đích. Thành công kỹ thuật có thể xảy ra qua quyền rộng chưa được kiểm soát. Cần đánh giá thao tác, đích, ngữ cảnh và điều kiện.

### Phân loại kết quả đánh giá

| Kết quả | Cách diễn giải |
|---|---|
| Phù hợp theo bằng chứng đã quan sát | Thao tác, đích và điều kiện được ghi nhận khớp use case áp dụng |
| Vi phạm đã xác minh | Có bằng chứng hoạt động ngoài một ràng buộc bắt buộc |
| Chưa đủ bằng chứng | Thiếu phiên bản, liên kết phiên, log hoặc thông tin điều kiện |
| Yêu cầu mới ngoài phạm vi | Cần đánh giá use case khác hoặc thay đổi được quản lý |

Không gộp phần thiếu bằng chứng vào phần phù hợp. Một tài khoản dùng chung chỉ ghi username ở hệ thống đích có thể chưa đủ để xác định chủ thể hoặc công việc đã dùng quyền.

## 11. Bằng chứng và chỉ số quản trị

### 11.1. Chuỗi bằng chứng cần liên kết

| Đối tượng | Thông tin cần giữ |
|---|---|
| Use case | ID, phiên bản, nội dung, trạng thái, owner và quyết định chấp thuận |
| Yêu cầu cụ thể | Chủ thể, mục đích, công việc tham chiếu, tài nguyên và thao tác đề nghị |
| Đánh giá và phê duyệt | Kết quả kiểm tra, nguồn dữ liệu, người/cơ chế quyết định và thời điểm |
| Grant | Danh tính thực thi, quyền thực tế, thời hạn và tham chiếu use case áp dụng |
| Hoạt động | Chủ thể, phiên, đích, thao tác, kết quả cho phép/từ chối và kết quả thực hiện |
| Thu hồi hoặc đóng việc | Quyền/phiên đã xử lý, xác minh kết quả và phần còn tồn tại |

Quyết định cho phép và kết quả thao tác là hai sự kiện khác nhau. Một lệnh restart được phép nhưng thất bại không nên được ghi thành đã khôi phục dịch vụ thành công.

Không đưa mật khẩu, token hoặc private key vào bản ghi use case và log đánh giá. Mô tả mục đích có thể chứa chi tiết sự cố hoặc dữ liệu cá nhân, nên cũng cần giới hạn nội dung và quyền xem phù hợp.

### 11.2. Chỉ số với mẫu số rõ ràng

```text
Độ bao phủ mục đích đã xác nhận =
    số danh tính đặc quyền trong phạm vi có ít nhất một
    allowed use case còn hợp lệ và ownership đã xác nhận
    / tổng số danh tính đặc quyền trong phạm vi
```

Ví dụ, có năm danh tính đặc quyền và bốn danh tính đạt điều kiện trên thì độ bao phủ là `4/5`. Chỉ số này chưa chứng minh mọi quyền của bốn danh tính đều cần thiết. Cần kiểm tra thêm phần quyền vượt nhu cầu hoặc hoạt động không gắn với use case nào.

Có thể bổ sung số use case quá hạn rà soát, số lần sử dụng ngoài phạm vi đã xác minh, số hoạt động chưa đủ bằng chứng và tỷ lệ grant có liên kết đúng phiên bản.

Nếu có mười hoạt động được đánh giá, tám phù hợp, một vi phạm đã xác minh và một chưa đủ dữ liệu, cần giữ cả ba nhóm. Không báo cáo toàn bộ là phù hợp bằng cách bỏ hoạt động thiếu dữ liệu khỏi mẫu số mà không giải thích.

Tỷ lệ liên kết use case cao cũng chưa chứng minh kiểm soát hiệu quả. Cần phân biệt “đã gắn nhãn mục đích” với “điều kiện đã được cưỡng chế và xác minh”.

## 12. Bài tập thiết kế và kiểm thử chấp nhận

### Tình huống

Tài khoản `svc-orders-ops` đang có quyền quản trị rộng, được dùng để restart dịch vụ, triển khai bản mới và hỗ trợ một tác vụ backup. Inventory chỉ ghi allowed use case là “vận hành orders”. Kỹ sư thường nhận mật khẩu trực tiếp, trong khi workload cũng dùng cùng credential.

### Yêu cầu thực hành

1. Tách các công việc thành những use case có mục đích, chủ thể, tài nguyên và thao tác cụ thể.
2. Xác định việc nào do con người thực hiện, việc nào là workload, và có nên tách danh tính không.
3. Ghi ownership cho nhu cầu nghiệp vụ, danh tính, credential và vận hành.
4. Chỉ ra điều kiện có thể thực thi kỹ thuật và phần cần người có thẩm quyền đánh giá.
5. Thiết kế cách cấp quyền phù hợp cho restart mà không mặc nhiên cho đọc credential hoặc sửa cấu hình.
6. Liệt kê bằng chứng và cách xử lý khi phát hiện dùng tài khoản để xuất dữ liệu ngoài mục đích.

### Hướng giải tham khảo

Tách restart, triển khai và backup thành các use case riêng. Đánh giá danh tính tối thiểu cho từng công việc thay vì giữ một tài khoản rộng cho mọi nhu cầu. Con người dùng xác thực cá nhân và kênh thao tác được kiểm soát; workload có danh tính và cơ chế cấp credential phù hợp với vòng đời của nó.

Nếu chưa thể tách ngay, cần ghi rõ tổng quyền thực tế, mức độ chia sẻ, phụ thuộc và phần kiểm soát chưa đạt. Một mô tả use case mới không tự thu hẹp tài khoản hiện tại. Việc thay đổi quyền, chuyển credential hoặc luân chuyển phải đi qua công việc triển khai riêng với kiểm tra tác động.

### Ma trận nghiệm thu trên dữ liệu hoặc môi trường thực hành

| Ca kiểm tra | Kết quả mong đợi |
|---|---|
| Yêu cầu đúng use case nhưng chưa đủ phê duyệt bắt buộc | Chưa cấp quyền |
| Đúng chủ thể, thao tác, đích, thời gian và mọi điều kiện cần thiết | Cấp grant giới hạn, thực thi và có bằng chứng liên kết |
| Chủ thể chỉ nhập lý do đúng mẫu nhưng không đủ điều kiện | Bị chặn bởi kiểm tra danh tính và chính sách |
| Tài nguyên nằm cùng system scope nhưng ngoài tập use case | Không tự cho phép |
| Đúng tài nguyên nhưng yêu cầu sửa cấu hình trong use case restart | Chuyển đánh giá phù hợp, không tự mở rộng grant |
| Kỹ sư cố dùng danh tính workload để mở console cá nhân | Không được coi là sử dụng workload hợp lệ |
| Use case đã hết hiệu lực, bị tạm dừng hoặc sai phiên bản | Chặn cấp mới theo chính sách và đánh giá quyền đang tồn tại |
| Mô tả không cho xuất secret nhưng vault vẫn cấp giá trị trực tiếp | Phát hiện khoảng cách giữa mô tả và kiểm soát thực tế |
| Chủ sở hữu không còn hoạt động hoặc chưa bàn giao | Gắn trạng thái cần xử lý, không tự coi ownership đã xác nhận |
| Log thiếu liên kết cá nhân–phiên ở tài khoản dùng chung | Đánh giá là chưa đủ bằng chứng cho phần chủ thể |
| Grant hết hạn nhưng phiên vẫn thao tác được | Phát hiện kiểm soát thu hồi chưa đạt, không chỉ dựa vào trạng thái UI |
| Yêu cầu dùng cho công việc khẩn cấp ngoài luồng hiện tại | Áp dụng luồng khẩn cấp hoặc ngoại lệ có thẩm quyền, giữ đúng loại bằng chứng |

Một allowed use case có ích phải giúp xác định công việc hợp lệ và đối chiếu được với quyền thực tế. Giá trị của nó nằm ở sự nhất quán giữa mục đích đã xác nhận, ownership, điều kiện thực thi và bằng chứng về những gì đã xảy ra.