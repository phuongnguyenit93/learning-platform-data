# Command logging policy

**Command logging policy** là chính sách xác định những lệnh hoặc thao tác quản trị nào phải được ghi nhận, ghi những trường thông tin nào, tại đâu, ai được truy cập và phải xử lý thế nào khi bằng chứng không được tạo đầy đủ.

Trong quản lý truy cập đặc quyền (Privileged Access Management — PAM), log lệnh giúp nối người yêu cầu với danh tính thực thi, tài nguyên đích, quyết định cấp quyền và hành động thực tế. Nó phục vụ kiểm toán, điều tra sự cố và phát hiện việc sử dụng quyền ngoài nhiệm vụ trên tài khoản quản trị, tài khoản dịch vụ và hạ tầng nhạy cảm.

Chính sách này thuộc **Governance** vì việc bật một tùy chọn ghi log chưa quyết định được độ bao phủ, dữ liệu cần bảo vệ, trách nhiệm vận hành và mức chấp nhận rủi ro khi log bị thiếu. Nó cũng cần phối hợp với least privilege, JIT/JEA, vault, luân chuyển credential và giám sát phiên.

## 1. Mục tiêu và ranh giới của log lệnh

Một chuỗi bằng chứng hữu ích phải trả lời được:

- Ai hoặc workload nào yêu cầu hành động, với danh tính nguồn nào.
- Danh tính nào thực thi tại hệ thống đích.
- Hành động nào được yêu cầu, được chấp thuận hoặc bị từ chối.
- Hành động đã được khởi chạy hay chưa, kết thúc ra sao và có xác minh tác động không.
- Tài nguyên, thời điểm, phiên và yêu cầu công việc nào liên quan.
- Chính sách cấp quyền và chính sách ghi nhận nào đã được áp dụng.

Log lệnh không thay thế cơ chế phân quyền. Một lệnh nguy hiểm đã được ghi lại vẫn có thể gây thiệt hại nếu được cấp quyền quá rộng. Ngược lại, lệnh bị từ chối cũng có giá trị bằng chứng, dù không tạo tiến trình hoặc không thay đổi tài nguyên.

Cần phân biệt **ý định**, **quyết định**, **thực thi** và **kết quả nghiệp vụ**. Người dùng gõ một chuỗi chưa chứng minh hệ thống đã chạy chuỗi đó; mã thoát thành công của chương trình chưa chứng minh dịch vụ đã khỏe hoặc dữ liệu nghiệp vụ đã đúng.

## 2. Xác định phạm vi và nguồn ghi nhận

### 2.1. Bao phủ nhiều đường quản trị

Phạm vi nên gồm các giao diện thực sự được sử dụng: shell tương tác, lệnh nâng quyền, PowerShell hoặc endpoint JEA, công cụ quản trị cơ sở dữ liệu, tác vụ tự động, pipeline và thao tác quản trị qua API.

Không phải mọi hành động đều có một chuỗi command line. Một tác vụ qua API có thể cần tên operation, principal, tài nguyên, request ID và kết quả thay cho tên executable. Giao diện đồ họa cần nguồn audit tương ứng; bản ghi hình không tự biến thành danh sách lệnh đầy đủ.

Chính sách phải chỉ rõ các đường trực tiếp ngoài gateway PAM. Nếu chỉ ghi phiên qua gateway mà vẫn cho phép đường quản trị khác không được quan sát, báo cáo phải thể hiện giới hạn bao phủ.

### 2.2. Biết mỗi nguồn nhìn thấy gì

