# Access approval policy

Trong quản lý truy cập đặc quyền (PAM), **access approval policy** là chính sách xác định yêu cầu truy cập nào được xem xét, ai hoặc cơ chế nào có quyền chấp thuận, cần những điều kiện gì và quyết định có giá trị đến đâu. Chính sách giúp việc cấp quyền cho tài khoản quản trị, tài khoản dịch vụ và hạ tầng nhạy cảm có căn cứ nhất quán, thay vì phụ thuộc vào người đang trực hoặc mức độ khẩn cấp được ghi trong một tin nhắn.

Bài học thuộc chương **Governance**, tập trung vào thiết kế và quản trị chính sách. Mục tiêu là kết nối thẩm quyền quyết định với kiểm kê quyền, ownership, đặc quyền tối thiểu, JIT/JEA, quản lý credential trong vault, giám sát phiên và bằng chứng phục vụ kiểm toán hoặc ứng phó sự cố.

Các ma trận, thời hạn và mô hình dữ liệu dưới đây là ví dụ thiết kế nội bộ. Chúng không phải yêu cầu bắt buộc của mọi tổ chức hay cấu hình có thể áp dụng trực tiếp cho một sản phẩm PAM.

## 1. Kết quả cần đạt

Sau bài học, người học có thể:

- Phân biệt chính sách phê duyệt với xác thực, phê duyệt thay đổi và thực thi cấp quyền.
- Xác định phạm vi, chủ sở hữu chính sách, nguồn thẩm quyền và vai trò người duyệt.
- Thiết kế quy tắc theo mức rủi ro, có xử lý dữ liệu thiếu và xung đột rõ ràng.
- Quản lý phân tách trách nhiệm, ủy quyền, ngoại lệ và truy cập khẩn cấp.
- Ràng buộc quyết định với đúng nội dung yêu cầu, phiên bản chính sách và thời hạn.
- Kiểm tra hiệu quả vận hành bằng bằng chứng từ yêu cầu đến quyền thực tế, không chỉ số lần bấm duyệt.

## 2. Chính sách phê duyệt quyết định điều gì?

Một chính sách có thể kiểm tra được cần trả lời:

1. Ai đủ điều kiện gửi yêu cầu cho loại quyền này?
2. Những tài nguyên, thao tác và mục đích sử dụng nào thuộc phạm vi?
3. Khi nào được quyết định tự động, khi nào cần người duyệt?
4. Người duyệt lấy thẩm quyền từ đâu và phải độc lập với ai?
5. Quy tắc nào không được bỏ qua bằng một lần chấp thuận thông thường?
6. Quyết định áp dụng cho phiên bản yêu cầu nào, được dùng mấy lần và trong bao lâu?
7. Điều gì xảy ra khi bị từ chối, quá hạn, thiếu dữ liệu hoặc kiểm soát không sẵn sàng?
8. Ai chịu trách nhiệm cho ngoại lệ, thay đổi chính sách và bằng chứng thực thi?

Một câu như “truy cập production cần manager duyệt” chưa đủ. Nó chưa xác định manager nào, có thẩm quyền với tài nguyên nào, có được tự duyệt không, có được đồng ý cho xuất secret không hoặc yêu cầu thay đổi sau lúc duyệt được xử lý thế nào.

### Phân biệt các lớp kiểm soát

| Lớp | Chức năng | Giới hạn |
|---|---|---|
| Xác thực | Xác định người hoặc workload | Không tự cho phép thực hiện công việc đặc quyền |
| Điều kiện xin quyền | Xác định chủ thể có thể yêu cầu loại quyền nào | Không tự chấp thuận từng lần sử dụng |
| Chính sách phê duyệt | Xác định quy tắc và thẩm quyền ra quyết định | Không tự tạo quyền ở hệ thống đích |
| Phê duyệt yêu cầu | Chấp thuận nội dung cụ thể theo chính sách | Không cho phép mở rộng ngoài nội dung đã duyệt |
| Cấp quyền và thực thi | Tạo grant, giới hạn thao tác và tài nguyên | Cần kiểm tra hiệu lực quyết định và điều kiện hiện tại |
| Giám sát, thu hồi | Theo dõi sử dụng và chấm dứt quyền | Không tự đảo ngược tác động đã xảy ra |

