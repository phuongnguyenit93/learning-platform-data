# Phát hiện lệnh nguy hiểm trong phiên đặc quyền — Dangerous command detection

## 1. Mục đích và giới hạn của việc phát hiện

Trong PAM, dangerous command detection là quá trình nhận diện những thao tác có khả năng gây thiệt hại lớn khi được thực hiện bằng quyền đặc biệt: xóa dữ liệu, làm gián đoạn dịch vụ, thay đổi kiểm soát truy cập, tiết lộ bí mật hoặc làm mất bằng chứng giám sát. Đối tượng phân tích có thể là lệnh trong phiên quản trị, tiến trình được tạo trên máy đích, script, truy vấn quản trị cơ sở dữ liệu hoặc yêu cầu gửi tới control plane.

Một thao tác nguy hiểm chưa chắc là hành vi ác ý. Xóa dữ liệu tạm trong một đợt bảo trì có thể hợp lệ; cùng loại thao tác trên thư mục dữ liệu chính ngoài phạm vi được duyệt có thể là sự cố nghiêm trọng. Ngược lại, một lệnh nhìn có vẻ bình thường vẫn có thể nguy hiểm khi chạy bằng tài khoản quản trị trên tài nguyên nhạy cảm.

Vì vậy, bộ phát hiện phải trả lời ít nhất năm câu hỏi:

1. Ai yêu cầu và danh tính nào thực sự thực thi?
2. Thao tác nào được yêu cầu, thông qua chương trình hoặc giao thức nào?
3. Tài nguyên nào bị tác động, với phạm vi và quyền hạn ra sao?
4. Thao tác có phù hợp với mục đích, phạm vi và thời gian của phiên được cấp quyền không?
5. Bằng chứng cho thấy mới có ý định, đã thử thực thi, đã bị chặn hay đã tạo ra thay đổi?

Mục tiêu của bài học là thiết kế một cơ chế phát hiện có thể giải thích và kiểm thử, kết nối kết quả với JIT/JEA, vault, giám sát phiên và quy trình ứng phó sự cố. Danh sách từ khóa chỉ là một lớp tín hiệu, không phải mô hình đầy đủ của hoạt động đặc quyền.

## 2. Phân biệt nguy cơ, sai phạm và kết quả thực thi

Ba nhận định sau phải được lưu riêng:

| Nhận định | Câu hỏi | Ví dụ |
| --- | --- | --- |
| Mức nguy hiểm của thao tác | Nếu thành công, thao tác có thể gây hậu quả gì? | Xóa đệ quy một vùng dữ liệu sản xuất |
| Mức phù hợp với quyền được cấp | Thao tác có nằm trong phạm vi được duyệt không? | Ticket chỉ cho phép xóa cache nhưng lệnh nhắm tới dữ liệu nghiệp vụ |
| Kết quả quan sát | Hệ thống biết điều gì đã xảy ra? | Chỉ thấy dòng lệnh, thấy tiến trình khởi chạy hoặc có audit xác nhận thay đổi |

Một cảnh báo “phát hiện ý định xóa dữ liệu” không được diễn giải thành “dữ liệu đã bị xóa”. Tương tự, PAM ghi nhận đã từ chối một yêu cầu không đủ để khẳng định không tồn tại đường truy cập trực tiếp ngoài PAM.

Có thể dùng các trạng thái quan sát nội bộ sau; đây là schema minh họa, không phải enum bắt buộc của một sản phẩm:

- `OBSERVED_INPUT`: thấy nội dung nhập hoặc nội dung script.
- `EXECUTION_ATTEMPT`: nguồn sự kiện cho thấy có yêu cầu hoặc lần thử thực thi.
- `PROCESS_STARTED`: có telemetry xác nhận tiến trình được tạo.
- `DENIED`: một điểm kiểm soát ghi nhận đã từ chối yêu cầu cụ thể.
- `RESULT_REPORTED`: nhận được kết quả từ công cụ hoặc giao thức.
- `EFFECT_CONFIRMED`: nguồn bằng chứng phù hợp xác nhận thay đổi trên tài nguyên.
- `UNKNOWN`: không đủ dữ liệu để kết luận.

Một exit code bằng không chỉ phản ánh quy ước báo kết quả của chương trình được quan sát. Nó không chứng minh mọi tác động mong muốn đều đã xảy ra, cũng không thay thế audit của hệ thống đích. Một exit code khác không cũng không bảo đảm không có thay đổi từng phần.

## 3. Xây dựng dữ liệu đầu vào đáng tin cậy

### 3.1. Kết hợp nhiều nguồn quan sát