| Nguồn bằng chứng | Thông tin thường hữu ích | Giới hạn cần nêu |
| --- | --- | --- |
| Gateway hoặc session recorder | Người dùng, phiên, kết nối, dữ liệu được luồng phiên ghi nhận | Có thể không thấy đầy đủ tác động tại đích hoặc đường truy cập ngoài gateway |
| Lịch sử shell | Một số lệnh người dùng nhập | Có thể bị sửa, thiếu lệnh, thiếu phiên khác và thiếu kết quả; không nên là bằng chứng duy nhất |
| Audit tiến trình ở hệ điều hành | Khởi tạo tiến trình, executable, đối số và ngữ cảnh theo cấu hình | Không tự bao phủ mọi shell builtin, hành động trong tiến trình hoặc lời gọi API |
| Transcript hoặc log PowerShell | Hoạt động theo loại log và cấu hình được bật | Không nên giả định một loại log thấy mọi lệnh, mọi dữ liệu và mọi phiên |
| Log nâng quyền | Sự kiện sử dụng quyền hoặc khởi chạy lệnh theo cơ chế | Cho phép mở shell nâng quyền có thể tạo nhiều hành động tiếp theo cần nguồn ghi bổ sung |
| Audit API hoặc tài nguyên | Operation, danh tính, tài nguyên và kết quả theo dịch vụ | Có thể có độ trễ, thiếu nội dung hoặc giới hạn lưu giữ |
| Log ứng dụng hoặc workflow | Nhiệm vụ, bước thực thi và kết quả theo nghiệp vụ | Phải đánh giá độ tin cậy và khả năng nối với sự kiện ở đích |

Không cộng tất cả nguồn rồi mặc định đã đầy đủ. Cần xác định nguồn nào chịu trách nhiệm cho từng loại hành động, phần nào được đối chiếu và phần nào còn là khoảng trống.

## 3. Định nghĩa một sự kiện lệnh

### 3.1. Danh tính và ngữ cảnh

Nên có định danh sự kiện, phiên, yêu cầu công việc và hành động để nối các bản ghi. Người dùng nguồn và danh tính thực thi phải được lưu riêng khi PAM dùng tài khoản đích khác.

| Nhóm trường | Nội dung cần thể hiện |
| --- | --- |
| Định danh | Event ID, command/action ID, session ID, request ID hoặc correlation ID phù hợp |
| Chủ thể | Người yêu cầu hoặc workload, nguồn xác thực và danh tính thực thi |
| Đích | Asset ID, tenant/account/project, môi trường và đối tượng tác động |
| Hành động | Tên lệnh hoặc operation, tham số được phép ghi, cách diễn giải có cấu trúc |
| Quyết định | Cho phép hoặc từ chối, lý do và phiên bản chính sách cấp quyền |
| Thực thi | Điểm capture, thời điểm bắt đầu/kết thúc và trạng thái được nguồn báo cáo |
| Kết quả | Mã thoát nếu có, lỗi đã làm sạch, trạng thái xác minh tác động |
| Quản trị log | Phiên bản chính sách ghi nhận, mức phân loại và nguồn bằng chứng liên quan |

Nên dùng định danh ổn định thay vì chỉ dựa vào tên hiển thị. Tên tài khoản giống nhau ở hai domain hoặc hai máy chủ không nhất thiết là cùng principal.

### 3.2. Phân biệt các pha

Một mô hình sự kiện có thể có các pha sau:

```text
requested -> authorization_decided -> execution_started -> execution_finished
                                                    -> outcome_verified
```

Đây là mô hình minh họa, không bắt buộc mọi công cụ phát ra đúng các tên trên. Lệnh bị từ chối có thể dừng ở quyết định; tác vụ bị mất kết nối có thể không có sự kiện kết thúc; xác minh tác động có thể xảy ra sau đó.

Không tự gán thành công khi thiếu sự kiện kết thúc. Cũng không xem việc không nhận phản hồi là bằng chứng chắc chắn lệnh chưa chạy: timeout có thể xảy ra sau khi đích đã thực hiện.

Đối với pipeline, script hoặc workflow gồm nhiều bước, phải quy định mức hạt cần ghi. Một bản ghi “đã chạy script” có thể đủ cho việc đối chiếu triển khai nếu script được kiểm soát phiên bản, nhưng có thể chưa đủ để điều tra những hành động con trong một shell tùy ý.

### 3.3. Lệnh nhập và lệnh được diễn giải

Alias, biến, pipeline, script, chương trình con và tham số có thể làm ý nghĩa thực thi khác chuỗi người dùng nhập. Chính sách cần chỉ rõ đang ghi đầu vào, hành động đã chuẩn hóa, sự kiện tiến trình hay kết hợp các loại đó.

Không dùng phép tách theo dấu cách hoặc dấu chấm phẩy như một bộ phân tích chung cho mọi shell. Nếu không thể diễn giải đáng tin cậy, giữ loại sự kiện và giới hạn kết luận thay vì trình bày một chuỗi đã xử lý như sự thật thực thi.

