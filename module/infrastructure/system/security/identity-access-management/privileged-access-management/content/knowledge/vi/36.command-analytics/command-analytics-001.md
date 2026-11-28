# Full-text privileged command

## 1. Tìm kiếm toàn văn lệnh đặc quyền giải quyết vấn đề gì?

Một tổ chức đã triển khai Privileged Access Management (PAM) có thể biết ai mở phiên quản trị, tài khoản đích nào được cấp và phiên kéo dài bao lâu. Tuy nhiên, khi cần trả lời “trong phiên đó đã thao tác gì?”, thông tin đăng nhập hoặc một video dài thường chưa đủ thuận tiện để điều tra.

**Full-text privileged command** trong bài này là khả năng tìm kiếm trên biểu diễn văn bản của lệnh đặc quyền đã được hệ thống thu thập, đồng thời liên kết kết quả với người thực hiện, tài khoản sử dụng, máy đích, phiên truy cập và nguồn bằng chứng. Nó giúp tìm một lệnh hoặc một chuỗi thao tác mà không phải xem lại thủ công mọi phiên.

Ví dụ, sau sự cố của dịch vụ thanh toán, đội vận hành muốn xác định:

- Ai đã dùng quyền quản trị để kiểm tra hoặc thay đổi dịch vụ trên máy production?
- Lệnh nào chứa tên dịch vụ payment-api trong khoảng thời gian cần điều tra?
- Người thực hiện có yêu cầu JIT còn hiệu lực và ticket phù hợp không?
- Kết quả tìm được là văn bản nhập vào terminal, một tiến trình được ghi nhận, hay một lệnh bị policy từ chối?

Tìm kiếm toàn văn không thay thế least privilege, JIT/JEA, quản lý credential trong vault hay kiểm soát phiên. Nó làm dữ liệu hoạt động đặc quyền có thể truy vấn được, hỗ trợ kiểm toán, phát hiện bất thường và ứng phó sự cố.

Sau bài học, người học có thể thiết kế một bản ghi lệnh đủ ngữ cảnh, phân biệt các kiểu tìm kiếm, xây dựng truy vấn điều tra và nhận biết giới hạn của kết luận rút ra từ log.

## 2. Trước hết phải xác định “lệnh” được thu thập ở đâu

Cùng một thao tác có thể tạo ra nhiều loại dữ liệu khác nhau. Không được coi mọi chuỗi hiển thị trên terminal là một lệnh thực sự đã chạy.

| Nguồn thu thập | Dữ liệu có thể quan sát | Giới hạn cần ghi rõ |
| --- | --- | --- |
| Gateway hoặc proxy phiên | Luồng dữ liệu đi qua kênh truy cập được giám sát | Khả năng nhận diện lệnh phụ thuộc giao thức, cách xử lý terminal và tính năng sản phẩm |
| Shell hoặc terminal integration | Dòng lệnh, thời điểm hoặc ngữ cảnh do integration cung cấp | Có thể chỉ bao phủ một số shell; cần kiểm tra alias, script, shell lồng và kênh khác |
| Endpoint process telemetry | Tiến trình, executable, arguments và quan hệ cha–con tùy nguồn | Không tự động thể hiện mọi shell builtin hoặc ý định ban đầu của người dùng |
| PowerShell telemetry được cấu hình | Dữ liệu script hoặc lệnh theo cơ chế logging đang bật | Phạm vi phụ thuộc cấu hình; có thể chứa dữ liệu nhạy cảm |
| Hệ thống thực thi có cấu trúc | Tác vụ, tham số, tài khoản và quyết định policy | Không đại diện cho thao tác qua kênh nằm ngoài hệ thống đó |
| Bản ghi màn hình hoặc video | Nội dung nhìn thấy trong phiên | Trích xuất văn bản có thể sai và không tương đương sự kiện thực thi |

Ví dụ:

~~~bash
sudo systemctl status payment-api
~~~

Dòng này xuất hiện trên màn hình chưa chứng minh người dùng đã nhấn Enter hoặc tiến trình đã thực thi thành công. Nếu nó xuất hiện trong output của một tài liệu trợ giúp, nó thậm chí không phải lệnh người dùng nhập.

Ngược lại, khi một shell chạy script, nguồn thu thập có thể chỉ thấy lệnh gọi script, trong khi endpoint ghi nhận thêm các tiến trình con. Lệnh builtin của shell có thể không tạo một tiến trình riêng. Một luồng nhập terminal cũng có thể chứa phím sửa dòng, thao tác dán, terminal control sequence hoặc dữ liệu nhập cho một chương trình tương tác.

Vì vậy, mỗi bản ghi cần có **capture_type** và thông tin chất lượng thu thập. Tên field trong bài là schema minh họa, không phải chuẩn bắt buộc hay cam kết của một sản phẩm PAM cụ thể.

Một tập giá trị có thể là:

~~~text
terminal_input
shell_command
process_execution
structured_operation
screen_text_extraction
~~~

Không tự nâng screen_text_extraction thành process_execution chỉ vì chuỗi trông giống một câu lệnh.

## 3. Phân biệt full-text với các cơ chế liên quan

| Cơ chế | Câu hỏi phù hợp | Điều không nên suy diễn |
| --- | --- | --- |
| Lọc field chính xác | Máy đích có asset_id đúng bằng srv-pay-01 không? | Chuỗi trùng tên host không bảo đảm cùng một tài sản |
| Tìm token toàn văn | Bản ghi nào có từ khóa payment-api theo analyzer đang dùng? | Không mặc định tương đương tìm chuỗi con nguyên văn |
| Tìm phrase | Các từ xuất hiện theo thứ tự gần nhau như thế nào? | Phrase có thể vẫn qua tokenizer; không nhất thiết khớp từng byte |
| Tìm chuỗi con hoặc mẫu | Trường có chứa một đoạn văn bản hay pattern không? | Khả năng và chi phí phụ thuộc công cụ truy vấn |
| Phân tích cú pháp lệnh | Executable, tham số và đối tượng thao tác là gì? | Parser không nhất thiết hiểu mọi shell hoặc biểu thức động |
| Phát hiện hành vi | Chuỗi hoạt động có lệch baseline hay phạm vi phê duyệt không? | Một từ khóa đơn lẻ không đủ kết luận có hành vi xấu |

Một full-text index thường phân tích văn bản thành token và xây dựng cấu trúc để truy vấn nhanh. Cách phân tích có thể thay đổi chữ hoa/thường, dấu câu hoặc ranh giới từ. Vì vậy, cần phân biệt:

- **Field dạng text:** phục vụ tìm nội dung theo analyzer.
- **Field dạng exact/keyword:** phục vụ định danh, lọc và đối chiếu giá trị chính xác.
- **Bản ghi bằng chứng:** giữ biểu diễn và nguồn gốc cần thiết để kiểm tra lại kết quả.

Tên đường dẫn, tùy chọn có dấu gạch, địa chỉ mạng, chuỗi có dấu chấm và ký tự của shell thường bị tokenizer xử lý khác nhau. Không được giả định truy vấn payment-api sẽ luôn có cùng ngữ nghĩa trên mọi công cụ.

Ví dụ, cấu hình analyzer có thể biến một tên có dấu gạch thành nhiều token. Khi cần kiểm tra đúng target hoặc account, hãy dùng asset_id và account_id có cấu trúc thay vì dựa vào cách tách từ của trường lệnh.

## 4. Ngữ cảnh tối thiểu của một bản ghi

Một kết quả tìm kiếm chỉ có nội dung lệnh nhưng không có người, thời điểm và máy đích sẽ khó dùng trong kiểm toán. Thiết kế bản ghi cần phục vụ cả truy vấn và truy vết.

### 4.1. Nhóm định danh và thời gian

| Field minh họa | Ý nghĩa |
| --- | --- |
| event_id | Định danh ổn định của sự kiện, hỗ trợ phát hiện bản gửi lại |
| session_id | Liên kết tới phiên PAM |
| sequence_number | Thứ tự trong luồng của nguồn thu thập khi nguồn hỗ trợ |
| occurred_at | Thời điểm nguồn ghi nhận sự kiện |
| ingested_at | Thời điểm hệ thống nhận sự kiện |
| source_id | Nguồn phát sinh hoặc collector |
| capture_type | Loại quan sát đã thu được |

occurred_at và ingested_at phục vụ hai câu hỏi khác nhau. Sự kiện xảy ra lúc 09:04 nhưng đến index lúc 09:08 không có nghĩa lệnh được chạy lúc 09:08. Cần lưu độ trễ và tình trạng đồng bộ thời gian; không tự suy ra một thứ tự tuyệt đối từ timestamp của nhiều máy có thể lệch đồng hồ.

### 4.2. Nhóm chủ thể, quyền và tài sản

Cần phân biệt người mở phiên với tài khoản đích mà họ sử dụng:

~~~text
human_subject_id     = user-104
privileged_account_id = account-root-pay-01
asset_id             = srv-pay-01
environment          = production
access_request_id    = jit-204
ticket_id            = CHG-204
~~~

Nếu hai người cùng dùng một tài khoản root qua cơ chế kiểm soát, account_id một mình không thể quy trách nhiệm cá nhân. Liên kết người dùng đã xác thực với phiên được broker cấp là yếu tố cần thiết.

Với automation, không tạo một người dùng giả để điền cho đủ schema. Có thể lưu workload identity hoặc service identity, job_id và chủ sở hữu chịu trách nhiệm; cách diễn giải trách nhiệm khác với một phiên tương tác của con người.