| Nguồn | Giá trị cho phát hiện | Giới hạn cần ghi rõ |
| --- | --- | --- |
| PAM gateway hoặc session proxy | Liên kết phiên với người yêu cầu, phê duyệt và tài khoản đích | Khả năng nhìn thấy lệnh phụ thuộc giao thức và cách tích hợp |
| Dữ liệu terminal | Giúp dựng lại những gì người vận hành nhìn thấy hoặc nhập | Phím sửa dòng, giao diện toàn màn hình và output có thể gây nhầm lẫn |
| Audit tiến trình trên host | Thấy executable, đối số, cây tiến trình và danh tính thực thi | Shell builtin, thao tác trong tiến trình và dữ liệu bị cắt có thể thiếu |
| Telemetry của trình thông dịch | Bổ sung nội dung script hoặc cấu trúc lệnh | Phụ thuộc cấu hình, phiên bản và khả năng thu thập |
| Audit cơ sở dữ liệu hoặc control plane | Thấy thao tác ở lớp tài nguyên và kết quả được hệ thống ghi nhận | Cần ánh xạ danh tính, phiên và đối tượng đích |
| Giám sát thay đổi file, quyền, cấu hình | Bổ sung bằng chứng về tác động | Không phải lúc nào cũng chỉ ra người yêu cầu ban đầu |

Không dùng shell history làm nguồn duy nhất. Nó có thể thiếu phiên không tương tác, không phản ánh đầy đủ tiến trình con hoặc không được ghi nhận theo cách đáp ứng yêu cầu bằng chứng của hệ thống.

