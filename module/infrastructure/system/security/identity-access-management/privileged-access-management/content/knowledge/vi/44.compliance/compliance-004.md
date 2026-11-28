# Command audit evidence — Bằng chứng kiểm toán lệnh đặc quyền

## 1. Bài toán: chứng minh điều đã xảy ra trong một phiên PAM

Một kỹ sư được cấp quyền JIT để khởi động lại dịch vụ thanh toán trên máy chủ sản xuất. Sau phiên làm việc, hệ thống PAM có bản ghi đăng nhập thành công và một video terminal. Tuy nhiên, kiểm toán viên vẫn cần biết lệnh nào thực sự được thực thi, ai chịu trách nhiệm, lệnh có nằm trong phạm vi được duyệt không và kết quả quan sát được là gì.

**Command audit evidence** là tập bằng chứng cho phép tái dựng, đối chiếu và đánh giá các thao tác bằng lệnh trong một phạm vi xác định. Tập bằng chứng thường kết hợp bản ghi PAM, quyết định cấp quyền, sự kiện trên máy đích và dữ liệu bảo vệ tính toàn vẹn. Nó phải gắn hành động với danh tính và bối cảnh, thay vì chỉ đưa ra một danh sách chuỗi lệnh.

Trong module quản lý truy cập đặc quyền, bằng chứng lệnh phục vụ hai nhu cầu liên quan nhưng khác nhau:

- Kiểm toán đánh giá việc thực hiện các kiểm soát như least privilege, JIT/JEA, phê duyệt và giám sát phiên.
- Ứng phó sự cố xác định phạm vi hành động, tài khoản bị lạm dụng, tài sản chịu ảnh hưởng và những khoảng trống chưa thể kết luận.

Có bằng chứng một lệnh được chạy không đồng nghĩa lệnh được phép chạy. Một phiên được phê duyệt cũng không làm cho mọi thao tác trong phiên tự động hợp lệ.

### Mục tiêu học tập

Sau bài học, người học có thể thiết kế tập bằng chứng cho một thao tác đặc quyền; phân biệt dữ liệu nhập, quyết định cho phép, thực thi và tác động; nối sự kiện giữa PAM với máy đích; bảo vệ, xuất và giải thích bằng chứng mà không khẳng định vượt quá dữ liệu.

## 2. Phân biệt log, bản ghi phiên và bằng chứng lệnh

| Nguồn dữ liệu | Điều có thể quan sát | Giới hạn cần nêu |
|---|---|---|
| Shell history | Một số chuỗi lệnh được shell lưu | Có thể thiếu, bị sửa, không có người thực hiện đáng tin cậy hoặc kết quả |
| Terminal input | Ký tự nhập hoặc dán vào terminal | Ký tự nhập chưa chắc được thực thi; có phím sửa, hủy hoặc ứng dụng tương tác |
| Terminal output hoặc video | Nội dung terminal hiển thị trong phiên | Không tự chứng minh đầy đủ process, thao tác không tương tác hay thay đổi ở đích |
| PAM authorization event | Quyết định cho phép hoặc từ chối truy cập | Không tự chứng minh lệnh đã chạy trên máy đích |
| Privilege elevation event | Việc yêu cầu hoặc sử dụng cơ chế nâng quyền | Có thể chỉ ghi lệnh khởi đầu như shell, chưa bao phủ các lệnh bên trong |
| Process execution event | Việc thực thi chương trình theo khả năng nguồn ghi | Không nhất thiết có exit code, toàn bộ output hoặc kết quả nghiệp vụ |
| Application/API audit event | Thao tác được ứng dụng hoặc dịch vụ tiếp nhận/xử lý | Phải hiểu ngữ nghĩa trạng thái, quyền thực tế và request ID của ứng dụng |
| Evidence package | Các nguồn đã được tổ chức, liên kết và bảo vệ để kiểm tra | Chất lượng phụ thuộc nguồn, phạm vi thu thập và cách bảo quản |

Không nên lấy shell history làm nguồn bằng chứng duy nhất cho thao tác đặc quyền. Nó có thể hữu ích để định hướng điều tra, nhưng không thay thế một đường thu thập được quản trị và kiểm tra.

Một gói bằng chứng tốt giữ được cả sự kiện thô và cách diễn giải. Nếu hệ thống chuẩn hóa `root` thành một trường `effective_identity`, người kiểm tra vẫn cần truy về bản ghi nguồn để biết giá trị đó đến từ đâu.

## 3. Sáu câu hỏi cần trả lời cho mỗi hành động

### 3.1. Ai khởi tạo và ai thực thi?

Phân biệt ít nhất ba danh tính:

1. **Initiating identity:** người hoặc workload yêu cầu thao tác.
2. **Session/connection identity:** tài khoản dùng để kết nối đến tài sản.
3. **Effective identity:** danh tính và quyền mà tiến trình hoặc API sử dụng khi hành động.

Ví dụ, nhân viên `user-1042` đăng nhập PAM, kết nối tới máy đích bằng tài khoản quản trị do vault quản lý, rồi chạy công cụ dưới quyền `root`. Chỉ ghi `root` sẽ làm mất thông tin người khởi tạo.

Với CI/CD, người bấm chạy pipeline, workload identity của runner và tài khoản triển khai trên đích cũng có thể khác nhau. Không gán toàn bộ hành động của service account cho một người chỉ vì người đó là owner của tài khoản.

### 3.2. Làm gì và trên đối tượng nào?

Cần mô tả thao tác và tài sản: host ID ổn định, môi trường, chương trình thực thi, tham số đã được xử lý theo chính sách bảo mật, thư mục làm việc hoặc đối tượng API.

Tên hiển thị có thể đổi. Hostname và địa chỉ IP có thể được tái sử dụng. Khi có thể, giữ thêm định danh tài sản từ inventory hoặc nền tảng quản lý để tránh nối nhầm máy.

### 3.3. Khi nào?