Đối với việc cấp credential từ vault, có thể lưu tham chiếu tới tài khoản, lần cấp hoặc phiên bản credential nếu chính sách cho phép. Không đưa password, private key hay access token vào bản ghi tìm kiếm.

### 4.3. Nhóm nội dung và kết quả

Một thiết kế thực dụng phân biệt:

- command.search_text: văn bản đã xử lý để tìm kiếm, được che dữ liệu nhạy cảm.
- command.executable và command.arguments: dữ liệu có cấu trúc nếu nguồn thực sự cung cấp hoặc parser suy ra được.
- parse_status và parser_version: cho biết quá trình phân tích có thành công và dùng phiên bản nào.
- execution_observed: có quan sát phù hợp về thực thi hay chưa.
- policy_decision: cho phép, từ chối hoặc chưa đánh giá.
- execution_result: kết quả được nguồn ghi nhận, hoặc unknown.
- evidence_ref: tham chiếu tới bằng chứng được kiểm soát quyền riêng.

Không điền exit_code bằng 0 khi nguồn không thu thập exit code. Giá trị unknown phản ánh đúng mức độ quan sát hơn một kết quả thành công được phỏng đoán.

Một mã thoát thành công cũng không tự chứng minh trạng thái nghiệp vụ cuối cùng đúng. Ví dụ, một công cụ có thể gửi yêu cầu thành công nhưng tác vụ phía sau còn đang chạy.

## 5. Ví dụ bản ghi sự kiện đã bảo vệ dữ liệu

~~~json
{
  "schema_version": "1",
  "event_id": "evt-demo-00041",
  "session_id": "sess-demo-017",
  "sequence_number": 41,
  "occurred_at": "2026-01-15T09:04:12Z",
  "ingested_at": "2026-01-15T09:04:14Z",
  "source_id": "collector-demo-a",
  "capture_type": "shell_command",
  "human_subject_id": "user-104",
  "privileged_account_id": "account-root-pay-01",
  "asset_id": "srv-pay-01",
  "environment": "production",
  "access_request_id": "jit-204",
  "ticket_id": "CHG-204",
  "command": {
    "search_text": "sudo systemctl status payment-api",
    "executable": "systemctl",
    "arguments": ["status", "payment-api"],
    "parse_status": "derived",
    "parser_version": "demo-1"
  },
  "execution_observed": false,
  "policy_decision": "unknown",
  "execution_result": "unknown",
  "redaction": {
    "applied": true,
    "policy_version": "redact-demo-3"
  },
  "evidence_ref": "evidence-demo-017-041"
}
~~~

Các định danh đều là dữ liệu giả. executable trong ví dụ là giá trị parser suy ra để phục vụ phân tích; nó không chứng minh tiến trình systemctl đã xuất hiện trên hệ điều hành. Wrapper sudo cũng có ý nghĩa nên biểu diễn lệnh nguồn vẫn phải được giữ ở lớp bằng chứng theo chính sách.

Bản ghi ghi rõ execution_observed=false và execution_result=unknown. Đây là lựa chọn có chủ đích: nguồn minh họa chỉ cung cấp shell command, chưa có dữ liệu kết quả tương ứng.

Nếu nguồn bổ sung cung cấp process execution hoặc kết quả, nên liên kết sự kiện đó với bản ghi ban đầu bằng định danh và mức độ tin cậy. Không ghi đè lịch sử quan sát để làm như hệ thống đã biết tất cả ngay từ đầu.

## 6. Luồng xử lý từ thu thập đến truy vấn

~~~text
Nguồn được giám sát
    ↓
Tiếp nhận và kiểm tra cấu trúc
    ↓
Gắn định danh, loại quan sát, thời gian và ngữ cảnh quyền
    ↓
Che dữ liệu nhạy cảm theo chính sách
    ↓
Tạo biểu diễn tìm kiếm và field định danh
    ↓
Lập chỉ mục có kiểm soát truy cập
    ↓
Truy vấn theo phạm vi người điều tra
    ↓
Đối chiếu bản ghi với bằng chứng và dữ liệu liên quan
~~~

Đây là một luồng thiết kế, không phải cấu hình triển khai của một công cụ cụ thể.

### 6.1. Kiểm tra và làm giàu

Collector hoặc pipeline cần phát hiện dữ liệu thiếu session_id, timestamp không hợp lệ, bản ghi quá dài và schema không được hỗ trợ. Đầu vào không hợp lệ cần có trạng thái xử lý riêng; không âm thầm bỏ rồi trình bày hệ thống như đã thu đủ.

Thông tin asset, môi trường và quyền nên có nguồn đáng tin cậy. Nếu một nhãn được người dùng tự nhập, cần phân biệt nó với thuộc tính đã đối chiếu từ inventory hoặc hệ thống cấp quyền.