Với PowerShell, Script Block Logging có thể bổ sung nội dung script được xử lý khi tính năng được bật. Cần phân biệt kênh log của Windows PowerShell và PowerShell hiện đại, kiểm tra đúng phiên bản triển khai và bảo vệ dữ liệu nhạy cảm trong log. Xem [tài liệu logging trên Windows của Microsoft](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_logging_windows) và [chính sách Windows PowerShell](https://learn.microsoft.com/en-us/windows/client-management/mdm/policy-csp-windowspowershell).

### 3.2. Liên kết người yêu cầu với quyền thực thi

Trong một phiên PAM có thể tồn tại nhiều danh tính:

- Người dùng cá nhân đăng nhập vào PAM.
- Tài khoản đích được lấy credential từ vault.
- Danh tính hiệu lực sau khi nâng quyền.
- Danh tính workload hoặc service account thực hiện thao tác tiếp theo.

Không gộp tất cả thành một trường `user`. Một phiên do người dùng cá nhân mở nhưng chạy bằng tài khoản dùng chung vẫn phải giữ được liên kết giữa người yêu cầu, phiên cấp quyền và danh tính hiệu lực. Nếu tiến trình con tách khỏi phiên hoặc một job tiếp tục chạy sau khi phiên đóng, cần nêu rõ phần liên kết nào chắc chắn và phần nào chỉ là suy luận.

### 3.3. Một sự kiện phân tích tối thiểu

Ví dụ dưới đây là dữ liệu tổng hợp để minh họa thiết kế; các trường không đại diện cho một sản phẩm PAM cụ thể.

~~~json
{
  "event_id": "evt-lab-042",
  "event_time": "2026-10-15T03:22:10Z",
  "ingest_time": "2026-10-15T03:22:12Z",
  "pam_session_id": "pam-lab-017",
  "requester_id": "operator-lab",
  "effective_identity": "root",
  "asset_id": "host-lab-03",
  "environment": "training",
  "process": {
    "entity_id": "proc-lab-042",
    "parent_entity_id": "proc-lab-011",
    "executable": "/usr/bin/rm",
    "args": ["rm", "-rf", "--", "/srv/pam-lab/cache"],
    "working_directory": "/srv/pam-lab"
  },
  "observation": {
    "kind": "PROCESS_STARTED",
    "args_truncated": false,
    "redaction_applied": false
  },
  "authorization": {
    "request_id": "req-lab-017",
    "change_id": "CHG-LAB-017",
    "context_status": "RESOLVED"
  }
}
~~~

Dòng đối số trên là mẫu log, không phải hướng dẫn thực thi. Bộ phân tích không được chạy lại lệnh để tìm hiểu tác động của nó.

Nên giữ cả biểu diễn gốc được bảo vệ và biểu diễn phục vụ tìm kiếm theo chính sách dữ liệu. Một schema như ECS phân biệt `process.args` với `process.command_line`, đồng thời có `process.entity_id` để hỗ trợ liên kết tiến trình. Khi ánh xạ sang schema chung, cần giữ thông tin nguồn và những phần đã bị che hoặc cắt. Xem [ECS Process fields](https://www.elastic.co/docs/reference/ecs/ecs-process).

### 3.4. Chất lượng và bảo mật telemetry

Cần theo dõi riêng độ đầy đủ của dữ liệu: đối số bị cắt, thiếu working directory, mất event, lệch đồng hồ, chậm ingest hoặc không xác định được tài khoản hiệu lực. Giá trị thiếu không được tự chuyển thành một giá trị an toàn.

Credential, token hoặc mật khẩu xuất hiện trong command line phải được xử lý như dữ liệu nhạy cảm. Có thể phát hiện “tham số chứa loại bí mật nhạy cảm” mà không đưa giá trị bí mật vào cảnh báo. Nếu cần bảo toàn bản gốc để điều tra, phải giới hạn người đọc, ghi audit truy cập và đặt thời hạn lưu phù hợp. Chỉ tạo hash của log không đủ để bảo đảm tính toàn vẹn nếu kẻ có quyền sửa log cũng có quyền sửa hash.

## 4. Phân tích lệnh trước khi áp rule

### 4.1. Không xem command line là một chuỗi từ khóa đơn giản

Cùng một đoạn văn bản có thể là lệnh được thực thi, đối số dữ liệu, nội dung được in ra hoặc một phần của tài liệu. Ví dụ:

~~~text
printf '%s\n' 'rm -rf /srv/pam-lab/cache'
~~~

Trong ví dụ này, chuỗi có hình dạng lệnh xóa chỉ là dữ liệu được in ra. Một rule tìm từ khóa xóa trên toàn bộ chuỗi có thể tạo cảnh báo sai nếu không phân biệt cấu trúc lệnh.

Theo [Bash Reference Manual về quoting](https://www.gnu.org/software/bash/manual/html_node/Quoting.html), dấu quote làm thay đổi cách shell xử lý ký tự đặc biệt. [Quy trình mở rộng simple command](https://www.gnu.org/software/bash/manual/html_node/Simple-Command-Expansion.html) cũng cho thấy phần văn bản ban đầu không luôn tương đương đối số cuối cùng của chương trình. Vì vậy, bộ phân tích cần hiểu đúng ngôn ngữ nguồn hoặc ghi nhận giới hạn khi không thể phân tích đầy đủ.

### 4.2. Giữ ba lớp biểu diễn

Một thiết kế thực dụng nên có:

1. **Raw observation:** nội dung và metadata mà nguồn đã ghi nhận, có kiểm soát truy cập.
2. **Parsed representation:** executable, đối số, toán tử điều khiển, redirection và cấu trúc script nếu có.
3. **Semantic features:** loại thao tác, phạm vi đích, quyền hiệu lực, độ nhạy cảm và độ chắc chắn.

Không thay thế raw bằng bản đã chuẩn hóa. Khi điều tra, cần giải thích được vì sao parser đã biến dữ liệu nguồn thành một kết luận cụ thể.

Các quy tắc chuẩn hóa phải phụ thuộc nền tảng:

- Không viết thường mọi đường dẫn Unix; chữ hoa và chữ thường có thể phân biệt tài nguyên.
- Không xóa quote và khoảng trắng một cách mù quáng; việc đó có thể đổi ranh giới đối số.
- Không dùng một parser chung cho Bash, PowerShell, SQL và CLI của thiết bị mạng.
- Không suy danh tính executable chỉ từ tên hiển thị; ưu tiên đường dẫn hoặc định danh file do nguồn đáng tin ghi nhận.
- Không giải mã và thực thi script để “xem nó làm gì”. Nếu có bước giải mã phục vụ phân tích tĩnh, phải giới hạn định dạng, kích thước, độ sâu và lưu dấu vết.
- Không coi lỗi parser hoặc timeout là kết luận lệnh an toàn.

### 4.3. Phân biệt giá trị quan sát với giá trị suy ra

Đường dẫn tương đối cần working directory. Biến môi trường cần giá trị trong ngữ cảnh phiên. Wildcard cần trạng thái filesystem ở thời điểm liên quan. Symlink, mount và container namespace có thể làm thay đổi tài nguyên thực tế.

Nếu chỉ thấy một script chứa biến chưa giải được, kết quả hợp lệ là “đích chưa xác định”, không phải tự thay biến bằng giá trị mặc định. Nếu có đối số cuối cùng từ process telemetry thì dùng bằng chứng đó, nhưng vẫn cần thận trọng với symlink, namespace và thời điểm quan sát.

Không truy vấn rồi kết luận trạng thái hiện tại chắc chắn giống trạng thái khi lệnh chạy. Đường dẫn đã được giải tại thời điểm đánh giá vẫn có thể thay đổi trước khi chương trình sử dụng nó. Những rủi ro này làm rõ vì sao việc chặn cần nằm ở điểm kiểm soát có hiểu biết về tài nguyên, không chỉ ở một bộ so khớp chuỗi đứng ngoài.

### 4.4. Wrapper và tiến trình con

Các lớp như nâng quyền, shell lồng nhau, remote execution hoặc script runner có thể che thao tác thực sự trong đối số hoặc tiến trình con. Bộ phát hiện cần liên kết các sự kiện theo cây tiến trình và phiên, thay vì xem lệnh wrapper là toàn bộ hành vi.

Chỉ mở các lớp wrapper mà parser hiểu rõ. Đặt giới hạn độ sâu và độ dài để tránh làm quá tải dịch vụ phân tích. Với lớp không hỗ trợ, lưu `parse_status=PARTIAL` hoặc `UNSUPPORTED`, nêu phần chưa hiểu và tiếp tục thu thập telemetry bổ sung.

## 5. Các nhóm thao tác nguy hiểm cần nhận diện

Phân loại theo tác động giúp xây dựng rule ít phụ thuộc vào tên một công cụ.

| Nhóm hành vi | Đặc điểm cần trích xuất | Ngữ cảnh làm tăng mức ưu tiên |
| --- | --- | --- |
| Hủy hoặc ghi đè dữ liệu | Xóa, truncate, ghi thẳng vào thiết bị, thao tác diện rộng | Dữ liệu sản xuất, backup, nhiều mục tiêu, quyền cao |
| Thay đổi quyền truy cập | ACL, owner, role, group hoặc policy mới | Mở rộng quyền quản trị, thay đổi ngoài phạm vi JEA |
| Làm suy yếu giám sát | Thay cấu hình audit, dừng collector, tác động kho log | Không có bảo trì hợp lệ, trùng thời điểm hành vi khác |
| Làm gián đoạn dịch vụ | Dừng, restart, reboot hoặc đổi cấu hình trọng yếu | Dịch vụ quan trọng, chưa có failover, ngoài cửa sổ duyệt |
| Tiếp cận bí mật | Đọc hoặc xuất credential, key, secret | Đích không thuộc nhiệm vụ, số lượng lớn, đường ra bất thường |
| Mở rộng ảnh hưởng | Thao tác trên nhiều host, cluster hoặc tài khoản | Phạm vi lớn hơn request, quyền liên môi trường |
| Thực thi nội dung chưa kiểm soát | Script hoặc chương trình không thuộc baseline tin cậy | Quyền đặc biệt, nguồn không được xác nhận, thiếu provenance |

Một công cụ có thể xuất hiện trong nhiều nhóm. Một CLI quản trị có thể đọc trạng thái, thay quyền hoặc xóa tài nguyên tùy subcommand, tham số, cấu hình và endpoint đang dùng. Cùng một tên lệnh không đủ để suy ra tác động.

Một số thao tác “chỉ đọc” vẫn nhạy cảm, chẳng hạn xuất nhiều secret hoặc đọc thông tin xác thực. Ngược lại, một thao tác ghi nhỏ trong môi trường thử nghiệm có thể có mức tác động thấp. Bộ phát hiện cần phân biệt tính toàn vẹn, tính sẵn sàng và tính bí mật của tài nguyên.

## 6. Thiết kế rule theo nhiều lớp

### 6.1. Lớp nhận diện thao tác

Lớp đầu xác định hành vi và các tham số quan trọng:

- Họ công cụ hoặc executable.
- Subcommand hoặc loại câu lệnh.
- Cờ làm thay đổi phạm vi, như đệ quy hoặc chọn tất cả.
- Đối tượng đích và các đối tượng phụ.
- Các toán tử nối lệnh, chuyển output hoặc redirection.
- Nội dung script được quan sát, nếu có.

Regex hữu ích để tìm ứng viên hoặc nhận diện mẫu đơn giản trong một nguồn đã xác định. Nó không thay thế parser khi rule cần hiểu ranh giới đối số, quoting hoặc thứ tự thực thi. Nếu dùng regex, cần giới hạn kích thước đầu vào và tránh biểu thức có chi phí xử lý khó kiểm soát.

### 6.2. Lớp rủi ro của tài nguyên

Đối chiếu đích với inventory và nhãn tài sản:

- Môi trường sản xuất hay thử nghiệm.
- Loại dữ liệu và mức quan trọng.
- Host, database, namespace hoặc tenant thực sự.
- Phạm vi tác động, từ một đối tượng tới toàn cụm.
- Khả năng phục hồi và trạng thái bảo vệ liên quan.

Một nhãn thiếu hoặc quá cũ làm giảm độ chắc chắn. Không được tự kết luận “không phải production” chỉ vì không tìm được nhãn production.

Với CLI có context mặc định, đích phải bao gồm cả context được sử dụng khi thực thi. Tên namespace giống nhau ở hai cluster không đại diện cho cùng tài nguyên. Một rule chỉ nhìn đối số namespace mà bỏ qua cluster có thể cho phép nhầm phạm vi.

### 6.3. Lớp quyền được cấp

Không chỉ kiểm tra có ticket hay không. Phải kiểm tra ticket hoặc request có ràng buộc đúng:

- Người yêu cầu và tài khoản thực thi.
- Tài sản, môi trường và đối tượng đích.
- Loại thao tác được cho phép.
- Khoảng thời gian hiệu lực.
- Điều kiện phê duyệt bổ sung.
- Phiên hoặc workload nhận quyền.

Ví dụ: request cho phép dọn cache trong `/srv/pam-lab/cache` không cho phép xóa dữ liệu nghiệp vụ ở thư mục khác. Khi so khớp đường dẫn, dùng quan hệ thành phần đường dẫn sau khi chuẩn hóa phù hợp; kiểm tra prefix chuỗi có thể nhận nhầm một đường dẫn như `/srv/pam-lab/cache-archive`.

Thông tin phê duyệt phải đến từ hệ thống có thẩm quyền. Một dòng comment do người thực thi nhập có chứa mã ticket không đủ để chứng minh lệnh nằm trong phạm vi được duyệt.

### 6.4. Lớp tương quan

Một sự kiện đơn lẻ có thể chưa đủ. Ví dụ chuỗi quan sát giả lập:

~~~text
T0: phiên JIT được mở để đọc trạng thái dịch vụ
T1: xuất hiện yêu cầu thay đổi cấu hình audit
T2: xuất hiện thao tác thay đổi quyền trên dữ liệu nhạy cảm
T3: xuất hiện thao tác xóa ngoài phạm vi request
~~~

Tương quan chuỗi này có thể nâng ưu tiên điều tra. Tuy nhiên, cần dùng thời gian sự kiện, giới hạn trễ ingest và độ tin cậy của liên kết phiên. Hai sự kiện gần nhau theo thời gian không tự chứng minh có quan hệ nhân quả.

Tương quan cần ràng buộc theo định danh phù hợp: cùng phiên, cùng tiến trình hoặc quan hệ cha con, cùng danh tính và tài sản. Với job chạy từ xa, có thể cần correlation ID hoặc audit từ hệ thống đích; không chỉ dựa vào tên người dùng phổ biến.

### 6.5. Lớp bất thường

Baseline hỗ trợ phát hiện hoạt động hiếm gặp: công cụ mới, đích mới, số lượng tài sản tăng mạnh hoặc thao tác không phù hợp vai trò. Đây là tín hiệu bổ sung. Tính hiếm gặp không đồng nghĩa nguy hiểm, và một hành vi xuất hiện thường xuyên không tự trở thành hợp lệ.

Không dùng mô hình bất thường để bỏ qua các rule bảo vệ tài nguyên trọng yếu. Dữ liệu huấn luyện cần tránh coi hành vi sai đã tồn tại lâu là hoạt động chuẩn.

## 7. Một rule minh họa có thể giải thích

Schema dưới đây là thiết kế giả lập để diễn đạt ý tưởng. Nó không phải cấu hình có thể nhập trực tiếp vào SIEM hay PAM.

~~~yaml
rule:
  id: PAM-DANGER-DELETE-OUTSIDE-SCOPE
  version: 1
  purpose: Phát hiện xóa có phạm vi rộng ngoài quyền được cấp
  required_evidence:
    - operation_class
    - effective_identity
    - resolved_asset
    - target_scope
    - authorization_scope
  match:
    operation_class: destructive_delete
    elevated_execution: true
    target_criticality: high
    authorization_scope_match: false
  unknown_handling:
    missing_target: review_with_incomplete_context
    missing_authorization: review_with_incomplete_context
    partial_parse: request_additional_telemetry
  result:
    severity: high
    confidence: derived_from_evidence
    response: alert_and_require_review
  lifecycle:
    owner: pam-detection-team
    exceptions_require_expiry: true
~~~

Rule phải kèm test cho cả điều kiện match và điều kiện không đủ dữ liệu. Có thể diễn đạt luồng quyết định như sau:

~~~text
Nếu không xác định được loại thao tác:
    trả về NEEDS_CONTEXT và các trường còn thiếu

Nếu thao tác không thuộc nhóm cần rule này bảo vệ:
    trả về NO_MATCH_FOR_THIS_RULE

Nếu đích, quyền hiệu lực hoặc quyền được cấp chưa rõ:
    trả về NEEDS_CONTEXT; không tự gán là được phép

Nếu thao tác nguy hiểm trên tài nguyên quan trọng, ngoài phạm vi:
    tạo finding kèm bằng chứng và phiên bản rule

Nếu thao tác nằm trong ngoại lệ hợp lệ, đúng phạm vi và còn hạn:
    ghi nhận EXCEPTION_APPLIED cùng ngoại lệ được sử dụng

Nếu không thỏa điều kiện còn lại:
    trả về NO_MATCH_FOR_THIS_RULE
~~~

`NO_MATCH_FOR_THIS_RULE` chỉ có nghĩa rule này không khớp. Nó không phải kết luận toàn bộ hoạt động an toàn. Các rule khác vẫn có thể phát hiện vi phạm khác trên cùng sự kiện.

Trong hệ thống thực tế, nên tách hai quyết định: kết quả phân tích và hành động kiểm soát. Một trường `NEEDS_CONTEXT` có thể tạo cảnh báo hoặc yêu cầu phê duyệt; việc từ chối thực thi khi thiếu context phụ thuộc chính sách đã được xác định trước và khả năng của điểm kiểm soát.

## 8. Severity, confidence và bằng chứng giải thích

Severity mô tả mức tác động tiềm tàng; confidence mô tả mức chắc chắn của kết luận. Không gộp chúng thành một con số không giải thích được.

| Tình huống | Severity dự kiến | Confidence dự kiến | Cách xử lý hợp lý |
| --- | --- | --- | --- |
| Xóa dữ liệu trọng yếu, đủ đối số và audit đích | Cao | Cao | Ưu tiên điều tra, kiểm tra tác động và áp dụng playbook |
| Có mẫu xóa nhưng đối số bị cắt | Có thể cao | Thấp hoặc trung bình | Thu thập bổ sung, ghi rõ phần chưa biết |
| Xóa cache đúng phạm vi đã duyệt | Tùy tài nguyên | Cao về nhận định phạm vi | Ghi nhận hoạt động và ngoại lệ nếu có |
| Chỉ thấy chuỗi nguy hiểm trong output tài liệu | Thấp đối với rule thực thi | Cao nếu parser phân biệt được | Không gán nhầm là lệnh đã chạy |
| Không hiểu script chạy bằng quyền quản trị | Chưa xác định đầy đủ | Thấp | Đánh dấu thiếu khả năng quan sát, áp chính sách phù hợp |

Nếu dùng điểm số để xếp hàng cảnh báo, hãy gọi đó là điểm ưu tiên nội bộ. Không diễn giải điểm 80 thành xác suất 80% có tấn công nếu chưa có mô hình xác suất được hiệu chỉnh và đánh giá tương ứng.

Một finding tốt cần cho người xử lý thấy:

- Rule và phiên bản đã khớp.
- Phiên, người yêu cầu và danh tính hiệu lực.
- Tài sản và đối tượng được suy ra, kèm độ chắc chắn.
- Nhóm thao tác và tham số gây rủi ro.
- Phạm vi quyền được cấp và điểm không khớp.
- Các event nguồn liên quan.
- Trạng thái thực thi quan sát được.
- Dữ liệu còn thiếu và hành động được đề xuất.

Ví dụ giải thích: “Phát hiện thao tác xóa đệ quy do tài khoản hiệu lực root thực hiện trên tài sản được gắn nhãn quan trọng. Đích quan sát không nằm trong phạm vi dọn cache của request. Nguồn hiện tại xác nhận tiến trình đã khởi chạy; chưa có bằng chứng xác nhận kết quả xóa.”

Cách mô tả này cụ thể hơn “lệnh độc hại” và giúp người trực phân biệt điều đã biết với điều còn phải xác minh.

## 9. Đặt phát hiện vào đúng vị trí của PAM

### 9.1. Phát hiện sau sự kiện và kiểm soát trước thực thi

Phân tích log thường diễn ra sau khi lệnh được yêu cầu hoặc chạy. Nó hỗ trợ cảnh báo, điều tra và đánh giá tác động. Không gọi cơ chế này là ngăn chặn trước thực thi nếu không có điểm kiểm soát thực sự nằm trước thao tác.

Chặn trước thực thi chỉ đáng tin khi hệ thống có khả năng can thiệp ở lớp phù hợp: cơ chế cấp quyền giới hạn thao tác, endpoint quản trị được ràng buộc, gateway hiểu giao thức hoặc API kiểm soát tài nguyên. Chặn một chuỗi trong terminal không tự bao phủ script, chương trình nhị phân, GUI và mọi đường truy cập khác.

JEA và least privilege giảm tập thao tác mà tài khoản có thể thực hiện. JIT giới hạn thời gian quyền có hiệu lực. Dangerous command detection bổ sung khả năng nhìn thấy và phản ứng; nó không thay thế việc thiết kế quyền tối thiểu.

### 9.2. Chọn phản ứng theo tác động và độ chắc chắn

Có thể phân cấp phản ứng:

1. Ghi nhận có cấu trúc để phục vụ điều tra.
2. Gửi cảnh báo có ưu tiên và liên kết bằng chứng.
3. Yêu cầu xác nhận hoặc phê duyệt bổ sung tại điểm kiểm soát hỗ trợ.
4. Từ chối thao tác cụ thể theo chính sách đã được kiểm thử.
5. Thu hồi quyền cấp mới, đóng phiên hoặc cô lập theo playbook được phép.

Không mặc định đóng mọi phiên ngay khi thấy từ khóa rủi ro. Ngắt một thao tác bảo trì đang chạy có thể tạo trạng thái dở dang. Ngược lại, với một thao tác phá hủy rõ ràng trên tài nguyên trọng yếu, chờ xử lý thủ công có thể không đáp ứng mục tiêu bảo vệ. Quyết định phải được thiết kế trước cho từng lớp tài nguyên và năng lực kiểm soát.

Đóng phiên không bảo đảm tiến trình con đã dừng. Thu hồi checkout từ vault không bảo đảm credential đã được thay đổi hoặc token đã bị vô hiệu hóa trên hệ thống đích. Playbook phải xác minh riêng trạng thái phiên, credential, quyền JIT và hoạt động đang tiếp tục.

### 9.3. Quy trình điều tra một finding

Người xử lý trước tiên xác minh dữ liệu nguồn và phạm vi cảnh báo, sau đó đối chiếu request với chủ sở hữu tài sản hoặc người phê duyệt qua kênh có thẩm quyền. Tiếp theo, kiểm tra audit đích để xác định thay đổi, ảnh hưởng và đường truy cập liên quan.

Các kết luận có thể là hoạt động hợp lệ, vi phạm quy trình, lỗi thao tác, hành vi đáng ngờ hoặc chưa đủ bằng chứng. Không ép mọi cảnh báo vào hai nhãn “tấn công” và “an toàn”. Lưu lý do kết luận, event tham chiếu và những hành động đã thực hiện để phục vụ kiểm toán và điều chỉnh rule.

## 10. Quản lý ngoại lệ và giảm cảnh báo sai

Ngoại lệ cần hẹp và có thời hạn. Một ngoại lệ cho bảo trì nên ràng buộc theo tài khoản hoặc workload, tài sản, đường dẫn hoặc loại tài nguyên, thao tác, thời gian và request có thẩm quyền.

Không dùng các ngoại lệ quá rộng như “bỏ qua mọi lệnh của nhóm quản trị” hoặc “bỏ qua mọi lệnh trong giờ bảo trì”. Tài khoản hợp lệ có thể bị chiếm dụng; hoạt động hợp lệ trên một tài sản không cho phép mở rộng sang toàn bộ hạ tầng.

Khi ngoại lệ khớp, hệ thống vẫn nên lưu hoạt động và mã ngoại lệ đã dùng. Có thể giảm thông báo cho người trực theo chính sách, nhưng không xóa bằng chứng chỉ vì hoạt động được duyệt.

Nếu phát sinh nhiều false positive, cần tìm nguyên nhân trước khi nới rule:

- Parser đang nhận nhầm dữ liệu được in ra thành lệnh.
- Không có context đích hoặc inventory chưa cập nhật.
- Mô hình phê duyệt không biểu đạt được thao tác thực tế.
- Workflow tự động hợp lệ chưa có danh tính và provenance rõ ràng.
- Rule nhận diện đúng nguy cơ nhưng phản ứng đang quá mạnh.

Điều chỉnh parser, context hoặc workflow thường chính xác hơn việc thêm tên công cụ vào allowlist toàn cục.

## 11. Kiểm thử bằng dữ liệu tổng hợp và replay

Bộ test nên chứa positive, negative, trường hợp thiếu dữ liệu và những biến thể cấu trúc. Không cần thực thi lệnh phá hủy để chứng minh rule nhận diện được một mẫu log.

| Mã | Dữ liệu hoặc tình huống tổng hợp | Kết quả mong đợi |
| --- | --- | --- |
| T01 | Thao tác xóa đệ quy ngoài phạm vi request trên tài nguyên quan trọng | Rule khớp, nêu rõ điểm không khớp |
| T02 | Dọn cache đúng tài sản, đúng phạm vi và thời gian | Ghi nhận hoạt động hợp lệ theo chính sách |
| T03 | Chuỗi có hình dạng lệnh xóa nằm trong dữ liệu của lệnh in | Không coi là thực thi thao tác xóa |
| T04 | Tên công cụ có đường dẫn đầy đủ, cờ thay đổi thứ tự nhưng cùng nghĩa | Nhận diện nhất quán nếu parser hỗ trợ |
| T05 | Thao tác đi qua wrapper nâng quyền và tiến trình con | Giữ liên kết phiên, nhận diện lớp được hỗ trợ |
| T06 | Đích chứa biến chưa giải được, thiếu đối số sau mở rộng | NEEDS_CONTEXT, không tự cho phép |
| T07 | Đối số bị cắt hoặc event thiếu working directory cần thiết | Giảm confidence, nêu dữ liệu thiếu |
| T08 | Ngoại lệ đúng thao tác nhưng đã hết hạn | Không áp dụng ngoại lệ |
| T09 | Cùng namespace nhưng khác cluster được duyệt | Không kết luận cùng phạm vi |
| T10 | Event trùng được gửi lại | Không tạo nhiều incident giống nhau, vẫn giữ dấu ingest cần thiết |
| T11 | Telemetry báo DENIED tại một điểm kiểm soát | Không khẳng định đã thực thi hoặc đã có tác động |
| T12 | Có bằng chứng tiến trình khởi chạy nhưng chưa có audit đích | Giữ trạng thái PROCESS_STARTED |
| T13 | Script không phân tích được vì lỗi cú pháp hoặc giới hạn parser | Trả về trạng thái chưa phân tích đầy đủ |
| T14 | Đường dẫn gần giống prefix được phép nhưng thuộc thư mục khác | Không áp dụng ngoại lệ theo prefix chuỗi |
| T15 | Request hợp lệ nhưng tài khoản hiệu lực khác ràng buộc | Báo sai phạm vi danh tính |
| T16 | Mất heartbeat collector khi vẫn có phiên đặc quyền | Phát sinh tín hiệu thiếu quan sát riêng |

Mỗi test lưu input, context, phiên bản parser, rule và expected result. Kiểm thử cả explanation, không chỉ nhãn match: một rule khớp vì lý do sai vẫn có thể tạo kết quả trông đúng trong bộ dữ liệu nhỏ.

Replay lịch sử giúp đánh giá khối lượng cảnh báo dự kiến, nhưng dữ liệu không có nhãn đầy đủ chỉ cho biết hành vi rule trên tập đã quan sát. Nó không tự chứng minh recall đối với toàn bộ hành vi nguy hiểm có thể xảy ra.

Để thử cơ chế chặn, dùng môi trường lab riêng, tài nguyên giả lập và thao tác vô hại được thiết kế để đi qua đúng luồng kiểm soát. Kiểm tra cả việc chỉ chặn thao tác dự định và việc không làm gián đoạn các thao tác khác trong phiên.

## 12. Chỉ số vận hành và triển khai dần

Các chỉ số nên giúp phân biệt hiệu quả phát hiện với chất lượng dữ liệu:

| Chỉ số | Ý nghĩa | Điểm dễ hiểu nhầm |
| --- | --- | --- |
| Coverage telemetry | Phần phiên hoặc tài sản trong phạm vi có dữ liệu yêu cầu | Có log đăng nhập không đồng nghĩa có đủ log lệnh |
| Parse success và partial rate | Mức dữ liệu được phân tích đủ cấu trúc | Tăng success bằng cách bỏ qua lỗi có thể che điểm mù |
| Context resolution rate | Phần sự kiện ánh xạ được đích, quyền và request | Context được gán nhưng sai không phải thành công |
| Precision trên tập đã đánh giá | Tỷ lệ finding đúng theo tiêu chí đã định trong tập đó | Không đại diện tự động cho mọi tài sản và thời kỳ |
| Độ bao phủ test hành vi | Những nhóm rủi ro đã có test và kết quả mong đợi | Không gọi đây là recall toàn hệ thống |
| Độ trễ phát hiện | Thời gian từ sự kiện đến finding theo định nghĩa đã chọn | Cần tách trễ nguồn, ingest và xử lý |
| Tỷ lệ ngoại lệ và ngoại lệ hết hạn | Mức phụ thuộc vào ngoại lệ, khả năng quản trị | Ngoại lệ nhiều có thể che thiết kế rule chưa phù hợp |
| Chất lượng phản ứng | Thời gian xử lý, quyết định đúng và tác động phụ | Giảm số cảnh báo chưa chắc giảm rủi ro |

Triển khai thường bắt đầu bằng chế độ chỉ quan sát trên một tập tài sản có owner rõ ràng. Sau khi kiểm tra dữ liệu, test và tải vận hành, có thể bật cảnh báo có ưu tiên. Việc bật phản ứng tự động cần được thử riêng với đường rollback, điểm dừng và trách nhiệm xử lý cụ thể.

Mỗi thay đổi rule nên có version, người sở hữu, lý do và bằng chứng test. Có thể triển khai giới hạn trên một nhóm trước khi mở rộng. Nếu parser mới làm tăng mạnh trạng thái thiếu dữ liệu hoặc phát sinh chặn sai, cần quay lại phiên bản đã kiểm thử và bảo toàn sự kiện để phân tích.

Khi collector hoặc hệ thống context không hoạt động, quyết định tiếp tục hay từ chối cấp quyền phải theo chính sách sẵn có cho từng loại tài nguyên. Tạo cảnh báo sức khỏe riêng; không để lỗi hạ tầng biến thành việc mọi lệnh đều được kết luận an toàn.

## 13. Bài tập áp dụng

Một nhóm vận hành được cấp phiên JIT để dọn cache trên một host thử nghiệm. Request ràng buộc một tài khoản đích, một thư mục và thời gian hiệu lực cụ thể. Bộ phát hiện nhận được ba sự kiện:

1. Một tiến trình thực hiện xóa trong thư mục cache được duyệt.
2. Một tiến trình thực hiện xóa ở thư mục khác; đối số đầy đủ nhưng chưa có kết quả audit đích.
3. Một dòng output chứa ví dụ về lệnh xóa, không có event thực thi tương ứng.

Hãy thiết kế kết quả riêng cho từng sự kiện, gồm trạng thái quan sát, phạm vi quyền, severity, confidence, explanation và hành động. Sau đó thêm biến thể: request đã hết hạn, thiếu working directory hoặc tài khoản hiệu lực không trùng tài khoản được duyệt.

Kết quả hợp lý cần thể hiện được rằng sự kiện thứ nhất có thể phù hợp phạm vi; sự kiện thứ hai cần cảnh báo về thao tác ngoài phạm vi nhưng chưa được kết luận dữ liệu đã mất; sự kiện thứ ba không đủ cơ sở để gán thành thao tác xóa đã thực thi. Các biến thể thiếu dữ liệu phải nêu rõ điều chưa biết thay vì ngầm chuyển thành cho phép.

## 14. Những nguyên tắc cần giữ

Dangerous command detection có giá trị khi kết nối được cấu trúc thao tác, tài nguyên, quyền được cấp và bằng chứng thực thi. Thiết kế tốt giữ nguyên dữ liệu nguồn có bảo vệ, không đánh đồng từ khóa với hành vi, không đánh đồng quyền quản trị với quyền làm mọi việc và không đánh đồng cảnh báo với kết quả đã được xác nhận.

Trong PAM, cơ chế này hoạt động cùng inventory quyền, least privilege, JIT/JEA, vault và audit. Phát hiện giúp nhìn thấy sai lệch; kiểm soát quyền làm giảm khả năng gây tác động; bằng chứng từ hệ thống đích giúp xác minh điều thực sự đã xảy ra.