## 4. Giảm dữ liệu nhạy cảm trước khi lưu

### 4.1. Không biến log thành kho credential

Command line, script, stdout, stderr và thông báo lỗi đều có thể chứa mật khẩu, token, private key hoặc dữ liệu nghiệp vụ. Ghi toàn bộ nội dung không kiểm soát có thể tạo thêm nơi rò rỉ đặc quyền.

Nên ưu tiên giao diện có cấu trúc: tên hành động, tài nguyên và các tham số đã xác định được phép ghi. Các trường chứa bí mật phải được loại bỏ hoặc thay bằng dấu hiệu phù hợp trước khi hệ thống ghi chúng vào nơi lưu bền, hàng đợi hoặc công cụ quan sát khác.

Không chỉ làm sạch màn hình xem log trong khi bản gốc, buffer, dead-letter queue hoặc hệ thống phân tích vẫn giữ bí mật. Mã hóa dữ liệu lưu là lớp bảo vệ cần thiết trong nhiều thiết kế, nhưng không thay thế giảm dữ liệu không cần thu thập.

Nếu nguồn gốc tự ghi raw command trước khi bộ lọc của PAM nhìn thấy, phải đánh giá và cấu hình tại nguồn theo khả năng hỗ trợ. Không tuyên bố đã loại bỏ bí mật chỉ vì bản sao chuyển tới SIEM được che.

### 4.2. Ưu tiên tránh đưa bí mật vào lệnh

Khi cơ chế hỗ trợ, tác vụ nên nhận credential qua thành phần quản lý bí mật hoặc danh tính phù hợp thay vì đối số command line. Tuy nhiên, chuyển sang stdin, biến môi trường hoặc tệp không tự bảo đảm an toàn: mỗi kênh còn có thể bị ghi hoặc đọc theo cơ chế khác.

Với trường hợp có nhập dữ liệu nhạy cảm trong phiên, cần thiết kế cách bảo vệ phần đó mà vẫn giữ đủ sự kiện quản trị. Ghi nhận rằng một nguồn credential được sử dụng không đồng nghĩa phải lưu giá trị credential.

Lọc theo biểu thức nhận diện bí mật chỉ là một biện pháp hỗ trợ. Token không có nhãn, encoding khác, lỗi định dạng hoặc secret nằm trong output có thể bị bỏ sót. Mô hình dữ liệu cho phép rõ các trường an toàn thường dễ kiểm soát hơn ghi mọi thứ rồi cố tìm bí mật.

Không dùng hash của mật khẩu hoặc chuỗi lệnh chứa secret như giải pháp che bí mật mặc định. Giá trị có miền đoán nhỏ vẫn có thể bị dò ngoại tuyến; hash cũng không sửa được việc đã thu thập dữ liệu quá mức.

### 4.3. Kiểm soát đầu ra

Chính sách cần xác định có lưu output hay không, lưu trường nào, giới hạn dung lượng và cách xử lý output nhạy cảm. Với tác vụ chỉ cần trạng thái dịch vụ, có thể chỉ lưu trạng thái được phép và tham chiếu tới bằng chứng khác.

Nếu output bị cắt hoặc không thu thập, phải thể hiện rõ điều đó. Không trình bày bản ghi thiếu như toàn bộ kết quả thực thi.

## 5. Thiết kế chuỗi thu thập có thể kiểm chứng

Một kiến trúc khái niệm có thể là:

```text
Điểm capture được xác định
    -> chuẩn hóa và giảm dữ liệu nhạy cảm
    -> buffer bền được bảo vệ khi cần
    -> kênh truyền có xác thực và bảo vệ
    -> collector xác minh nguồn, schema và định danh
    -> nơi lưu bằng chứng có kiểm soát
    -> giao diện tra cứu và phân tích
```

Các nguồn có thể có cách triển khai khác nhau, nhưng phải mô tả ai kiểm soát từng bước, độ bền nào được bảo đảm và điểm nào có thể mất dữ liệu.

### 5.1. Thời gian và thứ tự

Nên giữ riêng thời điểm sự kiện tại nguồn và thời điểm tiếp nhận. Đồng hồ các nguồn cần được quản lý; độ lệch hoặc nguồn thời gian không đáng tin phải được nhận diện.