Phê duyệt thay đổi cũng khác phê duyệt truy cập. Một thay đổi ứng dụng đã được chấp thuận chưa mặc nhiên cho mọi thành viên nhóm quyền admin để thực hiện. Tổ chức có thể liên kết hai quy trình, nhưng phải nêu rõ quyết định nào bao phủ công việc và quyết định nào bao phủ quyền truy cập.

MFA là điều kiện xác thực, có thể áp dụng cho cả người xin và người duyệt. Nó không thay thế thẩm quyền phê duyệt hoặc sự độc lập cần có giữa hai người.

## 3. Thiết lập trách nhiệm quản trị

| Vai trò | Trách nhiệm cần làm rõ |
|---|---|
| Chủ sở hữu chính sách | Duy trì mục tiêu, phạm vi, phiên bản, lịch rà soát và trách nhiệm xử lý thiếu sót |
| Chủ sở hữu hệ thống/nghiệp vụ | Xác nhận nhu cầu truy cập, ảnh hưởng vận hành và mục đích sử dụng |
| Chủ sở hữu kỹ thuật | Xác định quyền tối thiểu, tài nguyên và khả năng thực thi kiểm soát |
| Đơn vị an toàn thông tin hoặc quản trị rủi ro | Đóng góp tiêu chí rủi ro, điều kiện độc lập và quản lý ngoại lệ theo thẩm quyền |
| Đơn vị vận hành PAM | Triển khai luồng, tích hợp nguồn dữ liệu, cấp/thu hồi quyền và lưu bằng chứng |
| Người duyệt được chỉ định | Quyết định trong phạm vi trách nhiệm, kiểm tra nội dung và ghi lý do phù hợp |
| Người đánh giá độc lập | Kiểm tra thiết kế và việc áp dụng, phát hiện khoảng cách và theo dõi khắc phục |

Một người có thể giữ nhiều vai trò nếu mô hình tổ chức cho phép, nhưng vẫn phải đáp ứng điều kiện phân tách trách nhiệm đối với quyết định cụ thể. Vai trò vận hành PAM không tự bao gồm quyền thay đổi mọi chính sách hoặc duyệt mọi yêu cầu.

Chủ sở hữu tài khoản dịch vụ, đơn vị quản lý credential và chủ sở hữu tài nguyên có thể khác nhau. Chính sách cần chỉ rõ ai xác nhận nhu cầu, ai chịu trách nhiệm cho consumer và ai có thẩm quyền quyết định việc cấp phát credential.

## 4. Xác định đầu vào và độ tin cậy dữ liệu

Chính sách chỉ có thể ra quyết định đúng khi các thuộc tính đầu vào có nguồn phù hợp.

| Đầu vào | Ví dụ | Nguồn cần xác minh |
|---|---|---|
| Chủ thể | Người, workload, nhóm đủ điều kiện, trạng thái hoạt động | Nguồn danh tính và cơ chế xác thực |
| Tài nguyên | Định danh, tenant, môi trường, mức nhạy cảm | Inventory và nguồn quản lý tài nguyên |
| Quyền yêu cầu | Thao tác, vai trò, khả năng thay đổi hoặc đọc dữ liệu | Catalog quyền và khả năng thực tế của đích |
| Mục đích | Allowed use case, sự cố, thay đổi, hỗ trợ | Hồ sơ được quản lý và đơn vị chịu trách nhiệm |
| Credential | Cấp trực tiếp hay dùng qua broker, sống lâu hay ngắn hạn | Nguồn quản lý credential và cơ chế cấp phát |
| Thời gian | Cửa sổ công việc, hạn kích hoạt, thời lượng | Nguồn thời gian tin cậy và dữ liệu được duyệt |
| Tín hiệu rủi ro | Mức tác động, trạng thái kiểm soát, ngữ cảnh truy cập | Nguồn được kiểm soát, có độ mới xác định |
| Người duyệt | Vai trò, phạm vi thẩm quyền, ủy quyền | Nguồn ownership và quản lý vai trò |

Không để người yêu cầu tự khai production thành development để được luồng duyệt nhẹ hơn. Không coi chuỗi `approved` trong ticket hoặc cờ `is_admin_request=false` từ client là quyết định đáng tin cậy.

Chính sách phải có hành vi khi dữ liệu thiếu, cũ hoặc mâu thuẫn. Ví dụ, tài nguyên chưa xác minh môi trường có thể chuyển sang trạng thái cần bổ sung dữ liệu và không được cấp quyền trong lúc chờ. Không mặc định nó là rủi ro thấp để hệ thống tiếp tục.