Lưu ngữ cảnh tại thời điểm sự kiện hoặc phiên bản mapping tương ứng. Nếu một tài khoản đã đổi chủ sau ba tháng, truy vấn lịch sử không được tự gán mọi lệnh cũ cho chủ hiện tại.

### 6.2. Chuẩn hóa để tìm, giữ khả năng đối chiếu

Chuẩn hóa có thể làm việc tìm kiếm tiện hơn nhưng cũng có thể làm mất thông tin. Nên có biểu diễn phục vụ tìm kiếm và tham chiếu tới nguồn, thay vì chỉ giữ chuỗi đã biến đổi.

Cần chú ý:

- Không xóa dấu nháy, dấu phân tách và ký tự đặc biệt mà không lưu lại cách xử lý.
- Không tự chuyển mọi arguments thành chữ thường; ý nghĩa chữ hoa/thường phụ thuộc đối tượng và môi trường.
- Không tự mở rộng alias hoặc biến môi trường khi thiếu ngữ cảnh shell đáng tin cậy.
- Không khẳng định một chuỗi đã được parse hoàn chỉnh khi parser chỉ nhận diện một phần.
- Nếu dữ liệu bị cắt ngắn, cần gắn cờ truncation và độ dài gốc nếu biết.

Lệnh gọi script, chuỗi được tạo động và thao tác trong chương trình tương tác không luôn thể hiện đầy đủ qua một dòng command text. Khi không hiểu được cú pháp, giữ trạng thái unknown hoặc partial và chuyển người điều tra về bằng chứng.

### 6.3. Chống trùng và theo dõi thiếu dữ liệu

Sự kiện có thể được gửi lại khi collector khôi phục kết nối. event_id ổn định giúp nhận diện bản gửi lại. Không loại trùng chỉ bằng nội dung lệnh: hai lần chạy cùng lệnh ở hai thời điểm khác nhau là hai hoạt động có ý nghĩa riêng.

Nếu sequence_number nhảy từ 41 sang 45, đó là dấu hiệu cần kiểm tra theo quy tắc nguồn; không tự khẳng định ba lệnh bị mất nếu nguồn còn dùng số thứ tự cho loại sự kiện khác.

Các trạng thái như collector offline, ingestion lag hoặc parse failure cần truy vấn được cùng dữ liệu hoạt động. Một index không có kết quả nhưng collector đang gián đoạn không tạo bằng chứng rằng không có thao tác.

## 7. Tìm kiếm toàn văn mà không biến index thành nơi chứa bí mật

Dòng lệnh có thể chứa token, mật khẩu, URI có credential, tên khách hàng hoặc dữ liệu nghiệp vụ. Output cũng có thể chứa bí mật dù input không chứa. Vì thế, “thu càng nhiều càng tốt” không phải nguyên tắc thiết kế phù hợp.

Một cách tiếp cận là giảm dữ liệu từ nguồn, che trước khi lập chỉ mục và chỉ giữ bằng chứng gốc khi có mục đích, quyền và thời hạn lưu rõ ràng.

### 7.1. Giảm khả năng bí mật xuất hiện trong lệnh

Trong thiết kế hệ thống PAM và automation, ưu tiên cơ chế truyền credential không đưa bí mật vào command line khi có lựa chọn phù hợp. Cách cụ thể phụ thuộc công cụ và môi trường; không giả định mọi công cụ đều có cùng một phương thức an toàn.

Nếu phát hiện credential đã lọt vào log, che hiển thị chỉ xử lý khả năng nhìn thấy về sau. Cần đánh giá phạm vi lộ và xử lý vòng đời credential theo quy trình, có thể bao gồm thu hồi hoặc luân chuyển. Không kết luận credential đã an toàn chỉ vì giao diện tìm kiếm đổi thành REDACTED.

### 7.2. Che trước khi văn bản đi vào index

~~~text
Văn bản dùng tìm kiếm:
maintenance-tool --token <REDACTED_TOKEN> --check payment-api
~~~

Ví dụ chỉ minh họa việc thay một giá trị nhạy cảm bằng marker. Không cần tạo một token giống thật để kiểm tra tài liệu.

Đặt redaction trước index giúp tránh đưa bí mật vào các cấu trúc tìm kiếm và bản sao phục vụ truy vấn. Chỉ che ở giao diện có thể vẫn để dữ liệu trong index, cache, export, cảnh báo hoặc API.

Regex đơn lẻ không bảo đảm nhận diện mọi secret. Khi có schema tham số, có thể kết hợp tên field, chính sách theo công cụ, quy tắc dữ liệu nhạy cảm và kiểm thử bằng dữ liệu giả. Ghi redaction policy version để giải thích vì sao một phần văn bản không còn xuất hiện.

Không tạo một hash dễ dò từ secret yếu để người xem log có thể đối chiếu. Marker ổn định hoặc fingerprint, nếu thực sự cần, phải qua thiết kế bảo vệ và phân quyền riêng.