Số thứ tự theo phiên hoặc nguồn và định danh lần khởi động có thể hỗ trợ phát hiện khoảng trống, trùng lặp hoặc khởi động lại collector. Không suy ra một thứ tự toàn cục tuyệt đối chỉ từ timestamp của nhiều máy.

Sự kiện đến muộn cần giữ thời điểm gốc và thông tin tiếp nhận. Không sửa mốc thời gian để bản ghi trông như đã được chuyển đúng hạn.

### 5.2. Tính toàn vẹn và tính xác thực

Quyền sửa, xóa hoặc tắt log phải được giới hạn và giám sát. Có thể dùng nơi lưu chỉ cho ghi thêm, cơ chế bảo vệ lưu giữ hoặc biện pháp tương đương theo yêu cầu, nhưng phải đánh giá cả tài khoản quản trị chính nền tảng lưu trữ.

Hash, chữ ký hoặc chuỗi liên kết sự kiện có thể hỗ trợ phát hiện thay đổi trong phạm vi thiết kế. Chúng không tự chứng minh điểm capture đã nhìn thấy mọi hành động hoặc nội dung được ghi là sự thật của hệ thống đích.

Bản ghi được bảo vệ sau khi đã giảm dữ liệu chứng minh tính toàn vẹn của bản được lưu, không chứng minh từng byte của đầu vào ban đầu nếu đầu vào đó không được giữ. Điều này cần được hiểu rõ khi diễn giải bằng chứng.

Sự kiện từ client không đáng tin không được tự khai actor, role hoặc quyết định cấp quyền mà không có xác minh. Những trường có thẩm quyền cần đến từ thành phần chịu trách nhiệm hoặc có cách kiểm chứng phù hợp.

### 5.3. Gửi lại và chống mất dữ liệu

Gửi lại sau lỗi phải có cơ chế nhận diện trùng lặp theo nguồn và định danh sự kiện. Nếu cùng định danh nhưng nội dung mâu thuẫn, không âm thầm bỏ một bản; cần xử lý như vấn đề dữ liệu hoặc tính toàn vẹn.

Buffer phải có giới hạn dung lượng, thời gian tồn tại, quyền truy cập và cảnh báo. Nếu đầy, không được âm thầm ghi đè bằng chứng bắt buộc rồi tiếp tục báo hệ thống hoạt động bình thường.

Log viewer cũng phải xử lý nội dung không đáng tin như dữ liệu. Ký tự xuống dòng, escape của terminal hoặc nội dung đánh dấu không được làm giả thêm sự kiện hay thực thi trong giao diện xem.

## 6. Quy định khi mất khả năng ghi log

Chính sách phải nêu rõ hành vi trước và sau khi hành động đã bắt đầu. Không dùng một quy tắc mơ hồ như “nếu log lỗi thì thử lại” cho mọi tình huống.

| Tình huống | Quyết định cần được định nghĩa |
| --- | --- |
| Chưa thực thi thao tác rủi ro cao và chưa đạt bảo đảm ghi nhận bắt buộc | Chặn luồng thông thường hoặc chuyển sang cơ chế khẩn cấp đủ điều kiện |
| Kênh tập trung lỗi nhưng buffer bền được phép vẫn an toàn | Có được tiếp tục không, trong phạm vi và giới hạn nào |
| Buffer đầy hoặc không còn bảo đảm tính toàn vẹn | Dừng tiếp nhận hành động cần bảo đảm đó và cảnh báo theo chính sách |
| Lệnh đã chạy nhưng mất sự kiện kết thúc | Ghi trạng thái chưa xác định, đối soát tại đích và xử lý khoảng trống bằng chứng |
| Mất log trong khi cần khôi phục dịch vụ | Áp dụng break-glass đã quy định, với bằng chứng thay thế và rà soát |

Với thao tác nhạy cảm, có thể yêu cầu bằng chứng tiền thực thi đã được ghi bền tại vị trí đủ tin cậy trước khi cho bắt đầu. “Đã ghi bền” phải có nghĩa cụ thể: bộ nhớ của tiến trình, một yêu cầu mạng đã gửi và bản ghi được nơi lưu xác nhận là các mức bảo đảm khác nhau.