Nếu một nguồn không có thẩm quyền đối với trường dữ liệu đang xét, việc nó cập nhật gần nhất chưa đủ để chọn làm căn cứ. Cần quy tắc ưu tiên nguồn và lưu phần mâu thuẫn để xử lý.

## 5. Phân loại yêu cầu theo rủi ro

Rủi ro có thể phụ thuộc vào:

- Mức nhạy cảm của tài nguyên và môi trường.
- Tập thao tác, khả năng thay đổi dữ liệu hoặc điều khiển hệ thống.
- Phạm vi ảnh hưởng: một đối tượng, một hệ thống hay nhiều hệ thống.
- Khả năng lấy và dùng credential ngoài kênh kiểm soát.
- Thời hạn, số lần kích hoạt và điều kiện thu hồi.
- Loại chủ thể, mục đích và chất lượng bằng chứng.
- Tình trạng các kiểm soát bắt buộc như broker hoặc log hoạt động.

Không chỉ dùng tên vai trò như `reader` hoặc `operator` để phân loại. Một quyền đọc secret có thể ảnh hưởng lớn hơn một quyền thay đổi giới hạn trên tài nguyên thử nghiệm. Cần xem khả năng thực tế và đường quyền liên quan.

### Ma trận minh họa

| Loại yêu cầu | Cách quyết định có thể được tổ chức chọn | Điều kiện cốt lõi |
|---|---|---|
| Thao tác hẹp trên tài nguyên thực hành | Quyết định tự động theo chính sách đã được chấp thuận | Danh tính và đích đã xác minh, quyền hẹp, có giới hạn |
| Restart một dịch vụ production | Người duyệt có trách nhiệm với dịch vụ; thêm vai trò độc lập nếu chính sách yêu cầu | Đúng use case, tài nguyên, cửa sổ công việc và kênh thực thi |
| Sửa quyền quản trị hoặc cấu hình có ảnh hưởng rộng | Nhiều vai trò quyết định độc lập theo mức tác động | Đánh giá đường mở rộng quyền, khả năng khôi phục và bằng chứng |
| Xuất credential nhạy cảm | Luồng đặc biệt hoặc từ chối nếu bị cấm trong phạm vi đó | Không được thay thế bằng một phê duyệt thông thường |
| Workload nhận credential ngắn hạn cho công việc đã định | Quyết định tự động từng lần theo chính sách và danh tính workload | Binding workload–tài nguyên đáng tin cậy, tái đánh giá điều kiện |
| Thiếu owner hoặc chưa xác định được tài nguyên | Chờ xác minh hoặc từ chối theo quy tắc | Không cấp quyền trong khi điều kiện bắt buộc chưa rõ |
| Khẩn cấp | Luồng khẩn cấp được quản trị riêng | Chủ thể, điều kiện kích hoạt, thời hạn và bằng chứng riêng |

Ma trận là điểm khởi đầu. Các ngưỡng và vai trò phải được cụ thể hóa để hai người vận hành có thể áp dụng nhất quán cho cùng một yêu cầu.

## 6. Thẩm quyền người duyệt và phân tách trách nhiệm

### 6.1. Quyền duyệt có phạm vi

Người duyệt cần có thẩm quyền với hệ thống, loại quyền và mức tác động đang xét. Một quản lý nhân sự có thể xác nhận nhiệm vụ của nhân viên nhưng chưa chắc đủ hiểu biết hoặc trách nhiệm để duyệt quyền kiểm soát một nền tảng dùng chung.

Tổ chức có thể kết hợp xác nhận nhu cầu của quản lý với quyết định của owner tài nguyên. Phải mô tả rõ mỗi vai trò quyết định điều gì, tránh thu nhiều chữ ký nhưng không ai thực sự chịu trách nhiệm cho quyền được cấp.

### 6.2. Độc lập theo danh tính gốc

Nếu chính sách yêu cầu độc lập, người nhận quyền không được tự duyệt qua một tài khoản khác. Hệ thống cần so sánh danh tính gốc phù hợp, không chỉ username.

Nếu yêu cầu hai người, một người thuộc hai nhóm không được tính là hai người độc lập. Nếu requester đồng thời là owner tài nguyên, cần chuyển tới người có thẩm quyền thay thế theo chính sách; không bỏ điều kiện độc lập vì thiếu người thuận tiện.