Ghi thời gian phát sinh tại nguồn và thời gian collector tiếp nhận. Giữ múi giờ hoặc chuẩn hóa về UTC, nhưng vẫn lưu khả năng truy về timestamp ban đầu.

Một timestamp có nhiều chữ số thập phân không bảo đảm đồng hồ chính xác. Cần biết nguồn thời gian, mức lệch đã quan sát và sự kiện xảy ra khi mất đồng bộ.

### 3.4. Theo thẩm quyền nào?

Liên kết với request ID, ticket thay đổi hoặc sự cố, người phê duyệt, thời hạn JIT, tài sản được duyệt, vai trò và phiên bản policy tại thời điểm quyết định.

Policy hiện tại không đủ để giải thích một quyết định trong quá khứ. Phải giữ policy version hoặc snapshot có thể truy xuất của quyết định cũ.

### 3.5. Kết quả nào được quan sát?

Tách bốn mốc:

- `requested`: thao tác được yêu cầu.
- `authorized/denied`: cơ chế kiểm soát quyết định cho phép hoặc từ chối.
- `executed/completed`: nguồn quan sát xác nhận một giai đoạn thực thi.
- `effect_verified`: có phép kiểm tra độc lập cho tác động mong đợi.

Không phải nguồn nào cũng cung cấp đủ bốn mốc. Một sự kiện thực thi thành công ở tầng hệ điều hành không tự cho biết dịch vụ đã khỏe. Một request API được chấp nhận cũng có thể khởi động công việc bất đồng bộ chưa hoàn thành.

### 3.6. Dựa vào bằng chứng nào?

Mỗi kết luận cần có source event ID, artifact reference hoặc vị trí bản ghi thô. Nếu chỉ có câu tóm tắt do người vận hành nhập sau phiên, hãy ghi rõ đây là lời khai hoặc ghi chú, không biến nó thành quan sát tự động.

## 4. Thiết kế đường thu thập bằng chứng

Một kiến trúc minh họa có các quan hệ sau:

~~~mermaid
flowchart LR
    I[Danh tính và xác thực] --> P[Quyết định PAM và JIT]
    P --> S[Phiên kết nối và nâng quyền]
    S --> T[Sự kiện thực thi tại đích]
    P --> C[Thu thập và tương quan]
    S --> C
    T --> C
    C --> E[Kho bằng chứng có bảo vệ]
    E --> R[Rà soát và xuất hồ sơ]
~~~

Sơ đồ thể hiện quan hệ logic, không hàm ý PAM luôn nhìn thấy mọi thao tác trên máy đích. Đường truy cập trực tiếp, console hạ tầng, tác vụ định kỳ, agent triển khai hoặc API quản trị có thể đi ngoài phiên terminal.

Cần xác định ranh giới thu thập:

| Lớp | Ví dụ bằng chứng | Câu hỏi đối chiếu |
|---|---|---|
| Identity | Subject ID, kết quả xác thực, yếu tố xác thực đã dùng | Ai được hệ thống nhận diện tại thời điểm đó? |
| Authorization | Request, quyết định, policy version, phạm vi JIT/JEA | Quyền nào được cấp, cho mục đích và khoảng thời gian nào? |
| Session | Session ID, gateway, tài khoản đích, thời điểm mở/đóng | Kết nối nào được môi giới và ghi lại? |
| Execution | Process event, sự kiện nâng quyền, audit ứng dụng | Hành động nào được nguồn tại đích quan sát? |
| Result | Exit observation, job state, kiểm tra dịch vụ | Kết quả được xác nhận đến mức nào? |
| Preservation | Collector receipt, manifest, dấu kiểm toàn vẹn, access log | Bản ghi được giữ và cung cấp như thế nào? |

Tách quyền quản trị máy đích khỏi quyền sửa hoặc xóa kho bằng chứng giúp giảm rủi ro một người vừa thực hiện thao tác vừa tự xóa dấu vết. Đồng thời phải giám sát tài khoản quản trị collector, kho lưu trữ và khóa bảo vệ bằng chứng.

## 5. Mô hình dữ liệu cho một hành động lệnh

Đoạn JSON dưới đây là **schema minh họa**, không phải định dạng chuẩn của PAM, sudo hay một sản phẩm cụ thể. Mọi giá trị đều là dữ liệu giả. Các trường `null` là thông tin chưa quan sát được, không phải bằng chứng rằng sự kiện không xảy ra.

~~~json
{
  "schema_version": "example-1",
  "event_id": "command-018",
  "action_id": "action-044",
  "event_type": "privileged_command_observation",
  "occurred_at": "2026-11-20T03:15:12.420Z",
  "received_at": "2026-11-20T03:15:13.080Z",
  "source": {
    "type": "endpoint_process_audit",
    "source_event_id": "host17:boot8:88210",
    "asset_id": "asset-prod-017",
    "collector_id": "collector-02"
  },
  "identity": {
    "initiating_subject_id": "user-1042",
    "connection_account_id": "account-admin-17",
    "effective_identity": "root",
    "attribution_method": "explicit_session_mapping"
  },
  "authorization": {
    "request_id": "req-730",
    "approval_id": "approval-510",
    "change_ticket_id": "CHG-824",
    "policy_version": "pam-prod-v17",
    "decision": "allow",
    "valid_from": "2026-11-20T03:00:00Z",
    "valid_until": "2026-11-20T03:30:00Z"
  },
  "execution": {
    "pam_session_id": "session-91",
    "host_session_id": "hostsession-408",
    "process_instance_id": "asset-prod-017:boot8:6120:03:15:12.420",
    "executable": "/usr/bin/systemctl",
    "arguments": ["restart", "settlement-demo.service"],
    "working_directory": "/srv/operations",
    "process_start_observed": true,
    "completion_observed": false,
    "exit_code": null
  },
  "evidence": {
    "raw_event_ref": "evidence://case-44/raw/endpoint-88210",
    "recording_ref": "evidence://case-44/session-91",
    "recording_offset_ms": 912420,
    "coverage": "process_start_only",
    "redaction_profile": "command-args-v3"
  }
}
~~~