Không nhất thiết mọi thao tác đều chờ đồng bộ với kho tập trung. Nếu cho phép buffer cục bộ, phải đánh giá việc ai có thể sửa hoặc xóa buffer, khả năng mất máy và giới hạn thời gian chưa chuyển được.

Nếu lệnh đã thực hiện nhưng log kết quả thất bại, không thể coi như chưa có tác động. Không tự chạy lại lệnh chỉ để có một bản ghi đẹp hơn; thao tác lặp có thể gây thay đổi lần nữa.

## 7. Quyền truy cập, lưu giữ và bảo vệ bằng chứng

### 7.1. Phân tách vai trò

Người thực hiện hành động đặc quyền không nên đồng thời có quyền xóa bằng chứng của chính hành động đó. Người vận hành collector, người tra cứu và người quản trị lưu trữ cần được phân quyền theo trách nhiệm.

Truy cập và xuất log cũng cần được ghi nhận. Quyền điều tra có thể giới hạn theo phạm vi vụ việc, tài sản, thời gian hoặc nhóm dữ liệu, thay vì mở toàn bộ transcript cho mọi người có vai trò quản trị.

Thông tin xác thực của collector và khóa bảo vệ dữ liệu log phải được quản lý như tài sản nhạy cảm. Thay đổi cấu hình ghi nhận, chính sách lọc, quyền truy cập và cơ chế lưu giữ cần có lịch sử cùng thẩm quyền phù hợp.

### 7.2. Thời hạn lưu và khả năng khôi phục

Thời gian lưu phải được xác định theo mục đích, mức rủi ro, yêu cầu áp dụng của tổ chức và loại dữ liệu. Không mặc định lưu mọi nội dung vô thời hạn là lựa chọn tốt hơn.

Phải làm rõ thời gian có thể tra cứu nhanh, lưu trữ dài hơn nếu có, khả năng khôi phục và cách xóa khi hết hạn. Dữ liệu cần bảo toàn cho một cuộc điều tra phải được xử lý theo quyết định có thẩm quyền để tránh bị xóa theo lịch thông thường.

Nếu bản sao lưu hoặc dữ liệu xuất vẫn chứa bằng chứng, chúng cũng cần chính sách truy cập, lưu giữ và xóa phù hợp. Khả năng đọc lại bằng chứng sau khôi phục phải được kiểm chứng, không chỉ dựa vào thông báo sao lưu thành công.

## 8. Ví dụ sự kiện có cấu trúc

Đoạn JSON dưới đây là schema minh họa nội bộ, không phải định dạng chuẩn của một sản phẩm. Các định danh và thời gian đều là ví dụ.

```json
{
  "event_id": "event-10042",
  "action_id": "action-4307",
  "session_id": "session-8201",
  "request_id": "change-2601",
  "event_time": "2026-11-26T03:10:00Z",
  "actor_ref": "user-oncall-17",
  "execution_identity_ref": "principal-billing-ops",
  "target": {
    "asset_ref": "asset-app-pay-02",
    "service_name": "ContosoBillingAgent"
  },
  "operation": "service.restart",
  "command_name": "Restart-BillingAgent",
  "handler_version": "billing-ops-v4",
  "capture_point": "management-endpoint",
  "authorization_decision": "allow",
  "phase": "execution_finished",
  "reported_result": "success",
  "resource_verification": "not_performed",
  "output_capture": "metadata_only",
  "command_log_policy_version": "cmdlog-v3",
  "authorization_policy_version": "pam-ops-v7"
}
```

Sự kiện nối được người gọi, danh tính thực thi, tài sản, chức năng và phiên bản áp dụng mà không chứa credential. Tên dịch vụ là đối tượng của hành động, không phải bằng chứng rằng người dùng được chọn tên dịch vụ tùy ý.

`reported_result` phản ánh kết quả do nguồn báo cáo. Vì `resource_verification` là `not_performed`, không được diễn giải bản ghi này thành bằng chứng ứng dụng thanh toán đã phục hồi. Nếu có bước kiểm tra sức khỏe được cho phép, ghi một sự kiện liên quan với nguồn và kết quả riêng.

Nếu lệnh bị từ chối, cần bản ghi quyết định và lý do phù hợp, nhưng không tạo giả sự kiện `execution_finished`. Nếu mất kết nối sau khi khởi chạy, phải giữ trạng thái chưa xác định cho tới khi có bằng chứng bổ sung.