### 7.3. Tách quyền tìm kiếm và quyền xem bằng chứng

Người được tìm lệnh đã che dữ liệu không mặc nhiên được mở luồng phiên gốc. Có thể tách các quyền:

1. Xem metadata trong phạm vi tài sản được giao.
2. Tìm command text đã che dữ liệu.
3. Mở bản ghi phiên hoặc bằng chứng chi tiết theo vụ việc.
4. Xuất dữ liệu phục vụ kiểm toán.

Mỗi lần truy vấn, mở bằng chứng hoặc export cần được ghi nhận phù hợp với chính sách. Search query cũng có thể chứa dữ liệu nhạy cảm, nên audit log của chính công cụ tìm kiếm cần được bảo vệ.

Kiểm soát truy cập phải được áp dụng ở dịch vụ truy vấn và đường dẫn xuất dữ liệu, không chỉ bằng cách ẩn nút trên giao diện. Bản gợi ý tìm kiếm, số lượng kết quả và facet cũng có thể tiết lộ thông tin ngoài phạm vi nếu triển khai sai.

## 8. Cách xây dựng truy vấn điều tra

Các truy vấn dưới đây là **DSL giả lập để diễn đạt ý tưởng**, không chạy trực tiếp trên một sản phẩm cụ thể. Khi triển khai phải ánh xạ sang cú pháp và analyzer thực tế.

### 8.1. Lọc phạm vi trước, tìm nội dung sau

Giả sử cần tìm thao tác liên quan payment-api trên một máy production trong cửa sổ sự cố:

~~~text
FILTER asset_id = "srv-pay-01"
FILTER environment = "production"
FILTER occurred_at >= "2026-01-15T09:00:00Z"
FILTER occurred_at <  "2026-01-15T09:30:00Z"
SEARCH command.search_text FOR "payment-api"
SORT occurred_at, session_id, sequence_number
~~~

Lọc bằng asset_id giúp tránh nhầm một tên máy xuất hiện trong nội dung lệnh với máy thực sự được thao tác. Khoảng thời gian nửa mở có điểm đầu bao gồm và điểm cuối loại trừ giúp tránh đếm trùng khi ghép các cửa sổ liên tiếp.

Thứ tự sắp xếp phục vụ xem kết quả; nó không tự giải quyết lệch đồng hồ giữa các nguồn.

### 8.2. Kết hợp từ khóa với loại quan sát

~~~text
FILTER session_id = "sess-demo-017"
FILTER capture_type = "shell_command"
SEARCH command.search_text FOR PHRASE "systemctl status"
RETURN occurred_at, human_subject_id, command.search_text, evidence_ref
~~~

Sau khi thấy kết quả, cần kiểm tra ngữ nghĩa phrase của công cụ. Nếu analyzer bỏ dấu hoặc token khác với mong đợi, kết quả có thể thiếu hoặc rộng hơn dự kiến.

Một bước tiếp theo có thể là mở các sự kiện lân cận của cùng session_id. Chỉ xem dòng trúng từ khóa dễ bỏ qua bối cảnh: người dùng có thể đang kiểm tra trạng thái sau thay đổi, hoặc đang đọc một file chứa chuỗi đó.

### 8.3. Đối chiếu phạm vi JIT và ticket

~~~text
FILTER human_subject_id = "user-104"
FILTER environment = "production"
FILTER occurred_at IN incident_window
JOIN access_request_id WITH approved_access_requests
RETURN session_id, asset_id, command.search_text,
       request_scope, request_validity, ticket_id
~~~

JOIN là yêu cầu phân tích minh họa. Một số hệ thống không hỗ trợ join trực tiếp; khi đó cần truy vấn hai nguồn và đối chiếu bằng định danh ổn định.

Không suy ra quyền chỉ từ một ticket_id có mặt trong log. Cần kiểm tra ticket có thật, trạng thái phê duyệt, thời gian, tài sản và loại hoạt động được phép. Lệnh xảy ra trong cửa sổ JIT vẫn có thể vượt phạm vi công việc; ngược lại, sự kiện nhận muộn không có nghĩa thực thi ngoài cửa sổ.

### 8.4. Tìm kiếm âm tính phải được diễn giải cẩn thận

“Không có kết quả” có thể do:

- Không có hoạt động phù hợp.
- Nguồn không bao phủ kênh truy cập.
- Lệnh nằm trong script hoặc giao diện tương tác mà nguồn không trích được.
- Analyzer tách từ khác với giả định.
- Dữ liệu đã bị che, cắt ngắn hoặc hết thời hạn lưu.
- Index chưa nhận đủ dữ liệu, hoặc người truy vấn không có quyền xem.
- Khoảng thời gian, timezone hoặc định danh lọc chưa đúng.

Một báo cáo tốt nói “không tìm thấy trong tập dữ liệu, phạm vi quyền và điều kiện truy vấn này”, kèm trạng thái coverage, thay vì khẳng định tuyệt đối rằng không có thao tác.

