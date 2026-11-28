# Command recording

## 1. Command recording trong Network PAM

Command recording là việc ghi nhận các lệnh hoặc thao tác quản trị đi qua một điểm quan sát. Trong Network PAM, mục tiêu là giúp tổ chức đối soát ai đã yêu cầu thao tác gì, trên thiết bị nào, trong phiên và phạm vi quyền nào.

Một bản ghi tốt cần hỗ trợ điều tra và kiểm toán mà không tự trở thành nguồn lộ credential. Nó cũng phải thể hiện đúng giới hạn: thấy người dùng gửi lệnh không đồng nghĩa thiết bị đã thực thi thành công, cấu hình đã được lưu hoặc lưu lượng đã thay đổi đúng ý định.

Ví dụ, một kỹ sư được cấp phiên vào Edge-A để kiểm tra uplink. Hệ thống có thể thu:

- Danh tính cá nhân ở cổng PAM.
- Định danh phiên truy cập.
- Lệnh quan sát được.
- Quyết định authorization.
- Phản hồi từ thiết bị.
- Bằng chứng trạng thái sau tác vụ.
- Thời điểm kết thúc và tình trạng bản ghi.

Những dữ liệu này có thể đến từ nhiều nguồn. Không nên gọi tất cả là “ghi lại đầy đủ lệnh” nếu mới có video terminal hoặc log đăng nhập.

Sau bài học, bạn có thể thiết kế phạm vi recording, liên kết danh tính, bảo vệ pipeline thu thập và kiểm chứng độ đầy đủ của bằng chứng trong phạm vi đã công bố.

## 2. Phân biệt recording, accounting và authorization

| Khái niệm | Câu hỏi chính | Giới hạn |
|---|---|---|
| Authentication log | Ai đã xác thực vào đâu? | Chưa cho biết thao tác tiếp theo |
| Authorization record | Thao tác có được phép không? | Chưa chứng minh nó đã được thực hiện |
| Command accounting | Thiết bị hoặc hệ thống báo hoạt động nào? | Phụ thuộc dữ liệu nguồn gửi và cấu hình |
| Session recording | Luồng tương tác nào được điểm ghi nhìn thấy? | Không tự bao phủ mọi kênh và đường đi vòng |
| Configuration audit | Trạng thái hoặc phần cấu hình nào đã đổi? | Cần liên kết thêm để quy trách nhiệm |
| Operational verification | Hệ thống đang hoạt động ra sao? | Không tự thay lịch sử thao tác |