## 9. Ví dụ áp dụng cho một phiên trực ca

Kỹ sư trực ca được cấp JIT để xem trạng thái và khởi động lại một dịch vụ trên `APP-PAY-02`. Endpoint JEA giới hạn chức năng; thành phần thực thi dùng danh tính riêng tại máy chủ.

Chính sách ghi nhận cho tình huống này cần quy định:

1. Liên kết danh tính người dùng, yêu cầu được duyệt, phiên JIT và danh tính thực thi.
2. Ghi cả thao tác được phép và yêu cầu vượt phạm vi bị từ chối.
3. Ghi chức năng cùng đối tượng được phép; không ghi giá trị bí mật của danh tính thực thi.
4. Phân biệt kết quả thao tác dịch vụ với kết quả kiểm tra sức khỏe ứng dụng.
5. Ghi trạng thái kết thúc hoặc khoảng trống bằng chứng nếu phiên bị gián đoạn.
6. Bảo vệ bằng chứng khỏi bị sửa hoặc xóa bằng quyền được cấp cho người trực ca.

Nếu người dùng tìm cách chuyển sang chức năng ngoài phạm vi, log quyết định giúp xác định điều gì bị chặn. Nếu chỉ có log tiến trình đã chạy, những nỗ lực bị chặn trước khi tạo tiến trình có thể không xuất hiện trong nguồn đó.

Nếu collector tập trung gián đoạn trong phiên, hệ thống phải áp dụng đúng quy tắc đã định về buffer hoặc chặn thao tác tiếp theo. Không âm thầm đổi sang chế độ không ghi nhận.

Khi hết JIT, cần nối bằng chứng phiên với kết quả hết hạn hoặc thu hồi phù hợp. Bản ghi “phiên đã đóng” tại gateway chưa đủ để chứng minh không còn tác vụ hoặc đường truy cập độc lập ở đích.

## 10. Trách nhiệm, ngoại lệ và xử lý khoảng trống

| Vai trò | Trách nhiệm chính |
| --- | --- |
| Chủ chính sách | Xác định mục tiêu, phạm vi, dữ liệu được ghi và mức bảo đảm |
| Chủ hệ thống hoặc dịch vụ | Xác nhận nguồn capture, ý nghĩa hành động và tác động vận hành |
| Đội PAM và nền tảng log | Triển khai, giám sát, đối soát, khôi phục và bảo vệ đường thu thập |
| Đội giám sát hoặc điều tra | Đánh giá bất thường, khai thác bằng chứng đúng thẩm quyền |
| Chủ quản dữ liệu liên quan | Phối hợp phân loại, quyền xem và xử lý nội dung nhạy cảm |
| Người chấp nhận ngoại lệ | Chấp thuận rủi ro trong scope và thời hạn được giao |

Ngoại lệ cho hệ thống chưa đủ khả năng ghi nhận cần có lý do, hành động chịu ảnh hưởng, biện pháp thay thế, người chịu trách nhiệm, hạn và mốc rà soát. Không gắn nhãn ngoại lệ rồi loại hệ thống khỏi thống kê bao phủ.

Khi có khoảng trống log, cần xác định nguồn, thời gian, principal và tài sản có thể bị ảnh hưởng. Thu thập bằng chứng bổ sung từ các nguồn còn tin cậy và phân biệt rõ dữ liệu quan sát trực tiếp với dữ liệu tái dựng.

Không chạy lại hành động để tái tạo một sự kiện lịch sử rồi coi như đó là bản gốc. Nếu bổ sung ghi nhận sau sự kiện, phải nêu nguồn, thời điểm bổ sung và giới hạn kết luận.

Nếu phát hiện bí mật trong log, cần kiểm soát quyền truy cập và bản sao, đánh giá nơi đã nhận dữ liệu, phối hợp xử lý credential và bảo toàn bằng chứng cần thiết. Chỉ che một dòng trên giao diện có thể chưa xử lý được những bản đã xuất hoặc chuyển tiếp.

## 11. Kiểm chứng chính sách trước khi vận hành

Bảng dưới đây là gợi ý xây dựng kiểm thử theo nền tảng và mức rủi ro. Nó không phải kết quả kiểm thử của một triển khai cụ thể.