Bản ghi trên chỉ hỗ trợ kết luận rằng một nguồn tại đích quan sát việc thực thi chương trình và hệ thống có mapping rõ tới phiên PAM. Nó chưa chứng minh lệnh hoàn tất hoặc dịch vụ hoạt động đúng.

Nếu có quan sát kết thúc, nên thêm sự kiện kết quả với cùng `action_id`, nguồn và thời gian riêng. Tránh ghi đè bản ghi ban đầu để biến thông tin chưa biết thành đã biết mà không để lại lịch sử.

Một số lưu ý thiết kế:

- `event_id` định danh bản ghi; `action_id` nối các quan sát của cùng hành động. Hai khái niệm không nên bị trộn lẫn.
- PID có thể được tái sử dụng. Khi nối process, cần thêm host, boot/session và thời điểm bắt đầu theo khả năng nguồn.
- `recording_offset_ms` là vị trí trong bản ghi phiên, không thay thế đồng hồ của sự kiện máy đích.
- `approval_id` phải dẫn tới dữ liệu phê duyệt đã lưu; tự thêm mã ticket vào log không chứng minh ticket đã cho phép thao tác.
- Phân biệt trường không thu thập, không áp dụng và bị che. Cả ba trường hợp đều có thể xuất hiện dưới dạng thiếu dữ liệu, nhưng ý nghĩa khác nhau.

## 6. Ngữ nghĩa lệnh: chuỗi nhập không phải toàn bộ hành động

### 6.1. Shell làm biến đổi điều được nhập

Xét lệnh minh họa:

~~~bash
sudo sh -c 'systemctl restart settlement-demo.service && systemctl is-active settlement-demo.service'
~~~

Bản ghi của cơ chế nâng quyền có thể ghi việc chạy `sh` cùng tham số. Các thao tác bên trong shell cần được quan sát bằng khả năng ghi bổ sung phù hợp. Không được suy từ một log `sudo sh` rằng mọi lệnh con đã được liệt kê đầy đủ.

Shell còn có thể mở rộng biến, wildcard, alias và chuyển hướng. Chuỗi người dùng nhập và danh sách tham số mà chương trình nhận vì thế có thể khác nhau. Một pipeline cũng gồm nhiều thành phần; trạng thái cuối của shell không nhất thiết mô tả kết quả từng thành phần.

Lệnh thay đổi thư mục hoặc phép gán biến có thể được shell xử lý nội bộ, không tạo một executable độc lập. Vì vậy, chỉ thu process execution chưa chắc bao phủ toàn bộ hành vi của shell.

### 6.2. Chương trình hợp lệ vẫn có thể là điểm khởi đầu cho hành động khác

Editor, interpreter, công cụ cơ sở dữ liệu và công cụ truyền tệp có thể thực hiện nhiều thao tác bên trong một lần khởi chạy. Log chương trình ban đầu chưa đủ cho biết file nào bị sửa, câu truy vấn nào được thực hiện hoặc dữ liệu nào đã truyền.

Với script, việc thấy đường dẫn `/opt/ops/maintenance.sh` không chứng minh nội dung script lúc chạy. Khi rủi ro yêu cầu, nối sự kiện với phiên bản artifact hoặc digest từ hệ thống triển khai đáng tin cậy; nêu rõ digest được quan sát ở thời điểm nào. Hash một file sau sự cố không chứng minh file đó có cùng nội dung khi thực thi.

### 6.3. Tác vụ nền và thao tác từ xa kéo dài đường truy vết

Một tiến trình có thể tạo job nền còn chạy sau khi terminal đóng. Một công cụ trên máy A có thể yêu cầu máy B hoặc dịch vụ cloud thực hiện công việc. Thời điểm đóng phiên PAM vì thế không nhất thiết là thời điểm mọi tác động kết thúc.

Cần nối thêm remote request ID, job ID hoặc audit event của dịch vụ đích. Nếu không có liên kết, ghi nhận khoảng trống; không gán mọi sự kiện gần nhau về thời gian cho cùng một hành động.

### 6.4. Bị từ chối cũng là bằng chứng

Một lệnh bị policy từ chối cho thấy có yêu cầu và cơ chế kiểm soát đã phản hồi. Nó không chứng minh lệnh đã thực thi trên đích.

Ngược lại, không tìm thấy sự kiện thực thi cũng chưa đủ chứng minh lệnh không chạy nếu nguồn ghi đang lỗi hoặc chưa bao phủ đường truy cập đó. Kết luận phải dựa trên cả sự kiện và tình trạng thu thập.

## 7. Chọn nguồn ghi theo loại truy cập

### 7.1. Phiên quản trị tương tác

Kết hợp bản ghi PAM với sự kiện máy đích để phân biệt người dùng, tài khoản kết nối và danh tính hiệu lực. Nếu sử dụng tài khoản dùng chung, cần mapping phiên đáng tin cậy, kiểm soát kết nối đồng thời và giám sát các đường truy cập ngoài PAM.