Cũng cần kiểm soát quyền sửa nhóm người duyệt, ownership, ngưỡng rủi ro và chính sách. Một chủ thể có thể tác động quyết định mà không trực tiếp bấm duyệt nếu họ sửa dữ liệu định tuyến để yêu cầu của mình được tự động thông qua.

### 6.3. Ủy quyền và chuyển cấp

Ủy quyền cần có người giao, người nhận, phạm vi, thời gian và căn cứ. Quyền ủy quyền không nên được hiểu là có thể chuyển tiếp vô hạn. Hệ thống cần phát hiện người nhận không còn hợp lệ hoặc chuỗi ủy quyền ngoài quy tắc.

Chuyển cấp khi quá thời gian chờ là chuyển tới người hoặc vai trò có thẩm quyền đã định. Nó không làm một yêu cầu chưa được quyết định trở thành được chấp thuận.

Thông báo chỉ hỗ trợ vận hành. Hành động duyệt phải được xác thực và ràng buộc với đúng yêu cầu; không để một lượt xem trước liên kết hoặc truy cập GET tự tạo quyết định. Không dùng việc chuyển tiếp email làm bằng chứng duy nhất về thẩm quyền.

## 7. Quy tắc bắt buộc, xung đột và kết quả quyết định

### 7.1. Chấp thuận không được vượt mọi ràng buộc

Chính sách cần phân biệt:

- Điều kiện cho phép đi vào luồng xem xét.
- Quyết định mà người duyệt được quyền đưa ra.
- Ràng buộc mà một lần chấp thuận thông thường không được vượt qua.
- Điều kiện có thể được ngoại lệ bởi một thẩm quyền và quy trình riêng.

Ví dụ, nếu chính sách cấm xuất credential của danh tính production trong luồng vận hành qua broker, một người quản lý bấm duyệt không tự biến yêu cầu xuất mật khẩu thành hợp lệ. Cần chọn phương thức được phép hoặc quy trình ngoại lệ thực sự có thẩm quyền nếu tổ chức cho phép loại ngoại lệ đó.

Không phải mọi điều kiện đều có thể được ngoại lệ. Danh sách điều kiện và thẩm quyền tương ứng phải do tổ chức xác định rõ.

### 7.2. Nhiều chính sách cùng áp dụng

Một yêu cầu có thể chịu quy tắc theo hệ thống, tài nguyên, loại danh tính và credential. Cần định nghĩa cách kết hợp, ví dụ:

- Từ chối bắt buộc có ưu tiên hơn chấp thuận thông thường.
- Các giới hạn thao tác và tài nguyên phải cùng được đáp ứng.
- Giới hạn thời lượng dùng giá trị chặt nhất trong các ràng buộc áp dụng.
- Các vai trò duyệt bổ sung cần được đáp ứng theo điều kiện độc lập đã đặt ra.
- Chỉ ngoại lệ được xác minh đúng thẩm quyền mới được thay đổi ràng buộc được phép ngoại lệ.

Đây là một cách thiết kế, không phải ngữ nghĩa mặc định của mọi engine. Phải triển khai và kiểm tra đúng cách kết hợp đã công bố. Không để quy tắc được viết sau âm thầm ghi đè một điều kiện chặn trước đó.

### 7.3. Các kết quả nên phân biệt

| Kết quả | Ý nghĩa |
|---|---|
| `DENY` | Yêu cầu không được phép theo điều kiện áp dụng |
| `NEEDS_DATA` | Chưa đủ dữ liệu để quyết định; không tạo quyền trong lúc chờ |
| `REQUIRES_APPROVAL` | Đủ điều kiện để đưa tới người duyệt, chưa được cấp quyền |
| `POLICY_APPROVED` | Cơ chế tự động đã chấp thuận theo chính sách cho đúng yêu cầu |
| `HUMAN_APPROVED` | Đã đủ quyết định con người cần thiết cho đúng nội dung |
| `ROUTE_TO_EMERGENCY_PROCESS` | Cần luồng khẩn cấp riêng, chưa có nghĩa tự cấp quyền |

Sau kết quả chấp thuận vẫn phải kiểm tra trước khi tạo grant. Nếu không có quy tắc cho phép phù hợp, mặc định không cấp quyền. Chính sách không nên dùng nhánh mặc định là quyền admin tạm thời để tránh chặn công việc.

## 8. Ràng buộc quyết định với yêu cầu và thời gian

Một quyết định cần tham chiếu ít nhất:

```text
Request ID + phiên bản nội dung
+ chủ thể nhận quyền + danh tính thực thi
+ thao tác + tài nguyên + mục đích/use case
+ điều kiện sử dụng + cửa sổ thời gian
+ phiên bản chính sách và quyết định áp dụng
```

Nếu tài nguyên, thao tác, chủ thể, cách xuất credential hoặc thời hạn thay đổi, cần đánh giá lại. Không gộp một quyết định cho phiên bản cũ với một quyết định cho phiên bản mới để đạt số lượng người duyệt.

### Các mốc thời gian cần tách

| Mốc | Tác dụng |
|---|---|
| Hạn chờ quyết định | Kết thúc hoặc chuyển xử lý yêu cầu chưa đủ phê duyệt |
| Hạn được kích hoạt | Ngăn dùng quyết định cũ để tạo grant mới quá muộn |
| Thời lượng grant | Giới hạn quyền kể từ thời điểm kích hoạt theo thiết kế |
| Hạn kết thúc tuyệt đối | Cắt quyền muộn nhất ở mốc được cho phép |
| Hiệu lực/phiên bản chính sách | Xác định quy tắc nào được áp dụng và xử lý chuyển đổi |

Ví dụ, chính sách có thể cho grant tối đa 20 phút và yêu cầu kết thúc trong cửa sổ công việc được duyệt. Khi đó thời điểm hết hạn thực tế lấy mốc sớm hơn giữa hai giới hạn. Số 20 phút là lựa chọn minh họa, không phải giá trị mặc định phù hợp cho mọi quyền.

Trước khi cấp, backend kiểm tra yêu cầu chưa bị hủy, quyết định chưa bị thu hồi, điều kiện còn đúng và chính sách hiện hành cho phép tiếp tục. Khi chính sách đổi, quy tắc chuyển đổi phải xác định quyết định cũ còn dùng được trong điều kiện nào; không mặc định mọi chấp thuận cũ hợp lệ mãi.

## 9. Ví dụ chính sách cho vận hành production qua broker

Đặc tả sau là **YAML minh họa mô hình chính sách**, không phải cú pháp của một sản phẩm:

```yaml
policy_id: PAM-PROD-OPERATIONS
version: 7
state: active
owner_ref: team-access-governance
scope:
  subject_type: human
  management_domain: acme
  environment: production
  use_case_family: controlled_service_operations
default_decision: deny
conflict_resolution: mandatory_deny_overrides_ordinary_approval
required_inputs:
  - verified_subject
  - verified_resource_scope
  - active_use_case
  - authoritative_work_reference
  - current_ownership
missing_required_input: needs_data_without_grant
approval:
  mode: human
  required_roles:
    - resource_service_owner
    - independent_operations_approver
  distinct_people_required: 2
  requester_may_approve: false
  bind_to_request_version: true
  bind_to_policy_version: true
  escalation_may_auto_approve: false
grant_constraints:
  maximum_duration_minutes: 20
  maximum_activations_per_request: 1
  must_end_within_approved_work_window: true
mandatory_controls:
  execution_channel: pam_broker
  arbitrary_shell_allowed: false
  credential_export_allowed: false
  activity_evidence_required: true
  unavailable_control_result: no_grant
policy_change_control:
  independent_review_required: true
  migration_rules_required: true
```

Hai người duyệt là lựa chọn của ví dụ cho nhóm công việc này. Chính sách cho workload hoặc môi trường khác có thể khác, nhưng phải được định nghĩa riêng thay vì mượn luồng này rồi bỏ các bước không thuận tiện.

Các nhãn như `activity_evidence_required` cần được triển khai bằng khả năng thực tế có thể xác minh. Nếu broker không ghi được hoạt động mà chính sách xem đó là điều kiện bắt buộc, không được cấp tiếp rồi chỉ ghi nhận rằng “đã cấu hình yêu cầu ghi log”.

Chính sách này cũng chưa tự mô tả catalog thao tác và tài nguyên của từng use case. Backend phải lấy đúng tập được phép và giới hạn grant theo yêu cầu cụ thể. Không cấp quyền trên toàn production chỉ vì yêu cầu nằm trong phạm vi áp dụng của chính sách production.

## 10. Quyết định tự động và tài khoản dịch vụ

Chính sách có thể cho phép phê duyệt tự động khi điều kiện rõ ràng, có nguồn xác minh và tác động được kiểm soát. Điều này khác với không có phê duyệt: bộ máy vẫn phải ra quyết định cho yêu cầu cụ thể theo một chính sách có thẩm quyền.