## 9. Tình huống thực hành: điều tra một cửa sổ bảo trì

### 9.1. Bối cảnh

Nhóm vận hành được duyệt truy cập JIT vào srv-pay-01 để kiểm tra dịch vụ payment-api. Yêu cầu CHG-204 chỉ cho phép kiểm tra trạng thái và đọc log. Sau cửa sổ bảo trì, hệ thống giám sát ghi nhận một thay đổi cấu hình ngoài kế hoạch.

Dữ liệu giả lập đã được che bí mật:

| Giờ UTC | Chủ thể | Loại quan sát | Nội dung tìm kiếm |
| --- | --- | --- | --- |
| 09:04:12 | user-104 | shell_command | sudo systemctl status payment-api |
| 09:06:20 | user-104 | shell_command | sudo journalctl -u payment-api --since 09:00 |
| 09:07:05 | user-104 | shell_command | sudo maintenance-tool --apply payment-api |
| 09:07:06 | user-104 | process_execution | maintenance-tool --apply payment-api |

maintenance-tool là công cụ giả định. Bảng không chứa kết quả nghiệp vụ của nó.

### 9.2. Trình tự điều tra

**Bước 1 — Khoanh vùng bằng định danh và thời gian.** Tìm các sự kiện của srv-pay-01 trong cửa sổ liên quan. Kiểm tra ingestion lag và tình trạng collector trước khi đánh giá độ đầy đủ.

**Bước 2 — Tìm theo đối tượng công việc.** Tìm payment-api trên command.search_text, sau đó mở toàn bộ phiên có kết quả. Không chỉ giữ các dòng chứa từ khóa, vì lệnh khác có thể tác động gián tiếp tới dịch vụ.

**Bước 3 — Phân biệt ý định, thực thi và kết quả.** Dòng shell_command cho thấy nguồn ghi nhận một lệnh. Sự kiện process_execution hỗ trợ nhận định có tiến trình tương ứng, nhưng mối liên kết vẫn cần đối chiếu timestamp, host, process identity hoặc cơ chế correlation của nguồn. Chưa có dữ liệu để kết luận thay đổi cấu hình thành công.

**Bước 4 — Đối chiếu quyền được phê duyệt.** Kiểm tra JIT, ticket và phạm vi. Một thao tác apply, nếu có ý nghĩa thay đổi trong công cụ đó, cần được đánh giá với quyền chỉ kiểm tra. Không kết luận dựa riêng vào từ apply; phải hiểu công cụ và bằng chứng.

**Bước 5 — Kiểm tra tác động.** Đối chiếu log ứng dụng, lịch sử cấu hình hoặc nguồn thay đổi được quản lý. Xác định tác vụ có chạy, đã thay đổi đối tượng nào và tác động tới dịch vụ ra sao.

**Bước 6 — Lưu hồ sơ điều tra.** Ghi query, thời điểm chạy query, phạm vi quyền, các event_id, bằng chứng được tham chiếu, trạng thái dữ liệu và phần kết luận chưa xác định. Tránh xuất toàn bộ phiên sang nơi lưu không được quản lý.

### 9.3. Kết luận mẫu ở đúng mức bằng chứng

“Đã tìm thấy một lệnh liên quan thao tác apply trong phiên sess-demo-017 của user-104; có sự kiện tiến trình liên quan cần đối chiếu chi tiết. Phạm vi CHG-204 được cung cấp chỉ cho phép kiểm tra. Chưa có bằng chứng trong tập dữ liệu này để kết luận thay đổi cấu hình đã thành công.”

Cách viết này tách quan sát khỏi nhận định. Nó đủ rõ để chuyển tiếp điều tra mà không biến kết quả full-text thành một phán quyết vượt quá dữ liệu.

## 10. Liên kết với các kiểm soát PAM khác

### 10.1. Least privilege và JEA

Kết quả tìm kiếm có thể cho thấy một nhóm người dùng thường chỉ dùng một số thao tác đọc. Đây là đầu vào để xem xét role, endpoint quản trị hoặc tập lệnh được giới hạn. Không tự động biến mọi lệnh thường thấy thành allowlist: lịch sử có thể chứa cả thao tác sai hoặc quyền dư thừa.

Nếu cần kiểm soát trước khi thực thi, phải dùng cơ chế thực sự có khả năng ra quyết định trên đường thực thi. Một truy vấn chạy sau khi lệnh đã xảy ra chỉ hỗ trợ phát hiện và điều tra.

### 10.2. JIT và break-glass

Khi phân tích lệnh ngoài khoảng cấp quyền thông thường, cần đối chiếu cả cơ chế break-glass được quản lý. Nhãn khẩn cấp không phải lý do bỏ audit; nó làm yêu cầu về quy trách nhiệm và rà soát sau sự kiện rõ hơn.