| Tình huống | Điều cần xác minh |
| --- | --- |
| Hai người dùng cùng tài khoản đích qua PAM | Vẫn phân biệt được người nguồn và từng hành động |
| Lệnh bị chặn trước khi thực thi | Có sự kiện từ chối; không tạo giả kết quả chạy |
| Alias, pipeline, script nhiều dòng hoặc tác vụ API | Thể hiện đúng loại hành động và giới hạn quan sát |
| Shell builtin không tạo tiến trình mới | Khoảng trống của nguồn audit tiến trình được nhận diện và xử lý |
| Bí mật nằm trong đối số, output hoặc lỗi | Không lọt vào các nơi lưu ngoài phạm vi cho phép, kể cả buffer và hàng đợi lỗi |
| Collector khởi động lại hoặc sự kiện được gửi lại | Phát hiện trùng lặp, khoảng trống và lần khởi động phù hợp |
| Đồng hồ nguồn lệch hoặc sự kiện đến muộn | Giữ được thời điểm và dấu hiệu độ tin cậy, không sửa lịch sử |
| Kênh tập trung lỗi, buffer đầy | Hành vi đúng chính sách và có cảnh báo |
| Timeout sau khi lệnh có thể đã chạy | Không tự kết luận thất bại hoặc lặp lệnh tùy ý |
| Người có quyền quản trị tác vụ thử sửa log | Bị giới hạn hoặc có bằng chứng giám sát theo thiết kế |
| Nội dung có ký tự điều khiển hoặc markup | Viewer không diễn giải như lệnh, nội dung hoạt động hay sự kiện giả |
| Khôi phục bằng chứng từ lưu trữ | Có thể đọc, nối và xác minh phạm vi toàn vẹn cần thiết |

Cần kiểm tra hiệu năng và backpressure ở tải dự kiến. Một cấu hình đủ chức năng nhưng làm đầy buffer khi có sự cố hàng loạt có thể mất bằng chứng đúng thời điểm quan trọng.

Thay đổi agent, shell, giao thức, schema, bộ lọc hoặc nơi lưu cần kích hoạt kiểm chứng các giả định bị ảnh hưởng. Không chỉ kiểm tra sự kiện đến được dashboard; cần kiểm tra ý nghĩa, độ đầy đủ và dữ liệu không được phép xuất hiện.

## 12. Đo lường và duy trì chính sách

Các chỉ số hữu ích gồm:

- Tỷ lệ đường quản trị và tài sản trong phạm vi có nguồn ghi nhận đã xác minh.
- Tỷ lệ sự kiện nối được người nguồn, danh tính thực thi, yêu cầu và đích.
- Độ trễ tiếp nhận, tuổi buffer, khoảng trống thứ tự và lỗi chuyển tiếp.
- Số hành động không có kết quả cuối, sai khác giữa nguồn PAM và nguồn đích.
- Sự cố lộ dữ liệu nhạy cảm, truy cập hoặc xuất log ngoài phạm vi cho phép.
- Ngoại lệ quá hạn, khoảng trống chưa xử lý và thời gian khôi phục thu thập.

Mẫu số phải phản ánh phạm vi đã biết và phần chưa quan sát được. Không thể tính độ đầy đủ bằng cách lấy số lệnh đã ghi chia cho chính số lệnh mà logger nhìn thấy rồi kết luận mọi hoạt động đều được bao phủ.

Heartbeat cho biết thành phần còn gửi tín hiệu, nhưng không tự chứng minh mọi hành động được capture. Nên đối chiếu thêm nguồn độc lập và các tình huống kiểm chứng được quản lý.

Chính sách cần có chủ quản, phiên bản, ngày hiệu lực, phạm vi, điều kiện ngoại lệ và lịch rà soát. Mỗi thay đổi phải nối được tới cấu hình triển khai và bằng chứng tương ứng để biết quy tắc nào áp dụng tại thời điểm một hành động xảy ra.

Command logging policy có hiệu lực khi tạo được bằng chứng đúng nghĩa về hành động đặc quyền, bảo vệ dữ liệu trong chuỗi ghi nhận và làm rõ cách xử lý khi bằng chứng không đầy đủ. Giá trị kiểm toán nằm ở khả năng truy vết và kiểm chứng đó, không chỉ ở số lượng dòng log đã thu thập.