Với workload, có thể phân biệt:

1. Người có thẩm quyền chấp thuận mô hình workload–tài nguyên–quyền.
2. Mỗi lần cấp hoặc gia hạn, hệ thống kiểm tra workload còn đúng danh tính và điều kiện.
3. Thành phần cấp phát tạo credential hoặc grant có phạm vi và thời hạn thực tế.

Không yêu cầu con người bấm duyệt mỗi lần cấp credential ngắn hạn cho mọi workload nếu mô hình đã chọn là cấp tự động có kiểm soát. Đồng thời, không cho một workload tự đổi mục đích, mở rộng tài nguyên hoặc gia hạn vô hạn ngoài điều kiện đã được chấp thuận.

Danh tính máy cần được xác thực bằng cơ chế phù hợp. Một người gửi cờ `subject_type=workload` không đủ để đi vào luồng tự động. Chủ thể sửa chính sách hoặc nguồn thuộc tính cũng cần được kiểm soát để tránh tự mở rộng quyền.

Luân chuyển credential dịch vụ cần phối hợp với chủ sở hữu consumer và phụ thuộc. Phê duyệt quyền thực hiện luân chuyển không thay thế đánh giá tác động của thay đổi; ngược lại, một kế hoạch luân chuyển đã được đồng ý không cho mọi người quyền đọc secret hiện hành.

## 11. Timeout, thiếu kiểm soát, ngoại lệ và khẩn cấp

### 11.1. Người duyệt không phản hồi

Nhắc, chuyển cấp hoặc hết hạn theo quy tắc đã định. Không coi im lặng là chấp thuận trong một luồng yêu cầu quyết định rõ ràng. Để giảm chậm trễ, cần owner dự phòng, lịch trực, tiêu chí ưu tiên và yêu cầu có dữ liệu đầy đủ.

Có thể đo thời gian chờ để cải thiện vận hành, nhưng không biến mục tiêu tốc độ thành lý do bỏ thẩm quyền hoặc điều kiện độc lập.

### 11.2. Nguồn danh tính, ownership hoặc broker không sẵn sàng

Chính sách phải nêu hành vi theo loại lỗi. Với điều kiện bắt buộc chưa kiểm tra được, không tạo quyền theo luồng thông thường. Nếu tổ chức có cơ chế dự phòng hoặc khẩn cấp, chỉ áp dụng đúng điều kiện của luồng đó.

Không tự chuyển từ broker sang cấp mật khẩu trực tiếp vì broker lỗi nếu chính sách đang cấm xuất secret. Đó là thay đổi phương thức và rủi ro, cần căn cứ khác có thẩm quyền.

### 11.3. Ngoại lệ có thời hạn

Một hồ sơ ngoại lệ nên có đối tượng, ràng buộc cần thay đổi, lý do, tác động, thẩm quyền quyết định, kiểm soát bổ sung, thời hạn và tiêu chí kết thúc. Phải liên kết ngoại lệ với yêu cầu hoặc phạm vi được phép, không dùng một văn bản chung để duyệt mọi lần sau.

Ngoại lệ hết hạn cần được xử lý rõ: chặn cấp mới, xem xét grant còn tồn tại và khắc phục phần phụ thuộc theo quyết định đã định. Không để hệ thống tiếp tục ngoại lệ chỉ vì trường dữ liệu chưa được dọn.

### 11.4. Break-glass

Luồng truy cập khẩn cấp cần xác định chủ thể ứng cứu, điều kiện kích hoạt, giới hạn quyền, thời gian, thông báo và bằng chứng. Nếu hạ tầng thông thường không sẵn sàng, phương án dự phòng phải mô tả cách xác minh chủ thể và bảo toàn bằng chứng trong điều kiện đó.

Rà soát sau sự kiện đánh giá lý do, thao tác và thu hồi. Không ghi quyết định hồi tố như thể đã có phê duyệt trước khi quyền xuất hiện. Ngoại lệ khẩn cấp cần được giữ đúng loại để báo cáo phản ánh thực tế.

## 12. Quản lý thay đổi chính sách và thực thi

Chính sách cần có lịch sử phiên bản, người đề xuất, người đánh giá, người có thẩm quyền chấp thuận, thời điểm hiệu lực và quy tắc chuyển đổi. Những thay đổi như giảm người duyệt, tăng TTL, mở quyền xuất secret hoặc đổi nguồn ownership có thể làm giảm kiểm soát trên nhiều hệ thống cùng lúc.