TACACS+ tách authentication, authorization và accounting; một triển khai có thể chưa dùng đầy đủ cả ba. Vì vậy, có xác thực tập trung chưa đủ để kết luận đã có accounting từng lệnh. [RFC 8907: TACACS+](https://www.rfc-editor.org/rfc/rfc8907.html).

Trong thiết kế PAM, nên dùng các nguồn bổ sung cho nhau:

~~~text
Yêu cầu và phê duyệt
    -> Phiên của người dùng
    -> Quyết định quyền
    -> Lệnh hoặc operation được quan sát
    -> Phản hồi và kết quả
    -> Trạng thái cấu hình liên quan
    -> Kết thúc phiên và chất lượng bằng chứng
~~~

Chuỗi này mô tả các câu hỏi cần trả lời. Không có nghĩa mọi giao thức tự cung cấp đủ tất cả dữ liệu.

## 3. Ghi ở đâu quyết định nhìn thấy gì

### 3.1. Tại PAM hoặc bastion

Một gateway có thể quan sát phiên mà nó thực sự xử lý. Nếu chỉ chuyển tiếp một kênh mã hóa mà không thấy nội dung, nó không tự có câu lệnh rõ để ghi.

Cần xác định:

- Gateway kết thúc giao thức ở đâu?
- Có nhìn thấy input, output hay chỉ metadata kết nối?
- Có biết danh tính backend trên thiết bị không?
- Có nhìn thấy mọi channel của connection không?
- Người dùng có thể mở một kênh không đi qua recorder không?

### 3.2. Tại thiết bị

Thiết bị có thể ghi các hoạt động theo facility, severity và cấu hình riêng.

Ví dụ, tài liệu Junos phân biệt mức ghi interactive-commands: info bao phủ lệnh CLI ở chế độ vận hành và cấu hình, trong khi notice tập trung hơn vào rollback và commit. Không dùng tên file log để suy ra phạm vi thu thập. [Juniper: Check the Commands That Users Are Entering](https://www.juniper.net/documentation/us/en/software/junos/network-mgmt/topics/concept/users-commands-entered-checking.html).

Đây là ví dụ của một nền tảng, không phải cú pháp hay hành vi chung cho mọi thiết bị.

### 3.3. Tại AAA

Accounting do thiết bị gửi có thể bổ sung định danh người dùng, tác vụ và thông tin phiên. Cần kiểm tra khi nào sự kiện được tạo và những trường nào thực sự có.

Không mặc định một định danh giao thức AAA trùng một-một với phiên con người ở PAM. Bản ánh xạ phải được hiểu và kiểm chứng.

### 3.4. Tại controller hoặc automation

Một controller có thể gửi thay đổi tới nhiều thiết bị bằng một danh tính máy. Khi đó cần nối:

- Người hoặc hệ thống yêu cầu.
- Revision cấu hình hoặc mã.
- Job thực thi.
- Danh tính automation.
- Thiết bị đích.
- Request và kết quả tại từng thiết bị.

Chỉ ghi tài khoản máy trên thiết bị chưa đủ để biết ai đã phê duyệt hoặc thay nguồn cấu hình.

## 4. Xác định phạm vi kênh trước khi công bố coverage

Một tổ chức cần một ma trận các đường quản trị:

| Kênh | Nguồn recording cần xem xét |
|---|---|
| SSH tương tác | Recorder nhìn thấy phiên và log thiết bị |
| SSH chạy một lệnh không tương tác | Metadata request, lệnh thực thi và nguồn kết quả |
| Shell bên trong hệ điều hành thiết bị | Cơ chế shell audit riêng nếu có |
| Console vật lý hoặc console server | Mapping cổng, người dùng và thao tác tại thiết bị |
| Giao diện web | Request hoặc action log, danh tính và kết quả |
| NETCONF hoặc RESTCONF | Operation, đích dữ liệu và kết quả được hỗ trợ |
| Controller hoặc API tự động | Job, phiên bản thay đổi và bằng chứng từng đích |
| Kênh khẩn cấp | Cơ chế bằng chứng riêng và đối soát sau sự kiện |

SSH có các request shell, exec và subsystem. Do đó, một recorder chỉ được thử với terminal tương tác chưa chứng minh đã bao phủ mọi cách sử dụng SSH. [RFC 4254: SSH Connection Protocol](https://www.rfc-editor.org/rfc/rfc4254.html).

Một số nền tảng cũng có cấu hình riêng cho logging shell. Ví dụ, Junos có statement dành cho lệnh shell với giới hạn hỗ trợ theo phiên bản; không suy rằng bật log CLI tự đồng nghĩa ghi được mọi lệnh trong shell. [Juniper: Shell Logging](https://www.juniper.net/documentation/us/en/software/junos/cli-reference/topics/ref/statement/shell-edit-system-syslog.html).

### Coverage phải gắn với đối tượng cụ thể

Một kết luận có thể kiểm chứng:

> Các phiên CLI tương tác qua gateway G tới nhóm thiết bị lab được ghi input và output theo cấu hình R; API quản trị được thu bằng nguồn riêng; console khẩn cấp có quy trình đối soát riêng.

Một kết luận quá rộng:

> Mọi thao tác quản trị đều đã được ghi đầy đủ.

Nếu một đường chưa được bao phủ, hãy ghi nhận khoảng trống và chủ sở hữu xử lý. Không loại nó khỏi inventory chỉ vì chưa có cơ chế thu thập.

## 5. Phân biệt phím gõ, lệnh được gửi và tác động

Một terminal là một luồng tương tác, không phải danh sách statement có cấu trúc hoàn hảo.

Người dùng có thể:

- Gõ rồi xóa trước khi gửi.
- Dùng lịch sử hoặc auto-complete.
- Dán nhiều dòng.
- Chuyển chế độ cấu hình.
- Nhập tham số qua prompt.
- Dùng lệnh rút gọn.
- Nhận output phân trang.
- Gọi script hoặc cơ chế thực thi khác.

Nếu parser của recorder ghép sai luồng input, câu lệnh được trích xuất có thể khác thao tác mà thiết bị nhận.

### Các mức quan sát nên tách rõ

~~~text
INPUT_OBSERVED
    Dữ liệu tương tác đã được điểm ghi nhìn thấy.

COMMAND_EXTRACTED
    Bộ phân tích tạo biểu diễn lệnh từ dữ liệu quan sát.

AUTHORIZATION_OBSERVED
    Có nguồn bằng chứng về quyết định quyền.

DEVICE_RESPONSE_OBSERVED
    Có phản hồi từ thiết bị.

EFFECT_VERIFIED
    Trạng thái liên quan đã được kiểm chứng bằng nguồn phù hợp.
~~~

Đây là các nhãn thiết kế minh họa, không phải trạng thái chuẩn của một sản phẩm.

Không tự chuyển DEVICE_RESPONSE_OBSERVED thành EFFECT_VERIFIED chỉ vì không thấy dòng lỗi. Một phản hồi có thể chưa nói đầy đủ về trạng thái lưu cấu hình hoặc hoạt động mạng.

### Ngữ cảnh phải đi cùng lệnh

Cùng một lệnh ngắn có thể mang ý nghĩa khác khi người dùng đang chọn một interface hoặc một nhánh cấu hình khác.

Nếu chỉ lưu chuỗi cuối cùng mà bỏ mất ngữ cảnh, người điều tra có thể hiểu sai tài nguyên bị tác động.

Cần ghi hoặc đối soát:

- Chế độ thao tác.
- Tài nguyên đang chọn nếu có thể xác định.
- Role hiệu lực.
- Các bước chuyển ngữ cảnh.
- Nguồn suy ra và mức chắc chắn.

Khi không xác định được, dùng giá trị unknown hoặc trạng thái chưa đủ bằng chứng, không bịa một ngữ cảnh để hoàn thiện báo cáo.

## 6. Liên kết danh tính từ người dùng tới thiết bị

Một bản ghi có chuỗi username chưa chắc chứng minh được cá nhân.

Cần phân biệt:

1. Danh tính xác thực tại cổng PAM.
2. Danh tính thiết bị nhận khi đăng nhập.
3. Role hoặc ngữ cảnh quyền khi thực thi.
4. Danh tính máy nếu đi qua automation.
5. Người yêu cầu và người phê duyệt thay đổi.

### Tài khoản dùng chung

Nếu nhiều người dùng cùng backend account, log thiết bị có thể chỉ thấy một tên.

PAM có thể bổ sung mapping phiên, nhưng cần kiểm chứng:

- Credential có được dùng trực tiếp ngoài PAM không?
- Có nhiều phiên đồng thời dưới cùng tài khoản không?
- Định danh phiên ở hai phía được nối thế nào?
- Gateway có giữ độc quyền hoặc ngữ cảnh đủ để phân biệt không?
- Có thể sửa metadata để giả mapping không?
- Console và đường khẩn cấp có dùng cùng credential không?

Không gọi backend account chia sẻ là danh tính cá nhân chỉ vì giao diện PAM có tên người.

### Không tin dữ liệu do người dùng tự khai

Tên client, nhãn phiên hoặc mã yêu cầu người dùng nhập có ích để tìm kiếm nhưng không tự là bằng chứng danh tính hay phê duyệt.

Mã tác vụ phải đối chiếu được hồ sơ hợp lệ. Một người không nên có khả năng tự ghi “approved” vào metadata rồi biến nó thành quyết định quyền.

### Định danh bền vững và thời gian

Địa chỉ IP có thể được dùng chung qua proxy hoặc NAT. Một PID hay session number có thể chỉ có ý nghĩa trong phạm vi một thiết bị và khoảng thời gian.

Nên có mã phiên logic, định danh tài nguyên, thông tin nguồn và mốc thời gian đủ để đối soát. Không chỉ dựa vào việc hai sự kiện xảy ra gần nhau để quy một lệnh cho một người.

## 7. Mô hình sự kiện có cấu trúc

Một bản ghi có cấu trúc giúp tách sự kiện khỏi văn bản hiển thị.

Ví dụ sau dùng dữ liệu giả và tên thao tác mô tả, không phải log thật hoặc cú pháp lệnh của một hãng:

~~~json
{
  "event_id": "EVT-EX-071-00012",
  "event_type": "network.command.observed",
  "logical_session_id": "SESSION-EX-071",
  "source_stream_id": "edge-a-cli-stream-3",
  "sequence": 12,
  "request_reference": "INCIDENT-EX-017",
  "actor_reference": "person-example-a",
  "backend_account_reference": "network-observer-example",
  "device_reference": "edge-a-training",
  "channel": "ssh-interactive",
  "observed_role": "network-observer",
  "command": {
    "display_text": "inspect interface uplink-a status",
    "text_kind": "normalized-example",
    "context_reference": "CTX-EX-071-02",
    "parser_revision": "parser-example-4"
  },
  "evidence": {
    "input_observed": true,
    "authorization_decision": "not-observed",
    "device_response_observed": true,
    "effect_verified": false
  },
  "timestamps": {
    "source_time": "<timestamp có múi giờ nếu có>",
    "collector_received_time": "<timestamp có múi giờ>"
  },
  "redaction": {
    "policy_revision": "REDACT-EX-006",
    "applied": true
  }
}
~~~

### Ý nghĩa của những trường quan trọng

- event_id giúp xử lý trùng và tham chiếu bằng chứng.
- source_stream_id cùng sequence hỗ trợ phát hiện bất thường trong một luồng.
- logical_session_id nối dữ liệu từ cổng tới các nguồn khác.
- text_kind cho biết đây là chuỗi gốc hay chuỗi được chuẩn hóa.
- parser_revision cho phép hiểu cách trích xuất lệnh.
- evidence tách điều được nhìn thấy khỏi điều chưa xác minh.
- redaction mô tả cách dữ liệu nhạy cảm đã được xử lý.

Một sequence do collector tự gán chỉ đếm sự kiện đã nhận. Nó không phát hiện được những sự kiện nguồn chưa từng gửi nếu không có thêm cơ chế đối chiếu.

Không mặc định một schema đầy đủ là bằng chứng nguồn dữ liệu đầy đủ.

## 8. Pipeline thu thập và các điểm có thể mất dữ liệu

~~~mermaid
flowchart LR
    A[Thiết bị hoặc recorder] --> B[Hàng đợi hoặc buffer]
    B --> C[Kênh vận chuyển được bảo vệ]
    C --> D[Collector]
    D --> E[Parser và chuẩn hóa]
    E --> F[Lưu trữ bằng chứng]
    F --> G[Tìm kiếm và xem lại]
    H[Kiểm tra sức khỏe và chất lượng] --> B
    H --> D
    H --> F
~~~

Mỗi bước có lỗi riêng:

| Điểm | Ví dụ rủi ro |
|---|---|
| Nguồn | Facility hoặc severity chưa thu tác vụ cần thiết |
| Buffer | Đầy hàng đợi hoặc mất khi khởi động lại |
| Transport | Gián đoạn, gửi trùng, nguồn giả hoặc dữ liệu bị sửa |
| Collector | Chấp nhận request nhưng chưa lưu bền vững |
| Parser | Sai encoding, mất ngữ cảnh hoặc loại nhầm dữ liệu |
| Lưu trữ | Sai quyền truy cập, mất dữ liệu hoặc thay đổi ngoài thẩm quyền |
| Index | Tìm kiếm không thấy dù bản gốc còn tồn tại |
| Viewer | Hiển thị sai thứ tự hoặc xử lý nội dung không an toàn |

Kết nối TCP còn sống không chứng minh mọi sự kiện đã được lưu bền vững. Một HTTP response thành công cũng cần được hiểu: nó xác nhận nhận vào bộ nhớ, ghi hàng đợi hay hoàn tất lưu trữ?

### Trạng thái chất lượng cần được giữ

Một phiên có thể được đánh dấu:

- Recording đang hoạt động.
- Recording có khoảng trống.
- Nguồn ghi bị gián đoạn.
- Parser chưa hiểu một phần nội dung.
- Đã nhận bản kết thúc nhưng chưa đối soát đủ.
- Đã kiểm chứng trong phạm vi thu thập.

Không im lặng bỏ phần lỗi rồi xuất một timeline trông hoàn chỉnh.

## 9. Bảo vệ truyền dẫn và nguồn sự kiện

Syslog có định dạng gồm các trường header và dữ liệu có cấu trúc, nhưng định dạng thông điệp không tự xác thực nguồn phát. [RFC 5424: The Syslog Protocol](https://www.rfc-editor.org/rfc/rfc5424.html).

Cần bảo vệ:

- Nguồn nào được phép gửi.
- Collector nào được nguồn tin cậy.
- Danh tính và trust của hai đầu theo cơ chế sử dụng.
- Đường truyền và khả năng phát hiện lỗi.
- Credential thiết bị dùng để gửi.
- Chính sách làm mới certificate hoặc key.

RFC 5425 định nghĩa syslog qua TLS. Khi sử dụng, phải kiểm tra cấu hình xác thực và trust thực tế, không chỉ xác nhận cổng TLS đang mở. [RFC 5425: TLS Transport Mapping for Syslog](https://www.rfc-editor.org/rfc/rfc5425.html).

Với dữ liệu AAA, cũng cần biết đường thiết bị–AAA có được bảo vệ không. RFC 9887 bổ sung TACACS+ qua TLS 1.3; việc dùng phụ thuộc khả năng và cấu hình của cả hai phía. [RFC 9887: TACACS+ over TLS 1.3](https://www.rfc-editor.org/rfc/rfc9887.html).

Các cơ chế truyền dẫn không tự chứng minh lệnh đã được thực thi. Chúng bảo vệ một chặng trao đổi; vẫn cần tin cậy nguồn tạo sự kiện và kiểm chứng kết quả khi mục tiêu yêu cầu.

## 10. Che bí mật trước khi bản ghi trở thành kho credential

Command recording có thể thu cả thông tin nhạy cảm trong input lẫn output:

- Mật khẩu nhập qua tham số.
- Shared secret AAA.
- Token trong URL hoặc header.
- Private key hoặc dữ liệu certificate liên quan.
- Nội dung cấu hình.
- Thông tin topology và địa chỉ nội bộ.
- Dữ liệu từ các lệnh xuất trạng thái hoặc chẩn đoán.

RFC 8907 ghi nhận sự khác biệt về độ chi tiết accounting và nguy cơ một số triển khai đưa mật khẩu hoặc khóa vào log. Vì vậy, không giả định nguồn đã tự che mọi bí mật. [RFC 8907: Accounting Security](https://www.rfc-editor.org/rfc/rfc8907.html#section-10.4).

### Không echo chưa chắc không ghi

Một prompt không hiển thị mật khẩu trên màn hình không tự chứng minh recorder không thu input. Ngược lại, recorder chỉ thu output có thể không thấy dữ liệu input ở prompt đó.

Cần kiểm tra cơ chế thật của nguồn ghi. Không dùng ảnh chụp màn hình thiếu mật khẩu làm bằng chứng toàn bộ pipeline không giữ mật khẩu.

### Thiết kế redaction

Một chính sách cần chỉ rõ:

1. Loại dữ liệu phải loại bỏ hoặc che.
2. Điểm redaction: nguồn, gateway, collector hay viewer.
3. Ai quản lý mẫu và phiên bản.
4. Cách xử lý cú pháp hoặc output chưa hiểu.
5. Bản gốc có được lưu không, nếu có thì ở đâu và ai đọc được.
6. Các chỉ mục, bản sao và file xuất có cùng được xử lý không.
7. Bằng chứng cho thấy redaction đã chạy.

Che tại viewer không xóa bí mật khỏi bản gốc, index hoặc dữ liệu đã xuất.

### Giữ khả năng điều tra mà không giữ giá trị bí mật

Có thể ghi:

~~~text
operation = thay credential AAA
target = thiết bị lab đã xác định
actor = danh tính đã xác minh
credential_reference = tham chiếu quản trị
secret_value = không lưu
result = theo nguồn bằng chứng thực tế
redaction_policy = phiên bản đã áp dụng
~~~

Không lưu hash của một bí mật yếu rồi coi như đã loại bỏ rủi ro. Giá trị có không gian đoán nhỏ có thể bị dò bằng cách so sánh hash.

Nếu cần giữ một bản gốc nhạy cảm theo nhu cầu đã được quyết định, nó phải có phạm vi truy cập và vòng đời riêng, không nằm mặc định trong hệ thống tìm kiếm cho mọi người.

### Thử redaction bằng dữ liệu giả

Trong lab, dùng chuỗi kiểm thử giả được nhận diện rõ để xem nó có xuất hiện ở:

- Recording nguồn.
- Hàng đợi.
- Log collector.
- Index.
- Viewer.
- File xuất.
- Backup.

Không dùng mật khẩu production thật làm mẫu thử.

## 11. Toàn vẹn bản ghi không đồng nghĩa đầy đủ hoặc đúng sự thật

Một kiểm tra hash cho biết dữ liệu có khớp với giá trị đối chiếu hay không. Nó không tự chứng minh dữ liệu là thật nếu người sửa được cả bản ghi lẫn giá trị đối chiếu.

Chữ ký hoặc chuỗi hash có thể hỗ trợ phát hiện sửa đổi trong phạm vi thiết kế. Cần bảo vệ khóa ký, điểm neo đối chiếu và metadata liên quan.

### Ba câu hỏi tách biệt

| Thuộc tính | Câu hỏi |
|---|---|
| Toàn vẹn | Dữ liệu đã lưu có bị đổi ngoài cơ chế cho phép không? |
| Đầy đủ | Những sự kiện cần thu có bị thiếu không? |
| Đúng nguồn và ngữ nghĩa | Sự kiện có đến từ nguồn tin cậy và mô tả đúng điều nó khẳng định không? |

Một file được ký hợp lệ vẫn có thể thiếu một phần phiên trước lúc bắt đầu ghi. Một nguồn bị chiếm quyền cũng có thể tạo dữ liệu sai rồi ký bằng khóa mà nó điều khiển.

### Các biện pháp bổ sung

- Phân tách người quản trị thiết bị với người quản trị kho bằng chứng.
- Giới hạn quyền sửa, xóa và đổi thời gian lưu giữ.
- Ghi audit cho việc đọc, xuất và thay cấu hình recording.
- Đối chiếu số phiên mở với số bản ghi bắt đầu và kết thúc.
- Theo dõi khoảng trống theo stream nếu nguồn hỗ trợ.
- Kiểm tra buffer, queue và lỗi parser.
- Bảo vệ metadata và khóa xác minh.
- Kiểm tra khả năng khôi phục dữ liệu trong phạm vi được phép.

Một kho “append-only” vẫn cần đánh giá ai thay được cấu hình hoặc khóa bảo vệ. Tên tính năng không thay bằng chứng quyền quản trị.

## 12. Thời gian, thứ tự và sự kiện trùng

Nguồn thiết bị, AAA, PAM và collector có thể có đồng hồ khác nhau hoặc độ trễ vận chuyển.

Nên giữ những mốc cần thiết, ví dụ:

- Thời gian do nguồn cung cấp.
- Thời gian collector nhận.
- Thời gian lưu bền vững nếu hệ thống có.
- Mã stream và sequence trong phạm vi phù hợp.
- Thông tin chất lượng đồng hồ nếu thực sự có nguồn xác minh.

Không sắp xếp toàn bộ sự kiện theo một timestamp rồi coi đó là thứ tự nhân quả chắc chắn.

### Ví dụ

Một sự kiện từ thiết bị tới chậm hơn log kết thúc ở PAM. Điều đó chưa chứng minh lệnh được thực hiện sau khi phiên đã đóng; có thể nguồn hoặc đường vận chuyển chậm.

Ngược lại, cũng không được tự giải thích mọi lệnh sau hạn là “do log chậm”. Cần đối chiếu phiên, thời gian nguồn, thứ tự request và khả năng thiết bị còn session.

### Xử lý trùng và replay

Đường vận chuyển có retry có thể gửi một sự kiện nhiều lần. Hệ thống cần giữ định danh đủ để phân biệt:

- Một sự kiện được gửi lại.
- Người dùng thực sự thực hiện cùng lệnh lần nữa.
- Hai nguồn khác nhau báo cùng một tác vụ.
- Dữ liệu bị phát lại ngoài ý định.

Không xóa mọi dòng có cùng command text trong một khoảng thời gian. Hai lần thao tác giống nhau có thể là hai hành động thật.

Việc loại trùng cần có quy tắc rõ và giữ khả năng đối chiếu bản gốc.

## 13. Ghi command không tự xác nhận thay đổi cấu hình

Một điều tra cần xem từng giai đoạn:

~~~text
Đã nhập hoặc gửi
    -> Được cho phép nếu có nguồn authorization
    -> Thiết bị chấp nhận
    -> Thay đổi có hiệu lực
    -> Trạng thái lưu phù hợp mô hình nền tảng
    -> Chức năng mạng được kiểm chứng
~~~

Trong một nền tảng dùng candidate và commit, lệnh sửa candidate không đồng nghĩa cấu hình chạy đã đổi. Trong kiến trúc controller, cấu hình trực tiếp có thể bị reconcile lại.

Cần hiểu mô hình cụ thể của tài nguyên đang quản lý.

### Đối chiếu recording với diff

Ví dụ, yêu cầu chỉ cho phép sửa mô tả của một interface thử nghiệm. Recording cho thấy một phiên thao tác cấu hình, nhưng diff còn có thay đổi AAA.

Kết luận đúng là cần điều tra phần thay đổi ngoài yêu cầu. Không kết luận mọi dòng trong diff đều thuộc cùng người chỉ vì xảy ra trong cửa sổ đó; có thể còn phiên khác hoặc automation.

Cần nối:

- Revision cấu hình trước và sau.
- Thời gian áp dụng.
- Phiên hoặc job có liên quan.
- Thao tác đồng thời.
- Nguồn quản lý cấu hình.
- Phê duyệt và phạm vi tác vụ.

### Trạng thái chưa biết phải được thể hiện

Nếu phiên mất kết nối sau khi gửi thao tác nhưng trước phản hồi, có thể chưa biết thiết bị đã áp dụng tới đâu.

Không tự đánh dấu FAILED theo nghĩa “không có tác động” rồi chạy lại toàn bộ. Cần đọc trạng thái và đánh giá khả năng thực hiện trùng trước bước tiếp theo.

Recording giúp đặt câu hỏi và tìm bằng chứng, không thay thế mọi kiểm chứng tại thiết bị.

## 14. Recording khi collector hoặc nguồn ghi gặp lỗi

Độ sẵn sàng và yêu cầu bằng chứng cần được quyết định trước sự cố.

Một chính sách nên xác định:

- Phiên mới có được mở khi nguồn ghi bắt buộc không hoạt động không?
- Phiên đang mở tiếp tục trong điều kiện nào?
- Buffer lưu ở đâu, giới hạn bao nhiêu và có được bảo vệ không?
- Khi buffer đầy thì làm gì?
- Ai nhận cảnh báo?
- Có đường khẩn cấp riêng không?
- Sau khi phục hồi, dữ liệu được đối soát thế nào?

Không để một lỗi ghi log âm thầm biến thành trạng thái “mọi thứ vẫn được recording đầy đủ”.

### Buffer và xác nhận bền vững

Một buffer có thể giúp chịu gián đoạn, nhưng cần biết nó có sống qua restart hay không và bí mật trong đó được bảo vệ thế nào.

Cần phân biệt:

- Nguồn đã tạo sự kiện.
- Sự kiện vào buffer.
- Collector đã nhận.
- Dữ liệu đã được lưu bền vững.
- Index đã sẵn sàng để tìm kiếm.

Dashboard có thể cần hiển thị riêng các mốc này thay vì một đèn xanh duy nhất.

### Truy cập khẩn cấp

Nếu có ngoại lệ để xử lý sự cố mạng khi hạ tầng recording lỗi, phải có thẩm quyền, scope, thời hạn và phương án bằng chứng thay thế.

Ví dụ có thể cần một log cục bộ được bảo vệ cùng đối soát cấu hình sau sự kiện. Không mô tả bằng chứng thay thế là tương đương ghi toàn bộ phiên nếu nó chỉ ghi một phần.

Sau khi hệ thống phục hồi, cần kiểm tra khoảng trống và hoàn tất hồ sơ ngoại lệ.

## 15. Kiểm soát người xem và xuất recording

Recording là dữ liệu nhạy cảm. Nó có thể bộc lộ topology, nội dung cấu hình, hoạt động quản trị và credential còn sót.

Quyền xem recording cũng cần least privilege:

- Ai được xem phiên của nhóm nào?
- Có cần lý do hoặc mã điều tra không?
- Có phân biệt xem metadata với xem nội dung không?
- Ai được xuất bản gốc?
- Ai quản lý redaction và thời gian lưu?
- Có audit việc đọc và xuất không?
- Khi người dùng đổi đội hoặc nghỉ việc, quyền xem được xử lý ra sao?

Không để một tài khoản vận hành có thể tùy ý xem mọi recording chỉ vì nó quản lý dashboard.

### Viewer phải xử lý nội dung như dữ liệu không tin cậy

Thiết bị hoặc phiên có thể tạo control character, chuỗi escape, dòng giả hoặc nội dung đánh lừa người xem.

Viewer và indexer cần xử lý encoding, tách trường và hiển thị an toàn. Không đưa nội dung recording trực tiếp vào một terminal có đặc quyền để “replay” bằng cách thực thi lại.

Bản xem an toàn có thể khác luồng gốc ở cách render; cần ghi rõ biến đổi để người điều tra không hiểu nhầm.

### File xuất và bản sao

Một file xuất có thể thoát khỏi chính sách quyền của hệ thống gốc.

Cần có:

- Lý do và người xuất.
- Phạm vi phiên.
- Mức redaction.
- Định danh hoặc hash công khai phù hợp để đối chiếu.
- Nơi giao nhận được phép.
- Vòng đời và trách nhiệm bảo vệ.

Không đưa bản recording chứa bí mật lên một nơi chia sẻ rộng chỉ để thuận tiện cộng tác.

## 16. Kiểm thử command recording bằng dữ liệu biết trước

Kiểm thử nên có tập thao tác giả hoặc ít tác động trong môi trường được phép. Mục tiêu là so sánh điều đã xảy ra với điều hệ thống tuyên bố ghi được.

### Một bộ kiểm thử minh họa

1. Mở phiên bằng danh tính thử nghiệm.
2. Thực hiện một lệnh quan sát đã chọn.
3. Gõ rồi xóa một phần trước khi gửi.
4. Dùng một dạng tương tác mà parser tuyên bố hỗ trợ.
5. Chuyển ngữ cảnh và thực hiện một thao tác khác.
6. Dùng một lệnh bị policy từ chối.
7. Thử một câu lệnh không hợp lệ để quan sát lỗi.
8. Gửi một chuỗi giả cần redaction theo chính sách.
9. Đóng phiên bình thường.
10. Đối chiếu bản ghi từ các nguồn liên quan.

Không đưa credential thật vào bước redaction. Không thử thao tác phá cấu hình chỉ để tạo log.

### Ma trận kiểm thử

| Ca kiểm thử | Điều cần chứng minh |
|---|---|
| Phiên SSH tương tác | Đúng người, thiết bị, phiên và input/output trong phạm vi đã nêu |
| SSH không tương tác | Đường này được ghi hoặc bị hạn chế theo thiết kế |
| Vào shell nếu được phép | Có nguồn ghi phù hợp, không suy từ log CLI |
| Console khẩn cấp | Có cơ chế bằng chứng đã công bố |
| Web hoặc API | Không bị bỏ sót khỏi hợp đồng coverage |
| Lệnh bị từ chối | Phân biệt quyết định quyền với lệnh đã thực hiện |
| Lệnh sai cú pháp | Không báo tác động thành công khi chỉ thấy input |
| Gõ rồi sửa | Chuỗi trích xuất không quy sai lệnh chưa gửi |
| Dán nhiều dòng | Thứ tự và ranh giới được xử lý theo khả năng |
| Hai phiên đồng thời | Không gộp nhầm người hoặc stream |
| Credential giả trong input/output | Được xử lý tại các điểm đã định |
| Collector mất kết nối | Có buffer, cảnh báo và trạng thái chất lượng đúng |
| Gửi lại sự kiện | Không nhân đôi tác vụ hoặc xóa nhầm thao tác thật |
| Đồng hồ nguồn lệch | Có cách nhận diện và giới hạn kết luận |
| Parser không hiểu | Không âm thầm bỏ dữ liệu |
| Người được ghi thử sửa log | Bị chặn theo ranh giới quyền |
| File xuất | Có redaction và audit phù hợp |
| Phiên kết thúc | Có mốc kết thúc và đối soát trạng thái bản ghi |

Một lần mở được video không chứng minh cả ma trận đạt.

### Coverage cần mẫu số

Chỉ số “có 500 recording” không nói có đủ không.

Có thể cần đối chiếu:

- Tổng số phiên thuộc phạm vi bắt buộc.
- Số phiên có bản bắt đầu và kết thúc.
- Số phiên có khoảng trống.
- Số nguồn chưa gửi.
- Số stream parser chưa hiểu.
- Số đường quản trị chưa được bao phủ.
- Số ngoại lệ quá hạn.

Các số này phải có nguồn và quy tắc tính. Đừng gộp phiên không có dữ liệu vào nhóm “không có thao tác” nếu chưa xác minh.

## 17. Runbook triển khai recording

### Bước 1: xác định mục tiêu bằng chứng

Chọn điều cần chứng minh: thao tác quản trị, thay đổi cấu hình, sử dụng credential hay điều tra truy cập ngoài tác vụ.

Không mặc định phải lưu mọi byte để đạt mọi mục tiêu.

### Bước 2: lập ma trận thiết bị và kênh

Gắn từng nhóm thiết bị, phiên bản và đường quản trị với nguồn ghi được hỗ trợ. Ghi rõ phần chưa bao phủ.

### Bước 3: thiết kế mapping danh tính

Xác định người nguồn, tài khoản backend, phiên PAM, sự kiện AAA và định danh thiết bị. Kiểm thử trường hợp tài khoản dùng chung và phiên đồng thời.

### Bước 4: cấu hình thu thập và bảo vệ

Thiết lập nguồn, mức thu thập, transport, collector, redaction, lưu trữ và quyền quản trị. Không đưa cấu hình của một hãng sang hãng khác mà không ánh xạ.

### Bước 5: kiểm thử trước khi mở rộng

Dùng tập thao tác biết trước, lỗi giả lập được phép và ca kiểm tra bí mật giả. Đối chiếu các nguồn, không chỉ giao diện tìm kiếm.

### Bước 6: triển khai theo nhóm

Theo dõi sức khỏe thiết bị, độ trễ, buffer, dung lượng và khả năng ghi. Logging quá nhiều có thể ảnh hưởng vận hành; cần điều chỉnh theo bằng chứng mà không âm thầm giảm coverage đã cam kết.

### Bước 7: đối soát định kỳ

Rà soát nguồn mới, đường mới, phiên bản parser, quyền người xem và ngoại lệ. Một upgrade hoặc thay controller có thể tạo loại sự kiện mới.

### Bước 8: kết thúc quyền tác vụ

Người triển khai recording có thể dùng đặc quyền cao. Sau change, cần kết thúc quyền tạm và bảo vệ lại cấu hình thu thập.

## 18. Hồ sơ quản trị recording minh họa

Mẫu dưới đây là hồ sơ thiết kế, không phải cấu hình nhập vào sản phẩm:

~~~yaml
network_command_recording:
  policy_reference: RECORD-EX-071
  accountable_owner: security-operations

  coverage:
    device_group_reference: network-training
    channels:
      - ssh-interactive
      - ssh-exec
      - management-api
    emergency_console_procedure: OOB-EX-071
    known_gaps_reference: GAPS-EX-071

  identity:
    personal_identity_required: true
    backend_account_mapping_reference: MAP-EX-071
    concurrent_session_test_reference: TEST-CONCURRENT-EX-071

  collection:
    source_configuration_revision: SOURCE-EX-004
    parser_revision: PARSER-EX-004
    transport_policy_reference: TRANSPORT-EX-071
    collector_acknowledgement_semantics: "<mốc được xác nhận thực tế>"
    recording_health_policy_reference: HEALTH-EX-071

  data_protection:
    redaction_policy_reference: REDACT-EX-006
    raw_secret_storage: forbidden
    raw_stream_retention_reference: "<nếu có>"
    viewer_access_policy_reference: VIEW-EX-071
    export_policy_reference: EXPORT-EX-071

  evidence:
    completeness_review_reference: REVIEW-EX-071
    integrity_verification_reference: INTEGRITY-EX-071
    configuration_effect_linkage_reference: DIFF-EX-071

  failure_handling:
    new_session_policy_reference: FAIL-EX-071
    active_session_policy_reference: ACTIVE-FAIL-EX-071
    gap_reconciliation_required: true
~~~

Một trường trong YAML không tự tạo kiểm soát. Mọi cam kết phải gắn với cấu hình, quyền và ca kiểm thử thực tế.

Ví dụ, raw_secret_storage: forbidden không có giá trị nếu collector vẫn ghi body đầy đủ vào debug log trước khi redaction.

## 19. Tình huống thực tế: có recording nhưng chưa biết ai đổi AAA

### Bối cảnh

Một thay đổi AAA ngoài kế hoạch được phát hiện trên Edge-A. PAM có video phiên của hai kỹ sư. Thiết bị dùng backend account chia sẻ. Một controller cũng có quyền sửa AAA qua API.

Dashboard tìm thấy chuỗi liên quan tới AAA trong output của một phiên và gắn cảnh báo cho kỹ sư đang xem cấu hình.

### Những điều cần kiểm tra

- Chuỗi đó là input hay output?
- Người dùng đang đọc cấu hình hay gửi thay đổi?
- Parser có phân biệt đúng hai hướng dữ liệu không?
- Tài khoản backend có đang được dùng trực tiếp ở nơi khác không?
- API của controller có bản ghi riêng không?
- Có diff và thời điểm áp dụng cấu hình không?
- Các đồng hồ và độ trễ log có đối soát được không?

Không quy trách nhiệm chỉ vì một chuỗi xuất hiện trong video của một người.

### Cách điều tra

Đội giữ nguyên bằng chứng theo quy trình, kiểm tra metadata và ngữ cảnh từng nguồn. Họ nối job controller, revision mong muốn, sự kiện tại thiết bị và phiên người dùng.

Nếu dữ liệu chưa đủ để xác định nguồn thay đổi, báo rõ kết luận chưa chắc chắn. Không lấp khoảng trống bằng giả định rằng mọi thay đổi đều tới từ terminal.

### Cải thiện sau sự kiện

- Tách input, output và lệnh trích xuất.
- Bổ sung audit API cùng mapping automation.
- Rà soát tài khoản chia sẻ và đường trực tiếp.
- Liên kết command recording với diff.
- Ghi trạng thái coverage và khoảng trống.
- Kiểm thử parser bằng tình huống xem cấu hình có chuỗi nhạy cảm.
- Bảo vệ cấu hình AAA và recording khỏi cùng một người tự ý sửa.

Kết quả cần đạt là chuỗi bằng chứng có thể giải thích, không chỉ tăng số lượng bản ghi.

## 20. Những lỗi thường gặp

### Gọi video terminal là danh sách lệnh chính xác

Video hoặc byte stream cần được hiểu theo ngữ cảnh. Parser trích xuất có thể sai và phải có giới hạn được ghi nhận.

### Ghi authorization rồi báo đã thực thi

Cho phép là một quyết định quyền, không phải kết quả thao tác.

### Bật một facility rồi mặc định mọi kênh được bao phủ

CLI, shell, API, controller và console có thể cần nguồn khác nhau.

### Dùng username chia sẻ làm căn cứ quy trách nhiệm

Cần mapping đáng tin cậy hoặc danh tính backend phân biệt phù hợp.

### Không bảo vệ đường accounting

Nguồn và đường truyền phải được xác thực, bảo vệ theo kiến trúc thực tế.

### Che ở màn hình rồi quên bản gốc

Bí mật có thể còn trong index, queue, log collector và file xuất.

### Coi ký log là chứng minh đầy đủ

Chữ ký không phát hiện mọi sự kiện chưa từng được tạo hoặc gửi.

### Gộp sự kiện cùng command text

Có thể xóa nhầm hai lần thao tác thật hoặc nhầm replay thành tác vụ mới.

### Đóng phiên rồi báo recording hoàn chỉnh

Cần đối soát nguồn, phần kết thúc, queue và khoảng trống.

### Replay bằng cách đưa recording vào shell

Nội dung phải được xem như dữ liệu không tin cậy, không thực thi lại.

### Bỏ qua đường automation

Thiết bị có thể được thay bởi job hoặc controller mà không có người gõ lệnh tương tác.

### Đặt thời gian lưu quá rộng mà không quản lý dữ liệu

Recording có thể chứa thông tin nhạy cảm; cần phạm vi, quyền và vòng đời phù hợp mục tiêu.

## 21. Bài thực hành

Thiết kế command recording cho môi trường lab gồm Edge-A, một gateway PAM và một controller.

Yêu cầu:

- Có danh tính cá nhân cho truy cập tương tác.
- Có danh tính máy riêng cho controller.
- Bao phủ các kênh được công bố và ghi nhận phần chưa bao phủ.
- Phân biệt input, output, quyết định quyền và kết quả.
- Không lưu credential thật trong báo cáo.
- Phát hiện được lỗi nguồn hoặc collector.
- Có kiểm thử quyền xem và quyền sửa bằng chứng.

Sản phẩm cần tạo:

1. Ma trận thiết bị, phiên bản, kênh và nguồn ghi.
2. Sơ đồ mapping danh tính cùng phiên.
3. Schema sự kiện có trạng thái unknown phù hợp.
4. Chính sách redaction với dữ liệu kiểm thử giả.
5. Thiết kế transport, buffer và xác nhận lưu trữ.
6. Phương án bảo vệ toàn vẹn và phát hiện khoảng trống.
7. Bộ ca kiểm thử có thao tác bị từ chối, cú pháp lỗi và phiên đồng thời.
8. Chuỗi đối soát recording với thay đổi cấu hình.
9. Chính sách người xem, xuất và thời gian lưu.
10. Runbook lỗi recording cùng ngoại lệ khẩn cấp.

Chỉ thực hành trên môi trường và danh tính được phép. Không cần thay AAA production, ngắt collector thật hoặc tạo credential nhạy cảm để hoàn thành bài.

Phương án đạt cần nêu rõ mỗi kết luận dựa trên nguồn nào và những giới hạn chưa được xác minh.

## 22. Câu hỏi tự kiểm tra

**Command recording có tự ngăn thao tác trái phép không?**

Không. Recording phục vụ quan sát và bằng chứng; authorization và những điểm thực thi quyền phải được thiết kế riêng.

**Một chuỗi lệnh xuất hiện trong video chứng minh điều gì?**

Trước hết chỉ chứng minh chuỗi đó xuất hiện trong dữ liệu được ghi. Cần biết nó là input, output, nội dung chưa gửi hay lệnh được thực thi.

**Vì sao phải kiểm tra SSH exec khi đã thử terminal tương tác?**

Vì đó là một đường sử dụng khác và có thể chịu khả năng recording khác.

**Một bản ghi được ký hợp lệ có luôn đầy đủ không?**

Không. Nó có thể được tạo sau khi thiếu một phần luồng, hoặc nguồn có thể đã không báo một số sự kiện.

**Che bí mật tại viewer có đủ không?**

Không nếu các bản gốc, hàng đợi, index hoặc bản xuất vẫn giữ giá trị bí mật ngoài chính sách.

**Vì sao cần cả thời gian nguồn và thời gian nhận?**

Để đánh giá độ trễ và hỗ trợ đối soát khi đồng hồ hoặc đường truyền không đồng nhất.

**Có thể quy người thay cấu hình chỉ bằng thời gian đăng nhập gần nhất không?**

Không đủ. Cần mapping phiên, kênh, thao tác và trạng thái thay đổi, nhất là khi có nhiều người và automation.

**Điều gì quan trọng hơn số lượng recording?**

Khả năng giải thích phạm vi được bao phủ, độ đầy đủ, chất lượng dữ liệu và nguồn bằng chứng cho từng kết luận.