Không lấy thời điểm index nhận log làm thời điểm bắt đầu sử dụng đặc quyền. Hãy dùng thời gian nguồn, chất lượng đồng hồ và các sự kiện cấp/thu hồi quyền.

### 10.3. Vault và luân chuyển credential

Full-text index không phải nơi lưu hoặc truy hồi credential. Nó có thể liên kết tới tài khoản được quản lý, sự kiện cấp credential và vòng đời credential bằng ID được kiểm soát.

Khi lệnh hoặc output làm lộ credential, cần quản lý sự cố ở cả nguồn, pipeline và các bản sao dữ liệu. Việc luân chuyển credential giải quyết một phần rủi ro sử dụng tiếp; không tự xóa được các bản sao bí mật đã phát tán.

### 10.4. Giám sát phiên và phản ứng

Một kết quả đáng ngờ có thể mở vụ việc, tăng mức giám sát hoặc đề xuất kết thúc phiên theo quy trình. Cần phân biệt mức độ tin cậy và tác động vận hành trước khi tự động phản ứng.

Tìm thấy một từ khóa trong output hoặc tài liệu không có cùng ý nghĩa với việc quan sát một lệnh thực thi trên production. Nếu hệ thống tự động chặn hoặc kết thúc phiên, điều kiện phải được thiết kế, thử nghiệm và phê duyệt cho mục đích đó; không coi một rule full-text đơn giản là cơ chế hiểu đầy đủ hành vi.

## 11. Chất lượng dịch vụ tìm kiếm và khả năng kiểm toán

### 11.1. Chỉ số cần quan sát

| Chỉ số | Cách dùng |
| --- | --- |
| Ingestion lag | Biết dữ liệu tìm kiếm đang chậm bao lâu so với thời gian nguồn |
| Collector health | Phát hiện kênh thu thập ngừng hoặc suy giảm |
| Parse failure và truncation | Đánh giá phần dữ liệu không được diễn giải đầy đủ |
| Tỷ lệ phiên có command telemetry | Đo coverage trong tập phiên dự kiến được thu thập |
| Duplicate và gap theo nguồn | Theo dõi bản gửi lại hoặc dấu hiệu thiếu sự kiện |
| Query latency và tỷ lệ lỗi | Đánh giá khả năng sử dụng khi điều tra |
| Redaction issue đã xác nhận | Theo dõi bí mật bị lọt hoặc dữ liệu hữu ích bị che nhầm |
| Truy vấn hoặc export bị từ chối | Quan sát hiệu lực và nhu cầu điều chỉnh phân quyền |

Mẫu số của coverage phải rõ. “Có command telemetry ở 95% phiên đi qua gateway” không nói gì về các kênh đặc quyền chưa nằm trong inventory hoặc chưa buộc đi qua gateway.

Không đặt một ngưỡng chung cho mọi tổ chức. Ngưỡng cần theo mức độ nhạy cảm, khối lượng dữ liệu, yêu cầu phản ứng và khả năng hệ thống.

### 11.2. Bảo toàn bằng chứng

Index tối ưu cho tìm kiếm, có thể được reindex hoặc thay analyzer. Nó không nên là nguồn duy nhất để giải thích một sự kiện quan trọng.

Cần quản lý bằng chứng với kiểm soát truy cập, retention, lịch sử xử lý và cơ chế phát hiện thay đổi phù hợp. Một digest có thể hỗ trợ kiểm tra tính toàn vẹn khi đối chiếu với giá trị được bảo vệ; bản thân digest không chứng minh dữ liệu nguồn đã được thu đủ hoặc người ghi log là đáng tin cậy.

Nếu có legal hold hoặc yêu cầu lưu giữ vụ việc đã được thiết lập, việc xóa theo vòng đời phải xử lý theo chính sách áp dụng. Không cố định một số ngày lưu cho mọi loại dữ liệu và mọi tổ chức.

Khi xuất kết quả, nên kèm:

- Điều kiện query và phạm vi thời gian, múi giờ.
- Thời điểm truy vấn và trạng thái dữ liệu liên quan.
- event_id, session_id, source_id và capture_type.
- Các field đã che hoặc bị cắt, cùng phiên bản xử lý nếu có.
- Tham chiếu bằng chứng và lịch sử truy cập phục vụ vụ việc.

Không cần xuất secret hoặc toàn bộ nội dung phiên để chứng minh rằng đã thực hiện tìm kiếm.

## 12. Sai lầm thường gặp và cách sửa