Tài liệu chính thức của sudo phân biệt event logging với I/O logging; việc ghi output không tự tạo một event cho từng lệnh con. Khả năng `log_subcmds` có giới hạn nền tảng và cơ chế thực hiện, nên phải kiểm tra tính hỗ trợ và hành vi của phiên bản triển khai trước khi dựa vào nó. Xem [tài liệu sudoers trong kho nguồn chính thức](https://github.com/sudo-project/sudo/blob/main/docs/sudoers.man.in).

Bài học thiết kế ở đây là xác minh **điều nguồn thực sự ghi**, thay vì giả định một tùy chọn mang tên “session logging” bao phủ mọi hành động. Không sao chép một cấu hình ghi input/output vào sản xuất trước khi đánh giá dữ liệu nhạy cảm, tải lưu trữ và tình huống lỗi.

### 7.2. API và quản trị cloud

CLI có thể chỉ là client. Đích kiểm toán đáng quan tâm nằm ở API: principal nào gọi, role/session nào được dùng, action/resource nào được yêu cầu, request có được chấp nhận và công việc có hoàn thành không.

Nối log CLI hoặc runner với audit dịch vụ qua request ID, workload identity và tài nguyên. Không đặt secret hoặc token vào command line để thuận tiện truy vết; dùng cơ chế credential của nền tảng và giữ định danh credential/lease thay cho giá trị bí mật.

### 7.3. Automation và service account

Gói bằng chứng của một lần chạy tự động nên nối được:

~~~text
Pipeline run / lịch tác vụ
    -> workload identity
    -> quyền hoặc credential lease
    -> job / bước triển khai
    -> hành động trên tài sản
    -> quan sát kết quả
~~~

Commit ID giúp xác định mã nguồn tham chiếu, nhưng không tự chứng minh artifact thực thi được build từ commit đó. Khi cần mức bảo đảm cao hơn, nối với build artifact, nguồn cấp phát và dữ liệu xác minh artifact của pipeline.

### 7.4. Thiết bị hoặc giao thức có khả năng audit hạn chế

Có môi trường chỉ cung cấp session transcript hoặc nhật ký cấu hình tổng quát. Hãy ghi rõ độ hạt và phần thiếu, rồi bổ sung bằng chứng phù hợp như thay đổi cấu hình, nhật ký quản lý tập trung hoặc xác nhận trạng thái ở đích.

Không tạo dữ liệu lệnh giả để làm schema “đủ trường”. Một giá trị `not_observed` kèm lý do hữu ích hơn một suy đoán được trình bày như sự thật.

## 8. Tương quan sự kiện mà không gán nhầm người

Ưu tiên các khóa liên kết có nguồn rõ ràng:

1. Correlation/session ID được truyền và xác minh qua các lớp.
2. Mapping do connector hoặc broker ghi giữa phiên PAM với phiên đăng nhập tại đích.
3. Định danh chứng thư, token session hoặc credential lease được hệ thống quản lý.
4. Tập thuộc tính như tài sản, tài khoản, địa chỉ nguồn và thời gian, khi không có khóa trực tiếp.

Mức thứ tư yếu hơn và có thể chỉ tạo ứng viên để điều tra. Địa chỉ nguồn của một gateway NAT có thể đại diện cho nhiều người. Một tài khoản `root` và khoảng thời gian gần nhau không đủ để phân biệt hai phiên đồng thời.

Nên lưu `correlation_method` và mức chắc chắn của liên kết. Có thể dùng các nhãn nội bộ như `explicit`, `derived`, `ambiguous`; cần định nghĩa chúng trong quy trình. Không biến điểm số tương quan thành chứng nhận danh tính.

### Ví dụ xung đột

- Người A mở phiên PAM `S1` vào máy H lúc 10:00.
- Người B mở phiên PAM `S2` vào cùng máy H lúc 10:01.
- Cả hai dùng một tài khoản đích.
- Một log lúc 10:02 chỉ có hostname và tài khoản đích.

Không đủ cơ sở để khẳng định A hoặc B chạy lệnh. Cần host session ID, thông tin kết nối, process ancestry hoặc dữ liệu tương ứng từ recorder. Nếu vẫn không phân biệt được, hồ sơ phải ghi `attribution=ambiguous` và mô tả kiểm soát cần bổ sung.

Không yêu cầu người vận hành “chọn một người” để hoàn thiện báo cáo. Đây là khoảng trống kiểm soát cần được xử lý, không phải ô dữ liệu thiếu có thể điền bằng cảm tính.

## 9. Thời gian, thứ tự và mức đầy đủ

### 9.1. Hai timestamp phục vụ hai câu hỏi

`occurred_at` mô tả thời gian nguồn cho rằng sự kiện xảy ra. `received_at` mô tả khi collector nhận sự kiện. Chênh lệch giữa hai giá trị có thể do trễ mạng, buffer hoặc lệch đồng hồ; không được mặc định đó là độ trễ truyền.

Giữ thêm số thứ tự, boot ID, offset tương đối hoặc dữ liệu đồng bộ thời gian nếu nguồn có. Chúng hỗ trợ phát hiện khoảng trống và thứ tự, nhưng cần hiểu vòng đời, reset và khả năng mất sự kiện của từng nguồn.

### 9.2. Tránh suy quan hệ nhân quả chỉ từ timestamp

Nếu máy A chậm ba phút còn PAM dùng đồng hồ đúng, một lệnh có thể trông như xảy ra trước khi phiên được mở. Trước khi kết luận vượt cửa sổ JIT, kiểm tra tình trạng đồng hồ và độ bất định.

Khi không giải quyết được, báo khoảng thời gian có thể xảy ra và nguồn bất định. Không âm thầm sửa timestamp gốc để timeline nhìn hợp lý hơn.

### 9.3. Tính đầy đủ cần có mẫu số

Báo cáo “đã thu 12.000 lệnh” không cho biết phạm vi bao phủ nếu không biết có bao nhiêu tài sản và đường truy cập thuộc diện phải ghi.

Các chỉ số hữu ích, khi có nguồn đo độc lập, gồm:

| Chỉ số | Cách hiểu | Điều cần tránh |
|---|---|---|
| Tài sản có nguồn audit khỏe / tài sản bắt buộc ghi | Độ bao phủ triển khai trong phạm vi | Loại tài sản mất kết nối khỏi mẫu số |
| Phiên có recorder hợp lệ / phiên bắt buộc ghi | Độ bao phủ ghi phiên | Đếm phiên mở thành công như đã có recording |
| Sự kiện đặc quyền nối được danh tính / sự kiện đặc quyền đã quan sát | Chất lượng quy thuộc trong tập quan sát | Gọi đây là tỷ lệ mọi lệnh thực tế |
| Gói bằng chứng truy xuất được / gói đã thử truy xuất | Khả năng cung cấp khi cần | Chỉ kiểm tra index tồn tại |
| Khoảng mất telemetry và thời gian khắc phục | Mức liên tục của đường thu thập | Đánh đồng không có log với không có hoạt động |

Nếu tập sự kiện quan sát cũng là tập duy nhất dùng làm mẫu số, chỉ số không đo được những hành động đã mất hoàn toàn. Cần thêm kiểm kê tài sản, inventory connector, số phiên và health event độc lập.

Khi collector hoặc recorder lỗi, hành vi chặn hay cho phép tiếp tục phải được quy định theo rủi ro, tính sẵn sàng và cơ chế khẩn cấp của tổ chức. Bằng chứng cần lưu cả lỗi ghi, quyết định ngoại lệ, người phê duyệt và hoạt động phục hồi; không che lỗi bằng một trạng thái thành công chung.

## 10. Bảo vệ tính toàn vẹn và khả năng kiểm tra nguồn gốc

### 10.1. Bảo vệ từ nguồn đến kho

Bảo vệ kênh truyền, xác thực collector, phân quyền ingest và giám sát thay đổi cấu hình. Nguồn máy đích có thể bị người có quyền cao tác động, nên việc chuyển log sớm ra một miền quản trị độc lập thường có giá trị.

Tuy nhiên, chuyển từ xa không khôi phục được một sự kiện chưa từng được nguồn tạo ra. Kho lưu trữ bất biến cũng không bảo đảm dữ liệu đầu vào đầy đủ hoặc đúng danh tính.

### 10.2. Hash có vai trò cụ thể

Hash giúp kiểm tra một artifact có thay đổi so với giá trị tham chiếu đã giữ hay không. Hash không tự chứng minh ai tạo artifact, nó được tạo khi nào hay nội dung có phản ánh sự thật.

Nếu người sửa file cũng có thể thay cả manifest chứa hash, việc so hash không tạo được mức bảo đảm mong muốn. Cần bảo vệ manifest, khóa ký nếu dùng, dấu thời gian và đường lưu trữ theo mô hình tin cậy của tổ chức.

Với chữ ký, kiểm tra signer, quyền sử dụng khóa, chuỗi tin cậy phù hợp, trạng thái khóa và dữ liệu thời gian cần thiết. Không gọi một file “không thể chối bỏ” chỉ vì có checksum.

### 10.3. Ghi nhận quá trình tiếp nhận và bàn giao

Hồ sơ bàn giao nên có người hoặc hệ thống thực hiện, thời gian, lý do, artifact ID, thao tác đã làm và kết quả kiểm tra toàn vẹn. Khi tạo bản trích xuất hoặc bản che dữ liệu, giữ quan hệ với nguồn và quy tắc biến đổi.

Nếu một người tải log, giải nén, chuyển encoding rồi lọc trước khi gửi, cần ghi các bước đó. Một bản đã biến đổi không nên được giới thiệu là bản thô nguyên gốc.

### 10.4. Thời hạn lưu và khả năng đọc lại

Thời hạn lưu cần được xác định theo yêu cầu áp dụng, phân loại dữ liệu, nhu cầu điều tra và chính sách nội bộ; bài học không đặt một số ngày chung cho mọi tổ chức.

Ngoài giữ byte, cần giữ khả năng giải mã, đọc schema cũ, tìm artifact, xác minh và phát recording. File còn nhưng khóa đã bị hủy hoặc trình phát không còn tương thích vẫn có thể làm bằng chứng không sử dụng được.

Các yêu cầu giữ lại phục vụ vụ việc phải được quản lý theo quy trình của tổ chức, bao gồm ảnh hưởng đến lịch xóa thông thường và quyền giải phóng giữ lại.

## 11. Giảm lộ dữ liệu trong chính bằng chứng

Command line, input và output có thể chứa mật khẩu, token, dữ liệu khách hàng hoặc khóa riêng. Kho bằng chứng vì vậy có thể trở thành một nơi tập trung dữ liệu nhạy cảm.

Thiết kế thu thập theo nhu cầu:

- Ưu tiên cơ chế sử dụng secret không đưa giá trị bí mật vào tham số.
- Giữ credential ID, lease ID hoặc phiên bản secret khi đủ cho truy vết.
- Chọn rõ dữ liệu nào được thu, che tại nguồn, che khi chuẩn hóa hoặc chỉ che khi xuất.
- Hạn chế người xem recording; ghi lại việc xem, tải và xuất bằng chứng.
- Không thu toàn bộ biến môi trường hoặc input chỉ để tăng số trường trong báo cáo.

Nếu chỉ che ở giao diện, dữ liệu bí mật vẫn có thể tồn tại trong log thô, index tìm kiếm, bản sao lưu hoặc gói export. Phải kiểm tra mọi lớp liên quan đến chính sách che.

Nếu không thu hoặc che tại nguồn, một số dữ liệu sẽ không thể khôi phục để điều tra. Cần ghi rõ giới hạn đó, giữ phiên bản redaction profile và đánh giá xem còn đủ thông tin để xác định thao tác hay không.

Không suy rằng hash của một mật khẩu ngắn là cách ẩn danh an toàn. Giá trị có không gian đoán nhỏ có thể bị thử đối chiếu. Trong nhiều trường hợp, nên giữ mã tham chiếu đến secret được quản lý thay vì hash trực tiếp secret.

Bản xuất cho kiểm toán viên có thể là bản đã che, trong khi bản nguồn được giữ ở vùng hạn chế theo chính sách. Khi làm vậy, cần định danh hai bản, quy tắc chuyển đổi và người có quyền yêu cầu đối chiếu.

## 12. Đóng gói hồ sơ có thể kiểm tra lại

Cấu trúc dưới đây chỉ là minh họa cho một gói export; không phải các file cần tạo trong bài thực hành hiện tại:

~~~text
case-CHG-824/
  scope-and-method.txt
  authorization-snapshot.json
  session-index.json
  command-events.ndjson
  raw-source-index.json
  collection-health.json
  artifacts-manifest.json
  review-and-transfer-log.json
~~~

Nếu recording hoặc bản ghi thô quá lớn, index phải trỏ tới kho kiểm soát truy cập còn hiệu lực và có phương án cung cấp cho người kiểm tra. Một URL hết hạn không làm hồ sơ đủ khả năng tái kiểm tra.

### Nội dung cần có trong hồ sơ

**Phạm vi và phương pháp:** tài sản, môi trường, khoảng thời gian, múi giờ, loại thao tác, hệ thống nguồn, phiên bản truy vấn và các bộ lọc. Ghi rõ thời điểm export vì dữ liệu có thể đến muộn.

**Dữ liệu cấp quyền:** request, phê duyệt, phạm vi quyền, cửa sổ JIT/JEA, policy version và ngoại lệ.

**Dữ liệu hành động:** bản ghi lệnh, mã sự kiện nguồn, mapping danh tính, phiên, process hoặc request đích.

**Dữ liệu kết quả:** exit observation, trạng thái job và phép xác nhận tác động nếu có; không gộp các mức kết quả thành một cờ `success`.

**Dữ liệu chất lượng:** nguồn mất kết nối, event bị cắt ngắn, trường bị che, độ lệch đồng hồ, liên kết mơ hồ và khoảng trống chưa xử lý.

**Dữ liệu bảo quản:** danh sách artifact, thuật toán và giá trị kiểm tra toàn vẹn thực tế, thông tin ký nếu dùng, quyền truy cập và lịch sử bàn giao.

Có thể dùng mô hình manifest sau; đây là mẫu, các giá trị nằm trong dấu ngoặc nhọn phải được hệ thống xuất điền từ dữ liệu thật:

~~~yaml
manifest_schema: example-1
package_id: "{package-id}"
scope:
  asset_ids: ["{asset-id}"]
  from_utc: "{start-time}"
  until_utc: "{end-time}"
  interval: "start-inclusive,end-exclusive"
export:
  generated_at: "{export-time}"
  query_version: "{query-version}"
  exporter_identity: "{exporter-id}"
  redaction_profile: "{profile-version}"
artifacts:
  - artifact_id: "{artifact-id}"
    relative_path: "command-events.ndjson"
    media_type: "application/x-ndjson"
    byte_length: "{actual-byte-length}"
    integrity:
      algorithm: "SHA-256"
      digest_hex: "{computed-digest}"
limitations:
  - "{known-gap-or-none-observed-with-scope}"
~~~

Không lấy manifest mẫu có placeholder làm bằng chứng thật. Giá trị digest phải được tính trên chính byte của artifact được cung cấp, và chính manifest cũng cần nằm trong cơ chế bảo vệ phù hợp.

## 13. Ví dụ xuyên suốt: kiểm toán một lần restart dịch vụ

Giả sử request `req-730` cho phép người `user-1042` restart đúng `settlement-demo.service` trên `asset-prod-017` từ 03:00 đến 03:30 UTC. Việc sửa cấu hình và thao tác trên tài sản khác không nằm trong phạm vi request.

| Mốc UTC | Quan sát | Nguồn cần giữ | Kết luận phù hợp |
|---|---|---|---|
| 02:55 | Request được phê duyệt | Hệ thống request và quyết định PAM | Có cấp quyền với phạm vi, thời hạn đã lưu |
| 03:00 | Cấp JIT có hiệu lực | PAM hoặc hệ thống quyền đích | Quyền được kích hoạt theo quan sát của nguồn |
| 03:02 | Mở phiên `session-91` | PAM + mapping tại đích | Có phiên liên quan đến người và tài sản |
| 03:15 | Quan sát chạy lệnh restart | Audit thực thi tại đích | Có hành động thực thi được ghi nhận |
| 03:15 | Quan sát lệnh kết thúc với mã 0 | Nguồn kết quả tiến trình | Công cụ trả trạng thái thành công theo quy ước của nó |
| 03:16 | Kiểm tra trạng thái dịch vụ | Công cụ hoặc telemetry dịch vụ | Trạng thái dịch vụ tại thời điểm kiểm tra được xác nhận |
| 03:20 | Yêu cầu thao tác ngoài phạm vi bị từ chối | Cơ chế kiểm soát tương ứng | Có attempt bị chặn; chưa thể gọi là thay đổi đã thực hiện |
| 03:30 | Quyền JIT được thu hồi | Hệ thống quyền và PAM | Có bằng chứng thu hồi ở các lớp được quan sát |

Đánh giá cần đi thêm một bước: lệnh restart có đúng tài sản và đúng dịch vụ không, có xảy ra trong thời hạn không, policy có thực sự giới hạn thao tác hay chỉ ghi nhận lý do, và kết quả kiểm tra có đáp ứng tiêu chí vận hành không?

Mã 0 của công cụ restart không tự chứng minh giao dịch thanh toán thành công. Nếu mục tiêu của thay đổi là phục hồi xử lý giao dịch, cần telemetry hoặc phép kiểm tra ở mức dịch vụ/nghiệp vụ phù hợp.

Tương tự, một attempt bị từ chối chỉ chứng minh kiểm soát chặn ở đường đã quan sát. Không được suy rằng không còn đường khác có thể thực hiện cùng thao tác.

### Cách viết kết luận

Kết luận có thể là:

> Trong phạm vi dữ liệu thu từ PAM và nguồn audit của tài sản đã nêu, có liên kết trực tiếp giữa người yêu cầu, phiên quản trị và lệnh restart. Nguồn kết quả ghi nhận công cụ kết thúc với mã 0; kiểm tra lúc 03:16 ghi nhận dịch vụ hoạt động. Hồ sơ không chứa phép kiểm tra giao dịch đầu cuối.

Câu cuối giúp người đọc hiểu giới hạn bằng chứng và tránh dùng hồ sơ cho một khẳng định rộng hơn phạm vi quan sát.

## 14. Quy trình kiểm tra command evidence cho một kỳ kiểm toán

### Bước 1 — Xác định tập cần kiểm tra

Chốt kỳ thời gian, tài sản, loại truy cập và tiêu chí kiểm soát. Lấy tập nền từ inventory, danh sách phiên, hệ thống cấp quyền và các đường quản trị trong phạm vi.

Không chỉ chọn những phiên đã có recording đẹp. Điều đó dễ loại đúng các trường hợp lỗi cần được xem xét.

### Bước 2 — Đối chiếu độ bao phủ và tình trạng nguồn

Kiểm tra tài sản nào có nguồn ghi, nguồn khỏe trong khoảng nào, có mất log, mất recording hoặc đồng hồ bất thường không. Ghi các khoảng thiếu trước khi diễn giải hành động.

### Bước 3 — Chọn mẫu theo mục tiêu và rủi ro

Ví dụ: phiên có quyền cao nhất, break-glass, thao tác thay đổi cấu hình, phiên vendor, automation và phiên ngoài giờ. Nếu lấy mẫu, ghi phương pháp, tập nền, số mẫu và tiêu chí lựa chọn; không tuyên bố đã kiểm tra toàn bộ.

### Bước 4 — Tái dựng chuỗi cho từng mẫu

Nối người/workload, phê duyệt, phiên, hành động và kết quả. Phân biệt khóa trực tiếp với suy luận; kiểm tra xung đột khi có nhiều phiên hoặc tài khoản dùng chung.

### Bước 5 — Kiểm tra khả năng cung cấp và bảo vệ

Thử lấy bản thô hoặc recording, đọc được artifact, đối chiếu toàn vẹn và kiểm tra quyền export. Có một dòng trong SIEM không bảo đảm file recording tương ứng còn truy xuất được.

### Bước 6 — Ghi phát hiện và cách xử lý

Phân biệt các loại phát hiện:

- Thiếu dữ liệu do thu thập hoặc bảo quản.
- Không đủ liên kết để quy thuộc hành động.
- Có hành động nhưng ngoài phạm vi cấp quyền.
- Có cấp quyền nhưng cơ chế thực thi chưa giới hạn đúng.
- Có bằng chứng đúng phạm vi và chưa quan sát thấy ngoại lệ trong mẫu.

Mỗi phát hiện cần nguồn, mức ảnh hưởng, owner xử lý và tiêu chí xác nhận khắc phục. Một ticket đóng không tự thay thế phép kiểm tra rằng đường thu thập đã hoạt động lại.

## 15. Khi có sự cố: sử dụng và bảo toàn bằng chứng

Khi nghi ngờ tài khoản đặc quyền bị lạm dụng, giữ lại dữ liệu liên quan theo quy trình, ghi nhận nguồn và hạn chế những thao tác làm mất trạng thái. Các hoạt động bảo vệ hệ thống cần phối hợp với việc bảo toàn bằng chứng; mọi biến đổi phục vụ thu thập nên được ghi lại.

Một trình tự phân tích phù hợp:

1. Xác định tài khoản, phiên, tài sản và khoảng thời gian ban đầu.
2. Kiểm tra nguồn nào còn hoạt động và nguồn nào có dấu hiệu bị tác động.
3. Thu các artifact liên quan cùng metadata, không chỉ ảnh chụp dashboard.
4. Nối hành động sang tiến trình con, máy từ xa, API hoặc job nền khi có khóa liên kết.
5. Tách điều đã quan sát, điều suy luận và điều chưa biết trong timeline.
6. Mở rộng phạm vi dựa trên bằng chứng mới; giữ lịch sử truy vấn và export.
7. Theo dõi việc xem, chuyển giao và phân tích các bản sao.

Nếu thấy sự kiện dừng audit hoặc thay đổi cấu hình collector, giữ chính sự kiện đó và tìm nguồn độc lập để đối chiếu. Không “sửa lại log cho đủ” hoặc chèn suy đoán vào luồng bản ghi nguồn.

Ghi lại bất kỳ timestamp nào được chuyển đổi, tham số nào bị che hoặc artifact nào được giải mã. Điều này cho phép người khác tái lập quá trình phân tích.

## 16. Bài thực hành với dữ liệu giả

Không cần chạy lệnh đặc quyền để thực hiện bài tập. Dùng tập quan sát sau:

~~~text
E01 03:00 PAM       req-R1 allow user-U1 asset-H1 until=03:30
E02 03:02 PAM       session-S1 open user-U1 account-A1 asset-H1
E03 03:02 CONNECTOR session-S1 maps-to hostsession-HS8
E04 03:05 ENDPOINT  hostsession-HS8 command=C1 process-start observed
E05 03:05 ENDPOINT  command=C1 process-exit code=0
E06 03:06 SERVICE   asset-H1 check=service-active result=true
E07 03:10 COLLECTOR source=H1 endpoint-audit unavailable
E08 03:12 PAM       session-S1 terminal-output artifact=REC1
E09 03:20 COLLECTOR source=H1 endpoint-audit restored
E10 03:30 PAM       req-R1 access-expired
~~~

Trong tập giả này, `C1` đại diện cho lệnh restart dịch vụ được request cho phép. Bản ghi tóm tắt đã lược trường để dễ đọc; hồ sơ thật cần các trường nguồn và phạm vi đầy đủ hơn.

### Yêu cầu

- Tái dựng chuỗi bằng chứng cho `C1`.
- Xác định những kết luận nào có thể đưa ra từ `E04`, `E05` và `E06`.
- Giải thích vì sao `E08` không tự bù được toàn bộ khoảng mất endpoint audit.
- Xác định bằng chứng bổ sung để chứng minh quyền thực tế trên đích đã bị thu hồi sau `E10`.
- Soạn một câu kết luận có nêu khoảng thiếu từ 03:10 đến 03:20.

### Gợi ý phân tích

`E02` và `E03` tạo liên kết rõ giữa người, phiên PAM và host session. `E04` cho thấy quan sát bắt đầu thực thi; `E05` cung cấp kết quả tiến trình; `E06` bổ sung trạng thái dịch vụ ở một thời điểm sau đó. Ba loại dữ liệu hỗ trợ các mức khẳng định khác nhau.

`E08` chỉ cho thấy một artifact terminal output được ghi nhận. Chưa biết nó có đầy đủ, có kiểm tra được hay có bao phủ thao tác ngoài terminal không. Vì vậy, không thể kết luận mọi hành động tại H1 trong khoảng mất audit đều được quan sát.

`E10` là trạng thái của PAM. Để xác nhận quyền tại đích đã hết hiệu lực, cần bằng chứng phù hợp với cơ chế cấp quyền: sự kiện thay đổi membership/role, trạng thái lease/token, thao tác thu hồi và kiểm tra quyền liên quan. Cũng cần xem phiên hoặc tiến trình đã mở có tiếp tục giữ quyền hay không.

Một kết luận phù hợp là:

> Lệnh C1 có liên kết tới user-U1 qua mapping phiên, có quan sát thực thi và kết thúc với mã 0; trạng thái dịch vụ được xác nhận tại 03:06. Endpoint audit không sẵn sàng từ 03:10 đến 03:20, nên tập dữ liệu này chưa đủ để xác nhận toàn bộ hoạt động trên H1 trong khoảng đó.

## 17. Sai lầm thường gặp và cách sửa

| Sai lầm | Vì sao làm yếu hồ sơ | Cách xử lý |
|---|---|---|
| “Có video nên biết mọi lệnh” | Bản ghi màn hình không bao phủ mọi kênh hoặc tác vụ nền | Nêu phạm vi recorder và bổ sung nguồn đích |
| Chỉ ghi tài khoản `root` | Mất người hoặc workload khởi tạo | Giữ mapping danh tính, phiên và account đích |
| Dùng timestamp gần nhau làm khóa chắc chắn | Có đồng hồ lệch và phiên đồng thời | Ưu tiên khóa trực tiếp, ghi liên kết mơ hồ |
| Log allow được gọi là executed | Quyết định và thực thi là hai giai đoạn | Tách event type và nguồn quan sát |
| Exit code 0 được gọi là thành công nghiệp vụ | Trạng thái chương trình có phạm vi hẹp | Bổ sung kiểm tra tác động theo mục tiêu |
| Hash được gọi là chứng minh tính xác thực | Hash chỉ so với một tham chiếu được tin cậy | Bảo vệ manifest và nguồn gốc, xác minh đúng mô hình |
| Chỉ lưu bản đã lọc | Không thể kiểm tra lại cách diễn giải | Giữ nguồn và quy tắc biến đổi theo chính sách |
| Ghi token vào log để nhận diện | Tạo thêm nơi lộ credential | Dùng mã tham chiếu hoặc lease/session ID |
| Không có log được coi là không có hành động | Có thể mất nguồn hoặc nằm ngoài coverage | Đối chiếu health, inventory và các đường truy cập |
| Đưa một số ngày lưu chung cho mọi môi trường | Không phản ánh yêu cầu và phân loại dữ liệu cụ thể | Xây lịch lưu, xóa và giữ lại theo phạm vi áp dụng |

## 18. Tự kiểm tra thiết kế trước khi bàn giao

Một thiết kế command audit evidence có thể được giải thích bằng các câu trả lời cụ thể sau:

1. Có thể đi từ một lệnh đến người hoặc workload khởi tạo bằng liên kết nào?
2. Có phân biệt account kết nối, effective identity và initiating identity không?
3. Có giữ quyết định cấp quyền và policy version đúng thời điểm không?
4. Nguồn nào quan sát thực thi, nguồn nào quan sát kết thúc và nguồn nào xác nhận tác động?
5. Có nhận diện được phiên đồng thời, process ID tái sử dụng và thao tác từ xa không?
6. Có biết nguồn nào mất dữ liệu, trễ, bị cắt ngắn hoặc lệch đồng hồ không?
7. Bản ghi thô và recording có truy xuất được, đọc được và kiểm tra toàn vẹn được không?
8. Ai có thể sửa, xóa, xem hoặc xuất bằng chứng, và các hành vi đó được ghi ở đâu?
9. Secret và dữ liệu cá nhân được xử lý thế nào trên nguồn, index, backup và export?
10. Kết luận có nêu phạm vi, phương pháp và giới hạn thay vì khẳng định bao phủ tuyệt đối không?

Giá trị của bằng chứng lệnh nằm ở khả năng kiểm tra lại một chuỗi hành động có bối cảnh. Khi một mắt xích chưa được quan sát, ghi rõ nó và điều kiện cần bổ sung sẽ giúp kiểm toán và ứng phó sự cố đáng tin cậy hơn.

## 19. Tài liệu tham chiếu

- [NIST SP 800-53 Rev. 5 — trang công bố chính thức](https://csrc.nist.gov/pubs/sp/800/53/r5/upd1/final): tham khảo nhóm Audit and Accountability và kiểm soát về sử dụng quyền đặc biệt. Bản công bố nêu AU-3 cho nội dung audit record; AC-6(9) liên quan việc ghi sử dụng chức năng đặc quyền. Khi áp dụng, cần chọn đúng phiên bản và phạm vi kiểm soát của tổ chức; một hồ sơ command evidence không tự chứng nhận tuân thủ toàn bộ framework.
- [sudoers — tài liệu trong kho nguồn chính thức của sudo](https://github.com/sudo-project/sudo/blob/main/docs/sudoers.man.in): tham khảo event logging, I/O logging và giới hạn ghi lệnh con. Nhánh nguồn có thể thay đổi; việc triển khai phải đối chiếu tài liệu đi kèm phiên bản đang dùng.