Trước khi đưa phiên bản mới vào sử dụng, nên kiểm tra các ca được phép, bị chặn, thiếu dữ liệu và xung đột bằng dữ liệu hoặc môi trường thực hành. Đối chiếu kết quả với ý định chính sách, không chỉ kiểm tra file cấu hình có hợp lệ cú pháp hay không.

Khi triển khai, cần biết thành phần nào đang dùng phiên bản nào. Việc engine đã tải phiên bản mới nhưng broker hoặc thành phần cấp quyền vẫn dùng bản cũ tạo khoảng cách cần phát hiện. Quay lại phiên bản trước cũng phải có căn cứ và đánh giá các quyền có thể đã phát sinh.

Một lần cấp quyền bị timeout không chứng minh chưa có grant ở đích. Hệ thống thực thi cần mã thao tác ổn định, xử lý gọi lặp và đối soát. Chính sách phê duyệt giới hạn một lần kích hoạt sẽ mất ý nghĩa nếu retry có thể tạo thêm grant hoặc kéo dài quyền.

Tương tự, thu hồi quyết định không tự kết thúc mọi phiên. Cần gỡ quyền, xử lý token/credential/phiên theo khả năng của đích và xác minh kết quả. Những trạng thái này nên được tách để người vận hành không nhầm “đã yêu cầu thu hồi” với “quyền đã hết hiệu lực”.

## 13. Bằng chứng và chỉ số đánh giá

### Chuỗi bằng chứng

| Phần | Nội dung cần liên kết |
|---|---|
| Chính sách | ID, phiên bản, phạm vi, thẩm quyền và thời điểm hiệu lực |
| Yêu cầu | Chủ thể, danh tính thực thi, thao tác, tài nguyên, mục đích và phiên bản nội dung |
| Đánh giá | Thuộc tính từ nguồn nào, thời điểm nào, quy tắc nào áp dụng và kết quả |
| Quyết định | Người/cơ chế duyệt, thẩm quyền, tính độc lập, nội dung được duyệt và thời hạn |
| Cấp quyền | Mã grant, quyền thực tế ở đích, thời điểm và số lần kích hoạt |
| Hoạt động | Phiên, thao tác, đích, kết quả quyết định và kết quả thực hiện |
| Kết thúc | Hết hạn/thu hồi, xử lý phiên và credential liên quan, kết quả xác minh |

Bằng chứng cần được bảo vệ khỏi sửa/xóa trái phép, có kiểm soát truy cập và thời gian lưu theo yêu cầu tổ chức. Không ghi mật khẩu, token hoặc private key vào log quyết định. Bản ghi phiên và nội dung công việc cũng có thể chứa dữ liệu nhạy cảm.

### Chỉ số nên tách biệt

- Tỷ lệ grant có bằng chứng đầy đủ về quyết định hợp lệ trước khi quyền có hiệu lực.
- Số yêu cầu tự duyệt, sai thẩm quyền hoặc không đủ độc lập đã phát hiện.
- Số grant có phạm vi hoặc thời hạn vượt nội dung được chấp thuận.
- Số yêu cầu quá hạn, ngoại lệ còn hiệu lực và ngoại lệ đã quá hạn xử lý.
- Thời gian đến quyết định, tách theo luồng tự động, thủ công và mức ưu tiên.
- Số lần không xác định được trạng thái quyền ở đích sau lỗi hoặc thu hồi.

Ví dụ, có mười grant nhưng chỉ chín grant có chuỗi bằng chứng đủ mới và đầy đủ thì tỷ lệ bằng chứng là `9/10`. Grant còn lại là chưa xác minh, không được tính là phù hợp chỉ vì không có log vi phạm.

Thời gian xử lý cần nêu điểm bắt đầu, điểm kết thúc và cách tính các yêu cầu thiếu dữ liệu, bị từ chối hoặc hết hạn. Không làm thời gian trung bình đẹp hơn bằng cách chỉ giữ những yêu cầu được duyệt nhanh.

Một chính sách có nhiều lượt chấp thuận không tự chứng minh kiểm soát tốt. Cần kiểm tra các quyết định có đúng thẩm quyền, đúng nội dung và thực sự giới hạn quyền ở đích hay không.

## 14. Bài tập và ma trận nghiệm thu

### Tình huống