| Sai lầm | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Coi shell history là nhật ký đầy đủ, bất biến | Bỏ sót kênh, phiên hoặc lệnh không được nguồn ghi lại | Xác định coverage, nguồn tin cậy và cơ chế thu thập được quản lý |
| Tìm tên máy trong command text để xác định máy đích | Nhầm đối tượng được nhắc tới với nơi lệnh chạy | Lọc asset_id từ ngữ cảnh phiên hoặc nguồn |
| Chỉ giữ bản chuẩn hóa | Khó kiểm tra cú pháp và cách biến đổi | Giữ provenance và tham chiếu bằng chứng theo chính sách |
| Dùng một tokenizer cho mọi nhu cầu exact match | Thiếu hoặc dư kết quả do tách từ | Tách field text và field chính xác, thử dữ liệu đại diện |
| Che secret ở giao diện nhưng giữ nguyên trong index | API, export hoặc bản sao vẫn có thể lộ bí mật | Che trước index và quản lý mọi đường đi dữ liệu |
| Loại trùng chỉ bằng command text | Mất các lần thực thi lặp lại hợp lệ | Dùng event identity và quy tắc của nguồn |
| Mặc định kết quả thành công khi không có exit code | Kết luận sai về thực thi hoặc tác động | Giữ unknown và đối chiếu nguồn bổ sung |
| Kết luận không có thao tác từ truy vấn rỗng | Bỏ qua lag, quyền, retention và coverage | Ghi rõ giới hạn tập dữ liệu và kiểm tra sức khỏe pipeline |
| Phản ứng tự động chỉ vì một từ khóa | Tạo cảnh báo sai hoặc gián đoạn vận hành | Thêm ngữ cảnh, chất lượng nguồn và điều kiện phản ứng phù hợp |

## 13. Bài tập tự kiểm tra

### Bài tập 1 — Thiết kế bản ghi tối thiểu

Một bản ghi hiện chỉ có username, timestamp và command. Hãy bổ sung những field cần thiết để phân biệt người dùng với tài khoản đặc quyền, xác định máy đích, liên kết JIT, phân biệt loại quan sát và truy vết bằng chứng.

**Gợi ý đáp án:** human_subject_id hoặc workload identity, privileged_account_id, asset_id, session_id, event_id, source_id, capture_type, occurred_at, ingested_at, access_request_id, ticket_id khi có, command.search_text đã che dữ liệu, trạng thái parse/thực thi và evidence_ref. Không tạo giá trị giả khi nguồn không cung cấp.

### Bài tập 2 — Diễn giải một kết quả tìm kiếm

Truy vấn từ khóa restart trả về một sự kiện screen_text_extraction. Có thể kết luận dịch vụ đã bị khởi động lại không?

**Gợi ý đáp án:** Chưa thể. Chuỗi có thể nằm trong output, tài liệu hoặc văn bản chưa được thực thi. Cần đối chiếu nguồn thu thập, ngữ cảnh phiên và sự kiện thực thi hoặc thay đổi trạng thái dịch vụ.

### Bài tập 3 — Không tìm thấy lệnh

Đội kiểm toán không thấy lệnh liên quan cấu hình trong cửa sổ sự cố. Collector có độ trễ 12 phút, còn query kết thúc ở thời điểm hiện tại. Báo cáo nên viết thế nào?

**Gợi ý đáp án:** Nêu rằng chưa tìm thấy trong dữ liệu hiện sẵn có, ghi rõ độ trễ và cửa sổ chưa đầy đủ. Tiếp tục kiểm tra khi dữ liệu đến đủ, đồng thời đối chiếu coverage và nguồn thay đổi khác. Không khẳng định chưa có thao tác cấu hình.

### Bài tập 4 — Token xuất hiện trong log

Một bản ghi đã được index với token trong argument. Sau khi bật che hiển thị, vấn đề đã được giải quyết hoàn toàn chưa?

**Gợi ý đáp án:** Chưa. Cần đánh giá dữ liệu trong index, bản sao, export và các hệ thống nhận log; xử lý credential theo quy trình. Điều chỉnh redaction trước index và kiểm thử bằng secret giả để hạn chế lặp lại.

## 14. Những điểm cần ghi nhớ

Tìm kiếm toàn văn lệnh đặc quyền biến hoạt động PAM thành dữ liệu có thể tra cứu, nhưng độ tin cậy của kết luận phụ thuộc nguồn thu thập và ngữ cảnh của từng bản ghi.

Một thiết kế hữu ích cần đồng thời có command text đã bảo vệ dữ liệu, định danh người và tài khoản đích, tài sản, phiên, thời gian, loại quan sát và tham chiếu bằng chứng. Field tìm kiếm phục vụ khám phá; field chính xác phục vụ lọc; nguồn bằng chứng phục vụ kiểm tra lại.

Khi điều tra, hãy bắt đầu từ phạm vi tài sản và thời gian, mở rộng theo nội dung lệnh, đối chiếu JIT/JEA hoặc ticket, rồi kiểm tra thực thi và tác động từ các nguồn liên quan. Kết quả trùng từ khóa là điểm bắt đầu của phân tích, còn kết quả rỗng luôn phải được đọc cùng coverage, retention, độ trễ và quyền truy cập.