Một kỹ sư đề nghị xuất mật khẩu admin production vì broker đang lỗi. Owner dịch vụ đồng ý. Chính sách hiện hành cấm xuất credential trong luồng vận hành thông thường, yêu cầu hai người độc lập và có luồng khẩn cấp riêng. Người xin quyền đồng thời thuộc nhóm người duyệt thứ hai.

### Yêu cầu thiết kế

1. Xác định những điều kiện mà sự đồng ý của owner chưa đáp ứng.
2. Nêu vì sao tư cách thành viên nhóm người duyệt không cho phép tự duyệt.
3. Đề xuất kết quả quyết định cho yêu cầu hiện tại và điều kiện để chuyển luồng khác.
4. Mô tả bằng chứng cần giữ, bao gồm phiên bản chính sách và lỗi broker.
5. Chỉ ra việc cần kiểm tra nếu sau đó phát hiện quyền đã xuất hiện ở đích qua một kênh khác.

### Hướng giải tham khảo

Yêu cầu chưa hợp lệ theo luồng thông thường: phương thức xuất credential bị cấm và chưa đáp ứng điều kiện độc lập. Không tự cấp mật khẩu vì owner đồng ý. Nếu tình huống đáp ứng điều kiện khẩn cấp, chuyển tới luồng được quản trị riêng với đúng thẩm quyền, giới hạn và bằng chứng; nếu không thì xử lý hoặc từ chối theo chính sách.

Nếu quyền đã phát sinh qua kênh khác, cần xác định ai hoặc cơ chế nào đã cấp, bằng căn cứ nào, với phạm vi gì và xử lý quyền còn tồn tại. Không chỉ sửa trạng thái yêu cầu để dữ liệu trông nhất quán với một việc cấp quyền không có căn cứ.

### Ma trận nghiệm thu trên dữ liệu hoặc môi trường thực hành

| Ca kiểm tra | Kết quả mong đợi |
|---|---|
| Yêu cầu đủ dữ liệu và đúng điều kiện cho quyết định tự động | Có quyết định gắn đúng yêu cầu và chính sách trước khi cấp |
| Yêu cầu cần hai người nhưng mới có một quyết định | Không cấp quyền |
| Một người dùng hai tài khoản hoặc giữ hai vai trò để duyệt | Không tính thành hai người độc lập |
| Người duyệt không có thẩm quyền với tài nguyên | Quyết định không thỏa điều kiện |
| Có chấp thuận thông thường nhưng vi phạm ràng buộc bắt buộc | Không bỏ qua ràng buộc |
| Không xác định được môi trường, owner hoặc đích | Chờ dữ liệu hoặc từ chối theo quy tắc; không tự coi là rủi ro thấp |
| Hai chính sách áp dụng có giới hạn thời lượng khác nhau | Kết quả theo cách kết hợp đã công bố, không vượt giới hạn bắt buộc |
| Yêu cầu bị sửa sau một quyết định | Đánh giá lại theo phiên bản, không gộp quyết định sai nội dung |
| Quyết định hết hạn, bị thu hồi hoặc yêu cầu bị hủy | Chặn cấp mới và xử lý quyền có thể đã phát sinh |
| Người duyệt không phản hồi hoặc bị chuyển cấp | Không tự động biến im lặng thành chấp thuận |
| Broker hoặc kiểm soát bắt buộc không sẵn sàng | Áp hành vi đã định, không âm thầm đổi sang phương thức rủi ro hơn |
| Retry sau timeout khi cấp quyền | Đối soát và không tạo thêm grant ngoài giới hạn |
| Phiên bản chính sách thay đổi khi yêu cầu đang chờ | Áp quy tắc chuyển đổi, lưu đúng phiên bản và đánh giá lại khi cần |
| Luồng khẩn cấp được sử dụng | Giữ đúng loại quyết định và bằng chứng, có xử lý kết thúc theo chính sách |
| Thu hồi đã gửi nhưng phiên vẫn hoạt động | Phát hiện phần quyền còn hiệu lực và xử lý, không tuyên bố hoàn tất chỉ theo UI |

Một access approval policy có thể vận hành được phải tạo ra quyết định nhất quán, đúng thẩm quyền và có giới hạn rõ ràng. Bằng chứng cần nối chính sách với quyền thực tế để tổ chức biết điều kiện nào đã được đáp ứng, phần nào còn thiếu và ai chịu trách nhiệm xử lý.